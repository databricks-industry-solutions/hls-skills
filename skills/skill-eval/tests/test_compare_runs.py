"""Unit tests for skills/skill-eval/scripts/compare_runs.py."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from compare_runs import (  # noqa: E402
    OUTCOME_REGRESSION,
    OUTCOME_TIE_FAIL,
    OUTCOME_TIE_PASS,
    OUTCOME_WIN,
    compare,
    format_markdown,
    format_text,
    load_scores,
    main,
    outcome,
    task_passed,
)


def test_task_passed_all_metrics():
    assert task_passed({"a": True, "b": True}, "all_metrics") is True
    assert task_passed({"a": True, "b": False}, "all_metrics") is False


def test_task_passed_any_metric():
    assert task_passed({"a": False, "b": True}, "any_metric") is True
    assert task_passed({"a": False, "b": False}, "any_metric") is False


def test_task_passed_empty_metrics_fails():
    assert task_passed({}, "all_metrics") is False
    assert task_passed({}, "any_metric") is False


def test_outcome_matrix():
    assert outcome(False, True) == OUTCOME_WIN
    assert outcome(True, False) == OUTCOME_REGRESSION
    assert outcome(True, True) == OUTCOME_TIE_PASS
    assert outcome(False, False) == OUTCOME_TIE_FAIL


def test_compare_counts_and_rates():
    baseline = {
        "t1": {"m": True},
        "t2": {"m": False},
        "t3": {"m": True},
        "t4": {"m": False},
    }
    candidate = {
        "t1": {"m": True},
        "t2": {"m": True},
        "t3": {"m": False},
        "t4": {"m": False},
    }
    comp = compare(baseline, candidate)
    counts = comp.counts()
    assert counts[OUTCOME_TIE_PASS] == 1  # t1
    assert counts[OUTCOME_WIN] == 1  # t2
    assert counts[OUTCOME_REGRESSION] == 1  # t3
    assert counts[OUTCOME_TIE_FAIL] == 1  # t4
    assert comp.win_rate == 0.25
    assert comp.regression_rate == 0.25


def test_compare_metric_flips_only_common_metrics():
    baseline = {"t1": {"a": True, "b": False}}
    candidate = {"t1": {"a": True, "c": False}}
    comp = compare(baseline, candidate)
    assert set(comp.tasks[0].metric_flips) == {"a"}


def test_compare_unpaired_excluded_and_reported():
    baseline = {"t1": {"m": True}, "t2": {"m": True}}
    candidate = {"t1": {"m": True}, "t3": {"m": True}}
    comp = compare(baseline, candidate)
    assert [t.task_id for t in comp.tasks] == ["t1"]
    assert comp.unpaired == {"t2": "candidate", "t3": "baseline"}
    assert comp.win_rate == 0.0  # only paired task counted


def test_compare_empty_paired_set():
    comp = compare({"a": {"m": True}}, {"b": {"m": True}})
    assert comp.tasks == []
    assert comp.win_rate == 0.0
    assert set(comp.unpaired) == {"a", "b"}


def test_load_scores_coerces_values(tmp_path):
    p = tmp_path / "scores.json"
    p.write_text(json.dumps({"t1": {"m1": "yes", "m2": "no", "m3": 1, "m4": False}}))
    scores = load_scores(p)
    assert scores == {"t1": {"m1": True, "m2": False, "m3": True, "m4": False}}


def test_load_scores_rejects_bad_shape(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(["not", "a", "dict"]))
    try:
        load_scores(p)
    except ValueError:
        return
    raise AssertionError("expected ValueError for non-dict top level")


def test_formats_render():
    comp = compare({"t1": {"m": False}}, {"t1": {"m": True}})
    text = format_text(comp)
    md = format_markdown(comp)
    assert "t1" in text and OUTCOME_WIN in text
    assert "| t1 | fail | pass | **win** |" in md
    assert "Win rate: 1/1" in md


def test_main_end_to_end(tmp_path, capsys):
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    b.write_text(json.dumps({"t1": {"m": False}, "t2": {"m": True}}))
    c.write_text(json.dumps({"t1": {"m": True}, "t2": {"m": True}}))
    rc = main([str(b), str(c)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "wins: 1" in out


def test_main_no_paired_tasks_returns_1(tmp_path, capsys):
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    b.write_text(json.dumps({"t1": {"m": True}}))
    c.write_text(json.dumps({"t2": {"m": True}}))
    rc = main([str(b), str(c)])
    assert rc == 1
    assert "No paired tasks" in capsys.readouterr().err


def test_main_pass_rule_any_metric(tmp_path, capsys):
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    b.write_text(json.dumps({"t1": {"m1": True, "m2": False}}))
    c.write_text(json.dumps({"t1": {"m1": True, "m2": False}}))
    rc = main([str(b), str(c), "--pass-rule", "any_metric"])
    assert rc == 0
    assert "tie-pass" in capsys.readouterr().out


def test_main_format_markdown(tmp_path, capsys):
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    b.write_text(json.dumps({"t1": {"m": False}}))
    c.write_text(json.dumps({"t1": {"m": True}}))
    rc = main([str(b), str(c), "--format", "markdown"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("| task_id |")
    assert "**win**" in out


def test_main_difficulty_ship_gate(tmp_path, capsys):
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    d = tmp_path / "d.json"
    b.write_text(json.dumps({"t1": {"m": True}, "t2": {"m": True}}))
    c.write_text(json.dumps({"t1": {"m": False}, "t2": {"m": True}}))
    d.write_text(json.dumps({"t1": "easy", "t2": "hard"}))
    rc = main([str(b), str(c), "--difficulty", str(d)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "SHIP GATE FAIL" in out
    assert "t1" in out


def test_easy_regressions_only_flags_easy():
    comp = compare(
        {"t1": {"m": True}, "t2": {"m": True}},
        {"t1": {"m": False}, "t2": {"m": False}},
        difficulty={"t1": "easy", "t2": "hard"},
    )
    assert comp.easy_regressions == ["t1"]


def test_asymmetric_metrics_pass_computed_on_common_only():
    # baseline has extra metric b (False) — must not drag baseline to FAIL
    comp = compare(
        {"t1": {"a": True, "b": False}},
        {"t1": {"a": True}},
    )
    t = comp.tasks[0]
    assert t.baseline_pass is True
    assert t.candidate_pass is True
    assert t.outcome == OUTCOME_TIE_PASS
    assert t.excluded_metrics == {"b": "candidate"}


def test_asymmetric_metrics_reported_in_text():
    comp = compare({"t1": {"a": True, "b": False}}, {"t1": {"a": True}})
    text = format_text(comp)
    assert "excluded (missing from candidate file)" in text


def test_zero_shared_metrics_excluded_from_rates():
    comp = compare({"t1": {"a": False}}, {"t1": {"b": False}})
    assert comp.tasks == []
    assert "t1" in comp.unpaired
    assert comp.win_rate == 0.0


def test_load_scores_rejects_unknown_values(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"t1": {"m": "maybe"}}))
    try:
        load_scores(p)
    except ValueError as exc:
        assert "maybe" in str(exc)
        return
    raise AssertionError("expected ValueError for unrecognized score value")


def test_load_difficulty_validates_labels(tmp_path):
    from compare_runs import load_difficulty

    good = tmp_path / "d.json"
    good.write_text(json.dumps({"t1": "easy", "t2": " HARD "}))
    assert load_difficulty(good) == {"t1": "easy", "t2": "hard"}

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"t1": "trivial"}))
    try:
        load_difficulty(bad)
    except ValueError:
        return
    raise AssertionError("expected ValueError for invalid difficulty label")


def test_ship_gate_pass_verdict():
    comp = compare(
        {"t1": {"m": False}, "t2": {"m": True}},
        {"t1": {"m": True}, "t2": {"m": True}},
        difficulty={"t1": "easy", "t2": "easy"},
    )
    assert comp.ship_gate_passed is True
    assert "SHIP GATE PASS" in format_text(comp)


def test_ship_gate_fail_on_no_wins():
    comp = compare(
        {"t1": {"m": True}},
        {"t1": {"m": True}},
        difficulty={"t1": "easy"},
    )
    assert comp.ship_gate_passed is False
    assert "no wins" in format_text(comp)


def test_main_strict_exit_codes(tmp_path, capsys):
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    d = tmp_path / "d.json"
    d.write_text(json.dumps({"t1": "easy"}))

    b.write_text(json.dumps({"t1": {"m": True}}))
    c.write_text(json.dumps({"t1": {"m": False}}))
    assert main([str(b), str(c), "--difficulty", str(d), "--strict"]) == 1

    b.write_text(json.dumps({"t1": {"m": False}}))
    c.write_text(json.dumps({"t1": {"m": True}}))
    assert main([str(b), str(c), "--difficulty", str(d), "--strict"]) == 0
