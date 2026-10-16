"""Validated, administrator-controlled station catalogue."""
import json
from dataclasses import dataclass
from pathlib import Path
import unicodedata
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    category: str
    url: str
    website: str
    kind: str = "stream"
    radio_browser_uuid: str = ""


def load_stations(path: Path) -> dict[str, Station]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    stations = {}
    seen = set()
    for entry in entries:
        identifier = entry["id"]
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 100 or identifier in seen:
            raise ValueError("Cada estação precisa de um id único de 1 a 100 caracteres.")
        seen.add(identifier)
        if not entry.get("enabled", False):
            continue
        station = Station(**{key: entry[key] for key in Station.__dataclass_fields__ if key in entry})
        if station.kind not in {"stream", "demo"}:
            raise ValueError(f"Tipo de estação inválido: {identifier}")
        if station.kind == "stream" and (urlsplit(station.url).scheme not in {"http", "https"} or not urlsplit(station.url).hostname):
            raise ValueError(f"URL HTTP(S) inválida: {identifier}")
        if not station.name or len(station.name) > 100 or len(station.category) > 100:
            raise ValueError(f"Nome/categoria inválidos: {identifier}")
        stations[identifier] = station
    if len(stations) > 25:
        raise ValueError("O menu suporta até 25 estações ativas.")
    def alphabetical(item):
        return "".join(char for char in unicodedata.normalize("NFKD", item[1].name).casefold()
                       if not unicodedata.combining(char))
    return dict(sorted(stations.items(), key=alphabetical))
