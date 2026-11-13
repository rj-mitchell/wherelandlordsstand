"""Statements in a landlord's own words, beside what the site says about it: the right of reply (the charity's
impartiality policy, section 7.2; docs/DECISIONS.md, 15).

A landlord this site covers, or someone acting for it, can send a statement of up to 150 words about a page that names
it: its own page, one part of it (the grade, the bands, the Ombudsman's figures, the safety checks), or a council
area's page that lists it. The form is on the "If you're named" page (``named/``) and posts to ``/api/statements``
(src/landlords/api.py), which keeps it in the state database as pending. Nothing is shown until the owner has
confirmed who sent it and published it (`landlords statements --publish`). It is published as written, or declined
with reasons; it is never edited, except to take out something the rules don't allow, with the author's agreement.

Where it is shown: beside the item it is about, and on the landlord's own page, headed "Statement from [name],
[date]" and followed by "In their own words. Not checked or endorsed by Where Landlords Stand." Pages are static, so a
statement is written into them: each landlord's page and each area's page has empty slots, ``<!--statements:KEY-->``
``<!--/statements:KEY-->``, which ``write_into`` fills. The build fills them from the statements published when it
runs, and every owner's command that changes a statement fills them again in the live pages and every kept build
(``refresh``), as the status page writes itself again (src/landlords/status.py). So a published statement is on the
site at once, and stays there in the next build and after an undo.

A statement is never part of the published figures: only this module and the API read the statements table. Search
(names.json), the compare page's data, the downloads, the bands and the checks never see it (tests/test_statements.py).

The email address given is used only to confirm who sent it, and to let them update or withdraw it. It is kept while
the statement is pending or shown, and deleted three months after it is withdrawn or declined (the privacy page), by
``forget_old_emails``, which runs with every owner's command and every weekly update.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from landlords.config import Settings

log = logging.getLogger(__name__)

MAX_WORDS = 150
EMAIL_KEPT_MONTHS = 3                     # after a statement is withdrawn or declined (the privacy page)
LIMITS = {"name": 120, "role": 200, "page": 300, "part": 20, "text": 2000, "link": 300, "email": 200}
SITE_HOSTS = ("wherelandlordsstand.com", "www.wherelandlordsstand.com")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# The pages a statement can sit beside: a landlord's page, and a council area's page (which lists landlords)
PAGE = re.compile(r"^(landlords|areas)/([a-z0-9][a-z0-9-]*)/?(?:index\.html)?$")
# The parts of a landlord's "Before you bid" card a statement can sit beside, by the id of each part's heading. A
# statement about anything else on the page (its names, a merger, the figures, the areas) sits after the card.
PARTS = ("grade", "bands", "ombudsman", "safety")
STATUSES = ("pending", "published", "declined", "withdrawn")
SLOT = re.compile(r"<!--statements:(\w+)-->.*?<!--/statements:\1-->", re.S)
SLOT_KEY = re.compile(r"<!--statements:(\w+)-->")


class StatementError(ValueError):
    """A statement that can't be accepted as sent; the message says why, in words for the person who sent it."""


def slot(key: str) -> str:
    """An empty place for statements in a page, filled by ``write_into``."""
    return f"<!--statements:{key}--><!--/statements:{key}-->"


# Checking what was sent -----------------------------------------------------------------------------------------------


def word_count(text: str) -> int:
    return len(text.split())


