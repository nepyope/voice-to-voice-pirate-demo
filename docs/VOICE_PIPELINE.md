# How the Painty reference clips were made

This documents how `voices/pirate_ref.wav` (English) and `voices/langs/<lang>.wav` (30 dubs)
were cut from two SpongeBob theme-song recordings on 2026-09-22. The output of this process
is in the repo; the scripts were written ad hoc in `/tmp` and lost on reboot, so this is the
recipe to rebuild them. `voices/langs/manifest.json` holds the exact result: per language
the block index, the source time spans in the separated-vocals track, and the transcript.

Everything ran on the RTX 5090 laptop. GPU steps ran inside the demo's backend image
(`docker compose run --rm --no-deps -v /tmp/work:/work s2s …`) because it already has
CUDA PyTorch; CPU steps ran in a throwaway `uv venv` with `faster-whisper soundfile numpy scipy`.

## Inputs

| File | Content | Length |
| --- | --- | --- |
| `SpongeBob SquarePants Theme Song (NEW HD) … Nick Animation.mp3` | English intro, one take | 66 s |
| `SpongeBob Theme Song in 27 Different Languages! 🌎 SpongeBob.mp3` | 29 dubs back to back (the title says 27) | ~20 min |

Both were downloaded from YouTube by the user (the official Nickelodeon uploads are geo-blocked
for `yt-dlp` from Austria). They are Nickelodeon IP: internal demo use only, which is why this
repository is private.

## Target format

OmniVoice clone reference: mono, 24 kHz, PCM16, 3–10 s recommended, **exact** transcript of the
audio. The launcher accepts up to 20 s (`scripts/voice_files.py`). Painty's lines alone are
~15 s in English, so the English default is 16.5 s; the dubs were cut to ~10–12 s.

What makes a good reference here: only the pirate (Painty) speaking, no kids' chorus, no music,
and a transcript that matches. The theme song interleaves Painty's call with the kids'
response ("Aye aye, Captain!", "SpongeBob SquarePants!"), so every Painty line has to be cut
*just before* the kids come in.

## Step 1 — decode and separate vocals from music

```bash
ffmpeg -i input.mp3 -ac 2 -ar 44100 src.wav
# in the backend container (has torch+CUDA); demucs is a pip install away
pip install demucs
python -m demucs --two-stems=vocals -n htdemucs_ft -d cuda -o sep src.wav
# → sep/htdemucs_ft/src/vocals.wav  (music removed), sep/htdemucs_ft/src/no_vocals.wav
```

`htdemucs_ft` is the fine-tuned 4-source Hybrid Transformer Demucs; `--two-stems=vocals` gives
vocals vs. everything else. Ukulele/accordion/waves are gone from the result; the kids'
chorus is *not*, since it's vocals too. Both source files got this treatment. A first version
of the English clip was cut from the un-separated mix ("painty_all_with_music" in
`voices/candidates/`); the separated one was preferred after listening.

## Step 2 (English) — find Painty's lines with word timestamps

```python
from faster_whisper import WhisperModel
m = WhisperModel("small.en", device="cpu", compute_type="int8")
segs, _ = m.transcribe("vocals.wav", word_timestamps=True, vad_filter=False, beam_size=5)
for s in segs:
    for w in s.words: print(f"{w.start:.2f}-{w.end:.2f} {w.word}")
```

From the word list, seven Painty spans, each ending before the kids' response:

| Span (s) | Text |
| --- | --- |
| 0.72–2.55 | Are you ready, kids? |
| 4.36–5.82 | I can't hear you! |
| 7.92–13.05 | Oh! Who lives in a pineapple under the sea? |
| 15.08–17.00 | Absorbent and yellow and porous is he! |
| 18.76–20.98 | If nautical nonsense be something you wish! |
| 22.72–25.08 | Then drop on the deck and flop like a fish! |
| 26.26–26.68 | Ready? |

Painty's laugh at ~36–40 s was excluded on purpose: it isn't speech and confuses cloning.

## Step 3 (English) — splice

```python
import soundfile as sf, numpy as np
from scipy.signal import resample_poly
x, sr = sf.read("sep/htdemucs_ft/src/vocals.wav", dtype="float32")
if x.ndim > 1: x = x.mean(1)
gap  = np.zeros(int(0.2 * sr), np.float32)         # 200 ms between lines
fade = int(0.012 * sr)                              # 12 ms fade in/out per cut
parts = []
for a, b, _ in lines:                               # the table above
    seg = x[int(a*sr):int(b*sr)].copy()
    seg[:fade] *= np.linspace(0, 1, fade); seg[-fade:] *= np.linspace(1, 0, fade)
    parts += [seg, gap]
y = np.concatenate(parts[:-1])
y = resample_poly(y, 24000, sr)
y = (0.9 * y / np.abs(y).max()).astype(np.float32)  # peak-normalize to -0.9 dBFS-ish
sf.write("pirate_ref.wav", y, 24000, subtype="PCM_16")
open("pirate_ref.txt", "w").write(" ".join(t for *_, t in lines) + "\n")
```

Result: 16.54 s, sha256 `b90cd394…` (the fallback for languages without their own clip).

## Step 4 (dubs) — locate the 29 language blocks

First attempt, cross-correlating the instrumental (`no_vocals.wav`) against the English block
to find repeats, **failed**: every dub is its own mix (different tempo/key/arrangement), not the
same instrumental with new vocals.

