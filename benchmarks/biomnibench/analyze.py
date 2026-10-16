#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Compare two arms on the labeled BiomniBench-DA tasks: does a skills arm beat a baseline where a skill applies,
and does it hold up where none does?

Run score = mean of the judge repeats. Cell = mean over a (task, arm)'s runs. For a comparison
A - B on a task set, d_t = cell(A) - cell(B) and the effect is the unweighted mean of d_t over tasks.
The 95% CI comes from a two-level bootstrap: resample tasks, then resample runs within each cell.
Runs that failed for infrastructure reasons (rate limit after all retries, skipped for disk) are
excluded and listed. Agent failures (timeout, no answer) keep the judge's score, which is 0.

Three comparisons, on the task sets from tasks.json (with --skill, covered means covered by that skill):
- covered: "improves" if the effect is at least --margin, the CI's low end is above -margin, and no task drops by
  more than --max-task-drop;
- control: "no harm" if the effect is above -margin and no task drops by more than --max-task-drop;
- all labeled tasks: descriptive.
Also reported: how often each arm opened an expected skill on covered tasks and any skill on controls, token cost,
and per-task cells. Fix the arms, tasks and thresholds before the runs.

    uv run analyze.py --grades sc --out sc --a skills --b no_skills --skill sc-rnaseq
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
from pathlib import Path

import taskset

HERE = Path(__file__).resolve().parent
OSB_HOME = Path(os.environ.get("OSB_HOME", Path.home() / "osb"))
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261014
MARGIN = 5.0
MAX_TASK_DROP = 15.0
MAX_TOKEN_RISE = 0.30


def load_runs(grades: list[dict]) -> list[dict]:
    runs = []
    for g in grades:
        path = OSB_HOME / "runs" / g["run_id"] / g["task"] / g["arm"] / f"rep{g['rep']}" / "run.json"
        meta = json.loads(path.read_text()) if path.exists() else {}
        infra_failure = bool(meta.get("rate_limited")) or "skipped" in meta
        runs.append({**g, "meta": meta, "infra_failure": infra_failure})
    return runs


def cells(runs: list[dict]) -> dict[tuple[str, str], list[float]]:
    out: dict[tuple[str, str], list[float]] = {}
    for r in runs:
        if not r["infra_failure"]:
            out.setdefault((r["task"], r["arm"]), []).append(r["score"])
    return out


def effect(cell_scores: dict, tasks: list[str], a: str, b: str) -> tuple[float, dict[str, float]]:
    diffs = {t: statistics.fmean(cell_scores[(t, a)]) - statistics.fmean(cell_scores[(t, b)]) for t in tasks}
    return statistics.fmean(diffs.values()), diffs


def bootstrap_ci(cell_scores: dict, tasks: list[str], a: str, b: str, rng: random.Random) -> tuple[float, float]:
    stats = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sampled = rng.choices(tasks, k=len(tasks))
        d = [
            statistics.fmean(rng.choices(cell_scores[(t, a)], k=len(cell_scores[(t, a)])))
            - statistics.fmean(rng.choices(cell_scores[(t, b)], k=len(cell_scores[(t, b)])))
            for t in sampled
        ]
        stats.append(statistics.fmean(d))
    stats.sort()
    return stats[int(0.025 * len(stats))], stats[int(0.975 * len(stats)) - 1]


def sign_test(diffs: list[float]) -> tuple[int, int, float]:
    """(ups, downs, two-sided exact binomial p); ties are dropped."""
    ups, downs = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    n = ups + downs
    if n == 0:
        return 0, 0, 1.0
    tail = sum(math.comb(n, k) for k in range(min(ups, downs) + 1)) / 2**n
    return ups, downs, min(1.0, 2 * tail)


def decide(rule: str | None, mean: float, lo: float, diffs: dict[str, float], margin: float = MARGIN,
           max_drop: float = MAX_TASK_DROP) -> str:
    worst = min(diffs.values())
    if rule == "improves":
        ok = mean >= margin and lo > -margin and worst >= -max_drop
        return "PASS" if ok else "inconclusive"
    if rule == "no_harm":
        return "PASS" if mean > -margin and worst >= -max_drop else "FAIL"
    return "descriptive"


def median_tokens(runs: list[dict], tasks: list[str], arm: str) -> float | None:
    vals = [r["meta"].get("input_tokens", 0) + r["meta"].get("output_tokens", 0)
            for r in runs if r["arm"] == arm and r["task"] in tasks and not r["infra_failure"] and r["meta"]]
    return statistics.median(vals) if vals else None


def token_rise(runs: list[dict], tasks: list[str], a: str, b: str) -> float | None:
    """Mean over tasks of median_tokens(a) / median_tokens(b), minus 1. Per task, so the task mix cannot drive it."""
    ratios = []
    for t in tasks:
        tok_a, tok_b = median_tokens(runs, [t], a), median_tokens(runs, [t], b)
        if tok_a and tok_b:
            ratios.append(tok_a / tok_b)
    return statistics.fmean(ratios) - 1 if ratios else None


