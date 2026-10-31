# Reference workflow setup

Use **ComfyUI 0.43.0** with the native MOSS implementation. This release includes
the exact small core extension used by the selected reference LoRA: spatial
reference offsets, reference-key visibility and panel-scoped text visibility.
A stock ComfyUI install does not yet include this extension.

## 1. Install the node pack and requirements

Install/update **MOSS Card Layout and Wardrobe** through Manager or its Git URL.
Use your ComfyUI Python for requirements, for example from the ComfyUI directory:

```bash
python -m pip install -r custom_nodes/ComfyUI-MOSS-Card-Layout/requirements.txt
```

For Windows Portable, run the same command with `python_embeded\python.exe` from
the portable root and prefix the requirements path with `ComfyUI\`.

## 2. Install reference support once

Stop ComfyUI. From the ComfyUI directory:

```bash
python custom_nodes/ComfyUI-MOSS-Card-Layout/install_reference_support.py --comfy-root . --apply
```

Replace the node-directory spelling with your installed folder if it differs.
Omit `--apply` for a read-only preflight. The installer checks both complete file
hashes before changing anything, preserves `.moss-studio-original` backups,
verifies the patched hashes, and refuses unknown or locally modified core files.
An already-patched install is detected without further changes. Restart ComfyUI.
An update of ComfyUI core may replace these files; rerun the preflight afterwards.

## 3. Models

Use the original [MOSS-Image-SFT HF snapshot](https://huggingface.co/OpenMOSS-Team/MOSS-Image-SFT),
including `transformer`, `text_encoder`, and the original FP32-compute small-decoder
`vae`. Place it in `ComfyUI/models/diffusers/MOSS-Image-SFT` or enter the full path
in **MOSS HF Snapshot - Native**. Reuse an existing complete snapshot.

Put [MOSS-Character-Studio-Reference-BF16.safetensors](https://huggingface.co/Coffmeteor/MOSS-Character-Studio/resolve/main/MOSS-Character-Studio-Reference-BF16.safetensors)
in `ComfyUI/models/loras/moss/`. Workflow model metadata supplies the download URL.

```text
SHA-256: b5bdc6a969a312025ce50ebe5f94463d5ad86dc5e0f260b915a8bfb1c806d477
Bytes: 495514728
Strength: 1.0
Trigger: none
```

The MediaPipe face-landmarker is a separate 3.76 MB dependency fetched and verified
on first reference use. It is stored under `models/mediapipe`, not inside the node
package. Offline users can place the pinned [official model](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task)
there first (SHA-256 `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`).

## 4. Open and run

Import `example_workflows/Character Studio - Reference.json`. Select face and
outfit previews, set coverage and run. Its API counterpart is provided for
automation. `auto_portrait` performs the selected framing; `center_crop` is an
explicit alternative, with different framing behavior.

The verified recipe is 25 steps, CFG 3, Euler/sgm_uniform, AuraFlow shift 5,
SLG single layer 22, full-portrait anchoring and panel-scoped text. Both text
self-attention mask debugging flags stay off. Do not load the 16-step text
accelerator into this workflow.
