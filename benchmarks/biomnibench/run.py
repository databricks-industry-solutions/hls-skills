#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Run Genie Code CLI on BiomniBench-DA tasks, once per (replicate, task, arm).

An arm is `no_skills` or NAME=GIT_REF[:INSTRUCTIONS]. GIT_REF names the published skill bundles of this repo at
that ref (eval/ and tests/ excluded, the same filter as the Unity Catalog sync), installed in the run's
./.agents/skills/. INSTRUCTIONS names a file in instructions/ that is copied to ./AGENTS.md, which Genie always
loads. Refs are resolved to SHAs once, so a moving branch cannot change an arm mid-study.

Tasks come from tasks.json: `--skill NAME` runs the tasks labeled as covered by that skill, `--controls N` adds N
control tasks drawn with --seed (the no-harm check), and `--tasks` names tasks directly. With none of these, every
covered and control task runs.

Each run gets a fresh workdir $OSB_HOME/runs/<run-id>/<task>/<arm>/rep<k>/ with ./data (the task's files,
hard-linked and read-only) and its own Python. The prompt is the task's instruction.md with /app/ rewritten to ./,
so the agent writes ./trace.md and ./answer.txt.

Runs go in a schedule written to schedule-*.json before the first run starts. Runs are grouped by replicate, and
within a replicate the task order and arm order are shuffled with --seed. Runs are resumable: rerunning the same
command keeps the SHAs pinned in that schedule and skips every workdir with run.json, except runs that were still
rate-limited after all retries, which run again. A run whose turn fails on the network (the workspace IP ACL blocks this machine, or the
connection to the model is lost) is an infrastructure failure: it is moved to $OSB_HOME/infra-failed/, the rest of
the batch is skipped, and rerunning the same command once the network is back starts those runs again.

Every run uses the Genie config profile `biomnibench` ($GENIE_HOME/biomnibench.config.toml, written here). It
disables the user's personal skills (~/.agents/skills), which Genie would otherwise load in every arm, and Genie's
memories. Genie's bundled Databricks skills stay on in every arm, as they ship with the product.

    uv run run.py --run-id sc --skill sc-rnaseq --controls 6 --arm no_skills --arm skills=main:D0 --reps 3
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sync_skills_git2unity import SKILL_LEAF_PATTERN, is_published  # noqa: E402

import taskset  # noqa: E402

OSB_HOME = Path(os.environ.get("OSB_HOME", Path.home() / "osb"))
OSB_GRADING = Path(os.environ.get("OSB_GRADING", Path.home() / ".cache" / "osb-grading"))
NO_SKILLS = "no_skills"
AGENT_TIMEOUT_S = 3600  # task.toml [agent] timeout_sec for every task used here
PYTHON_VERSION = "3.12"  # the task containers run Ubuntu 24.04, whose python3 is 3.12
MAX_ATTEMPTS = 4
RATE_LIMIT_BACKOFF_S = 120
MIN_FREE_GB = 8
# Turn failures caused by this machine's network, not by the agent. They last until the network changes, so
# retrying in place cannot help.
NETWORK_FAILURES = {
    "ip_acl": ("blocked by Databricks IP ACL",),
    "connection_lost": ("stream disconnected before completion: error sending request",),
}
network_blocked = threading.Event()
# Files the agent leaves behind above this size are deleted after a run, except the run's own record.
MAX_KEPT_FILE_BYTES = 100 * 1024**2
RUN_RECORD = {"events.jsonl", "stderr.log", "trace.md", "answer.txt"}
GENIE_HOME = Path(os.environ.get("GENIE_HOME", Path.home() / ".genie"))
GENIE_PROFILE = "biomnibench"
# User-scope skill roots Genie scans; their skills would leak into every arm.
USER_SKILL_DIRS = (GENIE_HOME / "skills", Path.home() / ".agents" / "skills")
GENIE_CMD = ["genie", "exec", "--json", "--skip-git-repo-check", "-p", GENIE_PROFILE, "--sandbox", "workspace-write"]
INSTRUCTIONS_DIR = HERE / "instructions"
SKILLS_DIR = ".agents/skills"
INSTRUCTIONS_FILE = "AGENTS.md"
SKILL_OPEN = re.compile(r"\.agents/skills/([A-Za-z0-9-]+)/SKILL\.md")


