# Captain — multilingual pirate voice demo

A browser or Reachy Mini client talks to Hugging Face `speech-to-speech`; Parakeet
transcribes the user and detects language, Qwen produces a short pirate reply,
and OmniVoice speaks it using a saved reference. The same Realtime endpoint works
with local models or separate vLLM LLM/TTS services.

**Status (2026-09-23):** all three inference modes run end-to-end on an RTX 5090
Laptop (24 GB, driver 580): in-process, LLM on vLLM, and LLM + OmniVoice both on
vLLM. Measured numbers, fixes and caveats are in
[GPU_VALIDATION_2026-09-23.md](GPU_VALIDATION_2026-09-23.md). Still pending: a
by-ear pass over many languages and a run on a physical Reachy Mini.
[PRESENTING_TO_ANDI.md](PRESENTING_TO_ANDI.md) has the demo plan,
[HANDOFF.md](HANDOFF.md) the work-item status, [REPORT.md](REPORT.md) the test evidence.

## Install

Requirements:

- Linux x86_64 with an NVIDIA GPU, **≥ 20 GB VRAM** (24 GB tested).
- NVIDIA driver **≥ 570** for the in-process mode, **≥ 580** for either vLLM
  overlay (their images are CUDA 12.9 / 13.0; on 570 vLLM fails with
  `Triton Error: device kernel image is invalid`). On Ubuntu 22.04 with the NVIDIA
  apt repo, upgrading is `sudo apt purge '*nvidia*570*' && sudo apt install nvidia-driver-580-open` + reboot.
- Docker Engine 24+ with Compose v2.30+ and the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  (`docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi -L` must list your GPU).
- ~30 GB free disk: backend image 14 GB, vLLM images 9–19 GB each, model cache ~12 GB.
- Internet on first start (model downloads from the Hub, silero-vad from GitHub).

```bash
git clone git@github.com:nepyope/voice-to-voice-pirate-demo.git
cd voice-to-voice-pirate-demo
cp .env.example .env            # defaults: VOICE=captain, local LLM, UI on 127.0.0.1:7860
python3 scripts/preflight.py --mode local
docker compose up -d --build    # first build ~10 min, first start downloads ~12 GB of models
docker compose logs -f s2s      # wait for "Uvicorn running on http://0.0.0.0:8765"
curl --fail http://localhost:7860/api/health   # {"ready":true,"backend":true,"sdk":true}
```

Open **http://localhost:7860**, click the orb, allow the microphone, speak a full
sentence. The reply follows the language you spoke. Use headphones.

For the pirate voice used in the demo set `VOICE=painty` in `.env` (cloned from the
SpongeBob intro, with a per-language reference for 30 dubs — internal use only,
it is Nickelodeon IP). `VOICE=captain` is an IP-free OmniVoice-designed voice.
Changing `.env` needs `docker compose up -d --force-recreate s2s`.

If you are on a Tailscale tailnet that advertises `172.18.0.0/16` or
`172.20.0.0/17` (the HF one does), Docker's default compose subnets collide with
it and containers silently lose network — `s2s` then hangs at `health: starting`
forever. `compose.yaml` pins the network to `172.30.0.0/24` for this reason;
override with `COMPOSE_SUBNET` if that range is taken on your host.

Everyday commands:

```bash
docker compose ps -a                        # both s2s and ui must be "healthy"
docker compose down                         # stop; keeps voices and model caches
docker compose up -d --build                # after changing scripts/, patches/, Dockerfile.backend
docker compose restart s2s                  # after changing anything under voices/
```

Health proves API and SDK availability, not speech quality. End the browser call
before smoke tests: one pipeline is configured by default. `NUM_PIPELINES` can
increase the pool, but also increases backend memory use; concurrency is unbenchmarked.

For a GPU server, tunnel the UI from your laptop:

```bash
ssh -N -L 7860:127.0.0.1:7860 YOUR_USER@YOUR_GPU_HOST
```

A remote browser microphone needs localhost or HTTPS. The UI relays `/api/realtime`
on its own origin. Add authentication/TLS before exposing this demo publicly.
`docker compose down` preserves reference clips and both cache volumes. Use the
same `-f` file list for all operations when an overlay is active.

