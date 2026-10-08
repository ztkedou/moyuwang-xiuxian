# -*- coding: utf-8 -*-
r"""
srv_patch_r196.py -- R-196 妖灵「灵纹」前 4 条加成重设（服务端环）

  ★ 用户拍板（逐字）：「4. 数值可以微改，属性要重新设置一下。」
  ★ 上一轮（r189c）已取证：前 4 条灵纹**全部已实装生效**（不是"只显示不生效"）。
    本环按用户意图把前 4 条的**加成类型重设 + 数值微改**，后 2 条（蕴纹 expMul / 天纹 ppMul）
    **一字不动**。

锚点落区（与其余任何环零交集）
--------------------------------------------------------------------------
  全部落在 R-018 妖灵核心块内的「灵纹表 + 灵纹效果纯函数 + 灵纹存档 payload」：
    · R018B_RUNE_TABLE        （约 6716-6723）
    · r018bRuneEffect         （约 6738-6752）
    · r018bApplyRune          （约 6754-6768）
  ★ 这三处只被 r018bSpiritBonus / r018SpiritSync / POST /api/pet/rune 引用，均为同块内。

改前 → 改后（前 4 条；后 2 条逐字不动）
--------------------------------------------------------------------------
  #  名     原加成(kind/value)                       新加成
  1  锐纹   critRate       0.015                     critRate 0.02  + critDamage 0.08（第二属性）
  2  御纹   damageReduction 0.02                      damageReduction 0.03
  3  疾纹   dodgeRate      0.015                     dodgeRate 0.02
  4  噬纹   lifeLeech      0.01                      lifeLeech 0.02
  5  蕴纹   expMul         0.30   ← 逐字不动
  6  天纹   ppMul          0.10   ← 逐字不动

  为什么给锐纹加「暴击伤害」：锐=攻击向，只给暴击率而无暴伤时，暴击收益被 1.5x 固定倍率锁死；
  补 critDamage 让"暴击"这一属性有真实伤害意义（战斗层 crit 倍率 = 1.5 + critDamage）。
  · critDamage 在客户端白名单内且**未被灵纹占用**（YlxwBattleBonus 的 o.critDamage 由羁绊层
    写入，灵纹此前 0 占用），并在**快速结算**（`1.5 + YlxwPB.critDamage`）与**回合制**
    （buffs 里 `critDamage` 累加）两套引擎都有读取点。
  · 御/疾 的「防御%/身法%」副属性**已放弃**：petSpirit.defense/speed 是"妖灵属性 × 0.10 × PP"
    的绝对小值（10 级凡阶约 +2），再乘 5% ≈ +0.1 且被 floor 抹掉 ⇒ 属"只显示不生效"，故不加。

强度换算（封顶 YlxwBattleCapCfg = critRate .35 / critDamage .8 / dodgeRate .35 / lifeLeech .25 /
damageReduction .5）：
  锐 0.02（封顶 5.7%）/ 暴伤 0.08（封顶 10%）/ 御 0.03（封顶 6%）/ 疾 0.02（5.7%）/ 噬 0.02（8%）
  ⇒ 全部远低于封顶，与羁绊层 + 装备词条叠加后仍不撞顶（羁绊层 critDamage 上限 0.4，加 0.08 = 0.48 < 0.8）。

契约
--------------------------------------------------------------------------
  CLI：--src <path>（就地原子写回；写回前落 .bak-r196-<时间戳>）/ --check / --selftest（只验不写）。
  幂等：产物含 /*[r196rune]*/ ⇒ SKIP（不写盘，rc=0）。
  退出码：0=成功/跳过；1=契约/门禁失败；2=意外异常（IO/写回）。
  · 锚点唯一（count==1）；round-trip 正反双向自证后才原子写回。
  · 工程红线：不新增 require(（ESM 直跑）/ 不新增 res.status(403 / 不动 PRAGMA / 不新增 setInterval。
  · 不改 srv/index_v28.ts 本体（由 chain_build 落盘）；不改任何既有 srv_patch_*.py。
  ★ 服务端源码的中文为**真实 UTF-8 字符**（非客户端 bundle 的 \uXXXX）⇒ desc 同步的锚点必然含中文；
    本脚本以"整行唯一"保证锚点不歧义（见 REQUIRES/EDITS 的 count==1 断言）。
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（TS 源码合法块注释）
MARK = "/*[r196rune]*/"

# ============================================================ 改动点（6 处）

# ── [1] 表类型：补第二属性可选字段 kind2/value2 ──────────────────────────────
E1_OLD = (
    "const R018B_RUNE_TABLE: Record<string, { key: string; name: string; unlock: number; "
    "kind: string; value: number; desc: string }> = {"
)
E1_NEW = (
    "const R018B_RUNE_TABLE: Record<string, { key: string; name: string; unlock: number; "
    "kind: string; value: number; kind2?: string; value2?: number; desc: string }> = { " + MARK
)

# ── [2] 前 4 条表行：重设属性 + 数值微改 + desc 同步（后 2 条不在锚点内） ──────
E2_OLD = (
    "  rui:  { key: 'rui',  name: '锐纹', unlock: 10, kind: 'critRate',        value: 0.015, desc: '主人暴击率 +1.5%' },\n"
    "  yu:   { key: 'yu',   name: '御纹', unlock: 20, kind: 'damageReduction', value: 0.02,  desc: '主人减伤 +2%' },\n"
    "  ji:   { key: 'ji',   name: '疾纹', unlock: 30, kind: 'dodgeRate',       value: 0.015, desc: '主人闪避 +1.5%' },\n"
    "  shi:  { key: 'shi',  name: '噬纹', unlock: 40, kind: 'lifeLeech',       value: 0.01,  desc: '主人吸血 +1%' },"
)
E2_NEW = (
    "  rui:  { key: 'rui',  name: '锐纹', unlock: 10, kind: 'critRate',        value: 0.02,  kind2: 'critDamage', value2: 0.08, desc: '主人暴击率 +2%、暴击伤害 +8%' },\n"
    "  yu:   { key: 'yu',   name: '御纹', unlock: 20, kind: 'damageReduction', value: 0.03,  desc: '主人减伤 +3%' },\n"
    "  ji:   { key: 'ji',   name: '疾纹', unlock: 30, kind: 'dodgeRate',       value: 0.02,  desc: '主人闪避 +2%' },\n"
    "  shi:  { key: 'shi',  name: '噬纹', unlock: 40, kind: 'lifeLeech',       value: 0.02,  desc: '主人吸血 +2%' },"
)

# ── [3] 效果函数：返回类型 + zero 增加 critDamage ────────────────────────────
E3_OLD = (
    "function r018bRuneEffect(key: unknown, level: unknown): { key: string; critRate: number; "
    "dodgeRate: number; lifeLeech: number; damageReduction: number; expMul: number; ppMul: number } {\n"
    "  const zero = { key: '', critRate: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0, expMul: 0, ppMul: 1 };"
)
E3_NEW = (
    "function r018bRuneEffect(key: unknown, level: unknown): { key: string; critRate: number; "
    "critDamage: number; dodgeRate: number; lifeLeech: number; damageReduction: number; expMul: number; ppMul: number } {\n"
    "  const zero = { key: '', critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0, expMul: 0, ppMul: 1 };"
)

# ── [4] 效果函数：第二属性 kind2 分派（仅锐纹） ──────────────────────────────
E4_OLD = (
    "  else if (d.kind === 'ppMul') o.ppMul = 1 + d.value;\n"
    "  return o;"
)
E4_NEW = (
    "  else if (d.kind === 'ppMul') o.ppMul = 1 + d.value;\n"
    "  if (d.kind2 === 'critDamage') o.critDamage = d.value2 || 0;\n"
    "  return o;"
)

# ── [5] payload 函数：入参类型增加 critDamage ────────────────────────────────
E5_OLD = (
    "function r018bApplyRune(b: { pp: number; attack: number; defense: number; maxHp: number; speed: number }, "
    "rn: { key: string; critRate: number; dodgeRate: number; lifeLeech: number; damageReduction: number; ppMul: number }): any {"
)
E5_NEW = (
    "function r018bApplyRune(b: { pp: number; attack: number; defense: number; maxHp: number; speed: number }, "
    "rn: { key: string; critRate: number; critDamage: number; dodgeRate: number; lifeLeech: number; damageReduction: number; ppMul: number }): any {"
)

# ── [6] payload 函数：新增 runeCritDmg 键（紧邻既有 runeCrit，供客户端读取） ──
E6_OLD = (
    "    runeCrit: rn ? rn.critRate : 0,\n"
    "    runeDodge: rn ? rn.dodgeRate : 0,"
)
E6_NEW = (
    "    runeCrit: rn ? rn.critRate : 0,\n"
    "    runeCritDmg: rn ? rn.critDamage : 0,\n"
    "    runeDodge: rn ? rn.dodgeRate : 0,"
)

# ── [7] r018bRuneDef 返回类型：同步补 kind2/value2（类型自洽，非语义改动） ──────
E7_OLD = (
    "function r018bRuneDef(key: unknown): { key: string; name: string; unlock: number; "
    "kind: string; value: number; desc: string } | null {"
)
E7_NEW = (
    "function r018bRuneDef(key: unknown): { key: string; name: string; unlock: number; "
    "kind: string; value: number; kind2?: string; value2?: number; desc: string } | null {"
)

EDITS = [
    ("R196 表类型补 kind2/value2", E1_OLD, E1_NEW),
    ("R196 前4条表行重设（锐/御/疾/噬）", E2_OLD, E2_NEW),
    ("R196 效果函数返回类型+zero 补 critDamage", E3_OLD, E3_NEW),
    ("R196 效果函数 kind2 分派", E4_OLD, E4_NEW),
    ("R196 payload 入参类型补 critDamage", E5_OLD, E5_NEW),
    ("R196 payload 新增 runeCritDmg 键", E6_OLD, E6_NEW),
    ("R196 r018bRuneDef 返回类型补 kind2/value2", E7_OLD, E7_NEW),
]

# ============================================================ 依赖（绝对在位，锚点唯一）

REQUIRES = [
    ("const R018B_RUNE_TABLE", "==", 1, "灵纹表必须在位（本环主改点）"),
    ("function r018bRuneDef(", "==", 1, "灵纹定义函数必须在位（本环不动）"),
    ("function r018bRuneList(", "==", 1, "灵纹列表函数必须在位（本环不动）"),
    ("function r018bRuneEffect(", "==", 1, "灵纹效果纯函数必须在位"),
    ("function r018bApplyRune(", "==", 1, "灵纹存档 payload 函数必须在位"),
    ("function r018bSpiritBonus(", "==", 1, "灵纹包装函数必须在位（本环不动）"),
    ("function r018SpiritSync(", "==", 1, "妖灵同步函数必须在位（本环不动）"),
    ("  yun:  { key: 'yun',  name: '蕴纹', unlock: 50, kind: 'expMul',          value: 0.30,  desc: '妖灵秘径修为产出 +30%' },", "==", 1, "蕴纹行必须在位（本环逐字不动）"),
    ("  tian: { key: 'tian', name: '天纹', unlock: 60, kind: 'ppMul',           value: 0.10,  desc: '妖灵之力 PP ×1.10' },", "==", 1, "天纹行必须在位（本环逐字不动）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 后 2 条逐字不动
    "kind: 'expMul',          value: 0.30,",
    "kind: 'ppMul',           value: 0.10,",
    # 灵纹核心函数签名（本环不改签名语义，仅扩类型）
    "function r018bRuneDef(",
    "function r018bRuneList(",
    "function r018bSpiritBonus(",
    "function r018SpiritSync(",
    "function r018bExpedExp(",
    # 使用者（间接引用，本环不动）
    "r018bSpiritBonus(row.rarity, level, row.bond, row.aptitude, row.rune_active)",
    "R018B_RUNE_COST",
    # 工程红线（相对计数）
    "res.status(403",
    "setInterval(",
    "PRAGMA",
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out, base):
    """五元组 (label, needle, expect, op, note)。"""
    return [
        ("R196 幂等标记在位", MARK, 1, "==", "本环已应用"),
        # ── 前 4 条新形态在位 ──
        ("R196 锐纹 暴击率 0.02 + 暴伤 0.08", "kind: 'critRate',        value: 0.02,  kind2: 'critDamage', value2: 0.08,", 1, "==", "锐纹双属性"),
        ("R196 御纹 减伤 0.03", "kind: 'damageReduction', value: 0.03,", 1, "==", "御纹数值"),
        ("R196 疾纹 闪避 0.02", "kind: 'dodgeRate',       value: 0.02,", 1, "==", "疾纹数值"),
        ("R196 噬纹 吸血 0.02", "kind: 'lifeLeech',       value: 0.02,", 1, "==", "噬纹数值"),
        # ── 前 4 条旧形态清零 ──
        ("R196 旧 0.015 清零", "value: 0.015", 0, "==", "旧暴击/闪避值必须消失"),
        ("R196 旧 御纹 0.02 清零", "kind: 'damageReduction', value: 0.02,", 0, "==", "旧御纹值必须消失"),
        ("R196 旧 噬纹 0.01 清零", "kind: 'lifeLeech',       value: 0.01,", 0, "==", "旧噬纹值必须消失"),
        # ── 文案同步 ──
        ("R196 锐纹 desc 同步", "desc: '主人暴击率 +2%、暴击伤害 +8%'", 1, "==", "锐纹文案"),
        ("R196 御纹 desc 同步", "desc: '主人减伤 +3%'", 1, "==", "御纹文案"),
        ("R196 疾纹 desc 同步", "desc: '主人闪避 +2%'", 1, "==", "疾纹文案"),
        ("R196 噬纹 desc 同步", "desc: '主人吸血 +2%'", 1, "==", "噬纹文案"),
        ("R196 旧 锐纹 desc 清零", "desc: '主人暴击率 +1.5%'", 0, "==", "旧锐纹文案消失"),
        ("R196 旧 噬纹 desc 清零", "desc: '主人吸血 +1%'", 0, "==", "旧噬纹文案消失"),
        # ── 管线打通 ──
        ("R196 效果函数 kind2 分派", "if (d.kind2 === 'critDamage') o.critDamage = d.value2 || 0;", 1, "==", "第二属性分派"),
        ("R196 payload runeCritDmg 键", "runeCritDmg: rn ? rn.critDamage : 0,", 1, "==", "客户端读取键"),
        ("R196 zero 含 critDamage", "const zero = { key: '', critRate: 0, critDamage: 0,", 1, "==", "零值含暴伤"),
        ("R196 r018bRuneDef 返回类型自洽", "function r018bRuneDef(key: unknown): { key: string; name: string; unlock: number; kind: string; value: number; kind2?: string; value2?: number; desc: string } | null {", 1, "==", "类型含 kind2/value2"),
        # ── 冻结：后 2 条逐字不动 ──
        ("R196 冻结·蕴纹行逐字不动", "kind: 'expMul',          value: 0.30,", 1, "==", "蕴纹不动"),
        ("R196 冻结·天纹行逐字不动", "kind: 'ppMul',           value: 0.10,", 1, "==", "天纹不动"),
        ("R196 冻结·蕴纹 desc", "desc: '妖灵秘径修为产出 +30%'", 1, "==", "蕴纹文案不动"),
        ("R196 冻结·天纹 desc", "desc: '妖灵之力 PP ×1.10'", 1, "==", "天纹文案不动"),
        # ── 冻结：既有函数签名/使用者不动 ──
        ("R196 冻结·r018bRuneDef 函数体", "return Object.prototype.hasOwnProperty.call(R018B_RUNE_TABLE, k) ? R018B_RUNE_TABLE[k] : null;", 1, "==", "函数体未动"),
        ("R196 冻结·r018bRuneList 签名", "function r018bRuneList(", 1, "==", "未动"),
        ("R196 冻结·r018bSpiritBonus 签名", "function r018bSpiritBonus(", 1, "==", "未动"),
        ("R196 冻结·r018SpiritSync 签名", "function r018SpiritSync(", 1, "==", "未动"),
        ("R196 冻结·r018bExpedExp 签名", "function r018bExpedExp(", 1, "==", "未动"),
        ("R196 冻结·r018bSpiritBonus 调用点", "r018bSpiritBonus(row.rarity, level, row.bond, row.aptitude, row.rune_active)", 1, "==", "未动"),
        ("R196 冻结·R018B_RUNE_COST", "const R018B_RUNE_COST = 50000;", 1, "==", "换纹价未动"),
        # ── 工程红线（相对计数）──
        ("R196 红线·无新 require", "require(", 0, "==", "ESM 直跑禁 require"),
        ("R196 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403"),
        ("R196 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R196 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
    ]


def _apply(src):
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)
    return out


def _roundtrip(out, src):
    back = out
    for name, old, new in reversed(EDITS):
        if back.count(new) != 1:
            return False, "逆向：新块出现 %d 次（期望 1）" % back.count(new)
        back = back.replace(new, old, 1)
    return (back == src), "逆向逐字节还原"


def main():
    ap = argparse.ArgumentParser(description="R-196 灵纹前 4 条加成重设（服务端环）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：产物含标记 ⇒ SKIP（不写盘，rc=0）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖（绝对在位）
    for needle, op, cnt, why in REQUIRES:
        n = src.count(needle)
        good = (n == cnt) if op == "==" else (n >= cnt)
        if not good:
            fail("依赖未满足（%r 出现 %d 次，期望 %s %d）：%s" % (needle[:80], n, op, cnt, why))

    # 3) 锚点唯一
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线（针脚必须在基座真实存在，防拼错导致冻结静默失效）
    base = {k: src.count(k) for k in BASE_NEEDLES}
    for k in BASE_NEEDLES:
        if base[k] <= 0:
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

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r196-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r196rune-", suffix=".tmp")
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
