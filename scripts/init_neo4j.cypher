// scripts/init_neo4j.cypher
// Запустить: cypher-shell -u neo4j -p <pass> < scripts/init_neo4j.cypher

// ─── Constraints ──────────────────────────────────────────────────────────────
CREATE CONSTRAINT unit_id    IF NOT EXISTS FOR (u:TextUnit)    REQUIRE u.id IS UNIQUE;
CREATE CONSTRAINT glas_val   IF NOT EXISTS FOR (g:Glas)        REQUIRE g.value IS UNIQUE;
CREATE CONSTRAINT section_k  IF NOT EXISTS FOR (s:Section)     REQUIRE s.key IS UNIQUE;
CREATE CONSTRAINT office_k   IF NOT EXISTS FOR (o:Office)      REQUIRE o.key IS UNIQUE;
CREATE CONSTRAINT ode_k      IF NOT EXISTS FOR (d:Ode)         REQUIRE d.key IS UNIQUE;
CREATE CONSTRAINT author_n   IF NOT EXISTS FOR (a:Author)      REQUIRE a.name IS UNIQUE;
CREATE CONSTRAINT feast_n    IF NOT EXISTS FOR (f:Feast)       REQUIRE f.name IS UNIQUE;
CREATE CONSTRAINT saint_cid  IF NOT EXISTS FOR (s:Saint)       REQUIRE s.cid IS UNIQUE;
CREATE CONSTRAINT podoben_k  IF NOT EXISTS FOR (p:Podoben)     REQUIRE p.incipit_cu IS UNIQUE;
CREATE CONSTRAINT collection_n IF NOT EXISTS FOR (c:Collection) REQUIRE c.name IS UNIQUE;

// ─── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX tu_lang   IF NOT EXISTS FOR (u:TextUnit) ON (u.lang);
CREATE INDEX tu_genre  IF NOT EXISTS FOR (u:TextUnit) ON (u.genre);
CREATE INDEX tu_glas   IF NOT EXISTS FOR (u:TextUnit) ON (u.glas);
CREATE INDEX tu_incipit IF NOT EXISTS FOR (u:TextUnit) ON (u.incipit);

// ─── Seed: Glas nodes 1–8 ────────────────────────────────────────────────────
UNWIND range(1,8) AS n
MERGE (:Glas {value: n});

// ─── Seed: Collections ───────────────────────────────────────────────────────
UNWIND [
  {name:"Октоих", name_grc:"Παρακλητική", abbrev:"OCT"},
  {name:"Минея",  name_grc:"Μηναίον",     abbrev:"MEN"},
  {name:"Триодь постная", name_grc:"Τριώδιον", abbrev:"TRI"},
  {name:"Пятидесятница", name_grc:"Πεντηκοστάριον", abbrev:"PEN"},
  {name:"Часослов", name_grc:"Ὡρολόγιον", abbrev:"HOR"}
] AS c
MERGE (:Collection {name: c.name, name_grc: c.name_grc, abbrev: c.abbrev});
