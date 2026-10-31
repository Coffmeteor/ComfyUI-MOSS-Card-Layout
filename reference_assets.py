"""Verified, shared face-landmarker dependency for reference framing."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import threading
import urllib.request

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
MODEL_BYTES = 3758596
_LOCK = threading.Lock()


def default_model_path() -> Path:
    import folder_paths

    override = os.environ.get("MOSS_FACE_LANDMARKER_MODEL")
    return (
        Path(override).expanduser()
        if override
        else Path(folder_paths.models_dir) / "mediapipe" / "face_landmarker.task"
    )


def ensure_landmarker(path: Path) -> Path:
    """Fetch one pinned public model, atomically, only when reference framing runs."""

    def valid(candidate):
        if not candidate.is_file() or candidate.stat().st_size != MODEL_BYTES:
            return False
        with candidate.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest() == MODEL_SHA256

    with _LOCK:
        if valid(path):
            return path
        if path.exists():
            raise ValueError(
                f"Face-landmarker checksum mismatch: {path}. Keep your file and set MOSS_FACE_LANDMARKER_MODEL to the verified model."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with urllib.request.urlopen(MODEL_URL, timeout=60) as response:
                data = response.read(MODEL_BYTES + 1)
            if (
                len(data) != MODEL_BYTES
                or hashlib.sha256(data).hexdigest() != MODEL_SHA256
            ):
                raise ValueError(
                    "Face-landmarker download failed size/SHA-256 verification"
                )
            with tempfile.NamedTemporaryFile(
                dir=path.parent, suffix=".download", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return path
