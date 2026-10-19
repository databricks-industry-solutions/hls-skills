#!/usr/bin/env python3
"""Generate synthetic X12 837P / 837I files plus a JSON answer key. Standard library only.

All names, IDs and NPIs are fake. The files deliberately include the cases that break naive parsers:
  - a 2000C patient loop followed by a subscriber-only claim (patient fields must not carry over)
  - a 2320/2330 COB loop with a second payer, REF*F8 and NM1*82 (must not overwrite primary values)
  - two transactions in one file, a pipe element separator, no line breaks, CRLF line breaks
  - a truncated file (no SE/GE/IEA) and a file that is not X12 at all

Usage:
    python3 generate_837.py --out /Volumes/<catalog>/<schema>/<volume>/x12/837 [--claims 6] [--seed 7]
Writes *.x12 / *.txt files to --out and the answer key beside it (<out>_answer_key.json), so a
directory read of --out sees only claim files.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

PROFESSIONAL = "005010X222A1"
INSTITUTIONAL = "005010X223A2"

FIRST = ["AVA", "NOAH", "MIA", "LIAM", "ZOE", "ELI", "IVY", "OWEN", "RUBY", "SAM", "NORA", "LEO"]
LAST = ["RIVERA", "CHEN", "PATEL", "OKAFOR", "NGUYEN", "SMITH", "GARCIA", "KIM", "SILVA", "BROWN"]
CPT = [("99213", 125.00), ("99214", 180.00), ("93000", 45.00), ("80053", 38.50), ("71046", 95.00), ("97110", 60.00)]
REV = [("0450", "99284", 850.00), ("0300", "80053", 120.00), ("0320", "71046", 310.00),
       ("0250", None, 75.00), ("0636", "J1100", 42.00)]
DX = ["E119", "I10", "J449", "M545", "N390", "R0789", "E785", "F329", "K219", "Z23"]
DRG = ["470", "291", "392", "871"]
FILING = ["MC", "MA", "CI", "HM"]
PAYERS = [("PAYER ALPHA", "PAY01"), ("PAYER BETA", "PAY02")]


def _amt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


class X12:
    def __init__(self, el="*", comp=":", term="~", newline="\n"):
        self.el, self.comp, self.term, self.newline = el, comp, term, newline
        self.rep = "^" if comp != "^" else "!"

    def seg(self, *parts) -> str:
        parts = [("" if p is None else str(p)) for p in parts]
        while parts and parts[-1] == "":
            parts.pop()
        return self.el.join(parts)

    def c(self, *parts) -> str:
        parts = [("" if p is None else str(p)) for p in parts]
        while parts and parts[-1] == "":
            parts.pop()
        return self.comp.join(parts)

    def isa(self, ctrl: int) -> str:
        f = [
            "ISA", "00", " " * 10, "00", " " * 10, "ZZ", "SUBMITTER01".ljust(15), "ZZ", "RECEIVER01".ljust(15),
            "261019", "1200", self.rep, "00501", f"{ctrl:09d}", "0", "T", self.comp,
        ]
        s = self.el.join(f)
        assert len(s) == 105, len(s)
        return s

    def render(self, segments: list[str]) -> str:
        return "".join(s + self.term + self.newline for s in segments)


class Gen:
    def __init__(self, seed: int):
        self.r = random.Random(seed)
        self.n = 0
        self.key: list[dict] = []

    def _npi(self) -> str:
        return "1" + "".join(self.r.choice("0123456789") for _ in range(9))

    def _dos(self) -> date:
        return date(2026, 9, 1) + timedelta(days=self.r.randrange(30))

    def _person(self) -> tuple[str, str, str, str]:
        dob = date(1950, 1, 1) + timedelta(days=self.r.randrange(25000))
        return self.r.choice(LAST), self.r.choice(FIRST), dob.strftime("%Y%m%d"), self.r.choice("MF")

    def transaction(self, x: X12, st_ctrl: str, kind: str, subscribers: list[dict], file_name: str) -> list[str]:
        version = PROFESSIONAL if kind == "P" else INSTITUTIONAL
        body = [
            x.seg("ST", "837", st_ctrl, version),
            x.seg("BHT", "0019", "00", f"B{st_ctrl}", "20261019", "1200", "CH"),
            x.seg("NM1", "41", "2", "SYNTHETIC CLEARINGHOUSE", "", "", "", "", "46", "SUB01"),
            x.seg("PER", "IC", "EDI DESK", "TE", "5555550100"),
            x.seg("NM1", "40", "2", "SYNTHETIC RECEIVER", "", "", "", "", "46", "RCV01"),
        ]
        hl = 1
        bp_npi, bp_tin = self._npi(), f"9{self.r.randrange(10**7, 10**8)}"
        bp_name = "SYNTH CLINIC GROUP" if kind == "P" else "SYNTH GENERAL HOSPITAL"
        body += [
            x.seg("HL", hl, "", "20", "1"),
            x.seg("PRV", "BI", "PXC", "207Q00000X" if kind == "P" else "282N00000X"),
            x.seg("NM1", "85", "2", bp_name, "", "", "", "", "XX", bp_npi),
            x.seg("N3", "100 MAIN ST"),
            x.seg("N4", "SPRINGFIELD", "WA", "98101"),
            x.seg("REF", "EI", bp_tin),
        ]
        bp_hl = hl
        for sub in subscribers:
            hl += 1
            sub_hl = hl
            last, first, dob, gender = self._person()
            member = f"M{self.r.randrange(10**8, 10**9)}"
            payer_name, payer_id = self.r.choice(PAYERS)
            filing = self.r.choice(FILING)
            has_patient = sub.get("patient", False)
            body += [
                x.seg("HL", sub_hl, bp_hl, "22", "1" if has_patient else "0"),
                x.seg("SBR", "P", "" if has_patient else "18", f"GRP{self.r.randrange(1000, 9999)}",
                      "", "", "", "", "", filing),
                x.seg("NM1", "IL", "1", last, first, "", "", "", "MI", member),
                x.seg("N3", "200 OAK AVE"),
                x.seg("N4", "TACOMA", "WA", "98402"),
                x.seg("DMG", "D8", dob, gender),
                x.seg("NM1", "PR", "2", payer_name, "", "", "", "", "PI", payer_id),
            ]
            pat = None
            if has_patient:
                hl += 1
                plast, pfirst, pdob, pgender = self._person()
                pat = {"last": plast, "dob": pdob, "gender": pgender}
                body += [
                    x.seg("HL", hl, sub_hl, "23", "0"),
                    x.seg("PAT", "19"),
                    x.seg("NM1", "QC", "1", plast, pfirst),
                    x.seg("N3", "200 OAK AVE"),
                    x.seg("N4", "TACOMA", "WA", "98402"),
                    x.seg("DMG", "D8", pdob, pgender),
                ]
            for _ in range(sub.get("claims", 1)):
                body += self.claim(x, kind, sub.get("cob", False), file_name, st_ctrl, {
                    "member_id": member, "payer_id": payer_id, "billing_provider_npi": bp_npi,
                    "billing_provider_tin": bp_tin, "claim_filing_indicator": filing,
                    "patient_is_subscriber": pat is None,
                    "patient_birth_date": (pat or {"dob": dob})["dob"],
                    "patient_gender": (pat or {"gender": gender})["gender"],
                    "subscriber_birth_date": dob,
                })
        body.append(x.seg("SE", len(body) + 1, st_ctrl))
        return body

    def claim(self, x: X12, kind: str, cob: bool, file_name: str, st_ctrl: str, ctx: dict) -> list[str]:
        self.n += 1
        pcn = f"PCN{self.n:06d}"
        dx = self.r.sample(DX, self.r.randint(1, 4))
        n_lines = self.r.randint(1, 4)
        segs, lines = [], []
        dos = self._dos()
        rendering = self._npi()
        prior_auth = f"PA{self.r.randrange(10**6, 10**7)}" if self.r.random() < 0.4 else None
        if kind == "P":
            for i in range(n_lines):
                code, price = self.r.choice(CPT)
                units = self.r.randint(1, 3)
                mod = "25" if code.startswith("992") and self.r.random() < 0.5 else None
                d = dos + timedelta(days=i)
                lines.append({"line_number": i + 1, "procedure_code": code, "revenue_code": None,
                              "modifiers": [mod] if mod else [], "charge": round(price * units, 2), "units": units,
                              "service_date": d.strftime("%Y%m%d"),
                              "diagnosis_pointers": list(range(1, min(len(dx), 2) + 1))})
            total = round(sum(ln["charge"] for ln in lines), 2)
            segs.append(x.seg("CLM", pcn, _amt(total), "", "", x.c("11", "B", "1"), "Y", "A", "Y", "Y"))
            if prior_auth:
                segs.append(x.seg("REF", "G1", prior_auth))
            segs.append(x.seg("HI", *[x.c("ABK" if i == 0 else "ABF", c) for i, c in enumerate(dx)]))
            segs += [x.seg("NM1", "82", "1", self.r.choice(LAST), self.r.choice(FIRST), "", "", "", "XX", rendering),
                     x.seg("PRV", "PE", "PXC", "207Q00000X")]
            drg, tob, stmt = None, None, None
        else:
            inpatient = self.r.random() < 0.5
            for i in range(n_lines):
                rev, code, price = self.r.choice(REV)
                units = self.r.randint(1, 2)
                lines.append({"line_number": i + 1, "procedure_code": code, "revenue_code": rev, "modifiers": [],
                              "charge": round(price * units, 2), "units": units,
                              "service_date": dos.strftime("%Y%m%d"), "diagnosis_pointers": None})
            total = round(sum(ln["charge"] for ln in lines), 2)
            fac = "11" if inpatient else "13"
            tob = fac + "1"
            end = dos + timedelta(days=self.r.randint(1, 5) if inpatient else 0)
            stmt = (dos.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
            drg = self.r.choice(DRG) if inpatient else None
            segs.append(x.seg("CLM", pcn, _amt(total), "", "", x.c(fac, "A", "1"), "", "A", "Y", "Y"))
            segs.append(x.seg("DTP", "434", "RD8", f"{stmt[0]}-{stmt[1]}"))
            if inpatient:
                segs.append(x.seg("DTP", "435", "D8", stmt[0]))
            segs.append(x.seg("CL1", "1" if inpatient else "3", "7", "01"))
            if prior_auth:
                segs.append(x.seg("REF", "G1", prior_auth))
            segs.append(x.seg("HI", x.c("ABK", dx[0])))
            if len(dx) > 1:
                segs.append(x.seg("HI", *[x.c("ABF", c) for c in dx[1:]]))
            if drg:
                segs.append(x.seg("HI", x.c("DR", drg)))
            segs.append(x.seg("NM1", "71", "1", self.r.choice(LAST), self.r.choice(FIRST), "", "", "", "XX", rendering))
        if cob:
            segs += [
                x.seg("SBR", "S", "18", "OTHERGRP", "", "", "", "", "", "CI"),
                x.seg("OI", "", "", "Y", "", "", "Y"),
                x.seg("NM1", "IL", "1", "OTHERSUB", "PAT", "", "", "", "MI", "OTHERMEMBER1"),
                x.seg("NM1", "PR", "2", "OTHER PAYER CO", "", "", "", "", "PI", "OTHER99"),
                x.seg("REF", "F8", "OTHERPAYERCLAIM1"),
                x.seg("NM1", "82", "1"),
            ]
        for ln in lines:
            segs.append(x.seg("LX", ln["line_number"]))
            if kind == "P":
                proc = x.c("HC", ln["procedure_code"], *ln["modifiers"])
                segs.append(x.seg("SV1", proc, _amt(ln["charge"]), "UN", ln["units"], "", "",
                                  x.c(*ln["diagnosis_pointers"])))
            else:
                proc = x.c("HC", ln["procedure_code"]) if ln["procedure_code"] else ""
                segs.append(x.seg("SV2", ln["revenue_code"], proc, _amt(ln["charge"]), "UN", ln["units"]))
            segs.append(x.seg("DTP", "472", "D8", ln["service_date"]))
            segs.append(x.seg("REF", "6R", f"{pcn}-{ln['line_number']}"))
        self.key.append({
            "file": file_name, "st_control_number": st_ctrl, "patient_control_number": pcn,
            "claim_type": "professional" if kind == "P" else "institutional",
            "total_charge_amount": total, "line_count": len(lines),
            "principal_diagnosis_code": dx[0], "diagnosis_codes": dx,
            "rendering_or_attending_npi": rendering, "prior_authorization_number": prior_auth,
            "has_cob": cob, "drg_code": drg, "type_of_bill": tob,
            "statement_from_date": stmt[0] if stmt else None, "statement_to_date": stmt[1] if stmt else None,
            "lines": lines, **ctx,
        })
        return segs


def build(seed: int = 7, claims_per_file: int = 6) -> tuple[dict[str, str], dict]:
    """Return ({file_name: content}, answer_key)."""
    g = Gen(seed)
    files: dict[str, str] = {}
    expected_tx: list[dict] = []

    def interchange(x: X12, name: str, kind: str, tx_subs: list[list[dict]], ctrl: int, truncate=False) -> str:
        segs = [x.isa(ctrl),
                x.seg("GS", "HC", "SUBMITTER01", "RECEIVER01", "20261019", "1200", ctrl, "X",
                      PROFESSIONAL if kind == "P" else INSTITUTIONAL)]
        for i, subs in enumerate(tx_subs):
            st = f"{ctrl % 1000:03d}{i + 1:01d}"
            body = g.transaction(x, st, kind, subs, name)
            if truncate:
                body = body[: max(len(body) // 2, 8)]
                expected_tx.append({"file": name, "st_control_number": st, "transaction_status": "missing_SE"})
            else:
                expected_tx.append({"file": name, "st_control_number": st, "transaction_status": "ok"})
            segs += body
        if not truncate:
            segs += [x.seg("GE", len(tx_subs), ctrl), x.seg("IEA", "1", f"{ctrl:09d}")]
        return x.render(segs)

    def subs(n: int, kind_traps: bool = True) -> list[dict]:
        out = [{"claims": 1} for _ in range(n)]
        if kind_traps and n >= 3:
            out[0] = {"claims": 1, "patient": True}   # 2000C patient loop ...
            out[1] = {"claims": 2}                     # ... followed by subscriber-only claims
            out[2] = {"claims": 1, "cob": True}        # COB loop with second payer
        return out

    files["prof_basic.x12"] = interchange(X12(), "prof_basic.x12", "P", [subs(claims_per_file)], 101)
    files["inst_basic.x12"] = interchange(X12(newline=""), "inst_basic.x12", "I", [subs(claims_per_file)], 102)
    files["prof_pipe_multi_tx.x12"] = interchange(
        X12(el="|", comp="^", newline="\r\n"), "prof_pipe_multi_tx.x12", "P",
        [subs(claims_per_file), subs(max(claims_per_file // 2, 3))], 103)
    files["prof_truncated.x12"] = interchange(X12(), "prof_truncated.x12", "P", [subs(3, False)], 104, truncate=True)
    files["not_x12.txt"] = "MEMBER_ID,CLAIM_ID,AMOUNT\nM1,C1,10.00\n"
    expected_tx.append({"file": "not_x12.txt", "st_control_number": None, "transaction_status": "not_x12"})

    truncated = {"prof_truncated.x12"}
    key = {
        "seed": seed,
        "claims": [c for c in g.key if c["file"] not in truncated],
        "truncated_claims": [c["patient_control_number"] for c in g.key if c["file"] in truncated],
        "transactions": expected_tx,
    }
    return files, key


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--claims", type=int, default=6, help="subscribers per transaction")
    ap.add_argument("--key", help="answer key path (default: <out>_answer_key.json)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files, key = build(a.seed, a.claims)
    for name, content in files.items():
        (out / name).write_text(content)
    key_path = Path(a.key) if a.key else out.parent / f"{out.name}_answer_key.json"
    key_path.write_text(json.dumps(key, indent=2))
    print(f"wrote {len(files)} files, {len(key['claims'])} complete claims -> {out} (key: {key_path})")


if __name__ == "__main__":
    main()
