#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["huggingface_hub>=0.25"]
# ///
"""Download BiomniBench-DA tasks and split what the agent may see from what only the grader sees.

Agent-visible data goes to $OSB_HOME/data/<task>/ (default ~/osb). The prompt, task.toml and
rubric go to $OSB_GRADING/<task>/ (default ~/.cache/osb-grading), away from every run workdir,
so an agent exploring its surroundings does not stumble on the answer key.

    HF_TOKEN=... uv run fetch.py --skill sc-rnaseq --controls 6   # what run.py will select for one skill
    HF_TOKEN=... uv run fetch.py --labeled                         # every covered and control task
    HF_TOKEN=... uv run fetch.py da-12-2                           # specific tasks, e.g. before label.py

The dataset is pinned to HF_REVISION, and each task's grading folder records it in hf_revision.txt.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OSB_HOME = Path(os.environ.get("OSB_HOME", Path.home() / "osb"))
OSB_GRADING = Path(os.environ.get("OSB_GRADING", Path.home() / ".cache" / "osb-grading"))
HF_REPO = "phylobio/BiomniBench-DA"
# Dataset commit behind every published result (lastModified 2026-06-19).
HF_REVISION = "e1c8ca5e11a620087bc48d97888eb69176a1f235"


def main() -> None:
    from huggingface_hub import snapshot_download

    import taskset

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tasks", nargs="*", help="task ids")
    ap.add_argument("--skill", help="the tasks labeled as covered by this skill")
    ap.add_argument("--controls", type=int, help="number of control tasks to add (default: all)")
    ap.add_argument("--labeled", action="store_true", help="every covered and control task in tasks.json")
    ap.add_argument("--seed", type=int, default=20261014, help="must match run.py --seed when using --controls")
    args = ap.parse_args()
    tasks = args.tasks
    if not tasks and (args.skill or args.labeled or args.controls is not None):
        tasks = taskset.select(taskset.load()["tasks"], args.skill, args.controls, args.seed)
    if not tasks:
        ap.error("pass task ids, --skill or --labeled")

    staging = OSB_HOME / "hf-staging"
    snapshot_download(HF_REPO, repo_type="dataset", revision=HF_REVISION, allow_patterns=[f"{t}/*" for t in tasks], local_dir=staging)
    try:
        for task in tasks:
            src = staging / task
            data = OSB_HOME / "data" / task
            if not data.exists():
                data.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(src / "environment" / "data", data)
            grading = OSB_GRADING / task
            grading.mkdir(parents=True, exist_ok=True)
            for name in ("instruction.md", "task.toml"):
                shutil.copy2(src / name, grading / name)
            shutil.copytree(src / "tests", grading / "tests", dirs_exist_ok=True)
            (grading / "hf_revision.txt").write_text(HF_REVISION + "\n")
            print(f"{task}: data -> {data}, grading -> {grading}")
    finally:
        # The staged copy still holds tests/rubric.txt next to the data.
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
