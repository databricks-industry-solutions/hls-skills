#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["mlflow[databricks]>=3.4", "databricks-sdk>=0.40", "openai>=1.40", "httpx", "pandas"]
# ///
"""Grade BiomniBench-DA runs with each task's own rubric, as MLflow LLM judges on FMAPI.

The prompt and rubric-level scoring are ported from the benchmark's tests/llm_judge.py: the judge
picks a level (A/B/C) for each criterion, and points come from the rubric, never from the model.
The default judge is Gemini 3.8 Flash on Foundation Model APIs. The benchmark ships a Gemini Flash
judge; pick a judge from a different model family than the agent's model. --judge-endpoint grades with
any other chat endpoint in the workspace.

Before grading, skill names and skill paths are removed from every trace and answer, so the judge
cannot tell which arm produced a run. Each answer is graded --repeats times. A second fixed prompt
records yes/no behavior checks for common analysis failure modes. --calibrate also grades
OpenScience's published answers with the same judge. Output goes to $OSB_HOME/grades/<out>/.
Graded rows are cached in grades/<out>/rows/, so rerunning the same command after a hang or crash
resumes; the command fails if any run is left ungraded.

    uv run judge.py --run-id sc --out sc --profile <profile>
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OSB_HOME = Path(os.environ.get("OSB_HOME", Path.home() / "osb"))
OSB_GRADING = Path(os.environ.get("OSB_GRADING", Path.home() / ".cache" / "osb-grading"))
JUDGES = {"gemini_3_8_flash": "databricks-gemini-3-8-flash", "claude_sonnet_5_5": "databricks-claude-sonnet-5-5"}
PRIMARY_JUDGE = "gemini_3_8_flash"
OPENSCIENCE_REPO = "synthetic-sciences/benchmarks-openscience"
# A run that touched any of these may have read the answer key.
LEAK_MARKERS = ("osb-grading", "rubric.txt", "llm_judge")

PROMPT = """You are an expert evaluator for a data analysis task.

Evaluate the agent's work using the following rubric:

{rubric}

Here is the agent's analysis trace:

<trace>
{trace}
</trace>

Here is the agent's final answer:

<answer>
{answer}
</answer>

For each criterion in the rubric, choose ONE level: A, B, or C — based purely on which level description best describes the agent's work. Do not output numerical points; the score for each level is computed automatically from the rubric.

You MUST respond with a JSON object in exactly this format:
{{
  "criteria": {{
    "criterion_1": {{"level": "A", "reason": "<one-sentence explanation>"}},
    "criterion_2": {{"level": "B", "reason": "<one-sentence explanation>"}},
    ...
  }},
  "overall_reasoning": "<short summary>"
}}

Each "level" value must be exactly the single character "A", "B", or "C". Only output the JSON object, nothing else."""


def parse_rubric_levels(rubric_text: str) -> dict[str, dict[str, int]]:
    """{criterion_<N>: {"A": pts, "B": pts, "C": pts}} from `Levels: A=X B=Y C=0` or legacy `[A] (X points)`."""
    out: dict[str, dict[str, int]] = {}
    parts = re.split(r"^Criterion\s+(\d+)\s*:", rubric_text, flags=re.MULTILINE)
    for i in range(1, len(parts), 2):
        body = parts[i + 1] if i + 1 < len(parts) else ""
        levels: dict[str, int] = {}
        m = re.search(r"Levels:\s*((?:[A-Z]=\d+\s*)+)", body)
        if m:
            levels = {lm.group(1).upper(): int(lm.group(2)) for lm in re.finditer(r"([A-Z])=(\d+)", m.group(1))}
        if not levels:
            levels = {
                lm.group(1).upper(): int(lm.group(2))
                for lm in re.finditer(r"\[([A-Z])\]\s*\(\s*(\d+)\s*points?\s*\)", body)
            }
        if levels:
            out[f"criterion_{parts[i].strip()}"] = levels
    return out


def first_json_object(text: str) -> dict:
    start = text.find("{")
    if start == -1:
        return json.loads(text)
    depth = 0
    for i, char in enumerate(text[start:], start):
        depth += {"{": 1, "}": -1}.get(char, 0)
        if depth == 0:
            return json.loads(text[start : i + 1])
    raise ValueError("unbalanced JSON object in judge response")


def score_response(rubric: str, response_text: str) -> dict:
    """Map the judge's per-criterion levels to rubric points; total clamped to 0-100."""
    try:
        result = first_json_object(response_text)
    except ValueError as e:  # json.JSONDecodeError is a ValueError
        return {"total": 0, "criteria": {}, "reasoning": f"unparseable judge response: {e}"}
    criteria = result.get("criteria", {})
    levels = parse_rubric_levels(rubric)
    for key, crit in criteria.items():
        if isinstance(crit, dict):
            crit["score"] = levels.get(key, {}).get((crit.get("level") or "").strip().upper(), 0)
    total = sum(c["score"] for c in criteria.values() if isinstance(c, dict))
    reasoning = result.get("overall_reasoning", result.get("reasoning", ""))
    return {"total": max(0, min(100, total)), "criteria": criteria, "reasoning": reasoning}


