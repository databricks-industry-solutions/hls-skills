#!/usr/bin/env python3
"""Paired per-task comparison of two skill-eval score files.

Compares a baseline (skill OFF) run against a candidate (skill ON) run.
Inputs are two JSON files shaped {task_id: {metric: bool}}. The comparison
unit is the task: per-metric flips roll up into a per-task outcome
(win / regression / tie-pass / tie-fail), and rates aggregate across tasks.

Usage:
  python compare_runs.py baseline_scores.json candidate_scores.json
  python compare_runs.py baseline.json candidate.json --pass-rule any_metric --format markdown
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

PASS_RULES = ("all_metrics", "any_metric")

OUTCOME_WIN = "win"
OUTCOME_REGRESSION = "regression"
OUTCOME_TIE_PASS = "tie-pass"
OUTCOME_TIE_FAIL = "tie-fail"


TRUTHY = ("true", "yes", "1")
FALSY = ("false", "no", "0")


def _to_bool(value, context: str) -> bool:
    """Strict score coercion — unknown values are an error, never silently False."""
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in TRUTHY:
        return True
    if normalized in FALSY:
        return False
    raise ValueError(f"{context}: unrecognized score value {value!r} (expected bool/yes/no/true/false/1/0)")


def load_scores(path: str | Path) -> dict[str, dict[str, bool]]:
    """Load {task_id: {metric: bool}} from JSON with strict value validation."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top level must be an object of task_id -> metrics")
    scores: dict[str, dict[str, bool]] = {}
    for task_id, metrics in raw.items():
        if not isinstance(metrics, dict):
            raise ValueError(f"{path}: task '{task_id}' metrics must be an object")
        scores[str(task_id)] = {
            str(k): _to_bool(v, f"{path}: task '{task_id}' metric '{k}'")
            for k, v in metrics.items()
        }
    return scores


DIFFICULTIES = ("easy", "hard", "edge")


