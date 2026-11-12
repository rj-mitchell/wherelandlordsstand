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
from landlords.sisters import council_url, councils_covered
from landlords.site import band_name, esc, fill, fill_html, nice_date, page, rich, sister_link, stack_table
from landlords.statements import slot

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
    text = json.dumps({"none": s["none"], "small": s["small"], "areas": s["areas_link"],
                       **{k: s[k] for k in ("found_one", "found", "found_none", "found_small")}})
    parts = [f"<h1>{esc(s['heading'])}</h1><p>{esc(s['intro'])}</p>",
             f'<form id="search" role="search" data-root=""><label for="q">{esc(s["label"])}</label>'
             f'<input id="q" name="q" type="search" autocomplete="off" placeholder="{esc(s["placeholder"])}" '
             f'aria-describedby="q-hint"><p class="hint" id="q-hint">{esc(s["hint"])}</p></form><ul id="results" class="results"></ul>'
             # the number found, for screen readers, rather than the list, which changes with every letter typed
             '<p id="results-status" class="sr-only" role="status" aria-live="polite"></p>'
             f'<script type="application/json" id="search-text">{text}</script>'
             f'<noscript><p>{esc(s["noscript"])}</p></noscript>',
             f'<p><a href="areas/index.html">{esc(s["areas_link"])}</a></p>',
             f"<h2>{esc(s['all'])}</h2><p>{fill(s['count'], count=len(profiles))}</p>"]
    for letter, ps in by_letter.items():
        items = "".join(f'<li><a href="landlords/{esc(p["slug"])}/index.html">{esc(p["name"])}</a></li>' for p in ps)
        parts.append(f'<h3>{esc(letter)}</h3><ul class="az">{items}</ul>')
    return page(w["site"]["name"], "".join(parts), w, depth=0, scripts=("search.js",), here="index.html",
                path="")


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
        a["council_url"] = council_url(settings, a["gss"])
        a["council_name"] = councils_covered().get(a["gss"], "")
    return areas


def area_html(a: dict, w: dict, sources: dict) -> str:
    from landlords.site import Sources

    t = w["area"]
    src = Sources([{"sha": s, **sources.get(s, {})} for s in sorted(a["sources"])])
    rows = []
    for p, homes, basis in a["landlords"]:
        g = p["grade"].get("grade") or "–"
        b = p["bands"].get("headline", {}) if p["bands"] else {}
        rows.append(f'<tr role="row"><td role="cell"><a href="../../landlords/{esc(p["slug"])}/index.html">{esc(p["name"])}</a>'
                    f'{" *" if basis == "council total" else ""}</td>'
                    f'<td role="cell" class="n" data-label="{esc(t["homes"])}">{homes:,.0f}</td>'
                    f'<td role="cell" data-label="{esc(t["grade"])}">{esc(g)}</td>'
                    f'<td role="cell" data-label="{esc(t["overall"])}">{esc(band_name(b.get("band")) or "–")}</td></tr>')
    # On a phone each row is drawn as a block, each figure under its heading (stack_table)
    body = (f"<h1 id=\"area\">{esc(a['name'])}</h1><p>{fill(t['intro'], count=len(a['landlords']))}</p>"
            f'<div class="scroll" tabindex="0" role="region" aria-labelledby="area">'
            + stack_table([t["landlord"], t["homes"], t["grade"], t["overall"]], rows, numeric=(1,)) + "</div>"
            + f'<p class="hint">{esc(t["notes"])}</p>'
            + (f'<p class="hint">* {esc(t["council_note"])}</p>' if any(x[2] == "council total" for x in a["landlords"]) else "")
            + f'<p class="warn">{esc(w["card"]["refusal"])}</p>' + src.ref(*a["sources"])
            # statements from landlords about this page, in their own words (src/landlords/statements.py)
            + slot("page")
            + sister_link(a.get("council_url", ""), fill(t["council_link"], council=a.get("council_name", "")))
            + src.html(w))
    return page(f"{a['name']} – {w['site']['name']}", body, w, depth=2, here="areas/index.html", path=f"areas/{a['slug']}/",
                description=fill(t["intro"], count=len(a["landlords"])))


