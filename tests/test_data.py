"""Checks on the real data. Skipped unless the files have been fetched and loaded (`landlords fetch`, `load`)."""

import re

import pytest

from landlords import checks
from landlords.config import load_settings

settings = load_settings()
pytestmark = pytest.mark.skipif(not (settings.staging_dir / "tsm.parquet").exists(),
                                reason="data not fetched and loaded")


@pytest.fixture(scope="module")
def report():
    return {c["name"]: c for c in checks.run(settings)["checks"]}


def test_reconciles_to_published_figures(report):
    for name, c in report.items():
        if "2024/25" in name or "2025-26" in name or "2025/26" in name:
            assert c["ok"], f"{name}: {c['detail']}"


def test_register_is_sound(report):
    for name in ("aliases point to known landlords and kinds", "no alias points to two landlords",
                 "slugs are unique", "no published slug has disappeared",
                 "every profiled landlord has a name, slug and type"):
        assert report[name]["ok"], report[name]["detail"]


def test_every_row_with_a_code_has_a_landlord(report):
    for table in ("tsm", "tsm_coverage", "grades", "stock_area", "providers"):
        c = report[f"every {table} row has a landlord"]
        assert c["ok"], c["detail"]


SITE = settings.data_dir / "site"


@pytest.mark.skipif(not (SITE / "index.html").exists(), reason="pages not built (`landlords build`)")
def test_landlords_that_stopped_reporting_say_who_reports_now():
    """data_static/reporting.csv: each row names a profiled landlord with no results of its own in the latest year,
    and the landlord now reporting for it (except "small") has a page, which the sentence links to."""
    import csv

    import duckdb

    from landlords.config import STATIC_DIR

    with open(STATIC_DIR / "reporting.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    with open(STATIC_DIR / "landlords.csv", encoding="utf-8") as fh:
        reg = {r["id"]: r for r in csv.DictReader(fh)}
    latest = duckdb.sql(f"select max(period) from '{settings.staging_dir / 'tsm_coverage.parquet'}'").fetchall()[0][0]
    reported = {r[0] for r in duckdb.sql(f"select landlord_id from '{settings.staging_dir / 'tsm_coverage.parquet'}' "
                                        f"where period = '{latest}'").fetchall()}
    assert rows
    for r in rows:
        assert reg[r["landlord_id"]]["profiled"] == "yes", r
        assert r["landlord_id"] not in reported, f"{r['landlord_id']} has results of its own for {latest}"
        assert r["reason"] in ("group", "other", "small"), r
        assert r["evidence"], r
        if r["reason"] != "small":
            assert reg[r["reported_by"]]["slug"] and r["reported_by"] in reported, r


@pytest.mark.skipif(not (SITE / "index.html").exists(), reason="pages not built (`landlords build`)")
def test_search_never_calls_a_large_landlord_or_a_covered_groups_company_small():
    """18 November 2026: search said 48 companies the regulator lists as Large (Clarion Housing Association, Aster
    Communities, Jigsaw Homes North …) had fewer than 1,000 homes, and ALMOs' names found nothing or only that."""
    import json

    from landlords.load.common import read_table
    from landlords.register import landlords, normalise

    names = json.loads((SITE / "names.json").read_text())
    by_name = {e["n"]: e for e in names if e.get("g") or not e.get("s")}     # the landlords without a page
    size = {g["landlord_id"]: g["size"] for g in read_table(settings, "groups")}
    owner = {o["landlord_id"]: o["profile_id"] for o in read_table(settings, "owners")}
    reg = {lid: r for lid, r in landlords().items() if r["status"] == "active" and r["profiled"] != "yes"}
    for lid, r in reg.items():
        e = by_name[r["legal_name"]]
        if owner.get(lid):
            assert "z" not in e and e["r"] == "part" and e["s"], (lid, e)
        if size.get(lid) == "Large":
            assert "z" not in e, (lid, e)
    assert by_name["Clarion Housing Association Limited"]["s"] == "clarion-housing-group"
    almos = {"St Leger Homes": "city-of-doncaster-council", "Berneslai Homes": "barnsley-metropolitan-borough-council",
             "Derby Homes": "derby-city-council", "Stockport Homes": "stockport-metropolitan-borough-council",
             "Nottingham City Homes": "nottingham-city-council", "Solihull Community Housing":
             "solihull-metropolitan-borough-council", "Wolverhampton Homes": "city-of-wolverhampton-council"}
    for alias, slug in almos.items():
        assert any(e.get("s") == slug and not e.get("g") and normalise(alias) in e["k"] for e in names), alias


def test_pages_are_small_self_contained_and_carry_the_warning():
    from landlords.config import load_toml

    refusal = load_toml("wording.toml")["card"]["refusal"].replace("'", "&#x27;")
    pages = list((SITE / "landlords").glob("*/index.html"))
    assert len(pages) >= 360
    for path in pages:
        text = path.read_text()
        assert len(text.encode()) < 100 * 1024, path
        assert refusal in text, path
        # readable without JavaScript, nothing third-party: the one script element is structured data for search
        # engines, which browsers never run
        assert "<script" not in re.sub(r'<script type="application/ld\+json">.*?</script>', "", text), path
        # nothing loaded from another site (a canonical link names this page's own address; it loads nothing)
        assert not re.search(r'<link(?![^>]*rel="canonical")[^>]+href="https?:', text), path
        assert not re.search(r'src="https?:', text), path
        assert 'id="sources"' in text, path                      # every page lists its sources
        for ref in re.findall(r'href="#source-(\d+)"', text):    # every figure's link goes to a listed file
            assert f'id="source-{ref}"' in text, (path, ref)


@pytest.mark.skipif(not (SITE / "index.html").exists(), reason="pages not built (`landlords build`)")
def test_every_page_carries_the_family_binding():
    """The Where They Stand family's binding (docs/DESIGN.md): the endorsement under the name, the footer shelf with
    the charity's line and every sister site, the kit's icons and link card, headings in Source Serif 4, and the
    footer's links in the family's order."""
    from landlords.config import load_toml

    w = load_toml("wording.toml")
    pages = sorted(SITE.rglob("*.html"))
    assert len(pages) > 600
    for path in pages:
        text = path.read_text()
        assert '<body class="wts-headings">' in text, path
        assert '<a class="wts-endorse" href="https://wheretheystand.uk/">' in text, path
        assert '<nav class="wts-shelf"' in text and "applying to register as a charity in England and Wales" in text
        for site in ("wherempsstand.com", "wherecouncilsstand.com", "wherecountriesstand.com", "wherelivesstand.com"):
            assert f'href="https://{site}/"' in text, (path, site)
        assert 'rel="apple-touch-icon"' in text and 'property="og:image"' in text, path
        assert 'name="theme-color" content="#40484D"' in text, path
        assert "/family/" not in text, path                         # every kit file at its address under assets/
        assert w["site"]["independence"].replace("'", "&#x27;") in text, path
        labels = [label.replace("'", "&#x27;") for label, _ in w["footer"]["links"]]
        found = [text.find(f">{label}</a></li>") for label in labels]
        assert all(i > 0 for i in found) and found == sorted(found), (path, found)
    assert (SITE / "favicon.ico").is_file()
    profile = (SITE / "landlords" / "abri-group" / "index.html").read_text()
    assert '<link rel="canonical" href="https://wherelandlordsstand.com/landlords/abri-group/">' in profile


@pytest.mark.skipif(not (SITE / "index.html").exists(), reason="pages not built (`landlords build`)")
def test_area_pages_link_to_the_council_on_where_councils_stand_where_it_is_covered():
    from landlords.sisters import councils_covered

    covered = councils_covered()
    linked = 0
    for path in (SITE / "areas").glob("*/index.html"):
        text = path.read_text()
        links = set(re.findall(r'href="https://wherecouncilsstand\.com/councils/(E\d{8})"', text))
        assert links <= set(covered), path
        linked += bool(links)
    assert linked > 200


@pytest.mark.skipif(not (settings.staging_dir / "scores.parquet").exists(), reason="data not scored")
def test_the_launch_switch(tmp_path):
    import dataclasses
    import json

    from landlords import site
    from landlords.site_pages import CC_BY, OGL

    def build(**site_cfg):
        raw = {**settings.raw, "site": {**settings.section("site"), **site_cfg}}
        s = dataclasses.replace(settings, raw=raw)
        out = tmp_path / str(len(list(tmp_path.iterdir())))
        site.build(s, out)
        return out

    test = build(launched=False)
    page = (test / "landlords" / "abri-group" / "index.html").read_text()
    assert 'name="robots" content="noindex"' in page
    assert "Disallow: /\n" in (test / "robots.txt").read_text() and not (test / "sitemap.xml").exists()

    with pytest.raises(RuntimeError, match="url"):
        build(launched=True, url="")

    live = build(launched=True, url="https://example.org")
    page = (live / "landlords" / "abri-group" / "index.html").read_text()
    assert "noindex" not in page
    assert "Sitemap: https://example.org/sitemap.xml" in (live / "robots.txt").read_text()
    assert "<loc>https://example.org/landlords/abri-group/</loc>" in (live / "sitemap.xml").read_text()
    sitemap = (live / "sitemap.xml").read_text()
    assert "<loc>https://example.org/named/</loc>" in sitemap   # "If you're named"
    # the day each page last changed; none for the pages that change with every build
    assert re.search(r"<loc>https://example.org/landlords/abri-group/</loc><lastmod>\d{4}-\d\d-\d\d</lastmod>", sitemap)
    assert "<url><loc>https://example.org/status/</loc></url>" in sitemap and "thanks.html" not in sitemap
    for thanks in ("corrections/thanks.html", "named/thanks.html"):
        assert '<meta name="robots" content="noindex">' in (live / thanks).read_text(), thanks
    # structured data for search engines, at the site's own address
    assert '"@type":"WebSite"' in (live / "index.html").read_text()
    assert '"item":"https://example.org/landlords/abri-group/"' in page
    assert '"item":"https://example.org/areas/leeds/"' in (live / "areas" / "leeds" / "index.html").read_text()
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',
                                (live / "data" / "index.html").read_text())[1])
    assert data["license"] == "https://example.org/terms/"  # the terms page, which gives each part's licence
    licences = {d["name"]: d.get("license") for d in data["distribution"]}
    assert licences == {"landlords.csv": OGL, "bands.csv": CC_BY, "tenant-satisfaction-measures.csv": OGL,
                        "ombudsman.csv": None, "regulatory-judgements.csv": OGL, "homes-by-area.csv": CC_BY}
    site.build(settings, settings.data_dir / "site")  # put the test-version pages back


