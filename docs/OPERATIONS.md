# Operations

How the data is fetched, loaded, checked and turned into pages, and how new pages are published. On the server the
weekly update runs by itself and asks the owner to approve new pages ("The weekly update, the email, and
publishing"). Every step can also be run by hand, as below.

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
code. `landlords build` replaces `data/site/` each time. On your own computer `serve` listens on 127.0.0.1 only.

The stylesheet is `src/landlords/static/styles.css`. The build copies it, the scripts, and the family kit's
stylesheets, fonts, icons and link card into `data/site/assets/`, each with a fingerprint of its content in its name,
so a cache never serves an old copy (docs/DESIGN.md, "Where the look lives").

**The family kit** (`src/landlords/family/`) is the Where They Stand family's binding: the endorsement, the footer
shelf, the icons and link card, and Source Serif 4. It is copied in from the charity's family folder, never edited
here. When the kit changes (a new sister site, a status, the stylesheet), copy it again from a checkout of the
charity's repository, then rebuild:

```bash
node <charity checkout>/family/kit/sync.mjs --site landlords --out src/landlords/family
```

`uv run pytest` fails if the copy has been edited by hand (its `VERSION` file carries a hash of the rest).

**Links to Where Councils Stand.** A council's page and each council area's page link to the council's page on Where
Councils Stand where that site covers the council, from `data_static/councils_covered.csv`. Refresh it now and then
(it grows as Where Councils Stand loads more councils), look at the change and commit it:

```bash
uv run landlords sister-councils       # reads wherecouncilsstand.com/api/councils
```

`uv run pytest` checks the built pages: each landlord's page under 100 KB, with the line about turning down offers,
no scripts or outside resources, and every source link pointing to a listed file; and every page carries the
family's binding.

## The weekly update, the email, and publishing

Every Thursday the server runs `landlords update`. The owner only needs to approve the new pages:

1. It fetches any new files, loads and checks them.
2. If anything is new (files from the publishers, or a new version of the site), it builds a new set of pages in
   `data/builds/<time>/`. If nothing is new, it builds nothing.
3. It emails `[publish] notify_to` (wheretheystanduk@gmail.com) a report and two links: one to look at the new
   pages, and one to approve them. The site is public, in alpha, so this happens whether or not the launch switch is
   on (docs/DECISIONS.md, 12). Only the very first pages, when none are live, are published at once. The approve
   link opens a page with the report and a **Publish these pages** button; opening the link never publishes on its
   own (email scanners open links). After publishing, the same page has an **Undo** button while those pages are
   live. Links work for 14 days; if nobody approves, the site keeps its current pages. A build whose checks failed
   can't be approved. If the email can't be sent, the update fails, so the server's alert says so: otherwise nobody
   would hear of the new pages.
4. The email also goes out, without links, when something else needs attention: checks failed, a new kind of release
   appeared, a section of the rights page is due to be checked again, or readers' reports are waiting.

`[publish] mode = "auto"` publishes every build whose checks pass, and the email just says what changed.

**The status page** (`/status/`, `src/landlords/status.py`) says when the pages were made, when each set of files was
last downloaded and read in, when the site last looked for new files, and whether new pages are waiting for approval.
Every build writes it, with `status.json` beside it; every weekly update, publish and undo then writes it again in the
live pages, so it is right even in a week with nothing new. Its sentences are in `config/pages.toml` ([status]), with
the press page's ([press]: contact, facts in brief, how to cite a landlord's page, and the logo files in `/press/`).

