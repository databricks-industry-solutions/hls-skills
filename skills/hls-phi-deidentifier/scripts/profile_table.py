"""Profile any table's columns to seed PHI detection.

For each column: type, null rate, distinct count, and a small sample of distinct
non-null values (used by the value validators in detect_phi). Runs one aggregate
pass plus a per-column sample.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ColumnProfile:
    column: str
    data_type: str
    null_rate: float = 0.0
    distinct_count: int = 0
    sample_values: list = field(default_factory=list)   # distinct non-null samples


def profile_table(q, table: str, sample_size: int = 20) -> list[ColumnProfile]:
    """Return a per-column profile for `table`. `q` is a SQL runner (see apply_uc_governance.Q)."""
    desc = [r for r in q(f"DESCRIBE {table}") if r[0] and not r[0].startswith("#")]
    columns = [(r[0], r[1]) for r in desc]
    total = int(q(f"SELECT COUNT(*) FROM {table}")[0][0]) or 1

    profiles = []
    for name, dtype in columns:
        agg = q(f"SELECT COUNT(*) - COUNT(`{name}`), COUNT(DISTINCT `{name}`) FROM {table}")
        nulls = int(agg[0][0]) if agg and agg[0][0] is not None else 0
        distinct = int(agg[0][1]) if agg and agg[0][1] is not None else 0
        samples = [r[0] for r in q(
            f"SELECT DISTINCT `{name}` FROM {table} WHERE `{name}` IS NOT NULL LIMIT {sample_size}")]
        profiles.append(ColumnProfile(column=name, data_type=dtype,
                                      null_rate=nulls / total, distinct_count=distinct,
                                      sample_values=[str(s) for s in samples]))
    return profiles
