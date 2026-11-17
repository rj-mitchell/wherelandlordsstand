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
ROOT = Path(__file__).resolve().parents[1]
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
    # first, where they were the oldest first (the package's lists are newest first)
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
    assert shared.as_before(shared.pages(old.data_dir / "site")) == GOLDEN["pages"]

    # the site's own tables are where they were: approval links still open their pages, missed searches are counted
    assert rows(old.state_db, "select build, published_at from approvals order by build") == [
        ("20261101-000000", "2026-11-06T10:00:00+00:00"), ("20261105-000000", None)]
    assert State(db).top_missed(28) == [("nobody homes", 3), ("example hsg", 1)]

    # nothing is deleted or lapses on the day of the move that would not have been deleted before it
    assert replies.forget_old_emails() == GOLDEN["forgotten_at_the_next_tidy"] == 0
    assert replies.lapse_undecided() == (0, 0)
    assert [s["status"] for s in replies.statements()] == [s["status"] for s in reversed(GOLDEN["statements"])]


def test_what_has_waited_three_months_lapses_at_the_first_tidy(old, monkeypatch):
    """The first write after the import can lapse old rows at once: any imported statement that has waited more than
    three months, and the contact of any report open that long. The site took
    its first statement on 12 November 2026, so nothing on the server is that old; this is what would happen."""
    con = sqlite3.connect(old.state_db)
    con.execute("update statements set at = '2026-08-01T09:00:00+00:00' where id = 4")           # still pending
    con.execute("update reports set at = '2026-08-01T09:00:00+00:00' where id = 2")              # still open
    con.commit()
    con.close()
    clock = FixedClock(NOW)
    replies = open_replies(old, clock=clock)
    assert (replies.statement(4)["status"], replies.statement(4)["email"]) == ("pending", "pat@example.gov.uk")
    # the owner can see it coming: `landlords lapsing` reads and does nothing
    from typer.testing import CliRunner

    from landlords.cli import app

    monkeypatch.setattr("landlords.cli.CLOCK", clock)
    said = json.loads(CliRunner().invoke(app, ["lapsing"]).output)
    assert said["statements"] == [{"id": 4, "at": "2026-08-01T09:00:00+00:00", "days": 104}]
    assert said["reports"] == [{"id": 2, "at": "2026-08-01T09:00:00+00:00", "days": 104}]
    assert "@" not in json.dumps(said) and replies.statement(4)["status"] == "pending"
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

    log_then = rows(old.state_db, "select count(*) from wts_statement_log")
    undo(old.state_db)

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
    # every line of the log goes back. (Read before the undo: since wts-core 0.3.0 the script ends by forgetting the
    # move, which empties the package's tables; test_going_back_and_coming_forward_again_counts_nothing_twice.)
    assert rows(old.state_db, "select count(*) from statement_log") == log_then
    # the old code shows a statement with the date of its last update, if it has one, or of its publishing
    assert rows(old.state_db, "select id, updated_at >= published_at from statements where updated_at is not null") \
        == [(2, 1)]
    assert json.dumps(rows(old.state_db, "select count(*) from missed")) == "[[2]]"      # the site's own: untouched


def run_script(path: Path, name: str) -> None:
    """One of the scripts in deploy/, run as docs/OPERATIONS.md says: the whole file, on the database."""
    con = sqlite3.connect(path)
    try:
        con.executescript((ROOT / "deploy" / name).read_text())
    finally:
        con.close()          # a script that stopped part-way is rolled back: nothing is changed


def undo(path: Path) -> None:
    run_script(path, "undo-wts-core.sql")


def redo(path: Path) -> None:
    run_script(path, "redo-wts-core.sql")


def count(path: Path, table: str, where: str = "1") -> int:
    return rows(path, f"select count(*) from {table} where {where}")[0][0]


# going back without the undo script, and coming forward again (wts-core 0.3.0)

