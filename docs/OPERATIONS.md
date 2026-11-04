# Operations

How the data is fetched, loaded, checked and turned into pages. Everything runs by hand for now; the weekly update
and publishing come later.

## Fetching

```bash
uv run landlords fetch                 # every source in config/sources.toml
uv run landlords fetch tsm             # one source
```

Each line of `config/sources.toml` names a page and how to find the file on it: a GOV.UK page and the attachment's
title, or another page and the link's address. A new year is a new line (a new `period`). Each run:

1. fetches each page once (GOV.UK pages through the Content API), one request at a time, a second apart;
2. downloads files whose address hasn't been fetched before (publishers put a changed file at a new address);
3. keeps each file as `data/raw/<source>/<sha256>.<ext>` with a note, and adds a line to that source's `index.jsonl`;
4. writes `data/staging/fetch-report.json`: new files, and sources that failed.

It exits 1 if a source fails: usually a page whose layout or file title has changed. Look at the page and update
`config/sources.toml`. Nothing already downloaded is touched.

## Loading

```bash
uv run landlords load                  # every source
uv run landlords load tsm grades       # some
```

Each loader reads the newest file for its source. It stops with "expected columns not found" or "sheet not found" if
the publisher has changed the file's layout: nothing is loaded from it until the loader is updated. The tables go to
`data/staging/`, never straight to the site.

## The register and names

```bash
uv run landlords register              # new landlords from the register; names publishers print beside a code
uv run landlords load ombudsman        # match the Ombudsman's names again
uv run landlords match                 # names still without a landlord -> data/staging/match-review.csv
```

Open `match-review.csv`, put `yes` in `accept` on the right candidate (and the alias `kind`: published, trading,
short, former, group, managing body or logo label), then:

```bash
uv run landlords match --accept data/staging/match-review.csv
uv run landlords load ombudsman
```

Display names, slugs, statuses and successors in `data_static/landlords.csv` are edited by hand and kept by
`landlords register`. When a landlord merges, set `status` to `merged`, with `successor_id` and `successor_date`, from
the regulator's own statement. Never change a slug that has been published; list published slugs in
`data_static/published_slugs.txt`.

## Checking

```bash
uv run landlords check
```

Every row matched to a landlord, the register sound, values in range, the publishers' totals reproduced
(`config/reconciliation.toml`), area codes known, homes by area against TSM populations, and a change report. It exits
1 if any check fails. The details are in `data/staging/check-report.json` and `change-report.json`.

When a new year is published, add its expected totals to `config/reconciliation.toml` from the publisher's report
before loading it.

## Scoring and the pages

```bash
uv run landlords score                 # peer groups and bands -> data/staging/peer_groups, scores
uv run landlords build                 # score, then write the pages to data/site/
uv run landlords serve                 # http://127.0.0.1:8000/ on this computer only
```

The rules are in `config/scoring.toml` and every sentence in `config/wording.toml`; change them there, not in the
code. `landlords build` replaces `data/site/` each time. Nothing is deployed: `serve` listens on 127.0.0.1 only.

`uv run pytest` checks the built pages: each under 100 KB, with the line about turning down offers, no scripts or
outside resources, and every source link pointing to a listed file.

## The weekly update, the email, and publishing

Every Thursday the server runs `landlords update`. Nobody needs to run anything by hand:

1. It fetches any new files, loads and checks them.
2. If anything is new (files from the publishers, or a new version of the site), it builds a new set of pages in
   `data/builds/<time>/`. If nothing is new, it builds nothing.
3. **Before launch** (`[site] launched` false) it publishes them at once: nothing is public, so there is nothing to
   approve. **After launch** it emails `[publish] notify_to` (wherestheystanduk@gmail.com) a report and two links:
   one to look at the new pages, and one to approve them. The approve link opens a page with the report and a
   **Publish these pages** button; opening the link never publishes on its own (email scanners open links). After
   publishing, the same page has an **Undo** button while those pages are live. Links work for 14 days; if nobody
   approves, the site keeps its current pages. A build whose checks failed can't be approved.
4. The email also goes out, without links, when something else needs attention: checks failed, a new kind of release
   appeared, a section of the rights page is due to be checked again, or readers' reports are waiting.

`[publish] mode = "auto"` publishes every build whose checks pass, and the email just says what changed.

Setting up the email, once, on the server (`env/landlords.env`): `LANDLORDS_SMTP_USER` (the Gmail address that
sends it) and `LANDLORDS_SMTP_PASSWORD` (a Google **app password**: Google account → Security → 2-Step Verification
→ App passwords; the account needs 2-Step Verification on). Then check it:
`bash scripts/run-job.sh landlords-job landlords email-test`.

By hand, if ever needed:

```bash
uv run landlords update                # as above (`--no-email` to skip the email)
uv run landlords publish               # make the newest build live
uv run landlords publish 20261103-232550
uv run landlords rollback              # put back the build that was live before
```

Each build has `build-info.json` (new files, failed checks, what was done) and `change-report.json` (grade changes,
biggest movers). The last six builds are kept, and never the live one or the one before it.

## Readers' reports and missed searches

```bash
uv run landlords reports                                   # open reports of mistakes
uv run landlords reports --close 3 --outcome "fixed alias"   # closes it and deletes the reporter's email address
uv run landlords missed                                    # searches that found nothing, most frequent first
uv run landlords backup --to backups                       # copy the state database
```

If a report shows a mistake of ours, fix it, add a line to `data_static/corrections.csv` (shown on the corrections
page), rebuild and publish. If it is about a publisher's figure, we don't change it: reply and point to the publisher.
A missed search that is really a landlord's name is added through `landlords match --accept` like any other alias.

## The rights page

Every section of `config/rights.toml` has a `recheck` date; `landlords check` warns once one has passed. The
Ombudsman's complaints section is due weekly while its IT incident lasts; Awaab's Law on 1 December 2026, when phase 2
should be in force; STAIRs by March 2027.
