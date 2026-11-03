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
- [ ] **Where Councils Stand's council list**: fix Barnsley's and Sheffield's codes there (E08000038, E08000039), then
      remove `where_councils_stand_codes` from `config/settings.toml`.

## On the server (docs/DEPLOY.md)

1. Cloudflare and the origin certificate for the domain.
2. Clone to `/opt/wherelandlordsstand`; `cp deploy/.env.example deploy/.env`; copy the B2 bucket and key across.
3. `bash /opt/wherelandlordsstand/deploy/update.sh`. The first time, Docker builds the image: it has not been built
   in the development environment, so watch the first build.
4. While still a test: `landlords update`, `landlords publish`, add the domain to the front door, check the site
   privately.
5. **Launch**: set `[site] url = "https://<domain>"` and `launched = true` in `config/settings.toml`, merge, run
   `update.sh`, then `landlords update` and `landlords publish`. Check: no "test version" line, `robots.txt` allows
   crawling, `/sitemap.xml` lists the pages, a test report through the corrections form arrives and closes.
6. `bash /opt/hansardgpt/deploy/check.sh`, and tell the sister sites' about pages.

## After launch

- Every Thursday: read the update's `build-info.json` and `change-report.json`, look at a few changed pages, publish.
- Weekly: `landlords reports` (reply, fix our mistakes, log them in `data_static/corrections.csv`) and
  `landlords missed` (add aliases for real names).
- When `landlords check` warns about a rights page date: check the sources, update the section and its dates.
