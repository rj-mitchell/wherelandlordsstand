"""The backup of the state database (`landlords backup`, `restore` and `backup-check`: the Where They Stand sites'
shared commands, wts-core's ``wts_core.ops``, with this site's names and lines; src/landlords/cli.py and
src/landlords/state.py, BACKUPS): a checked copy, written whole or not at all, as the sister sites make theirs."""

from __future__ import annotations

import gzip
import os
import sqlite3
import stat
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner
from wts_core import ops
from wts_core.testing import FixedClock

from landlords.cli import app
from landlords.state import BACKUPS

B2 = ("LANDLORDS_B2_BUCKET", "LANDLORDS_B2_KEY_ID", "LANDLORDS_B2_APPLICATION_KEY")


def make_backup(db, to, keep: int = 14, stamp: str = "20261101-041500"):
    """A backup as the command makes it, at the time ``stamp`` says."""
    when = datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
    return ops.make_backup(db, to, BACKUPS, keep=keep, clock=FixedClock(when))


def database(path, damaged: bool = False):
    """A state database with one report in it. ``damaged``: one whose pages SQLite's integrity check finds fault with
    (an index dropped from the list of tables, so its pages belong to nothing), though it still opens and copies."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("create table reports (id integer primary key, message text)")
    con.executemany("insert into reports (message) values (?)", [("a mistake " * 20,)] * 50)
    con.execute("create table missed (day text, query text, count integer)")    # the two tables every backup of
    con.execute("create table approvals (token_hash text primary key)")         # this site has (BACKUPS)
    if damaged:
        con.execute("create index by_message on reports (message)")
        con.commit()
        con.execute("pragma writable_schema = on")
        con.execute("delete from sqlite_master where name = 'by_message'")
    con.commit()
    con.close()
    return path


def names(folder) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_a_backup_is_a_checked_copy_and_the_newest_are_kept(tmp_path, monkeypatch):
    opened = []
    connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: opened.append(connect(*a, **k)) or opened[-1])
    db, dest = database(tmp_path / "data" / "state.db"), tmp_path / "backups"
    for stamp in ("20261101-041500", "20261102-041500", "20261102-180000"):
        out = make_backup(db, dest, keep=2, stamp=stamp)
    # two in one day are two files (the name carries the time); nothing else is left in the folder
    assert names(dest) == ["landlords-state-20261102-041500.sqlite.gz", "landlords-state-20261102-180000.sqlite.gz"]
    assert out == dest / "landlords-state-20261102-180000.sqlite.gz"
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress(out.read_bytes()))
    assert connect(restored).execute("select count(*) from reports").fetchone() == (50,)
    assert len(opened) == 7                                    # the database's own, then two for each backup
    for con in opened:                                         # every connection was closed, not left to be collected
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            con.execute("select 1")


def test_a_copy_that_fails_its_check_is_not_kept(tmp_path):
    dest = tmp_path / "backups"
    make_backup(database(tmp_path / "good" / "state.db"), dest, stamp="20261101-041500")
    with pytest.raises(RuntimeError, match="failed its integrity check"):
        make_backup(database(tmp_path / "data" / "state.db", damaged=True), dest, keep=1, stamp="20261102-041500")
    # no half-made file or temporary folder, and the last good backup is still there
    assert names(dest) == ["landlords-state-20261101-041500.sqlite.gz"]


@pytest.mark.parametrize("how", ["fails its check", "can't be read"])
def test_the_command_says_so_and_leaves_nothing_behind(settings, tmp_path, monkeypatch, how):
    for k in B2:
        monkeypatch.setenv(k, "x")                               # set up, so a good backup would be sent off-site
    db = database(settings.data_dir / "state.db", damaged=how == "fails its check")
    if how == "can't be read":
        with open(db, "r+b") as f:                               # two pages of the file overwritten
            f.seek(4096)
            f.write(b"\xff" * 8192)
    result = CliRunner().invoke(app, ["backup", "--to", str(tmp_path / "backups")])
    assert result.exit_code == 1 and result.output.startswith("Backup failed: "), result.output
    assert ("failed its integrity check" in result.output) == (how == "fails its check")
    assert "Off-site" not in result.output                       # a copy that can't be trusted is never sent
    assert names(tmp_path / "backups") == []


@pytest.mark.parametrize("keep", [0, -1, -2])
def test_keeping_none_or_fewer_deletes_nothing(settings, tmp_path, monkeypatch, keep):
    for k in B2:
        monkeypatch.delenv(k, raising=False)
    db, dest = database(settings.data_dir / "state.db"), tmp_path / "backups"
    for stamp in ("20261101-041500", "20261102-041500", "20261103-041500"):
        make_backup(db, dest, keep=keep, stamp=stamp)
    assert len(names(dest)) == 3
    result = CliRunner().invoke(app, ["backup", "--to", str(dest), "--keep", str(keep)])
    assert result.exit_code == 0 and "(4 kept)" in result.output, result.output
    assert len(names(dest)) == 4 and all(n.endswith(".sqlite.gz") for n in names(dest))


def test_the_command_keeps_the_newest_and_says_how_many(settings, tmp_path, monkeypatch):
    for k in B2:
        monkeypatch.delenv(k, raising=False)
    db, dest = database(settings.data_dir / "state.db"), tmp_path / "backups"
    for stamp in ("20261101-041500", "20261102-041500", "20261103-041500"):
        make_backup(db, dest, stamp=stamp)
    result = CliRunner().invoke(app, ["backup", "--to", str(dest), "--keep", "2"])
    assert result.exit_code == 0, result.output
    [newest] = [n for n in names(dest) if n > "landlords-state-20261103-041500.sqlite.gz"]
    assert names(dest) == ["landlords-state-20261103-041500.sqlite.gz", newest]
    assert result.output.startswith(f"Backed up to {dest / newest} (2 kept)\n")


def test_a_new_site_has_nothing_to_back_up(settings, tmp_path):
    result = CliRunner().invoke(app, ["backup", "--to", str(tmp_path / "backups")])
    assert result.exit_code == 0 and "nothing to back up" in result.output
    assert not (tmp_path / "backups").exists() and not (settings.data_dir / "state.db").exists()


# Putting one back, and noticing that backups have stopped (new with the shared commands) -----------------------------


def test_a_backup_is_put_back_and_the_database_it_replaces_is_kept(settings, tmp_path, monkeypatch):
    for k in B2:
        monkeypatch.delenv(k, raising=False)
    db, dest = database(settings.data_dir / "state.db"), tmp_path / "backups"
    assert CliRunner().invoke(app, ["backup", "--to", str(dest)]).exit_code == 0
    [archive] = dest.glob("landlords-state-*.sqlite.gz")
    con = sqlite3.connect(db)
    con.execute("delete from reports")                                  # a mistake made after the backup
    con.commit()
    con.close()
    result = CliRunner().invoke(app, ["restore", str(archive)], input="n\n")
    assert result.exit_code == 1 and f"Replace {db} with {archive}? Stop the site first." in result.output
    assert sqlite3.connect(db).execute("select count(*) from reports").fetchone() == (0,)    # "no": nothing done
    result = CliRunner().invoke(app, ["restore", str(archive), "--yes"])
    assert result.exit_code == 0, result.output
    assert result.output == (f"Restored {db} from {archive}; the database it replaced is kept as "
                             f"{db}.before-restore\n")
    assert sqlite3.connect(db).execute("select count(*) from reports").fetchone() == (50,)
    assert stat.S_IMODE(db.stat().st_mode) == 0o600
    kept = sqlite3.connect(f"{db}.before-restore")
    assert kept.execute("select count(*) from reports").fetchone() == (0,)
    # the kept copy is the only copy of what was replaced: a second restore is refused until it is moved or deleted
    result = CliRunner().invoke(app, ["restore", str(archive), "--yes"])
    assert result.exit_code == 1 and result.output.startswith("Not restored: ") and "move or delete it first" in \
        result.output


def test_only_a_sound_backup_of_this_site_is_put_back(settings, tmp_path):
    db = database(settings.data_dir / "state.db")
    before = db.read_bytes()
    other = tmp_path / "wcs-state-2026-11-01.sqlite.gz"                 # a sister site's: it has neither of our tables
    con = sqlite3.connect(tmp_path / "other.db")
    con.execute("create table usage (id integer primary key)")
    con.execute("create table reports (id integer primary key)")
    con.commit()
    con.close()
    other.write_bytes(gzip.compress((tmp_path / "other.db").read_bytes()))
    broken = tmp_path / "landlords-state-20261101-041500.sqlite.gz"
    broken.write_bytes(b"not a gzip file at all")
    for archive, says in ((other, "is not a backup of this site's state database"), (broken, "could not be read"),
                          (tmp_path / "landlords-state-nothing.sqlite.gz", "could not be read")):
        result = CliRunner().invoke(app, ["restore", str(archive), "--yes"])
        assert result.exit_code == 1 and result.output.startswith("Not restored: ") and says in result.output, archive
    assert db.read_bytes() == before and not db.with_name("state.db.before-restore").exists()


def test_a_backup_made_before_the_shared_package_is_put_back(settings, tmp_path):
    """The database the site's own code made (tests/golden/old-state.sql) has the two tables a restore asks for."""
    from pathlib import Path

    old = tmp_path / "old.db"
    con = sqlite3.connect(old)
    con.executescript((Path(__file__).parent / "golden" / "old-state.sql").read_text())
    con.close()
    archive = make_backup(old, tmp_path / "backups")
    result = CliRunner().invoke(app, ["restore", str(archive), "--yes"])
    assert result.exit_code == 0 and result.output == f"Restored {settings.state_db} from {archive}\n"
    assert sqlite3.connect(settings.state_db).execute("select count(*) from statements").fetchone() == (6,)


