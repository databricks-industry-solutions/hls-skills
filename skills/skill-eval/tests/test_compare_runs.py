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
    assert comp.tasks[0].metric_flips == {"a": OUTCOME_TIE_PASS}


def test_compare_metric_flips_classify_each_direction():
    baseline = {"t1": {"up": False, "down": True, "same_pass": True, "same_fail": False}}
    candidate = {"t1": {"up": True, "down": False, "same_pass": True, "same_fail": False}}
    comp = compare(baseline, candidate)
    assert comp.tasks[0].metric_flips == {
        "up": OUTCOME_WIN,
        "down": OUTCOME_REGRESSION,
        "same_pass": OUTCOME_TIE_PASS,
        "same_fail": OUTCOME_TIE_FAIL,
    }


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


def test_main_pass_rule_any_metric_changes_outcome(tmp_path, capsys):
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    b.write_text(json.dumps({"t1": {"m1": True, "m2": False}}))
    c.write_text(json.dumps({"t1": {"m1": True, "m2": False}}))

    assert main([str(b), str(c), "--pass-rule", "all_metrics"]) == 0
    assert "t1: baseline=FAIL candidate=FAIL -> tie-fail" in capsys.readouterr().out

    assert main([str(b), str(c), "--pass-rule", "any_metric"]) == 0
    assert "t1: baseline=PASS candidate=PASS -> tie-pass" in capsys.readouterr().out


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
    assert comp.no_common_metrics == ["t1"]
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


def test_any_regression_blocks_gate_whatever_its_difficulty():
    """A hard or edge regression is the signal the eval exists to catch."""
    for label in ("easy", "hard", "edge"):
        comp = compare(
            {"t1": {"m": False}, "t2": {"m": True}},
            {"t1": {"m": True}, "t2": {"m": False}},
            difficulty={"t1": "easy", "t2": label},
        )
        assert comp.counts()[OUTCOME_WIN] == 1
        assert comp.counts()[OUTCOME_REGRESSION] == 1
        assert comp.ship_gate_passed is False, label
        assert f"regressions: t2 ({label})" in format_text(comp)


def test_unlabeled_regression_blocks_gate_and_map_gap_is_reported():
    """A partial difficulty map must not let a regression through unchecked."""
    comp = compare(
        {"t1": {"m": False}, "t2": {"m": True}},
        {"t1": {"m": True}, "t2": {"m": False}},
        difficulty={"t1": "easy"},
    )
    assert comp.ship_gate_passed is False
    text = format_text(comp)
    assert "regressions: t2 (no label)" in text
    assert "difficulty map is incomplete" in text


def test_no_regressions_gate_passes_a_clean_tie():
    """The regression re-run recipe needs a clean tie to pass under --gate."""
    comp = compare(
        {"t1": {"m": True}},
        {"t1": {"m": True}},
        difficulty={"t1": "easy"},
    )
    assert comp.gate_passed("default") is False  # no wins
    assert comp.gate_passed("no-regressions") is True
    assert "SHIP GATE PASS" in format_text(comp, gate_mode="no-regressions")
    assert "SHIP GATE FAIL (no wins)" in format_text(comp)


def test_no_regressions_gate_still_blocks_a_regression():
    comp = compare(
        {"t1": {"m": True}},
        {"t1": {"m": False}},
        difficulty={"t1": "hard"},
    )
    assert comp.gate_passed("no-regressions") is False


def test_main_gate_flag_flows_into_exit_code(tmp_path):
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    d = tmp_path / "d.json"
    d.write_text(json.dumps({"t1": "easy"}))
    b.write_text(json.dumps({"t1": {"m": True}}))
    c.write_text(json.dumps({"t1": {"m": True}}))
    assert main([str(b), str(c), "--difficulty", str(d), "--strict"]) == 1
    assert (
        main([str(b), str(c), "--difficulty", str(d), "--strict", "--gate", "no-regressions"]) == 0
    )


