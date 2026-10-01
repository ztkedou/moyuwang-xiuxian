# -*- coding: utf-8 -*-
r"""
srv_patch_fun086.py -- 0.8.6 批次 · 服务端（每日行乐四玩法 + 奇遇抽奖多样化）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  不提供 `--out`：`localtest/chain_build.py` 会把上一环产物复制成私有工作副本
  再让本补丁就地改。

覆盖范围
--------------------------------------------------------------------------
  S1  新表 fun_daily（掷骰/一签/翻牌/茶馆 的每日次数与流水）
  S2  茶馆数值加大（500~50000）+ 每日 3 注 + 茶运（修为/彩头，不进灵石经济）
  S3  /api/teahouse/today 下发 fun 状态（客户端一次请求驱动整个行乐面板）
  S4  /api/teahouse/bet 支持每日 3 注、同侧追加
  S5  三个新端点：POST /api/fun/dice | /api/fun/sign | /api/fun/card
  S6~S10 奇遇抽奖：ADVENTURE_TIERS 定值 → 区间；事件池 18 → 34 条；新增抽奖券/额外珍宝
  S11 adventures 表加 tickets / bonus_text 两列（PRAGMA 迁移，与既有 linuxdo_id 同款）

★ 业务拒绝一律 400/409，绝不 403
--------------------------------------------------------------------------
客户端 `Xc()`（bundle @594262）把 401/403 一律当**会话失效**并强制登出玩家。
所以「灵石不足 / 今日次数已用尽」全部用 409，与既有 /teahouse/bet、/adventure/draw 同款。

★ 全或无的顺序契约（本批自测暴露并修掉的真实缺陷）
--------------------------------------------------------------------------
四个扣费端点一律 **先占次数位（fun_daily 的 UNIQUE(player_id,date,kind,count)
单语句原子）→ 再扣灵石 → 最后落注池/派彩**，扣款失败则补偿删行。
若反过来（先扣款后占位），并发双击时两请求都读到 used=0，都能扣款，
但只有一个能插进 count=1，另一个吃 UNIQUE 回 409 —— **被白扣一次注额，拿不到任何服务**。

茶馆还有第二层：注池 teahouse_bets 的「追加同侧」必须写成**单条 ON CONFLICT**，
夹在「占次数位」与「扣款」之间。若写成「读 dup → 分支 INSERT/UPDATE」，
并发下两请求都读到 dup=null，各自 INSERT，后到者吃 teahouse_bets 的 UNIQUE
→ 未捕获异常直接 500，而它已被扣款且注额不在池里 = 无对价扣款。
（两者都是 0.8.6 沙盒并发反向对照**实测复现**出来的，不是推演。）

main() 末尾有位置断言（ORDER_CONTRACT ×2）把这两条契约钉死，不依赖人工 review。

★ 期望值（EV）红线：任何玩法 EV 必须 ≤ 1，否则 = 无限刷灵石漏洞
--------------------------------------------------------------------------
  茶馆竞猜   中奖 50%（胜负由日期哈希定），赔率 1.9            ⇒ EV 0.95
  掷骰大/小  11-18 共 216 组合中 108 种，赔率 1.95              ⇒ EV 0.975
  掷骰豹子   三同 6/216 = 2.78%，赔率 25                        ⇒ EV 0.694
  灵石翻牌   三张牌 4500/1200/0 等概率，成本 2000               ⇒ EV 1900/2000 = 0.95
  每日一签   免费但有每日 1 次上限（不构成无限 faucet）
所以本批的「加大」只落在**注额区间**与**每日次数**，赔率一律不抬。
"""
import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ S1 新表

S1_OLD = """  db.run(`CREATE TABLE IF NOT EXISTS teahouse_bets (
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
  )`);"""

S1_NEW = S1_OLD + """
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
  db.run(`CREATE INDEX IF NOT EXISTS idx_fun_daily_player ON fun_daily(player_id, date)`);"""

# ============================================================ S2a 常量

S2A_OLD = "const TEA_MIN_BET = 100, TEA_MAX_BET = 10000, TEA_PAYOUT = 1.9, TEA_OPEN_UTC = 13;"
S2A_NEW = ("const TEA_MIN_BET = 500, TEA_MAX_BET = 50000, TEA_PAYOUT = 1.9, TEA_OPEN_UTC = 13;\n"
           "const TEA_MAX_BETS = 3; // 0.8.6：每日最多下注 3 次（首注 INSERT，其后同侧追加，累计不超 3×上限）")

