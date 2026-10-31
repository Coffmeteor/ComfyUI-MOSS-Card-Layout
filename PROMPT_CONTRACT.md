# Character Studio prompt contract, version 2

`prompt_contract.py` is the single compiler for Character Studio. Components provide typed data; they do not append complete generation prompts. `outfit_contract.py` validates garment facts and renders the two views. `layout.py` owns the four boxes, the official absolute centralized `yxyx` conversion, and body-reference privacy instructions.

With `reference_identity=false`,
the compiler fills `resources/t2i-card-scaffold.json`, derived from the original
`wardrobe-four-view-card-request.json`. It retains the frontal portrait pose,
upper-chest framing, anatomy stance, ghost-mannequin neckline and complete-panel
containment clauses. Slots own adult subject, body shape, facial attributes,
lighting, upper clothing and the separate front/back garment descriptions.
The original outfit-specific stocking/heel assumption is replaced by selected
clothing and footwear. Reference-conditioned wording has a separate branch.
The graph uses one full-canvas sampler and one decode; no panel assembly.

## Ownership

| Input | May change | Must preserve |
| --- | --- | --- |
| Text face selection | Portrait facial attributes | Outfit, panel order and boxes |
| Adult age / presentation | The same subject across all four panels | Outfit and framing |
| Hairstyle, hair color, expression | Its single portrait instruction | Other appearance controls and all body captions |
| Body shape / shared body appearance | Three body captions | Portrait identity and edit instruction |
| Outfit fields | Portrait upper clothing, clothed front and clothed back | Anatomy reference and identity clauses |
| Privacy switch | Summary privacy clause and anatomy-reference coverage | Portrait, outfit captions and all boxes |
| Dimensions | Canvas and computed boxes | Captions |
| Lighting | Shared scene and each local body caption | Identity and clothing data |

The portrait contains a complete head, a small crown margin, natural head-to-shoulder proportions, shoulders and upper chest. It does not inherit body-panel feet or neckline rules. The three body panels omit the complete head and neck, retain hands/feet and share camera scale, body proportions and a ground baseline; footwear may alter standing height. The anatomy reference has bare feet; selected clothing and footwear only belong to clothed views.

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

`face_contract.py` owns independent facial geometry, hairstyle, hair color and expression. The face node carries this structured record through the existing string output; users edit separate form fields and never need to write JSON. Text generation replaces only the selected field when a control is overridden. Reference editing uses the actual image for identity; with `reference_identity=true`, reconstructed facial geometry, hairstyle, hair color and expression prose from `face_spec` are excluded when `From face selection` is chosen, emitting generic reference preservation instructions while `resolve_skin_tone` still extracts the skin phrase for four-panel skin tone unification. Empty descriptions support raw LoadImage references; text-only generation requires a face description. Explicit overrides replace their own preservation instruction.

The reference portrait requests an upright head, horizontal eye line, level shoulders
and lowered hands. A word-boundary headwear detector inspects portrait clothing:
ordinary outfits request a bare head and natural hair crown, while explicit hats,
cloches, veils and other indexed headwear retain their requested accessory. The
summary and all three body captions retain headless/neckless wording recognized
by `text_scope.py`; privacy wording stays in the summary and anatomy caption.

The public source provides hairstyle metadata, not its author generation prompts
or numeric age/ethnicity annotations. Face descriptions are visually authored
attributes, not recovered original prompts. Revision2 reviews all60 full-size
sources for cheek/jaw proportions, eyelids, iris hue when visible, nose shape,
lips, skin detail, hair length/layers and expression. Uncertain hues stay
unspecified. Original IDs, URLs, source descriptions and categories remain as
provenance.

For T2I, **Age prompt** offers `Set age` and `Unspecified adult age`. The latter
does not infer a number from the selected picture, and disables the numeric
control. Old `From face selection` values remain accepted as an equivalent
backend alias and migrate to the clearer label in the UI. Reference-only
settings retain their existing inheritance behavior.

```json
{"schema_version":2,"geometry":"Oval face, almond eyes, a straight nose and full lower lip.","hair":{"style":"Center-parted straight bob","color":"Dark brown"},"expression":"Parted-lip smile showing upper teeth."}
```

All 24,000 face/outfit/privacy/conditioning combinations have been compiled and checked for valid fields and four-box geometry. This validates construction, separately from the model's image fidelity.

## Inspect the executed prompt

The active text workflow connects:

`Face / Character / Outfit -> Card Settings -> Preview as Text -> CLIPTextEncode`.

The built-in `PreviewAny` node passes its input string unchanged. Its preview is therefore the JSON consumed by the positive encoder, not a separately reconstructed explanation. Face thumbnails are selection previews; image outputs do not connect to text generation.

Runtime audits record component settings, the structured outfit, upper clothing and final JSON from ComfyUI history. Property tests check field ownership, schema rejection, side transforms, view visibility, box bounds and library round trips. Native output review is separate: a correct prompt does not certify that every generated pixel obeys it. Model comparisons follow prompt audit, using matched references, seeds and sampling settings.

## Released single-pass reference route

The selected reference release uses one joint canvas, one sampler and one decode.
Regional/shared-body assembly remains a retired experiment. The active
route uses `MOSSAnchoredReferenceEncode`, bbox-aligned reference positions and
per-panel direct text/reference visibility. Image self-attention and native text
self-attention stay open. `skin_tone` resolves one shared phrase into the summary,
portrait and all three body captions. Personal reference uploads without a skin
phrase use the documented light warm-ivory fallback; no image-based skin classifier
is applied. See REFERENCE_SETUP.md and the saved Character Studio - Reference graphs.
