# -*- coding: utf-8 -*-
r"""
srv_patch_r249.py -- R-249 排行称号轮换（服务端第 94 环 / 新末环）

唯一真相源：策划_仙务称号体系重做_20261011.md（§4 轮换机制 / §5.1 服务端接口冻结 / §7 工单边界）。
本文件只按该规格实现，任何偏离必须先改那份规格文件。

背景（现状 = 半成品，两头断链）
--------------------------------------------------------------------------
  · `titles` 目录 + `player_titles`（持有）+ `saves.title_id`（佩戴）三件套已在位；
  · `maybeGrantAutoTitles()` + `RANK_TITLE_SOURCES`（三榜）只**授**不**收回**（全文件无 DELETE FROM player_titles）；
  · 排行称号加成偏低（1%~5%），且 seed 用 INSERT OR IGNORE ⇒ 改数值不生效；
  · `GET /api/quest/summary` 无「各榜当前持有者」信息。
  ⇒ 本环补齐「动态轮换 + 加成上调 + 端点字段」三件事。

机制（逐条，全部 expect=1）
--------------------------------------------------------------------------
  ① 新函数 `reconcileRankTitles()`（模块作用域，紧邻 maybeGrantAutoTitles）：
     对 RANK_TITLE_SOURCES 每条：取该榜 #1（用 LEADERBOARD_SORTS[sort].orderBy，与
     /api/leaderboard 逐字同源）+ 总人数 cnt ⇒
       · 收回：`DELETE ... title_id = ? AND user_id != ?`（#1 以外全收回）；
         榜空 / cnt < minBoardSize(=2) ⇒ 该称号**全表收回**；
       · 授予：合法 #1 ⇒ 复用 `grantTitleBySource`（INSERT OR IGNORE）；
       · ★ 佩戴清理：被收回者若正佩戴（saves.title_id 指向它）⇒ 同步置空。
     整函数 try/catch **自吞异常**，绝不阻塞存档链路。
  ② 定时器：`RANK_TITLE_TICK_MS = 10 * 60 * 1000` + `rankTitleEngineOn` + `rankTitleSettling`
     + setInterval（首行早退 + 重入锁 + try/catch），照 [arenaweek] 既有写法，注释标 [ranktitle]。
  ③ 加成上调（幂等迁移）：三句 `UPDATE titles SET attr_json = ? WHERE source = ?`
     （rank_combat→atkRate .15 / rank_stones→stoneRate .15 / rank_realm→expRate .15）。
     ★ 必须用 UPDATE —— 既有 seed 是 INSERT OR IGNORE，改不动已存在的行。
  ④ 端点增强：GET /api/quest/summary 响应**追加** rankHolders（不改任何既有键）：
     { combat:{name,title}|null, stones:{name,title}|null, realm:{name,title}|null }。
  ⑤ maybeGrantAutoTitles() 的「授」逻辑改为调用 reconcileRankTitles()（存档汇聚点不变）。

设计取向
--------------------------------------------------------------------------
  · 冻结 `LEADERBOARD_SORTS` 的 orderBy（必须与 /api/leaderboard 逐字同源）、rankings/titles/
    player_titles 表结构、其它任何 API —— 一律不改。
  · 复用（不改名、不改语义）：RANK_TITLE_SOURCES / LEADERBOARD_SORTS / grantTitleBySource /
    shouldGrantRankTitle / dbGet / dbRun / attr_json 键名（atkRate/stoneRate/expRate/charmRate）。
  · rankHolders 快照内部自吞异常 ⇒ 端点恒返回对象（不会因快照失败而 500）。

CLI 契约（照 srv_patch_r233.py）
--------------------------------------------------------------------------
  `--src <path>`：就地原子写回该路径（写回前落 `<src>.bak-r249-<时间戳>`）。
  `--check` / `--selftest`：只校验不写回（含 Node 语法门禁 + sqlite3 语义真跑）。
  `--reverse <path>`：反向对照——在**未打 r249 的服务端**上跑同一套断言，必须确认标记缺席。
  退出码：0=成功 / 3=幂等（产物已含 [r249]）/ 2=锚点不符 / 1=门禁失败。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `PRAGMA`。
  · 只改服务端；不改客户端 bundle；不改任何既有 srv_patch_*.py / chain_build.py / deploy_*/。
  · 每处替换 expect=1，命中数不符即中止（退出码 2）；产物 round-trip 自证 + Node 语法门禁
    + sqlite3 语义真跑后原子写回。
"""

