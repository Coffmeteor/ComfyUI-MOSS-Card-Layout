"""Small character controls compiled into the established four-panel contract."""

from __future__ import annotations
import json
from . import wardrobe, user_library
from .prompt_contract import (
    compile_card,
    validate_character,
    validate_outfit,
    SKIN_TONE_CHOICES,
)
from .outfit_contract import validate_spec


class MOSSOutfitLibrary:
    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "outfit_id": ("STRING", {"default": "SPR-0048"}),
                "extra_outfit_details": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("outfit_description", "portrait_clothing")
    FUNCTION = "build"
    CATEGORY = "MOSS-Image/Character Studio"

    @classmethod
    def IS_CHANGED(cls, **kwargs) -> str:
        return json.dumps(wardrobe.get_entry(kwargs["outfit_id"]), sort_keys=True)

    def build(self, outfit_id: str, extra_outfit_details: str) -> tuple[str, str]:
        e = wardrobe.get_entry(outfit_id)
        if extra_outfit_details.strip():
            raise ValueError(
                "Edit the shared/front/back/asymmetric outfit fields instead of appending unscoped outfit notes"
            )
        spec = validate_spec(
            e.get("outfit_spec")
            or dict(
                schema_version=2,
                shared=e["description"],
                front=e.get("front_details", ""),
                back=e.get("back_details", ""),
                portrait=e["portrait_description"],
                asymmetries=e.get("asymmetries", []),
            )
        )
        return json.dumps(spec, ensure_ascii=False, separators=(",", ":")), spec[
            "portrait"
        ]


class MOSSCharacterSettings:
    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "age_mode": (
                    ["Set age", "Unspecified adult age", "From face selection"],
                    {
                        "tooltip": "The text face library has no numeric age. Set age adds the chosen adult age; Unspecified adult age adds no number. From face selection is a legacy alias."
                    },
                ),
                "age": (
                    "INT",
                    {
                        "default": 25,
                        "min": 18,
                        "max": 100,
                        "tooltip": "Used only when Age prompt is Set age.",
                    },
                ),
                "presentation": (["woman", "man", "person", "From face selection"],),
                "body_shape": (["slim", "average", "athletic", "curvy", "broad"],),
                "hair_style": (
                    [
                        "From face selection",
                        "Elegant updo",
                        "Short bob",
                        "Pixie cut",
                        "Shoulder-length waves",
                        "Long straight hair",
                        "Long loose curls",
                    ],
                ),
                "hair_color": (
                    [
                        "From face selection",
                        "Black",
                        "Brown",
                        "Auburn",
                        "Blonde",
                        "Silver",
                        "Pink",
                        "Blue",
                    ],
                ),
                "expression": (
                    [
                        "From face selection",
                        "Calm and relaxed",
                        "Soft smile",
                        "Serious",
                        "Cheerful",
                    ],
                ),
                "extra_character_details": (
                    "STRING",
                    {"default": "", "multiline": True},
                ),
                "face_description": ("STRING", {"forceInput": True}),
                "reference_hair": ("STRING", {"forceInput": True}),
            },
            "optional": {
                "body_appearance": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "Shared body traits and natural proportions for the three body views. Use Skin tone for one tone across all four panels.",
                    },
                ),
                "skin_tone": (
                    list(SKIN_TONE_CHOICES),
                    {"default": "From face selection"},
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("character",)
    FUNCTION = "build"
    CATEGORY = "MOSS-Image/Character Studio"

    def build(self, **values) -> tuple[str]:
        return (json.dumps(validate_character(values), ensure_ascii=False),)


class MOSSReferenceCharacterSettings:
    """Reference-preserving cards expose only controls that do not contradict the face."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "body_shape": (["slim", "average", "athletic", "curvy", "broad"],),
                "face_description": ("STRING", {"forceInput": True}),
                "reference_hair": ("STRING", {"forceInput": True}),
            },
            "optional": {
                "body_appearance": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "Shared body traits for anatomy, front and back. The isolated body generator does not infer these from the portrait reference.",
                    },
                ),
                "skin_tone": (
                    list(SKIN_TONE_CHOICES),
                    {"default": "From face selection"},
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("character",)
    FUNCTION = "build"
    CATEGORY = "MOSS-Image/Character Studio"

    def build(
        self,
        body_shape,
        face_description,
        reference_hair,
        body_appearance="",
        skin_tone="From face selection",
    ):
        return MOSSCharacterSettings().build(
            age_mode="From face selection",
            age=25,
            presentation="From face selection",
            body_shape=body_shape,
            hair_style="From face selection",
            hair_color="From face selection",
            expression="From face selection",
            extra_character_details="",
            face_description=face_description,
            reference_hair=reference_hair,
            body_appearance=body_appearance,
            skin_tone=skin_tone,
        )


class MOSSCharacterCardComposer:
    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {
            "required": {
                "long_edge": (
                    "INT",
                    {"default": 1824, "min": 256, "max": 4096, "step": 16},
                ),
                "short_edge": (
                    "INT",
                    {"default": 1024, "min": 256, "max": 4096, "step": 16},
                ),
                "privacy_blocks": ("BOOLEAN", {"default": True}),
                "character": ("STRING", {"forceInput": True}),
                "outfit_description": ("STRING", {"forceInput": True}),
                "portrait_clothing": ("STRING", {"forceInput": True}),
                "lighting": (
                    [
                        "Soft even studio light",
                        "Soft window light",
                        "Clean catalog lighting",
                    ],
                ),
                "reference_identity": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Enable only in the face-reference workflow; it must be connected to reference image conditioning.",
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING", "INT", "INT")
    RETURN_NAMES = ("layout_json", "width", "height")
    FUNCTION = "build"
    CATEGORY = "MOSS-Image/Character Studio"

    def build(
        self,
        long_edge: int,
        short_edge: int,
        privacy_blocks: bool,
        character: str,
        outfit_description: str,
        portrait_clothing: str,
        lighting: str,
        reference_identity: bool,
    ) -> tuple[str, int, int]:
        return compile_card(
            long_edge,
            short_edge,
            privacy_blocks,
            character,
            outfit_description,
            portrait_clothing,
            lighting,
            reference_identity,
        )
