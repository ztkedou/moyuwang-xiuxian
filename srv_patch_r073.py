# -*- coding: utf-8 -*-
r"""
srv_patch_r073.py -- R-073 妖灵「进食成本降低」（服务端半边 · SRV_CHAIN 链尾）

需求原文（用户）
--------------------------------------------------------------------------
  「仙务·妖灵 进食的成本降低，这个饱食度实际作用是什么？……」
  （本环只做「成本降低」；「饱食度作用说明」与「归位名字/种族不匹配」是客户端半边，
    见 yl_r073_ext.py / yl_r074_ext.py。）

改前 / 改后（`R018_FEED_TIERS`，r018 环产物，srv/index_v28.ts:6030 起）
--------------------------------------------------------------------------
   档位          改前 灵石/hunger           改后 灵石/hunger
   凡品·青草露    5,000 / +30  = 166.67     3,000 / +30  = 100
   灵品·玉髓羹   25,000 / +150 = 166.67    15,000 / +150 = 100
   仙品·九转灵丹 100,000 / +600 = 166.67   60,000 / +600 = 100
  ⇒ 单价 166.67 → 100 灵石/hunger（**−40%**），三档**仍单价一致**（守 r018 设计案 §D1
     「单价完全一致，只买批量便利」的红线，不产生「大额更划算」的套利）。
  ⇒ 喂满 99 级（饱食度 9900）总投入：1,650,000 → **990,000 灵石**（对照天品心法 211.2 万：
     0.79× → 0.47×）。**不新增任何灵石 faucet**（进食始终是纯消耗口，经济红线不破）。

为什么改这里（口径证据）
--------------------------------------------------------------------------
  · 进食扣费的**唯一权威源** = `POST /api/pet/feed` 里的 `_feed.cost`，
    而 `_feed = r018FeedTier(req.body?.tier)` 读的正是 `R018_FEED_TIERS`（r018 注入块内）。
  · 客户端**不复制**任何价格：`YlxwR18FeedRow` 的按钮文案用服务端回显的
    `t.consts.feedTiers[k].cost`（`GET /api/pet` → `convert: ..., feedTiers: R018_FEED_TIERS,`）
    ⇒ 只改这一张表，UI 与扣费**自动同步**，无需改客户端。
  · `hunger` 增量（30/150/600）与 `PET_FEED_COST`（旧单档常量）**一律不动**：
    前者是升级曲线口径（`level = floor(hunger/100)`），后者仍是 r018 门禁面。

幂等
--------------------------------------------------------------------------
  三档新价若已全部在位 ⇒ 直接 SKIP（不重复改）。

CLI 契约（照 srv_patch_r018.py / srv_patch_r048.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  每处替换 expect=1，命中数不符即中止；round-trip 自证后原子写回。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403) / setInterval / PRAGMA。
  · 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；不改任何既有 srv_patch_*.py。
  · ★ 接线：SRV_CHAIN 链尾追加 'srv_patch_r073.py'；**硬依赖 srv_patch_r018.py 在前**
    （锚点是 r018 注入的 `R018_FEED_TIERS` 表体）。与 r018b 零锚点交集
    （r018b 只引用 `feedTiers: R018_FEED_TIERS` 回显行，不动表值）。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ 唯一调参点（三档单价 166.67 → 100）
COST_COMMON = 3000        # 凡品·青草露（原 5000）
COST_FINE = 15000         # 灵品·玉髓羹（原 25000）
COST_IMMORTAL = 60000     # 仙品·九转灵丹（原 100000）

# ============================================================ 三处就地替换（锚点实测 count==1）

E_COMMON_OLD = '  common:   { cost: 5000,   hunger: 30,'
E_COMMON_NEW = '  common:   { cost: 3000,   hunger: 30,'

E_FINE_OLD = '  fine:     { cost: 25000,  hunger: 150,'
E_FINE_NEW = '  fine:     { cost: 15000,  hunger: 150,'

# ★ 100000(6 位) → 60000(5 位)，补一个空格以保持 `name:` 列对齐
E_IMM_OLD = '  immortal: { cost: 100000, hunger: 600,'
E_IMM_NEW = '  immortal: { cost: 60000,  hunger: 600,'

EDITS = [
    ("E1 凡品档 5000 → 3000",   E_COMMON_OLD, E_COMMON_NEW),
    ("E2 灵品档 25000 → 15000", E_FINE_OLD,   E_FINE_NEW),
    ("E3 仙品档 100000 → 60000", E_IMM_OLD,   E_IMM_NEW),
]

# 幂等判据：三档新价全部在位
NEW_LINES = [E_COMMON_NEW, E_FINE_NEW, E_IMM_NEW]

# ============================================================ 依赖（r018 环必须已在链内）

REQUIRES = [
    ("const R018_FEED_TIERS: Record<string, { cost: number; hunger: number; name: string }> = {", 1,
     "r018 灵食三档表必须在位（本环锚点所在）"),
    ("    const _feed = r018FeedTier(req.body?.tier);", 1,
     "feed 端点走档位取价（本环改价才会生效）"),
    ("const PET_FEED_COST = 5000;", 1, "petcore 旧单档常量（门禁面，本环不动）"),
    ("const R018_CONVERT = 0.06;", 1, "r018 转化率（门禁面，本环不动）"),
    ("convert: R018_CONVERT, feedTiers: R018_FEED_TIERS, playKinds: R018_PLAY_KINDS,", 1,
     "GET /api/pet 常量回显（客户端价格来源，本环不动）"),
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description='R-073 妖灵进食成本降低（服务端环 r073）')
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:70], n, cnt, why))

    # 2) 幂等
    if all(ln in src for ln in NEW_LINES):
        print("  [SKIP] 三档新价已全部在位（已打过本环），未写回 %s" % src_path)
        return

    # 3) 锚点计数（每个必须恰 1）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old))
        if old == new:
            fail("%s old == new" % name)

    # 4) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 5) 门禁
    base403 = src.count("res.status(403")
    gates = [
        # ---- 本环改动 ----
        ("R73 凡品档 3000/+30",   E_COMMON_NEW, 1),
        ("R73 灵品档 15000/+150", E_FINE_NEW, 1),
        ("R73 仙品档 60000/+600", E_IMM_NEW, 1),
        ("R73 旧 5000 档已清零",  "cost: 5000,   hunger: 30,", 0),
        ("R73 旧 25000 档已清零", "cost: 25000,  hunger: 150,", 0),
        ("R73 旧 100000 档已清零", "cost: 100000, hunger: 600,", 0),
        # ---- 冻结（本环不得回踩）----
        ("冻结 r018 三档表仍在",
         "const R018_FEED_TIERS: Record<string, { cost: number; hunger: number; name: string }> = {", 1),
        ("冻结 r018 档位取价仍在", "const _feed = r018FeedTier(req.body?.tier);", 1),
        ("冻结 r018 feedTiers 回显未动",
         "convert: R018_CONVERT, feedTiers: R018_FEED_TIERS, playKinds: R018_PLAY_KINDS,", 1),
        ("冻结 PET_FEED_COST 未动", "const PET_FEED_COST = 5000;", 1),
        ("冻结 R018_CONVERT 未动", "const R018_CONVERT = 0.06;", 1),
        ("冻结 喂食度上限未动", "const PET_HUNGER_MAX = 9999;", 1),
        ("冻结 升级除数未动", "const PET_LEVEL_DIVISOR = 100;", 1),
        ("冻结 feed 端点未动", "app.post('/api/pet/feed', authenticateToken", 1),
        ("冻结 play 端点未动", "app.post('/api/pet/play', authenticateToken", 1),
        ("冻结 经济配额函数未动", "function settleSaveEconV2", 1),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-38s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 6) 红线：不得新增 403
    a403 = out.count("res.status(403")
    good = (a403 == base403)
    ok = ok and good
    print("  [%s] %-38s actual=%d expect==%d" % ("OK" if good else "FAIL",
                                                 "红线 未新增 res.status(403)", a403, base403))

    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r073-", suffix=".tmp")
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
