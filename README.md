# Where Landlords Stand

**How England's larger social landlords compare, from the regulator's and the Housing Ombudsman's published data.**
At [wherelandlordsstand.com](https://wherelandlordsstand.com), in alpha.

Where Landlords Stand will profile every social landlord in England with 1,000 or more homes, about 360 housing
associations, councils and for-profit providers, and show where each stands against similar landlords. It is for
people deciding whether to bid for or accept a social home: someone who sees a landlord named on a lettings advert and
wants to know, on a phone and in under a minute, what that landlord is like. Every figure shown links to the
published file and year it comes from.

It is a project of [Where They Stand](https://wheretheystand.uk), which is applying to register as a charity in
England and Wales, like Where MPs Stand, Where Councils Stand and Where Countries Stand (same licence, same author).

> Where Landlords Stand is independent. It is not affiliated with or endorsed by the Regulator of Social Housing, the
> Housing Ombudsman Service or any landlord.

**Not deployed.** The code is public, like the sibling sites; the site goes live only when the owner says so.

## Status

Phase 1, the data spine. It:

- downloads each published file politely and keeps every version (`landlords fetch`);
- reads the Tenant Satisfaction Measures 2024/25, the regulator's judgements and gradings (current and archived),
  the register of providers, the 2025/26 stock data, and the Ombudsman's 2025-26 landlord tables into tidy tables
  (`landlords load`);
- keeps a register of every landlord and the names it goes by (`data_static/landlords.csv`, `aliases.csv`), and
  proposes matches for names that come without a code, for a person to accept (`landlords match`);
- checks every row against the register and the data against the figures the publishers print (`landlords check`).

On the data downloaded on 3 November 2026 the data reconciles with the regulator's and the Ombudsman's published
totals, and every row is matched to a landlord, which was the gate for phase 1. What is in each file, and what doesn't
fit, is in
[`docs/DATA.md`](docs/DATA.md).

Phase 2, profiles, is built and waiting for its gate, a review of the method by a housing-data reviewer
([`docs/METHOD.md`](docs/METHOD.md) has the method, a worked example and the questions for them). It adds:

- a second year (TSM 2023/24, the Ombudsman's 2024-25 tables), so profiles can show changes;
- peer groups, percentiles and bands, by the rules in `config/scoring.toml` (`landlords score`);
- a page for each of the 363 landlords, led by a "Before you bid" card: the regulator's grade, bands among similar
  landlords with changes since last year, the Ombudsman's figures and the safety checks. Every sentence comes from
  `config/wording.toml`, and every figure links to its file. Static HTML, no JavaScript, under 11 KB a page
  (`landlords build`), seen only on this computer (`landlords serve`).

Phase 3, the bidder tools, is built and waiting for its gate, testing with applicants
([`docs/USER-TESTING.md`](docs/USER-TESTING.md) is the plan):

- **search** by any name a landlord goes by (advert, short, former, ALMO), in the browser; a name that isn't covered
  gets an explanation (a registered landlord under 1,000 homes is named as such) and a way in through council areas;
- **area pages** for 296 council areas, listing the landlords that own homes there;
- **compare** up to three landlords side by side (needs JavaScript; each profile has the same figures without it);
- **your rights**: offers and reviews, Awaab's Law, complaints and the Ombudsman, the regulator, STAIRs and FOI,
  written from official sources, each section dated with a date to check it again (`config/rights.toml`);
- **data downloads**: CSV files whose rows carry their source and licence;
- **report a mistake**, a form that works without JavaScript, with a public log of our fixes; and a count of searches
  that found nothing, so names can be added (`landlords serve`, the small API in `src/landlords/api.py`);
- council profiles link to Where Councils Stand where it covers the council.

Ready for phase 4, launch, which happens only when the owner says: a weekly `landlords update` builds into a new
folder, `landlords publish` makes it live by hand, `landlords rollback` undoes it, and `deploy/` has the container,
timers and [`docs/DEPLOY.md`](docs/DEPLOY.md). It runs on the charity's shared server at wherelandlordsstand.com, in
alpha: public, but search engines are asked not to index it until the launch switch is on.

Phase 4, launch, is prepared: about, terms, accessibility and "not found" pages; an accessibility test (axe-core, WCAG
2.2 AA, no failures); one switch that takes the site out of test mode (`[site] launched`); off-site backups; and a
watch for new releases (TSM 2025/26 was loaded the day it came out). What is left needs people or the server: see
[`docs/LAUNCH.md`](docs/LAUNCH.md).

| File | What it is |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Product decisions. They override everything else. |
| [`docs/DATA.md`](docs/DATA.md) | The sources, what is really in each file, how it is loaded, the checks, and open questions |
| [`docs/METHOD.md`](docs/METHOD.md) | How landlords are compared, with a worked example and questions for the reviewer |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Fetching, loading, matching names, checking, updating and publishing |
| [`docs/USER-TESTING.md`](docs/USER-TESTING.md) | The plan for testing the bidder tools with applicants (phase 3's gate) |
| [`docs/DESIGN.md`](docs/DESIGN.md) | The look: a volume in the Where They Stand family, in roof slate |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Putting the site on the shared server, and releasing it |
| [`docs/LAUNCH.md`](docs/LAUNCH.md) | The launch checklist: what is done, and what needs the owner, reviewers or the server |

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

## Licence

Code: AGPL-3.0, as the sibling sites. Our own work on the site (text, bands, peer groups, homes by council area, the
method) is under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), as on Where MPs Stand. The regulator's
data is under the Open Government Licence v3.0. The Housing Ombudsman's reuse terms are being confirmed; its data is
used meanwhile (docs/DECISIONS.md, 9).
