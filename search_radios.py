"""List Radio Browser candidates for manual verification of station identity."""
import concurrent.futures
import json
from pathlib import Path
from radio_browser import search

QUERIES = [("Groove Salad", "US"), ("Radio Swiss Jazz", "CH"), ("89", "BR"),
           ("RMF FM", "PL"), ("357", "PL"), ("Radio Record", "RU"), ("CBN", "BR")]


def query(item):
    name, country = item
    try:
        return name, search(name, country)
    except ConnectionError:
        return name, []


if __name__ == "__main__":
    cache = Path("radio_browser_candidates.json")
    results = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    pending = [q for q in QUERIES if not results.get(q[0])]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results.update(dict(pool.map(query, pending)))
    Path("radio_browser_candidates.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for query_name, entries in results.items():
        print("\n" + query_name)
        for entry in entries[:8]:
            print(json.dumps({key: entry.get(key) for key in ["name", "stationuuid", "url_resolved", "homepage", "codec", "bitrate", "lastcheckok"]}, ensure_ascii=False))
