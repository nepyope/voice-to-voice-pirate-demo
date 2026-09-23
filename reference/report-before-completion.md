# Captain demo — implementation and verification report

Date: 22 September 2026

## Result

Converted the supplied `voice-to-voice-pirate-demo(2).zip` handoff into a launchable
source package with a Captain persona, persistent reference-voice preparation,
Docker Compose configurations, backend patches and repeatable checks.

**37 automated tests passed:** 30 Python and 7 JavaScript. Both Compose
configurations validated with Docker Compose 2.30.3. The backend's 124 package
versions resolved successfully for Python 3.11 / Linux x86_64.

This is an implementation verified at the application/protocol level. It is
**not yet certified on a GPU or physical robot**. The environment had no NVIDIA
GPU or Docker daemon, and the browser tool blocked access to the local app.
No audible pirate response, microphone round trip, latency benchmark or robot
motion is claimed as tested.

## What changed

| Area | In the attachment | Finished implementation |
| --- | --- | --- |
| Deployment | Separate commands in a goal document; no complete launcher | Primary Compose stack, optional vLLM override, environment example, health checks and ordered startup |
| Browser networking | Browser received the configured backend URL directly; Docker and browser hostnames could differ | Same-origin `/api/realtime` relay; Docker target stays server-side; HTTPS pages derive `wss` automatically |
| Persona | Generic friendly assistant | Shared Captain instructions, same-language replies, short spoken answers and separate browser settings namespace |
| Voice selection | Qwen speaker menu | One locked Captain label; the saved reference actually determines OmniVoice's speaker |
| Reference voice | Proposed manual generation command | Generate once, persist and reuse; validate supplied WAV/transcript pairs; record reference hash |
| Language configuration | Generic `--language auto` example | Parakeet automatic detection with no fixed language, plus the LLM language prompt |
| Remote TTS | Clone fields missing; only a fixed configured language was forwarded | Reference audio/text pair validation, forwarding on every request, and detected per-turn language propagation |
| Model UI | Hosted Gemma/Cerebras/Qwen-TTS claims | Default local Qwen/Parakeet/OmniVoice description; unavailable camera feature hidden and no automatic camera capture |
| Dependencies | Backend install not specified or resolved | Exact backend commit, core pins, 124-version lock, and a minimal packaging fix |
| Verification | npm scripts referred to tests absent from the ZIP | Working test commands, offline fixtures with provenance, and a real-backend smoke client |

The backend build fetches the exact commit and applies the patches before
installing it. The remote fix is therefore part of the executable deployment,
not merely a change to an unused reference file.

## Concrete problems found

1. **Missing clone payload:** the generic OpenAI-compatible TTS adapter lacked
   `ref_audio` and `ref_text`. A remote endpoint could not reconstruct the intended
   Captain voice from the handoff's proposed flags. Added both dataclass fields,
   setup validation and request serialization.
2. **Missing per-turn language in remote TTS:** the adapter read only its fixed
   language setting. The patch now carries `tts_input.language_code` through the
   HTTP request, while allowing an explicit fixed-language override.
3. **Stale CLI flag:** the current selected-backend parser treats `--language` as
   a Whisper option and ignores it for Parakeet. The launcher uses
   Parakeet's documented automatic-detection default by leaving its fixed-language
   option unset. Passing literal `auto` to that option would instead leave an
   invalid fallback language on a short first turn. Tests check that both fixed
   and stale language options are absent, and check other flags against names
   extracted from the pinned source.
4. **Container networking and binding:** a browser cannot use Docker service
   names. Also, the current backend defaults to loopback. The launcher binds it
   to `0.0.0.0` inside the private Compose network; only the UI's loopback port is
   published, and the browser uses its own origin.
5. **Dependency resolution failure:** upstream's default
   `faster-qwen3-tts[ggml]` extra pulled a C++ wheel requiring a newer glibc
   platform. This demo uses OmniVoice. A one-line packaging patch retains the
   Python Qwen package but omits its unused GGML extra. Resolution then passed.
6. **Unsupported voice-design expectation:** the supplied OmniVoice attributes
   document lists whisper as its style attribute, not hoarseness. Generation
   uses supported age/pitch/accent attributes. A genuinely gravelly performance
   still needs auditioning or a suitable reference recording.

