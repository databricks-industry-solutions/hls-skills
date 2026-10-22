"""Score a Genie phi-deidentifier STRUCTURED run against an owned raw table.

Unlike score_deid_table.py (written for an older output schema), this understands the
current skill output: pseudo_<id>, <qi>_generalized, los_generalized, year columns, and
analytic passthrough. It measures k over the generalized QIs, confirms the output is a
governed VIEW (no 2nd PHI copy), scans residual leaks against the ACTUAL input, and feeds
the skill's own objective.py.

Usage:
  DATABRICKS_CONFIG_PROFILE=fevm-testing-playground python3 -I score_phi_struct.py \
     --raw testing_playground_catalog.deid_live_test.patients_raw \
     --out testing_playground_catalog.genie_science_eval.phi_struct_skillrun1
"""
from __future__ import annotations
import argparse, importlib.util, os, sys, time
from pathlib import Path
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

_EVAL = Path(__file__).resolve().parent
PROFILE = os.environ.get("DATABRICKS_CONFIG_PROFILE", "fevm-testing-playground")

DIRECT_IDS = ["patient_name", "ssn", "email", "phone"]          # must be gone/tokenized
QIS = ["zip", "admit_date", "discharge_date", "age_band", "sex"]  # must be generalized
ANALYTIC = ["hba1c", "age_band", "sex", "zip"]                  # should survive (full or generalized)
LEAK_CLASSES = ["ssn", "email", "phone", "patient_name"]


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


def score(raw_fqn: str, out_fqn: str, label: str = "") -> dict:
    sc = _load("deid_scorers", _EVAL / "scorers.py")
    obj = _load("deid_obj", _EVAL / "objective.py")
    q = Q()
    out_sch, out_tbl = out_fqn.split(".")[1], out_fqn.split(".")[2]

    out_cols = [c[0] for c in q(f"SELECT column_name FROM {out_fqn.split('.')[0]}.information_schema.columns "
                                f"WHERE table_schema='{out_sch}' AND table_name='{out_tbl}' ORDER BY ordinal_position")]
    ttype = q(f"SELECT table_type FROM {out_fqn.split('.')[0]}.information_schema.tables "
              f"WHERE table_schema='{out_sch}' AND table_name='{out_tbl}'")
    is_view = bool(ttype) and ttype[0][0] == "VIEW"
    nrows = int(q(f"SELECT COUNT(*) FROM {out_fqn}")[0][0])

    gen_cols = [c for c in out_cols if c.endswith("_generalized") or c.endswith("_year")]
    has_pseudo = any(c.startswith("pseudo_") for c in out_cols)
    has_los = any("los" in c for c in out_cols)
    direct_present = [c for c in DIRECT_IDS if c in out_cols]  # verbatim direct id survived == bad

    # --- residual leak scan against the ACTUAL input ---
    blob = "CONCAT_WS('|', " + ", ".join(f"CAST(`{c}` AS STRING)" for c in out_cols) + ")"
    leaks = 0
    leak_detail = {}
    for cls in LEAK_CLASSES:
        n = int(q(f"SELECT COUNT(*) FROM (SELECT DISTINCT `{cls}` v FROM {raw_fqn} WHERE `{cls}` IS NOT NULL) r "
                  f"WHERE EXISTS (SELECT 1 FROM {out_fqn} o WHERE {blob} LIKE CONCAT('%', r.v, '%'))")[0][0])
        leak_detail[cls] = n; leaks += n

    # --- k-anonymity over generalized QIs ---
    if gen_cols:
        grp = ", ".join(f"`{c}`" for c in gen_cols)
        k = int(q(f"SELECT MIN(cnt) FROM (SELECT COUNT(*) cnt FROM {out_fqn} GROUP BY {grp})")[0][0])
    else:
        k = 0

    # --- build gold + output contracts ---
    raw_n = int(q(f"SELECT COUNT(*) FROM {raw_fqn}")[0][0])
    injected = [sc.PhiSpan(f"r{i}", c, "id", "") for i in range(raw_n) for c in (DIRECT_IDS + QIS)]
    # a PHI column is 'transformed' if it is NOT present verbatim in the output
    transformed = {(f"r{i}", c) for i in range(raw_n) for c in (DIRECT_IDS + QIS) if c not in out_cols}
    residual = {("leak", f"{cls}{j}") for cls, n in leak_detail.items() for j in range(n)}

    # analytic fidelity: hba1c full if present verbatim; QIs generalized if present as *_generalized
    fidelity, surviving = {}, []
    for c in ANALYTIC:
        if c in out_cols:
            fidelity[c] = "full"; surviving.append(c)
        elif f"{c}_generalized" in out_cols:
            fidelity[c] = "generalized"; surviving.append(c)

    gold = sc.DeidGold(injected=injected, analytic_columns=ANALYTIC,
                       intervals=[(f"p{i}", "admit_date", "discharge_date", 1) for i in range(raw_n)])
    out = sc.DeidOutput(
        transformed_cells=transformed, residual_phi_cells=residual,
        surviving_analytic_columns=surviving, analytic_fidelity=fidelity,
        preserved_intervals=[], interval_generalized=has_los, k_anonymity=k,
        is_view_over_raw=is_view, raw_phi_still_exposed=(not is_view) or bool(direct_present))
    res = obj.deid_objective(gold, out)
    b = res.breakdown

    print(f"\n=== {label or out_fqn} ===")
    print(f"  output: {'VIEW' if is_view else 'TABLE'}, {nrows} rows, cols={out_cols}")
    print(f"  residual leaks     : {leaks}  detail={leak_detail}  {'<-- GATE=0' if leaks else ''}")
    print(f"  detection recall   : {b['recall']:.3f}   precision: {b['precision']:.3f}   F2: {b['f2']:.3f}")
    print(f"  direct-id verbatim : {direct_present or 'none'}")
    print(f"  tokenized id       : {has_pseudo}")
    print(f"  utility retention  : {b['utility_retention']:.3f}  (fidelity={fidelity}, interval_generalized={has_los})")
    print(f"  k-anonymity        : {k}  over {gen_cols}   (k_term={b['k_term']:.2f})")
    print(f"  governance         : {b['governance']:.2f}  (view_over_raw={is_view}, raw_exposed={(not is_view) or bool(direct_present)})")
    print(f"  OBJECTIVE SCORE    : {res.score}   leaked={res.leaked}")
    return {"label": label or out_tbl, "leaks": leaks, "recall": b["recall"], "precision": b["precision"],
            "f2": b["f2"], "utility": b["utility_retention"], "k": k, "governance": b["governance"],
            "score": res.score, "is_view": is_view, "tokenized": has_pseudo, "nrows": nrows}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    score(a.raw, a.out, a.label)
