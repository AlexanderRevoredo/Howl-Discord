"""Local demonstration audio and portable FFmpeg discovery."""
import math
from pathlib import Path
import shutil
import struct
import wave


def find_ffmpeg(configured: str) -> str:
    found = shutil.which(configured)
    if found:
        return found
    if configured != "ffmpeg":
        raise ValueError("FFMPEG_PATH aponta para um executável inexistente.")
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as error:
        raise ValueError("FFmpeg não encontrado. Instale as dependências de requirements.txt.") from error


def ensure_demo(path: Path) -> Path:
    """Generate an original quiet arpeggio, with fades to prevent clicks."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 48000
    notes = (261.63, 329.63, 392.0, 523.25, 392.0, 329.63, 293.66, 392.0)
    frames = bytearray()
    for frequency in notes:
        for index in range(rate // 2):
            t = index / rate
            envelope = min(1.0, t / 0.02, (0.5 - t) / 0.06)
            sample = int(5000 * envelope * math.sin(2 * math.pi * frequency * t))
            frames.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(frames)
    return path
