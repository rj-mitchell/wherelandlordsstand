"""Email to the owner after each weekly update: what changed, and a link to approve the new pages.

On the server, the site doesn't send email itself. It writes each email as a letter to the outbox, ``data/outbox/``
in its data folder: "To:" and "Subject:" lines, a blank line, then the text. The weekly update's systemd unit then
sends whatever is in the outbox with the charity's shared ``mail.sh`` (deploy/send-mail.sh), which keeps the one copy
of the server's mail password, and moves each letter it sent to ``data/outbox/sent/``. If a letter can't be sent,
the unit fails and the server's alert says so (docs/OPERATIONS.md, "The weekly update").

For development only, ``LANDLORDS_MAIL=smtp`` sends with Python's own smtplib instead, through an account of your own:

    LANDLORDS_SMTP_USER=        the account that sends
    LANDLORDS_SMTP_PASSWORD=    its password (for Gmail, an app password)
    LANDLORDS_SMTP_HOST=        default smtp.gmail.com
    LANDLORDS_SMTP_PORT=        default 465 (SSL)

``LANDLORDS_NOTIFY_TO`` changes who gets it, either way; by default [publish] notify_to in config/settings.toml.
"""

from __future__ import annotations

import logging
import os
import secrets
import smtplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

from landlords.config import Settings

log = logging.getLogger(__name__)


def recipient(settings: Settings) -> str:
    return (os.environ.get("LANDLORDS_NOTIFY_TO") or settings.section("publish").get("notify_to", "")).strip()


def outbox_dir(settings: Settings) -> Path:
    return settings.data_dir / "outbox"


def by_smtp() -> bool:
    """Whether to send with smtplib (development only) rather than leave letters for the server's mail.sh."""
    return os.environ.get("LANDLORDS_MAIL", "").strip().lower() == "smtp"


def delivered(result: str) -> bool:
    """Whether ``send``'s result means the email is on its way: sent, or waiting in the outbox for the server."""
    return result.startswith(("sent", "queued"))


def _one_line(text: str) -> str:
    return " ".join(text.split())


def letter(to: str, subject: str, body: str) -> str:
    """A letter as the shared mail.sh reads it: "To:" and "Subject:" lines, a blank line, then the text."""
    return f"To: {_one_line(to)}\nSubject: {_one_line(subject)}\n\n{body.rstrip()}\n"


def queue(settings: Settings, subject: str, body: str, kind: str = "update") -> Path:
    """Write a letter to the outbox and return its path. Each letter has a name of its own: mail.sh skips a letter
    whose name it has sent before. It is written under a temporary name first, so the server never sends half a
    letter, and is readable by its owner only, as approval links publish pages."""
    to = recipient(settings)
    if not to:
        raise ValueError("nobody to send it to: [publish] notify_to in config/settings.toml is empty")
    folder = outbox_dir(settings)
    (folder / "sent").mkdir(parents=True, exist_ok=True)
    name = f"landlords-{datetime.now(UTC):%Y%m%d-%H%M%S}-{kind}-{secrets.token_hex(2)}.txt"
    tmp = folder / f".{name}.part"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(letter(to, subject, body))
    os.replace(tmp, folder / name)
    return folder / name


def send(settings: Settings, subject: str, body: str, kind: str = "update") -> str:
    """Send one plain-text email, or leave it in the outbox for the server to send. Returns what happened, for the
    update's report ("sent …", "queued …" or "not sent: …"); never raises."""
    if by_smtp():
        return _send_smtp(settings, subject, body)
    try:
        path = queue(settings, subject, body, kind)
    except (OSError, ValueError) as exc:
        log.warning("email not queued: %s", exc)
        return f"not sent: couldn't write it to the outbox: {str(exc)[:200]}"
    return f"queued for {recipient(settings)}: outbox/{path.name}, which the server sends (deploy/send-mail.sh)"


