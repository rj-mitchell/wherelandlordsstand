"""Command line.

    landlords fetch                     # download new files listed in config/sources.toml into data/raw/
    landlords fetch tsm stock           # some sources only
    landlords load                      # build the tidy tables in data/staging/ from the newest files
    landlords register                  # add new landlords to data_static/landlords.csv, and published names
    landlords match                     # propose landlords for names without a code, for review
    landlords match --accept FILE       # add the proposals marked "yes" in FILE to data_static/aliases.csv
    landlords check                     # the checks: every row matched, ranges, reconciliation, coverage
    landlords score                     # peer groups and bands (config/scoring.toml)
    landlords build                     # the pages, in data/site/
    landlords serve                     # see them at http://127.0.0.1:8000/ (this computer only)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from landlords.config import load_settings

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(message)s")


@app.command()
def fetch(source: list[str] = typer.Argument(None, help="sources to fetch; all if none"),
          refresh: bool = typer.Option(False, help="fetch files again even if their address was fetched before")) -> None:
    """Download new published files into data/raw/, never overwriting one already there."""
    from landlords import fetch as fetch_

    failed = 0
    for r in fetch_.run(load_settings(), source or None, refresh):
        failed += bool(r.error)
        typer.echo(json.dumps({"source": r.entry.source, "role": r.entry.role, "period": r.entry.period,
                               "found": len(r.found), "new": [n["file"] for n in r.new],
                               "cached": len(r.cached), "error": r.error}))
    raise typer.Exit(1 if failed else 0)


@app.command()
def load(source: list[str] = typer.Argument(None, help="tsm, grades, providers, stock, ombudsman; all if none")) -> None:
    """Read the newest fetched files into tidy tables in data/staging/. Stops if a file's layout has changed."""
    from landlords import load as load_

    for name, counts in load_.run(load_settings(), source or None).items():
        typer.echo(json.dumps({"loaded": name, **counts}))


@app.command()
def register() -> None:
    """Add new landlords to data_static/landlords.csv and the names publishers print to aliases.csv."""
    from landlords import register as reg

    typer.echo(json.dumps(reg.build(load_settings()).__dict__))


@app.command()
def match(accept: Path = typer.Option(None, help="a reviewed file: add the rows marked accept=yes"),
          out: Path = typer.Option(None, help="where to write proposals (default data/staging/match-review.csv)")) -> None:
    """Propose landlords for published names with no code (the Ombudsman's). Nothing is accepted automatically."""
    from landlords import register as reg
    from landlords.load.common import read_table

    s = load_settings()
    if accept:
        typer.echo(json.dumps({"aliases_added": reg.accept(accept)}))
        return
    names = sorted({(r["name_published"], f"Housing Ombudsman {r['period']}")
                    for r in read_table(s, "ombudsman") if not r["landlord_id"]})
    parents: dict[str, list[str]] = {}
    for g in read_table(s, "groups"):
        if g.get("unregistered_parent"):
            parents.setdefault(reg.normalise(g["unregistered_parent"]), []).append(g["landlord_id"])
    proposals = reg.propose(names, unregistered_parents=parents)
    path = out or s.staging_dir / "match-review.csv"
    reg.write_csv(path, proposals, reg.REVIEW_FIELDS)
    typer.echo(json.dumps({"names_without_landlord": len(names), "proposals": len(proposals), "file": str(path)}))


@app.command()
def score() -> None:
    """Place each profiled landlord among similar landlords, by the rules in config/scoring.toml."""
    from landlords import area
    from landlords import score as score_

    s = load_settings()
    area.build(s)
    typer.echo(json.dumps(score_.run(s)))


@app.command()
def build() -> None:
    """Write the pages to data/site/: a profile for each landlord, the list, and the method page."""
    from landlords import area, site
    from landlords import score as score_

    s = load_settings()
    area.build(s)
    score_.run(s)
    typer.echo(json.dumps(site.build(s)))


@app.command()
def serve(port: int = typer.Option(8000), host: str = typer.Option("127.0.0.1", help="local only by default")) -> None:
    """Serve data/site/ on this computer only (nothing is deployed)."""
    import functools
    import http.server

    folder = load_settings().data_dir / "site"
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(folder))
    typer.echo(f"http://{host}:{port}/")
    http.server.ThreadingHTTPServer((host, port), handler).serve_forever()


@app.command()
def check(strict: bool = typer.Option(True, help="exit 1 if any check fails")) -> None:
    """Every row matched to a landlord, ranges, reconciliation to published figures, coverage, and movers."""
    from landlords import checks

    report = checks.run(load_settings())
    for c in report["checks"]:
        typer.echo(f"{'ok  ' if c['ok'] else 'FAIL'} {c['name']}: {c['detail']}")
    typer.echo(f"Report: {report['file']}")
    raise typer.Exit(1 if strict and not all(c["ok"] for c in report["checks"]) else 0)
