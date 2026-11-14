"""The site on the shared package (wts-core) gives what its own code gave before.

tests/golden/ holds what the site's code gave on 13 November 2026, before the switch, recorded by
tests/golden/record.py from the scripts in tests/golden/shared.py. Each test here plays the same script to the site
as it is now and compares. Where the two differ on purpose, the difference is asserted, with the entry of wts-core's
docs/AS-BUILT.md (or docs/MIGRATION.md) that lists it: nothing is skipped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "golden"))

import pytest  # noqa: E402
import shared  # noqa: E402

from landlords.config import REPO_ROOT, load_settings  # noqa: E402


def plain(value, tmp: Path):
    """As the recorder wrote it: the scenario's own folder as "<tmp>", the repository as "<root>"."""
    return json.loads(json.dumps(value).replace(str(tmp), "<tmp>").replace(str(REPO_ROOT), "<root>"))


# ---- settings (wts-core docs/MIGRATION.md, 1.1: no difference) -----------------------------------------------------


@pytest.mark.parametrize("case", shared.read("settings.json"), ids=lambda case: case["name"])
def test_settings_resolve_as_before(case, tmp_path):
    tmp = tmp_path.resolve()
    env = {k: v.replace("<tmp>", str(tmp)) for k, v in case["env"].items()}
    argument = None
    if case["config"] != "real":
        path = tmp / "sample.toml"
        path.write_text(case["config"].format(data_dir=case["data_dir"].replace("<tmp>", str(tmp))))
        if case.get("as_argument"):
            argument = path
        else:
            env["LANDLORDS_CONFIG"] = str(path)
    s = load_settings(argument, env)
    assert plain({"raw": s.raw, "data_dir": str(s.data_dir), "config_path": str(s.config_path), "fetch": s.fetch,
                  "raw_dir": str(s.raw_dir), "staging_dir": str(s.staging_dir), "site": s.section("site"),
                  "no_such_section": s.section("no_such_section")}, tmp) == case["gives"]


def test_the_environment_settings_are_read_from_the_real_environment_too(monkeypatch, tmp_path):
    monkeypatch.setenv("LANDLORDS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LANDLORDS_SITE_URL", "https://example.test")
    monkeypatch.setenv("LANDLORDS_LAUNCHED", "yes")
    s = load_settings()
    assert (s.data_dir, s.section("site")["url"], s.section("site")["launched"]) == (
        tmp_path / "data", "https://example.test", True)
    assert s.state_db == tmp_path / "data" / "state.db" and s.site.env_prefix == "LANDLORDS"


def test_a_local_settings_file_in_the_data_folder_is_laid_over_the_repositorys(tmp_path):
    """New with the shared loader (MIGRATION 1.1: "the local layer becomes available; nothing uses it"): the server
    has no such file, so nothing changes there."""
    (tmp_path / "settings.local.toml").write_text('[publish]\nkeep_builds = 9\n')
    s = load_settings(env={"LANDLORDS_DATA_DIR": str(tmp_path)})
    assert s.section("publish")["keep_builds"] == 9 and s.section("publish")["mode"] == "approve"


# ---- the limit on posts (MIGRATION 1.3: no difference; the lock and the forgetting came in phase 1) ---------------


def test_the_limit_on_posts_lets_in_and_refuses_as_before():
    from wts_core.testing import FixedClock
    from wts_core.usage import RateLimiter

    from landlords import api

    golden = shared.read("limiter.json")
    assert (golden["per_minute"], golden["forget_over"]) == (api.PER_MINUTE, api.FORGET_OVER)
    clock = FixedClock()
    limiter = RateLimiter(api.PER_MINUTE, forget_over=api.FORGET_OVER, clock=clock)
    allowed, at = [], 0.0
    for t, who in golden["script"]:
        clock.advance(t - at)
        at = t
        allowed.append(limiter.allow(api.counted_by(who)))
    assert allowed == golden["allowed"]
    # AS-BUILT, usage: "Where Landlords Stand hashes the address before its limiter keeps it. RateLimiter keeps the
    # key it is given, so the site passes ... its own hash, not the address." The same short hash as before.
    counted_by = sorted({api.counted_by(who) for _, who in golden["script"]})
    assert counted_by == golden["counted_by"]
    assert not any(who and who in key for _, who in golden["script"] for key in counted_by)


# ---- backups and their off-site copies (MIGRATION 1.11: the name, what it holds and what is kept, unchanged) -------


def environment(monkeypatch, data_dir: Path, **more: str) -> None:
    import os

    for key in [k for k in os.environ if k.startswith("LANDLORDS_")]:
        monkeypatch.delenv(key)
    monkeypatch.setenv("LANDLORDS_DATA_DIR", str(data_dir))
    for key, value in more.items():
        monkeypatch.setenv(key, value)


