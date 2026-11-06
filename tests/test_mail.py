"""The weekly email goes through the server's shared mail.sh: the site leaves a letter in its outbox
(src/landlords/notify.py), and deploy/send-mail.sh, run by deploy/run-update.sh after the update, sends it."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from landlords import notify

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
needs_bash = pytest.mark.skipif(not (shutil.which("bash") and shutil.which("flock")), reason="needs bash and flock")


def test_a_letter_is_left_in_the_outbox_as_mail_sh_reads_it(settings):
    result = notify.send(settings, "Where Landlords Stand: new pages to approve (b1)", "Approve them:  https://x/T\n")
    assert result.startswith("queued for wheretheystanduk@gmail.com") and notify.delivered(result)
    [path] = (settings.data_dir / "outbox").glob("*.txt")
    assert path.name.startswith("landlords-") and "-update-" in path.name
    assert path.read_text() == ("To: wheretheystanduk@gmail.com\nSubject: Where Landlords Stand: new pages to approve "
                                "(b1)\n\nApprove them:  https://x/T\n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600                # approval links publish pages
    assert (settings.data_dir / "outbox" / "sent").is_dir()
    assert not list((settings.data_dir / "outbox").glob(".*"))      # no half-written letter left behind


def test_each_letter_has_a_name_of_its_own_and_one_line_headers(settings, monkeypatch):
    monkeypatch.setenv("LANDLORDS_NOTIFY_TO", "owner@example.org")
    a = notify.queue(settings, "two\nlines", "text")
    b = notify.queue(settings, "two\nlines", "text")
    assert a != b                                                    # mail.sh skips a name it has sent before
    assert a.read_text().startswith("To: owner@example.org\nSubject: two lines\n\n")


def test_an_outbox_that_cant_be_written_is_not_sent(settings):
    settings.data_dir.mkdir(parents=True)
    (settings.data_dir / "outbox").write_text("not a folder")
    result = notify.send(settings, "s", "b")
    assert result.startswith("not sent") and not notify.delivered(result)


def test_email_test_goes_through_the_outbox(settings):
    from landlords.cli import app

    out = CliRunner().invoke(app, ["email-test"])
    assert out.exit_code == 0 and "queued" in out.output
    [path] = (settings.data_dir / "outbox").glob("*-test-*.txt")
    assert "Subject: Where Landlords Stand: test email" in path.read_text()


# The scripts on the server, with a stand-in for mail.sh and docker ---------------------------------------------------

FAKE_MAIL = """#!/usr/bin/env bash
# a stand-in for the shared mail.sh: checks the letter as mail.sh does, notes it, and fails letters that say FAIL
[[ "$1" == send ]] || exit 2
f="$2"
head_end=$(grep -n -m1 '^$' "$f" | cut -d: -f1)
to=$(head -n "${head_end:-0}" "$f" | sed -n 's/^To: *//p')
subject=$(head -n "${head_end:-0}" "$f" | sed -n 's/^Subject: *//p')
[[ -n "$head_end" && -n "$to" && -n "$subject" ]] || { echo "bad letter $f"; exit 1; }
grep -q FAIL "$f" && exit 1
echo "$(basename "$f") $to $subject" >> "$MAIL_LOG"
"""

FAKE_DOCKER = """#!/usr/bin/env bash
# a stand-in for docker: notes the command, and the update exits with UPDATE_RC
echo "$*" >> "$DOCKER_LOG"
exit "${UPDATE_RC:-0}"
"""


@pytest.fixture
def server(tmp_path, settings):
    for name, text in (("mail.sh", FAKE_MAIL), ("docker", FAKE_DOCKER)):
        (tmp_path / name).write_text(text)
        (tmp_path / name).chmod(0o755)
    env = {**os.environ, "MAIL_SH": str(tmp_path / "mail.sh"), "DOCKER": str(tmp_path / "docker"),
           "OUTBOX": str(settings.data_dir / "outbox"), "MAIL_LOG": str(tmp_path / "mail.log"),
           "DOCKER_LOG": str(tmp_path / "docker.log"), "LOCK": str(tmp_path / "update.lock"),
           "DIR": str(DEPLOY.parent)}

    def run(script: str, **extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(DEPLOY / script)], env={**env, **extra}, capture_output=True, text=True,
                              timeout=60)

    return settings, tmp_path, run


@needs_bash
def test_the_server_scripts_parse():
    for script in sorted(DEPLOY.glob("*.sh")):
        assert subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0, script


@needs_bash
def test_send_mail_sends_each_letter_and_moves_it_to_sent(server):
    settings, tmp, run = server
    assert run("send-mail.sh").returncode == 0                      # nothing waiting, no outbox yet: nothing to do
    good = notify.queue(settings, "Where Landlords Stand: weekly update", "All well.")
    test = notify.queue(settings, "Where Landlords Stand: test email", "A test.", kind="test")
    done = run("send-mail.sh")
    assert done.returncode == 0, done.stdout + done.stderr
    assert not list((settings.data_dir / "outbox").glob("*.txt"))
    assert {p.name for p in (settings.data_dir / "outbox" / "sent").glob("*.txt")} == {good.name, test.name}
    log = (tmp / "mail.log").read_text()
    assert f"{good.name} wheretheystanduk@gmail.com Where Landlords Stand: weekly update" in log


@needs_bash
def test_a_letter_that_cant_be_sent_stays_and_the_run_fails(server):
    settings, _, run = server
    bad = notify.queue(settings, "s", "FAIL")
    good = notify.queue(settings, "s", "fine")
    done = run("send-mail.sh")
    assert done.returncode == 1 and "not sent" in done.stdout
    assert bad.exists() and not good.exists()                         # the one sent is not sent again
    assert run("send-mail.sh", MAIL_SH="/nowhere/mail.sh").returncode == 1


@needs_bash
@pytest.mark.parametrize(("update_rc", "letter", "expected"), [
    ("0", "fine", 0),
    ("1", "fine", 1),        # the update needs attention: its email still goes, and the unit fails
    ("0", "FAIL", 1),        # the email couldn't be sent: the unit fails, so the alert goes
])
def test_run_update_sends_the_email_after_the_update(server, update_rc, letter, expected):
    settings, tmp, run = server
    notify.queue(settings, "s", letter)
    done = run("run-update.sh", UPDATE_RC=update_rc)
    assert done.returncode == expected, done.stdout + done.stderr
    assert (tmp / "docker.log").read_text() == "compose run --rm -T app landlords update\n"
    assert (tmp / "mail.log").exists() == (letter == "fine")
