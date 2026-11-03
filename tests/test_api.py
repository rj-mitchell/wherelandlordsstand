import json
import shutil
import sqlite3
import subprocess

import pytest
from fastapi.testclient import TestClient

from landlords import publish
from landlords.api import create_app
from landlords.register import normalise


@pytest.fixture
def client(settings):
    site = settings.data_dir / "site"
    (site / "corrections").mkdir(parents=True)
    (site / "index.html").write_text("<h1>home</h1>")
    (site / "corrections" / "thanks.html").write_text("thanks")
    return TestClient(create_app(settings))


def test_pages_are_served_with_a_strict_policy_and_no_cookies(client):
    r = client.get("/")
    assert r.status_code == 200 and "home" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert "set-cookie" not in r.headers


def test_a_report_from_the_form_is_kept_and_its_email_deleted_on_closing(client, settings):
    r = client.post("/api/corrections", content="page=landlords%2Fx%2F&message=Wrong+grade&email=a%40b.org",
                    headers={"content-type": "application/x-www-form-urlencoded"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/corrections/thanks.html"
    from landlords.api import State

    state = State(settings.data_dir / "state.db")
    [(rid, _, page, message, email)] = state.open_reports()
    assert (page, message, email) == ("landlords/x/", "Wrong grade", "a@b.org")
    assert state.close_report(rid, "fixed")
    assert sqlite3.connect(settings.data_dir / "state.db").execute("select email from reports").fetchone() == (None,)
    assert client.post("/api/corrections", json={"message": ""}).status_code == 400


def test_a_missed_search_keeps_only_the_words(client, settings):
    client.post("/api/missed", json={"q": "Nobody Homes Ltd"})
    client.post("/api/missed", json={"q": "nobody homes"})
    db = sqlite3.connect(settings.data_dir / "state.db")
    assert db.execute("select query, count from missed").fetchall() == [("nobody homes", 2)]
    assert [c[1] for c in db.execute("pragma table_info(missed)")] == ["day", "query", "count"]


def _fake_build(settings, name, failed=()):
    d = publish.builds_dir(settings) / name
    d.mkdir(parents=True)
    (d / "index.html").write_text(name)
    (d / "build-info.json").write_text(json.dumps({"build": name, "checks_failed": list(failed)}))


def test_publish_and_rollback_switch_the_live_site(settings):
    _fake_build(settings, "20261101-000000")
    _fake_build(settings, "20261102-000000")
    _fake_build(settings, "20261103-000000", failed=["something"])
    with pytest.raises(RuntimeError, match="failed checks"):
        publish.publish(settings)
    publish.publish(settings, "20261101-000000")
    publish.publish(settings, "20261102-000000")
    assert (settings.data_dir / "live" / "index.html").read_text() == "20261102-000000"
    assert publish.rollback(settings)["live"] == "20261101-000000"
    assert (settings.data_dir / "live" / "index.html").read_text() == "20261101-000000"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_browser_normalises_names_as_the_register_does():
    from pathlib import Path

    names = ["Town & Country Housing", "Abbeyfield Society  (The)", "Metropolitan Thames Valley Housing (MTV)",
             "Hyde Housing Association Limited", "Bournemouth, Christchurch and Poole Council", "L&H Homes",
             "Héritage Homes Ltd", "St. Mungo's", "whg"]
    js = Path(__file__).parents[1] / "src/landlords/static/search.js"
    script = (f"global.window={{}};global.document={{addEventListener(){{}}}};require({json.dumps(str(js))});"
              f"console.log(JSON.stringify({json.dumps(names)}.map(window.WLS.norm)))")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [normalise(n) for n in names]
