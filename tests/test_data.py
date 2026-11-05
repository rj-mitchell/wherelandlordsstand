"""Checks on the real data. Skipped unless the files have been fetched and loaded (`landlords fetch`, `load`)."""

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
def test_pages_are_small_self_contained_and_carry_the_warning():
    import re

    from landlords.config import load_toml

    refusal = load_toml("wording.toml")["card"]["refusal"].replace("'", "&#x27;")
    pages = list((SITE / "landlords").glob("*/index.html"))
    assert len(pages) >= 360
    for path in pages:
        text = path.read_text()
        assert len(text.encode()) < 100 * 1024, path
        assert refusal in text, path
        assert "<script" not in text, path                       # readable without JavaScript, nothing third-party
        assert not re.search(r'<link[^>]+href="https?:', text), path
        assert 'id="sources"' in text, path                      # every page lists its sources
        for ref in re.findall(r'href="#source-(\d+)"', text):    # every figure's link goes to a listed file
            assert f'id="source-{ref}"' in text, (path, ref)


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
    assert 'name="robots" content="noindex"' in page and 'class="test"' in page
    assert "Disallow: /\n" in (test / "robots.txt").read_text() and not (test / "sitemap.xml").exists()

    with pytest.raises(RuntimeError, match="url"):
        build(launched=True, url="")

    live = build(launched=True, url="https://example.org")
    page = (live / "landlords" / "abri-group" / "index.html").read_text()
    assert "noindex" not in page and 'class="test"' not in page
    assert "Sitemap: https://example.org/sitemap.xml" in (live / "robots.txt").read_text()
    assert "<loc>https://example.org/landlords/abri-group/</loc>" in (live / "sitemap.xml").read_text()
    site.build(settings, settings.data_dir / "site")  # put the test-version pages back


@pytest.mark.skipif(not (settings.raw_dir / "tsm").exists(), reason="data not fetched")
def test_the_weekly_update_publishes_before_launch_and_asks_after(tmp_path, monkeypatch):
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

    launched = dataclasses.replace(s, raw={**s.raw, "site": {**s.section("site"), "launched": True,
                                                             "url": "https://example.org"}})
    asked = publish.update(launched, fetch=False, notify=False)
    assert asked["build"] and asked["approval"] and publish.current(s) == first["build"]   # waits for approval
    [(build,)] = State(data / "state.db").connect().execute("select build from approvals").fetchall()
    assert build == asked["build"]                # going public (deploy/.env) is enough for new pages

    monkeypatch.setattr(publish, "code_version", lambda: "a-new-version")
    assert publish.update(launched, fetch=False, notify=False)["build"]          # and so is a new version
