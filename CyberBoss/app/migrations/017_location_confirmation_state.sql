-- 「问过没问过」是第三种状态（CB9-220 / AC-014）。
--
-- Additive only. Nothing here alters or drops an existing object.
--
-- 016 里的 confirmed 说的是「用户**答**过了」。AC-014 要的是「冲突或低置信度
-- 时，在首次成功回复后**问一次**」——「问过但他没答」和「压根没问过」是两种不
-- 同的状态，而 confirmed 只有 0/1 装不下第三种。
--
-- 用 confirmed=0 当「没问过」的话，每一轮都会重新满足「低置信且未确认」这个条
-- 件，于是每句话后面都跟一句「你是不是在悉尼？」——AC-014 明说只问一次。
--
-- 时间列照例成对（AC-010）：*_at_utc 排序用，*_at_beijing 是给人看的权威表达。
-- 只存一个的话，跨服务排序和显示必有一个是错的。
--
-- 编号 017 对应 MIGRATIONS 里的 version 15（本仓编号与 version 有固定偏移）。

PRAGMA foreign_keys = ON;

BEGIN;

ALTER TABLE user_location_profiles_v009
  ADD COLUMN confirmation_asked_at_utc TEXT;

ALTER TABLE user_location_profiles_v009
  ADD COLUMN confirmation_asked_at_beijing TEXT;

-- 问的是哪个时区。用户答「对」的时候要知道他在确认什么——中间如果又来了新信
-- 号，把新的那个当成他确认过的就是张冠李戴。
ALTER TABLE user_location_profiles_v009
  ADD COLUMN confirmation_asked_timezone TEXT;

INSERT INTO schema_migrations(
  version,
  applied_at,
  source_commit,
  checksum_sha256
) VALUES (
  15,
  strftime('%Y-%m-%dT%H:%M:%fZ','now'),
  'CB9-220',
  '__MIGRATION_015_CHECKSUM__'
);

COMMIT;
PRAGMA integrity_check;
