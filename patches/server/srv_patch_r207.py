# -*- coding: utf-8 -*-
r"""
srv_patch_r207.py -- R-198 心法「点一次加经验，不再每次升一级」+ 大幅提高点一次灵石（服务端第 88 环）

  ★ 用户原话（R-198，逐字，唯一依据）：
    「心法学习也变成点一次增加经验，不要每次升一级，并且大幅度提高点一次所需的灵石数量。」

  ★ 目标 = 仙务·心法六卷面板（客户端 YlxwTXinfa087，注册 YLXW_COMP.gongfa），服务端权威：
      GET /api/gongfa 取数、POST /api/gongfa/levelup 升级；现状「点一次 = 扣满整级价 → level+1」。

  ★ 环号：基座 _chainstage/s87.r201.ts（当前链尾 = 87 环）⇒ 本环顺延 **第 88 环**。
    锚点全部落在 [gongfacore] 纯逻辑块 + /api/gongfa + /api/gongfa/levelup，与其余任何环零交集。

==============================================================================
零、改前取证（_chainstage/s87.r201.ts 字符级实测）
==============================================================================
  [证据 1] 常量 @6947-6992：
    · GONGFA_MAX_LEVEL = 100（上限，本环不动）。
    · GONGFA_TIER_COST = [300,500,800,1200,2000,3000,5000,8000,12000,20000]（每 10 级一档）。
    · gongfaCostToReach(L) = TIER[floor((L-1)/10)] × 品级乘数（玄 ×1）⇒ 升 1 级单次价。
    · gongfaExpToReach(L) = 按段累计（玄品：L10=3000 / L50=48000 / L100=528000）。
    · gongfaLevelFromExp(exp) = 由累计 exp 反推等级（已存在，本环复用）。
  [证据 2] levelup @9194-9275（严格三段式）：
    · cost = gongfaCostToReach(curLevel+1)（**升 1 级 = 扣整级价**，正是用户说的「每次升一级」）。
    · 【占位】UPDATE level=level+1 WHERE level=旧值 →【扣款】锁内扣 cost →【补偿】回退 level。
    · 事后另有 exp += cost 的展示累加（exp 语义 = 累计投入灵石，满级 = 528000）。
  [证据 3] GET /api/gongfa @9131-9185：回显 per-key {level, exp, costNext, costToNext, ...} +
    全局 {maxLevel, tierCost, gradeMult, maxExpTotal=528000, balance}。

  ⇒ **最省事路径（团队裁示）**：把「点一次」从「扣满整级价 → level+1」改成
    「**扣固定价 P → exp += P → level 由 exp 反推**」，复用既有 exp / gongfaLevelFromExp，**无需新字段**。

==============================================================================
一、★ 数值设计（C 方案：每档恒定 3 次点击）
==============================================================================
  · 每级阈值表 ×**7.5**：新表 = [2250,3750,6000,9000,15000,22500,37500,60000,90000,150000]
    ⇒ 满级累计投入 528000 → **3,960,000**（×7.5）。
  · 每次点击单价 **P 按档位取表**（=现状档位价 ×2.5）= [750,1250,2000,3000,5000,7500,12500,20000,30000,50000]。
  · ⇒ 每档点击数 = 新阈值 / P = 7.5 / 2.5 = **3.000（全档位恒定 3 次）**，不再有低档一键跨级。
  · 单价倍数 = **2.5×**（每档都成立，vs 该档现状价）。
  · 用户第一诉求「点一次加经验、不要每次升一级」优先满足；总价 7.5 倍为 C 方案必然代价（团队裁示采纳）。

==============================================================================
二、★ 旧档 exp 兼容（必须明说，否则玩家等级会回退）
==============================================================================
  现状 exp = 旧口径累计投入（L50 → 48000）；本环阈值 ×3 后，由 exp 反推会把 L50 玩家算成 L33（回退）。
  处理（一次性、幂等、无需新字段）：点击时把 exp **对齐到当前等级的新口径下限**
      baseExp = max(旧 exp, gongfaExpToReach(curLevel))  →  nextExp = baseExp + P
  ⇒ 旧档首次点击后 exp 抬到新口径本级起点，level 不回退、后续点击自然推进；新档（exp≥下限）零影响。

==============================================================================
三、改动点（11 处；锚点全部纯 ASCII 且唯一 count==1）
==============================================================================
  1  GONGFA_TIER_COST 旧表 → 新表（×7.5）+ 新增按档位单价表 GONGFA_CLICK_COST（×2.5）
     + 取值器 gongfaClickCost(level)（MARK 落此）
  2  levelup：cost 由「按目标级计价」→ 按档位单价 gongfaClickCost(curLevel+1)，并预算 curExp/baseExp/nextExp/nextLevel
  3  levelup【占位】：UPDATE 由「level=level+1 WHERE level=旧值」→「exp=exp+P, level=反推 WHERE exp=旧值」
  4  levelup【占位·首建】：INSERT level=1,exp=0 → level=nextLevel,exp=nextExp
  5  levelup【补偿】：回退由「level 反向」→「exp 反向」（首建行按 nextExp 删行）
  6  levelup：删除事后 exp 二次累加；newLevel=nextLevel
  7  levelup 响应：exp = nextExp
  8  GET per-key：新增 levelExp / levelNeed（本级进度）
  9  GET per-key：costNext/costToNext = gongfaClickCost(shown+1)（点一次按档位价）
  10 GET 全局：新增 clickCost = GONGFA_CLICK_COST（单价表）

契约
--------------------------------------------------------------------------
  CLI：--src <path>（默认 _chainstage/s87.r201.ts；就地原子写回，写回前落 .bak-r207-<时间戳>）
       / --check / --selftest（只验不写）。
  幂等：产物含 /*[r207gf]*/ ⇒ SKIP（不写盘，rc=3）。
  退出码：0=成功/自检通过；1=门禁/往返失败；2=前置断言（依赖/锚点/冻结）不符或 IO 异常；3=幂等跳过。
  · 锚点唯一（count==1，纯 ASCII）；round-trip 正反双向自证后才原子写回。
  · 工程红线：不新增 require(（ESM 直跑）/ 不新增 res.status(403 / 不动 PRAGMA / 不新增 setInterval(。
  · 自证：--check rc=0 → 临时副本写回 → node --experimental-strip-types --check rc=0 → 复跑 SKIP rc=3。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.join("_chainstage", "s87.r201.ts")

# 幂等标记（TS 源码合法块注释）
MARK = "/*[r207gf]*/"

# ============================================================ 改动点（11 处）

# ── [1] 阈值表 ×7.5 + 按档位单价表 P + 取值器（MARK 落此）────────────────────
E1_OLD = "const GONGFA_TIER_COST = [300, 500, 800, 1200, 2000, 3000, 5000, 8000, 12000, 20000];"
E1_NEW = (
    "// [r207gf] R-198（C 方案）：心法改「点一次 +经验」（不再每次升一级），并大幅提高点一次灵石。\n"
    "//   ★ 覆盖上方 0.8.7 旧口径：\n"
    "//   ① 每级阈值表 ×7.5：满级累计投入 528000 → 3960000（7.5 倍）。\n"
    "//   ② 每次点击单价按档位取 P 表（=现状档位价 ×2.5）→ 每档点击数 = 7.5/2.5 = 3 次（全档恒定 3 次）。\n"
    "//   ③ 点击后 exp += P → 等级由 gongfaLevelFromExp 反推（不再每次必升一级）。\n"
    "const GONGFA_TIER_COST = [2250, 3750, 6000, 9000, 15000, 22500, 37500, 60000, 90000, 150000];\n"
    "const GONGFA_CLICK_COST = [750, 1250, 2000, 3000, 5000, 7500, 12500, 20000, 30000, 50000]; " + MARK + "\n"
    "// 升到 L 级的每次点击单价（按 L 所在档位取 P 表）；非法输入钳 1..100\n"
    "function gongfaClickCost(level: unknown): number {\n"
    "  const l = Math.min(GONGFA_MAX_LEVEL, Math.max(1, Math.floor(Number(level) || 1)));\n"
    "  const seg = Math.min(GONGFA_CLICK_COST.length - 1, Math.floor((l - 1) / 10));\n"
    "  return GONGFA_CLICK_COST[seg];\n"
    "}"
)

# ── [2] levelup：按档位单价 + 预算 exp/level（锚点=旧 cost 行，纯 ASCII）────────
E2_OLD = "    const cost = gongfaCostToReach(curLevel + 1);"
E2_NEW = (
    "    // [r207gf] R-198（C 方案）：本次点击单价按**目标等级所在档位**取 P 表（=现状档位价 ×2.5）。\n"
    "    //   exp += 单价，等级由 exp 反推（每档恒 3 次点击/级）。\n"
    "    //   ★ 旧档 exp 为旧口径（×1）：先对齐到当前等级的新口径下限（一次性、幂等），避免等级回退。\n"
    "    const curExp = Math.max(0, Math.floor(Number(row?.exp) || 0));\n"
    "    const baseExp = Math.max(curExp, gongfaExpToReach(curLevel));\n"
    "    const cost = gongfaClickCost(curLevel + 1);\n"
    "    const nextExp = baseExp + cost;\n"
    "    const nextLevel = Math.min(GONGFA_MAX_LEVEL, gongfaLevelFromExp(nextExp));"
)

# ── [3] levelup【占位】按 exp 推进（WHERE exp=旧值 ⇒ 同 exp 并发/连点只一方生效）──
E3_OLD = (
    "        'UPDATE player_gongfa SET level = level + 1, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?',\n"
    "        [userId, gid, curLevel]"
)
E3_NEW = (
    "        // [r207gf] R-198：占位改为「exp 累加 + level 反推」，WHERE exp=旧值保连点幂等。\n"
    "        'UPDATE player_gongfa SET exp = exp + ?, level = ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND exp = ?',\n"
    "        [cost, nextLevel, userId, gid, curExp]"
)

# ── [4] levelup【占位·首建】INSERT level=nextLevel,exp=nextExp ─────────────────
E4_OLD = "const ins = await dbRun('INSERT INTO player_gongfa (player_id, gongfa_id, level, exp) VALUES (?, ?, 1, 0)', [userId, gid]);"
E4_NEW = "const ins = await dbRun('INSERT INTO player_gongfa (player_id, gongfa_id, level, exp) VALUES (?, ?, ?, ?)', [userId, gid, nextLevel, nextExp]);"

# ── [5] levelup【补偿】按 exp 反向回退 ─────────────────────────────────────────
E5_OLD = (
    "      const rev = inserted\n"
    "        ? await dbRun('DELETE FROM player_gongfa WHERE player_id = ? AND gongfa_id = ? AND level = 1', [userId, gid])\n"
    "        : await dbRun('UPDATE player_gongfa SET level = level - 1, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?', [userId, gid, curLevel + 1]);\n"
    "      if (!rev.changes) console.error('gongfa levelup revert failed: user=%s gongfa=%s level=%s', userId, key, curLevel + 1);"
)
E5_NEW = (
    "      // [r207gf] R-198：补偿回退改为 exp 反向（首建行按 nextExp 删行）。\n"
    "      const rev = inserted\n"
    "        ? await dbRun('DELETE FROM player_gongfa WHERE player_id = ? AND gongfa_id = ? AND exp = ?', [userId, gid, nextExp])\n"
    "        : await dbRun('UPDATE player_gongfa SET exp = exp - ?, level = ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND exp = ?', [cost, curLevel, userId, gid, nextExp]);\n"
    "      if (!rev.changes) console.error('gongfa levelup revert failed: user=%s gongfa=%s exp=%s', userId, key, nextExp);"
)

# ── [6] levelup：删除事后 exp 二次累加（已在占位完成），newLevel=nextLevel ──────
E6_OLD = (
    "    await dbRun(\n"
    "      'UPDATE player_gongfa SET exp = exp + ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?',\n"
    "      [cost, userId, gid, curLevel + 1]\n"
    "    ).catch((e: any) => console.error('gongfa exp update error:', e?.message || e));\n"
    "    const newLevel = curLevel + 1;"
)
E6_NEW = (
    "    // [r207gf] R-198: exp already accumulated atomically in the placeholder step above; no second pass.\n"
    "    const newLevel = nextLevel;"
)

# ── [7] levelup 响应 exp = nextExp ───────────────────────────────────────────
E7_OLD = "      exp: Math.max(0, Math.floor(Number(row?.exp) || 0)) + cost,"
E7_NEW = "      exp: nextExp,"

# ── [8] GET per-key：costNext=P + 新增 levelExp/levelNeed ────────────────────
E8_OLD = (
    "        costNext: next == null ? 0 : next,\n"
    "        costToNext: next == null ? 0 : next,"
)
E8_NEW = (
    "        costNext: next == null ? 0 : next,\n"
    "        costToNext: next == null ? 0 : next,\n"
    "        // [r207gf] R-198：本级进度（exp 落入当前级的量 / 当前级所需量），供客户端进度条与文案。\n"
    "        levelExp: Math.max(0, exp - gongfaExpToReach(shown)),\n"
    "        levelNeed: Math.max(1, (shown < GONGFA_MAX_LEVEL ? gongfaExpToReach(shown + 1) : gongfaExpToReach(GONGFA_MAX_LEVEL)) - gongfaExpToReach(shown)),"
)

# ── [9] GET per-key：costNext 取值改按档位单价 ───────────────────────────────
E9_OLD = "      const next = shown < GONGFA_MAX_LEVEL ? gongfaCostToReach(shown + 1) : null;"
E9_NEW = "      const next = shown < GONGFA_MAX_LEVEL ? gongfaClickCost(shown + 1) : null; // [r207gf] R-198：点一次按档位单价"

# ── [10] GET 全局：新增 clickCost（单价表）──────────────────────────────────
E10_OLD = "      maxExpTotal: GONGFA_MAX_EXP_TOTAL,"
E10_NEW = "      maxExpTotal: GONGFA_MAX_EXP_TOTAL,\n      clickCost: GONGFA_CLICK_COST, // [r207gf] R-198：点一次单价表（按档位）"

EDITS = [
    ("R207 阈值表×7.5 + 单价表 P + 取值器（MARK）", E1_OLD, E1_NEW),
    ("R207 levelup 按档位单价 + exp/level 预算", E2_OLD, E2_NEW),
    ("R207 levelup 占位按 exp 推进", E3_OLD, E3_NEW),
    ("R207 levelup 首建 INSERT exp/level", E4_OLD, E4_NEW),
    ("R207 levelup 补偿按 exp 回退", E5_OLD, E5_NEW),
    ("R207 levelup 删二次累加 + newLevel", E6_OLD, E6_NEW),
    ("R207 levelup 响应 exp=nextExp", E7_OLD, E7_NEW),
    ("R207 GET per-key levelExp/levelNeed", E8_OLD, E8_NEW),
    ("R207 GET per-key costNext=按档位单价", E9_OLD, E9_NEW),
    ("R207 GET 全局 clickCost 表", E10_OLD, E10_NEW),
]

# ============================================================ 依赖（绝对在位，锚点唯一）

REQUIRES = [
    ("const GONGFA_MAX_LEVEL = 100;", "==", 1, "等级上限必须在位（本环不动）"),
    ("const GONGFA_TIER_COST = [300, 500, 800, 1200, 2000, 3000, 5000, 8000, 12000, 20000];", "==", 1,
     "旧阈值表必须在位（本环 ×7.5）"),
    ("function gongfaCostToReach(", "==", 1, "单级消耗函数必须在位（本环保留）"),
    ("function gongfaExpToReach(", "==", 1, "累计投入函数必须在位（本环复用）"),
    ("function gongfaLevelFromExp(", "==", 1, "exp 反推等级函数必须在位（本环复用）"),
    ("const GONGFA_MAX_EXP_TOTAL = gongfaExpToReach(GONGFA_MAX_LEVEL);", "==", 1, "满级累计必须在位"),
    ("app.get('/api/gongfa', authenticateToken", "==", 1, "GET /api/gongfa 必须在位"),
    ("app.post('/api/gongfa/levelup', authenticateToken", "==", 1, "levelup 端点必须在位"),
    ("function dbGet<T = any>(sql: string, params: any[] = []): Promise<T | undefined> {", "==", 1, "dbGet 在位"),
    ("function dbRun(", "==", 1, "dbRun 在位"),
    ("function updatePlayerSave(", ">=", 1, "锁内扣款器必须在位（本环不动扣款）"),
    ("[r201", ">=", 0, "链尾标记（存在性不强制，仅留位）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    "const GONGFA_MAX_LEVEL = 100;",
    "const GONGFA_GRADE_MULT",
    "const GONGFA_MAIN_KEYS",
    "const GONGFA_LIST",
    "function gongfaBonusPct(",
    "app.get('/api/gongfa', authenticateToken",
    "app.post('/api/gongfa/levelup', authenticateToken",
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
        ("R207 幂等标记在位", MARK, 1, "==", "本环已应用"),
        # ── 阈值表 / 单价 ──
        ("R207 新阈值表(×7.5)", "const GONGFA_TIER_COST = [2250, 3750, 6000, 9000, 15000, 22500, 37500, 60000, 90000, 150000];", 1, "==", "k=7.5"),
        ("R207 旧阈值表清零", "const GONGFA_TIER_COST = [300, 500, 800, 1200, 2000, 3000, 5000, 8000, 12000, 20000];", 0, "==", "旧值消失"),
        ("R207 单价表(×2.5)", "const GONGFA_CLICK_COST = [750, 1250, 2000, 3000, 5000, 7500, 12500, 20000, 30000, 50000];", 1, "==", "按档位"),
        ("R207 单价取值器", "function gongfaClickCost(level: unknown): number {", 1, "==", "按 L 所在档位取 P"),
        ("R207 等级上限未动", "const GONGFA_MAX_LEVEL = 100;", 1, "==", "上限保留"),
        # ── levelup 机制 ──
        ("R207 cost=按档位单价", "const cost = gongfaClickCost(curLevel + 1);", 1, "==", "目标级所在档位"),
        ("R207 旧按级计价清零", "const cost = gongfaCostToReach(curLevel + 1);", 0, "==", "旧行消失"),
        ("R207 exp 反推等级", "const nextLevel = Math.min(GONGFA_MAX_LEVEL, gongfaLevelFromExp(nextExp));", 1, "==", "level 由 exp 反推"),
        ("R207 旧档对齐下限", "const baseExp = Math.max(curExp, gongfaExpToReach(curLevel));", 1, "==", "防等级回退"),
        ("R207 占位按 exp", "UPDATE player_gongfa SET exp = exp + ?, level = ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND exp = ?", 1, "==", "单语句原子"),
        ("R207 首建 INSERT 新口径", "INSERT INTO player_gongfa (player_id, gongfa_id, level, exp) VALUES (?, ?, ?, ?)", 1, "==", "level/exp 入参"),
        ("R207 首建旧口径清零", "INSERT INTO player_gongfa (player_id, gongfa_id, level, exp) VALUES (?, ?, 1, 0)", 0, "==", "旧行消失"),
        ("R207 补偿按 exp 回退", "UPDATE player_gongfa SET exp = exp - ?, level = ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND exp = ?", 1, "==", "回退分支"),
        ("R207 补偿删行按 exp", "DELETE FROM player_gongfa WHERE player_id = ? AND gongfa_id = ? AND exp = ?", 1, "==", "首建回退"),
        ("R207 旧 level+1 占位清零", "UPDATE player_gongfa SET level = level + 1, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?", 0, "==", "旧行消失"),
        ("R207 二次累加已删", "gongfa exp update error:", 0, "==", "占位已含 exp"),
        ("R207 newLevel=nextLevel", "    const newLevel = nextLevel;", 1, "==", "响应等级"),
        ("R207 响应 exp=nextExp", "      exp: nextExp,", 1, "==", "响应经验"),
        # ── GET ──
        ("R207 GET costNext=按档位单价", "const next = shown < GONGFA_MAX_LEVEL ? gongfaClickCost(shown + 1) : null;", 1, "==", "点一次价"),
        ("R207 GET levelExp/levelNeed", "        levelExp: Math.max(0, exp - gongfaExpToReach(shown)),", 1, "==", "本级进度"),
        ("R207 GET levelNeed", "        levelNeed: Math.max(1, (shown < GONGFA_MAX_LEVEL ? gongfaExpToReach(shown + 1) : gongfaExpToReach(GONGFA_MAX_LEVEL)) - gongfaExpToReach(shown)),", 1, "==", "本级所需"),
        ("R207 GET clickCost 表", "      clickCost: GONGFA_CLICK_COST, // [r207gf] R-198：点一次单价表（按档位）", 1, "==", "全局下发"),
        # ── 冻结：六卷目录 / 加成 / 端点未动 ──
        ("R207 冻结·GONGFA_MAX_LEVEL", "const GONGFA_MAX_LEVEL = 100;", 1, "==", "上限未动"),
        ("R207 冻结·GONGFA_GRADE_MULT", "const GONGFA_GRADE_MULT", 1, "==", "品级乘数未动"),
        ("R207 冻结·GONGFA_LIST", "const GONGFA_LIST", 1, "==", "六卷 key 未动"),
        ("R207 冻结·gongfaBonusPct", "function gongfaBonusPct(", 1, "==", "加成公式未动"),
        ("R207 冻结·GET 端点", "app.get('/api/gongfa', authenticateToken", 1, "==", "未动"),
        ("R207 冻结·levelup 端点", "app.post('/api/gongfa/levelup', authenticateToken", 1, "==", "未动"),
        ("R207 冻结·gradeMult 下发", "gradeMult: GONGFA_GRADE_MULT,", 1, "==", "未动"),
        ("R207 冻结·tierCost 下发", "tierCost: GONGFA_TIER_COST,", 1, "==", "未动（表值随 ×3 变）"),
        # ── 工程红线（相对计数）──
        ("R207 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403"),
        ("R207 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R207 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        ("R207 红线·无 require", "require(", 0, "==", "ESM 不新增 require"),
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
    nroot = 'C:/Users/27026/.workbuddy-ai/binaries/node/versions'
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
    ap = argparse.ArgumentParser(description="R-198 心法点一次加经验 + 大幅提高单价（服务端第 88 环）")
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

    # 3) 锚点唯一 + 纯 ASCII
    for name, old, new in EDITS:
        if not all(ord(c) < 128 for c in old):
            fail("%s 锚点含非 ASCII 字符（违反工程约束）" % name)
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线（针脚必须在基座真实存在，防拼错导致冻结静默失效）
    base = {k: src.count(k) for k in BASE_NEEDLES}
    for k in BASE_NEEDLES:
        if base[k] <= 0 and k != "require(":  # require( 合法基线 = 0（ESM 红线）
            fail("冻结针脚在基座不存在（拼写错误？）：%r" % k[:90])

    # 5) 应用
    out = _apply(src)

    # 6) 门禁 + 往返 + 语法
    _verify(out, src, base, do_node=(a.check or a.selftest), tag="--check")

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return 0

    # 7) 改前 .bak + 原子写回
    bak = "%s.bak-r207-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r207gf-", suffix=".tmp")
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
