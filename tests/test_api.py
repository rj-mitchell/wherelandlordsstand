import json
import shutil
import sqlite3
import subprocess

import pytest
from fastapi.testclient import TestClient
from wts_core.usage import RateLimiter

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
    from landlords.replies import open_replies

    replies = open_replies(settings)
    [report] = replies.reports()
    assert (report["kind"], report["page"], report["message"], report["contact"]) == (
        None, "landlords/x/", "Wrong grade", "a@b.org")                                       # an older form: no kind
    replies.close(report["id"], outcome="resolved", note="fixed")
    assert sqlite3.connect(settings.data_dir / "state.db").execute(
        "select contact, status, resolution from wts_reports").fetchone() == (None, "resolved", "fixed")
    assert client.post("/api/corrections", json={"message": ""}).status_code == 400


def test_a_missed_search_keeps_only_the_words(client, settings):
    client.post("/api/missed", json={"q": "Nobody Homes Ltd"})
    client.post("/api/missed", json={"q": "nobody homes"})
    db = sqlite3.connect(settings.data_dir / "state.db")
    assert db.execute("select query, count from missed").fetchall() == [("nobody homes", 2)]
    assert [c[1] for c in db.execute("pragma table_info(missed)")] == ["day", "query", "count"]


@pytest.mark.parametrize("body", [b"{not json", b'["a", "list"]', b"\xff\xfe"])
def test_a_json_body_that_cannot_be_read_is_refused_and_nothing_kept(client, settings, body):
    from landlords.replies import open_replies
    from landlords.state import own

    json_body = {"content": body, "headers": {"content-type": "application/json"}}
    r = client.post("/api/corrections", **json_body)
    assert r.status_code == 400
    assert r.json() == {"ok": False, "error": "the report couldn't be read; please send it again"}
    r = client.post("/api/missed", **json_body)
    assert r.status_code == 400 and r.json() == {"ok": False}
    assert open_replies(settings).reports() == [] and own(settings).top_missed() == []
    assert client.post("/api/corrections", json={"message": "Wrong grade"}).json() == {"ok": True, "id": 1}


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


def test_fingerprinted_files_are_kept_and_everything_else_is_checked_each_time():
    """Cloudflare kept the old styles.css for two hours after the redesign was published (6 November 2026)."""
    from landlords.api import cache_control

    assert "immutable" in cache_control("/assets/styles.7bbe18f016.css")
    assert "immutable" in cache_control("/assets/search.ddce99e856.js")
    assert "immutable" in cache_control("/assets/fonts/source-serif-4-normal-latin.0a1b2c3d4e.woff2")
    for path in ("/styles.css", "/index.html", "/landlords/abri-group/", "/data/landlords.csv", "/names.json"):
        assert cache_control(path) == "no-cache", path


def test_every_file_a_page_uses_is_fingerprinted_under_assets(tmp_path):
    """A changed stylesheet, script, icon or font gets a new name under assets/, and the stylesheet names the fonts by
    their new names, so no page can meet an old file (6 November 2026)."""
    import re

    from landlords import site

    names = site.write_assets(tmp_path)
    assert set(names) >= {"styles.css", "fonts.css", "family.css", "search.js", "compare.js", "tabs.js", "icon.svg",
                          "favicon.ico", "apple-touch-icon.png", "card.png", "fonts/source-serif-4-normal-latin.woff2"}
    for built in names.values():
        assert built.startswith("assets/") and re.search(r"\.[0-9a-f]{10}\.\w+$", built), built
        assert (tmp_path / built).is_file(), built
    fonts = (tmp_path / names["fonts.css"]).read_text()
    assert len(re.findall(r"url\(([^)]+)\)", fonts)) == 4
    for css in ("styles.css", "fonts.css", "family.css"):
        for url in re.findall(r"url\(([^)]+)\)", (tmp_path / names[css]).read_text()):
            assert (tmp_path / "assets" / url).is_file(), url
    assert (tmp_path / "favicon.ico").is_file()                    # browsers ask for it at the root
    assert json.loads((tmp_path / "assets.json").read_text()) == names
    assert site.write_assets(tmp_path / "again") == names          # the same files give the same names
    assert 'width="52" height="52"' in site.MARK                    # stays small without the stylesheet


# The limit on posts: ten a minute from one visitor (the shared package's RateLimiter, counting by api.counted_by) ----


class Recording:
    """A limiter that also notes what it was asked to count by, for a test to look at."""

    def __init__(self, limiter):
        self.limiter, self.asked = limiter, []

    def allow(self, key: str) -> bool:
        self.asked.append(key)
        return self.limiter.allow(key)