def clean_text(text: str) -> str:
    """Line endings made plain and runs of blank lines closed up; the words themselves are never changed."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def not_too_long(what: str, value: str, field: str) -> None:
    """Refuse what is longer than its limit, with words for the sender. Nothing sent is ever cut to fit: a statement
    is published as written or declined, never edited (the policy, 7.2)."""
    if len(value) > LIMITS[field]:
        raise StatementError(f"{what} can be up to {LIMITS[field]:,} characters. This one is {len(value):,}.")


def clean_link(link: str) -> str:
    link = (link or "").strip()
    if not link:
        return ""
    not_too_long("The link to the record", link, "link")
    parsed = urlparse(link)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or re.search(r"[\s\"'<>]", link):
        raise StatementError("The link to the record should be a full web address, starting https://.")
    return link


def item(address: str, part: str = "") -> tuple[str, str, str | None]:
    """The page a statement is about, from what someone pasted (a full address, or a path), as ``(page, part,
    landlord)``: "landlords/abri-group/", "grade", "abri-group". A part of a landlord's page comes from ``part``, or
    from the address's #fragment; the landlord is known from its own page's address, and for an area's page is set by
    the owner when publishing."""
    address = (address or "").strip()
    if "://" not in address:            # "wherelandlordsstand.com/landlords/…", or a path
        host = address.split("/")[0]
        address = "https://" + (address if host in SITE_HOSTS else "wherelandlordsstand.com/" + address.lstrip("/"))
    parsed = urlparse(address)
    found = PAGE.match(parsed.path.lstrip("/")) if parsed.hostname in SITE_HOSTS else None
    if not found:
        raise StatementError("Please give the address of a page on wherelandlordsstand.com that names your landlord: "
                             "its own page (with /landlords/ in it), or a council area's page (with /areas/ in it).")
    kind, slug = found.groups()
    part = (part or parsed.fragment or "").strip().lower()
    part = part if kind == "landlords" and part in PARTS else ""
    return f"{kind}/{slug}/", part, slug if kind == "landlords" else None


def check(name: str, role: str, text: str, email: str | None) -> None:
    """The rules a statement must meet to be kept. ``email`` is None when the owner updates one already kept."""
    if len(name.strip()) < 2:
        raise StatementError("Please give the name the statement is from.")
    not_too_long("Your name", name.strip(), "name")
    if len(role.strip()) < 2:
        raise StatementError("Please give your role and the landlord you speak for, for example \"Chief executive, "
                             "Example Housing\".")
    not_too_long("Your role", role.strip(), "role")
    words = word_count(text)
    if words < 3:
        raise StatementError("Please write the statement: a sentence or more.")
    if words > MAX_WORDS:
        raise StatementError(f"A statement can be up to {MAX_WORDS} words. This one is {words}.")
    not_too_long("A statement", text, "text")
    if email is not None and (not EMAIL.match(email.strip()) or len(email.strip()) > LIMITS["email"]):
        raise StatementError("Please give an email address, so we can confirm who the statement is from.")


def submit(state, data: dict, page_exists: Callable[[str], bool]) -> int:
    """Keep a statement sent through the form as pending. ``data`` is the form's fields; ``page_exists`` says whether
    a page is on the live site. Raises StatementError if it can't be accepted: a name, role, statement, link or
    email address longer than its limit (LIMITS) is refused, never cut to fit and kept."""
    f = {k: str(data.get(k, "") or "").strip() for k in LIMITS}
    text = clean_text(f["text"])
    check(f["name"], f["role"], text, f["email"])
    # The page's address and the part are only read, to find the page (``item``): what is kept is ours, not theirs
    page, part, landlord = item(f["page"][:LIMITS["page"]], f["part"][:LIMITS["part"]])
    if not page_exists(page):
        raise StatementError("We couldn't find that page on the site. Please copy its address from your browser.")
    sid = state.add_statement(f["name"], f["role"], page, part, text, clean_link(f["link"]), f["email"], landlord)
    forget_old_emails(state)
    return sid


# The owner's decisions (`landlords statements`) -----------------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _get(state, sid: int, *allowed: str) -> dict:
    s = state.statement(sid)
    if not s:
        raise StatementError(f"no statement {sid}")
    if allowed and s["status"] not in allowed:
        raise StatementError(f"statement {sid} is {s['status']}, not {' or '.join(allowed)}")
    return s


def publish(state, sid: int, checked: str, landlord: str | None, landlord_exists: Callable[[str], bool]) -> dict:
    """Show a pending statement, once the owner has confirmed who sent it (``checked`` says how). A statement about an
    area's page needs ``landlord``, the slug of the landlord it speaks for, whose own page shows it too."""
    s = _get(state, sid, "pending")
    if not checked.strip():
        raise StatementError("say how you confirmed who sent it (--checked), for the log")
    landlord = (landlord or s["landlord"] or "").strip()
    if not landlord:
        raise StatementError(f"statement {sid} is about {s['page']}: say which landlord it speaks for (--landlord)")
    if not landlord_exists(landlord):
        raise StatementError(f"no landlord's page landlords/{landlord}/ on the site")
    state.change_statement(sid, "published", checked, status="published", landlord=landlord, checked=checked,
                           published_at=_now())
    return state.statement(sid)


