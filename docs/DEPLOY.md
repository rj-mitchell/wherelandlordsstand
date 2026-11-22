# Deploying Where Landlords Stand

How the site is set up and run on the charity's shared server. It is for the maintainer.

The site runs in its own folder (`/opt/wherelandlordsstand`), with its own container, data, settings and timers,
beside the charity's other sites. This page has only this site's own steps. Everything the sites share is described
in Where MPs Stand's [`docs/HOSTING.md`](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md):

| Shared part | Where it is described |
|---|---|
| The front door (Caddy, in Where MPs Stand's checkout at `/opt/hansardgpt`), which answers this site's domain and passes visitors to its container | [Other sites on this server](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md#other-sites-on-this-server) |
| Cloudflare: the DNS record, `www` redirect, Full (strict) and the origin certificate | [Cloudflare protection](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md#cloudflare-protection-optional) and "Adding a site" under [Other sites on this server](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md#other-sites-on-this-server) |
| Email from the server, and failure alerts | [Email from the server](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md#email-from-the-server) |
| The Backblaze B2 bucket for off-site backups | [Backups](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md#backups) |
| The server-wide update lock, the health check and the update times of every site | [Other sites on this server](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md#other-sites-on-this-server) |

## Requirements

Well under 1 GB of memory (the container is limited to 1 GB), and about 1 GB of disk for the downloaded files and a
few builds of the pages. No API keys and no paid services.

## Setting it up

The server pulls the branch it cloned, so this repository's default branch must be `main` (GitHub: Settings,
General, Default branch). On the server, as root:

1. Code and settings:
   ```bash
   git clone -b main https://github.com/rj-mitchell/wherelandlordsstand /opt/wherelandlordsstand
   cd /opt/wherelandlordsstand/deploy && cp .env.example .env
   ```
   Everything in `.env` can stay empty to begin with.
2. Start it: `bash /opt/wherelandlordsstand/deploy/update.sh` builds and starts the site and, once the site answers,
   installs its weekly update, nightly backup and daily backup check timers.
3. The first pages. This is the weekly update, run now: it waits for any other site's update to finish, downloads
   the regulator's and the Ombudsman's files, builds the pages and publishes them, as none are live yet (every later
   build waits for approval). It takes a few minutes, then sends its email (step 5):
   ```bash
   bash /opt/wherelandlordsstand/deploy/run-update.sh
   ```
4. Look at it privately from another computer: `ssh -L 8004:127.0.0.1:8004 root@<server>`, then open
   http://localhost:8004. The port answers on the server itself only.
5. The weekly email, once the server's own email is set up (`mail.sh setup`, in "Email from the server" above). New
   pages are approved from this email, so without it nothing new is published, and each update fails to say so. The
   site keeps no mail password of its own (docs/OPERATIONS.md, "Sending the email"). Send a test:
   ```bash
   cd /opt/wherelandlordsstand/deploy
   docker compose run --rm -T app landlords email-test && bash send-mail.sh
   ```
   It arrives from the charity's account, as "Where They Stand", with a subject starting "Where Landlords Stand".
6. The domain: Cloudflare and the front door, as for any site on the server ("Adding a site", above), with
   `wherelandlordsstand.com=wherelandlordsstand` in `SITES` and
   `bash /opt/hansardgpt/deploy/cloudflare.sh site wherelandlordsstand.com`.
7. Check: `bash /opt/hansardgpt/deploy/check.sh` lists the site and the memory left.

## The launch switch

`[site] launched` in `config/settings.toml` decides whether search engines are let in. It is `false` in the
repository; the live site turns it on with `LANDLORDS_LAUNCHED=true` in `/opt/wherelandlordsstand/deploy/.env`.

- Off: every page carries `noindex`, and `robots.txt` asks crawlers to stay away.
- On: `robots.txt` allows crawling and points to `/sitemap.xml`, which lists every page. This needs `[site] url`
  (or `LANDLORDS_SITE_URL`). Each page's `<lastmod>` is the day its content (what is inside `<main>`) last changed:
  each build keeps a fingerprint and date for every page in `page-dates.json`, and the next build keeps a page's
  date if its fingerprint is the same as in the pages live when it is built. The status and press pages, which
  change with every build, have no date. Thank-you pages carry `noindex` and are not in the sitemap.

It changes nothing else: new pages wait for approval by email either way (docs/DECISIONS.md, 12). A change to it
counts as something new, so the next update builds the pages again. To switch it, edit `.env`, then run
`cd /opt/wherelandlordsstand/deploy && bash update.sh && bash run-update.sh` and approve the new pages from the email.
Check that `robots.txt` and `/sitemap.xml` say what they should and that `check.sh` shows the site working.

## Measurement

Measurement for Google Ad Grants (docs/DECISIONS.md, 20; the charity's `family/MEASUREMENT.md`) is off:
`[ads] measurement = false` and `tag = ""` in `config/settings.toml`. Turn it on only once the charity is registered
and its Google Ads account has the conversions set up, in this order:

1. Finish `[privacy_measurement]` in `config/wording.toml`: the charity number for `NNNNNNN`, and `updated`. Merge it.
2. The front door. On this server Where MPs Stand's Caddy front door sends its own content security policy in place
   of this site's, and it would block the Google tag. Apply the charity's `family/front-door-measurement.patch` to
   `wherempsstand` and run its `update.sh`; then add `MEASURED_SITES="wherelandlordsstand.com"` to
   `/opt/hansardgpt/deploy/.env` and run its `update.sh` again. Until `MEASURED_SITES` names this site, the front door
   sends what it sends today.
3. Add `LANDLORDS_ADS_MEASUREMENT=true` and `LANDLORDS_ADS_TAG=AW-…` to `/opt/wherelandlordsstand/deploy/.env`, run
   `bash update.sh && bash run-update.sh`, and approve the rebuilt pages from the email.
4. Check in a private window: the banner shows; "Reject" leaves no request to Google; "Accept" loads the tag;
   "Measurement choices" at the foot of a page opens the banner again; and
   `curl -sI https://wherelandlordsstand.com/ | grep -i content-security-policy` names `https://www.googletagmanager.com`.

To turn it off, remove the two lines from `.env`, run the update and approve, and take the site out of
`MEASURED_SITES`.

## Running it

Commands are run in `/opt/wherelandlordsstand/deploy`. Any `landlords` command runs in a one-off container:
`docker compose run --rm -T app landlords <command>`.

### Routine

- Every Thursday: read the weekly update's email, look at a few changed pages, and press Publish.
- At least twice a week: `landlords waiting`, then answer readers' reports and statements from landlords
  (docs/OPERATIONS.md, "Readers' reports, statements and missed searches"). The site promises a reply within 5
  working days.
- Every week: `landlords missed`, and add aliases for the real landlord names among the searches that found nothing
  (docs/OPERATIONS.md, "The register and names").
- When `landlords check` (or the weekly email) says a section of the rights page is due: check its sources, then
  update the section and its dates (docs/OPERATIONS.md, "The rights page").

### The weekly update

It runs every Thursday at 11.40 UK time (`landlords-update.timer`, which runs `deploy/run-update.sh`), after any
other site's update has finished (the shared lock). It emails a link to approve the new pages, with Publish and Undo
buttons (docs/OPERATIONS.md, "The weekly update, the email, and publishing"). Nothing needs to be run by hand. The
email waits in the outbox until it is sent: `bash send-mail.sh` sends anything still there (after a mail failure,
say). Sent emails are kept in the volume's `outbox/sent/` for 30 days.

### Reports, statements and hiding a page

- Readers' reports: `landlords reports list`. Close one with `landlords reports close <id> --outcome resolved
  --note "..."` (or `--outcome dismissed`), which deletes the reporter's email address. Add `--public-note "..."` to
  put a fix of ours in the corrections page's list at once.
- Statements from landlords (the right of reply): `landlords statements list` shows those waiting. Publish one with
  `landlords statements publish <id> --checked "how the sender was confirmed"`, or decline, update, withdraw or
  remove it. It goes on the live pages at once.
- Hiding a landlord's page while a concern about it is decided: `landlords hide landlords/<slug>/ --note "..."`,
  and `landlords unhide landlords/<slug>/` to put everything back.

docs/OPERATIONS.md explains each of these in full.

### New code

Merge it into `main` on GitHub, then run `bash /opt/wherelandlordsstand/deploy/update.sh`. It builds the new image,
restarts the site on it, waits for it to answer, and only then installs or refreshes the timers: if the build fails,
nothing has changed. The next weekly update rebuilds the pages.

Whichever command first opens the state database on new code makes any change the new code needs to its tables. So:

- don't run `update.sh` while a timer may be running: the backup at 04:52 UTC (a minute or two), the backup check at
  12:23 UTC, and the weekly update on Thursdays from 11.40 UK time (it can wait hours for another site's update);
- run no `landlords` command by hand until `update.sh` has finished.

The Docker build installs the shared package, wts-core, as the wheel of its release on GitHub (`github.com`, which
hands the download to `objects.githubusercontent.com`), so the server must be able to reach both, as it reaches PyPI.
No git is needed in the image. `uv.lock` holds the wheel's SHA-256, so a changed file fails the build.

### Caching

Stylesheets, scripts, fonts, icons and the link card are served from `/assets/` under names that change with their
content, and the front door and the site tell caches to keep them for a year. Pages and downloads are checked with
the server each time. So a new release needs no Cloudflare purge.

### Addresses

Each page has one address, its folder (`/landlords/abri-group/`), which every link and the canonical link name. The
site moves `…/index.html` there for good (301, keeping the query), and a folder asked for without its slash to the
address with it (301, from the site's root, so it keeps https). The container runs `landlords serve
--behind-proxy`, which also tells uvicorn to trust the front door's `X-Forwarded-Proto` from any address (the front
door reaches it over the Docker network, not from 127.0.0.1). That is safe only while the app's port is published on
the server's `127.0.0.1` alone (`deploy/docker-compose.yml`; `tests/test_api.py` checks it).

### Backups

Everything but the state database can be rebuilt from the publishers' files. The state database holds readers'
reports, statements, missed searches and approval links (docs/OPERATIONS.md, "The state database").

- Every night at 04:52 UTC, `landlords-backup.timer` copies it to `/opt/wherelandlordsstand/deploy/backups` (the
  last 14 kept) and to the charity's B2 bucket under this site's own names (each site deletes only its own old
  copies). Each copy is checked first (SQLite's integrity check): if the check fails, the command says
  `Backup failed: ...` and exits 1, so the alert email is sent, and nothing is kept, deleted or sent off-site.
- After each backup the same unit runs `landlords nightly`, which deletes email addresses whose time is up
  (docs/OPERATIONS.md, "Nightly housekeeping").
- A backup timer that has stopped sends no failure of its own, so every day at 12:23 UTC `landlords backup-check`
  (`landlords-backup-check.timer`) looks at the backups folder. It fails, and so sends the alert email, when the last
  backup or off-site copy is over two days old or the last off-site copy failed. By hand:
  `docker compose run --rm --no-deps -T app landlords backup-check --in /backups`.

To set up the off-site copy, once, copy the bucket and key from Where MPs Stand's settings and check them. Where MPs
Stand's settings are named `HANSARD_*`, its original name.

```bash
cd /opt/wherelandlordsstand/deploy
for k in BUCKET KEY_ID APPLICATION_KEY; do v=$(grep "^HANSARD_B2_$k=" /opt/hansardgpt/deploy/.env | cut -d= -f2-); \
  sed -i "/^LANDLORDS_B2_$k=/d" .env; echo "LANDLORDS_B2_$k=$v" >> .env; done
docker compose run --rm -T app landlords offsite                  # "ok": true
docker compose run --rm -T app landlords backup --to /backups     # ends "Off-site copy: stored in ..."
```

To put a backup back, with the site stopped (one from B2 goes in `backups/` first):

```bash
cd /opt/wherelandlordsstand/deploy && docker compose stop app
docker compose run --rm --no-deps app landlords restore /backups/landlords-state-<time>.sqlite.gz
docker compose up -d app
```

`restore` asks first (`--yes` skips the question). It unpacks the backup beside the database and checks it (SQLite's
integrity check, and that it is this site's database) before anything is replaced. The database it replaces is kept
as `state.db.before-restore`, which must be moved or deleted before another restore. Delete it once the site is known
to be right, as it holds email addresses as they stood.

### The nightly check

Set `LANDLORDS_CHECK_TOKEN` in `.env` to the family's check token, then run `update.sh` (docs/OPERATIONS.md, "The
nightly check"). Until then the address `/api/check` does not exist.

### Privacy

The privacy page (`[privacy]` in `config/wording.toml`) names Cloudflare and says visits are not logged. Keep it true:
`landlords serve` turns uvicorn's access log off, and the front door keeps none. While measurement is on, the page is
`[privacy_measurement]` instead ("Measurement", above).

## On the maintainer's own computer

The weekly update and publishing can be tried locally (docs/OPERATIONS.md, "The weekly update, the email, and
publishing"):

```bash
uv sync
uv run landlords update --no-fetch     # or run `landlords fetch` first
uv run landlords publish
uv run landlords serve                 # http://127.0.0.1:8000/
```
