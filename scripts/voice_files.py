"""Small, dependency-free checks shared by preparation and launch."""
import hashlib
import re
import wave
from pathlib import Path


def voice_directory(env) -> Path:
    return Path(env.get("VOICES_DIR", "/voices"))


def language_key(language: str) -> str:
    code = language.strip().lower().replace("_", "-")
    if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", code):
        raise ValueError(f"Invalid reference language code: {language!r}")
    return code


def validate_voice(directory: Path) -> dict:
    return _validate_pair(directory / "pirate_ref.wav", directory / "pirate_ref.txt",
                          "Provide both voices/pirate_ref.wav and voices/pirate_ref.txt")


def validate_language_voices(directory: Path) -> dict:
    """Validate voices/langs/<lang>.wav + <lang>.txt pairs; returns {lang: details}."""
    voices = {}
    if not directory.is_dir():
        raise ValueError(f"Language reference directory does not exist: {directory}")
    for audio in sorted(directory.glob("*.wav")):
        transcript = audio.with_suffix(".txt")
        code = language_key(audio.stem)
        if code in voices:
            raise ValueError(f"Duplicate reference language code: {code}")
        voices[code] = _validate_pair(
            audio, transcript, f"{audio.name} needs a matching transcript {transcript.name}")
    for transcript in directory.glob("*.txt"):
        if not transcript.with_suffix(".wav").is_file():
            raise ValueError(f"{transcript.name} needs a matching WAV")
    return voices


def _validate_pair(audio: Path, transcript: Path, missing_message: str) -> dict:
    if not audio.is_file() or not transcript.is_file():
        raise ValueError(missing_message)
    text = transcript.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"{transcript.name}: reference transcript is empty")
    with wave.open(str(audio), "rb") as wav:
        seconds = wav.getnframes() / wav.getframerate()
        if wav.getnchannels() != 1 or wav.getframerate() != 24000 or wav.getsampwidth() != 2:
            raise ValueError(f"{audio.name}: reference WAV must be mono, 24 kHz, PCM 16-bit")
        # OmniVoice recommends 3–10 s; up to 20 s is accepted for spliced multi-line
        # references (longer clips slow cloning and may degrade quality).
        if not 3 <= seconds <= 20:
            raise ValueError(f"{audio.name}: reference duration is {seconds:.2f}s; use 3–20 seconds")
        frames = wav.readframes(wav.getnframes())
        if len(frames) != wav.getnframes() * 2:
            raise ValueError(f"{audio.name}: reference WAV is truncated")
        if not any(frames):
            raise ValueError(f"{audio.name}: reference WAV is silent")
    return {"audio": str(audio), "text": text, "seconds": round(seconds, 3),
            "sha256": hashlib.sha256(audio.read_bytes()).hexdigest()}
