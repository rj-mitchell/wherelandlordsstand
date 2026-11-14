BEGIN TRANSACTION;
CREATE TABLE approvals (token_hash text primary key, build text not null, created text not null,
  expires text not null, published_at text, rolled_back_at text);
INSERT INTO "approvals" VALUES('0a886d81a0830f4b8a5a64aeaf235afdb9f2b9f738e15b4219eaa3a3c2fd6445','20261101-000000','2026-11-06T10:00:00+00:00','2026-11-20T10:00:00+00:00','2026-11-06T10:00:00+00:00',NULL);
INSERT INTO "approvals" VALUES('669f04466bbacaa0190840b559d1441dcc5f1b02fdbd3f6a0716558402465427','20261105-000000','2026-11-06T10:00:00+00:00','2026-11-20T10:00:00+00:00',NULL,NULL);
CREATE TABLE missed (day text not null, query text not null, count integer not null default 0,
  primary key (day, query));
INSERT INTO "missed" VALUES('2026-11-05','nobody homes',3);
INSERT INTO "missed" VALUES('2026-11-06','example hsg',1);
CREATE TABLE reports (id integer primary key, at text not null, page text, message text not null, email text, closed_at text, outcome text, kind text);
INSERT INTO "reports" VALUES(1,'2026-06-20T08:00:00+00:00',NULL,'From before kinds, with no page',NULL,NULL,NULL,NULL);
INSERT INTO "reports" VALUES(2,'2026-11-03T09:00:00+00:00','landlords/x/','Wrong grade','reader@example.org',NULL,NULL,'wrong');
INSERT INTO "reports" VALUES(3,'2026-11-03T09:00:00+00:00','areas/leeds/','Please remove my name.',NULL,NULL,NULL,'takedown');
INSERT INTO "reports" VALUES(4,'2026-11-03T09:00:00+00:00','','Loaded words','c@d.org',NULL,NULL,'unfair');
INSERT INTO "reports" VALUES(5,'2026-11-03T09:00:00+00:00','landlords/y/','A merger you missed',NULL,'2026-11-03T10:00:00+00:00','fixed alias','wrong');
INSERT INTO "reports" VALUES(6,'2026-11-03T09:00:00+00:00','landlords/z/','Closed with nothing said',NULL,'2026-11-03T10:00:00+00:00','','other');
CREATE TABLE statement_log (id integer primary key, statement integer not null, at text not null,
  action text not null, note text);
INSERT INTO "statement_log" VALUES(1,1,'2026-07-01T09:00:00+00:00','received',NULL);
INSERT INTO "statement_log" VALUES(2,1,'2026-07-02T09:00:00+00:00','published','phoned in July');
INSERT INTO "statement_log" VALUES(3,1,'2026-07-03T09:00:00+00:00','withdrawn','withdrawn by the author');
INSERT INTO "statement_log" VALUES(4,2,'2026-11-03T10:00:00+00:00','received',NULL);
INSERT INTO "statement_log" VALUES(5,3,'2026-11-03T10:00:00+00:00','received',NULL);
INSERT INTO "statement_log" VALUES(6,4,'2026-11-03T10:00:00+00:00','received',NULL);
INSERT INTO "statement_log" VALUES(7,5,'2026-11-03T10:00:00+00:00','received',NULL);
INSERT INTO "statement_log" VALUES(8,6,'2026-11-03T10:00:00+00:00','received',NULL);
INSERT INTO "statement_log" VALUES(9,2,'2026-11-04T10:00:00+00:00','published','replied from the landlord''s own address');
INSERT INTO "statement_log" VALUES(10,3,'2026-11-04T10:00:00+00:00','published','phoned the council');
INSERT INTO "statement_log" VALUES(11,5,'2026-11-04T10:00:00+00:00','declined','it is about a tenant');
INSERT INTO "statement_log" VALUES(12,6,'2026-11-04T10:00:00+00:00','published','letter');
INSERT INTO "statement_log" VALUES(13,2,'2026-11-06T10:00:00+00:00','updated','the author''s new version');
INSERT INTO "statement_log" VALUES(14,4,'2026-11-06T10:00:00+00:00','updated',NULL);
INSERT INTO "statement_log" VALUES(15,6,'2026-11-06T10:00:00+00:00','withdrawn','withdrawn by the author');
CREATE TABLE statements (id integer primary key, at text not null, name text not null, role text not null,
  page text not null, part text not null default '', text text not null, link text, email text,
  status text not null default 'pending', landlord text, checked text, reason text, published_at text,
  updated_at text, closed_at text);
INSERT INTO "statements" VALUES(1,'2026-07-01T09:00:00+00:00','Old Author','Director, Example Housing','landlords/example-housing/','','Words withdrawn long ago.',NULL,NULL,'withdrawn','example-housing','phoned in July','withdrawn by the author','2026-07-02T09:00:00+00:00',NULL,'2026-07-03T09:00:00+00:00');
INSERT INTO "statements" VALUES(2,'2026-11-03T10:00:00+00:00','Jane Example','Chief executive, Example Housing','landlords/example-housing/','bands','Our newer results are published every quarter.','https://example.org/results','jane@example-housing.org.uk','published','example-housing','replied from the landlord''s own address',NULL,'2026-11-04T10:00:00+00:00','2026-11-06T10:00:00+00:00',NULL);
INSERT INTO "statements" VALUES(3,'2026-11-03T10:00:00+00:00','Sam Officer','Head of housing, Example Council','areas/leeds/','','Our homes in Leeds are
listed rightly.

Thank you.',NULL,'sam@example.gov.uk','published','example-council','phoned the council',NULL,'2026-11-04T10:00:00+00:00',NULL,NULL);
INSERT INTO "statements" VALUES(4,'2026-11-03T10:00:00+00:00','Pat Waiting','Housing officer, Example Council','areas/leeds/','','Still waiting for a decision.',NULL,'pat@example.gov.uk','pending',NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "statements" VALUES(5,'2026-11-03T10:00:00+00:00','X  Y','Z','landlords/example-council/','safety','Never shown at all.',NULL,'x@example.org','declined','example-council',NULL,'it is about a tenant',NULL,NULL,'2026-11-04T10:00:00+00:00');
INSERT INTO "statements" VALUES(6,'2026-11-03T10:00:00+00:00','Recent Author','Director','landlords/example-council/','','Shown for a day only.','https://example.org/r?a=1&b=2','recent@example.org','withdrawn','example-council','letter','withdrawn by the author','2026-11-04T10:00:00+00:00',NULL,'2026-11-06T10:00:00+00:00');
COMMIT;
