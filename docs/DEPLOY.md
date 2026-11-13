# Deploying Where Landlords Stand

**Public, in alpha**, at wherelandlordsstand.com (docs/DECISIONS.md, 12). New pages go live only when the owner
approves them by email. Search engines are kept out until launch (docs/LAUNCH.md).

This page has only this site's own steps. The site runs on the charity's shared server, in its own folder
(`/opt/wherelandlordsstand`) with its own container, data, settings and timers, beside the charity's other sites.
Everything the sites share is in Where MPs Stand's
[`docs/HOSTING.md`](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md), the manual for the
shared server until the family's own operations document exists:

| Shared part | Where it is described |
|---|---|
| The front door (Caddy, in Where MPs Stand's checkout at `/opt/hansardgpt`), which answers this site's domain and passes visitors to its container | [Other sites on this server](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md#other-sites-on-this-server) |
| Cloudflare: the DNS record, `www` redirect, Full (strict) and the origin certificate | [Cloudflare protection](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md#cloudflare-protection-optional) and "Adding a site" under [Other sites on this server](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md#other-sites-on-this-server) |
| Email from the server, and failure alerts | [Email from the server](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md#email-from-the-server) |
| The Backblaze B2 bucket for off-site backups | [Backups](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md#backups) |
| The server-wide update lock, the health check and the update times of every site | [Other sites on this server](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md#other-sites-on-this-server) |

## What it needs

Well under 1 GB of memory (the container is limited to 1 GB), and about 1 GB of disk for the downloaded files and a
few builds of the pages. No API keys and no paid services.

## Setting it up

On the server, as root:

1. **Code and settings:**
   ```bash
   git clone -b main https://github.com/rj-mitchell/wherelandlordsstand /opt/wherelandlordsstand
   cd /opt/wherelandlordsstand/deploy && cp .env.example .env
   ```
   Everything in `.env` can stay empty to begin with.
2. **Start it:** `bash /opt/wherelandlordsstand/deploy/update.sh` builds and starts the site, and installs its weekly
   update and nightly backup timers.
3. **The first pages** (a few minutes: it downloads the regulator's and the Ombudsman's files, then builds and
   publishes the pages, as none are live yet; every later build waits for approval). It is the weekly update, run
   now: it waits for any other site's update to finish, then sends its email (step 5):
   ```bash
   bash /opt/wherelandlordsstand/deploy/run-update.sh
   ```
4. **Look at it privately** from another computer: `ssh -L 8004:127.0.0.1:8004 root@<server>`, then open
   http://localhost:8004. The port answers on the server itself only.
5. **The weekly email**, once the server's own email is set up (`mail.sh setup`; see above). New pages are approved
   from this email, so without it nothing new is published, and each update fails to say so. The site keeps no mail
   password of its own: the update, in its container, leaves the email in the outbox in its data volume, and
   `deploy/run-update.sh` then sends it on the server with the shared `mail.sh` (`deploy/send-mail.sh`;
   docs/OPERATIONS.md, "The weekly update, the email, and publishing"). Send a test the same way:
   ```bash
   cd /opt/wherelandlordsstand/deploy
   docker compose run --rm -T app landlords email-test && bash send-mail.sh
   ```
   It arrives from the charity's account, as "Where They Stand", with a subject starting "Where Landlords Stand".
6. **The domain:** Cloudflare and the front door, as for any site on the server ("Adding a site", linked above), with
   `wherelandlordsstand.com=wherelandlordsstand` in `SITES` and
   `bash /opt/hansardgpt/deploy/cloudflare.sh site wherelandlordsstand.com`. Done: the site is public, in alpha.
7. **Check:** `bash /opt/hansardgpt/deploy/check.sh` lists the site and the memory left.

## Launch

When the owner says so (docs/LAUNCH.md): in `/opt/wherelandlordsstand/deploy/.env`, set `LANDLORDS_LAUNCHED=true`,
then rebuild the pages:
```bash
cd /opt/wherelandlordsstand/deploy && bash update.sh && bash run-update.sh
```
and approve them from the email. Check that `robots.txt` allows crawling, `/sitemap.xml` lists the pages and
`check.sh` says the site works.

**This repository's default branch must be `main`** (GitHub: Settings → General → Default branch). The server pulls
the branch it cloned.

## Running it

Commands are run in `/opt/wherelandlordsstand/deploy`. Any `landlords` command runs in a one-off container:
`docker compose run --rm -T app landlords <command>`.

* **Updates** run every Thursday at 11.40 UK time (`landlords-update.timer`, which runs `deploy/run-update.sh`), and
  wait for any other site's update first (the shared lock). Each emails a link to approve the new pages, with Publish
  and Undo buttons (docs/OPERATIONS.md, "The weekly update"). Nothing to run by hand. The email waits in the outbox
  until it is sent: `bash send-mail.sh` sends anything still there (after a mail failure, say), and sent ones are kept
  in the volume's `outbox/sent/` for 30 days.
* **Readers' reports:** `landlords reports list`; close one with `landlords reports close <id> --outcome resolved
  --note "..."` (or `--outcome dismissed`), which deletes the reporter's email address. Fixes to our own mistakes go
  in the public log, `data_static/corrections.csv`.
* **Statements from landlords** (the right of reply): `landlords statements list` shows those waiting; publish one
  with `landlords statements publish <id> --checked "how you confirmed who sent it"`, or decline, update, withdraw
  or remove it (docs/OPERATIONS.md, "Readers' reports, statements and missed searches"). It goes on the live pages at
  once. `landlords waiting` counts what is waiting, and for how long.
* **Missed searches:** `landlords missed`: candidates for new aliases (docs/OPERATIONS.md, "The register and names").
* **New code:** merge it into `main` on GitHub, then `bash /opt/wherelandlordsstand/deploy/update.sh`. The next
  update rebuilds the pages.
* **Caching.** Stylesheets, scripts, fonts, icons and the link card are served from `/assets/` under names that change
  with their content, and the front door and the site tell caches to keep them for a year. Pages and downloads are
  checked with the server each time. So a new release needs no Cloudflare purge.
* **Backups:** everything but the state database (readers' reports, statements, missed searches, approval links) can be rebuilt
  from the raw files. That database is copied every night (`landlords-backup.timer`) to
  `/opt/wherelandlordsstand/deploy/backups`, the last 14 kept, and to the charity's B2 bucket under this site's own
  names (each site deletes only its own old copies). Each copy is checked before it is kept (SQLite's integrity
  check, as the sister sites' backups are): if it fails, the command says `Backup failed: ...` and exits 1, so the
  alert email is sent, and nothing is kept, deleted or sent off-site. After each night's backup the same unit runs
  `landlords nightly`, which deletes email addresses whose time is up (docs/OPERATIONS.md). A backup timer that has
  stopped sends no failure of its own, so every day at 12:23 UTC `landlords backup-check`
  (`landlords-backup-check.timer`) looks at the backups folder: it fails, and so sends the alert email, when the last
  backup or off-site copy is over two days old or the last off-site copy failed. By hand:
  `docker compose run --rm --no-deps -T app landlords backup-check --in /backups`. To set up the off-site copy, once,
  copy the bucket and key from Where MPs Stand's settings and check them:
  ```bash
  cd /opt/wherelandlordsstand/deploy
  for k in BUCKET KEY_ID APPLICATION_KEY; do v=$(grep "^HANSARD_B2_$k=" /opt/hansardgpt/deploy/.env | cut -d= -f2-); \
    sed -i "/^LANDLORDS_B2_$k=/d" .env; echo "LANDLORDS_B2_$k=$v" >> .env; done
  docker compose run --rm -T app landlords offsite                  # "ok": true
  docker compose run --rm -T app landlords backup --to /backups     # ends "Off-site copy: stored in ..."
  ```
  (`HANSARD_*` is Where MPs Stand's settings' original name, kept because renaming it would break the server.)
  To put a backup back (one from B2 goes in `backups/` first), with the site stopped:
  ```bash
  cd /opt/wherelandlordsstand/deploy && docker compose stop app
  docker compose run --rm --no-deps app landlords restore /backups/landlords-state-<time>.sqlite.gz
  docker compose up -d app
  ```
  `restore` asks first (`--yes` to skip the question). It unpacks the backup beside the database and checks it
  (SQLite's integrity check, and that it is this site's database) before anything is replaced; the database it
  replaces is kept as `state.db.before-restore`, which must be moved or deleted before another restore. A backup made
  before the site moved onto the shared package can be put back too: its rows are brought across when the site
  starts (docs/OPERATIONS.md, "The state database").
* **The Docker build** installs the shared package (wts-core) as the wheel of its release, from GitHub's releases
  (`github.com`, which hands the download to `objects.githubusercontent.com`): the server must
  be able to reach both, as it reaches PyPI. No git is needed in the image. `uv.lock` holds the wheel's SHA-256, so a
  changed file fails the build.
* **The nightly check:** set `LANDLORDS_CHECK_TOKEN` in `.env` to the family's check token, then run `update.sh`
  (docs/OPERATIONS.md, "The nightly check"). Until then the address `/api/check` does not exist.
* **The privacy page** (`[privacy]` in `config/wording.toml`) names Cloudflare and says visits are not logged
  (`landlords serve` turns uvicorn's access log off, and the front door keeps none). Keep it true.

## On your own computer

```bash
uv sync
uv run landlords update --no-fetch     # or `landlords fetch` first
uv run landlords publish
uv run landlords serve                 # http://127.0.0.1:8000/
```