**How the email is sent.** The site keeps no mail password. `landlords update` runs in a one-off container and
writes its email as a letter to the outbox in its data folder, `data/outbox/` (`/data/outbox` in the container): "To:"
and "Subject:" lines, a blank line, then the text (`src/landlords/notify.py`). On the server,
`deploy/run-update.sh` (which the weekly unit runs) then sends every letter in the outbox with the charity's shared
`mail.sh` in Where MPs Stand's checkout (`deploy/send-mail.sh`), which reads the one copy of the password in
`/etc/wheretheystand/mail.env`, and moves each one sent to `data/outbox/sent/`. A letter that can't be sent stays in the
outbox, and the unit fails, so the server's alert says so; `bash deploy/send-mail.sh` tries again. `landlords
email-test` leaves a test letter in the outbox the same way (docs/DEPLOY.md, step 5).

On your own computer, letters just collect in `data/outbox/`. To send them for real while developing, set
`LANDLORDS_MAIL=smtp` with `LANDLORDS_SMTP_USER` and `LANDLORDS_SMTP_PASSWORD` for an account of your own (the
docstring of `src/landlords/notify.py`). Never on the server.

By hand, if ever needed:

```bash
uv run landlords update                # as above (`--no-email` to skip the email; on the server, deploy/run-update.sh)
uv run landlords publish               # make the newest build live
uv run landlords publish 20261103-232550
uv run landlords rollback              # put back the build that was live before
```

Each build has `build-info.json` (new files, failed checks, what was done) and `change-report.json` (grade changes,
biggest movers). The last six builds are kept, and never the live one or the one before it.

## Readers' reports, statements and missed searches

```bash
uv run landlords reports                                   # open reports; requests to remove a person's details first
uv run landlords reports --close 3 --outcome "fixed alias"   # closes it and deletes the reporter's email address
uv run landlords missed                                    # searches that found nothing, most frequent first
uv run landlords backup --to backups                       # copy the state database
```

The "report a mistake" form posts to the site's small API, so it works wherever the pages are served by `landlords
serve` (on the server and on your own computer), but not when the built files are opened on their own. Each report has
a `kind`: `wrong` ("Something is wrong"), `unfair` ("You've been characterised unfairly"), `takedown` (a person's
details to remove: deal with these first) or `other` (docs/DECISIONS.md, 15). A link to
`/corrections/?kind=unfair&page=landlords/abri-group/` opens the form with that kind chosen and the page filled in.

If a report shows a mistake of ours, fix it, add a line to `data_static/corrections.csv` (shown on the corrections
page), rebuild and publish. If it is about a publisher's figure, we don't change it: reply and point to the publisher.
If it says our own words, labels or groupings are unfair, check them against the charity's impartiality policy and,
if they break it, put them right in the same way. A missed search that is really a landlord's name is added through
`landlords match --accept` like any other alias.

**Response times** (the impartiality policy, 7.3; said on the corrections page and "If you're named"): reply within 5
working days, decide within 20. The weekly email counts open reports and statements waiting, but a week is too long
to wait for the first reply: look at `landlords reports` and `landlords statements` at least twice a week.

**Statements from landlords** (the right of reply; `src/landlords/statements.py`). A landlord, or someone acting for
it, sends a statement of up to 150 words from the form on "If you're named" (`/named/`). One that breaks a limit
(150 words or 2,000 characters; a name of 120 characters, a role of 200, a link of 300) is refused, and the sender is
told which limit and by how much: nothing sent is ever cut to fit, because a statement is published as written or
declined, never edited. The same limits hold for `--update`. A statement that passes is kept as pending:

```bash
uv run landlords statements                                # those waiting, with their email and word count
uv run landlords statements --all                          # every one, whatever its state
uv run landlords statements --publish 4 --checked "reply from j.smith@example-housing.org.uk, 14 Nov"
uv run landlords statements --publish 5 --checked "..." --landlord birmingham-city-council   # about an area's page
uv run landlords statements --decline 6 --reason "it names a tenant"
uv run landlords statements --update 4 --text-file new.txt --reason "the author's new version"   # or --name/--role/--link
uv run landlords statements --withdraw 4 --reason "withdrawn by the author"
uv run landlords statements --log 4                        # what was done to it, and why
```

1. **Confirm who sent it** before publishing: write to the address given, from admin@wherelandlordsstand.com, and
   check it is the landlord's own (an address at its web address, or the council's), or check with the landlord
   through its published contact details. Say how in `--checked`: it is logged.
2. **Check it against the rules** (the policy, 7.2): nothing defamatory, abusive or about a private individual, no
   one else's personal data, no appeals for votes, money or support, nothing about another person's conduct (and in an
   election period, nothing that campaigns). Then publish it as written, or decline it with `--reason` and tell the
   sender why. Never edit it: if something must come out, agree it with the author and use `--update` with their
   new version.
3. Publishing, updating or withdrawing writes the live pages again at once (and every kept build, so approving or
   undoing pages never brings back an old version or drops a new one); no rebuild or approval is needed. A statement
   about an area's page needs `--landlord`: it is shown there and on that landlord's own page.

Every decision is logged in the state database (`statement_log`), for the trustees' review (the policy, 7.4). The
email address given is never shown; it is deleted three months after a statement is withdrawn or declined, at each
`landlords statements` command and each weekly update. There is no admin page for statements or reports: the owner
uses these commands on the server (docs/DEPLOY.md, "Running it").

## The rights page

Every section of `config/rights.toml` has a `recheck` date; `landlords check` warns once one has passed. The
Ombudsman's complaints section is due weekly while its IT incident lasts; Awaab's Law on 1 December 2026, to confirm
that phase 2's regulations were made and are in force (on 6 November 2026 they were still a draft); STAIRs by March
2027.
