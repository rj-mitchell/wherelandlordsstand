# Putting the site on a server

**Not public yet.** The site is released only when the owner says so (docs/LAUNCH.md).

## On Where They Stand's shared server (the plan)

The Where They Stand sites share one server, set up by the private repository `rj-mitchell/parentwheretheystand`
(`/opt/where-they-stand/server`). It runs every site in one Docker project behind one Caddy, with each site's jobs
taking turns under one lock, nightly backups to the shared B2 bucket and a watchdog. Its README says which sites are
public (`PUBLIC_SITES`) and how to release one. **That repository, not this one's `deploy/` folder, is how this site
runs there**; never run both on the same server.

Where Landlords Stand is added to it by a change to that repository (prepared 4 November 2026, to be reviewed and
merged by the owner): its site and job containers (private port 8004), its Caddy site, `env/landlords.env`, a weekly
update that builds but never publishes, its backups, and its place in `check.sh`. Its README section "Where Landlords
Stand" has the commands. In short, on a server that has already moved in:

```bash
cd /opt/where-they-stand/server && git pull --ff-only
git clone -b main https://github.com/rj-mitchell/wherelandlordsstand ../apps/wherelandlordsstand
cp env/landlords.env.example env/landlords.env && mkdir -p backups/landlords
bash scripts/update.sh
bash scripts/run-job.sh landlords-job landlords update     # the first pages, published at once (or wait for Thursday)
```

Then look at it privately: `ssh -L 8004:127.0.0.1:8004 root@<server>` and open http://localhost:8004.

**Releasing it:** a domain whose DNS A records point at the server; `LANDLORDS_DOMAIN`, `LANDLORDS_REDIRECTS` and
`landlords` in `PUBLIC_SITES` in the server's `.env`; `LANDLORDS_SITE_URL` and `LANDLORDS_LAUNCHED=true` in
`env/landlords.env` (they override `[site]` in `config/settings.toml`); `bash scripts/update.sh`; then rebuild and
publish the pages: `bash scripts/run-job.sh landlords-job sh -c 'landlords update && landlords publish'`. From then on
new pages wait for approval by email.

**This repository's default branch must be `main`.** It was created empty, so its first branch
(`claude/dazzling-bardeen-dwkkk1`) became the default and there is no `main`. On GitHub, create `main` from that branch
(or merge a pull request into it) and make it the default (Settings → General → Default branch). The server pulls the
branch it cloned.

## Running it

Commands go through the shared server's job lock: `bash scripts/run-job.sh landlords-job landlords <command>`, in
`/opt/where-they-stand/server`.

* **Updates** run every Thursday (`where-they-stand-landlords-update.timer`). Before launch they publish new pages
  themselves; after launch they email a link to approve them, with a Publish button and an Undo button
  (docs/OPERATIONS.md, "The weekly update"). Nothing to run by hand. For the email, put `LANDLORDS_SMTP_USER` and
  `LANDLORDS_SMTP_PASSWORD` (a Gmail app password) in `env/landlords.env`, then check it:
  `bash scripts/run-job.sh landlords-job landlords email-test`.
* **Readers' reports:** `landlords reports`; close one with `landlords reports --close <id> --outcome "..."`, which
  deletes the reporter's email address. Fixes to our own mistakes go in the public log, `data_static/corrections.csv`.
* **Missed searches:** `landlords missed`: candidates for new aliases (docs/OPERATIONS.md, "The register and names").
* **Backups:** the shared server's `scripts/backup.sh` copies the state database (reports, missed searches) every
  night to `backups/landlords/` and the shared B2 bucket. Everything else can be rebuilt from the raw files.
* **New code:** merge into `main` on GitHub, then `bash scripts/update.sh` on the server (it updates every site).
* **The privacy page** (`[privacy]` in `config/wording.toml`) names Cloudflare and says visits are not logged
  (`landlords serve` turns uvicorn's access log off). Keep it true.

## Running it on its own, elsewhere

`deploy/` (a compose file, timers, `update.sh`) runs the site alone on a server of its own, like each sibling's own
`deploy/`. Its own nightly backup can send copies to B2 itself (`LANDLORDS_B2_…` in `deploy/.env`, `landlords
offsite`). It is not for the shared server.

## On your own computer

```bash
uv sync
uv run landlords update --no-fetch     # or `landlords fetch` first
uv run landlords publish
uv run landlords serve                 # http://127.0.0.1:8000/
```
