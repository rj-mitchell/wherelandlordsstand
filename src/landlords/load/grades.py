"""Regulatory judgements, gradings under review and enforcement notices, as one long table: ``grades``.

* The current table (judgements since April 2024) gives each landlord's latest grade for each standard: consumer
  (C1-C4; the only one for councils), governance (G1-G4), viability (V1-V4), and rent, with the grade's date and
  how it changed.
* The archived table (2012 to March 2024) gives every published judgement and notice, with governance and viability
  grades at the time. There were no consumer grades before April 2024.
* The gradings under review list is a GOV.UK page: each entry names a landlord, its code and the date.

A ``*`` after a grade marks a for-profit provider. It is kept as ``for_profit`` and removed from the grade.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pyarrow as pa

from landlords.config import Settings
from landlords.load.common import (
    as_date,
    code,
    file_ref,
    record_sources,
    require,
    sheet_table,
    source_file,
    text,
    write_table,
)

SCHEMA = pa.schema([
    ("landlord_id", pa.string()),
    ("name_published", pa.string()),
    ("table", pa.string()),             # current, archive, under-review, enforcement
    ("publication_type", pa.string()),  # Narrative RJ, Interim RJ, Strapline RJ, Regulatory Notice, ...
    ("publication_date", pa.date32()),
    ("standard", pa.string()),          # consumer, governance, viability, rent; empty for notices
    ("grade", pa.string()),             # C1 ... V4, or Y for a rent judgement; empty if none
    ("for_profit", pa.bool_()),
    ("change", pa.string()),            # as published: First grading, Downgrade, Regrade V1 to V2 ...
    ("grade_date", pa.date32()),
    ("engagement", pa.string()),        # Inspection, Stability Check, Responsive Engagement ...
    ("explanation", pa.string()),
    ("other_landlords", pa.string()),   # other landlords the judgement covers, as published
    ("name_change", pa.string()),       # the regulator's note of name and code changes
    ("source_file", pa.string()),
])

CURRENT = {
    "consumer": ("Consumer grade", "Consumer Grade Change", "Consumer Grade Date"),
    "governance": ("Governance Grade", "Governance Grade Change", "Governance Date"),
    "viability": ("Viability Grade", "Viability Grade Change", "Viability Grade Date"),
    "rent": ("Rent", "Rent Change", "Rent Date"),
}


def _none(v) -> str:
    s = text(v)
    return "" if s in ("-", "None", "N/A") else s


def _grade(v) -> tuple[str, bool]:
    s = _none(v)
    return s.rstrip("*"), s.endswith("*")


def load_current(note: dict) -> list[dict]:
    header, rows = sheet_table(note["path"], "Regulatory Judgements", "Reg Code")
    require(header, ["Reg Code", "Landlord", "Name and Reg Code Change Details", "Type of Publication",
                     "Publication Date", "Engagement Process", *[c for t in CURRENT.values() for c in t]],
            "judgements table")
    out = []
    for r in rows:
        d = dict(zip(header, r, strict=False))
        base = {"landlord_id": code(d["Reg Code"]), "name_published": text(d["Landlord"]), "table": "current",
                "publication_type": text(d["Type of Publication"]),
                "publication_date": as_date(d["Publication Date"]), "engagement": text(d["Engagement Process"]),
                "explanation": "", "other_landlords": _none(d.get("Other landlords included in the judgement", "")),
                "name_change": _none(d["Name and Reg Code Change Details"]), **file_ref(note)}
        graded = False
        for standard, (g, ch, dt) in CURRENT.items():
            grade, for_profit = _grade(d[g])
            change = _none(d[ch])
            if grade or change:
                graded = True
                out.append({**base, "standard": standard, "grade": grade, "for_profit": for_profit,
                            "change": change, "grade_date": as_date(d[dt])})
        if not graded:  # a judgement with no grades, kept so the publication is still listed
            out.append({**base, "standard": "", "grade": "", "for_profit": False, "change": "", "grade_date": None})
    header, rows = sheet_table(note["path"], "Enforcement Notices", "Reg Code")
    require(header, ["Reg Code", "Provider", "Type of Publication", "Publication Date", "Explanation"],
            "enforcement notices")
    for r in rows:
        d = dict(zip(header, r, strict=False))
        out.append(_notice(d, note))
    return out


def _notice(d: dict, note: dict) -> dict:
    return {"landlord_id": code(d["Reg Code"]), "name_published": text(d["Provider"]), "table": "enforcement",
            "publication_type": text(d["Type of Publication"]), "publication_date": as_date(d["Publication Date"]),
            "standard": "", "grade": "", "for_profit": False, "change": "", "grade_date": None,
            "engagement": text(d.get("Route", "")), "explanation": text(d.get("Explanation", "")),
            "other_landlords": _none(d.get("Other providers included in the notice", "")),
            "name_change": _none(d.get("Name and Reg Code Change Details", "")), **file_ref(note)}


def load_archive(note: dict) -> list[dict]:
    header, rows = sheet_table(note["path"], "RegulatoryJudgementsNotices", "Reg Code")
    require(header, ["Reg Code", "Provider", "Gov", "Via", "Type of Publication", "Publication Date", "Route",
                     "Explanation"], "archived judgements")
    out = []
    for r in rows:
        d = dict(zip(header, r, strict=False))
        if not text(d["Reg Code"]):
            continue
        base = {"landlord_id": code(d["Reg Code"]), "name_published": text(d["Provider"]), "table": "archive",
                "publication_type": text(d["Type of Publication"]),
                "publication_date": as_date(d["Publication Date"]), "engagement": _none(d["Route"]),
                "explanation": text(d["Explanation"]),
                "other_landlords": _none(d.get("Other providers included in the judgement", "")),
                "name_change": _none(d.get("Name and Reg Code Change Details", "")), "change": "",
                **file_ref(note)}
        graded = False
        for standard, col in (("governance", "Gov"), ("viability", "Via")):
            grade, for_profit = _grade(d[col])
            if grade:
                graded = True
                out.append({**base, "standard": standard, "grade": grade, "for_profit": for_profit,
                            "grade_date": base["publication_date"]})
        if not graded:
            out.append({**base, "standard": "", "grade": "", "for_profit": False, "grade_date": None})
    header, rows = sheet_table(note["path"], "EnforcementNotices", "Reg Code")
    for r in rows:
        d = dict(zip(header, r, strict=False))
        if text(d.get("Reg Code")):
            out.append({**_notice(d, note), "table": "archive"})
    return out


_ENTRY = re.compile(r"<h3[^>]*>(.*?)</h3>(.*?)(?=<h[23]|\Z)", re.S)
_HEADING = re.compile(r"^(\d{1,2} \w+ \d{4}):\s*(.+?)\s*\(([A-Z0-9]+)\)\s*$")


def load_under_review(note: dict) -> list[dict]:
    content = json.loads(Path(note["path"]).read_text())
    body = content.get("details", {}).get("body", "")
    out = []
    for heading, rest in _ENTRY.findall(body):
        heading = text(re.sub(r"<[^>]+>", "", heading))
        m = _HEADING.match(heading)
        if not m:
            raise ValueError(f"gradings under review: can't read the heading {heading!r}")
        out.append({"landlord_id": m.group(3), "name_published": m.group(2), "table": "under-review",
                    "publication_type": "Grading Under Review", "publication_date": as_date(m.group(1)),
                    "standard": "", "grade": "", "for_profit": False, "change": "", "grade_date": None,
                    "engagement": "", "explanation": text(re.sub(r"<[^>]+>", " ", rest)),
                    "other_landlords": "", "name_change": "", **file_ref(note)})
    return out


def load(settings: Settings) -> dict[str, int]:
    notes = [source_file(settings, "judgements", "table"), source_file(settings, "judgements", "archive"),
             source_file(settings, "judgements", "under-review")]
    rows = load_current(notes[0]) + load_archive(notes[1]) + load_under_review(notes[2])
    write_table(settings, "grades", rows, SCHEMA)
    record_sources(settings, notes)
    return {"grades": len(rows)}