@pytest.mark.skipif(not (SITE / "index.html").exists(), reason="pages not built (`landlords build`)")
def test_with_measurement_off_no_page_names_measure_js_or_google():
    """The measurement switch ships off (docs/DECISIONS.md, 20): the built pages carry nothing of it but the kit's inert
    data-wts-conversion attributes, and no measure.js is among the built files."""
    assert settings.section("ads").get("measurement") is False
    for path in sorted(SITE.rglob("*.html")):
        text = path.read_text()
        assert not re.search(r"measure\.[0-9a-f]{10}\.js|googletagmanager|data-wts-measure-open", text), path
    assert not list((SITE / "assets").glob("measure.*.js"))
    assert 'data-wts-conversion="download"' in (SITE / "data" / "index.html").read_text()
    assert 'data-wts-conversion="source_opened"' in (SITE / "landlords" / "abri-group" / "index.html").read_text()


@pytest.mark.skipif(not (settings.staging_dir / "scores.parquet").exists(), reason="data not scored")
def test_the_measurement_switch_on_every_real_page(tmp_path, monkeypatch):
    import dataclasses
    import json

    from landlords import site
    from landlords.config import load_toml

    def wording(name):
        w = load_toml(name)
        if name == "wording.toml":   # the notice as the owner finishes it before turning measurement on
            text = json.dumps(w["privacy_measurement"]).replace("NNNNNNN", "1234567")
            w["privacy_measurement"] = {**json.loads(text), "updated": "Last updated 1 March 2027."}
        return w

    monkeypatch.setattr(site, "load_toml", wording)
    raw = {**settings.raw, "ads": {"measurement": True, "tag": "AW-123456789"}}
    out = tmp_path / "on"
    try:
        site.build(dataclasses.replace(settings, raw=raw), out)
        pages = sorted(out.rglob("*.html"))
        assert len(pages) > 600
        # relative to the page, or from the root on the 404 page, which is served at any address
        script = re.compile(r'<script src="(/|(?:\.\./)*)assets/measure\.[0-9a-f]{10}\.js" data-tag="AW-123456789" '
                            r'data-privacy="\1privacy/" data-measures="[a-z_ ]+" defer></script>')
        for path in pages:
            text = path.read_text()
            assert script.search(text.split("</head>")[0]), path
            assert "data-wts-measure-open>Measurement choices</a>" in text, path
        assert 'id="measurement"' in (out / "privacy" / "index.html").read_text()
        assert len(list((out / "assets").glob("measure.*.js"))) == 1
    finally:
        monkeypatch.undo()
        site.build(settings, settings.data_dir / "site")  # put the test-version pages back


