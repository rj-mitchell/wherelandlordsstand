"""Hiding a landlord while a concern about it is decided (the charity's impartiality policy, 7.3; docs/DECISIONS.md, 17).

`landlords hide landlords/<slug>/ --note "…"` hides one landlord's page from that moment, and `landlords unhide`
shows it again. The Where They Stand sites' shared package keeps the record of what is hidden, the note and when
(wts-core, ``Replies.hide``). This file is what "hidden" means on this site, where the pages are built ahead of time.

While a landlord is hidden:

* its own page says "This page is hidden while a concern about it is decided." and then the owner's note, under its
  name, in place of its figures and of any statement beside them;
* it is left out of the list of all landlords, of search (names.json), of the compare page (its data file goes), of
  the table on each council area's page, of the sitemap, and of the downloads (its rows go from each CSV file);
* statements beside its page are not shown, nor one on an area's page that speaks for it, and none is taken or
  published for it (src/landlords/replies.py and statements.py).

Like a statement (src/landlords/statements.py), this is written into the pages already built, at once: the command
edits the live pages and every kept build (``refresh``), and a new build is edited the same way when it is made
(``apply``, called by ``site.build``). A build is never made again for it: the live pages may be older than the
data now loaded, and nothing new goes live without the owner's approval (docs/DECISIONS.md, 12).

Showing it again puts back exactly what was there. Before a file is changed, the file as it was built is kept in
``data/hidden-originals/``, outside the pages that are served; whatever is hidden is always worked out afresh from
those, so two landlords can be hidden and shown again in any order. Statements published or withdrawn meanwhile
are written into the pages put back.

What an edit cannot reach is left as it was built, and said in docs/OPERATIONS.md: another landlord's page that
names this one (a merger, a group's grade) still does, and its link leads to the note; each landlord's bands were
worked out among similar landlords that include it; the press page's count of landlords includes it.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import re
import shutil
from hashlib import sha256
from pathlib import Path

from landlords.config import Settings, load_toml

ORIGINALS = "hidden-originals"        # in the data folder, beside the builds: never served
LANDLORD = re.compile(r"^landlords/([a-z0-9][a-z0-9-]*)/$")
# the CSV files of the downloads, and the columns that say whose a row is
DOWNLOADS = {"landlords.csv": ("landlord_id",), "bands.csv": ("landlord_id",),
             "tenant-satisfaction-measures.csv": ("landlord_id",), "regulatory-judgements.csv": ("landlord_id",),
             "homes-by-area.csv": ("landlord_id",), "ombudsman.csv": ("landlord_id", "profile_id")}


def originals(settings: Settings, folder: Path) -> Path:
    """Where the files of one set of pages are kept as they were built, while something in them is hidden."""
    try:
        key = folder.resolve().relative_to(settings.data_dir.resolve()).as_posix().replace("/", "__")
    except ValueError:                       # a set of pages built somewhere else (a test, a look by hand)
        key = "elsewhere-" + sha256(str(folder.resolve()).encode()).hexdigest()[:16]
    return settings.data_dir / ORIGINALS / key


def forget(settings: Settings, folder: Path) -> None:
    """A set of pages has gone, or is about to be built again from nothing: so do the files kept for it."""
    shutil.rmtree(originals(settings, folder), ignore_errors=True)
    with contextlib.suppress(OSError):          # and the folder they were in, once nothing of any set is kept
        (settings.data_dir / ORIGINALS).rmdir()


def hidden_now(settings: Settings) -> list[dict]:
    """The landlords hidden now, longest hidden first: each a ``slug`` and the ``note`` shown in its place."""
    from landlords.replies import open_replies

    if not settings.state_db.exists():
        return []
    return [{"slug": found[1], "note": h["note"]} for h in open_replies(settings).all_hidden()
            if (found := LANDLORD.match(h["item"]))]


class _Pages:
    """One set of pages as they were built, and what they are to be while something is hidden."""

    def __init__(self, folder: Path, kept: Path):
        self.folder, self.kept = folder, kept
        self.now: dict[str, str | None] = {}            # address -> the text to serve; None: no such file

    def built(self, address: str) -> str | None:
        """A file as it was built: from the copy kept when it was first changed, else as it is."""
        for path in (self.kept / address, self.folder / address):
            if path.is_file():
                return path.read_text()
        return None

    def read(self, address: str) -> str | None:
        return self.now[address] if address in self.now else self.built(address)

    def areas(self) -> list[str]:
        return sorted(p.relative_to(self.folder).as_posix() for p in self.folder.glob("areas/*/index.html"))


def _csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue()


def _leave_out(pages: _Pages, slug: str, note: str, w: dict) -> None:
    """Work out one set of pages without one landlord."""
    from landlords.site import esc, fill

    own = f"landlords/{slug}/index.html"
    page = pages.read(own)
    if page is not None:
        # its own page: the note in place of its figures, under its name, in the page as it was built
        name = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        words = esc(w["hidden"]["text"])
        body = (f"<h1>{name[1] if name else esc(slug)}</h1><p>{words}</p><p>{esc(note)}</p>")
        page = re.sub(r'(<main id="main" class="wrap">).*?(</main>)', lambda m: m[1] + body + m[2], page, count=1,
                      flags=re.S)
        page = re.sub(r'(<meta (?:name="description"|property="og:description") content=")[^"]*(">)',
                      lambda m: m[1] + words + m[2], page)
        pages.now[own] = page
    if pages.read(f"data/landlords/{slug}.json") is not None:          # the compare page's data
        pages.now[f"data/landlords/{slug}.json"] = None

    names = pages.read("names.json")                                    # search, and the compare page's box
    if names is not None:
        pages.now["names.json"] = json.dumps([e for e in json.loads(names) if e.get("s") != slug],
                                             separators=(",", ":"))

    index = pages.read("index.html")                                    # the list of all landlords, and its count
    item = re.compile(rf'<li><a href="landlords/{re.escape(slug)}/index\.html">[^<]*</a></li>')
    if index is not None and item.search(index):
        listed = len(re.findall(r'<li><a href="landlords/[a-z0-9-]+/index\.html">', index))
        index = item.sub("", index, count=1)
        index = re.sub(r'<h3>[^<]*</h3><ul class="az"></ul>', "", index)        # a letter with nobody left under it
        index = index.replace(fill(w["search"]["count"], count=listed), fill(w["search"]["count"], count=listed - 1), 1)
        pages.now["index.html"] = index

    row = re.compile(rf'<tr role="row"><td role="cell"><a href="\.\./\.\./landlords/{re.escape(slug)}/index\.html">'
                     r".*?</tr>", re.S)
    fewer: list[str] = []
    for address in pages.areas():                                       # each council area's table, and its count
        area = pages.read(address)
        if area is None or not row.search(area):
            continue
        listed = len(re.findall(r'<tr role="row"><td role="cell"><a href="\.\./\.\./landlords/', area))
        area = row.sub("", area, count=1)
        area = area.replace(fill(w["area"]["intro"], count=listed), fill(w["area"]["intro"], count=listed - 1))
        if "</a> *</td>" not in area:                                   # no council's total left to explain
            area = area.replace(f'<p class="hint">* {esc(w["area"]["council_note"])}</p>', "", 1)
        pages.now[address] = area
        fewer.append(address.split("/")[1])
    areas = pages.read("areas/index.html")
    if areas is not None and fewer:
        for area_slug in fewer:
            areas = re.sub(rf'(<a href="{re.escape(area_slug)}/index\.html">[^<]*</a> <span class="hint">\()(\d+)(\))',
                           lambda m: f"{m[1]}{int(m[2]) - 1}{m[3]}", areas, count=1)
        pages.now["areas/index.html"] = areas

    sitemap = pages.read("sitemap.xml")
    if sitemap is not None:
        pages.now["sitemap.xml"] = re.sub(rf"<url><loc>[^<]*/landlords/{re.escape(slug)}/</loc></url>", "", sitemap)

    # the downloads: its rows go from each file, and the downloads page says how many rows are left
    landlords = pages.read("data/landlords.csv")
    if landlords is None:
        return
    table = list(csv.reader(io.StringIO(landlords)))
    where = {name: n for n, name in enumerate(table[0])}
    ids = {r[where["landlord_id"]] for r in table[1:] if r[where["page"]] == f"landlords/{slug}/"}
    listing = pages.read("data/index.html")
    for name, columns in DOWNLOADS.items():
        text = pages.read(f"data/{name}")
        if text is None or not ids:
            continue
        table = list(csv.reader(io.StringIO(text)))
        at = [table[0].index(c) for c in columns if c in table[0]]
        kept = [table[0], *(r for r in table[1:] if not any(r[i] in ids for i in at))]
        if len(kept) == len(table):
            continue
        text = _csv(kept)
        pages.now[f"data/{name}"] = text
        if listing is not None:
            listing = re.sub(rf'(<a href="{re.escape(name)}">{re.escape(name)}</a> <span class="hint">\()[^)]*(\))',
                             lambda m, text=text, kept=kept: f"{m[1]}{len(kept) - 1:,} rows, "
                                                             f"{len(text.encode()) // 1024 + 1} KB{m[2]}",
                             listing, count=1)
    if listing is not None and listing != pages.read("data/index.html"):
        pages.now["data/index.html"] = listing


def apply(settings: Settings, folder: Path, hidden: list[dict] | None = None, w: dict | None = None) -> int:
    """Make one set of pages show what is hidden now as hidden, and everything else as it was built. Returns how
    many files were written. A hidden landlord's page never shows its figures on the way: a file is changed in one
    step, from what it was to what it should be."""
    from landlords import statements

    hidden = hidden_now(settings) if hidden is None else hidden
    w = w or load_toml("wording.toml")
    kept = originals(settings, folder)
    pages = _Pages(folder, kept)
    for one in hidden:
        _leave_out(pages, one["slug"], one["note"], w)
    # Statements published or withdrawn since a page was kept or built are written into it before it is put in
    # place, so no page is ever served with a statement that has since come down
    where = statements.placements(statements.published(settings))

    def as_served(address: str, text: str) -> str:
        if re.fullmatch(r"(landlords|areas)/[^/]+/index\.html", address):
            return statements.filled(text, address.removesuffix("index.html"), where, folder, w)
        return text

    written = 0
    was_kept = sorted(p.relative_to(kept).as_posix() for p in kept.rglob("*") if p.is_file()) if kept.exists() else []
    for address in was_kept:                              # no longer changed: put back as it was built
        if address not in pages.now:
            (folder / address).parent.mkdir(parents=True, exist_ok=True)
            _write(folder / address, as_served(address, (kept / address).read_text()))
            (kept / address).unlink()
            written += 1
    for address, text in pages.now.items():
        path = folder / address
        if not (kept / address).is_file():                # keep it as it was built, before the first change
            (kept / address).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, kept / address)
        if text is None:
            if path.exists():
                path.unlink()
                written += 1
        elif not path.is_file() or path.read_text() != as_served(address, text):
            _write(path, as_served(address, text))
            written += 1
    if kept.exists() and not any(p.is_file() for p in kept.rglob("*")):
        forget(settings, folder)
    return written


def _write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)                       # a reader sees the file before or after, never half of it


def refresh(settings: Settings) -> dict:
    """Show what is hidden now as hidden in every set of pages that can be live, now."""
    from landlords.statements import folders

    hidden = hidden_now(settings)
    return {"pages_changed": sum(apply(settings, f, hidden) for f in folders(settings))}
