"""Everything a landlord's page shows, gathered from the staging tables: ``build_profiles``.

Each figure is kept with the hash of the file it came from (``source``), so the page can link every figure to its
published file and year. Nothing here changes a published figure; positions among similar landlords come from
``scores`` and are labelled as ours.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from landlords.config import Settings
from landlords.load.common import read_table
from landlords.register import aliases, landlords
from landlords.score import rules

ALSO_KNOWN = ("short", "trading", "logo label", "managing body", "group")


@dataclass
class Data:
    """The staging tables, read once."""

    settings: Settings
    reg: dict = field(default_factory=dict)
    tables: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.reg = landlords()
        for name in ("tsm", "tsm_coverage", "tsm_survey", "grades", "groups", "ombudsman", "owners",
                     "landlord_area", "peer_groups", "scores"):
            self.tables[name] = read_table(self.settings, name)
        path = self.settings.staging_dir / "sources.json"
        self.sources = json.loads(path.read_text()) if path.exists() else {}
        self.aliases = defaultdict(list)
        for a in aliases():
            self.aliases[a["landlord_id"]].append(a)
        self.parents = {g["landlord_id"]: g["parent_id"] for g in self.tables["groups"] if g["parent_id"]}
        self.tsm_periods = sorted({c["period"] for c in self.tables["tsm_coverage"]})
        self.om_periods = sorted({r["period"] for r in self.tables["ombudsman"]})
        self.index = {name: defaultdict(list) for name in ("tsm", "tsm_coverage", "tsm_survey", "grades",
                                                            "landlord_area", "peer_groups", "scores")}
        for name, idx in self.index.items():
            key = "profile_id" if name == "landlord_area" else "landlord_id"
            for r in self.tables[name]:
                idx[r[key]].append(r)
        self.om_by_profile = defaultdict(list)
        owner = {o["landlord_id"]: o["profile_id"] for o in self.tables["owners"]}
        for r in self.tables["ombudsman"]:
            if owner.get(r["landlord_id"]):
                self.om_by_profile[owner[r["landlord_id"]]].append(r)


def _latest(rows: list[dict], key: str = "period") -> str | None:
    return max((r[key] for r in rows), default=None)


def grade_for(data: Data, lid: str) -> dict:
    """The landlord's latest consumer grade in the current judgements, or its nearest registered parent's."""
    chain, cur, seen = [], lid, set()
    while cur and cur not in seen:
        chain.append(cur)
        seen.add(cur)
        cur = data.parents.get(cur, "")
    out: dict = {"grade": None}
    for who in chain:
        rows = [g for g in data.index["grades"][who] if g["table"] == "current"]
        consumer = [g for g in rows if g["standard"] == "consumer" and g["grade"]]
        if consumer:
            g = max(consumer, key=lambda x: x["grade_date"] or date.min)
            out = {"grade": g["grade"], "date": g["grade_date"], "change": g["change"],
                   "publication": g["publication_type"], "source": g["source_file"],
                   "by": who, "by_name": data.reg.get(who, {}).get("display_name") or g["name_published"]}
            break
    own = data.index["grades"][lid]
    under = [g for g in own if g["table"] == "under-review"]
    if under:
        out["under_review"] = {"date": under[-1]["publication_date"], "source": under[-1]["source_file"]}
    notices = [g for g in own if g["table"] == "enforcement"]
    if notices:
        out["enforcement"] = {"date": notices[-1]["publication_date"], "source": notices[-1]["source_file"]}
    if not out.get("source"):
        cur = [g for g in data.tables["grades"] if g["table"] == "current"]
        out["source"] = cur[0]["source_file"] if cur else ""
    return out


def bands_for(data: Data, lid: str) -> dict:
    r = rules()
    if not data.tsm_periods:
        return {}
    latest = data.tsm_periods[-1]
    previous = data.tsm_periods[-2] if len(data.tsm_periods) > 1 else None
    scores = data.index["scores"][lid]
    peer = next((p for p in data.index["peer_groups"][lid] if p["period"] == latest), None)
    by = {(s["period"], s["kind"], s["item"]): s for s in scores}

    def item(kind: str, key: str) -> dict:
        now = by.get((latest, kind, key))
        old = by.get((previous, kind, key)) if previous else None
        trend = None
        # A move is shown only if both years were scored on the same number of measures: otherwise a change of
        # band could come from different figures being available, not from the landlord.
        if now and old and now["band"] and old["band"] and now["band"] != old["band"] \
                and now["measures_used"] == old["measures_used"]:
            trend = {"direction": "up" if now["band"] > old["band"] else "down", "old_band": old["band"],
                     "old_period": previous}
        return {"band": now["band"] if now else None, "value": now["value"] if now else None,
                "note": now["note"] if now else "", "trend": trend,
                "measures_used": now["measures_used"] if now else None}

    out = {"period": latest, "peer": peer,
           "headline": {"key": r["headline"]["measure"], "label": r["headline"]["label"],
                        **item("headline", r["headline"]["measure"])},
           "pillars": []}
    for key, p in r["pillars"].items():
        measures = []
        for m in p["measures"]:
            s = by.get((latest, "measure", m))
            measures.append({"key": m, "label": r["measures"][m]["label"], "unit": r["measures"][m]["unit"],
                             "value": s["value"] if s else None, "band": s["band"] if s else None,
                             "note": s["note"] if s else ""})
        out["pillars"].append({"key": key, "label": p["label"], **item("pillar", key), "measures": measures})
    tsm_rows = [t for t in data.index["tsm"][lid] if t["period"] == latest]
    cov = [c for c in data.index["tsm_coverage"][lid] if c["period"] == latest]
    out["source"] = tsm_rows[0]["source_file"] if tsm_rows else (cov[0]["source_file"] if cov else "")
    scored = {m for p in r["pillars"].values() for m in p["measures"]} | {r["headline"]["measure"]}
    stock = peer["stock_type"] if peer else "LCRA"
    other = []
    for m, spec in r["measures"].items():
        if m in scored:
            continue
        row = next((t for t in tsm_rows if t["measure"] == m and t["method"] == "all"
                    and t["stock_type"] in (stock, "ALL")), None)
        if row:
            other.append({"key": m, "label": spec["label"], "unit": spec["unit"], "value": row["value"],
                          "status": row["status"]})
    out["other"] = other
    return out


def safety_for(data: Data, lid: str) -> dict:
    r = rules()["building_safety"]
    if not data.tsm_periods:
        return {}
    latest = data.tsm_periods[-1]
    rows = {t["measure"]: t for t in data.index["tsm"][lid] if t["period"] == latest and t["measure"] in r["measures"]}
    if not rows:
        return {}
    checks = []
    for m, label in r["measures"].items():
        t = rows.get(m)
        checks.append({"key": m, "label": label, "value": t["value"] if t else None,
                       "status": t["status"] if t else "not published"})
    applies = [c for c in checks if c["status"] != "undefined"]
    done = all(c["value"] is not None and c["value"] >= r["complete_at"] for c in applies)
    return {"period": latest, "year": "20" + latest[-2:], "all_done": done, "checks": checks,
            "source": next(iter(rows.values()))["source_file"]}


def ombudsman_for(data: Data, lid: str) -> dict:
    rows = data.om_by_profile.get(lid, [])
    latest = data.om_periods[-1] if data.om_periods else None
    reports = defaultdict(dict)
    for r in rows:
        reports[(r["period"], r["name_published"])][r["measure"]] = r["value"]
        reports[(r["period"], r["name_published"])]["_source"] = r["source_file"]
    out = {"period": latest, "reports": [], "earlier": []}
    for (period, name), m in sorted(reports.items()):
        entry = {"period": period, "name": name, **m}
        (out["reports"] if period == latest else out["earlier"]).append(entry)
    return out


def survey_note(data: Data, lid: str) -> dict | None:
    if not data.tsm_periods:
        return None
    peer = next((p for p in data.index["peer_groups"][lid] if p["period"] == data.tsm_periods[-1]), None)
    if peer and peer["survey_method"] and peer["peer_survey_method"] and \
            peer["survey_method"] != peer["peer_survey_method"]:
        return {"method": peer["survey_method"], "peer_method": peer["peer_survey_method"]}
    return None


def areas_for(data: Data, lid: str) -> list[dict]:
    rows = [a for a in data.index["landlord_area"][lid] if a["gss"].startswith("E") and a["rented_homes"]]
    return sorted(rows, key=lambda a: -a["rented_homes"])


def homes_for(data: Data, lid: str) -> dict | None:
    if not data.tsm_periods:
        return None
    latest = data.tsm_periods[-1]
    pop = [s for s in data.index["tsm_survey"][lid]
           if s["period"] == latest and s["population"] and s["stock_type"] in ("LCRA", "COMB")]
    if not pop:
        return None
    return {"homes": sum(s["population"] for s in pop), "period": latest, "source": pop[0]["source_file"]}


def regulator_notes(data: Data, lid: str) -> list[dict]:
    if not data.tsm_periods:
        return []
    latest = data.tsm_periods[-1]
    return [{"note": c["rsh_comment"], "source": c["source_file"]} for c in data.index["tsm_coverage"][lid]
            if c["period"] == latest and c["rsh_comment"]]


def council_link(settings: Settings, gss: str) -> str:
    """The council's page on Where Councils Stand, if that site covers it."""
    import csv

    from landlords.config import STATIC_DIR

    sister = settings.section("sister_sites")
    if not gss or not sister.get("where_councils_stand"):
        return ""
    with open(STATIC_DIR / "councils.csv", newline="", encoding="utf-8") as fh:
        ok = {r["gss"] for r in csv.DictReader(fh) if r.get("modgov_status") == "ok"}
    if gss not in ok:
        return ""
    return sister["where_councils_stand"].format(gss=gss)


