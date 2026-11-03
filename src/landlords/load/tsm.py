"""Tenant Satisfaction Measures: the regulator's full data set, read from the CSVs in its zip.

The zip's CSVs use the regulator's field names (``TP01_Satisfied_Calc_LCRA``), which are steadier than the xlsx's
long headings. Three tables come out:

* ``tsm``: one row per landlord, stock type, measure and survey method. ``value`` is the published figure;
  ``status`` says why there is none ("undefined", "excluded" ...). Management information measures also carry their
  published numerator and denominator.
* ``tsm_survey``: how each landlord ran its survey for each stock type: population, sample, margin of error,
  predominant method and the number of responses by method.
* ``tsm_coverage``: which tables each landlord appears in, and the regulator's exclusions and comments.
"""

from __future__ import annotations

import json

import pyarrow as pa

from landlords.config import Settings
from landlords.load.common import (
    LayoutChanged,
    file_ref,
    parse_value,
    record_sources,
    require,
    source_file,
    text,
    write_table,
    zip_csv,
)

PERCEPTION = [f"TP{i:02d}" for i in range(1, 13)]
METHODS = {"Telephone": "telephone", "Internet": "internet", "FacetoFace": "face to face", "Postal": "postal",
           "SMS": "sms", "Other": "other"}
STOCK_TYPES = {"LCRA": "LCRA_perception", "LCHO": "LCHO_perception", "COMB": "COMB_perception"}

# Management information. Building safety and repairs are reported once per landlord; complaints by stock type.
MI_LANDLORD = ["BS01", "BS02", "BS03", "BS04", "BS05", "RP01", "RP02_1", "RP02_2", "NM01_1", "NM01_2"]
MI_BY_STOCK = ["CH01_1", "CH01_2", "CH02_1", "CH02_2"]

TSM_SCHEMA = pa.schema([
    ("landlord_id", pa.string()),
    ("name_published", pa.string()),
    ("period", pa.string()),
    ("stock_type", pa.string()),       # LCRA (rented), LCHO (shared ownership), COMB (combined), ALL
    ("measure", pa.string()),          # TP01 ... TP12, BS01 ... BS05, RP01, RP02_1, RP02_2, CH01_1 ..., NM01_1 ...
    ("method", pa.string()),           # survey method for TP01 by method; "all" otherwise
    ("value", pa.float64()),
    ("status", pa.string()),           # value, undefined, excluded, suppressed, not required, blank, empty
    ("numerator", pa.float64()),
    ("denominator", pa.float64()),
    ("source_file", pa.string()),
])

SURVEY_SCHEMA = pa.schema([
    ("landlord_id", pa.string()),
    ("period", pa.string()),
    ("stock_type", pa.string()),
    ("population", pa.float64()),
    ("minimum_sample", pa.float64()),
    ("sample", pa.float64()),
    ("margin_of_error", pa.float64()),
    ("census_or_sample", pa.string()),
    ("predominant_method", pa.string()),
    ("responses", pa.string()),        # JSON: responses by method, as published
    ("external_contractor", pa.string()),
    ("rsh_comment", pa.string()),
    ("source_file", pa.string()),
])

COVERAGE_SCHEMA = pa.schema([
    ("landlord_id", pa.string()),
    ("name_published", pa.string()),
    ("landlord_type", pa.string()),    # PRP or LA, as published
    ("period", pa.string()),
    ("group_size", pa.string()),       # the regulator's band: <5,000, 5,000-40,000, >40,000
    ("region", pa.string()),
    ("above_30pc_supported", pa.string()),
    ("publication_url", pa.string()),
    ("lcra", pa.bool_()),
    ("lcho", pa.bool_()),
    ("combined", pa.bool_()),
    ("management_info", pa.bool_()),
    ("perception_excluded", pa.bool_()),
    ("management_excluded", pa.bool_()),
    ("rsh_comment", pa.string()),
    ("source_file", pa.string()),
])


def _yes(v: str) -> bool:
    return text(v).lower() == "yes"


def _num(v: str) -> float | None:
    return parse_value(v)[0]


