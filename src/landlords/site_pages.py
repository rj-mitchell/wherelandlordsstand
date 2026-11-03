"""The pages beyond the profiles: home and search, council areas, compare, your rights, data downloads, corrections and
privacy (`landlords build`, through ``site.build``). Every sentence is in config/wording.toml, or config/rights.toml
for the rights page.
"""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from pathlib import Path

from landlords.config import Settings, load_toml
from landlords.register import normalise, slugify
from landlords.score import rules
from landlords.site import band_name, esc, fill, nice_date, page

STATIC = Path(__file__).parent / "static"


# Search ----------------------------------------------------------------------------------------------------------------


def names_json(profiles: list[dict], reg: dict, aliases: list[dict], w: dict) -> list[dict]:
    """Every name a reader might search for. Profiled landlords carry their slug; active landlords below 1,000 homes
    are listed without one, so a search can say they exist but aren't covered."""
    by_id: dict[str, set[str]] = defaultdict(set)
    for a in aliases:
        by_id[a["landlord_id"]].add(a["alias"])
    out = []
    profiled = {p["id"] for p in profiles}
    for p in profiles:
        names = {p["name"], p["legal_name"], *by_id[p["id"]]}
        out.append({"n": p["name"], "s": p["slug"], "t": w["types"].get(p["type"], p["type"]),
                    "a": p["also_known_as"][:4], "k": sorted({normalise(n) for n in names} - {""})})
    for lid, r in reg.items():
        if lid not in profiled and r["status"] == "active":
            keys = sorted({normalise(n) for n in (r["legal_name"], *by_id[lid])} - {""})
            out.append({"n": r["legal_name"], "k": keys})
    return out


def index_html(profiles: list[dict], w: dict) -> str:
    s = w["search"]
    by_letter: dict[str, list] = {}
    for p in sorted(profiles, key=lambda p: p["name"].lower().removeprefix("the ")):
        letter = p["name"].lower().removeprefix("the ")[:1].upper()
        by_letter.setdefault(letter if letter.isalpha() else "#", []).append(p)
    text = json.dumps({"none": s["none"], "small": s["small"], "areas": s["areas_link"]})
    parts = [f"<h1>{esc(s['heading'])}</h1><p>{esc(s['intro'])}</p>",
             f'<form id="search" role="search" data-root=""><label for="q">{esc(s["label"])}</label>'
             f'<input id="q" name="q" type="search" autocomplete="off" placeholder="{esc(s["placeholder"])}">'
             f'<p class="hint">{esc(s["hint"])}</p></form><ul id="results" class="results" aria-live="polite"></ul>'
             f'<script type="application/json" id="search-text">{text}</script>'
             f'<noscript><p>{esc(s["noscript"])}</p></noscript>',
             f'<p><a href="areas/index.html">{esc(s["areas_link"])}</a></p>',
             f"<h2>{esc(s['all'])}</h2><p>{fill(s['count'], count=len(profiles))}</p>"]
    for letter, ps in by_letter.items():
        items = "".join(f'<li><a href="landlords/{esc(p["slug"])}/index.html">{esc(p["name"])}</a></li>' for p in ps)
        parts.append(f'<h3>{esc(letter)}</h3><ul class="az">{items}</ul>')
    return page(w["site"]["name"], "".join(parts), w, depth=0, scripts=("search.js",))


# Council areas ---------------------------------------------------------------------------------------------------------


def area_rows(settings: Settings, profiles: list[dict]) -> dict[str, dict]:
    from landlords.load.common import read_table

    by_id = {p["id"]: p for p in profiles}
    areas: dict[str, dict] = {}
    for a in read_table(settings, "landlord_area"):
        if not a["gss"].startswith("E") or a["profile_id"] not in by_id or not a["rented_homes"]:
            continue
        area = areas.setdefault(a["gss"], {"gss": a["gss"], "name": a["area_name"], "landlords": [],
                                           "sources": set()})
        area["landlords"].append((by_id[a["profile_id"]], a["rented_homes"], a["basis"]))
        area["sources"].update(a["source_files"].split(","))
    slugs: dict[str, int] = defaultdict(int)
    for a in sorted(areas.values(), key=lambda a: a["name"]):
        base = slugify(a["name"])
        slugs[base] += 1
        a["slug"] = base if slugs[base] == 1 else f"{base}-{a['gss'].lower()}"
        a["landlords"].sort(key=lambda x: -x[1])
    return areas


