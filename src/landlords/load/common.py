"""Shared pieces for the loaders: reading spreadsheets, codes, published markers, and the staging store."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from python_calamine import CalamineWorkbook

from landlords.config import Settings
from landlords.fetch import entries, latest


class LayoutChanged(RuntimeError):
    """A published file no longer has the columns or sheets a loader expects. Stop and look."""


class MissingFile(RuntimeError):
    """No file has been fetched for a source the loader needs."""


# Markers the regulator puts in place of a value. They are kept as a status, never turned into a number.
MARKERS = {
    "[x]": "blank",          # left blank by the landlord
    "[z]": "not required",   # a response was not required
    "[u]": "undefined",      # zero denominator: not applicable, not zero
    "[s]": "suppressed",     # fewer than 50 surveys by that method
    "[e]": "excluded",       # removed by the regulator after review
}


def code(value: Any) -> str:
    """A landlord's regulator code as text. Spreadsheets store numeric codes as numbers (4747.0)."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def text(value: Any) -> str:
    """Cell text with runs of spaces collapsed, as names are often published with stray spaces."""
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()


def parse_value(value: Any) -> tuple[float | None, str]:
    """A published cell as (number, status). Status is "value", a marker's meaning, "empty" or "text"."""
    if isinstance(value, bool):
        return None, "text"
    if isinstance(value, int | float):
        return float(value), "value"
    s = str(value or "").strip()
    if not s:
        return None, "empty"
    marker = MARKERS.get(s.lower())
    if marker:
        return None, marker
    try:
        return float(s.replace(",", "")), "value"
    except ValueError:
        return None, "text"


def as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def require(header: Iterable[str], needed: Iterable[str], where: str) -> None:
    missing = [c for c in needed if c not in set(header)]
    if missing:
        raise LayoutChanged(f"{where}: expected columns not found: {missing}")


# Reading files ---------------------------------------------------------------------------------------------------


def source_file(settings: Settings, source: str, role: str, period: str | None = None,
                ext: str | None = None) -> dict:
    note = latest(settings, source, role, period, ext)
    if not note:
        raise MissingFile(f"no {source} {role} file{' for ' + period if period else ''}: run `landlords fetch {source}`")
    return note


def sheet_table(path: str | Path, sheet: str, first_header: str | tuple[str, ...]) -> tuple[list[str], list[list]]:
    """A sheet's table: the header row (found by its first cell) and the rows below it, empty rows dropped.

    The regulator's sheets start with a title, notes and links before the table, and the number of those lines
    changes between releases, so the header is found rather than assumed.
    """
    wb = CalamineWorkbook.from_path(str(path))
    if sheet not in wb.sheet_names:
        raise LayoutChanged(f"{Path(path).name}: sheet {sheet!r} not found (sheets: {wb.sheet_names})")
    rows = wb.get_sheet_by_name(sheet).to_python()
    firsts = (first_header,) if isinstance(first_header, str) else first_header
    for i, row in enumerate(rows):
        if row and text(row[0]) in firsts:
            header = [text(c) for c in row]
            body = [r for r in rows[i + 1:] if any(str(c).strip() for c in r)]
            return header, body
    raise LayoutChanged(f"{Path(path).name}: no header row starting {firsts} in sheet {sheet!r}")


def zip_csv(path: str | Path, name_contains: str | tuple[str, ...]) -> tuple[list[str], list[dict]]:
    """A CSV in a zip, found by part of its name (any of several). UTF-8, or Windows-1252 where a file isn't UTF-8
    (some of the regulator's 2025/26 files)."""
    wanted = (name_contains,) if isinstance(name_contains, str) else name_contains
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if any(w.lower() in n.lower() for w in wanted)]
        if len(names) != 1:
            raise LayoutChanged(f"{Path(path).name}: expected one file named like {wanted}, found {names}")
        raw = z.read(names[0])
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    return [h.strip() for h in reader.fieldnames or []], [{k.strip(): v for k, v in r.items()} for r in rows]


def has_zip_file(path: str | Path, name_contains: str) -> bool:
    with zipfile.ZipFile(path) as z:
        return any(name_contains.lower() in n.lower() for n in z.namelist())


# The staging store -----------------------------------------------------------------------------------------------


def write_table(settings: Settings, name: str, rows: list[dict], schema: pa.Schema) -> Path:
    settings.staging_dir.mkdir(parents=True, exist_ok=True)
    path = settings.staging_dir / f"{name}.parquet"
    table = pa.Table.from_pylist(rows, schema=schema)
    tmp = path.with_suffix(".parquet.part")
    pq.write_table(table, tmp, compression="zstd")
    tmp.rename(path)
    return path


def read_table(settings: Settings, name: str) -> list[dict]:
    path = settings.staging_dir / f"{name}.parquet"
    if not path.exists():
        raise MissingFile(f"staging table {name} not built: run `landlords load`")
    return pq.read_table(path).to_pylist()


def file_ref(note: dict) -> dict:
    """What every row carries so a figure can be traced to its file: the file's hash and the period."""
    return {"source_file": note["sha256"], "period": note["period"]}


def record_sources(settings: Settings, notes: list[dict]) -> None:
    """Keep the notes of the files a build read, in staging/sources.json, keyed by hash. The licence comes from
    config/sources.toml as it is now, not as it was when the file was fetched, so a change to the terms reaches the
    pages."""
    licences = {(e.source, e.role, e.period): e.licence for e in entries()}
    path = settings.staging_dir / "sources.json"
    known = json.loads(path.read_text()) if path.exists() else {}
    for n in notes:
        known[n["sha256"]] = {k: n[k] for k in ("source", "role", "period", "title", "url", "page", "publisher",
                                                "licence", "fetched_at", "file")}
        known[n["sha256"]]["licence"] = licences.get((n["source"], n["role"], n["period"]), n["licence"])
    path.write_text(json.dumps(known, indent=2, sort_keys=True) + "\n")