def user_skill_names() -> list[str]:
    names = set()
    for root in USER_SKILL_DIRS:
        for skill_md in root.glob("*/SKILL.md"):
            m = re.search(r"^name:\s*['\"]?([^'\"\n]+)", skill_md.read_text(errors="replace"), flags=re.MULTILINE)
            names.add(m.group(1).strip() if m else skill_md.parent.name)
    return sorted(names)


def disabled_user_skills() -> list[str]:
    lines = []
    for name in user_skill_names():
        lines += ["", "[[skills.config]]", f"name = {json.dumps(name)}", "enabled = false"]
    return lines


def write_genie_profile() -> Path:
    """Unattended runs: no approval prompts, network on (tasks allow internet), memories and user skills off."""
    lines = ['approval_policy = "never"', "", "[sandbox_workspace_write]", "network_access = true",
             "", "[memories]", "generate_memories = false", "use_memories = false", *disabled_user_skills()]
    path = GENIE_HOME / f"{GENIE_PROFILE}.config.toml"
    path.write_text("\n".join(lines) + "\n")
    return path


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()


def resolve_arms(specs: list[str]) -> dict[str, dict]:
    """`no_skills` or NAME=GIT_REF[:INSTRUCTIONS] -> {name: arm}; refs are pinned to SHAs here."""
    arms = {}
    for spec in specs:
        if spec == NO_SKILLS:
            arms[NO_SKILLS] = {"ref": None, "sha": None, "skills_tree": None}
            continue
        name, sep, value = spec.partition("=")
        ref, _, instructions = value.partition(":")
        if not sep or not name or name == NO_SKILLS or not ref:
            sys.exit(f"--arm must be `{NO_SKILLS}` or NAME=GIT_REF[:INSTRUCTIONS], got {spec!r}")
        sha = git("rev-parse", "--verify", f"{ref}^{{commit}}")
        arm = {"ref": ref, "sha": sha, "skills_tree": git("rev-parse", f"{sha}:skills")}
        if instructions:
            path = INSTRUCTIONS_DIR / f"{instructions}.md"
            if not path.is_file():
                sys.exit(f"No instructions file {path}")
            arm |= {"instructions": instructions, "instructions_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        arms[name] = arm
    return arms


def skill_bundles(sha: str) -> dict[str, dict[str, bytes]]:
    """{skill: {relative path: bytes}} for every published skill under skills/ at a commit."""
    archive = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "archive", "--format=tar", sha, "skills/"], capture_output=True, check=True
    ).stdout
    bundles: dict[str, dict[str, bytes]] = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts  # ("skills", <skill>, ...rel)
            if member.isfile() and len(parts) > 2 and is_published(Path(*parts[2:])):
                bundles.setdefault(parts[1], {})[str(Path(*parts[2:]))] = tar.extractfile(member).read()
    return {
        name: files for name, files in sorted(bundles.items()) if "SKILL.md" in files and SKILL_LEAF_PATTERN.match(name)
    }


def install_skills(sha: str, dest: Path) -> list[str]:
    bundles = skill_bundles(sha)
    for name, files in bundles.items():
        for rel, data in files.items():
            path = dest / name / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return list(bundles)


def build_schedule(tasks: list[str], arms: list[str], reps: list[int], seed: int) -> list[dict]:
    """Grouped by replicate. Within each, task order and each task's arm order are shuffled."""
    rng = random.Random(seed)
    schedule = []
    for rep in reps:
        for task in rng.sample(tasks, len(tasks)):
            schedule += [{"rep": rep, "task": task, "arm": arm} for arm in rng.sample(arms, len(arms))]
    return schedule


def read_text(path: Path) -> str:
    return path.read_text(errors="replace") if path.exists() else ""


