-- eei_reader：公开数据接口（eei-api）用的只读角色。幂等，可反复执行。
--
--   docker exec -i eei-db psql -U eei -d eei -v ON_ERROR_STOP=1 < readonly_role.sql
--
-- 设计：
--   * 只授 SELECT，且只授 API 真用到的表（白名单）。个人状态（saved_views、watchlists…）、
--     候选与复核队列、原文快照、任务队列不在名单里——哪怕 API 被攻破也读不到。
--   * 新建的表不会自动授权（不设 ALTER DEFAULT PRIVILEGES）：要给 API 新表，改这份文件再跑一遍。
--   * 会话级只读 + 语句超时，双保险；密码不在这里设（见 apps/api/deploy/README.md）。

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eei_reader') THEN
    CREATE ROLE eei_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT
      CONNECTION LIMIT 8;
  END IF;
END
$$;

ALTER ROLE eei_reader SET default_transaction_read_only = on;
ALTER ROLE eei_reader SET statement_timeout = '10s';
ALTER ROLE eei_reader SET idle_in_transaction_session_timeout = '30s';

DO $$
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO eei_reader', current_database());
END
$$;

-- 先收回再授：反复执行结果一致，手滑多授的权限也会被收回。
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM eei_reader;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM eei_reader;
REVOKE CREATE ON SCHEMA public FROM eei_reader;
GRANT USAGE ON SCHEMA public TO eei_reader;

GRANT SELECT ON
  entities,
  relationships,
  relationship_evidence,
  sources,
  source_documents,
  events,
  event_participants,
  event_evidence,
  supply_chain_stages,
  data_snapshots,
  active_analysis_contexts,
  scoring_models,
  scoring_profiles,
  scoring_profile_versions
TO eei_reader;
