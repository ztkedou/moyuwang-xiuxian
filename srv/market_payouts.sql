-- migrations/market_payouts.sql
-- V27 交易行服务端结算：卖家收益托管表（上游 JeasonLoop/react-xiuxian-game 1ec1b63 移植）
--
-- 用途：交易行物品售出后，货款先入账到本表托管（claimed=0），待卖家调用
--       POST /api/market/payouts/claim 领取时再由服务端入账到 saves.save_data 的
--       player.spiritStones（走 updatePlayerSave：saveLock 互斥 + gm_revision++ + 排行/经济镜像）。
--
-- 规范：与 account_refactor.sql / sect_system.sql 同款——幂等 IF NOT EXISTS，
--       与 server/index.ts 启动 DDL 块（market_listings 建表之后）双写一致。
-- 执行：sqlite3 /opt/yl/server/database.sqlite < market_payouts.sql
-- 回滚：DROP TABLE market_payouts;（无其它表引用本表，删除无害；未领取的收益会一并丢失）

CREATE TABLE IF NOT EXISTS market_payouts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  listing_id INTEGER,
  amount INTEGER NOT NULL,
  claimed INTEGER NOT NULL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users (id)
);

-- 领取查询主路径：WHERE user_id = ? AND claimed = 0
CREATE INDEX IF NOT EXISTS idx_payouts_user ON market_payouts(user_id, claimed);
