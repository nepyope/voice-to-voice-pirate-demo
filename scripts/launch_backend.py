"""Construct the pinned CLI using argument arrays, never shell interpolation."""
import argparse
import json
import os
import shlex
from pathlib import Path

from voice_files import remote_audio_uri, validate_language_voices, validate_voice, voice_directory

ROOT = Path(__file__).resolve().parents[1]


def build_command(env, voice, instructions):
    mode = env.get("TTS_MODE", "local")
    if mode not in {"local", "remote"}:
        raise ValueError("TTS_MODE must be local or remote")
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
    if env.get("LLM_BASE_URL", "").strip():
        if not env.get("LLM_MODEL", "").strip():
            raise ValueError("Set LLM_MODEL explicitly when using LLM_BASE_URL")
        command += ["--llm_backend", "chat-completions", "--responses_api_base_url", env["LLM_BASE_URL"],
                    "--model_name", env["LLM_MODEL"]]
        # The provider key stays in OPENAI_API_KEY, not in command logs.
    else:
        command += ["--llm_backend", "transformers", "--model_name",
                    env.get("LLM_MODEL") or "Qwen/Qwen3-4B-Instruct-2507",
                    "--llm_device", "cuda", "--llm_torch_dtype", "float16",
                    "--llm_gen_max_new_tokens", "160"]
    model = env.get("TTS_MODEL", "k2-fsa/OmniVoice")
    if mode == "local":
        command += ["--tts", "omnivoice", "--omnivoice_model_name", model,
                    "--omnivoice_device", "cuda", "--omnivoice_dtype", "float16",
                    "--omnivoice_ref_audio", voice["audio"], "--omnivoice_ref_text", voice["text"],
                    "--omnivoice_num_steps", "32"]
        # Optional per-language references (voices/langs/<lang>.wav + .txt): the clip matching the
        # detected utterance language is cloned; anything else falls back to the default reference.
        if languages:
            command += ["--omnivoice_ref_voices_dir", str(langs_dir)]
    else:
        command += ["--tts", "openai", "--openai_tts_base_url", env.get("TTS_BASE_URL", "http://tts:8091/v1"),
                    "--openai_tts_model", model, "--openai_tts_voice", "default",
                    "--openai_tts_response_format", "wav", "--openai_tts_stream", "false",
                    "--openai_tts_ref_audio", remote_audio_uri(Path(voice["audio"]), env),
                    "--openai_tts_ref_text", voice["text"], "--openai_tts_api_key", "local-demo"]
        if languages:
            command += ["--openai_tts_ref_voices_dir", str(langs_dir),
                        "--openai_tts_ref_voices_base_url", remote_audio_uri(langs_dir, env)]
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
        print(f"Starting {os.environ.get('TTS_MODE', 'local')} TTS; "
              f"reference {voice['sha256']}; "
              f"per-language voices: {', '.join(languages) or 'none'}", flush=True)
        os.execvp(command[0], command)
