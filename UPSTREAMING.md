# Upstream review package

The runtime remains pinned to `ca5c33c9bb5e381288d315d1f8da122613845c4c`.
Two independent diffs in `patches/upstream/` were generated and applied against
`speech-to-speech` main at `a6576590f2a63f0d7c090e306422d86e0e1756ce` on 2026-09-23.
The four touched source files are identical at the runtime pin and that main
revision; no semantic conflict resolution was necessary. `git diff --check`
passed. Recheck against main again when submitting.

## Proposed PR 1 — Clone references for OpenAI-compatible TTS

Problem: remote speech synthesis cannot preserve a configured cloned speaker
or select its per-language recording if the handler forwards only named voices.

Changes: add optional reference audio/text arguments, forward turn language,
load a directory of reference pairs once, and choose exact language, base language
or configured default per request. Optional reference base URLs support a TTS
server with a different media mount. Reject incomplete or ambiguous reference
pairs at setup. Configured clones retain the server's voice selector when a
Realtime client sends a speaker preset from another TTS model; ordinary preset
selection remains unchanged when no clone is configured.

Validation: `tests/test_tts_patch.py` applies the actual patch to exact upstream
source and executes its methods without GPU imports, including the real process
path, mixed-language fallback, bad configuration and client-preset precedence.
The tests currently live in this demo; adapt them to upstream's normal handler
fixtures before opening the PR. A live vLLM-Omni run is still outstanding.

## Proposed PR 2 — Per-language OmniVoice clone prompts

Problem: using one source-language recording for every target language can carry
the source accent across languages.

Changes: add optional `omnivoice_ref_voices_dir`, create one prompt per reference
at startup, and select exact/base language per utterance with the default prompt
as fallback. This is the existing handoff patch, preserved and checked on main.
Its startup cost and additional prompt memory should be called out in review.

Validation: source patch application and launcher/reference tests pass. The
original handoff reported EN/FR log/smoke validation on its GPU. Broad listening
review and current GPU regression are still pending. Unlike the remote patch,
this handoff patch warns and skips a missing per-language transcript when used
outside the demo launcher; ask maintainers whether upstream should fail instead.

## Review workflow

Use separate clean branches from the inspected main revision and apply one file
from `patches/upstream/` on each, or combine them if Andi prefers. Keep the demo UI,
voice recordings and `omnivoice-dependencies.patch` out of these feature PRs.
That dependency workaround belongs to the pinned demo build and needs its own
upstream dependency review if still relevant.

No repository was pushed and no PR was opened. The reviewable diffs and proposed
PR scope are complete; repository ownership and submission destination remain
for Andi/the project owner to choose.