## Select the voice

Set `VOICE` in `.env`, then recreate the services using your selected Compose files.
Each preset owns its own default and optional `langs/` directory. Captain never
silently switches to the supplied third-party dubs.

| `VOICE` | Files used | Behavior |
| --- | --- | --- |
| `captain` (default) | `voices/captain/pirate_ref.wav` + `.txt` | Original OmniVoice-designed reference from the handoff, cloned across languages. Not newly generated or listening-tested here. |
| `painty` | `voices/pirate_ref.wav` + `.txt`, `voices/langs/` | Painty the Pirate (SpongeBob intro, music removed) plus 30 per-language dub references. Tracked in this private repo; excluded from the `--public` export. |
| `custom` | `voices/custom/pirate_ref.wav` + `.txt`, optional `voices/custom/langs/` | A supplied recording and exact transcript; missing/invalid files fail before model startup. |

References must be mono, 24 kHz PCM16, 3–20 seconds, with non-empty exact
transcripts. Short clean 3–10 second clips are preferred. A language reference is
named `<code>.wav` and `<code>.txt`. Both TTS routes choose an exact normalized
code, then its base language, then the selected preset's default (`fr-CA` → `fr`
→ default). Directory contents are validated at startup. Restart after edits.
A configured remote clone also takes precedence over client speaker presets,
so Reachy's Qwen voice selection cannot accidentally change the Captain.

The generated Captain in the handoff was described as generic. To audition a
new candidate on a GPU without overwriting it:

```bash
docker compose run --rm --no-deps voice-init python scripts/prepare_voice.py \
  --directory /voices/custom --seed 23 \
  --description "male, elderly, very low pitch, british accent"
```

The command reuses an existing pair rather than replacing it. Use a new candidate
directory to try another seed; after listening, place the chosen pair under
`voices/custom/` and select `VOICE=custom`. Voice design is used once in English;
subsequent turns use cloning. No new multilingual Captain references were synthesized here.

## Choose where inference runs

| Mode | Compose files after `-f compose.yaml` | Driver note |
| --- | --- | --- |
| Local LLM + local TTS | None | Driver 570+. Validated: ~2.5 s to first audio, 17 GB |
| vLLM LLM + local TTS | `-f compose.llm-vllm.yaml` | Driver 580+ (CUDA 12.9 image; fails on 570). Validated: ~2 s, 20 GB |
| Local/remote LLM + vLLM TTS | `-f compose.vllm.yaml` | Driver 580+ (CUDA 13 image) |
| vLLM LLM + vLLM TTS | Both overlays | Driver 580+. Validated: ~4 s to first audio (no TTS streaming), 19 GB |

When starting both overlays, `llm` may fail once with "No available memory for the
cache blocks" if it profiles memory while `tts` is still capturing CUDA graphs;
run `up -d` again. Send one request to warm up before demoing: the first turn or
two after a cold start can exceed the 20 s LLM timeout.

```bash
# Check the combined mode, including image tag availability.
python3 scripts/preflight.py --mode vllm --check-images --output artifacts/preflight.json
# Stop the previous stack before switching modes.
docker compose down
docker compose -f compose.yaml -f compose.vllm.yaml -f compose.llm-vllm.yaml up -d --build
```

Other preflight modes are `local`, `vllm-llm`, and `vllm-tts`. Preflight checks the
actual resolved Compose config, selected reference files, Docker access, host
GPU/driver, and optional registry manifests. It does not prove CUDA container
access, available VRAM fit, or successful inference. It does not change drivers.
LLM image: `vllm/vllm-openai:v0.29.0-cu129`, Qwen3-4B, 4,096-token context,
4 sequence limit, eager execution (`v0.30.0-cu129` crashes on import, do not use).
TTS image: `vllm/vllm-omni:v0.28.0`, OmniVoice.
Images and memory fractions are configurable in `.env`. Defaults of 0.45 (LLM)
and 0.35 (TTS) are initial allocations, not measured fit guarantees. Leave room
for STT, CUDA overhead and other processes. All services use the available GPU
by default; these files do not distribute models across multiple GPUs.

