# Putting the site on a server

**Not deployed.** The site goes live only when the owner says so (docs/DECISIONS.md, ground rules). This page is
ready for that day. Until then, `landlords serve` shows it on one computer only.

Where Landlords Stand is planned to run on Where They Stand's shared server, beside Where MPs Stand, Where Councils
Stand and Where Countries Stand, in its own folder (`/opt/wherelandlordsstand`) with its own container and data.
Where MPs Stand's web server (Caddy) is the front door for every site on the server: it answers the site's domain
through Cloudflare and passes visitors to this site's container over the shared Docker network (`sites`). See "Other
sites on this server" in Where MPs Stand's `docs/HOSTING.md`.

## What it needs

Very little: the pages are static files built from a few megabytes of data. The container is limited to 1 GB of
memory. Disk: about 30 MB per build, and the last six builds are kept (`landlords publish`), plus the raw files
(about 25 MB a year). No API keys: it uses no AI and no paid services.

## Steps

0. **A `main` branch.** The repository was created empty, so its first branch (`claude/dazzling-bardeen-dwkkk1`)
   became the default and there is no `main`. On GitHub: open a pull request from that branch, or create `main` from
   it (Branches → New branch), then Settings → General → Default branch → `main`. The server follows `main`
   (`update.sh` pulls the branch it was cloned on).
1. **Choose the domain** (the name is a working title: docs/DECISIONS.md, 1), and set `[site] url` in
   `config/settings.toml`.
2. **Cloudflare**, as for the other sites: an **A** record for `@` pointing at the server, **Proxied**, `www`
   redirected to it; SSL/TLS **Full (strict)**; an **origin certificate** for the domain (leave its page open).
3. **Code**, on the server, as root:
   ```bash
   git clone https://github.com/rj-mitchell/wherelandlordsstand /opt/wherelandlordsstand
   cd /opt/wherelandlordsstand/deploy && cp .env.example .env
   ```
4. **Start it:**
   ```bash
   bash /opt/wherelandlordsstand/deploy/update.sh
   ```
   It builds and starts the container and installs the weekly update and nightly backup timers.
5. **First data and pages** (a few minutes; the publishers' servers are asked one thing at a time):
   ```bash
   cd /opt/wherelandlordsstand/deploy
   docker compose run --rm -T app landlords update      # fetch, load, check, score, build: data/builds/<time>
   docker compose run --rm -T app landlords publish     # make that build live
   ```
6. **The front door:** add `<domain>=wherelandlordsstand` to `SITES` in `/opt/hansardgpt/deploy/.env`, then paste the
   origin certificate:
   ```bash
   bash /opt/hansardgpt/deploy/cloudflare.sh site <domain>
   ```
7. **Check:** visit the site, search for a landlord, send a test report through the corrections form (then close it:
   `landlords reports --close <id>`), and run `bash /opt/hansardgpt/deploy/check.sh`.
8. **The launch switch** (docs/LAUNCH.md): set `[site] url` and `launched = true` in `config/settings.toml`, merge,
   update the server, then `landlords update` and `landlords publish`. That takes off the "test version" line and
   `noindex`, opens robots.txt and writes the sitemap. Until then the site can run on the server as a private test.

## Running it

Commands are run in `/opt/wherelandlordsstand/deploy`, each in a one-off container:
`docker compose run --rm -T app landlords <command>`.

* **Updates** run every Thursday morning (`landlords-update.timer`). They build into `data/builds/`; they never
  publish. Read the change report, then publish by hand (docs/OPERATIONS.md):
  ```bash
  docker compose run --rm -T app sh -c 'ls /data/builds; cat /data/builds/$(ls /data/builds | tail -1)/build-info.json'
  docker compose run --rm -T app landlords publish
  docker compose run --rm -T app landlords rollback   # if something is wrong
  ```
* **Readers' reports:** `landlords reports`; close one with `landlords reports --close <id> --outcome "..."`, which
  deletes the reporter's email address. Fixes to our own mistakes go in the public log, `data_static/corrections.csv`.
* **Missed searches:** `landlords missed` lists the words people searched for without a result: candidates for new
  aliases (docs/OPERATIONS.md, "The register and names").
* **Backups:** the state database (reports, missed searches) is copied every night to
  `/opt/wherelandlordsstand/deploy/backups`, the last 14 kept, and to the charity's Backblaze B2 bucket, the last 60
  kept there beside the other sites' backups (each site's have their own names, and each deletes only its own).
  Everything else can be rebuilt from the raw files. To set up the off-site copy, once, copy the bucket and key from
  Where MPs Stand's settings and check them:
  ```bash
  cd /opt/wherelandlordsstand/deploy
  for k in BUCKET KEY_ID APPLICATION_KEY; do v=$(grep "^HANSARD_B2_$k=" /opt/hansardgpt/deploy/.env | cut -d= -f2-); \
    sed -i "/^LANDLORDS_B2_$k=/d" .env; echo "LANDLORDS_B2_$k=$v" >> .env; done
  docker compose run --rm -T app landlords offsite                  # "ok": true
  docker compose run --rm -T app landlords backup --to /backups     # ends "Off-site copy: stored in ..."
  ```
* **New code:** merge into `main` on GitHub, then `bash /opt/wherelandlordsstand/deploy/update.sh`.
* **The privacy page** (`[privacy]` in `config/wording.toml`) names Cloudflare and says visits are not logged
  (`landlords serve` turns uvicorn's access log off). Keep it true.

## On your own computer

```bash
uv sync
uv run landlords update --no-fetch     # or `landlords fetch` first
uv run landlords publish
uv run landlords serve                 # http://127.0.0.1:8000/
```
