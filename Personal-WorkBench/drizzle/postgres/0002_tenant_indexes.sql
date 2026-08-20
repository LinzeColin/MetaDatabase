-- Additive S2 guardrail: the frozen task-pack migration intentionally remains
-- byte-identical; these indexes complete tenant-first access coverage for the
-- two remaining user-associated operational tables.
CREATE INDEX IF NOT EXISTS outbox_events_user_idx ON outbox_events(user_id, created_at);
CREATE INDEX IF NOT EXISTS security_audit_events_user_idx ON security_audit_events(user_id, created_at);