def decline(state, sid: int, reason: str) -> dict:
    """Decline a pending statement, with the reasons the sender is told (the policy: never edited, published as written
    or declined with reasons)."""
    _get(state, sid, "pending")
    if not reason.strip():
        raise StatementError("give the reasons (--reason): the sender is told why")
    state.change_statement(sid, "declined", reason, status="declined", reason=reason, closed_at=_now())
    return state.statement(sid)


def update(state, sid: int, note: str, text: str | None = None, name: str | None = None, role: str | None = None,
           link: str | None = None) -> dict:
    """The author's new version of a published or pending statement, as they sent it (or with something the rules
    don't allow taken out, with their agreement: ``note`` says which)."""
    s = _get(state, sid, "pending", "published")
    new = {k: v for k, v in (("text", clean_text(text) if text is not None else None), ("name", name), ("role", role))
           if v is not None}
    if link is not None:
        new["link"] = clean_link(link) or None
    if not new:
        raise StatementError("nothing to change: give --text-file, --name, --role or --link")
    merged = {**s, **new}
    check(merged["name"], merged["role"], merged["text"], None)
    state.change_statement(sid, "updated", note, **new, updated_at=_now() if s["status"] == "published" else None)
    return state.statement(sid)


def withdraw(state, sid: int, reason: str) -> dict:
    """Take a statement down: the author withdrew it, or it broke the rules (``reason`` says which; the policy: the
    charity says why)."""
    _get(state, sid, "pending", "published")
    if not reason.strip():
        raise StatementError("say why (--reason): \"withdrawn by the author\", or the rule it broke")
    state.change_statement(sid, "withdrawn", reason, status="withdrawn", reason=reason, closed_at=_now())
    return state.statement(sid)


def months_ago(now: datetime, months: int) -> datetime:
    """The same moment ``months`` calendar months earlier (the month's last day when that day is missing)."""
    import calendar

    y, m = divmod(now.year * 12 + now.month - 1 - months, 12)
    return now.replace(year=y, month=m + 1, day=min(now.day, calendar.monthrange(y, m + 1)[1]))


def forget_old_emails(state, now: datetime | None = None) -> int:
    """Delete the email address of every statement withdrawn or declined more than three months ago."""
    cutoff = months_ago(now or datetime.now(UTC), EMAIL_KEPT_MONTHS)
    return state.forget_statement_emails(cutoff.isoformat(timespec="seconds"))


# Showing them --------------------------------------------------------------------------------------------------------


def published(settings: Settings) -> list[dict]:
    """The statements shown now. Only what a page shows is kept: never the email address."""
    from landlords.api import State

    if not (settings.data_dir / "state.db").exists():
        return []
    keep = ("id", "name", "role", "page", "part", "text", "link", "landlord", "published_at", "updated_at")
    return [{k: s[k] for k in keep} for s in State(settings.data_dir / "state.db").statements("published")]


def render(s: dict, w: dict, level: int, about: str = "") -> str:
    """One statement, set apart from the site's own words: in the sans, inside a dashed rule (styles.css,
    ".statement"), marked as a note for screen readers and named by its heading. ``about`` is a link to the page it
    is about, when it is shown away from it (on the landlord's own page)."""
    from landlords.site import esc, fill, fill_html, nice_date

    t = w["statement"]
    sid = f"statement-{s['id']}"
    when = s.get("date") or nice_date((s.get("updated_at") or s["published_at"])[:10])
    words = "".join("<p>" + "<br>".join(esc(line) for line in para.split("\n")) + "</p>"
                    for para in s["text"].split("\n\n"))
    out = [f'<div class="statement" role="note" id="{sid}" aria-labelledby="{sid}-h">',
           f'<h{level} id="{sid}-h">{fill(t["heading"], name=s["name"], date=when)}</h{level}>',
           f'<p class="st-role">{esc(s["role"])}</p>']
    if about:
        out.append(f'<p class="st-about">{fill_html(t["about"], page=about)}</p>')
    out.append(f'<blockquote class="st-words">{words}</blockquote>')
    if s.get("link"):
        out.append(f'<p class="st-link"><a href="{esc(s["link"])}" rel="nofollow">{esc(t["record"])}</a></p>')
    out.append(f'<p class="st-note">{fill(t["endorsed"], site=w["site"]["name"])}</p></div>')
    return "".join(out)