def command(args: list[str]) -> tuple[int, str]:
    from typer.testing import CliRunner

    from landlords.cli import app

    result = CliRunner().invoke(app, args)
    return result.exit_code, result.output


def test_backups_are_named_hold_and_keep_what_they_did_and_the_commands_print_the_same_lines(tmp_path, monkeypatch):
    import sqlite3
    from datetime import UTC, datetime

    from wts_core import ops
    from wts_core.testing import FixedClock

    from landlords.state import BACKUPS

    def make_backup(db: Path, to: Path, keep: int, stamp: str) -> Path:
        when = datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=UTC)
        return ops.make_backup(db, to, BACKUPS, keep=keep, clock=FixedClock(when))

    golden = shared.read("backups.json")
    now = shared.backups_scenario(tmp_path.resolve(), make_backup=make_backup, run=command,
                                  environment=lambda data_dir, **more: environment(monkeypatch, data_dir, **more))
    if golden["sqlite"] != sqlite3.sqlite_version:
        # the database inside a backup is SQLite's own copy, which carries the library's version: its bytes are
        # compared only where the library is the one the goldens were recorded with
        for made in (*golden["made"], *now["made"]):
            del made["inside"]["sha256"]
        golden["sqlite"] = now["sqlite"]
    assert now == golden


def test_off_site_copies_are_sent_pruned_and_recorded_as_before(tmp_path):
    from wts_core import ops
    from wts_core.adapters import b2

    from landlords.config import SITE
    from landlords.state import BACKUPS

    now = shared.offsite_scenario(
        tmp_path, error=ops.OffsiteError,
        send=lambda archive, keep, env, client: ops.send_offsite(archive, b2.configured(SITE, env, client=client),
                                                                 BACKUPS, keep=keep),
        check=lambda env, client: ops.check_offsite(b2.configured(SITE, env, client=client), BACKUPS,
                                                    how_to_set_up=b2.how_to_set_up(SITE)))
    assert json.loads(json.dumps(now)) == shared.read("offsite.json")


# ---- reports and statements: what is sent (MIGRATION 1.9; AS-BUILT, replies, "At adoption") --------------------------


def send(client, step: dict) -> dict:
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


def kept(replies) -> dict:
    """What is kept, under the names the site's own tables had (as the recorder wrote it)."""
    reports = [{"id": r["id"], "kind": r["kind"], "page": r["page"], "message": r["message"], "email": r["contact"],
                "closed": int(r["closed_at"] is not None), "outcome": r["resolution"]}
               for r in sorted(replies.reports(open_only=False), key=lambda r: r["id"])]
    statements = [{"id": s["id"], "name": s["name"], "role": s["role"], "page": s["item"], "part": s["part"],
                   "text": s["text"], "link": s["link"], "email": s["email"], "status": s["status"],
                   "landlord": s["about"], "reason": s["reason"]}
                  for s in sorted(replies.statements(), key=lambda s: s["id"])]
    return {"reports": reports, "statements": statements}


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    """A site of our own with its clock in hand: its settings, its pages, the clock and the app."""
    from fastapi.testclient import TestClient
    from wts_core.testing import FixedClock

    from landlords import api

    tmp = tmp_path.resolve()
    environment(monkeypatch, tmp / "data")
    settings = load_settings()
    root = shared.fixture_site(settings.data_dir)
    clock = FixedClock(shared.START)
    # the owner's commands read the clock of the day: for the script, that is the scenario's
    monkeypatch.setattr("landlords.cli.CLOCK", clock)
    return tmp, settings, root, clock, TestClient(api.create_app(settings, clock=clock))


