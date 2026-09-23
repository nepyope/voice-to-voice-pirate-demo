"""Build a complete ZIP, or a shareable source ZIP without the supplied dub audio."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "artifacts", "pytest-of-root"}


def package(output: Path, public: bool = False):
    files = []
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if not path.is_file() or path.is_symlink() or any(part in SKIP_DIRS for part in relative.parts):
            continue
        if path.name in {".env", "MANIFEST.json"} or path.suffix in {".zip", ".log", ".pyc"}:
            continue
        if path.name.startswith(".env.") and path.name != ".env.example":
            continue
        if public and relative.parts[0] == "voices":
            if not (relative == Path("voices/README.md") or relative.parts[1] == "captain"):
                continue
        files.append((relative, path))
    manifest = {str(rel): hashlib.sha256(path.read_bytes()).hexdigest() for rel, path in files}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, path in files:
            archive.write(path, "voice-to-voice-pirate-demo/" + relative.as_posix())
        archive.writestr("voice-to-voice-pirate-demo/MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    return {"output": str(output), "files": len(files) + 1, "public_export": public,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "bytes": output.stat().st_size}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--public", action="store_true", help="Include only the original Captain voice preset")
    args = parser.parse_args()
    print(json.dumps(package(args.output, args.public), indent=2))
