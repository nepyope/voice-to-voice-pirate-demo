# Presenting the Captain demo to Andi

Lead with a short multilingual conversation, then show the reusable engineering
behind it. Frame the outcome as **a packaged OmniVoice pirate backend for the
Pollen/Reachy workflow, with both vLLM routes implemented and ready for GPU
validation**. Until that validation runs, do not describe vLLM as deployed.

## Why this framing fits

The project context strongly points to Andrés “Andi” Marafioti. His public
[GitHub profile](https://github.com/andimarafioti) identifies speech systems,
efficient inference and robotics-facing deployment among his work. He co-authored
[“Reachy Mini goes fully local”](https://huggingface.co/blog/local-reachy-mini-conversation),
which connects the robot to the same speech-to-speech Realtime endpoint.
My recommendation from that context: emphasize working integration, measured
behavior and small upstream contributions. Avoid spending the opening minutes
explaining the general STT → LLM → TTS concept he already works on.

## A five-minute walkthrough

| Time | Show | Point to make |
| --- | --- | --- |
| 0:00–0:30 | The Captain UI or the actual Reachy client | “This packages your multilingual pirate idea into a backend Pollen can run.” |
| 0:30–1:45 | English → French → German in one conversation | The reply follows the latest language and keeps the selected speaker; use full sentences. |
| 1:45–2:30 | One interruption and a reconnect | Demonstrate conversation behavior only if you have run and checked it. |
| 2:30–3:30 | Voice selector and inference modes in README | Original Captain is the default; both local and remote paths use exact/base/default reference selection. LLM and TTS can be served separately. |
| 3:30–4:15 | REPORT.md plus saved WAV/JSON from the GPU run | Separate proven protocol/configuration behavior from observed inference quality, latency and VRAM. |
| 4:15–5:00 | Two upstream diffs and Reachy profile | Ask for one GPU/robot validation slot and the preferred PR split. |

If no GPU is available for the meeting, present the implementation and test
evidence as a review. Use a previously recorded real demo only if it is clearly
identified as the earlier in-process configuration. Do not play test fixtures as
if they were synthesized outputs.

## The engineering points worth highlighting

- Remote TTS now chooses a per-language reference on every turn, with a stable
  fallback and protection against a client sending an unrelated speaker preset.
- The new LLM overlay and existing TTS overlay can be composed independently.
  Memory fractions are configurable; co-resident VRAM fit remains unmeasured.
- There is a native Reachy personality and endpoint configuration, checked with
  the app's current parser. Physical audio and movement are separate: the shipped
  personality enables no movement tools.
- The default uses the already-generated original Captain voice. A separate
  shareable export excludes the supplied cartoon dub recordings. Voice quality
  still deserves an audition, and the model's own license remains relevant.
- The two general-purpose voice changes are isolated as upstream review diffs.

## Be precise about the remaining work

Say: “The code and configuration checks pass. This environment has no Docker
engine, GPU or Reachy, so I have not claimed a new live inference result. The
remaining gate is running the supplied checks on the intended GPU, listening to
language changes, and verifying the physical client.”

The old handoff reported roughly 2.5 seconds to first audio and 17.8 GB VRAM on
its in-process setup. Those numbers are historical, not current vLLM results.
For the new run, capture the hardware, voice, service mode and latency definition.
OmniVoice's vLLM path returns complete audio responses; position it as a shared
serving option to evaluate, not an established latency win. Thirty reference
clips also do not mean thirty languages were validated end to end.

## A message you can send

Andi — I filled in the implementation gaps in the pirate demo: remote OmniVoice
now uses per-language references, there’s a vLLM LLM overlay, an original Captain
voice option, and a Reachy connection/profile package. I also added audio-input
and direct-TTS checks that save the actual WAVs and timing results, and split the
general voice changes into upstream-ready diffs.

The code/protocol tests and all eight Compose combinations pass. The remaining
validation is on the GPU and an actual Mini; I haven’t claimed that vLLM is already
running. Could we do a short English/French/German run on a CUDA-13-compatible
host, then decide whether you want the local and remote voice patches as two PRs?

## Bring to the review

Use the shareable ZIP plus this guide and REPORT.md. After a GPU run, add three
short real conversation clips, their timing JSON, the model/image revisions and
an honest list of any poor pronunciations or interruption failures. Keep the
full private archive for reference; it contains the supplied third-party audio.
