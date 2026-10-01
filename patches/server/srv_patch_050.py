# -*- coding: utf-8 -*-
r"""
srv_patch_050.py -- R-050 洞府：每日催熟基础值 3→10 且公式改「逐级 +3/+2」（服务端半边 · SRV_CHAIN 第 35 环）

两件事：① 把 t10_farm 定档常量 `FARM_BOOST_BASE_CAP` 从 3 改为 10；
② 把 farmBoostCap 的公式从「+1 次/2 级」改为「每升 1 级 +3（前 4 级）/ +2（其后）」。
   （用户原话：「洞府升级是比较困难的，改为每一级提高 2-3」，且建议前几级 +3 更爽。）
每田每日 1 次闸门、催熟计价（起价/单价）全部不动。

为什么改这里（口径证据，与 yl_050_ext.py 配套）
--------------------------------------------------------------------------
  R-050 原文：「每日催熟次数也增加到最简陋的10次起步，根据洞府等级相应增加。」
  · 全游戏「每日催熟 X 次」文案 = 洞府页「灵田联动」行（grotto087 T9-F4 写死的
    客户端展示 3+floor(级/2)），其服务端真身就是 farmBoostCap：
        FARM_BOOST_BASE_CAP(3) + floor(max(0, 洞府等级)/2)
  · 该上限由 /farm/boost 用 farm_daily_care 表强执法（409 文案与 boostDaily 回执
    都走 farmBoostCap），只改客户端展示会造成「显示 10 实际 3」的假达标。
  · t10_farm 设计即「定档只改常数/纯函数、端点零改动」→ 本环只动常数与纯函数体。
  · 新梯度（与客户端两处展示同式）：
        cap(L) = 10 + 3*min(max(0,L-1), 4) + 2*max(0, L-5)
        L1=10 L2=13 L3=16 L4=19 L5=22 L6=24 L7=26 L8=28 L9=30 L10=32
    简陋洞府（1 级）= 10 次起步 ✓；每升 1 级 +3（前 4 级）/ +2（其后）✓。
  · 催熟是纯灵石回收口（费用恒高于作物净收益），抬高次数只加大回收口、
    不构成刷钱口，经济方向安全。

客户端半边（yl_050_ext.py，另一环）
--------------------------------------------------------------------------
  两处「每日催熟 3+floor(级/2)」展示同步改 10+floor(级/2)；洞府灵草园的
  「灵石加速一次半小时」也在那一环（本服务端不涉灵草园，plantedHerbs 不进服务端）。

CLI 契约（与链上其余补丁一致，照 srv_patch_r039.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` / `--selftest` 只校验不写。
  幂等：产物里已含 `[r050boost]` 标记或 `FARM_BOOST_BASE_CAP = 10` 则 SKIP。
  lead 接线：localtest/chain_build.py 的 SRV_CHAIN 链尾追加 'srv_patch_050.py'
  （第 35 环，现末环 srv_patch_r039.py 之后；仅要求 t10_farm 第 7 环在前）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval` / `PRAGMA`。
  · 本环是纯常数替换：不插入任何新代码块，无 zh()/注入块需求。
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
MARK = "[r050boost]"

# ============================================================ 唯一改动点（四处替换）

# ① 常数行（其行尾注释见 ② 单独同步，避免锚点跨越中文注释）
EDIT_CAP_OLD = "const FARM_BOOST_BASE_CAP = 3;"
EDIT_CAP_NEW = "const FARM_BOOST_BASE_CAP = 10;"

# ② 常数行尾注释：旧式「+1 次/2 级」→ 新式「逐级 +3/+2」（防注释骗人）
CAP_TAIL_OLD = "// #6 每日催熟总次数基础值（+1 次/2 级洞府，见 farmBoostCap）"
CAP_TAIL_NEW = "// #6 每日催熟总次数基础值（R-050：逐级 +3/+2，见 farmBoostCap）"

# ③ farmBoostCap 公式体：旧「+1 次/2 级」→ 新「每级 +3（前 4 级）/ +2（其后）」。
#    与客户端两处展示（yl_050_ext.py）逐式同构；L1=10 L2=13 … L5=22 … L10=32。
FORMULA_OLD = "return FARM_BOOST_BASE_CAP + Math.floor(Math.max(0, grottoLevel) / 2);"
FORMULA_NEW = ("return FARM_BOOST_BASE_CAP + 3 * Math.min(Math.max(0, grottoLevel - 1), 4) "
               "+ 2 * Math.max(0, grottoLevel - 5);")

# ④ farmBoostCap 说明注释（同步公式并落 R-050 标记，防注释骗人）
EDIT_CMT_OLD = ("// T10 每日催熟总次数上限（纯）：基础 3 + 1 次/2 级洞府"
                "（#6；与客户端洞府页联动展示同式）")
EDIT_CMT_NEW = ("// T10 每日催熟总次数上限（纯）：基础 10 + 逐级 +3/+2（L1=10…L10=32）"
                "（#6；与客户端洞府页联动展示同式）[r050boost] R-050：基础 3→10 且公式改逐级 +3/+2"
                "（客户端两处展示同步见 yl_050_ext.py）")

EDITS = [
    ("R050 催熟基础次数 3→10", EDIT_CAP_OLD, EDIT_CAP_NEW),
    ("R050 常数行尾注释同步", CAP_TAIL_OLD, CAP_TAIL_NEW),
    ("R050 公式改逐级 +3/+2", FORMULA_OLD, FORMULA_NEW),
    ("R050 farmBoostCap 注释同步", EDIT_CMT_OLD, EDIT_CMT_NEW),
]

# 前置依赖（本环只读这些串做自证，不改）
REQUIRES = [
    (EDIT_CAP_OLD, 1, "待改常数行必须在位（本环数值改动点）"),
    (CAP_TAIL_OLD, 1, "待改常数行尾注释必须在位（本环同步改注释）"),
    (FORMULA_OLD, 1, "待改公式必须在位（本环改公式体）"),
    ("function farmBoostCap(", 1, "上限纯函数必须在位（改动经它生效）"),
    (EDIT_CMT_OLD, 1, "待改注释行必须在位（本环同步改注释）"),
    ("app.post('/api/farm/boost'", 1, "催熟端点必须在位（409 上限文案自动跟随）"),
    ("boostDaily: { used: boostUsed, cap: farmBoostCap(grottoLevel) }",
     1, "status 回执必须在位（farm087 面板 used/cap 的来源）"),
    ("今日催熟总次数已尽", 1, "409 文案必须在位（内插 farmBoostCap，自动跟随）"),
    ("CREATE TABLE IF NOT EXISTS farm_daily_care (",
     1, "强执法表必须在位（每田每日 1 次 + 总次数 COUNT 复核，本环不动）"),
]

# 冻结基线（打补丁前统计，打完后必须不变）
BASE_NEEDLES = ["res.status(403", "setInterval(", "PRAGMA", "require(",
                "farm_daily_care", "function farmBoostCap(",
                "app.post('/api/farm/boost'",
                "boostDaily: { used: boostUsed, cap: farmBoostCap(grottoLevel) }"]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-050 每日催熟基础次数 3→10 环")
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
    if (MARK in src) or ("const FARM_BOOST_BASE_CAP = 10;" in src):
        print("[SKIP] source looks already patched（已含 %s 或 FARM_BOOST_BASE_CAP = 10）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点计数（本环全部是「常数替换」型：old 不保留进 new 是本意，无自毁防线需求）
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
        ("R50 基础值已改 10", "const FARM_BOOST_BASE_CAP = 10;", 1),
        ("R50 旧基础值已清零", "const FARM_BOOST_BASE_CAP = 3;", 0),
        ("R50 公式已改逐级 +3/+2", FORMULA_NEW, 1),
        ("R50 旧公式已清零", FORMULA_OLD, 0),
        ("R50 常数行尾注释已同步", CAP_TAIL_NEW, 1),
        ("R50 旧常数行尾注释已清零", CAP_TAIL_OLD, 0),
        ("R50 注释已同步（逐级 +3/+2）", "基础 10 + 逐级 +3/+2", 1),
        ("R50 旧注释（基础 3）已清零", "基础 3 + 1 次/2 级洞府", 0),
        ("R50 幂等标记就位", MARK, 1),
        # ---- 冻结：闸门 / 回执 / 端点一字不动 ----
        ("冻结 boostDaily 回执未动",
         "boostDaily: { used: boostUsed, cap: farmBoostCap(grottoLevel) }", 1),
        ("冻结 催熟端点仍在", "app.post('/api/farm/boost'", base["app.post('/api/farm/boost'"]),
        ("冻结 farm_daily_care 计数不变", "farm_daily_care", base["farm_daily_care"]),
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
        print("  [%s] %-42s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 7) 语义自证：改动后 1 级洞府上限 = 10（基础值本身），公式引用未断
    sem_ok = (
        out.count("const FARM_BOOST_BASE_CAP = 10;") == 1
        and out.count("FARM_BOOST_BASE_CAP") == 2  # 常数定义 + farmBoostCap 引用
        and out.count("function farmBoostCap(") == 1
    )
    ok = ok and sem_ok
    print("  [%s] %-42s cap_refs=%d"
          % ("OK" if sem_ok else "FAIL", "R50 语义自证(常数唯一/引用完整)",
             out.count("FARM_BOOST_BASE_CAP")))

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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r050boost-", suffix=".tmp")
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
