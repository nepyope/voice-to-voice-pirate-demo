# Deployment acceptance

Automated source tests are recorded in `validation/`; they use deterministic
protocol fixtures and do not establish GPU inference or perceived voice quality.
Run the following on the target host before presenting a live result.

## Host and inference

1. Run `scripts/preflight.py` for the chosen mode. The default vLLM-Omni image
   needs a CUDA-13-compatible driver (580+). Verify Container Toolkit with the
   real containers; preflight's host checks are not a CUDA kernel test.
2. Start that mode and wait for API health. Capture `docker compose ps -a`, image
   digests, `nvidia-smi`, model revisions and the exact `.env` settings **with
   tokens removed**. Keep those alongside the WAV/JSON smoke artifacts.
3. For remote TTS, run `smoke_tts.py` with EN and FR using the selected preset.
   For `VOICE=painty`, confirm the returned evidence selects `langs/fr.wav` for
   French. For Captain, confirm the default Captain reference is used for both.
4. Run `smoke_realtime.py` once with text, then with recorded speech. Use complete
   sentences longer than a greeting; save English/French/German speech inputs
   and replies. The audio test requires a final STT transcript before passing.
5. Listen to every saved reply. Check intelligibility, intended response language,
   stable perceived character and clipped/truncated speech. Listen to suspicious
   dub references and correct their transcripts or trim spoken lines before
   claiming broad voice quality. A valid file does not establish these properties.

## Browser and robot

Use one conversation and switch languages on consecutive turns. Example inputs:

| Language | Spoken input | What to verify |
| --- | --- | --- |
| English | Captain, where should we sail to find our next treasure? | Brief useful English answer and pirate character |
| French | Capitaine, raconte-moi comment nous allons trouver le trésor. | Switch to natural French on this turn |
| German | Kapitän, welches Abenteuer erwartet uns auf der nächsten Insel? | Switch to German without keeping the French language |

Interrupt a long reply midway. Check that playback stops, the new utterance is
recognized and stale speech does not resume. End and reconnect five times;
watch for a held pipeline, missing audio, or a growing VRAM allocation. Repeat
through the physical Reachy microphone/speaker using its local backend setting.
Any failure belongs in the demo notes, not in an unqualified success claim.

## Latency and capacity

Record at least five warm turns per configuration. Compare identical prompts,
voice preset and hardware. Report the median and worst observed time from
**server speech-stop to first audio**, alongside raw JSON. Text-request latency
starts earlier in a different flow and should be labeled separately. Cold start,
utterance duration, silence padding and model load time are different metrics.

Only claim multi-robot capacity after setting `NUM_PIPELINES`, running that many
simultaneous real clients and checking VRAM, queueing, failures and per-session
latency. The vLLM overlays and configurable pool enable that experiment; there
is no throughput benchmark in this package.

## Current evidence boundary

| Area | This revision |
| --- | --- |
| Python and JavaScript code/protocol tests | Passed; see REPORT.md |
| Eight Compose configurations | Validated by actual Compose parser without a daemon |
| Upstream patch application | Passed against runtime pin and inspected main revision |
| Reachy profile format | Passed using upstream parser; no hardware |
| Local GPU inference | Original handoff reports a prior run; not rerun here |
| vLLM GPU inference, VRAM fit, real audio | Pending GPU-host execution |
| Physical Reachy, listening, interruption | Pending hardware/person review |
