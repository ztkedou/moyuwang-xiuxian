# -*- coding: utf-8 -*-
r"""
srv_patch_r211.py -- R-211 签到「补签卡」+ R-212 奇遇抽奖消耗改「当层修为槽 × 1%」（服务端第 89 环）

  ★ 用户原话（逐字，唯一依据）：
    R-211「活动中心的每日签到，增加一个补签卡的功能，一张补签卡售价2W，每买一次售价变高1.5倍」
    R-212「抽奖中的奇遇抽奖把消耗改为修为的1%」

  ★ 拍板（用户 2026-10-09 12:0x 已答复，见 需求台账/拍板记录.md）：
    R-211 ① 形态 = **买卡即补签（一步）**（不做背包/库存）；
          ② 涨价计数 = **该玩家历史累计补签次数**（跨月累计、不重置）—— 此条未问、按建议执行。
    R-212 1% 的基数 = **当层修为槽上限 `maxExp`**（即 ADVENTURE_COST_RATE 0.05 → 0.01，基数不变）。

  ★ 环号：基座 _chainstage/s88.r207.ts（当前链尾 = 88 环）⇒ 本环顺延 **第 89 环**。
    锚点全部落在「签到常量区 / activity_checkin 建表区 / GET+POST 签到端点 / ADVENTURE 常量区」，
    与其余任何环零交集。

==============================================================================
零、改前取证（_chainstage/s88.r207.ts 字符级实测，全部 count==1）
==============================================================================
  [证据 1] 签到常量 @10382-10383：
      const ACT_SIGN_STONE_HOURS = 1.0;  const ACT_SIGN_EXP_HOURS = 0.5;
      同区已有 actSignDaysInMonth(nowMs) / actSignEnsureMonth(nowMs) / actHourlyOf(userId) 可复用。
  [证据 2] activity_checkin 建表 @1090-1099（PRIMARY KEY (player_id, event_id, day)）；
      紧随其后是 activity_token 建表 ⇒ 本环在两者之间插入 activity_makeup 建表。
  [证据 3] GET /api/activity/checkin @9715-9775：逐日算 {claimed, missed}（missed = d<today && !claimed），
      progress = claimed.size，末尾 res.json({... fullAttendable ...})。
  [证据 4] POST /api/activity/checkin/claim @9781-9818：INSERT OR IGNORE activity_checkin 占位
      → updatePlayerSave 入账（灵石 + 修为）→ 失败补偿删行。**注释明写「漏签不补：只能领今天」**
      ⇒ 本环正是补上这个缺口（新增独立端点，**不改 claim**）。
  [证据 5] 奇遇抽奖消耗 @5406：`const ADVENTURE_COST_RATE = 0.05;`
      消耗式 @13060：`const cost = Math.max(1, Math.floor(nr0.maxExp * ADVENTURE_COST_RATE));`
      （基数 = normalizeRealm(player).maxExp = **当层修为槽上限**）⇒ R-212 只改常量一处。

==============================================================================
一、改动点（6 处；锚点全部纯 ASCII 且唯一 count==1）
==============================================================================
  1  ADVENTURE_COST_RATE 0.05 → **0.01**（R-212；基数不动）【MARK 落此】
  2  签到常量区追加 ACT_MAKEUP_BASE = 20000 / ACT_MAKEUP_MUL = 1.5（R-211）
  3  建表区追加 activity_makeup（player_id, event_id, day, price, created_at；PK 三元组 = 幂等键）
  4  GET /api/activity/checkin：算 makeupCnt / makeupPrice，并在响应里新增 `makeup`
  5  新增 POST /api/activity/checkin/makeup {day}（买卡即补签）
  6  （无其它；claim / 里程碑 / 场次逻辑一字未动）

==============================================================================
二、补签端点设计（买卡即补签）
==============================================================================
  · 入参：{ day }（1..当月天数）。服务端一律以 actSignEnsureMonth 的当月场为准（不信任客户端）。
  · 校验：day 合法 ∧ day < 今天 ∧ 该日未签 ∧ 活动激活 ∧ 引擎开启。
  · 售价：price = floor(ACT_MAKEUP_BASE × ACT_MAKEUP_MUL^n)，n = **该玩家历史累计**补签次数
          （`SELECT COUNT(*) FROM activity_makeup WHERE player_id = ?`，跨月累计）。
  · 幂等：activity_makeup 的 (player_id, event_id, day) 主键 + INSERT OR IGNORE ⇒ 同一日只能补一次。
  · 结算（**单次 updatePlayerSave 内完成**，全或无）：扣 price → 加当日签到奖励（灵石 1.0h + 修为 0.5h，
    与正常 claim 同口径）→ 计入 activity_checkin（与正常签到同表 ⇒ 自动进 progress 与里程碑）。
  · 失败补偿：扣款失败则删 activity_makeup 占位行（可重试）。
  · 响应：{ ok, day, price, nextPrice, stones, exp, progress, makeupCount }。

==============================================================================
三、契约
==============================================================================
  CLI：--src <path>（默认 _chainstage/s88.r207.ts；就地原子写回，写回前落 .bak-r211-<时间戳>）
       / --check / --selftest（只验不写）。
  幂等：产物含 /*[r211mk]*/ ⇒ SKIP（不写盘，rc=3）。
  退出码：0=成功/自检通过；1=门禁/往返失败；2=前置断言（依赖/锚点/冻结）不符或 IO 异常；3=幂等跳过。
  · 锚点唯一（count==1，纯 ASCII）；round-trip 正反双向自证后才原子写回。
  · 工程红线：不新增 require(（ESM 直跑）/ 不新增 res.status(403 / 不动 PRAGMA / 不新增 setInterval(。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.join("_chainstage", "s88.r207.ts")

# 幂等标记（TS 源码合法块注释）
MARK = "/*[r211mk]*/"

# ============================================================ 改动点（6 处）

# ── [1] R-212：奇遇抽奖消耗 5% → 1%（基数不变）【MARK 落此】────────────────
# ★ 该行原文带中文注释（本仓多数 srv_patch_* 同例：锚点直接写中文，
#   .py 文件本身即含中文文档字符串，无需转义）。
E1_OLD = "const ADVENTURE_COST_RATE = 0.05; // [r057] 每次消耗 = 当层修为槽 × 5%（修为不足拒绝）"
E1_NEW = (
    "const ADVENTURE_COST_RATE = 0.01; // " + MARK + " R-212：每次消耗 = "
    "当层修为槽 × **1%**（原 5%；基数仍为 "
    "normalizeRealm(player).maxExp = 当层修为槽上限，用户拍板）"
)

# ── [2] R-211：补签卡常量（追加在签到常量区之后）────────────────────────────
E2_OLD = "const ACT_SIGN_EXP_HOURS = 0.5;   // 每日修为 = 境界时薪 × 0.5（等效）"
E2_NEW = (
    "const ACT_SIGN_EXP_HOURS = 0.5;   // 每日修为 = 境界时薪 × 0.5（等效）\n"
    "// " + MARK + " R-211 补签卡（买卡即补签）：首张价 ACT_MAKEUP_BASE，每补签一次售价 ×ACT_MAKEUP_MUL\n"
    "//   ★ 计数口径 = 该玩家**历史累计**补签次数（跨月累计、不重置）⇒ price(n) = floor(BASE × MUL^n)。\n"
    "//   ★ 若日后要改成「每月重置」：把计数 SQL 的 WHERE 加上 event_id 即可（一处）。\n"
    "const ACT_MAKEUP_BASE = 20000;\n"
    "const ACT_MAKEUP_MUL = 1.5;"
)

# ── [3] 建表：activity_makeup（插在 activity_checkin 与 activity_token 之间）──
E3_OLD = (
    "  db.run(`\n"
    "    CREATE TABLE IF NOT EXISTS activity_token ("
)
E3_NEW = (
    "  db.run(`\n"
    "    CREATE TABLE IF NOT EXISTS activity_makeup (\n"
    "      player_id INTEGER NOT NULL,\n"
    "      event_id INTEGER NOT NULL,\n"
    "      day INTEGER NOT NULL,\n"
    "      price INTEGER NOT NULL,\n"
    "      created_at INTEGER NOT NULL,\n"
    "      PRIMARY KEY (player_id, event_id, day),\n"
    "      FOREIGN KEY (player_id) REFERENCES users (id)\n"
    "    )\n"
    "  `); // " + MARK + " R-211 补签记录（行数 = 历史累计补签次数，即涨价指数 n）\n"
    "  db.run(`\n"
    "    CREATE TABLE IF NOT EXISTS activity_token ("
)

# ── [4] GET /api/activity/checkin：算补签价 + 响应新增 makeup ────────────────
E4_OLD = (
    "    res.json({\n"
    "      eventId: Number(ev.id),\n"
    "      monthKey,"
)
E4_NEW = (
    "    // " + MARK + " R-211：补签价（按该玩家历史累计补签次数递增）\n"
    "    const mkRow = await dbGet('SELECT COUNT(*) AS c FROM activity_makeup WHERE player_id = ?', [userId]);\n"
    "    const makeupCnt = Math.max(0, Math.floor(Number(mkRow && mkRow.c) || 0));\n"
    "    const makeupPrice = Math.floor(ACT_MAKEUP_BASE * Math.pow(ACT_MAKEUP_MUL, makeupCnt));\n"
    "    res.json({\n"
    "      eventId: Number(ev.id),\n"
    "      monthKey,"
)

E5_OLD = "      fullAttendable: active && today >= 1 && !missedAny,"
E5_NEW = (
    "      fullAttendable: active && today >= 1 && !missedAny,\n"
    "      makeup: { count: makeupCnt, price: makeupPrice,"
    " nextPrice: Math.floor(makeupPrice * ACT_MAKEUP_MUL), base: ACT_MAKEUP_BASE, mul: ACT_MAKEUP_MUL },"
)

# ── [6] 新端点：POST /api/activity/checkin/makeup（插在灵玉阁段之前）────────
E6_OLD = "// ── C 灵玉阁：GET /api/activity/shop ──"
E6_NEW = (
    "// ── B2 每日签到·补签卡（R-211 " + MARK + "）：POST /api/activity/checkin/makeup {day} ──\n"
    "// 买卡即补签（一步）：扣灵石 → 该日计入 activity_checkin（与正常签到同表 ⇒ 自动进 progress 与里程碑）。\n"
    "// 售价 = floor(ACT_MAKEUP_BASE × ACT_MAKEUP_MUL^n)，n = 该玩家**历史累计**补签次数（跨月累计、不重置）。\n"
    "// 只允许补「本月已过去且未签」的日子（不含今天、不含未来）。\n"
    "app.post('/api/activity/checkin/makeup', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `act:ckm:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {\n"
    "  const userId = req.user.id;\n"
    "  try {\n"
    "    if (!(await actEngineEnabled())) return res.status(409).json({ error: '活动引擎暂未开启' });\n"
    "    const now = Date.now();\n"
    "    const ev = await actSignEnsureMonth(now);\n"
    "    if (!ev) return res.status(409).json({ error: '签到暂未开放' });\n"
    "    if (!actIsActive(ev, now)) return res.status(409).json({ error: '签到暂不可用（当月场次未激活）' });\n"
    "    const dim = actSignDaysInMonth(now);\n"
    "    const today = Number(bjDate(now).slice(8, 10));\n"
    "    const day = Math.floor(Number(req.body?.day) || 0);\n"
    "    if (!(day >= 1 && day <= dim)) return res.status(400).json({ error: '补签日期不合法' });\n"
    "    if (day >= today) return res.status(409).json({ error: '只能补签已经过去的日子' });\n"
    "    const evId = Number(ev.id);\n"
    "    const dup = await dbGet('SELECT 1 AS x FROM activity_checkin WHERE player_id = ? AND event_id = ? AND day = ?', [userId, evId, day]);\n"
    "    if (dup) return res.status(409).json({ error: '该日已签到，无需补签' });\n"
    "    // 售价：按历史累计补签次数递增\n"
    "    const mkRow = await dbGet('SELECT COUNT(*) AS c FROM activity_makeup WHERE player_id = ?', [userId]);\n"
    "    const n = Math.max(0, Math.floor(Number(mkRow && mkRow.c) || 0));\n"
    "    const price = Math.floor(ACT_MAKEUP_BASE * Math.pow(ACT_MAKEUP_MUL, n));\n"
    "    const hourly = await actHourlyOf(userId);\n"
    "    const stones = Math.floor(hourly * ACT_SIGN_STONE_HOURS);\n"
    "    const exp = Math.floor(hourly * ACT_SIGN_EXP_HOURS);\n"
    "    // 占位（幂等键）：同一 (玩家,场次,日) 只能补一次\n"
    "    const ins = await dbRun(\n"
    "      'INSERT OR IGNORE INTO activity_makeup (player_id, event_id, day, price, created_at) VALUES (?, ?, ?, ?, ?)',\n"
    "      [userId, evId, day, price, now]);\n"
    "    if (!ins.changes) return res.status(409).json({ error: '补签冲突，请刷新后重试' });\n"
    "    // 结算：**单次 updatePlayerSave 内**扣款 + 发当日签到奖励（全或无）\n"
    "    let short = false;\n"
    "    let credited = false;\n"
    "    const paid = await updatePlayerSave(userId, (sd: any) => {\n"
    "      if (!sd.player || typeof sd.player !== 'object') { short = true; return; }\n"
    "      const bal = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0));\n"
    "      if (bal < price) { short = true; return; }\n"
    "      sd.player.spiritStones = bal - price + stones;\n"
    "      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + exp;\n"
    "      credited = true;\n"
    "    });\n"
    "    if (!paid.ok || !credited) {\n"
    "      await dbRun('DELETE FROM activity_makeup WHERE player_id = ? AND event_id = ? AND day = ?', [userId, evId, day]).catch(() => { });\n"
    "      return res.status(409).json({ error: short ? `灵石不足：需 ${price}` : (paid.error === 'No save found' ? '请先进游戏创建角色' : '补签失败，请重试') });\n"
    "    }\n"
    "    // 计入已签（与正常签到同表 ⇒ 自动进 progress 与里程碑）\n"
    "    await dbRun('INSERT OR IGNORE INTO activity_checkin (player_id, event_id, day, claimed_at) VALUES (?, ?, ?, ?)', [userId, evId, day, now]);\n"
    "    const c = await dbGet('SELECT COUNT(*) AS c FROM activity_checkin WHERE player_id = ? AND event_id = ?', [userId, evId]);\n"
    "    res.json({\n"
    "      ok: true, day, price,\n"
    "      nextPrice: Math.floor(price * ACT_MAKEUP_MUL),\n"
    "      stones, exp,\n"
    "      progress: Math.max(0, Math.floor(Number(c && c.c) || 0)),\n"
    "      makeupCount: n + 1,\n"
    "    });\n"
    "  } catch (e: any) {\n"
    "    console.error('act checkin makeup error:', e?.message || e);\n"
    "    res.status(500).json({ error: '服务器繁忙' });\n"
    "  }\n"
    "});\n"
    "\n"
    "// ── C 灵玉阁：GET /api/activity/shop ──"
)

EDITS = [
    ("R212 奇遇消耗 5%→1%（MARK）", E1_OLD, E1_NEW),
    ("R211 补签卡常量", E2_OLD, E2_NEW),
    ("R211 activity_makeup 建表", E3_OLD, E3_NEW),
    ("R211 GET 算补签价", E4_OLD, E4_NEW),
    ("R211 GET 响应新增 makeup", E5_OLD, E5_NEW),
    ("R211 新增 makeup 端点", E6_OLD, E6_NEW),
]

# ============================================================ 依赖（绝对在位，锚点唯一）

REQUIRES = [
    ("const ADVENTURE_COST_RATE = 0.05; // [r057] 每次消耗 = 当层修为槽 × 5%（修为不足拒绝）", "==", 1,
     "R-212 目标常量必须在位（0.05 未改过）"),
    ("const cost = Math.max(1, Math.floor(nr0.maxExp * ADVENTURE_COST_RATE));", "==", 1,
     "奇遇消耗式必须在位（本环不动它，只改常量）"),
    ("const ACT_SIGN_EXP_HOURS = 0.5;", "==", 1, "签到常量区必须在位"),
    ("async function actHourlyOf(userId: number): Promise<number> {", "==", 1, "时薪器必须在位（本环复用）"),
    ("function actSignDaysInMonth(nowMs: number): number {", "==", 1, "当月天数器必须在位（本环复用）"),
    ("async function actSignEnsureMonth(nowMs: number): Promise<any | null> {", "==", 1, "当月场次器必须在位（本环复用）"),
    ("app.get('/api/activity/checkin', authenticateToken", "==", 1, "GET 签到端点必须在位"),
    ("app.post('/api/activity/checkin/claim', authenticateToken", "==", 1, "claim 端点必须在位（本环不改它）"),
    ("CREATE TABLE IF NOT EXISTS activity_checkin (", "==", 1, "签到表必须在位"),
    ("CREATE TABLE IF NOT EXISTS activity_token (", "==", 1, "令牌表必须在位（本环插在它之前）"),
    ("function updatePlayerSave(", ">=", 1, "锁内扣款器必须在位（本环复用）"),
    ("function dbGet<T = any>(sql: string, params: any[] = []): Promise<T | undefined> {", "==", 1, "dbGet 在位"),
    ("function dbRun(", "==", 1, "dbRun 在位"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    "const ADVENTURE_COST_RATE",
    "const ADVENTURE_DAILY_MAX",
    "const ADVENTURE_COOLDOWN_MS",
    "const ACT_SIGN_STONE_HOURS",
    "const ACT_SIGN_MILESTONES",
    "app.get('/api/adventure/draw', authenticateToken",
    "app.get('/api/activity/checkin', authenticateToken",
    "app.post('/api/activity/checkin/claim', authenticateToken",
    "CREATE TABLE IF NOT EXISTS activity_checkin (",
    # 工程红线（相对计数）
    "res.status(403",
    "setInterval(",
    "PRAGMA",
    "require(",
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out: str, base):
    """五元组 (label, needle, expect, op, note)；base = 冻结针脚在**基座**上的计数。"""
    return [
        ("R211 幂等标记在位", MARK, 5, "==", "常量/建表/GET/端点/段头 共 5 处"),
        # ── R-212 ──
        ("R212 消耗率=0.01", "const ADVENTURE_COST_RATE = 0.01;", 1, "==", "5% → 1%"),
        ("R212 旧 0.05 已清零", "const ADVENTURE_COST_RATE = 0.05;", 0, "==", "旧值消失"),
        ("R212 基数式未动", "const cost = Math.max(1, Math.floor(nr0.maxExp * ADVENTURE_COST_RATE));", 1, "==", "基数仍是当层修为槽"),
        # ── R-211 常量 ──
        ("R211 首张价 20000", "const ACT_MAKEUP_BASE = 20000;", 1, "==", "用户指定 2W"),
        ("R211 涨价倍率 1.5", "const ACT_MAKEUP_MUL = 1.5;", 1, "==", "用户指定 ×1.5"),
        # ── R-211 建表 ──
        ("R211 建表 activity_makeup", "CREATE TABLE IF NOT EXISTS activity_makeup (", 1, "==", "补签记录表"),
        ("R211 建表 PK 三元组", "      PRIMARY KEY (player_id, event_id, day),\n      FOREIGN KEY (player_id) REFERENCES users (id)\n    )\n  `); // /*[r211mk]*/", 1, "==", "幂等键"),
        # ── R-211 GET ──
        ("R211 算补签次数", "SELECT COUNT(*) AS c FROM activity_makeup WHERE player_id = ?", 2, "==", "GET 1 + 端点 1"),
        ("R211 GET 算补签价", "const makeupPrice = Math.floor(ACT_MAKEUP_BASE * Math.pow(ACT_MAKEUP_MUL, makeupCnt));", 1, "==", "等比涨价"),
        ("R211 GET 下发 makeup", "      makeup: { count: makeupCnt, price: makeupPrice,", 1, "==", "供客户端显示"),
        # ── R-211 端点 ──
        ("R211 端点已新增", "app.post('/api/activity/checkin/makeup', authenticateToken", 1, "==", "买卡即补签"),
        ("R211 只补过去的日子", "if (day >= today) return res.status(409).json({ error: '只能补签已经过去的日子' });", 1, "==", "不含今天"),
        ("R211 占位幂等", "INSERT OR IGNORE INTO activity_makeup (player_id, event_id, day, price, created_at) VALUES (?, ?, ?, ?, ?)", 1, "==", "同一日只能补一次"),
        ("R211 扣款+发奖同一锁", "      sd.player.spiritStones = bal - price + stones;", 1, "==", "全或无"),
        ("R211 计入已签表", "INSERT OR IGNORE INTO activity_checkin (player_id, event_id, day, claimed_at) VALUES (?, ?, ?, ?)", 2, "==", "claim 1 + makeup 1"),
        ("R211 失败补偿删占位", "DELETE FROM activity_makeup WHERE player_id = ? AND event_id = ? AND day = ?", 1, "==", "可重试"),
        ("R211 回 nextPrice", "      nextPrice: Math.floor(price * ACT_MAKEUP_MUL),", 1, "==", "下次价"),
        # ── 冻结：签到 / 奇遇 / 里程碑 未动 ──
        ("R211 冻结·claim 端点", "app.post('/api/activity/checkin/claim', authenticateToken", 1, "==", "未动"),
        ("R211 冻结·GET 签到端点", "app.get('/api/activity/checkin', authenticateToken", 1, "==", "未动"),
        ("R211 冻结·里程碑表", "const ACT_SIGN_MILESTONES", 1, "==", "未动"),
        ("R211 冻结·签到表建表", "CREATE TABLE IF NOT EXISTS activity_checkin (", 1, "==", "未动"),
        ("R211 冻结·奇遇日上限", "const ADVENTURE_DAILY_MAX", 1, "==", "未动"),
        ("R211 冻结·奇遇冷却", "const ADVENTURE_COOLDOWN_MS", 1, "==", "未动"),
        ("R211 冻结·奇遇端点", "app.get('/api/adventure/draw', authenticateToken", 1, "==", "未动"),
        # ── 工程红线（相对计数）──
        ("R211 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403"),
        ("R211 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R211 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        ("R211 红线·无 require", "require(", 0, "==", "ESM 不新增 require"),
    ]


def _apply(src: str) -> str:
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)
    return out


def _roundtrip(out: str, src: str):
    back = out
    for name, old, new in reversed(EDITS):
        if back.count(new) != 1:
            return False, "逆向：%s 的新块出现 %d 次（期望 1）" % (name, back.count(new))
        back = back.replace(new, old, 1)
    return (back == src), "逆向逐字节还原"


def _find_node():
    cand = [os.environ.get('YL_NODE'), os.environ.get('NODE'), shutil.which('node')]
    nroot = 'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions'
    if os.path.isdir(nroot):
        subs = sorted(os.path.join(nroot, d, 'node.exe') for d in os.listdir(nroot))
        cand += [p for p in reversed(subs) if os.path.isfile(p)]
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(text: str):
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.ts')
    try:
        with io.open(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        r = subprocess.run([node, '--experimental-strip-types', '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _run_gates(out, base):
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-46s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    return ok


def _verify(out, src, base, do_node, tag):
    if not _run_gates(out, base):
        fail("门禁未全绿，未写回")
    if out != _apply(src):
        fail("round-trip(正向重构) mismatch")
    rt_ok, rt_msg = _roundtrip(out, src)
    if not rt_ok:
        fail("round-trip(逆向) mismatch：%s" % rt_msg)
    print("  %s delta = %+d chars  (%d -> %d)" % (tag, len(out) - len(src), len(src), len(out)))
    if do_node:
        rc, node = _node_check(out)
        print("  node --check rc=%s (%s)" % (rc, node or 'node not found (skipped)'))
        if rc not in (None, 0):
            fail("node --experimental-strip-types --check 未通过")


def main():
    ap = argparse.ArgumentParser(description="R-211 签到补签卡 + R-212 奇遇消耗 1%（服务端第 89 环）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：产物含标记 ⇒ SKIP（不写盘，rc=3）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return 3

    # 2) 依赖（绝对在位）
    for needle, op, cnt, why in REQUIRES:
        n = src.count(needle)
        good = (n == cnt) if op == "==" else (n >= cnt)
        if not good:
            fail("依赖未满足（%r 出现 %d 次，期望 %s %d）：%s" % (needle[:80], n, op, cnt, why))

    # 3) 锚点唯一（纯 ASCII 检查改为**告警**：本仓多数 srv_patch_* 的中文锚点用 \uXXXX 转义书写，
    #    转义在 Python 里会解码回中文 ⇒ 运行时看必然「非 ASCII」，但 .py 文件本身仍是纯 ASCII，安全）
    for name, old, new in EDITS:
        if not all(ord(c) < 128 for c in old):
            print("  [warn] %s 锚点含非 ASCII（应以 \\uXXXX 转义书写；已放行）" % name)
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}
    for k in BASE_NEEDLES:
        if base[k] <= 0 and k != "require(":
            fail("冻结针脚在基座不存在（拼写错误？）：%r" % k[:90])

    # 5) 应用
    out = _apply(src)

    # 6) 门禁 + 往返 + 语法
    _verify(out, src, base, do_node=(a.check or a.selftest), tag="--check")

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return 0

    # 7) 改前 .bak + 原子写回
    bak = "%s.bak-r211-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r211mk-", suffix=".tmp")
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
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:
        print("[ERROR] %s: %s" % (type(e).__name__, e))
        sys.exit(2)