def area_html(a: dict, w: dict, sources: dict) -> str:
    from landlords.site import Sources

    t = w["area"]
    src = Sources([{"sha": s, **sources.get(s, {})} for s in sorted(a["sources"])])
    rows = []
    for p, homes, basis in a["landlords"]:
        g = p["grade"].get("grade") or "–"
        b = p["bands"].get("headline", {}) if p["bands"] else {}
        rows.append(f'<tr><td><a href="../../landlords/{esc(p["slug"])}/index.html">{esc(p["name"])}</a>'
                    f'{" *" if basis == "council total" else ""}</td><td class="n">{homes:,.0f}</td>'
                    f'<td>{esc(g)}</td><td>{esc(band_name(b.get("band")) or "–")}</td></tr>')
    body = (f"<h1>{esc(a['name'])}</h1><p>{fill(t['intro'], count=len(a['landlords']))}</p>"
            f'<div class="scroll"><table><thead><tr><th scope="col">{esc(t["landlord"])}</th>'
            f'<th scope="col" class="n">{esc(t["homes"])}</th><th scope="col">{esc(t["grade"])}</th>'
            f'<th scope="col">{esc(t["overall"])}</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            f'<p class="hint">{esc(t["notes"])}</p>'
            + (f'<p class="hint">* {esc(t["council_note"])}</p>' if any(x[2] == "council total" for x in a["landlords"]) else "")
            + f'<p class="warn">{esc(w["card"]["refusal"])}</p>' + src.ref(*a["sources"]) + src.html(w))
    return page(f"{a['name']} – {w['site']['name']}", body, w, depth=2,
                description=fill(t["intro"], count=len(a["landlords"])))


def areas_index_html(areas: dict[str, dict], w: dict) -> str:
    t = w["area"]
    items = "".join(f'<li><a href="{esc(a["slug"])}/index.html">{esc(a["name"])}</a> '
                    f'<span class="hint">({len(a["landlords"])})</span></li>'
                    for a in sorted(areas.values(), key=lambda a: a["name"]))
    body = f"<h1>{esc(t['heading'])}</h1><p>{esc(t['index_intro'])}</p><ul class=\"az\">{items}</ul>"
    return page(f"{t['heading']} – {w['site']['name']}", body, w, depth=1)


# Compare ---------------------------------------------------------------------------------------------------------------


def landlord_json(p: dict, w: dict) -> dict:
    b = p["bands"] or {}
    head = b.get("headline", {})
    om = (p["ombudsman"] or {}).get("reports") or []
    om_latest = None
    if om:
        r = om[0]
        om_latest = {"period": r["period"], "findings": f'{r.get("findings_in_jurisdiction", 0):,.0f}',
                     "at_fault": f'{100 * r.get("maladministration_rate", 0):.0f}%'}
    return {
        "name": p["name"], "slug": p["slug"], "type": w["types"].get(p["type"], p["type"]),
        "homes": round(p["homes"]["homes"]) if p["homes"] else None,
        "grade": p["grade"].get("grade"), "grade_date": nice_date(p["grade"]["date"]) if p["grade"].get("date") else "",
        "overall": head.get("value"), "overall_band": head.get("band"),
        "pillars": [{"label": x["label"], "band": x["band"]} for x in b.get("pillars", [])],
        "peer_group": (b.get("peer") or {}).get("peer_group_label", ""), "period": b.get("period", ""),
        "ombudsman": om_latest, "safety": p["safety"]["all_done"] if p["safety"] else None,
    }


def compare_html(w: dict) -> str:
    t = w["compare"]
    text = {**{k: t[k] for k in ("measure", "type", "homes", "grade", "overall", "peer", "ombudsman", "safety", "remove", "empty",
                                  "not_graded", "no_report", "at_fault", "findings", "all_done", "not_all_done",
                                  "caveat", "none")},
            "bands": rules()["scoring"]["bands"]}
    body = (f"<h1>{esc(t['heading'])}</h1><p>{esc(t['intro'])}</p>"
            f'<div id="compare" data-root="../"><label for="add">{esc(t["add"])}</label>'
            f'<input id="add" type="search" autocomplete="off"><ul id="suggest" class="results"></ul>'
            f'<ul id="picks" class="results"></ul><div id="table"></div></div>'
            f'<script type="application/json" id="compare-text">{json.dumps(text)}</script>'
            f'<noscript><p>{esc(t["noscript"])}</p></noscript><p class="warn">{esc(w["card"]["refusal"])}</p>')
    return page(f"{t['heading']} – {w['site']['name']}", body, w, depth=1, scripts=("search.js", "compare.js"))


# Data downloads --------------------------------------------------------------------------------------------------------


