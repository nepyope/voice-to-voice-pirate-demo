# Current handoff — Captain implementation

Start with [README.md](README.md). The supplied earlier handoff is preserved as
[reference/handoff-before-completion.md](reference/handoff-before-completion.md).

| Original work item | Current state |
| --- | --- |
| A1: remote language references | Implemented in `remote-voice.patch`, with actual patched-method tests |
| A1: vLLM-Omni on GPU | **Validated 2026-09-23** on driver 580: clone via `ref_audio`, per-language FR reference, end-to-end EN/FR/ES — see [GPU_VALIDATION_2026-09-23.md](GPU_VALIDATION_2026-09-23.md) |
| A2: LLM on vLLM | **Validated 2026-09-23** alone and combined with the TTS overlay (image pinned to v0.29.0-cu129) |
| B: original/default voice selection | Original generated Captain is bundled and default; `VOICE` selects isolated presets; candidate generation remains a GPU task |
| B: broad listening/transcript cleanup | Not performed; supplied recordings/transcripts preserved |
| C: Reachy connection | Port overlay, verified environment setup and native profile supplied; actual robot run still pending |
| D: upstream feature patches | Checked on current main, two diffs and review scope prepared; no repo push/PR |
| E: cache, ignored assets and stale metadata | Torch cache persisted; original Captain tracked; third-party references excluded by shareable exporter; metadata and docs reconciled |

`REPORT.md` records 58 passing Python tests, 7 JavaScript tests and 8 valid
Compose configurations. `VALIDATION.md` describes the remaining GPU/listening
and robot gates. `PRESENTING_TO_ANDI.md` contains the review plan.

The complete ZIP retains the user's supplied audio collection. The shareable
ZIP excludes third-party recordings and transcripts and uses the original
Captain reference. Model licensing is separate from voice selection.
