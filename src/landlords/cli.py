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
    landlords reports list / missed     # readers' reports of mistakes; searches that found nothing
    landlords reports close 3 --outcome resolved --note "fixed alias"
    landlords statements list           # statements from landlords waiting; then publish, decline, update, withdraw,
                                        # remove, show or log, each with the statement's number
    landlords waiting                   # how many reports and statements are waiting, and for how long
    landlords backup --to FOLDER        # copy the state database; `restore` puts a copy back; `backup-check`; `offsite`
    landlords nightly                   # the nightly housekeeping: email addresses deleted when their time is up
    landlords sister-councils           # which councils Where Councils Stand covers, for the links to it

The commands for reports, statements and backups are the Where They Stand sites' shared ones (wts-core,
``wts_core.cli``), under this site's names and printing this site's lines. `landlords statements --publish 3` and
`landlords reports --close 3 --outcome "..."`, the shape these had before, still work for now.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import typer
from wts_core import cli as shared
from wts_core.ops import AlertWording
from wts_core.ports import SYSTEM_CLOCK
from wts_core.replies import REPORT_OUTCOMES, NotDone, Refused, Replies, word_count

from landlords.config import SITE, load_settings
from landlords.state import BACKUPS, BACKUPS_KEPT_DAYS

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


# ---- Readers' reports and statements from landlords (src/landlords/replies.py) -------------------------------------
# The shared package's commands, under this site's names, printing this site's lines: one JSON object a line.


CLOCK = SYSTEM_CLOCK        # the time the owner's commands record; a test stands another in its place


def _replies() -> Replies:
    """Reports and statements for the owner's commands: the shared package's desk, behind this site's own check that
    a statement's landlord still has a page before it is published (landlords.replies.OwnersDesk)."""
    from landlords.replies import OwnersDesk, open_replies

    settings = load_settings()
    return OwnersDesk(open_replies(settings, clock=CLOCK), settings)


def _report_line(r: Mapping[str, Any]) -> list[str]:
    row = {"id": r["id"], "at": r["at"], "kind": r["kind"], "page": r["page"] or "", "message": r["message"],
           "email": r["contact"]}
    if r["closed_at"]:        # only `reports list --all` and `reports show` meet a closed one
        row |= {"closed_at": r["closed_at"], "outcome": r["status"], "note": r["resolution"],
                "public_note": r["public_note"]}
    return [json.dumps(row)]


def _statement_row(s: Mapping[str, Any]) -> dict[str, Any]:
    """A statement under this site's own names for its fields: the page it is about, the landlord it speaks for, and
    how its sender was confirmed (the note of its publishing, which is kept in its log)."""
    checked = next((e["note"] for e in s["log"] if e["action"] == "published" and e["note"]), None)
    return {"id": s["id"], "at": s["at"], "name": s["name"], "role": s["role"], "page": s["item"], "part": s["part"],
            "text": s["text"], "link": s["link"], "email": s["email"], "status": s["status"], "landlord": s["about"],
            "checked": checked, "reason": s["reason"], "published_at": s["published_at"],
            "updated_at": s["updated_at"], "closed_at": s["closed_at"]}


def _statement_line(s: Mapping[str, Any]) -> list[str]:
    return [json.dumps(_statement_row(s) | {"words": s["words"]})]


def _done_line(s: Mapping[str, Any]) -> str:
    row = _statement_row(s)
    return json.dumps({k: row[k] for k in ("id", "status", "name", "page", "part", "landlord", "email")}
                      | {"pages_changed": s["pages_changed"], "shown": s["shown"]})


def _log_line(e: Mapping[str, Any]) -> list[str]:
    return [json.dumps({"at": e["at"], "action": e["action"], "note": e["note"]}
                       | ({"previous": e["previous"]} if e.get("previous") else {}))]