def _csv(rows: list[dict], fields: list[str]) -> str:
    buf = io.StringIO()
    wr = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    wr.writeheader()
    wr.writerows(rows)
    return buf.getvalue()


def downloads(settings: Settings, profiles: list[dict], out: Path, w: dict) -> list[tuple[str, str, int]]:
    """CSV files, each row carrying its source file's address and licence so the attribution travels with it."""
    from landlords.load.common import read_table

    sources = json.loads((settings.staging_dir / "sources.json").read_text())
    ids = {p["id"]: p for p in profiles}

    def attr(sha: str) -> dict:
        s = sources.get(sha, {})
        return {"source_publisher": s.get("publisher", ""), "source_title": s.get("title", ""),
                "source_url": s.get("url", ""), "licence": s.get("licence", "")}

    files = []
    rows = [{"landlord_id": p["id"], "name": p["name"], "legal_name": p["legal_name"], "type": p["type"],
             "status": p["status"], "page": f"landlords/{p['slug']}/", "consumer_grade": p["grade"].get("grade") or "",
             "grade_date": p["grade"].get("date") or "", "grade_of": p["grade"].get("by") or "",
             **attr(p["grade"].get("source", ""))} for p in profiles]
    files.append(("landlords.csv", _csv(rows, list(rows[0])), len(rows)))

    sc = [s for s in read_table(settings, "scores") if s["landlord_id"] in ids and s["kind"] != "measure"]
    pg = {(p["landlord_id"], p["period"]): p for p in read_table(settings, "peer_groups")}
    bands = rules()["scoring"]["bands"]
    rows = [{"landlord_id": s["landlord_id"], "period": s["period"], "item": s["item"], "kind": s["kind"],
             "band": bands[s["band"] - 1] if s["band"] else "", "percentile": round(s["percentile"], 1) if s["percentile"] is not None else "",
             "peer_group": pg.get((s["landlord_id"], s["period"]), {}).get("peer_group_label", ""),
             "made_by": "Where Landlords Stand, from the regulator's published figures (method/)"} for s in sc]
    files.append(("bands.csv", _csv(rows, list(rows[0])), len(rows)))

    rows = [{"landlord_id": t["landlord_id"], "name_published": t["name_published"], "period": t["period"],
             "stock_type": t["stock_type"], "measure": t["measure"], "method": t["method"], "value": t["value"],
             "status": t["status"], "numerator": t["numerator"], "denominator": t["denominator"],
             **attr(t["source_file"])} for t in read_table(settings, "tsm") if t["landlord_id"] in ids]
    files.append(("tenant-satisfaction-measures.csv", _csv(rows, list(rows[0])), len(rows)))

    owners = {o["landlord_id"]: o["profile_id"] for o in read_table(settings, "owners")}
    rows = [{"landlord_id": o["landlord_id"], "profile_id": owners.get(o["landlord_id"], ""),
             "name_published": o["name_published"], "period": o["period"], "measure": o["measure"],
             "value": o["value"], **attr(o["source_file"])} for o in read_table(settings, "ombudsman")]
    files.append(("ombudsman.csv", _csv(rows, list(rows[0])), len(rows)))

    rows = [{"landlord_id": g["landlord_id"], "name_published": g["name_published"], "table": g["table"],
             "standard": g["standard"], "grade": g["grade"], "grade_date": g["grade_date"] or "",
             "publication_type": g["publication_type"], "publication_date": g["publication_date"] or "",
             **attr(g["source_file"])} for g in read_table(settings, "grades") if g["landlord_id"] in ids]
    files.append(("regulatory-judgements.csv", _csv(rows, list(rows[0])), len(rows)))

    rows = [{"landlord_id": a["profile_id"], "gss": a["gss"], "area_name": a["area_name"], "period": a["period"],
             "rented_homes": a["rented_homes"], "shared_ownership_homes": a["shared_ownership_homes"],
             "companies": a["companies"], "basis": a["basis"],
             "made_by": "Where Landlords Stand: the sum of the published figures for each company"}
            for a in read_table(settings, "landlord_area") if a["profile_id"] in ids]
    files.append(("homes-by-area.csv", _csv(rows, list(rows[0])), len(rows)))

    folder = out / "data"
    folder.mkdir(exist_ok=True)
    for name, text, _ in files:
        (folder / name).write_text(text)
    return [(n, t, c) for n, t, c in files]


