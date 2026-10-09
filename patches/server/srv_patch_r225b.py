# -*- coding: utf-8 -*-
r"""
srv_patch_r225b.py -- R-225b 服务端**冻结难度**（服务端第 92 环）

背景（0.9.50 已上线，这是它的安全补丁）
--------------------------------------------------------------------------
  0.9.50 的服务端第 91 环（srv_patch_r225.py）让服务端离线收益吃难度倍率，
  但它读的是 `save_data.settings.difficulty` —— 那是**客户端 localStorage 的镜像**
  （客户端 pushSave body 里带 settings: S.settings，服务端整包落库）。
  ⇒ 玩家改本地存储就能白拿 ×2 离线收益。用户不接受。

本环改为「**服务端冻结难度**」：服务端持有权威副本（saves.difficulty 列），
首次记录后忽略客户端改动，倍率只读服务端这一列。

机制（逐条）
--------------------------------------------------------------------------
  ① `saves` 表新增 `difficulty` 列（照 srv/index_v28.ts L168-169 的 safeAddColumn 范式）。
  ② 冻结语义：某 uid **首次**写入时把客户端提交的 settings.difficulty（合法值仅 easy/normal/hard；
     非法/缺失按 normal）记进该列；**此后一律忽略客户端提交的改动**，倍率只读服务端这一列。
  ③ `ylR225DiffMul()` 改为读**服务端冻结值**（从行对象/冻结串取），**不再读 saveData.settings.difficulty**。
  ④ 老行迁移：`difficulty IS NULL` 的行（0.9.50 之前的老档）→ **首次见到时按客户端值落一次**，之后冻结。
     ★ 不把老玩家判成作弊、不清空/重置任何存档字段。
  ⑤ 倍率表**一字不变**（easy 1/1、normal 1.5/1.5、hard 2/2）。

必须覆盖的 4 个调用点（与 srv_patch_r225.py 相同的 4 个）
--------------------------------------------------------------------------
  · settleSaveEconV2（cap 配额项 calcOfflineGainV2 的调用）
  · GET  /api/offline/report  （预览）
  · POST /api/offline/claim   （预览 + 入档）

CLI 契约（照技能 §18.10 / localtest/srv_patch_r129.py）
--------------------------------------------------------------------------
  `--src <path>`：就地原子写回该路径（写回前落 `<src>.bak-r225b-<时间戳>`）。装配器把它复制成
    **私有副本**再传 `--src`，故就地写是安全的、也是被期望的（§18.10）。
  `--check` / `--selftest`：只校验不写回。幂等：产物含 `[r225b]` 或 `R225bFrozen` 则 SKIP。
  `--reverse <path>`：反向对照（§18.16）——在**未打 r225b 的服务端**上跑同一套断言，必须 FAIL。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval` / `PRAGMA`。
  · 只改服务端；不改客户端 bundle；不改任何既有 srv_patch_*.py / chain_build.py / deploy_*/。
  · 每处替换 expect=1，命中数不符即中止；产物 round-trip 自证 + Node 真跑语义校验后原子写回。
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "srv", "index_v28.ts")

MARK = "[r225b]"

# ============================================================ 新增/改写块
# ② 改写取值器 + 新增冻结器（R225_DIFF_MUL 三档表逐字保留）
HELPER_OLD = (
    "// ★ Object.create(null) + hasOwnProperty 守卫：difficulty 由客户端提交，防 \"toString\" 之类\n"
    "//   命中 Object.prototype（§18.12 原型链泄漏）。\n"
    "const R225_DIFF_MUL: Record<string, { exp: number; stone: number }> = Object.create(null); // [r225diff]\n"
    "R225_DIFF_MUL.easy = { exp: 1, stone: 1 };\n"
    "R225_DIFF_MUL.normal = { exp: 1.5, stone: 1.5 };\n"
    "R225_DIFF_MUL.hard = { exp: 2, stone: 2 };\n"
    "// 难度倍率取值（纯）：saveData = 整包存档对象。key ∈ {'exp','stone'}。缺失/非法 ⇒ normal 档。\n"
    "function ylR225DiffMul(saveData: any, key: 'exp' | 'stone'): number {\n"
    "  try {\n"
    "    const d = saveData && saveData.settings ? saveData.settings.difficulty : null;\n"
    "    const row = (typeof d === 'string' && Object.prototype.hasOwnProperty.call(R225_DIFF_MUL, d))\n"
    "      ? R225_DIFF_MUL[d] : R225_DIFF_MUL.normal;\n"
    "    const v = Number(row ? row[key] : 1);\n"
    "    return Number.isFinite(v) && v > 0 ? v : 1;\n"
    "  } catch { return 1; }\n"
    "}\n"
    "// 难度倍率（接受「整包存档对象」或「原始 JSON 字符串」）：解析失败/缺失 ⇒ normal 档。\n"
    "function ylR225OfflineMults(saveData: any): { exp: number; stone: number } {\n"
    "  try {\n"
    "    let root: any = saveData;\n"
    "    if (typeof root === 'string') root = JSON.parse(root);\n"
    "    return { exp: ylR225DiffMul(root, 'exp'), stone: ylR225DiffMul(root, 'stone') };\n"
    "  } catch {\n"
    "    return { exp: ylR225DiffMul(null, 'exp'), stone: ylR225DiffMul(null, 'stone') };\n"
    "  }\n"
    "}"
)

HELPER_NEW = (
    "// ★ 表用 Object.create(null)（无原型）⇒ 键名即使是 \"toString\" 也取不到 Object.prototype 成员；\n"
    "//   取值器再用**显式白名单**（=== 'easy'|'normal'|'hard'）二次收口（§18.12 原型链泄漏）。\n"
    "const R225_DIFF_MUL: Record<string, { exp: number; stone: number }> = Object.create(null); // [r225diff]\n"
    "R225_DIFF_MUL.easy = { exp: 1, stone: 1 };\n"
    "R225_DIFF_MUL.normal = { exp: 1.5, stone: 1.5 };\n"
    "R225_DIFF_MUL.hard = { exp: 2, stone: 2 };\n"
    "// ★ R-225b（[r225b]）服务端**冻结难度**：把「难度从哪来」从客户端镜像（localStorage）改为服务端权威列 saves.difficulty。\n"
    "//   客户端难度归一（纯）：仅在**首次冻结**时用来落一次库；此后一律忽略客户端提交。非法/缺失 ⇒ normal。\n"
    "function ylR225bClientDiff(src: any): 'easy' | 'normal' | 'hard' {\n"
    "  try {\n"
    "    let root: any = src;\n"
    "    if (typeof root === 'string') root = JSON.parse(root);\n"
    "    const d = root && root.settings ? root.settings.difficulty : null;\n"
    "    return (d === 'easy' || d === 'normal' || d === 'hard') ? d : 'normal';\n"
    "  } catch { return 'normal'; }\n"
    "}\n"
    "// 服务端冻结难度（纯）：row.difficulty 合法 ⇒ 用它（**忽略客户端改动**）；NULL/非法（老行/新号）⇒ 首次按客户端值落一次。\n"
    "function ylR225bFrozen(row: any, src: any): 'easy' | 'normal' | 'hard' {\n"
    "  const col = row ? row.difficulty : null;\n"
    "  if (col === 'easy' || col === 'normal' || col === 'hard') return col;\n"
    "  return ylR225bClientDiff(src);\n"
    "}\n"
    "// 离线路由用：返回冻结难度，并（**仅当列 NULL**）把客户端值落一次库（老行迁移；不重置任何存档字段）。\n"
    "function ylR225bFreezeRow(userId: number, row: any, src: any): 'easy' | 'normal' | 'hard' {\n"
    "  const col = row ? row.difficulty : null;\n"
    "  if (col === 'easy' || col === 'normal' || col === 'hard') return col;\n"
    "  const d = ylR225bClientDiff(src);\n"
    "  try { dbRun('UPDATE saves SET difficulty = ? WHERE user_id = ? AND difficulty IS NULL', [d, userId]).catch(() => {}); } catch { /* 落库失败不影响读取 */ }\n"
    "  return d;\n"
    "}\n"
    "// 难度倍率取值（纯）：读**服务端冻结难度**（不再读客户端存档里的 settings.difficulty）。key ∈ {'exp','stone'}。\n"
    "//   入参可为冻结难度串（'easy'|'normal'|'hard'）或含 .difficulty 的行对象。缺失/非法 ⇒ normal 档。\n"
    "function ylR225DiffMul(frozenDiff: any, key: 'exp' | 'stone'): number {\n"
    "  try {\n"
    "    const raw = (frozenDiff && typeof frozenDiff === 'object') ? frozenDiff.difficulty : frozenDiff;\n"
    "    const d = (raw === 'easy' || raw === 'normal' || raw === 'hard') ? raw : 'normal';\n"
    "    const row = R225_DIFF_MUL[d];\n"
    "    const v = Number(row ? row[key] : 1);\n"
    "    return Number.isFinite(v) && v > 0 ? v : 1;\n"
    "  } catch { return 1; }\n"
    "}\n"
    "// 难度倍率（接受「服务端冻结难度串」或「含 .difficulty 的行对象」）：解析失败/缺失 ⇒ normal 档。\n"
    "function ylR225OfflineMults(frozenDiff: any): { exp: number; stone: number } {\n"
    "  return { exp: ylR225DiffMul(frozenDiff, 'exp'), stone: ylR225DiffMul(frozenDiff, 'stone') };\n"
    "}"
)

# ============================================================ 改动点（全部 expect=1）
EDITS = [
    # ① 新增 difficulty 列（照 L168-169 的 safeAddColumn 范式）
    ("R225b 新增 difficulty 列",
     "          if (!rows.some((r: any) => r.name === 'last_active_at')) safeAddColumn('saves', 'last_active_at', 'ALTER TABLE saves ADD COLUMN last_active_at INTEGER');\n"
     "        }",
     "          if (!rows.some((r: any) => r.name === 'last_active_at')) safeAddColumn('saves', 'last_active_at', 'ALTER TABLE saves ADD COLUMN last_active_at INTEGER');\n"
     "          // ★ R-225b（[r225b]）：saves.difficulty —— 服务端**冻结**的难度权威副本（easy/normal/hard，NULL=老行/未冻结）。\n"
     "          //   0.9.50 的 R-225 读 save_data.settings.difficulty（客户端 localStorage 镜像）⇒ 改本地存储即可白拿 ×2 离线收益。\n"
     "          //   本列在**首次写入**时按客户端提交值落一次，此后一律忽略客户端改动；倍率只读本列。\n"
     "          //   建列复用既有列存在性快路径 + safeAddColumn（容忍 duplicate column name ⇒ 冷启动/重跑幂等），不新增库表探测语句。\n"
     "          if (!rows.some((r: any) => r.name === 'difficulty')) safeAddColumn('saves', 'difficulty', 'ALTER TABLE saves ADD COLUMN difficulty TEXT'); // [r225b]\n"
     "        }"),

    # ② 改写取值器 + 新增冻结器
    ("R225b 改写取值器/新增冻结器", HELPER_OLD, HELPER_NEW),

    # ③ settleSaveEconV2 签名加 frozenDiff 形参
    ("R225b settleSaveEconV2 签名",
     "function settleSaveEconV2(oldSd: any, newSd: any, prevSavedAtMs: number | null, lumpPool?: { tower: number; exped: number }, winState?: { start: number | null; exp: number; stone: number }): string[] {",
     "function settleSaveEconV2(oldSd: any, newSd: any, prevSavedAtMs: number | null, lumpPool?: { tower: number; exped: number }, winState?: { start: number | null; exp: number; stone: number }, frozenDiff?: string): string[] { // [r225b] frozenDiff = 服务端冻结难度"),

    # ③b 调用点 1：cap 配额项读冻结值
    ("R225b 调用点1 cap 配额项",
     "    const off = calcOfflineGainV2(op, prevSavedAtMs, ylR225DiffMul(oldSd, 'exp'), ylR225DiffMul(oldSd, 'stone')); // [r225diff] 离线收益吃难度（配额项与发放同档）",
     "    const off = calcOfflineGainV2(op, prevSavedAtMs, ylR225DiffMul(frozenDiff, 'exp'), ylR225DiffMul(frozenDiff, 'stone')); // [r225b] 离线收益吃难度（配额项读服务端冻结值）"),

    # ④ /api/save SELECT 加 difficulty
    ("R225b /api/save SELECT 加列",
     "    db.get('SELECT save_data, gm_revision, updated_at, tower_lump_left, exped_lump_left, econ_win_start, econ_win_exp, econ_win_stone FROM saves WHERE user_id = ?', [req.user.id], (err, row: any) => {",
     "    db.get('SELECT save_data, gm_revision, updated_at, tower_lump_left, exped_lump_left, econ_win_start, econ_win_exp, econ_win_stone, difficulty FROM saves WHERE user_id = ?', [req.user.id], (err, row: any) => {"),

    # ⑤ 计算冻结难度并传给 settleSaveEconV2
    ("R225b /api/save 计算冻结难度",
     "      const winState = row ? winStateFromRow(row) : { start: null, exp: 0, stone: 0 };\n"
     "      let clampedFields: string[] = settleSaveEconV2(row && !econSkip ? (() => { try { return JSON.parse(row.save_data); } catch { return null; } })() : null, saveData, row && row.updated_at ? (() => { const t = Date.parse(String(row.updated_at).replace(' ', 'T') + 'Z'); return Number.isFinite(t) ? t : null; })() : null, lumpPool, winState);",
     "      const winState = row ? winStateFromRow(row) : { start: null, exp: 0, stone: 0 };\n"
     "      // [r225b] 服务端冻结难度：row.difficulty 合法 ⇒ 权威值（忽略客户端改动）；NULL（新号/老行）⇒ 按本次提交落一次\n"
     "      const ylR225bD = ylR225bFrozen(row, saveData);\n"
     "      let clampedFields: string[] = settleSaveEconV2(row && !econSkip ? (() => { try { return JSON.parse(row.save_data); } catch { return null; } })() : null, saveData, row && row.updated_at ? (() => { const t = Date.parse(String(row.updated_at).replace(' ', 'T') + 'Z'); return Number.isFinite(t) ? t : null; })() : null, lumpPool, winState, ylR225bD); // [r225b]"),

    # ⑥ UPDATE 分支首次落库（COALESCE ⇒ 只写一次）
    ("R225b UPDATE 首次落库",
     "          'UPDATE saves SET save_data = ?, gm_revision = ?, tower_lump_left = ?, exped_lump_left = ?, econ_win_start = ?, econ_win_exp = ?, econ_win_stone = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', // S2 v26c：玩家写递增修订号\n"
     "          [saveDataStringClamped, curRev + 1, lumpPool.tower, lumpPool.exped, winState.start, winState.exp, winState.stone, req.user.id],",
     "          'UPDATE saves SET save_data = ?, gm_revision = ?, tower_lump_left = ?, exped_lump_left = ?, econ_win_start = ?, econ_win_exp = ?, econ_win_stone = ?, difficulty = COALESCE(difficulty, ?), updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', // S2 v26c：玩家写递增修订号 // [r225b] difficulty 首次落库后冻结（COALESCE 保证只写一次）\n"
     "          [saveDataStringClamped, curRev + 1, lumpPool.tower, lumpPool.exped, winState.start, winState.exp, winState.stone, ylR225bD, req.user.id],"),

    # ⑦ INSERT 分支首存即冻结
    ("R225b INSERT 首存即冻结",
     "          'INSERT INTO saves (user_id, save_data, gm_revision, tower_lump_left, exped_lump_left, econ_win_start, econ_win_exp, econ_win_stone) VALUES (?, ?, 1, ?, ?, ?, ?, ?)', // S2 v26c：首存修订号=1（兼容 C6 首存，无头放行）\n"
     "          [req.user.id, saveDataStringClamped, lumpPool.tower, lumpPool.exped, winState.start, winState.exp, winState.stone], // QA-Y fix(BUG#1)：参数反序已修；此处用钳后串：原 [saveDataString, req.user.id] 参数反序——新玩家首存 user_id 写成整包 JSON、save_data 写成数字，GET /save 404、邮件 claim/buff/称号落空，且每次上传再插一行垃圾（UNIQUE 不命中）",
     "          'INSERT INTO saves (user_id, save_data, gm_revision, tower_lump_left, exped_lump_left, econ_win_start, econ_win_exp, econ_win_stone, difficulty) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)', // S2 v26c：首存修订号=1（兼容 C6 首存，无头放行） // [r225b] 首存即冻结 difficulty\n"
     "          [req.user.id, saveDataStringClamped, lumpPool.tower, lumpPool.exped, winState.start, winState.exp, winState.stone, ylR225bD], // QA-Y fix(BUG#1)：参数反序已修；此处用钳后串：原 [saveDataString, req.user.id] 参数反序——新玩家首存 user_id 写成整包 JSON、save_data 写成数字，GET /save 404、邮件 claim/buff/称号落空，且每次上传再插一行垃圾（UNIQUE 不命中）"),

    # ⑧ report SELECT 加 difficulty
    ("R225b report SELECT 加列",
     "  db.get('SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at, last_active_at FROM saves WHERE user_id = ?', [req.user.id], async (err: any, row: any) => {",
     "  db.get('SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at, last_active_at, difficulty FROM saves WHERE user_id = ?', [req.user.id], async (err: any, row: any) => {"),

    # ⑨ 调用点 2：report 读冻结值
    ("R225b 调用点2 report",
     "    const ylR225M = ylR225OfflineMults(row.save_data); // [r225diff]\n"
     "    const rw = win ? offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour, ylR225M.exp, ylR225M.stone) : null;",
     "    const ylR225M = ylR225OfflineMults(ylR225bFreezeRow(req.user.id, row, row.save_data)); // [r225b] 读服务端冻结难度（老行首次落库）\n"
     "    const rw = win ? offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour, ylR225M.exp, ylR225M.stone) : null;"),

    # ⑩ claim SELECT 加 difficulty
    ("R225b claim SELECT 加列",
     "    const row = await dbGet('SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at, last_active_at FROM saves WHERE user_id = ?', [userId]);",
     "    const row = await dbGet('SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at, last_active_at, difficulty FROM saves WHERE user_id = ?', [userId]);"),

    # ⑪ 调用点 3：claim 预览读冻结值
    ("R225b 调用点3 claim 预览",
     "    const ylR225M = ylR225OfflineMults(row.save_data); // [r225diff]\n"
     "    const rw = offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour, ylR225M.exp, ylR225M.stone);",
     "    const ylR225bD = ylR225bFreezeRow(userId, row, row.save_data); // [r225b] 读服务端冻结难度（老行首次落库）\n"
     "    const ylR225M = ylR225OfflineMults(ylR225bD); // [r225b] 预览\n"
     "    const rw = offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour, ylR225M.exp, ylR225M.stone);"),

    # ⑫ 调用点 4：claim 入档读冻结值（与预览同源）
    ("R225b 调用点4 claim 入档",
     "      const ylR225M = ylR225OfflineMults(sd); // [r225diff]\n"
     "      const r = offlineRewards(nrNow.maxExp, nrNow.exp, win.windowMs, capHours, ratePerHour, ylR225M.exp, ylR225M.stone);",
     "      const ylR225M = ylR225OfflineMults(ylR225bD); // [r225b] 入档（与预览同源，读服务端冻结难度）\n"
     "      const r = offlineRewards(nrNow.maxExp, nrNow.exp, win.windowMs, capHours, ratePerHour, ylR225M.exp, ylR225M.stone);"),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    ("[r225diff]", 13, "R-225（第 91 环）必须已应用（链序：本环排在 r225 之后）"),
    ("const R225_DIFF_MUL: Record<string, { exp: number; stone: number }> = Object.create(null); // [r225diff]", 1, "R-225 倍率表必须在位"),
    ("function ylR225DiffMul(saveData: any, key: 'exp' | 'stone'): number {", 1, "R-225 旧取值器必须在位（本环改写它）"),
    ("function calcOfflineGainV2(p: any, fromMs: number | null, diffExp: number = 1, diffStone: number = 1): { exp: number; stones: number } { // [r225diff]", 1, "R-225 calcOfflineGainV2 新签名必须在位"),
    ("  diffExpMul: number = 1, diffStoneMul: number = 1 // [r225diff]", 1, "R-225 offlineRewards 新签名必须在位"),
    ("function settleSaveEconV2(oldSd: any, newSd: any, prevSavedAtMs: number | null, lumpPool?: { tower: number; exped: number }, winState?: { start: number | null; exp: number; stone: number }): string[] {", 1, "settleSaveEconV2 旧签名必须在位且唯一"),
    ("const OFFLINE_STONE_RATIO = 0.1;", 1, "OFFLINE_STONE_RATIO 必须在位"),
    ("const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;", 1, "OFFLINE_RATE_BASE_PER_HOUR 必须在位"),
    ("const OFFLINE_MIN_MS = 5 * 60 * 1000;", 1, "OFFLINE_MIN_MS 必须在位"),
    ("const ECON_REALM_ORDER: string[] = Object.keys(TRIB_REALM_BASES);", 1, "ECON_REALM_ORDER 必须在位（境界序）"),
    ("function dbRun(sql: string, params: any[] = []): Promise<{ lastID: number; changes: number }> {", 1, "dbRun 必须在位（冻结器一次性落库用）"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "res.status(403", "require(", "setInterval(", "PRAGMA",
    "function offlineRewards(",
    "function offlineWindow(",
    "function offlineAnchor(",
    "function offlineCapHours(",
    "function offlineRatePerHour(",
    "function hasMonthCard(",
    "function offlineBreakthroughHint(",
    "const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;",
    "const OFFLINE_RATE_MONTHCARD_PER_HOUR = 0.006;",
    "const OFFLINE_STONE_RATIO = 0.1;",
    "const OFFLINE_MIN_MS = 5 * 60 * 1000;",
    "function actApplyGain(base: unknown, mult: unknown): number {",
    "const off = calcOfflineGainV2(",
    "app.get('/api/offline/report'",
    "app.post('/api/offline/claim'",
    "insertMail(userId, '闭关修炼 · 离线收益'",
    "offline_claimed_until = ? WHERE user_id = ? AND (offline_claimed_until IS NULL OR offline_claimed_until < ?)",
    "[r173offline]",
    "// 计数器差值：只认正增量（回档/多端旧档不倒扣，同 Y15/DG 口径）",
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


# ============================================================ 源码抽取（字符串/注释感知的括号配平，§25.1）
def extract_brace(src, start):
    """从 src[start] == '{' 起做括号配平，返回含首尾花括号的函数体片段。"""
    assert src[start] == '{', "extract_brace: not at '{'"
    depth = 0
    k = start
    n = len(src)
    mode = None  # None | "'" | '"' | '`' | '//' | '/*'
    while k < n:
        c = src[k]
        if mode == "'" or mode == '"' or mode == '`':
            if c == '\\':
                k += 2
                continue
            if c == mode:
                mode = None
        elif mode == '//':
            if c == '\n':
                mode = None
        elif mode == '/*':
            if c == '*' and k + 1 < n and src[k + 1] == '/':
                mode = None
                k += 2
                continue
        else:
            if c == '/' and k + 1 < n and src[k + 1] == '/':
                mode = '//'
                k += 2
                continue
            if c == '/' and k + 1 < n and src[k + 1] == '*':
                mode = '/*'
                k += 2
                continue
            if c == "'" or c == '"' or c == '`':
                mode = c
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return src[start:k + 1]
        k += 1
    raise ValueError("unbalanced braces")


def extract_fn(src, header, ret_anchor, new_name):
    i = src.index(header)
    a = src.index(ret_anchor, i) + len(ret_anchor) - 1
    assert src[a] == '{', "extract_fn: ret_anchor tail not '{'"
    body = src[i:a] + extract_brace(src, a)
    return body.replace(header, "function " + new_name + "(", 1)


# ============================================================ Node 语义校验（真跑产物函数）
HARNESS = r'''
const FIXED = 1700000000000;
const _realNow = Date.now;
Date.now = () => FIXED;

const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;
const OFFLINE_RATE_MONTHCARD_PER_HOUR = 0.006;
const OFFLINE_STONE_RATIO = 0.1;
const OFFLINE_MIN_MS = 5 * 60 * 1000;
const ECON_REALM_ORDER = ['\u70bc\u6c14\u671f','\u7b51\u57fa\u671f','\u91d1\u4e39\u671f','\u5143\u5a74\u671f','\u5316\u795e\u671f','\u5408\u9053\u671f','\u957f\u751f\u5883'];

var __writes = [];
function dbRun(sql, params) { __writes.push([sql, params]); return Promise.resolve({ lastID: 0, changes: 1 }); }

__HELPER__

__BASE_FN__

__NEW_FN__

const R = [];
function ck(name, fn) { try { R.push({ name: name, ok: !!fn() }); } catch (e) { R.push({ name: name, ok: false, extra: 'throw:' + ((e && e.message) || e) }); } }

// ---- A) 冻结语义 ----
ck('A1 新号首次按客户端 normal 冻结', () => ylR225bFrozen({ difficulty: null }, { settings: { difficulty: 'normal' } }) === 'normal');
ck('A2 已冻结 normal 后客户端改 hard 被忽略', () => ylR225bFrozen({ difficulty: 'normal' }, { settings: { difficulty: 'hard' } }) === 'normal');
ck('A3 冻结值驱动倍率（normal=1.5）', () => ylR225DiffMul(ylR225bFrozen({ difficulty: 'normal' }, { settings: { difficulty: 'hard' } }), 'exp') === 1.5);
ck('A4 老行 NULL 首次按客户端 hard 落一次', () => ylR225bFrozen({ difficulty: null }, { settings: { difficulty: 'hard' } }) === 'hard');
ck('A5 老行冻结后倍率 hard=2', () => ylR225DiffMul(ylR225bFrozen({ difficulty: 'hard' }, { settings: { difficulty: 'normal' } }), 'exp') === 2);
ck('A6 客户端难度以 JSON 串传入（老行）', () => ylR225bFrozen({}, '{"settings":{"difficulty":"easy"}}') === 'easy');
ck('A7 客户端难度缺失⇒normal', () => ylR225bClientDiff({}) === 'normal');
ck('A8 客户端难度非法⇒normal', () => ylR225bClientDiff({ settings: { difficulty: 'NOPE' } }) === 'normal');
ck('A9 客户端难度 toString⇒normal', () => ylR225bClientDiff({ settings: { difficulty: 'toString' } }) === 'normal');

// ---- B) 核心：改客户端难度后服务端倍率不再变化（冻结生效）----
ck('B1 三连存（normal→hard→hard）倍率恒 1.5', () => {
  const seq = [{ row: { difficulty: null }, cli: 'normal' }, { row: { difficulty: 'normal' }, cli: 'hard' }, { row: { difficulty: 'normal' }, cli: 'hard' }];
  const m = seq.map(function (s) { return ylR225DiffMul(ylR225bFrozen(s.row, { settings: { difficulty: s.cli } }), 'exp'); });
  return m[0] === 1.5 && m[1] === 1.5 && m[2] === 1.5;
});
ck('B2 取值器不读客户端 settings（传含 settings 的对象也只按 .difficulty）', () => ylR225DiffMul({ settings: { difficulty: 'hard' } }, 'exp') === 1.5);

// ---- C) 倍率表（服务端冻结值）----
ck('C1 easy=1/1', () => ylR225DiffMul('easy', 'exp') === 1 && ylR225DiffMul('easy', 'stone') === 1);
ck('C2 normal=1.5/1.5', () => ylR225DiffMul('normal', 'exp') === 1.5 && ylR225DiffMul('normal', 'stone') === 1.5);
ck('C3 hard=2/2', () => ylR225DiffMul('hard', 'exp') === 2 && ylR225DiffMul('hard', 'stone') === 2);
ck('C4 缺失/原型链键⇒normal', () => ylR225DiffMul(null, 'exp') === 1.5 && ylR225DiffMul('toString', 'exp') === 1.5 && ylR225DiffMul('constructor', 'exp') === 1.5);
ck('C5 行对象入参（.difficulty）', () => ylR225DiffMul({ difficulty: 'hard' }, 'exp') === 2);

// ---- D) 一次性落库（老行迁移）----
ck('D1 NULL 行首次落库一次（值+uid）', () => { __writes = []; var d = ylR225bFreezeRow(7, { difficulty: null }, { settings: { difficulty: 'hard' } }); return d === 'hard' && __writes.length === 1 && __writes[0][1][0] === 'hard' && __writes[0][1][1] === 7; });
ck('D2 已冻结行不再落库', () => { __writes = []; var d = ylR225bFreezeRow(7, { difficulty: 'normal' }, { settings: { difficulty: 'hard' } }); return d === 'normal' && __writes.length === 0; });
ck('D3 落库 SQL 带 difficulty IS NULL 守卫', () => { __writes = []; ylR225bFreezeRow(7, { difficulty: null }, { settings: { difficulty: 'normal' } }); return __writes.length === 1 && /difficulty IS NULL/.test(__writes[0][0]); });

// ---- E) 算法未动（m=1 逐位一致 / hard 恰 ×2）----
ck('E1 offlineRewards m=1 与基线逐位一致', () => {
  var grids = [[100,0,0,24],[60000,0,3600e3,24],[760500,100,12*3600e3,86],[1e9,0,24*3600e3,24],[452500000,1000,47*3600e3,86],[12345,0,299999,24],[12345,0,300001,24]];
  for (var i = 0; i < grids.length; i++) { var g = grids[i];
    var b = baseOfflineRewards(g[0], g[1], g[2], g[3], OFFLINE_RATE_BASE_PER_HOUR);
    var n = newOfflineRewards(g[0], g[1], g[2], g[3], OFFLINE_RATE_BASE_PER_HOUR);
    if (JSON.stringify(b) !== JSON.stringify(n)) return false; }
  return true;
});
ck('E2 offlineRewards hard 恰 ×2', () => { var e1 = newOfflineRewards(1e9, 0, 12*3600e3, 86, OFFLINE_RATE_BASE_PER_HOUR, 1, 1); var e2 = newOfflineRewards(1e9, 0, 12*3600e3, 86, OFFLINE_RATE_BASE_PER_HOUR, 2, 2); return e2.expGain === e1.expGain * 2 && e2.stonesGain === e1.stonesGain * 2; });
ck('E3 calcOfflineGainV2 m=1 与基线逐位一致', () => {
  var cases = [[{ realm: '\u91d1\u4e39\u671f', maxExp: 1e9 }, FIXED - 60000], [{ realm: '\u957f\u751f\u5883', maxExp: 3e9 }, FIXED - 3600000], [{ realm: '\u70bc\u6c14\u671f', maxExp: 12345 }, FIXED - 300001]];
  for (var i = 0; i < cases.length; i++) {
    var b = baseCalcOfflineGainV2(cases[i][0], cases[i][1], 1, 1);
    var n = newCalcOfflineGainV2(cases[i][0], cases[i][1], 1, 1);
    if (JSON.stringify(b) !== JSON.stringify(n)) return false; }
  return true;
});
ck('E4 calcOfflineGainV2 hard 恰 ×2（60s 档）', () => { var d1 = newCalcOfflineGainV2({ realm: '\u91d1\u4e39\u671f', maxExp: 1e9 }, FIXED - 60000, 1, 1); var d2 = newCalcOfflineGainV2({ realm: '\u91d1\u4e39\u671f', maxExp: 1e9 }, FIXED - 60000, 2, 2); return d2.exp === d1.exp * 2 && d2.stones === d1.stones * 2; });

Date.now = _realNow;
var bad = R.filter(function (x) { return !x.ok; });
for (var k = 0; k < R.length; k++) console.log((R[k].ok ? '  [OK] ' : '  [FAIL] ') + R[k].name + (R[k].extra ? ('  <' + R[k].extra + '>') : ''));
console.log('HARNESS_RESULT ' + JSON.stringify({ total: R.length, fail: bad.length }));
if (bad.length) process.exit(3);
'''


def node_bin():
    root = r"C:/Users/<USER>/.workbuddy-ai/binaries/node/versions"
    cands = []
    if os.path.isdir(root):
        cands = sorted(os.path.join(root, d, "node.exe") for d in os.listdir(root))
        cands = [c for c in cands if os.path.isfile(c)]
    return os.environ.get("YL_NODE") or (cands[-1] if cands else "node")


def run_node(args):
    d = tempfile.mkdtemp(prefix="r225bnode-")
    try:
        p = os.path.join(d, "h.mts")
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(args["js"])
        r = subprocess.run([node_bin(), "--experimental-strip-types", p],
                           capture_output=True, text=True, encoding="utf-8")
        return r
    finally:
        shutil.rmtree(d, ignore_errors=True)


def node_syntax_check(text):
    """产物必须过 node --experimental-strip-types --check。"""
    d = tempfile.mkdtemp(prefix="r225bchk-")
    try:
        p = os.path.join(d, "c.ts")
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        r = subprocess.run([node_bin(), "--experimental-strip-types", "--check", p],
                           capture_output=True, text=True, encoding="utf-8")
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def build_harness(base_src, new_src):
    """base_src = 未打 r225b 的服务端（含 r225）；new_src = 目标产物。"""
    ret_off = "): { hours: number; expGain: number; stonesGain: number; capped: boolean; claimable: boolean; effectiveMs: number } {"
    ret_calc = "): { exp: number; stones: number } {"
    base_off = extract_fn(base_src, "function offlineRewards(", ret_off, "baseOfflineRewards")
    new_off = extract_fn(new_src, "function offlineRewards(", ret_off, "newOfflineRewards")
    base_calc = extract_fn(base_src, "function calcOfflineGainV2(", ret_calc, "baseCalcOfflineGainV2")
    new_calc = extract_fn(new_src, "function calcOfflineGainV2(", ret_calc, "newCalcOfflineGainV2")
    a = new_src.index("// ── R-225")
    b = new_src.index("// 计数器差值", a)
    helper = new_src[a:b]
    return (HARNESS
            .replace("__HELPER__", helper)
            .replace("__BASE_FN__", base_off + "\n" + base_calc + "\n")
            .replace("__NEW_FN__", new_off + "\n" + new_calc + "\n"))


def run_harness(js):
    r = run_node({"js": js})
    sys.stdout.write(r.stdout or "")
    if r.stderr:
        sys.stdout.write("[node stderr]\n" + r.stderr)
    res = None
    if "HARNESS_RESULT" in (r.stdout or ""):
        try:
            res = json.loads(r.stdout.strip().split("HARNESS_RESULT ")[-1].splitlines()[0])
        except Exception:
            res = None
    return r, res


def main() -> None:
    ap = argparse.ArgumentParser(description="R-225b 服务端冻结难度（服务端第 92 环）")
    ap.add_argument("--src", default=SRC, help="待打补丁的服务端源码（装配器会传私有副本）")
    ap.add_argument("--check", action="store_true", help="只校验不写回")
    ap.add_argument("--selftest", action="store_true", help="只校验不写回（含 Node 真跑）")
    ap.add_argument("--reverse", default=None, metavar="PATH",
                    help="反向对照：在未打 r225b 的服务端上跑同一套断言，必须 FAIL（只校验不写回）")
    a = ap.parse_args()

    # ---- 反向对照模式（§18.16）----
    if a.reverse:
        path = a.reverse
        if not os.path.exists(path):
            fail("reverse source not found: " + path)
        with io.open(path, "r", encoding="utf-8", newline="") as f:
            rev = f.read()
        print("== 反向对照（未打 r225b 的服务端）：%s ==" % path)
        print("  旧取值器读 settings 的形态计数 = %d（期望 ≥1，证明这是未打补丁的基线）"
              % rev.count("saveData && saveData.settings ? saveData.settings.difficulty : null"))
        print("  ylR225bFrozen 计数 = %d（期望 0，证明冻结器不存在）" % rev.count("function ylR225bFrozen("))
        js = build_harness(rev, rev)
        r, res = run_harness(js)
        if res is None:
            print("  [REVERSE FAIL] 基线跑不出 HARNESS_RESULT（node 返回 %d）——按 FAIL 计" % r.returncode)
            return
        print("  [REVERSE] baseline: total=%d fail=%d  =>  %s"
              % (res["total"], res["fail"], "FAIL（符合预期）" if res["fail"] > 0 else "PASS（★ 反向对照失效，断言不具区分度！）"))
        return

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等
    if MARK in src or "ylR225bFrozen" in src:
        print("[SKIP] source looks already patched（已含 %s / ylR225bFrozen）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:90], n, cnt, why))

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    mark_n = sum(new.count(MARK) for _, _, new in EDITS)
    gates = [
        ("R225b 幂等标记就位", MARK, mark_n),
        # ① 新列
        ("① difficulty 列已加", "ALTER TABLE saves ADD COLUMN difficulty TEXT", 1),
        ("① difficulty 建列范式（列存在性快路径）", "if (!rows.some((r: any) => r.name === 'difficulty')) safeAddColumn('saves', 'difficulty', 'ALTER TABLE saves ADD COLUMN difficulty TEXT');", 1),
        # ② 冻结逻辑
        ("② 冻结器 ylR225bFrozen 在位", "function ylR225bFrozen(row: any, src: any): 'easy' | 'normal' | 'hard' {", 1),
        ("② 客户端难度归一器在位", "function ylR225bClientDiff(src: any): 'easy' | 'normal' | 'hard' {", 1),
        ("② 离线路由冻结器在位", "function ylR225bFreezeRow(userId: number, row: any, src: any): 'easy' | 'normal' | 'hard' {", 1),
        ("② 冻结一次性落库 SQL（NULL 守卫）", "UPDATE saves SET difficulty = ? WHERE user_id = ? AND difficulty IS NULL", 1),
        ("② UPDATE 分支 COALESCE 冻结", "difficulty = COALESCE(difficulty, ?)", 1),
        ("② INSERT 分支首存即冻结", "econ_win_stone, difficulty) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)", 1),
        ("② /api/save SELECT 取 difficulty", "econ_win_stone, difficulty FROM saves WHERE user_id = ?', [req.user.id], (err, row: any)", 1),
        ("② report SELECT 取 difficulty", "last_active_at, difficulty FROM saves WHERE user_id = ?', [req.user.id], async (err: any, row: any)", 1),
        ("② claim SELECT 取 difficulty", "last_active_at, difficulty FROM saves WHERE user_id = ?', [userId])", 1),
        ("② /api/save 计算冻结难度", "const ylR225bD = ylR225bFrozen(row, saveData);", 1),
        ("② settleSaveEconV2 新签名（frozenDiff）", "winState?: { start: number | null; exp: number; stone: number }, frozenDiff?: string): string[] {", 1),
        ("② settleSaveEconV2 调用传冻结值", ", lumpPool, winState, ylR225bD); // [r225b]", 1),
        # ③ 4 个调用点全部读服务端值
        ("③ 调用点1 cap 配额项读冻结值", "ylR225DiffMul(frozenDiff, 'exp'), ylR225DiffMul(frozenDiff, 'stone')", 1),
        ("③ 调用点2 report 读冻结值", "ylR225OfflineMults(ylR225bFreezeRow(req.user.id, row, row.save_data))", 1),
        ("③ 调用点3 claim 预览读冻结值", "const ylR225M = ylR225OfflineMults(ylR225bD); // [r225b] 预览", 1),
        ("③ 调用点4 claim 入档读冻结值", "const ylR225M = ylR225OfflineMults(ylR225bD); // [r225b] 入档", 1),
        # ④ 旧路径清零（核心断言）
        ("④ 旧取值器读 settings.difficulty 已清零", "const d = saveData && saveData.settings ? saveData.settings.difficulty : null;", 0),
        ("④ saveData.settings.difficulty 全产物清零", "saveData.settings.difficulty", 0),
        ("④ 旧取值器签名已清零", "function ylR225DiffMul(saveData: any, key: 'exp' | 'stone'): number {", 0),
        ("④ 新取值器读冻结值签名", "function ylR225DiffMul(frozenDiff: any, key: 'exp' | 'stone'): number {", 1),
        ("④ settings.difficulty 仅存于客户端归一器", "root.settings.difficulty", 1),
        # ⑤ 倍率表三档逐字在位
        ("⑤ 倍率表 easy 1/1", "R225_DIFF_MUL.easy = { exp: 1, stone: 1 };", 1),
        ("⑤ 倍率表 normal 1.5/1.5", "R225_DIFF_MUL.normal = { exp: 1.5, stone: 1.5 };", 1),
        ("⑤ 倍率表 hard 2/2", "R225_DIFF_MUL.hard = { exp: 2, stone: 2 };", 1),
        ("⑤ 倍率表定义（Object.create(null)）", "const R225_DIFF_MUL: Record<string, { exp: number; stone: number }> = Object.create(null);", 1),
        # ⑥ offlineRewards / calcOfflineGainV2 签名与公式一字未动
        ("⑥ calcOfflineGainV2 签名未动", "function calcOfflineGainV2(p: any, fromMs: number | null, diffExp: number = 1, diffStone: number = 1): { exp: number; stones: number } {", 1),
        ("⑥ offlineRewards 签名未动", "  diffExpMul: number = 1, diffStoneMul: number = 1", 1),
        ("⑥ offlineRewards exp 公式未动", "const expGain = Math.max(0, Math.min(Math.floor(baseExp * ylR225ME), slot - cur));", 1),
        ("⑥ offlineRewards stones 公式未动", "const stonesGain = Math.max(0, Math.floor(Math.floor(baseExp * OFFLINE_STONE_RATIO) * ylR225MS));", 1),
        ("⑥ calcOfflineGainV2 exp 公式未动", "out.exp = Math.floor(Math.floor((Number(p.maxExp) || 100) * 0.004 * 0.02 * hours * 60) * ylR225ME);", 1),
        ("⑥ calcOfflineGainV2 stones 公式未动", "out.stones = Math.floor(Math.floor(Math.floor((idx <= 0 ? 4 / 3 : 2 * idx + 1) * 125) * hours) * ylR225MS);", 1),
    ]
    # 冻结：既有离线函数/常量/路由/邮件一字不动
    for needle in BASE_NEEDLES:
        gates.append(("冻结 " + needle[:44].replace("\n", " "), needle, base[needle]))
    # 红线
    gates.append(("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]))
    gates.append(("红线 未新增 require(", "require(", base["require("]))
    gates.append(("红线 未新增 setInterval", "setInterval(", base["setInterval("]))
    gates.append(("红线 未新增 PRAGMA", "PRAGMA", base["PRAGMA"]))

    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        if not good:
            print("  [FAIL] %-52s actual=%d expect==%d" % (label, act, exp))
    print("  [%s] 门禁 %d 条" % ("OK" if ok else "FAIL", len(gates)))

    # 7) round-trip 自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    # 8) node --check 语法门禁（§5.0：字面门禁替代不了语法门禁）
    syn_ok, syn_msg = node_syntax_check(out)
    if not syn_ok:
        sys.stdout.write(syn_msg)
    print("  [%s] node --experimental-strip-types --check" % ("OK" if syn_ok else "FAIL"))
    ok = ok and syn_ok

    # 9) Node 真跑产物函数
    js = build_harness(src, out)
    r, res = run_harness(js)
    sem_ok = res is not None and res["fail"] == 0
    if res is not None:
        print("  [%s] Node 真跑语义校验  (total=%d fail=%d)" % ("OK" if sem_ok else "FAIL", res["total"], res["fail"]))
    else:
        print("  [FAIL] Node 真跑语义校验（无 HARNESS_RESULT）")
    ok = ok and sem_ok

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if not ok:
        fail("门禁未全绿，未写回")

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 10) 改前 .bak + 原子写回
    bak = "%s.bak-r225b-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r225b-", suffix=".tmp")
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
