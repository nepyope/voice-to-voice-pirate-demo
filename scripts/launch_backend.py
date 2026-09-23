"""Construct the pinned CLI using argument arrays, never shell interpolation."""
import argparse
import json
import os
import shlex
from pathlib import Path

from voice_files import validate_language_voices, validate_voice, voice_directory

ROOT = Path(__file__).resolve().parents[1]


def build_command(env, voice, instructions):
    pipelines = int(env.get("NUM_PIPELINES", "1"))
    if pipelines < 1:
        raise ValueError("NUM_PIPELINES must be at least 1")
    langs_dir = Path(voice["audio"]).parent / "langs"
    languages = validate_language_voices(langs_dir) if langs_dir.exists() else {}
    command = ["speech-to-speech", "serve", "--host", "0.0.0.0", "--port", "8765",
        "--stt", "parakeet-tdt",  # Unset fixed language enables autodetection with a valid fallback.
        "--parakeet_tdt_model_name", "nvidia/parakeet-tdt-0.6b-v3",
        "--parakeet_tdt_device", "cuda", "--enable_live_transcription", "true",
        "--enable_lang_prompt", "true", "--stream_batch_sentences", "1",
        "--init_chat_prompt", instructions, "--num_pipelines", str(pipelines)]
    if not env.get("LLM_BASE_URL", "").strip() or not env.get("LLM_MODEL", "").strip():
        raise ValueError("Set LLM_BASE_URL and LLM_MODEL to the vLLM server")
    command += ["--llm_backend", "chat-completions", "--responses_api_base_url", env["LLM_BASE_URL"],
                "--model_name", env["LLM_MODEL"]]
    # The API key stays in OPENAI_API_KEY, not in command logs.
    command += ["--tts", "omnivoice", "--omnivoice_model_name", env.get("TTS_MODEL", "k2-fsa/OmniVoice"),
                "--omnivoice_device", "cuda", "--omnivoice_dtype", "float16",
                "--omnivoice_ref_audio", voice["audio"], "--omnivoice_ref_text", voice["text"],
                "--omnivoice_num_steps", "32"]
    # Optional per-language references (voices/langs/<lang>.wav + .txt): the clip matching the
    # detected utterance language is cloned; anything else falls back to the default reference.
    if languages:
        command += ["--omnivoice_ref_voices_dir", str(langs_dir)]
    return command


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args()
    voice = validate_voice(voice_directory(os.environ))
    instructions = json.loads((ROOT / "hf-realtime-voice/pirate.json").read_text())["instructions"]
    command = build_command(os.environ, voice, instructions)
    if options.dry_run:
        print(shlex.join(command))
    else:
        languages = sorted(validate_language_voices(Path(voice["audio"]).parent / "langs")) \
            if (Path(voice["audio"]).parent / "langs").is_dir() else []
        print(f"Starting with reference {voice['sha256']}; "
              f"per-language voices: {', '.join(languages) or 'none'}", flush=True)
        os.execvp(command[0], command)
