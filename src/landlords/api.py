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
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from landlords.config import Settings
from landlords.register import normalise

LIMITS = {"page": 300, "message": 4000, "email": 200}
SCHEMA = """
create table if not exists reports (id integer primary key, at text not null, page text, message text not null,
  email text, closed_at text, outcome text);
create table if not exists missed (day text not null, query text not null, count integer not null default 0,
  primary key (day, query));
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

    def top_missed(self, days: int = 28, limit: int = 50) -> list[tuple]:
        with self.connect() as db:
            return db.execute("select query, sum(count) n from missed where day >= date('now', ?) group by query "
                              "order by n desc limit ?", (f"-{days} days", limit)).fetchall()


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

    app.mount("/", LiveFiles(settings), name="site")
    return app
