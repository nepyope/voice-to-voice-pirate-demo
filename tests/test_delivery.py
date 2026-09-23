from pathlib import Path

import pytest

from launch_backend import build_command
from voice_files import validate_language_voices, validate_voice, voice_directory

ROOT = Path(__file__).resolve().parents[1]


def test_painty_loads_all_language_references():
    env = {"VOICES_DIR": str(ROOT / "voices")}
    voice = validate_voice(voice_directory(env))
    assert len(validate_language_voices(ROOT / "voices/langs")) == 29
    command = build_command({**env, "LLM_BASE_URL": "http://llm:8000/v1", "LLM_MODEL": "m"}, voice, "Painty")
    assert "--omnivoice_ref_voices_dir" in command


def test_missing_reference_fails(tmp_path):
    with pytest.raises(ValueError):
        validate_voice(voice_directory({"VOICES_DIR": str(tmp_path)}))
