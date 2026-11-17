"""The state database, ``data/state.db``: the one thing that can't be rebuilt from the publishers' files.

It is a small SQLite file opened through the Where They Stand sites' shared package (wts-core, ``wts_core.state``;
its docs/adr/0005). Two kinds of table live in it:

* The shared package's own, each named ``wts_…``: readers' reports and statements from landlords
  (``wts_reports``, ``wts_statements``, ``wts_statement_log`` and the two beside them; src/landlords/replies.py).
  The package makes them, and only it reads or writes them.
* This site's own, made here: ``missed`` (searches that found nothing: the words and the day, as a count) and
  ``approvals`` (the links in the weekly email; only a hash of each token is kept, so the database can't approve).

Before wts-core the site kept reports and statements in tables of its own (``reports``, ``statements``,
``statement_log``). The first time the site starts on a database that has them, their rows are copied into the
``wts_`` tables, once (``IMPORTS``), and a copy of the whole file as it was is kept beside it first, as
``state.pre-wts-core.<date>.db``. The old tables stay for the way back (deploy/undo-wts-core.sql; and the move is
made again with deploy/redo-wts-core.sql, should the old code have run meanwhile), but not as they were for ever
(``RETIRING``): an email address the site has promised to delete is deleted from the old row on the night it is
deleted from the package's, and the old tables themselves are dropped on 1 February 2027. ``landlords nightly``
does both, deletes the copy once it is older than the backups are kept, and then writes the file out afresh, so
that nothing deleted is left in its unused space. docs/OPERATIONS.md, "The state database", says how to go back,
and until when.
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import date, timedelta
from hashlib import sha256

from wts_core import replies
from wts_core.ops import BackupSpec
from wts_core.ports import SYSTEM_CLOCK, Clock
from wts_core.state import Import, OldTables, StateDB, StateError, columns, iso

from landlords.config import Settings

OWN_TABLES = """
create table if not exists missed (day text not null, query text not null, count integer not null default 0,
  primary key (day, query));
create table if not exists approvals (token_hash text primary key, build text not null, created text not null,
  expires text not null, published_at text, rolled_back_at text);