def test_main_reports_metric_name_mismatch_not_task_id_mismatch(tmp_path, capsys):
    """Matching task_ids with different metric names must not blame task_ids."""
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    b.write_text(json.dumps({"t1": {"planted_check": True}}))
    c.write_text(json.dumps({"t1": {"planted_genes_check": True}}))
    rc = main([str(b), str(c)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "share no metric name" in err
    assert "task_id values match" not in err


def test_main_strict_fails_on_unpaired_task(tmp_path, capsys):
    """A candidate that dropped a task must not clear the gate under --strict."""
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    d = tmp_path / "d.json"
    d.write_text(json.dumps({"t1": "easy", "t2": "hard"}))
    # t1 is a clean win; t2 (which baseline passed) is missing from the candidate.
    b.write_text(json.dumps({"t1": {"m": False}, "t2": {"m": True}}))
    c.write_text(json.dumps({"t1": {"m": True}}))
    rc = main([str(b), str(c), "--difficulty", str(d), "--strict"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "complete comparison" in captured.err
    # --allow-incomplete ships on the paired subset (t1 win, no regressions).
    assert main([str(b), str(c), "--difficulty", str(d), "--strict", "--allow-incomplete"]) == 0


def test_main_strict_fails_on_uncomparable_task(tmp_path, capsys):
    """A task present in both files but sharing no metric blocks --strict."""
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    d = tmp_path / "d.json"
    d.write_text(json.dumps({"t1": "easy", "t2": "hard"}))
    b.write_text(json.dumps({"t1": {"m": False}, "t2": {"planted_check": True}}))
    c.write_text(json.dumps({"t1": {"m": True}, "t2": {"planted_genes_check": True}}))
    rc = main([str(b), str(c), "--difficulty", str(d), "--strict"])
    assert rc == 1
    assert "complete comparison" in capsys.readouterr().err


def test_main_strict_fails_on_partial_metric_rename(tmp_path, capsys):
    """Renaming only the metric that would regress must not clear --strict."""
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    d = tmp_path / "d.json"
    d.write_text(json.dumps({"t1": "easy", "t2": "hard"}))
    # t1: clean win. t2: baseline would regress on `regressing`, but the candidate
    # renamed that metric, so only `shared` is compared -> tie-pass hides the loss.
    b.write_text(json.dumps({"t1": {"m": False}, "t2": {"shared": True, "regressing": True}}))
    c.write_text(json.dumps({"t1": {"m": True}, "t2": {"shared": True, "renamed": False}}))
    rc = main([str(b), str(c), "--difficulty", str(d), "--strict"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "complete comparison" in captured.err
    # The non-strict verdict must carry the incompleteness caveat, not a bare PASS.
    assert "comparison incomplete" in captured.out
    # --allow-incomplete ships on the paired subset deliberately.
    assert main([str(b), str(c), "--difficulty", str(d), "--strict", "--allow-incomplete"]) == 0


def test_allow_incomplete_without_strict_warns(tmp_path, capsys):
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    b.write_text(json.dumps({"t1": {"m": False}}))
    c.write_text(json.dumps({"t1": {"m": True}}))
    rc = main([str(b), str(c), "--allow-incomplete"])
    assert rc == 0
    assert "no effect without --strict" in capsys.readouterr().err


def test_main_strict_fails_when_gate_not_evaluable(tmp_path, capsys):
    """--strict without --difficulty must not report success."""
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    b.write_text(json.dumps({"t1": {"m": True}}))
    c.write_text(json.dumps({"t1": {"m": False}}))
    rc = main([str(b), str(c), "--strict"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "--strict requires an evaluable ship gate" in captured.err
    assert "SHIP GATE NOT EVALUATED" in captured.out


def test_no_shared_metrics_is_not_an_unpaired_task():
    """A task in both files with no shared metric is reported as uncomparable."""
    comp = compare({"t1": {"a": True}}, {"t1": {"b": True}})
    assert comp.unpaired == {}
    assert "UNCOMPARABLE: task 't1' is in both files but shares no metric" in format_text(comp)


def test_markdown_renders_metric_flips():
    comp = compare(
        {"t1": {"a": True, "b": True}},
        {"t1": {"a": False, "b": True}},
        difficulty={"t1": "easy"},
    )
    md = format_markdown(comp)
    assert "`t1` metric `a` flipped to regression" in md
    assert "`b`" not in md.split("Regressions:")[1]