def _written_again(statement: Mapping[str, Any]) -> dict:
    """After each change to a statement: the published ones written again into the live pages and every kept build,
    so the change is on the site at once."""
    from landlords import statements

    return statements.refresh(load_settings())


def _landlord(slug: str) -> str:
    from landlords.replies import landlord

    return landlord(load_settings(), slug)


REPLIES_WORDING = shared.RepliesWording(
    report=_report_line, statement=_statement_line, log_entry=_log_line,
    published=_done_line, declined=_done_line, updated=_done_line, withdrawn=_done_line, removed=_done_line,
    closed=lambda r: json.dumps({"closed": True}),
    waiting=lambda w: json.dumps(dict(w)),
    # this site hides nothing yet (no `hide` command: see _commands), but the package asks for every line
    hidden_item=lambda h: [json.dumps(dict(h))], hid=lambda h: json.dumps({"hidden": h["item"]}),
    unhid=lambda h: json.dumps({"shown": h["item"]}),
    not_done="Not done: {message}", refused="Not done: {message}", errors_to_stderr=False)

_NO_COMMAND = dict.fromkeys(
    ("reports_list", "reports_show", "reports_close", "statements_list", "statements_show", "statements_publish",
     "statements_decline", "statements_update", "statements_withdraw", "statements_remove", "statements_log", "hide",
     "unhide", "hidden", "waiting"))
_HELP = {
    "reports_list": "Readers' reports that are still open, requests to remove a person's details first.",
    "reports_close": "Close a report. The reporter's email address is deleted.",
    "reports_close.note": "what was found and done (kept privately)",
    "reports_close.public_note": "a note that may be made public. It is kept, but this site's list of fixes "
                                 "(\"Mistakes we have fixed\") is still data_static/corrections.csv: add a row there too",
    "statements_list": "Statements waiting for a decision, with the address to confirm who sent each.",
    "statements_publish": "Show a waiting statement on the site, as written, once you know who sent it. It goes on "
                          "the live pages at once.",
    "statements_publish.checked": "how you confirmed who sent it, for the log. The note is kept for good, so leave "
                                  "the sender's email address out of it: that address is deleted three months after "
                                  "a statement is withdrawn, declined or removed",
    "statements_publish.about": "the landlord it speaks for (its slug), for a statement about an area's page",
    "statements_withdraw": "Take a statement down, or stop one waiting, because its author asked. Say so with "
                           "--reason, for the log.",
    "statements_remove": "Take a published statement down because it breaks the rules (give --reason).",
}


def _commands(**names: str) -> shared.RepliesCommands:
    """The shared package's commands that go in one place, each under the name given; the rest are left out there.
    `hide`, `unhide` and `hidden` are left out everywhere: the pages are built ahead of time and none of them can
    yet show a note in an item's place, so the commands would hide nothing."""
    return shared.RepliesCommands(listed=("pending",), about_option="--landlord", withdraw_note_required=True,
                                  help=_HELP, **{**_NO_COMMAND, **names})


def _add(to: typer.Typer, **names: str) -> None:
    to.add_typer(shared.replies_commands(_replies, _commands(**names), REPLIES_WORDING, about=_landlord,
                                         changed=_written_again))


reports_app = typer.Typer(help="Readers' reports of mistakes: list, show and close them. With no command, those still "
                               "open.")
statements_app = typer.Typer(help="Statements from landlords in their own words (the right of reply): list, show, "
                                  "publish, decline, update, withdraw and remove them, and read a statement's log. "
                                  "With no command, those waiting for a decision.")
_add(reports_app, reports_list="list", reports_show="show", reports_close="close")
_add(statements_app, statements_list="list", statements_show="show", statements_publish="publish",
     statements_decline="decline", statements_update="update", statements_withdraw="withdraw",
     statements_remove="remove", statements_log="log")
_add(app, waiting="waiting")
app.add_typer(reports_app, name="reports")
app.add_typer(statements_app, name="statements")