# ============================================================ S2b 行乐常量与纯函数

S2B_OLD = "const GREET_STONES_BASE = 200;"

S2B_NEW = S2B_OLD + """

// ─────────────────────────────────────────────────────────
// 0.8.6 每日行乐：掷骰比大小 / 每日一签 / 灵石翻牌（+ 茶馆茶运）
// 设计红线：任何玩法 EV ≤ 1（见本文件顶部注释）。免费玩法一律设每日次数上限。
// ─────────────────────────────────────────────────────────
const FUN_DICE_DAILY = 3;
const FUN_DICE_MIN = 1000, FUN_DICE_MAX = 20000;
const FUN_DICE_PAY = 1.95, FUN_DICE_TRIPLE_PAY = 25;
const FUN_SIGN_DAILY = 1;
const FUN_SIGN_BASE = 500; // 一签灵石底数（再乘 realmMultOf 与签档倍率）
const FUN_CARD_DAILY = 2, FUN_CARD_COST = 2000;
const FUN_CARD_PAYS = [4500, 1200, 0];
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
  { key: 'ss', name: '上上签', weight: 10, expRate: 0.020, stonesRate: 4.0, ticketChance: 0.30,
    texts: ['紫气东来，道基天成。', '云开见月，仙缘自来。', '一念通玄，百脉俱畅。', '天光垂照，此签大吉。'] },
  { key: 's', name: '上签', weight: 30, expRate: 0.010, stonesRate: 2.4, ticketChance: 0.10,
    texts: ['清风入怀，修行顺遂。', '溪山有约，前路可期。', '小有际遇，宜静心守拙。', '云淡风轻，一步一进。'] },
  { key: 'm', name: '中签', weight: 45, expRate: 0.005, stonesRate: 1.4, ticketChance: 0.02,
    texts: ['不咸不淡，稳中有进。', '行路平平，守常即可。', '无大吉亦无大凶。', '日常如常，即是好签。'] },
  { key: 'x', name: '下签', weight: 15, expRate: 0.002, stonesRate: 0.7, ticketChance: 0,
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
}"""

# ============================================================ S2c 结算：茶运

S2C_OLD = """    const payout = won ? Math.floor(Number(b.stones) * payMult) : 0;
    await dbRun('UPDATE teahouse_bets SET won = ?, payout = ? WHERE id = ?', [won, payout, b.id]);
    if (payout > 0) {
      await updatePlayerSave(Number(b.user_id), (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + payout; });
    }"""

S2C_NEW = """    const payout = won ? Math.floor(Number(b.stones) * payMult) : 0;
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
    }"""

S2D_OLD = "  if (best && Number(best.payout) >= 5000) {"
S2D_NEW = "  if (best && Number(best.payout) >= 50000) {"

# ============================================================ S3 /api/teahouse/today

S3_OLD = """    const open = new Date().getUTCHours() < TEA_OPEN_UTC;
    res.json({
      now: Date.now(), date: today, topic: t, open,
      closesAtUtcHour: TEA_OPEN_UTC, payoutMult: TEA_PAYOUT,
      minBet: TEA_MIN_BET, maxBet: TEA_MAX_BET,
      myBet: mine ? { side: Number(mine.side), stones: Number(mine.stones), won: mine.won == null ? null : Number(mine.won), payout: mine.payout == null ? null : Number(mine.payout) } : null,
      pool: (pool || []).map((x: any) => ({ side: Number(x.side), bets: Number(x.n), stones: Number(x.s) || 0 })),
    });"""

S3_NEW = """    const open = new Date().getUTCHours() < TEA_OPEN_UTC;
    const luck = teaLuckOf(today);
    const myTimes = await dbGet('SELECT COALESCE(MAX(count), 0) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, today, 'tea']);
    const times = Math.max(0, Number(myTimes?.c) || 0);
    const [diceRows, signRow, cardRow, diceHist] = await Promise.all([
      dbGet('SELECT COUNT(*) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, today, 'dice']),
      dbGet('SELECT detail, payout, cost FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ? ORDER BY count DESC LIMIT 1', [userId, today, 'sign']),
      dbGet('SELECT COUNT(*) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, today, 'card']),
      dbAll('SELECT count, cost, payout, detail FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ? ORDER BY count DESC LIMIT ?', [userId, today, 'dice', 10]),
    ]);
    const signToday = signRow ? (() => {
      try { return JSON.parse(String(signRow.detail || '{}')); } catch { return null; }
    })() : null;
    res.json({
      now: Date.now(), date: today, topic: t, open,
      closesAtUtcHour: TEA_OPEN_UTC, payoutMult: TEA_PAYOUT,
      minBet: TEA_MIN_BET, maxBet: TEA_MAX_BET, maxTimes: TEA_MAX_BETS,
      luck,
      myBet: mine ? { side: Number(mine.side), stones: Number(mine.stones), won: mine.won == null ? null : Number(mine.won), payout: mine.payout == null ? null : Number(mine.payout), times } : null,
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
    });"""