What worked: run `faster-whisper small` (multilingual) over the whole vocals track once, look at
where the recognizable "are you ready / I can't hear you" lines land, and notice the blocks sit
on a fixed grid because the compilation editor spaced them evenly:

```
block_start(k) = 81.78 + 40.804 * k      for k = -1 … 28      (seconds, in the 20-min file)
```

k = −1 is the first dub (es-419) at 41.0 s; the intro before it is not a theme. Residuals of
whisper-detected onsets against this grid were ±0.5 s, good enough to cut each block with a
0.6 s margin before and 0.3 s after.

Whisper's per-file language detection is useless on a 27-language file (it tagged everything
`es`), hence the per-block pass next.

## Step 5 (dubs) — transcribe each block on GPU

```python
import whisper, soundfile as sf, json                # openai-whisper, in the backend container
x, sr = sf.read("/work/vocals16.wav", dtype="float32")   # vocals resampled to 16 kHz mono
model = whisper.load_model("large-v3", device="cuda")
a, b = 81.78, 40.804
blocks = []
for k in range(-1, 29):
    t0 = a + b*k - 0.6; t1 = t0 + b + 0.3
    seg = x[int(max(0, t0)*sr):int(t1*sr)]
    r = model.transcribe(seg, word_timestamps=True, fp16=True,
                         condition_on_previous_text=False, temperature=0.0)
    blocks.append({"k": k, "t0": t0, "lang": r["language"],
                   "segments": [{"start": t0+s["start"], "end": t0+s["end"], "text": s["text"],
                                 "words": [{"w": w["word"], "s": t0+w["start"], "e": t0+w["end"]}
                                           for w in s.get("words", [])]} for s in r["segments"]]})
json.dump(blocks, open("/work/blocks.json", "w"), ensure_ascii=False)
```

`large-v3` needs ~6 GB; the demo's `s2s` had to be stopped to make room. `temperature=0.0`
and `condition_on_previous_text=False` reduce hallucination on sung material. Manual
corrections to the detected language: block 7 tagged `sl` is Serbian → `sr`; block 21 tagged
`sk` is Croatian → `hr`. Two Spanish blocks: Spain kept as `es`, Latin America as `es-419`.
No English or Italian block exists in the compilation (English falls back to `pirate_ref.wav`).

## Step 6 (dubs) — separate Painty from the kids, cut, splice

For each block, classify whisper segments as **kids** if either:

- the normalized text (lowercased, punctuation stripped) occurs two or more times within the
  block — the chorus repeats the localized SpongeBob name and the "aye aye" answer, Painty
  never repeats himself; or
- the segment midpoint falls in a kids' time slot relative to the block onset. Slots were
  derived from the English structure (Painty call ≈ 0–1.9 s, kids ≈ 2.4–3.2 s, Painty ≈
  3.6–5.1 s, kids ≈ 5.6–6.5 s, then sung verse/chorus alternation) and hold within ±0.5 s
  across dubs because the melody forces the timing.

Everything else is Painty. Segments that whisper merged across a slot boundary (common in
Korean/Chinese) are trimmed at the **word** level to the end of the Painty slot. Segments are
concatenated in time order until the clip reaches ~10–12 s; the transcript is the segment text
when all its words are kept, otherwise the kept words re-joined (no spaces for `zh`/`ja`/`th`,
and `J 'ai` / `într -un` style apostrophe/hyphen splits repaired with a regex).
Fades, gaps, resampling and normalization are identical to the English splice.

Known imperfections, all left as-is:

- Whisper's transcripts of the **sung** verses are approximate in several languages (e.g. German
  "Wer wohnt in der anderen…"). OmniVoice tolerates transcript errors reasonably; if a language
  sounds off, trim its `.wav`/`.txt` to the two spoken lines.
- Greek (`el`) whisper hallucinated subtitle-credit text for the whole sung part, so `el` is
  only the two spoken lines (3.5 s).
- Japanese has a short usable pirate span; it is under 3 s in some cuts and was kept only where
  it passed validation.
- Only Parakeet's 25 European languages are ever selected at runtime; `ar ja ko th ta te tr zh`
  are present but unreachable through STT.

## Step 7 — install and validate

```bash
cp langs/*.wav langs/*.txt langs/manifest.json voices/langs/
cp langs/en.wav voices/pirate_ref.wav; cp langs/en.txt voices/pirate_ref.txt
python3 - <<'EOF'
import sys; sys.path.insert(0, "scripts"); from pathlib import Path
from voice_files import validate_voice, validate_language_voices
print(validate_voice(Path("voices"))["seconds"], len(validate_language_voices(Path("voices/langs"))))
EOF
docker compose restart s2s     # rebuilds all clone prompts; ~30 s extra startup
```

`validate_*` enforce mono / 24 kHz / PCM16 / 3–20 s / non-silent / transcript present, and a
missing `.txt` fails the launch rather than silently skipping the language.

## To redo it for another character or a cleaner take

1. Get a recording where the target speaker has ≥ 5 s of clean speech, ideally spoken not sung.
2. `demucs` if there is music. Skip if the recording is already clean.
3. Whisper with word timestamps; pick spans of only that speaker.
4. Splice with the snippet above; type the transcript by hand — it is worth the two minutes,
   whisper's lyrics are the weakest part of the current clips.
5. Replace `voices/pirate_ref.wav` + `.txt` (and `voices/langs/` for per-language clips),
   restart `s2s`.

Voice cloning of a real person or a copyrighted character needs the relevant consent/rights.
