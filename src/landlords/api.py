"""The website's server (`landlords serve`): the published pages, and three small endpoints.

* ``POST /api/corrections``: a reader reports a mistake, or something unfair (its ``kind``). The form works without
  JavaScript (it posts, then goes to a thank-you page). The report is kept in ``data/state.db`` until it is dealt with;
  the email address, if given, is deleted when the report is closed (`landlords reports --close`). Like the statement
  form, it has a hidden field people leave empty: a post with it filled in is thanked, and nothing is kept.
* ``POST /api/statements``: a landlord, or someone acting for it, sends a statement in its own words to show beside
  what the site says about it (the right of reply; src/landlords/statements.py). It is kept as pending until the owner
  publishes or declines it (`landlords statements`).
* ``POST /api/missed``: a search that found nothing. Only the words searched (normalised, at most 80 characters) and
  the day are kept, as a count, so names people look for can be added. No address or identifier is stored.

No cookies, no logs of visits (uvicorn's access log is off), and a content security policy that allows nothing from
other sites.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
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
MAX_BODY = 20000                    # bytes of a posted report or statement that are read
# The routes of the charity's impartiality policy (section 7.1) on the report form, by the family glossary's names
# (config/wording.toml, [corrections] kinds). The third route, a statement, has its own form. "takedown" is a request to
# remove a person's details, dealt with first. A report from an older copy of the form has no kind.
KINDS = ("wrong", "unfair", "takedown", "other")
# ?kind= and the posted value also accept the words the sister sites use, so a link made for one of them still works
KIND_ALIASES = {"correction": "wrong", "error": "wrong", "mistake": "wrong", "complaint": "unfair",
                "general": "other"}
SCHEMA = """
create table if not exists reports (id integer primary key, at text not null, page text, message text not null,
  email text, closed_at text, outcome text);
create table if not exists statements (id integer primary key, at text not null, name text not null, role text not null,
  page text not null, part text not null default '', text text not null, link text, email text,
  status text not null default 'pending', landlord text, checked text, reason text, published_at text,
  updated_at text, closed_at text);
