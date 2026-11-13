"""What the site keeps about a visitor: nothing. And what the charity's nightly check is told: counts and ages only.

The privacy page says the site sets no cookies, keeps no logs of visits, and keeps of a search that found nothing
only the words and the day. The limit on posts counts a visitor by a short hash of their address, held in memory for
about a minute. Moving onto the shared package (wts-core) must change none of that: the site passes it no visitor
code, so the package has nothing of a visitor's to keep."""

from __future__ import annotations

import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient
from wts_core.testing import assert_no_reader_data

from landlords import api
from landlords.state import open_state

ADDRESS = "203.0.113.77"
ADDRESS_6 = "2001:db8:77::77"
SEARCH = "zebrafinch canary nowhere"          # as the site keeps it: already in its normal form
FORM = {"name": "Jane Example", "role": "Chief executive, Example Housing", "page": "landlords/example-housing/",
        "part": "", "text": "Our survey was carried out after a big change.", "link": "https://example.org/results",
        "email": "jane@example-housing.org.uk"}


@pytest.fixture
def site(settings):
    root = settings.data_dir / "site"
    (root / "landlords" / "example-housing").mkdir(parents=True)
    (root / "landlords" / "example-housing" / "index.html").write_text("<h1>Example Housing</h1>")
    (root / "index.html").write_text("<h1>home</h1>")
    return root


def test_nothing_about_a_visitor_is_kept_anywhere(settings, site, caplog):
    caplog.set_level(logging.DEBUG)
    from landlords.register import normalise

    assert normalise(SEARCH) == SEARCH
    client = TestClient(api.create_app(settings, behind_proxy=True))
    for address in (ADDRESS, ADDRESS_6):
        sent_from = {"x-forwarded-for": f"{address}, 10.0.0.1"}
        assert client.post("/api/missed", json={"q": SEARCH}, headers=sent_from).status_code == 200
        assert client.post("/api/corrections", json={"kind": "wrong", "message": "Wrong grade", "email": "a@b.org"},
                           headers=sent_from).status_code == 200
        assert client.post("/api/statements", json=FORM, headers=sent_from).status_code == 200
        assert client.get("/", headers=sent_from).status_code == 200
        for _ in range(12):                                         # and past the limit, which counts them
            client.post("/api/missed", json={"q": "nobody homes"}, headers=sent_from)
    db = open_state(settings)
    lines = [record.getMessage() for record in caplog.records]
    for address in (ADDRESS, ADDRESS_6):
        # the shared package's own check of its tables and of what was logged
        assert_no_reader_data(db, lines, question=SEARCH, address=address, visitor=api.counted_by(address))
    # and the site's own, of everything it wrote: every table, and every file in its data folder
    con = sqlite3.connect(settings.state_db)
    held = {(table, repr(row)) for (table,) in con.execute("select name from sqlite_master where type = 'table'")
            for row in con.execute(f"select * from {table}")}  # noqa: S608 (the database's own table names)
    con.close()
    assert {table for table, row in held if SEARCH in row} == {"missed"}        # the words searched, and the day
    assert [c[1] for c in sqlite3.connect(settings.state_db).execute("pragma table_info(missed)")] == [
        "day", "query", "count"]
    for needle in (ADDRESS, ADDRESS_6, api.counted_by(ADDRESS), api.counted_by(ADDRESS_6), "10.0.0.1"):
        assert not [table for table, row in held if needle in row], needle
        for path in settings.data_dir.rglob("*"):
            if path.is_file():
                assert needle.encode() not in path.read_bytes(), (needle, path)
    # no visitor is counted towards a daily limit either: the package is passed no code, so its table stays empty
    assert sqlite3.connect(settings.state_db).execute("select count(*) from wts_reply_counts").fetchone() == (0,)
    assert "set-cookie" not in client.get("/").headers


def test_with_no_check_token_the_address_is_not_there(settings, site, monkeypatch):
    monkeypatch.delenv("LANDLORDS_CHECK_TOKEN", raising=False)
    client = TestClient(api.create_app(settings))
    missing, check = client.get("/api/no-such-address"), client.get("/api/check")
    assert (check.status_code, check.text) == (missing.status_code, missing.text) and check.status_code == 404
    assert client.get("/api/check", headers={"authorization": "Bearer anything"}).status_code == 404


def test_the_nightly_check_is_told_counts_and_ages_and_nothing_else(settings, site, monkeypatch, tmp_path):
    from wts_core import ops
    from wts_core.testing import FixedClock

    from landlords.state import BACKUPS

    clock = FixedClock("2026-11-13T12:00:00+00:00")
    monkeypatch.setenv("LANDLORDS_CHECK_TOKEN", "the-family-token")
    monkeypatch.setattr(api, "BACKUPS_DIR", tmp_path / "backups")
    client = TestClient(api.create_app(settings, clock=clock))
    assert client.post("/api/statements", json={**FORM, "text": f"A statement about {SEARCH} here."}).status_code == 200
    assert client.post("/api/corrections", json={"kind": "takedown", "message": f"Remove {SEARCH}",
                                                 "email": "reader@example.org"}).status_code == 200
    archive = ops.make_backup(settings.state_db, tmp_path / "backups", BACKUPS, clock=clock)
    assert archive.name == "landlords-state-20261113-120000.sqlite.gz"
    clock.advance(days=3)                                           # Monday 16 November: one working day on

    assert client.get("/api/check").status_code == 401
    wrong = client.get("/api/check", headers={"authorization": "Bearer not-the-token"})
    assert (wrong.status_code, wrong.json()) == (401, {})
    r = client.get("/api/check", headers={"authorization": "Bearer the-family-token"})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["site"] == "landlords" and body["versions"]["package"] == "0.1.0"
    assert body["waiting"] == {"reports": 1, "statements": 1, "hidden": 0, "oldest_working_days": 1}
    assert set(body["backups"]) == {"newest_hours", "offsite_hours", "offsite_ok"}
    assert body["backups"]["offsite_ok"] is None and body["backups"]["newest_hours"] is not None
    # never a word of a report or a statement, a name or an address
    for needle in (SEARCH, "Jane", "example", "reader@", "takedown"):
        assert needle not in r.text, needle
    # and it is limited like any other address: ten a minute from one visitor
    answers = [client.get("/api/check", headers={"authorization": "Bearer the-family-token"}).status_code
               for _ in range(10)]
    assert answers[-1] == 429 and set(answers) == {200, 429}
