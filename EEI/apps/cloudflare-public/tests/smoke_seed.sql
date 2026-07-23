-- Local D1 smoke seed (S10PAT01): mirrors the shape of the two real
-- owner-signed published facts so the Worker smoke exercises the same
-- schema the production publication drill writes. Synthetic ids.
DELETE FROM event_evidence;
DELETE FROM event_participants;
DELETE FROM events;
DELETE FROM relationship_evidence;
DELETE FROM relationships;
DELETE FROM entities;
DELETE FROM snapshot_meta;
DELETE FROM publication_meta;
DELETE FROM filing_year_counts;

INSERT INTO entities(id, canonical_name, entity_type, status) VALUES
  ('00000000-0000-4000-8000-000000000001', 'Taiwan Semiconductor Manufacturing Company Limited', 'company', 'active'),
  ('00000000-0000-4000-8000-000000000002', 'NVIDIA Corporation', 'company', 'active'),
  ('00000000-0000-4000-8000-000000000003', 'ASML Holding N.V.', 'company', 'active');

INSERT INTO relationships(id, subject_entity_id, object_entity_id, relationship_type,
  relationship_family, status, confidence, observed_at, published_at, qualifiers_json) VALUES
  (
    '00000000-0000-4000-9000-000000000001',
    '00000000-0000-4000-8000-000000000001',
    '00000000-0000-4000-8000-000000000002',
    'foundry_supply', 'supply_chain_operations', 'reported', 0.88,
    '2026-06-01T00:00:00+00:00', '2026-07-15T00:00:00+00:00',
    '{"decision_set_key": "smoke-decision-set", "source_threshold_policy": {"minimum_independent_sources": 2, "independent_source_count": 2}, "parser_version": "relationship-publisher-v1"}'
  ),
  (
    '00000000-0000-4000-9000-000000000002',
    '00000000-0000-4000-8000-000000000003',
    '00000000-0000-4000-8000-000000000001',
    'equipment_supply', 'supply_chain_operations', 'reported', 0.84,
    '2026-06-01T00:00:00+00:00', '2026-07-15T00:00:00+00:00',
    '{"decision_set_key": "smoke-decision-set", "source_threshold_policy": {"minimum_independent_sources": 2, "independent_source_count": 2}, "parser_version": "relationship-publisher-v1"}'
  );

INSERT INTO relationship_evidence(relationship_id, source_document_id, role, locator,
  support_excerpt, source_url, source_title, publisher, document_date) VALUES
  ('00000000-0000-4000-9000-000000000001', 'doc-tsmc-10k', 'primary', 'p.12',
   'TSMC manufactures advanced accelerators for NVIDIA.',
   'https://www.sec.gov/example/tsmc-10k', 'TSMC Annual Report', 'SEC EDGAR', '2026-04-01'),
  ('00000000-0000-4000-9000-000000000001', 'doc-nvda-10k', 'corroborating', 'p.33',
   'NVIDIA relies on TSMC as its primary foundry.',
   'https://www.sec.gov/example/nvda-10k', 'NVIDIA Annual Report', 'NVIDIA IR', '2026-03-01'),
  ('00000000-0000-4000-9000-000000000002', 'doc-asml-ar', 'primary', 'p.8',
   'ASML supplies EUV lithography systems to TSMC.',
   'https://www.sec.gov/example/asml-20f', 'ASML Annual Report', 'SEC EDGAR', '2026-02-01'),
  ('00000000-0000-4000-9000-000000000002', 'doc-tsmc-pr', 'corroborating', 'para.2',
   'TSMC confirms EUV tooling procurement from ASML.',
   'https://pr.tsmc.com/example', 'TSMC Press Release', 'TSMC Newsroom', '2026-02-15');

-- A published first-hand event (SEC 8-K) with its evidence, so the smoke
-- exercises the /v1/evidence/event/:id drill-down the capital panel loads.
INSERT INTO events(id, event_type, title, status, announced_at, effective_at,
  period_start, period_end, observed_at, amount, currency, amount_kind,
  description, qualifiers_json) VALUES
  ('00000000-0000-4000-b000-000000000001', 'material_disclosure',
   'NVIDIA Corporation — Material event (8-K)', 'reported',
   '2026-06-10T00:00:00+00:00', '2026-06-10T00:00:00+00:00', NULL, NULL,
   '2026-06-10T00:00:00+00:00', NULL, NULL, 'amount_unreported',
   'Material event (8-K) filed with the SEC on 2026-06-10.', NULL);

INSERT INTO event_participants(event_id, entity_id, entity_name, role, direction) VALUES
  ('00000000-0000-4000-b000-000000000001', '00000000-0000-4000-8000-000000000002',
   'NVIDIA Corporation', 'filer', NULL);

INSERT INTO event_evidence(event_id, source_document_id, role, locator,
  support_excerpt, source_url, source_title, publisher, document_date) VALUES
  ('00000000-0000-4000-b000-000000000001', 'doc-nvda-8k', 'supports',
   'EDGAR accession 0001045810-26-000123',
   'NVIDIA filed 8-K on 2026-06-10.',
   'https://www.sec.gov/example/nvda-8k', 'NVIDIA 8-K',
   'U.S. Securities and Exchange Commission', '2026-06-10');

INSERT INTO snapshot_meta(snapshot_key, scope, record_mode, status, as_of, activated_at) VALUES
  ('smoke-publication-snapshot', 'global', 'database', 'active',
   '2026-07-15T00:00:00+00:00', '2026-07-15T00:00:00+00:00');

INSERT INTO publication_meta(key, value) VALUES
  ('published_at', '2026-07-15T00:00:00+00:00'),
  ('publisher_version', 'eei-publication-schema-v1'),
  ('active_analysis_context', '{"schema_version":"active-analysis-context-v1","context_key":"global","active_scoring_profile_version_id":"00000000-0000-4000-a000-000000000001","active_data_snapshot_key":"smoke-publication-snapshot","active_scoring_run_id":"00000000-0000-4000-a000-000000000002","refresh_token":"00000000-0000-4000-a000-000000000003","refresh_generation":7,"status":"active","activated_at":"2026-07-15T00:00:00+00:00","affected_modules":["business_empire","supply_chain"],"model_version":"business-empire-model-v2@2","profile_version":"balanced-v2@2"}');

INSERT INTO filing_year_counts(year, filings) VALUES
  (2016, 120), (2020, 240), (2026, 210);

DELETE FROM supply_chain_stages;
INSERT INTO supply_chain_stages(stage_id, stage_order, slug, name_zh, name_en,
  default_direction, examples) VALUES
  ('SC-04', 4, 'equipment', '设备', 'Equipment', 'upstream', 'lithography'),
  ('SC-06', 6, 'manufacturing', '制造', 'Manufacturing', 'upstream', 'foundry');
