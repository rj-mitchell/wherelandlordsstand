"""Homes by landlord and council area: ``stock_area``.

* Housing associations and for-profit providers (the Statistical Data Return): each registered provider's homes in
  each local authority area, on 31 March. The figures are per registered company, not per group.
* Councils (the Local Authority Data Return): each council's homes in total. The return counts the homes a council
  owns "regardless of where the stock is geographically located", so a council's homes are placed in its own area,
  and ``basis`` says so.

Values are kept as published, one row per landlord, area and measure. Zero and blank cells are left out.
"""

from __future__ import annotations

import pyarrow as pa

from landlords.config import Settings
from landlords.load.common import (
    code,
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
    ("landlord_id", pa.string()),       # the registered company (not the group)
    ("name_published", pa.string()),
    ("period", pa.string()),
    ("gss", pa.string()),               # local authority area; E... in England
    ("area_name", pa.string()),
    ("basis", pa.string()),             # "by area" (SDR) or "council total" (LADR)
    ("measure", pa.string()),
    ("value", pa.float64()),
    ("source_file", pa.string()),
])

# Our short names for the SDR's columns: low cost rental (LCR) owned and managed, and shared ownership (LCHO).
PRP_COLUMNS = {
    "lcr_owned_general_needs": "General needs - Self-contained - Owned low cost rental accommodation by Local Authority area",
    "lcr_owned_general_needs_bedspaces": "General needs - Bedspace - Owned low cost rental accommodation by Local Authority area",
    "lcr_owned_supported": "Supported housing - Owned low cost rental accommodation by Local Authority area",
    "lcr_owned_older_people": "Housing for older people - Owned low cost rental accommodation by Local Authority area",
    "lcr_managed_general_needs": "General needs - Self-contained - Managed low cost rental accommodation by Local Authority area",
    "lcr_managed_general_needs_bedspaces": "General needs - Bedspace - Managed low cost rental accommodation by Local Authority area",
    "lcr_managed_supported": "Supported housing - Managed low cost rental accommodation by Local Authority area",
    "lcr_managed_older_people": "Housing for older people - Managed low cost rental accommodation by Local Authority area",
    "lcho_owned": "Owned - where the purchaser has not acquired 100% of the equity",
    "lcho_managed": "Managed only - where the purchaser has not acquired 100% of the equity",
}

LARP_COLUMNS = {
    "social_rent_owned": "Low cost rental - Total - All",
    "affordable_rent_owned": "Affordable Rent - Total - All",
    "lcho_owned": "All - Total - LCHO",
    "all_owned": "All - Total - All",
    "all_owned_excluding_pfi_and_lcho": "All - Total (excluding PFI and LCHO) - All",
}

# Measures counted as "homes" for rented stock (LCR owned) on area pages; see docs/DATA.md.
LCR_OWNED = [k for k in PRP_COLUMNS if k.startswith("lcr_owned")]


def load(settings: Settings, period: str = "2025/26") -> dict[str, int]:
    prp = source_file(settings, "stock", "prp-data", period)
    larp = source_file(settings, "stock", "larp-data", period)
    out = []

    header, rows = sheet_table(prp["path"], "SDR26_STOCK_INFORMATION_BY_LA", "PRP name")
    require(header, ["PRP name", "PRP registration number", "Local Authority name", "LA code",
                     *PRP_COLUMNS.values()], "SDR stock by local authority")
    for r in rows:
        d = dict(zip(header, r, strict=False))
        gss = text(d["LA code"])
        for measure, col in PRP_COLUMNS.items():
            value, status = parse_value(d[col])
            if status == "value" and value:
                out.append({"landlord_id": code(d["PRP registration number"]), "name_published": text(d["PRP name"]),
                            "gss": "" if gss == "[x]" else gss, "area_name": text(d["Local Authority name"]),
                            "basis": "by area", "measure": measure, "value": value, **file_ref(prp)})

    header, rows = sheet_table(larp["path"], "LADR26_Stock_Information", "LARP Name")
    require(header, ["LARP Name", "LARP Code", "Local Authority area name", "Local Authority area (GSS) code",
                     *LARP_COLUMNS.values()], "LADR stock")
    for r in rows:
        d = dict(zip(header, r, strict=False))
        for measure, col in LARP_COLUMNS.items():
            value, status = parse_value(d[col])
            if status == "value" and value:
                out.append({"landlord_id": code(d["LARP Code"]), "name_published": text(d["LARP Name"]),
                            "gss": text(d["Local Authority area (GSS) code"]),
                            "area_name": text(d["Local Authority area name"]), "basis": "council total",
                            "measure": measure, "value": value, **file_ref(larp)})

    write_table(settings, "stock_area", out, SCHEMA)
    record_sources(settings, [prp, larp])
    return {"stock_area": len(out)}
