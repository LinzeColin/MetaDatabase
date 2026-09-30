-- 公开数据接口用到、而迁移里没有的索引。幂等，由库属主（eei）执行：
--
--   docker exec -i eei-db psql -U eei -d eei -v ON_ERROR_STOP=1 < indexes.sql
--
-- explore（按端点取边）、实体检索（pg_trgm）、证据（主键）都已有索引覆盖；这里补的是
-- 「变更流」「模块概览」「事件流」的排序索引。写入量小（每小时几百行），建索引的代价可忽略。

CREATE INDEX IF NOT EXISTS relationships_created_idx
  ON relationships (created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS relationships_family_type_idx
  ON relationships (relationship_family, relationship_type, id);

CREATE INDEX IF NOT EXISTS events_public_time_idx
  ON events ((COALESCE(effective_at, announced_at, observed_at)) DESC, observed_at DESC, id);

CREATE INDEX IF NOT EXISTS event_participants_entity_idx
  ON event_participants (entity_id, event_id);

ANALYZE relationships;
ANALYZE events;
ANALYZE event_participants;
