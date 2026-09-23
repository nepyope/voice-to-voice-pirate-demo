# Painty the multilingual pirate voice-to-voice

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
docker compose up -d --build   # first build ~10 min, first start downloads ~12 GB
docker compose ps              # wait until llm, s2s and ui are all "healthy"
```

Then open **http://localhost:7860**, click the orb, allow the microphone and speak
a full sentence. Use headphones. The first reply after a start is slow.
Stop with `docker compose down`.

On a remote GPU machine, tunnel the page first:
`ssh -N -L 7860:127.0.0.1:7860 USER@GPU_HOST` (the microphone needs localhost or HTTPS).

## How the voice follows the language

Parakeet detects the language of each turn; OmniVoice then clones Painty from
`voices/langs/<code>.wav`, falling back to `voices/pirate_ref.wav` (English).
How the clips were made: [docs/VOICE_PIPELINE.md](docs/VOICE_PIPELINE.md).

`Dockerfile.backend` builds `speech-to-speech` at a pinned commit with the patches
in `patches/`; the per-language voice patch is proposed upstream in
[huggingface/speech-to-speech#584](https://github.com/huggingface/speech-to-speech/pull/584).
