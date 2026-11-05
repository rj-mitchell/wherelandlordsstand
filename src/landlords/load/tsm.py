"""Tenant Satisfaction Measures: the regulator's full data set, every year fetched.

Where the regulator publishes a zip of CSVs (2024/25 on), those are read: they use the regulator's field names
(``TP01_Satisfied_Calc_LCRA``), which are steadier than the xlsx's long headings. Where there is only an xlsx
(2023/24), each heading is turned into the same field name by the measure code it carries ("(TP01)", "(RP02 1)",
"LCRA - … (CH02 1 Numerator)"), so every year goes through the same code. (The 2023/24 data dictionary can't be
used for this: several of its headings and field names don't match the sheets.) Three tables come out:

* ``tsm``: one row per landlord, stock type, measure and survey method. ``value`` is the published figure;
  ``status`` says why there is none ("undefined", "excluded" ...). Management information measures also carry their
  published numerator and denominator.
* ``tsm_survey``: how each landlord ran its survey for each stock type: population, sample, margin of error,
  predominant method and the number of responses by method.
* ``tsm_coverage``: which tables each landlord appears in, and the regulator's exclusions and comments.
"""

from __future__ import annotations

import json
import re

import pyarrow as pa

from landlords.config import Settings
from landlords.load.common import (
    LayoutChanged,
    MissingFile,
    code,
    file_ref,
    has_zip_file,
    parse_value,
    record_sources,
    require,
    sheet_table,
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


# Reading the files ------------------------------------------------------------------------------------------------

_ID = {"Landlord name": "ProviderName", "Landlord code": "ProviderNumber", "Landlord type": "ProviderType"}
_PART = {None: "Calculated_Value", " Numerator": "Numerator", " Denominator": "Denominator"}
_SHEETS = {"Table_coverage": "Table_Coverage", "LCRA_perception": "LCRA_Perception",
           "LCHO_perception": "LCHO_Perception", "COMB_perception": "Combined_Perception",
           "Management_info": "Management_Info", "Perception_not_inc": "Perception_Not_Inc",
           "Man_not_inc": "Man_Info_Not_Inc"}


# 2025/26 renamed the zip's files and many fields: "Combined_Perception" for "COMB_perception"; survey fields end in
# _a, _b, _c for LCRA, LCHO, COMB; and a few gained spaces. They are turned back into the 2024/25 names.
ZIP_NAMES = {"COMB_perception": ("COMB_perception", "Combined_Perception"),
             "Table_coverage": ("Table_coverage",), "Management_info": ("Management_info",)}
_SUFFIX = {"LCRA": "_a", "LCHO": "_b", "COMB": "_c"}


def harmonise(field: str, stock: str | None, table: str) -> str:
    """A CSV field name as the 2024/25 files have it, whichever year's file it comes from."""
    if table == "Table_coverage" and field in ("Landlord name", "Landlord code", "Landlord type"):
        return field.replace(" ", "_")
    if field == "Above 30% SH":
        return "Above_30_SH"
    if stock:
        for new, old in (("MinimumSample", "MinimumSample"), ("Estimated margin", "Estimated_margin"),
                         ("RSH Comments", "RSH_Comments"), ("Predominant method", "Predominant_method")):
            if field == new:
                return f"{old}_{stock}"
        if field.endswith(_SUFFIX[stock]) and not field.endswith(f"_{stock}"):
            return field[: -len(_SUFFIX[stock])] + f"_{stock}"
    return field


def field_name(heading: str, stock: str | None) -> str:
    """The regulator's field name for an xlsx column heading. ``stock`` is LCRA, LCHO or COMB on a perception
    sheet, None on the management sheet. Headings that aren't needed are returned unchanged."""
    h = re.sub(r"\s+", " ", str(heading).replace("\xa0", " ")).strip()
    if h in _ID:
        return _ID[h]
    for start, name in (("Landlord TSM Publication URL", "Publication_URL"), ("Landlord group size", "Group size"),
                        ("Landlord predominant region", "Predominant region"),
                        ("LCRA above 30% supported", "Above_30_SH")):
        if h.startswith(start):
            return name
    if h == "Any additional notes from RSH":
        return f"RSH_Comments_{stock}" if stock else "RSH Comments"
    if stock:
        for start, name in (("Relevant tenant population size", "Relevant_ten_pop_size"),
                            ("Required minimum sample size", "MinimumSample"),
                            ("Total sample size achieved", "Total_sample_size"),
                            ("Estimated margin of error", "Estimated_margin"),
                            ("Sample or census", "Census_or_Sample"),
                            ("Predominant collection method", "Predominant_method"),
                            ("External contractor's name", "External_contractor_name")):
            if h.startswith(start):
                return f"{name}_{stock}"
        if m := re.fullmatch(r"Number of responses by method - (\w+?)", h):
            return f"Responses_{m.group(1)}_{stock}"
        if m := re.search(r"\(TP01\) for each survey method - ([A-Za-z]+?)\d*$", h):
            return f"TP01_Satisfied_{m.group(1)}_{stock}"
        if m := re.fullmatch(r"Proportion of respondents who report .*\((TP\d\d)\)\d*", h):
            return f"{m.group(1)}_Satisfied_Calc_{stock}"
        return h
    if m := re.fullmatch(r"(LCRA|LCHO|Combined) - .*\((CH0[12]) ([12])( Numerator| Denominator)?\)\d*", h):
        st = "COMB" if m.group(1) == "Combined" else m.group(1)
        return f"{m.group(2)}_{m.group(3)}_{_PART[m.group(4)]}_{st}"
    if m := re.search(r"\(((?:BS|RP|NM)\d\d)(?: (\d))?( Numerator| Denominator)?\)\d*$", h):
        base = m.group(1) + (f"_{m.group(2)}" if m.group(2) else "")
        return f"{base}_{_PART[m.group(3)]}"
    if h.startswith("What is your (maximum) target timescale for non-emergency"):
        return "RP02_Max_Timescale_Non_Emer"
    if h.startswith("What is your (maximum) target timescale for emergency"):
        return "RP02_Max_Timescale_Emer"
    return h


def xlsx_tables(path: str):
    """A reader over the xlsx with the same interface as ``zip_csv``: (header, rows) for a table, by its CSV name."""
    from python_calamine import CalamineWorkbook

    sheets = CalamineWorkbook.from_path(path).sheet_names

    def read(name: str) -> tuple[list[str], list[dict]]:
        suffix = _SHEETS[name]
        found = [sh for sh in sheets if sh.lower().endswith(suffix.lower())]
        if len(found) != 1:
            raise LayoutChanged(f"TSM xlsx: expected one sheet ending {suffix!r}, found {found}")
        header, rows = sheet_table(path, found[0], "Landlord name")
        if name == "Table_coverage":
            fields = [h.replace(" ", "_") if h in ("Landlord name", "Landlord code", "Landlord type") else h
                      for h in header]
        elif name in ("Perception_not_inc", "Man_not_inc"):
            fields = header
        else:
            stock = {"LCRA_perception": "LCRA", "LCHO_perception": "LCHO", "COMB_perception": "COMB"}.get(name)
            fields = [field_name(h, stock) for h in header]
        out = [dict(zip(fields, r, strict=False)) for r in rows]
        # 2023/24 puts its notes below each table, so keep only rows that carry a landlord code.
        key = next(k for k in ("ProviderNumber", "Landlord_code", "Landlord code") if k in fields)
        return fields, [r for r in out if code(r.get(key, ""))]

    return read


def load(settings: Settings) -> dict[str, int]:
    """Every TSM year fetched, into one set of tables."""
    from landlords.fetch import read_index

    periods = sorted({r["period"] for r in read_index(settings, "tsm") if r["role"] == "full-data"})
    tsm, survey, coverage, notes = [], [], [], []
    for period in periods:
        t, s, c, note = load_period(settings, period)
        tsm += t
        survey += s
        coverage += c
        notes.append(note)
    write_table(settings, "tsm", tsm, TSM_SCHEMA)
    write_table(settings, "tsm_survey", survey, SURVEY_SCHEMA)
    write_table(settings, "tsm_coverage", coverage, COVERAGE_SCHEMA)
    record_sources(settings, notes)
    return {"periods": len(periods), "tsm": len(tsm), "tsm_survey": len(survey), "tsm_coverage": len(coverage)}


def load_period(settings: Settings, period: str) -> tuple[list, list, list, dict]:
    try:
        note = source_file(settings, "tsm", "full-data", period, ext="zip")
        path = note["path"]

        def read(name: str):
            header, rows = zip_csv(path, ZIP_NAMES.get(name, name))
            stock = {"LCRA_perception": "LCRA", "LCHO_perception": "LCHO", "COMB_perception": "COMB"}.get(name)
            fields = [harmonise(h, stock, name) for h in header]
            renamed = dict(zip(header, fields, strict=True))
            return fields, [{renamed.get(k, k): v for k, v in r.items()} for r in rows]

        def has(name: str) -> bool:
            return has_zip_file(path, name)
    except MissingFile:
        note = source_file(settings, "tsm", "full-data", period, ext="xlsx")
        read = xlsx_tables(note["path"])

        def has(name: str) -> bool:
            return True
    ref = file_ref(note)
    tsm, survey, coverage = [], [], {}

    # Coverage: who is in which table ----------------------------------------------------------------------------
    header, rows = read("Table_coverage")
    cov_cols = {"lcra": "LCRA_Perception", "lcho": "LCHO_Perception", "combined": "Combined_Perception",
                "management_info": "Management _Info", "perception_excluded": "Perception_Not_Inc",
                "management_excluded": "Man_Info_Not_Inc"}
    resolved = {}
    for key, suffix in cov_cols.items():
        found = [h for h in header if h.endswith(suffix)]
        if not found and key.endswith("_excluded"):
            continue  # 2025/26 has no exclusion columns: exclusions are marked [E] in the tables instead
        if len(found) != 1:
            raise LayoutChanged(f"TSM coverage: no single column ending {suffix!r} in {header}")
        resolved[key] = found[0]
    require(header, ["Landlord_name", "Landlord_code", "Landlord_type"], "TSM coverage")
    for r in rows:
        lid = code(r["Landlord_code"])
        coverage[lid] = {"landlord_id": lid, "name_published": text(r["Landlord_name"]),
                         "landlord_type": text(r["Landlord_type"]), "period": period,
                         "perception_excluded": False, "management_excluded": False,
                         **{k: _yes(r[c]) for k, c in resolved.items()},
                         "group_size": "", "region": "", "above_30pc_supported": "", "publication_url": "",
                         "rsh_comment": "", "source_file": ref["source_file"]}

    # Perception: one file per stock type --------------------------------------------------------------------------
    for stock, name in STOCK_TYPES.items():
        header, rows = read(name)
        method_col = next((h for h in header if h.lower().startswith("predominant_method")), None)
        need = ["ProviderName", "ProviderNumber", f"TP01_Satisfied_Calc_{stock}", f"Total_sample_size_{stock}",
                f"Relevant_ten_pop_size_{stock}"]
        require(header, need, f"TSM {stock} perception")
        if not method_col:
            raise LayoutChanged(f"TSM {stock} perception: no predominant method column")
        for r in rows:
            lid = code(r["ProviderNumber"])
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
    header, rows = read("Management_info")
    require(header, ["ProviderName", "ProviderNumber", "RSH Comments"]
            + [f"{m}_Calculated_Value" for m in MI_LANDLORD]
            + [f"{m}_Calculated_Value_{s}" for m in MI_BY_STOCK for s in ("LCRA", "LCHO", "COMB")],
            "TSM management information")
    for r in rows:
        lid = code(r["ProviderNumber"])
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
        if not has(name):
            continue  # not published separately from 2025/26: see the [E] markers and the regulator's comments
        header, rows = read(name)
        require(header, ["Landlord code", "Notes from RSH following TSM review"], f"TSM {name}")
        flag = "perception_excluded" if name == "Perception_not_inc" else "management_excluded"
        for r in rows:
            lid = code(r["Landlord code"])
            # A landlord can be on these lists without being in the coverage table (Guildford, 2023/24: "Did not
            # submit TSM data"), so it is added, with no results, to keep the regulator's note.
            c = coverage.setdefault(lid, {
                "landlord_id": lid, "name_published": text(r.get("Landlord name", "")),
                "landlord_type": "", "period": period, "lcra": False, "lcho": False, "combined": False,
                "management_info": False, "perception_excluded": False, "management_excluded": False,
                "group_size": "", "region": "", "above_30pc_supported": "", "publication_url": "",
                "rsh_comment": "", "source_file": ref["source_file"]})
            c[flag] = True
            note_text = text(r["Notes from RSH following TSM review"])
            existing = c.get("rsh_comment") or ""
            c["rsh_comment"] = existing if note_text in existing else (existing + " " + note_text).strip()

    return tsm, survey, list(coverage.values()), note
