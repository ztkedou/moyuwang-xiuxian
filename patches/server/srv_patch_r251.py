# -*- coding: utf-8 -*-
r"""
srv_patch_r251.py -- R-250 服务端环（服务端第 95 环 / 新末环）

唯一真相源：策划_仙务称号体系扩充_20261011.md（§3.2 日期门 + 新表 / §4 四新榜 / §5.1 服务端接口冻结 / §6 工单边界）。
本文件只按该规格实现，任何偏离必须先改那份规格文件。

背景（基座 = 94 环终态 srv/index_v28.ts，md5 6fe5bf9c33ae5bd3008cbb8f36443860）
--------------------------------------------------------------------------
  · r249 已落地：RANK_TITLE_SOURCES(三榜) / reconcileRankTitles / rankHoldersSnapshot /
    RANK_TITLE_TICK_MS(10 分钟) / 三句 UPDATE titles SET attr_json / rankHolders 端点注入。
  · 缺口：结算周期过频（10 分钟）；只有 3 榜 3 称号；rankHolders 只 3 键。
  ⇒ 本环：加「每北京日一次」的日期门 + 4 新榜/4 新称号 + rankHolders 扩 7 键。

机制（逐条）
--------------------------------------------------------------------------
  ① 新表 rank_title_state(id=1, last_date TEXT)（幂等 DDL + INSERT OR IGNORE 单行）。
  ② reconcileRankTitles() 开头加日期门：bjDate(Date.now()) 取今日；dbGet 读 last_date；
     相等即 return（空转，零写）；真正结算**成功走完**后 UPDATE last_date（放最后，抛异常不误标）。
  ③ RANK_TITLE_TICK_MS 10*60*1000 → 60*60*1000（每小时检查；真正结算由日期门保证每北京日一次）。
  ④ LEADERBOARD_SORTS 追加 kills/achieve/playtime/fame（orderBy + aheadCondition + getParams，照 combat 同构）。
  ⑤ 4 条称号 seed（INSERT OR IGNORE）：万人敌 atkRate .10 / 功成名就 expRate .10 /
     苦修不辍 defRate .10 / 德高望重 stoneRate .10。
  ⑥ RANK_TITLE_SOURCES 追加 4 条 ⇒ 合计 7 条；rankHoldersSnapshot out 扩为 7 键。
  ⑦ GET /api/leaderboard/me 的 queries 追加 4 条（既有 3 条不改）⇒ 响应新增 kills_rank /
     achieve_rank / playtime_rank / fame_rank（避免客户端「我的排名」三元链回落显示灵石榜名次）。

★ `/api/leaderboard` 的 sort 校验（本环已核实）：`const sortConfig = LEADERBOARD_SORTS[sort] || LEADERBOARD_SORTS.realm;`
  —— **非硬编码白名单**，按 LEADERBOARD_SORTS 的键取值、未知回落 realm。故新增 4 键即自动放行，端点**无需改动**。

设计取向
--------------------------------------------------------------------------
  · 冻结 LEADERBOARD_SORTS 既有 3 条 orderBy（必须与 /api/leaderboard 逐字同源）、
    rankings/titles/player_titles 表结构、既有 3 条称号 seed、其它任何 API —— 一律不改。
  · 复用（不改名、不改语义）：RANK_TITLE_SOURCES / LEADERBOARD_SORTS / grantTitleBySource /
    shouldGrantRankTitle / bjDate / dbGet / dbRun / attr_json 键名。
  · 日期门 + 结算写入同在 reconcileRankTitles 的 try 内 ⇒ DB 异常被自吞，绝不阻塞存档链路。

CLI 契约（照 srv_patch_r233.py / r249.py）
--------------------------------------------------------------------------
  `--src <path>`：就地原子写回该路径（写回前落 `<src>.bak-r251-<时间戳>`）。
  `--check` / `--selftest`：只校验不写回（含 Node 语法门禁 + sqlite3 语义真跑）。
  `--reverse <path>`：反向对照——在**未打 r251 的服务端**上跑同一套断言，必须确认标记缺席。
  退出码：0=成功 / 3=幂等（产物已含 [r251]）/ 2=锚点不符 / 1=门禁失败。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `PRAGMA`。
  · 只改服务端；不改客户端 bundle；不改任何既有 srv_patch_*.py / chain_build.py / deploy_*/。
  · 每处替换 expect=1，命中数不符即中止（退出码 2）；产物 round-trip 自证 + Node 语法门禁
    + sqlite3 语义真跑后原子写回。
"""

import argparse
import functools
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# 本脚本位于 <repo>/patches/server/，服务端源码在 <repo>/srv/index_v28.ts ⇒ 上跳两级到仓库根再拼。
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), "srv", "index_v28.ts")

MARK = "[r251]"

# ============================================================ 与注入 TS 逐字同源的 SQL 常量
# ★ 这些常量既用于 sqlite3 语义真跑（harness），也由门禁断言「必须出现在产物中」——
#   从而保证「测的就是发出去的逻辑」，不是另一套等价实现。
SQL_DELETE_ALL = "DELETE FROM player_titles WHERE title_id = ?"
SQL_DELETE_OTHERS = "DELETE FROM player_titles WHERE title_id = ? AND user_id != ?"
SQL_CLEAR_EQUIP_ALL = "UPDATE saves SET title_id = NULL WHERE title_id = ?"
SQL_CLEAR_EQUIP_OTHERS = "UPDATE saves SET title_id = NULL WHERE title_id = ? AND user_id != ?"
SQL_INSERT_OR_IGNORE = "INSERT OR IGNORE INTO player_titles (user_id, title_id) VALUES (?, ?)"
SQL_TOP = "SELECT user_id FROM rankings ORDER BY"
SQL_COUNT = "SELECT COUNT(*) AS c FROM rankings"
SQL_TITLE_ID = "SELECT id FROM titles WHERE source = ?"
# R-250 新增
SQL_STATE_DDL = "CREATE TABLE IF NOT EXISTS rank_title_state"
SQL_STATE_SEED = "INSERT OR IGNORE INTO rank_title_state (id, last_date) VALUES (1, '')"
SQL_STATE_SEL = "SELECT last_date FROM rank_title_state WHERE id = 1"
SQL_STATE_UPD = "UPDATE rank_title_state SET last_date = ? WHERE id = 1"
SQL_SEED = "INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES"