def downloads_html(files: list[tuple[str, str, int]], w: dict) -> str:
    t = w["downloads"]
    items = "".join(f'<li><a href="{esc(n)}">{esc(n)}</a> <span class="hint">({c:,} rows, '
                    f'{len(text.encode()) // 1024 + 1} KB)</span>: {esc(t["files"].get(n, ""))}</li>'
                    for n, text, c in files)
    body = (f"<h1>{esc(t['heading'])}</h1><p>{esc(t['intro'])}</p><ul class=\"list\">{items}</ul>"
            f"<h2>{esc(t['attribution_heading'])}</h2>" + "".join(f"<p>{esc(x)}</p>" for x in t["attribution"]))
    return page(f"{t['heading']} – {w['site']['name']}", body, w, depth=1)


# Corrections and privacy -----------------------------------------------------------------------------------------------


def corrections_html(w: dict) -> str:
    t = w["corrections"]
    body = (f"<h1>{esc(t['heading'])}</h1>" + "".join(f"<p>{esc(x)}</p>" for x in t["intro"]) +
            f'<form method="post" action="../api/corrections"><label for="page">{esc(t["page"])}</label>'
            f'<input id="page" name="page" type="text" maxlength="300">'
            f'<label for="message">{esc(t["message"])}</label><textarea id="message" name="message" rows="6" '
            f'maxlength="4000" required></textarea><label for="email">{esc(t["email"])}</label>'
            f'<input id="email" name="email" type="email" maxlength="200"><p class="hint">{esc(t["email_hint"])}</p>'
            f'<p><button type="submit">{esc(t["send"])}</button></p></form>'
            f'<p class="hint">{esc(t["offline"])}</p>')
    from landlords.config import STATIC_DIR

    with open(STATIC_DIR / "corrections.csv", newline="", encoding="utf-8") as fh:
        log = list(csv.DictReader(fh))
    body += f"<h2>{esc(t['log_heading'])}</h2>"
    if log:
        rows = "".join(f"<tr><td>{esc(r['date'])}</td><td>{esc(r['page'])}</td><td>{esc(r['what_was_wrong'])}</td>"
                       f"<td>{esc(r['what_we_did'])}</td></tr>" for r in reversed(log))
        body += (f'<div class="scroll"><table><thead><tr><th scope="col">Date</th><th scope="col">Page</th>'
                 f'<th scope="col">What was wrong</th><th scope="col">What we did</th></tr></thead>'
                 f"<tbody>{rows}</tbody></table></div>")
    else:
        body += f"<p>{esc(t['log_empty'])}</p>"
    return page(f"{t['heading']} – {w['site']['name']}", body, w, depth=1)


def thanks_html(w: dict) -> str:
    t = w["corrections"]
    return page(f"{t['thanks_heading']} – {w['site']['name']}",
                f"<h1>{esc(t['thanks_heading'])}</h1><p>{esc(t['thanks'])}</p>", w, depth=1)


def privacy_html(w: dict) -> str:
    t = w["privacy"]
    body = f"<h1>{esc(t['heading'])}</h1>" + "".join(f"<h2>{esc(h)}</h2><p>{esc(x)}</p>" for h, x in t["sections"])
    return page(f"{t['heading']} – {w['site']['name']}", body, w, depth=1)


# Your rights -----------------------------------------------------------------------------------------------------------


def rights_html(w: dict) -> str:
    r = load_toml("rights.toml")
    parts = [f"<h1>{esc(r['heading'])}</h1>"] + [f"<p>{esc(x)}</p>" for x in r["intro"]]
    parts.append(f'<p class="warn">{esc(w["card"]["refusal"])}</p>')
    for sec in r["section"]:
        parts.append(f"<h2>{esc(sec['heading'])}</h2>")
        for para in sec["text"]:
            parts.append(f"<p>{esc(para)}</p>")
        if sec.get("list"):
            parts.append('<ul class="list">' + "".join(f"<li>{esc(x)}</li>" for x in sec["list"]) + "</ul>")
        if sec.get("note"):
            parts.append(f"<p>{esc(sec['note'])}</p>")
        links = " · ".join(f'<a href="{esc(u)}">{esc(label)}</a>' for label, u in sec["sources"])
        parts.append(f'<p class="src">Sources: {links}. Checked {esc(nice_date(sec["checked"]))}; to be checked again by '
                     f'{esc(nice_date(sec["recheck"]))}.</p>')
    parts.append(f'<p class="hint">{esc(r["not_advice"])}</p>')
    return page(f"{r['heading']} – {w['site']['name']}", "".join(parts), w, depth=1)


# About, terms, accessibility, not found; robots.txt and the sitemap -------------------------------------------------


