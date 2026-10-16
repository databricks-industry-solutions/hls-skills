"""Scoring must match the benchmark's llm_judge.py; skills bundles must never carry eval/ or tests/; task
selection, labeling, the schedule, blinding and the statistics must behave as README.md says."""

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import analyze  # noqa: E402
import label  # noqa: E402
import run  # noqa: E402
import taskset  # noqa: E402
from judge import first_json_object, parse_rubric_levels, redact, score_response  # noqa: E402
from run import install_skills, token_usage  # noqa: E402

# Shape of the current rubric format (da-1-3) plus one legacy-format criterion.
RUBRIC = """RUBRIC: example

Criterion 1: Tissue-Compartment and Baseline Filtering
    Levels: A=13 B=8 C=0
      [A]: Filters for the three tissue types.

Criterion 2: Enrichment Metric
    Levels: A=16 B=10 C=0
      [A]: Ro/e or normalized fold-change.

Criterion 3: Legacy format
      [A] (20 points): full credit
      [B] (5 points): partial
      [C] (0 points): none
"""


def test_parse_rubric_levels_both_formats():
    assert parse_rubric_levels(RUBRIC) == {
        "criterion_1": {"A": 13, "B": 8, "C": 0},
        "criterion_2": {"A": 16, "B": 10, "C": 0},
        "criterion_3": {"A": 20, "B": 5, "C": 0},
    }


def test_points_come_from_rubric_not_model():
    response = json.dumps({
        "criteria": {
            "criterion_1": {"level": "A", "reason": "ok", "score": 99},
            "criterion_2": {"level": "b", "reason": "lowercase level"},
            "criterion_3": {"level": "Z", "reason": "unknown level"},
        },
        "overall_reasoning": "summary",
    })
    result = score_response(RUBRIC, "Here you go:\n" + response + "\nthanks")
    assert result["total"] == 13 + 10 + 0
    assert result["criteria"]["criterion_1"]["score"] == 13
    assert result["reasoning"] == "summary"


def test_unparseable_response_scores_zero():
    assert score_response(RUBRIC, "I cannot grade this.")["total"] == 0
    assert score_response(RUBRIC, '{"criteria": {')["total"] == 0


def test_first_json_object_ignores_trailing_objects():
    assert first_json_object('x {"a": {"b": 1}} {"c": 2}') == {"a": {"b": 1}}


def test_token_usage_sums_completed_turns(tmp_path):
    events = tmp_path / "events.jsonl"
    events.write_text("\n".join([
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 7}}),
        "not json",
        json.dumps({"type": "item.completed", "usage": {"input_tokens": 999}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 50, "cached_input_tokens": 0, "output_tokens": 3}}),
    ]))
    assert token_usage(events) == {"input_tokens": 150, "cached_input_tokens": 80, "output_tokens": 10}


def test_genie_profile_disables_every_user_skill(tmp_path, monkeypatch):
    agents = tmp_path / "agents-skills"
    (agents / "caveman").mkdir(parents=True)
    (agents / "caveman" / "SKILL.md").write_text("---\nname: caveman\n---\n")
    (agents / "folder-name").mkdir()
    (agents / "folder-name" / "SKILL.md").write_text("---\nname: 'quoted-name'\n---\n")
    (agents / "no-frontmatter").mkdir()
    (agents / "no-frontmatter" / "SKILL.md").write_text("# just a heading\n")
    monkeypatch.setattr(run, "GENIE_HOME", tmp_path)
    monkeypatch.setattr(run, "USER_SKILL_DIRS", (tmp_path / "missing", agents))

    text = run.write_genie_profile().read_text()
    assert 'approval_policy = "never"' in text and "network_access = true" in text
    for name in ("caveman", "quoted-name", "no-frontmatter"):
        assert f'[[skills.config]]\nname = "{name}"\nenabled = false' in text


def test_installed_skills_exclude_answer_keys(tmp_path):
    names = install_skills(run.git("rev-parse", "HEAD"), tmp_path)
    assert "bulk-rnaseq" in names and "sc-rnaseq" in names
    for name in names:
        assert (tmp_path / name / "SKILL.md").is_file()
        assert not (tmp_path / name / "eval").exists()
        assert not (tmp_path / name / "tests").exists()