# LEADERBOARD_SORTS 七条 orderBy 的**逐字镜像**（既有 3 条为冻结基线；harness 取 #1 用）。
ORDERBY = {
    "realm": "realm_index DESC, realm_level DESC, exp DESC, updated_at DESC, user_id ASC",
    "combat": "combat_power DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC",
    "stones": "spirit_stones DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC",
    "kills": "kill_count DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC",
    "achieve": "achievement_count DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC",
    "playtime": "play_time DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC",
    "fame": "reputation DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC",
}
# RANK_TITLE_SOURCES 的**逐字镜像**（source ↔ sort），合计 7 条。
RANK_SOURCES = [
    ("rank_realm", "realm"), ("rank_combat", "combat"), ("rank_stones", "stones"),
    ("rank_kills", "kills"), ("rank_achieve", "achieve"),
    ("rank_playtime", "playtime"), ("rank_fame", "fame"),
]
MIN_BOARD_SIZE = 2

# ============================================================ 改动点（全部 expect=1）
EDITS = [
    # ① 新表 rank_title_state + 4 条新称号 seed（插在既有称号 seed 区之后、Y2 daily_quests 之前）
    ("R251 新表 rank_title_state + 4 称号 seed",
     "  db.run('UPDATE titles SET attr_json = ? WHERE source = ?', ['{\"expRate\":0.15}', 'rank_realm']);    // [r249] 登峰造极 · 境界第一 ⇒ 修为 +15%\n",
     "  db.run('UPDATE titles SET attr_json = ? WHERE source = ?', ['{\"expRate\":0.15}', 'rank_realm']);    // [r249] 登峰造极 · 境界第一 ⇒ 修为 +15%\n"
     "  // [r251] 四新榜称号 seed（INSERT OR IGNORE 幂等，照既有 3 条 seed 写法）：各 10%（比旧 3 榜 15% 低 —— 这 4 项更易登顶）。\n"
     "  db.run(`INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES\n"
     "    ('万人敌', '{\"atkRate\":0.10}', 'rank_kills'),\n"
     "    ('功成名就', '{\"expRate\":0.10}', 'rank_achieve'),\n"
     "    ('苦修不辍', '{\"defRate\":0.10}', 'rank_playtime'),\n"
     "    ('德高望重', '{\"stoneRate\":0.10}', 'rank_fame')`);\n"
     "  // [r251] 排行称号结算状态（单行表 id=1）：last_date = 上次真正结算的北京日（YYYY-MM-DD）。\n"
     "  //   日期门依据：同北京日重复调用 reconcileRankTitles ⇒ 空转（零写）；跨天 / 首部署(last_date='') ⇒ 立即结算一次。\n"
     "  db.run(`\n"
     "    CREATE TABLE IF NOT EXISTS rank_title_state (\n"
     "      id INTEGER PRIMARY KEY CHECK (id = 1),\n"
     "      last_date TEXT NOT NULL DEFAULT ''\n"
     "    )\n"
     "  `);\n"
     "  db.run(\"INSERT OR IGNORE INTO rank_title_state (id, last_date) VALUES (1, '')\");\n"),

    # ② LEADERBOARD_SORTS 追加 4 条（照 combat 条目同构：orderBy + aheadCondition + getParams）
    ("R251 LEADERBOARD_SORTS 追加 4 榜",
     "      row.spirit_stones, row.realm_index, row.realm_level, row.updated_at, row.user_id,\n"
     "    ],\n"
     "  },\n"
     "};\n",
     "      row.spirit_stones, row.realm_index, row.realm_level, row.updated_at, row.user_id,\n"
     "    ],\n"
     "  },\n"
     "  // [r251] 四新榜（各 10% 档）：orderBy / aheadCondition / getParams 照 combat 条目同构，仅换主排序列。\n"
     "  kills: {\n"
     "    orderBy: 'kill_count DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC',\n"
     "    aheadCondition: `\n"
     "      (kill_count > ?)\n"
     "      OR (kill_count = ? AND realm_index > ?)\n"
     "      OR (kill_count = ? AND realm_index = ? AND realm_level > ?)\n"
     "      OR (kill_count = ? AND realm_index = ? AND realm_level = ? AND updated_at > ?)\n"
     "      OR (kill_count = ? AND realm_index = ? AND realm_level = ? AND updated_at = ? AND user_id < ?)\n"
     "    `,\n"
     "    getParams: (row) => [\n"
     "      row.kill_count,\n"
     "      row.kill_count, row.realm_index,\n"
     "      row.kill_count, row.realm_index, row.realm_level,\n"
     "      row.kill_count, row.realm_index, row.realm_level, row.updated_at,\n"
     "      row.kill_count, row.realm_index, row.realm_level, row.updated_at, row.user_id,\n"
     "    ],\n"
     "  },\n"
     "  achieve: {\n"
     "    orderBy: 'achievement_count DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC',\n"
     "    aheadCondition: `\n"
     "      (achievement_count > ?)\n"
     "      OR (achievement_count = ? AND realm_index > ?)\n"
     "      OR (achievement_count = ? AND realm_index = ? AND realm_level > ?)\n"
     "      OR (achievement_count = ? AND realm_index = ? AND realm_level = ? AND updated_at > ?)\n"
     "      OR (achievement_count = ? AND realm_index = ? AND realm_level = ? AND updated_at = ? AND user_id < ?)\n"
     "    `,\n"
     "    getParams: (row) => [\n"
     "      row.achievement_count,\n"
     "      row.achievement_count, row.realm_index,\n"
     "      row.achievement_count, row.realm_index, row.realm_level,\n"
     "      row.achievement_count, row.realm_index, row.realm_level, row.updated_at,\n"
     "      row.achievement_count, row.realm_index, row.realm_level, row.updated_at, row.user_id,\n"
     "    ],\n"
     "  },\n"
     "  playtime: {\n"
     "    orderBy: 'play_time DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC',\n"
     "    aheadCondition: `\n"
     "      (play_time > ?)\n"
     "      OR (play_time = ? AND realm_index > ?)\n"
     "      OR (play_time = ? AND realm_index = ? AND realm_level > ?)\n"
     "      OR (play_time = ? AND realm_index = ? AND realm_level = ? AND updated_at > ?)\n"
     "      OR (play_time = ? AND realm_index = ? AND realm_level = ? AND updated_at = ? AND user_id < ?)\n"
     "    `,\n"
     "    getParams: (row) => [\n"
     "      row.play_time,\n"
     "      row.play_time, row.realm_index,\n"
     "      row.play_time, row.realm_index, row.realm_level,\n"
     "      row.play_time, row.realm_index, row.realm_level, row.updated_at,\n"
     "      row.play_time, row.realm_index, row.realm_level, row.updated_at, row.user_id,\n"
     "    ],\n"
     "  },\n"
     "  fame: {\n"
     "    orderBy: 'reputation DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC',\n"
     "    aheadCondition: `\n"
     "      (reputation > ?)\n"
     "      OR (reputation = ? AND realm_index > ?)\n"
     "      OR (reputation = ? AND realm_index = ? AND realm_level > ?)\n"
     "      OR (reputation = ? AND realm_index = ? AND realm_level = ? AND updated_at > ?)\n"
     "      OR (reputation = ? AND realm_index = ? AND realm_level = ? AND updated_at = ? AND user_id < ?)\n"
     "    `,\n"
     "    getParams: (row) => [\n"
     "      row.reputation,\n"
     "      row.reputation, row.realm_index,\n"
     "      row.reputation, row.realm_index, row.realm_level,\n"
     "      row.reputation, row.realm_index, row.realm_level, row.updated_at,\n"
     "      row.reputation, row.realm_index, row.realm_level, row.updated_at, row.user_id,\n"
     "    ],\n"
     "  },\n"
     "};\n"),

    # ③ RANK_TITLE_SOURCES 追加 4 条 ⇒ 合计 7 条
    ("R251 RANK_TITLE_SOURCES 追加 4 条",
     "  { source: 'rank_stones', sort: 'stones' },\n];\n",
     "  { source: 'rank_stones', sort: 'stones' },\n"
     "  // [r251] 四新榜称号来源（与 LEADERBOARD_SORTS 新键逐字对应）。\n"
     "  { source: 'rank_kills', sort: 'kills' },\n"
     "  { source: 'rank_achieve', sort: 'achieve' },\n"
     "  { source: 'rank_playtime', sort: 'playtime' },\n"
     "  { source: 'rank_fame', sort: 'fame' },\n"
     "];\n"),

    # ④ RANK_TITLE_TICK_MS 10 分钟 → 每小时
    ("R251 TICK 周期改为 1 小时",
     "const RANK_TITLE_TICK_MS = 10 * 60 * 1000; // [r249] 排行称号重算周期 = 10 分钟",
     "const RANK_TITLE_TICK_MS = 60 * 60 * 1000; // [r251] 排行称号检查周期 = 每小时（真正结算由日期门保证每北京日一次）"),

    # ⑤ reconcileRankTitles 开头加日期门
    ("R251 reconcile 日期门（开头）",
     "async function reconcileRankTitles(): Promise<void> {\n"
     "  // [r249] 全榜重算：对 RANK_TITLE_SOURCES 每条做「取 #1 → 收回非 #1 → 授予 #1」。整函数自吞异常，绝不阻塞存档链路。\n"
     "  try {\n",
     "async function reconcileRankTitles(): Promise<void> {\n"
     "  // [r249] 全榜重算：对 RANK_TITLE_SOURCES 每条做「取 #1 → 收回非 #1 → 授予 #1」。整函数自吞异常，绝不阻塞存档链路。\n"
     "  try {\n"
     "    // [r251] 日期门：每个北京日只真正结算一次。同北京日重复调用 ⇒ 空转（不产生任何写）；跨天 / 首部署 ⇒ 立即结算。\n"
     "    const today = bjDate(Date.now());\n"
     "    const st = await dbGet('SELECT last_date FROM rank_title_state WHERE id = 1');\n"
     "    if (st && st.last_date === today) return;\n"),

    # ⑥ reconcileRankTitles 结算成功走完后写回 last_date（放最后，抛异常不误标）
    ("R251 reconcile 写回 last_date（末尾）",
     "    }\n"
     "  } catch (e: any) {\n"
     "    console.error('rank title reconcile error:', e?.message || e);\n"
     "  }\n"
     "}\n",
     "    }\n"
     "    // [r251] 结算成功走完 ⇒ 标记今日已结算（放在最后；中途抛异常不写，避免误标已结算）。\n"
     "    await dbRun('UPDATE rank_title_state SET last_date = ? WHERE id = 1', [today]);\n"
     "  } catch (e: any) {\n"
     "    console.error('rank title reconcile error:', e?.message || e);\n"
     "  }\n"
     "}\n"),

    # ⑦ rankHoldersSnapshot out 扩为 7 键（既有 3 键名/语义一字不改，仅追加）
    ("R251 rankHolders 扩 7 键",
     "  const out: Record<string, { name: string; title: string } | null> = { combat: null, stones: null, realm: null };",
     "  const out: Record<string, { name: string; title: string } | null> = { combat: null, stones: null, realm: null, kills: null, achieve: null, playtime: null, fame: null }; // [r251] 扩 7 键"),

    # ⑧ GET /api/leaderboard/me 的 queries 扩为 7 条（既有 3 条一字不改，仅追加；注释同步更正为「七种排序」）
    ("R251 leaderboard/me 扩 7 查询",
     "      // 查询三种排序的排名：必须和 /api/leaderboard 的 ORDER BY 完全一致\n"
     "      const queries = [\n"
     "        { sort: 'realm', config: LEADERBOARD_SORTS.realm },\n"
     "        { sort: 'combat', config: LEADERBOARD_SORTS.combat },\n"
     "        { sort: 'stones', config: LEADERBOARD_SORTS.stones },\n"
     "      ];\n",
     "      // 查询七种排序的排名：必须和 /api/leaderboard 的 ORDER BY 完全一致（aheadCondition / getParams 与 LEADERBOARD_SORTS 逐字同源）\n"
     "      const queries = [\n"
     "        { sort: 'realm', config: LEADERBOARD_SORTS.realm },\n"
     "        { sort: 'combat', config: LEADERBOARD_SORTS.combat },\n"
     "        { sort: 'stones', config: LEADERBOARD_SORTS.stones },\n"
     "        // [r251] 四新榜：与 LEADERBOARD_SORTS 新键同源 ⇒ 响应新增 kills_rank / achieve_rank / playtime_rank / fame_rank\n"
     "        { sort: 'kills', config: LEADERBOARD_SORTS.kills },\n"
     "        { sort: 'achieve', config: LEADERBOARD_SORTS.achieve },\n"
     "        { sort: 'playtime', config: LEADERBOARD_SORTS.playtime },\n"
     "        { sort: 'fame', config: LEADERBOARD_SORTS.fame },\n"
     "      ];\n"),
]

