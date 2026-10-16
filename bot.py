"""Howl: live radio in Discord voice channels. Run with python bot.py."""
import asyncio
import logging
import os
from collections import defaultdict
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

from catalog import load_stations
from audio import ensure_demo, find_ffmpeg
from playback import prepare_source, SwitchableAudio, TuneRequests, TuneCancelled
from radio_browser import StreamResolver

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")
log = logging.getLogger("howl")


class Howl(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.stations = load_stations(BASE / "stations.json")
        self.locks = defaultdict(asyncio.Lock)
        self.current = {}
        self.last_station = {}
        self.tunes = TuneRequests()
        self.resolver = StreamResolver()
        self.ffmpeg = os.getenv("FFMPEG_PATH", "ffmpeg")
        self.global_commands_ready = False
        self.cleaned_command_guilds = set()
        self.command_cleanup_lock = asyncio.Lock()

    async def setup_hook(self):
        self.add_view(RadioPanel())
        self.resolver.warm(self.stations.values())
        synced = await self.tree.sync()
        self.global_commands_ready = True
        log.info("Comandos globais registrados: %s", ", ".join(c.name for c in synced))

    async def cleanup_legacy_commands(self, guild):
        # Only remove this application's old guild copies after global sync succeeds.
        async with self.command_cleanup_lock:
            if not self.global_commands_ready or guild.id in self.cleaned_command_guilds:
                return 0
            names = {command.name for command in self.tree.get_commands()}
            try:
                commands = await self.tree.fetch_commands(guild=guild)
                removed = 0
                for command in commands:
                    if command.type == discord.AppCommandType.chat_input and command.name in names:
                        await command.delete()
                        removed += 1
                self.cleaned_command_guilds.add(guild.id)
                if removed:
                    log.info("Removidos %s comandos de teste duplicados de %s", removed, guild.name)
                return removed
            except discord.HTTPException:
                log.exception("Não consegui limpar os comandos de teste de %s; tentarei na próxima conexão.", guild.name)
                return 0

    async def on_guild_join(self, guild):
        await self.cleanup_legacy_commands(guild)

    async def on_ready(self):
        log.info("Howl conectado como %s", self.user)
        log.info("Servidores conectados: %s", ", ".join(g.name for g in self.guilds) or "nenhum")
        for guild in self.guilds:
            await self.cleanup_legacy_commands(guild)
        if not self.guilds:
            log.warning("Adicione o Howl ao servidor: %s", discord.utils.oauth_url(
                self.application_id,
                permissions=discord.Permissions(view_channel=True, send_messages=True, embed_links=True, connect=True, speak=True),
                scopes=("bot", "applications.commands"),
            ))

    async def on_voice_state_update(self, member, before, after):
        guild = member.guild
        async with self.locks[guild.id]:
            voice = guild.voice_client
            if voice and not any(not m.bot for m in voice.channel.members):
                self.tunes.cancel(guild.id)
                await voice.disconnect(force=True)
                self.current.pop(guild.id, None)
            if member.id == self.user.id and after.channel is None:
                self.tunes.cancel(guild.id)
                self.current.pop(guild.id, None)

    async def close(self):
        for guild_id in list(self.tunes.pending):
            self.tunes.cancel(guild_id)
        await self.resolver.close()
        await super().close()


bot = Howl()


def member_channel(interaction):
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
        raise ValueError("Entre em um canal de voz para controlar o Howl.")
    channel = member.voice.channel
    if not isinstance(channel, discord.VoiceChannel):
        raise ValueError("Use um canal de voz comum; palcos ainda não são suportados.")
    voice = interaction.guild.voice_client
    if voice and voice.channel != channel:
        raise ValueError("Entre no mesmo canal de voz do Howl para controlá-lo.")
    return channel


class RadioPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        if bot.stations:
            select = discord.ui.Select(custom_id="howl:station", placeholder="Escolha uma estação", options=[
                discord.SelectOption(label=s.name, value=s.id, description=s.category)
                for s in bot.stations.values()
            ])
            select.callback = self.choose
            self.add_item(select)

    async def choose(self, interaction, *, resume=False):
        await interaction.response.defer(ephemeral=True, thinking=True)
        token = None
        source = None
        old_source = None
        guild_id = interaction.guild_id
        started = asyncio.get_running_loop().time()
        try:
            async with bot.locks[guild_id]:
                channel = member_channel(interaction)
                permissions = channel.permissions_for(interaction.guild.me)
                if not (permissions.view_channel and permissions.connect and permissions.speak):
                    raise ValueError("Preciso das permissões Ver canal, Conectar e Falar nesse canal.")
                station_id = bot.last_station.get(guild_id) if resume else interaction.data["values"][0]
                if station_id not in bot.stations:
                    raise ValueError("Escolha uma rádio no menu primeiro; depois você pode usar Retomar.")
                station = bot.stations[station_id]
                token = bot.tunes.begin(guild_id)
                voice = interaction.guild.voice_client
                if voice and voice.is_playing() and bot.current.get(guild_id) == station:
                    await interaction.edit_original_response(content=f"🐺 **{station.name}** já está tocando.")
                    return
                original_channel_id = channel.id
                playing = voice is not None and voice.is_playing()

            # Loading never holds the guild lock or interrupts the old source.
            await interaction.edit_original_response(content=(
                f"🐺 Carregando **{station.name}**… "
                + ("A rádio atual continua tocando." if playing else "Vou entrar na call quando o áudio estiver pronto.")
            ))
            executable = find_ffmpeg(bot.ffmpeg)
            if station.kind == "demo":
                audio_input = str(await asyncio.to_thread(ensure_demo, BASE / "assets" / "demo.wav"))
            else:
                audio_input = bot.resolver.url_for(station)
            try:
                source = await prepare_source(audio_input, executable, demo=station.kind == "demo", cancel=token)
            except ValueError:
                if not bot.tunes.active(guild_id, token):
                    raise TuneCancelled()
                refreshed = await bot.resolver.refresh(station)
                if refreshed == audio_input:
                    raise
                source = await prepare_source(refreshed, executable, cancel=token)

            async with bot.locks[guild_id]:
                if not bot.tunes.active(guild_id, token):
                    raise TuneCancelled()
                channel = member_channel(interaction)
                if channel.id != original_channel_id:
                    raise ValueError("Você mudou de canal durante o carregamento. Selecione a rádio novamente.")
                voice = interaction.guild.voice_client
                if not voice:
                    voice = await asyncio.wait_for(
                        channel.connect(self_deaf=True, timeout=10, reconnect=False), timeout=12,
                    )
                if not voice.is_connected():
                    raise ValueError("A conexão de voz foi encerrada. Selecione a estação novamente.")
                if not bot.tunes.active(guild_id, token):
                    raise TuneCancelled()
                # Swap in the same sender: no stop/play cycle or silence packets between stations.
                if voice.is_playing() and isinstance(voice.source, SwitchableAudio):
                    old_source = voice.source.swap(source)
                    source = None
                else:
                    player = SwitchableAudio(source)
                    voice.stop()
                    try:
                        voice.play(player, after=lambda error: log.warning("Reprodução interrompida: %s", error) if error else None)
                    except Exception:
                        await asyncio.to_thread(player.cleanup)
                        source = None
                        raise
                    source = None
                bot.current[guild_id] = station
                bot.last_station[guild_id] = station.id
            log.info("Estação %s pronta em %.1fs", station.name, asyncio.get_running_loop().time() - started)
            await interaction.edit_original_response(content=f"🐺 Tocando **{station.name}** em {channel.mention}.")
        except TuneCancelled:
            await interaction.edit_original_response(content="Seleção cancelada por uma nova escolha ou pelo controle de parada.")
        except ValueError as error:
            await interaction.edit_original_response(content=str(error))
        except asyncio.TimeoutError:
            await interaction.edit_original_response(content="A conexão de voz demorou para responder. Tente novamente.")
        except Exception:
            log.exception("Falha ao sintonizar estação")
            await interaction.edit_original_response(content="Não consegui iniciar essa rádio. Se havia outra tocando, ela foi mantida. Os detalhes estão no log.")
        finally:
            if token:
                bot.tunes.finish(guild_id, token)
            # Terminating FFmpeg can block; never do that on Discord's event loop.
            for unused in (source, old_source):
                if unused:
                    await asyncio.to_thread(unused.cleanup)

    async def control(self, interaction, disconnect):
        await interaction.response.defer(ephemeral=True, thinking=True)
        async with bot.locks[interaction.guild_id]:
            try:
                member_channel(interaction)
                bot.tunes.cancel(interaction.guild_id)
                voice = interaction.guild.voice_client
                if voice:
                    if disconnect:
                        await voice.disconnect(force=True)
                    else:
                        voice.stop()
                bot.current.pop(interaction.guild_id, None)
                await interaction.followup.send("🐺 Desconectado." if disconnect else "⏹ Reprodução parada.", ephemeral=True)
            except ValueError as error:
                await interaction.followup.send(str(error), ephemeral=True)

    @discord.ui.button(label="Retomar", emoji="▶", style=discord.ButtonStyle.success, custom_id="howl:resume")
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.choose(interaction, resume=True)

    @discord.ui.button(label="Parar", emoji="⏹", style=discord.ButtonStyle.secondary, custom_id="howl:stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.control(interaction, False)

    @discord.ui.button(label="Desconectar", emoji="👋", style=discord.ButtonStyle.danger, custom_id="howl:disconnect")
    async def disconnect(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.control(interaction, True)


@bot.tree.command(name="radio", description="Abra o painel de rádios do Howl")
@app_commands.guild_only()
async def radio(interaction: discord.Interaction):
    description = "Escolha uma estação para ouvir no seu canal de voz.\nUse /tocando para consultar a estação atual."
    if not bot.stations:
        description = "Nenhuma estação ativa. Configure uma fonte autorizada em stations.json e reinicie o Howl."
    embed = discord.Embed(title="🐺 Howl · Rádio ao vivo", description=description, color=0x8576D9)
    embed.set_footer(text="Parar e Retomar controlam a última rádio · Retomar volta à transmissão ao vivo")
    await interaction.response.send_message(embed=embed, view=RadioPanel())


@bot.tree.command(name="tocando", description="Veja a estação que está tocando")
@app_commands.guild_only()
async def now_playing(interaction: discord.Interaction):
    station = bot.current.get(interaction.guild_id)
    voice = interaction.guild.voice_client
    text = f"📻 Tocando **{station.name}** · {station.category}" if station and voice and voice.is_playing() else "O Howl não está tocando nenhuma rádio."
    await interaction.response.send_message(text, ephemeral=True)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv(BASE / ".env")
    bot.ffmpeg = os.getenv("FFMPEG_PATH", "ffmpeg")
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise SystemExit("Configure DISCORD_TOKEN no arquivo .env (veja .env.example).")
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
