# Operations

How the data is fetched, loaded, checked and turned into pages, how new pages are published, and how readers'
reports, statements and the state database are looked after. It is for the maintainer. On the server the weekly
update runs by itself and asks the owner to approve new pages ("The weekly update, the email, and publishing");
every step can also be run by hand, as below. Setting up and running the server is in docs/DEPLOY.md.

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
code. `landlords build` replaces `data/site/` each time. `serve` listens on 127.0.0.1 only unless told otherwise.

The stylesheet is `src/landlords/static/styles.css`. The build copies it, the scripts, and the family kit's
stylesheets, fonts, icons and link card into `data/site/assets/`, each with a fingerprint of its content in its name,
so a cache never serves an old copy (docs/DESIGN.md, "Stylesheets and assets").

The family kit (`src/landlords/family/`) is the Where They Stand family's binding: the endorsement, the footer
shelf, the icons and link card, the family stylesheet, and Source Serif 4 and Source Sans 3. It is copied in from the
charity's repository (`family/kit/`) and never edited here. When the kit changes (a new sister site, a status, the
stylesheet), copy it again from a checkout of the charity's repository, then rebuild:

```bash
node <charity checkout>/family/kit/sync.mjs --site landlords --out src/landlords/family
```

`uv run pytest` fails if the copy has been edited by hand (its `VERSION` file carries a hash of the rest). It also
checks the built pages (`tests/test_data.py`): each landlord's page under 100 KB, with the line about turning down offers,
no scripts or outside resources, and every source link pointing to a listed file; and every page carries the
family's binding.

### Links to Where Councils Stand

A council's page and each council area's page link to the council's page on Where Councils Stand where that site
covers the council, from `data_static/councils_covered.csv`. Refresh it now and then
(it grows as Where Councils Stand loads more councils), look at the change and commit it:

```bash
uv run landlords sister-councils       # reads wherecouncilsstand.com/api/councils
```

## The weekly update, the email, and publishing

Every Thursday the server runs `landlords update`. The owner only needs to approve the new pages:

1. It fetches any new files, loads and checks them.
2. If anything is new (files from the publishers, or a new version of the site), it builds a new set of pages in
   `data/builds/<time>/`. If nothing is new, it builds nothing.
3. It emails `[publish] notify_to` (wheretheystanduk@gmail.com) a report and two links: one to look at the new
   pages, and one to approve them. This happens whether or not the launch switch is on (docs/DECISIONS.md, 12).
   Only the very first pages, when none are live, are published at once. The approve
   link opens a page with the report and a Publish these pages button; opening the link never publishes on its
   own (email scanners open links). After publishing, the same page has an Undo button while those pages are
   live. Links work for 14 days; if nobody approves, the site keeps its current pages. A build whose checks failed
   can't be approved. If the email can't be sent, the update fails, so the server's alert says so: otherwise nobody
   would hear of the new pages.
4. The email also goes out, without links, when something else needs attention: checks failed, a new kind of release
   appeared, a section of the rights page is due to be checked again, or readers' reports are waiting.

`[publish] mode = "auto"` publishes every build whose checks pass, and the email just says what changed.

The status page (`/status/`, `src/landlords/status.py`) says when the pages were made, when each set of files was
last downloaded and read in, when the site last looked for new files, and whether new pages are waiting for approval.
Every build writes it, with `status.json` beside it; every weekly update, publish and undo then writes it again in the
live pages, so it is right even in a week with nothing new. Its sentences are in `config/pages.toml` ([status]), with
the press page's ([press]: contact, facts in brief, how to cite a landlord's page, and the logo files in `/press/`).

### Sending the email