import argparse
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

MARK = "[r249]"

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

# LEADERBOARD_SORTS 三条 orderBy 的**逐字镜像**（冻结基线；harness 取 #1 用）。
ORDERBY = {
    "realm": "realm_index DESC, realm_level DESC, exp DESC, updated_at DESC, user_id ASC",
    "combat": "combat_power DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC",
    "stones": "spirit_stones DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC",
}
# RANK_TITLE_SOURCES 的**逐字镜像**（source ↔ sort）。
RANK_SOURCES = [("rank_realm", "realm"), ("rank_combat", "combat"), ("rank_stones", "stones")]
MIN_BOARD_SIZE = 2

# ============================================================ 改动点（全部 expect=1）
EDITS = [
    # ① 新函数 reconcileRankTitles + 常量 + 定时器 + rankHoldersSnapshot
    #    （插在 RANK_TITLE_SOURCES 定义之后、maybeGrantAutoTitles 之前）
    ("R249 新增 reconcileRankTitles + 定时器 + 快照",
     "  { source: 'rank_stones', sort: 'stones' },\n];\n",
     "  { source: 'rank_stones', sort: 'stones' },\n];\n"
     "// ─────────────────────────────────────────────────────────\n"
     "// [r249] R-249 排行称号轮换（服务端第 94 环 / 新末环）\n"
     "//   · 三榜（战力/灵石/境界）#1 动态持有对应称号；被超越即收回（DELETE），非榜首一律不持有。\n"
     "//   · 触发：① setInterval 每 RANK_TITLE_TICK_MS 全榜重算；② 存档惰性汇聚点 maybeGrantAutoTitles 复用本函数。\n"
     "//   · 榜上 < minBoardSize(=2) 人 ⇒ 视为无主 ⇒ 该称号全表收回（沿用 shouldGrantRankTitle 语义）。\n"
     "//   · 被收回者若正佩戴（saves.title_id 指向该称号）⇒ 同步置空，杜绝「未持有却佩戴中」。\n"
     "// ─────────────────────────────────────────────────────────\n"
     "const RANK_TITLE_TICK_MS = 10 * 60 * 1000; // [r249] 排行称号重算周期 = 10 分钟\n"
     "let rankTitleEngineOn = true;   // [r249] 引擎开关（关 ⇒ tick 首行早退，零 DB 操作）\n"
     "let rankTitleSettling = false;  // [r249] 重入锁（上一轮未结束则跳过本轮）\n"
     "async function reconcileRankTitles(): Promise<void> {\n"
     "  // [r249] 全榜重算：对 RANK_TITLE_SOURCES 每条做「取 #1 → 收回非 #1 → 授予 #1」。整函数自吞异常，绝不阻塞存档链路。\n"
     "  try {\n"
     "    for (const { source, sort } of RANK_TITLE_SOURCES) {\n"
     "      const cfg = LEADERBOARD_SORTS[sort];\n"
     "      const [top, cnt, t] = await Promise.all([\n"
     "        dbGet(`SELECT user_id FROM rankings ORDER BY ${cfg.orderBy} LIMIT 1`),\n"
     "        dbGet('SELECT COUNT(*) AS c FROM rankings'),\n"
     "        dbGet('SELECT id FROM titles WHERE source = ?', [source]),\n"
     "      ]);\n"
     "      if (!t) continue;\n"
     "      const titleId = Number(t.id);\n"
     "      const boardSize = Number(cnt && cnt.c) || 0;\n"
     "      const topId = top ? Number(top.user_id) : null;\n"
     "      // 合法榜首：存在且榜上 ≥ minBoardSize（复用 shouldGrantRankTitle，与授予判定同源）\n"
     "      const validTop = topId != null && shouldGrantRankTitle(topId, boardSize, topId);\n"
     "      if (!validTop) {\n"
     "        // 无主（榜空 / 人数不足）⇒ 该称号全表收回 + 佩戴清理\n"
     "        await dbRun('DELETE FROM player_titles WHERE title_id = ?', [titleId]);\n"
     "        await dbRun('UPDATE saves SET title_id = NULL WHERE title_id = ?', [titleId]);\n"
     "      } else {\n"
     "        // 收回 #1 以外全部 + 清理被收回者的佩戴\n"
     "        await dbRun('DELETE FROM player_titles WHERE title_id = ? AND user_id != ?', [titleId, topId]);\n"
     "        await dbRun('UPDATE saves SET title_id = NULL WHERE title_id = ? AND user_id != ?', [titleId, topId]);\n"
     "        // 授予 #1（INSERT OR IGNORE，复用既有授予通道）\n"
     "        await grantTitleBySource(topId as number, source);\n"
     "      }\n"
     "    }\n"
     "  } catch (e: any) {\n"
     "    console.error('rank title reconcile error:', e?.message || e);\n"
     "  }\n"
     "}\n"
     "// [r249] rankHolders 快照：三榜 #1 的 {name(rankings.name), title(称号名)}；无主 ⇒ null。内部自吞异常恒返回对象。\n"
     "async function rankHoldersSnapshot(): Promise<Record<string, { name: string; title: string } | null>> {\n"
     "  const out: Record<string, { name: string; title: string } | null> = { combat: null, stones: null, realm: null };\n"
     "  try {\n"
     "    for (const { source, sort } of RANK_TITLE_SOURCES) {\n"
     "      const cfg = LEADERBOARD_SORTS[sort];\n"
     "      const [top, cnt, t] = await Promise.all([\n"
     "        dbGet(`SELECT user_id, name FROM rankings ORDER BY ${cfg.orderBy} LIMIT 1`),\n"
     "        dbGet('SELECT COUNT(*) AS c FROM rankings'),\n"
     "        dbGet('SELECT name FROM titles WHERE source = ?', [source]),\n"
     "      ]);\n"
     "      const boardSize = Number(cnt && cnt.c) || 0;\n"
     "      const topId = top ? Number(top.user_id) : null;\n"
     "      if (top && t && topId != null && shouldGrantRankTitle(topId, boardSize, topId)) {\n"
     "        out[sort] = { name: String(top.name || ''), title: String(t.name || '') };\n"
     "      }\n"
     "    }\n"
     "  } catch (e: any) {\n"
     "    console.error('rank holders snapshot error:', e?.message || e);\n"
     "  }\n"
     "  return out;\n"
     "}\n"
     "setInterval(() => {\n"
     "  // [ranktitle] 排行称号轮换 tick：与活动引擎无关，只看 rankTitleEngineOn（首行早退 ⇒ 引擎关闭零 DB 操作）\n"
     "  if (!rankTitleEngineOn) return;\n"
     "  if (rankTitleSettling) return; // 重入锁：上一轮未结束则跳过本轮\n"
     "  rankTitleSettling = true;\n"
     "  try {\n"
     "    reconcileRankTitles()\n"
     "      .catch((e: any) => console.error('rank title tick error:', e?.message || e))\n"
     "      .finally(() => { rankTitleSettling = false; });\n"
     "  } catch (e: any) {\n"
     "    rankTitleSettling = false;\n"
     "    console.error('rank title tick error:', e?.message || e);\n"
     "  }\n"
     "}, RANK_TITLE_TICK_MS).unref();\n"),

    # ② maybeGrantAutoTitles 的「授」逻辑替换为调用 reconcileRankTitles（存档汇聚点不变）
    ("R249 maybeGrant 复用 reconcile",
     "async function maybeGrantAutoTitles(userId: number, achCount: number): Promise<void> {\n"
     "  try {\n"
     "    if (shouldGrantAchievementTitle(achCount)) await grantTitleBySource(userId, 'achievement');\n"
     "    for (const { source, sort } of RANK_TITLE_SOURCES) {\n"
     "      const cfg = LEADERBOARD_SORTS[sort];\n"
     "      const [top, cnt] = await Promise.all([\n"
     "        dbGet(`SELECT user_id FROM rankings ORDER BY ${cfg.orderBy} LIMIT 1`),\n"
     "        dbGet('SELECT COUNT(*) AS c FROM rankings'),\n"
     "      ]);\n"
     "      if (top && cnt && shouldGrantRankTitle(Number(top.user_id), Number(cnt.c), userId)) {\n"
     "        await grantTitleBySource(userId, source);\n"
     "      }\n"
     "    }\n"
     "  } catch (e: any) {\n"
     "    console.error('auto title grant error:', e?.message || e);\n"
     "  }\n"
     "}",
     "async function maybeGrantAutoTitles(userId: number, achCount: number): Promise<void> {\n"
     "  try {\n"
     "    if (shouldGrantAchievementTitle(achCount)) await grantTitleBySource(userId, 'achievement');\n"
     "    // ★ R-249（[r249]）：排行称号的「授」改为**全榜重算**（收回+授予），不再只对本玩家惰性授予。\n"
     "    //   存档汇聚点不变（POST /api/save 与 updatePlayerSave 仍调本函数）；内部自吞异常不阻塞存档链路。\n"
     "    await reconcileRankTitles(); // [r249]\n"
     "  } catch (e: any) {\n"
     "    console.error('auto title grant error:', e?.message || e);\n"
     "  }\n"
     "}"),

    # ③ 排行称号加成上调（UPDATE 幂等迁移）
    ("R249 attr 上调 UPDATE 迁移",
     "    ('初入江湖', '{\"expRate\":0.01}', 'achievement')`);",
     "    ('初入江湖', '{\"expRate\":0.01}', 'achievement')`);\n"
     "  // [r249] 排行称号加成上调（15% 档）：既有 seed 是 INSERT OR IGNORE（改不动已存在行）⇒ 必须 UPDATE 幂等迁移。\n"
     "  //   source 定位与 RANK_TITLE_SOURCES 逐字同源；常量集中于此，单点可调。\n"
     "  db.run('UPDATE titles SET attr_json = ? WHERE source = ?', ['{\"atkRate\":0.15}', 'rank_combat']);   // [r249] 武林盟主 · 战力第一 ⇒ 攻击 +15%\n"
     "  db.run('UPDATE titles SET attr_json = ? WHERE source = ?', ['{\"stoneRate\":0.15}', 'rank_stones']); // [r249] 富甲一方 · 灵石第一 ⇒ 灵石收益 +15%\n"
     "  db.run('UPDATE titles SET attr_json = ? WHERE source = ?', ['{\"expRate\":0.15}', 'rank_realm']);    // [r249] 登峰造极 · 境界第一 ⇒ 修为 +15%"),

    # ④ GET /api/quest/summary 响应追加 rankHolders（不改既有键）
    ("R249 quest/summary 追加 rankHolders",
     "                res.json({\n"
     "                  date,\n"
     "                  quests: questList,\n"
     "                  groups: QUEST_GROUPS,\n"
     "                  activity,\n"
     "                  activityMax: ACTIVITY_MAX,\n"
     "                  chests,\n"
     "                  week, weekActivity, weekMax: ACTIVITY_MAX * 7,\n"
     "                  milestones,\n"
     "                  realmMult: rf,\n"
     "                  returnBuff: { until: buffUntil, active: mult > 1, multiplier: mult },\n"
     "                  titleEquipped: meta?.title_id != null ? Number(meta.title_id) : null,\n"
     "                  ownedTitles: (owned || []).map((t) => ({ id: Number(t.id), name: t.name, attr: attr(t.attr_json), source: t.source })),\n"
     "                  allTitles: (catalog || []).map((t) => ({ id: Number(t.id), name: t.name, attr: attr(t.attr_json), source: t.source })),\n"
     "                });",
     "                const r249payload = {\n"
     "                  date,\n"
     "                  quests: questList,\n"
     "                  groups: QUEST_GROUPS,\n"
     "                  activity,\n"
     "                  activityMax: ACTIVITY_MAX,\n"
     "                  chests,\n"
     "                  week, weekActivity, weekMax: ACTIVITY_MAX * 7,\n"
     "                  milestones,\n"
     "                  realmMult: rf,\n"
     "                  returnBuff: { until: buffUntil, active: mult > 1, multiplier: mult },\n"
     "                  titleEquipped: meta?.title_id != null ? Number(meta.title_id) : null,\n"
     "                  ownedTitles: (owned || []).map((t) => ({ id: Number(t.id), name: t.name, attr: attr(t.attr_json), source: t.source })),\n"
     "                  allTitles: (catalog || []).map((t) => ({ id: Number(t.id), name: t.name, attr: attr(t.attr_json), source: t.source })),\n"
     "                };\n"
     "                // [r249] 追加三榜当前持有者（rankHolders；既有键一字不改）；快照内部自吞异常 ⇒ 恒返回对象。\n"
     "                rankHoldersSnapshot().then((rankHolders) => {\n"
     "                  res.json(Object.assign(r249payload, { rankHolders }));\n"
     "                });"),
]

