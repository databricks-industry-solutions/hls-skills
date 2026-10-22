# 837 loop and segment cheat sheet

Summary of the 5010 837P (005010X222A1) and 837I (005010X223A2) structure as used by
`scripts/x12_837.py`. Element numbers are 1-based (`CLM02` = second element after the segment id).
Written from public descriptions of the transaction; the licensed X12 TR3 guides are the authority.

## Envelope

| Segment | Meaning | Elements used |
|---|---|---|
| ISA | Interchange header, fixed width 106 chars | pos 4 element separator, ISA13 control number, pos 105 component separator (ISA16), pos 106 segment terminator |
| GS | Functional group | GS08 implementation version (`X222` professional, `X223` institutional, `X224` dental) |
| ST / SE | Transaction set | ST01 `837`, ST02 control number; SE01 segment count (ST..SE inclusive), SE02 = ST02 |
| GE / IEA | Group / interchange trailers | not used for parsing |

Delimiters are declared per file. Never hard-code `*`, `:` or `~`: `|`, `^` and newline terminators
are common.

## Hierarchy (HL)

`HL01` id, `HL02` parent id, `HL03` level code, `HL04` has-children flag.

| HL03 | Loop | Holds | Key segments |
|---|---|---|---|
| 20 | 2000A billing provider | 2010AA billing provider, 2010AB pay-to | `PRV*BI` taxonomy; `NM1*85` (NM103 name, NM109 NPI when NM108=`XX`); `N4`; `REF*EI` TIN |
| 22 | 2000B subscriber | 2010BA subscriber, 2010BB payer | `SBR` (01 payer responsibility P/S/T, 02 relationship `18`=self, 03 group, 09 claim filing indicator); `NM1*IL` (NM109 member id); `DMG*D8` (02 DOB, 03 gender); `NM1*PR` (NM109 payer id) |
| 23 | 2000C patient (only when patient is not the subscriber) | 2010CA patient | `PAT` (01 relationship); `NM1*QC`; `DMG` |

A claim belongs to the most recent subscriber HL, and to the most recent patient HL only if that
patient HL is a child of the same subscriber. The billing provider HL is the most recent HL 20.

## Claim (2300) and its child loops

| Segment | Meaning | Elements used |
|---|---|---|
| CLM | Claim | 01 patient control number, 02 total charge, 05 composite: facility code (POS for 837P, facility type for 837I) : qualifier : frequency code |
| DTP*434 | Statement period (837I) | 03 `CCYYMMDD-CCYYMMDD` (RD8) |
| DTP*435 | Admission date (837I) | 03 |
| CL1 | Institutional claim code (837I) | 01 admission type, 02 admission source, 03 patient status |
| REF*G1 / 9F / F8 / D9 | Prior auth / referral / payer claim control number (replacements) / clearinghouse trace | 02 |
| HI | Diagnosis and other code lists | each element is `qualifier:code`. ABK/BK principal dx, ABF/BF other dx, ABJ/BJ admitting, APR/PR reason for visit, ABN/BN external cause, DR DRG |
| NM1*82 / 71 / DN / 77 | Rendering (2310B, 837P) / attending (2310A, 837I) / referring / service facility | NM109 NPI when NM108=`XX` |

### Other subscriber (COB) loops: 2320 / 2330A-G

Start with a second `SBR` after the CLM and before the first `LX`. They repeat `NM1*IL`, `NM1*PR`,
`REF*F8`, `NM1*82` and more **for the other payer**. Reading them as claim-level values is the most
common 837 parsing bug: the member id, payer id or payer claim number gets overwritten with the
secondary payer's. The module flags these segments with `in_cob` and excludes them from claim fields.

## Service line (2400)

| Segment | Meaning | Elements used |
|---|---|---|
| LX | Line counter | 01 line number |
| SV1 (837P) | Professional service | 01 composite `HC:code:mod1:mod2:mod3:mod4`, 02 charge, 03 unit basis (UN/MJ), 04 units, 05 place of service, 07 diagnosis pointers `1:2:3:4` |
| SV2 (837I) | Institutional service | 01 revenue code, 02 composite procedure (optional), 03 charge, 04 unit basis, 05 units |
| DTP*472 | Service date | 03 `CCYYMMDD` or `CCYYMMDD-CCYYMMDD` |
| REF*6R | Line item control number | 02 |
| LIN (2410) | Drug identification | 02 `N4`, 03 NDC |
| NM1*82 (2420A) | Line rendering provider | NM109 |

Line adjudication loops (2430: SVD, CAS, DTP*573) appear only on COB claims and are not parsed.

## Parsing traps (checked by the unit tests)

1. Delimiters differ per file; read them from the ISA.
2. Segment terminator may be followed by `\n` or `\r\n`, or may itself be `\n`. Trim whitespace per segment.
3. Patient (2000C) values must not carry forward to the next subscriber's claims.
4. COB loops repeat NM1/REF qualifiers used at claim level.
5. 837I carries several HI segments per claim; keep diagnosis order by segment then element.
6. Trailing empty elements are omitted by senders, so `CLM` may have fewer elements than expected:
   index with `get()` (NULL when absent), never `[n]` under ANSI mode.
7. Amount and date elements can be malformed; `try_cast` / `try_to_timestamp` keep the job running
   and leave a NULL that reconciliation (header vs line totals) will surface.
8. A transaction without `SE`, or with `SE01` not equal to the segments received, is incomplete.
