"""Dependency-free audio checks for deployment evidence, not voice-quality scoring."""
import io
import math
import struct
import wave
from pathlib import Path


def pcm_stats(pcm: bytes) -> dict:
    if not pcm or len(pcm) % 2:
        raise ValueError("Expected non-empty, aligned PCM16 audio")
    samples = [s[0] for s in struct.iter_unpack("<h", pcm)]
    peak = max(abs(s) for s in samples)
    if peak == 0:
        raise ValueError("Received silent audio")
    return {"seconds": len(samples) / 24000,
            "peak": round(peak / 32768, 6),
            "rms": round(math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768, 6)}


def read_pcm_wav(source: Path | bytes, max_seconds: float = 300) -> tuple[bytes, dict]:
    stream = io.BytesIO(source) if isinstance(source, bytes) else str(source)
    with wave.open(stream, "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 24000, "NONE"):
            raise ValueError("WAV must be mono, 24 kHz, uncompressed PCM16")
        frames = wav.getnframes()
        if frames > max_seconds * 24000:
            raise ValueError(f"Audio exceeds {max_seconds:g} seconds")
        pcm = wav.readframes(frames)
        if len(pcm) != frames * 2:
            raise ValueError("Truncated WAV audio")
    return pcm, pcm_stats(pcm)


def write_pcm_wav(output: Path, pcm: bytes) -> dict:
    stats = pcm_stats(pcm)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(pcm)
    return stats
