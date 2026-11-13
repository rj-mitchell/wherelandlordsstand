"""Command line.

    landlords fetch                     # download new files listed in config/sources.toml into data/raw/
    landlords fetch tsm stock           # some sources only
    landlords load                      # build the tidy tables in data/staging/ from the newest files
    landlords register                  # add new landlords to data_static/landlords.csv, and published names
    landlords match                     # propose landlords for names without a code, for review
    landlords match --accept FILE       # add the proposals marked "yes" in FILE to data_static/aliases.csv
    landlords check                     # the checks: every row matched, ranges, reconciliation, coverage
    landlords score                     # peer groups and bands (config/scoring.toml)
    landlords build                     # the pages, in data/site/
    landlords serve                     # the site and its API at http://127.0.0.1:8000/ (this computer only)
    landlords update                    # weekly: fetch, load, check, score, build into data/builds/; email to approve
    landlords email-test                # a test email, through the outbox like the weekly one
    landlords publish                   # by hand: make the newest build live; `landlords rollback` undoes it
    landlords reports / missed          # readers' reports of mistakes; searches that found nothing
    landlords statements                # statements from landlords waiting; --publish, --decline, --update, --withdraw
    landlords sister-councils           # which councils Where Councils Stand covers, for the links to it
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from landlords.config import load_settings

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(message)s")


@app.command()
def fetch(source: list[str] = typer.Argument(None, help="sources to fetch; all if none"),
          refresh: bool = typer.Option(False, help="fetch files again even if their address was fetched before")) -> None:
    """Download new published files into data/raw/, never overwriting one already there."""
    from landlords import fetch as fetch_

    failed = 0
    for r in fetch_.run(load_settings(), source or None, refresh):
        failed += bool(r.error)
        typer.echo(json.dumps({"source": r.entry.source, "role": r.entry.role, "period": r.entry.period,
                               "found": len(r.found), "new": [n["file"] for n in r.new],
                               "cached": len(r.cached), "error": r.error}
                              | ({"waiting": "not published yet"} if r.waiting else {})))
    raise typer.Exit(1 if failed else 0)


@app.command()
def load(source: list[str] = typer.Argument(None, help="tsm, grades, providers, stock, ombudsman; all if none")) -> None:
    """Read the newest fetched files into tidy tables in data/staging/. Stops if a file's layout has changed."""
    from landlords import load as load_

    for name, counts in load_.run(load_settings(), source or None).items():
        typer.echo(json.dumps({"loaded": name, **counts}))


@app.command()
def register() -> None:
    """Add new landlords to data_static/landlords.csv and the names publishers print to aliases.csv."""
    from landlords import register as reg

    typer.echo(json.dumps(reg.build(load_settings()).__dict__))


@app.command("sister-councils")
def sister_councils() -> None:
    """Update data_static/councils_covered.csv from Where Councils Stand's list of councils: a council's page here,
    and its area's page, link to it there once it is covered. Review the change, then commit it."""
    from landlords import sisters

    typer.echo(json.dumps(sisters.refresh(load_settings())))


@app.command()
def match(accept: Path = typer.Option(None, help="a reviewed file: add the rows marked accept=yes"),
          out: Path = typer.Option(None, help="where to write proposals (default data/staging/match-review.csv)")) -> None:
    """Propose landlords for published names with no code (the Ombudsman's). Nothing is accepted automatically."""
    from landlords import register as reg
    from landlords.load.common import read_table

    s = load_settings()
    if accept:
        typer.echo(json.dumps({"aliases_added": reg.accept(accept)}))
        return
    names = sorted({(r["name_published"], f"Housing Ombudsman {r['period']}")
                    for r in read_table(s, "ombudsman") if not r["landlord_id"]})
    parents: dict[str, list[str]] = {}
    for g in read_table(s, "groups"):
        if g.get("unregistered_parent"):
            parents.setdefault(reg.normalise(g["unregistered_parent"]), []).append(g["landlord_id"])
    proposals = reg.propose(names, unregistered_parents=parents)
    path = out or s.staging_dir / "match-review.csv"
    reg.write_csv(path, proposals, reg.REVIEW_FIELDS)
    typer.echo(json.dumps({"names_without_landlord": len(names), "proposals": len(proposals), "file": str(path)}))


@app.command()
def score() -> None:
    """Place each profiled landlord among similar landlords, by the rules in config/scoring.toml."""
    from landlords import area
    from landlords import score as score_

    s = load_settings()
    area.build(s)
    typer.echo(json.dumps(score_.run(s)))


@app.command()
def build() -> None:
    """Write the pages to data/site/: a profile for each landlord, the list, and the method page."""
    from landlords import area, site
    from landlords import score as score_

    s = load_settings()
    area.build(s)
    score_.run(s)
    typer.echo(json.dumps(site.build(s)))