def areas_index_html(areas: dict[str, dict], w: dict) -> str:
    t = w["area"]
    items = "".join(f'<li><a href="{esc(a["slug"])}/index.html">{esc(a["name"])}</a> '
                    f'<span class="hint">({len(a["landlords"])})</span></li>'
                    for a in sorted(areas.values(), key=lambda a: a["name"]))
    body = f"<h1>{esc(t['heading'])}</h1><p>{esc(t['index_intro'])}</p><ul class=\"az\">{items}</ul>"
    return page(f"{t['heading']} – {w['site']['name']}", body, w, depth=1, here="areas/index.html", path="areas/")


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
    body = (f"<h1 id=\"compare-heading\">{esc(t['heading'])}</h1><p>{esc(t['intro'])}</p>"
            f'<div id="compare" data-root="../"><label for="add">{esc(t["add"])}</label>'
            f'<input id="add" type="search" autocomplete="off"><ul id="suggest" class="results"></ul>'
            f'<ul id="picks" class="results" aria-live="polite"></ul><div id="table"></div></div>'
            f'<script type="application/json" id="compare-text">{json.dumps(text)}</script>'
            f'<noscript><p>{esc(t["noscript"])}</p></noscript><p class="warn">{esc(w["card"]["refusal"])}</p>')
    return page(f"{t['heading']} – {w['site']['name']}", body, w, depth=1, scripts=("search.js", "compare.js"), path="compare/",
                here="compare/index.html")


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
    return page(f"{t['heading']} – {w['site']['name']}", body, w, depth=1, path="data/")


# Corrections, "If you're named" and privacy ---------------------------------------------------------------------------


def corrections_html(w: dict) -> str:
    """The corrections page: the response times, a link to "If you're named", and the report form, whose options are the
    impartiality policy's routes (7.1) by the family glossary's names. ?kind= and ?page= in a link to it choose an
    option and fill in the page, when the page is served by the site's API (api.prefill)."""
    t = w["corrections"]
    named = fill_html(t["named"], named=f'<a href="../named/index.html">{esc(t["named_link"])}</a>')
    kinds = "".join(
        f'<div class="choice"><input type="radio" id="kind-{v}" aria-describedby="kind-{v}-hint" name="kind" '
        f'value="{v}"{" checked" if i == 0 else ""}><label for="kind-{v}">{esc(label)}</label>'
        f'<p class="hint" id="kind-{v}-hint">{esc(hint)}</p></div>' for i, (v, label, hint) in enumerate(t["kinds"]))
    body = (f"<h1>{esc(t['heading'])}</h1>" + "".join(f"<p>{esc(x)}</p>" for x in t["intro"]) +
            f'<p class="times"><strong>{esc(t["times"])}</strong> {esc(t["times_note"])}</p>'
            f'<p>{named}</p>'
            f'<form id="report" method="post" action="../api/corrections"><fieldset><legend>{esc(t["kind"])}</legend>'
            f'{kinds}</fieldset><label for="page">{esc(t["page"])}</label>'
            f'<input id="page" name="page" value="" type="text" maxlength="300" autocomplete="off" '
            f'aria-describedby="page-hint"><p class="hint" id="page-hint">{esc(t["page_hint"])}</p>'
            f'<label for="message">{esc(t["message"])}</label><textarea id="message" name="message" rows="6" '
            f'maxlength="4000" required></textarea><label for="email">{esc(t["email"])}</label>'
            f'<input id="email" name="email" type="email" maxlength="200" autocomplete="email" '
            f'aria-describedby="email-hint"><p class="hint" id="email-hint">{esc(t["email_hint"])}</p>'
            f'<p><button type="submit">{esc(t["send"])}</button></p></form>')
    # The form posts to the site's small API (src/landlords/api.py), which serves every page, so it always works for
    # readers. Opened as plain files, without `landlords serve`, it can't send (docs/OPERATIONS.md).
    from landlords.config import STATIC_DIR

    with open(STATIC_DIR / "corrections.csv", newline="", encoding="utf-8") as fh:
        log = list(csv.DictReader(fh))
    body += f"<h2 id=\"log\">{esc(t['log_heading'])}</h2>"
    if log:
        rows = "".join(f"<tr><td>{esc(r['date'])}</td><td>{esc(r['page'])}</td><td>{esc(r['what_was_wrong'])}</td>"
                       f"<td>{esc(r['what_we_did'])}</td></tr>" for r in reversed(log))
        body += (f'<div class="scroll" tabindex="0" role="region" aria-labelledby="log"><table><thead><tr><th scope="col">Date</th><th scope="col">Page</th>'
                 f'<th scope="col">What was wrong</th><th scope="col">What we did</th></tr></thead>'
                 f"<tbody>{rows}</tbody></table></div>")
    else:
        body += f"<p>{esc(t['log_empty'])}</p>"
    return page(f"{t['heading']} – {w['site']['name']}", body, w, depth=1, path="corrections/")


