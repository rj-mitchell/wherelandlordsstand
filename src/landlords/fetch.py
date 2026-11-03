"""Download the published files listed in config/sources.toml.

Every file is kept in ``raw/<source>/<sha256>.<ext>`` with a JSON note beside it (``<sha256>.note.json``) saying where it came from: the file's
URL, the page that linked to it, the period it covers, its title on that page, and when it was fetched. A file is
never overwritten: a changed file has a new hash and is stored beside the old one. Each fetch is also appended to
``raw/<source>/index.jsonl``, which the loaders read to find the newest file for each source, role and period.

Being a good citizen (docs/DECISIONS.md): one request at a time, at least ``min_interval_seconds`` apart, with a user
agent that names the project. A published asset whose URL has already been fetched is not fetched again, because
GOV.UK and the Ombudsman publish a changed file at a new address. Pages are fetched again to find new files.

Where files are found:

* ``govuk``: a GOV.UK page, through the Content API (``https://www.gov.uk/api/content/<path>``). Its attachments are
  picked by title (``match``, a regular expression) and file type (``types``).
* ``html``: any other web page. Links are picked by their address (``links``, a regular expression).
* ``urls``: addresses given in full.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from landlords.config import Settings, load_toml

log = logging.getLogger(__name__)

GOVUK_API = "https://www.gov.uk/api/content"


@dataclass(frozen=True)
class Entry:
    """One line of config/sources.toml: where to find one kind of file for one period."""

    source: str                 # folder under raw/: tsm, judgements, providers, stock, ombudsman ...
    role: str                   # what the file is: "full-data", "report", "list" ...
    period: str                 # the period it covers, as the publisher writes it: "2024/25", "2025-26", "current"
    publisher: str
    licence: str
    govuk: str = ""             # GOV.UK path
    page: str = ""              # any other page
    urls: tuple[str, ...] = ()
    match: str = ""             # regular expression on attachment titles (govuk)
    links: str = ""             # regular expression on link addresses (html)
    types: tuple[str, ...] = () # file extensions to keep
    keep_page: bool = False     # keep the page itself as a raw file (when the data is in the page)
    optional: bool = False      # a release not published yet: a missing page is expected, not a failure
    notes: str = ""


def entries(path: str = "sources.toml") -> list[Entry]:
    out = []
    for raw in load_toml(path).get("file", []):
        raw = dict(raw)
        for key in ("urls", "types"):
            if key in raw:
                raw[key] = tuple(raw[key])
        out.append(Entry(**raw))
    return out


@dataclass
class Found:
    url: str
    title: str
    page: str
    page_updated_at: str = ""


@dataclass
class Result:
    entry: Entry
    found: list[Found] = field(default_factory=list)
    new: list[dict] = field(default_factory=list)       # notes of files not seen before
    cached: list[str] = field(default_factory=list)     # URLs already fetched
    error: str = ""
    waiting: bool = False       # an optional page that isn't published yet


class NotFound(RuntimeError):
    """The page or file doesn't exist (HTTP 404 or 410). Not retried."""


class Client:
    """One request at a time, spaced out, with retries for transient failures."""

    def __init__(self, settings: Settings):
        cfg = settings.fetch
        self.interval = float(cfg.get("min_interval_seconds", 1.0))
        self.retries = int(cfg.get("retries", 3))
        self._last = 0.0
        self.http = httpx.Client(
            headers={"User-Agent": cfg.get("user_agent", "WhereLandlordsStand")},
            timeout=float(cfg.get("timeout_seconds", 60)),
            follow_redirects=True,
        )

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(self, url: str) -> httpx.Response:
        error: Exception | None = None
        for attempt in range(self.retries):
            wait = self.interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                self._last = time.monotonic()
                resp = self.http.get(url)
                if resp.status_code in (404, 410):
                    raise NotFound(f"{url}: {resp.status_code}")
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(f"{resp.status_code}", request=resp.request, response=resp)
                resp.raise_for_status()
                return resp
            except httpx.HTTPError as exc:
                error = exc
                log.warning("%s: %s (attempt %d)", url, exc, attempt + 1)
                time.sleep(self.interval * 2 ** (attempt + 1))
        raise RuntimeError(f"{url}: {error}")


# Finding files -------------------------------------------------------------------------------------------------


