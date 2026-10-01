# -*- coding: utf-8 -*-
r"""
srv_patch_r018.py -- R-018 妖灵培养重设计（服务端环 r018）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  前置依赖：必须在 **t2spirit** 之后（本环锚点 `// [/t2spirit]` 是 t2spirit 产物，
  且复用其 `petT2Roll()` / `petT2Affection()`）。lead 接线时请把本环挂在链尾。

=========================================================================== 本环做什么（第一版范围）
  出口  妖灵之力 PP = 品阶K × 等级K × 羁绊K × 资质K（极差 11.25×）→ 主人属性加成，
        写入存档 `player.petSpirit`；客户端 `xt()` 只读加算 ⇒ 快速结算 `X0` 与
        回合制 `QS` 两套战斗**同时生效**（两处都调 `xt(player)`）。
  D1    进食三档（5000/+30、25000/+150、100000/+600，单价恒 166.67 灵石/hunger）
  D2    互动三选（逗弄/梳毛/夜话，各 1 次/日免费，bond 均 +5，额外产出不同）
        + 买额度（20000 灵石/次，≤2 次/日）+ `bond` 封顶 500
  D3    点化（30000 灵石/次 → aptitude +1~3，上限 100）
  D4    秘径（每日 1 次，4 小时，5000 灵石 → hunger +80 / bond +15 / 修为 +800）
  D6    归位（`merged=1` 幂等标记，此后不可再培养）
  ★ D5 灵纹 **不做**（第二版，见设计案 §6）。
  ★ 不合并「妖灵 / 灵宠」两套系统（决策点 1 = A）；加成**加算**（决策点 2 = A）。

=========================================================================== 10 个已拍板决策的落地
  1 不合并            → 本环只动服务端 `pets` 表，不碰客户端 `player.pets` 协议
  2 加算              → `player.petSpirit` 独立字段，客户端 `xt()` 直接 +=，不对系统 B 乘算
  3 转化率 0.06       → `R018_CONVERT = 0.06`（满配 攻击 +327 = 系统 B 满配的 66%）
  4 bond 封顶 500     → `R018_BOND_MAX = 500`（feed 不变；play 的 UPDATE 走 MIN 封顶）
  5 30k + 随机 +1~3   → `R018_APTITUDE_COST = 30000`、`R018_APTITUDE_STEP = 3`（均值 +2.0）
  6 秘径 4 小时       → `R018_EXPED_MS = 4*60*60*1000`
  7 买额度可接受      → `R018_BUY_COST = 20000`、`R018_BUY_DAILY_MAX = 2`
  8 不新增仙途任务    → 本环**不碰** QUEST_DEFS / daily_quests / 活跃度
  9 D5 第二版         → 本环**不碰** rune 列 / 灵纹
  10 精魄每 10 级一次 → `r018Milestones()` 取代 `petBattleReached()`（跨 10/20/…/90 各给一次）

=========================================================================== 经济红线（设计案 §4 / §5）
  · **0 新增灵石 faucet**：D1/D2买额度/D3/D4 全是**消耗**灵石；唯一灵石产出仍是既有的
    一次性「妖灵精魄」邮件（`R018_MILESTONE_STONES`，与旧 `PET_BATTLE_STONES` 同值 1000）。
  · 新增修为 = 秘径 800/日 + 夜话 200/日 = **1000 定值/日**（不随境界/PP 缩放），
    全境界折打坐 0.0006~0.0365 h ⇒ 可忽略（设计案 §5.2）。
  · 入账走 `updatePlayerSave`（不经 `settleSaveEconV2`）⇒ 无配额夹取；
    **全站既有先例**：fun086 / t10_farm / t5_crops / t16arena 均以
    `sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + X` 直写修为。
  · 业务拒绝码一律 **409**（灵石不足 / 次数用尽 / 未到点），**不新增 403**
    （403 会被客户端 `Xc()` 当会话失效并强制登出）。

=========================================================================== 锚区（与既有环零交集，逐条 grep 过）
  S1  DDL：`safeAddColumn('pets','sub_consumed',…)` 之后 —— 加 `pets.aptitude` +
      `pet_play_log` 四列 + 新表 `pet_spirit_exped`。**保持在 db.serialize 回调内**
      （t2spirit G8b 的 TDZ 教训）。不删任何既有行 ⇒ t2spirit G8d/G29/G30 不受影响。
  S2  纯逻辑 + 端点：`// [/t2spirit]` 之后（`[wudaocore]` 之前）。t2spirit G27 断言
      `// [/t2spirit]` 恰 1 处 —— 本环 `insert_after` **保留该行**，计数不变。
  S3  `petView()` 追加 `aptitude` / `merged` 两字段（`bond: Number(p.bond) || 0,` 之后）。
  S4  `GET /api/pet`：SELECT 加列 + `Promise.all` 加 `exped` 查询 + `consts` 追加 R-018 表。
  S5  `POST /api/pet/feed`：+`tier` 参数（缺省 common，向后兼容）+ 归位守卫 + 精魄里程碑。
  S6  `POST /api/pet/play`：+`kind` / `buy` 参数 + 分种额度闸门 + bond 封顶 + 额外产出。
  ★ **不改** `const PET_FEED_COST = 5000;` / `const PET_PLAY_DAILY_MAX = 3;`（t2spirit G30 门禁面）；
    `PET_HUNGER_PER_FEED` 常量保留（供 `consts` 回显），feed 端点改走 `_feed.hunger`。

=========================================================================== 已知风险（诚实标注）
  · `player.petSpirit` 走**存档字段**通道：客户端 `applyRemoteSave` 是**整包替换** player
    （见 localtest/t_arb_hpjump.py 头部结论）⇒ 服务端写入后客户端能拿到；客户端再推档时
    因该字段在 player 内 ⇒ 可回传。**但若客户端在收到前推了旧档，服务端写入会被覆盖**
    ⇒ 本环在**每次** pet 变更后都重算并重写（自愈），且 `updatePlayerSave` 递增 gm_revision
    触发客户端拉新档。
  · 修为直写（夜话 200 / 秘径 800）走既有先例通道；与「客户端权威 exp」存在理论竞争窗口，
    与 fun086/t10_farm 等既有玩法同款风险，非本环新增。
  · 秘径到点判定在**服务端**（客户端只做倒计时展示，不可信）。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ S2 纯逻辑 + 端点（插在 // [/t2spirit] 之后）

R018_CODE = r'''
// [r018] R-018 妖灵培养重设计（纯逻辑 + 端点；纯函数不引用本块外符号，可整块提取单测）
//   出口：妖灵之力 PP = 品阶K × 等级K × 羁绊K × 资质K（极差 11.25×）→ 主人属性加成
//         （写入存档 player.petSpirit；客户端 xt() 只读加算 ⇒ X0 / QS 两套战斗同时生效）
//   六维：D1 进食三档 / D2 互动三选+买额度 / D3 点化 / D4 秘径 / D5 灵纹（第二版）/ D6 归位
//   ★ 服务端权威；0 新增灵石 faucet（唯一灵石产出仍是既有「妖灵精魄」邮件）。
const R018_FEED_TIERS: Record<string, { cost: number; hunger: number; name: string }> = {
  common:   { cost: 5000,   hunger: 30,  name: '凡品·青草露' },
  fine:     { cost: 25000,  hunger: 150, name: '灵品·玉髓羹' },
  immortal: { cost: 100000, hunger: 600, name: '仙品·九转灵丹' },
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
  const row: any = await dbGet('SELECT rarity, hunger, bond, aptitude, merged FROM pets WHERE player_id = ?', [userId]);
  if (!row || Number(row.merged) > 0) {
    await updatePlayerSave(userId, (sd: any) => { if (sd.player) sd.player.petSpirit = null; });
    return null;
  }
  const level = petLevel(row.hunger);
  const b = r018SpiritBonus(row.rarity, level, row.bond, row.aptitude);
  const payload = { pp: b.pp, attack: b.attack, defense: b.defense, maxHp: b.maxHp, speed: b.speed, level, rarity: String(row.rarity) };
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
    await updatePlayerSave(userId, (sd: any) => { if (sd.player) sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + R018_EXPED_EXP; });
    logPetCare(userId, 'exped', `秘径归来，喂食度 +${R018_EXPED_HUNGER}、羁绊 +${R018_EXPED_BOND}、修为 +${R018_EXPED_EXP}`);
    const spirit = await r018SpiritSync(userId);
    const fresh: any = await dbGet('SELECT name, rarity, hunger, exp, bond, aptitude, merged FROM pets WHERE player_id = ?', [userId]);
    res.json({ ok: true, pet: petView(fresh), spirit, expGain: R018_EXPED_EXP });
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
    const upd = await dbRun('UPDATE pets SET merged = 1 WHERE player_id = ? AND merged = 0', [userId]);
    if (!upd.changes) return res.status(409).json({ error: '归位状态已变更，请刷新后重试' });
    logPetCare(userId, 'away', `「${String(pet.name)}」妖灵归位，化为可出战灵宠`);
    await r018SpiritSync(userId);
    res.json({
      ok: true,
      merged: 1,
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
'''

# ============================================================ S1 DDL（db.serialize 内）

S1_OLD = "  safeAddColumn('pets', 'sub_consumed', 'ALTER TABLE pets ADD COLUMN sub_consumed INTEGER NOT NULL DEFAULT 0');"

S1_NEW = """  safeAddColumn('pets', 'sub_consumed', 'ALTER TABLE pets ADD COLUMN sub_consumed INTEGER NOT NULL DEFAULT 0');
  // ── R-018（r018 环）妖灵培养重设计：幂等加列 + 新表（**必须在 db.serialize 回调内**，t2spirit G8b TDZ 教训）──
  //   * pets.aptitude            —— 资质（D3 点化，0..100），进 PP 的资质K
  //   * pet_play_log.tease/brush/talk —— D2 三种互动各自的「今日免费额度」计数（各 <1 放行）
  //   * pet_play_log.bought      —— D2 买额度计数（< R018_BUY_DAILY_MAX 放行）
  //   * pet_spirit_exped         —— D4 秘径每日派遣闸门（PK(player_id,date) 单语句原子）
  safeAddColumn('pets', 'aptitude', 'ALTER TABLE pets ADD COLUMN aptitude INTEGER NOT NULL DEFAULT 0');
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
  `);"""

# ============================================================ S3 petView 追加两字段

S3_OLD = "    bond: Number(p.bond) || 0,\n  } : null;"
S3_NEW = "    bond: Number(p.bond) || 0,\n    aptitude: Number(p.aptitude) || 0,\n    merged: Number(p.merged) || 0,\n  } : null;"

# ============================================================ S4 GET /api/pet

S4A_OLD = "'SELECT name, rarity, hunger, exp, bond, created_at FROM pets WHERE player_id = ?'"
S4A_NEW = "'SELECT name, rarity, hunger, exp, bond, aptitude, merged, created_at FROM pets WHERE player_id = ?'"

S4B_OLD = r"""    const [play, logs] = await Promise.all([
      dbGet('SELECT times FROM pet_play_log WHERE player_id = ? AND date = ?', [userId, today]),
      dbAll('SELECT kind, detail, created_at FROM pet_care_log WHERE player_id = ? ORDER BY id DESC LIMIT 20', [userId]),
    ]);"""
S4B_NEW = r"""    const [play, logs, exped] = await Promise.all([
      dbGet('SELECT times, tease, brush, talk, bought FROM pet_play_log WHERE player_id = ? AND date = ?', [userId, today]),
      dbAll('SELECT kind, detail, created_at FROM pet_care_log WHERE player_id = ? ORDER BY id DESC LIMIT 20', [userId]),
      dbGet('SELECT started_at, claimed FROM pet_spirit_exped WHERE player_id = ? AND date = ?', [userId, today]),
    ]);"""

S4C_OLD = r"""      consts: {
        feedCost: PET_FEED_COST, hungerPerFeed: PET_HUNGER_PER_FEED, hungerMax: PET_HUNGER_MAX,
        levelDivisor: PET_LEVEL_DIVISOR, playDailyMax: PET_PLAY_DAILY_MAX, playBond: PET_PLAY_BOND,
        battleLevel: PET_BATTLE_LEVEL,
      },
    });"""
S4C_NEW = r"""      // R-018 出口回显：与 r018SpiritSync() 写入存档的 payload 同源同式（纯函数，不写库）
      spirit: (pet && Number(pet.merged) === 0)
        ? Object.assign({ level: petLevel(pet.hunger), rarity: String(pet.rarity) },
            r018SpiritBonus(pet.rarity, petLevel(pet.hunger), pet.bond, pet.aptitude))
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
      consts: {
        feedCost: PET_FEED_COST, hungerPerFeed: PET_HUNGER_PER_FEED, hungerMax: PET_HUNGER_MAX,
        levelDivisor: PET_LEVEL_DIVISOR, playDailyMax: PET_PLAY_DAILY_MAX, playBond: PET_PLAY_BOND,
        battleLevel: PET_BATTLE_LEVEL,
        bondMax: R018_BOND_MAX, aptitudeMax: R018_APTITUDE_MAX, aptitudeCost: R018_APTITUDE_COST,
        buyCost: R018_BUY_COST, buyDailyMax: R018_BUY_DAILY_MAX,
        expedCost: R018_EXPED_COST, expedMs: R018_EXPED_MS, expedHunger: R018_EXPED_HUNGER,
        expedBond: R018_EXPED_BOND, expedExp: R018_EXPED_EXP,
        convert: R018_CONVERT, feedTiers: R018_FEED_TIERS, playKinds: R018_PLAY_KINDS,
      },
    });"""

# ============================================================ S5 POST /api/pet/feed

S5A_OLD = "    const pet = await dbGet('SELECT id, name, hunger, level FROM pets WHERE player_id = ?', [userId]);"
S5A_NEW = ("    const _feed = r018FeedTier(req.body?.tier);\n"
           "    const pet: any = await dbGet('SELECT id, name, hunger, level, merged FROM pets WHERE player_id = ?', [userId]);\n"
           "    if (pet && Number(pet.merged) > 0) return res.status(409).json({ error: '妖灵已归位，无法再喂养' });")

S5B_OLD = r"    if (bal < PET_FEED_COST) return res.status(409).json({ error: `灵石不足：需 ${PET_FEED_COST}，现有 ${bal}` });"
S5B_NEW = r"    if (bal < _feed.cost) return res.status(409).json({ error: `灵石不足：需 ${_feed.cost}，现有 ${bal}` });"

S5C_OLD = ("      if (b < PET_FEED_COST) { short = true; return; }\n"
           "      sd.player.spiritStones = b - PET_FEED_COST;")
S5C_NEW = ("      if (b < _feed.cost) { short = true; return; }\n"
           "      sd.player.spiritStones = b - _feed.cost;")

S5D_OLD = "      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + PET_FEED_COST; });"
S5D_NEW = "      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + _feed.cost; });"

S5E_OLD = "[PET_HUNGER_MAX, PET_HUNGER_PER_FEED, PET_HUNGER_MAX, PET_HUNGER_PER_FEED, PET_HUNGER_MAX, PET_HUNGER_PER_FEED, PET_LEVEL_DIVISOR, userId]"
S5E_NEW = "[PET_HUNGER_MAX, _feed.hunger, PET_HUNGER_MAX, _feed.hunger, PET_HUNGER_MAX, _feed.hunger, PET_LEVEL_DIVISOR, userId]"

S5F_OLD = r"""    let fresh = await dbGet('SELECT name, rarity, hunger, exp, bond FROM pets WHERE player_id = ?', [userId]);
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
    }"""
S5F_NEW = r"""    let fresh = await dbGet('SELECT name, rarity, hunger, exp, bond, aptitude, merged FROM pets WHERE player_id = ?', [userId]);
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
    }"""

S5G_OLD = "    res.json({ ok: true, pet: petView(fresh), battleReached });"
S5G_NEW = "    res.json({ ok: true, pet: petView(fresh), battleReached, milestones: _miles, spirit: await r018SpiritSync(userId) });"

# ============================================================ S6 POST /api/pet/play

S6A_OLD = r"""    const gate = await dbRun(
      `INSERT INTO pet_play_log (player_id, date, times) VALUES (?, ?, 1)
       ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1 WHERE times < ?`,
      [userId, date, PET_PLAY_DAILY_MAX]
    );"""
S6A_NEW = r"""    const _kind = r018PlayKind(req.body?.kind);
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
    const gate = await dbRun(_gateSql, _gateArgs);"""

S6B_OLD = r"    if (!gate.changes) return res.status(409).json({ error: `今日嬉戏次数已用完（每日 ${PET_PLAY_DAILY_MAX} 次），明日再来` });"
S6B_NEW = r"    if (!gate.changes) return res.status(409).json({ error: _buy ? `今日买额度已用完（每日 ${R018_BUY_DAILY_MAX} 次）` : `今日「${_kind.name}」已用过（每种每日 1 次免费），明日再来` });"

S6C_OLD = "    const upd = await dbRun('UPDATE pets SET bond = bond + ? WHERE player_id = ?', [PET_PLAY_BOND, userId]);"
S6C_NEW = r"""    if (_buy) {
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
    );"""

S6D_OLD = "      await dbRun('UPDATE pet_play_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?', [userId, date]); // 补偿回退占位可重试"
S6D_NEW = ("      await dbRun('UPDATE pet_play_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?', [userId, date]); // 补偿回退占位可重试\n"
           "      if (_buy) await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + R018_BUY_COST; });")

S6E_OLD = r"""    const fresh = await dbGet('SELECT name, rarity, hunger, exp, bond FROM pets WHERE player_id = ?', [userId]);
    const prow = await dbGet('SELECT times FROM pet_play_log WHERE player_id = ? AND date = ?', [userId, date]);
    logPetCare(userId, 'play', `与「${fresh ? String(fresh.name) : '灵宠'}」嬉戏，羁绊 +${PET_PLAY_BOND}`);
    res.json({
      ok: true,
      pet: petView(fresh),
      playTimes: Math.min(PET_PLAY_DAILY_MAX, Math.max(1, Number(prow?.times) || 0)),
    });"""
S6E_NEW = r"""    if (_kind.extra === 'exp' && _kind.exp > 0) {
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
    });"""

# ============================================================ 汇总

EDITS = [
    ("S1 DDL 加列 + pet_spirit_exped 新表", S1_OLD, S1_NEW),
    ("S3 petView 追加 aptitude/merged",     S3_OLD, S3_NEW),
    ("S4a /api/pet SELECT 加列",            S4A_OLD, S4A_NEW),
    ("S4b /api/pet 并行查询加 exped",        S4B_OLD, S4B_NEW),
    ("S4c /api/pet 响应加 R-018 字段",       S4C_OLD, S4C_NEW),
    ("S5a feed 加 tier + 归位守卫",          S5A_OLD, S5A_NEW),
    ("S5b feed 预检用档位价",                S5B_OLD, S5B_NEW),
    ("S5c feed 扣费用档位价",                S5C_OLD, S5C_NEW),
    ("S5d feed 补偿退费用档位价",            S5D_OLD, S5D_NEW),
    ("S5e feed UPDATE 用档位喂食度",         S5E_OLD, S5E_NEW),
    ("S5f feed 精魄改每 10 级里程碑",        S5F_OLD, S5F_NEW),
    ("S5g feed 回执带 milestones/spirit",    S5G_OLD, S5G_NEW),
    ("S6a play 加 kind/buy + 分种额度闸门",  S6A_OLD, S6A_NEW),
    ("S6b play 409 文案分种",                S6B_OLD, S6B_NEW),
    ("S6c play 扣买额度 + bond 封顶 + 额外产出", S6C_OLD, S6C_NEW),
    ("S6d play 补偿回退含买额度退费",        S6D_OLD, S6D_NEW),
    ("S6e play 回执带 playQuota/spirit",     S6E_OLD, S6E_NEW),
]

# S2 是 insert_after（保留锚点行）
S2_ANCHOR = "// [/t2spirit]"

REQUIRES = [
    ("const PET_FEED_COST = 5000;", 1, "petcore 基线常量必须在位（t2spirit G30 门禁面）"),
    ("const PET_HUNGER_PER_FEED = 30;", 1, "petcore 基线常量必须在位"),
    ("const PET_PLAY_DAILY_MAX = 3;", 1, "petcore 基线常量必须在位（t2spirit G30 门禁面）"),
    ("function petT2Roll(): number {", 1, "t2spirit 伪随机（点化复用）"),
    ("function petT2Affection(bond: unknown): number {", 1, "t2spirit 亲密度（归位 inheritHints 复用）"),
    ("// [/t2spirit]", 1, "t2spirit 闭合行（本环 S2 锚点，且 t2spirit G27 门禁面）"),
    ("function updatePlayerSave(", 1, "updatePlayerSave 原语必须在位"),
    ("function petView(p: any): any {", 1, "petView 原语必须在位"),
    ("function logPetCare(playerId: number, kind: string, detail: string): void {", 1, "logPetCare 原语必须在位"),
    ("app.post('/api/pet/feed', authenticateToken", 1, "feed 端点唯一"),
    ("app.post('/api/pet/play', authenticateToken", 1, "play 端点唯一"),
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description='R-018 妖灵培养重设计（服务端环 r018）')
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:70], n, cnt, why))

    # 2) 幂等
    if "r018SpiritPP" in src or "pet_spirit_exped" in src:
        fail("source looks already patched（已存在 r018SpiritPP / pet_spirit_exped）")

    # 3) 锚点计数（每个必须恰 1）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)
    if src.count(S2_ANCHOR) != 1:
        fail("S2 锚点 %r 出现 %d 次（期望 1）" % (S2_ANCHOR, src.count(S2_ANCHOR)))

    # 4) 应用（先 replace，后 insert_after）
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)
    out = out.replace(S2_ANCHOR, S2_ANCHOR + "\n" + R018_CODE + "\n", 1)

    # 5) 门禁
    base403 = src.count("res.status(403")
    gates = [
        # ---- S2 纯函数 ----
        ("R18 灵食三档表",            "const R018_FEED_TIERS: Record<string, { cost: number; hunger: number; name: string }> = {", 1),
        ("R18 互动三选表",            "const R018_PLAY_KINDS: Record<string, { key: string; name: string; unlock: number; bond: number; extra: string; hunger: number; exp: number }> = {", 1),
        ("R18 三档单价恒 166.67",     "common:   { cost: 5000,   hunger: 30,  name: '凡品·青草露' },", 1),
        ("R18 仙品档 100000/+600",    "immortal: { cost: 100000, hunger: 600, name: '仙品·九转灵丹' },", 1),
        ("R18 bond 封顶 500",         "const R018_BOND_MAX = 500;", 1),
        ("R18 资质上限 100",          "const R018_APTITUDE_MAX = 100;", 1),
        ("R18 点化 30000",            "const R018_APTITUDE_COST = 30000;", 1),
        ("R18 点化随机步长 3",        "const R018_APTITUDE_STEP = 3;", 1),
        ("R18 买额度 20000",          "const R018_BUY_COST = 20000;", 1),
        ("R18 买额度每日 2",          "const R018_BUY_DAILY_MAX = 2;", 1),
        ("R18 秘径 4 小时",           "const R018_EXPED_MS = 4 * 60 * 60 * 1000;", 1),
        ("R18 秘径修为定值 800",      "const R018_EXPED_EXP = 800;", 1),
        ("R18 转化率 0.06",           "const R018_CONVERT = 0.06;", 1),
        ("R18 里程碑步长 10",         "const R018_MILESTONE_STEP = 10;", 1),
        ("R18 PP 纯函数",             "function r018SpiritPP(rarity: unknown, level: unknown, bond: unknown, aptitude: unknown): number {", 1),
        ("R18 妖灵属性纯函数",        "function r018SpiritStats(rarity: unknown, level: unknown): { attack: number; defense: number; maxHp: number; speed: number } {", 1),
        ("R18 加成纯函数",            "function r018SpiritBonus(rarity: unknown, level: unknown, bond: unknown, aptitude: unknown): { pp: number; attack: number; defense: number; maxHp: number; speed: number } {", 1),
        ("R18 档位取值 common 兜底",  "return Object.prototype.hasOwnProperty.call(R018_FEED_TIERS, k) ? R018_FEED_TIERS[k] : R018_FEED_TIERS.common;", 1),
        ("R18 互动取值 tease 兜底",   "return Object.prototype.hasOwnProperty.call(R018_PLAY_KINDS, k) ? R018_PLAY_KINDS[k] : R018_PLAY_KINDS.tease;", 1),
        ("R18 里程碑函数",            "function r018Milestones(oldLevel: unknown, newLevel: unknown): number[] {", 1),
        ("R18 存档同步函数",          "async function r018SpiritSync(userId: number): Promise<any> {", 1),
        ("R18 加成写 player.petSpirit", "sd.player.petSpirit = payload;", 1),
        ("R18 归位后清 petSpirit",     "sd.player.petSpirit = null;", 1),
        # ---- 端点 ----
        ("R18 点化端点",              "app.post('/api/pet/aptitude', authenticateToken, rateLimit(", 1),
        ("R18 秘径派遣端点",          "app.post('/api/pet/spirit/exped', authenticateToken, rateLimit(", 1),
        ("R18 秘径领取端点",          "app.post('/api/pet/spirit/exped/claim', authenticateToken, rateLimit(", 1),
        ("R18 归位端点",              "app.post('/api/pet/spirit/away', authenticateToken, rateLimit(", 1),
        ("R18 秘径到点判定在服务端",   "if (now < startAt + R018_EXPED_MS) {", 1),
        ("R18 修为入账走 updatePlayerSave", "sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + R018_EXPED_EXP;", 1),
        # ---- S1 DDL ----
        ("R18 pets.aptitude 幂等加列", "safeAddColumn('pets', 'aptitude', 'ALTER TABLE pets ADD COLUMN aptitude INTEGER NOT NULL DEFAULT 0');", 1),
        ("R18 pet_play_log 四列",      "safeAddColumn('pet_play_log', 'tease', 'ALTER TABLE pet_play_log ADD COLUMN tease INTEGER NOT NULL DEFAULT 0');", 1),
        ("R18 pet_spirit_exped 新表",  "CREATE TABLE IF NOT EXISTS pet_spirit_exped (", 1),
        # ---- S3/S4 ----
        ("R18 petView 加 aptitude",    "    aptitude: Number(p.aptitude) || 0,\n    merged: Number(p.merged) || 0,\n  } : null;", 1),
        ("R18 GET /api/pet 带 exped",  "const [play, logs, exped] = await Promise.all([", 1),
        ("R18 GET /api/pet 常量回显",  "convert: R018_CONVERT, feedTiers: R018_FEED_TIERS, playKinds: R018_PLAY_KINDS,", 1),
        ("R18 GET /api/pet 回显 spirit（客户端卡依赖）",
         "        ? Object.assign({ level: petLevel(pet.hunger), rarity: String(pet.rarity) },", 1),
        ("R18 GET spirit 归位后为 null", "      spirit: (pet && Number(pet.merged) === 0)", 1),
        ("R18 GET /api/pet playQuota", "      playQuota: {\n        tease: Math.min(1, Number(play?.tease) || 0),", 1),
        # ---- S5 feed ----
        ("R18 feed 档位取值",          "    const _feed = r018FeedTier(req.body?.tier);", 1),
        ("R18 feed 归位守卫",          "if (pet && Number(pet.merged) > 0) return res.status(409).json({ error: '妖灵已归位，无法再喂养' });", 1),
        ("R18 feed 旧单档价已清零",    "if (bal < PET_FEED_COST) return res.status(409).json(", 0),
        ("R18 feed 用档位喂食度",      "[PET_HUNGER_MAX, _feed.hunger, PET_HUNGER_MAX, _feed.hunger, PET_HUNGER_MAX, _feed.hunger, PET_LEVEL_DIVISOR, userId]", 1),
        ("R18 feed 旧喂食度数组已清零", "[PET_HUNGER_MAX, PET_HUNGER_PER_FEED, PET_HUNGER_MAX, PET_HUNGER_PER_FEED, PET_HUNGER_MAX, PET_HUNGER_PER_FEED, PET_LEVEL_DIVISOR, userId]", 0),
        ("R18 feed 里程碑取代旧判定",  "const _miles = fresh ? r018Milestones(pet.level, petLevel(fresh.hunger)) : [];", 1),
        ("R18 feed 旧 5 级判定已清零", "if (fresh && petBattleReached(pet.level, petLevel(fresh.hunger))) {", 0),
        ("R18 feed 回执带 spirit",     "res.json({ ok: true, pet: petView(fresh), battleReached, milestones: _miles, spirit: await r018SpiritSync(userId) });", 1),
        # ---- S6 play ----
        ("R18 play 分种闸门",          "const _kind = r018PlayKind(req.body?.kind);", 1),
        ("R18 play 免费额度闸门 SQL",  "ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1, tease = tease + excluded.tease", 1),
        ("R18 play 买额度闸门 SQL",    "ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1, bought = bought + 1 WHERE bought < ?", 1),
        ("R18 play 旧闸门已清零",      "ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1 WHERE times < ?", 0),
        ("R18 play bond 封顶",         "bond = MIN(?, bond + ?),", 1),
        ("R18 play 旧 bond 无封顶已清零", "const upd = await dbRun('UPDATE pets SET bond = bond + ? WHERE player_id = ?', [PET_PLAY_BOND, userId]);", 0),
        ("R18 play 回执带 playQuota",  "      playQuota: {\n        tease: Math.min(1, Number(prow?.tease) || 0),", 1),
        ("R18 play 回执带 spirit",     "      spirit,\n    });", 1),
        # ---- 冻结（本环不得回踩）----
        ("冻结 PET_FEED_COST 未动",    "const PET_FEED_COST = 5000;", 1),
        ("冻结 PET_PLAY_DAILY_MAX 未动", "const PET_PLAY_DAILY_MAX = 3;", 1),
        ("冻结 PET_PLAY_BOND 未动",    "const PET_PLAY_BOND = 5;", 1),
        ("冻结 petBattleReached 定义未动", "function petBattleReached(oldLevel: unknown, newLevel: unknown): boolean {", 1),
        ("冻结 t2spirit 闭合行仍在",   "// [/t2spirit]", 1),
        ("冻结 t2spirit 开闭各 1",     "// [t2spirit] ", 1),
        ("冻结 petT2Roll 未动",        "function petT2Roll(): number {", 1),
        ("冻结 feed 端点未动",         "app.post('/api/pet/feed', authenticateToken", 1),
        ("冻结 play 端点未动",         "app.post('/api/pet/play', authenticateToken", 1),
        ("冻结 spirit/list 未动",      "app.get('/api/pet/spirit/list', authenticateToken", 1),
        ("冻结 spirit/merge 未动",     "app.post('/api/pet/spirit/merge', authenticateToken", 1),
        ("冻结 merge 结算语句未动",    "UPDATE pets SET merged = ?, merge_pity = ?, sub_consumed = sub_consumed + 1 WHERE player_id = ? AND merged = 0", 1),
        ("冻结 merged 按成败写入",     "merged: success ? 1 : 0,", 1),
        ("冻结 pets UNIQUE 防线未动",  "player_id INTEGER NOT NULL UNIQUE", 1),
        ("冻结 经济配额函数未动",      "function settleSaveEconV2", 1),
        ("R18 不新增仙途任务",         "QUEST_DEFS", src.count("QUEST_DEFS")),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 6) 红线：不得新增 403
    a403 = out.count("res.status(403")
    good = (a403 == base403)
    ok = ok and good
    print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", "红线 未新增 res.status(403)", a403, base403))

    # 6b) D8：本环注入块内不得引用 QUEST_DEFS（不新增仙途任务）
    qd = R018_CODE.count("QUEST_DEFS")
    good = (qd == 0)
    ok = ok and good
    print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", "R18 注入块不引用 QUEST_DEFS", qd, 0))

    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back.count(S2_ANCHOR + "\n" + R018_CODE + "\n") != 1:
        fail("S2 代码块未按预期出现恰 1 次")
    back = back.replace(S2_ANCHOR + "\n" + R018_CODE + "\n", S2_ANCHOR, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r018-", suffix=".tmp")
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
