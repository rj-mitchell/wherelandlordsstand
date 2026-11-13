"""Statements in a landlord's own words, beside what the site says about it: the right of reply (the charity's
impartiality policy, section 7.2; docs/DECISIONS.md, 15; src/landlords/statements.py)."""

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from landlords import statements as st
from landlords.api import State, create_app, report_kind
from landlords.config import load_toml
from landlords.statements import slot

W = load_toml("wording.toml")
WORDS = "Our survey was carried out after a big change to our repairs service, and we have published newer results."
FORM = {"name": "Jane Example", "role": "Chief executive, Example Housing", "page": "landlords/example-housing/",
        "part": "", "text": WORDS, "link": "https://example.org/results", "email": "jane@example-housing.org.uk"}


def landlord_page(slug: str, name: str, parts=st.PARTS) -> str:
    """A landlord's page as the build writes it, cut down to its slots: one beside each part of the card, one after."""
    card = "".join(f'<section><h3 id="{p}">{p}</h3><p>Our words.</p>{slot(p)}</section>' for p in parts)
    return f'<h1>{name}</h1><section class="card">{card}</section>{slot("page")}<h2>Figures</h2>'


@pytest.fixture
def site(settings):
    """data/site with two landlords' pages and an area's page, and the files that hold the published figures."""
    root = settings.data_dir / "site"
    for slug, name, parts in (("example-housing", "Example Housing", st.PARTS),
                              ("example-council", "Example Council", ("grade", "bands", "ombudsman"))):
        (root / "landlords" / slug).mkdir(parents=True)
        (root / "landlords" / slug / "index.html").write_text(landlord_page(slug, name, parts))
    (root / "areas" / "leeds").mkdir(parents=True)
    from landlords.site_pages import area_html

    p = {"slug": "example-council", "name": "Example Council", "grade": {"grade": "C2"}, "bands": {}}
    (root / "areas" / "leeds" / "index.html").write_text(
        area_html({"name": "Leeds", "slug": "leeds", "landlords": [(p, 1000, "")], "sources": set()}, W, {}))
    (root / "index.html").write_text("<h1>home</h1>")
    (root / "names.json").write_text(json.dumps([{"n": "Example Housing", "s": "example-housing"}]))
    (root / "data" / "landlords").mkdir(parents=True)
    (root / "data" / "landlords.csv").write_text("landlord_id,name\nL1,Example Housing\n")
    (root / "data" / "landlords" / "example-housing.json").write_text('{"name":"Example Housing"}')
    return root


@pytest.fixture
def client(settings, site):
    return TestClient(create_app(settings))


@pytest.fixture
def state(settings):
    return State(settings.data_dir / "state.db")


def post(client, **fields):
    return client.post("/api/statements", data={**FORM, **fields}, follow_redirects=False)


# Sending one: the checks --------------------------------------------------------------------------------------------


def test_a_statement_from_the_form_is_kept_as_pending(client, state):
    r = post(client)
    assert r.status_code == 303 and r.headers["location"] == "/named/thanks.html"
    [s] = state.statements()
    assert (s["status"], s["page"], s["part"], s["landlord"]) == ("pending", "landlords/example-housing/", "",
                                                                   "example-housing")
    assert (s["name"], s["role"], s["text"], s["email"]) == (FORM["name"], FORM["role"], WORDS, FORM["email"])
    assert state.statement_log(s["id"])[0][1] == "received"


def test_up_to_150_words(client, state):
    assert post(client, text=" ".join(["word"] * 150)).status_code == 303
    r = post(client, text=" ".join(["word"] * 151))
    assert r.status_code == 400 and "up to 150 words. This one is 151" in r.text
    assert "word word" in r.text                      # their words are given back to copy, escaped
    assert len(state.statements()) == 1


@pytest.mark.parametrize("field, value, says", [
    ("name", "", "the name"), ("role", " ", "your role"), ("text", "", "write the statement"),
    ("email", "", "email address"), ("email", "not-an-address", "email address"),
    ("page", "", "address of a page"), ("page", "https://example.org/landlords/example-housing/", "address of a page"),
    ("page", "/compare/", "address of a page"), ("page", "landlords/nobody-at-all/", "couldn't find that page"),
    ("link", "javascript:alert(1)", "full web address"), ("link", "https://example.org/a b", "full web address"),
])
def test_what_is_needed(client, state, field, value, says):
    r = client.post("/api/statements", json={**FORM, field: value})
    assert r.status_code == 400 and says in r.json()["error"]
    assert state.statements() == []