def events(events_path: Path) -> list[dict]:
    out = []
    for line in read_text(events_path).splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def token_usage(events_path: Path) -> dict[str, int]:
    totals = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    for event in events(events_path):
        if event.get("type") == "turn.completed":
            for key in totals:
                totals[key] += int((event.get("usage") or {}).get(key, 0))
    return totals


def opened_skills(events_path: Path) -> list[str]:
    """Skills whose SKILL.md the agent read with a shell command, in first-open order."""
    order: list[str] = []
    for event in events(events_path):
        item = event.get("item") or {}
        if event.get("type") == "item.started" and item.get("type") == "command_execution":
            order += [n for n in SKILL_OPEN.findall(item.get("command", "")) if n not in order]
    return order


def rate_limited(events_path: Path) -> bool:
    # Genie reports the workspace limit as REQUEST_LIMIT_EXCEEDED.
    text = read_text(events_path)
    return "REQUEST_LIMIT_EXCEEDED" in text and '"turn.failed"' in text


def network_failure(events_path: Path) -> str | None:
    """The NETWORK_FAILURES key whose message is in a failed turn, else None."""
    failed = [line for line in read_text(events_path).splitlines() if '"turn.failed"' in line]
    return next((k for k, ms in NETWORK_FAILURES.items() if any(m in line for m in ms for line in failed)), None)


def free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1024**3


def link_data(src: Path, dest: Path) -> None:
    """Give the run the task's files as regular files. A symbolic link to the data folder looked empty to agents
    that list files with `rg --files` or `find -type f`. Hard links cost no disk; the files are made read-only
    first, so an agent cannot change the shared copy in place. Falls back to copying across file systems."""
    for path in src.rglob("*"):
        if path.is_file():
            path.chmod(0o444)

    def link(s: str, d: str) -> None:
        try:
            os.link(s, d)
        except OSError:
            shutil.copy2(s, d)

    shutil.copytree(src, dest, copy_function=link)


def prepare_workdir(wd: Path, task: str, arm: dict) -> tuple[list[str], dict[str, str]]:
    wd.mkdir(parents=True)
    link_data(OSB_HOME / "data" / task, wd / "data")
    # Project-level skills are discovered from the repository root.
    subprocess.run(["git", "init", "-q"], cwd=wd, check=True)
    skills = install_skills(arm["sha"], wd / SKILLS_DIR) if arm["sha"] else []
    if arm.get("instructions"):
        shutil.copyfile(INSTRUCTIONS_DIR / f"{arm['instructions']}.md", wd / INSTRUCTIONS_FILE)
    # The benchmark container ships a current python3 with pip. The macOS system python3 (3.9,
    # LibreSSL 2.8) cannot complete a TLS handshake with PyPI, so give each run its own Python.
    subprocess.run(["uv", "venv", "--quiet", "--seed", "--python", PYTHON_VERSION, str(wd / ".venv")], check=True)
    # Genie runs commands with `zsh -lc`. /etc/zprofile (path_helper) puts /usr/bin back in front,
    # and $ZDOTDIR/.zprofile runs after it, so the venv goes first again there.
    zdotdir = wd / ".zdotdir"
    zdotdir.mkdir()
    (zdotdir / ".zprofile").write_text(f'export PATH="{wd / ".venv" / "bin"}:$PATH"\n')

    # The sandbox only allows writes inside the workdir, so point package caches there.
    cache = wd / ".cache"
    (wd / ".rlib").mkdir()
    env = {
        **os.environ,
        "PATH": f"{wd / '.venv' / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "VIRTUAL_ENV": str(wd / ".venv"),
        "ZDOTDIR": str(zdotdir),
        "XDG_CACHE_HOME": str(cache),
        "UV_CACHE_DIR": str(cache / "uv"),
        "PIP_CACHE_DIR": str(cache / "pip"),
        "MPLCONFIGDIR": str(cache / "matplotlib"),
        "R_LIBS_USER": str(wd / ".rlib"),
    }
    return skills, env