The site keeps no mail password. `landlords update` runs in a one-off container and
writes its email as a letter to the outbox in its data folder, `data/outbox/` (`/data/outbox` in the container): "To:"
and "Subject:" lines, a blank line, then the text (`src/landlords/notify.py`). On the server,
`deploy/run-update.sh` (which the weekly unit runs) then sends every letter in the outbox with the charity's shared
`mail.sh` in Where MPs Stand's checkout (`deploy/send-mail.sh`), which reads the one copy of the password in
`/etc/wheretheystand/mail.env`, and moves each one sent to `data/outbox/sent/`. A letter that can't be sent stays in the
outbox, and the unit fails, so the server's alert says so; `bash deploy/send-mail.sh` tries again. `landlords
email-test` leaves a test letter in the outbox the same way (docs/DEPLOY.md, step 5).

On a developer's own computer, letters just collect in `data/outbox/`. To send them for real while developing, set
`LANDLORDS_MAIL=smtp` with `LANDLORDS_SMTP_USER` and `LANDLORDS_SMTP_PASSWORD` for the developer's own account (the
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
uv run landlords waiting                                   # how many reports and statements are waiting, and how long
uv run landlords reports list                              # open reports; requests to remove a person's details first
uv run landlords reports show 3                            # one report
uv run landlords reports close 3 --outcome resolved --note "fixed alias"   # and deletes the reporter's email address
uv run landlords reports close 4 --outcome dismissed --note "the regulator's figure, not ours"
uv run landlords reports list --all                        # closed ones too, with how each ended and the note
uv run landlords missed                                    # searches that found no landlord with a page, most frequent first
uv run landlords backup --to backups                       # copy the state database
```

These commands, and those for statements below, are the Where They Stand sites' shared ones (the shared package,
wts-core), under this site's names; each prints one JSON object a line. A report is closed as `resolved` (put right)
or `dismissed` (looked at, and nothing of ours to change), with a private note of what was found and done. Lists
show the newest first.

The "report a mistake" form posts to the site's small API, so it works wherever the pages are served by `landlords
serve` (on the server and on a developer's computer), but not when the built files are opened on their own. Each report has
a `kind`: `wrong` ("Something is wrong"), `unfair` ("You've been characterised unfairly"), `takedown` (a person's
details to remove: deal with these first) or `other` (docs/DECISIONS.md, 15). A link to
`/corrections/?kind=unfair&page=landlords/abri-group/` opens the form with that kind chosen and the page filled in.
The report form and the statement form each have a hidden field that people never see or reach, labelled "Leave this
empty": a post with it filled in comes from a robot, so it is thanked like any other and nothing is kept.

If a report shows a mistake of ours, fix it and say so in the corrections page's list, "Mistakes we have fixed". The
list is drawn from two places, newest first (`src/landlords/corrections.py`):

- a public note given when the report is closed: `landlords reports close 3 --outcome resolved --note "fixed the
  alias" --public-note "Example Housing's grade was shown as C3. It is C2."`. It is on the live pages at once, with
  the date the report was closed and its kind in the form's own words ("Something is wrong"). Nothing the reporter
  typed is ever shown, not even the page they named, so say in the note which page was put right; and name no one who
  reported. The private `--note` is never shown.
- a row in `data_static/corrections.csv` (date as `2026-11-14`, page, what was wrong, what we did), for a mistake
  nobody reported, or one that needs the page named in its own column. It reaches the site with the next pages that
  are built and approved.

If it is about a publisher's figure, we don't change it: reply and point to the publisher.
If it says our own words, labels or groupings are unfair, check them against the charity's impartiality policy and,
if they break it, put them right in the same way. A missed search that is really a landlord's name is added through
`landlords match --accept` like any other alias.

