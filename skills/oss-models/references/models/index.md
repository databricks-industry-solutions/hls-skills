# HLS model reference index

The core skill loads these references on demand. Add a row when a new model family is introduced.

| Family | Primary modality | Default deployment bias | Reference |
| --- | --- | --- | --- |
| Geneformer | single-cell transcriptomics | bounded serving (A10G); two deployment paths (serving tested, eval WIP): V1-10M (dim=256) and BioNeMo V2-316M (dim=1152) | [geneformer.md](geneformer.md) |
| scGPT | single-cell transcriptomics | batch or bounded serving with explicit schema | [scgpt.md](scgpt.md) |
| Scimilarity | single-cell embedding and similarity | serving for bounded queries; Jobs for large catalogs | [scimilarity.md](scimilarity.md) |
| AlphaFold/OpenFold | protein structure prediction | Jobs or hybrid | [alphafold-openfold.md](alphafold-openfold.md) |
| Boltz | biomolecular structure and interaction prediction | Jobs or hybrid | [boltz.md](boltz.md) |
| TEDDY | single-cell transcriptomics (scRNA-seq embeddings) | serving for bounded per-cell queries; Jobs for full AnnData batch | [teddy.md](teddy.md) |
| Midnight | histopathology tile embedding | serving for bounded tile queries (GPU_SMALL) | [midnight.md](midnight.md) |

To add a family:

* copy [model-template.md](../model-template.md)
* pin code and weight sources
* add at least one transport example and one negative test
* document serving versus Jobs constraints
* add a row here
* record the change and upstream version in the repository changelog