def test_every_answer_to_what_is_sent_is_as_before(scenario):
    from landlords.replies import open_replies

    tmp, settings, _, clock, client = scenario
    golden = shared.read("api.json")
    answers, burst = {}, False
    for step in shared.API_STEPS:
        if "burst" in step:
            burst = True
            clock.advance(61)
            continue
        if not burst:
            clock.advance(61)
        answer = send(client, step)
        answers[answer["case"]] = answer
    before = {answer["case"]: answer for answer in golden["answers"]}
    assert list(answers) == list(before)

    # 1. AS-BUILT, replies, "At adoption": "Order of checks when two things are wrong: the package's order is trap,
    #    daily limit, words, name, role, link, email, address, item shown. ... Where Landlords Stand checked name
    #    and role before the words ... A sender with two faults may be told about a different one first." Here the
    #    link was also checked last, after the page. Each fault alone gets the same words as before.
    told_first = {
        "two faults: no name and no words": ("Please give the name the statement is from.",
                                             "Please write the statement: a sentence or more."),
        "two faults: a bad link and a page not on the site": (
            "We couldn't find that page on the site. Please copy its address from your browser.",
            "The link to the record should be a full web address, starting https://."),
        "two faults: a bad email address and a bad link": (
            "Please give an email address, so we can confirm who the statement is from.",
            "The link to the record should be a full web address, starting https://."),
    }
    for case, (was, now) in told_first.items():
        assert before.pop(case)["json"] == {"ok": False, "error": was}
        assert answers.pop(case) == {"case": case, "status": 400, "location": None, "text": None,
                                     "json": {"ok": False, "error": now}}
    # 2. AS-BUILT, replies, "At adoption": "Where Landlords Stand: an over-long message or contact is refused, not
    #    cut." The form stops at both lengths, so only a post made some other way is told so; the words are new.
    refused_now = {
        "a message longer than its limit": "the report is too long: it can be up to 4,000 characters, and this one "
                                           "is 4,001",
        "an email address longer than its limit": "the email address is too long: it can be up to 200 characters",
    }
    for case, words in refused_now.items():
        assert (before[case]["status"], before.pop(case)["json"]["ok"]) == (200, True)       # cut to fit, and kept
        assert answers.pop(case) == {"case": case, "status": 400, "location": None, "text": None,
                                     "json": {"ok": False, "error": words}}
    # Every other answer, word for word and byte for byte: each refusal, the page that gives a sender's words back,
    # the hidden field, the limit of ten a minute in each route's own words.
    assert answers == before

    now, then = kept(open_replies(settings)), golden["kept"]
    # 2, again: the two reports that were cut to fit are not kept at all
    assert [r["id"] for r in then["reports"]] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert (len(then["reports"][7]["message"]), len(then["reports"][8]["email"])) == (4000, 200)
    del then["reports"][7:]
    # 3. A report with no page is kept with none (NULL), where the site's own table kept an empty text. The owner's
    #    listing prints "" for both (test_the_owners_commands_print_what_they_did). AS-BUILT, replies: "No link is
    #    stored as NULL"; the page is the same change.
    for was, is_now in zip(then["reports"], now["reports"], strict=True):
        if was["page"] == "":
            assert is_now["page"] is None
            is_now["page"] = ""
    assert now["reports"] == then["reports"]
    # 4. AS-BUILT, replies, "At adoption": "Text cleaning now ... tidies inner spaces in names and roles on Where MPs
    #    Stand and Where Landlords Stand."
    assert (then["statements"][5]["name"], then["statements"][5]["role"]) == (
        "Jane   Example", "Chief  executive,  Example Housing")
    assert (now["statements"][5]["name"], now["statements"][5]["role"]) == (
        "Jane Example", "Chief executive, Example Housing")
    then["statements"][5] |= {"name": "Jane Example", "role": "Chief executive, Example Housing"}
    assert now["statements"] == then["statements"]


# ---- reports and statements: what the owner types (AS-BUILT, cli, "At adoption") -----------------------------------

# What can't be done is now said in the shared package's words. AS-BUILT, cli: "Where each site printed one fixed
# line when something could not be done ..., the owner now sees the exact reason. The exit code is 1 as before."
NOT_DONE_NOW = {
    "statements --publish 1": "say how you confirmed who sent it (checked), for the log",
    "statements --publish 2 --checked phoned the council":
        "statement 2 is beside areas/leeds/: say whom it speaks for (about)",
    "statements --update 1": "nothing to change: give new words, a name, a role, a link or whom it speaks for",
    "statements --withdraw 3": "say why it is withdrawn (--reason), for the log",
    "statements --decline 4": "give the reason: the sender is told why",
    # AS-BUILT, cli: "a closed report closed again is refused" (it printed {"closed": false} and exited 0)
    "reports --close 1 --outcome again": "no open report 1",
    "reports --close 9": "no open report 9",
}


def lines(output: str) -> list[dict]:
    return [json.loads(line) for line in output.splitlines()]


