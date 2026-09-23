# Reference voices

The default is `VOICE=captain`: `captain/pirate_ref.wav` and its exact transcript,
copied byte-for-byte from `previous-generated-captain/` in the supplied archive.
`captain/reference.json` records generation provenance and its SHA-256. It was
not regenerated or listening-tested during this implementation pass.

`VOICE=painty` selects the supplied top-level `pirate_ref.*` and `langs/` directory.
These recordings and transcripts are retained for continuity in the complete
bundle, and are excluded from the shareable export. Their source spans and transcripts
are in `langs/manifest.json`; how they were cut (demucs separation, whisper word
timestamps, block grid, pirate-vs-kids split, splice) is in
[`docs/VOICE_PIPELINE.md`](../docs/VOICE_PIPELINE.md). Inclusion here does not
establish redistribution rights.

`VOICE=custom` uses `custom/pirate_ref.wav` and `custom/pirate_ref.txt`. Add optional
`custom/langs/<language>.wav` and matching `.txt` pairs to use localized references.
Do not mix speakers under one preset if the goal is consistent identity.

All reference pairs are checked for mono 24 kHz PCM16, 3–20 seconds, non-silent
complete data and a non-empty transcript. Transcription accuracy and perceptual
voice quality still require listening. Both TTS paths choose exact language,
then base language, then the active preset's default. Unsupported STT languages
are not enabled by adding a voice reference.
