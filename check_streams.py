"""Manual diagnostic: decode a short sample without connecting to Discord."""
import concurrent.futures
import argparse
from pathlib import Path
import time
from audio import find_ffmpeg
from catalog import load_stations
from playback import create_source


def check(station, seconds=2, realtime=False):
    source = None
    try:
        source = create_source(station.url, find_ffmpeg("ffmpeg"))
        deadline = time.monotonic()
        for _ in range(int(seconds * 50)):
            if not source.read():
                raise ValueError("O stream terminou durante o teste.")
            if realtime:
                deadline += 0.02
                time.sleep(max(0, deadline - time.monotonic()))
        return station.name, "OK", f"buffer esvaziou {source.underruns} vez(es)"
    except Exception as error:
        return station.name, "FALHA", str(error)
    finally:
        if source:
            source.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--station", help="ID de uma estação, por exemplo cbn")
    parser.add_argument("--seconds", type=int, default=2)
    parser.add_argument("--realtime", action="store_true")
    args = parser.parse_args()
    stations = [s for s in load_stations(Path(__file__).with_name("stations.json")).values()
                if s.kind == "stream" and (not args.station or s.id == args.station)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(check, s, args.seconds, args.realtime) for s in stations]
        for future in concurrent.futures.as_completed(futures):
            print(future.result(), flush=True)
