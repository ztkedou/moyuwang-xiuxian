# -*- coding: utf-8 -*-
r"""
srv_patch_activity087.py -- 0.8.7 批次 · T5 限时活动服务端（环 p4_activity087，环主 implEventsSrv）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  不提供 `--out`：`localtest/chain_build.py` 会把上一环产物复制成私有工作副本
  再让本补丁就地改。

覆盖范围（T5 设计案 §2/§3~§6 + 数值表-T5T6 定档）
--------------------------------------------------------------------------
  A1  6 新表 DDL：activity_rank_settled / activity_checkin / activity_token /
      activity_token_daily / event_boss / event_boss_hits（全 IF NOT EXISTS，回滚保留勿删）
      + idx_stats_daily_date（冲榜窗口聚合索引）+ 活动称号 seed（act087_jade）
  A2  ACT_TYPES 扩 4 键：rank_battle / checkin_fest / token_shop / boss_raid
      （target 全 'live'=永不进倍率引擎；actTypeOk//api/events/GM 建场自动放行，GM 零新增）
  A3  C 灵玉阁掉玉挂点 ×3：actDropTokens 只挂 3 个服务端入账点——
      炼丹出炉领取（actApplyGain 入账后）/ 灵田收获（actApplyGain 入账后；
      t10_farm 环先行时该锚即 farmHarvestOne 公共入账点，单收/一键收口径自动一致）/
      离线收益领取（actApplyGain 入账后）。离线预览 /api/offline/report 两处
      actApplyGain 保持裸调用不挂（防双计，门禁断言）。
  A4  actSettleTick 结算器（并列于 rainSettleTick）：内存重入保护 + engine_on 内存镜像
      首行早退 + setInterval(unref) + ★boot-run（停服跨窗口补结算，快照表主键幂等）
      —— A 冲榜快照发奖 / D 万妖档位·排名·击杀·全服四类发奖
  A5  8 新端点：GET /api/activity/rank · GET|POST /api/activity/checkin(/claim) ·
      GET /api/activity/shop · POST /api/activity/shop/exchange ·
      GET /api/eventboss/status · POST /api/eventboss/strike · POST /api/eventboss/talisman
  A6  GM config 写入侧同步 actEngineOn 内存镜像（结算器 kill switch 热更新）

★ 与 t10_farm 环（环 7，先于本环）的入账点耦合
--------------------------------------------------------------------------
灵田挂点 = farmHarvestOne 公共入账点（t10 抽公共原语后的唯一收获入账路径，单收/一键收
口径自动一致）。补丁内置**双形态候选锚**：形态 A = t10 后 farmHarvestOne 内 2 空格缩进的
「回执邮件（尽力而为…」注释（首选，钩在入账成功守卫之后）；形态 B = 0.8.6 单收端点内
4 空格缩进的同一注释行（独立试跑兜底）。两候选必须**恰命中一个**，0 或 2 个命中都 FAIL；
钩子恒在「UPDATE spirit_farm SET harvested = 1」守卫之后（顺序契约断言）。若 implGrotto
后续再改形态，链在此环 FAIL 中止——接线人按实际形态补候选，禁止静默跳过挂点。

★ 业务拒绝一律 400/409，绝不 403
--------------------------------------------------------------------------
客户端 Xc() 把 403 当会话失效强制登出。本补丁新增拒绝一律 400/409/401，
门禁断言 `res.status(403)` 计数与原文逐字相等。

★ 扣费纪律三段式 + 幂等
--------------------------------------------------------------------------
  兑换：守卫式扣玉（balance>=? 单语句）→ 守卫式占限购位（UNIQUE upsert + WHERE 钳）
        → 发放；任一步失败全补偿（退玉/退位/删行），可重试。
  诛妖符：占符位（fun_daily UNIQUE）→ 扣灵石（失败补偿删行）→ 守卫式扣血
          （killed=0 守卫；被他人抢先击杀则退灵石+删行）。
  签到：INSERT OR IGNORE 主键占位 → 直入账（失败补偿删行）。
  免费出手即时灵石恒 0、追加出手即时灵石恒 0（D2：产出全部延后到预算化结算）。

★ EV 红线（数值表-T5T6 §2.5，装配门禁在 localtest/check_srv_087.py 复算）
--------------------------------------------------------------------------
  C1 灵玉阁闭环：r=2 玉/万灵石 × v_max=229788*12/800=3446.8 = 6893.6 ≤ 9000 ⇒ EV ≤ 0.689
  D1 诛妖符：符价=1×境界时薪 ⇒ 3×1h ≥ 档位增量 2h ⇒ EV ≤ 0.67；即时产出=0（结构保证）
  全体：四活动零新增赔率常量；兑换率恒定（C2 无随机）。

★ 数值定档（数值表-T5T6 §1，禁就地调参，只动常量区）
--------------------------------------------------------------------------
  A：参与线 60min；名次档 12/8/5/2/0.5h（n30=max(11,ceil(0.3N))）；两榜合计≤24h（结构封顶）
  B：第 N 天=N/6h；第 7 天 3h；全勤 +3h（COUNT=7 校验）；无补签（B1 结构成立）
  C：r=2 玉/万灵石；日上限 300；袋 100/300/800 玉=1/4/12h；限购 20/10/5；称号 2500 玉；
     装饰 SKU 砍（C-5：无承载系统整行砍）
  D：血量系数 20（=113,906,250）；免费 3/日；诛妖符 +2/日×1×时薪；档位线 4/12/24 次
     →1/2/4h；排名 1/2~3/4~10 →12/8/5h；击杀 +2h（chronicle【诛妖】）；全服 +0.5h；休战 2 天
"""
import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ A1 六新表 DDL（挂在 activity_rain_state 索引之后）