def test_rate_limited_needs_failed_turn(tmp_path):
    events = tmp_path / "events.jsonl"
    limit = {"type": "error", "message": "429 Too Many Requests: REQUEST_LIMIT_EXCEEDED: input tokens per minute"}
    events.write_text(json.dumps(limit) + "\n" + json.dumps({"type": "turn.completed", "usage": {}}))
    assert not run.rate_limited(events)  # genie retried by itself and the turn finished
    events.write_text(json.dumps(limit) + "\n" + json.dumps({"type": "turn.failed", "error": limit}))
    assert run.rate_limited(events)


def test_arm_specs_pin_refs_to_shas():
    arms = run.resolve_arms(["no_skills", "v1=HEAD"])
    assert arms["no_skills"] == {"ref": None, "sha": None, "skills_tree": None}
    assert arms["v1"]["sha"] == run.git("rev-parse", "HEAD") and len(arms["v1"]["skills_tree"]) == 40


def test_arm_specs_with_instructions():
    arms = run.resolve_arms(["d0=HEAD:D0"])
    assert arms["d0"]["sha"] == run.git("rev-parse", "HEAD") and arms["d0"]["instructions"] == "D0"
    assert len(arms["d0"]["instructions_sha256"]) == 64
    for bad in ("x=HEAD:missing", "x=", "no_skills=HEAD", "plain"):
        with pytest.raises(SystemExit):
            run.resolve_arms([bad])


def test_workdir_follows_the_arm(tmp_path, monkeypatch):
    real_run = run.subprocess.run
    monkeypatch.setattr(run, "OSB_HOME", tmp_path)
    # Only `uv venv` is faked; git still runs, so the skills come from the real repo.
    monkeypatch.setattr(run.subprocess, "run", lambda cmd, *a, **k: real_run(cmd, *a, **k) if cmd[0] == "git"
                        else run.subprocess.CompletedProcess(cmd, 0))
    (tmp_path / "data" / "t").mkdir(parents=True)
    run.prepare_workdir(tmp_path / "d0", "t", {"sha": run.git("rev-parse", "HEAD"), "instructions": "D0"})
    run.prepare_workdir(tmp_path / "none", "t", {"sha": None})
    assert (tmp_path / "d0" / "AGENTS.md").read_bytes() == (run.INSTRUCTIONS_DIR / "D0.md").read_bytes()
    assert (tmp_path / "d0" / ".agents" / "skills" / "bulk-rnaseq" / "SKILL.md").is_file()
    assert not (tmp_path / "none" / "AGENTS.md").exists() and not (tmp_path / "none" / ".agents").exists()


def test_data_are_read_only_hard_links(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "OSB_HOME", tmp_path)
    monkeypatch.setattr(run.subprocess, "run", lambda cmd, *a, **k: run.subprocess.CompletedProcess(cmd, 0))
    src = tmp_path / "data" / "t" / "sub" / "x.csv"
    src.parent.mkdir(parents=True)
    src.write_text("a\n")
    run.prepare_workdir(tmp_path / "wd", "t", {"sha": None})
    data = tmp_path / "wd" / "data"
    assert not data.is_symlink() and (data / "sub" / "x.csv").read_text() == "a\n"
    assert (data / "sub" / "x.csv").stat().st_ino == src.stat().st_ino  # no disk cost
    with pytest.raises(PermissionError):
        (data / "sub" / "x.csv").write_text("changed")  # the shared copy cannot be changed in place


def test_opened_skills_come_from_commands_in_first_open_order(tmp_path):
    def cmd(command):
        return json.dumps({"type": "item.started", "item": {"type": "command_execution", "command": command}})

    events = tmp_path / "events.jsonl"
    events.write_text("\n".join([
        cmd("ls .agents/skills"),
        cmd("sed -n 1,200p .agents/skills/bulk-rnaseq/SKILL.md"),
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": ".agents/skills/sc-rnaseq/SKILL.md"}}),
        cmd("cat /w/.agents/skills/pathway-enrichment-analysis/SKILL.md .agents/skills/bulk-rnaseq/SKILL.md"),
    ]))
    # A path the agent only mentions in a message is not an open.
    assert run.opened_skills(events) == ["bulk-rnaseq", "pathway-enrichment-analysis"]