@app.command()
def serve(port: int = typer.Option(8000), host: str = typer.Option("127.0.0.1", help="local only by default"),
          behind_proxy: bool = typer.Option(False, help="take visitors' addresses from X-Forwarded-For")) -> None:
    """Serve the published pages (data/live, or data/site if nothing is published) and the small API."""
    import uvicorn

    from landlords.api import create_app, site_dir

    s = load_settings()
    typer.echo(f"Serving {site_dir(s)} at http://{host}:{port}/")
    uvicorn.run(create_app(s, behind_proxy), host=host, port=port, access_log=False, log_level="warning")


@app.command()
def update(no_fetch: bool = typer.Option(False, help="use the files already fetched"),
           no_email: bool = typer.Option(False, help="don't send the weekly email")) -> None:
    """The weekly update: fetch, load, check; build new pages if anything is new; then email a link to approve them
    ([publish] in config/settings.toml). Exits 1 if something needs attention, or the approval email wasn't sent."""
    from landlords import publish

    info = publish.update(load_settings(), fetch=not no_fetch, notify=not no_email)
    typer.echo(json.dumps({k: info.get(k) for k in ("build", "needs_attention", "checks_failed", "published",
                                                     "approval", "email")}
                          | {"new_files": len(info.get("new_files", []))}))
    raise typer.Exit(1 if info["needs_attention"] else 0)


@app.command()
def email_test() -> None:
    """A test email, by the same way as the weekly update's: on the server it waits in the outbox until
    deploy/send-mail.sh sends it (docs/DEPLOY.md). Exits 1 if it couldn't be written or sent."""
    from landlords import notify

    result = notify.send(load_settings(), "Where Landlords Stand: test email",
                         "This is a test. The weekly update will send its report and approval link like this.",
                         kind="test")
    typer.echo(result)
    raise typer.Exit(0 if notify.delivered(result) else 1)


@app.command()
def publish(build: str = typer.Argument(None, help="a build in data/builds/; the newest if none"),
            force: bool = typer.Option(False, help="publish even though its checks failed")) -> None:
    """Make a build the live site, by hand, after reading its change report."""
    from landlords import publish as publish_

    typer.echo(json.dumps(publish_.publish(load_settings(), build, force)))


@app.command()
def rollback() -> None:
    """Put back the build that was live before the last publish."""
    from landlords import publish

    typer.echo(json.dumps(publish.rollback(load_settings())))


@app.command()
def reports(close: int = typer.Option(None, help="close this report (its email address is deleted)"),
            outcome: str = typer.Option("", help="what was done, when closing")) -> None:
    """Readers' reports of mistakes that are still open."""
    from landlords.api import State

    state = State(load_settings().data_dir / "state.db")
    if close is not None:
        typer.echo(json.dumps({"closed": state.close_report(close, outcome)}))
        return
    for r in state.open_reports():
        typer.echo(json.dumps(dict(zip(("id", "at", "kind", "page", "message", "email"), r, strict=True))))


@app.command()
def statements(publish: int = typer.Option(None, help="show this statement on the site, once you know who sent it"),
               checked: str = typer.Option("", help="with --publish: how you confirmed who sent it, for the log"),
               landlord: str = typer.Option("", help="with --publish: the landlord it speaks for (its slug), for a "
                                                     "statement about an area's page"),
               decline: int = typer.Option(None, help="decline this pending statement (give --reason)"),
               update: int = typer.Option(None, help="replace this statement's words (--text-file), name, role or link "
                                                     "with the author's new version"),
               text_file: Path = typer.Option(None, help="with --update: a file holding the new words"),
               name: str = typer.Option(None, help="with --update: the new name"),
               role: str = typer.Option(None, help="with --update: the new role"),
               link: str = typer.Option(None, help="with --update: the new link to the record (\"\" for none)"),
               withdraw: int = typer.Option(None, help="take this statement down (give --reason)"),
               reason: str = typer.Option("", help="why it was declined or taken down (the sender is told), or what "
                                                   "an update took out"),
               show_all: bool = typer.Option(False, "--all", help="list every statement, not only those waiting"),
               log: int = typer.Option(None, help="what was done to this statement, and why")) -> None:
    """Statements from landlords in their own words (the right of reply; src/landlords/statements.py). With no options,
    those waiting for a decision. Publishing, declining, updating or withdrawing one writes the live pages again at
    once, and deletes the email addresses of statements withdrawn or declined three months ago."""
    from landlords import statements as st
    from landlords.api import State, site_dir

    s = load_settings()
    state = State(s.data_dir / "state.db")
    st.forget_old_emails(state)
    if log is not None:
        for at, action, note in state.statement_log(log):
            typer.echo(json.dumps({"at": at, "action": action, "note": note}))
        return
    try:
        if publish is not None:
            exists = lambda slug: (site_dir(s) / "landlords" / slug / "index.html").is_file()  # noqa: E731
            done = st.publish(state, publish, checked, landlord or None, exists)
        elif decline is not None:
            done = st.decline(state, decline, reason)
        elif update is not None:
            text = text_file.read_text(encoding="utf-8") if text_file else None
            done = st.update(state, update, reason, text=text, name=name, role=role, link=link)
        elif withdraw is not None:
            done = st.withdraw(state, withdraw, reason)
        else:
            for row in state.statements(None if show_all else "pending"):
                typer.echo(json.dumps(row | {"words": st.word_count(row["text"])}))
            return
    except st.StatementError as exc:
        typer.echo(f"Not done: {exc}")
        raise typer.Exit(1) from exc
    typer.echo(json.dumps({k: done[k] for k in ("id", "status", "name", "page", "part", "landlord", "email")}
                          | st.refresh(s)))


