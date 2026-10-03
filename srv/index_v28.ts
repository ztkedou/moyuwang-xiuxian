import express from 'express';
import cors from 'cors';
import sqlite3 from 'sqlite3';
import bcrypt from 'bcrypt';
import jwt from 'jsonwebtoken';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import { fileURLToPath } from 'url';

dotenv.config();

const app = express();
app.set("trust proxy", 1); // nginx 反代下取真实客户端 IP，限流按人生效而非全服一桶
const PORT = process.env.PORT || 3001;
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
let JWT_SECRET = process.env.JWT_SECRET;
// access 缩到 2h（账号重构 2026-09-23，docs/account-refactor-plan.md §2）：客户端只在收到 401 时
// 才静默走 /api/auth/refresh 续期；过期由 authenticateToken 回 401（见该中间件注释）。
// refresh 不再是 JWT：改为服务端落 refresh_tokens 表的不透明随机串（180 天滑动窗口、可逐台/全部吊销），
// 封禁生效延迟由"无限期"收敛为"≤2h"（存量旧 access 自然老化，方案 §5.4）。
const ACCESS_TOKEN_EXPIRY = '2h';

// 安全设置
app.disable('x-powered-by');

// 如果没有设置JWT_SECRET：先复用上次持久化在 server/.jwt_secret 的密钥（重启/重部署不换钥匙，
// 线上已签发的 access/refresh token 不会整体失效→消除"部署一次全员被踢下线"类登录过期）；
// 首次才随机生成并尽力持久化（写失败退回旧行为）。服务器 .env 显式配置 JWT_SECRET 时本段不生效（env 优先）。
if (!JWT_SECRET) {
  try {
    const secretFile = path.join(__dirname, '.jwt_secret');
    if (fs.existsSync(secretFile)) {
      const persisted = fs.readFileSync(secretFile, 'utf8').trim();
      if (persisted.length >= 32) {
        JWT_SECRET = persisted;
        console.log('JWT_SECRET loaded from persisted .jwt_secret file');
      }
    }
  } catch { /* 读取失败按无持久化处理 */ }
}
if (!JWT_SECRET) {
  JWT_SECRET = crypto.randomBytes(64).toString('hex');
  console.log('⚠️  JWT_SECRET not set in environment, auto-generated a random secret');
  try {
    fs.writeFileSync(path.join(__dirname, '.jwt_secret'), JWT_SECRET, { mode: 0o600 });
    console.log('JWT_SECRET persisted to server/.jwt_secret');
  } catch { /* 尽力而为；写失败退回旧行为（每次重启随机密钥） */ }
}

const JWT_SECRET_USED = JWT_SECRET;

app.use(cors({
  // 允许跨域，如果你只有前端在同一个域名可以限制origin
  origin: true,
  credentials: true
}));
app.use(express.json({ limit: '50mb' }));

// 批1a：JSON 解析失败一律 400（原为 500「服务器繁忙」，裸调 API 误报）
app.use((err: any, req: any, res: any, next: any) => {
  if (err && (err.type === 'entity.parse.failed' || err instanceof SyntaxError)) {
    return res.status(400).json({ error: '请求体不是合法 JSON' });
  }
  next(err);
});

// 添加安全响应头
app.use((req, res, next) => {
  res.setHeader('X-Frame-Options', 'SAMEORIGIN');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-XSS-Protection', '1; mode=block');
  next();
});

// SQLite database setup
const defaultDbDir = path.basename(__dirname) === 'server'
  ? __dirname
  : path.resolve(process.cwd(), 'server');
const defaultDbPath = path.join(defaultDbDir, 'database.sqlite');
const dbPath = process.env.DATABASE_PATH
  ? path.resolve(process.env.DATABASE_PATH)
  : defaultDbPath;

// RANKINGMIG089：**幂等加列**。serialize 队列只保证「入队顺序」，不提供「完成屏障」——
//   紧随 CREATE TABLE 的 `PRAGMA table_info(T)` 可能读到空 / 部分 schema，使
//   `!rows.some(r => r.name === col)` 误判「缺列」，对已含该列的表重复 ADD COLUMN ⇒
//   `SQLITE_ERROR: duplicate column name` ⇒ 该错误经 db 'error' 事件在顶层抛出、无人 catch
//   ⇒ **进程起不来**（空库冷启动 100% 命中；见本环文件头）。
//   故不加 `rows.length > 0` 之类的概率性判断，而是让 **DDL 本身幂等**：
//   容忍 `duplicate column name`（重跑 / 冷启动双安全），其余错误照常上报。
//   守卫处的 PRAGMA 判断保留作**快路径**（列已存在可省一次 DDL），真正兜底的是这里。
const safeAddColumn = (table: string, col: string, ddl: string) => {
  db.exec(ddl, (e: any) => {
    if (e && !/duplicate column name/i.test(String(e.message || ''))) {
      console.error('[migrate]', table, col, e.message);
    }
  });
};
const db = new sqlite3.Database(dbPath, (err) => {
  if (err) {
    console.error('Error opening database', err.message);
  } else {
    console.log('Connected to the SQLite database.');

    // Create tables and indexes
    db.serialize(() => {
      db.run(`
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          linuxdo_id TEXT UNIQUE,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
      `);

      // migration: 添加 linuxdo_id 字段（已有则跳过）
      db.all("PRAGMA table_info(users)", (err, rows: any[]) => {
        if (!err && rows && !rows.some((r) => r.name === 'linuxdo_id')) {
          safeAddColumn('users', 'linuxdo_id', 'ALTER TABLE users ADD COLUMN linuxdo_id TEXT');
        }
      });

      db.run(`
        CREATE TABLE IF NOT EXISTS saves (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL UNIQUE,
          save_data TEXT NOT NULL,
          gm_revision INTEGER DEFAULT 0,
          tower_lump_left INTEGER NOT NULL DEFAULT 12000000,
          exped_lump_left INTEGER NOT NULL DEFAULT 2000000,
          econ_win_start INTEGER,
          econ_win_exp INTEGER NOT NULL DEFAULT 0,
          econ_win_stone INTEGER NOT NULL DEFAULT 0,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (user_id) REFERENCES users (id)
        )
      `);

      // migration: 添加 gm_revision 字段（已有则跳过）
      db.all("PRAGMA table_info(saves)", (err: any, rows: any[]) => {
        if (!err && rows && !rows.some((r: any) => r.name === 'gm_revision')) {
          safeAddColumn('saves', 'gm_revision', 'ALTER TABLE saves ADD COLUMN gm_revision INTEGER DEFAULT 0');
        }
      });

      // v28 P0-1/P0-2 migration: one-time tower/expedition exp pools + the persisted
      // real-time allowance ledger. Pool default = FULL (= "never granted yet", so legacy
      // saves get the one-time lump exactly once and are never silently zeroed).
      // econ_win_start stays NULL for every existing row = "window not opened yet" -> the
      // first save anchors it at the real previous save time (no zero-grant cliff).
      db.all("PRAGMA table_info(saves)", (err: any, rows: any[]) => {
        if (!err && rows) {
          if (!rows.some((r: any) => r.name === 'tower_lump_left')) safeAddColumn('saves', 'tower_lump_left', 'ALTER TABLE saves ADD COLUMN tower_lump_left INTEGER NOT NULL DEFAULT 12000000');
          if (!rows.some((r: any) => r.name === 'exped_lump_left')) safeAddColumn('saves', 'exped_lump_left', 'ALTER TABLE saves ADD COLUMN exped_lump_left INTEGER NOT NULL DEFAULT 2000000');
          if (!rows.some((r: any) => r.name === 'econ_win_start')) safeAddColumn('saves', 'econ_win_start', 'ALTER TABLE saves ADD COLUMN econ_win_start INTEGER');
          if (!rows.some((r: any) => r.name === 'econ_win_exp')) safeAddColumn('saves', 'econ_win_exp', 'ALTER TABLE saves ADD COLUMN econ_win_exp INTEGER NOT NULL DEFAULT 0');
          if (!rows.some((r: any) => r.name === 'econ_win_stone')) safeAddColumn('saves', 'econ_win_stone', 'ALTER TABLE saves ADD COLUMN econ_win_stone INTEGER NOT NULL DEFAULT 0');
          // ★ R-021（offline2 环）：真实「离开 / 回来」时刻（毫秒，NULL=未知）。
          //   last_seen_at ：客户端在 visibilitychange(hidden)/pagehide/beforeunload 上报离开；
          //                  服务端落的是**上报那一刻本行的 updated_at**（服务端权威时间轴，
          //                  客户端只能触发事件、不能自带时间戳 ⇒ 无法伪造离线时长）。
          //   last_resume_at：客户端可见 / 启动时上报回来（Date.now()），用于给离线段封口。
          //   二者只服务 /api/offline/report|claim 的**离线窗口锚点**，不参与任何收益公式。
          if (!rows.some((r: any) => r.name === 'last_seen_at')) safeAddColumn('saves', 'last_seen_at', 'ALTER TABLE saves ADD COLUMN last_seen_at INTEGER');
          if (!rows.some((r: any) => r.name === 'last_resume_at')) safeAddColumn('saves', 'last_resume_at', 'ALTER TABLE saves ADD COLUMN last_resume_at INTEGER');
        }
      });

      // S4 v26c 保险快照表：玩家写档前的旧档快照（节流 10min/条、每号留 50 条），误覆盖/误伤救援用；
      // 旁路独立件，裁掉本表与 snapshotOldSave 不影响 S1-S3
      db.run(`
        CREATE TABLE IF NOT EXISTS save_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          save_data TEXT NOT NULL,
          gm_revision INTEGER DEFAULT 0,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
      `);
      db.run(`CREATE INDEX IF NOT EXISTS idx_save_snapshots_user ON save_snapshots(user_id, id DESC)`);

      // 单写者会话锁（session-lock）：同一账号当前活跃写入会话（顶号判定）。
      // 时间戳统一毫秒（Date.now()，与本文件其它 INTEGER 时间戳口径一致）。
      db.run(`
        CREATE TABLE IF NOT EXISTS active_sessions (
          user_id INTEGER PRIMARY KEY,
          session_id TEXT NOT NULL,
          device TEXT,
          claimed_at INTEGER NOT NULL,
          last_seen INTEGER NOT NULL
        )
      `);

      // 添加索引加速查询
      db.run(`CREATE INDEX IF NOT EXISTS idx_saves_user_id ON saves(user_id)`);

      // 排行榜表：存储从存档中提取的可排序字段
      // fix(rank) 2026-09-17：新增 name 列冗余存角色昵称（saves.save_data JSON player.name 的同步副本）；
      // username 列仍是登录账号。此前排行榜展示的是 username（登录账号）而非角色名，读侧现在优先取 name。
      db.run(`
        CREATE TABLE IF NOT EXISTS rankings (
          user_id INTEGER PRIMARY KEY,
          username TEXT NOT NULL,
          name TEXT NOT NULL DEFAULT '',
          realm_index INTEGER NOT NULL DEFAULT 0,
          realm_level INTEGER NOT NULL DEFAULT 1,
          exp INTEGER NOT NULL DEFAULT 0,
          combat_power INTEGER NOT NULL DEFAULT 0,
          spirit_stones INTEGER NOT NULL DEFAULT 0,
          reputation INTEGER NOT NULL DEFAULT 0,
          achievement_count INTEGER NOT NULL DEFAULT 0,
          kill_count INTEGER NOT NULL DEFAULT 0,
          play_time INTEGER NOT NULL DEFAULT 0,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (user_id) REFERENCES users (id)
        )
      `);
      db.run(`CREATE INDEX IF NOT EXISTS idx_rankings_realm ON rankings(realm_index DESC, realm_level DESC, exp DESC)`);
      db.run(`CREATE INDEX IF NOT EXISTS idx_rankings_combat ON rankings(combat_power DESC)`);
      db.run(`CREATE INDEX IF NOT EXISTS idx_rankings_stones ON rankings(spirit_stones DESC)`);

      // 交易行表：玩家上架物品
      db.run(`
        CREATE TABLE IF NOT EXISTS market_listings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          seller_id INTEGER NOT NULL,
          seller_name TEXT NOT NULL,
          item_name TEXT NOT NULL,
          item_type TEXT NOT NULL,
          item_description TEXT DEFAULT '',
          item_rarity TEXT NOT NULL DEFAULT '普通',
          price INTEGER NOT NULL,
          quantity INTEGER DEFAULT 1,
          is_equippable INTEGER DEFAULT 0,
          equipment_slot TEXT,
          effect_json TEXT,
          item_source_json TEXT NOT NULL,
          status TEXT DEFAULT 'active',
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          sold_at DATETIME,
          buyer_id INTEGER,
          FOREIGN KEY (seller_id) REFERENCES users (id)
        )
      `);
      db.run(`CREATE INDEX IF NOT EXISTS idx_market_status ON market_listings(status)`);
      db.run(`CREATE INDEX IF NOT EXISTS idx_market_seller ON market_listings(seller_id)`);

      // 交易行卖家收益表（V27 交易行服务端结算，上游 1ec1b63 移植；迁移留档=migrations/market_payouts.sql，双写一致）：
      // 物品售出后，卖家灵石先入账到此表托管，待卖家调用 /api/market/payouts/claim 领取。
      db.run(`
        CREATE TABLE IF NOT EXISTS market_payouts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          listing_id INTEGER,
          amount INTEGER NOT NULL,
          claimed INTEGER NOT NULL DEFAULT 0,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (user_id) REFERENCES users (id)
        )
      `);
      db.run(`CREATE INDEX IF NOT EXISTS idx_payouts_user ON market_payouts(user_id, claimed)`);

      // 世界聊天表：存储玩家聊天消息
      db.run(`
        CREATE TABLE IF NOT EXISTS chat_messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT NOT NULL,
          text TEXT NOT NULL,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
      `);
      db.run(`CREATE INDEX IF NOT EXISTS idx_chat_messages_id ON chat_messages(id)`);

      // 站内邮件表（E2）：系统/GM 给玩家发文字+灵石附件
      // 灵石余额存放在 saves.save_data JSON 的 player.spiritStones（rankings.spirit_stones 仅是同步副本），
      // 因此领取附件走 updatePlayerSave（带 saveLock 互斥 + gm_revision++ + 排行同步）
      db.run(`
        CREATE TABLE IF NOT EXISTS mail (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          sender TEXT NOT NULL DEFAULT 'system',
          title TEXT NOT NULL,
          content TEXT NOT NULL DEFAULT '',
          attached_lingshi INTEGER NOT NULL DEFAULT 0,
          claimed INTEGER NOT NULL DEFAULT 0,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          read_at DATETIME,
          FOREIGN KEY (user_id) REFERENCES users (id)
        )
      `);
      db.run(`CREATE INDEX IF NOT EXISTS idx_mail_user_id ON mail(user_id, id)`);
    });
  }
});

// ── Y 系列增量 schema（Y5 回归 / Y6 称号 / Y2 每日任务）：IF NOT EXISTS + PRAGMA 守卫，重启幂等 ──
// 设计口径：凡服务端所有的状态一律放"列"，不放 saves.save_data JSON——该 JSON 由客户端权威整包上传，
// 服务端写进 JSON 的字段会在玩家下次存档上传时被覆盖（mail claim 报告 §7.2 同源结论）。
db.serialize(() => {
  // Y5：users.last_login——回归判定基准（ISO UTC 文本，每次登录成功刷新）
  db.all("PRAGMA table_info(users)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'last_login')) {
      safeAddColumn('users', 'last_login', 'ALTER TABLE users ADD COLUMN last_login TEXT');
    }
  });
  // Y5：saves.return_buff_until——回归 buff 截止（ms epoch，NULL=无 buff）
  db.all("PRAGMA table_info(saves)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'return_buff_until')) {
      safeAddColumn('saves', 'return_buff_until', 'ALTER TABLE saves ADD COLUMN return_buff_until INTEGER');
    }
  });
  // Y3A：saves.offline_claimed_until——离线收益已结算到的时刻（ms epoch，NULL=从未领过）。
  // 防重复领取的唯一防线：守卫式单语句推进（WHERE offline_claimed_until < 新值），并发双领只一方生效
  db.all("PRAGMA table_info(saves)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'offline_claimed_until')) {
      safeAddColumn('saves', 'offline_claimed_until', 'ALTER TABLE saves ADD COLUMN offline_claimed_until INTEGER');
    }
  });
  // WUDAO：saves.month_card_until——月卡有效期截止（ms epoch，NULL/过期=无月卡）。
  // 离线收益月卡档（上限 12h + 效率 100%）的唯一判定依据；开通入口（购买流程）未上线，
  // 过渡期由 GM 直接 UPDATE saves SET month_card_until=<ms epoch> 开通（纯判定 hasMonthCard 已单测覆盖）
  db.all("PRAGMA table_info(saves)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'month_card_until')) {
      safeAddColumn('saves', 'month_card_until', 'ALTER TABLE saves ADD COLUMN month_card_until INTEGER');
    }
  });
  // Y6：titles（称号目录）+ player_titles（玩家持有，主键幂等防重复授予）
  db.run(`
    CREATE TABLE IF NOT EXISTS titles (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      attr_json TEXT NOT NULL DEFAULT '{}',
      source TEXT NOT NULL DEFAULT 'gm'
    )
  `);
  db.run(`
    CREATE TABLE IF NOT EXISTS player_titles (
      user_id INTEGER NOT NULL,
      title_id INTEGER NOT NULL,
      granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (user_id, title_id),
      FOREIGN KEY (user_id) REFERENCES users (id),
      FOREIGN KEY (title_id) REFERENCES titles (id)
    )
  `);
  // Y6：saves.title_id——佩戴中的称号（服务端列；save_data JSON 里的 player.titleId 是客户端自带称号体系，两不相干）
  db.all("PRAGMA table_info(saves)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'title_id')) {
      safeAddColumn('saves', 'title_id', 'ALTER TABLE saves ADD COLUMN title_id INTEGER');
    }
  });
  // Y6：预置称号目录（name UNIQUE + OR IGNORE → 重启幂等；id 由自增分配，业务只按 source 定位）
  db.run(`INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES
    ('登峰造极', '{"expRate":0.05}', 'rank_realm'),
    ('武林盟主', '{"atkRate":0.03}', 'rank_combat'),
    ('富甲一方', '{"stoneRate":0.03}', 'rank_stones'),
    ('回归仙人', '{"expRate":0.02}', 'return'),
    ('初入江湖', '{"expRate":0.01}', 'achievement')`);
  // Y2：daily_quests——每日任务进度 + 宝箱领取标记（quest_key='chest_25' 等，done=1 即已领）；
  // UNIQUE(user_id,date,quest_key) 是并发领取/重复计数的唯一防线；date=北京时区 YYYY-MM-DD
  db.run(`
    CREATE TABLE IF NOT EXISTS daily_quests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      quest_key TEXT NOT NULL,
      progress INTEGER NOT NULL DEFAULT 0,
      done INTEGER NOT NULL DEFAULT 0,
      UNIQUE (user_id, date, quest_key),
      FOREIGN KEY (user_id) REFERENCES users (id)
    )
  `);
  // Y4：渡劫天劫——失败冷却/累计胜场/最近成功目标（服务端自有状态放独立表，不进客户端权威的 save_data JSON）
  db.run(`
    CREATE TABLE IF NOT EXISTS rebirth_state (
      user_id INTEGER PRIMARY KEY,
      fail_until INTEGER,
      wins INTEGER NOT NULL DEFAULT 0,
      last_target TEXT,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users (id)
    )
  `);
  // Y3A：rebirth_state 渡劫垫刀两列（PRAGMA 守卫 ALTER 幂等）——
  // pills=已垫刀数（0..10，下一次引动天劫时消耗，胜败皆焚）；pill_stash=凝元丹仓库（炼丹炉凝元丹出炉 +1 入库）
  db.all("PRAGMA table_info(rebirth_state)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'pills')) {
      safeAddColumn('rebirth_state', 'pills', 'ALTER TABLE rebirth_state ADD COLUMN pills INTEGER NOT NULL DEFAULT 0');
    }
  });
  db.all("PRAGMA table_info(rebirth_state)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'pill_stash')) {
      safeAddColumn('rebirth_state', 'pill_stash', 'ALTER TABLE rebirth_state ADD COLUMN pill_stash INTEGER NOT NULL DEFAULT 0');
    }
  });
  // Y4：预置称号（name UNIQUE + OR IGNORE → 重启幂等）
  db.run(`INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES
    ('渡劫飞升', '{"atkRate":0.05}', 'rebirth')`);
  // Y14：rankings.season——赛季归属标记（北京时区 YYYY-MM；跨月惰性归档上季 TOP3 后全表重标）
  // RANKINGMIG089：rankings 的两处加列守卫（season / name）**合并为一次 schema 读取** ——
  // 原先 :380 与 :388 各读一次同一份 schema，纯冗余入队；合并后语义等价
  // （season 的 ALTER 仍先于 name 入队；backfillRankingNames() 仍在两者之后）。
  // 该 PRAGMA 只是**快路径**（列已存在则省一次 DDL），**不能**作为「是否缺列」的判据：
  // 紧随 CREATE TABLE 的 PRAGMA 无完成屏障，可能读到空/部分 schema（实测 rows=0 @44ms）而误报缺列。
  // 真正兜底的是 safeAddColumn：即便误判，`duplicate column name` 也会被吞掉，不再顶崩进程。
  db.all("PRAGMA table_info(rankings)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'season')) {
      safeAddColumn('rankings', 'season', 'ALTER TABLE rankings ADD COLUMN season TEXT');
    }
    if (!err && rows && !rows.some((r: any) => r.name === 'name')) {
      safeAddColumn('rankings', 'name', "ALTER TABLE rankings ADD COLUMN name TEXT NOT NULL DEFAULT ''");
    }
    backfillRankingNames(); // 列必存在：或建表自带（:184）或上方 ADD 已入队，且已幂等
  });
  // Y14：赛季归档快照（UNIQUE(season,rank) 是防并发重复归档/重复发奖的唯一防线）
  db.run(`
    CREATE TABLE IF NOT EXISTS season_archives (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      season TEXT NOT NULL,
      rank INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      username TEXT NOT NULL,
      realm TEXT NOT NULL DEFAULT '',
      combat_power INTEGER NOT NULL DEFAULT 0,
      spirit_stones INTEGER NOT NULL DEFAULT 0,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      UNIQUE (season, rank),
      FOREIGN KEY (user_id) REFERENCES users (id)
    )
  `);
  // Y14：赛季结算称号 seed（OR IGNORE 幂等）
  db.run(`INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES
    ('赛季魁首', '{"expRate":0.03}', 'season_top1'),
    ('赛季榜眼', '{"expRate":0.02}', 'season_top2'),
    ('赛季探花', '{"expRate":0.01}', 'season_top3')`);
  // Y15：stats_daily——每日四维统计（修为/灵石/击杀/在线分钟），埋点=POST /api/save 存档差值（与 Y2 每日任务同源同口径）；
  // PRIMARY KEY(player_id,date) 单语句 upsert 累加（防并发丢更新），跨日自然分行；date=北京时区 YYYY-MM-DD
  db.run(`
    CREATE TABLE IF NOT EXISTS stats_daily (
      player_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      exp_gain INTEGER NOT NULL DEFAULT 0,
      silver_gain INTEGER NOT NULL DEFAULT 0,
      kills INTEGER NOT NULL DEFAULT 0,
      minutes INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (player_id, date),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  // Y16：chronicle——全服共享时间线（江湖志）：关键事件由服务端各埋点路径写入，只增不改不删
  db.run(`
    CREATE TABLE IF NOT EXISTS chronicle (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts DATETIME DEFAULT CURRENT_TIMESTAMP,
      player_id INTEGER,
      nickname TEXT NOT NULL DEFAULT '',
      text TEXT NOT NULL,
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  // Y17：alchemy——炼丹炉：每玩家 3 炉位（slot 0..2），行存在即炉位在炼（UNIQUE(player_id,slot) 是"同炉位在炼拒绝"
  // 与并发双开的唯一防线）；领取即删行，奖励走邮件（insertMail 通道）
  db.run(`
    CREATE TABLE IF NOT EXISTS alchemy (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      player_id INTEGER NOT NULL,
      slot INTEGER NOT NULL,
      pill_name TEXT NOT NULL,
      start_at INTEGER NOT NULL,
      mature_at INTEGER NOT NULL,
      UNIQUE (player_id, slot),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);

  // Y19：achievement_claimed——成就领取记录（PRIMARY KEY(user_id,ach_id) 是防重复领奖的唯一防线）；
  // 成就本体不落库：达成状态每次请求从 stats_daily/daily_quests/saves 惰性推导（Y19 零新增埋点零新增统计表）
  db.run(`
    CREATE TABLE IF NOT EXISTS achievement_claimed (
      user_id INTEGER NOT NULL,
      ach_id TEXT NOT NULL,
      claimed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (user_id, ach_id),
      FOREIGN KEY (user_id) REFERENCES users (id)
    )
  `);
  // E1：economy_ledger——经济镜像账本（旁路观察，零行为改变）：存档写路径差值记账一行一镜像（kind='mirror'），
  // anomaly_json 仅在命中异常规则时非 NULL；只增不改不删，供 GM /api/economy/* 只读汇总，绝不拦截/拒绝存档
  db.run(`
    CREATE TABLE IF NOT EXISTS economy_ledger (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      player_id INTEGER NOT NULL,
      ts DATETIME DEFAULT CURRENT_TIMESTAMP,
      kind TEXT NOT NULL DEFAULT 'mirror',
      silver_delta INTEGER,
      exp_delta INTEGER,
      level_from INTEGER,
      level_to INTEGER,
      silver_after INTEGER,
      anomaly_json TEXT,
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_economy_ledger_player_ts ON economy_ledger(player_id, ts)`);
  // Y18：pets——妖灵宠物（服务端权威，轻量版每玩家一只，UNIQUE(player_id) 是"重复收养拒绝"与并发双收的
  // 唯一防线）；hunger=喂食度（累计，喂养 +30，上限 9999），level=floor(hunger/100)，exp 为 hunger 镜像列
  db.run(`
    CREATE TABLE IF NOT EXISTS pets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      player_id INTEGER NOT NULL UNIQUE,
      name TEXT NOT NULL,
      rarity TEXT NOT NULL DEFAULT '凡',
      level INTEGER NOT NULL DEFAULT 0,
      exp INTEGER NOT NULL DEFAULT 0,
      hunger INTEGER NOT NULL DEFAULT 0,
      bond INTEGER NOT NULL DEFAULT 0,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  // T2SPIRIT089：T2 灵宠面板新增两列（**幂等加列**，冷启动 / 重跑双安全）。
  //   本环是末环追加，顶层 pets 建表 DDL 不在可动范围 ⇒ 走 safeAddColumn（DDL 自带幂等）。
  //   * pets.merged      —— 融合状态标记（策划 §2.7 步骤 1「妖灵归位」：服务端妖灵结算进客户端灵宠后
  //                         本行标记 merged=1，保留不删、幂等；0=未融合 / 1=已归位）。
  //   * pets.merge_pity  —— 融合失败保底计数（策划 §2.4：连续失败 3 次后第 4 次必成功；成功清零）。
  //                         **服务端权威**：若交由客户端报数，客户端不报失败即可无限免费必成。
  //   * pets.sub_consumed—— 累计消耗的副宠数（审计面：融合过多少次，面板/GM 可核）。
  //   ★ 位置纪律（本环实测踩过）：这三行**必须留在 db.serialize 回调内**，不可提到模块顶层。
  //     `const db` 在下方初始化，顶层直调 safeAddColumn ⇒ `ReferenceError: Cannot access 'db'
  //     before initialization` ⇒ 进程起不来（TDZ，实测同 srv_patch_rankmig 文件头警告）。
  //   ★ 三列均不做 PRAGMA 前置守卫：safeAddColumn 自身容忍 duplicate column name，
  //     重复入队无害（守卫只是省一次 DDL 的快路径，不是正确性依赖 —— 与第 18 环口径一致）。
  safeAddColumn('pets', 'merged', 'ALTER TABLE pets ADD COLUMN merged INTEGER NOT NULL DEFAULT 0');
  safeAddColumn('pets', 'merge_pity', 'ALTER TABLE pets ADD COLUMN merge_pity INTEGER NOT NULL DEFAULT 0');
  safeAddColumn('pets', 'sub_consumed', 'ALTER TABLE pets ADD COLUMN sub_consumed INTEGER NOT NULL DEFAULT 0');
  // ── R-018（r018 环）妖灵培养重设计：幂等加列 + 新表（**必须在 db.serialize 回调内**，t2spirit G8b TDZ 教训）──
  //   * pets.aptitude            —— 资质（D3 点化，0..100），进 PP 的资质K
  //   * pet_play_log.tease/brush/talk —— D2 三种互动各自的「今日免费额度」计数（各 <1 放行）
  //   * pet_play_log.bought      —— D2 买额度计数（< R018_BUY_DAILY_MAX 放行）
  //   * pet_spirit_exped         —— D4 秘径每日派遣闸门（PK(player_id,date) 单语句原子）
  safeAddColumn('pets', 'aptitude', 'ALTER TABLE pets ADD COLUMN aptitude INTEGER NOT NULL DEFAULT 0');
  // R-018 D5 灵纹（r018b 环）：当前生效灵纹（'' = 未激活）
  safeAddColumn('pets', 'rune_active', "ALTER TABLE pets ADD COLUMN rune_active TEXT NOT NULL DEFAULT ''");
  safeAddColumn('pet_play_log', 'tease', 'ALTER TABLE pet_play_log ADD COLUMN tease INTEGER NOT NULL DEFAULT 0');
  safeAddColumn('pet_play_log', 'brush', 'ALTER TABLE pet_play_log ADD COLUMN brush INTEGER NOT NULL DEFAULT 0');
  safeAddColumn('pet_play_log', 'talk', 'ALTER TABLE pet_play_log ADD COLUMN talk INTEGER NOT NULL DEFAULT 0');
  safeAddColumn('pet_play_log', 'bought', 'ALTER TABLE pet_play_log ADD COLUMN bought INTEGER NOT NULL DEFAULT 0');
  db.run(`
    CREATE TABLE IF NOT EXISTS pet_spirit_exped (
      player_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      started_at INTEGER NOT NULL,
      claimed INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (player_id, date),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);

  // Y18：pet_play_log——每日嬉戏次数（UNIQUE(player_id,date)=PK 单语句原子 upsert，times<3 才放行）
  db.run(`
    CREATE TABLE IF NOT EXISTS pet_play_log (
      player_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      times INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (player_id, date),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  // Y18：pet_care_log——喂养/嬉戏/收养/精魄流水（伴生页"喂养记录"；每次写入后裁剪至 PET_CARE_LOG_KEEP 条防膨胀）
  db.run(`
    CREATE TABLE IF NOT EXISTS pet_care_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      player_id INTEGER NOT NULL,
      kind TEXT NOT NULL,
      detail TEXT NOT NULL DEFAULT '',
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_pet_care_log_player ON pet_care_log(player_id, id)`);
  // DG：dungeon_tracker——秘境/地宫每日门槛与追踪（R5：地宫客户端无任何计数器，服务端第一次"看见"秘境行为）：
  // count=entry API 权威计数（软门槛账本，超上限仍累加留痕）；observed=存档 statistics.secretRealmCount 差值被动观测；
  // adventure=statistics.adventureCount 差值（刷度参考）；单日 count 或 observed > 阈值 → anomaly=1（GM 可查）
  db.run(`
    CREATE TABLE IF NOT EXISTS dungeon_tracker (
      player_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      count INTEGER NOT NULL DEFAULT 0,
      observed INTEGER NOT NULL DEFAULT 0,
      adventure INTEGER NOT NULL DEFAULT 0,
      last_ts INTEGER,
      anomaly INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (player_id, date),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_dungeon_anomaly ON dungeon_tracker(anomaly, date)`);
  // ── [r063] R-063 roguelike 地宫独立账本列（与普通点选 count/last_ts 分账；幂等加列）──
  safeAddColumn('dungeon_tracker', 'rogue_count', 'ALTER TABLE dungeon_tracker ADD COLUMN rogue_count INTEGER NOT NULL DEFAULT 0');
  safeAddColumn('dungeon_tracker', 'rogue_last_ts', 'ALTER TABLE dungeon_tracker ADD COLUMN rogue_last_ts INTEGER');
  // Y3A：adventures——奇遇日记：每日 3 次随机奇遇（白 60/蓝 25/紫 12/金 3%），一抽一行；
  // UNIQUE(player_id,date,count) 是"每日 3 次上限"与并发双抽 409 的唯一防线（count=当日第几次，1..3）
  db.run(`
    CREATE TABLE IF NOT EXISTS adventures (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      player_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      count INTEGER NOT NULL,
      tier TEXT NOT NULL,
      event_key TEXT NOT NULL DEFAULT '',
      exp_gain INTEGER NOT NULL DEFAULT 0,
      stones INTEGER NOT NULL DEFAULT 0,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      UNIQUE (player_id, date, count),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_adventures_player ON adventures(player_id, date)`);
  // 0.8.6：奇遇奖励多样化 —— tickets（抽奖券）/ bonus_text（额外珍宝名）
  // 与既有 linuxdo_id 同款 PRAGMA 迁移，老库安全跳过
  db.all("PRAGMA table_info(adventures)", (err, rows: any[]) => {
    if (err || !rows) return;
    if (!rows.some((r) => r.name === 'tickets')) safeAddColumn('adventures', 'tickets', 'ALTER TABLE adventures ADD COLUMN tickets INTEGER NOT NULL DEFAULT 0');
    if (!rows.some((r) => r.name === 'bonus_text')) safeAddColumn('adventures', 'bonus_text', "ALTER TABLE adventures ADD COLUMN bonus_text TEXT NOT NULL DEFAULT ''");
if (!rows.some((r) => r.name === 'drawn_at')) safeAddColumn('adventures', 'drawn_at', 'ALTER TABLE adventures ADD COLUMN drawn_at INTEGER NOT NULL DEFAULT 0'); // [r057] 冷却基准（epoch ms）
  });
  // Y3A：金色奇遇称号 seed（OR IGNORE 幂等；业务按 source='adventure_gold' 定位授予）
  db.run(`INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES ('福缘深厚', '{"stoneRate":0.03}', 'adventure_gold')`);
  // Y19：spirit_farm——洞府灵田：每玩家 3 块田（slot 1..3），行存在即田上有作物（harvested=0 为活跃行）；
  // 部分唯一索引 idx_farm_active_slot 是"同田不可重复种植"与并发双种 409 的唯一防线
  // （历史行 harvested=1 不入索引，可留档且不阻碍复种）；收获=守卫式单语句 harvested=1，防并发双收
  db.run(`
    CREATE TABLE IF NOT EXISTS spirit_farm (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      player_id INTEGER NOT NULL,
      slot INTEGER NOT NULL,
      crop TEXT NOT NULL,
      planted_at INTEGER NOT NULL,
      mature_at INTEGER NOT NULL,
      harvested INTEGER NOT NULL DEFAULT 0,
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_farm_player ON spirit_farm(player_id, harvested)`);
  db.run(`CREATE UNIQUE INDEX IF NOT EXISTS idx_farm_active_slot ON spirit_farm(player_id, slot) WHERE harvested = 0`);
  // Y19：farm_unlocks——田地开垦记录（slot 2/3 灵石开垦永久有效；slot 1 免费无需行；
  // PRIMARY KEY 幂等：INSERT OR IGNORE changes=0 即已开垦，防重复扣费）
  db.run(`
    CREATE TABLE IF NOT EXISTS farm_unlocks (
      player_id INTEGER NOT NULL,
      slot INTEGER NOT NULL,
      unlocked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (player_id, slot),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  // 0.8.7 T10：farm_daily_care——照料/催熟的日切状态（北京日切，与 stats_daily 同口径）。
  // PK(player_id,slot,date) 幂等 + ON CONFLICT DO UPDATE ... WHERE x=0 单语句原子闸门：
  // 「每田每日照料 1 次 / 催熟 1 次」与并发双击的唯一防线；每日催熟总次数 = COUNT(boosted=1) 复核。
  // 回滚保留勿删（IF NOT EXISTS，旧代码无害）。
  db.run(`
    CREATE TABLE IF NOT EXISTS farm_daily_care (
      player_id INTEGER NOT NULL,
      slot INTEGER NOT NULL,
      date TEXT NOT NULL,
      tended INTEGER NOT NULL DEFAULT 0,
      boosted INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (player_id, slot, date),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_farm_care_player_date ON farm_daily_care(player_id, date)`);
  // WUDAO（R-GAME3）：悟道十系——每玩家每系至多一行（PK 幂等）；exp=该系累计修为（只增不减，
  // 等级由 exp 阈值纯函数推导，level 列为同语句 upsert 维护的冗余缓存，展示一律以 exp 推导值为准）；
  // 心得入账=单语句 ON CONFLICT 原子 upsert（挂机 tick 与手动顿悟并发安全，无读改写竞态）
  db.run(`
    CREATE TABLE IF NOT EXISTS wudao (
      player_id INTEGER NOT NULL,
      dao_type TEXT NOT NULL,
      level INTEGER NOT NULL DEFAULT 1,
      exp INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (player_id, dao_type),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  // WUDAO：悟道日志（心得来源 idle=挂机 roll / manual=灵石顿悟；写入后裁剪至最近 WUDAO_LOG_KEEP 条防膨胀）
  db.run(`
    CREATE TABLE IF NOT EXISTS wudao_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      player_id INTEGER NOT NULL,
      dao_type TEXT NOT NULL,
      exp INTEGER NOT NULL DEFAULT 0,
      source TEXT NOT NULL DEFAULT 'idle',
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_wudao_log_player ON wudao_log(player_id, id)`);
  // Y6B：mentorships 师徒关系——徒弟发起拜师（目标须境界≥筑基期 且 总等级≥徒弟+5，API 侧校验）；
  // status: pending(预留)/active/completed/expired；部分唯一索引 idx_mentorships_apprentice_active 是
  // "每徒弟同时仅 1 位在门师傅"的唯一防线（completed/expired 历史行不占位，可再拜）；每师傅 ≤3 弟子
  // 由拜师守卫式单语句 INSERT（COUNT 子查询）兜底；解除=expired + ended_at（双方 7 天冷却起点）；
  // tax_stones=师傅累计抽成灵石（徒弟收益 5% 流水累计）；mentor_buff_until=出师 ×1.3 增益截止（+7 天）
  db.run(`
    CREATE TABLE IF NOT EXISTS mentorships (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      mentor_id INTEGER NOT NULL,
      apprentice_id INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'active',
      created_at INTEGER NOT NULL,
      graduated_at INTEGER,
      ended_at INTEGER,
      mentor_buff_until INTEGER,
      tax_stones INTEGER NOT NULL DEFAULT 0,
      FOREIGN KEY (mentor_id) REFERENCES users (id),
      FOREIGN KEY (apprentice_id) REFERENCES users (id)
    )
  `);
  db.run(`CREATE UNIQUE INDEX IF NOT EXISTS idx_mentorships_apprentice_active ON mentorships(apprentice_id) WHERE status IN ('pending','active')`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_mentorships_mentor ON mentorships(mentor_id, status)`);
  // ── 批2 社交三件：好友互赠 / 结拜金兰 / 道侣（schema_v17）──
  db.run(`CREATE TABLE IF NOT EXISTS friendships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    friend_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    UNIQUE (user_id, friend_id)
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_friendships_user ON friendships(user_id)`);
  db.run(`CREATE TABLE IF NOT EXISTS friend_gifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    receiver_id INTEGER NOT NULL,
    quality TEXT NOT NULL DEFAULT 'white',
    stones INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_friend_gifts_sender ON friend_gifts(sender_id, created_at)`);
  db.run(`CREATE TABLE IF NOT EXISTS sworn_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    creator_id INTEGER NOT NULL,
    bond INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    disbanded INTEGER NOT NULL DEFAULT 0
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS sworn_members (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at INTEGER NOT NULL,
    last_cheer_date TEXT,
    PRIMARY KEY (group_id, user_id)
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_sworn_members_user ON sworn_members(user_id)`);
  db.run(`CREATE TABLE IF NOT EXISTS couples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_a INTEGER NOT NULL,
    user_b INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    married_at INTEGER,
    ended_at INTEGER,
    last_birds_date TEXT
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_couples_a ON couples(user_a, status)`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_couples_b ON couples(user_b, status)`);
  // 道侣喜宴：couple_feasts——每对道侣一生一席（UNIQUE(couple_id) 是"开过不再开"的唯一防线）；
  // couple_feast_guests——宾客赴宴记录（PK(feast_id,user_id) 每人每席限一次，stones=所得喜糖快照）
  db.run(`
    CREATE TABLE IF NOT EXISTS couple_feasts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      couple_id INTEGER NOT NULL,
      created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL,
      UNIQUE (couple_id),
      FOREIGN KEY (couple_id) REFERENCES couples (id)
    )
  `);
  db.run(`
    CREATE TABLE IF NOT EXISTS couple_feast_guests (
      feast_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      stones INTEGER NOT NULL,
      created_at INTEGER NOT NULL,
      PRIMARY KEY (feast_id, user_id),
      FOREIGN KEY (feast_id) REFERENCES couple_feasts (id),
      FOREIGN KEY (user_id) REFERENCES users (id)
    )
  `);
  // ── 批3：擂台 / 恩怨 / 传功（schema_v17 续）──
  db.run(`CREATE TABLE IF NOT EXISTS arena_battles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenger_id INTEGER NOT NULL,
    defender_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    winner_id INTEGER,
    log TEXT,
    created_at INTEGER NOT NULL,
    resolved_at INTEGER
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_arena_def ON arena_battles(defender_id, status)`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_arena_cha ON arena_battles(challenger_id, status)`);
  // ── T16（0.8.8）演武场：试炼 / 积分段位 / 快照挑战 / 试炼日状态 ──
  //   全部 `CREATE TABLE IF NOT EXISTS` 且**建表即带全部列**（最稳，后续无需 ALTER）。
  //   * arena_trials       —— 试炼战斗流水（won=1 计次；first_clear=1 为首通，部分唯一索引防重复首通）
  //   * arena_scores       —— 演武场积分/段位（独立表，不动 rankings 存量结构，§6.1）
  //   * arena_snapshots    —— 快照挑战流水（唯一索引 (challenger,target,date) = R6「同一目标每日 1 次」的原子防线）
  //   * arena_trial_daily  —— 试炼日状态（今日已购次数 + 每日首胜/三连胜一次性奖励已发标记）
  db.run(`CREATE TABLE IF NOT EXISTS arena_trials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    realm_index INTEGER NOT NULL,
    layer INTEGER NOT NULL,
    kind TEXT NOT NULL,
    date TEXT NOT NULL,
    won INTEGER NOT NULL DEFAULT 0,
    first_clear INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_arena_trials_daily ON arena_trials(user_id, date)`);
  db.run(`CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_trials_first ON arena_trials(user_id, realm_index, layer) WHERE first_clear = 1`);
  db.run(`CREATE TABLE IF NOT EXISTS arena_scores (
    user_id INTEGER PRIMARY KEY,
    points INTEGER NOT NULL DEFAULT 0,
    tier INTEGER NOT NULL DEFAULT 1,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS arena_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenger_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    won INTEGER NOT NULL,
    date TEXT NOT NULL,
    created_at INTEGER NOT NULL
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_arena_snap_daily ON arena_snapshots(challenger_id, date)`);
  db.run(`CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_snap_once ON arena_snapshots(challenger_id, target_id, date)`);
  db.run(`CREATE TABLE IF NOT EXISTS arena_trial_daily (
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    buys INTEGER NOT NULL DEFAULT 0,
    first_win INTEGER NOT NULL DEFAULT 0,
    triple_win INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
  )`);
  // ── T5（0.8.9）修复落点：farm_daily_care 照料计次列 tend_count 的**幂等迁移** ──
  //   ★ 为何落在本环（第 20 环）而非灵田环（第 15 环）：
  //     第 18 环 rankingmig 的 G5/G7 硬编码「全仓 safeAddColumn 调用点 == 20 / ADD COLUMN == 20」，
  //     且该环为**禁改文件** ⇒ 第 15 环任何新增加列都会让它 FAIL。本环在其之后 ⇒ 计数门禁不受影响。
  //   * tend_count：farm_daily_care 当日该田照料次数（tended 原为布尔，装不下次数）。
  //     tendBonus = min(FARM_TEND_CAP, tend_count × FARM_TEND_PER)（见第 15 环 farmHarvestMods）。
  //     幂等 safeAddColumn（容忍 duplicate column name；空库冷启动 / 重跑双安全）。
  //   * farm_daily_care 的 CREATE TABLE（第 12 环）在本行之前已入 db.serialize 队列 ⇒ PRAGMA 可见该表。
  db.all("PRAGMA table_info(farm_daily_care)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'tend_count')) {
      safeAddColumn('farm_daily_care', 'tend_count', 'ALTER TABLE farm_daily_care ADD COLUMN tend_count INTEGER NOT NULL DEFAULT 0');
    }
  });
  // ── R-019①（farm2 环）灵田照料 2 小时冷却落点：farm_daily_care.last_tend_at 的幂等迁移 ──
  //   口径（T5 §7-Q3 原文「每 2 小时 1 次」）：12 次/日封顶已由 t5_crops 落地，本列补「时间间隔」。
  //   last_tend_at = 该田当日**最近一次照料**的 epoch ms（0 = 今日未照料过）。
  //   幂等 safeAddColumn（容忍 duplicate column name；空库冷启动 / 重跑双安全）。
  db.all("PRAGMA table_info(farm_daily_care)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'last_tend_at')) {
      safeAddColumn('farm_daily_care', 'last_tend_at', 'ALTER TABLE farm_daily_care ADD COLUMN last_tend_at INTEGER NOT NULL DEFAULT 0');
    }
  });
  db.run(`CREATE TABLE IF NOT EXISTS grudges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    enemy_id INTEGER NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    avenged INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_revenge_at INTEGER,
    UNIQUE (owner_id, enemy_id)
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_grudges_owner ON grudges(owner_id, avenged)`);
  db.run(`CREATE TABLE IF NOT EXISTS social_scores (
    user_id INTEGER PRIMARY KEY,
    renown INTEGER NOT NULL DEFAULT 0,
    virtue INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS teach_log (
    user_id INTEGER NOT NULL,
    apprentice_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    UNIQUE (user_id, date)
  )`);
  // ── 批4：师门请安 / 茶馆竞猜 / 世界妖兽（schema_v17 续）──
  db.run(`CREATE TABLE IF NOT EXISTS teahouse_bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    topic_id INTEGER NOT NULL,
    side INTEGER NOT NULL,
    stones INTEGER NOT NULL,
    won INTEGER,
    payout INTEGER,
    created_at INTEGER NOT NULL,
    UNIQUE (user_id, date)
  )`);
  // 0.8.6：每日行乐流水（掷骰 / 一签 / 翻牌）。UNIQUE(player_id,date,kind,count) 是
  // 「每日次数上限」与「并发双击」的唯一防线（同 adventures / pet_play_log 口径）。
  db.run(`CREATE TABLE IF NOT EXISTS fun_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    kind TEXT NOT NULL,
    count INTEGER NOT NULL,
    cost INTEGER NOT NULL DEFAULT 0,
    payout INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    UNIQUE (player_id, date, kind, count)
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_fun_daily_player ON fun_daily(player_id, date)`);
  db.run(`CREATE TABLE IF NOT EXISTS worldboss (
    date TEXT PRIMARY KEY,
    hp_max INTEGER NOT NULL,
    hp_cur INTEGER NOT NULL,
    killed INTEGER NOT NULL DEFAULT 0,
    killer_id INTEGER
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS worldboss_hits (
    date TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    damage INTEGER NOT NULL DEFAULT 0,
    strikes INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, user_id)
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS mentor_greetings (
    date TEXT NOT NULL,
    mentor_id INTEGER NOT NULL,
    apprentice_id INTEGER NOT NULL,
    greeted_by TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (date, mentor_id, apprentice_id)
  )`);
  // ── 批5：仙途指引 / 首周七日礼 / 活动排期（schema_v17 续）──
  db.run(`CREATE TABLE IF NOT EXISTS guide_progress (
    user_id INTEGER NOT NULL,
    step_id TEXT NOT NULL,
    claimed_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, step_id)
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS week_goals (
    user_id INTEGER NOT NULL,
    day INTEGER NOT NULL,
    claimed_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, day)
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS activity_frame (
    date TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    mult REAL NOT NULL DEFAULT 1.0,
    title TEXT NOT NULL DEFAULT ''
  )`);
  db.run(`INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES ('七日筑基', '{"expRate":0.02}', 'week7')`);
  // Y6B：出师称号 seed（OR IGNORE 幂等；业务按 source='mentor_grad' 定位授予）
  db.run(`INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES ('良师益友', '{"expRate":0.02}', 'mentor_grad')`);
  // Y20：gongfa 功法目录（六部：焚天诀/御剑术/不灭体/大衍诀/周天阵/御灵术，key UNIQUE 定位；
  // name UNIQUE 兜底防重复 seed）+ INSERT OR IGNORE 重启幂等
  db.run(`
    CREATE TABLE IF NOT EXISTS gongfa (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      key TEXT NOT NULL UNIQUE,
      name TEXT NOT NULL UNIQUE,
      stat TEXT NOT NULL,
      stat_name TEXT NOT NULL,
      sort INTEGER NOT NULL DEFAULT 0
    )
  `);
  db.run(`INSERT OR IGNORE INTO gongfa (key, name, stat, stat_name, sort) VALUES
    ('fentian',  '焚天诀', 'attack',  '攻击', 1),
    ('yujian',   '御剑术', 'crit',    '暴击', 2),
    ('bumie',    '不灭体', 'defense', '防御', 3),
    ('dayan',    '大衍诀', 'hit',     '命中', 4),
    ('zhoutian', '周天阵', 'maxHp',   '气血', 5),
    ('yuling',   '御灵术', 'dodge',   '闪避', 6)`);
  // Y20：player_gongfa 玩家功法进度——每玩家每部至多一行（PK 幂等）；level 0=未入门 1..10；
  // exp=累计投入修为（只增不减，展示等级以 exp 推导为准，level 列为守卫式升级维护的冗余缓存）；
  // 升级=守卫式单语句（WHERE level=旧值），并发双升只一方生效
  db.run(`
    CREATE TABLE IF NOT EXISTS player_gongfa (
      player_id INTEGER NOT NULL,
      gongfa_id INTEGER NOT NULL,
      level INTEGER NOT NULL DEFAULT 0,
      exp INTEGER NOT NULL DEFAULT 0,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (player_id, gongfa_id),
      FOREIGN KEY (player_id) REFERENCES users (id),
      FOREIGN KEY (gongfa_id) REFERENCES gongfa (id)
    )
  `);
  // Y21：activity_config 活动引擎全局开关（KV 表，admin/GM 经 /api/gm/activity/config 写入；
  // engine_on='0' 一键停发所有活动倍率——kill switch，逐场开关在 events.enabled）
  db.run(`
    CREATE TABLE IF NOT EXISTS activity_config (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `);
  db.run(`INSERT OR IGNORE INTO activity_config (key, value) VALUES ('engine_on', '1')`);
  // Y21：events 限时活动实例——type=exp2|stones2|boss|drop（服务端常量 ACT_TYPES 定档）；
  // multiplier=收益倍率（1..100，非法配置读取时钳 1）；start_at/end_at=ms epoch（恰 start 开启、恰 end 结束）；
  // enabled=逐场开关；活动窗口查询走 idx_events_window，倍率结算点每次请求读一次（同窗口内一致）
  db.run(`
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      type TEXT NOT NULL,
      name TEXT NOT NULL,
      multiplier REAL NOT NULL DEFAULT 2,
      start_at INTEGER NOT NULL,
      end_at INTEGER NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_events_window ON events(enabled, start_at, end_at)`);
  // Y21-R "Tianjiang Lingyu" (rain) settlement state: one row per (player, event, Beijing date).
  // PRIMARY KEY is the single guard against settling the same window twice. All state lives in
  // columns, never in saves.save_data JSON (the client uploads that JSON authoritatively).
  // last_minutes = last observed stats_daily.minutes; accrued_minutes = remainder below 1h;
  // settled_minutes = minutes already paid today (daily cap 480 = 8h).
  db.run(`
    CREATE TABLE IF NOT EXISTS activity_rain_state (
      player_id INTEGER NOT NULL,
      event_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      last_minutes INTEGER NOT NULL DEFAULT 0,
      accrued_minutes INTEGER NOT NULL DEFAULT 0,
      settled_minutes INTEGER NOT NULL DEFAULT 0,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (player_id, event_id, date),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_rain_state_date ON activity_rain_state(date)`);
  // [act087] 0.8.7 T5 限时活动六新表（全部 IF NOT EXISTS；回滚保留勿删——旧代码读到新表无害）。
  // 主键=幂等与并发防重的唯一防线（activity_rain_state / fun_daily 同款纪律）。
  // event_boss 额外带 killed_at/settled_at 两列（D-7 休战期需要击杀时刻；settled_at 便于核对）。
  db.run(`
    CREATE TABLE IF NOT EXISTS activity_rank_settled (
      event_id INTEGER NOT NULL,
      board TEXT NOT NULL,
      user_id INTEGER NOT NULL,
      rank INTEGER,
      tier TEXT NOT NULL DEFAULT '',
      score INTEGER NOT NULL DEFAULT 0,
      reward INTEGER NOT NULL DEFAULT 0,
      settled_at INTEGER NOT NULL,
      PRIMARY KEY (event_id, board, user_id),
      FOREIGN KEY (user_id) REFERENCES users (id)
    )
  `);
  db.run(`
    CREATE TABLE IF NOT EXISTS activity_checkin (
      player_id INTEGER NOT NULL,
      event_id INTEGER NOT NULL,
      day INTEGER NOT NULL,
      claimed_at INTEGER NOT NULL,
      PRIMARY KEY (player_id, event_id, day),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  db.run(`
    CREATE TABLE IF NOT EXISTS activity_token (
      player_id INTEGER NOT NULL,
      token_key TEXT NOT NULL,
      balance INTEGER NOT NULL DEFAULT 0,
      earned_total INTEGER NOT NULL DEFAULT 0,
      spent_total INTEGER NOT NULL DEFAULT 0,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (player_id, token_key),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  db.run(`
    CREATE TABLE IF NOT EXISTS activity_token_daily (
      player_id INTEGER NOT NULL,
      date TEXT NOT NULL,
      earned INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (player_id, date),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  db.run(`
    CREATE TABLE IF NOT EXISTS event_boss (
      event_id INTEGER PRIMARY KEY,
      hp_max INTEGER NOT NULL,
      hp_cur INTEGER NOT NULL,
      killed INTEGER NOT NULL DEFAULT 0,
      killer_id INTEGER,
      settled INTEGER NOT NULL DEFAULT 0,
      killed_at INTEGER,
      settled_at INTEGER
    )
  `);
  db.run(`
    CREATE TABLE IF NOT EXISTS event_boss_hits (
      event_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      score INTEGER NOT NULL DEFAULT 0,
      strikes INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (event_id, user_id),
      FOREIGN KEY (user_id) REFERENCES users (id)
    )
  `);
  // 冲榜窗口聚合索引（stats_daily 按 date 区间聚合；0.8.6 落地方案 §3 可选索引转正）
    // [r056boss] R-056 万妖巢穴多 boss：老库幂等加列（safeAddColumn 容忍 duplicate column name，冷启动/重跑双安全）。建表语句不动，默认值经 ALTER 生效。
  //   event_boss.boss_no 当前第几只（1 起）；event_boss_hits.free_used 对当前这只已用免费数（换 boss 归零）；event_boss_hits.last_strike_at 上次免费出手时刻（10 分钟冷却锚点）。
  db.all("PRAGMA table_info(event_boss)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'boss_no')) safeAddColumn('event_boss', 'boss_no', 'ALTER TABLE event_boss ADD COLUMN boss_no INTEGER NOT NULL DEFAULT 1');
  });
  db.all("PRAGMA table_info(event_boss_hits)", (err: any, rows: any[]) => {
    if (!err && rows) {
      if (!rows.some((r: any) => r.name === 'free_used')) safeAddColumn('event_boss_hits', 'free_used', 'ALTER TABLE event_boss_hits ADD COLUMN free_used INTEGER NOT NULL DEFAULT 0');
      if (!rows.some((r: any) => r.name === 'last_strike_at')) safeAddColumn('event_boss_hits', 'last_strike_at', 'ALTER TABLE event_boss_hits ADD COLUMN last_strike_at INTEGER NOT NULL DEFAULT 0');
    }
  });
  // [r113boss] R-113 万妖巢穴五只同现：新建 event_boss5（每期 5 行并存，复合主键）。
  //   建表幂等；不改 event_boss / event_boss_hits（前者降级为聚合/结算行，后者仍为跨只累计榜）。
  db.run(`CREATE TABLE IF NOT EXISTS event_boss5 (
    event_id INTEGER NOT NULL,
    boss_no INTEGER NOT NULL,
    hp_max INTEGER NOT NULL,
    hp_cur INTEGER NOT NULL,
    killed INTEGER NOT NULL DEFAULT 0,
    killer_id INTEGER,
    PRIMARY KEY (event_id, boss_no)
  )`);
db.run(`CREATE INDEX IF NOT EXISTS idx_stats_daily_date ON stats_daily(date)`);
  // [act087] 活动限定称号 seed（灵玉阁 1000 玉兑换物；grantTitleBySource 按 source 定位，OR IGNORE 重启幂等）
  db.run(`INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES ('灵玉仙客', '{"expRate":0.01}', 'act087_jade')`);
  // Y-B 悬赏榜：玩家发赏托管（发布即全额扣灵石入表托管）→ 完成者得 90%，10% 系统税；
  // status: open(悬赏中)/accepted(已接取)/done(已完成)/expired(过期退款)/cancelled(取消退款，cancelled 为实现扩展态)；
  // 24h 过期惰性清扫退款（bountySweepCore），poster_name/acceptor_name 为展示快照（对齐 season_archives.username 同款）
  db.run(`
    CREATE TABLE IF NOT EXISTS bounties (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      poster_id INTEGER NOT NULL,
      poster_name TEXT NOT NULL DEFAULT '',
      title TEXT NOT NULL,
      desc TEXT NOT NULL DEFAULT '',
      reward INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'open',
      acceptor_id INTEGER,
      acceptor_name TEXT NOT NULL DEFAULT '',
      created_at INTEGER NOT NULL,
      deadline INTEGER NOT NULL,
      finished_at INTEGER,
      FOREIGN KEY (poster_id) REFERENCES users (id)
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_bounties_open ON bounties(status, reward DESC, id DESC)`);
  // Y16B 传阅：chronicle_praise——江湖志传阅记录（每人每条限一次，PK(entry_id,user_id) 是唯一防线）；
  // 恰第 10 次传阅时当事人（chronicle.player_id 非空）得一次性灵石奖 1000×1.5^境界（境界=rankings.realm_index）
  db.run(`
    CREATE TABLE IF NOT EXISTS chronicle_praise (
      entry_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      created_at INTEGER NOT NULL,
      PRIMARY KEY (entry_id, user_id),
      FOREIGN KEY (entry_id) REFERENCES chronicle (id),
      FOREIGN KEY (user_id) REFERENCES users (id)
    )
  `);
});

// ── fix(rank) 2026-09-17：rankings 存量行昵称回填（幂等，重启安全：只补 name 为空的行）──
// 昵称唯一权威源是 saves.save_data JSON 的 player.name；LEFT JOIN saves 兜底：
// 无存档行 / JSON 解析失败 → 回落 rankings.username（登录账号），保证展示字段永不空。
// 全程参数化查询；只回填不覆盖非空 name。
function backfillRankingNames(): void {
  db.all(
    `SELECT r.user_id AS user_id, r.username AS username, s.save_data AS save_data
     FROM rankings r LEFT JOIN saves s ON s.user_id = r.user_id
     WHERE r.name IS NULL OR r.name = ''`,
    (err: any, rows: any[]) => {
      if (err) {
        console.error('Ranking name backfill query failed:', err.message);
        return;
      }
      if (!rows || rows.length === 0) return;
      let fixed = 0;
      let pending = rows.length;
      rows.forEach((row) => {
        let nickname = '';
        try {
          nickname = String(JSON.parse(row.save_data)?.player?.name ?? '').trim();
        } catch {
          // 解析失败保持空串 → 下面回落登录账号
        }
        if (!nickname) nickname = row.username;
        db.run(
          'UPDATE rankings SET name = ? WHERE user_id = ?',
          [nickname, row.user_id],
          (uerr: any) => {
            pending--;
            if (uerr) {
              console.error('Ranking name backfill update failed:', uerr.message);
            } else {
              fixed++;
            }
            if (pending === 0) {
              console.log(`Ranking name backfill done: ${fixed}/${rows.length} rows updated`);
            }
          }
        );
      });
    }
  );
}

// Middleware to verify access JWT token
const authenticateToken = (req: any, res: any, next: any) => {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];

  if (token == null) return res.sendStatus(401);

  jwt.verify(token, JWT_SECRET_USED, (err: any, payload: any) => {
    // 过期（TokenExpiredError）必须回 401 而非 403：客户端 Xc 请求封装只在 401 时调用 pS()
    // 走 /api/auth/refresh 静默续期并自动重试一次；403 被视为不可恢复会话→logout+“登录已过期”弹窗。
    // 修复前过期也回 403，access token 一到期（曾为 1h）玩家即被强制踢下线（投诉①根因）。
    // 其余错误（签名不符/格式非法）维持 403 原语义。
    if (err) {
      if (err.name === 'TokenExpiredError') return res.sendStatus(401);
      return res.sendStatus(403);
    }
    if (payload.type !== 'access') return res.sendStatus(403);
    req.user = { id: payload.id, username: payload.username };
    next();
  });
};

// ─────────────────────────────────────────────────────────
// GM 后台：额外数据库表 + GM 鉴权中间件
// ─────────────────────────────────────────────────────────
// BASECLEAN089: 原写法带「弱口令兜底」（env 缺失时回落固定口令）—— .env 丢失会静默降级为
//   可猜口令，使 /api/gm/*（发钱/改档/封号）暴露在弱口令下。改为**启动时硬失败**，不静默降级。
const GM_PASSWORD = process.env.GM_PASSWORD;
if (!GM_PASSWORD) {
  console.error('[FATAL] GM_PASSWORD 未设置，拒绝以弱口令启动。请在 .env 配置 GM_PASSWORD 后重启。');
  process.exit(1);
}

// 创建 GM 相关表（在数据库打开后执行）
db.serialize(() => {
  db.run(`
    CREATE TABLE IF NOT EXISTS gm_sessions (
      token TEXT PRIMARY KEY,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `);
  // 会话表（账号重构 2026-09-23，docs/account-refactor-plan.md §2.2；与 migrations/account_refactor.sql 同一增量）：
  // 存 SHA-256 哈希不存原文；expires_at/last_used_at/revoked_at 由 Node 写 ISO UTC 字符串，比较在 Node 内做。
  // 建表后 GM「踢下线/重置密码」既有的 DELETE FROM refresh_tokens（本文件 kick/reset-password 端点）原样生效。
  db.run(`
    CREATE TABLE IF NOT EXISTS refresh_tokens (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id      INTEGER NOT NULL,
      token_hash   TEXT NOT NULL UNIQUE,
      device       TEXT,
      created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
      last_used_at DATETIME,
      expires_at   DATETIME NOT NULL,
      revoked_at   DATETIME
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id)`);
  db.run(`
    CREATE TABLE IF NOT EXISTS lottery_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      username TEXT NOT NULL,
      prize_name TEXT NOT NULL,
      prize_type TEXT NOT NULL,
      prize_rarity TEXT,
      quantity INTEGER DEFAULT 1,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users (id)
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_lottery_history_user ON lottery_history(user_id)`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_lottery_history_created ON lottery_history(created_at DESC)`);
  db.run(`
    CREATE TABLE IF NOT EXISTS gm_audit_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      gm_username TEXT NOT NULL DEFAULT 'gm',
      action TEXT NOT NULL,
      target TEXT,
      detail TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `);
});

// GM 鉴权中间件（基于 GM token）
const authenticateGM = (req: any, res: any, next: any) => {
  const authHeader = req.headers['authorization'] || '';
  const token = authHeader.split(' ')[1] || req.query.token || req.body?.token;
  if (!token) return res.status(401).json({ error: 'GM token required' });
  db.get('SELECT token, expires_at FROM gm_sessions WHERE token = ?', [token], (err: any, row: any) => {
    if (err || !row) return res.status(403).json({ error: 'Invalid GM token' });
    // [v2810] GM \u4f1a\u8bdd\u8fc7\u671f\u5224\u5b9a\uff1aexpires_at \u4e3a\u7a7a\uff08\u5b58\u91cf\u65e7\u884c\uff09\u6216\u5df2\u8fc7\u671f
    //   \u21d2 \u89c6\u4e3a\u65e0\u6548\uff08401 \u5f3a\u5236\u91cd\u65b0\u767b\u5f55\uff09+ \u60f0\u6027\u5220\u884c\u3002
    //   \u9009 401 \u800c\u975e 403\uff1aGM \u524d\u7aef gm-pro.html \u4ec5\u5728 401 \u65f6\u6e05 token \u5e76\u5f39\u56de\u767b\u5f55\u9875\u3002
    const exp = row.expires_at ? Date.parse(String(row.expires_at)) : NaN;
    if (!Number.isFinite(exp) || exp <= Date.now()) {
      db.run('DELETE FROM gm_sessions WHERE token = ?', [token]);
      return res.status(401).json({ error: 'GM session expired' });
    }
    next();
  });
};

// 记录 GM 审计日志
// v28.2 (P2-9): safe primitive coercion for untrusted request values.
// `String(x)` / `Number(x)` / `parseInt(x)` THROW a TypeError ("Cannot convert object to
// primitive value") when `x` is a non-primitive whose `toString` / `Symbol.toPrimitive` is
// not callable -- e.g. body {"id":{"toString":1}} or {"gongfa":{"toString":1}}. That
// surfaced as HTTP 500 for plain client junk. These helpers accept only real primitives and
// never throw: anything else degrades to '' / NaN so the pre-existing guard answers 4xx.
function asStr(x: unknown): string {
  if (typeof x === 'string') return x;
  if (typeof x === 'number' && Number.isFinite(x)) return String(x);
  if (typeof x === 'boolean') return x ? 'true' : 'false';
  return '';
}
function asNum(x: unknown): number {
  if (typeof x === 'number') return x;
  if (typeof x === 'string') return Number(x);
  if (typeof x === 'boolean') return x ? 1 : 0;
  if (x === null) return 0;
  return NaN;
}
function asInt(x: unknown): number {
  if (typeof x === 'number') return Number.isFinite(x) ? Math.trunc(x) : NaN;
  if (typeof x === 'string') { const n = parseInt(x, 10); return Number.isFinite(n) ? n : NaN; }
  return NaN;
}
function logGmAction(action: string, target?: string, detail?: any) {
  db.run(
    'INSERT INTO gm_audit_logs (action, target, detail) VALUES (?, ?, ?)',
    [action, target || null, detail ? JSON.stringify(detail) : null]
  );
}

// 存档读改写互斥（P1-2）：进程内 per-user Promise 串行化（Map<userId, Promise> 队列），
// 防止 GM patch 与玩家 POST /api/save 并发时 SELECT→UPDATE 间隙互相覆盖（后写者胜、先写者丢失）
const saveLocks = new Map<number, Promise<unknown>>();
function withSaveLock<T>(userId: number, fn: () => Promise<T>): Promise<T> {
  const prev = saveLocks.get(userId) || Promise.resolve();
  const run = prev.then(fn, fn); // 前一个任务失败也照常执行本任务
  const chain = run.then(
    () => undefined,
    () => undefined // 吞掉异常，避免污染后续排队任务
  );
  saveLocks.set(userId, chain);
  chain.then(() => {
    if (saveLocks.get(userId) === chain) saveLocks.delete(userId);
  });
  return run;
}

// 修改玩家存档（用于 GM 编辑/发放），gm_revision++ 触发前端实时刷新
function updatePlayerSave(
  userId: number,
  mutate: (saveData: any) => void,
  extraColumns?: Record<string, any>
): Promise<{ ok: boolean; error?: string }> {
  return withSaveLock(userId, () => new Promise((resolve) => {
    db.get('SELECT save_data, gm_revision FROM saves WHERE user_id = ?', [userId], (err: any, row: any) => {
      if (err) return resolve({ ok: false, error: 'Database error' });
      if (!row) return resolve({ ok: false, error: 'No save found' });
      let saveData: any;
      try {
        saveData = JSON.parse(row.save_data);
      } catch (e) {
        return resolve({ ok: false, error: 'Save parse error' });
      }
      const prevEconSnap = extractEconSnapshot(saveData); // E1：变更前经济快照（纯函数自吞异常）
      mutate(saveData);
      const newRevision = (Number(row.gm_revision) || 0) + 1;
      // S1 v26e：可选附加列（默认不传行为完全不变；传入时同锁同语句原子附带，如 title_id 双写）
      let extraSets = '';
      let extraVals: any[] = [];
      if (extraColumns && Object.keys(extraColumns).length > 0) {
        const ekeys = Object.keys(extraColumns);
        for (const ek of ekeys) {
          if (!/^[a-z_][a-z0-9_]*$/i.test(ek)) return resolve({ ok: false, error: 'Bad extra column' });
        }
        extraSets = ', ' + ekeys.map((k) => `${k} = ?`).join(', ');
        extraVals = ekeys.map((k) => extraColumns![k]);
      }
      db.run(
        `UPDATE saves SET save_data = ?, gm_revision = ?, updated_at = CURRENT_TIMESTAMP${extraSets} WHERE user_id = ?`,
        [JSON.stringify(saveData), newRevision, ...extraVals, userId],
        async (updateErr) => {
          if (updateErr) return resolve({ ok: false, error: 'Update failed' });
          await upsertRanking(userId, saveData.player?.name || '', saveData);
          maybeGrantAutoTitles(userId, achievementsLen(saveData)); // Y6 惰性授予（幂等，内部自吞异常）
          writeEconomyMirror(userId, prevEconSnap, extractEconSnapshot(saveData)); // E1 镜像记账（GM patch/邮件领取/炼丹扣费/天劫代写均经此路径；fire-and-forget 不影响结果）
          resolve({ ok: true });
        }
      );
    });
    })); // withSaveLock
}

// ── 排行榜辅助函数：从存档JSON中提取排名字段 ──
const REALM_ORDER_FOR_RANKING = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];

function extractRankingData(saveData: any): {
  realm_index: number;
  realm_level: number;
  exp: number;
  combat_power: number;
  spirit_stones: number;
  reputation: number;
  achievement_count: number;
  kill_count: number;
  play_time: number;
} | null {
  try {
    const player = saveData?.player;
    if (!player) return null;

    const realmIndex = REALM_ORDER_FOR_RANKING.indexOf(player.realm);
    const attack = Number(player.attack) || 0;
    const defense = Number(player.defense) || 0;
    const maxHp = Number(player.maxHp) || 0;
    const spirit = Number(player.spirit) || 0;
    const speed = Number(player.speed) || 0;
    const combatPower = Math.floor(attack + defense + maxHp / 10 + spirit + speed);

    return {
      realm_index: realmIndex >= 0 ? realmIndex : 0,
      realm_level: Number(player.realmLevel) || 1,
      exp: Number(player.exp) || 0,
      combat_power: combatPower,
      spirit_stones: Number(player.spiritStones) || 0,
      reputation: Number(player.reputation) || 0,
      achievement_count: Array.isArray(player.achievements) ? player.achievements.length : 0,
      kill_count: Number(player.statistics?.killCount) || 0,
      play_time: Number(player.playTime) || 0,
    };
  } catch {
    return null;
  }
}

function upsertRanking(userId: number, username: string, saveData: any): Promise<boolean> {
  const data = extractRankingData(saveData);
  if (!data) return Promise.resolve(false);
  // fix(rank) 2026-09-17：冗余存角色昵称（saves.save_data JSON player.name 的当前快照）。
  // 存空串时读侧回落 username；改名场景容忍旧名，玩家下次存档上传即刷新。
  const playerName = String(saveData?.player?.name ?? '').trim();

  return new Promise((resolve) => {
    // 按 user_id 键控 upsert（P1-3）：users.username 本身 UNIQUE，无需按 name 去重。
    // 旧逻辑 `DELETE FROM rankings WHERE username=? AND user_id!=?` 会把"角色名撞他人账号名"
    // 的无辜玩家排行行删掉，且 GM 路径传角色名、玩家路径传账号名导致显示漂移，已移除。
    db.run(
      `INSERT INTO rankings (user_id, username, name, realm_index, realm_level, exp, combat_power, spirit_stones, reputation, achievement_count, kill_count, play_time, season, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
       ON CONFLICT(user_id) DO UPDATE SET
         username = excluded.username,
         name = excluded.name,
         realm_index = excluded.realm_index,
         realm_level = excluded.realm_level,
         exp = excluded.exp,
         combat_power = excluded.combat_power,
         spirit_stones = excluded.spirit_stones,
         reputation = excluded.reputation,
         achievement_count = excluded.achievement_count,
         kill_count = excluded.kill_count,
         play_time = excluded.play_time,
         season = excluded.season,
         updated_at = CURRENT_TIMESTAMP`,
      [userId, username, playerName, data.realm_index, data.realm_level, data.exp, data.combat_power, data.spirit_stones, data.reputation, data.achievement_count, data.kill_count, data.play_time, seasonId(Date.now())],
      (err) => {
        if (err) {
          console.error('Leaderboard sync failed:', err.message);
          resolve(false);
          return;
        }
        resolve(true);
      }
    );
  });
}

// 敏感词列表 - 禁止包含这些词的用户名
const BANNED_USERNAME_WORDS = [
  'admin', 'root', 'system', 'moderator', 'mod', 'fuck', 'shit', 'ass', 'porn', 'sex',
  'gay', 'lesbian', 'nigger', 'chink', 'kike', 'spic', 'xi', 'jinping', 'jiang', 'hu',
  'mao', '共产党', '法轮功', '台独', '藏独', '疆独'
];

// 验证用户名格式和敏感词
const validateUsername = (username: string): { valid: boolean; error?: string } => {
  const trimmed = asStr(username).trim();

  if (trimmed.length < 2 || trimmed.length > 32) {
    return { valid: false, error: 'Username must be between 2 and 32 characters' };
  }

  // 只允许字母、数字、下划线、中文
  if (!/^[a-zA-Z0-9_\u4e00-\u9fa5]+$/.test(trimmed)) {
    return { valid: false, error: 'Username can only contain letters, numbers, underscores, and Chinese characters' };
  }

  // 检查敏感词
  const lowerUsername = trimmed.toLowerCase();
  for (const word of BANNED_USERNAME_WORDS) {
    if (lowerUsername.includes(word.toLowerCase())) {
      return { valid: false, error: 'Username contains forbidden words' };
    }
  }

  return { valid: true };
};

// 验证密码强度
const validatePassword = (passwordRaw: string): { valid: boolean; error?: string } => {
  const password = asStr(passwordRaw);
  if (password.length < 6) {
    return { valid: false, error: 'Password must be at least 6 characters long' };
  }

  if (password.length > 128) {
    return { valid: false, error: 'Password cannot exceed 128 characters' };
  }

  // 要求至少包含字母和数字（可以放松要求，但至少增加一点强度）
  const hasLetter = /[a-zA-Z]/.test(password);
  const hasNumber = /[0-9]/.test(password);

  if (!hasLetter || !hasNumber) {
    return { valid: false, error: 'Password must contain at least one letter and one number' };
  }

  return { valid: true };
};

// ── 会话模型（账号重构 2026-09-23，docs/account-refactor-plan.md §2）：opaque refresh token ──
// 服务端只存 SHA-256 哈希（泄库不可逆）；不轮换（同设备双标签页共享同一 token，轮换必互踢，§2.2 取舍）；
// 180 天滑动窗口：每次刷新 UPDATE last_used_at/expires_at。时间统一 ISO UTC 字符串，比较在 Node 内做。
const REFRESH_TOKEN_DAYS = 180;
const nowIso = () => new Date().toISOString();
const sha256hex = (s: string) => crypto.createHash('sha256').update(s, 'utf8').digest('hex');

// 签发一个新会话行，返回 opaque token 原文（仅此一次可见）
function issueRefreshSession(userId: number, device: unknown): Promise<string> {
  return new Promise((resolve, reject) => {
    const token = crypto.randomBytes(48).toString('base64url');
    const expiresAt = new Date(Date.now() + REFRESH_TOKEN_DAYS * 86400000).toISOString();
    db.run(
      'INSERT INTO refresh_tokens (user_id, token_hash, device, expires_at) VALUES (?, ?, ?, ?)',
      [userId, sha256hex(token), String(device || '').slice(0, 80), expiresAt],
      (err: any) => (err ? reject(err) : resolve(token))
    );
  });
}

// 吊销某用户全部未吊销会话；keepSessionId 指定时跳过该行（自助改密保留当前设备）
function revokeRefreshSessions(userId: number, keepSessionId?: number): Promise<number> {
  return new Promise((resolve, reject) => {
    const sql = keepSessionId
      ? 'UPDATE refresh_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL AND id != ?'
      : 'UPDATE refresh_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL';
    const params: any[] = keepSessionId ? [nowIso(), userId, keepSessionId] : [nowIso(), userId];
    db.run(sql, params, function (this: any, err: any) {
      if (err) reject(err);
      else resolve(this.changes || 0);
    });
  });
}

// ─────────────────────────────────────────────────────────
// 灵石余额回显中间件（YL_STONE_ECHO_V26K）
// 客户端权威存量架构下，服务端独立接口（灵宠/悟道/农田/炼丹/茶楼/双修/邮件/挂机…）会直接改写
// saves.save_data 的 player.spiritStones，但响应体不带余额 → 客户端内存不同步 →
//   ① header 灵石不刷新；② 客户端自动保存把陈旧余额写回，把服务端扣减抹平（白嫖）。
// 这里对白名单路径的成功 JSON 响应统一附加 balance = 最新余额；客户端单点拦截写入 store。
// 只读一次 saves、只加一个字段，不改动任何业务逻辑与响应语义。
// ─────────────────────────────────────────────────────────
// T7_LEGACY (0.8.8 T7 传承 · §3.2) —— 回显侧与客户端写入对称。
// 客户端在 save_data.player.inhStoneWeek 记录传承石「本周已购」（北京周 key，YYYY-MM-DD）。
// GET /api/save 本就是整包 res.json(saveData) 原样透传，此处只做**只读取回 + shape 复核**，
// 供「服务端 -> 客户端」方向也有一条明确的对称通路；过滤规则与存档侧 sanitizeInhSaveField 逐字一致。
// 只读：不写库、不改响应语义、不做限购判定（P1）。脏值一律回落 null（绝不产出 NaN）。
function t7legacyEchoInh(sd: any): string | null {
  try {
    const p = sd && sd.player;
    if (!p || typeof p !== 'object' || Array.isArray(p)) return null;
    const v = p.inhStoneWeek;
    if (typeof v !== 'string') return null;
    if (v === '') return '';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return null;
    const t = Date.parse(v + 'T00:00:00Z');
    if (!Number.isFinite(t) || new Date(t).toISOString().slice(0, 10) !== v) return null;
    return v;
  } catch (e) { return null; }
}

const STONE_ECHO_RE = /^\/api\/(pet|wudao|farm|alchemy|teahouse|couple|friends|mail|offline|quest|sect|gongfa|bounty|arena|adventure|dungeon|rebirth|guide|mentor|daily|events|lottery|market|chat|achievements|stats|rankings|titles|chronicle|save|gm)\b/; // NET2_STALE: gm 域纳入回显（GM 发放后客户端需立刻拿到新余额回填 base）
app.use((req: any, res: any, next: any) => {
  if (req.method !== 'POST' && req.method !== 'GET') return next();
  if (!STONE_ECHO_RE.test(req.path)) return next();
  const origJson = res.json.bind(res);
  let ylEchoDone = false;
  res.json = function (body: any) {
    if (ylEchoDone) return origJson(body);
    ylEchoDone = true;
    if (res.statusCode >= 400) return origJson(body);           // 错误响应不查库
    const uid = req.user && req.user.id;
    if (!uid || !body || typeof body !== 'object' || Array.isArray(body)) return origJson(body);
    if (typeof body.balance === 'number') return origJson(body);
    dbGet('SELECT save_data FROM saves WHERE user_id = ?', [uid]).then((row: any) => {
      let bal: number | null = null;
      try {
        const sd = JSON.parse((row && row.save_data) || '{}');
        const p = sd && sd.player;
        if (p && typeof p.spiritStones === 'number' && isFinite(p.spiritStones)) {
          bal = Math.max(0, Math.floor(p.spiritStones));
        }
      } catch (e) { bal = null; }
      if (bal === null) return origJson(body);
      origJson(Object.assign({}, body, { balance: bal }));
    }).catch(() => origJson(body));
    return res;
  };
  next();
});

// Auth Routes
app.post('/api/auth/register', async (req: any, res: any) => {
  const { username, password } = req.body || {};

  if (!username || !password) {
    return res.status(400).json({ error: 'Username and password are required' });
  }

  // 验证用户名
  const usernameCheck = validateUsername(username);
  if (!usernameCheck.valid) {
    return res.status(400).json({ error: usernameCheck.error });
  }

  // 验证密码强度
  const passwordCheck = validatePassword(password);
  if (!passwordCheck.valid) {
    return res.status(400).json({ error: passwordCheck.error });
  }

  const trimmedUsername = asStr(username).trim();

  try {
    const hashedPassword = await bcrypt.hash(password, 10);

    db.run(
      'INSERT INTO users (username, password_hash) VALUES (?, ?)',
      [trimmedUsername, hashedPassword],
      function (err) {
        if (err) {
          if (err.message.includes('UNIQUE constraint failed')) {
            return res.status(409).json({ error: 'Username already exists' });
          }
          console.error('Database insert error:', err);
          return res.status(500).json({ error: 'Database error' });
        }
        res.status(201).json({ message: 'User registered successfully' });
      }
    );
  } catch (error) {
    console.error('Registration error:', error);
    res.status(500).json({ error: 'Server error' });
  }
});

app.post('/api/auth/login', (req: any, res: any) => {
  const { username, password } = req.body || {};

  if (!username || !password) {
    return res.status(400).json({ error: 'Username and password are required' });
  }

  const trimmedUsername = asStr(username).trim();

  db.get('SELECT * FROM users WHERE username = ?', [trimmedUsername], async (err, user: any) => {
    if (err) {
      console.error('Login database error:', err);
      return res.status(500).json({ error: 'Database error' });
    }
    if (!user) {
      return res.status(404).json({ error: 'User not found', code: 'USER_NOT_FOUND' });
    }

    try {
      if (await bcrypt.compare(asStr(password), user.password_hash)) {
        // 账号重构：封禁账号拒绝登录（banned 列由 GM 封禁端点守卫迁移；缺列时 undefined 为 falsy 不影响）
        if (user.banned) {
          return res.status(403).json({ error: '账号已被封禁', code: 'ACCOUNT_BANNED' });
        }
        // Y5：登录元数据（刷新 last_login + ≥3 天回归 → 邮件/buff/称号），fire-and-forget 不阻塞登录响应
        onLoginMeta(user.id, user.last_login).catch((e: any) => console.error('login meta error:', e?.message || e));
        const token = jwt.sign(
          { id: user.id, username: user.username, type: 'access' },
          JWT_SECRET_USED,
          { expiresIn: ACCESS_TOKEN_EXPIRY }
        );
        // 账号重构：refresh 改为不透明随机串，服务端落 refresh_tokens 表（180 天滑动、可吊销），响应 shape 不变
        const refreshToken = await issueRefreshSession(user.id, req.headers['user-agent']);
        res.json({
          token,
          refreshToken,
          user: { id: user.id, username: user.username },
        });
      } else {
        res.status(401).json({ error: 'Incorrect password', code: 'INVALID_PASSWORD' });
      }
    } catch (error) {
      console.error('Login error:', error);
      res.status(500).json({ error: 'Server error' });
    }
  });
});

// Refresh token（账号重构 2026-09-23 重写，docs/account-refactor-plan.md §2.3②）：
// 1) opaque token 查 refresh_tokens 表：吊销/过期 → 401；封禁 → 403；通过则滑动续期（不轮换 token 本体）
// 2) 表里查不到 → 兼容通道按旧版 refresh JWT 校验，通过则签发新 opaque refresh（旧版缓存客户端一次性升级）
// 无效一律 401（401 才触发客户端静默续期/清键路径），仅封禁回 403。
app.post('/api/auth/refresh', async (req: any, res: any) => {
  const { refreshToken } = req.body || {};
  if (!refreshToken || typeof refreshToken !== 'string') return res.status(400).json({ error: 'Refresh token required' });

  const signAccess = (u: any) =>
    jwt.sign({ id: u.id, username: u.username, type: 'access' }, JWT_SECRET_USED, { expiresIn: ACCESS_TOKEN_EXPIRY });

  try {
    const row: any = await dbGet('SELECT * FROM refresh_tokens WHERE token_hash = ?', [sha256hex(refreshToken)]);
    if (row) {
      if (row.revoked_at || new Date(row.expires_at).getTime() <= Date.now()) {
        return res.status(401).json({ error: 'Invalid or expired refresh token' });
      }
      const user: any = await dbGet('SELECT id, username, banned FROM users WHERE id = ?', [row.user_id]);
      if (!user) return res.status(401).json({ error: 'User not found' });
      if (user.banned) return res.status(403).json({ error: '账号已被封禁', code: 'ACCOUNT_BANNED' });
      await dbRun(
        'UPDATE refresh_tokens SET last_used_at = ?, expires_at = ? WHERE id = ?',
        [nowIso(), new Date(Date.now() + REFRESH_TOKEN_DAYS * 86400000).toISOString(), row.id]
      );
      return res.json({
        token: signAccess(user),
        refreshToken, // 不轮换：原样返回
        user: { id: user.id, username: user.username },
      });
    }

    // 兼容通道：旧版客户端升级（旧 refresh JWT 用一次换一对 opaque 会话）
    jwt.verify(refreshToken, JWT_SECRET_USED, async (err: any, payload: any) => {
      if (err || payload?.type !== 'refresh') return res.status(401).json({ error: 'Invalid or expired refresh token' });
      try {
        const user: any = await dbGet('SELECT id, username, banned FROM users WHERE id = ?', [payload.id]);
        if (!user) return res.status(401).json({ error: 'User not found' });
        if (user.banned) return res.status(403).json({ error: '账号已被封禁', code: 'ACCOUNT_BANNED' });
        const newRefreshToken = await issueRefreshSession(user.id, req.headers['user-agent']);
        return res.json({
          token: signAccess(user),
          refreshToken: newRefreshToken,
          user: { id: user.id, username: user.username },
        });
      } catch (e) {
        console.error('Refresh compat error:', e);
        return res.status(500).json({ error: 'Server error' });
      }
    });
  } catch (e) {
    console.error('Refresh error:', e);
    res.status(500).json({ error: 'Server error' });
  }
});

// access 换会话（v26d 2026-09-24 新增，?token= 外链进场专用）：生产 ?token= 链接为手拼、只带 access
// JWT（无 refreshToken），2h 后必然被登出。本端点凭 authenticateToken 验过的 access 签发全新 opaque
// refresh 会话（issueRefreshSession：180 天滑动、落 refresh_tokens 表 SHA-256 哈希、可吊销），响应
// shape 与 /auth/login、/auth/refresh 完全一致。JWT 无效/过期由 authenticateToken 回 401/403；
// 封禁口径与 login/refresh 相同（403 ACCOUNT_BANNED）。既有吊销路径（logout 按本体吊销、改密全端
// 吊销、GM 踢下线）对本端点签发的会话行原样生效。
app.post('/api/auth/exchange', authenticateToken, async (req: any, res: any) => {
  try {
    const user: any = await dbGet('SELECT id, username, banned FROM users WHERE id = ?', [req.user.id]);
    if (!user) return res.status(401).json({ error: 'User not found' });
    if (user.banned) return res.status(403).json({ error: '账号已被封禁', code: 'ACCOUNT_BANNED' });
    const token = jwt.sign({ id: user.id, username: user.username, type: 'access' }, JWT_SECRET_USED, { expiresIn: ACCESS_TOKEN_EXPIRY });
    const refreshToken = await issueRefreshSession(user.id, req.headers['user-agent']);
    res.json({ token, refreshToken, user: { id: user.id, username: user.username } });
  } catch (e) {
    console.error('Exchange error:', e);
    res.status(500).json({ error: 'Server error' });
  }
});

// 登出（账号重构 2026-09-23 新增，§2.3③）：凭 refresh 本体吊销自己的会话行，无需 access 鉴权
// （access 已过期也能正常登出）。恒 200 幂等：token 不匹配/已吊销也返回成功，不泄露存在性。
app.post('/api/auth/logout', (req: any, res: any) => {
  const { refreshToken } = req.body || {};
  if (!refreshToken || typeof refreshToken !== 'string') return res.json({ message: 'Logged out' });
  db.run(
    'UPDATE refresh_tokens SET revoked_at = ? WHERE token_hash = ?',
    [nowIso(), sha256hex(refreshToken)],
    () => res.json({ message: 'Logged out' })
  );
});

// 自助改密（账号重构 2026-09-23 新增，§2.3④，authenticateToken 保护）：
// 验旧密码 → 更新 bcrypt 哈希 → 吊销该用户全部会话；keepCurrentDevice=true 保留当前设备
// （按 User-Agent 匹配，末位兜底取 last_used_at 最新）最新一行，本机不掉线、其他设备全部下线。
app.post('/api/auth/password', authenticateToken, async (req: any, res: any) => {
  const { oldPassword, newPassword, keepCurrentDevice } = req.body || {};
  if (!oldPassword || !newPassword || typeof newPassword !== 'string') {
    return res.status(400).json({ error: 'oldPassword and newPassword are required' });
  }
  const passwordCheck = validatePassword(newPassword);
  if (!passwordCheck.valid) return res.status(400).json({ error: passwordCheck.error });

  try {
    const user: any = await dbGet('SELECT id, username, password_hash FROM users WHERE id = ?', [req.user.id]);
    if (!user) return res.status(404).json({ error: 'User not found' });
    if (!(await bcrypt.compare(asStr(oldPassword), user.password_hash))) {
      return res.status(401).json({ error: 'Incorrect old password', code: 'INVALID_PASSWORD' });
    }
    const hash = await bcrypt.hash(newPassword, 10);
    await dbRun('UPDATE users SET password_hash = ? WHERE id = ?', [hash, user.id]);

    let keptCurrentDevice = false;
    if (keepCurrentDevice) {
      const device = String(req.headers['user-agent'] || '').slice(0, 80);
      const rows: any[] = await dbAll(
        'SELECT id, device, last_used_at FROM refresh_tokens WHERE user_id = ? AND revoked_at IS NULL',
        [user.id]
      );
      if (rows.length > 0) {
        const ts = (r: any) => (r.last_used_at ? new Date(r.last_used_at).getTime() : 0);
        rows.sort((a, b) => ((b.device === device ? 1 : 0) - (a.device === device ? 1 : 0)) || (ts(b) - ts(a)));
        await revokeRefreshSessions(user.id, rows[0].id);
        keptCurrentDevice = true;
      }
    } else {
      await revokeRefreshSessions(user.id);
    }
    res.json({ message: 'Password updated', ok: true, keptCurrentDevice });
  } catch (e: any) {
    console.error('Password change error:', e);
    res.status(500).json({ error: 'Server error' });
  }
});

// Save Routes
// GET /api/save 拉取存档；?revision=1 时返回 gm_revision 轻量元数据（供前端轮询 GM 变更）
app.get('/api/save', authenticateToken, (req: any, res: any) => {
  const isRevision = String(req.query.revision) === '1';
  db.get('SELECT save_data, gm_revision, updated_at FROM saves WHERE user_id = ?', [req.user.id], (err: any, row: any) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    if (!row) {
      if (isRevision) return res.json({ gm_revision: 0, has_save: false, updated_at: null });
      return res.status(404).json({ error: 'No save found' });
    }

    if (isRevision) {
      const gm_revision = Number(row.gm_revision ?? 0);
      return res.json({ gm_revision, has_save: true, updated_at: row.updated_at ?? null });
    }

    try {
      const saveData = JSON.parse(row.save_data);
      res.set('X-YL-Gm-Revision', String(Number(row.gm_revision) || 0)); // S3 v26c：响应头带修订号（不污染存档 schema）
      res.json(saveData);
    } catch (e) {
      res.status(500).json({ error: 'Error parsing save data' });
    }
  });
});

// ── P0-1 经济钳制（2026-09-19，设计稿降级方案落地）──
// 客户端权威存量架构下，服务端对 POST /api/save 的 spiritStones/exp 正增量做硬钳制：
// cap = 每分钟基线 × 1.5^境界 × 距上次保存分钟数（长时挂机不误伤），另设绝对线兜底。
// 首存/无基线按 1440 分钟宽限。钳制只影响服务端留档与排行/埋点口径，命中记 economy_ledger(kind='clamp')。
// 全量服务端化（客户端只报行为）为二阶段，见 reports/yl-feature-design.md §3 P0-1。
const ECON_CLAMP_SILVER_PER_MIN = 300_000;  // 灵石每分钟基线（高倍率历练的富余量级）
const ECON_CLAMP_EXP_PER_MIN = 10_000_000;  // 修为每分钟基线；v28：须容纳通天塔 100 层扫荡 2,356,523（旧 533,165）。最低存档间隔 0.5min × mult=1 ⇒ 5,000,000，余量 2.12x
const ECON_CLAMP_ABS_MAX = 5_000_000_000;   // 单次保存增量绝对上限（合法玩法不可达；门槛×10 后长生满槽 1.32e9，抬线维持"不可达"语义）
const ECON_CLAMP_REALM_MULT = 1.5;          // 与游戏通胀同基数：每境界 ×1.5
const ECON_CLAMP_FIRST_SAVE_MINS = 1440;    // 首存宽限（老档迁移/清库重传不误伤）

// ── P0-2 经济二阶段：存档落库服务端权威结算（2026-09-25，取代上行 P0-1 单一时间基线成为 /api/save 的结算入口）──
// 三层防线（客户端零改动，正常玩家配额内分毫不差）：
// ① 离线收益重算封顶：耗时取服务端 saves.updated_at（权威时间轴，不信任存档内 lastActiveTime），
//    公式与客户端 Nw 同源：exp=floor(maxExp*0.004*0.02*小时*60)、灵石=floor(floor(50*1.5^境界序)*小时)、封顶 24h、>30s 起算
// ② 逐类计数器配额：Δ打坐/历练/击杀/秘境（statistics 差值）× 每类单次上限（公式自客户端锚点提取），
//    计数器增速另做时间合理性钳制（防改档虚增计数器撑大配额）；出售灵石按背包总量×单价上限单独给额度
// ③ 总额兜底：灵石 125万×1.5^境界/小时+10万（YL_ECON_X5_V26K 起口径；原 25万+2万）、
//    修为沿用 P0-1 每分钟线、绝对线 ECON_CLAMP_ABS_MAX；另物品单组数量 ≤1e6、负值/NaN 归零
// 超限截断写 economy_ledger（kind='clamp' 复用既有埋点，明细带 'E2:' 前缀可区分一/二阶段命中）
const E2_REALM_EXP_FACTOR_STEPS: number[] = [1, 2, 4, 8, 15, 30, 60]; // 打坐修为境界系数表（客户端 RS.handleMeditate 同源）
const E2_ADV_STONE_EACH = 1000; // YL_ECON_X5_V26K 原 200 ×5   // 历练灵石事件区间 10~120（妖兽/奇遇/洞窟）→ 单次上限 200
const E2_KILL_STONE_EACH = 500; // YL_ECON_X5_V26K 原 100 ×5  // 战斗掉落单次上限
const E2_SR_STONE_EACH = 3000; // YL_ECON_X5_V26K 原 600 ×5    // 秘境单次上限
const E2_SELL_UNIT = 250; // YL_ECON_X5_V26K 原 50 ×5         // 出售单价上限（客户端 sellPrice/xm 默认几十）
const E2_SELL_PER_HOUR = 1000000; // YL_ECON_X5_V26K 原 200000 ×5 // 出售额度：20万×境界乘数/小时 + 1万 起步
const E2_STONE_BURST_PER_HOUR = 1250000; // YL_ECON_X5_V26K 原 250000 ×5 // 灵石总额兜底：25万×1.5^境界/小时
const E2_STONE_BURST_BASE = 6_000_000; // YL_REALM_REWARD_SCALE_V26L 原 100_000（v28：须容纳通天塔 100 层扫荡灵石 938,914 + 满额出售 550,000）
const E2_LUMP_STONE_ALLOWANCE = 6_000_000; // YL_REALM_REWARD_SCALE_V26L（v28：通天塔灵石无独立计数器，只能落在此项；旧值炼气档仅 533,333）
const E2_INV_QTY_MAX = 1000000;  // 物品单组数量上限（合法玩法不可达，9e9 类暴改直接截断）
const E2_MIN_SAVE_MINS = 0.5;    // 上传间隔下限（客户端 30s 自动同步节奏）

// ── v27：通天塔 / 灵兽远征 修为放行（2026-09-28）──
// 这两套玩法由客户端直接改 player.exp，且不递增 statistics.*Count，E2 逐类配额完全覆盖不到。
// 客户端权威存档下，服务端按客户端上报的「累计已发放修为」差值给配额（信任级别与 statistics 计数器等同）。
// 计数器位置：player.tower.expGained、player.grotto.expeditionExpGained —— 之所以放子对象，
// 是因为客户端 UI 层 setPlayer 只 Object.assign 部分字段，tower/grotto 是会被完整透传的两个。
const E2_TOWER_EXP_PER_MIN = 20000;    // 通天塔：100 层扫荡 2,356,523/天≈1,636/min，单层首通最高 375,920；给 ~12x 富余（v28 扫荡对齐首通 30% 后刷新）
const E2_EXPED_EXP_PER_MIN = 60000;    // 远征：太虚陨星单次≈65k/4h/队，4 队≈4.3k/min；给 ~14x 富余
const E2_TOWER_EXP_LUMP = 12_000_000;  // 一次性：1..100 层全通累计 7,855,203（给 1.5x 富余）
const E2_EXPED_EXP_LUMP = 2_000_000;   // 一次性：远征存量结算余量

// 离线收益重算（客户端 Nw 同源纯函数）：p=旧档玩家，fromMs=上次落库时间；首存(null)=0（宽限走配额层）
function calcOfflineGainV2(p: any, fromMs: number | null): { exp: number; stones: number } {
  const out = { exp: 0, stones: 0 };
  try {
    if (!p || fromMs == null) return out;
    const sec = (Date.now() - fromMs) / 1000;
    if (!(sec > 30)) return out; // 客户端 f>3e4 才结算离线，同口径
    const hours = Math.min(sec / 3600, 24);
    const idx = Math.max(0, ECON_REALM_ORDER.indexOf(String(p.realm || '')));
    out.exp = Math.floor((Number(p.maxExp) || 100) * 0.004 * 0.02 * hours * 60);
    out.stones = Math.floor(Math.floor((idx <= 0 ? 4 / 3 : 2 * idx + 1) * 125) * hours); // YL_REALM_REWARD_SCALE_V26L
  } catch { /* 自吞异常，绝不影响存档主路径 */ }
  return out;
}

// 计数器差值：只认正增量（回档/多端旧档不倒扣，同 Y15/DG 口径）
function e2Delta(a: number, b: number): number { return b > a ? Math.floor(b) - Math.floor(a) : 0; }

// [r112] R-112 打坐/历练掉玉（服务端环，2026-10-02）：打坐每跳 0.4%、历练每次 0.9%（打坐最低、历练略高），命中 1 玉/次。
// 口径：Δ 差值只在 POST /api/save 的 UPDATE 分支结算（服务端权威）；首存（INSERT 分支）与基线坏 JSON 不 roll；
// Δ 为负（回档/采纳器回调）按 e2Delta 语义 = 0，绝不扣玉；发放走 actDropTokens —— 日上限 300（ACT_TOKEN_DAILY_CAP）、
// activity_token_daily 守卫钳制、活跃 token_shop 场次门槛全部复用既有口径；玉/命中经 stones 当量换算（RATE=50 ⇒ 200 石/玉，floor 恰 1:1）。
// ★ 防刷钳 cMed/cAdv 为 settleSaveEconV2 计数器时间钳的逐字镜像（那边改公式必须同步这边）。
const R112_JADE_MED_CHANCE = 0.004; // 打坐 每跳（约 2s/跳 ⇒ 期望 ≈7.2 玉/时）
const R112_JADE_ADV_CHANCE = 0.009; // 历练 每次（约 4s/次 ⇒ 期望 ≈8.1 玉/时，略高于打坐）
function ylR112RollHits(n: number, chance: number): number {
  const total = Math.floor(Number(n) || 0);
  const c = Number(chance);
  if (!(total > 0) || !(c > 0)) return 0;
  let hits = 0;
  for (let i = 0; i < total; i++) { if (Math.random() < c) hits++; }
  return hits;
}
function ylR112JadeDrop(userId: number, oldSaveJson: unknown, newSd: any, prevUpdatedAt: unknown): void {
  try {
    if (!oldSaveJson) return; // 无上次基线（首存/行缺失）⇒ 不 roll
    let oldSd: any = null;
    try { oldSd = JSON.parse(String(oldSaveJson)); } catch { return; } // 基线坏 JSON ⇒ 不 roll（防历史计数一次性全额入账）
    const os = (oldSd && oldSd.player && oldSd.player.statistics) || {};
    const ns = (newSd && newSd.player && newSd.player.statistics) || {};
    const t = prevUpdatedAt == null ? NaN : Date.parse(String(prevUpdatedAt).replace(' ', 'T') + 'Z');
    const realMins = Number.isFinite(t) ? Math.max(0, (Date.now() - t) / 60000) : NaN;
    const cntCap = (c: number): number => (Number.isFinite(c) && c >= 0 ? c : 0); // 镜像 settleSaveEconV2 KI-001 K3
    let dMed = e2Delta(Number(os.meditateCount) || 0, Number(ns.meditateCount) || 0);
    let dAdv = e2Delta(Number(os.adventureCount) || 0, Number(ns.adventureCount) || 0);
    const cMed = cntCap(Math.ceil(realMins * 300) + 30); // 镜像：自动打坐 200ms/次 → 300 次/分
    const cAdv = cntCap(Math.ceil(realMins * 130) + 30); // 镜像：自动历练 500ms/次 → 120 次/分
    if (dMed > cMed) dMed = cMed;
    if (dAdv > cAdv) dAdv = cAdv;
    const hits = ylR112RollHits(dMed, R112_JADE_MED_CHANCE) + ylR112RollHits(dAdv, R112_JADE_ADV_CHANCE);
    if (hits <= 0) return;
    const stonesEq = hits * Math.ceil(10000 / ACT_TOKEN_RATE_PER_10K); // 1 玉/命中（RATE=50 ⇒ 200 石/玉，floor 换算恰 1:1）
    actDropTokens(userId, stonesEq, Date.now()).catch((e: any) => console.error('r112 act drop tokens error:', e?.message || e));
  } catch (e: any) {
    console.error('r112 jade drop error:', e?.message || e); // 掉玉旁路，绝不影响存档主路径
  }
}

// v28 P0-2b: `mins` is gone from the cap path. Every time-scaled allowance uses REAL
// elapsed minutes (no floor); the per-save CEILING comes from the persisted allowance
// ledger (saves.econ_win_*) instead of `rate * max(0.5, dt)` -- that per-request floor
// was what a 120 req/min spammer multiplied into ~60x.
function settleSaveEconV2(oldSd: any, newSd: any, prevSavedAtMs: number | null, lumpPool?: { tower: number; exped: number }, winState?: { start: number | null; exp: number; stone: number }): string[] {
  const clamped: string[] = [];
  try {
    const np: any = newSd && newSd.player;
    if (!np) return clamped;
    const op: any = (oldSd && oldSd.player) || {};
    const realmIdx = Math.max(0, ECON_REALM_ORDER.indexOf(String(np.realm || '')));
    const mult = Math.pow(ECON_CLAMP_REALM_MULT, Math.min(20, realmIdx));
    const realMins = prevSavedAtMs ? Math.max(0, (Date.now() - prevSavedAtMs) / 60000) : ECON_CLAMP_FIRST_SAVE_MINS;
    // v28 P0-2b: persisted real-time allowance ledger. The ceiling is the REMAINING
    // cumulative allowance since the anchor: allow = rate * mult * elapsed, granted total
    // persisted. Steady state a spammer can only consume rate * elapsed (1.0x), while an
    // idle/offline player keeps the full real-time credit (no 0.5-floor regression).
    const e2NowMs = Date.now();
    const anchorRaw = winState ? winState.start : null;
    const anchor0: number | null = (typeof anchorRaw === 'number' && Number.isFinite(anchorRaw) && anchorRaw > 0)
      ? anchorRaw : null;
    let winExp = winState ? Math.max(0, Math.floor(Number(winState.exp) || 0)) : 0;
    let winStone = winState ? Math.max(0, Math.floor(Number(winState.stone) || 0)) : 0;
    const oldRealmIdx = Math.max(0, ECON_REALM_ORDER.indexOf(String((op && op.realm) || '')));
    const reanchor = anchor0 === null || anchor0 > e2NowMs || oldRealmIdx !== realmIdx;
    const winStart: number = reanchor
      ? (prevSavedAtMs != null ? prevSavedAtMs : e2NowMs - ECON_CLAMP_FIRST_SAVE_MINS * 60000)
      : (anchor0 as number);
    if (reanchor) { winExp = 0; winStone = 0; }
    const elapsedMs = Math.max(0, e2NowMs - winStart);
    const allowExp = Math.floor(ECON_CLAMP_EXP_PER_MIN * mult * (elapsedMs / 60000));
    // v28 P0-2c: ylScale is hoisted here so allowStone is expressed in the SAME scale as
    // winStone / appliedStone. The old shape left allowStone unscaled while capStone
    // multiplied it by ylScale, so the ledger mixed a pre-scale allowance with post-scale
    // consumption -- at low realms (ylScale 4/3) that let stone throughput exceed the rate
    // line (measured up to 2.25x at qi-refining). The value of ylScale is unchanged.
    const ylScale = (realmIdx <= 0 ? 4 / 3 : 2 * realmIdx + 1) / 3; // YL_REALM_REWARD_SCALE_V26L realmScale (realmIdx=1 => 1x, 6 => 13/3)
    const allowStone = Math.floor((Math.floor(E2_STONE_BURST_PER_HOUR * mult * (elapsedMs / 3600000)) + E2_STONE_BURST_BASE) * ylScale);
    const grantExp = Math.max(0, allowExp - winExp);
    const grantStone = Math.max(0, allowStone - winStone);

    // 0) KI-001 归零步骤（三态区分：缺失 / 非法 / 负值）——原实现把三者合并成「写 0」，实测
    //    会把「字段缺失」(Number(undefined)=NaN) 与「合法超大值」(Number.isFinite(Infinity)=false)
    //    一并抹成 0，这正是线上「8W 灵石 → 0」的确切路径（KNOWN_ISSUES.md KI-001）。
    //    新语义：① 缺字段 ⇒ 回写 op 原值（op 也没有 ⇒ 保持缺失，绝不凭空造 0）；
    //            ② 显式负值 ⇒ 0（沿用旧意）；
    //            ③ NaN/非有限/null/非数值类型且 op 有合法旧值 ⇒ 保留旧值（宁可不动，不抹平）。
    //    ★ 唯一权威判据是 `f in np` / `f in op`，不是 Number() 的结果。
    //    ★ `null` 陷阱：`Number(null) === 0`（有限且 >= 0），若只按数值判会**静默变 0** ——
    //      与「字段缺失」同类，必须显式排除（客户端从不发 null，但手工档/GM 可能）。
    for (const f of ['spiritStones', 'exp']) {
      const hasNew = Object.prototype.hasOwnProperty.call(np, f);
      const hasOld = Object.prototype.hasOwnProperty.call(op, f);
      const oldN = hasOld ? Number(op[f]) : NaN;
      const oldOk = hasOld && Number.isFinite(oldN) && oldN >= 0;
      if (!hasNew) {
        // ① 字段缺失：绝不写 0。op 有合法旧值则回写，否则保持缺失（由后续 cap 循环与写入端兜底）
        if (oldOk) { np[f] = oldN; clamped.push('KI001:' + f + ':missing->keep_old'); }
        else { clamped.push('KI001:' + f + ':missing'); }
        continue;
      }
      const rawNew = np[f];
      if (rawNew === null || typeof rawNew === 'boolean' || (typeof rawNew === 'string' && rawNew.trim() === '')) {
        // ③a 非数值类型（null/布尔/空串）：与「缺失」同口径，不解释成 0
        if (oldOk) { np[f] = oldN; clamped.push('KI001:' + f + ':invalid->keep_old'); }
        else { clamped.push('KI001:' + f + ':invalid'); }
        continue;
      }
      const n = Number(rawNew);
      if (Number.isFinite(n) && n >= 0) { np[f] = Math.floor(n); continue; } // 正常路径
      if (Number.isFinite(n) && n < 0) { np[f] = 0; clamped.push('E2:' + f + ':neg'); continue; }
      // ③ NaN / ±Infinity：非法值 ⇒ 优先保留 op 合法旧值
      if (oldOk) { np[f] = oldN; clamped.push('KI001:' + f + ':invalid->keep_old'); }
      else { np[f] = 0; clamped.push('E2:' + f + ':neg'); }
    }

    // 1) 计数器差值 + 增速时间合理性钳制（计数器本身不改写，只按钳后值给配额）
    const os = op.statistics || {}, ns = np.statistics || {};
    let dMed = e2Delta(Number(os.meditateCount) || 0, Number(ns.meditateCount) || 0);
    let dAdv = e2Delta(Number(os.adventureCount) || 0, Number(ns.adventureCount) || 0);
    let dKill = e2Delta(Number(os.killCount) || 0, Number(ns.killCount) || 0);
    let dSR = e2Delta(Number(os.secretRealmCount) || 0, Number(ns.secretRealmCount) || 0);
    const cMed = Math.ceil(realMins * 300) + 30;   // 自动打坐 200ms/次 → 300 次/分
    const cAdv = Math.ceil(realMins * 130) + 30;   // 自动历练 500ms/次 → 120 次/分
    const cSR = Math.ceil(realMins * 4) + 6;       // 秘境门每日 3 次 + 战斗内秘境富余
    const cKill = cAdv * 2 + cSR * 5 + 30;
    // KI-001 K3：配额本身必须有限。realMins 若为 NaN/Infinity（旧档 updated_at 解析异常）
    // 会让 cMed..cKill 全变 NaN ⇒ `dX > cX` 恒 false ⇒ **所有计数器钳制静默失效**，
    // 进而把 capStone/capExp 抬到 Infinity。此处先兜底再比较。
    const cntCap = (c: number): number => (Number.isFinite(c) && c >= 0 ? c : 0);
    const cMedG = cntCap(cMed), cAdvG = cntCap(cAdv), cSRG = cntCap(cSR), cKillG = cntCap(cKill);
    if (dMed > cMedG) { clamped.push('E2:cnt:med' + dMed + '>' + cMedG); dMed = cMedG; }
    if (dAdv > cAdvG) { clamped.push('E2:cnt:adv' + dAdv + '>' + cAdvG); dAdv = cAdvG; }
    if (dSR > cSRG) { clamped.push('E2:cnt:sr' + dSR + '>' + cSRG); dSR = cSRG; }
    if (dKill > cKillG) { clamped.push('E2:cnt:kill' + dKill + '>' + cKillG); dKill = cKillG; }

    // 1b) 通天塔 / 灵兽远征 累计修为计数器差值（v27；与 statistics 计数器同信任级别）
    const ot = op.tower || {}, nt = np.tower || {};
    const og = op.grotto || {}, ng = np.grotto || {};
    const dTowerExp = e2Delta(Number(ot.expGained) || 0, Number(nt.expGained) || 0);
    const dExpedExp = e2Delta(Number(og.expeditionExpGained) || 0, Number(ng.expeditionExpGained) || 0);

    // 2) 离线收益重算（服务端权威时间轴）
    const off = calcOfflineGainV2(op, prevSavedAtMs);

    // 3) 逐类配额（公式自客户端锚点提取，上限均含富余）
    const rl = Math.min(9, Math.max(1, Math.floor(Number(np.realmLevel) || 1)));
    const lvlMaxExp = realmMaxExp(String(np.realm || ''), rl); // 与客户端 ad(realm,lv) 同源（TRIB 表）
    const medBase = Math.floor((E2_REALM_EXP_FACTOR_STEPS[realmIdx] || 1) * 10 * (1 + rl * 0.15));
    const medEach = medBase * 3.7 + medBase * 50 * 0.05;             // 常规 0.85~1.15×1.2 富余 + 顿悟期望 5%×50 倍
    const advEach = Math.max(1, Math.floor(lvlMaxExp * 0.025)) + 20; // 客户端 _ylCapPct=.25 同源上限（收益÷10 同步收紧）
    const killEach = Math.floor(lvlMaxExp * 0.05) + 50;
    const srEach = lvlMaxExp * 0.1 + 200;
    const invQtySum: number = Array.isArray(np.inventory)
      ? np.inventory.reduce((s: number, it: any) => s + (Number(it && it.quantity) || 0), 0) : 0;
    const sellAllow = Math.min(Math.floor(invQtySum * E2_SELL_UNIT),
      Math.floor(E2_SELL_PER_HOUR * mult * (realMins / 60)) + 50000);

    // v28 P0-1: one-time LUMP pools. Server-authoritative lifetime allowance, NOT a per-save
    // bonus: drawn down by what each save actually consumes, never refilled.
    const towerPerMin = Math.floor(E2_TOWER_EXP_PER_MIN * mult * realMins);
    const expedPerMin = Math.floor(E2_EXPED_EXP_PER_MIN * mult * realMins);
    const towerLumpLeft = lumpPool ? Math.max(0, Math.floor(Number(lumpPool.tower) || 0)) : 0;
    const expedLumpLeft = lumpPool ? Math.max(0, Math.floor(Number(lumpPool.exped) || 0)) : 0;
    // v28 P0-2b: the one-time pools are ADDITIVE to the rate-based ceiling, so a legitimate
    // single burst (100-floor tower sweep 2,356,523) is covered by the pool instead of by a
    // per-request 0.5-min floor -- which is exactly what made the old ceiling exploitable.
    const towerOver = Math.max(0, dTowerExp - towerPerMin);
    const expedOver = Math.max(0, dExpedExp - expedPerMin);
    const towerLumpGrant = Math.min(towerOver, towerLumpLeft);
    const expedLumpGrant = Math.min(expedOver, expedLumpLeft);
    const lumpGrantExp = towerLumpGrant + expedLumpGrant;
    const capExp = Math.min(ECON_CLAMP_ABS_MAX,
      grantExp + lumpGrantExp,                                    // P0-1 修为总额兜底（合法峰值无实测收紧数据，本批不收紧）
      Math.floor(off.exp + dMed * medEach + dAdv * advEach + dKill * killEach + dSR * srEach
        + dTowerExp
        + dExpedExp
        + Math.max(100, lvlMaxExp * 0.05)));                     // 尾项=用药/杂项修为兜底（收益÷10 同步收紧）
    // v28 P0-2c: ylScale definition moved up into econ-ledger (above allowStone) so the
    // stone allowance ledger is scale-consistent; the scaled accumulator terms below
    // still reference that hoisted binding. Value unchanged.
    const capStone = Math.min(ECON_CLAMP_ABS_MAX,
      Math.floor(grantStone), // ③ 灵石总额兜底
      Math.floor(off.stones + dMed * ((realmIdx * 2 + 4) * 5) * ylScale + dAdv * E2_ADV_STONE_EACH * ylScale
        + dKill * E2_KILL_STONE_EACH * ylScale + dSR * E2_SR_STONE_EACH * ylScale + sellAllow * ylScale
        + E2_LUMP_STONE_ALLOWANCE * ylScale + 10000));

    // 4) KI-001 超限截断修复（原实现无下界，会把玩家已有余额「往回压」）
    //    旧写法 `np[f] = ov + cap` 有两处病：① `ov` 来自 `Number(op[f]) || 0`，op 缺字段/
    //    非有限时 `ov=0` ⇒ 截断目标变成纯 `cap`，与玩家真实余额无关；
    //    ② 对**负增量**（上游合法降值，如 GM 改档 / 换机旧档 / 客户端回显）也照截，
    //       结果把真实余额截到一个更小的值 —— 「修 bug 反而偷钱」。
    //    新语义：
    //      ① 配额非有限 / 负 ⇒ 直接跳过（宁放过不误伤）；
    //      ② op 无合法基线 ⇒ 不做增量封顶（无法定义「增量」），原样放行；
    //      ③ op 合法 ⇒ 只在**正增量 > cap** 时封顶，目标 = ov + floor(cap)。
    //    ★ 安全性证明（见 --selftest 的随机不变量）：
    //        guard 为 `delta = nvi - ovi > capN >= 0` ⇒ `nvi > ovi + capN = limit`，
    //        故 `limit < nvi` 恒真、`np[f] = limit >= ovi` —— 截断结果**永不低于 ov**，
    //        也**永不为 0**（除 ov==0 且 cap==0 的退化情形）。负增量一律走 `delta <= capN`
    //        分支原样通过。因此本步单独即满足「只削超发、绝不压低玩家已有余额」，
    //        无需任何额外补偿步骤。
    const caps: Array<[string, number]> = [['spiritStones', capStone], ['exp', capExp]];
    for (const [f, cap] of caps) {
      const capN = Number(cap);
      if (!Number.isFinite(capN) || capN < 0) continue;      // 配额本身非有限 ⇒ 不截（宁放过不误伤）
      const nv = Number(np[f]);
      if (!Number.isFinite(nv) || nv < 0) continue;          // 已在 0) 处理
      const hasOld = Object.prototype.hasOwnProperty.call(op, f);
      const oldN = hasOld ? Number(op[f]) : NaN;
      const oldOk = hasOld && Number.isFinite(oldN) && oldN >= 0;
      const nvi = Math.floor(nv);
      if (!oldOk) continue;                                  // 无参照物 ⇒ 不封顶，原样放行
      const ovi = Math.floor(oldN);
      const delta = nvi - ovi;
      if (delta <= capN) continue;
      const limit = ovi + Math.floor(capN);
      if (limit < nvi) {
        np[f] = limit;
        clamped.push('E2:' + f + ':' + delta + '>' + capN
          + '|off' + (f === 'exp' ? off.exp : off.stones)
          + ',m' + dMed + ',a' + dAdv + ',k' + dKill + ',r' + dSR + ',s' + sellAllow
          + ',tw' + dTowerExp + ',ex' + dExpedExp);
      }
    }

    // v28 P0-1c: settle the ledger and the one-time pools by what this save ACTUALLY applied
    // under the final cap (never more than was granted).
    // INVARIANT: the pool draw-down must depend ONLY on server-observed data (`appliedExp` =
    //   the exp actually committed under the final cap) plus server constants. It must NOT
    //   depend on `off.exp` / `dMed` / `dAdv` / `dKill` / `dSR` / the old `expSumNoLump` --
    //   every one of those is forgeable from the submitted save. Inflating `adventureCount`
    //   to its own clamp (cAdv = 31 at dt->0) alone pushed the old `expSumNoLump` to
    //   31 * advEach = 9.9e8 at longevity lv9 => `avail` = 0 => `twApplied` = 0 => the tower
    //   pool was NEVER drawn => the full 7,855,203 burst was re-granted on EVERY save, forever.
    //   Fix: draw each pool by `min(grant, appliedExp)`. Since the pool shrinks by exactly the
    //   amount drawn, `sum(pool-funded exp) <= pool size` holds by construction, for ANY
    //   submitted payload.
    {
      const appliedExp = Math.max(0, Math.floor(Number(np.exp) || 0) - Math.floor(Number(op.exp) || 0));
      const appliedStone = Math.max(0, Math.floor(Number(np.spiritStones) || 0) - Math.floor(Number(op.spiritStones) || 0));
      // The pool may only be charged for exp ABOVE the rate line (towerPerMin + expedPerMin is
      // already covered by the ledger/accumulator). `min(capExp, appliedExp)` is server-computed
      // (capExp) or server-observed (appliedExp = committed np.exp - stored op.exp).
      const appliedOverRate = Math.max(0, Math.min(capExp, appliedExp) - towerPerMin - expedPerMin);
      const lumpApplied = Math.min(lumpGrantExp, appliedOverRate);
      if (lumpPool) {
        const towerDraw = lumpGrantExp > 0
          ? Math.floor(lumpApplied * towerLumpGrant / lumpGrantExp) : 0;
        const expedDraw = lumpApplied - towerDraw;
        lumpPool.tower = Math.floor(Math.max(0, towerLumpLeft - towerDraw));
        lumpPool.exped = Math.floor(Math.max(0, expedLumpLeft - expedDraw));
      }
      if (winState) {
        winState.start = winStart;
        winState.exp = Math.min(allowExp, winExp + appliedExp);
        winState.stone = Math.min(allowStone, winStone + appliedStone);
      }
    }

    // 0.8.7 T7 G7 硬化：sectContribution 差值钳（堵「客户端权威可刷」，写法抄上方计数器窗口钳）。
    // 数值定档《数值表-T7T8》T7-9：dContrib ≤ ceil(realMins×20/分)+5000——
    // 兜底 5000=原生职衔晋升单笔恰好放行（bundle 常量实测），增速 1200/时=任务阁稳态贡献（6k/日÷5h）。
    // 超限钳回并记 clamped，计数器本体（负值）一并归零防负刷。
    {
      const oContrib = Math.floor(Number(op.sectContribution) || 0);
      const nContribRaw = Math.floor(Number(np.sectContribution) || 0);
      const nContrib = Math.max(0, nContribRaw);
      if (!Number.isFinite(nContribRaw) || nContribRaw < 0) {
        // KI-001 K4：与病根①同口径——「缺失/非法」保留旧值（有合法旧值时不抹平），仅显式负值归零
        const keepOld = nContribRaw < 0 && nContribRaw !== 0 ? false : Number.isFinite(oContrib) && oContrib >= 0;
        if (keepOld && Object.prototype.hasOwnProperty.call(np, 'sectContribution') === false) np.sectContribution = oContrib;
        else np.sectContribution = 0;
        clamped.push('E2:sectContrib:neg');
      }
      else {
        const dContrib = e2Delta(oContrib, nContrib);
        const cContrib = Math.ceil(realMins * SECT_CONTRIB_CLAMP_PER_MIN) + SECT_CONTRIB_CLAMP_BASE;
        if (dContrib > cContrib) {
          np.sectContribution = oContrib + cContrib;
          clamped.push('E2:sectContrib' + dContrib + '>' + cContrib);
        }
      }
    }

    // 5) 物品数量轻钳制（NaN/负→1，单组上限 1e6；不做总量钳制防误伤囤草党）
    if (Array.isArray(np.inventory)) {
      np.inventory.forEach((it: any, i: number) => {
        if (!it || typeof it !== 'object') return;
        const q = Math.floor(Number(it.quantity));
        if (!Number.isFinite(q) || q < 0) { it.quantity = 1; clamped.push('E2:inv' + i + ':fix'); }
        else if (q > E2_INV_QTY_MAX) { it.quantity = E2_INV_QTY_MAX; clamped.push('E2:inv' + i + ':' + q + '>max'); }
      });
    }
  } catch { /* 结算挂掉绝不影响存档主路径（与 P0-1 同纪律） */ }
  return clamped;
}

// v28 P0-1: read the one-time pool balance from the authoritative saves columns. A missing or
// NULL value (pre-migration row / older DB) means "full allowance", i.e. never granted yet.
function lumpPoolFromRow(row: any): { tower: number; exped: number } {
  const pick = (v: any, full: number): number => {
    if (v === null || v === undefined) return full;
    const n = Number(v);
    return Number.isFinite(n) ? Math.max(0, Math.floor(n)) : full;
  };
  return {
    tower: pick(row && row.tower_lump_left, E2_TOWER_EXP_LUMP),
    exped: pick(row && row.exped_lump_left, E2_EXPED_EXP_LUMP),
  };
}

// v28 P0-2b: read the persisted allowance ledger. econ_win_start NULL = window not opened
// yet (legacy row / new account) -> settleSaveEconV2 anchors it at the real previous save time.
function winStateFromRow(row: any): { start: number | null; exp: number; stone: number } {
  const num = (v: any): number => {
    const n = Number(v);
    return Number.isFinite(n) ? Math.max(0, Math.floor(n)) : 0;
  };
  const s = row ? Number(row.econ_win_start) : NaN;
  return {
    start: Number.isFinite(s) && s > 0 ? s : null,
    exp: num(row && row.econ_win_exp),
    stone: num(row && row.econ_win_stone),
  };
}

// v28 P0-3: POST /api/save body shape guard, derived from the client's real payload (see the
// header of srv_patch_p0_save.py). `player` is the only structural requirement; requiring more
// (logs/timestamp/realmLevel/maxExp) would reject legitimate legacy saves.
function isValidSavePayload(sd: any): boolean {
  if (!sd || typeof sd !== 'object' || Array.isArray(sd)) return false;
  const p = sd.player;
  if (!p || typeof p !== 'object' || Array.isArray(p)) return false;
  if (typeof p.name !== 'string' || typeof p.realm !== 'string') return false;
  sanitizeInhSaveField(p); // T7_LEGACY: 传承石周 key 只读 shape 归一（§3.1/§3.3）—— 保证 inhStoneWeek 原样往返，且脏值安全丢弃
  return true;
}

// T7_LEGACY (0.8.8 T7 传承 · §3.1+§3.3) —— 传承石「每周限购」软约束字段的只读归一。
// 设计口径（T7-传承系统.md §3.4.5）：限购走 save_data 软约束，**服务端零业务改动**；
// 本函数只负责「让合法值原样往返 + 让脏值安全消失」，**不做**任何限购权威判定（那是 P1）。
//   · 合法 'YYYY-MM-DD'（含真实日期校验）→ 原样保留（string）
//   · '' / 缺省 → 保留（客户端约定「可为空字符串」）
//   · 其它任何形态 → 静默删除该字段（**绝不**写 NaN / 哨兵值）
// ★ 全程零 Number() 转换：本字段是 string，引入数值化即重新引入 KI-001 的 NaN 病灶。
function sanitizeInhSaveField(p: any): void {
  if (!p || typeof p !== 'object' || Array.isArray(p)) return;
  if (!Object.prototype.hasOwnProperty.call(p, 'inhStoneWeek')) return; // 缺省：不动
  const v = p.inhStoneWeek;
  if (typeof v !== 'string') { delete p.inhStoneWeek; return; }        // 非 string（如 12345）→ 丢弃
  if (v === '') return;                                                 // 空串：客户端约定合法
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) { delete p.inhStoneWeek; return; } // 形状不符 → 丢弃
  const t = Date.parse(v + 'T00:00:00Z');
  if (!Number.isFinite(t) || new Date(t).toISOString().slice(0, 10) !== v) {
    delete p.inhStoneWeek; return;                                      // 非法日期（如 2026-13-45）→ 丢弃
  }
  // 合法：原样保留，不做任何转换
}

// S4 v26c 保险快照（可选独立件）：对写档前旧档做节流快照（每用户 ≥10min 一条、每号最多留 50 条），
// 用于误覆盖/防倒滚误伤救援；fire-and-forget + 全程自吞异常，绝不影响保存主路径
function snapshotOldSave(userId: number, oldSaveData: string, gmRevision: number, force: boolean = false) { // [v2810] force=true \u8df3\u8fc7 10min \u8282\u6d41\uff08\u56de\u6863\u524d\u5f3a\u5236\u843d\u4e00\u6761\uff09
  try {
    db.get('SELECT created_at FROM save_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT 1', [userId], (err: any, row: any) => {
      if (err) return;
      if (row && row.created_at) {
        const t = Date.parse(String(row.created_at).replace(' ', 'T') + 'Z');
        if (!force && Number.isFinite(t) && Date.now() - t < 10 * 60 * 1000) return; // 节流：距上一条 <10min 不再快照
      }
      db.run('INSERT INTO save_snapshots (user_id, save_data, gm_revision) VALUES (?, ?, ?)', [userId, oldSaveData, gmRevision], (ierr: any) => {
        if (ierr) return;
        db.run('DELETE FROM save_snapshots WHERE user_id = ? AND id NOT IN (SELECT id FROM save_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT 50)', [userId, userId]);
      });
    });
  } catch { /* 快照挂掉绝不影响存档路径 */ }
}

// ── 单写者会话锁（session-lock）：同一账号仅一个活跃写入会话，支持跨端顶号 ──
// claim 认领会话 / heartbeat 每 ≤60s 续期 / save 带 X-YL-Session 校验归属。
// 兼容：不带 X-YL-Session 的 /api/save 一律放行（老客户端、GM 脚本、/yl/apps/* 等调用方）。
const SESSION_STALE_MS = 60000; // 心跳静默超过 60s 视为会话已失效

app.post('/api/session/claim', authenticateToken, async (req: any, res: any) => {
  try {
    const device = typeof req.body?.device === 'string' ? req.body.device : null;
    const now = Date.now();
    const row: any = await dbGet('SELECT session_id, last_seen FROM active_sessions WHERE user_id = ?', [req.user.id]);
    const superseded = !!(row && Number(row.last_seen) > now - SESSION_STALE_MS);
    const sessionId = crypto.randomUUID();
    await dbRun(
      'INSERT OR REPLACE INTO active_sessions (user_id, session_id, device, claimed_at, last_seen) VALUES (?, ?, ?, ?, ?)',
      [req.user.id, sessionId, device, now, now]
    );
    res.json({ ok: true, sessionId, superseded });
  } catch (e: any) {
    console.error('session claim error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

app.post('/api/session/heartbeat', authenticateToken, async (req: any, res: any) => {
  try {
    const sid = req.headers['x-yl-session'];
    const row: any = await dbGet('SELECT session_id FROM active_sessions WHERE user_id = ?', [req.user.id]);
    if (!row || !sid || row.session_id !== sid) {
      return res.status(409).json({ error: 'session_superseded' });
    }
    await dbRun('UPDATE active_sessions SET last_seen = ? WHERE user_id = ?', [Date.now(), req.user.id]);
    res.json({ ok: true });
  } catch (e: any) {
    console.error('session heartbeat error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

app.get('/api/session/state', authenticateToken, async (req: any, res: any) => {
  try {
    const row: any = await dbGet('SELECT session_id, last_seen FROM active_sessions WHERE user_id = ?', [req.user.id]);
    const active = !!(row && Number(row.last_seen) > Date.now() - SESSION_STALE_MS);
    res.json({ sessionId: row ? row.session_id : null, active });
  } catch (e: any) {
    console.error('session state error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

app.post('/api/save', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 120, keyFn: (req: any) => 'save:' + (req.user?.id ?? req.ip) }), async (req: any, res: any) => {
  // 单写者会话锁：带 X-YL-Session 时校验归属；头缺失放行（兼容老客户端/GM/其它调用方）
  const reqSessionId = req.headers['x-yl-session'];
  if (reqSessionId) {
    try {
      const srow: any = await dbGet('SELECT session_id FROM active_sessions WHERE user_id = ?', [req.user.id]);
      if (srow && srow.session_id !== reqSessionId) {
        return res.status(409).json({ error: 'session_superseded' });
      }
    } catch (e: any) {
      console.error('save session check error:', e?.message || e); // 会话锁查询异常不阻塞存档路径
    }
  }
  const saveData = req.body;

  if (!saveData) {
    return res.status(400).json({ error: 'Save data is required' });
  }
  // v28 P0-3: reject malformed payloads (e.g. {"logs":[]}, {"player":null}, {"player":[]})
  // BEFORE any DB write. Previously such a body was stored verbatim and bricked the account.
  if (!isValidSavePayload(saveData)) {
    return res.status(400).json({ error: 'invalid_save' });
  }

  const saveDataString = JSON.stringify(saveData);
  const saveStreak = recordEconSaveUpload(req.user.id); // SEC 规则③：上传频率滚动窗（进程内存；仅玩家上传计入，失败请求也计=尝试口径）

  // 读改写全程持锁，防止与 GM patch（updatePlayerSave）并发互相覆盖（P1-2）
  withSaveLock(req.user.id, (): Promise<void> => new Promise((resolve) => {
    // Y2：读旧存档做差值基线（服务端结算埋点）。行不存在→全零起算；JSON 坏→null 跳过本次计数（防历史计数一次性全额入账）
    db.get('SELECT save_data, gm_revision, updated_at, tower_lump_left, exped_lump_left, econ_win_start, econ_win_exp, econ_win_stone FROM saves WHERE user_id = ?', [req.user.id], (err, row: any) => {
      if (err) {
        res.status(500).json({ error: 'Database error' });
        return resolve();
      }
      let prevCounters: StatCounters;
      let prevEcon: EconSnapshot | null = null; // E1：旧档经济快照（首存=null→空基线）
      let econSkip = false; // E1：旧档 JSON 坏 → 静默跳过镜像（绝不因记账挂存档路径）
      if (!row) {
        prevCounters = zeroCounters();
      } else {
        try {
          const oldSd = JSON.parse(row.save_data);
          prevCounters = extractCounters(oldSd);
          prevEcon = extractEconSnapshot(oldSd);
        } catch { prevCounters = null as any; econSkip = true; }
      }

      // S1 v26c 防倒滚比对（fail-closed）：带档上传必须声明其基于的修订号（请求头 x-yl-base-revision）。
      // row 存在且（头缺失/非数值或 base 落后当前）→ 409 返回云端现档，不写不记账；
      // 旧客户端（v26b/v25p）与过期会话保存一律被拒，杜绝换机旧档静默覆盖云端新档。
      // row 不存在（新号首存）→ 放行 INSERT，兼容 C6 首存路径
      const baseRev = parseInt(String(req.headers['x-yl-base-revision'] ?? ''), 10);
      const curRev = Number(row && row.gm_revision) || 0;
      if (row && (!Number.isFinite(baseRev) || baseRev < curRev)) {
        let curSave: any = null;
        try { curSave = JSON.parse(row.save_data); } catch { curSave = null; }
        // NET2_STALE: 409 多带一个服务端权威 balance，供客户端重试前自纠（不改 409 语义、不放宽防倒滚）。
        let staleBal: number | null = null;
        try {
          const cp = curSave && curSave.player;
          if (cp && typeof cp.spiritStones === 'number' && isFinite(cp.spiritStones)) {
            staleBal = Math.max(0, Math.floor(cp.spiritStones));
          }
        } catch (e) { staleBal = null; }
        res.status(409).json({ error: 'stale_save', gm_revision: curRev, updated_at: row.updated_at ?? null, save: curSave, balance: staleBal !== null ? staleBal : undefined });
        return resolve();
      }
      // S4 保险快照：写前对旧档节流快照（fire-and-forget，见 snapshotOldSave）
      if (row) snapshotOldSave(req.user.id, row.save_data, curRev);

      // P0-2：二阶段服务端权威结算（离线重算封顶+计数器逐类配额+总额兜底）。YL_V26L：死代码 clampSaveEcon 已删除
      // v28 P0-1/P0-2b: pool balance + allowance ledger for this save (missing -> defaults).
      const lumpPool = row ? lumpPoolFromRow(row) : { tower: E2_TOWER_EXP_LUMP, exped: E2_EXPED_EXP_LUMP };
      const winState = row ? winStateFromRow(row) : { start: null, exp: 0, stone: 0 };
      let clampedFields: string[] = settleSaveEconV2(row && !econSkip ? (() => { try { return JSON.parse(row.save_data); } catch { return null; } })() : null, saveData, row && row.updated_at ? (() => { const t = Date.parse(String(row.updated_at).replace(' ', 'T') + 'Z'); return Number.isFinite(t) ? t : null; })() : null, lumpPool, winState);
      const saveDataStringClamped = clampedFields.length ? JSON.stringify(saveData) : saveDataString;
      if (row) {
        db.run(
          'UPDATE saves SET save_data = ?, gm_revision = ?, tower_lump_left = ?, exped_lump_left = ?, econ_win_start = ?, econ_win_exp = ?, econ_win_stone = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', // S2 v26c：玩家写递增修订号
          [saveDataStringClamped, curRev + 1, lumpPool.tower, lumpPool.exped, winState.start, winState.exp, winState.stone, req.user.id],
          async (updateErr) => {
            if (updateErr) {
              res.status(500).json({ error: 'Error updating save' });
              return resolve();
            }
            const rankingSynced = await upsertRanking(req.user.id, req.user.username, saveData);
            maybeGrantAutoTitles(req.user.id, achievementsLen(saveData)); // Y6 惰性授予（幂等，内部自吞异常）
            if (prevCounters) tickDailyQuests(req.user.id, computeQuestDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('daily tick error:', (e as any)?.message || e)); // Y2 埋点：语句级原子，无需等待
            if (prevCounters) tickSectTasks(req.user.id, computeQuestDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('sect tick error:', (e as any)?.message || e)); // V27 宗门集体任务：同源差值汇入全宗进度（无宗门首查早退），fire-and-forget
            if (prevCounters) { const __sc = extractCounters(saveData); const __sd = computeStatsDeltas(prevCounters, __sc); __sd.minutes = statsMinutesCarried(req.user.id, prevCounters.playTimeMs, __sc.playTimeMs); tickStatsDaily(req.user.id, __sd).catch((e: any) => console.error('stats tick error:', (e as any)?.message || e)); } // Y15 埋点：同源差值（[r069min] minutes 走余量携带）
            if (prevCounters) tickMentorTax(req.user.id, computeStatsDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('mentor tax error:', (e as any)?.message || e)); // Y6B 师徒抽成：师傅得在门徒弟收益 5%，fire-and-forget
            if (prevCounters) tickDungeonTracker(req.user.id, computeDungeonDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('dungeon tick error:', (e as any)?.message || e)); // DG 埋点：秘境观测差值，fire-and-forget
            if (prevCounters) tickWudaoIdle(req.user.id, ylWudaoIdleDelta(prevCounters, saveData)).catch((e: any) => console.error('wudao idle error:', (e as any)?.message || e)); // WUDAO 埋点：打坐时长差值→随机系心得，fire-and-forget
            if (prevCounters) ylR112JadeDrop(req.user.id, row.save_data, saveData, row.updated_at); // [r112] R-112 打坐/历练掉玉：Δmeditate/Δadventure 服务端 roll → actDropTokens（行存在=有上次基线；prevCounters=null=基线坏不 roll；首存走 INSERT 分支无此行=结构性不 roll；Δ负按 e2Delta=0 不扣玉）
            if (!econSkip) writeEconomyMirror(req.user.id, prevEcon ?? EMPTY_ECON_SNAPSHOT, extractEconSnapshot(saveData), saveStreak); // E1 镜像记账（旁路 fire-and-forget，不 await 不影响响应）；SEC 规则③传上传频次
            if (clampedFields.length) { dbRun("INSERT INTO economy_ledger (player_id, kind, anomaly_json) VALUES (?, 'clamp', ?)", [req.user.id, clampedFields.join('|').slice(0, 500)]).catch((e: any) => console.error('clamp ledger error:', e?.message || e)); }
            res.json({ message: 'Save updated successfully', rankingSynced, clamped: clampedFields, settledExp: Math.floor(Number(saveData && saveData.player && saveData.player.exp) || 0), gm_revision: curRev + 1 }); // S2 v26c：回传新修订号供客户端回填 base
            resolve();
          }
        );
      } else {
        db.run(
          'INSERT INTO saves (user_id, save_data, gm_revision, tower_lump_left, exped_lump_left, econ_win_start, econ_win_exp, econ_win_stone) VALUES (?, ?, 1, ?, ?, ?, ?, ?)', // S2 v26c：首存修订号=1（兼容 C6 首存，无头放行）
          [req.user.id, saveDataStringClamped, lumpPool.tower, lumpPool.exped, winState.start, winState.exp, winState.stone], // QA-Y fix(BUG#1)：参数反序已修；此处用钳后串：原 [saveDataString, req.user.id] 参数反序——新玩家首存 user_id 写成整包 JSON、save_data 写成数字，GET /save 404、邮件 claim/buff/称号落空，且每次上传再插一行垃圾（UNIQUE 不命中）
          async (insertErr) => {
            if (insertErr) {
              res.status(500).json({ error: 'Error creating save' });
              return resolve();
            }
            const rankingSynced = await upsertRanking(req.user.id, req.user.username, saveData);
            maybeGrantAutoTitles(req.user.id, achievementsLen(saveData)); // Y6 惰性授予（幂等，内部自吞异常）
            tickDailyQuests(req.user.id, computeQuestDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('daily tick error:', (e as any)?.message || e)); // Y2 埋点（prev=全零）
            if (prevCounters) tickSectTasks(req.user.id, computeQuestDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('sect tick error:', (e as any)?.message || e)); // V27 宗门集体任务（首存=全零基线），fire-and-forget
            if (prevCounters) { const __sc = extractCounters(saveData); const __sd = computeStatsDeltas(prevCounters, __sc); __sd.minutes = statsMinutesCarried(req.user.id, prevCounters.playTimeMs, __sc.playTimeMs); tickStatsDaily(req.user.id, __sd).catch((e: any) => console.error('stats tick error:', (e as any)?.message || e)); } // Y15 埋点（首存=全零基线；[r069min] minutes 走余量携带）
            if (prevCounters) tickMentorTax(req.user.id, computeStatsDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('mentor tax error:', (e as any)?.message || e)); // Y6B 师徒抽成（首存=全零基线，无差值不抽），fire-and-forget
            if (prevCounters) tickDungeonTracker(req.user.id, computeDungeonDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('dungeon tick error:', (e as any)?.message || e)); // DG 埋点（首存=全零基线，老号历史秘境量不回填）
            if (prevCounters) tickWudaoIdle(req.user.id, ylWudaoIdleDelta(prevCounters, saveData)).catch((e: any) => console.error('wudao idle error:', (e as any)?.message || e)); // WUDAO 埋点（首存=全零基线；在线时长近似口径与"打坐"任务同源）
            logChronicle(req.user.id, String(saveData?.player?.name || req.user.username || '').slice(0, 32), '【入世】踏入仙途，自此修行问道，江湖又添一笔'); // Y16 江湖志（仅首存触发，每号一次）
            if (!econSkip) writeEconomyMirror(req.user.id, prevEcon ?? EMPTY_ECON_SNAPSHOT, extractEconSnapshot(saveData), saveStreak); // E1 镜像记账（首存=空基线，差值记 NULL）；SEC 规则③传上传频次
            res.json({ message: 'Save created successfully', rankingSynced, clamped: clampedFields, settledExp: Math.floor(Number(saveData && saveData.player && saveData.player.exp) || 0), gm_revision: 1 }); // S2 v26c：首存回传修订号=1
            resolve();
          }
        );
      }
    });
  }));
});

// 健康检查端点（用于Docker健康检查）
app.get('/api/health', (req, res) => {
  res.status(200).json({ status: 'ok', message: 'Backend is running' });
});

// ─────────────────────────────────────────────────────────
// GM 后台 API（前缀 /api/gm）
// ─────────────────────────────────────────────────────────

// GM 登录
app.post('/api/gm/login', (req: any, res: any) => {
  const { password } = req.body || {};
  if (!password || password !== GM_PASSWORD) {
    return res.status(401).json({ error: '密码错误' });
  }
  const token = crypto.randomBytes(32).toString('hex');
  db.run('INSERT INTO gm_sessions (token, expires_at) VALUES (?, ?)', [token, new Date(Date.now() + 7 * 86400e3).toISOString()], (err: any) => { // [v2810] GM \u4f1a\u8bdd 7 \u5929\u8fc7\u671f
    if (err) return res.status(500).json({ error: 'Login failed' });
    logGmAction('login');
    res.json({ token });
  });
});

// GM 登出
app.post('/api/gm/logout', authenticateGM, (req: any, res: any) => {
  const authHeader = req.headers['authorization'] || '';
  const token = authHeader.split(' ')[1];
  db.run('DELETE FROM gm_sessions WHERE token = ?', [token]);
  res.json({ message: 'Logged out' });
});

// 运营统计看板
app.get('/api/gm/dashboard', authenticateGM, (req: any, res: any) => {
  const queries = [
    'SELECT COUNT(*) AS c FROM users',
    'SELECT COUNT(*) AS c FROM saves',
    'SELECT COUNT(*) AS c FROM chat_messages',
    'SELECT COUNT(*) AS c FROM (SELECT DISTINCT username FROM chat_messages WHERE created_at > datetime("now","-1 day"))',
    'SELECT COUNT(*) AS c FROM lottery_history',
  ];
  Promise.all(queries.map((q) => new Promise<any>((resolve) => db.get(q, (e: any, r: any) => resolve(r)))))
    .then((rows) => {
      const topPower = new Promise<any[]>((resolve) =>
        db.all(
          'SELECT username, combat_power FROM rankings ORDER BY combat_power DESC LIMIT 10',
          (e: any, r: any[]) => resolve(r || [])
        )
      );
      const realmDist = new Promise<any[]>((resolve) =>
        db.all(
          `SELECT CASE realm_index
             WHEN 0 THEN '炼气期' WHEN 1 THEN '筑基期' WHEN 2 THEN '金丹期'
             WHEN 3 THEN '元婴期' WHEN 4 THEN '化神期' WHEN 5 THEN '合道期' ELSE '长生境' END AS realm,
           COUNT(*) AS c FROM rankings GROUP BY realm_index ORDER BY realm_index`,
          (e: any, r: any[]) => resolve(r || [])
        )
      );
      Promise.all([topPower, realmDist]).then(([top, dist]) => {
        res.json({
          totalUsers: rows[0].c,
          totalSaves: rows[1].c,
          totalChat: rows[2].c,
          activeToday: rows[3].c,
          totalLottery: rows[4].c,
          topPower: top,
          realmDistribution: dist,
        });
      });
    });
});

// 玩家列表（搜索 + 分页）
app.get('/api/gm/players', authenticateGM, (req: any, res: any) => {
  const keyword = (req.query.q as string) || '';
  const bannedFilter = req.query.banned as string; // '1' | '0' | undefined
  const page = Math.max(1, parseInt(req.query.page as string) || 1);
  const pageSize = Math.min(50, parseInt(req.query.pageSize as string) || 20);
  const offset = (page - 1) * pageSize;
  const like = `%${keyword}%`;
  const wheres: string[] = [];
  const countParams: any[] = [];
  const listParams: any[] = [];
  if (keyword) { wheres.push('u.username LIKE ?'); countParams.push(like); listParams.push(like); }
  if (bannedFilter === '1') { wheres.push('u.banned = 1'); }
  if (bannedFilter === '0') { wheres.push('(u.banned IS NULL OR u.banned = 0)'); }
  const where = wheres.length ? 'WHERE ' + wheres.join(' AND ') : '';
  const countSql = `SELECT COUNT(*) AS c FROM users u ${where}`;
  const listSql = `
    SELECT u.id, u.username, u.created_at, u.banned,
           s.gm_revision, s.save_data,
           (SELECT realm_index FROM rankings r WHERE r.user_id = u.id) AS realm_index,
           (SELECT realm_level FROM rankings r WHERE r.user_id = u.id) AS realm_level,
           (SELECT combat_power FROM rankings r WHERE r.user_id = u.id) AS combat_power,
           (SELECT spirit_stones FROM rankings r WHERE r.user_id = u.id) AS spirit_stones,
           (SELECT updated_at FROM saves sv WHERE sv.user_id = u.id) AS last_active
    FROM users u
    LEFT JOIN saves s ON s.user_id = u.id
    ${where}
    ORDER BY u.id DESC
    LIMIT ? OFFSET ?`;
  const params = [...listParams, pageSize, offset];
  db.get(countSql, countParams, (err: any, countRow: any) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    db.all(listSql, params, (err2: any, rows: any[]) => {
      if (err2) return res.status(500).json({ error: 'Database error' });
      const REALM_NAMES = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];
      const players = (rows || []).map((r) => {
        let charName = '';
        let sectName = '';
        try {
          const sd = r.save_data ? JSON.parse(r.save_data) : null;
          charName = sd?.player?.name || '';
          sectName = sd?.player?.sectId ? `sect#${sd.player.sectId}` : '';
        } catch {}
        return {
          id: r.id,
          username: r.username,
          charName,
          sectName,
          createdAt: r.created_at,
          banned: !!r.banned,
          realm: r.realm_index != null ? REALM_NAMES[r.realm_index] : '未开始',
          realmIndex: r.realm_index,
          realmLevel: r.realm_level || 0,
          combatPower: r.combat_power || 0,
          spiritStones: r.spirit_stones || 0,
          gmRevision: r.gm_revision || 0,
          lastActive: r.last_active,
        };
      });
      res.json({
        total: countRow.c,
        page,
        pageSize,
        players,
      });
    });
  });
});

// 读取玩家完整存档
app.get('/api/gm/players/:id/save', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  db.get('SELECT save_data FROM saves WHERE user_id = ?', [userId], (err: any, row: any) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    if (!row) return res.status(404).json({ error: 'No save found' });
    try {
      res.json(JSON.parse(row.save_data));
    } catch (e) {
      res.status(500).json({ error: 'Parse error' });
    }
  });
});

// \u2500\u2500 \u73a9\u5bb6\u4fa7\u5b58\u6863\u5feb\u7167 \u00b7 \u65f6\u5149\u56de\u6eaf\uff080.8.10 [snapself]\uff09\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
// \u628a `save_snapshots`\uff08\u5199\u6863\u65f6\u81ea\u52a8\u843d\u3001\u6bcf\u53f7\u6700\u591a 50 \u6761\uff09\u5f00\u653e\u7ed9\u73a9\u5bb6**\u81ea\u52a9\u56de\u6eaf**\uff0c\u7528\u4e8e\u8bef\u64cd\u4f5c\u6551\u63f4\u3002
// \u5feb\u7167**\u5168\u90e8\u7531\u670d\u52a1\u7aef\u81ea\u52a8\u4ea7\u751f**\uff0c\u73a9\u5bb6\u4e0d\u80fd\u624b\u5de5\u9020\u5feb\u7167\u3002
//
// \u989d\u5ea6\uff1a\u6bcf\u5468 SNAP_SELF_WEEKLY \u6b21\uff08\u5317\u4eac\u5468\u4e00\u53e3\u5f84\uff09\uff0c\u8ba1\u6570\u952e activity_config
//       `snap_self_used:<\u5468\u4e00>:<uid>`\u3002**\u5fc5\u987b\u9650\u989d**\uff1a\u672c\u4f5c\u7edd\u5927\u591a\u6570\u73a9\u6cd5\uff08\u62bd\u5956 / \u7075\u7530 / \u4e39\u7089 /
//       \u8bd5\u70bc / \u5947\u9047\uff09\u5728\u5ba2\u6237\u7aef\u7ed3\u7b97\u3001\u53ea\u628a\u7ed3\u679c\u5199\u8fdb\u5b58\u6863 \u21d2\u300c\u56de\u6eaf\u300d= \u65e0\u6210\u672c\u64a4\u9500\u4e00\u6b21\u7ed3\u679c\u3002
//
// \u5b89\u5168\uff1a\u2460 \u5f52\u5c5e\u6821\u9a8c\u6253\u5728 id + user_id\uff08\u9632\u8de8\u53f7\u8d8a\u6743\uff09\uff1b
//       \u2461 \u56de\u6eaf\u524d force \u843d\u4e00\u6761\u5f53\u524d\u6863\u5feb\u7167 \u21d2 \u56de\u6eaf\u53ef\u9006\uff08\u4e0e GM \u4fa7 \u2462-b \u540c\u6b3e\uff09\uff1b
//       \u2462 \u5199\u56de\u8d70 updatePlayerSave\uff08saveLock + gm_revision++ + \u6392\u884c\u540c\u6b65 + \u7ecf\u6d4e\u955c\u50cf\uff09\uff1b
//       \u2463 \u5217\u8868\u53ea\u56de\u6807\u91cf\u6458\u8981\uff0c\u6574\u6863 JSON \u4e0d\u51fa\u7f51\u3002
const SNAP_SELF_WEEKLY = 1;
const SNAP_SELF_MARK = 'snap_self_used:';
const SNAP_SELF_LIST_MAX = 20;

// \u672c\u5468\u989d\u5ea6\uff08week = \u5317\u4eac\u5468\u4e00\uff0c\u4e0e\u5468\u699c / \u5468\u91cc\u7a0b\u7891\u540c\u6e90\uff09
async function snapSelfQuota(userId: number) {
  const week = bjWeekStart(Date.now());
  const key = SNAP_SELF_MARK + week + ':' + userId;
  const row: any = await dbGet('SELECT value FROM activity_config WHERE key = ?', [key]).catch(() => null);
  const used = Math.max(0, Number(row && row.value) || 0);
  return { week, key, used, left: Math.max(0, SNAP_SELF_WEEKLY - used) };
}
// \u539f\u5b50\u5360\u989d\uff1a\u4ec5\u5f53\u300c\u5df2\u7528 < \u989d\u5ea6\u300d\u65f6 +1\uff1bchanges === 1 \u624d\u662f\u5360\u989d\u6210\u529f\uff08\u5e76\u53d1\u4e0d\u8d85\u53d1\uff09
async function snapSelfReserve(key: string): Promise<boolean> {
  await dbRun("INSERT OR IGNORE INTO activity_config (key, value) VALUES (?, '0')", [key]).catch(() => null);
  const r: any = await dbRun(
    'UPDATE activity_config SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key = ? AND CAST(value AS INTEGER) < ?',
    [key, SNAP_SELF_WEEKLY]
  ).catch(() => null);
  return !!(r && Number(r.changes) === 1);
}
// \u9000\u8fd8\u5360\u989d\uff08\u56de\u6eaf\u5931\u8d25\u65f6\u8c03\u7528\uff0c\u4e0d\u767d\u6263\u73a9\u5bb6\u6b21\u6570\uff09
async function snapSelfRelease(key: string) {
  await dbRun('UPDATE activity_config SET value = CAST(MAX(0, CAST(value AS INTEGER) - 1) AS TEXT) WHERE key = ?', [key]).catch(() => null);
}

// GET /api/snapshots \u2014 \u672c\u4eba\u5feb\u7167\u5217\u8868\uff08\u5143\u6570\u636e + \u6807\u91cf\u6458\u8981\uff0c**\u7edd\u4e0d\u56de\u5b58\u6863\u6b63\u6587**\uff09+ \u672c\u5468\u989d\u5ea6\u3002
//   \u6458\u8981\u7531\u670d\u52a1\u7aef\u89e3\u6790\u540e\u53ea\u56de 4 \u4e2a\u6807\u91cf\uff08\u5883\u754c / \u5c42\u6570 / \u7075\u77f3 / \u6218\u529b\uff09\uff0c\u4f9b\u73a9\u5bb6\u5224\u65ad\u8be5\u56de\u54ea\u4e00\u7248\u3002
app.get('/api/snapshots', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `snap:ls:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const q = await snapSelfQuota(userId);
    const rows: any[] = await dbAll(
      'SELECT id, gm_revision, created_at, LENGTH(save_data) AS save_bytes, save_data FROM save_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT ?',
      [userId, SNAP_SELF_LIST_MAX]
    ).catch(() => []);
    const nowMs = Date.now();
    const snapshots = (rows || []).map((r: any) => {
      let summary: any = null;
      try {
        const k = extractRankingData(JSON.parse(String(r.save_data)));
        if (k) summary = {
          realm: REALM_ORDER_FOR_RANKING[k.realm_index] || '',
          realmLevel: k.realm_level,
          stones: k.spirit_stones,
          combatPower: k.combat_power,
        };
      } catch (e) { /* \u5355\u6761\u89e3\u6790\u5931\u8d25\u4e0d\u5f71\u54cd\u6574\u8868 */ }
      const t = Date.parse(String(r.created_at || '').replace(' ', 'T') + 'Z');
      return {
        id: Number(r.id),
        created_at: r.created_at ?? null,
        gm_revision: Number(r.gm_revision) || 0,
        save_bytes: Number(r.save_bytes) || 0,
        age_ms: Number.isFinite(t) ? Math.max(0, nowMs - t) : null,
        summary,
      };
    });
    res.json({
      ok: true,
      week: q.week,
      quota: { weekly: SNAP_SELF_WEEKLY, used: q.used, left: q.left },
      count: snapshots.length,
      snapshots,
    });
  } catch (e: any) {
    console.error('snapshots list error:', e?.message || e);
    res.status(500).json({ error: '\u670d\u52a1\u5668\u7e41\u5fd9' });
  }
});

// POST /api/snapshots/:id/restore \u2014 \u81ea\u52a9\u56de\u6eaf\uff08\u6bcf\u5468\u9650\u989d\uff1b\u56de\u6eaf\u524d\u5f3a\u5236\u843d\u4e00\u6761\uff0c\u4fdd\u8bc1\u53ef\u9006\uff09\u3002
app.post('/api/snapshots/:id/restore', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => `snap:rs:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  const sid = asInt(req.params.id);
  if (!Number.isFinite(sid) || sid <= 0) return res.status(400).json({ error: '\u5feb\u7167\u7f16\u53f7\u975e\u6cd5' });
  let reservedKey = '';
  try {
    // \u5f52\u5c5e\u6821\u9a8c\u6253\u5728 id + user_id \u4e0a\uff08\u5feb\u7167 id \u5168\u8868\u81ea\u589e\uff0c\u53ea\u6309 id \u67e5\u4f1a\u8de8\u53f7\u8d8a\u6743\uff09
    const snap: any = await dbGet('SELECT id, save_data, gm_revision FROM save_snapshots WHERE id = ? AND user_id = ?', [sid, userId]).catch(() => null);
    if (!snap) return res.status(404).json({ error: '\u5feb\u7167\u4e0d\u5b58\u5728\u6216\u4e0d\u5c5e\u4e8e\u4f60' });
    let restored: any;
    try { restored = JSON.parse(String(snap.save_data)); } catch (e) { return res.status(500).json({ error: '\u5feb\u7167\u89e3\u6790\u5931\u8d25' }); }
    if (!restored || typeof restored !== 'object' || Array.isArray(restored)) return res.status(400).json({ error: '\u5feb\u7167\u5185\u5bb9\u975e\u6cd5' });

    // \u5148\u5360\u989d\uff08\u539f\u5b50\u6761\u4ef6\u81ea\u589e\uff09\uff1b\u5360\u4e0d\u5230\u5373\u62d2\u7edd
    const q = await snapSelfQuota(userId);
    const ok = await snapSelfReserve(q.key);
    if (!ok) {
      return res.status(409).json({ error: '\u672c\u5468\u56de\u6eaf\u6b21\u6570\u5df2\u7528\u5c3d\uff0c\u4e0b\u5468\u5237\u65b0\u540e\u518d\u8bd5', code: 'SNAP_QUOTA_EXHAUSTED', weekly: SNAP_SELF_WEEKLY, used: q.used });
    }
    reservedKey = q.key;   // \u5360\u989d\u6210\u529f\uff1b\u4ee5\u4e0b\u4efb\u4f55\u5931\u8d25\u8def\u5f84\u90fd\u9000\u8fd8

    const cur: any = await dbGet('SELECT save_data, gm_revision FROM saves WHERE user_id = ?', [userId]).catch(() => null);
    if (!cur) return res.status(404).json({ error: '\u5c1a\u65e0\u5b58\u6863\uff0c\u65e0\u6cd5\u56de\u6eaf' });
    // \u56de\u6eaf\u524d\u628a\u300c\u5f53\u524d\u6863\u300d\u518d\u843d\u4e00\u6761\uff08force \u7ed5\u8fc7 10min \u8282\u6d41\uff09\u21d2 \u56de\u6eaf\u672c\u8eab\u53ef\u9006
    snapshotOldSave(userId, String(cur.save_data), Number(cur.gm_revision) || 0, true);

    const r = await updatePlayerSave(userId, (saveData: any) => {
      Object.keys(saveData).forEach((k) => { delete saveData[k]; });
      Object.assign(saveData, restored);
    });
    if (!r.ok) return res.status(400).json({ error: r.error || '\u56de\u6eaf\u5931\u8d25' });
    reservedKey = '';      // \u5199\u56de\u6210\u529f \u21d2 \u989d\u5ea6\u5df2\u771f\u6b63\u6d88\u8d39\uff0c\u4e0d\u518d\u9000\u8fd8

    const after: any = await dbGet('SELECT gm_revision FROM saves WHERE user_id = ?', [userId]).catch(() => null);
    const gm_revision = Number(after && after.gm_revision) || 0;
    const nowQ = await snapSelfQuota(userId);
    logChronicle(userId, String(req.user?.username || ''), '\u3010\u9006\u5929\u6539\u547d\u3011\u56de\u6eaf\u81ea\u8eab\u56e0\u679c\uff0c\u65f6\u5149\u5012\u8f6c\uff0c\u91cd\u56de\u65e7\u65e5\u4ed9\u9014');
    logGmAction('player_restore_snapshot', `user:${userId}`, { snapshot_id: sid, snapshot_gm_revision: Number(snap.gm_revision) || 0, gm_revision, week: q.week });
    res.json({ ok: true, restored_snapshot_id: sid, gm_revision, quota: { weekly: SNAP_SELF_WEEKLY, used: nowQ.used, left: nowQ.left } });
  } catch (e: any) {
    console.error('snapshot restore error:', e?.message || e);
    res.status(500).json({ error: '\u670d\u52a1\u5668\u7e41\u5fd9' });
  } finally {
    if (reservedKey) await snapSelfRelease(reservedKey).catch(() => null);   // \u5931\u8d25\u8def\u5f84\u9000\u8fd8\u989d\u5ea6
  }
});
// BASECLEAN089 ③-a：GM 快照**元数据**列表（救援快照读侧）。
// 只回 id / created_at / gm_revision / save_data **字节数** —— 绝不回全文（整档 JSON 可达数百 KB，
// 列表若带正文会一次吐几十 MB）。要看某一版全文：拿 id 走下方 restore 的对照，或另取 GM 存档端点。
app.get('/api/gm/players/:id/snapshots', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  if (!Number.isFinite(userId)) return res.status(400).json({ error: 'Bad player id' });
  const limit = Math.min(Math.max(asInt(req.query.limit) || 50, 1), 200);
  db.all(
    'SELECT id, gm_revision, created_at, LENGTH(save_data) AS save_bytes FROM save_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT ?',
    [userId, limit],
    (err: any, rows: any[]) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      const list = (rows || []).map((r: any) => ({
        id: Number(r.id),
        created_at: r.created_at ?? null,
        gm_revision: Number(r.gm_revision) || 0,
        save_bytes: Number(r.save_bytes) || 0,
      }));
      res.json({ ok: true, user_id: userId, count: list.length, snapshots: list });
    }
  );
});

// BASECLEAN089 ③-b：GM 回档到指定快照（救援快照写回）。
// 语义顺序（每步都不可省）：归属校验 → 回档前自动存档 → updatePlayerSave 写回 → 审计 → 回传新修订号。
app.post('/api/gm/players/:id/snapshots/:sid/restore', authenticateGM, async (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  const sid = parseInt(req.params.sid);
  if (!Number.isFinite(userId) || !Number.isFinite(sid)) {
    return res.status(400).json({ error: 'Bad player id or snapshot id' });
  }
  // 归属校验打在**主键 + user_id** 上：快照 id 全表自增，只按 id 查会拿到别人号的快照（跨号越权）。
  const snap: any = await dbGet(
    'SELECT id, save_data, gm_revision FROM save_snapshots WHERE id = ? AND user_id = ?',
    [sid, userId]
  ).catch(() => null);
  if (!snap) return res.status(404).json({ error: 'Snapshot not found for this player' });

  let restored: any;
  try {
    restored = JSON.parse(snap.save_data);
  } catch (e) {
    return res.status(500).json({ error: 'Snapshot parse error' });
  }

  // 回档前把「当前档」再存一条（否则回档不可逆；snapshotOldSave 自带 <10min 节流 + 每号留 50 条）
  const cur: any = await dbGet('SELECT save_data, gm_revision FROM saves WHERE user_id = ?', [userId]).catch(() => null);
  if (cur) snapshotOldSave(userId, String(cur.save_data), Number(cur.gm_revision) || 0, true); // [v2810] \u56de\u6863\u524d\u5f3a\u5236\u5feb\u7167\uff08\u7ed5\u8fc7 10min \u8282\u6d41\uff0c\u4fdd\u8bc1\u53ef\u9006\uff09

  const r = await updatePlayerSave(userId, (saveData: any) => {
    if (!restored || typeof restored !== 'object' || Array.isArray(restored)) return;
    Object.keys(saveData).forEach((k) => { delete saveData[k]; });
    Object.assign(saveData, restored);
  });
  if (!r.ok) return res.status(400).json({ error: r.error });

  const after: any = await dbGet('SELECT gm_revision FROM saves WHERE user_id = ?', [userId]).catch(() => null);
  const gm_revision = Number(after && after.gm_revision) || 0;
  logGmAction('restore_snapshot', `user:${userId}`, { snapshot_id: sid, snapshot_gm_revision: Number(snap.gm_revision) || 0, gm_revision });
  res.json({ ok: true, restored_snapshot_id: sid, gm_revision });
});

// 修改玩家存档（通用 patch；不再白名单限制）
// Body 形态：
//   { set:    { 'player.spiritStones': 1000, 'player.playerName': '...', top: v } }  ← 路径赋值（覆盖式）
//   { merge:  { player: { grotto: {...} } } }                                            ← 对象合并
//   { push:   { 'player.inventory': {...} } }                                            ← 数组追加
//   { remove: { 'player.inventory': 'item-id-xxx' } }                                    ← 数组按值删除
//   { set: 0 } + { reset: true }                                                          ← 初始化整个存档（保留账号名）
//   { replace: { ... } }                                                                  ← 用整段 patch 替换 player 对象
app.put('/api/gm/players/:id/save', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  const body = req.body || {};
  const op = (key: string) => (Array.isArray(body[key]) ? body[key] : []);

  updatePlayerSave(userId, (saveData: any) => {
    if (!saveData.player || typeof saveData.player !== 'object') {
      saveData.player = {};
    }
    // 1) reset: 整存档初始化（保留 username + createdAt）
    if (body.reset === true) {
      const username = saveData.player?.name || '';
      const p: any = {
        name: username,
        spiritStones: 0,
        exp: 0,
        realmIndex: 0,
        realmLevel: 0,
        combatPower: 0,
        reputation: 0,
        killCount: 0,
        playTime: 0,
        lotteryTickets: 0,
        inventory: [],
        pets: [],
        grotto: {},
        achievements: [],
        // 兼容旧字段
        realm: '炼气期',
      };
      saveData.player = p;
    }
    // 2) replace: 整个 player 用对象替换（深合并）
    if (body.replace && typeof body.replace === 'object') {
      saveData.player = { ...saveData.player, ...stripUnsafeKeys(body.replace) };
    }
    // 3) merge: 浅合并 player 字段
    if (body.merge && typeof body.merge === 'object') {
      if (body.merge.player && typeof body.merge.player === 'object') {
        saveData.player = { ...saveData.player, ...stripUnsafeKeys(body.merge.player) };
      } else {
        saveData.player = { ...saveData.player, ...stripUnsafeKeys(body.merge) };
      }
    }
    // 4) set: 路径赋值（'a.b.c' = v）
    for (const p of op('set')) {
      const [path, value] = Object.entries(p)[0] || [];
      if (!path) continue;
      setPath(saveData, path, value);
    }
    // 5) push: 路径为数组则 push
    for (const p of op('push')) {
      const [path, value] = Object.entries(p)[0] || [];
      if (!path) continue;
      const arr = getPath(saveData, path);
      if (Array.isArray(arr)) arr.push(value);
      else setPath(saveData, path, [value]);
    }
    // 6) remove: 数组按值删
    for (const p of op('remove')) {
      const [path, value] = Object.entries(p)[0] || [];
      if (!path) continue;
      const arr = getPath(saveData, path);
      if (Array.isArray(arr)) {
        const i = arr.findIndex((x: any) => x === value || x?.id === value || x?.name === value);
        if (i >= 0) arr.splice(i, 1);
      }
    }
  }).then((r) => {
    if (!r.ok) return res.status(400).json({ error: r.error });
    logGmAction('edit_save', `user:${userId}`, body);
    res.json({ message: 'Save updated', ok: true });
  });
});

// 简单路径工具（P2-3：过滤 __proto__/constructor/prototype，防 GM patch set/push/remove 路径原型污染）
const UNSAFE_PATH_KEYS = new Set(['__proto__', 'constructor', 'prototype']);
// 浅剥离危险键（P2-3）：spread 复制自身可枚举属性不会触发 __proto__ setter（无污染），
// 但会把字面 "__proto__" 键带进存档 JSON，统一剥掉
function stripUnsafeKeys(o: any): any {
  if (!o || typeof o !== 'object') return o;
  for (const k of Object.keys(o)) {
    if (UNSAFE_PATH_KEYS.has(k)) delete o[k];
  }
  return o;
}
function getPath(obj: any, path: string): any {
  return path.split('.').reduce((o, k) => (o == null || UNSAFE_PATH_KEYS.has(k) ? undefined : o[k]), obj);
}
function setPath(obj: any, path: string, value: any): void {
  const keys = path.split('.').filter((k) => !UNSAFE_PATH_KEYS.has(k));
  if (keys.length === 0) return;
  const last = keys.pop()!;
  const o = keys.reduce((a, k) => (a[k] == null ? (a[k] = {}) : a[k]), obj);
  o[last] = value;
}

// GM 物品字典：返回可发放的参考物品（抽奖池 + 玩家背包去重 + 抽奖历史 + bundle 字典）
app.get('/api/gm/items', authenticateGM, (req: any, res: any) => {
  const ITEM_TYPES = ['材料', '草药', '丹药', '武器', '护甲', '法宝', '首饰', '戒指', '进阶物品', '装备合成石'];
  const dict: Record<string, { name: string; type: string; rarity: string; description?: string; effect?: any }> = {};
  // 1) 完整抽奖池物品（从玩家前端 lottery 配置归纳，覆盖游戏核心物品）
  const LOTTERY_POOL: [string, string, string][] = [
    // 货币/修为
    ['灵石', '材料', '普通'], ['10灵石', '材料', '普通'], ['50灵石', '材料', '普通'],
    ['100灵石', '材料', '稀有'], ['500灵石', '材料', '稀有'], ['1000灵石', '材料', '传说'],
    ['修为', '材料', '普通'], ['50修为', '材料', '普通'], ['200修为', '材料', '普通'],
    ['500修为', '材料', '稀有'], ['2000修为', '材料', '传说'],
    // 材料
    ['炼器石', '材料', '普通'], ['炼器石x10', '材料', '普通'], ['强化石', '材料', '稀有'],
    ['强化石x10', '材料', '传说'], ['灵石碎片', '材料', '普通'], ['精铁', '材料', '普通'],
    ['秘银', '材料', '稀有'], ['龙鳞', '材料', '传说'], ['木锭', '材料', '普通'],
    // 草药
    ['聚灵草', '草药', '普通'], ['聚灵草x20', '草药', '普通'], ['紫猴花', '草药', '稀有'],
    ['雪莲花', '草药', '稀有'], ['千年人参', '草药', '传说'], ['凤凰羽', '草药', '传说'],
    ['止血草', '草药', '普通'],
    // 丹药
    ['聚气丹', '丹药', '普通'], ['聚气丹x3', '丹药', '普通'], ['回春丹', '丹药', '普通'],
    ['洗髓丹', '丹药', '稀有'], ['筑基丹', '丹药', '稀有'], ['结金丹', '丹药', '传说'],
    ['凝魂丹', '丹药', '传说'], ['龙血丹', '丹药', '传说'], ['凤凰涅槃丹', '丹药', '传说'],
    ['九转金丹', '丹药', '仙品'], ['保命丹', '丹药', '稀有'],
    // 武器
    ['凡铁剑', '武器', '普通'], ['玄铁剑', '武器', '稀有'], ['青锋剑', '武器', '传说'],
    ['至高永恒耙', '武器', '仙品'],
    // 护甲
    ['粗布道袍', '护甲', '普通'], ['玄铁护甲', '护甲', '稀有'], ['三足金乌外衣', '护甲', '传说'],
    // 法宝
    ['耐用珠', '法宝', '普通'], ['珊瑚珠', '法宝', '稀有'], ['乾坤珠', '法宝', '传说'],
    // 首饰
    ['耐用生铁发带', '首饰', '普通'], ['嗜血琉璃吊坠', '首饰', '稀有'], ['玄水精魄', '进阶物品', '普通'],
    ['月华露珠', '进阶物品', '普通'], ['轮回髓', '进阶物品', '稀有'], ['麒麟角', '进阶物品', '稀有'],
    // 灵宠
    ['灵狐', '进阶物品', '普通'], ['雷虎', '进阶物品', '稀有'], ['凤凰', '进阶物品', '仙品'],
    // 抽奖券
    ['1张抽奖券', '材料', '普通'], ['3张抽奖券', '材料', '稀有'], ['5张抽奖券', '材料', '传说'],
  ];
  for (const [name, type, rarity] of LOTTERY_POOL) {
    if (!dict[name]) dict[name] = { name, type, rarity };
  }
  // 2) 玩家背包去重（补充玩家实际持有的物品）
  db.all('SELECT save_data FROM saves', (err: any, rows: any[]) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    for (const row of rows || []) {
      try {
        const p = JSON.parse(row.save_data)?.player;
        const inv: any[] = Array.isArray(p?.inventory) ? p.inventory : [];
        for (const it of inv) {
          if (!it || !it.name) continue;
          if (!dict[it.name]) dict[it.name] = { name: it.name, type: it.type || '材料', rarity: it.rarity || '普通' };
        }
      } catch (e) { /* skip bad save */ }
    }
    // 3) 抽奖历史（玩家抽到过的物品）
    db.all('SELECT DISTINCT prize_name, prize_type, prize_rarity FROM lottery_history', (err2: any, rows2: any[]) => {
      if (!err2 && rows2) {
        for (const it of rows2) {
          if (!it.prize_name) continue;
          if (!dict[it.prize_name]) dict[it.prize_name] = { name: it.prize_name, type: it.prize_type || '材料', rarity: it.prize_rarity || '普通' };
        }
      }
      // 4) 从 game-dicts.json 合并 bundle 物品 (ta + Jb + N + shop items)
      const gd = loadGameDicts();
      for (const it of (gd.items || [])) {
        if (!it || !it.name) continue;
        if (!dict[it.name]) {
          dict[it.name] = {
            name: it.name,
            type: it.type || '材料',
            rarity: it.rarity || '普通',
            subType: it.subType,
            slot: it.slot,
            realm: it.realm,
            baseName: it.baseName,
            description: it.description,
            effect: it.effect,
          };
        }
      }
      const list = Object.values(dict).sort((a, b) => a.name.localeCompare(b.name, 'zh'));
      res.json({ items: list, itemTypes: ITEM_TYPES });
    });
  });
});

// 给玩家发放物品/资源
app.post('/api/gm/players/:id/grant', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  const { spiritStones, tickets, exp, item } = req.body || {};
  updatePlayerSave(userId, (saveData: any) => {
    const p = saveData.player;
    if (typeof spiritStones === 'number') p.spiritStones = (p.spiritStones || 0) + spiritStones;
    if (typeof tickets === 'number') p.lotteryTickets = (p.lotteryTickets || 0) + tickets;
    if (typeof exp === 'number') p.exp = (p.exp || 0) + exp;
    if (item && item.name) {
      p.inventory = p.inventory || [];
      // 完整下发物品结构，让玩家背包能正常显示描述/属性/可装备
      const equippableTypes = ['武器','护甲','戒指','首饰','法宝','发簪','耳坠','项链','手镯','护符','披风','帽','胸甲','护腕','腰带','鞋'];
      const isEquip = (item.equipmentSlot || item.slot)
        ? equippableTypes.includes(item.equipmentSlot || item.slot)
        : (item.effect && Object.keys(item.effect).length > 0);
      p.inventory.push({
        id: `gm-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
        name: item.name,
        type: item.type || '材料',
        description: item.description || '',
        quantity: item.quantity || 1,
        rarity: item.rarity || '普通',
        subType: item.subType || '',
        slot: item.slot || item.equipmentSlot || '',
        equipmentSlot: item.equipmentSlot || item.slot || '',
        realm: item.realm || '',
        baseName: item.baseName || '',
        effect: item.effect || null,
        isEquippable: item.isEquippable !== undefined ? item.isEquippable : isEquip,
        level: typeof item.level === 'number' ? item.level : 0,
      });
    }
  }).then((r) => {
    if (!r.ok) return res.status(400).json({ error: r.error });
    logGmAction('grant', `user:${userId}`, req.body);
    // NET2_STALE: 回传服务端权威余额。客户端据此立刻回填 spiritStones 与 base revision，
    //   消灭「服务端已入账、客户端仍持旧值」的未知期 —— 这正是 G2 抹档的窗口。
    //   此处 balance 由回显中间件（N1，白名单已含 gm）统一附加；若中间件因故未命中，
    //   下面的显式回查是第二道保险（只读一次，失败不影响发放结果）。
    dbGet('SELECT save_data, gm_revision FROM saves WHERE user_id = ?', [userId]).then((row: any) => {
      let bal: number | null = null;
      let rev: number | null = null;
      try {
        const sd = JSON.parse((row && row.save_data) || '{}');
        const p = sd && sd.player;
        if (p && typeof p.spiritStones === 'number' && isFinite(p.spiritStones)) {
          bal = Math.max(0, Math.floor(p.spiritStones));
        }
        if (row && row.gm_revision !== undefined) rev = Number(row.gm_revision);
      } catch (e) { /* 保持 null，降级为原响应 */ }
      const body: any = { message: 'Granted' };
      if (bal !== null) body.balance = bal;
      if (rev !== null) body.gm_revision = rev;
      res.json(body);
    }).catch(() => res.json({ message: 'Granted' }));
  });
});

// 封禁 / 解封账号（通过标记 GM 字段实现：在 users 表加 banned 列）
db.serialize(() => {
  db.all("PRAGMA table_info(users)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'banned')) {
      safeAddColumn('users', 'banned', 'ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0');
    }
  });
});
// [v2810] 0.8.10 \u8fc1\u79fb\uff1ausers.muted_until\uff08\u7981\u8a00\uff09+ gm_sessions.expires_at\uff08GM \u4f1a\u8bdd\u8fc7\u671f\uff09\u3002
//   \u2605 \u5e42\u7b49\u52a0\u5217\uff1asafeAddColumn \u541e duplicate column name\uff1b\u4e0d\u8bfb PRAGMA\uff08serialize \u65e0\u5b8c\u6210\u5c4f\u969c\uff0c\u5751 12\uff09\u3002
db.serialize(() => {
  safeAddColumn('users', 'muted_until', 'ALTER TABLE users ADD COLUMN muted_until DATETIME');
  safeAddColumn('gm_sessions', 'expires_at', "ALTER TABLE gm_sessions ADD COLUMN expires_at DATETIME");
});
app.post('/api/gm/players/:id/ban', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  const banned = req.body?.banned ? 1 : 0;
  const reason = asStr(req.body?.reason).slice(0, 200);
  db.run('UPDATE users SET banned = ? WHERE id = ?', [banned, userId], (err: any) => {
    if (err) return res.status(500).json({ error: 'Update failed' });
    logGmAction(banned ? 'ban' : 'unban', `user:${userId}`, { reason });
    res.json({ message: banned ? 'Banned' : 'Unbanned', banned: !!banned, userId });
  });
});
// [v2810] POST /api/gm/players/:id/mute \u2014 \u7981\u8a00 / \u89e3\u9664\u7981\u8a00\uff08users.muted_until\uff09\u3002
//   body { minutes?: number, until?: string }\uff1a\u4e8c\u8005\u53d6\u4e00\uff1bminutes<=0 \u6216 until \u4e3a\u7a7a/\u5df2\u8fc7\u53bb
//   \u21d2 \u89e3\u9664\u7981\u8a00\u3002\u53ea\u62e6\u300c\u53d1\u8a00\u300d\uff08POST /api/messages\uff09\uff0c\u4e0d\u62e6\u767b\u5f55 / \u5b58\u6863 / \u9886\u53d6\uff08\u90a3\u662f\u5c01\u7981\u7684\u8bed\u4e49\uff09\u3002
app.post('/api/gm/players/:id/mute', authenticateGM, async (req: any, res: any) => {
  const userId = asInt(req.params.id);
  if (!Number.isInteger(userId) || userId <= 0) return res.status(400).json({ error: '\u7528\u6237 id \u975e\u6cd5' });
  const minutes = Math.floor(asNum(req.body?.minutes) || 0);
  const untilRaw = asStr(req.body?.until).trim();
  let untilIso: string | null = null;
  if (untilRaw) {
    const t = Date.parse(untilRaw);
    if (Number.isFinite(t) && t > Date.now()) untilIso = new Date(t).toISOString();
  } else if (Number.isFinite(minutes) && minutes > 0) {
    untilIso = new Date(Date.now() + minutes * 60000).toISOString();
  }
  try {
    const up = await dbRun('UPDATE users SET muted_until = ? WHERE id = ?', [untilIso, userId]);
    if (!up.changes) return res.status(404).json({ error: '\u7528\u6237\u4e0d\u5b58\u5728' });
    logGmAction(untilIso ? 'mute' : 'unmute', `user:${userId}`, { until: untilIso, minutes });
    res.json({ ok: true, userId, mutedUntil: untilIso });
  } catch (e: any) {
    console.error('gm mute error:', e?.message || e);
    res.status(500).json({ error: '\u64cd\u4f5c\u5931\u8d25' });
  }
});

// [v2810] GET /api/me/mute \u2014 \u53ea\u8bfb\uff1a\u5f53\u524d\u73a9\u5bb6\u7981\u8a00\u72b6\u6001\uff08\u5ba2\u6237\u7aef\u5c55\u793a\uff1b\u5b57\u6bb5\u540d mutedUntil \u7a33\u5b9a\uff09\u3002
app.get('/api/me/mute', authenticateToken, async (req: any, res: any) => {
  try {
    const row: any = await dbGet('SELECT muted_until FROM users WHERE id = ?', [req.user.id]);
    const raw = row && row.muted_until ? String(row.muted_until) : '';
    const t = raw ? Date.parse(raw) : NaN;
    const active = Number.isFinite(t) && t > Date.now();
    res.json({ muted: active, mutedUntil: active ? new Date(t).toISOString() : null });
  } catch (e: any) {
    console.error('me mute error:', e?.message || e);
    res.status(500).json({ error: '\u670d\u52a1\u5668\u7e41\u5fd9' });
  }
});

// 删除账号 + 存档
app.delete('/api/gm/players/:id', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  db.serialize(() => {
    db.run('DELETE FROM saves WHERE user_id = ?', [userId]);
    db.run('DELETE FROM rankings WHERE user_id = ?', [userId]);
    db.run('DELETE FROM lottery_history WHERE user_id = ?', [userId]);
    db.run('DELETE FROM users WHERE id = ?', [userId], (err: any) => {
      if (err) return res.status(500).json({ error: 'Delete failed' });
      logGmAction('delete_user', `user:${userId}`);
      res.json({ message: 'User deleted' });
    });
  });
});

// 批量操作：按条件筛选后批量发物品/灵石/封禁
app.post('/api/gm/players/batch', authenticateGM, (req: any, res: any) => {
  const { filter, action } = req.body || {};
  // filter: { realm?, minCombatPower?, keyword? }
  // action: { spiritStones?, tickets?, ban? }
  const conditions: string[] = [];
  const params: any[] = [];
  if (filter?.realm != null) {
    conditions.push('realm_index = ?');
    params.push(filter.realm);
  }
  if (filter?.minCombatPower != null) {
    conditions.push('combat_power >= ?');
    params.push(filter.minCombatPower);
  }
  if (filter?.keyword) {
    conditions.push('u.username LIKE ?');
    params.push(`%${filter.keyword}%`);
  }
  const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
  const sql = `SELECT r.user_id FROM rankings r JOIN users u ON u.id = r.user_id ${where}`;
  db.all(sql, params, async (err: any, rows: any[]) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    let count = 0;
    for (const row of rows || []) {
      const ok = await updatePlayerSave(row.user_id, (saveData: any) => {
        const p = saveData.player;
        if (action?.spiritStones) p.spiritStones = (p.spiritStones || 0) + action.spiritStones;
        if (action?.tickets) p.lotteryTickets = (p.lotteryTickets || 0) + action.tickets;
        if (action?.exp) p.exp = (p.exp || 0) + action.exp;
        // 批量发放物品（合并到同名物品）
        if (action?.item && action.item.name) {
          p.inventory = Array.isArray(p.inventory) ? p.inventory : [];
          const qty = Number(action.item.quantity) || 1;
          const existing = p.inventory.find((it: any) => it && it.name === action.item.name);
          if (existing) {
            existing.quantity = (Number(existing.quantity) || 0) + qty;
          } else {
            p.inventory.push({
              id: `gm-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
              name: action.item.name,
              type: action.item.type || '材料',
              description: action.item.description || '',
              quantity: qty,
              rarity: action.item.rarity || '普通',
              ...(action.item.extra || {}),
            });
          }
        }
      });
      if (ok.ok) count++;
    }
    if (action?.ban != null) {
      // P2-2：where 可能含 u.username LIKE ?，子查询必须同样 JOIN users u，否则 no such column: u.username
      db.run(`UPDATE users SET banned = ? WHERE id IN (SELECT r.user_id FROM rankings r JOIN users u ON u.id = r.user_id ${where})`, [action.ban ? 1 : 0, ...params]);
    }
    logGmAction('batch', JSON.stringify(filter), { affected: count, action });
    res.json({ message: 'Batch done', affected: count });
  });
});

// ── 玩家管理扩展端点（GM Pro 用）──

// 清空玩家背包
app.post('/api/gm/players/:id/inventory/clear', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  updatePlayerSave(userId, (saveData: any) => {
    if (saveData.player) saveData.player.inventory = [];
  }).then((r) => {
    if (!r.ok) return res.status(400).json({ error: r.error });
    logGmAction('inventory_clear', `user:${userId}`);
    res.json({ message: 'Inventory cleared', ok: true });
  });
});

// 按 id/name 删除一条背包条目
app.post('/api/gm/players/:id/inventory/remove', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  const { id, name } = req.body || {};
  if (!id && !name) return res.status(400).json({ error: '需要 id 或 name' });
  updatePlayerSave(userId, (saveData: any) => {
    if (Array.isArray(saveData.player?.inventory)) {
      const inv = saveData.player.inventory;
      const i = inv.findIndex((x: any) => (id && x?.id === id) || (name && x?.name === name));
      if (i >= 0) inv.splice(i, 1);
    }
  }).then((r) => {
    if (!r.ok) return res.status(400).json({ error: r.error });
    logGmAction('inventory_remove', `user:${userId}`, { id, name });
    res.json({ message: 'Removed', ok: true });
  });
});

// 重置玩家存档（保留账号名）
app.post('/api/gm/players/:id/reset-save', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  updatePlayerSave(userId, (saveData: any) => {
    const username = saveData.player?.name || '';
    saveData.player = {
      name: username,
      spiritStones: 0,
      exp: 0,
      realmIndex: 0,
      realmLevel: 0,
      combatPower: 0,
      reputation: 0,
      killCount: 0,
      playTime: 0,
      lotteryTickets: 0,
      inventory: [],
      pets: [],
      grotto: {},
      achievements: [],
      realm: '炼气期',
    };
  }).then((r) => {
    if (!r.ok) return res.status(400).json({ error: r.error });
    logGmAction('reset_save', `user:${userId}`);
    res.json({ message: 'Save reset', ok: true });
  });
});

// 强制修改玩家密码（无需旧密码）并吊销其所有 refresh token
app.post('/api/gm/players/:id/reset-password', authenticateGM, async (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  const { newPassword } = req.body || {};
  if (!newPassword || typeof newPassword !== 'string' || newPassword.length < 4) {
    return res.status(400).json({ error: 'newPassword 至少 4 个字符' });
  }
  if (newPassword.length > 64) return res.status(400).json({ error: 'newPassword 太长' });
  try {
    const hash = await bcrypt.hash(newPassword, 10);
    db.run('UPDATE users SET password_hash = ? WHERE id = ?', [hash, userId], (err: any) => {
      if (err) return res.status(500).json({ error: 'Update failed' });
      // 尝试踢下线（refresh_tokens 表可能不存在，忽略错误）
      db.run('DELETE FROM refresh_tokens WHERE user_id = ?', [userId], () => {
        logGmAction('reset_password', `user:${userId}`);
        res.json({ message: 'Password updated, all sessions revoked', ok: true });
      });
    });
  } catch (e: any) {
    res.status(500).json({ error: 'Hash error: ' + e.message });
  }
});

// 给指定玩家踢下线（清掉其 refresh tokens）
app.post('/api/gm/players/:id/kick', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  db.run('DELETE FROM refresh_tokens WHERE user_id = ?', [userId], (err: any) => {
    // 即使表不存在也返回成功（用户可能没有启用 refresh token）
    logGmAction('kick', `user:${userId}`);
    res.json({ message: 'Kicked', ok: true, tableExisted: !err });
  });
});

// ===== [r039reset] R-039 \u8bbe\u7f6e\u300c\u91cd\u65b0\u5f00\u59cb\u6e38\u620f\u300d\u21d2 \u8fde\u670d\u52a1\u7aef\u4e00\u8d77\u6e05\u5e72\u51c0\uff08\u4fdd\u7559\u8d26\u53f7\uff09=====
// \u75c5\u6839\uff1a\u91cd\u7f6e\u6309\u94ae\u53ea\u8d70\u524d\u7aef handleRebirth\uff08mm() \u7a7a\u5b9e\u73b0 + setPlayer(null)\u2026\uff09\uff0c\u96f6\u670d\u52a1\u7aef\u8bf7\u6c42 \u21d2
//   \u4ed9\u52a1\u00b7\u79f0\u53f7(player_titles) / \u4fee\u884c\u7edf\u8ba1(stats_daily) / \u4ed9\u52a1\u00b7\u5fc3\u6cd5(wudao) / \u6210\u5c31(achievement_claimed)
//   / \u529f\u6cd5(player_gongfa) \u7b49\u670d\u52a1\u7aef\u884c\u539f\u6837\u4fdd\u7559\u3002\u672c\u73af\u65b0\u589e POST /api/character/reset \u81ea\u670d\u6e05\u6863\u3002
// \u4fdd\u7559\uff08\u8d26\u53f7\u4e0e\u5171\u4eab/\u5168\u5c40\uff0c\u4e00\u6982\u4e0d\u52a8\uff09\uff1ausers \u884c / refresh_tokens / active_sessions\uff08\u8d26\u53f7\u4e0e\u767b\u5f55\u6001\uff09;
//   titles / gongfa\uff08\u5b57\u5178\u8868\uff09; worldboss / event_boss / activity_config / events / activity_frame;
//   sect_tasks / sect_ledger\uff08\u5b97\u95e8\u5171\u4eab\u8d26\uff09; chat_messages / gm_sessions / gm_audit_logs;
//   season_archives\uff08\u5386\u53f2\u8d5b\u5b63\uff09\u3002
// \u4e8b\u52a1\uff1a\u5168\u90e8 DELETE \u62fc\u6210**\u4e00\u6761** BEGIN..COMMIT \u811a\u672c\u4ea4\u7ed9 db.exec\uff08\u5355\u6b21\u63d0\u4ea4 \u21d2 \u522b\u7684\u8bf7\u6c42\u7684\u88f8
//   db.run \u4e0d\u53ef\u80fd\u63d2\u8fdb\u6765\uff1b\u4efb\u4e00\u53e5\u5931\u8d25 \u21d2 sqlite3_exec \u505c\u6b62 \u21d2 \u672c\u73af ROLLBACK\uff09\u3002SQL \u91cc\u9664\u300c\u6821\u9a8c\u8fc7
//   \u7684\u6574\u6570 uid\u300d\u5916\u65e0\u4efb\u4f55\u5916\u90e8\u8f93\u5165\uff08\u8868\u540d/\u5217\u540d\u5747\u4e3a\u672c\u73af\u5e38\u91cf\uff09\u3002
const R039_SINGLE: Array<[string, string]> = [
  // [\u8868, \u5f52\u5c5e\u5217] \u2014\u2014 \u73a9\u5bb6\u5355\u5217\u5f52\u5c5e\u7684\u884c\uff0c\u6574\u884c\u5220\u9664
  ['saves', 'user_id'], ['save_snapshots', 'user_id'], ['rankings', 'user_id'],
  ['mail', 'user_id'], ['player_titles', 'user_id'], ['daily_quests', 'user_id'],
  ['rebirth_state', 'user_id'], ['achievement_claimed', 'user_id'], ['lottery_history', 'user_id'],
  ['activity_milestones', 'user_id'], ['activity_rank_settled', 'user_id'],
  ['arena_trials', 'user_id'], ['arena_scores', 'user_id'], ['arena_trial_daily', 'user_id'],
  ['social_scores', 'user_id'], ['worldboss_hits', 'user_id'], ['event_boss_hits', 'user_id'],
  ['guide_progress', 'user_id'], ['week_goals', 'user_id'], ['teahouse_bets', 'user_id'],
  ['sect_cooldowns', 'user_id'], ['sect_task_claims', 'user_id'], ['sect_welfare_claims', 'user_id'],
  ['sect_applications', 'user_id'], ['player_sect_gongfa', 'user_id'], ['market_payouts', 'user_id'],
  ['stats_daily', 'player_id'], ['alchemy', 'player_id'], ['economy_ledger', 'player_id'],
  ['pets', 'player_id'], ['pet_spirit_exped', 'player_id'], ['pet_play_log', 'player_id'],
  ['pet_care_log', 'player_id'], ['dungeon_tracker', 'player_id'], ['adventures', 'player_id'],
  ['spirit_farm', 'player_id'], ['farm_unlocks', 'player_id'], ['farm_daily_care', 'player_id'],
  ['wudao', 'player_id'], ['wudao_log', 'player_id'], ['player_gongfa', 'player_id'],
  ['fun_daily', 'player_id'], ['activity_rain_state', 'player_id'], ['activity_checkin', 'player_id'],
  ['activity_token', 'player_id'], ['activity_token_daily', 'player_id'],
  ['chronicle', 'player_id'], ['market_listings', 'seller_id'], ['bounties', 'poster_id'],
  // \u9000\u5b97 / \u9000\u7ed3\u4e49\uff1a\u6210\u5458\u884c\u672c\u4f53\uff08\u9884\u6b65\u9aa4\u53ea\u8d1f\u8d23\u8ba9\u4f4d/\u89e3\u6563\uff0c\u884c\u672c\u4f53\u5728\u8fd9\u91cc\u5220\uff09
  ['sect_members', 'user_id'], ['sworn_members', 'user_id'],
];
// \u53cc\u5411\u5f52\u5c5e\uff08\u8be5\u73a9\u5bb6\u662f\u4efb\u4e00\u65b9\u90fd\u7b97\u300c\u4ed6\u7684\u6570\u636e\u300d\uff09\uff1a\u5bf9\u79f0\u5173\u7cfb/\u5bf9\u6218/\u6069\u6028\u5220\u53cc\u5411\uff08\u4e0e /api/friends/remove \u540c\u53e3\u5f84\uff09
const R039_MULTI: Array<[string, string]> = [
  ['friendships', 'user_id = ? OR friend_id = ?'],
  ['friend_gifts', 'sender_id = ? OR receiver_id = ?'],
  ['mentorships', 'mentor_id = ? OR apprentice_id = ?'],
  ['mentor_greetings', 'mentor_id = ? OR apprentice_id = ?'],
  ['teach_log', 'user_id = ? OR apprentice_id = ?'],
  ['arena_battles', 'challenger_id = ? OR defender_id = ?'],
  ['arena_snapshots', 'challenger_id = ? OR target_id = ?'],
  ['grudges', 'owner_id = ? OR enemy_id = ?'],
];
// \u5f52\u5c5e\u8be5\u73a9\u5bb6\u89d2\u8272\u7684\u5168\u90e8\u5f85\u5220\u8bed\u53e5\uff08\u987a\u5e8f\uff1a\u5148\u5220\u5f15\u7528\u4ed6\u8868\u7684\u884c\uff0c\u518d\u5220\u4e3b\u4f53\uff1b\u672c\u5e93 FK \u672a\u5f00\uff0c\u987a\u5e8f\u4ec5\u4e3a\u7a33\u59a5\uff09
function r039PurgeStatements(userId: number): Array<[string, any[]]> {
  const u = userId;
  const out: Array<[string, any[]]> = [];
  out.push(['DELETE FROM chronicle_praise WHERE user_id = ? OR entry_id IN (SELECT id FROM chronicle WHERE player_id = ?)', [u, u]]);
  out.push(['DELETE FROM couple_feast_guests WHERE user_id = ? OR feast_id IN (SELECT f.id FROM couple_feasts f JOIN couples c ON c.id = f.couple_id WHERE c.user_a = ? OR c.user_b = ?)', [u, u, u]]);
  out.push(['DELETE FROM couple_feasts WHERE couple_id IN (SELECT id FROM couples WHERE user_a = ? OR user_b = ?)', [u, u]]);
  for (const pair of R039_SINGLE) out.push(['DELETE FROM ' + pair[0] + ' WHERE ' + pair[1] + ' = ?', [u]]);
  for (const pair of R039_MULTI) {
    const n = (pair[1].match(/\?/g) || []).length;
    const args: any[] = [];
    for (let i = 0; i < n; i++) args.push(u);
    out.push(['DELETE FROM ' + pair[0] + ' WHERE ' + pair[1], args]);
  }
  return out;
}
// \u793e\u4ea4\u5173\u7cfb\u4fee\u590d\uff1a\u5148\u5904\u7406\u4f1a\u5f71\u54cd**\u4ed6\u4eba**\u7684\u591a\u6b65\u8bed\u4e49\uff08\u5e42\u7b49\uff1b\u5931\u8d25\u53ea\u8bb0\u65e5\u5fd7\uff0c\u4e0d\u963b\u65ad\u4e3b\u6e05\u6863\uff09
async function r039SocialRepair(userId: number, nowMs: number, iso: string): Promise<void> {
  // (a) \u5b97\u95e8\uff1a\u5b97\u4e3b\u8ba9\u4f4d\u7ed9\u6700\u65e9\u52a0\u5165\u7684\u5176\u5b83\u6210\u5458\uff1b\u72ec\u82d7\u5219\u89e3\u6563\uff08\u5426\u5219\u4f1a\u628a\u522b\u4eba\u7684\u5b97\u95e8\u5f04\u6210\u65e0\u4e3b\uff09
  const sm: any = await dbGet('SELECT sect_id, role FROM sect_members WHERE user_id = ?', [userId]);
  if (sm) {
    const sectId = Number(sm.sect_id);
    if (String(sm.role) === 'leader') {
      const next: any = await dbGet(
        'SELECT user_id FROM sect_members WHERE sect_id = ? AND user_id <> ? ORDER BY joined_at ASC, user_id ASC LIMIT 1',
        [sectId, userId]);
      if (next) {
        await dbRun("UPDATE sect_members SET role = 'leader' WHERE sect_id = ? AND user_id = ?", [sectId, Number(next.user_id)]);
        await dbRun('UPDATE sects SET leader_id = ? WHERE id = ?', [Number(next.user_id), sectId]);
      } else {
        await dbRun('UPDATE sects SET disbanded_at = ? WHERE id = ?', [iso, sectId]);
      }
    }
  }
  // (b) \u7ed3\u4e49\uff1a\u672c\u4eba\u9000\u51fa\u540e\u4eba\u6570\u4e0d\u8db3\u5219\u89e3\u6563\uff08\u4e0e /api/sworn/leave \u540c\u53e3\u5f84\uff09
  const sws: any[] = await dbAll('SELECT group_id FROM sworn_members WHERE user_id = ?', [userId]);
  for (const g of (sws || [])) {
    const c: any = await dbGet('SELECT COUNT(*) AS c FROM sworn_members WHERE group_id = ?', [Number(g.group_id)]);
    if (Number(c && c.c) - 1 < SWORN_MIN) {
      await dbRun('UPDATE sworn_groups SET disbanded = 1 WHERE id = ?', [Number(g.group_id)]);
    }
  }
  // (c) \u60ac\u8d4f\uff1a\u672c\u4eba\u300c\u63a5\u8fc7\u300d\u522b\u4eba\u7684\u60ac\u8d4f \u2192 \u9000\u56de\u53ef\u63a5\u72b6\u6001\uff08\u4e0d\u5220\u522b\u4eba\u7684\u60ac\u8d4f\u5355\uff09
  await dbRun("UPDATE bounties SET status = 'open', acceptor_id = NULL, acceptor_name = '' WHERE acceptor_id = ? AND status = 'accepted'", [userId]);
  // (d) \u9053\u4fa3\uff1a\u672a\u6210/\u5df2\u6210\u4e00\u5f8b\u548c\u79bb\uff08\u6cbf\u7528 divorce/decline \u7684 'divorced' \u53e3\u5f84\uff0c\u4e0d\u5f15\u5165\u65b0\u72b6\u6001\uff09
  await dbRun("UPDATE couples SET status = 'divorced', ended_at = ? WHERE status IN ('pending','married') AND (user_a = ? OR user_b = ?)", [nowMs, userId, userId]);
}
// \u4e3b\u6e05\u6863\uff1a\u793e\u4ea4\u4fee\u590d \u2192 \u52a0\u9501 \u2192 BEGIN..COMMIT \u5355\u811a\u672c\uff08\u5168\u6e05\u6216\u5168\u4e0d\u52a8\uff09
function r039PurgeCharacter(userId: number): Promise<{ ok: boolean; error?: string }> {
  const uid = Math.floor(Number(userId));
  if (!Number.isFinite(uid) || uid <= 0) return Promise.resolve({ ok: false, error: 'bad_user' });
  const nowMs = Date.now();
  const iso = nowIso();
  return r039SocialRepair(uid, nowMs, iso).catch((e: any) => {
    console.error('[r039reset] social repair failed:', e && e.message ? e.message : e);
  }).then(() => withSaveLock(uid, () => new Promise<{ ok: boolean; error?: string }>((resolve) => {
    const lines: string[] = ['BEGIN IMMEDIATE;'];   // \u2605 2026-10-01 \u4fee\uff1a\u5fc5\u987b\u5e26\u5206\u53f7\uff01join('\n') \u4e0d\u4f1a\u81ea\u52a8\u52a0\uff0c
    //   \u4e0d\u5e26\u5c31\u62fc\u6210 `BEGIN IMMEDIATE\nDELETE...` \u21d2 SQLite \u8bed\u6cd5\u9519\u8bef \u21d2 \u63a5\u53e3\u6052 500
    for (const s of r039PurgeStatements(uid)) {
      const args = s[1];
      let i = 0;
      lines.push(s[0].replace(/\?/g, () => String(args[i++])) + ';');
    }
    lines.push('COMMIT;');
    db.exec(lines.join('\n'), (err: any) => {
      if (!err) return resolve({ ok: true });
      console.error('[r039reset] purge failed, rolling back:', err && err.message ? err.message : err);
      db.run('ROLLBACK', () => resolve({ ok: false, error: 'purge_failed' }));
    });
  })));
}
// R-039 \u81ea\u670d\u6e05\u6863\uff1a\u6e05\u8be5\u89d2\u8272\u7684\u5168\u90e8\u670d\u52a1\u7aef\u6570\u636e\uff08\u4fdd\u7559\u8d26\u53f7 / \u767b\u5f55\u6001\uff09
app.post('/api/character/reset', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => 'chreset:' + (req.user?.id ?? req.ip) }), async (req: any, res: any) => {
  try {
    const r = await r039PurgeCharacter(req.user.id);
    if (!r.ok) return res.status(500).json({ error: 'reset_failed' });
    res.json({ ok: true });
  } catch (e: any) {
    console.error('[r039reset] error:', e && e.message ? e.message : e);
    res.status(500).json({ error: '\u670d\u52a1\u5668\u7e41\u5fd9' });
  }
});

// 游戏字典端点 (成就/称号/洞府/灵宠/功法/物品/抽奖池/宗门/天赋/草药)
let gameDicts: any = null;
function loadGameDicts() {
  if (gameDicts) return gameDicts;
  try {
    // BASECLEAN089: require 在 ESM 下未定义（fs/path 已由文件头 :7/:8 import），
    //   原 2 行会抛 ReferenceError 并被下方 catch 静默吞掉 ⇒ /api/gm/dicts 恒返回 {}。
    //   __dirname 由基座 :18 fileURLToPath(import.meta.url) 自建，可直接用。
    const file = path.join(__dirname, 'game-dicts.json');
    if (fs.existsSync(file)) {
      gameDicts = JSON.parse(fs.readFileSync(file, 'utf-8'));
      console.log('[GM] loaded game-dicts.json:', Object.keys(gameDicts).map(k => `${k}=${Array.isArray(gameDicts[k])?gameDicts[k].length:'-'}`).join(', '));
    } else {
      console.log('[GM] game-dicts.json not found at', file);
      gameDicts = {};
    }
  } catch (e: any) {
    console.log('[GM] loadGameDicts error:', e.message);
    gameDicts = {};
  }
  return gameDicts;
}
app.get('/api/gm/dicts', authenticateGM, (req: any, res: any) => {
  const d = loadGameDicts();
  res.json(d);
});

// 列出/查询表结构（GM Pro 用：拿 saves/users/rankings/lottery_history 字段名）
app.get('/api/gm/schema', authenticateGM, (req: any, res: any) => {
  const tables = ['users', 'saves', 'rankings', 'lottery_history', 'chat_messages', 'market_listings', 'gm_audit_logs', 'gm_sessions'];
  const result: Record<string, any[]> = {};
  let done = 0;
  tables.forEach((t) => {
    db.all(`PRAGMA table_info(${t})`, (err: any, rows: any[]) => {
      if (!err) result[t] = rows;
      done++;
      if (done === tables.length) res.json(result);
    });
  });
});

// 读取某玩家一条审计记录（最近 N 条）
app.get('/api/gm/players/:id/audit', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  const limit = Math.min(100, parseInt(req.query.limit as string) || 30);
  // gm_audit_logs.details 是 JSON 字符串，其中可能含 'user:123' 形式的 target
  db.all(
    `SELECT id, action, target, detail, created_at FROM gm_audit_logs
     WHERE target LIKE ? OR detail LIKE ?
     ORDER BY id DESC LIMIT ?`,
    [`%user:${userId}%`, `%user:${userId}%`, limit],
    (err: any, rows: any[]) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json({ logs: rows || [] });
    }
  );
});

// GM 交易行管理：列出所有 listings（任意 status）
app.get('/api/gm/market', authenticateGM, (req: any, res: any) => {
  const page = Math.max(1, parseInt(req.query.page as string) || 1);
  const pageSize = Math.min(100, parseInt(req.query.pageSize as string) || 20);
  const offset = (page - 1) * pageSize;
  const status = (req.query.status as string) || '';
  const where = status ? 'WHERE status = ?' : '';
  const params: any[] = status ? [status] : [];
  db.get(`SELECT COUNT(*) as total FROM market_listings ${where}`, params, (err, countRow: any) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    db.all(
      `SELECT id, seller_id, seller_name, item_name, item_type, item_rarity, price, quantity,
              buyer_id, is_equippable, equipment_slot, status, created_at, sold_at
       FROM market_listings ${where}
       ORDER BY id DESC LIMIT ? OFFSET ?`,
      [...params, pageSize, offset],
      (err2, rows: any[]) => {
        if (err2) return res.status(500).json({ error: 'Database error' });
        res.json({ total: countRow.total, page, pageSize, listings: rows || [] });
      }
    );
  });
});

// GM 改价 / 修改 listing
app.put('/api/gm/market/:id', authenticateGM, (req: any, res: any) => {
  const id = parseInt(req.params.id);
  const { price, quantity, status } = req.body || {};
  const sets: string[] = [];
  const params: any[] = [];
  if (price != null && Number(price) > 0) { sets.push('price = ?'); params.push(Number(price)); }
  if (quantity != null && asNum(quantity) >= 1) { sets.push('quantity = ?'); params.push(Math.floor(asNum(quantity))); }
  if (status && ['active', 'sold', 'cancelled'].includes(status)) { sets.push('status = ?'); params.push(status); }
  if (sets.length === 0) return res.status(400).json({ error: '没有可改的字段' });
  params.push(id);
  db.run(`UPDATE market_listings SET ${sets.join(', ')} WHERE id = ?`, params, function (err) {
    if (err) return res.status(500).json({ error: 'Update failed' });
    if (this.changes === 0) return res.status(404).json({ error: 'Not found' });
    logGmAction('market_update', `market:${id}`, { price, quantity, status });
    res.json({ message: 'Updated', ok: true, changes: this.changes });
  });
});

// GM 强制下架
app.post('/api/gm/market/:id/cancel', authenticateGM, (req: any, res: any) => {
  const id = parseInt(req.params.id);
  db.run(`UPDATE market_listings SET status = 'cancelled' WHERE id = ? AND status = 'active'`, [id], function (err) {
    if (err) return res.status(500).json({ error: 'Cancel failed' });
    if (this.changes === 0) return res.status(409).json({ error: '商品已售出/已下架' });
    logGmAction('market_cancel', `market:${id}`);
    res.json({ message: 'Cancelled', ok: true });
  });
});

// 世界聊天管理
app.get('/api/gm/messages', authenticateGM, (req: any, res: any) => {
  const limit = Math.min(200, parseInt(req.query.limit as string) || 50);
  db.all(
    'SELECT id, username AS user, text, created_at FROM chat_messages ORDER BY id DESC LIMIT ?',
    [limit],
    (err: any, rows: any[]) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json({ messages: (rows || []).reverse() });
    }
  );
});
app.delete('/api/gm/messages/:id', authenticateGM, (req: any, res: any) => {
  const msgId = parseInt(req.params.id);
  db.run('DELETE FROM chat_messages WHERE id = ?', [msgId], (err: any) => {
    if (err) return res.status(500).json({ error: 'Delete failed' });
    logGmAction('delete_chat', `msg:${msgId}`);
    res.json({ message: 'Deleted' });
  });
});

// 抽奖历史查询 - 玩家自助历史（前端抽奖历史弹窗）
// 注：原 GM 全量统计接口已停用，避免大量抽奖请求写入数据库造成膨胀
app.get('/api/gm/lottery-history', authenticateGM, (req: any, res: any) => {
  const userId = req.query.userId ? parseInt(req.query.userId as string) : null;
  if (!userId) {
    // 禁止全量统计，必须指定 userId
    return res.status(400).json({ error: 'userId required (full history disabled)' });
  }
  const limit = Math.min(200, parseInt(req.query.limit as string) || 100);
  db.all(
    'SELECT id, prize_name, prize_type, prize_rarity, quantity, created_at FROM lottery_history WHERE user_id = ? ORDER BY id DESC LIMIT ?',
    [userId, limit],
    (err: any, rows: any[]) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json({ history: rows || [] });
    }
  );
});

// GM 审计日志
app.get('/api/gm/audit-logs', authenticateGM, (req: any, res: any) => {
  const limit = Math.min(500, parseInt(req.query.limit as string) || 100);
  db.all(
    'SELECT * FROM gm_audit_logs ORDER BY id DESC LIMIT ?',
    [limit],
    (err: any, rows: any[]) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json({ logs: rows || [] });
    }
  );
});

// ── 抽奖历史记录接口（前端在抽奖后调用，使用 token 查询参数）──
// 注意：原实现会把所有抽奖记录写入数据库，10000 张抽奖劵会产生 10000 条记录，
//      撑爆 lottery_history 表并使前端 save 请求超过 body 限制。
//      改为：只接受请求并返回成功（前端抽奖弹窗本身已展示本次结果），
//      不再持久化抽奖历史。GM 全量统计接口已停用，玩家自助查询保留。
function registerLotteryRecordHandler(routePath: string) {
  app.post(routePath, (req: any, res: any) => {
    const token = req.query.token as string;
    if (!token) return res.status(401).json({ error: 'token required' });
    jwt.verify(token, JWT_SECRET_USED, (err: any, payload: any) => {
      if (err || payload.type !== 'access') return res.status(403).json({ error: 'Invalid token' });
      const records = req.body?.records;
      if (!Array.isArray(records) || records.length === 0) return res.json({ message: 'nothing to record' });
      // 不再写入数据库；前端抽奖弹窗已经展示本次结果，无需服务端持久化。
      res.json({ message: 'skipped (server-side lottery history disabled)', count: records.length });
    });
  });
}
registerLotteryRecordHandler('/lottery-history');
registerLotteryRecordHandler('/api/lottery-history');

// ── 玩家自助抽奖历史查询（前端"抽奖历史"弹窗调用，access token 查询本人记录）──
// 玩家端 GET /yl/api/lottery-history?token=... → Nginx 反代为 /api/lottery-history
app.get('/api/lottery-history', (req: any, res: any) => {
  const token = req.query.token as string;
  if (!token) return res.status(401).json({ error: 'token required' });
  jwt.verify(token, JWT_SECRET_USED, (err: any, payload: any) => {
    if (err || payload.type !== 'access') return res.status(403).json({ error: 'Invalid token' });
    const userId = payload.id;
    const limit = Math.min(200, parseInt(req.query.limit as string) || 100);
    db.all(
      'SELECT id, prize_name, prize_type, prize_rarity, quantity, created_at FROM lottery_history WHERE user_id = ? ORDER BY id DESC LIMIT ?',
      [userId, limit],
      (err: any, rows: any[]) => {
        if (err) return res.status(500).json({ error: 'Database error' });
        res.json({ history: rows || [] });
      }
    );
  });
});
// 同时提供无前缀版本（直连 3002 时使用）
app.get('/lottery-history', (req: any, res: any) => {
  const token = req.query.token as string;
  if (!token) return res.status(401).json({ error: 'token required' });
  jwt.verify(token, JWT_SECRET_USED, (err: any, payload: any) => {
    if (err || payload.type !== 'access') return res.status(403).json({ error: 'Invalid token' });
    const userId = payload.id;
    const limit = Math.min(200, parseInt(req.query.limit as string) || 100);
    db.all(
      'SELECT id, prize_name, prize_type, prize_rarity, quantity, created_at FROM lottery_history WHERE user_id = ? ORDER BY id DESC LIMIT ?',
      [userId, limit],
      (err: any, rows: any[]) => {
        if (err) return res.status(500).json({ error: 'Database error' });
        res.json({ history: rows || [] });
      }
    );
  });
});

// ── 轻量内存限流（P1-4/P1-5，无新依赖）：Map<key,{count,resetAt}> ──
const rateBuckets = new Map<string, { count: number; resetAt: number }>();
// v28.1: hoisted to a function declaration on purpose -- `/api/save` (declared earlier in this file) references it at module-eval time; a `const` arrow would hit the temporal dead zone and crash the server on boot.
function rateLimit({ windowMs, max, keyFn }: { windowMs: number; max: number; keyFn?: (req: any) => string }) {
  return (req: any, res: any, next: any) => {
    const key = keyFn ? keyFn(req) : String(req.ip || req.socket?.remoteAddress || 'unknown');
    const now = Date.now();
    const bucket = rateBuckets.get(key);
    if (!bucket || bucket.resetAt <= now) {
      rateBuckets.set(key, { count: 1, resetAt: now + windowMs });
      return next();
    }
    bucket.count++;
    if (bucket.count > max) {
      res.set('Retry-After', String(Math.max(1, Math.ceil((bucket.resetAt - now) / 1000))));
      return res.status(429).json({ error: '请求过于频繁，请稍后再试' });
    }
    next();
  };
}
// 定期清理过期桶，防止 Map 无限膨胀
setInterval(() => {
  const now = Date.now();
  for (const [k, b] of rateBuckets) {
    if (b.resetAt <= now) rateBuckets.delete(k);
  }
}, 10 * 60 * 1000).unref();

// ── AI 代理 API（隐藏密钥，供前端通过 VITE_AI_USE_PROXY=true 调用）──
app.post('/api/ai/chat', rateLimit({ windowMs: 60 * 60 * 1000, max: 20 }), async (req: any, res: any) => {
  const { messages, temperature = 0.8, max_tokens = 500 } = req.body || {};
  if (!messages || !Array.isArray(messages) || messages.length === 0) {
    return res.status(400).json({ error: 'messages is required' });
  }

  const apiKey = process.env.AI_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'AI_API_KEY not configured on server' });
  }

  const apiUrl = process.env.AI_API_URL || 'https://api.siliconflow.cn/v1/chat/completions';
  // 服务端强制使用 .env 配置的模型（忽略前端硬编码的旧 model），避免旧模型名覆盖新配置
  const useModel = process.env.AI_MODEL || 'Qwen/Qwen2.5-7B-Instruct';
  // 限制温度上下限（P1-4）
  const temp = Math.min(Math.max(Number(temperature) || 0.8, 0), 0.8);
  // 钳制 max_tokens（P1-4）：防止客户端传超大值刷爆上游额度
  const maxTokens = Math.min(Math.max(Math.floor(Number(max_tokens)) || 500, 1), 1000);

  try {
    const aiRes = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: useModel,
        messages,
        temperature: temp,
        max_tokens: maxTokens,
        // 免费思考型模型（Qwen3.5 等）关闭思考，避免 reasoning 吃掉 max_tokens
        enable_thinking: false,
        // 硅基非流式请求当前会无限挂起（2026-09-15 实测），改流式聚合
        stream: true,
      }),
      // 30 秒超时（流式有首包即判活）
      signal: AbortSignal.timeout(30000),
    });

    if (!aiRes.ok) {
      const errText = await aiRes.text();
      return res.status(aiRes.status).json({ error: 'AI upstream error', detail: errText.slice(0, 300) });
    }

    // 聚合 SSE 分片 → 组装标准 OpenAI 非流式响应（前端零改动）
    let content = '';
    const reader = (aiRes.body as any).getReader();
    const decoder = new TextDecoder();
    let buf = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() || '';
      for (const line of lines) {
        const t = line.trim();
        if (!t.startsWith('data:')) continue;
        const payload = t.slice(5).trim();
        if (!payload || payload === '[DONE]') continue;
        try {
          const chunk = JSON.parse(payload);
          const delta = chunk.choices?.[0]?.delta?.content;
          if (typeof delta === 'string') content += delta;
        } catch (_) { /* 跳过非 JSON 行 */ }
      }
    }
    res.status(200).json({
      id: 'chatcmpl-aggregated',
      object: 'chat.completion',
      model: useModel,
      choices: [{ index: 0, message: { role: 'assistant', content }, finish_reason: 'stop' }],
    });
  } catch (err: any) {
    res.status(502).json({ error: 'AI proxy error', detail: String(err?.message || err) });
  }
});

// ── 世界聊天 API（HTTP 轮询版，替代 PartyKit WebSocket）──
// GET /api/messages?after=<id>&limit=<n> 拉取指定 id 之后的新消息
app.get('/api/messages', (req: any, res: any) => {
  const afterId = parseInt(req.query.after as string) || 0;
  const limit = Math.min(Math.max(parseInt(req.query.limit as string) || 50, 1), 100);

  db.all(
    `SELECT id, username as user, text, (strftime('%s', created_at) * 1000) as timestamp
     FROM chat_messages WHERE id > ? ORDER BY id ASC LIMIT ?`,
    [afterId, limit],
    (err: any, rows: any[]) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json({ messages: rows || [] });
    }
  );
});

// POST /api/messages 发送消息 { text, user }
// P1-5：加限流（每 IP 10 条/分钟防刷屏）；软鉴权——前端当前不带 Authorization
// （硬鉴权 authenticateToken 会当场打断线上世界聊天，需前端配合后收紧，见 yl-fix.md），
// 但若请求带了合法 access token，则显示名强制取 token 用户名，杜绝已登录链路的身份伪造。
app.post('/api/messages', rateLimit({ windowMs: 60 * 1000, max: 10 }), async (req: any, res: any) => {
  const { text, user } = req.body || {};
  const trimmedText = typeof text === 'string' ? text.trim() : '';
  let username = typeof user === 'string' ? user.trim() : '';

  if (!trimmedText || !username) {
    return res.status(400).json({ error: 'text and user are required' });
  }
  if (trimmedText.length > 200) {
    return res.status(400).json({ error: 'text too long' });
  }
  const authHeader = req.headers['authorization'] || '';
  const bearer = authHeader.split(' ')[1];
  if (bearer) {
    try {
      const payload: any = await jwt.verify(bearer, JWT_SECRET_USED);
      if (payload?.type === 'access' && payload.username) username = String(payload.username);
    } catch { /* 无效 token 忽略，沿用 body 用户名 */ }
  }
  username = username.slice(0, 32);

  // [v2810] \u7981\u8a00\u62e6\u622a\uff1a\u4ec5\u62e6\u300c\u53d1\u8a00\u300d\uff08\u4e16\u754c\u804a\u5929\u5199\u5165\uff09\uff0c\u4e0d\u62e6\u767b\u5f55/\u5b58\u6863/\u9886\u53d6\u3002
  try {
    const mrow: any = await dbGet('SELECT muted_until FROM users WHERE username = ?', [username]);
    const mu = mrow && mrow.muted_until ? Date.parse(String(mrow.muted_until)) : NaN;
    if (Number.isFinite(mu) && mu > Date.now()) {
      res.statusCode = 403;
      return res.json({ error: '\u4f60\u5df2\u88ab\u7981\u8a00\uff0c\u89e3\u9664\u65f6\u95f4 ' + new Date(mu).toISOString(), code: 'MUTED', mutedUntil: new Date(mu).toISOString() });
    }
  } catch (e: any) { /* \u7981\u8a00\u6821\u9a8c\u5931\u8d25\u4e0d\u963b\u65ad\u53d1\u8a00\uff08\u53ef\u7528\u6027\u4f18\u5148\uff09 */ }
  db.run(
    'INSERT INTO chat_messages (username, text) VALUES (?, ?)',
    [username, trimmedText],
    function (this: any, err: any) {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.status(201).json({
        message: {
          id: this.lastID,
          type: 'chat',
          user: username,
          text: trimmedText,
          timestamp: Date.now(),
        },
      });
    }
  );
});

// ── 排行榜 API ──
const REALM_NAMES = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];

const LEADERBOARD_SORTS: Record<string, { orderBy: string; aheadCondition: string; getParams: (row: any) => any[] }> = {
  realm: {
    orderBy: 'realm_index DESC, realm_level DESC, exp DESC, updated_at DESC, user_id ASC',
    aheadCondition: `
      (realm_index > ?)
      OR (realm_index = ? AND realm_level > ?)
      OR (realm_index = ? AND realm_level = ? AND exp > ?)
      OR (realm_index = ? AND realm_level = ? AND exp = ? AND updated_at > ?)
      OR (realm_index = ? AND realm_level = ? AND exp = ? AND updated_at = ? AND user_id < ?)
    `,
    getParams: (row) => [
      row.realm_index,
      row.realm_index, row.realm_level,
      row.realm_index, row.realm_level, row.exp,
      row.realm_index, row.realm_level, row.exp, row.updated_at,
      row.realm_index, row.realm_level, row.exp, row.updated_at, row.user_id,
    ],
  },
  combat: {
    orderBy: 'combat_power DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC',
    aheadCondition: `
      (combat_power > ?)
      OR (combat_power = ? AND realm_index > ?)
      OR (combat_power = ? AND realm_index = ? AND realm_level > ?)
      OR (combat_power = ? AND realm_index = ? AND realm_level = ? AND updated_at > ?)
      OR (combat_power = ? AND realm_index = ? AND realm_level = ? AND updated_at = ? AND user_id < ?)
    `,
    getParams: (row) => [
      row.combat_power,
      row.combat_power, row.realm_index,
      row.combat_power, row.realm_index, row.realm_level,
      row.combat_power, row.realm_index, row.realm_level, row.updated_at,
      row.combat_power, row.realm_index, row.realm_level, row.updated_at, row.user_id,
    ],
  },
  stones: {
    orderBy: 'spirit_stones DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC',
    aheadCondition: `
      (spirit_stones > ?)
      OR (spirit_stones = ? AND realm_index > ?)
      OR (spirit_stones = ? AND realm_index = ? AND realm_level > ?)
      OR (spirit_stones = ? AND realm_index = ? AND realm_level = ? AND updated_at > ?)
      OR (spirit_stones = ? AND realm_index = ? AND realm_level = ? AND updated_at = ? AND user_id < ?)
    `,
    getParams: (row) => [
      row.spirit_stones,
      row.spirit_stones, row.realm_index,
      row.spirit_stones, row.realm_index, row.realm_level,
      row.spirit_stones, row.realm_index, row.realm_level, row.updated_at,
      row.spirit_stones, row.realm_index, row.realm_level, row.updated_at, row.user_id,
    ],
  },
};

// GET /api/leaderboard?sort=realm|combat|stones&limit=50&offset=0
app.get('/api/leaderboard', (req: any, res: any) => {
  const sort = (req.query.sort as string) || 'realm';
  const limit = Math.min(Math.max(parseInt(req.query.limit as string) || 50, 1), 200);
  const offset = Math.max(parseInt(req.query.offset as string) || 0, 0);
  const sortConfig = LEADERBOARD_SORTS[sort] || LEADERBOARD_SORTS.realm;

  try {
    db.all(
      `SELECT user_id, username, name, realm_index, realm_level, exp, combat_power, spirit_stones, reputation, achievement_count, kill_count, play_time, updated_at
       FROM rankings
       ORDER BY ${sortConfig.orderBy}
       LIMIT ? OFFSET ?`,
      [limit, offset],
      (err, rows: any[]) => {
        // 查询失败或表不存在时，返回空数组而非报错
        if (err) {
          console.error('Leaderboard query error:', err.message);
          return res.json({
            sort,
            limit,
            offset,
            total: 0,
            rankings: [],
          });
        }

        const result = (rows || []).map((row, index) => ({
          rank: offset + index + 1,
          user_id: row.user_id,
          // fix(rank) 2026-09-17：返回角色昵称（无则回落登录账号 username）
          name: row.name || row.username,
          // 客户端排行 UI 当前渲染的是 username 字段，同步为昵称；账号标识以 user_id 为准
          username: row.name || row.username,
          realm: REALM_NAMES[row.realm_index] || '未知',
          realm_index: row.realm_index,
          realm_level: row.realm_level,
          exp: row.exp,
          combat_power: row.combat_power,
          spirit_stones: row.spirit_stones,
          reputation: row.reputation,
          achievement_count: row.achievement_count,
          kill_count: row.kill_count,
          play_time: row.play_time,
          updated_at: row.updated_at,
        }));

        res.json({
          sort,
          limit,
          offset,
          total: result.length,
          rankings: result,
        });
      }
    );
  } catch (err: any) {
    // 极端情况（如同步异常），也返回空数组
    console.error('Leaderboard unexpected error:', err.message);
    return res.json({
      sort,
      limit,
      offset,
      total: 0,
      rankings: [],
    });
  }
});

// GET /api/leaderboard/me — 获取当前登录用户的排名
app.get('/api/leaderboard/me', authenticateToken, (req: any, res: any) => {
  // 获取用户自己的排名数据
  db.get(
    'SELECT * FROM rankings WHERE user_id = ?',
    [req.user.id],
    (err, myRow: any) => {
      // 数据库错误或无数据时，返回 found: false，不报错
      if (err) {
        console.error('Leaderboard/me query error:', err.message);
        return res.json({ found: false, message: '暂无排名数据' });
      }
      if (!myRow) return res.json({ found: false, message: '您尚未上传存档，无法查看排名' });

      // 查询三种排序的排名：必须和 /api/leaderboard 的 ORDER BY 完全一致
      const queries = [
        { sort: 'realm', config: LEADERBOARD_SORTS.realm },
        { sort: 'combat', config: LEADERBOARD_SORTS.combat },
        { sort: 'stones', config: LEADERBOARD_SORTS.stones },
      ];

      // fix(rank) 2026-09-17：name=角色昵称（无则回落登录账号）；username 同步为昵称与列表口径一致
      const results: any = {
        found: true,
        name: myRow.name || myRow.username,
        username: myRow.name || myRow.username,
      };

      let completed = 0;
      queries.forEach(({ sort, config }) => {
        db.get(
          `SELECT COUNT(*) as cnt FROM rankings WHERE ${config.aheadCondition}`,
          config.getParams(myRow),
          (err2, countRow: any) => {
            completed++;
            if (!err2 && countRow) {
              results[`${sort}_rank`] = (countRow.cnt || 0) + 1;
            }
            if (completed === queries.length) {
              res.json(results);
            }
          }
        );
      });
    }
  );
});

// ── 交易行 API ──

// GET /api/market/items — 获取在售商品列表（分页+分类+搜索）
function parseMarketSourceItem(itemSourceJson?: string | null): any | null {
  if (!itemSourceJson) return null;
  try {
    return JSON.parse(itemSourceJson);
  } catch {
    return null;
  }
}

app.get('/api/market/items', (req: any, res: any) => {
  const page = Math.max(1, parseInt(req.query.page as string) || 1);
  const limit = Math.min(Math.max(1, parseInt(req.query.limit as string) || 10), 100);
  const offset = (page - 1) * limit;
  const category = (req.query.category as string) || 'all';
  const search = (req.query.search as string) || '';

  let where = "WHERE status = 'active'";
  const params: any[] = [];

  if (category && category !== 'all') {
    where += ' AND item_type = ?';
    params.push(category);
  }
  if (search.trim()) {
    where += ' AND item_name LIKE ?';
    params.push(`%${search.trim()}%`);
  }

  // 查总数
  db.get(`SELECT COUNT(*) as total FROM market_listings ${where}`, params, (err, row: any) => {
    if (err) return res.json({ items: [], total: 0, page, limit: 0 });
    const total = row?.total || 0;

    // 查分页
    db.all(
      `SELECT id, seller_id, seller_name, item_name as name, item_type as type, item_description as description,
              item_rarity as rarity, price, quantity, is_equippable, equipment_slot, effect_json, item_source_json, created_at
       FROM market_listings ${where}
       ORDER BY created_at DESC
       LIMIT ? OFFSET ?`,
      [...params, limit, offset],
      (err2, rows: any[]) => {
        if (err2) return res.json({ items: [], total: 0, page, limit });
        const items = (rows || []).map((r) => {
          const sourceItem = parseMarketSourceItem(r.item_source_json);
          return {
            id: `market-${r.id}`,
            name: r.name,
            type: r.type,
            description: r.description || '',
            rarity: r.rarity,
            price: r.price,
            quantity: r.quantity || 1,
            advancedItemType: sourceItem?.advancedItemType,
            advancedItemId: sourceItem?.advancedItemId,
            isEquippable: !!r.is_equippable,
            equipmentSlot: r.equipment_slot || undefined,
            effect: r.effect_json ? JSON.parse(r.effect_json) : undefined,
            sellerName: r.seller_name,
            sellerId: 'system',
            sellerItemData: r.item_source_json || undefined,
            createdAt: r.created_at,
          };
        });
        res.json({ items, total, page, limit });
      }
    );
  });
});

// POST /api/market/list — 上架物品
app.post('/api/market/list', authenticateToken, (req: any, res: any) => {
  const { itemName, itemType, description, rarity, price, quantity, effect, isEquippable, equipmentSlot, itemSourceJson } = req.body || {};

  // P1-6 存储型 XSS 防护：price/quantity 强制数字（旧校验 `!price || price <= 0` 对非数字字符串
  // 恒为 false 直接原样入库，gm-pro 交易行属性位未转义渲染即打 GM 管理员）；文本字段强制 String+截断
  const priceNum = Math.floor(asNum(price));
  if (!itemName || typeof itemName !== 'string' || !itemName.trim() || !Number.isFinite(priceNum) || priceNum <= 0) {
    return res.status(400).json({ error: '物品名称和有效价格是必填项' });
  }
  const safeItemName = itemName.trim().slice(0, 100);
  const safeItemType = (asStr(itemType) || '\u6750\u6599').slice(0, 50);
  const safeDescription = asStr(description).slice(0, 500);
  const safeRarity = (asStr(rarity) || '\u666e\u901a').slice(0, 50);
  const safeSlot = equipmentSlot ? asStr(equipmentSlot).slice(0, 50) : null;
  const listingQuantity = Math.max(1, Math.floor(asNum(quantity)) || 1);

  db.run(
    `INSERT INTO market_listings (seller_id, seller_name, item_name, item_type, item_description, item_rarity, price, quantity, is_equippable, equipment_slot, effect_json, item_source_json)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      req.user.id,
      req.user.username,
      safeItemName,
      safeItemType,
      safeDescription,
      safeRarity,
      priceNum,
      listingQuantity,
      isEquippable ? 1 : 0,
      safeSlot,
      effect ? JSON.stringify(effect) : null,
      itemSourceJson || '',
    ],
    function (err) {
      if (err) {
        console.error('上架失败:', err.message);
        return res.status(500).json({ error: '上架失败' });
      }
      res.json({ success: true, listingId: this.lastID });
    }
  );
});

// POST /api/market/purchase — 购买物品（先查库存再扣）
app.post('/api/market/purchase', authenticateToken, (req: any, res: any) => {
  const { listingId } = req.body || {};
  if (!listingId) return res.status(400).json({ error: '缺少 listingId' });

  // V27：容忍重复前缀（market-market-7）——上游 1ec1b63 同款修复；旧写法只剥一层
  const cleanId = asStr(listingId).replace(/^(?:market-)+/, '');
  const numericId = parseInt(cleanId, 10);

  db.get('SELECT * FROM market_listings WHERE id = ? AND status = ?', [numericId, 'active'], (err, listing: any) => {
    if (err || !listing) {
      return res.status(404).json({ error: '商品不存在或已售出' });
    }
    if (listing.seller_id === req.user.id) {
      return res.status(400).json({ error: '不能购买自己的商品' });
    }

    // 返回商品信息（真实扣款在客户端完成，服务端只做库存检查和锁定）
    // 实际扣款由客户端调用 purchase/confirm 完成
    const sourceItem = parseMarketSourceItem(listing.item_source_json);
    res.json({
      success: true,
      listing: {
        id: listing.id,
        name: listing.item_name,
        type: listing.item_type,
        description: listing.item_description,
        rarity: listing.item_rarity,
        price: listing.price,
        quantity: listing.quantity || 1,
        advancedItemType: sourceItem?.advancedItemType,
        advancedItemId: sourceItem?.advancedItemId,
        isEquippable: !!listing.is_equippable,
        equipmentSlot: listing.equipment_slot,
        effect: listing.effect_json ? JSON.parse(listing.effect_json) : undefined,
        itemSourceJson: listing.item_source_json,
      },
    });
  });
});

// POST /api/market/purchase/confirm — 确认购买（原子锁定库存 + 卖家收益入账托管）
// 与上游 1ec1b63 的差异（有意，非疏漏）：上游在此处「服务端扣买家灵石 + 往云存档背包塞物品」。
// 本服存档为客户端权威 + gm_revision 乐观锁，云档存在 ≤10s 同步滞后（客户端 ylHidePush 自动存档 10s 节流），
// 若服务端按旧云档扣款，会与客户端本地未同步的收益互相覆盖 → 双重扣款 / 丢收益。故：
//   · 买家扣款与入包仍由客户端完成（沿用既有 handlePurchase：本地扣款 + confirm 失败回滚）
//   · 服务端只做 ① 原子锁定 listing ② 把货款写入 market_payouts 托管，待卖家 /api/market/payouts/claim 领取
app.post('/api/market/purchase/confirm', authenticateToken, (req: any, res: any) => {
  const { listingId } = req.body || {};
  if (!listingId) return res.status(400).json({ error: '缺少 listingId' });

  // V27：容忍重复前缀（market-market-7）——上游 1ec1b63 同款修复；旧写法只剥一层
  const cleanId = asStr(listingId).replace(/^(?:market-)+/, '');
  const numericId = parseInt(cleanId, 10);
  if (!Number.isFinite(numericId)) return res.status(400).json({ error: '商品 ID 非法' });

  // 先取卖家与货款（入账托管需要），再做原子锁定
  db.get('SELECT id, seller_id, price FROM market_listings WHERE id = ?', [numericId], (getErr: any, listing: any) => {
    if (getErr || !listing) return res.status(404).json({ error: '商品不存在' });
    if (listing.seller_id === req.user.id) return res.status(400).json({ error: '不能购买自己的商品' });

    db.run(
      `UPDATE market_listings SET status = 'sold', buyer_id = ?, sold_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'active' AND seller_id != ?`,
      [req.user.id, numericId, req.user.id],
      function (this: any, err: any) {
        if (err) return res.status(500).json({ error: '购买失败' });
        if (this.changes === 0) return res.status(409).json({ error: '商品已被他人买走' });

        const amount = Math.max(0, Math.floor(Number(listing.price) || 0));
        if (!(amount > 0) || !listing.seller_id) return res.json({ success: true });

        // 卖家收益入账托管：listing 已原子锁定，changes>0 全局唯一一次，天然幂等不重复入账
        db.run(
          'INSERT INTO market_payouts (user_id, listing_id, amount) VALUES (?, ?, ?)',
          [listing.seller_id, numericId, amount],
          (insErr: any) => {
            if (insErr) {
              // 入账失败不回滚交易（物品已交付买家）；仅记录，可事后补偿
              console.error('[market] payout insert failed listing=' + numericId + ' seller=' + listing.seller_id + ': ' + insErr.message);
            }
            res.json({ success: true, payout: amount });
          }
        );
      }
    );
  });
});

// POST /api/market/cancel — 下架自己的商品
app.post('/api/market/cancel', authenticateToken, (req: any, res: any) => {
  const { listingId } = req.body || {};
  if (!listingId) return res.status(400).json({ error: '缺少 listingId' });

  // V27：容忍重复前缀（market-market-7）——上游 1ec1b63 同款修复；旧写法只剥一层
  const cleanId = asStr(listingId).replace(/^(?:market-)+/, '');
  const numericId = parseInt(cleanId, 10);

  db.get('SELECT item_source_json FROM market_listings WHERE id = ? AND seller_id = ? AND status = ?',
    [numericId, req.user.id, 'active'],
    (err, listing: any) => {
      if (err || !listing) return res.status(404).json({ error: '商品不存在或无权操作' });

      db.run('UPDATE market_listings SET status = ? WHERE id = ?', ['cancelled', numericId], (err2) => {
        if (err2) return res.status(500).json({ error: '下架失败' });
        // 返回原始物品数据用于客户端还原
        const sourceItem = listing.item_source_json ? JSON.parse(listing.item_source_json) : null;
        res.json({ success: true, item: sourceItem });
      });
    }
  );
});

// ── 交易行卖家收益（V27，上游 1ec1b63 移植）──
// 与上游差异：上游用裸读改写 helper（getSavePlayer/writeSavePlayer，不 bump gm_revision、无锁），
// 这里入账/回滚一律走 updatePlayerSave —— 复用其 saveLock 读改写互斥、gm_revision++（促客户端拉新档）、
// upsertRanking 排行同步与 writeEconomyMirror 经济镜像，避免与 GM patch / POST /api/save / 炼丹 / 悬赏等并发路径互相覆盖。

// GET /api/market/payouts — 查询当前用户未领取的卖家收益
app.get('/api/market/payouts', authenticateToken, (req: any, res: any) => {
  db.get(
    'SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count FROM market_payouts WHERE user_id = ? AND claimed = 0',
    [req.user.id],
    (err: any, row: any) => {
      if (err) return res.status(500).json({ error: '查询收益失败' });
      db.all(
        'SELECT id, listing_id, amount, created_at FROM market_payouts WHERE user_id = ? AND claimed = 0 ORDER BY id DESC LIMIT 200',
        [req.user.id],
        (err2: any, rows: any[]) => {
          if (err2) return res.status(500).json({ error: '查询收益失败' });
          res.json({
            total: Number(row?.total) || 0,
            count: Number(row?.count) || 0,
            items: (rows || []).map((r) => ({
              id: r.id,
              listingId: r.listing_id,
              amount: Number(r.amount) || 0,
              createdAt: r.created_at,
            })),
          });
        }
      );
    }
  );
});

// POST /api/market/payouts/claim — 领取卖家收益（全部未领取的一次性入账）
// 事务口径：① 先入账（updatePlayerSave，失败不动 claimed，可重试、绝不吞钱）
//           ② 入账成功后再守卫式标记 claimed=1（WHERE claimed=0，changes=0 = 并发已被他人领走）
//           ③ 标记失败/被并发抢先 → 回滚刚入账的灵石（补偿式，与 mailClaimCore / alchemy 同款全或无可重试）
app.post('/api/market/payouts/claim', authenticateToken, (req: any, res: any) => {
  const userId = req.user.id;
  db.all(
    'SELECT id, amount FROM market_payouts WHERE user_id = ? AND claimed = 0',
    [userId],
    (err: any, rows: any[]) => {
      if (err) return res.status(500).json({ error: '领取失败' });
      if (!rows || rows.length === 0) return res.json({ success: true, amount: 0, stones: null });

      const total = rows.reduce((sum, r) => sum + (Number(r.amount) || 0), 0);
      const ids = rows.map((r) => r.id);
      const placeholders = ids.map(() => '?').join(',');

      const markClaimed = (): Promise<number> =>
        new Promise((resolve) => {
          db.run(
            `UPDATE market_payouts SET claimed = 1 WHERE user_id = ? AND claimed = 0 AND id IN (${placeholders})`,
            [userId, ...ids],
            function (this: any, err2: any) {
              resolve(err2 ? -1 : this.changes);
            }
          );
        });

      // 全 0 额记录：无需入账，直接标记（避免空转一次 gm_revision++）
      if (!(total > 0)) {
        return markClaimed().then(() => res.json({ success: true, amount: 0, stones: null }));
      }

      // 预检存档存在性（避免在 mutate 内 throw —— updatePlayerSave 的 mutate 无 try/catch，抛错会逸出回调）
      db.get('SELECT user_id FROM saves WHERE user_id = ?', [userId], (preErr: any, preRow: any) => {
        if (preErr) return res.status(500).json({ error: '领取失败' });
        if (!preRow) return res.status(409).json({ error: '尚未同步云存档，无法领取收益' });

        // ① 入账（锁内；sd.player 缺失时兜底建对象，不抛错）
        updatePlayerSave(userId, (sd: any) => {
          if (!sd) return;
          sd.player = sd.player || {};
          sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + total;
        })
          .then((r) => {
            if (!r.ok) return res.status(409).json({ error: '尚未同步云存档，无法领取收益' });

            // ② 守卫式标记
            markClaimed().then((changes) => {
              if (changes > 0) {
                // ③ 成功：读回落库后余额作为回执（客户端可用它对账，兼容上游响应契约）
                db.get('SELECT save_data FROM saves WHERE user_id = ?', [userId], (_e: any, r2: any) => {
                  let stones: number | null = null;
                  try {
                    stones = Number(JSON.parse(r2?.save_data)?.player?.spiritStones) || 0;
                  } catch {
                    stones = null;
                  }
                  res.json({ success: true, amount: total, stones });
                });
                return;
              }
              // ③ 标记失败（DB 错）或被并发抢先（changes=0）→ 回滚入账，保证不吞钱也不重复发
              updatePlayerSave(userId, (sd: any) => {
                if (sd && sd.player) {
                  sd.player.spiritStones = Math.max(0, (Number(sd.player.spiritStones) || 0) - total);
                }
              }).then(() => res.status(409).json({ error: '收益已被领取或入账失败，请刷新后重试' }));
            });
          })
          .catch(() => res.status(500).json({ error: '入账失败，请重试' }));
      });
    }
  );
});


// ── LinuxDo OAuth ──
// P2-1：本项目驱动是回调式 sqlite3，此前这里用 better-sqlite3 的 db.prepare().get()/.run()
// 同步链式写法——Statement.get 无回调不返回行、Statement.run 返回 Statement 而非 {lastInsertRowid}，
// 启用即崩。改为对回调式 API 的 Promise 封装。
function dbGet<T = any>(sql: string, params: any[] = []): Promise<T | undefined> {
  return new Promise((resolve, reject) => {
    db.get(sql, params, (err: any, row: any) => (err ? reject(err) : resolve(row)));
  });
}
function dbAll<T = any>(sql: string, params: any[] = []): Promise<T[]> {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (err: any, rows: any[]) => (err ? reject(err) : resolve(rows || [])));
  });
}
function dbRun(sql: string, params: any[] = []): Promise<{ lastID: number; changes: number }> {
  return new Promise((resolve, reject) => {
    db.run(sql, params, function (this: any, err: any) {
      if (err) reject(err);
      else resolve({ lastID: this.lastID, changes: this.changes });
    });
  });
}
const LINUXDO_AUTH_URL = 'https://connect.linux.do/oauth2/authorize';
const LINUXDO_TOKEN_URL = 'https://connect.linux.do/oauth2/token';
const LINUXDO_USER_URL = 'https://connect.linux.do/api/user';
const LINUXDO_CLIENT_ID = process.env.LINUXDO_CLIENT_ID;
const LINUXDO_CLIENT_SECRET = process.env.LINUXDO_CLIENT_SECRET;

// GET /api/auth/linuxdo → 跳转授权
app.get('/api/auth/linuxdo', (req, res) => {
  if (!LINUXDO_CLIENT_ID) {
    return res.status(500).json({ error: 'LinuxDo OAuth not configured: missing LINUXDO_CLIENT_ID' });
  }
  const protocol = req.headers['x-forwarded-proto'] as string || req.protocol;
  const redirectUri = `${protocol}://${req.get('host')}/api/auth/linuxdo/callback`;
  res.redirect(`${LINUXDO_AUTH_URL}?client_id=${LINUXDO_CLIENT_ID}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=read`);
});

// GET /api/auth/linuxdo/callback?code=xxx
app.get('/api/auth/linuxdo/callback', async (req, res) => {
  const code = req.query.code as string;
  if (!code) return res.status(400).json({ error: '缺少授权码' });

  try {
    const protocol = req.headers['x-forwarded-proto'] as string || req.protocol;
    const redirectUri = `${protocol}://${req.get('host')}/api/auth/linuxdo/callback`;

    // 1. 换 token
    const tokenRes = await fetch(LINUXDO_TOKEN_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ grant_type: 'authorization_code', code, client_id: LINUXDO_CLIENT_ID, client_secret: LINUXDO_CLIENT_SECRET, redirect_uri: redirectUri }),
    });
    const tokenData = await tokenRes.json() as any;
    if (!tokenRes.ok || !tokenData.access_token) return res.status(401).json({ error: 'OAuth 授权失败' });

    // 2. 获取用户信息
    const userRes = await fetch(LINUXDO_USER_URL, { headers: { Authorization: `Bearer ${tokenData.access_token}` } });
    const ldUser = await userRes.json() as any;
    if (!ldUser.username) return res.status(500).json({ error: '获取用户信息失败' });

    // 3. 查找或创建用户（P2-1：回调式 sqlite3 + Promise）
    const linuxdoId = String(ldUser.id);
    const existing = await dbGet('SELECT * FROM users WHERE linuxdo_id = ?', [linuxdoId]);

    let userId: number;
    let username: string;
    if (existing) {
      // 账号重构：封禁账号拒绝 OAuth 登录（与 /api/auth/login 同一口径，封死绕道密码登录的旁路）
      if ((existing as any).banned) {
        return res.status(403).json({ error: '账号已被封禁', code: 'ACCOUNT_BANNED' });
      }
      userId = Number(existing.id);
      username = existing.username;
      onLoginMeta(userId, (existing as any).last_login).catch((e: any) => console.error('login meta error:', e?.message || e));
    } else {
      username = String(ldUser.username);
      const dup = await dbGet('SELECT id FROM users WHERE username = ? AND linuxdo_id IS NULL', [username]);
      if (dup) username = `${username}_ld`;
      const result = await dbRun('INSERT INTO users (username, password_hash, linuxdo_id) VALUES (?, ?, ?)', [username, '', linuxdoId]);
      userId = Number(result.lastID);
    }

    // 4. JWT（P2-1：id 保持数字类型，与常规登录一致，避免 save/排行按 user_id 查不到）
    const token = jwt.sign({ id: userId, username, type: 'access' }, JWT_SECRET_USED, { expiresIn: ACCESS_TOKEN_EXPIRY });
    // 账号重构（§2.3⑤）：OAuth 登录同样建 refresh 会话行并回传 refreshToken——
    // 原先只发 access，OAuth 用户 access 到期必被踢；现与常规登录同享 180 天滑动续登。
    let refreshToken = '';
    try {
      refreshToken = await issueRefreshSession(userId, req.headers['user-agent']);
    } catch (e) {
      console.error('LinuxDo refresh session error:', e); // 尽力而为：失败时仅退化为本来的 access-only 行为
    }
    const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:5173';
    // P2-1：postMessage 限定目标 origin，不再用 '*'
    let frontendOrigin = frontendUrl;
    try { frontendOrigin = new URL(frontendUrl).origin; } catch { /* 解析失败保底原值 */ }
    res.send(`<!DOCTYPE html><html><head><script>window.opener?(window.opener.postMessage({type:'linuxdo-auth',token:'${token}',refreshToken:'${refreshToken}',username:'${username}'},'${frontendOrigin}'),window.close()):window.location.replace('${frontendUrl}?token=${token}&refreshToken=${encodeURIComponent(refreshToken)}&username=${encodeURIComponent(username)}')</script></head><body>登录成功，正在跳转...</body></html>`);
  } catch (e: any) {
    // P2-1：不再把内部错误 e.message 回显给客户端
    console.error('LinuxDo OAuth error:', e?.stack || e);
    res.status(500).json({ error: 'OAuth 登录失败，请稍后再试' });
  }
});

// ─────────────────────────────────────────────────────────
// 站内邮件（E2）：表建在文件头 db 初始化段（mail 表）。
// 灵石账本位置：saves.save_data JSON → player.spiritStones（rankings.spirit_stones 只是同步副本），
// 领取附件复用 updatePlayerSave：其内部自带 saveLock 读改写互斥 + gm_revision++（触发前端拉新档）+ 排行自动同步。
// ─────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────
// Y 系列（Y5 回归奖励 / Y6 称号 / Y2 每日任务）
// ─────────────────────────────────────────────────────────

// [ycore] Y 系列纯逻辑核心（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
// ── Y5 回归判定与收益倍率 ──
const DAY_MS = 24 * 60 * 60 * 1000;
const RETURN_GAP_MS = 3 * DAY_MS;   // 距上次登录 ≥3 天 → 回归
const RETURN_BUFF_MS = 3 * DAY_MS;  // 回归 buff 时长 3 天（yl-feature-design.md §4.6 口径）
const RETURN_MAIL_STONES = 5000;    // 回归邮件附灵石
const BUFF_MULTIPLIER = 1.5;        // buff 期间打坐/历练收益倍率
function isReturnLogin(lastLoginMs: number | null, nowMs: number, gapMs: number = RETURN_GAP_MS): boolean {
  if (lastLoginMs == null || !Number.isFinite(lastLoginMs)) return false;
  return nowMs - lastLoginMs >= gapMs; // 恰好 ≥gap 即回归；时钟回拨（负差值）不误判
}
function returnBuffMultiplier(buffUntilMs: number | null | undefined, nowMs: number): number {
  return buffUntilMs != null && nowMs < Number(buffUntilMs) ? BUFF_MULTIPLIER : 1;
}
// 收益叠乘：多倍率相乘后四舍五入钳 6 位小数，防浮点尾巴进存档（floor 会把 33.3×1.5=49.94999…9 截成 49.949999）
function applyYield(base: number, ...mults: number[]): number {
  return Math.round(mults.reduce((acc, m) => acc * m, base) * 1e6) / 1e6;
}
// sqlite 时间文本 → ms（ISO 直接解析；'YYYY-MM-DD HH:MM:SS' 视为 UTC 补 Z）；非法/空 → null
function parseDbTimeMs(v: unknown): number | null {
  if (typeof v !== 'string' || !v) return null;
  const t = Date.parse(v.includes('T') ? v : v.replace(' ', 'T') + 'Z');
  return Number.isFinite(t) ? t : null;
}
// ── Y2 每日任务：任务池 / 差值结算 / 活跃度档位（结算埋点=POST /api/save 存档差值，全部服务端）──
// 客户端权威存档架构下，打坐/历练/战斗结算都在客户端跑，服务端唯一可见的结算汇聚点是存档上传：
// statistics.killCount 仅在战斗胜利 +1、statistics.adventureCount 每次历练 +1（assets js 锚点已核）、
// playTime 为客户端累计在线毫秒（打坐时长的服务端可见代理）、灵石消费=spiritStones 上传差值下降部分。
// T9 0.8.8：18 项活跃度来源（A 核心 / B 进阶 / C 社交 / D 休闲），名义满分 330。
//   每条 { key, name, group, points, limit, target, unit }：
//     points = 单次分值；limit = 当日计分次数上限（points×limit = 该项满分）；
//     target = 单次触发阈值（读时计算时 progress 除以它取整，与 legacy 任务同语义）。
//   ★ legacy 4 键（meditate/kill/adventure/spend）键名与 target 逐字不变 ——
//     `tickDailyQuests` 仍只喂这 4 键，Y19 成就口径须 byte 级一致（见文件尾 §Y19）。
const QUEST_DEFS = [
  // ── A 组 · 核心（5 项，名义 110）──
  { key: 'signin',       name: '仙途签到',     group: 'A', points: 10, limit: 1, target: 1,              unit: '次' },
  { key: 'meditate',     name: '打坐修心',     group: 'A', points: 5,  limit: 6, target: 20 * 60 * 1000,  unit: '分钟' },
  { key: 'kill',         name: '斩妖除魔',     group: 'A', points: 5,  limit: 4, target: 5,              unit: '场' },
  { key: 'adventure',    name: '历练问道',     group: 'A', points: 6,  limit: 5, target: 4,              unit: '次' },
  { key: 'expgain',      name: '修为精进',     group: 'A', points: 5,  limit: 4, target: 1,              unit: '次' },
  // ── B 组 · 进阶（5 项，名义 86）──
  { key: 'dungeon',      name: '秘境探幽',     group: 'B', points: 8,  limit: 3, target: 1,              unit: '次' },
  { key: 'alchemy',      name: '丹火不熄',     group: 'B', points: 5,  limit: 3, target: 1,              unit: '次' },
  { key: 'farm',         name: '灵田躬耕',     group: 'B', points: 4,  limit: 4, target: 1,              unit: '次' },
  { key: 'pet',          name: '妖灵相伴',     group: 'B', points: 4,  limit: 4, target: 1,              unit: '次' },
  { key: 'grotto',       name: '洞府营造',     group: 'B', points: 5,  limit: 3, target: 1,              unit: '次' },
  // ── C 组 · 社交（5 项，名义 80）──
  { key: 'sect',         name: '仙盟同心',     group: 'C', points: 7,  limit: 3, target: 1,              unit: '次' },
  { key: 'arena',        name: '擂台论道',     group: 'C', points: 7,  limit: 3, target: 1,              unit: '次' },
  { key: 'mentor',       name: '师徒相授',     group: 'C', points: 7,  limit: 2, target: 1,              unit: '次' },
  { key: 'bounty',       name: '悬赏缉凶',     group: 'C', points: 5,  limit: 3, target: 1,              unit: '次' },
  { key: 'chat',         name: '江湖留名',     group: 'C', points: 3,  limit: 3, target: 1,              unit: '次' },
  // ── D 组 · 休闲（3 项，名义 54）──
  { key: 'fun',          name: '行乐有道',     group: 'D', points: 5,  limit: 4, target: 1,              unit: '次' },
  { key: 'lottery',      name: '仙缘奇遇',     group: 'D', points: 4,  limit: 4, target: 1,              unit: '次' },
  { key: 'spend',        name: '财货通流',     group: 'D', points: 6,  limit: 3, target: 10000,          unit: '灵石' },
];
// 名义满分（points×limit 之和）= 110+86+80+54 = 330；P0 降级（丹火/灵田收获）后见 T9 §7.3
const ACTIVITY_MAX = 330;
// 分组元数据（客户端分组折叠用；顺序 = 展示顺序）
const QUEST_GROUPS: Record<string, string> = { A: '核心', B: '进阶', C: '社交', D: '休闲' };
// 当日依赖「行/读时」双口径的 legacy 4 键（tickDailyQuests 会写行，读时应与之取大）
const LEGACY_QUEST_KEYS = ['meditate', 'kill', 'adventure', 'spend'];
const CHEST_TIERS = [30, 60, 100, 150, 200, 260]; // T9 0.8.8：活跃度六档宝箱（门槛=活跃度）
// T9 0.8.8：灵石 base 表（实际发放 = floor(base × ylrf(realm))，见 T4 的 ylrf()）
//   旧四档固定值（25/50/75/100 → 2500/7500/15000/30000，合计 55,000）按「低境界不砍、
//   高境界按境界补齐」原则改为六档 base；炼气期合计 ≈ 54,664（与旧值基本持平）。
const CHEST_REWARDS: Record<number, number> = { 30: 1000, 60: 2000, 100: 4000, 150: 7000, 200: 11000, 260: 16000 };
// 每档附带的「修为打坐等效次数」与「抽奖券」数（T9 §4.2）
//   P0 发奖通道：insertMail 只支持灵石附件 ⇒ 修为/券按 §7.4「零风险降级」折算成灵石一并发放，
//   邮件正文说明折算比例；折算基准 = 1 次打坐等效 ≈ 12 灵石（保守低估值，避免新 faucet 超发）。
const CHEST_EXP_TIMES: Record<number, number> = { 30: 60, 60: 120, 100: 240, 150: 360, 200: 480, 260: 600 };
const CHEST_TICKETS: Record<number, number> = { 30: 0, 60: 1, 100: 2, 150: 3, 200: 5, 260: 8 };
const CHEST_EXP_TO_STONE = 12; // 1 打坐等效次 → 12 灵石（P0 折算比）
function chestKey(tier: number): string { return 'chest_' + tier; }
// T9 0.8.8：周里程碑领取幂等表（week 列实际存 claimKey：周档='w'+week+'_'+tier，月档='m'+YYYY-MM+'_'+tier）
db.run('CREATE TABLE IF NOT EXISTS activity_milestones (user_id INTEGER, week TEXT, tier INTEGER, claimed_at INTEGER, UNIQUE(user_id, week, tier))');
// T9 0.8.8：境界奖励倍率 YLRF（= 既有 rainRealmFactor，与「数值表-T11」§4.3 的
//   rainHourlyStones 同源：i<=0 → 4/3；i>=1 → 2i+1（筑基 3 / 金丹 5 / 元婴 7 / 化神 9 /
//   合道 11 / 长生 13）。注意与 sameRealmMult 的 1.5^idx 指数曲线不同，本函数专供 T9 奖励，
//   勿改 sameRealmMult）。T9_REALM_ORDER 与 ECON_REALM_ORDER 同源同序。
const T9_REALM_ORDER = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];
// ★ T9 活跃度奖励倍率 = 既有 rainRealmFactor(i)（:4921 同源，勿自造曲线）：
//     i <= 0 → 4/3（炼气）；i >= 1 → 2*i+1（筑基 3 / 金丹 5 / … / 长生 13）。
//     与「数值表-T11」§4.3 rainHourlyStones 完全同源，保证 T9 奖励与挂机时薪口径一致。
function ylrf(realm: unknown): number {
  const idx = Math.max(0, T9_REALM_ORDER.indexOf(String(realm || '')));
  return idx <= 0 ? 4 / 3 : 2 * idx + 1;
}
// 与 ylrf 同源的「按境界序 idx」入口（内部直调，避免字符串往返）
function ylrfIdx(idx: number): number {
  const i = Math.max(0, Math.floor(Number(idx) || 0));
  return i <= 0 ? 4 / 3 : 2 * i + 1;
}
// 北京时区「周一 0 点」对应的 YYYY-MM-DD（与 bjDate 同风格；ISO 周一=1，周日=0 ⇒ 归一到周一）
function bjWeekStart(ms: number): string {
  const d = new Date(ms + 8 * 60 * 60 * 1000);
  const dow = (d.getUTCDay() + 6) % 7;            // 周一=0 … 周日=6
  const monday = new Date(d.getTime() - dow * 86400000);
  return monday.toISOString().slice(0, 10);
}
// 周里程碑档位（门槛 = 周累计活跃度；wbase = 灵石 base；wexp = 打坐等效；wtk = 抽奖券）
//   ★ R-028（econ2 环）：3 档 → 5 档（500/1000/1500/1900/2310），灵石 base 总额 125k → 160k/周。
//     顶端 2310 = ACTIVITY_MAX(330) × 7（周活跃度打满）；wexp = wbase/100；与客户端 YlxwQMile 同表。
//   ★ R-013b：传承石移到**最高档 2310**（满活跃度才给），并改发**实物**（背包通道 legacyStoneItem），
//     不再折算灵石。原 2310 的展示串 '仙品道具+称号' 下移 1900 档保留（见 报告_r013b.md §4）。
const WEEK_MILESTONES: Array<{ tier: number; wbase: number; wexp: number; wtk: number; legacy: string }> = [
  { tier: 500,  wbase: 10000, wexp: 100, wtk: 4,  legacy: '' },
  { tier: 1000, wbase: 20000, wexp: 200, wtk: 9,  legacy: '' },
  { tier: 1500, wbase: 30000, wexp: 300, wtk: 14, legacy: '' },
  { tier: 1900, wbase: 40000, wexp: 400, wtk: 21, legacy: '仙品道具+称号' },
  { tier: 2310, wbase: 60000, wexp: 600, wtk: 30, legacy: '传承石' },
];
const MILE_MONTHLY_TIER = 2310; // 该档的 legacy 额外奖励（传承石）按「月」限领一次，其余按周
// R-013b：传承石**实物**发放。名称/类型/稀有度与客户端 yl_r013_ext.py 的 YlxwInhStoneItem 逐字对齐
//   （name='传承石' / type='材料' / rarity='仙品' / isEquippable=false）⇒ 交易行上架、使用 +1 传承等级
//   两条客户端链路天然可用。发放走 updatePlayerSave 背包通道（同宗门丹药 sectPillItem 范式）。
const LEGACY_STONE_NAME = '传承石';
function legacyStoneItem(): any {
  return {
    id: `inh-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`,
    name: LEGACY_STONE_NAME,
    type: '材料',
    description: '先辈传承凝结的灵石，使用后传承等级 +1，亦可于交易行转售。',
    quantity: 1,
    rarity: '仙品',
    effect: {},
    permanentEffect: {},
    isEquippable: false,
    level: 0,
  };
}

// T9 0.8.8：周里程碑幂等表（UNIQUE(user_id,week,tier)）—— 建表语句在下方 DDL 区执行
function weekMonthKey(week: string): string { return week.slice(0, 7); } // YYYY-MM
// 每日重置基准：北京时区 YYYY-MM-DD（UTC+8，北京 0 点跨日）
function bjDate(ms: number): string {
  return new Date(ms + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);
}
interface StatCounters { killCount: number; adventureCount: number; playTimeMs: number; spiritStones: number; exp: number; secretRealmCount: number; grottoLevel: number; grottoSpeedup: number; }
function extractCounters(saveData: any): StatCounters {
  const p = saveData?.player ?? {};
  return {
    killCount: Number(p.statistics?.killCount) || 0,
    adventureCount: Number(p.statistics?.adventureCount) || 0,
    playTimeMs: Number(p.playTime) || 0,
    spiritStones: Number(p.spiritStones) || 0,
    exp: Number(p.exp) || 0, // Y15：修为进统计差值（Y2 任务不消费此字段，向后兼容）
    secretRealmCount: Number(p.statistics?.secretRealmCount) || 0, // DG：秘境经典门计数（R5 锚点核实）
    // T9 0.8.8 第 10 项「洞府营造」：洞府等级 + 当日加速次数（存档差值口径）
    grottoLevel: Number(p.grotto?.level) || 0,
    grottoSpeedup: Number(p.grotto?.dailySpeedupCount) || 0,
  };
}
function zeroCounters(): StatCounters { return { killCount: 0, adventureCount: 0, playTimeMs: 0, spiritStones: 0, exp: 0, secretRealmCount: 0, grottoLevel: 0, grottoSpeedup: 0 }; }
// 上传差值 → 各任务增量。计数回退（改档/多端旧档）按 0 计不倒扣；余额上升不算消费。
function computeQuestDeltas(prev: StatCounters, next: StatCounters): Record<string, number> {
  const up = (a: number, b: number) => (b > a ? b - a : 0);
  return {
    meditate: up(prev.playTimeMs, next.playTimeMs),
    kill: up(prev.killCount, next.killCount),
    adventure: up(prev.adventureCount, next.adventureCount),
    spend: prev.spiritStones - next.spiritStones > 0 ? prev.spiritStones - next.spiritStones : 0,
  };
}
// 进度推进（纯）：封顶不溢出，达标即 done；SQL 侧用单语句原子 UPDATE 镜像同一语义（MIN/CASE）防并发丢更新
function nextProgress(progress: number, delta: number, target: number): { progress: number; done: boolean } {
  const np = Math.min(target, (Number(progress) || 0) + Math.max(0, Number(delta) || 0));
  return { progress: np, done: np >= target };
}
// 活跃度 = 已完成任务分值和；宝箱按档位解锁
function activityFromQuests(quests: Array<{ key: string; done: boolean | number }>): number {
  let act = 0;
  for (const def of QUEST_DEFS) {
    const q = quests.find((x) => x.key === def.key);
    if (q && (q.done === true || q.done === 1)) act += def.points;
  }
  return act;
}
function isChestUnlocked(activity: number, tier: number): boolean { return activity >= tier; }

// ─────────────────────────────────────────────────────────────────────────────
// T9 0.8.8 · 读时计算核心：collectDailyActivity(userId, date)
//   对 18 项来源各跑一条当日取值，合成 { items, activity }。**不写 daily_quests 行**
//   （14 个新项目刻意不落行，保 Y19 口径 4 行/日 byte 级不变，见 §7.6）。
//   legacy 4 键（meditate/kill/adventure/spend）取 max(行值, 读时值)：tick 会写行，
//   但读时口径更实时（玩家同日内先大后小可能 tick 只记到部分），取大不漏分。
//
//   ⚠️ 时间戳三口径（逐表核对，勿统一假设）：
//     ① date TEXT（北京日）：stats_daily / daily_quests / dungeon_tracker / fun_daily /
//        farm_daily_care / sect_task_claims / pet_play_log / mentor_greetings / teach_log
//     ② INTEGER ms epoch：arena_battles.resolved_at / bounties.finished_at
//     ③ DATETIME UTC 文本：chat_messages / lottery_history / users.last_login / sect_ledger /
//        pet_care_log / alchemy.mature_at(INTEGER) —— 需换算北京日
// ─────────────────────────────────────────────────────────────────────────────

// 北京日 → [当日 0 点 ms, 次日 0 点 ms)，供 INTEGER/DATETIME 列做区间过滤
function bjDayRangeMs(date: string): [number, number] {
  const start = Date.parse(date + 'T00:00:00+08:00');
  return [start, start + 86400000];
}
// DATETIME(UTC 文本) → 北京日 YYYY-MM-DD：先按 UTC 解析，再 +8h 取日
function bjDateOfUtcText(s: unknown): string | null {
  if (!s) return null;
  const t = Date.parse(String(s).includes('T') ? String(s) : String(s).replace(' ', 'T') + 'Z');
  if (!Number.isFinite(t)) return null;
  return bjDate(t);
}

async function collectDailyActivity(userId: number, date: string): Promise<{ items: Array<{ key: string; progress: number; done: boolean; points: number }>; activity: number }> {
  const [d0, d1] = bjDayRangeMs(date);
  const rows = await Promise.all([
    // 1 仙途签到：users.last_login（UTC DATETIME 文本）换算北京日 = 今日
    dbGet('SELECT last_login AS v FROM users WHERE id = ?', [userId]).catch(() => null),
    // 2 打坐修心：stats_daily.minutes（date）
    dbGet('SELECT minutes AS v FROM stats_daily WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 3 斩妖除魔：stats_daily.kills（date）
    dbGet('SELECT kills AS v FROM stats_daily WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 4 历练问道：daily_quests.progress（legacy 行）
    dbGet("SELECT progress AS v, done AS d FROM daily_quests WHERE user_id = ? AND date = ? AND quest_key = 'adventure'", [userId, date]).catch(() => null),
    // 5 修为精进：stats_daily.exp_gain（date），每 25% 当前层算 1 次 —— 读时无境界层基数，
    //   改用「exp_gain 每 12.5 万算 1 次」的保守代理（P0；P1 可注入 realm/level 精算）
    dbGet('SELECT exp_gain AS v FROM stats_daily WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 6 秘境探幽：dungeon_tracker.count（date）
    dbGet('SELECT count AS v FROM dungeon_tracker WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 7 丹火不熄：alchemy.mature_at（INTEGER ms）落在当日（P0 近似：同 slot 覆盖只算最后一次，接受）
    dbGet('SELECT COUNT(*) AS v FROM alchemy WHERE player_id = ? AND mature_at >= ? AND mature_at < ?', [userId, d0, d1]).catch(() => null),
    // 8 灵田躬耕：farm_daily_care（date，tended/boosted 计数）；spirit_farm 无收获时间列 ⇒ P0 只算照料
    dbGet('SELECT COALESCE(SUM(tended),0) + COALESCE(SUM(boosted),0) AS v FROM farm_daily_care WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 9 妖灵相伴：pet_play_log.times（date）+ pet_care_log.created_at（UTC DATETIME）
    dbGet('SELECT COALESCE(SUM(times),0) AS v FROM pet_play_log WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    dbGet('SELECT COUNT(*) AS v FROM pet_care_log WHERE player_id = ? AND created_at >= ? AND created_at < ?', [userId, new Date(d0).toISOString().slice(0, 19).replace('T', ' '), new Date(d1).toISOString().slice(0, 19).replace('T', ' ')]).catch(() => null),
    // 10 洞府营造：由存档差值统计（tickGrotto，见下方经济埋点）；读时无法回溯 ⇒ 用 stats_daily 无对应列，
    //    改由 grotto 计数器（在 extractCounters 扩展后经 tickDailyQuests 之外的独立计数）——
    //    P0 简化：读 daily_quests 无键 ⇒ 恒 0，改由 tick 侧单独累进（见 T9 §7.2 #10 注）。
    Promise.resolve(null),
    // 11 仙盟同心：sect_task_claims.date + sect_ledger.created_at（UTC DATETIME）
    dbGet('SELECT COUNT(*) AS v FROM sect_task_claims WHERE user_id = ? AND date = ?', [userId, date]).catch(() => null),
    dbGet('SELECT COUNT(*) AS v FROM sect_ledger WHERE user_id = ? AND created_at >= ? AND created_at < ?', [userId, new Date(d0).toISOString().slice(0, 19).replace('T', ' '), new Date(d1).toISOString().slice(0, 19).replace('T', ' ')]).catch(() => null),
    // 12 擂台论道（M=只计论剑，L=甲北京日切）：arena_battles.resolved_at（INTEGER ms）+ status='accepted'
    dbGet("SELECT COUNT(*) AS v FROM arena_battles WHERE (challenger_id = ? OR defender_id = ?) AND status = 'accepted' AND resolved_at >= ? AND resolved_at < ?", [userId, userId, d0, d1]).catch(() => null),
    // 13 师徒相授：mentor_greetings.date + teach_log.date（均北京日）
    dbGet('SELECT COUNT(*) AS v FROM mentor_greetings WHERE (mentor_id = ? OR apprentice_id = ?) AND date = ?', [userId, userId, date]).catch(() => null),
    dbGet('SELECT COUNT(*) AS v FROM teach_log WHERE user_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 14 悬赏缉凶：bounties.finished_at（INTEGER ms）+ status='done'
    dbGet("SELECT COUNT(*) AS v FROM bounties WHERE (poster_id = ? OR acceptor_id = ?) AND status = 'done' AND finished_at >= ? AND finished_at < ?", [userId, userId, d0, d1]).catch(() => null),
    // 15 江湖留名：chat_messages（无 user_id ⇒ 按 username 匹配，created_at UTC）+ chronicle_praise.created_at（INTEGER ms）
    dbGet('SELECT COUNT(*) AS v FROM chronicle_praise WHERE user_id = ? AND created_at >= ? AND created_at < ?', [userId, d0, d1]).catch(() => null),
    // 16 行乐有道：fun_daily（date + kind + count）
    dbGet('SELECT COALESCE(SUM(count),0) AS v FROM fun_daily WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 17 仙缘奇遇：lottery_history.created_at（UTC DATETIME）
    dbGet('SELECT COUNT(*) AS v FROM lottery_history WHERE user_id = ? AND created_at >= ? AND created_at < ?', [userId, new Date(d0).toISOString().slice(0, 19).replace('T', ' '), new Date(d1).toISOString().slice(0, 19).replace('T', ' ')]).catch(() => null),
    // 18 财货通流：daily_quests.progress（legacy 'spend' 行）
    dbGet("SELECT progress AS v, done AS d FROM daily_quests WHERE user_id = ? AND date = ? AND quest_key = 'spend'", [userId, date]).catch(() => null),
    // 15b（用户名匹配聊天次数）：单查 users.username → chat_messages
    dbGet('SELECT username AS v FROM users WHERE id = ?', [userId]).catch(() => null),
  ]);
  // ★ 索引映射用**具名解构**（不用 rows[i] 下标算术，防错位；Promise.all 顺序 = 上方数组顺序）
  const [
    rLogin, rMed, rKill, rAdv, rExp, rDun, rAlc, rFarm, rPetPlay, rPetCare,
    _rGrotto, rSectClaim, rSectLedger, rArena, rMentorGreet, rTeach, rBounty,
    rPraise, rFun, rLottery, rSpend, rUname,
  ] = rows as any[];
  const num = (r: any) => (r && Number.isFinite(Number(r.v)) ? Number(r.v) : 0);
  const utcLo = new Date(d0).toISOString().slice(0, 19).replace('T', ' ');
  const utcHi = new Date(d1).toISOString().slice(0, 19).replace('T', ' ');

  // 1 签到：last_login 换算北京日 == date
  const signN = bjDateOfUtcText(rLogin && rLogin.v) === date ? 1 : 0;
  // 9 妖灵相伴 = 嬉戏次数 + 照料次数
  const petN = num(rPetPlay) + num(rPetCare);
  // 11 仙盟同心 = 任务领取数 + 捐献笔数
  const sectN = num(rSectClaim) + num(rSectLedger);
  // 13 师徒相授 = 问候 + 传功
  const mentorN = num(rMentorGreet) + num(rTeach);
  // 15 江湖留名 = 传阅赞 + 当日世界聊天条数（chat_messages 无 user_id ⇒ 按 username）
  let chatN = num(rPraise);
  const uname = rUname && rUname.v ? String(rUname.v) : '';
  if (uname) {
    const cm = await dbGet('SELECT COUNT(*) AS v FROM chat_messages WHERE username = ? AND created_at >= ? AND created_at < ?',
      [uname, utcLo, utcHi]).catch(() => null);
    chatN += num(cm);
  }

  // ★ P0 修复（2026-09-29）：`grottoN` 此前被下面 raw 映射引用却**从未声明** ⇒
  //   collectDailyActivity 每次调用都在 raw 求值时抛 ReferenceError ⇒ 其 Promise **恒 reject**
  //   ⇒ /api/quest/summary 恒 500、/api/quest/chest 恒 500、周里程碑恒 0（整条 T9 活跃度链路失效）。
  //   该缺陷此前被更早的 `quests: questList` ReferenceError（单请求崩进程）**掩盖**，
  //   修掉那个崩溃后才暴露出来（实测：修 A 后 /quest/summary 由「进程 exit」变为「500」）。
  //   口径与上方第 10 项查询的注释一致：P0 简化 ⇒ 恒 0
  //   （stats_daily 无 grotto 列、读时无法回溯；tick 侧累进列未落库）。
  //   本项在 QUEST_DEFS 中**保留**（18 项结构与 ACTIVITY_MAX=330 不变），只是不产生积分。
  const grottoN = 0;

  // 读时原始量（单位 = 项目自述的「次/分钟/场/灵石」），下按 target 折算成计分次数
  const raw: Record<string, number> = {
    signin: signN,
    meditate: num(rMed) * 60000,                          // 分钟 → 毫秒（def.target 为毫秒口径）
    kill: num(rKill),                                     // 场
    adventure: num(rAdv),                                 // 次（legacy 行 progress 已是「次」口径）
    expgain: Math.floor(num(rExp) / 125000),              // 修为增益 / 12.5 万 = 1 次（P0 代理）
    dungeon: num(rDun),
    alchemy: num(rAlc),
    farm: num(rFarm),
    pet: petN,
    grotto: grottoN,                                      // ★ 洞府营造（存档直读，见下）
    sect: sectN,
    arena: num(rArena),                                   // ★ M=只计论剑 + status='accepted'
    mentor: mentorN,
    bounty: num(rBounty),
    chat: chatN,
    fun: num(rFun),
    lottery: num(rLottery),
    spend: num(rSpend),                                   // 灵石
  };

  const items: Array<{ key: string; progress: number; done: boolean; points: number }> = [];
  let activity = 0;
  for (const def of QUEST_DEFS) {
    const qty = Math.max(0, Number(raw[def.key]) || 0);
    const times = Math.min(def.limit, Math.floor(qty / Math.max(1, def.target)));
    const pts = Math.min(def.limit, Math.max(0, times)) * def.points;
    items.push({ key: def.key, progress: qty, done: times > 0, points: pts });
    activity += pts;
  }
  return { items, activity: Math.min(ACTIVITY_MAX, activity) };
}

// 周活跃度 = 该周 7 日 collectDailyActivity 之和（日上限 330 ⇒ 周上限 2310）
async function collectWeeklyActivity(userId: number, weekStart: string): Promise<number> {
  const tasks: Array<Promise<number>> = [];
  const base = Date.parse(weekStart + 'T00:00:00+08:00');
  for (let i = 0; i < 7; i++) {
    const day = bjDate(base + i * 86400000);
    tasks.push(collectDailyActivity(userId, day).then((r) => r.activity).catch(() => 0));
  }
  const all = await Promise.all(tasks);
  return all.reduce((a, b) => a + b, 0);
}
// ── Y6 称号：授予判定（入库幂等靠 player_titles 主键，这里只出"该不该授"的纯判定）──
function shouldGrantAchievementTitle(achievementCount: number): boolean { return achievementCount >= 1; }
function shouldGrantRankTitle(topUserId: number, boardSize: number, userId: number, minBoardSize: number = 2): boolean {
  return boardSize >= minBoardSize && topUserId === userId; // 榜上至少 2 人才算"榜首"
}
// ── Y4 渡劫天劫：境界数值表（客户端 assets js Cs 表同源镜像，勿凭记忆改数）──
// v26f 修为曲线：与客户端 Cs.maxExpBase 逐档同源；本轮修为难度再×10（6000→60000 … 45250000→452500000）
const TRIB_REALM_BASES: Record<string, { maxExpBase: number; baseAttack: number; baseDefense: number; baseMaxHp: number }> = {
  '炼气期': { maxExpBase: 60000, baseAttack: 10, baseDefense: 5, baseMaxHp: 100 },
  '筑基期': { maxExpBase: 390000, baseAttack: 25, baseDefense: 12, baseMaxHp: 250 },
  '金丹期': { maxExpBase: 1521000, baseAttack: 50, baseDefense: 25, baseMaxHp: 625 },
  '元婴期': { maxExpBase: 6592000, baseAttack: 125, baseDefense: 62, baseMaxHp: 1250 },
  '化神期': { maxExpBase: 26775000, baseAttack: 312, baseDefense: 156, baseMaxHp: 3125 },
  '合道期': { maxExpBase: 104430000, baseAttack: 781, baseDefense: 390, baseMaxHp: 7812 },
  '长生境': { maxExpBase: 452500000, baseAttack: 1953, baseDefense: 976, baseMaxHp: 19531 },
};
const TRIB_LEVEL_EXP_FACTOR = 0.24; // 客户端 ad(realm,lv)=floor(maxExpBase*(1+(lv-1)*0.24)) 同源
// 修为上限（客户端同源公式）：当前境界第 lv 层的修为槽——天劫的"修为门槛"= 修为值须修满此槽
function realmMaxExp(realm: string, realmLevel: number): number {
  const base = TRIB_REALM_BASES[realm]?.maxExpBase ?? 60000;
  const lv = Math.min(9, Math.max(1, Math.floor(Number(realmLevel) || 1)));
  return Math.floor(base * (1 + (lv - 1) * TRIB_LEVEL_EXP_FACTOR));
}
const TRIBULATION_FAIL_COOLDOWN_MS = 10 * 60 * 1000; // 渡劫失败冷却 10 分钟
const TRIB_ENEMY_SCALE = { attack: 2, defense: 2, hp: 1.5 }; // 天劫使者=目标境界基础属性×系数（本次定档，可调）
// 天劫使者战力只按目标境界缩放（不随玩家变强变弱），数值是否合理由常量统一调
function tribulationEnemy(targetRealm: string): { attack: number; defense: number; maxHp: number } {
  const b = TRIB_REALM_BASES[targetRealm] || TRIB_REALM_BASES['炼气期'];
  return {
    attack: Math.floor(b.baseAttack * TRIB_ENEMY_SCALE.attack),
    defense: Math.floor(b.baseDefense * TRIB_ENEMY_SCALE.defense),
    maxHp: Math.floor(b.baseMaxHp * TRIB_ENEMY_SCALE.hp),
  };
}
// 天劫战斗（纯函数，rng 注入便于单测）：玩家先手，伤害=max(1, 攻×随机0.85~1.15 − 敌防)；
// TRIB_MAX_ROUNDS 回合未分胜负按余血比例判（≥ 玩家胜，平局仁慈判胜）
const TRIB_MAX_ROUNDS = 50;
function simulateTribulationBattle(
  player: { attack: number; defense: number; maxHp: number },
  enemy: { attack: number; defense: number; maxHp: number },
  rng: () => number = Math.random
): { win: boolean; rounds: number[]; playerHpLeft: number; enemyHpLeft: number } {
  const pMax = Math.max(1, Math.floor(Number(player.maxHp) || 0));
  const eMax = Math.max(1, Math.floor(Number(enemy.maxHp) || 0));
  let php = pMax;
  let ehp = eMax;
  const patk = Math.max(0, Math.floor(Number(player.attack) || 0));
  const pdef = Math.max(0, Math.floor(Number(player.defense) || 0));
  const eatk = Math.max(0, Math.floor(Number(enemy.attack) || 0));
  const edef = Math.max(0, Math.floor(Number(enemy.defense) || 0));
  const rounds: number[] = [];
  for (let i = 0; i < TRIB_MAX_ROUNDS; i++) {
    const pdmg = Math.max(1, Math.round(patk * (0.85 + rng() * 0.3)) - edef);
    ehp -= pdmg;
    rounds.push(pdmg);
    if (ehp <= 0) return { win: true, rounds, playerHpLeft: php, enemyHpLeft: 0 };
    const edmg = Math.max(1, Math.round(eatk * (0.85 + rng() * 0.3)) - pdef);
    php -= edmg;
    if (php <= 0) return { win: false, rounds, playerHpLeft: 0, enemyHpLeft: ehp };
  }
  return { win: php / pMax >= ehp / eMax, rounds, playerHpLeft: Math.max(0, php), enemyHpLeft: Math.max(0, ehp) };
}
// ── Y14 赛季：season=北京时区 YYYY-MM（每月 1 号跨季）；跨月惰性归档 ──
function seasonId(ms: number): string {
  return new Date(ms + 8 * 60 * 60 * 1000).toISOString().slice(0, 7);
}
function prevSeasonId(cur: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(cur);
  if (!m) return cur;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  return mo === 1 ? `${y - 1}-12` : `${y}-${String(mo - 1).padStart(2, '0')}`;
}
const SEASON_TOP_N = 3;
const SEASON_REWARDS: Array<{ rank: number; title: string; source: string; stones: number }> = [
  { rank: 1, title: '赛季魁首', source: 'season_top1', stones: 3000 },
  { rank: 2, title: '赛季榜眼', source: 'season_top2', stones: 2000 },
  { rank: 3, title: '赛季探花', source: 'season_top3', stones: 1000 },
];
function seasonRewardForRank(rank: number): { title: string; source: string; stones: number } | null {
  return SEASON_REWARDS.find((r) => r.rank === rank) || null;
}
// 归档判定（纯）：foreign=已标注过非当前赛季的行数>0 → 归档+发奖；首部署全 NULL 只重打标记不发奖
function shouldArchiveSeason(foreignCount: number): boolean { return foreignCount > 0; }
// ── Y15 统计面板：四维日聚合差值（埋点同 Y2=POST /api/save 存档差值；负差钳 0 防回档/多端旧档倒扣）──
const STATS_DAYS = 30; // 曲线窗口（近 30 日）
interface StatsDelta { exp: number; silver: number; kills: number; minutes: number; }
function computeStatsDeltas(prev: StatCounters, next: StatCounters): StatsDelta {
  const up = (a: number, b: number) => (b > a ? b - a : 0);
  return {
    exp: up(prev.exp, next.exp),                      // 升层/突破瞬间槽位结转段服务端不可见（该段钳 0，见报告边界）
    silver: up(prev.spiritStones, next.spiritStones), // 净上升=获取（含邮件/宝箱/GM 入账）；下降=消费不计
    kills: up(prev.killCount, next.killCount),
    minutes: Math.floor(up(prev.playTimeMs, next.playTimeMs) / 60000), // 在线毫秒差 → 分钟（取整丢 <1min 尾巴）
  };
}
function statsDeltaHasAny(d: StatsDelta): boolean { return d.exp > 0 || d.silver > 0 || d.kills > 0 || d.minutes > 0; }
// 近 N 日序列（纯）：缺日补零；date=北京时区 YYYY-MM-DD（与 daily_quests 同口径跨日）
function buildStatsSeries(
  rows: Array<{ date: string; exp_gain?: number; silver_gain?: number; kills?: number; minutes?: number }>,
  nowMs: number,
  days: number = STATS_DAYS
): Array<{ date: string; exp: number; silver: number; kills: number; minutes: number }> {
  const map: Record<string, any> = {};
  for (const r of rows || []) if (r && r.date) map[String(r.date)] = r;
  const out: Array<{ date: string; exp: number; silver: number; kills: number; minutes: number }> = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = bjDate(nowMs - i * DAY_MS);
    const r = map[d];
    out.push({
      date: d,
      exp: Math.max(0, Math.floor(Number(r?.exp_gain) || 0)),
      silver: Math.max(0, Math.floor(Number(r?.silver_gain) || 0)),
      kills: Math.max(0, Math.floor(Number(r?.kills) || 0)),
      minutes: Math.max(0, Math.floor(Number(r?.minutes) || 0)),
    });
  }
  return out;
}
// ── E1 经济镜像：存档差值快照/记账/异常检测（旁路观察，零行为改变；账本=economy_ledger，kind='mirror'）──
// 快照口径：spiritStones/exp 取数值（缺失/空串/非数值/±Infinity → null=未知，不参与差值）；
// level=境界序×9+层数（复合层级行程：跳大境界=+9 或跨层；未知境界字符串按序 0 计；无 realm 字段 → null）
const ECON_REALM_ORDER: string[] = Object.keys(TRIB_REALM_BASES); // 七境界顺序（与 REALM_ORDER_FOR_RANKING 同源同序）
interface EconSnapshot { silver: number | null; exp: number | null; level: number | null; }
const EMPTY_ECON_SNAPSHOT: EconSnapshot = { silver: null, exp: null, level: null }; // 首存无旧档基线（差值记 NULL）
function extractEconSnapshot(saveData: any): EconSnapshot {
  try {
    const p = saveData?.player;
    if (!p) return { ...EMPTY_ECON_SNAPSHOT };
    const num = (v: any): number | null => {
      if (v == null || v === '' || typeof v === 'boolean') return null;
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    };
    let level: number | null = null;
    if (typeof p.realm === 'string' && p.realm) {
      const idx = ECON_REALM_ORDER.indexOf(p.realm);
      const lv = num(p.realmLevel);
      level = (idx < 0 ? 0 : idx) * 9 + (lv == null ? 1 : Math.floor(lv));
    }
    return { silver: num(p.spiritStones), exp: num(p.exp), level };
  } catch {
    return { ...EMPTY_ECON_SNAPSHOT };
  }
}
interface EconMirror {
  silverDelta: number | null;
  expDelta: number | null;
  levelFrom: number | null;
  levelTo: number | null;
  silverAfter: number | null;
}
// 差值（纯）：任一侧未知 → 该字段 null（不猜基线，宁缺毋假）；level 两侧原样带上供跳升判定
function computeEconMirror(prev: EconSnapshot, next: EconSnapshot): EconMirror {
  const diff = (a: number | null, b: number | null): number | null => (a == null || b == null ? null : b - a);
  return {
    silverDelta: diff(prev.silver, next.silver),
    expDelta: diff(prev.exp, next.exp),
    levelFrom: prev.level,
    levelTo: next.level,
    silverAfter: next.silver,
  };
}
// 异常规则（常量可配）：单次灵石增量 >50 万 / 负超 10 万、修为增量 >200 万、复合层级跳升 ≥3——命中写 flags
const ECON_SILVER_SPIKE = 500000;
const ECON_SILVER_DROP = 100000;
const ECON_EXP_SPIKE = 2000000;
const ECON_LEVEL_JUMP = 3;
function detectEconAnomalies(m: EconMirror): string[] {
  const flags: string[] = [];
  if (m.silverDelta != null) {
    if (m.silverDelta > ECON_SILVER_SPIKE) flags.push('silver_spike');
    if (m.silverDelta < -ECON_SILVER_DROP) flags.push('silver_drop');
  }
  if (m.expDelta != null && m.expDelta > ECON_EXP_SPIKE) flags.push('exp_spike');
  if (m.levelFrom != null && m.levelTo != null && m.levelTo - m.levelFrom >= ECON_LEVEL_JUMP) flags.push('level_jump');
  return flags;
}
// anomaly_json（可空）：无 flags → NULL；有 → {flags, mirror} 供清单回放
function econAnomalyJson(m: EconMirror, flags: string[]): string | null {
  if (!flags.length) return null;
  try { return JSON.stringify({ flags, mirror: m }); } catch { return null; }
}
// SEC 异常规则②③（2026-09-17 校准：真实存档 3 号筑基9=562万/金丹3=118万/炼气9=48万 + DT-Y 产出模型
// reports/data/hourly_model.json——现役最高合法产出≈21万/h@金丹（F-EXP 节奏 650 次/h 折算），见 reports/yl-sec.md §1）
const ECON_SILVER_BURST_1H = 1000000;  // 规则②：1h 滚动窗 silver_delta 累计（窗内镜像和+本次差值）>100 万 → silver_burst_1h
const ECON_SAVE_FREQ_MAX = 5;          // 规则③：1 分钟内存档上传次数 >5 → save_freq（恰 5 次不 flag）
const ECON_SAVE_FREQ_MS = 60000;       // 上传频率滚动窗宽
// 规则②判定（纯）：窗内既有累计 + 本次差值；两侧未知按 0 计（NULL 差值不参与），边界=严格大于
function detectSilverBurst(priorSum: number | null | undefined, m: EconMirror): boolean {
  const prior = Number.isFinite(Number(priorSum)) ? Number(priorSum) : 0;
  const cur = m.silverDelta == null ? 0 : m.silverDelta;
  return prior + cur > ECON_SILVER_BURST_1H;
}
// 规则③滚动窗（进程内存，重启清零=信号不丢账本账）：仅 POST /api/save 调用点登记——
// updatePlayerSave（GM patch/邮件/炼丹/天劫）不算"上传"，GM 批量操作不会误标
const econSaveStreak = new Map<number, number[]>();
function recordEconSaveUpload(playerId: number, nowMs: number = Date.now()): number {
  try {
    const keep = (econSaveStreak.get(playerId) || []).filter((t) => nowMs - t < ECON_SAVE_FREQ_MS);
    keep.push(nowMs);
    econSaveStreak.set(playerId, keep);
    return keep.length;
  } catch { return 0; } // 记账挂掉绝不影响存档路径（与 E1 同纪律）
}
// ── DG 秘境/地宫软门槛（R5：经典秘境计数=statistics.secretRealmCount；地宫客户端无任何计数器，
// 服务端可见性只能靠 entry 上报+存档差值被动观测两条腿；数值客户端读 /api/dungeon/status 展示与执行）──
const DUNGEON_DAILY_CAP = 3;          // 每日进入上限（entry 超限 403 但仍 +1 留账）
const DUNGEON_ENTRY_CD_MS = 900_000;   // 两次进入最小间隔（CD 内重复上报视为同一次，拒绝不计数）
const DUNGEON_ANOMALY_THRESHOLD = 25; // 单日 count 或 observed 超此值 → anomaly=1（GM /api/dungeon/anomalies 可查）
// ── R-032（dungeon2 环）每日上限**按境界**下发：客户端 yl_dungeon2_ext.py 用同一张表 ──
//   用户最新拍板：炼气基数 10 次、长生 20 次，中间 5 档递增（[10,12,14,15,17,18,20]）。
//   ★ 与策划案 D13-A（min(20,3+3×境界序)=[3,6,9,12,15,18,20]，炼气 3 起）不一致 ——
//     以用户最新拍板为准。两侧同源：此处 DUNGEON_CAP_BY_REALM ↔ 客户端 YLXW_DG_CAP。
//   境界序自持（不依赖 ECON_REALM_ORDER，避免与其它环的加载顺序耦合）。
const DUNGEON_REALM_ORDER: string[] = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];
const DUNGEON_CAP_BY_REALM: number[] = [10, 12, 14, 15, 17, 18, 20];
// 玩家境界 → 每日上限。未知境界 / 无存档 / 解析失败 → 兜底 DUNGEON_DAILY_CAP(=3)。
async function dungeonCapForUser(userId: number): Promise<number> {
  try {
    const row: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row || !row.save_data) return DUNGEON_DAILY_CAP;
    const realm = JSON.parse(String(row.save_data))?.player?.realm;
    const idx = DUNGEON_REALM_ORDER.indexOf(String(realm || ''));
    if (!(idx >= 0)) return DUNGEON_DAILY_CAP;
    const cap = DUNGEON_CAP_BY_REALM[Math.min(idx, DUNGEON_CAP_BY_REALM.length - 1)];
    return Number.isFinite(cap) && cap > 0 ? cap : DUNGEON_DAILY_CAP;
  } catch { return DUNGEON_DAILY_CAP; }
}
// ── [r063] R-063 roguelike 地宫「单独算上限」：独立上限表（与客户端 yl_063_ext.py 的
//   YLXW_DG_ROGUE_CAP 同源）。用户拍板口径：最低境界（炼气）一天 3 次、其他相应增加 ——
//   递增节奏沿用普通表（+2,+2,+1,+2,+1,+2，总 +10）、基座 3 ⇒ [3,5,7,8,10,11,13]，
//   任何境界都严格低于普通点选表 [10..20]（roguelike 单轮收益更高，次数保持更稀缺）。
const DUNGEON_ROGUE_CAP_BY_REALM: number[] = [3, 5, 7, 8, 10, 11, 13];
// 玩家境界 → roguelike 每日上限。未知境界 / 无存档 / 解析失败 → 兜底 DUNGEON_DAILY_CAP(=3，恰为 rogue 最低档)。
async function dungeonRogueCapForUser(userId: number): Promise<number> {
  try {
    const row: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row || !row.save_data) return DUNGEON_DAILY_CAP;
    const realm = JSON.parse(String(row.save_data))?.player?.realm;
    const idx = DUNGEON_REALM_ORDER.indexOf(String(realm || ''));
    if (!(idx >= 0)) return DUNGEON_DAILY_CAP;
    const cap = DUNGEON_ROGUE_CAP_BY_REALM[Math.min(idx, DUNGEON_ROGUE_CAP_BY_REALM.length - 1)];
    return Number.isFinite(cap) && cap > 0 ? cap : DUNGEON_DAILY_CAP;
  } catch { return DUNGEON_DAILY_CAP; }
}
// 存档差值 → 秘境观测增量（负差钳 0 同 Y15 口径：回档/多端旧档不倒扣）
function computeDungeonDeltas(prev: StatCounters, next: StatCounters): { realm: number; adventure: number } {
  const up = (a: number, b: number) => (b > a ? b - a : 0);
  return { realm: up(prev.secretRealmCount, next.secretRealmCount), adventure: up(prev.adventureCount, next.adventureCount) };
}
// 进入判定（纯）：CD 内=同一次进入的重复上报，不计数；超上限=记账仍拒（客户端可忽略 403，服务端有账，
// count 照加、超阈值自然触发 anomaly）；时钟回拨（dt<0）按 CD 未到处理防连点
function dungeonEntryVerdict(
  prevCount: number, prevLastTs: number | null, nowMs: number,
  cap: number = DUNGEON_DAILY_CAP, cdMs: number = DUNGEON_ENTRY_CD_MS
): { allowed: boolean; count: number; reason?: 'cd' | 'cap'; retryAfterMs?: number } {
  const c = Math.max(0, Math.floor(Number(prevCount) || 0));
  const last = prevLastTs != null && Number.isFinite(prevLastTs) ? Number(prevLastTs) : null;
  if (last != null && nowMs - last < cdMs) {
    return { allowed: false, count: c, reason: 'cd', retryAfterMs: cdMs - (nowMs - last) };
  }
  if (c >= cap) return { allowed: false, count: c + 1, reason: 'cap', retryAfterMs: 0 };
  return { allowed: true, count: c + 1 };
}
// 异常判定（纯）：entry 账本或存档观测任一"超"阈值（恰好等于不算）
function dungeonAnomaly(count: number, observed: number, threshold: number = DUNGEON_ANOMALY_THRESHOLD): boolean {
  return count > threshold || observed > threshold;
}
// 今日状态视图（纯）：status API 与伴生页同源展示口径；行不存在=今日首查全零可进
function dungeonStatusView(
  row: { count?: unknown; observed?: unknown; adventure?: unknown; last_ts?: unknown; anomaly?: unknown; rogue_count?: unknown; rogue_last_ts?: unknown; __rogueCap?: unknown } | null | undefined,
  nowMs: number,
  cap: number = DUNGEON_DAILY_CAP,
  cdMs: number = DUNGEON_ENTRY_CD_MS
): {
  date: string; count: number; cap: number; remaining: number;
  observed: number; adventure: number; anomaly: boolean;
  lastTs: number | null; cdLeftMs: number; canEnter: boolean;
  rogueCount: number; rogueCap: number; rogueRemaining: number; rogueCdLeftMs: number; rogueCanEnter: boolean;
} {
  const count = Math.max(0, Math.floor(Number(row?.count) || 0));
  const observed = Math.max(0, Math.floor(Number(row?.observed) || 0));
  const adventure = Math.max(0, Math.floor(Number(row?.adventure) || 0));
  const lastTs = row?.last_ts != null && Number.isFinite(Number(row.last_ts)) ? Number(row.last_ts) : null;
  /* [r136dg] last_ts 只由 /api/dungeon/entry 写入（观测累加不再刷它）；count=0 = 今天没进过 = 无冷却 */
  const cdLeftMs = lastTs != null && count > 0 ? Math.max(0, cdMs - (nowMs - lastTs)) : 0;
  // [r063] roguelike 独立账本字段（rogueCap 由 status 端点挂在 row.__rogueCap；缺省兜底 DUNGEON_DAILY_CAP）
  const rogueCount = Math.max(0, Math.floor(Number(row?.rogue_count) || 0));
  const rogueLastTs = row?.rogue_last_ts != null && Number.isFinite(Number(row.rogue_last_ts)) ? Number(row.rogue_last_ts) : null;
  const rogueCdLeftMs = rogueLastTs != null ? Math.max(0, cdMs - (nowMs - rogueLastTs)) : 0;
  const rogueCap = Math.max(1, Math.floor(Number((row as any)?.__rogueCap) || 0)) || DUNGEON_DAILY_CAP;
  return {
    date: bjDate(nowMs),
    count, cap,
    remaining: Math.max(0, cap - count),
    observed, adventure,
    anomaly: dungeonAnomaly(count, observed) || Number(row?.anomaly) === 1,
    lastTs, cdLeftMs,
    canEnter: count < cap && cdLeftMs === 0,
    rogueCount,
    rogueCap,
    rogueRemaining: Math.max(0, rogueCap - rogueCount),
    rogueCdLeftMs,
    rogueCanEnter: rogueCount < rogueCap && rogueCdLeftMs === 0,
  };
}
// ── Y16 江湖志：分页/文本钳制（写入在各自事件埋点路径 fire-and-forget，此处只管纯规则）──
const CHRONICLE_PAGE_SIZE = 50;     // 50 条/页
const CHRONICLE_MAX_PAGE = 200;     // 分页上限（50×200=1 万条查询窗口），防深翻拖库
const CHRONICLE_MAX_TEXT = 200;     // 单条正文上限
const CHRONICLE_MAIL_STONES = 10000; // 邮件附件灵石 ≥ 此值入志
const CHRONICLE_PRAISE_GOAL = 10;   // Y16B 传阅：恰达此次数触发当事人一次性奖励
const CHRONICLE_PRAISE_BASE = 1000; // Y16B 传阅奖励基数灵石（×1.5^境界指数，境界=rankings.realm_index 0..6）
function clampPage(raw: unknown, maxPage: number = CHRONICLE_MAX_PAGE): number {
  const p = Math.floor(asNum(raw) || 1);
  return Math.min(maxPage, Math.max(1, p)); // 非法/越界一律钳回有效页
}
function clampChronicleText(t: unknown): string { return asStr(t).slice(0, CHRONICLE_MAX_TEXT); }
// ── Y17 炼丹炉：配方/炉位/成熟判定/收益（数值为本次定档，常量集中可调）──
const ALCHEMY_SLOTS = 3;        // 每玩家炉位数（slot 0..2）
const ALCHEMY_YIELD_RATE = 1.5; // 出炉灵石返还率（丹药实体在客户端权威存档内服务端无法入包，按名目折算灵石随邮件发放）
// [r064] R-064 丹炉扩容 3→9 方 + 出炉丹道造诣常量（拍板 2026-10-01）：
//   收益率定档口径 = 净收益 ≈83.3 灵石/分钟（与既有 3 方同率，不通胀；YIELD_RATE 不动）；
//   profGain = 熟练度基础档（同丹房 ug 表），实际入账 ×ALCHEMY_PROF_FURNACE_MULT；
//   unlockLevel 与客户端丹方书同表；summary 数值与丹房配方表同源。
type AlchemyRecipeDef = { name: string; minutes: number; cost: number; rarity?: string; unlockLevel?: number; summary?: string; profGain?: number };
const ALCHEMY_PROF_GATE: number[] = [0, 100, 300, 800, 2000, 5000, 12000, 30000, 80000]; // 与客户端丹房 pm 同表（9 层）
const ALCHEMY_PROF_FURNACE_MULT = 1.2; // 兑现 t17 玩法说明「丹炉造诣涨得快 20%」
const ALCHEMY_RECIPES: Record<string, AlchemyRecipeDef> = {
  juqi:     { name: '聚气丹',   minutes: 30,  cost: 5000,   rarity: '普通', unlockLevel: 1, summary: '服用 修为+150', profGain: 10 },
  huichun:  { name: '回春丹',   minutes: 60,  cost: 10000,  rarity: '稀有', unlockLevel: 1, summary: '服用 气血+200', profGain: 30 },
  ningyuan: { name: '凝元丹',   minutes: 120, cost: 20000,  rarity: '稀有', unlockLevel: 1, summary: '出炉入丹囊：渡劫垫刀，每颗天劫成功率+3%', profGain: 30 },
  xisui:    { name: '洗髓丹',   minutes: 150, cost: 25000,  rarity: '稀有', unlockLevel: 3, summary: '永久 气血上限+50', profGain: 30 },
  yanshou:  { name: '延寿丹',   minutes: 180, cost: 30000,  rarity: '稀有', unlockLevel: 4, summary: '服用 寿命+10年', profGain: 30 },
  zhuji:    { name: '筑基丹',   minutes: 240, cost: 40000,  rarity: '传说', unlockLevel: 4, summary: '服用 修为+500｜永久 神识+300 体魄+30 气血上限+100', profGain: 100 },
  longxue:  { name: '龙血丹',   minutes: 360, cost: 60000,  rarity: '传说', unlockLevel: 6, summary: '永久 气血上限+500 体魄+50', profGain: 100 },
  pojing:   { name: '破境丹',   minutes: 480, cost: 80000,  rarity: '传说', unlockLevel: 5, summary: '服用 修为+1万｜永久 神识+50 体魄+50 攻击+30 防御+30', profGain: 100 },
  jiuzhuan: { name: '九转金丹', minutes: 720, cost: 120000, rarity: '仙品', unlockLevel: 8, summary: '服用 修为+5万｜永久 全属性+1000 寿命上限+1000年', profGain: 500 },
};
// [r077] R-077 炼丹开炉按成熟时长随机出丹数量（拍板 2026-10-01）：
//   基础方（聚气丹/回春丹）1-10 枚随机；方子越高阶（成熟越久、单枚越贵）随机枚数越少、波动越窄；
//   出炉灵石 = max(cost, floor(alchemyYieldStones(cost) × 枚数 / E[枚数])) ⇒ 期望 = cost×1.5（同改前，不通胀），
//   最差一掷保本（= cost）；单枚价值随成本/成熟时长递增（30min 1364 → 720min 120000）。
//   枚数区间走旁表（不改 ALCHEMY_RECIPES 逐行，srv_patch_064 门禁逐字钉死该表）。
const ALCHEMY_PILL_QTY: Record<string, [number, number]> = {
  '聚气丹': [1, 10], '回春丹': [1, 10], '凝元丹': [2, 8], '洗髓丹': [2, 7], '延寿丹': [2, 6],
  '筑基丹': [2, 5], '龙血丹': [1, 4], '破境丹': [1, 3], '九转金丹': [1, 2],
};
function alchemyQtyRange(name: unknown): [number, number] {
  const q = ALCHEMY_PILL_QTY[String(name)];
  if (!q) { return [1, 1]; }
  const lo = Math.max(1, Math.floor(Number(q[0]) || 1));
  const hi = Math.max(lo, Math.floor(Number(q[1]) || lo));
  return [lo, hi];
}
function alchemyRollPillCount(name: unknown): number {
  const r = alchemyQtyRange(name);
  return r[0] + Math.floor(Math.random() * (r[1] - r[0] + 1));
}
function alchemyPillYield(cost: number, count: number, name: unknown): number {
  const r = alchemyQtyRange(name);
  const e = (r[0] + r[1]) / 2;
  const n = Math.max(1, Math.floor(Number(count) || 1));
  return Math.max(cost, Math.floor(alchemyYieldStones(cost) * n / e));
}
function alchemyRecipesWithQty(): Record<string, any> {
  const out: Record<string, any> = {};
  for (const k of Object.keys(ALCHEMY_RECIPES)) {
    out[k] = Object.assign({}, ALCHEMY_RECIPES[k], { qty: alchemyQtyRange(ALCHEMY_RECIPES[k].name) });
  }
  return out;
}
function alchemyRecipe(key: unknown): AlchemyRecipeDef | null {
  return key != null && Object.prototype.hasOwnProperty.call(ALCHEMY_RECIPES, asStr(key)) ? ALCHEMY_RECIPES[asStr(key)] : null;
}
function alchemyRecipeByName(name: unknown): AlchemyRecipeDef | null {
  const n = asStr(name);
  for (const k of Object.keys(ALCHEMY_RECIPES)) if (ALCHEMY_RECIPES[k].name === n) return ALCHEMY_RECIPES[k];
  return null;
}
function alchemySlotOk(raw: unknown): boolean {
  const s = asNum(raw);
  return Number.isInteger(s) && s >= 0 && s < ALCHEMY_SLOTS;
}
function alchemyMatureAt(startMs: number, minutes: number): number {
  return startMs + Math.max(1, Math.floor(Number(minutes) || 1)) * 60 * 1000;
}
// 成熟判定（纯）：恰好到点算成熟（>=），提前收获拒绝
function alchemyIsReady(matureAt: number, nowMs: number): boolean { return nowMs >= matureAt; }
function alchemyYieldStones(cost: number): number { return Math.floor(cost * ALCHEMY_YIELD_RATE); }

// ── Y19 成就系统：五类各 10 项共 50 项，达成状态从 stats_daily/daily_quests/saves 惰性推导（零新增埋点）；[r122] 4→10 档
// 领取记录 achievement_claimed 主键幂等防重复领奖；奖励=灵石阶梯 500/1200/2500/4500/7000/10000/15000/22000/32000/50000（R-122 定档，单类 Σ144,700 / 全清 723,500；下方 ACH_REWARD_TIERS 为历史死常量、零消费点，未动）──
const ACH_REWARD_TIERS = [200, 500, 1000, 2000]; // 每类四档奖励阶梯（灵石）
// 境界序（ycore 内自持镜像，与 REALM_ORDER_FOR_RANKING 同源同序，勿外引）
const ACH_REALM_ORDER: string[] = Object.keys(TRIB_REALM_BASES);
type AchMetric = 'minutes' | 'kills' | 'silver' | 'quests' | 'realmIndex' | 'totalLevel'; // [r122] +totalLevel（境界组 10 档度量）
const ACH_GROUPS: Array<{ key: string; name: string; metric: AchMetric }> = [
  { key: 'cultivate', name: '修行', metric: 'minutes' },
  { key: 'battle', name: '战斗', metric: 'kills' },
  { key: 'wealth', name: '财富', metric: 'silver' },
  { key: 'quest', name: '任务', metric: 'quests' },
  { key: 'realm', name: '境界', metric: 'totalLevel' }, // [r122] realmIndex(0..6) 只有 7 档容量 → 总等级=境界序×9+层（rankings 口径）
];
interface AchTotals { minutes: number; kills: number; silver: number; quests: number; realmIndex: number; totalLevel: number; } // [r122] +totalLevel
interface AchDef { id: string; group: string; name: string; desc: string; target: number; reward: number; }
const ACH_DEFS: AchDef[] = [
  // 修行：累计 stats_daily.minutes（在线分钟=打坐时长的服务端可见代理）[r122] 4→10 档
  { id: 'cultivate_60', group: 'cultivate', name: '初窥门径', desc: '累计在线 60 分钟', target: 60, reward: 500 },
  { id: 'cultivate_300', group: 'cultivate', name: '潜心修行', desc: '累计在线 300 分钟', target: 300, reward: 1200 },
  { id: 'cultivate_1200', group: 'cultivate', name: '闭关苦修', desc: '累计在线 20 小时', target: 1200, reward: 2500 },
  { id: 'cultivate_3000', group: 'cultivate', name: '水磨功夫', desc: '累计在线 50 小时', target: 3000, reward: 4500 },
  { id: 'cultivate_7000', group: 'cultivate', name: '枯禅入定', desc: '累计在线 7000 分钟', target: 7000, reward: 7000 },
  { id: 'cultivate_15000', group: 'cultivate', name: '心斋坐忘', desc: '累计在线 250 小时', target: 15000, reward: 10000 },
  { id: 'cultivate_30000', group: 'cultivate', name: '禅定不移', desc: '累计在线 500 小时', target: 30000, reward: 15000 },
  { id: 'cultivate_60000', group: 'cultivate', name: '老僧入定', desc: '累计在线 1000 小时', target: 60000, reward: 22000 },
  { id: 'cultivate_100000', group: 'cultivate', name: '静水深流', desc: '累计在线 10 万分钟', target: 100000, reward: 32000 },
  { id: 'cultivate_150000', group: 'cultivate', name: '与道合真', desc: '累计在线 2500 小时', target: 150000, reward: 50000 },
  // 战斗：累计 stats_daily.kills（战斗胜利场次）[r122] 4→10 档
  { id: 'battle_10', group: 'battle', name: '初试锋芒', desc: '累计战斗胜利 10 场', target: 10, reward: 500 },
  { id: 'battle_50', group: 'battle', name: '身经百战', desc: '累计战斗胜利 50 场', target: 50, reward: 1200 },
  { id: 'battle_200', group: 'battle', name: '杀伐果断', desc: '累计战斗胜利 200 场', target: 200, reward: 2500 },
  { id: 'battle_500', group: 'battle', name: '百战成钢', desc: '累计战斗胜利 500 场', target: 500, reward: 4500 },
  { id: 'battle_1200', group: 'battle', name: '千锤百炼', desc: '累计战斗胜利 1200 场', target: 1200, reward: 7000 },
  { id: 'battle_2500', group: 'battle', name: '战无不胜', desc: '累计战斗胜利 2500 场', target: 2500, reward: 10000 },
  { id: 'battle_5000', group: 'battle', name: '攻无不克', desc: '累计战斗胜利 5000 场', target: 5000, reward: 15000 },
  { id: 'battle_10000', group: 'battle', name: '一骑当千', desc: '累计战斗胜利 1 万场', target: 10000, reward: 22000 },
  { id: 'battle_18000', group: 'battle', name: '万夫莫开', desc: '累计战斗胜利 1.8 万场', target: 18000, reward: 32000 },
  { id: 'battle_30000', group: 'battle', name: '天下无敌', desc: '累计战斗胜利 3 万场', target: 30000, reward: 50000 },
  // 财富：累计 stats_daily.silver_gain（灵石净获取，含邮件/宝箱/GM 入账）[r122] 4→10 档
  { id: 'wealth_1e4', group: 'wealth', name: '小有积蓄', desc: '累计获取灵石 1 万', target: 10000, reward: 500 },
  { id: 'wealth_1e5', group: 'wealth', name: '家财万贯', desc: '累计获取灵石 10 万', target: 100000, reward: 1200 },
  { id: 'wealth_1e6', group: 'wealth', name: '富可敌国', desc: '累计获取灵石 100 万', target: 1000000, reward: 2500 },
  { id: 'wealth_3e6', group: 'wealth', name: '日进斗金', desc: '累计获取灵石 300 万', target: 3000000, reward: 4500 },
  { id: 'wealth_8e6', group: 'wealth', name: '堆金积玉', desc: '累计获取灵石 800 万', target: 8000000, reward: 7000 },
  { id: 'wealth_2e7', group: 'wealth', name: '仙门首富', desc: '累计获取灵石 2000 万', target: 20000000, reward: 10000 },
  { id: 'wealth_5e7', group: 'wealth', name: '富甲天下', desc: '累计获取灵石 5000 万', target: 50000000, reward: 15000 },
  { id: 'wealth_12e7', group: 'wealth', name: '金玉满堂', desc: '累计获取灵石 1.2 亿', target: 120000000, reward: 22000 },
  { id: 'wealth_25e7', group: 'wealth', name: '灵石成海', desc: '累计获取灵石 2.5 亿', target: 250000000, reward: 32000 },
  { id: 'wealth_5e8', group: 'wealth', name: '仙界财神', desc: '累计获取灵石 5 亿', target: 500000000, reward: 50000 },
  // 任务：累计 daily_quests 完成（done=1 的任务行，不含宝箱领取占位行）[r122] 4→10 档
  { id: 'quest_1', group: 'quest', name: '小试牛刀', desc: '累计完成每日任务 1 个', target: 1, reward: 500 },
  { id: 'quest_10', group: 'quest', name: '勤修不辍', desc: '累计完成每日任务 10 个', target: 10, reward: 1200 },
  { id: 'quest_50', group: 'quest', name: '任务达人', desc: '累计完成每日任务 50 个', target: 50, reward: 2500 },
  { id: 'quest_150', group: 'quest', name: '日积月累', desc: '累计完成每日任务 150 个', target: 150, reward: 4500 },
  { id: 'quest_350', group: 'quest', name: '恒心毅力', desc: '累计完成每日任务 350 个', target: 350, reward: 7000 },
  { id: 'quest_700', group: 'quest', name: '仙途楷模', desc: '累计完成每日任务 700 个', target: 700, reward: 10000 },
  { id: 'quest_1200', group: 'quest', name: '卷中豪杰', desc: '累计完成每日任务 1200 个', target: 1200, reward: 15000 },
  { id: 'quest_2000', group: 'quest', name: '勤能补拙', desc: '累计完成每日任务 2000 个', target: 2000, reward: 22000 },
  { id: 'quest_3000', group: 'quest', name: '初心如磐', desc: '累计完成每日任务 3000 个', target: 3000, reward: 32000 },
  { id: 'quest_5000', group: 'quest', name: '仙途无悔', desc: '累计完成每日任务 5000 个', target: 5000, reward: 50000 },
  // 境界：saves 存档总等级达标（总等级=境界序×9+层数，rankings 口径；[r122] realmIndex→totalLevel，7 档容量→10 档）
  { id: 'realm_3', group: 'realm', name: '初入仙途', desc: '总等级达到 3（炼气三层）', target: 3, reward: 500 },
  { id: 'realm_10', group: 'realm', name: '筑基功成', desc: '总等级达到 10（筑基期一层）', target: 10, reward: 1200 },
  { id: 'realm_19', group: 'realm', name: '金丹初成', desc: '总等级达到 19（金丹期一层）', target: 19, reward: 2500 },
  { id: 'realm_28', group: 'realm', name: '元婴出窍', desc: '总等级达到 28（元婴期一层）', target: 28, reward: 4500 },
  { id: 'realm_37', group: 'realm', name: '化神通玄', desc: '总等级达到 37（化神期一层）', target: 37, reward: 7000 },
  { id: 'realm_46', group: 'realm', name: '合道之始', desc: '总等级达到 46（合道期一层）', target: 46, reward: 10000 },
  { id: 'realm_52', group: 'realm', name: '合道七重', desc: '总等级达到 52（合道期七层）', target: 52, reward: 15000 },
  { id: 'realm_56', group: 'realm', name: '长生之初', desc: '总等级达到 56（长生境二层）', target: 56, reward: 22000 },
  { id: 'realm_60', group: 'realm', name: '长生六重', desc: '总等级达到 60（长生境六层）', target: 60, reward: 32000 },
  { id: 'realm_63', group: 'realm', name: '长生久视', desc: '总等级达到 63（长生境九层·圆满）', target: 63, reward: 50000 },
]; // [r122ach10] R-122 五类各 4→10 档（0.9.13 数值表 §6）；单类 Σ144,700 / 全清 723,500；旧第 4 档退役（线上库已清空，无迁移负担）
// 全量钳制（纯）：负值/NaN/undefined/±Infinity → 0，小数 floor（DB 空表 SUM=NULL 亦归 0，边界 0 值安全）
function achTotalsFrom(t: { minutes?: unknown; kills?: unknown; silver?: unknown; quests?: unknown; realmIndex?: unknown; totalLevel?: unknown }): AchTotals {
  const n = (v: unknown) => { const x = Number(v); return Number.isFinite(x) ? Math.max(0, Math.floor(x)) : 0; };
  return { minutes: n(t.minutes), kills: n(t.kills), silver: n(t.silver), quests: n(t.quests), realmIndex: n(t.realmIndex), totalLevel: n(t.totalLevel) }; // [r122] +totalLevel
}
// 视图组装（纯）：50 项全量 + 分组计数 + 可领取清单（done && !claimed）
function buildAchievementsView(
  totals: AchTotals,
  claimed: string[]
): {
  totals: AchTotals;
  groups: Array<{ key: string; name: string; done: number; total: number; items: Array<{ id: string; name: string; desc: string; target: number; reward: number; progress: number; done: boolean; claimed: boolean }> }>;
  claimableIds: string[];
} {
  const claimedSet = new Set(claimed);
  const groups = ACH_GROUPS.map((g) => {
    const items = ACH_DEFS.filter((d) => d.group === g.key).map((d) => {
      const val = Number(totals[g.metric]) || 0;
      return {
        id: d.id, name: d.name, desc: d.desc, target: d.target, reward: d.reward,
        progress: Math.max(0, Math.min(val, d.target)), // 进度封顶不溢出
        done: val >= d.target,
        claimed: claimedSet.has(d.id),
      };
    });
    return { key: g.key, name: g.name, done: items.filter((i) => i.done).length, total: items.length, items };
  });
  const claimableIds: string[] = [];
  for (const g of groups) for (const it of g.items) if (it.done && !it.claimed) claimableIds.push(it.id);
  return { totals, groups, claimableIds };
}
// 领取选取（纯）：缺省=一键全部可达标；指定 id 只领该项（未达成/已领 → 空数组即拒绝，防越权领取）
function achPickClaimable(view: { claimableIds: string[] }, requestedId?: unknown): string[] {
  if (requestedId == null || requestedId === '') return view.claimableIds.slice();
  const id = asStr(requestedId);
  return view.claimableIds.includes(id) ? [id] : [];
}
// ── Y3A 奇遇日记 → [r057] R-057 奇遇抽奖：每日 10 次 · 冷却 30 分钟 · 消耗修为 5% 槽 · 15% 暴击双倍 ──
const ADVENTURE_DAILY_MAX = 10; // 每日抽取次数上限 [r057] 3→10
const ADVENTURE_COOLDOWN_MS = 30 * 60 * 1000; // [r057] 抽取冷却：30 分钟
const ADVENTURE_COST_RATE = 0.05; // [r057] 每次消耗 = 当层修为槽 × 5%（修为不足拒绝）
const ADVENTURE_CRIT_RATE = 0.15; // [r057] 暴击几率（灵石与修为收益双倍）
// 奇遇品阶：weight=权重（合计 100），stones=固定灵石，expRate=按当层修为槽百分比的修为收益（钳槽内不溢出）。
// 数值为本次定档，常量集中可调
// 0.8.6：stones / expRate 由**定值**改为**区间**（用户反馈「数值都是固定值」），
// 同时新增 tickets（必得抽奖券）与 bonusChance/bonusTickets（小概率额外珍宝）。
interface AdventureTierDef {
  key: string; name: string; weight: number;
  stonesMin: number; stonesMax: number;
  expRateMin: number; expRateMax: number;
  tickets: number; bonusChance: number; bonusTickets: number;
}
const ADVENTURE_TIERS: AdventureTierDef[] = [
  { key: 'white',  name: '白', weight: 80,   stonesMin: 2400,  stonesMax: 5400,   expRateMin: 0.0015, expRateMax: 0.0030, tickets: 0, bonusChance: 0.02, bonusTickets: 0 }, // [r057] 灵石 ×30
  { key: 'blue',   name: '蓝', weight: 12.5, stonesMin: 7500,  stonesMax: 16500,  expRateMin: 0.0030, expRateMax: 0.0060, tickets: 0, bonusChance: 0.06, bonusTickets: 0 }, // [r057] 灵石 ×30
  { key: 'purple', name: '紫', weight: 6,    stonesMin: 21000, stonesMax: 48000,  expRateMin: 0.0060, expRateMax: 0.0120, tickets: 0, bonusChance: 0.01, bonusTickets: 1 }, // [r057] 灵石 ×30 // [r116] 券概率压低：紫档 bonus 0.15→0.01
  { key: 'gold',   name: '金', weight: 1.5,  stonesMin: 54000, stonesMax: 126000, expRateMin: 0.0120, expRateMax: 0.0220, tickets: 0, bonusChance: 0.02, bonusTickets: 1 }, // [r057] 灵石 ×30 // [r116] 券概率压低：金档 1→0 / 0.35→0.02 / 2→1
];
// 额外珍宝文案池（小概率触发时随抽附赠，纯展示 + 抽奖券）
const ADVENTURE_BONUS_TEXTS = [
  '拾得一枚残破玉简，其中隐有前人笔记',
  '草丛里翻出半截古符，虽已失效仍带灵气',
  '溪底摸到一块温润灵石原矿',
  '古树上挂着一只无人认领的储物袋',
  '崖壁凹处藏着一小坛封存多年的灵酒',
  '路边石缝里嵌着一枚锈迹斑斑的古钱',
];
function adventureTierByKey(key: unknown): AdventureTierDef | null {
  const k = String(key ?? '');
  return ADVENTURE_TIERS.find((t) => t.key === k) || null;
}
// 抽品阶（纯，rng 注入可单测）：从高稀有到低稀有累计区间落点——
// 金 [0,0.015) / 紫 [0.015,0.075) / 蓝 [0.075,0.20) / 白 [0.20,1)（物品概率÷2：稀有以上权重减半，白80/蓝12.5/紫6/金1.5，分母仍为 100）
function drawAdventureTier(rng: () => number): AdventureTierDef {
  const roll = Math.min(0.999999, Math.max(0, Number(rng()) || 0));
  let acc = 0;
  for (let i = ADVENTURE_TIERS.length - 1; i >= 0; i--) { // gold → purple → blue → white
    acc += ADVENTURE_TIERS[i].weight / 100;
    if (roll < acc) return ADVENTURE_TIERS[i];
  }
  return ADVENTURE_TIERS[0];
}
// 奇遇文本池（修仙风；key 全局唯一=伴生页图鉴收藏位；同阶内等概率随机取一条）
interface AdventureEventDef { key: string; tier: string; text: string; }
const ADVENTURE_EVENTS: AdventureEventDef[] = [
  // 白 · 凡遇
  { key: 'w_grass', tier: 'white', text: '山道旁随手采了一把狗尾巴草，编成指环戴上，聊胜于无。' },
  { key: 'w_nap', tier: 'white', text: '古树下打盹片刻，梦见自己御剑飞行，醒来枕边多了几枚落叶。' },
  { key: 'w_rain', tier: 'white', text: '山中突降细雨，躲进山神庙避雨，供桌下摸出几枚散碎灵石。' },
  { key: 'w_carp', tier: 'white', text: '溪边濯足，惊起一尾锦鲤，跃起时甩了你一脸水，倒也清凉提神。' },
  { key: 'w_egg', tier: 'white', text: '草丛里捡到一枚鸟蛋，孵出一只歪脖子小鸡，叽叽喳喳跟了你半日。' },
  // 蓝 · 小机缘
  { key: 'b_herb', tier: 'blue', text: '崖壁石缝间寻得一株百年灵芝，服下后灵台清明，修为略进。' },
  { key: 'b_ruins', tier: 'blue', text: '误入晨雾深谷，雾散时脚下竟是一处前人吐纳遗迹，盘坐参悟片刻。' },
  { key: 'b_monkey', tier: 'blue', text: '一只灵猴抢了你的干粮，追至洞中，反在它窝里淘出一袋灵石。' },
  { key: 'b_stone', tier: 'blue', text: '河滩上一块顽石在月光下泛着微光，剖开竟是中品灵石原矿。' },
  { key: 'b_dew', tier: 'blue', text: '以葫芦收得紫竹叶上天露一捧，饮之通体舒畅，修为微涨。' },
  // 紫 · 大机缘
  { key: 'p_cave', tier: 'purple', text: '雷雨夜山体崩塌，露出一段上古洞府遗刻，参悟一夜，修为大进。' },
  { key: 'p_sword', tier: 'purple', text: '于断剑残冢中得一柄无名古剑，剑意灌体，气海翻涌，境界隐隐松动。' },
  { key: 'p_lotus', tier: 'purple', text: '寒潭深处采得一朵九叶黑莲，炼化入体，周天运转豁然贯通。' },
  { key: 'p_chess', tier: 'purple', text: '山中棋逢一位老叟，老叟抚须大笑，指点一二如拨云见日，修为精进。' },
  { key: 'p_fire', tier: 'purple', text: '地火喷发的缝隙里拾得一缕地心离火，淬炼经脉，根基愈发凝实。' },
  { key: 'w_wind', tier: 'white', text: '山风忽起，吹落一襟松针，倒也神清气爽。' },
  { key: 'w_dog', tier: 'white', text: '一只黄犬摇尾跟了你三里路，临别时从它项圈上掉下几枚铜钱。' },
  { key: 'w_moon', tier: 'white', text: '夜观月色，忽觉心中块垒消了几分，聊胜于无。' },
  { key: 'w_bamboo', tier: 'white', text: '竹林中捡到一节中空的紫竹，削成短笛，吹得走调却也自得其乐。' },
  { key: 'w_fish', tier: 'white', text: '溪中徒手摸鱼半日，鱼没摸着，倒摸出一把光滑的鹅卵石。' },
  // 蓝 · 小机缘（补 5 条）
  { key: 'b_well', tier: 'blue', text: '枯井深处传来水声，垂下绳索汲上一瓢，入口甘冽异常。' },
  { key: 'b_market', tier: 'blue', text: '集市上以三枚铜钱淘得一本旧账簿，夹页里竟藏着几粒灵石碎屑。' },
  { key: 'b_hermit', tier: 'blue', text: '茅屋前遇一采药老翁，闲谈半日，老翁随手赠你一味不知名的药草。' },
  { key: 'b_bell', tier: 'blue', text: '古刹钟声一响，你忽有所悟，盘坐檐下静听了一个时辰。' },
  { key: 'b_mirror', tier: 'blue', text: '荒宅妆台上搁着一面铜镜，照见自己眉目清明，心神为之一静。' },
  // 紫 · 大机缘（补 3 条）
  { key: 'p_tide', tier: 'purple', text: '观潮三日，潮起潮落间窥见一线天机，气机随之鼓荡。' },
  { key: 'p_grave', tier: 'purple', text: '荒山野冢无碑无名，你以礼相拜，冢中竟浮出一缕精纯灵气没入眉心。' },
  { key: 'p_rain', tier: 'purple', text: '雷雨交加夜，你在崖顶立而不动，一道紫雷擦身而过，经脉隐隐拓宽。' },
  // 金 · 天缘（原 3 条**保留** + 补 3 条）
  { key: 'g_immortal', tier: 'gold', text: '云海之巅遇仙人对弈，一子落枰，天机灌顶——此等缘法，万中无一！' },
  { key: 'g_dragon', tier: 'gold', text: '蛟龙虚影自深潭腾空而过，一片逆鳞坠入你手，灵气如江河灌体！' },
  { key: 'g_scroll', tier: 'gold', text: '残破古卷自九天飘落，仙文入眼即化道音——福缘深厚，天授之才！' },
  { key: 'g_phoenix', tier: 'gold', text: '九霄之上凤鸣一声，一枚赤羽飘落掌心，灼热灵气直冲百会！' },
  { key: 'g_star', tier: 'gold', text: '星河倒悬，一颗流星坠入你怀，化为浑圆灵石，光华流转不息！' },
  { key: 'g_master', tier: 'gold', text: '白衣人拦路，只说了一句「你我有缘」，你便觉周天运转豁然开朗！' },
];
function adventureEventsOfTier(tier: string): AdventureEventDef[] {
  return ADVENTURE_EVENTS.filter((e) => e.tier === tier);
}
function pickAdventureEvent(tier: string, rng: () => number): AdventureEventDef {
  const pool = adventureEventsOfTier(tier);
  if (!pool.length) return { key: 'unknown', tier, text: '一路平安，无事发生。' };
  const roll = Math.min(0.999999, Math.max(0, Number(rng()) || 0));
  const idx = Math.min(pool.length - 1, Math.floor(roll * pool.length));
  return pool[idx];
}
// 奇遇修为收益（纯）：按当层修为槽百分比计，钳在槽内不溢出（已圆满则收益归零，不入结转段）
// 0.8.6：百分比改为**调用方传入**（区间随机后固定），保证 updatePlayerSave 回调可重入而不抖动。
function adventureExpGainRate(expRate: unknown, maxExp: number, currentExp: number): number {
  const slot = Math.max(0, Math.floor(Number(maxExp) || 0));
  const cur = Math.max(0, Math.floor(Number(currentExp) || 0));
  const raw = Math.floor(slot * Math.max(0, Number(expRate) || 0));
  return Math.max(0, Math.min(raw, slot - cur));
}
// 兼容旧调用：取该档区间中值
function adventureExpGain(tierKey: string, maxExp: number, currentExp: number): number {
  const t = adventureTierByKey(tierKey);
  if (!t) return 0;
  return adventureExpGainRate((t.expRateMin + t.expRateMax) / 2, maxExp, currentExp);
}
// ── Y3A 渡劫垫刀：凝元丹（炼丹炉凝元丹方出炉入库）垫刀提天劫胜率；失败返五成修为 ──
const TRIB_PILL_MAX = 10;          // 垫刀数上限（≤10 颗）
const TRIB_PILL_BONUS = 0.03;      // 每颗 +3% 天劫成功率（落实为我方三维各 +3%，把"成功率"落进天劫战胜率）
const TRIB_FAIL_REFUND_RATE = 0.5; // 渡劫失败：满槽修为尽散后返还五成（净损 = maxExp - floor(maxExp/2)）
// 垫刀数（纯）：钳 [0, TRIB_PILL_MAX]，非数/负数归 0
function pillCount(v: unknown): number {
  const n = Math.floor(Number(v) || 0);
  return Math.min(TRIB_PILL_MAX, Math.max(0, n));
}
function pillBonusRate(pills: unknown): number { return pillCount(pills) * TRIB_PILL_BONUS; }
// 垫刀增幅后的我方面板（纯）：攻/防/血各 ×(1+加成) 向下取整（0 保持 0）
function tribBuffedStats(
  stats: { attack: unknown; defense: unknown; maxHp: unknown },
  pills: unknown
): { attack: number; defense: number; maxHp: number } {
  const mult = 1 + pillBonusRate(pills);
  const f = (v: unknown) => Math.max(0, Math.floor(Math.max(0, Math.floor(Number(v) || 0)) * mult));
  return { attack: f(stats.attack), defense: f(stats.defense), maxHp: f(stats.maxHp) };
}
// 渡劫失败修为结转（纯）：反噬先震散整个当层修为槽，再按 TRIB_FAIL_REFUND_RATE 返还——
// 等价净损 = maxExp - floor(maxExp*rate)；exp 不足部分钳 0 兜底
function tribFailExpAfter(exp: number, maxExp: number): number {
  const slot = Math.max(0, Math.floor(Number(maxExp) || 0));
  const cur = Math.max(0, Math.floor(Number(exp) || 0));
  const refund = Math.floor(slot * TRIB_FAIL_REFUND_RATE);
  return Math.max(0, cur - slot + refund);
}
// ─────────────────────────────────────────────────────────
// ★ R-021（offline2 环）离线窗口锚点修正
//   旧口径：锚点 = saves.updated_at。而客户端每 10s 自动存档（心跳存档）都会刷新 updated_at，
//     于是「挂机 / 离开」期间窗口恒 ≈10s < OFFLINE_MIN_MS(5min) ⇒ 面板恒 0（真 bug）。
//   新口径：优先取客户端上报的「真实离开时刻」last_seen_at（心跳存档不再能移动锚点）；
//     缺失 / 已被领取覆盖时**逐位回落**旧口径 updated_at —— 老客户端零行为变更。
//   ★ 红线：本环只改「离线时长」的判定。offlineRewards()（expGain/stoneGain 公式）、
//     offlineWindow() 本体、OFFLINE_* 常量、月卡判定、活动/师徒倍率、入账与钳制逻辑一行未动。
// ─────────────────────────────────────────────────────────
// 离线窗口锚点（纯函数）：返回 { anchorMs, endMs, source }
//   · last_seen_at 有效条件：非空、且尚未被 offline_claimed_until 覆盖（该段还没领过）。
//     → 窗口 = [max(last_seen_at, claimed_until), endMs]
//   · 无效 / 缺失 → 回落 updated_at，窗口末端 = nowMs（与改前逐位一致）
//   · endMs：已上报「回来」且晚于离开 → 用 last_resume_at 封口（离线段冻结，不随在线时长增长）；
//            否则 = nowMs（玩家仍在离线中，窗口自然增长）
function offlineAnchor(
  updatedAtMs: number | null, lastSeenAtMs: unknown, lastResumeAtMs: unknown,
  claimedUntilMs: unknown, nowMs: number
): { anchorMs: number | null; endMs: number; source: string } {
  const u = (updatedAtMs != null && Number.isFinite(updatedAtMs)) ? updatedAtMs : null;
  const lRaw = Number(lastSeenAtMs);
  const l = (lastSeenAtMs != null && Number.isFinite(lRaw) && lRaw > 0) ? lRaw : null;
  const rRaw = Number(lastResumeAtMs);
  const r = (lastResumeAtMs != null && Number.isFinite(rRaw) && rRaw > 0) ? rRaw : null;
  const cl = (claimedUntilMs != null && Number.isFinite(Number(claimedUntilMs))) ? Number(claimedUntilMs) : 0;
  if (l != null && l > cl) {
    const end = (r != null && r > l) ? r : nowMs;
    return { anchorMs: Math.max(l, cl), endMs: end, source: 'last_seen_at' };
  }
  return { anchorMs: u, endMs: nowMs, source: 'updated_at' };
}

// POST /api/session/presence —— 客户端上报「离开 / 回来」（R-021 锚点事件源）
//   body { state: 'away' | 'back' }
//   away：last_seen_at = 本行当前 updated_at（服务端权威；客户端只能触发，不能带时间戳）
//   back：last_resume_at = Date.now()
// 幂等、无副作用：不写存档、不记账、不影响经济；尚未建角（无行）直接 ok。
app.post('/api/session/presence', authenticateToken, async (req: any, res: any) => {
  try {
    const st = req.body && req.body.state;
    if (st !== 'away' && st !== 'back') return res.status(400).json({ error: 'state must be away|back' });
    if (st === 'away') {
      const row: any = await dbGet('SELECT updated_at FROM saves WHERE user_id = ?', [req.user.id]);
      const at = parseDbTimeMs(row && row.updated_at);
      if (row && at != null) await dbRun('UPDATE saves SET last_seen_at = ? WHERE user_id = ?', [at, req.user.id]);
    } else {
      await dbRun('UPDATE saves SET last_resume_at = ? WHERE user_id = ?', [Date.now(), req.user.id]);
    }
    res.json({ ok: true, state: st });
  } catch (e: any) {
    console.error('session presence error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

// ── Y3A 离线收益报告：按上次存档(saves.updated_at)到当前的离线时长结算收益（修为+灵石分项）──
// WUDAO 增强（2026-09-17）：月卡判定接线（saves.month_card_until）——上限 12h + 效率 100%；
// 效率口径：4.8%/h = 6%/h 基准 × 80% 效率，故月卡效率 100% = 6%/h（两档均为定值常量，不做乘法防浮点漂移，
// 无月卡玩家收益与改前逐位一致）。月卡开通入口（购买流程）未上线，过渡期 GM 直改 month_card_until 列。
const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;     // 离线速率（无月卡）：0.48% 当层修为槽/小时（修为难度×10：0.048→0.0048）
const OFFLINE_RATE_MONTHCARD_PER_HOUR = 0.006; // 离线速率（月卡，效率 100%）：0.6% 当层修为槽/小时（修为难度×10：0.06→0.006）
const OFFLINE_CAP_HOURS_BASE = 8;       // 离线结算时长上限（无月卡）
const OFFLINE_CAP_HOURS_MONTHCARD = 12; // 离线结算时长上限（月卡）
const OFFLINE_STONE_RATIO = 0.1;        // 灵石分项 = 修为收益 × 10%（本次定档，常量可调）
const OFFLINE_MIN_MS = 5 * 60 * 1000;   // 离线不足 5 分钟不计（防频繁登录白嫖零头）
// 月卡判定（纯）：month_card_until 时刻之前有效；恰好到期时刻已失效；NULL/非法=无月卡
function hasMonthCard(untilMs: unknown, nowMs: number): boolean {
  const u = Number(untilMs);
  return Number.isFinite(u) && nowMs < u;
}
// 结算时长上限（纯）：月卡 12h / 无月卡 8h
function offlineCapHours(hasMonth: unknown): number {
  return hasMonth ? OFFLINE_CAP_HOURS_MONTHCARD : OFFLINE_CAP_HOURS_BASE;
}
// 结算速率（纯）：月卡（效率 100%）6%/h / 无月卡（效率 80%）4.8%/h
function offlineRatePerHour(hasMonth: unknown): number {
  return hasMonth ? OFFLINE_RATE_MONTHCARD_PER_HOUR : OFFLINE_RATE_BASE_PER_HOUR;
}
// 离线窗口（纯）：起点=上次存档与"已领截止"二者较晚者；无存档时间 → null（无法结算）
function offlineWindow(
  lastSaveMs: number | null, claimedUntilMs: number | null | undefined, nowMs: number
): { startMs: number; windowMs: number } | null {
  if (lastSaveMs == null || !Number.isFinite(lastSaveMs)) return null;
  const cl = claimedUntilMs != null && Number.isFinite(Number(claimedUntilMs)) ? Number(claimedUntilMs) : 0;
  const startMs = Math.max(Number(lastSaveMs), cl);
  return { startMs, windowMs: Math.max(0, nowMs - startMs) };
}
// 收益明细（纯）：时长钳上限；修为=槽×速率×小时，钳槽内不溢出；灵石=修为×10%；
// 离线不足 OFFLINE_MIN_MS 收益归零（预览与可领判定一致，claimable=false 时明细必为 0）
function offlineRewards(
  maxExp: number, currentExp: number, windowMs: number, capHours: number,
  ratePerHour: number = OFFLINE_RATE_BASE_PER_HOUR
): { hours: number; expGain: number; stonesGain: number; capped: boolean; claimable: boolean; effectiveMs: number } {
  const slot = Math.max(0, Math.floor(Number(maxExp) || 0));
  const cur = Math.max(0, Math.floor(Number(currentExp) || 0));
  const cap = Math.max(0, Number(capHours) || 0);
  const rate = Math.max(0, Number(ratePerHour) || 0);
  const rawHours = Math.max(0, (Number(windowMs) || 0) / 3600000);
  const effHours = Math.min(rawHours, cap);
  const enough = (Number(windowMs) || 0) >= OFFLINE_MIN_MS;
  const expGain = enough ? Math.max(0, Math.min(Math.floor(slot * rate * effHours), slot - cur)) : 0;
  const stonesGain = Math.floor(expGain * OFFLINE_STONE_RATIO);
  return {
    hours: Math.round(effHours * 100) / 100,
    expGain,
    stonesGain,
    capped: rawHours > cap,
    claimable: enough && (expGain > 0 || stonesGain > 0),
    effectiveMs: Math.round(effHours * 3600000),
  };
}
// 境界差值提示（纯）：离线收益叠加后若修为满槽→提示"快突破"；第九层且满槽=已满足突破条件（可渡劫）；
// 已至最高境（长生境/境界数据异常）不打扰。ready 只在"渡劫真正可用"（第九层+满槽）时为 true
function offlineBreakthroughHint(
  realmIndex: number, realmLevel: number, exp: number, maxExp: number, expGain: number, realmCount: number
): { ready: boolean; hint: string | null } {
  const isMax = !Number.isInteger(realmIndex) || realmIndex < 0 || realmIndex >= realmCount - 1;
  if (isMax) return { ready: false, hint: null };
  const lv = Math.max(1, Math.floor(Number(realmLevel) || 1));
  const slot = Math.max(1, Math.floor(Number(maxExp) || 1));
  const fullAfter = Math.max(0, Math.floor(Number(exp) || 0)) + Math.max(0, Math.floor(Number(expGain) || 0)) >= slot;
  if (fullAfter && lv >= 9) return { ready: true, hint: '离线中已满足突破条件：修为圆满第九层，可前往「渡劫」挑战天劫！' };
  if (fullAfter) return { ready: false, hint: `离线修为已圆满，但突破还需修至第九层（当前第${lv}层）` };
  return { ready: false, hint: null };
}
// ── Y-B 悬赏榜：纯规则（数值为本次定档，常量集中可调）──
// 口径：发布即全额托管（扣发布者灵石存 bounties.reward）→ 发布者确认完成 → 接受者得 payout=floor(reward×90%)，
// 差额=系统税（不上账即销毁，经济通缩口径）；取消/24h 过期退全款。
const BOUNTY_FEE_RATE = 0.1;                    // 系统税率 10%
const BOUNTY_DURATION_MS = 24 * 60 * 60 * 1000; // 悬赏有效期 24h（过期自动退款退任务）
const BOUNTY_ACCEPT_MAX = 3;                    // 同一玩家同时最多接取 3 个（防占坑）
const BOUNTY_POSTER_OPEN_MAX = 5;               // 同一发布者同时最多 5 个 open（防大厅刷屏）
const BOUNTY_MIN_REWARD = 100;                  // 单笔赏金下限（防灰尘单）
const BOUNTY_MAX_REWARD = 1000000;              // 单笔赏金上限（防手滑天价单）
const BOUNTY_TITLE_MAX = 32;                    // 标题上限
const BOUNTY_DESC_MAX = 200;                    // 描述上限
const BOUNTY_PAGE_SIZE = 20;                    // 大厅分页
const BOUNTY_MAX_PAGE = 200;                    // 分页上限（20×200=4000 条查询窗口，防深翻拖库）
const BOUNTY_SWEEP_BATCH = 20;                  // 过期清扫单批行数（惰性分批，逐批消化）
// 完成发放（纯）：floor(reward×(1-fee))，payout+tax 恒等于 reward（分账不丢灵石）
function bountyPayout(reward: number): number {
  return Math.max(0, Math.floor((Number(reward) || 0) * (1 - BOUNTY_FEE_RATE)));
}
function bountyTax(reward: number): number {
  return Math.max(0, (Number(reward) || 0) - bountyPayout(reward));
}
function bountyDeadline(nowMs: number): number { return nowMs + BOUNTY_DURATION_MS; }
// 过期判定（纯）：恰好到点算过期（>=，与炼丹成熟同语义族）
function bountyIsExpired(deadline: number, nowMs: number): boolean { return nowMs >= Number(deadline); }
// 赏金校验（纯）：正整数且在 [MIN,MAX] 内 → 返回规范化数值，否则 null（字符串数字可过，小数/负数/越界拒）
function bountyRewardOk(raw: unknown): number | null {
  const n = asNum(raw);
  if (!Number.isFinite(n) || !Number.isInteger(n)) return null;
  if (n < BOUNTY_MIN_REWARD || n > BOUNTY_MAX_REWARD) return null;
  return n;
}
function bountyTitleClamp(t: unknown): string { return asStr(t).trim().slice(0, BOUNTY_TITLE_MAX); }
function bountyDescClamp(t: unknown): string { return asStr(t).trim().slice(0, BOUNTY_DESC_MAX); }
// [/ycore]

// [farmcore] Y19 洞府灵田纯逻辑核心（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
// 数值为本次定档，常量集中可调；作物=种子灵石/生长时长/产量（灵石+修为），提前收获收益减半
const FARM_SLOTS = 6; // T10：田位数 3→6（slot 1 免费隐式解锁；2/3 灵石开垦；4/5/6 另需洞府等级门槛，见 FARM_UNLOCK_GROTTO_LEVEL；farmSlotOk/status 循环/LIMIT 全部随本常量自动泛化）
// ★ T5（0.8.9）灵田品种重构：5 种 → 20 种（5 品阶 × 4 产品线）+ 5 旧种兼容区。
//   数值全部来自 docs/0.8.8-design/T5-灵田品种重构.md §3 完整数值表（定稿），
//   聚合为「品阶基准 + 类型系数」两张纯表（§2.3/§2.4/§2.5 生成规则，§4.2 抽样验证 ✅）：
//     时长 = clamp30(B(品阶) × k(类型))，下限 120；变卖价 = round(V(品阶) × m(类型))；
//     种子价 = round(变卖价 × Cs(类型))；服用修为 = 纯修为草直表 / 其余 = E(品阶) × e(类型)。
//   ★ 旧 5 种**不再是可播种品种**（plant 端点 409 拒绝新播），但表体逐字保留 ⇒
//     存量已种下的旧作物仍能被 farmCrop() 查到并按旧口径正常收获（§7-Q7(a)，防玩家损失）。
//     （farmCrop() 经 farmCropDefs() 取表，后者把本表 5 键原样并入 ⇒ 存量旧田口径逐字不变。）
const FARM_CROPS: Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number }> = {
  // ── 旧作物（T5 兼容区 · 只读存量，不可新播）──────────────────────────
  //   旧作物只有「灵石 + 修为」一个出口 ⇒ 服用只给修为、变卖给灵石（§7-Q7）。
  //   照料口径对旧作物同样生效（tendBonus 由 farmHarvestMods 统一给出）。
  lingcao:     { name: '灵草',   seed: 1000, minutes: 240,  stones: 800,   exp: 500 },
  lingzhi:     { name: '灵芝',   seed: 5000, minutes: 720,  stones: 5000,  exp: 3000 },
  qianniancan: { name: '千年参', seed: 20000, minutes: 1440, stones: 25000, exp: 15000 },
  // T10 高阶作物（数值=设计案建议锚值，★待《数值表-T9T10.md》#8 定档回填；洞府门槛对齐地块档 #4）：
  //   经济红线 #11 预验算（相对式）：满配（L10 洞府 +10% × 照料 +10% = ×1.21 毛额）最赚钱作物=造化青莲，
  //   日净 = (215000×1.21−200000)/3 天 ≈ 20,050/田 → ×6 田 ≈ 120,300/日 ≤ 150,000（=T5-C 对价 150 万的 1/10）✓
  //   净收益率 产出/种子：太虚果 1.40（2 天）、造化青莲 1.075（3 天，但日净绝对值 2 倍于千年参）；修为≈灵石×0.6 同既有比例
  taixuguo:       { name: '太虚果',   seed: 50000,  minutes: 2880, stones: 70000,  exp: 42000,  grottoLevel: 5 },
  zaohuaqinglian: { name: '造化青莲', seed: 200000, minutes: 4320, stones: 215000, exp: 129000, grottoLevel: 7 },
};

// ── T5 新 20 种：品阶基准 + 类型系数（两层查表，零手抄，杜绝抄错）────────
//   品阶 1..5 = 凡品/灵品/玄品/仙品/神品；洞府解锁门槛 凡灵 Lv1 / 玄 Lv3 / 仙 Lv5 / 神 Lv7。
const FARM_CROP_BASE: Record<number, { min: number; sell: number; expBase: number; attr: number }> = {
  1: { min: 120, sell: 500,   expBase: 63000,  attr: 8 },     // 凡品
  2: { min: 180, sell: 1500,  expBase: 189000, attr: 30 },    // 灵品
  3: { min: 300, sell: 5000,  expBase: 630000, attr: 100 },   // 玄品
  4: { min: 480, sell: 13000, expBase: 2016000, attr: 350 },   // 仙品
  5: { min: 720, sell: 27000, expBase: 5670000, attr: 1000 },  // 神品
};
const FARM_CROP_KIND: Record<string, { min: number; money: number; seed: number; exp: number; kindName: string }> = {
  sell: { min: 1.0,  money: 1.0,  seed: 0.50, exp: 0.2, kindName: '纯卖钱草' },   // 出售主出口（种子 0.70 见下 sellSeed）
  cult: { min: 1.25, money: 0.2,  seed: 0.50, exp: 1.0, kindName: '纯修为草' },   // 只加修为
  mix:  { min: 1.5,  money: 0.6,  seed: 1.50, exp: 1.0, kindName: '综合草' }, // R-115 [r115price]：加属性作物种子价大幅提升（0.50→1.50，成本 ×3.00）     // 修为 + 2~3 基础属性
  rare: { min: 2.0,  money: 0.5,  seed: 2.00, exp: 0.5, kindName: '稀有百分比草' }, // R-115 [r115price]：加属性作物种子价大幅提升（0.56→2.00，成本 ×3.57） // 修为 + 1~2 百分比属性（有上限）
};
// 纯修为草「服用·修为」直表（§2.5-A，★已按 T7 §3.5 铁律单独下调：200/800/3000/10000/30000 → 下表）
const FARM_CROP_EXP_PURE: Record<number, number> = { 1: 63000, 2: 189000, 3: 630000, 4: 2016000, 5: 5670000 }; // R-129 [r129farm]：纯修为草服用修为 = 打坐2h×(min/120)（凡63,000/灵189,000/玄630,000/仙2,016,000/神5,670,000）
// 综合草「服用·修为」玄/仙保序微调（§2.5-A：1,500→1,400 / 5,000→4,400，为保「纯修为 > 综合」的 §4.3 断言）
// R-129 [r129farm]：新值按「终值 = 0.9 × 同阶纯修为草」反推（tf=mix 1.5 在 farmCropDefs 内后乘）：378,000×1.5=567,000 / 1,209,600×1.5=1,814,400
const FARM_CROP_EXP_MIX_ADJ: Record<number, number> = { 3: 378000, 4: 1209600 }; // R-129 [r129farm] 终值 567,000/1,814,400
const FARM_CROP_TIERS = ['凡品', '灵品', '玄品', '仙品', '神品'];
// 品阶解锁门槛（复用洞府等级；★与 T10 地块门槛 FARM_UNLOCK_GROTTO_LEVEL={4:5,5:7,6:9} 错位，避免同一门槛卡两件事）
const FARM_CROP_TIER_LEVEL: Record<number, number> = { 1: 1, 2: 1, 3: 3, 4: 5, 5: 7 };
// T5 新 20 种（key 刻意避开既有物品名：聚灵草/血参/回气草/凝神花/龙鳞果/千年灵芝/九叶芝草/… 零碰撞）
const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {
  linggusi:       { t: 1, k: 'sell' }, // 凡品 · 灵谷穗
  ziwenlingdao:   { t: 2, k: 'sell' }, // 灵品 · 紫纹灵稻
  jinsuiteng:     { t: 3, k: 'sell' }, // 玄品 · 金髓藤
  xianyulian:     { t: 4, k: 'sell' }, // 仙品 · 仙玉莲
  shencangjinshen:{ t: 5, k: 'sell' }, // 神品 · 神藏金参
  peiyuancao:     { t: 1, k: 'mix' },  // 凡品 · 培元草
  zhuangguhua:    { t: 2, k: 'mix' },  // 灵品 · 壮骨花
  bailianzhi:     { t: 3, k: 'mix' },  // 玄品 · 百炼芝
  jiugiaoxuanzhi: { t: 4, k: 'mix' },  // 仙品 · 九窍玄芝
  wanxianghua:    { t: 5, k: 'mix' },  // 神品 · 万象花
  yinqimiao:      { t: 1, k: 'cult' }, // 凡品 · 引气苗
  ningyuanzhi:    { t: 2, k: 'cult' }, // 灵品 · 凝元芝
  xuanyuanguo:    { t: 3, k: 'cult' }, // 玄品 · 玄元果
  taiqingguo:     { t: 4, k: 'cult' }, // 仙品 · 太清果
  hunyuandaoguo:  { t: 5, k: 'cult' }, // 神品 · 混元道果
  jifengye:       { t: 3, k: 'rare' }, // 玄品 · 疾风叶
  xuepohua:       { t: 4, k: 'rare' }, // 仙品 · 血魄花
  xingyunhua:     { t: 4, k: 'rare' }, // 仙品 · 星陨花
  dongxuanhua:    { t: 5, k: 'rare' }, // 神品 · 洞玄花
  bumieteng:      { t: 5, k: 'rare' }, // 神品 · 不灭藤
};
const FARM_CROPS_NEW_NAME: Record<string, string> = {
  linggusi: '灵谷穗', ziwenlingdao: '紫纹灵稻', jinsuiteng: '金髓藤', xianyulian: '仙玉莲', shencangjinshen: '神藏金参',
  peiyuancao: '培元草', zhuangguhua: '壮骨花', bailianzhi: '百炼芝', jiugiaoxuanzhi: '九窍玄芝', wanxianghua: '万象花',
  yinqimiao: '引气苗', ningyuanzhi: '凝元芝', xuanyuanguo: '玄元果', taiqingguo: '太清果', hunyuandaoguo: '混元道果',
  jifengye: '疾风叶', xuepohua: '血魄花', xingyunhua: '星陨花', dongxuanhua: '洞玄花', bumieteng: '不灭藤',
};
// 综合草「服用·基础属性」（§3.2：2~3 项；键=服务端存档字段名）
const FARM_CROP_ATTRS: Record<string, Array<{ key: string; label: string }>> = {
  peiyuancao:     [{ key: 'maxHp', label: '气血' }, { key: 'defense', label: '体魄' }],
  zhuangguhua:    [{ key: 'maxHp', label: '气血' }, { key: 'defense', label: '体魄' }], // R-124：原第三项 { defense,防御 } 与第二项同键重复 ⇒ 服用防御被 +30 两次（实得 +60），去重后单次 +30 [r124attrfix]
  bailianzhi:     [{ key: 'attack', label: '攻击' }, { key: 'defense', label: '防御' }, { key: 'maxHp', label: '气血' }],
  jiugiaoxuanzhi: [{ key: 'attack', label: '攻击' }, { key: 'maxHp', label: '气血' }, { key: 'spirit', label: '神识' }],
  wanxianghua:    [{ key: 'attack', label: '攻击' }, { key: 'defense', label: '防御' }, { key: 'maxHp', label: '气血' }],
};
// 稀有草「服用·百分比属性」（§3.4；pct 为百分点数值，如 0.4 = +0.4%）。
// ★ 落地裁剪（策划案 §9.2）：客户端 YLXW_FT_PCT 只认 critRate / dodgeRate / lifeLeech 三键，
//   且存档中只有这三键参与战斗结算。策划案原案的次级项（速度/气血/攻击的百分比）无对应存档字段
//   ⇒ 本期**不生成**，避免写进存档的僵尸字段；主项数值不变（仅洞玄花因命中未接而折算为暴击，见下）。
const FARM_CROP_PCT: Record<string, Array<{ key: string; label: string; pct: number }>> = {
  jifengye:   [{ key: 'dodgeRate', label: '闪避率', pct: 0.4 }],
  xuepohua:   [{ key: 'lifeLeech', label: '吸血率', pct: 0.8 }],
  xingyunhua: [{ key: 'critRate', label: '暴击率', pct: 1.0 }],
  // ★ 洞玄花：策划案原案为「命中 +1.2% / 暴击 +0.6%」，但命中率尚未接进战斗结算
  //   （策划案 §9.2 实测：命中多为文案）⇒ 本期按 §9.2 落地建议折算为「暴击 +1.8%」，
  //   **不生成任何空转的命中草**（上限表保留命中项占位，供后续批次直接启用）。
  dongxuanhua:[{ key: 'critRate', label: '暴击率', pct: 1.8 }],
  bumieteng:  [{ key: 'lifeLeech', label: '吸血率', pct: 1.0 }, { key: 'dodgeRate', label: '闪避率', pct: 0.6 }],
};
// ★ 百分比属性硬上限（§2.5-C：灵田「服用」来源累计，独立于装备/称号）。
//   单位为**百分点**（critRate: 8 = +8%）；玩家存档里这些键存的是**小数比例**（0.08 = 8%）
//   ⇒ farmCropConsume 内做 ×100 归一后再比对，避免单位错配导致上限永不触发。
const FARM_CROP_ATTR_CAP: Record<string, number> = { hitRate: 8, critRate: 8, dodgeRate: 6, lifeLeech: 4 };
// R-047：灵田双出口收益倍率（变卖 → 灵石 / 服用 → 修为）[r047yield]
//   只放大 farmCropDefs() 的产出（stones / exp）；种子价 seed 与成熟时长 minutes 不动。
//   ★ 这是**纯单位时间增益**（时长不变）⇒ 满配日净放大 >倍率本身，见本文件头与报告复算。
const FARM_YIELD_MUL = 1.0; // R-129 [r129farm]：修为侧倍率归 1（修为收益改走 expBase/PURE/ADJ 新表，对标打坐2h，不再二次放大）
const FARM_STONES_MUL = 10; // R-129 [r129farm]：灵石侧收益 ×10（纯灵石大幅提升；种子价 seed / 成熟时长 minutes 不经此乘数，与 r047 同口径）

// R-048：灵草分三档——综合草（mix）×1.5 / 稀有草（rare）×2.5；成熟时长与收益同倍放大。[r048tier]
//   普通（sell/cult）不动。倍率在下方 farmCropDefs() 内施加；种子价 seed 不动。
const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };
// R-048：特殊属性（rare）灵草种植门槛 = 元婴期（境界序下标 3 / 共 7 档）
const FARM_CROP_RARE_REALM = 3;
// R-048：是否特殊属性（rare）草（供 /api/farm/plant 门槛判定；非 rare 恒 false）
function farmCropIsRare(key: string): boolean {
  const c = FARM_CROPS_NEW[asStr(key)];
  return !!c && c.k === 'rare';
}
// R-048：从存档取玩家境界序（读法与 farmGrottoInfo 同款；解析失败/缺档按 0 = 最低境）
function farmRealmIndexOf(saveDataJson: string | null | undefined): number {
  try {
    const r = JSON.parse(saveDataJson || '{}')?.player?.realm;
    const i = REALM_ORDER_FOR_RANKING.indexOf(asStr(r));
    return i >= 0 ? i : 0;
  } catch { return 0; }
}
// T5：作物定义生成器（纯函数，零副作用；每次调用重算，25 项规模可忽略）。
//   返回结构与旧 FARM_CROPS 逐字段同形（name/seed/minutes/stones/exp/grottoLevel）。
//   ⚠ 修正（2026-09-29）：**"plant / farmCrop 零改动即可消费" 是错的** —— 该假设正是本环 P0 的病根。
//     本生成器产出的 25 键表必须被 farmCrop() **显式消费**（见下方 farmCrop 定义），
//     否则 /api/farm/plant 的 `if (!crop) return 400 '未知作物'` 会把 20 个新种全部拒掉。
//     客户端渲染走 status.crops（已是 25 键）本就无需改动，但**服务端 farmCrop 必须改**。
//   ★ exp 字段按产品线分流（§2.5-A）：纯修为草取直表；综合草 = E(品阶) × 1.0（玄/仙保序微调）；
//     稀有草 = E(品阶) × 0.5；纯卖钱草 = E(品阶) × 0.2。
function farmCropDefs(): Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number }> {
  const out: Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number }> = {};
  out.lingcao = FARM_CROPS.lingcao;
  out.lingzhi = FARM_CROPS.lingzhi;
  out.qianniancan = FARM_CROPS.qianniancan;
  out.taixuguo = FARM_CROPS.taixuguo;
  out.zaohuaqinglian = FARM_CROPS.zaohuaqinglian;
  // ★ 旧种 retired 标记（0.8.9 补丁）：crops 目录里「已停种」品种带 retired: true。
  //   客户端（yl_farm089_ext.py:170 `g = (t && t.crops) || {}, h = Object.keys(g)` 逐键画按钮）
  //   据此把按钮置灰，不再让玩家点了吃 409「该灵草品种已停止栽种」。
  //   ★ 条目**必须保留、不许删**：存量已种下的旧田仍按旧口径正常收获，槽位回显需要作物名。
  //   ★ 判据与 plant 端点同源（farmCropNoPlant ⇒ isLegacyCrop）⇒「标的」恒等于「拒播的」。
  //   ★ 5 个旧种**全标**：lingcao/lingzhi/qianniancan（0.8.7 旧种）+ taixuguo/zaohuaqinglian
  //     （T10 高阶种）—— 后两者同样被 plant 409 拒掉，不标则客户端照样画成可点按钮。
  for (const legacyKey of Object.keys(out)) {
    if (isLegacyCrop(legacyKey)) out[legacyKey] = Object.assign({}, out[legacyKey], { retired: true });
  }
  for (const key of Object.keys(FARM_CROPS_NEW)) {
    const c = FARM_CROPS_NEW[key], b = FARM_CROP_BASE[c.t], k = FARM_CROP_KIND[c.k];
    if (!b || !k) continue;
    const tf = FARM_CROP_TIER_MUL[c.k] || 1; // R-048 档位倍率（mix 1.5 / rare 2.5 / 其余 1）
    const min = Math.round(Math.max(120, Math.ceil((b.min * k.min) / 30) * 30) * tf); // R-048 成熟时长同倍放大
    const stones = Math.round(b.sell * k.money);
    // 种子系数：纯卖钱草 0.70，其余三线 0.50（§2.4）
    const cs = c.k === 'sell' ? 0.70 : k.seed;
    const gl = FARM_CROP_TIER_LEVEL[c.t] || 1;
    // 服用·修为（§2.5-A）：纯修为草直表；综合草玄/仙保序微调；其余 = round(E × e)
    let cexp: number;
    if (c.k === 'cult') cexp = FARM_CROP_EXP_PURE[c.t] || 0;
    else if (c.k === 'mix' && (c.t === 3 || c.t === 4)) cexp = FARM_CROP_EXP_MIX_ADJ[c.t];
    else cexp = Math.round(b.expBase * k.exp);
    out[key] = { name: FARM_CROPS_NEW_NAME[key] || key, seed: Math.round(stones * cs), minutes: min, stones: Math.round(stones * tf), exp: Math.round(cexp * tf), grottoLevel: gl > 1 ? gl : undefined };
  }
  // R-047：双出口收益按倍率放大（变卖灵石 / 服用修为；seed 与 minutes 原样保留）
  for (const _r47k of Object.keys(out)) {
    const _r47d = out[_r47k];
    out[_r47k] = Object.assign({}, _r47d, {
      stones: Math.round(Number(_r47d.stones) * FARM_STONES_MUL), // R-129 [r129farm] 灵石侧改乘 FARM_STONES_MUL(×10)；exp 行仍乘 FARM_YIELD_MUL(=1.0)
      exp: Math.round(Number(_r47d.exp) * FARM_YIELD_MUL),
    });
  }
  return out;
}
// T5：变卖出口定价（纯）：与收获结算同源（farmYield 基准 × 洞府/照料乘区，提前减半）——
//   供 UI 在「尚未收获」时预告两种出口到手值；权威口径始终在 farmHarvestOne 内复算。
function farmCropSell(key: string): number {
  const d = farmCropDefs()[key];
  return d ? Math.max(0, Math.floor(Number(d.stones) || 0)) : 0;
}
// T5：服用出口效果（纯）：修为 + 基础属性 + 百分比属性（含硬上限值与已满标记，供 UI 置灰）。
//   owned = 玩家当前存档 player（可空）；上限按「灵田服用累计」字段实算，触顶项给 capped:true。
function farmCropConsume(key: string, owned?: any): { exp: number; attrs: Array<{ key: string; label: string; add: number }>; pcts: Array<{ key: string; label: string; pct: number; cap: number; capped: boolean }> } {
  const d = farmCropDefs()[key];
  if (!d) return { exp: 0, attrs: [], pcts: [] };
  const cnt = FARM_CROPS_NEW[key];
  const p = owned && typeof owned === 'object' ? owned : {};
  const attrs: Array<{ key: string; label: string; add: number }> = [];
  const pcts: Array<{ key: string; label: string; pct: number; cap: number; capped: boolean }> = [];
  if (cnt && cnt.k === 'mix') {
    const per = FARM_CROP_BASE[cnt.t].attr;
    for (const a of (FARM_CROP_ATTRS[key] || [])) attrs.push({ key: a.key, label: a.label, add: per });
  }
  if (cnt && cnt.k === 'rare') {
    for (const a of (FARM_CROP_PCT[key] || [])) {
      const cap = Number(FARM_CROP_ATTR_CAP[a.key] || 0); // 百分点（如 8）
      // ★ 单位归一：存档里 critRate 等存的是小数比例（0.08 = 8%）⇒ ×100 转百分点再与 cap 比对
      const curPct = Math.max(0, Number(p[a.key]) || 0) * 100;
      pcts.push({ key: a.key, label: a.label, pct: a.pct, cap, capped: cap > 0 && curPct >= cap - 1e-9 });
    }
  }
  return { exp: Math.max(0, Math.floor(Number(d.exp) || 0)), attrs, pcts };
}
// T5：旧种禁止新播（存量兼容：已种下的旧田不受影响，仍走 farmCrop 旧口径收获）
function farmCropNoPlant(key: string): boolean {
  return !Object.prototype.hasOwnProperty.call(FARM_CROPS_NEW, key);
}
const FARM_UNLOCK_COST: Record<number, number> = { 2: 20000, 3: 80000, 4: 200000, 5: 800000, 6: 2000000 }; // 开垦价（slot 1 免费，不在表内；物价×10；4/5/6=T10 建议锚值，★待 #5 定档）
// ─────────────────────────────────────────────────────────
// T10 灵田扩充（0.8.7 t10_farm）：照料/催熟/虫害/连作/洞府联动常量
// ★ 以下全部「建议锚值」，待《数值表-T9T10.md》定档回填（#3~#7/#10）——定档只改这里，端点零改动
// ─────────────────────────────────────────────────────────
const FARM_UNLOCK_GROTTO_LEVEL: Record<number, number> = { 4: 5, 5: 7, 6: 9 }; // #4 地块洞府门槛（建议 L5/L7/L9，与 T9 表同一套档）
const FARM_GROTTO_BONUS_PER_LEVEL = 0.01;  // #3 灵田产出加成/级（建议 +1%/级线性；服务端按存档 grotto.level 实算）
const FARM_GROWTH_BONUS_COEF = 0.5;        // #10 洞府 growthSpeedBonus→灵田成熟时长折算系数（建议 ×0.5 防双吃）
// ★ T5（0.8.9）item4 照料口径改档：每日 1 次 → 每 2 小时 1 次，但每次只 +2%、
//   单田当日累计上限 +10%（总收益量与 0.8.7 完全一致，只是更频繁、更易参与）。
//   ★ 红线耦合：若沿用旧「每次 +10% × 12 次/日」则满配乘区 → ×2.2，117,612 会变 213,840，必破 150,000。
const FARM_TEND_PER = 0.02;                // #7 照料单次收获加成（+2%/次，每 2 小时可照料 1 次）
const FARM_TEND_CAP = 0.10;                // #7 照料单田当日累计加成上限（+10%，与 0.8.7 总收益同口径）
const FARM_PEST_RATE = 0.30;               // #7 虫害概率（建议 30%；确定性 hash 可复算）
const FARM_PEST_PENALTY = 0.20;            // #7 虫害未照料收获减产（建议 -20%）
const FARM_STREAK_DECAY_2 = 0.15;          // #9 连作第 2 茬产出衰减（建议 -15%）
const FARM_STREAK_DECAY_3 = 0.30;          // #9 连作第 3+ 茬产出衰减（建议 -30%）
const FARM_BOOST_MIN_COST = 1000;          // #6 催熟起价（同洞府加速 Br.minCost=1000）
const FARM_BOOST_COST_PER_MIN = 100;       // #6 催熟单价/剩余分钟（同 Br.costPerMinute=100；纯灵石回收口）
const FARM_BOOST_BASE_CAP = 10;             // #6 每日催熟总次数基础值（R-050：逐级 +3/+2，见 farmBoostCap）
function farmCrop(key: unknown): { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number } | null {
  // ★ T5 修复（2026-09-29）：查 farmCropDefs()（25 键 = 5 旧兼容 + 20 新），**不再查旧 FARM_CROPS（5 键）**。
  //   旧种不可新播由 farmCropNoPlant() 单独判定，与本函数正交 ⇒ 旧种仍走 409 retired。
  if (key == null) return null;
  const k = asStr(key);
  const defs = farmCropDefs();
  return Object.prototype.hasOwnProperty.call(defs, k) ? defs[k] : null;
}
// 田位（纯）：1..FARM_SLOTS 整数合法（Number 宽容数字字符串，与 alchemySlotOk 同口径）
function farmSlotOk(raw: unknown): boolean {
  const s = asNum(raw);
  return Number.isInteger(s) && s >= 1 && s <= FARM_SLOTS;
}
function farmMatureAt(startMs: number, minutes: number): number {
  return startMs + Math.max(1, Math.floor(Number(minutes) || 1)) * 60 * 1000;
}
// 成熟判定（纯）：恰好到点算成熟（>=），提前收获不减产为 0 而是减半（玩家自选止损）
function farmIsReady(matureAt: number, nowMs: number): boolean { return nowMs >= matureAt; }
// 收益（纯）：到期=全额；提前收获=减半（两项独立 floor）
// T10：mods 乘区（缺省 undefined = 乘区全 1 / 无虫害 ⇒ 0.8.6 口径逐位不变）：
//   产出 = floor(base × (1+grottoBonus) × (1+tendBonus) × (1−streakDecay−pest))，提前减半照旧在最外层
function farmYield(crop: { stones: number; exp: number }, early: boolean, mods?: { grottoBonus?: number; tendBonus?: number; streakDecay?: number; pest?: boolean }): { stones: number; exp: number } {
  const m = mods || {};
  const mul = (1 + Math.max(0, Number(m.grottoBonus) || 0)) * (1 + Math.max(0, Number(m.tendBonus) || 0));
  const dec = Math.min(0.9, Math.max(0, Number(m.streakDecay) || 0) + (m.pest ? FARM_PEST_PENALTY : 0));
  const s = Math.max(0, Math.floor((Number(crop.stones) || 0) * mul * (1 - dec)));
  const e = Math.max(0, Math.floor((Number(crop.exp) || 0) * mul * (1 - dec)));
  return early ? { stones: Math.floor(s / 2), exp: Math.floor(e / 2) } : { stones: s, exp: e };
}
// T10 连作衰减（纯）：streak=同田同作物连续茬数（由 spirit_farm harvested=1 历史行推导，零新表）
function farmStreakDecayOf(streak: number): number {
  return streak >= 2 ? FARM_STREAK_DECAY_3 : (streak === 1 ? FARM_STREAK_DECAY_2 : 0);
}
// T10 虫害（纯，确定性伪随机）：FNV-1a hash(playerId,slot,crop,plantedAt,bjDate) 取模 < 虫害率。
// 同输入恒同结果 ⇒ status 与 harvest 各自复算恒一致，零 cron 零落库（服务端权威，客户端不判权）
function farmPestToday(playerId: number, slot: number, cropKey: string, plantedAt: number, date: string): boolean {
  const key = playerId + '|' + slot + '|' + cropKey + '|' + plantedAt + '|' + date;
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) { h ^= key.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) % 10000 < Math.round(FARM_PEST_RATE * 10000);
}
// T10 催熟费（纯）：max(起价, 剩余分钟×单价)——公式同构洞府加速 Br={minCost:1000,costPerMinute:100}，
// 常量独立不引客户端符号；催熟是纯灵石回收口（全周期催熟费恒高于作物净收益，不构成刷钱口）
function farmBoostCost(leftMs: number): number {
  return Math.max(FARM_BOOST_MIN_COST, Math.ceil(Math.max(0, leftMs) / 60000) * FARM_BOOST_COST_PER_MIN);
}
// T10 每日催熟总次数上限（纯）：基础 10 + 逐级 +3/+2（L1=10…L10=32）（#6；与客户端洞府页联动展示同式）[r050boost] R-050：基础 3→10 且公式改逐级 +3/+2（客户端两处展示同步见 yl_050_ext.py）
function farmBoostCap(grottoLevel: number): number {
  return FARM_BOOST_BASE_CAP + 3 * Math.min(Math.max(0, grottoLevel - 1), 4) + 2 * Math.max(0, grottoLevel - 5);
}
// T10 洞府灵田产出加成（纯）：+1%/级线性（#3），等级钳 0..10
function farmGrottoBonusOf(grottoLevel: number): number {
  return Math.min(10, Math.max(0, grottoLevel)) * FARM_GROTTO_BONUS_PER_LEVEL;
}
// T10 洞府等级→可开垦地块上限（纯）：3 基础 + 已达门槛的 4/5/6 号田（#4；与客户端联动展示同式）
function farmSlotsForLevel(grottoLevel: number): number {
  let n = 3;
  for (let s = 4; s <= FARM_SLOTS; s++) { if (grottoLevel >= (FARM_UNLOCK_GROTTO_LEVEL[s] || Infinity)) n++; }
  return n;
}
// [/farmcore]

// [petcore] Y18 妖灵宠物纯逻辑核心（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
// 数值为本次定档，常量集中可调；hunger=喂食度（只增不减），level=floor(hunger/100)，出战加成保守落点见 PET_BATTLE_*
const PET_FEED_COST = 5000;

// T2SPIRIT089：以下常量为 T2 灵宠面板服务端权威面**共用**（品阶系数 / 融合费 / 成功率 / 保底 / 秘径消耗）。
//   纯逻辑（系数表 / 融合费 / 成功率 / 伪随机 / 视图投影）下沉到下方 [t2spirit] 块。
// （petcore 原有 9 个常量一字未动，本环只做加法。）       // 喂养一次消耗灵石（物价×10）
const PET_HUNGER_PER_FEED = 30;   // 每次喂养喂食度 +30
const PET_HUNGER_MAX = 9999;      // 喂食度上限（防无限膨胀；满仓 → 满级 99）
const PET_LEVEL_DIVISOR = 100;    // 升级公式 level = floor(hunger / 100)
const PET_PLAY_DAILY_MAX = 3;     // 每日嬉戏次数上限（pet_play_log PK(player_id,date) 单语句原子闸门）
const PET_PLAY_BOND = 5;          // 每次嬉戏羁绊 +5
const PET_BATTLE_LEVEL = 5;       // 出战加成门槛：level ≥5 触发一次性「妖灵精魄」（保守落点）
const PET_BATTLE_BOND = 20;       // 触发出战加成时的一次性 bond 提升（实际战斗数值加成待客户端接入）
const PET_BATTLE_STONES = 1000;   // 「妖灵精魄」邮件附灵石
const PET_CARE_LOG_KEEP = 50;     // 喂养记录保留条数（写入后裁剪，防表膨胀）
const PET_NAME_POOL: string[] = ['青鸾', '白泽', '貔貅', '九尾', '玄龟', '麒麟', '鲲鹏', '玉兔', '灵狐', '墨蛟'];
const PET_RARITIES = ['凡', '灵', '仙'];
// 品阶权重 凡85 / 灵12.5 / 仙2.5（物品概率÷2：灵 25→12.5、仙 5→2.5）：rng∈[0,1) 落 <0.85 → 凡、<0.975 → 灵、其余 → 仙（边界值归左区间）
function rollPetRarity(rng: () => number = Math.random): string {
  const r = rng();
  if (r < 0.85) return '凡';
  if (r < 0.975) return '灵';
  return '仙';
}
function rollPetName(rng: () => number = Math.random): string {
  const i = Math.floor(rng() * PET_NAME_POOL.length);
  return PET_NAME_POOL[Math.min(PET_NAME_POOL.length - 1, Math.max(0, i))];
}
function clampHunger(v: unknown): number {
  const n = Math.floor(Number(v) || 0);
  return Math.min(PET_HUNGER_MAX, Math.max(0, Number.isFinite(n) ? n : 0));
}
// 升级公式（纯）：level = floor(hunger/100)，hunger 已钳 0..9999 → level 0..99
function petLevel(hunger: unknown): number {
  return Math.floor(clampHunger(hunger) / PET_LEVEL_DIVISOR);
}
// 喂养结算（纯）：到上限拒喂（ok:false 不扣灵石）；未到则 +30 封顶，exp 镜像 hunger
function petFeedResult(hunger: unknown): { ok: boolean; hunger: number; exp: number; level: number } {
  const h = clampHunger(hunger);
  if (h >= PET_HUNGER_MAX) return { ok: false, hunger: h, exp: h, level: petLevel(h) };
  const nh = Math.min(PET_HUNGER_MAX, h + PET_HUNGER_PER_FEED);
  return { ok: true, hunger: nh, exp: nh, level: petLevel(nh) };
}
// 出战加成触发判定（纯，入参为等级）：从 <5 跨到 ≥5 恰好一次（hunger 只增不减，天然幂等无需标记位）
function petBattleReached(oldLevel: unknown, newLevel: unknown): boolean {
  const a = Math.floor(Number(oldLevel) || 0);
  const b = Math.floor(Number(newLevel) || 0);
  return a < PET_BATTLE_LEVEL && b >= PET_BATTLE_LEVEL;
}
// 每日嬉戏（纯）：times=今日已玩次数；恰好 3 次封顶
function petPlayNext(times: unknown): { allowed: boolean; times: number } {
  const t = Math.max(0, Math.floor(Number(times) || 0));
  return { allowed: t < PET_PLAY_DAILY_MAX, times: Math.min(PET_PLAY_DAILY_MAX, t + 1) };
}
// 嬉戏日期（纯）：北京时区 YYYY-MM-DD（与 daily_quests/stats_daily 同口径跨日）
function petDate(ms: number): string {
  return new Date(ms + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);
}
// 喂养/嬉戏流水文案（钳 60 字，伴生页喂养记录展示用）
function clampPetDetail(t: unknown): string { return asStr(t).slice(0, 60); }
// [/petcore]
// [t2spirit] T2 灵宠面板服务端权威纯逻辑（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
//
// 权威边界（策划 §2.1 P2「不新增权威源」）：
//   * 灵宠属性（affection / evolutionStage / exp / 技能）唯一事实源 = 客户端存档 player.pets；
//     本块**只做投影与结算定价**，不落任何属性库。
//   * 服务端权威面 = ① 视图投影（§2.3 / §3.1 公开系数）② 融合费（§2.4 + 用户 2026-09-29 指示）
//     ③ 融合成功率 / 失败保底（§2.4，确定性非赌博 P3）④ 融合落库动作（扣灵石 + 材料消耗 + 标记）。
//   * 属性继承（等级取高 / 阶段晋升 / 技能继承）按 P2 归客户端存档域 ⇒ 服务端只回 inheritHints。

// ── 品阶：服务端 pets.rarity 只有 凡/灵/仙 三档（rollPetRarity :5186）──
//   策划案 §2.4 / §3 用四档（普/稀/传/仙）描述客户端 23 物种的品阶。
//   映射：凡→普通(0) / 灵→稀有(1) / 仙→仙品(3)。**传说(2) 服务端不可达**（rollPetRarity 不产出）。
const PET_RARITY_IDX: Record<string, number> = { '凡': 0, '灵': 1, '仙': 3 };
const PET_RARITY_CN: Record<string, string> = { '凡': '普通', '灵': '稀有', '仙': '仙品' };
// T2 品阶序号显示名（普0/稀1/传2/仙3）——按**序号**取，供副宠品阶序号 → 中文名。
const PET_RARITY_KO: string[] = ['普通', '稀有', '传说', '仙品'];
// 进化阶段（策划 §1.2 evolutionStage 0→1→2）
const PET_STAGE_CN: string[] = ['幼年期', '成熟期', '完全体'];
// T2 消耗定价（策划 §3.1 / §2.4；round100 取整到百位）
const PET_T2_COST_BASE = 10000;             // ← 用户 2026-09-29：基础 10000 灵石起
const PET_T2_PATH_BASE = 7500;              // 0.8.10\uff1a\u79d8\u5f84\u57fa\u7840 10000 \u2192 7500\uff08\u7528\u6237\u8981\u6c42\uff09\uff1b\u878d\u5408\u4ecd 10000
const PET_T2_AFFECTION_DIVISOR = 2000;      // 亲密度弱因子：1 + aff/2000 → ×1.00~×1.05（≤5%）
// 秘径品阶因子（策划 §3.1 P品阶，主因子 1.6× 跨度）
const PET_FUSE_RARITY_MULT: Record<string, number> = { '凡': 1.00, '灵': 1.20, '仙': 1.60 };
// 秘径阶段因子（策划 §3.1 P阶段，次因子 1.25×）
const PET_FUSE_STAGE_MULT: number[] = [1.00, 1.10, 1.25];
// 融合费：主宠品阶因子（对齐 §3.1，服务端三档；用户「消耗根据品阶为主」）
const PET_MERGE_RARITY_MULT: Record<string, number> = { '凡': 1.00, '灵': 1.20, '仙': 1.40 };
// 融合成功率（策划 §2.4 逐字）
const PET_MERGE_RATE_SAME = 0.70;
const PET_MERGE_RATE_LOW_STEP = 0.15;       // 副宠低阶：+15% × 品阶差
const PET_MERGE_RATE_HIGH_STEP = 0.20;      // 副宠高阶：-20% × 品阶差
const PET_MERGE_RATE_MIN = 0.20;
const PET_MERGE_RATE_MAX = 1.00;
// 失败保底（策划 §2.4）：连续失败 3 次后第 4 次必成功。计数落 pets.merge_pity（服务端权威）
const PET_MERGE_PITY_LIMIT = 3;

// 品阶序号（纯）：凡0 / 灵1 / 仙3；未知名归一为 0（防御外部脏值）
function petRarityIdx(rarity: unknown): number {
  const k = String(rarity);
  return Object.prototype.hasOwnProperty.call(PET_RARITY_IDX, k) ? PET_RARITY_IDX[k] : 0;
}
// round100（纯）：取整到百位，四舍五入（≥50 进）—— 策划 §3.1 round100
function petRound100(n: number): number {
  const v = Math.floor(Number(n) || 0);
  return Math.floor((v + 50) / 100) * 100;
}
// 亲密度（纯）：由服务端 bond 派生 —— 策划 §2.7 步骤 1「亲密度 = min(100, floor(bond/2))」
function petT2Affection(bond: unknown): number {
  const b = Math.max(0, Math.floor(Number(bond) || 0));
  return Math.min(100, Math.floor(b / 2));
}
// 亲密度弱因子（纯）：1 + aff/2000 → 0~100 ⇒ ×1.00~×1.05
function petT2AffectionMult(affection: number): number {
  const a = Math.min(100, Math.max(0, Math.floor(Number(affection) || 0)));
  return 1 + a / PET_T2_AFFECTION_DIVISOR;
}
// 秘径消耗（纯）：round100(10000 × P品阶 × P阶段 × P亲密度) —— 策划 §3.1/§3.2 逐条落地
//   evolutionStage 由调用方传入（服务端无该列 ⇒ 取 0，只出该品阶最低档，见文件头「口径差异 1」）
function petT2ExpeditionCost(rarity: unknown, stage: unknown, affection: number): number {
  const si = Math.min(2, Math.max(0, Math.floor(Number(stage) || 0)));
  const rk = String(rarity);
  const rm = Object.prototype.hasOwnProperty.call(PET_FUSE_RARITY_MULT, rk) ? PET_FUSE_RARITY_MULT[rk] : 1.00;
  return petRound100(PET_T2_PATH_BASE * rm * PET_FUSE_STAGE_MULT[si] * petT2AffectionMult(affection)); // [v2810] \u79d8\u5f84\u57fa\u7840 7500
}
// 融合费（纯）：round100(10000 × M品阶(主) × (1 + 副宠品阶序号/3) × P亲密度)
//   —— 策划 §2.4 基础由 3000 提到 10000（用户 2026-09-29「基础改为 10000 灵石起」）；
//      副宠跨度由「1 + 序号」（4.0×）压缩到「1 + 序号/3」（2.0×），落实「整体幅度不要太大」。
function petT2MergeCost(rarity: unknown, subRarityIdx: number, affection: number): number {
  const rk = String(rarity);
  const mm = Object.prototype.hasOwnProperty.call(PET_MERGE_RARITY_MULT, rk) ? PET_MERGE_RARITY_MULT[rk] : 1.00;
  const si = Math.min(PET_RARITY_KO.length - 1, Math.max(0, Math.floor(Number(subRarityIdx) || 0)));
  return petRound100(PET_T2_COST_BASE * mm * (1 + si / 3) * petT2AffectionMult(affection));
}
// 融合成功率（纯）：策划 §2.4 —— 副宠低阶稳（上限 100%）、同阶 70%、高阶险（下限 20%）
function petT2MergeRate(mainIdx: number, subIdx: number): number {
  const a = Math.floor(Number(mainIdx) || 0);
  const b = Math.floor(Number(subIdx) || 0);
  const d = b - a;
  let r: number;
  if (d < 0) r = PET_MERGE_RATE_SAME + PET_MERGE_RATE_LOW_STEP * (-d);
  else if (d > 0) r = PET_MERGE_RATE_SAME - PET_MERGE_RATE_HIGH_STEP * d;
  else r = PET_MERGE_RATE_SAME;
  return Math.min(PET_MERGE_RATE_MAX, Math.max(PET_MERGE_RATE_MIN, r));
}
// 是否触发保底（纯）：连续失败 >= 3 后调用必成功（策划 §2.4「连续失败 3 次，第 4 次必成功」）
function petT2PityDue(pity: unknown): boolean {
  return Math.max(0, Math.floor(Number(pity) || 0)) >= PET_MERGE_PITY_LIMIT;
}
// 伪随机（纯）：Node crypto 可用则用之，否则 Math.random（不引新依赖）
function petT2Roll(): number {
  try {
    const c: any = (globalThis as any)?.crypto;
    if (c && typeof c.getRandomValues === 'function') {
      const u = new Uint32Array(1);
      c.getRandomValues(u);
      return (u[0] >>> 0) / 4294967296;
    }
  } catch { /* 无 crypto 时退化为 Math.random，不影响正确性 */ }
  return Math.random();
}
// 视图投影（纯）：pets 行 → T2 灵宠面板卡（策划 §2.3 / §3.1 / §2.7 逐条）
//   ★ 只读投影，不落库；主宠口径 = 服务端每玩家唯一一行（策划 §2.2 主战宠）
function petT2SpiritView(p: any): any {
  if (!p) return null;
  const hunger = Math.max(0, Math.floor(Number(p.hunger) || 0));
  const lv = Math.floor(hunger / PET_LEVEL_DIVISOR);
  const rIdx = petRarityIdx(p.rarity);
  const aff = petT2Affection(p.bond);
  // 气血 / 修为上限（策划 §3.4 新口径的规模基准；服务端无 evolutionStage ⇒ 恒幼年期档）
  const maxHp = 1200 + lv * 20;
  const maxExp = 1200 + lv * 200;
  const stage = 0; // 服务端无 evolutionStage 列 ⇒ 恒幼年期（见文件头「口径差异 1」）
  return {
    name: String(p.name),
    rarity: String(p.rarity),
    rarityIdx: rIdx,
    rarityCn: PET_RARITY_CN[String(p.rarity)] || PET_RARITY_CN['凡'],
    rarityKo: PET_RARITY_KO[Math.min(PET_RARITY_KO.length - 1, rIdx)],
    evolutionStage: stage,
    stageName: PET_STAGE_CN[stage],
    level: lv,
    // 亲密度（策划 §2.7 步骤 1）：bond/2 钳 0..100
    affection: aff,
    // 气血 / 修为（策划 §3.4 口径：幼年期系数 0.11 / 0.005，触底 100 / 50）
    maxHp,
    hp: Math.max(100, Math.floor(maxHp * 0.11)),
    maxExp,
    exp: Math.max(50, Math.floor(maxExp * 0.005)),
    // 喂养面（既有 Y18 字段，面板原样展示）
    hunger,
    bond: Math.max(0, Math.floor(Number(p.bond) || 0)),
    // 秘径消耗（该品阶幼年期档）+ 上限档（完全体 + 亲密度 100）夹住真实值
    fuseCost: petT2ExpeditionCost(p.rarity, stage, aff),
    fuseCostMax: petT2ExpeditionCost(p.rarity, 2, 100),
    // 融合费（该宠作主宠、以同品阶为副宠的基准档）
    mergeCost: petT2MergeCost(p.rarity, rIdx, aff),
    // 融合状态标记（策划 §2.7 步骤 1 的 merged 列语义）
    mergeMerged: Number(p.merged) || 0,
    mergePity: Math.max(0, Math.floor(Number(p.merge_pity) || 0)),
    isActive: true,
  };
}
// [/t2spirit]

// [r018] R-018 妖灵培养重设计（纯逻辑 + 端点；纯函数不引用本块外符号，可整块提取单测）
//   出口：妖灵之力 PP = 品阶K × 等级K × 羁绊K × 资质K（极差 11.25×）→ 主人属性加成
//         （写入存档 player.petSpirit；客户端 xt() 只读加算 ⇒ X0 / QS 两套战斗同时生效）
//   六维：D1 进食三档 / D2 互动三选+买额度 / D3 点化 / D4 秘径 / D5 灵纹（第二版）/ D6 归位
//   ★ 服务端权威；0 新增灵石 faucet（唯一灵石产出仍是既有「妖灵精魄」邮件）。
const R018_FEED_TIERS: Record<string, { cost: number; hunger: number; name: string }> = {
  common:   { cost: 3000,   hunger: 30,  name: '凡品·青草露' },
  fine:     { cost: 15000,  hunger: 150, name: '灵品·玉髓羹' },
  immortal: { cost: 60000,  hunger: 600, name: '仙品·九转灵丹' },
};
const R018_PLAY_KINDS: Record<string, { key: string; name: string; unlock: number; bond: number; extra: string; hunger: number; exp: number }> = {
  tease: { key: 'tease', name: '逗弄', unlock: 0,  bond: 5, extra: 'none',   hunger: 0,  exp: 0 },
  brush: { key: 'brush', name: '梳毛', unlock: 10, bond: 5, extra: 'hunger', hunger: 20, exp: 0 },
  talk:  { key: 'talk',  name: '夜话', unlock: 30, bond: 5, extra: 'exp',    hunger: 0,  exp: 200 },
};
const R018_BOND_MAX = 500;          // 羁绊封顶（决策点 4 = A）
const R018_APTITUDE_MAX = 100;      // 资质上限
const R018_APTITUDE_COST = 30000;   // 点化单次价（决策点 5 = A）
const R018_APTITUDE_STEP = 3;       // 随机 +1~3（均值 +2.0）
const R018_BUY_COST = 20000;        // 买互动额度单次价（决策点 7 = A）
const R018_BUY_DAILY_MAX = 2;       // 每日买额度上限
const R018_EXPED_COST = 5000;       // 秘径派遣价
const R018_EXPED_HUNGER = 80;       // 秘径归来喂食度
const R018_EXPED_BOND = 15;         // 秘径归来羁绊
const R018_EXPED_EXP = 800;         // 秘径归来修为（定值，不随境界/PP 缩放）
const R018_EXPED_MS = 4 * 60 * 60 * 1000; // 秘径时长 4 小时（决策点 6 = A）
const R018_MILESTONE_STEP = 10;     // 妖灵精魄：每 10 级一次（决策点 10 = C）
const R018_MILESTONE_BOND = 20;     // 每次里程碑 bond（与旧 PET_BATTLE_BOND 同值）
const R018_MILESTONE_STONES = 1000; // 每次里程碑邮件灵石（与旧 PET_BATTLE_STONES 同值）
const R018_CONVERT = 0.06;          // 转化率（决策点 3 = A）

// [r071] R-071 / R-072 / R-075 妖灵「收养 / 归位 / 放生」定价（本环新增 2 个消耗常量）
//   · 收养 20000 —— 与「买互动额度 / 灵兽远征」同档（同系统既有价格点），作妖灵入口门票；
//   · 归位 30000 —— 与「点化」同档（同系统既有价格点），归位产出可出战灵宠，属高价动作；
//   · 放生 0     —— 纯舍弃，不产出、不收费，只为腾出妖灵槽位重抽（见本环 S3 端点）。
//   ★ 两者都是**消耗**（0 新增灵石 faucet）；业务拒绝码一律 409。
const R071_ADOPT_COST = 20000;
const R071_AWAY_COST = 30000;

// 品阶 → PP 品阶K 的 b 值（凡 0 / 灵 1 / 仙 2）
function r018RarityB(rarity: unknown): number {
  const k = String(rarity);
  return k === '仙' ? 2 : (k === '灵' ? 1 : 0);
}
// 品阶K = 1 + 0.5b → 凡 1.00 / 灵 1.50 / 仙 2.50
function r018RarityK(rarity: unknown): number {
  return 1 + 0.5 * r018RarityB(rarity);
}
// 妖灵之力 PP = 品阶K × 等级K × 羁绊K × 资质K（保留 4 位小数，稳定可断言）
function r018SpiritPP(rarity: unknown, level: unknown, bond: unknown, aptitude: unknown): number {
  const lv = Math.max(0, Math.min(99, Math.floor(Number(level) || 0)));
  const bd = Math.max(0, Math.min(R018_BOND_MAX, Math.floor(Number(bond) || 0)));
  const ap = Math.max(0, Math.min(R018_APTITUDE_MAX, Math.floor(Number(aptitude) || 0)));
  const k = r018RarityK(rarity) * (1 + lv / 99) * (1 + bd / 1000) * (1 + ap / 200);
  return Math.round(k * 10000) / 10000;
}
// 妖灵本体属性（仅由 rarity + level 推导，不新增任何数据表）
function r018SpiritStats(rarity: unknown, level: unknown): { attack: number; defense: number; maxHp: number; speed: number } {
  const b = r018RarityB(rarity);
  const lv = Math.max(0, Math.min(99, Math.floor(Number(level) || 0)));
  return {
    attack:  Math.floor((30 + b * 20) * (1 + lv * 0.06)),
    defense: Math.floor((15 + b * 10) * (1 + lv * 0.06)),
    maxHp:   Math.floor((300 + b * 200) * (1 + lv * 0.06)),
    speed:   Math.floor((20 + b * 5) * (1 + lv * 0.03)),
  };
}
// 主人加成 = floor(妖灵属性 × 0.06 × PP)
function r018SpiritBonus(rarity: unknown, level: unknown, bond: unknown, aptitude: unknown): { pp: number; attack: number; defense: number; maxHp: number; speed: number } {
  const pp = r018SpiritPP(rarity, level, bond, aptitude);
  const s = r018SpiritStats(rarity, level);
  return {
    pp,
    attack:  Math.floor(s.attack  * R018_CONVERT * pp),
    defense: Math.floor(s.defense * R018_CONVERT * pp),
    maxHp:   Math.floor(s.maxHp   * R018_CONVERT * pp),
    speed:   Math.floor(s.speed   * R018_CONVERT * pp),
  };
}
// 灵食档位（缺省 common，向后兼容）
function r018FeedTier(tier: unknown): { cost: number; hunger: number; name: string } {
  const k = String(tier == null ? 'common' : tier);
  return Object.prototype.hasOwnProperty.call(R018_FEED_TIERS, k) ? R018_FEED_TIERS[k] : R018_FEED_TIERS.common;
}
// 互动种类（缺省 tease，向后兼容）
function r018PlayKind(kind: unknown): { key: string; name: string; unlock: number; bond: number; extra: string; hunger: number; exp: number } {
  const k = String(kind == null ? 'tease' : kind);
  return Object.prototype.hasOwnProperty.call(R018_PLAY_KINDS, k) ? R018_PLAY_KINDS[k] : R018_PLAY_KINDS.tease;
}
// 妖灵精魄里程碑（每 10 级一次）：返回跨过的里程碑等级列表（决策点 10 = C）
function r018Milestones(oldLevel: unknown, newLevel: unknown): number[] {
  const a = Math.floor(Number(oldLevel) || 0);
  const b = Math.floor(Number(newLevel) || 0);
  const out: number[] = [];
  for (let m = R018_MILESTONE_STEP; m <= 99; m += R018_MILESTONE_STEP) {
    if (a < m && b >= m) out.push(m);
  }
  return out;
}
// 重算并写入 player.petSpirit（服务端权威；客户端 xt() 只读加算）。
//   merged=1（已归位）或无 pet 行 ⇒ 清空 petSpirit（归位后不再提供加成）。
async function r018SpiritSync(userId: number): Promise<any> {
  const row: any = await dbGet('SELECT rarity, hunger, bond, aptitude, merged, rune_active FROM pets WHERE player_id = ?', [userId]);
  if (!row || Number(row.merged) > 0) {
    await updatePlayerSave(userId, (sd: any) => { if (sd.player) sd.player.petSpirit = null; });
    return null;
  }
  const level = petLevel(row.hunger);
  const payload = Object.assign({ level, rarity: String(row.rarity) }, r018bSpiritBonus(row.rarity, level, row.bond, row.aptitude, row.rune_active));
  await updatePlayerSave(userId, (sd: any) => { if (sd.player) sd.player.petSpirit = payload; });
  return payload;
}

// POST /api/pet/aptitude — 点化（D3）：扣 30000 灵石 → aptitude +1~3（上限 100）。
//   事务口径 = pet/feed 同款补偿式：预检 → 扣费（saveLock 互斥，二次校验）→ 原子 UPDATE → 行缺失补偿退费。
app.post('/api/pet/aptitude', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `pet:apt:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const pet: any = await dbGet('SELECT id, name, aptitude, merged FROM pets WHERE player_id = ?', [userId]);
    if (!pet) return res.status(404).json({ error: '请先收养一只灵宠' });
    if (Number(pet.merged) > 0) return res.status(409).json({ error: '妖灵已归位，无法再点化' });
    const cur = Math.max(0, Math.min(R018_APTITUDE_MAX, Math.floor(Number(pet.aptitude) || 0)));
    if (cur >= R018_APTITUDE_MAX) return res.status(409).json({ error: `资质已达上限 ${R018_APTITUDE_MAX}` });

    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    try { bal = Number(JSON.parse(row.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < R018_APTITUDE_COST) return res.status(409).json({ error: `灵石不足：需 ${R018_APTITUDE_COST}，现有 ${bal}` });

    const gain = 1 + Math.floor(petT2Roll() * R018_APTITUDE_STEP); // 1~3（均值 2.0）
    const next = Math.min(R018_APTITUDE_MAX, cur + gain);

    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < R018_APTITUDE_COST) { short = true; return; }
      sd.player.spiritStones = b - R018_APTITUDE_COST;
    });
    if (!paid.ok || short) {
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '点化失败，请重试') });
    }
    const upd = await dbRun('UPDATE pets SET aptitude = ? WHERE player_id = ?', [next, userId]);
    if (!upd.changes) {
      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + R018_APTITUDE_COST; });
      return res.status(404).json({ error: '请先收养一只灵宠' });
    }
    logPetCare(userId, 'aptitude', `点化「${String(pet.name)}」，资质 +${next - cur}（${cur} → ${next}）`);
    const spirit = await r018SpiritSync(userId);
    const fresh: any = await dbGet('SELECT name, rarity, hunger, exp, bond, aptitude, merged FROM pets WHERE player_id = ?', [userId]);
    res.json({ ok: true, pet: petView(fresh), aptitude: next, gain: next - cur, spirit });
  } catch (e: any) {
    console.error('pet aptitude error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/pet/spirit/exped — 秘径派遣（D4）：每日 1 次，扣 5000 灵石，记 started_at。
app.post('/api/pet/spirit/exped', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `pet:exped:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const pet: any = await dbGet('SELECT id, name, merged FROM pets WHERE player_id = ?', [userId]);
    if (!pet) return res.status(404).json({ error: '请先收养一只灵宠' });
    if (Number(pet.merged) > 0) return res.status(409).json({ error: '妖灵已归位，无法再派遣' });
    const date = petDate(Date.now());
    const row: any = await dbGet('SELECT started_at, claimed FROM pet_spirit_exped WHERE player_id = ? AND date = ?', [userId, date]);
    if (row && Number(row.claimed) > 0) return res.status(409).json({ error: '今日秘径已完成，明日再来' });
    if (row) return res.status(409).json({ error: '今日秘径已派遣，请先领取' });

    const srow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!srow) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    try { bal = Number(JSON.parse(srow.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < R018_EXPED_COST) return res.status(409).json({ error: `灵石不足：需 ${R018_EXPED_COST}，现有 ${bal}` });

    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < R018_EXPED_COST) { short = true; return; }
      sd.player.spiritStones = b - R018_EXPED_COST;
    });
    if (!paid.ok || short) {
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '派遣失败，请重试') });
    }
    const now = Date.now();
    const gate = await dbRun(
      `INSERT INTO pet_spirit_exped (player_id, date, started_at, claimed) VALUES (?, ?, ?, 0)
       ON CONFLICT(player_id, date) DO UPDATE SET started_at = excluded.started_at, claimed = 0`,
      [userId, date, now]
    );
    if (!gate.changes) {
      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + R018_EXPED_COST; });
      return res.status(409).json({ error: '今日秘径已派遣' });
    }
    logPetCare(userId, 'exped', `派遣「${String(pet.name)}」踏上秘径（${R018_EXPED_MS / 3600000} 小时）`);
    res.json({ ok: true, startedAt: now, readyAt: now + R018_EXPED_MS });
  } catch (e: any) {
    console.error('pet spirit exped error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/pet/spirit/exped/claim — 秘径领取：4h 到点后入账 hunger +80 / bond +15 / 修为 +800。
//   到点判定在**服务端**（客户端倒计时只是展示，不可信）。
app.post('/api/pet/spirit/exped/claim', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `pet:expedc:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const date = petDate(Date.now());
    const row: any = await dbGet('SELECT started_at, claimed FROM pet_spirit_exped WHERE player_id = ? AND date = ?', [userId, date]);
    if (!row) return res.status(404).json({ error: '今日尚未派遣秘径' });
    if (Number(row.claimed) > 0) return res.status(409).json({ error: '今日秘径已领取' });
    const now = Date.now();
    const startAt = Number(row.started_at) || 0;
    if (now < startAt + R018_EXPED_MS) {
      const left = Math.ceil((startAt + R018_EXPED_MS - now) / 60000);
      return res.status(409).json({ error: `秘径尚未归来（还需 ${left} 分钟）` });
    }
    const gate = await dbRun('UPDATE pet_spirit_exped SET claimed = 1 WHERE player_id = ? AND date = ? AND claimed = 0', [userId, date]);
    if (!gate.changes) return res.status(409).json({ error: '今日秘径已领取' });
    const upd = await dbRun(
      `UPDATE pets SET
         hunger = MIN(?, hunger + ?),
         exp = MIN(?, hunger + ?),
         level = CAST(MIN(?, hunger + ?) / ? AS INTEGER),
         bond = MIN(?, bond + ?)
       WHERE player_id = ?`,
      [PET_HUNGER_MAX, R018_EXPED_HUNGER, PET_HUNGER_MAX, R018_EXPED_HUNGER, PET_HUNGER_MAX, R018_EXPED_HUNGER, PET_LEVEL_DIVISOR, R018_BOND_MAX, R018_EXPED_BOND, userId]
    );
    if (!upd.changes) {
      await dbRun('UPDATE pet_spirit_exped SET claimed = 0 WHERE player_id = ? AND date = ?', [userId, date]);
      return res.status(404).json({ error: '请先收养一只灵宠' });
    }
    const _r018bRow: any = await dbGet('SELECT hunger, rune_active FROM pets WHERE player_id = ?', [userId]);
    const _r018bBonus = _r018bRow ? (r018bExpedExp(_r018bRow.rune_active, petLevel(_r018bRow.hunger)) - R018_EXPED_EXP) : 0;
    await updatePlayerSave(userId, (sd: any) => { if (sd.player) { sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + R018_EXPED_EXP; if (_r018bBonus > 0) sd.player.exp += _r018bBonus; } });
    logPetCare(userId, 'exped', `秘径归来，喂食度 +${R018_EXPED_HUNGER}、羁绊 +${R018_EXPED_BOND}、修为 +${R018_EXPED_EXP}`);
    const spirit = await r018SpiritSync(userId);
    const fresh: any = await dbGet('SELECT name, rarity, hunger, exp, bond, aptitude, merged FROM pets WHERE player_id = ?', [userId]);
    res.json({ ok: true, pet: petView(fresh), spirit, expGain: R018_EXPED_EXP + _r018bBonus });
  } catch (e: any) {
    console.error('pet spirit exped claim error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/pet/spirit/away — 妖灵归位（D6）：标记 merged=1（幂等、无消耗）；此后不可再培养。
//   属性继承按策划 §2.1 P2 归客户端存档域（YlxwMergeSpiritAway），服务端只回 inheritHints。
app.post('/api/pet/spirit/away', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `pet:away:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const pet: any = await dbGet('SELECT id, name, rarity, hunger, bond, merged FROM pets WHERE player_id = ?', [userId]);
    if (!pet) return res.status(404).json({ error: '请先收养一只灵宠' });
    if (Number(pet.merged) > 0) return res.status(409).json({ error: '该妖灵已完成归位' });
    // R-075 归位花灵石（归位产出可出战灵宠，故与「点化」同档 30000；口径同收养）
    const _wrow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!_wrow) return res.status(404).json({ error: '请先进游戏创建角色' });
    let _wbal = 0;
    try { _wbal = Number(JSON.parse(_wrow.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (_wbal < R071_AWAY_COST) return res.status(409).json({ error: `灵石不足：归位需 ${R071_AWAY_COST}，现有 ${_wbal}` });
    let _wshort = false;
    const _wpaid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < R071_AWAY_COST) { _wshort = true; return; }
      sd.player.spiritStones = b - R071_AWAY_COST;
    });
    if (!_wpaid.ok || _wshort) return res.status(409).json({ error: _wshort ? '灵石不足' : (_wpaid.error === 'No save found' ? '请先进游戏创建角色' : '归位失败，请重试') });
    const upd = await dbRun('UPDATE pets SET merged = 1 WHERE player_id = ? AND merged = 0', [userId]);
    if (!upd.changes) {
      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + R071_AWAY_COST; });
      return res.status(409).json({ error: '归位状态已变更，请刷新后重试' });
    }
    logPetCare(userId, 'away', `「${String(pet.name)}」妖灵归位，化为可出战灵宠`);
    await r018SpiritSync(userId);
    res.json({
      ok: true,
      merged: 1,
      cost: R071_AWAY_COST,
      inheritHints: {
        keepName: String(pet.name),
        keepRarity: String(pet.rarity),
        keepLevel: petLevel(pet.hunger),
        affection: petT2Affection(pet.bond),
        note: '属性继承按策划 §2.1 P2 归客户端存档域（YlxwMergeSpiritAway）',
      },
    });
  } catch (e: any) {
    console.error('pet spirit away error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/pet/spirit/release — 妖灵放生（R-075）：丢弃当前妖灵（DELETE pets 行），免费、无产出。
//   与「归位」的区别：归位 = 转化（妖灵 → 可出战灵宠，花 R071_AWAY_COST）；放生 = 舍弃（无产出，0 灵石）。
//   两者都释放妖灵槽位 ⇒ 之后可重新 POST /api/pet/adopt 收养新妖灵（R-071 / R-072）。
//   无扣费 ⇒ 无补偿退费面；DELETE 以 changes 判成败（0 行 = 并发下已被他人放生 / 归位）。
app.post('/api/pet/spirit/release', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `pet:release:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const pet: any = await dbGet('SELECT id, name, rarity, merged FROM pets WHERE player_id = ?', [userId]);
    if (!pet) return res.status(404).json({ error: '请先收养一只灵宠' });
    const del = await dbRun('DELETE FROM pets WHERE player_id = ?', [userId]);
    if (!del.changes) return res.status(409).json({ error: '放生失败，请刷新后重试' });
    logPetCare(userId, 'release', `放生「${String(pet.name)}」（${String(pet.rarity)}品），妖灵归隐山林`);
    await r018SpiritSync(userId);
    res.json({ ok: true, released: 1, name: String(pet.name), cost: 0 });
  } catch (e: any) {
    console.error('pet spirit release error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});





// [r018b] R-018 D5 灵纹（6 条被动 · 任选 1 条生效 · 每 10 级解锁）
//   ★ 本环 = r018 的 D5 补齐（r018 第一版按决策点 9 留第二版）。不改 r018 既有常量 / 端点签名，
//     只在 r018 的纯函数体内接入「灵纹」这一层（r018 自身门禁面全部保留）。
//   落点：锐纹/御纹/疾纹/噬纹 → 客户端战斗层（player.petSpirit.rune* → YlxwBattleBonus）；
//         蕴纹 → 服务端秘径修为 +30%；天纹 → 服务端 PP ×1.10。
//   消耗：首次激活免费；此后换纹 50,000 灵石/次（策划 §2 D5「任选 1 条生效」+「换纹 50,000/次」）。
const R018B_RUNE_COST = 50000;      // 换纹单价（首次激活免费）
const R018B_RUNE_TABLE: Record<string, { key: string; name: string; unlock: number; kind: string; value: number; desc: string }> = {
  rui:  { key: 'rui',  name: '锐纹', unlock: 10, kind: 'critRate',        value: 0.015, desc: '主人暴击率 +1.5%' },
  yu:   { key: 'yu',   name: '御纹', unlock: 20, kind: 'damageReduction', value: 0.02,  desc: '主人减伤 +2%' },
  ji:   { key: 'ji',   name: '疾纹', unlock: 30, kind: 'dodgeRate',       value: 0.015, desc: '主人闪避 +1.5%' },
  shi:  { key: 'shi',  name: '噬纹', unlock: 40, kind: 'lifeLeech',       value: 0.01,  desc: '主人吸血 +1%' },
  yun:  { key: 'yun',  name: '蕴纹', unlock: 50, kind: 'expMul',          value: 0.30,  desc: '妖灵秘径修为产出 +30%' },
  tian: { key: 'tian', name: '天纹', unlock: 60, kind: 'ppMul',           value: 0.10,  desc: '妖灵之力 PP ×1.10' },
};
// 灵纹定义（未知 key ⇒ null）
function r018bRuneDef(key: unknown): { key: string; name: string; unlock: number; kind: string; value: number; desc: string } | null {
  const k = String(key == null ? '' : key);
  return Object.prototype.hasOwnProperty.call(R018B_RUNE_TABLE, k) ? R018B_RUNE_TABLE[k] : null;
}
// 已解锁灵纹列表（含 unlocked 标志；供 GET /api/pet 回显）
function r018bRuneList(level: unknown): any[] {
  const lv = Math.max(0, Math.min(99, Math.floor(Number(level) || 0)));
  return Object.keys(R018B_RUNE_TABLE).map((k) => {
    const d = R018B_RUNE_TABLE[k];
    return { key: d.key, name: d.name, unlock: d.unlock, desc: d.desc, unlocked: lv >= d.unlock };
  });
}
// 当前生效灵纹的效果（未解锁 / 未激活 ⇒ 全 0、乘数 1）
function r018bRuneEffect(key: unknown, level: unknown): { key: string; critRate: number; dodgeRate: number; lifeLeech: number; damageReduction: number; expMul: number; ppMul: number } {
  const zero = { key: '', critRate: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0, expMul: 0, ppMul: 1 };
  const d = r018bRuneDef(key);
  if (!d) return zero;
  const lv = Math.max(0, Math.min(99, Math.floor(Number(level) || 0)));
  if (lv < d.unlock) return zero;
  const o = Object.assign({}, zero, { key: d.key });
  if (d.kind === 'critRate') o.critRate = d.value;
  else if (d.kind === 'dodgeRate') o.dodgeRate = d.value;
  else if (d.kind === 'lifeLeech') o.lifeLeech = d.value;
  else if (d.kind === 'damageReduction') o.damageReduction = d.value;
  else if (d.kind === 'expMul') o.expMul = d.value;
  else if (d.kind === 'ppMul') o.ppMul = 1 + d.value;
  return o;
}
// 基础加成 + 灵纹（天纹 ×1.10）→ 存档 payload（与 GET /api/pet 回显同源同式）
function r018bApplyRune(b: { pp: number; attack: number; defense: number; maxHp: number; speed: number }, rn: { key: string; critRate: number; dodgeRate: number; lifeLeech: number; damageReduction: number; ppMul: number }): any {
  const mul = (rn && rn.ppMul) ? rn.ppMul : 1;
  return {
    pp: Math.round(b.pp * mul * 10000) / 10000,
    attack: Math.floor(b.attack * mul),
    defense: Math.floor(b.defense * mul),
    maxHp: Math.floor(b.maxHp * mul),
    speed: Math.floor(b.speed * mul),
    rune: rn ? rn.key : '',
    runeCrit: rn ? rn.critRate : 0,
    runeDodge: rn ? rn.dodgeRate : 0,
    runeLeech: rn ? rn.lifeLeech : 0,
    runeDR: rn ? rn.damageReduction : 0,
  };
}
// 品阶 / 等级 / 羁绊 / 资质 + 灵纹 → 主人加成（GET /api/pet 与 r018SpiritSync 同源同式）
function r018bSpiritBonus(rarity: unknown, level: unknown, bond: unknown, aptitude: unknown, runeKey: unknown): any {
  const b = r018SpiritBonus(rarity, level, bond, aptitude);
  return r018bApplyRune(b, r018bRuneEffect(runeKey, level));
}
// 秘径修为（蕴纹 +30%）：返回应发修为（无蕴纹 = R018_EXPED_EXP）
function r018bExpedExp(runeKey: unknown, level: unknown): number {
  const rn = r018bRuneEffect(runeKey, level);
  return R018_EXPED_EXP + Math.floor(R018_EXPED_EXP * (rn.expMul || 0));
}

// POST /api/pet/rune — 换纹（D5）：首次激活免费，此后 50,000 灵石/次；须已解锁（level ≥ unlock）。
//   事务口径 = r018 同款补偿式：预检 → 扣费（saveLock 互斥，二次校验）→ 原子 UPDATE → 行缺失补偿退费。
app.post('/api/pet/rune', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `pet:rune:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const pet: any = await dbGet('SELECT id, name, hunger, rune_active, merged FROM pets WHERE player_id = ?', [userId]);
    if (!pet) return res.status(404).json({ error: '请先收养一只灵宠' });
    if (Number(pet.merged) > 0) return res.status(409).json({ error: '妖灵已归位，无法换纹' });
    const key = String(req.body?.rune ?? '');
    const def = r018bRuneDef(key);
    if (!def) return res.status(400).json({ error: '未知的灵纹' });
    const level = petLevel(pet.hunger);
    if (level < def.unlock) return res.status(409).json({ error: `「${def.name}」需妖灵达到 ${def.unlock} 级` });
    const cur = String(pet.rune_active || '');
    if (cur === key) return res.status(409).json({ error: `「${def.name}」已生效` });
    const cost = cur ? R018B_RUNE_COST : 0; // 首次激活免费（策划 §2 D5「任选 1 条生效」）
    if (cost > 0) {
      const srow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
      if (!srow) return res.status(404).json({ error: '请先进游戏创建角色' });
      let bal = 0;
      try { bal = Number(JSON.parse(srow.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }
      if (bal < cost) return res.status(409).json({ error: `灵石不足：需 ${cost}，现有 ${bal}` });
      let short = false;
      const paid = await updatePlayerSave(userId, (sd: any) => {
        const b = Number(sd.player?.spiritStones) || 0;
        if (b < cost) { short = true; return; }
        sd.player.spiritStones = b - cost;
      });
      if (!paid.ok || short) {
        return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '换纹失败，请重试') });
      }
    }
    const upd = await dbRun('UPDATE pets SET rune_active = ? WHERE player_id = ?', [key, userId]);
    if (!upd.changes) {
      if (cost > 0) await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + cost; });
      return res.status(404).json({ error: '请先收养一只灵宠' });
    }
    logPetCare(userId, 'rune', `妖灵换纹「${def.name}」（${def.desc}）${cost > 0 ? '，消耗 ' + cost + ' 灵石' : '（首次激活免费）'}`);
    const spirit = await r018SpiritSync(userId);
    const fresh: any = await dbGet('SELECT name, rarity, hunger, exp, bond, aptitude, merged FROM pets WHERE player_id = ?', [userId]);
    res.json({ ok: true, rune: key, cost, spirit, pet: petView(fresh) });
  } catch (e: any) {
    console.error('pet rune error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});


// [wudaocore] R-GAME3 悟道系统纯逻辑核心（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
// 十系悟道（血/剑/体/法/锋/影/甲/噬/禅/丰），每系独立 1..10 级，exp 只增不减；数值为本次定档，常量集中可调。
// 加成落点：客户端权威架构下攻防血暴击的实际结算在客户端（与称号 attr_json/回归 buff 同一架构边界，
// 服务端出权威数值+伴生页展示，客户端接管后即插即用）。
const WUDAO_DAOS: Record<string, { name: string; stat: string; statName: string; basePct: number; stepPct: number }> = {
  // [r110wudao] R-110 悟道十道：顺序即客户端展示顺序（客户端动态枚举 daos[]，零改动自动跟随）。
  //   ① 旧 6 键（pill/sword/body/spell/array/tame）原样保留 —— 其 level/exp 存于 wudao 表（按 key 存续），
  //      本环只改 name/statName、绝不改 key ⇒ 存量等级 100% 不丢；
  //   ② 新增 4 键（edge/shadow/armor/devour）追加于后，接同一条加成/展示管线（wudaoBonusPct → bonusText）；
  //   ③「重构每一种道的名称」：十道各取语义匹配且互不重复的道名（血/剑/体/法/锋/影/甲/噬/禅/丰）。
  pill:   { name: '血道', stat: 'maxHp',           statName: '气血', basePct: 2.0, stepPct: 0.5  }, // 1 气血（炼气期开放）
  sword:  { name: '剑道', stat: 'attack',          statName: '攻击', basePct: 2.0, stepPct: 0.5  }, // 2 攻击（筑基期）
  body:   { name: '体道', stat: 'defense',         statName: '防御', basePct: 2.0, stepPct: 0.5  }, // 3 防御（筑基期）
  spell:  { name: '法道', stat: 'crit',            statName: '暴击', basePct: 1.0, stepPct: 0.25 }, // 4 暴击（金丹期）
  edge:   { name: '锋道', stat: 'critDamage',      statName: '暴伤', basePct: 1.0, stepPct: 0.25 }, // 5 暴伤（金丹期·新增）
  shadow: { name: '影道', stat: 'dodge',           statName: '闪避', basePct: 1.0, stepPct: 0.25 }, // 6 闪避（元婴期·新增）
  armor:  { name: '甲道', stat: 'damageReduction', statName: '减伤', basePct: 1.0, stepPct: 0.25 }, // 7 减伤（元婴期·新增）
  devour: { name: '噬道', stat: 'lifesteal',       statName: '吸血', basePct: 1.0, stepPct: 0.25 }, // 8 吸血（元婴期·新增）
  array:  { name: '禅道', stat: 'cultivate',       statName: '修炼', basePct: 1.0, stepPct: 0.25 }, // 9 修炼（化神期）
  tame:   { name: '丰道', stat: 'gather',          statName: '资源', basePct: 1.0, stepPct: 0.25 }, // 10 资源（长生境）
};
const WUDAO_MAX_LEVEL = 10;
const WUDAO_BONUS_UNLOCK_LEVEL = 3; // 系等级达标（≥3）解锁被动加成，之后每级再叠 stepPct
// 升级曲线：升到 L 级共需 25×(L-1)×L 累计 exp（L=2 需 50 … L=10 需 2250），纯函数无表
function wudaoExpToReach(level: unknown): number {
  const l = Math.min(WUDAO_MAX_LEVEL, Math.max(1, Math.floor(Number(level) || 1)));
  return 25 * (l - 1) * l;
}
function wudaoLevelFromExp(exp: unknown): number {
  const e = Math.max(0, Math.floor(Number(exp) || 0));
  let lv = 1;
  while (lv < WUDAO_MAX_LEVEL && e >= wudaoExpToReach(lv + 1)) lv++;
  return lv;
}
const WUDAO_MAX_EXP_TOTAL = wudaoExpToReach(WUDAO_MAX_LEVEL); // 2250：满级累计（心得入账钳此值，满级后不再积累）
// 挂机心得：每分钟 roll 一次，8% 命中=1 条心得（=期望 4.8 条/小时），随机落入本人已开放的系之一；
// 单次上传挂机时长钳 120 分钟（与每日任务差值钳制同风格，防改档单次爆量）
const WUDAO_INSIGHT_CHANCE = 0.04;  // 每分钟 roll 命中概率（物品概率÷2：0.08→0.04）
const WUDAO_INSIGHT_EXP = 10;       // 每条心得修为
const WUDAO_IDLE_CAP_MINUTES = 120; // 单次上传计的挂机分钟上限
function wudaoIdleInsights(minutes: unknown, rng: () => number = Math.random): number {
  const m = Math.min(WUDAO_IDLE_CAP_MINUTES, Math.max(0, Math.floor(Number(minutes) || 0)));
  let hits = 0;
  for (let i = 0; i < m; i++) { if (rng() < WUDAO_INSIGHT_CHANCE) hits++; }
  return hits;
}
function wudaoPickDao(rng: () => number = Math.random): string {
  const keys = Object.keys(WUDAO_DAOS);
  return keys[Math.min(keys.length - 1, Math.max(0, Math.floor(rng() * keys.length)))];
}
// 被动加成（纯）：Lv≥解锁级给 basePct，之后每级 +stepPct（钳 2 位小数防浮点尾巴）；未解锁/未知道=0
function wudaoBonusPct(daoKey: string, level: unknown): number {
  const d = WUDAO_DAOS[daoKey];
  const lv = Math.min(WUDAO_MAX_LEVEL, Math.max(0, Math.floor(Number(level) || 0)));
  if (!d || lv < WUDAO_BONUS_UNLOCK_LEVEL) return 0;
  return Math.round((d.basePct + (lv - WUDAO_BONUS_UNLOCK_LEVEL) * d.stepPct) * 100) / 100;
}
// 手动顿悟：灵石 500 → 直获 100 exp（大额快车道；本次定档可调）
const WUDAO_MANUAL_COST = 5000;
const WUDAO_MANUAL_EXP = 100;
function wudaoDaoOk(key: unknown): boolean {
  return key != null && Object.prototype.hasOwnProperty.call(WUDAO_DAOS, asStr(key));
}
const WUDAO_LOG_KEEP = 50; // 每玩家悟道日志保留条数（写入后裁剪，防表膨胀）
// ── [r101wudao] R-091 悟道体系重规划：稀有道等阶门槛 + 灵石价随境界递增 ──
// 境界序自持镜像（与 REALM_ORDER_FOR_RANKING / DUNGEON_REALM_ORDER 同源同序；本块不引用外部符号）
const WUDAO_REALM_ORDER: string[] = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];
// [r110wudao] R-110 十道境界门槛（境界序）：血道(序1)炼气0；剑/体(2-3)筑基1；法/锋(4-5)金丹2；
//   影/甲/噬(6-8)元婴3；禅(9)化神4；丰(10)长生境6（★注：WUDAO_REALM_ORDER 序5=合道期、序6=长生境；
//   用户原文「资源（长生）」，故取长生境=6，与「名称」口径一致）。
// ★ 门槛只挡「从未投入(exp<=0)」的玩家；已投入者由调用方按 exp>0 祖父放行，不追溯锁死。
const WUDAO_DAO_REALM_GATE: Record<string, number> = { pill: 0, sword: 1, body: 1, spell: 2, edge: 2, shadow: 3, armor: 3, devour: 3, array: 4, tame: 6 };
function wudaoRealmIndex(realm: unknown): number {
  const i = WUDAO_REALM_ORDER.indexOf(String(realm == null ? '' : realm));
  return i >= 0 ? i : 0; // 未知境界按最低档（炼气期），与 dungeon 同口径
}
function wudaoDaoGateRealm(daoKey: string): number {
  const g = WUDAO_DAO_REALM_GATE[daoKey];
  return typeof g === 'number' && g > 0 ? Math.min(g, WUDAO_REALM_ORDER.length - 1) : 0;
}
// 手动顿悟灵石价：随人物境界递增（炼气 5000 → 长生 60000，≈12×；稀有道同价——门槛已限人数）
const WUDAO_MANUAL_COST_BY_REALM: number[] = [WUDAO_MANUAL_COST, 8000, 12000, 18000, 27000, 40000, 60000];
function wudaoManualCost(realmIdx: unknown): number {
  const i = Math.min(WUDAO_MANUAL_COST_BY_REALM.length - 1, Math.max(0, Math.floor(Number(realmIdx) || 0)));
  return WUDAO_MANUAL_COST_BY_REALM[i];
}
// [/wudaocore]

// [gongfacore] Y20 功法系统纯逻辑核心（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
// 六部功法（焚天诀/御剑术/不灭体/大衍诀/周天阵/御灵术）各 1..100 级（0.8.7 T3），level 0=未入门；
// 数值为本次定档（任务书口径），常量集中可调。属性被动落点：客户端权威架构下攻/防/血/暴击/闪避/命中
// 的实际结算在客户端混淆码内（与称号 attr_json/悟道加成同一架构边界），服务端出权威数值+伴生页展示，
// 客户端接管后即插即用，不入实际战斗结算。
const GONGFA_MAX_LEVEL = 100;
// 0.8.7 T3（《数值表-T2T3》§5.2）：升到 L 级的单级消耗 = TIER[floor((L-1)/10)] × 品级乘数。
// TIER = 每 10 级一档的每级基价（L1-10 每级 300 … L91-100 每级 20000，玄品口径）；
// 满级累计投入：黄 264,000 / 玄 528,000 / 地 1,056,000 / 天 2,112,000。
const GONGFA_TIER_COST = [300, 500, 800, 1200, 2000, 3000, 5000, 8000, 12000, 20000];
const GONGFA_GRADE_MULT: Record<string, number> = { huang: 0.5, xuan: 1, di: 2, tian: 4 };
const GONGFA_GRADE_DEFAULT = 'xuan'; // 六卷未设品级，一律按玄（×1）计；乘数表随公式留档，定品级时直接挂表
// 属性成长（《数值表-T2T3》§5.1）：攻/防/血 +1%/级（满级恰 ×2.00），其余三卷 +0.2%/级（满级恰 ×1.20）
const GONGFA_MAIN_KEYS: Record<string, boolean> = { fentian: true, bumie: true, zhoutian: true };
const GONGFA_MAIN_STEP_PCT = 1;    // 焚天诀(攻击)/不灭体(防御)/周天阵(气血)
const GONGFA_MINOR_STEP_PCT = 0.2; // 御剑术(暴击)/大衍诀(命中)/御灵术(闪避)
const GONGFA_LIST: Record<string, { name: string; stat: string; statName: string }> = {
  fentian:  { name: '焚天诀', stat: 'attack',  statName: '攻击' },
  yujian:   { name: '御剑术', stat: 'crit',    statName: '暴击' },
  bumie:    { name: '不灭体', stat: 'defense', statName: '防御' },
  dayan:    { name: '大衍诀', stat: 'hit',     statName: '命中' },
  zhoutian: { name: '周天阵', stat: 'maxHp',   statName: '气血' },
  yuling:   { name: '御灵术', stat: 'dodge',   statName: '闪避' },
};
function gongfaOk(key: unknown): boolean {
  return key != null && Object.prototype.hasOwnProperty.call(GONGFA_LIST, asStr(key));
}
// 升到 L 级的单级消耗（纯）：TIER[floor((L-1)/10)] × 品级乘数（缺省玄 ×1）；非法输入钳 1..100
function gongfaCostToReach(level: unknown): number {
  const l = Math.min(GONGFA_MAX_LEVEL, Math.max(1, Math.floor(Number(level) || 1)));
  const seg = Math.min(GONGFA_TIER_COST.length - 1, Math.floor((l - 1) / 10));
  const mult = GONGFA_GRADE_MULT[GONGFA_GRADE_DEFAULT] || 1;
  return Math.round(GONGFA_TIER_COST[seg] * mult);
}
// 升到 L 级累计投入（纯）：按段求和（玄品：L10=3,000 / L50=48,000 / L100=528,000）
function gongfaExpToReach(level: unknown): number {
  const l = Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(level) || 0)));
  let total = 0;
  for (let i = 1; i <= l; i++) total += gongfaCostToReach(i);
  return total;
}
// 由累计 exp 推导等级（纯）：0=未入门；恰达阈值升级（>=）；非法/负数安全。
// 0.8.7 起仅作无行兜底：旧档 exp 是 0.8.6 旧曲线（1000×L 累计）值，与新曲线不可换算，
// 展示等级一律以 level 列（守卫推进维护）为准，从 exp 反推会凭空涨级。
function gongfaLevelFromExp(exp: unknown): number {
  const e = Math.max(0, Math.floor(Number(exp) || 0));
  let lv = 0;
  while (lv < GONGFA_MAX_LEVEL && e >= gongfaExpToReach(lv + 1)) lv++;
  return lv;
}
const GONGFA_MAX_EXP_TOTAL = gongfaExpToReach(GONGFA_MAX_LEVEL); // 528000：满级累计投入（玄品口径）
// 属性被动（纯）：攻/防/血 +1%/级、其余 +0.2%/级（非法输入按 0 计；key 非法按小卷计）
function gongfaBonusPct(key: unknown, level: unknown): number {
  const lv = Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(level) || 0)));
  const main = key != null && Object.prototype.hasOwnProperty.call(GONGFA_MAIN_KEYS, asStr(key));
  return (main ? GONGFA_MAIN_STEP_PCT : GONGFA_MINOR_STEP_PCT) * lv;
}
// 展示辅助（纯）：百分比去浮点尾零（0.2→"0.2"、5→"5"、100→"100"）
function gongfaPctStr(n: unknown): string {
  const v = Number(n) || 0;
  return String(Math.round(v * 10) / 10);
}
// [/gongfacore]

// [actcore] Y21 限时活动框架纯逻辑核心（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
// 四类活动（双倍修为/双倍灵石/限时 Boss/限时掉落），admin 经 GM API 写 events/activity_config 表驱动；
// 服务端结算点（离线收益/灵田收获/炼丹出炉）自动应用倍率；Boss/掉落两类在客户端接管前仅展示+倒计时。
const ACT_TYPES: Record<string, { name: string; target: 'exp' | 'stones' | 'boss' | 'drop' | 'live'; desc: string }> = {
  exp2:    { name: '双倍修为', target: 'exp',    desc: '活动期间离线/灵田等服务端结算的修为收益加倍' },
  stones2: { name: '双倍灵石', target: 'stones', desc: '活动期间离线/灵田/炼丹出炉等服务端结算的灵石收益加倍' },
  boss:    { name: '限时 Boss', target: 'boss',  desc: '限时世界 Boss 现世（客户端接管前仅展示与倒计时）' },
  drop:    { name: '限时掉落', target: 'drop',   desc: '野外掉落率提升（客户端接管前仅展示）' },
  // "Tianjiang Lingyu": target 'live' matches no actMultiplierFor() query target ('exp'/'stones'),
  // so this type NEVER multiplies exp/stones income; it only carries the window and is shown in the
  // existing read-only events panel. Payout is done by the [raincore] settler, not by the multiplier engine.
  stones2_live: { name: '\u5929\u964d\u7075\u96e8', target: 'live', desc: '\u5728\u7ebf\u4fee\u884c\uff1a\u6bcf\u6ee1 1 \u5c0f\u65f6\u7ed3\u7b97\u4e00\u5c01\u7075\u77f3\u90ae\u4ef6\uff08\u6309\u5883\u754c\u6298\u7b97\uff09' },
  // [act087] 0.8.7 T5 四活动：target 全 'live'（actMultiplierFor 只认 'exp'/'stones'，永不命中
  // ⇒ 新玩法天然不污染倍率引擎，stones2_live 先例）。进目录后 actTypeOk 白名单 / /api/events
  // 展示 / GM 建场播报全部自动放行，GM 零新增。
  rank_battle:  { name: '仙途冲榜',   target: 'live', desc: '七天双榜竞速：灵石获取榜与讨伐击杀榜，按境界时薪折算发奖' },
  checkin_fest: { name: '仙缘七日礼', target: 'live', desc: '每日签到：按月历每日签到得修为与灵石，累计达标领额外奖励（长期活动）[r054sign]' },
  token_shop:   { name: '灵玉阁',     target: 'live', desc: '活动期服务端结算掉落灵玉，灵玉阁固定率兑换限时好礼' },
  boss_raid:    { name: '万妖巢穴',   target: 'live', desc: '全服共讨限时大妖：出手得讨伐积分，结算按档位与排名发奖' },
};
const ACT_MULT_CAP = 10;      // 同类多场活动叠乘上限（防误配爆量；叠加口径=叠乘）
const ACT_MULT_CFG_MAX = 100; // 单场 multiplier 配置上限（GM 写入侧钳制）
function actTypeOk(t: unknown): boolean {
  return t != null && Object.prototype.hasOwnProperty.call(ACT_TYPES, String(t));
}
// 倍率配置钳制（纯）：有限正数取值钳 [1, 100]；非法/非正 → 1（=无加成，坏配置不放大也不清零收益）
function actClampMultiplier(m: unknown): number {
  const v = Number(m);
  if (!Number.isFinite(v) || v <= 0) return 1;
  return Math.min(ACT_MULT_CFG_MAX, Math.max(1, v));
}
// 活动窗口判定（纯）：start<=now<end（恰 start 开启、恰 end 结束）；任一端点非法 → 永不生效
function actWindowOk(startAt: unknown, endAt: unknown, nowMs: number): boolean {
  const s = Number(startAt);
  const e = Number(endAt);
  if (!Number.isFinite(s) || !Number.isFinite(e)) return false;
  return nowMs >= s && nowMs < e;
}
// 活动行激活判定（纯）：逐场 enabled 且窗口内
function actIsActive(ev: { enabled?: unknown; start_at?: unknown; end_at?: unknown }, nowMs: number): boolean {
  return Number(ev?.enabled) === 1 && actWindowOk(ev?.start_at, ev?.end_at, nowMs);
}
// 目标倍率解析（纯）：同类（target 匹配）活跃活动倍率叠乘，钳 ACT_MULT_CAP；无匹配=1；4 位小数防浮点尾巴
function actMultiplierFor(
  rows: Array<{ type?: unknown; multiplier?: unknown; enabled?: unknown; start_at?: unknown; end_at?: unknown }>,
  target: 'exp' | 'stones' | 'boss' | 'drop',
  nowMs: number
): number {
  let m = 1;
  for (const ev of rows || []) {
    const t = ACT_TYPES[String(ev?.type)];
    if (!t || t.target !== target) continue;
    if (!actIsActive(ev, nowMs)) continue;
    m *= actClampMultiplier(ev?.multiplier);
    if (m >= ACT_MULT_CAP) { m = ACT_MULT_CAP; break; }
  }
  return Math.round(m * 10000) / 10000;
}
// 结算放大（纯）：收益 × 倍率后 floor（只在服务端结算点调用；倍率=1 时与原值逐位一致）
function actApplyGain(base: unknown, mult: unknown): number {
  return Math.max(0, Math.floor((Math.max(0, Math.floor(Number(base) || 0))) * (Number(mult) || 1)));
}
// [/actcore]

// [raincore] Y21-R "Tianjiang Lingyu" pure logic core (no external refs; extractable for unit tests).
// Reward anchor, derived from the client meditation loop (measured, not a literal in the bundle):
//   stones per meditate = max(1, max(1, 2*idx+1) + randInt(0..2) - 1) * 5
//   effective rate      = 0.982 meditates/sec (setCooldown(1) + per-second -1 cooldown, 40s steady state)
//   stones/sec          = 4.91 * rainRealmFactor(idx)
//   stones/hour         = 17676 * rainRealmFactor(idx)
//   rainRealmFactor(i)  = 4/3 (i <= 0) | 2*i + 1 (i >= 1)
// Cross-check: idx 0 -> 23568, idx 1 -> 53028, idx 6 -> 229788 stones/hour.
const RAIN_HOURLY_STONES_BASE = 17676;        // = round(0.982 * 5 * 3600) = 4.91 stones/sec * 3600
const RAIN_SETTLE_MIN_MINUTES = 60;           // pay only in whole hours
const RAIN_DAILY_CAP_MINUTES = 480;           // per-day settled cap = 8h
const RAIN_ONLINE_STALE_MS = 15 * 60 * 1000;  // presence window over server-timestamped saves.updated_at
const RAIN_TICK_MS = 10 * 60 * 1000;          // settlement period
let rainEngineOn = false;   // in-memory mirror of the GLOBAL kill switch (activity_config.engine_on)
let rainSettling = false;   // re-entrancy guard: skip a tick if the previous one is still running
let rainLastTickMs = 0;     // server wall-clock of the previous tick (the hard per-tick ceiling)
// Realm factor (pure): i <= 0 -> 4/3, else 2i+1; NaN/negative clamped to 0.
function rainRealmFactor(idx: unknown): number {
  const i = Math.max(0, Math.floor(Number(idx) || 0));
  return i <= 0 ? 4 / 3 : 2 * i + 1;
}
// Hourly stones for a realm index (pure).
function rainHourlyStones(idx: unknown): number {
  return Math.floor(RAIN_HOURLY_STONES_BASE * rainRealmFactor(idx));
}
// Minutes to credit this tick: the client-reported minutes delta, HARD-CAPPED by the server
// wall-clock interval. The wall clock is server-authoritative, so an inflated playTime can never
// earn more than the real elapsed time between two ticks.
function rainDeltaMinutes(prevMinutes: unknown, nowMinutes: unknown, wallMinutes: unknown): number {
  const p = Math.max(0, Math.floor(Number(prevMinutes) || 0));
  const n = Math.max(0, Math.floor(Number(nowMinutes) || 0));
  const raw = n > p ? n - p : 0;
  const cap = Math.max(1, Math.ceil(Math.max(0, Number(wallMinutes) || 0)));
  return Math.min(raw, cap);
}
// Whole hours payable now, bounded by the unpaid remainder and the per-day cap (pure).
function rainPayableHours(accruedMinutes: unknown, settledMinutes: unknown): number {
  const acc = Math.max(0, Math.floor(Number(accruedMinutes) || 0));
  const done = Math.max(0, Math.floor(Number(settledMinutes) || 0));
  const room = Math.max(0, RAIN_DAILY_CAP_MINUTES - done);
  return Math.floor(Math.min(acc, room) / RAIN_SETTLE_MIN_MINUTES);
}
// Stones for a whole number of hours at the given realm index (pure).
function rainBonusStones(hours: unknown, idx: unknown): number {
  const h = Math.max(0, Math.floor(Number(hours) || 0));
  return h * rainHourlyStones(idx);
}
// [/raincore]

// [mentorcore] Y6B 师徒系统纯逻辑核心（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
// 拜师：徒弟发起，目标（师傅候选）须境界≥筑基期 且 总等级≥徒弟+5；每徒弟同时仅 1 位师傅
// （部分唯一索引 idx_mentorships_apprentice_active 兜底），每师傅最多 3 名在门弟子（守卫式单语句插入兜底）；
// 解除：双方 7 天冷却（恰满 7 天出冷却）；出师：徒弟境界≥金丹期，师傅得徒弟累计灵石收益 30%（邮件发放）
// + 7 天 ×1.3 收益增益 + 称号「良师益友」；福利：师徒都在线（近 10 分钟均有存档活动）徒弟服务端
// 结算收益 ×1.1，师傅抽徒弟收益 5%（挂 POST /api/save 差值路径）。数值均为本次定档，常量集中可调。
const MENTOR_MIN_REALM_INDEX = 1;              // 拜师门槛：师傅候选境界 ≥ 筑基期
const MENTOR_GRAD_REALM_INDEX = 2;             // 出师门槛：徒弟境界 ≥ 金丹期
const MENTOR_LEVEL_STEP = 9;                   // 总等级 = 境界序×9 + 层数（跨境界折算口径，本次定档）
const MENTOR_LEVEL_GAP = 5;                    // 师傅候选总等级须 ≥ 徒弟 +5
const MENTOR_MAX_APPRENTICES = 3;              // 每师傅同时在门弟子上限
const MENTOR_TAX_RATE = 0.05;                  // 师傅抽徒弟收益 5%
const MENTOR_ONLINE_MS = 10 * 60 * 1000;       // "都在线"= 最近 10 分钟内有存档活动
const MENTOR_BONUS_MULT = 1.1;                 // 师徒同行：徒弟修为/灵石 +10%
const MENTOR_GRAD_RATE = 0.30;                 // 出师回馈：徒弟累计灵石收益的 30%
const MENTOR_BUFF_MULT = 1.3;                  // 师傅出师收益增益 ×1.3
const MENTOR_BUFF_MS = 7 * 24 * 60 * 60 * 1000;          // 出师增益持续 7 天
const MENTOR_EXPIRE_COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000; // 解除后双方冷却 7 天
// 0.8.7 申请-审批制新增常量（数值定档《数值表-T7T8》T8-7/T8-8/T8-9；declined 不进冷却，冷却只认 expired）
const MENTOR_APPLY_TTL_MS = 48 * 3600 * 1000;   // 拜师申请有效期 48 小时（超时惰性置 declined）
const MENTOR_GRAD_GIFT_BASE = 3000;             // 徒弟出师贺礼基数：贺礼=floor(基数×realmMultOf(徒弟))，每徒每日限 1 笔
// 总等级（纯）：境界序×9+层数；未知境界（负值）按 0 计、层数钳 1..9；字符串/NaN 安全
function mentorLevelOf(realmIndex: unknown, realmLevel: unknown): number {
  const ri = Math.max(0, Math.floor(Number(realmIndex) || 0));
  const lv = Math.min(9, Math.max(1, Math.floor(Number(realmLevel) || 1)));
  return ri * MENTOR_LEVEL_STEP + lv;
}
// 师傅候选境界门槛（纯）：≥筑基期
function mentorRealmOk(realmIndex: unknown): boolean { return Math.floor(Number(realmIndex)) >= MENTOR_MIN_REALM_INDEX; }
// 等级差门槛（纯）：师傅候选总等级 ≥ 徒弟总等级 +5
function mentorGapOk(myLevel: unknown, targetLevel: unknown): boolean {
  return Math.floor(Number(targetLevel) || 0) >= Math.floor(Number(myLevel) || 0) + MENTOR_LEVEL_GAP;
}
// 出师门槛（纯）：徒弟境界 ≥ 金丹期
function mentorGradOk(realmIndex: unknown): boolean { return Math.floor(Number(realmIndex)) >= MENTOR_GRAD_REALM_INDEX; }
// 师傅门下余位（纯）：在门弟子 <3 为可收
function mentorSlotsOk(activeApprentices: unknown): boolean {
  return Math.max(0, Math.floor(Number(activeApprentices) || 0)) < MENTOR_MAX_APPRENTICES;
}
// 在线判定（纯）：最近一次存档活动距今 ≤10 分钟（恰 10 分钟算在线；未来时间不算）
function mentorOnline(lastSeenMs: unknown, nowMs: number): boolean {
  const t = Number(lastSeenMs);
  return Number.isFinite(t) && t > 0 && nowMs - t >= 0 && nowMs - t <= MENTOR_ONLINE_MS;
}
// 师徒同行加成倍率（纯）：关系在门且师傅在线 → ×1.1，否则 ×1
function mentorBonusMult(isActive: boolean, mentorLastSeenMs: unknown, nowMs: number): number {
  return isActive && mentorOnline(mentorLastSeenMs, nowMs) ? MENTOR_BONUS_MULT : 1;
}
// 出师增益倍率（纯）：completed 行 mentor_buff_until 未到期（恰到期即失效）→ ×1.3
function mentorBuffMult(buffUntilMs: unknown, nowMs: number): number {
  const t = Number(buffUntilMs);
  return Number.isFinite(t) && t > nowMs ? MENTOR_BUFF_MULT : 1;
}
// 抽成（纯）：floor(收益×5%)，修为/灵石各自取整；负值钳 0
function mentorTax(silverGain: unknown, expGain: unknown): { stones: number; exp: number } {
  const s = Math.max(0, Math.floor(Number(silverGain) || 0));
  const e = Math.max(0, Math.floor(Number(expGain) || 0));
  return { stones: Math.floor(s * MENTOR_TAX_RATE), exp: Math.floor(e * MENTOR_TAX_RATE) };
}
// 出师回馈（纯）：floor(徒弟累计灵石收益×30%)
function mentorGradLump(cumSilverGain: unknown): number {
  return Math.floor(Math.max(0, Math.floor(Number(cumSilverGain) || 0)) * MENTOR_GRAD_RATE);
}
// 出师增益截止（纯）：出师时刻 +7 天
function mentorGradBuffUntil(nowMs: number): number { return nowMs + MENTOR_BUFF_MS; }
// 解除冷却（纯）：截止=解除时刻+7 天；恰满 7 天出冷却（now < endedAt+7d 为在冷却）
function mentorCoolingUntil(endedAtMs: unknown): number { return Math.floor(Number(endedAtMs) || 0) + MENTOR_EXPIRE_COOLDOWN_MS; }
function mentorCooling(endedAtMs: unknown, nowMs: number): boolean {
  const t = Number(endedAtMs);
  return Number.isFinite(t) && t > 0 && nowMs < t + MENTOR_EXPIRE_COOLDOWN_MS;
}
// 申请过期（纯）：pending 行 created_at 距今超过申请有效期（48h）即过期（恰满算过期；脏数据按过期）
function mentorApplyExpired(createdAtMs: unknown, nowMs: number): boolean {
  const t = Number(createdAtMs);
  return !(Number.isFinite(t) && t > 0) || nowMs - t >= MENTOR_APPLY_TTL_MS;
}
// 出师贺礼（纯）：floor(基数 × realmMultOf(徒弟))，负值钳 0
function mentorGradGift(realmMult: unknown): number {
  return Math.floor(Math.max(0, Number(realmMult) || 0) * MENTOR_GRAD_GIFT_BASE);
}
// 搜索词规范化（纯）：trim 后 1..16 字；空/超长/null → null
function mentorSearchName(raw: unknown): string | null {
  const n = String(raw ?? '').trim();
  return n.length >= 1 && n.length <= 16 ? n : null;
}
// LIKE 通配转义（纯）：\ % _ 前缀 \，配合 ESCAPE '\' 使用
function mentorLikeEscape(name: string): string {
  return name.replace(/[\\%_]/g, (c) => '\\' + c);
}
// [/mentorcore]

// Y5/Y6 登录元数据：刷新 last_login；距上次登录 ≥3 天 → 回归邮件（5000 灵石）+ saves.return_buff_until（3 天）+ 回归仙人称号
async function onLoginMeta(userId: number, prevLastLogin: unknown): Promise<void> {
  const nowMs = Date.now();
  const prevMs = parseDbTimeMs(prevLastLogin);
  db.run('UPDATE users SET last_login = ? WHERE id = ?', [new Date(nowMs).toISOString(), userId], () => {});
  maybeRolloverSeason().catch((e: any) => console.error('season rollover error:', e?.message || e)); // Y14：跨月惰性归档（幂等，不阻塞登录）
  if (!isReturnLogin(prevMs, nowMs)) return;
  try {
    await insertMail(
      userId,
      '仙路重逢 · 回归大礼',
      `道友一别数日，修仙界物是人非，特备回归大礼：\n\n· 灵石 ×${RETURN_MAIL_STONES}（点击下方领取）\n· 回归增益 ×${BUFF_MULTIPLIER}：打坐/历练收益提升 50%，持续 ${RETURN_BUFF_MS / DAY_MS} 天\n· 专属称号「回归仙人」已放入称号收藏\n\n愿道友此番仙途更进一步。`,
      'system',
      RETURN_MAIL_STONES
    );
    db.run('UPDATE saves SET return_buff_until = ? WHERE user_id = ?', [nowMs + RETURN_BUFF_MS, userId], () => {});
    await grantTitleBySource(userId, 'return');
  } catch (e: any) {
    console.error('return reward error:', e?.message || e);
  }
}

// Y16 江湖志写入（fire-and-forget，自吞异常绝不阻塞业务路径；昵称/正文钳制防超长刷屏）
function logChronicle(playerId: number | null, nickname: string, text: string): void {
  dbRun('INSERT INTO chronicle (player_id, nickname, text) VALUES (?, ?, ?)',
    [playerId, String(nickname || '').slice(0, 32), clampChronicleText(text)])
    .catch((e: any) => console.error('chronicle log error:', e?.message || e));
}

// 站内邮件内部发送函数：mail send（GM）/回归奖励/每日宝箱共用一条 INSERT 通道
function insertMail(userId: number, title: string, content: string, sender: string, lingshi: number, opts?: { noChronicle?: boolean }): Promise<number> {
  if (!opts?.noChronicle && lingshi >= CHRONICLE_MAIL_STONES) {
    // Y16：大额邮件入志（fire-and-forget，昵称异步取 users.username；全服广播 INSERT...SELECT 不经此处不入志）
    dbGet('SELECT username FROM users WHERE id = ?', [userId])
      .then((u: any) => logChronicle(userId, String(u?.username || ''), `【鸿函】「${title}」自天机阁送达，附灵石 ×${lingshi}`))
      .catch(() => {});
  }
  return new Promise((resolve, reject) => {
    db.run(
      'INSERT INTO mail (user_id, sender, title, content, attached_lingshi) VALUES (?, ?, ?, ?, ?)',
      [userId, sender, title, content, lingshi],
      function (this: any, err: any) {
        if (err) reject(err);
        else resolve(this.lastID);
      }
    );
  });
}

// Y6 称号授予（按 source 定位目录行）：INSERT OR IGNORE + 主键幂等，重复授予静默返回 false
async function grantTitleBySource(userId: number, source: string): Promise<boolean> {
  const t = await dbGet('SELECT id FROM titles WHERE source = ?', [source]);
  if (!t) return false;
  const r = await dbRun('INSERT OR IGNORE INTO player_titles (user_id, title_id) VALUES (?, ?)', [userId, Number(t.id)]);
  return r.changes > 0;
}

// Y6 存档成就数（称号达标判定输入）
function achievementsLen(saveData: any): number {
  const a = saveData?.player?.achievements;
  return Array.isArray(a) ? a.length : 0;
}

// Y6 惰性授予：成就数达标（初入江湖）+ 三榜榜首（登峰造极/武林盟主/富甲一方）。
// 挂在 upsertRanking 之后（POST /api/save 与 updatePlayerSave 两个汇聚点），幂等可重入；内部自吞异常不阻塞存档链路
const RANK_TITLE_SOURCES: Array<{ source: string; sort: string }> = [
  { source: 'rank_realm', sort: 'realm' },
  { source: 'rank_combat', sort: 'combat' },
  { source: 'rank_stones', sort: 'stones' },
];
async function maybeGrantAutoTitles(userId: number, achCount: number): Promise<void> {
  try {
    if (shouldGrantAchievementTitle(achCount)) await grantTitleBySource(userId, 'achievement');
    for (const { source, sort } of RANK_TITLE_SOURCES) {
      const cfg = LEADERBOARD_SORTS[sort];
      const [top, cnt] = await Promise.all([
        dbGet(`SELECT user_id FROM rankings ORDER BY ${cfg.orderBy} LIMIT 1`),
        dbGet('SELECT COUNT(*) AS c FROM rankings'),
      ]);
      if (top && cnt && shouldGrantRankTitle(Number(top.user_id), Number(cnt.c), userId)) {
        await grantTitleBySource(userId, source);
      }
    }
  } catch (e: any) {
    console.error('auto title grant error:', e?.message || e);
  }
}

// Y2 每日任务计数：把存档差值增量写入当日 daily_quests。
// 先 INSERT OR IGNORE 建当日行，再单语句原子 UPDATE（MIN/CASE 镜像 nextProgress 语义）——
// UPDATE 的 RHS 全部按旧行值求值，语句级原子免并发读改写丢更新，无需 saveLock；progress 封顶不溢出
async function tickDailyQuests(userId: number, deltas: Record<string, number>): Promise<void> {
  const date = bjDate(Date.now());
  for (const def of QUEST_DEFS) {
    const delta = Math.floor(Number(deltas[def.key]) || 0);
    if (delta <= 0) continue;
    await dbRun('INSERT OR IGNORE INTO daily_quests (user_id, date, quest_key, progress, done) VALUES (?, ?, ?, 0, 0)', [userId, date, def.key]);
    await dbRun(
      `UPDATE daily_quests SET
         progress = MIN(?, progress + ?),
         done = CASE WHEN MIN(?, progress + ?) >= ? THEN 1 ELSE done END
       WHERE user_id = ? AND date = ? AND quest_key = ?`,
      [def.target, delta, def.target, delta, def.target, userId, date, def.key]
    );
  }
}

// Y15 每日统计累加：单语句 upsert（PRIMARY KEY(player_id,date)，RHS 按旧行求值防并发丢更新）；全零增量不落行
// [r069min] R-069：stats_daily.minutes 余量携带（修「修行统计·时间恒 0 分钟」）
//   根因：minutes = floor((next.playTimeMs - prev.playTimeMs)/60000)，而 prev 取自上一次
//   已落库存档、客户端约每 10s 存档一次 ⇒ 每次差值 <60s，floor 恒 0，余量被逐次丢弃。
//   修法：按玩家在内存里累加余量，凑满 1 分钟才计 1；只作用于 minutes 这一路。
//   重启丢 <1 分钟余量，可接受（不引入 schema 迁移）。
const STATS_PLAY_CARRY = new Map<number, number>();
function statsMinutesCarried(userId: number, prevMs: number, nextMs: number): number {
  const up = nextMs > prevMs ? nextMs - prevMs : 0;
  const total = (STATS_PLAY_CARRY.get(userId) || 0) + up;
  const mins = Math.floor(total / 60000);
  STATS_PLAY_CARRY.set(userId, total - mins * 60000);
  return mins;
}
async function tickStatsDaily(userId: number, d: StatsDelta): Promise<void> {
  if (!statsDeltaHasAny(d)) return;
  await dbRun(
    `INSERT INTO stats_daily (player_id, date, exp_gain, silver_gain, kills, minutes) VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(player_id, date) DO UPDATE SET
       exp_gain = exp_gain + excluded.exp_gain,
       silver_gain = silver_gain + excluded.silver_gain,
       kills = kills + excluded.kills,
       minutes = minutes + excluded.minutes`,
    [userId, bjDate(Date.now()), d.exp, d.silver, d.kills, d.minutes]
  );
}

// DG 秘境观测累加：单语句 upsert（PRIMARY KEY(player_id,date)，RHS 按旧行求值防并发丢更新）；
// [r136dg] 观测累加**不再触碰 last_ts**（last_ts 写权收归 /api/dungeon/entry，即真正的「上次进入」）；
// anomaly 语句内 CASE 判定（observed 累计或既有 count 超阈置 1，粘滞不清除）；
// 绑定数必须与占位符精确相等（VALUES 6 + CASE 2 = 8：驱动对缺参静默绑 NULL 会废掉 count>阈 分支）
async function tickDungeonTracker(userId: number, d: { realm: number; adventure: number }): Promise<void> {
  const realm = Math.max(0, Math.floor(Number(d?.realm) || 0));
  const adventure = Math.max(0, Math.floor(Number(d?.adventure) || 0));
  if (realm <= 0 && adventure <= 0) return;
  const nowMs = Date.now();
  await dbRun(
    `INSERT INTO dungeon_tracker (player_id, date, count, observed, adventure, last_ts, anomaly) VALUES (?, ?, 0, ?, ?, ?, ?)
     ON CONFLICT(player_id, date) DO UPDATE SET
       observed = observed + excluded.observed,   /* [r136dg] */
       adventure = adventure + excluded.adventure,
       anomaly = CASE WHEN observed + excluded.observed > ? OR count > ? THEN 1 ELSE anomaly END`,
    [userId, bjDate(nowMs), realm, adventure, null, realm > DUNGEON_ANOMALY_THRESHOLD ? 1 : 0, DUNGEON_ANOMALY_THRESHOLD, DUNGEON_ANOMALY_THRESHOLD]
  );
}

// ── WUDAO（R-GAME3）悟道入账 ──
// 单语句原子 upsert：exp 只增不减（钳 WUDAO_MAX_EXP_TOTAL），level 列由同一语句内的 CASE（按升级曲线
// wudaoExpToReach 生成）同步重算；阈值/上限等服务端常量全部走占位符绑定（dungeon_tracker 同款纪律）。
// 心得日志写入后裁剪至 WUDAO_LOG_KEEP 条。并发挂机 tick/手动顿悟无读改写竞态（全在一条语句内）。
// 返回 null=入账失败（调用方补偿）。
const WUDAO_LEVEL_CASE_SQL = 'CASE ' + Array.from({ length: WUDAO_MAX_LEVEL - 1 }, (_, i) => WUDAO_MAX_LEVEL - i)
  .map(() => `WHEN MIN(wudao.exp + excluded.exp, ?) >= ? THEN ?`)
  .join(' ') + ' ELSE 1 END';
const WUDAO_UPSERT_SQL =
  `INSERT INTO wudao (player_id, dao_type, level, exp) VALUES (?, ?, ?, ?)
   ON CONFLICT(player_id, dao_type) DO UPDATE SET
     exp = MIN(wudao.exp + excluded.exp, ?),
     level = ${WUDAO_LEVEL_CASE_SQL}`;
// upsert 绑定参数（顺序严格对应 SQL）：首行 4 个（player/dao/首建行 level=按 delta 推导/exp=delta）
// + 尾部 28 个（exp 钳顶 1 个 + 每级 (MIN 钳顶/阈值/等级) 3×9 个）。
// 注意 excluded.exp 取自 VALUES（=delta）：新建行直接落 delta，冲突行=旧行累计+delta——单语句两条路径都正确。
const WUDAO_UPSERT_TAIL: any[] = [WUDAO_MAX_EXP_TOTAL];
for (let lv = WUDAO_MAX_LEVEL; lv >= 2; lv--) WUDAO_UPSERT_TAIL.push(WUDAO_MAX_EXP_TOTAL, wudaoExpToReach(lv), lv);
async function wudaoAddExp(
  userId: number, daoKey: string, expDelta: number, source: 'idle' | 'manual'
): Promise<{ level: number; exp: number } | null> {
  try {
    const delta = Math.max(0, Math.floor(Number(expDelta) || 0));
    if (delta <= 0 || !wudaoDaoOk(daoKey)) return null;
    await dbRun(WUDAO_UPSERT_SQL, [userId, daoKey, wudaoLevelFromExp(delta), delta, ...WUDAO_UPSERT_TAIL]);
    const row = await dbGet('SELECT level, exp FROM wudao WHERE player_id = ? AND dao_type = ?', [userId, daoKey]);
    if (!row) return null;
    dbRun('INSERT INTO wudao_log (player_id, dao_type, exp, source) VALUES (?, ?, ?, ?)', [userId, daoKey, delta, source])
      .then(() => dbRun(
        'DELETE FROM wudao_log WHERE player_id = ? AND id NOT IN (SELECT id FROM wudao_log WHERE player_id = ? ORDER BY id DESC LIMIT ?)',
        [userId, userId, WUDAO_LOG_KEEP]
      ))
      .catch((e: any) => console.error('wudao log error:', e?.message || e));
    return { level: wudaoLevelFromExp(row.exp), exp: Math.max(0, Math.floor(Number(row.exp) || 0)) };
  } catch (e: any) {
    console.error('wudao add exp error:', e?.message || e);
    return null;
  }
}

// WUDAO 挂机埋点：挂机时长（playTime 差值，客户端累计在线毫秒——与每日任务"打坐"同一服务端可见近似口径）
// 每分钟 roll 8% 得 1 条心得（+10 exp），随机落入本人已开放的系之一。fire-and-forget 自吞异常，绝不阻塞存档路径；
// 按系聚合后逐系一次 upsert（单次上传至多 120 条心得 → 至多 6 条语句，fetchAll/写入均有界）
// [v2810] \u609f\u9053\u6302\u673a\u65f6\u957f = \u6253\u5750 + \u5386\u7ec3\uff08\u7528\u6237\u8981\u6c42\u300c\u6253\u5750/\u5386\u7ec3\u4e2d\u968f\u673a\u89e6\u53d1\u609f\u9053\u7ecf\u9a8c\u300d\uff09\u3002
//   tickWudaoIdle \u5185\u90e8\u6982\u7387/\u7ecf\u9a8c\u516c\u5f0f\u4e00\u5b57\u4e0d\u52a8\uff0c\u53ea\u6539\u5582\u8fdb\u53bb\u7684\u65f6\u957f\u3002
function ylWudaoIdleDelta(prevCounters: StatCounters, saveData: any): number {
  const d = computeQuestDeltas(prevCounters, extractCounters(saveData));
  return Math.max(0, (Number(d.meditate) || 0) + (Number(d.adventure) || 0));
}

async function tickWudaoIdle(userId: number, playTimeDeltaMs: number): Promise<void> {
  try {
    const hits = wudaoIdleInsights(Math.floor((Number(playTimeDeltaMs) || 0) / 60000), Math.random);
    if (hits <= 0) return;
    // [r101wudao] R-091：挂机心得只落入本人已开放的系（稀有道未达境界不随机命中；已投入者仍可手动顿悟）
    let realmIdx = 0;
    try {
      const srow: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
      realmIdx = wudaoRealmIndex(JSON.parse(String(srow?.save_data || '{}'))?.player?.realm);
    } catch { realmIdx = 0; }
    const openKeys = Object.keys(WUDAO_DAOS).filter((k) => realmIdx >= wudaoDaoGateRealm(k));
    const pool = openKeys.length > 0 ? openKeys : [Object.keys(WUDAO_DAOS)[0]];
    const perDao: Record<string, number> = {};
    for (let i = 0; i < hits; i++) {
      const k = pool[Math.min(pool.length - 1, Math.max(0, Math.floor(Math.random() * pool.length)))];
      perDao[k] = (perDao[k] || 0) + WUDAO_INSIGHT_EXP;
    }
    for (const k of Object.keys(perDao)) await wudaoAddExp(userId, k, perDao[k], 'idle');
  } catch (e: any) {
    console.error('wudao idle tick error:', e?.message || e);
  }
}

// E1/SEC 经济镜像写入（旁路 fire-and-forget）：内部全 try/catch 自吞异常——存档/GM 路径绝不能因记账挂掉。
// 调用点=POST /api/save 与 updatePlayerSave 两个存档写汇聚点（均在 withSaveLock 内，读旧值→写旁路表，不拦截不拒绝）
// saveUploadStreak：SEC 规则③入参——仅玩家上传调用点传 recordEconSaveUpload() 结果，GM patch 路径不传（=0 不判）
async function writeEconomyMirror(playerId: number, prev: EconSnapshot, next: EconSnapshot, saveUploadStreak: number = 0): Promise<void> {
  try {
    const m = computeEconMirror(prev, next);
    const flags = detectEconAnomalies(m);
    if (m.silverDelta != null) { // SEC 规则②：1h 滚动窗累计（既有镜像 SUM + 本次差值；SUM 忽略 NULL 行，单查询命中 (player_id,ts) 索引）
      const prior = await dbGet(
        "SELECT COALESCE(SUM(silver_delta), 0) AS s FROM economy_ledger WHERE player_id = ? AND ts >= datetime('now', ?)",
        [playerId, '-1 hour']
      );
      if (detectSilverBurst(prior?.s, m)) flags.push('silver_burst_1h');
    }
    if (saveUploadStreak > ECON_SAVE_FREQ_MAX) flags.push('save_freq'); // SEC 规则③：恰 5 次不 flag（严格大于）
    await dbRun(
      'INSERT INTO economy_ledger (player_id, kind, silver_delta, exp_delta, level_from, level_to, silver_after, anomaly_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
      [playerId, 'mirror', m.silverDelta, m.expDelta, m.levelFrom, m.levelTo, m.silverAfter, econAnomalyJson(m, flags)]
    );
  } catch (e: any) {
    console.error('economy mirror error:', e?.message || e);
  }
}

// [mail-claim-core] 领取附件核心逻辑（依赖注入以便 mock db 单测；块内不得引用其它模块符号）
// 原子性说明：本项目是 node-sqlite3 单连接回调式驱动，直接 BEGIN/COMMIT 会有其他请求的裸 db.run
// 语句插进同一事务、被一起 ROLLBACK 的串号风险，故用"补偿式事务"：
//   1) 条件 UPDATE claimed 0→1 —— 单语句原子，WHERE claimed=0 保证并发领取只有一方生效（防重复领取）
//   2) updatePlayerSave 入账（内部 saveLock 互斥，不与玩家存档上传/GM 发放互相覆盖）
//   3) 入账失败 → 补偿 claimed 回 0，玩家可重试，全程全或无
async function mailClaimCore(
  deps: {
    dbGet: (sql: string, params?: any[]) => Promise<any>;
    dbRun: (sql: string, params?: any[]) => Promise<{ lastID: number; changes: number }>;
    updatePlayerSave: (userId: number, mutate: (sd: any) => void) => Promise<{ ok: boolean; error?: string }>;
  },
  userId: number,
  mailId: number
): Promise<{ ok: boolean; error?: string; lingshi?: number }> {
  const row = await deps.dbGet(
    'SELECT id, attached_lingshi, claimed FROM mail WHERE id = ? AND user_id = ?',
    [mailId, userId]
  );
  if (!row) return { ok: false, error: '邮件不存在' };
  if (!Number(row.attached_lingshi)) return { ok: false, error: '该邮件没有可领取附件' };
  if (row.claimed) return { ok: false, error: '附件已领取' };

  // 事务第一步：占住附件（单语句原子，并发重复领取只放行一方）
  const upd = await deps.dbRun(
    'UPDATE mail SET claimed = 1 WHERE id = ? AND user_id = ? AND claimed = 0',
    [mailId, userId]
  );
  if (!upd.changes) return { ok: false, error: '附件已领取' };

  // 事务主体：灵石入账 player.spiritStones（saveLock 互斥，gm_revision++ 联动）
  const credit = await deps.updatePlayerSave(userId, (sd: any) => {
    if (!sd.player || typeof sd.player !== 'object') sd.player = {};
    sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + Number(row.attached_lingshi);
  });

  // 回滚：入账失败（如玩家还没建存档），把 claimed 标志退回，玩家进游戏建号后可重试
  if (!credit.ok) {
    await deps.dbRun('UPDATE mail SET claimed = 0 WHERE id = ?', [mailId]);
    return { ok: false, error: credit.error === 'No save found' ? '请先进游戏创建角色后再领取' : (credit.error || '入账失败') };
  }
  return { ok: true, lingshi: Number(row.attached_lingshi) };
}
// [/mail-claim-core]

// GET /api/mail/list?page=&pageSize= — 我的邮件（分页 + 未读数）
app.get('/api/mail/list', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `mail:list:${req.user?.id ?? req.ip}` }), (req: any, res: any) => {
  const page = Math.max(1, parseInt(req.query.page as string) || 1);
  const pageSize = Math.min(50, Math.max(1, parseInt(req.query.pageSize as string) || 20));
  db.get(
    'SELECT COUNT(*) AS total, SUM(CASE WHEN read_at IS NULL THEN 1 ELSE 0 END) AS unread, SUM(CASE WHEN claimed = 0 AND attached_lingshi > 0 THEN 1 ELSE 0 END) AS claimable FROM mail WHERE user_id = ?',
    [req.user.id],
    (err: any, cnt: any) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      db.all(
        'SELECT id, sender, title, content, attached_lingshi, claimed, created_at, read_at FROM mail WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?',
        [req.user.id, pageSize, (page - 1) * pageSize],
        (err2: any, rows: any[]) => {
          if (err2) return res.status(500).json({ error: 'Database error' });
          res.json({
            mails: (rows || []).map((r) => ({
              id: r.id,
              sender: r.sender,
              title: r.title,
              content: r.content,
              lingshi: Number(r.attached_lingshi) || 0,
              claimed: !!r.claimed,
              read: !!r.read_at,
              createdAt: r.created_at,
            })),
            page,
            pageSize,
            total: Number(cnt?.total) || 0,
            unread: Number(cnt?.unread) || 0,
            claimable: Number(cnt?.claimable) || 0,
          });
        }
      );
    }
  );
});

// POST /api/mail/read — 标记已读（{id} 单封 / {all:true} 全部）
app.post('/api/mail/read', authenticateToken, (req: any, res: any) => {
  const { id, all } = req.body || {};
  if (all) {
    db.run('UPDATE mail SET read_at = CURRENT_TIMESTAMP WHERE user_id = ? AND read_at IS NULL', [req.user.id], (err: any) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json({ ok: true });
    });
    return;
  }
  const mailId = asInt(id);
  if (!mailId) return res.status(400).json({ error: '需要 id 或 all:true' });
  db.run('UPDATE mail SET read_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ? AND read_at IS NULL', [mailId, req.user.id], (err: any) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    res.json({ ok: true });
  });
});

// POST /api/mail/claim — 领取灵石附件（补偿式事务 + saveLock 互斥，见 mailClaimCore）
app.post('/api/mail/claim', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `mail:claim:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const mailId = asInt(req.body?.id);
  if (!mailId) return res.status(400).json({ error: '需要 id' });
  try {
    const r = await mailClaimCore({ dbGet, dbRun, updatePlayerSave }, req.user.id, mailId);
    if (!r.ok) return res.status(409).json({ error: r.error });
    res.json({ ok: true, lingshi: r.lingshi });
  } catch (e: any) {
    console.error('mail claim error:', e?.message || e);
    res.status(500).json({ error: '领取失败' });
  }
});

// POST /api/mail/claim-all -- one-tap claim of every unclaimed mail that carries a
// lingshi attachment. Reuses mailClaimCore per mail (NEVER a second credit path), so the
// atomic claim flag / compensating rollback / gm_revision semantics stay identical to the
// single /api/mail/claim route. A failing mail is logged and skipped; the rest still settle.
app.post('/api/mail/claim-all', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `mail:claimall:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const rows: any[] = await dbAll(
      'SELECT id FROM mail WHERE user_id = ? AND claimed = 0 AND attached_lingshi > 0 ORDER BY id ASC',
      [userId]
    );
    let count = 0;
    let lingshi = 0;
    for (const row of rows || []) {
      try {
        const r = await mailClaimCore({ dbGet, dbRun, updatePlayerSave }, userId, Number(row.id));
        if (r.ok) { count++; lingshi += Number(r.lingshi) || 0; }
      } catch (perMailErr: any) {
        console.error('mail claim-all per-mail error:', perMailErr?.message || perMailErr);
      }
    }
    res.json({ ok: true, count, lingshi });
  } catch (e: any) {
    console.error('mail claim-all error:', e?.message || e);
    res.status(500).json({ error: '\u9886\u53d6\u5931\u8d25' });
  }
});

// POST /api/mail/send — GM 发信（authenticateGM）。单发 {userId|username}，全服 {all:true}
app.post('/api/mail/send', authenticateGM, (req: any, res: any) => {
  const { title, content, sender, lingshi, userId, username, all } = req.body || {};
  const safeTitle = asStr(title).trim().slice(0, 100);
  const safeContent = asStr(content).slice(0, 2000);
  const safeSender = (asStr(sender) || 'system').slice(0, 32);
  const stones = Math.floor(Number(lingshi) || 0);
  if (!safeTitle) return res.status(400).json({ error: '需要 title' });
  if (stones < 0 || stones > 1e9) return res.status(400).json({ error: 'lingshi 数额非法' });

  if (all) {
    // 全服广播：一条 INSERT...SELECT 为每个用户各生成一封
    db.run(
      'INSERT INTO mail (user_id, sender, title, content, attached_lingshi) SELECT id, ?, ?, ?, ? FROM users',
      [safeSender, safeTitle, safeContent, stones],
      function (this: any, err: any) {
        if (err) return res.status(500).json({ error: '发送失败' });
        logGmAction('mail_send', 'all', { title: safeTitle, lingshi: stones, count: this.changes });
        res.json({ ok: true, sent: this.changes });
      }
    );
    return;
  }

  const sendTo = (targetUserId: number) =>
    insertMail(targetUserId, safeTitle, safeContent, safeSender, stones)
      .then((mailId) => {
        logGmAction('mail_send', `user:${targetUserId}`, { title: safeTitle, lingshi: stones });
        res.json({ ok: true, sent: 1, mailId });
      })
      .catch(() => res.status(500).json({ error: '发送失败' }));

  if (userId) return sendTo(asInt(userId));
  if (username) {
    db.get('SELECT id FROM users WHERE username = ?', [asStr(username).slice(0, 32)], (err: any, row: any) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      if (!row) return res.status(404).json({ error: '用户不存在' });
      sendTo(row.id);
    });
    return;
  }
  res.status(400).json({ error: '需要 userId / username / all:true' });
});
// [v2810] DELETE /api/mail/:id \u2014 \u5220\u9664\u5355\u5c01\u90ae\u4ef6\uff08\u5ba2\u6237\u7aef\u4fe1\u7bb1\u5220\u9664\u6309\u94ae\uff09\u3002
//   \u5951\u7ea6\uff1a200 {ok,id} / 400 id \u975e\u6cd5 / 404 \u4e0d\u5b58\u5728\u6216\u4e0d\u5c5e\u4e8e\u672c\u73a9\u5bb6 / 409 \u5df2\u9886\u53d6\u4e0d\u53ef\u5220\u3002
app.delete('/api/mail/:id', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `mail:del:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  const mailId = asInt(req.params.id);
  if (!Number.isInteger(mailId) || mailId <= 0) return res.status(400).json({ error: '\u90ae\u4ef6 id \u975e\u6cd5' });
  try {
    const row: any = await dbGet('SELECT id, claimed FROM mail WHERE id = ? AND user_id = ?', [mailId, userId]);
    if (!row) return res.status(404).json({ error: '\u90ae\u4ef6\u4e0d\u5b58\u5728' });
    if (Number(row.claimed) === 1) return res.status(409).json({ error: '\u5df2\u9886\u53d6\u7684\u90ae\u4ef6\u4e0d\u53ef\u5220\u9664' });
    const del = await dbRun('DELETE FROM mail WHERE id = ? AND user_id = ? AND claimed = 0', [mailId, userId]);
    if (!del.changes) return res.status(404).json({ error: '\u90ae\u4ef6\u4e0d\u5b58\u5728' });
    res.json({ ok: true, id: mailId });
  } catch (e: any) {
    console.error('mail delete error:', e?.message || e);
    res.status(500).json({ error: '\u5220\u9664\u5931\u8d25' });
  }
});


// ─────────────────────────────────────────────────────────
// Y6 称号 API（佩戴展示走伴生页 /yl/apps/quest/，游戏内混淆码不动）
// ─────────────────────────────────────────────────────────

// POST /api/title/equip — 佩戴/摘下称号（{titleId:number|null}；佩戴须已持有；S1 v26e 双写 saves.title_id 列 + save_data.player.xianwuTitle）
app.post('/api/title/equip', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `title:equip:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const raw = req.body?.titleId;
  if (raw == null || raw === 0) {
    // 摘下（S1 v26e）：title_id 列 + save_data.player.xianwuTitle 同锁同语句原子双清；无存档行 -> 400
    const r = await updatePlayerSave(req.user.id, (sd: any) => {
      if (sd && sd.player && sd.player.xianwuTitle) delete sd.player.xianwuTitle;
    }, { title_id: null });
    if (!r.ok) {
      if (r.error === 'No save found') return res.status(400).json({ error: '请先进游戏创建角色' });
      return res.status(500).json({ error: 'Database error' });
    }
    return res.json({ ok: true, titleId: null });
  }
  const tid = asInt(raw);
  if (!tid) return res.status(400).json({ error: 'titleId 非法' });
  try {
    const owned = await dbGet('SELECT 1 AS ok FROM player_titles WHERE user_id = ? AND title_id = ?', [req.user.id, tid]);
    if (!owned) return res.status(403).json({ error: '尚未获得该称号' });
    const trow = await dbGet('SELECT name FROM titles WHERE id = ?', [tid]);
    if (!trow) return res.status(404).json({ error: '称号不存在' });
    const r = await updatePlayerSave(req.user.id, (sd: any) => {
      if (!sd.player) sd.player = {};
      sd.player.xianwuTitle = { id: tid, name: trow.name };
    }, { title_id: tid });
    if (!r.ok) {
      if (r.error === 'No save found') return res.status(400).json({ error: '请先进游戏创建角色' });
      return res.status(500).json({ error: 'Database error' });
    }
    res.json({ ok: true, titleId: tid });
  } catch (e: any) {
    console.error('title equip error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

// POST /api/gm/title/grant — GM 发放称号（{userId|username, titleId}；INSERT OR IGNORE 幂等，重复发放 granted:false）
app.post('/api/gm/title/grant', authenticateGM, async (req: any, res: any) => {
  const { userId, username, titleId } = req.body || {};
  const tid = asInt(titleId);
  if (!tid) return res.status(400).json({ error: '需要 titleId' });
  try {
    const t = await dbGet('SELECT id, name FROM titles WHERE id = ?', [tid]);
    if (!t) return res.status(404).json({ error: '称号不存在' });
    let uid: number | null = null;
    if (userId) uid = asInt(userId);
    else if (username) {
      const u = await dbGet('SELECT id FROM users WHERE username = ?', [asStr(username).slice(0, 32)]);
      uid = u ? Number(u.id) : null;
    }
    if (!uid) return res.status(400).json({ error: '需要 userId / username' });
    const r = await dbRun('INSERT OR IGNORE INTO player_titles (user_id, title_id) VALUES (?, ?)', [uid, tid]);
    logGmAction('title_grant', `user:${uid}`, { titleId: tid, title: t.name, granted: r.changes > 0 });
    res.json({ ok: true, granted: r.changes > 0 });
  } catch (e: any) {
    console.error('gm title grant error:', e?.message || e);
    res.status(500).json({ error: '发放失败' });
  }
});

// ─────────────────────────────────────────────────────────
// Y2 每日活跃任务 API（伴生页 /yl/apps/quest/ 用；每日 0 点按北京时区重置）
// ─────────────────────────────────────────────────────────

// GET /api/quest/summary — 当日任务进度 + 活跃度 + 宝箱 + 回归 buff + 称号（一页全量）
app.get('/api/quest/summary', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `quest:summary:${req.user?.id ?? req.ip}` }), (req: any, res: any) => {
  const date = bjDate(Date.now());
  const nowMs = Date.now();
  db.all('SELECT quest_key, progress, done FROM daily_quests WHERE user_id = ? AND date = ?', [req.user.id, date], (err1: any, quests: any[]) => {
    if (err1) return res.status(500).json({ error: 'Database error' });
    db.get('SELECT return_buff_until, title_id FROM saves WHERE user_id = ?', [req.user.id], (err2: any, meta: any) => {
      if (err2) return res.status(500).json({ error: 'Database error' });
      db.all(`SELECT t.id, t.name, t.attr_json, t.source FROM player_titles pt JOIN titles t ON t.id = pt.title_id
              WHERE pt.user_id = ? ORDER BY t.id LIMIT 100`, [req.user.id], (err3: any, owned: any[]) => {
        if (err3) return res.status(500).json({ error: 'Database error' });
        db.all('SELECT id, name, attr_json, source FROM titles ORDER BY id LIMIT 100', (err4: any, catalog: any[]) => {
          if (err4) return res.status(500).json({ error: 'Database error' });
          const rows = quests || [];
          const qOf = (key: string) => rows.find((r) => r.quest_key === key);
          // T9 0.8.8：18 项读时计算（不依赖 daily_quests 新行）；legacy 4 键取 max(行值, 读时值)
          collectDailyActivity(req.user.id, date).then((collected) => {
            const byKey: Record<string, { progress: number; done: boolean; pts: number }> = {};
            for (const it of collected.items) byKey[it.key] = { progress: it.progress, done: it.done, pts: it.points };
            const questList = QUEST_DEFS.map((def) => {
              const row = qOf(def.key);
              const c = byKey[def.key] || { progress: 0, done: false, pts: 0 };
              const rowProgress = Number(row?.progress) || 0;
              // legacy 行值（tick 写的 progress）与读时值取大，保证不漏分
              const progress = LEGACY_QUEST_KEYS.includes(def.key) ? Math.max(rowProgress, c.progress) : c.progress;
              const done = !!(row && Number(row.done) === 1) || c.done;
              const n = Math.min(def.limit, Math.floor(progress / Math.max(1, def.target)));
              return {
                key: def.key, name: def.name, group: def.group, unit: def.unit,
                target: def.target, points: def.points, limit: def.limit,
                progress, done, score: Math.min(def.limit, n) * def.points,
              };
            });
            const activity = Math.min(ACTIVITY_MAX,
              questList.reduce((a, q) => a + (Number(q.score) || 0), 0));
            const realmRow = meta || {};
            const rf = ylrf(meta?.realm);
            const chests = CHEST_TIERS.map((tier) => {
              const row = qOf(chestKey(tier));
              const expTimes = CHEST_EXP_TIMES[tier] || 0;
              const tickets = CHEST_TICKETS[tier] || 0;
              return {
                tier,
                reward: Math.floor((CHEST_REWARDS[tier] || 0) * rf),
                exp: expTimes, tickets,
                unlocked: isChestUnlocked(activity, tier),
                claimed: !!(row && Number(row.done) === 1),
              };
            });
            const week = bjWeekStart(nowMs);
            collectWeeklyActivity(req.user.id, week).then((weekActivity) => {
              // claimedfix：activity_milestones.week 列存的是 **claimKey**（里程碑端点写 'w'+week+'_'+tier），
              //   原来按裸 week（'2026-09-28'）查 ⇒ 永远匹配不到 ⇒ claimedTiers 恒空 ⇒ claimed 恒 false。
              //   改按 claimKey 前缀匹配。LIKE 里的 '_' 是单字符通配符，恰好吃掉键里那个字面 '_'；
              //   裸周号只含数字与 '-'（无 %/_）⇒ 前缀全字面；传承石月频行以 'm' 开头（'m<YYYY-MM>_<tier>_legacy'）
              //   ⇒ 不匹配 'w' 前缀，不会被误算成「档位已领」。
              db.all('SELECT tier FROM activity_milestones WHERE user_id = ? AND week LIKE ?', [req.user.id, 'w' + week + '_%'], (errm: any, mrows: any[]) => {
                const claimedTiers = new Set((mrows || []).map((r) => Number(r.tier)));
                const milestones = WEEK_MILESTONES.map((m) => ({
                  tier: m.tier,
                  reward: Math.floor(m.wbase * rf),
                  exp: m.wexp, tickets: m.wtk, legacy: m.legacy,
                  monthly: m.tier === MILE_MONTHLY_TIER,
                  unlocked: weekActivity >= m.tier,
                  claimed: claimedTiers.has(m.tier),
                }));
                res.json({
                  date,
                  quests: questList,
                  groups: QUEST_GROUPS,
                  activity,
                  activityMax: ACTIVITY_MAX,
                  chests,
                  week, weekActivity, weekMax: ACTIVITY_MAX * 7,
                  milestones,
                  realmMult: rf,
                  returnBuff: { until: buffUntil, active: mult > 1, multiplier: mult },
                  titleEquipped: meta?.title_id != null ? Number(meta.title_id) : null,
                  ownedTitles: (owned || []).map((t) => ({ id: Number(t.id), name: t.name, attr: attr(t.attr_json), source: t.source })),
                  allTitles: (catalog || []).map((t) => ({ id: Number(t.id), name: t.name, attr: attr(t.attr_json), source: t.source })),
                });
              });
            }).catch(() => res.status(500).json({ error: 'Database error' }));
          }).catch(() => res.status(500).json({ error: 'Database error' }));
          const buffUntil = meta && meta.return_buff_until != null ? Number(meta.return_buff_until) : null;
          const mult = returnBuffMultiplier(buffUntil, nowMs);
          const attr = (s: any) => { try { return JSON.parse(String(s || '{}')); } catch { return {}; } };
        });
      });
    });
  });
});

// POST /api/quest/chest — 领取活跃度宝箱（{tier:25|50|75|100}）→ 邮件发灵石
// 领取占位=UNIQUE(user_id,date,quest_key) 单语句原子（并发双击只一方生效）；发信失败补偿删占位可重试
app.post('/api/quest/chest', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `quest:chest:${req.user?.id ?? req.ip}` }), (req: any, res: any) => {
  const tier = asInt(req.body?.tier);
  if (!CHEST_TIERS.includes(tier)) return res.status(400).json({ error: 'tier 非法' });
  const userId = req.user.id;
  const date = bjDate(Date.now());
  const key = chestKey(tier);
  dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]).then((srow: any) => {
    let realm = '';
    try { realm = String(JSON.parse(srow?.save_data || '{}')?.player?.realm || ''); } catch { realm = ''; }
    const rf = ylrf(realm);
    const baseReward = Math.floor((CHEST_REWARDS[tier] || 0) * rf);
    const expTimes = CHEST_EXP_TIMES[tier] || 0;
    const tickets = CHEST_TICKETS[tier] || 0;
    return collectDailyActivity(userId, date).then((collected) => ({ rf, baseReward, expTimes, tickets, activity: collected.activity }));
  }).then((info: any) => {
    if (!isChestUnlocked(info.activity, tier)) return res.status(409).json({ error: '活跃度不足' });
    db.run('INSERT INTO daily_quests (user_id, date, quest_key, progress, done) VALUES (?, ?, ?, 0, 1)', [userId, date, key], function (this: any, err2: any) {
      if (err2) {
        if (String(err2.message || '').includes('UNIQUE')) return res.status(409).json({ error: '宝箱已领取' });
        return res.status(500).json({ error: 'Database error' });
      }
      // T9 §7.4 P0 发奖通道（零风险降级）：insertMail 只支持灵石附件 ⇒
      //   灵石 base×YLRF 走邮件附件；修为（打坐等效）×12 与抽奖券（）折算成灵石一并附上。
      const expStone = Math.floor(info.expTimes * CHEST_EXP_TO_STONE * 1);
      const totalStone = info.baseReward + expStone;
      const detail = `灵石 ×${info.baseReward}`
        + (info.expTimes > 0 ? `、修为等效 ×${info.expTimes}（折灵石 ×${expStone}）` : '')
        + (info.tickets > 0 ? `、抽奖券 ×${info.tickets}` : '');
      insertMail(userId, '活跃度宝箱', `今日活跃度达到 ${tier}，宝箱开启：${detail} 已附上（合计灵石 ×${totalStone}），点击领取。`, 'system', totalStone)
        .then(() => res.json({ ok: true, tier, reward: totalStone, base: info.baseReward, exp: info.expTimes, tickets: info.tickets }))
        .catch((e: any) => {
          console.error('chest mail error:', e?.message || e);
          db.run('DELETE FROM daily_quests WHERE user_id = ? AND date = ? AND quest_key = ?', [userId, date, key], () => {
            res.status(500).json({ error: '发奖失败，请重试' });
          });
        });
    });
  }).catch((e: any) => {
    console.error('chest error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  });
});

// POST /api/quest/milestone — 领取周里程碑（{tier:500|1000|1500|1900|2310}）→ 邮件发灵石
//   T9 0.8.8：幂等靠 activity_milestones 的 UNIQUE(user_id, week, tier)（周）；
//   R-013c：**常规奖励一律按周**（含最高档 2,310，恢复周频）；**仅「传承石」按月**限领一次
//     （独立幂等键 <周一>_legacy，tier 存 -tier 哨兵；用户拍板「传承石最多一个月一个」）。
app.post('/api/quest/milestone', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `quest:ms:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const tier = asInt(req.body?.tier);
  const mdef = WEEK_MILESTONES.find((m) => m.tier === tier);
  if (!mdef) return res.status(400).json({ error: 'tier 非法' });
  const userId = req.user.id;
  const week = bjWeekStart(Date.now());
  const isStoneTier = mdef.legacy === '传承石';   // 声明在 try 外，供 catch 的 UNIQUE 分支引用
  const claimKey = 'w' + week + '_' + tier;                                  // R-013c 常规奖励：每周一次
  const stoneKey = 'm' + weekMonthKey(week) + '_' + tier + '_legacy';        // R-013c 传承石：每月一次
  try {
    const srow: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    let realm = '';
    try { realm = String(JSON.parse(srow?.save_data || '{}')?.player?.realm || ''); } catch { realm = ''; }
    const rf = ylrf(realm);
    const weekActivity = await collectWeeklyActivity(userId, week);
    if (weekActivity < mdef.tier) return res.status(409).json({ error: '周活跃度不足' });
    // R-013c：常规奖励**每周**限领一次（含 2,310 档，恢复周频；T9 原语义）。
    //   week 列存 claimKey 直接复用 UNIQUE(user_id, week, tier) 实现幂等。
    await dbRun('INSERT INTO activity_milestones (user_id, week, tier, claimed_at) VALUES (?, ?, ?, ?)', [userId, claimKey, tier, Date.now()]);
    // R-013c：传承石**每月**限领一次 —— 独立幂等行（week 存 'm<YYYY-MM>_<tier>_legacy'，
    //   tier 存 -tier 哨兵，与周档行互不冲突）。本月已领过 ⇒ 本次仍照发常规奖励，只是不再发石。
    let stoneDue = isStoneTier;
    if (stoneDue) {
      try {
        await dbRun('INSERT INTO activity_milestones (user_id, week, tier, claimed_at) VALUES (?, ?, ?, ?)', [userId, stoneKey, -tier, Date.now()]);
      } catch (e2: any) {
        if (String(e2?.message || '').includes('UNIQUE')) {
          stoneDue = false;   // 本月传承石已领 ⇒ 常规奖励照发，不报错
        } else {
          await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, claimKey, tier]);
          throw e2;           // 真错 ⇒ 撤回周档占位，交外层 500
        }
      }
    }
    const baseReward = Math.floor(mdef.wbase * rf);
    const expStone = Math.floor(mdef.wexp * CHEST_EXP_TO_STONE);
    // R-013b：传承石改发**实物**（走 updatePlayerSave 背包通道，同宗门丹药 sectPillItem），
    //   不再折算成灵石塞邮件附件。实物先发；发信失败则补偿撤回（见下，防重复发放）。
    const totalStone = baseReward + expStone;
    const detail = `灵石 ×${baseReward}、修为等效 ×${mdef.wexp}（折灵石 ×${expStone}）`
      + (stoneDue ? `、传承石 ×1（实物已入背包，每月限一次）` : '')
      + (isStoneTier && !stoneDue ? `、本月传承石已领取` : '')
      + (mdef.wtk > 0 ? `、抽奖券 ×${mdef.wtk}` : '');
    let grantedStoneId = '';
    if (stoneDue) {
      const stone = legacyStoneItem();
      grantedStoneId = stone.id;
      const g = await updatePlayerSave(userId, (sd: any) => {
        if (!sd.player || typeof sd.player !== 'object') sd.player = {};
        sd.player.inventory = Array.isArray(sd.player.inventory) ? sd.player.inventory : [];
        sd.player.inventory.push(stone);
      });
      if (!g.ok) {
        await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, claimKey, tier]);
        await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, stoneKey, -tier]);
        return res.status(500).json({ error: '发奖失败，请重试' });
      }
    }
    try {
      await insertMail(userId, '周里程碑·勤修', `本周活跃度达到 ${tier}，${detail} 已附上（合计灵石 ×${totalStone}），点击领取。`, 'system', totalStone);
      res.json({ ok: true, tier, reward: totalStone, week, weekActivity, monthly: isStoneTier, item: stoneDue ? LEGACY_STONE_NAME : undefined });
    } catch (e: any) {
      console.error('milestone mail error:', e?.message || e);
      // 补偿式回滚（同 mailClaimCore）：撤回已发的传承石，再删两条占位，玩家可重试（防重复发放）
      if (grantedStoneId) {
        await updatePlayerSave(userId, (sd: any) => {
          if (Array.isArray(sd.player?.inventory)) {
            const i = sd.player.inventory.findIndex((x: any) => x && x.id === grantedStoneId);
            if (i >= 0) sd.player.inventory.splice(i, 1);
          }
        }).catch(() => undefined);
      }
      await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, claimKey, tier]);
      if (stoneDue) await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, stoneKey, -tier]);
      res.status(500).json({ error: '发奖失败，请重试' });
    }
  } catch (e: any) {
    if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '该里程碑本周已领取' });
    console.error('milestone error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

// ─────────────────────────────────────────────────────────
// Y15 统计面板 API（伴生页 /yl/apps/stats/ 用）：近 30 日修为/灵石/击杀/在线时长曲线
// 数据源=POST /api/save 存档差值累加（stats_daily，与 Y2 每日任务埋点同源同口径）
// ─────────────────────────────────────────────────────────

// GET /api/stats/me — 近 30 日四维日序列（缺日补零，date 升序）
app.get('/api/stats/me', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `stats:me:${req.user?.id ?? req.ip}` }), (req: any, res: any) => {
  const nowMs = Date.now();
  const since = bjDate(nowMs - (STATS_DAYS - 1) * DAY_MS);
  db.all(
    'SELECT date, exp_gain, silver_gain, kills, minutes FROM stats_daily WHERE player_id = ? AND date >= ? ORDER BY date LIMIT ?',
    [req.user.id, since, STATS_DAYS + 5],
    (err: any, rows: any[]) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json({ days: STATS_DAYS, series: buildStatsSeries(rows || [], nowMs) });
    }
  );
});

// ─────────────────────────────────────────────────────────
// Y16 江湖志 API（全服共享时间线）：突破飞升/天劫/赛季结算/大额邮件/入世等关键事件
// 埋点写在各自业务路径（logChronicle，fire-and-forget）；此处只读
// ─────────────────────────────────────────────────────────

// GET /api/chronicle?page=1 — 公开只读（同 /api/leaderboard 无需登录），50 条/页，新事件在前
// Y16B：每条附 praise_count（传阅数，LEFT JOIN COUNT）；请求带有效凭据时再附 praisedByMe（是否已传阅），无凭据仍公开可读
app.get('/api/chronicle', rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `chronicle:${req.user?.id ?? req.ip}` }), (req: any, res: any) => {
  const page = clampPage(req.query.page);
  let meId = 0; // 可选身份：只用于已传阅标记，凭据缺失/失效一律按未登录处理
  const bearer = String(req.headers['authorization'] || '').split(' ')[1] || '';
  if (bearer) {
    try {
      const p: any = jwt.verify(bearer, JWT_SECRET_USED);
      if (p?.type === 'access') meId = Number(p.id) || 0;
    } catch { /* 无效凭据静默降级为未登录 */ }
  }
  db.get('SELECT COUNT(*) AS c FROM chronicle', [], (err: any, cnt: any) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    db.all(
      `SELECT c.id, c.ts, c.player_id, c.nickname, c.text, COUNT(cp.user_id) AS praise_count
       FROM chronicle c LEFT JOIN chronicle_praise cp ON cp.entry_id = c.id
       GROUP BY c.id ORDER BY c.id DESC LIMIT ? OFFSET ?`,
      [CHRONICLE_PAGE_SIZE, (page - 1) * CHRONICLE_PAGE_SIZE],
      (err2: any, rows: any[]) => {
        if (err2) return res.status(500).json({ error: 'Database error' });
        const ids = (rows || []).map((r: any) => Number(r.id));
        const respond = (praised: Set<number>) => {
          res.json({
            page,
            pageSize: CHRONICLE_PAGE_SIZE,
            total: Number(cnt?.c) || 0,
            entries: (rows || []).map((r: any) => ({
              id: Number(r.id),
              ts: r.ts,
              playerId: r.player_id == null ? null : Number(r.player_id),
              nickname: String(r.nickname || ''),
              text: String(r.text || ''),
              praiseCount: Number(r.praise_count) || 0, // Y16B 传阅数
              praisedByMe: praised.has(Number(r.id)),   // Y16B 我是否已传阅（无凭据恒 false）
            })),
          });
        };
        if (!meId || !ids.length) return respond(new Set());
        db.all(
          `SELECT entry_id FROM chronicle_praise WHERE user_id = ? AND entry_id IN (${ids.map(() => '?').join(',')})`,
          [meId, ...ids],
          (err3: any, prows: any[]) => {
            // 标记查询失败不阻塞主列表（降级为全未传阅）
            respond(err3 ? new Set() : new Set((prows || []).map((x: any) => Number(x.entry_id))));
          }
        );
      }
    );
  });
});

// POST /api/chronicle/praise {id} — Y16B 传阅（authenticateToken+rateLimit；每人每条限一次：
// INSERT OR IGNORE 后 changes=0 即重复 → 409「你已传阅过」，同时返回该条当前传阅总数）。
// 恰第 10 次（INSERT 后 COUNT===10，行只增不减故全生命周期只命中一次）：当事人（entry.player_id
// 非空）得一次性灵石奖 1000×1.5^境界（rankings.realm_index 查得，updatePlayerSave 入账
// fire-and-forget），并 logChronicle 播报；系统条目（player_id 为空）跳过奖励只播报。
app.post('/api/chronicle/praise', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `chronicle:praise:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const id = asInt(req.body?.id);
  if (!id) return res.status(400).json({ error: '需要 id' });
  try {
    const entry = await dbGet('SELECT id, player_id, nickname FROM chronicle WHERE id = ?', [id]);
    if (!entry) return res.status(404).json({ error: '该条轶事不存在' });
    const ins = await dbRun('INSERT OR IGNORE INTO chronicle_praise (entry_id, user_id, created_at) VALUES (?, ?, ?)', [id, req.user.id, Date.now()]);
    const cntRow = await dbGet('SELECT COUNT(*) AS c FROM chronicle_praise WHERE entry_id = ?', [id]);
    const praiseCount = Number(cntRow?.c) || 0;
    if (!ins.changes) return res.status(409).json({ error: '你已传阅过', praiseCount });
    let stones = 0;
    if (praiseCount === CHRONICLE_PRAISE_GOAL) {
      const who = String(entry.nickname || '').slice(0, 32);
      if (entry.player_id != null) {
        const rk = await dbGet('SELECT realm_index FROM rankings WHERE user_id = ?', [Number(entry.player_id)]).catch(() => null);
        stones = realmStoneGain(CHRONICLE_PRAISE_BASE, rk?.realm_index); // 0.8.9 [reward089] 统一口径
        if (stones > 0) {
          // 入账 fire-and-forget（saveLock 互斥、无存档等失败自吞），不阻塞传阅响应
          updatePlayerSave(Number(entry.player_id), (sd: any) => {
            if (!sd.player || typeof sd.player !== 'object') sd.player = {};
            sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + stones;
          }).catch((e: any) => console.error('chronicle praise reward error:', e?.message || e));
        }
      }
      // 系统条目（player_id 为空）：跳过奖励只播报（stones 恒 0）
      logChronicle(entry.player_id != null ? Number(entry.player_id) : null, who, `【传阅江湖】『${who}』事迹传遍江湖，众口相传`);
    }
    res.json({ ok: true, praiseCount, reward: praiseCount === CHRONICLE_PRAISE_GOAL ? stones : 0 });
  } catch (e: any) {
    console.error('chronicle praise error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// E1 经济镜像 GM API（旁路账本只读，authenticateGM）：summary=单玩家近 30 日汇总；anomalies=异常清单 TOP50
// 在线判定口径：saves.updated_at（GM 玩家列表 last_active 同源）5 分钟内=在线
// ─────────────────────────────────────────────────────────
const ECON_SUMMARY_DAYS = 30;           // summary 窗口（近 30 日）
const ECON_SUMMARY_RECENT = 20;         // summary 附带最近流水条数
const ECON_ANOMALY_LIMIT = 50;          // 异常清单 TOP50
const ECON_ANOMALY_MAX_DAYS = 90;       // ?days 上限防深扫
const ECON_ONLINE_MS = 5 * 60 * 1000;   // “在线”=5 分钟内存档活跃

// economy_ledger.anomaly_json → flags（坏 JSON/空 → []）
function econFlagsOf(anomalyJson: unknown): string[] {
  try {
    const o = JSON.parse(String(anomalyJson ?? ''));
    return Array.isArray(o?.flags) ? o.flags.map(String) : [];
  } catch { return []; }
}

// GET /api/economy/summary?player=<userId|username> — 该玩家近 30 日 ledger 汇总 + 最近 20 条流水
app.get('/api/economy/summary', authenticateGM, async (req: any, res: any) => {
  try {
    const raw = String(req.query.player ?? '').trim();
    if (!raw) return res.status(400).json({ error: 'player required' });
    let player: any = null;
    if (/^\d+$/.test(raw)) player = await dbGet('SELECT id, username FROM users WHERE id = ?', [Number(raw)]);
    if (!player) player = await dbGet('SELECT id, username FROM users WHERE username = ?', [raw.slice(0, 32)]);
    if (!player) return res.status(404).json({ error: 'Player not found' });
    const totals = await dbGet(
      `SELECT COUNT(*) AS entries,
              COALESCE(SUM(silver_delta), 0) AS silver_net,
              COALESCE(SUM(CASE WHEN silver_delta > 0 THEN silver_delta ELSE 0 END), 0) AS silver_up,
              COALESCE(SUM(CASE WHEN silver_delta < 0 THEN -silver_delta ELSE 0 END), 0) AS silver_down,
              COALESCE(SUM(exp_delta), 0) AS exp_net,
              SUM(CASE WHEN anomaly_json IS NOT NULL THEN 1 ELSE 0 END) AS anomalies,
              MIN(ts) AS first_ts, MAX(ts) AS last_ts
       FROM economy_ledger WHERE player_id = ? AND ts >= datetime('now', ?)`,
      [player.id, `-${ECON_SUMMARY_DAYS} day`]
    );
    const recent = await dbAll(
      'SELECT id, ts, kind, silver_delta, exp_delta, level_from, level_to, silver_after, anomaly_json FROM economy_ledger WHERE player_id = ? ORDER BY id DESC LIMIT ?',
      [player.id, ECON_SUMMARY_RECENT]
    );
    const lastActive = await dbGet('SELECT updated_at FROM saves WHERE user_id = ?', [player.id]);
    const lastActMs = parseDbTimeMs(lastActive?.updated_at);
    res.json({
      player: { id: player.id, username: player.username },
      days: ECON_SUMMARY_DAYS,
      totals: {
        entries: Number(totals?.entries) || 0,
        silverNet: Number(totals?.silver_net) || 0,
        silverUp: Number(totals?.silver_up) || 0,
        silverDown: Number(totals?.silver_down) || 0,
        expNet: Number(totals?.exp_net) || 0,
        anomalies: Number(totals?.anomalies) || 0,
        firstTs: totals?.first_ts ?? null,
        lastTs: totals?.last_ts ?? null,
      },
      online: lastActMs != null && Date.now() - lastActMs <= ECON_ONLINE_MS,
      lastActive: lastActive?.updated_at ?? null,
      recent: (recent || []).map((r: any) => ({
        id: Number(r.id),
        ts: r.ts,
        kind: String(r.kind || ''),
        silverDelta: r.silver_delta == null ? null : Number(r.silver_delta),
        expDelta: r.exp_delta == null ? null : Number(r.exp_delta),
        levelFrom: r.level_from == null ? null : Number(r.level_from),
        levelTo: r.level_to == null ? null : Number(r.level_to),
        silverAfter: r.silver_after == null ? null : Number(r.silver_after),
        flags: econFlagsOf(r.anomaly_json),
      })),
    });
  } catch (e: any) {
    console.error('economy summary error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

// GET /api/economy/anomalies?days=7&player=<userId|username> — 近 N 日异常清单 TOP50（新→旧；联合 saves.updated_at 判 5 分钟内在线）
// SEC 增强（2026-09-17）：?player 可选过滤（数字 id 或用户名，未命中 404，与 summary 同解析）；nickname 取 rankings.name
// （rank 名=存档 player.name 快照，fix(rank) 同源维护），空/无行回落 username——SQL 端 COALESCE 一次取齐
app.get('/api/economy/anomalies', authenticateGM, async (req: any, res: any) => {
  try {
    const days = Math.min(ECON_ANOMALY_MAX_DAYS, Math.max(1, Math.floor(Number(req.query.days) || 7)));
    let player: any = null;
    const raw = String(req.query.player ?? '').trim();
    if (raw) {
      if (/^\d+$/.test(raw)) player = await dbGet('SELECT id, username FROM users WHERE id = ?', [Number(raw)]);
      if (!player) player = await dbGet('SELECT id, username FROM users WHERE username = ?', [raw.slice(0, 32)]);
      if (!player) return res.status(404).json({ error: 'Player not found' });
    }
    const where = ["l.anomaly_json IS NOT NULL", "l.ts >= datetime('now', ?)"]; // 常量片段拼接，值全走占位符
    const params: any[] = [`-${days} day`];
    if (player) { where.push('l.player_id = ?'); params.push(player.id); }
    const rows = await dbAll(
      `SELECT l.id, l.ts, l.player_id, l.kind, l.silver_delta, l.exp_delta, l.level_from, l.level_to, l.silver_after, l.anomaly_json,
              u.username,
              COALESCE(NULLIF(r.name, ''), u.username, '') AS nickname,
              (SELECT updated_at FROM saves sv WHERE sv.user_id = l.player_id) AS last_active
       FROM economy_ledger l
       LEFT JOIN users u ON u.id = l.player_id
       LEFT JOIN rankings r ON r.user_id = l.player_id
       WHERE ${where.join(' AND ')}
       ORDER BY l.id DESC LIMIT ?`,
      [...params, ECON_ANOMALY_LIMIT]
    );
    const nowMs = Date.now();
    res.json({
      days,
      playerFilter: player ? { id: player.id, username: player.username } : null,
      limit: ECON_ANOMALY_LIMIT,
      total: (rows || []).length,
      anomalies: (rows || []).map((r: any) => {
        const lastActMs = parseDbTimeMs(r.last_active);
        return {
          id: Number(r.id),
          ts: r.ts,
          playerId: Number(r.player_id),
          username: String(r.username ?? ''),
          nickname: String(r.nickname ?? ''),
          silverDelta: r.silver_delta == null ? null : Number(r.silver_delta),
          expDelta: r.exp_delta == null ? null : Number(r.exp_delta),
          levelFrom: r.level_from == null ? null : Number(r.level_from),
          levelTo: r.level_to == null ? null : Number(r.level_to),
          silverAfter: r.silver_after == null ? null : Number(r.silver_after),
          flags: econFlagsOf(r.anomaly_json),
          online: lastActMs != null && nowMs - lastActMs <= ECON_ONLINE_MS,
          lastActive: r.last_active ?? null,
        };
      }),
    });
  } catch (e: any) {
    console.error('economy anomalies error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

// ─────────────────────────────────────────────────────────
// Y17 炼丹炉 API（伴生页 /yl/apps/alchemy/）：三炉位延时玩法——开炉扣灵石，到期出炉按名目发奖励邮件
// 防重复：UNIQUE(player_id,slot)，行存在即炉位在炼（并发双开必有一方冲突 409）；领取即删行
// 事务口径：占炉 → 扣灵石（saveLock 互斥）→ 失败补偿删炉（mailClaimCore 补偿式同款，全或无可重试）
// ─────────────────────────────────────────────────────────

// GET /api/alchemy/list — 我的炉位 + 配方目录（一页全量）
app.get('/api/alchemy/list', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `alchemy:list:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  try {
    const rows = await dbAll('SELECT slot, pill_name, start_at, mature_at FROM alchemy WHERE player_id = ? LIMIT ?', [req.user.id, ALCHEMY_SLOTS]);
    const now = Date.now();
    const bySlot: Record<number, any> = {};
    for (const r of rows || []) bySlot[Number(r.slot)] = r;
    const slots: any[] = [];
    for (let s = 0; s < ALCHEMY_SLOTS; s++) {
      const r = bySlot[s];
      slots.push(r ? {
        slot: s,
        pill: String(r.pill_name),
        startAt: Number(r.start_at),
        matureAt: Number(r.mature_at),
        ready: alchemyIsReady(Number(r.mature_at), now),
        leftMs: Math.max(0, Number(r.mature_at) - now),
      } : { slot: s, pill: null });
    }
    res.json({ now, slots, recipes: alchemyRecipesWithQty(), yieldRate: ALCHEMY_YIELD_RATE, pillQty: ALCHEMY_PILL_QTY });
  } catch (e: any) {
    console.error('alchemy list error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

// POST /api/alchemy/start {pill:'juqi'|'ningyuan'|'pojing', slot:0..2} — 开炉：预检灵石 → 占炉 → 扣灵石
app.post('/api/alchemy/start', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `alchemy:start:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const recipe = alchemyRecipe(req.body?.pill);
  if (!recipe) return res.status(400).json({ error: '未知丹方' });
  const slot = Math.floor(asNum(req.body?.slot));
  if (!alchemySlotOk(slot)) return res.status(400).json({ error: '炉位非法' });
  const userId = req.user.id;
  try {
    // 预检：灵石余额（并发窗口由 updatePlayerSave 内闭包二次校验兜底）
    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    let alcLv = 1;
    try {
      const sd0 = JSON.parse(row.save_data);
      bal = Number(sd0?.player?.spiritStones) || 0;
      alcLv = Math.max(1, Math.min(9, Number(sd0?.player?.alchemyLevel) || 1));
    } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < recipe.cost) return res.status(409).json({ error: `灵石不足：需 ${recipe.cost}，现有 ${bal}` });
    // [r064] 造诣门槛服务端权威（此前只是客户端展示；unlockLevel 缺省视为 1）
    if (alcLv < (recipe.unlockLevel || 1)) return res.status(409).json({ error: `丹道造诣不足：此方需第 ${recipe.unlockLevel || 1} 层，你当前第 ${alcLv} 层` });

    // 占炉：UNIQUE(player_id,slot) 冲突 → 同炉位在炼拒绝（含并发双开）
    const now = Date.now();
    const matureAt = alchemyMatureAt(now, recipe.minutes);
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun(
        'INSERT INTO alchemy (player_id, slot, pill_name, start_at, mature_at) VALUES (?, ?, ?, ?, ?)',
        [userId, slot, recipe.name, now, matureAt]
      );
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '该炉位尚在炼制，不可重复开炉' });
      throw e;
    }

    // 扣灵石（saveLock 互斥 + gm_revision++ 促客户端拉新档）；余额不足/入账失败 → 补偿删炉可重试
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < recipe.cost) { short = true; return; }
      sd.player.spiritStones = b - recipe.cost;
    });
    if (!paid.ok || short) {
      await dbRun('DELETE FROM alchemy WHERE id = ?', [ins.lastID]);
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '开炉失败，请重试') });
    }
    res.json({ ok: true, slot, pill: recipe.name, startAt: now, matureAt, cost: recipe.cost });
  } catch (e: any) {
    console.error('alchemy start error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/alchemy/claim {slot} — 出炉领取：提前收获 409 拒绝；删行占位原子防双领；奖励走邮件（失败补偿回炉可重试）
app.post('/api/alchemy/claim', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `alchemy:claim:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const slot = Math.floor(asNum(req.body?.slot));
  if (!alchemySlotOk(slot)) return res.status(400).json({ error: '炉位非法' });
  const userId = req.user.id;
  try {
    const r = await dbGet('SELECT id, pill_name, start_at, mature_at FROM alchemy WHERE player_id = ? AND slot = ?', [userId, slot]);
    if (!r) return res.status(404).json({ error: '该炉位空空如也' });
    const now = Date.now();
    const matureAt = Number(r.mature_at);
    if (!alchemyIsReady(matureAt, now)) {
      return res.status(409).json({ error: `丹药尚未成形，还差约 ${Math.ceil((matureAt - now) / 60000)} 分钟`, matureAt });
    }
    // Y21：活动倍率（出炉化灵灵石结算自动应用；引擎读取失败按 ×1 保底，不阻塞出炉）
    const evMult = await resolveEventMults(now).catch(() => ({ events: [] as any[], expMult: 1, stonesMult: 1 }));
    const del = await dbRun('DELETE FROM alchemy WHERE id = ? AND player_id = ?', [Number(r.id), userId]);
    if (!del.changes) return res.status(409).json({ error: '该炉已领取' }); // 并发双击只一方生效
    const pill = String(r.pill_name);
    const recipe = alchemyRecipeByName(pill);
    // Y6B：师徒加成/出师增益（徒弟在门且师徒都在线 ×1.1；本人有未到期出师增益 ×1.3；读取失败 ×1 保底）
    const mnG = await resolveMentorGains(userId, now).catch(() => ({ expMult: 1, stonesMult: 1 }));
    // [r077] 开炉按成熟时长/方子档随机出丹枚数（1-10 基础方 → 1-2 高阶），枚数折算灵石（期望同改前）
    const pillCount = recipe ? alchemyRollPillCount(pill) : 0;
    const yieldStones = recipe ? actApplyGain(alchemyPillYield(recipe.cost, pillCount, pill), evMult.stonesMult * mnG.stonesMult) : 0; // Y21 活动 × Y6B 师徒倍率入账；[r077] 枚数→灵石（保本下限 cost）
    // Y3A：凝元丹出炉额外凝丹入囊（渡劫垫刀材料，upsert 幂等；失败不影响出炉本体，只记日志）
    let pillsGained = 0;
    if (pill === '凝元丹') {
      const credit = await dbRun(
        `INSERT INTO rebirth_state (user_id, fail_until, wins, last_target, pill_stash) VALUES (?, NULL, 0, NULL, 1)
         ON CONFLICT(user_id) DO UPDATE SET pill_stash = pill_stash + 1, updated_at = CURRENT_TIMESTAMP`,
        [userId]
      ).catch((e: any) => { console.error('pill stash credit error:', e?.message || e); return { changes: 0 }; });
      pillsGained = credit.changes > 0 ? 1 : 0;
    }
    try {
      const pillLine = pillsGained > 0 ? '\n· 凝元丹 ×1 已收入丹囊（渡劫页可垫刀，每颗 +3% 天劫成功率）' : '';
      await insertMail(userId, '丹药出炉',
        `炉火纯青，「${pill}」×${pillCount} 枚丹成出炉！\n\n· 丹药化灵：灵石 ×${yieldStones}（点击下方领取）${pillLine}\n\n丹炉已空，下一炉随时可开。`,
        'system', yieldStones);
    } catch (e: any) {
      console.error('alchemy claim mail error:', e?.message || e);
      // 补偿：把丹回炉（行已删，INSERT 必不冲突），玩家可重试领取
      await dbRun('INSERT INTO alchemy (player_id, slot, pill_name, start_at, mature_at) VALUES (?, ?, ?, ?, ?)',
        [userId, slot, pill, Number(r.start_at), matureAt]).catch(() => {});
      return res.status(500).json({ error: '发奖失败，请重试' });
    }
    // [act087] C 灵玉阁掉玉挂点（入账点：炼丹出炉化灵灵石已确认发放；活动不活跃时零开销）
    if (yieldStones > 0) actDropTokens(userId, yieldStones, now).catch((e: any) => console.error('act drop tokens (alchemy) error:', e?.message || e));
    // [r064] R-064 出炉加丹道造诣（用户报「出炉没加造诣」）：熟练度 = 方子档位 profGain ×1.2，
    //   门槛与丹房 pm 同表、上限 9 层；updatePlayerSave 落档（saveLock + gm_revision++ 拉新档）。
    //   入账失败不阻塞出炉本体（灵石/丹囊已发，只记日志——拍板 2026-10-01）。
    let profGained = 0, profLevel = 0, profNow = 0, profNext = 0, profUp = false;
    try {
      const profGain = Math.max(0, Math.floor((recipe ? (recipe.profGain || 0) : 0) * ALCHEMY_PROF_FURNACE_MULT));
      if (profGain > 0) {
        const up = await updatePlayerSave(userId, (sd: any) => {
          const pl = sd.player || (sd.player = {});
          let lv = Math.max(1, Math.min(9, Number(pl.alchemyLevel) || 1));
          let prof = Math.max(0, Number(pl.alchemyProficiency != null ? pl.alchemyProficiency : pl.alchemyExp) || 0) + profGain;
          let nextAt = ALCHEMY_PROF_GATE[lv] || 0;
          while (lv < 9 && nextAt > 0 && prof >= nextAt) { prof -= nextAt; lv += 1; profUp = true; nextAt = ALCHEMY_PROF_GATE[lv] || 0; }
          if (lv >= 9) { nextAt = 0; }
          pl.alchemyLevel = lv; pl.alchemyProficiency = prof;
          profGained = profGain; profLevel = lv; profNow = prof; profNext = nextAt;
        });
        if (!up.ok) { profGained = 0; profLevel = 0; profNow = 0; profNext = 0; profUp = false; console.error('alchemy claim prof save error:', up.error); }
      }
    } catch (e: any) { console.error('alchemy claim prof error:', e?.message || e); }
    res.json({ ok: true, slot, pill, yieldStones, pillCount, pillsGained, eventMults: { exp: evMult.expMult, stones: evMult.stonesMult }, prof: profGained > 0 ? { gained: profGained, level: profLevel, proficiency: profNow, nextAt: profNext, leveledUp: profUp } : null });
  } catch (e: any) {
    console.error('alchemy claim error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// Y19 洞府灵田 API（伴生页 /yl/apps/farm/）：三田位延时种植——slot 1 免费，2/3 灵石开垦（永久）；
// 种植扣种子灵石，收获灵石+修为一笔入档（updatePlayerSave saveLock 互斥 + gm_revision++ 促客户端拉新档；
// offline/claim 同款全或无：收获标记守卫推进 → 入档 → 失败补偿回退标记可重试 → 回执邮件尽力而为）；
// 提前收获=收益减半（玩家自选止损）；防重复种植/双收：idx_farm_active_slot 部分唯一索引 + 守卫式 UPDATE
// ─────────────────────────────────────────────────────────

// GET /api/farm/status — 三田位全量（开垦状态/空田/生长中/已成熟）+ 作物目录 + 灵石余额（伴生页头部展示）
app.get('/api/farm/status', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `farm:status:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const [unlocks, crops, saveRow, careRows, histRows] = await Promise.all([
      dbAll('SELECT slot FROM farm_unlocks WHERE player_id = ? LIMIT ?', [userId, FARM_SLOTS]),
      dbAll('SELECT id, slot, crop, planted_at, mature_at FROM spirit_farm WHERE player_id = ? AND harvested = 0 LIMIT ?', [userId, FARM_SLOTS]),
      dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
      dbAll('SELECT slot, tended, boosted, last_tend_at FROM farm_daily_care WHERE player_id = ? AND date = ?', [userId, bjDate(Date.now())]),
      dbAll('SELECT id, slot, crop FROM spirit_farm WHERE player_id = ? AND harvested = 1 ORDER BY id DESC LIMIT 24', [userId]),
    ]);
    let stones = 0;
    let grottoLevel = 0;
    let playerObj: any = null; // T5：供服用效果的百分比上限触顶判定（只读）
    if (saveRow) {
      try {
        const sd0 = JSON.parse(saveRow.save_data);
        stones = Math.max(0, Math.floor(Number(sd0?.player?.spiritStones) || 0));
        grottoLevel = Math.min(10, Math.max(0, Math.floor(Number(sd0?.player?.grotto?.level) || 0)));
        playerObj = sd0?.player && typeof sd0.player === 'object' ? sd0.player : null;
      } catch { stones = 0; }
    }
    const unlocked = new Set<number>([1]); // slot 1 永远免费可用
    for (const u of unlocks || []) { const s = Number(u.slot); if (farmSlotOk(s)) unlocked.add(s); }
    const bySlot: Record<number, any> = {};
    for (const r of crops || []) bySlot[Number(r.slot)] = r;
    const now = Date.now();
    const today = bjDate(now);
    // T10：当日照料/催熟行按田索引；连作数 = 活跃行之前最近同田历史行中同作物的连续条数
    const careBySlot: Record<number, any> = {};
    for (const c of careRows || []) careBySlot[Number(c.slot)] = c;
    const streakOf = (slotNum: number, cropKey: string, beforeId: number): number => {
      let n = 0;
      for (const hr of (histRows || [])) {
        if (Number(hr.slot) !== slotNum || Number(hr.id) >= beforeId) continue;
        if (String(hr.crop) === cropKey) n++;
        else break; // 第一条同田历史行不同作物 ⇒ 无连作
      }
      return n;
    };
    const slots: any[] = [];
    let readyCount = 0;
    for (let s = 1; s <= FARM_SLOTS; s++) {
      const r = bySlot[s];
      const key = r ? String(r.crop) : '';
      const def = farmCrop(key);
      const ready = !!(r && def && farmIsReady(Number(r.mature_at), now));
      if (ready) readyCount++;
      const care = careBySlot[s];
      const tended = !!care && Number(care.tended) === 1;
      const boosted = !!care && Number(care.boosted) === 1;
      const leftMs = r && def ? Math.max(0, Number(r.mature_at) - now) : 0;
      // 虫害（净）：仅生长中田 roll，且未照料（照料即净虫害）；status 与 harvest 各自复算恒一致
      const pest = !!(r && def && !ready && !tended && farmPestToday(userId, s, key, Number(r.planted_at), today));
      slots.push({
        slot: s,
        unlocked: unlocked.has(s),
        crop: r && def ? {
          key,
          name: def.name,
          plantedAt: Number(r.planted_at),
          matureAt: Number(r.mature_at),
          ready,
          leftMs,
        } : null,
        // T10 扩展：care（当日照料/催熟/净虫害）/ streak（连作茬数）/ boostCost（催熟费；无生长中作物=null）
        care: { date: today, tended: tended ? 1 : 0, boosted: boosted ? 1 : 0, pest,
          // ★ R-019①：照料冷却绝对就绪时刻（epoch ms；0 = 无冷却）。客户端 YlxwFtTendCdMs 消费。
          tendReadyAt: (care && Number(care.last_tend_at) > 0) ? Number(care.last_tend_at) + FARM_TEND_CD_MS : 0 },
        streak: r ? streakOf(s, key, Number(r.id)) : 0,
        boostCost: r && def && !ready ? farmBoostCost(leftMs) : null,
      });
    }
    let nextUnlock: any = null;
    for (let s = 1; s <= FARM_SLOTS; s++) {
      if (!unlocked.has(s)) { nextUnlock = { slot: s, cost: FARM_UNLOCK_COST[s] || 0, grottoLevel: FARM_UNLOCK_GROTTO_LEVEL[s] || 0 }; break; }
    }
    let boostUsed = 0;
    for (const c of careRows || []) { if (Number(c.boosted) === 1) boostUsed++; }
    // T5（0.8.9）：下发新作物表 + 每种的「变卖价 / 服用效果」+ 品阶分层 + 百分比上限（供前端展示与置灰）。
    //   crops 仍为「key → 定义」同形结构（旧客户端零改动兼容，原样可渲染）；
    //   cropList 为带 key 的数组，字段契约对齐 yl_farm089_ext.py（YlxwTFarmT5）：
    //     tier  = '凡'|'灵'|'玄'|'仙'|'神'（单字，直接拼「X品」）；line = 'sell'|'cult'|'mix'|'rare'；
    //     sell  = 变卖价（灵石，纯数）；consExp = 服用修为；
    //     consAttr = [{key:'attack'|'defense'|'maxHp'|'spirit'|'speed', value:n}]；
    //     consPct  = [{key:'critRate'|'dodgeRate'|'lifeLeech', value:0.008}]（**小数比例**，UI ×100 显示）。
    const cropDefs = farmCropDefs();
    const cropList: any[] = [];
    for (const ck of Object.keys(cropDefs)) {
      const cd0 = cropDefs[ck];
      const cc = farmCropConsume(ck, playerObj);
      const legacy = !FARM_CROPS_NEW[ck];
      cropList.push({
        key: ck, name: cd0.name, seed: cd0.seed, minutes: cd0.minutes, stones: cd0.stones, exp: cd0.exp,
        grottoLevel: cd0.grottoLevel || 0,
        tier: legacy ? '' : FARM_CROP_TIERS[FARM_CROPS_NEW[ck].t - 1].slice(0, 1),
        line: legacy ? '' : FARM_CROPS_NEW[ck].k, // 'sell'|'cult'|'mix'|'rare'（客户端 YLXW_FT_LINE 键）
        legacy,
        plantable: !legacy,
        sell: cd0.stones,
        consExp: cc.exp,
        consAttr: cc.attrs.map((x: any) => ({ key: x.key, value: x.add })),
        consPct: cc.pcts.map((x: any) => ({ key: x.key, value: x.pct / 100 })),
      });
    }
    res.json({ now, stones, grottoLevel, slots, crops: cropDefs, cropList, cropTiers: FARM_CROP_TIERS, cropTierLevel: FARM_CROP_TIER_LEVEL, attrCaps: FARM_CROP_ATTR_CAP, unlockCost: FARM_UNLOCK_COST, unlockGrottoLevel: FARM_UNLOCK_GROTTO_LEVEL, readyCount, nextUnlock, boostDaily: { used: boostUsed, cap: farmBoostCap(grottoLevel) } });
  } catch (e: any) {
    console.error('farm status error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

// POST /api/farm/plant {slot, crop:'lingcao'|'lingzhi'|'qianniancan'} — 种植：预检解锁+余额 →
// 占田（部分唯一索引冲突=同田已有活跃作物/并发双种 → 409）→ 扣种子灵石（saveLock 互斥+闭包二次校验）；
// 扣费失败补偿删行可重试（全或无）
app.post('/api/farm/plant', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `farm:plant:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const crop = farmCrop(req.body?.crop);
  if (!crop) return res.status(400).json({ error: '未知作物' });
  const cropKey = asStr(req.body.crop);
  const slot = Math.floor(asNum(req.body?.slot));
  if (!farmSlotOk(slot)) return res.status(400).json({ error: '田位非法' });
  const userId = req.user.id;
  try {
    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    // T5（0.8.9）：旧 5 种已下线，禁止新播（409）；存量已种下的旧田仍可正常收获（兼容）
    if (farmCropNoPlant(cropKey)) {
      return res.status(409).json({ error: '该灵草品种已停止栽种，请改种新灵草（存量旧作物仍可正常收获）', retired: true });
    }
    // R-048：特殊属性（rare）灵草需元婴期（境界序 ≥3）方可栽种；不足 → 409（非 403）
    if (farmCropIsRare(cropKey)) {
      const rIdx = farmRealmIndexOf(saveRow.save_data);
      if (rIdx < FARM_CROP_RARE_REALM) {
        return res.status(409).json({ error: `【${crop.name}】为特殊属性灵草，需元婴期方可栽种（当前境界不足）`, needRealm: FARM_CROP_RARE_REALM, realmIndex: rIdx });
      }
    }
    // T10：高阶作物洞府门槛（409；needGrottoLevel 供客户端置灰提示）
    const gi = farmGrottoInfo(saveRow.save_data);
    if (crop.grottoLevel && gi.level < crop.grottoLevel) {
      return res.status(409).json({ error: `【${crop.name}】需洞府等级 ≥${crop.grottoLevel}，当前洞府 Lv.${gi.level}`, needGrottoLevel: crop.grottoLevel });
    }
    if (slot > 1) {
      const u = await dbGet('SELECT slot FROM farm_unlocks WHERE player_id = ? AND slot = ?', [userId, slot]);
      if (!u) return res.status(409).json({ error: `第 ${slot} 块田尚未开垦`, needUnlock: true });
    }
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < crop.seed) return res.status(409).json({ error: `灵石不足：需种子 ${crop.seed}，现有 ${bal}` });

    const now = Date.now();
    const matureAt = farmMatureAt(now, crop.minutes * (1 - Math.min(0.5, FARM_GROWTH_BONUS_COEF * gi.growthSpeedBonus))); // T10：洞府生长加速 ×0.5 折算进灵田成熟时长（#10，防双吃）
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun(
        'INSERT INTO spirit_farm (player_id, slot, crop, planted_at, mature_at) VALUES (?, ?, ?, ?, ?)',
        [userId, slot, cropKey, now, matureAt]
      );
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '该田已有作物在生长' });
      throw e;
    }

    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Math.max(0, Math.floor(Number(sd.player?.spiritStones) || 0));
      if (b < crop.seed) { short = true; return; }
      sd.player.spiritStones = b - crop.seed;
    });
    if (!paid.ok || short) {
      await dbRun('DELETE FROM spirit_farm WHERE id = ?', [ins.lastID]); // 补偿删行，田位归还可重试
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '种植失败，请重试') });
    }
    // T10：本茬连作衰减与当日虫害随回执下发（提示性字段；衰减/虫害权威口径在收获时复算）
    const mods = await farmHarvestMods(userId, { id: Number(ins.lastID), slot, crop: cropKey, planted_at: now });
    res.json({ ok: true, slot, crop: cropKey, name: crop.name, plantedAt: now, matureAt, seed: crop.seed, streakDecay: mods.streakDecay, pest: mods.pest });
  } catch (e: any) {
    console.error('farm plant error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/farm/harvest {slot, mode:'sell'|'consume'} — T5 双出口收获：到期=全额，提前=减半（玩家自选）；
// 变卖 → 灵石；服用 → 修为 + 属性（2~3 基础属性 / 1~2 百分比属性，百分比有硬上限）。
// 缺省 mode='sell' 保持 0.8.7 单出口逐位兼容。
// 守卫式 harvested=1 单语句防并发双收（双方同发只一方 changes=1）→ 灵石+修为一笔入档
// （失败补偿回退标记可重试；回退若撞上极窄窗口的新种植会失败，只记日志，收益不补——见报告边界）
app.post('/api/farm/harvest', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `farm:harvest:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const slot = Math.floor(asNum(req.body?.slot));
  if (!farmSlotOk(slot)) return res.status(400).json({ error: '田位非法' });
  const userId = req.user.id;
  try {
    const r = await dbGet('SELECT id, crop, planted_at, mature_at FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 0', [userId, slot]);
    if (!r) return res.status(404).json({ error: '该田空空如也' });
    // T5（0.8.9）：出口二选一——非法值 409 明确拒绝（绝不静默降级为变卖，防玩家误吞神品）
    const modeRaw = req.body?.mode;
    if (modeRaw != null && asStr(modeRaw) !== 'sell' && asStr(modeRaw) !== 'consume') {
      return res.status(409).json({ error: '出口非法：仅支持 变卖（sell）/ 服用（consume）' });
    }
    const mode = asStr(modeRaw) === 'consume' ? 'consume' : 'sell';
    // T10：单收/一键收抽公共 farmHarvestOne（倍率/掉玉挂点/邮件口径逐位一致；T5 只钩公共入账点）
    // ★ T5 修复（0.8.9）：T10 单收端点的 SELECT 只取 id/crop/planted_at/mature_at，**漏取 slot**
    //   ⇒ farmHarvestOne 收到的 row.slot 为 undefined ⇒ farmHarvestMods 按 slot 查 farm_daily_care
    //   得到 NaN 匹配不到 ⇒ 照料加成与虫害在**单收路径恒失效**（一键收因 SELECT 带 slot 不受影响）。
    //   端点内已有 `slot` 变量，此处补回（不改 T10 的 SELECT，最小面）。
    const one = await farmHarvestOne(userId, Object.assign({}, r, { slot }), { mode });
    if (!one.ok) return res.status(one.status || 500).json({ error: one.error || '服务器繁忙' });
    res.json({ ok: true, slot: one.slot, crop: one.crop, name: one.name, early: one.early, mode: one.mode, stones: one.stones, exp: one.exp, attrs: one.attrs || [], pcts: one.pcts || [], matureAt: one.matureAt, eventMults: one.eventMults });
  } catch (e: any) {
    console.error('farm harvest error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/farm/unlock {slot:2|3} — 开垦第 2/3 块田（灵石 2000/8000，永久有效；slot 1 免费无需调用）；
// farm_unlocks 主键幂等：INSERT OR IGNORE 先占位（已开垦 changes=0 → 409 不重复扣费）→ 扣费失败补偿删行
app.post('/api/farm/unlock', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `farm:unlock:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const slot = Math.floor(asNum(req.body?.slot));
  if (!farmSlotOk(slot)) return res.status(400).json({ error: '田位非法' });
  const cost = FARM_UNLOCK_COST[slot];
  if (!cost) return res.status(409).json({ error: '首块田地免费可用，无需开垦' });
  const userId = req.user.id;
  try {
    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    // T10：slot 4/5/6 洞府等级门槛（409 需洞府等级 X；E6 契约；门槛先于灵石校验，先告知缺什么）
    const gu = farmGrottoInfo(saveRow.save_data);
    const needLevel = FARM_UNLOCK_GROTTO_LEVEL[slot] || 0;
    if (needLevel > 0 && gu.level < needLevel) {
      return res.status(409).json({ error: `第 ${slot} 块田需洞府等级 ≥${needLevel}，当前洞府 Lv.${gu.level}`, needGrottoLevel: needLevel });
    }
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < cost) return res.status(409).json({ error: `灵石不足：需 ${cost}，现有 ${bal}` });
    const ins = await dbRun('INSERT OR IGNORE INTO farm_unlocks (player_id, slot) VALUES (?, ?)', [userId, slot]);
    if (!ins.changes) return res.status(409).json({ error: '该田已开垦' });
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Math.max(0, Math.floor(Number(sd.player?.spiritStones) || 0));
      if (b < cost) { short = true; return; }
      sd.player.spiritStones = b - cost;
    });
    if (!paid.ok || short) {
      await dbRun('DELETE FROM farm_unlocks WHERE player_id = ? AND slot = ?', [userId, slot]); // 补偿删行可重试
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '开垦失败，请重试') });
    }
    res.json({ ok: true, slot, cost });
  } catch (e: any) {
    console.error('farm unlock error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// T10（0.8.7）：公共原语与三新端点（boost 催熟 / tend 照料 / harvest/all 一键收取）
// 动账原语零新增：dbGet/dbAll/dbRun/insertMail/bjDate 均为既有 hoisted 函数声明；
// 扣费端点统一「占位 → 守卫推进 → 扣款 → 失败补偿」，拒绝码只用 400/409（绝不 403）。
// ─────────────────────────────────────────────────────────

// T10：从 saves.save_data 读洞府等级与生长加速（读法与 status/plant 现有 JSON.parse 同款；解析失败按 0 处理）
function farmGrottoInfo(saveDataJson: string | null | undefined): { level: number; growthSpeedBonus: number } {
  try {
    const g = JSON.parse(saveDataJson || '{}')?.player?.grotto || {};
    return {
      level: Math.min(10, Math.max(0, Math.floor(Number(g.level) || 0))),
      growthSpeedBonus: Math.min(0.5, Math.max(0, Number(g.growthSpeedBonus) || 0)),
    };
  } catch { return { level: 0, growthSpeedBonus: 0 }; }
}

// T5：照料日计次上限（每 2 小时 1 次 ⇒ 单田每日至多 12 次）
const FARM_TEND_COUNT = 12;
// ★ R-019①（farm2 环）：照料冷却 2 小时（T5 §7-Q3「每 2 小时 1 次」）。
//   只作频率闸门，不参与任何收益公式 ⇒ 满配 ×1.21 经济红线零漂移。
const FARM_TEND_CD_MS = 2 * 60 * 60 * 1000;

// T10/T5：收获/种植时的产出修正（洞府加成/照料/连作衰减/虫害）。
// 读存档洞府等级 + 当日 farm_daily_care 行 + spirit_farm 历史行推导连作；全部只读，无副作用。
// ★ 照料口径（T5 §7-Q3）：每次 +2%、单田当日累计封顶 +10% ⇒ 满配乘区仍是 ×1.21，红线结论不变。
async function farmHarvestMods(userId: number, row: { id?: number; slot: number; crop: string; planted_at: number }): Promise<{ grottoBonus: number; tendBonus: number; streakDecay: number; pest: boolean }> {
  const slot = Number(row.slot);
  const today = bjDate(Date.now());
  const [saveRow, careRow, histRows] = await Promise.all([
    dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
    dbGet('SELECT tended, tend_count FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]),
    row.id
      ? dbAll('SELECT crop FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 1 AND id < ? ORDER BY id DESC LIMIT 2', [userId, slot, Number(row.id)])
      : Promise.resolve([] as any[]),
  ]);
  const gi = farmGrottoInfo(saveRow ? saveRow.save_data : null);
  const tended = !!careRow && Number(careRow.tended) === 1;
  // ★ T5 修复（0.8.9）：tendBonus 按**当日实际照料次数**算（tend_count），不再恒为满配常量。
  //   病根：旧实现 `FARM_TEND_COUNT * FARM_TEND_PER` = 12 × 0.02 = 0.10 是编译期常量 ⇒
  //   照料 0 次与 1 次产出完全一样，照料玩法无收益、经济恒处满配。
  //   存量行（升级前 tended=1 但无计数列）退回「至少 1 次」以保底不为 0。
  const tendCount = Math.max(Number(careRow?.tend_count) || 0, tended ? 1 : 0);
  let streak = 0;
  for (const hr of (histRows || [])) { if (String(hr.crop) === String(row.crop)) streak++; else break; }
  const pest = !tended && farmPestToday(userId, slot, String(row.crop), Number(row.planted_at), today);
  return {
    grottoBonus: farmGrottoBonusOf(gi.level),
    tendBonus: Math.min(FARM_TEND_CAP, tendCount * FARM_TEND_PER), // T5：照料按当日实际计次累计（每次 +2%，单田当日封顶 +10%）
    streakDecay: farmStreakDecayOf(streak),
    pest,
  };
}

// T10：单收/一键收公共收获原语（内部顺序与 0.8.6 单收逐字一致：
// mods→gainBase→Y21 活动倍率→Y6B 师徒加成→守卫式收获→入账→失败回退→回执邮件）。
// opts.mail=false 时不发单行邮件（harvest/all 用，改发一封汇总邮件），其余行为不变。
// ★ T5（0.8.9）双出口：mode='sell'（变卖 → 灵石）/ 'consume'（服用 → 修为 + 属性）。
//   缺省 mode='sell' ⇒ 0.8.7 单收/一键收调用点逐位兼容（不传 mode 行为不变）。
//   ★ 回滚三段式逐字保留：守卫式 harvested=1 → credited 标志 → hit.ok 失败回退 harvested=0。
//   consume 的百分比属性有硬上限（FARM_CROP_ATTR_CAP，灵田服用累计口径，独立于装备/称号）。
//   ⚠ 百分比属性独立于修为独立入账：入账闭包内不做“上限后再回退修为”的二次写，
//     避免「一次收获拆成两笔存档事务」引入新的部分成功态。
async function farmHarvestOne(userId: number, row: any, opts?: { mail?: boolean; mode?: string }): Promise<{ ok: boolean; status?: number; error?: string; slot?: number; crop?: string; name?: string; early?: boolean; stones?: number; exp?: number; matureAt?: number; eventMults?: { exp: number; stones: number }; mode?: string; attrs?: Array<{ key: string; label: string; add: number }>; pcts?: Array<{ key: string; label: string; pct: number; cap: number; capped: boolean }> }> {
  const def = farmCrop(String(row.crop));
  if (!def) return { ok: false, status: 500, error: '作物数据异常' };
  const mode = opts?.mode === 'consume' ? 'consume' : 'sell'; // ★ 缺省 sell = 旧口径
  const now = Date.now();
  const matureAt = Number(row.mature_at);
  const early = !farmIsReady(matureAt, now);
  const mods = await farmHarvestMods(userId, { id: Number(row.id), slot: Number(row.slot), crop: String(row.crop), planted_at: Number(row.planted_at) });
  const gainBase = farmYield(def, early, mods);
  // Y21：活动倍率（收获结算自动应用；引擎读取失败按 ×1 保底，不阻塞收获）
  const evMult = await resolveEventMults(now).catch(() => ({ events: [] as any[], expMult: 1, stonesMult: 1 }));
  // Y6B：师徒加成/出师增益（读取失败 ×1 保底，不阻塞收获）
  const mnG = await resolveMentorGains(userId, now).catch(() => ({ expMult: 1, stonesMult: 1 }));
  const gain = { stones: actApplyGain(gainBase.stones, evMult.stonesMult * mnG.stonesMult), exp: actApplyGain(gainBase.exp, evMult.expMult * mnG.expMult) };
  // T5：服用出口效果（纯函数，只读；含上限触顶标记）。变卖出口不消耗属性。
  const cons = mode === 'consume' ? farmCropConsume(String(row.crop)) : null;
  const claim = await dbRun('UPDATE spirit_farm SET harvested = 1 WHERE id = ? AND player_id = ? AND harvested = 0', [Number(row.id), userId]);
  if (!claim.changes) return { ok: false, status: 409, error: '该田已收获' }; // 并发双击只一方生效
  const credit: { stones: number; exp: number; attrs: Array<{ key: string; label: string; add: number }>; pcts: Array<{ key: string; label: string; pct: number; cap: number; capped: boolean }> } = {
    stones: mode === 'sell' ? gain.stones : 0,
    exp: mode === 'consume' ? gain.exp : 0,
    attrs: mode === 'consume' && cons ? cons.attrs.slice() : [],
    pcts: mode === 'consume' && cons ? cons.pcts.slice() : [],
  };
  // ★ T5 修复（0.8.9）：**实际入账修为** = creditedExp。变卖出口只有「旧种兼容区」同时给修为
  //   （见下方入账闭包 isLegacyCrop 分支），20 新品纯卖钱草给 0；服用出口给 credit.exp。
  //   病根：旧邮件按 `gain.exp` 写「修为 +N（已入账）」，但新品变卖实际未加 ⇒ 谎报；回执又写 credit.exp
  //   （旧种变卖时亦为 0）⇒ 邮件/回执/实际入账三处口径不一致。现统一以 creditedExp 为准。
  const creditedExp = mode === 'consume' ? credit.exp : (isLegacyCrop(String(row.crop)) ? gain.exp : 0);
  let credited = false;
  const hit = await updatePlayerSave(userId, (sd: any) => {
    if (!sd.player || typeof sd.player !== 'object') return;
    if (mode === 'sell') {
      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + credit.stones;
      // T5 变卖口径：旧作物（兼容区）按 0.8.7 原口径**同时**给修为；新品（4 产品线）纯卖钱草只给灵石
      if (isLegacyCrop(String(row.crop))) sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + gain.exp;
    } else {
      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + credit.exp;
      for (const a of credit.attrs) sd.player[a.key] = Math.max(0, Math.floor(Number(sd.player[a.key]) || 0)) + a.add;
      // 百分比属性：逐项按硬上限封顶（上限按灵田服用累计字段实算；触顶项不写）。
      // ★ 单位：pc.pct / pc.cap 均为**百分点**（如 pct=1.8, cap=8）；存档存**小数比例** ⇒ 全程在百分点上算，末尾 ÷100 落盘。
      for (const pc of credit.pcts) {
        if (pc.capped) continue;
        const curPct = Math.max(0, Number(sd.player[pc.key]) || 0) * 100;
        const nextPct = pc.cap > 0 ? Math.min(pc.cap, curPct + pc.pct) : curPct + pc.pct;
        sd.player[pc.key] = Math.round(nextPct * 100) / 10000; // 百分點 → 小数比例，保留 4 位
        pc.capped = pc.cap > 0 && nextPct >= pc.cap - 1e-9;
      }
    }
    credited = true;
  });
  if (!hit.ok || !credited) {
    // 补偿：回退收获标记（活跃行已清零，恢复 harvested=0 必不违反部分唯一索引；极窄竞态见函数头注）
    await dbRun('UPDATE spirit_farm SET harvested = 0 WHERE id = ?', [Number(row.id)]).catch((e: any) => console.error('farm harvest revert error:', e?.message || e));
    return { ok: false, status: hit.error === 'No save found' ? 404 : 500, error: hit.error === 'No save found' ? '请先进游戏创建角色' : '入账失败，请重试' };
  }
  // [act087] C 灵玉阁掉玉挂点（farmHarvestOne 公共入账点：单收/一键收口径自动一致；409 落败方不掉玉）
  if (gain.stones > 0) actDropTokens(userId, gain.stones, now).catch((e: any) => console.error('act drop tokens (farm) error:', e?.message || e));

  if (opts?.mail !== false) {
    const lines = mode === 'sell'
      ? `· 灵石 +${credit.stones}（已入账）` + (creditedExp > 0 ? `\n· 修为 +${creditedExp}（已入账）` : `\n· 修为 +0（本品种变卖不产修为）`)
      : `· 修为 +${credit.exp}（已入账）\n` + credit.attrs.map((a: any) => `· ${a.label} +${a.add}（永久生效）`).join('\n')
        + (credit.pcts.length ? '\n' + credit.pcts.map((p: any) => `· ${p.label} ${p.capped ? '已达上限（未增加）' : '+' + p.pct + '%'}`).join('\n') : '');
    insertMail(userId, '灵田丰收',
      `洞府灵田，「${def.name}」${early ? '提前起收（收益减半）' : '应时而收'}！\n\n· 出口：${mode === 'sell' ? '变卖' : '服用'}\n${lines}\n\n田地已翻新，随时可播下一茬。`,
      'system', 0).catch((e: any) => console.error('farm harvest mail error:', e?.message || e));
  }
  return { ok: true, slot: Number(row.slot), crop: String(row.crop), name: def.name, early, stones: credit.stones, exp: creditedExp, matureAt, mode, attrs: credit.attrs, pcts: credit.pcts, eventMults: { exp: evMult.expMult, stones: evMult.stonesMult } };
}

// T5：旧作物判定（兼容区 5 种；供上述变卖口径分流用）
function isLegacyCrop(key: string): boolean {
  return key === 'lingcao' || key === 'lingzhi' || key === 'qianniancan' || key === 'taixuguo' || key === 'zaohuaqinglian';
}

// POST /api/farm/boost {slot} — T10 催熟：立即成熟，灵石计费（公式同构洞府加速 Br，常量独立）。
// 每田每日 1 次 + 每日总次数 = farmBoostCap(洞府等级)。三段式：
//   ①farm_daily_care 单语句原子占位（ON CONFLICT DO UPDATE SET boosted=1 WHERE boosted=0，
//     changes=0 → 409 今日该田已催熟）+ 占位后总次数复核（并发双开不同田双双落闸=宁可错拒不可超扣）
//   ②守卫推进 mature_at（changes=0 → 409 已成熟/并发已收，补偿删 care 行）
//   ③updatePlayerSave 扣费（short → 回滚 mature_at + 删 care 行，可重试）
app.post('/api/farm/boost', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `farm:boost:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const slot = Math.floor(asNum(req.body?.slot));
  if (!farmSlotOk(slot)) return res.status(400).json({ error: '田位非法' });
  const userId = req.user.id;
  try {
    const r = await dbGet('SELECT id, crop, planted_at, mature_at FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 0', [userId, slot]);
    if (!r) return res.status(409).json({ error: '该田空空如也，无需催熟' });
    const now = Date.now();
    const matureAt = Number(r.mature_at);
    if (farmIsReady(matureAt, now)) return res.status(409).json({ error: '该田已成熟，无需催熟' });
    const def = farmCrop(String(r.crop));
    if (!def) return res.status(500).json({ error: '作物数据异常' });
    const cost = farmBoostCost(Math.max(0, matureAt - now));
    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    const gb = farmGrottoInfo(saveRow.save_data);
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < cost) return res.status(409).json({ error: `灵石不足：催熟需 ${cost}，现有 ${bal}` });
    const today = bjDate(now);
    const capMsg = `今日催熟总次数已尽（${farmBoostCap(gb.level)} 次/日，随洞府等级提升）`;
    const preCnt = await dbGet('SELECT COUNT(*) AS c FROM farm_daily_care WHERE player_id = ? AND date = ? AND boosted = 1', [userId, today]);
    if (Number(preCnt?.c) >= farmBoostCap(gb.level)) return res.status(409).json({ error: capMsg });
    // ①占位：同田每日 1 次（原子闸门）
    const gate = await dbRun(
      'INSERT INTO farm_daily_care (player_id, slot, date, tended, boosted) VALUES (?, ?, ?, 0, 1) ' +
      'ON CONFLICT(player_id, slot, date) DO UPDATE SET boosted = 1 WHERE boosted = 0',
      [userId, slot, today]
    );
    if (!gate.changes) return res.status(409).json({ error: '该田今日已催熟' });
    // 占位后复核总次数
    const cnt = await dbGet('SELECT COUNT(*) AS c FROM farm_daily_care WHERE player_id = ? AND date = ? AND boosted = 1', [userId, today]);
    if (Number(cnt?.c) > farmBoostCap(gb.level)) {
      await dbRun('DELETE FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]).catch(() => {});
      return res.status(409).json({ error: capMsg });
    }
    // ②守卫推进 mature_at（立即成熟）
    const matureNow = Date.now();
    const upd = await dbRun('UPDATE spirit_farm SET mature_at = ? WHERE id = ? AND player_id = ? AND harvested = 0 AND mature_at > ?', [matureNow, Number(r.id), userId, matureNow]);
    if (!upd.changes) {
      await dbRun('DELETE FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]).catch(() => {});
      return res.status(409).json({ error: '该田已成熟或已收获，无需催熟' });
    }
    // ③扣费（锁内二次校验；失败回滚 mature_at + 删 care 行）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Math.max(0, Math.floor(Number(sd.player?.spiritStones) || 0));
      if (b < cost) { short = true; return; }
      sd.player.spiritStones = b - cost;
    });
    if (!paid.ok || short) {
      await dbRun('UPDATE spirit_farm SET mature_at = ? WHERE id = ?', [matureAt, Number(r.id)]).catch((e: any) => console.error('farm boost revert error:', e?.message || e));
      await dbRun('DELETE FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]).catch(() => {});
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '催熟失败，请重试') });
    }
    res.json({ ok: true, slot, matureAt: matureNow, cost, message: `催熟完成，「${def.name}」已立即成熟，消耗 ${cost} 灵石` });
  } catch (e: any) {
    console.error('farm boost error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/farm/tend {slot} — T5 照料（浇灌+除虫二合一，免费）：清当日虫害 + 该田当日累计收获加成。
// ★ T5（0.8.9）item4 口径（策划 Q3(a)）：每次 +2%、单田当日累计封顶 +10%（总收益同 0.8.7）。
//   ★ 修复（0.8.9）：照料改**计次**（每次 +1，封顶 FARM_TEND_COUNT 次/日），tendBonus 按实际次数生效。
// farm_daily_care 单语句原子占位（DO UPDATE SET tended=1 WHERE tended=0，changes=0 → 409 今日已照料）
app.post('/api/farm/tend', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `farm:tend:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const slot = Math.floor(asNum(req.body?.slot));
  if (!farmSlotOk(slot)) return res.status(400).json({ error: '田位非法' });
  const userId = req.user.id;
  try {
    const r = await dbGet('SELECT id FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 0', [userId, slot]);
    if (!r) return res.status(409).json({ error: '该田空空如也，无需照料' });
    const nowMs = Date.now();
    const today = bjDate(nowMs);
    // ★ R-019①（farm2 环）：2 小时照料冷却闸门（T5 §7-Q3「每 2 小时 1 次」）。
    //   读今日该田最近一次照料时刻；未到冷却直接 409（业务拒绝用 409，**绝不 403**）。
    const cdRow = await dbGet('SELECT last_tend_at FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]);
    const lastTendAt = Number(cdRow?.last_tend_at) || 0;
    if (lastTendAt > 0) {
      const readyAt = lastTendAt + FARM_TEND_CD_MS;
      const leftMs = readyAt - nowMs;
      if (leftMs > 0) {
        return res.status(409).json({
          error: `照料冷却中：还需 ${Math.ceil(leftMs / 60000)} 分钟（每 2 小时可照料 1 次）`,
          cooldownMs: leftMs, tendReadyAt: readyAt, tendCdMs: FARM_TEND_CD_MS,
        });
      }
    }
    // ★ T5 修复（0.8.9）：计次闸门——每次 +1（封顶 FARM_TEND_COUNT 次/日），取代原布尔「每日 1 次」。
    //   tend_count 由 db.serialize 内的幂等 safeAddColumn 迁移保证存在；tended 仍置 1（=今日照料过）。
    const gate = await dbRun(
      'INSERT INTO farm_daily_care (player_id, slot, date, tended, boosted, tend_count, last_tend_at) VALUES (?, ?, ?, 1, 0, 1, ?) ' +
      'ON CONFLICT(player_id, slot, date) DO UPDATE SET tended = 1, tend_count = tend_count + 1, last_tend_at = ? WHERE tend_count < ?',
      [userId, slot, today, nowMs, nowMs, FARM_TEND_COUNT]
    );
    if (!gate.changes) return res.status(409).json({ error: '该田今日照料次数已达上限' });
    const cntRow = await dbGet('SELECT tend_count FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]);
    const tendCount = Math.max(1, Number(cntRow?.tend_count) || 1);
    const bonusPct = Math.round(Math.min(FARM_TEND_CAP, tendCount * FARM_TEND_PER) * 100);
    res.json({ ok: true, slot, tendCount, tendBonusPct: bonusPct, tendPerPct: Math.round(FARM_TEND_PER * 100), tendCapPct: Math.round(FARM_TEND_CAP * 100), message: `照料完成（今日第 ${tendCount} 次），本块田今日收获 +${bonusPct}%（每次 +${Math.round(FARM_TEND_PER * 100)}%，封顶 +${Math.round(FARM_TEND_CAP * 100)}%，虫害已清除）` });
  } catch (e: any) {
    console.error('farm tend error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/farm/harvest/all — T10 一键收取全部成熟田：逐行复用 farmHarvestOne（守卫式逐行，
// 单行失败不阻塞其余行），聚合并只发一封汇总邮件；无成熟田 = 空数组 200。
// 与单收同倍率/同掉玉挂点（T5 挂点零漂移）；GET status 保持只读，自动收取由客户端触发 POST。
app.post('/api/farm/harvest/all', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `farm:harvestall:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const rows = await dbAll('SELECT id, slot, crop, planted_at, mature_at FROM spirit_farm WHERE player_id = ? AND harvested = 0 LIMIT ?', [userId, FARM_SLOTS]);
    const now = Date.now();
    const ready = (rows || []).filter((rw: any) => farmIsReady(Number(rw.mature_at), now));
    const harvested: any[] = [];
    let totalStones = 0, totalExp = 0;
    const mailLines: string[] = [];
    for (const rw of ready) {
      try {
        const one = await farmHarvestOne(userId, rw, { mail: false, mode: 'sell' }); // T5：一键收恒走变卖（与 0.8.7 单出口口径一致，不掉修为）
        if (one.ok) {
          harvested.push({ slot: one.slot, crop: one.crop, name: one.name, stones: one.stones, exp: one.exp, early: one.early });
          totalStones += Number(one.stones) || 0;
          totalExp += Number(one.exp) || 0;
          mailLines.push(`· 第 ${one.slot} 田「${one.name}」：灵石 +${one.stones}，修为 +${one.exp}${one.early ? '（提前起收，收益减半）' : ''}`);
        }
      } catch (e: any) {
        console.error('farm harvest all row error:', e?.message || e); // 单行失败不阻塞其余行
      }
    }
    if (harvested.length > 0) {
      insertMail(userId, '灵田丰收（一键收取）',
        `洞府灵田一键收取 ${harvested.length} 块成熟田！\n\n${mailLines.join('\n')}\n\n· 合计灵石 +${totalStones}（已入账）\n· 合计修为 +${totalExp}（已入账）\n\n空田可随时播下一茬。`,
        'system', 0).catch((e: any) => console.error('farm harvest all mail error:', e?.message || e));
    }
    res.json({ ok: true, harvested, totalStones, totalExp, message: harvested.length > 0 ? `一键收取 ${harvested.length} 块田：灵石 +${totalStones.toLocaleString()}，修为 +${totalExp.toLocaleString()}` : '暂无成熟田可收' });
  } catch (e: any) {
    console.error('farm harvest all error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// WUDAO（R-GAME3）悟道 API（伴生页 /yl/apps/wudao/）：十系悟道（血/剑/体/法/锋/影/甲/噬/禅/丰）各 1..10 级。
// 心得来源两条腿：① 挂机 roll（POST /api/save 打坐时长差值埋点，每分钟 8% → +10 exp 随机系）；
// ② 手动顿悟（灵石 500 → +100 exp）。攻/防/血/暴击被动加成随系等级达标解锁（Lv3 起）——
// 客户端权威架构下实际战斗结算在客户端，服务端出权威数值+伴生页展示（与称号 attr_json 同边界）。
// exp 入账=单语句原子 upsert（wudao 表 PK 幂等，无读改写竞态）；扣灵石走 updatePlayerSave（锁内二次校验）。
// ─────────────────────────────────────────────────────────

// ── [r101wudao] R-091 祖父条款：阵道/御道定位变更（攻击/气血 → 修炼速度/资源产出）一次性灵石补偿 ──
//   规则：按两条道「改前已投入 exp」× 50 灵石/exp（= 历史手动顿悟等价 5000/100）一次性返还，
//   走 insertMail（玩家在邮件里领取）。幂等键 = activity_config['r091_wudao_respec:<uid>']，
//   首次触达悟道面（GET/POST）即结算一次；**先占键后发信** ⇒ 至多一次（绝不重复发放）。
//   已练等级/exp 原样保留（升级曲线未动），本条仅补偿「加成语义变更」的定位损失。
const WUDAO_RESPEC_REFUND_PER_EXP = 50;
async function wudaoRespecCompensateOnce(userId: number): Promise<void> {
  try {
    const key = 'r091_wudao_respec:' + userId;
    const seen = await dbGet('SELECT value FROM activity_config WHERE key = ?', [key]).catch(() => null);
    if (seen) return;
    // 先占键（INSERT OR IGNORE，changes=0 ⇒ 已被并发/前次占位），保证至多一次发放
    const claim = await dbRun("INSERT OR IGNORE INTO activity_config (key, value) VALUES (?, '1')", [key]).catch(() => null);
    if (!claim || Number(claim.changes) <= 0) return;
    const rows = await dbAll('SELECT dao_type, exp FROM wudao WHERE player_id = ? AND dao_type IN (?, ?)', [userId, 'array', 'tame']);
    let expSum = 0;
    for (const r of rows || []) expSum += Math.max(0, Math.floor(Number(r.exp) || 0));
    const refund = Math.floor(expSum * WUDAO_RESPEC_REFUND_PER_EXP);
    if (refund > 0) {
      await insertMail(userId, '悟道体系重规划补偿',
        `阵道/御道定位已重规划（阵道→修炼速度、御道→资源产出）。按你此前投入的 ${expSum} 点道行，一次性返还灵石 ×${refund}。`,
        '天机阁', refund);
    }
  } catch (e: any) {
    console.error('wudao respec compensate error:', e?.message || e);
  }
}

// GET /api/wudao — 十系等级+exp+加成列表+悟道日志+灵石余额（一页全量，不落账）
app.get('/api/wudao', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `wudao:me:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const [rows, saveRow, logRows] = await Promise.all([
      dbAll('SELECT dao_type, exp FROM wudao WHERE player_id = ?', [userId]), // [r110wudao] R-110：原 LIMIT 6 会截断新增四道，改全量（PK(player_id,dao_type) 天然限 10 行）
      dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
      dbAll('SELECT dao_type, exp, source, created_at FROM wudao_log WHERE player_id = ? ORDER BY id DESC LIMIT 20', [userId]),
    ]);
    const expByDao: Record<string, number> = {};
    for (const r of rows || []) expByDao[String(r.dao_type)] = Math.max(0, Math.floor(Number(r.exp) || 0));
    let balance: number | null = null;
    let realmIdx = 0;
    if (saveRow) {
      try {
        const p = JSON.parse(saveRow.save_data)?.player;
        balance = Math.max(0, Math.floor(Number(p?.spiritStones) || 0));
        realmIdx = wudaoRealmIndex(p?.realm);
      } catch { balance = null; }
    }
    await wudaoRespecCompensateOnce(userId); // [r101wudao] 祖父条款：首次触达即一次性补偿（幂等，自吞异常）
    const daos = Object.keys(WUDAO_DAOS).map((k) => {
      const d = WUDAO_DAOS[k];
      const exp = expByDao[k] || 0;
      const level = wudaoLevelFromExp(exp);
      const next = level < WUDAO_MAX_LEVEL ? wudaoExpToReach(level + 1) : null;
      const gateRealm = wudaoDaoGateRealm(k);
      const locked = realmIdx < gateRealm && exp <= 0; // 已投入者祖父放行，不追溯锁死
      return {
        key: k,
        name: d.name,
        stat: d.stat,
        statName: d.statName,
        level,
        exp,
        expToNext: next == null ? 0 : next - exp,
        bonusUnlocked: level >= WUDAO_BONUS_UNLOCK_LEVEL,
        bonusPct: wudaoBonusPct(k, level),
        locked,
        gateRealmIndex: gateRealm,
        gateRealmName: gateRealm > 0 ? WUDAO_REALM_ORDER[gateRealm] : null,
        bonusText: level >= WUDAO_BONUS_UNLOCK_LEVEL
          ? `${d.statName} +${wudaoBonusPct(k, level)}%`
          : `${d.statName}加成（${d.statName} +${d.basePct}%，Lv${WUDAO_BONUS_UNLOCK_LEVEL} 解锁）`,
      };
    });
    res.json({
      now: Date.now(),
      daos,
      maxLevel: WUDAO_MAX_LEVEL,
      bonusUnlockLevel: WUDAO_BONUS_UNLOCK_LEVEL,
      maxExpTotal: WUDAO_MAX_EXP_TOTAL,
      realmIndex: realmIdx,
      insight: { chancePerMinute: WUDAO_INSIGHT_CHANCE, exp: WUDAO_INSIGHT_EXP, capMinutesPerUpload: WUDAO_IDLE_CAP_MINUTES },
      manual: { cost: wudaoManualCost(realmIdx), exp: WUDAO_MANUAL_EXP },
      balance,
      hasSave: !!saveRow,
      log: (logRows || []).map((r: any) => ({
        dao: String(r.dao_type),
        exp: Math.max(0, Math.floor(Number(r.exp) || 0)),
        source: String(r.source) === 'manual' ? 'manual' : 'idle',
        createdAt: r.created_at ?? null,
      })),
    });
  } catch (e: any) {
    console.error('wudao list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/wudao/insight {dao:'sword'|...} — 手动顿悟：扣灵石 500 → 该系 +100 exp（全或无可重试）
// 顺序=先扣灵石（防加成端被白嫖）后加 exp；加 exp 失败补偿退灵石（退款失败仅记日志，不产生复制收益）
app.post('/api/wudao/insight', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `wudao:insight:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const daoKey = asStr(req.body?.dao);
    if (!wudaoDaoOk(daoKey)) return res.status(400).json({ error: '未知的悟道系别' });
    // 预检：角色与灵石余额（并发窗口由 updatePlayerSave 锁内二次校验兜底）
    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    let realmIdx = 0;
    try { const p = JSON.parse(row.save_data)?.player; bal = Math.max(0, Math.floor(Number(p?.spiritStones) || 0)); realmIdx = wudaoRealmIndex(p?.realm); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    await wudaoRespecCompensateOnce(userId); // [r101wudao] 祖父条款：一次性补偿（先于本次加 exp，按改前已投入结算）
    // [r101wudao] R-091 稀有道等阶门槛：阵道/御道按境界逐步开放；已投入(exp>0)者祖父放行，不追溯锁死
    const gateRealm = wudaoDaoGateRealm(daoKey);
    if (gateRealm > 0 && realmIdx < gateRealm) {
      const own: any = await dbGet('SELECT exp FROM wudao WHERE player_id = ? AND dao_type = ?', [userId, daoKey]);
      const ownExp = Math.max(0, Math.floor(Number(own?.exp) || 0));
      if (ownExp <= 0) return res.status(409).json({ error: `此道需 ${WUDAO_REALM_ORDER[gateRealm]} 起方可参悟`, code: 'DAO_LOCKED', gateRealmIndex: gateRealm });
    }
    const cost = wudaoManualCost(realmIdx); // [r101wudao] 灵石价随境界递增
    if (bal < cost) return res.status(409).json({ error: `灵石不足：需 ${cost}，现有 ${bal}` });
    // 1) 扣灵石（saveLock 互斥 + gm_revision++ 促客户端拉新档；锁内余额不足拒绝）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') { short = true; return; }
      const b = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0));
      if (b < cost) { short = true; return; }
      sd.player.spiritStones = b - cost;
    });
    if (!paid.ok || short) {
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '顿悟失败，请重试') });
    }
    // 2) exp 入账 + 日志（原子 upsert）；失败补偿退灵石，本次不作数可重试
    const added = await wudaoAddExp(userId, daoKey, WUDAO_MANUAL_EXP, 'manual');
    if (!added) {
      await updatePlayerSave(userId, (sd: any) => {
        if (!sd.player || typeof sd.player !== 'object') return;
        sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + cost;
      }).catch((e: any) => console.error('wudao insight refund error:', e?.message || e));
      return res.status(500).json({ error: '顿悟入账失败，灵石已退还，请重试' });
    }
    const d = WUDAO_DAOS[daoKey];
    res.json({
      ok: true,
      dao: daoKey,
      daoName: d.name,
      expGain: WUDAO_MANUAL_EXP,
      level: added.level,
      exp: added.exp,
      expToNext: added.level < WUDAO_MAX_LEVEL ? wudaoExpToReach(added.level + 1) - added.exp : 0,
      maxLevel: WUDAO_MAX_LEVEL,
      bonusPct: wudaoBonusPct(daoKey, added.level),
      bonusText: added.level >= WUDAO_BONUS_UNLOCK_LEVEL ? `${d.statName} +${wudaoBonusPct(daoKey, added.level)}%` : null,
      cost,
    });
  } catch (e: any) {
    console.error('wudao insight error:', e?.message || e);
    if (!res.headersSent) res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// Y20 功法系统 API：六部功法（焚天诀/御剑术/不灭体/大衍诀/周天阵/御灵术）各 1..100 级（0.8.7 T3）。
// 修炼即时完成，升到 L 级耗 TIER[floor((L-1)/10)] 灵石（玄品口径），攻/防/血 +1%/级、其余 +0.2%/级——
// 客户端权威架构下实际属性结算在客户端（与称号 attr_json/悟道加成同边界），服务端出权威数值。
// 升级（0.8.7 严格三段式，见 levelup 处注释）：【占位】守卫推进等级位 →【扣款】锁内二次校验扣灵石
// →【补偿】扣款失败守卫回退等级位。同档连点在占位即被拒（零扣费零叠加）。
// ─────────────────────────────────────────────────────────

// GET /api/gongfa — 六部等级+加成列表+灵石余额（一页全量，不落账）
app.get('/api/gongfa', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `gongfa:me:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const [rows, saveRow] = await Promise.all([
      dbAll(
        'SELECT g.key AS key, pg.level AS level, pg.exp AS exp FROM player_gongfa pg JOIN gongfa g ON g.id = pg.gongfa_id WHERE pg.player_id = ? LIMIT 6',
        [userId]
      ),
      dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
    ]);
    const byKey: Record<string, { level: number; exp: number }> = {};
    for (const r of rows || []) byKey[String(r.key)] = { level: Math.max(0, Math.floor(Number(r.level) || 0)), exp: Math.max(0, Math.floor(Number(r.exp) || 0)) };
    let balance: number | null = null;
    if (saveRow) {
      try { balance = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { balance = null; }
    }
    const gongfas = Object.keys(GONGFA_LIST).map((k) => {
      const d = GONGFA_LIST[k];
      const exp = byKey[k]?.exp || 0;
      // 0.8.7：展示等级以 level 列为准（守卫推进维护）；无行=未入门 0 级
      const shown = byKey[k]
        ? Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(byKey[k].level) || 0)))
        : 0;
      const next = shown < GONGFA_MAX_LEVEL ? gongfaCostToReach(shown + 1) : null;
      const stepPct = shown > 0 ? gongfaBonusPct(k, shown) : (GONGFA_MAIN_KEYS[k] ? GONGFA_MAIN_STEP_PCT : GONGFA_MINOR_STEP_PCT);
      return {
        key: k,
        name: d.name,
        stat: d.stat,
        statName: d.statName,
        level: shown,
        exp,
        costNext: next == null ? 0 : next,
        costToNext: next == null ? 0 : next,
        bonusPct: gongfaBonusPct(k, shown),
        bonusText: shown > 0 ? `${d.statName} +${gongfaPctStr(gongfaBonusPct(k, shown))}%` : `${d.statName}加成（修炼后 +${gongfaPctStr(stepPct)}%/级）`,
        maxed: shown >= GONGFA_MAX_LEVEL,
      };
    });
    res.json({
      now: Date.now(),
      gongfas,
      maxLevel: GONGFA_MAX_LEVEL,
      tierCost: GONGFA_TIER_COST,
      gradeMult: GONGFA_GRADE_MULT,
      maxExpTotal: GONGFA_MAX_EXP_TOTAL,
      balance,
      hasSave: !!saveRow,
    });
  } catch (e: any) {
    console.error('gongfa list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/gongfa/levelup {gongfa:'fentian'|...} — 修炼升级（0.8.7 T3 重做：严格三段式 + 连点幂等）。
// 顺序=【占位】守卫推进等级位（WHERE level=旧值；首建 INSERT level=1）→【扣款】saveLock 锁内二次校验
// 扣灵石 →【补偿】扣款失败守卫回退等级位（首建行删行），可重试。
// 同档并发/连点只一方赢占位，落败方**未扣款**直接 409（幂等：同档重复请求零扣费零叠加）；
// 响应丢失后的重试读到新等级按新档计价，属买下一级而非重复扣费。
// 旧序（先扣款后推进→落败退款）的退款失败=玩家白扣且不可逆；占位优先把失败面挪到服务端侧
// （回退失败=白送一级，量级轻且留日志）。
app.post('/api/gongfa/levelup', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `gongfa:levelup:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const key = asStr(req.body?.gongfa);
    if (!gongfaOk(key)) return res.status(400).json({ error: '未知的功法' });
    const g = await dbGet('SELECT id FROM gongfa WHERE key = ?', [key]);
    if (!g) return res.status(500).json({ error: '功法目录缺失' });
    const gid = Number(g.id);
    // 当前等级（level 列=守卫推进维护的权威值；无行=未入门 0 级）
    const row = await dbGet('SELECT level, exp FROM player_gongfa WHERE player_id = ? AND gongfa_id = ?', [userId, gid]);
    const curLevel = Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(row?.level) || 0)));
    if (curLevel >= GONGFA_MAX_LEVEL) return res.status(409).json({ error: '该功法已大成（Lv100），无法再进阶' });
    const cost = gongfaCostToReach(curLevel + 1);
    // 预检：角色与灵石余额（只读快查；权威校验在【扣款】锁内二次进行）
    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < cost) return res.status(409).json({ error: `灵石不足：需 ${cost}，现有 ${bal}` });
    // 1)【占位】守卫推进：WHERE level=旧值（同档并发/连点只一方生效）；无行则首建 L1（PK 冲突=他人已建→占位失败）
    let advanced = false;
    let inserted = false;
    if (row) {
      const up = await dbRun(
        'UPDATE player_gongfa SET level = level + 1, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?',
        [userId, gid, curLevel]
      );
      advanced = up.changes > 0;
    } else {
      try {
        const ins = await dbRun('INSERT INTO player_gongfa (player_id, gongfa_id, level, exp) VALUES (?, ?, 1, 0)', [userId, gid]);
        advanced = ins.changes > 0;
        inserted = advanced;
      } catch (e: any) {
        if (String(e?.message || '').includes('UNIQUE')) advanced = false;
        else throw e;
      }
    }
    if (!advanced) {
      // 并发他手已推进同档：未扣款直接 409（连点幂等；客户端刷新后按新档续买）
      return res.status(409).json({ error: '修炼并发冲突，请刷新后重试' });
    }
    // 2)【扣款】saveLock 互斥 + 锁内余额二次校验；gm_revision++ 促客户端拉新档
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') { short = true; return; }
      const b = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0));
      if (b < cost) { short = true; return; }
      sd.player.spiritStones = b - cost;
    });
    if (!paid.ok || short) {
      // 3)【补偿】扣款失败：守卫回退等级位（本次占位不作数可重试）；首建行直接删行
      const rev = inserted
        ? await dbRun('DELETE FROM player_gongfa WHERE player_id = ? AND gongfa_id = ? AND level = 1', [userId, gid])
        : await dbRun('UPDATE player_gongfa SET level = level - 1, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?', [userId, gid, curLevel + 1]);
      if (!rev.changes) console.error('gongfa levelup revert failed: user=%s gongfa=%s level=%s', userId, key, curLevel + 1);
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '修炼失败，请重试') });
    }
    // 投入入账：exp=累计投入，服务端侧累加（守卫 WHERE level=新值，防并发串档）；失败仅日志（展示面）
    await dbRun(
      'UPDATE player_gongfa SET exp = exp + ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?',
      [cost, userId, gid, curLevel + 1]
    ).catch((e: any) => console.error('gongfa exp update error:', e?.message || e));
    const newLevel = curLevel + 1;
    const d = GONGFA_LIST[key];
    res.json({
      ok: true,
      gongfa: key,
      name: d.name,
      level: newLevel,
      exp: Math.max(0, Math.floor(Number(row?.exp) || 0)) + cost,
      cost,
      spent: cost,
      bonusPct: gongfaBonusPct(key, newLevel),
      bonusText: `${d.statName} +${gongfaPctStr(gongfaBonusPct(key, newLevel))}%`,
      maxed: newLevel >= GONGFA_MAX_LEVEL,
    });
  } catch (e: any) {
    console.error('gongfa levelup error:', e?.message || e);
    if (!res.headersSent) res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// Y21 限时活动框架 API（伴生页 /yl/apps/events/）：events 表 + activity_config 全局开关表驱动，
// admin 经 GM 端点控制；活动期间服务端结算点（离线收益/灵田收获/炼丹出炉）自动应用倍率（同类叠乘、
// 钳 10 上限）；限时 Boss/掉落两类在客户端接管前仅展示+倒计时（架构边界，伴生页注记）。
// 引擎读取：engine_on='0' 一键停发（kill switch）；倍率每次结算请求读一次，同请求内口径一致。
// ─────────────────────────────────────────────────────────

// 活动引擎读取（每结算请求一次）：返回活跃活动行 + 修为/灵石目标倍率（engine 关闭 → 空表 ×1）
async function resolveEventMults(nowMs: number): Promise<{ events: any[]; expMult: number; stonesMult: number }> {
  const cfg = await dbGet("SELECT value FROM activity_config WHERE key = 'engine_on'");
  if (!cfg || String(cfg.value) !== '1') return { events: [], expMult: 1, stonesMult: 1 };
  const rows = await dbAll(
    'SELECT id, type, name, multiplier, start_at, end_at FROM events WHERE enabled = 1 AND start_at <= ? AND end_at > ? LIMIT 20',
    [nowMs, nowMs]
  );
  return { events: rows || [], expMult: actMultiplierFor(rows || [], 'exp', nowMs), stonesMult: actMultiplierFor(rows || [], 'stones', nowMs) };
}

// GET /api/events — 当前活动列表 + 倒计时 + 引擎状态（活跃在前，其余按开始时间）
app.get('/api/events', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `events:me:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  try {
    const now = Date.now();
    const cfg = await dbGet("SELECT value FROM activity_config WHERE key = 'engine_on'");
    const rows = await dbAll('SELECT id, type, name, multiplier, start_at, end_at, enabled FROM events ORDER BY start_at DESC LIMIT 50', []);
    const events = (rows || []).map((r) => {
      const type = String(r.type);
      const def = ACT_TYPES[type];
      const startAt = Number(r.start_at);
      const endAt = Number(r.end_at);
      const active = actIsActive(r, now);
      return {
        id: Number(r.id),
        type,
        typeName: def ? def.name : type,
        target: def ? def.target : 'boss',
        desc: def ? def.desc : '',
        name: String(r.name || '').slice(0, 24),
        multiplier: actClampMultiplier(r.multiplier),
        startAt,
        endAt,
        enabled: Number(r.enabled) === 1,
        active,
        state: active ? 'active' : (now < startAt ? 'upcoming' : 'ended'),
        leftMs: active ? Math.max(0, endAt - now) : 0,
        startsInMs: !active && now < startAt ? Math.max(0, startAt - now) : 0,
      };
    })
      // 活跃在前 → 未开始 → 已结束（同组内新start在前）
      .sort((a, b) => {
        const w = (s: string) => (s === 'active' ? 0 : s === 'upcoming' ? 1 : 2);
        return w(a.state) - w(b.state) || b.startAt - a.startAt;
      });
    res.json({
      now,
      engineOn: String(cfg?.value) === '1',
      types: ACT_TYPES,
      events,
    });
  } catch (e: any) {
    console.error('events list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// GET /api/gm/activity — 活动管理面板数据（引擎开关 + 全部活动 + 类型目录）
app.get('/api/gm/activity', authenticateGM, async (req: any, res: any) => {
  try {
    const cfg = await dbGet("SELECT value FROM activity_config WHERE key = 'engine_on'");
    const rows = await dbAll('SELECT id, type, name, multiplier, start_at, end_at, enabled, created_at FROM events ORDER BY id DESC LIMIT 100', []);
    res.json({ engineOn: String(cfg?.value) === '1', types: ACT_TYPES, multCap: ACT_MULT_CAP, multCfgMax: ACT_MULT_CFG_MAX, events: rows || [] });
  } catch (e: any) {
    console.error('gm activity list error:', e?.message || e);
    res.status(500).json({ error: '查询失败' });
  }
});

// POST /api/gm/activity — 创建/编辑活动（{id?} 有=编辑无=新建；type/multiplier/窗口服务端钳制；
// 建场 enabled=1 即全服江湖志播报一次【活动】）
app.post('/api/gm/activity', authenticateGM, async (req: any, res: any) => {
  try {
    const b = req.body || {};
    const id = Math.floor(Number(b.id)) || 0;
    const type = String(b.type ?? '');
    if (!actTypeOk(type)) return res.status(400).json({ error: '未知活动类型' });
    const multiplier = actClampMultiplier(b.multiplier);
    const name = String(b.name ?? ACT_TYPES[type].name).slice(0, 24).trim() || ACT_TYPES[type].name;
    const startAt = Math.floor(Number(b.startAt));
    const endAt = Math.floor(Number(b.endAt));
    if (!Number.isFinite(startAt) || !Number.isFinite(endAt) || endAt <= startAt) {
      return res.status(400).json({ error: '活动窗口非法（需 endAt > startAt，ms epoch）' });
    }
    const enabled = Number(b.enabled) === 0 ? 0 : 1;
    if (id) {
      const up = await dbRun(
        'UPDATE events SET type = ?, name = ?, multiplier = ?, start_at = ?, end_at = ?, enabled = ? WHERE id = ?',
        [type, name, multiplier, startAt, endAt, enabled, id]
      );
      if (!up.changes) return res.status(404).json({ error: '活动不存在' });
      logGmAction('activity_update', `event:${id}`, { type, name, multiplier, startAt, endAt, enabled });
      if (enabled && actWindowOk(startAt, endAt, Date.now())) {
        logChronicle(null, '天机阁', `【活动】「${name}」开启：${ACT_TYPES[type].desc}，限时进行中！`);
      }
      return res.json({ ok: true, id, updated: true });
    }
    const ins = await dbRun(
      'INSERT INTO events (type, name, multiplier, start_at, end_at, enabled) VALUES (?, ?, ?, ?, ?, ?)',
      [type, name, multiplier, startAt, endAt, enabled]
    );
    logGmAction('activity_create', `event:${ins.lastID}`, { type, name, multiplier, startAt, endAt, enabled });
    if (enabled && actWindowOk(startAt, endAt, Date.now())) {
      logChronicle(null, '天机阁', `【活动】「${name}」开启：${ACT_TYPES[type].desc}，限时进行中！`);
    }
    res.json({ ok: true, id: ins.lastID, created: true });
  } catch (e: any) {
    console.error('gm activity save error:', e?.message || e);
    res.status(500).json({ error: '保存失败' });
  }
});

// POST /api/gm/activity/config {engineOn:0|1} — 引擎全局开关（kill switch：'0'=所有倍率停发，活动仍展示）
app.post('/api/gm/activity/config', authenticateGM, async (req: any, res: any) => {
  try {
    const on = asNum(req.body?.engineOn) === 0 ? '0' : '1';
    await dbRun(
      "INSERT INTO activity_config (key, value) VALUES ('engine_on', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
      [on]
    );
    logGmAction('activity_config', 'engine_on', { engineOn: on });
    // GM global kill switch (activity_config.engine_on): mirror into memory so the timer
    // needs no DB read while the engine is off. This is a hot-reload channel for the GM
    // switch only; it is NOT what keeps Tianjiang Lingyu off by default.
    rainEngineOn = on === '1';
    actEngineOn = on === '1'; // [act087] 结算器共用同一全局开关（内存镜像，settle tick 首行早退）
    res.json({ ok: true, engineOn: on === '1' });
  } catch (e: any) {
    console.error('gm activity config error:', e?.message || e);
    res.status(500).json({ error: '保存失败' });
  }
});
// [v2810] DELETE /api/gm/activity/:id \u2014 \u5220\u9664\u6d3b\u52a8\uff08events \u884c + \u5ba1\u8ba1\uff09\u3002
//   \u7ea7\u8054\u7b56\u7565\uff1a\u53ea\u5220 events \u884c\uff1bactivity_token \u7684 bought:<eventId>:<itemId> \u884c\u3001
//   activity_checkin / activity_rank_settled / activity_rain_state / event_boss \u4e2d\u540c
//   event_id \u7684\u884c\u4fdd\u7559\u4e3a\u5b64\u513f\uff08\u5747\u6309 event_id \u5b9a\u4f4d\uff0c\u6d3b\u52a8\u5220\u540e\u67e5\u8be2\u4e0d\u5230\u5373\u65e0\u5bb3\uff09\u3002
app.delete('/api/gm/activity/:id', authenticateGM, async (req: any, res: any) => {
  const id = asInt(req.params.id);
  if (!Number.isInteger(id) || id <= 0) return res.status(400).json({ error: '\u6d3b\u52a8 id \u975e\u6cd5' });
  try {
    const del = await dbRun('DELETE FROM events WHERE id = ?', [id]);
    if (!del.changes) return res.status(404).json({ error: '\u6d3b\u52a8\u4e0d\u5b58\u5728' });
    logGmAction('activity_delete', `event:${id}`, { id });
    res.json({ ok: true, id });
  } catch (e: any) {
    console.error('gm activity delete error:', e?.message || e);
    res.status(500).json({ error: '\u5220\u9664\u5931\u8d25' });
  }
});


// [raincore-settler] Y21-R rain settler: the only new setInterval in this file.
// When the engine is off the timer callback returns on its FIRST line, before any DB work.
// dbGet/dbAll/dbRun/insertMail/bjDate are hoisted function declarations, safe to call at runtime.
async function rainSettleTick(wallMinutes: number): Promise<void> {
  if (rainSettling) return;
  rainSettling = true;
  try {
    const nowMs = Date.now();
    const ev: any = await dbGet(
      "SELECT id FROM events WHERE type = 'stones2_live' AND enabled = 1 AND start_at <= ? AND end_at > ? LIMIT 1",
      [nowMs, nowMs]
    );
    if (!ev) return;
    const eventId = Math.max(0, Math.floor(Number(ev.id) || 0));
    if (!eventId) return;
    const today = bjDate(nowMs);
    const staleMod = '-' + Math.floor(RAIN_ONLINE_STALE_MS / 60000) + ' minutes';
    const rows: any[] = await dbAll(
      "SELECT s.user_id AS uid, r.realm_index AS ri, COALESCE(d.minutes, 0) AS minutes" +
      " FROM saves s" +
      " LEFT JOIN rankings r ON r.user_id = s.user_id" +
      " LEFT JOIN stats_daily d ON d.player_id = s.user_id AND d.date = ?" +
      " WHERE s.updated_at >= datetime('now', ?)",
      [today, staleMod]
    );
    for (const row of rows || []) {
      try {
        const uid = Math.max(0, Math.floor(Number(row.uid) || 0));
        if (!uid) continue;
        const nowMinutes = Math.max(0, Math.floor(Number(row.minutes) || 0));
        const st: any = await dbGet(
          'SELECT last_minutes, accrued_minutes, settled_minutes FROM activity_rain_state WHERE player_id = ? AND event_id = ? AND date = ?',
          [uid, eventId, today]
        );
        if (!st) {
          // First sight of this player/date: baseline only, never pay for the whole day at once.
          await dbRun(
            'INSERT OR IGNORE INTO activity_rain_state (player_id, event_id, date, last_minutes, accrued_minutes, settled_minutes) VALUES (?, ?, ?, ?, 0, 0)',
            [uid, eventId, today, nowMinutes]
          );
          continue;
        }
        const delta = rainDeltaMinutes(st.last_minutes, nowMinutes, wallMinutes);
        const accrued = Math.max(0, Math.floor(Number(st.accrued_minutes) || 0)) + delta;
        const settled = Math.max(0, Math.floor(Number(st.settled_minutes) || 0));
        const hours = rainPayableHours(accrued, settled);
        if (hours <= 0) {
          await dbRun(
            'UPDATE activity_rain_state SET last_minutes = ?, accrued_minutes = ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND event_id = ? AND date = ?',
            [nowMinutes, accrued, uid, eventId, today]
          );
          continue;
        }
        const payMinutes = hours * RAIN_SETTLE_MIN_MINUTES;
        // Guarded single statement: atomically reserve this payout (concurrency/re-entry safe, daily cap enforced).
        const claim = await dbRun(
          'UPDATE activity_rain_state SET last_minutes = ?, accrued_minutes = accrued_minutes + ? - ?, settled_minutes = settled_minutes + ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND event_id = ? AND date = ? AND settled_minutes + ? <= ?',
          [nowMinutes, delta, payMinutes, payMinutes, uid, eventId, today, payMinutes, RAIN_DAILY_CAP_MINUTES]
        );
        if (!claim.changes) continue;
        const bonus = rainBonusStones(hours, row.ri);
        const title = '\u5929\u964d\u7075\u96e8 \u00b7 \u5728\u7ebf\u4fee\u884c\u56de\u9988';
        const body = '\u7075\u96e8\u6da6\u6cfd\uff0c\u9053\u53cb\u5728\u7ebf\u4fee\u884c ' + hours + ' \u5c0f\u65f6\uff0c\u5929\u5730\u7075\u6c14\u5316\u4f5c\u7075\u77f3\u76f8\u8d60\uff1a\n\n\u00b7 \u7075\u77f3 +' + bonus + '\uff08\u8bf7\u70b9\u51fb\u4e0b\u65b9\u9886\u53d6\uff09\n\n\uff08\u6d3b\u52a8\u671f\u95f4\u5728\u7ebf\u6bcf\u6ee1 1 \u5c0f\u65f6\u7ed3\u7b97\u4e00\u6b21\uff0c\u5355\u65e5\u4e0a\u9650 8 \u5c0f\u65f6\uff09';
        try {
          await insertMail(uid, title, body, 'system', bonus, { noChronicle: true });
        } catch (mailErr: any) {
          // Compensating rollback: mail failed, release the reservation so the player retries next tick.
          await dbRun(
            'UPDATE activity_rain_state SET accrued_minutes = accrued_minutes + ?, settled_minutes = settled_minutes - ? WHERE player_id = ? AND event_id = ? AND date = ?',
            [payMinutes, payMinutes, uid, eventId, today]
          ).catch(() => {});
          console.error('rain mail error:', mailErr?.message || mailErr);
        }
      } catch (perUserErr: any) {
        console.error('rain settle per-user error:', perUserErr?.message || perUserErr);
      }
    }
  } catch (e: any) {
    console.error('rain settle tick error:', e?.message || e);
  } finally {
    rainSettling = false;
  }
}
setInterval(() => {
  if (!rainEngineOn) return; // engine off: first-line early return, zero DB work
  const nowMs = Date.now();
  const wallMinutes = rainLastTickMs > 0 ? (nowMs - rainLastTickMs) / 60000 : RAIN_TICK_MS / 60000;
  rainLastTickMs = nowMs;
  rainSettleTick(wallMinutes).catch((e: any) => console.error('rain tick error:', e?.message || e));
}, RAIN_TICK_MS).unref();
// Boot: mirror engine_on into memory so the timer needs no DB read while the engine is off.
dbGet("SELECT value FROM activity_config WHERE key = 'engine_on'")
  .then((r: any) => { rainEngineOn = String(r && r.value) === '1'; })
  .catch(() => {});

// ─────────────────────────────────────────────────────────
// [act087] 0.8.7 T5 限时活动 ×4：仙途冲榜 rank_battle / 仙缘七日礼 checkin_fest /
//   灵玉阁 token_shop / 万妖巢穴 boss_raid。活动实例复用 events 表（GM 零新增）。
//   纪律：业务拒绝一律 400/409（Xc() 把 403 当会话失效）；扣费三段式（占位→扣款→补偿）；
//   kill switch 双层（activity_config.engine_on 全局 + events.enabled 逐场）；
//   「每日」一律 utcDateStr()（fun_daily/worldboss 现网主口径）；冲榜窗口聚合按 stats_daily
//   的 bjDate 键换算区间；EV 红线见补丁头注与本文件顶部注释。
// ─────────────────────────────────────────────────────────
let actEngineOn = false;   // engine_on 内存镜像（GM config / boot 各镜像一次；结算 tick 首行早退）
let actSettling = false;   // 结算器重入保护（单进程假设，同 rainSettling）
const ACT_TICK_MS = 10 * 60 * 1000;                // 结算周期（同 RAIN_TICK_MS）
const ACT_RANK_MIN_MINUTES = 60;                   // A 参与线：窗口 SUM(minutes) ≥ 60 才计奖
const ACT_CHECKIN_DAYS = 7;                        // B 每期 7 天
const ACT_TOKEN_KEY = 'lingyu';                    // C 代币键（余额跨期保留，不按期清零）
const ACT_TOKEN_RATE_PER_10K = 50;                  // C 掉玉率 r=50 玉/万灵石结算 [r055jade] R-055：2→50（0.02%→0.5%，单笔 200 石起即掉 1 玉）
const ACT_TOKEN_DAILY_CAP = 300;                   // C 掉玉日上限（=6 万灵石结算量/日）[r055jade] R-055：原 150 万口径随掉率×25 同比例收紧
const ACT_SHOP_ITEMS: Array<{ id: string; name: string; price: number; limit: number; hours?: number; titleSource?: string }> = [
  { id: 'bag_s',      name: '灵石袋·小',     price: 100,  limit: 20, hours: 1 },
  { id: 'bag_m',      name: '灵石袋·中',     price: 300,  limit: 10, hours: 4 },
  { id: 'bag_l',      name: '灵石袋·大',     price: 800,  limit: 5,  hours: 12 },
  { id: 'title_jade', name: '称号·灵玉仙客', price: 1000, limit: 1,  titleSource: 'act087_jade' },
]; // 兑换率恒定零随机（C2，零新增赔率常量）；装饰 SKU 无承载系统整行砍（数值表-T5T6 C-5）[r055jade] R-055：title_jade 2500→1000（顶价可达性，见拍板 2026-10-01）
const ACT_BOSS_FREE_STRIKES = 5;                   // [r113boss] R-113 免费出手 5 次/日/只（fun_daily kind='raid5f<ev>_<no>'，逐只独立）
const ACT_BOSS_PAID_LIMIT = 10;                    // [r113boss] R-113 收费（诛妖符）10 次/日/只（kind='raid5p<ev>_<no>'，逐只独立）
const ACT_BOSS_PAID_COOLDOWN_MS = 5 * 60 * 1000;   // [r113boss] R-113 收费出手冷却 5 分钟（逐只独立，取该 kind 最近一次时间）
const ACT_BOSS_MAX_BOSSES = 5;                     // [r113boss] R-113 五只 boss 同时出现（event_boss5 五行并存，各自独立血量/次数/冷却）
const ACT_BOSS_STRIKE_COOLDOWN_MS = 10 * 60 * 1000; // [r113boss] R-113 免费出手冷却 10 分钟（逐只独立，kind='raid5f<ev>_<no>'）
const ACT_BOSS_HP_GROWTH = 0.5;                    // [r113boss] R-113 第 n 只血量 = 基础 × (1 + 0.5×(n-1))：第 1 只 1× … 第 5 只 3×
const ACT_BOSS_TALISMAN_DAILY = 2;                 // D 诛妖符 +2 次/日（kind='raid_talisman'，价=1×境界时薪）
const ACT_BOSS_HP_CYCLE = 20;                      // D 血量期数系数：500,000×1.5^6×20 = 113,906,250
const ACT_BOSS_TRUCE_MS = 2 * 24 * 60 * 60 * 1000; // D 提前击杀休战期 2 天（结算=击杀时刻+2 天）
const ACT_BOSS_STRIKE_TIERS: Array<{ min: number; hours: number }> = [
  { min: 24, hours: 4 }, { min: 12, hours: 2 }, { min: 4, hours: 1 },
]; // 档位线=累计出手次数 4/12/24（数值表-T5T6 D-3 口径裁决：量纲自洽/零加列/D1 确定性）
const ACT_BOSS_RANK_HOURS = [12, 8, 5];            // D 排名 1 / 2~3 / 4~10（榜单只含出手≥1 次）
const ACT_KILLER_HOURS = 2;                        // D 击杀者 +2h（+chronicle【诛妖】在击杀时刻）
const ACT_SERVER_KILL_HOURS = 0.5;                 // D 全服击破奖 +0.5h

// 冲榜档位（纯）：名次 1 基；n30 = max(11, ceil(0.3N))（数值表-T5T6 §2.1 边界口径）。
// 结构封顶 A1：榜 1 双榜 = 12×2 = 24h 恰等封顶，封顶不裁剪任何合法所得。
function actRankTier(rank: number, total: number): { hours: number; tier: string } {
  if (rank <= 1) return { hours: 12, tier: 'top1' };
  if (rank <= 3) return { hours: 8, tier: 'top2_3' };
  if (rank <= 10) return { hours: 5, tier: 'top4_10' };
  if (rank <= Math.max(11, Math.ceil(total * 0.3))) return { hours: 2, tier: 'top30' };
  return { hours: 0.5, tier: 'part' };
}
// 境界时薪（复用 rainHourlyStones 同源公式；无 rankings 行按炼气档保底）
async function actHourlyOf(userId: number): Promise<number> {
  const r = await dbGet('SELECT realm_index FROM rankings WHERE user_id = ?', [userId]).catch(() => null);
  return rainHourlyStones(r ? r.realm_index : 0);
}
// 活动事件行读取：id 非法/不存在/type 不符 → null（端点回 400，不信任客户端传参）
async function actEventOf(eventIdRaw: unknown, wantType: string): Promise<any | null> {
  const id = Math.floor(Number(eventIdRaw));
  if (!Number.isFinite(id) || id <= 0) return null;
  const r = await dbGet('SELECT id, type, name, start_at, end_at, enabled FROM events WHERE id = ?', [id]).catch(() => null);
  return r && String(r.type) === wantType ? r : null;
}
// 引擎开关（低频端点每次直读 DB，不依赖内存镜像时效；镜像只服务结算器首行早退）
async function actEngineEnabled(): Promise<boolean> {
  const cfg = await dbGet("SELECT value FROM activity_config WHERE key = 'engine_on'").catch(() => null);
  return String(cfg && cfg.value) === '1';
}
// C 掉玉（服务端结算点专用挂点）：只认活跃 token_shop 场次；floor(结算×2/10000)，日上限 300。
// 日账 activity_token_daily 守卫式钳制（超额自动截到剩余额度）；余额 ON CONFLICT 原子累加，跨期保留。
async function actDropTokens(userId: number, stonesSettled: number, nowMs: number): Promise<number> {
  const settled = Math.max(0, Math.floor(Number(stonesSettled) || 0));
  if (!settled) return 0;
  const ev = await dbGet(
    "SELECT id FROM events WHERE type = 'token_shop' AND enabled = 1 AND start_at <= ? AND end_at > ? LIMIT 1",
    [nowMs, nowMs]).catch(() => null);
  if (!ev) return 0;
  let gain = Math.floor((settled * ACT_TOKEN_RATE_PER_10K) / 10000);
  if (gain <= 0) return 0;
  const today = utcDateStr();
  await dbRun('INSERT OR IGNORE INTO activity_token_daily (player_id, date, earned) VALUES (?, ?, 0)', [userId, today]).catch(() => { });
  let up = await dbRun(
    'UPDATE activity_token_daily SET earned = earned + ? WHERE player_id = ? AND date = ? AND earned + ? <= ?',
    [gain, userId, today, gain, ACT_TOKEN_DAILY_CAP]);
  if (!up.changes) {
    const row = await dbGet('SELECT earned FROM activity_token_daily WHERE player_id = ? AND date = ?', [userId, today]).catch(() => null);
    const left = Math.max(0, ACT_TOKEN_DAILY_CAP - Math.max(0, Math.floor(Number(row && row.earned) || 0)));
    if (left <= 0) return 0;
    up = await dbRun(
      'UPDATE activity_token_daily SET earned = earned + ? WHERE player_id = ? AND date = ? AND earned + ? <= ?',
      [left, userId, today, left, ACT_TOKEN_DAILY_CAP]);
    if (!up.changes) return 0;
    gain = left;
  }
  await dbRun(
    `INSERT INTO activity_token (player_id, token_key, balance, earned_total, spent_total, updated_at)
     VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
     ON CONFLICT(player_id, token_key) DO UPDATE SET
       balance = balance + excluded.balance, earned_total = earned_total + excluded.earned_total,
       updated_at = CURRENT_TIMESTAMP`,
    [userId, ACT_TOKEN_KEY, gain, gain]).catch((e: any) => console.error('act token credit error:', e?.message || e));
  return gain;
}

// ── A 仙途冲榜：GET /api/activity/rank?eventId=&board=silver|kills ──
// 活跃期实时聚合（LIMIT 50 + mine，服务端重算参与线）；已结算期返回快照（PK 幂等落表）。
app.get('/api/activity/rank', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `act:rank:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const board = asStr(req.query?.board);
    if (board !== 'silver' && board !== 'kills') return res.status(400).json({ error: 'board 非法（silver|kills）' });
    const ev = await actEventOf(req.query?.eventId, 'rank_battle');
    if (!ev) return res.status(400).json({ error: 'eventId 非法' });
    const now = Date.now();
    const startAt = Number(ev.start_at);
    const endAt = Number(ev.end_at);
    const settled = now >= endAt;
    const window = {
      eventId: Number(ev.id), name: String(ev.name || ''), startAt, endAt,
      active: actIsActive(ev, now),
      leftMs: actWindowOk(startAt, endAt, now) ? Math.max(0, endAt - now) : 0,
    };
    const mkRow = (uid: number, name: string, score: unknown, rank: number, tier: string) => ({
      userId: uid, name: String(name || ''), score: Math.max(0, Math.floor(Number(score) || 0)), rank, tier,
    });
    let top50: any[] = [];
    let mine: any = null;
    if (settled) {
      const rows = await dbAll(
        `SELECT s.user_id AS uid, s.rank AS rk, s.tier AS tier, s.score AS score,
                COALESCE(NULLIF(r.name, ''), u.username) AS name
         FROM activity_rank_settled s JOIN users u ON u.id = s.user_id LEFT JOIN rankings r ON r.user_id = s.user_id
         WHERE s.event_id = ? AND s.board = ? ORDER BY s.rank ASC LIMIT 50`,
        [Number(ev.id), board]);
      top50 = (rows || []).map((x: any) => mkRow(Number(x.uid), x.name, x.score, Math.max(0, Math.floor(Number(x.rk) || 0)), String(x.tier || '')));
      const m = await dbGet(
        'SELECT rank AS rk, tier, score FROM activity_rank_settled WHERE event_id = ? AND board = ? AND user_id = ? LIMIT 1',
        [Number(ev.id), board, userId]).catch(() => null);
      if (m) mine = mkRow(userId, '', m.score, Math.max(0, Math.floor(Number(m.rk) || 0)), String(m.tier || ''));
    } else {
      const scoreCol = board === 'silver' ? 'SUM(s.silver_gain)' : 'SUM(s.kills)';
      const rows: any[] = await dbAll(
        `SELECT s.player_id AS uid, ${scoreCol} AS score, COALESCE(NULLIF(r.name, ''), u.username) AS name
         FROM stats_daily s JOIN users u ON u.id = s.player_id LEFT JOIN rankings r ON r.user_id = s.player_id
         WHERE s.date >= ? AND s.date <= ?
         GROUP BY s.player_id HAVING SUM(s.minutes) >= ? AND ${scoreCol} > 0
         ORDER BY score DESC, uid ASC`,
        [bjDate(startAt), bjDate(Math.max(startAt, endAt - 1)), ACT_RANK_MIN_MINUTES]);
      const list = rows || [];
      top50 = list.slice(0, 50).map((x, i) => {
        const t = actRankTier(i + 1, list.length);
        return mkRow(Number(x.uid), x.name, x.score, i + 1, t.tier);
      });
      const idx = list.findIndex((x) => Number(x.uid) === userId);
      if (idx >= 0) {
        const t = actRankTier(idx + 1, list.length);
        mine = mkRow(userId, '', list[idx].score, idx + 1, t.tier);
      }
    }
    res.json({ engineOn: await actEngineEnabled(), window, settled, top50, mine, board });
  } catch (e: any) {
    console.error('act rank error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ── B 仙缘七日礼：GET /api/activity/checkin?eventId= ──
app.get('/api/activity/checkin', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `act:ck:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    // [r054sign] R-054 每日签到（月历长期活动）：场次 = 北京自然月 lazy 建场；
    // day = 北京日期几号（不再由 start_at 推导），1..daysInMonth 随每月天数自动伸缩。
    // 奖励 = 灵石 1.0h + 修为 0.5h（境界时薪）；数值全在服务端实算下发，客户端零硬编码。
    const now = Date.now();
    const ev = await actSignEnsureMonth(now);
    if (!ev) return res.status(409).json({ error: '签到暂未开放' });
    const hourly = await actHourlyOf(userId);
    const monthKey = bjDate(now).slice(0, 7);
    const dim = actSignDaysInMonth(now);
    const today = Number(bjDate(now).slice(8, 10));
    const claimedRows = await dbAll('SELECT day FROM activity_checkin WHERE player_id = ? AND event_id = ?', [userId, Number(ev.id)]);
    const claimed = new Set<number>((claimedRows || []).map((x: any) => Math.floor(Number(x.day) || 0)));
    const days: any[] = [];
    let missedAny = false;
    for (let d = 1; d <= dim; d++) {
      const isClaimed = claimed.has(d);
      const missed = d < today && !isClaimed;
      if (missed) missedAny = true;
      days.push({ day: d, stones: Math.floor(hourly * ACT_SIGN_STONE_HOURS), exp: Math.floor(hourly * ACT_SIGN_EXP_HOURS), claimed: isClaimed, missed });
    }
    const progress = claimed.size;
    const mileRows = await dbAll('SELECT tier FROM activity_sign_miles WHERE player_id = ? AND event_id = ?', [userId, Number(ev.id)]);
    const claimedTiers = new Set<number>((mileRows || []).map((x: any) => Math.floor(Number(x.tier) || 0)));
    const active = actIsActive(ev, now);
    const milestones = ACT_SIGN_MILESTONES.map((m) => {
      const min = m.min < 0 ? dim : m.min; // -1 哨兵 = 当月全勤
      const parts: string[] = [];
      if (m.tickets > 0) parts.push(`抽奖券 ×${m.tickets}`);
      if (m.stoneHours > 0) parts.push(`灵石 +${Math.floor(hourly * m.stoneHours)}`);
      if (m.expHours > 0) parts.push(`修为 +${Math.floor(hourly * m.expHours)}`);
      if (m.scrolls > 0) parts.push(`太虚悟道卷 ×${m.scrolls}`);
      if (m.title) parts.push(`称号「${m.title}」`);
      return {
        min,
        desc: parts.join('、'),
        stones: Math.floor(hourly * (m.stoneHours || 0)),
        exp: Math.floor(hourly * (m.expHours || 0)),
        unlocked: progress >= min,
        claimed: claimedTiers.has(min),
      };
    });
    res.json({
      eventId: Number(ev.id),
      monthKey,
      daysInMonth: dim,
      days,
      today,
      progress,
      stonesToday: Math.floor(hourly * ACT_SIGN_STONE_HOURS),
      expToday: Math.floor(hourly * ACT_SIGN_EXP_HOURS),
      canClaim: active && (await actEngineEnabled()) && today >= 1 && today <= dim && !claimed.has(today),
      fullAttendable: active && today >= 1 && !missedAny,
      milestones,
    });
  } catch (e: any) {
    console.error('act checkin error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ── B 每日签到：POST /api/activity/checkin/claim {eventId} [r054sign] ──
// 主键 INSERT OR IGNORE 占位 → 服务端算 day = 北京几号（不信任客户端）→ updatePlayerSave
// 灵石+修为双入账（不走 mail，零邮件量；失败补偿删行可重试）。漏签不补：只能领「今天」。
app.post('/api/activity/checkin/claim', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `act:ckc:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    // [r054sign] 每日签到领取。客户端仍传 eventId（body 形态兼容），服务端一律以
    // actSignEnsureMonth 的当月场为准。奖励 = 灵石 1.0h + 修为 0.5h（境界时薪）。
    if (!(await actEngineEnabled())) return res.status(409).json({ error: '活动引擎暂未开启' });
    const now = Date.now();
    const ev = await actSignEnsureMonth(now);
    if (!ev) return res.status(409).json({ error: '签到暂未开放' });
    if (!actIsActive(ev, now)) return res.status(409).json({ error: '签到暂不可用（当月场次未激活）' });
    const day = Number(bjDate(now).slice(8, 10));
    const ins = await dbRun(
      'INSERT OR IGNORE INTO activity_checkin (player_id, event_id, day, claimed_at) VALUES (?, ?, ?, ?)',
      [userId, Number(ev.id), day, now]);
    if (!ins.changes) return res.status(409).json({ error: '今日已签到，明日再来' });
    const hourly = await actHourlyOf(userId);
    const stones = Math.floor(hourly * ACT_SIGN_STONE_HOURS);
    const exp = Math.floor(hourly * ACT_SIGN_EXP_HOURS);
    let credited = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') return;
      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + stones;
      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + exp;
      credited = true;
    });
    if (!paid.ok || !credited) {
      // 补偿删行可重试（占位已撤，直入账失败不吞签到机会）
      await dbRun('DELETE FROM activity_checkin WHERE player_id = ? AND event_id = ? AND day = ?', [userId, Number(ev.id), day]).catch(() => { });
      return res.status(409).json({ error: paid.error === 'No save found' ? '请先进游戏创建角色' : '领取失败，请重试' });
    }
    const c = await dbGet('SELECT COUNT(*) AS c FROM activity_checkin WHERE player_id = ? AND event_id = ?', [userId, Number(ev.id)]);
    res.json({ ok: true, day, stones, exp, reward: stones, progress: Math.max(0, Math.floor(Number(c && c.c) || 0)) });
  } catch (e: any) {
    console.error('act checkin claim error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ── C 灵玉阁：GET /api/activity/shop ──
// 商品目录 = 服务端常量字典（免表）；余额跨期保留；限购按期记账（bought:<eventId>:<itemId> 行）。
app.get('/api/activity/shop', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `act:shop:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const now = Date.now();
    const ev = await dbGet("SELECT id, name, start_at, end_at, enabled FROM events WHERE type = 'token_shop' AND enabled = 1 ORDER BY id DESC LIMIT 1").catch(() => null);
    const balRow = await dbGet('SELECT balance FROM activity_token WHERE player_id = ? AND token_key = ?', [userId, ACT_TOKEN_KEY]).catch(() => null);
    const balance = Math.max(0, Math.floor(Number(balRow && balRow.balance) || 0));
    const window = ev ? {
      eventId: Number(ev.id), name: String(ev.name || ''),
      startAt: Number(ev.start_at), endAt: Number(ev.end_at),
      active: actIsActive(ev, now),
      leftMs: actWindowOk(Number(ev.start_at), Number(ev.end_at), now) ? Math.max(0, Number(ev.end_at) - now) : 0,
    } : null;
    let items: any[] = ACT_SHOP_ITEMS.map((it) => ({ id: it.id, name: it.name, price: it.price, limit: it.limit, bought: 0 }));
    if (ev) {
      const keys = ACT_SHOP_ITEMS.map((it) => 'bought:' + Number(ev.id) + ':' + it.id);
      const rows = await dbAll(
        `SELECT token_key, balance FROM activity_token WHERE player_id = ? AND token_key IN (${keys.map(() => '?').join(', ')})`,
        [userId].concat(keys)).catch(() => []);
      const byKey = new Map<string, number>((rows || []).map((x: any) => [String(x.token_key), Math.max(0, Math.floor(Number(x.balance) || 0))]));
      items = ACT_SHOP_ITEMS.map((it) => ({
        id: it.id, name: it.name, price: it.price, limit: it.limit,
        bought: byKey.get('bought:' + Number(ev.id) + ':' + it.id) || 0,
      }));
    }
    res.json({ jadeBalance: balance, window, items, engineOn: await actEngineEnabled() }); // [v2810] \u9876\u5c42 balance \u6539\u540d jadeBalance\uff1a\u8fd9\u91cc\u662f activity_token \u7075\u7389\u4f59\u989d\uff0c\u4e0e\u7075\u77f3\u65e0\u5173
  } catch (e: any) {
    console.error('act shop error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ── C 灵玉阁：POST /api/activity/shop/exchange {itemId} ──
// 三段式：守卫式扣玉 → 守卫式占限购位（UNIQUE upsert + WHERE 钳限购）→ 发放；
// 任一步失败全补偿（退玉/退位），可重试。窗口外/引擎关：409 且余额分毫不动。
app.post('/api/activity/shop/exchange', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `act:exc:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const itemId = asStr(req.body?.itemId);
    const item = ACT_SHOP_ITEMS.find((x) => x.id === itemId);
    if (!item) return res.status(400).json({ error: 'itemId 非法' });
    if (!(await actEngineEnabled())) return res.status(409).json({ error: '本期灵玉阁已闭阁' });
    const now = Date.now();
    const ev = await dbGet(
      "SELECT id FROM events WHERE type = 'token_shop' AND enabled = 1 AND start_at <= ? AND end_at > ? LIMIT 1",
      [now, now]).catch(() => null);
    if (!ev) return res.status(409).json({ error: '本期灵玉阁已闭阁' });
    // ① 守卫式扣玉（changes=0 ⇒ 余额不足）
    const deduct = await dbRun(
      'UPDATE activity_token SET balance = balance - ?, spent_total = spent_total + ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND token_key = ? AND balance >= ?',
      [item.price, item.price, userId, ACT_TOKEN_KEY, item.price]);
    if (!deduct.changes) return res.status(409).json({ error: '灵玉余额不足' });
    // ② 守卫式占限购位
    const bk = 'bought:' + Number(ev.id) + ':' + item.id;
    const up = await dbRun(
      `INSERT INTO activity_token (player_id, token_key, balance, earned_total, spent_total, updated_at)
       VALUES (?, ?, 1, 0, 0, CURRENT_TIMESTAMP)
       ON CONFLICT(player_id, token_key) DO UPDATE SET balance = activity_token.balance + 1, updated_at = CURRENT_TIMESTAMP
       WHERE activity_token.balance + 1 <= ?`,
      [userId, bk, item.limit]);
    if (!up.changes) {
      // 补偿退玉
      await dbRun('UPDATE activity_token SET balance = balance + ?, spent_total = spent_total - ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND token_key = ?',
        [item.price, item.price, userId, ACT_TOKEN_KEY]).catch(() => { });
      return res.status(409).json({ error: '该商品本期限购已用完' });
    }
    // ③ 发放（失败全补偿：退玉 + 退限购位）
    let gained = 0;
    let title: string | null = null;
    const refundAll = async () => {
      await dbRun('UPDATE activity_token SET balance = balance + ?, spent_total = spent_total - ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND token_key = ?',
        [item.price, item.price, userId, ACT_TOKEN_KEY]).catch(() => { });
      await dbRun('UPDATE activity_token SET balance = balance - 1 WHERE player_id = ? AND token_key = ? AND balance > 0', [userId, bk]).catch(() => { });
    };
    if (item.hours) {
      gained = Math.floor((await actHourlyOf(userId)) * item.hours);
      let credited = false;
      const paid = await updatePlayerSave(userId, (sd: any) => {
        if (!sd.player || typeof sd.player !== 'object') return;
        sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + gained;
        credited = true;
      });
      if (!paid.ok || !credited) {
        await refundAll();
        return res.status(409).json({ error: paid.error === 'No save found' ? '请先进游戏创建角色' : '兑换失败，请重试' });
      }
    } else if (item.titleSource) {
      const okT = await grantTitleBySource(userId, item.titleSource).catch(() => false);
      title = '灵玉仙客';
      if (!okT) {
        await refundAll();
        return res.status(409).json({ error: '称号已拥有或发放失败' });
      }
    }
    const balRow = await dbGet('SELECT balance FROM activity_token WHERE player_id = ? AND token_key = ?', [userId, ACT_TOKEN_KEY]).catch(() => null);
    res.json({ ok: true, jadeBalance: Math.max(0, Math.floor(Number(balRow && balRow.balance) || 0)), gained, item: item.id, title }); // [v2810] \u540c\u4e0a\uff1a\u7075\u7389\u4f59\u989d\u6539\u540d jadeBalance
  } catch (e: any) {
    console.error('act exchange error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ── D 万妖巢穴：lazy 建场（同 wbEnsure 口径；血量=WB_HP_BASE×1.5^maxRealm×20）──
async function actBossEnsure(eventId: number): Promise<any> {
  // [r113boss] R-113 五只 boss 同时出现：event_boss 行降级为「聚合/结算行」（血量求和；五只全诛才
  //   killed=1），真正血量在 event_boss5 五行（各自独立）。R-056「诛一只刷下一只」顺序逻辑整体移除。
  //   ★ 基础血量行（hp = floor(WB_HP_BASE × mult × ACT_BOSS_HP_CYCLE)）逐字保留，
  //     不改 reward089 冻结锚「万妖巢穴血量未动」；逐只血量在其上乘成长系数。
  const top = await dbGet('SELECT MAX(realm_index) AS ri FROM rankings').catch(() => null);
  const mult = Math.pow(1.5, Math.min(20, Math.max(0, Number(top && top.ri) || 0)));
  const hp = Math.floor(WB_HP_BASE * mult * ACT_BOSS_HP_CYCLE);
  let row = await dbGet('SELECT * FROM event_boss WHERE event_id = ?', [eventId]).catch(() => null);
  if (!row) {
    const sum0 = Math.floor(hp * (ACT_BOSS_MAX_BOSSES + ACT_BOSS_HP_GROWTH * ACT_BOSS_MAX_BOSSES * (ACT_BOSS_MAX_BOSSES - 1) / 2));
    await dbRun('INSERT OR IGNORE INTO event_boss (event_id, hp_max, hp_cur) VALUES (?, ?, ?)', [eventId, sum0, sum0]).catch(() => { });
    row = await dbGet('SELECT * FROM event_boss WHERE event_id = ?', [eventId]).catch(() => null);
  }
  // 五只槽位幂等建场（各自血量 = 基础 × (1 + 0.5×(n-1))；建场即定血，跨请求不漂移）
  for (let no = 1; no <= ACT_BOSS_MAX_BOSSES; no++) {
    const slot = await dbGet('SELECT boss_no FROM event_boss5 WHERE event_id = ? AND boss_no = ?', [eventId, no]).catch(() => null);
    if (!slot) {
      const hpN = Math.floor(hp * (1 + ACT_BOSS_HP_GROWTH * (no - 1)));
      await dbRun('INSERT OR IGNORE INTO event_boss5 (event_id, boss_no, hp_max, hp_cur) VALUES (?, ?, ?, ?)', [eventId, no, hpN, hpN]).catch(() => { });
    }
  }
  return row;
}
async function actNameOf(userIdRaw: unknown): Promise<string> {
  const uid = Math.floor(Number(userIdRaw) || 0);
  if (!uid) return '';
  const r = await dbGet("SELECT COALESCE(NULLIF(r.name, ''), u.username) AS n FROM users u LEFT JOIN rankings r ON r.user_id = u.id WHERE u.id = ?", [uid]).catch(() => null);
  return String((r && r.n) || '');
}
async function actFunUsedToday(userId: number, kind: string): Promise<number> {
  const c = await dbGet('SELECT COUNT(*) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, utcDateStr(), kind]).catch(() => null);
  return Math.max(0, Number(c && c.c) || 0);
}
// [r113boss] R-113：逐只 boss 的当日计数 / 最近一次时间（kind = 'raid5' + f|p + eventId + '_' + bossNo）
function actBossKind(eventId: number, bossNo: number, slot: string): string {
  return 'raid5' + slot + eventId + '_' + bossNo;
}
async function actBossUsedToday(userId: number, eventId: number, bossNo: number, slot: string): Promise<number> {
  const c = await dbGet('SELECT COUNT(*) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, utcDateStr(), actBossKind(eventId, bossNo, slot)]).catch(() => null);
  return Math.max(0, Number(c && c.c) || 0);
}
async function actBossLastAt(userId: number, eventId: number, bossNo: number, slot: string): Promise<number> {
  const r = await dbGet('SELECT COALESCE(MAX(created_at), 0) AS t FROM fun_daily WHERE player_id = ? AND kind = ?', [userId, actBossKind(eventId, bossNo, slot)]).catch(() => null);
  return Math.max(0, Math.floor(Number(r && r.t) || 0));
}
// 出手公共体：守卫式扣血 + 记分 + 击杀播报（免费/追加同口径；即时灵石恒 0）
async function actBossHitOnce(userId: number, eventId: number, bossNo: number, nowMs: number, isFree: boolean): Promise<{ score: number; total: number; killed: boolean; hpCur: number }> {
  const cpRow = await dbGet('SELECT combat_power FROM rankings WHERE user_id = ?', [userId]).catch(() => null);
  const cp = Number(cpRow && cpRow.combat_power) || 100;
  const score = Math.max(1, Math.floor(cp * 2 * (0.8 + Math.random() * 0.4)));
  // [r113boss] R-113：扣血改打指定槽位 event_boss5（bossNo 由请求体带入）；守卫式扣血口径与单 boss 时代一致。
  const upd = await dbRun(
    `UPDATE event_boss5 SET
       hp_cur = MAX(0, hp_cur - ?),
       killed = CASE WHEN hp_cur - ? <= 0 THEN 1 ELSE killed END,
       killer_id = CASE WHEN hp_cur - ? <= 0 THEN ? ELSE killer_id END
     WHERE event_id = ? AND boss_no = ? AND killed = 0`,
    [score, score, score, userId, eventId, bossNo]);
  if (!upd.changes) throw new Error('ACT_BOSS_KILLED_RACE');
  // 记分（PK 幂等 upsert；跨 5 只累计到 event_boss_hits ⇒ 结算档位/榜单口径与单 boss 时代一致）
  await dbRun(
    `INSERT INTO event_boss_hits (event_id, user_id, score, strikes) VALUES (?, ?, ?, 1)
     ON CONFLICT(event_id, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1`,
    [eventId, userId, score]);
  // 聚合行重算：血量求和；五只全诛才把 killed=1 / killed_at 落到 event_boss（供结算器判定休战与结算）
  const agg = await dbGet('SELECT COALESCE(SUM(hp_max),0) AS hm, COALESCE(SUM(hp_cur),0) AS hc, COALESCE(SUM(killed),0) AS kc, COUNT(*) AS n FROM event_boss5 WHERE event_id = ?', [eventId]).catch(() => null);
  const allDead = Number(agg && agg.n) > 0 && Number(agg && agg.kc) >= Number(agg && agg.n);
  await dbRun(
    'UPDATE event_boss SET hp_max = ?, hp_cur = ?, killed = ?, killer_id = CASE WHEN ? = 1 THEN ? ELSE killer_id END, killed_at = CASE WHEN ? = 1 THEN ? ELSE killed_at END WHERE event_id = ?',
    [Math.max(0, Math.floor(Number(agg && agg.hm) || 0)), Math.max(0, Math.floor(Number(agg && agg.hc) || 0)), allDead ? 1 : 0, allDead ? 1 : 0, userId, allDead ? 1 : 0, nowMs, eventId]).catch(() => { });
  const after = await dbGet('SELECT hp_cur, killed, killer_id FROM event_boss5 WHERE event_id = ? AND boss_no = ?', [eventId, bossNo]);
  const mine = await dbGet('SELECT score FROM event_boss_hits WHERE event_id = ? AND user_id = ?', [eventId, userId]);
  const killed = Number(after && after.killed) === 1;
  if (killed && Number(after && after.killer_id) === userId) {
    const kn = await actNameOf(userId);
    logChronicle(userId, kn, `【诛妖】「${String((await dbGet('SELECT name FROM events WHERE id = ?', [eventId]).catch(() => null))?.name || '万妖')}」第 ${bossNo} 只伏诛，最后一击出自「${kn}」之手，全服同贺`);
  }
  return { score, total: Math.max(0, Math.floor(Number(mine && mine.score) || 0)), killed, hpCur: Math.max(0, Math.floor(Number(after && after.hp_cur) || 0)) };
}

// ── D 万妖巢穴：GET /api/eventboss/status?eventId= ──
app.get('/api/eventboss/status', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `act:boss:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const ev = await actEventOf(req.query?.eventId, 'boss_raid');
    if (!ev) return res.status(400).json({ error: 'eventId 非法' });
    const boss = await actBossEnsure(Number(ev.id));
    const mine = await dbGet('SELECT score, strikes FROM event_boss_hits WHERE event_id = ? AND user_id = ?', [Number(ev.id), userId]).catch(() => null);
    const top = await dbAll(
      `SELECT h.user_id AS uid, h.score, COALESCE(NULLIF(r.name, ''), u.username) AS name
       FROM event_boss_hits h JOIN users u ON u.id = h.user_id LEFT JOIN rankings r ON r.user_id = h.user_id
       WHERE h.event_id = ? ORDER BY h.score DESC LIMIT 10`, [Number(ev.id)]);
    // [r113boss] R-113：五只 boss 同时出现，逐只回执（各自血量/击杀/免费次数/收费次数/冷却）。
    const slots = await dbAll('SELECT boss_no, hp_max, hp_cur, killed, killer_id FROM event_boss5 WHERE event_id = ? ORDER BY boss_no ASC', [Number(ev.id)]).catch(() => []);
    const nowS = Date.now();
    const bosses: any[] = [];
    for (const s of (slots || [])) {
      const no = Math.max(1, Math.floor(Number(s.boss_no) || 1));
      const kd = Number(s.killed) === 1;
      const fUsed = await actBossUsedToday(userId, Number(ev.id), no, 'f');
      const pUsed = await actBossUsedToday(userId, Number(ev.id), no, 'p');
      const fAt = await actBossLastAt(userId, Number(ev.id), no, 'f');
      const pAt = await actBossLastAt(userId, Number(ev.id), no, 'p');
      bosses.push({
        no,
        hpMax: Math.max(0, Math.floor(Number(s.hp_max) || 0)),
        hpCur: Math.max(0, Math.floor(Number(s.hp_cur) || 0)),
        killed: kd,
        killerName: kd ? await actNameOf(s.killer_id) : null,
        freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - fUsed),
        paidLeft: Math.max(0, ACT_BOSS_PAID_LIMIT - pUsed),
        freeCoolLeft: fAt > 0 ? Math.max(0, Math.ceil((ACT_BOSS_STRIKE_COOLDOWN_MS - (nowS - fAt)) / 1000)) : 0,
        paidCoolLeft: pAt > 0 ? Math.max(0, Math.ceil((ACT_BOSS_PAID_COOLDOWN_MS - (nowS - pAt)) / 1000)) : 0,
      });
    }
    const killed = Number(boss.killed) === 1;
    res.json({
      eventId: Number(ev.id),
      hpMax: Math.max(0, Math.floor(Number(boss.hp_max) || 0)),
      hpCur: Math.max(0, Math.floor(Number(boss.hp_cur) || 0)),
      killed,
      killerName: killed ? await actNameOf(boss.killer_id) : null,
      myScore: Math.max(0, Math.floor(Number(mine && mine.score) || 0)),
      myStrikes: Math.max(0, Math.floor(Number(mine && mine.strikes) || 0)),
      freeLeft: bosses.length ? bosses[0].freeLeft : 0,
      talismanLeft: bosses.length ? bosses[0].paidLeft : 0,
      bossNo: 1,
      bossMax: ACT_BOSS_MAX_BOSSES,
      coolLeft: bosses.length ? bosses[0].freeCoolLeft : 0,
      freeLimit: ACT_BOSS_FREE_STRIKES,
      paidLimit: ACT_BOSS_PAID_LIMIT,
      bosses,
      top10: (top || []).map((x: any, i: number) => ({ userId: Number(x.uid), name: String(x.name || ''), score: Math.max(0, Math.floor(Number(x.score) || 0)), rank: i + 1 })),
      active: actIsActive(ev, Date.now()),
    });
  } catch (e: any) {
    console.error('act boss status error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ── D 万妖巢穴：POST /api/eventboss/strike {eventId}（免费出手，即时灵石=0）──
app.post('/api/eventboss/strike', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `act:bst:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const ev = await actEventOf(req.body?.eventId, 'boss_raid');
    if (!ev) return res.status(400).json({ error: 'eventId 非法' });
    if (!(await actEngineEnabled())) return res.status(409).json({ error: '活动引擎暂未开启' });
    const now = Date.now();
    if (!actIsActive(ev, now)) return res.status(409).json({ error: '活动未开启或已结束' });
    const boss = await actBossEnsure(Number(ev.id));
    if (Number(boss.killed) === 1) return res.status(409).json({ error: '妖兽已被诛杀' });
    // [r113boss] R-113：bossNo 由请求体带入；五只同时出现，逐只独立「免费 5 次/日 + 10 分钟冷却」。
    const bossNo = Math.max(1, Math.min(ACT_BOSS_MAX_BOSSES, Math.floor(Number(req.body?.bossNo) || 1)));
    const slotRow = await dbGet('SELECT killed FROM event_boss5 WHERE event_id = ? AND boss_no = ?', [Number(ev.id), bossNo]).catch(() => null);
    if (!slotRow) return res.status(409).json({ error: '该妖兽不存在' });
    if (Number(slotRow.killed) === 1) return res.status(409).json({ error: '该妖兽已被诛杀' });
    const freeUsed = await actBossUsedToday(userId, Number(ev.id), bossNo, 'f');
    if (freeUsed >= ACT_BOSS_FREE_STRIKES) {
      return res.status(409).json({ error: `本只妖兽的免费出手已用尽（${ACT_BOSS_FREE_STRIKES} 次/日），可用诛妖符追加` });
    }
    const lastAt = await actBossLastAt(userId, Number(ev.id), bossNo, 'f');
    const coolMs = lastAt > 0 ? ACT_BOSS_STRIKE_COOLDOWN_MS - (now - lastAt) : 0;
    if (coolMs > 0) {
      return res.status(409).json({ error: `出手冷却中，还需 ${Math.ceil(coolMs / 1000)} 秒` });
    }
    // ① 占次数位（fun_daily UNIQUE 单语句原子）
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun(
        'INSERT INTO fun_daily (player_id, date, kind, count, cost, payout, detail, created_at) VALUES (?, ?, ?, ?, 0, 0, ?, ?)',
        [userId, utcDateStr(), actBossKind(Number(ev.id), bossNo, 'f'), freeUsed + 1, JSON.stringify({ eventId: Number(ev.id), bossNo }), now]);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '手速太快，请再试一次' });
      throw e;
    }
    // ② 守卫式扣血 + ③ 记分（被他人抢先击杀则补偿撤位）
    let hit: { score: number; total: number; killed: boolean; hpCur: number };
    try {
      hit = await actBossHitOnce(userId, Number(ev.id), bossNo, now, true);
    } catch (e: any) {
      if (String(e?.message || '') === 'ACT_BOSS_KILLED_RACE') {
        await dbRun('DELETE FROM fun_daily WHERE id = ?', [ins.lastID]).catch(() => { });
        return res.status(409).json({ error: '妖兽已被诛杀' });
      }
      throw e;
    }
    const killerIdRow = hit.killed ? await dbGet('SELECT killer_id FROM event_boss WHERE event_id = ?', [Number(ev.id)]).catch(() => null) : null;
    res.json({
      ok: true, score: hit.score, total: hit.total, killed: hit.killed,
      killer: hit.killed ? await actNameOf(killerIdRow && killerIdRow.killer_id) : null,
      hpCur: hit.hpCur,
      bossNo,
      freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - freeUsed - 1),
      coolLeft: ACT_BOSS_STRIKE_COOLDOWN_MS,
    });
  } catch (e: any) {
    console.error('act boss strike error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ── D 万妖巢穴：POST /api/eventboss/talisman {eventId}（诛妖符追加，三段式扣费）──
// ① 占符位（fun_daily UNIQUE）→ ② 扣灵石（失败补偿删行）→ ③ 守卫式扣血（失败退灵石+删行）。
// 符价 = 1×境界时薪；即时产出=0（D1 EV≤0.67 的结构保证）。
app.post('/api/eventboss/talisman', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `act:btl:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const ev = await actEventOf(req.body?.eventId, 'boss_raid');
    if (!ev) return res.status(400).json({ error: 'eventId 非法' });
    if (!(await actEngineEnabled())) return res.status(409).json({ error: '活动引擎暂未开启' });
    const now = Date.now();
    if (!actIsActive(ev, now)) return res.status(409).json({ error: '活动未开启或已结束' });
    const boss = await actBossEnsure(Number(ev.id));
    if (Number(boss.killed) === 1) return res.status(409).json({ error: '妖兽已被诛杀' });
    // [r113boss] R-113：收费（诛妖符）逐只 10 次/日 + 5 分钟冷却；bossNo 由请求体带入。
    const bossNo = Math.max(1, Math.min(ACT_BOSS_MAX_BOSSES, Math.floor(Number(req.body?.bossNo) || 1)));
    const slotRow = await dbGet('SELECT killed FROM event_boss5 WHERE event_id = ? AND boss_no = ?', [Number(ev.id), bossNo]).catch(() => null);
    if (!slotRow) return res.status(409).json({ error: '该妖兽不存在' });
    if (Number(slotRow.killed) === 1) return res.status(409).json({ error: '该妖兽已被诛杀' });
    const used = await actBossUsedToday(userId, Number(ev.id), bossNo, 'p');
    if (used >= ACT_BOSS_PAID_LIMIT) {
      return res.status(409).json({ error: `本只妖兽的收费出手已用尽（${ACT_BOSS_PAID_LIMIT} 次/日）` });
    }
    const paidLastAt = await actBossLastAt(userId, Number(ev.id), bossNo, 'p');
    const paidCoolMs = paidLastAt > 0 ? ACT_BOSS_PAID_COOLDOWN_MS - (now - paidLastAt) : 0;
    if (paidCoolMs > 0) {
      return res.status(409).json({ error: `收费出手冷却中，还需 ${Math.ceil(paidCoolMs / 1000)} 秒` });
    }
    const price = await actHourlyOf(userId); // 符价=1×境界时薪
    // ① 占符位
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun(
        'INSERT INTO fun_daily (player_id, date, kind, count, cost, payout, detail, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)',
        [userId, utcDateStr(), actBossKind(Number(ev.id), bossNo, 'p'), used + 1, price, JSON.stringify({ eventId: Number(ev.id), bossNo }), now]);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '手速太快，请再试一次' });
      throw e;
    }
    // ② 扣灵石（失败补偿删行）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Math.max(0, Math.floor(Number(sd.player?.spiritStones) || 0));
      if (b < price) { short = true; return; }
      sd.player.spiritStones = b - price;
    });
    if (!paid.ok || short) {
      await dbRun('DELETE FROM fun_daily WHERE id = ?', [ins.lastID]).catch(() => { });
      return res.status(409).json({ error: '灵石不足' });
    }
    // ③ 守卫式扣血 + 记分（被他人抢先击杀则退灵石 + 删行，全或无）
    let hit: { score: number; total: number; killed: boolean; hpCur: number };
    try {
      hit = await actBossHitOnce(userId, Number(ev.id), bossNo, now, false);
    } catch (e: any) {
      if (String(e?.message || '') === 'ACT_BOSS_KILLED_RACE') {
        await updatePlayerSave(userId, (sd: any) => {
          sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player?.spiritStones) || 0)) + price;
        }).catch(() => { });
        await dbRun('DELETE FROM fun_daily WHERE id = ?', [ins.lastID]).catch(() => { });
        return res.status(409).json({ error: '妖兽已被诛杀' });
      }
      throw e;
    }
    const killerIdRow = hit.killed ? await dbGet('SELECT killer_id FROM event_boss WHERE event_id = ?', [Number(ev.id)]).catch(() => null) : null;
    res.json({
      ok: true, score: hit.score, total: hit.total, killed: hit.killed,
      killer: hit.killed ? await actNameOf(killerIdRow && killerIdRow.killer_id) : null,
      hpCur: hit.hpCur, spent: price,
      bossNo,
      talismanLeft: Math.max(0, ACT_BOSS_PAID_LIMIT - used - 1),
      paidCoolLeft: ACT_BOSS_PAID_COOLDOWN_MS,
    });
  } catch (e: any) {
    console.error('act boss talisman error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ── 结算器 A：冲榜单榜结算（快照表主键幂等；邮件失败删行=断点续发挡板）──
async function actSettleRankBoard(ev: any, board: 'silver' | 'kills', nowMs: number): Promise<{ claimed: number; failed: number }> {
  const scoreCol = board === 'silver' ? 'SUM(s.silver_gain)' : 'SUM(s.kills)';
  const rows: any[] = await dbAll(
    `SELECT s.player_id AS uid, ${scoreCol} AS score
     FROM stats_daily s WHERE s.date >= ? AND s.date <= ?
     GROUP BY s.player_id HAVING SUM(s.minutes) >= ? AND ${scoreCol} > 0
     ORDER BY score DESC, uid ASC`,
    [bjDate(Number(ev.start_at)), bjDate(Math.max(Number(ev.start_at), Number(ev.end_at) - 1)), ACT_RANK_MIN_MINUTES]).catch(() => []);
  const total = (rows || []).length;
  let claimed = 0;
  let failed = 0;
  for (let i = 0; i < total; i++) {
    const t = actRankTier(i + 1, total);
    const uid = Number(rows[i].uid);
    const score = Math.max(0, Math.floor(Number(rows[i].score) || 0));
    const reward = Math.floor((await actHourlyOf(uid)) * t.hours);
    const ins = await dbRun(
      'INSERT OR IGNORE INTO activity_rank_settled (event_id, board, user_id, rank, tier, score, reward, settled_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
      [Number(ev.id), board, uid, i + 1, t.tier, score, reward, nowMs]).catch(() => ({ changes: 0 }));
    if (!ins.changes) continue; // 已结算（重跑幂等挡板）
    claimed++;
    const boardName = board === 'silver' ? '灵石获取' : '讨伐击杀';
    const tierName = t.tier === 'top1' ? '魁首' : t.tier === 'top2_3' ? '榜眼层' : t.tier === 'top4_10' ? '十强' : t.tier === 'top30' ? '前三十%' : '有效参与';
    try {
      await insertMail(uid, `仙途冲榜 · ${boardName}榜第 ${i + 1} 名`,
        `「${String(ev.name || '仙途冲榜')}」落幕！你以 ${score} 的成绩位居${boardName}榜第 ${i + 1} 名（${tierName}），奖励灵石 ×${reward} 已随信附上。

下期冲榜，再会！`,
        'system', reward, { noChronicle: true });
    } catch (mailErr: any) {
      // 断点续发：删快照行，下一轮只补失败者（已发者有行挡板不重发）
      await dbRun('DELETE FROM activity_rank_settled WHERE event_id = ? AND board = ? AND user_id = ?', [Number(ev.id), board, uid]).catch(() => { });
      failed++;
      console.error('act rank mail error:', mailErr?.message || mailErr);
    }
  }
  return { claimed, failed };
}

// ── 结算器（并列于 rainSettleTick）：A 冲榜 + D 万妖；boot-run + 定时双触发 ──
async function actSettleTick(): Promise<void> {
  if (actSettling) return;
  actSettling = true;
  try {
    if (!actEngineOn) return; // engine off: first-line early return, zero DB work
    const nowMs = Date.now();
    // A 仙途冲榜：窗口结束（enabled=1，层 2）后的首个 tick 结算；activity_config 行标记完成
    const rankEvs = await dbAll(
      "SELECT id, name, start_at, end_at FROM events WHERE type = 'rank_battle' AND enabled = 1 AND end_at <= ?",
      [nowMs]).catch(() => []);
    for (const ev of rankEvs || []) {
      const done = await dbGet("SELECT value FROM activity_config WHERE key = ?", ['act_rank_settled:' + Number(ev.id)]).catch(() => null);
      if (done) continue;
      const silver = await actSettleRankBoard(ev, 'silver', nowMs);
      const kills = await actSettleRankBoard(ev, 'kills', nowMs);
      if (silver.failed + kills.failed > 0) continue; // 有邮件失败：不标记，下一轮续发
      const mark = await dbRun("INSERT OR IGNORE INTO activity_config (key, value) VALUES (?, '1')", ['act_rank_settled:' + Number(ev.id)]);
      if (mark.changes && silver.claimed + kills.claimed > 0) {
        logChronicle(null, '天机阁', `【活动】「${String(ev.name || '仙途冲榜')}」仙途冲榜落幕，双榜名次已定，奖励随邮件送达，下期再会！`);
      }
    }
    // D 万妖巢穴：窗口结束或（击杀后休战 2 天）到期结算；settled=1 后重跑零新增
    const bossEvs = await dbAll(
      "SELECT id, name, start_at, end_at FROM events WHERE type = 'boss_raid' AND enabled = 1",
      []).catch(() => []);
    for (const ev of bossEvs || []) {
      const boss = await dbGet('SELECT * FROM event_boss WHERE event_id = ?', [Number(ev.id)]).catch(() => null);
      if (!boss || Number(boss.settled) === 1) continue;
      const killed = Number(boss.killed) === 1;
      const due = nowMs >= Number(ev.end_at) || (killed && nowMs >= Number(boss.killed_at || 0) + ACT_BOSS_TRUCE_MS);
      if (!due) continue;
      const hits = await dbAll(
        'SELECT user_id AS uid, score, strikes FROM event_boss_hits WHERE event_id = ? ORDER BY score DESC, user_id ASC',
        [Number(ev.id)]).catch(() => []);
      const total = (hits || []).length;
      let failed = 0;
      const sendOne = async (board: string, uid: number, rank: number, hours: number, mailTitle: string, body: string): Promise<void> => {
        if (hours <= 0) return;
        const reward = Math.floor((await actHourlyOf(uid)) * hours);
        if (reward <= 0) return;
        const ins = await dbRun(
          'INSERT OR IGNORE INTO activity_rank_settled (event_id, board, user_id, rank, tier, score, reward, settled_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)',
          [Number(ev.id), board, uid, rank, '', reward, nowMs]).catch(() => ({ changes: 0 }));
        if (!ins.changes) return; // 已发（幂等挡板）
        try {
          await insertMail(uid, mailTitle, body, 'system', reward, { noChronicle: true });
        } catch (mailErr: any) {
          await dbRun('DELETE FROM activity_rank_settled WHERE event_id = ? AND board = ? AND user_id = ?', [Number(ev.id), board, uid]).catch(() => { });
          failed++;
          console.error('act boss mail error:', mailErr?.message || mailErr);
        }
      };
      for (let i = 0; i < total; i++) {
        const uid = Number(hits[i].uid);
        const strikes = Math.max(0, Math.floor(Number(hits[i].strikes) || 0));
        const tier = ACT_BOSS_STRIKE_TIERS.find((x) => strikes >= x.min);
        const tierH = tier ? tier.hours : 0;
        const rankH = i === 0 ? ACT_BOSS_RANK_HOURS[0] : i <= 2 ? ACT_BOSS_RANK_HOURS[1] : i <= 9 ? ACT_BOSS_RANK_HOURS[2] : 0;
        const killH = killed && Number(boss.killer_id) === uid ? ACT_KILLER_HOURS : 0;
        const evName = String(ev.name || '万妖巢穴');
        if (tierH > 0) await sendOne('boss_tier', uid, i + 1, tierH, '万妖巢穴 · 讨伐档位奖',
          `「${evName}」结算：你累计出手 ${strikes} 次，达成${tierH >= 4 ? '破阵' : tierH >= 2 ? '讨伐' : '斩妖'}档，奖励已随信附上。`);
        if (rankH > 0) await sendOne('boss_rank', uid, i + 1, rankH, `万妖巢穴 · 讨伐榜第 ${i + 1} 名`,
          `「${evName}」结算：你以 ${Math.max(0, Math.floor(Number(hits[i].score) || 0))} 讨伐积分位居第 ${i + 1} 名，奖励已随信附上。`);
        if (killH > 0) await sendOne('boss_kill', uid, i + 1, killH, '万妖巢穴 · 诛妖者嘉奖',
          `「${evName}」被你亲手诛杀！额外嘉奖已随信附上，全服铭记这一击。`);
      }
      if (killed) {
        const all = await dbAll('SELECT user_id FROM saves', []).catch(() => []);
        for (const r of all || []) {
          await sendOne('boss_server', Number(r.user_id), 0, ACT_SERVER_KILL_HOURS, '万妖巢穴 · 全服同贺',
            `「${String(ev.name || '万妖巢穴')}」已被全服道友齐心诛灭！人人有份，略表心意。`);
        }
      }
      if (failed > 0) continue; // 有邮件失败：不置 settled，下一轮续发（已发者有挡板）
      await dbRun('UPDATE event_boss SET settled = 1, settled_at = ? WHERE event_id = ?', [nowMs, Number(ev.id)]).catch(() => { });
      const mark = await dbRun("INSERT OR IGNORE INTO activity_config (key, value) VALUES (?, '1')", ['act_boss_settled:' + Number(ev.id)]);
      if (mark.changes) {
        logChronicle(null, '天机阁', killed
          ? `【活动】「${String(ev.name || '万妖巢穴')}」万妖巢穴结算完成：妖兽已诛，档位/排名/全服奖励随邮件送达！`
          : `【活动】「${String(ev.name || '万妖巢穴')}」万妖巢穴落幕：妖兽遁走，讨伐奖励随邮件送达，下期再战！`);
      }
    }
  } catch (e: any) {
    console.error('act settle tick error:', e?.message || e);
  } finally {
    actSettling = false;
  }
}
setInterval(() => {
  // [arenaweek] \u5468\u699c\u7ed3\u7b97\u4e0e\u6d3b\u52a8\u5f15\u64ce\u65e0\u5173 \u21d2 \u5fc5\u987b\u65e9\u4e8e actEngineOn \u65e9\u9000\uff0c\u5426\u5219\u5f15\u64ce\u5173\u95ed\u65f6\u6c38\u4e0d\u7ed3\u7b97
  arenaWeekSettle().catch((e: any) => console.error('arena week tick error:', e?.message || e));
  if (!actEngineOn) return; // engine off: first-line early return, zero DB work
  actSettleTick().catch((e: any) => console.error('act tick error:', e?.message || e));
}, ACT_TICK_MS).unref();
// [act087] Boot: mirror engine_on for the activity settler + boot-run once — a restart that
// spanned an event window end must still settle (rank/boss snapshots are PK-idempotent).
dbGet("SELECT value FROM activity_config WHERE key = 'engine_on'")
  .then((r: any) => { actEngineOn = String(r && r.value) === '1'; return actSettleTick(); })
  .catch((e: any) => console.error('act boot settle error:', e?.message || e));

// ─────────────────────────────────────────────────────────
// [r054sign] R-054 每日签到（「仙缘七日礼」→ 月历长期活动，服务端半边）
//   · 场次：北京自然月 lazy 建场（type=checkin_fest，start=月初 0 点 / end=下月 1 日 0 点），
//     每月自动滚新场，GM 零维护；GM 禁用当月场 ⇒ ensure 返回禁用行、actIsActive=false ⇒ 409。
//   · day = 北京日期几号（与场窗口解耦）；奖励 = 灵石 1.0h + 修为 0.5h（境界时薪，actHourlyOf）。
//   · 里程碑：当月累计签到 3/7/14/21/全勤 五档，min=-1 哨兵=全勤；幂等表 activity_sign_miles。
//   · 业务拒绝一律 400/409；发放走 updatePlayerSave 直入账 + 失败补偿删行（087 同款纪律）。
// ─────────────────────────────────────────────────────────
db.run('CREATE TABLE IF NOT EXISTS activity_sign_miles (player_id INTEGER NOT NULL, event_id INTEGER NOT NULL, tier INTEGER NOT NULL, claimed_at INTEGER NOT NULL, PRIMARY KEY (player_id, event_id, tier))');
// [r054sign] 全勤限定称号 seed（OR IGNORE 幂等；grantTitleBySource 按 source='r054_month_sign' 定位）
db.run(`INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES ('月满勤修', '{"expRate":0.01}', 'r054_month_sign')`);
const ACT_SIGN_STONE_HOURS = 1.0; // 每日灵石 = 境界时薪 × 1.0（≈挂机 1 小时）
const ACT_SIGN_EXP_HOURS = 0.5;   // 每日修为 = 境界时薪 × 0.5（等效）
// 里程碑档（min=-1 哨兵 = 当月全勤）：tickets 抽奖券 / stoneHours·expHours 时薪折算 / scrolls 太虚悟道卷 / title 全勤称号
const ACT_SIGN_MILESTONES: Array<{ min: number; tickets: number; stoneHours: number; expHours: number; scrolls: number; title: string }> = [
  { min: 3, tickets: 3, stoneHours: 0, expHours: 0, scrolls: 0, title: '' },
  { min: 7, tickets: 0, stoneHours: 4, expHours: 0, scrolls: 0, title: '' },
  { min: 14, tickets: 0, stoneHours: 0, expHours: 6, scrolls: 0, title: '' },
  { min: 21, tickets: 0, stoneHours: 8, expHours: 0, scrolls: 2, title: '' },
  { min: -1, tickets: 0, stoneHours: 12, expHours: 0, scrolls: 0, title: '月满勤修' },
];
// 北京时区当月天数（28/29/30/31 自动伸缩；北京无夏令时 ⇒ 月长差恒整天）
function actSignDaysInMonth(nowMs: number): number {
  const month = bjDate(nowMs).slice(0, 7);
  const seg = month.split('-');
  const y = Number(seg[0]);
  const mo = Number(seg[1]);
  const nextMonth = mo === 12 ? (y + 1) + '-01' : month.slice(0, 5) + String(mo + 1).padStart(2, '0');
  return Math.max(28, Math.round((Date.parse(nextMonth + '-01T00:00:00+08:00') - Date.parse(month + '-01T00:00:00+08:00')) / 86400000));
}
// 当月签到场 lazy 建场：按 (type, start_at, end_at) 精确匹配自然月场；GM 手建的历史 7 天场
// start_at 非月初 ⇒ 天然不匹配而被弃用。禁用场原样返回（kill switch 逐场层生效，不重建）。
async function actSignEnsureMonth(nowMs: number): Promise<any | null> {
  const month = bjDate(nowMs).slice(0, 7);
  const startAt = Date.parse(month + '-01T00:00:00+08:00');
  const seg = month.split('-');
  const y = Number(seg[0]);
  const mo = Number(seg[1]);
  const nextMonth = mo === 12 ? (y + 1) + '-01' : month.slice(0, 5) + String(mo + 1).padStart(2, '0');
  const endAt = Date.parse(nextMonth + '-01T00:00:00+08:00');
  if (!Number.isFinite(startAt) || !Number.isFinite(endAt) || endAt <= startAt) return null;
  const cur = await dbGet("SELECT id, type, name, start_at, end_at, enabled FROM events WHERE type = 'checkin_fest' AND start_at = ? AND end_at = ? ORDER BY id DESC LIMIT 1", [startAt, endAt]).catch(() => null);
  if (cur) return cur;
  await dbRun("INSERT INTO events (type, name, multiplier, start_at, end_at, enabled) VALUES ('checkin_fest', ?, 2, ?, ?, 1)", ['每日签到·' + month, startAt, endAt]).catch(() => { });
  return await dbGet("SELECT id, type, name, start_at, end_at, enabled FROM events WHERE type = 'checkin_fest' AND start_at = ? AND end_at = ? ORDER BY id DESC LIMIT 1", [startAt, endAt]).catch(() => null);
}
// [r054sign] 里程碑领取：{tier} = GET milestones[].min；主键占位幂等 + 直入账 + 失败补偿删行。
// 全勤称号在入账成功后授予（INSERT OR IGNORE 幂等；失败仅记日志不回滚奖励）。
app.post('/api/activity/checkin/milestone', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `act:ckm:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const tier = Math.floor(Number(req.body?.tier));
    if (!(await actEngineEnabled())) return res.status(409).json({ error: '活动引擎暂未开启' });
    const now = Date.now();
    const ev = await actSignEnsureMonth(now);
    if (!ev || !actIsActive(ev, now)) return res.status(409).json({ error: '签到暂不可用' });
    const dim = actSignDaysInMonth(now);
    const mdef = ACT_SIGN_MILESTONES.find((m) => (m.min < 0 ? dim : m.min) === tier);
    if (!mdef) return res.status(400).json({ error: 'tier 非法' });
    const c = await dbGet('SELECT COUNT(*) AS c FROM activity_checkin WHERE player_id = ? AND event_id = ?', [userId, Number(ev.id)]);
    const progress = Math.max(0, Math.floor(Number(c && c.c) || 0));
    if (progress < tier) return res.status(409).json({ error: '累计签到天数未达标' });
    const ins = await dbRun('INSERT OR IGNORE INTO activity_sign_miles (player_id, event_id, tier, claimed_at) VALUES (?, ?, ?, ?)', [userId, Number(ev.id), tier, now]);
    if (!ins.changes) return res.status(409).json({ error: '该里程碑已领取' });
    const hourly = await actHourlyOf(userId);
    const stones = Math.floor(hourly * (mdef.stoneHours || 0));
    const exp = Math.floor(hourly * (mdef.expHours || 0));
    let credited = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') return;
      if (stones > 0) { sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + stones; }
      if (exp > 0) { sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + exp; }
      if (mdef.tickets > 0) { sd.player.lotteryTickets = Math.max(0, Math.floor(Number(sd.player.lotteryTickets) || 0)) + mdef.tickets; }
      if (mdef.scrolls > 0) {
        sd.player.inventory = Array.isArray(sd.player.inventory) ? sd.player.inventory : [];
        sd.player.inventory.push({ id: 'r054sign-' + now + '-' + Math.floor(Math.random() * 10000), name: '太虚悟道卷', type: '材料', description: '记载远古神通道法奥义的残卷，可用于自创神通与提升神通领悟境界。', quantity: mdef.scrolls, rarity: '传说' });
      }
    });
    if (!paid.ok || !credited) {
      await dbRun('DELETE FROM activity_sign_miles WHERE player_id = ? AND event_id = ? AND tier = ?', [userId, Number(ev.id), tier]).catch(() => { });
      return res.status(409).json({ error: paid.error === 'No save found' ? '请先进游戏创建角色' : '领取失败，请重试' });
    }
    let title: string | null = null;
    if (mdef.title) {
      const okT = await grantTitleBySource(userId, 'r054_month_sign').catch(() => false);
      title = okT ? mdef.title : null;
      if (!okT) console.error('act sign title grant failed:', userId);
    }
    res.json({ ok: true, tier, stones, exp, tickets: mdef.tickets || 0, scrolls: mdef.scrolls || 0, title, progress });
  } catch (e: any) {
    console.error('act checkin milestone error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});
// [arenaweek] \u5468\u699c\u7ed3\u7b97 boot-run\uff1a\u91cd\u542f\u8de8\u8fc7\u5468\u4e00 0 \u70b9\u65f6\u8865\u7ed3\u7b97\uff08\u5e42\u7b49\uff1b\u5fae\u4efb\u52a1\u5ef6\u8fdf\u907f\u514d TDZ\uff09
Promise.resolve().then(() => arenaWeekSettle()).catch((e: any) => console.error('arena week boot settle error:', e?.message || e));

// ─────────────────────────────────────────────────────────
// Y6B 师徒系统 API（伴生页 /yl/apps/mentor/）：拜师（徒弟发起：目标须境界≥筑基期 且 总等级≥徒弟+5，
// 即时生效+系统邮件双方通知）/ 我的师徒 / 出师（徒弟≥金丹期：师傅得徒弟累计灵石收益 30% 邮件回馈
// + 7 天 ×1.3 收益增益 + 称号「良师益友」）/ 解除（双方 7 天冷却）/ 拜师搜索（按玩家名 LIKE）。
// 上限兜底：每徒弟 1 位在门师傅=部分唯一索引；每师傅 3 弟子=拜师守卫式单语句 INSERT（COUNT 子查询），
// 并发双拜只一方 changes=1 生效。福利：师徒都在线（近 10 分钟均有存档活动）徒弟服务端结算 ×1.1
// （resolveMentorGains 挂离线/灵田/炼丹三结算点，与 Y21 活动倍率叠乘）；师傅抽徒弟收益 5%
// （tickMentorTax 挂 POST /api/save 差值路径，与 stats_daily 同源同口径，fire-and-forget）。
// 架构边界：游戏内打坐/历练结算在客户端混淆码内，徒弟 +10% 仅服务端结算点生效（同回归 buff/活动倍率口径）。
// ─────────────────────────────────────────────────────────

// Y6B 师徒收益倍率解析（每结算请求一次）：徒弟在门且师徒都在线 → ×1.1；本人有未到期出师增益 → ×1.3；
// 两者叠乘（同一人可兼徒弟+出师师傅）。调用方 catch 按 ×1 保底，师徒任何故障不阻塞结算主路径。
async function resolveMentorGains(userId: number, nowMs: number): Promise<{ expMult: number; stonesMult: number }> {
  let mult = 1;
  const rel = await dbGet("SELECT mentor_id FROM mentorships WHERE apprentice_id = ? AND status = 'active' LIMIT 1", [userId]);
  if (rel) {
    const mSave = await dbGet('SELECT updated_at FROM saves WHERE user_id = ?', [Number(rel.mentor_id)]);
    mult = mentorBonusMult(true, parseDbTimeMs(mSave?.updated_at), nowMs);
  }
  const buffRow = await dbGet("SELECT MAX(mentor_buff_until) AS b FROM mentorships WHERE mentor_id = ? AND status = 'completed'", [userId]);
  mult *= mentorBuffMult(buffRow?.b, nowMs);
  return { expMult: mult, stonesMult: mult };
}

// Y6B 师徒抽成：徒弟存档上传差值（与 stats_daily 同源路径）→ 在门师徒关系存在时，
// 师傅入账 5% 灵石 + 5% 修为（修为钳槽内防溢出，saveLock 互斥）；tax_stones 单语句原子累加供伴生页展示。
// 无差值/无关系/师傅无存档一律静默跳过；失败记日志，绝不影响存档主路径。
async function tickMentorTax(apprenticeId: number, d: StatsDelta): Promise<void> {
  if (!(d.silver > 0) && !(d.exp > 0)) return;
  const rel = await dbGet("SELECT id, mentor_id FROM mentorships WHERE apprentice_id = ? AND status = 'active' LIMIT 1", [apprenticeId]);
  if (!rel) return;
  const tax = mentorTax(d.silver, d.exp);
  if (tax.stones <= 0 && tax.exp <= 0) return;
  let applied = false;
  const paid = await updatePlayerSave(Number(rel.mentor_id), (sd: any) => {
    if (!sd.player || typeof sd.player !== 'object') return;
    sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + tax.stones;
    const nrNow = normalizeRealm(sd.player);
    sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + Math.min(tax.exp, Math.max(0, nrNow.maxExp - nrNow.exp));
    applied = true;
  });
  if (!paid.ok || !applied) return;
  if (tax.stones > 0) await dbRun('UPDATE mentorships SET tax_stones = tax_stones + ? WHERE id = ?', [tax.stones, Number(rel.id)]);
}

// GET /api/mentor/my — 我的师徒关系全景：师傅/在门弟子（含累计抽成与出师就绪）/历史/冷却截止/规则常量
app.get('/api/mentor/my', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `mentor:my:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const now = Date.now();
    const rn = (i: unknown) => (Number.isInteger(Number(i)) && Number(i) >= 0 ? REALM_ORDER_FOR_RANKING[Number(i)] || '' : '');
    // 0.8.7 申请-审批制：惰性归档——读取时把超过申请有效期（48h，见 [mentorcore] 常量区）的 pending 置 declined
    //（幂等，零定时任务惯例；declined 不进冷却，部分唯一索引位随之释放，申请人可立刻改投他人）
    await dbRun("UPDATE mentorships SET status = 'declined' WHERE status = 'pending' AND created_at < ?", [now - MENTOR_APPLY_TTL_MS]).catch(() => {});
    const [meRow, mentorRow, appRows, histRows, coolRow, pendRow, incRows, teachRow] = await Promise.all([
      dbGet('SELECT COALESCE(NULLIF(name, \'\'), username) AS name, realm_index, realm_level FROM rankings WHERE user_id = ?', [userId]),
      dbGet(
        `SELECT m.created_at, u.id AS uid, COALESCE(NULLIF(r.name, ''), u.username) AS name, r.realm_index, r.realm_level
         FROM mentorships m JOIN users u ON u.id = m.mentor_id LEFT JOIN rankings r ON r.user_id = m.mentor_id
         WHERE m.apprentice_id = ? AND m.status = 'active' LIMIT 1`,
        [userId]
      ),
      dbAll(
        `SELECT m.created_at, m.tax_stones, u.id AS uid, COALESCE(NULLIF(r.name, ''), u.username) AS name, r.realm_index, r.realm_level
         FROM mentorships m JOIN users u ON u.id = m.apprentice_id LEFT JOIN rankings r ON r.user_id = m.apprentice_id
         WHERE m.mentor_id = ? AND m.status = 'active' ORDER BY m.created_at LIMIT ?`,
        [userId, MENTOR_MAX_APPRENTICES]
      ),
      dbAll(
        `SELECT m.status, m.created_at, m.graduated_at, m.ended_at,
                CASE WHEN m.mentor_id = ? THEN 'mentor' ELSE 'apprentice' END AS role,
                COALESCE(NULLIF(r.name, ''), u.username) AS name
         FROM mentorships m JOIN users u ON u.id = (CASE WHEN m.mentor_id = ? THEN m.apprentice_id ELSE m.mentor_id END)
         LEFT JOIN rankings r ON r.user_id = u.id
         WHERE (m.mentor_id = ? OR m.apprentice_id = ?) AND m.status NOT IN ('pending', 'declined')
         ORDER BY m.id DESC LIMIT 10`,
        [userId, userId, userId, userId]
      ),
      dbGet("SELECT MAX(ended_at) AS e FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND (mentor_id = ? OR apprentice_id = ?)", [userId, userId]),
      // 0.8.7：我发出的待审申请（作为徒弟；过期行已被上方惰性归档，此处必是新申请）
      dbGet(
        `SELECT m.created_at, m.mentor_id, COALESCE(NULLIF(r.name, ''), u.username) AS name
         FROM mentorships m JOIN users u ON u.id = m.mentor_id LEFT JOIN rankings r ON r.user_id = m.mentor_id
         WHERE m.apprentice_id = ? AND m.status = 'pending' LIMIT 1`,
        [userId]
      ),
      // 0.8.7：我（作为师傅）收到的待审申请
      dbAll(
        `SELECT m.created_at, u.id AS uid, COALESCE(NULLIF(r.name, ''), u.username) AS name, r.realm_index, r.realm_level
         FROM mentorships m JOIN users u ON u.id = m.apprentice_id LEFT JOIN rankings r ON r.user_id = m.apprentice_id
         WHERE m.mentor_id = ? AND m.status = 'pending' ORDER BY m.created_at LIMIT 10`,
        [userId]
      ),
      // 0.8.7：今日传功状态（与 /api/mentor/teach 同用 teach_log UNIQUE(user_id,date) 的 UTC 日切口径）
      dbGet('SELECT apprentice_id FROM teach_log WHERE user_id = ? AND date = ? LIMIT 1', [userId, utcDateStr()]),
    ]);
    const cooldownUntil = coolRow && coolRow.e != null ? mentorCoolingUntil(Number(coolRow.e)) : null;
    const peop = (r: any) => ({
      id: Number(r.uid),
      name: String(r.name || ''),
      realmIndex: r.realm_index == null ? null : Number(r.realm_index),
      realmName: rn(r.realm_index),
      realmLevel: r.realm_level == null ? null : Number(r.realm_level),
      level: mentorLevelOf(r.realm_index, r.realm_level),
    });
    res.json({
      now,
      me: meRow ? { ...peop(meRow) } : null,
      mentor: mentorRow ? { ...peop(mentorRow), since: Number(mentorRow.created_at) || 0 } : null,
      apprentices: (appRows || []).map((r) => ({ ...peop(r), since: Number(r.created_at) || 0, taxStones: Math.max(0, Math.floor(Number(r.tax_stones) || 0)), canGraduate: mentorGradOk(r.realm_index) })),
      history: (histRows || []).map((r) => ({
        role: String(r.role),
        name: String(r.name || ''),
        status: String(r.status),
        since: Number(r.created_at) || 0,
        endedAt: Number(r.ended_at) || Number(r.graduated_at) || 0,
      })),
      cooldownUntil,
      // ── 0.8.7 申请-审批制扩展（契约 C2）──
      myPending: pendRow ? { mentorId: Number(pendRow.mentor_id), mentorName: String(pendRow.name || ''), since: Number(pendRow.created_at) || 0 } : null,
      pendingIncoming: (incRows || []).map((r) => ({ apprenticeId: Number(r.uid), name: String(r.name || ''), realmName: rn(r.realm_index), level: mentorLevelOf(r.realm_index, r.realm_level), since: Number(r.created_at) || 0 })),
      teachDone: !!teachRow,
      taughtApprenticeId: teachRow ? Number(teachRow.apprentice_id) : null,
      consts: { teachExpBase: TEACH_EXP_BASE, teachVirtue: TEACH_VIRTUE, applyTtlMs: MENTOR_APPLY_TTL_MS },
      rules: {
        maxApprentices: MENTOR_MAX_APPRENTICES, levelGap: MENTOR_LEVEL_GAP, levelStep: MENTOR_LEVEL_STEP,
        onlineWindowMs: MENTOR_ONLINE_MS, bonusMult: MENTOR_BONUS_MULT, taxRate: MENTOR_TAX_RATE,
        gradRate: MENTOR_GRAD_RATE, buffMult: MENTOR_BUFF_MULT, buffMs: MENTOR_BUFF_MS,
        cooldownMs: MENTOR_EXPIRE_COOLDOWN_MS, minRealmIndex: MENTOR_MIN_REALM_INDEX, gradRealmIndex: MENTOR_GRAD_REALM_INDEX,
      },
    });
  } catch (e: any) {
    console.error('mentor my error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/mentor/apprentice {userId} — 拜师：我=徒弟，目标=师傅候选。门槛（目标境界≥筑基、总等级≥我+5）
// + 守卫式单语句插入（师傅门下<3 / 我无在门师傅 / 双方均不在解除冷却），并发双拜只一方生效；
// 成功后系统邮件通知双方（fire-and-forget，不阻塞响应）
app.post('/api/mentor/apprentice', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `mentor:bind:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const targetId = Math.floor(asNum(req.body?.userId));
    if (!Number.isInteger(targetId) || targetId <= 0) return res.status(400).json({ error: '参数非法' });
    if (targetId === userId) return res.status(400).json({ error: '不能拜自己为师' });
    const target = await dbGet('SELECT id, username FROM users WHERE id = ?', [targetId]);
    if (!target) return res.status(404).json({ error: '查无此道友' });
    const rows = await dbAll(
      "SELECT user_id, COALESCE(NULLIF(name, ''), username) AS name, realm_index, realm_level FROM rankings WHERE user_id IN (?, ?)",
      [userId, targetId]
    );
    const mine = (rows || []).find((r) => Number(r.user_id) === userId);
    const theirs = (rows || []).find((r) => Number(r.user_id) === targetId);
    if (!mine) return res.status(404).json({ error: '请先进游戏创建角色' });
    if (!theirs) return res.status(404).json({ error: '对方尚未踏入仙途（无角色存档）' });
    if (!mentorRealmOk(theirs.realm_index)) return res.status(409).json({ error: '对方境界未达筑基期，尚不可拜师' });
    const myLevel = mentorLevelOf(mine.realm_index, mine.realm_level);
    const targetLevel = mentorLevelOf(theirs.realm_index, theirs.realm_level);
    if (!mentorGapOk(myLevel, targetLevel)) {
      return res.status(409).json({ error: `对方总等级须比你高 ${MENTOR_LEVEL_GAP} 级（当前差 ${targetLevel - myLevel} 级）` });
    }
    const now = Date.now();
    const coolSince = now - MENTOR_EXPIRE_COOLDOWN_MS;
    // 0.8.7 拜师改申请-审批制：status 由 'active' 改 'pending'（守卫条件逐字保留；并发双拜只一方 changes=1）。
    // 部分唯一索引 idx_mentorships_apprentice_active(pending,active) 兜底「重复申请」：
    // 守卫只挡 active，已有 pending 行时 INSERT 撞索引 ⇒ 捕获 UNIQUE 转 409（绝不 500 / 绝不白扣）。
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun(
        `INSERT INTO mentorships (mentor_id, apprentice_id, status, created_at)
         SELECT ?, ?, 'pending', ?
         WHERE (SELECT COUNT(*) FROM mentorships WHERE mentor_id = ? AND status = 'active') < ?
           AND NOT EXISTS (SELECT 1 FROM mentorships WHERE apprentice_id = ? AND status = 'active')
           AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))
           AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))`,
        [targetId, userId, now, targetId, MENTOR_MAX_APPRENTICES, userId, coolSince, userId, userId, coolSince, targetId, targetId]
      );
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '你已有一份待处理的拜师申请，可先撤回再重新申请' });
      throw e;
    }
    if (!ins.changes) {
      // 失败逐项诊断（仅失败路径多查，给出可读 409）
      const [cntRow, hasRow, myCoolRow, tCoolRow] = await Promise.all([
        dbGet("SELECT COUNT(*) AS c FROM mentorships WHERE mentor_id = ? AND status = 'active'", [targetId]),
        dbGet("SELECT 1 AS x FROM mentorships WHERE apprentice_id = ? AND status = 'active' LIMIT 1", [userId]),
        dbGet("SELECT 1 AS x FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?) LIMIT 1", [coolSince, userId, userId]),
        dbGet("SELECT 1 AS x FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?) LIMIT 1", [coolSince, targetId, targetId]),
      ]);
      let msg = '拜师未成，条件有变，请刷新重试';
      if (hasRow) msg = '你已有师傅，不可另拜他人';
      else if (Number(cntRow?.c) >= MENTOR_MAX_APPRENTICES) msg = `对方门下弟子已满（${MENTOR_MAX_APPRENTICES}/${MENTOR_MAX_APPRENTICES}）`;
      else if (myCoolRow) msg = '你刚解除师徒关系，冷却中（7 天）';
      else if (tCoolRow) msg = '对方刚解除师徒关系，冷却中（7 天）';
      return res.status(409).json({ error: msg });
    }
    const myName = String(mine.name || req.user.username || '无名修士').slice(0, 32);
    const targetName = String(theirs.name || target.username || '').slice(0, 32);
    // 0.8.7：信只告知「收到申请」——正式生效以师傅在游戏内仙务·师徒页签收纳为准
    const rnName = (i: unknown) => (Number.isInteger(Number(i)) && Number(i) >= 0 ? REALM_ORDER_FOR_RANKING[Number(i)] || '' : '');
    const ttlH = Math.round(MENTOR_APPLY_TTL_MS / 3600000);
    insertMail(targetId, '拜师申请',
      `道友「${myName}」（${rnName(mine.realm_index)}${Number(mine.realm_level) || ''}层）仰慕你修行精深，递交了拜师申请。\n\n· 申请 ${ttlH} 小时内有效，逾期自动作废\n· 游戏内「仙务 → 师徒」页签可收纳或婉拒（收纳前关系不生效，双方无福利/抽成）\n· 收纳后：徒弟收益的 ${MENTOR_TAX_RATE * 100}%（修为/灵石）将自动奉上；师徒同行（双方在线）时徒弟结算收益 +${Math.round((MENTOR_BONUS_MULT - 1) * 100)}%；其金丹期出师时你将获得累计灵石收益 ${MENTOR_GRAD_RATE * 100}% 回馈 + 7 天 ×${MENTOR_BUFF_MULT} 收益增益 + 称号「良师益友」`,
      'system', 0).catch((e: any) => console.error('mentor bind mail(target) error:', e?.message || e));
    insertMail(userId, '拜师申请已提交',
      `你已向「${targetName}」递交拜师申请，等待对方收纳。\n\n· 申请 ${ttlH} 小时内有效，期间可在游戏内师徒页签撤回\n· 被婉拒或撤回均不进冷却，可立刻改投他人\n· 对方收纳后即刻生效，届时将另收到拜师成功信`,
      'system', 0).catch((e: any) => console.error('mentor bind mail error:', e?.message || e));
    res.json({ ok: true, status: 'pending', mentor: { id: targetId, name: targetName }, since: now });
  } catch (e: any) {
    console.error('mentor apprentice error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 师傅处理拜师申请（0.8.7 新增 N1，POST，入参 {apprenticeId, action:'accept'|'decline'}）。
// 仅被申请的师傅本人可调（他人 400）；无 pending 409；过期（超 48h）惰性置 declined + 409。
// accept=申请门槛重验（师傅境界/等级差）+ 守卫式单语句 UPDATE pending→active（门下<3、双方非 7 天解除
// 冷却，并发双审批只一方 changes=1）+ 双方邮件；decline=置 declined（不进 7 天冷却）+ 申请人邮件。
app.post('/api/mentor/decide', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `mentor:bind:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const appId = Math.floor(asNum(req.body?.apprenticeId));
    const action = asStr(req.body?.action);
    if (!Number.isInteger(appId) || appId <= 0) return res.status(400).json({ error: '参数非法' });
    if (action !== 'accept' && action !== 'decline') return res.status(400).json({ error: 'action 须为 accept 或 decline' });
    const rel: any = await dbGet("SELECT id, mentor_id, apprentice_id, created_at FROM mentorships WHERE apprentice_id = ? AND status = 'pending' LIMIT 1", [appId]);
    if (!rel) return res.status(409).json({ error: '对方没有待处理的拜师申请' });
    if (Number(rel.mentor_id) !== userId) return res.status(400).json({ error: '只有被申请的师傅本人可以处理该申请' });
    if (mentorApplyExpired(rel.created_at, Date.now())) {
      await dbRun("UPDATE mentorships SET status = 'declined' WHERE id = ? AND status = 'pending'", [Number(rel.id)]);
      return res.status(409).json({ error: `申请已过期（超过 ${Math.round(MENTOR_APPLY_TTL_MS / 3600000)} 小时未处理），已自动作废` });
    }
    const [aU, mNameRow] = await Promise.all([
      dbGet("SELECT u.username, COALESCE(NULLIF(r.name, ''), u.username) AS name, r.realm_index, r.realm_level FROM users u LEFT JOIN rankings r ON r.user_id = u.id WHERE u.id = ?", [appId]),
      dbGet("SELECT COALESCE(NULLIF(r.name, ''), u.username) AS name FROM users u LEFT JOIN rankings r ON r.user_id = u.id WHERE u.id = ?", [userId]),
    ]);
    const aName = String(aU?.name || '').slice(0, 32);
    const mName = String(mNameRow?.name || '').slice(0, 32);
    if (action === 'decline') {
      const dn = await dbRun("UPDATE mentorships SET status = 'declined' WHERE id = ? AND status = 'pending'", [Number(rel.id)]);
      if (!dn.changes) return res.status(409).json({ error: '该申请已被处理，请刷新' });
      // declined 不进 7 天冷却（冷却只认 expired），申请人可立刻改投他人
      insertMail(appId, '拜师申请被婉拒',
        `很遗憾，「${mName}」婉拒了你的拜师申请。\n\n· 婉拒不进冷却，你现在就可以在师徒页签改投其他师傅\n· 仙路广阔，总有投缘的师门`,
        'system', 0).catch((e: any) => console.error('mentor decide decline mail error:', e?.message || e));
      return res.json({ ok: true, apprentice: { id: appId, name: aName }, status: 'declined' });
    }
    // accept：申请门槛重验（境界/等级差——申请后 48h 内境界可能变动），失败给可读 409
    if (!aU || aU.realm_index == null) return res.status(409).json({ error: '对方角色档案缺失，无法收纳' });
    const myRank = await dbGet('SELECT realm_index, realm_level FROM rankings WHERE user_id = ?', [userId]);
    if (!myRank || !mentorRealmOk(myRank.realm_index)) return res.status(409).json({ error: '你的境界未达筑基期，尚不可收徒' });
    if (!mentorGapOk(mentorLevelOf(aU.realm_index, aU.realm_level), mentorLevelOf(myRank.realm_index, myRank.realm_level))) {
      return res.status(409).json({ error: `你的总等级须比对方高 ${MENTOR_LEVEL_GAP} 级（申请后条件已变化）` });
    }
    // 守卫式单语句 UPDATE：门下<3、双方非 7 天解除冷却，全部原子重验（并发双审批只一方 changes=1）
    const now = Date.now();
    const coolSince = now - MENTOR_EXPIRE_COOLDOWN_MS;
    const up = await dbRun(
      `UPDATE mentorships SET status = 'active'
       WHERE id = ? AND status = 'pending'
         AND (SELECT COUNT(*) FROM mentorships WHERE mentor_id = ? AND status = 'active') < ?
         AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))
         AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))`,
      [Number(rel.id), userId, MENTOR_MAX_APPRENTICES, coolSince, userId, userId, coolSince, appId, appId]
    );
    if (!up.changes) {
      // 失败逐项诊断（口径抄拜师失败诊断）
      const [cntRow, myCoolRow, tCoolRow] = await Promise.all([
        dbGet("SELECT COUNT(*) AS c FROM mentorships WHERE mentor_id = ? AND status = 'active'", [userId]),
        dbGet("SELECT 1 AS x FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?) LIMIT 1", [coolSince, userId, userId]),
        dbGet("SELECT 1 AS x FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?) LIMIT 1", [coolSince, appId, appId]),
      ]);
      let msg = '收纳未成，条件有变，请刷新重试';
      if (Number(cntRow?.c) >= MENTOR_MAX_APPRENTICES) msg = `门下弟子已满（${MENTOR_MAX_APPRENTICES}/${MENTOR_MAX_APPRENTICES}），无法再收`;
      else if (myCoolRow) msg = '你刚解除师徒关系，冷却中（7 天）';
      else if (tCoolRow) msg = '对方刚解除师徒关系，冷却中（7 天）';
      return res.status(409).json({ error: msg });
    }
    insertMail(appId, '拜师成功',
      `「${mName}」已收纳你为徒，师徒关系即刻生效。\n\n· 师徒同行（双方在线）时，你的服务端结算收益 +${Math.round((MENTOR_BONUS_MULT - 1) * 100)}%\n· 师傅将抽成你收益的 ${MENTOR_TAX_RATE * 100}%（师傅入账）\n· 修至金丹期后可在师徒页出师\n\n尊师重道，修行有道。`,
      'system', 0).catch((e: any) => console.error('mentor decide accept mail(a) error:', e?.message || e));
    insertMail(userId, '新徒入门',
      `你已收纳「${aName}」为徒。\n\n· 徒弟收益的 ${MENTOR_TAX_RATE * 100}%（修为/灵石）将自动奉上\n· 师徒同行（双方在线）时，徒弟服务端结算收益 +${Math.round((MENTOR_BONUS_MULT - 1) * 100)}%\n· 徒弟金丹期出师时：你将获得其拜师以来累计灵石收益 ${MENTOR_GRAD_RATE * 100}% 的出师回馈 + 7 天 ×${MENTOR_BUFF_MULT} 收益增益 + 称号「良师益友」`,
      'system', 0).catch((e: any) => console.error('mentor decide accept mail(m) error:', e?.message || e));
    res.json({ ok: true, apprentice: { id: appId, name: aName, realmIndex: aU.realm_index == null ? null : Number(aU.realm_index), realmLevel: aU.realm_level == null ? null : Number(aU.realm_level) }, status: 'active' });
  } catch (e: any) { console.error('mentor decide error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// POST /api/mentor/cancel — 徒弟撤回自己的待处理拜师申请（0.8.7 新增 N2）。
// 撤回=置 declined：不进 7 天冷却、部分唯一索引位随即释放，可立刻改投他人。
app.post('/api/mentor/cancel', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `mentor:bind:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const up = await dbRun("UPDATE mentorships SET status = 'declined' WHERE apprentice_id = ? AND status = 'pending'", [userId]);
    if (!up.changes) return res.status(409).json({ error: '没有待处理的拜师申请' });
    res.json({ ok: true });
  } catch (e: any) { console.error('mentor cancel error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// POST /api/mentor/graduate {apprenticeId?} — 出师：徒弟本人调用，或师傅指定徒弟。
// 门槛=徒弟境界≥金丹期；守卫式单语句 UPDATE（active→completed + 增益截止），并发双点只一方生效；
// 回馈=徒弟拜师日以来累计灵石收益（stats_daily 同源）×30% 随邮件发放；发信失败回滚出师可重试
app.post('/api/mentor/graduate', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `mentor:grad:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    let rel = await dbGet("SELECT id, mentor_id, apprentice_id, created_at FROM mentorships WHERE apprentice_id = ? AND status = 'active' LIMIT 1", [userId]);
    if (!rel) {
      const appId = Math.floor(asNum(req.body?.apprenticeId));
      if (Number.isInteger(appId) && appId > 0) {
        rel = await dbGet("SELECT id, mentor_id, apprentice_id, created_at FROM mentorships WHERE mentor_id = ? AND apprentice_id = ? AND status = 'active' LIMIT 1", [userId, appId]);
      }
    }
    if (!rel) return res.status(404).json({ error: '没有在门的师徒关系' });
    const mentorId = Number(rel.mentor_id);
    const apprenticeId = Number(rel.apprentice_id);
    const appRank = await dbGet('SELECT realm_index FROM rankings WHERE user_id = ?', [apprenticeId]);
    if (!mentorGradOk(appRank?.realm_index)) return res.status(409).json({ error: '徒弟境界未达金丹期，尚未可出师' });
    const now = Date.now();
    const up = await dbRun(
      "UPDATE mentorships SET status = 'completed', graduated_at = ?, mentor_buff_until = ? WHERE id = ? AND status = 'active'",
      [now, mentorGradBuffUntil(now), Number(rel.id)]
    );
    if (!up.changes) return res.status(409).json({ error: '该师徒关系已不在门（可能已出师或解除）' });
    let cumSilver = 0;
    try {
      const sum = await dbGet('SELECT COALESCE(SUM(silver_gain), 0) AS s FROM stats_daily WHERE player_id = ? AND date >= ?', [apprenticeId, bjDate(Number(rel.created_at))]);
      cumSilver = Math.max(0, Math.floor(Number(sum?.s) || 0));
    } catch { /* 统计缺失按 0 计 */ }
    const lump = mentorGradLump(cumSilver);
    const appRow = await dbGet("SELECT COALESCE(NULLIF(name, ''), username) AS name FROM rankings WHERE user_id = ?", [apprenticeId]);
    const appName = String(appRow?.name || '徒儿').slice(0, 32);
    try {
      await insertMail(mentorId, '徒儿出师',
        `「${appName}」已修至金丹，今日出师，青出于蓝！\n\n· 出师回馈：灵石 ×${lump}（其拜师以来累计灵石收益的 ${MENTOR_GRAD_RATE * 100}%，点击下方领取）\n· 出师增益：你的服务端结算收益 ×${MENTOR_BUFF_MULT}，持续 7 天\n· 称号「良师益友」已放入称号收藏\n\n桃李不言，下自成蹊。`,
        'system', lump);
    } catch (e: any) {
      console.error('mentor graduate mail error:', e?.message || e);
      // 补偿：回滚出师（可重试）；增益随之失效，称号在邮件成功后才授不留悬空
      await dbRun("UPDATE mentorships SET status = 'active', graduated_at = NULL, mentor_buff_until = NULL WHERE id = ?", [Number(rel.id)]).catch(() => {});
      return res.status(500).json({ error: '发奖失败，请重试' });
    }
    grantTitleBySource(mentorId, 'mentor_grad').catch((e: any) => console.error('mentor grad title error:', e?.message || e));
    // 0.8.7 徒弟出师贺礼（《数值表-T7T8》T8-8）：floor(贺礼基数 × realmMultOf(徒弟))，见 [mentorcore] 常量区。
    // 频控=每徒弟每日限 1 笔（T8-9）：当日已有 completed 行（不含本次）→ 贺礼置 0，出师本身不受影响。
    // 发信失败仅日志不回滚出师（小额礼按金额分级缩小补偿面；师傅侧大额回馈的回滚保护维持原样）。
    let gift = mentorGradGift(await realmMultOf(apprenticeId));
    try {
      const dupGift: any = await dbGet(
        "SELECT COUNT(*) AS c FROM mentorships WHERE apprentice_id = ? AND status = 'completed' AND graduated_at IS NOT NULL AND graduated_at >= ? AND id != ?",
        [apprenticeId, utcDayStartMs(), Number(rel.id)]
      );
      if (Number(dupGift?.c) >= 1) gift = 0;
    } catch { /* 频控查询异常不影响出师 */ }
    insertMail(apprenticeId, '出师',
      `恭喜道友修至金丹，今日出师，自立门户！\n\n师恩已报于传承之中：师傅获得了你拜师以来累计收益的 ${MENTOR_GRAD_RATE * 100}% 作为出师回馈。\n\n${gift > 0 ? `另奉上出师贺礼 灵石 ×${gift}（每徒弟每日至多一份），点击下方领取。\n\n` : ''}愿仙路漫漫，各自精进，他日江湖再见。`,
      'system', gift).catch((e: any) => console.error('mentor graduate mail(app) error:', e?.message || e));
    res.json({ ok: true, lumpStones: lump, buffUntil: mentorGradBuffUntil(now) });
  } catch (e: any) {
    console.error('mentor graduate error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/mentor/expire {apprenticeId?} — 解除关系：徒弟本人，或师傅指定徒弟。
// 守卫式单语句 UPDATE（active→expired + ended_at），并发双点只一方生效；双方各得 7 天冷却（系统邮件告知）
app.post('/api/mentor/expire', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `mentor:expire:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    let rel = await dbGet("SELECT id, mentor_id, apprentice_id FROM mentorships WHERE apprentice_id = ? AND status = 'active' LIMIT 1", [userId]);
    if (!rel) {
      const appId = Math.floor(asNum(req.body?.apprenticeId));
      if (Number.isInteger(appId) && appId > 0) {
        rel = await dbGet("SELECT id, mentor_id, apprentice_id FROM mentorships WHERE mentor_id = ? AND apprentice_id = ? AND status = 'active' LIMIT 1", [userId, appId]);
      }
    }
    if (!rel) return res.status(404).json({ error: '没有可解除的师徒关系' });
    const now = Date.now();
    const up = await dbRun("UPDATE mentorships SET status = 'expired', ended_at = ? WHERE id = ? AND status = 'active'", [now, Number(rel.id)]);
    if (!up.changes) return res.status(409).json({ error: '该师徒关系已不在门' });
    const cooldownUntil = mentorCoolingUntil(now);
    const line = '师徒关系已解除。\n\n· 双方 7 天内不可再缔结新的师徒关系（冷却中）\n· 好聚好散，仙路再会。';
    insertMail(Number(rel.mentor_id), '师徒缘尽', line, 'system', 0).catch((e: any) => console.error('mentor expire mail(m) error:', e?.message || e));
    insertMail(Number(rel.apprentice_id), '师徒缘尽', line, 'system', 0).catch((e: any) => console.error('mentor expire mail(a) error:', e?.message || e));
    res.json({ ok: true, cooldownUntil });
  } catch (e: any) {
    console.error('mentor expire error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// GET /api/mentor/search?name= — 拜师搜索（账号名/角色名模糊 LIKE，% _ 转义防通配注入；≤10 条有界）。
// 附按我方境界的可拜判定（对方境界≥筑基 + 总等级差 +5），只读不落库
app.get('/api/mentor/search', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `mentor:search:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const q = mentorSearchName(req.query.name);
    if (!q) return res.status(400).json({ error: '请输入 1-16 字的玩家名' });
    const like = '%' + mentorLikeEscape(q) + '%';
    const [meRow, rows] = await Promise.all([
      dbGet('SELECT realm_index, realm_level FROM rankings WHERE user_id = ?', [userId]),
      dbAll(
        `SELECT u.id, COALESCE(NULLIF(r.name, ''), u.username) AS name, r.realm_index, r.realm_level,
           (SELECT COUNT(*) FROM mentorships ms WHERE ms.mentor_id = u.id AND ms.status = 'active') AS apprentice_count
         FROM users u LEFT JOIN rankings r ON r.user_id = u.id
         WHERE u.id != ? AND (u.username LIKE ? ESCAPE '\\' OR r.name LIKE ? ESCAPE '\\')
         ORDER BY CASE WHEN r.realm_index IS NULL THEN -1 ELSE r.realm_index END DESC, r.realm_level DESC
         LIMIT 10`,
        [userId, like, like]
      ),
    ]);
    const myLevel = meRow ? mentorLevelOf(meRow.realm_index, meRow.realm_level) : 0;
    const rn = (i: unknown) => (Number.isInteger(Number(i)) && Number(i) >= 0 ? REALM_ORDER_FOR_RANKING[Number(i)] || '' : '');
    res.json({
      now: Date.now(),
      myLevel,
      candidates: (rows || []).map((r) => {
        const realmOk = mentorRealmOk(r.realm_index);
        const gapOk = mentorGapOk(myLevel, mentorLevelOf(r.realm_index, r.realm_level));
        return {
          id: Number(r.id),
          name: String(r.name || ''),
          realmIndex: r.realm_index == null ? null : Number(r.realm_index),
          realmName: r.realm_index == null ? '尚未入世' : rn(r.realm_index),
          realmLevel: r.realm_level == null ? null : Number(r.realm_level),
          level: r.realm_index == null ? null : mentorLevelOf(r.realm_index, r.realm_level),
          apprenticeCount: Math.max(0, Math.floor(Number(r.apprentice_count) || 0)),
          full: Math.max(0, Math.floor(Number(r.apprentice_count) || 0)) >= MENTOR_MAX_APPRENTICES,
          eligible: r.realm_index != null && realmOk && gapOk,
          reason: r.realm_index == null ? '对方尚未踏入仙途（无角色存档）' : (!realmOk ? '境界未达筑基期' : (!gapOk ? `总等级须比你高 ${MENTOR_LEVEL_GAP} 级` : '')),
        };
      }),
    });
  } catch (e: any) {
    console.error('mentor search error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// 批2 社交三件 API（伴生页 /yl/apps/friends/）：好友互赠 / 结拜金兰 / 道侣
// 口径：好友=双向两行式（上限 50）；赠丹=每人每日赠 5 次，赠者 +20 灵石，受者邮件收
// 白70/蓝25/紫5%（50/120/400 灵石，紫丹江湖志播报）；结拜=2-5 人互为好友、不得互为
// 师徒/道侣、每日义气酒全组发灵石并累积羁绊；道侣=propose 托管 5200 灵石、accept 成婚、
// 每日比翼双修双方各得修为+灵石。全程服务端账（updatePlayerSave/insertMail），不经客户端 JSON。
// ─────────────────────────────────────────────────────────
const FRIEND_MAX = 50;
const FRIEND_GIFT_PER_DAY = 5;
const GIFT_SEND_BONUS = 20;
const GIFT_STONES: Record<string, number> = { white: 50, blue: 120, purple: 400 };
const SWORN_MIN = 2, SWORN_MAX = 5;
const SWORN_CHEER_BASE = 500, SWORN_BOND_STEP = 1000, SWORN_CHEER_BOND = 10;
const COUPLE_PROPOSE_STONES = 52000;
const COUPLE_MIN_LEVEL = 30;
const FEAST_COST = 20000;                             // 喜宴开席成本：双方各扣（托管式全拒不部分扣；物价×10）
const FEAST_GIFT = 1000;                              // 赴宴回礼：两位新人各得（基数，实际再乘 1.5^境界）
const FEAST_GUEST_BASE = 500;                         // 宾客喜糖保底
const FEAST_GUEST_MIN = 1000, FEAST_GUEST_MAX = 10000; // 宾客随机喜糖闭区间 [1000,10000]
const FEAST_DURATION_MS = 24 * 60 * 60 * 1000;        // 席期 24 小时

const utcDateStr = (): string => new Date().toISOString().slice(0, 10);
// T9 0.8.8 L=甲：日切统一北京 0 点（原为 UTC 0 点，与 daily_quests/stats_daily 的 bjDate 口径不一致，
//   导致擂台「今日下战书上限」在北京 08:00 而非 0 点复位）。语义改为「北京当日 0 点」。
const utcDayStartMs = (): number => {
  const bj = Date.parse(bjDate(Date.now()) + 'T00:00:00+08:00');
  return Number.isFinite(bj) ? bj : ((): number => { const d = new Date(); d.setUTCHours(0, 0, 0, 0); return d.getTime(); })();
};

// 按玩家名（rankings.name 优先，退 users.username，精确匹配）找用户
async function findUserByName(nameRaw: unknown): Promise<{ id: number; name: string } | null> {
  const name = asStr(nameRaw).trim().slice(0, 32);
  if (!name) return null;
  const r = await dbGet(
    `SELECT u.id AS id, COALESCE(NULLIF(rg.name, ''), u.username) AS name
     FROM users u LEFT JOIN rankings rg ON rg.user_id = u.id
     WHERE COALESCE(NULLIF(rg.name, ''), u.username) = ? LIMIT 1`, [name]);
  if (r) return { id: Number(r.id), name: String(r.name) };
  const u = await dbGet('SELECT id, username AS name FROM users WHERE username = ? LIMIT 1', [name]);
  return u ? { id: Number(u.id), name: String(u.name) } : null;
}

// ── 0.8.9 [reward089] 灵石境界倍率统一（与客户端 YLRF / YLRewardFactor 同源同曲线）──
// 客户端面板与打坐口径：idx<=0 -> 4/3（镜像 max(1,q) 地板），idx>=1 -> 2*idx+1。
// 服务端过去 6 处各自内联 Math.pow(1.5, idx)（指数曲线），与客户端线性曲线并存 => 面板与到账对不上。
// 本函数是服务端**唯一**的灵石境界倍率来源；后续新增灵石发放点一律调用它。
// 定义位置必须在 sameRealmMult / realmMultOf 之前（两处调用方）。
function realmStoneFactor(realmIdx: unknown): number {
  const i = Math.floor(Number(realmIdx));
  if (!Number.isFinite(i) || i < 0) return 4 / 3;   // 缺档/脏数据按炼气期地板，绝不 NaN
  if (i <= 0) return 4 / 3;
  return 2 * i + 1;
}
// 灵石发放（纯）：floor(基数 × 境界倍率)，负值/NaN 钳 0。发放点与面板同式，玩家可反推。
function realmStoneGain(base: unknown, realmIdx: unknown): number {
  return Math.max(0, Math.floor((Number(base) || 0) * realmStoneFactor(realmIdx)));
}

// 总等级（rankings 口径 境界序×9+层数）；无档返回 null
async function totalLevelOf(userId: number): Promise<number | null> {
  const r = await dbGet('SELECT realm_index, realm_level FROM rankings WHERE user_id = ?', [userId]);
  if (!r || r.realm_index == null) return null;
  return Number(r.realm_index) * 9 + Number(r.realm_level || 1);
}

function sameRealmMult(realm: unknown): number {
  const idx = Math.max(0, ECON_REALM_ORDER.indexOf(String(realm || '')));
  // 0.8.9 [reward089] 本函数是赴宴回礼的**独立第三套**境界倍率（既不走 realmMultOf 也不走客户端曲线），
  // 一并收口到统一线性曲线，避免「同一境界三种倍率」。
  return realmStoneFactor(idx);
}

function isFriend(a: number, b: number): Promise<boolean> {
  return dbGet('SELECT 1 AS x FROM friendships WHERE user_id = ? AND friend_id = ? LIMIT 1', [a, b])
    .then((r: any) => !!r).catch(() => false);
}

// ── 好友 ──
app.post('/api/friends/add', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 15, keyFn: (req: any) => `fr:add:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const t = await findUserByName(req.body?.name);
    if (!t) return res.status(404).json({ error: '查无此道友' });
    if (t.id === userId) return res.status(400).json({ error: '不能加自己为好友' });
    if (await isFriend(userId, t.id)) return res.status(409).json({ error: '你们已是好友' });
    const cnt = await dbGet('SELECT COUNT(*) AS c FROM friendships WHERE user_id = ?', [userId]);
    if (Number(cnt?.c) >= FRIEND_MAX) return res.status(409).json({ error: `好友已满（${FRIEND_MAX}）` });
    await dbRun('INSERT OR IGNORE INTO friendships (user_id, friend_id, created_at) VALUES (?, ?, ?)', [userId, t.id, Date.now()]);
    await dbRun('INSERT OR IGNORE INTO friendships (user_id, friend_id, created_at) VALUES (?, ?, ?)', [t.id, userId, Date.now()]);
    insertMail(t.id, '新好友', `道友「${String(req.user.username || '').slice(0, 32)}」与你结为好友。每日可互赠丹药（赠出得灵石，收丹看人品）。`, 'system', 0).catch(() => {});
    res.json({ ok: true, friend: t });
  } catch (e: any) { console.error('friends add error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/friends/remove', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 15, keyFn: (req: any) => `fr:rm:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const fid = Math.floor(asNum(req.body?.friendId));
    if (!Number.isInteger(fid) || fid <= 0) return res.status(400).json({ error: '参数非法' });
    await dbRun('DELETE FROM friendships WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)', [userId, fid, fid, userId]);
    res.json({ ok: true });
  } catch (e: any) { console.error('friends rm error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.get('/api/friends/list', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `fr:list:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const rows = await dbAll(
      `SELECT f.friend_id AS id, u.username AS uname, COALESCE(NULLIF(r.name, ''), u.username) AS name,
              r.realm_index, r.realm_level, r.combat_power
       FROM friendships f
       JOIN users u ON u.id = f.friend_id
       LEFT JOIN rankings r ON r.user_id = f.friend_id
       WHERE f.user_id = ? ORDER BY f.created_at DESC LIMIT ?`, [userId, FRIEND_MAX]);
    const dayStart = utcDayStartMs();
    const sent = await dbAll('SELECT receiver_id FROM friend_gifts WHERE sender_id = ? AND created_at >= ?', [userId, dayStart]);
    const sentSet = new Set((sent || []).map((x: any) => Number(x.receiver_id)));
    res.json({
      now: Date.now(),
      max: FRIEND_MAX,
      giftsLeftToday: Math.max(0, FRIEND_GIFT_PER_DAY - sentSet.size),
      friends: (rows || []).map((r: any) => ({
        id: Number(r.id),
        name: String(r.name || r.uname || ''),
        realmIndex: r.realm_index == null ? null : Number(r.realm_index),
        realmName: r.realm_index == null ? '尚未入世' : (REALM_ORDER_FOR_RANKING[Number(r.realm_index)] || ''),
        level: r.realm_index == null ? null : Number(r.realm_index) * 9 + Number(r.realm_level || 1),
        combatPower: r.combat_power == null ? null : Number(r.combat_power),
        giftedToday: sentSet.has(Number(r.id)),
      })),
    });
  } catch (e: any) { console.error('friends list error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/friends/gift', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `fr:gift:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const fid = Math.floor(asNum(req.body?.friendId));
    if (!Number.isInteger(fid) || fid <= 0) return res.status(400).json({ error: '参数非法' });
    if (!(await isFriend(userId, fid))) return res.status(409).json({ error: '先加好友再赠丹' });
    const sent = await dbGet('SELECT COUNT(*) AS c FROM friend_gifts WHERE sender_id = ? AND created_at >= ?', [userId, utcDayStartMs()]);
    if (Number(sent?.c) >= FRIEND_GIFT_PER_DAY) return res.status(409).json({ error: `今日已赠 ${FRIEND_GIFT_PER_DAY} 次，明日再来` });
    const roll = Math.random();
    const quality = roll < 0.025 ? 'purple' : roll < 0.15 ? 'blue' : 'white';
    const stones = GIFT_STONES[quality];
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      sd.player.spiritStones = b + GIFT_SEND_BONUS;
    });
    if (!paid.ok) return res.status(500).json({ error: paid.error || '入账失败' });
    await dbRun('INSERT INTO friend_gifts (sender_id, receiver_id, quality, stones, created_at) VALUES (?, ?, ?, ?, ?)', [userId, fid, quality, stones, Date.now()]);
    const senderName = String(req.user.username || '道友').slice(0, 32);
    const qn = quality === 'purple' ? '紫品灵丹' : quality === 'blue' ? '蓝品灵丹' : '白品灵丹';
    insertMail(fid, '好友赠丹', `道友「${senderName}」赠你一枚${qn}，灵石 ×${stones} 已随信附上。\n\n礼尚往来：去好友页回赠可各得灵石。`, 'system', stones)
      .then(() => {
        if (quality === 'purple') logChronicle(fid, senderName, `【紫丹赠友】「${senderName}」炼得紫品灵丹赠予好友，福缘深厚，全服称羡`);
      }).catch(() => {});
    res.json({ ok: true, quality, stones, sendBonus: GIFT_SEND_BONUS });
  } catch (e: any) { console.error('friends gift error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// ── 结拜金兰 ──
async function swornOf(userId: number): Promise<any> {
  return dbGet(
    `SELECT g.id, g.name, g.bond, g.creator_id, g.created_at
     FROM sworn_members m JOIN sworn_groups g ON g.id = m.group_id
     WHERE m.user_id = ? AND g.disbanded = 0 LIMIT 1`, [userId]);
}

app.get('/api/sworn/my', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `sw:my:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const g = await swornOf(userId);
    if (!g) return res.json({ now: Date.now(), group: null, rules: { min: SWORN_MIN, max: SWORN_MAX, cheerBase: SWORN_CHEER_BASE, bondStep: SWORN_BOND_STEP } });
    const members = await dbAll(
      `SELECT m.user_id AS id, u.username AS uname, COALESCE(NULLIF(r.name, ''), u.username) AS name,
              m.last_cheer_date, r.realm_index
       FROM sworn_members m JOIN users u ON u.id = m.user_id LEFT JOIN rankings r ON r.user_id = m.user_id
       WHERE m.group_id = ? ORDER BY m.joined_at`, [g.id]);
    const today = utcDateStr();
    res.json({
      now: Date.now(),
      group: {
        id: Number(g.id), name: String(g.name), bond: Number(g.bond),
        isCreator: Number(g.creator_id) === userId,
        bonusPct: Math.min(5, Math.floor(Number(g.bond) / SWORN_BOND_STEP)),
        members: (members || []).map((m: any) => ({
          id: Number(m.id), name: String(m.name || m.uname || ''),
          cheeredToday: m.last_cheer_date === today,
        })),
      },
      rules: { min: SWORN_MIN, max: SWORN_MAX, cheerBase: SWORN_CHEER_BASE, bondStep: SWORN_BOND_STEP },
    });
  } catch (e: any) { console.error('sworn my error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// 守卫：两人不得互为师徒（任一方向 active）或道侣（pending/married）
async function areBounded(a: number, b: number): Promise<string | null> {
  const mt = await dbGet("SELECT 1 AS x FROM mentorships WHERE status = 'active' AND ((mentor_id = ? AND apprentice_id = ?) OR (mentor_id = ? AND apprentice_id = ?)) LIMIT 1", [a, b, b, a]);
  if (mt) return '师徒';
  const cp = await dbGet("SELECT 1 AS x FROM couples WHERE status IN ('pending','married') AND ((user_a = ? AND user_b = ?) OR (user_a = ? AND user_b = ?)) LIMIT 1", [a, b, b, a]);
  if (cp) return '道侣';
  return null;
}

app.post('/api/sworn/create', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => `sw:cr:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    if (await swornOf(userId)) return res.status(409).json({ error: '你已在结义之中' });
    const name = asStr(req.body?.name).trim().slice(0, 12);
    if (!name) return res.status(400).json({ error: '请取一个结义名号（≤12 字）' });
    const ids = Array.from(new Set([userId, ...((Array.isArray(req.body?.memberIds) ? req.body.memberIds : []).map((x: any) => Math.floor(Number(x))).filter((x: number) => Number.isInteger(x) && x > 0))]));
    if (ids.length < SWORN_MIN || ids.length > SWORN_MAX) return res.status(400).json({ error: `结义人数须 ${SWORN_MIN}-${SWORN_MAX} 人` });
    for (const uid of ids) {
      if (await swornOf(uid)) return res.status(409).json({ error: `有人已在其他结义之中` });
    }
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
      if (!(await isFriend(ids[i], ids[j]))) return res.status(409).json({ error: '结义须全员互为好友（先互相加好友）' });
      const bound = await areBounded(ids[i], ids[j]);
      if (bound) return res.status(409).json({ error: `结义成员不得互为${bound}` });
    }
    const g = await dbRun('INSERT INTO sworn_groups (name, creator_id, created_at) VALUES (?, ?, ?)', [name, userId, Date.now()]);
    const gid = Number(g.lastID);
    for (const uid of ids) await dbRun('INSERT OR IGNORE INTO sworn_members (group_id, user_id, joined_at) VALUES (?, ?, ?)', [gid, uid, Date.now()]);
    // 全员称号「义结金兰」（一次性，幂等）
    for (const uid of ids) {
      grantTitleBySource(uid, 'sworn').catch(() => {});
    }
    logChronicle(userId, name, `【义结金兰】「${name}」歃血为盟，${ids.length} 人结为异姓兄妹，江湖传为佳话`);
    res.json({ ok: true, groupId: gid, size: ids.length });
  } catch (e: any) { console.error('sworn create error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/sworn/invite', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `sw:inv:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const g = await swornOf(userId);
    if (!g) return res.status(404).json({ error: '你不在任何结义之中' });
    const cnt = await dbGet('SELECT COUNT(*) AS c FROM sworn_members WHERE group_id = ?', [g.id]);
    if (Number(cnt?.c) >= SWORN_MAX) return res.status(409).json({ error: `结义已满（${SWORN_MAX} 人）` });
    const t = await findUserByName(req.body?.name);
    if (!t) return res.status(404).json({ error: '查无此道友' });
    if (await swornOf(t.id)) return res.status(409).json({ error: '对方已在结义之中' });
    for (const row of await dbAll('SELECT user_id FROM sworn_members WHERE group_id = ?', [g.id])) {
      if (!(await isFriend(Number(row.user_id), t.id))) return res.status(409).json({ error: '新成员须与全员互为好友' });
      const bound = await areBounded(Number(row.user_id), t.id);
      if (bound) return res.status(409).json({ error: `不得与结义成员互为${bound}` });
    }
    await dbRun('INSERT OR IGNORE INTO sworn_members (group_id, user_id, joined_at) VALUES (?, ?, ?)', [g.id, t.id, Date.now()]);
    grantTitleBySource(t.id, 'sworn').catch(() => {});
    insertMail(t.id, '义结金兰', `你已加入结义「${String(g.name).slice(0, 12)}」。每日义气酒：到结拜页共饮，全组得灵石。`, 'system', 0).catch(() => {});
    res.json({ ok: true, added: t });
  } catch (e: any) { console.error('sworn invite error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/sworn/leave', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => `sw:lv:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const g = await swornOf(userId);
    if (!g) return res.status(404).json({ error: '你不在任何结义之中' });
    await dbRun('DELETE FROM sworn_members WHERE group_id = ? AND user_id = ?', [g.id, userId]);
    const cnt = await dbGet('SELECT COUNT(*) AS c FROM sworn_members WHERE group_id = ?', [g.id]);
    if (Number(cnt?.c) < SWORN_MIN) {
      await dbRun('UPDATE sworn_groups SET disbanded = 1 WHERE id = ?', [g.id]);
      logChronicle(userId, String(g.name).slice(0, 12), `【金兰散】结义「${String(g.name).slice(0, 12)}」人各自散，江湖再无故人`);
    }
    res.json({ ok: true, disbanded: Number(cnt?.c) < SWORN_MIN });
  } catch (e: any) { console.error('sworn leave error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// 义气酒：每日每人 1 次，全组在线成员各得灵石，羁绊 +10
app.post('/api/sworn/cheer', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `sw:cheer:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const g = await swornOf(userId);
    if (!g) return res.status(404).json({ error: '你不在任何结义之中' });
    const today = utcDateStr();
    const mine = await dbGet('SELECT last_cheer_date FROM sworn_members WHERE group_id = ? AND user_id = ?', [g.id, userId]);
    if (mine && mine.last_cheer_date === today) return res.status(409).json({ error: '今日已共饮义气酒，明早再来' });
    await dbRun('UPDATE sworn_members SET last_cheer_date = ? WHERE group_id = ? AND user_id = ?', [today, g.id, userId]);
    await dbRun('UPDATE sworn_groups SET bond = bond + ? WHERE id = ?', [SWORN_CHEER_BOND, g.id]);
    const bondNow = Number((await dbGet('SELECT bond FROM sworn_groups WHERE id = ?', [g.id]))?.bond || 0);
    const per = SWORN_CHEER_BASE + Math.floor(bondNow / SWORN_BOND_STEP) * 20;
    const members = await dbAll('SELECT user_id FROM sworn_members WHERE group_id = ?', [g.id]);
    let paid = 0;
    for (const m of members || []) {
      const r = await updatePlayerSave(Number(m.user_id), (sd: any) => {
        sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + per;
      });
      if (r.ok) paid++;
    }
    res.json({ ok: true, bond: bondNow, perStones: per, paid, bonusPct: Math.min(5, Math.floor(bondNow / SWORN_BOND_STEP)) });
  } catch (e: any) { console.error('sworn cheer error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// ── 道侣 ──
async function activeCouple(userId: number): Promise<any> {
  return dbGet(
    "SELECT * FROM couples WHERE status IN ('pending','married') AND (user_a = ? OR user_b = ?) LIMIT 1", [userId, userId]);
}

app.get('/api/couple/my', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `cp:my:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const c = await activeCouple(userId);
    if (!c) return res.json({ now: Date.now(), couple: null, rules: { proposeStones: COUPLE_PROPOSE_STONES, minLevel: COUPLE_MIN_LEVEL } });
    const otherId = Number(c.user_a) === userId ? Number(c.user_b) : Number(c.user_a);
    const other = await dbGet(
      `SELECT u.username AS uname, COALESCE(NULLIF(r.name, ''), u.username) AS name, r.realm_index
       FROM users u LEFT JOIN rankings r ON r.user_id = u.id WHERE u.id = ?`, [otherId]);
    const today = utcDateStr();
    res.json({
      now: Date.now(),
      couple: {
        id: Number(c.id),
        status: String(c.status),
        isProposer: Number(c.user_a) === userId,
        other: { id: otherId, name: String(other?.name || other?.uname || '') },
        marriedAt: c.married_at,
        birdsToday: c.last_birds_date === today,
        proposeStones: COUPLE_PROPOSE_STONES,
      },
      rules: { proposeStones: COUPLE_PROPOSE_STONES, minLevel: COUPLE_MIN_LEVEL },
    });
  } catch (e: any) { console.error('couple my error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/couple/propose', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => `cp:pr:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    if (await activeCouple(userId)) return res.status(409).json({ error: '你已有婚约或道侣' });
    const t = await findUserByName(req.body?.name);
    if (!t) return res.status(404).json({ error: '查无此道友' });
    if (t.id === userId) return res.status(400).json({ error: '不能向自己求婚' });
    if (await activeCouple(t.id)) return res.status(409).json({ error: '对方已有婚约或道侣' });
    if (!(await isFriend(userId, t.id))) return res.status(409).json({ error: '须先结为好友方可求婚' });
    const bound = await areBounded(userId, t.id);
    if (bound) return res.status(409).json({ error: `不得与${bound}结为道侣` });
    const myLv = await totalLevelOf(userId), tLv = await totalLevelOf(t.id);
    if (myLv == null || myLv < COUPLE_MIN_LEVEL) return res.status(409).json({ error: `你的总等级须 ≥ ${COUPLE_MIN_LEVEL}` });
    if (tLv == null || tLv < COUPLE_MIN_LEVEL) return res.status(409).json({ error: `对方总等级须 ≥ ${COUPLE_MIN_LEVEL}` });
    // 托管聘礼（decline 退全款，与悬赏同口径）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < COUPLE_PROPOSE_STONES) { short = true; return; }
      sd.player.spiritStones = b - COUPLE_PROPOSE_STONES;
    });
    if (!paid.ok || short) return res.status(409).json({ error: `灵石不足：聘礼需托管 ${COUPLE_PROPOSE_STONES}` });
    const c = await dbRun('INSERT INTO couples (user_a, user_b, status, created_at) VALUES (?, ?, ?, ?)', [userId, t.id, 'pending', Date.now()]);
    insertMail(t.id, '道侣求婚', `道友「${String(req.user.username || '').slice(0, 32)}」以 ${COUPLE_PROPOSE_STONES} 灵石为聘，向你求婚。\n\n到道侣页应允即结为道侣（每日比翼双修，双方各得修为与灵石）；婉拒则聘礼原路退回。`, 'system', 0).catch(() => {});
    res.json({ ok: true, coupleId: Number(c.lastID) });
  } catch (e: any) { console.error('couple propose error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/couple/accept', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => `cp:ac:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const c = await dbGet("SELECT * FROM couples WHERE user_b = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", [userId]);
    if (!c) return res.status(404).json({ error: '没有待应允的求婚' });
    await dbRun("UPDATE couples SET status = 'married', married_at = ? WHERE id = ? AND status = 'pending'", [Date.now(), c.id]);
    const proposer = await dbGet('SELECT username FROM users WHERE id = ?', [c.user_a]);
    const me = await dbGet('SELECT username FROM users WHERE id = ?', [userId]);
    const aName = String(proposer?.username || '').slice(0, 32), bName = String(me?.username || '').slice(0, 32);
    logChronicle(userId, aName, `【喜结连理】「${aName}」与「${bName}」结为道侣，三界同贺，月老祠前红绸满枝`);
    for (const uid of [Number(c.user_a), userId]) {
      insertMail(uid, '结为道侣', `三书六礼已成，你与道侣正式结发。每日可到道侣页行「比翼双修」，双方各得修为与灵石。`, 'system', 200).catch(() => {});
    }
    res.json({ ok: true });
  } catch (e: any) { console.error('couple accept error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/couple/decline', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => `cp:dc:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const c = await dbGet("SELECT * FROM couples WHERE user_b = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", [userId]);
    if (!c) return res.status(404).json({ error: '没有待应允的求婚' });
    await dbRun("UPDATE couples SET status = 'divorced', ended_at = ? WHERE id = ?", [Date.now(), c.id]);
    // 聘礼原路退回
    await updatePlayerSave(Number(c.user_a), (sd: any) => {
      sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + COUPLE_PROPOSE_STONES;
    });
    insertMail(Number(c.user_a), '求婚婉拒', `道友婉拒了你的求婚，聘礼 ${COUPLE_PROPOSE_STONES} 灵石已原路退回。道友有缘，来日方长。`, 'system', 0).catch(() => {});
    res.json({ ok: true, refunded: COUPLE_PROPOSE_STONES });
  } catch (e: any) { console.error('couple decline error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/couple/divorce', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => `cp:dv:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const c = await activeCouple(userId);
    if (!c) return res.status(404).json({ error: '你并无道侣' });
    // 简化口径：立即和离（设计稿 7 天冷静期对摸鱼小站过重，暂不设；聘礼不退）
    await dbRun("UPDATE couples SET status = 'divorced', ended_at = ? WHERE id = ?", [Date.now(), c.id]);
    const otherId = Number(c.user_a) === userId ? Number(c.user_b) : Number(c.user_a);
    for (const uid of [userId, otherId]) insertMail(uid, '和离书', '缘尽于此，各安前路。道侣关系已解除。', 'system', 0).catch(() => {});
    res.json({ ok: true });
  } catch (e: any) { console.error('couple divorce error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// 比翼双修：married 每日 1 次，双方各得修为+灵石（按最高境界 ×1.5^realm）
app.post('/api/couple/birds', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `cp:bd:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const c = await activeCouple(userId);
    if (!c || c.status !== 'married') return res.status(409).json({ error: '结为道侣后方可双修' });
    const today = utcDateStr();
    if (c.last_birds_date === today) return res.status(409).json({ error: '今日已双修，情比金坚不必贪多' });
    const otherId = Number(c.user_a) === userId ? Number(c.user_b) : Number(c.user_a);
    const mult = await dbGet(
      `SELECT MAX(COALESCE(r.realm_index, 0)) AS ri FROM rankings r WHERE r.user_id IN (?, ?)`, [userId, otherId]);
    const realmMult = Math.pow(1.5, Math.min(20, Math.max(0, Number(mult?.ri) || 0))); // 修为仍走 C2（不在本次口径内）
    const expGain = Math.floor(20000 * realmMult);
    // 0.8.9 [reward089] 灵石改走统一线性曲线（与客户端面板同源）
    const stoneGain = realmStoneGain(1000, mult?.ri);
    const results: any[] = [];
    for (const uid of [userId, otherId]) {
      const r = await updatePlayerSave(Number(uid), (sd: any) => {
        sd.player.exp = (Number(sd.player?.exp) || 0) + expGain;
        sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + stoneGain;
      });
      results.push({ uid: Number(uid), ok: !!r.ok });
    }
    await dbRun('UPDATE couples SET last_birds_date = ? WHERE id = ?', [today, c.id]);
    if (!results[1].ok) insertMail(otherId, '比翼双修', `道侣与你双修一轮，你得修为 ×${expGain}、灵石 ×${stoneGain}（已入档）。`, 'system', 0).catch(() => {});
    res.json({ ok: true, expGain, stoneGain, partnerCredited: results[1].ok });
  } catch (e: any) { console.error('couple birds error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// ── 道侣喜宴（设计稿 #13 婚礼仪式可服务端化子集）：开席双方各扣 2000（托管式全拒不部分扣），
// 席期 24h；任意玩家赴宴得 50+随机[100,1000] 喜糖，两位新人各得 100 回礼（updatePlayerSave）+报喜邮件；
// 每对道侣一生一席（UNIQUE couple_id），每人每席限赴一次（PK feast_id+user_id）
async function coupleNames(ua: number, ub: number): Promise<{ a: string; b: string }> {
  const rows = await dbAll(
    `SELECT u.id AS id, COALESCE(NULLIF(r.name, ''), u.username) AS name
     FROM users u LEFT JOIN rankings r ON r.user_id = u.id WHERE u.id IN (?, ?)`, [ua, ub]);
  const pick = (id: number) => String((rows || []).find((x: any) => Number(x.id) === id)?.name || `道友#${id}`).slice(0, 32);
  return { a: pick(ua), b: pick(ub) };
}

// POST /api/feast/open — married 道侣任一方开席：双方各扣 FEAST_COST，任一方不足即 409 且不部分扣
// （先 A 托管式扣、再 B 扣，B 不足/失败即回滚 A；INSERT 撞 UNIQUE(couple_id) 也全款退回）；席期 24h
app.post('/api/feast/open', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => `feast:open:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const c = await activeCouple(userId);
    if (!c || c.status !== 'married') return res.status(409).json({ error: '结为道侣后方可开席' });
    const existed = await dbGet('SELECT id FROM couple_feasts WHERE couple_id = ?', [Number(c.id)]);
    if (existed) return res.status(409).json({ error: '你们的喜宴已开过，一生一次' });
    let shortA = false, shortB = false;
    const pa = await updatePlayerSave(Number(c.user_a), (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < FEAST_COST) { shortA = true; return; }
      sd.player.spiritStones = b - FEAST_COST;
    });
    if (!pa.ok || shortA) return res.status(409).json({ error: `灵石不足：开席双方各需 ${FEAST_COST}` });
    const pb = await updatePlayerSave(Number(c.user_b), (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < FEAST_COST) { shortB = true; return; }
      sd.player.spiritStones = b - FEAST_COST;
    });
    if (!pb.ok || shortB) {
      // B 不足/失败：退回 A 已扣的部分，绝不部分成交
      await updatePlayerSave(Number(c.user_a), (sd: any) => {
        sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + FEAST_COST;
      });
      return res.status(409).json({ error: `道侣灵石不足：开席双方各需 ${FEAST_COST}` });
    }
    const now = Date.now();
    try {
      await dbRun('INSERT INTO couple_feasts (couple_id, created_at, expires_at) VALUES (?, ?, ?)', [Number(c.id), now, now + FEAST_DURATION_MS]);
    } catch (uniq: any) {
      // 并发双开撞 UNIQUE(couple_id)：全款退回双方
      for (const uid of [Number(c.user_a), Number(c.user_b)]) {
        await updatePlayerSave(uid, (sd: any) => {
          sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + FEAST_COST;
        });
      }
      return res.status(409).json({ error: '你们的喜宴已开过，一生一次' });
    }
    const names = await coupleNames(Number(c.user_a), Number(c.user_b));
    logChronicle(userId, names.a, `【喜宴开席】『${names.a}』与『${names.b}』大摆喜宴，全侠赴宴同贺`);
    res.json({ ok: true, coupleId: Number(c.id), expiresAt: now + FEAST_DURATION_MS, costEach: FEAST_COST });
  } catch (e: any) { console.error('feast open error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// POST /api/feast/attend {coupleId} — 赴宴：新人自己不赴自己的席（409）；须在席期内；
// 宾客得 50+randomInt[100,1000] 喜糖（无存档则删行补偿可重试），两位新人各得 100 回礼 + 报喜邮件（无附件防领取双算）
app.post('/api/feast/attend', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `feast:at:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  const coupleId = asInt(req.body?.coupleId);
  if (!coupleId) return res.status(400).json({ error: '需要 coupleId' });
  try {
    const c = await dbGet("SELECT * FROM couples WHERE id = ? AND status = 'married'", [coupleId]);
    if (!c) return res.status(404).json({ error: '查无此席' });
    if (Number(c.user_a) === userId || Number(c.user_b) === userId) return res.status(409).json({ error: '新人不赴自己的喜宴' });
    const f = await dbGet('SELECT * FROM couple_feasts WHERE couple_id = ?', [coupleId]);
    if (!f) return res.status(404).json({ error: '该道侣尚未开席' });
    const now = Date.now();
    if (now > Number(f.expires_at)) return res.status(409).json({ error: '喜宴已散席' });
    const stones = FEAST_GUEST_BASE + crypto.randomInt(FEAST_GUEST_MIN, FEAST_GUEST_MAX + 1);
    const ins = await dbRun('INSERT OR IGNORE INTO couple_feast_guests (feast_id, user_id, stones, created_at) VALUES (?, ?, ?, ?)', [Number(f.id), userId, stones, now]);
    if (!ins.changes) return res.status(409).json({ error: '你已赴过这场喜宴' });
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') sd.player = {};
      sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + stones;
    });
    if (!paid.ok) {
      // 宾客无存档等失败：删行补偿（可先进游戏建号再赴），喜糖不入账
      await dbRun('DELETE FROM couple_feast_guests WHERE feast_id = ? AND user_id = ?', [Number(f.id), userId]);
      return res.status(409).json({ error: paid.error === 'No save found' ? '请先进游戏创建角色后再赴宴' : (paid.error || '入账失败') });
    }
    const names = await coupleNames(Number(c.user_a), Number(c.user_b));
    const guestName = String(req.user.username || '').slice(0, 32);
    for (const [uid, other] of [[Number(c.user_a), names.b], [Number(c.user_b), names.a]] as [number, string][]) {
      await updatePlayerSave(uid, (sd: any) => {
        if (!sd.player || typeof sd.player !== 'object') sd.player = {};
        sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + realmStoneGain(FEAST_GIFT, ECON_REALM_ORDER.indexOf(String(sd.player.realm || ''))); // 0.8.9 [reward089] 统一口径
      });
      insertMail(uid, '喜宴报喜', `道友「${guestName}」赴了你与「${other}」的喜宴，同贺之喜回礼 ${FEAST_GIFT} 灵石已入你档。`, 'system', 0).catch(() => {});
    }
    res.json({ ok: true, stones, feastId: Number(f.id), expiresAt: Number(f.expires_at) });
  } catch (e: any) { console.error('feast attend error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// GET /api/feast/list — 进行中的喜宴（双方名字+剩余时间+已赴宴人数）+ 我赴过宴的席（含所得喜糖）
app.get('/api/feast/list', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `feast:ls:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const now = Date.now();
    const cols = `f.id AS fid, f.couple_id AS cid, f.created_at AS cat, f.expires_at AS eat,
      c.user_a AS ua, c.user_b AS ub,
      COALESCE(NULLIF(ra.name, ''), ua_u.username) AS aname,
      COALESCE(NULLIF(rb.name, ''), ub_u.username) AS bname,
      (SELECT COUNT(*) FROM couple_feast_guests gc WHERE gc.feast_id = f.id) AS guests`;
    const joins = `FROM couple_feasts f
      JOIN couples c ON c.id = f.couple_id
      LEFT JOIN users ua_u ON ua_u.id = c.user_a
      LEFT JOIN users ub_u ON ub_u.id = c.user_b
      LEFT JOIN rankings ra ON ra.user_id = c.user_a
      LEFT JOIN rankings rb ON rb.user_id = c.user_b`;
    const open = await dbAll(
      `SELECT ${cols} ${joins} WHERE c.status = 'married' AND f.expires_at > ? ORDER BY f.id DESC`, [now]);
    const mine = await dbAll(
      `SELECT ${cols}, g.stones AS my_stones, g.created_at AS my_at ${joins}
       JOIN couple_feast_guests g ON g.feast_id = f.id AND g.user_id = ?
       ORDER BY g.created_at DESC LIMIT 50`, [userId]);
    res.json({
      now,
      feasts: (open || []).map((r: any) => ({
        feastId: Number(r.fid),
        coupleId: Number(r.cid),
        a: { id: Number(r.ua), name: String(r.aname || '') },
        b: { id: Number(r.ub), name: String(r.bname || '') },
        createdAt: Number(r.cat),
        expiresAt: Number(r.eat),
        remainingMs: Math.max(0, Number(r.eat) - now),
        guests: Number(r.guests) || 0,
      })),
      mine: (mine || []).map((r: any) => ({
        feastId: Number(r.fid),
        coupleId: Number(r.cid),
        couple: `${String(r.aname || '')} 与 ${String(r.bname || '')}`,
        stones: Number(r.my_stones) || 0,
        attendedAt: Number(r.my_at),
        expiresAt: Number(r.eat),
        expired: Number(r.eat) <= now,
      })),
    });
  } catch (e: any) { console.error('feast list error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// ─────────────────────────────────────────────────────────
// 批3 API（伴生页 /yl/apps/arena/）：擂台切磋 / 恩怨仇杀 / 师徒传功
// 擂台：下战书→应战即异步结算（战力+随机 ±30%），胜者侠名+10 与灵石，败者自动入仇人名单；
// 恩怨：北京 19:00-22:00（UTC 11:00-14:00）可复仇，同仇人 24h 一次，雪耻播报；
// 传功：师傅每日 1 次，徒弟得修为 3 万×1.5^境界，师傅师德 +30。
// ─────────────────────────────────────────────────────────
const ARENA_DAILY_MAX = 3;
const ARENA_RENOWN_WIN = 10;
const ARENA_STONE_BASE = 3000;
const GRUDGE_STONE_BASE = 8000;
const GRUDGE_WINDOW_UTC = [11, 14]; // 北京 19-22 点
const GRUDGE_COOLDOWN_MS = 24 * 3600 * 1000;
const TEACH_EXP_BASE = 30000;
const TEACH_VIRTUE = 30;

function arenaCombat(of: any): number {
  const cp = Number(of && of.combat_power);
  return Number.isFinite(cp) && cp > 0 ? cp : 100;
}

// 异步镜像战斗（纯）：战力加权随机，返回 {winner, log}
function arenaResolve(myCp: number, opCp: number, myName: string, opName: string): { winnerIsMe: boolean; log: string } {
  const myScore = myCp * (0.7 + Math.random() * 0.6);
  const opScore = opCp * (0.7 + Math.random() * 0.6);
  const iWin = myScore >= opScore;
  const log = `${myName}（战力${myCp}，出手${Math.round(myScore)}）对决 ${opName}（战力${opCp}，出手${Math.round(opScore)}）——${iWin ? myName + ' 胜' : opName + ' 胜'}`;
  return { winnerIsMe: iWin, log };
}

async function addScore(userId: number, patch: { renown?: number; virtue?: number; wins?: number; losses?: number }): Promise<void> {
  await dbRun(
    `INSERT INTO social_scores (user_id, renown, virtue, wins, losses) VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(user_id) DO UPDATE SET
       renown = renown + ?,
       virtue = virtue + ?,
       wins = wins + ?,
       losses = losses + ?`,
    [userId, patch.renown || 0, patch.virtue || 0, patch.wins || 0, patch.losses || 0,
     patch.renown || 0, patch.virtue || 0, patch.wins || 0, patch.losses || 0]);
}

async function realmMultOf(userId: number): Promise<number> {
  const r = await dbGet('SELECT realm_index FROM rankings WHERE user_id = ?', [userId]);
  // 0.8.9 [reward089] C2 指数 -> C1 线性（与客户端同源）：擂台/仇杀/请安/求签/出师贺礼 5 处调用点一并收敛
  return realmStoneFactor(r && r.realm_index);
}

// \u2500\u2500 T16 \u6f14\u6b66\u573a\u5468\u699c\u7ed3\u7b97\uff080.8.10 [arenaweek]\uff09\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
// \u4f9d\u636e docs/0.8.8-design/T16-\u6f14\u6b66\u573a.md \u00a73.3\u300c\u65b0\u589e C \u00b7 \u5468\u699c\u300d/ \u00a75.5\u300c\u5468\u699c\u5956\u52b1\u300d\u3002
//   \u65f6\u70b9\uff1a\u6bcf\u5468\u4e00 00:00\uff08\u5317\u4eac\uff09\u5bf9**\u521a\u7ed3\u675f\u7684\u4e00\u5468**\u7ed3\u7b97\u4e00\u6b21\uff1b\u5e42\u7b49\u952e activity_config
//         `arena_week_settled:<\u5468\u4e00\u65e5\u671f>`\uff08\u4e0e\u6d3b\u52a8\u7ed3\u7b97\u540c\u6b3e\u6807\u8bb0\uff0c\u91cd\u8dd1\u96f6\u65b0\u589e\uff09\u3002
//   \u6392\u540d\uff1aarena_scores.points\uff08**\u4e0d\u6e05\u96f6**\uff0c\u6eda\u52a8\u7d2f\u8ba1 \u2014\u2014 \u00a73.3 \u53d6\u820d\u70b9 E\uff09\u3002
//   \u5956\u52b1\uff08\u90ae\u4ef6\u53d1\u653e\uff1b\u500d\u7387\u4e00\u5f8b realmMultOf\uff0c\u4e0e\u5168\u4ed3\u7075\u77f3\u5956\u52b1\u540c\u6e90\uff09\uff1a
//     \u7b2c 1 \u540d   floor(20000\u00d7M) \u7075\u77f3 + \u79f0\u53f7\u300c\u592a\u865a\u9b41\u9996\u300d
//     \u7b2c 2~3 \u540d floor(12000\u00d7M) \u7075\u77f3
//     \u7b2c 4~10 \u540d floor(6000\u00d7M) \u7075\u77f3
//     \u53c2\u4e0e\u5956\uff08\u672c\u5468\u8bba\u5251 \u226510 \u573a\uff09floor(2000\u00d7M) \u7075\u77f3
//   \u2605 \u62a4\u680f\uff1a\u540d\u6b21\u5956\u8981\u6c42\u300c\u672c\u5468\u81f3\u5c11\u6253 1 \u573a\u300d\uff0c\u5426\u5219\u79ef\u5206\u4e0d\u6e05\u96f6\u4f1a\u8ba9\u505c\u73a9\u7684\u9ad8\u5206\u53f7\u6bcf\u5468\u767d\u62ff\u5956\u3002
//   \u26a0\ufe0f \u8fb9\u754c\uff1a\u53ea\u8865\u7ed3\u7b97\u300c\u6700\u8fd1\u4e00\u4e2a\u5df2\u7ed3\u675f\u7684\u5468\u300d\uff1b\u505c\u673a\u8de8\u591a\u4e2a\u5468\u4e00\u65f6\u4e0d\u8ffd\u6eaf\u66f4\u65e9\u7684\u5468\u3002
const ARENA_WEEK_PARTICIPATE = 10;
const ARENA_WEEK_TOP = 10;
const ARENA_WEEK_MARK = 'arena_week_settled:';

// \u5468\u952e\uff08\u5317\u4eac\u5468\u4e00 YYYY-MM-DD\uff09\u2192 \u8be5\u5468\u8d77\u70b9 ms\uff08\u5317\u4eac\u5468\u4e00 0 \u70b9\uff09
function arenaWeekStartMs(week: string): number {
  return Date.parse(week + 'T00:00:00.000Z') - 8 * 3600 * 1000;
}
// \u67d0\u5468\u8bba\u5251\u573a\u6b21 = \u5df2\u7ed3\u7b97\u6218\u4e66\uff08status='accepted'\uff09+ \u5feb\u7167\u6311\u6218
async function arenaWeekMatches(userId: number, week: string): Promise<number> {
  const s = arenaWeekStartMs(week), e = s + 7 * 86400000;
  const [b, k] = await Promise.all([
    dbGet("SELECT COUNT(*) AS c FROM arena_battles WHERE status = 'accepted' AND (challenger_id = ? OR defender_id = ?) AND resolved_at >= ? AND resolved_at < ?",
      [userId, userId, s, e]).catch(() => null),
    dbGet('SELECT COUNT(*) AS c FROM arena_snapshots WHERE challenger_id = ? AND created_at >= ? AND created_at < ?',
      [userId, s, e]).catch(() => null),
  ]);
  return (Number(b && b.c) || 0) + (Number(k && k.c) || 0);
}
// \u540d\u6b21 \u2192 \u7075\u77f3\u57fa\u6570\uff080 = \u4e0d\u53d1\u540d\u6b21\u5956\uff09
function arenaWeekRewardBase(rank: number): number {
  if (rank === 1) return 20000;
  if (rank <= 3) return 12000;
  if (rank <= ARENA_WEEK_TOP) return 6000;
  return 0;
}
// \u7ed3\u7b97\u300c\u521a\u7ed3\u675f\u7684\u4e00\u5468\u300d\u3002\u5f02\u5e38\u81ea\u541e\u4e0d\u963b\u585e\u8c03\u7528\u65b9\uff1b\u5e42\u7b49\uff08\u6807\u8bb0\u5728\u53d1\u5b8c\u4e4b\u540e\u5199\uff09\u3002
let arenaWeekSettling = false;
async function arenaWeekSettle(): Promise<void> {
  if (arenaWeekSettling) return;
  arenaWeekSettling = true;
  try {
    const nowMs = Date.now();
    const curStart = arenaWeekStartMs(bjWeekStart(nowMs));   // \u672c\u5468\u4e00\uff08\u5317\u4eac\uff090 \u70b9
    if (nowMs < curStart) return;
    const week = bjWeekStart(curStart - 86400000);           // \u521a\u7ed3\u675f\u90a3\u5468\u7684\u5468\u4e00
    const done = await dbGet('SELECT value FROM activity_config WHERE key = ?', [ARENA_WEEK_MARK + week]).catch(() => null);
    if (done) return;
    const rows = await dbAll('SELECT user_id FROM arena_scores WHERE points > 0 ORDER BY points DESC, user_id ASC', []).catch(() => []);
    let sent = 0;
    for (let i = 0; i < (rows || []).length; i++) {
      const uid = Number(rows[i].user_id);
      if (!Number.isFinite(uid)) continue;
      const rank = i + 1;
      const mult = await realmMultOf(uid).catch(() => 1);
      const m = await arenaWeekMatches(uid, week);
      const base = arenaWeekRewardBase(rank);
      if (base > 0 && m >= 1) {                              // \u62a4\u680f\uff1a\u672c\u5468\u81f3\u5c11\u6253 1 \u573a\uff08\u6539 true \u5373\u4e25\u683c\u7167\u7b56\u5212\u6848\uff09
        const reward = Math.floor(base * mult);
        if (reward > 0) {
          const champ = rank === 1;
          await insertMail(uid, champ ? '\u6f14\u6b66\u573a\u00b7\u5468\u699c\u9b41\u9996' : '\u6f14\u6b66\u573a\u00b7\u5468\u699c\u7ed3\u7b97',
            champ ? `\u4f60\u5728 ${week} \u8fd9\u4e00\u5468\u7684\u6f14\u6b66\u573a\u79ef\u5206\u9ad8\u5c45\u7b2c 1 \u540d\uff0c\u83b7\u5c01\u300c\u592a\u865a\u9b41\u9996\u300d\uff0c\u9644\u7075\u77f3 \u00d7${reward}\u3002`
                  : `\u4f60\u5728 ${week} \u8fd9\u4e00\u5468\u7684\u6f14\u6b66\u573a\u79ef\u5206\u6392\u540d\u7b2c ${rank} \u540d\uff0c\u5956\u52b1\u7075\u77f3 \u00d7${reward}\u3002`,
            'system', reward).catch(() => null);
          if (champ) await grantTitleBySource(uid, 'arena_week1').catch(() => false);
          sent++;
        }
      }
      if (m >= ARENA_WEEK_PARTICIPATE) {
        const pr = Math.floor(2000 * mult);
        if (pr > 0) {
          await insertMail(uid, '\u6f14\u6b66\u573a\u00b7\u53c2\u4e0e\u5956', `\u4f60\u672c\u5468\u8bba\u5251 ${m} \u573a\uff0c\u8fbe\u6210\u53c2\u4e0e\u5956\uff0c\u5956\u52b1\u7075\u77f3 \u00d7${pr}\u3002`, 'system', pr).catch(() => null);
          sent++;
        }
      }
    }
    await dbRun("INSERT OR IGNORE INTO activity_config (key, value) VALUES (?, '1')", [ARENA_WEEK_MARK + week]).catch(() => null);
    if (sent > 0) logChronicle(null, '\u5929\u673a\u9601', `\u3010\u6f14\u6b66\u573a\u3011${week} \u5468\u699c\u5df2\u7ed3\u7b97\uff0c\u5956\u52b1\u968f\u90ae\u4ef6\u9001\u8fbe\u3002`);
  } catch (e: any) {
    console.error('arena week settle error:', e?.message || e);
  } finally {
    arenaWeekSettling = false;
  }
}
// ── 擂台 ──
app.post('/api/arena/challenge', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `ar:ch:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const t = await findUserByName(req.body?.name);
    if (!t) return res.status(404).json({ error: '查无此道友' });
    if (t.id === userId) return res.status(400).json({ error: '不能向自己下战书' });
    const sent = await dbGet("SELECT COUNT(*) AS c FROM arena_battles WHERE challenger_id = ? AND created_at >= ?", [userId, utcDayStartMs()]);
    if (Number(sent?.c) >= ARENA_DAILY_MAX) return res.status(409).json({ error: `今日下战书已达上限（${ARENA_DAILY_MAX} 次）` });
    const dup = await dbGet("SELECT 1 AS x FROM arena_battles WHERE challenger_id = ? AND defender_id = ? AND status = 'pending' LIMIT 1", [userId, t.id]);
    if (dup) return res.status(409).json({ error: '战书已在途，等对方应战' });
    const b = await dbRun("INSERT INTO arena_battles (challenger_id, defender_id, status, created_at) VALUES (?, ?, 'pending', ?)", [userId, t.id, Date.now()]);
    insertMail(t.id, '擂台战书', `道友「${String(req.user.username || '').slice(0, 32)}」向你下了战书！到擂台页应战，胜者得侠名与灵石。`, 'system', 0).catch(() => {});
    res.json({ ok: true, battleId: Number(b.lastID), target: t });
  } catch (e: any) { console.error('arena challenge error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.get('/api/arena/my', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `ar:my:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const [incoming, outgoing, hist, score, renownTop] = await Promise.all([
      dbAll(
        `SELECT b.id, u.username AS uname, COALESCE(NULLIF(r.name, ''), u.username) AS name
         FROM arena_battles b JOIN users u ON u.id = b.challenger_id LEFT JOIN rankings r ON r.user_id = b.challenger_id
         WHERE b.defender_id = ? AND b.status = 'pending' ORDER BY b.id DESC LIMIT 10`, [userId]),
      dbAll(
        `SELECT b.id, u.username AS uname, COALESCE(NULLIF(r.name, ''), u.username) AS name
         FROM arena_battles b JOIN users u ON u.id = b.defender_id LEFT JOIN rankings r ON r.user_id = b.defender_id
         WHERE b.challenger_id = ? AND b.status = 'pending' ORDER BY b.id DESC LIMIT 10`, [userId]),
      dbAll(
        `SELECT b.id, b.status, b.winner_id, b.log, b.resolved_at,
                CASE WHEN b.challenger_id = ? THEN 'out' ELSE 'in' END AS dir
         FROM arena_battles b
         WHERE (b.challenger_id = ? OR b.defender_id = ?) AND b.status IN ('accepted','declined')
         ORDER BY b.id DESC LIMIT 10`, [userId, userId, userId]),
      dbGet('SELECT renown, virtue, wins, losses FROM social_scores WHERE user_id = ?', [userId]),
      dbAll('SELECT s.user_id AS id, s.renown, COALESCE(NULLIF(r.name, ""), u.username) AS name FROM social_scores s JOIN users u ON u.id = s.user_id LEFT JOIN rankings r ON r.user_id = s.user_id ORDER BY s.renown DESC LIMIT 10'),
    ]);
    res.json({
      now: Date.now(),
      dailyLeft: Math.max(0, ARENA_DAILY_MAX - Number((await dbGet("SELECT COUNT(*) AS c FROM arena_battles WHERE challenger_id = ? AND created_at >= ?", [userId, utcDayStartMs()]))?.c || 0)),
      incoming: (incoming || []).map((x: any) => ({ id: Number(x.id), name: String(x.name || x.uname || '') })),
      outgoing: (outgoing || []).map((x: any) => ({ id: Number(x.id), name: String(x.name || x.uname || '') })),
      history: (hist || []).map((x: any) => ({ id: Number(x.id), status: String(x.status), iWon: x.winner_id === userId, dir: String(x.dir), log: String(x.log || '').slice(0, 160) })),
      score: { renown: Number(score?.renown) || 0, virtue: Number(score?.virtue) || 0, wins: Number(score?.wins) || 0, losses: Number(score?.losses) || 0 },
      renownTop: (renownTop || []).map((x: any) => ({ id: Number(x.id), name: String(x.name || ''), renown: Number(x.renown) || 0 })),
      // ★ T16（0.8.8）追加字段（D7：**只加不改** —— 上面 6 个既有字段逐字保留，零语义变更）。
      //   客户端新演武场面板读：realmIndex（试炼境界）/ grudges[]（恩怨分栏）/
      //   points·tier·tierName·snapshotLeft（论剑分栏）/ rules（玩法说明动态拼接）。
      ...(await arenaMyExtra(userId)),
    });
  } catch (e: any) { console.error('arena my error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

async function arenaSettle(battleId: number, userId: number): Promise<{ ok: boolean; error?: string; log?: string; iWon?: boolean }> {
  const b = await dbGet("SELECT * FROM arena_battles WHERE id = ? AND status = 'pending'", [battleId]);
  if (!b) return { ok: false, error: '战书不存在或已处理' };
  if (Number(b.defender_id) !== userId) return { ok: false, error: '此战书不是下给你的' };
  const rows = await dbAll('SELECT id, username FROM users WHERE id IN (?, ?)', [b.challenger_id, b.defender_id]);
  const cps = await dbAll('SELECT user_id, combat_power, name FROM rankings WHERE user_id IN (?, ?)', [b.challenger_id, b.defender_id]);
  const nameOf = (uid: number) => {
    const cu: any = (rows || []).find((x: any) => Number(x.id) === uid);
    const cr: any = (cps || []).find((x: any) => Number(x.user_id) === uid);
    return String((cr && cr.name) || (cu && cu.username) || '无名');
  };
  const cpOf = (uid: number) => arenaCombat((cps || []).find((x: any) => Number(x.user_id) === uid));
  const cName = nameOf(Number(b.challenger_id)), dName = nameOf(userId);
  const out = arenaResolve(cpOf(userId), cpOf(Number(b.challenger_id)), dName, cName);
  const winnerId = out.winnerIsMe ? userId : Number(b.challenger_id);
  const loserId = out.winnerIsMe ? Number(b.challenger_id) : userId;
  const mult = await realmMultOf(winnerId);
  const stones = Math.floor(ARENA_STONE_BASE * mult);
  await dbRun("UPDATE arena_battles SET status = 'accepted', winner_id = ?, log = ?, resolved_at = ? WHERE id = ?", [winnerId, out.log, Date.now(), battleId]);
  await addScore(winnerId, { renown: ARENA_RENOWN_WIN, wins: 1 });
  await addScore(loserId, { losses: 1 });
  // 败者自动入胜者仇人名单（胜者记仇败者无意义；反向：败者记胜者为仇）
  await dbRun("INSERT OR IGNORE INTO grudges (owner_id, enemy_id, reason, created_at) VALUES (?, ?, ?, ?)", [loserId, winnerId, '擂台落败', Date.now()]);
  await updatePlayerSave(winnerId, (sd: any) => {
    sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + stones;
  });
  insertMail(loserId, '擂台落败', `战报：${out.log}。\n胜者得侠名 +${ARENA_RENOWN_WIN}、灵石 ×${stones}。到擂台页可于复仇时段（北京 19-22 点）向对方雪耻。`, 'system', 0).catch(() => {});
  return { ok: true, log: out.log, iWon: out.winnerIsMe };
}

app.post('/api/arena/accept', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `ar:ac:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const id = Math.floor(asNum(req.body?.battleId));
    if (!Number.isInteger(id) || id <= 0) return res.status(400).json({ error: '参数非法' });
    const r = await arenaSettle(id, userId);
    if (!r.ok) return res.status(409).json({ error: r.error });
    res.json({ ok: true, iWon: r.iWon, log: r.log });
  } catch (e: any) { console.error('arena accept error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/arena/decline', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `ar:dc:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const id = Math.floor(asNum(req.body?.battleId));
    const r = await dbRun("UPDATE arena_battles SET status = 'declined', resolved_at = ? WHERE id = ? AND defender_id = ? AND status = 'pending'", [Date.now(), id, userId]);
    if (!r.changes) return res.status(404).json({ error: '战书不存在或已处理' });
    res.json({ ok: true });
  } catch (e: any) { console.error('arena decline error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// ── 恩怨 ──
app.get('/api/grudge/list', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `gr:list:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const rows = await dbAll(
      `SELECT g.id, g.enemy_id AS id2, g.reason, g.wins, g.losses, g.avenged, g.last_revenge_at,
              COALESCE(NULLIF(r.name, ''), u.username) AS name
       FROM grudges g JOIN users u ON u.id = g.enemy_id LEFT JOIN rankings r ON r.user_id = g.enemy_id
       WHERE g.owner_id = ? ORDER BY g.avenged ASC, g.id DESC LIMIT 30`, [userId]);
    res.json({
      now: Date.now(),
      windowOpen: (() => { const h = new Date().getUTCHours(); return h >= GRUDGE_WINDOW_UTC[0] && h < GRUDGE_WINDOW_UTC[1]; })(),
      windowUtc: GRUDGE_WINDOW_UTC,
      grudges: (rows || []).map((g: any) => ({
        enemyId: Number(g.id2),
        name: String(g.name || ''),
        reason: String(g.reason || ''),
        wins: Number(g.wins) || 0,
        losses: Number(g.losses) || 0,
        avenged: !!g.avenged,
        cooldownUntil: g.last_revenge_at ? Number(g.last_revenge_at) + GRUDGE_COOLDOWN_MS : null,
      })),
    });
  } catch (e: any) { console.error('grudge list error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/grudge/revenge', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `gr:rv:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const h = new Date().getUTCHours();
    if (!(h >= GRUDGE_WINDOW_UTC[0] && h < GRUDGE_WINDOW_UTC[1])) return res.status(409).json({ error: '快意恩仇仅在晚间开放（北京 19:00-22:00）' });
    const enemyId = Math.floor(asNum(req.body?.enemyId));
    if (!Number.isInteger(enemyId) || enemyId <= 0) return res.status(400).json({ error: '参数非法' });
    const g = await dbGet('SELECT * FROM grudges WHERE owner_id = ? AND enemy_id = ?', [userId, enemyId]);
    if (!g) return res.status(404).json({ error: '仇人名单中无此人' });
    if (g.last_revenge_at && Date.now() - Number(g.last_revenge_at) < GRUDGE_COOLDOWN_MS) {
      return res.status(409).json({ error: '同一仇人 24 小时内仅可复仇一次' });
    }
    const cps = await dbAll('SELECT user_id, combat_power, name FROM rankings WHERE user_id IN (?, ?)', [userId, enemyId]);
    const us = await dbAll('SELECT id, username FROM users WHERE id IN (?, ?)', [userId, enemyId]);
    const nameOf = (uid: number) => {
      const cr: any = (cps || []).find((x: any) => Number(x.user_id) === uid);
      const cu: any = (us || []).find((x: any) => Number(x.id) === uid);
      return String((cr && cr.name) || (cu && cu.username) || '无名');
    };
    const out = arenaResolve(arenaCombat(cps.find((x: any) => Number(x.user_id) === userId)), arenaCombat(cps.find((x: any) => Number(x.user_id) === enemyId)), nameOf(userId), nameOf(enemyId));
    await dbRun('UPDATE grudges SET last_revenge_at = ?, wins = wins + ?, losses = losses + ?, avenged = CASE WHEN ? THEN 1 ELSE avenged END WHERE id = ?',
      [Date.now(), out.winnerIsMe ? 1 : 0, out.winnerIsMe ? 0 : 1, out.winnerIsMe ? 1 : 0, g.id]);
    if (out.winnerIsMe) {
      const mult = await realmMultOf(userId);
      const stones = Math.floor(GRUDGE_STONE_BASE * mult);
      await updatePlayerSave(userId, (sd: any) => {
        sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + stones;
      });
      await addScore(userId, { renown: ARENA_RENOWN_WIN });
      logChronicle(userId, nameOf(userId), `【快意恩仇】「${nameOf(userId)}」阵前雪耻，击败「${nameOf(enemyId)}」，恩怨两清`);
      insertMail(enemyId, '恩怨了结', `战报：${out.log}。江湖恩怨，来日再叙。`, 'system', 0).catch(() => {});
      return res.json({ ok: true, iWon: true, stones, log: out.log });
    }
    await addScore(userId, { losses: 1 });
    return res.json({ ok: true, iWon: false, log: out.log });
  } catch (e: any) { console.error('grudge revenge error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// ─────────────────────────────────────────────────────────
// T16ARENA088 · T16（0.8.8 C 组）演武场：PVE 试炼 + 异步 PVP 论剑（快照挑战）+ 积分段位 + 恩怨入口。
// 权威规格：docs/0.8.8-design/T16-演武场.md §5.1 / §5.2 / §5.3 / §5.4 / §6.1 / §6.2 / §6.4。
// ★ 活跃度纪律（§6.4 / §7.3）：演武场侧**零埋点** —— 本块不写 daily_quests、不新增
//   QUEST_DEFS、不碰 /api/quest/chest 的 activityFromQuests。活跃度「擂台论道」由 T9
//   读时 COUNT arena_battles（本环不动该表结构 ⇒ T9 读法不变）。
// ★ 日切：统一北京 0 点。日串一律 bjDate(Date.now())（与 T9 活跃度同口径）。
// ★ 与存量擂台边界（D7）：ARENA_DAILY_MAX / ARENA_RENOWN_WIN / ARENA_STONE_BASE /
//   arena_battles 表结构 / 4 个旧端点语义 —— 一字不动。
// [t16arena]
const ARENA_TIER_CUTS = [0, 100, 300, 600, 1000, 1500, 2100];
const ARENA_TIER_NAMES = ['凡铁境', '青锋境', '银锋境', '金锋境', '玄锋境', '化虚境', '太虚境'];
const ARENA_PT_WIN = [12, 12, 12, 14, 14, 16, 16];   // 胜（同段 / 低段）
const ARENA_PT_OVER = [18, 18, 18, 21, 21, 24, 24];  // 胜（越级挑战，= 同段 +6/+7/+8）
const ARENA_PT_LOSE = [5, 5, 5, 6, 6, 7, 7];         // 负（扣分，下限 0）
const ARENA_TRIAL_FREE = 5;          // 试炼每日免费 5 次（§5.3）
const ARENA_TRIAL_BUY_MAX = 2;       // 试炼每日最多购买 2 次（§5.3）
const ARENA_SNAPSHOT_MAX = 5;        // 快照挑战每日 5 次（§5.3）
const ARENA_TRIAL_LAYERS = 9;        // 每关 9 层（§3.2）
const ARENA_TRIAL_ELITE = [3, 6, 9]; // 精英层（奖励 ×1.5，§3.2）
// Cs 境界基础属性（§5.1；与客户端 YlxwArenaRealms 同源；maxHp/attack/defense 与
// TRIB_REALM_BASES :4343 逐字一致，spirit=defense、physique=attack，speed 与 maxExpBase 见 §5.1 表）
const ARENA_TRIAL_REALMS = [
  { name: '炼气期', maxHp: 100,   attack: 10,   defense: 5,   spirit: 5,   physique: 10,   speed: 10,  maxExpBase: 60000 },
  { name: '筑基期', maxHp: 250,   attack: 25,   defense: 12,  spirit: 12,  physique: 25,   speed: 15,  maxExpBase: 390000 },
  { name: '金丹期', maxHp: 625,   attack: 50,   defense: 25,  spirit: 25,  physique: 50,   speed: 13,  maxExpBase: 1521000 },
  { name: '元婴期', maxHp: 1250,  attack: 125,  defense: 62,  spirit: 62,  physique: 125,  speed: 13,  maxExpBase: 6592000 },
  { name: '化神期', maxHp: 3125,  attack: 312,  defense: 156, spirit: 156, physique: 312,  speed: 50,  maxExpBase: 26775000 },
  { name: '合道期', maxHp: 7812,  attack: 781,  defense: 390, spirit: 390, physique: 781,  speed: 125, maxExpBase: 104430000 },
  { name: '长生境', maxHp: 19531, attack: 1953, defense: 976, spirit: 976, physique: 1953, speed: 313, maxExpBase: 452500000 },
];
// 试炼 NPC 名号（同一层名号固定，可反复挑战、可记忆，§3.2）
const ARENA_TRIAL_NPC = ['青石道人', '竹影剑客', '玄铁真君', '赤霄魔君', '紫府仙尊', '太虚剑尊', '长生老祖'];
// M(r) = 1.5^r（r 0..6；全部为二进制可精确表示的 dyadic 有理数，无浮点尾巴）
const ARENA_M_MULT = [1, 1.5, 2.25, 3.375, 5.0625, 7.59375, 11.390625];

function arenaM(realmIdx: number): number {
  const i = Math.floor(Number(realmIdx));
  return (Number.isFinite(i) && i >= 0 && i < ARENA_M_MULT.length) ? ARENA_M_MULT[i] : 1;
}
// 段位序（0..6，纯）：积分 → 段位索引（实时升降、可掉段，§5.4）
function arenaTierIdx(points: unknown): number {
  const p = Math.max(0, Math.floor(Number(points) || 0));
  let i = 0;
  for (let k = 0; k < ARENA_TIER_CUTS.length; k++) { if (p >= ARENA_TIER_CUTS[k]) i = k; }
  return i;
}
// 试炼敌人属性（纯）：f(layer)=135×(100+16×(layer-1))/10000，E(stat)=floor(Cs×f)
//   ★ 整数式（乘 10000 再除），不做 60/300 下限 —— §5.1 主表即「已定档绝对属性」，
//     套下限会与主表（炼气 L1 气血 135）自相矛盾；与客户端 YlxwArenaEnemy 同口径。
function arenaTrialStats(realmIdx: number, layer: number): any {
  const r = ARENA_TRIAL_REALMS[realmIdx];
  if (!r) return null;
  const fn = 135 * (100 + 16 * (layer - 1)); // = f(layer) × 10000
  const sc = (v: number) => Math.floor(v * fn / 10000);
  return {
    maxHp: sc(r.maxHp), attack: sc(r.attack), defense: sc(r.defense),
    spirit: sc(r.spirit), physique: sc(r.physique), speed: sc(r.speed),
  };
}
// 战力口径（与 extractRankingData :1315 同式）：floor(attack+defense+maxHp/10+spirit+speed)
//   ★ R2 定档：敌人 CP 用与玩家**同一条**公式（physique 不入 CP —— 玩家侧也不入），
//     保证「同境界同层敌人」与同境界玩家的 CP 可比。
function arenaCombatOfStats(s: any): number {
  if (!s) return 100;
  const cp = Number(s.attack || 0) + Number(s.defense || 0) + Number(s.maxHp || 0) / 10 + Number(s.spirit || 0) + Number(s.speed || 0);
  return Number.isFinite(cp) && cp > 0 ? Math.floor(cp) : 100;
}
function arenaIsElite(layer: number): boolean { return ARENA_TRIAL_ELITE.indexOf(layer) >= 0; }
// 奖励（§5.2；★ 一律整数百分比式再除，禁直接乘浮点字面量）
function arenaTrialWinStones(realmIdx: number, layer: number): number {
  return Math.floor(150 * arenaM(realmIdx) * (100 + 8 * (layer - 1)) / 100);
}
function arenaTrialFirstWin(realmIdx: number): number { return Math.floor(800 * arenaM(realmIdx)); }
function arenaTrialTriple(realmIdx: number): number { return Math.floor(1200 * arenaM(realmIdx)); }
// 首通灵石：普通 floor(500×M×layer)；精英 ×1.5（★ 先乘再 floor，对齐 §5.2 手算 76,886）
function arenaTrialClearStones(realmIdx: number, layer: number, elite: boolean): number {
  const raw = 500 * arenaM(realmIdx) * layer;
  return elite ? Math.floor(raw * 3 / 2) : Math.floor(raw);
}
// 修为槽：floor(maxExpBase × (100 + 24×(layer-1)) / 100)（§5.2 整数式）
//   ★ 刻意不复用 realmMaxExp()（:4354）—— 后者是 `base×(1+(lv-1)×0.24)` 浮点式，
//     金丹 L5 会得 2,981,159 而非 §5.2 的 2,981,160（浮点尾巴）。天劫口径不动，本环另立整数式。
function arenaTrialMaxExp(realmIdx: number, layer: number): number {
  const r = ARENA_TRIAL_REALMS[realmIdx];
  const base = r ? r.maxExpBase : 60000;
  return Math.floor(base * (100 + 24 * (layer - 1)) / 100);
}
// 首通修为：floor(0.05 × realmMaxExp × (精英?1.5:1))，0.05 = 5/100、1.5 = 3/2（整数式）
function arenaTrialClearExp(realmIdx: number, layer: number, elite: boolean): number {
  const raw = arenaTrialMaxExp(realmIdx, layer) * 5;
  return elite ? Math.floor(raw * 3 / 200) : Math.floor(raw / 100);
}
// 购买价：第 n 次（n 从 0 起）floor(2000×(n+1)×M(r))（§5.3）
function arenaTrialBuyPrice(realmIdx: number, nth: number): number {
  return Math.floor(2000 * (nth + 1) * arenaM(realmIdx));
}
// 规则下发（对齐 T8 mentor 的 rules 口径，§6.2）
function arenaRules(): any {
  return {
    trialFree: ARENA_TRIAL_FREE, trialBuyMax: ARENA_TRIAL_BUY_MAX, trialLayers: ARENA_TRIAL_LAYERS,
    trialElite: ARENA_TRIAL_ELITE.slice(), snapshotMax: ARENA_SNAPSHOT_MAX, dailyMax: ARENA_DAILY_MAX,
    tierCuts: ARENA_TIER_CUTS.slice(), tierNames: ARENA_TIER_NAMES.slice(),
    ptWin: ARENA_PT_WIN.slice(), ptOver: ARENA_PT_OVER.slice(), ptLose: ARENA_PT_LOSE.slice(),
  };
}
// 试炼日状态（北京日）：wins=今日胜场（=今日已耗次数，失败不扣次数）；buys=今日已购
async function arenaTrialDay(userId: number): Promise<{ date: string; wins: number; buys: number; firstWin: number; tripleWin: number }> {
  const date = bjDate(Date.now());
  const [w, d] = await Promise.all([
    dbGet("SELECT COUNT(*) AS c FROM arena_trials WHERE user_id = ? AND date = ? AND won = 1", [userId, date]),
    dbGet("SELECT buys, first_win, triple_win FROM arena_trial_daily WHERE user_id = ? AND date = ?", [userId, date]),
  ]);
  return {
    date,
    wins: Number(w && w.c) || 0,
    buys: Number(d && d.buys) || 0,
    firstWin: Number(d && d.first_win) || 0,
    tripleWin: Number(d && d.triple_win) || 0,
  };
}
// 试炼日状态累计（单语句原子 upsert；patch 只传 0/1 增量）
async function arenaTrialDayTouch(userId: number, date: string, patch: { buys?: number; firstWin?: number; tripleWin?: number }): Promise<void> {
  await dbRun(
    `INSERT INTO arena_trial_daily (user_id, date, buys, first_win, triple_win) VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(user_id, date) DO UPDATE SET
       buys = buys + ?, first_win = first_win + ?, triple_win = triple_win + ?`,
    [userId, date, patch.buys || 0, patch.firstWin || 0, patch.tripleWin || 0,
     patch.buys || 0, patch.firstWin || 0, patch.tripleWin || 0]);
}
// 今日尾段连胜数（纯读）：从最新一行往回数，遇到败即停
async function arenaTrialStreak(userId: number, date: string): Promise<number> {
  const rows = await dbAll('SELECT won FROM arena_trials WHERE user_id = ? AND date = ? ORDER BY id DESC LIMIT 20', [userId, date]);
  let s = 0;
  for (const r of (rows || [])) { if (Number(r.won) === 1) s++; else break; }
  return s;
}
// 积分/段位读写（§5.4）
async function arenaScoreOf(userId: number): Promise<{ points: number; wins: number; losses: number }> {
  const r = await dbGet('SELECT points, wins, losses FROM arena_scores WHERE user_id = ?', [userId]);
  return { points: Number(r && r.points) || 0, wins: Number(r && r.wins) || 0, losses: Number(r && r.losses) || 0 };
}
async function arenaScoreAdd(userId: number, dPoints: number, won: boolean): Promise<{ points: number; tier: number; tierName: string }> {
  const cur = await arenaScoreOf(userId);
  const next = Math.max(0, cur.points + Math.floor(Number(dPoints) || 0)); // 积分下限 0（不为负）
  const tier = arenaTierIdx(next);
  await dbRun(
    `INSERT INTO arena_scores (user_id, points, tier, wins, losses, updated_at) VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(user_id) DO UPDATE SET points = ?, tier = ?, wins = wins + ?, losses = losses + ?, updated_at = ?`,
    [userId, next, tier + 1, won ? 1 : 0, won ? 0 : 1, Date.now(),
     next, tier + 1, won ? 1 : 0, won ? 0 : 1, Date.now()]);
  return { points: next, tier: tier + 1, tierName: ARENA_TIER_NAMES[tier] };
}
async function arenaCombatOfUser(userId: number): Promise<number> {
  const r = await dbGet('SELECT combat_power FROM rankings WHERE user_id = ?', [userId]);
  const cp = Number(r && r.combat_power);
  return Number.isFinite(cp) && cp > 0 ? cp : 100;
}
async function arenaNameOf(userId: number): Promise<string> {
  const r = await dbGet('SELECT name FROM rankings WHERE user_id = ?', [userId]);
  if (r && r.name) return String(r.name);
  const u = await dbGet('SELECT username FROM users WHERE id = ?', [userId]);
  return String((u && u.username) || '无名');
}
// /api/arena/my 追加字段（D7：只加不改；既有 6 字段在调用处逐字保留）
//   客户端读：t.realmIndex（试炼 myRealm）/ t.grudges[]（恩怨分栏）/ points/tier/tierName/
//   snapshotLeft（论剑分栏）/ rules（玩法说明动态拼接）。
async function arenaMyExtra(userId: number): Promise<any> {
  const [rk, sc, gr, snap] = await Promise.all([
    dbGet('SELECT realm_index FROM rankings WHERE user_id = ?', [userId]),
    arenaScoreOf(userId),
    dbAll(`SELECT g.enemy_id AS id, g.reason, COALESCE(NULLIF(r.name, ''), u.username) AS name
           FROM grudges g JOIN users u ON u.id = g.enemy_id LEFT JOIN rankings r ON r.user_id = g.enemy_id
           WHERE g.owner_id = ? ORDER BY g.avenged ASC, g.id DESC LIMIT 30`, [userId]),
    dbGet("SELECT COUNT(*) AS c FROM arena_snapshots WHERE challenger_id = ? AND date = ?", [userId, bjDate(Date.now())]),
  ]);
  const tierIdx = arenaTierIdx(sc.points);
  return {
    realmIndex: rk && rk.realm_index != null ? Math.max(0, Math.floor(Number(rk.realm_index))) : 0,
    points: sc.points,
    tier: tierIdx + 1,
    tierName: ARENA_TIER_NAMES[tierIdx],
    snapshotLeft: Math.max(0, ARENA_SNAPSHOT_MAX - (Number(snap && snap.c) || 0)),
    // 客户端恩怨分栏读 my.grudges[]（字段名对齐 YlxwArenaGrudgeZone：g.id / g.name / g.reason）
    grudges: (gr || []).map((g: any) => ({ id: Number(g.id), name: String(g.name || ''), reason: String(g.reason || '') })),
    rules: arenaRules(),
  };
}

// GET /api/arena/trials — 试炼状态（客户端 st = tl.data）：今日剩余次数 / 已首通层 / 可挑战境界 / 购买余额。
//   cleared 键形如 "0-1"（realmIndex-layer），与客户端 `cleared[realm + "-" + (layer+1)]` 逐字对应。
app.get('/api/arena/trials', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `ar:tr:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const [rk, day, clearedRows] = await Promise.all([
      dbGet('SELECT realm_index FROM rankings WHERE user_id = ?', [userId]),
      arenaTrialDay(userId),
      dbAll('SELECT realm_index, layer FROM arena_trials WHERE user_id = ? AND first_clear = 1', [userId]),
    ]);
    const realmIndex = rk && rk.realm_index != null ? Math.max(0, Math.floor(Number(rk.realm_index))) : 0;
    const cleared: Record<string, number> = {};
    for (const c of (clearedRows || [])) cleared[Number(c.realm_index) + '-' + Number(c.layer)] = 1;
    res.json({
      now: Date.now(),
      date: day.date,
      realmIndex,
      maxRealm: realmIndex, // 解锁规则：第 N 关需玩家境界 ≥ 该关境界（§3.2）
      dailyLeft: Math.max(0, ARENA_TRIAL_FREE + day.buys - day.wins),
      buyLeft: Math.max(0, ARENA_TRIAL_BUY_MAX - day.buys),
      winsToday: day.wins,
      firstWinToday: day.firstWin > 0,
      tripleToday: day.tripleWin > 0,
      layers: ARENA_TRIAL_LAYERS,
      eliteLayers: ARENA_TRIAL_ELITE.slice(),
      cleared,
      realms: ARENA_TRIAL_REALMS.map((r: any, i: number) => ({ index: i, name: r.name })),
      rules: arenaRules(),
    });
  } catch (e: any) { console.error('arena trials error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// POST /api/arena/trials/fight {realmIndex, layer} — 试炼闯关（快速结算，复用 arenaResolve 战力加权随机）。
//   校验：境界解锁 → 层解锁（第 k 层需第 k-1 层已首通）→ 次数；★ 失败**不扣次数**（§3.2 取舍点 D 默认）。
//   奖励（§5.2）：单次胜利 + 每日首胜 + 当日三连胜 + 首通（灵石 + 修为，一次性）。
app.post('/api/arena/trials/fight', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `ar:tf:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const realmIndex = Math.floor(asNum(req.body?.realmIndex));
    const layer = Math.floor(asNum(req.body?.layer));
    if (!Number.isInteger(realmIndex) || realmIndex < 0 || realmIndex >= ARENA_TRIAL_REALMS.length) return res.status(400).json({ error: '参数非法' });
    if (!Number.isInteger(layer) || layer < 1 || layer > ARENA_TRIAL_LAYERS) return res.status(400).json({ error: '参数非法' });
    const [rk, day, prevClear, already] = await Promise.all([
      dbGet('SELECT realm_index FROM rankings WHERE user_id = ?', [userId]),
      arenaTrialDay(userId),
      layer > 1 ? dbGet('SELECT 1 AS x FROM arena_trials WHERE user_id = ? AND realm_index = ? AND layer = ? AND first_clear = 1 LIMIT 1', [userId, realmIndex, layer - 1]) : Promise.resolve(null),
      dbGet('SELECT 1 AS x FROM arena_trials WHERE user_id = ? AND realm_index = ? AND layer = ? AND first_clear = 1 LIMIT 1', [userId, realmIndex, layer]),
    ]);
    const myRealm = rk && rk.realm_index != null ? Math.max(0, Math.floor(Number(rk.realm_index))) : 0;
    if (realmIndex > myRealm) return res.status(409).json({ error: '境界不足，尚不可挑战此关' });
    if (layer > 1 && !prevClear) return res.status(409).json({ error: '请先通关上一层' });
    if (Math.max(0, ARENA_TRIAL_FREE + day.buys - day.wins) <= 0) return res.status(409).json({ error: '今日挑战次数已用完' });
    const elite = arenaIsElite(layer);
    const stats = arenaTrialStats(realmIndex, layer);
    const [myCp, myName] = await Promise.all([arenaCombatOfUser(userId), arenaNameOf(userId)]);
    const opName = (ARENA_TRIAL_NPC[realmIndex] || '试炼对手') + '·第' + layer + '层';
    const out = arenaResolve(myCp, arenaCombatOfStats(stats), myName, opName);
    const won = out.winnerIsMe;
    const isFirst = won && !already;
    const now = Date.now();
    await dbRun(
      "INSERT INTO arena_trials (user_id, realm_index, layer, kind, date, won, first_clear, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
      [userId, realmIndex, layer, elite ? 'elite' : 'normal', day.date, won ? 1 : 0, isFirst ? 1 : 0, now]);
    let stones = 0, exp = 0, dailyFirst = false, triple = false, streak = 0;
    if (won) {
      const winsAfter = day.wins + 1;
      stones += arenaTrialWinStones(realmIndex, layer);
      if (day.firstWin === 0 && winsAfter === 1) { stones += arenaTrialFirstWin(realmIndex); dailyFirst = true; }
      streak = await arenaTrialStreak(userId, day.date);
      if (day.tripleWin === 0 && streak >= 3) { stones += arenaTrialTriple(realmIndex); triple = true; }
      if (isFirst) { stones += arenaTrialClearStones(realmIndex, layer, elite); exp += arenaTrialClearExp(realmIndex, layer, elite); }
      await updatePlayerSave(userId, (sd: any) => {
        if (!sd.player || typeof sd.player !== 'object') return;
        if (stones > 0) sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + stones;
        if (exp > 0) sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + exp;
      });
      if (dailyFirst || triple) await arenaTrialDayTouch(userId, day.date, { firstWin: dailyFirst ? 1 : 0, tripleWin: triple ? 1 : 0 });
    }
    const day2 = await arenaTrialDay(userId);
    res.json({
      ok: true, iWon: won, log: out.log, realmIndex, layer, elite, firstClear: isFirst,
      // [r061] R-061 战报：客户端 YlxwUseAct 在第 4 参缺省时 toast 响应的 message 字段（yl_061_ext.py 已去死 label）
      message: (won
        ? '🏆 挑战胜利！灵石 +' + stones + (exp > 0 ? ' · 修为 +' + exp : '')
        : '挑战失败，本次不扣次数') + (isFirst ? ' · 首通达成！' : '') + (triple ? ' · 三连胜奖励！' : ''),
      dailyFirst, triple, streak, stones, exp, nextMaxExp: arenaTrialMaxExp(realmIndex, layer),
      dailyLeft: Math.max(0, ARENA_TRIAL_FREE + day2.buys - day2.wins),
      buyLeft: Math.max(0, ARENA_TRIAL_BUY_MAX - day2.buys),
    });
  } catch (e: any) { console.error('arena trials fight error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// POST /api/arena/trials/buy {} — 购买额外试炼次数（每日 ≤2，§5.3）。
//   定价 floor(2000×(n+1)×M(r))（第 1 次 2000×M、第 2 次 4000×M），与客户端
//   YlxwArenaBuyPrice(realm, buyNth) 逐位一致（buyNth = buyMax - buyLeft）。
//   事务口径：预检 → 扣费（saveLock 互斥 + 二次校验）→ 计数；计数失败则**退费**（唯一补偿窗口）。
app.post('/api/arena/trials/buy', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => `ar:tb:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const [rk, day] = await Promise.all([dbGet('SELECT realm_index FROM rankings WHERE user_id = ?', [userId]), arenaTrialDay(userId)]);
    if (day.buys >= ARENA_TRIAL_BUY_MAX) return res.status(409).json({ error: '今日购买次数已达上限' });
    const realmIndex = rk && rk.realm_index != null ? Math.max(0, Math.floor(Number(rk.realm_index))) : 0;
    const cost = arenaTrialBuyPrice(realmIndex, day.buys);
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < cost) { short = true; return; }
      sd.player.spiritStones = b - cost;
    });
    if (!paid.ok || short) return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '购买失败，请重试') });
    try {
      await arenaTrialDayTouch(userId, day.date, { buys: 1 });
    } catch (e: any) {
      // 补偿：退费（计数未增），保证「扣了钱没加次数」不可能发生
      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + cost; });
      console.error('arena trial buy settle error:', e?.message || e);
      return res.status(500).json({ error: '购买失败，请重试' });
    }
    const day2 = await arenaTrialDay(userId);
    res.json({ ok: true, cost, buys: day2.buys, buyLeft: Math.max(0, ARENA_TRIAL_BUY_MAX - day2.buys), dailyLeft: Math.max(0, ARENA_TRIAL_FREE + day2.buys - day2.wins) });
  } catch (e: any) { console.error('arena trial buy error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// GET /api/arena/ladder — 战力榜 TOP20（快照挑战目标）+ 我的积分/段位/快照余额。
//   客户端读 data.top[].{id|userId, name, combatPower|combat_power} / data.me.{points,wins,losses}
//   / data.snapshotLeft ⇒ 本响应**两种 id/战力键名都给**，避免客户端取键落空。
app.get('/api/arena/ladder', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `ar:ld:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const [top, me, sc, snap] = await Promise.all([
      dbAll(`SELECT r.user_id AS id, COALESCE(NULLIF(r.name, ''), r.username) AS name, r.combat_power, r.realm_index, r.realm_level
             FROM rankings r ORDER BY r.combat_power DESC, r.user_id ASC LIMIT 20`),
      dbGet('SELECT user_id, combat_power, realm_index, realm_level, name, username FROM rankings WHERE user_id = ?', [userId]),
      arenaScoreOf(userId),
      dbGet("SELECT COUNT(*) AS c FROM arena_snapshots WHERE challenger_id = ? AND date = ?", [userId, bjDate(Date.now())]),
    ]);
    const tierIdx = arenaTierIdx(sc.points);
    res.json({
      now: Date.now(),
      top: (top || []).map((x: any, i: number) => ({
        rank: i + 1, id: Number(x.id), userId: Number(x.id), name: String(x.name || ''),
        combatPower: Number(x.combat_power) || 0, combat_power: Number(x.combat_power) || 0,
        realmIndex: Number(x.realm_index) || 0, realmLevel: Number(x.realm_level) || 1,
      })),
      me: {
        id: userId, userId,
        name: String((me && (me.name || me.username)) || ''),
        combatPower: Number(me && me.combat_power) || 0,
        realmIndex: Number(me && me.realm_index) || 0,
        realmLevel: Number(me && me.realm_level) || 1,
        points: sc.points, tier: tierIdx + 1, tierName: ARENA_TIER_NAMES[tierIdx],
        wins: sc.wins, losses: sc.losses,
      },
      snapshotLeft: Math.max(0, ARENA_SNAPSHOT_MAX - (Number(snap && snap.c) || 0)),
      rules: arenaRules(),
    });
  } catch (e: any) { console.error('arena ladder error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// POST /api/arena/snapshot {targetId} — 快照挑战（§3.3 新增 A）：以目标战力镜像为对手立即结算。
//   对方无需在线、不受任何损失（不加其败场、不进其仇人名单），仅收一封战报邮件。
//   次数 5/日；积分只在此与下战书结算时变动（§3.3 新增 B）。
//   ★ R6 防刷两道守卫：① 同一目标每日 1 次（唯一索引 (challenger,target,date) + INSERT OR IGNORE 原子判定）
//     ② 目标战力 < 我方 50% ⇒ 结算但不计积分（防刷小号刷分）。
app.post('/api/arena/snapshot', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `ar:sn:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const targetId = Math.floor(asNum(req.body?.targetId));
    if (!Number.isInteger(targetId) || targetId <= 0) return res.status(400).json({ error: '参数非法' });
    if (targetId === userId) return res.status(400).json({ error: '不能挑战自己' });
    const date = bjDate(Date.now());
    const [cnt, tgt, sc, myCp, myName] = await Promise.all([
      dbGet('SELECT COUNT(*) AS c FROM arena_snapshots WHERE challenger_id = ? AND date = ?', [userId, date]),
      dbGet('SELECT user_id, combat_power, name, username FROM rankings WHERE user_id = ?', [targetId]),
      arenaScoreOf(userId),
      arenaCombatOfUser(userId),
      arenaNameOf(userId),
    ]);
    if (Number(cnt && cnt.c) >= ARENA_SNAPSHOT_MAX) return res.status(409).json({ error: '今日快照挑战次数已用完' });
    if (!tgt) return res.status(404).json({ error: '查无此道友' });
    const targetCp = Number(tgt.combat_power) || 100;
    const opName = String(tgt.name || tgt.username || '无名');
    const out = arenaResolve(myCp, targetCp, myName, opName);
    const won = out.winnerIsMe;
    // 段位对比（越级加成，§5.4）：先取目标积分再定增量
    const tgtSc = await arenaScoreOf(targetId);
    const myTier = arenaTierIdx(sc.points), tgtTier = arenaTierIdx(tgtSc.points);
    let dPoints = won ? (tgtTier > myTier ? ARENA_PT_OVER[myTier] : ARENA_PT_WIN[myTier]) : -ARENA_PT_LOSE[myTier];
    let noPoint = false;
    if (targetCp < myCp * 0.5) { dPoints = 0; noPoint = true; }
    // 原子占位（唯一索引防「同一目标当日重复」；changes=0 ⇒ 今日已打过，且此时尚未结算积分）
    const ins = await dbRun(
      "INSERT OR IGNORE INTO arena_snapshots (challenger_id, target_id, won, date, created_at) VALUES (?, ?, ?, ?, ?)",
      [userId, targetId, won ? 1 : 0, date, Date.now()]);
    if (!ins.changes) return res.status(409).json({ error: '今日已挑战过此道友' });
    const after = await arenaScoreAdd(userId, dPoints, won);
    insertMail(targetId, '快照挑战', '道友「' + myName + '」向你发起快照挑战：' + out.log + '。此为战力镜像战，你无需应战、亦无任何损失。', 'system', 0).catch(() => {});
    const cnt2 = await dbGet('SELECT COUNT(*) AS c FROM arena_snapshots WHERE challenger_id = ? AND date = ?', [userId, date]);
    res.json({
      ok: true, iWon: won, log: out.log, noPoint, pointsDelta: dPoints,
      target: { id: targetId, name: opName, combatPower: targetCp },
      points: after.points, tier: after.tier, tierName: after.tierName,
      snapshotLeft: Math.max(0, ARENA_SNAPSHOT_MAX - (Number(cnt2 && cnt2.c) || 0)),
    });
  } catch (e: any) { console.error('arena snapshot error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// GET /api/arena/week \u2014 \u6f14\u6b66\u573a\u5468\u699c\uff08\u5ba2\u6237\u7aef\u300c\u8bba\u5251\u300d\u5206\u680f\u5c55\u793a\u7528\uff1bT16 \u00a73.3 \u65b0\u589e C\uff09\u3002
//   board\uff1a\u524d 50 \u540d\uff08\u6309 points \u964d\u5e8f\uff09\uff1bme\uff1a\u6211\u7684\u540d\u6b21/\u79ef\u5206/\u6bb5\u4f4d/\u672c\u5468\u573a\u6b21\uff1blastSettleWeek\uff1a\u6700\u8fd1\u5df2\u7ed3\u7b97\u5468\u3002
app.get('/api/arena/week', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `ar:wk:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const week = bjWeekStart(Date.now());
    const rows = await dbAll(`SELECT s.user_id AS uid, s.points AS points,
        COALESCE(NULLIF(r.name, ''), u.username) AS name, r.combat_power AS cp
      FROM arena_scores s JOIN users u ON u.id = s.user_id
      LEFT JOIN rankings r ON r.user_id = s.user_id
      WHERE s.points > 0 ORDER BY s.points DESC, s.user_id ASC LIMIT 50`, []).catch(() => []);
    const board = (rows || []).map((x: any, i: number) => {
      const p = Number(x.points) || 0;
      return { rank: i + 1, name: String(x.name || ''), points: p,
               tierName: ARENA_TIER_NAMES[arenaTierIdx(p)], combatPower: Number(x.cp) || 0 };
    });
    const mine = await arenaScoreOf(userId);
    const ahead = await dbGet('SELECT COUNT(*) AS c FROM arena_scores WHERE points > ?', [mine.points]).catch(() => null);
    const myRank = mine.points > 0 ? (Number(ahead && ahead.c) || 0) + 1 : null;
    const matches = await arenaWeekMatches(userId, week);
    const lastMark = await dbGet("SELECT key FROM activity_config WHERE key LIKE 'arena_week_settled:%' ORDER BY key DESC LIMIT 1", []).catch(() => null);
    res.json({
      ok: true, week, participateAt: ARENA_WEEK_PARTICIPATE, top: ARENA_WEEK_TOP,
      board,
      me: { rank: myRank, points: mine.points, tierName: ARENA_TIER_NAMES[arenaTierIdx(mine.points)],
            matches, participated: matches >= ARENA_WEEK_PARTICIPATE },
      lastSettleWeek: lastMark ? String(lastMark.key).slice(ARENA_WEEK_MARK.length) : null,
    });
  } catch (e: any) { console.error('arena week error:', e?.message || e); res.status(500).json({ error: '\u670d\u52a1\u5668\u7e41\u5fd9' }); }
});
// POST /api/arena/grudge {targetId} — 恩怨复仇（客户端「恩怨」分栏的「复仇」按钮）。
//   与既有 POST /api/grudge/revenge 同规则（北京 19:00-22:00 窗口 + 同仇人 24h 冷却 + 雪耻播报），
//   仅入参名不同（客户端传 targetId，旧端点传 enemyId）⇒ 本环新增该入口，**不动旧端点**。
app.post('/api/arena/grudge', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `ar:gv:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const h = new Date().getUTCHours();
    if (!(h >= GRUDGE_WINDOW_UTC[0] && h < GRUDGE_WINDOW_UTC[1])) return res.status(409).json({ error: '快意恩仇仅在晚间开放（北京 19:00-22:00）' });
    const enemyId = Math.floor(asNum(req.body?.targetId));
    if (!Number.isInteger(enemyId) || enemyId <= 0) return res.status(400).json({ error: '参数非法' });
    const g = await dbGet('SELECT * FROM grudges WHERE owner_id = ? AND enemy_id = ?', [userId, enemyId]);
    if (!g) return res.status(404).json({ error: '仇人名单中无此人' });
    if (g.last_revenge_at && Date.now() - Number(g.last_revenge_at) < GRUDGE_COOLDOWN_MS) return res.status(409).json({ error: '同一仇人 24 小时内仅可复仇一次' });
    const [myCp, enCp, myName, enName] = await Promise.all([arenaCombatOfUser(userId), arenaCombatOfUser(enemyId), arenaNameOf(userId), arenaNameOf(enemyId)]);
    const out = arenaResolve(myCp, enCp, myName, enName);
    await dbRun('UPDATE grudges SET last_revenge_at = ?, wins = wins + ?, losses = losses + ?, avenged = CASE WHEN ? THEN 1 ELSE avenged END WHERE id = ?',
      [Date.now(), out.winnerIsMe ? 1 : 0, out.winnerIsMe ? 0 : 1, out.winnerIsMe ? 1 : 0, g.id]);
    if (out.winnerIsMe) {
      const mult = await realmMultOf(userId);
      const stones = Math.floor(GRUDGE_STONE_BASE * mult);
      await updatePlayerSave(userId, (sd: any) => {
        sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + stones;
      });
      await addScore(userId, { renown: ARENA_RENOWN_WIN });
      logChronicle(userId, myName, '【快意恩仇】「' + myName + '」阵前雪耻，击败「' + enName + '」，恩怨两清');
      insertMail(enemyId, '恩怨了结', '战报：' + out.log + '。江湖恩怨，来日再叙。', 'system', 0).catch(() => {});
      return res.json({ ok: true, iWon: true, stones, log: out.log });
    }
    await addScore(userId, { losses: 1 });
    return res.json({ ok: true, iWon: false, log: out.log });
  } catch (e: any) { console.error('arena grudge error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});
// [/t16arena]

// ── 师徒传功 ──
app.post('/api/mentor/teach', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `mt:teach:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const rel = await dbAll("SELECT apprentice_id FROM mentorships WHERE mentor_id = ? AND status = 'active' ORDER BY created_at LIMIT 10", [userId]);
    const list = (rel || []).map((x: any) => Number(x.apprentice_id));
    if (!list.length) return res.status(409).json({ error: '你门下暂无弟子' });
    let appId: number;
    if (list.length === 1) appId = list[0];
    else {
      appId = Math.floor(asNum(req.body?.apprenticeId));
      if (!list.includes(appId)) return res.status(400).json({ error: '参数须为在门弟子' });
    }
    const today = utcDateStr();
    const dup = await dbRun('INSERT OR IGNORE INTO teach_log (user_id, apprentice_id, date) VALUES (?, ?, ?)', [userId, appId, today]);
    if (!dup.changes) return res.status(409).json({ error: '今日已传功，明日再来' });
    const mult = await realmMultOf(appId);
    const expGain = Math.floor(TEACH_EXP_BASE * mult);
    const r = await updatePlayerSave(appId, (sd: any) => {
      sd.player.exp = (Number(sd.player?.exp) || 0) + expGain;
    });
    if (!r.ok) {
      await dbRun('DELETE FROM teach_log WHERE user_id = ? AND date = ?', [userId, today]); // 补偿回退，可重试
      return res.status(409).json({ error: '徒弟尚无存档，暂不可传功' });
    }
    await addScore(userId, { virtue: TEACH_VIRTUE });
    const tName = String(req.user.username || '').slice(0, 32);
    insertMail(appId, '师傅传功', `师傅「${tName}」倾囊相授，你获修为 ×${expGain}（已入档）。勤加修炼，莫负师恩。`, 'system', 0).catch(() => {});
    res.json({ ok: true, apprenticeId: appId, expGain, virtue: TEACH_VIRTUE });
  } catch (e: any) { console.error('mentor teach error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// ─────────────────────────────────────────────────────────
// 批4 API（伴生页 /yl/apps/daily/）：师门请安 / 茶馆竞猜 / 世界妖兽
// 请安：师徒每日互请安，双方各得灵石 200×1.5^境界，双向都请安时双方再加一份；
// 茶馆：每日一题二选一押注（100~10000），北京 21:00（UTC 13:00）惰性开盅，猜中 1.9 倍（5% 抽水）；
// 妖兽：全服共享血量池（按当日最高境界缩放），每人每日 3 击，出手即得伤害 2% 灵石，补刀者 5000+播报。
// ─────────────────────────────────────────────────────────
const TEA_MIN_BET = 500, TEA_MAX_BET = 50000, TEA_PAYOUT = 1.9, TEA_OPEN_UTC = 13;
const TEA_MAX_BETS = 3; // 0.8.6：每日最多下注 3 次（首注 INSERT，其后同侧追加，累计不超 3×上限）
const WB_STRIKES = 3, WB_HP_BASE = 500000, WB_KILLER_BONUS = 5000;
const GREET_STONES_BASE = 200;

// ─────────────────────────────────────────────────────────
// 0.8.6 每日行乐：掷骰比大小 / 每日一签 / 灵石翻牌（+ 茶馆茶运）
// 设计红线：任何玩法 EV ≤ 1（见本文件顶部注释）。免费玩法一律设每日次数上限。
// ─────────────────────────────────────────────────────────
const FUN_DICE_DAILY = 10; // R-128 [r128fun] 每日 3→10 次（掷骰上限 10 次，台账原文）
const FUN_DICE_MIN = 20000, FUN_DICE_MAX = 20000; // R-128 [r128fun] 每次固定 2 万注（MIN 1000→20000；赔率 1.95/25 不动，EV=91/96≈0.9479≤1 铁律②）
const FUN_DICE_PAY = 1.95, FUN_DICE_TRIPLE_PAY = 25;
const FUN_SIGN_DAILY = 1;
const FUN_SIGN_BASE = 2000; // R-127 [r127sign]：一签灵石底数 500→2000（每日仅 1 抽，奖励大幅增加；仍再乘 realmMultOf 与签档倍率）
const FUN_CARD_DAILY = 10, FUN_CARD_COST = 20000; // R-128 [r128fun] 每日 2→10 次 · 单次成本 2000→20000
const FUN_CARD_PAYS = [0, 2000, 6000, 10000, 14000, 18000, 22000, 28000, 34000, 54000]; // R-128 [r128fun] 3 档→10 档：Σ=188,000，EV=18,800/20,000=0.94≤1；赚(>2万)4 张/亏(<2万)6 张，头奖=2.7x 注额
const FUN_DICE_PICK_NAME: Record<string, string> = { big: '大', small: '小', triple: '豹子' };

// 茶运：每日由日期哈希定 0/1/2 档。只放大**修为**与**彩头概率**，绝不碰灵石赔率。
function teaLuckOf(date: string): { tier: number; label: string } {
  let h = 0;
  for (const ch of (date + 'luck')) h = (h * 37 + ch.charCodeAt(0)) >>> 0;
  const tier = h % 3;
  return { tier, label: ['平', '旺', '大旺'][tier] };
}
const TEA_LUCK_BOND = 0; // 占位（保持常量表可读性，勿删）

// 区间随机（纯，rng 注入可单测）
function funRandInt(lo: unknown, hi: unknown, rng: () => number): number {
  const a = Math.floor(Number(lo) || 0), b = Math.floor(Number(hi) || 0);
  const lo2 = Math.min(a, b), hi2 = Math.max(a, b);
  const r = Math.min(0.999999, Math.max(0, Number(rng()) || 0));
  return lo2 + Math.floor(r * (hi2 - lo2 + 1));
}
function funRandFloat(lo: unknown, hi: unknown, rng: () => number): number {
  const a = Number(lo) || 0, b = Number(hi) || 0;
  const lo2 = Math.min(a, b), hi2 = Math.max(a, b);
  const r = Math.min(0.999999, Math.max(0, Number(rng()) || 0));
  return lo2 + r * (hi2 - lo2);
}
// 修为收益（纯）：按当层修为槽百分比计，钳槽内不溢出（与 adventureExpGain 同口径）
function funExpGain(rate: unknown, maxExp: unknown, curExp: unknown): number {
  const slot = Math.max(0, Math.floor(Number(maxExp) || 0));
  const cur = Math.max(0, Math.floor(Number(curExp) || 0));
  const raw = Math.floor(slot * Math.max(0, Number(rate) || 0));
  return Math.max(0, Math.min(raw, slot - cur));
}
// 三骰判定（纯）：三同 → triple；否则 3-10 小、11-18 大
function funDiceKind(a: number, b: number, c: number): string {
  if (a === b && b === c) return 'triple';
  return (a + b + c) >= 11 ? 'big' : 'small';
}
// 三骰派彩（纯）：大/小 1.95，豹子 25；未中 0
function funDicePayout(kind: string, pick: string, bet: number): number {
  if (kind !== pick) return 0;
  const mult = kind === 'triple' ? FUN_DICE_TRIPLE_PAY : FUN_DICE_PAY;
  return Math.floor(Math.max(0, Math.floor(bet)) * mult);
}

// 每日一签：四档签文池（权重合计 100）
interface FunSignTier { key: string; name: string; weight: number; expRate: number; stonesRate: number; ticketChance: number; texts: string[]; }
const FUN_SIGN_TIERS: FunSignTier[] = [
  { key: 'ss', name: '上上签', weight: 10, expRate: 0.050, stonesRate: 12.0, ticketChance: 0.30, // R-127 [r127sign] expRate .020→.050 · stonesRate 4.0→12.0（权重/彩头率/签文不动）
    texts: ['紫气东来，道基天成。', '云开见月，仙缘自来。', '一念通玄，百脉俱畅。', '天光垂照，此签大吉。'] },
  { key: 's', name: '上签', weight: 30, expRate: 0.025, stonesRate: 6.0, ticketChance: 0.10, // R-127 [r127sign] expRate .010→.025 · stonesRate 2.4→6.0
    texts: ['清风入怀，修行顺遂。', '溪山有约，前路可期。', '小有际遇，宜静心守拙。', '云淡风轻，一步一进。'] },
  { key: 'm', name: '中签', weight: 45, expRate: 0.010, stonesRate: 2.5, ticketChance: 0.02, // R-127 [r127sign] expRate .005→.010 · stonesRate 1.4→2.5
    texts: ['不咸不淡，稳中有进。', '行路平平，守常即可。', '无大吉亦无大凶。', '日常如常，即是好签。'] },
  { key: 'x', name: '下签', weight: 15, expRate: 0.003, stonesRate: 1.0, ticketChance: 0, // R-127 [r127sign] expRate .002→.003 · stonesRate 0.7→1.0
    texts: ['风微云暗，宜少动多思。', '前路稍阻，退一步自有天地。', '小晦而已，不必挂怀。'] },
];
// 抽签档位（纯）：从低档到高档累计区间落点
function funSignTierOf(rng: () => number): FunSignTier {
  const roll = Math.min(0.999999, Math.max(0, Number(rng()) || 0)) * 100;
  let acc = 0;
  for (let i = FUN_SIGN_TIERS.length - 1; i >= 0; i--) {
    acc += FUN_SIGN_TIERS[i].weight;
    if (roll < acc) return FUN_SIGN_TIERS[i];
  }
  return FUN_SIGN_TIERS[FUN_SIGN_TIERS.length - 1];
}
function funSignTextOf(t: FunSignTier, rng: () => number): string {
  const r = Math.min(0.999999, Math.max(0, Number(rng()) || 0));
  return t.texts[Math.min(t.texts.length - 1, Math.floor(r * t.texts.length))];
}

const TEA_TOPICS = [
  { q: "明日天机：宜远行还是宜闭关？", a: "宜远行", b: "宜闭关" },
  { q: "灵潮将至，涨的是灵石还是丹药？", a: "灵石涨", b: "丹药涨" },
  { q: "魔教叩山，正魔大战谁胜？", a: "正道胜", b: "魔教胜" },
  { q: "天降流星，坠于东海还是北漠？", a: "坠东海", b: "坠北漠" },
  { q: "千年灵芝现世，归于名门还是散修？", a: "名门得之", b: "散修得之" },
  { q: "今夜月圆，妖兽出山还是蛰伏？", a: "出山作乱", b: "蛰伏不动" },
  { q: "仙门大比，剑修夺魁还是体修夺魁？", a: "剑修夺魁", b: "体修夺魁" },
];
const teaTopicOf = (date: string): { id: number; q: string; a: string; b: string } => {
  let h = 0;
  for (const ch of date) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const i = h % TEA_TOPICS.length;
  return { id: i, q: TEA_TOPICS[i].q, a: TEA_TOPICS[i].a, b: TEA_TOPICS[i].b };
};

// ── 师门请安 ──
app.get('/api/mentor/greet', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `mt:gr:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const today = utcDateStr();
    const rows = await dbAll(
      `SELECT g.date, g.mentor_id, g.apprentice_id, g.greeted_by,
              COALESCE(NULLIF(r.name, ''), u.username) AS peerName
       FROM mentor_greetings g
       JOIN mentorships m ON m.mentor_id = g.mentor_id AND m.apprentice_id = g.apprentice_id AND m.status = 'active'
       JOIN users u ON u.id = (CASE WHEN g.mentor_id = ? THEN g.apprentice_id ELSE g.mentor_id END)
       LEFT JOIN rankings r ON r.user_id = (CASE WHEN g.mentor_id = ? THEN g.apprentice_id ELSE g.mentor_id END)
       WHERE g.date = ? AND (g.mentor_id = ? OR g.apprentice_id = ?)`,
      [userId, userId, today, userId, userId]);
    const rels = await dbAll(
      `SELECT mentor_id, apprentice_id FROM mentorships WHERE status = 'active' AND (mentor_id = ? OR apprentice_id = ?)`,
      [userId, userId]);
    const peers = [];
    for (const m of rels || []) {
      const isMentor = Number(m.mentor_id) === userId;
      const peerId = isMentor ? Number(m.apprentice_id) : Number(m.mentor_id);
      const pr: any = await dbGet(
        `SELECT COALESCE(NULLIF(r.name, ''), u.username) AS name FROM users u LEFT JOIN rankings r ON r.user_id = u.id WHERE u.id = ?`, [peerId]);
      const g: any = (rows || []).find((x: any) => Number(x.mentor_id) === peerId || Number(x.apprentice_id) === peerId);
      const by = g ? String(g.greeted_by) : '';
      peers.push({
        peerId, peerName: String(pr?.name || ''),
        isMentor,
        iGreeted: by === (isMentor ? 'mentor' : 'apprentice') || by === 'both',
        peerGreeted: by === (isMentor ? 'apprentice' : 'mentor') || by === 'both',
      });
    }
    res.json({ now: Date.now(), date: today, peers });
  } catch (e: any) { console.error('mentor greet get error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/mentor/greet', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 15, keyFn: (req: any) => `mt:gr2:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const peerId = Math.floor(asNum(req.body?.peerId));
    if (!Number.isInteger(peerId) || peerId <= 0) return res.status(400).json({ error: '参数非法' });
    const rel = await dbGet("SELECT mentor_id, apprentice_id FROM mentorships WHERE status = 'active' AND ((mentor_id = ? AND apprentice_id = ?) OR (mentor_id = ? AND apprentice_id = ?)) LIMIT 1", [userId, peerId, peerId, userId]);
    if (!rel) return res.status(404).json({ error: '你们并无师徒关系' });
    const isMentor = Number(rel.mentor_id) === userId;
    const today = utcDateStr();
    let row: any = await dbGet('SELECT greeted_by FROM mentor_greetings WHERE date = ? AND mentor_id = ? AND apprentice_id = ?', [today, Number(rel.mentor_id), Number(rel.apprentice_id)]);
    const by = row ? String(row.greeted_by) : '';
    const myKey = isMentor ? 'mentor' : 'apprentice';
    const peerKey = isMentor ? 'apprentice' : 'mentor';
    if (by === myKey || by === 'both') return res.status(409).json({ error: '今日已请过安' });
    const newBy = by === peerKey ? 'both' : myKey;
    await dbRun(
      `INSERT INTO mentor_greetings (date, mentor_id, apprentice_id, greeted_by) VALUES (?, ?, ?, ?)
       ON CONFLICT(date, mentor_id, apprentice_id) DO UPDATE SET greeted_by = ?`,
      [today, Number(rel.mentor_id), Number(rel.apprentice_id), newBy, newBy]);
    // 双方各得请安礼（我请安：我得半礼，对方得全礼；若对方已请安（both）双方各再得一份）
    const mult = await realmMultOf(userId);
    const full = Math.floor(GREET_STONES_BASE * mult);
    const half = Math.floor(full / 2);
    const bonus = newBy === 'both' ? full : 0;
    await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + half + bonus; });
    await updatePlayerSave(peerId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + full + bonus; });
    res.json({ ok: true, mine: half + bonus, peer: full + bonus, bothDone: newBy === 'both' });
  } catch (e: any) { console.error('mentor greet post error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// ── 茶馆竞猜 ──
async function teaSettleDue(today: string): Promise<void> {
  // 已过开盅时点（UTC>=13）的未结算注单 → 开盅（当日全部惰性结算，结果由日期哈希伪随机定）
  const h = new Date().getUTCHours();
  if (h < TEA_OPEN_UTC) return;
  const open = await dbAll('SELECT id, user_id, topic_id, side, stones FROM teahouse_bets WHERE date = ? AND won IS NULL', [today]);
  if (!open || !open.length) return;
  const t = teaTopicOf(today);
  let h2 = 0;
  for (const ch of (today + 'open')) h2 = (h2 * 33 + ch.charCodeAt(0)) >>> 0;
  const winSide = h2 % 2;
  for (const b of open) {
    if (Number(b.topic_id) !== t.id) { // 旧题注单（理论不存在）按输处理
      await dbRun('UPDATE teahouse_bets SET won = 0, payout = 0 WHERE id = ?', [b.id]);
      continue;
    }
    const won = Number(b.side) === winSide ? 1 : 0;
    const act: any = await activityOf(today).catch(() => null);
    const payMult = act && String(act.kind) === 'tea_double' ? Number(act.mult) || 1 : TEA_PAYOUT;
    const payout = won ? Math.floor(Number(b.stones) * payMult) : 0;
    await dbRun('UPDATE teahouse_bets SET won = ?, payout = ? WHERE id = ?', [won, payout, b.id]);
    if (payout > 0) {
      // 0.8.6 茶运：中奖额外送**修为**（与灵石经济解耦，所以不破坏 1.9 赔率的 EV 红线）
      const lk = teaLuckOf(today);
      const luckExp = Math.floor(Number(b.stones) * lk.tier * 2);
      const luckTicket = lk.tier > 0 && Math.random() < (lk.tier * 0.08) ? 1 : 0;
      await updatePlayerSave(Number(b.user_id), (sd: any) => {
        sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + payout;
        if (luckExp > 0) {
          const nr = normalizeRealm(sd.player);
          const g = funExpGain(luckExp / Math.max(1, nr.maxExp), nr.maxExp, nr.exp);
          sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + g;
        }
        if (luckTicket > 0) sd.player.lotteryTickets = (Number(sd.player.lotteryTickets) || 0) + luckTicket;
      });
    }
  }
  // 全服播报：当日最大赢家电台
  const best = await dbGet('SELECT user_id, payout FROM teahouse_bets WHERE date = ? AND won = 1 ORDER BY payout DESC LIMIT 1', [today]);
  if (best && Number(best.payout) >= 50000) {
    const nm: any = await dbGet('SELECT username FROM users WHERE id = ?', [Number(best.user_id)]);
    logChronicle(Number(best.user_id), String(nm?.username || ''), `【茶馆开盅】「${String(nm?.username || '')}」一卦中鹄，赢灵石 ×${best.payout}，满座喝彩`);
  }
}

app.get('/api/teahouse/today', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `th:td:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const today = utcDateStr();
    await teaSettleDue(today);
    const t = teaTopicOf(today);
    const mine = await dbGet('SELECT side, stones, won, payout FROM teahouse_bets WHERE user_id = ? AND date = ?', [userId, today]);
    const pool = await dbAll('SELECT side, COUNT(*) AS n, SUM(stones) AS s FROM teahouse_bets WHERE date = ? GROUP BY side', [today]);
    const open = new Date().getUTCHours() < TEA_OPEN_UTC;
    const luck = teaLuckOf(today);
    const myTimes = await dbGet('SELECT COALESCE(MAX(count), 0) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, today, 'tea']);
    const times = Math.max(0, Number(myTimes?.c) || 0);
    const [diceRows, signRow, cardRow, diceHist] = await Promise.all([
      dbGet('SELECT COUNT(*) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, today, 'dice']),
      dbGet('SELECT detail, payout, cost FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ? ORDER BY count DESC LIMIT 1', [userId, today, 'sign']),
      dbGet('SELECT COUNT(*) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, today, 'card']),
      dbAll('SELECT count, cost, payout, detail FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ? ORDER BY count DESC LIMIT ?', [userId, today, 'dice', 10]),
    ]);
    // ★ R-029（fun2 环）：茶馆「可查看记录」——近 14 日逐日流水（**纯只读投影**，
    //   不写表、不改结算、不改 /teahouse/bet）。客户端 yl_fun2_ext.py 消费 myHistory。
    const teaHist = await dbAll('SELECT date, side, stones, won, payout FROM teahouse_bets WHERE user_id = ? ORDER BY date DESC LIMIT 14', [userId]);
    const signToday = signRow ? (() => {
      try { return JSON.parse(String(signRow.detail || '{}')); } catch { return null; }
    })() : null;
    res.json({
      now: Date.now(), date: today, topic: t, open,
      closesAtUtcHour: TEA_OPEN_UTC, payoutMult: TEA_PAYOUT,
      minBet: TEA_MIN_BET, maxBet: TEA_MAX_BET, maxTimes: TEA_MAX_BETS,
      luck,
      myBet: mine ? { side: Number(mine.side), stones: Number(mine.stones), won: mine.won == null ? null : Number(mine.won), payout: mine.payout == null ? null : Number(mine.payout), times } : null,
      // ★ R-029：茶馆历史记录（逐字段 Number 归一；won/payout 保留 null = 待结算）
      myHistory: (teaHist || []).map((x: any) => ({ date: String(x.date), side: Number(x.side) || 0, stones: Number(x.stones) || 0, won: x.won == null ? null : Number(x.won), payout: x.payout == null ? null : Number(x.payout) })),
      pool: (pool || []).map((x: any) => ({ side: Number(x.side), bets: Number(x.n), stones: Number(x.s) || 0 })),
      fun: {
        dice: {
          left: Math.max(0, FUN_DICE_DAILY - (Number(diceRows?.c) || 0)), dailyMax: FUN_DICE_DAILY,
          minBet: FUN_DICE_MIN, maxBet: FUN_DICE_MAX, pay: FUN_DICE_PAY, triplePay: FUN_DICE_TRIPLE_PAY,
          history: (diceHist || []).map((r: any) => {
            let d: any = {}; try { d = JSON.parse(String(r.detail || '{}')); } catch {}
            return { count: Number(r.count) || 0, bet: Number(r.cost) || 0, payout: Number(r.payout) || 0,
                     pickName: FUN_DICE_PICK_NAME[String(d.pick || '')] || '', win: Number(r.payout) > 0 };
          }),
        },
        sign: { left: Math.max(0, FUN_SIGN_DAILY - (signRow ? 1 : 0)), dailyMax: FUN_SIGN_DAILY, today: signToday },
        card: { left: Math.max(0, FUN_CARD_DAILY - (Number(cardRow?.c) || 0)), dailyMax: FUN_CARD_DAILY, cost: FUN_CARD_COST, pays: FUN_CARD_PAYS },
      },
    });
  } catch (e: any) { console.error('teahouse today error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/teahouse/bet', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `th:bet:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const today = utcDateStr();
    if (new Date().getUTCHours() >= TEA_OPEN_UTC) return res.status(409).json({ error: '今日茶馆已开盅，明日赶早' });
    const t = teaTopicOf(today);
    const side = Math.floor(asNum(req.body?.side));
    if (side !== 0 && side !== 1) return res.status(400).json({ error: '只可选 A 或 B' });
    const stones = Math.floor(asNum(req.body?.stones));
    if (!Number.isInteger(stones) || stones < TEA_MIN_BET || stones > TEA_MAX_BET) return res.status(400).json({ error: `押注须 ${TEA_MIN_BET}~${TEA_MAX_BET} 灵石` });
    const dup: any = await dbGet('SELECT id, side, stones FROM teahouse_bets WHERE user_id = ? AND date = ?', [userId, today]);
    const usedRow: any = await dbGet('SELECT COALESCE(MAX(count), 0) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, today, 'tea']);
    const used = Math.max(0, Number(usedRow?.c) || 0);
    if (used >= TEA_MAX_BETS) return res.status(409).json({ error: `今日下注已达上限（${TEA_MAX_BETS} 注），明日赶早` });
    if (dup && Number(dup.side) !== side) return res.status(409).json({ error: '今日已押了另一侧，只能追加同侧' });
    if (dup && Number(dup.stones) + stones > TEA_MAX_BET * TEA_MAX_BETS) return res.status(409).json({ error: `今日累计注额上限 ${TEA_MAX_BET * TEA_MAX_BETS} 灵石` });
    // ★ 顺序契约（全或无）：先占次数位（UNIQUE 单语句原子）→ 再扣灵石 → 最后落注池。
    //   先扣后占的话，并发双击的落败方会被扣掉灵石却拿不到服务 = 无对价扣款。
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun('INSERT INTO fun_daily (player_id, date, kind, count, cost, payout, detail, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)',
        [userId, today, 'tea', used + 1, stones, JSON.stringify({ side }), Date.now()]);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '手速太快，请再试一次' });
      throw e;
    }
    // ★ 注池原子 upsert：把「追加同侧 + 累计上限」压进**单条** ON CONFLICT 语句。
    //   若仍写成「读 dup → 分支 INSERT/UPDATE」，并发下两请求都读到 dup=null，
    //   各自走 INSERT → 后到者吃 teahouse_bets 的 UNIQUE 直接 500，
    //   而它已被扣款且注额不在池里 = 无对价扣款（0.8.6 自测实测复现过）。
    //   changes === 0 ⇒ WHERE 不成立（异侧 / 超上限）⇒ 撤次数位、不扣款。
    const up = await dbRun(
      `INSERT INTO teahouse_bets (user_id, date, topic_id, side, stones, created_at) VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT(user_id, date) DO UPDATE SET stones = teahouse_bets.stones + excluded.stones
       WHERE teahouse_bets.side = excluded.side AND teahouse_bets.stones + excluded.stones <= ?`,
      [userId, today, t.id, side, stones, Date.now(), TEA_MAX_BET * TEA_MAX_BETS]);
    if (!up.changes) {
      await dbRun('DELETE FROM fun_daily WHERE id = ?', [ins.lastID]).catch(() => {});
      return res.status(409).json({ error: '今日已押了另一侧，或累计注额已超上限' });
    }
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < stones) { short = true; return; }
      sd.player.spiritStones = b - stones;
    });
    if (!paid.ok || short) {
      // 回滚注池增量（原子、带下界保护）后再撤次数位，保证「池里有 / 钱扣了」永远同进同出
      await dbRun('UPDATE teahouse_bets SET stones = stones - ? WHERE user_id = ? AND date = ? AND stones >= ?',
        [stones, userId, today, stones]).catch(() => {});
      await dbRun('DELETE FROM fun_daily WHERE id = ?', [ins.lastID]).catch(() => {});
      return res.status(409).json({ error: '灵石不足' });
    }
    res.json({ ok: true, side, stones, times: used + 1, maxTimes: TEA_MAX_BETS });
  } catch (e: any) { console.error('teahouse bet error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// ─────────────────────────────────────────────────────────
// 0.8.6 每日行乐 · 三件套（掷骰比大小 / 每日一签 / 灵石翻牌）
// 记账口径与 /teahouse/bet、/adventure/draw 一致：
//   · 扣费走 updatePlayerSave（saveLock 互斥 + gm_revision++ 促客户端拉新档）
//   · 次数闸门走 fun_daily 的 UNIQUE(player_id,date,kind,count) 单语句原子
//   · 派彩失败一律补偿删行（全或无），可重试
//   · 业务拒绝 400/409，绝不 403（403 会被客户端 Xc() 当会话失效强制登出）
// ─────────────────────────────────────────────────────────
function funDateStr(): string { return utcDateStr(); }

app.post('/api/fun/dice', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `fun:dice:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const today = funDateStr();
    const bet = Math.floor(asNum(req.body?.bet));
    const pick = asStr(req.body?.pick);
    if (!FUN_DICE_PICK_NAME[pick]) return res.status(400).json({ error: '只能押 大 / 小 / 豹子' });
    if (!Number.isInteger(bet) || bet < FUN_DICE_MIN || bet > FUN_DICE_MAX) return res.status(400).json({ error: `注额须 ${FUN_DICE_MIN}~${FUN_DICE_MAX} 灵石` });
    const cnt: any = await dbGet('SELECT COUNT(*) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, today, 'dice']);
    const used = Math.max(0, Number(cnt?.c) || 0);
    if (used >= FUN_DICE_DAILY) return res.status(409).json({ error: `今日已掷 ${FUN_DICE_DAILY} 次，明日再来` });
    const d1 = funRandInt(1, 6, Math.random), d2 = funRandInt(1, 6, Math.random), d3 = funRandInt(1, 6, Math.random);
    const kind = funDiceKind(d1, d2, d3);
    const payout = funDicePayout(kind, pick, bet);
    const detail = JSON.stringify({ pick, dice: [d1, d2, d3], sum: d1 + d2 + d3, kind });
    // ★ 顺序契约（全或无）：先占次数位 → 再扣款派彩。反过来会让并发落败方被白扣灵石。
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun('INSERT INTO fun_daily (player_id, date, kind, count, cost, payout, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        [userId, today, 'dice', used + 1, bet, payout, detail, Date.now()]);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '手速太快，请再试一次' });
      throw e;
    }
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Math.max(0, Math.floor(Number(sd.player?.spiritStones) || 0));
      if (b < bet) { short = true; return; }
      sd.player.spiritStones = b - bet + payout;
    });
    if (!paid.ok || short) {
      await dbRun('DELETE FROM fun_daily WHERE id = ?', [ins.lastID]).catch(() => {});
      return res.status(409).json({ error: short ? `灵石不足：需 ${bet}` : '结算失败，请重试' });
    }
    if (payout > 0) {
      logChronicle(userId, String(req.user.username || '').slice(0, 32), `【行乐·掷骰】${d1}+${d2}+${d3} 开出「${FUN_DICE_PICK_NAME[kind]}」，赢灵石 ×${payout}`);
    }
    res.json({ ok: true, count: used + 1, left: Math.max(0, FUN_DICE_DAILY - used - 1), dailyMax: FUN_DICE_DAILY,
      dice: [d1, d2, d3], sum: d1 + d2 + d3, kind, kindName: FUN_DICE_PICK_NAME[kind],
      pick, win: payout > 0, payout });
  } catch (e: any) { console.error('fun dice error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/fun/sign', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `fun:sign:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const today = funDateStr();
    const dup: any = await dbGet('SELECT id FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ? LIMIT 1', [userId, today, 'sign']);
    if (dup) return res.status(409).json({ error: '今日已求过签，明日再来' });
    const tier = funSignTierOf(Math.random);
    const text = funSignTextOf(tier, Math.random);
    const mult = await realmMultOf(userId);
    const stones = Math.floor(FUN_SIGN_BASE * mult * tier.stonesRate);
    const tickets = Math.random() < tier.ticketChance ? 1 : 0;
    let expGain = 0;
    // ★ 顺序契约（全或无）：先占次数位（每日 1 次由 UNIQUE 兜底），再结算入档。
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun('INSERT INTO fun_daily (player_id, date, kind, count, cost, payout, detail, created_at) VALUES (?, ?, ?, 1, 0, ?, ?, ?)',
        [userId, today, 'sign', stones, JSON.stringify({ tier: tier.key, tierName: tier.name, text, exp: 0, stones, tickets }), Date.now()]);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '今日已求过签' });
      throw e;
    }
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const nr = normalizeRealm(sd.player);
      expGain = funExpGain(tier.expRate, nr.maxExp, nr.exp);
      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + expGain;
      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + stones;
      if (tickets > 0) sd.player.lotteryTickets = (Number(sd.player.lotteryTickets) || 0) + tickets;
    });
    if (!paid.ok) {
      await dbRun('DELETE FROM fun_daily WHERE id = ?', [ins.lastID]).catch(() => {});
      return res.status(409).json({ error: '求签结算失败，请重试' });
    }
    // 回填实际修为（expGain 只有进锁后才知道）；失败仅展示列残留 0，不影响收益
    await dbRun('UPDATE fun_daily SET detail = ? WHERE id = ?',
      [JSON.stringify({ tier: tier.key, tierName: tier.name, text, exp: expGain, stones, tickets }), ins.lastID]).catch(() => {});
    logChronicle(userId, String(req.user.username || '').slice(0, 32), `【行乐·求签】得「${tier.name}」：${text}`);
    res.json({ ok: true, tier: tier.key, tierName: tier.name, text, exp: expGain, stones, tickets, left: 0, dailyMax: FUN_SIGN_DAILY });
  } catch (e: any) { console.error('fun sign error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/fun/card', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `fun:card:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const today = funDateStr();
    const pick = Math.floor(asNum(req.body?.pick));
    if (!(pick >= 0 && pick <= 9)) return res.status(400).json({ error: '只能翻 1 ~ 10 号牌' }); // R-128 [r128fun] 牌号 0..2→0..9（400=业务拒绝，非 403）
    const cnt: any = await dbGet('SELECT COUNT(*) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, today, 'card']);
    const used = Math.max(0, Number(cnt?.c) || 0);
    if (used >= FUN_CARD_DAILY) return res.status(409).json({ error: `今日已翻 ${FUN_CARD_DAILY} 次，明日再来` });
    // 洗牌：奖项等概率落十张牌（R-128 [r128fun] 3→10 档）
    const deck = FUN_CARD_PAYS.slice();
    for (let i = deck.length - 1; i > 0; i--) {
      const j = funRandInt(0, i, Math.random);
      const tmp = deck[i]; deck[i] = deck[j]; deck[j] = tmp;
    }
    const payout = Math.max(0, Math.floor(Number(deck[pick]) || 0));
    const detail = JSON.stringify({ pick, deck });
    // ★ 顺序契约（全或无）：先占次数位 → 再扣成本派彩。
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun('INSERT INTO fun_daily (player_id, date, kind, count, cost, payout, detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        [userId, today, 'card', used + 1, FUN_CARD_COST, payout, detail, Date.now()]);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '手速太快，请再试一次' });
      throw e;
    }
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Math.max(0, Math.floor(Number(sd.player?.spiritStones) || 0));
      if (b < FUN_CARD_COST) { short = true; return; }
      sd.player.spiritStones = b - FUN_CARD_COST + payout;
    });
    if (!paid.ok || short) {
      await dbRun('DELETE FROM fun_daily WHERE id = ?', [ins.lastID]).catch(() => {});
      return res.status(409).json({ error: short ? `灵石不足：需 ${FUN_CARD_COST}` : '结算失败，请重试' });
    }
    res.json({ ok: true, count: used + 1, left: Math.max(0, FUN_CARD_DAILY - used - 1), dailyMax: FUN_CARD_DAILY,
      pick, deck, payout, cost: FUN_CARD_COST });
  } catch (e: any) { console.error('fun card error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// ── 世界妖兽 ──
async function wbEnsure(today: string): Promise<any> {
  let row = await dbGet('SELECT * FROM worldboss WHERE date = ?', [today]);
  if (row) return row;
  const top = await dbGet('SELECT MAX(realm_index) AS ri FROM rankings');
  const mult = Math.pow(1.5, Math.min(20, Math.max(0, Number(top && top.ri) || 0)));
  const hp = Math.floor(WB_HP_BASE * mult);
  await dbRun('INSERT OR IGNORE INTO worldboss (date, hp_max, hp_cur) VALUES (?, ?, ?)', [today, hp, hp]);
  return await dbGet('SELECT * FROM worldboss WHERE date = ?', [today]);
}

app.get('/api/worldboss/today', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `wb:td:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const today = utcDateStr();
    const wb = await wbEnsure(today);
    const mine = await dbGet('SELECT damage, strikes FROM worldboss_hits WHERE date = ? AND user_id = ?', [today, userId]);
    const top = await dbAll(
      `SELECT h.user_id AS id, h.damage, COALESCE(NULLIF(r.name, ''), u.username) AS name
       FROM worldboss_hits h JOIN users u ON u.id = h.user_id LEFT JOIN rankings r ON r.user_id = h.user_id
       WHERE h.date = ? ORDER BY h.damage DESC LIMIT 10`, [today]);
    res.json({
      now: Date.now(), date: today,
      hpMax: Number(wb.hp_max), hpCur: Number(wb.hp_cur), killed: !!wb.killed,
      killerName: wb.killer_id ? await dbGet('SELECT COALESCE(NULLIF(r.name, ""), u.username) AS n FROM users u LEFT JOIN rankings r ON r.user_id = u.id WHERE u.id = ?', [Number(wb.killer_id)]).then((x: any) => String(x?.n || '')) : null,
      myStrikes: Number(mine?.strikes) || 0,
      myDamage: Number(mine?.damage) || 0,
      strikesLeft: Math.max(0, WB_STRIKES - (Number(mine?.strikes) || 0)),
      top: (top || []).map((x: any) => ({ id: Number(x.id), name: String(x.name || ''), damage: Number(x.damage) || 0 })),
    });
  } catch (e: any) { console.error('worldboss today error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/worldboss/strike', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `wb:st:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const today = utcDateStr();
    const wb = await wbEnsure(today);
    if (wb.killed) return res.status(409).json({ error: '妖兽今日已被诛杀，明日再战' });
    const mine = await dbGet('SELECT damage, strikes FROM worldboss_hits WHERE date = ? AND user_id = ?', [today, userId]);
    const used = Number(mine?.strikes) || 0;
    if (used >= WB_STRIKES) return res.status(409).json({ error: `今日出手已用尽（${WB_STRIKES} 次）` });
    const cpRow = await dbGet('SELECT combat_power FROM rankings WHERE user_id = ?', [userId]);
    const cp = Number(cpRow && cpRow.combat_power) || 100;
    const act: any = await activityOf(today).catch(() => null);
    const actMult = act && String(act.kind) === 'wb_double' ? Number(act.mult) || 1 : 1;
    const dmg = Math.max(1, Math.floor(cp * 2 * (0.8 + Math.random() * 0.4) * actMult));
    const newHp = Math.max(0, Number(wb.hp_cur) - dmg);
    const kill = newHp === 0;
    await dbRun('UPDATE worldboss SET hp_cur = ?, killed = CASE WHEN ? THEN 1 ELSE killed END, killer_id = CASE WHEN ? THEN ? ELSE killer_id END WHERE date = ?', [newHp, kill, kill, userId, today]);
    await dbRun(
      `INSERT INTO worldboss_hits (date, user_id, damage, strikes) VALUES (?, ?, ?, 1)
       ON CONFLICT(date, user_id) DO UPDATE SET damage = damage + ?, strikes = strikes + 1`,
      [today, userId, dmg, dmg]);
    const stones = Math.floor(dmg * 0.02) + (kill ? WB_KILLER_BONUS : 0);
    await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + stones; });
    if (kill) {
      const nm: any = await dbGet('SELECT COALESCE(NULLIF(r.name, ""), u.username) AS n FROM users u LEFT JOIN rankings r ON r.user_id = u.id WHERE u.id = ?', [userId]);
      logChronicle(userId, String(nm?.n || ''), `【诛妖】妖兽伏诛，最后一击出自「${String(nm?.n || '')}」之手，全服同贺`);
    }
    res.json({ ok: true, damage: dmg, stones, killed: kill, hpCur: newHp, strikesLeft: WB_STRIKES - used - 1 });
  } catch (e: any) { console.error('worldboss strike error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// ─────────────────────────────────────────────────────────
// 批5 API（伴生页 /yl/apps/guide/）：仙途指引 / 首周七日礼 / 活动日历
// 指引：服务端可校验的里程碑（有档/境界/好友/师徒/道侣/金丹），达标即领；
// 七日：以首次存档日为第 1 天，逐日递增灵石，第 7 天赠称号「七日筑基」；
// 活动：7 天滚动排期惰性生成（周五妖兽双倍 / 周日茶馆双倍），妖兽与茶馆读取当日加成。
// ─────────────────────────────────────────────────────────
const GUIDE_STEPS = [
  { id: 'enter', name: '初入江湖', desc: '创建角色存档', reward: 2000, check: 'has_save' },
  { id: 'lv3', name: '炼气三层', desc: '总等级达到 3', reward: 3000, check: 'lv', arg: 3 },
  { id: 'lv9', name: '炼气圆满', desc: '总等级达到 9', reward: 6000, check: 'lv', arg: 9 },
  { id: 'zhuji', name: '筑基成功', desc: '总等级达到 10', reward: 8000, check: 'lv', arg: 10 },
  { id: 'friend', name: '结识道友', desc: '添加 1 位好友', reward: 3000, check: 'friend' },
  { id: 'baishi', name: '拜入师门', desc: '拥有师傅', reward: 6000, check: 'has_mentor' },
  { id: 'jindan', name: '金丹初成', desc: '总等级达到 19', reward: 20000, check: 'lv', arg: 19 },
  { id: 'daolv', name: '喜结道侣', desc: '结为道侣', reward: 12000, check: 'married' },
]; // [r123guide] R-123 指引 8 步加码（0.9.13 数值表 §7）：Σ60,000（旧 15,100，3.97x）；七日礼同批 Σ15,300→50,000
const WEEK_REWARDS = [2000, 3000, 4000, 6000, 8000, 12000, 15000]; // [r123guide] R-123 七日礼加码：Σ50,000（旧 15,300，3.27x，逐日递增）

// 当日活动（惰性生成 7 天滚动排期：周五妖兽双倍，周日茶馆双倍）
async function activityOf(today: string): Promise<any> {
  let row = await dbGet('SELECT * FROM activity_frame WHERE date = ?', [today]);
  if (row) return row;
  // 生成含今天在内的 7 天（以今天为锚）
  for (let i = 0; i < 7; i++) {
    const d = new Date(); d.setUTCHours(0, 0, 0, 0);
    d.setUTCDate(d.getUTCDate() + i);
    const ds = d.toISOString().slice(0, 10);
    const dow = d.getUTCDay(); // 0=日 5=五
    let kind = 'rest', mult = 1.0, title = '休整日';
    if (dow === 5) { kind = 'wb_double'; mult = 2.0; title = '妖兽狂潮·伤害双倍'; }
    else if (dow === 0) { kind = 'tea_double'; mult = 2.5; title = '茶馆盛日·赔付 2.5 倍'; }
    await dbRun('INSERT OR IGNORE INTO activity_frame (date, kind, mult, title) VALUES (?, ?, ?, ?)', [ds, kind, mult, title]);
  }
  return await dbGet('SELECT * FROM activity_frame WHERE date = ?', [today]);
}

app.get('/api/activities/schedule', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `ac:sc:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  try {
    const today = utcDateStr();
    const cur = await activityOf(today);
    const rows = await dbAll('SELECT date, kind, mult, title FROM activity_frame WHERE date >= ? ORDER BY date LIMIT 7', [today]);
    res.json({
      now: Date.now(), today,
      current: { kind: String(cur.kind), mult: Number(cur.mult), title: String(cur.title) },
      week: (rows || []).map((r: any) => ({ date: String(r.date), kind: String(r.kind), mult: Number(r.mult), title: String(r.title) })),
    });
  } catch (e: any) { console.error('activities schedule error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// 指引/七日状态（合并查询减少前端请求数）
app.get('/api/guide/status', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `gd:st:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const claimed = await dbAll('SELECT step_id FROM guide_progress WHERE user_id = ?', [userId]);
    const claimedSet = new Set((claimed || []).map((x: any) => String(x.step_id)));
    const rk = await dbGet('SELECT realm_index, realm_level FROM rankings WHERE user_id = ?', [userId]);
    const lv = rk && rk.realm_index != null ? Number(rk.realm_index) * 9 + Number(rk.realm_level || 1) : null;
    const hasSave = !!(await dbGet('SELECT 1 AS x FROM saves WHERE user_id = ?', [userId]));
    const friendCnt = await dbGet('SELECT COUNT(*) AS c FROM friendships WHERE user_id = ?', [userId]);
    const hasMentor = !!(await dbGet("SELECT 1 AS x FROM mentorships WHERE apprentice_id = ? AND status = 'active' LIMIT 1", [userId]));
    const married = !!(await dbGet("SELECT 1 AS x FROM couples WHERE status = 'married' AND (user_a = ? OR user_b = ?) LIMIT 1", [userId, userId]));
    const steps = GUIDE_STEPS.map((st) => {
      let done = false;
      if (claimedSet.has(st.id)) done = true;
      else if (st.check === 'has_save') done = hasSave;
      else if (st.check === 'lv') done = lv != null && lv >= Number(st.arg);
      else if (st.check === 'friend') done = Number(friendCnt && friendCnt.c) >= 1;
      else if (st.check === 'has_mentor') done = hasMentor;
      else if (st.check === 'married') done = married;
      return { id: st.id, name: st.name, desc: st.desc, reward: st.reward, done, claimed: claimedSet.has(st.id) };
    });
    // 七日：首存日为 day1
    const first = await dbGet('SELECT MIN(date(updated_at)) AS d FROM saves WHERE user_id = ?', [userId]);
    let week = null;
    if (first && first.d) {
      const startMs = Date.parse(String(first.d) + 'T00:00:00Z');
      const nowMs = Date.now();
      const dayNo = Math.min(7, Math.floor((nowMs - startMs) / 86400000) + 1);
      const wclaimed = await dbAll('SELECT day FROM week_goals WHERE user_id = ?', [userId]);
      const wset = new Set((wclaimed || []).map((x: any) => Number(x.day)));
      const days = [];
      for (let i = 1; i <= 7; i++) {
        days.push({ day: i, reward: WEEK_REWARDS[i - 1], claimable: i <= dayNo && !wset.has(i), claimed: wset.has(i) });
      }
      week = { start: String(first.d), dayNo, days };
    }
    res.json({ now: Date.now(), steps, week });
  } catch (e: any) { console.error('guide status error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/guide/claim', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `gd:cl:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const stepId = asStr(req.body?.stepId).slice(0, 32);
    const st = GUIDE_STEPS.find((x) => x.id === stepId);
    if (!st) return res.status(404).json({ error: '无此里程碑' });
    // 复核条件（防直接调 API 蹭奖）
    const rk = await dbGet('SELECT realm_index, realm_level FROM rankings WHERE user_id = ?', [userId]);
    const lv = rk && rk.realm_index != null ? Number(rk.realm_index) * 9 + Number(rk.realm_level || 1) : null;
    let done = false;
    if (st.check === 'has_save') done = !!(await dbGet('SELECT 1 AS x FROM saves WHERE user_id = ?', [userId]));
    else if (st.check === 'lv') done = lv != null && lv >= Number(st.arg);
    else if (st.check === 'friend') done = Number((await dbGet('SELECT COUNT(*) AS c FROM friendships WHERE user_id = ?', [userId]))?.c) >= 1;
    else if (st.check === 'has_mentor') done = !!(await dbGet("SELECT 1 AS x FROM mentorships WHERE apprentice_id = ? AND status = 'active' LIMIT 1", [userId]));
    else if (st.check === 'married') done = !!(await dbGet("SELECT 1 AS x FROM couples WHERE status = 'married' AND (user_a = ? OR user_b = ?) LIMIT 1", [userId, userId]));
    if (!done) return res.status(409).json({ error: '条件未达成' });
    const ins = await dbRun('INSERT OR IGNORE INTO guide_progress (user_id, step_id, claimed_at) VALUES (?, ?, ?)', [userId, stepId, Date.now()]);
    if (!ins.changes) return res.status(409).json({ error: '已领取过' });
    await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + st.reward; });
    res.json({ ok: true, reward: st.reward });
  } catch (e: any) { console.error('guide claim error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/week/claim', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `wk:cl:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const day = Math.floor(asNum(req.body?.day));
    if (!Number.isInteger(day) || day < 1 || day > 7) return res.status(400).json({ error: '参数非法' });
    const first = await dbGet('SELECT MIN(date(updated_at)) AS d FROM saves WHERE user_id = ?', [userId]);
    if (!first || !first.d) return res.status(409).json({ error: '先进入游戏创建角色' });
    const startMs = Date.parse(String(first.d) + 'T00:00:00Z');
    const dayNo = Math.floor((Date.now() - startMs) / 86400000) + 1;
    if (day > dayNo) return res.status(409).json({ error: `第 ${day} 天奖励尚未解锁（今天第 ${dayNo} 天）` });
    const ins = await dbRun('INSERT OR IGNORE INTO week_goals (user_id, day, claimed_at) VALUES (?, ?, ?)', [userId, day, Date.now()]);
    if (!ins.changes) return res.status(409).json({ error: '该日奖励已领取' });
    const reward = WEEK_REWARDS[day - 1];
    await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + reward; });
    if (day === 7) await grantTitleBySource(userId, 'week7').catch(() => {});
    res.json({ ok: true, reward, title: day === 7 ? '七日筑基' : null });
  } catch (e: any) { console.error('week claim error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// 结义称号 seed（幂等）
db.run("INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES ('义结金兰', '{\"charmRate\":0.01}', 'sworn')");
db.run("INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES ('\u592a\u865a\u9b41\u9996', '{\"stoneRate\":0.05}', 'arena_week1')"); // [arenaweek] T16 \u5468\u699c\u7b2c 1 \u540d\u79f0\u53f7

// ─────────────────────────────────────────────────────────
// Y3A 奇遇日记 API（伴生页 /yl/apps/adventure/）：每日 3 次随机奇遇（白 60/蓝 25/紫 12/金 3%）。
// 一抽一行入 adventures（UNIQUE(player_id,date,count)=每日上限与并发双抽的唯一防线）；
// 收益=修为（按当层修为槽百分比，钳槽内）+固定灵石，updatePlayerSave 直接入档（saveLock 互斥 +
// gm_revision++ 促客户端拉新档）；入档失败补偿删行，本抽不作数可重试（alchemy 同款全或无）；
// 金色奇遇另授「福缘深厚」称号（player_titles 主键幂等）
// ─────────────────────────────────────────────────────────

// GET /api/adventure/list — 今日已抽记录 + 剩余次数 + 图鉴（全事件目录+本人收藏次数）
app.get('/api/adventure/list', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `adventure:list:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const date = bjDate(Date.now());
    const [rows, book, cdRow] = await Promise.all([
      dbAll('SELECT count, tier, event_key, exp_gain, stones, tickets, bonus_text FROM adventures WHERE player_id = ? AND date = ? ORDER BY count LIMIT ?', [userId, date, ADVENTURE_DAILY_MAX]),
      dbAll('SELECT event_key, COUNT(*) AS times FROM adventures WHERE player_id = ? GROUP BY event_key ORDER BY MIN(id) LIMIT 100', [userId]),
      dbGet('SELECT MAX(drawn_at) AS t FROM adventures WHERE player_id = ?', [userId]), // [r057] 冷却基准
    ]);
    const draws = (rows || []).map((r: any) => {
      const ev = ADVENTURE_EVENTS.find((e) => e.key === String(r.event_key || ''));
      const t = adventureTierByKey(r.tier);
      return {
        count: Number(r.count) || 0,
        tier: String(r.tier || ''),
        tierName: t ? t.name : String(r.tier || ''),
        eventKey: String(r.event_key || ''),
        text: ev ? ev.text : String(r.event_key || ''),
        expGain: Math.max(0, Number(r.exp_gain) || 0),
        stones: Math.max(0, Number(r.stones) || 0),
        tickets: Math.max(0, Number(r.tickets) || 0),
        bonusText: String(r.bonus_text || ''),
      };
    });
    const collected: Record<string, number> = {};
    for (const b of book || []) collected[String(b.event_key || '')] = Math.max(0, Number(b.times) || 0);
    res.json({
      date,
      drawn: draws.length,
      dailyMax: ADVENTURE_DAILY_MAX,
      cdLeft: Math.max(0, ADVENTURE_COOLDOWN_MS - (Date.now() - Math.max(0, Number(cdRow?.t) || 0))), // [r057] 毫秒
      draws,
      book: ADVENTURE_EVENTS.map((e) => {
        const t = adventureTierByKey(e.tier);
        return {
          key: e.key,
          tier: e.tier,
          tierName: t ? t.name : '',
          text: e.text,
          times: collected[e.key] || 0,
          collected: (collected[e.key] || 0) > 0,
        };
      }),
      tiers: ADVENTURE_TIERS.map((t) => ({ key: t.key, name: t.name, weight: t.weight,
        stonesMin: t.stonesMin, stonesMax: t.stonesMax,
        expRateMin: t.expRateMin, expRateMax: t.expRateMax,
        tickets: t.tickets, bonusChance: t.bonusChance, bonusTickets: t.bonusTickets })),
    });
  } catch (e: any) {
    console.error('adventure list error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

// GET /api/adventure/draw — 抽一次奇遇（每日 3 次）：抽品阶 → 取事件 → 收益入档 → 落账本
app.get('/api/adventure/draw', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `adventure:draw:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const date = bjDate(Date.now());
    const prev = await dbGet('SELECT COALESCE(MAX(count), 0) AS c FROM adventures WHERE player_id = ? AND date = ?', [userId, date]);
    const drawn = Math.max(0, Math.floor(Number(prev?.c) || 0));
    if (drawn >= ADVENTURE_DAILY_MAX) return res.status(409).json({ error: `今日奇遇已抽满 ${ADVENTURE_DAILY_MAX} 次，明日再来` });
    // [r057] 冷却 30 分钟：本人最近一次抽取时间（drawn_at）距今不足冷却则拒绝（409 文案带剩余秒数）
    const cdRow = await dbGet('SELECT MAX(drawn_at) AS t FROM adventures WHERE player_id = ?', [userId]);
    const cdMs = Date.now() - Math.max(0, Number(cdRow?.t) || 0);
    if (cdMs < ADVENTURE_COOLDOWN_MS) return res.status(409).json({ error: `奇遇冷却中，还需 ${Math.ceil((ADVENTURE_COOLDOWN_MS - cdMs) / 1000)} 秒` });
    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let sd0: any = null;
    try { sd0 = JSON.parse(row.save_data); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    // [r057] 消耗检查：当层修为槽 × ADVENTURE_COST_RATE，修为不足拒绝（锁内入档时同式重算兜底）
    const nr0 = normalizeRealm(sd0 && typeof sd0.player === 'object' ? sd0.player : null);
    const cost = Math.max(1, Math.floor(nr0.maxExp * ADVENTURE_COST_RATE));
    if (Math.max(0, Math.floor(Number(nr0.exp) || 0)) < cost) return res.status(409).json({ error: '修为不足，无法抽取' });
    const tier = drawAdventureTier(Math.random);
    const ev = pickAdventureEvent(tier.key, Math.random);
    // 0.8.6：数值区间化 + 额外珍宝（抽奖券 / 展示用珍宝名）
    const crit = Math.random() < ADVENTURE_CRIT_RATE; // [r057] 暴击：灵石与修为收益双倍
    const stones = funRandInt(tier.stonesMin, tier.stonesMax, Math.random) * (crit ? 2 : 1);
    const expRate = funRandFloat(tier.expRateMin, tier.expRateMax, Math.random);
    const tickets = Math.max(0, Math.floor(tier.tickets)) + (Math.random() < tier.bonusChance ? Math.max(0, Math.floor(tier.bonusTickets)) : 0);
    const bonusText = Math.random() < tier.bonusChance ? ADVENTURE_BONUS_TEXTS[funRandInt(0, ADVENTURE_BONUS_TEXTS.length - 1, Math.random)] : '';
    // 落账本先行占位：UNIQUE(player_id,date,count) 冲突=并发双抽，只一方生效（另一方 409 重试）
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun(
        'INSERT INTO adventures (player_id, date, count, tier, event_key, exp_gain, stones, tickets, bonus_text, drawn_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)', // [r057] 加 drawn_at
        [userId, date, drawn + 1, tier.key, ev.key, stones, tickets, bonusText, Date.now()]
      );
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '手速太快，奇遇正在展开，请再试一次' });
      throw e;
    }
    // 收益入档（锁内重算修为钳制，防并发存档窗口差）：失败补偿删行，本抽不作数可重试
    let short = false;
    let expGain = 0;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') { short = true; return; }
      const nrNow = normalizeRealm(sd.player);
      // [r057] 先扣消耗（与入档前检查同式重算，锁内权威），再发收益；失败走外层补偿删行（全或无）
      const costNow = Math.max(1, Math.floor(nrNow.maxExp * ADVENTURE_COST_RATE));
      if (Math.max(0, Math.floor(Number(sd.player.exp) || 0)) < costNow) { short = true; return; }
      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) - costNow;
      expGain = adventureExpGainRate(expRate, nrNow.maxExp, Math.max(0, Math.floor(Number(sd.player.exp) || 0)));
      if (crit) expGain = Math.min(expGain * 2, Math.max(0, nrNow.maxExp - Math.max(0, Math.floor(Number(sd.player.exp) || 0))));
      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + expGain;
      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + stones;
      if (tickets > 0) sd.player.lotteryTickets = (Number(sd.player.lotteryTickets) || 0) + tickets;
    });
    if (!paid.ok || short) {
      await dbRun('DELETE FROM adventures WHERE id = ?', [ins.lastID]).catch(() => {});
      return res.status(409).json({ error: paid.error === 'No save found' ? '请先进游戏创建角色' : '奇遇结算失败，请重试' });
    }
    const upd = await dbRun('UPDATE adventures SET exp_gain = ? WHERE id = ?', [expGain, ins.lastID]); // 回填实际入档修为（失败仅展示列残留 0，不影响收益）
    if (!upd.changes) console.error('adventure draw exp backfill missed:', ins.lastID);
    let titleGranted = false;
    if (tier.key === 'gold') titleGranted = await grantTitleBySource(userId, 'adventure_gold');
    res.json({
      ok: true,
      count: drawn + 1,
      left: Math.max(0, ADVENTURE_DAILY_MAX - drawn - 1),
      tier: tier.key,
      tierName: tier.name,
      eventKey: ev.key,
      text: ev.text,
      expGain,
      stones,
      tickets,
      bonusText,
      crit,
      cost,
      titleGranted,
    });
  } catch (e: any) {
    console.error('adventure draw error:', e?.message || e);
    if (!res.headersSent) res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// Y3A 离线收益 API（伴生页 /yl/apps/offline/）：按上次存档(saves.updated_at)到当前的离线时长结算，
// 基础 4.8% 当层修为槽/小时（时长上限 8h；月卡 12h 为判定桩，暂无月卡体系恒关）；灵石=修为×10%。
// 领取=先守卫推进 saves.offline_claimed_until（防并发双领唯一防线）→ 修为+灵石一笔入档
// （updatePlayerSave saveLock 互斥 + gm_revision++ 促客户端拉新档）→ 回执邮件（失败不影响账）
// ─────────────────────────────────────────────────────────

// GET /api/offline/report — 离线收益明细预览（不落账）。WUDAO 增强：月卡判定接线（saves.month_card_until，
// 有效期内上限 12h + 效率 100%=6%/h；无月卡 8h + 4.8%/h 与改前一致）+ 境界差值提示（离线叠加后修为满槽/
// 第九层满槽=已满足突破条件）
app.get('/api/offline/report', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `offline:report:${req.user?.id ?? req.ip}` }), (req: any, res: any) => {
  db.get('SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at FROM saves WHERE user_id = ?', [req.user.id], async (err: any, row: any) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let p: any;
    try { p = JSON.parse(row.save_data)?.player ?? {}; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    const nr = normalizeRealm(p);
    const nowMs = Date.now();
    const mc = hasMonthCard(row.month_card_until, nowMs);
    const capHours = offlineCapHours(mc);
    const ratePerHour = offlineRatePerHour(mc);
    // ★ R-021：锚点优先取「真实离开时刻」last_seen_at（心跳存档不再刷新它）；
    //   缺失 / 已领覆盖时逐位回落 updated_at。offlineWindow/offlineRewards 本体未动。
    const ylAnc = offlineAnchor(parseDbTimeMs(row.updated_at), row.last_seen_at, row.last_resume_at, row.offline_claimed_until, nowMs);
    const win = offlineWindow(ylAnc.anchorMs, row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, ylAnc.endMs);
    const rw = win ? offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour) : null;
    // Y21：活动倍率预览（与 claim 同一 resolveEventMults 口径；修为叠乘后仍钳槽内防溢出；引擎读取失败按 ×1 保底）
    let evMult = { events: [] as any[], expMult: 1, stonesMult: 1 };
    try { evMult = await resolveEventMults(nowMs); } catch { /* 保底 ×1 */ }
    // Y6B：师徒加成/出师增益预览（与 claim 同口径；读取失败 ×1 保底）
    let mnG = { expMult: 1, stonesMult: 1 };
    try { mnG = await resolveMentorGains(req.user.id, nowMs); } catch { /* 保底 ×1 */ }
    const shownExpGain = rw ? Math.min(actApplyGain(rw.expGain, evMult.expMult * mnG.expMult), Math.max(0, nr.maxExp - nr.exp)) : 0;
    const shownStonesGain = rw ? actApplyGain(rw.stonesGain, evMult.stonesMult * mnG.stonesMult) : 0;
    const bt = offlineBreakthroughHint(nr.realmIndex, nr.realmLevel, nr.exp, nr.maxExp, shownExpGain, REALM_ORDER_FOR_RANKING.length);
    res.json({
      now: nowMs,
      lastSaveAt: row.updated_at ?? null,
      from: win ? win.startMs : null,
      windowMs: win ? win.windowMs : 0,
      anchorSource: ylAnc.source, // R-021 只读诊断：last_seen_at=用真实离开时刻 / updated_at=回落旧口径
      anchorAt: ylAnc.anchorMs,   // R-021 只读诊断：实际锚点毫秒
      windowEndAt: ylAnc.endMs,   // R-021 只读诊断：窗口末端毫秒
      hours: rw ? rw.hours : 0,
      capHours,
      capped: rw ? rw.capped : false,
      monthCard: mc,
      monthCardUntil: row.month_card_until != null && Number.isFinite(Number(row.month_card_until)) ? Number(row.month_card_until) : null,
      realm: nr.realm,
      realmLevel: nr.realmLevel,
      exp: nr.exp,
      maxExp: nr.maxExp,
      expGain: shownExpGain,
      stonesGain: shownStonesGain,
      claimable: !!rw && rw.claimable,
      ratePerHourPct: Math.round(ratePerHour * 1000) / 10,
      stoneRatio: OFFLINE_STONE_RATIO,
      eventMults: { exp: evMult.expMult, stones: evMult.stonesMult }, // Y21：当前活动倍率（×1=无活动）
      breakthrough: bt, // { ready, hint }：ready=true 即"离线中已满足突破条件"（第九层+修为满槽，可渡劫）
    });
  });
});

// POST /api/offline/claim — 领取离线收益（全或无：标记推进失败/入档失败均补偿回退可重试）。
// WUDAO 增强：结算参数按月卡判定实时取（上限/速率），回执邮件文案随参数、不再写死 4.8%/8h
app.post('/api/offline/claim', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `offline:claim:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const row = await dbGet('SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let p: any;
    try { p = JSON.parse(row.save_data)?.player ?? {}; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    const nr = normalizeRealm(p);
    const nowMs = Date.now();
    const mc = hasMonthCard(row.month_card_until, nowMs);
    const capHours = offlineCapHours(mc);
    const ratePerHour = offlineRatePerHour(mc);
    // ★ R-021：与 /api/offline/report 同一锚点口径（预览与领取必须一致，否则出现"看得到领不到"）
    const ylAnc = offlineAnchor(parseDbTimeMs(row.updated_at), row.last_seen_at, row.last_resume_at, row.offline_claimed_until, nowMs);
    const win = offlineWindow(ylAnc.anchorMs, row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, ylAnc.endMs);
    if (!win) return res.status(409).json({ error: '暂无可领的离线收益' });
    const rw = offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour);
    if (!rw.claimable) return res.status(409).json({ error: '离线时长不足或收益为零（至少离线 5 分钟）' });
    // Y21：活动倍率（结算自动应用；引擎读取失败按 ×1 保底，不阻塞领取）
    const evMult = await resolveEventMults(nowMs).catch(() => ({ events: [] as any[], expMult: 1, stonesMult: 1 }));
    // Y6B：师徒加成/出师增益（读取失败 ×1 保底，不阻塞领取）
    const mnG = await resolveMentorGains(userId, nowMs).catch(() => ({ expMult: 1, stonesMult: 1 }));
    const claimedUntil = win.startMs + rw.effectiveMs;
    // 1) 守卫推进已领标记（单语句原子：旧值必须小于新值，并发双领只一方生效）
    const mark = await dbRun(
      'UPDATE saves SET offline_claimed_until = ? WHERE user_id = ? AND (offline_claimed_until IS NULL OR offline_claimed_until < ?)',
      [claimedUntil, userId, claimedUntil]
    );
    if (!mark.changes) return res.status(409).json({ error: '该段离线收益已领取' });
    // 2) 修为+灵石一笔入档（锁内按新档重算钳制；Y21 活动倍率叠乘后修为仍钳槽内防溢出）；失败补偿回退标记可重试
    let applied: { expGain: number; stonesGain: number } | null = null;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') return;
      const nrNow = normalizeRealm(sd.player);
      const r = offlineRewards(nrNow.maxExp, nrNow.exp, win.windowMs, capHours, ratePerHour);
      const gExp = Math.min(actApplyGain(r.expGain, evMult.expMult * mnG.expMult), Math.max(0, nrNow.maxExp - nrNow.exp));
      const gStones = actApplyGain(r.stonesGain, evMult.stonesMult * mnG.stonesMult);
      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + gExp;
      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + gStones;
      applied = { expGain: gExp, stonesGain: gStones };
    });
    if (!paid.ok || !applied) {
      await dbRun('UPDATE saves SET offline_claimed_until = ? WHERE user_id = ?', [row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, userId]).catch(() => {});
      return res.status(409).json({ error: paid.error === 'No save found' ? '请先进游戏创建角色' : '领取失败，请重试' });
    }
    // [act087] C 灵玉阁掉玉挂点（入账点：离线收益入账成功后；/api/offline/report 预览两处
    // actApplyGain 保持裸调用不挂——挂预览必双计，门禁断言）
    if (applied.stonesGain > 0) actDropTokens(userId, applied.stonesGain, nowMs).catch((e: any) => console.error('act drop tokens (offline) error:', e?.message || e));
    // 3) 回执邮件（奖励已入档，邮件仅为回执；发送失败不影响领取，只记日志）；附带突破差值提示
    const bt = offlineBreakthroughHint(nr.realmIndex, nr.realmLevel, nr.exp, nr.maxExp, applied.expGain, REALM_ORDER_FOR_RANKING.length);
    const btLine = bt.ready ? `\n\n⚡ ${bt.hint}` : (bt.hint ? `\n\n· ${bt.hint}` : '');
    const evLine = (evMult.expMult > 1 || evMult.stonesMult > 1) ? `\n· 限时活动加成已生效：修为 ×${evMult.expMult} / 灵石 ×${evMult.stonesMult}` : '';
    insertMail(userId, '闭关修炼 · 离线收益',
      `道友离线修行有时，天地灵气自行灌体：\n\n· 修为 +${applied.expGain}\n· 灵石 +${applied.stonesGain}（已直接入档，回游戏即可见）${evLine}\n\n（按当层修为槽 ${Math.round(ratePerHour * 1000) / 10}%/小时结算，时长上限 ${capHours} 小时${mc ? '（月卡）' : ''}）${btLine}`,
      'system', 0).catch((e: any) => console.error('offline claim mail error:', e?.message || e));
    res.json({ ok: true, expGain: applied.expGain, stonesGain: applied.stonesGain, claimedUntil, monthCard: mc, capHours, ratePerHourPct: Math.round(ratePerHour * 1000) / 10, breakthrough: bt, eventMults: { exp: evMult.expMult, stones: evMult.stonesMult } });
  } catch (e: any) {
    console.error('offline claim error:', e?.message || e);
    if (!res.headersSent) res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// Y19 成就系统 API（伴生页 /yl/apps/ach/ 用）：五类各 10 项共 50 项，达成从 stats_daily/daily_quests/saves
// 惰性推导（零新增埋点、零新增统计表）；achievement_claimed 主键幂等防重复领奖，奖励走邮件（灵石阶梯）
// ─────────────────────────────────────────────────────────

// GET /api/achievements — 全 50 项 + 每类进度 + 可领取清单（惰性计算，一页全量）
app.get('/api/achievements', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `ach:list:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  try {
    const userId = req.user.id;
    const [sum, questCnt, saveRow, claimedRows] = await Promise.all([
      dbGet('SELECT SUM(minutes) AS m, SUM(kills) AS k, SUM(silver_gain) AS s FROM stats_daily WHERE player_id = ?', [userId]),
      dbGet("SELECT COUNT(*) AS c FROM daily_quests WHERE user_id = ? AND done = 1 AND quest_key NOT LIKE ?", [userId, 'chest_%']),
      dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
      dbAll('SELECT ach_id FROM achievement_claimed WHERE user_id = ? LIMIT 100', [userId]),
    ]);
    let realmIndex = -1;
    let realmLevel = 1; // [r122] 当层层数（save.player.realmLevel，与 rankings 同源；无档=1）
    let realmName = '未开始';
    if (saveRow) {
      try {
        const p = JSON.parse(String(saveRow.save_data))?.player;
        const r = p?.realm;
        const i = typeof r === 'string' ? REALM_ORDER_FOR_RANKING.indexOf(r) : -1;
        if (i >= 0) {
          realmIndex = i; realmName = r;
          const lv = Math.floor(Number(p?.realmLevel));
          if (Number.isFinite(lv)) realmLevel = Math.max(1, lv);
        }
      } catch { /* 坏存档按无境界处理，不阻塞列表 */ }
    }
    const view = buildAchievementsView(
      achTotalsFrom({ minutes: sum?.m, kills: sum?.k, silver: sum?.s, quests: questCnt?.c, realmIndex, totalLevel: realmIndex >= 0 ? realmIndex * 9 + realmLevel : 0 }), // [r122] 总等级=境界序×9+层；无档=0
      (claimedRows || []).map((r: any) => String(r.ach_id))
    );
    res.json({ realm: { name: realmName, index: realmIndex }, ...view });
  } catch (e: any) {
    console.error('achievements list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/achievements/claim {id?} — 领奖：缺省=一键领取全部达成未领，指定 id=领单项；
// 服务端重算达成状态（不信任客户端）；占位=achievement_claimed 主键单语句 INSERT OR IGNORE
// （并发双击只一方 changes>0 生效）；发信失败补偿删占位可重试（mailClaimCore/alchemy claim 补偿式同款）
app.post('/api/achievements/claim', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `ach:claim:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const [sum, questCnt, saveRow, claimedRows] = await Promise.all([
      dbGet('SELECT SUM(minutes) AS m, SUM(kills) AS k, SUM(silver_gain) AS s FROM stats_daily WHERE player_id = ?', [userId]),
      dbGet("SELECT COUNT(*) AS c FROM daily_quests WHERE user_id = ? AND done = 1 AND quest_key NOT LIKE ?", [userId, 'chest_%']),
      dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
      dbAll('SELECT ach_id FROM achievement_claimed WHERE user_id = ? LIMIT 100', [userId]),
    ]);
    let realmIndex = -1;
    let realmLevel = 1; // [r122] 当层层数（save.player.realmLevel，与 rankings 同源；无档=1）
    if (saveRow) {
      try {
        const p = JSON.parse(String(saveRow.save_data))?.player;
        const r = p?.realm;
        realmIndex = typeof r === 'string' ? REALM_ORDER_FOR_RANKING.indexOf(r) : -1;
        if (realmIndex >= 0) {
          const lv = Math.floor(Number(p?.realmLevel));
          if (Number.isFinite(lv)) realmLevel = Math.max(1, lv);
        }
      } catch { /* 坏存档按无境界处理 */ }
    }
    const view = buildAchievementsView(
      achTotalsFrom({ minutes: sum?.m, kills: sum?.k, silver: sum?.s, quests: questCnt?.c, realmIndex, totalLevel: realmIndex >= 0 ? realmIndex * 9 + realmLevel : 0 }), // [r122] 总等级=境界序×9+层；无档=0
      (claimedRows || []).map((r: any) => String(r.ach_id))
    );
    const ids = achPickClaimable(view, req.body?.id);
    if (!ids.length) {
      return res.status(409).json({ error: req.body?.id ? '该成就未达成或奖励已领取' : '暂无可领取的成就奖励' });
    }
    const byId = new Map(ACH_DEFS.map((d) => [d.id, d]));
    const claimedNow: string[] = [];
    for (const id of ids) {
      const r = await dbRun('INSERT OR IGNORE INTO achievement_claimed (user_id, ach_id) VALUES (?, ?)', [userId, id]);
      if (r.changes > 0) claimedNow.push(id); // 并发双领只有一方生效
    }
    if (!claimedNow.length) return res.status(409).json({ error: '奖励已领取' });
    const stones = claimedNow.reduce((a, id) => a + (byId.get(id)?.reward || 0), 0);
    const names = claimedNow.map((id) => byId.get(id)?.name || id).join('、');
    try {
      await insertMail(userId, '成就达成奖励',
        `恭喜道友达成成就：${names}！\n\n· 奖励灵石 ×${stones}（点击下方领取）\n\n仙途漫漫，愿百尺竿头更进一步。`,
        'system', stones);
    } catch (e: any) {
      console.error('achievements claim mail error:', e?.message || e);
      // 补偿：回滚本次领取占位，玩家可重试领取
      for (const id of claimedNow) await dbRun('DELETE FROM achievement_claimed WHERE user_id = ? AND ach_id = ?', [userId, id]).catch(() => {});
      return res.status(500).json({ error: '发奖失败，请重试' });
    }
    res.json({ ok: true, claimed: claimedNow, stones });
  } catch (e: any) {
    console.error('achievements claim error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});


// ─────────────────────────────────────────────────────────
// Y18 妖灵宠物 API（伴生页 /yl/apps/pet/）：服务端权威轻量版——宠物数据全在 pets 表，游戏内展示走伴生页，
// 喂养扣灵石（alchemy/start 同款补偿式事务），精魄/奖励走邮件名目；实际战斗加成待客户端接入（边界见报告）。
// 喂养记录=pet_care_log（写入后裁剪至 PET_CARE_LOG_KEEP 条防膨胀）。
// ─────────────────────────────────────────────────────────

// Y18 喂养/嬉戏/收养流水（fire-and-forget 自吞异常；写入后裁剪保留最近 PET_CARE_LOG_KEEP 条）
function logPetCare(playerId: number, kind: string, detail: string): void {
  dbRun('INSERT INTO pet_care_log (player_id, kind, detail) VALUES (?, ?, ?)', [playerId, kind, clampPetDetail(detail)])
    .then(() => dbRun(
      'DELETE FROM pet_care_log WHERE player_id = ? AND id NOT IN (SELECT id FROM pet_care_log WHERE player_id = ? ORDER BY id DESC LIMIT ?)',
      [playerId, playerId, PET_CARE_LOG_KEEP]
    ))
    .catch((e: any) => console.error('pet care log error:', e?.message || e));
}

function petView(p: any): any {
  return p ? {
    name: String(p.name),
    rarity: String(p.rarity),
    level: petLevel(p.hunger),
    exp: Number(p.exp) || 0,
    hunger: Number(p.hunger) || 0,
    bond: Number(p.bond) || 0,
    aptitude: Number(p.aptitude) || 0,
    merged: Number(p.merged) || 0,
  } : null;
}

// GET /api/pet — 我的宠物全量（宠物卡 + 今日嬉戏次数 + 喂养记录 + 常量表）
app.get('/api/pet', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `pet:me:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const pet = await dbGet('SELECT name, rarity, hunger, exp, bond, aptitude, merged, rune_active, created_at FROM pets WHERE player_id = ?', [userId]);
    const today = petDate(Date.now());
    const [play, logs, exped] = await Promise.all([
      dbGet('SELECT times, tease, brush, talk, bought FROM pet_play_log WHERE player_id = ? AND date = ?', [userId, today]),
      dbAll('SELECT kind, detail, created_at FROM pet_care_log WHERE player_id = ? ORDER BY id DESC LIMIT 20', [userId]),
      dbGet('SELECT started_at, claimed FROM pet_spirit_exped WHERE player_id = ? AND date = ?', [userId, today]),
    ]);
    res.json({
      pet: petView(pet),
      createdAt: pet?.created_at ?? null,
      playTimes: Math.min(PET_PLAY_DAILY_MAX, Number(play?.times) || 0),
      careLog: (logs || []).map((l: any) => ({ kind: String(l.kind), detail: String(l.detail), createdAt: l.created_at })),
      // R-018 出口回显：与 r018SpiritSync() 写入存档的 payload 同源同式（纯函数，不写库）
      spirit: (pet && Number(pet.merged) === 0)
        ? Object.assign({ level: petLevel(pet.hunger), rarity: String(pet.rarity) },
            r018bSpiritBonus(pet.rarity, petLevel(pet.hunger), pet.bond, pet.aptitude, pet.rune_active))
        : null,
      playQuota: {
        tease: Math.min(1, Number(play?.tease) || 0),
        brush: Math.min(1, Number(play?.brush) || 0),
        talk: Math.min(1, Number(play?.talk) || 0),
        bought: Math.min(R018_BUY_DAILY_MAX, Number(play?.bought) || 0),
      },
      exped: exped ? {
        startedAt: Number(exped.started_at) || 0,
        claimed: Number(exped.claimed) || 0,
        ready: (Number(exped.claimed) || 0) === 0 && Date.now() >= (Number(exped.started_at) || 0) + R018_EXPED_MS,
      } : null,
      rune: (pet && Number(pet.merged) === 0)
        ? { active: String(pet.rune_active || ''), list: r018bRuneList(petLevel(pet.hunger)) }
        : null,
      consts: {
        feedCost: PET_FEED_COST, hungerPerFeed: PET_HUNGER_PER_FEED, hungerMax: PET_HUNGER_MAX,
        levelDivisor: PET_LEVEL_DIVISOR, playDailyMax: PET_PLAY_DAILY_MAX, playBond: PET_PLAY_BOND,
        battleLevel: PET_BATTLE_LEVEL,
        bondMax: R018_BOND_MAX, aptitudeMax: R018_APTITUDE_MAX, aptitudeCost: R018_APTITUDE_COST,
        buyCost: R018_BUY_COST, buyDailyMax: R018_BUY_DAILY_MAX,
        expedCost: R018_EXPED_COST, expedMs: R018_EXPED_MS, expedHunger: R018_EXPED_HUNGER,
        expedBond: R018_EXPED_BOND, expedExp: R018_EXPED_EXP,
        convert: R018_CONVERT, feedTiers: R018_FEED_TIERS, playKinds: R018_PLAY_KINDS,
        runeCost: R018B_RUNE_COST, runeTable: R018B_RUNE_TABLE,
        // [r078] R-078 消耗回显：收养 / 归位 的灵石价（引用 r071 常量，客户端按钮据此显示与置灰）
        adoptCost: R071_ADOPT_COST, awayCost: R071_AWAY_COST,
      },
    });
  } catch (e: any) {
    console.error('pet get error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/pet/adopt — 收养：每玩家一只 active（UNIQUE(player_id) 原子防线，并发双收只放行一方）；
// 随机仙兽名 + 品阶权重 凡70/灵25/仙5
app.post('/api/pet/adopt', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => `pet:adopt:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const existed: any = await dbGet('SELECT id, merged FROM pets WHERE player_id = ?', [userId]);
    if (existed && Number(existed.merged) === 0) return res.status(409).json({ error: '你已有灵宠相伴' });
    // R-071 收养花灵石（照抄 r018 补偿式扣费口径：预检 → saveLock 内二次校验 → 失败退费）
    const _arow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!_arow) return res.status(404).json({ error: '请先进游戏创建角色' });
    let _abal = 0;
    try { _abal = Number(JSON.parse(_arow.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (_abal < R071_ADOPT_COST) return res.status(409).json({ error: `灵石不足：收养需 ${R071_ADOPT_COST}，现有 ${_abal}` });
    let _ashort = false;
    const _apaid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < R071_ADOPT_COST) { _ashort = true; return; }
      sd.player.spiritStones = b - R071_ADOPT_COST;
    });
    if (!_apaid.ok || _ashort) return res.status(409).json({ error: _ashort ? '灵石不足' : (_apaid.error === 'No save found' ? '请先进游戏创建角色' : '收养失败，请重试') });
    // R-072 归位后（merged=1）释放槽位：删墓碑行后重新 INSERT（UNIQUE 仍是并发唯一防线）
    if (existed) await dbRun('DELETE FROM pets WHERE player_id = ? AND merged = 1', [userId]);
    const name = rollPetName();
    const rarity = rollPetRarity();
    try {
      await dbRun('INSERT INTO pets (player_id, name, rarity, level, exp, hunger, bond) VALUES (?, ?, ?, 0, 0, 0, 0)', [userId, name, rarity]);
    } catch (e: any) {
      // INSERT 失败（并发双收养 / 已存在 active 行）⇒ 退回已扣的收养费
      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + R071_ADOPT_COST; });
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '你已有灵宠相伴' });
      throw e;
    }
    const rarityLabel = rarity === '仙' ? '仙品' : rarity === '灵' ? '灵品' : '凡品';
    logChronicle(userId, String(req.user.username || '').slice(0, 32), `【妖灵】仙山偶遇${rarityLabel}灵宠「${name}」，结缘收养，自此相伴修行`); // Y16 江湖志
    logPetCare(userId, 'adopt', `收养灵宠「${name}」（${rarityLabel}）`);
    res.json({ ok: true, pet: petView({ name, rarity, hunger: 0, exp: 0, bond: 0 }), cost: R071_ADOPT_COST });
  } catch (e: any) {
    console.error('pet adopt error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/pet/feed — 喂养：扣灵石 500 → 喂食度 +30（到 9999 拒喂不扣费）→ level=floor(hunger/100)。
// 事务口径=alchemy/start 同款补偿式：预检 → 扣费（saveLock 互斥）→ 单语句原子 UPDATE（RHS 按旧行值求值，MIN 封顶）→
// 宠物行缺失则补偿退费；恰跨 5 级触发一次性「妖灵精魄」（bond+20 + 邮件 1000 灵石，实战加成待客户端接入）
app.post('/api/pet/feed', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `pet:feed:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const _feed = r018FeedTier(req.body?.tier);
    const pet: any = await dbGet('SELECT id, name, hunger, level, merged FROM pets WHERE player_id = ?', [userId]);
    if (pet && Number(pet.merged) > 0) return res.status(409).json({ error: '妖灵已归位，无法再喂养' });
    if (!pet) return res.status(404).json({ error: '请先收养一只灵宠' });
    if (!petFeedResult(pet.hunger).ok) return res.status(409).json({ error: `喂食度已达上限 ${PET_HUNGER_MAX}，灵宠已经饱足` });

    // 预检灵石余额（并发窗口由 updatePlayerSave 内闭包二次校验兜底）
    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    try { bal = Number(JSON.parse(row.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < _feed.cost) return res.status(409).json({ error: `灵石不足：需 ${_feed.cost}，现有 ${bal}` });

    // 扣费（saveLock 互斥 + gm_revision++ 促客户端拉新档）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < _feed.cost) { short = true; return; }
      sd.player.spiritStones = b - _feed.cost;
    });
    if (!paid.ok || short) {
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '喂养失败，请重试') });
    }

    // 喂养落库（单语句原子：RHS hunger 全按旧行值求值，MIN 封顶不溢出；并发喂养不丢更新）
    const upd = await dbRun(
      `UPDATE pets SET
         hunger = MIN(?, hunger + ?),
         exp = MIN(?, hunger + ?),
         level = CAST(MIN(?, hunger + ?) / ? AS INTEGER)
       WHERE player_id = ?`,
      [PET_HUNGER_MAX, _feed.hunger, PET_HUNGER_MAX, _feed.hunger, PET_HUNGER_MAX, _feed.hunger, PET_LEVEL_DIVISOR, userId]
    );
    if (!upd.changes) {
      // 补偿退费（宠物行异常缺失，理论不可达，防御性全或无）
      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + _feed.cost; });
      return res.status(404).json({ error: '请先收养一只灵宠' });
    }
    let fresh = await dbGet('SELECT name, rarity, hunger, exp, bond, aptitude, merged FROM pets WHERE player_id = ?', [userId]);
    let battleReached = false;
    // R-018 决策点 10 = C：妖灵精魄改为「每 10 级一次」（跨 10/20/…/90 各触发一次）
    const _miles = fresh ? r018Milestones(pet.level, petLevel(fresh.hunger)) : [];
    if (_miles.length > 0) {
      battleReached = true;
      for (const _m of _miles) {
        await dbRun('UPDATE pets SET bond = MIN(?, bond + ?) WHERE player_id = ?', [R018_BOND_MAX, R018_MILESTONE_BOND, userId]);
        logPetCare(userId, 'battle', `「${String(fresh.name)}」修至第 ${_m} 级，凝出妖灵精魄，羁绊 +${R018_MILESTONE_BOND}`);
        try {
          await insertMail(userId, '妖灵精魄',
            `灵宠「${String(fresh.name)}」喂食有成，修至第 ${_m} 级，凝出「妖灵精魄」！\n\n· 羁绊 +${R018_MILESTONE_BOND}（妖灵之力之基）\n· 灵石 ×${R018_MILESTONE_STONES}（点击下方领取）\n\n人宠同心，其利断金。`,
            'system', R018_MILESTONE_STONES);
        } catch (e: any) {
          console.error('pet battle mail error:', e?.message || e); // 邮件失败不影响喂养本体（bond 已落库）
        }
      }
      fresh = await dbGet('SELECT name, rarity, hunger, exp, bond, aptitude, merged FROM pets WHERE player_id = ?', [userId]); // 精魄 bond 后回读
    }
    logPetCare(userId, 'feed', `喂食「${String(pet.name)}」，喂食度 +${PET_HUNGER_PER_FEED}`);
    res.json({ ok: true, pet: petView(fresh), battleReached, milestones: _miles, spirit: await r018SpiritSync(userId) });
  } catch (e: any) {
    console.error('pet feed error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/pet/play — 嬉戏：每日 3 次（pet_play_log PK(player_id,date) 单语句原子闸门，times<3 才放行，
// 封顶后 changes=0 拒绝）→ 羁绊 +5；宠物行缺失补偿回退次数占位
app.post('/api/pet/play', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `pet:play:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const date = petDate(Date.now());
    const _kind = r018PlayKind(req.body?.kind);
    const _buy = !!req.body?.buy;
    const _pet0: any = await dbGet('SELECT id, name, hunger, bond, merged FROM pets WHERE player_id = ?', [userId]);
    if (!_pet0) return res.status(404).json({ error: '请先收养一只灵宠' });
    if (Number(_pet0.merged) > 0) return res.status(409).json({ error: '妖灵已归位，无法再互动' });
    if (!_buy && petLevel(_pet0.hunger) < _kind.unlock) return res.status(409).json({ error: `「${_kind.name}」需妖灵达到 ${_kind.unlock} 级` });
    let _gateSql: string, _gateArgs: any[];
    if (_buy) {
      const srow0 = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
      if (!srow0) return res.status(404).json({ error: '请先进游戏创建角色' });
      let bal0 = 0;
      try { bal0 = Number(JSON.parse(srow0.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }
      if (bal0 < R018_BUY_COST) return res.status(409).json({ error: `灵石不足：需 ${R018_BUY_COST}，现有 ${bal0}` });
      _gateSql = 'INSERT INTO pet_play_log (player_id, date, times, bought) VALUES (?, ?, 1, 1) ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1, bought = bought + 1 WHERE bought < ?';
      _gateArgs = [userId, date, R018_BUY_DAILY_MAX];
    } else {
      _gateSql = "INSERT INTO pet_play_log (player_id, date, times, tease, brush, talk, bought) VALUES (?, ?, 1, ?, ?, ?, 0) ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1, tease = tease + excluded.tease, brush = brush + excluded.brush, talk = talk + excluded.talk WHERE (CASE ? WHEN 'tease' THEN tease WHEN 'brush' THEN brush ELSE talk END) < 1";
      _gateArgs = [userId, date, _kind.key === 'tease' ? 1 : 0, _kind.key === 'brush' ? 1 : 0, _kind.key === 'talk' ? 1 : 0, _kind.key];
    }
    const gate = await dbRun(_gateSql, _gateArgs);
    if (!gate.changes) return res.status(409).json({ error: _buy ? `今日买额度已用完（每日 ${R018_BUY_DAILY_MAX} 次）` : `今日「${_kind.name}」已用过（每种每日 1 次免费），明日再来` });
    if (_buy) {
      let short0 = false;
      const paid0 = await updatePlayerSave(userId, (sd: any) => {
        const b = Number(sd.player?.spiritStones) || 0;
        if (b < R018_BUY_COST) { short0 = true; return; }
        sd.player.spiritStones = b - R018_BUY_COST;
      });
      if (!paid0.ok || short0) {
        await dbRun('UPDATE pet_play_log SET times = MAX(0, times - 1), bought = MAX(0, bought - 1) WHERE player_id = ? AND date = ?', [userId, date]);
        return res.status(409).json({ error: short0 ? '灵石不足' : '买额度失败，请重试' });
      }
    }
    const _extraH = _kind.extra === 'hunger' ? _kind.hunger : 0;
    const upd = await dbRun(
      `UPDATE pets SET
         bond = MIN(?, bond + ?),
         hunger = MIN(?, hunger + ?),
         exp = MIN(?, hunger + ?),
         level = CAST(MIN(?, hunger + ?) / ? AS INTEGER)
       WHERE player_id = ?`,
      [R018_BOND_MAX, _kind.bond, PET_HUNGER_MAX, _extraH, PET_HUNGER_MAX, _extraH, PET_HUNGER_MAX, _extraH, PET_LEVEL_DIVISOR, userId]
    );
    if (!upd.changes) {
      await dbRun('UPDATE pet_play_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?', [userId, date]); // 补偿回退占位可重试
      if (_buy) await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + R018_BUY_COST; });
      return res.status(404).json({ error: '请先收养一只灵宠' });
    }
    if (_kind.extra === 'exp' && _kind.exp > 0) {
      await updatePlayerSave(userId, (sd: any) => { if (sd.player) sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + _kind.exp; });
    }
    const fresh = await dbGet('SELECT name, rarity, hunger, exp, bond, aptitude, merged FROM pets WHERE player_id = ?', [userId]);
    const prow = await dbGet('SELECT times, tease, brush, talk, bought FROM pet_play_log WHERE player_id = ? AND date = ?', [userId, date]);
    const spirit = await r018SpiritSync(userId);
    logPetCare(userId, 'play', `${_buy ? '花费 ' + R018_BUY_COST + ' 灵石，' : ''}与「${fresh ? String(fresh.name) : '灵宠'}」${_kind.name}，羁绊 +${_kind.bond}`);
    res.json({
      ok: true,
      pet: petView(fresh),
      playTimes: Math.min(PET_PLAY_DAILY_MAX, Math.max(1, Number(prow?.times) || 0)),
      playQuota: {
        tease: Math.min(1, Number(prow?.tease) || 0),
        brush: Math.min(1, Number(prow?.brush) || 0),
        talk: Math.min(1, Number(prow?.talk) || 0),
        bought: Math.min(R018_BUY_DAILY_MAX, Number(prow?.bought) || 0),
      },
      spirit,
    });
  } catch (e: any) {
    console.error('pet play error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// T2 灵宠面板 API（灵宠列表 + 融合）：服务端权威面 = 视图投影（策划 §2.3/§3.1 公开系数）
// + 融合费定价（§2.4 + 用户 2026-09-29「基础 10000 起 / 以品阶为主 / 亲密度影响不大」）
// + 融合成功率与失败保底（§2.4，确定性非赌博 P3）+ 融合落库动作（扣灵石 / 材料消耗 / 标记）。
// 属性继承（等级取高 / 阶段晋升 / 技能继承）按策划 §2.1 P2 归客户端存档域 ⇒ 服务端只回 inheritHints，
// 不代写 player.pets（避免双写漂移；先例：战斗结算 Oy 在客户端）。
// ─────────────────────────────────────────────────────────

// GET /api/pet/spirit/list — 灵宠列表（面板采集面）。
// 语义：服务端 pets 权威行 → T2 视图（品阶 / 亲密度 / 气血 / 修为 / 融合状态 / 消耗预览）。
// 另回常量表，供客户端自算 §3.2 精确档位（服务端无 evolutionStage，只能出幼年期档）。
app.get('/api/pet/spirit/list', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `pet:spirit:list:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const rows = await dbAll('SELECT name, rarity, hunger, exp, bond, merged, merge_pity, created_at FROM pets WHERE player_id = ? ORDER BY id ASC LIMIT 50', [userId]);
    const spirits = (rows || []).map((r: any) => petT2SpiritView(r));
    res.json({
      ok: true,
      spirits,
      count: spirits.length,
      activeIndex: 0, // 服务端每玩家唯一一行 ⇒ 恒为主宠（策划 §2.2 主战宠）
      consts: {
        costBase: PET_T2_COST_BASE,               // 秘径 / 融合费基础 10000 灵石
        pathCostBase: PET_T2_PATH_BASE,           // [v2810] \u79d8\u5f84\u57fa\u7840 7500\uff08\u878d\u5408\u4ecd 10000\uff09
        affectionDivisor: PET_T2_AFFECTION_DIVISOR, // 亲密度弱因子分母（影响 ≤5%）
        rarityMultFuse: PET_FUSE_RARITY_MULT,     // 秘径品阶因子（主因子）
        stageMultFuse: PET_FUSE_STAGE_MULT,       // 秘径阶段因子（次因子）
        rarityMultMerge: PET_MERGE_RARITY_MULT,   // 融合费主宠品阶因子
        rarityIdxMap: PET_RARITY_IDX,             // 凡0/灵1/仙3
        rarityKo: PET_RARITY_KO,                  // 普0/稀1/传2/仙3
        stageCn: PET_STAGE_CN,                    // 幼年/成熟/完全体
        mergeRateSame: PET_MERGE_RATE_SAME,
        mergeRateLowStep: PET_MERGE_RATE_LOW_STEP,
        mergeRateHighStep: PET_MERGE_RATE_HIGH_STEP,
        mergeRateMin: PET_MERGE_RATE_MIN,
        mergePityLimit: PET_MERGE_PITY_LIMIT,
      },
    });
  } catch (e: any) {
    console.error('pet spirit list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/pet/spirit/merge — 灵宠融合（主宠保留 + 副宠消耗 + 融合费）。
// 请求体收口：subRarity 只认 凡/灵/仙（asStr + 白名单），忽略任何其它字段（防原型链污染）。
// 事务口径 = pet/feed 同款补偿式：预检余额 → 扣灵石（updatePlayerSave saveLock 互斥，含二次校验）
// → 单语句原子 UPDATE 结算（pity+1 或 清零 + sub_consumed+1 + merged 标记；守卫 merged=0 防重放）
// → 余额不足 / 宠物行缺失 → 补偿退费可重试。
// 成功率按策划 §2.4；失败保底由**服务端** merge_pity 把关（连续失败 3 次后第 4 次必成功）。
// 属性继承不回写服务端（策划 §2.1 P2）⇒ 成功时回 inheritHints 供客户端存档域落主宠。
app.post('/api/pet/spirit/merge', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `pet:spirit:merge:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const subRarity = asStr(req.body?.subRarity);
    if (!PET_RARITIES.includes(subRarity)) return res.status(400).json({ error: '副宠品阶非法（仅 凡/灵/仙）' });

    const pet: any = await dbGet('SELECT id, name, rarity, hunger, exp, bond, merged, merge_pity FROM pets WHERE player_id = ?', [userId]);
    if (!pet) return res.status(404).json({ error: '请先收养一只灵宠' });
    if (Number(pet.merged) > 0) return res.status(409).json({ error: '该灵宠已完成妖灵归位，不可再融合' });

    const aff = petT2Affection(pet.bond);
    const mainIdx = petRarityIdx(pet.rarity);
    const subIdx = petRarityIdx(subRarity);
    const cost = petT2MergeCost(pet.rarity, subIdx, aff);
    const rate = petT2MergeRate(mainIdx, subIdx);

    // 保底判定与掷骰（服务端权威：不信任客户端报数）
    const pityDue = petT2PityDue(pet.merge_pity);
    const roll = petT2Roll();
    const success = pityDue || roll < rate;

    // 单语句原子结算：RHS 全按旧行值求值；守卫 merged = 0 防并发重放（双击只一方 changes>0）。
    // ★ 顺序纪律（本环实测踩过）：**先结算、后扣费**，不是先扣费后结算。
    //   一旦「扣费成功」与「结算抛错」之间存在无补偿窗口，玩家会被扣钱却什么都没得到
    //   （实测：`sub_consumed` 列不存在时 UPDATE 抛错 ⇒ 500 且 10000 灵石已扣、未退回）。
    //   现序：结算失败（changes=0 或异常）→ 直接返回，**此时尚未扣费**，无需补偿、零资损；
    //   结算成功 → 再扣费，扣费失败才需要补偿回滚结算。补偿窗口缩到最短且方向唯一。
    // ★ T2 修复（0.8.9）：`merged` 改为**按成败**写入 —— 成功才归位（merged=1），
    //   失败保持 merged=0（仅 merge_pity+1）。
    //   病根：旧实现无条件 `merged = 1` ⇒ 第 1 次融合（无论成败）后 merged=1，
    //   第 2 次必被上方 `if (Number(pet.merged) > 0) return 409` 与 WHERE merged=0 双双挡下，
    //   merge_pity 永远到不了 3 ⇒ 策划 §2.4「连续失败 3 次后第 4 次必成功」保底形同虚设。
    //   sub_consumed 无论成败都 +1：策划 §2.4「失败：副宠消失」⇒ 副宠已被消耗（审计计数）。
    const nextPity = success ? 0 : Math.min(9999, Math.max(0, Math.floor(Number(pet.merge_pity) || 0)) + 1);
    let upd: { lastID: number; changes: number };
    try {
      upd = await dbRun(
        `UPDATE pets SET merged = ?, merge_pity = ?, sub_consumed = sub_consumed + 1 WHERE player_id = ? AND merged = 0`,
        [success ? 1 : 0, nextPity, userId]
      );
    } catch (e: any) {
      console.error('pet spirit merge settle error:', e?.message || e);
      return res.status(500).json({ error: '融合结算失败，请重试' }); // 未扣费，无资损
    }
    if (!upd.changes) {
      // 并发已归位 / 宠物行异常缺失 —— 未扣费，直接拒绝
      return res.status(409).json({ error: '融合状态已变更，请刷新后重试' });
    }

    // 扣融合费（saveLock 互斥 + gm_revision++ 促客户端拉新档）；扣费失败 → 补偿回滚结算（merged/pity/计数）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < cost) { short = true; return; }
      sd.player.spiritStones = b - cost;
    });
    if (!paid.ok || short) {
      await dbRun(
        'UPDATE pets SET merged = 0, merge_pity = ?, sub_consumed = MAX(0, sub_consumed - 1) WHERE player_id = ?',
        [Math.max(0, Math.floor(Number(pet.merge_pity) || 0)), userId]
      ).catch(() => {});
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '融合失败，请重试') });
    }

    const mainLevel = Math.floor(Math.max(0, Math.floor(Number(pet.hunger) || 0)) / PET_LEVEL_DIVISOR);
    logPetCare(userId, success ? 'merge' : 'merge_fail',
      `「${String(pet.name)}」融合${success ? '成功' : '失败'}（副宠 ${subRarity} 品阶，耗 ${cost} 灵石）`);

    res.json({
      ok: true,
      success,
      pity: pityDue,
      cost,
      rate,
      merged: success ? 1 : 0,
      mergePity: nextPity,
      // 服务端不回写灵宠属性（策划 §2.1 P2）；成功时给出客户端存档域的继承指令
      inheritHints: success ? {
        keepName: String(pet.name),
        keepLevel: mainLevel,
        rarity: String(pet.rarity),
        rarityIdx: mainIdx,
        affection: aff,
        subRarity,
        subRarityIdx: subIdx,
        note: '属性继承按策划 §2.1 P2 归客户端存档域，由客户端按 §2.4 继承表落主宠',
      } : null,
    });
  } catch (e: any) {
    console.error('pet spirit merge error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// Y4 渡劫天劫（伴生页 /yl/apps/rebirth/）：突破仪式化——第九层修为圆满 → 挑战天劫使者，
// 胜=服务端代写突破（realm/realmLevel/exp 结转，gm_revision++ 触发客户端拉新档）+ 全服公告 + 「渡劫飞升」称号；
// 败=10 分钟冷却。突破材料按任务书简化为修为门槛（不引入新材料；筑基奇物等材料门槛仍由客户端自带逻辑把守）。
// Y14 赛季雏形：登录惰性跨月归档上季 TOP3 → 邮件发称号+灵石 → 全表重标新赛季。
// ─────────────────────────────────────────────────────────

// Y4：按客户端同源口径规范化存档里的境界字段（只读镜像，不动混淆码）
function normalizeRealm(p: any): { realm: string; realmIndex: number; realmLevel: number; exp: number; maxExp: number } {
  const realm = p && typeof p.realm === 'string' && TRIB_REALM_BASES[p.realm] ? p.realm : '炼气期';
  const realmLevel = Math.min(9, Math.max(1, Math.floor(Number(p?.realmLevel) || 1)));
  const exp = Math.max(0, Math.floor(Number(p?.exp) || 0));
  return { realm, realmIndex: REALM_ORDER_FOR_RANKING.indexOf(realm), realmLevel, exp, maxExp: realmMaxExp(realm, realmLevel) };
}

// GET /api/rebirth/status — 天劫状态（境界/修为进度/目标境界/冷却/胜场）
app.get('/api/rebirth/status', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `rebirth:status:${req.user?.id ?? req.ip}` }), (req: any, res: any) => {
  db.get('SELECT save_data FROM saves WHERE user_id = ?', [req.user.id], (err: any, row: any) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let p: any;
    try { p = JSON.parse(row.save_data)?.player ?? {}; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    const nr = normalizeRealm(p);
    const isMax = nr.realmIndex < 0 || nr.realmIndex >= REALM_ORDER_FOR_RANKING.length - 1;
    db.get('SELECT fail_until, wins, last_target, pills, pill_stash FROM rebirth_state WHERE user_id = ?', [req.user.id], (err2: any, st: any) => {
      if (err2) return res.status(500).json({ error: 'Database error' });
      const cooldownUntil = st?.fail_until != null ? Number(st.fail_until) : null;
      const levelOk = nr.realmLevel >= 9;
      const expOk = nr.exp >= nr.maxExp;
      const targetRealm = isMax ? null : REALM_ORDER_FOR_RANKING[nr.realmIndex + 1];
      const committedPills = pillCount(st?.pills); // Y3A：已垫刀数（下一次天劫生效）
      res.json({
        realm: nr.realm,
        realmLevel: nr.realmLevel,
        exp: nr.exp,
        maxExp: nr.maxExp,
        targetRealm,
        levelOk,
        expOk,
        ready: !isMax && levelOk && expOk,
        myStats: { attack: Math.max(0, Math.floor(Number(p?.attack) || 0)), defense: Math.max(0, Math.floor(Number(p?.defense) || 0)), maxHp: Math.max(0, Math.floor(Number(p?.maxHp) || 0)) },
        buffedStats: tribBuffedStats({ attack: p?.attack, defense: p?.defense, maxHp: p?.maxHp }, committedPills), // Y3A：垫刀增幅面板
        enemy: targetRealm ? tribulationEnemy(targetRealm) : null,
        wins: Number(st?.wins) || 0,
        lastTarget: st?.last_target || null,
        cooldownUntil,
        cooldownLeft: cooldownUntil != null ? Math.max(0, cooldownUntil - Date.now()) : 0,
        pills: committedPills,                                              // Y3A：已垫刀数 0..10
        pillBonusPct: committedPills * 3,                                   // Y3A：天劫成功率加成 %
        pillStash: Math.max(0, Math.floor(Number(st?.pill_stash) || 0)),    // Y3A：凝元丹仓库
        pillMax: TRIB_PILL_MAX,
      });
    });
  });
});

// POST /api/rebirth/challenge — 发起天劫挑战。胜=突破+公告+称号；败=10 分钟冷却。
// 冷却与胜利账本均为单语句 upsert（无读改写竞态）；瓶颈 gate 在修为门槛——胜利后修为结转，天然防连刷
app.post('/api/rebirth/challenge', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `rebirth:challenge:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let p: any;
    try { p = JSON.parse(row.save_data)?.player ?? {}; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    const nr = normalizeRealm(p);
    if (nr.realmIndex < 0) return res.status(400).json({ error: '境界数据异常' });
    if (nr.realmIndex >= REALM_ORDER_FOR_RANKING.length - 1) return res.status(409).json({ error: '已至长生境，仙路尽头，无需再渡劫' });
    const targetRealm = REALM_ORDER_FOR_RANKING[nr.realmIndex + 1];
    if (nr.realmLevel < 9) return res.status(409).json({ error: `需修至${nr.realm}第九层方可引动天劫（当前第${nr.realmLevel}层）` });
    if (nr.exp < nr.maxExp) return res.status(409).json({ error: `修为尚未圆满：需 ${nr.maxExp}，当前 ${nr.exp}` });
    const now = Date.now();
    const st = await dbGet('SELECT fail_until, wins, last_target FROM rebirth_state WHERE user_id = ?', [userId]);
    if (st?.fail_until != null && Number(st.fail_until) > now) {
      return res.status(409).json({ error: '渡劫失利心魔未散，须静心调息', cooldownUntil: Number(st.fail_until) });
    }
    const enemy = tribulationEnemy(targetRealm);
    // Y3A 垫刀：消耗"已垫"凝元丹（胜败皆焚；守卫式单语句清零防并发双耗），按颗数增幅我方三维战力
    const pillsUsed = pillCount(st?.pills);
    if (pillsUsed > 0) {
      await dbRun('UPDATE rebirth_state SET pills = 0 WHERE user_id = ? AND pills = ?', [userId, pillsUsed]);
    }
    const myStats = tribBuffedStats({ attack: p.attack, defense: p.defense, maxHp: p.maxHp }, pillsUsed);
    const battle = simulateTribulationBattle(myStats, enemy);
    if (!battle.win) {
      const cooldownUntil = now + TRIBULATION_FAIL_COOLDOWN_MS;
      await dbRun(
        `INSERT INTO rebirth_state (user_id, fail_until, wins, last_target) VALUES (?, ?, 0, NULL)
         ON CONFLICT(user_id) DO UPDATE SET fail_until = excluded.fail_until, updated_at = CURRENT_TIMESTAMP`,
        [userId, cooldownUntil]
      );
      // Y3A：渡劫失败反噬——满槽修为尽散、返还五成（锁内按新档重算；updatePlayerSave saveLock 互斥 + gm_revision++ 促拉新档）
      let expAfter = -1;
      const hit = await updatePlayerSave(userId, (sd: any) => {
        if (!sd.player || typeof sd.player !== 'object') return;
        const nrNow = normalizeRealm(sd.player);
        sd.player.exp = tribFailExpAfter(nrNow.exp, nrNow.maxExp);
        expAfter = Math.max(0, Math.floor(Number(sd.player.exp) || 0));
      });
      if (!hit.ok) console.error('trib fail exp penalty error:', hit.error);
      logChronicle(userId, String(p?.name || req.user.username || '无名修士').slice(0, 32), `【天劫】引动${targetRealm}天劫，为雷所伤，散功五成，闭关调息，再候良机`); // Y16 江湖志
      return res.json({ ok: true, win: false, targetRealm, enemy, battle, cooldownUntil, pillsUsed, pillBonusPct: pillsUsed * 3, expAfter: hit.ok ? expAfter : null });
    }
    // 胜 → 服务端代写突破（realm 改写 / 层数归 1 / 修为结转）：updatePlayerSave 内部 saveLock 互斥 + gm_revision++ 联动
    const applied = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') sd.player = {};
      sd.player.realm = targetRealm;
      sd.player.realmLevel = 1;
      sd.player.exp = Math.max(0, (Number(sd.player.exp) || 0) - nr.maxExp); // 同客户端突破口径：溢出修为结转
    });
    if (!applied.ok) return res.status(500).json({ error: '渡劫结算失败，请稍后重试' });
    const wins = (Number(st?.wins) || 0) + 1;
    await dbRun(
      `INSERT INTO rebirth_state (user_id, fail_until, wins, last_target) VALUES (?, NULL, 1, ?)
       ON CONFLICT(user_id) DO UPDATE SET wins = wins + 1, last_target = excluded.last_target, fail_until = NULL, updated_at = CURRENT_TIMESTAMP`,
      [userId, targetRealm]
    );
    // 全服公告（system 频道）：同一目标境界只播报一次（last_target 防重复渡劫刷屏；称号幂等由 player_titles 主键兜底）
    const charName = String(p?.name || req.user.username || '无名修士').slice(0, 32);
    let announced = false;
    if (!(st && st.last_target === targetRealm)) {
      announced = await new Promise<boolean>((resolve) => {
        db.run('INSERT INTO chat_messages (username, text) VALUES (?, ?)',
          ['系统公告', `【渡劫】道友「${charName}」引动${targetRealm}天劫，力斩天劫使者，渡劫飞升！`],
          (e: any) => resolve(!e));
      });
    }
    logChronicle(userId, charName, `【飞升】力斩${targetRealm}天劫使者，晋入${targetRealm}，仙路更上一步！`); // Y16 江湖志
    await grantTitleBySource(userId, 'rebirth');
    res.json({ ok: true, win: true, targetRealm, enemy, battle, announced, wins, pillsUsed, pillBonusPct: pillsUsed * 3 });
  } catch (e: any) {
    console.error('rebirth challenge error:', e?.message || e);
    if (!res.headersSent) res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/rebirth/use-pill {count?:number} — Y3A 渡劫垫刀：凝元丹从仓库转入"已垫"（累计 ≤10 颗），
// 下一次引动天劫时生效（每颗 +3% 胜率，胜败皆焚）。守卫式单语句 UPDATE 原子防并发超垫/超扣
app.post('/api/rebirth/use-pill', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `rebirth:usepill:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    await dbRun('INSERT OR IGNORE INTO rebirth_state (user_id) VALUES (?)', [userId]); // 无状态行先建（全默认 0）
    const st = await dbGet('SELECT pills, pill_stash FROM rebirth_state WHERE user_id = ?', [userId]);
    const committed = pillCount(st?.pills);
    const stash = Math.max(0, Math.floor(Number(st?.pill_stash) || 0));
    const move = Math.min(Math.max(1, Math.floor(asNum(req.body?.count) || 1)), stash, TRIB_PILL_MAX - committed);
    if (move <= 0) {
      return res.status(409).json({ error: committed >= TRIB_PILL_MAX ? `垫刀已满 ${TRIB_PILL_MAX} 颗，引动天劫后需重新垫刀` : '丹囊空空：炼丹炉炼「凝元丹」出炉可得' });
    }
    const upd = await dbRun(
      'UPDATE rebirth_state SET pill_stash = pill_stash - ?, pills = pills + ? WHERE user_id = ? AND pill_stash >= ? AND pills + ? <= ?',
      [move, move, userId, move, move, TRIB_PILL_MAX]
    );
    if (!upd.changes) return res.status(409).json({ error: '垫刀失败，请重试' }); // 并发竞争落空，重试即可
    const fresh = await dbGet('SELECT pills, pill_stash FROM rebirth_state WHERE user_id = ?', [userId]);
    const pills = pillCount(fresh?.pills);
    res.json({
      ok: true,
      used: move,
      pills,
      pillStash: Math.max(0, Math.floor(Number(fresh?.pill_stash) || 0)),
      pillBonusPct: pills * 3,
    });
  } catch (e: any) {
    console.error('rebirth use-pill error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// DG 秘境/地宫 API（伴生页 /yl/apps/dungeon/）：软门槛账本——服务端只提供权威计数与异常标记，
// 数值由客户端读 status 展示与执行；无论客户端是否配合，服务端都有账（entry 上报 + 存档差值双通道）
// ─────────────────────────────────────────────────────────

// GET /api/dungeon/status — 今日秘境权威状态（次数/上限/CD/观测/异常）
app.get('/api/dungeon/status', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `dungeon:status:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  try {
    const nowMs = Date.now();
    const row = await dbGet('SELECT count, observed, adventure, last_ts, anomaly, rogue_count, rogue_last_ts FROM dungeon_tracker WHERE player_id = ? AND date = ?', [req.user.id, bjDate(nowMs)]);
    // [r063] rogueCap 挂在**请求本地**的 row 上传给视图（模块级变量在并发下会串号；
    //   dungeon2 门禁钉死下面这行 res.json 原样保留，只能走 row 携带）
    if (row) (row as any).__rogueCap = await dungeonRogueCapForUser(req.user.id);
    res.json(dungeonStatusView(row, nowMs, await dungeonCapForUser(req.user.id)));
  } catch (e: any) {
    console.error('dungeon status error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/dungeon/entry — 进入秘境上报：当日计数 +1；CD 内重复上报不计数；超上限 403+原因但留账（服务端有账）。
// 读→判→写全程 saveLock 串行（与存档上传/GM patch 同锁），并发 entry 只放行到上限
app.post('/api/dungeon/entry', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `dungeon:entry:${req.user?.id ?? req.ip}` }), (req: any, res: any) => {
  withSaveLock(req.user.id, async (): Promise<void> => {
    try {
      const nowMs = Date.now();
      const date = bjDate(nowMs);
      const row = await dbGet('SELECT count, last_ts, rogue_count, rogue_last_ts FROM dungeon_tracker WHERE player_id = ? AND date = ?', [req.user.id, date]);
      // ── [r063] R-063 roguelike 地宫独立账本分流：body.mode==="rogue" 走
      //      rogue_count/rogue_last_ts + DUNGEON_ROGUE_CAP_BY_REALM，判定/落库/403/200
      //      在本分支内自洽结束；普通点选路径下行字节不动（dungeon2 环门禁钉死
      //      _dgCap / verdict / 普通插入 / 普通 403 / 普通 200 五处）。
      if (String((req.body && req.body.mode) || '') === 'rogue') {
        const _rCap = await dungeonRogueCapForUser(req.user.id);
        const rVerdict = dungeonEntryVerdict(row?.rogue_count, row?.rogue_last_ts != null ? Number(row.rogue_last_ts) : null, nowMs, _rCap);
        if (rVerdict.reason !== 'cd') {
          await dbRun(
            `INSERT INTO dungeon_tracker (player_id, date, count, observed, adventure, last_ts, anomaly, rogue_count, rogue_last_ts) VALUES (?, ?, 0, 0, 0, NULL, ?, ?, ?)
             ON CONFLICT(player_id, date) DO UPDATE SET
               rogue_count = excluded.rogue_count,
               rogue_last_ts = excluded.rogue_last_ts,
               anomaly = CASE WHEN excluded.rogue_count > ? THEN 1 ELSE anomaly END`,
            [req.user.id, date, rVerdict.count > DUNGEON_ANOMALY_THRESHOLD ? 1 : 0, rVerdict.count, nowMs, DUNGEON_ANOMALY_THRESHOLD]
          );
        }
        if (!rVerdict.allowed) {
          return res.status(403).json({
            ok: false,
            reason: rVerdict.reason,
            error: rVerdict.reason === 'cap' ? `今日地宫探索次数已用完（上限 ${_rCap} 次）` : '进入过于频繁，请稍候再试',
            count: rVerdict.count,
            cap: _rCap,
            remaining: Math.max(0, _rCap - rVerdict.count),
            retryAfterMs: rVerdict.retryAfterMs ?? 0,
            mode: 'rogue',
          });
        }
        return res.json({ ok: true, count: rVerdict.count, cap: _rCap, remaining: Math.max(0, _rCap - rVerdict.count), cdMs: DUNGEON_ENTRY_CD_MS, mode: 'rogue' });
      }
      const _dgCap = await dungeonCapForUser(req.user.id);
      const verdict = dungeonEntryVerdict(row?.count, row?.last_ts != null ? Number(row.last_ts) : null, nowMs, _dgCap);
      if (verdict.reason !== 'cd') {
        // CD 拒绝=同一次进入的重复上报不计数不刷 last_ts；首报/放行/超限留账均落表（anomaly 由语句内 CASE 判定）
        await dbRun(
          `INSERT INTO dungeon_tracker (player_id, date, count, observed, adventure, last_ts, anomaly) VALUES (?, ?, ?, 0, 0, ?, ?)
           ON CONFLICT(player_id, date) DO UPDATE SET
             count = excluded.count,
             last_ts = excluded.last_ts,
             anomaly = CASE WHEN excluded.count > ? OR observed > ? THEN 1 ELSE anomaly END`,
          [req.user.id, date, verdict.count, nowMs,
            verdict.count > DUNGEON_ANOMALY_THRESHOLD ? 1 : 0, DUNGEON_ANOMALY_THRESHOLD, DUNGEON_ANOMALY_THRESHOLD]
        );
      }
      if (!verdict.allowed) {
        return res.status(403).json({
          ok: false,
          reason: verdict.reason,
          error: verdict.reason === 'cap' ? `今日秘境次数已用完（上限 ${_dgCap} 次）` : '进入过于频繁，请稍候再试',
          count: verdict.count,
          cap: _dgCap,
          remaining: Math.max(0, _dgCap - verdict.count),
          retryAfterMs: verdict.retryAfterMs ?? 0,
        });
      }
      res.json({ ok: true, count: verdict.count, cap: _dgCap, remaining: Math.max(0, _dgCap - verdict.count), cdMs: DUNGEON_ENTRY_CD_MS });
    } catch (e: any) {
      console.error('dungeon entry error:', e?.message || e);
      if (!res.headersSent) res.status(500).json({ error: '服务器繁忙' });
    }
  });
});

// GET /api/dungeon/anomalies?days=7 — GM 异常清单（单日 count/observed 超阈置标的行，近 N 日，有界 200 条）
app.get('/api/dungeon/anomalies', authenticateGM, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `dungeon:anomalies:${req.user?.id ?? req.ip}` }), (req: any, res: any) => {
  const days = Math.min(30, Math.max(1, parseInt(req.query.days as string) || 7));
  const since = bjDate(Date.now() - (days - 1) * DAY_MS);
  db.all(
    `SELECT d.player_id, d.date, d.count, d.observed, d.adventure, d.last_ts, d.anomaly, u.username
     FROM dungeon_tracker d LEFT JOIN users u ON u.id = d.player_id
     WHERE d.anomaly = 1 AND d.date >= ? ORDER BY d.date DESC, d.count DESC LIMIT 200`,
    [since],
    (err: any, rows: any[]) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      res.json({
        days,
        threshold: DUNGEON_ANOMALY_THRESHOLD,
        cap: DUNGEON_DAILY_CAP,
        anomalies: (rows || []).map((r) => ({
          playerId: Number(r.player_id),
          username: String(r.username || ''),
          date: String(r.date),
          count: Number(r.count) || 0,
          observed: Number(r.observed) || 0,
          adventure: Number(r.adventure) || 0,
          lastTs: r.last_ts != null ? Number(r.last_ts) : null,
          anomaly: Number(r.anomaly) === 1,
        })),
      });
    }
  );
});

// ─────────────────────────────────────────────────────────
// Y-B 悬赏榜（伴生页 /yl/apps/bounty/）：玩家发赏托管 → 完成者得 90%，10% 系统税。
// 事务口径全走"守卫式单语句 + 补偿式回退"（mailClaimCore/alchemy 同款，不用裸 BEGIN/COMMIT）：
//   create：INSERT 悬赏（status=open）→ 扣发布者灵石托管（saveLock 互斥+闭包二次校验）→ 失败补偿删单可重试
//   accept：接取上限 COUNT + 守卫式 UPDATE status='accepted'（WHERE status='open' 并发只放行一方），全程 saveLock 串行
//   complete：仅发布者可确认；守卫式 UPDATE status='done' → 托管 90% 入接受者账（updatePlayerSave）→ 失败回退可重试
//   cancel：仅 open 可取消（已接取不可撤，防坑接受者）；守卫式 UPDATE status='cancelled' → 退全款 → 失败回退可重试
//   sweep：24h 过期惰性清扫（open/accepted 一律退全款退任务），守卫式 UPDATE 防重复退款
// ─────────────────────────────────────────────────────────

// [bounty-core] 悬赏榜状态流转核心（依赖注入以便 mock db 单测；块内不得引用其它模块符号）
interface BountyDeps {
  dbGet: (sql: string, params?: any[]) => Promise<any>;
  dbAll: (sql: string, params?: any[]) => Promise<any[]>;
  dbRun: (sql: string, params?: any[]) => Promise<{ lastID: number; changes: number }>;
  updatePlayerSave: (userId: number, mutate: (sd: any) => void) => Promise<{ ok: boolean; error?: string }>;
  logEvent?: (playerId: number, nickname: string, text: string) => void; // Y16 江湖志（可注入，缺省不记）
}
interface BountyRow { id: number; poster_id: number; poster_name: string; title: string; desc: string; reward: number; status: string; acceptor_id: number | null; acceptor_name: string; created_at: number; deadline: number; finished_at: number | null; }

// create：托管入账成功 → 悬赏单已插入（调用方保证先 INSERT 后扣费，扣费失败由补偿删单）
async function bountyCreateCore(
  deps: BountyDeps, userId: number, posterName: string, title: string, desc: string, reward: number, nowMs: number
): Promise<{ ok: boolean; error?: string; id?: number; deadline?: number }> {
  const ins = await deps.dbRun(
    `INSERT INTO bounties (poster_id, poster_name, title, desc, reward, status, created_at, deadline)
     VALUES (?, ?, ?, ?, ?, 'open', ?, ?)`,
    [userId, String(posterName || '').slice(0, 32), bountyTitleClamp(title), bountyDescClamp(desc), reward, nowMs, bountyDeadline(nowMs)]
  );
  // 托管扣费（saveLock 互斥 + gm_revision++ 促客户端拉新档）；闭包二次校验防并发透支
  let short = false;
  const paid = await deps.updatePlayerSave(userId, (sd: any) => {
    const b = Number(sd.player?.spiritStones) || 0;
    if (b < reward) { short = true; return; }
    sd.player.spiritStones = b - reward;
  });
  if (!paid.ok || short) {
    await deps.dbRun('DELETE FROM bounties WHERE id = ?', [ins.lastID]).catch(() => {}); // 补偿删单可重试
    return { ok: false, error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : (paid.error || '托管失败')) };
  }
  return { ok: true, id: ins.lastID, deadline: bountyDeadline(nowMs) };
}

// accept：接取（每玩家同时最多 BOUNTY_ACCEPT_MAX 个；并发双抢守卫式 UPDATE 只放行一方）
async function bountyAcceptCore(
  deps: BountyDeps, userId: number, acceptorName: string, bountyId: number, nowMs: number
): Promise<{ ok: boolean; error?: string }> {
  const b: BountyRow | undefined = await deps.dbGet('SELECT id, poster_id, status, deadline FROM bounties WHERE id = ?', [bountyId]);
  if (!b) return { ok: false, error: '悬赏不存在' };
  if (Number(b.poster_id) === userId) return { ok: false, error: '不能接取自己发布的悬赏' };
  if (b.status !== 'open') return { ok: false, error: '该悬赏已被接取或已结束' };
  if (bountyIsExpired(Number(b.deadline), nowMs)) return { ok: false, error: '该悬赏已过期' };
  const cnt = await deps.dbGet(`SELECT COUNT(*) AS c FROM bounties WHERE acceptor_id = ? AND status = 'accepted'`, [userId]);
  if ((Number(cnt?.c) || 0) >= BOUNTY_ACCEPT_MAX) return { ok: false, error: `最多同时接取 ${BOUNTY_ACCEPT_MAX} 个悬赏，先去完成手头的吧` };
  const upd = await deps.dbRun(
    `UPDATE bounties SET status = 'accepted', acceptor_id = ?, acceptor_name = ?, finished_at = NULL WHERE id = ? AND status = 'open'`,
    [userId, String(acceptorName || '').slice(0, 32), bountyId]
  );
  if (!upd.changes) return { ok: false, error: '手慢了，该悬赏已被他人接下' };
  return { ok: true };
}

// complete：发布者确认完成——守卫式置 done（单语句防并发重复发放）→ 托管 90% 入接受者账；入账失败回退可重试
async function bountyCompleteCore(
  deps: BountyDeps, userId: number, bountyId: number, nowMs: number
): Promise<{ ok: boolean; error?: string; payout?: number; tax?: number; acceptorId?: number; title?: string }> {
  const b: BountyRow | undefined = await deps.dbGet(
    'SELECT id, poster_id, title, reward, status, acceptor_id, acceptor_name FROM bounties WHERE id = ?', [bountyId]);
  if (!b) return { ok: false, error: '悬赏不存在' };
  if (Number(b.poster_id) !== userId) return { ok: false, error: '只有发布者可以确认完成' };
  if (b.status !== 'accepted') return { ok: false, error: '该悬赏不在已接取状态，无法确认' };
  const acceptorId = Number(b.acceptor_id);
  if (!acceptorId) return { ok: false, error: '该悬赏无接取人，无法确认' };
  const upd = await deps.dbRun(
    `UPDATE bounties SET status = 'done', finished_at = ? WHERE id = ? AND status = 'accepted'`,
    [nowMs, bountyId]
  );
  if (!upd.changes) return { ok: false, error: '悬赏状态已变化，请刷新后重试' };
  const payout = bountyPayout(Number(b.reward));
  const credit = await deps.updatePlayerSave(acceptorId, (sd: any) => {
    if (!sd.player || typeof sd.player !== 'object') sd.player = {};
    sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + payout;
  });
  if (!credit.ok) {
    // 补偿回退（接受者无存档等）：单退回 accepted，发布者可重试
    await deps.dbRun(`UPDATE bounties SET status = 'accepted', finished_at = NULL WHERE id = ? AND status = 'done'`, [bountyId]).catch(() => {});
    return { ok: false, error: credit.error === 'No save found' ? '接取者尚未进游戏创建角色，暂无法发放，请稍后再试' : (credit.error || '发放失败，请重试') };
  }
  if (deps.logEvent) {
    deps.logEvent(Number(b.poster_id), String(b.acceptor_name || ''), `【悬赏】道友「${String(b.acceptor_name || '')}」完成悬赏「${String(b.title)}」，获得赏金灵石 ×${payout}（发布者已确认）`);
  }
  return { ok: true, payout, tax: bountyTax(Number(b.reward)), acceptorId, title: String(b.title) };
}

// cancel：发布者取消（仅 open 可撤——已接取不可撤，防坑已接取者；过期由 sweep 退款）
async function bountyCancelCore(
  deps: BountyDeps, userId: number, bountyId: number, nowMs: number
): Promise<{ ok: boolean; error?: string; refund?: number }> {
  const b: BountyRow | undefined = await deps.dbGet('SELECT id, poster_id, reward, status FROM bounties WHERE id = ?', [bountyId]);
  if (!b) return { ok: false, error: '悬赏不存在' };
  if (Number(b.poster_id) !== userId) return { ok: false, error: '只有发布者可以取消悬赏' };
  if (b.status !== 'open') return { ok: false, error: b.status === 'accepted' ? '该悬赏已被接取，不可取消（等确认完成或过期自动退款）' : '该悬赏已结束，无需取消' };
  const upd = await deps.dbRun(
    `UPDATE bounties SET status = 'cancelled', finished_at = ? WHERE id = ? AND status = 'open'`,
    [nowMs, bountyId]
  );
  if (!upd.changes) return { ok: false, error: '悬赏状态已变化，请刷新后重试' };
  // 退全款（托管原路退回发布者）
  const refund = Math.max(0, Number(b.reward) || 0);
  const credit = await deps.updatePlayerSave(userId, (sd: any) => {
    if (!sd.player || typeof sd.player !== 'object') sd.player = {};
    sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + refund;
  });
  if (!credit.ok) {
    await deps.dbRun(`UPDATE bounties SET status = 'open', finished_at = NULL WHERE id = ? AND status = 'cancelled'`, [bountyId]).catch(() => {});
    return { ok: false, error: credit.error === 'No save found' ? '请先进游戏创建角色后再取消' : (credit.error || '退款失败，请重试') };
  }
  return { ok: true, refund };
}

// sweep：24h 过期惰性清扫——open/accepted 一律退全款退任务（守卫式置 expired 防重复退款；批量有界逐批消化）
async function bountySweepCore(deps: BountyDeps, nowMs: number): Promise<number> {
  const rows = await deps.dbAll(
    `SELECT id, poster_id, status, reward FROM bounties WHERE status IN ('open','accepted') AND deadline <= ? LIMIT ?`,
    [nowMs, BOUNTY_SWEEP_BATCH]
  );
  let refunded = 0;
  for (const r of rows || []) {
    const prevStatus = String(r.status);
    const upd = await deps.dbRun(
      `UPDATE bounties SET status = 'expired', finished_at = ? WHERE id = ? AND status = ? AND deadline <= ?`,
      [nowMs, Number(r.id), prevStatus, nowMs]
    );
    if (!upd.changes) continue; // 并发被他方清扫/状态已变
    const credit = await deps.updatePlayerSave(Number(r.poster_id), (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') sd.player = {};
      sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + Math.max(0, Number(r.reward) || 0);
    });
    if (!credit.ok) {
      // 补偿回退原状态，下次清扫重试（宁可晚退不可漏退）
      await deps.dbRun(`UPDATE bounties SET status = ?, finished_at = NULL WHERE id = ? AND status = 'expired'`, [prevStatus, Number(r.id)]).catch(() => {});
      continue;
    }
    refunded++;
  }
  return refunded;
}
// [/bounty-core]

// Y-B：悬赏核心 deps（生产装配；logEvent 挂 Y16 江湖志通道）
const bountyDeps: BountyDeps = { dbGet, dbAll, dbRun, updatePlayerSave, logEvent: logChronicle };

// 大厅/我的视图行（公开字段白名单，不漏 poster_id 之外信息）
function bountyPublicRow(r: any, nowMs: number) {
  return {
    id: Number(r.id),
    title: String(r.title || ''),
    desc: String(r.desc || ''),
    reward: Number(r.reward) || 0,
    posterName: String(r.poster_name || ''),
    acceptorName: String(r.acceptor_name || ''),
    status: String(r.status || ''),
    createdAt: Number(r.created_at) || 0,
    deadline: Number(r.deadline) || 0,
    leftMs: Math.max(0, Number(r.deadline) - nowMs),
  };
}

// GET /api/bounty/list?page= — 当前 open 悬赏大厅（金额降序分页）；进入先惰性清扫过期单（退款）
app.get('/api/bounty/list', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `bounty:list:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  try {
    const nowMs = Date.now();
    try { await bountySweepCore(bountyDeps, nowMs); } catch (e: any) { console.error('bounty sweep error:', e?.message || e); }
    const page = clampPage(req.query.page, BOUNTY_MAX_PAGE);
    const cnt = await dbGet(`SELECT COUNT(*) AS c FROM bounties WHERE status = 'open' AND deadline > ?`, [nowMs]);
    const rows = await dbAll(
      `SELECT id, poster_name, title, desc, reward, status, acceptor_name, created_at, deadline FROM bounties
       WHERE status = 'open' AND deadline > ? ORDER BY reward DESC, id DESC LIMIT ? OFFSET ?`,
      [nowMs, BOUNTY_PAGE_SIZE, (page - 1) * BOUNTY_PAGE_SIZE]
    );
    res.json({
      now: nowMs,
      page,
      pageSize: BOUNTY_PAGE_SIZE,
      total: Number(cnt?.c) || 0,
      bounties: (rows || []).map((r) => bountyPublicRow(r, nowMs)),
      consts: { minReward: BOUNTY_MIN_REWARD, maxReward: BOUNTY_MAX_REWARD, feeRate: BOUNTY_FEE_RATE, acceptMax: BOUNTY_ACCEPT_MAX, posterOpenMax: BOUNTY_POSTER_OPEN_MAX },
    });
  } catch (e: any) {
    console.error('bounty list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// GET /api/bounty/mine — 我的悬赏（我发布的全状态 + 我接取的进行中）+ 发布者 open 数/接取数
app.get('/api/bounty/mine', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `bounty:mine:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const nowMs = Date.now();
    try { await bountySweepCore(bountyDeps, nowMs); } catch (e: any) { console.error('bounty sweep error:', e?.message || e); }
    const [posted, taken, openCnt, accCnt] = await Promise.all([
      dbAll('SELECT id, poster_name, title, desc, reward, status, acceptor_name, created_at, deadline FROM bounties WHERE poster_id = ? ORDER BY id DESC LIMIT 50', [userId]),
      dbAll(`SELECT id, poster_name, title, reward, status, created_at, deadline FROM bounties WHERE acceptor_id = ? AND status = 'accepted' ORDER BY id DESC LIMIT ?`, [userId, BOUNTY_ACCEPT_MAX]),
      dbGet(`SELECT COUNT(*) AS c FROM bounties WHERE poster_id = ? AND status = 'open'`, [userId]),
      dbGet(`SELECT COUNT(*) AS c FROM bounties WHERE acceptor_id = ? AND status = 'accepted'`, [userId]),
    ]);
    res.json({
      now: nowMs,
      posted: (posted || []).map((r) => bountyPublicRow(r, nowMs)),
      taken: (taken || []).map((r) => bountyPublicRow(r, nowMs)),
      postedOpenCount: Number(openCnt?.c) || 0,
      acceptedCount: Number(accCnt?.c) || 0,
    });
  } catch (e: any) {
    console.error('bounty mine error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/bounty/create {title, desc?, reward} — 发悬赏：全额托管（发布即扣灵石）；补偿删单可重试
app.post('/api/bounty/create', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `bounty:create:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  const reward = bountyRewardOk(req.body?.reward);
  if (!reward) return res.status(400).json({ error: `赏金须为 ${BOUNTY_MIN_REWARD} ~ ${BOUNTY_MAX_REWARD} 的整数灵石` });
  const title = bountyTitleClamp(req.body?.title);
  if (!title) return res.status(400).json({ error: '悬赏标题不能为空' });
  const desc = bountyDescClamp(req.body?.desc);
  try {
    // 预检：存档/余额/角色名快照（并发窗口由 bountyCreateCore 扣费闭包二次校验兜底）
    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0, posterName = '';
    try {
      const sd = JSON.parse(row.save_data);
      bal = Number(sd?.player?.spiritStones) || 0;
      posterName = String(sd?.player?.name || req.user.username || '').slice(0, 32);
    } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < reward) return res.status(409).json({ error: `灵石不足：需托管 ${reward}，现有 ${bal}` });
    const openCnt = await dbGet(`SELECT COUNT(*) AS c FROM bounties WHERE poster_id = ? AND status = 'open'`, [userId]);
    if ((Number(openCnt?.c) || 0) >= BOUNTY_POSTER_OPEN_MAX) return res.status(409).json({ error: `同时最多挂出 ${BOUNTY_POSTER_OPEN_MAX} 个悬赏，请先处理现有的` });
    const r = await bountyCreateCore(bountyDeps, userId, posterName, title, desc, reward, Date.now());
    if (!r.ok) return res.status(409).json({ error: r.error || '发布失败' });
    res.json({ ok: true, id: r.id, reward, deadline: r.deadline });
  } catch (e: any) {
    console.error('bounty create error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/bounty/accept {id} — 接取：上限/自接/过期校验 + 守卫式占单（saveLock 串行防接取上限并发击穿）
app.post('/api/bounty/accept', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `bounty:accept:${req.user?.id ?? req.ip}` }), (req: any, res: any) => {
  const bountyId = Math.floor(asNum(req.body?.id));
  if (!Number.isInteger(bountyId) || bountyId <= 0) return res.status(400).json({ error: '悬赏编号非法' });
  const userId = req.user.id;
  withSaveLock(userId, async (): Promise<void> => {
    try {
      const acceptorName = String(
        ((await dbGet('SELECT name FROM rankings WHERE user_id = ?', [userId]))?.name) || req.user.username || ''
      ).slice(0, 32);
      const r = await bountyAcceptCore(bountyDeps, userId, acceptorName, bountyId, Date.now());
      if (!r.ok) return void res.status(409).json({ error: r.error || '接取失败' });
      res.json({ ok: true, id: bountyId });
    } catch (e: any) {
      console.error('bounty accept error:', e?.message || e);
      if (!res.headersSent) res.status(500).json({ error: '服务器繁忙' });
    }
  });
});

// POST /api/bounty/complete {id} — 发布者确认完成：托管 90% 发接受者，10% 系统税；发放失败回退可重试
app.post('/api/bounty/complete', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `bounty:complete:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const bountyId = Math.floor(asNum(req.body?.id));
  if (!Number.isInteger(bountyId) || bountyId <= 0) return res.status(400).json({ error: '悬赏编号非法' });
  try {
    const r = await bountyCompleteCore(bountyDeps, req.user.id, bountyId, Date.now());
    if (!r.ok) return res.status(409).json({ error: r.error || '确认失败' });
    res.json({ ok: true, payout: r.payout, tax: r.tax });
  } catch (e: any) {
    console.error('bounty complete error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/bounty/cancel {id} — 发布者取消（仅 open）：退全款；退款失败回退可重试
app.post('/api/bounty/cancel', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `bounty:cancel:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const bountyId = Math.floor(asNum(req.body?.id));
  if (!Number.isInteger(bountyId) || bountyId <= 0) return res.status(400).json({ error: '悬赏编号非法' });
  try {
    const r = await bountyCancelCore(bountyDeps, req.user.id, bountyId, Date.now());
    if (!r.ok) return res.status(409).json({ error: r.error || '取消失败' });
    res.json({ ok: true, refund: r.refund });
  } catch (e: any) {
    console.error('bounty cancel error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// Y14 赛季惰性归档：挂在 onLoginMeta（cron 缺位则登录触发）——
// 存在"已标注过非当前赛季"的行 → 按当前境界榜序归档 TOP3（贴上季标签，UNIQUE(season,rank) 幂等防重复发奖）→
// 每名发「称号+灵石」邮件（复用 insertMail）→ 全表重标当前赛季。首部署全 NULL 只重标不发奖（防上线即空发一季）。
async function maybeRolloverSeason(): Promise<void> {
  try {
    const cur = seasonId(Date.now());
    const [total, foreign] = await Promise.all([
      dbGet('SELECT COUNT(*) AS c FROM rankings'),
      dbGet('SELECT COUNT(*) AS c FROM rankings WHERE season IS NOT NULL AND season != ?', [cur]),
    ]);
    if (!(Number(total?.c) > 0)) return;
    if (shouldArchiveSeason(Number(foreign?.c) || 0)) {
      const prev = prevSeasonId(cur);
      // QA-RT fix(BUG#S1 2026-09-16)：原 SELECT ... realm ... FROM rankings——rankings 表无 realm 列
      // （实列 realm_index/realm_level），惰性归档每次登录都在此抛 no such column: realm 被自吞，
      // 赛季归档/发奖/重标全静默失效。改取索引列并在入库时镜像境界名。
      const top = await dbAll(
        `SELECT user_id, username, realm_index, realm_level, combat_power, spirit_stones FROM rankings ORDER BY ${LEADERBOARD_SORTS.realm.orderBy} LIMIT ?`,
        [SEASON_TOP_N]
      );
      for (let i = 0; i < top.length; i++) {
        const r = top[i];
        const rw = seasonRewardForRank(i + 1);
        if (!rw) continue;
        const ins = await dbRun(
          `INSERT OR IGNORE INTO season_archives (season, rank, user_id, username, realm, combat_power, spirit_stones)
           VALUES (?, ?, ?, ?, ?, ?, ?)`,
          [prev, rw.rank, Number(r.user_id), String(r.username || '').slice(0, 32),
            REALM_ORDER_FOR_RANKING[Number(r.realm_index)] || '', Number(r.combat_power) || 0, Number(r.spirit_stones) || 0]
        );
        if (ins.changes > 0) {
          logChronicle(Number(r.user_id), String(r.username || '').slice(0, 32), `【赛季】${prev} 赛季结算，位列境界榜第 ${rw.rank}，膺称号「${rw.title}」，受赏灵石 ×${rw.stones}`); // Y16 江湖志
          await grantTitleBySource(Number(r.user_id), rw.source);
          await insertMail(Number(r.user_id), `${prev} 赛季结算`,
            `上赛季（${prev}）境界榜第 ${rw.rank} 名，结算奖励：\n\n· 称号「${rw.title}」已放入称号收藏\n· 灵石 ×${rw.stones}（点击下方领取）\n\n新赛季已开启，仙路再争锋。`,
            'system', rw.stones);
        }
      }
    }
    await dbRun('UPDATE rankings SET season = ? WHERE season IS NULL OR season != ?', [cur, cur]);
  } catch (e: any) {
    console.error('season rollover error:', e?.message || e);
  }
}

// ─────────────────────────────────────────────────────────
// V27 宗门体系（2026-09-25）：/api/sect/* 全家桶
// 架构纪律（设计稿定案）：零主 bundle 改动（伴生页 /yl/apps/sect/）；灵石动账全部服务端结算——
// 扣款=spendFromSave（withSaveLock 内二次校验防双开同扣）、发奖=updatePlayerSave，均走
// gm_revision+1/upsertRanking/writeEconomyMirror 收尾序列，与 409 stale_save 防倒滚零冲突；
// 宗门归属单一事实源=sect_members 表，不写存档 player.sectId；数值表全部集中下方常量，调参不改逻辑。
// 迁移留档=migrations/sect_system.sql（与 account_refactor.sql 同规范：幂等 IF NOT EXISTS，双写一致）。
// ─────────────────────────────────────────────────────────
const SECT_CREATE_COST = 1000000;    // 建宗灵石（一次性；不进 sect_ledger、不推进捐献任务；0.8.8 item15 50000→1000000）
const SECT_CREATE_MIN_REALM = 3;     // 建宗境界门槛：REALM_ORDER_FOR_RANKING 下标 ≥3（元婴期；0.8.8 item15）
const SECT_NAME_MIN = 2;             // 宗门名称长度下限（TRIM 后字符数）
const SECT_NAME_MAX = 12;            // 宗门名称长度上限
const SECT_DONATE_MIN = 100;         // 单笔捐献下限
const SECT_DONATE_MAX = 100000;      // 单笔捐献上限
const SECT_DONATE_DAILY_CAP = 50000; // 每人每日捐献累计上限（sect_ledger 北京日切 SUM 口径）
const SECT_LEAVE_COOLDOWN_MS = 24 * 3600 * 1000; // 退宗/被踢/解散后 24h 冷却（服务端表约束）
// 0.8.7 T7：申请审批流与捐献回馈（数值定档=《数值表-T7T8》T7-6/7/8/9，调参只动本区）
const SECT_APPLY_TTL_MS = 72 * 3600 * 1000; // 申请有效期 72h（过期由读取路径惰性置 expired）
const SECT_DONATE_CONTRIB_RATE = 0.02;      // 捐献回馈贡献率 2%；日上限=SECT_DONATE_DAILY_CAP×rate=1000（公式值不设新常量）
const SECT_CONTRIB_CLAMP_PER_MIN = 20;      // E2:sectContrib 差值钳增速：20/分（=1200/时，任务阁稳态）
const SECT_CONTRIB_CLAMP_BASE = 5000;       // E2:sectContrib 兜底（原生职衔晋升单笔 5000 恰容）
const SECT_SALARY_PER_LEVEL = 500;   // 每日俸禄 = 宗门等级 × 500 灵石（全员可领）
const SECT_PILL_MIN_LEVEL = 2;       // 宗门丹药解锁等级
const SECT_PILL_NAME = '宗门凝气丹';
const SECT_LIST_PAGE_SIZE = 10;
const SECT_MEMBER_CAP = (level: number) => level * 10 + 20; // 人数上限 = 等级×10+20
// 升级资金阶梯：索引 i = 从 level i+1 升 i+2 所需累计资金（funds 只增不清零）
const SECT_LEVEL_UP_FUNDS = [20000, 60000, 150000, 400000, 1000000, 2500000, 6000000];
function sectLevelForFunds(funds: number): number {
  let lv = 1;
  for (let i = 0; i < SECT_LEVEL_UP_FUNDS.length; i++) {
    if (funds >= SECT_LEVEL_UP_FUNDS[i]) lv = i + 2; else break;
  }
  return lv;
}
// 宗门每日任务（集体进度个人领奖）：hunt/adventure/meditate 进度源=POST /api/save 存档差值
// （tickSectTasks 消费 computeQuestDeltas 现成输出），contribute 由 /sect/contribute 端点推进；
// 日期统一 bjDate 北京日切（与 daily_quests 同口径）
const SECT_TASK_DEFS = [
  { key: 'hunt', name: '宗门围猎', desc: '全宗今日累计击杀 50 只妖兽', target: 50, reward: 200, counter: 'kill' },
  { key: 'adventure', name: '结伴历练', desc: '全宗今日累计历练 30 次', target: 30, reward: 200, counter: 'adventure' },
  { key: 'meditate', name: '宗门共修', desc: '全宗今日累计共修 240 分钟', target: 240 * 60 * 1000, reward: 150, counter: 'meditate' },
  { key: 'contribute', name: '捐献灵石', desc: '全宗今日累计捐献 3000 灵石', target: 3000, reward: 300, counter: 'contribute' },
];
// 宗门丹药（welfare kind=pill）：结构克隆自生产 saves 实测丹药 schema（type:'丹药'+effect+
// isEquippable:false，id 格式 ts-rand，背包可正常显示/服用）；若日后客户端消费逻辑变化，
// 降级预案=改发双倍俸禄并在 UI 注明
function sectPillItem(): any {
  return {
    id: `sect-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`,
    name: SECT_PILL_NAME,
    type: '丹药',
    description: '宗门福利丹药，服用后气血翻涌、灵台清明（宗门 2 级起每日可领）。',
    quantity: 1,
    rarity: '稀有',
    effect: { hp: 888, exp: 888 },
    isEquippable: false,
    level: 0,
  };
}

// 建表（与 migrations/sect_system.sql 同一增量，幂等；规范与 account_refactor 双写一致）
db.serialize(() => {
  db.run(`CREATE TABLE IF NOT EXISTS sects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    leader_id INTEGER NOT NULL,
    level INTEGER NOT NULL DEFAULT 1,
    funds INTEGER NOT NULL DEFAULT 0,
    notice TEXT NOT NULL DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    disbanded_at DATETIME,
    join_mode TEXT NOT NULL DEFAULT 'auto'
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS sect_members (
    sect_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('leader','officer','member')),
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sect_id, user_id)
  )`);
  db.run(`CREATE UNIQUE INDEX IF NOT EXISTS idx_sect_members_user ON sect_members(user_id)`);
  db.run(`CREATE TABLE IF NOT EXISTS sect_cooldowns (
    user_id INTEGER PRIMARY KEY,
    cooldown_until TEXT NOT NULL
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS sect_tasks (
    sect_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    task_key TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    done INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (sect_id, date, task_key)
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS sect_task_claims (
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    task_key TEXT NOT NULL,
    claimed_at TEXT,
    PRIMARY KEY (user_id, date, task_key)
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS sect_welfare_claims (
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    kind TEXT NOT NULL,
    claimed_at TEXT,
    PRIMARY KEY (user_id, date, kind)
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS sect_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sect_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    after_funds INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_sect_ledger_sect ON sect_ledger(sect_id, created_at)`);
  // Y22 sect gongfa progress: one row per (player, gongfa id). PK is the idempotency guard.
  // This table is the AUTHORITATIVE level store; player.sectGongfa in saves.save_data is only a
  // mirror for the client (xt reads it). Written by updatePlayerSave + this table in one request.
  db.run(`CREATE TABLE IF NOT EXISTS player_sect_gongfa (
    user_id INTEGER NOT NULL,
    gongfa_id TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, gongfa_id),
    FOREIGN KEY (user_id) REFERENCES users (id)
  )`);
  // 0.8.7 T7：盟申请审批流。一人一 pending 由部分唯一索引兜底（先例 idx_mentorships_apprentice_active），
  // 并发防重靠主键与部分唯一索引，不靠先查后写（设计案 §2-4）
  db.run(`CREATE TABLE IF NOT EXISTS sect_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sect_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
      CHECK (status IN ('pending','approved','rejected','cancelled','expired')),
    created_at INTEGER NOT NULL,
    handled_at INTEGER,
    handled_by INTEGER
  )`);
  db.run(`CREATE UNIQUE INDEX IF NOT EXISTS idx_sect_app_user_pending ON sect_applications(user_id) WHERE status = 'pending'`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_sect_app_sect ON sect_applications(sect_id, status, created_at)`);
  // 存量库加列守卫（先例 saves :139 PRAGMA table_info）：老库 sects 无 join_mode 时补列（与上方建表定义双写一致）
  db.all("PRAGMA table_info(sects)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'join_mode')) {
      safeAddColumn('sects', 'join_mode', "ALTER TABLE sects ADD COLUMN join_mode TEXT NOT NULL DEFAULT 'auto'");
    }
  });
});

// 0.8.7 T7：过期申请惰性置 expired（读取路径调用；TTL=SECT_APPLY_TTL_MS=72h。
// 自吞异常绝不影响业务主路径，与 tickSectTasks 同纪律）
async function sectExpireStaleApplications(): Promise<void> {
  try {
    await dbRun("UPDATE sect_applications SET status = 'expired' WHERE status = 'pending' AND created_at + ? <= ?", [SECT_APPLY_TTL_MS, Date.now()]);
  } catch (e: any) {
    console.error('sect applications expire error:', e?.message || e);
  }
}

// 宗门归属查询（单一事实源=sect_members；一人一宗由 idx_sect_members_user 唯一索引兜底）
async function sectMemberOf(userId: number): Promise<{ sect_id: number; role: string } | null> {
  const row: any = await dbGet('SELECT sect_id, role FROM sect_members WHERE user_id = ?', [userId]);
  return row ? { sect_id: Number(row.sect_id), role: String(row.role) } : null;
}
// 北京日切当日的 UTC 时间下界（'YYYY-MM-DD HH:MM:SS'，与 sect_ledger.created_at 的
// CURRENT_TIMESTAMP 字符串同构，可直接 SQL 字符串比较）
function bjDayUtcFloor(dateStr: string): string {
  return new Date(Date.parse(dateStr + 'T00:00:00+08:00')).toISOString().slice(0, 19).replace('T', ' ');
}

// 划扣灵石（V27）：updatePlayerSave 的"带校验扣款"变体——updatePlayerSave 的 mutate 无中止语义
// 不适合扣费；这里在 withSaveLock 内二次校验 spiritStones ≥ amount（读改写全程持锁，防双开并发同扣），
// 复用其 gm_revision+1 / upsertRanking / maybeGrantAutoTitles / writeEconomyMirror 收尾序列。
function spendFromSave(
  userId: number,
  amount: number,
  extraMutate?: (saveData: any) => void
): Promise<{ ok: boolean; error?: string; spiritStones?: number }> {
  return withSaveLock(userId, () => new Promise((resolve) => {
    db.get('SELECT save_data, gm_revision FROM saves WHERE user_id = ?', [userId], (err: any, row: any) => {
      if (err) return resolve({ ok: false, error: 'Database error' });
      if (!row) return resolve({ ok: false, error: 'No save found' });
      let saveData: any;
      try { saveData = JSON.parse(row.save_data); } catch { return resolve({ ok: false, error: 'Save parse error' }); }
      if (!saveData?.player) return resolve({ ok: false, error: 'No player' });
      try { if (extraMutate) extraMutate(saveData); } catch { return resolve({ ok: false, error: 'Mutate error' }); }
      const stones = Math.floor(Number(saveData.player.spiritStones) || 0);
      if (!Number.isFinite(amount) || amount <= 0 || stones < amount) {
        return resolve({ ok: false, error: 'INSUFFICIENT_STONES' });
      }
      const prevEconSnap = extractEconSnapshot(saveData); // E1：变更前经济快照
      saveData.player.spiritStones = stones - amount;
      const newRevision = (Number(row.gm_revision) || 0) + 1;
      db.run(
        'UPDATE saves SET save_data = ?, gm_revision = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
        [JSON.stringify(saveData), newRevision, userId],
        async (updateErr: any) => {
          if (updateErr) return resolve({ ok: false, error: 'Update failed' });
          await upsertRanking(userId, saveData.player?.name || '', saveData);
          maybeGrantAutoTitles(userId, achievementsLen(saveData));
          writeEconomyMirror(userId, prevEconSnap, extractEconSnapshot(saveData)); // E1 镜像记账（fire-and-forget）
          resolve({ ok: true, spiritStones: stones - amount });
        }
      );
    });
  }));
}

// V27 宗门每日任务计数：把玩家存档差值增量汇入所在宗的当日集体进度。
// 无宗门单查询早退（sect_members 主键查一次，零开销）；写入与 tickDailyQuests 同款——
// 先 INSERT OR IGNORE 建当日行，再单语句原子 UPDATE（MIN/CASE 镜像 nextProgress 语义）
// 防并发丢更新；contribute 键由 /sect/contribute 端点推进，此处跳过。
async function tickSectTasks(userId: number, deltas: Record<string, number>): Promise<void> {
  try {
    const member = await sectMemberOf(userId);
    if (!member) return;
    const date = bjDate(Date.now());
    for (const def of SECT_TASK_DEFS) {
      if (def.counter === 'contribute') continue;
      const delta = Math.floor(Number(deltas[def.counter]) || 0);
      if (delta <= 0) continue;
      await dbRun('INSERT OR IGNORE INTO sect_tasks (sect_id, date, task_key, progress, done) VALUES (?, ?, ?, 0, 0)', [member.sect_id, date, def.key]);
      await dbRun(
        `UPDATE sect_tasks SET
           progress = MIN(?, progress + ?),
           done = CASE WHEN MIN(?, progress + ?) >= ? THEN 1 ELSE done END
         WHERE sect_id = ? AND date = ? AND task_key = ?`,
        [def.target, delta, def.target, delta, def.target, member.sect_id, date, def.key]
      );
    }
  } catch (e: any) {
    console.error('sect tick error:', e?.message || e); // fire-and-forget 自吞异常，绝不影响存档路径
  }
}


// [sectgfcore] Y22 \u5b97\u95e8\u529f\u6cd5\uff08\u5b97\u95e8\u300c\u529f\u6cd5\u9601\u300d\uff09\u7eaf\u903b\u8f91\u6838\u5fc3\uff1a4 \u9636 x 3 \u7cfb = 12 \u90e8\uff0c\u6bcf\u90e8 1..5 \u5c42\u3002
// \u8d44\u6e90 = \u5b97\u95e8\u8d21\u732e\u5ea6 player.sectContribution\uff08legacy \u5b97\u95e8\u65e2\u6709\u5b57\u6bb5\uff09\uff0c\u4e0e\u300c\u5fc3\u6cd5\u516d\u5377\u300d(/api/gongfa\uff1a
// \u7075\u77f3 + \u5168\u5c5e\u6027\u767e\u5206\u6bd4 + player_gongfa \u8868) \u5b8c\u5168\u5206\u79bb\uff1a\u672c\u7cfb\u7edf\u53ea\u7ed9\u5b9a\u5411\u56fa\u5b9a\u503c\uff0c\u4e14\u53d7\u804c\u8854/\u5883\u754c\u53cc\u95e8\u69db\u3002
// \u6bcf\u5c42\u6d88\u8017 = SECT_GF_TIER_BASE[tier] * level\uff08\u4e00\u9636 100/200/300/400/500 ... \u56db\u9636 1500..7500\uff09\u3002
// \u7d2f\u8ba1\u6ee1\u7ea7\uff0812 \u90e8 x 5 \u5c42\uff09= 110250 \u8d21\u732e\u3002\u66f2\u7ebf\u610f\u56fe\uff1a\u5355\u90e8\u4e00\u9636\u7ea6 1 \u5929\u3001\u56db\u9636\u7ea6 4 \u5929\uff08\u8d21\u732e\u65e5\u6536\u5165
// \u91cf\u7ea7 1.2k~6k\uff0c\u968f\u804c\u8854 d=1/1.5/2/3 \u9012\u589e\uff09\uff0c\u5168\u90e8\u6ee1\u7ea7\u7ea6 25~30 \u5929\uff0c\u4f5c\u4e3a\u5b97\u95e8\u7684\u957f\u671f\u6c89\u6dc0\u3002
const SECT_GF_MAX_LEVEL = 5;
const SECT_GF_TIER_BASE: Record<number, number> = { 1: 200, 2: 600, 3: 1500, 4: 4000 }; // [r066] R-066 贡献重做：基价 ×2~×2.7（与客户端 yl_066_ext.py 同源）
const SECT_GF_RANK_ORDER = ['\u5916\u95e8\u5f1f\u5b50', '\u5185\u95e8\u5f1f\u5b50', '\u771f\u4f20\u5f1f\u5b50', '\u957f\u8001', '\u5b97\u4e3b'];
type SectGfDef = { id: string; tier: number; name: string; grade: string; rank: string; realm: string; desc: string; per: Record<string, number> };
const SECT_GF_LIST: SectGfDef[] = [
  { id: 'sgf-t1-atk', tier: 1, name: '\u6dec\u4f53\u62f3\u8c31', grade: '\u9ec4', rank: '\u5916\u95e8\u5f1f\u5b50', realm: '\u70bc\u6c14\u671f', desc: '\u5916\u95e8\u5f1f\u5b50\u5165\u95e8\u62f3\u8c31\uff0c\u4ee5\u62f3\u610f\u6dec\u70bc\u7b4b\u9aa8\uff0c\u51fa\u624b\u66f4\u75be\u66f4\u91cd\u3002', per: { attack: 8, speed: 2 } },
  { id: 'sgf-t1-def', tier: 1, name: '\u7384\u9f9f\u5410\u7eb3\u8bc0', grade: '\u9ec4', rank: '\u5916\u95e8\u5f1f\u5b50', realm: '\u70bc\u6c14\u671f', desc: '\u6548\u7384\u9f9f\u95ed\u606f\u4e4b\u6cd5\uff0c\u5410\u7eb3\u7ef5\u957f\uff0c\u76ae\u7cd9\u8089\u539a\uff0c\u8010\u6253\u8010\u78e8\u3002', per: { defense: 6, maxHp: 30 } },
  { id: 'sgf-t1-psi', tier: 1, name: '\u5f15\u6c14\u5f52\u5143\u7bc7', grade: '\u9ec4', rank: '\u5916\u95e8\u5f1f\u5b50', realm: '\u70bc\u6c14\u671f', desc: '\u5f15\u5929\u5730\u7075\u6c14\u5f52\u5165\u4e39\u7530\uff0c\u795e\u8bc6\u6e10\u660e\uff0c\u4f53\u9b44\u65e5\u56fa\u3002', per: { spirit: 5, physique: 4 } },
  { id: 'sgf-t2-atk', tier: 2, name: '\u7834\u519b\u5251\u8bc0', grade: '\u7384', rank: '\u5185\u95e8\u5f1f\u5b50', realm: '\u7b51\u57fa\u671f', desc: '\u5185\u95e8\u5251\u4fee\u5fc5\u4fee\uff0c\u5251\u8d70\u7834\u519b\u4e4b\u52bf\uff0c\u4e00\u5f80\u65e0\u524d\uff0c\u950b\u9510\u903c\u4eba\u3002', per: { attack: 25, speed: 6 } },
  { id: 'sgf-t2-def', tier: 2, name: '\u78d0\u77f3\u91d1\u8eab\u8bc0', grade: '\u7384', rank: '\u5185\u95e8\u5f1f\u5b50', realm: '\u7b51\u57fa\u671f', desc: '\u4ee5\u78d0\u77f3\u4e4b\u610f\u94f8\u8eab\uff0c\u6c14\u8840\u6d51\u539a\uff0c\u5bfb\u5e38\u6cd5\u5b9d\u96be\u4f24\u5206\u6beb\u3002', per: { defense: 20, maxHp: 120 } },
  { id: 'sgf-t2-psi', tier: 2, name: '\u7075\u7280\u901a\u795e\u7bc7', grade: '\u7384', rank: '\u5185\u95e8\u5f1f\u5b50', realm: '\u7b51\u57fa\u671f', desc: '\u7075\u53f0\u901a\u660e\uff0c\u795e\u8bc6\u5982\u7280\uff0c\u53ef\u7aa5\u654c\u5148\u673a\uff0c\u53ef\u517b\u81ea\u8eab\u6839\u9aa8\u3002', per: { spirit: 16, physique: 13 } },
  { id: 'sgf-t3-atk', tier: 3, name: '\u711a\u5929\u70c8\u7130\u7ecf', grade: '\u5730', rank: '\u771f\u4f20\u5f1f\u5b50', realm: '\u91d1\u4e39\u671f', desc: '\u771f\u4f20\u7edd\u5b66\uff0c\u4e00\u8eab\u771f\u706b\u711a\u5929\u707c\u5730\uff0c\u51fa\u624b\u4fbf\u662f\u71ce\u539f\u4e4b\u52bf\u3002', per: { attack: 80, speed: 18 } },
  { id: 'sgf-t3-def', tier: 3, name: '\u7384\u5929\u4e0d\u706d\u4f53', grade: '\u5730', rank: '\u771f\u4f20\u5f1f\u5b50', realm: '\u91d1\u4e39\u671f', desc: '\u7384\u5929\u62a4\u4f53\u4e4b\u6cd5\uff0c\u8089\u8eab\u51e0\u8fd1\u4e0d\u706d\uff0c\u6c14\u8840\u5982\u6e0a\uff0c\u5386\u52ab\u4e0d\u635f\u3002', per: { defense: 65, maxHp: 420 } },
  { id: 'sgf-t3-psi', tier: 3, name: '\u592a\u865a\u5143\u795e\u7bc7', grade: '\u5730', rank: '\u771f\u4f20\u5f1f\u5b50', realm: '\u91d1\u4e39\u671f', desc: '\u51dd\u70bc\u592a\u865a\u5143\u795e\uff0c\u795e\u8bc6\u5916\u653e\u53ef\u8986\u767e\u91cc\uff0c\u6839\u9aa8\u4ea6\u968f\u4e4b\u8131\u80ce\u6362\u9aa8\u3002', per: { spirit: 50, physique: 40 } },
  { id: 'sgf-t4-atk', tier: 4, name: '\u4e5d\u9704\u622e\u4ed9\u5178', grade: '\u5929', rank: '\u957f\u8001', realm: '\u5143\u5a74\u671f', desc: '\u9547\u5b97\u6740\u4f10\u4e4b\u5178\uff0c\u5251\u610f\u76f4\u4e0a\u4e5d\u9704\uff0c\u4ed9\u795e\u4ea6\u53ef\u622e\u4e4b\u3002', per: { attack: 250, speed: 55 } },
  { id: 'sgf-t4-def', tier: 4, name: '\u6df7\u6c8c\u9547\u5cb3\u7ecf', grade: '\u5929', rank: '\u957f\u8001', realm: '\u5143\u5a74\u671f', desc: '\u4ee5\u6df7\u6c8c\u4e4b\u6c14\u9547\u5b88\u8089\u58f3\uff0c\u4e00\u8eab\u6c14\u8840\u91cd\u903e\u5c71\u5cb3\uff0c\u4e07\u6cd5\u96be\u4fb5\u3002', per: { defense: 200, maxHp: 1400 } },
  { id: 'sgf-t4-psi', tier: 4, name: '\u4e07\u7075\u5f52\u5143\u5f55', grade: '\u5929', rank: '\u957f\u8001', realm: '\u5143\u5a74\u671f', desc: '\u4e07\u7075\u5f52\u5143\uff0c\u5143\u795e\u5706\u6ee1\uff0c\u795e\u8bc6\u4e0e\u6839\u9aa8\u540c\u81fb\u5316\u5883\u3002', per: { spirit: 160, physique: 130 } },
];
const SECT_GF_BY_ID: Record<string, SectGfDef> = (() => {
  const m: Record<string, SectGfDef> = Object.create(null);
  for (const g of SECT_GF_LIST) m[g.id] = g;
  return m;
})();
// \u5c42\u6570\u5f52\u4e00\uff080..5\uff09
function sectGfLevel(v: unknown): number {
  return Math.min(SECT_GF_MAX_LEVEL, Math.max(0, Math.floor(Number(v) || 0)));
}
// \u5347\u5230 level \u5c42\u6240\u9700\u7684\u5b97\u95e8\u8d21\u732e
function sectGfCost(tier: unknown, level: unknown): number {
  const base = SECT_GF_TIER_BASE[Math.floor(Number(tier) || 0)] || 0;
  const lv = Math.max(1, Math.floor(Number(level) || 1));
  return Math.floor(base * Math.pow(2, lv - 1)); // [r066] 每层 ×2 指数递增（客户端同式）
}
// \u804c\u8854\u95e8\u69db\uff08\u4e0b\u6807\u6bd4\u8f83\uff1b\u672a\u77e5\u804c\u8854\u4e00\u5f8b\u4e0d\u901a\u8fc7\uff09
function sectGfRankOk(rank: unknown, need: string): boolean {
  const i = SECT_GF_RANK_ORDER.indexOf(String(rank || ''));
  const j = SECT_GF_RANK_ORDER.indexOf(need);
  return i >= 0 && j >= 0 && i >= j;
}
// \u5883\u754c\u95e8\u69db\uff08\u590d\u7528\u6392\u884c\u7528\u5883\u754c\u5e8f\uff09
function sectGfRealmOk(realm: unknown, need: string): boolean {
  const i = REALM_ORDER_FOR_RANKING.indexOf(String(realm || ''));
  const j = REALM_ORDER_FOR_RANKING.indexOf(need);
  return i >= 0 && j >= 0 && i >= j;
}
// \u8bfb\u5b58\u6863 player\uff08legacy \u5b97\u95e8\u7684\u5355\u4e00\u4e8b\u5b9e\u6e90\u5728\u5ba2\u6237\u7aef\u5b58\u6863\u91cc\uff09
async function sectGfPlayerOf(userId: number): Promise<any | null> {
  const row: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
  if (!row) return null;
  try {
    const sd = JSON.parse(row.save_data);
    return sd && sd.player ? sd.player : null;
  } catch {
    return null;
  }
}
// \u6743\u5a01\u5c42\u6570\u8868
async function sectGfRows(userId: number): Promise<Record<string, number>> {
  const rows: any[] = await dbAll('SELECT gongfa_id, level FROM player_sect_gongfa WHERE user_id = ?', [userId]);
  const out: Record<string, number> = {};
  for (const r of rows || []) out[String(r.gongfa_id)] = sectGfLevel(r.level);
  return out;
}
// 12 \u90e8\u5b8c\u6574\u955c\u50cf\uff08\u7f3a\u9879\u8865 0\uff09\uff0c\u4f9b\u5199\u5165 player.sectGongfa
function sectGfMirror(levels: Record<string, number>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const g of SECT_GF_LIST) out[g.id] = sectGfLevel(levels[g.id]);
  return out;
}
// \u5b66\u4e60/\u5347\u7ea7\u5171\u7528\u6838\u5fc3\u3002mode='learn' \u8981\u6c42\u5f53\u524d 0 \u5c42\uff1bmode='upgrade' \u8981\u6c42 1..4 \u5c42\u3002
async function sectGfAdvance(userId: number, idRaw: unknown, mode: 'learn' | 'upgrade'): Promise<{ status: number; body: any }> {
  const id = asStr(idRaw);
  const def = SECT_GF_BY_ID[id];
  if (!def) return { status: 400, body: { error: '\u672a\u77e5\u7684\u5b97\u95e8\u529f\u6cd5', code: 'BAD_GONGFA' } };
  const pl = await sectGfPlayerOf(userId);
  if (!pl || !pl.sectId) return { status: 400, body: { error: '\u4f60\u8fd8\u6ca1\u6709\u52a0\u5165\u5b97\u95e8', code: 'NO_SECT' } };
  if (!sectGfRankOk(pl.sectRank, def.rank)) {
    return { status: 400, body: { error: '\u804c\u8854\u4e0d\u8db3\uff0c\u9700\u8fbe\u5230' + def.rank, code: 'RANK_TOO_LOW' } };
  }
  if (!sectGfRealmOk(pl.realm, def.realm)) {
    return { status: 400, body: { error: '\u5883\u754c\u4e0d\u8db3\uff0c\u9700\u8fbe\u5230' + def.realm, code: 'REALM_TOO_LOW' } };
  }
  const levels = await sectGfRows(userId);
  const cur = sectGfLevel(levels[id]);
  if (mode === 'learn' && cur > 0) {
    return { status: 409, body: { error: '\u8be5\u529f\u6cd5\u5df2\u9886\u609f\uff0c\u8bf7\u4f7f\u7528\u300c\u9886\u609f\u300d\u63d0\u5347\u5c42\u6570', code: 'ALREADY_LEARNED', level: cur } };
  }
  if (mode === 'upgrade' && cur <= 0) {
    return { status: 409, body: { error: '\u8be5\u529f\u6cd5\u5c1a\u672a\u5b66\u4e60', code: 'NOT_LEARNED', level: cur } };
  }
  if (cur >= SECT_GF_MAX_LEVEL) {
    return { status: 409, body: { error: '\u8be5\u529f\u6cd5\u5df2\u5927\u6210\uff085 \u5c42\uff09\uff0c\u65e0\u6cd5\u518d\u8fdb', code: 'MAXED', level: cur } };
  }
  const next = cur + 1;
  const cost = sectGfCost(def.tier, next);
  const contrib = Math.max(0, Math.floor(Number(pl.sectContribution) || 0));
  if (contrib < cost) {
    return { status: 400, body: { error: '\u5b97\u95e8\u8d21\u732e\u4e0d\u8db3\uff08\u9700 ' + cost + '\uff09', code: 'INSUFFICIENT_CONTRIBUTION', cost, contribution: contrib } };
  }
  const mirror = sectGfMirror(levels);
  mirror[id] = next;
  let applied = false;
  const r = await updatePlayerSave(userId, (sd: any) => {
    const p = sd && sd.player;
    if (!p) return;
    // \u9501\u5185\u4e8c\u6b21\u6821\u9a8c\uff1aupdatePlayerSave \u7684 mutate \u65e0\u4e2d\u6b62\u8bed\u4e49\uff0c\u4e0d\u6ee1\u8db3\u5219\u539f\u5730\u4e0d\u52a8\u3001\u96f6\u526f\u4f5c\u7528
    const bal = Math.max(0, Math.floor(Number(p.sectContribution) || 0));
    if (bal < cost) return;
    p.sectContribution = bal - cost;
    p.sectGongfa = Object.assign({}, mirror); // \u6574\u8868\u955c\u50cf\uff1a\u987a\u624b\u4fee\u590d\u88ab\u5ba2\u6237\u7aef\u5b58\u6863\u8986\u76d6\u9020\u6210\u7684\u6f02\u79fb
    applied = true;
  });
  if (!r.ok) return { status: 400, body: { error: r.error || '\u5165\u8d26\u5931\u8d25' } };
  if (!applied) {
    return { status: 400, body: { error: '\u5b97\u95e8\u8d21\u732e\u4e0d\u8db3\uff08\u9700 ' + cost + '\uff09', code: 'INSUFFICIENT_CONTRIBUTION', cost } };
  }
  // \u5c42\u6570\u843d\u8868\uff1a\u5355\u8c03\u5b88\u536b\uff08\u4ec5\u5f53\u5df2\u5b58\u5c42\u6570 < next \u624d\u5199\u5165\uff09\u3002
  // \u4e0a\u9762\u7684\u300c\u8bfb\u5c42\u6570 \u2192 \u6821\u9a8c \u2192 \u6263\u8d21\u732e\u300d\u8de8\u8d8a\u4e86 saveLock \u8fb9\u754c\uff1a\u4e24\u4e2a\u5e76\u53d1\u8bf7\u6c42\u53ef\u80fd\u90fd\u8bfb\u5230 cur=0
  // \u5e76\u5404\u81ea\u6263\u4e00\u6b21\u8d21\u732e\uff0c\u968f\u540e\u4e24\u6b21\u65e0\u6761\u4ef6 upsert \u90fd\u6210\u529f \u2192 \u540c\u4e00\u90e8\u529f\u6cd5\u88ab\u91cd\u590d\u6263\u8d21\u732e\u3002
  // \u56e0\u6b64\u8fd9\u91cc\u7528\u5355\u6761\u539f\u5b50\u8bed\u53e5\u505a\u5e76\u53d1\u95f8\u95e8\uff1a\u62a2\u5148\u8005 changes=1\uff0c\u843d\u540e\u8005 changes=0\u3002
  // \u843d\u540e\u8005\u5fc5\u987b\u628a\u521a\u624d\u6263\u6389\u7684\u8d21\u732e**\u539f\u6837\u9000\u56de**\uff0c\u5426\u5219\u8d21\u732e\u51c0\u635f\u5931\u4e00\u6b21\u3002
  const up = await dbRun(
    'INSERT INTO player_sect_gongfa (user_id, gongfa_id, level) VALUES (?, ?, ?) ON CONFLICT(user_id, gongfa_id) DO UPDATE SET level = excluded.level, updated_at = CURRENT_TIMESTAMP WHERE player_sect_gongfa.level < excluded.level',
    [userId, id, next]
  );
  if (!up.changes) {
    const fresh = await sectGfRows(userId);
    await updatePlayerSave(userId, (sd: any) => {
      const p = sd && sd.player;
      if (!p) return;
      p.sectContribution = Math.max(0, Math.floor(Number(p.sectContribution) || 0) + cost);
      p.sectGongfa = Object.assign({}, sectGfMirror(fresh));
    });
    return { status: 409, body: { error: '\u8be5\u529f\u6cd5\u5df2\u88ab\u62a2\u5148\u9886\u609f\uff0c\u8bf7\u5237\u65b0\u540e\u91cd\u8bd5', code: 'CONFLICT', cost } };
  }
  return {
    status: 200,
    body: {
      message: '\u3010' + def.name + '\u3011\u5df2\u9886\u609f\u81f3\u7b2c ' + next + ' \u5c42',
      id, name: def.name, level: next, maxed: next >= SECT_GF_MAX_LEVEL,
      cost, contribution: contrib - cost, levels: mirror,
    },
  };
}
const sectGfReadLimit = rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `sectgf:r:${req.user.id}` });
const sectGfWriteLimit = rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `sectgf:w:${req.user.id}` });

// \u5b97\u95e8\u529f\u6cd5\u5217\u8868\uff1a12 \u90e8\u76ee\u5f55 + \u6211\u7684\u5c42\u6570 + \u5f53\u524d\u8d21\u732e/\u804c\u8854/\u5883\u754c\uff08\u4e00\u9875\u5168\u91cf\uff0c\u4e0d\u843d\u8d26\uff09
app.get('/api/sect/gongfa', authenticateToken, sectGfReadLimit, async (req: any, res: any) => {
  try {
    const pl = await sectGfPlayerOf(req.user.id);
    if (!pl || !pl.sectId) return res.status(400).json({ error: '\u4f60\u8fd8\u6ca1\u6709\u52a0\u5165\u5b97\u95e8', code: 'NO_SECT' });
    const levels = await sectGfRows(req.user.id);
    res.json({
      sectId: String(pl.sectId),
      sectRank: String(pl.sectRank || ''),
      realm: String(pl.realm || ''),
      contribution: Math.max(0, Math.floor(Number(pl.sectContribution) || 0)),
      maxLevel: SECT_GF_MAX_LEVEL,
      tierBase: SECT_GF_TIER_BASE,
      gongfa: SECT_GF_LIST.map((g) => Object.assign({}, g, { cost: sectGfCost(g.tier, 1) })),
      // [r066] 化形盖章表随目录下发，面板据此渲染「已化形 / 可化为」
      converted: (pl.sectGfConverted && typeof pl.sectGfConverted === 'object') ? pl.sectGfConverted : {},
      levels: sectGfMirror(levels),
    });
  } catch (e: any) {
    console.error('sect gongfa list error:', e?.message || e);
    res.status(500).json({ error: '\u670d\u52a1\u5668\u7e41\u5fd9' });
  }
});

// \u5b66\u4e60\u5b97\u95e8\u529f\u6cd5\uff080 -> 1 \u5c42\uff09\uff1a\u804c\u8854+\u5883\u754c+\u8d21\u732e\u4e09\u91cd\u6821\u9a8c -> updatePlayerSave \u6263\u8d21\u732e\u5e76\u5199 player.sectGongfa
app.post('/api/sect/gongfa/learn', authenticateToken, sectGfWriteLimit, async (req: any, res: any) => {
  try {
    const out = await sectGfAdvance(req.user.id, req.body?.id, 'learn');
    res.status(out.status).json(out.body);
  } catch (e: any) {
    console.error('sect gongfa learn error:', e?.message || e);
    res.status(500).json({ error: '\u670d\u52a1\u5668\u7e41\u5fd9' });
  }
});

// \u9886\u609f\u5b97\u95e8\u529f\u6cd5\uff08L -> L+1 \u5c42\uff0c\u6700\u9ad8 5 \u5c42\uff09
app.post('/api/sect/gongfa/upgrade', authenticateToken, sectGfWriteLimit, async (req: any, res: any) => {
  try {
    const out = await sectGfAdvance(req.user.id, req.body?.id, 'upgrade');
    res.status(out.status).json(out.body);
  } catch (e: any) {
    console.error('sect gongfa upgrade error:', e?.message || e);
    res.status(500).json({ error: '\u670d\u52a1\u5668\u7e41\u5fd9' });
  }
});

// ── [r066] R-066 修满化形：宗门功法 5 层大成 → 消耗宗门贡献解锁对应「游戏实装」功法（基座 is 表 id，
//   写入 player.unlockedArts，功法界面即可修炼）。幂等：sectGfConverted 真值表，已化形原地不动。
//   化形费 = f(品阶) = 基价 × 16（= 第 5 层单价，= 修满总耗 基价×31 的 51.6%）；贡献不足/未修满/已化形一律 409。
//   权威扣费在 updatePlayerSave 锁内（客户端只显示、不拦）；绝不用 403（Xc 对 403 强制登出）。
//   R-067 功法大重做扩表：与客户端 yl_066_ext.py 的 YLXW_SECT_GF_CONVERT 同源同扩，端点零改动。
const SECT_GF_CONVERT_MULT = 16; // [r066] 化形费倍数（= 第 5 层 2^4；与客户端 yl_066_ext.py 的 YlxwSectGfCvtFee 同源）
function sectGfConvertFee(tier: unknown): number {
  return (SECT_GF_TIER_BASE[Math.floor(Number(tier) || 0)] || 0) * SECT_GF_CONVERT_MULT;
}
const SECT_GF_CONVERT: Record<string, string> = {
  'sgf-t1-atk': 'art-sharp-blade',
  'sgf-t1-def': 'art-earth-core',
  'sgf-t1-psi': 'art-moonlight-refine',
  'sgf-t2-atk': 'art-wind-sword',
  'sgf-t2-def': 'art-golden-protection',
  'sgf-t2-psi': 'art-frost-breath',
  'sgf-t3-atk': 'art-sword-intent',
  'sgf-t3-def': 'art-earth-mountain',
  'sgf-t3-psi': 'art-starlight-gather',
  'sgf-t4-atk': 'art-immortal-sword',
  'sgf-t4-def': 'art-earth-immortal',
  'sgf-t4-psi': 'art-dao-heart',
};
const SECT_GF_CONVERT_NAMES: Record<string, string> = {
  'art-sharp-blade': '锐刃诀',
  'art-earth-core': '土核功',
  'art-moonlight-refine': '月华淬炼诀',
  'art-wind-sword': '疾风剑',
  'art-golden-protection': '金甲护体',
  'art-frost-breath': '寒冰吐息',
  'art-sword-intent': '剑意诀',
  'art-earth-mountain': '山岳功',
  'art-starlight-gather': '聚星诀',
  'art-immortal-sword': '斩仙剑诀',
  'art-earth-immortal': '土仙体',
  'art-dao-heart': '道心诀',
};
app.post('/api/sect/gongfa/convert', authenticateToken, sectGfWriteLimit, async (req: any, res: any) => {
  try {
    const id = String(req.body?.id || '');
    const def = SECT_GF_BY_ID[id];
    const artId = SECT_GF_CONVERT[id];
    if (!def || !artId) return res.status(400).json({ error: '未知的宗门功法', code: 'BAD_GONGFA' });
    const pl = await sectGfPlayerOf(req.user.id);
    if (!pl || !pl.sectId) return res.status(400).json({ error: '你还没有加入宗门', code: 'NO_SECT' });
    const levels = await sectGfRows(req.user.id);
    const cur = sectGfLevel(levels[id]);
    if (cur < SECT_GF_MAX_LEVEL) {
      return res.status(409).json({ error: '该功法尚未修满（需 5 层大成）', code: 'NOT_MAXED', level: cur });
    }
    const fee = sectGfConvertFee(def.tier); // [r066] 化形费 = f(品阶) = 基价 × 16
    const contrib = Math.max(0, Math.floor(Number(pl.sectContribution) || 0));
    const prevCvt = (pl.sectGfConverted && typeof pl.sectGfConverted === 'object') ? pl.sectGfConverted : {};
    if (prevCvt[id]) {
      return res.status(409).json({ error: '该功法已化形，无需重复转化', code: 'ALREADY_CONVERTED' });
    }
    if (contrib < fee) {
      // [r066] 贡献不足 → 409（**绝不用 403**：Xc 对 403 强制登出）
      return res.status(409).json({ error: '宗门贡献不足（需 ' + fee + '）', code: 'INSUFFICIENT_CONTRIBUTION', cost: fee, contribution: contrib });
    }
    let done = false;
    let shortfall = false;
    const r = await updatePlayerSave(req.user.id, (sd: any) => {
      const p = sd && sd.player;
      if (!p) return;
      const prev = (p.sectGfConverted && typeof p.sectGfConverted === 'object') ? p.sectGfConverted : {};
      if (prev[id]) return; // 锁内幂等闸：已化形 → 原地不动、零副作用
      const bal = Math.max(0, Math.floor(Number(p.sectContribution) || 0));
      if (bal < fee) { shortfall = true; return; } // 锁内二次校验：余额不足 → 原地不动、零副作用
      p.sectContribution = bal - fee; // [r066] 权威扣费（客户端只显示，不拦）
      const cvt: Record<string, number> = Object.assign({}, prev);
      cvt[id] = 1;
      const arts: string[] = Array.isArray(p.unlockedArts) ? p.unlockedArts.slice() : [];
      if (arts.indexOf(artId) < 0) arts.push(artId);
      p.unlockedArts = arts;
      p.sectGfConverted = cvt;
      done = true;
    });
    if (!r.ok) return res.status(400).json({ error: r.error || '入账失败' });
    if (!done) {
      if (shortfall) return res.status(409).json({ error: '宗门贡献不足（需 ' + fee + '）', code: 'INSUFFICIENT_CONTRIBUTION', cost: fee, contribution: contrib });
      return res.status(409).json({ error: '该功法已化形，无需重复转化', code: 'ALREADY_CONVERTED' });
    }
    const fresh = await sectGfPlayerOf(req.user.id);
    const freshCvt = (fresh && fresh.sectGfConverted && typeof fresh.sectGfConverted === 'object') ? fresh.sectGfConverted : {};
    const artName = SECT_GF_CONVERT_NAMES[artId] || artId;
    return res.status(200).json({
      message: '【' + def.name + '】大成化形！已耗 ' + fee + ' 贡献，将可用功法【' + artName + '】收入囊中，可在【功法】界面修炼。',
      id, art: artId, artName, cost: fee, contribution: contrib - fee,
      converted: freshCvt,
      levels: await sectGfRows(req.user.id),
    });
  } catch (e: any) {
    console.error('sect gongfa convert error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ── V27 限流：读 60/min、写 20/min（按用户分桶；rateLimit 实现见 P1-4/P1-5 段）──
const sectReadLimit = rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `sect:r:${req.user.id}` });
const sectWriteLimit = rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `sect:w:${req.user.id}` });

// 宗门列表（分页+检索，0.8.7 T7）：keyword 走 mentorSearchName/mentorLikeEscape 同款净化
//（trim 后 1..16 字，LIKE \ % _ 前缀 \ 转义 + ESCAPE '\'，防通配注入）；排序维持等级→资金→id，分页 10/页不变。
// 响应=契约 §4.3 C1 {rows:[{id,name,level,funds,memberCount,leaderName,joinMode}],page,hasMore,mine}；
// 兼容旧伴生页（src/index-v26e 消费 list/leader/member_count）：list/pages/total 与行内旧字段双发。
// mine={sectId,myRole,pendingSectId}：「我的盟」标记与「已申请」置灰取全局一份，不在列表行重复。
app.get('/api/sect/list', authenticateToken, sectReadLimit, async (req: any, res: any) => {
  try {
    await sectExpireStaleApplications();
    const page = Math.max(1, Math.floor(Number(req.query.page)) || 1);
    let kw: string | null = null;
    const kwRaw = req.query.keyword;
    if (kwRaw !== undefined && kwRaw !== null && String(kwRaw).trim() !== '') {
      const n = String(kwRaw).trim();
      if (n.length < 1 || n.length > 16) return res.status(400).json({ error: '\u5173\u952e\u8bcd\u9700 1-16 \u4e2a\u5b57', code: 'BAD_KEYWORD' });
      kw = mentorLikeEscape(n);
    }
    const whereSql = kw ? "WHERE s.disbanded_at IS NULL AND s.name LIKE ? ESCAPE '\\'" : 'WHERE s.disbanded_at IS NULL';
    const baseParams: any[] = kw ? ['%' + kw + '%'] : [];
    const totalRow: any = await dbGet(`SELECT COUNT(*) AS c FROM sects s ${whereSql}`, baseParams);
    const total = Number(totalRow?.c) || 0;
    const rows: any[] = await dbAll(
      `SELECT s.id, s.name, s.level, s.funds, s.join_mode, lu.username AS leader,
              (SELECT COUNT(*) FROM sect_members m WHERE m.sect_id = s.id) AS member_count
       FROM sects s LEFT JOIN users lu ON lu.id = s.leader_id
       ${whereSql}
       ORDER BY s.level DESC, s.funds DESC, s.id ASC
       LIMIT ? OFFSET ?`,
      [...baseParams, SECT_LIST_PAGE_SIZE + 1, (page - 1) * SECT_LIST_PAGE_SIZE]
    );
    const hasMore = rows.length > SECT_LIST_PAGE_SIZE;
    const list = (hasMore ? rows.slice(0, SECT_LIST_PAGE_SIZE) : rows).map((r: any) => ({
      id: Number(r.id), name: String(r.name || ''), level: Number(r.level) || 1,
      funds: Number(r.funds) || 0, memberCount: Number(r.member_count) || 0,
      member_count: Number(r.member_count) || 0, leaderName: String(r.leader || ''), leader: String(r.leader || ''),
      joinMode: String(r.join_mode || 'auto') === 'apply' ? 'apply' : 'auto',
    }));
    const member = await sectMemberOf(req.user.id);
    const myApp: any = await dbGet("SELECT sect_id FROM sect_applications WHERE user_id = ? AND status = 'pending' LIMIT 1", [req.user.id]);
    res.json({
      rows: list, list, page, hasMore,
      pages: Math.max(1, Math.ceil(total / SECT_LIST_PAGE_SIZE)), total,
      mine: {
        sectId: member ? member.sect_id : null,
        myRole: member ? member.role : null,
        pendingSectId: myApp ? Number(myApp.sect_id) : null,
      },
    });
  } catch (e: any) {
    console.error('sect list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 我的宗门（全景）：宗门信息 + 成员表 + 今日任务进度与个人可领状态 + 福利可领状态
app.get('/api/sect/mine', authenticateToken, sectReadLimit, async (req: any, res: any) => {
  try {
    const member = await sectMemberOf(req.user.id);
    if (!member) {
      // 0.8.7 T7 扩展（N1 无盟视图）：myApplication（我的 pending 申请）+ cooldownUntil（退盟冷却截止）。
      await sectExpireStaleApplications();
      const app0: any = await dbGet(
        "SELECT a.id, a.sect_id, a.created_at, s.name AS sect_name FROM sect_applications a LEFT JOIN sects s ON s.id = a.sect_id WHERE a.user_id = ? AND a.status = 'pending' LIMIT 1",
        [req.user.id]
      );
      const cd0: any = await dbGet('SELECT cooldown_until FROM sect_cooldowns WHERE user_id = ?', [req.user.id]);
      const cdMs0 = cd0 ? Date.parse(String(cd0.cooldown_until || '')) : NaN;
      const cdUntil0 = Number.isFinite(cdMs0) && cdMs0 > Date.now() ? new Date(cdMs0).toISOString() : null;
      return res.json({
        sect: null,
        joinMode: null,
        myApplication: app0 ? {
          id: Number(app0.id), sectId: Number(app0.sect_id), sectName: String(app0.sect_name || ''),
          createdAt: Number(app0.created_at) || 0,
          expiresAt: (Number(app0.created_at) || 0) + SECT_APPLY_TTL_MS,
        } : null,
        applications: [],
        cooldownUntil: cdUntil0,
        applyTtlMs: SECT_APPLY_TTL_MS,
      });
    }
    const sect: any = await dbGet('SELECT * FROM sects WHERE id = ?', [member.sect_id]);
    if (!sect || sect.disbanded_at) return res.json({ sect: null }); // 解散竞态兜底
    const members: any[] = await dbAll(
      `SELECT m.user_id, m.role, m.joined_at,
              COALESCE(NULLIF(r.name, ''), u.username) AS name,
              r.realm_index, r.realm_level, r.combat_power
       FROM sect_members m
       LEFT JOIN users u ON u.id = m.user_id
       LEFT JOIN rankings r ON r.user_id = m.user_id
       WHERE m.sect_id = ?
       ORDER BY CASE m.role WHEN 'leader' THEN 0 WHEN 'officer' THEN 1 ELSE 2 END, r.combat_power DESC, m.user_id ASC`,
      [member.sect_id]
    );
    const date = bjDate(Date.now());
    const taskRows: any[] = await dbAll('SELECT task_key, progress, done FROM sect_tasks WHERE sect_id = ? AND date = ?', [member.sect_id, date]);
    const claimRows: any[] = await dbAll('SELECT task_key FROM sect_task_claims WHERE user_id = ? AND date = ?', [req.user.id, date]);
    const claimedSet = new Set(claimRows.map((r: any) => String(r.task_key)));
    const tasks = SECT_TASK_DEFS.map((def) => {
      const row = taskRows.find((r: any) => String(r.task_key) === def.key);
      const progress = Math.min(def.target, Number(row?.progress) || 0);
      return {
        key: def.key, name: def.name, desc: def.desc, target: def.target, progress,
        done: (Number(row?.done) || 0) === 1, reward: def.reward, claimed: claimedSet.has(def.key),
      };
    });
    const welfareRows: any[] = await dbAll('SELECT kind FROM sect_welfare_claims WHERE user_id = ? AND date = ?', [req.user.id, date]);
    const claimedKinds = new Set(welfareRows.map((r: any) => String(r.kind)));
    const level = Number(sect.level) || 1;
    // 0.8.7 T7 扩展（N1 有盟视图）：joinMode / applications（仅盟主长老可见，成员得空数组）/
    // cooldownUntil（我方退盟冷却截止）/ applyTtlMs。在盟时 myApplication 恒 null
    //（join 直进成功会撤残留申请、审批入盟时申请行已 approved，无 pending 残留）。
    const isMgr = member.role === 'leader' || member.role === 'officer';
    const cdRow: any = await dbGet('SELECT cooldown_until FROM sect_cooldowns WHERE user_id = ?', [req.user.id]);
    const cdMs = cdRow ? Date.parse(String(cdRow.cooldown_until || '')) : NaN;
    const cooldownUntil = Number.isFinite(cdMs) && cdMs > Date.now() ? new Date(cdMs).toISOString() : null;
    const apps: any[] = isMgr ? await dbAll(
      `SELECT a.id, a.user_id, a.created_at,
              COALESCE(NULLIF(r.name, ''), u.username) AS name,
              r.realm_index, r.realm_level, r.combat_power
       FROM sect_applications a
       LEFT JOIN users u ON u.id = a.user_id
       LEFT JOIN rankings r ON r.user_id = a.user_id
       WHERE a.sect_id = ? AND a.status = 'pending'
       ORDER BY a.created_at ASC
       LIMIT 50`,
      [member.sect_id]
    ) : [];
    const joinModeNow = String(sect.join_mode || 'auto') === 'apply' ? 'apply' : 'auto';
    res.json({
      sect: {
        id: sect.id, name: sect.name, level, funds: Number(sect.funds) || 0,
        notice: String(sect.notice || ''), memberCount: members.length,
        memberCap: SECT_MEMBER_CAP(level), createdAt: sect.created_at ?? null,
        joinMode: joinModeNow,
      },
      myRole: member.role,
      members,
      tasks,
      joinMode: joinModeNow,
      myApplication: null,
      applications: apps.map((a: any) => ({
        id: Number(a.id), userId: Number(a.user_id), name: String(a.name || ''),
        realmName: REALM_ORDER_FOR_RANKING[Number(a.realm_index)] || '',
        level: mentorLevelOf(a.realm_index, a.realm_level),
        combatPower: Math.max(0, Math.floor(Number(a.combat_power) || 0)),
        createdAt: Number(a.created_at) || 0,
        expiresAt: (Number(a.created_at) || 0) + SECT_APPLY_TTL_MS,
      })),
      cooldownUntil,
      applyTtlMs: SECT_APPLY_TTL_MS,
      welfare: {
        salary: { amount: level * SECT_SALARY_PER_LEVEL, claimed: claimedKinds.has('salary') },
        pill: { unlocked: level >= SECT_PILL_MIN_LEVEL, claimed: claimedKinds.has('pill'), name: SECT_PILL_NAME },
      },
    });
  } catch (e: any) {
    console.error('sect mine error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 创建宗门：境界≥元婴 + 名称唯一 + 1000000 灵石（服务端结算：spendFromSave 失败即无宗；0.8.7 T7 顺手修正注释 5000→50000；0.8.8 item15 门槛 50000→1000000、筑基→元婴）
app.post('/api/sect/create', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const name = asStr(req.body?.name).trim();
    if (name.length < SECT_NAME_MIN || name.length > SECT_NAME_MAX) {
      return res.status(400).json({ error: `宗门名称需 ${SECT_NAME_MIN}-${SECT_NAME_MAX} 个字`, code: 'BAD_NAME' });
    }
    if (!/^[a-zA-Z0-9_\u4e00-\u9fa5]+$/.test(name)) {
      return res.status(400).json({ error: '宗门名称只能含中文、字母、数字、下划线', code: 'BAD_NAME' });
    }
    const dup: any = await dbGet('SELECT id FROM sects WHERE name = ?', [name]);
    if (dup) return res.status(409).json({ error: '宗门名称已被使用', code: 'NAME_TAKEN' });
    if (await sectMemberOf(req.user.id)) {
      return res.status(400).json({ error: '你已有宗门，请先退出再创建', code: 'ALREADY_IN_SECT' });
    }
    const saveRow: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [req.user.id]);
    let realm = '';
    try { realm = String(JSON.parse(saveRow?.save_data)?.player?.realm ?? ''); } catch { realm = ''; }
    if (REALM_ORDER_FOR_RANKING.indexOf(realm) < SECT_CREATE_MIN_REALM) {
      return res.status(400).json({ error: '境界需达到元婴期方可开宗立派', code: 'REALM_TOO_LOW' });
    }
    let sectId = 0;
    try {
      const ins = await dbRun('INSERT INTO sects (name, leader_id) VALUES (?, ?)', [name, req.user.id]);
      sectId = ins.lastID;
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '宗门名称已被使用', code: 'NAME_TAKEN' });
      throw e;
    }
    // 扣费（withSaveLock 内二次校验，防双开同扣）；失败补偿删宗，保证无中间态外泄
    const spend = await spendFromSave(req.user.id, SECT_CREATE_COST);
    if (!spend.ok) {
      await dbRun('DELETE FROM sects WHERE id = ?', [sectId]).catch(() => undefined);
      if (spend.error === 'INSUFFICIENT_STONES') {
        return res.status(400).json({ error: `灵石不足（开宗需 ${SECT_CREATE_COST} 灵石）`, code: 'INSUFFICIENT_STONES' });
      }
      return res.status(400).json({ error: spend.error || '开宗失败' });
    }
    try {
      await dbRun('INSERT INTO sect_members (sect_id, user_id, role) VALUES (?, ?, ?)', [sectId, req.user.id, 'leader']);
    } catch (e: any) {
      // 并发竞态（入会瞬间已在别宗）：退款+删宗
      await updatePlayerSave(req.user.id, (sd: any) => {
        sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + SECT_CREATE_COST;
      }).catch(() => undefined);
      await dbRun('DELETE FROM sects WHERE id = ?', [sectId]).catch(() => undefined);
      return res.status(400).json({ error: '你已有宗门，请先退出再创建', code: 'ALREADY_IN_SECT' });
    }
    res.json({ message: '宗门创建成功', sect: { id: sectId, name }, spiritStones: spend.spiritStones ?? null });
  } catch (e: any) {
    console.error('sect create error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 加入宗门：24h 冷却（服务端 sect_cooldowns）+ 人数上限 level*10+20
app.post('/api/sect/join', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const sectId = Math.floor(asNum(req.body?.sectId));
    if (!Number.isFinite(sectId) || sectId <= 0) return res.status(400).json({ error: '参数非法' });
    if (await sectMemberOf(req.user.id)) {
      return res.status(400).json({ error: '你已在宗门中', code: 'ALREADY_IN_SECT' });
    }
    const cd: any = await dbGet('SELECT cooldown_until FROM sect_cooldowns WHERE user_id = ?', [req.user.id]);
    if (cd) {
      const untilMs = Date.parse(String(cd.cooldown_until || ''));
      if (Number.isFinite(untilMs) && untilMs > Date.now()) {
        return res.status(409).json({
          error: '退宗冷却中，24 小时后方可加入新宗门', code: 'COOLDOWN_UNTIL',
          until: new Date(untilMs).toISOString(),
          cooldownLeftMs: Math.max(0, untilMs - Date.now()),
        });
      }
    }
    const sect: any = await dbGet('SELECT id, level, disbanded_at, join_mode FROM sects WHERE id = ?', [sectId]);
    if (!sect || sect.disbanded_at) return res.status(404).json({ error: '宗门不存在或已解散' });
    const cntRow: any = await dbGet('SELECT COUNT(*) AS c FROM sect_members WHERE sect_id = ?', [sectId]);
    if ((Number(cntRow?.c) || 0) >= SECT_MEMBER_CAP(Number(sect.level) || 1)) {
      return res.status(400).json({ error: '该宗门人数已满', code: 'SECT_FULL' });
    }
    const joinMode = String(sect.join_mode || 'auto') === 'apply' ? 'apply' : 'auto';
    if (joinMode === 'apply') {
      // 0.8.7 T7：审批制盟 → 写 pending 申请（一人一 pending 由用户侧部分唯一索引
      // 兜底挡重复→409；72h 有效期由读取路径惰性置 expired）。满员/冷却/已在盟检查已在上方与 auto 共用。
      try {
        await dbRun('INSERT INTO sect_applications (sect_id, user_id, status, created_at) VALUES (?, ?, ?, ?)', [sectId, req.user.id, 'pending', Date.now()]);
      } catch (e: any) {
        if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '\u5df2\u6709\u5f85\u5904\u7406\u7684\u7533\u8bf7\uff0c\u8bf7\u5148\u64a4\u9500\u6216\u7b49\u5f85\u5ba1\u6279', code: 'APP_PENDING' });
        throw e;
      }
      return res.json({ ok: true, message: '\u7533\u8bf7\u5df2\u63d0\u4ea4\uff0c\u7b49\u5f85\u76df\u4e3b/\u957f\u8001\u5ba1\u6838', joinMode });
    }
    try {
      await dbRun('INSERT INTO sect_members (sect_id, user_id, role) VALUES (?, ?, ?)', [sectId, req.user.id, 'member']);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(400).json({ error: '你已在宗门中', code: 'ALREADY_IN_SECT' });
      throw e;
    }
    // 0.8.7 T7：直进入盟成功即撤销本人残留 pending 申请（防审批竞态产生死申请；fire-and-forget）
    await dbRun("UPDATE sect_applications SET status = 'cancelled', handled_at = ?, handled_by = ? WHERE user_id = ? AND status = 'pending'", [Date.now(), req.user.id, req.user.id]).catch(() => undefined);
    res.json({ message: '入宗成功' });
  } catch (e: any) {
    console.error('sect join error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 退出宗门：宗主不可退（先转让/解散）；退宗写 24h 冷却
app.post('/api/sect/leave', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const member = await sectMemberOf(req.user.id);
    if (!member) return res.status(400).json({ error: '你还没有加入宗门', code: 'NO_SECT' });
    if (member.role === 'leader') {
      return res.status(400).json({ error: '宗主不可退宗，请先转让宗主或解散宗门', code: 'LEADER_CANNOT_LEAVE' });
    }
    await dbRun('DELETE FROM sect_members WHERE user_id = ?', [req.user.id]);
    const until = new Date(Date.now() + SECT_LEAVE_COOLDOWN_MS).toISOString();
    await dbRun(
      'INSERT INTO sect_cooldowns (user_id, cooldown_until) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET cooldown_until = excluded.cooldown_until',
      [req.user.id, until]
    );
    res.json({ message: '已退宗', cooldownUntil: until });
  } catch (e: any) {
    console.error('sect leave error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 移除成员：宗主可踢长老/成员，长老只能踢成员；被踢同写 24h 冷却
app.post('/api/sect/kick', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const targetId = Math.floor(asNum(req.body?.userId));
    if (!Number.isFinite(targetId) || targetId <= 0) return res.status(400).json({ error: '参数非法' });
    const actor = await sectMemberOf(req.user.id);
    if (!actor || (actor.role !== 'leader' && actor.role !== 'officer')) return res.status(400).json({ error: '无权限' });
    if (targetId === req.user.id) return res.status(400).json({ error: '不能移除自己，请使用退出宗门' });
    const target = await sectMemberOf(targetId);
    if (!target || target.sect_id !== actor.sect_id) return res.status(400).json({ error: '目标不在本宗', code: 'NOT_SAME_SECT' });
    if (target.role === 'leader') return res.status(400).json({ error: '不能移除宗主' });
    if (actor.role === 'officer' && target.role !== 'member') return res.status(400).json({ error: '长老只能移除普通成员' });
    await dbRun('DELETE FROM sect_members WHERE sect_id = ? AND user_id = ?', [actor.sect_id, targetId]);
    const until = new Date(Date.now() + SECT_LEAVE_COOLDOWN_MS).toISOString();
    await dbRun(
      'INSERT INTO sect_cooldowns (user_id, cooldown_until) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET cooldown_until = excluded.cooldown_until',
      [targetId, until]
    );
    res.json({ message: '已移出宗门' });
  } catch (e: any) {
    console.error('sect kick error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 任免职位：仅宗主；长老/成员互转，宗主职位不可改（转让另走 /transfer）
app.post('/api/sect/role', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const targetId = Math.floor(asNum(req.body?.userId));
    const role = asStr(req.body?.role);
    if (!Number.isFinite(targetId) || targetId <= 0) return res.status(400).json({ error: '参数非法' });
    if (role !== 'officer' && role !== 'member') return res.status(400).json({ error: '职位参数非法' });
    const actor = await sectMemberOf(req.user.id);
    if (!actor || actor.role !== 'leader') return res.status(400).json({ error: '仅宗主可任免职位' });
    if (targetId === req.user.id) return res.status(400).json({ error: '宗主职位不可变更，请使用转让宗主' });
    const target = await sectMemberOf(targetId);
    if (!target || target.sect_id !== actor.sect_id) return res.status(400).json({ error: '目标不在本宗' });
    if (target.role === 'leader') return res.status(400).json({ error: '宗主职位不可变更' });
    await dbRun('UPDATE sect_members SET role = ? WHERE sect_id = ? AND user_id = ?', [role, actor.sect_id, targetId]);
    res.json({ message: role === 'officer' ? '已任命为长老' : '已设为成员' });
  } catch (e: any) {
    console.error('sect role error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 转让宗主：仅宗主；目标须为本宗长老/成员，原宗主转为长老
app.post('/api/sect/transfer', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const targetId = Math.floor(asNum(req.body?.userId));
    if (!Number.isFinite(targetId) || targetId <= 0) return res.status(400).json({ error: '参数非法' });
    const actor = await sectMemberOf(req.user.id);
    if (!actor || actor.role !== 'leader') return res.status(400).json({ error: '仅宗主可转让宗主之位' });
    if (targetId === req.user.id) return res.status(400).json({ error: '不能转让给自己' });
    const target = await sectMemberOf(targetId);
    if (!target || target.sect_id !== actor.sect_id) return res.status(400).json({ error: '目标不在本宗' });
    await dbRun('UPDATE sect_members SET role = ? WHERE sect_id = ? AND user_id = ?', ['leader', actor.sect_id, targetId]);
    await dbRun('UPDATE sect_members SET role = ? WHERE sect_id = ? AND user_id = ?', ['officer', actor.sect_id, req.user.id]);
    await dbRun('UPDATE sects SET leader_id = ? WHERE id = ?', [targetId, actor.sect_id]);
    res.json({ message: '宗主之位已禅让' });
  } catch (e: any) {
    console.error('sect transfer error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 解散宗门：仅宗主；硬删全员成员行 + 每人写 24h 冷却 + sects.disbanded_at 置位（列表不可见）
app.post('/api/sect/disband', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const actor = await sectMemberOf(req.user.id);
    if (!actor || actor.role !== 'leader') return res.status(400).json({ error: '仅宗主可解散宗门' });
    const members: any[] = await dbAll('SELECT user_id FROM sect_members WHERE sect_id = ?', [actor.sect_id]);
    const until = new Date(Date.now() + SECT_LEAVE_COOLDOWN_MS).toISOString();
    await dbRun('DELETE FROM sect_members WHERE sect_id = ?', [actor.sect_id]);
    for (const m of members) {
      await dbRun(
        'INSERT INTO sect_cooldowns (user_id, cooldown_until) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET cooldown_until = excluded.cooldown_until',
        [Number(m.user_id), until]
      ).catch(() => undefined);
    }
    await dbRun('UPDATE sects SET disbanded_at = ? WHERE id = ?', [nowIso(), actor.sect_id]);
    res.json({ message: '宗门已解散' });
  } catch (e: any) {
    console.error('sect disband error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 捐献：单笔 100~100000、每人每日累计 ≤50000（sect_ledger 北京日切 SUM）；
// 扣款 spendFromSave（防双开同扣）→ funds 自增 + 升级判定 + 流水 + 推进捐献任务
app.post('/api/sect/contribute', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const amount = asNum(req.body?.amount);
    if (!Number.isInteger(amount) || amount < SECT_DONATE_MIN || amount > SECT_DONATE_MAX) {
      return res.status(400).json({ error: `单笔捐献需 ${SECT_DONATE_MIN} ~ ${SECT_DONATE_MAX} 整数灵石`, code: 'BAD_AMOUNT' });
    }
    const member = await sectMemberOf(req.user.id);
    if (!member) return res.status(400).json({ error: '你还没有加入宗门', code: 'NO_SECT' });
    const sect: any = await dbGet('SELECT id, disbanded_at FROM sects WHERE id = ?', [member.sect_id]);
    if (!sect || sect.disbanded_at) return res.status(400).json({ error: '宗门不存在或已解散' });
    const dayFloor = bjDayUtcFloor(bjDate(Date.now()));
    const sumRow: any = await dbGet('SELECT COALESCE(SUM(amount), 0) AS s FROM sect_ledger WHERE user_id = ? AND created_at >= ?', [req.user.id, dayFloor]);
    const donated = Number(sumRow?.s) || 0;
    if (donated + amount > SECT_DONATE_DAILY_CAP) {
      return res.status(400).json({ error: `今日捐献已达上限（每人每日 ${SECT_DONATE_DAILY_CAP} 灵石）`, code: 'DAILY_CAP' });
    }
    const spend = await spendFromSave(req.user.id, amount);
    if (!spend.ok) {
      if (spend.error === 'INSUFFICIENT_STONES') return res.status(400).json({ error: '灵石不足', code: 'INSUFFICIENT_STONES' });
      return res.status(400).json({ error: spend.error || '捐献失败' });
    }
    await dbRun('UPDATE sects SET funds = funds + ? WHERE id = ?', [amount, member.sect_id]);
    const fresh: any = await dbGet('SELECT funds, level FROM sects WHERE id = ?', [member.sect_id]);
    const funds = Number(fresh?.funds) || 0;
    const newLevel = sectLevelForFunds(funds);
    const levelUp = newLevel > (Number(fresh?.level) || 1);
    if (levelUp) await dbRun('UPDATE sects SET level = ? WHERE id = ?', [newLevel, member.sect_id]);
    await dbRun('INSERT INTO sect_ledger (sect_id, user_id, amount, after_funds) VALUES (?, ?, ?, ?)', [member.sect_id, req.user.id, amount, funds]);
    // 0.8.7 T7 P1 捐献回馈：floor(捐献额×2%) 写个人 sectContribution（两套宗门唯一经济互通点；
    // 数值定档《数值表-T7T8》T7-7/8）。日上限=SECT_DONATE_DAILY_CAP×2%=1000，由上方日捐献累计
    // 上限天然钳制（常量单一来源，调贡献率时上限自动跟随），不另设常量不另加查询。
    // 顺序契约：先扣款成功、再发回馈；回馈写失败仅日志不回滚捐献（贡献无灵石回流路径，无对价风险为零）
    const contribBack = Math.floor(amount * SECT_DONATE_CONTRIB_RATE);
    if (contribBack > 0) {
      const rb = await updatePlayerSave(req.user.id, (sd: any) => {
        const p = sd && sd.player;
        if (p) p.sectContribution = Math.max(0, Math.floor(Number(p.sectContribution) || 0)) + contribBack;
      });
      if (!rb.ok) console.error('sect contribute contrib-back error:', rb.error || 'unknown');
    }
    const date = bjDate(Date.now());
    const def = SECT_TASK_DEFS.find((d) => d.key === 'contribute')!;
    await dbRun('INSERT OR IGNORE INTO sect_tasks (sect_id, date, task_key, progress, done) VALUES (?, ?, ?, 0, 0)', [member.sect_id, date, def.key]);
    await dbRun(
      `UPDATE sect_tasks SET
         progress = MIN(?, progress + ?),
         done = CASE WHEN MIN(?, progress + ?) >= ? THEN 1 ELSE done END
       WHERE sect_id = ? AND date = ? AND task_key = ?`,
      [def.target, amount, def.target, amount, def.target, member.sect_id, date, def.key]
    );
    res.json({
      message: '捐献成功', funds, level: newLevel, levelUp,
      donated: donated + amount, dailyCap: SECT_DONATE_DAILY_CAP, spiritStones: spend.spiritStones ?? null,
      contribBack,
    });
  } catch (e: any) {
    console.error('sect contribute error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 领取宗门任务奖励：核验所在宗当日任务 done=1 + sect_task_claims 主键防重 → updatePlayerSave 发灵石
app.post('/api/sect/tasks/claim', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const taskKey = asStr(req.body?.taskKey);
    const def = SECT_TASK_DEFS.find((d) => d.key === taskKey);
    if (!def) return res.status(400).json({ error: '任务不存在', code: 'BAD_TASK' });
    const member = await sectMemberOf(req.user.id);
    if (!member) return res.status(400).json({ error: '你还没有加入宗门', code: 'NO_SECT' });
    const date = bjDate(Date.now());
    const taskRow: any = await dbGet('SELECT done FROM sect_tasks WHERE sect_id = ? AND date = ? AND task_key = ?', [member.sect_id, date, def.key]);
    if (!taskRow || (Number(taskRow.done) || 0) !== 1) {
      return res.status(400).json({ error: '该任务尚未完成', code: 'TASK_NOT_DONE' });
    }
    try {
      await dbRun('INSERT INTO sect_task_claims (user_id, date, task_key, claimed_at) VALUES (?, ?, ?, ?)', [req.user.id, date, def.key, nowIso()]);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '今日该任务奖励已领取', code: 'ALREADY_CLAIMED' });
      throw e;
    }
    const grant = await updatePlayerSave(req.user.id, (saveData: any) => {
      saveData.player.spiritStones = (Number(saveData.player.spiritStones) || 0) + def.reward;
    });
    if (!grant.ok) {
      await dbRun('DELETE FROM sect_task_claims WHERE user_id = ? AND date = ? AND task_key = ?', [req.user.id, date, def.key]).catch(() => undefined);
      return res.status(400).json({ error: grant.error || '奖励发放失败' });
    }
    res.json({ message: '奖励已入账', reward: def.reward });
  } catch (e: any) {
    console.error('sect task claim error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 领取宗门福利：salary=每日俸禄 level*500 灵石（全员）；pill=宗门丹药（等级≥2，发背包）
app.post('/api/sect/welfare/claim', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const kind = asStr(req.body?.kind);
    if (kind !== 'salary' && kind !== 'pill') return res.status(400).json({ error: '福利类型非法', code: 'BAD_KIND' });
    const member = await sectMemberOf(req.user.id);
    if (!member) return res.status(400).json({ error: '你还没有加入宗门', code: 'NO_SECT' });
    const sect: any = await dbGet('SELECT level, disbanded_at FROM sects WHERE id = ?', [member.sect_id]);
    if (!sect || sect.disbanded_at) return res.status(400).json({ error: '宗门不存在或已解散' });
    const level = Number(sect.level) || 1;
    if (kind === 'pill' && level < SECT_PILL_MIN_LEVEL) {
      return res.status(400).json({ error: `宗门丹药 ${SECT_PILL_MIN_LEVEL} 级解锁`, code: 'LEVEL_LOCKED' });
    }
    const date = bjDate(Date.now());
    try {
      await dbRun('INSERT INTO sect_welfare_claims (user_id, date, kind, claimed_at) VALUES (?, ?, ?, ?)', [req.user.id, date, kind, nowIso()]);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '今日已领取', code: 'ALREADY_CLAIMED' });
      throw e;
    }
    const grant = await updatePlayerSave(req.user.id, (saveData: any) => {
      if (kind === 'salary') {
        saveData.player.spiritStones = (Number(saveData.player.spiritStones) || 0) + level * SECT_SALARY_PER_LEVEL;
      } else {
        saveData.player.inventory = Array.isArray(saveData.player.inventory) ? saveData.player.inventory : [];
        const existing = saveData.player.inventory.find((it: any) => it && it.name === SECT_PILL_NAME);
        if (existing) existing.quantity = (Number(existing.quantity) || 0) + 1;
        else saveData.player.inventory.push(sectPillItem());
      }
    });
    if (!grant.ok) {
      await dbRun('DELETE FROM sect_welfare_claims WHERE user_id = ? AND date = ? AND kind = ?', [req.user.id, date, kind]).catch(() => undefined);
      return res.status(400).json({ error: grant.error || '福利发放失败' });
    }
    if (kind === 'salary') res.json({ message: '俸禄已入账', reward: level * SECT_SALARY_PER_LEVEL });
    else res.json({ message: `${SECT_PILL_NAME} 已放入背包`, item: SECT_PILL_NAME });
  } catch (e: any) {
    console.error('sect welfare claim error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// [r081salary] R-081 \u5b97\u95e8\u4ff8\u7984\uff08\u6309\u804c\u4f4d\u6bcf\u65e5\u9886\u53d6\uff09\uff1a
//   \u804c\u4f4d\u6765\u6e90=\u5b58\u6863 player.sectRank\uff08\u5916\u95e8\u5f1f\u5b50/\u5185\u95e8\u5f1f\u5b50/\u771f\u4f20\u5f1f\u5b50/\u957f\u8001/\u5b97\u4e3b\uff0c\u4e0e SECT_GF_RANK_ORDER \u540c\u6e90\uff09\uff1b
//   \u5e42\u7b49=sect_welfare_claims PK(user_id,date,kind=rank_salary)\uff08UNIQUE \u51b2\u7a81\u5373 409\uff09\uff1b
//   \u7075\u77f3\u4f59\u989d\u7531 YL_STONE_ECHO_V26K \u4e2d\u95f4\u4ef6\u81ea\u52a8\u56de\u663e\uff1b\u8d21\u732e\u503c\u5728\u56de\u6267\u91cc\u56de\u663e\u3002
const SECT_RANK_SALARY: Record<string, { spiritStones: number; contribution: number }> = {
  '\u5916\u95e8\u5f1f\u5b50': { spiritStones: 1000, contribution: 10 },
  '\u5185\u95e8\u5f1f\u5b50': { spiritStones: 2500, contribution: 25 },
  '\u771f\u4f20\u5f1f\u5b50': { spiritStones: 6000, contribution: 60 },
  '\u957f\u8001': { spiritStones: 12000, contribution: 120 },
  '\u5b97\u4e3b': { spiritStones: 25000, contribution: 300 },
};
const SECT_RANK_SALARY_ORDER = ['\u5916\u95e8\u5f1f\u5b50', '\u5185\u95e8\u5f1f\u5b50', '\u771f\u4f20\u5f1f\u5b50', '\u957f\u8001', '\u5b97\u4e3b'];
// \u672a\u77e5/\u7f3a\u5931\u804c\u8854\u4e00\u5f8b\u6309\u6700\u4f4e\u6863\uff08\u9632\u8d8a\u6743\u591a\u9886\uff09
function sectSalaryOf(rank: unknown): { spiritStones: number; contribution: number } {
  return SECT_RANK_SALARY[String(rank || '')] || SECT_RANK_SALARY[SECT_RANK_SALARY_ORDER[0]];
}
// \u4eca\u65e5\u53ef\u9886/\u5df2\u9886\uff08\u53ea\u8bfb\uff09
app.get('/api/sect/salary/status', authenticateToken, sectReadLimit, async (req: any, res: any) => {
  try {
    const pl = await sectGfPlayerOf(req.user.id);
    if (!pl || !pl.sectId) return res.json({ inSect: false, claimed: false });
    const rank = String(pl.sectRank || '');
    const sal = sectSalaryOf(rank);
    const date = bjDate(Date.now());
    const row: any = await dbGet('SELECT 1 AS c FROM sect_welfare_claims WHERE user_id = ? AND date = ? AND kind = ?', [req.user.id, date, 'rank_salary']);
    res.json({ inSect: true, rank, spiritStones: sal.spiritStones, contribution: sal.contribution, claimed: !!row, date });
  } catch (e: any) {
    console.error('sect salary status error:', e?.message || e);
    res.status(500).json({ error: '\u670d\u52a1\u5668\u7e41\u5fd9' });
  }
});
// \u9886\u53d6\u5b97\u95e8\u4ff8\u7984\uff08\u6309\u804c\u4f4d\uff1b\u6bcf\u65e5\u9650\u4e00\u6b21\uff09
app.post('/api/sect/salary', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const pl = await sectGfPlayerOf(req.user.id);
    if (!pl || !pl.sectId) return res.status(400).json({ error: '\u4f60\u8fd8\u6ca1\u6709\u52a0\u5165\u5b97\u95e8\uff0c\u65e0\u6cd5\u9886\u53d6\u4ff8\u7984', code: 'NO_SECT' });
    const rank = String(pl.sectRank || '');
    const sal = sectSalaryOf(rank);
    const date = bjDate(Date.now());
    try {
      await dbRun('INSERT INTO sect_welfare_claims (user_id, date, kind, claimed_at) VALUES (?, ?, ?, ?)', [req.user.id, date, 'rank_salary', nowIso()]);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '\u4eca\u65e5\u4ff8\u7984\u5df2\u9886\u53d6', code: 'ALREADY_CLAIMED' });
      throw e;
    }
    let contribAfter = 0;
    const grant = await updatePlayerSave(req.user.id, (saveData: any) => {
      const p = saveData && saveData.player;
      if (!p) return;
      p.spiritStones = (Number(p.spiritStones) || 0) + sal.spiritStones;
      const c0 = Math.max(0, Math.floor(Number(p.sectContribution) || 0));
      p.sectContribution = c0 + sal.contribution;
      contribAfter = p.sectContribution;
    });
    if (!grant.ok) {
      await dbRun('DELETE FROM sect_welfare_claims WHERE user_id = ? AND date = ? AND kind = ?', [req.user.id, date, 'rank_salary']).catch(() => undefined);
      return res.status(400).json({ error: grant.error || '\u4ff8\u7984\u53d1\u653e\u5931\u8d25' });
    }
    res.json({ message: '\u4ff8\u7984\u5df2\u5165\u8d26', rank, reward: { spiritStones: sal.spiritStones, contribution: sal.contribution }, contribution: contribAfter, date });
  } catch (e: any) {
    console.error('sect salary error:', e?.message || e);
    res.status(500).json({ error: '\u670d\u52a1\u5668\u7e41\u5fd9' });
  }
});

// 编辑宗门公告：仅宗主（≤200 字；设计稿管理页配套端点）
app.post('/api/sect/notice', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const notice = asStr(req.body?.notice).trim().slice(0, 200);
    const actor = await sectMemberOf(req.user.id);
    if (!actor || (actor.role !== 'leader' && actor.role !== 'officer')) return res.status(400).json({ error: '\u4ec5\u76df\u4e3b\u6216\u957f\u8001\u53ef\u7f16\u8f91\u516c\u544a' });
    await dbRun('UPDATE sects SET notice = ? WHERE id = ?', [notice, actor.sect_id]);
    res.json({ message: '公告已更新', notice });
  } catch (e: any) {
    console.error('sect notice error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 宗门详情（登录即可看；管理类操作另走各写端点的权限校验）
app.get('/api/sect/:id', authenticateToken, sectReadLimit, async (req: any, res: any) => {
  try {
    const sectId = Math.floor(Number(req.params.id));
    if (!Number.isFinite(sectId) || sectId <= 0) return res.status(400).json({ error: '参数非法' });
    const sect: any = await dbGet(
      `SELECT s.id, s.name, s.level, s.funds, s.notice, s.created_at, lu.username AS leader,
              (SELECT COUNT(*) FROM sect_members m WHERE m.sect_id = s.id) AS member_count
       FROM sects s LEFT JOIN users lu ON lu.id = s.leader_id
       WHERE s.id = ? AND s.disbanded_at IS NULL`,
      [sectId]
    );
    if (!sect) return res.status(404).json({ error: '宗门不存在或已解散' });
    const members: any[] = await dbAll(
      `SELECT m.user_id, m.role,
              COALESCE(NULLIF(r.name, ''), u.username) AS name,
              r.realm_index, r.combat_power
       FROM sect_members m
       LEFT JOIN users u ON u.id = m.user_id
       LEFT JOIN rankings r ON r.user_id = m.user_id
       WHERE m.sect_id = ?
       ORDER BY CASE m.role WHEN 'leader' THEN 0 WHEN 'officer' THEN 1 ELSE 2 END, r.combat_power DESC, m.user_id ASC`,
      [sectId]
    );
    const date = bjDate(Date.now());
    const taskRows: any[] = await dbAll('SELECT task_key, progress, done FROM sect_tasks WHERE sect_id = ? AND date = ?', [sectId, date]);
    const tasks = SECT_TASK_DEFS.map((def) => {
      const row = taskRows.find((r: any) => String(r.task_key) === def.key);
      const progress = Math.min(def.target, Number(row?.progress) || 0);
      return { key: def.key, name: def.name, desc: def.desc, target: def.target, progress, done: (Number(row?.done) || 0) === 1, reward: def.reward };
    });
    const level = Number(sect.level) || 1;
    res.json({
      sect: {
        id: sect.id, name: sect.name, level, funds: Number(sect.funds) || 0,
        notice: String(sect.notice || ''), leader: sect.leader ?? '',
        memberCount: Number(sect.member_count) || 0, memberCap: SECT_MEMBER_CAP(level),
        createdAt: sect.created_at ?? null,
      },
      members,
      tasks,
    });
  } catch (e: any) {
    console.error('sect detail error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 0.8.7 T7 N2：撤销我的 pending 申请（部分唯一索引保证一人最多一条；撤销后可立即再申请——
// 拒绝/撤销不进 24h 冷却，冷却只由 leave/kick/disband 三个写入点产生）
app.post('/api/sect/applications/cancel', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const up = await dbRun("UPDATE sect_applications SET status = 'cancelled', handled_at = ?, handled_by = ? WHERE user_id = ? AND status = 'pending'", [Date.now(), req.user.id, req.user.id]);
    if (!up.changes) return res.status(409).json({ error: '\u6ca1\u6709\u5f85\u5904\u7406\u7684\u7533\u8bf7', code: 'NO_PENDING' });
    res.json({ ok: true });
  } catch (e: any) {
    console.error('sect app cancel error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 0.8.7 T7 N3：审批入盟申请（approve/reject；权限=盟主+长老，§3 权限矩阵）。
// 顺序契约=先占位（单语句守卫 UPDATE 防并发双批/重复审批，changes=1 者才有资格动成员表）
// → 守卫式 INSERT 成员行（已在盟/冷却/满员三门槛一次原子生效，并发靠唯一索引兜底）
// → 插入失败回滚申请行 pending + 409 逐项诊断（口径抄 /api/mentor/apprentice :6510-6523）
// → 成功/拒绝均邮件通知申请人（先例 :6527-6532，fire-and-forget 不阻塞响应）。
// 错误码纪律：业务拒绝一律 400/409，绝不用 403（Xc() 会把 403 当会话失效强制登出）
app.post('/api/sect/applications/decide', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const appId = Math.floor(asNum(req.body?.id));
    const action = asStr(req.body?.action);
    if (!Number.isInteger(appId) || appId <= 0) return res.status(400).json({ error: '参数非法', code: 'BAD_PARAMS' });
    if (action !== 'approve' && action !== 'reject') return res.status(400).json({ error: '参数非法', code: 'BAD_ACTION' });
    const actor = await sectMemberOf(userId);
    if (!actor || (actor.role !== 'leader' && actor.role !== 'officer')) {
      return res.status(400).json({ error: '\u4ec5\u76df\u4e3b\u6216\u957f\u8001\u53ef\u5ba1\u6279\u7533\u8bf7', code: 'FORBIDDEN' });
    }
    await sectExpireStaleApplications();
    const appRow: any = await dbGet('SELECT id, sect_id, user_id, status, created_at FROM sect_applications WHERE id = ?', [appId]);
    if (!appRow) return res.status(404).json({ error: '\u7533\u8bf7\u4e0d\u5b58\u5728\u6216\u5df2\u64a4\u9500', code: 'NO_SUCH_APP' });
    if (Number(appRow.sect_id) !== actor.sect_id) return res.status(400).json({ error: '\u8be5\u7533\u8bf7\u4e0d\u5c5e\u4e8e\u672c\u76df', code: 'NOT_SAME_SECT' });
    // 占位：pending→approved/rejected 单语句守卫（并发双批/重复审批只一方 changes=1；过期行已被惰性置 expired 同样挡下）
    const newStatus = action === 'approve' ? 'approved' : 'rejected';
    const up = await dbRun(
      "UPDATE sect_applications SET status = ?, handled_at = ?, handled_by = ? WHERE id = ? AND status = 'pending'",
      [newStatus, Date.now(), userId, appId]
    );
    if (!up.changes) return res.status(409).json({ error: '\u8be5\u7533\u8bf7\u5df2\u88ab\u5904\u7406\u6216\u5df2\u8fc7\u671f', code: 'ALREADY_HANDLED' });
    const applicantId = Number(appRow.user_id);
    const sectRow: any = await dbGet('SELECT id, name, level, disbanded_at FROM sects WHERE id = ?', [actor.sect_id]);
    const sectName = String(sectRow?.name || '');
    if (action === 'reject') {
      insertMail(applicantId, '\u5165\u76df\u7533\u8bf7\u672a\u901a\u8fc7',
        `\u5f88\u9057\u61be\uff0c\u300c${sectName}\u300d\u672c\u6b21\u672a\u901a\u8fc7\u4f60\u7684\u5165\u76df\u7533\u8bf7\u3002\u4f60\u4ecd\u53ef\u7533\u8bf7\u5176\u4ed6\u4ed9\u76df\uff0c\u4ed9\u8def\u5e7f\u9614\uff0c\u4f55\u5fc5\u4e00\u5904\u3002`,
        'system', 0).catch((e: any) => console.error('sect decide reject mail error:', e?.message || e));
      return res.json({ ok: true, message: '\u5df2\u62d2\u7edd\u8be5\u7533\u8bf7' });
    }
    // approve：守卫式插入成员行（三门槛一次原子判定；冷却用 ISO 串字典序比较，与 join 端点 Date.parse 同构）
    const nowMs = Date.now();
    const ins = await dbRun(
      `INSERT INTO sect_members (sect_id, user_id, role)
       SELECT ?, ?, 'member'
       WHERE NOT EXISTS (SELECT 1 FROM sect_members WHERE user_id = ?)
         AND NOT EXISTS (SELECT 1 FROM sect_cooldowns WHERE user_id = ? AND cooldown_until > ?)
         AND (SELECT COUNT(*) FROM sect_members WHERE sect_id = ?) < ?`,
      [actor.sect_id, applicantId, applicantId, applicantId, new Date(nowMs).toISOString(), actor.sect_id, SECT_MEMBER_CAP(Number(sectRow?.level) || 1)]
    );
    if (!ins.changes) {
      // 补偿：回滚申请行 pending（满员等场景可恢复重批），再逐项诊断
      await dbRun("UPDATE sect_applications SET status = 'pending', handled_at = NULL, handled_by = NULL WHERE id = ?", [appId]).catch(() => undefined);
      const [inRow, cdRow, cntRow] = await Promise.all([
        dbGet('SELECT 1 AS x FROM sect_members WHERE user_id = ? LIMIT 1', [applicantId]),
        dbGet('SELECT cooldown_until FROM sect_cooldowns WHERE user_id = ? LIMIT 1', [applicantId]),
        dbGet('SELECT COUNT(*) AS c FROM sect_members WHERE sect_id = ?', [actor.sect_id]),
      ]);
      let msg = '\u5165\u76df\u672a\u6210\uff0c\u6761\u4ef6\u6709\u53d8\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5';
      let code = 'CONFLICT';
      let cooldownLeftMs: number | undefined = undefined;
      if (inRow) { msg = '\u5bf9\u65b9\u5df2\u52a0\u5165\u5176\u4ed6\u4ed9\u76df'; code = 'ALREADY_IN_SECT'; }
      else {
        const cdLeftMs = cdRow ? Date.parse(String(cdRow.cooldown_until || '')) - nowMs : NaN;
        if (Number.isFinite(cdLeftMs) && cdLeftMs > 0) { msg = '\u5bf9\u65b9\u9000\u76df\u51b7\u5374\u4e2d\uff0c\u6682\u4e0d\u53ef\u52a0\u5165'; code = 'COOLDOWN_UNTIL'; cooldownLeftMs = cdLeftMs; }
        else if ((Number(cntRow?.c) || 0) >= SECT_MEMBER_CAP(Number(sectRow?.level) || 1)) { msg = '\u8be5\u76df\u4eba\u6570\u5df2\u6ee1'; code = 'SECT_FULL'; }
      }
      const body: any = { error: msg, code };
      if (cooldownLeftMs !== undefined) body.cooldownLeftMs = cooldownLeftMs;
      return res.status(409).json(body);
    }
    insertMail(applicantId, '\u5165\u76df\u7533\u8bf7\u5df2\u901a\u8fc7',
      `\u9053\u53cb\u606d\u559c\uff01\u300c${sectName}\u300d\u7684\u76df\u4e3b/\u957f\u8001\u5df2\u901a\u8fc7\u4f60\u7684\u5165\u76df\u7533\u8bf7\uff0c\u4f60\u5df2\u6b63\u5f0f\u52a0\u5165\u672c\u76df\u3002\n\n\u6bcf\u65e5\u4ff8\u7984\u3001\u76df\u4efb\u52a1\u5956\u52b1\u4e0e\u5b97\u95e8\u4e39\u836f\u8bb0\u5f97\u9886\u53d6\uff0c\u613f\u4e0e\u76df\u4e2d\u9053\u53cb\u5171\u8bc1\u4ed9\u9014\u3002`,
      'system', 0).catch((e: any) => console.error('sect decide approve mail error:', e?.message || e));
    return res.json({ ok: true, message: '\u5df2\u901a\u8fc7\u7533\u8bf7\uff0c\u5bf9\u65b9\u5df2\u52a0\u5165\u672c\u76df', member: { sectId: actor.sect_id, userId: applicantId } });
  } catch (e: any) {
    console.error('sect decide error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 0.8.7 T7 N4：盟设置。notice（≤200 字）=盟主+长老（§3 权限矩阵，放宽自 V27 仅盟主，
// /api/sect/notice 保留为公告子集等价端点）；joinMode（'auto'|'apply'）=仅盟主。
// 两字段至少传一个；各自独立校验权限（长老传 joinMode → 400）
app.post('/api/sect/settings', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const actor = await sectMemberOf(req.user.id);
    if (!actor || (actor.role !== 'leader' && actor.role !== 'officer')) {
      return res.status(400).json({ error: '\u4ec5\u76df\u4e3b\u6216\u957f\u8001\u53ef\u4fee\u6539\u76df\u8bbe\u7f6e', code: 'FORBIDDEN' });
    }
    const sectRow: any = await dbGet('SELECT id, notice, join_mode, disbanded_at FROM sects WHERE id = ?', [actor.sect_id]);
    if (!sectRow || sectRow.disbanded_at) return res.status(400).json({ error: '宗门不存在或已解散' });
    const hasNotice = req.body != null && req.body.notice !== undefined && req.body.notice !== null;
    const hasMode = req.body != null && req.body.joinMode !== undefined && req.body.joinMode !== null;
    if (!hasNotice && !hasMode) return res.status(400).json({ error: '参数非法', code: 'BAD_PARAMS' });
    let notice = String(sectRow.notice || '');
    if (hasNotice) notice = asStr(req.body.notice).trim().slice(0, 200);
    let joinMode = String(sectRow.join_mode || 'auto') === 'apply' ? 'apply' : 'auto';
    if (hasMode) {
      const m = asStr(req.body.joinMode);
      if (m !== 'auto' && m !== 'apply') return res.status(400).json({ error: 'joinMode \u4ec5\u652f\u6301 auto/apply', code: 'BAD_JOIN_MODE' });
      if (actor.role !== 'leader') return res.status(400).json({ error: '\u4ec5\u76df\u4e3b\u53ef\u5207\u6362\u52a0\u5165\u6a21\u5f0f', code: 'FORBIDDEN' });
      joinMode = m;
    }
    await dbRun('UPDATE sects SET notice = ?, join_mode = ? WHERE id = ?', [notice, joinMode, actor.sect_id]);
    res.json({ ok: true, notice, joinMode });
  } catch (e: any) {
    console.error('sect settings error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 全局错误处理（P1-1）：不再向客户端回显 err.stack/内部信息
// 必须放在所有路由之后；生产环境日志仍走 console.error
app.use((err: any, req: any, res: any, next: any) => {
  console.error(`[error] ${req?.method} ${req?.originalUrl}:`, err?.stack || err);
  if (res.headersSent) return next(err);
  // body-parser JSON 解析错误等自带 status（如 400），其余一律 500
  const status = Number(err?.status || err?.statusCode) || 500;
  res.status(status).json({ error: '服务器繁忙' });
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
