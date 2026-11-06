"""The pages, written as static HTML to ``data/site/`` (`landlords build`), and served locally (`landlords serve`).

Every page reads without JavaScript, sets no cookies and loads nothing from anywhere else. Every sentence comes from
config/wording.toml. Every figure links to the published file it comes from, listed at the foot of the page.
"""

from __future__ import annotations

import html
import shutil
from collections import Counter
from datetime import date
from pathlib import Path

from landlords.config import Settings, load_toml
from landlords.profile import build_profiles
from landlords.score import rules

# The stylesheet, a file of its own (docs/DESIGN.md). The build gives it a fingerprinted name (``build`` below).
CSS_FILE = Path(__file__).parent / "static" / "styles.css"


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def fill(template: str, **values) -> str:
    """A wording.toml sentence with its {placeholders} filled, escaped for HTML."""
    return esc(template.format(**values))


def pct(v: float | None) -> str:
    return "–" if v is None else f"{v:.1f}%"


def nice_date(d) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return f"{d.day} {d:%B %Y}" if d else ""


class Sources:
    """Numbers the files a page uses, and gives the link for each figure."""

    def __init__(self, sources: list[dict]):
        self.items = sources
        self.number = {s["sha"]: i + 1 for i, s in enumerate(sources)}

    def ref(self, *shas: str) -> str:
        nums = sorted({self.number[s] for s in shas if s in self.number})
        if not nums:
            return ""
        links = ", ".join(f'<a href="#source-{n}">[{n}]</a>' for n in nums)
        return f'<p class="src">Source: {links}</p>'

    def html(self, w: dict) -> str:
        if not self.items:
            return ""
        lis = []
        for i, s in enumerate(self.items, 1):
            title = esc(s.get("title") or s.get("file", ""))
            lis.append(
                f'<li id="source-{i}">{esc(s.get("publisher", ""))}, <a href="{esc(s.get("page", ""))}">{title}</a>'
                f' ({esc(s.get("period", ""))}). <a href="{esc(s.get("url", ""))}">The file</a>, fetched '
                f'{esc(s.get("fetched_at", "")[:10])}. {esc(s.get("licence", ""))}.</li>')
        return (f'<section aria-labelledby="sources"><h2 id="sources">{esc(w["sources"]["heading"])}</h2>'
                f'<p>{esc(w["sources"]["intro"])}</p><ol class="sources">{"".join(lis)}</ol></section>')


NAV = [("index.html", "Find a landlord"), ("areas/index.html", "Areas"), ("compare/index.html", "Compare"),
       ("rights/index.html", "Your rights"), ("method/index.html", "How we compare")]


_LAUNCHED = False
_SITE: dict = {}
# The stylesheet's, scripts' and icon's names for this build, each with a fingerprint of its content
# ("styles.3f9a2c1d.css"): a changed file gets a new name, so no cache (Cloudflare's, a browser's) can serve the old one.
_ASSETS: dict[str, str] = {}


def asset(name: str) -> str:
    return _ASSETS.get(name, name)


def fingerprint(name: str, content: bytes) -> str:
    import hashlib

    stem, _, ext = name.rpartition(".")
    return f"{stem}.{hashlib.sha256(content).hexdigest()[:10]}.{ext}"


def alpha_banner(words: dict) -> str:
    """The alpha strip at the top of every page, while [site] stage = "alpha", as on the sibling sites: its label
    (the words before the colon) as a chip, and the feedback address as a link."""
    if _SITE.get("stage") != "alpha" or not words.get("alpha"):
        return ""
    email = _SITE.get("feedback_email") or _SITE.get("contact", "")
    before, _, after = words["alpha"].partition("{email}")
    label, _, rest = before.partition(":")
    link = f'<a href="mailto:{esc(email)}">{esc(email)}</a>' if email else ""
    rest = rest.strip()
    rest = rest[:1].upper() + rest[1:]                       # "Alpha: this site…" reads "ALPHA This site…"
    return (f'<div class="strip"><p class="wrap alpha"><span class="chip">{esc(label)}</span>{esc(rest)} '
            f'{link}{esc(after)}</p></div>')