# The old code's kind of write, as its own code made each (src/landlords/api.py before the move, which wrote every
# time as `datetime.now(UTC).isoformat(timespec="seconds")`): a reader's report, a statement sent with the first line
# of its log, and the owner's decision on a statement, which adds a line to the log. An hour after the move.
AFTER_THE_MOVE = "2026-11-13T10:01:00+00:00"
OLD_CODE_WRITES = {
    "reports": [f"insert into reports (at, page, message, email, kind) values ('{AFTER_THE_MOVE}', 'landlords/x/', "
                "'Sent to the old code after the move.', 'after@example.org', 'wrong')"],
    "statements": [f"insert into statements (id, at, name, role, page, part, text, link, email, landlord) values (7, "
                   f"'{AFTER_THE_MOVE}', 'Old Code', 'Director, Example Housing', 'landlords/example-housing/', '', "
                   "'Sent to the old code after the move.', NULL, 'oldcode@example.org', 'example-housing')",
                   f"insert into statement_log (statement, at, action) values (7, '{AFTER_THE_MOVE}', 'received')"],
    "statement_log": ["update statements set status = 'published', published_at = '" + AFTER_THE_MOVE + "', checked "
                      "= 'phoned, on the old code' where id = 4",
                      f"insert into statement_log (statement, at, action, note) values (4, '{AFTER_THE_MOVE}', "
                      "'published', 'phoned, on the old code')"],
}


def written_by_the_old_code(path: Path, *what: str) -> None:
    con = sqlite3.connect(path)
    for sql in (sql for kind in what for sql in OLD_CODE_WRITES[kind]):
        con.execute(sql)
    con.commit()
    con.close()


@pytest.mark.parametrize("what", sorted(OLD_CODE_WRITES))
def test_a_row_the_old_code_wrote_after_the_move_stops_the_new_code_and_the_words_name_the_mend(old, what):
    """wts-core 0.3.0, `state.StateError` and `Import(written_at=…)`: the site is put back on its old code
    without deploy/undo-wts-core.sql, the old code takes a report, a statement or a decision, and the new code is
    deployed again. The import is marked as done and would be skipped: what was written meanwhile would be silently
    missing. The new code refuses to open the database, changes nothing, and says what to run."""
    from wts_core.state import StateError

    from landlords.api import create_app
    from landlords.state import IMPORTS

    assert IMPORTS[0].written_at == {"reports": "at", "statements": "at", "statement_log": "at"}  # UPGRADING's line
    clock = FixedClock(NOW)
    open_state(old, clock)                                         # the move
    clock.advance(hours=2)
    open_state(old, clock)                                         # as it stands, the database opens
    written_by_the_old_code(old.state_db, what)
    before = dump(old.state_db)
    with pytest.raises(StateError) as refused:
        open_state(old, clock)
    said = str(refused.value)
    table = "statement_log" if what == "statement_log" else what
    assert (f"{table} has 1 row written after the import 'landlords-reports-and-statements' ran "
            "(2026-11-13T09:00:00+00:00)") in said
    if what == "statements":                                       # a statement sent adds the first line of its log
        assert "statement_log has 1 row written after" in said
    assert "Nothing has been changed" in said and dump(old.state_db) == before
    # the package's words for the mend, and then this site's: which of its two scripts, and what each discards
    assert "run the site's script for undoing the move" in said
    assert "deploy/redo-wts-core.sql, which keeps what the old code wrote" in said
    assert "Do not run undo-wts-core.sql to keep what the old code wrote" in said
    assert 'docs/OPERATIONS.md, "Going back, and coming forward again"' in said
    # and the site does not start, nor does a command of the owner's, nor the nightly housekeeping
    with pytest.raises(StateError):
        create_app(old, clock=clock)
    with pytest.raises(StateError):
        open_replies(old, clock=clock)
    assert dump(old.state_db) == before


def test_the_mend_brings_across_what_the_old_code_wrote_meanwhile(old):
    """deploy/redo-wts-core.sql forgets the move and touches nothing else: the next start of the new code makes the
    move afresh, and what the old code wrote since is there."""
    from wts_core.state import StateError

    clock = FixedClock(NOW)
    open_state(old, clock)
    clock.advance(hours=2)
    written_by_the_old_code(old.state_db, *OLD_CODE_WRITES)
    old_tables_then = dump(old.state_db, OLD_TABLES)
    with pytest.raises(StateError):
        open_state(old, clock)
    redo(old.state_db)
    assert dump(old.state_db, OLD_TABLES) == old_tables_then        # the old tables are not touched
    assert count(old.state_db, "wts_reports") == count(old.state_db, "wts_statements") == 0
    assert count(old.state_db, "wts_statement_log") == 0
    assert count(old.state_db, "wts_schema", "name = 'import:landlords-reports-and-statements'") == 0
    replies = open_replies(old, clock=clock)                       # the new code starts: the move made afresh
    assert "Sent to the old code after the move." in [r["message"] for r in replies.reports()]
    assert (replies.statement(7)["text"], replies.statement(7)["status"]) == (
        "Sent to the old code after the move.", "pending")
    assert replies.statement(4)["status"] == "published"
    assert replies.log(4)[-1]["note"] == "phoned, on the old code"
    assert count(old.state_db, "wts_reports") == 7 and count(old.state_db, "wts_statements") == 7
    assert rows(old.state_db, "select applied_at from wts_schema where name = "
                              "'import:landlords-reports-and-statements'") == [("2026-11-13T11:00:00+00:00",)]
    open_state(old, clock)                                         # and it opens from then on
    # a second run of either script on a database whose move has been forgotten changes nothing
    redo(old.state_db)
    forgotten = dump(old.state_db)
    for script in (redo, undo):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            script(old.state_db)
        assert dump(old.state_db) == forgotten


