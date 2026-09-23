import asyncio
import json
import shutil
import struct
import threading
import wave
from pathlib import Path

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from websockets.asyncio.server import serve

import server
from launch_backend import build_command
from realtime_proxy import relay
from voice_files import validate_voice

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def voice(tmp_path):
    with wave.open(str(tmp_path / "pirate_ref.wav"), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(struct.pack("<h", 1000) * 96000)
    (tmp_path / "pirate_ref.txt").write_text("Welcome aboard, matey!", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("problem", ["missing_text", "empty_text", "stereo", "wrong_rate", "too_short", "silent"])
def test_invalid_reference_fails_before_model_start(voice, problem):
    if problem == "missing_text":
        (voice / "pirate_ref.txt").unlink()
    elif problem == "empty_text":
        (voice / "pirate_ref.txt").write_text("   ")
    else:
        with wave.open(str(voice / "pirate_ref.wav"), "wb") as wav:
            wav.setnchannels(2 if problem == "stereo" else 1)
            wav.setsampwidth(2)
            wav.setframerate(16000 if problem == "wrong_rate" else 24000)
            wav.writeframes(struct.pack("<h", 0 if problem == "silent" else 1000) * (12000 if problem == "too_short" else 96000))
    with pytest.raises(ValueError):
        validate_voice(voice)


def test_launch_preserves_language_and_clone_contract(voice):
    command = build_command({"VOICES_DIR": str(voice)}, validate_voice(voice), "Pirate instructions")
    args = dict(zip(command[2::2], command[3::2]))
    assert args["--host"] == "0.0.0.0"
    assert "--parakeet_tdt_language" not in args  # None = auto; literal auto leaks into short-turn fallback.
    assert "--language" not in args  # This legacy flag is ignored for current Parakeet.
    assert args["--enable_lang_prompt"] == "true"
    assert args["--init_chat_prompt"] == "Pirate instructions"
    assert args["--stream_batch_sentences"] == "1"
    assert args["--omnivoice_ref_text"] == "Welcome aboard, matey!"
    assert "--omnivoice_language" not in args


def test_per_language_voices_are_passed_only_when_present_and_valid(voice):
    command = build_command({}, validate_voice(voice), "Painty")
    assert "--omnivoice_ref_voices_dir" not in command  # no voices/langs directory
    langs = voice / "langs"
    langs.mkdir()
    shutil.copy(voice / "pirate_ref.wav", langs / "fr.wav")
    (langs / "fr.txt").write_text("Prêts les enfants ?", encoding="utf-8")
    command = build_command({}, validate_voice(voice), "Painty")
    args = dict(zip(command[2::2], command[3::2]))
    assert args["--omnivoice_ref_voices_dir"] == str(langs)
    assert args["--omnivoice_ref_audio"] == str(voice / "pirate_ref.wav")  # default stays as fallback
    (langs / "fr.txt").unlink()  # a clip without its transcript must fail loudly, not be skipped
    with pytest.raises(ValueError, match="fr.wav"):
        build_command({}, validate_voice(voice), "Painty")


def test_remote_llm_requires_model_and_keeps_key_out_of_argv(voice):
    details = validate_voice(voice)
    with pytest.raises(ValueError):
        build_command({"LLM_BASE_URL": "https://example.com/v1"}, details, "Painty")
    command = build_command({"LLM_BASE_URL": "https://example.com/v1", "LLM_MODEL": "test-model",
                             "OPENAI_API_KEY": "test-secret"}, details, "Painty")
    assert "chat-completions" in command
    assert "test-secret" not in command


def test_config_and_static_assets(monkeypatch):
    monkeypatch.setattr(server, "SPEECH_TO_SPEECH_URL", "ws://private-container:8765/v1/realtime")
    with TestClient(server.app) as client:
        config = client.get("/api/config").json()
        assert config["s2sUrl"] == "/api/realtime"
        assert config["voice"] == "default"
        assert "latest spoken message" in config["instructions"]
        assert not config["rtc"]
        assert config["startupGreeting"] == ""
        assert "private-container" not in json.dumps(config)
        assert client.get("/").status_code == 200
        assert client.get("/worklets/mic-capture.js").status_code == 200
        for path in ["/server.py", "/.env", "/package-lock.json", "/ui/../server.py"]:
            assert client.get(path).status_code == 404


def test_readiness_tracks_backend(monkeypatch):
    async def ready(_):
        return True
    async def down(_):
        return False
    with TestClient(server.app) as client:
        monkeypatch.setattr(server, "backend_ready", ready)
        response = client.get("/api/health")
        # SDK is installed by npm ci; health must include it in readiness.
        assert response.json()["backend"] is True
        assert response.status_code == (200 if response.json()["sdk"] else 503)
        monkeypatch.setattr(server, "backend_ready", down)
        assert client.get("/api/health").status_code == 503


@pytest.fixture
def upstream():
    started = threading.Event()
    disconnected = threading.Event()
    state = {}
    async def echo(ws):
        await ws.send(json.dumps({"type": "session.created", "session": {"id": "fixture"}}))
        try:
            async for message in ws:
                await ws.send(message)
        finally:
            disconnected.set()
    async def run():
        async with serve(echo, "127.0.0.1", 0) as ws_server:
            state.update(loop=asyncio.get_running_loop(), stop=asyncio.Event(),
                         port=ws_server.sockets[0].getsockname()[1])
            started.set()
            await state["stop"].wait()
    thread = threading.Thread(target=lambda: asyncio.run(run()), daemon=True)
    thread.start()
    assert started.wait(5)
    yield state["port"], disconnected
    state["loop"].call_soon_threadsafe(state["stop"].set)
    thread.join(5)
    assert not thread.is_alive()


def relay_app(target):
    app = FastAPI()
    @app.websocket("/api/realtime")
    async def ws(websocket: WebSocket):
        await relay(websocket, target)
    return app


def test_websocket_relays_json_binary_and_releases_session(upstream):
    port, disconnected = upstream
    with TestClient(relay_app(f"ws://127.0.0.1:{port}/v1/realtime")) as client:
        with client.websocket_connect("/api/realtime", headers={"origin": "http://testserver"}) as ws:
            assert ws.receive_json()["type"] == "session.created"
            for event in [
                {"type": "session.update", "session": {"instructions": "Painty", "audio": {"output": {"voice": "default"}}}},
                {"type": "input_audio_buffer.append", "audio": "AACAAA=="},
                {"type": "response.cancel"},
            ]:
                ws.send_json(event)
                assert ws.receive_json() == event
            ws.send_bytes(b"\x00\x00\xff\x7f")
            assert ws.receive_bytes() == b"\x00\x00\xff\x7f"
        assert disconnected.wait(5)


def test_backend_failure_is_actionable_and_sanitized():
    with TestClient(relay_app("ws://127.0.0.1:1/v1/realtime?secret=do-not-leak")) as client:
        with client.websocket_connect("/api/realtime") as ws:
            result = ws.receive_json()
            assert result["error"]["code"] == "backend_unavailable"
            assert "do-not-leak" not in json.dumps(result)


def test_cross_origin_connection_rejected():
    from starlette.websockets import WebSocketDisconnect
    with TestClient(relay_app("ws://unused:8765")) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect("/api/realtime", headers={"origin": "https://another-origin.example"}):
                pass
        assert error.value.code == 1008


@pytest.mark.parametrize("remote_llm", [False, True])
def test_launch_flags_belong_to_selected_pinned_backends(voice, remote_llm):
    inventory = json.loads((ROOT / "tests/fixtures/cli-argument-names.json").read_text())["arguments"]
    groups = ["module_arguments", "realtime_server_arguments", "language_model_base_arguments", "parakeet_tdt_arguments",
              "omnivoice_tts_arguments"]
    groups += ["responses_api_language_model_arguments", "chat_completions_language_model_arguments"] if remote_llm else ["language_model_arguments"]
    allowed = {"--" + name for group in groups for name in inventory[group]}
    env = {"VOICES_DIR": str(voice)}
    if remote_llm:
        env.update(LLM_BASE_URL="https://example.com/v1", LLM_MODEL="test-model")
    command = build_command(env, validate_voice(voice), "Painty")
    assert set(command[2::2]) <= allowed


def test_health_probes_real_backend_http(monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class PoolHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == "/v1/pool"
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"size":1,"in_use":0,"units":[]}')
        def log_message(self, *_):
            pass
    with ThreadingHTTPServer(("127.0.0.1", 0), PoolHandler) as upstream:
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setattr(server, "SPEECH_TO_SPEECH_URL", f"ws://127.0.0.1:{upstream.server_port}/v1/realtime")
        try:
            with TestClient(server.app) as client:
                assert client.get("/api/health").json()["backend"] is True
        finally:
            upstream.shutdown()
            thread.join(5)


def test_smoke_client_protocol_and_wav_writer(tmp_path):
    import base64
    from smoke_realtime import smoke
    async def run():
        async def fixture(ws):
            await ws.send(json.dumps({"type": "session.created"}))
            config = json.loads(await ws.recv())
            assert config["session"]["audio"]["output"]["format"]["rate"] == 24000
            await ws.send(json.dumps({"type": "session.updated"}))
            assert json.loads(await ws.recv())["type"] == "conversation.item.create"
            assert json.loads(await ws.recv())["type"] == "response.create"
            await ws.send(json.dumps({"type": "response.output_audio.delta", "delta": base64.b64encode(b'\x00\x01' * 2400).decode()}))
            await ws.send(json.dumps({"type": "response.output_audio_transcript.delta", "delta": "Fixture only"}))
            await ws.send(json.dumps({"type": "response.done", "response": {"status": "completed"}}))
        async with serve(fixture, "127.0.0.1", 0) as ws_server:
            port = ws_server.sockets[0].getsockname()[1]
            result = await smoke(f"ws://127.0.0.1:{port}", "test", tmp_path / "smoke.wav", 5)
            assert result["seconds"] == 0.1
    asyncio.run(run())
    with wave.open(str(tmp_path / "smoke.wav")) as wav:
        assert wav.getframerate() == 24000
        assert wav.getnframes() == 2400
