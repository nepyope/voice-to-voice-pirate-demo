# Handoff — multilingual pirate voice demo (2026-09-23)

## The goal

Andi (HF, `huggingface/speech-to-speech` + hf-voice) asked for:

> a multilingual "pirate" voice demo for the Pollen team. I think using OmniVoice it
> should be doable. If it can be deployed with vLLM, that would be super great.

Context: hf-voice is a *hosted* speech-to-speech service that clients (browser, Reachy
Mini robots) ping over the OpenAI Realtime protocol. The demo should therefore be
something Pollen can run on a GPU box and talk to, not a one-off notebook.

Three requirements, current status:

| Requirement | Status |
|---|---|
| Multilingual pirate voice | **Done, working.** Parakeet detects the language, LLM answers in it, OmniVoice speaks it with a cloned pirate voice; a per-language reference is used when available (30 languages). |
| Using OmniVoice | **Done.** In-process `--tts omnivoice` handler from speech-to-speech, with a small upstream patch. |
| Deployed with vLLM | **Not done.** Compose overlay exists (`compose.vllm.yaml`) but has never run. Blocked by CUDA 13 vs host driver 570 — see "What's missing". LLM currently runs via transformers, not vLLM. |

## What's in this bundle

```
compose.yaml              3 services: voice-init (one-shot), s2s (backend), ui (hf-realtime-voice)
compose.vllm.yaml         overlay: OmniVoice served by vllm/vllm-omni as a separate TTS service (UNTESTED)
Dockerfile.backend        speech-to-speech @ ca5c33c9 + 3 patches + torch 2.8 cu128
patches/
  per-language-voices.patch   NEW: --omnivoice_ref_voices_dir, one clone prompt per language, chosen per turn
  remote-voice.patch          OpenAI-compatible TTS handler forwards ref_audio/ref_text/language (for vLLM-Omni)
  omnivoice-dependencies.patch  pyproject fix so .[omnivoice] resolves
scripts/
  launch_backend.py       builds the `speech-to-speech serve` command from .env + voices/
  voice_files.py          validates reference clips (mono, 24 kHz, 16-bit, 3–20 s, transcript present)
  prepare_voice.py        voice-init: generates a designed voice if voices/pirate_ref.wav is absent
  smoke_realtime.py       text -> websocket -> WAV, prints latency + transcript
voices/
  pirate_ref.wav/.txt     DEFAULT voice: Painty the Pirate (SpongeBob intro), music removed, 16.5 s
  langs/<lang>.wav/.txt   30 per-language Painty references cut from the 27-language dub video
  langs/manifest.json     source timestamps + transcripts per language
  candidates/             earlier variants (with music, 10 s cut, A/B test outputs)
  previous-generated-captain/   the original OmniVoice voice-design output (IP-free, sounded generic)
hf-realtime-voice/        the smolagents/hf-realtime-voice Space, served locally as the UI
tests/                    31 pytest tests (launcher, validation, patch application); no GPU needed
reference/                notes on OmniVoice + vLLM-Omni APIs
GOAL.md, REPORT.md, README.md   original brief, first implementation report, run instructions
```

Source MP3s used for the clips are in the repo root / Downloads, not needed at runtime.

## How to run (what works today)

Host: Linux x86_64, NVIDIA GPU with ≥ 20 GB, driver ≥ 570 (CUDA 12.8), Docker + Compose v2.30+,
NVIDIA Container Toolkit. Tested on an RTX 5090 Laptop 24 GB, driver 570.211, Docker 29 / Compose v5.

```bash
cp .env.example .env
docker compose up -d --build           # first build ~10 min, first start downloads ~12 GB of models
docker compose logs -f s2s             # wait for "Prepared 30 per-language OmniVoice clone prompts" + "Uvicorn running"
curl localhost:7860/api/health         # {"ready":true,"backend":true,"sdk":true}
```

Open http://localhost:7860, click the orb, allow mic, speak. GPU use ≈ 17.8 GB
(Qwen3-4B fp16 ≈ 8, OmniVoice + 31 clone prompts ≈ 6, Parakeet ≈ 1, rest CUDA overhead).

Scripted check (bypasses STT, always uses the default English voice):
```bash
docker compose exec s2s python scripts/smoke_realtime.py --url ws://ui:7860/api/realtime \
  --text "Bonjour capitaine, on part chercher un trésor ?" --output /voices/smoke.wav
```
Measured: ~2.5 s to first audio, ~7.5 s total for a two-sentence reply.

Unit tests: `python -m venv .venv && .venv/bin/pip install -r requirements-test.txt && .venv/bin/pytest -q tests`

Known operational gotcha: after a host reboot the compose network has come up without NAT once;
`s2s` then hangs at "health: starting" with no log output (it does a few HTTP fetches at boot).
`docker compose down && docker compose up -d` fixes it.

## Pipeline (what actually runs)

```
mic ──ws──▶ hf-realtime-voice (:7860, FastAPI, OpenAI Realtime protocol)
                │
                ▼
        speech-to-speech serve (:8765)
        VAD  : Silero + Smart Turn v3.2
        STT  : nvidia/parakeet-tdt-0.6b-v3   → text + language_code (25 EU languages)
        LLM  : Qwen/Qwen3-4B-Instruct-2507 via transformers, fp16, 160 max tokens
               (or any OpenAI-compatible endpoint via LLM_BASE_URL / LLM_MODEL / OPENAI_API_KEY)
        TTS  : k2-fsa/OmniVoice, 32 steps, voice_clone_prompt = langs[language_code] or default
```