def load_difficulty(path: str | Path) -> dict[str, str]:
    """Load {task_id: easy|hard|edge} with strict label validation."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: difficulty file must be an object of task_id -> difficulty")
    out: dict[str, str] = {}
    for task_id, level in raw.items():
        label = str(level).strip().lower()
        if label not in DIFFICULTIES:
            raise ValueError(
                f"{path}: task '{task_id}' has invalid difficulty {level!r} "
                f"(expected one of {DIFFICULTIES})"
            )
        out[str(task_id)] = label
    return out


def task_passed(metrics: dict[str, bool], pass_rule: str) -> bool:
    """Task-level pass under the given rule. Empty metrics = fail."""
    if not metrics:
        return False
    if pass_rule == "all_metrics":
        return all(metrics.values())
    return any(metrics.values())


def outcome(baseline_pass: bool, candidate_pass: bool) -> str:
    if candidate_pass and not baseline_pass:
        return OUTCOME_WIN
    if baseline_pass and not candidate_pass:
        return OUTCOME_REGRESSION
    if baseline_pass:
        return OUTCOME_TIE_PASS
    return OUTCOME_TIE_FAIL


def metric_flip(baseline_val: bool, candidate_val: bool) -> str:
    return outcome(baseline_val, candidate_val)


@dataclass
class TaskComparison:
    task_id: str
    baseline_pass: bool
    candidate_pass: bool
    outcome: str
    metric_flips: dict[str, str] = field(default_factory=dict)
    excluded_metrics: dict[str, str] = field(default_factory=dict)  # metric -> which arm lacks it
    difficulty: str | None = None


@dataclass
class Comparison:
    tasks: list[TaskComparison]
    unpaired: dict[str, str] = field(default_factory=dict)  # task_id -> which file lacks it
    no_common_metrics: list[str] = field(default_factory=list)  # task_id present in both, 0 shared

    def counts(self) -> dict[str, int]:
        c = {OUTCOME_WIN: 0, OUTCOME_REGRESSION: 0, OUTCOME_TIE_PASS: 0, OUTCOME_TIE_FAIL: 0}
        for t in self.tasks:
            c[t.outcome] += 1
        return c

    @property
    def win_rate(self) -> float:
        return self.counts()[OUTCOME_WIN] / len(self.tasks) if self.tasks else 0.0

    @property
    def regression_rate(self) -> float:
        return self.counts()[OUTCOME_REGRESSION] / len(self.tasks) if self.tasks else 0.0

    @property
    def easy_regressions(self) -> list[str]:
        """task_ids of regressions on tasks marked easy via --difficulty."""
        return [
            t.task_id
            for t in self.tasks
            if t.outcome == OUTCOME_REGRESSION and t.difficulty == "easy"
        ]

    @property
    def unlabeled_regressions(self) -> list[str]:
        """task_ids of regressions with no difficulty label, so easiness is unknown."""
        return [t.task_id for t in self.tasks if t.outcome == OUTCOME_REGRESSION and not t.difficulty]

    @property
    def unlabeled_tasks(self) -> list[str]:
        """Paired task_ids missing from the difficulty map."""
        return [t.task_id for t in self.tasks if not t.difficulty]

    @property
    def ship_gate_passed(self) -> bool:
        """Ship rule: at least one win, and no regression that is easy or unlabeled.

        An unlabeled regression blocks the gate because a partial difficulty map
        must not let an easy-task regression through unnoticed.
        """
        return (
            self.counts()[OUTCOME_WIN] > 0
            and not self.easy_regressions
            and not self.unlabeled_regressions
        )


def compare(
    baseline: dict[str, dict[str, bool]],
    candidate: dict[str, dict[str, bool]],
    pass_rule: str = "all_metrics",
    difficulty: dict[str, str] | None = None,
) -> Comparison:
    """Pair tasks on task_id; compute outcomes and flips on shared metrics only.

    Task pass/fail and flips use the intersection of each task's metric keys —
    a metric present in only one arm cannot fairly influence the verdict and is
    reported in excluded_metrics instead.
    """
    if pass_rule not in PASS_RULES:
        raise ValueError(f"pass_rule must be one of {PASS_RULES}, got {pass_rule!r}")

    unpaired: dict[str, str] = {}
    no_common_metrics: list[str] = []
    paired_ids: list[str] = []
    for task_id in baseline:
        if task_id in candidate:
            paired_ids.append(task_id)
        else:
            unpaired[task_id] = "candidate"
    for task_id in candidate:
        if task_id not in baseline:
            unpaired[task_id] = "baseline"

    tasks: list[TaskComparison] = []
    for task_id in sorted(paired_ids):
        b_metrics = baseline[task_id]
        c_metrics = candidate[task_id]
        common = b_metrics.keys() & c_metrics.keys()
        excluded = {
            **{m: "candidate" for m in b_metrics.keys() - common},
            **{m: "baseline" for m in c_metrics.keys() - common},
        }
        if not common:
            # No comparable evidence — do not count this task in rates at all.
            no_common_metrics.append(task_id)
            continue
        b_pass = task_passed({m: b_metrics[m] for m in common}, pass_rule)
        c_pass = task_passed({m: c_metrics[m] for m in common}, pass_rule)
        flips = {m: metric_flip(b_metrics[m], c_metrics[m]) for m in common}
        tasks.append(
            TaskComparison(
                task_id=task_id,
                baseline_pass=b_pass,
                candidate_pass=c_pass,
                outcome=outcome(b_pass, c_pass),
                metric_flips=flips,
                excluded_metrics=excluded,
                difficulty=(difficulty or {}).get(task_id),
            )
        )
    return Comparison(tasks=tasks, unpaired=unpaired, no_common_metrics=no_common_metrics)


def gate_evaluable(comp: Comparison) -> bool:
    """Ship gate needs difficulty labels on at least one task and paired tasks."""
    return bool(comp.tasks) and any(t.difficulty for t in comp.tasks)


def format_text(comp: Comparison) -> str:
    lines = []
    counts = comp.counts()
    lines.append(
        f"Paired tasks: {len(comp.tasks)} | wins: {counts[OUTCOME_WIN]} | "
        f"regressions: {counts[OUTCOME_REGRESSION]} | "
        f"tie-pass: {counts[OUTCOME_TIE_PASS]} | tie-fail: {counts[OUTCOME_TIE_FAIL]}"
    )
    lines.append(f"win_rate: {comp.win_rate:.2f} | regression_rate: {comp.regression_rate:.2f}")
    if gate_evaluable(comp):
        verdict = "SHIP GATE PASS" if comp.ship_gate_passed else "SHIP GATE FAIL"
        reasons = []
        if comp.counts()[OUTCOME_WIN] == 0:
            reasons.append("no wins")
        if comp.easy_regressions:
            reasons.append(f"easy regressions: {', '.join(comp.easy_regressions)}")
        if comp.unlabeled_regressions:
            reasons.append(
                f"regressions with no difficulty label: {', '.join(comp.unlabeled_regressions)}"
            )
        suffix = f" ({'; '.join(reasons)})" if reasons else ""
        lines.append(f"{verdict}{suffix}")
        if comp.unlabeled_tasks:
            lines.append(
                f"NOTE: no difficulty label for {', '.join(comp.unlabeled_tasks)} "
                "— the difficulty map is incomplete."
            )
    elif comp.tasks:
        lines.append("SHIP GATE NOT EVALUATED (pass --difficulty to enable it)")
    lines.append("")
    for t in comp.tasks:
        diff = f" [{t.difficulty}]" if t.difficulty else ""
        lines.append(
            f"{t.task_id}{diff}: baseline={'PASS' if t.baseline_pass else 'FAIL'} "
            f"candidate={'PASS' if t.candidate_pass else 'FAIL'} -> {t.outcome}"
        )
        for metric, flip in sorted(t.metric_flips.items()):
            if flip in (OUTCOME_WIN, OUTCOME_REGRESSION):
                lines.append(f"    {metric}: {flip}")
        for metric, missing_in in sorted(t.excluded_metrics.items()):
            lines.append(f"    {metric}: excluded (missing from {missing_in} file)")
    for task_id, missing_in in sorted(comp.unpaired.items()):
        lines.append(f"UNPAIRED: task '{task_id}' missing from {missing_in} file (excluded)")
    for task_id in sorted(comp.no_common_metrics):
        lines.append(
            f"UNCOMPARABLE: task '{task_id}' is in both files but shares no metric (excluded)"
        )
    return "\n".join(lines)


def format_markdown(comp: Comparison) -> str:
    has_diff = any(t.difficulty for t in comp.tasks)
    header = "| task_id |" + (" difficulty |" if has_diff else "") + " baseline | with skill | outcome |"
    sep = "|---------|" + ("------------|" if has_diff else "") + "----------|------------|---------|"
    lines = [header, sep]
    for t in comp.tasks:
        b = "pass" if t.baseline_pass else "fail"
        c = "pass" if t.candidate_pass else "fail"
        emph = f"**{t.outcome}**" if t.outcome in (OUTCOME_WIN, OUTCOME_REGRESSION) else t.outcome
        row = f"| {t.task_id} |"
        if has_diff:
            row += f" {t.difficulty or ''} |"
        row += f" {b} | {c} | {emph} |"
        lines.append(row)
    counts = comp.counts()
    lines.append("")
    lines.append(
        f"Win rate: {counts[OUTCOME_WIN]}/{len(comp.tasks)}. "
        f"Regressions: {counts[OUTCOME_REGRESSION]}/{len(comp.tasks)}."
    )
    if gate_evaluable(comp):
        verdict = "**Ship gate PASS**" if comp.ship_gate_passed else "**Ship gate FAIL**"
        reasons = []
        if comp.counts()[OUTCOME_WIN] == 0:
            reasons.append("no wins")
        if comp.easy_regressions:
            reasons.append(f"easy regressions: {', '.join(comp.easy_regressions)}")
        if comp.unlabeled_regressions:
            reasons.append(
                f"regressions with no difficulty label: {', '.join(comp.unlabeled_regressions)}"
            )
        suffix = f" — {'; '.join(reasons)}" if reasons else ""
        lines.append(f"{verdict}{suffix}")
        if comp.unlabeled_tasks:
            lines.append(
                f"No difficulty label for {', '.join(comp.unlabeled_tasks)}. "
                "The difficulty map is incomplete."
            )
    elif comp.tasks:
        lines.append("**Ship gate not evaluated** — pass `--difficulty` to enable it.")
    notes = [
        f"- `{t.task_id}` metric `{m}` flipped to {flip}"
        for t in comp.tasks
        for m, flip in sorted(t.metric_flips.items())
        if flip in (OUTCOME_WIN, OUTCOME_REGRESSION)
    ]
    notes += [
        f"- `{t.task_id}` metric `{m}` excluded (missing from {missing_in} file)"
        for t in comp.tasks
        for m, missing_in in sorted(t.excluded_metrics.items())
    ]
    notes += [
        f"- UNPAIRED: `{task_id}` missing from {missing_in} file (excluded)"
        for task_id, missing_in in sorted(comp.unpaired.items())
    ]
    notes += [
        f"- UNCOMPARABLE: `{task_id}` is in both files but shares no metric (excluded)"
        for task_id in sorted(comp.no_common_metrics)
    ]
    if notes:
        lines.append("")
        lines.extend(notes)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("baseline", help="Baseline (skill OFF) scores JSON")
    parser.add_argument("candidate", help="Candidate (skill ON) scores JSON")
    parser.add_argument("--pass-rule", choices=PASS_RULES, default="all_metrics")
    parser.add_argument("--format", choices=("text", "markdown"), default="text")
    parser.add_argument(
        "--difficulty",
        help="Optional JSON {task_id: easy|hard|edge} from the evalset; enables the ship gate",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when the ship gate fails (for CI)",
    )
    args = parser.parse_args(argv)

    baseline = load_scores(args.baseline)
    candidate = load_scores(args.candidate)
    difficulty = load_difficulty(args.difficulty) if args.difficulty else None
    comp = compare(baseline, candidate, pass_rule=args.pass_rule, difficulty=difficulty)

    if not comp.tasks:
        print("No paired tasks found — check task_id values match in both files.", file=sys.stderr)
        return 1

    print(format_markdown(comp) if args.format == "markdown" else format_text(comp))
    if args.strict:
        if not gate_evaluable(comp):
            print(
                "--strict requires an evaluable ship gate: pass --difficulty with a label "
                "for at least one paired task.",
                file=sys.stderr,
            )
            return 1
        if not comp.ship_gate_passed:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
