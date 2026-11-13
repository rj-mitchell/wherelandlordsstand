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
``wts_`` tables, once (``IMPORTS``). The old tables are left exactly as they were, and a copy of the whole file as
it was is kept beside it first, as ``state.pre-wts-core.<date>.db``; ``landlords nightly`` deletes that copy once
it is older than the backups are kept. docs/OPERATIONS.md, "The state database", says how to go back.
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

from wts_core import replies
from wts_core.ops import BackupSpec
from wts_core.ports import SYSTEM_CLOCK, Clock
from wts_core.state import Import, StateDB, iso

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
BACKUPS = BackupSpec(prefix="landlords-state-", stamp="%Y%m%d-%H%M%S", keep=14,
                     required_tables=("missed", "approvals"))
# How many copies are kept off-site (one a night: about two months, as the privacy page says). Nothing else that
# holds old rows, such as the copy made before the import, is kept longer.
BACKUPS_KEPT_DAYS = 60

OLD_TABLES = ("reports", "statements", "statement_log")


def imports(path: Path) -> tuple[Import, ...]:
    """The one-off copy of the site's old rows into the shared package's tables (wts-core docs/adr/0005).

    A report's ``email`` becomes its ``contact`` and its ``outcome`` (what was done, in the owner's words) its
    private note; a closed report is recorded as resolved. A statement's ``page`` becomes its ``item`` and its
    ``landlord`` whom it is ``about``; the note of how its sender was confirmed is already in its log. A report made
    before reports had a kind has none, and a database from before then has no such column to copy."""
    kind = "kind" if "kind" in _columns(path, "reports") else "NULL"
    return (Import(
        name="landlords-reports-and-statements",
        statements=(
            "INSERT INTO wts_reports (id, at, kind, page, message, contact, status, closed_at, resolution) "
            f"SELECT id, at, {kind}, nullif(page, ''), message, email, "
            "CASE WHEN closed_at IS NULL THEN 'open' ELSE 'resolved' END, closed_at, nullif(outcome, '') FROM reports",
            "INSERT INTO wts_statements (id, at, item, part, about, name, role, text, link, email, status, "
            "published_at, updated_at, closed_at, reason) SELECT id, at, page, part, landlord, name, role, text, "
            "nullif(link, ''), email, status, published_at, updated_at, closed_at, reason FROM statements",
            "INSERT INTO wts_statement_log (id, statement, at, action, note) SELECT id, statement, at, action, note "
            "FROM statement_log",
        ),
        needs=OLD_TABLES,
    ),)


def _columns(path: Path, table: str) -> set[str]:
    if not path.exists():
        return set()
    con = sqlite3.connect(path, timeout=30)
    try:
        return {row[1] for row in con.execute(f"pragma table_info({table})")}  # noqa: S608 (a fixed name)
    finally:
        con.close()


def open_state(settings: Settings, clock: Clock = SYSTEM_CLOCK) -> StateDB:
    """The state database, with the shared package's tables and this site's own made on the way in, and the old
    rows brought across the first time."""
    db = StateDB(settings.state_db, migrations=replies.migrations(), imports=imports(settings.state_db), clock=clock)
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
