# Painty — multilingual pirate voice demo

Speak to a browser in any of 25 European languages; Painty the Pirate answers in
the same language, in his own cloned voice.

Pipeline, built on Hugging Face [`speech-to-speech`](https://github.com/huggingface/speech-to-speech):
Silero VAD + Smart Turn → Parakeet-TDT 0.6B v3 (transcript + language) →
Qwen3-4B-Instruct on vLLM (short pirate reply) → OmniVoice (voice cloned from the
reference clip for that language).

| Container | Runs |
| --- | --- |
| `llm` | Qwen3-4B-Instruct on `vllm/vllm-openai:v0.29.0-cu129` |
| `s2s` | VAD, Parakeet, OmniVoice and the Realtime WebSocket server |
| `ui` | Browser UI on port 7860, relays to `s2s` |

**Status (2026-09-23):** runs end-to-end on an RTX 5090 Laptop (24 GB, driver 580):
~2 s from a text request to first audio (plus ~0.5–0.8 s of turn detection), 20 GB
VRAM. Not yet done: a by-ear pass over all 30 voices (English + 29 dubs).

The voice is cut from Nickelodeon's SpongeBob theme song; keep this repo private.

## Install

Requirements:

- Linux x86_64 with an NVIDIA GPU, **≥ 20 GB VRAM** (24 GB tested).
- NVIDIA driver **≥ 580** (on 570 vLLM fails with `Triton Error: device kernel image is invalid`).
  On Ubuntu 22.04 with the NVIDIA apt repo:
  `sudo apt purge '*nvidia*570*' && sudo apt install nvidia-driver-580-open`, then reboot.
- Docker Engine 24+ with Compose v2.30+ and the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  (`docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi -L` must list your GPU).
- ~40 GB free disk: backend image 14 GB, vLLM image ~19 GB, model cache ~12 GB.
- Internet on first start (model downloads from the Hub, silero-vad from GitHub).

```bash
git clone git@github.com:nepyope/voice-to-voice-pirate-demo.git
cd voice-to-voice-pirate-demo
cp .env.example .env
python3 scripts/preflight.py   # checks Docker, driver, compose config and voice files; does not prove inference
docker compose up -d --build   # first build ~10 min, first start downloads ~12 GB
docker compose logs -f s2s     # wait for "Uvicorn running on http://0.0.0.0:8765"
curl --fail http://localhost:7860/api/health   # {"ready":true,"backend":true,"sdk":true}
```

Open **http://localhost:7860**, click the orb, allow the microphone and speak a
full sentence. Use headphones. Send one throwaway sentence first: the first turn
after a cold start is slow (the first 1–2 LLM requests can even time out).

```bash
docker compose ps -a              # llm, s2s and ui must be "healthy"
docker compose down               # stop; keeps model caches
docker compose restart s2s        # after changing voices/
docker compose up -d --build      # after changing scripts/, patches/, Dockerfile.backend
```

VRAM is mostly vLLM's up-front reservation (`LLM_GPU_MEMORY_UTILIZATION` in
`.env`), not what the model needs. `v0.30.0-cu129` of the vLLM image crashes on
import, hence the pin.

Qwen3-4B sometimes answers German text in English with this prompt (FR/ES/IT are
fine); check German by voice before demoing.

If you are on a Tailscale tailnet that advertises `172.18.0.0/16` or
`172.20.0.0/17` (the HF one does), Docker's default subnets collide with it and
containers silently lose network (`s2s` hangs at `health: starting`).
`compose.yaml` pins `172.30.0.0/24`; override with `COMPOSE_SUBNET` if needed.

For a remote GPU server, tunnel the UI: `ssh -N -L 7860:127.0.0.1:7860 USER@GPU_HOST`.
The browser microphone needs localhost or HTTPS. There is no authentication; do
not expose the UI publicly.

## How the voice follows the language

Parakeet transcribes each turn and detects its language (lingua on the transcript;
turns under 20 characters keep the previous language, initially English). The
language goes to the LLM prompt and to the TTS handler, which picks
`voices/langs/<code>.wav` + `.txt`, then the base language, then
`voices/pirate_ref.wav`. See
[voices/README.md](voices/README.md) and, for how the clips were made,
[docs/VOICE_PIPELINE.md](docs/VOICE_PIPELINE.md).

## Smoke tests

Run inside `s2s`. Outputs go to `artifacts/`.

```bash
# Text → spoken reply through the whole relay (bypasses STT)
docker compose exec s2s python scripts/smoke_realtime.py --url ws://ui:7860/api/realtime \
  --text "Bonjour Painty, où allons-nous aujourd'hui ?" --output /artifacts/text-fr.wav

# Recorded speech (mono 24 kHz PCM16) → reply, exercises STT and language selection
docker compose exec s2s python scripts/smoke_realtime.py --url ws://ui:7860/api/realtime \
  --input-audio /artifacts/question-fr.wav --output /artifacts/audio-fr.wav
```

A valid WAV does not prove pronunciation, speaker similarity or reply language;
listen to it.

## Tests and upstream patches

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-test.txt
pytest -q tests
(cd hf-realtime-voice && npm test)
```

These are CPU protocol/config tests, not GPU inference tests.

`Dockerfile.backend` builds `speech-to-speech` at commit
`ca5c33c9bb5e381288d315d1f8da122613845c4c` with the patches in `patches/`.
Per-language OmniVoice references are proposed upstream in
[huggingface/speech-to-speech#584](https://github.com/huggingface/speech-to-speech/pull/584).
Licensing: [NOTICE.md](NOTICE.md).
