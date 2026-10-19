"""Unit tests for the Phase-4 document de-id pure helpers (scripts/deid_docs.py).

Offline: the regex layer, the member-name redaction, the residual scan, and the SQL builders are
pure. The live parse / chunked-ai_mask / crosswalk pipeline needs a warehouse and is covered in
the expensive tier.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def dd():
    sys.path.insert(0, str(_SCRIPTS))
    try:
        return _load("deid_docs")
    except ModuleNotFoundError as e:
        pytest.skip(f"deid_docs transitively needs {e.name}; covered in the expensive tier")


_DOC = ("PATIENT RECORD (synthetic) - rec1\nSSN: 123-45-6789\n"
        "MRN: MRN448201\nContact: (617) 555-2830  patient1@example-synthetic.org\n"
        "Visit summary: routine follow-up.")

_RICH = ("Attending Dr. Jane Smith, NPI: 1234567893, DEA# AK-5824791\n"
         "SSN 123-45-6789; shown ***-**-7935; card ending in 4821; MRN-2024-00847291; ACCT-CVH-9938471\n"
         "Call 555-234-5678 or 555.345.6789; portal https://mychart.example.org/rj\n"
         "IP 172.16.254.89; seen 03/14/2025 and 2025-03-20")


# --- regex layer -------------------------------------------------------------

def test_detect_phi_spans_value_classes(dd):
    classes = {c for c, _v in dd.detect_phi_spans(_DOC)}
    assert classes == {"ssn", "mrn", "email", "phone"}       # no 'name' spec anymore


def test_redact_text_masks_value_classes_and_no_residual(dd):
    red, counts = dd.redact_text(_DOC)
    assert "123-45-6789" not in red and "MRN448201" not in red
    assert "patient1@example-synthetic.org" not in red
    assert "[SSN]" in red and "[MRN]" in red and "[EMAIL]" in red and "[PHONE]" in red
    assert set(counts) >= {"ssn", "mrn", "email", "phone"}
    assert dd.residual_phi(red) == []


def test_new_regex_classes_including_dea_dash_and_masked_ssn(dd):
    classes = {c for c, _v in dd.detect_phi_spans(_RICH)}
    assert {"ssn_masked", "ssn_partial", "dea", "labeled_id", "phone_dash", "phone_dot",
            "url", "ip", "date", "date_iso"} <= classes
    red, _ = dd.redact_text(_RICH)
    for raw in ("AK-5824791", "***-**-7935", "ending in 4821", "123-45-6789", "MRN-2024-00847291",
                "ACCT-CVH-9938471", "555-234-5678", "555.345.6789",
                "https://mychart.example.org/rj", "172.16.254.89", "03/14/2025", "2025-03-20"):
        assert raw not in red, f"{raw!r} survived redaction"
    assert dd.residual_phi(red) == []


def test_residual_phi_flags_incomplete_redaction(dd):
    hits = dd.residual_phi(_DOC)       # raw doc still has the raw values
    assert "ssn" in hits and "mrn" in hits and "email" in hits and "phone" in hits


# --- member-name layer (patient redacted, providers kept) --------------------

def test_member_name_tokens(dd):
    assert dd.member_name_tokens("Margaret Eleanor Whitfield") == ["Margaret", "Eleanor", "Whitfield"]
    assert dd.member_name_tokens("") == []


def test_redact_member_removes_patient_keeps_providers(dd):
    member = "Margaret Eleanor Whitfield"
    text = ("Margaret Whitfield seen by Dr. Krishnamurthy and Dr. Okonkwo; "
            "husband Robert Whitfield; daughter Sarah Whitfield-Chen.")
    red = dd.redact_member(text, member)
    assert "Margaret" not in red and "Whitfield" not in red     # patient + shared surname gone
    assert "Krishnamurthy" in red and "Okonkwo" in red          # providers kept
    assert "Robert" in red and "Sarah" in red                   # relatives' bare first names remain


def test_redact_member_noop_without_member(dd):
    assert dd.redact_member("some text", "") == "some text"


# --- SQL builders ------------------------------------------------------------

def test_redaction_sql_uses_same_patterns(dd):
    sql = dd.redaction_sql("text")
    assert sql.count("regexp_replace(") == len(dd.PHI_SPECS)
    assert "text" in sql and "[SSN]" in sql and "[MRN]" in sql


def test_member_redaction_sql_is_guarded(dd):
    s = dd._member_redaction_sql("masked", "member")
    assert "CASE WHEN" in s and "member <> ''" in s and "[NAME]" in s


def test_ai_mask_labels_within_cap_and_no_person_name(dd):
    assert len(dd.AI_MASK_LABELS) <= 20
    assert "person name" not in dd.AI_MASK_LABELS      # providers must not be masked


def test_chunked_cte_shapes(dd):
    on = dd._chunked_mask_cte("staged", True)
    off = dd._chunked_mask_cte("staged", False)
    assert "ai_mask(" in on and "posexplode(" in on and "array_sort(" in on
    assert "ai_mask(" not in off and "text AS masked" in off


def test_apply_document_deid_confirm_gate(dd, monkeypatch):
    """Unless confirmed=True, apply_document_deid must BUILD NOTHING and return the preview + STOP."""
    calls = {"preview": 0}

    def fake_preview(*a, **k):
        calls["preview"] += 1
        return "## (stubbed read-only preview)"

    monkeypatch.setattr(dd, "preview_document_deid_options", fake_preview)
    out = dd.apply_document_deid("/Volumes/c/s/docs/*.pdf", "c", "s")   # confirmed defaults False
    assert calls["preview"] == 1
    assert "STOP" in out and "confirmed=True" in out


# ============================================================================
# Edge-case coverage: regex precision, member extraction formats, known gaps.
# ============================================================================

import pytest as _pytest


@_pytest.mark.parametrize("text,expect_class", [
    ("SSN: 123-45-6789", "ssn"),
    ("SSN shown as ***-**-7935", "ssn_masked"),
    ("account ending in 4821", "ssn_partial"),
    ("MRN12345", "mrn"),
    ("MRN-2024-00847291", "mrn"),
    ("mrn: 99812", "mrn"),
    ("DEA# AB1234563", "dea"),
    ("DEA: AK-5824791", "dea"),
    ("Policy # BCBS-4455", "labeled_id"),
    ("Group number 445566", "labeled_id"),
    ("Medicare ID 1EG4TE5MK73", "labeled_id"),
    ("ACCT-CVH-9938471", "labeled_id"),
    ("Reach me at (617) 555-2830", "phone"),
    ("call 555-234-5678", "phone_dash"),
    ("fax 555.345.6789", "phone_dot"),
    ("a@b.co", "email"),
    ("see https://x.org/p", "url"),
    ("from 10.0.0.1", "ip"),
    ("on 03/14/2025", "date"),
    ("on 2025-03-20", "date_iso"),
])
def test_each_class_matches(dd, text, expect_class):
    assert expect_class in {c for c, _v in dd.detect_phi_spans(text)}


@_pytest.mark.parametrize("prose", [
    "The account balance was reviewed.",
    "The care group met on the ward.",
    "Member of the care team signed off.",
    "Policy regarding visitors is posted.",
    "Routine follow-up; no acute distress.",
])
def test_labeled_id_does_not_over_redact_prose(dd, prose):
    # no digit in the value -> must NOT be flagged as an ID (precision guard)
    assert "labeled_id" not in {c for c, _v in dd.detect_phi_spans(prose)}
    red, _ = dd.redact_text(prose)
    assert "[ID]" not in red


@_pytest.mark.parametrize("text", [
    "bare 123456789 nine digits",          # SSN without dashes — known gap (not matched)
    "intl +1 555 123 4567",                # international phone — known gap
])
def test_known_gaps_not_matched(dd, text):
    classes = {c for c, _v in dd.detect_phi_spans(text)}
    assert "ssn" not in classes and "phone" not in classes and "phone_dash" not in classes


def test_mrn_dash_not_split_as_date(dd):
    red, _ = dd.redact_text("MRN-2024-00847291 recorded")
    assert "[MRN]" in red and "2024-00" not in red          # consumed as MRN, not a date


def test_ssn_not_mistaken_for_phone(dd):
    spans = dict(dd.detect_phi_spans("SSN 123-45-6789"))
    assert "ssn" in spans.values() or ("ssn", "123-45-6789") in dd.detect_phi_spans("SSN 123-45-6789")


def test_empty_and_none_text(dd):
    assert dd.detect_phi_spans("") == [] and dd.detect_phi_spans(None) == []
    assert dd.redact_text("")[0] == "" and dd.residual_phi("") == []
    assert dd.redact_member(None, "Jane Doe") == ""


def test_no_phi_text_unchanged(dd):
    clean = "Patient tolerated the procedure well and was discharged in stable condition."
    red, counts = dd.redact_text(clean)
    assert red == clean and counts == {}


@_pytest.mark.parametrize("text,expected", [
    ("Patient Name: John Doe", "John Doe"),
    ("Patient Name:</td><td>Margaret Eleanor Whitfield</td>", "Margaret Eleanor Whitfield"),
    ("Member Name: Jane A. Smith\n", "Jane A. Smith"),
    ("SUBSCRIBER NAME: Robert Lee", "Robert Lee"),
    ("Insured Name:  Maria Garcia  ", "Maria Garcia"),
    ("No member field here", ""),
    ("Patient Name: Patrick O'Brien", "Patrick O'Brien"),
])
def test_extract_member_name_formats(dd, text, expected):
    assert dd.extract_member_name(text) == expected


def test_sql_member_regex_derived_from_python(dd):
    # single source of truth: SQL form is the python pattern with backslashes/quotes escaped
    assert dd.MEMBER_NAME_RE == dd._MEMBER_PATTERN.replace("\\", "\\\\").replace("'", "''")


def test_member_redaction_removes_all_occurrences(dd):
    member = dd.extract_member_name("Patient Name: Margaret Whitfield")
    text = "Margaret Whitfield (MARGARET) and Ms. Whitfield were seen; Dr. Whitfield-Jones consulted."
    red = dd.redact_member(text, member)
    assert "Margaret" not in red and "MARGARET" not in red     # case-insensitive, all occurrences
    # NOTE: a provider sharing the member surname is also redacted (acceptable, recall-favoring)
    assert red.count("[NAME]") >= 3


def test_full_regex_plus_member_layer_residual_clean(dd):
    member = "Margaret Whitfield"
    text = ("Patient Margaret Whitfield, SSN 123-45-6789, MRN-2024-0088, DEA: AK-5824791, "
            "phone 555-234-5678, portal https://x.org/a, seen 03/14/2025.")
    red, _ = dd.redact_text(dd.redact_member(text, member))
    assert dd.residual_phi(red) == []
    assert "Whitfield" not in red and "AK-5824791" not in red


# --- shipped quick-wins: multi-word/abbrev IDs + relative-name redaction -----

@_pytest.mark.parametrize("text,gone", [
    ("EMS run number 44821", "44821"),
    ("Prescription ID 887241", "887241"),
    ("Radiology accession number RAD-2026-VT-091244829", "RAD-2026-VT-091244829"),
    ("Lab Specimen ID: SP-2026-00123", "SP-2026-00123"),
    ("Group GRP-2241-05 state VT", "GRP-2241-05"),
    ("Insurance group number 445566", "445566"),
])
def test_multiword_and_abbrev_ids_redacted(dd, text, gone):
    red, _ = dd.redact_text(text)
    assert gone not in red and "[ID]" in red


@_pytest.mark.parametrize("prose", [
    "Lab results were within normal limits.",      # 'lab' is NOT a trigger keyword
    "The care group of patients met.",
    "Prescription for metformin was continued.",   # 'prescription' + no digit value
])
def test_quickwin_keywords_do_not_eat_clinical_prose(dd, prose):
    red, _ = dd.redact_text(prose)
    assert "[ID]" not in red


def test_redact_relatives_keeps_cue_and_providers(dd):
    text = ("Husband Robert; daughter Sarah Whitfield-Chen; granddaughter Mia. "
            "Mother was admitted last year. Seen by Dr. Krishnamurthy.")
    red = dd.redact_relatives(text)
    assert "Husband [NAME]" in red and "daughter [NAME]" in red and "granddaughter [NAME]" in red
    assert "Robert" not in red and "Sarah" not in red and "Mia" not in red
    assert "Mother was admitted" in red          # lowercase after cue -> untouched
    assert "Krishnamurthy" in red                # provider kept


def test_relative_sql_derived_from_python(dd):
    assert dd._RELATIVE_SQL == dd._RELATIVE_PATTERN.replace("\\", "\\\\").replace("'", "''")
    assert "$1$2[NAME]" in dd._relative_redaction_sql("col")


# --- rec 1-2: dict ID, employer, multi-field member (misspelled surname) --------

def test_dictation_id_now_redacted(dd):
    red, _ = dd.redact_text("Dictation ID:</td><td>DICT-20260912-08421")
    assert "DICT-20260912-08421" not in red and "20260912" not in red and "[ID]" in red


def test_extract_employer(dd):
    assert dd.extract_employer(
        "Employer:</td><td>Vermont Department of Education (Retired 2023)</td>"
    ) == "Vermont Department of Education"
    assert dd.extract_employer("no employer field") == ""


def test_redact_employer_phrase_keeps_clinical(dd):
    text = "Works at Vermont Department of Education. Seen in the Emergency Department today."
    red = dd.redact_employer(text, "Vermont Department of Education")
    assert "Vermont Department of Education" not in red and "[EMPLOYER]" in red
    assert "Emergency Department" in red          # generic 'Department' not over-redacted


def test_multifield_member_unions_misspelled_surname(dd):
    text = ("Patient Name:</td><td>Margaret E. Whitfield</td>\n"
            "...\nPatient:</td><td>Whittfield, Margaret E. DOB: 03/14/1958</td>")
    member = dd.extract_member_name(text)
    toks = {t.lower() for t in dd.member_name_tokens(member)}
    assert "whitfield" in toks and "whittfield" in toks       # BOTH spellings captured
    red = dd.redact_member(text, member)
    assert "Whitfield" not in red and "Whittfield" not in red


def test_bare_patient_colon_requires_table_cell(dd):
    # prose "Patient: ..." without a table cell must NOT be mistaken for a name field
    assert dd.extract_member_name("Patient: reports feeling well today") == ""


def test_sql_forms_derived_from_python(dd):
    assert dd.MEMBER_NAME_RE == dd._MEMBER_PATTERN.replace("\\", "\\\\").replace("'", "''")
    assert dd.EMPLOYER_RE == dd._EMPLOYER_PATTERN.replace("\\", "\\\\").replace("'", "''")


# --- rec 2: shared-surname family redaction (relatives' first names) ------------

def test_redact_family_shared_surname(dd):
    member = "Margaret E. Whitfield Whittfield"     # face sheet + misspelled imaging field
    text = ("Husband Robert James Whitfield; son Thomas Whitfield; daughter Sarah Whitfield-Chen. "
            "Seen by Dr. Krishnamurthy. Emergency contact Robert Whitfield.")
    red = dd.redact_family(text, member)
    assert "Robert" not in red and "Thomas" not in red and "James" not in red
    assert "Krishnamurthy" in red                    # provider (no member surname) kept
    assert "Chen" in red                             # only the shared-surname part is anchored


def test_redact_family_noop_without_member(dd):
    assert dd.redact_family("Robert Jones here", "") == "Robert Jones here"


def test_redact_family_lowercase_prose_untouched(dd):
    # no capitalized name before the surname -> nothing to redact here
    member = "Margaret Whitfield"
    assert dd.redact_family("the whitfield building", member) == "the whitfield building"
