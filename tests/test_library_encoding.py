"""Verify face library metadata on systems with a Windows ANSI default."""

from __future__ import annotations

import importlib
from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from unittest.mock import patch

from PIL import Image

PACKAGE = Path(__file__).resolve().parents[1]
namespace = ModuleType("moss_library_encoding_tests")
namespace.__path__ = [str(PACKAGE)]
sys.modules[namespace.__name__] = namespace
portraits = importlib.import_module(namespace.__name__ + ".portraits")
user_library = importlib.import_module(namespace.__name__ + ".user_library")


class LibraryEncodingTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(
            patch.object(user_library, "root", return_value=Path(directory))
        )
        original_open = Path.open

        def open_with_windows_default(
            path, mode="r", buffering=-1, encoding=None, **kwargs
        ):
            if "b" not in mode and encoding in (None, "locale"):
                encoding = "cp1252"
            return original_open(path, mode, buffering, encoding, **kwargs)

        self.enterContext(patch.object(Path, "open", open_with_windows_default))

    def test_official_face_can_be_listed_and_selected(self):
        expected = json.loads(portraits.CATALOG.read_bytes())["entries"]
        self.assertEqual(portraits.entries(), expected)
        face = expected[0]
        self.assertEqual(portraits.get(face["id"]), face)
        self.assertEqual(
            json.loads(portraits.MOSSFaceLibrary.IS_CHANGED(face_id=face["id"])), face
        )

    def test_personal_face_metadata_preserves_unicode(self):
        image = BytesIO()
        Image.new("RGB", (2, 2)).save(image, format="PNG")
        fields = {"label": "Élodie 顔", "description": "Oval face", "tags": ["写真"]}
        entry = user_library.create("faces", fields, image.getvalue())
        identifier = entry["id"]
        self.assertEqual(portraits.get(identifier), entry)
        self.assertEqual(portraits.entries()[0], entry)

        updated = user_library.update("faces", identifier, fields | {"label": "冬"})
        path = user_library.kind_root("faces") / identifier / "entry.json"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), updated)

    def test_legacy_ansi_entry_can_be_read_and_updated(self):
        identifier = "USER-" + "B" * 32
        fields = {"label": "Élodie", "description": "Oval face"}
        entry = {"id": identifier, **fields}
        path = user_library.kind_root("faces") / identifier / "entry.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(entry, ensure_ascii=False), encoding="cp1252")
        self.assertEqual(user_library.entries("faces"), [entry])
        self.assertEqual(portraits.get(identifier), entry)

        updated = user_library.update("faces", identifier, fields)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), updated)
