"""Check/apply the exact validated MOSS core extension; never run on import."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(root: Path) -> list:
    contract = json.loads((PACKAGE / "resources/reference-core.json").read_text())
    plan = []
    for entry in contract["files"]:
        path = (root / entry["path"]).resolve(strict=True)
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Core file resolves outside ComfyUI")
        original = path.read_bytes()
        actual = digest(original)
        if actual == entry["patched_sha256"]:
            plan.append((path, original, original))
            continue
        if actual != entry["base_sha256"]:
            raise ValueError(
                f"Unsupported or locally modified core file: {entry['path']}. Expected stock ComfyUI v0.43.0 or this exact installed patch. No files changed."
            )
        lines = original.decode().splitlines(keepends=True)
        for edit in reversed(entry["edits"]):
            if "".join(lines[edit["start"] : edit["stop"]]) != edit["before"]:
                raise ValueError("Core patch context mismatch")
            lines[edit["start"] : edit["stop"]] = edit["after"].splitlines(
                keepends=True
            )
        patched = "".join(lines).encode()
        if digest(patched) != entry["patched_sha256"]:
            raise ValueError("Core patch result checksum mismatch")
        plan.append((path, original, patched))
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-root", type=Path, default=PACKAGE.parent.parent)
    parser.add_argument(
        "--apply", action="store_true", help="Apply after preflight; stop ComfyUI first"
    )
    args = parser.parse_args()
    plan = prepare(args.comfy_root)
    changed = []
    try:
        for path, original, patched in plan:
            if original == patched:
                print(
                    f"Already installed: {path.relative_to(args.comfy_root.resolve())}"
                )
                continue
            print(
                f"{'Applying' if args.apply else 'Would apply'}: {path.relative_to(args.comfy_root.resolve())}"
            )
            if args.apply:
                backup = path.with_name(path.name + ".moss-studio-original")
                if backup.exists() and backup.read_bytes() != original:
                    raise ValueError(f"Conflicting backup: {backup}")
                backup.write_bytes(original)
                changed.append((path, original))
                path.write_bytes(patched)
                if path.read_bytes() != patched:
                    raise OSError(f"Write verification failed: {path}")
    except Exception:
        for path, original in reversed(changed):
            path.write_bytes(original)
        raise
    print(
        "Reference support verified."
        if args.apply or all(a == b for _, a, b in plan)
        else "Preflight passed. Stop ComfyUI and add --apply, then restart."
    )


if __name__ == "__main__":
    main()
