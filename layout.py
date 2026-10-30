"""Size-derived three-view MOSS layout, shared by the UI node and task entrypoint."""
from __future__ import annotations
import json
import math

CAPTIONS = ("summary_caption", "portrait_caption", "front_caption", "back_caption")
# Normalized from the twelve-case layout; retain its tested margins and proportions.
BOXES = ((16, 16, 410, 560), (438, 16, 707, 560), (735, 16, 1008, 560))
FOUR_VIEW_CAPTIONS = (*CAPTIONS, "body_caption")
FOUR_VIEW_BOXES = ((28, 28, 548, 996), (580, 28, 964, 996),
                   (996, 28, 1380, 996), (1412, 28, 1796, 996))
PRIVACY_SUMMARY = {
    True: "Only the second panel has solid opaque charcoal privacy rectangles covering the breast and pelvic areas.",
    False: "The second panel is an unobstructed neutral adult anatomy reference without privacy overlays.",
}
PRIVACY_BODY = {
    True: ("Place smooth solid opaque charcoal privacy rectangles in front of the figure: "
           "one wide horizontal rectangle completely covers both breasts and nipples, and a second "
           "opaque rectangle completely covers the entire pubic and genital region. These are flat "
           "graphic overlays, not clothing; neither follows nor reshapes the anatomy. All intimate "
           "anatomy is fully concealed. Keep the shoulders, abdomen, waist, outer hips, arms, "
           "hands and legs visible for body proportion reference."),
    False: ("Show the unclothed adult figure as a neutral anatomical proportion study. "
            "No censor bars, privacy blocks, mosaics or other graphic coverings."),
}


def build_layout(long_edge: int, short_edge: int, summary_caption: str,
                 portrait_caption: str, front_caption: str, back_caption: str) -> str:
    for name, value in (("long_edge", long_edge), ("short_edge", short_edge)):
        if type(value) is not int or not 256 <= value <= 4096 or value % 16:
            raise ValueError(f"{name} must be a multiple of 16 between 256 and 4096")
    if long_edge < short_edge:
        raise ValueError("The side-by-side card requires long_edge >= short_edge")
    captions = (summary_caption, portrait_caption, front_caption, back_caption)
    if any(not isinstance(value, str) or not value.strip() for value in captions):
        raise ValueError("All four card descriptions must be nonempty text")
    items = []
    for caption, (x0, y0, x1, y1) in zip(captions[1:], BOXES):
        # Official compiler's outward rounding and centered yxyx convention:
        # OpenMOSS/MOSS-Image/skills/moss-image-prompt-enhancer/scripts/compile_prompt.py
        bbox = [math.floor(round(y0 * short_edge / 576, 9)) - short_edge // 2,
                math.floor(round(x0 * long_edge / 1024, 9)) - long_edge // 2,
                math.ceil(round(y1 * short_edge / 576, 9)) - short_edge // 2,
                math.ceil(round(x1 * long_edge / 1024, 9)) - long_edge // 2]
        items.append({"label": "character", "caption": caption, "bbox": bbox})
    return json.dumps({"summary": {"meta": ["photorealistic wardrobe reference board"],
                                   "canvas": "multi_panel", "caption": summary_caption},
                       "items": items, "bbox_coord_space": "abs_centralized",
                       "bbox_format": "yxyx"}, ensure_ascii=False, separators=(",", ":"))


def build_four_view_layout(long_edge: int, short_edge: int, privacy_blocks: bool,
                           body_caption: str, **captions) -> str:
    """Generate prompt-level privacy instructions; this is not pixel masking."""
    if type(privacy_blocks) is not bool:
        raise ValueError("privacy_blocks must be a boolean")
    if not isinstance(body_caption, str) or not body_caption.strip():
        raise ValueError("body_caption must be nonempty text")
    # Reuse all established dimension and caption validation.
    layout = json.loads(build_layout(long_edge, short_edge, **captions))
    layout["summary"]["caption"] += " " + PRIVACY_SUMMARY[privacy_blocks]
    descriptions = (captions["portrait_caption"],
                    body_caption + " " + PRIVACY_BODY[privacy_blocks],
                    captions["front_caption"], captions["back_caption"])
    items = []
    for caption, (x0, y0, x1, y1) in zip(descriptions, FOUR_VIEW_BOXES):
        bbox = [math.floor(round(y0 * short_edge / 1024, 9)) - short_edge // 2,
                math.floor(round(x0 * long_edge / 1824, 9)) - long_edge // 2,
                math.ceil(round(y1 * short_edge / 1024, 9)) - short_edge // 2,
                math.ceil(round(x1 * long_edge / 1824, 9)) - long_edge // 2]
        items.append({"label": "character", "caption": caption, "bbox": bbox})
    layout["items"] = items
    return json.dumps(layout, ensure_ascii=False, separators=(",", ":"))
