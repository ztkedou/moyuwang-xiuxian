# -*- coding: utf-8 -*-
r"""
srv_patch_r201.py -- R-201 服务端渡劫修为门槛对齐客户端 R-183 分级倍率表（服务端环）

  ★ 用户原话（逐字，唯一依据）：
    「服务端渡劫的修为门槛与客户端曲线对齐 —— 客户端 0.9.30 起把升级所需修为乘了一张
     分级倍率表（R-183），服务端没跟上，口径不一致。」（用户已拍板「按你建议来」= 对齐。）

  ★ 环号说明：测试基座 _chainstage/s85.r198.ts（当前 SRV_CHAIN 链尾 = 85 环，末环 R-198）。
    本环顺延 **第 86 环**。锚点全部落在「Y4 渡劫天劫·境界数值表 + realmMaxExp」这一小块，
    与其余任何环零交集。

==============================================================================
零、问题（srv/index_v28.ts 字符级实测）
==============================================================================
  [客户端 0.9.30 起 · 产物 build/assets/index-v2935-20261008.js 实测]
    YLXW_R183_K=[14,6,4,2.5,1.5,1,1]      // 炼气 筑基 金丹 元婴 化神 合道 长生
    fe=[QiRefining, Foundation, GoldenCore, NascentSoul, SpiritSevering, DaoCombining, LongevityRealm]
    ad=(t,r=1)=>{ const a=Cs[t]||Cs[QiRefining], l=Math.min(9,Math.max(1,Math.floor(r))),
                  __r183i=fe.indexOf(t), __r183k=(__r183i>=0&&YLXW_R183_K[__r183i])||1;
                  return Math.floor(a.maxExpBase*(1+(l-1)*pN)*__r183k) } /*[r183exp]*/

  [服务端 · srv/index_v28.ts]
    · TRIB_REALM_BASES @4890-4898：maxExpBase 仍是**未乘 K** 的原值（60000 … 452500000）。
    · TRIB_LEVEL_EXP_FACTOR @4899 = 0.24；注释仍写「ad(realm,lv)=floor(maxExpBase*(1+(lv-1)*0.24)) 同源」。
    · realmMaxExp() @4901-4905：
        return Math.floor(base * (1 + (lv - 1) * TRIB_LEVEL_EXP_FACTOR));   // ★ 没有 K
    · 渡劫判定用服务端 maxExp 做门槛：normalizeRealm() @13848 回 maxExp: realmMaxExp(...)，
      再由 GET /api/rebirth/status @13864 `const expOk = nr.exp >= nr.maxExp;` 判满。
    ⇒ 后果：客户端显示「还差很多」时，服务端可能已判满（两端口径不一致）。本环把 K 补上对齐。

==============================================================================
一、改动点（3 处；锚点全部纯 ASCII 且唯一）
==============================================================================
  [1] 在 `const TRIB_LEVEL_EXP_FACTOR = 0.24;` 之前插入 **同序 K 表** `TRIB_REALM_R183_K`
      （Record<string, number>；键与 TRIB_REALM_BASES 逐字一致、同序：炼气/筑基/金丹/元婴/化神/合道/长生
       → 14/6/4/2.5/1.5/1/1）。幂等标记 /*[r201k]*/ 落此。未知境界由 realmMaxExp 侧 `?? 1` 兜底。
  [2] 更新 TRIB_LEVEL_EXP_FACTOR 旁「与客户端 ad() 同源」注释 → 标注「已含 R-183 的 K 表」。
      （锚点取注释中**纯 ASCII** 的算式片段，避免拿中文当锚点。）
  [3] realmMaxExp() 返回值**再乘 K**：floor(base × (1+(lv-1)×factor) × K) —— 与客户端 ad() 逐项对应。

  ★ 不动：TRIB_REALM_BASES 表体（:4890-4898 一行未改）、tribulationEnemy（:4909 只用 base* 属性）、
    normalizeRealm（:13844 只调 realmMaxExp）、ARENA_TRIAL_REALMS 与其 arenaTrialMaxExp（:11812/:11873，
    **刻意不复用** realmMaxExp 的自有整数式算法，是有意为之，本环一行未动）。

==============================================================================
二、绕过 realmMaxExp() 直接读 maxExpBase 的其它落点（★ 只列不改，交主线决定）
==============================================================================
  · :11875 `arenaTrialMaxExp()` 读的是 **ARENA_TRIAL_REALMS[].maxExpBase**（另一张表 :11812-11820，
    非 TRIB_REALM_BASES），且 :11870-11872 明写「刻意不复用 realmMaxExp()」——自有整数式，**不属于本环口径**。
  · 全文件对 TRIB_REALM_BASES 的引用仅：realmMaxExp（读 maxExpBase）、tribulationEnemy（读 base* 属性）、
    ECON_REALM_ORDER/ACH_REALM_ORDER（只取 Object.keys 顺序）、normalizeRealm（只做存在性校验）。
    ⇒ **除 realmMaxExp 外，无任何地方直接读 TRIB_REALM_BASES[..].maxExpBase 做修为门槛判定**。
  · ARENA 侧的修为槽（arenaTrialMaxExp）与天劫修为门槛是**两套独立口径**（前者奖励/关卡曲线，
    后者渡劫门槛），本环按团队指令**不改 ARENA 侧**。

==============================================================================
契约
==============================================================================
  CLI：--src <path>（就地原子写回；写回前落 .bak-r201-<时间戳>）/ --check / --selftest（只验不写）。
  幂等：产物含 /*[r201k]*/ ⇒ SKIP（不写盘，rc=3）。
  退出码：0=成功；3=幂等跳过（产物已含标记）；1=契约/门禁失败；2=意外异常（IO/写回）。
  · 锚点唯一（count==1，纯 ASCII）；round-trip 正反双向自证后才原子写回。
  · 工程红线：不新增 require(（ESM 直跑）/ 不新增 res.status(403 / 不动 PRAGMA / 不新增 setInterval。
  · 服务端自证五步：--check rc=0 → 临时副本写回 → node --experimental-strip-types --check rc=0
    → 复跑 SKIP → 清理（--selftest 内置同款语法校验）。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（TS 源码合法块注释）
MARK = "/*[r201k]*/"

# ============================================================ 改动点（3 处）

# ── [1] 插入同序 K 表（MARK 落此）；紧贴 TRIB_LEVEL_EXP_FACTOR 之前 ──────────────
E1_OLD = "const TRIB_LEVEL_EXP_FACTOR = 0.24;"
E1_NEW = (
    MARK + "\n"
    "// R-201：客户端 R-183 修为分级倍率表（YLXW_R183_K）同序镜像 —— 键与 TRIB_REALM_BASES 逐字一致、同序。\n"
    "//   客户端 ad() 自 0.9.30 起再乘 K[realmIndex]；服务端 realmMaxExp() 自本环起同乘 K，与客户端逐项同源。\n"
    "//   未知境界兜底 K=1（不改变 realmMaxExp 对未知境界的既有 base 兜底行为）。\n"
    "const TRIB_REALM_R183_K: Record<string, number> = {\n"
    "  '炼气期': 14,\n"
    "  '筑基期': 6,\n"
    "  '金丹期': 4,\n"
    "  '元婴期': 2.5,\n"
    "  '化神期': 1.5,\n"
    "  '合道期': 1,\n"
    "  '长生境': 1,\n"
    "};\n"
    "const TRIB_LEVEL_EXP_FACTOR = 0.24;"
)

# ── [2] 更新同源注释（锚点取注释中纯 ASCII 的算式片段）──────────────────────────
E2_OLD = "ad(realm,lv)=floor(maxExpBase*(1+(lv-1)*0.24))"
E2_NEW = "ad(realm,lv)=floor(maxExpBase*(1+(lv-1)*0.24)*K) 已含 R-183 的 K 表"

# ── [3] realmMaxExp 返回值再乘 K（与客户端 ad() 逐项对应）──────────────────────
E3_OLD = "  return Math.floor(base * (1 + (lv - 1) * TRIB_LEVEL_EXP_FACTOR));"
E3_NEW = "  return Math.floor(base * (1 + (lv - 1) * TRIB_LEVEL_EXP_FACTOR) * (TRIB_REALM_R183_K[realm] ?? 1));"

EDITS = [
    ("R201 插入同序 K 表 TRIB_REALM_R183_K（MARK）", E1_OLD, E1_NEW),
    ("R201 同源注释标注已含 R-183 K 表", E2_OLD, E2_NEW),
    ("R201 realmMaxExp 再乘 K", E3_OLD, E3_NEW),
]

# ============================================================ 依赖（绝对在位，锚点唯一）

REQUIRES = [
    ("const TRIB_REALM_BASES: Record<", "==", 1, "境界数值表必须在位（本环表体一行未改）"),
    ("const TRIB_LEVEL_EXP_FACTOR = 0.24;", "==", 1, "层因子常量必须在位（本环在其前插 K 表）"),
    ("function realmMaxExp(realm: string, realmLevel: number): number {", "==", 1,
     "修为槽函数必须在位（本环改其返回值）"),
    ("const expOk = nr.exp >= nr.maxExp;", "==", 1, "渡劫修为门槛判定必须在位（本环对齐其口径）"),
    ("function arenaTrialMaxExp(realmIdx: number, layer: number): number {", "==", 1,
     "ARENA 自有整数式必须在位（本环一行未动）"),
    ("[r198free]", ">=", 1, "R-198 环必须已应用（链序约束：本环排其后）"),
    ("[r194dao]", ">=", 1, "R-194 环必须已应用（链序约束）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 境界表 / 函数（本环除 realmMaxExp 返回值外一行未动）
    "const TRIB_REALM_BASES: Record<",
    "'炼气期': { maxExpBase: 60000, baseAttack: 10, baseDefense: 5, baseMaxHp: 100 },",
    "const TRIB_LEVEL_EXP_FACTOR = 0.24;",
    "function realmMaxExp(realm: string, realmLevel: number): number {",
    "function tribulationEnemy(targetRealm: string)",
    # ARENA 侧刻意不复用的自有整数式（本环一行未动）
    "function arenaTrialMaxExp(realmIdx: number, layer: number): number {",
    "return Math.floor(base * (100 + 24 * (layer - 1)) / 100);",
    # 渡劫门槛消费点（本环只改其上游 realmMaxExp）
    "const expOk = nr.exp >= nr.maxExp;",
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
        ("R201 幂等标记在位", MARK, 1, "==", "本环已应用"),
        # ── K 表 ──
        ("R201 K 表定义", "const TRIB_REALM_R183_K: Record<string, number> = {", 1, "==", "同序镜像"),
        ("R201 K 炼气=14", "'炼气期': 14,", 1, "==", "client[0]"),
        ("R201 K 筑基=6", "'筑基期': 6,", 1, "==", "client[1]"),
        ("R201 K 金丹=4", "'金丹期': 4,", 1, "==", "client[2]"),
        ("R201 K 元婴=2.5", "'元婴期': 2.5,", 1, "==", "client[3]"),
        ("R201 K 化神=1.5", "'化神期': 1.5,", 1, "==", "client[4]"),
        ("R201 K 合道=1", "'合道期': 1,", 1, "==", "client[5]"),
        ("R201 K 长生=1", "'长生境': 1,", 1, "==", "client[6]"),
        # ── realmMaxExp 乘 K ──
        ("R201 realmMaxExp 乘 K（未知兜底 1）",
         "* (TRIB_REALM_R183_K[realm] ?? 1));", 1, "==", "floor(base×因子×K)"),
        ("R201 旧式（无 K）清零",
         "Math.floor(base * (1 + (lv - 1) * TRIB_LEVEL_EXP_FACTOR));", 0, "==", "旧返回值消失"),
        # ── 注释 ──
        ("R201 注释标注含 K 表", "已含 R-183 的 K 表", 1, "==", "同源注释更新"),
        # ── 冻结：表体 / 函数 / ARENA 侧 / 门槛消费点未动 ──
        ("R201 冻结·境界表头", "const TRIB_REALM_BASES: Record<", 1, "==", "未动"),
        ("R201 冻结·炼气表行", "'炼气期': { maxExpBase: 60000, baseAttack: 10, baseDefense: 5, baseMaxHp: 100 },", 1, "==", "未动"),
        ("R201 冻结·层因子常量", "const TRIB_LEVEL_EXP_FACTOR = 0.24;", 1, "==", "未动"),
        ("R201 冻结·realmMaxExp 签名", "function realmMaxExp(realm: string, realmLevel: number): number {", 1, "==", "未动"),
        ("R201 冻结·tribulationEnemy", "function tribulationEnemy(targetRealm: string)", 1, "==", "未动（只用 base* 属性）"),
        ("R201 冻结·ARENA 自有整数式", "return Math.floor(base * (100 + 24 * (layer - 1)) / 100);", 1, "==", "刻意不复用，未动"),
        ("R201 冻结·ARENA 函数", "function arenaTrialMaxExp(realmIdx: number, layer: number): number {", 1, "==", "未动"),
        ("R201 冻结·渡劫门槛消费点", "const expOk = nr.exp >= nr.maxExp;", 1, "==", "未动（上游已对齐）"),
        # ── 工程红线（相对计数）──
        ("R201 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403"),
        ("R201 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R201 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        ("R201 红线·无 require", "require(", 0, "==", "ESM 不新增 require"),
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
    """在临时副本上跑 node --experimental-strip-types --check；返回 (rc, node)（node 缺失 → (None,None)）。"""
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


def main():
    ap = argparse.ArgumentParser(description="R-201 服务端渡劫修为门槛对齐客户端 R-183 分级倍率表（服务端环）")
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
        sys.exit(3)

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

    # 6) 门禁（五元组）
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-46s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证（正向重放一致 + 逆向逐字节还原）
    if out != _apply(src):
        fail("round-trip(正向重构) mismatch")
    rt_ok, rt_msg = _roundtrip(out, src)
    if not rt_ok:
        fail("round-trip(逆向) mismatch：%s" % rt_msg)

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    # 8) 语法自证（node --experimental-strip-types --check；node 缺失则跳过）
    if a.check or a.selftest:
        rc, node = _node_check(out)
        print("  node --check rc=%s (%s)" % (rc, node or 'node not found (skipped)'))
        if rc not in (None, 0):
            fail("node --experimental-strip-types --check 未通过")
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r201-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r201k-", suffix=".tmp")
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
    except BaseException as e:
        print("[ERROR] %s: %s" % (type(e).__name__, e))
        sys.exit(2)