create table if not exists statement_log (id integer primary key, statement integer not null, at text not null,
  action text not null, note text);
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
            if "kind" not in {c[1] for c in db.execute("pragma table_info(reports)")}:
                db.execute("alter table reports add column kind text")   # a database made before kinds

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """A connection for one piece of work: committed at the end of the ``with`` block, and always closed (on an
        error, without committing, which undoes the work), as the sister sites' state databases do."""
        db = sqlite3.connect(self.path, timeout=10)
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def add_report(self, page: str, message: str, email: str, kind: str = "") -> int:
        with self.connect() as db:
            cur = db.execute("insert into reports (at, page, message, email, kind) values (?, ?, ?, ?, ?)",
                             (datetime.now(UTC).isoformat(timespec="seconds"), page, message, email or None,
                              kind or None))
            return int(cur.lastrowid)

    def open_reports(self) -> list[tuple]:
        """Open reports, requests to remove a person's details first (the impartiality policy, 7.1)."""
        with self.connect() as db:
            return db.execute("select id, at, kind, page, message, email from reports where closed_at is null "
                              "order by kind is not 'takedown', id").fetchall()

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

    # Statements in a landlord's own words (src/landlords/statements.py has the rules, and shows them on the pages)
    STATEMENT_FIELDS = ("id", "at", "name", "role", "page", "part", "text", "link", "email", "status", "landlord",
                        "checked", "reason", "published_at", "updated_at", "closed_at")

    def add_statement(self, name: str, role: str, page: str, part: str, text: str, link: str, email: str,
                      landlord: str | None) -> int:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self.connect() as db:
            cur = db.execute("insert into statements (at, name, role, page, part, text, link, email, landlord) "
                             "values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (now, name, role, page, part, text, link or None, email, landlord))
            sid = int(cur.lastrowid)
            db.execute("insert into statement_log (statement, at, action) values (?, ?, 'received')", (sid, now))
            return sid

    def statements(self, status: str | None = None) -> list[dict]:
        sql = f"select {', '.join(self.STATEMENT_FIELDS)} from statements"  # noqa: S608 (fixed names)
        with self.connect() as db:
            rows = (db.execute(sql + " where status = ? order by id", (status,)) if status
                    else db.execute(sql + " order by id")).fetchall()
        return [dict(zip(self.STATEMENT_FIELDS, r, strict=True)) for r in rows]

    def statement(self, sid: int) -> dict | None:
        return next((s for s in self.statements() if s["id"] == sid), None)

    def change_statement(self, sid: int, action: str, note: str = "", **fields) -> None:
        """Set some of a statement's fields, and log what was done and why (the policy, 7.4: every decision and its
        reasons are logged)."""
        assert set(fields) <= set(self.STATEMENT_FIELDS) - {"id", "at"}
        with self.connect() as db:
            if fields:
                sets = ", ".join(f"{k} = ?" for k in fields)
                db.execute(f"update statements set {sets} where id = ?",  # noqa: S608 (names are checked)
                           (*fields.values(), sid))
            db.execute("insert into statement_log (statement, at, action, note) values (?, ?, ?, ?)",
                       (sid, datetime.now(UTC).isoformat(timespec="seconds"), action, note or None))

    def statement_log(self, sid: int) -> list[tuple]:
        with self.connect() as db:
            return db.execute("select at, action, note from statement_log where statement = ? order by id",
                              (sid,)).fetchall()

    def forget_statement_emails(self, before: str) -> int:
        """Delete the email address of every statement withdrawn or declined before ``before`` (the privacy page:
        three months after; ``statements.forget_old_emails``)."""
        with self.connect() as db:
            return db.execute("update statements set email = null where email is not null and status in "
                              "('withdrawn', 'declined') and closed_at < ?", (before,)).rowcount

    def pending_statement_count(self) -> int:
        with self.connect() as db:
            return db.execute("select count(*) from statements where status = 'pending'").fetchone()[0]

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


def report_kind(value: str) -> str:
    """The kind of a report, from the form or a link's ?kind=: one of KINDS, or "" if it is none of them."""
    value = value.strip().lower()
    value = KIND_ALIASES.get(value, value)
    return value if value in KINDS else ""


def prefill(html: str, kind: str = "", page: str = "", part: str = "") -> str:
    """The report form or the statement form with a choice made: the radio button for ``kind`` checked, the page's
    address filled in, and the part of the page chosen. Only the form's own fields are touched, and what is filled in
    is escaped."""
    from html import escape

    kind = report_kind(kind)
    if kind and f'name="kind" value="{kind}"' in html:
        html = re.sub(r'(name="kind" value="\w+") checked>', r"\1>", html)
        html = html.replace(f'name="kind" value="{kind}">', f'name="kind" value="{kind}" checked>')
    if page:
        html = html.replace('id="page" name="page" value=""', f'id="page" name="page" value="{escape(page[:300])}"', 1)
    if part and re.fullmatch(r"[a-z]{1,20}", part):
        html = html.replace(f'<option value="{part}">', f'<option value="{part}" selected>', 1)
    return html


def posted(body: bytes, is_json: bool, keep_blank: bool = False) -> dict:
    """The fields of a posted form, or of a JSON object. Raises ValueError if a JSON body can't be read as one."""
    if not is_json:
        return {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace"), keep_blank_values=keep_blank).items()}
    data = json.loads(body or b"{}")
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data


class Limiter:
    """At most ``per_minute`` posts a minute from one visitor, counted in memory only and never written down. Safe to
    call from several threads at once (the approval pages run on a pool of them). Once more than ``forget_over``
    visitors are remembered, those with nothing in the last minute are forgotten, so the memory used stays small."""

    def __init__(self, per_minute: int = 10, forget_over: int = 50_000):
        self.per_minute = per_minute
        self.forget_over = forget_over
        self.seen: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, who: str) -> bool:
        key = sha256(who.encode()).hexdigest()[:16]
        now = time.monotonic()
        with self.lock:
            q = self.seen[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            if len(self.seen) > self.forget_over:  # forget idle visitors
                for k in [k for k, v in self.seen.items() if not v or now - v[-1] > 60]:
                    del self.seen[k]
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
        body = (await request.body())[:MAX_BODY]
        is_json = request.headers.get("content-type", "").startswith("application/json")
        try:
            data = posted(body, is_json)
        except ValueError:
            return JSONResponse({"ok": False, "error": "the report couldn't be read; please send it again"},
                                status_code=400)
        if str(data.get("website", "")).strip():
            # the hidden field people leave empty, as on the statement form: a robot filled it in. Thank it, keep
            # nothing.
            return {"ok": True} if is_json else RedirectResponse("/corrections/thanks.html", status_code=303)
        fields = {k: str(data.get(k, "")).strip()[:n] for k, n in LIMITS.items()}
        if not fields["message"]:
            return JSONResponse({"ok": False, "error": "please say what is wrong"}, status_code=400)
        if fields["email"] and "@" not in fields["email"]:
            fields["email"] = ""
        rid = state.add_report(**fields, kind=report_kind(str(data.get("kind", ""))))
        if is_json:
            return {"ok": True, "id": rid}
        return RedirectResponse("/corrections/thanks.html", status_code=303)

    @app.post("/api/statements")
    async def statements_(request: Request):
        """A statement in a landlord's own words, kept as pending (src/landlords/statements.py). The form works without
        JavaScript: it posts, then goes to a thank-you page, or to a page that says what to change."""
        from landlords import statements as st

        is_json = request.headers.get("content-type", "").startswith("application/json")
        if not limiter.allow(visitor(request)):
            return JSONResponse({"ok": False, "error": "too many tries; try again in a minute"}, status_code=429)
        body = await request.body()
        data: dict | None = None            # None until the body has been read
        try:
            # Nothing sent is cut to fit and kept (a statement is published as written or declined, never edited):
            # what is too long, here or in st.submit, is refused with words for the sender.
            if len(body) > MAX_BODY:
                raise st.StatementError(f"What you sent is too long. A statement can be up to {st.MAX_WORDS} words.")
            try:
                data = posted(body, is_json, keep_blank=True)
            except ValueError:
                raise st.StatementError("We couldn't read what was sent. Please send it again.") from None
            if str(data.get("website", "")).strip():
                # the hidden field people leave empty: a robot filled it in. Thank it, keep nothing.
                return {"ok": True} if is_json else RedirectResponse("/named/thanks.html", status_code=303)
            sid = st.submit(state, data, lambda page: (site_dir(settings) / page / "index.html").is_file())
        except st.StatementError as exc:
            if is_json:
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
            from html import escape

            # Their words are given back whole, to copy: what is too long is theirs to shorten, not ours to cut
            words = "</p>" if data is None else (
                f' Here it is too, so you can copy it.</p><label for="words">Your statement</label>'
                f'<textarea id="words" rows="8" readonly>{escape(str(data.get("text", "")))}</textarea>')
            return admin_page("Your statement wasn't sent", (
                f"<p>{escape(str(exc))}</p><p>Go back to the form to change it: your browser should still have what "
                f'you wrote.{words}<p><a href="/named/index.html#send">Back to the form</a></p>'), 400)
        if is_json:
            return {"ok": True, "id": sid}
        return RedirectResponse("/named/thanks.html", status_code=303)

    # The report form and the statement form, with a choice made by the link that led there: ?kind= picks the kind of
    # report ("wrong", "unfair", "takedown", "other", or the sister sites' words for them) and ?page= fills in the
    # page, so "If you're named" can start each route. Without a query the page is served as it was built.
    def prefilled(page: str, request: Request):
        path = site_dir(settings) / page / "index.html"
        if not path.is_file():
            return admin_page("Page not found", "<p>That page isn't on the site.</p>", 404)
        q = request.query_params
        if not (q.get("kind") or q.get("page") or q.get("part")):
            return FileResponse(path)
        return HTMLResponse(prefill(path.read_text(), q.get("kind", ""), q.get("page", ""), q.get("part", "")))

    @app.api_route("/corrections/", methods=["GET", "HEAD"])
    @app.api_route("/corrections/index.html", methods=["GET", "HEAD"])
    def corrections_page(request: Request):
        return prefilled("corrections", request)

    @app.api_route("/named/", methods=["GET", "HEAD"])
    @app.api_route("/named/index.html", methods=["GET", "HEAD"])
    def named_page(request: Request):
        return prefilled("named", request)

    @app.post("/api/missed")
    async def missed(request: Request):
        if not limiter.allow(visitor(request)):
            return JSONResponse({"ok": False}, status_code=429)
        try:
            data = posted((await request.body())[:2000], True)
        except ValueError:
            return JSONResponse({"ok": False}, status_code=400)
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
                f'<meta name="color-scheme" content="light dark"><title>{escape(title)}</title>'
                + "".join(f'<link rel="stylesheet" href="{href}">' for href in stylesheets(settings))
                + '</head><body>'
                f'<main id="main" class="wrap"><h1>{escape(title)}</h1>{body}</main></body></html>')
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