MARK = ('<svg class="mark" viewBox="0 0 64 64" aria-hidden="true" focusable="false">'
        '<path class="mk-roof" d="M8 29 32 10l24 19"/><rect class="mk-book" x="17" y="29" width="30" height="27"/>'
        '<path class="mk-band" d="M17 36h30M17 40h30"/><path class="mk-shelf" d="M6 57.5h52"/></svg>')


def launched() -> bool:
    """The launch switch, [site] launched in config/settings.toml (docs/LAUNCH.md), as set by the current build."""
    return _LAUNCHED


def page(title: str, body: str, w: dict, depth: int, description: str = "", scripts: tuple[str, ...] = (),
         here: str = "") -> str:
    """A whole page: our own stylesheet, fonts and scripts only, nothing from anywhere else. ``here`` is the NAV entry
    this page belongs to, marked as the current tab."""
    up = "../" * depth
    live = launched()
    nav = "".join(f'<a href="{up}{href}"{' aria-current="page"' if href == here else ""}>{esc(label)}</a>'
                  for href, label in NAV)
    js = "".join(f'<script src="{up}{asset(src)}" defer></script>' for src in scripts)
    site = w["site"]
    return f"""<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description or site['tagline'])}">
{"" if live else '<meta name="robots" content="noindex">'}<link rel="icon" href="{up}{asset('icon.svg')}" type="image/svg+xml">
<link rel="preload" href="{up}fonts/source-serif-4-normal-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{up}{asset('styles.css')}">{js}</head>
<body><a class="skip" href="#main">Skip to content</a>{alpha_banner(site)}
<header class="mast"><div class="wrap mast-in"><a class="brand" href="{up}index.html">{MARK}<span>
<span class="name">{esc(site['name'])}</span><span class="tag">{esc(site['tagline'])}</span></span></a>
<p class="indep">{esc(site['independence'])}</p></div>
<nav class="tabs wrap" aria-label="Main">{nav}</nav></header>
<main id="main" class="wrap">{body}</main>
<footer class="wrap"><p>{esc(site['parent'])}</p>
<p><a href="{up}about/index.html">About</a> · <a href="{up}corrections/index.html">Report a mistake</a> ·
<a href="{up}data/index.html">Download the data</a> · <a href="{up}terms/index.html">Terms</a> ·
<a href="{up}privacy/index.html">Privacy</a> · <a href="{up}accessibility/index.html">Accessibility</a></p></footer>
</body></html>
"""


def meter(b: int | None) -> str:
    cells = "".join(f'<i class="{"on" if b and i < b else ""}"></i>' for i in range(4))
    return f'<span class="meter" aria-hidden="true">{cells}</span>'


def band_name(b: int | None) -> str:
    return rules()["scoring"]["bands"][b - 1] if b else ""


