# -*- coding: utf-8 -*-
r"""
srv_patch_r198.py -- R-198 妖灵「免费玩法·免费进食」+ 买额度上限 2 → 5（服务端环）

  ★ 用户原话（逐字，唯一依据）：
    「③④ 我一起说，现在的妖灵玩法，在「培养（出口：妖灵之力 PP）」加一栏「免费玩法」，
     里面放一个免费进食的按钮，喂食度一次加 100，一日 3 次，冷却 30 分钟。接着是免费互动的
     三个按钮，逗弄、梳毛、夜话。然后再接现在的「进食」和「买额度」，买额度改成 5 次，
     3 个选项共用 5 次上限。」

  ★ 环号说明：srv/index_v28.ts 末环 = R-194（[r194dao]，第 84 环）⇒ 本环顺延 **第 85 环**。
    锚点全部落在「R018 妖灵培养核心块 + pet_feed_log 建表/闸门/回显 + feed 端点」，
    与其余任何环零交集。

==============================================================================
零、改前取证（srv/index_v28.ts 字符级实测）
==============================================================================
  [证据 1] 买额度上限常量 @6414：`const R018_BUY_DAILY_MAX = 2;`（注释「每日买额度上限」）
    闸门 @13571（POST /api/pet/play 的 _buy 分支）：
      INSERT INTO pet_play_log (player_id, date, times, bought) VALUES (?, ?, 1, 1)
        ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1, bought = bought + 1 WHERE bought < ?
    ⇒ 3 个选项（tease/brush/talk）**共用同一 `bought` 计数**（WHERE bought < 2）。
    ⇒ 结论：**「3 个选项共用」现在就已成立**，本环只需把上限 2 → 5（改 1 个常量，闸门 SQL 一行未动）。

  [证据 2] 进食现状（POST /api/pet/feed @13453-13550）：
    · 付费三档 R018_FEED_TIERS：common 3000/+30 · fine 15000/+150 · immortal 60000/+600（本环一行未动）。
    · R-167「当日首次免费」闸门 @13483-13488（pet_feed_log.times < 1）⇒ 当日第 1 次付费进食免灵石。
    · 现状**没有**独立的「免费进食」动作（+100 喂食度 / 每日 3 次 / 30 分冷却）。
    · 喂食度上限 PET_HUNGER_MAX=9999、等级 = floor(hunger/100)（99 级封顶）—— 既有规则，
      免费进食 +100 后**仍走同一条 `MIN(9999, hunger+?)` 原子 UPDATE**，天然不越界。

  [证据 3] GET /api/pet @13344-13406：回显 `feedQuota:{date,used,free}`（R-167 免费进食口径），
    未回显任何「免费进食次数/冷却」字段。客户端 bundle 消费 `feedQuota.free`（[r189ui]）。

  [证据 4] pet_feed_log 建表 @583-590：`(player_id, date, times, PRIMARY KEY(player_id,date))`。
    ⇒ 本环复用该表：**新增两列** free_times（当日免费进食已用次数）+ last_free_at（冷却基准 ms）。
       不改 PK、不动 times（times 仍是 R-167 首免计数）⇒ 两套免费机制**独立共存、互不影响**。

==============================================================================
一、★ 与既有「当日首次免费」的关系（团队要求：冲突必须明说 + 给方案）
==============================================================================
  用户原话「然后再接**现在的**「进食」和「买额度」」⇒ 现有进食（含其 R-167 当日首次免费）
  **保留不动**（本环未删）。免费进食是**新增的独立动作**，因此：
    · 技术上**无冲突**：R-167 用 pet_feed_log.times（0/1）；本环用 free_times（0/3）+ last_free_at。
      两个计数器互不读写，同一天可以「先免费用 3 次免费进食、再用掉 1 次付费首免」，或反之。
    · 代价（已上报，待用户拍板）：每日免费喂食度 = 100×3（免费进食）+ 1 档付费档位喂食度（首免）。
      若用户希望「免费进食**取代**旧首免」（每日仅 300 点免费喂食度），
      只需后续一环删除 R-167 闸门分支（本环的 else 分支）+ 客户端去掉「今日首次免费」后缀即可，
      **不需要改本环任何代码**（本环 else 分支即 R-167 原闸门，逐字保留）。

==============================================================================
二、免费进食规则（服务端权威 · 客户端不可信）
==============================================================================
  · 每日 3 次（R198_FREE_FEED_MAX=3）、30 分钟冷却（R198_FREE_FEED_CD_MS=30*60*1000）、
    单次 +100 喂食度（R198_FREE_FEED_HUNGER=100）、免灵石。
  · 闸门 = pet_feed_log 单语句原子 upsert（与 R-167 / pet_play_log 同款口径）：
      INSERT INTO pet_feed_log (player_id, date, free_times, last_free_at) VALUES (?, ?, 1, ?)
        ON CONFLICT(player_id, date) DO UPDATE SET
          free_times = free_times + 1, last_free_at = excluded.last_free_at
        WHERE free_times < 3 AND (last_free_at IS NULL OR (? - last_free_at) >= 30min)
    ⇒ 新行（当日第 1 次）走 INSERT 分支：**无冷却继承**（跨日自然重置）；
      已存在行走 DO UPDATE：WHERE 不满足 ⇒ changes=0 ⇒ 拒绝（409）。
    ⇒ 冷却判定**全在服务端**（客户端只读回显字段，不可信）。
  · 拒绝体带 `freeFeed:{used,left,cdLeftMs,max,cdMs}`（剩余次数 / 剩余冷却毫秒）；
    成功体（feed 响应）与 GET /api/pet 同样回显 `freeFeed`，供 UI 渲染按钮态与倒计时。
  · 失败补偿：免费进食为 0 成本动作，下游（扣费/宠物行）几乎不可达；仍照 R-167 口径回退
    free_times 并把 last_free_at 置 NULL（罕见失败不把玩家锁在冷却里）。

==============================================================================
三、改动点（13 处；锚点全部纯 ASCII 且唯一）
==============================================================================
  1  `const R018_BUY_DAILY_MAX = 2;` → `= 5;`（3 选项共用上限 2→5）
  2  新增 3 个常量（R198_FREE_FEED_MAX / _CD_MS / _HUNGER；MARK 落此）
  3  pet_feed_log 建表块后**幂等加列** free_times / last_free_at（safeAddColumn，紧贴 CREATE 之后）
  4  feed handler：免费分支（_freeReq + _feed 按分支取值）
  5  feed handler：请求级状态补 `let _freeReq = false;`
  6  feed handler：闸门按分支（免费闸门 / R-167 原闸门逐字保留）
  7  feed handler：回退闭包按分支（免费回退 free_times+last_free_at / 付费回退 times）
  8  feed handler：catch 兜底回退按分支
  9  新增 helper `r198FreeFeedQuota()`（读 pet_feed_log 当日行 → 额度视图）
  10 GET /api/pet：查询源补 free_times / last_free_at
  11 GET /api/pet：回显 `freeFeed`（feedQuota 逐字保留）
  12 feed 响应补 `freeFeed`
  13 feed 日志 detail 的喂食度按分支（付费仍 +30 逐字，免费 +100）
  14 GET /api/pet consts 补 freeFeedMax / freeFeedCdMs / freeFeedHunger

契约
--------------------------------------------------------------------------
  CLI：--src <path>（就地原子写回；写回前落 .bak-r198-<时间戳>）/ --check / --selftest（只验不写）。
  幂等：产物含 /*[r198free]*/ ⇒ SKIP（不写盘，rc=0）。
  退出码：0=成功/跳过；1=契约/门禁失败；2=意外异常（IO/写回）。
  · 锚点唯一（count==1，纯 ASCII）；round-trip 正反双向自证后才原子写回。
  · 工程红线：不新增 require(（ESM 直跑）/ 不新增 res.status(403 / 不动 PRAGMA / 不新增 setInterval。
  · 服务端自证五步：--check rc=0 → 临时副本写回 → node --experimental-strip-types --check rc=0
    → 复跑 SKIP → 清理（--selftest 内置同款语法校验）。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（TS 源码合法块注释）
MARK = "/*[r198free]*/"

# ============================================================ 改动点（14 处）

# ── [1] 买额度上限 2 → 5（3 选项共用；闸门 SQL 一行未动）──────────────────────
E1_OLD = "const R018_BUY_DAILY_MAX = 2;"
E1_NEW = "const R018_BUY_DAILY_MAX = 5;"

# ── [2] 新增免费进食常量（MARK 落此）──────────────────────────────────────────
E2_OLD = "const R018_BUY_COST = 20000;"
E2_NEW = (
    "const R018_BUY_COST = 20000;\n"
    "// [r198free] R-198：免费玩法·免费进食（每日 3 次 · 30 分钟冷却 · +100 喂食度 · 免灵石）\n"
    "//   · 与 R-167「当日首次免费」**独立共存**（各用各的计数列：free_times / times，互不影响）。\n"
    "//   · MAX 每日次数上限；CD_MS 冷却毫秒；HUNGER 单次喂食度（+100 仍受 PET_HUNGER_MAX=9999 封顶）。\n"
    "const R198_FREE_FEED_MAX = 3;\n"
    "const R198_FREE_FEED_CD_MS = 30 * 60 * 1000;\n"
    "const R198_FREE_FEED_HUNGER = 100; " + MARK
)

# ── [3] pet_feed_log 幂等加列（紧贴 CREATE 之后 ⇒ 冷启动表已存在）──────────────
E3_OLD = (
    "  db.run(`\n"
    "    CREATE TABLE IF NOT EXISTS pet_feed_log (\n"
    "      player_id INTEGER NOT NULL,\n"
    "      date TEXT NOT NULL,\n"
    "      times INTEGER NOT NULL DEFAULT 0,\n"
    "      PRIMARY KEY (player_id, date),\n"
    "      FOREIGN KEY (player_id) REFERENCES users (id)\n"
    "    )\n"
    "  `);"
)
E3_NEW = (
    E3_OLD + "\n"
    "  // [r198free] R-198：免费进食额度列（**幂等加列**，DDL 自带幂等；紧贴 CREATE 之后 ⇒ 冷启动表已存在）。\n"
    "  //   · free_times   —— 当日免费进食已用次数（0..R198_FREE_FEED_MAX）\n"
    "  //   · last_free_at —— 上次免费进食时刻（ms；30 分钟冷却基准）\n"
    "  safeAddColumn('pet_feed_log', 'free_times', 'ALTER TABLE pet_feed_log ADD COLUMN free_times INTEGER NOT NULL DEFAULT 0');\n"
    "  safeAddColumn('pet_feed_log', 'last_free_at', 'ALTER TABLE pet_feed_log ADD COLUMN last_free_at INTEGER');"
)

# ── [4] feed handler：免费分支（_freeReq + _feed 按分支取值）───────────────────
E4_OLD = (
    "    const _feedTier = r018FeedTier(req.body?.tier);\n"
    "    const _feed = { cost: _feedTier.cost, hunger: _feedTier.hunger, name: _feedTier.name };"
)
E4_NEW = (
    "    // [r198free] R-198：免费进食分支（每日 3 次 · 30 分钟冷却 · +100 喂食度 · 免灵石）。\n"
    "    //   请求体 { free: true } ⇒ 走免费闸门；否则照 R-167 付费进食（含当日首次免费，逐字保留）。\n"
    "    _freeReq = !!req.body?.free;\n"
    "    const _feedTier = r018FeedTier(req.body?.tier);\n"
    "    const _feed = _freeReq\n"
    "      ? { cost: 0, hunger: R198_FREE_FEED_HUNGER, name: '免费进食' }\n"
    "      : { cost: _feedTier.cost, hunger: _feedTier.hunger, name: _feedTier.name };"
)

# ── [5] 请求级状态补 _freeReq（try 外声明 ⇒ catch 兜底回退可见）─────────────────
E5_OLD = (
    "  let _feedFree = false;\n"
    "  let _feedDate = '';\n"
    "  let _feedDone = false;"
)
E5_NEW = (
    "  let _feedFree = false;\n"
    "  let _feedDate = '';\n"
    "  let _feedDone = false;\n"
    "  let _freeReq = false; // [r198free] R-198：本次是否「免费进食」（catch 兜底回退分支用）"
)

# ── [6] 闸门按分支（免费闸门 / R-167 原闸门逐字保留）──────────────────────────
E6_OLD = (
    "    _feedDate = petDate(Date.now());\n"
    "    const _feedGate = await dbRun(\n"
    "      'INSERT INTO pet_feed_log (player_id, date, times) VALUES (?, ?, 1) ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1 WHERE times < 1',\n"
    "      [userId, _feedDate]\n"
    "    );\n"
    "    _feedFree = _feedGate.changes > 0;\n"
    "    if (_feedFree) _feed.cost = 0;"
)
E6_NEW = (
    "    _feedDate = petDate(Date.now());\n"
    "    if (_freeReq) {\n"
    "      // [r198free] R-198 免费进食闸门：每日 3 次 + 30 分钟冷却（单语句原子；changes>0 才放行）。\n"
    "      //   INSERT ... DO UPDATE SET free_times=free_times+1, last_free_at=excluded.last_free_at\n"
    "      //     WHERE free_times < 3 AND (last_free_at IS NULL OR (now-last_free_at) >= 30min)\n"
    "      //   ★ 新行（当日首次）走 INSERT 分支：无冷却继承（跨日重置）；WHERE 仅在已存在行时生效。\n"
    "      //   ★ 拒绝时回显剩余次数 / 剩余冷却毫秒（客户端据此渲染按钮态）。\n"
    "      const _nowMs = Date.now();\n"
    "      const _freeGate = await dbRun(\n"
    "        'INSERT INTO pet_feed_log (player_id, date, free_times, last_free_at) VALUES (?, ?, 1, ?) ON CONFLICT(player_id, date) DO UPDATE SET free_times = free_times + 1, last_free_at = excluded.last_free_at WHERE free_times < ? AND (last_free_at IS NULL OR (? - last_free_at) >= ?)',\n"
    "        [userId, _feedDate, _nowMs, R198_FREE_FEED_MAX, _nowMs, R198_FREE_FEED_CD_MS]\n"
    "      );\n"
    "      if (!_freeGate.changes) {\n"
    "        const _q = await r198FreeFeedQuota(userId, _feedDate);\n"
    "        return res.status(409).json({ error: _q.left <= 0 ? `今日免费进食已用完（每日 ${R198_FREE_FEED_MAX} 次）` : `免费进食冷却中（还需 ${Math.ceil(_q.cdLeftMs / 60000)} 分钟）`, freeFeed: _q });\n"
    "      }\n"
    "      _feedFree = true; // [r198free] 占用一次免费额度（下游失败时回退）\n"
    "    } else {\n"
    "      // [r167feed] R-167 原「当日首次免费」闸门（本环一行未动）\n"
    "      const _feedGate = await dbRun(\n"
    "        'INSERT INTO pet_feed_log (player_id, date, times) VALUES (?, ?, 1) ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1 WHERE times < 1',\n"
    "        [userId, _feedDate]\n"
    "      );\n"
    "      _feedFree = _feedGate.changes > 0;\n"
    "      if (_feedFree) _feed.cost = 0;\n"
    "    }"
)

# ── [7] 回退闭包按分支（免费回退 free_times+last_free_at / 付费回退 times）──────
E7_OLD = (
    "      await dbRun('UPDATE pet_feed_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?', [userId, _feedDate]);\n"
    "    };\n"
    "    if (bal < _feed.cost)"
)
E7_NEW = (
    "      if (_freeReq) {\n"
    "        await dbRun('UPDATE pet_feed_log SET free_times = MAX(0, free_times - 1), last_free_at = NULL WHERE player_id = ? AND date = ?', [userId, _feedDate]);\n"
    "      } else {\n"
    "        await dbRun('UPDATE pet_feed_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?', [userId, _feedDate]);\n"
    "      }\n"
    "    };\n"
    "    if (bal < _feed.cost)"
)

# ── [8] catch 兜底回退按分支 ─────────────────────────────────────────────────
E8_OLD = (
    "    if (_feedFree && !_feedDone) { _feedFree = false; try { await dbRun('UPDATE pet_feed_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?', [userId, _feedDate]); } catch {} }"
)
E8_NEW = (
    "    if (_feedFree && !_feedDone) { _feedFree = false; try { await dbRun(_freeReq ? 'UPDATE pet_feed_log SET free_times = MAX(0, free_times - 1), last_free_at = NULL WHERE player_id = ? AND date = ?' : 'UPDATE pet_feed_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?', [userId, _feedDate]); } catch {} }"
)

# ── [9] helper r198FreeFeedQuota（插在 GET /api/pet 之前）────────────────────
E9_OLD = "app.get('/api/pet', authenticateToken, rateLimit({"
E9_NEW = (
    "// [r198free] R-198 免费进食额度视图（读 pet_feed_log 当日行；供 GET /api/pet 与 feed 响应）。\n"
    "//   cdLeftMs：距下次可免费进食的剩余毫秒（left<=0 或从未进食 ⇒ 0）。\n"
    "async function r198FreeFeedQuota(userId: number, date: string): Promise<{ used: number; left: number; cdLeftMs: number; max: number; cdMs: number }> {\n"
    "  const row: any = await dbGet('SELECT free_times, last_free_at FROM pet_feed_log WHERE player_id = ? AND date = ?', [userId, date]);\n"
    "  const used = Math.min(R198_FREE_FEED_MAX, Math.max(0, Number(row?.free_times) || 0));\n"
    "  const left = Math.max(0, R198_FREE_FEED_MAX - used);\n"
    "  const lastAt = Number(row?.last_free_at) || 0;\n"
    "  const cdLeftMs = (left <= 0 || !lastAt) ? 0 : Math.max(0, R198_FREE_FEED_CD_MS - (Date.now() - lastAt));\n"
    "  return { used, left, cdLeftMs, max: R198_FREE_FEED_MAX, cdMs: R198_FREE_FEED_CD_MS };\n"
    "}\n"
    "\n"
    "app.get('/api/pet', authenticateToken, rateLimit({"
)

# ── [10] GET /api/pet 查询源补两列 ───────────────────────────────────────────
E10_OLD = "      dbGet('SELECT times FROM pet_feed_log WHERE player_id = ? AND date = ?', [userId, today]),"
E10_NEW = "      dbGet('SELECT times, free_times, last_free_at FROM pet_feed_log WHERE player_id = ? AND date = ?', [userId, today]),"

# ── [11] GET /api/pet 回显 freeFeed（feedQuota 逐字保留）─────────────────────
E11_OLD = (
    "      feedQuota: {\n"
    "        date: today,\n"
    "        used: Math.min(1, Number(feed?.times) || 0),\n"
    "        free: (Number(feed?.times) || 0) < 1,\n"
    "      },"
)
E11_NEW = (
    "      feedQuota: {\n"
    "        date: today,\n"
    "        used: Math.min(1, Number(feed?.times) || 0),\n"
    "        free: (Number(feed?.times) || 0) < 1,\n"
    "      },\n"
    "      // [r198free] R-198：免费进食额度（used/left/cdLeftMs/max/cdMs）—— 与 R-167 feedQuota 并列回显。\n"
    "      freeFeed: (() => {\n"
    "        const _u = Math.min(R198_FREE_FEED_MAX, Math.max(0, Number(feed?.free_times) || 0));\n"
    "        const _l = Math.max(0, R198_FREE_FEED_MAX - _u);\n"
    "        const _la = Number(feed?.last_free_at) || 0;\n"
    "        const _cd = (_l <= 0 || !_la) ? 0 : Math.max(0, R198_FREE_FEED_CD_MS - (Date.now() - _la));\n"
    "        return { used: _u, left: _l, cdLeftMs: _cd, max: R198_FREE_FEED_MAX, cdMs: R198_FREE_FEED_CD_MS };\n"
    "      })(),"
)

# ── [12] feed 响应补 freeFeed ────────────────────────────────────────────────
E12_OLD = "    res.json({ ok: true, pet: petView(fresh), battleReached, milestones: _miles, spirit: await r018SpiritSync(userId) });"
E12_NEW = "    res.json({ ok: true, pet: petView(fresh), battleReached, milestones: _miles, spirit: await r018SpiritSync(userId), freeFeed: await r198FreeFeedQuota(userId, _feedDate) });"

# ── [13] 日志 detail 喂食度按分支（付费仍 +30 逐字，免费 +100）───────────────────
E13_OLD = "+${PET_HUNGER_PER_FEED}`);"
E13_NEW = "+${_freeReq ? R198_FREE_FEED_HUNGER : PET_HUNGER_PER_FEED}`);"

# ── [14] consts 补 freeFeedMax / freeFeedCdMs / freeFeedHunger ───────────────
E14_OLD = "        buyCost: R018_BUY_COST, buyDailyMax: R018_BUY_DAILY_MAX,"
E14_NEW = (
    "        buyCost: R018_BUY_COST, buyDailyMax: R018_BUY_DAILY_MAX,\n"
    "        freeFeedMax: R198_FREE_FEED_MAX, freeFeedCdMs: R198_FREE_FEED_CD_MS, freeFeedHunger: R198_FREE_FEED_HUNGER,"
)

EDITS = [
    ("R198 买额度上限 2->5", E1_OLD, E1_NEW),
    ("R198 免费进食常量（MARK）", E2_OLD, E2_NEW),
    ("R198 pet_feed_log 幂等加列 free_times/last_free_at", E3_OLD, E3_NEW),
    ("R198 feed 免费分支（_freeReq + _feed 取值）", E4_OLD, E4_NEW),
    ("R198 feed 请求级状态补 _freeReq", E5_OLD, E5_NEW),
    ("R198 闸门按分支（免费/R-167 原闸门保留）", E6_OLD, E6_NEW),
    ("R198 回退闭包按分支", E7_OLD, E7_NEW),
    ("R198 catch 兜底回退按分支", E8_OLD, E8_NEW),
    ("R198 helper r198FreeFeedQuota", E9_OLD, E9_NEW),
    ("R198 GET /api/pet 查询源补两列", E10_OLD, E10_NEW),
    ("R198 GET /api/pet 回显 freeFeed", E11_OLD, E11_NEW),
    ("R198 feed 响应补 freeFeed", E12_OLD, E12_NEW),
    ("R198 日志 detail 喂食度按分支", E13_OLD, E13_NEW),
    ("R198 consts 补 freeFeed*", E14_OLD, E14_NEW),
]

# ============================================================ 依赖（绝对在位，锚点唯一）

REQUIRES = [
    ("const R018_FEED_TIERS", "==", 1, "付费三档表必须在位（本环一行未动）"),
    ("function r018FeedTier(", "==", 1, "喂养档位函数必须在位（本环只读）"),
    ("function r018PlayKind(", "==", 1, "互动种类函数必须在位（本环一行未动）"),
    ("const R018_BUY_COST = 20000;", "==", 1, "买额度单价必须在位（本环一行未动）"),
    ("const R018_BUY_DAILY_MAX = 2;", "==", 1, "买额度上限旧值必须在位（本环改 5）"),
    ("const PET_HUNGER_MAX = 9999;", "==", 1, "喂食度上限必须在位（免费 +100 仍受其封顶）"),
    ("const PET_LEVEL_DIVISOR = 100;", "==", 1, "升级除数必须在位（本环一行未动）"),
    ("CREATE TABLE IF NOT EXISTS pet_feed_log (", "==", 1, "pet_feed_log 建表必须在位（本环加列）"),
    ("const safeAddColumn = (table: string, col: string, ddl: string) => {", "==", 1,
     "既有幂等建列器必须在位（本环复用，不自造）"),
    ("app.post('/api/pet/feed', authenticateToken", "==", 1, "feed 端点必须在位（本环接线免费分支）"),
    ("app.get('/api/pet', authenticateToken", "==", 1, "GET /api/pet 必须在位（本环回显 freeFeed）"),
    ("function dbGet<T = any>(sql: string, params: any[] = []): Promise<T | undefined> {", "==", 1,
     "dbGet 必须在位（helper 读当日行）"),
    ("function dbRun(", "==", 1, "dbRun 必须在位（单语句原子闸门）"),
    ("function petDate(", "==", 1, "日期键换算必须在位（与 R-167 同口径）"),
    ("INSERT INTO pet_play_log (player_id, date, times, bought) VALUES (?, ?, 1, 1)", "==", 1,
     "买额度闸门必须在位（本环只改常量，SQL 一行未动）"),
    ("[r194dao]", ">=", 1, "R-194 环必须已应用（链序约束：本环排其后）"),
    ("[r167feed]", ">=", 1, "R-167 环必须已应用（本环保留其闸门为 else 分支）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 付费进食 / 互动（本环一行未动）
    "const R018_FEED_TIERS",
    "function r018FeedTier(",
    "function r018PlayKind(",
    "const PET_HUNGER_PER_FEED = 30;",
    "const PET_HUNGER_MAX = 9999;",
    "const PET_LEVEL_DIVISOR = 100;",
    # R-167 原闸门 SQL（本环保留为 else 分支，逐字未动）
    "INSERT INTO pet_feed_log (player_id, date, times) VALUES (?, ?, 1) ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1 WHERE times < 1",
    # 买额度闸门（本环只改常量）
    "INSERT INTO pet_play_log (player_id, date, times, bought) VALUES (?, ?, 1, 1)",
    "app.post('/api/pet/play', authenticateToken",
    "app.post('/api/pet/feed', authenticateToken",
    "app.get('/api/pet', authenticateToken",
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
        ("R198 幂等标记在位", MARK, 1, "==", "本环已应用"),
        # ── 买额度 2->5 ──
        ("R198 买额度上限=5", "const R018_BUY_DAILY_MAX = 5;", 1, "==", "3 选项共用上限改 5"),
        ("R198 旧上限 2 清零", "const R018_BUY_DAILY_MAX = 2;", 0, "==", "旧值消失"),
        # ── 免费进食常量 ──
        ("R198 常量 MAX=3", "const R198_FREE_FEED_MAX = 3;", 1, "==", "每日 3 次"),
        ("R198 常量 CD=30min", "const R198_FREE_FEED_CD_MS = 30 * 60 * 1000;", 1, "==", "30 分钟冷却"),
        ("R198 常量 HUNGER=100", "const R198_FREE_FEED_HUNGER = 100;", 1, "==", "单次 +100 喂食度"),
        # ── 幂等加列 ──
        ("R198 新列 DDL free_times", "'ALTER TABLE pet_feed_log ADD COLUMN free_times INTEGER NOT NULL DEFAULT 0'", 1, "==", "safeAddColumn"),
        ("R198 新列 DDL last_free_at", "'ALTER TABLE pet_feed_log ADD COLUMN last_free_at INTEGER'", 1, "==", "safeAddColumn"),
        # ── 闸门 ──
        ("R198 免费闸门 SQL（次数+冷却）",
         "ON CONFLICT(player_id, date) DO UPDATE SET free_times = free_times + 1, last_free_at = excluded.last_free_at WHERE free_times < ? AND (last_free_at IS NULL OR (? - last_free_at) >= ?)",
         1, "==", "单语句原子：3 次 + 30 分冷却"),
        ("R198 免费闸门占用标记", "_feedFree = true; // [r198free]", 1, "==", "占用免费额度"),
        ("R198 拒绝体带 freeFeed", "freeFeed: _q });", 1, "==", "剩余次数/冷却回显"),
        ("R198 R-167 原闸门保留", "ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1 WHERE times < 1", 1, "==", "else 分支逐字保留"),
        # ── 回退 ──
        ("R198 回退闭包分支", "SET free_times = MAX(0, free_times - 1), last_free_at = NULL WHERE player_id = ? AND date = ?", 2, "==", "闭包 + catch 各一处"),
        ("R198 付费回退 times 保留", "UPDATE pet_feed_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?", 2, "==", "else 分支 + catch 三目各一处"),
        # ── helper + 回显 ──
        ("R198 helper 唯一入口", "async function r198FreeFeedQuota(", 1, "==", "额度视图"),
        ("R198 GET 查询源补两列", "dbGet('SELECT times, free_times, last_free_at FROM pet_feed_log WHERE player_id = ? AND date = ?', [userId, today]),", 1, "==", "GET /api/pet"),
        ("R198 GET 回显 freeFeed", "freeFeed: (() => {", 1, "==", "GET /api/pet"),
        ("R198 feed 响应补 freeFeed", "spirit: await r018SpiritSync(userId), freeFeed: await r198FreeFeedQuota(userId, _feedDate) });", 1, "==", "feed 成功体"),
        ("R198 consts 补 freeFeedMax", "freeFeedMax: R198_FREE_FEED_MAX, freeFeedCdMs: R198_FREE_FEED_CD_MS, freeFeedHunger: R198_FREE_FEED_HUNGER,", 1, "==", "常量表下发"),
        ("R198 日志 detail 分支", "+${_freeReq ? R198_FREE_FEED_HUNGER : PET_HUNGER_PER_FEED}`);", 1, "==", "免费 +100 / 付费 +30"),
        # ── 冻结：付费进食 / 互动 / R-167 口径未动 ──
        ("R198 冻结·R018_FEED_TIERS", "const R018_FEED_TIERS", 1, "==", "三档表未动"),
        ("R198 冻结·r018FeedTier", "function r018FeedTier(", 1, "==", "未动"),
        ("R198 冻结·r018PlayKind", "function r018PlayKind(", 1, "==", "未动"),
        ("R198 冻结·PET_HUNGER_PER_FEED", "const PET_HUNGER_PER_FEED = 30;", 1, "==", "付费喂食度常量未动"),
        ("R198 冻结·PET_HUNGER_MAX", "const PET_HUNGER_MAX = 9999;", 1, "==", "喂食度上限未动"),
        ("R198 冻结·PET_LEVEL_DIVISOR", "const PET_LEVEL_DIVISOR = 100;", 1, "==", "升级除数未动"),
        ("R198 冻结·买额度闸门 SQL", "INSERT INTO pet_play_log (player_id, date, times, bought) VALUES (?, ?, 1, 1)", 1, "==", "SQL 一行未动"),
        ("R198 冻结·feedQuota 保留", "feedQuota: {", 1, "==", "R-167 回显保留"),
        ("R198 冻结·play 端点", "app.post('/api/pet/play', authenticateToken", 1, "==", "未动"),
        ("R198 冻结·feed 端点仍在", "app.post('/api/pet/feed', authenticateToken", 1, "==", "未动"),
        # ── 工程红线（相对计数）──
        ("R198 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403"),
        ("R198 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R198 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库（复用 safeAddColumn）"),
        ("R198 红线·无 require", "require(", 0, "==", "ESM 不新增 require"),
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
    """在临时副本上跑 node --experimental-strip-types --check；返回 (rc, node)（node 缺失 → (None,None)）。"""
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


def main():
    ap = argparse.ArgumentParser(description="R-198 妖灵免费玩法·免费进食 + 买额度 5（服务端环）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：产物含标记 ⇒ SKIP（不写盘，rc=0）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

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

    # 6) 门禁（五元组）
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-46s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证（正向重放一致 + 逆向逐字节还原）
    if out != _apply(src):
        fail("round-trip(正向重构) mismatch")
    rt_ok, rt_msg = _roundtrip(out, src)
    if not rt_ok:
        fail("round-trip(逆向) mismatch：%s" % rt_msg)

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    # 8) 语法自证（node --experimental-strip-types --check；node 缺失则跳过）
    if a.check or a.selftest:
        rc, node = _node_check(out)
        print("  node --check rc=%s (%s)" % (rc, node or 'node not found (skipped)'))
        if rc not in (None, 0):
            fail("node --experimental-strip-types --check 未通过")
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r198-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r198free-", suffix=".tmp")
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
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        print("[ERROR] %s: %s" % (type(e).__name__, e))
        sys.exit(2)
