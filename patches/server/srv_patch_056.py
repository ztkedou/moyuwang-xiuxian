# -*- coding: utf-8 -*-
r"""
srv_patch_056.py -- R-056 万妖（万兽）巢穴：多 boss + 每只 5 次免费 + 10 分钟冷却（服务端半边 · SRV_CHAIN 第 36 环）

需求（台账 R-056 原文，进行中.md:27）
--------------------------------------------------------------------------
  「万兽巢穴增加boss数量，每日不设置上限，但是加冷却时间，10分钟一次。免费的次数每一个boss5次。」

现状（侦察 srv/index_v28.ts，activity087 环产物）
--------------------------------------------------------------------------
  · 每期 boss_raid 活动 1 只妖兽（event_boss.event_id PRIMARY KEY，actBossEnsure lazy 建场）；
  · 免费出手 3 次/日（ACT_BOSS_FREE_STRIKES=3，actFunUsedToday('raid') 计数闸门）；
  · 诛妖符 2 张/日（本环不动：ACT_BOSS_TALISMAN_DAILY=2 原样、价格=1×境界时薪原样）。

本环改点（13 处锚改，全在 activity087 注入的 boss 域内）
--------------------------------------------------------------------------
  E1  常量：ACT_BOSS_FREE_STRIKES 3→5（口径改「每只」）+ 新增
      ACT_BOSS_MAX_BOSSES=5 / ACT_BOSS_STRIKE_COOLDOWN_MS=10 分钟 / ACT_BOSS_HP_GROWTH=0.5
  E2  DDL：老库幂等加列 event_boss.boss_no、event_boss_hits.free_used / last_strike_at
      （safeAddColumn 容忍 duplicate column name，冷启动/重跑双安全；建表语句不动）
  E3  actBossEnsure：lazy 刷新下一只（killed=1 && boss_no<MAX && settled!=1 ⇒ 换血重生 +
      全员 free_used 归零；killed=1 守卫防并发双刷）
  E4  actBossHitOnce 签名 + isFree: boolean
  E5  hits upsert：写 free_used（免费才 +1）/ last_strike_at（每次出手都刷）
  E6  actBossHitOnce 击杀当场刷新下一只（惰性兜底在 E3；守卫同 killed=1）
  E7  strike 配额块：每日 3 次闸门 →「本只 5 次 + 10 分钟冷却」双闸；
      fun_daily 'raid' 行保留（账目审计 + UNIQUE 防双击竞态），不再作配额依据
  E8  strike 响应：freeLeft 按 freeUsed 计 + 回 coolLeft(=冷却窗全长，客户端倒计时锚)
  E9  strike 调用 hitOnce(…, true)
  E10 talisman 调用 hitOnce(…, false)（符不占免费位、不写冷却——本环不扩权到符）
  E11 status mine SELECT 加读 free_used / last_strike_at
  E12 status：usedFree(每日口径) → freeUsed + coolLeft（剩余秒）
  E13 status 响应：freeLeft 每只口径 + 新回执 bossNo / bossMax / coolLeft

结算兼容（多 boss 不破坏结算器的论证）
--------------------------------------------------------------------------
  · event_boss_hits 按 (event_id,user_id) 累计 score/strikes ⇒ 档位/排名奖励跨 5 只累计，
    结算器（settled 置位、ACT_BOSS_TRUCE_MS 休战、killer/全服奖）零改动；
  · 中途 boss 诛杀后当场刷新 ⇒ killed=0，早结算分支 (killed && now>=killed_at+2d) 不会误触发；
  · 最终只（第 5 只）诛杀后不再刷新 ⇒ 休战/结算行为与现状完全一致；
  · settled=1 后不再刷新（E3 守卫），杜绝「结算后继续打」的脏窗口。

数值拍板（AI 代决，详见 拍板/2026-10-01_*.md）
--------------------------------------------------------------------------
  · boss 数量 5 只：需求只说「增加」未给数；5 与「每只免费 5 次」对仗（每期免费出手上限
    5×5=25），且血量 +50%/只、10 分钟冷却下第 5 只显著更硬，过程感足。常量一行可调。
  · 血量 第 n 只 = 基础×(1+0.5×(n-1))：第 1 只与现状完全一致（不改变既有难度锚），
    第 5 只 3×。不用 2^n（5 只就是 16×，小服全服合力也打不动，boss 数量形同虚设）。
  · 冷却只闸免费出手：诛妖符本就有「2 张/日 + 1×时薪/张」双重闸，本环不扩权不加闸。

CLI 契约（与链上其余补丁一致，照 srv_patch_r039.py / srv_patch_050.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` / `--selftest` 只校验不写。
  幂等：产物里已含 `[r056boss]` 标记则 SKIP。
  lead 接线：localtest/chain_build.py 的 SRV_CHAIN 链尾追加 'srv_patch_056.py'
  （第 36 环，现末环 srv_patch_050.py 之后；仅要求 activity087 环在前）。
  客户端半边：yl_056_ext.py（标题/口径/冷却显示 + 讨灭横幅分叉），两者配套。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval`。
  · PRAGMA 仅 +2（E2 的两处加列守卫，基线计数断言 base+2；DDL 兜底是 safeAddColumn 自身幂等）。
  · 每处替换 expect=1（含 9a/9b 两个同形调用点用前置注释行区分），命中数不符即中止。
  · ⛔ 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；⛔ 不改任何既有 srv_patch_*.py。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（同时用于已打补丁判定）
MARK = "[r056boss]"

# ============================================================ 唯一锚点与替换

# E1 常量行（activity087 环原文，行尾注释一并在锚内，替换后旧口径注释消失）
E1_OLD = "const ACT_BOSS_FREE_STRIKES = 3;                   // D 免费出手 3 次/日（fun_daily kind='raid'）"
E1_NEW = (
    "const ACT_BOSS_FREE_STRIKES = 5;                   // [r056boss] R-056 免费出手 5 次/只"
    "（event_boss_hits.free_used，换 boss 归零；每日不限次）\n"
    "const ACT_BOSS_MAX_BOSSES = 5;                     // [r056boss] R-056 每期连刷 5 只"
    "（诛一只当场现身下一只；最终只保留休战 2 天结算）\n"
    "const ACT_BOSS_STRIKE_COOLDOWN_MS = 10 * 60 * 1000; // [r056boss] R-056 免费出手冷却 10 分钟"
    "（event_boss_hits.last_strike_at）\n"
    "const ACT_BOSS_HP_GROWTH = 0.5;                    // [r056boss] R-056 第 n 只血量 = 基础 × (1 + 0.5×(n-1))：第 2 只 1.5× … 第 5 只 3×"
)

# E2 DDL：插在冲榜窗口聚合索引之前（activity087 DDL 块尾部，唯一）
E2_ANCHOR = "db.run(`CREATE INDEX IF NOT EXISTS idx_stats_daily_date ON stats_daily(date)`);"
E2_BLOCK = (
    "  // [r056boss] R-056 万妖巢穴多 boss：老库幂等加列（safeAddColumn 容忍 duplicate column name，"
    "冷启动/重跑双安全）。建表语句不动，默认值经 ALTER 生效。\n"
    "  //   event_boss.boss_no 当前第几只（1 起）；event_boss_hits.free_used 对当前这只已用免费数"
    "（换 boss 归零）；event_boss_hits.last_strike_at 上次免费出手时刻（10 分钟冷却锚点）。\n"
    "  db.all(\"PRAGMA table_info(event_boss)\", (err: any, rows: any[]) => {\n"
    "    if (!err && rows && !rows.some((r: any) => r.name === 'boss_no')) "
    "safeAddColumn('event_boss', 'boss_no', 'ALTER TABLE event_boss ADD COLUMN boss_no INTEGER NOT NULL DEFAULT 1');\n"
    "  });\n"
    "  db.all(\"PRAGMA table_info(event_boss_hits)\", (err: any, rows: any[]) => {\n"
    "    if (!err && rows) {\n"
    "      if (!rows.some((r: any) => r.name === 'free_used')) "
    "safeAddColumn('event_boss_hits', 'free_used', 'ALTER TABLE event_boss_hits ADD COLUMN free_used INTEGER NOT NULL DEFAULT 0');\n"
    "      if (!rows.some((r: any) => r.name === 'last_strike_at')) "
    "safeAddColumn('event_boss_hits', 'last_strike_at', 'ALTER TABLE event_boss_hits ADD COLUMN last_strike_at INTEGER NOT NULL DEFAULT 0');\n"
    "    }\n"
    "  });\n"
)

# E3 actBossEnsure：lazy 刷新下一只
E3_OLD = (
    "  let row = await dbGet('SELECT * FROM event_boss WHERE event_id = ?', [eventId]).catch(() => null);\n"
    "  if (row) return row;\n"
)
E3_NEW = (
    "  let row = await dbGet('SELECT * FROM event_boss WHERE event_id = ?', [eventId]).catch(() => null);\n"
    "  if (row) {\n"
    "    // [r056boss] R-056 多 boss：上一只已诛且非最终只 ⇒ 就地刷新下一只（killed=1 守卫幂等，\n"
    "    //   与 actBossHitOnce 内的当场刷新互斥兜底）；settled=1 不再刷新（结算已落）。刷新同时\n"
    "    //   把全员 free_used 归零（每只 5 次免费）。血量按第 n 只 = 基础×(1+0.5×(n-1))。\n"
    "    const no0 = Math.max(1, Math.floor(Number(row.boss_no) || 1));\n"
    "    if (Number(row.killed) === 1 && no0 < ACT_BOSS_MAX_BOSSES && Number(row.settled) !== 1) {\n"
    "      const nextNo = no0 + 1;\n"
    "      const topR = await dbGet('SELECT MAX(realm_index) AS ri FROM rankings').catch(() => null);\n"
    "      const multR = Math.pow(1.5, Math.min(20, Math.max(0, Number(topR && topR.ri) || 0)));\n"
    "      const hpNext = Math.floor(WB_HP_BASE * multR * ACT_BOSS_HP_CYCLE * (1 + ACT_BOSS_HP_GROWTH * (nextNo - 1)));\n"
    "      const up = await dbRun('UPDATE event_boss SET boss_no = ?, hp_max = ?, hp_cur = ?, killed = 0, killer_id = NULL WHERE event_id = ? AND killed = 1', [nextNo, hpNext, hpNext, eventId]).catch(() => null);\n"
    "      if (up && up.changes) await dbRun('UPDATE event_boss_hits SET free_used = 0 WHERE event_id = ?', [eventId]).catch(() => { });\n"
    "      row = await dbGet('SELECT * FROM event_boss WHERE event_id = ?', [eventId]).catch(() => null) || row;\n"
    "    }\n"
    "    return row;\n"
    "  }\n"
)

# E4 actBossHitOnce 签名
E4_OLD = "async function actBossHitOnce(userId: number, eventId: number, nowMs: number): Promise<{ score: number; total: number; killed: boolean; hpCur: number }> {"
E4_NEW = "async function actBossHitOnce(userId: number, eventId: number, nowMs: number, isFree: boolean): Promise<{ score: number; total: number; killed: boolean; hpCur: number }> {"

# E5 hits upsert：free_used 只在免费出手时 +1；last_strike_at 每次出手都刷
E5_OLD = (
    "  await dbRun(\n"
    "    `INSERT INTO event_boss_hits (event_id, user_id, score, strikes) VALUES (?, ?, ?, 1)\n"
    "     ON CONFLICT(event_id, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1`,\n"
    "    [eventId, userId, score]);\n"
)
E5_NEW = (
    "  await dbRun(\n"
    "    `INSERT INTO event_boss_hits (event_id, user_id, score, strikes, free_used, last_strike_at) VALUES (?, ?, ?, 1, ?, ?)\n"
    "     ON CONFLICT(event_id, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1,\n"
    "       free_used = free_used + excluded.free_used, last_strike_at = excluded.last_strike_at`,\n"
    "    [eventId, userId, score, isFree ? 1 : 0, nowMs]);\n"
)

# E6 击杀当场刷新下一只（锚 = killed 判定行，唯一）
E6_OLD = "  const killed = Number(after && after.killed) === 1;\n"
E6_NEW = (
    "  const killed = Number(after && after.killed) === 1;\n"
    "  // [r056boss] R-056：击杀当场刷新下一只（惰性兜底在 actBossEnsure；killed=1 守卫防并发双刷；\n"
    "  //   最终只不刷新 ⇒ 休战/结算行为与单 boss 时代完全一致）。\n"
    "  if (killed) {\n"
    "    const curR = await dbGet('SELECT boss_no, settled FROM event_boss WHERE event_id = ?', [eventId]).catch(() => null);\n"
    "    const noR = Math.max(1, Math.floor(Number(curR && curR.boss_no) || 1));\n"
    "    if (noR < ACT_BOSS_MAX_BOSSES && Number(curR && curR.settled) !== 1) {\n"
    "      const nextR = noR + 1;\n"
    "      const topR2 = await dbGet('SELECT MAX(realm_index) AS ri FROM rankings').catch(() => null);\n"
    "      const multR2 = Math.pow(1.5, Math.min(20, Math.max(0, Number(topR2 && topR2.ri) || 0)));\n"
    "      const hpR = Math.floor(WB_HP_BASE * multR2 * ACT_BOSS_HP_CYCLE * (1 + ACT_BOSS_HP_GROWTH * (nextR - 1)));\n"
    "      const upR = await dbRun('UPDATE event_boss SET boss_no = ?, hp_max = ?, hp_cur = ?, killed = 0, killer_id = NULL WHERE event_id = ? AND killed = 1', [nextR, hpR, hpR, eventId]).catch(() => { });\n"
    "      if (upR && upR.changes) await dbRun('UPDATE event_boss_hits SET free_used = 0 WHERE event_id = ?', [eventId]).catch(() => { });\n"
    "    }\n"
    "  }\n"
)

# E7 strike 配额块：每日 3 次 → 本只 5 次 + 10 分钟冷却（fun_daily 行保留作审计/防竞态）
E7_OLD = (
    "    const used = await actFunUsedToday(userId, 'raid');\n"
    "    if (used >= ACT_BOSS_FREE_STRIKES) {\n"
    "      return res.status(409).json({ error: `今日免费出手已用尽（${ACT_BOSS_FREE_STRIKES} 次），可用诛妖符追加` });\n"
    "    }\n"
)
E7_NEW = (
    "    const used = await actFunUsedToday(userId, 'raid');\n"
    "    // [r056boss] R-056：免费次数改「每只 5 次」（event_boss_hits.free_used，随换 boss 归零），\n"
    "    //   每日不限次；节奏闸门 = 10 分钟冷却（event_boss_hits.last_strike_at）。\n"
    "    const mineQ = await dbGet('SELECT free_used, last_strike_at FROM event_boss_hits WHERE event_id = ? AND user_id = ?', [Number(ev.id), userId]).catch(() => null);\n"
    "    const freeUsed = Math.max(0, Math.floor(Number(mineQ && mineQ.free_used) || 0));\n"
    "    if (freeUsed >= ACT_BOSS_FREE_STRIKES) {\n"
    "      return res.status(409).json({ error: `本只妖兽的免费出手已用尽（${ACT_BOSS_FREE_STRIKES} 次），可用诛妖符追加或等下一只现身` });\n"
    "    }\n"
    "    const lastAt = Math.max(0, Math.floor(Number(mineQ && mineQ.last_strike_at) || 0));\n"
    "    const coolMs = lastAt > 0 ? ACT_BOSS_STRIKE_COOLDOWN_MS - (now - lastAt) : 0;\n"
    "    if (coolMs > 0) {\n"
    "      return res.status(409).json({ error: `出手冷却中，还需 ${Math.ceil(coolMs / 1000)} 秒` });\n"
    "    }\n"
)

# E8 strike 响应：freeLeft 按 freeUsed 计；回 coolLeft=冷却窗全长（客户端倒计时锚）
E8_OLD = "      freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - used - 1),\n"
E8_NEW = (
    "      freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - freeUsed - 1),\n"
    "      coolLeft: ACT_BOSS_STRIKE_COOLDOWN_MS,\n"
)

# E9/E10 两个同形调用点（用前置注释行区分；expect=1 各自命中）
E9_OLD = (
    "    // ② 守卫式扣血 + ③ 记分（被他人抢先击杀则补偿撤位）\n"
    "    let hit: { score: number; total: number; killed: boolean; hpCur: number };\n"
    "    try {\n"
    "      hit = await actBossHitOnce(userId, Number(ev.id), now);"
)
E9_NEW = (
    "    // ② 守卫式扣血 + ③ 记分（被他人抢先击杀则补偿撤位）\n"
    "    let hit: { score: number; total: number; killed: boolean; hpCur: number };\n"
    "    try {\n"
    "      hit = await actBossHitOnce(userId, Number(ev.id), now, true);"
)
E10_OLD = (
    "    // ③ 守卫式扣血 + 记分（被他人抢先击杀则退灵石 + 删行，全或无）\n"
    "    let hit: { score: number; total: number; killed: boolean; hpCur: number };\n"
    "    try {\n"
    "      hit = await actBossHitOnce(userId, Number(ev.id), now);"
)
E10_NEW = (
    "    // ③ 守卫式扣血 + 记分（被他人抢先击杀则退灵石 + 删行，全或无）\n"
    "    let hit: { score: number; total: number; killed: boolean; hpCur: number };\n"
    "    try {\n"
    "      hit = await actBossHitOnce(userId, Number(ev.id), now, false);"
)

# E11 status mine SELECT 加列
E11_OLD = "    const mine = await dbGet('SELECT score, strikes FROM event_boss_hits WHERE event_id = ? AND user_id = ?', [Number(ev.id), userId]).catch(() => null);"
E11_NEW = "    const mine = await dbGet('SELECT score, strikes, free_used, last_strike_at FROM event_boss_hits WHERE event_id = ? AND user_id = ?', [Number(ev.id), userId]).catch(() => null);"

# E12 status 每日口径 → 每只口径 + 冷却剩余秒
E12_OLD = "    const usedFree = await actFunUsedToday(userId, 'raid');\n"
E12_NEW = (
    "    // [r056boss] R-056：freeLeft 改「每只 5 次」口径（free_used）；coolLeft = 免费出手冷却剩余秒。\n"
    "    const freeUsed = Math.max(0, Math.floor(Number(mine && mine.free_used) || 0));\n"
    "    const lastAtS = Math.max(0, Math.floor(Number(mine && mine.last_strike_at) || 0));\n"
    "    const coolLeft = lastAtS > 0 ? Math.max(0, Math.ceil((ACT_BOSS_STRIKE_COOLDOWN_MS - (Date.now() - lastAtS)) / 1000)) : 0;\n"
)

# E13 status 响应
E13_OLD = (
    "      freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - usedFree),\n"
    "      talismanLeft: Math.max(0, ACT_BOSS_TALISMAN_DAILY - usedTal),\n"
)
E13_NEW = (
    "      freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - freeUsed),\n"
    "      talismanLeft: Math.max(0, ACT_BOSS_TALISMAN_DAILY - usedTal),\n"
    "      bossNo: Math.max(1, Math.floor(Number(boss.boss_no) || 1)),\n"
    "      bossMax: ACT_BOSS_MAX_BOSSES,\n"
    "      coolLeft,\n"
)

EDITS = [
    ("E1 常量 3→5 + 三个新常量", E1_OLD, E1_NEW),
    ("E2 DDL 幂等加列块（插在聚合索引前）", E2_ANCHOR, E2_BLOCK + E2_ANCHOR),
    ("E3 ensure lazy 刷新下一只", E3_OLD, E3_NEW),
    ("E4 hitOnce 签名 + isFree", E4_OLD, E4_NEW),
    ("E5 upsert 写 free_used/last_strike_at", E5_OLD, E5_NEW),
    ("E6 击杀当场刷新下一只", E6_OLD, E6_NEW),
    ("E7 strike 配额块（每只5次+冷却）", E7_OLD, E7_NEW),
    ("E8 strike 响应 freeLeft/coolLeft", E8_OLD, E8_NEW),
    ("E9 strike 调用 true", E9_OLD, E9_NEW),
    ("E10 talisman 调用 false", E10_OLD, E10_NEW),
    ("E11 status mine 加列", E11_OLD, E11_NEW),
    ("E12 status 每只口径 + coolLeft", E12_OLD, E12_NEW),
    ("E13 status 响应 bossNo/bossMax/coolLeft", E13_OLD, E13_NEW),
]

# 前置依赖（本环只读这些串做自证，不改）
REQUIRES = [
    ("const ACT_BOSS_TALISMAN_DAILY = 2;", 1, "诛妖符常量在位（本环不动）"),
    ("const ACT_BOSS_HP_CYCLE = 20;", 1, "血量期数系数在位（本环复用）"),
    ("const ACT_BOSS_TRUCE_MS = 2 * 24 * 60 * 60 * 1000;", 1, "休战期常量在位（本环不动）"),
    ("const hp = Math.floor(WB_HP_BASE * mult * ACT_BOSS_HP_CYCLE);", 1, "基础血量行在位（reward089 冻结锚，本环不碰）"),
    ("const safeAddColumn = (table: string, col: string, ddl: string) => {", 1, "幂等加列工具在位（E2 复用）"),
    ("app.get('/api/eventboss/status'", 1, "状态端点在位"),
    ("app.post('/api/eventboss/strike'", 1, "出手端点在位"),
    ("app.post('/api/eventboss/talisman'", 1, "诛妖符端点在位"),
    ("[userId, utcDateStr(), 'raid', used + 1,", 1, "fun_daily 审计行在位（本环保留）"),
    ("async function actBossEnsure(eventId: number): Promise<any> {", 1, "lazy 建场函数在位"),
    ("今日诛妖符已用尽", 1, "诛妖符 409 文案在位（本环不动）"),
    ("UPDATE event_boss SET settled = 1, settled_at = ? WHERE event_id = ?", 1, "结算置位在位（本环不动）"),
]

# 冻结基线（打补丁前统计，打完后必须不变或按注记 +N）
BASE_NEEDLES = ["res.status(403", "setInterval(", "require(", "PRAGMA",
                "ACT_BOSS_TALISMAN_DAILY", "ACT_BOSS_HP_CYCLE",
                "boss_raid:    { name: '万妖巢穴'",
                "INSERT OR IGNORE INTO event_boss (event_id, hp_max, hp_cur)",
                "actBossHitOnce(userId, Number(ev.id), now)"]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-056 万妖巢穴多 boss 环")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：已打过本环
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点计数（仅插入型改动要求 new 包含锚原文防自毁；常数/语句替换型 old 不进 new 是本意）
    INSERTION_EDITS = {"E2 DDL 幂等加列块（插在聚合索引前）"}
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:120]))
        if old == new:
            fail("%s old == new" % name)
        if name in INSERTION_EDITS and old not in new:
            fail("%s 自毁防线：new 未包含锚点原文" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    gates = [
        # ---- 本环改动 ----
        ("R56 免费次数已改 5/只", "const ACT_BOSS_FREE_STRIKES = 5;", 1),
        ("R56 旧 3 次/日已清零", "const ACT_BOSS_FREE_STRIKES = 3;", 0),
        ("R56 boss 总数常量", "const ACT_BOSS_MAX_BOSSES = 5;", 1),
        ("R56 冷却常量 10 分钟", "const ACT_BOSS_STRIKE_COOLDOWN_MS = 10 * 60 * 1000;", 1),
        ("R56 血量成长常量", "const ACT_BOSS_HP_GROWTH = 0.5;", 1),
        ("R56 加列 boss_no", "ALTER TABLE event_boss ADD COLUMN boss_no INTEGER NOT NULL DEFAULT 1", 1),
        ("R56 加列 free_used", "ALTER TABLE event_boss_hits ADD COLUMN free_used INTEGER NOT NULL DEFAULT 0", 1),
        ("R56 加列 last_strike_at", "ALTER TABLE event_boss_hits ADD COLUMN last_strike_at INTEGER NOT NULL DEFAULT 0", 1),
        ("R56 upsert 写 free_used", "free_used = free_used + excluded.free_used", 1),
        ("R56 upsert 写 last_strike_at", "last_strike_at = excluded.last_strike_at", 1),
        ("R56 hitOnce 带 isFree", "isFree: boolean", 1),
        ("R56 strike 调用 true", "hit = await actBossHitOnce(userId, Number(ev.id), now, true);", 1),
        ("R56 talisman 调用 false", "hit = await actBossHitOnce(userId, Number(ev.id), now, false);", 1),
        ("R56 旧调用形态已清零", "hit = await actBossHitOnce(userId, Number(ev.id), now);", 0),
        ("R56 本只口径 409 文案", "本只妖兽的免费出手已用尽", 1),
        ("R56 冷却 409 文案", "出手冷却中，还需", 1),
        ("R56 旧每日 409 文案已清零", "今日免费出手已用尽", 0),
        ("R56 击杀当场刷新（hitOnce）", "const nextR = noR + 1;", 1),
        ("R56 lazy 刷新（ensure）", "const nextNo = no0 + 1;", 1),
        ("R56 换 boss 归零 free_used ×2", "UPDATE event_boss_hits SET free_used = 0 WHERE event_id = ?", 2),
        ("R56 刷新守卫 killed=1 ×2", "killed = 0, killer_id = NULL WHERE event_id = ? AND killed = 1", 2),
        ("R56 刷新守卫 settled=0（ensure）", "Number(row.settled) !== 1", 1),
        ("R56 刷新守卫 settled=0（hitOnce）", "Number(curR && curR.settled) !== 1", 1),
        ("R56 status 回执 bossNo", "bossNo: Math.max(1, Math.floor(Number(boss.boss_no) || 1)),", 1),
        ("R56 status 回执 bossMax", "bossMax: ACT_BOSS_MAX_BOSSES,", 1),
        ("R56 status 回执 coolLeft", "      coolLeft,", 1),
        ("R56 strike 回执 coolLeft 全长", "coolLeft: ACT_BOSS_STRIKE_COOLDOWN_MS,", 1),
        ("R56 status 冷却剩余秒", "ACT_BOSS_STRIKE_COOLDOWN_MS - (Date.now() - lastAtS)", 1),
        ("R56 幂等标记就位", MARK, 9),
        # ---- 冻结：邻面一字不动 ----
        ("冻结 诛妖符常量未动", "const ACT_BOSS_TALISMAN_DAILY = 2;", 1),
        ("冻结 血量期数系数未动", "const ACT_BOSS_HP_CYCLE = 20;", 1),
        ("冻结 休战期未动", "const ACT_BOSS_TRUCE_MS = 2 * 24 * 60 * 60 * 1000;", 1),
        ("冻结 reward089 血量行恰 1", "const hp = Math.floor(WB_HP_BASE * mult * ACT_BOSS_HP_CYCLE);", 1),
        ("冻结 talisman 409 文案未动", "今日诛妖符已用尽", 1),
        ("冻结 结算置位未动", "UPDATE event_boss SET settled = 1, settled_at = ? WHERE event_id = ?", 1),
        ("冻结 建场 INSERT 未动", "INSERT OR IGNORE INTO event_boss (event_id, hp_max, hp_cur)", 1),
        ("冻结 fun_daily 审计行未动", "[userId, utcDateStr(), 'raid', used + 1,", 1),
        ("冻结 三端点仍在", "app.post('/api/eventboss/strike'", 1),
        # ---- 红线 ----
        ("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]),
        ("红线 未新增 require(", "require(", base["require("]),
        ("红线 未新增 setInterval", "setInterval(", base["setInterval("]),
        ("红线 PRAGMA 仅 +2（E2 两处加列守卫）", "PRAGMA", base["PRAGMA"] + 2),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-42s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 7) 语义自证：引用计数闭合（各常量 = 定义 + 全部引用，无悬挂无遗漏）
    sem_ok = (
        out.count("ACT_BOSS_FREE_STRIKES") == 5   # 定义 + status freeLeft + strike 检查 + strike 409 文案(模板串) + strike 响应
        and out.count("ACT_BOSS_MAX_BOSSES") == 4  # 定义 + ensure 刷新 + hitOnce 刷新 + status bossMax
        and out.count("ACT_BOSS_STRIKE_COOLDOWN_MS") == 4  # 定义 + strike 检查 + strike 回执 + status 计算
        and out.count("SELECT free_used, last_strike_at FROM event_boss_hits") == 1
        and out.count("SELECT score, strikes, free_used, last_strike_at FROM event_boss_hits") == 1
    )
    ok = ok and sem_ok
    print("  [%s] %-42s FREE=%d MAX=%d CD=%d"
          % ("OK" if sem_ok else "FAIL", "R56 语义自证(引用计数闭合)",
             out.count("ACT_BOSS_FREE_STRIKES"), out.count("ACT_BOSS_MAX_BOSSES"),
             out.count("ACT_BOSS_STRIKE_COOLDOWN_MS")))

    if not ok:
        fail("门禁未全绿，未写回")

    # 8) 往返自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r056boss-", suffix=".tmp")
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