def _fill_site(text: str, settings: Settings, w: dict, extra: dict | None = None) -> str:
    site = settings.section("site")
    values = {"site": w["site"]["name"], "parent": site.get("parent_name", "Where They Stand"),
              "operator": site.get("operator", ""), "contact": site.get("contact", ""),
              "url": (site.get("url") or "the site's address").removeprefix("https://"), **(extra or {})}
    return text.format(**values)


def text_page(settings: Settings, w: dict, key: str, extra: dict | None = None) -> str:
    t = load_toml("pages.toml")[key]
    parts = [f"<h1>{esc(t['heading'])}</h1>"]
    if t.get("short"):
        parts.append(f"<p><strong>{esc(t['short'])}</strong></p>")
    if t.get("updated"):
        parts.append(f'<p class="hint">Last updated {esc(nice_date(t["updated"]))}.</p>')
    for heading, paras in t["sections"]:
        parts.append(f"<h2>{esc(heading)}</h2>")
        parts += [f"<p>{esc(_fill_site(x, settings, w, extra))}</p>" for x in paras]
    return page(f"{t['heading']} – {w['site']['name']}", "".join(parts), w, depth=1)


def not_found_html(w: dict) -> str:
    t = load_toml("pages.toml")["not_found"]
    # Served for any missing address, at any depth, so its links start from the site's root.
    body = f'<h1>{esc(t["heading"])}</h1><p>{esc(t["text"])}</p><p><a href="/index.html">{esc(w["search"]["heading"])}</a></p>'
    return page(f"{t['heading']} – {w['site']['name']}", body, w, depth=0).replace('href="styles.css"', 'href="/styles.css"') \
        .replace('href="icon.svg"', 'href="/icon.svg"').replace('href="index.html"', 'href="/index.html"')


def robots_and_sitemap(settings: Settings, out: Path) -> None:
    """While the site is a test version, crawlers are asked to stay away. Once launched, they get a sitemap."""
    from landlords.site import launched

    site = settings.section("site")
    if not launched():
        (out / "robots.txt").write_text("# A test version, not yet public.\nUser-agent: *\nDisallow: /\n")
        return
    url = (site.get("url") or "").rstrip("/")
    if not url.startswith("https://"):
        raise RuntimeError("[site] launched is true but [site] url is not set (https://…): see docs/LAUNCH.md")
    pages = sorted(p.relative_to(out).as_posix() for p in out.rglob("index.html"))
    locs = "".join(f"<url><loc>{url}/{p.removesuffix('index.html')}</loc></url>" for p in pages)
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                     f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>\n')
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: {url}/sitemap.xml\n")


def build_extra(settings: Settings, profiles: list[dict], out: Path, w: dict) -> dict:
    """Write every page except the profiles and the method page."""
    import shutil

    from landlords.register import aliases, landlords

    for name in ("search.js", "compare.js", "icon.svg"):
        shutil.copy(STATIC / name, out / name)
    (out / "names.json").write_text(json.dumps(names_json(profiles, landlords(), aliases(), w),
                                               separators=(",", ":")))
    (out / "index.html").write_text(index_html(profiles, w))

    sources = json.loads((settings.staging_dir / "sources.json").read_text())
    areas = area_rows(settings, profiles)
    for a in areas.values():
        d = out / "areas" / a["slug"]
        d.mkdir(parents=True)
        (d / "index.html").write_text(area_html(a, w, sources))
    (out / "areas" / "index.html").write_text(areas_index_html(areas, w))

    (out / "data" / "landlords").mkdir(parents=True)
    for p in profiles:
        (out / "data" / "landlords" / f"{p['slug']}.json").write_text(
            json.dumps(landlord_json(p, w), separators=(",", ":")))
    (out / "compare").mkdir()
    (out / "compare" / "index.html").write_text(compare_html(w))

    files = downloads(settings, profiles, out, w)
    (out / "data" / "index.html").write_text(downloads_html(files, w))

    for name, html in (("corrections", corrections_html(w)), ("privacy", privacy_html(w)), ("rights", rights_html(w))):
        (out / name).mkdir(exist_ok=True)
        (out / name / "index.html").write_text(html)
    (out / "corrections" / "thanks.html").write_text(thanks_html(w))
    acc = load_toml("pages.toml")["accessibility"]
    for name in ("about", "terms", "accessibility"):
        (out / name).mkdir(exist_ok=True)
        (out / name / "index.html").write_text(text_page(settings, w, name, {
            "tested": nice_date(acc["tested"]) if acc.get("tested") else "not yet",
            "tested_how": acc.get("tested_how", "")}))
    (out / "404.html").write_text(not_found_html(w))
    robots_and_sitemap(settings, out)
    return {"areas": len(areas), "downloads": len(files)}
