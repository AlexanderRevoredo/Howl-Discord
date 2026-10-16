import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import discord
from bot import Howl


class CommandCleanupTests(unittest.IsolatedAsyncioTestCase):
    def client(self, commands, *, synced=True):
        return SimpleNamespace(
            global_commands_ready=synced, cleaned_command_guilds=set(), command_cleanup_lock=asyncio.Lock(),
            tree=SimpleNamespace(get_commands=lambda: [SimpleNamespace(name="radio"), SimpleNamespace(name="tocando")],
                                 fetch_commands=AsyncMock(return_value=commands)),
        )

    async def test_deletes_only_old_chat_command_copies(self):
        radio = SimpleNamespace(name="radio", type=discord.AppCommandType.chat_input, delete=AsyncMock())
        other = SimpleNamespace(name="other", type=discord.AppCommandType.chat_input, delete=AsyncMock())
        context = SimpleNamespace(name="radio", type=discord.AppCommandType.user, delete=AsyncMock())
        client = self.client([radio, other, context])
        guild = SimpleNamespace(id=1, name="Test")
        self.assertEqual(await Howl.cleanup_legacy_commands(client, guild), 1)
        radio.delete.assert_awaited_once()
        other.delete.assert_not_awaited()
        context.delete.assert_not_awaited()
        self.assertEqual(await Howl.cleanup_legacy_commands(client, guild), 0)
        client.tree.fetch_commands.assert_awaited_once()

    async def test_no_removal_before_successful_global_sync(self):
        client = self.client([], synced=False)
        self.assertEqual(await Howl.cleanup_legacy_commands(client, SimpleNamespace(id=1)), 0)
        client.tree.fetch_commands.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
