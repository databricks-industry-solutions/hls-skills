"""The labeled BiomniBench-DA tasks in tasks.json, and the tasks to run when testing one skill.

Each task has a `coverage` label from label.py: `covered` (both labelers name a shared skill; `hls_skills` holds the
shared skills), `control` (both labelers name none) or `disputed` (they disagree; `hls_skills` holds the union).
Disputed tasks are never selected, because neither "the skill applies" nor "no skill applies" is settled for them.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

TASKS_JSON = Path(__file__).resolve().parent / "tasks.json"
COVERAGE = ("covered", "control", "disputed")


def combine(a: list[str], b: list[str]) -> tuple[str, list[str]]:
    """Two labelers' skill lists -> (coverage, expected skills)."""
    shared = sorted(set(a) & set(b))
    if shared:
        return "covered", shared
    if not a and not b:
        return "control", []
    return "disputed", sorted(set(a) | set(b))


def load(path: Path = TASKS_JSON) -> dict:
    return json.loads(path.read_text())


def save(doc: dict, path: Path = TASKS_JSON) -> None:
    """One task per line, so a relabel shows up as a readable diff."""
    labels = json.dumps(doc["labels"], indent=2).replace("\n", "\n  ")
    rows = ",\n".join("    " + json.dumps(t) for t in doc["tasks"])
    path.write_text(f'{{\n  "labels": {labels},\n  "tasks": [\n{rows}\n  ]\n}}\n')


def merge(doc: dict, rows: list[dict], labels: dict) -> dict:
    """tasks.json after a labeling run. Relabeling every task replaces the labels; labeling some tasks replaces or
    adds those rows and records the run under labels.updates, so the other frozen labels are kept."""
    if {t["task_id"] for t in doc["tasks"]} <= {r["task_id"] for r in rows}:
        return {"labels": labels, "tasks": rows}
    new = {r["task_id"]: r for r in rows}
    tasks = [new.pop(t["task_id"], t) for t in doc["tasks"]] + list(new.values())
    updates = [*doc["labels"].get("updates", []), {**labels, "tasks": [r["task_id"] for r in rows]}]
    return {"labels": {**doc["labels"], "updates": updates}, "tasks": tasks}


def select(tasks: list[dict], skill: str | None = None, controls: int | None = None, seed: int = 0) -> list[str]:
    """Task ids to run: the tasks covered by `skill` (every covered task if None), plus `controls` control tasks
    drawn with `seed` (every control task if None)."""
    covered = [t["task_id"] for t in tasks if t["coverage"] == "covered" and (skill is None or skill in t["hls_skills"])]
    if skill is not None and not covered:
        raise SystemExit(f"No covered task for skill {skill!r}; run label.py, or pick from: "
                         f"{sorted({s for t in tasks if t['coverage'] == 'covered' for s in t['hls_skills']})}")
    pool = [t["task_id"] for t in tasks if t["coverage"] == "control"]
    if controls is not None:
        pool = sorted(random.Random(seed).sample(pool, min(controls, len(pool))))
    return covered + pool


def task_sets(tasks: list[dict]) -> dict[str, list[str]]:
    sets: dict[str, list[str]] = {c: [] for c in COVERAGE}
    for t in tasks:
        sets[t["coverage"]].append(t["task_id"])
    return sets