# The shape these two commands had before the shared package: one command, with an option for each action
# (`landlords statements --publish 3 --checked "..."`, `landlords reports --close 2 --outcome "fixed alias"`). It
# still works for now, so that nothing the owner types from habit, or has written down, fails. The commands above
# (`landlords statements publish 3 --checked "..."`) are the way from here on, and the only one the docs give.
_OLD = "The old way of typing `landlords {new}`, kept for now"


def _not_done(exc: Exception) -> typer.Exit:
    typer.echo(f"Not done: {exc}")
    return typer.Exit(1)


@reports_app.callback(invoke_without_command=True)
def reports(ctx: typer.Context,
            close: int = typer.Option(None, help=_OLD.format(new="reports close N --outcome resolved --note \"...\"")),
            outcome: str = typer.Option("", help="with --close: what was done (kept privately as the note)")) -> None:
    if ctx.invoked_subcommand is not None:
        return
    desk = _replies()
    if close is None:
        for row in desk.reports():
            typer.echo(_report_line(row)[0])
        return
    said = outcome.strip()
    try:        # the old --outcome was free text: it is kept as the private note, and the report recorded as resolved
        if said.lower() in REPORT_OUTCOMES:
            desk.close(close, outcome=said.lower())
        else:
            desk.close(close, outcome="resolved", note=said)
    except NotDone as exc:
        raise _not_done(exc) from exc
    typer.echo(json.dumps({"closed": True}))


@statements_app.callback(invoke_without_command=True)
def statements(ctx: typer.Context,
               publish: int = typer.Option(None, help=_OLD.format(new="statements publish N --checked \"...\"")),
               checked: str = typer.Option("", help="with --publish: how you confirmed who sent it, for the log. Leave "
                                                    "the sender's email address out of it"),
               landlord: str = typer.Option("", help="with --publish: the landlord it speaks for (its slug), for a "
                                                     "statement about an area's page"),
               decline: int = typer.Option(None, help=_OLD.format(new="statements decline N --reason \"...\"")),
               update: int = typer.Option(None, help=_OLD.format(new="statements update N --text-file FILE")),
               text_file: Path = typer.Option(None, help="with --update: a file holding the new words"),
               name: str = typer.Option(None, help="with --update: the new name"),
               role: str = typer.Option(None, help="with --update: the new role"),
               link: str = typer.Option(None, help="with --update: the new link to the record (\"\" for none)"),
               withdraw: int = typer.Option(None, help=_OLD.format(new="statements withdraw N --reason \"...\"")),
               reason: str = typer.Option("", help="with --decline, --withdraw or --update: why"),
               show_all: bool = typer.Option(False, "--all", help=_OLD.format(new="statements list --all")),
               log: int = typer.Option(None, help=_OLD.format(new="statements log N"))) -> None:
    if ctx.invoked_subcommand is not None:
        return
    desk = _replies()

    def whole(row: Mapping[str, Any]) -> dict[str, Any]:
        return {**row, "words": word_count(row["text"]), "log": desk.log(row["id"])}

    if log is not None:
        for entry in desk.log(log):
            typer.echo(_log_line(entry)[0])
        return
    try:
        if publish is not None:
            try:
                about = _landlord(landlord) if landlord.strip() else None
            except ValueError as exc:
                raise NotDone(str(exc)) from exc
            desk.publish(publish, checked=checked, about=about)
            sid = publish
        elif decline is not None:
            desk.decline(decline, reason)
            sid = decline
        elif update is not None:
            text = text_file.read_text(encoding="utf-8") if text_file else None
            desk.update(update, text=text, name=name, role=role, link=link, note=reason)
            sid = update
        elif withdraw is not None:
            if not reason.strip():
                raise NotDone("say why it is withdrawn (--reason), for the log")
            desk.withdraw(withdraw, reason)
            sid = withdraw
        else:
            for row in desk.statements(None if show_all else "pending"):
                typer.echo(_statement_line(whole(row))[0])
            return
    except (NotDone, Refused) as exc:
        raise _not_done(exc) from exc
    done = whole(desk.statement(sid))
    typer.echo(_done_line(done | _written_again(done)))


