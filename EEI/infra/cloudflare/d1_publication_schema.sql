-- EEI cloud publication layer (Cloudflare D1 / SQLite dialect).
-- S7PDT04: one-way local -> cloud channel. Contains ONLY the publication
-- surface: owner-signed published facts, their endpoint entities, the
-- evidence index (excerpt + official link), and snapshot metadata.
-- Raw texts, candidates, review queues, scoring internals stay local.

CREATE TABLE IF NOT EXISTS publication_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  canonical_name TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relationships (
  id TEXT PRIMARY KEY,
  subject_entity_id TEXT NOT NULL REFERENCES entities(id),
  object_entity_id TEXT NOT NULL REFERENCES entities(id),
  relationship_type TEXT NOT NULL,
  relationship_family TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL,
  observed_at TEXT,
  published_at TEXT,
  qualifiers_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_relationships_subject
  ON relationships(subject_entity_id);
CREATE INDEX IF NOT EXISTS idx_relationships_object
  ON relationships(object_entity_id);

CREATE TABLE IF NOT EXISTS relationship_evidence (
  relationship_id TEXT NOT NULL REFERENCES relationships(id),
  source_document_id TEXT NOT NULL,
  role TEXT NOT NULL,
  locator TEXT,
  support_excerpt TEXT,
  source_url TEXT,
  source_title TEXT,
  publisher TEXT,
  document_date TEXT,
  PRIMARY KEY (relationship_id, source_document_id, role)
);

CREATE TABLE IF NOT EXISTS snapshot_meta (
  snapshot_key TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  record_mode TEXT NOT NULL,
  status TEXT NOT NULL,
  as_of TEXT,
  activated_at TEXT
);

-- S12PB: per-year official filing depth for the vertical timeline
-- (aggregate counts only; publication-surface boundary applies).
CREATE TABLE IF NOT EXISTS filing_year_counts (
  year INTEGER PRIMARY KEY,
  filings INTEGER NOT NULL
);

-- EEI-F01: static 16-stage supply-chain reference rail so the cloud
-- /v1/supply-chain/overview mirrors the local module surface.
CREATE TABLE IF NOT EXISTS supply_chain_stages (
  stage_id TEXT PRIMARY KEY,
  stage_order INTEGER NOT NULL,
  slug TEXT NOT NULL,
  name_zh TEXT NOT NULL,
  name_en TEXT NOT NULL,
  default_direction TEXT NOT NULL,
  examples TEXT
);