# ============================================================ S4 /api/teahouse/bet（每日 3 注）

S4_OLD = """    const stones = Math.floor(asNum(req.body?.stones));
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
    res.json({ ok: true, side, stones });"""

S4_NEW = """    const stones = Math.floor(asNum(req.body?.stones));
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
    res.json({ ok: true, side, stones, times: used + 1, maxTimes: TEA_MAX_BETS });"""

# ============================================================ S5 三个新端点

S5_OLD = """// ── 世界妖兽 ──"""

S5_NEW = """// ─────────────────────────────────────────────────────────
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
    if (!(pick >= 0 && pick <= 2)) return res.status(400).json({ error: '只能翻 1 / 2 / 3 号牌' });
    const cnt: any = await dbGet('SELECT COUNT(*) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, today, 'card']);
    const used = Math.max(0, Number(cnt?.c) || 0);
    if (used >= FUN_CARD_DAILY) return res.status(409).json({ error: `今日已翻 ${FUN_CARD_DAILY} 次，明日再来` });
    // 洗牌：奖项等概率落三张牌
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

// ── 世界妖兽 ──"""

# ============================================================ S6 奇遇：区间化

S6_OLD = """interface AdventureTierDef { key: string; name: string; weight: number; stones: number; expRate: number; }
const ADVENTURE_TIERS: AdventureTierDef[] = [
  { key: 'white', name: '白', weight: 80, stones: 100, expRate: 0.002 },
  { key: 'blue', name: '蓝', weight: 12.5, stones: 300, expRate: 0.004 },
  { key: 'purple', name: '紫', weight: 6, stones: 800, expRate: 0.008 },
  { key: 'gold', name: '金', weight: 1.5, stones: 2000, expRate: 0.015 },
];"""

S6_NEW = """// 0.8.6：stones / expRate 由**定值**改为**区间**（用户反馈「数值都是固定值」），
// 同时新增 tickets（必得抽奖券）与 bonusChance/bonusTickets（小概率额外珍宝）。
interface AdventureTierDef {
  key: string; name: string; weight: number;
  stonesMin: number; stonesMax: number;
  expRateMin: number; expRateMax: number;
  tickets: number; bonusChance: number; bonusTickets: number;
}
const ADVENTURE_TIERS: AdventureTierDef[] = [
  { key: 'white',  name: '白', weight: 80,   stonesMin: 80,   stonesMax: 180,   expRateMin: 0.0015, expRateMax: 0.0030, tickets: 0, bonusChance: 0.02, bonusTickets: 0 },
  { key: 'blue',   name: '蓝', weight: 12.5, stonesMin: 250,  stonesMax: 550,   expRateMin: 0.0030, expRateMax: 0.0060, tickets: 0, bonusChance: 0.06, bonusTickets: 0 },
  { key: 'purple', name: '紫', weight: 6,    stonesMin: 700,  stonesMax: 1600,  expRateMin: 0.0060, expRateMax: 0.0120, tickets: 0, bonusChance: 0.15, bonusTickets: 1 },
  { key: 'gold',   name: '金', weight: 1.5,  stonesMin: 1800, stonesMax: 4200,  expRateMin: 0.0120, expRateMax: 0.0220, tickets: 1, bonusChance: 0.35, bonusTickets: 2 },
];
// 额外珍宝文案池（小概率触发时随抽附赠，纯展示 + 抽奖券）
const ADVENTURE_BONUS_TEXTS = [
  '拾得一枚残破玉简，其中隐有前人笔记',
  '草丛里翻出半截古符，虽已失效仍带灵气',
  '溪底摸到一块温润灵石原矿',
  '古树上挂着一只无人认领的储物袋',
  '崖壁凹处藏着一小坛封存多年的灵酒',
  '路边石缝里嵌着一枚锈迹斑斑的古钱',
];"""

