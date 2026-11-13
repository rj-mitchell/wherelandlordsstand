"""Statements in a landlord's own words, beside what the site says about it: the right of reply (the charity's
impartiality policy, section 7.2; docs/DECISIONS.md, 15). This file is how they are shown on the pages.

A landlord this site covers, or someone acting for it, can send a statement of up to 150 words about a page that names
it: its own page, one part of it (the grade, the bands, the Ombudsman's figures, the safety checks), or a council
area's page that lists it. The form is on the "If you're named" page (``named/``) and posts to ``/api/statements``
(src/landlords/api.py). The Where They Stand sites' shared package keeps it and its rules (wts-core,
``wts_core.replies``; what this site passes to it is in src/landlords/replies.py). Nothing is shown until the owner
has confirmed who sent it and published it (`landlords statements publish`). It is published as written, or declined
with reasons; it is never edited, except to take out something the rules don't allow, with the author's agreement.

Where it is shown: beside the item it is about, and on the landlord's own page, headed "Statement from [name],
[date]" and followed by "In their own words. Not checked or endorsed by Where Landlords Stand." Pages are static, so a
statement is written into them: each landlord's page and each area's page has empty slots, ``<!--statements:KEY-->``
``<!--/statements:KEY-->``, which ``write_into`` fills. The build fills them from the statements published when it
runs, and every owner's command that changes a statement fills them again in the live pages and every kept build
(``refresh``), as the status page writes itself again (src/landlords/status.py). So a published statement is on the
site at once, and stays there in the next build and after an undo.

A statement is never part of the published figures: only this module asks the shared package for the published
statements, and it is given only what a page shows (never the email address, the owner's notes or the log). Search
(names.json), the compare page's data, the downloads, the bands and the checks never see one
(tests/test_statements.py).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path

from wts_core.replies import safe_link

from landlords.config import Settings
from landlords.replies import PARTS, open_replies

log = logging.getLogger(__name__)

SLOT = re.compile(r"<!--statements:(\w+)-->.*?<!--/statements:\1-->", re.S)
SLOT_KEY = re.compile(r"<!--statements:(\w+)-->")


def slot(key: str) -> str:
    """An empty place for statements in a page, filled by ``write_into``."""
    return f"<!--statements:{key}--><!--/statements:{key}-->"


# Showing them --------------------------------------------------------------------------------------------------------


def published(settings: Settings) -> list[dict]:
    """The statements shown now, oldest first, as the shared package gives them to the public: ``id``, ``item`` (the
    page it is about), ``part``, ``about`` (the landlord it speaks for), ``name``, ``role``, ``text``, ``link`` and
    ``date`` (when the words now shown were first shown). Never the email address."""
    if not settings.state_db.exists():
        return []
    return open_replies(settings).published(everywhere=True)


def render(s: dict, w: dict, level: int, about: str = "") -> str:
    """One statement, set apart from the site's own words: in the sans, inside a dashed rule (styles.css,
    ".statement"), marked as a note for screen readers and named by its heading. ``about`` is a link to the page it
    is about, when it is shown away from it (on the landlord's own page)."""
    from landlords.site import esc, fill, fill_html, nice_date

    t = w["statement"]
    sid = f"statement-{s['id']}"
    when = s.get("dated") or nice_date(s["date"])      # "dated": the date already in words (the form's example)
    words = "".join("<p>" + "<br>".join(esc(line) for line in para.split("\n")) + "</p>"
                    for para in s["text"].split("\n\n"))
    out = [f'<div class="statement" role="note" id="{sid}" aria-labelledby="{sid}-h">',
           f'<h{level} id="{sid}-h">{fill(t["heading"], name=s["name"], date=when)}</h{level}>',
           f'<p class="st-role">{esc(s["role"])}</p>']
    if about:
        out.append(f'<p class="st-about">{fill_html(t["about"], page=about)}</p>')
    out.append(f'<blockquote class="st-words">{words}</blockquote>')
    link = safe_link(s.get("link"))          # checked again when shown, as it was when it was sent
    if link:
        out.append(f'<p class="st-link"><a href="{esc(link)}" rel="nofollow">{esc(t["record"])}</a></p>')
    out.append(f'<p class="st-note">{fill(t["endorsed"], site=w["site"]["name"])}</p></div>')
    return "".join(out)


def placements(items: list[dict]) -> dict[tuple[str, str], list[tuple[dict, str]]]:
    """Where each statement goes: ``(page, slot)`` to a list of (statement, the page it is about, if it is shown away
    from it). Beside its item: a part of a landlord's card, or the end of the page's own content. And on the
    landlord's own page, after the card, when the item is on another page."""
    out: dict[tuple[str, str], list] = defaultdict(list)
    for s in items:                     # oldest first, as ``published`` gives them
        out[(s["item"], s["part"] or "page")].append((s, ""))
        home = f"landlords/{s['about']}/" if s.get("about") else s["item"]
        if home != s["item"]:
            out[(home, "page")].append((s, s["item"]))
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
