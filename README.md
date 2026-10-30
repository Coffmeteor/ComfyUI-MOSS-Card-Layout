# MOSS Card Layout and Wardrobe

ComfyUI nodes for three/four-panel character cards, including a searchable
1,407-outfit wardrobe with a live thumbnail preview.

## Install

In ComfyUI Manager, use Install via Git URL:
https://github.com/Coffmeteor/ComfyUI-MOSS-Card-Layout

Restart ComfyUI and refresh the browser. Existing users update this node pack
once to get `MOSSFourViewWardrobeCard`. Registry/Manager search listing is pending;
Git URL installation works independently of registry approval.

The prompt catalog ships with the node. Gallery images download automatically
from https://ai-costume-gallery.pages.dev/ when their previews are requested,
then remain in `ComfyUI/user/moss-card-layout/images`. Downloads are bounded,
SHA-256 verified and atomically cached. No Hermes installation or private paths
are required. First use needs internet; previously downloaded previews work offline.
The images remain third-party assets under the source site's terms.

## Use

Open the provided four-view wardrobe workflow. Click Browse Wardrobe, filter by
category or search, then click an outfit. The selection updates the preview and
fills the portrait/front/back clothing slots. Save to retain the outfit ID.
The body-reference panel and privacy switch remain independent. All body panels
retain the original headless/neckless instructions; MOSS can still render short
neck sections. Preview images do not become image conditioning.

This package supplies layout and wardrobe nodes, not the MOSS model loader or
weights. Keep the original MOSS integration, SFT model and sixteen-step accelerator
installed. Select the model folder and LoRA filename for your own installation.

## Publishing

GitHub releases are versioned. Comfy Registry requires an actual publisher ID and
publishing API key; neither is fabricated or embedded in this repository.
See https://docs.comfy.org/registry/publishing for registration.