Response times (the charity's impartiality policy, 7.3; said on the corrections page and "If you're named"):
reply within 5 working days, decide within 20. The weekly email counts what is waiting, but a week is too long to
wait for the first reply, so the maintainer runs `landlords waiting` at least twice a week (docs/DEPLOY.md,
"Routine"). It also says how many working days the oldest has waited. Once `LANDLORDS_CHECK_TOKEN` is set (below,
"The nightly check"), the charity's nightly check of its sites also fails when anything has waited four working
days.

Statements from landlords are the right of reply (`src/landlords/replies.py` has the rules this site sets, and
`src/landlords/statements.py` how a statement is shown). A landlord, or someone acting for it, sends a statement
of up to 150 words from the form on "If you're named" (`/named/`). One that breaks a limit (150 words or 2,000
characters; a name of 120 characters, a role of 200, a link of 300) is refused, and the sender is told which limit
and by how much: nothing sent is ever cut to fit, because a statement is published as written or declined, never
edited. The same limits hold for `update`. A statement that passes is kept as pending:

```bash
uv run landlords statements list                           # those waiting, with their email and word count
uv run landlords statements list --all                     # every one, whatever its state (or --status published)
uv run landlords statements show 4                         # one, and everything done to it
uv run landlords statements publish 4 --checked "replied from the landlord's own address, 14 Nov"
uv run landlords statements publish 5 --checked "..." --landlord birmingham-city-council   # about an area's page
uv run landlords statements decline 6 --reason "it names a tenant"
uv run landlords statements update 4 --text-file new.txt --reason "the author's new version"   # or --name/--role/--link
uv run landlords statements withdraw 4 --reason "withdrawn by the author"   # its author asked
uv run landlords statements remove 4 --reason "it names a tenant"           # we took it down: it broke the rules
uv run landlords statements log 4                          # what was done to it, and why
```

1. Confirm who sent it before publishing: write to the address given, from admin@wherelandlordsstand.com, and
   check it is the landlord's own (an address at its web address, or the council's), or check with the landlord
   through its published contact details. Say how in `--checked`: it is logged, and the log is kept for good.
   So don't put the sender's email address in the note (say "replied from the landlord's own address", not the
   address itself): the privacy page promises that address is deleted three months after a statement is withdrawn,
   declined or removed. A note that holds the sender's address is refused.
2. Check it against the rules (the policy, 7.2): nothing defamatory, abusive or about a private individual, no
   one else's personal data, no appeals for votes, money or support, nothing about another person's conduct (and in an
   election period, nothing that campaigns). Then publish it as written, or decline it with `--reason` and tell the
   sender why. Never edit it: if something must come out, agree it with the author and use `update` with their
   new version; the log keeps the words it replaced.
3. Publishing, updating, withdrawing or removing writes the live pages again at once (and every kept build, so
   approving or undoing pages never brings back an old version or drops a new one); no rebuild or approval is needed.
   A statement about an area's page needs `--landlord`: it is shown there and on that landlord's own page.
4. A published statement comes down in one of two ways, and the log says which: `withdraw` when its author asks,
   `remove` when it breaks the rules (tell the author why). `decline` is only for one that was never shown.

Every decision is logged in the state database (`wts_statement_log`), for the trustees' review (the policy, 7.4). The
email address given is never shown; it is deleted three months after a statement is withdrawn, declined or removed.
That is checked every night, after the backup (`landlords nightly`, run by `landlords-backup.service`), and at every
command above. Nothing waits for ever: a statement nobody has decided after three months lapses (it is declined, with
the reason "No decision was made in time; please send it again", and its email address deleted), and a report still
open after three months keeps its place in the list but loses its email address. `landlords lapsing` shows what the
next tidy would lapse, and does nothing: numbers, dates and ages only. Every list and every decision above tidies
first, so look there before anything else if something may have waited that long. There is no admin page for
statements or reports: the owner uses these commands on the server (docs/DEPLOY.md, "Running it").

## Hiding a landlord's page while a concern is decided

The charity's impartiality policy (7.3) says an item is hidden, with a note, while a concern about it is decided.
Here the item is a landlord's page (`src/landlords/hiding.py`; docs/DECISIONS.md, 17):

```bash
uv run landlords hide landlords/abri-group/ --note "We are checking how we matched one of its names."
uv run landlords hidden                                    # what is hidden now, the longest hidden first
uv run landlords unhide landlords/abri-group/              # puts everything back exactly as it was
```

