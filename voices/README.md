# Reference voices

Painty the Pirate, cloned from the SpongeBob theme song (music removed):

- `pirate_ref.wav` + `pirate_ref.txt`: the English reference, also used for any
  language without its own clip.
- `langs/<code>.wav` + `<code>.txt`: one reference per dub (29 languages), so each
  reply takes on that dub's accent. `langs/manifest.json` records the source spans.

How the clips were cut (demucs separation, whisper word timestamps, block grid,
pirate-vs-kids split, splice) is in [`docs/VOICE_PIPELINE.md`](../docs/VOICE_PIPELINE.md).
The source audio is Nickelodeon IP; keep this repository private.

Every pair is checked at startup: mono 24 kHz PCM16, 3–20 seconds, non-silent, with
a non-empty transcript. For each reply the backend picks the clip for the detected
language, then its base language (`es-419` → `es`), then `pirate_ref.wav`. Adding a
clip does not add STT support: Parakeet recognizes 25 European languages.
