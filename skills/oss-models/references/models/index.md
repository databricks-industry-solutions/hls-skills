# HLS model reference index

The core skill loads these references on demand. Add a row when a new model family is introduced.

| Family | Primary modality | Default deployment bias | Reference |
| --- | --- | --- | --- |
| Geneformer | single-cell transcriptomics | batch or bounded serving after preprocessing | [geneformer.md](geneformer.md) |
| scGPT | single-cell transcriptomics | batch or bounded serving with explicit schema | [scgpt.md](scgpt.md) |
| Scimilarity | single-cell embedding and similarity | serving for bounded queries; Jobs for large catalogs | [scimilarity.md](scimilarity.md) |
| AlphaFold/OpenFold | protein structure prediction | Jobs or hybrid | [alphafold-openfold.md](alphafold-openfold.md) |
| Boltz | biomolecular structure and interaction prediction | Jobs or hybrid | [boltz.md](boltz.md) |

To add a family:

* copy [model-template.md](../model-template.md)
* pin code and weight sources
* add at least one transport example and one negative test
* document serving versus Jobs constraints
* add a row here
* record the change and upstream version in the repository changelog