# ============================================================ 前置依赖（只读自证，不改；不符 ⇒ 退出码 2）
REQUIRES = [
    ("const RANK_TITLE_SOURCES: Array<{ source: string; sort: string }> = [", 1, "RANK_TITLE_SOURCES 必须在位（本环复用）"),
    ("const LEADERBOARD_SORTS: Record<string, { orderBy: string; aheadCondition: string; getParams: (row: any) => any[] }> = {", 1, "LEADERBOARD_SORTS 必须在位（取 #1 的 orderBy 同源）"),
    ("async function grantTitleBySource(userId: number, source: string): Promise<boolean> {", 1, "grantTitleBySource 必须在位（复用授予通道）"),
    ("function shouldGrantRankTitle(topUserId: number, boardSize: number, userId: number, minBoardSize: number = 2): boolean {", 1, "shouldGrantRankTitle 必须在位（minBoardSize=2 语义复用）"),
    ("async function maybeGrantAutoTitles(userId: number, achCount: number): Promise<void> {", 1, "maybeGrantAutoTitles 必须在位（存档汇聚点）"),
    ("app.get('/api/quest/summary'", 1, "quest/summary 端点在位（追加 rankHolders）"),
    ("function dbGet<T = any>(sql: string, params: any[] = []): Promise<T | undefined> {", 1, "dbGet 必须在位"),
    ("function dbRun(sql: string, params: any[] = []): Promise<{ lastID: number; changes: number }> {", 1, "dbRun 必须在位"),
    # 锚点独占性
    ("  { source: 'rank_stones', sort: 'stones' },\n];\n", 1, "RANK_TITLE_SOURCES 收尾锚点必须唯一"),
    ("    ('初入江湖', '{\"expRate\":0.01}', 'achievement')`);", 1, "称号 seed 收尾锚点必须唯一"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "res.status(403", "require(", "PRAGMA",
    # 三榜 orderBy（必须与 /api/leaderboard 逐字同源）——一字不动
    "orderBy: 'realm_index DESC, realm_level DESC, exp DESC, updated_at DESC, user_id ASC'",
    "orderBy: 'combat_power DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC'",
    "orderBy: 'spirit_stones DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC'",
    # 表结构
    "CREATE TABLE IF NOT EXISTS titles (",
    "CREATE TABLE IF NOT EXISTS player_titles (",
    "CREATE TABLE IF NOT EXISTS rankings (",
    # 既有符号
    "async function grantTitleBySource(userId: number, source: string): Promise<boolean> {",
    "function shouldGrantRankTitle(topUserId: number, boardSize: number, userId: number, minBoardSize: number = 2): boolean {",
    "const RANK_TITLE_SOURCES: Array<{ source: string; sort: string }> = [",
    "app.get('/api/leaderboard'",
    "app.get('/api/quest/summary'",
    "return res.json({ gm_revision, has_save: true, updated_at: row.updated_at ?? null });",
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
    d = tempfile.mkdtemp(prefix="r249chk-")
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
# 用内存库 + 合成 rankings/player_titles/saves 行，跑与注入 TS **逐字同源**的 SQL 决策逻辑。
def semantic_harness():
    results = []

    def ck(name, fn):
        try:
            ok = bool(fn())
            results.append((name, ok, ""))
        except Exception as e:
            results.append((name, False, "throw:" + repr(e)))

    def fresh():
        con = sqlite3.connect(":memory:")
        con.executescript(
            "CREATE TABLE rankings (user_id INTEGER PRIMARY KEY, name TEXT,"
            " realm_index INT DEFAULT 0, realm_level INT DEFAULT 1, exp INT DEFAULT 0,"
            " combat_power INT DEFAULT 0, spirit_stones INT DEFAULT 0, updated_at TEXT);"
            "CREATE TABLE titles (id INTEGER PRIMARY KEY, name TEXT, source TEXT);"
            "CREATE TABLE player_titles (user_id INT, title_id INT, PRIMARY KEY(user_id,title_id));"
            "CREATE TABLE saves (user_id INTEGER PRIMARY KEY, title_id INT);"
        )
        con.execute("INSERT INTO titles (id,name,source) VALUES (1,'武林盟主','rank_combat')")
        con.execute("INSERT INTO titles (id,name,source) VALUES (2,'富甲一方','rank_stones')")
        con.execute("INSERT INTO titles (id,name,source) VALUES (3,'登峰造极','rank_realm')")
        con.commit()
        return con

    def reconcile(con, source, title_id, sort):
        orderBy = ORDERBY[sort]
        top = con.execute(SQL_TOP + " " + orderBy + " LIMIT 1").fetchone()
        cnt = con.execute(SQL_COUNT).fetchone()[0]
        topId = top[0] if top else None
        # shouldGrantRankTitle(topId, cnt, topId) == (cnt >= minBoardSize)（minBoardSize 默认 2）
        valid = (topId is not None) and (cnt >= MIN_BOARD_SIZE)
        if not valid:
            con.execute(SQL_DELETE_ALL, [title_id])
            con.execute(SQL_CLEAR_EQUIP_ALL, [title_id])
        else:
            con.execute(SQL_DELETE_OTHERS, [title_id, topId])
            con.execute(SQL_CLEAR_EQUIP_OTHERS, [title_id, topId])
            con.execute(SQL_INSERT_OR_IGNORE, [topId, title_id])
        con.commit()

    def rows(con):
        return sorted(con.execute("SELECT user_id, title_id FROM player_titles").fetchall())

    def equip(con, uid):
        return con.execute("SELECT title_id FROM saves WHERE user_id=?", [uid]).fetchone()[0]

    # ① A 第 1 ⇒ A 持有
    def s1():
        con = fresh()
        con.execute("INSERT INTO rankings (user_id,name,combat_power) VALUES (1,'甲',100)")
        con.execute("INSERT INTO rankings (user_id,name,combat_power) VALUES (2,'乙',50)")
        con.commit()
        reconcile(con, "rank_combat", 1, "combat")
        return rows(con) == [(1, 1)]

    # ② B 反超 ⇒ A 失去、B 获得、该称号恰 1 行
    def s2():
        con = fresh()
        con.execute("INSERT INTO rankings (user_id,name,combat_power) VALUES (1,'甲',100)")
        con.execute("INSERT INTO rankings (user_id,name,combat_power) VALUES (2,'乙',50)")
        con.commit()
        reconcile(con, "rank_combat", 1, "combat")          # A 先持有
        con.execute("UPDATE rankings SET combat_power=200 WHERE user_id=2")
        con.commit()
        reconcile(con, "rank_combat", 1, "combat")          # B 反超
        r = rows(con)
        return r == [(2, 1)] and len(r) == 1

    # ③ 榜不足 2 人 ⇒ 全收回
    def s3():
        con = fresh()
        con.execute("INSERT INTO rankings (user_id,name,combat_power) VALUES (1,'甲',100)")
        con.execute("INSERT INTO player_titles (user_id,title_id) VALUES (1,1)")
        con.commit()
        reconcile(con, "rank_combat", 1, "combat")
        return rows(con) == []

    # ④ 被收回者正佩戴 ⇒ saves.title_id 置空
    def s4():
        con = fresh()
        con.execute("INSERT INTO rankings (user_id,name,combat_power) VALUES (1,'甲',100)")
        con.execute("INSERT INTO rankings (user_id,name,combat_power) VALUES (2,'乙',50)")
        con.execute("INSERT INTO player_titles (user_id,title_id) VALUES (1,1)")
        con.execute("INSERT INTO saves (user_id,title_id) VALUES (1,1)")  # A 佩戴中
        con.commit()
        reconcile(con, "rank_combat", 1, "combat")          # A 第 1 ⇒ 仍佩戴
        kept = equip(con, 1)
        con.execute("UPDATE rankings SET combat_power=200 WHERE user_id=2")
        con.commit()
        reconcile(con, "rank_combat", 1, "combat")          # B 反超 ⇒ A 被收回
        return kept == 1 and equip(con, 1) is None and rows(con) == [(2, 1)]

    # ⑤ 反超后被收回者佩戴置空 + 新榜首合法（综合）
    def s5():
        con = fresh()
        con.execute("INSERT INTO rankings (user_id,name,combat_power) VALUES (1,'甲',100)")
        con.execute("INSERT INTO rankings (user_id,name,combat_power) VALUES (2,'乙',50)")
        con.execute("INSERT INTO player_titles (user_id,title_id) VALUES (1,1)")
        con.execute("INSERT INTO saves (user_id,title_id) VALUES (2,1)")  # 乙未持有却佩戴（脏数据）
        con.commit()
        reconcile(con, "rank_combat", 1, "combat")          # 甲第 1 ⇒ 乙被收回+佩戴置空
        return rows(con) == [(1, 1)] and equip(con, 2) is None

    ck("① A#1 ⇒ A 持有", s1)
    ck("② B 反超 ⇒ A 失去/B 获得/恰 1 行", s2)
    ck("③ 榜不足 2 人 ⇒ 全收回", s3)
    ck("④ 被收回者正佩戴 ⇒ saves.title_id 置空", s4)
    ck("⑤ 脏佩戴者被收回 ⇒ 佩戴同步置空", s5)

    total = len(results)
    nfail = sum(1 for _, ok, _ in results if not ok)
    for name, ok, extra in results:
        print(("  [OK] " if ok else "  [FAIL] ") + name + (("  <" + extra + ">") if extra else ""))
    print("HARNESS_RESULT " + json.dumps({"total": total, "fail": nfail}))
    return total, nfail


def main() -> None:
    ap = argparse.ArgumentParser(description="R-249 排行称号轮换（服务端第 94 环）")
    ap.add_argument("--src", default=SRC, help="待打补丁的服务端源码（装配器会传私有副本）")
    ap.add_argument("--check", action="store_true", help="只校验不写回")
    ap.add_argument("--selftest", action="store_true", help="只校验不写回（含 Node 语法 + sqlite3 语义真跑）")
    ap.add_argument("--reverse", default=None, metavar="PATH",
                    help="反向对照：在未打 r249 的服务端上跑同一套断言，必须确认标记缺席（只校验不写回）")
    a = ap.parse_args()

    # ---- 反向对照模式 ----
    if a.reverse:
        path = a.reverse
        if not os.path.exists(path):
            fail("reverse source not found: " + path)
        with io.open(path, "r", encoding="utf-8", newline="") as f:
            rev = f.read()
        print("== 反向对照（未打 r249 的服务端）：%s ==" % path)
        has_fn = rev.count("reconcileRankTitles")
        has_mark = rev.count(MARK)
        print("  reconcileRankTitles 计数 = %d（期望 0，证明未打）" % has_fn)
        print("  [r249] 计数 = %d（期望 0）" % has_mark)
        if has_fn == 0 and has_mark == 0:
            print("  [REVERSE] PASS（基线确实未打 r249，标记缺席）")
        else:
            print("  [REVERSE] FAIL（★ 该源已含 r249 痕迹，不构成基线）")
        return

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等（★ 与 r233 的差异：幂等 ⇒ 退出码 3，由调用方区分「已打」与「失败」）
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
    # SQL 同源基线（harness 测的就是产物里的 SQL）：改动后计数由「移除旧循环 / 新增两处」推导。
    base_sql_top = src.count(SQL_TOP)          # 旧循环 1 处 → 移除 1 / 新增 reconcile 1 ⇒ 不变
    base_sql_count = src.count(SQL_COUNT)      # 旧循环 1 处 → 移除 1 / 新增 reconcile+snapshot 2 ⇒ +1
    base_sql_title_id = src.count(SQL_TITLE_ID)  # grantTitleBySource 1 处 → 新增 reconcile 1 ⇒ +1

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    mark_n = sum(new.count(MARK) for _, _, new in EDITS)
    gates = [
        ("R249 幂等标记就位", MARK, mark_n),
        # ① 新函数/常量/定时器
        ("① reconcileRankTitles 定义", "async function reconcileRankTitles(): Promise<void> {", 1),
        ("① rankHoldersSnapshot 定义", "async function rankHoldersSnapshot(): Promise<Record<string, { name: string; title: string } | null>> {", 1),
        ("① RANK_TITLE_TICK_MS 常量", "const RANK_TITLE_TICK_MS = 10 * 60 * 1000;", 1),
        ("① rankTitleEngineOn 开关", "let rankTitleEngineOn = true;", 1),
        ("① rankTitleSettling 重入锁", "let rankTitleSettling = false;", 1),
        ("① tick 首行早退", "  if (!rankTitleEngineOn) return;", 1),
        ("① tick 重入锁", "  if (rankTitleSettling) return;", 1),
        ("① tick 注释 [ranktitle]", "[ranktitle]", 1),
        ("① 收回非 #1（SQL）", SQL_DELETE_OTHERS, 1),
        ("① 全表收回（SQL）", "dbRun('DELETE FROM player_titles WHERE title_id = ?', [titleId])", 1),
        ("① 佩戴清理非 #1（SQL）", SQL_CLEAR_EQUIP_OTHERS, 1),
        ("① 佩戴清理全表（SQL）", "dbRun('UPDATE saves SET title_id = NULL WHERE title_id = ?', [titleId])", 1),
        ("① 授予 #1 复用 grantTitleBySource", "await grantTitleBySource(topId as number, source);", 1),
        # ② maybeGrant 复用
        ("② maybeGrant 复用 reconcile", "await reconcileRankTitles(); // [r249]", 1),
        ("② 旧惰性授予循环已清零", "if (top && cnt && shouldGrantRankTitle(Number(top.user_id), Number(cnt.c), userId)) {", 0),
        # ③ attr 迁移
        ("③ attr rank_combat → atkRate .15", "'{\"atkRate\":0.15}', 'rank_combat'", 1),
        ("③ attr rank_stones → stoneRate .15", "'{\"stoneRate\":0.15}', 'rank_stones'", 1),
        ("③ attr rank_realm → expRate .15", "'{\"expRate\":0.15}', 'rank_realm'", 1),
        ("③ 用 UPDATE（非 INSERT OR IGNORE）", "db.run('UPDATE titles SET attr_json = ? WHERE source = ?'", 3),
        # ④ 端点
        ("④ 端点追加 rankHolders", "Object.assign(r249payload, { rankHolders })", 1),
        ("④ rankHolders 结构（三键 null）", "const out: Record<string, { name: string; title: string } | null> = { combat: null, stones: null, realm: null };", 1),
        ("④ 旧 res.json({ 主载荷已清零", "                res.json({\n                  date,", 0),
        # SQL 同源门禁（harness 测的就是产物里的 SQL）
        ("SQL 同源 SQL_INSERT_OR_IGNORE", SQL_INSERT_OR_IGNORE, src.count(SQL_INSERT_OR_IGNORE)),
        ("SQL 同源 SQL_TOP", SQL_TOP, base_sql_top),
        ("SQL 同源 SQL_COUNT", SQL_COUNT, base_sql_count + 1),
        ("SQL 同源 SQL_TITLE_ID", SQL_TITLE_ID, base_sql_title_id + 1),
    ]
    # 冻结：既有符号/表结构/orderBy 一字不动
    for needle in BASE_NEEDLES:
        gates.append(("冻结 " + needle[:44].replace("\n", " "), needle, base[needle]))
    # setInterval 只新增 1 个
    gates.append(("红线 setInterval 仅 +1", "setInterval(", base_interval + 1))
    # 红线：不新增 res.status(403) / PRAGMA
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
    bak = "%s.bak-r249-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r249-", suffix=".tmp")
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
