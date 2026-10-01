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
          db.exec('ALTER TABLE users ADD COLUMN linuxdo_id TEXT');
        }
      });

      db.run(`
        CREATE TABLE IF NOT EXISTS saves (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL UNIQUE,
          save_data TEXT NOT NULL,
          gm_revision INTEGER DEFAULT 0,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (user_id) REFERENCES users (id)
        )
      `);

      // migration: 添加 gm_revision 字段（已有则跳过）
      db.all("PRAGMA table_info(saves)", (err: any, rows: any[]) => {
        if (!err && rows && !rows.some((r: any) => r.name === 'gm_revision')) {
          db.exec('ALTER TABLE saves ADD COLUMN gm_revision INTEGER DEFAULT 0');
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
      db.exec('ALTER TABLE users ADD COLUMN last_login TEXT');
    }
  });
  // Y5：saves.return_buff_until——回归 buff 截止（ms epoch，NULL=无 buff）
  db.all("PRAGMA table_info(saves)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'return_buff_until')) {
      db.exec('ALTER TABLE saves ADD COLUMN return_buff_until INTEGER');
    }
  });
  // Y3A：saves.offline_claimed_until——离线收益已结算到的时刻（ms epoch，NULL=从未领过）。
  // 防重复领取的唯一防线：守卫式单语句推进（WHERE offline_claimed_until < 新值），并发双领只一方生效
  db.all("PRAGMA table_info(saves)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'offline_claimed_until')) {
      db.exec('ALTER TABLE saves ADD COLUMN offline_claimed_until INTEGER');
    }
  });
  // WUDAO：saves.month_card_until——月卡有效期截止（ms epoch，NULL/过期=无月卡）。
  // 离线收益月卡档（上限 12h + 效率 100%）的唯一判定依据；开通入口（购买流程）未上线，
  // 过渡期由 GM 直接 UPDATE saves SET month_card_until=<ms epoch> 开通（纯判定 hasMonthCard 已单测覆盖）
  db.all("PRAGMA table_info(saves)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'month_card_until')) {
      db.exec('ALTER TABLE saves ADD COLUMN month_card_until INTEGER');
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
      db.exec('ALTER TABLE saves ADD COLUMN title_id INTEGER');
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
      db.exec('ALTER TABLE rebirth_state ADD COLUMN pills INTEGER NOT NULL DEFAULT 0');
    }
  });
  db.all("PRAGMA table_info(rebirth_state)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'pill_stash')) {
      db.exec('ALTER TABLE rebirth_state ADD COLUMN pill_stash INTEGER NOT NULL DEFAULT 0');
    }
  });
  // Y4：预置称号（name UNIQUE + OR IGNORE → 重启幂等）
  db.run(`INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES
    ('渡劫飞升', '{"atkRate":0.05}', 'rebirth')`);
  // Y14：rankings.season——赛季归属标记（北京时区 YYYY-MM；跨月惰性归档上季 TOP3 后全表重标）
  db.all("PRAGMA table_info(rankings)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'season')) {
      db.exec('ALTER TABLE rankings ADD COLUMN season TEXT');
    }
  });
  // fix(rank) 2026-09-17：rankings.name——冗余角色昵称（来源 saves.save_data JSON 的 player.name，
  // users 表无昵称列）。此前排行榜展示 username（登录账号）。读侧回落 username；改名场景容忍旧名，
  // 玩家下次存档上传即刷新。存量行回填见 backfillRankingNames()（幂等：只补 name 为空的行）。
  db.all("PRAGMA table_info(rankings)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'name')) {
      db.exec("ALTER TABLE rankings ADD COLUMN name TEXT NOT NULL DEFAULT ''");
    }
    backfillRankingNames(); // 在 ALTER 入队之后调用（serialize 队列保证列已存在）
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
  // WUDAO（R-GAME3）：悟道六系——每玩家每系至多一行（PK 幂等）；exp=该系累计修为（只增不减，
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
const GM_PASSWORD = process.env.GM_PASSWORD || 'gamer';

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
  db.get('SELECT token FROM gm_sessions WHERE token = ?', [token], (err: any, row: any) => {
    if (err || !row) return res.status(403).json({ error: 'Invalid GM token' });
    next();
  });
};

