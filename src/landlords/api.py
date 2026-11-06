"""The website's server (`landlords serve`): the published pages, and two small endpoints.

* ``POST /api/corrections``: a reader reports a mistake. The form works without JavaScript (it posts, then goes to a
  thank-you page). The report is kept in ``data/state.db`` until it is dealt with; the email address, if given, is
  deleted when the report is closed (`landlords reports --close`).
* ``POST /api/missed``: a search that found nothing. Only the words searched (normalised, at most 80 characters) and
  the day are kept, as a count, so names people look for can be added. No address or identifier is stored.

No cookies, no logs of visits (uvicorn's access log is off), and a content security policy that allows nothing from
other sites.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import defaultdict, deque
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from landlords.config import Settings
from landlords.register import normalise

LIMITS = {"page": 300, "message": 4000, "email": 200}
SCHEMA = """
create table if not exists reports (id integer primary key, at text not null, page text, message text not null,
  email text, closed_at text, outcome text);
create table if not exists missed (day text not null, query text not null, count integer not null default 0,
  primary key (day, query));
create table if not exists approvals (token_hash text primary key, build text not null, created text not null,
  expires text not null, published_at text, rolled_back_at text);
"""
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                               "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "interest-cohort=()",
}


class State:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def add_report(self, page: str, message: str, email: str) -> int:
        with self.connect() as db:
            cur = db.execute("insert into reports (at, page, message, email) values (?, ?, ?, ?)",
                             (datetime.now(UTC).isoformat(timespec="seconds"), page, message, email or None))
            return int(cur.lastrowid)

    def open_reports(self) -> list[tuple]:
        with self.connect() as db:
            return db.execute("select id, at, page, message, email from reports where closed_at is null "
                              "order by id").fetchall()

    def close_report(self, rid: int, outcome: str) -> bool:
        """Close a report and delete the reporter's email address (the privacy page says so)."""
        with self.connect() as db:
            cur = db.execute("update reports set closed_at = ?, outcome = ?, email = null where id = ? and "
                             "closed_at is null", (datetime.now(UTC).isoformat(timespec="seconds"), outcome, rid))
            return cur.rowcount == 1

    def missed(self, query: str) -> None:
        with self.connect() as db:
            db.execute("insert into missed (day, query, count) values (?, ?, 1) on conflict (day, query) "
                       "do update set count = count + 1", (date.today().isoformat(), query))

    def open_report_count(self) -> int:
        with self.connect() as db:
            return db.execute("select count(*) from reports where closed_at is null").fetchone()[0]

    # Approval links (publish.py, "approve"): only a hash of each token is kept, so the database can't approve.
    def add_approval(self, build: str, days: int) -> str:
        import secrets
        from datetime import timedelta

        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        with self.connect() as db:
            db.execute("insert into approvals (token_hash, build, created, expires) values (?, ?, ?, ?)",
                       (_hash(token), build, now.isoformat(timespec="seconds"),
                        (now + timedelta(days=days)).isoformat(timespec="seconds")))
        return token

    def approval(self, token: str) -> dict | None:
        """The approval a token is for, if it exists and hasn't expired."""
        with self.connect() as db:
            row = db.execute("select build, created, expires, published_at, rolled_back_at from approvals "
                             "where token_hash = ?", (_hash(token),)).fetchone()
        if not row or row[2] < datetime.now(UTC).isoformat(timespec="seconds"):
            return None
        return dict(zip(("build", "created", "expires", "published_at", "rolled_back_at"), row, strict=True))

    def mark(self, token: str, field: str) -> None:
        assert field in ("published_at", "rolled_back_at")
        with self.connect() as db:
            db.execute(f"update approvals set {field} = ? where token_hash = ?",  # noqa: S608 (field is checked)
                       (datetime.now(UTC).isoformat(timespec="seconds"), _hash(token)))

    def top_missed(self, days: int = 28, limit: int = 50) -> list[tuple]:
        with self.connect() as db:
            return db.execute("select query, sum(count) n from missed where day >= date('now', ?) group by query "
                              "order by n desc limit ?", (f"-{days} days", limit)).fetchall()


def _hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


