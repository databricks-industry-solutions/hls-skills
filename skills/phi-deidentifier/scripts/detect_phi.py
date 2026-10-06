"""Classify columns of a structured table into HIPAA Safe Harbor identifier classes.

Detection order (highest trust first):
    1. Unity Catalog PII tags / classifiers already on the column.
    2. Column-name heuristics (ssn, mrn, dob, zip, phone, email, ...).
    3. Value validators (deterministic regex + checksums) -- authoritative over names.
    4. ai_classify as a tie-breaker only, for ambiguous columns.

Detection is recall-dominated: when uncertain, mark PHI rather than pass through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Safe Harbor class identifiers used across the skill. See references/safe_harbor_classes.md.
SAFE_HARBOR_CLASSES = (
    "name", "geo_sub_state", "date_element", "phone", "fax", "email", "ssn",
    "mrn", "health_plan_number", "account_number", "certificate_license",
    "vehicle_id", "device_id", "url", "ip_address", "biometric", "photo",
    "other_unique_id", "age_over_89", "not_phi",
)


@dataclass
class ColumnClassification:
    column: str
    detected_class: str
    method: str          # "uc_tag" | "name_heuristic" | "validator" | "ai_classify"
    confidence: float    # 0.0-1.0
    proposed_strategy: str
    sample_masked: str   # a masked example value for user confirmation


# --- Deterministic value validators (authoritative) --------------------------

_SSN_RE = re.compile(r"^\d{3}-?\d{2}-?\d{4}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$")
_IP_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")


def _luhn_ok(digits: str) -> bool:
    """Luhn checksum -- used for account/card numbers and (with prefix) NPI."""
    ds = [int(c) for c in digits if c.isdigit()]
    if len(ds) < 2:
        return False
    checksum = 0
    parity = len(ds) % 2
    for i, d in enumerate(ds):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def validate_value(value: str) -> str | None:
    """Return a Safe Harbor class if the value matches a deterministic validator."""
    if value is None:
        return None
    v = value.strip()
    if _SSN_RE.match(v):
        return "ssn"
    if _EMAIL_RE.match(v):
        return "email"
    if _PHONE_RE.match(v):
        return "phone"
    if _IP_RE.match(v):
        return "ip_address"
    if _ZIP_RE.match(v):
        return "geo_sub_state"
    # TODO: NPI (Luhn w/ 80840 prefix), account/card (Luhn), URL, dates, MRN patterns.
    return None


# --- Name heuristics ----------------------------------------------------------

# Name hints as an ORDERED list of (hint, class), highest PRIORITY first. Order matters:
# a column can contain several hint tokens (e.g. `email_address` has both "email" and
# "address"), and we must return the most protective / most specific class. Direct
# identifiers (redacted) are listed before generalizable classes (date, geo) so that, e.g.,
# `email_address` classifies as email (redact) rather than geo (LEFT(,3) — which would EXPOSE
# the first characters of every email). Multi-word hints use "_" and match adjacent tokens.
_NAME_HINTS = [
    # direct identifiers first (redacted) — most protective
    ("ssn", "ssn"), ("social", "ssn"),
    ("email", "email"),
    ("phone", "phone"), ("fax", "fax"),
    ("url", "url"),
    ("first_name", "name"), ("last_name", "name"), ("patient_name", "name"),
    ("full_name", "name"), ("fullname", "name"), ("surname", "name"), ("name", "name"),
    # tokenized identifiers
    ("mrn", "mrn"), ("medical_record", "mrn"),
    ("account", "account_number"), ("member_id", "health_plan_number"),
    ("device", "device_id"), ("ip", "ip_address"),
    # generalizable classes last (least protective) — only chosen if no direct-ID hint matched
    ("dob", "date_element"), ("birth", "date_element"), ("date", "date_element"),
    ("zip", "geo_sub_state"), ("postal", "geo_sub_state"), ("address", "geo_sub_state"),
]

# Identifier-ish column names -> Safe Harbor class 18 ("any other unique identifier").
# Checked only as whole-word / suffix matches so we don't flag e.g. "condition_code".
_ID_SUFFIX_HINTS = ("patient_id", "person_id", "subject_id", "record_id", "encounter_id", "mrn")


def _tokenize(column: str) -> list[str]:
    """Split a column name into lowercase word tokens on non-alphanumeric AND camelCase
    boundaries, so hint matching is by whole word — 'date' matches `admit_date` but NOT
    `candidate_id`/`mandate_amount`, and 'address' is a distinct token from 'email'."""
    import re
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", column)   # camelCase -> camel_Case
    return [t for t in re.split(r"[^a-z0-9]+", spaced.lower()) if t]


def _hint_matches(hint: str, tokens: list[str]) -> bool:
    """True if the hint appears as a whole token, or (for multi-word hints) as an adjacent
    run of tokens. Substring-within-token matches (e.g. 'date' in 'candidate') do NOT count."""
    parts = hint.split("_")
    n = len(parts)
    return any(tokens[i:i + n] == parts for i in range(len(tokens) - n + 1))


def classify_by_name(column: str) -> str | None:
    tokens = _tokenize(column)
    for hint, klass in _NAME_HINTS:      # priority order: first match wins
        if _hint_matches(hint, tokens):
            return klass
    # patient/person identifiers: match the whole name or an _id suffix form,
    # but NOT generic code columns.
    col = column.lower()
    if col in _ID_SUFFIX_HINTS or col.endswith("patient_id") or col.endswith("person_id") \
            or col.endswith("subject_id"):
        return "other_unique_id"
    return None


# --- Classification -> strategy mapping ---------------------------------------

_CLASS_STRATEGY = {
    "name": "redact", "ssn": "redact", "email": "redact", "phone": "redact",
    "fax": "redact", "url": "redact", "ip_address": "redact",
    "mrn": "tokenize", "health_plan_number": "tokenize", "account_number": "tokenize",
    "device_id": "tokenize", "certificate_license": "redact", "vehicle_id": "redact",
    "date_element": "shift_or_generalize", "age_over_89": "generalize_age",
    "geo_sub_state": "generalize_zip", "other_unique_id": "review",
    "not_phi": "keep",
}


def _mask(value: str) -> str:
    """Mask a sample value so raw PHI is never echoed back in the classification table."""
    if value is None:
        return ""
    v = str(value)
    return (v[0] + "*" * (len(v) - 2) + v[-1]) if len(v) > 2 else "**"


def _looks_like_date(samples: list[str]) -> bool:
    hits = 0
    for s in samples:
        s = s.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}", s) or re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", s):
            hits += 1
    return samples and hits / len(samples) >= 0.6


def detect_phi(profiles, uc_tags=None, min_value_agreement: float = 0.5):
    """Classify each column into a Safe Harbor class from its profile.

    Detection order (recall-biased -- when in doubt, flag as PHI):
        1. UC PII tags (highest trust) -- pass uc_tags={column: class}.
        2. Value validators on the sampled values (majority vote) -- authoritative for
           SSN/email/phone/IP/ZIP because format is unambiguous.
        3. Column-name heuristics -- catch name/mrn/dob/account where values are opaque.
        4. Date shape -- flags date columns validators may miss.

    Args:
        profiles: list from profile_table.profile_table.
        uc_tags: optional {column: safe_harbor_class} from Unity Catalog tags.
        min_value_agreement: fraction of sampled values that must validate to the same
            class for the value-validator vote to win.

    Returns:
        list[ColumnClassification]; surface to the user BEFORE transforming.
    """
    uc_tags = uc_tags or {}
    results = []

    for p in profiles:
        detected, method, confidence = None, None, 0.0

        # 1. UC tag
        if p.column in uc_tags:
            detected, method, confidence = uc_tags[p.column], "uc_tag", 0.99

        # 2. Value validators (majority vote over samples)
        if detected is None and p.sample_values:
            votes = {}
            for v in p.sample_values:
                klass = validate_value(v)
                if klass:
                    votes[klass] = votes.get(klass, 0) + 1
            if votes:
                top_class, top_n = max(votes.items(), key=lambda kv: kv[1])
                agreement = top_n / len(p.sample_values)
                if agreement >= min_value_agreement:
                    detected, method, confidence = top_class, "validator", round(agreement, 2)

        # 3. Name heuristic
        if detected is None:
            klass = classify_by_name(p.column)
            if klass:
                detected, method, confidence = klass, "name_heuristic", 0.7

        # 4. Date shape
        if detected is None and _looks_like_date(p.sample_values):
            detected, method, confidence = "date_element", "date_shape", 0.75

        # default: not PHI
        if detected is None:
            detected, method, confidence = "not_phi", "default", 0.5

        results.append(ColumnClassification(
            column=p.column, detected_class=detected, method=method, confidence=confidence,
            proposed_strategy=_CLASS_STRATEGY.get(detected, "review"),
            sample_masked=_mask(p.sample_values[0]) if p.sample_values else "",
        ))
    return results
