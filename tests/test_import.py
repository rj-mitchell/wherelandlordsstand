"""The one-off import of the site's old rows into the shared package's tables (src/landlords/state.py, ``imports``;
wts-core docs/adr/0005).

tests/golden/old-state.sql is a state database made by the site's own code before the move, with rows of every
kind: a report from before reports had a kind, with no page and no email; open and closed reports; statements
pending, published (one updated since), declined and withdrawn, one withdrawn so long ago that its email address had
already been deleted; missed searches; approval links. tests/golden/old-state.json is what the old code read from
it. Here the site as it is now opens that database, and must read the same.
"""

from __future__ import annotations

import json
import sqlite3
import stat
import sys
from pathlib import Path

import pytest
from wts_core.testing import FixedClock

sys.path.insert(0, str(Path(__file__).parent / "golden"))

import shared  # noqa: E402

from landlords import notify, statements  # noqa: E402
from landlords.replies import open_replies  # noqa: E402
from landlords.state import OLD_TABLES, State, open_state  # noqa: E402

GOLDEN = shared.read("old-state.json")
NOW = shared.START                    # when the old code's figures were read: 13 November 2026


def dump(path: Path, tables=None) -> list[str]:
    """Every statement that would make the database again, for the tables named (all of them if none are)."""
    con = sqlite3.connect(path)
    try:
        return [line for line in con.iterdump()
                if tables is None or any(f'"{t}"' in line or f"TABLE {t} " in line for t in tables)]
    finally:
        con.close()


def not_the_packages(lines: list[str]) -> list[str]:
    """A dump without the shared package's tables (and SQLite's own count of their rows)."""
    return [line for line in lines if "wts_" not in line and "sqlite_sequence" not in line]


