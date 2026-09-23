"""Check a GPU host before launch. Uses Docker's actual merged configuration.

No models are loaded, no services started, and no host drivers changed. Image
inspection is optional and requires registry access. An OK report establishes
prerequisites only; run the smoke scripts to establish inference behavior.
"""
import argparse
import json
import platform
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from voice_files import validate_language_voices, validate_voice, voice_directory

ROOT = Path(__file__).resolve().parents[1]
MODES = {"local": [], "vllm-llm": ["compose.llm-vllm.yaml"],
         "vllm-tts": ["compose.vllm.yaml"],
         "vllm": ["compose.vllm.yaml", "compose.llm-vllm.yaml"]}


def compose_command(mode, reachy=False):
    files = ["compose.yaml", *MODES[mode], *(["compose.reachy.yaml"] if reachy else [])]
    return ["docker", "compose", *[v for name in files for v in ("-f", name)]]


def version_tuple(value):
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", value)
    if not match:
        raise ValueError("Unrecognized version")
    return tuple(int(n or 0) for n in match.groups())


def driver_issues(driver, services):
    """Conservative rules for this package's default CUDA images, not all GPUs."""
    major = version_tuple(driver)[0]
    problems, warnings = [], []
    if major < 570:
        problems.append("The CUDA 12.8 backend targets driver 570 or newer; upgrade on the GPU host.")
    if "tts" in services:
        image = services["tts"]["image"]
        if image == "vllm/vllm-omni:v0.28.0" and major < 580:
            problems.append("The default vLLM-Omni image uses CUDA 13; use driver 580+ or a separately validated CUDA 12 build.")
        elif image != "vllm/vllm-omni:v0.28.0":
            warnings.append("Custom TTS image: verify its CUDA/driver and OmniVoice compatibility separately.")
    if "llm" in services:
        image = services["llm"]["image"]
        if image == "vllm/vllm-openai:v0.30.0-cu129" and major < 575:
            warnings.append("CUDA 12.9 LLM on a pre-575 driver relies on minor compatibility; PTX/JIT may fail. Validate inference or upgrade.")
        elif image != "vllm/vllm-openai:v0.30.0-cu129":
            warnings.append("Custom LLM image: verify its CUDA/driver compatibility separately.")
    return problems, warnings


def check(mode="local", reachy=False, check_images=False):
    report = {"mode": mode, "ready_for_launch": False, "errors": [], "warnings": [], "checks": {}}
    errors, warnings, checks = report["errors"], report["warnings"], report["checks"]
    command = compose_command(mode, reachy)

    def run(argv, timeout=30):
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            # Compose diagnostics may contain interpolated credentials. Do not copy them into evidence.
            raise ValueError(f"{shlex.join(argv[:3])} failed (exit {result.returncode}); inspect it on the host")
        return result.stdout

    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        errors.append("This package targets a Linux x86_64 NVIDIA GPU host.")
    checks["free_disk_gib"] = round(shutil.disk_usage(ROOT).free / 2**30, 1)
    if checks["free_disk_gib"] < 40:
        warnings.append("Less than 40 GiB disk is free; images and model caches can require tens of GiB.")
    if not shutil.which("docker"):
        errors.append("Docker is not installed or is not on PATH.")
        services = {}
    else:
        try:
            version = run(["docker", "compose", "version", "--short"]).strip()
            checks["compose_version"] = version
            if version_tuple(version) < (2, 30, 0):
                errors.append("Docker Compose 2.30+ is required for gpus configuration.")
            run(["docker", "info", "--format", "{{.ServerVersion}}"])
            config = json.loads(run(command + ["config", "--format", "json"]))
            services = config["services"]
            checks["compose_services"] = sorted(services)
            env = dict(services["s2s"].get("environment", {}))
            env["VOICES_DIR"] = str(ROOT / "voices")
            voice = validate_voice(voice_directory(env))
            langs = Path(voice["audio"]).parent / "langs"
            checks["voice"] = {"preset": env.get("VOICE", "captain"), "sha256": voice["sha256"],
                               "language_references": sorted(validate_language_voices(langs)) if langs.exists() else []}
            if not env.get("LLM_BASE_URL") and "llm" in services:
                errors.append("LLM overlay is active but the backend has no LLM_BASE_URL.")
            fractions = []
            for name in ("llm", "tts"):
                if name in services:
                    args = services[name]["command"]
                    fraction = float(args[args.index("--gpu-memory-utilization") + 1])
                    if not 0 < fraction < 1:
                        errors.append(f"{name} GPU memory fraction must be between 0 and 1.")
                    fractions.append(fraction)
                    if check_images:
                        run(["docker", "manifest", "inspect", services[name]["image"]], timeout=60)
            if sum(fractions) >= 0.9:
                warnings.append("vLLM memory fractions leave little room for STT, CUDA overhead, and other processes.")
            if check_images:
                checks["image_manifests"] = "available"
        except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
            errors.append(str(exc))
            services = {}
    if not shutil.which("nvidia-smi"):
        errors.append("nvidia-smi is unavailable; run this check on the GPU host.")
    else:
        try:
            rows = run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.free", "--format=csv,noheader,nounits"])
            checks["gpus"] = []
            for row in rows.strip().splitlines():
                name, driver, total, free = [value.strip() for value in row.split(",")]
                checks["gpus"].append({"name": name, "driver": driver, "total_mib": int(total), "free_mib": int(free)})
                issues, notes = driver_issues(driver, services)
                errors.extend(issues)
                warnings.extend(notes)
            if not checks["gpus"]:
                errors.append("No NVIDIA GPUs were found.")
            elif checks["gpus"][0]["free_mib"] < 20 * 1024:
                warnings.append("GPU 0 has less than 20 GiB free; reduce allocations or move the LLM to a remote host.")
        except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
            errors.append(str(exc))
    warnings.append("Preflight does not load CUDA inside containers or measure VRAM fit. Run the inference checks after startup.")
    report["ready_for_launch"] = not errors
    report["launch_command"] = shlex.join(command + ["up", "-d", "--build"])
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=MODES, default="local")
    parser.add_argument("--reachy", action="store_true")
    parser.add_argument("--check-images", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check(args.mode, args.reachy, args.check_images)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    raise SystemExit(0 if result["ready_for_launch"] else 1)