def clean_workdir(wd: Path) -> list[str]:
    """Record the agent's packages, then drop the venv, caches and large leftovers. Outputs stay."""
    python = wd / ".venv" / "bin" / "python"
    if python.exists():
        freeze = subprocess.run([str(python), "-m", "pip", "freeze"], capture_output=True, text=True, check=False)
        (wd / "pip-freeze.txt").write_text(freeze.stdout)
    for name in (".venv", ".cache", ".rlib"):
        shutil.rmtree(wd / name, ignore_errors=True)
    removed = []
    for path in wd.rglob("*"):
        # Hard links into the shared task data cost no disk and stay; grading and the leak check need RUN_RECORD.
        if path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1 and path.stat().st_size > MAX_KEPT_FILE_BYTES \
                and str(path.relative_to(wd)) not in RUN_RECORD:
            removed.append(str(path.relative_to(wd)))
            path.unlink()
    return removed


def run_one(run_dir: Path, item: dict, arms: dict[str, dict], provenance: dict) -> dict:
    task, arm, rep = item["task"], item["arm"], item["rep"]
    wd = run_dir / task / arm / f"rep{rep}"
    if (wd / "run.json").exists():
        meta = json.loads((wd / "run.json").read_text())
        if not meta.get("rate_limited"):
            return meta
        print(f"{task}/{arm}/rep{rep}: was rate-limited, running it again", flush=True)
    if free_gb(OSB_HOME) < MIN_FREE_GB:
        print(f"{task}/{arm}/rep{rep}: skipped, under {MIN_FREE_GB} GB free", flush=True)
        return {**item, "skipped": "low_disk"}
    if network_blocked.is_set():
        return {**item, "skipped": "network"}
    prompt = (OSB_GRADING / task / "instruction.md").read_text().replace("/app/", "./")

    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Every attempt starts from a clean workdir, so a retry sees exactly what a first try sees.
        shutil.rmtree(wd, ignore_errors=True)
        skills, env = prepare_workdir(wd, task, arms[arm])
        started = dt.datetime.now(dt.timezone.utc)
        with open(wd / "events.jsonl", "w") as out, open(wd / "stderr.log", "w") as err:
            try:
                returncode = subprocess.run(
                    [*GENIE_CMD, prompt], cwd=wd, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                    timeout=AGENT_TIMEOUT_S, check=False,
                ).returncode
            except subprocess.TimeoutExpired:
                returncode = "timeout"
        if not rate_limited(wd / "events.jsonl") or attempt == MAX_ATTEMPTS:
            break
        print(f"{task}/{arm}/rep{rep}: workspace rate limit on attempt {attempt}, retrying", flush=True)
        time.sleep(RATE_LIMIT_BACKOFF_S * attempt)
    if reason := network_failure(wd / "events.jsonl"):
        # An infrastructure failure: keep the evidence outside the run folder so a rerun of the same command
        # starts this run again, and skip the rest of the batch, which would hit the same failure.
        network_blocked.set()
        dest = OSB_HOME / "infra-failed" / f"{run_dir.name}-{task}-{arm}-rep{rep}-{reason}-{started:%Y%m%dT%H%M%S}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(wd, dest)
        print(f"{task}/{arm}/rep{rep}: network failure ({reason}); moved to {dest}, skipping the rest", flush=True)
        return {**item, "skipped": reason}
    ended = dt.datetime.now(dt.timezone.utc)
    meta = {
        **item,
        **{f"arm_{k}": v for k, v in arms[arm].items()},
        "skills": skills,
        "returncode": returncode,
        "attempts": attempt,
        "rate_limited": rate_limited(wd / "events.jsonl"),
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "wall_s": round((ended - started).total_seconds()),
        "has_answer": (wd / "answer.txt").exists(),
        "has_trace": (wd / "trace.md").exists(),
        "opened": opened_skills(wd / "events.jsonl"),
        **token_usage(wd / "events.jsonl"),
        **provenance,
        "hf_revision": read_text(OSB_GRADING / task / "hf_revision.txt").strip() or None,
        "removed_large_files": clean_workdir(wd),
    }
    (wd / "run.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({k: meta[k] for k in ("task", "arm", "rep", "returncode", "attempts", "wall_s", "has_answer")}),
          flush=True)
    return meta