def _send_smtp(settings: Settings, subject: str, body: str) -> str:
    env = os.environ
    cfg = {"host": env.get("LANDLORDS_SMTP_HOST", "smtp.gmail.com").strip(),
           "port": int(env.get("LANDLORDS_SMTP_PORT", "465") or 465),
           "user": env.get("LANDLORDS_SMTP_USER", "").strip(),
           "password": env.get("LANDLORDS_SMTP_PASSWORD", "").strip(),
           "to": recipient(settings)}
    if not (cfg["user"] and cfg["password"] and cfg["to"]):
        return "not sent: email by SMTP is not set up (LANDLORDS_SMTP_USER, LANDLORDS_SMTP_PASSWORD)"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Where Landlords Stand <{cfg['user']}>"
    msg["To"] = cfg["to"]
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ssl.create_default_context(), timeout=60) as smtp:
            smtp.login(cfg["user"], cfg["password"])
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        log.warning("email not sent: %s", exc)
        return f"not sent: {exc.__class__.__name__}: {str(exc)[:200]}"
    return f"sent to {cfg['to']}"


def report(info: dict, links: dict | None, extra: dict) -> tuple[str, str]:
    """The weekly email's subject and text, from a build's build-info.json and change report."""
    lines = []
    build = info["build"]
    new = info.get("new_file_titles") or []
    failed = info.get("checks_failed") or []
    if links and links.get("approve"):
        subject = f"Where Landlords Stand: new pages to approve ({build})"
        lines += ["New pages are ready. Nothing changes on the site until you approve them.", "",
                  f"Look at them:  {links['preview']}",
                  f"Approve them:  {links['approve']}",
                  f"(The approve link opens a page with a Publish button. Both links work for "
                  f"{links['days']} days. If you do nothing, the site keeps its current pages.)", ""]
    elif info.get("published"):
        subject = f"Where Landlords Stand: pages updated ({build})"
        lines += [info["published"], ""]
    else:
        subject = "Where Landlords Stand: weekly update"
        lines += ["Nothing new from the publishers this week, so the pages are unchanged.", ""]

    if new:
        lines += ["New files from the publishers:"] + [f"  - {t}" for t in new] + [""]
    lines += ["Checks: " + ("all passed." if not failed else f"{len(failed)} failed:")]
    lines += [f"  - {f}" for f in failed]
    if failed:
        lines += ["  A build with failed checks can't be approved: it needs fixing first."]
    lines.append("")
    changes = extra.get("changes") or {}
    grades = changes.get("grade_changes") or []
    if new and grades:
        lines += [f"Recent grade changes in the regulator's table ({len(grades)}; newest first):"]
        lines += [f"  - {g['name_published']}: {g['standard']} {g['grade']} ({g['change']}, {g['grade_date']})"
                  for g in grades[:5]] + [""]
    movers = changes.get("tp01_rented_movers") or []
    if new and movers:
        lines += ["Biggest changes in overall satisfaction (rented homes):"]
        lines += [f"  - {m['landlord_id']}: {m['change']:+.1f} points" for m in movers[:5]] + [""]
    for label, key in (("New releases to add to config/sources.toml", "unlisted"),
                       ("Still waiting to be published", "waiting")):
        items = info.get(key) or []
        if items:
            lines += [f"{label}:"] + [f"  - {x if isinstance(x, str) else x.get('title') or x.get('document')}"
                                      for x in items] + [""]
    if extra.get("rights_due"):
        lines += ["The rights page has sections due to be checked again (config/rights.toml):"]
        lines += [f"  - {x}" for x in extra["rights_due"]] + [""]
    if extra.get("open_reports"):
        lines += [f"Readers' reports of mistakes waiting: {extra['open_reports']} (landlords reports)", ""]
    if extra.get("pending_statements"):
        lines += [f"Statements from landlords waiting for a decision: {extra['pending_statements']} "
                  "(landlords statements). We reply within 5 working days, and decide within 20 working days.", ""]
    if extra.get("missed"):
        lines += ["Most searched-for names that found nothing this week:"]
        lines += [f"  - {q} ({n})" for q, n in extra["missed"][:5]] + [""]
    lines += ["-- ", "Sent by the weekly update on the server (Where Landlords Stand, docs/OPERATIONS.md)."]
    return subject, "\n".join(lines)
