# -*- coding: utf-8 -*-
r"""
srv_patch_057.py -- R-057 奇遇抽奖经济重做（服务端半边 · SRV_CHAIN 第 23 环）

需求原文（需求台账_进行中.md R-057）
--------------------------------------------------------------------------
  「奇遇抽奖变成消耗修为抽取，冷却时间30分钟，每日最多10次。获得的灵石数量大幅提升，
    这个也作为主要的灵石来源活动。并且抽奖时还有几率暴击，暴击获得双倍。」

改动总览（全部在 srv/index_v28.ts 的 adventure 面，锚区已实测各 count==1）
--------------------------------------------------------------------------
  E1  常量区：ADVENTURE_DAILY_MAX 3→10；新增 冷却 30 分钟 / 消耗修为 5% 槽 / 暴击 15% 三常量
  E2~E5  ADVENTURE_TIERS 四档灵石区间 ×30（expRate / weight / tickets / bonus 全不动）：
        白 80~180→2400~5400 · 蓝 250~550→7500~16500 · 紫 700~1600→21000~48000 · 金 1800~4200→54000~126000
        期望 ≈ 8040/抽 ×1.15(暴击) ≈ 9246 ≈ 灵石缩放方案锚点 8,838@筑基 ×1.05（「主要灵石来源」定标）
  E6  adventures 表迁移守卫：safeAddColumn 加 drawn_at INTEGER DEFAULT 0（冷却基准，老行 0 不触发）
  E7~E9 /api/adventure/list：Promise.all 加查 MAX(drawn_at)，响应加 cdLeft（毫秒）
  E10a /api/adventure/draw：每日上限检查后加 30 分钟冷却检查（409 文案带剩余秒数）
  E10b 存档解析后加修为消耗检查：cost = max(1, floor(当层修为槽 × 0.05))，不足 409「修为不足」
  E11 抽取体：crit = Math.random() < 0.15；灵石 funRandInt(...) × (crit ? 2 : 1)
  E12 INSERT 加 drawn_at = Date.now()（冷却基准落库）
  E13 收益回调（锁内）：先扣 costNow（同式重算，不足置 short → 外层补偿删行，全或无），
      再按扣后余量算 expGain；暴击 ×2 后二次钳槽内不溢出；灵石已含暴击（E11 在 INSERT 前算好，账本一致）
  E14 响应加 crit / cost（客户端 toast「⚡暴击×2！」「修为-cost」的数据源）

设计依据（为什么这么定档）
--------------------------------------------------------------------------
  · §22.8 全或无顺序契约：占位 INSERT → 扣费+收益（同一 updatePlayerSave 回调）→ 失败补偿删行，
    与既有 adventure/alchemy 结构一致；本环把扣费放进既有回调，不新增第二步写档。
    顺序契约做成门禁：片段内 idx(MAX(drawn_at)) < idx(INSERT INTO adventures) < idx(updatePlayerSave(userId)。
  · §22.6 EV 红线的适用性：本玩法非赌局对冲（茶馆那类赔率盘），是「修为换灵石」的产出活动；
    硬顶 = 每日 10 次 + 冷却 30 分钟，非无限 faucet。修为侧净耗 ≈ 4.6% 槽/抽
    （5% 消耗 − 期望回补 ~0.36%：四档 expRate 加权均值 0.316%，15% 暴击 ×1.15）；
    ⇒ 每日 10 次最多消耗一层修为槽约 46%，不会抽干一层（有真实代价，非无限刷）。
  · §11.4 经济上限：收益走服务端 updatePlayerSave 直写入档（gm_revision++ 促客户端拉档），
    不经过 /api/save 的 settleSaveEconV2 逐类配额 ⇒ 无需动 E2 配额常量。
  · 客户端半边 = yl_057_ext.py（V28_MODULES）：冷却禁用/标题倒计时/说明行/toast 暴击与消耗显示。

CLI 契约（与链上其余补丁一致，照 srv_patch_050.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` / `--selftest` 只校验不写。
  幂等：产物里已含 `[r057]` 标记则 SKIP。
  lead 接线：localtest/chain_build.py 的 SRV_CHAIN 链尾追加 'srv_patch_057.py'
  （第 23 环，现末环 srv_patch_arenaweek.py 之后；锚区与前 22 环零交集，无顺序硬约束）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval` / `PRAGMA`。
  · 每处替换 expect=1（count 断言），命中数不符即中止；round-trip 自证后原子写回。
  · ⛔ 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；⛔ 不改任何既有 srv_patch_*.py。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（同时用于已打补丁判定）
MARK = "[r057]"

# ============================================================ EDITS（每处锚点均已实测 count==1）

# E1 常量区：注释行 + 上限常量行（两行连续，一次替换）
E1_OLD = (
    "// ── Y3A 奇遇日记：每日 3 次随机奇遇（白 60/蓝 25/紫 12/金 3%），一抽一行入 adventures ──\n"
    "const ADVENTURE_DAILY_MAX = 3; // 每日抽取次数上限"
)
E1_NEW = (
    "// ── Y3A 奇遇日记 → [r057] R-057 奇遇抽奖：每日 10 次 · 冷却 30 分钟 · 消耗修为 5% 槽 · 15% 暴击双倍 ──\n"
    "const ADVENTURE_DAILY_MAX = 10; // 每日抽取次数上限 [r057] 3→10\n"
    "const ADVENTURE_COOLDOWN_MS = 30 * 60 * 1000; // [r057] 抽取冷却：30 分钟\n"
    "const ADVENTURE_COST_RATE = 0.05; // [r057] 每次消耗 = 当层修为槽 × 5%（修为不足拒绝）\n"
    "const ADVENTURE_CRIT_RATE = 0.15; // [r057] 暴击几率（灵石与修为收益双倍）"
)

# E2~E5 TIERS 四档灵石区间 ×30（整行替换；expRate/weight/tickets/bonusChance/bonusTickets 一字不动）
E2_OLD = "  { key: 'white',  name: '白', weight: 80,   stonesMin: 80,   stonesMax: 180,   expRateMin: 0.0015, expRateMax: 0.0030, tickets: 0, bonusChance: 0.02, bonusTickets: 0 },"
E2_NEW = "  { key: 'white',  name: '白', weight: 80,   stonesMin: 2400,  stonesMax: 5400,   expRateMin: 0.0015, expRateMax: 0.0030, tickets: 0, bonusChance: 0.02, bonusTickets: 0 }, // [r057] 灵石 ×30"
E3_OLD = "  { key: 'blue',   name: '蓝', weight: 12.5, stonesMin: 250,  stonesMax: 550,   expRateMin: 0.0030, expRateMax: 0.0060, tickets: 0, bonusChance: 0.06, bonusTickets: 0 },"
E3_NEW = "  { key: 'blue',   name: '蓝', weight: 12.5, stonesMin: 7500,  stonesMax: 16500,  expRateMin: 0.0030, expRateMax: 0.0060, tickets: 0, bonusChance: 0.06, bonusTickets: 0 }, // [r057] 灵石 ×30"
E4_OLD = "  { key: 'purple', name: '紫', weight: 6,    stonesMin: 700,  stonesMax: 1600,  expRateMin: 0.0060, expRateMax: 0.0120, tickets: 0, bonusChance: 0.15, bonusTickets: 1 },"
E4_NEW = "  { key: 'purple', name: '紫', weight: 6,    stonesMin: 21000, stonesMax: 48000,  expRateMin: 0.0060, expRateMax: 0.0120, tickets: 0, bonusChance: 0.15, bonusTickets: 1 }, // [r057] 灵石 ×30"
E5_OLD = "  { key: 'gold',   name: '金', weight: 1.5,  stonesMin: 1800, stonesMax: 4200,  expRateMin: 0.0120, expRateMax: 0.0220, tickets: 1, bonusChance: 0.35, bonusTickets: 2 },"
E5_NEW = "  { key: 'gold',   name: '金', weight: 1.5,  stonesMin: 54000, stonesMax: 126000, expRateMin: 0.0120, expRateMax: 0.0220, tickets: 1, bonusChance: 0.35, bonusTickets: 2 }, // [r057] 灵石 ×30"

# E6 adventures 表迁移守卫：加 drawn_at 列（safeAddColumn 幂等，老行 DEFAULT 0 不触发冷却）
E6_OLD = "if (!rows.some((r) => r.name === 'bonus_text')) safeAddColumn('adventures', 'bonus_text', \"ALTER TABLE adventures ADD COLUMN bonus_text TEXT NOT NULL DEFAULT ''\");"
E6_NEW = (E6_OLD + "\n"
          "if (!rows.some((r) => r.name === 'drawn_at')) safeAddColumn('adventures', 'drawn_at', 'ALTER TABLE adventures ADD COLUMN drawn_at INTEGER NOT NULL DEFAULT 0'); // [r057] 冷却基准（epoch ms）")

# E7 list：Promise.all 加冷却基准查询
E7_OLD = "const [rows, book] = await Promise.all(["
E7_NEW = "const [rows, book, cdRow] = await Promise.all(["

# E8 list：book 查询行尾追加 cd 查询
E8_OLD = ("GROUP BY event_key ORDER BY MIN(id) LIMIT 100', [userId]),\n"
          "    ]);")
E8_NEW = ("GROUP BY event_key ORDER BY MIN(id) LIMIT 100', [userId]),\n"
          "      dbGet('SELECT MAX(drawn_at) AS t FROM adventures WHERE player_id = ?', [userId]), // [r057] 冷却基准\n"
          "    ]);")

# E9 list 响应：加 cdLeft（毫秒）
E9_OLD = ("      drawn: draws.length,\n"
          "      dailyMax: ADVENTURE_DAILY_MAX,")
E9_NEW = ("      drawn: draws.length,\n"
          "      dailyMax: ADVENTURE_DAILY_MAX,\n"
          "      cdLeft: Math.max(0, ADVENTURE_COOLDOWN_MS - (Date.now() - Math.max(0, Number(cdRow?.t) || 0))), // [r057] 毫秒")

# E10a draw：每日上限检查后加冷却检查
E10A_OLD = "    if (drawn >= ADVENTURE_DAILY_MAX) return res.status(409).json({ error: `今日奇遇已抽满 ${ADVENTURE_DAILY_MAX} 次，明日再来` });"
E10A_NEW = (E10A_OLD + "\n"
            "    // [r057] 冷却 30 分钟：本人最近一次抽取时间（drawn_at）距今不足冷却则拒绝（409 文案带剩余秒数）\n"
            "    const cdRow = await dbGet('SELECT MAX(drawn_at) AS t FROM adventures WHERE player_id = ?', [userId]);\n"
            "    const cdMs = Date.now() - Math.max(0, Number(cdRow?.t) || 0);\n"
            "    if (cdMs < ADVENTURE_COOLDOWN_MS) return res.status(409).json({ error: `奇遇冷却中，还需 ${Math.ceil((ADVENTURE_COOLDOWN_MS - cdMs) / 1000)} 秒` });")

# E10b draw：存档解析后加修为消耗检查（cost 与锁内重算同式）
E10B_OLD = "    try { JSON.parse(row.save_data); } catch { return res.status(500).json({ error: '存档解析失败' }); }"
E10B_NEW = ("    let sd0: any = null;\n"
            "    try { sd0 = JSON.parse(row.save_data); } catch { return res.status(500).json({ error: '存档解析失败' }); }\n"
            "    // [r057] 消耗检查：当层修为槽 × ADVENTURE_COST_RATE，修为不足拒绝（锁内入档时同式重算兜底）\n"
            "    const nr0 = normalizeRealm(sd0 && typeof sd0.player === 'object' ? sd0.player : null);\n"
            "    const cost = Math.max(1, Math.floor(nr0.maxExp * ADVENTURE_COST_RATE));\n"
            "    if (Math.max(0, Math.floor(Number(nr0.exp) || 0)) < cost) return res.status(409).json({ error: '修为不足，无法抽取' });")

# E11 抽取体：暴击判定 + 灵石翻倍（INSERT 之前算好 ⇒ 账本/响应一致）
E11_OLD = "    const stones = funRandInt(tier.stonesMin, tier.stonesMax, Math.random);"
E11_NEW = ("    const crit = Math.random() < ADVENTURE_CRIT_RATE; // [r057] 暴击：灵石与修为收益双倍\n"
           "    const stones = funRandInt(tier.stonesMin, tier.stonesMax, Math.random) * (crit ? 2 : 1);")

# E12 INSERT：加 drawn_at 列与值
E12_OLD = ("        'INSERT INTO adventures (player_id, date, count, tier, event_key, exp_gain, stones, tickets, bonus_text) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)',\n"
           "        [userId, date, drawn + 1, tier.key, ev.key, stones, tickets, bonusText]")
E12_NEW = ("        'INSERT INTO adventures (player_id, date, count, tier, event_key, exp_gain, stones, tickets, bonus_text, drawn_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)', // [r057] 加 drawn_at\n"
           "        [userId, date, drawn + 1, tier.key, ev.key, stones, tickets, bonusText, Date.now()]")

# E13 收益回调：先扣消耗（同式重算，不足置 short → 外层补偿删行），再发收益；暴击二次钳槽
E13_OLD = ("      const nrNow = normalizeRealm(sd.player);\n"
           "      expGain = adventureExpGainRate(expRate, nrNow.maxExp, nrNow.exp);\n"
           "      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + expGain;")
E13_NEW = ("      const nrNow = normalizeRealm(sd.player);\n"
           "      // [r057] 先扣消耗（与入档前检查同式重算，锁内权威），再发收益；失败走外层补偿删行（全或无）\n"
           "      const costNow = Math.max(1, Math.floor(nrNow.maxExp * ADVENTURE_COST_RATE));\n"
           "      if (Math.max(0, Math.floor(Number(sd.player.exp) || 0)) < costNow) { short = true; return; }\n"
           "      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) - costNow;\n"
           "      expGain = adventureExpGainRate(expRate, nrNow.maxExp, Math.max(0, Math.floor(Number(sd.player.exp) || 0)));\n"
           "      if (crit) expGain = Math.min(expGain * 2, Math.max(0, nrNow.maxExp - Math.max(0, Math.floor(Number(sd.player.exp) || 0))));\n"
           "      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + expGain;")

# E14 响应：加 crit / cost
E14_OLD = ("      bonusText,\n"
           "      titleGranted,")
E14_NEW = ("      bonusText,\n"
           "      crit,\n"
           "      cost,\n"
           "      titleGranted,")

EDITS = [
    ("E1 常量区（上限 10 + 冷却/消耗/暴击三常量）", E1_OLD, E1_NEW),
    ("E2 白档灵石 ×30", E2_OLD, E2_NEW),
    ("E3 蓝档灵石 ×30", E3_OLD, E3_NEW),
    ("E4 紫档灵石 ×30", E4_OLD, E4_NEW),
    ("E5 金档灵石 ×30", E5_OLD, E5_NEW),
    ("E6 drawn_at 迁移守卫", E6_OLD, E6_NEW),
    ("E7 list Promise.all 加 cdRow", E7_OLD, E7_NEW),
    ("E8 list book 行尾加 cd 查询", E8_OLD, E8_NEW),
    ("E9 list 响应加 cdLeft", E9_OLD, E9_NEW),
    ("E10a draw 加冷却检查", E10A_OLD, E10A_NEW),
    ("E10b draw 加修为消耗检查", E10B_OLD, E10B_NEW),
    ("E11 暴击判定 + 灵石翻倍", E11_OLD, E11_NEW),
    ("E12 INSERT 加 drawn_at", E12_OLD, E12_NEW),
    ("E13 收益回调扣费 + 暴击钳槽", E13_OLD, E13_NEW),
    ("E14 响应加 crit/cost", E14_OLD, E14_NEW),
]

# 前置依赖（本环只读这些串做自证，不改）
REQUIRES = [
    (E1_OLD, 1, "常量区两行必须在位（本环唯一数值定义改动点）"),
    (E2_OLD, 1, "白档行必须在位"),
    (E3_OLD, 1, "蓝档行必须在位"),
    (E4_OLD, 1, "紫档行必须在位"),
    (E5_OLD, 1, "金档行必须在位"),
    (E6_OLD, 1, "bonus_text 迁移守卫行必须在位（drawn_at 守卫挂它后面）"),
    (E7_OLD, 1, "list 的 Promise.all 解构行必须在位"),
    (E8_OLD, 1, "list 的 book 查询行尾必须在位"),
    (E9_OLD, 1, "list 响应 dailyMax 行必须在位"),
    (E10A_OLD, 1, "draw 每日上限检查行必须在位"),
    (E10B_OLD, 1, "draw 存档解析行必须在位"),
    (E11_OLD, 1, "draw 灵石计算行必须在位"),
    (E12_OLD, 1, "draw INSERT 两行必须在位"),
    (E13_OLD, 1, "draw 收益回调三行必须在位"),
    (E14_OLD, 1, "draw 响应尾两行必须在位"),
    ("app.get('/api/adventure/draw'", 1, "draw 端点必须在位"),
    ("app.get('/api/adventure/list'", 1, "list 端点必须在位"),
    ("UNIQUE (player_id, date, count)", 1, "adventures 唯一约束必须在位（并发双抽防线，本环不动）"),
    ("grantTitleBySource(userId, 'adventure_gold')", 1, "金档称号授予必须在位（本环不动）"),
    ("function adventureExpGainRate(", 1, "修为钳槽纯函数必须在位（本环不改其公式）"),
]

# 冻结基线（打补丁前统计，打完后必须不变）
BASE_NEEDLES = ["res.status(403", "setInterval(", "PRAGMA", "require(",
                "ADVENTURE_EVENTS", "ADVENTURE_BONUS_TEXTS",
                "UNIQUE (player_id, date, count)",
                "grantTitleBySource(userId, 'adventure_gold')",
                "expRateMin: 0.0015", "expRateMin: 0.0120",
                "app.get('/api/adventure/list'", "app.get('/api/adventure/draw'"]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-057 奇遇抽奖经济重做环（服务端半边）")
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
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:90], n, cnt, why))

    # 3) 锚点计数 + 自毁防线（old 须为 new 的子串形态豁免：本环 E6/E8/E10 是「行后追加」型，
    #    old 完整保留在 new 里，old==new 检查照跑）
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
    gates = [
        # ---- 本环改动：常量 ----
        ("R57 上限已改 10", "const ADVENTURE_DAILY_MAX = 10;", 1),
        ("R57 旧上限 3 已清零", "const ADVENTURE_DAILY_MAX = 3;", 0),
        ("R57 冷却常量定义", "const ADVENTURE_COOLDOWN_MS = 30 * 60 * 1000;", 1),
        ("R57 消耗常量定义", "const ADVENTURE_COST_RATE = 0.05;", 1),
        ("R57 旧消耗常量 0.01 已清零", "const ADVENTURE_COST_RATE = 0.01;", 0),
        ("R57 暴击常量定义", "const ADVENTURE_CRIT_RATE = 0.15;", 1),
        ("R57 幂等标记就位", MARK, sum(new.count(MARK) for _, _, new in EDITS)),  # NEW 串自带标记总数（实测 17）
        # ---- 本环改动：TIERS ×30 ----
        ("R57 白档新灵石", "stonesMin: 2400,  stonesMax: 5400", 1),
        ("R57 蓝档新灵石", "stonesMin: 7500,  stonesMax: 16500", 1),
        ("R57 紫档新灵石", "stonesMin: 21000, stonesMax: 48000", 1),
        ("R57 金档新灵石", "stonesMin: 54000, stonesMax: 126000", 1),
        ("R57 旧白档灵石清零", "stonesMin: 80,   stonesMax: 180", 0),
        ("R57 旧蓝档灵石清零", "stonesMin: 250,  stonesMax: 550", 0),
        ("R57 旧紫档灵石清零", "stonesMin: 700,  stonesMax: 1600", 0),
        ("R57 旧金档灵石清零", "stonesMin: 1800, stonesMax: 4200", 0),
        # ---- 本环改动：冷却 ----
        ("R57 list 冷却查询", "dbGet('SELECT MAX(drawn_at) AS t FROM adventures WHERE player_id = ?', [userId]), // [r057] 冷却基准", 1),
        ("R57 list 响应 cdLeft", "cdLeft: Math.max(0, ADVENTURE_COOLDOWN_MS - (Date.now() - Math.max(0, Number(cdRow?.t) || 0))),", 1),
        ("R57 draw 冷却检查", "if (cdMs < ADVENTURE_COOLDOWN_MS) return res.status(409).json({ error: `奇遇冷却中，还需 ${Math.ceil((ADVENTURE_COOLDOWN_MS - cdMs) / 1000)} 秒` });", 1),
        ("R57 INSERT 带 drawn_at", "bonus_text, drawn_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)', // [r057] 加 drawn_at", 1),
        # ---- 本环改动：消耗修为 ----
        ("R57 消耗检查（入档前）", "if (Math.max(0, Math.floor(Number(nr0.exp) || 0)) < cost) return res.status(409).json({ error: '修为不足，无法抽取' });", 1),
        ("R57 锁内消耗重算", "const costNow = Math.max(1, Math.floor(nrNow.maxExp * ADVENTURE_COST_RATE));", 1),
        ("R57 锁内不足置 short", "if (Math.max(0, Math.floor(Number(sd.player.exp) || 0)) < costNow) { short = true; return; }", 1),
        ("R57 先扣后发", "sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) - costNow;", 1),
        # ---- 本环改动：暴击 ----
        ("R57 暴击判定", "const crit = Math.random() < ADVENTURE_CRIT_RATE;", 1),
        ("R57 灵石翻倍", "funRandInt(tier.stonesMin, tier.stonesMax, Math.random) * (crit ? 2 : 1)", 1),
        ("R57 修为暴击二次钳槽", "if (crit) expGain = Math.min(expGain * 2, Math.max(0, nrNow.maxExp", 1),
        ("R57 响应带 crit/cost", "      crit,\n      cost,", 1),
        # ---- 本环改动：drawn_at 总量自证（守卫 3 + list 查 1 + draw 注释/查 2 + INSERT 列/注释 2）----
        ("R57 drawn_at 引用总数", "drawn_at", sum(new.count("drawn_at") for _, _, new in EDITS)),  # 实测 8
        # ---- 顺序契约（§22.8 全或无）：冷却查询 < 占位 INSERT < 扣费入档 ----
        #      （在 main 尾部单独断言，见下方 order 段）
        # ---- 冻结：链上前 22 环与本环未触及的 adventure 面 ----
        ("冻结 UNIQUE 约束未动", "UNIQUE (player_id, date, count)", base["UNIQUE (player_id, date, count)"]),
        ("冻结 金档称号未动", "grantTitleBySource(userId, 'adventure_gold')", base["grantTitleBySource(userId, 'adventure_gold')"]),
        ("冻结 白档修为区间未动", "expRateMin: 0.0015", base["expRateMin: 0.0015"]),
        ("冻结 金档修为区间未动", "expRateMin: 0.0120", base["expRateMin: 0.0120"]),
        ("冻结 list 端点唯一", "app.get('/api/adventure/list'", base["app.get('/api/adventure/list'"]),
        ("冻结 draw 端点唯一", "app.get('/api/adventure/draw'", base["app.get('/api/adventure/draw'"]),
        ("冻结 事件池未动", "ADVENTURE_EVENTS", base["ADVENTURE_EVENTS"]),
        ("冻结 珍宝文案池未动", "ADVENTURE_BONUS_TEXTS", base["ADVENTURE_BONUS_TEXTS"]),
        ("冻结 钳槽公式未动", "function adventureExpGainRate(", 1),
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

    # 7) 顺序契约（§22.8）：draw 端点片段内 冷却查询 → 占位 INSERT → 扣费入档 严格递增
    d0 = out.find("app.get('/api/adventure/draw'")
    seg = out[d0:d0 + 7000] if d0 >= 0 else ""
    i_cd = seg.find("SELECT MAX(drawn_at)")
    i_ins = seg.find("INSERT INTO adventures")
    i_pay = seg.find("updatePlayerSave(userId")
    order_ok = d0 >= 0 and 0 <= i_cd < i_ins < i_pay
    ok = ok and order_ok
    print("  [%s] %-44s cd@%d < ins@%d < pay@%d"
          % ("OK" if order_ok else "FAIL", "R57 顺序契约 冷却<占位<扣费", i_cd, i_ins, i_pay))

    # 8) 语义自证：新常量引用闭合
    sem_ok = (
        out.count("ADVENTURE_COOLDOWN_MS") == 4   # 定义 + list 响应 + draw 检查 + draw 差值
        and out.count("ADVENTURE_COST_RATE") == 4  # 定义 + E10b 注释 + nr0 + costNow
        and out.count("ADVENTURE_CRIT_RATE") == 2  # 定义 + crit 判定
        and out.count("const crit") == 1
    )
    ok = ok and sem_ok
    print("  [%s] %-44s cd=%d cost=%d crit=%d"
          % ("OK" if sem_ok else "FAIL", "R57 语义自证(常量引用闭合)",
             out.count("ADVENTURE_COOLDOWN_MS"), out.count("ADVENTURE_COST_RATE"),
             out.count("ADVENTURE_CRIT_RATE")))

    if not ok:
        fail("门禁未全绿，未写回")

    # 9) 往返自证
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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r057-", suffix=".tmp")
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
