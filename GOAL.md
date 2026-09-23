> Original handoff, retained for context. Commands below may be outdated; use [README.md](README.md) to run the completed package.

# Goal: multilingual "pirate" voice demo for the Pollen team

Talk to the robot in any (European) language; it answers **in the same
language**, **in character as a pirate**, with **one consistent gravelly pirate
voice** across languages. TTS is [OmniVoice](https://github.com/k2-fsa/OmniVoice)
(600+ languages, zero-shot voice cloning). Stretch goal: serve OmniVoice with
vLLM-Omni so the TTS is a shared, batched service instead of an in-process model.

Status: researched, nothing built yet. Findings and the plan are below.

## Architecture (3 processes)

```
browser  ──ws──▶  hf-realtime-voice (FastAPI, :7860)   # UI + /api/* proxies
                        │ SPEECH_TO_SPEECH_URL
                        ▼
                  speech-to-speech serve (:8765)        # VAD → STT → LLM → TTS
                        │ (path B only) POST /v1/audio/speech
                        ▼
                  vllm serve k2-fsa/OmniVoice --omni (:8091)
```

- Front-end: `smolagents/hf-realtime-voice` Space, cloned at
  `~/Documents/hf-realtime-voice`. Speaks the OpenAI Realtime GA protocol.
- Backend: [`huggingface/speech-to-speech`](https://github.com/huggingface/speech-to-speech)
  (`speech-to-speech serve`), which **already ships two OmniVoice routes**:
  - `--tts omnivoice` — in-process (`src/speech_to_speech/TTS/omnivoice_handler.py`).
  - `--tts openai` — generic OpenAI-compatible `/v1/audio/speech` client
    (`openai_compatible_handler.py`), usable against vLLM-Omni.

## What "pirate" means here (two independent layers)

1. **Persona** = LLM system prompt. Sent by the front-end via `session.update`
   `instructions` (Settings → Instructions in the UI; `STARTUP_GREETING` env
   for the opening line). Language-following comes from the pipeline:
   `--language auto` (STT detects the language per utterance) plus
   `--enable_lang_prompt` ("reply in <language>" hint for small LLMs).
2. **Voice** = OmniVoice voice cloning from one 3–10 s reference clip. Cloning
   is the model's primary/most stable mode; **voice design (`instruct=`) is
   trained on Chinese+English only**, so don't rely on it for multilingual
   output. Use voice design *once* (in English) to manufacture the pirate
   reference clip, then clone that clip for every language.

   Caveat from upstream: cross-lingual cloning carries the reference clip's
   accent into the target language (an English pirate speaking French with an
   English accent). For this demo that is arguably the joke; if not, keep one
   reference clip per language (needs a small handler patch, see "Later").

## Findings on the vLLM path

- vLLM-Omni serves OmniVoice: `vllm serve k2-fsa/OmniVoice --omni --port 8091 --trust-remote-code`,
  OpenAI-compatible `POST /v1/audio/speech`, 24 kHz output
  ([docs](https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/examples/online_serving/omnivoice/)).
- Voice cloning online is supported **per request** via `ref_audio` + `ref_text`
  (HTTP URL, base64 data URL, or `file://` with `--allowed-local-media-path`).
  The doc intro still says "auto voice only" but the client, the API
  reference and PR #2463 all expose `ref_audio`; treat the intro as stale and
  verify on the installed version. Cloning needs `transformers>=5.3.0`.
- **No streaming and no voice presets/upload for OmniVoice** on vLLM-Omni
  (feature table). Every request must carry the ref clip; the answer arrives
  as one blob (wav/pcm).
- speech-to-speech's `--tts openai` handler forwards `model, input, voice,
  response_format, speed, language, task_type, instructions, stream` — **not
  `ref_audio` / `ref_text`**. So a cloned voice via vLLM needs a ~15-line patch
  to speech-to-speech (below). Without the patch you only get OmniVoice
  "auto voice" (random speaker) or `instructions` voice design (EN/ZH only).
- Honest trade-off: for a single booth demo the vLLM path buys nothing in
  latency (no streaming either way; OmniVoice RTF ≈ 0.025 on GPU in-process).
  It pays off when several sessions / several Reachy Minis share one TTS
  service (`--num_pipelines N` on the backend, batching on vLLM), or when the
  GPU for TTS lives on a different box than the pipeline.

## Plan

### Step 0 — hardware
One CUDA box. Rough VRAM: Qwen3-4B fp16 ≈ 8 GB, OmniVoice (0.6B + codec) ≈
2–3 GB, Parakeet ≈ 1 GB. To shrink: run the LLM remotely via HF router
(`--llm_backend responses-api --responses_api_base_url https://router.huggingface.co/v1`)
and keep only STT + TTS local.

### Step 1 — make the pirate reference clip
```bash
uv pip install "omnivoice>=0.2.1"
omnivoice-infer --model k2-fsa/OmniVoice \
  --text "Arr, welcome aboard, ye landlubbers! I be the captain of this fine vessel, and there be treasure to find." \
  --instruct "male, elderly, very low pitch, hoarse, British accent" \
  --output pirate_ref.wav
```
Iterate on `--instruct` until it sounds right (attributes: gender, age, pitch,
whisper, English accent; see `docs/voice-design.md` upstream). Keep the clip
3–10 s, 24 kHz mono. Record the exact text as `pirate_ref.txt`. Optionally
freeze it as a reusable prompt:
```python
from omnivoice import OmniVoice
m = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="cuda", dtype="float16")
m.create_voice_clone_prompt(ref_audio="pirate_ref.wav", ref_text=open("pirate_ref.txt").read()).save("pirate.pt")
```
(Or record a consenting team member doing the voice — cloning needs consent
either way.)

### Step 2 — Path A: in-process OmniVoice (fastest to a working demo)
```bash
uv pip install "speech-to-speech[omnivoice]"
speech-to-speech serve \
  --stt parakeet-tdt --language auto --enable_lang_prompt \
  --llm_backend transformers --model_name Qwen/Qwen3-4B-Instruct-2507 \
  --llm_device cuda --llm_torch_dtype float16 \
  --tts omnivoice --omnivoice_device cuda --omnivoice_dtype float16 \
  --omnivoice_voice_clone_prompt pirate.pt \
  --enable_live_transcription
# (or --omnivoice_ref_audio pirate_ref.wav --omnivoice_ref_text "$(cat pirate_ref.txt)")
```
Leave `--omnivoice_language` unset so the per-utterance detected language is
forwarded to TTS. Parakeet TDT v3 covers 25 European languages; use
`--stt whisper` for wider coverage.

### Step 3 — front-end
```bash
cd ~/Documents/hf-realtime-voice
docker build -t s2s-demo .
docker run -p 7860:7860 \
  -e SPEECH_TO_SPEECH_URL=ws://localhost:8765/v1/realtime \
  -e STARTUP_GREETING="Greet the user as a pirate captain, one sentence, in the language they are most likely to speak." \
  s2s-demo
```
`localhost:8765` is right for the WebSocket transport (the browser dials it);
use `host.docker.internal` only for WebRTC (server-side dial). Open
http://localhost:7860, Settings → Instructions → paste the pirate system
prompt (persona + "always answer in the user's language, 1–2 sentences").
The Voice dropdown lists Qwen3-TTS speaker names and is ignored by OmniVoice;
hide or relabel it in `index.html`/`main.js` when polishing.

### Step 4 — Path B: OmniVoice behind vLLM-Omni
1. Serve: `vllm serve k2-fsa/OmniVoice --omni --port 8091 --trust-remote-code --allowed-local-media-path /voices`
   (mount `pirate_ref.wav` under `/voices`). Smoke test with the upstream
   `examples/online_serving/text_to_speech/omnivoice/speech_client.py --ref-audio ... --ref-text ...`.
2. Patch speech-to-speech so the OpenAI-compatible TTS client can clone:
   - `arguments_classes/openai_tts_arguments.py`: add `openai_tts_ref_audio: Optional[str]`
     and `openai_tts_ref_text: Optional[str]`.
   - `TTS/openai_compatible_handler.py`: accept them in `setup()` and add
     `payload["ref_audio"]` / `payload["ref_text"]` next to `language` /
     `task_type` / `instructions` in the payload builder.
   - Upstream this as a PR — it is generic (CosyVoice3, Fish, GLM-TTS on
     vLLM-Omni need the same fields).
3. Run the pipeline against it:
```bash
speech-to-speech serve \
  --stt parakeet-tdt --language auto --enable_lang_prompt \
  --llm_backend transformers --model_name Qwen/Qwen3-4B-Instruct-2507 --llm_device cuda \
  --tts openai --openai_tts_base_url http://localhost:8091/v1 \
  --openai_tts_model k2-fsa/OmniVoice --openai_tts_voice default \
  --openai_tts_stream false --openai_tts_response_format wav \
  --openai_tts_ref_audio file:///voices/pirate_ref.wav \
  --openai_tts_ref_text "$(cat pirate_ref.txt)" \
  --enable_live_transcription
```
   `--openai_tts_stream` must stay `false` (no stream extension for OmniVoice).

### Step 5 — package as this repo
`docker-compose.yml` with three services (`vllm-omni`, `s2s`, `frontend`), a
`voices/` dir with the pirate clip + transcript, the pirate system prompt,
and a README with the two run modes. Pin `speech-to-speech` to a commit (or
your fork with the Step 4 patch) and `vllm-omni` to a release.

## Later / nice to have
- Per-language reference clips: extend `omnivoice_handler.py` to pick a
  `VoiceClonePrompt` keyed on `tts_input.language_code` (removes the accent
  carry-over).
- Sentence-level chunking already happens upstream of TTS; if first-audio
  latency feels long, lower `--omnivoice_num_steps` (32 default) and measure.
- Front-end: replace the Qwen3 voice list with a single locked "Captain"
  voice; pirate-themed orb colours.

## Licensing
OmniVoice code is Apache-2.0; the `k2-fsa/OmniVoice` weights are **CC-BY-NC**
(non-commercial). Fine for an internal/booth demo, not for a shipped product.
Voice cloning requires consent for the reference speaker.

## References
- https://github.com/k2-fsa/OmniVoice
- https://huggingface.co/k2-fsa/OmniVoice
- https://docs.vllm.ai/projects/vllm-omni/en/latest/user_guide/examples/online_serving/omnivoice/
- https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/
- https://github.com/vllm-project/vllm-omni/pull/2463
- https://github.com/huggingface/speech-to-speech (TTS/README.md, docs/openai-compatible-tts.md)
- https://huggingface.co/spaces/smolagents/hf-realtime-voice
