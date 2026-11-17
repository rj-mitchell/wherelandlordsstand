-- Making the move onto the shared package (wts-core) again from the site's old tables, when the code from before
-- the move has written to the database since it was moved. docs/OPERATIONS.md, "Going back, and coming forward
-- again", says when and how to run this.
--
-- VALID ONLY UNTIL 1 February 2027, like deploy/undo-wts-core.sql: from that day the old tables are gone, and this
-- stops at its first step ("no such table") and changes nothing.
--
-- When it is needed. The move is made once, and marked. If the old code is then started on the database without
-- deploy/undo-wts-core.sql having been run first, what it takes in (a report, a statement, a decision on one) goes
-- to the old tables only. The new code, deployed again, would never see it, so it refuses to start: "the site's old
-- tables hold rows that are newer than the import that copied them". This script forgets the move and touches
-- nothing else, so that the next start of the new code brings every row of the old tables across afresh.
--
--   docker compose stop app
--   docker compose run --rm --no-deps -T app python -c "import sqlite3, sys; con = sqlite3.connect('/data/state.db'); con.executescript(sys.stdin.read())" < redo-wts-core.sql
--   docker compose up -d
--
-- Run it once: a second run stops at its first step ("CHECK constraint failed") and changes nothing.
--
-- WHAT THIS DISCARDS. Everything the NEW code wrote to its own tables between the move and the day the old code was
-- started again, which the old tables do not hold: reports sent and closed on the new code (with how each ended and
-- any public note for the corrections page's list), statements sent, published, updated, withdrawn, removed,
-- declined or lapsed on it, and the log of what was done to each. A statement published on the new code is then as
-- the old tables have it (waiting, if it was waiting at the move), and is shown again only when the owner publishes
-- it again. If the new code never took a report or a decision after the move, that is nothing. If the new code's
-- rows are the ones to keep, run deploy/undo-wts-core.sql instead, which carries them to the old tables and
-- discards what the old code wrote since the move.
--
-- Kept as they are: the old tables, the site's own tables (missed searches, approval links), and the list of
-- hidden pages (a page hidden on the new code is hidden again by the first build the new code makes).
BEGIN IMMEDIATE;

-- Only while the old tables are there: without them there is nothing to make the move again from, and the move
-- forgotten would leave the site with no reports and no statements at all.
SELECT count(*) FROM reports;

-- Only on a database that has been moved, and only once. Without the move's mark there is no move to forget: the
-- INSERT below then fails ("CHECK constraint failed"), and nothing is changed.
CREATE TEMP TABLE the_move_was_made (yes INTEGER NOT NULL CHECK (yes = 1));
INSERT INTO the_move_was_made SELECT count(*) FROM wts_schema WHERE name = 'import:landlords-reports-and-statements';
DROP TABLE the_move_was_made;

-- Forgetting the move (the same statements as deploy/undo-wts-core.sql ends with; tests/test_import.py keeps them
-- the same).
DELETE FROM wts_statement_log;
DELETE FROM wts_statements;
DELETE FROM wts_reports;
DELETE FROM wts_schema WHERE name = 'import:landlords-reports-and-statements';

COMMIT;
