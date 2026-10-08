# -*- coding: utf-8 -*-
r"""
srv_patch_r191.py -- R-191 妖灵「主人加成」转化率 6% → 10%（服务端环）

  ★ 环号说明：srv/index_v28.ts 末环 = R-186（[r186offline]，第 80 环）⇒ 本环顺延 **第 81 环**。
    锚点全部落在 R-018 妖灵核心块（r018SpiritBonus 的转化率常量），与其余任何锚区零交集。

用户原文（逐字）
--------------------------------------------------------------------------
  「①加成改到 10%」
  ⇒ 上下文即妖灵「主人加成」= 妖灵属性 × R018_CONVERT × PP（r018SpiritBonus）。

改前取证（srv/index_v28.ts 字符级实测，md5 e12f4ebc0d1e6aa98d9c9ce1b71d998b / 1,011,566 B）
--------------------------------------------------------------------------
  · :6423  const R018_CONVERT = 0.06;          // 转化率（决策点 3 = A）
  · :6461  // 主人加成 = floor(妖灵属性 × 0.06 × PP)          ← 同值的中文注释
  · :6467-6470  r018SpiritBonus() 内 4 个使用点（attack/defense/maxHp/speed 各 × R018_CONVERT）
  · :6770  r018bSpiritBonus()（= r018SpiritBonus + 灵纹）—— 间接引用，无需改
  · :13396 GET /api/pet 响应 `convert: R018_CONVERT` —— 引用常量，自动跟随
  ⇒ 常量是唯一权威源：改 0.06→0.10 一处，4 个使用点 + 对外暴露的 convert 全部跟随。

R-191 改动（2 处）
--------------------------------------------------------------------------
  [1] 权威常量：`const R018_CONVERT = 0.06;` → `const R018_CONVERT = 0.10;`（+ 幂等标记）
      ⇒ 主人加成 = 妖灵属性 × **10%** × PP（相对 6% 提升 +66.7%）。
  [2] 同步修正同值的中文注释 `// 主人加成 = floor(妖灵属性 × 0.06 × PP)` 里的 `0.06`
      （纯文档、同一数值；**非**其它数值）。锚点用 `0.06 `（0.06+尾随空格，全文件 count==1）。
      ★ 不动的 `0.06`：:6455-6457 `(1 + lv * 0.06)`（妖灵本体等级成长系数，与主人加成无关）、
        :5402 `bonusChance: 0.06`、:5680 `0.06→0.006`（离线速率注释）—— 一律逐字保留。

CLI 契约（照 srv_patch_r182.py / srv_patch_r186.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r191-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 /*[r191conv]*/ 则 SKIP（直接返回 rc=0，不写盘）。
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

# 幂等标记（块注释；TS 源码合法）
MARK = "/*[r191conv]*/"

# ============================================================ 改动点（2 处）

# ── [1] 权威转化率常量 0.06 → 0.10 ──────────────────────────────────────────────
CONV_OLD = "const R018_CONVERT = 0.06;"
CONV_NEW = "const R018_CONVERT = 0.10; " + MARK

# ── [2] 同值中文注释里的 0.06 → 0.10（纯文档；锚点 = "0.06 " 全文件唯一）──────────
NOTE_OLD = "0.06 "
NOTE_NEW = "0.10 "

EDITS = [
    ("R191 主人加成转化率常量 0.06 -> 0.10", CONV_OLD, CONV_NEW),
    ("R191 同值中文注释 0.06 -> 0.10（文档同步）", NOTE_OLD, NOTE_NEW),
]

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("const R018_CONVERT = 0.06;", "==", 1,
     "R-018 转化率常量必须在位（本环唯一权威源）"),
    ("function r018SpiritBonus(", "==", 1,
     "妖灵主人加成纯函数必须在位（本环只改其常量引用）"),
    ("function r018bSpiritBonus(", "==", 1,
     "灵纹包装函数必须在位（间接引用，一行未动）"),
    ("function r018SpiritSync(", "==", 1,
     "妖灵同步函数必须在位（一行未动）"),
    ("Math.floor(s.attack  * R018_CONVERT * pp),", "==", 1,
     "主人加成公式本体必须在位（本环一行未动）"),
    ("convert: R018_CONVERT,", "==", 1,
     "GET /api/pet 暴露的 convert 必须在位（自动跟随常量）"),
    ("0.06 ", "==", 1,
     "同值中文注释的锚点必须唯一（0.06+空格）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 妖灵核心（本环只改常量；公式 / 签名 / 关联常量一行未动）
    "function r018SpiritPP(",
    "function r018SpiritStats(",
    "function r018SpiritBonus(",
    "function r018bSpiritBonus(",
    "function r018SpiritSync(",
    "Math.floor(s.attack  * R018_CONVERT * pp),",
    "Math.floor(s.defense * R018_CONVERT * pp),",
    "Math.floor(s.maxHp   * R018_CONVERT * pp),",
    "Math.floor(s.speed   * R018_CONVERT * pp),",
    "const R018_BOND_MAX = 500;",
    "const R018_APTITUDE_MAX = 100;",
    "lv * 0.06",                       # 妖灵本体等级成长系数（3 处；本环不动）
    "bonusChance: 0.06",               # 无关数值（本环不动）
    "convert: R018_CONVERT,",          # 对外暴露（自动跟随）
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
        ("R191 幂等标记在位", MARK, 1, "==", "本环已应用"),
        # ── 新形态在位 ──
        ("R191 权威常量新值 0.10", "const R018_CONVERT = 0.10;", 1, "==", "转化率已升 10%"),
        # ★ `0.10 `（尾随空格）原件已有 1 处（:8642 FARM_TEND 注释，无关）⇒ 补丁后应为 2
        ("R191 注释新值 0.10", "0.10 ", 2, "==", "原 :8642 一处 + 本环注释一处"),
        # ── 旧形态清零 ──
        ("R191 旧常量 0.06 清零", "const R018_CONVERT = 0.06;", 0, "==", "旧 6% 必须消失"),
        ("R191 旧注释 0.06 清零", "0.06 ", 0, "==", "旧注释 6% 必须消失（唯一 0.06+空格 已被替换）"),
        # ── 冻结断言：公式本体 / 使用点 / 关联常量 改动前后逐字一致 ──
        ("R191 冻结·主人加成 attack 使用点", "Math.floor(s.attack  * R018_CONVERT * pp),", 1, "==", "公式未动"),
        ("R191 冻结·主人加成 defense 使用点", "Math.floor(s.defense * R018_CONVERT * pp),", 1, "==", "公式未动"),
        ("R191 冻结·主人加成 maxHp 使用点", "Math.floor(s.maxHp   * R018_CONVERT * pp),", 1, "==", "公式未动"),
        ("R191 冻结·主人加成 speed 使用点", "Math.floor(s.speed   * R018_CONVERT * pp),", 1, "==", "公式未动"),
        ("R191 冻结·r018SpiritBonus 签名", "function r018SpiritBonus(", 1, "==", "签名未动"),
        ("R191 冻结·r018bSpiritBonus 签名", "function r018bSpiritBonus(", 1, "==", "签名未动"),
        ("R191 冻结·r018SpiritSync 签名", "function r018SpiritSync(", 1, "==", "签名未动"),
        ("R191 冻结·r018SpiritPP 签名", "function r018SpiritPP(", 1, "==", "签名未动"),
        ("R191 冻结·r018SpiritStats 签名", "function r018SpiritStats(", 1, "==", "签名未动"),
        ("R191 冻结·妖灵本体等级系数 lv*0.06", "lv * 0.06", 3, "==", "本体成长系数未动（3 处）"),
        ("R191 冻结·无关 0.06 保留", "bonusChance: 0.06", 1, "==", "无关数值未动"),
        ("R191 冻结·convert 暴露", "convert: R018_CONVERT,", 1, "==", "对外字段自动跟随"),
        ("R191 冻结·BOND_MAX", "const R018_BOND_MAX = 500;", 1, "==", "常量未动"),
        ("R191 冻结·APTITUDE_MAX", "const R018_APTITUDE_MAX = 100;", 1, "==", "常量未动"),
        # ── 工程红线（相对计数）──
        ("R191 红线·无新 require", "require(", 0, "==", "ESM 直跑禁 require"),
        ("R191 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403（客户端会强制登出）"),
        ("R191 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R191 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
    ]
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-191 妖灵主人加成转化率 6% -> 10%（服务端环）")
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
    for name, old, new in reversed(EDITS):
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    for name, old, new in EDITS:
        # ★ E2 的 new=`0.10 `（尾随空格）在原件 :8642 已存在同类子串 ⇒ 用 >=1（强保证由
        #   `back == src` 逆向逐字节还原给出；E1 的 `const R018_CONVERT = 0.10;` 由门禁 ==1 兜底）。
        if out.count(new) < 1:
            fail("round-trip：新增块缺失（%s）" % name)

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r191-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r191conv-", suffix=".tmp")
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