def profile_html(p: dict, w: dict) -> str:
    src = Sources(p["sources"])
    name = p["name"]
    out = [f"<h1>{esc(name)}</h1>"]
    sub = [w["types"].get(p["type"], p["type"].capitalize())]
    if p["also_known_as"]:
        sub.append("also known as " + ", ".join(p["also_known_as"]))
    out.append(f'<p class="sub">{esc("; ".join(sub))}.</p>')
    if p["status"] == "merged" and p["successor"]:
        link = f'../{esc(p["successor"]["slug"])}/index.html' if p["successor"].get("slug") else ""
        text = fill(w["card"]["merged"], name=name, successor=p["successor"]["name"],
                    date=nice_date(p["successor"]["date"]))
        out.append(f'<p class="note">{text} ' + (f'<a href="{link}">{esc(p["successor"]["name"])}</a>' if link else "")
                   + "</p>")

    # The card --------------------------------------------------------------------------------------------------------
    card = [f'<section class="card" aria-labelledby="card"><h2 id="card">{esc(w["card"]["heading"])}</h2>']
    card.append(f'<p class="warn">{esc(w["card"]["refusal"])}</p>')
    if p["homes"]:
        card.append(f'<section><p>{fill(w["card"]["homes"], homes=f"{p["homes"]["homes"]:,.0f}")} '
                    f'{fill(w["card"]["homes_note"], period=p["homes"]["period"])}</p>'
                    f'{src.ref(p["homes"]["source"])}</section>')

    g = p["grade"]
    gs = [f'<h3>{esc(w["grade"]["heading"])}</h3>']
    if g.get("grade"):
        if g["by"] == p["id"]:
            gs.append(f'<p class="grade">{esc(g["grade"])}</p><p>{fill(w["grade"]["graded"], name=name, grade=g["grade"], date=nice_date(g["date"]))}</p>')
        else:
            gs.append(f'<p class="grade">{esc(g["grade"])}</p><p>{fill(w["grade"]["group_graded"], group=g["by_name"], name=name, grade=g["grade"], date=nice_date(g["date"]))}</p>')
        gs.append(f'<p>{esc(w["grade"].get(g["grade"], ""))} {esc(w["grade"]["scale"])}</p>')
    else:
        gs.append(f'<p>{fill(w["grade"]["not_graded"], name=name)}</p>')
    if g.get("under_review"):
        gs.append(f'<p>{fill(w["grade"]["under_review"], name=name, date=nice_date(g["under_review"]["date"]))}</p>')
    if g.get("enforcement"):
        gs.append(f'<p>{fill(w["grade"]["enforcement"], name=name, date=nice_date(g["enforcement"]["date"]))}</p>')
    shas = [g.get("source", "")] + [g[k]["source"] for k in ("under_review", "enforcement") if g.get(k)]
    card.append("<section>" + "".join(gs) + src.ref(*shas) + "</section>")

    b = p["bands"]
    bs = [f'<h3>{esc(w["bands"]["heading"])}</h3>']
    peer = b.get("peer")
    if peer and (b["headline"]["band"] or any(x["band"] for x in b["pillars"])):
        bs.append(f'<p>{fill(w["bands"]["intro"], name=name, peers=peer["peers"] - 1, peer_label=peer["peer_group_label"], period=b["period"])}</p>')
        for item, is_head in [(b["headline"], True)] + [(x, False) for x in b["pillars"]]:
            if item["band"]:
                text = fill(w["bands"]["headline"] if is_head else w["bands"]["pillar"], label=item["label"],
                            band=band_name(item["band"]), value=pct(item["value"]))
                t = item.get("trend")
                trend = ""
                if t:
                    key = "up" if t["direction"] == "up" else "down"
                    trend = f' <span class="trend">{"↑" if key == "up" else "↓"} {fill(w["bands"][key], old_band=band_name(t["old_band"]), old_period=t["old_period"])}</span>'
                bs.append(f'<p class="band">{meter(item["band"])}<span>{text}{trend}</span></p>')
            else:
                bs.append(f'<p class="band">{meter(None)}<span>{fill(w["bands"]["not_scored"], label=item["label"])}</span></p>')
        bs.append(f'<p class="src">{esc(w["bands"]["explain"])}</p>')
    else:
        bs.append(f'<p>{fill(w["bands"]["no_results"], name=name, period=b.get("period", ""))}</p>')
        why = p.get("reporting")
        if why and why["reason"] == "small":
            bs.append(f'<p class="note">{fill(w["bands"]["too_small"], name=name, year="20" + why["from_period"][-2:])}</p>')
        elif why and why.get("other"):
            other = why["other"]
            link = (f'<a href="../{esc(other["slug"])}/index.html">{esc(other["name"])}</a>' if other.get("slug")
                    else esc(other["name"]))
            key = "in_group" if why["reason"] == "group" else "in_other"
            bs.append(f'<p class="note">{fill(w["bands"][key], name=name, period=why["from_period"], other="@@OTHER@@").replace("@@OTHER@@", link)}</p>')
    for n in p["regulator_notes"]:
        bs.append(f'<p class="note">{fill(w["bands"]["regulator_note"], note=n["note"])}</p>')
    if p["survey_note"]:
        labels = rules()["survey_method"]["labels"]
        bs.append(f'<p class="note">{fill(w["method_note"]["text"], name=name, method=labels.get(p["survey_note"]["method"], p["survey_note"]["method"]), peer_method=labels.get(p["survey_note"]["peer_method"], p["survey_note"]["peer_method"]))}</p>')
    card.append("<section>" + "".join(bs) + src.ref(b.get("source", "")) + "</section>")

    om = p["ombudsman"]
    os_ = [f'<h3>{esc(w["ombudsman"]["heading"])}</h3>']
    if om["reports"]:
        for r in om["reports"]:
            os_.append("<p>" + fill(w["ombudsman"]["report"], period=r["period"], published_name=r["name"],
                                    findings=f'{r.get("findings_in_jurisdiction", 0):,.0f}',
                                    rate=f'{100 * r.get("maladministration_rate", 0):.0f}%'))
            if r.get("compensation"):
                os_.append(" " + fill(w["ombudsman"]["compensation"], amount=f'£{r["compensation"]:,.0f}'))
            if r.get("severe_maladministration"):
                os_.append(" " + fill(w["ombudsman"]["severe"], severe=f'{r["severe_maladministration"]:,.0f}'))
            os_.append("</p>")
        os_.append(f'<p class="src">{esc(w["ombudsman"]["change"])}</p>')
    elif om["period"]:
        os_.append(f'<p>{fill(w["ombudsman"]["no_report"], name=name, period=om["period"])}</p>')
    card.append("<section>" + "".join(os_) + src.ref(*[r["_source"] for r in om["reports"]]) + "</section>")

    sf = p["safety"]
    if sf:
        ss = [f'<h3>{esc(w["safety"]["heading"])}</h3>']
        if sf["all_done"]:
            ss.append(f'<p>{fill(w["safety"]["all_done"], year=sf["year"])}</p>')
        else:
            items = []
            for c in sf["checks"]:
                if c["status"] == "undefined":
                    continue
                if c["value"] is None:
                    items.append(f'<li>{fill(w["safety"]["not_published"], label=c["label"].capitalize())}</li>')
                elif c["value"] < 100:
                    items.append(f'<li>{fill(w["safety"]["gap_item"], label=c["label"].capitalize(), value=pct(c["value"]))}</li>')
            ss.append(f'<p>{fill(w["safety"]["gaps"], year=sf["year"])}</p><ul class="list">{"".join(items)}</ul>')
        card.append("<section>" + "".join(ss) + src.ref(sf["source"]) + "</section>")
    card.append("</section>")
    out.append("".join(card))

    # Detail -----------------------------------------------------------------------------------------------------
    if peer:
        rows = []
        for x in b["pillars"]:
            rows.append(f'<tr><th colspan="3" scope="colgroup">{esc(x["label"])}</th></tr>')
            for m in x["measures"]:
                rows.append(f'<tr><td>{esc(m["label"])}</td><td class="n">{pct(m["value"]) if m["value"] is not None else esc(m["note"] or "–")}</td>'
                            f'<td>{esc(band_name(m["band"]))}</td></tr>')
        if b["other"]:
            rows.append('<tr><th colspan="3" scope="colgroup">Shown but not compared</th></tr>')
            for m in b["other"]:
                v = (pct(m["value"]) if m["unit"] == "%" else f'{m["value"]:,.1f}') if m["value"] is not None else m["status"]
                rows.append(f'<tr><td>{esc(m["label"])}</td><td class="n">{esc(v)}</td><td></td></tr>')
        out.append(f'<h2>The figures, {esc(b["period"])}</h2><table><thead><tr><th scope="col">Measure</th>'
                   f'<th scope="col" class="n">Figure</th><th scope="col">Among similar landlords</th></tr></thead>'
                   f'<tbody>{"".join(rows)}</tbody></table>{src.ref(b.get("source", ""))}')

    if om["earlier"]:
        rows = "".join(f'<tr><td>{esc(r["period"])}</td><td>{esc(r["name"])}</td><td class="n">{r.get("findings_in_jurisdiction", 0):,.0f}</td>'
                       f'<td class="n">{100 * r.get("maladministration_rate", 0):.0f}%</td></tr>' for r in om["earlier"])
        out.append(f'<h2>Earlier Ombudsman figures</h2><p>{esc(w["ombudsman"]["change"])}</p><table><thead><tr>'
                   f'<th scope="col">Year</th><th scope="col">Name in the report</th><th scope="col" class="n">Findings</th>'
                   f'<th scope="col" class="n">At fault</th></tr></thead><tbody>{rows}</tbody></table>'
                   f'{src.ref(*[r["_source"] for r in om["earlier"]])}')

    if p["type"] == "council":
        out.append(f'<h2>{esc(w["areas"]["heading"])}</h2><p>{fill(w["areas"]["council"], name=name)}</p>')
        if p.get("council_link"):
            out.append(f'<p><a href="{esc(p["council_link"])}">{fill(w["council_link"]["text"], name=name)}</a></p>')
    elif p["areas"]:
        top = p["areas"][:12]
        items = "".join(f'<li>{esc(a["area_name"])}: {a["rented_homes"]:,.0f}</li>' for a in top)
        more = f'<p>{fill(w["areas"]["more"], count=len(p["areas"]) - len(top))}</p>' if len(p["areas"]) > len(top) else ""
        out.append(f'<h2>{esc(w["areas"]["heading"])}</h2><p>{esc(w["areas"]["intro"])}</p><ul class="list">{items}</ul>'
                   f'{more}{src.ref(*{s for a in p["areas"] for s in a["source_files"].split(",")})}')
    out.append(f'<p><a href="../../compare/index.html?l={esc(p["slug"])}">{esc(w["card"]["compare"])}</a></p>')
    if p["formerly"]:
        out.append(f'<p class="src">Earlier names: {esc(", ".join(p["formerly"]))}.</p>')
    out.append(src.html(w))
    return page(f"{name} – {w['site']['name']}", "".join(out), w, depth=2,
                description=f"{name}: grade, tenant satisfaction compared with similar landlords, Ombudsman complaints and safety checks.")


