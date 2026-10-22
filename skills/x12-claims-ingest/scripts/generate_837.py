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
import copy
import json
import random
from datetime import date, timedelta
from pathlib import Path

PROFESSIONAL = "005010X222A1"
INSTITUTIONAL = "005010X223A2"
PROFESSIONAL_4010 = "004010X098A1"
INSTITUTIONAL_4010 = "004010X096A1"

FIRST = ["AVA", "NOAH", "MIA", "LIAM", "ZOE", "ELI", "IVY", "OWEN", "RUBY", "SAM", "NORA", "LEO"]
LAST = ["RIVERA", "CHEN", "PATEL", "OKAFOR", "NGUYEN", "SMITH", "GARCIA", "KIM", "SILVA", "BROWN"]
CPT = [("99213", 125.00), ("99214", 180.00), ("93000", 45.00), ("80053", 38.50), ("71046", 95.00), ("97110", 60.00)]
REV = [("0450", "99284", 850.00), ("0300", "80053", 120.00), ("0320", "71046", 310.00),
       ("0250", None, 75.00), ("0636", "J1100", 42.00)]
DX = ["E119", "I10", "J449", "M545", "N390", "R0789", "E785", "F329", "K219", "Z23"]
DX9 = ["25000", "4019", "49390", "7242", "5990", "78650", "2724", "311", "53081", "V0481"]  # 4010 / ICD-9
DRG = ["470", "291", "392", "871"]
FILING = ["MC", "MA", "CI", "HM"]
PAYERS = [("PAYER ALPHA", "PAY01"), ("PAYER BETA", "PAY02")]
TX_DEFECTS = {"po_box": "BILLING_ADDRESS_PO_BOX", "zip5": "ZIP_INCOMPLETE"}