def resume_or_pin(schedule_path: Path, arms: dict[str, dict], schedule: list[dict]) -> dict[str, dict]:
    """A rerun of the same command keeps the SHAs the first call pinned, even if a ref has moved since."""
    if not schedule_path.exists():
        return arms
    prev = json.loads(schedule_path.read_text())
    if list(prev["arms"]) != list(arms) or prev["schedule"] != schedule:
        sys.exit(f"{schedule_path} has other arms or tasks; resume with the same command, or use a new --run-id")
    for name, arm in prev["arms"].items():
        if arm["sha"] != arms[name]["sha"]:
            print(f"arm {name}: keeping pinned {arm['sha'][:7]} ({arm['ref']} is now {arms[name]['sha'][:7]})")
    return prev["arms"]


def check_user_skills(arms: dict[str, dict]) -> None:
    """Personal skills are turned off by name, which would also turn off a project skill with the same name."""
    hls = {name for arm in arms.values() if arm["sha"] for name in skill_bundles(arm["sha"])}
    if clash := sorted(set(user_skill_names()) & hls):
        sys.exit(f"Personal skills named like HLS skills would turn those off in every arm: {clash}. "
                 f"Remove them from {', '.join(map(str, USER_SKILL_DIRS))} for the study.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--skill", help="run the tasks labeled as covered by this skill")
    ap.add_argument("--controls", type=int, help="number of control tasks to add (default: all)")
    ap.add_argument("--tasks", nargs="*", help="task ids (overrides --skill and --controls)")
    ap.add_argument("--arm", action="append", required=True,
                    help=f"`{NO_SKILLS}` or NAME=GIT_REF[:INSTRUCTIONS]; repeat per arm")
    ap.add_argument("--reps", type=int, default=3, help="replicates per (task, arm)")
    ap.add_argument("--rep-start", type=int, default=1, help="number of the first replicate")
    ap.add_argument("--seed", type=int, default=20261014)
    # Two agents at a time is the most the workspace's input-tokens-per-minute limit allowed in practice.
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()

    arms = resolve_arms(args.arm)
    if 'model_provider = "databricks"' not in read_text(GENIE_HOME / "config.toml"):
        sys.exit("Genie is not connected to Databricks: run `genie` once and finish onboarding.")
    labeled = taskset.load()
    tasks = args.tasks or taskset.select(labeled["tasks"], args.skill, args.controls, args.seed)
    missing = [t for t in tasks if not (OSB_HOME / "data" / t).is_dir() or not (OSB_GRADING / t).is_dir()]
    if missing:
        sys.exit(f"Run fetch.py first; missing: {missing}")

    run_dir = OSB_HOME / "runs" / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    reps = list(range(args.rep_start, args.rep_start + args.reps))
    schedule = build_schedule(tasks, list(arms), reps, args.seed)
    config = read_text(GENIE_HOME / "config.toml")
    provenance = {
        "genie_version": subprocess.run(["genie", "--version"], capture_output=True, text=True, check=True).stdout.strip(),
        "model": (re.search(r'^model\s*=\s*"([^"]+)"', config, flags=re.MULTILINE) or [None, None])[1],
        "harness_sha": git("rev-parse", "HEAD"),
        "labels_skills_sha": labeled["labels"].get("skills_sha"),
    }
    schedule_path = run_dir / f"schedule-rep{reps[0]}-{reps[-1]}.json"
    resumed = schedule_path.exists()
    arms = resume_or_pin(schedule_path, arms, schedule)
    if not resumed:
        schedule_path.write_text(json.dumps({"seed": args.seed, "skill": args.skill, "arms": arms,
                                             "provenance": provenance,
                                             "written_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                             "schedule": schedule}, indent=2))
    check_user_skills(arms)
    print(f"Genie profile: {write_genie_profile()} ({len(user_skill_names())} user skills disabled)")
    print(f"Schedule: {schedule_path} ({len(schedule)} runs)", flush=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda item: run_one(run_dir, item, arms, provenance), schedule))
    (run_dir / f"runs-rep{reps[0]}-{reps[-1]}.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
