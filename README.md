# MOSS Character Studio

Build a complete four-panel character card from a selected face and outfit:
portrait, adult anatomy reference, clothed front and clothed back. The reference
workflow uses one full-canvas sampler and one VAE decode, with JSON/bbox layout,
portrait-scoped reference conditioning, automatic framing and shared skin controls.

**Release:** nodes 1.4.0 · reference LoRA 1.0.0 · ComfyUI 0.43.0 plus the bundled
reference-support patch. The existing 16-step text workflow remains available.

- [LoRA, workflows, examples and walkthrough](https://huggingface.co/Coffmeteor/MOSS-Character-Studio)
- [Reference installation](REFERENCE_SETUP.md)
- [Prompt field ownership](PROMPT_CONTRACT.md)

## Install

Search **MOSS Card Layout and Wardrobe** in ComfyUI Manager. The legacy Manager
catalog contains this Git repository. Registry version approval is separate;
if a version is unavailable there, use **Install via Git URL**:

```text
https://github.com/Coffmeteor/ComfyUI-MOSS-Card-Layout
```

Install the package requirements with ComfyUI's Python, restart and refresh.
For reference generation, complete the one-time [reference setup](REFERENCE_SETUP.md).
The setup verifies the exact supported core version and backs up both modified
files. It is never run automatically when the package is imported.

## Make and revise a card

1. Open **example_workflows/Character Studio - Reference.json**.
2. Click **Choose face**. Search features/hair tags and select a thumbnail.
3. Click **Choose outfit**. Search garment, color or material and select an outfit.
4. Set character controls and **Privacy coverage**. Off requests an unobstructed
   adult anatomy panel; On requests two opaque rectangles. The whole card is
   regenerated when this changes.
5. Run. **Preview as Text** shows the exact JSON used by the model; **Save Image**
   shows the complete result. Change a component and run again to revise it.

The selected recipe is 1536×864, 25 steps, CFG 3, Euler/sgm_uniform, AuraFlow
shift 5, SLG layer 22 and reference LoRA strength 1.0. No trigger word is used.
The LoRA loader includes a Hugging Face model-download link in workflow metadata.

**Character Studio - Text.json** uses the original independent 16-step accelerator
and descriptors instead of reference-image identity conditioning. It has its own
settings; do not substitute that accelerator into the reference workflow.

## Add your own assets

**Add my own** accepts PNG/JPEG/WebP images with a name, tags and editable fields.
Face geometry, hairstyle/color and expression have separate fields. Outfits use
shared garment identity, front/back details, portrait clothing and wearer-side
accessory descriptions. Uploaded descriptions are entered manually.

**My library**, **Edit**, **Remove** and **Undo remove** manage personal items.
They live in `ComfyUI/user/moss-card-layout/library` and survive package updates.
A workflow JSON does not include personal images; share those separately when needed.

## Downloads and dependencies

The curated library contains 60 faces and 100 outfits. Catalog descriptions ship
with the package. Image previews download from the original
[portrait gallery](https://ai-portrait-gallery.pages.dev/) and
[costume gallery](https://ai-costume-gallery.pages.dev/), with bounded downloads,
checksum verification and persistent caching under `ComfyUI/user/moss-card-layout`.
Source images are not redistributed or relicensed by this repository.

Automatic reference framing downloads Google's pinned 3.76 MB MediaPipe landmark
model on first use into `ComfyUI/models/mediapipe`. It verifies the exact size and
SHA-256 before installation. Existing verified models are reused; an optional
`MOSS_FACE_LANDMARKER_MODEL` environment variable supports a shared local copy.

## Observed behavior

The release examples retain the four roles and apply selected outfits in one
sampling pass. Short neck remnants, facial/expression variation, accessory changes
and differences in skin illumination remain visible in some outputs. Automatic
framing can level a tilted face, suppress headwear and locally adjust unequal eye
geometry; it can also alter outer hair. Direct reference access is scoped to the
portrait, while target image-to-image and text self-attention remain shared.

The node pack is MIT licensed. The bundled ComfyUI reference patch is GPL-3.0;
see `licenses/ComfyUI-GPL-3.0.txt`. Model weights have their separate Apache-2.0
license and attribution on Hugging Face. Gallery assets retain their source terms.
