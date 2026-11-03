"""From registered companies to the landlords we profile: ``owners`` and ``landlord_area``.

TSMs are submitted by the landlord that owns the homes, which for a group is often the group's parent, while the
stock return and the Ombudsman report on each registered company. So every company is linked to the profiled
landlord it belongs to: itself if it is profiled, otherwise its nearest registered parent that is (``owners``).

``landlord_area`` adds up, for each profiled landlord and council area, the homes its companies own there, as
published in the stock returns. This is the only arithmetic done on a publisher's figures in phase 1, and it is
described on the method page (docs/DATA.md, "Homes by area").
"""

from __future__ import annotations

from collections import defaultdict

import pyarrow as pa

from landlords.config import Settings
from landlords.load.common import read_table, write_table
from landlords.load.stock import LCR_OWNED
from landlords.register import landlords

OWNERS = pa.schema([
    ("landlord_id", pa.string()),   # a registered company
    ("profile_id", pa.string()),    # the profiled landlord it belongs to; empty if none
    ("how", pa.string()),           # "itself", "parent", or "" if not profiled
])

AREA = pa.schema([
    ("profile_id", pa.string()),
    ("gss", pa.string()),
    ("area_name", pa.string()),
    ("period", pa.string()),
    ("rented_homes", pa.float64()),           # low cost rental owned (social and affordable rent, supported, older people)
    ("shared_ownership_homes", pa.float64()), # low cost home ownership owned
    ("companies", pa.string()),               # the registered companies counted, comma separated
    ("basis", pa.string()),                   # "by area" or "council total"
    ("source_files", pa.string()),
])

COUNCIL_RENTED = ("social_rent_owned", "affordable_rent_owned")


def owner_map(parents: dict[str, str], profiled: set[str], ids: set[str]) -> dict[str, tuple[str, str]]:
    out = {}
    for lid in ids:
        cur, seen, how = lid, set(), "itself"
        while cur and cur not in seen:
            if cur in profiled:
                out[lid] = (cur, how)
                break
            seen.add(cur)
            cur, how = parents.get(cur, ""), "parent"
        else:
            out[lid] = ("", "")
    return out


def build(settings: Settings) -> dict[str, int]:
    reg = landlords()
    profiled = {lid for lid, r in reg.items() if r.get("profiled") == "yes"}
    parents = {g["landlord_id"]: g["parent_id"] for g in read_table(settings, "groups") if g["parent_id"]}
    owners = owner_map(parents, profiled, set(reg))
    write_table(settings, "owners", [{"landlord_id": k, "profile_id": v[0], "how": v[1]} for k, v in owners.items()],
                OWNERS)

    acc: dict[tuple[str, str], dict] = {}
    for r in read_table(settings, "stock_area"):
        pid = owners.get(r["landlord_id"], ("", ""))[0]
        if not pid or not r["gss"]:
            continue
        a = acc.setdefault((pid, r["gss"]), {"profile_id": pid, "gss": r["gss"], "area_name": r["area_name"],
                                             "period": r["period"], "rented_homes": 0.0,
                                             "shared_ownership_homes": 0.0, "companies": set(),
                                             "basis": r["basis"], "source_files": set()})
        if r["measure"] in LCR_OWNED or r["measure"] in COUNCIL_RENTED:
            a["rented_homes"] += r["value"]
        elif r["measure"] == "lcho_owned":
            a["shared_ownership_homes"] += r["value"]
        else:
            continue
        a["companies"].add(r["landlord_id"])
        a["source_files"].add(r["source_file"])
    rows = []
    for a in acc.values():
        if a["rented_homes"] or a["shared_ownership_homes"]:
            rows.append({**a, "companies": ",".join(sorted(a["companies"])),
                         "source_files": ",".join(sorted(a["source_files"]))})
    write_table(settings, "landlord_area", rows, AREA)
    return {"owners": len(owners), "landlord_area": len(rows),
            "profiled_with_homes": len({r["profile_id"] for r in rows})}


def rolled_up_totals(settings: Settings) -> dict[str, float]:
    """Rented homes in England for each profiled landlord, from ``landlord_area``."""
    total: dict[str, float] = defaultdict(float)
    for r in read_table(settings, "landlord_area"):
        if r["gss"].startswith("E"):
            total[r["profile_id"]] += r["rented_homes"]
    return dict(total)