def test_what_is_too_long_is_refused_never_cut_to_fit(client, state):
    """A statement is published as written or declined, never edited (the policy, 7.2): so one longer than a limit
    is refused, with words for the sender, where it used to be cut at the limit and kept."""
    long = " ".join(["extraordinarily"] * 140)                    # within 150 words, but 2,239 characters
    r = post(client, text=long)
    assert r.status_code == 400 and "A statement can be up to 2,000 characters. This one is 2,239." in r.text
    assert f">{long}</textarea>" in r.text                       # given back whole, to copy and shorten
    for field, value, says in (
            ("text", long, "A statement can be up to 2,000 characters. This one is 2,239."),
            ("name", "N" * 121, "Your name can be up to 120 characters. This one is 121."),
            ("role", "R" * 201, "Your role can be up to 200 characters. This one is 201."),
            ("link", "https://example.org/" + "a" * 281, "The link to the record can be up to 300 characters. This "
                                                         "one is 301."),
            ("email", "a" * 189 + "@example.org", "Please give an email address, so we can confirm who the statement "
                                                  "is from.")):
        r = client.post("/api/statements", json={**FORM, field: value})
        assert r.status_code == 400 and r.json() == {"ok": False, "error": says}, field
    assert state.statements() == []


def test_what_is_just_within_the_limits_is_kept_as_written(client, state):
    words = ["a" * 20] + ["b" * 19] * 99                           # 100 words; 2,000 characters with a space between
    exact = {"name": "N" * 120, "role": "R" * 200, "text": " ".join(words),
             "link": "https://example.org/" + "a" * 280, "email": "a" * 188 + "@example.org"}
    assert [len(v) for v in exact.values()] == [120, 200, 2000, 300, 200]
    assert client.post("/api/statements", json={**FORM, **exact}).status_code == 200
    # a browser sends each line break as two characters: they are counted as one, as its own limit counts them
    assert post(client, text="\r\n".join(words)).status_code == 303
    one, two = state.statements()
    assert {k: one[k] for k in exact} == exact
    assert two["text"] == "\n".join(words)


def test_more_than_the_form_can_take_is_refused_unread(client, state):
    r = post(client, text="word " * 5000)                          # 150 words would fit many times over
    assert r.status_code == 400 and "What you sent is too long. A statement can be up to 150 words." in r.text
    assert "Back to the form" in r.text and "<textarea" not in r.text
    r = client.post("/api/statements", json={**FORM, "text": "word " * 5000})
    assert r.status_code == 400 and r.json() == {"ok": False, "error": "What you sent is too long. A statement can be "
                                                                       "up to 150 words."}
    assert state.statements() == []


