# -*- coding: utf-8 -*-
r"""
srv_patch_r215.py -- R-215 整体升级经验 ÷2（服务端第 90 环）

  ★ 用户诉求（R-215，唯一依据）：
    「整体升级经验减半（÷2）。」

  ★ 目标：修为曲线 base 值 TRIB_REALM_BASES[*].maxExpBase **全部 ÷2**（保持整数），
    使「升到本境界第 lv 层所需修为」= floor(maxExpBase × (1 + (lv-1)×0.24) × K[realm])
    逐档恰好减半。

  ★ 环号：基座 _chainstage/s89.r211.ts（当前链尾 = 89 环；
    md5 a40670097c22074d4c5c31a444118057，与 srv/index_v28.ts **逐字节同源**）⇒ 本环顺延 **第 90 环**。
    锚点全部落在 TRIB_REALM_BASES 表区（含 7 行境界数据），与其余任何环零交集。

  ★ 客户端同源表（本环**必须**同步，见 localtest/yl_r217_ext.py）：
      bundle build/assets/index-v2944-20261009.js（md5 7dec9546b3b9849063338558ee8eadac）
      @246010 处的 Cs 表（每境界对象的 maxExpBase）。
      客户端 ad(t,r) = floor(Cs[t].maxExpBase × (1+(r-1)×0.24) × YLXW_R183_K[i])，
      与服务端 realmMaxExp() 逐档同源；两侧必须同值。

==============================================================================
零、改前取证（_chainstage/s89.r211.ts 字符级实测，全部 count==1）
==============================================================================
  [证据 1] TRIB_REALM_BASES @4901-4909（Record<string,{maxExpBase;baseAttack;baseDefense;baseMaxHp}>）：
      炼气期 60000 / 筑基期 390000 / 金丹期 1521000 / 元婴期 6592000 /
      化神期 26775000 / 合道期 104430000 / 长生境 452500000
  [证据 2] realmMaxExp(realm, realmLevel) @4925-4929：
      base = TRIB_REALM_BASES[realm]?.maxExpBase ?? 60000;
      lv   = min(9, max(1, floor(realmLevel||1)));
      return floor(base × (1 + (lv-1) × TRIB_LEVEL_EXP_FACTOR) × (TRIB_REALM_R183_K[realm] ?? 1));
      ⇒ maxExpBase 是「修为槽上限」的唯一 base 因子；本环只改它 ⇒ 整条曲线 ÷2。
  [证据 3] K 表 TRIB_REALM_R183_K @4914-4922（炼14/筑6/金4/元2.5/化1.5/合1/长1）
      与 TRIB_LEVEL_EXP_FACTOR = 0.24 @4923 —— **本环一字不动**。
  [证据 4] ARENA_TRIAL_REALMS @11931-11939 另有一份 maxExpBase（演武场试炼 NPC/奖励口径，
      与本表同值但**独立**）—— 本环**不动**（见「范围边界」）。

==============================================================================
一、★ 数值对照（仅 maxExpBase；其余字段与公式一律不动）
==============================================================================
  境界         改前           改后（÷2）
  炼气期       60000     ->   30000
  筑基期       390000    ->   195000
  金丹期       1521000   ->   760500
  元婴期       6592000   ->   3296000
  化神期       26775000  ->   13387500
  合道期       104430000 ->   52215000
  长生境       452500000 ->   226250000
  ⇒ 因 (1+(lv-1)×0.24) 与 K 均不变、7 个 base 均为偶数，逐档 floor 结果**恰好减半**
    （已数值推演复核，无 ±1 抖动）。

==============================================================================
二、改动点（8 处；锚点全部纯 ASCII 且唯一 count==1）
==============================================================================
  E1  MARK 注入：在 TRIB_REALM_BASES 声明行前插入 /*[r215exp]*/ 说明块注释（幂等标记）。
  E2..E8 7 个境界行：仅把 `maxExpBase: <旧值>` 换成 `<旧值 ÷ 2>`。
      锚点带 `baseAttack/baseDefense/baseMaxHp` 上下文 ⇒ 与 ARENA_TRIAL_REALMS 里同值的
      `maxExpBase: <旧值> }`（空格+右花括号）**不会撞锚**。

  ★ 范围边界（重要，供复核）：
    · 本环**只改 TRIB_REALM_BASES**（玩家修为槽 / 渡劫门槛口径）。
    · ARENA_TRIAL_REALMS.maxExpBase（演武场试炼「修为槽」奖励口径）**不动**：它影响的是
      试炼首通修为奖励 = floor(0.05 × arenaTrialMaxExp)，属**产出**侧、非「升级所需经验」；
      用户诉求为「升级经验 ÷2」，故不在本环范围。
    · 客户端 Cs 表由 localtest/yl_r217_ext.py 同步；本环**必须**双侧一致（命门）。

契约
--------------------------------------------------------------------------
  CLI：--src <path>（默认 _chainstage/s89.r211.ts；就地原子写回，写回前落 .bak-r215-<时间戳>）
       / --check / --selftest（只验不写）。
  幂等：产物含 /*[r215exp]*/ ⇒ SKIP（不写盘，rc=3）。
  退出码：0=成功/自检通过；1=门禁/往返失败；2=前置断言（依赖/锚点/冻结）不符或 IO 异常；3=幂等跳过。
  · 锚点唯一（count==1，纯 ASCII）；round-trip 正反双向自证后才原子写回。
  · 工程红线：不新增 require(（ESM 直跑）/ 不新增 res.status(403 / 不动 PRAGMA / 不新增 setInterval(。
  · 自证：--check rc=0 → 临时副本写回 → node --experimental-strip-types --check rc=0 → 复跑 SKIP rc=3。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.join("_chainstage", "s89.r211.ts")

# 幂等标记（TS 源码合法块注释）
MARK = "/*[r215exp]*/"

# ============================================================ 改动点（8 处）

# ── [1] MARK 注入（声明行前加说明注释；锚点=纯 ASCII 声明行，唯一）──────────────
E1_OLD = ("const TRIB_REALM_BASES: Record<string, { maxExpBase: number; baseAttack: number; "
          "baseDefense: number; baseMaxHp: number }> = {")
E1_NEW = (
    "// " + MARK + " R-215：整体升级经验 ÷2 —— 仅下调本表 7 个 maxExpBase（其余字段/公式/K 表一律不动）。\n"
    "//   客户端同源表 Cs（bundle @246010）同步 ÷2，见 localtest/yl_r217_ext.py。\n"
    + E1_OLD
)

# ── [2..8] 7 个境界行：仅 maxExpBase ÷2（锚点带 baseAttack/baseDefense/baseMaxHp 上下文，纯 ASCII）──
E2_OLD = "maxExpBase: 60000, baseAttack: 10, baseDefense: 5, baseMaxHp: 100 },"
E2_NEW = "maxExpBase: 30000, baseAttack: 10, baseDefense: 5, baseMaxHp: 100 },"

E3_OLD = "maxExpBase: 390000, baseAttack: 25, baseDefense: 12, baseMaxHp: 250 },"
E3_NEW = "maxExpBase: 195000, baseAttack: 25, baseDefense: 12, baseMaxHp: 250 },"

E4_OLD = "maxExpBase: 1521000, baseAttack: 50, baseDefense: 25, baseMaxHp: 625 },"
E4_NEW = "maxExpBase: 760500, baseAttack: 50, baseDefense: 25, baseMaxHp: 625 },"

E5_OLD = "maxExpBase: 6592000, baseAttack: 125, baseDefense: 62, baseMaxHp: 1250 },"
E5_NEW = "maxExpBase: 3296000, baseAttack: 125, baseDefense: 62, baseMaxHp: 1250 },"

E6_OLD = "maxExpBase: 26775000, baseAttack: 312, baseDefense: 156, baseMaxHp: 3125 },"
E6_NEW = "maxExpBase: 13387500, baseAttack: 312, baseDefense: 156, baseMaxHp: 3125 },"

E7_OLD = "maxExpBase: 104430000, baseAttack: 781, baseDefense: 390, baseMaxHp: 7812 },"
E7_NEW = "maxExpBase: 52215000, baseAttack: 781, baseDefense: 390, baseMaxHp: 7812 },"

E8_OLD = "maxExpBase: 452500000, baseAttack: 1953, baseDefense: 976, baseMaxHp: 19531 },"
E8_NEW = "maxExpBase: 226250000, baseAttack: 1953, baseDefense: 976, baseMaxHp: 19531 },"

EDITS = [
    ("R215 MARK 注入 + 说明块", E1_OLD, E1_NEW),
    ("R215 炼气期 60000 -> 30000", E2_OLD, E2_NEW),
    ("R215 筑基期 390000 -> 195000", E3_OLD, E3_NEW),
    ("R215 金丹期 1521000 -> 760500", E4_OLD, E4_NEW),
    ("R215 元婴期 6592000 -> 3296000", E5_OLD, E5_NEW),
    ("R215 化神期 26775000 -> 13387500", E6_OLD, E6_NEW),
    ("R215 合道期 104430000 -> 52215000", E7_OLD, E7_NEW),
    ("R215 长生境 452500000 -> 226250000", E8_OLD, E8_NEW),
]

# ============================================================ 依赖（绝对在位，锚点唯一）

REQUIRES = [
    (E1_OLD, "==", 1, "TRIB_REALM_BASES 声明行必须在位（本环在其前插 MARK）"),
    ("function realmMaxExp(", "==", 1, "修为槽公式必须在位（本环不动）"),
    ("const TRIB_REALM_R183_K: Record<string, number> = {", "==", 1, "K 倍率表必须在位（本环不动）"),
    ("const TRIB_LEVEL_EXP_FACTOR = 0.24;", "==", 1, "0.24 系数必须在位（本环不动）"),
    ("const ARENA_TRIAL_REALMS = [", "==", 1, "演武场境界表必须在位（本环不动）"),
    (E2_OLD, "==", 1, "炼气期行必须在位"),
    (E3_OLD, "==", 1, "筑基期行必须在位"),
    (E4_OLD, "==", 1, "金丹期行必须在位"),
    (E5_OLD, "==", 1, "元婴期行必须在位"),
    (E6_OLD, "==", 1, "化神期行必须在位"),
    (E7_OLD, "==", 1, "合道期行必须在位"),
    (E8_OLD, "==", 1, "长生境行必须在位"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    "const TRIB_REALM_BASES",
    "const TRIB_REALM_R183_K",
    "const TRIB_LEVEL_EXP_FACTOR = 0.24;",
    "function realmMaxExp(",
    "const TRIB_ENEMY_SCALE",
    "const ARENA_TRIAL_REALMS",
    "const ARENA_M_MULT",
    # 工程红线（相对计数）
    "res.status(403",
    "setInterval(",
    "PRAGMA",
    "require(",
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out: str, base):
    """五元组 (label, needle, expect, op, note)；base = 冻结针脚在**基座**上的计数。"""
    return [
        ("R215 幂等标记在位", MARK, 1, "==", "本环已应用"),
        # ── 新值（TRIB_REALM_BASES，各 1 次）──
        ("R215 炼气期=30000", E2_NEW, 1, "==", "60000/2"),
        ("R215 筑基期=195000", E3_NEW, 1, "==", "390000/2"),
        ("R215 金丹期=760500", E4_NEW, 1, "==", "1521000/2"),
        ("R215 元婴期=3296000", E5_NEW, 1, "==", "6592000/2"),
        ("R215 化神期=13387500", E6_NEW, 1, "==", "26775000/2"),
        ("R215 合道期=52215000", E7_NEW, 1, "==", "104430000/2"),
        ("R215 长生境=226250000", E8_NEW, 1, "==", "452500000/2"),
        # ── 旧值清零（TRIB_REALM_BASES，各 0 次）──
        ("R215 旧炼气期清零", E2_OLD, 0, "==", "旧 base 消失"),
        ("R215 旧筑基期清零", E3_OLD, 0, "==", "旧 base 消失"),
        ("R215 旧金丹期清零", E4_OLD, 0, "==", "旧 base 消失"),
        ("R215 旧元婴期清零", E5_OLD, 0, "==", "旧 base 消失"),
        ("R215 旧化神期清零", E6_OLD, 0, "==", "旧 base 消失"),
        ("R215 旧合道期清零", E7_OLD, 0, "==", "旧 base 消失"),
        ("R215 旧长生境清零", E8_OLD, 0, "==", "旧 base 消失"),
        # ── 冻结：公式 / K 表 / 系数未动 ──
        ("R215 冻结·公式 realmMaxExp", "function realmMaxExp(realm: string, realmLevel: number): number {", 1, "==", "未动"),
        ("R215 冻结·0.24 系数", "const TRIB_LEVEL_EXP_FACTOR = 0.24;", 1, "==", "未动"),
        ("R215 冻结·K 表头", "const TRIB_REALM_R183_K: Record<string, number> = {", 1, "==", "未动"),
        ("R215 冻结·K 炼气=14", "'炼气期': 14,", 1, "==", "未动"),
        ("R215 冻结·K 长生=1", "'长生境': 1,", 1, "==", "未动"),
        # ── 冻结：同对象的 baseAttack/baseDefense/baseMaxHp 未动 ──
        ("R215 冻结·炼气属性未动", "baseAttack: 10, baseDefense: 5, baseMaxHp: 100 },", 1, "==", "仅 base 变"),
        ("R215 冻结·长生属性未动", "baseAttack: 1953, baseDefense: 976, baseMaxHp: 19531 },", 1, "==", "仅 base 变"),
        # ── 冻结：ARENA_TRIAL_REALMS 的同值 maxExpBase 未动（独立口径，本环不碰）──
        ("R215 冻结·arena 炼气 base 未动", "maxExpBase: 60000 }", 1, "==", "演武场不动"),
        ("R215 冻结·arena 筑基 base 未动", "maxExpBase: 390000 }", 1, "==", "演武场不动"),
        ("R215 冻结·arena 金丹 base 未动", "maxExpBase: 1521000 }", 1, "==", "演武场不动"),
        ("R215 冻结·arena 元婴 base 未动", "maxExpBase: 6592000 }", 1, "==", "演武场不动"),
        ("R215 冻结·arena 化神 base 未动", "maxExpBase: 26775000 }", 1, "==", "演武场不动"),
        ("R215 冻结·arena 合道 base 未动", "maxExpBase: 104430000 }", 1, "==", "演武场不动"),
        ("R215 冻结·arena 长生 base 未动", "maxExpBase: 452500000 }", 1, "==", "演武场不动"),
        # ── 工程红线（相对计数）──
        ("R215 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403"),
        ("R215 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R215 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        ("R215 红线·无 require", "require(", 0, "==", "ESM 不新增 require"),
    ]


def _apply(src: str) -> str:
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)
    return out


def _roundtrip(out: str, src: str):
    back = out
    for name, old, new in reversed(EDITS):
        if back.count(new) != 1:
            return False, "逆向：%s 的新块出现 %d 次（期望 1）" % (name, back.count(new))
        back = back.replace(new, old, 1)
    return (back == src), "逆向逐字节还原"


def _find_node():
    cand = [os.environ.get('YL_NODE'), os.environ.get('NODE'), shutil.which('node')]
    nroot = 'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions'
    if os.path.isdir(nroot):
        subs = sorted(os.path.join(nroot, d, 'node.exe') for d in os.listdir(nroot))
        cand += [p for p in reversed(subs) if os.path.isfile(p)]
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(text: str):
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.ts')
    try:
        with io.open(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        r = subprocess.run([node, '--experimental-strip-types', '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _run_gates(out, base):
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-46s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    return ok


def _verify(out, src, base, do_node, tag):
    if not _run_gates(out, base):
        fail("门禁未全绿，未写回")
    if out != _apply(src):
        fail("round-trip(正向重构) mismatch")
    rt_ok, rt_msg = _roundtrip(out, src)
    if not rt_ok:
        fail("round-trip(逆向) mismatch：%s" % rt_msg)
    print("  %s delta = %+d chars  (%d -> %d)" % (tag, len(out) - len(src), len(src), len(out)))
    if do_node:
        rc, node = _node_check(out)
        print("  node --check rc=%s (%s)" % (rc, node or 'node not found (skipped)'))
        if rc not in (None, 0):
            fail("node --experimental-strip-types --check 未通过")


def main():
    ap = argparse.ArgumentParser(description="R-215 整体升级经验 ÷2（服务端第 90 环）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：产物含标记 ⇒ SKIP（不写盘，rc=3）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return 3

    # 2) 依赖（绝对在位）
    for needle, op, cnt, why in REQUIRES:
        n = src.count(needle)
        good = (n == cnt) if op == "==" else (n >= cnt)
        if not good:
            fail("依赖未满足（%r 出现 %d 次，期望 %s %d）：%s" % (needle[:80], n, op, cnt, why))

    # 3) 锚点唯一 + 纯 ASCII
    for name, old, new in EDITS:
        if not all(ord(c) < 128 for c in old):
            fail("%s 锚点含非 ASCII 字符（违反工程约束）" % name)
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线（针脚必须在基座真实存在，防拼错导致冻结静默失效）
    base = {k: src.count(k) for k in BASE_NEEDLES}
    for k in BASE_NEEDLES:
        if base[k] <= 0 and k != "require(":  # require( 合法基线 = 0（ESM 红线）
            fail("冻结针脚在基座不存在（拼写错误？）：%r" % k[:90])

    # 5) 应用
    out = _apply(src)

    # 6) 门禁 + 往返 + 语法
    _verify(out, src, base, do_node=(a.check or a.selftest), tag="--check")

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return 0

    # 7) 改前 .bak + 原子写回
    bak = "%s.bak-r215-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r215exp-", suffix=".tmp")
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
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:
        print("[ERROR] %s: %s" % (type(e).__name__, e))
        sys.exit(2)