def grade(client, endpoint: str, rubric: str, trace: str, answer: str) -> dict:
    if not trace and not answer:
        return {"total": 0, "criteria": {}, "reasoning": "no trace.md or answer.txt"}
    prompt = PROMPT.format(
        rubric=rubric, trace=trace or "[No trace file provided]", answer=answer or "[No answer file provided]"
    )
    return score_response(rubric, complete(client, endpoint, prompt))


BEHAVIOR_PROMPT = """You are auditing how a data analysis was carried out. Read the task, the analysis trace and the final answer.

<task>
{task}
</task>

<trace>
{trace}
</trace>

<answer>
{answer}
</answer>

Answer each question with "yes", "no", or "not_applicable" (the analysis did not involve that kind of step).
- ora_background_stated: If the analysis ran an over-representation (ORA / Fisher / hypergeometric) enrichment test, did it state explicitly which background (universe) gene set it used?
- task_threshold_used: If the task stated a significance threshold, did the analysis apply that threshold, rather than a different default, when calling results significant?
- gsea_for_condition_response: If the question asked how a transcriptional response differs across cell types, doses, or conditions, did the analysis run gene set enrichment analysis (GSEA or similar ranked pathway analysis)?
- sc_standard_pipeline: If the analysis worked with single-cell expression data, did it perform quality control, normalization, highly variable gene selection, PCA, and clustering?

Respond with only a JSON object with exactly these four keys, each mapped to "yes", "no", or "not_applicable"."""
BEHAVIOR_KEYS = ("ora_background_stated", "task_threshold_used", "gsea_for_condition_response", "sc_standard_pipeline")


def complete(client, endpoint: str, prompt: str) -> str:
    resp = client.chat.completions.create(model=endpoint, messages=[{"role": "user", "content": prompt}], max_tokens=8192)
    content = resp.choices[0].message.content
    # FMAPI may return content blocks (e.g. reasoning + text) instead of a plain string.
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return content


def behavior(client, endpoint: str, task: str, trace: str, answer: str) -> dict[str, str]:
    prompt = BEHAVIOR_PROMPT.format(task=task, trace=trace, answer=answer)
    try:
        result = first_json_object(complete(client, endpoint, prompt))
    except ValueError:
        result = {}
    return {k: str(result.get(k, "unparseable")).strip().lower() for k in BEHAVIOR_KEYS}


def read(path: Path) -> str:
    return path.read_text(errors="replace") if path.exists() else ""


def leaked(workdir: Path) -> list[str]:
    events = read(workdir / "events.jsonl")
    return [m for m in LEAK_MARKERS if m in events]


