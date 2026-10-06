# -*- coding: utf-8 -*-
r"""
srv_patch_r172.py -- R-172 仙途指引奖励「按努力重定档」（服务端环）

台账原文（R-172，逐字）
--------------------------------------------------------------------------
  「仙途指引里面的奖励也同样跟成就系统一样，不能只按照奖励的数值来做乘数，
    而是要以实际达到需求所付出的努力来计算，初入江湖奖励2000.初入江湖到炼气三层
    都需要几个小时甚至1天的时间。这部分奖励变化可能不算大。但是炼气3层到圆满
    可能需要好多天的时间。」

改前取证（srv/index_v28.ts 字符级实测）
--------------------------------------------------------------------------
  · 指引表 GUIDE_STEPS @12588-12597（8 步，旧 reward 逐字）：
      enter 2000 / lv3 3000 / lv9 6000 / zhuji 8000
      friend 3000 / baishi 6000 / jindan 20000 / daolv 12000   （旧 Σ60,000）
  · 消费方**只读** reward，判定逻辑与 reward 无关：
      GET  /api/guide/status @12632（回 {id,name,desc,reward,done,claimed}）
      POST /api/guide/claim  @12672（复核条件 → INSERT guide_progress → 加灵石 st.reward）
    ⇒ 只改数值，判定链（has_save / lv / friend / has_mentor / married）一行不动。

  「努力」度量 = 达到该里程碑的**累计所需修为**（用户要求按实际付出算，非旧值×系数）。
  等级语义（index_v28.ts:12638）：lv = realm_index * 9 + realm_level
      ⇒ lv3=炼气期3层、lv9=炼气期9层(圆满)、lv10=筑基期1层、lv19=金丹期1层。
  修为槽（index_v28.ts:4859-4865，与客户端 ad(realm,lv) 同源）：
      realmMaxExp(realm, lv) = floor(maxExpBase * (1 + (lv-1)*0.24))，lv 上限 9
      TRIB_LEVEL_EXP_FACTOR = 0.24                     @4859
      TRIB_REALM_BASES @4850-4858：炼气期 maxExpBase=60000 / 筑基期=390000 / 金丹期=1521000

  逐档求和（Math.floor，逐槽累加）：
      到达 lv3  = 炼气 lv1..lv2 槽 = 60,000 + 74,400                    =   134,400
      到达 lv9  = 炼气 lv1..lv8 槽                                      =   883,199
      到达 lv10 = 炼气 lv1..lv9 槽（修满方能破境入筑基）                = 1,058,399
      到达 lv19 = 炼气满(1,058,399) + 筑基 lv1..lv9 槽(6,879,599)        = 7,937,998

  努力倍率（以 lv3 为 1）：lv9/lv3 = 6.571x、lv10/lv3 = 7.875x、lv19/lv3 = 59.062x。
      ⇒ 与用户定性吻合：enter→lv3 仅数小时~1天 ⇒ 增幅小；lv3→lv9 需多日 ⇒ 大幅跳档；
        lv10/lv19 继续显著放大。
      （注：高境界打坐修为系数更高 E2_REALM_EXP_FACTOR_STEPS @1920 = [1,2,4,8,15,30,60]，
        故墙钟时间倍率小于修为倍率；本环按用户要求以「累计修为」为努力度量。）

设计规格
--------------------------------------------------------------------------
  reward = 2000 + K × 累计所需修为，取整到百位；
      K = 1000 / 134400 ≈ 0.007440476（标定：令 lv3 = 3000，即 enter→lv3「增幅很小」）。
      enter 为锚点 2000（用户指定，不动）。
  社交三步（friend / baishi / daolv）无修为度量 ⇒ 按「达成难度」保持原档
      （friend 3000 < baishi 6000 < daolv 12000，难度序已成立，本环不动）。

  新旧对照（本环 8 步）：
      id      里程碑       旧     新      依据（累计修为）
      enter   初入江湖     2000   2000    锚点（用户指定）
      lv3     炼气三层     3000   3000    2000+K×134,400=3000（标定点）
      lv9     炼气圆满     6000   8600    2000+K×883,199≈8571→8600  ★大幅跳档
      zhuji   筑基成功     8000   9900    2000+K×1,058,399≈9875→9900
      friend  结识道友     3000   3000    社交（不动）
      baishi  拜入师门     6000   6000    社交（不动）
      jindan  金丹初成    20000  61000    2000+K×7,937,998≈61062→61000  ★显著放大
      daolv   喜结道侣    12000  12000    社交（不动）
      新 Σ = 105,500（旧 60,000，1.758x）；Sum=105500

  ★ 幂等/兼容：guide_progress 以 (user_id, step_id) 主键去重，**已领取的行不动**；
    改 reward 只影响**尚未领取**的里程碑发放额 ⇒ 对已领玩家安全，无需迁移。
    旧注释「[r123guide] Σ60,000」为 r123 历史标记，Σ 已被本环 r172 注释覆盖。

改法（4 处 ASCII 锚点替换 · 零新表 / 零新列 / 零改端点 / 零改判定）
--------------------------------------------------------------------------
  E1 在 `const WEEK_REWARDS = [` 前插入 [r172guide] 说明行（标记 + Sum）；
  E2 lv9   reward 6000 → 8600   （锚 `reward: 6000, check: 'lv', arg: 9`）
  E3 zhuji reward 8000 → 9900   （锚 `reward: 8000, check: 'lv', arg: 10`）
  E4 jindan reward 20000 → 61000（锚 `reward: 20000, check: 'lv', arg: 19`）
  id/name/desc/check/arg **一律不动**；WEEK_REWARDS 七日礼**不动**（用户未提）。

CLI 契约（照 srv_patch_r165.py / r163.py / r149.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r172-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r172guide] 则 SKIP（rc=0，不写盘）。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII；替换 expect=1；门禁全绿 + round-trip 自证后才原子写回。
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
MARK = "[r172guide]"

# ============================================================ 改动点（4 处 ASCII 替换）

A1_OLD = "const WEEK_REWARDS = [2000, 3000, 4000, 6000, 8000, 12000, 15000];"
A1_NEW = (
    "// [r172guide] R-172 仙途指引奖励按「达到所需付出的努力(累计修为)」重定档，非旧值×系数。\n"
    "//   锚点 enter=2000（不动）；reward = 2000 + K×累计修为，K=1000/134400≈0.00744（令 lv3=3000）。\n"
    "//   努力倍率(lv3=1)：lv9=6.571x、zhuji=7.875x、jindan=59.062x；社交三步无修为度量保持原档。\n"
    "//   Sum=105500 (old 60000, 1.758x)；逐档推导见 patches/server/srv_patch_r172.py 文件头。\n"
    + A1_OLD
)

A2_OLD = "reward: 6000, check: 'lv', arg: 9"
A2_NEW = "reward: 8600, check: 'lv', arg: 9"

A3_OLD = "reward: 8000, check: 'lv', arg: 10"
A3_NEW = "reward: 9900, check: 'lv', arg: 10"

A4_OLD = "reward: 20000, check: 'lv', arg: 19"
A4_NEW = "reward: 61000, check: 'lv', arg: 19"

EDITS = [
    ("R172 说明行（插在 WEEK_REWARDS 前）", A1_OLD, A1_NEW),
    ("R172 lv9 炼气圆满 6000→8600", A2_OLD, A2_NEW),
    ("R172 zhuji 筑基成功 8000→9900", A3_OLD, A3_NEW),
    ("R172 jindan 金丹初成 20000→61000", A4_OLD, A4_NEW),
]

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("const GUIDE_STEPS = [", "==", 1,
     "指引表必须在位（本环改其 reward 值）"),
    ("const WEEK_REWARDS = [2000, 3000, 4000, 6000, 8000, 12000, 15000];", "==", 1,
     "七日礼表必须在位且逐字未变（本环不动它）"),
    ("reward: 2000, check: 'has_save'", "==", 1,
     "enter 锚点行必须恰好 1 次（reward 保持 2000）"),
    ("reward: 3000, check: 'lv', arg: 3", "==", 1,
     "lv3 行必须恰好 1 次（reward 保持 3000）"),
    ("reward: 6000, check: 'lv', arg: 9", "==", 1,
     "lv9 待改锚点必须恰好 1 次"),
    ("reward: 8000, check: 'lv', arg: 10", "==", 1,
     "zhuji 待改锚点必须恰好 1 次"),
    ("reward: 20000, check: 'lv', arg: 19", "==", 1,
     "jindan 待改锚点必须恰好 1 次"),
    ("reward: 3000, check: 'friend'", "==", 1,
     "friend 社交行必须恰好 1 次（不动）"),
    ("reward: 6000, check: 'has_mentor'", "==", 1,
     "baishi 社交行必须恰好 1 次（不动）"),
    ("reward: 12000, check: 'married'", "==", 1,
     "daolv 社交行必须恰好 1 次（不动）"),
    ("app.get('/api/guide/status', authenticateToken", "==", 1,
     "状态端点必须在位（只读 reward，一行未动）"),
    ("app.post('/api/guide/claim', authenticateToken", "==", 1,
     "领取端点必须在位（判定逻辑一行未动）"),
    ("sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + st.reward;", "==", 1,
     "发放逻辑必须在位（本环只改数值，不改发放式）"),
    ("function realmMaxExp(", "==", 1,
     "修为槽函数必须在位（本环取证依据，只读）"),
    ("const TRIB_LEVEL_EXP_FACTOR = 0.24;", "==", 1,
     "修为曲线系数必须在位（本环取证依据，只读）"),
    ("[r123guide]", ">=", 1,
     "R-123 环必须已应用（前序环在位）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 指引/七日 结构（本环一行未动其结构）
    "const GUIDE_STEPS = [",
    "const WEEK_REWARDS = [2000, 3000, 4000, 6000, 8000, 12000, 15000];",
    # 未动的里程碑（值冻结）
    "reward: 2000, check: 'has_save'",
    "reward: 3000, check: 'lv', arg: 3",
    "reward: 3000, check: 'friend'",
    "reward: 6000, check: 'has_mentor'",
    "reward: 12000, check: 'married'",
    # 消费方（不动）
    "app.get('/api/guide/status', authenticateToken",
    "app.post('/api/guide/claim', authenticateToken",
    "sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + st.reward;",
    # 取证依据（只读）
    "function realmMaxExp(",
    "const TRIB_LEVEL_EXP_FACTOR = 0.24;",
    # 工程红线
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
        ("R172 幂等标记在位", MARK, 1, "==", "本环已应用"),
        ("R172 说明行 Sum 标记", "Sum=105500", 1, "==", "新 Σ 已写入注释"),
        ("R172 enter 锚点未动", "reward: 2000, check: 'has_save'", 1, "==", "2000 冻结"),
        ("R172 lv3 未动", "reward: 3000, check: 'lv', arg: 3", 1, "==", "3000 冻结"),
        ("R172 lv9 新值", "reward: 8600, check: 'lv', arg: 9", 1, "==", "6000→8600"),
        ("R172 zhuji 新值", "reward: 9900, check: 'lv', arg: 10", 1, "==", "8000→9900"),
        ("R172 jindan 新值", "reward: 61000, check: 'lv', arg: 19", 1, "==", "20000→61000"),
        ("R172 friend 未动", "reward: 3000, check: 'friend'", 1, "==", "社交冻结"),
        ("R172 baishi 未动", "reward: 6000, check: 'has_mentor'", 1, "==", "社交冻结"),
        ("R172 daolv 未动", "reward: 12000, check: 'married'", 1, "==", "社交冻结"),
        ("R172 旧 lv9 值已消失", "reward: 6000, check: 'lv', arg: 9", 0, "==", "旧值不得残留"),
        ("R172 旧 zhuji 值已消失", "reward: 8000, check: 'lv', arg: 10", 0, "==", "旧值不得残留"),
        ("R172 旧 jindan 值已消失", "reward: 20000, check: 'lv', arg: 19", 0, "==", "旧值不得残留"),
        ("R172 七日礼未动", "const WEEK_REWARDS = [2000, 3000, 4000, 6000, 8000, 12000, 15000];", 1, "==", "本环不动七日礼"),
        ("R172 状态端点仍在", "app.get('/api/guide/status', authenticateToken", 1, "==", "冻结"),
        ("R172 领取端点仍在", "app.post('/api/guide/claim', authenticateToken", 1, "==", "冻结"),
        ("R172 发放式未动", "sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + st.reward;", 1, "==", "只改数值不改逻辑"),
        ("R172 id/check 结构未动·enter", "check: 'has_save'", 1, "==", "判定键冻结"),
        ("R172 id/check 结构未动·lv19", "check: 'lv', arg: 19", 1, "==", "判定键冻结"),
        ("R172 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403（客户端会强制登出）"),
        ("R172 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R172 红线·无 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        ("R172 红线·无新 require", "require(", 0, "==", "ESM 不新增 require"),
    ]
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-172 仙途指引奖励按努力重定档（服务端环）")
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
        if not old.isascii():
            fail("%s 锚点非纯 ASCII：%r" % (name, old))

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

    # 7) 往返自证：正向重构一致 + 逆向后逐字节回到 src（除改动点外零变化）
    fwd = src
    for name, old, new in EDITS:
        fwd = fwd.replace(old, new, 1)
    if out != fwd:
        fail("round-trip(正向重构) mismatch")
    rev = out
    for name, old, new in reversed(EDITS):
        if rev.count(new) != 1:
            fail("round-trip：NEW 出现次数 != 1：%s" % name)
        rev = rev.replace(new, old, 1)
    if rev != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    for name, old, new in EDITS:
        if out.count(new) != 1:
            fail("round-trip：%s 的 NEW 在产物中出现次数 != 1" % name)

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r172-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r172guide-", suffix=".tmp")
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
