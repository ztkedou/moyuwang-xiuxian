# -*- coding: utf-8 -*-
r"""
srv_patch_113.py -- R-113 万妖巢穴：五只 boss 同时出现 + 逐只独立次数/冷却（服务端半边）

需求原文（台账 R-113，用户 2026-10-02，逐字）
--------------------------------------------------------------------------
  「万妖巢穴 是5只boss同时出现，每个次数与冷却单独计算，不按照等阶变化次数了，
    统一全部免费一天5次，收费一天10次。收费一次冷却时间5分钟。」

现状（侦察 srv/index_v28.ts，ring-54 产物；activity087 + srv_patch_056 之后）
--------------------------------------------------------------------------
  · event_boss 每期**仅 1 行**（event_id PRIMARY KEY），boss_no 是「当前第几只」；
    R-056 把五只做成**逐只顺序**：诛一只当场把该行刷成下一只（free_used 全员归零）；
  · 免费出手 5 次/只（event_boss_hits.free_used），免费出手 10 分钟冷却（last_strike_at）；
  · 收费 = 诛妖符 2 张/日（fun_daily kind='raid_talisman'），**无冷却**。
  ⇒ 与需求「五只**同时** / 每只次数与冷却**单独** / 免费一天 5 次 / 收费一天 10 次 /
     收费一次冷却 5 分钟」结构性不符。

★ 落点判定（0.8.10 教训：次数/冷却的真闸门在服务端端点，只改客户端 = 死代码）
--------------------------------------------------------------------------
  本玩法三端点 `/api/eventboss/{status,strike,talisman}` 是次数（fun_daily / free_used）与
  冷却（last_strike_at）的**唯一权威**；客户端（YlxwTActBoss）只做展示与发意图。
  ⇒ 客户端半边（yl_r113_ext.py）**必须**配套本服务端补丁，否则「五只同现/逐只计数/收费冷却」
    全是死代码。两者同批交付。

本环改点（14 处锚改，全在 activity087 注入的 boss 域内）
--------------------------------------------------------------------------
  E1  常量：保留 FREE_STRIKES=5 / MAX_BOSSES=5 / HP_GROWTH=0.5；新增 PAID_LIMIT=10、
      PAID_COOLDOWN_MS=5 分钟；STRIKE_COOLDOWN_MS 维持 10 分钟（逐只口径）。
  E2  DDL：新建 event_boss5（event_id,boss_no 复合主键，五只血量并存）；老表不重建、不迁移。
  E3  actBossEnsure：删除 R-056「诛一只刷下一只」顺序逻辑；改为幂等建 5 个槽位；
      event_boss 行降级为「聚合/结算行」（血量求和）。
  E4  actBossHitOnce 签名 + bossNo；扣血改打 event_boss5 指定槽位；记分仍累计到
      event_boss_hits（结算档位/榜单口径不变）；聚合行重算（五只全诛才 killed=1）。
  E5  status：逐只回执 bosses[]（血量/击杀/免费剩余/收费剩余/免费冷却/收费冷却）+
      freeLimit/paidLimit；保留 legacy 顶层字段（取第 1 只）供旧客户端兜底。
  E6  strike 配额块：改「指定只 · 免费 5 次/日 + 10 分钟冷却」（fun_daily kind='raid5f…'）。
  E7  strike fun_daily 行：kind 逐只化，count 用 freeUsed+1。
  E8  strike 调用 hitOnce(…, bossNo, true)。
  E9  strike 回执：回 bossNo。
  E10 talisman 配额块：改「指定只 · 收费 10 次/日 + 5 分钟冷却」（kind='raid5p…'）。
  E11 talisman fun_daily 行：kind 逐只化。
  E12 talisman 调用 hitOnce(…, bossNo, false)。
  E13 talisman 回执：回 bossNo + talismanLeft(收费口径) + paidCoolLeft。
  E14 新增逐只计数助手 actBossKind / actBossUsedToday / actBossLastAt。

结算兼容（五只同现不破坏结算器）
--------------------------------------------------------------------------
  · 结算器读 event_boss.killed/killer_id/killed_at/settled + event_boss_hits（聚合）。
    本环令 event_boss 成为聚合行：血量求和；**五只全诛**才 killed=1、killed_at=全诛时刻、
    killer_id=最后一击者 ⇒ 「全诛后休战 2 天结算」语义与单 boss 时代一致；
  · event_boss_hits 仍按 (event_id,user_id) 累计 score/strikes ⇒ 档位/排名/全服奖零改动；
  · 窗口结束未全诛 ⇒ killed=0，结算走「妖兽遁走」分支，与现状一致。

CLI 契约（同 srv_patch_056.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回；`--check` / `--selftest` 只校验不写。
  幂等：产物含 `[r113boss]` 标记则 SKIP。lead 接线：SRV_CHAIN 链尾追加本文件（ring 55）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval`；不新增 PRAGMA（用
    CREATE TABLE IF NOT EXISTS，无需加列守卫）。
  · 每处替换 expect=1；命中数不符即中止。
  · ⛔ 不改 srv/index_v28.ts（链产物）；⛔ 不改任何既有 srv_patch_*.py。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r113boss]"

# ============================================================ 锚点与替换

# E1 常量块（srv_patch_056 产物形态，逐字节）
E1_OLD = (
    "const ACT_BOSS_FREE_STRIKES = 5;                   // [r056boss] R-056 免费出手 5 次/只（event_boss_hits.free_used，换 boss 归零；每日不限次）\n"
    "const ACT_BOSS_MAX_BOSSES = 5;                     // [r056boss] R-056 每期连刷 5 只（诛一只当场现身下一只；最终只保留休战 2 天结算）\n"
    "const ACT_BOSS_STRIKE_COOLDOWN_MS = 10 * 60 * 1000; // [r056boss] R-056 免费出手冷却 10 分钟（event_boss_hits.last_strike_at）\n"
    "const ACT_BOSS_HP_GROWTH = 0.5;                    // [r056boss] R-056 第 n 只血量 = 基础 × (1 + 0.5×(n-1))：第 2 只 1.5× … 第 5 只 3×"
)
E1_NEW = (
    "const ACT_BOSS_FREE_STRIKES = 5;                   // [r113boss] R-113 免费出手 5 次/日/只（fun_daily kind='raid5f<ev>_<no>'，逐只独立）\n"
    "const ACT_BOSS_PAID_LIMIT = 10;                    // [r113boss] R-113 收费（诛妖符）10 次/日/只（kind='raid5p<ev>_<no>'，逐只独立）\n"
    "const ACT_BOSS_PAID_COOLDOWN_MS = 5 * 60 * 1000;   // [r113boss] R-113 收费出手冷却 5 分钟（逐只独立，取该 kind 最近一次时间）\n"
    "const ACT_BOSS_MAX_BOSSES = 5;                     // [r113boss] R-113 五只 boss 同时出现（event_boss5 五行并存，各自独立血量/次数/冷却）\n"
    "const ACT_BOSS_STRIKE_COOLDOWN_MS = 10 * 60 * 1000; // [r113boss] R-113 免费出手冷却 10 分钟（逐只独立，kind='raid5f<ev>_<no>'）\n"
    "const ACT_BOSS_HP_GROWTH = 0.5;                    // [r113boss] R-113 第 n 只血量 = 基础 × (1 + 0.5×(n-1))：第 1 只 1× … 第 5 只 3×"
)

# E2 DDL：插在冲榜聚合索引之前（与 srv_patch_056 E2 同一落点，唯一）
E2_ANCHOR = "db.run(`CREATE INDEX IF NOT EXISTS idx_stats_daily_date ON stats_daily(date)`);"
E2_BLOCK = (
    "  // [r113boss] R-113 万妖巢穴五只同现：新建 event_boss5（每期 5 行并存，复合主键）。\n"
    "  //   建表幂等；不改 event_boss / event_boss_hits（前者降级为聚合/结算行，后者仍为跨只累计榜）。\n"
    "  db.run(`CREATE TABLE IF NOT EXISTS event_boss5 (\n"
    "    event_id INTEGER NOT NULL,\n"
    "    boss_no INTEGER NOT NULL,\n"
    "    hp_max INTEGER NOT NULL,\n"
    "    hp_cur INTEGER NOT NULL,\n"
    "    killed INTEGER NOT NULL DEFAULT 0,\n"
    "    killer_id INTEGER,\n"
    "    PRIMARY KEY (event_id, boss_no)\n"
    "  )`);\n"
)

# E3 actBossEnsure 整段
E3_OLD = (
    "async function actBossEnsure(eventId: number): Promise<any> {\n"
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
    "  const top = await dbGet('SELECT MAX(realm_index) AS ri FROM rankings').catch(() => null);\n"
    "  const mult = Math.pow(1.5, Math.min(20, Math.max(0, Number(top && top.ri) || 0)));\n"
    "  const hp = Math.floor(WB_HP_BASE * mult * ACT_BOSS_HP_CYCLE);\n"
    "  await dbRun('INSERT OR IGNORE INTO event_boss (event_id, hp_max, hp_cur) VALUES (?, ?, ?)', [eventId, hp, hp]).catch(() => { });\n"
    "  return await dbGet('SELECT * FROM event_boss WHERE event_id = ?', [eventId]);\n"
    "}\n"
)
E3_NEW = (
    "async function actBossEnsure(eventId: number): Promise<any> {\n"
    "  // [r113boss] R-113 五只 boss 同时出现：event_boss 行降级为「聚合/结算行」（血量求和；五只全诛才\n"
    "  //   killed=1），真正血量在 event_boss5 五行（各自独立）。R-056「诛一只刷下一只」顺序逻辑整体移除。\n"
    "  //   ★ 基础血量行（hp = floor(WB_HP_BASE × mult × ACT_BOSS_HP_CYCLE)）逐字保留，\n"
    "  //     不改 reward089 冻结锚「万妖巢穴血量未动」；逐只血量在其上乘成长系数。\n"
    "  const top = await dbGet('SELECT MAX(realm_index) AS ri FROM rankings').catch(() => null);\n"
    "  const mult = Math.pow(1.5, Math.min(20, Math.max(0, Number(top && top.ri) || 0)));\n"
    "  const hp = Math.floor(WB_HP_BASE * mult * ACT_BOSS_HP_CYCLE);\n"
    "  let row = await dbGet('SELECT * FROM event_boss WHERE event_id = ?', [eventId]).catch(() => null);\n"
    "  if (!row) {\n"
    "    const sum0 = Math.floor(hp * (ACT_BOSS_MAX_BOSSES + ACT_BOSS_HP_GROWTH * ACT_BOSS_MAX_BOSSES * (ACT_BOSS_MAX_BOSSES - 1) / 2));\n"
    "    await dbRun('INSERT OR IGNORE INTO event_boss (event_id, hp_max, hp_cur) VALUES (?, ?, ?)', [eventId, sum0, sum0]).catch(() => { });\n"
    "    row = await dbGet('SELECT * FROM event_boss WHERE event_id = ?', [eventId]).catch(() => null);\n"
    "  }\n"
    "  // 五只槽位幂等建场（各自血量 = 基础 × (1 + 0.5×(n-1))；建场即定血，跨请求不漂移）\n"
    "  for (let no = 1; no <= ACT_BOSS_MAX_BOSSES; no++) {\n"
    "    const slot = await dbGet('SELECT boss_no FROM event_boss5 WHERE event_id = ? AND boss_no = ?', [eventId, no]).catch(() => null);\n"
    "    if (!slot) {\n"
    "      const hpN = Math.floor(hp * (1 + ACT_BOSS_HP_GROWTH * (no - 1)));\n"
    "      await dbRun('INSERT OR IGNORE INTO event_boss5 (event_id, boss_no, hp_max, hp_cur) VALUES (?, ?, ?, ?)', [eventId, no, hpN, hpN]).catch(() => { });\n"
    "    }\n"
    "  }\n"
    "  return row;\n"
    "}\n"
)

# E4 actBossHitOnce 整段
E4_OLD = (
    "async function actBossHitOnce(userId: number, eventId: number, nowMs: number, isFree: boolean): Promise<{ score: number; total: number; killed: boolean; hpCur: number }> {\n"
    "  const cpRow = await dbGet('SELECT combat_power FROM rankings WHERE user_id = ?', [userId]).catch(() => null);\n"
    "  const cp = Number(cpRow && cpRow.combat_power) || 100;\n"
    "  const score = Math.max(1, Math.floor(cp * 2 * (0.8 + Math.random() * 0.4)));\n"
    "  // 守卫式扣血（killed=0 守卫：SET 表达式全按旧值求值，kill 判定与回写一次完成）\n"
    "  const upd = await dbRun(\n"
    "    `UPDATE event_boss SET\n"
    "       hp_cur = MAX(0, hp_cur - ?),\n"
    "       killed = CASE WHEN hp_cur - ? <= 0 THEN 1 ELSE killed END,\n"
    "       killer_id = CASE WHEN hp_cur - ? <= 0 THEN ? ELSE killer_id END,\n"
    "       killed_at = CASE WHEN hp_cur - ? <= 0 THEN ? ELSE killed_at END\n"
    "     WHERE event_id = ? AND killed = 0`,\n"
    "    [score, score, score, userId, score, nowMs, eventId]);\n"
    "  if (!upd.changes) throw new Error('ACT_BOSS_KILLED_RACE');\n"
    "  // 记分（PK 幂等 upsert；不发放任何即时灵石——D2 结构保证）\n"
    "  await dbRun(\n"
    "    `INSERT INTO event_boss_hits (event_id, user_id, score, strikes, free_used, last_strike_at) VALUES (?, ?, ?, 1, ?, ?)\n"
    "     ON CONFLICT(event_id, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1,\n"
    "       free_used = free_used + excluded.free_used, last_strike_at = excluded.last_strike_at`,\n"
    "    [eventId, userId, score, isFree ? 1 : 0, nowMs]);\n"
    "  const after = await dbGet('SELECT hp_cur, killed, killer_id FROM event_boss WHERE event_id = ?', [eventId]);\n"
    "  const mine = await dbGet('SELECT score FROM event_boss_hits WHERE event_id = ? AND user_id = ?', [eventId, userId]);\n"
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
    "  if (killed && Number(after && after.killer_id) === userId) {\n"
    "    const kn = await actNameOf(userId);\n"
    "    logChronicle(userId, kn, `【诛妖】「${String((await dbGet('SELECT name FROM events WHERE id = ?', [eventId]).catch(() => null))?.name || '万妖')}」伏诛，最后一击出自「${kn}」之手，全服同贺`);\n"
    "  }\n"
    "  return { score, total: Math.max(0, Math.floor(Number(mine && mine.score) || 0)), killed, hpCur: Math.max(0, Math.floor(Number(after && after.hp_cur) || 0)) };\n"
    "}\n"
)
E4_NEW = (
    "async function actBossHitOnce(userId: number, eventId: number, bossNo: number, nowMs: number, isFree: boolean): Promise<{ score: number; total: number; killed: boolean; hpCur: number }> {\n"
    "  const cpRow = await dbGet('SELECT combat_power FROM rankings WHERE user_id = ?', [userId]).catch(() => null);\n"
    "  const cp = Number(cpRow && cpRow.combat_power) || 100;\n"
    "  const score = Math.max(1, Math.floor(cp * 2 * (0.8 + Math.random() * 0.4)));\n"
    "  // [r113boss] R-113：扣血改打指定槽位 event_boss5（bossNo 由请求体带入）；守卫式扣血口径与单 boss 时代一致。\n"
    "  const upd = await dbRun(\n"
    "    `UPDATE event_boss5 SET\n"
    "       hp_cur = MAX(0, hp_cur - ?),\n"
    "       killed = CASE WHEN hp_cur - ? <= 0 THEN 1 ELSE killed END,\n"
    "       killer_id = CASE WHEN hp_cur - ? <= 0 THEN ? ELSE killer_id END\n"
    "     WHERE event_id = ? AND boss_no = ? AND killed = 0`,\n"
    "    [score, score, score, userId, eventId, bossNo]);\n"
    "  if (!upd.changes) throw new Error('ACT_BOSS_KILLED_RACE');\n"
    "  // 记分（PK 幂等 upsert；跨 5 只累计到 event_boss_hits ⇒ 结算档位/榜单口径与单 boss 时代一致）\n"
    "  await dbRun(\n"
    "    `INSERT INTO event_boss_hits (event_id, user_id, score, strikes) VALUES (?, ?, ?, 1)\n"
    "     ON CONFLICT(event_id, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1`,\n"
    "    [eventId, userId, score]);\n"
    "  // 聚合行重算：血量求和；五只全诛才把 killed=1 / killed_at 落到 event_boss（供结算器判定休战与结算）\n"
    "  const agg = await dbGet('SELECT COALESCE(SUM(hp_max),0) AS hm, COALESCE(SUM(hp_cur),0) AS hc, COALESCE(SUM(killed),0) AS kc, COUNT(*) AS n FROM event_boss5 WHERE event_id = ?', [eventId]).catch(() => null);\n"
    "  const allDead = Number(agg && agg.n) > 0 && Number(agg && agg.kc) >= Number(agg && agg.n);\n"
    "  await dbRun(\n"
    "    'UPDATE event_boss SET hp_max = ?, hp_cur = ?, killed = ?, killer_id = CASE WHEN ? = 1 THEN ? ELSE killer_id END, killed_at = CASE WHEN ? = 1 THEN ? ELSE killed_at END WHERE event_id = ?',\n"
    "    [Math.max(0, Math.floor(Number(agg && agg.hm) || 0)), Math.max(0, Math.floor(Number(agg && agg.hc) || 0)), allDead ? 1 : 0, allDead ? 1 : 0, userId, allDead ? 1 : 0, nowMs, eventId]).catch(() => { });\n"
    "  const after = await dbGet('SELECT hp_cur, killed, killer_id FROM event_boss5 WHERE event_id = ? AND boss_no = ?', [eventId, bossNo]);\n"
    "  const mine = await dbGet('SELECT score FROM event_boss_hits WHERE event_id = ? AND user_id = ?', [eventId, userId]);\n"
    "  const killed = Number(after && after.killed) === 1;\n"
    "  if (killed && Number(after && after.killer_id) === userId) {\n"
    "    const kn = await actNameOf(userId);\n"
    "    logChronicle(userId, kn, `【诛妖】「${String((await dbGet('SELECT name FROM events WHERE id = ?', [eventId]).catch(() => null))?.name || '万妖')}」第 ${bossNo} 只伏诛，最后一击出自「${kn}」之手，全服同贺`);\n"
    "  }\n"
    "  return { score, total: Math.max(0, Math.floor(Number(mine && mine.score) || 0)), killed, hpCur: Math.max(0, Math.floor(Number(after && after.hp_cur) || 0)) };\n"
    "}\n"
)

# E5 status 块
E5_OLD = (
    "    const mine = await dbGet('SELECT score, strikes, free_used, last_strike_at FROM event_boss_hits WHERE event_id = ? AND user_id = ?', [Number(ev.id), userId]).catch(() => null);\n"
    "    const top = await dbAll(\n"
    "      `SELECT h.user_id AS uid, h.score, COALESCE(NULLIF(r.name, ''), u.username) AS name\n"
    "       FROM event_boss_hits h JOIN users u ON u.id = h.user_id LEFT JOIN rankings r ON r.user_id = h.user_id\n"
    "       WHERE h.event_id = ? ORDER BY h.score DESC LIMIT 10`, [Number(ev.id)]);\n"
    "    // [r056boss] R-056：freeLeft 改「每只 5 次」口径（free_used）；coolLeft = 免费出手冷却剩余秒。\n"
    "    const freeUsed = Math.max(0, Math.floor(Number(mine && mine.free_used) || 0));\n"
    "    const lastAtS = Math.max(0, Math.floor(Number(mine && mine.last_strike_at) || 0));\n"
    "    const coolLeft = lastAtS > 0 ? Math.max(0, Math.ceil((ACT_BOSS_STRIKE_COOLDOWN_MS - (Date.now() - lastAtS)) / 1000)) : 0;\n"
    "    const usedTal = await actFunUsedToday(userId, 'raid_talisman');\n"
    "    const killed = Number(boss.killed) === 1;\n"
    "    res.json({\n"
    "      eventId: Number(ev.id),\n"
    "      hpMax: Math.max(0, Math.floor(Number(boss.hp_max) || 0)),\n"
    "      hpCur: Math.max(0, Math.floor(Number(boss.hp_cur) || 0)),\n"
    "      killed,\n"
    "      killerName: killed ? await actNameOf(boss.killer_id) : null,\n"
    "      myScore: Math.max(0, Math.floor(Number(mine && mine.score) || 0)),\n"
    "      myStrikes: Math.max(0, Math.floor(Number(mine && mine.strikes) || 0)),\n"
    "      freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - freeUsed),\n"
    "      talismanLeft: Math.max(0, ACT_BOSS_TALISMAN_DAILY - usedTal),\n"
    "      bossNo: Math.max(1, Math.floor(Number(boss.boss_no) || 1)),\n"
    "      bossMax: ACT_BOSS_MAX_BOSSES,\n"
    "      coolLeft,\n"
    "      top10: (top || []).map((x: any, i: number) => ({ userId: Number(x.uid), name: String(x.name || ''), score: Math.max(0, Math.floor(Number(x.score) || 0)), rank: i + 1 })),\n"
    "      active: actIsActive(ev, Date.now()),\n"
)
E5_NEW = (
    "    const mine = await dbGet('SELECT score, strikes FROM event_boss_hits WHERE event_id = ? AND user_id = ?', [Number(ev.id), userId]).catch(() => null);\n"
    "    const top = await dbAll(\n"
    "      `SELECT h.user_id AS uid, h.score, COALESCE(NULLIF(r.name, ''), u.username) AS name\n"
    "       FROM event_boss_hits h JOIN users u ON u.id = h.user_id LEFT JOIN rankings r ON r.user_id = h.user_id\n"
    "       WHERE h.event_id = ? ORDER BY h.score DESC LIMIT 10`, [Number(ev.id)]);\n"
    "    // [r113boss] R-113：五只 boss 同时出现，逐只回执（各自血量/击杀/免费次数/收费次数/冷却）。\n"
    "    const slots = await dbAll('SELECT boss_no, hp_max, hp_cur, killed, killer_id FROM event_boss5 WHERE event_id = ? ORDER BY boss_no ASC', [Number(ev.id)]).catch(() => []);\n"
    "    const nowS = Date.now();\n"
    "    const bosses: any[] = [];\n"
    "    for (const s of (slots || [])) {\n"
    "      const no = Math.max(1, Math.floor(Number(s.boss_no) || 1));\n"
    "      const kd = Number(s.killed) === 1;\n"
    "      const fUsed = await actBossUsedToday(userId, Number(ev.id), no, 'f');\n"
    "      const pUsed = await actBossUsedToday(userId, Number(ev.id), no, 'p');\n"
    "      const fAt = await actBossLastAt(userId, Number(ev.id), no, 'f');\n"
    "      const pAt = await actBossLastAt(userId, Number(ev.id), no, 'p');\n"
    "      bosses.push({\n"
    "        no,\n"
    "        hpMax: Math.max(0, Math.floor(Number(s.hp_max) || 0)),\n"
    "        hpCur: Math.max(0, Math.floor(Number(s.hp_cur) || 0)),\n"
    "        killed: kd,\n"
    "        killerName: kd ? await actNameOf(s.killer_id) : null,\n"
    "        freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - fUsed),\n"
    "        paidLeft: Math.max(0, ACT_BOSS_PAID_LIMIT - pUsed),\n"
    "        freeCoolLeft: fAt > 0 ? Math.max(0, Math.ceil((ACT_BOSS_STRIKE_COOLDOWN_MS - (nowS - fAt)) / 1000)) : 0,\n"
    "        paidCoolLeft: pAt > 0 ? Math.max(0, Math.ceil((ACT_BOSS_PAID_COOLDOWN_MS - (nowS - pAt)) / 1000)) : 0,\n"
    "      });\n"
    "    }\n"
    "    const killed = Number(boss.killed) === 1;\n"
    "    res.json({\n"
    "      eventId: Number(ev.id),\n"
    "      hpMax: Math.max(0, Math.floor(Number(boss.hp_max) || 0)),\n"
    "      hpCur: Math.max(0, Math.floor(Number(boss.hp_cur) || 0)),\n"
    "      killed,\n"
    "      killerName: killed ? await actNameOf(boss.killer_id) : null,\n"
    "      myScore: Math.max(0, Math.floor(Number(mine && mine.score) || 0)),\n"
    "      myStrikes: Math.max(0, Math.floor(Number(mine && mine.strikes) || 0)),\n"
    "      freeLeft: bosses.length ? bosses[0].freeLeft : 0,\n"
    "      talismanLeft: bosses.length ? bosses[0].paidLeft : 0,\n"
    "      bossNo: 1,\n"
    "      bossMax: ACT_BOSS_MAX_BOSSES,\n"
    "      coolLeft: bosses.length ? bosses[0].freeCoolLeft : 0,\n"
    "      freeLimit: ACT_BOSS_FREE_STRIKES,\n"
    "      paidLimit: ACT_BOSS_PAID_LIMIT,\n"
    "      bosses,\n"
    "      top10: (top || []).map((x: any, i: number) => ({ userId: Number(x.uid), name: String(x.name || ''), score: Math.max(0, Math.floor(Number(x.score) || 0)), rank: i + 1 })),\n"
    "      active: actIsActive(ev, Date.now()),\n"
)

# E6 strike 配额块
E6_OLD = (
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
E6_NEW = (
    "    // [r113boss] R-113：bossNo 由请求体带入；五只同时出现，逐只独立「免费 5 次/日 + 10 分钟冷却」。\n"
    "    const bossNo = Math.max(1, Math.min(ACT_BOSS_MAX_BOSSES, Math.floor(Number(req.body?.bossNo) || 1)));\n"
    "    const slotRow = await dbGet('SELECT killed FROM event_boss5 WHERE event_id = ? AND boss_no = ?', [Number(ev.id), bossNo]).catch(() => null);\n"
    "    if (!slotRow) return res.status(409).json({ error: '该妖兽不存在' });\n"
    "    if (Number(slotRow.killed) === 1) return res.status(409).json({ error: '该妖兽已被诛杀' });\n"
    "    const freeUsed = await actBossUsedToday(userId, Number(ev.id), bossNo, 'f');\n"
    "    if (freeUsed >= ACT_BOSS_FREE_STRIKES) {\n"
    "      return res.status(409).json({ error: `本只妖兽的免费出手已用尽（${ACT_BOSS_FREE_STRIKES} 次/日），可用诛妖符追加` });\n"
    "    }\n"
    "    const lastAt = await actBossLastAt(userId, Number(ev.id), bossNo, 'f');\n"
    "    const coolMs = lastAt > 0 ? ACT_BOSS_STRIKE_COOLDOWN_MS - (now - lastAt) : 0;\n"
    "    if (coolMs > 0) {\n"
    "      return res.status(409).json({ error: `出手冷却中，还需 ${Math.ceil(coolMs / 1000)} 秒` });\n"
    "    }\n"
)

# E7 strike fun_daily 行
E7_OLD = (
    "        'INSERT INTO fun_daily (player_id, date, kind, count, cost, payout, detail, created_at) VALUES (?, ?, ?, ?, 0, 0, ?, ?)',\n"
    "        [userId, utcDateStr(), 'raid', used + 1, JSON.stringify({ eventId: Number(ev.id) }), now]);\n"
)
E7_NEW = (
    "        'INSERT INTO fun_daily (player_id, date, kind, count, cost, payout, detail, created_at) VALUES (?, ?, ?, ?, 0, 0, ?, ?)',\n"
    "        [userId, utcDateStr(), actBossKind(Number(ev.id), bossNo, 'f'), freeUsed + 1, JSON.stringify({ eventId: Number(ev.id), bossNo }), now]);\n"
)

# E8 strike hitOnce 调用
E8_OLD = "      hit = await actBossHitOnce(userId, Number(ev.id), now, true);\n"
E8_NEW = "      hit = await actBossHitOnce(userId, Number(ev.id), bossNo, now, true);\n"

# E9 strike 回执
E9_OLD = (
    "      freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - freeUsed - 1),\n"
    "      coolLeft: ACT_BOSS_STRIKE_COOLDOWN_MS,\n"
)
E9_NEW = (
    "      bossNo,\n"
    "      freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - freeUsed - 1),\n"
    "      coolLeft: ACT_BOSS_STRIKE_COOLDOWN_MS,\n"
)

# E10 talisman 配额块
E10_OLD = (
    "    const used = await actFunUsedToday(userId, 'raid_talisman');\n"
    "    if (used >= ACT_BOSS_TALISMAN_DAILY) {\n"
    "      return res.status(409).json({ error: `今日诛妖符已用尽（${ACT_BOSS_TALISMAN_DAILY} 张）` });\n"
    "    }\n"
)
E10_NEW = (
    "    // [r113boss] R-113：收费（诛妖符）逐只 10 次/日 + 5 分钟冷却；bossNo 由请求体带入。\n"
    "    const bossNo = Math.max(1, Math.min(ACT_BOSS_MAX_BOSSES, Math.floor(Number(req.body?.bossNo) || 1)));\n"
    "    const slotRow = await dbGet('SELECT killed FROM event_boss5 WHERE event_id = ? AND boss_no = ?', [Number(ev.id), bossNo]).catch(() => null);\n"
    "    if (!slotRow) return res.status(409).json({ error: '该妖兽不存在' });\n"
    "    if (Number(slotRow.killed) === 1) return res.status(409).json({ error: '该妖兽已被诛杀' });\n"
    "    const used = await actBossUsedToday(userId, Number(ev.id), bossNo, 'p');\n"
    "    if (used >= ACT_BOSS_PAID_LIMIT) {\n"
    "      return res.status(409).json({ error: `本只妖兽的收费出手已用尽（${ACT_BOSS_PAID_LIMIT} 次/日）` });\n"
    "    }\n"
    "    const paidLastAt = await actBossLastAt(userId, Number(ev.id), bossNo, 'p');\n"
    "    const paidCoolMs = paidLastAt > 0 ? ACT_BOSS_PAID_COOLDOWN_MS - (now - paidLastAt) : 0;\n"
    "    if (paidCoolMs > 0) {\n"
    "      return res.status(409).json({ error: `收费出手冷却中，还需 ${Math.ceil(paidCoolMs / 1000)} 秒` });\n"
    "    }\n"
)

# E11 talisman fun_daily 行
E11_OLD = (
    "        'INSERT INTO fun_daily (player_id, date, kind, count, cost, payout, detail, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)',\n"
    "        [userId, utcDateStr(), 'raid_talisman', used + 1, price, JSON.stringify({ eventId: Number(ev.id) }), now]);\n"
)
E11_NEW = (
    "        'INSERT INTO fun_daily (player_id, date, kind, count, cost, payout, detail, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)',\n"
    "        [userId, utcDateStr(), actBossKind(Number(ev.id), bossNo, 'p'), used + 1, price, JSON.stringify({ eventId: Number(ev.id), bossNo }), now]);\n"
)

# E12 talisman hitOnce 调用
E12_OLD = "      hit = await actBossHitOnce(userId, Number(ev.id), now, false);\n"
E12_NEW = "      hit = await actBossHitOnce(userId, Number(ev.id), bossNo, now, false);\n"

# E13 talisman 回执
E13_OLD = "      talismanLeft: Math.max(0, ACT_BOSS_TALISMAN_DAILY - used - 1),\n"
E13_NEW = (
    "      bossNo,\n"
    "      talismanLeft: Math.max(0, ACT_BOSS_PAID_LIMIT - used - 1),\n"
    "      paidCoolLeft: ACT_BOSS_PAID_COOLDOWN_MS,\n"
)

# E14 逐只计数助手（紧跟 actFunUsedToday 定义之后）
E14_OLD = (
    "async function actFunUsedToday(userId: number, kind: string): Promise<number> {\n"
    "  const c = await dbGet('SELECT COUNT(*) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, utcDateStr(), kind]).catch(() => null);\n"
    "  return Math.max(0, Number(c && c.c) || 0);\n"
    "}\n"
)
E14_NEW = E14_OLD + (
    "// [r113boss] R-113：逐只 boss 的当日计数 / 最近一次时间（kind = 'raid5' + f|p + eventId + '_' + bossNo）\n"
    "function actBossKind(eventId: number, bossNo: number, slot: string): string {\n"
    "  return 'raid5' + slot + eventId + '_' + bossNo;\n"
    "}\n"
    "async function actBossUsedToday(userId: number, eventId: number, bossNo: number, slot: string): Promise<number> {\n"
    "  const c = await dbGet('SELECT COUNT(*) AS c FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ?', [userId, utcDateStr(), actBossKind(eventId, bossNo, slot)]).catch(() => null);\n"
    "  return Math.max(0, Number(c && c.c) || 0);\n"
    "}\n"
    "async function actBossLastAt(userId: number, eventId: number, bossNo: number, slot: string): Promise<number> {\n"
    "  const r = await dbGet('SELECT COALESCE(MAX(created_at), 0) AS t FROM fun_daily WHERE player_id = ? AND kind = ?', [userId, actBossKind(eventId, bossNo, slot)]).catch(() => null);\n"
    "  return Math.max(0, Math.floor(Number(r && r.t) || 0));\n"
    "}\n"
)

EDITS = [
    ("E1 常量 + 收费上限/收费冷却", E1_OLD, E1_NEW),
    ("E2 DDL event_boss5（插在聚合索引前）", E2_ANCHOR, E2_BLOCK + E2_ANCHOR),
    ("E3 ensure 五槽位幂等建场（去顺序刷新）", E3_OLD, E3_NEW),
    ("E4 hitOnce 打指定槽位 + 聚合重算", E4_OLD, E4_NEW),
    ("E5 status 逐只回执 bosses[]", E5_OLD, E5_NEW),
    ("E6 strike 配额（逐只 5/日 + 冷却）", E6_OLD, E6_NEW),
    ("E7 strike fun_daily 逐只 kind", E7_OLD, E7_NEW),
    ("E8 strike 调 hitOnce(bossNo)", E8_OLD, E8_NEW),
    ("E9 strike 回执 bossNo", E9_OLD, E9_NEW),
    ("E10 talisman 配额（逐只 10/日 + 5min）", E10_OLD, E10_NEW),
    ("E11 talisman fun_daily 逐只 kind", E11_OLD, E11_NEW),
    ("E12 talisman 调 hitOnce(bossNo)", E12_OLD, E12_NEW),
    ("E13 talisman 回执 bossNo/paidCoolLeft", E13_OLD, E13_NEW),
    ("E14 逐只计数助手", E14_OLD, E14_NEW),
]

INSERTION_EDITS = {"E2 DDL event_boss5（插在聚合索引前）"}

# 前置依赖（只读，自证在位）
REQUIRES = [
    ("const ACT_BOSS_TALISMAN_DAILY = 2;", 1, "诛妖符常量在位（本环后不再作为闸门，常量保留）"),
    ("const ACT_BOSS_HP_CYCLE = 20;", 1, "血量期数系数在位"),
    ("const ACT_BOSS_TRUCE_MS = 2 * 24 * 60 * 60 * 1000;", 1, "休战期常量在位"),
    ("const safeAddColumn = (table: string, col: string, ddl: string) => {", 1, "幂等加列工具在位"),
    ("app.get('/api/eventboss/status'", 1, "状态端点在位"),
    ("app.post('/api/eventboss/strike'", 1, "出手端点在位"),
    ("app.post('/api/eventboss/talisman'", 1, "诛妖符端点在位"),
    ("async function actBossEnsure(eventId: number): Promise<any> {", 1, "lazy 建场函数在位"),
    ("UPDATE event_boss SET settled = 1, settled_at = ? WHERE event_id = ?", 1, "结算置位在位（本环不动）"),
    ("const price = await actHourlyOf(userId); // 符价=1×境界时薪", 1, "诛妖符定价在位（本环不动）"),
]

BASE_NEEDLES = ["res.status(403", "setInterval(", "require(", "PRAGMA",
                "ACT_BOSS_TALISMAN_DAILY", "ACT_BOSS_HP_CYCLE",
                "boss_raid:    { name: '万妖巢穴'",
                "UPDATE event_boss SET settled = 1, settled_at = ? WHERE event_id = ?"]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-113 万妖巢穴五只同现环")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
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
        # ---- 本环改动：常量 ----
        ("R113 免费 5 次/日/只", "const ACT_BOSS_FREE_STRIKES = 5;", 1),
        ("R113 收费上限 10", "const ACT_BOSS_PAID_LIMIT = 10;", 1),
        ("R113 收费冷却 5 分钟", "const ACT_BOSS_PAID_COOLDOWN_MS = 5 * 60 * 1000;", 1),
        ("R113 五只常量", "const ACT_BOSS_MAX_BOSSES = 5;", 1),
        ("R113 免费冷却 10 分钟保留", "const ACT_BOSS_STRIKE_COOLDOWN_MS = 10 * 60 * 1000;", 1),
        ("R113 血量成长常量保留", "const ACT_BOSS_HP_GROWTH = 0.5;", 1),
        # ---- DDL ----
        ("R113 event_boss5 建表", "CREATE TABLE IF NOT EXISTS event_boss5 (", 1),
        ("R113 复合主键", "PRIMARY KEY (event_id, boss_no)", 1),
        # ---- ensure ----
        ("R113 五槽位建场", "INSERT OR IGNORE INTO event_boss5 (event_id, boss_no, hp_max, hp_cur) VALUES (?, ?, ?, ?)", 1),
        ("R113 顺序刷新已移除(ensure)", "const nextNo = no0 + 1;", 0),
        ("R113 顺序刷新已移除(hitOnce)", "const nextR = noR + 1;", 0),
        ("R113 换boss归零已移除", "UPDATE event_boss_hits SET free_used = 0 WHERE event_id = ?", 0),
        # ---- hitOnce ----
        ("R113 hitOnce 带 bossNo", "eventId: number, bossNo: number, nowMs: number, isFree: boolean", 1),
        ("R113 扣血打 event_boss5", "UPDATE event_boss5 SET", 1),
        ("R113 聚合重算查询", "COALESCE(SUM(hp_max),0) AS hm, COALESCE(SUM(hp_cur),0) AS hc", 1),
        ("R113 五只全诛判定", "const allDead = Number(agg && agg.n) > 0", 1),
        ("R113 strike 调 hitOnce true", "hit = await actBossHitOnce(userId, Number(ev.id), bossNo, now, true);", 1),
        ("R113 talisman 调 hitOnce false", "hit = await actBossHitOnce(userId, Number(ev.id), bossNo, now, false);", 1),
        ("R113 旧调用形态已清零", "hit = await actBossHitOnce(userId, Number(ev.id), now,", 0),
        # ---- status ----
        ("R113 status 逐只数组", "const bosses: any[] = [];", 1),
        ("R113 status 读 5 槽位", "SELECT boss_no, hp_max, hp_cur, killed, killer_id FROM event_boss5 WHERE event_id = ? ORDER BY boss_no ASC", 1),
        ("R113 status 逐只免费剩余", "freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - fUsed),", 1),
        ("R113 status 逐只收费剩余", "paidLeft: Math.max(0, ACT_BOSS_PAID_LIMIT - pUsed),", 1),
        ("R113 status 免费冷却", "freeCoolLeft: fAt > 0 ?", 1),
        ("R113 status 收费冷却", "paidCoolLeft: pAt > 0 ?", 1),
        ("R113 status 回 freeLimit", "freeLimit: ACT_BOSS_FREE_STRIKES,", 1),
        ("R113 status 回 paidLimit", "paidLimit: ACT_BOSS_PAID_LIMIT,", 1),
        ("R113 status 回 bosses", "      bosses,", 1),
        # ---- strike ----
        ("R113 strike 逐只 5 次闸", "if (freeUsed >= ACT_BOSS_FREE_STRIKES) {", 1),
        ("R113 strike fun_daily 逐只 kind", "actBossKind(Number(ev.id), bossNo, 'f'), freeUsed + 1", 1),
        ("R113 strike 回 bossNo", "      bossNo,\n      freeLeft: Math.max(0, ACT_BOSS_FREE_STRIKES - freeUsed - 1),", 1),
        # ---- talisman ----
        ("R113 talisman 逐只 10 次闸", "if (used >= ACT_BOSS_PAID_LIMIT) {", 1),
        ("R113 talisman 收费冷却闸", "const paidCoolMs = paidLastAt > 0 ? ACT_BOSS_PAID_COOLDOWN_MS - (now - paidLastAt) : 0;", 1),
        ("R113 talisman fun_daily 逐只 kind", "actBossKind(Number(ev.id), bossNo, 'p'), used + 1", 1),
        ("R113 talisman 回 paidCoolLeft", "paidCoolLeft: ACT_BOSS_PAID_COOLDOWN_MS,", 1),
        ("R113 talisman 收费口径回执", "talismanLeft: Math.max(0, ACT_BOSS_PAID_LIMIT - used - 1),", 1),
        # ---- 助手 ----
        ("R113 逐只 kind 助手", "function actBossKind(eventId: number, bossNo: number, slot: string): string {", 1),
        ("R113 逐只计数助手", "async function actBossUsedToday(userId: number, eventId: number, bossNo: number, slot: string): Promise<number> {", 1),
        ("R113 逐只冷却助手", "async function actBossLastAt(userId: number, eventId: number, bossNo: number, slot: string): Promise<number> {", 1),
        # ---- 旧形态清零 ----
        ("R113 旧每日免费 409 清零", "本只妖兽的免费出手已用尽（${ACT_BOSS_FREE_STRIKES} 次）", 0),
        ("R113 旧每日符 409 清零", "今日诛妖符已用尽", 0),
        ("R113 旧单只状态查询清零", "SELECT score, strikes, free_used, last_strike_at FROM event_boss_hits", 0),
        # ---- 冻结：邻面一字不动 ----
        ("冻结 诛妖符常量保留", "const ACT_BOSS_TALISMAN_DAILY = 2;", 1),
        ("冻结 血量期数系数未动", "const ACT_BOSS_HP_CYCLE = 20;", 1),
        ("冻结 休战期未动", "const ACT_BOSS_TRUCE_MS = 2 * 24 * 60 * 60 * 1000;", 1),
        ("冻结 reward089 血量行恰 1", "const hp = Math.floor(WB_HP_BASE * mult * ACT_BOSS_HP_CYCLE);", 1),
        ("冻结 activity087 killed_at DDL 恰 1", "killed_at INTEGER", 1),
        ("冻结 结算置位未动", "UPDATE event_boss SET settled = 1, settled_at = ? WHERE event_id = ?", 1),
        ("冻结 三端点仍在", "app.post('/api/eventboss/talisman'", 1),
        ("冻结 冲榜结算器未动", "async function actSettleRankBoard", 1),
        ("冻结 榜单仍读聚合表", "SELECT user_id AS uid, score, strikes FROM event_boss_hits WHERE event_id = ? ORDER BY score DESC", 1),
        # ---- 红线 ----
        ("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]),
        ("红线 未新增 require(", "require(", base["require("]),
        ("红线 未新增 setInterval", "setInterval(", base["setInterval("]),
        ("红线 未新增 PRAGMA", "PRAGMA", base["PRAGMA"]),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-44s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 7) 语义自证：引用计数闭合
    # actBossKind 引用：定义 1 + actBossUsedToday 1 + actBossLastAt 1 + strike 插入 1 + talisman 插入 1 = 5
    # FREE/PAID 各 6 = 定义 + status 回执上限 + status 逐只剩余 + 端点闸门 + 端点 409 文案 + 端点回执
    sem_ok = (
        out.count("ACT_BOSS_PAID_LIMIT") == 6
        and out.count("ACT_BOSS_PAID_COOLDOWN_MS") == 4  # 定义 + status paidCoolLeft + talis 闸 + talis 回执
        and out.count("ACT_BOSS_FREE_STRIKES") == 6
        and out.count("actBossKind(") == 5
    )
    ok = ok and sem_ok
    print("  [%s] %-44s PAID=%d PCD=%d FREE=%d KIND=%d"
          % ("OK" if sem_ok else "FAIL", "R113 语义自证(引用计数闭合)",
             out.count("ACT_BOSS_PAID_LIMIT"), out.count("ACT_BOSS_PAID_COOLDOWN_MS"),
             out.count("ACT_BOSS_FREE_STRIKES"), out.count("actBossKind(")))

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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r113boss-", suffix=".tmp")
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
