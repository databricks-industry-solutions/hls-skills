"""Score a Genie cohort-builder FREE-TEXT NOTES run (ai_query path) against owned gold.

Task: from clinical_docs_parsed (patient_id, note_text), include patients whose note
asserts their OWN current Type 2 diabetes; exclude family-history and ruled-out/negated
mentions. Gold comes from the seeded note archetypes in clinical_docs_gold:
  assert   -> true current-dx members (INCLUDE)
  family   -> family-history traps     (EXCLUDE)
  ruledout -> negation traps           (EXCLUDE)
A naive LIKE '%diabet%' matches all three -> leaks every trap. The skill's negation-/
subject-aware ai_query should include asserts and exclude traps.

Usage:
  DATABRICKS_CONFIG_PROFILE=fevm-testing-playground python3 -I score_cohort_notes.py \
     --out testing_playground_catalog.genie_science_eval.cohort_notes_skillrun1
"""
from __future__ import annotations
import argparse, importlib.util, os, sys, time
from pathlib import Path
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

_EVAL = Path(__file__).resolve().parent
PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE", "fevm-testing-playground")
C = "testing_playground_catalog.genie_science_eval"
GOLD = f"{C}.clinical_docs_gold"
PARSED = f"{C}.clinical_docs_parsed"


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


def score(out_fqn: str, label: str = "") -> dict:
    sc = _load("cohort_scorers", _EVAL / "scorers.py")
    obj = _load("cohort_obj", _EVAL / "objective.py")
    q = Q()

    asserts = {r[0] for r in q(f"SELECT DISTINCT patient_id FROM {GOLD} WHERE archetype='assert'")}
    family = {r[0] for r in q(f"SELECT DISTINCT patient_id FROM {GOLD} WHERE archetype='family'")}
    ruledout = {r[0] for r in q(f"SELECT DISTINCT patient_id FROM {GOLD} WHERE archetype='ruledout'")}
    traps = family | ruledout
    allp = {r[0] for r in q(f"SELECT DISTINCT patient_id FROM {PARSED}")}
    naive = {r[0] for r in q(f"SELECT DISTINCT patient_id FROM {PARSED} WHERE lower(note_text) LIKE '%diab%' OR lower(note_text) LIKE '%t2dm%'")}

    out_cat, out_sch, out_tbl = out_fqn.split(".")
    out_cols = [c[0] for c in q(f"SELECT column_name FROM {out_cat}.information_schema.columns "
                                f"WHERE table_schema='{out_sch}' AND table_name='{out_tbl}'")]
    pid = "patient_id" if "patient_id" in out_cols else next((c for c in out_cols if "patient" in c.lower()), out_cols[0])
    predicted = {r[0] for r in q(f"SELECT DISTINCT `{pid}` FROM {out_fqn}")}

    gold = sc.CohortGold(
        true_members=asserts, all_patients=allp, reference_codes=set(), actual_feasible_n=len(asserts),
        should_build=True, note_true_members=asserts, union_true_members=asserts,
        negation_traps=ruledout, family_history_traps=family, naive_keyword_members=naive)
    out = sc.CohortOutput(predicted_members=predicted, resolved_codes=set(), predicted_n=len(predicted),
                          decided_to_build=True, citations=[])

    mem = sc.membership_f1(gold, out)
    spec = sc.note_trap_specificity(gold, out)
    res = obj.cohort_objective(gold, out)

    # naive baseline membership (what LIKE would score) for the A/B contrast
    naive_out = sc.CohortOutput(predicted_members=(naive & (asserts | traps)))
    naive_mem = sc.membership_f1(gold, naive_out)
    naive_spec = sc.note_trap_specificity(gold, sc.CohortOutput(predicted_members=naive))

    print(f"\n=== {label or out_fqn} ===")
    print(f"  gold assert(true)={len(asserts)}  traps(family {len(family)}+ruledout {len(ruledout)})={len(traps)}  parsed_pop={len(allp)}")
    print(f"  predicted N      : {len(predicted)}")
    print(f"  membership       : P={mem['precision']:.3f} R={mem['recall']:.3f} F1={mem['f1']:.3f}  (tp={mem['tp']} fp={mem['fp']} fn={mem['fn']})")
    print(f"  trap specificity : {spec['specificity']:.3f}  (leaked {len(spec['leaked'])}/{spec['n_traps']} traps: {spec['leaked'][:8]})")
    print(f"  OBJECTIVE SCORE  : {res.score}")
    print(f"  -- naive LIKE baseline: P={naive_mem['precision']:.3f} R={naive_mem['recall']:.3f} F1={naive_mem['f1']:.3f}, "
          f"trap_specificity={naive_spec['specificity']:.3f} (leaks {naive_spec['n_traps']-len(naive_spec['leaked'])==0 and 'all' or len(naive_spec['leaked'])} traps)")
    return {"label": label or out_tbl, "true_n": len(asserts), "trap_n": len(traps), "pred_n": len(predicted),
            "precision": mem["precision"], "recall": mem["recall"], "f1": mem["f1"],
            "trap_specificity": spec["specificity"], "trap_leaked": len(spec["leaked"]),
            "score": res.score, "naive_f1": naive_mem["f1"], "naive_spec": naive_spec["specificity"]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    score(a.out, a.label)
