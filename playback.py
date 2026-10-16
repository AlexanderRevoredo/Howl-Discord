"""Bounded buffer of 20 ms Opus packets between FFmpeg and Discord."""
import logging
import asyncio
import queue
import threading
import time

import discord

log = logging.getLogger("howl.audio")
SILENCE = b"\xf8\xff\xfe"


class BufferedAudio(discord.AudioSource):
    def __init__(self, source, *, prebuffer=150, capacity=300):
        self.source = source
        self.packets = queue.Queue(maxsize=capacity)
        self.prebuffer = prebuffer
        self.ready = threading.Event()
        self.finished = threading.Event()
        self.stopped = threading.Event()
        self.rebuffering = False
        self.underruns = 0
        self.error = None
        self.worker = threading.Thread(target=self._fill, name="howl-audio-buffer", daemon=True)
        self.worker.start()

    def _fill(self):
        try:
            while not self.stopped.is_set():
                packet = self.source.read()
                if not packet:
                    break
                while not self.stopped.is_set():
                    try:
                        self.packets.put(packet, timeout=0.1)
                        break
                    except queue.Full:
                        pass
                if self.packets.qsize() >= self.prebuffer:
                    self.ready.set()
        except Exception as error:
            self.error = error
            log.exception("Falha ao preencher buffer de áudio")
        finally:
            self.finished.set()
            self.ready.set()

    def prime(self, timeout=12, cancel=None):
        """Called off the event loop before replacing the current source."""
        deadline = time.monotonic() + timeout
        while True:
            if cancel is not None and cancel.is_set():
                self.cleanup()
                raise TuneCancelled()
            if self.ready.is_set():
                if self.packets.empty():
                    self.cleanup()
                    raise ValueError("A rádio não enviou áudio. A estação anterior foi mantida, se estava tocando.")
                break
            if time.monotonic() >= deadline:
                self.cleanup()
                raise ValueError("A rádio demorou para responder. A estação anterior foi mantida, se estava tocando.")
            self.ready.wait(min(0.1, max(0, deadline - time.monotonic())))
        return self

    def read(self):
        if self.stopped.is_set():
            return b""
        if self.rebuffering and not self.finished.is_set():
            if self.packets.qsize() < self.prebuffer:
                return SILENCE
            self.rebuffering = False
        try:
            return self.packets.get_nowait()
        except queue.Empty:
            if self.finished.is_set():
                return b""
            self.rebuffering = True
            self.underruns += 1
            log.warning("Buffer esvaziou (%s). Aguardando %.1f segundos de áudio para retomar.", self.underruns, self.prebuffer / 50)
            return SILENCE

    def is_opus(self):
        return True

    def cleanup(self):
        if not self.stopped.is_set():
            self.stopped.set()
            self.source.cleanup()
            if threading.current_thread() is not self.worker:
                self.worker.join(timeout=1)


STREAM_OPTIONS = (
    "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_at_eof 1 "
    "-reconnect_on_network_error 1 -reconnect_on_http_error 429,5xx "
    "-reconnect_delay_max 5 -rw_timeout 15000000 -thread_queue_size 512"
    " -analyzeduration 1000000 -probesize 32768"
)


class TuneCancelled(Exception):
    """A pending station choice was superseded or stopped."""


class TuneRequests:
    """Only the latest selection may take over a guild's player."""
    def __init__(self):
        self.pending = {}

    def cancel(self, guild_id):
        previous = self.pending.pop(guild_id, None)
        if previous:
            previous.set()

    def begin(self, guild_id):
        self.cancel(guild_id)
        token = threading.Event()
        self.pending[guild_id] = token
        return token

    def active(self, guild_id, token):
        return self.pending.get(guild_id) is token and not token.is_set()

    def finish(self, guild_id, token):
        if self.pending.get(guild_id) is token:
            self.pending.pop(guild_id)


class SwitchableAudio(discord.AudioSource):
    """Keep one Discord audio sender alive across prepared source swaps."""
    def __init__(self, source):
        self._source = source
        self._lock = threading.Lock()

    def read(self):
        with self._lock:
            return self._source.read() if self._source else b""

    def swap(self, source):
        with self._lock:
            if self._source is None:
                raise ValueError("O player foi encerrado durante a troca. Selecione a estação novamente.")
            old = self._source
            self._source = source
            return old

    def is_opus(self):
        return True

    def cleanup(self):
        with self._lock:
            old, self._source = self._source, None
        if old:
            old.cleanup()


def create_source(url, executable, *, demo=False, cancel=None):
    if cancel is not None and cancel.is_set():
        raise TuneCancelled()
    source = discord.FFmpegOpusAudio(
        url, executable=executable,
        before_options="-nostdin -stream_loop -1" if demo else STREAM_OPTIONS,
        options="-vn -loglevel warning -flush_packets 1 -page_duration 20000",
    )
    return BufferedAudio(source, prebuffer=100).prime(cancel=cancel)


async def prepare_source(url, executable, *, demo=False, cancel):
    """Dispose of a prepared source even if the awaiting coroutine is cancelled."""
    worker = asyncio.create_task(asyncio.to_thread(create_source, url, executable, demo=demo, cancel=cancel))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancel.set()
        try:
            abandoned = await worker
        except (Exception, asyncio.CancelledError):
            pass
        else:
            await asyncio.to_thread(abandoned.cleanup)
        raise
