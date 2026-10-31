"""Reference prompt and authored workflow contracts, without loading models."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
from types import ModuleType
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
namespace = ModuleType("moss_studio_contract_tests")
namespace.__path__ = [str(PACKAGE)]
sys.modules[namespace.__name__] = namespace
contract = importlib.import_module(namespace.__name__ + ".prompt_contract")


class ReferencePromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.faces = json.loads(
            (PACKAGE / "resources/portrait-gallery.json").read_text()
        )["entries"]
        cls.outfits = json.loads(
            (PACKAGE / "resources/costume-gallery.json").read_text()
        )["entries"]

    def settings(self, **changes):
        return (
            dict(
                age_mode="From face selection",
                age=25,
                presentation="From face selection",
                body_shape="slim",
                hair_style="From face selection",
                hair_color="From face selection",
                expression="From face selection",
                extra_character_details="",
                reference_hair="",
                face_description=json.dumps(self.faces[0]["face_spec"]),
            )
            | changes
        )

    def build(self, *, outfit="SPR-0048", privacy=True, reference=True, **changes):
        entry = next(e for e in self.outfits if e["id"] == outfit)
        prompt, w, h = contract.compile_card(
            1536,
            864,
            privacy,
            json.dumps(self.settings(**changes)),
            json.dumps(entry["outfit_spec"]),
            entry["portrait_description"],
            "Soft even studio light",
            reference,
        )
        self.assertEqual((w, h), (1536, 864))
        return json.loads(prompt)

    def test_curated_face_inherits_separate_style_color_and_expression(self):
        caption = self.build()["items"][0]["caption"]
        face = self.faces[0]["face_spec"]
        for phrase in (
            "Keep the exact facial identity, eye shape, nose bridge, lip contour, and skin tone from reference image 1.",
            "Preserve the reference hairstyle.",
            "Preserve the reference hair color.",
            "Preserve the reference expression.",
            "Keep the reference eye color and gaze.",
        ):
            self.assertIn(phrase, caption)
        for text in (
            face["geometry"],
            face["hair"]["style"].rstrip(" ."),
            face["hair"]["color"].rstrip(" ."),
            face["expression"].rstrip(" ."),
        ):
            self.assertNotIn(text, caption)

    def test_raw_loadimage_allows_empty_face_and_generic_inheritance(self):
        for empty in ("", "   "):
            with self.subTest(empty=empty):
                caption = self.build(face_description=empty)["items"][0]["caption"]
                for field in ("hairstyle", "hair color", "expression"):
                    self.assertIn(f"Preserve the reference {field}.", caption)
        with self.assertRaisesRegex(ValueError, r"face_description is required\."):
            self.build(face_description="", reference=False)

    def test_explicit_overrides_replace_only_their_inheritance(self):
        old = self.build()
        new = self.build(
            hair_style="Pixie cut", hair_color="Blonde", expression="Serious"
        )
        self.assertEqual(old["summary"], new["summary"])
        self.assertEqual(old["items"][1:], new["items"][1:])
        caption = new["items"][0]["caption"]
        for phrase in (
            "Change the hairstyle to Pixie cut.",
            "Use Blonde hair color.",
            "Expression: Serious.",
        ):
            self.assertIn(phrase, caption)
        for field in ("hairstyle", "hair color", "expression"):
            self.assertNotIn(f"Preserve the reference {field}", caption)

    def test_pose_and_non_hat_outfit_normalize_headwear(self):
        caption = self.build()["items"][0]["caption"]
        self.assertIn(
            "Head upright, horizontal eye line, level shoulders, hands lowered completely out of frame.",
            caption,
        )
        self.assertIn(
            "Bare head with no hat, headwear, or hair accessories; complete natural hair crown with studio margin above.",
            caption,
        )

    def test_hat_outfit_retains_cloche_without_bare_head_instruction(self):
        card = self.build(outfit="SPR-0001")
        caption = card["items"][0]["caption"]
        self.assertRegex(caption, r"(?i)straw cloche hat")
        self.assertNotIn("Bare head", caption)
        self.assertIn("Head upright, horizontal eye line, level shoulders", caption)
        for item in card["items"][1:]:
            self.assertNotIn("cloche", item["caption"])
        self.assertIsNone(
            contract.HEADWEAR_RE.search("capsule blouse with capped sleeves")
        )

    def test_privacy_and_headless_triggers_remain_in_their_scopes(self):
        for privacy in (True, False):
            card = self.build(privacy=privacy)
            self.assertRegex(card["summary"]["caption"], r"\bprivacy\b")
            self.assertRegex(
                card["summary"]["caption"], r"\b(?:no head|headless|neckless)\b"
            )
            self.assertNotRegex(
                card["items"][0]["caption"],
                r"\bprivacy\b|\b(?:no head|headless|neckless)\b",
            )
            for item in card["items"][1:]:
                self.assertRegex(
                    item["caption"].lower(), r"\b(?:no head|headless|neckless)\b"
                )
            for item in card["items"][2:]:
                self.assertNotRegex(item["caption"], r"\bprivacy\b")
        on, off = self.build(), self.build(privacy=False)
        for i in (0, 2, 3):
            self.assertEqual(on["items"][i], off["items"][i])

    def test_skin_tone_defaults_are_backward_compatible_and_inherited_to_every_panel(
        self,
    ):
        old = self.settings()
        self.assertEqual(
            contract.validate_character(old)["skin_tone"], "From face selection"
        )
        self.assertEqual(self.build(), self.build(skin_tone="From face selection"))
        card = self.build()
        phrase = contract.resolve_skin_tone(old)
        self.assertIn(phrase, card["summary"]["caption"])
        for item in card["items"]:
            self.assertIn(phrase, item["caption"])
        for item in card["items"][1:]:
            self.assertIn("no tan lines or lower-leg darkening", item["caption"])
            for part in ("shoulders", "thighs", "calves", "feet", "hands"):
                self.assertIn(part, item["caption"])

    def test_skin_resolver_extracts_only_skin_and_undertone_and_handles_missing_description(
        self,
    ):
        for geometry, expected in (
            (
                "Oval face. Smooth light warm-ivory skin.",
                "smooth light warm-ivory skin",
            ),
            (
                "Oval face, fair porcelain skin with a cool undertone, brown eyes.",
                "fair porcelain skin with a cool undertone",
            ),
            (
                "Smooth light skin with warm undertone. Fine brows.",
                "smooth light skin with warm undertone",
            ),
            (
                "Light skin has subtle texture, faint small marks and soft cheek color.",
                "light skin",
            ),
            ("Angular jaw and green eyes.", contract.DEFAULT_SKIN_TONE),
        ):
            with self.subTest(geometry=geometry):
                face = dict(
                    schema_version=2,
                    geometry=geometry,
                    hair=dict(style="Bob", color="Black"),
                    expression="",
                )
                result = contract.resolve_skin_tone(
                    self.settings(face_description=json.dumps(face))
                )
                self.assertEqual(result, expected)
        self.assertEqual(
            contract.resolve_skin_tone(self.settings(face_description="")),
            contract.DEFAULT_SKIN_TONE,
        )

    def test_explicit_skin_tones_reach_every_panel_without_preserving_reference_skin_tone(
        self,
    ):
        baseline = self.build()
        for choice, phrase in contract.SKIN_TONE_PHRASES.items():
            with self.subTest(choice=choice):
                card = self.build(skin_tone=choice)
                self.assertIn(phrase, card["summary"]["caption"])
                for item in card["items"]:
                    self.assertIn(phrase, item["caption"])
                portrait = card["items"][0]["caption"]
                self.assertNotIn("and skin tone from reference image 1", portrait)
                self.assertIn(
                    "Keep the exact facial identity, eye shape, nose bridge, and lip contour",
                    portrait,
                )
                self.assertEqual(
                    [i["bbox"] for i in card["items"]],
                    [i["bbox"] for i in baseline["items"]],
                )
        with self.assertRaisesRegex(ValueError, "Invalid skin_tone"):
            self.build(skin_tone="unknown")

    def test_optional_skin_widget_is_appended_and_old_reference_calls_still_work(self):
        components = importlib.import_module(namespace.__name__ + ".components")
        for node in (
            components.MOSSCharacterSettings,
            components.MOSSReferenceCharacterSettings,
        ):
            schema = node.INPUT_TYPES()
            self.assertNotIn("skin_tone", schema["required"])
            self.assertEqual(list(schema["optional"])[-1], "skin_tone")
            self.assertEqual(
                schema["optional"]["skin_tone"][0], list(contract.SKIN_TONE_CHOICES)
            )
        node = components.MOSSReferenceCharacterSettings()
        self.assertEqual(
            json.loads(node.build("slim", "", "")[0])["skin_tone"],
            "From face selection",
        )
        self.assertEqual(
            json.loads(node.build("slim", "", "", skin_tone="Warm honey tan")[0])[
                "skin_tone"
            ],
            "Warm honey tan",
        )

    def test_explicit_skin_tone_also_works_on_shared_text_settings_without_changing_default_scaffold(
        self,
    ):
        baseline = self.build(reference=False)
        changed = self.build(reference=False, skin_tone="Warm honey tan")
        phrase = contract.SKIN_TONE_PHRASES["Warm honey tan"]
        for item in changed["items"]:
            self.assertIn(phrase, item["caption"])
        self.assertNotIn("Smooth light skin", changed["items"][0]["caption"])
        self.assertEqual(
            [i["bbox"] for i in changed["items"]],
            [i["bbox"] for i in baseline["items"]],
        )


if __name__ == "__main__":
    unittest.main()
