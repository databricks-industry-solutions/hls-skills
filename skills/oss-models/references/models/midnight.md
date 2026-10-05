# Midnight model reference

## Identity

* Model family: Midnight (pathology tile-embedding foundation model)
* Upstream code: https://github.com/kaiko-ai/midnight
* HuggingFace: https://huggingface.co/kaiko-ai/midnight
* Paper: https://arxiv.org/abs/2404.17700 ("Midnight: Towards Better Understanding of Night-time Vision-Language")
* Reviewed date: 2026-10-03
* Code license: MIT
* Weight terms: MIT (verify on model card before distribution)
* Architecture: DINOv2-based ViT (Vision Transformer) fine-tuned on histopathology tiles

## What this model does

Midnight is a pathology foundation model that produces embedding vectors from
histopathology image tiles. It is built on DINOv2 (a self-supervised ViT) and
fine-tuned on a large corpus of whole-slide-image (WSI) tiles. The embeddings
are used for tile retrieval, slide classification, tissue segmentation, and
biomarker prediction. This reference covers **online inference** — single or
small-batch tile embedding queries to a Model Serving endpoint.

## Inputs and outputs

### Serving contract

The model accepts image tiles. For Model Serving, encode tiles as base64
strings in the request payload.

| Column | Type | Description |
|--------|------|-------------|
| `image` | `str` (base64) | A single histopathology tile, PNG or JPEG encoded, then base64-encoded. |

**Output**: A JSON object with an `embedding` key containing a float list
(dimension depends on ViT variant — typically 384 or 768).

### Extra params

| Parameter | Default | Notes |
|-----------|---------|-------|
| `tile_size` | `224` | Resize target for the tile before ViT forward pass. |

## Input example

A single-tile embedding request via the Model Serving REST API:

```json
{
  "dataframe_records": [
    {
      "image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    }
  ]
}
```

The `image` field is a base64-encoded PNG or JPEG tile (the example above is a
1×1 pixel red PNG). A real request would contain a 224×224 histopathology tile.

Expected response:

```json
{
  "predictions": [
    {
      "embedding": [0.0123, -0.456, 0.789, "...768 floats total..."]
    }
  ]
}
```

## Variants

| Variant | Params | d_model | GPU requirement | Notes |
|---------|--------|---------|----------------|-------|
| midnight (base) | ~86M | 768 | GPU_SMALL (A10G) | Default HF checkpoint |

## Download and staging

Use `huggingface_hub.snapshot_download` to download all files. No special Xet
handling expected — standard HF download.

```python
import os
os.environ["HF_HUB_DISABLE_XET"] = "1"  # safety: disable Xet in case env pre-enables it

from huggingface_hub import snapshot_download

MODEL_DIR = "/Volumes/mmt_aws_usw2/skills/<arm>/models/midnight"
snapshot_download(
    repo_id="kaiko-ai/midnight",
    local_dir=MODEL_DIR,
    local_dir_use_symlinks=False,
)
```

## Dependencies

```
torch
torchvision
timm
Pillow
huggingface_hub
```

**Pin note**: Midnight uses `timm` for the DINOv2 backbone. Check the
repo's `requirements.txt` for exact version pins. On AI Runtime v5,
`torch` and `torchvision` are pre-installed.

## PyFunc wrapper pattern

The wrapper must:
1. Load the model weights and preprocessing transforms in `load_context`
2. Accept base64-encoded image strings in `predict`
3. Decode, preprocess (resize + normalize), run inference, return embedding

```python
import mlflow
import torch
import base64
import io
from PIL import Image

class MidnightWrapper(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        import sys
        # Purge stale module caches (per SKILL.md §11)
        for mod_name in list(sys.modules):
            if any(k in mod_name for k in ["timm", "midnight"]):
                del sys.modules[mod_name]

        model_dir = context.artifacts["model_dir"]
        # Load model — adapt to actual repo structure
        # Example: timm.create_model("vit_base_patch16_224.dino", ...)
        # Load checkpoint weights from model_dir
        self.model = ...  # TODO: adapt to actual Midnight loading pattern
        self.model.eval()
        self.transform = ...  # TODO: standard DINOv2 preprocessing

    def predict(self, context, model_input, params=None):
        import logging
        logger = logging.getLogger("midnight")
        results = []
        for _, row in model_input.iterrows():
            img_b64 = row["image"]
            img_bytes = base64.b64decode(img_b64)
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            tensor = self.transform(img).unsqueeze(0)
            with torch.no_grad():
                emb = self.model(tensor).squeeze(0).cpu().tolist()
            results.append({"embedding": emb})
        return results
```

> **Note**: The wrapper above is a skeleton — adapt to the actual Midnight
> repo loading pattern (check `kaiko-ai/midnight` for the model class and
> preprocessing). The key patterns from SKILL.md still apply: sys.modules
> purge in `load_context`, file-based logging, GPU_SMALL for deploy.

## Registration

Follow SKILL.md §23 for AI Gateway configuration:

```python
from databricks.sdk.service.serving import (
    AiGatewayConfig,
    AiGatewayInferenceTableConfig,
    AiGatewayUsageTrackingConfig,
)

import datetime
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")

ai_gateway = AiGatewayConfig(
    inference_table_config=AiGatewayInferenceTableConfig(
        catalog_name="mmt_aws_usw2",
        schema_name="skills",
        table_name_prefix=f"midnight_{ts}",
        enabled=True,
    ),
    usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),
)
```

## Deployment

Use `ServingModelWorkloadType.GPU_SMALL` (A10G). Image models benefit
from GPU for ViT forward pass.

```python
from databricks.sdk.service.serving import (
    ServedEntityInput,
    ServingModelWorkloadType,
)

served = ServedEntityInput(
    name="midnight-served",
    entity_name="mmt_aws_usw2.skills.midnight",
    entity_version="1",
    workload_type=ServingModelWorkloadType.GPU_SMALL,
    workload_size="Small",
    scale_to_zero_enabled=True,
)
```

## Validation checklist

- [ ] Model loads without error on GPU_SMALL
- [ ] Base64 image input → embedding output round-trip works
- [ ] Embedding dimension matches expected ViT hidden size
- [ ] Embeddings are non-degenerate (not all zeros, reasonable norm)
- [ ] Endpoint reaches READY state
- [ ] SDK query with base64 tile succeeds

## Known issues

* **Image size**: Large tiles (>1024px) may need downsampling before
  encoding. The wrapper should handle resize to `tile_size`.
* **Memory**: Batch inference with many tiles may exceed A10G VRAM.
  Keep batch size small for Model Serving (1-4 tiles per request).
* **Dependencies**: `timm` version compatibility with the checkpoint —
  check the repo's pinned version.
