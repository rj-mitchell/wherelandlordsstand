# Where Landlords Stand

**How England's larger social landlords compare, from the regulator's and the Housing Ombudsman's published data.**
(A working title: docs/DECISIONS.md, 1.)

Where Landlords Stand will profile every social landlord in England with 1,000 or more homes, about 360 housing
associations, councils and for-profit providers, and show where each stands against similar landlords. It is for
people deciding whether to bid for or accept a social home: someone who sees a landlord named on a lettings advert and
wants to know, on a phone and in under a minute, what that landlord is like. Every figure shown links to the
published file and year it comes from.

It is planned as a project of the Where They Stand Foundation, like Where MPs Stand, Where Councils Stand and Where
Countries Stand (same licence, same author).

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

Next: the bidder tools (phase 3): search, compare, area pages and a rights page, tested with applicants.

| File | What it is |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Product decisions. They override everything else. **All proposed, none confirmed yet.** |
| [`docs/DATA.md`](docs/DATA.md) | The sources, what is really in each file, how it is loaded, the checks, and open questions |
| [`docs/METHOD.md`](docs/METHOD.md) | How landlords are compared, with a worked example and questions for the reviewer |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Fetching, loading, matching names and checking |

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
uv run landlords build            # peer groups, bands and the pages, in data/site/
uv run landlords serve            # http://127.0.0.1:8000/, on this computer only
uv run pytest
```

## Licence

Code: AGPL-3.0, as the sibling sites. The regulator's data is under the Open Government Licence v3.0. The Housing
Ombudsman's reuse terms are being confirmed; its data is used meanwhile (docs/DECISIONS.md, 9).