The address can be typed any way it is copied (the full address from a browser, with or without `index.html`).
Anything that is not a landlord's page, or a landlord with no page on the site, is refused. The change is on the
live pages at once, and in every kept build, so approving or undoing pages never shows it again by mistake; no
rebuild or approval is needed, and pages built while it is hidden hide it too. While it is hidden:

- its own page shows its name, then "This page is hidden while a concern about it is decided." and the note, in
  place of its figures and of any statement;
- it is left out of the list of all landlords, of search and the compare page, of the table on each council area's
  page (and the counts beside them), of the sitemap, and of the downloads (its rows go from each CSV file);
- statements beside its page are not shown, nor one on an area's page that speaks for it; none can be sent about
  its page, and none is published for it until it is shown again.

`unhide` puts back, to the byte, what was there before, with any statement published or withdrawn meanwhile. The
files as they were built are kept in the data folder's `hidden-originals/` while something is hidden; it is not
served, and holds nothing but pages.

What hiding does not reach, because it is another page's own fact or a figure worked out with the landlord in
it: another landlord's page that names it (a merger, or a grade given to its group) still does, and the link leads
to the note; the bands of similar landlords were worked out with it among them, and are not worked out again; the
press page's count of landlords still includes it, and still gives it as the example if it is the one hidden; a
council area where it was the only landlord keeps its page, with nobody in its table. `landlords waiting` counts
what is hidden, so a page is not left hidden by oversight.

## The state database

`data/state.db` (on the server, in the `landlords-data` volume) is the one thing that can't be rebuilt from the
publishers' files. `src/landlords/state.py` opens it through the shared package, wts-core. It holds the package's
tables, each named `wts_…` (reports, statements and their log), and this site's own two: `missed` (searches that
found nothing) and `approvals` (the links in the weekly email). Until 1 February 2027 it also holds the site's old
tables (below, "The move onto wts-core").

### Nightly housekeeping

`landlords nightly` runs after each night's backup (`landlords-backup.service`). In this order, it:

1. deletes the email address of each statement withdrawn, declined or removed three months ago, lapses what nobody
   has decided in three months, and deletes the email address of each report open that long;
2. until 1 February 2027, deletes the same addresses from the site's old tables, and from the old copy of any note
   an address was written into; on 1 February 2027 it drops the old tables;
3. deletes `state.pre-wts-core.<date>.db` once it is more than 60 days old (as long as off-site backups are
   kept), because it holds email addresses as they stood that day;
4. last, writes the database out afresh (wts-core's `wts_core.cli.write_afresh`: SQLite's `VACUUM`). SQLite does not
   wipe what it deletes by itself, so a deleted address could otherwise stay in the file's unused space, and in each
   backup of it. Every connection the package makes also overwrites what it deletes as it deletes it (`PRAGMA
   secure_delete`), so what the steps above delete is gone even on a night the file cannot be written out afresh.

It prints what it did as one line of JSON, then one line that says whether the file was written out afresh: "Wrote
the database out afresh: nothing deleted is left in the file.", or, when the site was using the file at that moment,
"The database was NOT written out afresh tonight: …", which is tried again the next night. It exits 1 (so the alert
email is sent) if the old tables were due to be dropped and could not be, or if the file could not be written out
afresh on the second night running ("That is 2 nights running."; the count is kept in the database, under
`tidy:nights_not_written_afresh`, and a second run by hand on the same night does not add to it). The backups made
before a deletion still hold what was deleted, until they age out: the privacy page says backups are kept for up to
two months.

### The move onto wts-core

Reports and statements used to be kept in tables of the site's own (`reports`, `statements`, `statement_log`). When
the site was first deployed on wts-core (November 2026), the first command to open the database copied their rows
into the `wts_` tables, in one step that either happens whole or not at all, and marked the move as made. Before
copying, it kept the whole file as it was beside it, as `state.pre-wts-core.<date>.db`, readable by the site's user
only.

