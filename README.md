# Where Landlords Stand

[![CI](https://github.com/rj-mitchell/wherelandlordsstand/actions/workflows/ci.yml/badge.svg)](https://github.com/rj-mitchell/wherelandlordsstand/actions/workflows/ci.yml)

Where Landlords Stand shows how England's social landlords look after their tenants, using the figures the
Regulator of Social Housing and the Housing Ombudsman publish. It is written for people deciding whether to bid for
or accept a social home: someone who sees a landlord named on a lettings advert can look it up on a phone and see its
grade, how it compares with similar landlords, its complaints record and its safety checks. It covers every council,
housing association and for-profit landlord in England with 1,000 or more homes (363 of them), and every figure
links to the published file and year it comes from.

Live at [wherelandlordsstand.com](https://wherelandlordsstand.com). It is a Where They Stand project; Where They
Stand is applying to register as a charity in England and Wales ([wheretheystand.uk](https://wheretheystand.uk)).
The site is independent and is not affiliated with or endorsed by the Regulator of Social Housing, the Housing
Ombudsman Service or any landlord.

## Status

Public alpha: open to everyone and to search engines, and working, but still being tested (November 2026). New
pages from the weekly update go live only once the owner has approved them by email. Beta needs three things: a
review of the method by a housing-data reviewer, testing with people who bid for social homes, and an adviser's
sign-off of the wording. [docs/BETA.md](docs/BETA.md) tracks them and the other open items.

Known limitations:

- Only landlords with 1,000 or more homes are covered, because smaller ones don't have to publish tenant survey
  results.
- The Housing Ombudsman's reuse terms are still being confirmed; its figures are used meanwhile. From October 2025
  its figures are not comparable with earlier years.
- Tenants were surveyed in different ways (phone, online, post), which can change the results. A landlord's page
  says when it surveyed mostly in a different way from similar landlords.
- Search and compare need JavaScript; everything else works without it.

## What it does

- A page for each landlord, led by a "Before you bid" card: the regulator's consumer grade, bands among similar
  landlords with changes since last year, the Ombudsman's figures and the building safety checks.
- Search by any name a landlord goes by (advert, short, former or ALMO name). A name that isn't covered gets an
  explanation and a way in through council areas.
- A page for each of 296 council areas, listing the landlords that own homes there.
- A side-by-side comparison of up to three landlords.
- A rights page on offers and reviews, Awaab's Law, complaints, the regulator and access to information, written
  from official sources (`config/rights.toml`).
- CSV downloads whose rows carry their source and licence.
- A corrections page with a report form that works without JavaScript and a public list of fixes, and an "If you're
  named" page where a landlord can ask for a correction or publish a statement beside what the site says about it
  (docs/DECISIONS.md, 15).

## How it works

The site is a Python package (`src/landlords/`) that downloads the publishers' files, checks them and writes static
HTML. A small FastAPI app serves the pages and takes readers' reports and landlords' statements.

1. `landlords fetch` downloads the files listed in `config/sources.toml` from GOV.UK and the Ombudsman's site into
   `data/raw/`, keyed by their SHA-256, and never overwrites one. It makes one request at a time, at least a second
   apart, with a user agent that names the project.
2. `landlords load` reads them into Parquet tables in `data/staging/`, each row carrying its file's hash and period.
3. `landlords check` matches every row to a landlord and reproduces the regulator's published totals. The
   regulator's code (L4203, 00GL) is every landlord's id. Other names (from adverts and the Ombudsman's tables) are
   kept as hand-checked aliases in `data_static/aliases.csv`; a name is never matched by guesswork.
4. `landlords build` places each landlord among similar ones (`config/scoring.toml`, explained in
   [docs/METHOD.md](docs/METHOD.md)) and writes the pages to `data/site/`. Every sentence comes from
   `config/*.toml`, written for a reading age of about 9. Content pages load no scripts and nothing from other sites,
   and stay under 100 KB.

The site publishes no AI-written text and installs no AI library: `tests/test_dependencies.py` fails if one is ever
installed.

The parts every Where They Stand site shares (settings, the state database, rate limiting, readers' reports and the
right of reply, backups and their commands) come from the charity's shared package,
[wts-core](https://github.com/rj-mitchell/wts-core). The shared header endorsement, footer shelf, fonts and icons
come from the Where They Stand family kit, copied into `src/landlords/family/`.

## Documentation

[docs/README.md](docs/README.md) indexes the documents and says who each is for:

- [docs/DATA.md](docs/DATA.md): the sources, what is in each file, how it is loaded and checked, and open questions
- [docs/METHOD.md](docs/METHOD.md): how landlords are compared, with a worked example and questions for the reviewer
- [docs/DESIGN.md](docs/DESIGN.md): the design, the family kit and the mark
- [docs/OPERATIONS.md](docs/OPERATIONS.md): building and publishing the pages, reports and statements, and the state
  database
- [docs/DEPLOY.md](docs/DEPLOY.md): setting up and running the site on the server
- [docs/DECISIONS.md](docs/DECISIONS.md): the product decisions
- [docs/BETA.md](docs/BETA.md): the gates to beta and the other open items
- [docs/USER-TESTING.md](docs/USER-TESTING.md): the plan for testing with people who bid for social homes

## Running it locally

It needs [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync
uv run landlords fetch     # about a minute; downloads into data/raw/
uv run landlords load      # data/staging/
uv run landlords check     # every row matched, published figures reproduced
uv run landlords build     # peer groups, bands and every page, in data/site/
uv run landlords serve     # the site and its API at http://127.0.0.1:8000/
```

## Testing

```bash
uv run ruff check .
uv run pytest
```

The tests on the real data and pages (`tests/test_data.py`) skip themselves until `landlords load` and
`landlords build` have run. The accessibility check, `node scripts/a11y.mjs http://127.0.0.1:8000`, needs Node 22,
Playwright and axe-core, and a running `landlords serve`.

GitHub Actions (`.github/workflows/ci.yml`) runs ruff and the tests on every pull request, builds the real pages from
the publishers' files (cached, and fetched again only when `config/sources.toml` changes), runs the data tests and
the accessibility check on them, and builds the server's Docker image. The jobs shared by every family site are
wts-core's reusable workflows, called at the tag of the release this site installs.

## Deployment

The site runs on the charity's shared server, behind Where MPs Stand's web server, with a weekly update and nightly
backups on systemd timers. See [docs/DEPLOY.md](docs/DEPLOY.md).

## Data sources and licences

- Tenant Satisfaction Measures, regulatory judgements, the register of providers and the stock data: the Regulator
  of Social Housing, under the Open Government Licence v3.0.
- Landlord complaint tables: the Housing Ombudsman Service, used while its reuse terms are confirmed.

[docs/DATA.md](docs/DATA.md) describes every file. Each landlord's page lists the files behind it.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). To report a mistake on the site, use its
[corrections page](https://wherelandlordsstand.com/corrections/).

## Licence

The code is licensed under the AGPL-3.0 ([LICENSE](LICENSE)). The site's own text and work (the bands, peer
groups, homes by council area and the method) are under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Data stays under each publisher's terms. The name and mark are not covered by either licence.
