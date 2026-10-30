# Character Studio prompt contract, version 2

`prompt_contract.py` is the single compiler for Character Studio. Components provide typed data; they do not append complete generation prompts. `outfit_contract.py` validates garment facts and renders the two views. `layout.py` owns the four boxes, the official absolute centralized `yxyx` conversion, and body-reference privacy instructions.

## Ownership

| Input | May change | Must preserve |
| --- | --- | --- |
| Reference identity / face selection | Portrait identity and the actual vision/VAE reference | Outfit, panel order and boxes |
| Age, hairstyle, hair color, expression | Its single portrait instruction | Other appearance controls and all body captions |
| Body shape | Three body captions | Portrait identity |
| Outfit fields | Portrait upper clothing, clothed front and clothed back | Anatomy reference and identity clauses |
| Privacy switch | Summary privacy clause and anatomy-reference coverage | Portrait, outfit captions and all boxes |
| Dimensions | Canvas and computed boxes | Captions |
| Lighting | Shared scene lighting | Identity and clothing data |

The portrait contains a complete head, a small crown margin, natural head-to-shoulder proportions, shoulders and upper chest. It does not inherit body-panel feet or neckline rules. The three body panels omit the complete head and neck, retain hands/feet and share shoulder height, body proportions and a ground baseline. The anatomy reference has bare feet; selected clothing and footwear only belong to clothed views.

## Outfit data

The form exposes shared garment identity, front-only details, back-only details, portrait clothing, and a repeatable list of asymmetric features. Users choose sides and visibility from menus; they do not need to write JSON.

```json
{
  "schema_version": 2,
  "shared": "A blue dress and black shoes.",
  "front": "A row of bodice buttons.",
  "back": "",
  "portrait": "A blue neckline and shoulder straps.",
  "asymmetries": [
    {"description": "A diagonal shoulder strap", "side": "left", "visible_in": "both"},
    {"description": "A decorative pocket", "side": "right", "visible_in": "front"}
  ]
}
```

`side` accepts `left`, `right`, `center`, or `both`. These are the wearer's anatomical sides, never image coordinates. `visible_in` accepts `front`, `back`, or `both`. The compiler maps wearer-left to viewer-right in a frontal view and viewer-left in a rear view; wearer-right maps oppositely. The same feature cannot switch wearer side between views. A symmetric pair uses `side: both`.

This rule applies to pockets, slits, straps, ornaments, carried objects and other asymmetric details. Front-only closures, chest details and shoe-toe decorations are not copied into rear garment data. Unknown rear details stay empty: the template asks for the rear surfaces of the same garments without inventing prints or fasteners. The body is viewed after a 180-degree turn, not as a mirrored front photograph.

Portrait clothing excludes waist, lower garments, legwear, footwear and carried bags. Head/neck accessories belong only to the portrait field. Shared garment facts cannot contain front/back or left/right directives; use their dedicated fields. Library fields cannot contain card-layout instructions or unresolved template markers. Invalid or missing fields fail before sampling. Personal-library create and update use the same validator as generation.

The former first-sentence portrait extractor is retired. New bulk imports require a complete versioned `outfit_spec`; they cannot infer missing fields. The packaged selection contains 100 visually reviewed outfits and 60 visually reviewed faces. Original descriptions, image URLs and hashes are retained as provenance. Physical side features persist across views; a front-view source image does not make a whole sleeve, bag or trouser leg a front-only feature.

## Face data

`face_contract.py` owns independent facial geometry, hairstyle, hair color and expression. The face node carries this structured record through the existing string output; users edit separate form fields and never need to write JSON. Text generation replaces only the selected field when a control is overridden. It does not remove whole sentences from facial descriptions or strip colors with a runtime heuristic. Reference editing uses the actual image for identity; reconstructed face prose is excluded. Inherited expression and an explicit expression override are mutually exclusive.

```json
{"schema_version":2,"geometry":"Oval face, almond eyes, a straight nose and full lower lip.","hair":{"style":"Center-parted straight bob","color":"Dark brown"},"expression":"Parted-lip smile showing upper teeth."}
```

All 24,000 face/outfit/privacy/conditioning combinations have been compiled and checked for valid fields and four-box geometry. This validates construction, separately from the model's image fidelity.

## Inspect the executed prompt

The reference evaluation workflow connects:

`Face / Character / Outfit -> Card Settings -> Preview as Text -> Text Encode MOSS-Image Edit`.

The built-in `PreviewAny` node passes its input string unchanged. Its preview is therefore the JSON consumed by the positive encoder, not a separately reconstructed explanation. Native edit encoding adds the `Picture 1` vision marker and Qwen chat template; it does not rewrite the JSON captions. Both conditioning branches receive the same reference image.

Runtime audits record component settings, the structured outfit, upper clothing and final JSON from ComfyUI history. Property tests check field ownership, schema rejection, side transforms, view visibility, box bounds and library round trips. Native output review is separate: a correct prompt does not certify that every generated pixel obeys it. Model comparisons follow prompt audit, using matched references, seeds and sampling settings.
