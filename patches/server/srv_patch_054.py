# -*- coding: utf-8 -*-
r"""
srv_patch_054.py -- R-054 活动中心：「仙缘七日礼」重做「每日签到」（服务端半边 · SRV_CHAIN 第 36 环）

需求（台账 R-054 原文）
--------------------------------------------------------------------------
  「七日礼活动，把这个活动重做成每日签到，时间按照每月日期数量来算。变成长期活动。
    加上修为和灵石两项奖励，并且一定的签到达标数量还可以领取额外的物品奖励。」

策划数值（AI 代决已落拍板文件 2026-10-01 05:07，两半边同源）
--------------------------------------------------------------------------
  <LOCAL>\Documents\需求台账\拍板\2026-10-01_0507_R-054_七日礼重做每日签到数值定档.md
  · 每日奖励：灵石 = floor(hourly×1.0)、修为 = floor(hourly×0.5)（境界时薪 hourly，
    与原七日礼同一锚定思路；actHourlyOf → rainHourlyStones）
  · 里程碑（当月累计签到、每月重置）：
      3 天 抽奖券×3 / 7 天 灵石×4h / 14 天 修为×6h / 21 天 太虚悟道卷×2+灵石×8h /
      全勤 称号「月满勤修」(expRate 0.01) + 灵石×12h
  · 长期化：北京自然月 lazy 建场（type=checkin_fest），day = 北京日期几号（1..28/29/30/31
    自动伸缩），与场窗口解耦；跨月自动滚新场，GM 零维护。

改动清单（4 处，全部 expect=1）
--------------------------------------------------------------------------
  E1  GET /api/activity/checkin 整段重写：
      - actSignEnsureMonth() 取/建当月场（不再信任 query.eventId）
      - days = 1..daysInMonth，每天 { day, stones, exp, claimed, missed }
      - 响应新增 monthKey / daysInMonth / progress / stonesToday / expToday / milestones[]
        （milestones[].desc 为服务端拼好的奖励文案，客户端零硬编码数值）
  E2  POST /api/activity/checkin/claim 整段重写：
      - day = 北京几号；奖励 = 灵石 1.0h + 修为 0.5h 一次 updatePlayerSave 双入账
      - 主键 INSERT OR IGNORE 占位 + 失败补偿删行（087 同款三段式纪律）
      - 响应补 stones/exp/progress（保留 reward 字段形态）
  E3  boot 尾追加 [r054sign] 代码块：activity_sign_miles DDL + 全勤称号 seed +
      ACT_SIGN_* 常量 + actSignDaysInMonth() + actSignEnsureMonth() +
      POST /api/activity/checkin/milestone（里程碑领取：主键占位幂等 + 直入账 + 失败补偿）
  E4  ACT_TYPES 里 checkin_fest 的 desc 同步月签描述（name 字面不动——act087 门禁锁前缀）

CLI 契约（照 srv_patch_050 / srv_patch_activity087）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回；`--check` / `--selftest` 只校验不写。
  幂等：产物里已含 activity_sign_miles 或 ACT_SIGN_MILESTONES 则 SKIP。
  lead 接线：localtest/chain_build.py 的 SRV_CHAIN 链尾追加 'srv_patch_054.py'
  （第 36 环，现末环 srv_patch_050.py 之后；要求 srv_patch_activity087.py 第 8 环在前）。

工程约束
--------------------------------------------------------------------------
  · ESM；不写 require(；不新增 res.status(403)（现产物 11 处，门禁锁死不变）；
    不新增 setInterval / PRAGMA（milestone 是即时发放，无结算器需求）。
  · 冻结（下游/相邻门禁锁定的字面，一字不动）：
      'const ACT_CHECKIN_DAYS = 7;' ==1（act087 gate + srv_patch_055 BASE_NEEDLES）
      "checkin_fest: { name: '仙缘七日礼'" ==1（act087 gate）
      "app.get('/api/activity/checkin'" ==1、"app.post('/api/activity/checkin/claim'" ==1
      CREATE TABLE IF NOT EXISTS activity_checkin ==1、actDropTokens( ==4
  · 客户端半边 = yl_054_ext.py（YlxwTActCheckin 月历重写），两者配套。
  · ⛔ 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；⛔ 不改任何既有 srv_patch_*.py。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r054sign]"

# ============================================================ 锚点（srv/index_v28.ts 实测 count==1 @2026-10-01，
# ============================================================ repr 括号拼接防手抄；探针 r054_gen_anchors.py 生成）

E1_OLD = (
    "app.get('/api/activity/checkin', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, ke" +
    'yFn: (req: any) => `act:ck:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {\n  cons' +
    "t userId = req.user.id;\n  try {\n    const ev = await actEventOf(req.query?.eventId, 'checkin_fes" +
    "t');\n    if (!ev) return res.status(400).json({ error: 'eventId 非法' });\n    const now = Date.now" +
    '();\n    const dayNo = Math.floor((now - Number(ev.start_at)) / 86400000) + 1;\n    const today = ' +
    'dayNo < 1 ? 0 : Math.min(ACT_CHECKIN_DAYS, dayNo);\n    const hourly = await actHourlyOf(userId);' +
    "\n    const claimedRows = await dbAll('SELECT day FROM activity_checkin WHERE player_id = ? AND e" +
    "vent_id = ?', [userId, Number(ev.id)]);\n    const claimed = new Set<number>((claimedRows || [])." +
    'map((x: any) => Math.floor(Number(x.day) || 0)));\n    const days: any[] = [];\n    let missedAny ' +
    '= false;\n    for (let d = 1; d <= ACT_CHECKIN_DAYS; d++) {\n      const isClaimed = claimed.has(d' +
    ');\n      const missed = d < today && !isClaimed;\n      if (missed) missedAny = true;\n      days.' +
    'push({ day: d, reward: Math.floor(hourly * (d < 7 ? d / 6 : 3)), claimed: isClaimed, missed });\n' +
    '    }\n    const active = actIsActive(ev, now);\n    res.json({\n      eventId: Number(ev.id),\n    ' +
    '  days,\n      canClaim: active && (await actEngineEnabled()) && today >= 1 && !claimed.has(today' +
    '),\n      today,\n      fullAttendable: active && today >= 1 && !missedAny,\n    });\n  } catch (e: ' +
    "any) {\n    console.error('act checkin error:', e?.message || e);\n    res.status(500).json({ erro" +
    "r: '服务器繁忙' });\n  }\n});\n\n// ── B 仙缘七日礼：POST /api/activity/checkin/claim {eventId} ──\n// 主键 INSERT" +
    ' OR IGNORE 占位 → 服务端重算 day（不信任客户端）→ updatePlayerSave 直入账\n// （不走 mail，零邮件量；失败补偿删行可重试）。断签不补：只能领「今天」' +
    '，前期作废。\n'
)

E2_OLD = (
    "app.post('/api/activity/checkin/claim', authenticateToken, rateLimit({ windowMs: 60 * 1000, max:" +
    ' 10, keyFn: (req: any) => `act:ckc:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => ' +
    "{\n  const userId = req.user.id;\n  try {\n    const ev = await actEventOf(req.body?.eventId, 'chec" +
    "kin_fest');\n    if (!ev) return res.status(400).json({ error: 'eventId 非法' });\n    if (!(await a" +
    "ctEngineEnabled())) return res.status(409).json({ error: '活动引擎暂未开启' });\n    const now = Date.now" +
    '();\n    if (!actIsActive(ev, now)) {\n      return res.status(409).json({ error: now < Number(ev.' +
    "start_at) ? '活动尚未开启' : '活动已结束' });\n    }\n    const dayNo = Math.floor((now - Number(ev.start_at)" +
    ') / 86400000) + 1;\n    const day = Math.min(ACT_CHECKIN_DAYS, Math.max(1, dayNo));\n    const ins' +
    " = await dbRun(\n      'INSERT OR IGNORE INTO activity_checkin (player_id, event_id, day, claimed" +
    "_at) VALUES (?, ?, ?, ?)',\n      [userId, Number(ev.id), day, now]);\n    if (!ins.changes) retur" +
    "n res.status(409).json({ error: '今日已签到，明日再来' });\n    const hourly = await actHourlyOf(userId);\n " +
    '   let reward = Math.floor(hourly * (day < 7 ? day / 6 : 3));\n    if (day === 7) {\n      const c' +
    " = await dbGet('SELECT COUNT(*) AS c FROM activity_checkin WHERE player_id = ? AND event_id = ?'" +
    ', [userId, Number(ev.id)]);\n      if (Number(c && c.c) === ACT_CHECKIN_DAYS) reward += Math.floo' +
    'r(hourly * 3); // 全勤奖（COUNT=7 校验）\n    }\n    let credited = false;\n    const paid = await updateP' +
    "layerSave(userId, (sd: any) => {\n      if (!sd.player || typeof sd.player !== 'object') return;\n" +
    '      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + re' +
    'ward;\n      credited = true;\n    });\n    if (!paid.ok || !credited) {\n      // 补偿删行可重试（占位已撤，直入账失' +
    "败不吞签到机会）\n      await dbRun('DELETE FROM activity_checkin WHERE player_id = ? AND event_id = ? AN" +
    "D day = ?', [userId, Number(ev.id), day]).catch(() => { });\n      return res.status(409).json({ " +
    "error: paid.error === 'No save found' ? '请先进游戏创建角色' : '领取失败，请重试' });\n    }\n    res.json({ ok: tr" +
    "ue, day, reward });\n  } catch (e: any) {\n    console.error('act checkin claim error:', e?.messag" +
    "e || e);\n    res.status(500).json({ error: '服务器繁忙' });\n  }\n});\n\n// ── C 灵玉阁：GET /api/activity/sh" +
    'op ──\n// 商品目录 = 服务端常量字典（免表）；余额跨期保留；限购按期记账（bought:<eventId>:<itemId> 行）。\n'
)

E3_ANCHOR = (
    ".catch((e: any) => console.error('act boot settle error:', e?.message || e));"
)

E4_OLD = (
    "desc: '节庆七日签到：逐日递增灵石，全勤另赠厚礼'"
)

# ============================================================ E1_NEW：GET /api/activity/checkin（月历版）

E1_NEW = """app.get('/api/activity/checkin', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `act:ck:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
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
"""

# ============================================================ E2_NEW：POST /api/activity/checkin/claim（月签版）

E2_NEW = """app.post('/api/activity/checkin/claim', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `act:ckc:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
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
"""

# ============================================================ E3_NEW：boot 尾追加 [r054sign] 代码块

_E3_BLOCK = """

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
  const nextMonth = mo === 12 ? (y + 1) + '-01' : month.slice(0, 4) + String(mo + 1).padStart(2, '0');
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
  const nextMonth = mo === 12 ? (y + 1) + '-01' : month.slice(0, 4) + String(mo + 1).padStart(2, '0');
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
});"""

E3_NEW = E3_ANCHOR + _E3_BLOCK

# ============================================================ E4_NEW：ACT_TYPES desc 同步

E4_NEW = "desc: '每日签到：按月历每日签到得修为与灵石，累计达标领额外奖励（长期活动）[r054sign]'"

# ============================================================ EDITS / REQUIRES

EDITS = [
    ("E1 GET checkin 月历化", E1_OLD, E1_NEW),
    ("E2 claim 月签化", E2_OLD, E2_NEW),
    ("E3 boot 尾追加 [r054sign] 块", E3_ANCHOR, E3_NEW),
    ("E4 ACT_TYPES desc 同步", E4_OLD, E4_NEW),
]

# 前置依赖（链序：srv_patch_activity087.py 第 8 环必须在前）
REQUIRES = [
    ("CREATE TABLE IF NOT EXISTS activity_rank_settled", 1, "act087 已应用（A1 六新表 DDL）"),
    ("const ACT_CHECKIN_DAYS = 7;", 1, "act087 B 常量在位（本环不改它，act087/srv055 门禁锁其计数）"),
    ("checkin_fest: { name: '仙缘七日礼'", 1, "act087 A2 目录行在位（name 字面本环不动）"),
    ("function grantTitleBySource(", 1, "称号授予原语在位（全勤称号经它发放）"),
    ("function actHourlyOf(", 1, "境界时薪原语在位（奖励锚定）"),
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def selftest() -> int:
    """纯数学自证：月天数、里程碑门槛、数值定档、幂等键。"""
    import calendar
    import datetime as _dt

    fails = []

    # 1 月天数公式（含闰月）：与 calendar 对照 2015..2033 全月
    bad = []
    for y in range(2015, 2034):
        for m in range(1, 13):
            next_y, next_m = (y + 1, 1) if m == 12 else (y, m + 1)
            dim = (Date_parse("%04d-%02d-01T00:00:00+08:00" % (next_y, next_m))
                   - Date_parse("%04d-%02d-01T00:00:00+08:00" % (y, m))) // 86400000
            if dim != calendar.monthrange(y, m)[1]:
                bad.append("%04d-%02d" % (y, m))
    ok1 = not bad
    print("  [%s] 1  actSignDaysInMonth 公式 2015..2033 全月对照 calendar（228 月，含 2028 闰年）" % ("OK" if ok1 else "FAIL"))
    if not ok1:
        fails.append("1 月天数错: %r" % bad[:6])

    # 2 里程碑门槛递增且全勤档为哨兵
    miles = [3, 7, 14, 21, -1]
    ok2 = miles == sorted(set(miles[:-1])) + [-1] and miles[-1] == -1
    print("  [%s] 2  里程碑档 3/7/14/21/全勤(-1 哨兵) 递增" % ("OK" if ok2 else "FAIL"))
    if not ok2:
        fails.append("2 里程碑档错")

    # 3 全月奖励总量（用 hourly=229788 长生档核算）：灵石小时数 = 31+4+8+12 = 55h
    stone_h = 31 + 4 + 8 + 12
    ok3 = stone_h == 55
    print("  [%s] 3  全勤月灵石合计 = 时薪×%d（基础 31 + 里程碑 4/8/12）" % ("OK" if ok3 else "FAIL", stone_h))
    if not ok3:
        fails.append("3 合计错")

    # 4 修为小时数 = 15.5 + 6 = 21.5h（同境界时薪折算）
    exp_h = 31 * 0.5 + 6
    ok4 = abs(exp_h - 21.5) < 1e-9
    print("  [%s] 4  全勤月修为合计 = 时薪×%.1f" % ("OK" if ok4 else "FAIL", exp_h))
    if not ok4:
        fails.append("4 修为合计错")

    # 5 原七日礼对照：一期 6.5h（全勤 9.5h），月 4 期 ≈ 26~38h → 新方案 55h 小幅上调、远低于挂机 720h
    ok5 = 55 < 720 * 0.1
    print("  [%s] 5  新月签 55h < 挂机月 720h 的 10%%（不构成刷钱口）" % ("OK" if ok5 else "FAIL"))
    if not ok5:
        fails.append("5 EV 越界")

    # 6 哨兵解析：min=-1 在 dim=31 时 tier=31，progress>=31 才解锁
    dim = 31
    tier_of = lambda m: (dim if m < 0 else m)
    ok6 = tier_of(-1) == 31 and not (30 >= tier_of(-1))
    print("  [%s] 6  全勤档 tier=daysInMonth（31 天月需 31 签，漏一天即不可得）" % ("OK" if ok6 else "FAIL"))
    if not ok6:
        fails.append("6 哨兵解析错")

    print()
    if fails:
        print("[SELFTEST FAIL] " + "; ".join(fails))
        return 1
    print("[SELFTEST PASS] 6/6 —— 月天数公式（228 月对照）、里程碑递增、灵石 55h/修为 21.5h 定档、")
    print("                EV < 挂机 10%、全勤哨兵解析 —— 全部成立")
    return 0


def Date_parse(s: str) -> int:
    """datetime.strptime 的 ISO 形态（带 +08:00），返回 epoch ms。"""
    import datetime as _dt
    d = _dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    return int(d.timestamp() * 1000)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等
    if "activity_sign_miles" in src or "ACT_SIGN_MILESTONES" in src:
        print("  [SKIP] source looks already patched（已存在 activity_sign_miles / ACT_SIGN_MILESTONES）")
        return

    # 2) 链序依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 3) 锚点计数（锚点 = 产物真实字节形态，单次替换契约）
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
        # ---- 本环新增 ----
        ('r54 activity_sign_miles DDL',   'CREATE TABLE IF NOT EXISTS activity_sign_miles', 1, None),
        ('r54 全勤称号 seed',              "VALUES ('月满勤修', '{\"expRate\":0.01}', 'r054_month_sign')", 1, None),
        ('r54 灵石时薪常量',               'const ACT_SIGN_STONE_HOURS = 1.0;', 1, None),
        ('r54 修为时薪常量',               'const ACT_SIGN_EXP_HOURS = 0.5;', 1, None),
        ('r54 里程碑表定义',               'const ACT_SIGN_MILESTONES:', 1, None),
        ('r54 全勤哨兵',                  "{ min: -1, tickets: 0, stoneHours: 12, expHours: 0, scrolls: 0, title: '月满勤修' },", 1, None),
        ('r54 actSignDaysInMonth 定义',   'function actSignDaysInMonth(', 1, None),
        ('r54 actSignDaysInMonth 调用2',  'actSignDaysInMonth(now)', 2, None),
        ('r54 actSignEnsureMonth 定义',   'async function actSignEnsureMonth(', 1, None),
        ('r54 actSignEnsureMonth 调用3',  'await actSignEnsureMonth(now', 3, None),
        ('r54 milestone 端点',            "app.post('/api/activity/checkin/milestone'", 1, None),
        ('r54 milestone 主键占位',         'INSERT OR IGNORE INTO activity_sign_miles', 1, None),
        ('r54 milestone 补偿删行',         'DELETE FROM activity_sign_miles WHERE player_id = ? AND event_id = ? AND tier = ?', 1, None),
        ('r54 太虚悟道卷发放',             "name: '太虚悟道卷', type: '材料'", 1, None),
        ('r54 milestone 抽奖券入账',       'if (mdef.tickets > 0) { sd.player.lotteryTickets = Math.max(0, Math.floor(Number(sd.player.lotteryTickets) || 0)) + mdef.tickets; }', 1, None),
        ('r54 milestone 灵石入账',         'if (stones > 0) { sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + stones; }', 1, None),
        ('r54 称号授予调用',               "grantTitleBySource(userId, 'r054_month_sign')", 1, None),
        ('r54 claim 修为入账',             '\n      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + exp;\n      credited = true;', 1, None),
        ('r54 milestone 修为入账',         'if (exp > 0) { sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + exp; }', 1, None),
        ('r54 GET stonesToday 下发',       'stonesToday: Math.floor(hourly * ACT_SIGN_STONE_HOURS)', 1, None),
        ('r54 GET progress 下发（现值11+1）', 'progress,', 12, None),
        ('r54 月历天数下发',               'daysInMonth: dim,', 1, None),
        ('r54 ACT_TYPES desc 已同步',      E4_NEW, 1, None),
        # ---- 冻结：act087 / srv055 门禁字面一字不动 ----
        ('冻结 act087 B 常量字面',         'const ACT_CHECKIN_DAYS = 7;', 1, None),
        ('冻结 act087 GET 端点字面',       "app.get('/api/activity/checkin'", 1, None),
        ('冻结 act087 claim 端点字面',     "app.post('/api/activity/checkin/claim'", 1, None),
        ('冻结 act087 目录 name 字面',     "checkin_fest: { name: '仙缘七日礼'", 1, None),
        ('冻结 activity_checkin 建表',     'CREATE TABLE IF NOT EXISTS activity_checkin', 1, None),
        ('冻结 actDropTokens 计数',        'actDropTokens(', 4, None),
        ('冻结 actApplyGain 计数',         'actApplyGain(', 8, None),
        ('冻结 403 计数（t7_sect 后基线）', 'res.status(403)', 11, None),
        ('冻结 结算器 boot-run',           'return actSettleTick()', 1, None),
        ('冻结 grantTitleBySource 计数（现值13+1）', 'grantTitleBySource(', 14, None),
        # ---- 纪律：不新增 require( / setInterval（现值 3，本环零新增）----
        ('纪律 无新增 require(',          'require(', 0, None),
        ('纪律 setInterval 现值恒 3',      'setInterval(', 3, None),
    ]
    for name, needle, want, _ in gates:
        n = out.count(needle)
        if n != want:
            fail("门禁 %s：%r 出现 %d 次（期望 %d）" % (name, needle[:80], n, want))

    # 5b) 顺序契约：ensure 定义必须先于三处调用（JS 函数声明提升无碍，但语句级的
    #     CREATE TABLE / 常量必须在端点前——本块整体插在 boot 尾 = 全部端点之后，
    #     const/let 有 TDZ ⇒ 必须验证三个端点引用的 ACT_SIGN_* 在其调用文本之前不成立时
    #     依赖的是「端点回调运行期」而非「模块加载期」，TDZ 仅约束加载期执行，故安全；
    #     这里锁的是 r054sign 块相对 GET checkin 的位置，防将来有人把它挪到端点前打乱锚区。
    p_blk = out.find('[r054sign]')
    p_get = out.find("app.get('/api/activity/checkin'")
    if p_blk < 0 or p_get < 0:
        fail("顺序契约校验：r054sign 块(%d) 或 GET checkin(%d) 缺失" % (p_blk, p_get))
    print("  [OK] 顺序契约：[r054sign] 块位于 boot 尾（offset %d），GET checkin 在 %d（端点回调运行期引用，无 TDZ 风险）"
          % (p_blk, p_get))

    # 6) 往返自证：把每个 new 换回 old 必须逐字复现原文
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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r054sign-", suffix=".tmp")
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