def method_html(settings: Settings, w: dict) -> str:
    from landlords.load.common import read_table

    r = rules()
    pg = read_table(settings, "peer_groups")
    latest = max(p["period"] for p in pg)
    groups = Counter(p["peer_group_label"] for p in pg if p["period"] == latest)
    sc = r["scoring"]
    pillars = "".join(f'<li><strong>{esc(p["label"])}</strong>: '
                      + esc("; ".join(r["measures"][m]["label"] for m in p["measures"])) + "</li>"
                      for p in r["pillars"].values())
    shown = [m for m, s in r["measures"].items() if m not in {x for p in r["pillars"].values() for x in p["measures"]}
             and m != r["headline"]["measure"]]
    groups_html = "".join(f"<li>{esc(k)}: {v}</li>" for k, v in sorted(groups.items()))
    body = f"""<h1>How we compare landlords</h1>
<p>This page explains every step. The rules are in one file, <code>config/scoring.toml</code>, and this page is made
from it. The method is being checked by a housing data reviewer before the site goes live.</p>
<h2>1. Similar landlords</h2>
<p>We compare each landlord only with landlords of the same type (councils, or housing associations) and a similar
size: {esc(", ".join(f"{e:,}" for e in r["peer_groups"]["size_bands"]))} homes are where the sizes change. Size is the number
of tenants in the landlord's own tenant survey that year. A group with fewer than {r["peer_groups"]["min_group"]}
landlords is joined to the next size down. For-profit landlords are too few to compare on their own, so they are
compared with housing associations of the same size.</p>
<p>The groups for {esc(latest)}:</p><ul class="list">{groups_html}</ul>
<h2>2. Each measure</h2>
<p>For each measure, we see how many similar landlords a landlord did better than (counting a tie as half). That
gives a number from 0 to 100, where 100 is best, whether a high or a low figure is good. We only do this if at least
{sc["min_peers"]} similar landlords have a figure. We use results for rented homes. We never change a published
figure.</p>
<h2>3. Three areas, and overall satisfaction</h2>
<ul class="list">{pillars}</ul>
<p>An area's score is the middle (median) of its measures' numbers. A landlord needs figures for at least half of
the measures in an area. Overall satisfaction ({esc(r["measures"][r["headline"]["measure"]]["label"].lower())}) is
shown on its own.</p>
<h2>4. Four bands</h2>
<p>We only show where a landlord comes among similar landlords, in four bands: {esc(", ".join(reversed(sc["bands"])))}.
Each band holds about a quarter of the group. We never add the bands up into one ranking, and the regulator's grade
and the Ombudsman's figures are shown beside them, never mixed in.</p>
<h2>5. Changes since last year</h2>
<p>An arrow shows when a landlord has moved to a different band since the year before.</p>
<h2>6. How tenants were asked</h2>
<p>Tenants answer differently on the phone, online and by post. Where a landlord asked mostly in a different way from
most similar landlords, we say so.</p>
<h2>What we show but do not compare</h2>
<p>{esc("; ".join(r["measures"][m]["label"] for m in shown))}. Complaints and anti-social behaviour cases are counts:
a high number can mean tenants find it easy to complain or report. Safety checks are shown as "all done" or the
share of homes that had each check.</p>
<h2>Where the figures come from</h2>
<p>The Regulator of Social Housing's Tenant Satisfaction Measures, regulatory judgements and statistical returns,
and the Housing Ombudsman's tables of landlords with performance reports. Every figure on a landlord's page links to
its file.</p>"""
    return page(f"How we compare landlords – {w['site']['name']}", body, w, depth=1, here="method/index.html")


