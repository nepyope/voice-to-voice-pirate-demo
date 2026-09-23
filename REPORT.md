# Implementation report — 2026-09-23

The software gaps from the attached handoff are implemented and packaged. The
new revision is validated at code, protocol, configuration and profile-parser
levels. Live vLLM inference and physical Reachy validation remain outstanding
because this workspace has no Docker daemon, NVIDIA GPU or robot.

## Changes

| Handoff gap | Delivered implementation |
| --- | --- |
| Remote per-language voices | Extended the real upstream HTTP TTS handler patch: per-request exact/base/default selection; startup validation; alternate remote media base URL; fixed-language override; configured clone precedence over client presets. |
| vLLM LLM | Independent `compose.llm-vllm.yaml` with pinned CUDA-12.9 vLLM image, health dependency, 4K context, eager mode and adjustable memory. Combines with local or remote TTS. |
| Original voice/default selector | `VOICE=captain\|painty\|custom`, isolated reference directories, bundled original Captain from the handoff, selectable custom reference, and non-overwriting candidate-generation arguments. |
| vLLM deployment blocker | `preflight.py` checks resolved configuration, host Docker/GPU/driver, reference integrity and optional image availability. It identifies the known CUDA-13/driver-570 mismatch; it does not upgrade the host. |
| Inference acceptance | Direct-TTS and text/audio Realtime clients save actual WAVs and JSON timings, reject failed/incomplete/cancelled/silent results, and require a final STT transcript for the audio route. |
| Reachy | Backend port overlay, verified local-endpoint environment keys and a native Captain profile. Parser validated against current app source; audio-only tools policy is explicit. |
| Upstreaming | Two independent patches generated against current main and review descriptions in UPSTREAMING.md. No public push or PR. |
| Operational cleanup | Persistent torch cache, mounted artifacts directory, updated ignore rules, current build metadata, historical documents retained, and manifest-generating shareable exporter. |

The original archive's Painty WAVs and transcripts were preserved. They are not
the new default. The shareable export includes only the original generated
Captain recording. No fresh voice generation, dub transcription correction or
listening review was possible here.

## Tests and evidence

- **58 Python tests passed**, including the actual patched handler methods and
  process path, language fallback, reference validation, remote path mapping,
  speaker preset precedence, HTTP/WAV checks, paced audio/STT protocol behavior,
  partial/cancelled response rejection, readiness and relay teardown.
- The extracted shareable ZIP also passed **57 Python tests**; the one test for
  optional private Painty assets was skipped. ZIP integrity, every manifest hash
  and exclusion of third-party audio were checked.
- **7 JavaScript tests passed** for endpoint construction, PCM framing/resampling
  and transcript behavior. No frontend code or styling was changed.
- **8 Compose combinations validated** with the actual standalone Docker Compose
  v2.30.3 parser: local, LLM-only vLLM, TTS-only vLLM and both, each with/without
  the Reachy overlay. A Docker daemon/container build was not involved.
- Both upstream patches apply cleanly to main
  `a6576590f2a63f0d7c090e306422d86e0e1756ce`; `git diff --check` passes. The four
  touched upstream files are unchanged relative to the pinned runtime revision.
- The native Reachy profile parser accepted the Captain profile at conversation
  app revision `b9f58a3587d79a3275d4402d1a8d210649d62d50`. No robot SDK/hardware run.
- All 30 supplied language reference pairs and both default references passed the
  package's WAV/transcript structure checks. This does not validate transcript
  accuracy, accent, intelligibility or speaker similarity.

Evidence is in `validation/`: pytest XML, Compose summaries, upstream/profile
receipts and this workspace's intentionally failing host preflight. The Python
run used Python 3.12; the Docker image still uses its pinned Python 3.11 stack.
Three inherited FastAPI/Starlette deprecation warnings did not fail the suite.

## Historical evidence versus this revision

`reference/handoff-before-completion.md` reports an earlier in-process run on a
24 GB RTX 5090 Laptop with driver 570, about 17.8 GB VRAM and about 2.5 seconds to
first audio for its scripted check. These are supplied historical observations,
not reproduced measurements, not vLLM results, and not guarantees for the newly
selected Captain default. The obsolete “nothing built/tested” statements in
prior documents are retained only under `reference/`.

## Remaining gates

1. Run preflight and actual containers on the target GPU. Default vLLM-Omni needs
   a driver compatible with CUDA 13 (580+); hardware upgrades are not code fixes.
2. Run the direct clone and speech-input tests in local and vLLM modes. Measure
   VRAM fit, cold/warm startup and latency; listen to EN/FR/DE before extending
   claims to additional languages. Re-audition the generic original Captain or
   generate candidates on the GPU.
3. Verify the physical Mini's microphone, playback, interruptions and reconnects.
   This delivery adds the connection/profile setup, not robot movement tools.
4. Choose an upstream submission destination and run the upstream project's
   required review checks. Patches and draft scope are ready; no PR is open.

See VALIDATION.md for the exact acceptance procedure and PRESENTING_TO_ANDI.md
for a five-minute walkthrough and a concise message.