# ============================================================ 前置依赖（只读自证，不改；不符 ⇒ 退出码 2）
REQUIRES = [
    ("const RANK_TITLE_SOURCES: Array<{ source: string; sort: string }> = [", 1, "RANK_TITLE_SOURCES 必须在位（本环追加 4 条）"),
    ("const LEADERBOARD_SORTS: Record<string, { orderBy: string; aheadCondition: string; getParams: (row: any) => any[] }> = {", 1, "LEADERBOARD_SORTS 必须在位（本环追加 4 条）"),
    ("async function grantTitleBySource(userId: number, source: string): Promise<boolean> {", 1, "grantTitleBySource 必须在位（复用授予通道）"),
    ("function shouldGrantRankTitle(topUserId: number, boardSize: number, userId: number, minBoardSize: number = 2): boolean {", 1, "shouldGrantRankTitle 必须在位（minBoardSize=2 语义复用）"),
    ("async function maybeGrantAutoTitles(userId: number, achCount: number): Promise<void> {", 1, "maybeGrantAutoTitles 必须在位（存档汇聚点）"),
    ("async function reconcileRankTitles(): Promise<void> {", 1, "reconcileRankTitles 必须在位（r249 基座）"),
    ("async function rankHoldersSnapshot(): Promise<Record<string, { name: string; title: string } | null>> {", 1, "rankHoldersSnapshot 必须在位（r249 基座）"),
    ("function bjDate(ms: number): string {", 1, "bjDate 必须在位（日期门取今日）"),
    ("function dbGet<T = any>(sql: string, params: any[] = []): Promise<T | undefined> {", 1, "dbGet 必须在位"),
    ("function dbRun(sql: string, params: any[] = []): Promise<{ lastID: number; changes: number }> {", 1, "dbRun 必须在位"),
    # 锚点独占性
    ("  { source: 'rank_stones', sort: 'stones' },\n];\n", 1, "RANK_TITLE_SOURCES 收尾锚点必须唯一"),
    ("  db.run('UPDATE titles SET attr_json = ? WHERE source = ?', ['{\"expRate\":0.15}', 'rank_realm']);    // [r249] 登峰造极 · 境界第一 ⇒ 修为 +15%\n", 1, "称号 seed 区收尾锚点必须唯一"),
    ("      row.spirit_stones, row.realm_index, row.realm_level, row.updated_at, row.user_id,\n    ],\n  },\n};\n", 1, "LEADERBOARD_SORTS 收尾锚点必须唯一"),
    ("const RANK_TITLE_TICK_MS = 10 * 60 * 1000; // [r249] 排行称号重算周期 = 10 分钟", 1, "TICK 锚点必须唯一"),
    ("async function reconcileRankTitles(): Promise<void> {\n  // [r249] 全榜重算：对 RANK_TITLE_SOURCES 每条做「取 #1 → 收回非 #1 → 授予 #1」。整函数自吞异常，绝不阻塞存档链路。\n  try {\n", 1, "reconcile 头部锚点必须唯一"),
    ("    }\n  } catch (e: any) {\n    console.error('rank title reconcile error:', e?.message || e);\n  }\n}\n", 1, "reconcile 尾部锚点必须唯一"),
    ("  const out: Record<string, { name: string; title: string } | null> = { combat: null, stones: null, realm: null };", 1, "rankHolders out 锚点必须唯一"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "res.status(403", "require(", "PRAGMA",
    # 既有 3 榜 orderBy（必须与 /api/leaderboard 逐字同源）——一字不动
    "orderBy: 'realm_index DESC, realm_level DESC, exp DESC, updated_at DESC, user_id ASC'",
    "orderBy: 'combat_power DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC'",
    "orderBy: 'spirit_stones DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC'",
    # 表结构
    "CREATE TABLE IF NOT EXISTS titles (",
    "CREATE TABLE IF NOT EXISTS player_titles (",
    "CREATE TABLE IF NOT EXISTS rankings (",
    # 既有称号 seed 与 attr_json
    "('登峰造极', '{\"expRate\":0.05}', 'rank_realm')",
    "('武林盟主', '{\"atkRate\":0.03}', 'rank_combat')",
    "('富甲一方', '{\"stoneRate\":0.03}', 'rank_stones')",
    "('回归仙人', '{\"expRate\":0.02}', 'return')",
    "('初入江湖', '{\"expRate\":0.01}', 'achievement')",
    # r249 三句 UPDATE
    "['{\"atkRate\":0.15}', 'rank_combat']",
    "['{\"stoneRate\":0.15}', 'rank_stones']",
    "['{\"expRate\":0.15}', 'rank_realm']",
    # 既有符号
    "async function grantTitleBySource(userId: number, source: string): Promise<boolean> {",
    "function shouldGrantRankTitle(topUserId: number, boardSize: number, userId: number, minBoardSize: number = 2): boolean {",
    "const RANK_TITLE_SOURCES: Array<{ source: string; sort: string }> = [",
    "async function maybeGrantAutoTitles(userId: number, achCount: number): Promise<void> {",
    "await reconcileRankTitles(); // [r249]",
    "app.get('/api/leaderboard'",
    "app.get('/api/leaderboard/me'",
    "app.get('/api/quest/summary'",
]


def fail(msg, code=1):
    print("[FAIL] " + msg)
    sys.exit(code)


# ============================================================ Node 语法门禁
def node_bin():
    root = r"C:/Users/<USER>/.workbuddy-ai/binaries/node/versions"
    cands = []
    if os.path.isdir(root):
        cands = sorted(os.path.join(root, d, "node.exe") for d in os.listdir(root))
        cands = [c for c in cands if os.path.isfile(c)]
    return os.environ.get("YL_NODE") or (cands[-1] if cands else "node")


def node_syntax_check(text):
    """产物必须过 node --experimental-strip-types --check。"""
    d = tempfile.mkdtemp(prefix="r251chk-")
    try:
        p = os.path.join(d, "c.ts")
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        r = subprocess.run([node_bin(), "--experimental-strip-types", "--check", p],
                           capture_output=True, text=True, encoding="utf-8")
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ============================================================ sqlite3 语义真跑
# 用内存库 + 合成 rankings/player_titles/saves/rank_title_state 行，跑与注入 TS **逐字同源**的 SQL 决策逻辑。
def semantic_harness():
    results = []

    def ck(name, fn):
        try:
            ok = bool(fn())
            results.append((name, ok, ""))
        except Exception as e:
            results.append((name, False, "throw:" + repr(e)))

    TITLES = [
        (1, "登峰造极", "rank_realm"), (2, "武林盟主", "rank_combat"), (3, "富甲一方", "rank_stones"),
        (4, "万人敌", "rank_kills"), (5, "功成名就", "rank_achieve"),
        (6, "苦修不辍", "rank_playtime"), (7, "德高望重", "rank_fame"),
    ]
    TID = {src: tid for tid, _n, src in TITLES}
    SORT_SRC = {sort: src for src, sort in RANK_SOURCES}

    def fresh():
        con = sqlite3.connect(":memory:")
        con.executescript(
            "CREATE TABLE rankings (user_id INTEGER PRIMARY KEY, name TEXT,"
            " realm_index INT DEFAULT 0, realm_level INT DEFAULT 1, exp INT DEFAULT 0,"
            " combat_power INT DEFAULT 0, spirit_stones INT DEFAULT 0,"
            " kill_count INT DEFAULT 0, achievement_count INT DEFAULT 0,"
            " play_time INT DEFAULT 0, reputation INT DEFAULT 0, updated_at TEXT);"
            "CREATE TABLE titles (id INTEGER PRIMARY KEY, name TEXT, source TEXT);"
            "CREATE TABLE player_titles (user_id INT, title_id INT, PRIMARY KEY(user_id,title_id));"
            "CREATE TABLE saves (user_id INTEGER PRIMARY KEY, title_id INT);"
            "CREATE TABLE rank_title_state (id INTEGER PRIMARY KEY CHECK (id = 1), last_date TEXT NOT NULL DEFAULT '');"
        )
        for tid, n, src in TITLES:
            con.execute("INSERT INTO titles (id,name,source) VALUES (?,?,?)", [tid, n, src])
        con.execute(SQL_STATE_SEED)
        con.commit()
        return con

    def reconcile_all(con, today):
        """镜像注入 TS reconcileRankTitles（含日期门）：返回 'settle' | 'skip'。"""
        st = con.execute(SQL_STATE_SEL).fetchone()
        if st and st[0] == today:
            return "skip"
        for source, sort in RANK_SOURCES:
            tid = TID[source]
            orderBy = ORDERBY[sort]
            top = con.execute(SQL_TOP + " " + orderBy + " LIMIT 1").fetchone()
            cnt = con.execute(SQL_COUNT).fetchone()[0]
            topId = top[0] if top else None
            valid = (topId is not None) and (cnt >= MIN_BOARD_SIZE)  # shouldGrantRankTitle(topId,cnt,topId)
            if not valid:
                con.execute(SQL_DELETE_ALL, [tid])
                con.execute(SQL_CLEAR_EQUIP_ALL, [tid])
            else:
                con.execute(SQL_DELETE_OTHERS, [tid, topId])
                con.execute(SQL_CLEAR_EQUIP_OTHERS, [tid, topId])
                con.execute(SQL_INSERT_OR_IGNORE, [topId, tid])
        con.execute(SQL_STATE_UPD, [today])
        con.commit()
        return "settle"

    def snapshot(con):
        """镜像注入 TS rankHoldersSnapshot：7 键，无主 ⇒ None。"""
        out = {sort: None for _s, sort in RANK_SOURCES}
        for source, sort in RANK_SOURCES:
            top = con.execute(SQL_TOP.replace("user_id", "user_id, name") + " " + ORDERBY[sort] + " LIMIT 1").fetchone()
            cnt = con.execute(SQL_COUNT).fetchone()[0]
            t = con.execute("SELECT name FROM titles WHERE source = ?", [source]).fetchone()
            topId = top[0] if top else None
            if top and t and topId is not None and (cnt >= MIN_BOARD_SIZE):
                out[sort] = {"name": top[1] or "", "title": t[0] or ""}
        return out

    def holders(con, tid):
        return sorted(r[0] for r in con.execute("SELECT user_id FROM player_titles WHERE title_id=?", [tid]).fetchall())

    def last_date(con):
        return con.execute(SQL_STATE_SEL).fetchone()[0]

    # ── /api/leaderboard/me 名次真跑：镜像注入 TS 的 aheadCondition + getParams（与 ORDER BY 逐字同源） ──
    ROWIDX = {"user_id": 0, "name": 1, "realm_index": 2, "realm_level": 3, "exp": 4, "combat_power": 5,
              "spirit_stones": 6, "kill_count": 7, "achievement_count": 8, "play_time": 9,
              "reputation": 10, "updated_at": 11}
    PRIMARY = {"realm": "realm_index", "combat": "combat_power", "stones": "spirit_stones",
               "kills": "kill_count", "achieve": "achievement_count", "playtime": "play_time", "fame": "reputation"}
    ORDER_COLS = {}
    for _s in PRIMARY:
        if _s == "realm":
            ORDER_COLS[_s] = [("realm_index", 1), ("realm_level", 1), ("exp", 1), ("updated_at", 1), ("user_id", 0)]
        else:
            ORDER_COLS[_s] = [(PRIMARY[_s], 1), ("realm_index", 1), ("realm_level", 1), ("updated_at", 1), ("user_id", 0)]

    def ahead_sql(sort):
        col = PRIMARY[sort]
        if sort == "realm":
            return ("(realm_index > ?) OR (realm_index = ? AND realm_level > ?) "
                    "OR (realm_index = ? AND realm_level = ? AND exp > ?) "
                    "OR (realm_index = ? AND realm_level = ? AND exp = ? AND updated_at > ?) "
                    "OR (realm_index = ? AND realm_level = ? AND exp = ? AND updated_at = ? AND user_id < ?)")
        return ("(%s > ?) OR (%s = ? AND realm_index > ?) OR (%s = ? AND realm_index = ? AND realm_level > ?) "
                "OR (%s = ? AND realm_index = ? AND realm_level = ? AND updated_at > ?) "
                "OR (%s = ? AND realm_index = ? AND realm_level = ? AND updated_at = ? AND user_id < ?)"
                % (col, col, col, col, col))

    def ahead_params(sort, row):
        uid, ri, rl, exp, ua = row[0], row[2], row[3], row[4], row[11]
        if sort == "realm":
            return [ri, ri, rl, ri, rl, exp, ri, rl, exp, ua, ri, rl, exp, ua, uid]
        c = row[ROWIDX[PRIMARY[sort]]]
        return [c, c, ri, c, ri, rl, c, ri, rl, ua, c, ri, rl, ua, uid]

    def me_rank(con, sort, row):
        n = con.execute("SELECT COUNT(*) AS cnt FROM rankings WHERE " + ahead_sql(sort), ahead_params(sort, row)).fetchone()[0]
        return n + 1

    def gt_rank(allrows, uid, sort):
        def cmpf(a, b):
            for col, desc in ORDER_COLS[sort]:
                va, vb = a[ROWIDX[col]], b[ROWIDX[col]]
                if va != vb:
                    if desc:
                        return -1 if va > vb else 1
                    return -1 if va < vb else 1
            return 0
        ordered = sorted(allrows, key=functools.cmp_to_key(cmpf))
        for i, r in enumerate(ordered):
            if r[0] == uid:
                return i + 1
        return -1

    # ① 日期门：同日第二次空转（last_date 未变 + player_titles 未变）；改昨天 ⇒ 真正结算
    def s1():
        con = fresh()
        con.execute("INSERT INTO rankings (user_id,name,combat_power) VALUES (1,'甲',100)")
        con.execute("INSERT INTO rankings (user_id,name,combat_power) VALUES (2,'乙',50)")
        con.commit()
        r1 = reconcile_all(con, "2026-10-11")
        d1 = last_date(con)
        before = sorted(con.execute("SELECT user_id,title_id FROM player_titles").fetchall())
        # 同日第二次：即使榜面已变（乙反超），也必须空转 ⇒ 不产生任何写
        con.execute("UPDATE rankings SET combat_power=999 WHERE user_id=2")
        con.commit()
        r2 = reconcile_all(con, "2026-10-11")
        after = sorted(con.execute("SELECT user_id,title_id FROM player_titles").fetchall())
        d2 = last_date(con)
        skip_noop = (r1 == "settle") and (r2 == "skip") and (d1 == "2026-10-11") and (d2 == "2026-10-11") and (before == after)
        # 改 last_date=昨天 ⇒ 再调 ⇒ 真正结算且 last_date 更新为今天
        con.execute(SQL_STATE_UPD, ["2026-10-10"])
        con.commit()
        r3 = reconcile_all(con, "2026-10-11")
        d3 = last_date(con)
        return skip_noop and r3 == "settle" and d3 == "2026-10-11"

    # ② kills 榜 A 第一 ⇒ A 持万人敌；B 反超 ⇒ A 失/B 得/恰 1 行
    def s2():
        con = fresh()
        con.execute("INSERT INTO rankings (user_id,name,kill_count) VALUES (1,'甲',10)")
        con.execute("INSERT INTO rankings (user_id,name,kill_count) VALUES (2,'乙',5)")
        con.commit()
        reconcile_all(con, "D1")
        ok1 = holders(con, TID["rank_kills"]) == [1]
        con.execute("UPDATE rankings SET kill_count=100 WHERE user_id=2")
        con.commit()
        reconcile_all(con, "D2")
        h = holders(con, TID["rank_kills"])
        return ok1 and h == [2] and len(h) == 1

    # ③ 7 榜互不干扰：每榜各自 #1；只改 kills 榜 ⇒ 其余 6 榜持有者不变
    def s3():
        con = fresh()
        rows = [
            # uid,name, realm_index, realm_level, exp, combat, stones, kills, ach, playtime, rep
            (1, "u1", 9, 9, 900, 10, 10, 10, 10, 10, 10),
            (2, "u2", 5, 5, 500, 20, 20, 20, 20, 20, 20),
            (3, "u3", 3, 3, 300, 30, 30, 30, 30, 30, 30),
            (4, "u4", 1, 1, 100, 40, 40, 40, 40, 40, 40),
            (5, "u5", 7, 7, 700, 50, 50, 50, 50, 50, 50),
            (6, "u6", 2, 2, 200, 60, 60, 60, 60, 60, 60),
            (7, "u7", 4, 4, 400, 70, 70, 70, 70, 70, 70),
        ]
        for r in rows:
            con.execute("INSERT INTO rankings (user_id,name,realm_index,realm_level,exp,combat_power,spirit_stones,kill_count,achievement_count,play_time,reputation) VALUES (?,?,?,?,?,?,?,?,?,?,?)", list(r))
        con.commit()
        reconcile_all(con, "D1")
        base = {sort: holders(con, TID[src]) for src, sort in RANK_SOURCES}
        # 只改 kills 榜：让 uid=7 的 kill_count 飙升为榜首
        con.execute("UPDATE rankings SET kill_count=999 WHERE user_id=7")
        con.commit()
        reconcile_all(con, "D2")
        now = {sort: holders(con, TID[src]) for src, sort in RANK_SOURCES}
        # kills 榜变了（7 成为唯一持有者），其余 6 榜原样
        kills_ok = now["kills"] == [7]
        others_ok = all(now[s] == base[s] for s in ["realm", "combat", "stones", "achieve", "playtime", "fame"])
        return kills_ok and others_ok

    # ④ rankHoldersSnapshot 返回 7 键；空表 ⇒ 无主 null；有数据 ⇒ 各榜 #1 的 {name,title}
    def s4():
        # 空表：7 键齐备且全 None（榜上 < minBoardSize ⇒ 无主）
        con0 = fresh()
        snap0 = snapshot(con0)
        keys0_ok = set(snap0.keys()) == {"realm", "combat", "stones", "kills", "achieve", "playtime", "fame"} and len(snap0) == 7
        empty_null_ok = all(v is None for v in snap0.values())
        # 2 人：7 榜同源 ⇒ 各榜均有合法 #1（非 None）；realm 榜首应为 uid=1 甲
        con = fresh()
        con.execute("INSERT INTO rankings (user_id,name,realm_index,realm_level,exp) VALUES (1,'甲',9,9,900)")
        con.execute("INSERT INTO rankings (user_id,name,realm_index,realm_level,exp) VALUES (2,'乙',1,1,100)")
        con.commit()
        snap = snapshot(con)
        keys_ok = set(snap.keys()) == {"realm", "combat", "stones", "kills", "achieve", "playtime", "fame"} and len(snap) == 7
        all_owned = all(isinstance(v, dict) and set(v.keys()) == {"name", "title"} for v in snap.values())
        realm_ok = snap["realm"] == {"name": "甲", "title": "登峰造极"}
        return keys0_ok and empty_null_ok and keys_ok and all_owned and realm_ok

    # ⑤ /api/leaderboard/me：7 条查询（aheadCondition+getParams）各自算出的名次 == ORDER BY 真值名次
    def s5():
        con = fresh()
        rows = [
            (1, "u1", 9, 9, 900, 10, 10, 10, 10, 10, 10, "t1"),
            (2, "u2", 8, 8, 800, 20, 20, 20, 20, 20, 20, "t2"),
            (3, "u3", 7, 7, 700, 30, 30, 30, 30, 30, 30, "t3"),
            (4, "u4", 6, 6, 600, 40, 40, 40, 40, 40, 40, "t4"),
            (5, "u5", 5, 5, 500, 50, 50, 50, 50, 50, 50, "t5"),
            (6, "u6", 4, 4, 400, 60, 60, 60, 60, 60, 60, "t6"),
            (7, "u7", 3, 3, 300, 70, 70, 70, 70, 70, 70, "t7"),
        ]
        for r in rows:
            con.execute(
                "INSERT INTO rankings (user_id,name,realm_index,realm_level,exp,combat_power,spirit_stones,"
                "kill_count,achievement_count,play_time,reputation,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", list(r))
        con.commit()
        allrows = con.execute("SELECT * FROM rankings").fetchall()
        # 7 榜 × 3 个目标用户，SQL 名次必须与 ORDER BY 真值名次逐一相等
        for target in (1, 4, 7):
            trow = con.execute("SELECT * FROM rankings WHERE user_id=?", [target]).fetchone()
            for _src, sort in RANK_SOURCES:
                if me_rank(con, sort, trow) != gt_rank(allrows, target, sort):
                    return False
        # 榜首先后自证：realm 榜首 = uid1、其余 6 榜榜首 = uid7
        if me_rank(con, "realm", con.execute("SELECT * FROM rankings WHERE user_id=1").fetchone()) != 1:
            return False
        for _src, sort in RANK_SOURCES:
            if sort == "realm":
                continue
            if me_rank(con, sort, con.execute("SELECT * FROM rankings WHERE user_id=7").fetchone()) != 1:
                return False
        return True

    ck("① 日期门：同日二次空转 / 改昨天再结算", s1)
    ck("② kills 榜 A#1 ⇒ A 持万人敌；B 反超 ⇒ 恰 1 行归 B", s2)
    ck("③ 7 榜互不干扰（只改 kills ⇒ 其余 6 榜不变）", s3)
    ck("④ rankHoldersSnapshot 返回 7 键 / 无主 null", s4)
    ck("⑤ /me 7 查询名次 == ORDER BY 真值名次", s5)

    total = len(results)
    nfail = sum(1 for _, ok, _ in results if not ok)
    for name, ok, extra in results:
        print(("  [OK] " if ok else "  [FAIL] ") + name + (("  <" + extra + ">") if extra else ""))
    print("HARNESS_RESULT " + json.dumps({"total": total, "fail": nfail}))
    return total, nfail


def main() -> None:
    ap = argparse.ArgumentParser(description="R-250 服务端环（服务端第 95 环）")
    ap.add_argument("--src", default=SRC, help="待打补丁的服务端源码（装配器会传私有副本）")
    ap.add_argument("--check", action="store_true", help="只校验不写回")
    ap.add_argument("--selftest", action="store_true", help="只校验不写回（含 Node 语法 + sqlite3 语义真跑）")
    ap.add_argument("--reverse", default=None, metavar="PATH",
                    help="反向对照：在未打 r251 的服务端上跑同一套断言，必须确认标记缺席（只校验不写回）")
    a = ap.parse_args()

    # ---- 反向对照模式 ----
    if a.reverse:
        path = a.reverse
        if not os.path.exists(path):
            fail("reverse source not found: " + path)
        with io.open(path, "r", encoding="utf-8", newline="") as f:
            rev = f.read()
        print("== 反向对照（未打 r251 的服务端）：%s ==" % path)
        has_tbl = rev.count("rank_title_state")
        has_mark = rev.count(MARK)
        print("  rank_title_state 计数 = %d（期望 0，证明未打）" % has_tbl)
        print("  [r251] 计数 = %d（期望 0）" % has_mark)
        if has_tbl == 0 and has_mark == 0:
            print("  [REVERSE] PASS（基线确实未打 r251，标记缺席）")
        else:
            print("  [REVERSE] FAIL（★ 该源已含 r251 痕迹，不构成基线）")
        return

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等（幂等 ⇒ 退出码 3，由调用方区分「已打」与「失败」）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        sys.exit(3)

    # 2) 依赖（不符 ⇒ 退出码 2）
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:90], n, cnt, why), 2)

    # 3) 锚点计数（不符 ⇒ 退出码 2）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]), 2)
        if old == new:
            fail("%s old == new" % name, 2)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}
    base_interval = src.count("setInterval(")
    # SQL 同源基线（harness 测的就是产物里的 SQL）：既有 SQL 计数打后必须不变。
    base_sql_delete_all = src.count(SQL_DELETE_ALL)
    base_sql_count = src.count(SQL_COUNT)
    base_sql_title_id = src.count(SQL_TITLE_ID)
    base_sql_ignore = src.count(SQL_INSERT_OR_IGNORE)
    base_today = src.count("const today = bjDate(Date.now());")  # 基座已有多处同名局部量 ⇒ 只断言 +1

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    mark_n = sum(new.count(MARK) for _, _, new in EDITS)
    gates = [
        ("R251 幂等标记就位", MARK, mark_n),
        # ① 新表 + seed
        ("① 新表 DDL", SQL_STATE_DDL, 1),
        ("① 新表单行 seed", SQL_STATE_SEED, 1),
        ("① 新表列 id/last_date", "last_date TEXT NOT NULL DEFAULT ''", 1),
        ("① CHECK(id=1)", "CHECK (id = 1)", 1),
        # ② 4 新榜
        ("② sort kills orderBy", "orderBy: 'kill_count DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC',", 1),
        ("② sort achieve orderBy", "orderBy: 'achievement_count DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC',", 1),
        ("② sort playtime orderBy", "orderBy: 'play_time DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC',", 1),
        ("② sort fame orderBy", "orderBy: 'reputation DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC',", 1),
        ("② 新榜 aheadCondition 齐备", "(kill_count > ?)", 1),
        ("② 新榜 getParams 齐备", "row.kill_count, row.realm_index, row.realm_level, row.updated_at, row.user_id,", 1),
        # ③ RANK_TITLE_SOURCES
        ("③ sources kills", "{ source: 'rank_kills', sort: 'kills' },", 1),
        ("③ sources achieve", "{ source: 'rank_achieve', sort: 'achieve' },", 1),
        ("③ sources playtime", "{ source: 'rank_playtime', sort: 'playtime' },", 1),
        ("③ sources fame", "{ source: 'rank_fame', sort: 'fame' },", 1),
        # ④ TICK
        ("④ TICK 60 分钟", "const RANK_TITLE_TICK_MS = 60 * 60 * 1000;", 1),
        ("④ 旧 TICK 10 分钟已清零", "const RANK_TITLE_TICK_MS = 10 * 60 * 1000;", 0),
        # ⑤ 日期门
        ("⑤ 日期门 取今日", "const today = bjDate(Date.now());", base_today + 1),
        ("⑤ 日期门 读 last_date", SQL_STATE_SEL, 1),
        ("⑤ 日期门 空转 return", "if (st && st.last_date === today) return;", 1),
        ("⑤ 写回 last_date", SQL_STATE_UPD, 1),
        # ⑥ seed
        ("⑥ seed 万人敌", "'万人敌', '{\"atkRate\":0.10}', 'rank_kills'", 1),
        ("⑥ seed 功成名就", "'功成名就', '{\"expRate\":0.10}', 'rank_achieve'", 1),
        ("⑥ seed 苦修不辍", "'苦修不辍', '{\"defRate\":0.10}', 'rank_playtime'", 1),
        ("⑥ seed 德高望重", "'德高望重', '{\"stoneRate\":0.10}', 'rank_fame'", 1),
        # ⑦ rankHolders 7 键
        ("⑦ rankHolders 7 键 init", "{ combat: null, stones: null, realm: null, kills: null, achieve: null, playtime: null, fame: null }", 1),
        # ⑧ /api/leaderboard/me 扩 7 查询 + 注释更正
        ("⑧ /me 追加 kills 查询", "{ sort: 'kills', config: LEADERBOARD_SORTS.kills },", 1),
        ("⑧ /me 追加 achieve 查询", "{ sort: 'achieve', config: LEADERBOARD_SORTS.achieve },", 1),
        ("⑧ /me 追加 playtime 查询", "{ sort: 'playtime', config: LEADERBOARD_SORTS.playtime },", 1),
        ("⑧ /me 追加 fame 查询", "{ sort: 'fame', config: LEADERBOARD_SORTS.fame },", 1),
        ("⑧ /me 旧三查询保留", "{ sort: 'stones', config: LEADERBOARD_SORTS.stones },", 1),
        ("⑧ /me 注释更新为七种", "// 查询七种排序的排名", 1),
        ("⑧ /me 旧注释已清零", "// 查询三种排序的排名", 0),
        # SQL 同源门禁（harness 测的就是产物里的 SQL）：既有 SQL 计数打后不变
        ("SQL 同源 SQL_DELETE_ALL", SQL_DELETE_ALL, base_sql_delete_all),
        ("SQL 同源 SQL_INSERT_OR_IGNORE", SQL_INSERT_OR_IGNORE, base_sql_ignore),
        ("SQL 同源 SQL_COUNT", SQL_COUNT, base_sql_count),
        ("SQL 同源 SQL_TITLE_ID", SQL_TITLE_ID, base_sql_title_id),
    ]
    # 冻结：既有符号/表结构/orderBy/seed 一字不动
    for needle in BASE_NEEDLES:
        gates.append(("冻结 " + needle[:44].replace("\n", " "), needle, base[needle]))
    # setInterval 不变（本环不加定时器）
    gates.append(("红线 setInterval 不变", "setInterval(", base_interval))
    # 红线：不新增 res.status(403) / PRAGMA / require(
    gates.append(("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]))
    gates.append(("红线 未新增 PRAGMA", "PRAGMA", base["PRAGMA"]))
    gates.append(("红线 未新增 require(", "require(", base["require("]))

    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        if not good:
            print("  [FAIL] %-56s actual=%d expect==%d" % (label, act, exp))
    print("  [%s] 门禁 %d 条" % ("OK" if ok else "FAIL", len(gates)))

    # 7) round-trip 自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    # 8) node --check 语法门禁
    syn_ok, syn_msg = node_syntax_check(out)
    if not syn_ok:
        sys.stdout.write(syn_msg)
    print("  [%s] node --experimental-strip-types --check" % ("OK" if syn_ok else "FAIL"))
    ok = ok and syn_ok

    # 9) sqlite3 语义真跑
    total, nfail = semantic_harness()
    sem_ok = (nfail == 0)
    print("  [%s] sqlite3 语义真跑  (total=%d fail=%d)" % ("OK" if sem_ok else "FAIL", total, nfail))
    ok = ok and sem_ok

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if not ok:
        fail("门禁未全绿，未写回", 1)

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 10) 改前 .bak + 原子写回
    bak = "%s.bak-r251-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r251-", suffix=".tmp")
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