A1_OLD = "  db.run(`CREATE INDEX IF NOT EXISTS idx_rain_state_date ON activity_rain_state(date)`);"

A1_NEW = A1_OLD + """
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
  db.run(`CREATE INDEX IF NOT EXISTS idx_stats_daily_date ON stats_daily(date)`);
  // [act087] 活动限定称号 seed（灵玉阁 2500 玉兑换物；grantTitleBySource 按 source 定位，OR IGNORE 重启幂等）
  db.run(`INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES ('灵玉仙客', '{"expRate":0.01}', 'act087_jade')`);"""

# ============================================================ A2 ACT_TYPES 扩 4 键（target 全 'live'）

A2_OLD = """  stones2_live: { name: '\\u5929\\u964d\\u7075\\u96e8', target: 'live', desc: '\\u5728\\u7ebf\\u4fee\\u884c\\uff1a\\u6bcf\\u6ee1 1 \\u5c0f\\u65f6\\u7ed3\\u7b97\\u4e00\\u5c01\\u7075\\u77f3\\u90ae\\u4ef6\\uff08\\u6309\\u5883\\u754c\\u6298\\u7b97\\uff09' },"""

A2_NEW = A2_OLD + """
  // [act087] 0.8.7 T5 四活动：target 全 'live'（actMultiplierFor 只认 'exp'/'stones'，永不命中
  // ⇒ 新玩法天然不污染倍率引擎，stones2_live 先例）。进目录后 actTypeOk 白名单 / /api/events
  // 展示 / GM 建场播报全部自动放行，GM 零新增。
  rank_battle:  { name: '仙途冲榜',   target: 'live', desc: '七天双榜竞速：灵石获取榜与讨伐击杀榜，按境界时薪折算发奖' },
  checkin_fest: { name: '仙缘七日礼', target: 'live', desc: '节庆七日签到：逐日递增灵石，全勤另赠厚礼' },
  token_shop:   { name: '灵玉阁',     target: 'live', desc: '活动期服务端结算掉落灵玉，灵玉阁固定率兑换限时好礼' },
  boss_raid:    { name: '万妖巢穴',   target: 'live', desc: '全服共讨限时大妖：出手得讨伐积分，结算按档位与排名发奖' },"""

# ============================================================ A3 掉玉挂点 ×3（只挂入账点，预览两处不挂）

A3A_OLD = "    res.json({ ok: true, slot, pill, yieldStones, pillsGained, eventMults: { exp: evMult.expMult, stones: evMult.stonesMult } });"
A3A_NEW = """    // [act087] C 灵玉阁掉玉挂点（入账点：炼丹出炉化灵灵石已确认发放；活动不活跃时零开销）
    if (yieldStones > 0) actDropTokens(userId, yieldStones, now).catch((e: any) => console.error('act drop tokens (alchemy) error:', e?.message || e));
""" + A3A_OLD

