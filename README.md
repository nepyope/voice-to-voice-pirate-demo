# Painty — multilingual pirate voice demo

Speak to a browser (or a Reachy Mini) in any of 25 European languages; Painty the
Pirate answers in the same language, in his own cloned voice.

Pipeline, built on Hugging Face [`speech-to-speech`](https://github.com/huggingface/speech-to-speech):
Silero VAD + Smart Turn → Parakeet-TDT 0.6B v3 (transcript + language) →
Qwen3-4B-Instruct (short pirate reply) → OmniVoice (voice cloned from the
reference clip for that language). The same Realtime endpoint works with the
models in-process or served by vLLM / vLLM-Omni.

**Status (2026-09-23):** all three inference modes run end-to-end on an RTX 5090
Laptop (24 GB, driver 580). Numbers, fixes and caveats are in
[GPU_VALIDATION_2026-09-23.md](GPU_VALIDATION_2026-09-23.md). Not yet done: a
by-ear pass over all 30 voices (English + 29 dubs) and a run on a physical Reachy Mini.

The voice is cut from Nickelodeon's SpongeBob theme song; keep this repo private.

## Install

Requirements:

- Linux x86_64 with an NVIDIA GPU, **≥ 20 GB VRAM** (24 GB tested).
- NVIDIA driver **≥ 570** for the in-process mode, **≥ 580** for either vLLM
  overlay (on 570 vLLM fails with `Triton Error: device kernel image is invalid`).
  On Ubuntu 22.04 with the NVIDIA apt repo:
  `sudo apt purge '*nvidia*570*' && sudo apt install nvidia-driver-580-open`, then reboot.
- Docker Engine 24+ with Compose v2.30+ and the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  (`docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi -L` must list your GPU).
- ~30 GB free disk: backend image 14 GB, vLLM images 9–19 GB each, model cache ~12 GB.
- Internet on first start (model downloads from the Hub, silero-vad from GitHub).

```bash
git clone git@github.com:nepyope/voice-to-voice-pirate-demo.git
cd voice-to-voice-pirate-demo
cp .env.example .env
python3 scripts/preflight.py --mode vllm-llm
docker compose -f compose.yaml -f compose.llm-vllm.yaml up -d --build   # first build ~10 min, first start downloads ~12 GB
docker compose -f compose.yaml -f compose.llm-vllm.yaml logs -f s2s     # wait for "Uvicorn running on http://0.0.0.0:8765"
curl --fail http://localhost:7860/api/health   # {"ready":true,"backend":true,"sdk":true}
```

Open **http://localhost:7860**, click the orb, allow the microphone and speak a
full sentence. Use headphones. Send one throwaway sentence first: the first turn
after a cold start is slow.

Use the same `-f` list for every command while a mode is running:

```bash
docker compose -f compose.yaml -f compose.llm-vllm.yaml ps -a       # s2s, llm and ui must be "healthy"
docker compose -f compose.yaml -f compose.llm-vllm.yaml down        # stop; keeps model caches
docker compose -f compose.yaml -f compose.llm-vllm.yaml restart s2s # after changing voices/
docker compose -f compose.yaml -f compose.llm-vllm.yaml up -d --build  # after changing scripts/, patches/, Dockerfile.backend
```

If you are on a Tailscale tailnet that advertises `172.18.0.0/16` or
`172.20.0.0/17` (the HF one does), Docker's default subnets collide with it and
containers silently lose network (`s2s` hangs at `health: starting`).
`compose.yaml` pins `172.30.0.0/24`; override with `COMPOSE_SUBNET` if needed.

For a remote GPU server, tunnel the UI: `ssh -N -L 7860:127.0.0.1:7860 USER@GPU_HOST`.
The browser microphone needs localhost or HTTPS. There is no authentication; do
not expose the UI publicly.

## Inference modes

| Mode | Compose files | Where the models run | First audio | VRAM |
| --- | --- | --- | --- | --- |
| In-process | `compose.yaml` | LLM and OmniVoice inside `s2s` | ~2.5 s | 17 GB |
| LLM on vLLM (recommended) | `+ compose.llm-vllm.yaml` | Qwen on `vllm-openai`, OmniVoice in `s2s` | ~2 s | 20 GB |
| Full vLLM | `+ compose.vllm.yaml + compose.llm-vllm.yaml` | Qwen on `vllm-openai`, OmniVoice on `vllm-omni` | ~4 s | 19 GB |

First-audio times are measured from a text request and exclude the ~0.5–0.8 s of
silence turn detection waits for. VRAM is mostly vLLM's up-front reservation
(`LLM_GPU_MEMORY_UTILIZATION`, `TTS_GPU_MEMORY_UTILIZATION` in `.env`), not what
the models need.

Full vLLM mode is slower because vLLM-Omni runs OmniVoice in float32 (bfloat16
crashes its CUDA-graph warmup) and re-processes the reference clip with every
request: a line takes ~0.8 s to synthesize with no reference, ~1.65 s with a 6 s
reference and ~2.7 s with the current ~11 s clips. Its value is that LLM and TTS
become shared services that several clients can use.

When starting full vLLM mode, `llm` may fail once with "No available memory for
the cache blocks" while `tts` is still capturing CUDA graphs; run `up -d` again.

Images: `vllm/vllm-openai:v0.29.0-cu129` (`v0.30.0-cu129` crashes on import) and
`vllm/vllm-omni:v0.28.0`. Preflight modes are `local`, `vllm-llm`, `vllm-tts` and
`vllm`; add `--check-images` to verify tags. Preflight checks config, voice files,
Docker and driver; it does not prove inference.

For an external LLM, omit `compose.llm-vllm.yaml` and set `LLM_BASE_URL`,
`LLM_MODEL` and `OPENAI_API_KEY` in `.env`.

## How the voice follows the language

Parakeet transcribes each turn and detects its language (lingua on the transcript;
turns under 20 characters keep the previous language, initially English). The
language goes to the LLM prompt and to the TTS handler, which picks
`voices/langs/<code>.wav` + `.txt`, then the base language, then
`voices/pirate_ref.wav`. Both TTS routes use the same rule. See
[voices/README.md](voices/README.md) and, for how the clips were made,
[docs/VOICE_PIPELINE.md](docs/VOICE_PIPELINE.md).

## Smoke tests

Run inside `s2s` with the same `-f` list you launched with. Outputs go to
`artifacts/`.

```bash
# Direct vLLM-Omni clone request (full vLLM mode only)
docker compose -f compose.yaml -f compose.vllm.yaml -f compose.llm-vllm.yaml exec s2s \
  python scripts/smoke_tts.py --language fr --output /artifacts/tts-fr.wav

# Text → spoken reply through the whole relay (bypasses STT)
docker compose -f compose.yaml -f compose.llm-vllm.yaml exec s2s \
  python scripts/smoke_realtime.py --url ws://ui:7860/api/realtime \
  --text "Bonjour Painty, où allons-nous aujourd'hui ?" --output /artifacts/text-fr.wav

# Recorded speech (mono 24 kHz PCM16) → reply, exercises STT and language selection
docker compose -f compose.yaml -f compose.llm-vllm.yaml exec s2s \
  python scripts/smoke_realtime.py --url ws://ui:7860/api/realtime \
  --input-audio /artifacts/question-fr.wav --output /artifacts/audio-fr.wav
```

A valid WAV does not prove pronunciation, speaker similarity or reply language;
listen to it.

## Reachy Mini

[integrations/reachy](integrations/reachy/README.md) has a Painty profile for the
Reachy Mini conversation app, a port overlay (`compose.reachy.yaml`) and a tunnel
recipe. The profile has no robot tools. It has not been run on hardware.

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
[huggingface/speech-to-speech#584](https://github.com/huggingface/speech-to-speech/pull/584);
`patches/remote-voice.patch` has not been proposed yet. Licensing: [NOTICE.md](NOTICE.md).
