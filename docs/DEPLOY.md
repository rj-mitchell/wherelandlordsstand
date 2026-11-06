# Putting the site on a server

**Not public yet.** The site is released only when the owner says so (docs/LAUNCH.md).

Where Landlords Stand runs on the charity's shared server the same way as Where Countries Stand and Where Councils
Stand: in its own folder (`/opt/wherelandlordsstand`) with its own container, data, settings and timers. Where MPs
Stand's web server (Caddy) is the front door for every site on the server. It answers each site's domain through
Cloudflare, with the same protections as its own site, and passes visitors to the site's container over a shared
Docker network (`sites`). See "Other sites on this server" in Where MPs Stand's `docs/HOSTING.md`.

Until it has a domain, the site runs and updates all the same, and can be looked at privately.

## What it needs

Little: well under 1 GB of memory (the container is limited to 1 GB), and about 1 GB of disk for the downloaded
files and a few builds of the pages. No API keys and no paid services.

## Steps

1. **Code and settings**, on the server, as root:
   ```bash
   git clone -b main https://github.com/rj-mitchell/wherelandlordsstand /opt/wherelandlordsstand
   cd /opt/wherelandlordsstand/deploy && cp .env.example .env
   ```
   Everything in `.env` can stay empty for now.
2. **Start it:**
   ```bash
   bash /opt/wherelandlordsstand/deploy/update.sh
   ```
   It builds and starts the site, and installs its weekly update and nightly backup timers.
3. **The first pages** (a few minutes: it downloads the regulator's and the Ombudsman's files, then builds and
   publishes the pages, as nothing is public yet):
   ```bash
   cd /opt/wherelandlordsstand/deploy && docker compose run --rm -T app landlords update
   ```
4. **Look at it privately**, from your own computer:
   ```bash
   ssh -L 8004:127.0.0.1:8004 root@<server>
   ```
   then open http://localhost:8004. The port answers on the server itself only, never on the internet.
5. **The weekly email** (to wheretheystanduk@gmail.com), once the server's own email is set up (Where MPs Stand's
   `docs/HOSTING.md`, "Email from the server"). This copies its account into this site's settings, then sends a test:
   ```bash
   cd /opt/wherelandlordsstand/deploy
   for k in FROM:USER APP_PASSWORD:PASSWORD; do v=$(grep "^MAIL_${k%%:*}=" /etc/wheretheystand/mail.env | cut -d= -f2-); \
     sed -i "/^LANDLORDS_SMTP_${k#*:}=/d" .env; echo "LANDLORDS_SMTP_${k#*:}=$v" >> .env; done
   bash update.sh && docker compose run --rm -T app landlords email-test
   ```
   Failed updates and backups also email the alerts address, as every site's do.
6. **Check:** `bash /opt/hansardgpt/deploy/check.sh` shows the memory left. The site appears in its list of other
   sites once it is in `SITES` ("Releasing it").

## Releasing it

When the owner says so, and once the name and domain are settled (docs/DECISIONS.md, 1):

1. **Cloudflare**, for the domain: as for the other sites ("Other sites on this server" in Where MPs Stand's
   `docs/HOSTING.md`): an **A** record for `@` pointing at the server, **Proxied**; `www` redirected to it by a
   redirect rule; SSL/TLS **Full (strict)**; and an **origin certificate** for the domain (leave its page open).
2. **The front door:** add `wherelandlordsstand.com=wherelandlordsstand` (with the real domain) to `SITES` in
   `/opt/hansardgpt/deploy/.env`, then paste the origin certificate:
   ```bash
   bash /opt/hansardgpt/deploy/cloudflare.sh site wherelandlordsstand.com
   ```
3. **Go public:** in `/opt/wherelandlordsstand/deploy/.env`, set `LANDLORDS_SITE_URL=https://wherelandlordsstand.com`
   and `LANDLORDS_LAUNCHED=true`, then rebuild and publish the pages:
   ```bash
   cd /opt/wherelandlordsstand/deploy && bash update.sh
   docker compose run --rm -T app sh -c 'landlords update && landlords publish'
   ```
   Check: `robots.txt` allows crawling, `/sitemap.xml` lists the pages, and
   `bash /opt/hansardgpt/deploy/check.sh` says the site works. From then on, new pages wait for approval by email.

**This repository's default branch must be `main`** (GitHub: Settings → General → Default branch). The server pulls
the branch it cloned.

## Running it

Commands are run in `/opt/wherelandlordsstand/deploy`. Any `landlords` command runs in a one-off container:
`docker compose run --rm -T app landlords <command>`.

* **Updates** run every Thursday at 11.40 UK time (`landlords-update.timer`), clear of the other sites' updates.
  Before launch they publish new pages themselves. After launch they email a link to approve them, with a Publish
  button and an Undo button (docs/OPERATIONS.md, "The weekly update"). Nothing to run by hand.
* **Readers' reports:** `landlords reports`; close one with `landlords reports --close <id> --outcome "..."`, which
  deletes the reporter's email address. Fixes to our own mistakes go in the public log, `data_static/corrections.csv`.
* **Missed searches:** `landlords missed`: candidates for new aliases (docs/OPERATIONS.md, "The register and names").
* **New code:** merge it into `main` on GitHub, then `bash /opt/wherelandlordsstand/deploy/update.sh`. The next
  update rebuilds the pages.
* **Backups:** everything but the state database (readers' reports, missed searches, approval links) can be rebuilt
  from the raw files. That database is copied every night (`landlords-backup.timer`) to
  `/opt/wherelandlordsstand/deploy/backups`, the last 14 kept, and to the charity's Backblaze B2 bucket beside the other
  sites' backups (each site's have their own names, and each deletes only its own old copies). To set up the
  off-site copy, once, copy the bucket and key from Where MPs Stand's settings and check them:
  ```bash
  cd /opt/wherelandlordsstand/deploy
  for k in BUCKET KEY_ID APPLICATION_KEY; do v=$(grep "^HANSARD_B2_$k=" /opt/hansardgpt/deploy/.env | cut -d= -f2-); \
    sed -i "/^LANDLORDS_B2_$k=/d" .env; echo "LANDLORDS_B2_$k=$v" >> .env; done
  docker compose run --rm -T app landlords offsite                  # "ok": true
  docker compose run --rm -T app landlords backup --to /backups     # ends "Off-site copy: stored in ..."
  ```
  To put a backup back (one from B2 goes in `backups/` first), with the site stopped:
  ```bash
  cd /opt/wherelandlordsstand/deploy && docker compose stop app
  docker compose run --rm -T app sh -c \
    'rm -f /data/state.db-wal /data/state.db-shm && gunzip -c /backups/landlords-state-<time>.sqlite.gz > /data/state.db'
  docker compose up -d app
  ```
* **The privacy page** (`[privacy]` in `config/wording.toml`) names Cloudflare and says visits are not logged
  (`landlords serve` turns uvicorn's access log off, and the front door keeps none). Keep it true.

## On your own computer

```bash
uv sync
uv run landlords update --no-fetch     # or `landlords fetch` first
uv run landlords publish
uv run landlords serve                 # http://127.0.0.1:8000/
```
