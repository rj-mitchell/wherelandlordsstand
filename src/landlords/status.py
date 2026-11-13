"""The status page, ``status/index.html``: when the pages were made, when each source's newest file was downloaded
and loaded, when the site last looked for new files, and whether new pages are waiting for approval.

The build writes it with the rest of the pages, and keeps what it knew about the sources in ``status.json`` beside
them. Every weekly update, and every publish or undo, then writes it again in the live pages (``refresh``), so it
says when the site last looked for new files even in a week with nothing new. Like every page, it is static HTML,
and every sentence is in config/pages.toml ([status]).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from landlords.config import Settings, load_toml

log = logging.getLogger(__name__)


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def snapshot(settings: Settings) -> dict:
    """What a build knows about its sources: for each, the newest file it read (of the latest period) and when that
    was downloaded and loaded (staging/sources.json and loaded.json, written by the loaders)."""
    files = _read(settings.staging_dir / "sources.json")
    loaded = _read(settings.staging_dir / "loaded.json")
    newest: dict[str, dict] = {}

    def key(f: dict) -> tuple[str, str]:          # the latest period, and of its files the last downloaded
        return f.get("period", ""), f.get("fetched_at", "")

    for f in files.values():
        if f["source"] not in newest or key(f) >= key(newest[f["source"]]):
            newest[f["source"]] = f
    return {"built": datetime.now(UTC).isoformat(timespec="seconds"),
            "sources": {name: {"publisher": f.get("publisher", ""), "title": f.get("title") or f.get("file", ""),
                               "period": f.get("period", ""), "fetched": f.get("fetched_at", ""),
                               "loaded": loaded.get(name, "")} for name, f in newest.items()}}


def checked(settings: Settings) -> dict:
    """When the site last looked for new files, and the sources it couldn't check (staging/fetch-report.json)."""
    report = _read(settings.staging_dir / "fetch-report.json")
    return {"at": report.get("finished", ""), "failed": sorted({f["source"] for f in report.get("failed", [])})}


def waiting(settings: Settings, live: str | None) -> str | None:
    """The newest build waiting for approval: an approval link not yet used or out of date, for pages that passed their
    checks and aren't live. Its build name, or None."""
    import sqlite3
    from contextlib import closing

    db = settings.data_dir / "state.db"
    if not db.exists():
        return None
    now = datetime.now(UTC).isoformat(timespec="seconds")
    try:
        with closing(sqlite3.connect(db, timeout=10)) as con:      # read only: nothing to commit; closed after
            rows = con.execute("select build from approvals where published_at is null and expires > ? "
                               "order by build desc", (now,)).fetchall()
    except sqlite3.Error:
        return None
    for (build,) in rows:
        info = _read(settings.data_dir / "builds" / build / "build-info.json")
        if build != live and info and not info.get("checks_failed"):
            return build
    return None


def _title(text: str) -> str:
    """A file's title as its publisher's page gives it, without the file type and size some add ("( xlsx, 0.39 MB)")."""
    import re

    return re.sub(r"\s*\(\s*(xlsx|xls|ods|csv|pdf|zip)\b[^)]*\)", "", text, flags=re.I).strip()


def _date(iso: str) -> str:
    from landlords.site import nice_date

    return nice_date(iso[:10]) if iso else ""


def page_html(w: dict, snap: dict, check: dict, pending: str | None, known: bool) -> str:
    """The page. ``known`` says whether the site knows about builds waiting for approval (not for pages built by hand
    with `landlords build`)."""
    from landlords.site import esc, fill, page, stack_table

    t = load_toml("pages.toml")["status"]
    names = t["sources"]
    parts = [f"<h1>{esc(t['heading'])}</h1>"] + [f"<p>{esc(x)}</p>" for x in t["intro"]]
    parts.append(f"<h2>{esc(t['now_heading'])}</h2><ul class=\"list\">")
    parts.append(f"<li>{fill(t['built'], date=_date(snap.get('built', '')))}</li>")
    if check["at"]:
        parts.append(f"<li>{fill(t['checked'], date=_date(check['at']))}</li>")
    else:
        parts.append(f"<li>{esc(t['not_checked'])}</li>")
    if check["failed"]:
        failed = ", ".join(names.get(s, s) for s in check["failed"])
        parts.append(f"<li>{fill(t['check_failed'], sources=failed)}</li>")
    if known:
        if pending:
            built = f"{pending[:4]}-{pending[4:6]}-{pending[6:8]}"
            parts.append(f"<li>{fill(t['waiting'], date=_date(built))}</li>")
        else:
            parts.append(f"<li>{esc(t['not_waiting'])}</li>")
    parts.append("</ul>")

    # On a phone each set of files is drawn as a block, each date under its heading (stack_table)
    _, newest, fetched, loaded = (esc(c) for c in t["columns"])
    rows = []
    for name, label in names.items():
        s = snap.get("sources", {}).get(name)
        if not s:
            rows.append(f'<tr role="row"><th scope="row" role="rowheader">{esc(label)}</th>'
                        f'<td role="cell" colspan="3">{esc(t["never"])}</td></tr>')
            continue
        rows.append(f'<tr role="row"><th scope="row" role="rowheader">{esc(label)}<br><span class="hint">{esc(s["publisher"])}</span></th>'
                    f'<td role="cell" class="wide" data-label="{newest}">{esc(_title(s["title"]))} ({esc(s["period"])})</td>'
                    f'<td role="cell" data-label="{fetched}">{esc(_date(s["fetched"]) or t["never"])}</td>'
                    f'<td role="cell" data-label="{loaded}">{esc(_date(s["loaded"]) or t["never"])}</td></tr>')
    parts.append(f"<h2 id=\"files\">{esc(t['sources_heading'])}</h2><p>{esc(t['sources_intro'])}</p>"
                 f'<div class="scroll" tabindex="0" role="region" aria-labelledby="files">'
                 + stack_table(t["columns"], rows, cls="stack stack-2") + "</div>")
    parts += [f'<p class="hint">{esc(x)}</p>' for x in t["notes"]]
    return page(f"{t['heading']} – {w['site']['name']}", "".join(parts), w, depth=1, path="status/")


def write(settings: Settings, out: Path, w: dict) -> None:
    """For the build: the page as the build knows it, and status.json for ``refresh``."""
    snap = snapshot(settings)
    (out / "status.json").write_text(json.dumps(snap, indent=1) + "\n")
    (out / "status").mkdir(exist_ok=True)
    (out / "status" / "index.html").write_text(page_html(w, snap, checked(settings), None, known=False))


def refresh(settings: Settings) -> bool:
    """Write the status page again in the live pages, with what the site knows now. Returns False if there are no
    live pages, or they were built before the status page. Never raises: a status page must never stop an update,
    a publish or an undo."""
    from landlords import publish, site

    try:
        live = publish.current(settings)
        folder = publish.builds_dir(settings) / (live or "-")
        snap = _read(folder / "status.json")
        names = _read(folder / "assets.json")
        if not live or not snap or not names:
            return False
        info = _read(folder / "build-info.json")
        snap["built"] = info.get("finished") or snap.get("built", "")
        site.use_build(settings, names, bool((info.get("site_settings") or {}).get("launched")))
        html = page_html(load_toml("wording.toml"), snap, checked(settings), waiting(settings, live), known=True)
        tmp = folder / "status" / "index.html.tmp"
        tmp.write_text(html)
        tmp.replace(folder / "status" / "index.html")
        return True
    except Exception as exc:  # noqa: BLE001 - see above
        log.warning("status page not refreshed: %s", exc)
        return False