The generated reference uses a fixed seed and is persisted, but a fixed seed
alone is not a guarantee of identical audio across hardware or package changes.
Reusing the saved WAV is the mechanism that preserves reference identity.

## Verification performed

| Check | Result | What it establishes |
| --- | --- | --- |
| Python tests | 30 passed | Reference handling, CLI construction, HTTP readiness, relay behavior, clone payloads/language, and smoke client protocol/WAV writing |
| JavaScript tests | 7 passed | Same-origin URL handling, large PCM base64 round trips, transcript recovery, 24 kHz PCM framing from 24/44.1/48 kHz input |
| Actual WebSocket upstream fixture | Passed | JSON and binary messages survive relay unchanged; client disconnect releases the upstream session; failure messages omit target secrets |
| Real HTTP readiness fixture | Passed | UI readiness contacts the backend pool endpoint and reports availability |
| Both Compose configurations | Passed | Valid syntax, service definitions, merged dependencies and GPU settings |
| Backend dependency resolution | Passed after packaging fix | Compatible package constraints for the chosen target environment; 124 versions recorded |
| Patch application | Passed | Patch applies to the exact pinned original handler and arguments; patched method bodies were exercised |
| Python/JavaScript syntax | Passed | New Python modules compile; edited JS parses |
| Full Docker image build / GPU inference | Not run | No Docker daemon or GPU in this environment |
| Visual UI / real mic and speaker | Not run | Browser tool returned `ERR_BLOCKED_BY_CLIENT` for the local app |
| Physical Reachy Mini | Not run | No robot, robot adapter or trained reference checkpoint supplied |

The Python suite emitted three deprecation warnings from existing FastAPI/
Starlette lifecycle APIs. They did not fail the tests. GPU model loading is not
mocked into a claim of inference success: tests exercise the patch's unchanged
method bodies with lightweight transport fixtures instead.

## Remaining acceptance on the target machine

1. Follow README startup commands and wait for backend and UI health.
2. Run `scripts/smoke_realtime.py` using the documented `docker compose exec`
   command. It requests a real reply and saves `voices/captain-smoke.wav`.
3. Listen for the desired Captain voice. Replace the reference if its texture
   does not match the intended performance.
4. Speak the test languages in the browser, switch languages mid-session,
   interrupt a reply, and reconnect. Check both intelligibility and perceived
   speaker consistency. The prompt and language plumbing do not guarantee
   perfect language detection or accent consistency. The pinned Parakeet handler
   retains its previous language for transcripts shorter than 20 characters
   (English initially); start and switch with a full sentence.
5. Measure time to first audio and peak GPU memory on the intended hardware.
   OmniVoice produces sentence batches before playback; no low-latency claim
   has been established here.
6. For Reachy, connect and verify the actual microphone/speaker adapter and
   sample-rate handling. Robot tool calling is a separate integration: this
   demo exposes no robot movement executor.

There was no training run, training configuration or known-good robot build in
the attachment, so this is a comparison against the supplied implementation and
pinned upstream source, not a comparison against “the one we trained.”

## Delivery and source references

The ZIP contains the modified UI, two Compose files, backend Dockerfile,
launch/reference/smoke scripts, patches, dependency lock, tests, this report and
the original reference material. It excludes installed dependencies, caches,
credentials, model weights and synthetic audio test fixtures generated during
execution. First launch creates the reference recording on the GPU host.

- [Pinned speech-to-speech source](https://github.com/huggingface/speech-to-speech/tree/ca5c33c9bb5e381288d315d1f8da122613845c4c) supports the CLI and handler comparisons above.
- [vLLM-Omni v0.28.0 installation](https://github.com/vllm-project/vllm-omni/blob/v0.28.0/docs/getting_started/installation/gpu/cuda.inc.md) identifies the optional image and its CUDA 13.0 dependency.
- [vLLM-Omni OmniVoice adapter](https://github.com/vllm-project/vllm-omni/blob/v0.28.0/vllm_omni/entrypoints/openai/tts_adapters/omnivoice.py) accepts reference audio, transcript and language.
- [OmniVoice model card](https://huggingface.co/k2-fsa/OmniVoice) documents cloning, 24 kHz output and the separate CC-BY-NC model-weight license. Commercial deployment suitability remains a license question; this package does not grant it.
