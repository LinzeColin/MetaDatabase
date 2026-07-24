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

-- Capital River / vertical timeline: first-hand published EVENTS (SEC filings
-- etc., derivation_rule = authoritative_first_hand_ingestion). Same one-way
-- publication surface: title/type/timing/amount + participant identity +
-- evidence index only. Raw filing texts stay local / in R2.
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  announced_at TEXT,
  effective_at TEXT,
  period_start TEXT,
  period_end TEXT,
  observed_at TEXT NOT NULL,
  amount REAL,
  currency TEXT,
  amount_kind TEXT,
  description TEXT,
  qualifiers_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_observed ON events(observed_at);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

-- Participant entity_name is denormalized at publish time so the worker serves
-- the capital river without a join (mirrors how evidence carries source_*).
CREATE TABLE IF NOT EXISTS event_participants (
  event_id TEXT NOT NULL REFERENCES events(id),
  entity_id TEXT NOT NULL,
  entity_name TEXT,
  role TEXT NOT NULL,
  direction TEXT,
  PRIMARY KEY (event_id, entity_id, role)
);

CREATE INDEX IF NOT EXISTS idx_event_participants_entity
  ON event_participants(entity_id);

CREATE TABLE IF NOT EXISTS event_evidence (
  event_id TEXT NOT NULL REFERENCES events(id),
  source_document_id TEXT NOT NULL,
  role TEXT NOT NULL,
  locator TEXT,
  support_excerpt TEXT,
  source_url TEXT,
  source_title TEXT,
  publisher TEXT,
  document_date TEXT,
  PRIMARY KEY (event_id, source_document_id, role)
);

CREATE INDEX IF NOT EXISTS idx_event_evidence_event
  ON event_evidence(event_id);

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