# ============================================================ S7 奇遇：事件池扩池

S7_OLD = """  // 金 · 天缘
  { key: 'g_immortal', tier: 'gold', text: '云海之巅遇仙人对弈，一子落枰，天机灌顶——此等缘法，万中无一！' },
  { key: 'g_dragon', tier: 'gold', text: '蛟龙虚影自深潭腾空而过，一片逆鳞坠入你手，灵气如江河灌体！' },
  { key: 'g_scroll', tier: 'gold', text: '残破古卷自九天飘落，仙文入眼即化道音——福缘深厚，天授之才！' },
];"""

S7_NEW = """  { key: 'w_wind', tier: 'white', text: '山风忽起，吹落一襟松针，倒也神清气爽。' },
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
];"""

# ============================================================ S8 奇遇：修为按区间

S8_OLD = """// 奇遇修为收益（纯）：按当层修为槽百分比计，钳在槽内不溢出（已圆满则收益归零，不入结转段）
function adventureExpGain(tierKey: string, maxExp: number, currentExp: number): number {
  const t = adventureTierByKey(tierKey);
  if (!t) return 0;
  const slot = Math.max(0, Math.floor(Number(maxExp) || 0));
  const cur = Math.max(0, Math.floor(Number(currentExp) || 0));
  const raw = Math.floor(slot * t.expRate);
  return Math.max(0, Math.min(raw, slot - cur));
}"""

S8_NEW = """// 奇遇修为收益（纯）：按当层修为槽百分比计，钳在槽内不溢出（已圆满则收益归零，不入结转段）
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
}"""

# ============================================================ S9 奇遇 list

S9_OLD = """      dbAll('SELECT count, tier, event_key, exp_gain, stones FROM adventures WHERE player_id = ? AND date = ? ORDER BY count LIMIT ?', [userId, date, ADVENTURE_DAILY_MAX]),"""

S9_NEW = """      dbAll('SELECT count, tier, event_key, exp_gain, stones, tickets, bonus_text FROM adventures WHERE player_id = ? AND date = ? ORDER BY count LIMIT ?', [userId, date, ADVENTURE_DAILY_MAX]),"""

S9B_OLD = """        expGain: Math.max(0, Number(r.exp_gain) || 0),
        stones: Math.max(0, Number(r.stones) || 0),
      };
    });"""

S9B_NEW = """        expGain: Math.max(0, Number(r.exp_gain) || 0),
        stones: Math.max(0, Number(r.stones) || 0),
        tickets: Math.max(0, Number(r.tickets) || 0),
        bonusText: String(r.bonus_text || ''),
      };
    });"""

S9C_OLD = """          text: e.text,
          times: collected[e.key] || 0,
          collected: (collected[e.key] || 0) > 0,
        };
      }),
      tiers: ADVENTURE_TIERS,"""

S9C_NEW = """          text: e.text,
          times: collected[e.key] || 0,
          collected: (collected[e.key] || 0) > 0,
        };
      }),
      tiers: ADVENTURE_TIERS.map((t) => ({ key: t.key, name: t.name, weight: t.weight,
        stonesMin: t.stonesMin, stonesMax: t.stonesMax,
        expRateMin: t.expRateMin, expRateMax: t.expRateMax,
        tickets: t.tickets, bonusChance: t.bonusChance, bonusTickets: t.bonusTickets })),"""

# ============================================================ S10 奇遇 draw

S10_OLD = """    const tier = drawAdventureTier(Math.random);
    const ev = pickAdventureEvent(tier.key, Math.random);
    const stones = tier.stones;"""

S10_NEW = """    const tier = drawAdventureTier(Math.random);
    const ev = pickAdventureEvent(tier.key, Math.random);
    // 0.8.6：数值区间化 + 额外珍宝（抽奖券 / 展示用珍宝名）
    const stones = funRandInt(tier.stonesMin, tier.stonesMax, Math.random);
    const expRate = funRandFloat(tier.expRateMin, tier.expRateMax, Math.random);
    const tickets = Math.max(0, Math.floor(tier.tickets)) + (Math.random() < tier.bonusChance ? Math.max(0, Math.floor(tier.bonusTickets)) : 0);
    const bonusText = Math.random() < tier.bonusChance ? ADVENTURE_BONUS_TEXTS[funRandInt(0, ADVENTURE_BONUS_TEXTS.length - 1, Math.random)] : '';"""