class Limiter:
    """At most ``per_minute`` posts a minute from one visitor, counted in memory only and never written down."""

    def __init__(self, per_minute: int = 10):
        self.per_minute = per_minute
        self.seen: dict[str, deque] = defaultdict(deque)

    def allow(self, who: str) -> bool:
        key = sha256(who.encode()).hexdigest()[:16]
        now = time.monotonic()
        q = self.seen[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return False
        q.append(now)
        return True


def site_dir(settings: Settings) -> Path:
    """The published pages: data/live (`landlords publish`), or data/site while nothing is published."""
    live = settings.data_dir / "live"
    return live if live.exists() else settings.data_dir / "site"


def cache_control(path: str) -> str:
    """How long Cloudflare and browsers may keep a file. Everything under /assets/ has a fingerprint of its content in
    its name ("styles.3f9a2c1d.css", src/landlords/site.py), so it never changes under that name and can be kept for a
    year, as the shared front door also says. Everything else (pages, downloads, names.json) changes with each update,
    so it is checked with the server each time: Cloudflare would otherwise keep a CSS, JS or CSV file for two hours by
    default and serve the old one after an update, as it did on 6 November 2026."""
    if path.startswith("/assets/"):
        return "public, max-age=31536000, immutable"
    return "no-cache"


def stylesheets(settings: Settings) -> list[str]:
    """The live build's stylesheets, for the API's own pages (assets.json, written by the build): the family kit's
    fonts and styles, then the site's own."""
    try:
        names = json.loads((site_dir(settings) / "assets.json").read_text())
        return ["/" + names[n] for n in ("fonts.css", "family.css", "styles.css") if n in names]
    except (OSError, ValueError, KeyError):
        return ["/styles.css"]   # a build made before assets/ (it kept its stylesheet at the top)


class LiveFiles(StaticFiles):
    """Static files from whichever build is live now, so `landlords publish` and `rollback` take effect at once."""

    def __init__(self, settings: Settings):
        self.settings = settings
        super().__init__(directory=site_dir(settings), html=True, check_dir=False)

    def lookup_path(self, path: str):
        self.all_directories = [site_dir(self.settings)]
        return super().lookup_path(path)


def create_app(settings: Settings, behind_proxy: bool = False) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    state = State(settings.data_dir / "state.db")
    limiter = Limiter()

    def visitor(request: Request) -> str:
        if behind_proxy and request.headers.get("x-forwarded-for"):
            return request.headers["x-forwarded-for"].split(",")[0].strip()
        return request.client.host if request.client else ""

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        for k, v in HEADERS.items():
            response.headers.setdefault(k, v)
        response.headers.setdefault("Cache-Control", cache_control(request.url.path))
        return response

    @app.get("/api/health")
    def health():
        info = site_dir(settings) / "build-info.json"
        return {"ok": True, "build": json.loads(info.read_text()).get("build") if info.exists() else None}

    @app.post("/api/corrections")
    async def corrections(request: Request):
        if not limiter.allow(visitor(request)):
            return JSONResponse({"ok": False, "error": "too many reports; try again in a minute"}, status_code=429)
        body = (await request.body())[:20000]
        is_json = request.headers.get("content-type", "").startswith("application/json")
        if is_json:
            data = json.loads(body or b"{}")
        else:
            data = {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace")).items()}
        fields = {k: str(data.get(k, "")).strip()[:n] for k, n in LIMITS.items()}
        if not fields["message"]:
            return JSONResponse({"ok": False, "error": "please say what is wrong"}, status_code=400)
        if fields["email"] and "@" not in fields["email"]:
            fields["email"] = ""
        rid = state.add_report(**fields)
        if is_json:
            return {"ok": True, "id": rid}
        return RedirectResponse("/corrections/thanks.html", status_code=303)

    @app.post("/api/missed")
    async def missed(request: Request):
        if not limiter.allow(visitor(request)):
            return JSONResponse({"ok": False}, status_code=429)
        data = json.loads((await request.body())[:2000] or b"{}")
        q = normalise(str(data.get("q", "")))[:80]
        if len(q) >= 2:
            state.missed(q)
        return {"ok": True}

    # ---- Approving a new build (publish.py): the link in the weekly email --------------------------------------
    # Opening the link never publishes (mail scanners open links): it shows the report and a button, which posts.

    def admin_page(title: str, body: str, status: int = 200) -> HTMLResponse:
        from html import escape

        html = (f'<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" '
                f'content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">'
                f'<title>{escape(title)}</title>'
                + "".join(f'<link rel="stylesheet" href="{href}">' for href in stylesheets(settings))
                + '</head><body>'
                f'<main id="main"><h1>{escape(title)}</h1>{body}</main></body></html>')
        return HTMLResponse(html, status_code=status, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})

    def approval_or_404(request: Request, token: str):
        if not limiter.allow(visitor(request)):
            return None, admin_page("Too many tries", "<p>Try again in a minute.</p>", 429)
        a = state.approval(token)
        info_path = settings.data_dir / "builds" / (a["build"] if a else "-") / "build-info.json"
        if not a or not info_path.exists():
            return None, admin_page("This link has expired", "<p>It is no longer valid, or its pages have been "
                                    "cleared away. The next weekly update sends a new one.</p>", 404)
        return (a, json.loads(info_path.read_text())), None

    def summary(info: dict) -> str:
        from html import escape

        new = info.get("new_file_titles") or []
        failed = info.get("checks_failed") or []
        parts = [f"<p>Built {escape(str(info.get('finished', '')))[:16].replace('T', ' ')}.</p>"]
        parts.append("<h2>New files from the publishers</h2>" + (
            "<ul>" + "".join(f"<li>{escape(t)}</li>" for t in new) + "</ul>" if new else
            "<p>None: these pages have new code or wording.</p>"))
        parts.append("<h2>Checks</h2>" + ("<p>All passed.</p>" if not failed else
                     "<ul>" + "".join(f"<li>{escape(f)}</li>" for f in failed) + "</ul>"))
        return "".join(parts)

    @app.get("/admin/approve/{token}")
    def approve_page(request: Request, token: str):
        from landlords.publish import current

        got, err = approval_or_404(request, token)
        if err:
            return err
        a, info = got
        if a["published_at"]:
            live = current(settings) == a["build"] and not a["rolled_back_at"]
            body = f"<p>These pages were published on {a['published_at'][:16].replace('T', ' ')}.</p>"
            if a["rolled_back_at"]:
                body += "<p>They were taken down again, and the pages before them put back.</p>"
            elif live:
                body += (f'<form method="post" action="/admin/rollback/{token}"><p><button type="submit">'
                         "Undo: put back the previous pages</button></p></form>")
            return admin_page("Published", body)
        body = summary(info) + f'<p><a href="/admin/preview/{token}/index.html">Look at the new pages</a></p>'
        if info.get("checks_failed"):
            body += "<p>These pages can't be published until the failed checks are fixed.</p>"
        else:
            body += ('<form method="post"><p><button type="submit">Publish these pages</button></p></form>'
                     "<p class=\"hint\">If you do nothing, the site keeps its current pages.</p>")
        return admin_page("New pages to approve", body)

    @app.post("/admin/approve/{token}")
    def approve(request: Request, token: str):
        from landlords import publish as publish_

        got, err = approval_or_404(request, token)
        if err:
            return err
        a, info = got
        if not a["published_at"]:
            if info.get("checks_failed"):
                return admin_page("Not published", "<p>Its checks failed: it needs fixing first.</p>", 409)
            publish_.publish(settings, a["build"])
            state.mark(token, "published_at")
        return RedirectResponse(f"/admin/approve/{token}", status_code=303)

    @app.post("/admin/rollback/{token}")
    def undo(request: Request, token: str):
        from landlords import publish as publish_

        got, err = approval_or_404(request, token)
        if err:
            return err
        a, _ = got
        if a["published_at"] and not a["rolled_back_at"] and publish_.current(settings) == a["build"]:
            publish_.rollback(settings)
            state.mark(token, "rolled_back_at")
        return RedirectResponse(f"/admin/approve/{token}", status_code=303)

    @app.get("/admin/preview/{token}/{path:path}")
    def preview(request: Request, token: str, path: str):
        got, err = approval_or_404(request, token)
        if err:
            return err
        root = (settings.data_dir / "builds" / got[0]["build"]).resolve()
        target = (root / path).resolve()
        if target.is_dir():
            target = target / "index.html"
        if not target.is_relative_to(root) or not target.is_file():
            return admin_page("Not found", "<p>That page isn't in this build.</p>", 404)
        return FileResponse(target, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})

    app.mount("/", LiveFiles(settings), name="site")
    return app