The same copy is made whenever the new code opens a database that has the old tables and no mark: a backup from
before the move that has been put back (`landlords restore`), or a database after going back (below). That is why
no `landlords` command is run by hand while `update.sh` deploys new code (docs/DEPLOY.md, "New code"): a copy made
while the old site was still writing would miss what it wrote afterwards.

The old tables stay in the file until 1 February 2027, for the way back, and are kept to the privacy page's
promises each night (above).

### Going back, and coming forward again

Until 1 February 2027 the site can go back to its code from before wts-core. That code is no longer in this
repository: it is in the private archived repository `rj-mitchell/wherelandlordsstand_old`, as it stood before the
site moved onto wts-core (14 November 2026). To go back, on the server:

1. Stop the site: `docker compose stop app`.
2. Run `deploy/undo-wts-core.sql` on the database (the command is at the top of the file). It writes the old tables
   again from the package's, so that the old code finds everything sent and decided since the move, then forgets the
   move: the package's copies of those rows are emptied and the move's mark is removed. Run it once: a second run
   stops at its first step and changes nothing.
3. Put the archived code in `/opt/wherelandlordsstand` and start it with `docker compose up -d --build`.

What the old tables cannot hold is folded into what they can, as the script's heading says (a statement removed for
breaking the rules goes back as withdrawn; how a report ended and its public note are not kept), and what the
package has deleted stays deleted.

Coming forward again is an ordinary deploy of this repository's code (docs/DEPLOY.md, "New code"). The new code makes
the move afresh over everything in the old tables, including what the old code took in meanwhile, and keeps a copy
of the file first. Nothing is counted twice.

If the old code was started without the undo script, what it takes in goes to the old tables only, and the new
code, deployed again, would never see it. So the new code refuses to start: the site, every `landlords` command and
the nightly housekeeping stop with "the site's old tables hold rows that are newer than the import that copied
them", naming the tables, and change nothing. There are then two scripts, and each discards something:

- the old code was started after the move: `deploy/redo-wts-core.sql`, which only forgets the move. It keeps
  what the old code wrote, and discards what the new code wrote between the move and then (reports and decisions on
  statements taken on the new code). Then start the site: the move is made afresh;
- the old code was never started after the move (a false alarm: the server's clock was put back between the old
  code's last write and the move): `deploy/undo-wts-core.sql`, which keeps what the new code wrote. Do not run it to
  keep what the old code wrote: it writes the old tables afresh from the package's, and would discard it.

The refusal cannot see a row the old code wrote in the very second the move was made, a row with no time, or a change
the old code made to a row already there without adding one (it adds a line to a statement's log for each decision,
so a decision is seen; a report closed is not). The nightly housekeeping never trips it: it changes and deletes rows
of the old tables, and adds none.

From 1 February 2027 both scripts stop ("no such table") and change nothing. Going back then, or throwing away
everything since the move, means putting back `state.pre-wts-core.<date>.db` (while it is kept, 60 days) or a backup
made before the move, while one is still kept.

## The nightly check

The charity checks its sites every night from its own repository (the family check). Once the owner has made the
family's check token and set it as `LANDLORDS_CHECK_TOKEN` in `deploy/.env` (then `update.sh`), the site answers
`GET /api/check` to that token alone, with counts and ages and nothing else: how many reports and statements are
waiting and how many working days the oldest has waited, and how old the newest backup and off-site copy are. Never
a word of a report or a statement, a name or an address. With no token set, the address does not exist, and the
nightly check reports this site as not set up.

## The rights page

Every section of `config/rights.toml` has a `recheck` date; `landlords check` warns once one has passed. The
Ombudsman's complaints section is due weekly while its IT incident lasts (reported October 2026). Awaab's Law is due
on 1 December 2026, to confirm that the regulations for its second phase were made and are in force (on 6 November
2026 they were still a draft). The section on STAIRs (the social tenant access to information requirements) is due by 1 March 2027.
