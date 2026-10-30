# MOSS Character Studio

ComfyUI nodes for three/four-panel character cards, including a searchable
visually curated 100-outfit wardrobe and 60-face library with live thumbnail previews,
editable character controls and a persistent personal library.

## Install

In ComfyUI Manager, use Install via Git URL:
https://github.com/Coffmeteor/ComfyUI-MOSS-Card-Layout

Restart ComfyUI and refresh the browser. Existing users update this node pack
to version 1.2.0 to get structured prompt fields and the aligned workflows. Registry/Manager search listing is pending;
Git URL installation works independently of registry approval.

The prompt catalog ships with the node. Gallery images download automatically
from https://ai-costume-gallery.pages.dev/ when their previews are requested,
then remain in `ComfyUI/user/moss-card-layout/images`. Downloads are bounded,
SHA-256 verified and atomically cached. No Hermes installation or private paths
are required. First use needs internet; previously downloaded previews work offline.
The images remain third-party assets under the source site's terms.

## Use

Open **Character Studio - Text.json** from `example_workflows`. The top row
contains aligned Face, Character/Card and Outfit sections. The actual final JSON, Result and a separate Advanced generation section sit below.

1. Click **Choose face**, search features or combine hair/face-shape tags, then
   click a thumbnail. This text route uses derived descriptions to generate a
   new face with similar traits; it does not preserve a reference person's identity.
2. Click **Choose outfit**, combine garment/color/material tags and select a
   thumbnail. Clothing fills the portrait and both clothed body views.
3. Set age, body shape, hairstyle, hair color and expression in **Character
   Settings**. `From face selection` keeps the selected description for that
   property. Explicit color/expression changes remove competing source details.
4. Choose dimensions, lighting and the privacy switch in **Four-Panel Card
   Settings**, then run. Change a component and run again to regenerate the card.

The component prompt contract is version 2. See [field ownership and validation](PROMPT_CONTRACT.md).
New items with conflicting spatial fields fail before generation. The previous
first-sentence clothing extractor is retired.

The requested panels are portrait, independent anatomy reference, clothed front and
clothed back. Output acceptance remains unresolved: body panels can retain full heads
or neck sections, anatomy panels can inherit shoes, and generated privacy shapes
can differ from the requested rectangles. Review the native output; the component
schema validates prompts, not these pixel-level requirements.
The older **Four View Visual Wardrobe** workflow remains supported.

### Add your own faces or outfits

Click **Add my own**, choose a PNG/JPEG/WebP (up to 16 MB and 32 megapixels),
then enter a name, tags and short description. For faces, describe facial details,
hairstyle, hair color and expression separately. For outfits, enter shared garment identity, front-only details,
known back-only details and portrait clothing. Add asymmetric features with a
wearer-side selector and front/back visibility; no JSON editing is required. Descriptions are entered manually; this node pack does not run a
captioning model for uploaded images. The saved item is selected automatically.
Use **My library** to find it later. **Edit**, **Remove** and **Undo remove** are
available on your own items. IDs are internal and never needed for normal use.

User data lives in `ComfyUI/user/moss-card-layout/library`, outside the node
package, and survives updates. Back up that directory with your workflows.
Removal moves items into that library's `.trash`; the browser offers immediate
undo. Workflows reference local library items: sharing a workflow JSON alone
does not transfer personal images. Uploads stay on the ComfyUI server.

### Models and reference editing

This package supplies selection, library and layout nodes. Text generation
requires the existing MOSS HF integration, original SFT model and sixteen-step
accelerator. Replace the example HF-directory placeholder `MOSS-Image-SFT` with your installed absolute HF directory and choose the installed accelerator in the generation section. It does not
install model weights or replace their licenses.

The released workflow uses text conditioning. Experimental armV5 reference-card workflows are separate: local clothing edits can retain a reference face, while rebuilding a four-panel card can change facial features or body framing. Reference-card quality is being evaluated independently of this library package.

### Face source

Face metadata comes from https://ai-portrait-gallery.pages.dev/. Images are
fetched from the source on demand and cached under
`ComfyUI/user/moss-card-layout/portraits`; they are not redistributed in this
repository. Thumbnail hashes and full-image byte counts are checked. The 60 selected faces and 100 selected outfits were visually reviewed and manually rewritten into independent fields. Original reconstructed captions remain in source-provenance fields; these are not the source creator's original generation prompts. Source gallery terms apply.

## Publishing

Publisher: `coffmeteor`. Registry publication uses the official Comfy-Org action.
Create a publishing API key for this publisher in Comfy Registry, then store it
as the GitHub repository Actions secret `REGISTRY_ACCESS_TOKEN`. Never commit it.
Run **Actions > Publish to Comfy Registry > Run workflow** for the first publish.
Later changes to `pyproject.toml` on main also trigger publication. Bump the
semantic version for each new Registry release. Without the secret, the workflow
reports that publication was skipped; a green setup run is not a published version.

See https://docs.comfy.org/registry/publishing for the official instructions.