def test_schedule_is_seeded_and_blocked_by_replicate():
    tasks, arms = ["t1", "t2", "t3"], ["no_skills", "v1", "v2"]
    first = run.build_schedule(tasks, arms, [1, 2], seed=7)
    assert first == run.build_schedule(tasks, arms, [1, 2], seed=7)
    assert first != run.build_schedule(tasks, arms, [1, 2], seed=8)
    assert [x["rep"] for x in first] == [1] * 9 + [2] * 9
    assert {(x["task"], x["arm"], x["rep"]) for x in first} == {(t, a, r) for t in tasks for a in arms for r in (1, 2)}
    # A task's arms run back to back, so they run close in time.
    for i in range(0, len(first), 3):
        assert len({x["task"] for x in first[i:i + 3]}) == 1


def test_clean_workdir_keeps_outputs_and_drops_bulk(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "MAX_KEPT_FILE_BYTES", 10)
    wd = tmp_path / "wd"
    (wd / ".venv" / "lib").mkdir(parents=True)
    (wd / ".cache").mkdir()
    (wd / "out").mkdir()
    for name in ("trace.md", "answer.txt", "events.jsonl", "run.json"):
        (wd / name).write_text("x")
    (wd / "out" / "big.h5ad").write_text("y" * 50)
    target = tmp_path / "task-data.h5ad"
    target.write_text("z" * 50)
    (wd / "data").mkdir()
    run.os.link(target, wd / "data" / "task-data.h5ad")

    removed = run.clean_workdir(wd)
    assert removed == ["out/big.h5ad"]
    assert not (wd / ".venv").exists() and not (wd / ".cache").exists()
    assert all((wd / n).exists() for n in ("trace.md", "answer.txt", "events.jsonl", "run.json"))
    assert (wd / "data" / "task-data.h5ad").exists()  # hard links into the shared data stay


def test_low_disk_skips_without_starting(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "free_gb", lambda _path: 1.0)
    meta = run.run_one(tmp_path, {"task": "t", "arm": "no_skills", "rep": 1}, {"no_skills": {"sha": None}}, {})
    assert meta["skipped"] == "low_disk" and not (tmp_path / "t").exists()


def test_ip_acl_block_is_moved_aside_and_stops_the_batch(tmp_path, monkeypatch):
    blocked = {"type": "turn.failed", "error": {"message": "403 Forbidden: Source IP address: 1.2.3.4 is blocked by "
                                                           "Databricks IP ACL for workspace: 1"}}
    (tmp_path / "grading" / "t").mkdir(parents=True)
    (tmp_path / "grading" / "t" / "instruction.md").write_text("do it")
    monkeypatch.setattr(run, "OSB_HOME", tmp_path / "osb")
    monkeypatch.setattr(run, "OSB_GRADING", tmp_path / "grading")
    monkeypatch.setattr(run, "free_gb", lambda _path: 100.0)
    monkeypatch.setattr(run, "network_blocked", run.threading.Event())
    monkeypatch.setattr(run, "prepare_workdir", lambda wd, *_: (wd.mkdir(parents=True), ([], {}))[1])

    def fake_genie(*_args, stdout, **_kwargs):
        stdout.write(json.dumps(blocked) + "\n")
        return run.subprocess.CompletedProcess([], 1)

    monkeypatch.setattr(run.subprocess, "run", fake_genie)
    run_dir = tmp_path / "osb" / "runs" / "r"
    arms = {"no_skills": {"sha": None}}
    meta = run.run_one(run_dir, {"task": "t", "arm": "no_skills", "rep": 1}, arms, {})
    assert meta["skipped"] == "ip_acl" and not (run_dir / "t" / "no_skills" / "rep1").exists()
    [moved] = (tmp_path / "osb" / "infra-failed").iterdir()
    assert moved.name.startswith("r-t-no_skills-rep1-ip_acl-") and not (moved / "run.json").exists()
    assert run.run_one(run_dir, {"task": "t", "arm": "no_skills", "rep": 2}, arms, {})["skipped"] == "network"