def test_ten_posts_a_minute_from_one_visitor_and_no_more_until_a_minute_has_passed(client, settings, monkeypatch):
    from wts_core.testing import FixedClock

    from landlords import api

    made = []
    monkeypatch.setattr(api, "RateLimiter", lambda *a, **k: made.append(Recording(RateLimiter(*a, **k))) or made[-1])
    clock = FixedClock()
    app = api.create_app(settings, behind_proxy=True, clock=clock)

    def post(who: str) -> int:
        return TestClient(app).post("/api/missed", json={"q": "nobody homes"},
                                    headers={"x-forwarded-for": f"{who}, 10.0.0.1"}).status_code

    assert [post("203.0.113.7") for _ in range(11)] == [200] * 10 + [429]
    assert post("203.0.113.8") == 200                                # another visitor is counted on their own
    clock.advance(59)
    assert post("203.0.113.7") == 429                                # a refused try doesn't count against them
    clock.advance(2)                                                 # the minute has passed since the first ten
    assert [post("203.0.113.7") for _ in range(11)] == [200] * 10 + [429]
    [limiter] = made
    assert (limiter.limiter.per_minute, limiter.limiter.forget_over) == (10, 50_000)
    # never the address itself: the limiter is given a short hash of it, and holds nothing else
    assert set(limiter.asked) == {api.counted_by("203.0.113.7"), api.counted_by("203.0.113.8")}
    assert all("203.0.113" not in key and len(key) == 16 for key in limiter.asked)


def test_the_limiter_forgets_visitors_with_nothing_in_the_last_minute():
    """The shared limiter's own tests look inside it (wts-core, tests/test_usage_limits.py); here, that forgetting
    the idle never changes who is let in."""
    from wts_core.testing import FixedClock

    clock = FixedClock()
    limiter = RateLimiter(2, forget_over=3, clock=clock)
    for who in ("a", "b", "c"):
        assert limiter.allow(who)
    clock.advance(30)
    assert limiter.allow("d")                                        # over three, but all were here this minute
    clock.advance(40)                                                # a, b and c were last here 70 seconds ago
    assert limiter.allow("d") and not limiter.allow("d")             # d is still counted: two this minute
    assert limiter.allow("e") and not limiter.allow("d")
    assert [limiter.allow("a"), limiter.allow("a"), limiter.allow("a")] == [True, True, False]   # counted afresh


def test_the_limiter_counts_rightly_from_many_threads():
    from concurrent.futures import ThreadPoolExecutor

    limiter = RateLimiter(100, forget_over=50)
    with ThreadPoolExecutor(8) as pool:
        mine = list(pool.map(lambda _: limiter.allow("one visitor"), range(400)))
        others = list(pool.map(lambda i: limiter.allow(f"visitor {i}"), range(400)))
    assert sum(mine) == 100 and all(others)


def test_each_route_says_too_many_in_its_own_words(client, settings):
    for _ in range(10):
        assert client.post("/api/missed", json={"q": "nobody homes"}).status_code == 200
    r = client.post("/api/missed", json={"q": "nobody homes"})
    assert r.status_code == 429 and r.json() == {"ok": False}
    r = client.post("/api/corrections", json={"message": "Wrong grade"})
    assert r.status_code == 429 and r.json() == {"ok": False, "error": "too many reports; try again in a minute"}
    r = client.post("/api/statements", json={"name": "Jane Example"})
    assert r.status_code == 429 and r.json() == {"ok": False, "error": "too many tries; try again in a minute"}
    r = client.get("/admin/approve/not-a-token")
    assert r.status_code == 429 and "<h1>Too many tries</h1><p>Try again in a minute.</p>" in r.text
    from landlords.replies import open_replies
    from landlords.state import own

    replies = open_replies(settings)
    assert replies.reports() == [] and replies.statements() == []    # nothing refused was kept
    assert own(settings).top_missed() == [("nobody homes", 10)]


# The state database's connections ------------------------------------------------------------------------------------


def test_every_connection_to_the_state_database_is_closed_after_use(settings, monkeypatch):
    from landlords import status
    from landlords.replies import open_replies
    from landlords.state import State, open_state

    (settings.data_dir / "site" / "landlords" / "x").mkdir(parents=True)
    (settings.data_dir / "site" / "landlords" / "x" / "index.html").write_text("<h1>X</h1>")
    opened = []
    connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: opened.append(connect(*a, **k)) or opened[-1])
    db = open_state(settings)
    state, replies = State(db), open_replies(settings, db)
    rid = replies.report(kind="wrong", page="landlords/x/", message="Wrong grade", contact="a@b.org")
    sid = replies.submit(name="Jane Example", role="Chief executive", item="landlords/x/", text="Our own words.",
                         link="", email="a@b.org")
    replies.publish(sid, checked="phoned")
    token = state.add_approval("20261101-000000", 7)
    state.mark(token, "published_at")
    state.missed("nobody homes")
    replies.close(rid, outcome="resolved", note="fixed")
    assert replies.reports() == [] and replies.waiting().reports == 0
    assert replies.statement(sid)["status"] == "published" and replies.waiting().statements == 0
    assert [entry["action"] for entry in replies.log(sid)] == ["received", "published"]
    assert state.approval(token)["published_at"] and state.top_missed() == [("nobody homes", 1)]
    assert replies.forget_old_emails() == 0
    assert status.waiting(settings, None) is None
    with pytest.raises(sqlite3.OperationalError), db.connect() as con:
        con.execute("insert into missed (day, query, count) values ('2026-11-12', 'half done', 1)")
        con.execute("insert into no_such_table values (1)")
    assert state.top_missed() == [("nobody homes", 1)]              # an error undoes the work, and still closes
    assert len(opened) >= 15
    for con in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            con.execute("select 1")
