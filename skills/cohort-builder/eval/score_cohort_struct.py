"""Score a Genie cohort-builder STRUCTURED run against owned gold.

Cohort = uncontrolled type 2 diabetes: T2D dx (E11.9 OR E11.65) AND hba1c_value > 8.0,
over multi_condition_patients. Gold is exact (SQL over the seeded table). Measures
membership P/R/F1 (headline), concept-set expansion (did it capture E11.65-only members,
not just E11.9), feasibility calibration, and the skill's objective.

Usage:
  DATABRICKS_CONFIG_PROFILE=fevm-testing-playground python3 -I score_cohort_struct.py \
     --base testing_playground_catalog.genie_science_eval.multi_condition_patients \
     --out  testing_playground_catalog.genie_science_eval.cohort_struct_skillrun1
"""
from __future__ import annotations
import argparse, importlib.util, os, sys, time
from pathlib import Path
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

_EVAL = Path(__file__).resolve().parent
PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE", "fevm-testing-playground")
REF_CODES = {("ICD10CM", "E11.9"), ("ICD10CM", "E11.65")}
GOLD_PRED = "condition_code IN ('E11.9','E11.65') AND hba1c_value > 8.0"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); return m


class Q:
    def __init__(self):
        self.w = WorkspaceClient(profile=PROFILE)
        self.wid = next(wh.id for wh in self.w.warehouses.list())
    def __call__(self, stmt):
        r = self.w.statement_execution.execute_statement(warehouse_id=self.wid, statement=stmt, wait_timeout="50s")
        while r.status and r.status.state in (StatementState.PENDING, StatementState.RUNNING):
            time.sleep(2); r = self.w.statement_execution.get_statement(r.statement_id)
        if r.status and r.status.state != StatementState.SUCCEEDED:
            raise RuntimeError(f"{r.status.error} :: {stmt[:160]}")
        return r.result.data_array if r.result else []


def _cols(q, fqn):
    cat, sch, tbl = fqn.split(".")
    return [c[0] for c in q(f"SELECT column_name FROM {cat}.information_schema.columns "
                            f"WHERE table_schema='{sch}' AND table_name='{tbl}' ORDER BY ordinal_position")]


def _exists(q, fqn):
    cat, sch, tbl = fqn.split(".")
    return bool(q(f"SELECT 1 FROM {cat}.information_schema.tables WHERE table_schema='{sch}' AND table_name='{tbl}'"))


def score(base_fqn: str, out_fqn: str, label: str = "") -> dict:
    sc = _load("cohort_scorers", _EVAL / "scorers.py")
    obj = _load("cohort_obj", _EVAL / "objective.py")
    q = Q()

    all_p = {r[0] for r in q(f"SELECT DISTINCT patient_id FROM {base_fqn}")}
    gold_members = {r[0] for r in q(f"SELECT DISTINCT patient_id FROM {base_fqn} WHERE {GOLD_PRED}")}
    e1165_only = {r[0] for r in q(f"SELECT DISTINCT patient_id FROM {base_fqn} WHERE condition_code='E11.65' AND hba1c_value>8.0")} - \
                 {r[0] for r in q(f"SELECT DISTINCT patient_id FROM {base_fqn} WHERE condition_code='E11.9' AND hba1c_value>8.0")}

    out_cols = _cols(q, out_fqn)
    pid = "patient_id" if "patient_id" in out_cols else next((c for c in out_cols if "patient" in c.lower() and "id" in c.lower()), out_cols[0])
    predicted = {r[0] for r in q(f"SELECT DISTINCT `{pid}` FROM {out_fqn}")}

    # resolved codes: prefer a provenance/code column; else infer from captured E11.65-only members
    resolved = set()
    code_src = None
    for cand in (out_fqn, out_fqn + "_provenance", out_fqn.rsplit(".", 1)[0] + "." + out_fqn.split(".")[-1] + "_provenance"):
        if _exists(q, cand):
            ccols = _cols(q, cand)
            codecol = next((c for c in ccols if c.lower() in ("condition_code", "code", "icd10", "diagnosis_code", "dx_code")), None)
            if codecol:
                resolved = {("ICD10CM", r[0]) for r in q(f"SELECT DISTINCT `{codecol}` FROM {cand} WHERE `{codecol}` IS NOT NULL")}
                code_src = f"{cand}.{codecol}"; break
    inferred = False
    if not resolved:
        inferred = True
        resolved = {("ICD10CM", "E11.9")}
        if predicted & e1165_only:
            resolved.add(("ICD10CM", "E11.65"))

    gold = sc.CohortGold(true_members=gold_members, all_patients=all_p, reference_codes=REF_CODES,
                         actual_feasible_n=len(gold_members), should_build=True)
    out = sc.CohortOutput(predicted_members=predicted, resolved_codes=resolved,
                          predicted_n=len(predicted), decided_to_build=True, citations=[])
    res = obj.cohort_objective(gold, out)
    b = res.breakdown
    m = b["membership"]
    e1165_captured = len(predicted & e1165_only)

    print(f"\n=== {label or out_fqn} ===")
    print(f"  cohort table col : patient_id='{pid}', {len(out_cols)} cols")
    print(f"  gold N           : {len(gold_members)}   predicted N: {len(predicted)}")
    print(f"  membership       : P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f}  (tp={m['tp']} fp={m['fp']} fn={m['fn']})")
    print(f"  concept expansion: E11.65-only members captured {e1165_captured}/{len(e1165_only)}  "
          f"(naive E11.9-only would miss these)")
    print(f"  resolved codes   : {sorted(resolved)}  {'(inferred)' if inferred else '(from '+str(code_src)+')'}")
    print(f"  conceptset F1    : {b['conceptset_f1']:.3f}")
    print(f"  feasibility cal  : {b['feasibility_calibration']:.3f}")
    print(f"  OBJECTIVE SCORE  : {res.score}")
    return {"label": label or out_fqn.split('.')[-1], "gold_n": len(gold_members), "pred_n": len(predicted),
            "precision": m["precision"], "recall": m["recall"], "f1": m["f1"],
            "e1165_captured": e1165_captured, "e1165_total": len(e1165_only),
            "conceptset_f1": b["conceptset_f1"], "feasibility": b["feasibility_calibration"], "score": res.score}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    score(a.base, a.out, a.label)