def rows(path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


@pytest.fixture
def old(settings):
    """A data folder holding the old database and the pages its statements are about."""
    shared.fixture_site(settings.data_dir)
    con = sqlite3.connect(settings.state_db)
    con.executescript((shared.GOLDEN / "old-state.sql").read_text())
    con.close()
    return settings


def test_every_old_row_is_brought_across_and_the_old_tables_are_left_as_they_were(old):
    before = dump(old.state_db)
    counts = {t: rows(old.state_db, f"select count(*) from {t}")[0][0] for t in OLD_TABLES}
    assert counts == {"reports": 6, "statements": 6, "statement_log": 15}

    db = open_state(old, FixedClock(NOW))

    after = dump(old.state_db)
    assert not_the_packages(after) == before                                 # nothing of the site's own has changed
    assert dump(old.state_db, OLD_TABLES) == [line for line in before if any(f'"{t}"' in line or f"TABLE {t} " in line
                                                                             for t in OLD_TABLES)]
    assert {t: rows(old.state_db, f"select count(*) from wts_{t}")[0][0] for t in OLD_TABLES} == counts

    # reports: the email becomes the contact, what was done the private note; a closed one is recorded as resolved
    assert rows(old.state_db, "select id, at, kind, page, message, contact, status, closed_at, resolution, "
                              "public_note, briefing_id from wts_reports order by id") == [
        (1, "2026-06-20T08:00:00+00:00", None, None, "From before kinds, with no page", None, "open", None, None,
         None, None),
        (2, "2026-11-03T09:00:00+00:00", "wrong", "landlords/x/", "Wrong grade", "reader@example.org", "open", None,
         None, None, None),
        (3, "2026-11-03T09:00:00+00:00", "takedown", "areas/leeds/", "Please remove my name.", None, "open", None,
         None, None, None),
        (4, "2026-11-03T09:00:00+00:00", "unfair", None, "Loaded words", "c@d.org", "open", None, None, None, None),
        (5, "2026-11-03T09:00:00+00:00", "wrong", "landlords/y/", "A merger you missed", None, "resolved",
         "2026-11-03T10:00:00+00:00", "fixed alias", None, None),
        (6, "2026-11-03T09:00:00+00:00", "other", "landlords/z/", "Closed with nothing said", None, "resolved",
         "2026-11-03T10:00:00+00:00", None, None, None),
    ]
    # statements: column for column, the page as the item and the landlord as whom it is about
    assert rows(old.state_db, "select id, at, item, part, about, name, role, text, link, email, status, "
                              "published_at, updated_at, closed_at, reason from wts_statements order by id") == rows(
        old.state_db, "select id, at, page, part, landlord, name, role, text, link, email, status, published_at, "
                      "updated_at, closed_at, reason from statements order by id")
    assert rows(old.state_db, "select id, statement, at, action, note, previous from wts_statement_log order by id") \
        == [(*row, None) for row in rows(old.state_db, "select id, statement, at, action, note from statement_log "
                                                       "order by id")]
    # the note of how each sender was confirmed, which the old table also kept in a column, is in the log
    assert rows(old.state_db, "select s.id, l.note from wts_statements s join wts_statement_log l on l.statement = "
                              "s.id and l.action = 'published' order by s.id") == rows(
        old.state_db, "select id, checked from statements where checked is not null order by id")
    # new rows are numbered on from the old ones
    replies = open_replies(old, db, FixedClock(NOW))
    assert replies.report(kind="wrong", page="", message="A new report") == 7
    assert replies.submit(name="New Author", role="Director, Example Housing", item="landlords/example-housing/",
                          text="A new statement here.", link="", email="new@example.org") == 7
    assert dump(old.state_db, OLD_TABLES) == [line for line in before if any(f'"{t}"' in line or f"TABLE {t} " in line
                                                                             for t in OLD_TABLES)]


def test_a_copy_of_the_database_as_it_was_is_kept_and_a_second_start_imports_nothing(old):
    before = dump(old.state_db)
    open_state(old, FixedClock(NOW))
    copy = old.data_dir / "state.pre-wts-core.2026-11-13.db"
    assert copy.is_file() and stat.S_IMODE(copy.stat().st_mode) == 0o600      # it holds email addresses
    # the whole file as it was, with the package's tables made in it and still empty
    assert not_the_packages(dump(copy)) == before
    assert not [line for line in dump(copy) if line.startswith('INSERT INTO "wts_') and "wts_schema" not in line]
    imported = "select name, applied_at from wts_schema where name like 'import:%'"
    assert rows(old.state_db, imported) == [("import:landlords-reports-and-statements", "2026-11-13T09:00:00+00:00")]

    after_first = dump(old.state_db)
    copy.unlink()
    open_state(old, FixedClock("2026-11-14T09:00:00+00:00"))                  # the next day's start
    open_replies(old, clock=FixedClock("2026-11-14T09:00:00+00:00")).waiting()
    assert dump(old.state_db) == after_first                                  # nothing imported twice
    assert not list(old.data_dir.glob("state.pre-wts-core.*"))                # and no second copy


def test_the_site_reads_from_the_imported_rows_what_it_read_from_its_own(old):
    clock = FixedClock(NOW)
    db = open_state(old, clock)
    replies = open_replies(old, db, clock)

    # the owner's list of open reports: requests to remove a person's details first, as before; then the newest
    # first, where they were the oldest first (wts-core docs/AS-BUILT.md, cli: "lists are newest first")
    now = [{"id": r["id"], "at": r["at"], "kind": r["kind"], "page": r["page"], "message": r["message"],
            "email": r["contact"]} for r in replies.reports()]
    then = [r | {"page": r["page"] or None} for r in GOLDEN["open_reports"]]   # no page: kept as none, not as ""
    assert sorted(now, key=lambda r: r["id"]) == sorted(then, key=lambda r: r["id"])
    assert [r["id"] for r in now] == [3, 4, 2, 1] and [r["id"] for r in then] == [3, 1, 2, 4]

    # the counts in the weekly email, and the email itself (which now names `landlords reports list`)
    waiting = replies.waiting()
    assert (waiting.reports, waiting.statements) == (GOLDEN["open_report_count"], GOLDEN["pending_statement_count"])
    _, body = notify.report({"build": "no new pages"}, None, {
        "open_reports": waiting.reports, "pending_statements": waiting.statements, "missed": []})
    assert body == GOLDEN["weekly_email"].replace("(landlords reports)", "(landlords reports list)").replace(
        "(landlords statements). We reply within", "(landlords statements list). We reply within")

    # every statement as the owner sees it, and its log
    for was in GOLDEN["statements"]:
        s = replies.statement(was["id"])
        log = replies.log(was["id"])
        assert {"id": s["id"], "at": s["at"], "name": s["name"], "role": s["role"], "page": s["item"],
                "part": s["part"], "text": s["text"], "link": s["link"], "email": s["email"], "status": s["status"],
                "landlord": s["about"], "reason": s["reason"], "published_at": s["published_at"],
                "updated_at": s["updated_at"], "closed_at": s["closed_at"],
                "checked": next((e["note"] for e in log if e["action"] == "published"), None)} == was
        assert [[e["at"], e["action"], e["note"]] for e in log] == GOLDEN["logs"][str(was["id"])]

    # what the pages are given, and the pages themselves, byte for byte
    assert statements.published(old) == [
        {"id": s["id"], "item": s["page"], "part": s["part"], "about": s["landlord"], "name": s["name"],
         "role": s["role"], "text": s["text"], "link": s["link"], "date": (s["updated_at"] or s["published_at"])[:10]}
        for s in sorted(GOLDEN["shown"], key=lambda s: (s["updated_at"] or s["published_at"], s["id"]))]
    assert statements.refresh(old) == {"pages_changed": 3, "shown": 2}
    assert shared.pages(old.data_dir / "site") == GOLDEN["pages"]

    # the site's own tables are where they were: approval links still open their pages, missed searches are counted
    assert rows(old.state_db, "select build, published_at from approvals order by build") == [
        ("20261101-000000", "2026-11-06T10:00:00+00:00"), ("20261105-000000", None)]
    assert State(db).top_missed(28) == [("nobody homes", 3), ("example hsg", 1)]

    # nothing is deleted or lapses on the day of the move that would not have been deleted before it
    assert replies.forget_old_emails() == GOLDEN["forgotten_at_the_next_tidy"] == 0
    assert replies.lapse_undecided() == (0, 0)
    assert [s["status"] for s in replies.statements()] == [s["status"] for s in reversed(GOLDEN["statements"])]


def test_what_has_waited_three_months_lapses_at_the_first_tidy(old):
    """wts-core docs/AS-BUILT.md, replies: "The first write after the import can lapse old rows at once: any imported
    statement that has waited more than three months, and the contact of any report open that long." The site took
    its first statement on 12 November 2026, so nothing on the server is that old; this is what would happen."""
    con = sqlite3.connect(old.state_db)
    con.execute("update statements set at = '2026-08-01T09:00:00+00:00' where id = 4")           # still pending
    con.execute("update reports set at = '2026-08-01T09:00:00+00:00' where id = 2")              # still open
    con.commit()
    con.close()
    clock = FixedClock(NOW)
    replies = open_replies(old, clock=clock)
    assert (replies.statement(4)["status"], replies.statement(4)["email"]) == ("pending", "pat@example.gov.uk")
    waiting = replies.waiting()                                    # the first look at what is waiting
    assert (waiting.reports, waiting.statements) == (4, 0)
    lapsed = replies.statement(4)
    assert (lapsed["status"], lapsed["email"], lapsed["reason"]) == (
        "declined", None, "No decision was made in time; please send it again")
    assert replies.log(4)[-1]["action"] == "lapsed"
    [report] = [r for r in replies.reports() if r["id"] == 2]      # still open, its sender's address deleted
    assert report["contact"] is None and report["closed_at"] is None


def test_a_database_from_before_reports_had_a_kind_is_imported_too(settings):
    """A backup made before 12 November 2026, put back with `landlords restore`: its reports table has no kind."""
    settings.data_dir.mkdir(parents=True)
    con = sqlite3.connect(settings.state_db)
    con.executescript("""
        create table reports (id integer primary key, at text not null, page text, message text not null, email text,
          closed_at text, outcome text);
        insert into reports (at, page, message, email) values ('2026-11-05T09:00:00+00:00', 'landlords/x/', 'Wrong', NULL);
        create table statements (id integer primary key, at text not null, name text not null, role text not null,
          page text not null, part text not null default '', text text not null, link text, email text,
          status text not null default 'pending', landlord text, checked text, reason text, published_at text,
          updated_at text, closed_at text);
        create table statement_log (id integer primary key, statement integer not null, at text not null,
          action text not null, note text);
    """)
    con.close()
    [report] = open_replies(settings, clock=FixedClock(NOW)).reports()
    assert (report["kind"], report["page"], report["message"]) == (None, "landlords/x/", "Wrong")


def test_a_new_site_has_nothing_to_import(settings):
    db = open_state(settings, FixedClock(NOW))
    assert db.tables() >= {"wts_reports", "wts_statements", "wts_statement_log", "missed", "approvals"}
    assert not db.tables() & set(OLD_TABLES)                      # the old tables are no longer made
    assert not list(settings.data_dir.glob("state.pre-wts-core.*"))
    assert rows(settings.state_db, "select count(*) from wts_schema where name like 'import:%'") == [(0,)]


def test_going_back_carries_what_was_written_since_into_the_old_tables(old):
    """deploy/undo-wts-core.sql, for the owner to run if the site must go back to the code before the shared
    package: it writes the old tables again from the package's, so nothing sent or decided in between is lost."""
    clock = FixedClock(NOW)
    replies = open_replies(old, clock=clock)
    clock.advance(hours=1)
    rid = replies.report(kind="wrong", page="", message="Sent since the move", contact="since@example.org")
    replies.close(2, outcome="dismissed", note="not ours to change")
    sid = replies.submit(name="New Author", role="Director, Example Housing", link="",
                         item="landlords/example-housing/#grade", text="Sent since the move.", email="n@example.org")
    replies.publish(sid, checked="phoned since the move")
    replies.publish(4, checked="letter", about="example-council")
    replies.remove(3, "it names a tenant")
    replies.update(2, text="Words changed since the move.", note="the author's newer version")

    undo = (Path(__file__).parents[1] / "deploy" / "undo-wts-core.sql").read_text()
    con = sqlite3.connect(old.state_db)
    con.executescript(undo)
    con.close()

    got = rows(old.state_db, f"select id, kind, page, message, email, closed_at is not null, outcome from reports "
                             f"where id in (2, 4, 6, {rid}) order by id")
    assert got == [(2, "wrong", "landlords/x/", "Wrong grade", None, 1, "not ours to change"),
                   (4, "unfair", "", "Loaded words", "c@d.org", 0, None),
                   (6, "other", "landlords/z/", "Closed with nothing said", None, 1, ""),
                   (rid, "wrong", "", "Sent since the move", "since@example.org", 0, None)]
    assert rows(old.state_db, "select id, page, part, landlord, status, checked, reason, text from statements "
                              f"where id in (2, 3, 4, {sid}) order by id") == [
        (2, "landlords/example-housing/", "bands", "example-housing", "published",
         "replied from the landlord's own address", None, "Words changed since the move."),
        # the old code has no "removed": a statement the site took down was "withdrawn" there, with the reason
        (3, "areas/leeds/", "", "example-council", "withdrawn", "phoned the council", "it names a tenant",
         "Our homes in Leeds are\nlisted rightly.\n\nThank you."),
        (4, "areas/leeds/", "", "example-council", "published", "letter", None, "Still waiting for a decision."),
        (sid, "landlords/example-housing/", "grade", "example-housing", "published", "phoned since the move", None,
         "Sent since the move."),
    ]
    assert rows(old.state_db, "select count(*) from statement_log") == rows(
        old.state_db, "select count(*) from wts_statement_log")
    # the old code shows a statement with the date of its last update, if it has one, or of its publishing
    assert rows(old.state_db, "select id, updated_at >= published_at from statements where updated_at is not null") \
        == [(2, 1)]
    assert json.dumps(rows(old.state_db, "select count(*) from missed")) == "[[2]]"      # the site's own: untouched
