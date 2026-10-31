"""Versioned component contract and the sole Character Studio prompt compiler.

Library fields contain appearance data, never layout or generation instructions.
The compiler owns panel roles, framing, inheritance, lighting and privacy scope.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from string import Template

CONTRACT_VERSION = 2
SKIN_TONE_PHRASES = {
    "Fair porcelain": "fair porcelain skin with a cool-ivory undertone",
    "Light warm ivory": "light warm ivory skin with a soft peach undertone",
    "Natural medium beige": "natural medium beige skin with a balanced neutral-warm undertone",
    "Warm honey tan": "warm sun-kissed honey-tan skin with a golden undertone",
    "Deep bronze brown": "deep bronze-brown skin with a rich warm undertone",
}
SKIN_TONE_CHOICES = ("From face selection", *SKIN_TONE_PHRASES)
DEFAULT_SKIN_TONE = "smooth light warm-ivory skin"
HEADWEAR_RE = re.compile(
    r"\b(?:hats?|berets?|beanies?|headbands?|earmuffs|headpiece|headdress|tiara|crown|caps?|cloche|bonnet|visor|veil|hood)\b",
    re.IGNORECASE,
)
LOWER_FRAME = re.compile(
    r"\b(?:skirts?|trousers|pants|jeans|shorts|leggings|tights|stockings|socks|shoes|heels|sandals|sneakers|boots|pumps|loafers|mules|stilettos|pantyhose|slippers|feet|footwear|waist|waistline|hips?|thighs?|knees?|ankles?|calves|calf|hemline|hem|handbags?|bags?|purses?|belts?|briefs|panties|thong|garter|bottoms)\b",
    re.I,
)
HEAD_ACCESSORY = re.compile(
    r"\b(?:hats?|berets?|beanies?|headbands?|earmuffs|sunglasses|eyeglasses|earrings|necklaces?|chokers?|headpiece|headdress|hairpins?|hairband|tiara|crown|caps?|halo)\b",
    re.I,
)
PRESENTATION = re.compile(
    r"ghost[- ]mannequin|\bmannequin\b|\binvisible\b|garment-only|\bfloating\b|\b(?:studio|plain|neutral|gray|grey) background\b|\bbbox\b|\b(?:four|three|\d+)[ -]panels?\b|\bheadless\b|\bneckless\b|{{|}}",
    re.I,
)
CONTROL_IN_EXTRA = re.compile(
    r"\b(?:hairstyle|hair|expression|smiling|smile|serious|cheerful|age|years old|shirt|dress|background|panel|headless|neckless|privacy|bbox)\b",
    re.I,
)


def content_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: enter a nonempty appearance description")
    value = value.strip()
    conflict = PRESENTATION.search(value)
    if conflict:
        raise ValueError(
            f'{field}: "{conflict[0]}" belongs to card settings, not a library description'
        )
    return value


def validate_outfit(body: str, portrait: str) -> tuple[str, str]:
    body = content_text(body, "Body outfit")
    portrait = content_text(portrait, "Portrait clothing")
    if match := LOWER_FRAME.search(portrait):
        raise ValueError(
            f'Portrait clothing: remove "{match[0]}"; describe only the neckline, shoulders, upper chest and head accessories'
        )
    if match := HEAD_ACCESSORY.search(body):
        raise ValueError(
            f'Body outfit: move "{match[0]}" to Portrait clothing; the three body panels have no head or neck'
        )
    return body, portrait


def validate_character(c: dict) -> dict:
    if not isinstance(c, dict):
        raise ValueError("Character settings must be an object")
    required = {
        "age",
        "presentation",
        "body_shape",
        "hair_style",
        "hair_color",
        "expression",
        "extra_character_details",
        "face_description",
        "reference_hair",
    }
    if missing := required - c.keys():
        raise ValueError(f"Missing character fields: {sorted(missing)}")
    if (
        unknown := c.keys()
        - required
        - {"age_mode", "schema_version", "body_appearance", "skin_tone"}
    ):
        raise ValueError(f"Unknown character fields: {sorted(unknown)}")
    if c.get("schema_version", CONTRACT_VERSION) != CONTRACT_VERSION:
        raise ValueError("Unsupported Character Studio prompt contract")
    if type(c["age"]) is not int or not 18 <= c["age"] <= 100:
        raise ValueError(
            "This anatomical character-card template requires an adult age"
        )
    choices = {
        "age_mode": ("Set age", "Unspecified adult age", "From face selection"),
        "presentation": ("woman", "man", "person", "From face selection"),
        "body_shape": ("slim", "average", "athletic", "curvy", "broad"),
        "hair_style": (
            "From face selection",
            "Elegant updo",
            "Short bob",
            "Pixie cut",
            "Shoulder-length waves",
            "Long straight hair",
            "Long loose curls",
        ),
        "hair_color": (
            "From face selection",
            "Black",
            "Brown",
            "Auburn",
            "Blonde",
            "Silver",
            "Pink",
            "Blue",
        ),
        "expression": (
            "From face selection",
            "Calm and relaxed",
            "Soft smile",
            "Serious",
            "Cheerful",
        ),
        "skin_tone": SKIN_TONE_CHOICES,
    }
    c = dict(
        c,
        age_mode=c.get("age_mode", "Set age"),
        schema_version=CONTRACT_VERSION,
        body_appearance=c.get("body_appearance", ""),
        skin_tone=c.get("skin_tone", "From face selection"),
    )
    for key, allowed in choices.items():
        if c[key] not in allowed:
            raise ValueError(f"Invalid {key}: select a supported value")
    for key in ("face_description", "reference_hair", "extra_character_details"):
        if not isinstance(c[key], str):
            raise ValueError(f"{key} must be text")
    if match := CONTROL_IN_EXTRA.search(c["extra_character_details"]):
        raise ValueError(
            f'Additional portrait details: use the dedicated control for "{match[0]}"'
        )
    if c["extra_character_details"].strip():
        content_text(c["extra_character_details"], "Additional portrait details")
    if not isinstance(c["body_appearance"], str):
        raise ValueError("Shared body appearance must be text")
    if c["body_appearance"].strip():
        c["body_appearance"] = content_text(
            c["body_appearance"], "Shared body appearance"
        )
    return c


def clean(value: str) -> str:
    return value.strip().rstrip(" .")


def resolve_skin_tone(c: dict) -> str:
    """Extract only the skin clause, leaving facial geometry and blush local."""
    choice = c.get("skin_tone", "From face selection")
    if choice != "From face selection":
        if choice not in SKIN_TONE_PHRASES:
            raise ValueError("Invalid skin_tone: select a supported value")
        return SKIN_TONE_PHRASES[choice]
    if c.get("face_description", "").strip():
        from .face_contract import parse_face

        face = parse_face(c["face_description"], c.get("reference_hair", ""))
        for clause in re.split(r"[.;,\n]", face["geometry"]):
            match = re.search(r"\bskin\b", clause, re.I)
            if not match:
                continue
            prefix = re.split(
                r"\b(?:and|with|has|have)\b", clause[: match.start()], flags=re.I
            )[-1].strip()
            prefix = re.sub(r"^(?:a|an|the|her|his|their)\s+", "", prefix, flags=re.I)
            undertone = re.search(
                r"\b(?:with|has)\s+([^.;,]*?\bundertone)\b", clause[match.end() :], re.I
            )
            if prefix or undertone:
                phrase = (prefix + " skin").strip()
                if undertone:
                    phrase += " with " + undertone[1].strip()
                return phrase[0].lower() + phrase[1:]
    return DEFAULT_SKIN_TONE


def identity_caption(c: dict, reference: bool = False) -> str:
    if reference:
        from .face_contract import parse_face

        face = (
            parse_face(c["face_description"], c.get("reference_hair", ""))
            if c.get("face_description", "").strip()
            else None
        )
        skin_phrase = resolve_skin_tone(c)
        if c.get("skin_tone", "From face selection") == "From face selection":
            parts = [
                "Keep the exact facial identity, eye shape, nose bridge, lip contour, and skin tone from reference image 1.",
                f"Consistent {skin_phrase} across face, neck and upper chest.",
            ]
        else:
            parts = [
                f"Keep the exact facial identity, eye shape, nose bridge, and lip contour from reference image 1, with {skin_phrase} across face, neck and upper chest."
            ]
        parts.append(
            "Preserve the apparent adult age of the reference."
            if c["age_mode"] != "Set age"
            else f"Show this adult person at age {c['age']}."
        )
        parts.append(
            "Preserve the gender presentation of the reference."
            if c["presentation"] == "From face selection"
            else f"Gender presentation: {c['presentation']}."
        )
        if c["hair_style"] == "From face selection":
            parts.append(
                f"Preserve the reference hairstyle ({clean(face['hair']['style'])})."
                if face and face["hair"]["style"]
                else "Preserve the reference hairstyle."
            )
        else:
            parts.append(f"Change the hairstyle to {clean(c['hair_style'])}.")
        if c["hair_color"] == "From face selection":
            parts.append(
                f"Preserve the reference hair color ({clean(face['hair']['color'])})."
                if face and face["hair"]["color"]
                else "Preserve the reference hair color."
            )
        else:
            parts.append(f"Use {clean(c['hair_color'])} hair color.")
        if c["expression"] == "From face selection":
            parts.append(
                f"Preserve the reference expression ({clean(face['expression'])})."
                if face and face["expression"]
                else "Preserve the reference expression."
            )
        else:
            parts.append(f"Expression: {clean(c['expression'])}.")
        parts.append(
            "Keep the reference eye color and gaze."
            if c.get("eyes", "From face selection") == "From face selection"
            else f"Eyes: {clean(c['eyes'])}."
        )
        if c["expression"] == "From face selection":
            parts.append(
                "Keep whether the mouth is open or closed, whether teeth are visible, and the smile intensity exactly as in the reference."
            )
    else:
        from .face_contract import parse_face

        face = parse_face(c["face_description"], c["reference_hair"])
        hair = (
            face["hair"]["style"]
            if c["hair_style"] == "From face selection"
            else c["hair_style"]
        )
        color = (
            face["hair"]["color"]
            if c["hair_color"] == "From face selection"
            else c["hair_color"]
        )
        if (
            color
            and c["hair_style"] == "From face selection"
            and not face["hair"]["color"]
        ):
            from .face_contract import HAIR_COLORS

            if HAIR_COLORS.search(hair):
                raise ValueError(
                    "Separate hair style and color in the face library before overriding hair color"
                )
        geometry = face["geometry"]
        if c.get("skin_tone", "From face selection") != "From face selection":
            inherited = resolve_skin_tone(dict(c, skin_tone="From face selection"))
            geometry, count = re.subn(
                re.escape(inherited), resolve_skin_tone(c), geometry, flags=re.I
            )
            if not count:
                geometry += " " + resolve_skin_tone(c) + "."
        parts = [geometry]
        if hair:
            parts.append("Hairstyle: " + hair.rstrip(" .") + ".")
        if color:
            parts.append("Hair color: " + color.rstrip(" .") + ".")
        if c["age_mode"] == "Set age":
            parts.append(f"Adult age {c['age']}.")
        if c["presentation"] != "From face selection":
            parts.append(f"Adult {c['presentation']}.")
        expression = (
            face["expression"]
            if c["expression"] == "From face selection"
            else c["expression"]
        )
        if expression:
            parts.append("Expression: " + expression.rstrip(" .") + ".")
    if c["extra_character_details"].strip():
        parts.append(
            "Additional portrait details: " + c["extra_character_details"].strip()
        )
    return " ".join(p.strip() for p in parts if p.strip())


def compile_card(
    long_edge: int,
    short_edge: int,
    privacy_blocks: bool,
    character: str,
    outfit_description: str,
    portrait_clothing: str,
    lighting: str,
    reference_identity: bool,
) -> tuple[str, int, int]:
    from .layout import build_four_view_layout
    from .outfit_contract import parse_spec, render_view

    c = validate_character(json.loads(character))
    outfit = parse_spec(outfit_description, portrait_clothing)
    upper_outfit = outfit["portrait"]
    if type(reference_identity) is not bool:
        raise ValueError("reference_identity must be a boolean")
    if not c["face_description"].strip() and not reference_identity:
        raise ValueError("face_description is required.")
    if lighting not in (
        "Soft even studio light",
        "Soft window light",
        "Clean catalog lighting",
    ):
        raise ValueError("Select a supported lighting setting")
    if not reference_identity:
        # Keep the original text-only wardrobe card scaffold. Reference experiments
        # must not rewrite the joint T2I card's framing or panel-role descriptions.
        scaffold = json.loads(
            (Path(__file__).parent / "resources/t2i-card-scaffold.json").read_text()
        )
        subject = "adult " + (
            "person"
            if c["presentation"] == "From face selection"
            else c["presentation"]
        )
        if c["age_mode"] == "Set age":
            subject = f"{c['age']}-year-old " + subject
        slots = dict(
            subject=subject,
            body_shape=c["body_shape"],
            identity=identity_caption(c, False),
            lighting=lighting,
            body_appearance=(
                c["body_appearance"].rstrip(" .") + "."
                if c["body_appearance"].strip()
                else ""
            ),
            portrait_outfit=upper_outfit,
            front_outfit=render_view(outfit, "front"),
            back_outfit=render_view(outfit, "back"),
        )
        captions = {
            key: Template(value).substitute(slots) for key, value in scaffold.items()
        }
        if c["skin_tone"] != "From face selection":
            skin_phrase = resolve_skin_tone(c)
            captions["summary_caption"] += (
                f" All four panels show the exact same {skin_phrase}."
            )
            for key in ("body_caption", "front_caption", "back_caption"):
                captions[key] += (
                    f" Uniform {skin_phrase} across all exposed skin, matching the portrait, with no tan lines or lower-leg darkening."
                )
        return (
            build_four_view_layout(long_edge, short_edge, privacy_blocks, **captions),
            long_edge,
            short_edge,
        )
    summary = (
        "Exactly four separate photographs in one horizontal row on matching neutral light-gray studio backgrounds: "
        "identity portrait, front body-proportion reference, clothed front view, clothed back view. "
        "Place every view inside its own bounding box. Only the portrait shows a complete head. "
        "The three body panels are headless and neckless. "
        "The other three views show the same adult body proportions and matching skin tone, at the same camera distance and body scale. "
        "Use a common ground baseline; footwear may change standing height without changing anatomy. "
        "Keep shoulder, waist and hip widths and limb lengths consistent. "
        "No text, labels or additional people. Natural skin and fabric. "
        + lighting
        + "."
    )
    skin_phrase = resolve_skin_tone(c)
    summary += f" All four panels show the exact same {skin_phrase} across face, neck, shoulders, torso, arms, hands, thighs, legs and feet."
    identity = identity_caption(c, reference=True)
    pose_and_headwear_clause = "Head upright, horizontal eye line, level shoulders, hands lowered completely out of frame."
    if not HEADWEAR_RE.search(upper_outfit):
        pose_and_headwear_clause += " Bare head with no hat, headwear, or hair accessories; complete natural hair crown with studio margin above."
    portrait = " ".join(
        [
            "Clean frontal studio chest-up portrait of the same adult person in reference image 1.",
            identity,
            pose_and_headwear_clause,
            f"Wearing {upper_outfit}.",
            f"Background: {c.get('background', 'neutral light-gray studio background')}.",
            "Soft even studio key light, natural skin texture, sharp eyes, 85mm portrait lens, no text, no watermark, no split screen.",
        ]
    )
    body_shared = (
        f"The same adult person with a {c['body_shape']} build and uniform {skin_phrase} matching the portrait across "
        "shoulders, chest, abdomen, waist, hips, thighs, knees, calves, ankles, feet, arms and hands, "
        "with even studio lighting and no tan lines or lower-leg darkening. "
        + (c["body_appearance"].rstrip(" .") + ". " if c["body_appearance"] else "")
        + lighting
        + ". Neutral light-gray studio background and neutral white balance. "
        "Photographic skin texture. Camera level with the waist, without perspective elongation. "
        "The body ends cleanly at the shoulder line. Headless and neckless. The entire head and neck are absent, leaving only empty gray background above the shoulders. "
        "Show both complete shoulders, relaxed arms, hands and feet; the figure is not cropped by the image edge. "
        "Leave a generous empty gray margin above the shoulder line and below the soles. "
    )
    body = (
        "One unclothed, barefoot FRONT adult anatomy reference. "
        + body_shared
        + "Neutral nonsexual anatomical reference with no clothing, footwear or accessories. "
        "Both bare feet rest flat on the ground, with visible toes, bare heels and bare ankles. "
        "No shoes, sandals, straps, socks or stockings cover any part of this anatomical figure. "
    )
    front = (
        "One complete straight-on FRONT outfit and body view, with footwear toes facing the camera. "
        + body_shared
        + "The garment neckline is hollow, with no throat or neck stump above it. Wear: "
        + render_view(outfit, "front")
    )
    back = (
        "One complete straight-on BACK outfit and body view after a 180-degree turn, showing the backs of the heels. "
        + body_shared
        + "The garment neckline is hollow, with no throat or neck stump above it. Show the back of the same outfit, "
        "with coherent colors, materials, lengths and footwear. Do not mirror the front photograph or copy its visible chest details onto the rear. "
        "Do not invent rear graphics or fasteners when they are unspecified. Wear: "
        + render_view(outfit, "back")
    )
    prompt = build_four_view_layout(
        long_edge,
        short_edge,
        privacy_blocks,
        summary_caption=summary,
        portrait_caption=portrait,
        body_caption=body,
        front_caption=front,
        back_caption=back,
    )
    return prompt, long_edge, short_edge
