-- Going back to the site's code as it was before the shared package (wts-core), without losing what was sent or
-- decided since. docs/OPERATIONS.md, "Going back, and coming forward again", says when and how to run this.
--
-- VALID ONLY UNTIL 1 February 2027. From that day `landlords nightly` drops the site's old tables, which this
-- script writes into: run after the drop it stops at its first use of them ("no such table") and changes nothing.
-- After that day, going back means putting back a backup made before the move, while one is still kept.
--
-- Since the move, reports and statements are kept in the package's tables (wts_reports, wts_statements,
-- wts_statement_log). The site's old tables (reports, statements, statement_log) are kept until that day, with the
-- email addresses the site has promised to delete taken out of them each night, and the old code reads only those.
-- This writes the old tables again from the package's, in one transaction, so the old code finds everything: what
-- it had, and what has come in since. Then it forgets the move (below).
--
--   docker compose stop app
--   docker compose run --rm --no-deps -T app python -c "import sqlite3, sys; con = sqlite3.connect('/data/state.db'); con.executescript(sys.stdin.read())" < undo-wts-core.sql
--   (then put the code from before the move, from the archived repository rj-mitchell/wherelandlordsstand_old,
--   in /opt/wherelandlordsstand, and: docker compose up -d --build)
--
-- Run it BEFORE the old code is started, and once: a second run stops at its first step ("CHECK constraint
-- failed") and changes nothing.
--
-- WHAT THE OLD CODE IS GIVEN BACK. What the old tables can't hold is folded into what they can, or left behind: a
-- statement the site removed for breaking the rules is "withdrawn" there (with its reason); a statement that lapsed
-- is "declined"; how a report ended (resolved or dismissed) and a public note for the corrections page's list are
-- not kept, only the private note, as its "outcome"; a landlord's page hidden while a concern is decided stays as
-- the live pages show it until the old code publishes a build, which shows it again (the old code can hide
-- nothing). And what the package has deleted stays deleted: an email address deleted from the package's tables
-- (three months after a statement ended, or from a report closed or open three months) is not in the old tables
-- either, and a note it was written into keeps "[address deleted]" in its place. This site keeps no spending and
-- no visitor's code, so nothing else of the package's forgetting reaches what goes back.
--
-- WHAT THIS DISCARDS. Anything the OLD code has written to the old tables since the move. It can have written
-- there only if it was started after the move without this script being run first; the new code then refuses to
-- start, and says so. If the old code's rows are the ones to keep, run deploy/redo-wts-core.sql instead, and read
-- what that one discards.
--
-- IT ENDS BY FORGETTING THE MOVE: the package's copies of these rows are emptied and the move's mark is removed.
-- The old tables are then the whole truth again, and the old code can run for as long as need be (until 1 February
-- 2027). When the new code is next started it makes the move afresh from the old tables, with whatever the old code
-- has taken in meanwhile, and keeps a copy of the file as it was first, as on the first move. Kept as they are: the
-- site's own tables (missed searches, approval links), and the list of hidden pages (a page hidden on the new code
-- is hidden again by the first build the new code makes). (wts-core's UPGRADING asks every site's script to empty
-- wts_account_months and the month rows of wts_visitor_days too, which summarise spending rows: this site keeps no
-- spending, and its database has neither table.)
BEGIN IMMEDIATE;

-- Only on a database that has been moved, and only once. Without the move's mark the package's tables are empty
-- or were never made, and this script would write the old tables afresh from nothing: the INSERT below then fails
-- ("CHECK constraint failed"), and nothing is changed.
CREATE TEMP TABLE the_move_was_made (yes INTEGER NOT NULL CHECK (yes = 1));
INSERT INTO the_move_was_made SELECT count(*) FROM wts_schema WHERE name = 'import:landlords-reports-and-statements';
DROP TABLE the_move_was_made;

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

-- Forgetting the move (the same statements as deploy/redo-wts-core.sql; tests/test_import.py keeps them the same).
DELETE FROM wts_statement_log;
DELETE FROM wts_statements;
DELETE FROM wts_reports;
DELETE FROM wts_schema WHERE name = 'import:landlords-reports-and-statements';

COMMIT;
