"""Save a real Realtime reply and timing evidence; optionally exercise STT with a WAV.

Audio mode uses paced input_audio_buffer.append plus trailing silence and server
VAD, matching the browser's speech boundary path. Commit alone does not flush VAD.
"""
import argparse
import asyncio
import base64
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from websockets.asyncio.client import connect
from audio_checks import read_pcm_wav, write_pcm_wav


async def smoke(url: str, text: str | None, output: Path, timeout: float,
                input_audio: Path | None = None):
    input_pcm = read_pcm_wav(input_audio, max_seconds=60)[0] if input_audio else None
    if input_pcm is None and not (text and text.strip()):
        raise ValueError("Provide text or an input WAV")
    pcm = bytearray()
    transcripts, input_transcripts = {}, {}
    started = first_audio = speech_stopped = input_end = completed_at = None
    completed = False
    sender = None
    config = json.loads((Path(__file__).resolve().parents[1] / "hf-realtime-voice/pirate.json").read_text())
    async with asyncio.timeout(timeout):
        async with connect(url, proxy=None, max_size=8 * 1024 * 1024) as ws:
            async def send(value):
                await ws.send(json.dumps(value))

            async def stream_input():
                nonlocal input_end
                # 40 ms PCM16 packets, followed by enough silence to finish VAD.
                padded = input_pcm + bytes(24000 * 2 * 2)
                deadline = time.monotonic()
                for offset in range(0, len(padded), 1920):
                    await send({"type": "input_audio_buffer.append",
                                "audio": base64.b64encode(padded[offset:offset + 1920]).decode()})
                    if offset < len(input_pcm):
                        input_end = time.monotonic()
                    deadline += 0.04
                    await asyncio.sleep(max(0, deadline - time.monotonic()))

            try:
                async for raw in ws:
                    event = json.loads(raw)
                    kind = event.get("type")
                    if kind == "error":
                        raise RuntimeError(event.get("error", {}).get("message", "Realtime error"))
                    if kind == "session.created":
                        turn_detection = ({"type": "server_vad", "create_response": True,
                                           "interrupt_response": True} if input_pcm is not None else None)
                        await send({"type": "session.update", "session": {"type": "realtime",
                            "instructions": config["instructions"], "output_modalities": ["audio"],
                            "audio": {"input": {"turn_detection": turn_detection,
                                                 "format": {"type": "audio/pcm", "rate": 24000}},
                                      "output": {"voice": config["voice"],
                                                 "format": {"type": "audio/pcm", "rate": 24000}}}}})
                    elif kind == "session.updated" and started is None:
                        started = time.monotonic()
                        if input_pcm is not None:
                            sender = asyncio.create_task(stream_input())
                        else:
                            await send({"type": "conversation.item.create", "item": {"type": "message", "role": "user",
                                "content": [{"type": "input_text", "text": text}]}})
                            await send({"type": "response.create"})
                    elif kind == "input_audio_buffer.speech_stopped":
                        speech_stopped = time.monotonic()
                    elif kind == "conversation.item.input_audio_transcription.completed":
                        input_transcripts[event.get("item_id", "default")] = event.get("transcript", "")
                    elif kind == "response.output_audio.delta":
                        data = base64.b64decode(event["delta"], validate=True)
                        if data and first_audio is None:
                            first_audio = time.monotonic()
                        pcm.extend(data)
                    elif kind == "response.output_audio_transcript.delta":
                        key = event.get("item_id", "default")
                        transcripts[key] = transcripts.get(key, "") + event.get("delta", "")
                    elif kind == "response.output_audio_transcript.done" and event.get("transcript"):
                        transcripts[event.get("item_id", "default")] = event["transcript"]
                    elif kind == "response.done":
                        status = event.get("response", {}).get("status")
                        if status != "completed":
                            raise RuntimeError(f"Response did not complete (status={status!r}); inspect backend logs")
                        completed_at = time.monotonic()
                        completed = True
                        break
            finally:
                if sender:
                    if not sender.done():
                        sender.cancel()
                    outcomes = await asyncio.gather(sender, return_exceptions=True)
                    if isinstance(outcomes[0], Exception):
                        raise outcomes[0]
    if not completed or started is None or first_audio is None:
        raise RuntimeError("Connection ended before a complete audio response")
    user_transcript = " ".join(input_transcripts.values()).strip()
    if input_pcm is not None and not user_transcript:
        raise RuntimeError("Audio arrived without an input transcription; STT was not verified")
    stats = write_pcm_wav(output, bytes(pcm))
    result = {"test": "realtime_audio" if input_audio else "realtime_text", "output": str(output), **stats,
              "completed_at_utc": datetime.now(timezone.utc).isoformat(),
              "first_audio_seconds": round(first_audio - started, 3),
              "total_seconds": round(completed_at - started, 3),
              "transcript": " ".join(transcripts.values()).strip(),
              "input_transcript": user_transcript,
              "stt_exercised": input_audio is not None}
    if speech_stopped is not None:
        result["speech_stopped_to_first_audio_seconds"] = round(first_audio - speech_stopped, 3)
    if input_end is not None:
        result["input_sent_to_first_audio_seconds"] = round(first_audio - input_end, 3)
    output.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="ws://127.0.0.1:7860/api/realtime")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text")
    source.add_argument("--input-audio", type=Path, help="Mono PCM16 24 kHz WAV, at most 60 seconds")
    parser.add_argument("--output", type=Path, default=Path("artifacts/captain-smoke.wav"))
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    text = args.text or (None if args.input_audio else "Bonjour capitaine, où allons-nous aujourd'hui ?")
    asyncio.run(smoke(args.url, text, args.output, args.timeout, args.input_audio))