A3C_OLD = "    // 3) 回执邮件（奖励已入档，邮件仅为回执；发送失败不影响领取，只记日志）；附带突破差值提示"
A3C_NEW = """    // [act087] C 灵玉阁掉玉挂点（入账点：离线收益入账成功后；/api/offline/report 预览两处
    // actApplyGain 保持裸调用不挂——挂预览必双计，门禁断言）
    if (applied.stonesGain > 0) actDropTokens(userId, applied.stonesGain, nowMs).catch((e: any) => console.error('act drop tokens (offline) error:', e?.message || e));
""" + A3C_OLD

# ★ A3b 灵田挂点双形态锚（t10_farm 环 7 先行 ⇒ farmHarvestOne 公共入账点为首选形态；
#   v286 单收端点形态仅作独立试跑兜底。两形态都把钩子放在「入账成功守卫」之后）：
#   形态 A（t10 后）：farmHarvestOne 内 2 空格缩进的回执邮件注释 + opts?.mail 分支
#   形态 B（v286 原样）：单收端点内 4 空格缩进的同一注释行
A3B_CANDIDATES = [
    ("  // 回执邮件（尽力而为：收益已实际入档，邮件失败仅记日志不影响收获结果）",
     """  // [act087] C 灵玉阁掉玉挂点（farmHarvestOne 公共入账点：单收/一键收口径自动一致；409 落败方不掉玉）
  if (gain.stones > 0) actDropTokens(userId, gain.stones, now).catch((e: any) => console.error('act drop tokens (farm) error:', e?.message || e));
"""),
    ("    // 回执邮件（尽力而为：收益已实际入档，邮件失败仅记日志不影响收获结果）",
     """    // [act087] C 灵玉阁掉玉挂点（入账点：灵田收获入账成功后）
    if (gain.stones > 0) actDropTokens(userId, gain.stones, now).catch((e: any) => console.error('act drop tokens (farm) error:', e?.message || e));
"""),
]

# ============================================================ A6 GM config 写入侧镜像

A6_OLD = "    rainEngineOn = on === '1';"
A6_NEW = """    rainEngineOn = on === '1';
    actEngineOn = on === '1'; // [act087] 结算器共用同一全局开关（内存镜像，settle tick 首行早退）"""

# ============================================================ A4/A5 结算器 + 8 端点（挂在 rain boot 块之后）

A7_OLD = """dbGet("SELECT value FROM activity_config WHERE key = 'engine_on'")
  .then((r: any) => { rainEngineOn = String(r && r.value) === '1'; })
  .catch(() => {});"""