"""

# What the site's backups are called and hold (`landlords backup`, `restore`, `backup-check`; src/landlords/cli.py).
# The name carries the time, so two in one day are two files, and "14 kept" is 14 runs: nightly, a fortnight.
# A restore takes only a database with these two tables, which every backup of this site has, made before the shared
# package or after, and which none of the charity's other sites has.
# The newest 60 are kept off-site (one a night: about two months, as the privacy page says). Nothing else that holds
# old rows, such as the copy made before the import, is kept longer.
BACKUPS_KEPT_DAYS = 60
BACKUPS = BackupSpec(prefix="landlords-state-", stamp="%Y%m%d-%H%M%S", keep=14, keep_offsite=BACKUPS_KEPT_DAYS,
                     required_tables=("missed", "approvals"))

OLD_TABLES = ("reports", "statements", "statement_log")


def _reports(con: sqlite3.Connection) -> list[str]:
    """A report made before reports had a kind has none, and a database from before then (an old backup, put back)
    has no such column to copy."""
    kind = "kind" if "kind" in columns(con, "reports") else "NULL"
    return ["INSERT INTO wts_reports (id, at, kind, page, message, contact, status, closed_at, resolution) "
            f"SELECT id, at, {kind}, nullif(page, ''), message, email, "
            "CASE WHEN closed_at IS NULL THEN 'open' ELSE 'resolved' END, closed_at, nullif(outcome, '') FROM reports"]


def _statements(con: sqlite3.Connection) -> list[str]:
    """Statements came to the site on 12 November 2026: a database from before then has neither table, and nothing
    of theirs to bring across."""
    out = []
    if columns(con, "statements"):
        out.append("INSERT INTO wts_statements (id, at, item, part, about, name, role, text, link, email, status, "
                   "published_at, updated_at, closed_at, reason) SELECT id, at, page, part, landlord, name, role, "
                   "text, nullif(link, ''), email, status, published_at, updated_at, closed_at, reason "
                   "FROM statements")
    if columns(con, "statement_log"):
        out.append("INSERT INTO wts_statement_log (id, statement, at, action, note) SELECT id, statement, at, "
                   "action, note FROM statement_log")
    return out


# The one-off copy of the site's old rows into the shared package's tables (wts-core docs/adr/0005). A report's
# ``email`` becomes its ``contact`` and its ``outcome`` (what was done, in the owner's words) its private note; a
# closed report is recorded as resolved. A statement's ``page`` becomes its ``item`` and its ``landlord`` whom it is
# ``about``; the note of how its sender was confirmed is already in its log. It needs only ``reports``, the one old
# table that every backup `landlords restore` accepts has: a backup from before statements is imported too.
#
# Going back is noticed (wts-core docs/UPGRADING.md, "Going back to the old code"): the column of
# each old table that holds the time a row was written. If the site is put back on its old code without
# deploy/undo-wts-core.sql being run, the old code adds rows to these tables again (a report, a statement, and a line
# of a statement's log for each decision); the import is marked as done and would not run a second time, so what was
# written meanwhile would be silently missing. With this the new code then refuses to open the database, naming the
# tables and the mend (``open_state``). The nightly tidy of the old tables (``RETIRING``) changes rows and adds none,
# so it never trips this.
IMPORTS = (Import(name="landlords-reports-and-statements", statements=(_reports, _statements), needs=("reports",),
                  written_at={"reports": "at", "statements": "at", "statement_log": "at"}),)

# Said after the package's own words when the database is refused because the old code has written to the old tables
# since the move (``Import.written_at``, above). The package says to run "the site's script for undoing the move".
# This site has two, and which is right depends on what happened: deploy/undo-wts-core.sql writes the old tables
# afresh from the package's, so run in that state it would discard the very rows the refusal is about.
WHICH_SCRIPT = ("On Where Landlords Stand there are two such scripts, and each discards something. If the old code "
                "was started after the move: deploy/redo-wts-core.sql, which keeps what the old code wrote and "
                "discards what the new code wrote between the move and then. If the old code was never started after "
                "the move (the false alarm): deploy/undo-wts-core.sql, which keeps what the new code wrote and writes "
                "the old tables afresh from it. Do not run undo-wts-core.sql to keep what the old code wrote: it would "
                "discard it. docs/OPERATIONS.md, \"Going back, and coming forward again\".")


# What becomes of the old tables once their rows have been brought across (wts-core docs/EXTENDING.md, "The old
# tables, after the import"). They
# stay in the file so that the move can be undone (deploy/undo-wts-core.sql), and while they do they keep to what
# the privacy page promises, each night (`landlords nightly`):
#
# * the email address of a statement is deleted from the old row once the package has deleted it from its own
#   (three months after the statement is withdrawn, declined or removed, or when it lapses);
# * where the package has taken that address out of a note or a reason too (it puts "[address deleted]" in its
#   place), the old copy of that note or reason is replaced by the package's;
# * the email address of a report is deleted from the old row once the report is closed, or has been open for
#   three months.
#
# From 1 February 2027 the old tables are dropped. After that day the undo script is of no use: going back means
# putting back a backup made before the move, while one is still kept.
DROP_OLD_TABLES_ON = date(2027, 2, 1)
_SCRUBBED = "'%[address deleted]%'"
RETIRING = OldTables(
    tables=OLD_TABLES,
    drop_on=DROP_OLD_TABLES_ON,
    nightly=(
        "UPDATE statement_log SET note = (SELECT w.note FROM wts_statement_log w WHERE w.id = statement_log.id) "
        f"WHERE id IN (SELECT w.id FROM wts_statement_log w WHERE w.note LIKE {_SCRUBBED}) "
        "AND note IS NOT (SELECT w.note FROM wts_statement_log w WHERE w.id = statement_log.id)",
        "UPDATE statements SET checked = (SELECT w.note FROM wts_statement_log w WHERE w.statement = statements.id "
        "AND w.action = 'published' ORDER BY w.id LIMIT 1) WHERE id IN (SELECT w.statement FROM wts_statement_log w "
        f"WHERE w.action = 'published' AND w.note LIKE {_SCRUBBED}) AND checked NOT LIKE {_SCRUBBED}",
        "UPDATE statements SET reason = (SELECT w.reason FROM wts_statements w WHERE w.id = statements.id) "
        f"WHERE id IN (SELECT w.id FROM wts_statements w WHERE w.reason LIKE {_SCRUBBED}) "
        "AND reason IS NOT (SELECT w.reason FROM wts_statements w WHERE w.id = statements.id)",
        "UPDATE statements SET email = NULL WHERE email IS NOT NULL AND id IN "
        "(SELECT id FROM wts_statements WHERE email IS NULL)",
        "UPDATE reports SET email = NULL WHERE email IS NOT NULL AND id IN "
        "(SELECT id FROM wts_reports WHERE contact IS NULL)",
    ))


def open_state(settings: Settings, clock: Clock = SYSTEM_CLOCK) -> StateDB:
    """The state database, with the shared package's tables and this site's own made on the way in, and the old
    rows brought across the first time. A database whose old tables hold rows written after the move (the site was
    put back on its old code without deploy/undo-wts-core.sql) is refused: nothing is changed, and the error says
    which script mends it."""
    try:
        db = StateDB(settings.state_db, migrations=replies.migrations(), imports=IMPORTS, clock=clock,
                     old_tables=RETIRING)
    except StateError as exc:
        if "newer than the import" not in str(exc):      # some other fault of the database's: as the package says it
            raise
        raise StateError(f"{exc} {WHICH_SCRIPT}") from exc
    with db.connect() as con:
        con.executescript(OWN_TABLES)
    return db


class State:
    """This site's own tables: missed searches and approval links."""

    def __init__(self, db: StateDB):
        self.db = db
        self.path = db.path

    def missed(self, query: str) -> None:
        with self.db.connect() as con:
            con.execute("insert into missed (day, query, count) values (?, ?, 1) on conflict (day, query) "
                        "do update set count = count + 1", (self.db.clock.now().date().isoformat(), query))

    def top_missed(self, days: int = 28, limit: int = 50) -> list[tuple]:
        since = (self.db.clock.now().date() - timedelta(days=days)).isoformat()
        with self.db.connect() as con:
            return [tuple(r) for r in con.execute(
                "select query, sum(count) n from missed where day >= ? group by query order by n desc limit ?",
                (since, limit))]

    # Approval links (publish.py, "approve"): only a hash of each token is kept, so the database can't approve.
    def add_approval(self, build: str, days: int) -> str:
        token = secrets.token_urlsafe(32)
        now = self.db.clock.now()
        with self.db.connect() as con:
            con.execute("insert into approvals (token_hash, build, created, expires) values (?, ?, ?, ?)",
                        (_hash(token), build, now.isoformat(timespec="seconds"),
                         (now + timedelta(days=days)).isoformat(timespec="seconds")))
        return token

    def approval(self, token: str) -> dict | None:
        """The approval a token is for, if it exists and hasn't expired."""
        with self.db.connect() as con:
            row = con.execute("select build, created, expires, published_at, rolled_back_at from approvals "
                              "where token_hash = ?", (_hash(token),)).fetchone()
        if not row or row["expires"] < iso(self.db.clock):
            return None
        return dict(row)

    def mark(self, token: str, field: str) -> None:
        assert field in ("published_at", "rolled_back_at")
        with self.db.connect() as con:
            con.execute(f"update approvals set {field} = ? where token_hash = ?",  # noqa: S608 (field is checked)
                        (iso(self.db.clock), _hash(token)))


def own(settings: Settings, clock: Clock = SYSTEM_CLOCK) -> State:
    return State(open_state(settings, clock))


def _hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()
