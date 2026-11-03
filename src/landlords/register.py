"""The name register: ``data_static/landlords.csv`` and ``data_static/aliases.csv``.

``landlords.csv`` has one row for every body on the regulator's register, and for every former provider that a
loaded file still names. Its ``id`` is the regulator's code, as the TSM data and judgements give it, and it is the
key every table joins on. Only landlords with 1,000 or more homes (those that submit TSMs) are profiled; they have a
``display_name`` and a ``slug``. A slug never changes once published.

``aliases.csv`` holds every other name a landlord goes by: names publishers print, trading and short names, former
names, and the names of bodies that manage a council's homes (ALMOs and TMOs). Each alias points to one landlord.

`landlords register` builds and refreshes ``landlords.csv`` from the loaded tables. It adds rows and refreshes the
facts that come from the regulator (legal name, type, area, group), and it never removes a row or changes a
display name, slug, status or successor that is already there: those are edited by hand.

`landlords match` proposes landlords for published names that have no code (the Ombudsman's) into a review file.
Nothing is accepted without a person marking it so (`landlords match --accept`).
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from landlords.config import STATIC_DIR

LANDLORDS_CSV = STATIC_DIR / "landlords.csv"
ALIASES_CSV = STATIC_DIR / "aliases.csv"
PUBLISHED_SLUGS = STATIC_DIR / "published_slugs.txt"

LANDLORD_FIELDS = ["id", "legal_name", "display_name", "type", "gss", "group_id", "registration_date", "status",
                   "successor_id", "successor_date", "profiled", "slug"]
ALIAS_FIELDS = ["landlord_id", "alias", "kind", "source", "valid_to"]
ALIAS_KINDS = {"published", "trading", "short", "former", "group", "managing body", "logo label"}

TYPES = {"local authority": "council", "non-profit": "housing association", "profit": "for-profit"}

# Words dropped when names are compared (the brief: lower case, "&" to "and", drop Limited, Ltd, Group, Housing
# Association). "The", "plc" and "CIC" are dropped too, and punctuation is removed.
_DROP = re.compile(r"\b(limited|ltd|plc|cic|the|group|housing association)\b")


def normalise(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ").replace("’", "'")
    s = re.sub(r"\(the\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = _DROP.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def display_name(legal_name: str) -> str:
    """A first display name from a legal name: legal suffixes removed, "(The)" moved to the front.

    These are a starting point to be checked by hand (docs/DATA.md).
    """
    s = re.sub(r"\s+", " ", legal_name).strip()
    if s.endswith("(The)"):
        s = "The " + s[:-5].strip()
    s = re.sub(r"\s*\b(Limited|Ltd\.?|PLC|plc|CIC)$", "", s).strip()
    return s


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    s = re.sub(r"^the\s+", "", s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# Reading and writing ---------------------------------------------------------------------------------------------


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.part")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    tmp.rename(path)


def landlords() -> dict[str, dict]:
    return {r["id"]: r for r in read_csv(LANDLORDS_CSV)}


def aliases() -> list[dict]:
    return read_csv(ALIASES_CSV)


def _exact(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


class Resolver:
    """Finds the landlord a published name refers to, in tiers, stopping at the first tier with an answer:

    1. an alias in aliases.csv, exactly (ignoring case and spacing);
    2. a legal name, exactly, among active landlords;
    3. a legal name, exactly, among all landlords, including former ones;
    4. an alias, normalised (``normalise``);
    5. a legal name, normalised, among active landlords;
    6. a legal name, normalised, among all landlords.

    Exact names come first so that a short alias ("Clarion") can't capture a different company whose full name
    normalises the same way ("Clarion Housing Association Limited"). If a tier finds two landlords, the name is left
    unmatched for a person to decide (`landlords match`), rather than falling through to a looser tier.
    """

    HOW = ["alias", "exact name", "exact name (former)", "normalised alias", "normalised name",
           "normalised name (former)"]

    def __init__(self) -> None:
        self.tiers: list[dict[str, set[str]]] = [defaultdict(set) for _ in range(6)]
        for a in aliases():
            self.tiers[0][_exact(a["alias"])].add(a["landlord_id"])
            self.tiers[3][normalise(a["alias"])].add(a["landlord_id"])
        for lid, r in landlords().items():
            for n in [r["legal_name"]] + ([r["display_name"]] if r.get("display_name") else []):
                if r["status"] == "active":
                    self.tiers[1][_exact(n)].add(lid)
                    self.tiers[4][normalise(n)].add(lid)
                self.tiers[2][_exact(n)].add(lid)
                self.tiers[5][normalise(n)].add(lid)

    def resolve(self, name: str) -> tuple[str, str]:
        """(landlord id, how it was found), or ("", why not)."""
        for i, tier in enumerate(self.tiers):
            found = tier.get(_exact(name) if i < 3 else normalise(name), set())
            if len(found) == 1:
                return next(iter(found)), self.HOW[i]
            if len(found) > 1:
                return "", f"ambiguous: {sorted(found)}"
        return "", "no match"


def ambiguous_names() -> dict[str, set[str]]:
    """Normalised names that point to more than one landlord."""
    found: dict[str, set[str]] = defaultdict(set)
    for a in aliases():
        found[normalise(a["alias"])].add(a["landlord_id"])
    for lid, r in landlords().items():
        if r.get("display_name"):
            found[normalise(r["display_name"])].add(lid)
    return {k: v for k, v in found.items() if len(v) > 1}


# Building the register ---------------------------------------------------------------------------------------------


@dataclass
class RegisterResult:
    added: int
    refreshed: int
    total: int
    profiled: int
    aliases_added: int


def _ultimate_parent(lid: str, parents: dict[str, str]) -> str:
    seen = set()
    while parents.get(lid) and lid not in seen:
        seen.add(lid)
        lid = parents[lid]
    return lid


def build(settings) -> RegisterResult:
    from landlords.load.common import read_table

    providers = read_table(settings, "providers")
    groups = read_table(settings, "groups")
    coverage = read_table(settings, "tsm_coverage")
    grades = read_table(settings, "grades")
    stock = read_table(settings, "stock_area")
    tsm_rows = read_table(settings, "tsm")

    existing = landlords()
    parents = {g["landlord_id"]: g["parent_id"] for g in groups if g["parent_id"]}
    # Profiled: the landlords in the latest TSM year (1,000 or more homes; docs/DECISIONS.md, 3).
    latest = max(c["period"] for c in coverage)
    profiled = {c["landlord_id"] for c in coverage if c["period"] == latest}
    rows: dict[str, dict] = {}

    for p in providers:
        lid = p["landlord_id"]
        top = _ultimate_parent(lid, parents)
        rows[lid] = {"id": lid, "legal_name": p["name"], "type": TYPES.get(p["designation"].lower(), ""),
                     "gss": p["gss"], "group_id": top if top != lid else "",
                     "registration_date": p["registration_date"].isoformat() if p["registration_date"] else "",
                     "status": "active"}

    # Former providers still named in loaded files: their name from the most recent mention.
    mentions: dict[str, tuple[date, str]] = {}
    for g in grades:
        d = g["publication_date"] or date.min
        if g["landlord_id"] not in rows and (g["landlord_id"] not in mentions or d > mentions[g["landlord_id"]][0]):
            mentions[g["landlord_id"]] = (d, g["name_published"])
    for t in (tsm_rows, stock):
        for r in t:
            if r["landlord_id"] and r["landlord_id"] not in rows and r["landlord_id"] not in mentions:
                mentions[r["landlord_id"]] = (date.min, r["name_published"])
    for lid, (_, name) in mentions.items():
        rows[lid] = {"id": lid, "legal_name": name, "type": "", "gss": "", "group_id": "", "registration_date": "",
                     "status": "deregistered"}

    added = refreshed = 0
    out = []
    for lid in sorted(set(rows) | set(existing), key=lambda k: (rows.get(k, existing.get(k))["legal_name"].lower(), k)):
        new = rows.get(lid)
        old = existing.get(lid)
        if old and new:
            merged = {**old, **{k: new[k] for k in ("legal_name", "type", "gss", "group_id", "registration_date")}}
            if old.get("status") in ("", "active") and new["status"] != "active":
                merged["status"] = new["status"]
            refreshed += merged != old
        elif old:
            merged = old  # never remove a row
        else:
            merged = {**new, "display_name": "", "slug": "", "successor_id": "", "successor_date": ""}
            added += 1
        merged["profiled"] = "yes" if lid in profiled else (merged.get("profiled") if merged.get("slug") else "no")
        if merged["profiled"] == "yes" and not merged.get("display_name"):
            merged["display_name"] = display_name(merged["legal_name"])
        if merged["profiled"] == "yes" and not merged.get("slug"):
            merged["slug"] = slugify(merged["display_name"])
        out.append(merged)

    # A new slug that clashes with another gets the landlord's code added; published slugs are never touched.
    by_slug: dict[str, list[dict]] = defaultdict(list)
    for r in out:
        if r.get("slug"):
            by_slug[r["slug"]].append(r)
    published = set(read_lines(PUBLISHED_SLUGS))
    for slug, rs in by_slug.items():
        if len(rs) > 1:
            for r in rs:
                if slug not in published:
                    r["slug"] = f"{slug}-{r['id'].lower()}"
    write_csv(LANDLORDS_CSV, out, LANDLORD_FIELDS)

    aliases_added = seed_published_aliases(settings, {r["id"]: r for r in out})
    return RegisterResult(added=added, refreshed=refreshed, total=len(out),
                          profiled=sum(r["profiled"] == "yes" for r in out), aliases_added=aliases_added)


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")]


def seed_published_aliases(settings, register: dict[str, dict]) -> int:
    """Add the names publishers print next to a landlord's code, where they differ from its legal name.

    These are not matches: the publisher gives the code. Names from the current files are kind "published";
    names only in the archived judgements, for a landlord whose name has since changed, are kind "former".
    """
    from landlords.load.common import read_table

    current = []
    for name, src in (("tsm", "Tenant Satisfaction Measures {period}"), ("stock_area", "Stock and rents {period}")):
        for r in read_table(settings, name):
            current.append((r["landlord_id"], r["name_published"], src.format(period=r["period"])))
    archive = []
    for g in read_table(settings, "grades"):
        label = "Regulatory judgements (archive, to March 2024)" if g["table"] == "archive" else \
            f"Regulatory judgements ({g['table']})"
        (archive if g["table"] == "archive" else current).append((g["landlord_id"], g["name_published"], label))

    have = {(a["landlord_id"], normalise(a["alias"])) for a in aliases()}
    rows = aliases()
    added = 0
    current_names = {(lid, normalise(n)) for lid, n, _ in current}
    for (lid, name, src), kind in [(c, "published") for c in current] + [(a, "former") for a in archive]:
        reg = register.get(lid)
        key = (lid, normalise(name))
        if not reg or not key[1] or key in have or key[1] == normalise(reg["legal_name"]):
            continue
        if kind == "former" and key in current_names:
            continue
        rows.append({"landlord_id": lid, "alias": name, "kind": kind, "source": src, "valid_to": ""})
        have.add(key)
        added += 1
    rows.sort(key=lambda a: (register.get(a["landlord_id"], {}).get("legal_name", "").lower(), a["landlord_id"],
                             a["kind"], a["alias"].lower()))
    write_csv(ALIASES_CSV, rows, ALIAS_FIELDS)
    return added


# Proposing matches for names without a code ---------------------------------------------------------------------------


REVIEW_FIELDS = ["name_published", "source", "candidate_id", "candidate_name", "candidate_type", "score", "accept",
                 "kind"]


def propose(names: list[tuple[str, str]], limit: int = 3,
            unregistered_parents: dict[str, list[str]] | None = None) -> list[dict]:
    """Candidate landlords for published names that the register can't place, best first. Nothing is accepted.

    ``unregistered_parents`` maps a parent company that isn't on the register (normalised name, from the stock
    return's group table) to its registered subsidiaries. The Ombudsman reports some groups under such a parent
    ("MHS Homes Ltd", parent of Heart of Medway Housing Association), so those subsidiaries are offered first.
    """
    from rapidfuzz import fuzz, process

    resolver = Resolver()
    reg = landlords()
    choices: dict[str, str] = {}  # normalised name -> landlord id (first seen)
    labels: dict[str, str] = {}
    for lid, r in reg.items():
        for n in (r["legal_name"], r.get("display_name", "")):
            if n:
                choices.setdefault(normalise(n), lid)
                labels.setdefault(normalise(n), n)
    for a in aliases():
        choices.setdefault(normalise(a["alias"]), a["landlord_id"])
        labels.setdefault(normalise(a["alias"]), a["alias"])
    keys = list(choices)
    out = []
    for name, source in names:
        n = normalise(name)
        if resolver.resolve(name)[0]:
            continue
        for lid in (unregistered_parents or {}).get(n, []):
            out.append({"name_published": name, "source": source, "candidate_id": lid,
                        "candidate_name": f"{reg[lid]['legal_name']} (its unregistered parent is {name!r})",
                        "candidate_type": reg[lid]["type"], "score": 100, "accept": "", "kind": "group"})
        for match, score, _ in process.extract(n, keys, scorer=fuzz.token_set_ratio, limit=limit * 3):
            lid = choices[match]
            if any(o["candidate_id"] == lid and o["name_published"] == name for o in out):
                continue
            out.append({"name_published": name, "source": source, "candidate_id": lid,
                        "candidate_name": f"{reg[lid]['legal_name']} (via {labels[match]!r})",
                        "candidate_type": reg[lid]["type"], "score": round(score), "accept": "", "kind": "published"})
            if sum(o["name_published"] == name for o in out) >= limit:
                break
    return out


def accept(review_file: Path) -> int:
    """Add the proposals marked ``accept = yes`` in a review file to aliases.csv."""
    rows = aliases()
    have = {(a["landlord_id"], normalise(a["alias"])) for a in rows}
    added = 0
    for r in read_csv(review_file):
        if r.get("accept", "").strip().lower() != "yes":
            continue
        kind = r.get("kind") or "published"
        if kind not in ALIAS_KINDS:
            raise ValueError(f"{review_file}: unknown alias kind {kind!r}")
        key = (r["candidate_id"], normalise(r["name_published"]))
        if key not in have:
            rows.append({"landlord_id": r["candidate_id"], "alias": r["name_published"], "kind": kind,
                         "source": r["source"], "valid_to": ""})
            have.add(key)
            added += 1
    write_csv(ALIASES_CSV, rows, ALIAS_FIELDS)
    return added
