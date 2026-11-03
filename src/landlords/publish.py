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


def update(settings: Settings, fetch: bool = True) -> dict:
    from landlords import area, checks, load, register, score, site
    from landlords import fetch as fetch_

    started = datetime.now(UTC)
    info: dict = {"build": started.strftime("%Y%m%d-%H%M%S"), "started": started.isoformat(timespec="seconds")}
    if fetch:
        results = fetch_.run(settings)
        info["new_files"] = [n["file"] for r in results for n in r.new]
        info["fetch_failed"] = [f"{r.entry.source} {r.entry.period}: {r.error}" for r in results if r.error]
    info["loaded"] = load.run(settings)
    info["register"] = register.build(settings).__dict__
    info["loaded"]["ombudsman"] = load.run(settings, ["ombudsman"])["ombudsman"]  # names matched to new rows
    report = checks.run(settings)
    info["checks_failed"] = [f"{c['name']}: {c['detail']}" for c in report["checks"] if not c["ok"]]
    area.build(settings)
    info["scores"] = score.run(settings)
    out = builds_dir(settings) / info["build"]
    info["pages"] = site.build(settings, out)
    changes = settings.staging_dir / "change-report.json"
    if changes.exists():
        shutil.copy(changes, out / "change-report.json")
    info["needs_attention"] = bool(info["checks_failed"] or info.get("fetch_failed"))
    info["finished"] = datetime.now(UTC).isoformat(timespec="seconds")
    (out / "build-info.json").write_text(json.dumps(info, indent=2, default=str) + "\n")
    with (settings.data_dir / "updates.jsonl").open("a") as fh:
        fh.write(json.dumps({k: info[k] for k in ("build", "finished", "needs_attention")}
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
