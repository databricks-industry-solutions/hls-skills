#!/usr/bin/env python3
"""Synthetic data for the x12-claims-ingest benchmark tasks (one folder per task) + grader-only keys.

Task datasets go to SKILL_EVAL_DATA_DIR/<task_id>/ (what the arms read). Answer keys go to
SKILL_EVAL_GRADER_DIR/<task_id>_key.json, a separate Volume the arms are never pointed at.

Usage:
    python3 generate_data.py                       # defaults below
    SKILL_EVAL_DATA_DIR=/Volumes/c/s/eval/x12-claims-ingest \
    SKILL_EVAL_GRADER_DIR=/Volumes/c/s/grader/x12-claims-ingest python3 generate_data.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import generate_837  # noqa: E402

DATA_DIR = os.environ.get("SKILL_EVAL_DATA_DIR", "/Volumes/hls_amer_catalog/x12_claims_ingest_test/eval/x12-claims-ingest")
GRADER_DIR = os.environ.get("SKILL_EVAL_GRADER_DIR",
                            "/Volumes/hls_amer_catalog/x12_claims_ingest_test/grader/x12-claims-ingest")

PIPE_CRLF = {"el": "|", "comp": "^", "newline": "\r\n"}
ONE_LINE = {"newline": ""}
ALT_COMP = {"comp": ">"}

TASKS = {
    # easy: clean professional files, default delimiters, no traps
    "x12-001": (101, [
        {"name": "clinic_a_20260915.x12", "kind": "P", "style": {}, "tx": [(8, False)], "ctrl": 201},
        {"name": "clinic_b_20260916.x12", "kind": "P", "style": {}, "tx": [(6, False)], "ctrl": 202},
    ]),
    # hard: 837P + 837I, three delimiter styles, multi-transaction file, patient + COB loops
    "x12-002": (202, [
        {"name": "ch_batch_0917.edi", "kind": "P", "style": PIPE_CRLF, "tx": [(6, True), (4, True)], "ctrl": 301},
        {"name": "hospital_0917.edi", "kind": "I", "style": ONE_LINE, "tx": [(8, True)], "ctrl": 302},
        {"name": "ch_batch_0918.edi", "kind": "P", "style": ALT_COMP, "tx": [(5, True)], "ctrl": 303},
    ]),
    # edge: a truncated transfer and a non-X12 file that still has an .x12 name
    "x12-003": (303, [
        {"name": "prof_0920.x12", "kind": "P", "style": {}, "tx": [(6, True)], "ctrl": 401},
        {"name": "prof_0921.x12", "kind": "P", "style": {}, "tx": [(4, False)], "ctrl": 402, "truncate": True},
        {"name": "inst_0921.x12", "kind": "I", "style": ONE_LINE, "tx": [(5, True)], "ctrl": 403},
        {"name": "remit_0921.x12", "raw": "CLAIM_ID|PAID_AMT|STATUS\nC100|125.00|PAID\nC101|0.00|DENIED\n"},
    ]),
    # hard: same mix, but delivered as a serverless Lakeflow pipeline
    "x12-004": (404, [
        {"name": "prof_0925.x12", "kind": "P", "style": {}, "tx": [(6, True)], "ctrl": 501},
        {"name": "inst_0925.x12", "kind": "I", "style": ONE_LINE, "tx": [(6, True)], "ctrl": 502},
    ]),
    # hard (mapping): 4010A1 archive + 5010 batch with line-level rendering and varied dx pointers, then
    # correction files two weeks later (replacements CLM05-3=7 and voids =8, with REF*F8)
    "x12-005": (505, [
        {"name": "archive_2011_prof.x12", "kind": "P", "version": "4010", "style": {}, "tx": [(5, True)],
         "ctrl": 601, "gs_date": "20110701"},
        {"name": "batch_1001_prof.x12", "kind": "P", "style": {},
         "tx": [(6, True, {"line_rendering": True, "varied_pointers": True})], "ctrl": 602, "gs_date": "20261001"},
        {"name": "batch_1001_inst.x12", "kind": "I", "style": ONE_LINE, "tx": [(5, True)], "ctrl": 603,
         "gs_date": "20261001"},
        {"name": "batch_1015_prof_corrections.x12", "kind": "P", "style": {}, "ctrl": 604, "gs_date": "20261015",
         "resend": [{"pcn": "PCN000007", "freq": "7"}, {"pcn": "PCN000009", "freq": "7"},
                    {"pcn": "PCN000011", "freq": "8"}]},
        {"name": "batch_1015_inst_corrections.x12", "kind": "I", "style": ONE_LINE, "ctrl": 605,
         "gs_date": "20261015",
         "resend": [{"pcn": "PCN000014", "freq": "7"}, {"pcn": "PCN000018", "freq": "8"}]},
    ]),
    # edge (quality): planted defects at known claims, plus duplicate resubmissions a week later
    "x12-006": (606, [
        {"name": "q_prof_a.x12", "kind": "P", "style": {}, "ctrl": 701, "gs_date": "20261005",
         "tx": [(14, True, {"sub_overrides": {
             3: {"defects": ["NPI_INVALID"]}, 4: {"defects": ["ICD10_FORMAT"]},
             5: {"defects": ["PROCEDURE_CODE_FORMAT"]}, 6: {"defects": ["POS_INVALID"]},
             7: {"defects": ["DX_POINTER_INVALID"]}, 8: {"defects": ["TOTAL_MISMATCH"]},
             9: {"defects": ["DATE_INVALID"]}}})]},
        {"name": "q_prof_b.x12", "kind": "P", "style": {}, "ctrl": 702, "gs_date": "20261005",
         "tx": [(3, False, {"po_box": True})]},
        {"name": "q_inst_a.x12", "kind": "I", "style": ONE_LINE, "ctrl": 703, "gs_date": "20261005",
         "tx": [(12, True, {"sub_overrides": {
             3: {"defects": ["REVENUE_CODE_FORMAT"]}, 4: {"defects": ["NPI_INVALID"]},
             5: {"defects": ["DATE_INVALID"]}, 6: {"defects": ["ICD10_FORMAT"]}}})]},
        {"name": "q_inst_b.x12", "kind": "I", "style": ONE_LINE, "ctrl": 704, "gs_date": "20261005",
         "tx": [(2, False, {"zip5": True})]},
        {"name": "q_resubmit_1012.x12", "kind": "P", "style": {}, "ctrl": 705, "gs_date": "20261012",
         "resend": [{"pcn": "PCN000012", "freq": "dup"}, {"pcn": "PCN000013", "freq": "dup"}]},
    ]),
}

# Pinned facts used by expectations.json; generation fails loudly if the generator drifts.
EXPECTED = {
    "x12-001": {"claims": 14, "bad_files": []},
    "x12-002": {"claims": 27, "bad_files": []},
    "x12-003": {"claims": 13, "bad_files": ["prof_0921.x12", "remit_0921.x12"]},
    "x12-004": {"claims": 14, "bad_files": []},
    "x12-005": {"claims": 17, "bad_files": []},       # 19 originals, 3 replaced, 2 voided
    "x12-006": {"claims": 35, "bad_files": []},       # 18 claims with planted defects, 17 clean
}


def build_all() -> dict:
    out = {}
    for task_id, (seed, spec) in TASKS.items():
        files, key = generate_837.build(seed=seed, spec=spec)
        bad = sorted({t["file"] for t in key["transactions"] if t["transaction_status"] != "ok"})
        got = {"claims": len(key["claims"]), "bad_files": bad}
        assert got == EXPECTED[task_id], f"{task_id}: generator drifted, {got} != {EXPECTED[task_id]}"
        out[task_id] = (files, key)
    return out


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Seed benchmark task data + grader keys")
    ap.add_argument("--tasks", nargs="*", help="only these task ids (default: all); keeps earlier tasks' data unchanged")
    only = set(ap.parse_args().tasks or [])
    for task_id, (files, key) in build_all().items():
        if only and task_id not in only:
            continue
        d = Path(DATA_DIR) / task_id
        d.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (d / name).write_text(content)
        Path(GRADER_DIR).mkdir(parents=True, exist_ok=True)
        (Path(GRADER_DIR) / f"{task_id}_key.json").write_text(json.dumps(key, indent=2))
        print(f"{task_id}: {len(files)} files, {len(key['claims'])} valid claims -> {d}")


if __name__ == "__main__":
    main()
