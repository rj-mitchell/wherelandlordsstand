"""The backup of the state database (`landlords backup`; src/landlords/cli.py, make_backup): a checked copy, written
whole or not at all, as the sister sites make theirs."""

from __future__ import annotations

import gzip
import sqlite3
import stat

import pytest
from typer.testing import CliRunner

from landlords.cli import app, make_backup

B2 = ("LANDLORDS_B2_BUCKET", "LANDLORDS_B2_KEY_ID", "LANDLORDS_B2_APPLICATION_KEY")


def database(path, damaged: bool = False):
    """A state database with one report in it. ``damaged``: one whose pages SQLite's integrity check finds fault with
    (an index dropped from the list of tables, so its pages belong to nothing), though it still opens and copies."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("create table reports (id integer primary key, message text)")
    con.executemany("insert into reports (message) values (?)", [("a mistake " * 20,)] * 50)
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