def statement_form(w: dict) -> str:
    """The form for a statement in a landlord's own words (src/landlords/statements.py), on the "If you're named"
    page. It works without JavaScript: it posts to the site's API, then goes to a thank-you page. The browser checks
    what it can (required fields, an email address, a web address); the API checks the rest, such as the 150 words.
    The hidden field ("Leave this empty") is for robots: a statement with it filled in is thanked and dropped."""
    from landlords.statements import LIMITS, PARTS

    t = w["statement"]
    parts = {"grade": w["grade"]["heading"], "bands": w["bands"]["heading"], "ombudsman": w["ombudsman"]["heading"],
             "safety": w["safety"]["heading"]}
    options = f'<option value="">{esc(t["part_whole"])}</option>' + "".join(
        f'<option value="{p}">{esc(parts[p])}</option>' for p in PARTS)

    def field(name: str, label: str, attrs: str, hint: str = "", fid: str = "") -> str:
        fid = fid or f"st-{name}"
        described = f' aria-describedby="{fid}-hint"' if hint else ""
        return (f'<label for="{fid}">{esc(label)}</label><input id="{fid}" name="{name}"{attrs}{described}>'
                + (f'<p class="hint" id="{fid}-hint">{esc(hint)}</p>' if hint else ""))

    return (f'<h3 id="send">{esc(t["form_heading"])}</h3>'
            f'<form id="statement" method="post" action="../api/statements">'
            + field("name", t["name"], f' type="text" maxlength="{LIMITS["name"]}" autocomplete="name" required')
            + field("role", t["role"], f' type="text" maxlength="{LIMITS["role"]}" autocomplete="organization-title" '
                    'required', t["role_hint"])
            # id="page" with an empty value, as on the report form, so ?page= can fill it in (api.prefill)
            + field("page", t["page"], f' value="" type="text" inputmode="url" maxlength="{LIMITS["page"]}" '
                    'autocomplete="off" required', t["page_hint"], fid="page")
            + f'<label for="st-part">{esc(t["part"])}</label><select id="st-part" name="part">{options}</select>'
            + f'<label for="st-text">{esc(t["text"])}</label><textarea id="st-text" name="text" rows="8" '
              f'maxlength="{LIMITS["text"]}" required aria-describedby="st-text-hint"></textarea>'
              f'<p class="hint" id="st-text-hint">{esc(t["text_hint"])}</p>'
            + field("link", t["link"], f' type="url" maxlength="{LIMITS["link"]}" autocomplete="url"', t["link_hint"])
            + field("email", t["email"], f' type="email" maxlength="{LIMITS["email"]}" autocomplete="email" required',
                    t["email_hint"])
            + f'<div class="hp" aria-hidden="true"><label for="st-website">{esc(t["honeypot"])}</label>'
              f'<input id="st-website" name="website" type="text" tabindex="-1" autocomplete="off"></div>'
            + f'<p><button type="submit">{esc(t["send"])}</button></p><p class="hint">{esc(t["after"])}</p></form>')