S10B_OLD = """        'INSERT INTO adventures (player_id, date, count, tier, event_key, exp_gain, stones) VALUES (?, ?, ?, ?, ?, 0, ?)',
        [userId, date, drawn + 1, tier.key, ev.key, stones]"""

S10B_NEW = """        'INSERT INTO adventures (player_id, date, count, tier, event_key, exp_gain, stones, tickets, bonus_text) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)',
        [userId, date, drawn + 1, tier.key, ev.key, stones, tickets, bonusText]"""

S10C_OLD = """      expGain = adventureExpGain(tier.key, nrNow.maxExp, nrNow.exp);
      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + expGain;
      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + stones;"""

S10C_NEW = """      expGain = adventureExpGainRate(expRate, nrNow.maxExp, nrNow.exp);
      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + expGain;
      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + stones;
      if (tickets > 0) sd.player.lotteryTickets = (Number(sd.player.lotteryTickets) || 0) + tickets;"""

# ============================================================ S10d draw 回执带券与珍宝

# 抽奖即时反馈：把 tickets / bonusText 一并回给客户端，客户端 toast 才能立刻告诉玩家
# 「抽到了抽奖券 / 额外珍宝」——否则只能等下一次 /adventure/list 刷新才看得到。
S10D_OLD = """      expGain,
      stones,
      titleGranted,
    });"""

S10D_NEW = """      expGain,
      stones,
      tickets,
      bonusText,
      titleGranted,
    });"""

# ============================================================ S11 adventures 加列（PRAGMA 迁移）

S11_OLD = """  db.run(`CREATE INDEX IF NOT EXISTS idx_adventures_player ON adventures(player_id, date)`);"""

S11_NEW = """  db.run(`CREATE INDEX IF NOT EXISTS idx_adventures_player ON adventures(player_id, date)`);
  // 0.8.6：奇遇奖励多样化 —— tickets（抽奖券）/ bonus_text（额外珍宝名）
  // 与既有 linuxdo_id 同款 PRAGMA 迁移，老库安全跳过
  db.all("PRAGMA table_info(adventures)", (err, rows: any[]) => {
    if (err || !rows) return;
    if (!rows.some((r) => r.name === 'tickets')) db.exec('ALTER TABLE adventures ADD COLUMN tickets INTEGER NOT NULL DEFAULT 0');
    if (!rows.some((r) => r.name === 'bonus_text')) db.exec("ALTER TABLE adventures ADD COLUMN bonus_text TEXT NOT NULL DEFAULT ''");
  });"""

EDITS = [
    ('S1  新表 fun_daily',                 S1_OLD, S1_NEW),
    ('S2a 茶馆常量加大 + 每日 3 注',        S2A_OLD, S2A_NEW),
    ('S2b 行乐常量与纯函数',                S2B_OLD, S2B_NEW),
    ('S2c 茶馆结算加茶运',                  S2C_OLD, S2C_NEW),
    ('S2d 播报阈值 5k -> 50k',              S2D_OLD, S2D_NEW),
    ('S3  today 下发 fun 状态',             S3_OLD, S3_NEW),
    ('S4  bet 支持每日 3 注',               S4_OLD, S4_NEW),
    ('S5  三件套新端点',                    S5_OLD, S5_NEW),
    ('S6  奇遇档位区间化',                  S6_OLD, S6_NEW),
    ('S7  奇遇事件池扩池',                  S7_OLD, S7_NEW),
    ('S8  奇遇修为按区间',                  S8_OLD, S8_NEW),
    ('S9  list 回执加区间与券',             S9_OLD, S9_NEW),
    ('S9b list draws 加 tickets/bonus',     S9B_OLD, S9B_NEW),
    ('S9c list tiers 显式投影',             S9C_OLD, S9C_NEW),
    ('S10 draw 区间 + 珍宝',                S10_OLD, S10_NEW),
    ('S10b draw INSERT 加列',               S10B_OLD, S10B_NEW),
    ('S10c draw 入档加券',                  S10C_OLD, S10C_NEW),
    ('S10d draw 回执带券与珍宝',            S10D_OLD, S10D_NEW),
    ('S11 adventures 加列迁移',             S11_OLD, S11_NEW),
]

