"""Record what Where Landlords Stand's own code gave before it moved onto wts-core (13 November 2026).

Run on the code as it was (the commit this file was added in, or any before the switch):

    uv run python tests/golden/record.py [folder to write into; default: this one]

It writes the JSON files beside it, which tests/test_parity.py compares with what the site gives now, and
``old-state.sql``, a state database made by the old code with rows of every kind, which the import is tested on.
It needs the modules the switch deleted (``landlords.offsite``, ``landlords.api.State`` and ``Limiter``), so it
does not run on the code as it is now: check out the old commit to record again.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import shared  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from landlords import api, cli, notify, offsite  # noqa: E402
from landlords import statements as st  # noqa: E402
from landlords.config import REPO_ROOT, load_settings  # noqa: E402


class Time:
    """The old code reads the clock itself: this stands in for ``datetime`` in its modules, and for ``time``."""

    def __init__(self) -> None:
        self.at = datetime.fromisoformat(shared.START)
        self.seconds = 1000.0

    def advance(self, seconds: float) -> None:
        self.at += timedelta(seconds=seconds)
        self.seconds += seconds

    def install(self) -> None:
        clock = self

        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock.at

        api.datetime = st.datetime = Frozen
        api.time = types.SimpleNamespace(monotonic=lambda: clock.seconds)


def environment(tmp: Path, **more: str) -> None:
    for key in [k for k in os.environ if k.startswith("LANDLORDS_")]:
        del os.environ[key]
    os.environ.update({"LANDLORDS_DATA_DIR": str(tmp / "data"), **more})


def plain(text: str, tmp: Path) -> str:
    return text.replace(str(tmp), "<tmp>").replace(str(REPO_ROOT), "<root>")


# ---- settings ------------------------------------------------------------------------------------------------------


def settings(tmp: Path) -> list[dict]:
    out = []
    for case in shared.SETTINGS_CASES:
        for key in [k for k in os.environ if k.startswith("LANDLORDS_")]:
            del os.environ[key]
        os.environ.update({k: v.replace("<tmp>", str(tmp)) for k, v in case["env"].items()})
        argument = None
        if case["config"] != "real":
            path = tmp / "sample.toml"
            path.write_text(case["config"].format(data_dir=case["data_dir"].replace("<tmp>", str(tmp))))
            if case.get("as_argument"):
                argument = path
            else:
                os.environ["LANDLORDS_CONFIG"] = str(path)
        s = load_settings(argument)
        out.append({**case, "gives": json.loads(plain(json.dumps({
            "raw": s.raw, "data_dir": str(s.data_dir), "config_path": str(s.config_path), "fetch": s.fetch,
            "raw_dir": str(s.raw_dir), "staging_dir": str(s.staging_dir), "site": s.section("site"),
            "no_such_section": s.section("no_such_section")}), tmp))})
    return out


# ---- the limit on posts -------------------------------------------------------------------------------------------


def limiter() -> dict:
    now = types.SimpleNamespace(t=1000.0)
    api.time = types.SimpleNamespace(monotonic=lambda: now.t)
    limiter = api.Limiter()
    allowed = []
    for t, who in shared.LIMITER_SCRIPT:
        now.t = 1000.0 + t
        allowed.append(limiter.allow(who))
    return {"per_minute": limiter.per_minute, "forget_over": limiter.forget_over, "script": shared.LIMITER_SCRIPT,
            "allowed": allowed, "counted_by": sorted(limiter.seen)}


# ---- backups -------------------------------------------------------------------------------------------------------


def backups(tmp: Path) -> dict:
    def run(args: list[str]) -> tuple[int, str]:
        result = CliRunner().invoke(cli.app, args)
        return result.exit_code, result.output

    def env(data_dir: Path, **more: str) -> None:
        environment(data_dir.parent, **more)

    return shared.backups_scenario(
        tmp, run=run, environment=env,
        make_backup=lambda db, to, keep, stamp: cli.make_backup(db, to, keep=keep, stamp=stamp))


def offsite_copies(tmp: Path) -> list[dict]:
    return shared.offsite_scenario(
        tmp, error=offsite.OffsiteError,
        send=lambda archive, keep, env, client: offsite.send(archive, keep=keep, env=env, client=client),
        check=lambda env, client: offsite.check(env=env, client=client))


# ---- reports and statements: what is sent, and what the owner types ----------------------------------------------


def send(client: TestClient, step: dict) -> dict:
    if "get" in step:
        r = client.get(step["get"], follow_redirects=False)
    elif "json" in step:
        r = client.post(step["post"], json=step["json"], follow_redirects=False)
    elif "data" in step:
        r = client.post(step["post"], data=step["data"], follow_redirects=False)
    else:
        r = client.post(step["post"], content=step["content"].encode("latin-1"),
                        headers={"content-type": "application/json"}, follow_redirects=False)
    is_json = r.headers.get("content-type", "").startswith("application/json")
    return {"case": step["case"], "status": r.status_code, "location": r.headers.get("location"),
            "json": r.json() if is_json else None, "text": None if is_json else r.text}


def kept(state: api.State) -> dict:
    con = sqlite3.connect(state.path)
    reports = [dict(zip(("id", "kind", "page", "message", "email", "closed", "outcome"), r, strict=True))
               for r in con.execute("select id, kind, page, message, email, closed_at is not null, outcome "
                                    "from reports order by id")]
    con.close()
    keep = ("id", "name", "role", "page", "part", "text", "link", "email", "status", "landlord", "reason")
    return {"reports": reports, "statements": [{k: s[k] for k in keep} for s in state.statements()]}


def through_the_api(tmp: Path) -> dict:
    environment(tmp)
    time = Time()
    time.install()
    s = load_settings()
    shared.fixture_site(s.data_dir)
    client = TestClient(api.create_app(s))
    answers, burst = [], False
    for step in shared.API_STEPS:
        if "burst" in step:
            burst = True
            time.advance(61)
            continue
        if not burst:
            time.advance(61)
        answers.append(send(client, step))
    return {"answers": answers, "kept": kept(api.State(s.data_dir / "state.db"))}


def what_the_owner_types(tmp: Path) -> dict:
    environment(tmp)
    time = Time()
    time.install()
    s = load_settings()
    root = shared.fixture_site(s.data_dir)
    client = TestClient(api.create_app(s))
    for step in shared.OWNER_SENT:
        time.advance(61)
        assert send(client, step)["status"] == 200, step
    for name, text in shared.OWNER_FILES.items():
        (tmp / name).write_text(text)
    runs, before = [], shared.pages(root)
    for args in shared.OWNER_COMMANDS:
        time.advance(61)
        result = CliRunner().invoke(cli.app, [a.replace("<tmp>", str(tmp)) for a in args])
        after = shared.pages(root)
        # the pages a command wrote again, as they then stood; none for a command that changed nothing
        runs.append({"args": args, "exit_code": result.exit_code, "output": plain(result.output, tmp),
                     "pages_written": {k: v for k, v in after.items() if v != before[k]}})
        before = after
    state = api.State(s.data_dir / "state.db")
    subject, body = notify.report({"build": "no new pages"}, None, {
        "open_reports": state.open_report_count(), "pending_statements": state.pending_statement_count(),
        "missed": state.top_missed(7, 5)})
    return {"runs": runs, "kept": kept(state), "shown": st.published(s),
            "weekly_email": {"subject": subject, "body": body}}


def a_page_that_has_gone(tmp: Path) -> dict:
    import shutil

    environment(tmp)
    time = Time()
    time.install()
    s = load_settings()
    root = shared.fixture_site(s.data_dir)
    client = TestClient(api.create_app(s))
    for step in shared.GONE_SENT:
        time.advance(61)
        assert send(client, step)["status"] == 200, step
    shutil.rmtree(root / shared.GONE_PAGE)
    runs = []
    for args in shared.GONE_COMMANDS:
        time.advance(61)
        result = CliRunner().invoke(cli.app, args)
        runs.append({"args": args, "exit_code": result.exit_code, "output": plain(result.output, tmp)})
    return {"runs": runs, "kept": kept(api.State(s.data_dir / "state.db")), "pages": shared.pages(root)}


# ---- a state database made by the old code, for the import ---------------------------------------------------------


def old_state(tmp: Path) -> tuple[str, dict]:
    environment(tmp)
    time = Time()
    time.install()
    time.at = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
    s = load_settings()
    shared.fixture_site(s.data_dir)
    path = s.data_dir / "state.db"
    con = sqlite3.connect(path)          # made before reports had a kind, with a row from then
    con.execute("create table reports (id integer primary key, at text not null, page text, message text not null, "
                "email text, closed_at text, outcome text)")
    con.execute("insert into reports (at, page, message, email) values ('2026-06-20T08:00:00+00:00', NULL, "
                "'From before kinds, with no page', NULL)")
    con.commit()
    con.close()
    state = api.State(path)
    exists = lambda slug: True  # noqa: E731
    # a statement withdrawn long ago, whose address has already been deleted
    old = state.add_statement("Old Author", "Director, Example Housing", "landlords/example-housing/", "", "Words "
                              "withdrawn long ago.", "", "old@example.org", "example-housing")
    time.advance(86400)
    st.publish(state, old, "phoned in July", None, exists)
    time.advance(86400)
    st.withdraw(state, old, "withdrawn by the author")
    time.at = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
    assert st.forget_old_emails(state) == 1
    state.add_report("landlords/x/", "Wrong grade", "reader@example.org", "wrong")
    state.add_report("areas/leeds/", "Please remove my name.", "", "takedown")
    state.add_report("", "Loaded words", "c@d.org", "unfair")
    closed = state.add_report("landlords/y/", "A merger you missed", "e@f.org", "wrong")
    blank = state.add_report("landlords/z/", "Closed with nothing said", "", "other")
    time.advance(3600)
    state.close_report(closed, "fixed alias")
    state.close_report(blank, "")
    shown = state.add_statement("Jane Example", "Chief executive, Example Housing", "landlords/example-housing/",
                                "bands", shared.WORDS, "https://example.org/results", "jane@example-housing.org.uk",
                                "example-housing")
    area = state.add_statement("Sam Officer", "Head of housing, Example Council", "areas/leeds/", "",
                               "Our homes in Leeds are\nlisted rightly.\n\nThank you.", "", "sam@example.gov.uk", None)
    waiting = state.add_statement("Pat Waiting", "Officer, Example Council", "areas/leeds/", "", "Still waiting "
                                  "for a decision.", "", "pat@example.gov.uk", None)
    declined = state.add_statement("X  Y", "Z", "landlords/example-council/", "safety", "Never shown at all.", "",
                                   "x@example.org", "example-council")
    recent = state.add_statement("Recent Author", "Director", "landlords/example-council/", "", "Shown for a "
                                 "day only.", "https://example.org/r?a=1&b=2", "recent@example.org", "example-council")
    time.advance(86400)
    st.publish(state, shown, "replied from the landlord's own address", None, exists)
    st.publish(state, area, "phoned the council", "example-council", exists)
    st.decline(state, declined, "it is about a tenant")
    st.publish(state, recent, "letter", None, exists)
    time.advance(2 * 86400)
    st.update(state, shown, "the author's new version", text="Our newer results are published every quarter.")
    st.update(state, waiting, "", role="Housing officer, Example Council")
    st.withdraw(state, recent, "withdrawn by the author")
    for day, query, count in (("2026-11-05", "nobody homes", 3), ("2026-11-06", "example hsg", 1)):
        with state.connect() as db:
            db.execute("insert into missed (day, query, count) values (?, ?, ?)", (day, query, count))
    token = state.add_approval("20261101-000000", 14)
    state.mark(token, "published_at")
    state.add_approval("20261105-000000", 14)
    time.at = datetime.fromisoformat(shared.START)
    st.refresh(s)
    con = sqlite3.connect(path)
    dump = "\n".join(con.iterdump()) + "\n"
    con.close()
    subject, body = notify.report({"build": "no new pages"}, None, {
        "open_reports": state.open_report_count(), "pending_statements": state.pending_statement_count(),
        "missed": []})
    figures = {
        "open_reports": [dict(zip(("id", "at", "kind", "page", "message", "email"), r, strict=True))
                         for r in state.open_reports()],
        "open_report_count": state.open_report_count(),
        "pending_statement_count": state.pending_statement_count(),
        "statements": state.statements(),
        "logs": {str(row["id"]): [list(entry) for entry in state.statement_log(row["id"])]
                 for row in state.statements()},
        "shown": st.published(s),
        "pages": shared.pages(s.data_dir / "site"),
        "weekly_email": body,
        "approval": state.approval(token),
        "forgotten_at_the_next_tidy": st.forget_old_emails(state),
    }
    return dump, figures


def main(out: Path) -> None:
    import logging

    logging.disable(logging.CRITICAL)    # the old command line set logging up afresh on a stream each run closed
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder).resolve()
        for name, record in (("settings", settings), ("backups", backups), ("offsite", offsite_copies),
                             ("api", through_the_api), ("owner", what_the_owner_types),
                             ("gone", a_page_that_has_gone)):
            (tmp / name).mkdir()
            shared.write(out, f"{name}.json", record(tmp / name))
        shared.write(out, "limiter.json", limiter())
        (tmp / "old").mkdir()
        dump, figures = old_state(tmp / "old")
        (out / "old-state.sql").write_text(dump)
        shared.write(out, "old-state.json", json.loads(plain(json.dumps(figures), tmp / "old")))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else shared.GOLDEN)
