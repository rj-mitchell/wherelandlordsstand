"""The website's server (`landlords serve`): the published pages, and three small endpoints.

* ``POST /api/corrections``: a reader reports a mistake, or something unfair (its ``kind``). The form works without
  JavaScript (it posts, then goes to a thank-you page). The report is kept in ``data/state.db`` until it is dealt with;
  the email address, if given, is deleted when the report is closed (`landlords reports close`). Like the statement
  form, it has a hidden field people leave empty: a post with it filled in is thanked, and nothing is kept.
* ``POST /api/statements``: a landlord, or someone acting for it, sends a statement in its own words to show beside
  what the site says about it (the right of reply). It is kept as pending until the owner publishes or declines it
  (`landlords statements`).
* ``POST /api/missed``: a search that found nothing. Only the words searched (normalised, at most 80 characters) and
  the day are kept, as a count, so names people look for can be added. No address or identifier is stored.

Reports and statements are kept, and their rules applied, by the Where They Stand sites' shared package (wts-core,
``wts_core.replies``); what this site passes to it is in src/landlords/replies.py, and how a statement is shown on the
pages in src/landlords/statements.py. The limit on posts is the package's too (``wts_core.usage.RateLimiter``).

``GET /api/check`` answers the charity's nightly check of its sites, with counts and ages only (how many reports and
statements are waiting and for how long, how old the newest backup is), and only to the family's check token
(``LANDLORDS_CHECK_TOKEN`` in deploy/.env; wts-core docs/adr/0010). With no token set, the address isn't there.

No cookies, no logs of visits (uvicorn's access log is off), and a content security policy that allows nothing from
other sites.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from wts_core.cli import backup_ages, check_route
from wts_core.ports import SYSTEM_CLOCK, Clock
from wts_core.replies import Refused
from wts_core.usage import RateLimiter, client_address

from landlords.config import SITE, Settings
from landlords.publish import site_dir
from landlords.register import normalise
from landlords.replies import RULES, beside, open_replies, report_kind
from landlords.state import BACKUPS, State, open_state

MAX_BODY = 20000                    # bytes of a posted report or statement that are read
PER_MINUTE = 10                     # posts a minute from one visitor
FORGET_OVER = 50_000                # visitors remembered before those with nothing in the last minute are forgotten
BACKUPS_DIR = Path("/backups")      # where the server's nightly backup is written (deploy/docker-compose.yml)
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                               "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "interest-cohort=()",
}


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


def counted_by(address: str | None) -> str:
    """What the limit on posts counts a visitor by: a short hash of their address, never the address itself. It is
    held in memory for a minute or so and never written down."""
    return sha256((address or "").encode()).hexdigest()[:16]


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


def create_app(settings: Settings, behind_proxy: bool = False, clock: Clock = SYSTEM_CLOCK) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    db = open_state(settings, clock)
    state = State(db)
    replies = open_replies(settings, db, clock)
    # at most ten posts a minute from one visitor, counted in memory only (the shared package's limiter)
    limiter = RateLimiter(PER_MINUTE, forget_over=FORGET_OVER, clock=clock)

    def visitor(request: Request) -> str:
        """The visitor, as the limiter counts them. Behind the front door their address is the first in
        X-Forwarded-For."""
        return counted_by(client_address(request.headers, request.client.host if request.client else None,
                                         behind_proxy=behind_proxy, trust_forwarded_first=True))

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
        page, message, email = (str(data.get(k, "")).strip() for k in ("page", "message", "email"))
        if email and "@" not in email:
            email = ""
        try:
            # The hidden field people leave empty, as on the statement form: when a robot has filled it in, nothing
            # is kept and no number comes back. What is too long is refused, never cut to fit and kept.
            rid = replies.report(kind=str(data.get("kind", "")), page=page, message=message, contact=email,
                                 trap=str(data.get("website", "")))
        except Refused as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        if is_json:
            return {"ok": True} if rid is None else {"ok": True, "id": rid}
        return RedirectResponse("/corrections/thanks.html", status_code=303)

    @app.post("/api/statements")
    async def statements_(request: Request):
        """A statement in a landlord's own words, kept as pending (src/landlords/replies.py). The form works without
        JavaScript: it posts, then goes to a thank-you page, or to a page that says what to change."""
        is_json = request.headers.get("content-type", "").startswith("application/json")
        if not limiter.allow(visitor(request)):
            return JSONResponse({"ok": False, "error": "too many tries; try again in a minute"}, status_code=429)
        body = await request.body()
        data: dict | None = None            # None until the body has been read
        try:
            # Nothing sent is cut to fit and kept (a statement is published as written or declined, never edited):
            # what is too long, here or in the shared rules, is refused with words for the sender.
            if len(body) > MAX_BODY:
                raise Refused(f"What you sent is too long. A statement can be up to {RULES.max_words} words.")
            try:
                data = posted(body, is_json, keep_blank=True)
            except ValueError:
                raise Refused("We couldn't read what was sent. Please send it again.") from None
            sent = {k: str(data.get(k, "") or "") for k in ("name", "role", "page", "part", "text", "link", "email")}
            # the hidden field people leave empty: when a robot has filled it in, it is thanked and nothing is kept
            sid = replies.submit(name=sent["name"], role=sent["role"], item=beside(sent["page"], sent["part"]),
                                 text=sent["text"], link=sent["link"], email=sent["email"],
                                 trap=str(data.get("website", "")))
        except Refused as exc:
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
            return {"ok": True} if sid is None else {"ok": True, "id": sid}
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

    # ---- The charity's nightly check of its sites (wts-core docs/adr/0010) ------------------------------------
    # Counts and ages only, and only to the family's check token. With no token set there is no such address: it
    # is answered as any missing page is.
    if SITE.env("CHECK_TOKEN"):
        check = check_route(SITE, token=SITE.env("CHECK_TOKEN"), replies=replies, clock=clock,
                            backups=lambda: backup_ages(BACKUPS_DIR, BACKUPS, clock=clock))

        @app.get("/api/check")
        def api_check(request: Request):
            if not limiter.allow(visitor(request)):
                return JSONResponse({}, status_code=429)
            status, body = check(request.headers.get("authorization"))
            return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})

    app.mount("/", LiveFiles(settings), name="site")
    return app