def test_network_failure_needs_failed_turn(tmp_path):
    events = tmp_path / "events.jsonl"
    lost = {"message": "stream disconnected before completion: error sending request for url (https://x/responses)"}
    events.write_text(json.dumps({"type": "error", **lost}) + "\n" + json.dumps({"type": "turn.completed", "usage": {}}))
    assert run.network_failure(events) is None  # genie reconnected and the turn finished
    events.write_text(json.dumps({"type": "turn.failed", "error": lost}))
    assert run.network_failure(events) == "connection_lost"


def test_redact_hides_which_arm_ran():
    text = ("Read .agents/skills/bulk-rnaseq/SKILL.md, then used bulk-rnaseq and sc-rnaseq. "
            "bulk-rnaseq-like tools and the scanpy pipeline stay.")
    out = redact(text, ["bulk-rnaseq", "sc-rnaseq"])
    assert "bulk-rnaseq " not in out and "sc-rnaseq" not in out and "SKILL.md" not in out and ".agents" not in out
    assert "bulk-rnaseq-like" in out and "scanpy" in out


def test_redact_hides_which_agent_and_instructions_ran():
    out = redact("Per AGENTS.md I ran it in Genie Code CLI; codex wrote answer.txt. The genie-like genes stay.", [])
    assert "AGENTS.md" not in out and "Genie" not in out and "codex" not in out
    assert out.count("[agent]") == 2 and "answer.txt" in out and "genie-like" in out


def test_sign_test_exact_binomial():
    assert analyze.sign_test([1, 2, 3, 4, 5]) == (5, 0, 0.0625)
    assert analyze.sign_test([1, -1, 0]) == (1, 1, 1.0)


def test_bootstrap_recovers_a_known_effect():
    import random

    rng = random.Random(0)
    cell_scores = {}
    for t in ("t1", "t2", "t3", "t4", "t5"):
        base = rng.uniform(20, 80)
        cell_scores[(t, "a")] = [base + 10 + rng.gauss(0, 3) for _ in range(3)]
        cell_scores[(t, "b")] = [base + rng.gauss(0, 3) for _ in range(3)]
    tasks = ["t1", "t2", "t3", "t4", "t5"]
    mean, _ = analyze.effect(cell_scores, tasks, "a", "b")
    lo, hi = analyze.bootstrap_ci(cell_scores, tasks, "a", "b", random.Random(1))
    assert 5 < mean < 15 and lo < mean < hi and lo > 0


def test_decision_rules():
    assert analyze.decide("improves", 8.0, -1.0, {"t1": 20, "t2": -4}) == "PASS"
    assert analyze.decide("improves", 8.0, -6.0, {"t1": 20, "t2": -4}) == "inconclusive"
    assert analyze.decide("improves", 8.0, 1.0, {"t1": 40, "t2": -16}) == "inconclusive"
    assert analyze.decide("no_harm", -3.0, -9.0, {"t1": -3}) == "PASS"
    assert analyze.decide("no_harm", -6.0, -9.0, {"t1": -6}) == "FAIL"


def test_token_rise_is_per_task_so_the_task_mix_cannot_drive_it():
    def run_(task, arm, tokens):
        return {"task": task, "arm": arm, "infra_failure": False, "meta": {"input_tokens": tokens, "output_tokens": 0}}

    # Arm a costs the same as b on each task, but has fewer runs of the cheap task.
    runs = [run_("cheap", "b", 100)] * 3 + [run_("big", "b", 1000)] * 3
    runs += [run_("cheap", "a", 100)] * 1 + [run_("big", "a", 1000)] * 3
    assert analyze.median_tokens(runs, ["cheap", "big"], "a") > 1.5 * analyze.median_tokens(runs, ["cheap", "big"], "b")
    assert analyze.token_rise(runs, ["cheap", "big"], "a", "b") == 0


