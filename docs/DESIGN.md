# Design

Where Landlords Stand uses the Where They Stand family's design (family kit 2.0): white pages, light grey panels,
Source Serif 4 for headings and Source Sans 3 for everything else. Each family site has its own cloth colour, shown
as a solid band across the top of every page. This site's cloth is roof slate, `#40484D`, on the United Kingdom
shelf. The family's rules are in its style guide
(`family/GLOSSARY.md`, "Design", in the charity's private repository).

The family shares its binding (the header endorsement, the footer shelf, the icons and the link card) so that
someone who has seen one site recognises the next. The pages themselves are this site's own.

## Independence and neutrality

- No landlord's or the regulator's logo, colours or house style, and nothing that resembles them.
- The family's independence line is in the footer of every page: "Independent. Not affiliated with the Regulator of
  Social Housing, the Housing Ombudsman Service or any landlord." The about and terms pages have the full line.
- No colour means good or bad. A band is four slate squares, filled from the left (one for the bottom quarter,
  four for the top), never red to green, because a band is a position among similar landlords and is not a verdict.
  The regulator's grade is shown in a plain box, whatever the grade.
- Slate is a neutral grey, so the United Kingdom shelf's rule against party colours holds.

## The family kit

The kit's files are copied into `src/landlords/family/` by the kit's own sync script and never edited here
(docs/OPERATIONS.md, "Scoring and the pages"). To change them, change the kit and sync again.

- `head.html` gives every page its favicons, `theme-color` (roof slate), the kit's stylesheets and fonts, and the
  link-preview card for this site. Every page also has Open Graph and Twitter tags and a canonical link. Some
  carry structured data for search engines (schema.org JSON-LD, `site.json_ld`): the home page a WebSite published
  by the charity (`https://wheretheystand.uk/#org`), landlords' and areas' pages a BreadcrumbList, and the data page
  a Dataset with each CSV file and its licence. It is a block of data that browsers never run and that loads
  nothing, so content pages still load no scripts.
- `endorsement.html` (this site's spine and "A Where They Stand project", linking to wheretheystand.uk) sits under
  the site's name in the header.
- `shelf.html` opens the footer of every page: the Where They Stand wordmark, the charity's line, links to
  wheretheystand.uk and its Donate page, and every project's spine with its name, this site's raised.
- `fonts.css` and `fonts/` hold Source Serif 4 and Source Sans 3 (SIL Open Font License), served from this site, so
  no request goes to Google.
- `<body class="wts-headings">` sets headings in Source Serif 4.
- `measure.js` and `measure-csp.json` are the family's consent banner and Google tag loader, and the hosts the
  content security policy adds for it. Both are unused while measurement is off, as it ships (docs/DECISIONS.md, 20):
  the build copies `measure.js` and the pages load it only when `[ads] measurement` is on. Its banner's styles are
  in `family.css` (`.wts-measure`).

A link to a sister site shows its spine: a council's page and each area's page link to the council on Where
Councils Stand with that site's spine beside the link.

## The mark

The site's picture mark sits beside its name in the header: a front door swung wide towards the viewer, its panels,
letterbox and gilt knob in view, the hall lit in gilt behind it and the light falling over the step. It is drawn in
ivory (`#F3EAD6`) on a rounded roof-slate tile with a fine gilt edge (`#D9BC72`, the family's spine gilt), in the same
manner as the sister sites' marks, and must stay distinct from Where Councils Stand's town hall (docs/DECISIONS.md,
14).

- It is drawn inline (`MARK` in `src/landlords/site.py`) at 52 px, and 44 px on a phone. Its colours and size are in
  the page as well as the stylesheet, so it draws correctly if the stylesheet fails. It is hidden from screen readers
  and is not a link; the name beside it is.
- On the header band the tile takes the other of the two slates (`#5B666D` in light mode, `#40484D` in dark), so it
  stands clear of the band. In forced colours it is redrawn in the system's two colours.
- `src/landlords/static/` has the same drawing as files, offered on the press page: `mark.svg`, `mark-dark.svg`, and
  `mark-small.svg` and `mark-small-dark.svg` for 16 to 32 pixels (a heavier edge and door outline, a plain knob, no
  panels or letterbox). `tests/test_site.py` checks that the inline mark and `mark.svg` have the same shapes.
- The favicon, touch icon and link card come from the family kit, which draws them from the same door.

## Type and colour

Source Serif 4 is used for the site's name and headings, and Source Sans 3 for running text, controls, tables and
figures, with tabular numerals in numeric columns. Headings and labels are in sentence case at normal letter spacing.

Colours come from the kit's tokens (`--wts-*` in `family.css`), with a few of the site's own in
`src/landlords/static/styles.css`. Dark mode follows the system setting.

| Token | Use | Light | Dark |
|---|---|---|---|
| `--page` (kit `--wts-paper-light`) | the page | `#FFFFFF` | `#111517` |
| `--panel` (kit `--wts-paper`) | panels, the alpha banner, the card, notes, the footer | `#F2F4F4` | `#1A2023` |
| `--ink`, `--muted` | text, and hints and source lines | `#1C2427`, `#4F5A5E` | `#E6EAEA`, `#A9B4B7` |
| `--cloth` (kit `--wts-cloth-landlords`) | the header band, buttons, selected radio buttons | `#40484D` | `#5B666D` |
| `--link` | links | `#2F4A5E` | `#A9C6DC` |
| `--band-on`, `--band-off` | filled and empty band squares | `#40484D`, `#DDE2E3` | `#B3BEC5`, `#38434A` |

There are no shadows, no coloured stripes down the side of boxes, no double rules and no gold text; gilt appears only
in the mark and on the book spines.

## Layout

The header, the main column and the footer share one 72rem column with the kit's gutter. Running text is held to
48rem and left-aligned; panels, tables and lists use the whole column.

- The header is the cloth band: the mark, the name and the endorsement in white, with the tabs (Find a landlord,
  Areas, Compare, Your rights, Methodology) on the right, the current one bold with a heavy underline. On a phone the
  tabs are one line that scrolls sideways, with a fade at the edge where there is more to see; on the two pages whose
  tab can start out of sight (Your rights, Methodology), `static/tabs.js` scrolls the row so the current tab shows.
- The alpha banner sits under the band while `[site] stage` is "alpha": an "Alpha" tag, one sentence and a link to
  the report form (`[site] alpha` in `config/wording.toml`).
- The home page puts the search beside a panel, then lists every landlord from A to Z in columns, each letter in a
  narrow column of its own beside its landlords, as in an index. The list of council areas has two columns even on
  a phone, as their names are short.
- A landlord's card, "Before you bid", is one grey panel. Its parts (the grade, how it compares, complaints, safety
  checks) sit in two columns on a wide screen, filled from the top of the left column to the bottom of the right, so
  a short part never leaves a hole beside a long one; on a phone they sit one under another. Each band's squares sit
  beside the first line of its words. The line about turning down an offer is in bold at the top.
- A statement in a landlord's own words (docs/DECISIONS.md, 15) must never look like the site's own text. It sits
  inside a dashed border on the page colour, with a sans-serif heading, "Statement from [name], [date]", its words
  indented, and "In their own words. Not checked or endorsed by Where Landlords Stand." in small type. It is a note
  for screen readers (`role="note"`), named by its heading.
- Tables have a dark rule under the column headings and faint rules between rows. The first and last columns'
  words line up with the text above and below the table. On a narrow phone (under 30rem) the area tables and the
  status page's table are drawn one block per row, with each figure under its column's name, so no name or date is
  broken mid-word. The column headings stay in the table for screen readers, and ARIA
  roles keep it a table whatever the stylesheet does (`stack_table` in `site.py`). The compare table scrolls inside
  its own box, which takes the keyboard focus.
- Forms have a label over each field and a hint under it. The report form's kinds are radio buttons, each with its
  hint under its label.
- The footer starts with the family shelf, then a grey panel with the site's six links (About, Methodology,
  Corrections, Accessibility, Privacy, Source code) and one paragraph with the independence line and the licence and
  attribution notices. Terms, Data, Press, Status, "If you're named" and the contact address are linked from the
  About page.

## Interaction and accessibility

- Focus rings are 3px and always visible, in the current text colour.
- Hover styles need a mouse; touch gets a pressed state instead. Links and buttons fade their colour over 0.12s, and
  only when the reader has not asked for reduced motion.
- Footer links and the contents links are at least 24px tall, and the tabs 44px.
- Search announces how many landlords it found half a second after typing stops (or at once on Enter), through a
  hidden status line, so the list is not read out with every letter.
- No page scrolls sideways on a phone; only the compare table scrolls, inside its own box.

`scripts/a11y.mjs` loads one page of each kind in Chromium, in light and dark mode at 1280px and 390px, and fails on
any serious or critical WCAG 2.2 AA problem that axe-core finds, or on a page that scrolls sideways. CI runs it on
the real pages for every pull request.

## Stylesheets and assets

The site's stylesheet is `src/landlords/static/styles.css`, beside the scripts. The kit's stylesheets
(`fonts.css`, `family.css`) load before it. The build copies the stylesheets, scripts, fonts, icons and link card into
`assets/`, each with a fingerprint of its content in its name (`assets/styles.3f9a2c1d.css`), and the pages name
those files. A changed file gets a new address, so Cloudflare and browsers can keep anything in `assets/` for a year
and never serve a page with an old stylesheet; pages themselves are checked with the server each time. The kit's
head partial names its files under `/family/`; the build rewrites those addresses to the fingerprinted ones, so the
copy in `src/landlords/family/` stays exactly as the kit wrote it. The favicon is also copied to the site's root.
