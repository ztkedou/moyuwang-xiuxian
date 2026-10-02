# -*- coding: utf-8 -*-
r"""
srv_patch_r116.py -- R-116 历练奇遇「抽奖券获取概率大幅压低」（服务端半边 · SRV_CHAIN 新环）

需求（台账 R-116，逐字）
--------------------------------------------------------------------------
  「发现一个严重问题，历练获取的抽奖卷太多了。把这个道具获取概率大幅度压低，
    这个道具主要是通过任务或者活动获取，历练获得这个的几率应该变得非常非常低。」

定档（★ 拍板 2026-10-02_0246「R116-R131数值代决」§R-116，数值表 docs/0.9.13-design/数值表.md §4）
--------------------------------------------------------------------------
  ADVENTURE_TIERS 四行 = 发券总闸（srv @684218 实读消费点）：
      tickets = floor(tier.tickets) + (rand < tier.bonusChance ? floor(tier.bonusTickets) : 0)
  只动 tickets / bonusChance / bonusTickets；weight / stones 区间 / expRate 区间一字不动：

    档 | 权重 | tickets        | bonusChance      | bonusTickets
    白 | 80   | 0（不动）      | 0.02（不动）     | 0（不动）
    蓝 | 12.5 | 0（不动）      | 0.06（不动）     | 0（不动）
    紫 | 6    | 0（不动）      | 0.15 → **0.01**  | 1（不动）
    金 | 1.5  | **1 → 0**      | 0.35 → **0.02**  | **2 → 1**

  期望验算（本脚本运行时实算断言，非转录）：
    旧 EV/抽 = 0.06×(0.15×1) + 0.015×(1+0.35×2) = 0.009 + 0.0255 = 0.0345 券（日 10 抽 = 0.345）
    新 EV/抽 = 0.06×(0.01×1) + 0.015×(0.02×1)   = 0.0006 + 0.0003 = 0.0009 券（日 10 抽 = 0.009）
    = 38.33x ↓。抽奖券主获取面回归「任务 / 签到里程碑 / 茶馆彩头 / 新号 10 张」（均不动）。

客户端半边（同拍板条目的「池自回流」建议档，属可摘除件）
--------------------------------------------------------------------------
  抽奖池自回流（抽奖奖品池里 1/3/5 张券的权重 15/3/0.5）在**客户端**产物
  （index-v2912-20261002.js @464616，纯客户端抽奖，yl_lottery_ext 侦察已证全仓无 /lottery/draw 端点），
  由 patches/client/yl_r116_ext.py 压到 4/0.6/0.08（券 EV 26.5→6.2 / 总权重，4.27x↓）。
  两脚本互相独立：主控合并时若不采纳池压缩，摘除 yl_r116_ext.py 模块即可，不影响本环。

CLI 契约（照 srv_patch_115.py / srv_patch_057.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回；`--check` / `--selftest` 只校验不写。
  幂等：产物含 `[r116]` 则 SKIP。
  写回前先落 `<src>.bak-r116-<时间戳>` 备份（改前 .bak 纪律）。
  lead 接线：SRV_CHAIN 追加 'srv_patch_r116.py'（**必须排在 srv_patch_057.py 之后**——
  本环锚点含 057 追加的 `// [r057] 灵石 ×30` 行尾注释；放链尾即可，与其余环零锚区交集）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403) / setInterval / PRAGMA。
  · 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；不改任何既有 srv_patch_*.py。
  · 每处替换 expect=1；EV 实算断言 + round-trip 自证后原子写回。
  · 业务拒绝码面（400/409/401）零改动：本环纯数值，不新增任何分支。
"""

import argparse
import datetime
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r116]"

# ============================================================ 定档数值（唯一调参点）
# 紫（purple）
PURPLE_BONUS_CHANCE = "0.01"   # 旧 0.15
# 金（gold）
GOLD_TICKETS = "0"             # 旧 1
GOLD_BONUS_CHANCE = "0.02"     # 旧 0.35
GOLD_BONUS_TICKETS = "1"       # 旧 2

# ============================================================ 改动点（两处整行尾替换）

# ① 紫档：bonusChance 0.15 → 0.01（tickets 0 / bonusTickets 1 不动）
PURPLE_OLD = "tickets: 0, bonusChance: 0.15, bonusTickets: 1 }, // [r057] 灵石 ×30"
PURPLE_NEW = ("tickets: 0, bonusChance: %s, bonusTickets: 1 }, // [r057] 灵石 ×30 "
              "// %s 券概率压低：紫档 bonus 0.15→%s") % (PURPLE_BONUS_CHANCE, MARK, PURPLE_BONUS_CHANCE)