@pytest.mark.parametrize("body", [b"{not json", b'["a", "list"]', b'"words"', b"\xff\xfe"])
def test_a_json_body_that_cannot_be_read_is_refused_like_any_other(client, state, body):
    r = client.post("/api/statements", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert r.json() == {"ok": False, "error": "We couldn't read what was sent. Please send it again."}
    assert state.statements() == []


def test_the_page_can_be_given_in_any_of_the_ways_people_copy_it():
    for address in ("https://wherelandlordsstand.com/landlords/example-housing/",
                    "https://www.wherelandlordsstand.com/landlords/example-housing/index.html",
                    "wherelandlordsstand.com/landlords/example-housing", "/landlords/example-housing/"):
        assert st.item(address) == ("landlords/example-housing/", "", "example-housing"), address
    assert st.item("https://wherelandlordsstand.com/landlords/example-housing/#bands") == (
        "landlords/example-housing/", "bands", "example-housing")
    assert st.item("landlords/example-housing/#figures")[1] == ""          # not a part of the card: after it
    assert st.item("landlords/example-housing/", "safety")[1] == "safety"
    assert st.item("https://wherelandlordsstand.com/areas/leeds/", "grade") == ("areas/leeds/", "", None)


def test_the_hidden_field_robots_fill_in_keeps_nothing(client, state):
    r = post(client, website="https://spam.example")
    assert r.status_code == 303 and r.headers["location"] == "/named/thanks.html"
    assert state.statements() == []


# The owner's commands --------------------------------------------------------------------------------------------------


def run(*args) -> tuple[int, str]:
    from landlords.cli import app

    r = CliRunner().invoke(app, ["statements", *args])
    return r.exit_code, r.output


def test_the_owner_lists_publishes_updates_and_withdraws(client, state, site, tmp_path):
    post(client)
    post(client, page="https://wherelandlordsstand.com/areas/leeds/", name="Sam Officer",
         role="Head of housing, Example Council")
    code, out = run()
    assert code == 0 and [json.loads(x)["id"] for x in out.splitlines()] == [1, 2]

    assert run("--publish", "1")[0] == 1                                # how was the sender confirmed?
    note = "replied from the landlord's own address, 14 Nov"
    code, out = run("--publish", "1", "--checked", note)
    assert code == 0 and json.loads(out)["status"] == "published"
    # the note is kept for good (in the log, and in the statement's own row), so it holds no email address: the
    # sender's is deleted three months after a statement is withdrawn or declined
    assert state.statement(1)["checked"] == state.statement_log(1)[1][2] == note
    page = (site / "landlords" / "example-housing" / "index.html").read_text()
    assert "Statement from Jane Example, " in page                     # on the site at once

    code, out = run("--publish", "2", "--checked", "phoned the council")
    assert code == 1 and "--landlord" in out                           # an area's page: which landlord?
    assert run("--publish", "2", "--checked", "phoned", "--landlord", "nobody")[0] == 1
    assert run("--publish", "2", "--checked", "phoned the council", "--landlord", "example-council")[0] == 0
    assert "Statement from Sam Officer" in (site / "areas" / "leeds" / "index.html").read_text()
    assert "Statement from Sam Officer" in (site / "landlords" / "example-council" / "index.html").read_text()

    words = tmp_path / "new.txt"
    words.write_text("Our newer results are published every quarter on our website.")
    assert run("--update", "1", "--text-file", str(words), "--reason", "the author's new version")[0] == 0
    assert "every quarter" in (site / "landlords" / "example-housing" / "index.html").read_text()
    assert state.statement(1)["updated_at"]
    words.write_text(" ".join(["word"] * 151))
    assert run("--update", "1", "--text-file", str(words))[0] == 1     # an update keeps to the rules too

    words.write_text(" ".join(["extraordinarily"] * 140))
    code, out = run("--update", "1", "--text-file", str(words))        # and is never cut to fit either
    assert code == 1 and "Not done: A statement can be up to 2,000 characters. This one is 2,239." in out
    assert run("--update", "1", "--name", "N" * 121)[0] == 1
    assert run("--update", "1", "--role", "R" * 201)[0] == 1
    assert run("--update", "1", "--link", "https://example.org/" + "a" * 281)[0] == 1
    assert state.statement(1)["text"] == "Our newer results are published every quarter on our website."
    assert (state.statement(1)["name"], state.statement(1)["link"]) == (FORM["name"], FORM["link"])

    assert run("--withdraw", "1")[0] == 1                              # why?
    assert run("--withdraw", "1", "--reason", "withdrawn by the author")[0] == 0
    assert "Statement from" not in (site / "landlords" / "example-housing" / "index.html").read_text()
    assert run("--publish", "1", "--checked", "again")[0] == 1         # only a pending one can be published

    code, out = run("--log", "1")
    assert [json.loads(x)["action"] for x in out.splitlines()] == ["received", "published", "updated", "withdrawn"]
    code, out = run("--all")
    assert [json.loads(x)["status"] for x in out.splitlines()] == ["withdrawn", "published"]


def test_the_owner_declines_with_reasons(client, state, site):
    post(client)
    assert run("--decline", "1")[0] == 1
    assert run("--decline", "1", "--reason", "it is about a tenant")[0] == 0
    s = state.statement(1)
    assert (s["status"], s["reason"]) == ("declined", "it is about a tenant") and s["closed_at"]
    assert "Statement from" not in (site / "landlords" / "example-housing" / "index.html").read_text()
    assert run()[1] == ""                                              # nothing waiting


def test_the_email_is_deleted_three_months_after_a_statement_is_withdrawn_or_declined(client, state):
    for _ in range(3):
        post(client)
    st.decline(state, 1, "breaks the rules")
    st.withdraw(state, 2, "withdrawn by the author")
    db = sqlite3.connect(state.path)
    db.execute("update statements set closed_at = '2026-08-12T10:00:00+00:00' where id in (1, 2)")
    db.commit()
    assert st.forget_old_emails(state, datetime(2026, 11, 12, 9, 0, tzinfo=UTC)) == 0      # not yet three months
    assert st.forget_old_emails(state, datetime(2026, 11, 12, 11, 0, tzinfo=UTC)) == 2
    assert [s["email"] for s in state.statements()] == [None, None, FORM["email"]]          # kept while pending
    assert st.months_ago(datetime(2026, 5, 31, tzinfo=UTC), 3) == datetime(2026, 2, 28, tzinfo=UTC)


def test_the_weekly_email_says_how_many_are_waiting():
    from landlords.notify import report

    _, body = report({"build": None}, None, {"pending_statements": 2})
    assert "Statements from landlords waiting for a decision: 2 (landlords statements)" in body


# How it is shown -------------------------------------------------------------------------------------------------------


def shown(**s) -> dict:
    return {"id": 7, "name": "Jane Example", "role": "Chief executive, Example Housing", "page":
            "landlords/example-housing/", "part": "", "text": WORDS, "link": "", "landlord": "example-housing",
            "published_at": "2026-11-12T10:00:00+00:00", "updated_at": None} | s


def test_a_statement_is_headed_and_marked_as_the_glossary_says():
    html = st.render(shown(text="Line one <b>bold</b>\nline two\n\npara two", link="https://example.org/r?a=1&b=2"),
                     W, 2)
    assert '<div class="statement" role="note" id="statement-7" aria-labelledby="statement-7-h">' in html
    assert '<h2 id="statement-7-h">Statement from Jane Example, 12 November 2026</h2>' in html
    assert html.endswith('<p class="st-note">In their own words. Not checked or endorsed by Where Landlords Stand.'
                         "</p></div>")
    assert "<p>Line one &lt;b&gt;bold&lt;/b&gt;<br>line two</p><p>para two</p>" in html     # as written, escaped
    assert '<a href="https://example.org/r?a=1&amp;b=2" rel="nofollow">The record they point to</a>' in html
    assert "updated" not in html and "Right of reply" not in html
    assert "13 November 2026" in st.render(shown(updated_at="2026-11-13T09:00:00+00:00"), W, 2)  # the newer version


def test_beside_its_item_and_on_the_landlords_own_page(site):
    items = [shown(id=1, part="bands"), shown(id=2, part="safety", page="landlords/example-council/",
                                                 landlord="example-council"),
             shown(id=3, page="areas/leeds/", landlord="example-council", name="Sam Officer")]
    assert st.write_into(site, items) == 3
    housing = (site / "landlords" / "example-housing" / "index.html").read_text()
    council = (site / "landlords" / "example-council" / "index.html").read_text()
    area = (site / "areas" / "leeds" / "index.html").read_text()
    # beside the bands, inside that part of the card, under its heading level
    assert re.search(r'<h3 id="bands">.*?<!--statements:bands--><div class="statement"[^>]*><h4', housing, re.S)
    # the council's page has no safety checks: its statement goes after the card
    assert re.search(r'<!--statements:page--><div class="statement" role="note" id="statement-2"', council)
    # a statement about an area's page: on that page, and on the landlord's own page with a link to the area
    assert 'id="statement-3"' in area and area.index('class="warn"') < area.index('id="statement-3"')
    assert ('<p class="st-about">This statement is about <a href="../../areas/leeds/index.html">what we say on the '
            'page for Leeds</a>.</p>') in council
    assert st.write_into(site, items) == 0                              # nothing new: nothing written
    assert st.write_into(site, []) == 3                                 # taken down: the slots are empty again
    assert (site / "landlords" / "example-housing" / "index.html").read_text() == landlord_page(
        "example-housing", "Example Housing")


def test_published_now_and_kept_through_a_build_publish_and_undo(client, settings, state, site):
    from landlords import publish

    for name in ("20261110-000000", "20261111-000000"):            # the live build, and one waiting for approval
        b = publish.builds_dir(settings) / name
        (b / "landlords" / "example-housing").mkdir(parents=True)
        (b / "landlords" / "example-housing" / "index.html").write_text(landlord_page("example-housing", "E"))
        (b / "build-info.json").write_text(json.dumps({"build": name, "checks_failed": []}))
    publish.publish(settings, "20261110-000000")
    post(client)
    st.publish(state, 1, "checked", None, lambda slug: True)
    assert st.refresh(settings) == {"pages_changed": 3, "shown": 1}    # both builds and data/site
    publish.publish(settings, "20261111-000000")                       # approving the waiting pages keeps it
    assert "Statement from Jane Example" in (settings.data_dir / "live" / "landlords" / "example-housing" /
                                             "index.html").read_text()
    st.withdraw(state, 1, "withdrawn by the author")
    publish.rollback(settings)                                         # an undo doesn't bring it back
    assert "Statement from" not in (settings.data_dir / "live" / "landlords" / "example-housing" /
                                    "index.html").read_text()


# Never part of the published figures -----------------------------------------------------------------------------------


def test_statements_never_reach_the_search_the_compare_data_or_the_downloads(site):
    before = {p: p.read_bytes() for p in site.rglob("*") if p.is_file() and p.suffix != ".html"}
    st.write_into(site, [shown(id=1, text="A very particular phrase from the landlord.")])
    after = {p: p.read_bytes() for p in site.rglob("*") if p.is_file() and p.suffix != ".html"}
    assert before == after                                       # names.json, the CSV files, compare's JSON untouched
    assert "very particular phrase" in (site / "landlords" / "example-housing" / "index.html").read_text()
    assert all("very particular phrase" not in p.read_text() for p in site.rglob("index.html")
               if "landlords/example-housing" not in p.as_posix())


def test_only_the_statements_module_and_the_api_read_the_statements_table():
    """The figures, bands, checks, search index, compare data and downloads are made by modules that never read
    statements: only statements.py (and the owner's command, through it) reads them, only api.py touches the table."""
    src = Path(__file__).parents[1] / "src" / "landlords"
    for path in src.rglob("*.py"):
        text = path.read_text()
        name = path.relative_to(src).as_posix()
        if name != "api.py":
            assert not re.search(r"(from|into|update|table)\s+statements\b", text, re.I), name
        if name not in ("statements.py", "cli.py", "api.py"):
            assert ".statements(" not in text and ".statement(" not in text, name
        if name not in ("statements.py", "site.py"):           # the build writes the published ones into its pages
            assert "statements.published" not in text, name
    for name in ("profile.py", "score.py", "checks.py", "area.py", "register.py", "load/common.py"):
        assert "statement" not in (src / name).read_text().lower(), name
    pages = (src / "site_pages.py").read_text()
    for fn in ("def names_json", "def landlord_json", "def downloads("):
        body = pages[pages.index(fn):].split("\ndef ", 1)[0]
        assert "statement" not in body.lower(), fn


# The report form, the corrections page and "If you're named" -----------------------------------------------------------


def test_report_kinds_and_links_that_choose_one(client, settings):
    from landlords.site_pages import corrections_html

    (settings.data_dir / "site" / "corrections").mkdir()
    html = corrections_html(W)
    (settings.data_dir / "site" / "corrections" / "index.html").write_text(html)
    labels = re.findall(r'<label for="kind-\w+">([^<]+)</label>', html)
    assert labels[:2] == ["Something is wrong", "You&#x27;ve been characterised unfairly"]
    assert 'name="kind" value="wrong" checked>' in html
    assert "<strong>We reply within 5 working days, and decide within 20 working days.</strong>" in html
    assert '<a href="../named/index.html">If you&#x27;re named on this site</a>' in html
    for kind, chosen in (("unfair", "unfair"), ("takedown", "takedown"), ("complaint", "unfair"),
                         ("correction", "wrong"), ("nonsense", "wrong")):
        page = client.get(f"/corrections/?kind={kind}").text
        assert re.findall(r'name="kind" value="(\w+)" checked>', page) == [chosen], kind
    page = client.get('/corrections/index.html?page="><script>x</script>').text
    assert 'value="&quot;&gt;&lt;script&gt;x&lt;/script&gt;"' in page and "<script>x" not in page
    assert client.get("/corrections/").text == html                     # no query: the page as built
    assert report_kind("Takedown") == "takedown" and report_kind("") == ""

    r = client.post("/api/corrections", data={"kind": "unfair", "page": "landlords/x/", "message": "a loaded word"},
                    follow_redirects=False)
    assert r.status_code == 303
    client.post("/api/corrections", data={"kind": "takedown", "message": "my name"})
    assert [r[2] for r in State(settings.data_dir / "state.db").open_reports()] == ["takedown", "unfair"]  # first


def test_the_hidden_field_robots_fill_in_keeps_no_report(client, settings):
    """The report form has the statement form's trap: a field people never see or reach, which a robot fills in."""
    from landlords.site_pages import corrections_html

    html = corrections_html(W)
    assert ('<div class="hp" aria-hidden="true"><label for="website">Leave this empty</label>'
            '<input id="website" name="website" type="text" tabindex="-1" autocomplete="off"></div>') in html
    assert html.index('name="email"') < html.index('name="website"') < html.index('<button type="submit">')
    assert "<script" not in html.split("<main", 1)[1].split("</main>", 1)[0]
    (settings.data_dir / "site" / "corrections").mkdir()
    (settings.data_dir / "site" / "corrections" / "thanks.html").write_text("thanks")
    report = {"kind": "wrong", "message": "Buy cheap pills", "email": "robot@spam.example"}
    r = client.post("/api/corrections", data={**report, "website": "https://spam.example"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/corrections/thanks.html"   # thanked like anyone
    r = client.post("/api/corrections", json={**report, "website": "https://spam.example"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    state = State(settings.data_dir / "state.db")
    assert state.open_reports() == []                                # and nothing kept
    r = client.post("/api/corrections", data={**report, "website": " "}, follow_redirects=False)
    assert r.status_code == 303 and len(state.open_reports()) == 1   # left empty, as people leave it: kept


def test_the_named_page(settings, client):
    from landlords.site_pages import named_html

    html = named_html(settings, W)
    text = html.replace("&#x27;", "'")
    assert "<h1>If you're named</h1>" in text
    for words in ("Something is wrong", "You've been characterised unfairly", "Add a statement in your own words",
                  "We reply within 5 working days, and decide within 20 working days.",
                  "Statement from [your name], [the date it is published]",
                  "In their own words. Not checked or endorsed by Where Landlords Stand.",
                  "Who decides, and how to appeal", "mailto:admin@wheretheystand.uk", "three months",
                  'href="../corrections/index.html?kind=wrong"', 'href="../corrections/index.html?kind=unfair"',
                  'href="../named/index.html#send"', 'action="../api/statements"', "the bands we work out",
                  "which companies we count as part of a group", "the homes we list"):
        assert words in text, words
    for name in ("name", "role", "page", "part", "text", "link", "email", "website"):
        assert f'name="{name}"' in html, name
    assert '<div class="hp" aria-hidden="true">' in html and 'tabindex="-1"' in html
    assert "<script" not in html
    (settings.data_dir / "site" / "named").mkdir()
    (settings.data_dir / "site" / "named" / "index.html").write_text(html)
    page = client.get("/named/?page=https://wherelandlordsstand.com/landlords/example-housing/&part=bands").text
    assert 'id="page" name="page" value="https://wherelandlordsstand.com/landlords/example-housing/"' in page
    assert '<option value="bands" selected>' in page


def test_every_page_links_to_the_named_page_beside_corrections():
    from landlords.site import page

    html = page("T", "", W, depth=1)
    assert ('<li><a href="../corrections/index.html">Corrections and problems</a></li>'
            '<li><a href="../named/index.html">If you&#x27;re named</a></li>') in html
