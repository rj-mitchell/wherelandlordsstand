# Where Landlords Stand

**How England's social landlords look after their tenants, from what the Regulator of Social Housing and the Housing
Ombudsman publish.**

[wherelandlordsstand.com](https://wherelandlordsstand.com) · Status: Alpha

For people deciding whether to bid for or accept a social home: someone who sees a landlord named on a lettings advert
can find out, on a phone and in under a minute, what that landlord is like. It covers every council, housing
association and for-profit landlord in England with 1,000 or more homes (363 of them), and shows where each stands
among similar landlords. Every figure links to the published file and year it comes from.

A Where They Stand project. Where They Stand is applying to register as a charity in England and Wales
([wheretheystand.uk](https://wheretheystand.uk)).

> Where Landlords Stand is independent. It is not affiliated with or endorsed by the Regulator of Social Housing, the
> Housing Ombudsman Service or any landlord.

## Status

6 November 2026. **Public alpha** (docs/DECISIONS.md, 12): open to everyone and working, still being tested. New
pages from the weekly update go live only when the owner approves them by email, and search engines are kept out
until launch. Three gates stand between alpha and beta: a review of the method by a housing-data reviewer
([`docs/METHOD.md`](docs/METHOD.md)), testing with applicants ([`docs/USER-TESTING.md`](docs/USER-TESTING.md)), and an
adviser's sign-off of the wording. What is left is in [`docs/LAUNCH.md`](docs/LAUNCH.md).

What it has:

- **a page for each landlord**, led by a "Before you bid" card: the regulator's grade, bands among similar landlords
  with changes since last year, the Ombudsman's figures and the safety checks (Tenant Satisfaction Measures 2025/26
  and 2024/25; the Ombudsman's 2025-26 and 2024-25 tables). Static HTML, no JavaScript, under 20 KB a page;
- **search** by any name a landlord goes by (advert, short, former, ALMO), in the browser; a name that isn't covered
  gets an explanation and a way in through council areas;
- **area pages** for 296 council areas, listing the landlords that own homes there;
- **compare** up to three landlords side by side (needs JavaScript; each landlord's page has the same figures without
  it);
- **your rights**: offers and reviews, Awaab's Law, complaints and the Ombudsman, the regulator, STAIRs and FOI,
  written from official sources, each section dated with a date to check it again (`config/rights.toml`);
- **data downloads**: CSV files whose rows carry their source and licence;
- **corrections and problems**, a form that works without JavaScript, for anything the site says about a landlord
  (its figures, labels, groupings and connections), with a public log of our fixes, and a count of searches that found
  nothing, so names can be added;
- **if you're named**: for landlords the site names, the charity's routes for putting something right, and a
  statement in their own words shown beside what the site says about them (docs/DECISIONS.md, 15);
- about, terms, privacy, accessibility (axe-core, WCAG 2.2 AA, no failures), press, status and "not found" pages; one switch that lets
  search engines in (`[site] launched`); off-site backups; and a watch for new releases.

A weekly `landlords update` builds new pages into a new folder and emails the owner a link to approve them; the
approval page's Undo button, or `landlords rollback`, puts back the pages before.

## In the family

- **Where its code came from.** Written for this site: it has no AI and shares no engine with its sister sites. It
  shares their licence, server, typeface and look, and the family's binding (the endorsement, the footer shelf, the
  icons and link card) comes from the charity's family kit, copied into `src/landlords/family/`
  ([`docs/DESIGN.md`](docs/DESIGN.md)).
- **Where it runs.** On the charity's shared server, in `/opt/wherelandlordsstand`, behind the front door in Where MPs
  Stand's checkout. [`docs/DEPLOY.md`](docs/DEPLOY.md) has this site's steps and links to Where MPs Stand's
  [`docs/HOSTING.md`](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md) for the shared server.
- **Links to and from sister sites.** Every page links to wheretheystand.uk and every sister site (Where MPs Stand,
  Where Councils Stand, Where Countries Stand, Where Lives Stand) through the endorsement and the footer shelf. A
  council's page, and each council area's page, link to the council's page on
  [Where Councils Stand](https://wherecouncilsstand.com) where it covers the council: both sites use the ONS (GSS)
  code, and `data_static/councils_covered.csv`, refreshed by `landlords sister-councils`, says which councils it
  covers. Where Councils Stand's council pages link back here.

## Documents

| File | What it is |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Product decisions. They override everything else |
| [`docs/DATA.md`](docs/DATA.md) | The sources, what is really in each file, how it is loaded, the checks, and open questions |
| [`docs/METHOD.md`](docs/METHOD.md) | How landlords are compared, with a worked example and questions for the reviewer |
| [`docs/DESIGN.md`](docs/DESIGN.md) | The look: the family's binding, and this site's own volume in roof slate |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Fetching, loading, matching names, checking, building, updating and publishing |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | This site's steps on the shared server |
| [`docs/LAUNCH.md`](docs/LAUNCH.md) | The checklist for beta and launch: what is done, and what needs the owner, reviewers or the server |
| [`docs/USER-TESTING.md`](docs/USER-TESTING.md) | The plan for testing with applicants |

## How it works

```
 config/sources.toml ─► landlords fetch ─► data/raw/<source>/<sha256>.<ext> + .note.json   (never overwritten)
   GOV.UK Content API          │
   Ombudsman pages             ▼
                         landlords load ─► data/staging/*.parquet: tsm, tsm_survey, tsm_coverage, grades,
                               │            providers, groups, stock_area, ombudsman   (each row: file hash, period)
                               ▼
 data_static/landlords.csv ◄─ landlords register   (new landlords; names publishers print beside a code)
 data_static/aliases.csv   ◄─ landlords match --accept   (hand-checked names: Ombudsman, adverts)
                               │
                               ▼
                         landlords check ─► owners, landlord_area (companies rolled up to profiled landlords),
                                             check-report.json, change-report.json
```

* **One key.** The regulator's code (L4203, 00GL, 5069) is every landlord's id, as in the TSM data and judgements.
* **Groups.** TSMs are often submitted by a group's parent while its homes, and some Ombudsman cases, belong to
  subsidiaries. Each registered company is linked to its nearest profiled parent.
* **Names.** Adverts rarely use registered names, so short, trading, former and logo names are kept as aliases, each
  pointing to one landlord. A name is never matched by guesswork: anything not exact goes to a review file.
* **Pages.** `landlords score` puts each landlord among similar ones (`config/scoring.toml`), and `landlords build`
  writes static HTML to `data/site/`: every sentence from `config/*.toml`, aiming at a reading age of about 9; no
  scripts and nothing from other sites on content pages, and a 100 KB budget a page, both checked by the tests; the
  stylesheets, scripts, fonts and icons under `/assets/` with fingerprinted names.
* **Being a good citizen.** One request at a time, at least a second apart, with a user agent that names the project.
  A published file's address is fetched once.

## Try it

You need [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run landlords fetch            # about a minute; data/raw/
uv run landlords load             # data/staging/
uv run landlords check            # the gate: every row matched, published figures reproduced
uv run landlords build            # peer groups, bands and every page, in data/site/
uv run landlords serve            # the site and its API at http://127.0.0.1:8000/, on this computer only
uv run pytest
```

GitHub Actions (`.github/workflows/ci.yml`) runs ruff and the tests on every pull request; builds the real pages from
the publishers' files (kept in the Actions cache, fetched again only when `config/sources.toml` changes), runs the
tests on them and checks them with axe-core (`scripts/a11y.mjs`); and builds the server's image.

## Known limitations

- The method has not yet been reviewed by a housing-data expert, the tools have not been tested with applicants, and
  the wording has not been signed off by an adviser (the three gates for beta).
- Only landlords with 1,000 or more homes are covered, because smaller ones don't have to publish tenant survey
  results.
- The Housing Ombudsman's reuse terms are still being confirmed; its figures are used meanwhile
  (docs/DECISIONS.md, 9). From October 2025 its figures are not comparable with earlier years.
- Tenants were asked in different ways (phone, online, post), which can change the results; a landlord's page says
  when it asked mostly in a different way from similar landlords.
- Search and compare need JavaScript; everything else works without it.

## Licence

Code: AGPL-3.0 ([LICENSE](LICENSE)). Text written by the site, and its own work (bands, peer groups, homes by council
area, the method): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (docs/DECISIONS.md, 11). Data: each
publisher's terms: the regulator's under the Open Government Licence v3.0; the Housing Ombudsman's while its terms are
confirmed. The name and mark are not covered.
