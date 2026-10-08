# Midnight model reference

> **Status: work in progress — needs workspace testing.** Upstream model identity,
> preprocessing, and embedding extraction are documented below; the Databricks
> PyFunc and Model Serving path is provisional until validated in a workspace.

## Identity

* Model family: Midnight (pathology tile-embedding foundation model)
* Upstream code: https://github.com/kaiko-ai/midnight
* HuggingFace: https://huggingface.co/kaiko-ai/midnight
* Paper: https://arxiv.org/abs/2504.05186 ("Training state-of-the-art pathology foundation models with orders of magnitude less data")
* Reviewed date: 2026-10-08
* Code license: MIT
* Public Midnight-12k weight terms: MIT; restricted-variant terms: confirm upstream
* Architecture: DINOv2-based pathology foundation model; the public Hugging Face
  checkpoint metadata names `facebook/dinov2-giant` as its base model

## What this model does

Midnight is a pathology foundation model that produces embedding vectors from
histopathology image tiles. The public Midnight-12k checkpoint was trained on
12,000 TCGA whole-slide images. Its model card documents embedding extraction
for classification and segmentation; the paper evaluates tile-level,
slide-level, and gene-expression-prediction tasks. This reference proposes an
**online inference** contract for single or small-batch tile embedding queries,
but that Model Serving path has not yet been workspace-tested.

## Inputs and outputs

### Proposed serving contract

The upstream model accepts image tiles. This provisional Model Serving wrapper
encodes tiles as base64 strings in the request payload.

| Column | Type | Description |
|--------|------|-------------|
| `image` | `str` (base64) | A single histopathology tile, PNG or JPEG encoded, then base64-encoded. |

**Output**: A JSON object with an `embedding` key containing the classification
embedding defined by the upstream model card. The public checkpoint config has
`hidden_size=1536`; concatenating the CLS token with the mean patch embedding
therefore produces 3,072 floats.

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
      "embedding": [0.0123, -0.456, 0.789, "...3072 floats total..."]
    }
  ]
}
```

## Variants

| Variant | Access | Upstream architecture | Embedding details | Notes |
|---------|--------|-----------------------|-------------------|-------|
| Midnight-12k | Public, MIT | DINOv2 giant | 1,536 hidden size; 3,072-float classification embedding | Public HF checkpoint |
| Midnight-92k | Restricted | Confirm upstream | Confirm upstream | Trained with proprietary NKI data |
| Midnight-92k/392 | Restricted | Confirm upstream | Confirm upstream | High-resolution post-trained variant |

## Download and staging

Use `huggingface_hub.snapshot_download` to download the public checkpoint.
Confirm the current Hugging Face transfer backend in the target environment;
the upstream model card does not require a special Xet setting.

```python
from huggingface_hub import snapshot_download

MODEL_DIR = "/Volumes/<catalog>/skills/<arm>/models/midnight"
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
transformers
Pillow
huggingface_hub
```

**Pin note**: The public checkpoint config records Transformers 4.43.4, and the
model card loads it with `AutoModel`. Confirm currently supported versions in
the upstream repository and the target Databricks runtime before pinning the
serving environment.

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
from transformers import AutoModel
from torchvision.transforms import v2

class MidnightWrapper(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        model_dir = context.artifacts["model_dir"]
        self.model = AutoModel.from_pretrained(model_dir)
        self.model.eval()
        self.transform = v2.Compose([
            v2.Resize(224),
            v2.CenterCrop(224),
            v2.ToTensor(),
            v2.Normalize(mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5)),
        ])

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
                hidden = self.model(tensor).last_hidden_state
                cls_embedding = hidden[:, 0, :]
                patch_embedding = hidden[:, 1:, :].mean(1)
                emb = torch.cat([cls_embedding, patch_embedding], dim=-1)
                emb = emb.squeeze(0).cpu().tolist()
            results.append({"embedding": emb})
        return results
```

> **Note**: Model loading, normalization, and classification-embedding
> extraction follow the upstream card. The DataFrame/base64 transport and
> Databricks serving configuration remain provisional until workspace-tested.

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
        catalog_name="<catalog>",
        schema_name="skills",
        table_name_prefix=f"midnight_{ts}",
        enabled=True,
    ),
    usage_tracking_config=AiGatewayUsageTrackingConfig(enabled=True),
)
```

## Deployment

The following `GPU_SMALL` configuration is a starting point, not a validated
requirement. Confirm workload compatibility, memory use, and latency in the
target workspace before treating it as the deployment recommendation.

```python
from databricks.sdk.service.serving import (
    ServedEntityInput,
    ServingModelWorkloadType,
)

served = ServedEntityInput(
    name="midnight-served",
    entity_name="<catalog>.skills.midnight",
    entity_version="1",
    workload_type=ServingModelWorkloadType.GPU_SMALL,
    workload_size="Small",
    scale_to_zero_enabled=True,
)
```

## Validation checklist

- [ ] Model loads without error on GPU_SMALL
- [ ] Base64 image input → embedding output round-trip works
- [ ] Classification embedding contains 3,072 floats for the public checkpoint
- [ ] Embeddings are non-degenerate (not all zeros, reasonable norm)
- [ ] Endpoint reaches READY state
- [ ] SDK query with base64 tile succeeds

## Known issues

* **Preprocessing**: Use the upstream 224×224 resize/crop and normalization
  mean/std of `(0.5, 0.5, 0.5)`; confirm upstream before changing them.
* **Restricted variants**: Midnight-92k and Midnight-92k/392 require restricted
  access. Confirm upstream terms before downloading or distributing them.
* **Serving capacity**: GPU type, batch size, memory use, and latency have not
  been workspace-tested. Confirm them on the target runtime.
* **Dependencies**: Confirm the current supported Transformers and Torch
  versions upstream before pinning the serving environment.