def behavior_rates(runs: list[dict], tasks: list[str], arm: str) -> dict[str, str]:
    out = {}
    for key in ("ora_background_stated", "task_threshold_used", "gsea_for_condition_response", "sc_standard_pipeline"):
        answers = [r["behavior"].get(key) for r in runs if r["arm"] == arm and r["task"] in tasks and "behavior" in r]
        applicable = [a for a in answers if a in ("yes", "no")]
        out[key] = f"{sum(a == 'yes' for a in applicable)}/{len(applicable)}" if applicable else "n/a"
    return out


def routing(runs: list[dict], task_sets: dict[str, list[str]], expected: dict[str, list[str]]) -> dict:
    """Per arm, in percent: how often a covered task's run opened an expected skill (hit), and how often a control
    task's run opened any HLS skill (false trigger)."""
    hits: dict[str, list[float]] = {}
    false: dict[str, list[float]] = {}
    for r in runs:
        if r["infra_failure"]:
            continue
        opened = set(r["meta"].get("opened", []))
        if r["task"] in task_sets.get("covered", []):
            hits.setdefault(r["arm"], []).append(100.0 * bool(opened & set(expected[r["task"]])))
        elif r["task"] in task_sets.get("control", []):
            false.setdefault(r["arm"], []).append(100.0 * bool(opened))
    rate = lambda values: statistics.fmean(values) if values else None  # noqa: E731
    return {arm: {"hit_rate": rate(hits.get(arm)), "false_trigger_rate": rate(false.get(arm))}
            for arm in sorted(hits | false)}


def per_protocol(runs: list[dict], tasks: list[str], expected: dict[str, list[str]]) -> dict:
    """Descriptive: on covered tasks, the mean score of a skills arm's runs that opened an expected skill and of
    those that did not. Opening is not randomized, so this is not a causal effect."""
    out = {}
    for arm in sorted({r["arm"] for r in runs}):
        groups: dict[str, list[float]] = {"opened": [], "not_opened": []}
        for r in runs:
            if r["arm"] == arm and r["task"] in tasks and not r["infra_failure"] and r["meta"].get("skills"):
                hit = bool(set(r["meta"].get("opened", [])) & set(expected[r["task"]]))
                groups["opened" if hit else "not_opened"].append(r["score"])
        if any(groups.values()):
            out[arm] = {k: {"n": len(v), "mean": statistics.fmean(v) if v else None} for k, v in groups.items()}
    return out


def comparisons_for(a: str, b: str) -> list[tuple]:
    """(name, task set, arm A, arm B, rule)."""
    return [
        (f"covered: {a} vs {b}", "covered", a, b, "improves"),
        (f"no harm on controls: {a} vs {b}", "control", a, b, "no_harm"),
        (f"all labeled tasks: {a} vs {b}", "all", a, b, None),
    ]


def analyze(grades: list[dict], task_sets: dict[str, list[str]], comparisons: list[tuple],
            expected: dict[str, list[str]], seed: int = BOOTSTRAP_SEED, margin: float = MARGIN,
            max_drop: float = MAX_TASK_DROP) -> dict:
    runs = load_runs(grades)
    cell_scores = cells(runs)
    rng = random.Random(seed)
    results = []
    for name, task_set, a, b, rule in comparisons:
        tasks = [t for t in task_sets.get(task_set, []) if (t, a) in cell_scores and (t, b) in cell_scores]
        if not tasks:
            continue
        mean, diffs = effect(cell_scores, tasks, a, b)
        lo, hi = bootstrap_ci(cell_scores, tasks, a, b, rng)
        ups, downs, p = sign_test(list(diffs.values()))
        tok_a, tok_b = median_tokens(runs, tasks, a), median_tokens(runs, tasks, b)
        rise = token_rise(runs, tasks, a, b)
        decision = decide(rule, mean, lo, diffs, margin, max_drop)
        if rule == "improves" and decision == "PASS" and rise is not None and rise > MAX_TOKEN_RISE:
            decision = "PASS on score, FAILS cost guardrail"
        results.append({
            "comparison": name, "set": task_set, "a": a, "b": b, "rule": rule, "tasks": tasks,
            "effect": mean, "ci95": [lo, hi], "per_task": diffs, "ups": ups, "downs": downs, "sign_p": p,
            "median_tokens": {a: tok_a, b: tok_b}, "token_rise": rise, "decision": decision,
        })
    infra = [f"{r['run_id']}/{r['task']}/{r['arm']}/rep{r['rep']}" for r in runs if r["infra_failure"]]
    table = {
        f"{t}|{arm}": {"mean": statistics.fmean(v), "runs": v}
        for (t, arm), v in sorted(cell_scores.items())
    }
    behavior = {
        f"{s}|{arm}": behavior_rates(runs, tasks, arm)
        for s, tasks in task_sets.items() for arm in sorted({r["arm"] for r in runs})
    }
    return {
        "comparisons": results, "cells": table, "behavior": behavior, "infra_failures": infra,
        "routing": routing(runs, task_sets, expected),
        "per_protocol": per_protocol(runs, task_sets.get("covered", []), expected),
        "cost": {arm: {"median_tokens": median_tokens(runs, task_sets["all"], arm),
                       "median_wall_s": statistics.median([r["meta"]["wall_s"] for r in runs if r["arm"] == arm
                                                           and r["meta"].get("wall_s") is not None] or [0])}
                 for arm in sorted({r["arm"] for r in runs})},
    }