def make_backup(state_db: Path, to: Path, keep: int = 14, stamp: str | None = None) -> Path:
    """A checked copy of the state database, compressed into ``to`` as ``landlords-state-YYYYMMDD-HHMMSS.sqlite.gz``
    and readable by its owner only (readers' reports and statements can hold email addresses). Then all but the newest
    ``keep`` of this site's copies there are deleted; none when ``keep`` is zero or less.

    Made as the sister sites make theirs (Where Councils Stand, councils/backup.py): the copy and the archive are
    written in a temporary folder inside ``to``, and the archive is moved to its name only once the copy has passed
    SQLite's integrity check. So a backup that fails, or is stopped half way, leaves no file that could be taken for a
    good one. Raises RuntimeError if the copy fails the check."""
    import gzip
    import shutil
    import sqlite3
    import tempfile
    from datetime import UTC, datetime

    from landlords.offsite import PREFIX

    to.mkdir(parents=True, exist_ok=True)
    out = to / f"{PREFIX}{stamp or datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.sqlite.gz"
    with tempfile.TemporaryDirectory(dir=to) as tmp:      # its owner only, as the copy inside it must be
        copy = Path(tmp) / "state.db"
        src, dst = sqlite3.connect(state_db), sqlite3.connect(copy)
        try:
            src.backup(dst)  # a consistent copy, even while the site is writing
            ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            dst.close()
            src.close()
        if ok != "ok":
            raise RuntimeError(f"the backup copy failed its integrity check: {ok}")
        partial = Path(tmp) / out.name
        with open(copy, "rb") as fi, gzip.open(partial, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        partial.chmod(0o600)
        partial.replace(out)  # there whole, or not at all
    for old in sorted(to.glob(f"{PREFIX}*.sqlite.gz"))[:-keep] if keep > 0 else []:
        old.unlink()
    return out


@app.command()
def backup(to: Path = typer.Option(..., help="folder for the copies"), keep: int = typer.Option(14)) -> None:
    """Copy the state database (readers' reports, statements, missed searches): the one thing that can't be rebuilt."""
    import sqlite3

    from landlords.offsite import PREFIX, OffsiteError, send

    src = load_settings().data_dir / "state.db"
    if not src.exists():
        typer.echo("No state database yet: nothing to back up.")
        return
    try:
        out = make_backup(src, to, keep)
    except (RuntimeError, sqlite3.Error) as exc:      # the copy can't be trusted: nothing is kept or sent off-site
        typer.echo(f"Backup failed: {exc}")
        raise typer.Exit(1) from exc
    typer.echo(f"Backed up to {out} ({len(list(to.glob(f'{PREFIX}*.sqlite.gz')))} kept)")
    try:
        status = send(out)
    except OffsiteError as exc:
        typer.echo(f"Off-site copy failed: {exc}")
        raise typer.Exit(1) from exc
    typer.echo(f"Off-site copy: {status.get('offsite') or 'stored in ' + status['bucket']}")


@app.command()
def offsite() -> None:
    """Check the off-site backup bucket: whether the key works, and how many of this site's backups are there."""
    from landlords.offsite import check

    typer.echo(json.dumps(check(), indent=2))


@app.command()
def missed(days: int = typer.Option(28)) -> None:
    """Searches that found nothing, most frequent first: names to consider adding as aliases."""
    from landlords.api import State

    for q, n in State(load_settings().data_dir / "state.db").top_missed(days):
        typer.echo(f"{n}\t{q}")


@app.command()
def check(strict: bool = typer.Option(True, help="exit 1 if any check fails")) -> None:
    """Every row matched to a landlord, ranges, reconciliation to published figures, coverage, and movers."""
    from landlords import checks

    report = checks.run(load_settings())
    for c in report["checks"]:
        typer.echo(f"{'ok  ' if c['ok'] else 'FAIL'} {c['name']}: {c['detail']}")
    typer.echo(f"Report: {report['file']}")
    raise typer.Exit(1 if strict and not all(c["ok"] for c in report["checks"]) else 0)
