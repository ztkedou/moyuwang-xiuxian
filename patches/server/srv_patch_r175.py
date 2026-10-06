# -*- coding: utf-8 -*-
r"""
srv_patch_r175.py -- R-175 万妖巢穴·五只同现：排行榜「每一只单独计算」（服务端 · SRV_CHAIN 第 78 环 / 新末环）

  ★ 环号说明：第 77 环 = R-173（srv_patch_r173.py，[r173offline]）⇒ 本环顺延 **第 78 环**。
    锚点全部落在「万妖巢穴 boss 段」：event_boss5 建表块 / actBossHitOnce 记分块 /
    GET /api/eventboss/status 的排行榜查询与响应对象。与 r173（离线/鉴权/saves 建列）、
    r165（悟道）、r160/r163 锚区零交集。链序无硬约束，排 r173 之后即可（REQUIRES 强制）。

台账原文（R-175，逐字）
--------------------------------------------------------------------------
  「万妖巢穴 · 五只同现  下面的排行榜计算，应该每一只单独计算，而不是算合计的攻击伤害」

改前取证（srv/index_v28.ts 字符级实测）
--------------------------------------------------------------------------
  [证据 1] 记分口径（actBossHitOnce @9887-9891）——**五只合计**：
      // 记分（PK 幂等 upsert；跨 5 只累计到 event_boss_hits ⇒ 结算档位/榜单口径与单 boss 时代一致）
      INSERT INTO event_boss_hits (event_id, user_id, score, strikes) VALUES (?, ?, ?, 1)
      ON CONFLICT(event_id, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1
    event_boss_hits 建表 PK = (event_id, user_id)（@1128-1136）⇒ **没有 boss_no 维度**，
    玩家对 5 只 boss 的伤害被累加成**一份总分**，无法拆出「每只各打多少」。

  [证据 2] 排行榜查询（GET /api/eventboss/status @9916-9919）——**合计总榜**：
      SELECT h.user_id AS uid, h.score, COALESCE(NULLIF(r.name, ''), u.username) AS name
      FROM event_boss_hits h JOIN users u ON u.id = h.user_id LEFT JOIN rankings r ON r.user_id = h.user_id
      WHERE h.event_id = ? ORDER BY h.score DESC LIMIT 10
    ⇒ 一锅端：把 5 只的伤害合计成一个榜（正是台账要改的「算合计的攻击伤害」）。

  [证据 3] 响应结构（@9944-9962）：排行榜字段 = `top10`（[{userId,name,score,rank}]，LIMIT 10）；
    客户端 YlxwTActBoss 消费 status.top10 渲染单张榜。

  [证据 4] 结算（actSettleLoop @10180-10182）也用 event_boss_hits 合计榜发档位/排名奖 ——
    **本环一行未动**（台账只提「排行榜计算」，未涉及结算奖励口径；动它会改奖励发放，超出范围）。

改法（1 建表 + 1 记分 + 1 查询 + 1 响应字段 + 1 销号登记）
--------------------------------------------------------------------------
  · 新表 event_boss_hits5(event_id, boss_no, user_id, score, strikes)，PK=(event_id,boss_no,user_id)：
    逐只伤害数据源。**幂等 CREATE TABLE IF NOT EXISTS**（不新增 PRAGMA）。
    ★ 为何必须建表：现有数据模型里**不存在**任何逐只伤害记录（event_boss_hits 只有合计；
      event_boss5 只有血量/击杀者；fun_daily 只有次数）。不落一份逐只记分，就无法「每只单独计算」。
      这是唯一可行且最小的口径补齐；不新增列、不改既有表结构、不动 event_boss_hits 语义。

  · actBossHitOnce 在既有合计 upsert **之后**并行落一行逐只记分（同一 score、同一次出手）：
      INSERT INTO event_boss_hits5 (event_id, boss_no, user_id, score, strikes) VALUES (?,?,?,?,1)
      ON CONFLICT(event_id, boss_no, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1
    ⇒ event_boss_hits（合计）与结算档位/排名奖励口径**逐位不变**；仅**新增**一条旁路记分。

  · GET /api/eventboss/status：按 5 只槽位各查一份榜（各按**该只** score DESC，同分 user_id ASC 稳定排序，
    LIMIT 10 沿用现状），装进新字段 `top10ByBoss: [{ no, top10:[...] }, ...]`。

  · R-039 账号删除清单登记：新表 event_boss_hits5 含 user_id 列 ⇒ 必须登记进
    `R039_SINGLE`（销号整行删除），否则销号后残留孤儿行（低危脏数据）。紧跟兄弟表
    `['event_boss_hits', 'user_id'],` 之后逐字同构追加 `['event_boss_hits5', 'user_id'],`。

  · ★ 响应结构（向后兼容）：
      - `top10`（合计总榜）**语义与内容逐位保留** ⇒ 老客户端零改动仍可渲染（不崩）。
      - **新增** `top10ByBoss` ⇒ 客户端改为按只渲染即可（见下「客户端是否必须跟着改」）。
    ⇒ 服务端先向后兼容上线；客户端切换渲染是后续派单，不在本环。

  ★ 红线（一行未动）：actBossHitOnce 的扣血/合计记分/聚合行重算、strike/talisman 入账与扣费口径、
    event_boss_hits 表结构与 PK、结算（档位/排名/诛妖/全服）奖励发放口径、ACT_BOSS_* 常量、
    event_boss5 建表、actBossEnsure、LIMIT 10。既有合计榜查询（top）与结算查询原样保留。

客户端是否必须跟着改
--------------------------------------------------------------------------
  · 服务端本环**已向后兼容**：老客户端读 `top10`（合计）不报错，但**仍是合计榜**（未满足 R-175 观感）。
  · 要真正呈现「每只单独计算」，客户端需把榜单渲染从 `status.top10` 换成 `status.top10ByBoss`
    （数组，每项 { no, top10 }），逐只渲染/切换（例如 5 个 tab 或 5 段列表）。
    ★ 具体函数名在客户端 bundle（YlxwTActBoss 系列）中，**本环不改客户端**，由主对话派单定位。

过渡态说明：补丁上线前已开活动的 event_boss_hits5 无历史行 ⇒ 逐只榜初始为空（合计榜仍有值）；
  记分从上线后**逐次累积**。如需回填需另立数据迁移（超出本环范围，未做）。

CLI 契约（照 srv_patch_r173.py / srv_patch_r165.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r175-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r175boss] 则 SKIP（直接返回 rc=0，不写盘）。
  退出码：0=成功/跳过；1=契约/门禁失败；2=意外异常（IO/写回）。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII；替换 expect=1；门禁全绿 + round-trip 正反双向自证后才原子写回。
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（写进替换新增的独立注释行；TS 源码 ⇒ 用 //）
MARK = "[r175boss]"

# ============================================================ 改动点（4 处）

# ── A. 建逐只记分表（紧接 event_boss5 建表块之后；幂等，不新增 PRAGMA）────────────────────
A_OLD = (
    "    PRIMARY KEY (event_id, boss_no)\n"
    "  )`);\n"
)
A_NEW = (
    "    PRIMARY KEY (event_id, boss_no)\n"
    "  )`);\n"
    "  // [r175boss] R-175 万妖巢穴·五只同现：逐只讨伐榜数据源。\n"
    "  //   既有 event_boss_hits 的 PK 是 (event_id, user_id) ⇒ 五只伤害被**合计**成一份，\n"
    "  //   无法支撑「每一只单独计算」。本表按 (event_id, boss_no, user_id) 记录**逐只**伤害，\n"
    "  //   仅服务 GET /api/eventboss/status 的逐只榜；结算（event_boss_hits）口径一行未动。\n"
    "  //   幂等建表（IF NOT EXISTS），不新增任何库表探测语句。\n"
    "  db.run(`CREATE TABLE IF NOT EXISTS event_boss_hits5 (\n"
    "    event_id INTEGER NOT NULL,\n"
    "    boss_no INTEGER NOT NULL,\n"
    "    user_id INTEGER NOT NULL,\n"
    "    score INTEGER NOT NULL DEFAULT 0,\n"
    "    strikes INTEGER NOT NULL DEFAULT 0,\n"
    "    PRIMARY KEY (event_id, boss_no, user_id),\n"
    "    FOREIGN KEY (user_id) REFERENCES users (id)\n"
    "  )`);\n"
)

# ── B. 逐只记分（actBossHitOnce：既有合计 upsert 之后并行落一行）────────────────────────
B_OLD = (
    "  await dbRun(\n"
    "    `INSERT INTO event_boss_hits (event_id, user_id, score, strikes) VALUES (?, ?, ?, 1)\n"
    "     ON CONFLICT(event_id, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1`,\n"
    "    [eventId, userId, score]);\n"
)
B_NEW = (
    "  await dbRun(\n"
    "    `INSERT INTO event_boss_hits (event_id, user_id, score, strikes) VALUES (?, ?, ?, 1)\n"
    "     ON CONFLICT(event_id, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1`,\n"
    "    [eventId, userId, score]);\n"
    "  // [r175boss] R-175：逐只伤害落 event_boss_hits5（PK 幂等 upsert；与上面的合计行**并行**，\n"
    "  //   同一 score / 同一次出手；不改 event_boss_hits 的入账口径 ⇒ 结算档位/排名奖励口径逐位不变）。\n"
    "  await dbRun(\n"
    "    `INSERT INTO event_boss_hits5 (event_id, boss_no, user_id, score, strikes) VALUES (?, ?, ?, ?, 1)\n"
    "     ON CONFLICT(event_id, boss_no, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1`,\n"
    "    [eventId, bossNo, userId, score]);\n"
)

# ── C. status handler：逐只查榜（插在响应组装之前，逐只按该只 score DESC / user_id ASC）──────
C_OLD = (
    "        paidCoolLeft: pAt > 0 ? Math.max(0, Math.ceil((ACT_BOSS_PAID_COOLDOWN_MS - (nowS - pAt)) / 1000)) : 0,\n"
    "      });\n"
    "    }\n"
    "    const killed = Number(boss.killed) === 1;\n"
)
C_NEW = (
    "        paidCoolLeft: pAt > 0 ? Math.max(0, Math.ceil((ACT_BOSS_PAID_COOLDOWN_MS - (nowS - pAt)) / 1000)) : 0,\n"
    "      });\n"
    "    }\n"
    "    // [r175boss] R-175：逐只榜——每一只 boss **单独计算**（该只 score DESC；同分 user_id ASC 稳定排序；\n"
    "    //   LIMIT 10 沿用现状）。数据源 = event_boss_hits5（逐只记分）；不再把 5 只伤害合计成一个榜。\n"
    "    const topByBoss: any[] = [];\n"
    "    for (const s of (slots || [])) {\n"
    "      const no = Math.max(1, Math.floor(Number(s.boss_no) || 1));\n"
    "      const list = await dbAll(\n"
    "        `SELECT h.user_id AS uid, h.score, COALESCE(NULLIF(r.name, ''), u.username) AS name\n"
    "         FROM event_boss_hits5 h JOIN users u ON u.id = h.user_id LEFT JOIN rankings r ON r.user_id = h.user_id\n"
    "         WHERE h.event_id = ? AND h.boss_no = ? ORDER BY h.score DESC, h.user_id ASC LIMIT 10`,\n"
    "        [Number(ev.id), no]).catch(() => []);\n"
    "      topByBoss.push({\n"
    "        no,\n"
    "        top10: (list || []).map((x: any, i: number) => ({ userId: Number(x.uid), name: String(x.name || ''), score: Math.max(0, Math.floor(Number(x.score) || 0)), rank: i + 1 })),\n"
    "      });\n"
    "    }\n"
    "    const killed = Number(boss.killed) === 1;\n"
)

# ── D. 响应：新增 top10ByBoss（合计榜 top10 原样保留 ⇒ 向后兼容）──────────────────────────
D_OLD = (
    "      top10: (top || []).map((x: any, i: number) => ({ userId: Number(x.uid), name: String(x.name || ''), score: Math.max(0, Math.floor(Number(x.score) || 0)), rank: i + 1 })),\n"
)
D_NEW = (
    "      top10: (top || []).map((x: any, i: number) => ({ userId: Number(x.uid), name: String(x.name || ''), score: Math.max(0, Math.floor(Number(x.score) || 0)), rank: i + 1 })),\n"
    "      // [r175boss] R-175：逐只榜（每项 { no, top10 }）。★ top10（合计）为向后兼容原样保留；\n"
    "      //   客户端应改用本字段逐只渲染（见文件头「客户端是否必须跟着改」）。\n"
    "      top10ByBoss: topByBoss,\n"
)

# ── E. R-039 账号删除清单登记（新表含 user_id ⇒ 销号必须一并删，防孤儿行）────────────────
E_OLD = (
    "  ['social_scores', 'user_id'], ['worldboss_hits', 'user_id'], ['event_boss_hits', 'user_id'],\n"
)
E_NEW = (
    "  ['social_scores', 'user_id'], ['worldboss_hits', 'user_id'], ['event_boss_hits', 'user_id'], ['event_boss_hits5', 'user_id'],\n"
)

EDITS = [
    ("R175 逐只记分表 event_boss_hits5（幂等建表）", A_OLD, A_NEW),
    ("R175 逐只记分（actBossHitOnce 并行落行）", B_OLD, B_NEW),
    ("R175 逐只查榜（status handler）", C_OLD, C_NEW),
    ("R175 响应新增 top10ByBoss（top10 保留）", D_OLD, D_NEW),
    ("R175 R-039 销号清单登记 event_boss_hits5", E_OLD, E_NEW),
]

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("CREATE TABLE IF NOT EXISTS event_boss5 (", "==", 1,
     "五只槽位建表必须在位（本环插入锚点，紧跟其后）"),
    ("async function actBossHitOnce(", "==", 1,
     "出手公共体必须在位（本环并行加逐只记分，不动既有口径）"),
    ("app.get('/api/eventboss/status', authenticateToken", "==", 1,
     "排行榜所在 handler 必须在位（本环改其排行榜计算与响应）"),
    ("INSERT INTO event_boss_hits (event_id, user_id, score, strikes) VALUES (?, ?, ?, 1)", "==", 1,
     "既有合计记分必须在位（本环一行未动，仅在其后并行加逐只行）"),
    ("const ACT_BOSS_MAX_BOSSES", "==", 1,
     "五只上限常量必须在位（本环只读）"),
    ("['event_boss_hits', 'user_id'],", "==", 1,
     "R-039 销号清单必须在位（本环登记新表 event_boss_hits5）"),
    ("[r173offline]", ">=", 1,
     "R-173 环必须已应用（链序约束：本环排在第 77 环之后 = 新末环）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 既有合计榜 / 结算口径（本环一行未动）
    "INSERT INTO event_boss_hits (event_id, user_id, score, strikes) VALUES (?, ?, ?, 1)",
    "ON CONFLICT(event_id, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1",
    "FROM event_boss_hits h JOIN users u ON u.id = h.user_id LEFT JOIN rankings r ON r.user_id = h.user_id",
    "WHERE h.event_id = ? ORDER BY h.score DESC LIMIT 10",
    "'SELECT user_id AS uid, score, strikes FROM event_boss_hits WHERE event_id = ? ORDER BY score DESC, user_id ASC',",
    # 端点在位
    "app.post('/api/eventboss/strike', authenticateToken",
    "app.post('/api/eventboss/talisman', authenticateToken",
    "app.get('/api/eventboss/status', authenticateToken",
    "async function actBossHitOnce(",
    "async function actBossEnsure(",
    "CREATE TABLE IF NOT EXISTS event_boss5 (",
    # R-039 销号清单（本环登记新表）
    "['event_boss_hits', 'user_id'],",
    # 工程红线（相对计数）
    "res.status(403",
    "setInterval(",
    "PRAGMA",
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out: str, base):
    """五元组 (label, needle, expect, op, note)；base = 冻结针脚在**基座**上的计数。"""
    g = [
        ("R175 幂等标记在位", MARK, 1, ">=", "本环已应用"),
        ("R175 逐只表 DDL", "CREATE TABLE IF NOT EXISTS event_boss_hits5 (", 1, "==", "逐只伤害数据源（幂等建表）"),
        ("R175 逐只表主键", "PRIMARY KEY (event_id, boss_no, user_id),", 1, "==", "(event_id,boss_no,user_id) 逐只维度"),
        ("R175 逐只记分 upsert", "INSERT INTO event_boss_hits5 (event_id, boss_no, user_id, score, strikes) VALUES (?, ?, ?, ?, 1)", 1, "==", "并行落逐只行"),
        ("R175 逐只记分冲突更新", "ON CONFLICT(event_id, boss_no, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1", 1, "==", "PK 幂等累加"),
        ("R175 逐只榜查询数据源", "FROM event_boss_hits5 h JOIN users u ON u.id = h.user_id", 1, "==", "按只查榜"),
        ("R175 逐只榜稳定排序", "WHERE h.event_id = ? AND h.boss_no = ? ORDER BY h.score DESC, h.user_id ASC LIMIT 10", 1, "==", "该只降序 + user_id 稳定序"),
        ("R175 逐只榜容器", "const topByBoss: any[] = [];", 1, "==", "逐只榜容器"),
        ("R175 逐只榜遍历槽位", "for (const s of (slots || [])) {", 2, "==", "bosses 循环 + 逐只榜循环"),
        ("R175 响应字段 top10ByBoss", "top10ByBoss: topByBoss,", 1, "==", "新增字段（top10 保留）"),
        ("R175 R-039 销号登记", "['event_boss_hits5', 'user_id'],", 1, "==", "新表含 user_id ⇒ 销号一并删（防孤儿行）"),
        # ── 冻结断言：既有合计榜 / 结算 / 端点 改动前后逐字一致 ──
        ("R175 冻结·合计记分仍在", "INSERT INTO event_boss_hits (event_id, user_id, score, strikes) VALUES (?, ?, ?, 1)", 1, "==", "入账口径未动"),
        ("R175 冻结·合计冲突更新仍在", "ON CONFLICT(event_id, user_id) DO UPDATE SET score = score + excluded.score, strikes = strikes + 1", 1, "==", "合计累加未动"),
        ("R175 冻结·合计总榜查询仍在", "FROM event_boss_hits h JOIN users u ON u.id = h.user_id LEFT JOIN rankings r ON r.user_id = h.user_id", 1, "==", "top10 数据源未动"),
        ("R175 冻结·合计总榜 LIMIT 10", "WHERE h.event_id = ? ORDER BY h.score DESC LIMIT 10", 1, "==", "top10 查询未动"),
        ("R175 冻结·结算查询未动", "'SELECT user_id AS uid, score, strikes FROM event_boss_hits WHERE event_id = ? ORDER BY score DESC, user_id ASC',", 1, "==", "结算口径未动"),
        ("R175 冻结·strike 端点", "app.post('/api/eventboss/strike', authenticateToken", 1, "==", "未动"),
        ("R175 冻结·talisman 端点", "app.post('/api/eventboss/talisman', authenticateToken", 1, "==", "未动"),
        ("R175 冻结·status 端点", "app.get('/api/eventboss/status', authenticateToken", 1, "==", "未动"),
        ("R175 冻结·actBossHitOnce 签名", "async function actBossHitOnce(", 1, "==", "签名未动"),
        ("R175 冻结·event_boss5 建表", "CREATE TABLE IF NOT EXISTS event_boss5 (", 1, "==", "未动"),
        ("R175 冻结·event_boss_hits 销号登记仍在", "['event_boss_hits', 'user_id'],", 1, "==", "原登记行未动"),
        # ── 工程红线（相对计数）──
        ("R175 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403（客户端会强制登出）"),
        ("R175 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R175 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库（幂等建表，非 PRAGMA）"),
        ("R175 红线·无 require", "require(", 0, "==", "ESM 不新增 require"),
    ]
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-175 万妖巢穴逐只榜（服务端环）")
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
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:200]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线（每个针脚必须在基座真实存在，防针脚拼错导致「冻结」静默失效）
    base = {k: src.count(k) for k in BASE_NEEDLES}
    for k in BASE_NEEDLES:
        if base[k] <= 0:
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
        print("  [%s] %-46s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证：正向重放一致 + 逆向还原后除改动点外字节零变化
    ref = src
    for name, old, new in EDITS:
        ref = ref.replace(old, new, 1)
    if out != ref:
        fail("round-trip(正向重构) mismatch")
    back = out
    for name, old, new in EDITS:
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    for name, old, new in EDITS:
        if out.count(new) != 1:
            fail("round-trip：新增块出现次数 != 1（%s）" % name)

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r175-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r175boss-", suffix=".tmp")
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
    except BaseException as e:  # 意外异常（IO/写回）⇒ 退出码 2
        print("[ERROR] %s: %s" % (type(e).__name__, e))
        sys.exit(2)
