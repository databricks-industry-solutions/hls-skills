# Accelerator index

Load only the reference that matches the request. Add a row when an accelerator is added.

| Accelerator | Domain | Smallest path | Needs admin for full install | Reference |
| --- | --- | --- | --- | --- |
| Pixels | DICOM medical imaging | Library from a repo clone (`Catalog`, `DicomMetaExtractor`); test on serverless first | Yes | [pixels.md](pixels.md) |
| Genesis Workbench | Proteins, small molecules, single cell, genomics, BioNeMo | Full install only | Yes | [genesis-workbench.md](genesis-workbench.md) |
| funke-hl7v2 | HL7v2 clinical messages (ADT, ORU, ORM, SIU, VXU) | `%pip install` from GitHub, then the `parse_hl7v2_msg` UDF on serverless | No | [funke-hl7v2.md](funke-hl7v2.md) |