def test_the_undo_script_run_in_that_state_would_discard_what_the_old_code_wrote(old):
    """Why the refusal's words name deploy/redo-wts-core.sql and warn against the other: deploy/undo-wts-core.sql
    writes the old tables afresh from the package's. That is right before the old code is started, and for the
    false alarm (the server's clock put back). Run after the old code has written, it discards those rows, as its
    own heading says."""
    open_state(old, FixedClock(NOW))
    written_by_the_old_code(old.state_db, *OLD_CODE_WRITES)
    undo(old.state_db)
    assert count(old.state_db, "reports", "message = 'Sent to the old code after the move.'") == 0
    assert count(old.state_db, "statements", "id = 7") == 0
    assert "WHAT THIS DISCARDS. Anything the OLD code has written" in (ROOT / "deploy" / "undo-wts-core.sql").read_text()


def test_the_nightly_housekeeping_of_the_old_tables_never_looks_like_the_old_code_writing(old, monkeypatch):
    """wts-core docs/EXTENDING.md, section 6: the nightly tidy of the old tables never trips the check on rows
    written since the import, since it changes and deletes rows and adds none. Nights on the new code, with readers and the owner at
    work each day and addresses deleted from the old rows on several of them: the database opens every morning."""
    clock = FixedClock(NOW)
    replies = open_replies(old, clock=clock)                       # the move: 13 November 2026
    for night, work in enumerate((
            lambda: replies.close(2, outcome="resolved", note="fixed"),
            lambda: replies.withdraw(2, "withdrawn by the author"),
            lambda: replies.report(kind="wrong", page="", message="Sent on the new code.", contact="new@example.org"),
            lambda: replies.close(4, outcome="dismissed"),
            lambda: replies.publish(4, checked="letter", about="example-council")), start=14):
        clock.set(f"2026-11-{night - 1}T15:00:00+00:00")
        work()
        clock.set(f"2026-11-{night}T04:55:00+00:00")
        nightly(monkeypatch, clock)
        clock.set(f"2026-11-{night}T09:00:00+00:00")
        open_state(old, clock)
    # the old rows were changed by those nights (addresses deleted), and nothing was added to the old tables
    assert rows(old.state_db, "select id, email from reports where id in (2, 4)") == [(2, None), (4, None)]
    assert (count(old.state_db, "reports"), count(old.state_db, "statements"), count(old.state_db, "statement_log")) \
        == (6, 6, 15)
    # and on the drop night, and after it, the old tables are gone and nothing is looked at
    clock.set("2027-02-01T04:55:00+00:00")
    assert nightly(monkeypatch, clock)["old_tables_dropped"] == list(OLD_TABLES)
    clock.advance(days=1)
    open_state(old, clock)


