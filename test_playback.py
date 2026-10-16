import unittest
from unittest.mock import patch

from playback import BufferedAudio, SILENCE


class ControlledSource:
    def __init__(self):
        import queue
        self.input = queue.Queue()
        self.closed = False

    def read(self):
        return self.input.get()

    def cleanup(self):
        self.closed = True
        self.input.put(b"")


class PlaybackTests(unittest.TestCase):
    def test_preserves_order_and_recovers_from_jitter(self):
        source = ControlledSource()
        buffered = BufferedAudio(source, prebuffer=2, capacity=4)
        try:
            source.input.put(b"one")
            source.input.put(b"two")
            buffered.prime(timeout=1)
            self.assertEqual(buffered.read(), b"one")
            self.assertEqual(buffered.read(), b"two")
            self.assertEqual(buffered.read(), SILENCE)
            self.assertEqual(buffered.underruns, 1)
            buffered.ready.clear()
            source.input.put(b"three")
            source.input.put(b"four")
            self.assertTrue(buffered.ready.wait(1))
            self.assertEqual(buffered.read(), b"three")
            self.assertEqual(buffered.read(), b"four")
            source.input.put(b"")
            self.assertTrue(buffered.finished.wait(1))
            self.assertEqual(buffered.read(), b"")
        finally:
            buffered.cleanup()
        self.assertFalse(buffered.worker.is_alive())
        self.assertTrue(source.closed)

    def test_timeout_cleans_up(self):
        source = ControlledSource()
        buffered = BufferedAudio(source)
        with self.assertRaises(ValueError):
            buffered.prime(timeout=0.01)
        self.assertTrue(source.closed)
        self.assertFalse(buffered.worker.is_alive())

    def test_stop_when_buffer_full(self):
        source = ControlledSource()
        buffered = BufferedAudio(source, prebuffer=1, capacity=2)
        for _ in range(10):
            source.input.put(b"packet")
        buffered.prime(timeout=1)
        buffered.cleanup()
        buffered.cleanup()
        self.assertFalse(buffered.worker.is_alive())
        self.assertEqual(buffered.read(), b"")

    def test_radio_browser_outage_keeps_saved_url(self):
        from catalog import Station
        from radio_browser import resolve
        station = Station("test", "Test", "Test", "https://example.com/live", "", radio_browser_uuid="abc")
        with patch("radio_browser.request_json", side_effect=ConnectionError):
            self.assertEqual(resolve(station), station.url)

    def test_radio_browser_refreshes_url(self):
        from catalog import Station
        from radio_browser import resolve
        station = Station("test", "Test", "Test", "https://example.com/old", "", radio_browser_uuid="abc")
        with patch("radio_browser.request_json", return_value=[{"lastcheckok": 1, "url_resolved": "https://example.com/new"}]):
            self.assertEqual(resolve(station), "https://example.com/new")


if __name__ == "__main__":
    unittest.main()
