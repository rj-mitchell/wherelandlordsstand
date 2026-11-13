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


def test_pages_are_small_self_contained_and_carry_the_warning():
    from landlords.config import load_toml

    refusal = load_toml("wording.toml")["card"]["refusal"].replace("'", "&#x27;")
    pages = list((SITE / "landlords").glob("*/index.html"))
    assert len(pages) >= 360
    for path in pages:
        text = path.read_text()
        assert len(text.encode()) < 100 * 1024, path
        assert refusal in text, path
        assert "<script" not in text, path                       # readable without JavaScript, nothing third-party
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

    from landlords import site

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
    assert "<loc>https://example.org/named/</loc>" in (live / "sitemap.xml").read_text()   # "If you're named"
    site.build(settings, settings.data_dir / "site")  # put the test-version pages back


@pytest.mark.skipif(not (settings.raw_dir / "tsm").exists(), reason="data not fetched")
def test_the_weekly_update_publishes_the_first_pages_and_asks_for_the_rest(tmp_path, monkeypatch):
    """The site is public, in alpha (docs/DECISIONS.md, 12): once pages are live, new ones wait for the owner's
    approval, whether or not the launch switch is on."""
    import dataclasses
    import shutil

    from landlords import publish
    from landlords.api import State

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
    with State(data / "state.db").connect() as db:
        [(build,)] = db.execute("select build from approvals").fetchall()
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
def test_a_published_statement_is_built_into_its_pages_and_nowhere_else(tmp_path):
    """The right of reply (src/landlords/statements.py; docs/DECISIONS.md, 15): a statement published before a build
    is in the pages it builds, beside its item and on the landlord's own page, and never in the search, the compare
    page's data, the downloads or the status page's data."""
    import dataclasses
    import shutil

    from landlords import site
    from landlords import statements as st
    from landlords.api import State

    data = tmp_path / "data"
    shutil.copytree(settings.staging_dir, data / "staging", ignore=shutil.ignore_patterns("*.part"))
    s = dataclasses.replace(settings, data_dir=data)
    state = State(data / "state.db")
    phrase = "A phrase only this statement uses, about our tenant survey."
    for page, part in (("landlords/abri-group/", "bands"), ("areas/birmingham/", "")):
        sid = state.add_statement("Jane Example", "Chief executive", page, part, phrase, "", "j@example.org",
                                  "abri-group" if part else None)
        st.publish(state, sid, "test", "abri-group" if part else "birmingham-city-council", lambda slug: True)
    out = tmp_path / "site"
    assert site.build(s, out)["statements"] == 3
    abri = (out / "landlords" / "abri-group" / "index.html").read_text()
    assert re.search(r'<h3 id="bands">.*?<div class="statement".*?' + re.escape(phrase), abri, re.S)
    assert phrase in (out / "areas" / "birmingham" / "index.html").read_text()
    assert phrase in (out / "landlords" / "birmingham-city-council" / "index.html").read_text()
    assert "<script" not in abri and len(abri.encode()) < 100 * 1024
    for path in out.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".csv", ".xml", ".txt"):
            assert "only this statement uses" not in path.read_text(errors="ignore"), path
    site.build(settings, settings.data_dir / "site")  # put the test-version pages back