def named_html(settings: Settings, w: dict) -> str:
    """"If you're named" (config/pages.toml, [named]): for landlords this site names, and people acting for them. The
    impartiality policy's three routes (7.1), each with a way to start it, what is covered on this site, what a
    statement can say and how it is shown (7.2), how identity is checked, the response times (7.3), and who decides and
    how to appeal (7.4). Its address, named/, is the one the charity's own page links to."""
    from landlords.statements import render

    t = load_toml("pages.toml")["named"]
    example = render({"id": "example", "name": t["example"]["name"], "date": t["example"]["date"],
                      "role": t["example"]["role"], "text": t["example"]["text"], "link": ""}, w, 4)

    def para(x: str | list) -> str:
        if isinstance(x, list):
            return '<ul class="list">' + "".join(f"<li>{rich(_fill_site(i, settings, w), '../')}</li>" for i in x) + "</ul>"
        if x == "@example":
            return example
        if x == "@form":
            return statement_form(w)
        return f"<p>{rich(_fill_site(x, settings, w), '../')}</p>"

    parts = [f"<h1>{esc(t['heading'])}</h1>"] + [para(x) for x in t["intro"]]
    parts.append(f'<p class="times"><strong>{esc(w["corrections"]["times"])}</strong></p>')
    contents = "".join(f'<li><a href="#{esc(s["id"])}">{esc(s["heading"])}</a></li>' for s in t["section"])
    parts.append(f'<nav aria-labelledby="contents"><h2 id="contents" class="sr-only">{esc(t["contents"])}</h2>'
                 f'<ul class="contents">{contents}</ul></nav>')
    for s in t["section"]:
        parts.append(f'<h2 id="{esc(s["id"])}">{esc(s["heading"])}</h2>')
        parts += [para(x) for x in s.get("text", [])]
        for heading, text, start, href in s.get("routes", []):
            parts.append(f"<h3>{esc(heading)}</h3><p>{rich(_fill_site(text, settings, w), '../')}</p>"
                         f'<p class="go">{rich(f"[{start}]({href})", "../")}</p>')
        for heading, paras in s.get("parts", []):
            parts.append(f"<h3>{esc(heading)}</h3>" + "".join(para(x) for x in paras))
    return page(f"{t['heading']} – {w['site']['name']}", "".join(parts), w, depth=1, path="named/",
                description=t["description"])


def named_thanks_html(w: dict) -> str:
    t = w["statement"]
    return page(f"{t['thanks_heading']} – {w['site']['name']}",
                f"<h1>{esc(t['thanks_heading'])}</h1><p>{esc(t['thanks'])}</p>"
                f'<p class="times"><strong>{esc(w["corrections"]["times"])}</strong></p>'
                f'<p><a href="index.html">{esc(load_toml("pages.toml")["named"]["heading"])}</a></p>', w, depth=1,
                path="named/thanks.html")


def thanks_html(w: dict) -> str:
    t = w["corrections"]
    return page(f"{t['thanks_heading']} – {w['site']['name']}",
                f"<h1>{esc(t['thanks_heading'])}</h1><p>{esc(t['thanks'])}</p>"
                f'<p class="times"><strong>{esc(t["times"])}</strong> {esc(t["times_note"])}</p>', w, depth=1,
                path="corrections/thanks.html")


def privacy_html(w: dict) -> str:
    t = w["privacy"]
    body = f"<h1>{esc(t['heading'])}</h1>" + "".join(f"<h2>{esc(h)}</h2><p>{esc(x)}</p>" for h, x in t["sections"])
    return page(f"{t['heading']} – {w['site']['name']}", body, w, depth=1, path="privacy/")


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
    return page(f"{r['heading']} – {w['site']['name']}", "".join(parts), w, depth=1, here="rights/index.html",
                path="rights/")


# About, terms, accessibility, not found; robots.txt and the sitemap -------------------------------------------------


def _fill_site(text: str, settings: Settings, w: dict, extra: dict | None = None) -> str:
    site = settings.section("site")
    values = {"site": w["site"]["name"], "parent": site.get("parent_name", "Where They Stand"),
              "operator": site.get("operator", ""), "contact": site.get("contact", ""),
              "url": (site.get("url") or "the site's address").removeprefix("https://"), **(extra or {})}
    return text.format(**values)


def text_page(settings: Settings, w: dict, key: str, extra: dict | None = None) -> str:
    """A page from config/pages.toml. Each section is a heading and its paragraphs; a paragraph that is itself a list
    of sentences is shown as a bulleted list. [Words](address) in a sentence become a link (``site.rich``)."""
    t = load_toml("pages.toml")[key]

    def para(x: str | list) -> str:
        if isinstance(x, list):
            return '<ul class="list">' + "".join(f"<li>{rich(_fill_site(i, settings, w, extra), '../')}</li>"
                                                 for i in x) + "</ul>"
        return f"<p>{rich(_fill_site(x, settings, w, extra), '../')}</p>"

    parts = [f"<h1>{esc(t['heading'])}</h1>"]
    if t.get("short"):
        parts.append(f"<p><strong>{esc(t['short'])}</strong></p>")
    if t.get("updated"):
        parts.append(f'<p class="hint">Last updated {esc(nice_date(t["updated"]))}.</p>')
    for heading, paras in t["sections"]:
        parts.append(f"<h2>{esc(heading)}</h2>")
        parts += [para(x) for x in paras]
    return page(f"{t['heading']} – {w['site']['name']}", "".join(parts), w, depth=1, path=f"{key}/")


