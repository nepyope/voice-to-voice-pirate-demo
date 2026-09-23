"""Send a real cloning request to vLLM-Omni and validate its non-streaming WAV."""
import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from audio_checks import read_pcm_wav
from voice_files import (reference_for_language, remote_audio_uri, validate_language_voices,
                         validate_voice, voice_directory)


def smoke_tts(base_url, text, language, output, env, timeout=180):
    directory = voice_directory(env)
    default = validate_voice(directory)
    langs = directory / "langs"
    references = validate_language_voices(langs) if langs.exists() else {}
    reference = reference_for_language(default, references, language)
    payload = {"model": env.get("TTS_MODEL", "k2-fsa/OmniVoice"), "input": text,
               "voice": "default", "response_format": "wav",
               "ref_audio": remote_audio_uri(Path(reference["audio"]), env),
               "ref_text": reference["text"]}
    if language and language != "auto":
        payload["language"] = language
    request = urllib.request.Request(base_url.rstrip("/") + "/audio/speech",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json",
        "Authorization": "Bearer " + env.get("TTS_API_KEY", "local-demo")})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            audio = response.read(16 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"TTS returned HTTP {exc.code}; inspect the TTS service logs") from None
    elapsed = time.monotonic() - started
    if len(audio) > 16 * 1024 * 1024:
        raise ValueError("TTS response exceeds 16 MiB")
    _, stats = read_pcm_wav(audio)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(audio)
    result = {"test": "direct_tts", "output": str(output), "completed_at_utc": datetime.now(timezone.utc).isoformat(),
              "language": language, "reference": payload["ref_audio"],
              "reference_sha256": reference["sha256"], "elapsed_seconds": round(elapsed, 3), **stats,
              "quality_review": "Listen to the saved WAV; audio validity does not establish clone quality."}
    output.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("TTS_BASE_URL", "http://tts:8091/v1"))
    parser.add_argument("--text", default="Bonjour, moussaillon ! Partons chercher un trésor.")
    parser.add_argument("--language", default="fr")
    parser.add_argument("--output", type=Path, default=Path("artifacts/tts-fr.wav"))
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    smoke_tts(args.base_url, args.text, args.language, args.output, os.environ, args.timeout)
