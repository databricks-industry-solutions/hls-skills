#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["databricks-sdk>=0.40", "openai>=1.40", "httpx", "pyyaml>=6"]
# ///
"""Label which HLS skills each BiomniBench-DA task falls under, before any run.

Two labelers, each a different LLM on Foundation Model APIs, work independently. Each sees only the task's
instruction.md and the name and description of every published skill at --skills-ref, never the rubric, the data
or any score. taskset.combine turns their two answers into `covered` (a shared skill), `control` (no skill from
either) or `disputed`. Each labeler's answers go to labels/<name>_labeler_{a,b}.json, the settings to
labels/<name>_meta.json. With --write, the labels go into tasks.json: relabeling every task there replaces the
labels; labeling some tasks updates or adds just those, and records the run under `labels.updates`.

Freeze the labels (commit them) before the first scored run. When the skills change, relabel at the new commit.

    uv run label.py --labeled --skills-ref main --name main --profile <profile> --write
    uv run label.py da-12-2 da-20-3 --skills-ref main --name new --profile <profile>
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

import taskset
from judge import complete
from run import OSB_GRADING, git, skill_bundles

HERE = Path(__file__).resolve().parent
LABELERS = {"a": "databricks-gemini-3-8-flash", "b": "databricks-claude-sonnet-5-5"}

PROMPT = """You decide which agent skills apply to a data analysis task. A skill applies only if the analysis the task asks for is what the skill's description says it is for. A task may fit several skills or none; most tasks fit none.

Skills:
{skills}

Task:
<task>
{task}
</task>

Respond with only a JSON object: {{"skills": [<names of the skills that apply, or empty>], "reason": "<one sentence>"}}"""


def skill_descriptions(sha: str) -> dict[str, str]:
    """{skill name: description} from each published skill's SKILL.md frontmatter at a commit."""
    out = {}
    for name, files in skill_bundles(sha).items():
        front = re.match(r"---\n(.*?)\n---", files["SKILL.md"].decode(), flags=re.DOTALL)
        out[name] = " ".join(str(yaml.safe_load(front.group(1))["description"]).split())
    return out


def prompt_for(skills: dict[str, str], task_text: str) -> str:
    listing = "\n".join(f"- {name}: {desc}" for name, desc in sorted(skills.items()))
    return PROMPT.format(skills=listing, task=task_text.strip())


def parse(response: str, known: set[str]) -> dict:
    start, end = response.find("{"), response.rfind("}")
    try:
        result = json.loads(response[start : end + 1])
    except ValueError:
        return {"skills": [], "reason": f"unparseable: {response[:200]}", "unparseable": True}
    named = [s for s in result.get("skills") or [] if isinstance(s, str)]
    out = {"skills": sorted(s for s in named if s in known), "reason": str(result.get("reason", ""))}
    if unknown := sorted(set(named) - known):
        out["unknown_skills"] = unknown
    return out


def main() -> None:
    from databricks.sdk import WorkspaceClient

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tasks", nargs="*", help="task ids (fetched with fetch.py)")
    ap.add_argument("--labeled", action="store_true", help="relabel every task already in tasks.json")
    ap.add_argument("--skills-ref", required=True, help="git ref whose published skills are offered")
    ap.add_argument("--name", required=True, help="label file prefix under labels/")
    ap.add_argument("--profile", required=True, help="Databricks CLI profile for Foundation Model APIs")
    ap.add_argument("--labeler-a", default=LABELERS["a"], help="serving endpoint of labeler A")
    ap.add_argument("--labeler-b", default=LABELERS["b"], help="serving endpoint of labeler B")
    ap.add_argument("--write", action="store_true", help="write these labels into tasks.json")
    args = ap.parse_args()

    doc = taskset.load()
    tasks = args.tasks or ([t["task_id"] for t in doc["tasks"]] if args.labeled else [])
    if not tasks:
        ap.error("pass task ids or --labeled")
    missing = [t for t in tasks if not (OSB_GRADING / t / "instruction.md").is_file()]
    if missing:
        raise SystemExit(f"Run fetch.py first; missing: {missing}")

    sha = git("rev-parse", "--verify", f"{args.skills_ref}^{{commit}}")
    skills = skill_descriptions(sha)
    prompts = {t: prompt_for(skills, (OSB_GRADING / t / "instruction.md").read_text()) for t in tasks}
    client = WorkspaceClient(profile=args.profile).serving_endpoints.get_open_ai_client().with_options(
        timeout=300, max_retries=3)
    endpoints = {"a": args.labeler_a, "b": args.labeler_b}
    labels: dict[str, dict[str, dict]] = {}
    for key, endpoint in endpoints.items():
        with ThreadPoolExecutor(max_workers=4) as pool:
            answers = pool.map(lambda t: parse(complete(client, endpoint, prompts[t]), set(skills)), tasks)
            labels[key] = dict(zip(tasks, answers))
        path = HERE / "labels" / f"{args.name}_labeler_{key}.json"
        path.write_text(json.dumps(labels[key], indent=1) + "\n")
        print(f"labeler {key} ({endpoint}): {path}")

    meta = {
        "skills_sha": sha,
        "skills": sorted(skills),
        "labelers": endpoints,
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "labeled_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    (HERE / "labels" / f"{args.name}_meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    topics = {t["task_id"]: t["topic"] for t in doc["tasks"] if t.get("topic")}
    rows = []
    for t in tasks:
        coverage, expected = taskset.combine(labels["a"][t]["skills"], labels["b"][t]["skills"])
        rows.append({"task_id": t, **({"topic": topics[t]} if t in topics else {}), "coverage": coverage,
                     "hls_skills": expected})
        print(f"{t}: {coverage} {expected}  (a: {labels['a'][t]['skills']}, b: {labels['b'][t]['skills']})")
    counts = {c: sum(r["coverage"] == c for r in rows) for c in taskset.COVERAGE}
    print(f"{len(rows)} tasks: {counts}")
    unparseable = [f"{k}/{t}" for k in labels for t in tasks if labels[k][t].get("unparseable")]
    if unparseable:
        raise SystemExit(f"unparseable answers, tasks.json not written: {unparseable}")
    if args.write:
        files = [f"labels/{args.name}_labeler_{k}.json" for k in endpoints]
        taskset.save(taskset.merge(doc, rows, {**meta, "method": "label.py", "labeler_files": files}))
        print(f"wrote {taskset.TASKS_JSON}")


if __name__ == "__main__":
    main()