# The press page's logo files, at addresses that don't change, so they can be linked to. The mark is the one in the
# masthead (site.MARK), in four files that keep their plain names (src/landlords/static/): mark.svg and mark-dark.svg
# (on the lifted slate), and mark-small.svg and mark-small-dark.svg for 16 to 32 pixels. The icon and link card are
# the family kit's.
PRESS_MARKS = ("mark.svg", "mark-dark.svg", "mark-small.svg", "mark-small-dark.svg")
PRESS_FILES = {"where-landlords-stand-icon.svg": "icon.svg", "where-landlords-stand-icon-512.png": "icon-512.png",
               "where-landlords-stand-card.png": "card.png"}


def press(settings: Settings, profiles: list[dict], areas: dict, out: Path, w: dict) -> None:
    """The press page (config/pages.toml, [press]): contact, facts in brief, how to cite a landlord's page, and the
    logo files beside it."""
    import shutil
    from datetime import date

    from landlords.site import FAMILY, STATIC

    folder = out / "press"
    folder.mkdir(exist_ok=True)
    for name in PRESS_MARKS:
        shutil.copy(STATIC / name, folder / name)
    for name, kit in PRESS_FILES.items():
        shutil.copy(FAMILY / kit, folder / name)
    example = next((p for p in profiles if p["slug"] == "abri-group"), profiles[0] if profiles else None)
    (folder / "index.html").write_text(text_page(settings, w, "press", {
        "profiles": f"{len(profiles):,}", "areas": f"{len(areas):,}", "today": nice_date(date.today()),
        "example_name": example["name"] if example else "",
        "example_url": f"{(settings.section('site').get('url') or '').rstrip('/')}/landlords/{example['slug']}/"
                       if example else ""}))


def not_found_html(w: dict) -> str:
    t = load_toml("pages.toml")["not_found"]
    # Served for any missing address, at any depth, so its links start from the site's root.
    body = f'<h1>{esc(t["heading"])}</h1><p>{esc(t["text"])}</p><p><a href="/index.html">{esc(w["search"]["heading"])}</a></p>'
    import re

    text = page(f"{t['heading']} – {w['site']['name']}", body, w, depth=0)
    return re.sub(r'(href|src)="(?![a-z]+:|/|#)', r'\1="/', text)   # every link and file from the site's root


def robots_and_sitemap(settings: Settings, out: Path) -> None:
    """Until the site is launched, crawlers are asked to stay away. Once launched, they get a sitemap."""
    from landlords.site import launched

    site = settings.section("site")
    if not launched():
        (out / "robots.txt").write_text("# Not launched yet: please don't index.\nUser-agent: *\nDisallow: /\n")
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
    """Write every page except the profiles and the method page (the stylesheet, scripts and fonts are in assets/,
    written by ``site.write_assets``)."""
    from landlords.register import aliases, landlords

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
    (out / "named").mkdir(exist_ok=True)
    (out / "named" / "index.html").write_text(named_html(settings, w))
    (out / "named" / "thanks.html").write_text(named_thanks_html(w))
    acc = load_toml("pages.toml")["accessibility"]
    for name in ("about", "terms", "accessibility"):
        (out / name).mkdir(exist_ok=True)
        (out / name / "index.html").write_text(text_page(settings, w, name, {
            "tested": nice_date(acc["tested"]) if acc.get("tested") else "not yet",
            "tested_how": acc.get("tested_how", "")}))
    press(settings, profiles, areas, out, w)
    from landlords import status

    status.write(settings, out, w)
    (out / "404.html").write_text(not_found_html(w))
    robots_and_sitemap(settings, out)
    return {"areas": len(areas), "downloads": len(files)}
