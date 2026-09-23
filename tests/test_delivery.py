import asyncio
import base64
import io
import json
import struct
import wave
from pathlib import Path

import pytest
from websockets.asyncio.server import serve

from launch_backend import build_command
from preflight import driver_issues
from smoke_realtime import smoke
from voice_files import validate_language_voices, validate_voice, voice_directory

ROOT = Path(__file__).resolve().parents[1]


def wav_bytes(pcm=b"\x00\x01" * 2400):
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    return out.getvalue()


def test_painty_loads_all_language_references():
    env = {"VOICES_DIR": str(ROOT / "voices")}
    voice = validate_voice(voice_directory(env))
    assert len(validate_language_voices(ROOT / "voices/langs")) == 29
    command = build_command({**env, "LLM_BASE_URL": "http://llm:8000/v1", "LLM_MODEL": "m"}, voice, "Painty")
    assert "--omnivoice_ref_voices_dir" in command


def test_missing_reference_fails(tmp_path):
    with pytest.raises(ValueError):
        validate_voice(voice_directory({"VOICES_DIR": str(tmp_path)}))


def test_preflight_requires_driver_580():
    assert driver_issues("570.211")[0]
    assert not driver_issues("580.178")[0]
    assert driver_issues("580.178", "vllm/vllm-openai:custom")[1]


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
