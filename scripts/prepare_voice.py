"""Generate ONE reference on first run; preserve it on every later run."""
import argparse
import json
import os
from pathlib import Path

from voice_files import validate_voice, voice_directory

REFERENCE_TEXT = "Arr, welcome aboard! I be the captain of this fine vessel. What adventure shall we seek today?"
# Only documented OmniVoice voice-design attributes. 'Hoarse' is not supported.
VOICE_DESCRIPTION = "male, elderly, very low pitch, british accent"


def prepare(directory: Path, description=VOICE_DESCRIPTION, seed=17, text=REFERENCE_TEXT):
    directory.mkdir(parents=True, exist_ok=True)
    audio = directory / "pirate_ref.wav"
    transcript = directory / "pirate_ref.txt"
    if audio.exists() or transcript.exists():
        details = validate_voice(directory)  # Never silently replace a supplied voice.
        print(f"Reusing Captain reference: {details['sha256']} ({details['seconds']}s)")
        return details

    import numpy as np
    import soundfile as sf
    import torch
    from omnivoice import OmniVoice
    from scipy.signal import resample_poly
    from math import gcd

    device = os.environ.get("VOICE_DEVICE", "cuda")
    torch.manual_seed(seed)
    model = OmniVoice.from_pretrained(os.environ.get("TTS_MODEL", "k2-fsa/OmniVoice"),
                                     device_map=device,
                                     dtype=torch.float32 if device == "cpu" else torch.float16)
    result = model.generate(text=text, language="en", instruct=description, num_step=32)
    waveform = result[0]
    if hasattr(waveform, "detach"):
        waveform = waveform.detach().cpu().numpy()
    waveform = np.asarray(waveform, dtype=np.float32).squeeze()
    if waveform.ndim != 1 or not np.isfinite(waveform).all():
        raise ValueError("Voice generator returned invalid audio")
    rate = int(model.sampling_rate)
    if rate != 24000:
        divisor = gcd(rate, 24000)
        waveform = resample_poly(waveform, 24000 // divisor, rate // divisor)
    if not 3 <= len(waveform) / 24000 <= 10:
        raise ValueError("Generated reference is outside 3–10s. Supply a suitable recording instead.")
    if np.max(np.abs(waveform)) < 0.001:
        raise ValueError("Voice generator returned silence")
    # Write temporary files first; a failed generation cannot poison the next boot.
    temp = directory / "pirate_ref.pending.wav"
    sf.write(temp, np.clip(waveform, -1, 1), 24000, subtype="PCM_16")
    text_temp = directory / "pirate_ref.pending.txt"
    text_temp.write_text(text + "\n", encoding="utf-8")
    temp.replace(audio)
    text_temp.replace(transcript)
    details = validate_voice(directory)
    (directory / "reference.json").write_text(json.dumps({**details, "origin": "generated",
        "model": os.environ.get("TTS_MODEL", "k2-fsa/OmniVoice"), "description": description,
        "seed": seed}, indent=2) + "\n", encoding="utf-8")
    print(f"Saved Captain reference: {details['sha256']} ({details['seconds']}s)")
    return details


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, help="Generate a separate candidate without overwriting the active preset")
    parser.add_argument("--description", default=VOICE_DESCRIPTION)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--text", default=REFERENCE_TEXT)
    args = parser.parse_args()
    directory = args.directory or voice_directory(os.environ)
    if args.directory or os.environ.get("VOICE", "captain") == "captain":
        prepare(directory, args.description, args.seed, args.text)
    else:
        # A named recording must never be silently replaced by a designed voice.
        details = validate_voice(directory)
        print(f"Validated {os.environ['VOICE']} reference: {details['sha256']}")