def _amt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def npi_check_digit(first9: str) -> str:
    """CMS NPI check digit: Luhn mod 10 over 9 digits as if prefixed by 80840 (constant 24)."""
    total = 24
    for i, ch in enumerate(reversed(first9)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            d = d - 9 if d > 9 else d
        total += d
    return str((10 - total % 10) % 10)


def _bad_npi(npi: str) -> str:
    return npi[:9] + str((int(npi[9]) + 1) % 10)


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

    def isa(self, ctrl: int, version: str = "00501", trimmed: bool = False) -> str:
        f = [
            "ISA", "00", " " * 10, "00", " " * 10, "ZZ", "SUBMITTER01".ljust(15), "ZZ", "RECEIVER01".ljust(15),
            "261019", "1200", self.rep if version == "00501" else "U", version, f"{ctrl:09d}", "0", "T", self.comp,
        ]
        if trimmed:  # non-compliant sender: padding stripped
            return self.el.join(x.strip() for x in f)
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
        self.store: dict[str, dict] = {}

    def _npi(self) -> str:
        raw = "1" + "".join(self.r.choice("0123456789") for _ in range(9))
        return raw[:9] + npi_check_digit(raw[:9])

    def _dos(self, version: str = "5010") -> date:
        base = date(2026, 9, 1) if version == "5010" else date(2011, 6, 1)
        return base + timedelta(days=self.r.randrange(30))

    def _person(self) -> tuple[str, str, str, str]:
        dob = date(1950, 1, 1) + timedelta(days=self.r.randrange(25000))
        return self.r.choice(LAST), self.r.choice(FIRST), dob.strftime("%Y%m%d"), self.r.choice("MF")

    def _header(self, x: X12, st_ctrl: str, kind: str, version: str) -> list[str]:
        if version == "4010":
            st = x.seg("ST", "837", st_ctrl)
        else:
            st = x.seg("ST", "837", st_ctrl, PROFESSIONAL if kind == "P" else INSTITUTIONAL)
        return [
            st,
            x.seg("BHT", "0019", "00", f"B{st_ctrl}", "20261019", "1200", "CH"),
            x.seg("NM1", "41", "2", "SYNTHETIC CLEARINGHOUSE", "", "", "", "", "46", "SUB01"),
            x.seg("PER", "IC", "EDI DESK", "TE", "5555550100"),
            x.seg("NM1", "40", "2", "SYNTHETIC RECEIVER", "", "", "", "", "46", "RCV01"),
        ]

    def transaction(self, x: X12, st_ctrl: str, kind: str, subscribers: list[dict], file_name: str,
                    opts: dict | None = None) -> list[str]:
        opts = opts or {}
        version = opts.get("version", "5010")
        body = self._header(x, st_ctrl, kind, version)
        hl = 1
        bp_npi, bp_tin = self._npi(), f"9{self.r.randrange(10**7, 10**8)}"
        bp_name = "SYNTH CLINIC GROUP" if kind == "P" else "SYNTH GENERAL HOSPITAL"
        bp_body = [
            x.seg("PRV", "BI", "PXC", "207Q00000X" if kind == "P" else "282N00000X"),
            x.seg("NM1", "85", "2", bp_name, "", "", "", "", "XX", bp_npi),
            x.seg("N3", "PO BOX 4471" if opts.get("po_box") else "100 MAIN ST"),
            x.seg("N4", "SPRINGFIELD", "WA", "98101" if opts.get("zip5") else "981011234"),
            x.seg("REF", "EI", bp_tin),
        ]
        body += [x.seg("HL", hl, "", "20", "1"), *bp_body]
        tx_defects = [d for k, d in TX_DEFECTS.items() if opts.get(k)]
        bp_hl = hl
        for sub in subscribers:
            hl += 1
            sub_hl = hl
            last, first, dob, gender = self._person()
            member = f"M{self.r.randrange(10**8, 10**9)}"
            payer_name, payer_id = self.r.choice(PAYERS)
            filing = self.r.choice(FILING)
            has_patient = sub.get("patient", False)
            sub_body = [
                x.seg("SBR", "P", "" if has_patient else "18", f"GRP{self.r.randrange(1000, 9999)}",
                      "", "", "", "", "", filing),
                x.seg("NM1", "IL", "1", last, first, "", "", "", "MI", member),
                x.seg("N3", "200 OAK AVE"),
                x.seg("N4", "TACOMA", "WA", "98402"),
                x.seg("DMG", "D8", dob, gender),
                x.seg("NM1", "PR", "2", payer_name, "", "", "", "", "PI", payer_id),
            ]
            body += [x.seg("HL", sub_hl, bp_hl, "22", "1" if has_patient else "0"), *sub_body]
            pat, pat_body = None, []
            if has_patient:
                hl += 1
                plast, pfirst, pdob, pgender = self._person()
                pat = {"last": plast, "dob": pdob, "gender": pgender}
                pat_body = [
                    x.seg("PAT", "19"),
                    x.seg("NM1", "QC", "1", plast, pfirst),
                    x.seg("N3", "200 OAK AVE"),
                    x.seg("N4", "TACOMA", "WA", "98402"),
                    x.seg("DMG", "D8", pdob, pgender),
                ]
                body += [x.seg("HL", hl, sub_hl, "23", "0"), *pat_body]
            for _ in range(sub.get("claims", 1)):
                segs = self.claim(x, kind, sub.get("cob", False), file_name, st_ctrl, {
                    "member_id": member, "payer_id": payer_id, "billing_provider_npi": bp_npi,
                    "billing_provider_tin": bp_tin, "claim_filing_indicator": filing,
                    "patient_is_subscriber": pat is None,
                    "patient_birth_date": (pat or {"dob": dob})["dob"],
                    "patient_gender": (pat or {"gender": gender})["gender"],
                    "subscriber_birth_date": dob,
                }, opts, sub.get("defects", []) + tx_defects)
                self.store[self.key[-1]["patient_control_number"]] = {
                    "kind": kind, "version": version, "bp": bp_body, "sub": sub_body, "pat": pat_body, "claim": segs}
                body += segs
        body.append(x.seg("SE", len(body) + 1, st_ctrl))
        return body

    def claim(self, x: X12, kind: str, cob: bool, file_name: str, st_ctrl: str, ctx: dict,
              opts: dict | None = None, defects: list | None = None) -> list[str]:
        opts, defects = opts or {}, list(defects or [])
        version = opts.get("version", "5010")
        self.n += 1
        pcn = f"PCN{self.n:06d}"
        dx = self.r.sample(DX9 if version == "4010" else DX, self.r.randint(1, 4))
        n_lines = self.r.randint(1, 4)
        segs, lines = [], []
        dos = self._dos(version)
        rendering = self._npi()
        prior_auth = f"PA{self.r.randrange(10**6, 10**7)}" if self.r.random() < 0.4 else None
        principal_q, other_q = ("BK", "BF") if version == "4010" else ("ABK", "ABF")
        if "ICD10_FORMAT" in defects:  # decimal point sent inside X12
            dx = [dx[0][:3] + "." + (dx[0][3:] or "0")] + dx[1:]
        sent_rendering = _bad_npi(rendering) if "NPI_INVALID" in defects else rendering
        if kind == "P":
            for i in range(n_lines):
                code, price = self.r.choice(CPT)
                units = self.r.randint(1, 3)
                mod = "25" if code.startswith("992") and self.r.random() < 0.5 else None
                d = dos + timedelta(days=i)
                if opts.get("varied_pointers"):
                    k = i % len(dx)
                    ptrs = [k + 1] + ([1] if k else [])
                else:
                    ptrs = list(range(1, min(len(dx), 2) + 1))
                lines.append({"line_number": i + 1, "procedure_code": code, "revenue_code": None,
                              "modifiers": [mod] if mod else [], "charge": round(price * units, 2), "units": units,
                              "service_date": d.strftime("%Y%m%d"), "diagnosis_pointers": ptrs,
                              "line_rendering_npi": None})
            if opts.get("line_rendering") and n_lines > 1:
                lines[1]["line_rendering_npi"] = self._npi()
            if "PROCEDURE_CODE_FORMAT" in defects:
                lines[0]["procedure_code"] = lines[0]["procedure_code"][:4]
            if "DATE_INVALID" in defects:
                lines[0]["service_date"] = "20270115"
            if "DX_POINTER_INVALID" in defects:
                lines[0]["diagnosis_pointers"] = [len(dx) + 1]
            total = round(sum(ln["charge"] for ln in lines), 2) + (10 if "TOTAL_MISMATCH" in defects else 0)
            pos = "75" if "POS_INVALID" in defects else "11"
            segs.append(x.seg("CLM", pcn, _amt(total), "", "", x.c(pos, "B", "1"), "Y", "A", "Y", "Y"))
            if prior_auth:
                segs.append(x.seg("REF", "G1", prior_auth))
            segs.append(x.seg("HI", *[x.c(principal_q if i == 0 else other_q, c) for i, c in enumerate(dx)]))
            segs += [x.seg("NM1", "82", "1", self.r.choice(LAST), self.r.choice(FIRST), "", "", "", "XX", sent_rendering),
                     x.seg("PRV", "PE", "PXC", "207Q00000X")]
            drg, tob, stmt = None, None, None
        else:
            inpatient = self.r.random() < 0.5
            for i in range(n_lines):
                rev, code, price = self.r.choice(REV)
                units = self.r.randint(1, 2)
                lines.append({"line_number": i + 1, "procedure_code": code, "revenue_code": rev, "modifiers": [],
                              "charge": round(price * units, 2), "units": units,
                              "service_date": dos.strftime("%Y%m%d"), "diagnosis_pointers": None,
                              "line_rendering_npi": None})
            total = round(sum(ln["charge"] for ln in lines), 2) + (10 if "TOTAL_MISMATCH" in defects else 0)
            fac = "11" if inpatient else "13"
            tob = fac + "1"
            end = dos + timedelta(days=self.r.randint(1, 5) if inpatient else 0)
            stmt = (dos.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
            drg = self.r.choice(DRG) if inpatient else None
            if "REVENUE_CODE_FORMAT" in defects:
                lines[0]["revenue_code"] = lines[0]["revenue_code"].lstrip("0")
            if "DATE_INVALID" in defects:
                lines[0]["service_date"] = (end + timedelta(days=3)).strftime("%Y%m%d")
            segs.append(x.seg("CLM", pcn, _amt(total), "", "", x.c(fac, "A", "1"), "", "A", "Y", "Y"))
            segs.append(x.seg("DTP", "434", "RD8", f"{stmt[0]}-{stmt[1]}"))
            if inpatient:
                segs.append(x.seg("DTP", "435", "D8", stmt[0]))
            segs.append(x.seg("CL1", "1" if inpatient else "3", "7", "01"))
            if prior_auth:
                segs.append(x.seg("REF", "G1", prior_auth))
            segs.append(x.seg("HI", x.c(principal_q, dx[0])))
            if len(dx) > 1:
                segs.append(x.seg("HI", *[x.c(other_q, c) for c in dx[1:]]))
            if drg:
                segs.append(x.seg("HI", x.c("DR", drg)))
            segs.append(x.seg("NM1", "71", "1", self.r.choice(LAST), self.r.choice(FIRST), "", "", "", "XX", sent_rendering))
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
            if ln["line_rendering_npi"]:
                segs.append(x.seg("NM1", "82", "1", "LINEDOC", "PAT", "", "", "", "XX", ln["line_rendering_npi"]))
        for ln in lines:  # what a correct mapping produces per line
            ln["rendering_npi"] = ln["line_rendering_npi"] or sent_rendering
            ptrs = ln["diagnosis_pointers"]
            ln["diagnosis_codes"] = [dx[q - 1] if 1 <= q <= len(dx) else None for q in ptrs] if ptrs else None
        self.key.append({
            "file": file_name, "st_control_number": st_ctrl, "patient_control_number": pcn,
            "claim_type": "professional" if kind == "P" else "institutional", "x12_version": version,
            "frequency": "1", "total_charge_amount": round(total, 2), "line_count": len(lines),
            "principal_diagnosis_code": dx[0], "diagnosis_codes": dx,
            "rendering_or_attending_npi": sent_rendering, "prior_authorization_number": prior_auth,
            "has_cob": cob, "drg_code": drg, "type_of_bill": tob,
            "statement_from_date": stmt[0] if stmt else None, "statement_to_date": stmt[1] if stmt else None,
            "defects": sorted(set(defects)), "lines": lines, **ctx,
        })
        return segs

    def resend_transaction(self, x: X12, st_ctrl: str, items: list[dict], file_name: str) -> list[str]:
        """Re-send earlier claims: freq 7 (replacement: first line +1 unit), 8 (void), or "dup" (identical
        claim under a new patient control number). Each re-sent claim gets its own billing/subscriber HLs."""
        first = self.store[items[0]["pcn"]]
        body = self._header(x, st_ctrl, first["kind"], first["version"])
        hl = 0
        for it in items:
            st = self.store[it["pcn"]]
            orig = next(k for k in reversed(self.key) if k["patient_control_number"] == it["pcn"])
            entry = copy.deepcopy(orig)
            hl += 1
            bp_hl = hl
            body += [x.seg("HL", hl, "", "20", "1"), *st["bp"]]
            hl += 1
            sub_hl = hl
            body += [x.seg("HL", hl, bp_hl, "22", "1" if st["pat"] else "0"), *st["sub"]]
            if st["pat"]:
                hl += 1
                body += [x.seg("HL", hl, sub_hl, "23", "0"), *st["pat"]]
            segs = list(st["claim"])
            ci = next(i for i, sg in enumerate(segs) if sg.startswith("CLM" + x.el))
            els = segs[ci].split(x.el)
            freq = it["freq"]
            if freq in ("7", "8"):
                comp = els[5].split(x.comp)
                comp[2] = freq
                els[5] = x.comp.join(comp)
                entry["frequency"] = freq
            if freq == "7":
                li = next(i for i, sg in enumerate(segs) if sg.startswith(("SV1" + x.el, "SV2" + x.el)))
                e = segs[li].split(x.el)
                ci_, ui = (2, 4) if e[0] == "SV1" else (3, 5)
                ln0 = entry["lines"][0]
                price = ln0["charge"] / ln0["units"]
                ln0["units"] += 1
                ln0["charge"] = round(price * ln0["units"], 2)
                e[ci_], e[ui] = _amt(ln0["charge"]), str(ln0["units"])
                segs[li] = x.el.join(e)
                entry["total_charge_amount"] = round(sum(ln["charge"] for ln in entry["lines"]), 2)
                els[2] = _amt(entry["total_charge_amount"])
            if freq == "dup":
                self.n += 1
                new_pcn = f"PCN{self.n:06d}"
                els[1] = new_pcn
                entry.update(patient_control_number=new_pcn, frequency="1", defects=["DUPLICATE_CLAIM"])
            segs[ci] = x.el.join(els)
            if freq in ("7", "8"):
                segs.insert(ci + 1, x.seg("REF", "F8", f"ICN{it['pcn'][3:]}"))
            body += segs
            entry.update(file=file_name, st_control_number=st_ctrl)
            if freq != "dup":
                entry["defects"] = []
            self.key.append(entry)
        body.append(x.seg("SE", len(body) + 1, st_ctrl))
        return body


def default_spec(claims_per_file: int = 6) -> list[dict]:
    """The file set used by the unit tests: every trap once, plus a truncated and a non-X12 file.

    Each entry is either an interchange {name, kind P|I, style (X12 kwargs), tx: [(subscribers, traps)],
    ctrl, truncate} or a raw non-X12 file {name, raw}.
    """
    n = claims_per_file
    return [
        {"name": "prof_basic.x12", "kind": "P", "style": {}, "tx": [(n, True)], "ctrl": 101},
        {"name": "inst_basic.x12", "kind": "I", "style": {"newline": ""}, "tx": [(n, True)], "ctrl": 102},
        {"name": "prof_pipe_multi_tx.x12", "kind": "P", "style": {"el": "|", "comp": "^", "newline": "\r\n"},
         "tx": [(n, True), (max(n // 2, 3), True)], "ctrl": 103},
        {"name": "prof_truncated.x12", "kind": "P", "style": {}, "tx": [(3, False)], "ctrl": 104, "truncate": True},
        {"name": "not_x12.txt", "raw": "MEMBER_ID,CLAIM_ID,AMOUNT\nM1,C1,10.00\n"},
    ]


def build(seed: int = 7, claims_per_file: int = 6, spec: list[dict] | None = None) -> tuple[dict[str, str], dict]:
    """Return ({file_name: content}, answer_key) for `spec` (default_spec() when omitted).

    File spec keys: name, kind (P|I), style (X12 kwargs), ctrl, tx [(subscribers, traps[, tx_opts])],
    truncate, version ("5010"|"4010"), trimmed_isa, gs_date (CCYYMMDD), or resend [{"pcn", "freq"}]
    (freq "7" replacement, "8" void, "dup" duplicate under a new PCN) in place of tx.
    tx_opts: po_box, zip5, line_rendering, varied_pointers, sub_overrides {index: {...subscriber keys}}.
    """
    g = Gen(seed)
    files: dict[str, str] = {}
    expected_tx: list[dict] = []

    def interchange(x: X12, f: dict, tx_bodies) -> str:
        version = f.get("version", "5010")
        kind = f.get("kind", "P")
        gs_ver = {("P", "5010"): PROFESSIONAL, ("I", "5010"): INSTITUTIONAL,
                  ("P", "4010"): PROFESSIONAL_4010, ("I", "4010"): INSTITUTIONAL_4010}[(kind, version)]
        ctrl, truncate = f["ctrl"], f.get("truncate", False)
        segs = [x.isa(ctrl, "00401" if version == "4010" else "00501", f.get("trimmed_isa", False)),
                x.seg("GS", "HC", "SUBMITTER01", "RECEIVER01", f.get("gs_date", "20261019"), "1200", ctrl, "X", gs_ver)]
        n_tx = 0
        for i, build_body in enumerate(tx_bodies):
            st = f"{ctrl % 1000:03d}{i + 1:01d}"
            body = build_body(st)
            n_tx += 1
            if truncate:
                body = body[: max(len(body) // 2, 8)]
                expected_tx.append({"file": f["name"], "st_control_number": st, "transaction_status": "missing_SE"})
            else:
                expected_tx.append({"file": f["name"], "st_control_number": st, "transaction_status": "ok"})
            segs += body
        if not truncate:
            segs += [x.seg("GE", n_tx, ctrl), x.seg("IEA", "1", f"{ctrl:09d}")]
        return x.render(segs)

    def subs(n: int, kind_traps: bool = True, overrides: dict | None = None) -> list[dict]:
        out = [{"claims": 1} for _ in range(n)]
        if kind_traps and n >= 3:
            out[0] = {"claims": 1, "patient": True}   # 2000C patient loop ...
            out[1] = {"claims": 2}                     # ... followed by subscriber-only claims
            out[2] = {"claims": 1, "cob": True}        # COB loop with second payer
        for i, extra in (overrides or {}).items():
            out[int(i)] = {**out[int(i)], **extra}
        return out

    truncated = set()
    for f in spec or default_spec(claims_per_file):
        if "raw" in f:
            files[f["name"]] = f["raw"]
            expected_tx.append({"file": f["name"], "st_control_number": None, "transaction_status": "not_x12"})
            continue
        if f.get("truncate"):
            truncated.add(f["name"])
        x = X12(**f.get("style", {}))
        if "resend" in f:
            bodies = [lambda st, f=f, x=x: g.resend_transaction(x, st, f["resend"], f["name"])]
        else:
            bodies = []
            for t in f["tx"]:
                n, traps, opts = (list(t) + [{}])[:3]
                opts = {**opts, "version": f.get("version", "5010")}
                bodies.append(lambda st, n=n, traps=traps, opts=opts, f=f, x=x: g.transaction(
                    x, st, f["kind"], subs(n, traps, opts.get("sub_overrides")), f["name"], opts))
        files[f["name"]] = interchange(x, f, bodies)

    # Current view: latest version of each claim (by file order, which is GS date order in the specs); voids drop.
    current: dict[str, dict] = {}
    for k in g.key:
        if k["file"] in truncated:
            continue
        pcn = k["patient_control_number"]
        if k["frequency"] == "8":
            current.pop(pcn, None)
        else:
            current[pcn] = k
    key = {
        "seed": seed,
        "claims": list(current.values()),
        "all_versions": [k for k in g.key if k["file"] not in truncated],
        "truncated_claims": [k["patient_control_number"] for k in g.key if k["file"] in truncated],
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