def redact(text: str, skill_names: list[str]) -> str:
    """Remove what would tell the judge which arm ran: skill folder paths, skill names, the instruction file and
    the agent's name."""
    text = re.sub(r"\S*\.agents/skills\S*", "[redacted]", text)
    text = re.sub(r"\b(SKILL|AGENTS)\.md\b", "[redacted]", text)
    text = re.sub(r"(?<![\w-])(Genie Code( CLI)?|Genie|Codex( CLI)?)(?![\w-])", "[agent]", text, flags=re.IGNORECASE)
    for name in sorted(skill_names, key=len, reverse=True):
        text = re.sub(rf"(?<![\w-]){re.escape(name)}(?![\w-])", "[redacted]", text)
    return text


def prompt_sha() -> str:
    return hashlib.sha256((PROMPT + BEHAVIOR_PROMPT).encode()).hexdigest()


def openscience_published(task: str) -> dict[str, str]:
    """OpenScience's counted trial for a task: its trace.md and answer.txt."""

    def get(url: str) -> bytes:
        return urllib.request.urlopen(url, timeout=60).read()

    trials = json.loads(get(f"https://api.github.com/repos/{OPENSCIENCE_REPO}/contents/biomnibench-da/{task}"))
    base = f"https://raw.githubusercontent.com/{OPENSCIENCE_REPO}/main/biomnibench-da/{task}/{trials[0]['name']}/verifier"
    return {name: get(f"{base}/{name}").decode(errors="replace") for name in ("trace.md", "answer.txt")}


def collect_rows(run_ids: list[str], calibrate: bool) -> list[dict]:
    """One row per run folder runs/<run-id>/<task>/<arm>/rep<k>, plus OpenScience rows with --calibrate."""
    rows = []
    for run_id in run_ids:
        for workdir in sorted((OSB_HOME / "runs" / run_id).glob("*/*/rep*")):
            meta = json.loads(read(workdir / "run.json") or "{}")
            rows.append({
                "run_id": run_id, "task": workdir.parent.parent.name, "arm": workdir.parent.name,
                "rep": int(workdir.name.removeprefix("rep")), "leaks": leaked(workdir), "skills": meta.get("skills", []),
                "trace": read(workdir / "trace.md"), "answer": read(workdir / "answer.txt"),
            })
    skill_names = sorted({s for r in rows for s in r["skills"]})
    for r in rows:
        r["trace"], r["answer"] = redact(r["trace"], skill_names), redact(r["answer"], skill_names)
    if calibrate:
        for task in sorted({r["task"] for r in rows}):
            pub = openscience_published(task)
            rows.append({"run_id": "openscience", "task": task, "arm": "openscience_published", "rep": 1, "leaks": [],
                         "skills": [], "trace": pub["trace.md"], "answer": pub["answer.txt"]})
    return rows