def build(settings: Settings, out: Path | None = None) -> dict[str, int]:
    global _LAUNCHED, _SITE, _ASSETS
    _LAUNCHED = bool(settings.section("site").get("launched"))
    _SITE = settings.section("site")
    from landlords.site_pages import STATIC

    css = CSS_FILE.read_bytes()
    _ASSETS = {"styles.css": fingerprint("styles.css", css)}
    for name in ("search.js", "compare.js", "icon.svg"):
        _ASSETS[name] = fingerprint(name, (STATIC / name).read_bytes())
    w = load_toml("wording.toml")
    out = out or settings.data_dir / "site"
    if out.exists():
        shutil.rmtree(out)
    (out / "landlords").mkdir(parents=True)
    (out / "method").mkdir()
    (out / asset("styles.css")).write_bytes(css)
    (out / "styles.css").write_bytes(css)   # under its plain name too, for the API's own pages (src/landlords/api.py)
    profiles = build_profiles(settings)
    sizes = []
    for p in profiles:
        d = out / "landlords" / p["slug"]
        d.mkdir()
        text = profile_html(p, w)
        (d / "index.html").write_text(text)
        sizes.append(len(text.encode()))
    (out / "method" / "index.html").write_text(method_html(settings, w))
    from landlords.site_pages import build_extra

    extra = build_extra(settings, profiles, out, w)
    if max(sizes) > 100 * 1024:
        raise RuntimeError(f"a profile page is over 100 KB ({max(sizes) // 1024} KB)")
    return {"profiles": len(profiles), "largest_kb": round(max(sizes) / 1024, 1), **extra, "folder": str(out)}