def load(settings: Settings, period: str = "2024/25") -> dict[str, int]:
    note = source_file(settings, "tsm", "full-data", period, ext="zip")
    path, ref = note["path"], file_ref(note)
    tsm, survey, coverage = [], [], {}

    # Coverage: who is in which table ----------------------------------------------------------------------------
    header, rows = zip_csv(path, "Table_coverage")
    cov_cols = {"lcra": "LCRA_Perception", "lcho": "LCHO_Perception", "combined": "Combined_Perception",
                "management_info": "Management _Info", "perception_excluded": "Perception_Not_Inc",
                "management_excluded": "Man_Info_Not_Inc"}
    resolved = {}
    for key, suffix in cov_cols.items():
        found = [h for h in header if h.endswith(suffix)]
        if len(found) != 1:
            raise LayoutChanged(f"TSM coverage: no single column ending {suffix!r} in {header}")
        resolved[key] = found[0]
    require(header, ["Landlord_name", "Landlord_code", "Landlord_type"], "TSM coverage")
    for r in rows:
        lid = text(r["Landlord_code"])
        coverage[lid] = {"landlord_id": lid, "name_published": text(r["Landlord_name"]),
                         "landlord_type": text(r["Landlord_type"]), "period": period,
                         **{k: _yes(r[c]) for k, c in resolved.items()},
                         "group_size": "", "region": "", "above_30pc_supported": "", "publication_url": "",
                         "rsh_comment": "", "source_file": ref["source_file"]}

    # Perception: one file per stock type --------------------------------------------------------------------------
    for stock, name in STOCK_TYPES.items():
        header, rows = zip_csv(path, name)
        method_col = next((h for h in header if h.lower().startswith("predominant_method")), None)
        need = ["ProviderName", "ProviderNumber", f"TP01_Satisfied_Calc_{stock}", f"Total_sample_size_{stock}",
                f"Relevant_ten_pop_size_{stock}"]
        require(header, need, f"TSM {stock} perception")
        if not method_col:
            raise LayoutChanged(f"TSM {stock} perception: no predominant method column")
        for r in rows:
            lid = text(r["ProviderNumber"])
            c = coverage.setdefault(lid, {"landlord_id": lid, "name_published": text(r["ProviderName"]),
                                          "period": period, "source_file": ref["source_file"]})
            c.update({"group_size": text(r.get("Group size", "")), "region": text(r.get("Predominant region", "")),
                      "above_30pc_supported": text(r.get("Above_30_SH", "")),
                      "publication_url": text(r.get("Publication_URL", ""))})
            base = {"landlord_id": lid, "name_published": text(r["ProviderName"]), "period": period,
                    "stock_type": stock, "numerator": None, "denominator": None, "source_file": ref["source_file"]}
            for m in PERCEPTION:
                col = f"{m}_Satisfied_Calc_{stock}"
                if col in r:  # shared owners aren't asked about repairs (TP02-TP04)
                    value, status = parse_value(r[col])
                    tsm.append({**base, "measure": m, "method": "all", "value": value, "status": status})
            for key, label in METHODS.items():
                col = f"TP01_Satisfied_{key}_{stock}"
                if col in r:
                    value, status = parse_value(r[col])
                    tsm.append({**base, "measure": "TP01", "method": label, "value": value, "status": status})
            responses = {label: _num(r.get(f"Responses_{key}_{stock}", "")) for key, label in METHODS.items()}
            survey.append({
                "landlord_id": lid, "period": period, "stock_type": stock,
                "population": _num(r[f"Relevant_ten_pop_size_{stock}"]),
                "minimum_sample": _num(r.get(f"MinimumSample_{stock}", "")),
                "sample": _num(r[f"Total_sample_size_{stock}"]),
                "margin_of_error": _num(r.get(f"Estimated_margin_{stock}", "")),
                "census_or_sample": text(r.get(f"Census_or_Sample_{stock}", "")),
                "predominant_method": text(r[method_col]),
                "responses": json.dumps(responses),
                "external_contractor": text(r.get(f"External_contractor_name_{stock}", "")),
                "rsh_comment": text(r.get(f"RSH_Comments_{stock}", "")).replace("[X]", ""),
                "source_file": ref["source_file"],
            })

    # Management information -----------------------------------------------------------------------------------------
    header, rows = zip_csv(path, "Management_info")
    require(header, ["ProviderName", "ProviderNumber", "RSH Comments"]
            + [f"{m}_Calculated_Value" for m in MI_LANDLORD]
            + [f"{m}_Calculated_Value_{s}" for m in MI_BY_STOCK for s in ("LCRA", "LCHO", "COMB")],
            "TSM management information")
    for r in rows:
        lid = text(r["ProviderNumber"])
        comment = text(r["RSH Comments"]).replace("[X]", "")
        if lid in coverage:
            c = coverage[lid]
            if comment:
                c["rsh_comment"] = comment
            for key, col in (("group_size", "Group size"), ("region", "Predominant region"),
                             ("above_30pc_supported", "Above_30_SH"), ("publication_url", "Publication_URL")):
                if not c.get(key):
                    c[key] = text(r.get(col, ""))
        base = {"landlord_id": lid, "name_published": text(r["ProviderName"]), "period": period, "method": "all",
                "source_file": ref["source_file"]}
        for m in MI_LANDLORD:
            value, status = parse_value(r[f"{m}_Calculated_Value"])
            tsm.append({**base, "stock_type": "ALL", "measure": m, "value": value, "status": status,
                        "numerator": _num(r.get(f"{m}_Numerator", "")),
                        "denominator": _num(r.get(f"{m}_Denominator", ""))})
        for m in MI_BY_STOCK:
            for s in ("LCRA", "LCHO", "COMB"):
                value, status = parse_value(r[f"{m}_Calculated_Value_{s}"])
                tsm.append({**base, "stock_type": s, "measure": m, "value": value, "status": status,
                            "numerator": _num(r.get(f"{m}_Numerator_{s}", "")),
                            "denominator": _num(r.get(f"{m}_Denominator_{s}", ""))})

    # The regulator's exclusion lists ---------------------------------------------------------------------------------
    for name in ("Perception_not_inc", "Man_not_inc"):
        header, rows = zip_csv(path, name)
        require(header, ["Landlord code", "Notes from RSH following TSM review"], f"TSM {name}")
        for r in rows:
            lid = text(r["Landlord code"])
            if lid in coverage:
                note_text = text(r["Notes from RSH following TSM review"])
                existing = coverage[lid].get("rsh_comment") or ""
                coverage[lid]["rsh_comment"] = (existing + " " + note_text).strip() if note_text not in existing \
                    else existing

    write_table(settings, "tsm", tsm, TSM_SCHEMA)
    write_table(settings, "tsm_survey", survey, SURVEY_SCHEMA)
    write_table(settings, "tsm_coverage", list(coverage.values()), COVERAGE_SCHEMA)
    record_sources(settings, [note])
    return {"tsm": len(tsm), "tsm_survey": len(survey), "tsm_coverage": len(coverage)}