def main() -> None:
    import mlflow
    from databricks.sdk import WorkspaceClient
    from mlflow.entities import Feedback
    from mlflow.genai.scorers import scorer

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", action="append", required=True, help="run folder under $OSB_HOME/runs; repeat")
    ap.add_argument("--out", required=True, help="output name under $OSB_HOME/grades")
    ap.add_argument("--profile", required=True, help="Databricks CLI profile for FMAPI + MLflow")
    ap.add_argument("--calibrate", action="store_true", help="also grade OpenScience's published answers")
    ap.add_argument("--repeats", type=int, default=5, help="grade each answer N times")
    ap.add_argument("--judge", choices=sorted(JUDGES), default=PRIMARY_JUDGE, help="judge model")
    ap.add_argument("--judge-endpoint", help="any other serving endpoint name; overrides --judge")
    args = ap.parse_args()

    # MLflow's artifact upload builds its own SDK config, which ignores the databricks://<profile> URI.
    os.environ["DATABRICKS_CONFIG_PROFILE"] = args.profile
    out_dir = OSB_HOME / "grades" / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = collect_rows(args.run_id, args.calibrate)
    w = WorkspaceClient(profile=args.profile)
    # The default (10 min, 2 retries) let one hung request stall a whole grading pass for over an hour.
    client = w.serving_endpoints.get_open_ai_client().with_options(timeout=300, max_retries=3)
    mlflow.set_tracking_uri(f"databricks://{args.profile}")
    mlflow.set_experiment(f"/Users/{w.current_user.me().user_name}/biomnibench-hls")
    endpoint = args.judge_endpoint or JUDGES[args.judge]
    results: dict[tuple, dict] = {}
    # Each graded row is saved as soon as it is done, so a rerun after a hang or crash resumes. A cached row
    # is reused only if it was graded with the same prompts, repeats and redacted inputs.
    cache_dir = out_dir / "rows"
    cache_dir.mkdir(exist_ok=True)

    # One row is 5 grades plus a behavior check, which can outlast MLflow's default per-scorer timeout. A timed-out
    # scorer keeps running in a daemon thread that dies when evaluate returns, so its row never reaches grades.json.
    # The client timeout above and the saved rows already handle a hung request.
    @scorer(name=args.judge, timeout=0)
    def rubric_judge(inputs, outputs, expectations) -> Feedback:
        key = (inputs["run_id"], inputs["task"], inputs["arm"], inputs["rep"])
        cache_path = cache_dir / ("__".join(map(str, key)) + ".json")
        inputs_sha = hashlib.sha256(json.dumps([prompt_sha(), args.repeats, outputs, expectations]).encode()).hexdigest()
        cached = json.loads(read(cache_path) or "{}")
        if cached.get("inputs_sha") == inputs_sha:
            results[key] = cached["result"]
        else:
            runs = [grade(client, endpoint, expectations["rubric"], outputs["trace"], outputs["answer"])
                    for _ in range(args.repeats)]
            totals = [g["total"] for g in runs]
            task_text = read(OSB_GRADING / inputs["task"] / "instruction.md")
            checks = behavior(client, endpoint, task_text, outputs["trace"], outputs["answer"])
            results[key] = {"score": sum(totals) / len(totals), "totals": totals, "behavior": checks, "grades": runs}
            cache_path.write_text(json.dumps({"inputs_sha": inputs_sha, "result": results[key]}))
        runs, totals = results[key]["grades"], results[key]["totals"]
        print(f"graded {'/'.join(map(str, key))}: {totals}", flush=True)
        return Feedback(value=results[key]["score"], rationale=runs[0]["reasoning"], metadata={"totals": json.dumps(totals)})

    data = [
        {
            "inputs": {k: r[k] for k in ("run_id", "task", "arm", "rep")},
            "outputs": {"trace": r["trace"], "answer": r["answer"]},
            "expectations": {"rubric": read(OSB_GRADING / r["task"] / "tests" / "rubric.txt")},
        }
        for r in rows
    ]
    with mlflow.start_run(run_name=f"grades-{args.out}"):
        mlflow.genai.evaluate(data=data, scorers=[rubric_judge])
        leaks = {f"{r['run_id']}/{r['task']}/{r['arm']}/rep{r['rep']}": r["leaks"] for r in rows if r["leaks"]}
        grades = [{"run_id": k[0], "task": k[1], "arm": k[2], "rep": k[3], **v} for k, v in sorted(results.items())]
        (out_dir / "grades.json").write_text(json.dumps(grades, indent=2))
        (out_dir / "meta.json").write_text(json.dumps({
            "run_ids": args.run_id, "judge_endpoint": endpoint, "repeats": args.repeats, "prompt_sha256": prompt_sha(),
            "calibrate": args.calibrate, "n_rows": len(rows), "leaks": leaks,
            "graded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }, indent=2))
        mlflow.log_artifacts(str(out_dir))
    print(f"wrote {out_dir}; leaks: {leaks or 'none'}")
    if len(grades) != len(rows):
        # Seen in practice: auth errors under concurrency made MLflow drop rows silently.
        raise SystemExit(f"only {len(grades)} of {len(rows)} runs were graded; rerun the same command to resume")


if __name__ == "__main__":
    main()