@pytest.mark.skipif(not (settings.raw_dir / "tsm").exists(), reason="data not fetched")
def test_the_weekly_update_publishes_the_first_pages_and_asks_for_the_rest(tmp_path, monkeypatch):
    """The site is public, in alpha (docs/DECISIONS.md, 12): once pages are live, new ones wait for the owner's
    approval, whether or not the launch switch is on."""
    import dataclasses
    import shutil

    from landlords import publish
    from landlords.state import open_state

    data = tmp_path / "data"
    shutil.copytree(settings.raw_dir, data / "raw")
    shutil.copytree(settings.staging_dir, data / "staging", ignore=shutil.ignore_patterns("*.part"))
    s = dataclasses.replace(settings, data_dir=data)

    first = publish.update(s, fetch=False, notify=False)
    assert first["build"] and "first pages" in first["published"] and publish.current(s) == first["build"]

    again = publish.update(s, fetch=False, notify=False)
    assert again["build"] is None                                   # nothing new: no new pages

    assert not s.section("site").get("launched")
    monkeypatch.setattr(publish, "code_version", lambda: "a-new-version")
    asked = publish.update(s, fetch=False, notify=False)            # a new version of the site, before launch
    assert asked["build"] and asked["approval"] and publish.current(s) == first["build"]   # waits for approval
    with open_state(s).connect() as db:
        [(build,)] = [tuple(row) for row in db.execute("select build from approvals")]
    assert build == asked["build"]

    launched = dataclasses.replace(s, raw={**s.raw, "site": {**s.section("site"), "launched": True,
                                                             "url": "https://example.org"}})
    after = publish.update(launched, fetch=False, notify=True)      # launching is enough for new pages, which wait too
    assert after["build"] and publish.current(s) == first["build"]
    assert after["email"].startswith("queued") and after["needs_attention"] == bool(after["checks_failed"])
    [letter] = (data / "outbox").glob("*.txt")                      # for the server's mail.sh (deploy/send-mail.sh)
    assert letter.read_text().startswith("To: wheretheystanduk@gmail.com\nSubject: Where Landlords Stand: new pages")
    assert "https://example.org/admin/approve/" in letter.read_text()

    from landlords import notify

    monkeypatch.setattr(notify, "send", lambda *a, **k: "not sent: the outbox is full")
    monkeypatch.setattr(publish, "code_version", lambda: "another-version")
    unsent = publish.update(launched, fetch=False, notify=True)
    assert unsent["needs_attention"] and "not sent" in unsent["approval"]   # nobody would hear: the update fails