def test_analysis_on_fake_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze, "OSB_HOME", tmp_path)
    expected = {"c1": ["bulk-rnaseq"], "c2": ["sc-rnaseq"], "k1": []}
    task_sets = {"covered": ["c1", "c2"], "control": ["k1"], "all": ["c1", "c2", "k1"]}
    skills = ["bulk-rnaseq", "sc-rnaseq"]
    # The skills arm opens the right skill and scores 20 higher on covered tasks, and the same on the control.
    runs = {"no_skills": ([], False, 50), "skills": (skills, True, 70)}
    grades = []
    for task in task_sets["all"]:
        for arm, (installed, opens, score) in runs.items():
            for rep in (1, 2):
                wd = tmp_path / "runs" / "x" / task / arm / f"rep{rep}"
                wd.mkdir(parents=True)
                (wd / "run.json").write_text(json.dumps({"skills": installed, "opened": expected[task] if opens else [],
                                                         "input_tokens": 10, "output_tokens": 1, "wall_s": 60}))
                grades.append({"run_id": "x", "task": task, "arm": arm, "rep": rep,
                               "score": score if task != "k1" else 50.0, "behavior": {}})
    result = analyze.analyze(grades, task_sets, analyze.comparisons_for("skills", "no_skills"), expected)
    covered, control, everything = result["comparisons"]
    assert covered["effect"] == 20 and covered["decision"] == "PASS"
    assert control["effect"] == 0 and control["decision"] == "PASS"
    assert everything["decision"] == "descriptive"
    assert result["routing"]["skills"] == {"hit_rate": 100.0, "false_trigger_rate": 0.0}
    assert result["per_protocol"]["skills"]["opened"] == {"n": 4, "mean": 70} and "no_skills" not in result["per_protocol"]
    assert "## Skill use" in analyze.to_markdown(result)


def test_combine_two_labelers():
    assert taskset.combine(["bulk-rnaseq", "pathway-enrichment-analysis"], ["bulk-rnaseq"]) == ("covered", ["bulk-rnaseq"])
    assert taskset.combine([], []) == ("control", [])
    assert taskset.combine(["sc-rnaseq"], []) == ("disputed", ["sc-rnaseq"])
    assert taskset.combine(["sc-rnaseq"], ["bulk-rnaseq"]) == ("disputed", ["bulk-rnaseq", "sc-rnaseq"])


def test_select_tasks_for_a_skill():
    tasks = [
        {"task_id": "b1", "coverage": "covered", "hls_skills": ["bulk-rnaseq"]},
        {"task_id": "s1", "coverage": "covered", "hls_skills": ["sc-rnaseq"]},
        {"task_id": "d1", "coverage": "disputed", "hls_skills": ["sc-rnaseq"]},
        *({"task_id": f"k{i}", "coverage": "control", "hls_skills": []} for i in range(6)),
    ]
    picked = taskset.select(tasks, "sc-rnaseq", controls=2, seed=1)
    assert picked[0] == "s1" and len(picked) == 3 and all(t.startswith("k") for t in picked[1:])
    assert picked == taskset.select(tasks, "sc-rnaseq", controls=2, seed=1)  # seeded
    assert taskset.select(tasks) == ["b1", "s1"] + [f"k{i}" for i in range(6)]  # disputed tasks never run
    with pytest.raises(SystemExit):
        taskset.select(tasks, "cohort-builder")


def test_tasks_json_round_trips_and_is_labeled(tmp_path):
    doc = taskset.load()
    assert doc["labels"]["skills_sha"] and all(t["coverage"] in taskset.COVERAGE for t in doc["tasks"])
    assert all(t["hls_skills"] for t in doc["tasks"] if t["coverage"] == "covered")
    taskset.save(doc, tmp_path / "tasks.json")
    assert taskset.load(tmp_path / "tasks.json") == doc


def test_labeler_sees_descriptions_and_task_only():
    skills = label.skill_descriptions(run.git("rev-parse", "HEAD"))
    assert {"bulk-rnaseq", "sc-rnaseq"} <= set(skills) and all(skills.values())
    prompt = label.prompt_for(skills, "Cluster these bulk RNA-seq samples.")
    assert "- bulk-rnaseq: " in prompt and "Cluster these bulk RNA-seq samples." in prompt
    assert "rubric" not in prompt.lower()


def test_label_parse_keeps_only_known_skills():
    known = {"bulk-rnaseq", "sc-rnaseq"}
    out = label.parse('Sure: {"skills": ["bulk-rnaseq", "made-up"], "reason": "DE"}', known)
    assert out == {"skills": ["bulk-rnaseq"], "reason": "DE", "unknown_skills": ["made-up"]}
    assert label.parse("no json here", known)["unparseable"]
