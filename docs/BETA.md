# Beta

What must happen before the site leaves alpha, and the other open items. It is for the owner and the maintainer.

The site is live at [wherelandlordsstand.com](https://wherelandlordsstand.com) as a public alpha, and search engines
have been allowed to index it since November 2026 (docs/DECISIONS.md, 12). The alpha banner stays until beta.

## Gates to beta

Beta needs all three:

- A housing-data reviewer has reviewed the method: [METHOD.md](METHOD.md), with its questions for the reviewer.
- The site has been tested with people who bid for social homes: [USER-TESTING.md](USER-TESTING.md).
- An adviser has signed off the wording (`config/wording.toml`) and the rights page (`config/rights.toml`),
  including the plain-English meanings of the regulator's grades.

Record each result as a decision in [DECISIONS.md](DECISIONS.md).

## Other open items

- The Ombudsman's reuse terms: send the drafted email and record the answer (docs/DECISIONS.md, 9; docs/DATA.md,
  "Open questions").
- Display names: check the 363 names made by rule in `data_static/landlords.csv`, and decide which name to lead with
  where adverts use another (docs/DATA.md, "Open questions").
- The Information Commissioner's pages on freedom of information complaints, quoted on the rights page: check them by
  hand, as they refuse automated requests.
- Confirm that admin@wherelandlordsstand.com receives mail. It is the contact address on the alpha banner and the
  about, terms and accessibility pages (`[site] contact` and `feedback_email` in `config/settings.toml`).
- Confirm the weekly email reaches the owner, with `landlords email-test` (docs/DEPLOY.md, step 5). New pages are
  approved from it, so without it nothing new is published.
- Where Councils Stand's council pages are to link back here; that work is in Where Councils Stand's repository
  (6 November 2026).
