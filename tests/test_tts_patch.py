"""Exercise patched methods from exact upstream source, without model weights.

Only the heavyweight module imports/base class are omitted. The handler method
bodies under test are compiled unchanged after applying the shipped git patch.
"""
import ast
import logging
import os
import shutil
import subprocess
from pathlib import Path
from threading import Event, Lock
from time import perf_counter
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def handler(tmp_path):
    package = tmp_path / "src/speech_to_speech"
    shutil.copytree(ROOT / "tests/fixtures/upstream", package)
    subprocess.run(["git", "apply", str(ROOT / "patches/remote-voice.patch")], cwd=tmp_path, check=True)
    tree = ast.parse((package / "TTS/openai_compatible_handler.py").read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OpenAICompatibleTTSHandler")
    cls.bases = []
    module = ast.Module(body=[ast.parse("from __future__ import annotations").body[0], cls], type_ignores=[])
    namespace = dict(os=os, Lock=Lock, perf_counter=perf_counter, logger=logging.getLogger("test"),
                     EndOfResponse=type("EndOfResponse", (), {}))
    exec(compile(ast.fix_missing_locations(module), "patched_handler", "exec"), namespace)
    Handler = namespace["OpenAICompatibleTTSHandler"]
    obj = Handler()
    obj.warmup = lambda: None
    obj.setup(Event(), ref_audio="file:///voices/pirate_ref.wav", ref_text="Welcome aboard", response_format="wav")
    return obj, namespace


@pytest.mark.parametrize("language", ["fr", "de", "es", "it", "pl"])
def test_clone_payload_keeps_voice_and_forwards_turn_language(handler, language):
    obj, _ = handler
    payload = obj._request_payload(text="Test", voice="default", language=language)
    assert payload["language"] == language
    assert payload["ref_audio"] == "file:///voices/pirate_ref.wav"
    assert payload["ref_text"] == "Welcome aboard"
    assert payload["response_format"] == "wav"
    assert "stream" not in payload


def test_fixed_language_override_and_auto_omission(handler):
    obj, _ = handler
    obj.language = "en"
    assert obj._request_payload(text="x", voice="default", language="fr")["language"] == "en"
    obj.language = None
    assert "language" not in obj._request_payload(text="x", voice="default", language="auto")


@pytest.mark.parametrize("audio,text", [("file:///ref.wav", None), (None, "hello"), ("file:///ref.wav", "  ")])
def test_clone_arguments_must_be_a_pair(handler, audio, text):
    obj, _ = handler
    with pytest.raises(ValueError, match="together"):
        obj.setup(Event(), ref_audio=audio, ref_text=text)


def test_process_actually_delivers_detected_language_to_request(handler):
    obj, namespace = handler
    requests = []
    def operation(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(iter_bytes=lambda _: iter([b"test-audio"]))
    namespace["HttpSpeechOperation"] = operation
    obj.stop_event = Event()
    obj._decode_wav_stream = lambda chunks: iter(chunks)
    obj._log_first_audio_latency = lambda *_: None
    turn = SimpleNamespace(text="Bonjour", language_code="fr", runtime_config=None, response=None,
                           cancel_generation=None, response_key=None, turn_id=None, turn_revision=None)
    assert list(obj.process(turn)) == [b"test-audio"]
    assert requests[0]["payload"]["language"] == "fr"
    assert requests[0]["payload"]["ref_audio"].endswith("pirate_ref.wav")


def reference(directory, name, text="Une référence française"):
    directory.mkdir(exist_ok=True)
    (directory / (name + ".wav")).write_bytes(b"fixture; audio shape is validated by voice_files")
    (directory / (name + ".txt")).write_text(text, encoding="utf-8")


@pytest.mark.parametrize("language,expected", [("FR_ca", "fr"), ("es-419", "es-419"),
    ("es-MX", "es"), ("pl", "default"), (None, "default"), ("../../fr", "default")])
def test_language_reference_exact_base_and_fallback(handler, tmp_path, language, expected):
    obj, _ = handler
    for code in ("fr", "es", "es-419"):
        reference(tmp_path, code, "Transcript " + code)
    obj.setup(Event(), ref_audio="file:///voices/default.wav", ref_text="Fallback",
              ref_voices_dir=str(tmp_path), ref_voices_base_url="file:///mounted/voices/langs")
    payload = obj._request_payload(text="x", voice="default", language=language)
    assert payload["ref_audio"].endswith("/" + expected + ".wav")
    assert payload["ref_text"] == ("Fallback" if expected == "default" else "Transcript " + expected)
    # A turn-specific reference never mutates the configured fallback or other turns.
    assert obj._request_payload(text="x", voice="default")["ref_audio"] == "file:///voices/default.wav"


def test_fixed_language_selects_matching_reference(handler, tmp_path):
    obj, _ = handler
    reference(tmp_path, "fr")
    obj.setup(Event(), language="fr", ref_voices_dir=str(tmp_path))
    payload = obj._request_payload(text="x", voice="default", language="en")
    assert payload["ref_audio"] == (tmp_path / "fr.wav").as_uri()
    assert payload["language"] == "fr"


@pytest.mark.parametrize("problem", ["missing", "blank", "duplicate", "invalid_code", "orphan_text"])
def test_bad_reference_directories_fail_at_startup(handler, tmp_path, problem):
    obj, _ = handler
    reference(tmp_path, "fr")
    if problem == "missing":
        (tmp_path / "fr.txt").unlink()
    elif problem == "blank":
        (tmp_path / "fr.txt").write_text(" ")
    elif problem == "duplicate":
        reference(tmp_path, "FR")
    elif problem == "invalid_code":
        reference(tmp_path, "bad name")
    else:
        (tmp_path / "en.txt").write_text("Orphan")
    with pytest.raises(ValueError):
        obj.setup(Event(), ref_voices_dir=str(tmp_path))


def test_language_reference_used_by_real_process_path(handler, tmp_path):
    obj, namespace = handler
    reference(tmp_path, "fr", "Bonjour capitaine")
    obj.setup(Event(), ref_audio="file:///voices/default.wav", ref_text="Fallback",
              ref_voices_dir=str(tmp_path), response_format="wav")
    requests = []
    def operation(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(iter_bytes=lambda _: iter([b"test-audio"]))
    namespace["HttpSpeechOperation"] = operation
    obj.stop_event = Event()
    obj._decode_wav_stream = lambda chunks: iter(chunks)
    obj._log_first_audio_latency = lambda *_: None
    turn = SimpleNamespace(text="Bonjour", language_code="fr-CA", runtime_config=None, response=None,
                           cancel_generation=None, response_key=None, turn_id=None, turn_revision=None)
    assert list(obj.process(turn)) == [b"test-audio"]
    assert requests[0]["payload"]["ref_text"] == "Bonjour capitaine"
    assert requests[0]["payload"]["ref_audio"] == (tmp_path / "fr.wav").as_uri()


def test_configured_clone_takes_precedence_over_reachy_preset(handler):
    obj, _ = handler
    obj.setup(Event(), voice="default", ref_audio="file:///voices/captain/pirate_ref.wav", ref_text="Ahoy")
    runtime = SimpleNamespace(session=SimpleNamespace(audio=SimpleNamespace(output=SimpleNamespace(voice="Aiden"))))
    assert obj._resolve_voice(runtime, None) == "default"
    obj.setup(Event(), voice="default")  # Preserve upstream behavior when cloning is not configured.
    assert obj._resolve_voice(runtime, None) == "Aiden"
