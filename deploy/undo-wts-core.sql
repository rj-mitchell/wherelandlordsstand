-- Going back to the site's code as it was before the shared package (wts-core), without losing what was sent or
-- decided since. docs/OPERATIONS.md, "The state database", says when and how to run this.
--
-- Since the move, reports and statements are kept in the package's tables (wts_reports, wts_statements,
-- wts_statement_log). The site's old tables (reports, statements, statement_log) were left exactly as they were on
-- the day of the move, and the old code reads only those. This writes the old tables again from the package's, in
-- one transaction, so the old code finds everything: what it had, and what has come in since.
--
--   docker compose stop app
--   docker compose run --rm -T app python -c "import sqlite3, sys; con = sqlite3.connect('/data/state.db'); con.executescript(sys.stdin.read())" < undo-wts-core.sql
--
-- What the old tables can't hold is folded into what they can: a statement the site removed for breaking the rules
-- is "withdrawn" there (with its reason); a statement that lapsed is "declined"; how a report ended (resolved or
-- dismissed) and a public note are not kept, only the private note, as its "outcome". The package's tables are not
-- changed, so the move can be made again later: delete the row 'import:landlords-reports-and-statements' from
-- wts_schema first, and
-- empty the three wts_ tables, or the old rows would be imported twice.
BEGIN IMMEDIATE;

DELETE FROM statement_log;
DELETE FROM statements;
DELETE FROM reports;

INSERT INTO reports (id, at, page, message, email, closed_at, outcome, kind)
SELECT id, at, coalesce(page, ''), message, contact, closed_at,
       CASE WHEN closed_at IS NULL THEN NULL ELSE coalesce(resolution, '') END, kind
FROM wts_reports;

INSERT INTO statements (id, at, name, role, page, part, text, link, email, status, landlord, checked, reason,
                        published_at, updated_at, closed_at)
SELECT s.id, s.at, s.name, s.role, s.item, s.part, s.text, s.link, s.email,
       CASE s.status WHEN 'removed' THEN 'withdrawn' ELSE s.status END, s.about,
       (SELECT l.note FROM wts_statement_log l WHERE l.statement = s.id AND l.action = 'published'
        ORDER BY l.id LIMIT 1),
       s.reason, s.published_at,
       -- the old code shows the date of the last update when there is one: only an update made since publishing
       CASE WHEN s.published_at IS NOT NULL AND s.updated_at >= s.published_at THEN s.updated_at END,
       s.closed_at
FROM wts_statements s;

INSERT INTO statement_log (id, statement, at, action, note)
SELECT id, statement, at, CASE action WHEN 'removed' THEN 'withdrawn' WHEN 'lapsed' THEN 'declined' ELSE action END,
       note
FROM wts_statement_log;

COMMIT;