A7_NEW = A7_OLD + """

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
const ACT_TOKEN_RATE_PER_10K = 2;                  // C 掉玉率 r=2 玉/万灵石结算
const ACT_TOKEN_DAILY_CAP = 300;                   // C 掉玉日上限（=150 万灵石结算量/日）
const ACT_SHOP_ITEMS: Array<{ id: string; name: string; price: number; limit: number; hours?: number; titleSource?: string }> = [
  { id: 'bag_s',      name: '灵石袋·小',     price: 100,  limit: 20, hours: 1 },
  { id: 'bag_m',      name: '灵石袋·中',     price: 300,  limit: 10, hours: 4 },
  { id: 'bag_l',      name: '灵石袋·大',     price: 800,  limit: 5,  hours: 12 },
  { id: 'title_jade', name: '称号·灵玉仙客', price: 2500, limit: 1,  titleSource: 'act087_jade' },
]; // 兑换率恒定零随机（C2，零新增赔率常量）；装饰 SKU 无承载系统整行砍（数值表-T5T6 C-5）
const ACT_BOSS_FREE_STRIKES = 3;                   // D 免费出手 3 次/日（fun_daily kind='raid'）
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
    const ev = await actEventOf(req.query?.eventId, 'checkin_fest');
    if (!ev) return res.status(400).json({ error: 'eventId 非法' });
    const now = Date.now();
    const dayNo = Math.floor((now - Number(ev.start_at)) / 86400000) + 1;
    const today = dayNo < 1 ? 0 : Math.min(ACT_CHECKIN_DAYS, dayNo);
    const hourly = await actHourlyOf(userId);
    const claimedRows = await dbAll('SELECT day FROM activity_checkin WHERE player_id = ? AND event_id = ?', [userId, Number(ev.id)]);
    const claimed = new Set<number>((claimedRows || []).map((x: any) => Math.floor(Number(x.day) || 0)));
    const days: any[] = [];
    let missedAny = false;
    for (let d = 1; d <= ACT_CHECKIN_DAYS; d++) {
      const isClaimed = claimed.has(d);
      const missed = d < today && !isClaimed;
      if (missed) missedAny = true;
      days.push({ day: d, reward: Math.floor(hourly * (d < 7 ? d / 6 : 3)), claimed: isClaimed, missed });
    }
    const active = actIsActive(ev, now);
    res.json({
      eventId: Number(ev.id),
      days,
      canClaim: active && (await actEngineEnabled()) && today >= 1 && !claimed.has(today),
      today,
      fullAttendable: active && today >= 1 && !missedAny,
    });
  } catch (e: any) {
    console.error('act checkin error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ── B 仙缘七日礼：POST /api/activity/checkin/claim {eventId} ──
// 主键 INSERT OR IGNORE 占位 → 服务端重算 day（不信任客户端）→ updatePlayerSave 直入账
// （不走 mail，零邮件量；失败补偿删行可重试）。断签不补：只能领「今天」，前期作废。
app.post('/api/activity/checkin/claim', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `act:ckc:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const ev = await actEventOf(req.body?.eventId, 'checkin_fest');
    if (!ev) return res.status(400).json({ error: 'eventId 非法' });
    if (!(await actEngineEnabled())) return res.status(409).json({ error: '活动引擎暂未开启' });
    const now = Date.now();
    if (!actIsActive(ev, now)) {
      return res.status(409).json({ error: now < Number(ev.start_at) ? '活动尚未开启' : '活动已结束' });
    }
    const dayNo = Math.floor((now - Number(ev.start_at)) / 86400000) + 1;
    const day = Math.min(ACT_CHECKIN_DAYS, Math.max(1, dayNo));
    const ins = await dbRun(
      'INSERT OR IGNORE INTO activity_checkin (player_id, event_id, day, claimed_at) VALUES (?, ?, ?, ?)',
      [userId, Number(ev.id), day, now]);
    if (!ins.changes) return res.status(409).json({ error: '今日已签到，明日再来' });
    const hourly = await actHourlyOf(userId);
    let reward = Math.floor(hourly * (day < 7 ? day / 6 : 3));
    if (day === 7) {
      const c = await dbGet('SELECT COUNT(*) AS c FROM activity_checkin WHERE player_id = ? AND event_id = ?', [userId, Number(ev.id)]);
      if (Number(c && c.c) === ACT_CHECKIN_DAYS) reward += Math.floor(hourly * 3); // 全勤奖（COUNT=7 校验）
    }
    let credited = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') return;
      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + reward;
      credited = true;
    });
    if (!paid.ok || !credited) {
      // 补偿删行可重试（占位已撤，直入账失败不吞签到机会）
      await dbRun('DELETE FROM activity_checkin WHERE player_id = ? AND event_id = ? AND day = ?', [userId, Number(ev.id), day]).catch(() => { });
      return res.status(409).json({ error: paid.error === 'No save found' ? '请先进游戏创建角色' : '领取失败，请重试' });
    }
    res.json({ ok: true, day, reward });
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
    res.json({ balance, window, items, engineOn: await actEngineEnabled() });
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
    res.json({ ok: true, balance: Math.max(0, Math.floor(Number(balRow && balRow.balance) || 0)), gained, item: item.id, title });
  } catch (e: any) {
    console.error('act exchange error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ── D 万妖巢穴：lazy 建场（同 wbEnsure 口径；血量=WB_HP_BASE×1.5^maxRealm×20）──
async function actBossEnsure(eventId: number): Promise<any> {
  let row = await dbGet('SELECT * FROM event_boss WHERE event_id = ?', [eventId]).catch(() => null);
  if (row) return row;
  const top = await dbGet('SELECT MAX(realm_index) AS ri FROM rankings').catch(() => null);
  const mult = Math.pow(1.5, Math.min(20, Math.max(0, Number(top && top.ri) || 0)));
  const hp = Math.floor(WB_HP_BASE * mult * ACT_BOSS_HP_CYCLE);
  await dbRun('INSERT OR IGNORE INTO event_boss (event_id, hp_max, hp_cur) VALUES (?, ?, ?)', [eventId, hp, hp]).catch(() => { });
  return await dbGet('SELECT * FROM event_boss WHERE event_id = ?', [eventId]);
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
// 出手公共体：守卫式扣血 + 记分 + 击杀播报（免费/追加同口径；即时灵石恒 0）
async function actBossHitOnce(userId: number, eventId: number, nowMs: number): Promise<{ score: number; total: number; killed: boolean; hpCur: number }> {
  const cpRow = await dbGet('SELECT combat_power FROM rankings WHERE user_id = ?', [userId]).catch(() => null);
  const cp = Number(cpRow && cpRow.combat_power) || 100;
  const score = Math.max(1, Math.floor(cp * 2 * (0.8 + Math.random() * 0.4)));
  // 守卫式扣血（killed=0 守卫：SET 表达式全按旧值求值，kill 判定与回写一次完成）
  const upd = await dbRun(
    `UPDATE event_boss SET
       hp_cur = MAX(0, hp_cur - ?),
       killed = CASE WHEN hp_cur - ? <= 0 THEN 1 ELSE killed END,
       killer_id = CASE WHEN hp_cur - ? <= 0 THEN ? ELSE killer_id END,
       killed_at = CASE WHEN hp_cur - ? <= 0 THEN ? ELSE killed_at END
     WHERE event_id = ? AND killed = 0`,
    [score, score, score, userId, score, nowMs, eventId]);
  if (!upd.changes) throw new Error('ACT_BOSS_KILLED_RACE');
  // 记分（PK 幂等 upsert；不发放任何即时灵石——D2 结构保证）
  await dbRun(
    `INSERT INTO event_boss_hits (event_id, user_id, score, strikes) VALUES (?, ?, ?, 1)
     ON CONFLICT(event_id, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1`,
    [eventId, userId, score]);
  const after = await dbGet('SELECT hp_cur, killed, killer_id FROM event_boss WHERE event_id = ?', [eventId]);
  const mine = await dbGet('SELECT score FROM event_boss_hits WHERE event_id = ? AND user_id = ?', [eventId, userId]);
  const killed = Number(after && after.killed) === 1;
  if (killed && Number(after && after.killer_id) === userId) {
    const kn = await actNameOf(userId);
    logChronicle(userId, kn, `【诛妖】「${String((await dbGet('SELECT name FROM events WHERE id = ?', [eventId]).catch(() => null))?.name || '万妖')}」伏诛，最后一击出自「${kn}」之手，全服同贺`);
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
    const usedFree = await actFunUsedToday(userId, 'raid');
    const usedTal = await actFunUsedToday(userId, 'raid_talisman');
    const killed = Number(boss.killed) === 1;
    res.json({
      eventId: Number(ev.id),
      hpMax: Math.max(0, Math.floor(Number(boss.hp_max) || 0)),
      hpCur: Math.max(0, Math.floor(Number(boss.hp_cur) || 0)),
      killed,
      killerName: killed ? await actNameOf(boss.killer_id) : null,
      myScore: Math.max(0, Math.floor(Number(mine && mine.score) || 0)),
      myStrikes: Math.max(0, Math.floor(Number(mine && mine.strikes) || 0)),
      freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - usedFree),
      talismanLeft: Math.max(0, ACT_BOSS_TALISMAN_DAILY - usedTal),
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
    const used = await actFunUsedToday(userId, 'raid');
    if (used >= ACT_BOSS_FREE_STRIKES) {
      return res.status(409).json({ error: `今日免费出手已用尽（${ACT_BOSS_FREE_STRIKES} 次），可用诛妖符追加` });
    }
    // ① 占次数位（fun_daily UNIQUE 单语句原子）
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun(
        'INSERT INTO fun_daily (player_id, date, kind, count, cost, payout, detail, created_at) VALUES (?, ?, ?, ?, 0, 0, ?, ?)',
        [userId, utcDateStr(), 'raid', used + 1, JSON.stringify({ eventId: Number(ev.id) }), now]);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '手速太快，请再试一次' });
      throw e;
    }
    // ② 守卫式扣血 + ③ 记分（被他人抢先击杀则补偿撤位）
    let hit: { score: number; total: number; killed: boolean; hpCur: number };
    try {
      hit = await actBossHitOnce(userId, Number(ev.id), now);
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
      freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - used - 1),
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
    const used = await actFunUsedToday(userId, 'raid_talisman');
    if (used >= ACT_BOSS_TALISMAN_DAILY) {
      return res.status(409).json({ error: `今日诛妖符已用尽（${ACT_BOSS_TALISMAN_DAILY} 张）` });
    }
    const price = await actHourlyOf(userId); // 符价=1×境界时薪
    // ① 占符位
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun(
        'INSERT INTO fun_daily (player_id, date, kind, count, cost, payout, detail, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)',
        [userId, utcDateStr(), 'raid_talisman', used + 1, price, JSON.stringify({ eventId: Number(ev.id) }), now]);
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
      hit = await actBossHitOnce(userId, Number(ev.id), now);
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
      talismanLeft: Math.max(0, ACT_BOSS_TALISMAN_DAILY - used - 1),
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
        `「${String(ev.name || '仙途冲榜')}」落幕！你以 ${score} 的成绩位居${boardName}榜第 ${i + 1} 名（${tierName}），奖励灵石 ×${reward} 已随信附上。\n\n下期冲榜，再会！`,
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
  if (!actEngineOn) return; // engine off: first-line early return, zero DB work
  actSettleTick().catch((e: any) => console.error('act tick error:', e?.message || e));
}, ACT_TICK_MS).unref();
// [act087] Boot: mirror engine_on for the activity settler + boot-run once — a restart that
// spanned an event window end must still settle (rank/boss snapshots are PK-idempotent).
dbGet("SELECT value FROM activity_config WHERE key = 'engine_on'")
  .then((r: any) => { actEngineOn = String(r && r.value) === '1'; return actSettleTick(); })
  .catch((e: any) => console.error('act boot settle error:', e?.message || e));"""

