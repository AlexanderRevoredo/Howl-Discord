"""Radio Browser lookup with timeouts and mirror failover."""
import json
import logging
import asyncio
import time
import aiohttp
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

log = logging.getLogger("howl.radio_browser")


def mirrors():
    # Avoid reverse-DNS lookups here: some networks leave them pending for minutes.
    return ["de1.api.radio-browser.info", "nl1.api.radio-browser.info"]


def request_json(endpoint):
    for host in mirrors()[:3]:
        try:
            request = Request(f"https://{host}/json/{endpoint}", headers={"User-Agent": "Howl-Discord/0.1"})
            with urlopen(request, timeout=6) as response:
                return json.load(response)
        except (OSError, ValueError) as error:
            log.warning("Radio Browser indisponível no espelho %s: %s", host, type(error).__name__)
    raise ConnectionError("Não consegui consultar o Radio Browser.")


def search(name, country):
    query = urlencode({"hidebroken": "true", "order": "votes", "reverse": "true", "limit": 50})
    return [s for s in request_json(f"stations/byname/{quote(name, safe='')}?{query}")
            if s.get("countrycode") == country][:12]


def resolve(station):
    """Refresh by stable UUID; keep the last tested URL when the API is down."""
    if station.radio_browser_uuid:
        try:
            entries = request_json(f"stations/byuuid/{quote(station.radio_browser_uuid, safe='')}")
            if entries and entries[0].get("lastcheckok") == 1:
                url = entries[0].get("url_resolved") or entries[0].get("url") or ""
                if urlsplit(url).scheme in {"http", "https"} and urlsplit(url).hostname:
                    return url
        except ConnectionError:
            log.warning("Usando último stream salvo para %s", station.name)
    return station.url


class StreamResolver:
    """Refresh URLs in the background; choosing a station never waits for the API."""
    def __init__(self):
        self.cache = {}
        self.tasks = {}
        self.limit = asyncio.Semaphore(3)

    def url_for(self, station):
        cached = self.cache.get(station.id)
        if station.radio_browser_uuid and (not cached or cached[1] < time.monotonic()):
            self._start(station)
        return cached[0] if cached else station.url

    def warm(self, stations):
        for station in stations:
            self.url_for(station)

    def _start(self, station):
        task = self.tasks.get(station.id)
        if task is None:
            task = asyncio.create_task(self._fetch(station))
            self.tasks[station.id] = task
            task.add_done_callback(lambda done: self.tasks.pop(station.id, None))
        return task

    async def refresh(self, station):
        if not station.radio_browser_uuid:
            return station.url
        return await asyncio.shield(self._start(station))

    async def _fetch(self, station):
        previous = self.cache.get(station.id, (station.url, 0))[0]
        async with self.limit:
            timeout = aiohttp.ClientTimeout(total=2.5)
            try:
                async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "Howl-Discord/0.1"}) as session:
                    url = f"https://de1.api.radio-browser.info/json/stations/byuuid/{quote(station.radio_browser_uuid, safe='')}"
                    async with session.get(url) as response:
                        response.raise_for_status()
                        entries = await response.json()
                if entries and entries[0].get("lastcheckok") == 1:
                    url = entries[0].get("url_resolved") or entries[0].get("url") or ""
                    if urlsplit(url).scheme in {"http", "https"} and urlsplit(url).hostname:
                        self.cache[station.id] = (url, time.monotonic() + 1800)
                        return url
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError, TypeError):
                log.info("Mantendo endereço salvo de %s; atualização indisponível.", station.name)
        self.cache[station.id] = (previous, time.monotonic() + 60)
        return previous

    async def close(self):
        pending = list(self.tasks.values())
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
