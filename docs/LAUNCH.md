# Launch checklist (phase 4)

The site goes public only when the owner says so. This list is what stands between the code as it is and a public
launch. Ticked items are done in the repository; the rest need the owner, a reviewer, or the server.

## Done

- [x] Every landlord with 1,000 or more homes has a page; council areas, compare, rights, method, downloads,
      corrections, privacy, about, terms, accessibility and "not found" pages.
- [x] Every figure traces to its file and year; every sentence is in `config/wording.toml`, `config/rights.toml` or
      `config/pages.toml`.
- [x] Licences: our own work under CC BY 4.0 (docs/DECISIONS.md, 11), on the terms page and in the downloads.
- [x] Accessibility: every kind of page checked with axe-core against WCAG 2.2 AA, phone and desktop, light and dark,
      with no failures (3 November 2026); keyboard use checked by script. Recorded on the accessibility page.
- [x] No cookies, no third-party anything, no visit logs; a content security policy that allows only the site itself.
- [x] Weekly update into a new build, publishing by hand, rollback; nightly backups, on the server and off site.
- [x] A watch for new releases: TSM 2025/26 is listed as "waiting", and new documents in the regulator's collections
      are reported (`landlords fetch`).
- [x] One launch switch, `[site] launched`, off.

## Needs people (the brief's gates, and sign-offs)

- [ ] **Method review** by a housing-data reviewer (phase 2's gate): `docs/METHOD.md`, with its nine questions.
- [ ] **Testing with applicants** (phase 3's gate): `docs/USER-TESTING.md`.
- [ ] **Adviser sign-off** of the wording (`config/wording.toml`) and the rights page (`config/rights.toml`), including
      the plain-English meanings of the regulator's grades.
- [ ] **The ICO's pages** on FOI complaints, checked by hand (they refused automated requests).
- [ ] **The Ombudsman's reuse terms** (docs/DECISIONS.md, 9): send the drafted email; record the answer.
- [ ] **Display names**: check the 363 rule-made names in `data_static/landlords.csv`, and which name to lead with
      where adverts use another.
- [ ] **Name and domain** (docs/DECISIONS.md, 1), and confirm the contact address on the about and terms pages
      (`[site] contact`, now admin@wheretheystand.uk, as Where MPs Stand).

## Just before launch

- [ ] **TSM 2025/26**: last year's release came out on 4 November. When `landlords fetch` stops saying "waiting", add its
      headline figures to `config/reconciliation.toml`, run `landlords update`, read the change report and the
      reconciliation, and publish. Profiles then show 2025/26 with changes since 2024/25.
- [ ] **Rights page dates**: `landlords check` warns when a section is due. Due now: the Ombudsman's complaints
      section weekly while its IT incident lasts; Awaab's Law on 1 December 2026 (phase 2 should be in force).
- [ ] **Where Councils Stand's council list**: fixed on its branch `claude/dazzling-bardeen-dwkkk1` (4 November 2026).
      Once that is merged into its `main`, remove `where_councils_stand_codes` from `config/settings.toml` here.

## On the server (docs/DEPLOY.md)

1. Make `main` this repository's default branch (docs/DEPLOY.md).
2. Review and merge the change to `rj-mitchell/parentwheretheystand` that adds Where Landlords Stand (prepared
   4 November 2026 as a patch; its README gains a section "Where Landlords Stand").
3. On the server (already moved in to `/opt/where-they-stand`): pull, clone this repository into `apps/`, create
   `env/landlords.env`, `bash scripts/update.sh`, then the first `landlords update` and `landlords publish` through
   `scripts/run-job.sh`. Docker builds this site's image there for the first time: watch it.
4. Look at it privately on port 8004 through an SSH tunnel; send a test report through the corrections form and close
   it (`landlords reports --close <id>`); `bash scripts/check.sh`.
5. **Launch**: point the domain's DNS at the server; set `LANDLORDS_DOMAIN`, `LANDLORDS_REDIRECTS` and add `landlords`
   to `PUBLIC_SITES` in `.env`; set `LANDLORDS_SITE_URL` and `LANDLORDS_LAUNCHED=true` in `env/landlords.env`;
   `bash scripts/update.sh`; then `landlords update && landlords publish`. Check: no "test version" line,
   `robots.txt` allows crawling, `/sitemap.xml` lists the pages, `check.sh` shows https working.
6. Tell the sister sites' about pages.

## After launch

- Every Thursday: read the update's `build-info.json` and `change-report.json`, look at a few changed pages, publish.
- Weekly: `landlords reports` (reply, fix our mistakes, log them in `data_static/corrections.csv`) and
  `landlords missed` (add aliases for real names).
- When `landlords check` warns about a rights page date: check the sources, update the section and its dates.