def placements(items: list[dict]) -> dict[tuple[str, str], list[tuple[dict, str]]]:
    """Where each statement goes: ``(page, slot)`` to a list of (statement, the page it is about, if it is shown away
    from it). Beside its item: a part of a landlord's card, or the end of the page's own content. And on the
    landlord's own page, after the card, when the item is on another page."""
    out: dict[tuple[str, str], list] = defaultdict(list)
    for s in sorted(items, key=lambda s: (s.get("updated_at") or s.get("published_at") or "", s["id"])):
        out[(s["page"], s["part"] or "page")].append((s, ""))
        home = f"landlords/{s['landlord']}/" if s.get("landlord") else s["page"]
        if home != s["page"]:
            out[(home, "page")].append((s, s["page"]))
    return out


def _h1(folder: Path, page: str) -> str:
    try:
        found = re.search(r"<h1[^>]*>(.*?)</h1>", (folder / page / "index.html").read_text())
        return found[1] if found else page
    except OSError:
        return page


def write_into(folder: Path, items: list[dict], w: dict | None = None) -> int:
    """Fill every statement slot in a set of pages (a build, the live pages, or data/site) with the statements that go
    there, and empty the others. Only landlords' and areas' pages have slots. Returns how many pages changed."""
    from landlords.config import load_toml
    from landlords.site import esc, fill

    w = w or load_toml("wording.toml")
    where = placements(items)
    changed = 0
    for path in [*sorted(folder.glob("landlords/*/index.html")), *sorted(folder.glob("areas/*/index.html"))]:
        page = path.parent.relative_to(folder).as_posix() + "/"
        text = path.read_text()

        keys = set(SLOT_KEY.findall(text))

        def fill_slot(m: re.Match, page: str = page, keys: set = keys) -> str:
            key = m[1]
            level = 4 if key in PARTS else 2
            shown = []
            here = where.get((page, key), [])
            if key == "page":               # a part this page doesn't have (no safety checks, say): after the card
                here = [x for k in PARTS if k not in keys for x in where.get((page, k), [])] + here
            for s, about in here:
                link = ""
                if about:
                    link = (f'<a href="../../{esc(about)}index.html">'
                            f'{fill(w["statement"]["about_page"], page="@@")}</a>').replace("@@", _h1(folder, about))
                shown.append(render(s, w, level, link))
            return f"<!--statements:{key}-->{''.join(shown)}<!--/statements:{key}-->"

        new = SLOT.sub(fill_slot, text)
        if new != text:
            tmp = path.with_name("index.html.tmp")
            tmp.write_text(new)
            tmp.replace(path)               # a reader sees the page before or after, never half of it
            changed += 1
    return changed


def folders(settings: Settings) -> list[Path]:
    """Every set of pages that can be live: the kept builds (the live one, the one before it, and any waiting for
    approval, so approving or undoing never brings back an old statement or drops a new one) and data/site."""
    from landlords import publish

    builds = sorted(p for p in publish.builds_dir(settings).glob("*") if (p / "build-info.json").exists())
    return [*builds, *([settings.data_dir / "site"] if (settings.data_dir / "site" / "index.html").exists() else [])]


def refresh(settings: Settings) -> dict:
    """Write the published statements into every set of pages that can be live, now (see the top of this file)."""
    items = published(settings)
    return {"pages_changed": sum(write_into(f, items) for f in folders(settings)), "shown": len(items)}