# ============================================================ EDITS

EDITS = [
    ("A1 六新表 DDL", A1_OLD, A1_NEW),
    ("A2 ACT_TYPES 扩 4 键", A2_OLD, A2_NEW),
    ("A3a 炼丹掉玉挂点", A3A_OLD, A3A_NEW),
    # A3b 灵田挂点：双形态候选，main() 内动态择一（见 A3B_CANDIDATES）
    ("A3c 离线掉玉挂点", A3C_OLD, A3C_NEW),
    ("A6 GM config 镜像", A6_OLD, A6_NEW),
    ("A4/A5 结算器+8 端点", A7_OLD, A7_NEW),
]

REQUIRES = [
    ("stones2_live: { name:", 1, "actcore 类型目录（环序：任何前环不得改动 ACT_TYPES）"),
    ("idx_rain_state_date ON activity_rain_state", 1, "DDL 挂点"),
    ("actApplyGain(", 8, "T5 挂点区纪律：定义 1 + 调用 7（:5662×1/:5813×2/:8270×2/:8333×2）——t10_farm 环不得增删"),
    ("res.status(403)", 22, "T7 前基线：res 形式 403 恰 22 处（0.8.6 定版口径；t7_sect 环 9 才降到 11，本环输入必须仍是 22）"),
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 链序依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 2) 幂等
    if "activity_rank_settled" in src or "ACT_SHOP_ITEMS" in src:
        fail("source looks already patched（已存在 activity_rank_settled / ACT_SHOP_ITEMS）")

    # 3) 锚点计数（锚点用产物真实字节形态；fun086 同款单次替换契约）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:120]))
        if old == new:
            fail("%s old == new" % name)
    # A3b 灵田挂点：双形态候选择一（t10 后形态优先）；0 或 >1 个候选命中都算 FAIL
    hits = [(old, new) for old, new in A3B_CANDIDATES if src.count(old) == 1]
    if len(hits) != 1:
        fail("A3b 灵田挂点候选命中 %d 个（期望恰 1）：%s"
             % (len(hits), [old[:60] for old, _ in A3B_CANDIDATES]))
    a3b_old, a3b_new = hits[0]
    if src.count(a3b_old) != 1:
        fail("A3b 灵田挂点锚点出现 %d 次（期望 1）" % src.count(a3b_old))

    # 4) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)
    out = out.replace(a3b_old, a3b_new, 1)

    # 5) 门禁
    gates = [
        # ---- A1 六新表 ----
        ('A1 activity_rank_settled',   'CREATE TABLE IF NOT EXISTS activity_rank_settled', 1, None),
        ('A1 activity_checkin',        'CREATE TABLE IF NOT EXISTS activity_checkin', 1, None),
        ('A1 activity_token',          'CREATE TABLE IF NOT EXISTS activity_token ', 1, None),
        ('A1 activity_token_daily',    'CREATE TABLE IF NOT EXISTS activity_token_daily', 1, None),
        ('A1 event_boss 主表',          'CREATE TABLE IF NOT EXISTS event_boss ', 1, None),
        ('A1 event_boss_hits',         'CREATE TABLE IF NOT EXISTS event_boss_hits', 1, None),
        ('A1 event_boss killed_at',    'killed_at INTEGER', 1, None),
        ('A1 聚合索引',                 'CREATE INDEX IF NOT EXISTS idx_stats_daily_date ON stats_daily(date)', 1, None),
        ('A1 活动称号 seed',            "VALUES ('灵玉仙客', '{\"expRate\":0.01}', 'act087_jade')", 1, None),
        # ---- A2 类型目录 ----
        ('A2 rank_battle 进目录',       "rank_battle:  { name: '仙途冲榜'", 1, None),
        ('A2 checkin_fest 进目录',      "checkin_fest: { name: '仙缘七日礼'", 1, None),
        ('A2 token_shop 进目录',        "token_shop:   { name: '灵玉阁'", 1, None),
        ('A2 boss_raid 进目录',         "boss_raid:    { name: '万妖巢穴'", 1, None),
        # ---- A3 挂点 ----
        ('A3 actDropTokens 总量=1 定义+3 挂点', 'actDropTokens(', 4, None),
        ('A3 炼丹挂点',                 "actDropTokens(userId, yieldStones, now)", 1, None),
        ('A3 灵田挂点',                 "actDropTokens(userId, gain.stones, now)", 1, None),
        ('A3 离线挂点',                 "actDropTokens(userId, applied.stonesGain, nowMs)", 1, None),
        # 预览两处必须保持裸调用（防双计）：预览段不含挂点串
        ('A3 actApplyGain 总量恒 8',     'actApplyGain(', 8, None),
        # ---- A4 结算器 ----
        ('A4 actSettleTick 定义',       'async function actSettleTick', 1, None),
        ('A4 boot-run',                'return actSettleTick()', 1, None),
        ('A4 setInterval',             "actSettleTick().catch((e: any) => console.error('act tick error", 1, None),
        ('A4 重入保护',                 'let actSettling = false;', 1, None),
        ('A4 内存镜像首行早退',          "if (!actEngineOn) return; // engine off: first-line early return, zero DB work", 2, None),
        ('A4 GM config 双镜像',         "actEngineOn = on === '1';", 1, None),
        # ---- A5 端点 ----
        ('A5 GET /api/activity/rank', "app.get('/api/activity/rank'", 1, None),
        ('A5 GET /api/activity/checkin', "app.get('/api/activity/checkin'", 1, None),
        ('A5 POST /api/activity/checkin/claim', "app.post('/api/activity/checkin/claim'", 1, None),
        ('A5 GET /api/activity/shop', "app.get('/api/activity/shop'", 1, None),
        ('A5 POST /api/activity/shop/exchange', "app.post('/api/activity/shop/exchange'", 1, None),
        ('A5 GET /api/eventboss/status', "app.get('/api/eventboss/status'", 1, None),
        ('A5 POST /api/eventboss/strike', "app.post('/api/eventboss/strike'", 1, None),
        ('A5 POST /api/eventboss/talisman', "app.post('/api/eventboss/talisman'", 1, None),
        # ---- 数值定档（只动常量区，禁就地调参）----
        ('C 掉玉率 r=2',               'const ACT_TOKEN_RATE_PER_10K = 2;', 1, None),
        ('C 日上限 300',               'const ACT_TOKEN_DAILY_CAP = 300;', 1, None),
        ('C 大袋 800 玉',               "price: 800,  limit: 5,  hours: 12", 1, None),
        ('C 限购 20/10/5',             'limit: 20', 1, None),
        ('D 免费出手 3 次',             'const ACT_BOSS_FREE_STRIKES = 3;', 1, None),
        ('D 诛妖符 2 张',               'const ACT_BOSS_TALISMAN_DAILY = 2;', 1, None),
        ('D 血量期数系数 20',           'const ACT_BOSS_HP_CYCLE = 20;', 1, None),
        ('D 档位线 4/12/24',           '{ min: 24, hours: 4 }, { min: 12, hours: 2 }, { min: 4, hours: 1 },', 1, None),
        ('D 排名 12/8/5',              'const ACT_BOSS_RANK_HOURS = [12, 8, 5];', 1, None),
        ('A 参与线 60 分钟',            'const ACT_RANK_MIN_MINUTES = 60;', 1, None),
        ('B 每期 7 天',                 'const ACT_CHECKIN_DAYS = 7;', 1, None),
        # ---- 403 语义红线 ----
        ('403 计数与原文逐字相等（本环不新增；t7_sect 环 9 才降到 11）', 'res.status(403)', 22, None),
    ]
    for name, needle, want, _ in gates:
        n = out.count(needle)
        if want is not None and n != want:
            fail("门禁 %s：%r 出现 %d 次（期望 %d）" % (name, needle[:80], n, want))

    # 5b) ★ 顺序契约：掉玉三挂点必须位于各自「入账成功守卫」之后（防 409/失败方双计）
    #     炼丹/离线 = 端点段内断言；灵田 = 全局位置断言（t10 后钩子在 farmHarvestOne 公共
    #     原语内，端点段被 /api/farm/unlock 截断，段内断言不适用）
    p_hook_farm = out.find("actDropTokens(userId, gain.stones, now)")
    p_claim_farm = out.find("const claim = await dbRun('UPDATE spirit_farm SET harvested = 1")
    if p_hook_farm < 0 or p_claim_farm < 0:
        fail("顺序契约校验：灵田挂点(%d) 或收获守卫(%d) 缺失" % (p_hook_farm, p_claim_farm))
    if p_hook_farm < p_claim_farm:
        fail("顺序契约被破坏：灵田掉玉挂点早于守卫式收获标记 ⇒ 并发落败方也会掉玉（双计）")
    print("  [OK] 顺序契约：灵田挂点位于 farmHarvestOne 守卫式收获标记之后（offset %d > %d）"
          % (p_hook_farm, p_claim_farm))
    pairs = [
        ("app.post('/api/alchemy/claim'", "actDropTokens(userId, yieldStones, now)",
         "if (!del.changes) return res.status(409).json({ error: '该炉已领取' });"),
        ("app.post('/api/offline/claim'", "actDropTokens(userId, applied.stonesGain, nowMs)",
         "if (!mark.changes) return res.status(409).json({ error: '该段离线收益已领取' });"),
    ]
    for ep, hook, guard in pairs:
        i = out.find(ep)
        if i < 0:
            fail("顺序契约校验：找不到端点 %s" % ep)
        j = out.find("app.get(", i + len(ep))
        k = out.find("app.post(", i + len(ep))
        ends = [x for x in (j, k) if x > 0]
        seg = out[i:min(ends) if ends else len(out)]
        p_hook = seg.find(hook)
        p_guard = seg.find(guard)
        if p_hook < 0 or p_guard < 0:
            fail("顺序契约校验：%s 缺少挂点(%d) 或入账守卫(%d)" % (ep, p_hook, p_guard))
        if p_hook < p_guard:
            fail("顺序契约被破坏：%s 掉玉挂点早于入账守卫 ⇒ 失败方也会掉玉（双计）" % ep)
    print("  [OK] 顺序契约：3 个掉玉挂点均在各自入账守卫之后（409 落败方不掉玉）")

    # 5c) 离线预览两处保持裸调用（防双计）：/api/offline/report 段内禁止出现 actDropTokens
    i = out.find("app.get('/api/offline/report'")
    j = out.find("app.post('/api/offline/claim'", i)
    seg = out[i:j if j > 0 else len(out)]
    if 'actDropTokens' in seg:
        fail("防双计门禁：/api/offline/report 预览段出现了掉玉挂点（挂预览必双计）")
    print("  [OK] 防双计：离线预览段保持裸调用，未挂掉玉")

    # 6) 往返自证：把每个 new 换回 old 必须逐字复现原文
    back = out
    all_edits = EDITS + [("A3b 灵田掉玉挂点", a3b_old, a3b_new)]
    for name, old, new in all_edits:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".act087-", suffix=".tmp")
    try:
        with io.open(fd, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print("  已原子写回 %s" % src_path)


if __name__ == "__main__":
    main()