def to_markdown(result: dict) -> str:
    lines = ["# Analysis", "", "## Comparisons", "",
             "| Comparison | Tasks | Effect | 95% CI | Up / down | Sign test p | Token change | Decision |",
             "|---|---|---|---|---|---|---|---|"]
    for c in result["comparisons"]:
        tr = f"{c['token_rise']:+.0%}" if c["token_rise"] is not None else "n/a"
        lines.append(f"| {c['comparison']} | {len(c['tasks'])} | {c['effect']:+.1f} | {c['ci95'][0]:+.1f} to {c['ci95'][1]:+.1f} "
                     f"| {c['ups']} / {c['downs']} | {c['sign_p']:.3f} | {tr} | {c['decision']} |")
    lines += ["", "## Cells (mean of runs; each run is the mean of its judge repeats)", "", "| Task | Arm | Mean | Runs |", "|---|---|---|---|"]
    for key, v in result["cells"].items():
        task, arm = key.split("|")
        lines.append(f"| {task} | {arm} | {v['mean']:.1f} | {', '.join(f'{x:.1f}' for x in v['runs'])} |")
    lines += ["", "## Behavior checks (yes / applicable)", "", "| Set and arm | ORA background | Task threshold | GSEA for response | sc pipeline |", "|---|---|---|---|---|"]
    for key, v in result["behavior"].items():
        lines.append(f"| {key.replace('|', ' ')} | " + " | ".join(v.values()) + " |")
    pct = lambda x: "n/a" if x is None else f"{x:.0f}%"  # noqa: E731
    lines += ["", "## Skill use (covered tasks: opened an expected skill; controls: opened any HLS skill)", "",
              "| Arm | Hit rate | False triggers |", "|---|---|---|"]
    for arm, m in result["routing"].items():
        lines.append(f"| {arm} | {pct(m['hit_rate'])} | {pct(m['false_trigger_rate'])} |")
    lines += ["", "## Score by whether an expected skill was opened (covered tasks; descriptive, not causal)", "",
              "| Arm | Opened: runs | Opened: mean | Not opened: runs | Not opened: mean |", "|---|---|---|---|---|"]
    for arm, g in result["per_protocol"].items():
        fmt = lambda m: "n/a" if m is None else f"{m:.1f}"  # noqa: E731
        lines.append(f"| {arm} | {g['opened']['n']} | {fmt(g['opened']['mean'])} | {g['not_opened']['n']} "
                     f"| {fmt(g['not_opened']['mean'])} |")
    lines += ["", "## Cost (all tasks)", "", "| Arm | Median tokens | Median wall time (s) |", "|---|---|---|"]
    for arm, c in result["cost"].items():
        lines.append(f"| {arm} | {c['median_tokens']} | {c['median_wall_s']} |")
    lines += ["", f"Infrastructure failures excluded: {', '.join(result['infra_failures']) or 'none'}"]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grades", action="append", required=True, help="grades folder name under $OSB_HOME/grades")
    ap.add_argument("--out", required=True)
    ap.add_argument("--a", required=True, help="the arm under test, e.g. skills")
    ap.add_argument("--b", required=True, help="the baseline arm, e.g. no_skills")
    ap.add_argument("--skill", help="count only the tasks covered by this skill as covered")
    ap.add_argument("--margin", type=float, default=MARGIN, help="score points")
    ap.add_argument("--max-task-drop", type=float, default=MAX_TASK_DROP, help="score points")
    ap.add_argument("--seed", type=int, default=BOOTSTRAP_SEED, help="bootstrap seed")
    args = ap.parse_args()
    grades = [g for name in args.grades for g in json.loads((OSB_HOME / "grades" / name / "grades.json").read_text())]
    grades = [g for g in grades if g["arm"] != "openscience_published"]
    tasks = taskset.load()["tasks"]
    if args.skill:
        tasks = [t for t in tasks if t["coverage"] != "covered" or args.skill in t["hls_skills"]]
    task_sets = taskset.task_sets(tasks)
    task_sets["all"] = task_sets["covered"] + task_sets["control"]
    expected = {t["task_id"]: t["hls_skills"] for t in tasks}
    result = analyze(grades, task_sets, comparisons_for(args.a, args.b), expected, args.seed, args.margin,
                     args.max_task_drop)
    out_dir = OSB_HOME / "analysis" / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analysis.json").write_text(json.dumps(result, indent=2))
    (out_dir / "analysis.md").write_text(to_markdown(result))
    print(to_markdown(result))


if __name__ == "__main__":
    main()
