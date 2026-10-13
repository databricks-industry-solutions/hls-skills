"""Unit tests for the generalized criteria layer (scripts/criteria.py).

Guards the condition-agnostic generalization: the clinical-threshold registry + measure-column
grounding, the fail-loud detection of unregistered out-of-range terms, and the demographic /
attribute filter compilation (ages, genders, arbitrary grounded columns) incl. SQL rendering and
escaping. Pure Python, offline, sub-second — no warehouse.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# criteria.py lives in this skill's scripts/ dir (sibling of tests/), pure + SDK-free.
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))
import criteria as c  # noqa: E402


# --- threshold registry + detection ------------------------------------------

def test_detect_registered_term():
    assert c.detect_threshold_term("adults with uncontrolled hypertension").term == "uncontrolled hypertension"
    assert c.detect_threshold_term("high LDL cohort").term == "high ldl"
    assert c.detect_threshold_term("sepsis cohort") is None


def test_detect_prefers_longest_term():
    # "poorly controlled hba1c" must win over any shorter substring match.
    assert c.detect_threshold_term("T2D poorly controlled hba1c").term == "poorly controlled hba1c"


def test_registry_options_have_multiple_defensible_cutoffs():
    # The whole point: each term carries >1 cutoff so the skill must surface, not pick.
    for spec in c.CLINICAL_THRESHOLDS:
        assert len(spec.options) >= 2
        for opt in spec.options:
            assert opt["op"] in c.NUMERIC_OPS and isinstance(opt["value"], (int, float))


def test_looks_like_threshold():
    assert c.looks_like_threshold("patients with elevated troponin")
    assert c.looks_like_threshold("uncontrolled asthma")
    assert not c.looks_like_threshold("define a heart failure cohort")


# --- measure-column grounding ------------------------------------------------

def test_ground_measure_from_registry_candidate():
    spec = c.detect_threshold_term("uncontrolled hba1c")
    assert c.ground_measure_column(["patient_id", "hba1c_value", "age"], spec) == "hba1c_value"
    # alternate column name still grounds
    assert c.ground_measure_column(["patient_id", "a1c"], spec) == "a1c"


def test_ground_measure_missing_returns_none():
    spec = c.detect_threshold_term("uncontrolled hba1c")
    assert c.ground_measure_column(["patient_id", "age"], spec) is None


def test_ground_measure_explicit_override():
    # explicit column present wins; explicit column absent -> None (fail loud), never a candidate.
    assert c.ground_measure_column(["ldl", "age"], None, explicit="ldl") == "ldl"
    assert c.ground_measure_column(["age"], None, explicit="ldl") is None


# --- demographic / attribute filters -----------------------------------------

def test_age_from_explicit_age_column():
    f, un = c.compile_demographics(["patient_id", "age"], age_min=18, age_max=64)
    assert not un and len(f) == 2
    assert c.filter_sql(f[0], "t") == "t.age >= 18.0"
    assert c.filter_sql(f[1], "t") == "t.age <= 64.0"


def test_age_derived_from_birthdate():
    f, un = c.compile_demographics(["patient_id", "birth_date"], age_min=65)
    assert not un and len(f) == 1
    sql = c.filter_sql(f[0], "t")
    assert "datediff" in sql and "t.birth_date" in sql and ">= 65.0" in sql


def test_age_unresolved_when_no_age_or_dob():
    f, un = c.compile_demographics(["patient_id", "sex"], age_min=18)
    assert f == [] and len(un) == 1 and "age" in un[0]


def test_sex_scalar_and_list():
    f1, _ = c.compile_demographics(["sex"], sex="F")
    assert c.filter_sql(f1[0], "t") == "t.sex = 'F'"
    f2, _ = c.compile_demographics(["gender"], sex=["M", "F"])
    assert c.filter_sql(f2[0], "t") == "t.gender IN ('M', 'F')"


def test_generic_filter_and_bad_column():
    cols = ["patient_id", "region"]
    f, un = c.compile_demographics(cols, filters=[{"column": "region", "op": "=", "value": "MA"},
                                                  {"column": "nope", "op": ">", "value": 1}])
    assert len(f) == 1 and c.filter_sql(f[0], "t") == "t.region = 'MA'"
    assert len(un) == 1 and "nope" in un[0]


# --- SQL rendering + safety --------------------------------------------------

def test_filter_sql_alias_optional():
    f = c.Filter("{a}age", ">=", 18)
    assert c.filter_sql(f, "t") == "t.age >= 18"
    assert c.filter_sql(f, "") == "age >= 18"


def test_sql_lit_escapes_quotes_and_types():
    assert c.sql_lit("O'Brien") == "'O''Brien'"
    assert c.sql_lit(5) == "5" and c.sql_lit(True) == "true"


def test_filter_sql_rejects_bad_operator():
    with pytest.raises(ValueError):
        c.filter_sql(c.Filter("{a}age", "DROP", 1), "t")


def test_filters_predicate_ands():
    fs = [c.Filter("{a}age", ">=", 18), c.Filter("{a}sex", "=", "F")]
    assert c.filters_predicate(fs, "t") == "(t.age >= 18) AND (t.sex = 'F')"
    assert c.filters_predicate([], "t") == ""


def test_filter_roundtrip_dict():
    f = c.Filter("{a}region", "in", ["MA", "NY"], "region in [MA, NY]", ["region"])
    f2 = c.Filter.from_dict(f.to_dict())
    assert c.filter_sql(f2, "t") == "t.region IN ('MA', 'NY')"
