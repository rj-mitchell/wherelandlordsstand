"""Email to the owner after each weekly update: what changed, and a link to approve the new pages.

Sent with Python's own smtplib, through an SMTP account set in the server's env/landlords.env (never in git):

    LANDLORDS_SMTP_USER=        the account that sends (a Gmail address, say)
    LANDLORDS_SMTP_PASSWORD=    for Gmail, an app password (Google account → Security → App passwords)
    LANDLORDS_SMTP_HOST=        default smtp.gmail.com
    LANDLORDS_SMTP_PORT=        default 465 (SSL)
    LANDLORDS_NOTIFY_TO=        who gets it; default [publish] notify_to in config/settings.toml

Left unset, no email is sent and the update carries on: the report is still in build-info.json.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

from landlords.config import Settings

log = logging.getLogger(__name__)


def configured(settings: Settings) -> dict | None:
    env = os.environ
    cfg = {
        "host": env.get("LANDLORDS_SMTP_HOST", "smtp.gmail.com").strip(),
        "port": int(env.get("LANDLORDS_SMTP_PORT", "465") or 465),
        "user": env.get("LANDLORDS_SMTP_USER", "").strip(),
        "password": env.get("LANDLORDS_SMTP_PASSWORD", "").strip(),
        "to": (env.get("LANDLORDS_NOTIFY_TO") or settings.section("publish").get("notify_to", "")).strip(),
    }
    return cfg if cfg["user"] and cfg["password"] and cfg["to"] else None


def send(settings: Settings, subject: str, body: str) -> str:
    """Send one plain-text email. Returns what happened, for the update's report; never raises."""
    cfg = configured(settings)
    if not cfg:
        return "not sent: email is not set up (LANDLORDS_SMTP_USER, LANDLORDS_SMTP_PASSWORD in env/landlords.env)"
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
    if extra.get("missed"):
        lines += ["Most searched-for names that found nothing this week:"]
        lines += [f"  - {q} ({n})" for q, n in extra["missed"][:5]] + [""]
    lines += ["-- ", "Sent by the weekly update on the server (Where Landlords Stand, docs/OPERATIONS.md)."]
    return subject, "\n".join(lines)