@app.command()
def nightly() -> None:
    """The nightly housekeeping, run after the backup (deploy/landlords-backup.service): email addresses deleted
    when their time is up, and the copy of the database made before it moved onto the shared package deleted once
    it is older than the backups are kept. It changes no page: a statement that lapses was never shown."""
    from landlords.state import open_state

    settings = load_settings()
    if not settings.state_db.exists():
        typer.echo("No state database yet: nothing to tidy.")
        return
    db = open_state(settings)
    desk = _replies()
    lapsed, contacts = desk.lapse_undecided()
    out = {"emails_deleted": desk.forget_old_emails(), "statements_lapsed": lapsed, "report_emails_deleted": contacts,
           "old_copies_deleted": [p.name for p in db.forget_old_copies(BACKUPS_KEPT_DAYS)]}
    desk.forget_old_counts()
    typer.echo(json.dumps(out))


# ---- Backups of the state database (src/landlords/state.py, BACKUPS) ---------------------------------------------
# The shared package's commands, printing this site's lines.

_BACKUP_ALERTS = AlertWording(
    no_backups="No backups have been made yet.",
    backup_stale="The last backup was made over two days ago ({name}).",
    server_only="Backups are kept on this server only: no off-site copy is set up.",
    no_offsite_yet="No off-site copy has been made yet; one is made with the next backup.",
    offsite_failed="The last off-site copy failed ({when}): {error}",
    offsite_stale="The last off-site copy was over two days ago ({day}).")

OPS_WORDING = shared.OpsWording(
    backup=shared.BackupWords(
        folder=None, keep=BACKUPS.keep, nothing_to_back_up="No state database yet: nothing to back up.",
        backed_up="Backed up to {archive} ({kept} kept)", failed="Backup failed: {error}",
        offsite_stored="Off-site copy: stored in {bucket}", offsite_not_set_up="Off-site copy: not set up",
        offsite_failed="Off-site copy failed: {error}",
        help="Copy the state database (readers' reports, statements, missed searches): the one thing that can't be "
             "rebuilt.",
        to_help="folder for the copies"),
    restore=shared.RestoreWords(
        archive_must_exist=False, says_aborted=False,
        confirm="Replace {state_db} with {archive}? Stop the site first.",
        restored="Restored {state_db} from {archive}", replaced="; the database it replaced is kept as {kept}",
        not_restored="Not restored: {error}",
        help="Put a backup of the state database back. Stop the site first. The copy is checked before anything is "
             "replaced, and the database it replaces is kept beside it.",
        archive_help="a backup: /backups/landlords-state-YYYYMMDD-HHMMSS.sqlite.gz", yes_help="don't ask first"),
    backup_check=shared.BackupCheckWords(
        folder="/backups", no_folder="error: there is no backup folder at {folder}", alert="{level}: {text}",
        up_to_date="Backups are up to date.", alerts=_BACKUP_ALERTS,
        help="Say whether the nightly backup and its off-site copy have stopped. Exits 1 if the last backup or copy "
             "is over two days old, or the last copy failed.",
        folder_help="the folder the backups are written to"),
    errors_to_stderr=False,
    offsite_help="Check the off-site backup bucket: whether the key works, and how many of this site's backups are "
                 "there.")

app.add_typer(shared.ops_commands(SITE, load_settings, BACKUPS, OPS_WORDING))    # backup, restore, backup-check, offsite


@app.command()
def missed(days: int = typer.Option(28)) -> None:
    """Searches that found nothing, most frequent first: names to consider adding as aliases."""
    from landlords.state import own

    for q, n in own(load_settings()).top_missed(days):
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