def test_backup_check_says_when_backups_or_their_copies_have_stopped(settings, tmp_path, monkeypatch):
    for k in B2:
        monkeypatch.delenv(k, raising=False)
    dest = tmp_path / "backups"
    result = CliRunner().invoke(app, ["backup-check", "--in", str(dest)])
    assert (result.exit_code, result.output) == (1, f"error: there is no backup folder at {dest}\n")
    dest.mkdir()
    result = CliRunner().invoke(app, ["backup-check", "--in", str(dest)])
    assert (result.exit_code, result.output) == (0, "warning: No backups have been made yet.\nwarning: Backups are "
                                                    "kept on this server only: no off-site copy is set up.\n")
    archive = make_backup(database(settings.data_dir / "state.db"), dest)
    for k in B2:
        monkeypatch.setenv(k, "x")                                      # off-site copies set up, and none made yet
    result = CliRunner().invoke(app, ["backup-check", "--in", str(dest)])
    assert (result.exit_code, result.output) == (0, "warning: No off-site copy has been made yet; one is made with "
                                                    "the next backup.\n")
    now = datetime.now(UTC).isoformat(timespec="seconds")
    (dest / "offsite.json").write_text(f'{{"ok": true, "when": "{now}", "file": "{archive.name}"}}')
    result = CliRunner().invoke(app, ["backup-check", "--in", str(dest)])
    assert (result.exit_code, result.output) == (0, "Backups are up to date.\n")
    (dest / "offsite.json").write_text('{"ok": false, "when": "2026-11-01T04:52:03+00:00", "error": "no network"}')
    three_days_ago = datetime.now(UTC).timestamp() - 3 * 86400
    os.utime(archive, (three_days_ago, three_days_ago))
    result = CliRunner().invoke(app, ["backup-check", "--in", str(dest)])
    assert (result.exit_code, result.output) == (1, (
        f"error: The last backup was made over two days ago ({archive.name}).\n"
        "error: The last off-site copy failed (2026-11-01T04:52): no network\n"))