# ② 金档：tickets 1→0、bonusChance 0.35→0.02、bonusTickets 2→1
GOLD_OLD = "tickets: 1, bonusChance: 0.35, bonusTickets: 2 }, // [r057] 灵石 ×30"
GOLD_NEW = ("tickets: %s, bonusChance: %s, bonusTickets: %s }, // [r057] 灵石 ×30 "
            "// %s 券概率压低：金档 1→%s / 0.35→%s / 2→%s") % (
    GOLD_TICKETS, GOLD_BONUS_CHANCE, GOLD_BONUS_TICKETS, MARK,
    GOLD_TICKETS, GOLD_BONUS_CHANCE, GOLD_BONUS_TICKETS)

EDITS = [
    ("R116 紫档 bonusChance ↓", PURPLE_OLD, PURPLE_NEW),
    ("R116 金档 三值 ↓", GOLD_OLD, GOLD_NEW),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    (PURPLE_OLD, 1, "紫档行旧形态必须在位（唯一锚点；含 [r057] 行尾注释 ⇒ 本环必须排 srv_patch_057.py 之后）"),
    (GOLD_OLD, 1, "金档行旧形态必须在位（唯一锚点）"),
    ("  { key: 'white',  name: '白', weight: 80,   stonesMin: 2400,  stonesMax: 5400,   expRateMin: 0.0015, expRateMax: 0.0030, tickets: 0, bonusChance: 0.02, bonusTickets: 0 }, // [r057] 灵石 ×30",
     1, "白档行必须在位（本环冻结）"),
    ("  { key: 'blue',   name: '蓝', weight: 12.5, stonesMin: 7500,  stonesMax: 16500,  expRateMin: 0.0030, expRateMax: 0.0060, tickets: 0, bonusChance: 0.06, bonusTickets: 0 }, // [r057] 灵石 ×30",
     1, "蓝档行必须在位（本环冻结）"),
    ("  tickets: number; bonusChance: number; bonusTickets: number;", 1, "AdventureTierDef 接口必须在位"),
    ("const tickets = Math.max(0, Math.floor(tier.tickets)) + (Math.random() < tier.bonusChance ? Math.max(0, Math.floor(tier.bonusTickets)) : 0);",
     1, "发券总闸消费点必须在位（/api/adventure/draw）"),
    ("const ADVENTURE_COST_RATE = 0.05;", 1, "修为消耗常量必须在位（R-057 拍板面，冻结）"),
    ("const ADVENTURE_CRIT_RATE = 0.15;", 1, "暴击常量必须在位（R-057 拍板面，冻结）"),
    ("const ADVENTURE_DAILY_MAX = 10;", 1, "日限常量必须在位（R-057 拍板面，冻结）"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "res.status(403", "require(", "setInterval(", "PRAGMA",
    "stonesMin: 21000, stonesMax: 48000,",          # 紫灵石区间（×30 口径，不动）
    "stonesMin: 54000, stonesMax: 126000,",          # 金灵石区间（不动）
    "expRateMin: 0.0060, expRateMax: 0.0120,",       # 紫修为区间（不动）
    "expRateMin: 0.0120, expRateMax: 0.0220,",       # 金修为区间（不动）
    "tickets: t.tickets, bonusChance: t.bonusChance, bonusTickets: t.bonusTickets })),",  # /list 下发映射
    "function drawAdventureTier(rng: () => number): AdventureTierDef {",  # 抽档函数（分母 100 口径，不动）
]


def ev_old_per_draw():
    return 0.06 * (0.15 * 1) + 0.015 * (1 + 0.35 * 2)


def ev_new_per_draw():
    return 0.06 * (float(PURPLE_BONUS_CHANCE) * 1) + 0.015 * (
        float(GOLD_TICKETS) + float(GOLD_BONUS_CHANCE) * float(GOLD_BONUS_TICKETS))


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-116 历练奇遇抽奖券概率大幅压低环（服务端）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 0) EV 实算断言（数值表 §4 的转录值必须与定档常量实算一致）
    ev_o, ev_n = ev_old_per_draw(), ev_new_per_draw()
    if abs(ev_o - 0.0345) > 1e-12:
        fail("旧 EV 实算 %r != 0.0345（与数值表/拍板不符）" % ev_o)
    if abs(ev_n - 0.0009) > 1e-12:
        fail("新 EV 实算 %r != 0.0009（与数值表/拍板不符）" % ev_n)
    print("  EV/抽：旧 %.4f → 新 %.4f 券（%.1fx↓）；日 10 抽：%.3f → %.3f 张"
          % (ev_o, ev_n, ev_o / ev_n, ev_o * 10, ev_n * 10))

    # 1) 幂等：已打过本环
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
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
    gates = [
        # ---- 本环改动 ----
        ("R116 幂等标记就位", MARK, 2),
        ("R116 紫档新 bonus 在位", "tickets: 0, bonusChance: %s, bonusTickets: 1 }, // [r057] 灵石 ×30 // %s" % (PURPLE_BONUS_CHANCE, MARK), 1),
        ("R116 金档新行在位", "tickets: %s, bonusChance: %s, bonusTickets: %s }, // [r057] 灵石 ×30 // %s" % (GOLD_TICKETS, GOLD_BONUS_CHANCE, GOLD_BONUS_TICKETS, MARK), 1),
        ("R116 旧紫档清零", PURPLE_OLD, 0),
        ("R116 旧金档清零", GOLD_OLD, 0),
        # ---- 冻结：白/蓝整行、灵石与修为区间、权重口径 ----
        ("冻结 白档行未动", REQUIRES[2][0], 1),
        ("冻结 蓝档行未动", REQUIRES[3][0], 1),
        ("冻结 紫灵石区间未动", "stonesMin: 21000, stonesMax: 48000,", base["stonesMin: 21000, stonesMax: 48000,"]),
        ("冻结 金灵石区间未动", "stonesMin: 54000, stonesMax: 126000,", base["stonesMin: 54000, stonesMax: 126000,"]),
        ("冻结 紫修为区间未动", "expRateMin: 0.0060, expRateMax: 0.0120,", base["expRateMin: 0.0060, expRateMax: 0.0120,"]),
        ("冻结 金修为区间未动", "expRateMin: 0.0120, expRateMax: 0.0220,", base["expRateMin: 0.0120, expRateMax: 0.0220,"]),
        ("冻结 抽档函数未动", "function drawAdventureTier(rng: () => number): AdventureTierDef {",
         base["function drawAdventureTier(rng: () => number): AdventureTierDef {"]),
        # ---- 冻结：R-057 拍板面（消耗 5% / 暴击 15% / 日限 10）----
        ("冻结 修为消耗常量", "const ADVENTURE_COST_RATE = 0.05;", 1),
        ("冻结 暴击常量", "const ADVENTURE_CRIT_RATE = 0.15;", 1),
        ("冻结 日限常量", "const ADVENTURE_DAILY_MAX = 10;", 1),
        # ---- 冻结：发券总闸与下发映射（结构不动，只动表值）----
        ("冻结 发券总闸", REQUIRES[5][0], 1),
        ("冻结 接口定义", REQUIRES[4][0], 1),
        ("冻结 /list 下发映射", "tickets: t.tickets, bonusChance: t.bonusChance, bonusTickets: t.bonusTickets })),",
         base["tickets: t.tickets, bonusChance: t.bonusChance, bonusTickets: t.bonusTickets })),"]),
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
        print("  [%s] %-32s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 7) 语义自证：四行齐备、且只换了 2 行的 ticket 三键
    sem_ok = (
        out.count("key: 'white'") == 1 and out.count("key: 'blue'") == 1
        and out.count("key: 'purple'") == 1 and out.count("key: 'gold'") == 1
        and out.count("tickets: 0, bonusChance: 0.15") == 0
        and out.count("bonusChance: 0.35") == 0
    )
    ok = ok and sem_ok
    print("  [%s] %-32s white=%d blue=%d purple=%d gold=%d 旧值残留0"
          % ("OK" if sem_ok else "FAIL", "R116 语义自证(四行齐备)",
             out.count("key: 'white'"), out.count("key: 'blue'"),
             out.count("key: 'purple'"), out.count("key: 'gold'")))

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

    # 9) 改前 .bak + 原子写回
    d = os.path.dirname(os.path.abspath(src_path))
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = src_path + ".bak-r116-" + ts
    with io.open(bak, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("  已备份原文件 -> %s" % bak)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r116-", suffix=".tmp")
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