def _ext(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower().lstrip(".")
    return suffix or "bin"


def find_govuk(content: dict[str, Any], entry: Entry) -> list[Found]:
    page = "https://www.gov.uk" + entry.govuk
    updated = content.get("public_updated_at", "")
    pattern = re.compile(entry.match, re.I) if entry.match else None
    out = []
    for att in content.get("details", {}).get("attachments", []):
        url, title = att.get("url", ""), (att.get("title") or "").strip()
        if not url.startswith("http"):
            continue  # an HTML attachment: a page on GOV.UK, not a file
        if pattern and not pattern.search(title):
            continue
        if entry.types and _ext(url) not in entry.types:
            continue
        out.append(Found(url=url, title=title, page=page, page_updated_at=updated))
    return out


_HREF = re.compile(r"""<a\b[^>]*\bhref\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""", re.I | re.S)


def find_links(html: str, entry: Entry) -> list[Found]:
    pattern = re.compile(entry.links, re.I)
    seen, out = set(), []
    for href, text in _HREF.findall(html):
        url = urljoin(entry.page, href.replace("&amp;", "&"))
        if url in seen or not pattern.search(url):
            continue
        if entry.types and _ext(url) not in entry.types:
            continue
        seen.add(url)
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()
        out.append(Found(url=url, title=title, page=entry.page))
    return out


# The raw store -------------------------------------------------------------------------------------------------


def index_path(settings: Settings, source: str) -> Path:
    return settings.raw_dir / source / "index.jsonl"


def read_index(settings: Settings, source: str) -> list[dict]:
    path = index_path(settings, source)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def store(settings: Settings, entry: Entry, found: Found, body: bytes, content_type: str,
          last_modified: str = "", ext: str | None = None) -> tuple[dict, bool]:
    """Keep a downloaded file and its note. Returns the note and whether the file is new."""
    sha = hashlib.sha256(body).hexdigest()
    folder = settings.raw_dir / entry.source
    folder.mkdir(parents=True, exist_ok=True)
    ext = ext or _ext(found.url)
    path = folder / f"{sha}.{ext}"
    note = {
        "sha256": sha,
        "file": path.name,
        "source": entry.source,
        "role": entry.role,
        "period": entry.period,
        "title": found.title,
        "url": found.url,
        "page": found.page,
        "page_updated_at": found.page_updated_at,
        "publisher": entry.publisher,
        "licence": entry.licence,
        "bytes": len(body),
        "content_type": content_type,
        "last_modified": last_modified,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    is_new = not path.exists()
    if is_new:
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(body)
        tmp.rename(path)
        (folder / f"{sha}.note.json").write_text(json.dumps(note, indent=2) + "\n")
    with index_path(settings, entry.source).open("a") as fh:
        fh.write(json.dumps({**note, "new": is_new}) + "\n")
    return note, is_new


def latest(settings: Settings, source: str, role: str | None = None, period: str | None = None,
           ext: str | None = None) -> dict | None:
    """The note of the most recently fetched file for a source, role and period, with its path."""
    rows = [r for r in read_index(settings, source)
            if (role is None or r["role"] == role) and (period is None or r["period"] == period)
            and (ext is None or r["file"].endswith("." + ext))]
    if not rows:
        return None
    row = rows[-1]  # the index is append-only, so the last line is the newest
    return {**row, "path": str(settings.raw_dir / source / row["file"])}


# Running ---------------------------------------------------------------------------------------------------------


def run_entry(settings: Settings, client: Client, entry: Entry, refresh: bool = False) -> Result:
    res = Result(entry)
    try:
        return _run_entry(settings, client, entry, res, refresh)
    except NotFound as exc:
        if entry.optional:
            res.waiting = True
        else:
            res.error = str(exc)
        return res


def _run_entry(settings: Settings, client: Client, entry: Entry, res: Result, refresh: bool) -> Result:
    try:
        if entry.govuk:
            resp = client.get(GOVUK_API + entry.govuk)
            content = resp.json()
            if entry.keep_page:
                page = Found(url=GOVUK_API + entry.govuk, title=content.get("title", ""),
                             page="https://www.gov.uk" + entry.govuk,
                             page_updated_at=content.get("public_updated_at", ""))
                note, new = store(settings, entry, page, resp.content, "application/json", ext="json")
                if new:
                    res.new.append(note)
            res.found = find_govuk(content, entry)
        elif entry.page:
            resp = client.get(entry.page)
            if entry.keep_page:
                note, new = store(settings, entry, Found(entry.page, "", entry.page), resp.content,
                                  resp.headers.get("content-type", ""), ext="html")
                if new:
                    res.new.append(note)
            res.found = find_links(resp.text, entry)
        res.found += [Found(url=u, title="", page=entry.page or u) for u in entry.urls]
        if not res.found and not entry.keep_page:
            res.error = "no files found on the page: has its layout or the file's title changed?"
            return res
        known = {r["url"] for r in read_index(settings, entry.source)}
        for f in res.found:
            if f.url in known and not refresh:
                res.cached.append(f.url)
                continue
            resp = client.get(f.url)
            note, new = store(settings, entry, f, resp.content, resp.headers.get("content-type", ""),
                              resp.headers.get("last-modified", ""))
            if new:
                res.new.append(note)
    except NotFound:
        raise
    except Exception as exc:  # noqa: BLE001 - one failed source must not stop the others
        res.error = str(exc)
        log.warning("%s %s: %s", entry.source, entry.period, exc)
    return res


def unlisted(client: Client) -> list[dict]:
    """Documents in the GOV.UK collections watched in sources.toml that no ``[[file]]`` line covers: new releases
    (a new TSM year, say) to add to sources.toml."""
    cfg = load_toml("sources.toml")
    known = {e.govuk for e in entries() if e.govuk} | set(cfg.get("ignore", []))
    out = []
    for w in cfg.get("watch", []):
        try:
            content = client.get(GOVUK_API + w["govuk"]).json()
        except Exception as exc:  # noqa: BLE001
            out.append({"collection": w["govuk"], "error": str(exc)})
            continue
        for doc in content.get("links", {}).get("documents", []):
            path = doc.get("base_path", "")
            if path and path not in known:
                out.append({"collection": w["govuk"], "document": path, "title": doc.get("title", ""),
                            "updated": doc.get("public_updated_at", "")})
    return out


def run(settings: Settings, sources: list[str] | None = None, refresh: bool = False) -> list[Result]:
    chosen = [e for e in entries() if not sources or e.source in sources]
    with Client(settings) as client:
        results = [run_entry(settings, client, e, refresh) for e in chosen]
        new_documents = unlisted(client) if not sources else []
    # New files are listed for review; nothing reaches the site until it is published by hand.
    settings.staging_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "finished": datetime.now(UTC).isoformat(timespec="seconds"),
        "new_files": [n for r in results for n in r.new],
        "failed": [{"source": r.entry.source, "role": r.entry.role, "period": r.entry.period, "error": r.error}
                   for r in results if r.error],
        "waiting": [f"{r.entry.source} {r.entry.role} {r.entry.period}" for r in results if r.waiting],
        "unlisted": new_documents,
    }
    (settings.staging_dir / "fetch-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return results