# 链序依赖证明（取自实测的 p3_brand 产物）
REQUIRES = [
    ("isValidSavePayload", 2, "p0_save 必须先跑过"),
    ("Object.create(null)", 1, "p2b_hardening 必须先跑过"),
    ("/myxxz/apps/mentor/", 1, "p3_brand 必须先跑过"),
]


def fail(msg):
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
    if "fun_daily" in src or "FUN_DICE_DAILY" in src:
        fail("source looks already patched（已存在 fun_daily / FUN_DICE_DAILY）")

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:120]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 5) 门禁
    gates = [
        # ---- S1/S11 表 ----
        ('S1 fun_daily 表已建',            'CREATE TABLE IF NOT EXISTS fun_daily', 1, None),
        ('S1 fun_daily 唯一约束',          'UNIQUE (player_id, date, kind, count)', 1, None),
        ('S1 fun_daily 索引',              'idx_fun_daily_player', 1, None),
        ('S11 adventures 加 tickets',      "ADD COLUMN tickets INTEGER NOT NULL DEFAULT 0", 1, None),
        ('S11 adventures 加 bonus_text',   "ADD COLUMN bonus_text TEXT NOT NULL DEFAULT ''", 1, None),
        # ---- S2 茶馆 ----
        ('S2 茶馆注额 500~50000',          'const TEA_MIN_BET = 500, TEA_MAX_BET = 50000', 1, None),
        ('S2 赔率仍 1.9（EV 红线）',        'TEA_PAYOUT = 1.9', 1, None),
        ('S2 每日 3 注常量',               'const TEA_MAX_BETS = 3;', 1, None),
        ('S2 茶运函数',                    'function teaLuckOf(date: string)', 1, None),
        ('S2 结算已加茶运',                'const lk = teaLuckOf(today);', 1, None),
        ('S2 茶运送的是修为',              'const luckExp = Math.floor(Number(b.stones) * lk.tier * 2);', 1, None),
        ('S2 播报阈值已抬',                'if (best && Number(best.payout) >= 50000) {', 1, None),
        ('S2 旧播报阈值已清零',            'if (best && Number(best.payout) >= 5000) {', 0, None),
        # ---- S3/S4 ----
        ('S3 today 下发 fun',              'fun: {', 1, None),
        # today 下发 1 处 + bet 回执 1 处（都是本补丁新增，故为 2）
        ('S3/S4 maxTimes 下发 2 处',        'maxTimes: TEA_MAX_BETS', 2, None),
        ('S3 today 下发 luck',             'luck,', 1, None),
        ('S4 bet 支持追加',                'ON CONFLICT(user_id, date) DO UPDATE SET stones = teahouse_bets.stones + excluded.stones', 1, None),
        ('S4 注池 upsert 原子化',          'ON CONFLICT(user_id, date) DO UPDATE SET stones = teahouse_bets.stones + excluded.stones', 1, None),
        ('S4 异侧/超限撤次数位',            "if (!up.changes) {\n      await dbRun('DELETE FROM fun_daily WHERE id = ?'", 1, None),
        ('S4 扣款失败回滚注池',             "UPDATE teahouse_bets SET stones = stones - ? WHERE user_id = ? AND date = ? AND stones >= ?", 1, None),
        ('S4 旧「读 dup 再分支写」已清零',     'UPDATE teahouse_bets SET stones = stones + ? WHERE id = ?', 0, None),
        ('S4 bet 每日上限闸门',            'if (used >= TEA_MAX_BETS) return res.status(409)', 1, None),
        ('S4 bet 异侧拒绝',                "return res.status(409).json({ error: '今日已押了另一侧，只能追加同侧' })", 1, None),
        ('S4 旧「今日已押过一卦」清零',      "error: '今日已押过一卦'", 0, None),
        # ---- S5 新端点 ----
        ('S5 dice 端点',                   "app.post('/api/fun/dice'", 1, None),
        ('S5 sign 端点',                   "app.post('/api/fun/sign'", 1, None),
        ('S5 card 端点',                   "app.post('/api/fun/card'", 1, None),
        ('S5 三骰判定纯函数',              'function funDiceKind(a: number, b: number, c: number): string {', 1, None),
        ('S5 派彩纯函数',                  'function funDicePayout(kind: string, pick: string, bet: number): number {', 1, None),
        ('S5 一签四档池',                  'const FUN_SIGN_TIERS: FunSignTier[] = [', 1, None),
        ('S5 翻牌三张牌',                  'const FUN_CARD_PAYS = [4500, 1200, 0];', 1, None),
        ('S5 翻牌成本 2000',               ', FUN_CARD_COST = 2000;', 1, None),
        ('S5 豹子赔率 25',                 'FUN_DICE_TRIPLE_PAY = 25', 1, None),
        ('S5 大小赔率 1.95',               'FUN_DICE_PAY = 1.95', 1, None),
        # dice 闸门 1 处（端内）+ today 状态查询 1 处 = 2；sign/card 用 LIMIT 1 / COUNT 各自形态
        ('S5 三玩法次数闸门走 fun_daily',   "kind = ?', [userId, today, 'dice']", 2, None),
        ('S5 sign 走 fun_daily',           "kind = ? LIMIT 1', [userId, today, 'sign']", 1, None),
        # card 闸门 1 处（端内）+ today 状态查询 1 处 = 2
        ('S5 card 走 fun_daily',           "kind = ?', [userId, today, 'card']", 2, None),
        # 403 语义红线：本补丁只允许出现 400/409/500，403 计数必须与原文**逐字相等**
        ('S5 未新增 403 拒绝',             'res.status(403)', None, 'same'),
        # ---- S6~S10 奇遇 ----
        ('S6 档位区间字段',                'stonesMin: 80,   stonesMax: 180', 1, None),
        ('S6 金档区间',                    'stonesMin: 1800, stonesMax: 4200', 1, None),
        ('S6 旧定值 stones 字段已清零',     "stones: 100, expRate: 0.002", 0, None),
        ('S6 额外珍宝池',                  'const ADVENTURE_BONUS_TEXTS = [', 1, None),
        # ★ 按**品阶计数**核对扩池结果，而不是「某个新 key 存在」——
        #   后者是典型的「只能通过的测试」：锚点若吃掉原有条目，新 key 照样在，条目却少了。
        #   原始 18 条（白5/蓝5/紫5/金3）→ 目标 34 条（白10/蓝10/紫8/金6）。
        ('S7 白档 10 条',                  "tier: 'white'", 10, None),
        ('S7 蓝档 10 条',                  "tier: 'blue'", 10, None),
        ('S7 紫档 8 条',                   "tier: 'purple'", 8, None),
        ('S7 金档 6 条（原 3 条保留）',        "tier: 'gold'", 6, None),
        ('S7 新增白档 key',                'w_bamboo', 1, None),
        ('S7 新增蓝档 key',                'b_mirror', 1, None),
        ('S7 新增紫档 key',                'p_rain', 1, None),
        ('S7 新增金档 key',                'g_master', 1, None),
        ('S7 原金档 key 未被吞掉',           'g_immortal', 1, None),
        ('S7 原金档 key 未被吞掉 2',         'g_dragon', 1, None),
        ('S7 原金档 key 未被吞掉 3',         'g_scroll', 1, None),
        ('S8 修为按传入区间',              'function adventureExpGainRate(expRate: unknown, maxExp: number, currentExp: number): number {', 1, None),
        ('S8 兼容旧调用仍在',              'function adventureExpGain(tierKey: string, maxExp: number, currentExp: number): number {', 1, None),
        ('S9 list 查询加两列',             'SELECT count, tier, event_key, exp_gain, stones, tickets, bonus_text FROM adventures', 1, None),
        ('S9 list 回执加 tickets',         'tickets: Math.max(0, Number(r.tickets) || 0),', 1, None),
        ('S9 list tiers 投影区间',         'stonesMin: t.stonesMin, stonesMax: t.stonesMax,', 1, None),
        ('S10 draw 区间随机',              'funRandInt(tier.stonesMin, tier.stonesMax, Math.random)', 1, None),
        ('S10 draw 修为区间随机',          'funRandFloat(tier.expRateMin, tier.expRateMax, Math.random)', 1, None),
        ('S10 draw INSERT 加列',           'INSERT INTO adventures (player_id, date, count, tier, event_key, exp_gain, stones, tickets, bonus_text)', 1, None),
        # 入档加券 2 处：/fun/sign（一签彩头）+ /adventure/draw（奇遇必得/额外）
        ('S10 draw 入档加券',              'if (tickets > 0) sd.player.lotteryTickets = (Number(sd.player.lotteryTickets) || 0) + tickets;', 2, None),
        ('S10d draw 回执带券与珍宝',        '      expGain,\n      stones,\n      tickets,\n      bonusText,\n      titleGranted,', 1, None),
        ('S10 旧固定 stones 取法已清零',    'const stones = tier.stones;', 0, None),
        ('S10 旧 INSERT 列清单已清零',      'INSERT INTO adventures (player_id, date, count, tier, event_key, exp_gain, stones) VALUES', 0, None),
        # ---- 全或无的顺序契约 ----
        # 4 个扣费端点各 1 处 fun_daily 占位（tea / dice / sign / card）
        ('S4/S5 fun_daily 占位共 4 处',      'INSERT INTO fun_daily (player_id, date, kind, count', 4, None),
        # 扣款/校验失败一律补偿删行，保证「无对价扣款」不可能发生
        #   5 处 = dice / sign / card 各 1 + 茶馆 2（异侧超限撤位、扣款失败撤位）
        ('S4/S5 失败补偿删行 5 处',
         "await dbRun('DELETE FROM fun_daily WHERE id = ?', [ins.lastID]).catch(() => {});", 5, None),
        # ---- 基线未被破坏 ----
        ('基线 奇遇每日上限未动',           'const ADVENTURE_DAILY_MAX = 3;', 1, None),
        ('基线 品阶权重未动',              'weight: 80,', 1, None),
        ('基线 奇遇占位唯一约束未动',       'UNIQUE (player_id, date, count)', 1, None),
        ('基线 茶馆表结构未动',             'CREATE TABLE IF NOT EXISTS teahouse_bets', 1, None),
        ('基线 存档校验未被动',             'isValidSavePayload', 2, None),
        ('基线 品牌入口未被动',             '/myxxz/apps/mentor/', 1, None),
    ]
    ok = True
    for g in gates:
        label, needle, exp = g[0], g[1], g[2]
        op = g[3] if len(g) > 3 else None
        if op == 'same':
            # 与原文逐字相等（用于「不许新增 X」这类红线门禁）
            exp = src.count(needle)
            shown = 'expect==base(%d)' % exp
        else:
            shown = 'expect==%d' % exp
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-32s actual=%d %s" % ("OK" if good else "FAIL", label, act, shown))
    if not ok:
        fail("门禁未全过")

    # 6) ★ 顺序契约位置断言（比「计数门禁」更强：计数对、次序错照样是缺陷）
    #    每个扣费端点内部：fun_daily 占位必须**早于** updatePlayerSave 扣款。
    for ep in ("app.post('/api/teahouse/bet'", "app.post('/api/fun/dice'",
               "app.post('/api/fun/sign'", "app.post('/api/fun/card'"):
        i = out.find(ep)
        if i < 0:
            fail("顺序契约校验：产物里找不到端点 %s" % ep)
        j = out.find("app.post(", i + len(ep))
        seg = out[i:j if j > 0 else len(out)]
        pa = seg.find("INSERT INTO fun_daily")
        pb = seg.find("updatePlayerSave(userId")
        if pa < 0 or pb < 0:
            fail("顺序契约校验：%s 缺少占位(%d) 或扣款(%d)" % (ep, pa, pb))
        if pa > pb:
            fail("顺序契约被破坏：%s 里 fun_daily 占位(%d) 晚于扣款(%d) ⇒ 并发落败方会被白扣灵石"
                 % (ep, pa, pb))
    print("  [OK] 顺序契约：4 个扣费端点均为「先占次数位 → 再扣款 → 再派彩」")

    # 6b) 茶馆额外一条：注池 upsert 必须夹在「占次数位」与「扣款」之间
    i = out.find("app.post('/api/teahouse/bet'")
    j = out.find("app.post(", i + 30)
    seg = out[i:j if j > 0 else len(out)]
    p1 = seg.find("INSERT INTO fun_daily")
    p2 = seg.find("ON CONFLICT(user_id, date) DO UPDATE SET stones")
    p3 = seg.find("updatePlayerSave(userId")
    if not (0 <= p1 < p2 < p3):
        fail("茶馆顺序契约被破坏：占位(%d) → 注池 upsert(%d) → 扣款(%d) 必须严格递增" % (p1, p2, p3))
    print("  [OK] 茶馆顺序契约：占次数位 → 注池原子 upsert → 扣款（异侧/超限/余额不足 均不留残账）")

    # 7) 往返自证：把每个 new 换回 old 必须逐字复现原文
    back = out
    for name, old, new in EDITS:
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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".fun086-", suffix=".tmp")
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