def test_going_back_and_coming_forward_again_counts_nothing_twice(old):
    """wts-core docs/UPGRADING.md, "Going back to the old code": the undo script ends by forgetting the move.
    The old code then runs; the new code, started again, makes the move afresh. Every report, statement and line of
    a log is there once, as the old code left it, with what it took in meanwhile. Before 0.3.0 the owner had to do
    that by hand, and a second move over the package's rows failed on the first number already there."""
    clock = FixedClock(NOW)
    replies = open_replies(old, clock=clock)
    clock.advance(hours=1)
    rid = replies.report(kind="wrong", page="", message="Sent since the move", contact="since@example.org")
    replies.publish(4, checked="letter", about="example-council")
    replies.remove(3, "it names a tenant")
    reports, statements_, log = (count(old.state_db, f"wts_{t}") for t in OLD_TABLES)

    undo(old.state_db)
    # the move is forgotten: the package's copies are empty and the mark is gone; the site's own tables are kept
    for table in ("wts_reports", "wts_statements", "wts_statement_log"):
        assert count(old.state_db, table) == 0, table
    assert count(old.state_db, "wts_schema", "name = 'import:landlords-reports-and-statements'") == 0
    assert count(old.state_db, "missed") == 2 and count(old.state_db, "approvals") == 2
    assert (count(old.state_db, "reports"), count(old.state_db, "statements"), count(old.state_db, "statement_log")) \
        == (reports, statements_, log)
    # undone twice: the second stops at its first step and changes nothing
    undone = dump(old.state_db)
    with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
        undo(old.state_db)
    assert dump(old.state_db) == undone

    # the old code runs for a day, and takes a report in
    written_by_the_old_code(old.state_db, "reports")
    clock.set("2026-11-15T09:00:00+00:00")
    again = open_replies(old, clock=clock)                         # the new code, started again: the move afresh
    assert count(old.state_db, "wts_reports") == reports + 1      # each once, and the old code's one
    assert count(old.state_db, "wts_statements") == statements_ and count(old.state_db, "wts_statement_log") == log
    assert [r["id"] for r in again.reports(open_only=False)].count(rid) == 1
    # a statement the site removed went back as "withdrawn", which is what the old tables can hold
    assert (again.statement(3)["status"], again.statement(4)["status"]) == ("withdrawn", "published")
    assert (old.data_dir / "state.pre-wts-core.2026-11-15.db").is_file()     # a copy first, as on the first move


def test_the_two_scripts_forget_the_move_with_the_same_statements():
    def forgetting(name: str) -> list[str]:
        text = (ROOT / "deploy" / name).read_text()
        return [line for line in text[text.index("-- Forgetting the move"):].splitlines()
                if line and not line.startswith("--")]

    assert forgetting("undo-wts-core.sql") == forgetting("redo-wts-core.sql") == [
        "DELETE FROM wts_statement_log;", "DELETE FROM wts_statements;", "DELETE FROM wts_reports;",
        "DELETE FROM wts_schema WHERE name = 'import:landlords-reports-and-statements';", "COMMIT;"]
    for name in ("undo-wts-core.sql", "redo-wts-core.sql"):
        assert "WHAT THIS DISCARDS" in (ROOT / "deploy" / name).read_text(), name


# the old tables after the move: kept within the site's promises, then dropped (state.RETIRING)


def nightly(monkeypatch, clock) -> dict:
    """`landlords nightly`, at the time the clock says."""
    from typer.testing import CliRunner

    from landlords.cli import app

    monkeypatch.setattr("landlords.cli.CLOCK", clock)
    result = CliRunner().invoke(app, ["nightly"])
    assert result.exit_code == 0, result.output
    # what it did, as one line of JSON; then, last, the shared package's own line for writing the file out afresh
    # (wts-core 0.3.0: the tidy's last step, `cli.write_afresh`, in place of the site's VACUUM)
    said, afresh = result.output.splitlines()
    assert afresh == "Wrote the database out afresh: nothing deleted is left in the file."
    return json.loads(said)


def holds(path: Path, *addresses: str) -> list[str]:
    """Which of these email addresses are anywhere in a file's bytes, whatever their case: in a row, or in space
    SQLite has stopped using and not wiped. A backup is unpacked first."""
    import gzip

    raw = path.read_bytes()
    raw = (gzip.decompress(raw) if path.name.endswith(".gz") else raw).lower()
    return [a for a in addresses if a.lower().encode() in raw]


def backup(settings, clock, to: Path) -> Path:
    from wts_core import ops

    from landlords.state import BACKUPS

    return ops.make_backup(settings.state_db, to, BACKUPS, clock=clock)


