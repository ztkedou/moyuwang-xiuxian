# -*- coding: utf-8 -*-
r"""
srv_patch_055.py -- R-055 灵玉阁数值重定档（服务端半边 · SRV_CHAIN 第 36 环）

只做两类常数/注释替换，公式与端点零改动：
  A. 掉玉率  ACT_TOKEN_RATE_PER_10K  2 → 50（0.02% → 0.5%）
  B. 货架顶价 title_jade（称号·灵玉仙客）2500 → 1000
  日上限 ACT_TOKEN_DAILY_CAP = 300【数值不动】，仅同步其换算注释（150 万→6 万结算量）。

为什么改这里（口径证据，与 yl_055_ext.py 配套）
--------------------------------------------------------------------------
  R-055 原文：「灵玉的获取途径和触发几率实装了吗，我玩了很久也没遇到过。
  如果每次是按个获取的话，最高2500个灵玉获取难度有点太高了……需要策划一下。」
  · 掉玉已实装（actDropTokens + 炼丹出炉/灵田收获/离线收益三挂点），但
    r=2（0.02%）+ floor ⇒ 单笔结算 <500 灵石必为 0 ⇒ 普通玩家几乎永远看不见掉落
    （floor(settled*2/10000)，settled=499 ⇒ 0）。机制在、感知为零。
  · r=50 后 floor(settled/200)：单笔 ≥200 石即掉 1 玉，每笔结算可见；
    活跃玩家（日结算 ~3 万石，估）≈150 玉/日 ⇒ 顶价 1000 约一个活动期可达；
    普通玩家 ~50 玉/日 ≈ 3 期攒齐（余额跨期保留，设计本就支持）。
  · 日上限 300 保持：新口径下 =6 万结算量/日封顶，仍能钳住重离线型玩家，
    经济总量保护不变（与原 300=150 万口径同「顶格玩家触顶」的设计意图）。
  · 货架其余三档（100/300/800）不动，价格序 100<300<800<1000 保持。
  · 掉率/顶价推演与依据全文见拍板文件（拍板/2026-10-01_*_R-055_*.md）。

客户端半边（yl_055_ext.py，另一环）
--------------------------------------------------------------------------
  灵玉阁面板新增【玩法说明】行（写明 0.5% / 50 玉/万灵石 / 日上限 300 / 仅活动期掉落），
  并把「未开放」句的「随时可掉」误导改掉。⚠ 文案里明写了 0.5% 与 300，
  本环若再调 r 或 cap，必须同步改 yl_055_ext.py 的 HELP_TEXT。

CLI 契约（与链上其余补丁一致，照 srv_patch_050.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` / `--selftest` 只校验不写。
  幂等：产物里已含 `[r055jade]` 标记或 `ACT_TOKEN_RATE_PER_10K = 50` 则 SKIP。
  lead 接线：localtest/chain_build.py 的 SRV_CHAIN 链尾追加 'srv_patch_055.py'
  （第 36 环，现末环 srv_patch_050.py 之后；仅要求第 8 环 srv_patch_activity087.py 在前）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval` / `PRAGMA`。
  · 本环是纯常数/注释替换：不插入任何新代码块，无注入块需求。
  · 每处替换 expect=1，命中数不符即中止；round-trip 自证后原子写回。
  · ⛔ 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；⛔ 不改任何既有 srv_patch_*.py。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（同时用于已打补丁判定）
MARK = "[r055jade]"

# ============================================================ 唯一改动点（六处替换）

# A1 掉玉率常数（公式 `let gain = Math.floor((settled * ACT_TOKEN_RATE_PER_10K) / 10000);` 不动，
#     数值经常量流入）
EDIT_RATE_OLD = "const ACT_TOKEN_RATE_PER_10K = 2;"
EDIT_RATE_NEW = "const ACT_TOKEN_RATE_PER_10K = 50;"

# A2 掉玉率行尾注释（同步语义，防注释骗人）
EDIT_RATECMT_OLD = "// C 掉玉率 r=2 玉/万灵石结算"
EDIT_RATECMT_NEW = "// C 掉玉率 r=50 玉/万灵石结算 [r055jade] R-055：2→50（0.02%→0.5%，单笔 200 石起即掉 1 玉）"

# A3 日上限换算注释（数值 300 不动，只改换算口径）
EDIT_CAPCMT_OLD = "// C 掉玉日上限（=150 万灵石结算量/日）"
EDIT_CAPCMT_NEW = "// C 掉玉日上限（=6 万灵石结算量/日）[r055jade] R-055：原 150 万口径随掉率×25 同比例收紧"

# B1 货架顶价：title_jade 2500 → 1000（价格序 100<300<800<1000 保持）
EDIT_TITLE_OLD = ("{ id: 'title_jade', name: '称号·灵玉仙客', price: 2500, limit: 1,"
                  "  titleSource: 'act087_jade' },")
EDIT_TITLE_NEW = ("{ id: 'title_jade', name: '称号·灵玉仙客', price: 1000, limit: 1,"
                  "  titleSource: 'act087_jade' },")

# B2 货架数组尾注释落改动记录
EDIT_ITEMSCMT_OLD = "装饰 SKU 无承载系统整行砍（数值表-T5T6 C-5）"
EDIT_ITEMSCMT_NEW = ("装饰 SKU 无承载系统整行砍（数值表-T5T6 C-5）"
                     "[r055jade] R-055：title_jade 2500→1000（顶价可达性，见拍板 2026-10-01）")

# B3 称号 seed 注释同步（2500 → 1000）
EDIT_SEEDCMT_OLD = "灵玉阁 2500 玉兑换物"
EDIT_SEEDCMT_NEW = "灵玉阁 1000 玉兑换物"

EDITS = [
    ("R055 掉玉率 2→50",            EDIT_RATE_OLD,    EDIT_RATE_NEW),
    ("R055 掉玉率注释同步",          EDIT_RATECMT_OLD, EDIT_RATECMT_NEW),
    ("R055 日上限换算注释同步",      EDIT_CAPCMT_OLD,  EDIT_CAPCMT_NEW),
    ("R055 title_jade 2500→1000",   EDIT_TITLE_OLD,   EDIT_TITLE_NEW),
    ("R055 货架尾注释落记录",        EDIT_ITEMSCMT_OLD, EDIT_ITEMSCMT_NEW),
    ("R055 称号 seed 注释同步",      EDIT_SEEDCMT_OLD, EDIT_SEEDCMT_NEW),
]

# 前置依赖（本环只读这些串做自证，不改）
REQUIRES = [
    (EDIT_RATE_OLD, 1, "待改掉玉率常数行必须在位（本环唯一掉率改动点）"),
    (EDIT_RATECMT_OLD, 1, "待改掉玉率注释必须在位"),
    (EDIT_CAPCMT_OLD, 1, "待改日上限注释必须在位（只改注释不改数值）"),
    (EDIT_TITLE_OLD, 1, "待改 title_jade 行必须在位（本环唯一价格改动点）"),
    (EDIT_ITEMSCMT_OLD, 1, "待改货架尾注释必须在位"),
    (EDIT_SEEDCMT_OLD, 1, "待改 seed 注释必须在位"),
    ("function actDropTokens(", 1, "掉玉公共函数必须在位（改动经它生效）"),
    ("let gain = Math.floor((settled * ACT_TOKEN_RATE_PER_10K) / 10000);",
     1, "掉率公式必须原样（本环只改常数不改公式）"),
    ("if (yieldStones > 0) actDropTokens(userId, yieldStones, now)",
     1, "炼丹出炉挂点必须在位（获取途径实装证据①）"),
    ("if (gain.stones > 0) actDropTokens(userId, gain.stones, now)",
     1, "灵田收获挂点必须在位（获取途径实装证据②）"),
    ("if (applied.stonesGain > 0) actDropTokens(userId, applied.stonesGain, nowMs)",
     1, "离线收益挂点必须在位（获取途径实装证据③）"),
    ("const ACT_TOKEN_DAILY_CAP = 300;", 1, "日上限数值行必须在位（本环不改它，只改其注释）"),
    ("const ACT_TOKEN_KEY = 'lingyu'", 1, "代币键必须在位（余额跨期保留载体）"),
    ("{ id: 'bag_s',", 1, "货架小袋行必须在位（其余三档价格不动）"),
    ("{ id: 'bag_m',", 1, "货架中袋行必须在位"),
    ("{ id: 'bag_l',", 1, "货架大袋行必须在位"),
]

# 冻结基线（打补丁前统计，打完后必须不变）
BASE_NEEDLES = ["res.status(403", "require(", "setInterval(", "PRAGMA",
                "jadeBalance", "function actDropTokens(",
                "const ACT_TOKEN_DAILY_CAP = 300;",
                "const ACT_BOSS_FREE_STRIKES = 3;",
                "const ACT_CHECKIN_DAYS = 7;",
                "const ACT_MULT_CAP = 10;",
                "{ id: 'bag_s',", "{ id: 'bag_m',", "{ id: 'bag_l',"]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-055 灵玉阁掉率/顶价重定档环")
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
    if (MARK in src) or ("const ACT_TOKEN_RATE_PER_10K = 50;" in src):
        print("[SKIP] source looks already patched（已含 %s 或 ACT_TOKEN_RATE_PER_10K = 50）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点计数（本环全部是「常数/注释替换」型：old 不保留进 new 是本意）
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
        ("R55 掉玉率已改 50", "const ACT_TOKEN_RATE_PER_10K = 50;", 1),
        ("R55 旧掉玉率已清零", "const ACT_TOKEN_RATE_PER_10K = 2;", 0),
        ("R55 掉率注释已同步（r=50）", "r=50 玉/万灵石结算", 1),
        ("R55 旧掉率注释（r=2）已清零", "r=2 玉/万灵石结算", 0),
        ("R55 日上限注释已同步（6 万）", "=6 万灵石结算量/日", 1),
        ("R55 旧日上限注释（150 万）已清零", "=150 万灵石结算量/日", 0),
        ("R55 title_jade 已改 1000", "price: 1000, limit: 1,  titleSource: 'act087_jade'", 1),
        ("R55 旧价 2500 已清零", "price: 2500", 0),
        ("R55 seed 注释已同步（1000 玉）", "灵玉阁 1000 玉兑换物", 1),
        ("R55 幂等标记就位", MARK, 3),
        # ---- 冻结：公式 / 挂点 / 上限数值 / 相邻面一字不动 ----
        ("冻结 掉率公式未动",
         "let gain = Math.floor((settled * ACT_TOKEN_RATE_PER_10K) / 10000);", 1),
        ("冻结 炼丹出炉挂点未动",
         "if (yieldStones > 0) actDropTokens(userId, yieldStones, now)", 1),
        ("冻结 灵田收获挂点未动",
         "if (gain.stones > 0) actDropTokens(userId, gain.stones, now)", 1),
        ("冻结 离线收益挂点未动",
         "if (applied.stonesGain > 0) actDropTokens(userId, applied.stonesGain, nowMs)", 1),
        ("冻结 日上限数值 300 不变", "const ACT_TOKEN_DAILY_CAP = 300;", base["const ACT_TOKEN_DAILY_CAP = 300;"]),
        ("冻结 代币键未动", "const ACT_TOKEN_KEY = 'lingyu'", 1),
        ("冻结 货架其余三档未动", "{ id: 'bag_s',", base["{ id: 'bag_s',"]),
        ("冻结 万妖免费出手未动", "const ACT_BOSS_FREE_STRIKES = 3;", base["const ACT_BOSS_FREE_STRIKES = 3;"]),
        ("冻结 七日礼天数未动", "const ACT_CHECKIN_DAYS = 7;", base["const ACT_CHECKIN_DAYS = 7;"]),
        ("冻结 活动倍率帽未动", "const ACT_MULT_CAP = 10;", base["const ACT_MULT_CAP = 10;"]),
        ("冻结 jadeBalance 回执未动", "jadeBalance", base["jadeBalance"]),
        # ---- 红线（基线不变式）----
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
        print("  [%s] %-42s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 7) 语义自证：掉率经常量流入公式（公式行唯一 + 常量引用恰 2 处：定义 + 公式）；
    #    价格序 100<300<800<1000 保持
    sem_ok = (
        out.count("ACT_TOKEN_RATE_PER_10K") == 2
        and out.count("function actDropTokens(") == 1
        and out.count("price: 100,") == 1
        and out.count("price: 300,") == 1
        and out.count("price: 800,") == 1
        and out.count("price: 1000,") == 1
        and out.count("price: 2500") == 0
    )
    ok = ok and sem_ok
    print("  [%s] %-42s rate_refs=%d"
          % ("OK" if sem_ok else "FAIL", "R55 语义自证(常量唯一/价格序保持)",
             out.count("ACT_TOKEN_RATE_PER_10K")))

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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r055jade-", suffix=".tmp")
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
