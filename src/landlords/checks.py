"""The checks behind `landlords check`. The gate for phase 1 is that every row is matched to a landlord.

Each check is "ok", "warn" (reported, does not fail) or "fail". The full report, with the rows behind each check, is
written to ``data/staging/check-report.json``; the change report to ``data/staging/change-report.json``.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import UTC, date, datetime

from landlords import area
from landlords.config import Settings, load_toml
from landlords.load.common import read_table
from landlords.register import ALIAS_KINDS, PUBLISHED_SLUGS, aliases, ambiguous_names, landlords, read_lines

PERCENT_MEASURES = ("TP", "BS", "RP", "CH02")


class Report:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, name: str, level: str, detail: str, rows: list | None = None) -> None:
        self.checks.append({"name": name, "level": level, "ok": level != "fail", "detail": detail,
                            "rows": (rows or [])[:200]})


def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol + 1e-9


def check_matched(settings: Settings, rep: Report) -> None:
    reg = landlords()
    for table in ("tsm", "tsm_coverage", "grades", "stock_area", "ombudsman", "providers"):
        rows = read_table(settings, table)
        missing = sorted({(r["landlord_id"], r.get("name_published") or r.get("name", "")) for r in rows
                          if r["landlord_id"] not in reg})
        rep.add(f"every {table} row has a landlord", "fail" if missing else "ok",
                f"{len(rows)} rows; {len(missing)} names without a landlord" +
                (": " + "; ".join(n or f"(code {i})" for i, n in missing[:10]) if missing else ""),
                [{"landlord_id": i, "name": n} for i, n in missing])


def check_register(settings: Settings, rep: Report) -> None:
    reg = landlords()
    al = aliases()
    bad = [a for a in al if a["landlord_id"] not in reg or a["kind"] not in ALIAS_KINDS]
    rep.add("aliases point to known landlords and kinds", "fail" if bad else "ok",
            f"{len(al)} aliases; {len(bad)} wrong", bad)
    amb = {k: sorted(v) for k, v in ambiguous_names().items()}
    rep.add("no alias points to two landlords", "fail" if amb else "ok",
            f"{len(amb)} names point to more than one landlord" + (f": {list(amb.items())[:5]}" if amb else ""),
            [{"name": k, "landlords": v} for k, v in amb.items()])
    slugs = Counter(r["slug"] for r in reg.values() if r.get("slug"))
    dupes = [s for s, n in slugs.items() if n > 1]
    rep.add("slugs are unique", "fail" if dupes else "ok", f"{len(slugs)} slugs; {len(dupes)} repeated", dupes)
    published = read_lines(PUBLISHED_SLUGS)
    gone = [s for s in published if s not in slugs]
    rep.add("no published slug has disappeared", "fail" if gone else "ok",
            f"{len(published)} published; {len(gone)} missing", gone)
    profiled = [r for r in reg.values() if r.get("profiled") == "yes"]
    incomplete = [r["id"] for r in profiled if not (r.get("display_name") and r.get("slug") and r.get("type"))]
    rep.add("every profiled landlord has a name, slug and type", "fail" if incomplete else "ok",
            f"{len(profiled)} profiled; {len(incomplete)} incomplete", incomplete)
    coverage = read_table(settings, "tsm_coverage")
    latest = max(c["period"] for c in coverage)
    cov = {c["landlord_id"] for c in coverage if c["period"] == latest}
    not_profiled = sorted(cov - {r["id"] for r in profiled})
    rep.add(f"every TSM {latest} landlord is profiled", "fail" if not_profiled else "ok",
            f"{len(cov)} in the TSM data; {len(not_profiled)} not profiled", not_profiled)


def check_ranges(settings: Settings, rep: Report) -> None:
    bad = []
    for r in read_table(settings, "tsm"):
        v = r["value"]
        if v is None:
            continue
        pct = r["measure"].startswith(PERCENT_MEASURES)
        if (pct and not 0 <= v <= 100) or v < 0:
            bad.append({k: r[k] for k in ("landlord_id", "stock_type", "measure", "method", "value")})
    rep.add("TSM values in range", "fail" if bad else "ok",
            f"{len(bad)} outside 0-100 (percentages) or below 0 (rates)", bad)
    bad = [r for r in read_table(settings, "ombudsman")
           if r["value"] < 0 or (r["measure"] == "maladministration_rate" and r["value"] > 1)]
    rep.add("Ombudsman values in range", "fail" if bad else "ok", f"{len(bad)} out of range", bad)
    bad = [r for r in read_table(settings, "stock_area") if r["value"] < 0]
    rep.add("stock values in range", "fail" if bad else "ok", f"{len(bad)} below 0", bad)
    bad = [g for g in read_table(settings, "grades") if g["grade"] and not re.fullmatch(r"[CGV][1-4]|Y", g["grade"])]
    rep.add("grades are C1-C4, G1-G4, V1-V4 or a rent judgement", "fail" if bad else "ok",
            f"{len(bad)} unexpected grades", [{k: g[k] for k in ("landlord_id", "grade", "table")} for g in bad])


def check_tsm_reconciliation(settings: Settings, rep: Report, expect: dict) -> None:
    tsm = read_table(settings, "tsm")
    cov = read_table(settings, "tsm_coverage")
    survey = read_table(settings, "tsm_survey")
    for period, e in expect.items():
        tol = e.get("tolerance", 0.0)
        cv = [c for c in cov if c["period"] == period]
        if not cv:
            rep.add(f"TSM {period} reconciles", "warn", "not loaded")
            continue
        with_results = [c for c in cv if c["lcra"] or c["lcho"] or c["combined"] or c["management_info"]]
        kinds = Counter()
        for c in cv:
            rented = c["lcra"] or (c["perception_excluded"] and c["management_info"] and not c["lcho"])
            if c["combined"]:
                kinds["combined"] += 1
            elif rented and c["lcho"]:
                kinds["rented_and_shared_ownership"] += 1
            elif rented:
                kinds["rented_only"] += 1
            elif c["lcho"]:
                kinds["shared_ownership_only"] += 1
        got = {"submissions": len(with_results), **kinds}
        diffs = {k: (got.get(k, 0), e[k]) for k in ("submissions", "rented_only", "rented_and_shared_ownership",
                                                    "shared_ownership_only", "combined") if got.get(k, 0) != e[k]}
        rep.add(f"TSM {period}: submissions by stock type", "fail" if diffs else "ok",
                f"{got}" + (f"; differs (got, published): {diffs}" if diffs else " as published"))

        tp01 = sorted(r["value"] for r in tsm if r["period"] == period and r["stock_type"] == "LCRA"
                      and r["measure"] == "TP01" and r["method"] == "all" and r["value"] is not None)
        q = statistics.quantiles(tp01, n=4, method="inclusive")
        got_q = {"lower": q[0], "median": q[1], "upper": q[2]}
        want = {"lower": e["tp01_rented_lower_quartile"], "median": e["tp01_rented_median"],
                "upper": e["tp01_rented_upper_quartile"]}
        ok = all(_close(got_q[k], want[k], tol) for k in want)
        rep.add(f"TSM {period}: TP01 (rented) quartiles", "ok" if ok else "fail",
                f"{len(tp01)} landlords; got {got_q}, published {want}")

        # Surveys by method count every response; satisfaction by method is weighted by the responses of the
        # landlords that report it (a method with fewer than 50 surveys at a landlord is suppressed, [S]).
        responses = {(x["landlord_id"], x["stock_type"]): json.loads(x["responses"]) for x in survey
                     if x["period"] == period}
        sums, sat, weight = defaultdict(float), defaultdict(float), defaultdict(float)
        for by_method in responses.values():
            for m, n in by_method.items():
                sums[m] += n or 0
        for r in tsm:
            if r["period"] == period and r["measure"] == "TP01" and r["method"] != "all" and r["value"] is not None:
                n = responses.get((r["landlord_id"], r["stock_type"]), {}).get(r["method"]) or 0
                sat[r["method"]] += r["value"] * n
                weight[r["method"]] += n
        rows, ok = [], True
        has_by_method = any(weight.values())  # 2023/24's file has no satisfaction by method
        for method, (count, pct) in e.get("by_method", {}).items():
            got_pct = sat[method] / weight[method] if weight[method] else None
            good = sums[method] == count and (not has_by_method or (got_pct is not None and _close(got_pct, pct, tol)))
            ok &= good
            rows.append({"method": method, "surveys": sums[method], "published_surveys": count,
                         "satisfaction": round(got_pct, 2) if got_pct else None, "published_satisfaction": pct})
        rep.add(f"TSM {period}: surveys and satisfaction by method", "ok" if ok else "fail",
                "; ".join(f"{r['method']} {int(r['surveys'])} at {r['satisfaction']}% "
                          f"(published {r['published_surveys']} at {r['published_satisfaction']}%)" for r in rows),
                rows)

        tel = e.get("telephone_main_method")
        if tel:
            main = {}
            for s in survey:
                if s["period"] == period:
                    main.setdefault(s["landlord_id"], s["predominant_method"])
            share = 100 * sum(m == "Telephone" for m in main.values()) / len(main)
            level = "ok" if _close(share, tel["percent"], 0.5) else ("warn" if tel.get("known_difference") else "fail")
            rep.add(f"TSM {period}: landlords using telephone as main method", level,
                    f"got {share:.1f}% of {len(main)}, published {tel['percent']}%"
                    + (f". Known: {tel['known_difference']}" if level == "warn" else ""))

        missing = []
        by = defaultdict(dict)
        for r in tsm:
            if r["period"] == period:
                by[r["landlord_id"]][(r["measure"], r["stock_type"], r["method"])] = r["status"]
        cov_by = {c["landlord_id"]: c for c in cv}
        for lid, what in e.get("excluded", {}).items():
            for w in what:
                if w == "perception":
                    good = lid in cov_by and cov_by[lid]["perception_excluded"] and not any(
                        k[0].startswith("TP") for k in by.get(lid, {}))
                elif w == "management":
                    good = lid in cov_by and cov_by[lid]["management_excluded"] and not any(
                        k[0][:2] in ("BS", "RP", "CH", "NM") for k in by.get(lid, {}))
                else:
                    # The exclusion can apply to one stock type only (Your Housing Group's TP10 is excluded for
                    # rented homes; its shared ownership TP10 is published).
                    statuses = [s for k, s in by.get(lid, {}).items() if k[0] == w and k[2] == "all"]
                    good = "excluded" in statuses
                if not good:
                    missing.append(f"{lid} {w}")
        rep.add(f"TSM {period}: the regulator's exclusions are marked", "fail" if missing else "ok",
                f"{sum(len(v) for v in e.get('excluded', {}).values())} listed; {len(missing)} not found as excluded"
                + (f": {missing}" if missing else ""))


def check_other_reconciliation(settings: Settings, rep: Report, expect: dict) -> None:
    om = read_table(settings, "ombudsman")
    for period, e in expect.get("ombudsman", {}).items():
        n = len({r["name_published"] for r in om if r["period"] == period})
        if "landlords" in e:
            rep.add(f"Ombudsman {period}: landlords", "ok" if n == e["landlords"] else "fail",
                    f"got {n}, published {e['landlords']}")
        else:  # only the number of reports is published, before those withheld for privacy
            rep.add(f"Ombudsman {period}: landlords", "ok" if 0 < n <= e["reports"] else "fail",
                    f"got {n}; {e['reports']} reports published, less an unstated number withheld for privacy")
    councils = [p for p in read_table(settings, "providers") if p["gss"]]
    stock = {r["landlord_id"] for r in read_table(settings, "stock_area") if r["basis"] == "council total"}
    for period, e in expect.get("stock", {}).items():
        n = len(councils)
        rep.add(f"Stock {period}: council returns", "ok" if n == e["councils"] else "fail",
                f"got {n} returns ({len(stock)} with homes; the rest report none), published {e['councils']}")


def check_areas(settings: Settings, rep: Report) -> None:
    """Every English area code in the stock data is a council in data_static/councils.csv (Where Councils Stand's)."""
    import csv

    from landlords.config import STATIC_DIR

    with open(STATIC_DIR / "councils.csv", newline="", encoding="utf-8") as fh:
        known = {r["gss"] for r in csv.DictReader(fh)}
    codes = {(r["gss"], r["area_name"]) for r in read_table(settings, "stock_area") if r["gss"].startswith("E")}
    missing = sorted(c for c in codes if c[0] not in known)
    other = Counter(r["gss"][:3] for r in read_table(settings, "stock_area") if not r["gss"].startswith("E"))
    rep.add("every English area is a council in councils.csv", "fail" if missing else "ok",
            f"{len(codes)} English areas; {len(missing)} not in councils.csv"
            + (f": {missing[:10]}" if missing else "") + f"; rows outside England by code prefix: {dict(other)}",
            [{"gss": g, "name": n} for g, n in missing])


def check_stock_against_tsm(settings: Settings, rep: Report) -> None:
    """Homes added up through the group table, against the rented population each landlord reported for its TSMs.

    A big difference means the group roll-up has picked up too many or too few companies, or the TSM covers
    different stock. It is a warning to look at, not a failure.
    """
    totals = area.rolled_up_totals(settings)
    pop = {}
    survey = read_table(settings, "tsm_survey")
    latest = max(s["period"] for s in survey)
    for s in survey:
        if s["period"] == latest and s["stock_type"] in ("LCRA", "COMB") and s["population"]:
            pop[s["landlord_id"]] = pop.get(s["landlord_id"], 0) + s["population"]
    rows = []
    for lid, p in pop.items():
        t = totals.get(lid, 0.0)
        ratio = t / p if p else None
        if ratio is None or not 0.75 <= ratio <= 1.33:
            rows.append({"landlord_id": lid, "tsm_rented_population": p, "rented_homes_by_area": t,
                         "ratio": round(ratio, 2) if ratio is not None else None})
    rows.sort(key=lambda r: abs((r["ratio"] or 0) - 1), reverse=True)
    rep.add("homes by area roughly match each landlord's TSM population", "warn" if rows else "ok",
            f"{len(pop)} landlords compared; {len(rows)} differ by more than a third (see the report)", rows)


def check_rights_dates(rep: Report, today: date | None = None) -> None:
    """Every section of the rights page has a date by which it must be checked again (config/rights.toml)."""
    today = today or date.today()
    due = [f"{s['heading']} (due {s['recheck']})" for s in load_toml("rights.toml").get("section", [])
           if date.fromisoformat(s["recheck"]) <= today]
    rep.add("rights page checked on time", "warn" if due else "ok",
            f"{len(due)} sections due to be checked again" + (f": {due}" if due else ""), due)


def change_report(settings: Settings) -> dict:
    """The biggest movers: TP01 (rented) between the two latest TSM periods, and grade changes in the current table."""
    tsm = read_table(settings, "tsm")
    periods = sorted({r["period"] for r in tsm})
    movers = []
    if len(periods) >= 2:
        a, b = periods[-2], periods[-1]
        vals = defaultdict(dict)
        for r in tsm:
            if r["measure"] == "TP01" and r["stock_type"] == "LCRA" and r["method"] == "all" and r["value"] is not None:
                vals[r["landlord_id"]][r["period"]] = r["value"]
        movers = sorted(({"landlord_id": k, a: v[a], b: v[b], "change": round(v[b] - v[a], 1)}
                         for k, v in vals.items() if a in v and b in v), key=lambda m: -abs(m["change"]))[:25]
    grades = [{k: g[k] for k in ("landlord_id", "name_published", "standard", "grade", "change", "grade_date")}
              for g in read_table(settings, "grades")
              if g["table"] == "current" and (g["change"] in ("Downgrade", "Upgrade") or g["change"].startswith("Regrade"))]
    grades.sort(key=lambda g: str(g["grade_date"]), reverse=True)
    return {"tsm_periods": periods, "tp01_rented_movers": movers,
            "note": "" if movers else "Only one TSM period is loaded, so there are no movers yet.",
            "grade_changes": grades}


def run(settings: Settings) -> dict:
    rep = Report()
    expect = load_toml("reconciliation.toml")
    area.build(settings)
    check_matched(settings, rep)
    check_register(settings, rep)
    check_ranges(settings, rep)
    check_tsm_reconciliation(settings, rep, expect.get("tsm", {}))
    check_other_reconciliation(settings, rep, expect)
    check_areas(settings, rep)
    check_stock_against_tsm(settings, rep)
    check_rights_dates(rep)
    changes = change_report(settings)
    out = settings.staging_dir / "check-report.json"
    out.write_text(json.dumps({"finished": datetime.now(UTC).isoformat(timespec="seconds"), "checks": rep.checks},
                              indent=2, default=str) + "\n")
    (settings.staging_dir / "change-report.json").write_text(json.dumps(changes, indent=2, default=str) + "\n")
    return {"checks": rep.checks, "file": str(out)}