@pytest.mark.skipif(not (settings.staging_dir / "scores.parquet").exists(), reason="data not scored")
def test_a_hidden_landlord_is_hidden_in_the_real_pages_and_put_back_exactly(tmp_path):
    """Hiding a landlord while a concern about it is decided (src/landlords/hiding.py; docs/DECISIONS.md, 17), on
    the real pages: build, hide, build again while it is hidden, show it again, build. Its page shows the note; it is
    in no list, table, search entry or download; a build made meanwhile hides it the same way; and showing it again
    puts every file back to the byte."""
    import dataclasses
    import json
    import shutil

    from landlords import hiding, site
    from landlords.replies import open_replies

    def tree(root) -> dict:
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
                if p.is_file() and p.name != "status.json"}             # status.json holds the time of the build

    data = tmp_path / "data"
    shutil.copytree(settings.staging_dir, data / "staging", ignore=shutil.ignore_patterns("*.part"))
    s = dataclasses.replace(settings, data_dir=data)
    out = data / "site"
    site.build(s, out)
    before = tree(out)
    replies = open_replies(s)
    note = "We are checking a figure on this page."
    replies.hide("https://wherelandlordsstand.com/landlords/abri-group/", note)
    assert hiding.refresh(s)["pages_changed"] > 40
    hidden = tree(out)
    own = hidden["landlords/abri-group/index.html"].decode()
    assert f"<h1>Abri Group</h1><p>This page is hidden while a concern about it is decided.</p><p>{note}</p></main>" in own
    assert "<!--statements:" not in own and "Before you bid" not in own and "%" not in own.split("<main")[1].split(
        "</main>")[0]                           # no figure of its own is left on it
    [abri] = [e for e in json.loads(before["names.json"]) if e.get("s") == "abri-group" and not e.get("g")]
    assert "abri-group" not in hidden["names.json"].decode() and "data/landlords/abri-group.json" not in hidden
    lid = next(line.split(",")[0] for line in before["data/landlords.csv"].decode().splitlines()
               if "landlords/abri-group/" in line)
    for name, text in hidden.items():
        if name.startswith(("areas/", "data/")) or name in ("index.html", "names.json", "sitemap.xml"):
            assert b"abri-group" not in text and b"Abri Group" not in text, name
        if name.endswith(".csv"):
            assert not [line for line in text.decode().splitlines() if line.split(",")[0] == lid], name
    # its own entry and those of the companies in its group, which link to its page
    gone = sum(e.get("s") == "abri-group" for e in json.loads(before["names.json"]))
    assert len(json.loads(before["names.json"])) - len(json.loads(hidden["names.json"])) == gone and abri["n"]
    assert b"362 social landlords" in hidden["index.html"] and b"363 social landlords" in before["index.html"]
    # what an edit cannot reach, and docs/OPERATIONS.md says so: another landlord's page that names it (a merger), and
    # the press page, which counts it and gives it as the example
    still = sorted(name for name, text in hidden.items() if name.endswith(".html") and b"Abri" in text)
    assert still == ["landlords/abri-group/index.html", "landlords/octavia-housing/index.html", "press/index.html"]
    assert hidden["landlords/octavia-housing/index.html"] == before["landlords/octavia-housing/index.html"]

    site.build(s, out)                          # new pages, built while it is hidden: hidden in them the same way
    assert tree(out) == hidden
    replies.unhide("landlords/abri-group/")
    hiding.refresh(s)
    assert tree(out) == before                  # put back, to the byte
    assert not (data / "hidden-originals").exists()
    site.build(s, out)
    assert tree(out) == before