The Omni path sends `ref_audio`, `ref_text` and the turn's language on each request.
References are mounted at `/voices` in both containers; file URLs use that server
path. It requests a complete WAV, not token streaming. vLLM provides a deployment
and shared-serving route; no latency or throughput improvement has been established.

For an external LLM, omit `compose.llm-vllm.yaml` and set `LLM_BASE_URL`, `LLM_MODEL`
and `OPENAI_API_KEY` in `.env`. The LLM overlay deliberately overrides the URL
and uses a local placeholder key. The TTS service never receives that provider key.

## Collect real inference evidence

Use the same Compose file list you used at launch in the commands below. For
brevity the examples show the combined vLLM mode. Outputs go into `artifacts/`,
which is mounted in the backend at `/artifacts` and excluded from source exports.

Direct vLLM-Omni clone request (saves validated 24 kHz WAV and JSON timing):

```bash
docker compose -f compose.yaml -f compose.vllm.yaml -f compose.llm-vllm.yaml exec s2s \
  python scripts/smoke_tts.py --language fr --output /artifacts/tts-fr.wav
```

Text to spoken reply through the entire Realtime relay:

```bash
docker compose -f compose.yaml -f compose.vllm.yaml -f compose.llm-vllm.yaml exec s2s \
  python scripts/smoke_realtime.py --url ws://ui:7860/api/realtime \
  --text "Bonjour capitaine, où allons-nous aujourd'hui ?" --output /artifacts/text-fr.wav
```

**Text input bypasses STT and does not exercise language-reference selection by
detected speech.** For speech input, record a complete sentence as mono 24 kHz
PCM16 in `artifacts/question-fr.wav`, then run:

```bash
docker compose -f compose.yaml -f compose.vllm.yaml -f compose.llm-vllm.yaml exec s2s \
  python scripts/smoke_realtime.py --url ws://ui:7860/api/realtime \
  --input-audio /artifacts/question-fr.wav --output /artifacts/audio-fr.wav
```

Audio mode paces PCM packets and appends silence to finish VAD. It requires a
final input transcript, non-silent output audio and a completed response. A
partial/disconnected/cancelled response fails. JSON records time from request to
first audio and, when available, from server speech-stop to first audio. Keep
these latency definitions separate when comparing runs. WAV checks do not judge
pronunciation, speaker similarity or whether the reply used the intended language.

Use full sentences when switching languages. The pinned STT language detector
skips transcripts shorter than 20 characters and otherwise falls back to its
last language (initially English). The STT route covers 25 European languages;
30 reference clips and OmniVoice's wider synthesis coverage do not expand it.
For the final listening/interruption checks, see [VALIDATION.md](VALIDATION.md).

## Reachy Mini

[The Reachy integration](integrations/reachy/README.md) includes a native Captain
profile, verified environment names, a direct backend port overlay and a tunnel
recipe. The profile uses no robot tools; movement/tool calling remains outside
this demo. Its format was checked with the current upstream parser. Hardware
microphone/playback, reconnection and echo behavior are not yet verified.

## Tests, upstream patches and distribution

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-test.txt
pytest -q tests
(cd hf-realtime-voice && npm test)
```

JavaScript unit tests use Node's built-in test runner; `npm ci` is required to
install the browser SDK for actually running the frontend. The frontend Docker
build does this. Python tests include protocol fixtures, which are not runtime
responses or evidence of GPU inference.

`patches/` targets pinned backend commit `ca5c33c9bb5e381288d315d1f8da122613845c4c`.
`patches/upstream/` contains separate diffs checked against current upstream
`a6576590f2a63f0d7c090e306422d86e0e1756ce`. See [UPSTREAMING.md](UPSTREAMING.md)
for review scope. This repository is private; no upstream PR has been opened yet.

The full supplied audio collection is retained in the complete bundle. For a
source export that includes only the original Captain recording:

```bash
python3 scripts/package_demo.py --public --output artifacts/captain-shareable.zip
```

The exporter excludes third-party voice folders, local secrets, dependencies,
recorded test artifacts and caches, and recomputes a content manifest. The model
card lists OmniVoice weights as CC-BY-NC; an original speaker reference does not
change that model license. See [NOTICE.md](NOTICE.md). Model weights are downloaded
at startup and are not bundled. `reference/` preserves the historical documents.
