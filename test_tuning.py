"""Station switches must preserve audio and respect stop/newer requests."""
import asyncio
from collections import defaultdict
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import bot as app
from catalog import Station
from playback import SwitchableAudio, TuneRequests, TuneCancelled


class Source:
    def __init__(self, packet):
        self.packet = packet
        self.closed = False

    def read(self):
        return self.packet if not self.closed else b""

    def cleanup(self):
        self.closed = True


class Voice:
    def __init__(self, source):
        self.source = SwitchableAudio(source)
        self.stops = 0
        self.connected = True

    def is_playing(self):
        return self.source is not None and self.connected

    def is_connected(self):
        return self.connected

    def stop(self):
        self.stops += 1
        if self.source:
            self.source.cleanup()
            self.source = None

    def play(self, source, *, after=None):
        self.source = source


class TuningTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old = Source(b"old")
        self.new = Source(b"new")
        self.voice = Voice(self.old)
        self.station = Station("new", "New", "Test", "https://example.com/live", "")
        self.channel = SimpleNamespace(id=10, mention="#voice", permissions_for=lambda _: SimpleNamespace(
            view_channel=True, connect=True, speak=True))
        self.guild = SimpleNamespace(voice_client=self.voice, me=None)
        self.client = SimpleNamespace(
            stations={"new": self.station}, locks=defaultdict(asyncio.Lock),
            current={1: "old"}, last_station={}, tunes=TuneRequests(), ffmpeg="ffmpeg",
            resolver=SimpleNamespace(url_for=lambda s: s.url, refresh=AsyncMock(return_value=self.station.url)),
        )
        self.patches = [patch.object(app, "bot", self.client),
                        patch.object(app, "member_channel", return_value=self.channel),
                        patch.object(app, "find_ffmpeg", return_value="ffmpeg")]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
        self.panel = app.RadioPanel()

    def interaction(self):
        return SimpleNamespace(
            guild_id=1, guild=self.guild, data={"values": ["new"]},
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()), edit_original_response=AsyncMock(),
        )

    async def test_old_station_plays_until_new_is_ready(self):
        entered, release = threading.Event(), threading.Event()

        def prepare(*args, **kwargs):
            entered.set()
            release.wait(2)
            return self.new

        with patch("playback.create_source", side_effect=prepare):
            task = asyncio.create_task(self.panel.choose(self.interaction()))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                self.assertEqual(self.voice.source.read(), b"old")
                self.assertEqual(self.voice.stops, 0)
                self.assertFalse(self.client.locks[1].locked())
            finally:
                release.set()
                await asyncio.wait_for(task, 2)
        self.assertEqual(self.voice.source.read(), b"new")
        self.assertEqual(self.voice.stops, 0)
        self.assertTrue(self.old.closed)
        self.assertEqual(self.client.current[1], self.station)

    async def test_failed_station_keeps_previous_audio(self):
        with patch("playback.create_source", side_effect=ValueError("offline")):
            await self.panel.choose(self.interaction())
        self.assertEqual(self.voice.source.read(), b"old")
        self.assertFalse(self.old.closed)
        self.assertEqual(self.voice.stops, 0)

    async def test_resume_after_stop_reuses_last_station(self):
        with patch("playback.create_source", return_value=self.new):
            await self.panel.choose(self.interaction())
        await self.panel.control(self.interaction(), False)
        self.assertIsNone(self.voice.source)
        self.assertEqual(self.client.last_station[1], self.station.id)
        resumed_source = Source(b"resumed-live-audio")
        interaction = self.interaction()
        interaction.data = {"custom_id": "howl:resume"}
        with patch("playback.create_source", return_value=resumed_source):
            await self.panel.resume.callback(interaction)
        self.assertEqual(self.voice.source.read(), b"resumed-live-audio")
        self.assertEqual(self.client.current[1], self.station)

    async def test_resume_before_first_selection_prompts_for_station(self):
        interaction = self.interaction()
        interaction.data = {"custom_id": "howl:resume"}
        with patch("playback.create_source") as prepare:
            await self.panel.resume.callback(interaction)
        prepare.assert_not_called()
        self.assertIn("Escolha uma rádio", interaction.edit_original_response.call_args.kwargs["content"])

    async def test_resume_while_already_playing_does_not_restart(self):
        self.client.current[1] = self.station
        self.client.last_station[1] = self.station.id
        with patch("playback.create_source") as prepare:
            await self.panel.resume.callback(self.interaction())
        prepare.assert_not_called()
        self.assertEqual(self.voice.stops, 0)

    async def test_resume_obeys_voice_channel_checks(self):
        self.client.last_station[1] = self.station.id
        with patch.object(app, "member_channel", side_effect=ValueError("Entre no mesmo canal")), patch("playback.create_source") as prepare:
            await self.panel.resume.callback(self.interaction())
        prepare.assert_not_called()

    async def test_stop_during_load_prevents_late_restart(self):
        entered = threading.Event()

        def prepare(*args, cancel, **kwargs):
            entered.set()
            cancel.wait(2)
            raise TuneCancelled()

        with patch("playback.create_source", side_effect=prepare):
            task = asyncio.create_task(self.panel.choose(self.interaction()))
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            await asyncio.wait_for(self.panel.control(self.interaction(), False), 0.5)
            await asyncio.wait_for(task, 2)
        self.assertIsNone(self.voice.source)
        self.assertNotIn(1, self.client.current)
        self.assertTrue(self.old.closed)

    def test_new_selection_invalidates_previous(self):
        first = self.client.tunes.begin(1)
        second = self.client.tunes.begin(1)
        self.assertTrue(first.is_set())
        self.client.tunes.finish(1, first)
        self.assertTrue(self.client.tunes.active(1, second))

    async def test_late_result_cannot_replace_newer_selection(self):
        entered, release = threading.Event(), threading.Event()
        stale = Source(b"stale")
        calls = []

        def prepare(*args, **kwargs):
            calls.append(True)
            if len(calls) == 1:
                entered.set()
                release.wait(2)
                return stale
            return self.new

        with patch("playback.create_source", side_effect=prepare):
            first = asyncio.create_task(self.panel.choose(self.interaction()))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                await self.panel.choose(self.interaction())
            finally:
                release.set()
                await asyncio.wait_for(first, 2)
        self.assertEqual(self.voice.source.read(), b"new")
        self.assertTrue(stale.closed)

    async def test_cancelling_coroutine_cleans_late_source(self):
        from playback import prepare_source
        entered = threading.Event()
        token = threading.Event()

        def prepare(*args, **kwargs):
            entered.set()
            token.wait(2)
            return self.new

        with patch("playback.create_source", side_effect=prepare):
            task = asyncio.create_task(prepare_source("url", "ffmpeg", cancel=token))
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(self.new.closed)


class ResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_lookup_returns_saved_url_without_waiting_for_refresh(self):
        from radio_browser import StreamResolver
        resolver = StreamResolver()
        station = Station("test", "Test", "Test", "https://example.com/live", "", radio_browser_uuid="abc")

        async def slow_refresh(station):
            await asyncio.Event().wait()

        with patch.object(resolver, "_fetch", side_effect=slow_refresh):
            try:
                self.assertEqual(resolver.url_for(station), station.url)
                self.assertEqual(resolver.url_for(station), station.url)
                self.assertEqual(len(resolver.tasks), 1)
                await asyncio.sleep(0)
            finally:
                await resolver.close()


if __name__ == "__main__":
    unittest.main()
