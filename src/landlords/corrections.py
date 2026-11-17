"""The list of what has been put right, on the corrections page ("Mistakes we have fixed"; docs/DECISIONS.md, 7).

It is drawn from two places, newest first:

* ``data_static/corrections.csv``, kept by hand in the repository: the date, the page, what was wrong and what we
  did. A row there reaches the site with the next pages that are built and approved.
* the reports the owner has closed with a public note (`landlords reports close 3 --outcome resolved --public-note
  "…"`), from the Where They Stand sites' shared package (wts-core, ``Replies.corrections``). The package gives the
  date the report was closed, its kind and the owner's note, and nothing a reporter typed: not the message, not
  the page they named, not their email address. So the note itself should say which page was put right.

Pages are static, so, like a statement (src/landlords/statements.py), a public note is written into them at once:
closing a report writes the list again in the live pages and every kept build (``refresh``). Only the list is
written, from its heading to the end of the page's content; the rest of the page stays as it was built.
"""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

from landlords.config import STATIC_DIR, Settings, load_toml

# from the list's heading to the end of the page's content
LOG = re.compile(r'<h2 id="log">.*?(?=</main>)', re.S)
NO_LIMIT = 1_000_000          # the package's list stops at a number; none that could bite here


def by_hand() -> list[dict]:
    """The rows kept by hand, in the order they were added."""
    with open(STATIC_DIR / "corrections.csv", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def from_reports(settings: Settings) -> list[dict]:
    """The public notes on closed reports, newest first: each a ``date``, a ``kind`` and a ``note``. A statement the
    site removed is not listed here: the package gives those only when asked."""
    from landlords.replies import open_replies

    if not settings.state_db.exists():
        return []
    return open_replies(settings).corrections(NO_LIMIT, removed=False)


def rows(entries: list[dict], w: dict) -> list[dict]:
    """Everything the list shows, newest first, in the columns the page has always had."""
    kinds = {value: label for value, label, _ in w["corrections"]["kinds"]}
    noted = [{"date": e["date"], "page": "", "what_was_wrong": kinds.get(e.get("kind") or "", ""),
              "what_we_did": e.get("note") or ""} for e in entries]
    return sorted([*noted, *reversed(by_hand())], key=lambda r: r["date"], reverse=True)


def _when(text: str) -> str:
    """A date as the site writes dates ("14 November 2026") where it was written as 2026-11-14; else as typed."""
    from landlords.site import nice_date

    try:
        return nice_date(date.fromisoformat(text.strip()))
    except ValueError:
        return text


def log_html(entries: list[dict], w: dict) -> str:
    """The list, from its heading: a table, or the words for an empty one."""
    from landlords.site import esc

    t = w["corrections"]
    out = f"<h2 id=\"log\">{esc(t['log_heading'])}</h2>"
    log = rows(entries, w)
    if not log:
        return out + f"<p>{esc(t['log_empty'])}</p>"
    body = "".join(f"<tr><td>{esc(_when(r['date']))}</td><td>{esc(r['page'])}</td><td>{esc(r['what_was_wrong'])}</td>"
                   f"<td>{esc(r['what_we_did'])}</td></tr>" for r in log)
    return out + ('<div class="scroll" tabindex="0" role="region" aria-labelledby="log"><table><thead><tr>'
                  '<th scope="col">Date</th><th scope="col">Page</th>'
                  '<th scope="col">What was wrong</th><th scope="col">What we did</th></tr></thead>'
                  f"<tbody>{body}</tbody></table></div>")


def write_into(folder: Path, entries: list[dict], w: dict | None = None) -> int:
    """Write the list again in a set of pages' corrections page. Returns 1 if the page changed, else 0."""
    path = folder / "corrections" / "index.html"
    if not path.is_file():
        return 0
    text = path.read_text()
    section = log_html(entries, w or load_toml("wording.toml"))
    new = LOG.sub(lambda _: section, text, count=1)
    if new == text:
        return 0
    tmp = path.with_name("index.html.tmp")
    tmp.write_text(new)
    tmp.replace(path)                       # a reader sees the page before or after, never half of it
    return 1


def refresh(settings: Settings) -> dict:
    """Write the list again in every set of pages that can be live, now."""
    from landlords.statements import folders

    entries = from_reports(settings)
    return {"pages_changed": sum(write_into(f, entries) for f in folders(settings))}