def reporting_for(data: Data, lid: str) -> dict | None:
    """Why a landlord has stopped publishing its own tenant survey results, and who publishes them now
    (data_static/reporting.csv, written from the regulator's files)."""
    from landlords.config import STATIC_DIR

    path = STATIC_DIR / "reporting.csv"
    if not path.exists():
        return None
    with open(path, newline="", encoding="utf-8") as fh:
        row = next((r for r in csv.DictReader(fh) if r["landlord_id"] == lid), None)
    if not row:
        return None
    other = data.reg.get(row["reported_by"] or "", {})
    return {"reason": row["reason"], "from_period": row["from_period"],
            "other": {"name": other.get("display_name") or other.get("legal_name"), "slug": other.get("slug")}
            if other else None}


def build_profile(data: Data, lid: str) -> dict:
    reg = data.reg[lid]
    al = data.aliases.get(lid, [])
    successor = data.reg.get(reg.get("successor_id") or "", {})
    p = {
        "id": lid, "name": reg["display_name"] or reg["legal_name"], "legal_name": reg["legal_name"],
        "slug": reg["slug"], "type": reg["type"], "status": reg["status"],
        "successor": {"name": successor.get("display_name") or successor.get("legal_name"),
                      "slug": successor.get("slug"), "date": reg.get("successor_date")} if successor else None,
        "also_known_as": sorted({a["alias"] for a in al if a["kind"] in ALSO_KNOWN}),
        "formerly": sorted({a["alias"] for a in al if a["kind"] == "former"})[:6],
        "homes": homes_for(data, lid), "grade": grade_for(data, lid), "bands": bands_for(data, lid),
        "survey_note": survey_note(data, lid), "safety": safety_for(data, lid),
        "ombudsman": ombudsman_for(data, lid), "areas": areas_for(data, lid),
        "regulator_notes": regulator_notes(data, lid),
        "council_link": council_link(data.settings, reg["gss"]) if reg["type"] == "council" else "",
        "reporting": reporting_for(data, lid),
    }
    used = set()

    def collect(x) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("source", "_source", "source_file") and v:
                    used.add(v)
                elif k == "source_files" and v:
                    used.update(v.split(","))
                else:
                    collect(v)
        elif isinstance(x, list):
            for v in x:
                collect(v)

    collect(p)
    p["sources"] = [{"sha": s, **data.sources.get(s, {})} for s in sorted(used, key=lambda s: (
        data.sources.get(s, {}).get("source", ""), data.sources.get(s, {}).get("period", "")))]
    return p


def build_profiles(settings: Settings) -> list[dict]:
    data = Data(settings)
    return [build_profile(data, lid) for lid, r in sorted(data.reg.items(), key=lambda kv: kv[1]["slug"] or "")
            if r.get("profiled") == "yes"]
