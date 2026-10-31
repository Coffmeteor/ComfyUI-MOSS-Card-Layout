"""Human-readable wardrobe labels derived from the reconstructed clothing text."""

from __future__ import annotations
import re

FACETS = {
    "Garment": [
        "Dress",
        "Skirt",
        "Blouse",
        "Sweater",
        "Cardigan",
        "Jacket",
        "Coat",
        "Corset",
        "Camisole",
        "Bikini",
        "Swimsuit",
        "Lingerie",
        "Trousers",
        "Shorts",
        "Bodysuit",
        "Kimono",
        "Qipao",
    ],
    "Color": [
        "Mint",
        "Ivory",
        "White",
        "Black",
        "Pink",
        "Brown",
        "Beige",
        "Blue",
        "Green",
        "Red",
        "Purple",
        "Lavender",
        "Yellow",
        "Grey",
        "Silver",
        "Gold",
        "Champagne",
        "Peach",
    ],
    "Material": [
        "Knit",
        "Lace",
        "Satin",
        "Silk",
        "Denim",
        "Leather",
        "Tulle",
        "Chiffon",
        "Tweed",
        "Velvet",
        "Fur",
    ],
    "Detail": [
        "Floral",
        "Pleated",
        "Ruffled",
        "Ribbed",
        "Striped",
        "Plaid",
        "Bow",
        "Off-shoulder",
        "Halter",
    ],
}
ALIASES = {
    "Trousers": r"trousers|pants",
    "Grey": r"grey|gray",
    "Knit": r"knit\w*",
    "Ruffled": r"ruffl\w*",
    "Off-shoulder": r"off.the.shoulder",
    "Bow": r"bows?",
}


def describe(entry: dict) -> dict:
    text = entry["description"].lower()
    facets = {}
    for family, labels in FACETS.items():
        matches = []
        for label in labels:
            match = re.search(
                r"\b(?:"
                + ALIASES.get(label, re.escape(label.lower()) + r"s?")
                + r")\b",
                text,
            )
            if match:
                matches.append((match.start(), label))
        facets[family] = [label for _, label in sorted(matches)]
    garment = next(iter(facets["Garment"]), "Outfit")
    color = next(iter(facets["Color"]), "")
    material = next(iter(facets["Material"]), "")
    label = (
        " ".join(x for x in (color, material.lower(), garment.lower()) if x)
        .strip()
        .capitalize()
    )
    return {
        "label": entry.get("label") or label,
        "tags": list(
            dict.fromkeys(
                [
                    *entry.get("tags", []),
                    *(tag for tags in facets.values() for tag in tags),
                ]
            )
        ),
        "facets": facets,
    }
