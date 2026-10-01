-- ============================================================================
-- migrate_t10_farm.sql — 0.8.7 T10 灵田扩充 · 数据库迁移留档
-- 归属：implGrotto（与 srv_patch_t10_farm.py 同批；本文件为留档/手工迁移用）
--
-- ★ 实际生效路径：服务端启动时 initDB 内的 CREATE TABLE IF NOT EXISTS（见
--   srv_patch_t10_farm.py F1 编辑块），本文件与其逐字对应，供：
--   ① 线上验收核对（PRAGMA table_info / .schema farm_daily_care）
--   ② 手工迁移兜底（如需在停服窗口提前建表）
--
-- ★ 回滚纪律：回滚保留新表勿删（IF NOT EXISTS 幂等，旧代码不读此表=无害）。
--   spirit_farm / farm_unlocks 零改零加列（FARM_SLOTS 常量 3→6 自动泛化，
--   slot 与 crop 均无 CHECK 硬编码，历史行天然兼容）。
-- ============================================================================

-- farm_daily_care：照料/催熟的日切状态（北京日切，与 stats_daily / sect_ledger 同口径）
-- PK(player_id,slot,date) 幂等；「每田每日照料 1 次 / 催熟 1 次」的唯一防线 =
-- ON CONFLICT(player_id,slot,date) DO UPDATE SET x=1 WHERE x=0 单语句原子闸门（changes=0 即 409）
CREATE TABLE IF NOT EXISTS farm_daily_care (
  player_id INTEGER NOT NULL,
  slot INTEGER NOT NULL,
  date TEXT NOT NULL,            -- bjDate（YYYY-MM-DD，UTC+8）
  tended INTEGER NOT NULL DEFAULT 0,
  boosted INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (player_id, slot, date),
  FOREIGN KEY (player_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_farm_care_player_date ON farm_daily_care(player_id, date);

-- 对照：既有表零改动（此处仅注释说明，不执行任何 ALTER）
--   spirit_farm(id, player_id, slot, crop, planted_at, mature_at, harvested)  —— 不变
--   farm_unlocks(player_id, slot, unlocked_at)                                —— 不变