def test_the_servers_timers_run_commands_the_site_has_and_update_sh_installs_them():
    """deploy/*.service: each `landlords …` a unit runs is a command of the site's, with the options it is given; and
    deploy/update.sh copies and enables every unit and timer there is."""
    import re
    from pathlib import Path

    import typer.main

    deploy = Path(__file__).parents[1] / "deploy"
    commands = typer.main.get_command(app).commands
    ran = []
    for unit in sorted(deploy.glob("landlords-*.service")):
        for line in re.findall(r"^ExecStart(?:Post)?=.* app landlords (.+)$", unit.read_text(), re.M):
            name, *args = line.split()
            options = {opt for p in commands[name].params for opt in p.opts}
            assert {a for a in args if a.startswith("--")} <= options, (unit.name, line)
            ran.append(name)
    assert ran == ["backup-check", "backup", "nightly"]      # the weekly update runs through deploy/run-update.sh
    assert "app landlords update" in (deploy / "run-update.sh").read_text() and "update" in commands
    update = (deploy / "update.sh").read_text()
    for unit in (*deploy.glob("landlords-*.service"), *deploy.glob("landlords-*.timer")):
        assert unit.name in update, unit.name
    assert update.count(".timer") == 2 * len(list(deploy.glob("landlords-*.timer"))) + 1   # copied, enabled; one shown
