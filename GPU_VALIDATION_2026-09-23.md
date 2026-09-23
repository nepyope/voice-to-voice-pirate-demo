# GPU validation run — 2026-09-23 evening

Host: RTX 5090 Laptop 24 GB, driver **580.178.04 / CUDA 13.0** (upgraded from 570 today),
Docker 29 / Compose v5, Ubuntu 22.04, kernel 6.8.0-138. Voice: Painty with per-language references.
Artifacts (WAV + JSON) in `artifacts/`.

## Results

| Mode | Compose files | Status | First audio (text smoke) | GPU |
| --- | --- | --- | --- | --- |
| local (in-process LLM + OmniVoice) | `compose.yaml` | pass | EN 2.5 s, FR 2.6 s | 17.3 GB |
| LLM on vLLM | `+ compose.llm-vllm.yaml` | pass | EN 1.9 s, FR 2.1 s | 20.2 GB |
| LLM + TTS on vLLM (full) | `+ compose.vllm.yaml + compose.llm-vllm.yaml` | pass | EN 4.1 s, FR 4.3 s, ES 4.1 s | 18.8 GB |

- Full mode: `smoke_tts.py --language fr` selected `file:///voices/langs/fr.wav` (evidence JSON
  in `artifacts/vllm-full/tts-fr.json`); direct clone request to vLLM-Omni returned 24 kHz WAV.
- Full mode is slower to first audio as predicted: vLLM-Omni has no streaming for OmniVoice, the
  whole reply is synthesized before playback starts. Its value is batching / sharing one TTS server.
- All text smokes bypass STT; language switching from the mic still needs the listening pass.

## Fixes made while deploying (all in this tree)

1. `compose.yaml`: pinned the compose network to `172.30.0.0/24` (`COMPOSE_SUBNET`). Docker's
   default subnets (172.18/16, 172.20/17) are advertised as routes on the HF Tailscale tailnet;
   containers on them silently lose all outbound traffic and `s2s` hangs at "health: starting".
   Anyone on the tailnet running this needs it.
2. `compose.llm-vllm.yaml` / `compose.vllm.yaml`: healthcheck used `python`, the vLLM images only
   ship `python3`; the service never became healthy so `s2s` never started. Changed to `python3`.
3. `.env`: `VLLM_LLM_IMAGE=vllm/vllm-openai:v0.29.0-cu129`. `v0.30.0-cu129` crashes on import
   (`operator torchvision::nms does not exist`) before touching the GPU.
4. `compose.llm-vllm.yaml`: added `NVIDIA_DISABLE_REQUIRE=1` and a tmpfs over
   `/usr/local/cuda/compat`. Needed to even start the cu129 image on a 570 driver; harmless on 580.
   Note: on 570 vLLM still failed later with `Triton Error [CUDA]: device kernel image is invalid`
   (PTX from CUDA 12.9 cannot JIT on a 12.8 driver). **Driver ≥ 580 is a hard requirement for both
   vLLM overlays on this GPU.**

## Observed, not fixed

- Starting `llm` and `tts` simultaneously: `llm` died once with "No available memory for the cache
  blocks" while `tts` was capturing CUDA graphs. A second `up -d` succeeded. Either start `tts` first
  or make `llm` depend on `tts` healthy in full mode.
- First 1–2 requests after a full-mode start timed out ("Language model generation timed out after
  20.0s"); vLLM logged ~1 tok/s during that window. Fine afterwards. Warm up with a request before demoing.
- Qwen3-4B (temperature 0) answers **German** text in English with this system prompt, while
  FR/ES/IT are fine. Reproduced against vLLM directly, so it is the model, not the serving path.
  The mic path adds Parakeet's detected language to the prompt (`--enable_lang_prompt`), which the
  text smoke does not; verify German by voice before the demo.
- Driver upgrade on Ubuntu 22.04 with the NVIDIA repo: `apt install nvidia-driver-580` fails on
  `nvidia-kernel-common` conflicts and a file clash with `libnvidia-common-570`. What worked:
  `apt purge '*nvidia*570*'` then `apt install nvidia-driver-580-open`, reboot.
