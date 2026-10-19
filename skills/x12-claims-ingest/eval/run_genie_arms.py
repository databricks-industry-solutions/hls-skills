#!/usr/bin/env python3
"""Run the x12-claims-ingest benchmark arms with Genie Code CLI (`genie exec`). Standard library only.

One fresh workdir per (task, arm, replicate). The with_skill arm gets the published skill bundle (no
eval/ or tests/) at ./.agents/skills/x12-claims-ingest/ plus a one-line AGENTS.md (the same nudge as the
BiomniBench harness); the baseline arm gets an empty folder. Genie runs with an isolated GENIE_HOME
(--genie-home) whose config has no AGENTS.md, memories, history or personal skills, so nothing but the
skill differs between arms. Prompts are evalset.json queries verbatim, with <PREFIX> = b_|s_<task>_r<k>_.

Each run writes events.jsonl, stderr.log, answer.txt and run.json in its workdir, and uploads
{"response", "action_log", ...} to <runs-dir>/r<k>/<arm>/<task_id>.json for score_x12_claims_ingest.py
(widgets: runs_dir=<runs-dir>/r<k>, baseline_prefix=b_{task}_r<k>_, with_skill_prefix=s_{task}_r<k>_).
Reruns skip workdirs that already have run.json.

Usage:
    python3 run_genie_arms.py --reps 1 [--tasks x12-001 x12-003] [--arms baseline with_skill] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
SKILL_DIR = EVAL_DIR.parent
SKILL_NAME = SKILL_DIR.name
PUBLISHED = ["SKILL.md", "references", "scripts", "assets"]          # never eval/ or tests/
AGENTS_MD = ("# HLS skills in this project\n\nBefore you write analysis code for biological, clinical or "
             "healthcare data, read the matching skill's `SKILL.md` in `.agents/skills/`. If no skill fits, "
             "continue without one.\n")
ARM_LETTER = {"baseline": "b", "with_skill": "s"}


def prefix(arm: str, task_id: str, rep: int) -> str:
    return f"{ARM_LETTER[arm]}_{task_id.replace('-', '_')}_r{rep}_"


def prepare_workdir(wd: Path, arm: str) -> None:
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True)
    if arm == "with_skill":
        dest = wd / ".agents" / "skills" / SKILL_NAME
        dest.mkdir(parents=True)
        for item in PUBLISHED:
            src = SKILL_DIR / item
            if src.is_dir():
                shutil.copytree(src, dest / item, ignore=shutil.ignore_patterns("__pycache__"))
            elif src.is_file():
                shutil.copy2(src, dest / item)
        (wd / "AGENTS.md").write_text(AGENTS_MD)


def read_events(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(errors="replace").splitlines():
        if line.strip().startswith("{"):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def summarize(events: list[dict]) -> dict:
    """Action log (ordered commands with exit codes), narrative, token usage, whether the skill was opened."""
    actions, messages, usage, opened = [], [], {}, False
    for e in events:
        item = e.get("item") or {}
        if e.get("type") == "item.completed" and item.get("type") == "command_execution":
            cmd = item.get("command", "")
            actions.append(f"[exit {item.get('exit_code')}] {cmd[:400]}")
            opened |= f"skills/{SKILL_NAME}/SKILL.md" in cmd
        elif e.get("type") == "item.completed" and item.get("type") == "agent_message":
            messages.append(item.get("text", ""))
        elif e.get("type") == "turn.completed":
            for k, v in (e.get("usage") or {}).items():
                usage[k] = usage.get(k, 0) + v
    return {"action_log": "\n".join(actions), "messages": messages, "usage": usage, "opened_skill": opened}


def upload(local: Path, remote: str, profile: str) -> None:
    subprocess.run(["databricks", "fs", "cp", str(local), f"dbfs:{remote}", "--overwrite", "-p", profile],
                   check=True, capture_output=True, text=True)


def run_one(item: dict, args) -> dict:
    wd = Path(args.run_root) / f"r{item['rep']}" / item["task_id"] / item["arm"]
    if (wd / "run.json").exists():
        return json.loads((wd / "run.json").read_text())
    prepare_workdir(wd, item["arm"])
    cmd = ["genie", "exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", "--ephemeral",
           "-C", str(wd), "-o", str(wd / "answer.txt"), item["prompt"]]
    env = {**os.environ, "GENIE_HOME": str(Path(args.genie_home).expanduser())}
    start = time.time()
    with open(wd / "events.jsonl", "w") as out, open(wd / "stderr.log", "w") as err:
        try:
            rc = subprocess.run(cmd, cwd=wd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                timeout=args.timeout_min * 60).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    s = summarize(read_events(wd / "events.jsonl"))
    answer = (wd / "answer.txt").read_text().strip() if (wd / "answer.txt").exists() else ""
    meta = {**item, "returncode": rc, "wall_s": round(time.time() - start), "response": answer, **s,
            "model": args.model_label, "workdir": str(wd)}
    (wd / "run.json").write_text(json.dumps(meta, indent=2))
    session = wd / "session.json"
    session.write_text(json.dumps({k: meta[k] for k in ("response", "action_log", "returncode", "opened_skill",
                                                        "usage", "wall_s", "prefix")}, indent=2))
    upload(session, f"{args.runs_dir}/r{item['rep']}/{item['arm']}/{item['task_id']}.json", args.profile)
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tasks", nargs="*", help="task ids (default: all in evalset.json)")
    ap.add_argument("--arms", nargs="*", default=["baseline", "with_skill"], choices=list(ARM_LETTER))
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--first-rep", type=int, default=1)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--run-root", default=str(Path.home() / "x12-eval-runs"))
    ap.add_argument("--genie-home", default="~/.genie-x12-eval")
    ap.add_argument("--runs-dir", default="/Volumes/hls_amer_catalog/x12_claims_ingest_test/eval/x12-claims-ingest/_runs")
    ap.add_argument("--profile", default="hls_amer")
    ap.add_argument("--timeout-min", type=int, default=45)
    ap.add_argument("--model-label", default="databricks-gpt-5-6-sol (GENIE_HOME config)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    home = Path(args.genie_home).expanduser()
    # Genie's bundled skills (skills/.system) ship with the product and stay on in both arms.
    personal = [p for p in (home / "skills").glob("*") if p.name != ".system"] if (home / "skills").exists() else []
    leaks = [p for p in (home / "AGENTS.md",) if p.exists()] + personal
    if leaks:
        sys.exit(f"GENIE_HOME {home} is not isolated, remove: {leaks}")
    evalset = {e["task_id"]: e for e in json.loads((EVAL_DIR / "evalset.json").read_text())}
    tasks = args.tasks or list(evalset)

    schedule = []
    rng = random.Random(args.seed)
    for rep in range(args.first_rep, args.first_rep + args.reps):
        block = [{"rep": rep, "task_id": t, "arm": a} for t in tasks for a in args.arms]
        rng.shuffle(block)
        for it in block:
            it["prefix"] = prefix(it["arm"], it["task_id"], rep)
            it["prompt"] = evalset[it["task_id"]]["query"].replace("<PREFIX>", it["prefix"])
        schedule += block

    Path(args.run_root).mkdir(parents=True, exist_ok=True)
    (Path(args.run_root) / f"schedule-r{args.first_rep}-{args.first_rep + args.reps - 1}.json").write_text(
        json.dumps(schedule, indent=2))
    for it in schedule:
        if args.dry_run:
            print(json.dumps({k: it[k] for k in ("rep", "task_id", "arm", "prefix")}))
            continue
        meta = run_one(it, args)
        print(json.dumps({k: meta.get(k) for k in ("rep", "task_id", "arm", "returncode", "wall_s", "opened_skill")}),
              flush=True)


if __name__ == "__main__":
    main()