@pytest.mark.skipif(not (settings.staging_dir / "scores.parquet").exists(), reason="data not scored")
def test_a_published_statement_is_built_into_its_pages_and_nowhere_else(tmp_path):
    """The right of reply (src/landlords/statements.py; docs/DECISIONS.md, 15): a statement published before a build
    is in the pages it builds, beside its item and on the landlord's own page, and never in the search, the compare
    page's data, the downloads or the status page's data."""
    import dataclasses
    import shutil

    from landlords import site
    from landlords.replies import beside, open_replies

    data = tmp_path / "data"
    shutil.copytree(settings.staging_dir, data / "staging", ignore=shutil.ignore_patterns("*.part"))
    s = dataclasses.replace(settings, data_dir=data)
    site.build(s, data / "site")                # a statement can only be sent about a page that is on the site
    replies = open_replies(s)
    phrase = "A phrase only this statement uses, about our tenant survey."
    for page, part in (("landlords/abri-group/", "bands"), ("areas/birmingham/", "")):
        sid = replies.submit(name="Jane Example", role="Chief executive", item=beside(page, part), text=phrase,
                             link="", email="j@example.org")
        replies.publish(sid, checked="test", about=None if part else "birmingham-city-council")
    out = tmp_path / "site"
    assert site.build(s, out)["statements"] == 3
    abri = (out / "landlords" / "abri-group" / "index.html").read_text()
    assert re.search(r'<h3 id="bands">.*?<div class="statement".*?' + re.escape(phrase), abri, re.S)
    assert phrase in (out / "areas" / "birmingham" / "index.html").read_text()
    assert phrase in (out / "landlords" / "birmingham-city-council" / "index.html").read_text()
    assert "<script" not in re.sub(r'<script type="application/ld\+json">.*?</script>', "", abri) and len(abri.encode()) < 100 * 1024
    # never in the page's title, description or link card, and in an element that asks search engines not to quote it
    assert phrase not in abri.split("</head>")[0] and abri.count("data-nosnippet") == abri.count('class="statement"')
    for path in out.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".csv", ".xml", ".txt"):
            assert "only this statement uses" not in path.read_text(errors="ignore"), path
    site.build(settings, settings.data_dir / "site")  # put the test-version pages back


@pytest.mark.skipif(not (SITE / "index.html").exists(), reason="pages not built (`landlords build`)")
def test_links_name_a_pages_folder_never_its_index_html():
    """One address for each page: Google chose "…/index.html" over "…/" for several pages while the links named
    index.html (19 November 2026)."""
    for path in SITE.rglob("*.html"):
        text = path.read_text()
        assert not re.search(r'href="(?!https?:|mailto:)[^"]*index\.html', text), path
    for js in (SITE / "assets").glob("*.js"):
        assert "index.html" not in js.read_text(), js
