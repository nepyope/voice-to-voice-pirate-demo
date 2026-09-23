import asyncio
import base64
import io
import json
import struct
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from websockets.asyncio.server import serve

from launch_backend import build_command
from preflight import compose_command, driver_issues
from smoke_realtime import smoke
from smoke_tts import smoke_tts
from voice_files import remote_audio_uri, validate_voice, voice_directory

ROOT = Path(__file__).resolve().parents[1]


def wav_bytes(pcm=b"\x00\x01" * 2400):
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    return out.getvalue()


def test_default_speaker_is_original_and_does_not_load_painty_languages():
    env = {"VOICES_DIR": str(ROOT / "voices")}
    directory = voice_directory(env)
    voice = validate_voice(directory)
    assert directory.name == "captain"
    assert voice["sha256"] == "20af87e41ae12f6dabfbbd3756e7d3cb5a4ca05ecfe51de7692dd5f5ea3397cf"
    for mode in ("local", "remote"):
        command = build_command({**env, "TTS_MODE": mode}, voice, "Captain")
        assert not any("ref_voices_dir" in arg for arg in command)
        if mode == "remote":
            assert "file:///voices/captain/pirate_ref.wav" in command


def test_painty_loads_all_supplied_languages_in_both_modes():
    if not (ROOT / "voices/pirate_ref.wav").exists():
        pytest.skip("Optional private Painty assets are excluded from the public export")
    env = {"VOICE": "painty", "VOICES_DIR": str(ROOT / "voices")}
    voice = validate_voice(voice_directory(env))
    for mode, prefix in (("local", "omnivoice"), ("remote", "openai_tts")):
        command = build_command({**env, "TTS_MODE": mode}, voice, "Captain")
        assert f"--{prefix}_ref_voices_dir" in command


def test_custom_missing_and_unknown_presets_fail(tmp_path):
    with pytest.raises(ValueError):
        validate_voice(voice_directory({"VOICE": "custom", "VOICES_DIR": str(tmp_path)}))
    with pytest.raises(ValueError):
        voice_directory({"VOICE": "../captain"})


def test_remote_mount_mapping_encodes_paths_and_rejects_escape(tmp_path):
    env = {"VOICES_DIR": str(tmp_path), "TTS_VOICES_DIR": "/media/voices"}
    assert remote_audio_uri(tmp_path / "custom/my voice.wav", env) == "file:///media/voices/custom/my%20voice.wav"
    with pytest.raises(ValueError, match="inside"):
        remote_audio_uri(tmp_path.parent / "escape.wav", env)


def test_preflight_detects_cuda13_blocker_without_rejecting_local_mode():
    services = {"tts": {"image": "vllm/vllm-omni:v0.28.0"}}
    assert driver_issues("570.211", services)[0]
    assert not driver_issues("580.178", services)[0]
    assert not driver_issues("570.211", {})[0]
    assert not driver_issues("580.178", {"llm": {"image": "vllm/vllm-openai:v0.30.0-cu129"}})[0]


def test_combined_overlays_have_an_unambiguous_order():
    assert compose_command("vllm", reachy=True) == ["docker", "compose", "-f", "compose.yaml",
        "-f", "compose.vllm.yaml", "-f", "compose.llm-vllm.yaml", "-f", "compose.reachy.yaml"]


def test_direct_tts_request_and_wav_validation(tmp_path):
    directory = tmp_path / "captain"
    (directory / "langs").mkdir(parents=True)
    directory.joinpath("pirate_ref.wav").write_bytes(wav_bytes(b"\x00\x01" * 96000))
    directory.joinpath("pirate_ref.txt").write_text("Welcome aboard")
    directory.joinpath("langs/fr.wav").write_bytes(wav_bytes(b"\x00\x02" * 96000))
    directory.joinpath("langs/fr.txt").write_text("Bonjour capitaine")
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/v1/audio/speech"
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(wav_bytes())
        def log_message(self, *_):
            pass
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = smoke_tts(f"http://127.0.0.1:{server.server_port}/v1", "Bonjour", "fr-CA",
                tmp_path / "result.wav", {"VOICES_DIR": str(tmp_path)})
        finally:
            server.shutdown()
            thread.join(5)
    assert requests[0]["ref_audio"] == "file:///voices/captain/langs/fr.wav"
    assert requests[0]["ref_text"] == "Bonjour capitaine"
    assert requests[0]["language"] == "fr-CA"
    assert "stream" not in requests[0]
    assert result["seconds"] == 0.1
    assert json.loads((tmp_path / "result.json").read_text())["test"] == "direct_tts"


def test_audio_smoke_sends_pcm_and_waits_for_stt_and_vad(tmp_path):
    pcm = struct.pack("<h", 1000) * 2400
    source = tmp_path / "utterance.wav"
    source.write_bytes(wav_bytes(pcm))
    async def run():
        async def fixture(ws):
            await ws.send(json.dumps({"type": "session.created"}))
            config = json.loads(await ws.recv())["session"]
            assert config["audio"]["input"]["turn_detection"]["type"] == "server_vad"
            await ws.send(json.dumps({"type": "session.updated"}))
            received = bytearray()
            while len(received) < len(pcm) + 1920:
                message = json.loads(await ws.recv())
                assert message["type"] == "input_audio_buffer.append"
                received.extend(base64.b64decode(message["audio"]))
            assert received[:len(pcm)] == pcm
            assert not any(received[len(pcm):])
            await ws.send(json.dumps({"type": "input_audio_buffer.speech_stopped"}))
            await ws.send(json.dumps({"type": "conversation.item.input_audio_transcription.completed", "transcript": "Bonjour capitaine"}))
            await ws.send(json.dumps({"type": "response.output_audio.delta", "delta": base64.b64encode(pcm).decode()}))
            await ws.send(json.dumps({"type": "response.output_audio_transcript.delta", "delta": "Ahoy"}))
            await ws.send(json.dumps({"type": "response.output_audio_transcript.done", "transcript": "Ahoy!"}))
            await ws.send(json.dumps({"type": "response.done", "response": {"status": "completed"}}))
        async with serve(fixture, "127.0.0.1", 0) as server:
            result = await smoke(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}", None,
                                 tmp_path / "reply.wav", 5, input_audio=source)
            assert result["stt_exercised"]
            assert result["input_transcript"] == "Bonjour capitaine"
            assert result["transcript"] == "Ahoy!"
            assert result["speech_stopped_to_first_audio_seconds"] >= 0
    asyncio.run(run())


@pytest.mark.parametrize("termination", ["cancelled", "failed", "incomplete", "disconnect", "silence"])
def test_smoke_does_not_report_partial_or_silent_audio_as_success(tmp_path, termination):
    output = tmp_path / "failed.wav"
    async def run():
        async def fixture(ws):
            await ws.send(json.dumps({"type": "session.created"}))
            await ws.recv()
            await ws.send(json.dumps({"type": "session.updated"}))
            await ws.recv()
            await ws.recv()
            pcm = bytes(4800) if termination == "silence" else b"\x00\x01" * 2400
            await ws.send(json.dumps({"type": "response.output_audio.delta", "delta": base64.b64encode(pcm).decode()}))
            if termination != "disconnect":
                await ws.send(json.dumps({"type": "response.done", "response": {
                    "status": "completed" if termination == "silence" else termination}}))
        async with serve(fixture, "127.0.0.1", 0) as server:
            with pytest.raises((RuntimeError, ValueError)):
                await smoke(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}", "Hello", output, 5)
    asyncio.run(run())
    assert not output.exists()