def test_the_owners_commands_print_what_they_did(scenario):
    from landlords import notify, statements
    from landlords.replies import open_replies
    from landlords.state import own

    tmp, settings, root, clock, client = scenario
    golden = shared.read("owner.json")
    for step in shared.OWNER_SENT:
        clock.advance(61)
        assert send(client, step)["status"] == 200, step
    for name, text in shared.OWNER_FILES.items():
        (tmp / name).write_text(text)
    before = shared.pages(root)
    for was in golden["runs"]:
        typed = " ".join(was["args"])
        clock.advance(61)
        code, output = command([a.replace("<tmp>", str(tmp)) for a in was["args"]])
        output = output.replace(str(tmp), "<tmp>")
        after = shared.pages(root)
        # the pages each command wrote again, byte for byte (but for the one attribute shared.as_before takes out)
        assert shared.as_before({k: v for k, v in after.items() if v != before[k]}) == was["pages_written"], typed
        before = after
        if typed in NOT_DONE_NOW:
            assert (code, output) == (1, f"Not done: {NOT_DONE_NOW[typed]}\n"), typed
            assert was["output"].startswith(("Not done: ", '{"closed": false}')), typed
        elif typed in ("statements", "statements --all", "reports"):
            # AS-BUILT, cli: "lists are newest first" (they were oldest first; requests to remove a person's details
            # still come before the other reports). The lines themselves are the same.
            assert code == was["exit_code"] == 0
            then = lines(was["output"])
            assert sorted(lines(output), key=lambda row: row["id"]) == sorted(then, key=lambda row: row["id"]), typed
            first = [row for row in lines(output) if row.get("kind") == "takedown"]
            rest = [row for row in lines(output) if row.get("kind") != "takedown"]
            assert lines(output) == first + rest and [r["id"] for r in rest] == sorted((r["id"] for r in rest),
                                                                                      reverse=True), typed
        elif typed.startswith("statements --log"):
            # the words an update replaced are now kept, and shown with it (AS-BUILT, replies: "The old words are
            # kept when a statement is updated, which no site did"); the rest of each line is as before
            now = lines(output)
            assert [{k: v for k, v in entry.items() if k != "previous"} for entry in now] == lines(was["output"]), typed
            assert all(("previous" in entry) == (entry["action"] == "updated") for entry in now), typed
        else:
            assert (code, output) == (was["exit_code"], was["output"]), typed

    replies = open_replies(settings)
    now = kept(replies)
    for report in now["reports"]:      # no page is kept as none, not as an empty text (see the test above, 3)
        report["page"] = report["page"] or ""
    assert now == golden["kept"]
    # what the pages are given: the same statements, in the order the pages place them (by the date of the words
    # shown, then by number), which the site's own code put them in when it placed them
    then = [{"id": s["id"], "item": s["page"], "part": s["part"], "about": s["landlord"], "name": s["name"],
             "role": s["role"], "text": s["text"], "link": s["link"],
             "date": (s["updated_at"] or s["published_at"])[:10]}
            for s in sorted(golden["shown"], key=lambda s: (s["updated_at"] or s["published_at"], s["id"]))]
    assert statements.published(settings) == then
    waiting = replies.waiting()
    subject, body = notify.report({"build": "no new pages"}, None, {
        "open_reports": waiting.reports, "pending_statements": waiting.statements,
        "missed": own(settings).top_missed(7, 5)})
    # the weekly email names the command to type, which is now `landlords reports list`
    assert subject == golden["weekly_email"]["subject"]
    assert body == golden["weekly_email"]["body"].replace("(landlords reports)", "(landlords reports list)")
    assert "(landlords reports)" in golden["weekly_email"]["body"]


def test_a_statement_is_not_published_for_a_landlord_whose_page_has_gone(scenario):
    """The site's own check, kept (landlords.replies.OwnersDesk): the landlord a statement would be published for,
    the one typed or else the one its page named, must still have a page on the site. The old code's line, word for
    word, from both shapes of the command."""
    import shutil

    from landlords.replies import open_replies

    tmp, settings, root, clock, client = scenario
    golden = shared.read("gone.json")
    for step in shared.GONE_SENT:
        clock.advance(61)
        assert send(client, step)["status"] == 200, step
    shutil.rmtree(root / shared.GONE_PAGE)
    gone = "Not done: no landlord's page landlords/example-council/ on the site\n"
    for was in golden["runs"]:
        typed = " ".join(was["args"])
        clock.advance(61)
        code, output = command(was["args"])
        if typed in NOT_DONE_NOW:            # no note of how the sender was confirmed: said first, as it was
            assert (code, output) == (1, f"Not done: {NOT_DONE_NOW[typed]}\n") and was["exit_code"] == 1, typed
        elif typed == "statements":          # both still waiting; the newest first now (AS-BUILT, cli)
            assert code == was["exit_code"] == 0
            assert sorted(lines(output), key=lambda row: row["id"]) == lines(was["output"])
            assert [row["status"] for row in lines(output)] == ["pending", "pending"]
        else:
            assert (code, output) == (was["exit_code"], was["output"]) == (1, gone), typed
    # and the same from the commands in their new shape
    assert command(["statements", "publish", "1", "--checked", "letter"]) == (1, gone)
    assert command(["statements", "publish", "2", "--checked", "letter", "--landlord", "example-council"]) == (1, gone)
    assert command(["statements", "publish", "2", "--checked", "letter", "--about", "example-council"]) == (1, gone)
    assert kept(open_replies(settings)) == golden["kept"]                     # nothing was published
    assert shared.pages(root) == golden["pages"]                              # and no page was written
