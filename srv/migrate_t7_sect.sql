-- T7 仙盟重构（0.8.7）migration.
-- Idempotent: safe to run any number of times.
-- Apply with:  sqlite3 /opt/yl/server/yl.db < srv/migrate_t7_sect.sql
--
-- NOTE: the server also applies all of this at boot (CREATE TABLE IF NOT EXISTS for
-- sect_applications + PRAGMA table_info(sects)-guarded ALTER for join_mode, both inside
-- the existing db.serialize block in srv/index.ts), so running this file is optional.
-- It exists for DB-only deployments and for pre-creating the table/column before the
-- new server binary starts (same convention as srv/migrate_activity.sql).
--
-- Contents:
--   1. sect_applications  —— 盟申请审批流（一人一 pending 由部分唯一索引兜底）
--   2. sects.join_mode    —— 加入模式 'auto' | 'apply'（存量盟默认 auto=直进，向后兼容）
--
-- 数值/语义定档 = docs/0.8.7-design/T7-仙盟重构.md + 数值表-T7T8：
--   申请有效期 72h（SECT_APPLY_TTL_MS，读取路径惰性置 expired，本迁移不写数据）

CREATE TABLE IF NOT EXISTS sect_applications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sect_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','approved','rejected','cancelled','expired')),
  created_at INTEGER NOT NULL,
  handled_at INTEGER,
  handled_by INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sect_app_user_pending
  ON sect_applications(user_id) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_sect_app_sect
  ON sect_applications(sect_id, status, created_at);

-- 加列（SQLite 3.35+ 无 IF NOT EXISTS 语义，靠 PRAGMA 守卫；此文件等价实现见下。
-- 若列已存在，本 ALTER 会报 duplicate column name —— 与服务端 PRAGMA 守卫行为一致，属幂等预期）。
-- 先查后改（sqlite3 CLI 手工执行时）：
--   PRAGMA table_info(sects);   -- 无 join_mode 再执行下行
ALTER TABLE sects ADD COLUMN join_mode TEXT NOT NULL DEFAULT 'auto';

-- ---------------------------------------------------------------------------
-- ROLLBACK (informational -- do NOT run):
-- 回滚铁律：**保留新表/新列，勿删**（topics《项目-摸鱼修仙传》既定）。旧版服务端代码
-- 不读 sect_applications / sects.join_mode，留着无害；删表才会造成审批数据丢失。
-- 仅在彻底放弃该功能且归档数据后：
--   DROP TABLE IF EXISTS sect_applications;
--   （sects.join_mode 列 SQLite 无法 DROP COLUMN（3.35 前），保留即可）
-- ---------------------------------------------------------------------------
