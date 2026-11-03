"""The Housing Ombudsman's landlord tables: ``ombudsman``.

Table 1 of the Ombudsman's yearly "tables for landlords with individual performance reports": one row per landlord
with five or more findings in the year (less any withheld to protect residents' privacy), giving determinations,
findings by outcome, orders, recommendations, Complaint Handling Failure Orders, compensation and the
maladministration rate.

The tables name landlords but give no regulator code, so each name is matched to a landlord through
``data_static/aliases.csv`` or the register (``register.Resolver``). A name with no alias is kept with an empty ``landlord_id`` and
reported by `landlords check`.
"""

from __future__ import annotations

import pyarrow as pa

from landlords.config import Settings
from landlords.load.common import (
    file_ref,
    parse_value,
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
    ("period", pa.string()),
    ("size_band", pa.string()),         # the Ombudsman's band, from homes on 31 March of the year before
    ("landlord_type", pa.string()),     # Housing Association, Local Authority / ALMO or TMO, Other
    ("measure", pa.string()),
    ("value", pa.float64()),
    ("source_file", pa.string()),
])

# Our short names for Table 1's columns.
MEASURES = {
    "determinations": "Determinations",
    "findings": "Findings",
    "maladministration_findings": "Maladministration Findings",
    "orders": "Orders Made",
    "recommendations": "Recommendations",
    "chfos": "CHFOs",
    "compensation": "Compensation",
    "maladministration_rate": "Maladministration Rate",
    "determinations_all": "Determinations including those entirely Outside Jurisdiction or Withdrawn",
    "determinations_outside_jurisdiction": "Determinations entirely Outside Jurisdiction",
    "determinations_withdrawn": "Determinations entirely Withdrawn",
    "severe_maladministration": "Severe Maladministration",
    "maladministration": "Maladministration",
    "service_failure": "Service failure",
    "redress": "Redress",
    "no_maladministration": "No maladministration",
    "mediation": "Mediation",
    "outside_jurisdiction": "Outside Jurisdiction",
    "findings_in_jurisdiction": "Total findings excluding Outside Jurisdiction and Withdrawn",
}


def load(settings: Settings, period: str = "2025-26") -> dict[str, int]:
    from landlords.register import Resolver

    note = source_file(settings, "ombudsman", "landlord-tables", period)
    header, rows = sheet_table(note["path"], "Table 1", "Landlord name")
    require(header, ["Landlord name", "Size band", "Landlord type", *MEASURES.values()], "Ombudsman Table 1")
    resolver = Resolver()
    out = []
    for r in rows:
        d = dict(zip(header, r, strict=False))
        name = text(d["Landlord name"])
        lid, _how = resolver.resolve(name)
        for measure, col in MEASURES.items():
            value, status = parse_value(d[col])
            if status == "value":
                out.append({"landlord_id": lid, "name_published": name, "size_band": text(d["Size band"]),
                            "landlord_type": text(d["Landlord type"]), "measure": measure, "value": value,
                            **file_ref(note)})
    write_table(settings, "ombudsman", out, SCHEMA)
    record_sources(settings, [note])
    return {"ombudsman": len(out), "landlords": len({r["name_published"] for r in out}),
            "unmatched": len({r["name_published"] for r in out if not r["landlord_id"]})}