The system prompt (`hf-realtime-voice/pirate.json`, passed via `--init_chat_prompt`) says: reply in
the user's language, one or two short sentences, light pirate flavour, no Markdown, no robot tools.

## What's missing — work items for parallel pickup

### A. vLLM deployment (Andi's explicit ask) — BLOCKED on host driver, otherwise ready to try

1. **TTS on vLLM-Omni.** `compose.vllm.yaml` runs `vllm/vllm-omni:v0.28.0` serving `k2-fsa/OmniVoice`
   on :8091 and switches `s2s` to `TTS_MODE=remote`, which uses the `--tts openai` handler +
   `remote-voice.patch` to send `ref_audio`/`ref_text`/`language` per request.
   - Blocker: every recent `vllm/vllm-omni` tag (v0.28–v0.30, nightly) is **CUDA 13.0**, which needs
     driver ≥ 580. Host has 570. Fix options: (a) `sudo apt install nvidia-driver-580` + reboot
     (the 580.178 package is available; the main image on cu128 keeps working), or (b) find/build a
     cu129 vllm-omni image (only `qwen-image21-*-cu129` / `minimax-h3-*-cu129` special tags exist).
   - Once it starts, verify: `POST http://tts:8091/v1/audio/speech` with `ref_audio: file:///voices/pirate_ref.wav`
     returns 24 kHz audio; then a smoke test through the whole stack.
   - Expect **higher** latency than in-process: vLLM-Omni has no streaming for OmniVoice, the reply
     arrives as one blob. Its value is batching many sessions / many robots on one TTS server.
   - Per-language voices are **not** wired for the remote path yet: `remote-voice.patch` sends one fixed
     `ref_audio`. Extend `openai_compatible_handler.py` to pick `file:///voices/langs/<lang>.wav` and
     read `<lang>.txt` by `tts_input.language_code`, falling back to the default (~10 lines).
     `--allowed-local-media-path /voices` is already set on the vLLM side.
   - Memory: `--gpu-memory-utilization 0.35` is a guess. With LLM in-process (8 GB) + backend + vLLM-Omni
     it should fit in 24 GB, but nobody has measured it.

2. **LLM on vLLM.** Add a `llm` service with `vllm/vllm-openai:v0.30.0-cu129` (CUDA 12.9 runs on
   driver 570) serving `Qwen/Qwen3-4B-Instruct-2507`, and set `LLM_BASE_URL=http://llm:8000/v1`,
   `LLM_MODEL=Qwen/Qwen3-4B-Instruct-2507` in `.env`. No code change: `launch_backend.py` already
   switches to the OpenAI-compatible LLM backend when `LLM_BASE_URL` is set. Needs
   `--gpu-memory-utilization` tuned (~0.45) so it coexists with the backend.
   Cheapest alternative that also dodges the "Cerebras stopped hosting" problem:
   `LLM_BASE_URL=https://router.huggingface.co/v1` (HF Inference Providers) + an HF token.

### B. Voice / IP

- Painty the Pirate is Nickelodeon IP. Fine for an internal Pollen demo, not shippable publicly.
  Ship an IP-free default too: generate a good pirate voice with OmniVoice voice-design (`instruct`,
  see `scripts/prepare_voice.py` and `voices/previous-generated-captain/`), save it as WAV, then
  clone *that* for all languages. Expose the choice as a `VOICE=` env var.
- Per-language switching has been verified only via logs/smoke for EN and FR, not by ear from the
  mic across many languages. Some dub clips have garbled Whisper transcripts of the sung verses
  (e.g. `de`, `el` is spoken-lines only). If a language sounds bad: trim its `voices/langs/<xx>.wav`
  and `.txt` to the two spoken lines, `docker compose restart s2s`.

### C. Reachy Mini

- Nothing robot-specific has been tested. The backend speaks the OpenAI Realtime protocol on
  `ws://<host>:8765/v1/realtime`; the browser UI is just one client. Find out from Andi how the Minis
  connect to hf-voice today and point one at this backend. The prompt currently says "you have no
  robot tools" — that line goes away once tool calling is wired.

### D. Upstreaming / delivery

- `per-language-voices.patch` and `remote-voice.patch` are small and general; rebase them from
  `ca5c33c9` onto `speech-to-speech` main and open PRs (ask Andi: one PR or two).
- The demo itself: push this folder to a repo (GitHub or HF). A Space is possible later but needs a
  paid always-on 24 GB GPU Space, one merged container (Docker Spaces run a single container), and
  no Painty audio if public. Andi's call.

### E. Small operational things

- Persist `torch.hub` cache (`/root/.cache/torch/hub`, silero-vad) in a named volume so `s2s` boots
  without internet once warmed.
- `voices/*.wav|txt|json` are gitignored (from the original brief); un-ignore `voices/langs/` and
  `pirate_ref.*` if the repo is meant to carry the voices.
- `BUILD_INFO.json` is stale (says gpu/docker untested) — update or delete.

## Quick facts for whoever picks this up

- Pinned speech-to-speech commit: `ca5c33c9bb5e381288d315d1f8da122613845c4c`
- Model IDs: `nvidia/parakeet-tdt-0.6b-v3`, `Qwen/Qwen3-4B-Instruct-2507`, `k2-fsa/OmniVoice`,
  `pipecat-ai/smart-turn-v3`
- New CLI flag added by our patch: `--omnivoice_ref_voices_dir /voices/langs`
- Reference clip contract: mono, 24 kHz, PCM16, 3–20 s, exact transcript in the sibling `.txt`
- Language codes: ISO 639-1 (`fr`, `de`, …); `es-419` also accepted, base code used as fallback