// 记录 GM 审计日志
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
  const trimmed = username.trim();

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
const validatePassword = (password: string): { valid: boolean; error?: string } => {
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
const STONE_ECHO_RE = /^\/api\/(pet|wudao|farm|alchemy|teahouse|couple|friends|mail|offline|quest|sect|gongfa|bounty|arena|adventure|dungeon|rebirth|guide|mentor|daily|events|lottery|market|chat|achievements|stats|rankings|titles|chronicle|save)\b/;
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
  const { username, password } = req.body;

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

  const trimmedUsername = username.trim();

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
  const { username, password } = req.body;

  if (!username || !password) {
    return res.status(400).json({ error: 'Username and password are required' });
  }

  const trimmedUsername = username.trim();

  db.get('SELECT * FROM users WHERE username = ?', [trimmedUsername], async (err, user: any) => {
    if (err) {
      console.error('Login database error:', err);
      return res.status(500).json({ error: 'Database error' });
    }
    if (!user) {
      return res.status(404).json({ error: 'User not found', code: 'USER_NOT_FOUND' });
    }

    try {
      if (await bcrypt.compare(password, user.password_hash)) {
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
  const { refreshToken } = req.body;
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
    if (!(await bcrypt.compare(oldPassword, user.password_hash))) {
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

function settleSaveEconV2(oldSd: any, newSd: any, prevSavedAtMs: number | null): string[] {
  const clamped: string[] = [];
  try {
    const np: any = newSd && newSd.player;
    if (!np) return clamped;
    const op: any = (oldSd && oldSd.player) || {};
    const realmIdx = Math.max(0, ECON_REALM_ORDER.indexOf(String(np.realm || '')));
    const mult = Math.pow(ECON_CLAMP_REALM_MULT, Math.min(20, realmIdx));
    const mins = prevSavedAtMs ? Math.max(E2_MIN_SAVE_MINS, (Date.now() - prevSavedAtMs) / 60000) : ECON_CLAMP_FIRST_SAVE_MINS;

    // 0) 负值/非有限值归零（灵石/修为）
    for (const f of ['spiritStones', 'exp']) {
      const n = Math.floor(Number(np[f]));
      if (!Number.isFinite(n) || n < 0) { np[f] = 0; clamped.push('E2:' + f + ':neg'); }
    }

    // 1) 计数器差值 + 增速时间合理性钳制（计数器本身不改写，只按钳后值给配额）
    const os = op.statistics || {}, ns = np.statistics || {};
    let dMed = e2Delta(Number(os.meditateCount) || 0, Number(ns.meditateCount) || 0);
    let dAdv = e2Delta(Number(os.adventureCount) || 0, Number(ns.adventureCount) || 0);
    let dKill = e2Delta(Number(os.killCount) || 0, Number(ns.killCount) || 0);
    let dSR = e2Delta(Number(os.secretRealmCount) || 0, Number(ns.secretRealmCount) || 0);
    const cMed = Math.ceil(mins * 300) + 30;   // 自动打坐 200ms/次 → 300 次/分
    const cAdv = Math.ceil(mins * 130) + 30;   // 自动历练 500ms/次 → 120 次/分
    const cSR = Math.ceil(mins * 4) + 6;       // 秘境门每日 3 次 + 战斗内秘境富余
    const cKill = cAdv * 2 + cSR * 5 + 30;
    if (dMed > cMed) { clamped.push('E2:cnt:med' + dMed + '>' + cMed); dMed = cMed; }
    if (dAdv > cAdv) { clamped.push('E2:cnt:adv' + dAdv + '>' + cAdv); dAdv = cAdv; }
    if (dSR > cSR) { clamped.push('E2:cnt:sr' + dSR + '>' + cSR); dSR = cSR; }
    if (dKill > cKill) { clamped.push('E2:cnt:kill' + dKill + '>' + cKill); dKill = cKill; }

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
      Math.floor(E2_SELL_PER_HOUR * mult * (mins / 60)) + 50000);

    const capExp = Math.min(ECON_CLAMP_ABS_MAX,
      Math.floor(ECON_CLAMP_EXP_PER_MIN * mult * mins),          // P0-1 修为总额兜底（合法峰值无实测收紧数据，本批不收紧）
      Math.floor(off.exp + dMed * medEach + dAdv * advEach + dKill * killEach + dSR * srEach
        + Math.min(dTowerExp, Math.floor(E2_TOWER_EXP_PER_MIN * mult * mins) + E2_TOWER_EXP_LUMP)
        + Math.min(dExpedExp, Math.floor(E2_EXPED_EXP_PER_MIN * mult * mins) + E2_EXPED_EXP_LUMP)
        + Math.max(100, lvlMaxExp * 0.05)));                     // 尾项=用药/杂项修为兜底（收益÷10 同步收紧）
    const ylScale = (realmIdx <= 0 ? 4 / 3 : 2 * realmIdx + 1) / 3; // YL_REALM_REWARD_SCALE_V26L realmScale (realmIdx=1 => 1x, 6 => 13/3)
    const capStone = Math.min(ECON_CLAMP_ABS_MAX,
      Math.floor((Math.floor(E2_STONE_BURST_PER_HOUR * mult * (mins / 60)) + E2_STONE_BURST_BASE) * ylScale), // ③ 灵石总额兜底
      Math.floor(off.stones + dMed * ((realmIdx * 2 + 4) * 5) * ylScale + dAdv * E2_ADV_STONE_EACH * ylScale
        + dKill * E2_KILL_STONE_EACH * ylScale + dSR * E2_SR_STONE_EACH * ylScale + sellAllow * ylScale
        + E2_LUMP_STONE_ALLOWANCE * ylScale + 10000));

    // 4) 超限截断（只拦正增量；消费/负增量不拦）
    const caps: Array<[string, number]> = [['spiritStones', capStone], ['exp', capExp]];
    for (const [f, cap] of caps) {
      const ov = Math.floor(Number(op[f]) || 0);
      const nv = Math.floor(Number(np[f]) || 0);
      if (!Number.isFinite(nv) || nv < 0) continue; // 已在 0) 归零
      const delta = nv - ov;
      if (delta > cap) {
        np[f] = ov + cap;
        clamped.push('E2:' + f + ':' + delta + '>' + cap
          + '|off' + (f === 'exp' ? off.exp : off.stones)
          + ',m' + dMed + ',a' + dAdv + ',k' + dKill + ',r' + dSR + ',s' + sellAllow
          + ',tw' + dTowerExp + ',ex' + dExpedExp);
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

// S4 v26c 保险快照（可选独立件）：对写档前旧档做节流快照（每用户 ≥10min 一条、每号最多留 50 条），
// 用于误覆盖/防倒滚误伤救援；fire-and-forget + 全程自吞异常，绝不影响保存主路径
function snapshotOldSave(userId: number, oldSaveData: string, gmRevision: number) {
  try {
    db.get('SELECT created_at FROM save_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT 1', [userId], (err: any, row: any) => {
      if (err) return;
      if (row && row.created_at) {
        const t = Date.parse(String(row.created_at).replace(' ', 'T') + 'Z');
        if (Number.isFinite(t) && Date.now() - t < 10 * 60 * 1000) return; // 节流：距上一条 <10min 不再快照
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

  const saveDataString = JSON.stringify(saveData);
  const saveStreak = recordEconSaveUpload(req.user.id); // SEC 规则③：上传频率滚动窗（进程内存；仅玩家上传计入，失败请求也计=尝试口径）

  // 读改写全程持锁，防止与 GM patch（updatePlayerSave）并发互相覆盖（P1-2）
  withSaveLock(req.user.id, (): Promise<void> => new Promise((resolve) => {
    // Y2：读旧存档做差值基线（服务端结算埋点）。行不存在→全零起算；JSON 坏→null 跳过本次计数（防历史计数一次性全额入账）
    db.get('SELECT save_data, gm_revision, updated_at FROM saves WHERE user_id = ?', [req.user.id], (err, row: any) => {
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
        res.status(409).json({ error: 'stale_save', gm_revision: curRev, updated_at: row.updated_at ?? null, save: curSave });
        return resolve();
      }
      // S4 保险快照：写前对旧档节流快照（fire-and-forget，见 snapshotOldSave）
      if (row) snapshotOldSave(req.user.id, row.save_data, curRev);

      // P0-2：二阶段服务端权威结算（离线重算封顶+计数器逐类配额+总额兜底）。YL_V26L：死代码 clampSaveEcon 已删除
      let clampedFields: string[] = settleSaveEconV2(row && !econSkip ? (() => { try { return JSON.parse(row.save_data); } catch { return null; } })() : null, saveData, row && row.updated_at ? (() => { const t = Date.parse(String(row.updated_at).replace(' ', 'T') + 'Z'); return Number.isFinite(t) ? t : null; })() : null);
      const saveDataStringClamped = clampedFields.length ? JSON.stringify(saveData) : saveDataString;
      if (row) {
        db.run(
          'UPDATE saves SET save_data = ?, gm_revision = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', // S2 v26c：玩家写递增修订号
          [saveDataStringClamped, curRev + 1, req.user.id],
          async (updateErr) => {
            if (updateErr) {
              res.status(500).json({ error: 'Error updating save' });
              return resolve();
            }
            const rankingSynced = await upsertRanking(req.user.id, req.user.username, saveData);
            maybeGrantAutoTitles(req.user.id, achievementsLen(saveData)); // Y6 惰性授予（幂等，内部自吞异常）
            if (prevCounters) tickDailyQuests(req.user.id, computeQuestDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('daily tick error:', (e as any)?.message || e)); // Y2 埋点：语句级原子，无需等待
            if (prevCounters) tickSectTasks(req.user.id, computeQuestDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('sect tick error:', (e as any)?.message || e)); // V27 宗门集体任务：同源差值汇入全宗进度（无宗门首查早退），fire-and-forget
            if (prevCounters) tickStatsDaily(req.user.id, computeStatsDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('stats tick error:', (e as any)?.message || e)); // Y15 埋点：同源差值，fire-and-forget
            if (prevCounters) tickMentorTax(req.user.id, computeStatsDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('mentor tax error:', (e as any)?.message || e)); // Y6B 师徒抽成：师傅得在门徒弟收益 5%，fire-and-forget
            if (prevCounters) tickDungeonTracker(req.user.id, computeDungeonDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('dungeon tick error:', (e as any)?.message || e)); // DG 埋点：秘境观测差值，fire-and-forget
            if (prevCounters) tickWudaoIdle(req.user.id, computeQuestDeltas(prevCounters, extractCounters(saveData)).meditate).catch((e: any) => console.error('wudao idle error:', (e as any)?.message || e)); // WUDAO 埋点：打坐时长差值→随机系心得，fire-and-forget
            if (!econSkip) writeEconomyMirror(req.user.id, prevEcon ?? EMPTY_ECON_SNAPSHOT, extractEconSnapshot(saveData), saveStreak); // E1 镜像记账（旁路 fire-and-forget，不 await 不影响响应）；SEC 规则③传上传频次
            if (clampedFields.length) { dbRun("INSERT INTO economy_ledger (player_id, kind, anomaly_json) VALUES (?, 'clamp', ?)", [req.user.id, clampedFields.join('|').slice(0, 500)]).catch((e: any) => console.error('clamp ledger error:', e?.message || e)); }
            res.json({ message: 'Save updated successfully', rankingSynced, clamped: clampedFields, settledExp: Math.floor(Number(saveData && saveData.player && saveData.player.exp) || 0), gm_revision: curRev + 1 }); // S2 v26c：回传新修订号供客户端回填 base
            resolve();
          }
        );
      } else {
        db.run(
          'INSERT INTO saves (user_id, save_data, gm_revision) VALUES (?, ?, 1)', // S2 v26c：首存修订号=1（兼容 C6 首存，无头放行）
          [req.user.id, saveDataStringClamped], // QA-Y fix(BUG#1)：参数反序已修；此处用钳后串：原 [saveDataString, req.user.id] 参数反序——新玩家首存 user_id 写成整包 JSON、save_data 写成数字，GET /save 404、邮件 claim/buff/称号落空，且每次上传再插一行垃圾（UNIQUE 不命中）
          async (insertErr) => {
            if (insertErr) {
              res.status(500).json({ error: 'Error creating save' });
              return resolve();
            }
            const rankingSynced = await upsertRanking(req.user.id, req.user.username, saveData);
            maybeGrantAutoTitles(req.user.id, achievementsLen(saveData)); // Y6 惰性授予（幂等，内部自吞异常）
            tickDailyQuests(req.user.id, computeQuestDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('daily tick error:', (e as any)?.message || e)); // Y2 埋点（prev=全零）
            if (prevCounters) tickSectTasks(req.user.id, computeQuestDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('sect tick error:', (e as any)?.message || e)); // V27 宗门集体任务（首存=全零基线），fire-and-forget
            if (prevCounters) tickStatsDaily(req.user.id, computeStatsDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('stats tick error:', (e as any)?.message || e)); // Y15 埋点（首存=全零基线）
            if (prevCounters) tickMentorTax(req.user.id, computeStatsDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('mentor tax error:', (e as any)?.message || e)); // Y6B 师徒抽成（首存=全零基线，无差值不抽），fire-and-forget
            if (prevCounters) tickDungeonTracker(req.user.id, computeDungeonDeltas(prevCounters, extractCounters(saveData))).catch((e: any) => console.error('dungeon tick error:', (e as any)?.message || e)); // DG 埋点（首存=全零基线，老号历史秘境量不回填）
            if (prevCounters) tickWudaoIdle(req.user.id, computeQuestDeltas(prevCounters, extractCounters(saveData)).meditate).catch((e: any) => console.error('wudao idle error:', (e as any)?.message || e)); // WUDAO 埋点（首存=全零基线；在线时长近似口径与"打坐"任务同源）
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
  db.run('INSERT INTO gm_sessions (token) VALUES (?)', [token], (err: any) => {
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
    res.json({ message: 'Granted' });
  });
});

// 封禁 / 解封账号（通过标记 GM 字段实现：在 users 表加 banned 列）
db.serialize(() => {
  db.all("PRAGMA table_info(users)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'banned')) {
      db.exec('ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0');
    }
  });
});
app.post('/api/gm/players/:id/ban', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  const banned = req.body?.banned ? 1 : 0;
  const reason = String(req.body?.reason || '').slice(0, 200);
  db.run('UPDATE users SET banned = ? WHERE id = ?', [banned, userId], (err: any) => {
    if (err) return res.status(500).json({ error: 'Update failed' });
    logGmAction(banned ? 'ban' : 'unban', `user:${userId}`, { reason });
    res.json({ message: banned ? 'Banned' : 'Unbanned', banned: !!banned, userId });
  });
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

// 游戏字典端点 (成就/称号/洞府/灵宠/功法/物品/抽奖池/宗门/天赋/草药)
let gameDicts: any = null;
function loadGameDicts() {
  if (gameDicts) return gameDicts;
  try {
    const fs = require('fs');
    const path = require('path');
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
  if (quantity != null && Number(quantity) >= 1) { sets.push('quantity = ?'); params.push(Math.floor(Number(quantity))); }
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
  const { messages, temperature = 0.8, max_tokens = 500 } = req.body;
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
  const { itemName, itemType, description, rarity, price, quantity, effect, isEquippable, equipmentSlot, itemSourceJson } = req.body;

  // P1-6 存储型 XSS 防护：price/quantity 强制数字（旧校验 `!price || price <= 0` 对非数字字符串
  // 恒为 false 直接原样入库，gm-pro 交易行属性位未转义渲染即打 GM 管理员）；文本字段强制 String+截断
  const priceNum = Math.floor(Number(price));
  if (!itemName || typeof itemName !== 'string' || !itemName.trim() || !Number.isFinite(priceNum) || priceNum <= 0) {
    return res.status(400).json({ error: '物品名称和有效价格是必填项' });
  }
  const safeItemName = itemName.trim().slice(0, 100);
  const safeItemType = String(itemType || '材料').slice(0, 50);
  const safeDescription = String(description || '').slice(0, 500);
  const safeRarity = String(rarity || '普通').slice(0, 50);
  const safeSlot = equipmentSlot ? String(equipmentSlot).slice(0, 50) : null;
  const listingQuantity = Math.max(1, Math.floor(Number(quantity)) || 1);

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
  const { listingId } = req.body;
  if (!listingId) return res.status(400).json({ error: '缺少 listingId' });

  // V27：容忍重复前缀（market-market-7）——上游 1ec1b63 同款修复；旧写法只剥一层
  const cleanId = (listingId || '').toString().replace(/^(?:market-)+/, '');
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
  const { listingId } = req.body;
  if (!listingId) return res.status(400).json({ error: '缺少 listingId' });

  // V27：容忍重复前缀（market-market-7）——上游 1ec1b63 同款修复；旧写法只剥一层
  const cleanId = (listingId || '').toString().replace(/^(?:market-)+/, '');
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
  const { listingId } = req.body;
  if (!listingId) return res.status(400).json({ error: '缺少 listingId' });

  // V27：容忍重复前缀（market-market-7）——上游 1ec1b63 同款修复；旧写法只剥一层
  const cleanId = (listingId || '').toString().replace(/^(?:market-)+/, '');
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
const QUEST_DEFS = [
  { key: 'meditate', name: '打坐 30 分钟', target: 30 * 60 * 1000, points: 25 },
  { key: 'kill', name: '战斗胜利 5 场', target: 5, points: 25 },
  { key: 'adventure', name: '历练 3 次', target: 3, points: 25 },
  { key: 'spend', name: '消费 10000 灵石', target: 10000, points: 25 },
];
const CHEST_TIERS = [25, 50, 75, 100]; // 活跃度四档宝箱
const CHEST_REWARDS: Record<number, number> = { 25: 2500, 50: 7500, 75: 15000, 100: 30000 };
function chestKey(tier: number): string { return 'chest_' + tier; }
// 每日重置基准：北京时区 YYYY-MM-DD（UTC+8，北京 0 点跨日）
function bjDate(ms: number): string {
  return new Date(ms + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);
}
interface StatCounters { killCount: number; adventureCount: number; playTimeMs: number; spiritStones: number; exp: number; secretRealmCount: number; }
function extractCounters(saveData: any): StatCounters {
  const p = saveData?.player ?? {};
  return {
    killCount: Number(p.statistics?.killCount) || 0,
    adventureCount: Number(p.statistics?.adventureCount) || 0,
    playTimeMs: Number(p.playTime) || 0,
    spiritStones: Number(p.spiritStones) || 0,
    exp: Number(p.exp) || 0, // Y15：修为进统计差值（Y2 任务不消费此字段，向后兼容）
    secretRealmCount: Number(p.statistics?.secretRealmCount) || 0, // DG：秘境经典门计数（R5 锚点核实）
  };
}
function zeroCounters(): StatCounters { return { killCount: 0, adventureCount: 0, playTimeMs: 0, spiritStones: 0, exp: 0, secretRealmCount: 0 }; }
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
const DUNGEON_ENTRY_CD_MS = 30_000;   // 两次进入最小间隔（CD 内重复上报视为同一次，拒绝不计数）
const DUNGEON_ANOMALY_THRESHOLD = 10; // 单日 count 或 observed 超此值 → anomaly=1（GM /api/dungeon/anomalies 可查）
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
  row: { count?: unknown; observed?: unknown; adventure?: unknown; last_ts?: unknown; anomaly?: unknown } | null | undefined,
  nowMs: number,
  cap: number = DUNGEON_DAILY_CAP,
  cdMs: number = DUNGEON_ENTRY_CD_MS
): {
  date: string; count: number; cap: number; remaining: number;
  observed: number; adventure: number; anomaly: boolean;
  lastTs: number | null; cdLeftMs: number; canEnter: boolean;
} {
  const count = Math.max(0, Math.floor(Number(row?.count) || 0));
  const observed = Math.max(0, Math.floor(Number(row?.observed) || 0));
  const adventure = Math.max(0, Math.floor(Number(row?.adventure) || 0));
  const lastTs = row?.last_ts != null && Number.isFinite(Number(row.last_ts)) ? Number(row.last_ts) : null;
  const cdLeftMs = lastTs != null ? Math.max(0, cdMs - (nowMs - lastTs)) : 0;
  return {
    date: bjDate(nowMs),
    count, cap,
    remaining: Math.max(0, cap - count),
    observed, adventure,
    anomaly: dungeonAnomaly(count, observed) || Number(row?.anomaly) === 1,
    lastTs, cdLeftMs,
    canEnter: count < cap && cdLeftMs === 0,
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
  const p = Math.floor(Number(raw) || 1);
  return Math.min(maxPage, Math.max(1, p)); // 非法/越界一律钳回有效页
}
function clampChronicleText(t: unknown): string { return String(t ?? '').slice(0, CHRONICLE_MAX_TEXT); }
// ── Y17 炼丹炉：配方/炉位/成熟判定/收益（数值为本次定档，常量集中可调）──
const ALCHEMY_SLOTS = 3;        // 每玩家炉位数（slot 0..2）
const ALCHEMY_YIELD_RATE = 1.5; // 出炉灵石返还率（丹药实体在客户端权威存档内服务端无法入包，按名目折算灵石随邮件发放）
const ALCHEMY_RECIPES: Record<string, { name: string; minutes: number; cost: number }> = {
  juqi:     { name: '聚气丹', minutes: 30,  cost: 5000 },
  ningyuan: { name: '凝元丹', minutes: 120, cost: 20000 },
  pojing:   { name: '破境丹', minutes: 480, cost: 80000 },
};
function alchemyRecipe(key: unknown): { name: string; minutes: number; cost: number } | null {
  return key != null && Object.prototype.hasOwnProperty.call(ALCHEMY_RECIPES, String(key)) ? ALCHEMY_RECIPES[String(key)] : null;
}
function alchemyRecipeByName(name: unknown): { name: string; minutes: number; cost: number } | null {
  const n = String(name ?? '');
  for (const k of Object.keys(ALCHEMY_RECIPES)) if (ALCHEMY_RECIPES[k].name === n) return ALCHEMY_RECIPES[k];
  return null;
}
function alchemySlotOk(raw: unknown): boolean {
  const s = Number(raw);
  return Number.isInteger(s) && s >= 0 && s < ALCHEMY_SLOTS;
}
function alchemyMatureAt(startMs: number, minutes: number): number {
  return startMs + Math.max(1, Math.floor(Number(minutes) || 1)) * 60 * 1000;
}
// 成熟判定（纯）：恰好到点算成熟（>=），提前收获拒绝
function alchemyIsReady(matureAt: number, nowMs: number): boolean { return nowMs >= matureAt; }
function alchemyYieldStones(cost: number): number { return Math.floor(cost * ALCHEMY_YIELD_RATE); }

// ── Y19 成就系统：五类各 4 项共 20 项，达成状态从 stats_daily/daily_quests/saves 惰性推导（零新增埋点）；
// 领取记录 achievement_claimed 主键幂等防重复领奖；奖励=灵石阶梯 200/500/1000/2000（本次定档，常量集中可调）──
const ACH_REWARD_TIERS = [200, 500, 1000, 2000]; // 每类四档奖励阶梯（灵石）
// 境界序（ycore 内自持镜像，与 REALM_ORDER_FOR_RANKING 同源同序，勿外引）
const ACH_REALM_ORDER: string[] = Object.keys(TRIB_REALM_BASES);
type AchMetric = 'minutes' | 'kills' | 'silver' | 'quests' | 'realmIndex';
const ACH_GROUPS: Array<{ key: string; name: string; metric: AchMetric }> = [
  { key: 'cultivate', name: '修行', metric: 'minutes' },
  { key: 'battle', name: '战斗', metric: 'kills' },
  { key: 'wealth', name: '财富', metric: 'silver' },
  { key: 'quest', name: '任务', metric: 'quests' },
  { key: 'realm', name: '境界', metric: 'realmIndex' },
];
interface AchTotals { minutes: number; kills: number; silver: number; quests: number; realmIndex: number; }
interface AchDef { id: string; group: string; name: string; desc: string; target: number; reward: number; }
const ACH_DEFS: AchDef[] = [
  // 修行：累计 stats_daily.minutes（在线分钟=打坐时长的服务端可见代理）
  { id: 'cultivate_60', group: 'cultivate', name: '初窥门径', desc: '累计在线 60 分钟', target: 60, reward: 500 },
  { id: 'cultivate_300', group: 'cultivate', name: '潜心修行', desc: '累计在线 300 分钟', target: 300, reward: 1500 },
  { id: 'cultivate_1200', group: 'cultivate', name: '闭关苦修', desc: '累计在线 20 小时', target: 1200, reward: 4000 },
  { id: 'cultivate_6000', group: 'cultivate', name: '枯禅入定', desc: '累计在线 100 小时', target: 6000, reward: 10000 },
  // 战斗：累计 stats_daily.kills（战斗胜利场次）
  { id: 'battle_10', group: 'battle', name: '初试锋芒', desc: '累计战斗胜利 10 场', target: 10, reward: 500 },
  { id: 'battle_50', group: 'battle', name: '身经百战', desc: '累计战斗胜利 50 场', target: 50, reward: 1500 },
  { id: 'battle_200', group: 'battle', name: '杀伐果断', desc: '累计战斗胜利 200 场', target: 200, reward: 4000 },
  { id: 'battle_1000', group: 'battle', name: '战无不胜', desc: '累计战斗胜利 1000 场', target: 1000, reward: 10000 },
  // 财富：累计 stats_daily.silver_gain（灵石净获取，含邮件/宝箱/GM 入账）
  { id: 'wealth_1e4', group: 'wealth', name: '小有积蓄', desc: '累计获取灵石 1 万', target: 10000, reward: 500 },
  { id: 'wealth_1e5', group: 'wealth', name: '家财万贯', desc: '累计获取灵石 10 万', target: 100000, reward: 1500 },
  { id: 'wealth_1e6', group: 'wealth', name: '富可敌国', desc: '累计获取灵石 100 万', target: 1000000, reward: 4000 },
  { id: 'wealth_1e7', group: 'wealth', name: '仙门首富', desc: '累计获取灵石 1000 万', target: 10000000, reward: 10000 },
  // 任务：累计 daily_quests 完成（done=1 的任务行，不含宝箱领取占位行）
  { id: 'quest_1', group: 'quest', name: '小试牛刀', desc: '累计完成每日任务 1 个', target: 1, reward: 500 },
  { id: 'quest_10', group: 'quest', name: '勤修不辍', desc: '累计完成每日任务 10 个', target: 10, reward: 1500 },
  { id: 'quest_50', group: 'quest', name: '任务达人', desc: '累计完成每日任务 50 个', target: 50, reward: 4000 },
  { id: 'quest_200', group: 'quest', name: '仙途楷模', desc: '累计完成每日任务 200 个', target: 200, reward: 10000 },
  // 境界：saves 存档 realm 达标（target=境界序；任务书"大乘"不存在于本游戏境界表 → 以最高境"长生境"压轴）
  { id: 'realm_jindan', group: 'realm', name: '金丹初成', desc: '境界达到金丹期', target: ACH_REALM_ORDER.indexOf('金丹期'), reward: 500 },
  { id: 'realm_yuanying', group: 'realm', name: '元婴出窍', desc: '境界达到元婴期', target: ACH_REALM_ORDER.indexOf('元婴期'), reward: 1500 },
  { id: 'realm_huashen', group: 'realm', name: '化神通玄', desc: '境界达到化神期', target: ACH_REALM_ORDER.indexOf('化神期'), reward: 4000 },
  { id: 'realm_changsheng', group: 'realm', name: '长生久视', desc: '境界达到长生境', target: ACH_REALM_ORDER.indexOf('长生境'), reward: 10000 },
];
// 全量钳制（纯）：负值/NaN/undefined/±Infinity → 0，小数 floor（DB 空表 SUM=NULL 亦归 0，边界 0 值安全）
function achTotalsFrom(t: { minutes?: unknown; kills?: unknown; silver?: unknown; quests?: unknown; realmIndex?: unknown }): AchTotals {
  const n = (v: unknown) => { const x = Number(v); return Number.isFinite(x) ? Math.max(0, Math.floor(x)) : 0; };
  return { minutes: n(t.minutes), kills: n(t.kills), silver: n(t.silver), quests: n(t.quests), realmIndex: n(t.realmIndex) };
}
// 视图组装（纯）：20 项全量 + 分组计数 + 可领取清单（done && !claimed）
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
  const id = String(requestedId);
  return view.claimableIds.includes(id) ? [id] : [];
}
// ── Y3A 奇遇日记：每日 3 次随机奇遇（白 60/蓝 25/紫 12/金 3%），一抽一行入 adventures ──
const ADVENTURE_DAILY_MAX = 3; // 每日抽取次数上限
// 奇遇品阶：weight=权重（合计 100），stones=固定灵石，expRate=按当层修为槽百分比的修为收益（钳槽内不溢出）。
// 数值为本次定档，常量集中可调
interface AdventureTierDef { key: string; name: string; weight: number; stones: number; expRate: number; }
const ADVENTURE_TIERS: AdventureTierDef[] = [
  { key: 'white', name: '白', weight: 80, stones: 100, expRate: 0.002 },
  { key: 'blue', name: '蓝', weight: 12.5, stones: 300, expRate: 0.004 },
  { key: 'purple', name: '紫', weight: 6, stones: 800, expRate: 0.008 },
  { key: 'gold', name: '金', weight: 1.5, stones: 2000, expRate: 0.015 },
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
  // 金 · 天缘
  { key: 'g_immortal', tier: 'gold', text: '云海之巅遇仙人对弈，一子落枰，天机灌顶——此等缘法，万中无一！' },
  { key: 'g_dragon', tier: 'gold', text: '蛟龙虚影自深潭腾空而过，一片逆鳞坠入你手，灵气如江河灌体！' },
  { key: 'g_scroll', tier: 'gold', text: '残破古卷自九天飘落，仙文入眼即化道音——福缘深厚，天授之才！' },
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
function adventureExpGain(tierKey: string, maxExp: number, currentExp: number): number {
  const t = adventureTierByKey(tierKey);
  if (!t) return 0;
  const slot = Math.max(0, Math.floor(Number(maxExp) || 0));
  const cur = Math.max(0, Math.floor(Number(currentExp) || 0));
  const raw = Math.floor(slot * t.expRate);
  return Math.max(0, Math.min(raw, slot - cur));
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
  const n = Number(raw);
  if (!Number.isFinite(n) || !Number.isInteger(n)) return null;
  if (n < BOUNTY_MIN_REWARD || n > BOUNTY_MAX_REWARD) return null;
  return n;
}
function bountyTitleClamp(t: unknown): string { return String(t ?? '').trim().slice(0, BOUNTY_TITLE_MAX); }
function bountyDescClamp(t: unknown): string { return String(t ?? '').trim().slice(0, BOUNTY_DESC_MAX); }
// [/ycore]

// [farmcore] Y19 洞府灵田纯逻辑核心（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
// 数值为本次定档，常量集中可调；作物=种子灵石/生长时长/产量（灵石+修为），提前收获收益减半
const FARM_SLOTS = 3; // 每玩家田位数（slot 1..3；slot 1 免费隐式解锁，2/3 灵石开垦永久）
const FARM_CROPS: Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number }> = {
  lingcao:     { name: '灵草',   seed: 1000, minutes: 240,  stones: 800,   exp: 500 },
  lingzhi:     { name: '灵芝',   seed: 5000, minutes: 720,  stones: 5000,  exp: 3000 },
  qianniancan: { name: '千年参', seed: 20000, minutes: 1440, stones: 25000, exp: 15000 },
};
const FARM_UNLOCK_COST: Record<number, number> = { 2: 20000, 3: 80000 }; // 开垦价（slot 1 免费，不在表内；物价×10）
function farmCrop(key: unknown): { name: string; seed: number; minutes: number; stones: number; exp: number } | null {
  return key != null && Object.prototype.hasOwnProperty.call(FARM_CROPS, String(key)) ? FARM_CROPS[String(key)] : null;
}
// 田位（纯）：1..FARM_SLOTS 整数合法（Number 宽容数字字符串，与 alchemySlotOk 同口径）
function farmSlotOk(raw: unknown): boolean {
  const s = Number(raw);
  return Number.isInteger(s) && s >= 1 && s <= FARM_SLOTS;
}
function farmMatureAt(startMs: number, minutes: number): number {
  return startMs + Math.max(1, Math.floor(Number(minutes) || 1)) * 60 * 1000;
}
// 成熟判定（纯）：恰好到点算成熟（>=），提前收获不减产为 0 而是减半（玩家自选止损）
function farmIsReady(matureAt: number, nowMs: number): boolean { return nowMs >= matureAt; }
// 收益（纯）：到期=全额；提前收获=减半（两项独立 floor）
function farmYield(crop: { stones: number; exp: number }, early: boolean): { stones: number; exp: number } {
  const s = Math.max(0, Math.floor(Number(crop.stones) || 0));
  const e = Math.max(0, Math.floor(Number(crop.exp) || 0));
  return early ? { stones: Math.floor(s / 2), exp: Math.floor(e / 2) } : { stones: s, exp: e };
}
// [/farmcore]

// [petcore] Y18 妖灵宠物纯逻辑核心（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
// 数值为本次定档，常量集中可调；hunger=喂食度（只增不减），level=floor(hunger/100)，出战加成保守落点见 PET_BATTLE_*
const PET_FEED_COST = 5000;       // 喂养一次消耗灵石（物价×10）
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
function clampPetDetail(t: unknown): string { return String(t ?? '').slice(0, 60); }
// [/petcore]

// [wudaocore] R-GAME3 悟道系统纯逻辑核心（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
// 六系悟道（剑/丹/体/法/阵/御），每系独立 1..10 级，exp 只增不减；数值为本次定档，常量集中可调。
// 加成落点：客户端权威架构下攻防血暴击的实际结算在客户端（与称号 attr_json/回归 buff 同一架构边界，
// 服务端出权威数值+伴生页展示，客户端接管后即插即用）。
const WUDAO_DAOS: Record<string, { name: string; stat: string; statName: string; basePct: number; stepPct: number }> = {
  sword: { name: '剑道', stat: 'attack', statName: '攻击', basePct: 2.0, stepPct: 0.5 },
  body:  { name: '体道', stat: 'defense', statName: '防御', basePct: 2.0, stepPct: 0.5 },
  pill:  { name: '丹道', stat: 'maxHp', statName: '气血', basePct: 2.0, stepPct: 0.5 },
  spell: { name: '法道', stat: 'crit', statName: '暴击', basePct: 1.0, stepPct: 0.25 },
  array: { name: '阵道', stat: 'attack', statName: '攻击', basePct: 1.0, stepPct: 0.25 },
  tame:  { name: '御道', stat: 'maxHp', statName: '气血', basePct: 1.0, stepPct: 0.25 },
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
// 挂机心得：每分钟 roll 一次，8% 命中=1 条心得（=期望 4.8 条/小时），随机落入六系之一；
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
  return key != null && Object.prototype.hasOwnProperty.call(WUDAO_DAOS, String(key));
}
const WUDAO_LOG_KEEP = 50; // 每玩家悟道日志保留条数（写入后裁剪，防表膨胀）
// [/wudaocore]

// [gongfacore] Y20 功法系统纯逻辑核心（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
// 六部功法（焚天诀/御剑术/不灭体/大衍诀/周天阵/御灵术）各 1..10 级，level 0=未入门；
// 数值为本次定档（任务书口径），常量集中可调。属性被动落点：客户端权威架构下攻/防/血/暴击/闪避/命中
// 的实际结算在客户端混淆码内（与称号 attr_json/悟道加成同一架构边界），服务端出权威数值+伴生页展示，
// 客户端接管后即插即用，不入实际战斗结算。
const GONGFA_MAX_LEVEL = 10;
const GONGFA_STEP_COST = 1000;  // 升到 L 级耗灵石 1000×L（L1=1000 … L10=10000；物价×10）
const GONGFA_BONUS_STEP_PCT = 2; // 每级对应属性 +2%（任务书"+2%×level"口径，Lv10=+20%）
const GONGFA_LIST: Record<string, { name: string; stat: string; statName: string }> = {
  fentian:  { name: '焚天诀', stat: 'attack',  statName: '攻击' },
  yujian:   { name: '御剑术', stat: 'crit',    statName: '暴击' },
  bumie:    { name: '不灭体', stat: 'defense', statName: '防御' },
  dayan:    { name: '大衍诀', stat: 'hit',     statName: '命中' },
  zhoutian: { name: '周天阵', stat: 'maxHp',   statName: '气血' },
  yuling:   { name: '御灵术', stat: 'dodge',   statName: '闪避' },
};
function gongfaOk(key: unknown): boolean {
  return key != null && Object.prototype.hasOwnProperty.call(GONGFA_LIST, String(key));
}
// 升到 L 级本级消耗（纯）：100×L；非法输入钳 1..10
function gongfaCostToReach(level: unknown): number {
  const l = Math.min(GONGFA_MAX_LEVEL, Math.max(1, Math.floor(Number(level) || 1)));
  return GONGFA_STEP_COST * l;
}
// 升到 L 级累计投入 exp（纯）：Σ 100×i = 50×L×(L+1)（L1=100 … L10=5500）
function gongfaExpToReach(level: unknown): number {
  const l = Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(level) || 0)));
  // v28.1: exp curve MUST scale with GONGFA_STEP_COST. Was hard-coded 50*L*(L+1) (= 100/level) while cost is 1000/level -> 10x mismatch,
  return (GONGFA_STEP_COST / 2) * l * (l + 1);
}
// 由累计 exp 推导等级（纯）：0=未入门；恰达阈值升级（>=）；非法/负数安全
function gongfaLevelFromExp(exp: unknown): number {
  const e = Math.max(0, Math.floor(Number(exp) || 0));
  let lv = 0;
  while (lv < GONGFA_MAX_LEVEL && e >= gongfaExpToReach(lv + 1)) lv++;
  return lv;
}
const GONGFA_MAX_EXP_TOTAL = gongfaExpToReach(GONGFA_MAX_LEVEL); // 55000：满级累计投入
// 属性被动（纯）：+2%×level（0..20%，非法输入按 0 计）
function gongfaBonusPct(level: unknown): number {
  const lv = Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(level) || 0)));
  return GONGFA_BONUS_STEP_PCT * lv;
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
// 无增量的存档上传不落行不刷 last_ts（last_ts 只反映秘境/历练活动，不是存档活跃）；
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
       observed = observed + excluded.observed,
       adventure = adventure + excluded.adventure,
       last_ts = excluded.last_ts,
       anomaly = CASE WHEN observed + excluded.observed > ? OR count > ? THEN 1 ELSE anomaly END`,
    [userId, bjDate(nowMs), realm, adventure, nowMs, realm > DUNGEON_ANOMALY_THRESHOLD ? 1 : 0, DUNGEON_ANOMALY_THRESHOLD, DUNGEON_ANOMALY_THRESHOLD]
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
// 每分钟 roll 8% 得 1 条心得（+10 exp），随机落入六系之一。fire-and-forget 自吞异常，绝不阻塞存档路径；
// 按系聚合后逐系一次 upsert（单次上传至多 120 条心得 → 至多 6 条语句，fetchAll/写入均有界）
async function tickWudaoIdle(userId: number, playTimeDeltaMs: number): Promise<void> {
  try {
    const hits = wudaoIdleInsights(Math.floor((Number(playTimeDeltaMs) || 0) / 60000), Math.random);
    if (hits <= 0) return;
    const perDao: Record<string, number> = {};
    for (let i = 0; i < hits; i++) {
      const k = wudaoPickDao(Math.random);
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
  const mailId = parseInt(id);
  if (!mailId) return res.status(400).json({ error: '需要 id 或 all:true' });
  db.run('UPDATE mail SET read_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ? AND read_at IS NULL', [mailId, req.user.id], (err: any) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    res.json({ ok: true });
  });
});

// POST /api/mail/claim — 领取灵石附件（补偿式事务 + saveLock 互斥，见 mailClaimCore）
app.post('/api/mail/claim', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `mail:claim:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const mailId = parseInt(req.body?.id);
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
  const safeTitle = String(title || '').trim().slice(0, 100);
  const safeContent = String(content || '').slice(0, 2000);
  const safeSender = String(sender || 'system').slice(0, 32);
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

  if (userId) return sendTo(parseInt(userId));
  if (username) {
    db.get('SELECT id FROM users WHERE username = ?', [String(username).slice(0, 32)], (err: any, row: any) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      if (!row) return res.status(404).json({ error: '用户不存在' });
      sendTo(row.id);
    });
    return;
  }
  res.status(400).json({ error: '需要 userId / username / all:true' });
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
  const tid = parseInt(raw);
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
  const tid = parseInt(titleId);
  if (!tid) return res.status(400).json({ error: '需要 titleId' });
  try {
    const t = await dbGet('SELECT id, name FROM titles WHERE id = ?', [tid]);
    if (!t) return res.status(404).json({ error: '称号不存在' });
    let uid: number | null = null;
    if (userId) uid = parseInt(userId);
    else if (username) {
      const u = await dbGet('SELECT id FROM users WHERE username = ?', [String(username).slice(0, 32)]);
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
          const questList = QUEST_DEFS.map((def) => {
            const row = qOf(def.key);
            return {
              key: def.key,
              name: def.name,
              target: def.target,
              points: def.points,
              progress: Number(row?.progress) || 0,
              done: !!(row && Number(row.done) === 1),
            };
          });
          const activity = activityFromQuests(questList);
          const chests = CHEST_TIERS.map((tier) => {
            const row = qOf(chestKey(tier));
            return {
              tier,
              reward: CHEST_REWARDS[tier] || 0,
              unlocked: isChestUnlocked(activity, tier),
              claimed: !!(row && Number(row.done) === 1),
            };
          });
          const buffUntil = meta && meta.return_buff_until != null ? Number(meta.return_buff_until) : null;
          const mult = returnBuffMultiplier(buffUntil, nowMs);
          const attr = (s: any) => { try { return JSON.parse(String(s || '{}')); } catch { return {}; } };
          res.json({
            date,
            quests: questList,
            activity,
            chests,
            returnBuff: { until: buffUntil, active: mult > 1, multiplier: mult },
            titleEquipped: meta?.title_id != null ? Number(meta.title_id) : null,
            ownedTitles: (owned || []).map((t) => ({ id: Number(t.id), name: t.name, attr: attr(t.attr_json), source: t.source })),
            allTitles: (catalog || []).map((t) => ({ id: Number(t.id), name: t.name, attr: attr(t.attr_json), source: t.source })),
          });
        });
      });
    });
  });
});

// POST /api/quest/chest — 领取活跃度宝箱（{tier:25|50|75|100}）→ 邮件发灵石
// 领取占位=UNIQUE(user_id,date,quest_key) 单语句原子（并发双击只一方生效）；发信失败补偿删占位可重试
app.post('/api/quest/chest', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `quest:chest:${req.user?.id ?? req.ip}` }), (req: any, res: any) => {
  const tier = parseInt(req.body?.tier);
  if (!CHEST_TIERS.includes(tier)) return res.status(400).json({ error: 'tier 非法' });
  const userId = req.user.id;
  const date = bjDate(Date.now());
  const key = chestKey(tier);
  db.all('SELECT quest_key, done FROM daily_quests WHERE user_id = ? AND date = ?', [userId, date], (err: any, rows: any[]) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    const activity = activityFromQuests((rows || []).map((r) => ({ key: r.quest_key, done: r.done })));
    if (!isChestUnlocked(activity, tier)) return res.status(409).json({ error: '活跃度不足' });
    db.run('INSERT INTO daily_quests (user_id, date, quest_key, progress, done) VALUES (?, ?, ?, 0, 1)', [userId, date, key], function (this: any, err2: any) {
      if (err2) {
        if (String(err2.message || '').includes('UNIQUE')) return res.status(409).json({ error: '宝箱已领取' });
        return res.status(500).json({ error: 'Database error' });
      }
      insertMail(userId, '活跃度宝箱', `今日活跃度达到 ${tier}，宝箱开启：灵石 ×${CHEST_REWARDS[tier]} 已附上，点击领取。`, 'system', CHEST_REWARDS[tier])
        .then(() => res.json({ ok: true, tier, reward: CHEST_REWARDS[tier] }))
        .catch((e: any) => {
          console.error('chest mail error:', e?.message || e);
          db.run('DELETE FROM daily_quests WHERE user_id = ? AND date = ? AND quest_key = ?', [userId, date, key], () => {
            res.status(500).json({ error: '发奖失败，请重试' });
          });
        });
    });
  });
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
  const id = parseInt(req.body?.id);
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
        stones = Math.floor(CHRONICLE_PRAISE_BASE * Math.pow(1.5, Math.max(0, Number(rk?.realm_index) || 0)));
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
    res.json({ now, slots, recipes: ALCHEMY_RECIPES, yieldRate: ALCHEMY_YIELD_RATE });
  } catch (e: any) {
    console.error('alchemy list error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

// POST /api/alchemy/start {pill:'juqi'|'ningyuan'|'pojing', slot:0..2} — 开炉：预检灵石 → 占炉 → 扣灵石
app.post('/api/alchemy/start', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `alchemy:start:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const recipe = alchemyRecipe(req.body?.pill);
  if (!recipe) return res.status(400).json({ error: '未知丹方' });
  const slot = Math.floor(Number(req.body?.slot));
  if (!alchemySlotOk(slot)) return res.status(400).json({ error: '炉位非法' });
  const userId = req.user.id;
  try {
    // 预检：灵石余额（并发窗口由 updatePlayerSave 内闭包二次校验兜底）
    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    try { bal = Number(JSON.parse(row.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < recipe.cost) return res.status(409).json({ error: `灵石不足：需 ${recipe.cost}，现有 ${bal}` });

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
  const slot = Math.floor(Number(req.body?.slot));
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
    const yieldStones = recipe ? actApplyGain(alchemyYieldStones(recipe.cost), evMult.stonesMult * mnG.stonesMult) : 0; // Y21 活动 × Y6B 师徒倍率入账
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
        `炉火纯青，「${pill}」丹成出炉！\n\n· 丹药化灵：灵石 ×${yieldStones}（点击下方领取）${pillLine}\n\n丹炉已空，下一炉随时可开。`,
        'system', yieldStones);
    } catch (e: any) {
      console.error('alchemy claim mail error:', e?.message || e);
      // 补偿：把丹回炉（行已删，INSERT 必不冲突），玩家可重试领取
      await dbRun('INSERT INTO alchemy (player_id, slot, pill_name, start_at, mature_at) VALUES (?, ?, ?, ?, ?)',
        [userId, slot, pill, Number(r.start_at), matureAt]).catch(() => {});
      return res.status(500).json({ error: '发奖失败，请重试' });
    }
    res.json({ ok: true, slot, pill, yieldStones, pillsGained, eventMults: { exp: evMult.expMult, stones: evMult.stonesMult } });
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
    const [unlocks, crops, saveRow] = await Promise.all([
      dbAll('SELECT slot FROM farm_unlocks WHERE player_id = ? LIMIT ?', [userId, FARM_SLOTS]),
      dbAll('SELECT slot, crop, planted_at, mature_at FROM spirit_farm WHERE player_id = ? AND harvested = 0 LIMIT ?', [userId, FARM_SLOTS]),
      dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
    ]);
    let stones = 0;
    if (saveRow) {
      try { stones = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { stones = 0; }
    }
    const unlocked = new Set<number>([1]); // slot 1 永远免费可用
    for (const u of unlocks || []) { const s = Number(u.slot); if (farmSlotOk(s)) unlocked.add(s); }
    const bySlot: Record<number, any> = {};
    for (const r of crops || []) bySlot[Number(r.slot)] = r;
    const now = Date.now();
    const slots: any[] = [];
    for (let s = 1; s <= FARM_SLOTS; s++) {
      const r = bySlot[s];
      const key = r ? String(r.crop) : '';
      const def = farmCrop(key);
      slots.push({
        slot: s,
        unlocked: unlocked.has(s),
        crop: r && def ? {
          key,
          name: def.name,
          plantedAt: Number(r.planted_at),
          matureAt: Number(r.mature_at),
          ready: farmIsReady(Number(r.mature_at), now),
          leftMs: Math.max(0, Number(r.mature_at) - now),
        } : null,
      });
    }
    res.json({ now, stones, slots, crops: FARM_CROPS, unlockCost: FARM_UNLOCK_COST });
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
  const cropKey = String(req.body.crop);
  const slot = Math.floor(Number(req.body?.slot));
  if (!farmSlotOk(slot)) return res.status(400).json({ error: '田位非法' });
  const userId = req.user.id;
  try {
    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    if (slot > 1) {
      const u = await dbGet('SELECT slot FROM farm_unlocks WHERE player_id = ? AND slot = ?', [userId, slot]);
      if (!u) return res.status(409).json({ error: `第 ${slot} 块田尚未开垦`, needUnlock: true });
    }
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < crop.seed) return res.status(409).json({ error: `灵石不足：需种子 ${crop.seed}，现有 ${bal}` });

    const now = Date.now();
    const matureAt = farmMatureAt(now, crop.minutes);
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
    res.json({ ok: true, slot, crop: cropKey, name: crop.name, plantedAt: now, matureAt, seed: crop.seed });
  } catch (e: any) {
    console.error('farm plant error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/farm/harvest {slot} — 收获：到期=全额收益，提前=减半（玩家自选）；
// 守卫式 harvested=1 单语句防并发双收（双方同发只一方 changes=1）→ 灵石+修为一笔入档
// （失败补偿回退标记可重试；回退若撞上极窄窗口的新种植会失败，只记日志，收益不补——见报告边界）
app.post('/api/farm/harvest', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `farm:harvest:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const slot = Math.floor(Number(req.body?.slot));
  if (!farmSlotOk(slot)) return res.status(400).json({ error: '田位非法' });
  const userId = req.user.id;
  try {
    const r = await dbGet('SELECT id, crop, planted_at, mature_at FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 0', [userId, slot]);
    if (!r) return res.status(404).json({ error: '该田空空如也' });
    const def = farmCrop(String(r.crop));
    if (!def) return res.status(500).json({ error: '作物数据异常' });
    const now = Date.now();
    const matureAt = Number(r.mature_at);
    const early = !farmIsReady(matureAt, now);
    const gainBase = farmYield(def, early);
    // Y21：活动倍率（收获结算自动应用；引擎读取失败按 ×1 保底，不阻塞收获）
    const evMult = await resolveEventMults(now).catch(() => ({ events: [] as any[], expMult: 1, stonesMult: 1 }));
    // Y6B：师徒加成/出师增益（读取失败 ×1 保底，不阻塞收获）
    const mnG = await resolveMentorGains(userId, now).catch(() => ({ expMult: 1, stonesMult: 1 }));
    const gain = { stones: actApplyGain(gainBase.stones, evMult.stonesMult * mnG.stonesMult), exp: actApplyGain(gainBase.exp, evMult.expMult * mnG.expMult) };
    const claim = await dbRun('UPDATE spirit_farm SET harvested = 1 WHERE id = ? AND player_id = ? AND harvested = 0', [Number(r.id), userId]);
    if (!claim.changes) return res.status(409).json({ error: '该田已收获' }); // 并发双击只一方生效
    let credited = false;
    const hit = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') return;
      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + gain.stones;
      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + gain.exp;
      credited = true;
    });
    if (!hit.ok || !credited) {
      // 补偿：回退收获标记（活跃行已清零，恢复 harvested=0 必不违反部分唯一索引；极窄竞态见函数头注）
      await dbRun('UPDATE spirit_farm SET harvested = 0 WHERE id = ?', [Number(r.id)]).catch((e: any) => console.error('farm harvest revert error:', e?.message || e));
      return res.status(hit.error === 'No save found' ? 404 : 500).json({ error: hit.error === 'No save found' ? '请先进游戏创建角色' : '入账失败，请重试' });
    }
    // 回执邮件（尽力而为：收益已实际入档，邮件失败仅记日志不影响收获结果）
    insertMail(userId, '灵田丰收',
      `洞府灵田，「${def.name}」${early ? '提前起收（收益减半）' : '应时而收'}！\n\n· 灵石 +${gain.stones}（已入账）\n· 修为 +${gain.exp}（已入账）\n\n灵石与修为已直接汇入随身囊中，回游戏即可查看。田地已翻新，随时可播下一茬。`,
      'system', 0).catch((e: any) => console.error('farm harvest mail error:', e?.message || e));
    res.json({ ok: true, slot, crop: String(r.crop), name: def.name, early, stones: gain.stones, exp: gain.exp, matureAt, eventMults: { exp: evMult.expMult, stones: evMult.stonesMult } });
  } catch (e: any) {
    console.error('farm harvest error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/farm/unlock {slot:2|3} — 开垦第 2/3 块田（灵石 2000/8000，永久有效；slot 1 免费无需调用）；
// farm_unlocks 主键幂等：INSERT OR IGNORE 先占位（已开垦 changes=0 → 409 不重复扣费）→ 扣费失败补偿删行
app.post('/api/farm/unlock', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `farm:unlock:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const slot = Math.floor(Number(req.body?.slot));
  if (!farmSlotOk(slot)) return res.status(400).json({ error: '田位非法' });
  const cost = FARM_UNLOCK_COST[slot];
  if (!cost) return res.status(409).json({ error: '首块田地免费可用，无需开垦' });
  const userId = req.user.id;
  try {
    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
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
// WUDAO（R-GAME3）悟道 API（伴生页 /yl/apps/wudao/）：六系悟道（剑/丹/体/法/阵/御）各 1..10 级。
// 心得来源两条腿：① 挂机 roll（POST /api/save 打坐时长差值埋点，每分钟 8% → +10 exp 随机系）；
// ② 手动顿悟（灵石 500 → +100 exp）。攻/防/血/暴击被动加成随系等级达标解锁（Lv3 起）——
// 客户端权威架构下实际战斗结算在客户端，服务端出权威数值+伴生页展示（与称号 attr_json 同边界）。
// exp 入账=单语句原子 upsert（wudao 表 PK 幂等，无读改写竞态）；扣灵石走 updatePlayerSave（锁内二次校验）。
// ─────────────────────────────────────────────────────────

// GET /api/wudao — 六系等级+exp+加成列表+悟道日志+灵石余额（一页全量，不落账）
app.get('/api/wudao', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `wudao:me:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const [rows, saveRow, logRows] = await Promise.all([
      dbAll('SELECT dao_type, exp FROM wudao WHERE player_id = ? LIMIT 6', [userId]),
      dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
      dbAll('SELECT dao_type, exp, source, created_at FROM wudao_log WHERE player_id = ? ORDER BY id DESC LIMIT 20', [userId]),
    ]);
    const expByDao: Record<string, number> = {};
    for (const r of rows || []) expByDao[String(r.dao_type)] = Math.max(0, Math.floor(Number(r.exp) || 0));
    let balance: number | null = null;
    if (saveRow) {
      try { balance = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { balance = null; }
    }
    const daos = Object.keys(WUDAO_DAOS).map((k) => {
      const d = WUDAO_DAOS[k];
      const exp = expByDao[k] || 0;
      const level = wudaoLevelFromExp(exp);
      const next = level < WUDAO_MAX_LEVEL ? wudaoExpToReach(level + 1) : null;
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
      insight: { chancePerMinute: WUDAO_INSIGHT_CHANCE, exp: WUDAO_INSIGHT_EXP, capMinutesPerUpload: WUDAO_IDLE_CAP_MINUTES },
      manual: { cost: WUDAO_MANUAL_COST, exp: WUDAO_MANUAL_EXP },
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
    const daoKey = String(req.body?.dao ?? '');
    if (!wudaoDaoOk(daoKey)) return res.status(400).json({ error: '未知的悟道系别' });
    // 预检：角色与灵石余额（并发窗口由 updatePlayerSave 锁内二次校验兜底）
    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(row.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < WUDAO_MANUAL_COST) return res.status(409).json({ error: `灵石不足：需 ${WUDAO_MANUAL_COST}，现有 ${bal}` });
    // 1) 扣灵石（saveLock 互斥 + gm_revision++ 促客户端拉新档；锁内余额不足拒绝）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') { short = true; return; }
      const b = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0));
      if (b < WUDAO_MANUAL_COST) { short = true; return; }
      sd.player.spiritStones = b - WUDAO_MANUAL_COST;
    });
    if (!paid.ok || short) {
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '顿悟失败，请重试') });
    }
    // 2) exp 入账 + 日志（原子 upsert）；失败补偿退灵石，本次不作数可重试
    const added = await wudaoAddExp(userId, daoKey, WUDAO_MANUAL_EXP, 'manual');
    if (!added) {
      await updatePlayerSave(userId, (sd: any) => {
        if (!sd.player || typeof sd.player !== 'object') return;
        sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + WUDAO_MANUAL_COST;
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
      cost: WUDAO_MANUAL_COST,
    });
  } catch (e: any) {
    console.error('wudao insight error:', e?.message || e);
    if (!res.headersSent) res.status(500).json({ error: '服务器繁忙' });
  }
});

// ─────────────────────────────────────────────────────────
// Y20 功法系统 API（伴生页 /yl/apps/gongfa/）：六部功法（焚天诀/御剑术/不灭体/大衍诀/周天阵/御灵术）
// 各 1..10 级；修炼即时完成，升到 L 级耗灵石 100×L，对应属性被动 +2%×level——
// 客户端权威架构下实际属性结算在客户端（与称号 attr_json/悟道加成同边界），服务端出权威数值+伴生页展示。
// 升级=扣灵石先行（updatePlayerSave saveLock 互斥+锁内二次校验）→ 守卫式推进（WHERE level=旧值，
// 并发双升只一方生效）→ 推进失败补偿退灵石可重试（wudao/insight 同款全或无）。
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
      const shown = gongfaLevelFromExp(exp); // 展示以 exp 推导为准（level 列仅为冗余缓存）
      const next = shown < GONGFA_MAX_LEVEL ? gongfaCostToReach(shown + 1) : null;
      return {
        key: k,
        name: d.name,
        stat: d.stat,
        statName: d.statName,
        level: shown,
        exp,
        costToNext: next == null ? 0 : next,
        bonusPct: gongfaBonusPct(shown),
        bonusText: shown > 0 ? `${d.statName} +${gongfaBonusPct(shown)}%` : `${d.statName}加成（修炼后 +2%/级）`,
        maxed: shown >= GONGFA_MAX_LEVEL,
      };
    });
    res.json({
      now: Date.now(),
      gongfas,
      maxLevel: GONGFA_MAX_LEVEL,
      stepCost: GONGFA_STEP_COST,
      bonusStepPct: GONGFA_BONUS_STEP_PCT,
      maxExpTotal: GONGFA_MAX_EXP_TOTAL,
      balance,
      hasSave: !!saveRow,
    });
  } catch (e: any) {
    console.error('gongfa list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/gongfa/levelup {gongfa:'fentian'|...} — 修炼升级：灵石 100×目标级 → level+1（即时完成）。
// 顺序=先扣灵石（防白嫖）后守卫推进；推进失败补偿退灵石（退款失败仅记日志，不产生复制收益）
app.post('/api/gongfa/levelup', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `gongfa:levelup:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const key = String(req.body?.gongfa ?? '');
    if (!gongfaOk(key)) return res.status(400).json({ error: '未知的功法' });
    const g = await dbGet('SELECT id FROM gongfa WHERE key = ?', [key]);
    if (!g) return res.status(500).json({ error: '功法目录缺失' });
    const gid = Number(g.id);
    // 当前等级（无行=未入门 0 级）
    const row = await dbGet('SELECT level, exp FROM player_gongfa WHERE player_id = ? AND gongfa_id = ?', [userId, gid]);
    const curLevel = Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(row?.level) || 0)));
    if (curLevel >= GONGFA_MAX_LEVEL) return res.status(409).json({ error: '该功法已大成（Lv10），无法再进阶' });
    const cost = gongfaCostToReach(curLevel + 1);
    // 预检：角色与灵石余额（并发窗口由 updatePlayerSave 锁内二次校验兜底）
    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
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
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '修炼失败，请重试') });
    }
    // 2) 守卫式推进：WHERE level=旧值（并发双升只一方生效）；无行则首建（PK 冲突=他人已建→视为并发失败）
    let advanced = false;
    if (row) {
      const up = await dbRun(
        'UPDATE player_gongfa SET level = level + 1, exp = exp + ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?',
        [cost, userId, gid, curLevel]
      );
      advanced = up.changes > 0;
    } else {
      try {
        const ins = await dbRun('INSERT INTO player_gongfa (player_id, gongfa_id, level, exp) VALUES (?, ?, 1, ?)', [userId, gid, cost]);
        advanced = ins.changes > 0;
      } catch (e: any) {
        if (String(e?.message || '').includes('UNIQUE')) advanced = false;
        else throw e;
      }
    }
    if (!advanced) {
      // 补偿：并发他手已推进，本次灵石退还，不作数可重试
      await updatePlayerSave(userId, (sd: any) => {
        if (!sd.player || typeof sd.player !== 'object') return;
        sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + cost;
      }).catch((e: any) => console.error('gongfa levelup refund error:', e?.message || e));
      return res.status(409).json({ error: '修炼并发冲突，灵石已退还，请重试' });
    }
    const newLevel = curLevel + 1;
    const d = GONGFA_LIST[key];
    res.json({
      ok: true,
      gongfa: key,
      name: d.name,
      level: newLevel,
      exp: gongfaExpToReach(newLevel),
      cost,
      bonusPct: gongfaBonusPct(newLevel),
      bonusText: `${d.statName} +${gongfaBonusPct(newLevel)}%`,
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
    const on = Number(req.body?.engineOn) === 0 ? '0' : '1';
    await dbRun(
      "INSERT INTO activity_config (key, value) VALUES ('engine_on', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
      [on]
    );
    logGmAction('activity_config', 'engine_on', { engineOn: on });
    // GM global kill switch (activity_config.engine_on): mirror into memory so the timer
    // needs no DB read while the engine is off. This is a hot-reload channel for the GM
    // switch only; it is NOT what keeps Tianjiang Lingyu off by default.
    rainEngineOn = on === '1';
    res.json({ ok: true, engineOn: on === '1' });
  } catch (e: any) {
    console.error('gm activity config error:', e?.message || e);
    res.status(500).json({ error: '保存失败' });
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
    const [meRow, mentorRow, appRows, histRows, coolRow] = await Promise.all([
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
         WHERE (m.mentor_id = ? OR m.apprentice_id = ?) AND m.status != 'active'
         ORDER BY m.id DESC LIMIT 10`,
        [userId, userId, userId, userId]
      ),
      dbGet("SELECT MAX(ended_at) AS e FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND (mentor_id = ? OR apprentice_id = ?)", [userId, userId]),
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
    const targetId = Math.floor(Number(req.body?.userId));
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
    // 守卫式单语句插入：全部门槛一次原子生效（并发双拜只一方 changes=1）
    const ins = await dbRun(
      `INSERT INTO mentorships (mentor_id, apprentice_id, status, created_at)
       SELECT ?, ?, 'active', ?
       WHERE (SELECT COUNT(*) FROM mentorships WHERE mentor_id = ? AND status = 'active') < ?
         AND NOT EXISTS (SELECT 1 FROM mentorships WHERE apprentice_id = ? AND status = 'active')
         AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))
         AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))`,
      [targetId, userId, now, targetId, MENTOR_MAX_APPRENTICES, userId, coolSince, userId, userId, coolSince, targetId, targetId]
    );
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
    insertMail(targetId, '拜师',
      `道友「${myName}」仰慕你修行精深，正式拜入你门下。\n\n· 徒弟收益的 ${MENTOR_TAX_RATE * 100}%（修为/灵石）将自动奉上\n· 师徒同行（双方在线）时，徒弟服务端结算收益 +${Math.round((MENTOR_BONUS_MULT - 1) * 100)}%\n· 徒弟金丹期出师时：你将获得其拜师以来累计灵石收益 ${MENTOR_GRAD_RATE * 100}% 的出师回馈 + 7 天 ×${MENTOR_BUFF_MULT} 收益增益 + 称号「良师益友」\n\n（若不欲收徒，可在 /yl/apps/mentor/ 解除关系；解除后双方冷却 7 天）`,
      'system', 0).catch((e: any) => console.error('mentor bind mail(target) error:', e?.message || e));
    insertMail(userId, '拜师成功',
      `你已正式拜「${targetName}」为师。\n\n· 师徒同行（双方在线）时，你的服务端结算收益 +${Math.round((MENTOR_BONUS_MULT - 1) * 100)}%\n· 师傅将抽成你收益的 ${MENTOR_TAX_RATE * 100}%（师傅入账）\n· 修至金丹期后可在师徒页出师\n\n尊师重道，修行有道。`,
      'system', 0).catch((e: any) => console.error('mentor bind mail error:', e?.message || e));
    res.json({ ok: true, mentor: { id: targetId, name: targetName }, since: now });
  } catch (e: any) {
    console.error('mentor apprentice error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/mentor/graduate {apprenticeId?} — 出师：徒弟本人调用，或师傅指定徒弟。
// 门槛=徒弟境界≥金丹期；守卫式单语句 UPDATE（active→completed + 增益截止），并发双点只一方生效；
// 回馈=徒弟拜师日以来累计灵石收益（stats_daily 同源）×30% 随邮件发放；发信失败回滚出师可重试
app.post('/api/mentor/graduate', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `mentor:grad:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    let rel = await dbGet("SELECT id, mentor_id, apprentice_id, created_at FROM mentorships WHERE apprentice_id = ? AND status = 'active' LIMIT 1", [userId]);
    if (!rel) {
      const appId = Math.floor(Number(req.body?.apprenticeId));
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
    insertMail(apprenticeId, '出师',
      `恭喜道友修至金丹，今日出师，自立门户！\n\n师恩已报于传承之中：师傅获得了你拜师以来累计收益的 ${MENTOR_GRAD_RATE * 100}% 作为出师回馈。\n\n愿仙路漫漫，各自精进，他日江湖再见。`,
      'system', 0).catch((e: any) => console.error('mentor graduate mail(app) error:', e?.message || e));
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
      const appId = Math.floor(Number(req.body?.apprenticeId));
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
        `SELECT u.id, COALESCE(NULLIF(r.name, ''), u.username) AS name, r.realm_index, r.realm_level
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
const utcDayStartMs = (): number => {
  const d = new Date(); d.setUTCHours(0, 0, 0, 0); return d.getTime();
};

// 按玩家名（rankings.name 优先，退 users.username，精确匹配）找用户
async function findUserByName(nameRaw: unknown): Promise<{ id: number; name: string } | null> {
  const name = String(nameRaw ?? '').trim().slice(0, 32);
  if (!name) return null;
  const r = await dbGet(
    `SELECT u.id AS id, COALESCE(NULLIF(rg.name, ''), u.username) AS name
     FROM users u LEFT JOIN rankings rg ON rg.user_id = u.id
     WHERE COALESCE(NULLIF(rg.name, ''), u.username) = ? LIMIT 1`, [name]);
  if (r) return { id: Number(r.id), name: String(r.name) };
  const u = await dbGet('SELECT id, username AS name FROM users WHERE username = ? LIMIT 1', [name]);
  return u ? { id: Number(u.id), name: String(u.name) } : null;
}

// 总等级（rankings 口径 境界序×9+层数）；无档返回 null
async function totalLevelOf(userId: number): Promise<number | null> {
  const r = await dbGet('SELECT realm_index, realm_level FROM rankings WHERE user_id = ?', [userId]);
  if (!r || r.realm_index == null) return null;
  return Number(r.realm_index) * 9 + Number(r.realm_level || 1);
}

function sameRealmMult(realm: unknown): number {
  const idx = Math.max(0, ECON_REALM_ORDER.indexOf(String(realm || '')));
  return Math.pow(1.5, Math.min(20, idx));
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
    const fid = Math.floor(Number(req.body?.friendId));
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
    const fid = Math.floor(Number(req.body?.friendId));
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
    const name = String(req.body?.name || '').trim().slice(0, 12);
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
    const realmMult = Math.pow(1.5, Math.min(20, Math.max(0, Number(mult?.ri) || 0)));
    const expGain = Math.floor(20000 * realmMult);
    const stoneGain = Math.floor(1000 * realmMult);
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
  const coupleId = parseInt(req.body?.coupleId);
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
        sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + Math.floor(FEAST_GIFT * Math.pow(1.5, Math.max(0, ECON_REALM_ORDER.indexOf(String(sd.player.realm || '')))));
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
  return Math.pow(1.5, Math.min(20, Math.max(0, Number(r && r.realm_index) || 0)));
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
    const id = Math.floor(Number(req.body?.battleId));
    if (!Number.isInteger(id) || id <= 0) return res.status(400).json({ error: '参数非法' });
    const r = await arenaSettle(id, userId);
    if (!r.ok) return res.status(409).json({ error: r.error });
    res.json({ ok: true, iWon: r.iWon, log: r.log });
  } catch (e: any) { console.error('arena accept error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/arena/decline', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `ar:dc:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const id = Math.floor(Number(req.body?.battleId));
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
    const enemyId = Math.floor(Number(req.body?.enemyId));
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
      appId = Math.floor(Number(req.body?.apprenticeId));
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
const TEA_MIN_BET = 100, TEA_MAX_BET = 10000, TEA_PAYOUT = 1.9, TEA_OPEN_UTC = 13;
const WB_STRIKES = 3, WB_HP_BASE = 500000, WB_KILLER_BONUS = 5000;
const GREET_STONES_BASE = 200;

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
    const peerId = Math.floor(Number(req.body?.peerId));
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
      await updatePlayerSave(Number(b.user_id), (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + payout; });
    }
  }
  // 全服播报：当日最大赢家电台
  const best = await dbGet('SELECT user_id, payout FROM teahouse_bets WHERE date = ? AND won = 1 ORDER BY payout DESC LIMIT 1', [today]);
  if (best && Number(best.payout) >= 5000) {
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
    res.json({
      now: Date.now(), date: today, topic: t, open,
      closesAtUtcHour: TEA_OPEN_UTC, payoutMult: TEA_PAYOUT,
      minBet: TEA_MIN_BET, maxBet: TEA_MAX_BET,
      myBet: mine ? { side: Number(mine.side), stones: Number(mine.stones), won: mine.won == null ? null : Number(mine.won), payout: mine.payout == null ? null : Number(mine.payout) } : null,
      pool: (pool || []).map((x: any) => ({ side: Number(x.side), bets: Number(x.n), stones: Number(x.s) || 0 })),
    });
  } catch (e: any) { console.error('teahouse today error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

app.post('/api/teahouse/bet', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `th:bet:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const today = utcDateStr();
    if (new Date().getUTCHours() >= TEA_OPEN_UTC) return res.status(409).json({ error: '今日茶馆已开盅，明日赶早' });
    const t = teaTopicOf(today);
    const side = Math.floor(Number(req.body?.side));
    if (side !== 0 && side !== 1) return res.status(400).json({ error: '只可选 A 或 B' });
    const stones = Math.floor(Number(req.body?.stones));
    if (!Number.isInteger(stones) || stones < TEA_MIN_BET || stones > TEA_MAX_BET) return res.status(400).json({ error: `押注须 ${TEA_MIN_BET}~${TEA_MAX_BET} 灵石` });
    const dup = await dbGet('SELECT id FROM teahouse_bets WHERE user_id = ? AND date = ?', [userId, today]);
    if (dup) return res.status(409).json({ error: '今日已押过一卦' });
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < stones) { short = true; return; }
      sd.player.spiritStones = b - stones;
    });
    if (!paid.ok || short) return res.status(409).json({ error: '灵石不足' });
    await dbRun('INSERT INTO teahouse_bets (user_id, date, topic_id, side, stones, created_at) VALUES (?, ?, ?, ?, ?, ?)', [userId, today, t.id, side, stones, Date.now()]);
    res.json({ ok: true, side, stones });
  } catch (e: any) { console.error('teahouse bet error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
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
  { id: 'enter', name: '初入江湖', desc: '创建角色存档', reward: 500, check: 'has_save' },
  { id: 'lv3', name: '炼气三层', desc: '总等级达到 3', reward: 800, check: 'lv', arg: 3 },
  { id: 'lv9', name: '炼气圆满', desc: '总等级达到 9', reward: 1500, check: 'lv', arg: 9 },
  { id: 'zhuji', name: '筑基成功', desc: '总等级达到 10', reward: 2000, check: 'lv', arg: 10 },
  { id: 'friend', name: '结识道友', desc: '添加 1 位好友', reward: 800, check: 'friend' },
  { id: 'baishi', name: '拜入师门', desc: '拥有师傅', reward: 1500, check: 'has_mentor' },
  { id: 'jindan', name: '金丹初成', desc: '总等级达到 19', reward: 5000, check: 'lv', arg: 19 },
  { id: 'daolv', name: '喜结道侣', desc: '结为道侣', reward: 3000, check: 'married' },
];
const WEEK_REWARDS = [500, 800, 1200, 1800, 2500, 3500, 5000];

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
    const stepId = String(req.body?.stepId || '').slice(0, 32);
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
    const day = Math.floor(Number(req.body?.day));
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
    const [rows, book] = await Promise.all([
      dbAll('SELECT count, tier, event_key, exp_gain, stones FROM adventures WHERE player_id = ? AND date = ? ORDER BY count LIMIT ?', [userId, date, ADVENTURE_DAILY_MAX]),
      dbAll('SELECT event_key, COUNT(*) AS times FROM adventures WHERE player_id = ? GROUP BY event_key ORDER BY MIN(id) LIMIT 100', [userId]),
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
      };
    });
    const collected: Record<string, number> = {};
    for (const b of book || []) collected[String(b.event_key || '')] = Math.max(0, Number(b.times) || 0);
    res.json({
      date,
      drawn: draws.length,
      dailyMax: ADVENTURE_DAILY_MAX,
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
      tiers: ADVENTURE_TIERS,
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
    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    try { JSON.parse(row.save_data); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    const tier = drawAdventureTier(Math.random);
    const ev = pickAdventureEvent(tier.key, Math.random);
    const stones = tier.stones;
    // 落账本先行占位：UNIQUE(player_id,date,count) 冲突=并发双抽，只一方生效（另一方 409 重试）
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun(
        'INSERT INTO adventures (player_id, date, count, tier, event_key, exp_gain, stones) VALUES (?, ?, ?, ?, ?, 0, ?)',
        [userId, date, drawn + 1, tier.key, ev.key, stones]
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
      expGain = adventureExpGain(tier.key, nrNow.maxExp, nrNow.exp);
      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + expGain;
      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + stones;
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
  db.get('SELECT save_data, updated_at, offline_claimed_until, month_card_until FROM saves WHERE user_id = ?', [req.user.id], async (err: any, row: any) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let p: any;
    try { p = JSON.parse(row.save_data)?.player ?? {}; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    const nr = normalizeRealm(p);
    const nowMs = Date.now();
    const mc = hasMonthCard(row.month_card_until, nowMs);
    const capHours = offlineCapHours(mc);
    const ratePerHour = offlineRatePerHour(mc);
    const win = offlineWindow(parseDbTimeMs(row.updated_at), row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, nowMs);
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
    const row = await dbGet('SELECT save_data, updated_at, offline_claimed_until, month_card_until FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let p: any;
    try { p = JSON.parse(row.save_data)?.player ?? {}; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    const nr = normalizeRealm(p);
    const nowMs = Date.now();
    const mc = hasMonthCard(row.month_card_until, nowMs);
    const capHours = offlineCapHours(mc);
    const ratePerHour = offlineRatePerHour(mc);
    const win = offlineWindow(parseDbTimeMs(row.updated_at), row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, nowMs);
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
// Y19 成就系统 API（伴生页 /yl/apps/ach/ 用）：五类各 4 项共 20 项，达成从 stats_daily/daily_quests/saves
// 惰性推导（零新增埋点、零新增统计表）；achievement_claimed 主键幂等防重复领奖，奖励走邮件（灵石阶梯）
// ─────────────────────────────────────────────────────────

// GET /api/achievements — 全 20 项 + 每类进度 + 可领取清单（惰性计算，一页全量）
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
    let realmName = '未开始';
    if (saveRow) {
      try {
        const r = JSON.parse(String(saveRow.save_data))?.player?.realm;
        const i = typeof r === 'string' ? REALM_ORDER_FOR_RANKING.indexOf(r) : -1;
        if (i >= 0) { realmIndex = i; realmName = r; }
      } catch { /* 坏存档按无境界处理，不阻塞列表 */ }
    }
    const view = buildAchievementsView(
      achTotalsFrom({ minutes: sum?.m, kills: sum?.k, silver: sum?.s, quests: questCnt?.c, realmIndex }),
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
    if (saveRow) {
      try {
        const r = JSON.parse(String(saveRow.save_data))?.player?.realm;
        realmIndex = typeof r === 'string' ? REALM_ORDER_FOR_RANKING.indexOf(r) : -1;
      } catch { /* 坏存档按无境界处理 */ }
    }
    const view = buildAchievementsView(
      achTotalsFrom({ minutes: sum?.m, kills: sum?.k, silver: sum?.s, quests: questCnt?.c, realmIndex }),
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
  } : null;
}

// GET /api/pet — 我的宠物全量（宠物卡 + 今日嬉戏次数 + 喂养记录 + 常量表）
app.get('/api/pet', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `pet:me:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const pet = await dbGet('SELECT name, rarity, hunger, exp, bond, created_at FROM pets WHERE player_id = ?', [userId]);
    const today = petDate(Date.now());
    const [play, logs] = await Promise.all([
      dbGet('SELECT times FROM pet_play_log WHERE player_id = ? AND date = ?', [userId, today]),
      dbAll('SELECT kind, detail, created_at FROM pet_care_log WHERE player_id = ? ORDER BY id DESC LIMIT 20', [userId]),
    ]);
    res.json({
      pet: petView(pet),
      createdAt: pet?.created_at ?? null,
      playTimes: Math.min(PET_PLAY_DAILY_MAX, Number(play?.times) || 0),
      careLog: (logs || []).map((l: any) => ({ kind: String(l.kind), detail: String(l.detail), createdAt: l.created_at })),
      consts: {
        feedCost: PET_FEED_COST, hungerPerFeed: PET_HUNGER_PER_FEED, hungerMax: PET_HUNGER_MAX,
        levelDivisor: PET_LEVEL_DIVISOR, playDailyMax: PET_PLAY_DAILY_MAX, playBond: PET_PLAY_BOND,
        battleLevel: PET_BATTLE_LEVEL,
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
    const existed = await dbGet('SELECT id FROM pets WHERE player_id = ?', [userId]);
    if (existed) return res.status(409).json({ error: '你已有灵宠相伴' });
    const name = rollPetName();
    const rarity = rollPetRarity();
    try {
      await dbRun('INSERT INTO pets (player_id, name, rarity, level, exp, hunger, bond) VALUES (?, ?, ?, 0, 0, 0, 0)', [userId, name, rarity]);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '你已有灵宠相伴' });
      throw e;
    }
    const rarityLabel = rarity === '仙' ? '仙品' : rarity === '灵' ? '灵品' : '凡品';
    logChronicle(userId, String(req.user.username || '').slice(0, 32), `【妖灵】仙山偶遇${rarityLabel}灵宠「${name}」，结缘收养，自此相伴修行`); // Y16 江湖志
    logPetCare(userId, 'adopt', `收养灵宠「${name}」（${rarityLabel}）`);
    res.json({ ok: true, pet: petView({ name, rarity, hunger: 0, exp: 0, bond: 0 }) });
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
    const pet = await dbGet('SELECT id, name, hunger, level FROM pets WHERE player_id = ?', [userId]);
    if (!pet) return res.status(404).json({ error: '请先收养一只灵宠' });
    if (!petFeedResult(pet.hunger).ok) return res.status(409).json({ error: `喂食度已达上限 ${PET_HUNGER_MAX}，灵宠已经饱足` });

    // 预检灵石余额（并发窗口由 updatePlayerSave 内闭包二次校验兜底）
    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    try { bal = Number(JSON.parse(row.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < PET_FEED_COST) return res.status(409).json({ error: `灵石不足：需 ${PET_FEED_COST}，现有 ${bal}` });

    // 扣费（saveLock 互斥 + gm_revision++ 促客户端拉新档）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < PET_FEED_COST) { short = true; return; }
      sd.player.spiritStones = b - PET_FEED_COST;
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
      [PET_HUNGER_MAX, PET_HUNGER_PER_FEED, PET_HUNGER_MAX, PET_HUNGER_PER_FEED, PET_HUNGER_MAX, PET_HUNGER_PER_FEED, PET_LEVEL_DIVISOR, userId]
    );
    if (!upd.changes) {
      // 补偿退费（宠物行异常缺失，理论不可达，防御性全或无）
      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + PET_FEED_COST; });
      return res.status(404).json({ error: '请先收养一只灵宠' });
    }
    let fresh = await dbGet('SELECT name, rarity, hunger, exp, bond FROM pets WHERE player_id = ?', [userId]);
    let battleReached = false;
    if (fresh && petBattleReached(pet.level, petLevel(fresh.hunger))) {
      battleReached = true;
      await dbRun('UPDATE pets SET bond = bond + ? WHERE player_id = ?', [PET_BATTLE_BOND, userId]);
      logPetCare(userId, 'battle', `「${String(fresh.name)}」修至第 ${PET_BATTLE_LEVEL} 品，凝出妖灵精魄，羁绊 +${PET_BATTLE_BOND}`);
      try {
        await insertMail(userId, '妖灵精魄',
          `灵宠「${String(fresh.name)}」喂食有成，修至第 ${PET_BATTLE_LEVEL} 品，凝出「妖灵精魄」！\n\n· 羁绊 +${PET_BATTLE_BOND}（出战加成之基，实战生效待客户端接入）\n· 灵石 ×${PET_BATTLE_STONES}（点击下方领取）\n\n人宠同心，其利断金。`,
          'system', PET_BATTLE_STONES);
      } catch (e: any) {
        console.error('pet battle mail error:', e?.message || e); // 邮件失败不影响喂养本体（bond 已落库）
      }
      fresh = await dbGet('SELECT name, rarity, hunger, exp, bond FROM pets WHERE player_id = ?', [userId]); // 精魄 bond+20 后回读
    }
    logPetCare(userId, 'feed', `喂食「${String(pet.name)}」，喂食度 +${PET_HUNGER_PER_FEED}`);
    res.json({ ok: true, pet: petView(fresh), battleReached });
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
    const gate = await dbRun(
      `INSERT INTO pet_play_log (player_id, date, times) VALUES (?, ?, 1)
       ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1 WHERE times < ?`,
      [userId, date, PET_PLAY_DAILY_MAX]
    );
    if (!gate.changes) return res.status(409).json({ error: `今日嬉戏次数已用完（每日 ${PET_PLAY_DAILY_MAX} 次），明日再来` });
    const upd = await dbRun('UPDATE pets SET bond = bond + ? WHERE player_id = ?', [PET_PLAY_BOND, userId]);
    if (!upd.changes) {
      await dbRun('UPDATE pet_play_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?', [userId, date]); // 补偿回退占位可重试
      return res.status(404).json({ error: '请先收养一只灵宠' });
    }
    const fresh = await dbGet('SELECT name, rarity, hunger, exp, bond FROM pets WHERE player_id = ?', [userId]);
    const prow = await dbGet('SELECT times FROM pet_play_log WHERE player_id = ? AND date = ?', [userId, date]);
    logPetCare(userId, 'play', `与「${fresh ? String(fresh.name) : '灵宠'}」嬉戏，羁绊 +${PET_PLAY_BOND}`);
    res.json({
      ok: true,
      pet: petView(fresh),
      playTimes: Math.min(PET_PLAY_DAILY_MAX, Math.max(1, Number(prow?.times) || 0)),
    });
  } catch (e: any) {
    console.error('pet play error:', e?.message || e);
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
    const move = Math.min(Math.max(1, Math.floor(Number(req.body?.count) || 1)), stash, TRIB_PILL_MAX - committed);
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
    const row = await dbGet('SELECT count, observed, adventure, last_ts, anomaly FROM dungeon_tracker WHERE player_id = ? AND date = ?', [req.user.id, bjDate(nowMs)]);
    res.json(dungeonStatusView(row, nowMs));
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
      const row = await dbGet('SELECT count, last_ts FROM dungeon_tracker WHERE player_id = ? AND date = ?', [req.user.id, date]);
      const verdict = dungeonEntryVerdict(row?.count, row?.last_ts != null ? Number(row.last_ts) : null, nowMs);
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
          error: verdict.reason === 'cap' ? `今日秘境次数已用完（上限 ${DUNGEON_DAILY_CAP} 次）` : '进入过于频繁，请稍候再试',
          count: verdict.count,
          cap: DUNGEON_DAILY_CAP,
          remaining: Math.max(0, DUNGEON_DAILY_CAP - verdict.count),
          retryAfterMs: verdict.retryAfterMs ?? 0,
        });
      }
      res.json({ ok: true, count: verdict.count, cap: DUNGEON_DAILY_CAP, remaining: Math.max(0, DUNGEON_DAILY_CAP - verdict.count), cdMs: DUNGEON_ENTRY_CD_MS });
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
  const bountyId = Math.floor(Number(req.body?.id));
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
  const bountyId = Math.floor(Number(req.body?.id));
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
  const bountyId = Math.floor(Number(req.body?.id));
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
const SECT_CREATE_COST = 50000;      // 建宗灵石（一次性；不进 sect_ledger、不推进捐献任务；物价×10）
const SECT_CREATE_MIN_REALM = 1;     // 建宗境界门槛：REALM_ORDER_FOR_RANKING 下标 ≥1（筑基期）
const SECT_NAME_MIN = 2;             // 宗门名称长度下限（TRIM 后字符数）
const SECT_NAME_MAX = 12;            // 宗门名称长度上限
const SECT_DONATE_MIN = 100;         // 单笔捐献下限
const SECT_DONATE_MAX = 100000;      // 单笔捐献上限
const SECT_DONATE_DAILY_CAP = 50000; // 每人每日捐献累计上限（sect_ledger 北京日切 SUM 口径）
const SECT_LEAVE_COOLDOWN_MS = 24 * 3600 * 1000; // 退宗/被踢/解散后 24h 冷却（服务端表约束）
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
    disbanded_at DATETIME
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
});

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
const SECT_GF_TIER_BASE: Record<number, number> = { 1: 100, 2: 250, 3: 600, 4: 1500 };
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
  const m: Record<string, SectGfDef> = {};
  for (const g of SECT_GF_LIST) m[g.id] = g;
  return m;
})();
// \u5c42\u6570\u5f52\u4e00\uff080..5\uff09
function sectGfLevel(v: unknown): number {
  return Math.min(SECT_GF_MAX_LEVEL, Math.max(0, Math.floor(Number(v) || 0)));
}
// \u5347\u5230 level \u5c42\u6240\u9700\u7684\u5b97\u95e8\u8d21\u732e
function sectGfCost(tier: unknown, level: unknown): number {
  return (SECT_GF_TIER_BASE[Math.floor(Number(tier) || 0)] || 0) * Math.max(1, Math.floor(Number(level) || 1));
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
  const id = String(idRaw || '');
  const def = SECT_GF_BY_ID[id];
  if (!def) return { status: 400, body: { error: '\u672a\u77e5\u7684\u5b97\u95e8\u529f\u6cd5', code: 'BAD_GONGFA' } };
  const pl = await sectGfPlayerOf(userId);
  if (!pl || !pl.sectId) return { status: 400, body: { error: '\u4f60\u8fd8\u6ca1\u6709\u52a0\u5165\u5b97\u95e8', code: 'NO_SECT' } };
  if (!sectGfRankOk(pl.sectRank, def.rank)) {
    return { status: 403, body: { error: '\u804c\u8854\u4e0d\u8db3\uff0c\u9700\u8fbe\u5230' + def.rank, code: 'RANK_TOO_LOW' } };
  }
  if (!sectGfRealmOk(pl.realm, def.realm)) {
    return { status: 403, body: { error: '\u5883\u754c\u4e0d\u8db3\uff0c\u9700\u8fbe\u5230' + def.realm, code: 'REALM_TOO_LOW' } };
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

// ── V27 限流：读 60/min、写 20/min（按用户分桶；rateLimit 实现见 P1-4/P1-5 段）──
const sectReadLimit = rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `sect:r:${req.user.id}` });
const sectWriteLimit = rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `sect:w:${req.user.id}` });

// 宗门列表（分页）：等级降序→资金降序；宗主名/人数实时子查询
app.get('/api/sect/list', authenticateToken, sectReadLimit, async (req: any, res: any) => {
  try {
    const page = Math.max(1, Math.floor(Number(req.query.page)) || 1);
    const totalRow: any = await dbGet('SELECT COUNT(*) AS c FROM sects WHERE disbanded_at IS NULL');
    const total = Number(totalRow?.c) || 0;
    const pages = Math.max(1, Math.ceil(total / SECT_LIST_PAGE_SIZE));
    const rows: any[] = await dbAll(
      `SELECT s.id, s.name, s.level, s.funds, lu.username AS leader,
              (SELECT COUNT(*) FROM sect_members m WHERE m.sect_id = s.id) AS member_count
       FROM sects s LEFT JOIN users lu ON lu.id = s.leader_id
       WHERE s.disbanded_at IS NULL
       ORDER BY s.level DESC, s.funds DESC, s.id ASC
       LIMIT ? OFFSET ?`,
      [SECT_LIST_PAGE_SIZE, (Math.min(page, pages) - 1) * SECT_LIST_PAGE_SIZE]
    );
    res.json({ list: rows, page: Math.min(page, pages), pages, total });
  } catch (e: any) {
    console.error('sect list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 我的宗门（全景）：宗门信息 + 成员表 + 今日任务进度与个人可领状态 + 福利可领状态
app.get('/api/sect/mine', authenticateToken, sectReadLimit, async (req: any, res: any) => {
  try {
    const member = await sectMemberOf(req.user.id);
    if (!member) return res.json({ sect: null });
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
    res.json({
      sect: {
        id: sect.id, name: sect.name, level, funds: Number(sect.funds) || 0,
        notice: String(sect.notice || ''), memberCount: members.length,
        memberCap: SECT_MEMBER_CAP(level), createdAt: sect.created_at ?? null,
      },
      myRole: member.role,
      members,
      tasks,
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

// 创建宗门：境界≥筑基 + 名称唯一 + 5000 灵石（服务端结算：spendFromSave 失败即无宗）
app.post('/api/sect/create', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const name = String(req.body?.name ?? '').trim();
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
      return res.status(400).json({ error: '境界需达到筑基期方可开宗立派', code: 'REALM_TOO_LOW' });
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
    const sectId = Math.floor(Number(req.body?.sectId));
    if (!Number.isFinite(sectId) || sectId <= 0) return res.status(400).json({ error: '参数非法' });
    if (await sectMemberOf(req.user.id)) {
      return res.status(400).json({ error: '你已在宗门中', code: 'ALREADY_IN_SECT' });
    }
    const cd: any = await dbGet('SELECT cooldown_until FROM sect_cooldowns WHERE user_id = ?', [req.user.id]);
    if (cd) {
      const untilMs = Date.parse(String(cd.cooldown_until || ''));
      if (Number.isFinite(untilMs) && untilMs > Date.now()) {
        return res.status(403).json({
          error: '退宗冷却中，24 小时后方可加入新宗门', code: 'COOLDOWN_UNTIL',
          until: new Date(untilMs).toISOString(),
        });
      }
    }
    const sect: any = await dbGet('SELECT id, level, disbanded_at FROM sects WHERE id = ?', [sectId]);
    if (!sect || sect.disbanded_at) return res.status(404).json({ error: '宗门不存在或已解散' });
    const cntRow: any = await dbGet('SELECT COUNT(*) AS c FROM sect_members WHERE sect_id = ?', [sectId]);
    if ((Number(cntRow?.c) || 0) >= SECT_MEMBER_CAP(Number(sect.level) || 1)) {
      return res.status(400).json({ error: '该宗门人数已满', code: 'SECT_FULL' });
    }
    try {
      await dbRun('INSERT INTO sect_members (sect_id, user_id, role) VALUES (?, ?, ?)', [sectId, req.user.id, 'member']);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(400).json({ error: '你已在宗门中', code: 'ALREADY_IN_SECT' });
      throw e;
    }
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
    const targetId = Math.floor(Number(req.body?.userId));
    if (!Number.isFinite(targetId) || targetId <= 0) return res.status(400).json({ error: '参数非法' });
    const actor = await sectMemberOf(req.user.id);
    if (!actor || (actor.role !== 'leader' && actor.role !== 'officer')) return res.status(403).json({ error: '无权限' });
    if (targetId === req.user.id) return res.status(400).json({ error: '不能移除自己，请使用退出宗门' });
    const target = await sectMemberOf(targetId);
    if (!target || target.sect_id !== actor.sect_id) return res.status(403).json({ error: '目标不在本宗', code: 'NOT_SAME_SECT' });
    if (target.role === 'leader') return res.status(403).json({ error: '不能移除宗主' });
    if (actor.role === 'officer' && target.role !== 'member') return res.status(403).json({ error: '长老只能移除普通成员' });
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
    const targetId = Math.floor(Number(req.body?.userId));
    const role = String(req.body?.role || '');
    if (!Number.isFinite(targetId) || targetId <= 0) return res.status(400).json({ error: '参数非法' });
    if (role !== 'officer' && role !== 'member') return res.status(400).json({ error: '职位参数非法' });
    const actor = await sectMemberOf(req.user.id);
    if (!actor || actor.role !== 'leader') return res.status(403).json({ error: '仅宗主可任免职位' });
    if (targetId === req.user.id) return res.status(400).json({ error: '宗主职位不可变更，请使用转让宗主' });
    const target = await sectMemberOf(targetId);
    if (!target || target.sect_id !== actor.sect_id) return res.status(403).json({ error: '目标不在本宗' });
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
    const targetId = Math.floor(Number(req.body?.userId));
    if (!Number.isFinite(targetId) || targetId <= 0) return res.status(400).json({ error: '参数非法' });
    const actor = await sectMemberOf(req.user.id);
    if (!actor || actor.role !== 'leader') return res.status(403).json({ error: '仅宗主可转让宗主之位' });
    if (targetId === req.user.id) return res.status(400).json({ error: '不能转让给自己' });
    const target = await sectMemberOf(targetId);
    if (!target || target.sect_id !== actor.sect_id) return res.status(403).json({ error: '目标不在本宗' });
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
    if (!actor || actor.role !== 'leader') return res.status(403).json({ error: '仅宗主可解散宗门' });
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
    const amount = Number(req.body?.amount);
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
    });
  } catch (e: any) {
    console.error('sect contribute error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 领取宗门任务奖励：核验所在宗当日任务 done=1 + sect_task_claims 主键防重 → updatePlayerSave 发灵石
app.post('/api/sect/tasks/claim', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const taskKey = String(req.body?.taskKey || '');
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
    const kind = String(req.body?.kind || '');
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

// 编辑宗门公告：仅宗主（≤200 字；设计稿管理页配套端点）
app.post('/api/sect/notice', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const notice = String(req.body?.notice ?? '').trim().slice(0, 200);
    const actor = await sectMemberOf(req.user.id);
    if (!actor || actor.role !== 'leader') return res.status(403).json({ error: '仅宗主可编辑公告' });
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