def test_what_the_site_deletes_is_deleted_from_the_old_tables_the_file_and_the_backups_made_after(
        old, monkeypatch, tmp_path):
    """The old tables stay for the way back, and both independent reviews of the sister sites' moves found that they
    then kept what the site had promised to delete, in the live file and in every night's backup. Here: an address
    deleted from the package's tables is gone that night from the old row, from the file's bytes, and from a backup
    made then; and once everything is due and the old tables have been dropped, no address is anywhere."""
    import re

    from landlords.state import DROP_OLD_TABLES_ON

    every = sorted(set(re.findall(r"[\w.+-]+@[\w.-]+\.\w+", (shared.GOLDEN / "old-state.sql").read_text())))
    assert len(every) == 7 and "reader@example.org" in every and "recent@example.org" in every
    con = sqlite3.connect(old.state_db)
    # a statement that ended long enough ago to be due before the old tables go, whose address the owner once wrote
    # into the note of how its sender was confirmed, in another case (the old code did not stop that)
    con.execute("update statements set closed_at = '2026-10-20T10:00:00+00:00', checked = 'replied from "
                "Recent@Example.org', reason = 'RECENT@example.org asked' where id = 6")
    con.execute("update statement_log set note = 'replied from Recent@Example.org' where statement = 6 and "
                "action = 'published'")
    con.commit()
    con.close()
    clock = FixedClock(NOW)
    replies = open_replies(old, clock=clock)                       # the move: 13 November 2026
    copy = old.data_dir / "state.pre-wts-core.2026-11-13.db"
    assert holds(old.state_db, *every) == every and "old@example.org" not in every   # that one went before the move

    # the next day the owner closes two reports and withdraws the two statements that are shown
    clock.advance(days=1)
    replies.close(2, outcome="resolved", note="fixed")
    replies.close(4, outcome="dismissed")
    replies.withdraw(2, "withdrawn by the author")
    replies.withdraw(3, "withdrawn by the author")
    said = nightly(monkeypatch, clock)
    assert (said["old_rows_cleared"], said["old_tables_dropped"]) == (2, [])
    assert rows(old.state_db, "select id, email from reports where id in (2, 4)") == [(2, None), (4, None)]
    night = backup(old, clock, tmp_path / "backups")
    for where in (old.state_db, night):
        assert holds(where, "reader@example.org", "c@d.org") == [], where       # gone from the bytes, not only the rows
    assert holds(copy, "reader@example.org", "c@d.org")       # the copy made before the move still has them: it is
    assert set(OLD_TABLES) <= open_state(old, clock).tables()  # kept as long as a backup is, and then deleted

    # three months after statement 6 ended: its address goes from the package's row and notes, and from the old ones
    clock.set("2027-01-25T04:55:00+00:00")
    said = nightly(monkeypatch, clock)
    assert (said["emails_deleted"], said["old_rows_cleared"], said["old_tables_dropped"]) == (1, 4, [])
    assert said["old_copies_deleted"] == [copy.name] and not copy.exists()      # 73 days old: no backup is older
    assert rows(old.state_db, "select email, checked, reason from statements where id = 6") == [
        (None, "replied from [address deleted]", "[address deleted] asked")]
    assert rows(old.state_db, "select note from statement_log where statement = 6 and action = 'published'") == [
        ("replied from [address deleted]",)]
    night = backup(old, clock, tmp_path / "backups")
    for where in (old.state_db, night):
        assert holds(where, "recent@example.org") == [], where
    assert holds(old.state_db, *every)                             # the others are not due yet
    assert set(OLD_TABLES) <= open_state(old, clock).tables() and clock.now().date() < DROP_OLD_TABLES_ON

    # by 20 February everything is due: the two withdrawn in November, the one declined, and the one nobody decided
    # (it lapses); and the old tables' day has come
    clock.set("2027-02-20T04:55:00+00:00")
    said = nightly(monkeypatch, clock)
    assert (said["emails_deleted"], said["statements_lapsed"]) == (3, 1)
    assert said["old_tables_dropped"] == list(OLD_TABLES)
    db = open_state(old, clock)
    assert not db.tables() & set(OLD_TABLES)
    with db.connect() as con:
        left = [str(tuple(row)) for table in sorted(db.tables()) for row in con.execute(f"select * from {table}")]
    assert not [row for row in left if "@" in row]                  # no address in any row of any table
    night = backup(old, clock, tmp_path / "backups")
    for where in (old.state_db, night):
        assert holds(where, *every, "@example") == [], where        # nor anywhere in the file, nor in a backup of it
    assert nightly(monkeypatch, clock) == {                         # and the next night there is nothing to do
        "emails_deleted": 0, "statements_lapsed": 0, "report_emails_deleted": 0, "old_rows_cleared": 0,
        "old_tables_dropped": [], "old_copies_deleted": []}


