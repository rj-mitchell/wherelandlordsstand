"""Placing each profiled landlord among similar landlords: ``peer_groups`` and ``scores``.

The rules are in config/scoring.toml and are explained on the method page. In short, for each TSM year:

1. Each landlord joins a peer group by type and size; small groups are merged.
2. For each scored measure, each landlord's published figure gets a percentile within its peer group (the
   share of peers it does better than, ties counted as half), so 100 is best whichever way the measure runs.
3. A pillar's score is the median of its measures' percentiles, if the landlord has at least half of them.
4. The overall satisfaction figure and each pillar score are ranked again within the peer group and shown only as
   a band: top quarter, upper middle, lower middle or bottom quarter.

Published figures are never changed: percentiles and bands are positions, and they are labelled as ours.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict

import pyarrow as pa

from landlords.config import Settings, load_toml
from landlords.load.common import read_table, write_table
from landlords.register import landlords

PEERS = pa.schema([
    ("landlord_id", pa.string()),
    ("period", pa.string()),
    ("type", pa.string()),
    ("homes", pa.float64()),
    ("homes_basis", pa.string()),       # "tsm population" or "stock return"
    ("size_band", pa.string()),         # the landlord's own band
    ("peer_group", pa.string()),        # the group it is compared within, after merging
    ("peer_group_label", pa.string()),
    ("peers", pa.int32()),
    ("stock_type", pa.string()),        # LCRA or COMB: the results scored
    ("survey_method", pa.string()),     # normalised predominant method
    ("peer_survey_method", pa.string()),
])

SCORES = pa.schema([
    ("landlord_id", pa.string()),
    ("period", pa.string()),
    ("kind", pa.string()),              # measure, pillar, headline
    ("item", pa.string()),              # TP01, RP02_1 ..., or a pillar key
    ("value", pa.float64()),            # the published figure (measures and headline only)
    ("percentile", pa.float64()),       # our position within the peer group, 0-100, higher is better
    ("band", pa.int8()),                # 1 bottom quarter ... 4 top quarter; empty if not scored
    ("peers_with_figure", pa.int32()),
    ("measures_used", pa.int32()),      # pillars: how many of its measures had a figure
    ("note", pa.string()),
])


def rules() -> dict:
    return load_toml("scoring.toml")


# The arithmetic -----------------------------------------------------------------------------------------------------


def percentiles(values: dict[str, float], higher_is_better: bool = True) -> dict[str, float]:
    """Each key's mid-rank percentile among ``values``: the share of the others it beats, ties counting half,
    scaled so the best of n gets close to 100 and the worst close to 0. 100 is always best."""
    n = len(values)
    if n == 0:
        return {}
    sign = 1 if higher_is_better else -1
    out = {}
    for k, v in values.items():
        below = sum(1 for o in values.values() if sign * o < sign * v)
        ties = sum(1 for o in values.values() if o == v) - 1
        out[k] = 100.0 * (below + 0.5 * ties + 0.5) / n
    return out


def band(percentile: float | None, edges: list[float]) -> int | None:
    if percentile is None:
        return None
    return 1 + sum(percentile >= e for e in edges)


def size_band(homes: float | None, edges: list[int]) -> int | None:
    if homes is None:
        return None
    if homes < edges[0]:
        return 0  # below the first edge: smallest band
    return max(i for i, e in enumerate(edges) if homes >= e)


def size_label(i: int, edges: list[int]) -> str:
    lo = edges[i]
    hi = edges[i + 1] - 1 if i + 1 < len(edges) else None
    return f"{lo:,} to {hi:,} homes" if hi else f"{lo:,} homes or more"


def merge_groups(members: dict[str, tuple[str, int]], types: list[str], n_bands: int, min_group: int,
                 merge_type_into: dict[str, str]) -> dict[str, tuple[str, tuple[int, ...]]]:
    """Each landlord's peer group as (type, size bands covered), after merging groups smaller than ``min_group``."""
    count_by_type = Counter(t for t, _ in members.values())
    final_type = {t: (merge_type_into.get(t, t) if count_by_type[t] < min_group else t) for t in types}
    groups: dict[str, list[list[int]]] = {}
    for t in set(final_type.values()):
        bands = [[b] for b in range(n_bands)]
        size = Counter(b for lt, b in members.values() if final_type[lt] == t)
        # Merge the smallest undersized group into its neighbour, preferring the band below, until all are big
        # enough or one group is left.
        while len(bands) > 1:
            sizes = [sum(size[b] for b in g) for g in bands]
            small = [i for i, s in enumerate(sizes) if s < min_group]
            if not small:
                break
            i = min(small, key=lambda j: sizes[j])
            j = i - 1 if i > 0 else i + 1
            bands[min(i, j)] = sorted(bands[i] + bands[j])
            del bands[max(i, j)]
        groups[t] = bands
    out = {}
    for lid, (t, b) in members.items():
        ft = final_type[t]
        out[lid] = (ft, tuple(next(g for g in groups[ft] if b in g)))
    return out


