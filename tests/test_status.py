"""The status and press pages, without the real data: built with a build's own files, and the status page written
again in the live pages after each update, publish and undo."""

import json
import re

import pytest

from landlords import publish, site, status
from landlords.api import State
from landlords.config import load_toml


def _text(html: str) -> str:
    main = re.search(r"<main.*?</main>", html, re.S)[0]
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", main)).replace("&#x27;", "'")


def _live_build(settings, name: str, checks_failed=()):
    """A build with what the status page needs: its files (assets.json), status.json and build-info.json."""
    folder = publish.builds_dir(settings) / name
    folder.mkdir(parents=True)
    site.use_build(settings, site.write_assets(folder), False)
    status.write(settings, folder, load_toml("wording.toml"))
    (folder / "build-info.json").write_text(json.dumps({
        "build": name, "finished": f"{name[:4]}-{name[4:6]}-{name[6:8]}T12:00:00+00:00",
        "checks_failed": list(checks_failed), "site_settings": {"launched": False}}))


@pytest.fixture
def staged(settings):
    staging = settings.staging_dir
    staging.mkdir(parents=True)
    (staging / "sources.json").write_text(json.dumps({
        "a": {"source": "tsm", "period": "2024/25", "title": "TSM 2024/25 full data", "publisher": "Regulator of "
              "Social Housing", "fetched_at": "2026-11-01T09:00:00+00:00", "file": "a.xlsx"},
        "b": {"source": "tsm", "period": "2025/26", "title": "TSM 2025/26 full data", "publisher": "Regulator of "
              "Social Housing", "fetched_at": "2026-10-01T09:00:00+00:00", "file": "b.xlsx"},
        "c": {"source": "ombudsman", "period": "2025-26", "title": "Landlord tables ( xlsx, 0.4 MB)",
              "publisher": "Housing Ombudsman Service", "fetched_at": "2026-10-02T09:00:00+00:00", "file": "c.xlsx"}}))
    (staging / "loaded.json").write_text(json.dumps({"tsm": "2026-11-02T10:00:00+00:00"}))
    (staging / "fetch-report.json").write_text(json.dumps({
        "finished": "2026-11-05T11:41:00+00:00", "failed": [{"source": "stock", "error": "page moved"}]}))
    return settings


def test_the_status_page_says_how_up_to_date_the_pages_are(staged, tmp_path):
    out = tmp_path / "site"
    out.mkdir()
    site.use_build(staged, site.write_assets(out), False)
    status.write(staged, out, load_toml("wording.toml"))
    text = _text((out / "status" / "index.html").read_text())
    assert "The site last looked for new files on 5 November 2026." in text
    assert "could not look for new files from: Homes each landlord owns" in text
    assert "TSM 2025/26 full data (2025/26) 1 October 2026 2 November 2026" in text   # the latest year's file
    assert "Landlord tables (2025-26) 2 October 2026 not yet" in text               # without "( xlsx, 0.4 MB)"
    assert "waiting" not in text                     # pages built by hand know nothing of approvals
    html = (out / "status" / "index.html").read_text()
    assert "<script" not in html and 'href="../press/index.html">Press</a>' in html


def test_the_live_status_page_is_written_again_after_each_update_publish_and_undo(staged):
    _live_build(staged, "20261101-000000")
    _live_build(staged, "20261105-000000")
    publish.publish(staged, "20261101-000000")
    live = publish.builds_dir(staged) / "20261101-000000" / "status" / "index.html"
    assert "No new pages are waiting" in _text(live.read_text())
    assert "These pages were made on 1 November 2026." in _text(live.read_text())

    State(staged.data_dir / "state.db").add_approval("20261105-000000", 14)
    assert status.refresh(staged)
    assert "New pages, made on 5 November 2026, are waiting to be checked" in _text(live.read_text())

    publish.publish(staged, "20261105-000000")       # as the approval page's button does
    new = publish.builds_dir(staged) / "20261105-000000" / "status" / "index.html"
    assert "No new pages are waiting" in _text(new.read_text())
    publish.rollback(staged)
    assert "These pages were made on 1 November 2026." in _text(live.read_text())


def test_failed_or_missing_pages_are_not_waiting_and_old_builds_are_left_alone(staged):
    _live_build(staged, "20261101-000000")
    _live_build(staged, "20261105-000000", checks_failed=["a check"])
    publish.publish(staged, "20261101-000000")
    State(staged.data_dir / "state.db").add_approval("20261105-000000", 14)
    State(staged.data_dir / "state.db").add_approval("20261109-000000", 14)        # its pages cleared away
    assert status.waiting(staged, "20261101-000000") is None
    old = publish.builds_dir(staged) / "20261020-000000"                            # built before the status page
    old.mkdir()
    (old / "build-info.json").write_text("{}")
    publish.publish(staged, "20261020-000000")
    assert not status.refresh(staged)


def test_the_press_page_has_the_facts_a_citation_and_logo_files(settings, tmp_path):
    from landlords.site_pages import press

    out = tmp_path / "site"
    out.mkdir()
    site.use_build(settings, site.write_assets(out), False)
    profiles = [{"slug": "abri-group", "name": "Abri Group"}, {"slug": "x", "name": "X"}]
    press(settings, profiles, {"E1": {}}, out, load_toml("wording.toml"))
    html = (out / "press" / "index.html").read_text()
    text = _text(html)
    assert "a page for each of 2 councils" in text and "a page for each of 1 council areas" in text
    assert re.search(r"Abri Group\. Where Landlords Stand\. https://wherelandlordsstand\.com/landlords/abri-group/ "
                     r"\(seen on \d+ \w+ \d{4}\)\.", text)
    assert "admin@wherelandlordsstand.com" in text and "<script" not in html
    for name in re.findall(r'href="\.\./press/([^"/]+\.(?:svg|png))"', html):
        assert (out / "press" / name).stat().st_size > 100, name
    assert len(re.findall(r'href="\.\./press/[^"]+\.(?:svg|png)"', html)) == 4
    mark = (out / "press" / "where-landlords-stand-mark.svg").read_text()
    assert mark.startswith("<svg xmlns=") and "var(" not in mark                    # its own colours, no stylesheet
