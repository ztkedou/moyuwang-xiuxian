# -*- coding: utf-8 -*-
r"""
srv_patch_r170b.py -- R-170 二环：成就「境界组」奖励重定档（服务端 · SRV_CHAIN 第 79 环 / 新末环）

  ★ 环号说明：第 77 环 = R-173（srv_patch_r173.py）、第 78 环 = R-175（srv_patch_r175.py）
    ⇒ 本环顺延 **第 79 环**。锚点是 ACH_DEFS 里境界组那 10 条的 `target: N, reward: M }`
    （纯 ASCII、各 count==1，与 r170/r175 锚区零交集）。

用户拍板（逐字）
--------------------------------------------------------------------------
  「是灵石的话把最顶级换算成奖励1亿，其他根据等级设置」
  （前置确认：`POST /api/achievements/claim` 把 5 个组的 reward 一律累加成 stones 走邮件发放
    ⇒ **境界组与其他组同为灵石**，无特殊待遇。）

改前现状（0.9.28 线上；R-170 一环「按需求次数正比」的产物）
--------------------------------------------------------------------------
  境界组度量 = 存档总等级（= 境界序×9 + 层数），10 档 target = 3/10/19/28/37/46/52/56/60/63。
  一环用 `reward = 2000 × target/首档target` ⇒ 境界组「需求」是**等级数**（3~63），
  量纲与其他组（分钟/场次/灵石/任务个数）差两个数量级 ⇒ 整组只有 2,000~42,000、Σ 249,470，
  明显小于其他组（修行 12,215,000 / 战斗 13,492,000 / 任务 24,922,000）⇒ 用户判为「乘数太少」。

改法（只改 reward，target 一行未动）
--------------------------------------------------------------------------
  **等比数列**：首档仍 **2,000**（守 R-171「所有成就最低档位 = 2000 灵石」），
  末档锁定 **100,000,000（1 亿）**，中间按公比 **r = 50000^(1/9) ≈ 3.3274** 铺开
  （≈「每档 ×3.33」），四舍五入到 3 位有效数字：

      档  1  总等级  3   2,000
      档  2  总等级 10   6,650
      档  3  总等级 19   22,100
      档  4  总等级 28   73,700
      档  5  总等级 37   245,000
      档  6  总等级 46   815,000
      档  7  总等级 52   2,710,000
      档  8  总等级 56   9,030,000
      档  9  总等级 60   30,000,000
      档 10  总等级 63   100,000,000   ← 用户指定「最顶级 = 1 亿」
      Σ = 142,904,450（原 249,470）

  ★ 为什么用**等比**而不是「按等级线性」：
    · 「线性 + 首档 2,000」在 60 级跨度上斜率高达 166.7 万/级 ⇒ 第 2 档就是 1,167 万，
      第 1 档 2,000 → 第 2 档 1,167 万，曲线在开头就断裂，观感极差；
    · 「按等级等比（reward ∝ target）」会让首档 = 1 亿 × 3/63 = 476 万，**违反 R-171**。
    ⇒ 等比（每档固定倍率）是唯一同时满足「首档 2,000」+「末档 1 亿」+ 平滑单调 的形态。
  ★ 本环**只动境界组 10 条 reward**；修行/战斗/财富/任务 四组**一行未动**
    （用户 2026-10-07 00:18 明确「财富组先不压」）。
  ★ `target` 一行未动 ⇒ **不影响任何玩家已有的进度判定**（已领的不退、未领的门槛不变）。

CLI 契约（照 srv_patch_r175.py / srv_patch_r165.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r170b-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r170brealm] 则 SKIP（直接返回 rc=0，不写盘）。

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
MARK = "[r170brealm]"

# ============================================================ 改动点（10 处精确替换）
# (旧 reward 值, 新 reward 值, 档位说明) —— 锚点 = "target: <T>, reward: <旧> }"
# ★ 第 1 档（target=3）**刻意不列进来**：它本来就是 2000，新旧相同 ⇒ 空替换会被契约拒绝。
#   它由 gates() 里的「档1 初入仙途 = 2000（守 R-171）」断言把守。
REALM_NEW = [
    (10, 6670, 6650, "筑基功成"),
    (19, 12700, 22100, "金丹初成"),
    (28, 18700, 73700, "元婴出窍"),
    (37, 24700, 245000, "化神通玄"),
    (46, 30700, 815000, "合道之始"),
    (52, 34700, 2710000, "合道七重"),
    (56, 37300, 9030000, "长生之初"),
    (60, 40000, 30000000, "长生六重"),
    (63, 42000, 100000000, "长生久视（长生境九层·圆满）"),
]

EDITS = []
for _t, _old, _new, _note in REALM_NEW:
    EDITS.append((
        "R170b 境界档 target=%d（%s）：%d -> %d" % (_t, _note, _old, _new),
        "target: %d, reward: %d }" % (_t, _old),
        "target: %d, reward: %d }" % (_t, _new),
    ))

# 头部注释块（插在 ACH_DEFS 表头之前，承载幂等标记）
HEAD_ANCHOR = "const ACH_DEFS: AchDef[] = ["
HEAD_BLOCK = (
    "// [r170brealm] R-170 二环：成就「境界组」奖励重定档（用户拍板「最顶级 = 1 亿，其他按等级设置」）。\n"
    "//   等比数列：首档 2,000（守 R-171）→ 末档 100,000,000（1 亿），公比 r = 50000^(1/9) ≈ 3.3274（≈每档 ×3.33）。\n"
    "//   ★ 只改境界组 10 条 reward；修行/战斗/财富/任务 四组一行未动；target 一行未动（不影响玩家已有进度判定）。\n"
    + HEAD_ANCHOR
)

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("const ACH_DEFS: AchDef[] = [", "==", 1,
     "成就表必须在位（本环只改其中境界组 10 条 reward）"),
    ("{ id: 'realm_3', group: 'realm',", "==", 1,
     "境界组第 1 档必须在位（锚区定位用）"),
    ("{ id: 'realm_63', group: 'realm',", "==", 1,
     "境界组末档必须在位（用户指定的 1 亿落点）"),
    ("const stones = claimedNow.reduce((a, id) => a + (byId.get(id)?.reward || 0), 0);", "==", 1,
     "发放式必须在位（reward 一律累加成灵石 —— 本环不改）"),
    ("[r170ach]", ">=", 1,
     "R-170 一环必须已应用（链序约束：本环排在其后）"),
    ("[r175boss]", ">=", 1,
     "R-175 环必须已应用（链序约束：本环 = 新末环，排在第 78 环之后）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 其他 4 组：本环一行未动（各抽 2 条作代表 + 组标记）
    "const ACH_DEFS: AchDef[] = [",
    "{ id: 'cultivate_60', group: 'cultivate',",
    "{ id: 'cultivate_150000', group: 'cultivate',",
    "{ id: 'battle_10', group: 'battle',",
    "{ id: 'battle_30000', group: 'battle',",
    "{ id: 'wealth_1e4', group: 'wealth',",
    "{ id: 'wealth_5e8', group: 'wealth',",
    "{ id: 'quest_1', group: 'quest',",
    "{ id: 'quest_5000', group: 'quest',",
    # 结构冻结
    "function buildAchievementsView(",
    "app.post('/api/achievements/claim', authenticateToken",
    "function achTotalsFrom(",
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
        ("R170b 幂等标记在位", MARK, 1, "==", "本环已应用"),
        ("R170b 表头注释块在位", HEAD_BLOCK.split("\n")[0], 1, "==", "幂等标记载体"),
        # ---- 10 条新值各恰 1 处 ----
        ("R170b 档1 初入仙途 = 2000（守 R-171）", "target: 3, reward: 2000 }", 1, "==", ""),
        ("R170b 档2 筑基功成 = 6650", "target: 10, reward: 6650 }", 1, "==", ""),
        ("R170b 档3 金丹初成 = 22100", "target: 19, reward: 22100 }", 1, "==", ""),
        ("R170b 档4 元婴出窍 = 73700", "target: 28, reward: 73700 }", 1, "==", ""),
        ("R170b 档5 化神通玄 = 245000", "target: 37, reward: 245000 }", 1, "==", ""),
        ("R170b 档6 合道之始 = 815000", "target: 46, reward: 815000 }", 1, "==", ""),
        ("R170b 档7 合道七重 = 2710000", "target: 52, reward: 2710000 }", 1, "==", ""),
        ("R170b 档8 长生之初 = 9030000", "target: 56, reward: 9030000 }", 1, "==", ""),
        ("R170b 档9 长生六重 = 30000000", "target: 60, reward: 30000000 }", 1, "==", ""),
        ("R170b 档10 长生久视 = 1 亿", "target: 63, reward: 100000000 }", 1, "==", "用户指定"),
        # ---- 10 条旧值各清零 ----
        ("R170b 旧档2 值已清零", "target: 10, reward: 6670 }", 0, "==", ""),
        ("R170b 旧档3 值已清零", "target: 19, reward: 12700 }", 0, "==", ""),
        ("R170b 旧档4 值已清零", "target: 28, reward: 18700 }", 0, "==", ""),
        ("R170b 旧档5 值已清零", "target: 37, reward: 24700 }", 0, "==", ""),
        ("R170b 旧档6 值已清零", "target: 46, reward: 30700 }", 0, "==", ""),
        ("R170b 旧档7 值已清零", "target: 52, reward: 34700 }", 0, "==", ""),
        ("R170b 旧档8 值已清零", "target: 56, reward: 37300 }", 0, "==", ""),
        ("R170b 旧档9 值已清零", "target: 60, reward: 40000 }", 0, "==", ""),
        ("R170b 旧档10 值已清零", "target: 63, reward: 42000 }", 0, "==", ""),
        # ---- 其他 4 组一行未动（抽检新值仍在）----
        ("R170b 冻结·修行组未动", "target: 150000, reward: 5000000 }", 1, "==", "R-170 一环值"),
        ("R170b 冻结·战斗组未动", "target: 30000, reward: 6000000 }", 1, "==", ""),
        ("R170b 冻结·财富组未动（先不压）", "target: 500000000, reward: 100000000 }", 1, "==", "用户 00:18「先不压」"),
        ("R170b 冻结·任务组未动", "target: 5000, reward: 10000000 }", 1, "==", ""),
        # ---- 结构 / 发放式冻结 ----
        ("R170b 冻结·发放式未动", "const stones = claimedNow.reduce((a, id) => a + (byId.get(id)?.reward || 0), 0);", 1, "==", "reward 一律累加成灵石"),
        ("R170b 冻结·领取端点仍在", "app.post('/api/achievements/claim', authenticateToken", 1, "==", ""),
        ("R170b 冻结·视图组装仍在", "function buildAchievementsView(", 1, "==", ""),
        ("R170b 冻结·统计钳制仍在", "function achTotalsFrom(", 1, "==", ""),
        # ---- 工程红线（相对计数持平）----
        ("R170b 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403"),
        ("R170b 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R170b 红线·无 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        # ★ `require(` 在 ESM 基座里本来就是 0 ⇒ 不能进 BASE_NEEDLES（那条会要求基座计数 >0），
        #   这里直接断言 == 0（本环不得引入 CommonJS）。
        ("R170b 红线·无新 require", "require(", 0, "==", "ESM"),
    ]
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-170 二环：成就境界组奖励重定档（服务端环）")
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
    if src.count(HEAD_ANCHOR) != 1:
        fail("表头锚点出现 %d 次（期望 1）" % src.count(HEAD_ANCHOR))

    # 4) 冻结基线（每个针脚必须在基座真实存在，防针脚拼错导致「冻结」静默失效）
    base = {k: src.count(k) for k in BASE_NEEDLES}
    for k in BASE_NEEDLES:
        if base[k] <= 0:
            fail("冻结针脚在基座不存在（拼写错误？）：%r" % k[:90])

    # 5) 应用（先插注释块，再逐条改值）
    out = src.replace(HEAD_ANCHOR, HEAD_BLOCK, 1)
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁（五元组，op 支持 == / >=）
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-52s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证：除改动点外其余字节完全一致
    rev = out.replace(HEAD_BLOCK, HEAD_ANCHOR, 1)
    for name, old, new in EDITS:
        rev = rev.replace(new, old, 1)
    if rev != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    if out.count(HEAD_BLOCK) != 1:
        fail("round-trip：HEAD_BLOCK 出现次数 != 1")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r170b-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r170brealm-", suffix=".tmp")
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
