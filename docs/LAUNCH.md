# From alpha to launch (phase 4)

The site is public at wherelandlordsstand.com, in alpha (docs/DECISIONS.md, 12). New pages go live only when the
owner approves them by email, and search engines are kept out. The three gates under "Needs people" (the method
review, testing with applicants, the adviser's sign-off) are the conditions for beta. Launch, which lets search
engines in, comes when the owner says so. Ticked items are done; the rest need the owner, a reviewer, or the server.

## Done

- [x] Every landlord with 1,000 or more homes has a page; council areas, compare, rights, method, downloads,
      corrections, privacy, about, terms, accessibility and "not found" pages.
- [x] Every figure traces to its file and year; every sentence is in `config/wording.toml`, `config/rights.toml` or
      `config/pages.toml`.
- [x] Licences: our own work under CC BY 4.0 (docs/DECISIONS.md, 11), on the terms page and in the downloads.
- [x] Accessibility: every kind of page checked with axe-core against WCAG 2.2 AA, phone and desktop, light and dark,
      with no failures (6 November 2026); keyboard use checked by script. Recorded on the accessibility page.
- [x] No cookies, no third-party anything, no visit logs; a content security policy that allows only the site itself.
- [x] Weekly update into a new build, approved by the owner by email with Publish and Undo buttons, whether or not
      the site has launched (docs/DECISIONS.md, 12); publishing and rollback by hand; nightly backups, on the server
      and off site.
- [x] A watch for new releases: TSM 2025/26 was loaded the day it came out, TSM 2026/27 is listed as "waiting", and
      new documents in the regulator's collections are reported (`landlords fetch`).
- [x] One launch switch, `[site] launched`, off. It only lets search engines in.

## Needs people (the brief's gates, and sign-offs)

- [ ] **Method review** by a housing-data reviewer (phase 2's gate): `docs/METHOD.md`, with its nine questions.
- [ ] **Testing with applicants** (phase 3's gate): `docs/USER-TESTING.md`.
- [ ] **Adviser sign-off** of the wording (`config/wording.toml`) and the rights page (`config/rights.toml`), including
      the plain-English meanings of the regulator's grades.
- [ ] **The ICO's pages** on FOI complaints, checked by hand (they refused automated requests).
- [ ] **The Ombudsman's reuse terms** (docs/DECISIONS.md, 9): send the drafted email; record the answer.
- [ ] **Display names**: check the 363 rule-made names in `data_static/landlords.csv`, and which name to lead with
      where adverts use another.
- [x] **Name and domain** (docs/DECISIONS.md, 1): Where Landlords Stand, at wherelandlordsstand.com.
- [ ] **The contact address** admin@wherelandlordsstand.com (`[site] contact` and `feedback_email`, on the alpha
      banner, the about, terms and accessibility pages) must receive mail before launch: the owner is setting it up.

## Before beta and launch

- [x] **TSM 2025/26**: published 5 November 2026; loaded and reconciled the same day (docs/DATA.md).
- [x] **Landlords with no 2025/26 results of their own**: all seven accounted for from the regulator's files, and
      their pages say who reports for them now (docs/DATA.md, `data_static/reporting.csv`).
- [ ] **Rights page dates**: `landlords check` warns when a section is due. The Ombudsman's complaints section is
      due weekly while its IT incident lasts. Awaab's Law was brought up to date on 6 November 2026 (phase 2 is still
      a draft); check it again on 1 December 2026, once phase 2 should be in force.
- [x] **Where Councils Stand's council list**: Barnsley's and Sheffield's codes fixed there (merged 4 November
      2026), and the temporary mapping removed here.

## On the server (docs/DEPLOY.md)

The site runs beside the others, with Where MPs Stand's web server as the front door, as Where Countries Stand and
Where Councils Stand do.

- [x] Steps 1–4 of docs/DEPLOY.md: cloned into `/opt/wherelandlordsstand`, `deploy/update.sh`, the first pages.
- [x] Step 6 of docs/DEPLOY.md, the domain: Cloudflare and an origin certificate for the domain, and the site in
      `SITES` on Where MPs Stand's side. The site is public, in alpha.
- [ ] Step 5 of docs/DEPLOY.md, **the weekly email**: check it with `landlords email-test`. New pages are approved
      from it, so without it nothing new is published (and each update fails to say so).
- [x] `main` is this repository's default branch (docs/DEPLOY.md).
- [ ] **Launch**, when the owner says so ("Launch" in docs/DEPLOY.md): `LANDLORDS_LAUNCHED=true` in `deploy/.env`,
      then `landlords update`, and approve the new pages. Check: `robots.txt` allows crawling, `/sitemap.xml` lists
      the pages, `check.sh` shows the site working.
- [x] The family binding (6 November 2026): every page carries "A Where They Stand project" and the family shelf,
      which links every sister site, and the about page names them all.
- [ ] Where Councils Stand's council pages link back here (being added there, 6 November 2026).

## Every week

- Every Thursday (in alpha too): read the update's email, look at a few changed pages, and press Publish.
- Weekly: `landlords reports` (reply, fix our mistakes, log them in `data_static/corrections.csv`) and
  `landlords missed` (add aliases for real names).
- When `landlords check` warns about a rights page date: check the sources, update the section and its dates.
