"""The register of providers, and how providers are grouped: ``providers`` and ``groups``.

* ``providers``: every body on the regulator's register (updated monthly), with its designation (local authority,
  non-profit or profit), plus, for councils, the GSS code of their area from the Local Authority Data Return.
* ``groups``: each private provider's registered parent, from the Statistical Data Return's group structure table.
  TSMs are often submitted by a group's parent while its homes are owned by its subsidiaries, so homes are added up
  through this table.
"""

from __future__ import annotations

import pyarrow as pa

from landlords.config import Settings
from landlords.load.common import (
    as_date,
    code,
    record_sources,
    require,
    sheet_table,
    source_file,
    text,
    write_table,
)

PROVIDERS = pa.schema([
    ("landlord_id", pa.string()),
    ("name", pa.string()),
    ("registration_date", pa.date32()),
    ("designation", pa.string()),       # Local authority, Non-profit, Profit
    ("corporate_form", pa.string()),
    ("gss", pa.string()),               # councils: their area's GSS code (LADR)
    ("region", pa.string()),            # councils: their region (LADR)
    ("source_file", pa.string()),
])

GROUPS = pa.schema([
    ("landlord_id", pa.string()),
    ("name", pa.string()),
    ("size", pa.string()),              # Large (1,000+ homes) or Small, as the SDR has it
    ("in_group", pa.bool_()),
    ("is_group_parent", pa.bool_()),
    ("parent_id", pa.string()),         # the registered parent's code, if any
    ("parent_name", pa.string()),
    ("source_file", pa.string()),
])


def load(settings: Settings) -> dict[str, int]:
    reg = source_file(settings, "providers", "register")
    prp = source_file(settings, "stock", "prp-data")
    larp = source_file(settings, "stock", "larp-data")

    from python_calamine import CalamineWorkbook

    first = CalamineWorkbook.from_path(reg["path"]).sheet_names[0]
    header, rows = sheet_table(reg["path"], first, "Organisation name")
    require(header, ["Organisation name", "Registration number", "Registration date", "Designation",
                     "Corporate form"], "providers list")
    header_l, rows_l = sheet_table(larp["path"], "LADR26_Entity_Level_Information", "LARP Name")
    require(header_l, ["LARP Name", "LARP Code", "Local Authority area (GSS) code", "Region"], "LADR entities")
    councils = {code(r[header_l.index("LARP Code")]): r for r in rows_l}

    providers = []
    for r in rows:
        d = dict(zip(header, r, strict=False))
        lid = code(d["Registration number"])
        c = councils.get(lid)
        providers.append({
            "landlord_id": lid, "name": text(d["Organisation name"]),
            "registration_date": as_date(d["Registration date"]), "designation": text(d["Designation"]),
            "corporate_form": text(d["Corporate form"]),
            "gss": text(c[header_l.index("Local Authority area (GSS) code")]) if c else "",
            "region": text(c[header_l.index("Region")]) if c else "", "source_file": reg["sha256"],
        })

    header, rows = sheet_table(prp["path"], "SDR26_Group_Structure", "PRP name")
    need = ["PRP name", "PRP registration number", "Size of organisation", "Does organisation belong to group structure",
            "Is organisation group parent", "Registered Parent's code", "Registered Parent's name"]
    require(header, need, "SDR group structure")
    groups: dict[str, dict] = {}
    for r in rows:
        d = dict(zip(header, r, strict=False))
        lid = code(d["PRP registration number"])
        g = groups.setdefault(lid, {"landlord_id": lid, "name": text(d["PRP name"]),
                                    "size": text(d["Size of organisation"]),
                                    "in_group": text(d["Does organisation belong to group structure"]) == "Yes",
                                    "is_group_parent": text(d["Is organisation group parent"]) == "Yes",
                                    "parent_id": "", "parent_name": "", "source_file": prp["sha256"]})
        parent = code(d["Registered Parent's code"])
        if parent and parent not in ("[x]",):
            g["parent_id"], g["parent_name"] = parent, text(d["Registered Parent's name"])

    write_table(settings, "providers", providers, PROVIDERS)
    write_table(settings, "groups", list(groups.values()), GROUPS)
    record_sources(settings, [reg, prp, larp])
    return {"providers": len(providers), "groups": len(groups)}
