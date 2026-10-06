# Databricks notebook source
#!/usr/bin/env python3
"""Generate four GSE164471-derived integrated RNA-seq evaluation datasets."""

from __future__ import annotations

import gzip
import io
import json
import os
import re
import urllib.request
from pathlib import Path

import pandas as pd


COUNTS_URL = (
    "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE164nnn/GSE164471/suppl/"
    "GSE164471_GESTALT_Muscle_ENSG_counts_annotated.csv.gz"
)
GMT_URL = (
    "https://maayanlab.cloud/Enrichr/geneSetLibrary?mode=text&"
    "libraryName=MSigDB_Hallmark_2020"
)
OUT_DIR = "/Volumes/hls_amer_catalog/vital_skills/eval"
SAMPLE_PATTERN = re.compile(
    r"^MUSCLE_AGE(?P<age>\d+)_(?P<sex>[FM])_"
    r"GROUP(?P<age_band>20_34|35_49|50_64|65_79|80_PLUS)_"
)


def download_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        return response.read()


def load_counts() -> pd.DataFrame:
    payload = download_bytes(COUNTS_URL)
    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
        return pd.read_csv(stream)


def sample_metadata(sample_columns: list[str]) -> pd.DataFrame:
    records = []
    for column in sample_columns:
        sample_id = column.removesuffix("_COUNT")
        match = SAMPLE_PATTERN.match(sample_id)
        if not match:
            raise ValueError(f"Unexpected sample column: {column}")
        record = match.groupdict()
        record["sample_id"] = sample_id
        record["age"] = int(record["age"])
        record["condition"] = (
            "young" if record["age_band"] == "20_34" else "old"
        )
        records.append(record)
    return pd.DataFrame(records).set_index("sample_id")


def count_columns(metadata: pd.DataFrame) -> list[str]:
    return [f"{sample_id}_COUNT" for sample_id in metadata.index]


def gene_by_sample(
    source: pd.DataFrame, metadata: pd.DataFrame, gene_column: str
) -> pd.DataFrame:
    columns = count_columns(metadata)
    frame = source[[gene_column, *columns]].copy()
    return frame.rename(
        columns={column: column.removesuffix("_COUNT") for column in columns}
    )


def write_common(directory: Path, gmt: bytes) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "MSigDB_Hallmark_2020.gmt").write_bytes(gmt)


def main() -> None:
    output_root = Path(os.environ.get("SKILL_EVAL_DATA_DIR", OUT_DIR))
    source = load_counts()
    gmt = download_bytes(GMT_URL)
    sample_columns = [column for column in source.columns if column.endswith("_COUNT")]
    metadata = sample_metadata(sample_columns)
    comparison = metadata[metadata["age_band"].isin(["20_34", "65_79"])].copy()

    task_001 = output_root / "task_001"
    write_common(task_001, gmt)
    gene_by_sample(source, comparison, "HG19en82 Gene Name").rename(
        columns={"HG19en82 Gene Name": "gene_symbol"}
    ).dropna(subset=["gene_symbol"]).drop_duplicates("gene_symbol").to_csv(
        task_001 / "counts.csv", index=False
    )
    comparison[["condition"]].to_csv(task_001 / "metadata.csv")

    task_002 = output_root / "task_002"
    write_common(task_002, gmt)
    columns_002 = count_columns(comparison)
    annotation_columns = [
        "Tracking_ID",
        "HG19en82 Gene Name",
        "HG19en82 Gene Biotype",
        "HG19en82 Description",
    ]
    source[[*annotation_columns, *columns_002]].rename(
        columns={column: column.removesuffix("_COUNT") for column in columns_002}
    ).to_csv(task_002 / "counts_with_annotations.csv", index=False)
    comparison[["condition", "sex", "age"]].to_csv(task_002 / "metadata.csv")

    task_003 = output_root / "task_003"
    write_common(task_003, gmt)
    task_003_counts = gene_by_sample(
        source, comparison, "HG19en82 Gene Name"
    ).rename(columns={"HG19en82 Gene Name": "gene_symbol"})
    task_003_counts = task_003_counts.dropna(subset=["gene_symbol"]).drop_duplicates(
        "gene_symbol"
    )
    task_003_counts.set_index("gene_symbol").T.rename_axis("sample_id").to_csv(
        task_003 / "counts_samples_by_genes.csv"
    )
    comparison.rename(columns={"condition": "age group"})[
        ["age group", "sex", "age"]
    ].to_csv(task_003 / "metadata_space_column.csv")

    task_004 = output_root / "task_004"
    write_common(task_004, gmt)
    gene_by_sample(source, comparison, "HG19en82 Gene Name").rename(
        columns={"HG19en82 Gene Name": "gene_symbol"}
    ).dropna(subset=["gene_symbol"]).drop_duplicates("gene_symbol").to_csv(
        task_004 / "counts.csv", index=False
    )
    task_004_metadata = comparison[["condition", "sex", "age"]].copy()
    task_004_metadata.loc["METADATA_ONLY_SAMPLE"] = ["old", "F", 75]
    task_004_metadata.to_csv(task_004 / "metadata_with_unmatched_sample.csv")

    manifest = pd.DataFrame(
        [
            {
                "task_id": f"hls-rnaseq-{number:03d}",
                "source": "GSE164471",
                "young_samples": int((comparison.condition == "young").sum()),
                "old_samples": int((comparison.condition == "old").sum()),
            }
            for number in range(1, 5)
        ]
    )
    manifest.to_csv(output_root / "manifest.csv", index=False)
    result = {
        "output_root": str(output_root),
        "tasks": 4,
        "samples_per_task": len(comparison),
    }
    if "dbutils" in globals():
        dbutils.notebook.exit(json.dumps(result))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
