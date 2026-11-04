"""Updating, publishing and rolling back (docs/OPERATIONS.md).

* `landlords update` fetches new files, loads them, runs the checks, scores and builds the pages into a new folder,
  ``data/builds/<time>/``, with ``build-info.json`` (the checks, what is new) beside them. It never changes the live
  site. Run weekly.
* `landlords publish` points ``data/live`` at a build, by hand, after looking at the change report. A build whose
  checks failed is refused unless ``--force``.
* `landlords rollback` points ``data/live`` back at the build published before.

The last ``keep`` builds are kept, and never the live one or the one before it.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from landlords.config import Settings


def builds_dir(settings: Settings) -> Path:
    return settings.data_dir / "builds"


def live_link(settings: Settings) -> Path:
    return settings.data_dir / "live"


def history_path(settings: Settings) -> Path:
    return settings.data_dir / "published.jsonl"


def code_version() -> str:
    """A fingerprint of everything that shapes the pages besides the data: the code, config/ and data_static/.
    A new version of the site (merged and installed on the server) changes it, so the pages are rebuilt."""
    import hashlib

    from landlords.config import REPO_ROOT

    h = hashlib.sha256()
    for folder in ("src/landlords", "config", "data_static"):
        for path in sorted((REPO_ROOT / folder).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                h.update(str(path.relative_to(REPO_ROOT)).encode())
                h.update(path.read_bytes())
    return h.hexdigest()[:16]


def _info(settings: Settings, build: str | None) -> dict:
    path = builds_dir(settings) / (build or "-") / "build-info.json"
    return json.loads(path.read_text()) if path.exists() else {}


def update(settings: Settings, fetch: bool = True, notify: bool = True) -> dict:
    """The weekly update. Builds new pages only when something is new (files from the publishers, or a new version
    of the site); then, before launch, publishes them, and after launch asks the owner to approve them by email
    ([publish] in config/settings.toml)."""
    from landlords import area, checks, load, register, score, site
    from landlords import fetch as fetch_

    started = datetime.now(UTC)
    info: dict = {"build": started.strftime("%Y%m%d-%H%M%S"), "started": started.isoformat(timespec="seconds"),
                  "code_version": code_version()}
    if fetch:
        results = fetch_.run(settings)
        new = [n for r in results for n in r.new]
        info["new_files"] = [n["file"] for n in new]
        info["new_file_titles"] = [f"{n['publisher']}: {n['title'] or n['file']} ({n['period']})" for n in new]
        info["fetch_failed"] = [f"{r.entry.source} {r.entry.period}: {r.error}" for r in results if r.error]
        info["waiting"] = [f"{r.entry.source} {r.entry.period}" for r in results if r.waiting]
        report = json.loads((settings.staging_dir / "fetch-report.json").read_text())
        info["unlisted"] = report.get("unlisted", [])
    info["loaded"] = load.run(settings)
    info["register"] = register.build(settings).__dict__
    info["loaded"]["ombudsman"] = load.run(settings, ["ombudsman"])["ombudsman"]  # names matched to new rows
    report = checks.run(settings)
    info["checks_failed"] = [f"{c['name']}: {c['detail']}" for c in report["checks"] if not c["ok"]]
    rights = next((c for c in report["checks"] if c["name"] == "rights page checked on time"), {})
    info["needs_attention"] = bool(info["checks_failed"] or info.get("fetch_failed"))

    live = current(settings)
    latest = sorted(p.name for p in builds_dir(settings).glob("*") if (p / "build-info.json").exists())
    last = _info(settings, latest[-1] if latest else None)
    something_new = (not latest or bool(info.get("new_files")) or last.get("code_version") != info["code_version"]
                     or bool(info["register"].get("added")))
    if something_new:
        area.build(settings)
        info["scores"] = score.run(settings)
        out = builds_dir(settings) / info["build"]
        info["pages"] = site.build(settings, out)
        changes = settings.staging_dir / "change-report.json"
        if changes.exists():
            shutil.copy(changes, out / "change-report.json")
    else:
        info["build"] = None  # the pages would be the same as the last build's
    info["finished"] = datetime.now(UTC).isoformat(timespec="seconds")

    # What happens to a new build -------------------------------------------------------------------------------
    cfg = settings.section("publish")
    launched = bool(settings.section("site").get("launched"))
    links = None
    if info["build"] and not info["checks_failed"]:
        if not live or not launched or cfg.get("mode") == "auto":
            why = ("the first pages" if not live else "the site is not public yet, so nothing needs approving"
                   if not launched else "pages are published without approval ([publish] mode = \"auto\")")
            (builds_dir(settings) / info["build"] / "build-info.json").write_text(json.dumps(info, default=str))
            publish(settings, info["build"])
            info["published"] = f"The new pages are live: {why}."
        else:
            from landlords.api import State

            days = int(cfg.get("approval_days", 14))
            token = State(settings.data_dir / "state.db").add_approval(info["build"], days)
            url = (settings.section("site").get("url") or "").rstrip("/")
            links = {"approve": f"{url}/admin/approve/{token}", "preview": f"{url}/admin/preview/{token}/index.html",
                     "days": days}
            info["approval"] = "waiting for approval by email"
    if info["build"]:
        (builds_dir(settings) / info["build"] / "build-info.json").write_text(
            json.dumps(info, indent=2, default=str) + "\n")
    _prune(settings, int(cfg.get("keep_builds", 6)), {info["build"], live, current(settings)})

    # The weekly email ------------------------------------------------------------------------------------------
    from landlords.api import State

    state = State(settings.data_dir / "state.db")
    extra = {"rights_due": rights.get("rows") or [], "open_reports": state.open_report_count(),
             "missed": state.top_missed(7, 5)}
    changes_path = settings.staging_dir / "change-report.json"
    extra["changes"] = json.loads(changes_path.read_text()) if changes_path.exists() else {}
    worth_sending = (info["build"] or info["checks_failed"] or info.get("fetch_failed") or info.get("unlisted")
                     or extra["rights_due"] or extra["open_reports"])
    if notify and worth_sending:
        from landlords import notify as notify_

        subject, body = notify_.report({**info, "build": info["build"] or "no new pages"}, links, extra)
        info["email"] = notify_.send(settings, subject, body)
    else:
        info["email"] = "nothing to report" if notify else "not sent (--no-email)"

    with (settings.data_dir / "updates.jsonl").open("a") as fh:
        fh.write(json.dumps({k: info.get(k) for k in ("build", "finished", "needs_attention", "email", "published",
                                                        "approval")}
                            | {"new_files": len(info.get("new_files", [])), "checks_failed": len(info["checks_failed"])})
                 + "\n")
    return info


def current(settings: Settings) -> str | None:
    link = live_link(settings)
    return Path(os.readlink(link)).name if link.is_symlink() else None


def _point_live(settings: Settings, build: str) -> None:
    link = live_link(settings)
    tmp = link.with_name("live.tmp")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(Path("builds") / build)
    os.replace(tmp, link)  # atomic: readers see the old site or the new one, never neither


def publish(settings: Settings, build: str | None = None, force: bool = False, keep: int = 6) -> dict:
    builds = sorted(p.name for p in builds_dir(settings).glob("*") if (p / "build-info.json").exists())
    if not builds:
        raise RuntimeError("no builds: run `landlords update` first")
    build = build or builds[-1]
    if build not in builds:
        raise RuntimeError(f"no build {build}")
    info = json.loads((builds_dir(settings) / build / "build-info.json").read_text())
    if info.get("checks_failed") and not force:
        raise RuntimeError(f"build {build} failed checks: {info['checks_failed']}. Fix them, or --force.")
    previous = current(settings)
    _point_live(settings, build)
    with history_path(settings).open("a") as fh:
        fh.write(json.dumps({"published": build, "previous": previous,
                             "at": datetime.now(UTC).isoformat(timespec="seconds"), "forced": force}) + "\n")
    _prune(settings, keep, {build, previous})
    return {"live": build, "previous": previous}


def rollback(settings: Settings) -> dict:
    path = history_path(settings)
    history = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    if not history or not history[-1].get("previous"):
        raise RuntimeError("nothing to roll back to")
    last = history[-1]
    if not (builds_dir(settings) / last["previous"]).exists():
        raise RuntimeError(f"the previous build {last['previous']} has been removed")
    _point_live(settings, last["previous"])
    with path.open("a") as fh:
        fh.write(json.dumps({"published": last["previous"], "previous": last["published"],
                             "at": datetime.now(UTC).isoformat(timespec="seconds"), "rollback": True}) + "\n")
    return {"live": last["previous"], "rolled_back_from": last["published"]}


def _prune(settings: Settings, keep: int, protect: set) -> None:
    builds = sorted(p for p in builds_dir(settings).glob("*") if p.is_dir())
    for p in builds[:-keep]:
        if p.name not in protect:
            shutil.rmtree(p)