def method_key(text: str) -> str:
    s = re.sub(r"[^a-z]", "", (text or "").lower())
    return {"telephone": "telephone", "internet": "internet", "facetoface": "face to face", "postal": "postal",
            "sms": "sms", "other": "other", "nopredominantmethod": "mixed"}.get(s, "")


# Running ---------------------------------------------------------------------------------------------------------------


def run(settings: Settings) -> dict[str, int]:
    r = rules()
    pg, sc = r["peer_groups"], r["scoring"]
    reg = landlords()
    tsm = read_table(settings, "tsm")
    survey = read_table(settings, "tsm_survey")
    coverage = read_table(settings, "tsm_coverage")
    area = read_table(settings, "landlord_area")
    stock_homes: dict[str, float] = defaultdict(float)
    for a in area:
        if a["gss"].startswith("E"):
            stock_homes[a["profile_id"]] += a["rented_homes"] + a["shared_ownership_homes"]

    measures = r["measures"]
    scored = [m for p in r["pillars"].values() for m in p["measures"]] + [r["headline"]["measure"]]
    peer_rows, score_rows = [], []
    for period in sorted({c["period"] for c in coverage}):
        # Who is scored this year, on which results ----------------------------------------------------------------
        # Rented results (LCRA), or combined (COMB) for landlords allowed to report both together. A landlord
        # whose survey results were excluded is still scored on its management measures for rented homes.
        # Landlords with shared owners only are not scored.
        stock_of: dict[str, str] = {}
        for c in coverage:
            if c["period"] != period:
                continue
            if c["combined"]:
                stock_of[c["landlord_id"]] = "COMB"
            elif c["lcra"] or (c["perception_excluded"] and c["management_info"] and not c["lcho"]):
                stock_of[c["landlord_id"]] = "LCRA"
        values: dict[str, dict[str, float]] = defaultdict(dict)
        status: dict[str, dict[str, str]] = defaultdict(dict)
        for row in tsm:
            lid = row["landlord_id"]
            if row["period"] != period or row["method"] != "all" or lid not in stock_of:
                continue
            if row["stock_type"] in (stock_of[lid], "ALL") and row["measure"] in measures:
                status[lid][row["measure"]] = row["status"]
                if row["value"] is not None:
                    values[lid][row["measure"]] = row["value"]
        population: dict[str, float] = defaultdict(float)
        method_of: dict[str, str] = {}
        for s in survey:
            if s["period"] == period and s["population"]:
                population[s["landlord_id"]] += s["population"]
            if s["period"] == period and s["stock_type"] == stock_of.get(s["landlord_id"]):
                method_of[s["landlord_id"]] = method_key(s["predominant_method"])
        ids = sorted(set(stock_of) & set(reg))

        # Peer groups ----------------------------------------------------------------------------------------------
        members, homes, basis = {}, {}, {}
        for lid in ids:
            h = population.get(lid) or stock_homes.get(lid)
            if not h or reg[lid]["type"] not in pg["types"]:
                continue
            homes[lid], basis[lid] = h, "tsm population" if population.get(lid) else "stock return"
            members[lid] = (reg[lid]["type"], size_band(h, pg["size_bands"]))
        groups = merge_groups(members, pg["types"], len(pg["size_bands"]), pg["min_group"],
                              pg.get("merge_type_into", {}))
        by_group: dict[tuple, list[str]] = defaultdict(list)
        for lid, g in groups.items():
            by_group[g].append(lid)
        for g, lids in by_group.items():
            common = Counter(method_of.get(lid, "") for lid in lids if method_of.get(lid)).most_common(1)
            peer_method = common[0][0] if common else ""
            plural = {"council": "councils", "housing association": "housing associations",
                      "for-profit": "for-profit landlords"}
            types_in = [t for t in pg["types"][::-1] if t in {members[lid][0] for lid in lids}]
            types_in = sorted(types_in, key=lambda t: t != g[0])  # the group's own type first
            label = " and ".join(plural.get(t, t) for t in types_in) + ", " + _bands_label(g[1], pg["size_bands"])
            for lid in lids:
                peer_rows.append({
                    "landlord_id": lid, "period": period, "type": members[lid][0], "homes": homes[lid],
                    "homes_basis": basis[lid], "size_band": size_label(members[lid][1], pg["size_bands"]),
                    "peer_group": f"{g[0]}|{','.join(map(str, g[1]))}", "peer_group_label": label,
                    "peers": len(lids), "stock_type": stock_of.get(lid, ""),
                    "survey_method": method_of.get(lid, ""), "peer_survey_method": peer_method})

            # Measures ---------------------------------------------------------------------------------------------
            pct: dict[str, dict[str, float]] = defaultdict(dict)
            for m in scored:
                better = measures[m]["better"]
                vals = {lid: values[lid][m] for lid in lids if m in values[lid]}
                if better == "volume" or len(vals) < sc["min_peers"]:
                    continue
                for lid, p in percentiles(vals, better == "higher").items():
                    pct[lid][m] = p
                for lid in lids:
                    if m == r["headline"]["measure"]:
                        continue
                    score_rows.append({
                        "landlord_id": lid, "period": period, "kind": "measure", "item": m,
                        "value": values[lid].get(m), "percentile": pct[lid].get(m),
                        "band": band(pct[lid].get(m), sc["band_edges"]), "peers_with_figure": len(vals),
                        "measures_used": None,
                        "note": "" if m in values[lid] else status[lid].get(m, "not published")})

            # Headline: overall satisfaction, banded directly ---------------------------------------------------------
            hm = r["headline"]["measure"]
            hv = {lid: pct[lid][hm] for lid in lids if hm in pct[lid]}
            for lid in lids:
                p = hv.get(lid)
                score_rows.append({
                    "landlord_id": lid, "period": period, "kind": "headline", "item": hm,
                    "value": values[lid].get(hm), "percentile": p, "band": band(p, sc["band_edges"]),
                    "peers_with_figure": len(hv), "measures_used": None,
                    "note": "" if p is not None else status[lid].get(hm, "not published")})

            # Pillars: median of measure percentiles, then ranked again within the group ------------------------------
            for key, pillar in r["pillars"].items():
                raw, used = {}, {}
                for lid in lids:
                    got = [pct[lid][m] for m in pillar["measures"] if m in pct[lid]]
                    used[lid] = len(got)
                    if got and len(got) >= sc["min_share"] * len(pillar["measures"]):
                        raw[lid] = statistics.median(got)
                ranked = percentiles(raw) if len(raw) >= sc["min_peers"] else {}
                for lid in lids:
                    p = ranked.get(lid)
                    score_rows.append({
                        "landlord_id": lid, "period": period, "kind": "pillar", "item": key, "value": None,
                        "percentile": p, "band": band(p, sc["band_edges"]), "peers_with_figure": len(ranked),
                        "measures_used": used[lid],
                        "note": "" if p is not None else
                        f"figures for {used[lid]} of {len(pillar['measures'])} measures"})

    write_table(settings, "peer_groups", peer_rows, PEERS)
    write_table(settings, "scores", score_rows, SCORES)
    return {"peer_groups": len({(p["period"], p["peer_group"]) for p in peer_rows}), "landlords": len(peer_rows),
            "scores": len(score_rows)}


def _bands_label(bands: tuple[int, ...], edges: list[int]) -> str:
    lo = edges[min(bands)]
    top = max(bands)
    hi = edges[top + 1] - 1 if top + 1 < len(edges) else None
    return f"{lo:,} to {hi:,} homes" if hi else f"{lo:,} homes or more"
