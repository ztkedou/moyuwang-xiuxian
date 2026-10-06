# -*- coding: utf-8 -*-
r"""
srv_patch_r167.py -- R-167 喂养「当日第 1 次免费」（服务端 · 接在 r165 之后）

台账原文（R-167，逐字）
--------------------------------------------------------------------------
  「仙务·妖灵 面板很多地方重复了，上面的今日互动不知道显示的什么内容，下面还有单独的
    "喂养"和"嬉戏"两个按钮。这两个应该归到前面的按钮，变成第一次免费。」

客户端半边（已完成，本环**不碰**）
--------------------------------------------------------------------------
  localtest/yl_r167_ext.py —— 删掉重复的「喂养 / 嬉戏」两个独立按钮 + 改自解释文案。
  本环只做服务端权威半边：**喂养当日第 1 次免灵石**。

改前取证（srv/index_v28.ts 字符级实测）
--------------------------------------------------------------------------
  · POST /api/pet/play  —— 已实现「每种（tease/brush/talk）每日 1 次免费」：
      闸门 = pet_play_log(PK(player_id,date)) 单语句原子 upsert，`WHERE <count> < 1` 才放行；
      changes=0 即拒绝（当日已用）。宠物行缺失时回退 times 占位（@13340-13343 补偿口径）。
  · POST /api/pet/feed  —— **没有任何每日免费额度**：每次按档恒扣费
      （R018_FEED_TIERS：common 3000 / fine 15000 / immortal 60000）。
  ⇒ 缺口：喂养侧缺「当日第 1 次免费」。本环补上（照抄 play 端点的原子闸门 + 补偿口径）。

改法（4 处插/改 + 1 处新表 + 1 处登记 + 1 处回显，共 11 个 EDITS）
--------------------------------------------------------------------------
  1) 新表 pet_feed_log(player_id,date,times) —— 照抄 pet_play_log 建表写法。
  2) 表清单 R039_SINGLE 登记 ['pet_feed_log','player_id']（GM 删玩家时清理）。
  3) POST /api/pet/feed 闸门（插在「余额预检」之前，即所有宠物/存档前置校验之后）：
       INSERT INTO pet_feed_log(player_id,date,times) VALUES(?,?,1)
         ON CONFLICT(player_id,date) DO UPDATE SET times = times + 1 WHERE times < 1
       ⇒ changes>0 = 本次真的插入/自增 = 当日第 1 次 ⇒ _feed.cost 置 0（免灵石）；
         changes=0 = 当日免费额度已用尽 ⇒ 按原 _feed.cost 正常扣费（扣费口径逐字不变）。
       ★ 失败补偿：余额不足 / 扣费失败 / 宠物行缺失 / 异常 —— 回退本次计数
         （UPDATE pet_feed_log SET times = MAX(0, times - 1) ...，与 play @13340-13343 同款）。
       ★ 顺序：先做全部宠物 + 存档前置校验，最后才动闸门计数；闸门后仅剩「余额相关」步骤，
         失败一律补偿回退。
       ★ _feed 改为**可变副本**：r018FeedTier() 返回 R018_FEED_TIERS 的共享引用，直接改 .cost
         会污染全局常量 ⇒ 必须复制（只复制 cost/hunger/name 三个字段，行为不变）。
  4) GET /api/pet 回显 feedQuota: { date, used, free }（free = used<1）。
     ★ 顶层**不含** balance（STONE_ECHO 中间件会补真实余额；自带 balance 会覆写玩家灵石）。

红线（一行未动）
--------------------------------------------------------------------------
  r018FeedTier / r018PlayKind / R018_FEED_TIERS / R018_PLAY_KINDS / pet_play_log 建表与闸门 /
  POST /api/pet/play 本体 / POST /api/pet/feed 的扣费口径（除「当日第 1 次免」外逐字不变）。

CLI 契约（照 srv_patch_r165.py / srv_patch_r163.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r167-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r167feed] 则 SKIP（直接返回 rc=0，不写盘）。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII；替换 expect=1；门禁全绿 + round-trip 自证后才原子写回。
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（写进各新增块的独立注释行；TS 源码 ⇒ 用 //）
MARK = "[r167feed]"

# ============================================================ 改动点（11 个 EDITS）

# ---- E1 新表 pet_feed_log（照抄 pet_play_log 建表写法） --------------------------------
E1_OLD = (
    "  db.run(`\n"
    "    CREATE TABLE IF NOT EXISTS pet_play_log (\n"
    "      player_id INTEGER NOT NULL,\n"
    "      date TEXT NOT NULL,\n"
    "      times INTEGER NOT NULL DEFAULT 0,\n"
    "      PRIMARY KEY (player_id, date),\n"
    "      FOREIGN KEY (player_id) REFERENCES users (id)\n"
    "    )\n"
    "  `);"
)
E1_NEW = (
    E1_OLD + "\n"
    "  // [r167feed] R-167：pet_feed_log——每日喂养免费额度（UNIQUE(player_id,date)=PK 单语句原子 upsert，times<1 才放行当日首次免费）\n"
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

# ---- E2 表清单登记（GM 删玩家清理用） -------------------------------------------------
E2_OLD = "['pet_spirit_exped', 'player_id'], ['pet_play_log', 'player_id'],"
E2_NEW = "['pet_spirit_exped', 'player_id'], ['pet_play_log', 'player_id'], ['pet_feed_log', 'player_id'],"

# ---- E3 feed handler 请求级状态（提到 try 外 ⇒ catch 兜底补偿可见） --------------------
E3_OLD = (
    "app.post('/api/pet/feed', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `pet:feed:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {\n"
    "  const userId = req.user.id;"
)
E3_NEW = (
    E3_OLD + "\n"
    "  // [r167feed] R-167 喂养「当日首次免费」请求级状态（提到 try 外 ⇒ catch 兜底补偿可见）：\n"
    "  //   _feedFree = 本次是否命中免费（闸门 changes>0）；_feedDate = 闸门日期键；\n"
    "  //   _feedDone = 喂养是否已成功落库（异常兜底据此判断是否还需回退免费额度）。\n"
    "  let _feedFree = false;\n"
    "  let _feedDate = '';\n"
    "  let _feedDone = false;"
)

# ---- E4 _feed 改为可变副本（防污染 R018_FEED_TIERS 共享引用） --------------------------
E4_OLD = "    const _feed = r018FeedTier(req.body?.tier);"
E4_NEW = (
    "    // [r167feed] 复制一份**可变**档位：r018FeedTier 返回的是 R018_FEED_TIERS 的共享引用，\n"
    "    //   直接改 .cost 会污染全局常量 ⇒ 必须复制；仅当「当日首次免费」时把 _feed.cost 置 0。\n"
    "    const _feedTier = r018FeedTier(req.body?.tier);\n"
    "    const _feed = { cost: _feedTier.cost, hunger: _feedTier.hunger, name: _feedTier.name };"
)

# ---- E5 闸门（插在「余额预检」之前 = 所有宠物/存档前置校验之后） ------------------------
E5_OLD = "    if (bal < _feed.cost)"
E5_NEW = (
    "    // [r167feed] R-167 喂养「当日第 1 次免费」单语句原子闸门（照抄 play 端点 pet_play_log 口径）：\n"
    "    //   INSERT ... ON CONFLICT DO UPDATE SET times = times + 1 WHERE times < 1\n"
    "    //   ⇒ changes > 0 = 本次真的插入/自增 = 当日第 1 次 ⇒ 免灵石（_feed.cost 置 0）；\n"
    "    //     changes = 0 = 当日免费额度已用尽 ⇒ 按 _feed.cost 正常扣费（原扣费口径逐字不变）。\n"
    "    //   ★ 失败补偿：后续任一环节失败（余额不足 / 扣费失败 / 宠物行缺失 / 异常）回退本次计数，\n"
    "    //     避免玩家白占一次免费额度（与 play 端点 @13340-13343 同款补偿口径）。\n"
    "    _feedDate = petDate(Date.now());\n"
    "    const _feedGate = await dbRun(\n"
    "      'INSERT INTO pet_feed_log (player_id, date, times) VALUES (?, ?, 1) ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1 WHERE times < 1',\n"
    "      [userId, _feedDate]\n"
    "    );\n"
    "    _feedFree = _feedGate.changes > 0;\n"
    "    if (_feedFree) _feed.cost = 0;\n"
    "    const _feedRollback = async (): Promise<void> => {\n"
    "      if (!_feedFree || _feedDone) return; // 未占用 or 已成功 ⇒ 无需回退（幂等）\n"
    "      _feedFree = false;                    // 至多回退一次\n"
    "      await dbRun('UPDATE pet_feed_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?', [userId, _feedDate]);\n"
    "    };\n"
    "    if (bal < _feed.cost)"
)

# ---- E6 扣费失败补偿（照抄 play 的 saveLock 二次校验失败补偿） -------------------------
E6_OLD = (
    "    const paid = await updatePlayerSave(userId, (sd: any) => {\n"
    "      const b = Number(sd.player?.spiritStones) || 0;\n"
    "      if (b < _feed.cost) { short = true; return; }\n"
    "      sd.player.spiritStones = b - _feed.cost;\n"
    "    });\n"
    "    if (!paid.ok || short) {"
)
E6_NEW = (
    E6_OLD + "\n"
    "      await _feedRollback(); // [r167feed] 扣费失败 ⇒ 回退本次免费额度占位"
)

# ---- E7 成功落定标记（异常兜底据此不再回退） ------------------------------------------
E7_OLD = "    let fresh = await dbGet('SELECT name, rarity, hunger, exp, bond, aptitude, merged FROM pets WHERE player_id = ?', [userId]);"
E7_NEW = (
    "    _feedDone = true; // [r167feed] 喂养已成功落库 ⇒ 后续异常不再回退免费额度\n"
    + E7_OLD
)

# ---- E8 宠物行缺失补偿（先回退闸门占位，再退费；退费按 _feed.cost=0 自然为 0） ---------
E8_OLD = "      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + _feed.cost; });"
E8_NEW = (
    "      await _feedRollback(); // [r167feed] 宠物行缺失（理论不可达）⇒ 回退本次免费额度占位\n"
    + E8_OLD
)

# ---- E9 异常兜底回退（catch 内联，与 _feedRollback 同款 SQL） --------------------------
E9_OLD = "    console.error('pet feed error:', e?.message || e);"
E9_NEW = (
    "    if (_feedFree && !_feedDone) { _feedFree = false; try { await dbRun('UPDATE pet_feed_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?', [userId, _feedDate]); } catch {} } // [r167feed] 异常兜底：回退未落库成功的免费额度\n"
    + E9_OLD
)

# ---- E10 GET /api/pet 查询源（新增 pet_feed_log 当日行） ------------------------------
E10_OLD = (
    "    const [play, logs, exped] = await Promise.all([\n"
    "      dbGet('SELECT times, tease, brush, talk, bought FROM pet_play_log WHERE player_id = ? AND date = ?', [userId, today]),"
)
E10_NEW = (
    "    const [play, feed, logs, exped] = await Promise.all([\n"
    "      dbGet('SELECT times, tease, brush, talk, bought FROM pet_play_log WHERE player_id = ? AND date = ?', [userId, today]),\n"
    "      // [r167feed] R-167：喂养当日免费额度回显源（pet_feed_log 当日 times）\n"
    "      dbGet('SELECT times FROM pet_feed_log WHERE player_id = ? AND date = ?', [userId, today]),"
)

# ---- E11 GET /api/pet 回显 feedQuota ------------------------------------------------
E11_OLD = (
    "        bought: Math.min(R018_BUY_DAILY_MAX, Number(play?.bought) || 0),\n"
    "      },"
)
E11_NEW = (
    E11_OLD + "\n"
    "      // [r167feed] R-167：喂养当日额度（date=日期键；used=当日已用免费次数 0/1；free=used<1 ⇒ 今日首次喂养仍免费）\n"
    "      //   ★ 顶层不新增余额字段（STONE_ECHO 会补真实余额；自带余额字段会覆写玩家灵石）。\n"
    "      feedQuota: {\n"
    "        date: today,\n"
    "        used: Math.min(1, Number(feed?.times) || 0),\n"
    "        free: (Number(feed?.times) || 0) < 1,\n"
    "      },"
)

EDITS = [
    ("R167 新表 pet_feed_log 建表", E1_OLD, E1_NEW),
    ("R167 表清单登记 ['pet_feed_log','player_id']", E2_OLD, E2_NEW),
    ("R167 feed 请求级状态（try 外声明）", E3_OLD, E3_NEW),
    ("R167 _feed 可变副本（防污染全局档位表）", E4_OLD, E4_NEW),
    ("R167 喂养当日首次免费闸门 + 回退闭包", E5_OLD, E5_NEW),
    ("R167 扣费失败补偿", E6_OLD, E6_NEW),
    ("R167 成功落定标记", E7_OLD, E7_NEW),
    ("R167 宠物行缺失补偿", E8_OLD, E8_NEW),
    ("R167 异常兜底回退", E9_OLD, E9_NEW),
    ("R167 GET /api/pet 查询源", E10_OLD, E10_NEW),
    ("R167 GET /api/pet 回显 feedQuota", E11_OLD, E11_NEW),
]

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("function r018FeedTier(", "==", 1,
     "喂养档位函数必须在位（本环只读 cost/hunger/name）"),
    ("const R018_FEED_TIERS", "==", 1,
     "档位表必须在位（common 3000 / fine 15000 / immortal 60000；本环不改）"),
    ("function r018PlayKind(", "==", 1,
     "互动种类函数必须在位（本环一行未动）"),
    ("INSERT INTO pet_play_log (player_id, date, times, bought) VALUES (?, ?, 1, 1)", "==", 1,
     "play 买额度闸门必须在位（本环照抄其单语句原子口径）"),
    ("CREATE TABLE IF NOT EXISTS pet_play_log (", "==", 1,
     "play 建表必须在位（本环照抄其写法新建 pet_feed_log）"),
    ("['pet_play_log', 'player_id'],", "==", 1,
     "play 表清单登记必须在位（本环照同方式加 pet_feed_log）"),
    ("app.post('/api/pet/play', authenticateToken", "==", 1,
     "play 端点必须在位（本环照抄其每日免费额度 + 补偿口径）"),
    ("app.post('/api/pet/feed', authenticateToken", "==", 1,
     "插入锚点：feed 路由行必须恰好 1 次"),
    ("app.get('/api/pet', authenticateToken", "==", 1,
     "GET /api/pet 必须在位（本环在此回显 feedQuota）"),
    ("function updatePlayerSave(", "==", 1,
     "扣费唯一入口必须在位（本环复用，不新写）"),
    ("function dbRun(", "==", 1,
     "dbRun 必须在位（返回 {lastID, changes}，闸门据此判定首次免费）"),
    ("function petDate(", "==", 1,
     "日期键换算必须在位（与 play 同口径）"),
    ("[r165wudao]", ">=", 1,
     "r165 环必须已应用（链序约束：本环排在 r165 之后）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 喂养核心（本环除「当日首次免」外一行未动）
    "const PET_HUNGER_PER_FEED = 30;",
    "const PET_HUNGER_MAX = 9999;",
    "function r018FeedTier(",
    "function r018PlayKind(",
    # play 侧（本环一行未动）
    "CREATE TABLE IF NOT EXISTS pet_play_log (",
    "INSERT INTO pet_play_log (player_id, date, times, bought) VALUES (?, ?, 1, 1)",
    "app.post('/api/pet/play', authenticateToken",
    # feed 端点仍在 + feed 响应逐字未变（防误加 balance）
    "app.post('/api/pet/feed', authenticateToken",
    "res.json({ ok: true, pet: petView(fresh), battleReached, milestones: _miles, spirit: await r018SpiritSync(userId) });",
    "app.get('/api/pet', authenticateToken",
    # 工程红线（冻结：相对基座计数必须持平）
    "res.status(403",
    "setInterval(",
    "PRAGMA",
    "require(",
    "balance",
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out: str, base):
    """五元组 (label, needle, expect, op, note)；base = 冻结针脚在**基座**上的计数。"""
    g = [
        ("R167 幂等标记在位", MARK, 1, ">=", "本环已应用"),
        ("R167 新表 pet_feed_log 建表", "CREATE TABLE IF NOT EXISTS pet_feed_log (", 1, "==", "照抄 pet_play_log 写法"),
        ("R167 表清单登记", "['pet_feed_log', 'player_id'],", 1, "==", "GM 删玩家清理"),
        ("R167 闸门 SQL（单语句原子）", "ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1 WHERE times < 1", 1, "==", "WHERE times<1 保证当日只放行 1 次"),
        ("R167 回退 SQL（幂等补偿 ×2）", "UPDATE pet_feed_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?", 2, "==", "闭包 + catch 内联"),
        ("R167 首次免费置 0", "if (_feedFree) _feed.cost = 0;", 1, "==", "免则 cost=0"),
        ("R167 补偿调用（扣费失败/宠物行缺失）", "await _feedRollback(); // [r167feed]", 2, "==", "两处失败补偿"),
        ("R167 成功落定标记", "_feedDone = true; // [r167feed]", 1, "==", "落库后不再回退"),
        ("R167 异常兜底回退", "if (_feedFree && !_feedDone)", 1, "==", "catch 兜底"),
        ("R167 回显 feedQuota", "feedQuota: {", 1, "==", "GET /api/pet"),
        ("R167 回显查询 pet_feed_log", "dbGet('SELECT times FROM pet_feed_log WHERE player_id = ? AND date = ?', [userId, today]),", 1, "==", "当日 times 源"),
        ("R167 旧常量未动·HUNGER_PER_FEED", "const PET_HUNGER_PER_FEED = 30;", 1, "==", "冻结"),
        ("R167 旧常量未动·HUNGER_MAX", "const PET_HUNGER_MAX = 9999;", 1, "==", "冻结"),
        ("R167 r018FeedTier 未动", "function r018FeedTier(", 1, "==", "冻结"),
        ("R167 r018PlayKind 未动", "function r018PlayKind(", 1, "==", "冻结"),
        ("R167 play 闸门未动", "INSERT INTO pet_play_log (player_id, date, times, bought) VALUES (?, ?, 1, 1)", 1, "==", "冻结"),
        ("R167 pet_play_log 建表未动", "CREATE TABLE IF NOT EXISTS pet_play_log (", 1, "==", "冻结"),
        ("R167 play 端点未动", "app.post('/api/pet/play', authenticateToken", 1, "==", "冻结"),
        ("R167 feed 端点仍在", "app.post('/api/pet/feed', authenticateToken", 1, "==", "冻结"),
        ("R167 feed 响应逐字未变", "res.json({ ok: true, pet: petView(fresh), battleReached, milestones: _miles, spirit: await r018SpiritSync(userId) });", 1, "==", "防误加 balance"),
        ("R167 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403（客户端会强制登出）"),
        ("R167 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R167 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        ("R167 红线·无新 require", "require(", base["require("], "==", "ESM ⇒ 不新增 require("),
        ("R167 红线·无新增 balance", "balance", base["balance"], "==", "不新增 balance（STONE_ECHO 补真实余额）"),
    ]
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-167 喂养当日第 1 次免费（服务端环）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：产物含标记则 SKIP（直接返回，不写盘，rc=0）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖（绝对在位）
    for needle, op, cnt, why in REQUIRES:
        n = src.count(needle)
        good = (n == cnt) if op == "==" else (n >= cnt)
        if not good:
            fail("依赖未满足（%r 出现 %d 次，期望 %s %d）：%s" % (needle[:80], n, op, cnt, why))

    # 3) 锚点计数（纯 ASCII，必须恰好 1）
    for name, old, new in EDITS:
        if not all(ord(c) < 128 for c in old):
            fail("%s 锚点含非 ASCII 字符（违反工程约束）" % name)
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:200]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线（每个针脚必须在基座真实存在，防针脚拼错导致「冻结」静默失效）
    base = {k: src.count(k) for k in BASE_NEEDLES}
    for k in BASE_NEEDLES:
        if base[k] <= 0 and k != "require(":  # require( 合法基线 = 0（ESM 红线）
            fail("冻结针脚在基座不存在（拼写错误？）：%r" % k[:90])

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁（五元组，op 支持 == / >=）
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-48s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证：逆向逐个撤销，必须逐字节还原为 src（除改动点外零变化）
    rev = out
    for name, old, new in reversed(EDITS):
        if rev.count(new) != 1:
            fail("round-trip：%s 的 NEW 出现次数 != 1" % name)
        rev = rev.replace(new, old, 1)
    if rev != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    # 正向：每个 NEW 必须恰好 1 次（防替换未生效 / 意外重复）
    for name, old, new in EDITS:
        if out.count(new) != 1:
            fail("round-trip(正向)：%s 的 NEW 出现次数 != 1" % name)

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r167-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r167feed-", suffix=".tmp")
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