def test_the_old_tables_go_on_the_first_of_february_2027_and_not_a_day_before(old, monkeypatch):
    from landlords.state import DROP_OLD_TABLES_ON

    clock = FixedClock(NOW)
    open_state(old, clock)
    assert DROP_OLD_TABLES_ON.isoformat() == "2027-02-01"
    clock.set("2027-01-31T23:00:00+00:00")
    assert nightly(monkeypatch, clock)["old_tables_dropped"] == []
    assert set(OLD_TABLES) <= open_state(old, clock).tables()
    clock.set("2027-02-01T04:55:00+00:00")
    assert nightly(monkeypatch, clock)["old_tables_dropped"] == list(OLD_TABLES)
    db = open_state(old, clock)                                    # a start after the drop imports nothing again
    assert not db.tables() & set(OLD_TABLES) and db.tables() >= {"wts_reports", "missed", "approvals"}
    assert rows(old.state_db, "select count(*) from wts_statements") == [(6,)]
    # the scripts for going back and for making the move again need the old tables: after the drop each fails whole,
    # changing nothing (the second would otherwise forget a move it could not make again)
    before = dump(old.state_db)
    for name, script in (("undo-wts-core.sql", undo), ("redo-wts-core.sql", redo)):
        assert "1 February 2027" in (ROOT / "deploy" / name).read_text()
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            script(old.state_db)
        assert dump(old.state_db) == before
    assert rows(old.state_db, "select count(*) from wts_statements") == [(6,)]


def test_a_backup_from_before_statements_is_put_back_and_its_reports_are_brought_across(settings, tmp_path, caplog):
    """The oldest backup `landlords restore` accepts is from 4 November 2026, when the approval links arrived (it
    asks for ``missed`` and ``approvals``). Statements, their log and a report's kind arrived on the 12th. The
    import needs only ``reports``, which every such backup has, so it is not passed over (wts-core 0.2.1: an import
    that needs a table an older backup lacks is skipped for ever, and the site shows nothing of what it held)."""
    import logging

    from typer.testing import CliRunner

    from landlords.cli import app
    from landlords.state import IMPORTS

    assert [(i.name, i.needs) for i in IMPORTS] == [("landlords-reports-and-statements", ("reports",))]
    before = tmp_path / "before" / "state.db"
    before.parent.mkdir()
    con = sqlite3.connect(before)
    con.executescript("""
        create table reports (id integer primary key, at text not null, page text, message text not null, email text,
          closed_at text, outcome text);
        create table missed (day text not null, query text not null, count integer not null default 0,
          primary key (day, query));
        create table approvals (token_hash text primary key, build text not null, created text not null,
          expires text not null, published_at text, rolled_back_at text);
        insert into reports (at, page, message, email) values ('2026-11-05T09:00:00+00:00', 'landlords/x/',
          'Wrong grade', 'reader@example.org');
        insert into reports (at, page, message, email, closed_at, outcome) values ('2026-11-06T09:00:00+00:00', '',
          'A merger you missed', NULL, '2026-11-07T09:00:00+00:00', 'fixed alias');
        insert into missed values ('2026-11-05', 'nobody homes', 2);
    """)
    con.close()
    clock = FixedClock(NOW)
    archive = backup(type(settings)(**{**settings.__dict__, "data_dir": before.parent}), clock, tmp_path / "backups")
    result = CliRunner().invoke(app, ["restore", str(archive), "--yes"])
    assert result.exit_code == 0, result.output
    with caplog.at_level(logging.WARNING, logger="wts_core.state"):
        replies = open_replies(settings, clock=clock)              # the site starts on the backup put back
    assert not caplog.records                                      # nothing was passed over
    assert [(r["id"], r["kind"], r["page"], r["message"], r["contact"], r["status"], r["resolution"])
            for r in sorted(replies.reports(open_only=False), key=lambda r: r["id"])] == [
        (1, None, "landlords/x/", "Wrong grade", "reader@example.org", "open", None),
        (2, None, None, "A merger you missed", None, "resolved", "fixed alias")]
    assert replies.statements() == []
    assert rows(settings.state_db, "select name from wts_schema where name like 'import:%'") == [
        ("import:landlords-reports-and-statements",)]
    assert State(open_state(settings, clock)).top_missed(28) == [("nobody homes", 2)]
