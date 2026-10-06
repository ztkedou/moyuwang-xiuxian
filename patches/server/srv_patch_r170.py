# -*- coding: utf-8 -*-
r"""
srv_patch_r170.py -- R-170 + R-171 成就奖励改为「按需求次数严格正比」结算（服务端环）

台账原文（逐字）
--------------------------------------------------------------------------
R-170：「成就系统的奖励档位没有拉开，要以次数为基础，不要以现有的档位奖励来结算。
        比如说修行中的初窥门径是60需求，奖励500灵石。第二档位变成了300需求，但是灵石
        只从500升到1200显然不合理。要以60需求升到300需求来计算奖励。其他的成就也是同理。」
R-171：「上一条，所有成就的最低档位奖励变成2000灵石」

改前取证（srv/index_v28.ts 字符级实测）
--------------------------------------------------------------------------
  · ACH_DEFS 在 @5250-5306，5 组 × 10 档 = 50 条，形如
      { id: 'cultivate_60', group: 'cultivate', name: '初窥门径', desc: '累计在线 60 分钟', target: 60, reward: 500 },
  · 五组 metric：cultivate(minutes) / battle(kills) / wealth(silver) / quest(quests) / realm(totalLevel)
  · 旧 reward 序列五组**共用同一条**：500,1200,2500,4500,7000,10000,15000,22000,32000,50000
    ⇒ 每组 Σ144,700；全清 723,500（r122ach10 注释自带）
  · 旧 target 序列：
      cultivate 60,300,1200,3000,7000,15000,30000,60000,100000,150000
      battle    10,50,200,500,1200,2500,5000,10000,18000,30000
      wealth    1e4,1e5,1e6,3e6,8e6,2e7,5e7,1.2e8,2.5e8,5e8
      quest     1,10,50,150,350,700,1200,2000,3000,5000
      realm     3,10,19,28,37,46,52,56,60,63
  · 症状（用户原话）：reward 档位梯度（500→1200，+140%）远弱于 target 梯度（60→300，+400%），
    导致「需求翻 5 倍、奖励只翻 2.4 倍」，越往后性价比越低。
  · buildAchievementsView() @5313 与领取端点 POST /api/achievements/claim 只**读** reward
    （ACH_DEFS 在 @13067 被 byId 索引）⇒ 本环**只改 reward 字面量**，逻辑零改动。

改法（1 处注释插入 + 50 处 reward 字面量改写 · 零逻辑改动）
--------------------------------------------------------------------------
  规则（本环唯一算法，用户原话「要以 60 需求升到 300 需求来计算奖励」的直接翻译）：

        reward_i = round3sig( 2000 × target_i / target_1 )

    · target_1 = 每组**第一档**的 target（cultivate=60 / battle=10 / wealth=1e4 /
      quest=1 / realm=3），故每组首档 reward ≡ 2000（R-171）。
    · round3sig(x) = 四舍五入到 **3 位有效数字**（>=1000 的档位即就近取整到 100/1000/10000…）。
      例：233333.33→233000；3333333.33→3330000；6666.67→6670；12666.67→12700。
    · target / id / name / desc / group **一律不动**（改 target 会让玩家进度错乱）。
    · 实现方式：**直接改 50 条 reward 字面量**（最可审计、round-trip 最稳），
      不改生成器、不引入常量表。

复算表（本环产出，供报告引用；reward 与 target 严格成正比）
--------------------------------------------------------------------------
  cultivate（target_1=60）：
      target  60 →   2000        target  3000 →   100000
      target 300 →  10000        target  7000 →   233000  (round3sig 233333.33)
      target 1200→  40000        target 15000 →   500000
      target 30000→ 1000000      target 60000 →  2000000
      target 100000→3330000      target 150000→ 5000000
      Σ = 12,215,000

  battle（target_1=10）：
      10→2000  50→10000  200→40000  500→100000  1200→240000
      2500→500000  5000→1000000  10000→2000000  18000→3600000  30000→6000000
      Σ = 13,492,000

  wealth（target_1=10000）：
      1e4→2000  1e5→20000  1e6→200000  3e6→600000  8e6→1600000
      2e7→4000000  5e7→10000000  1.2e8→24000000  2.5e8→50000000  5e8→100000000
      Σ = 190,422,000   ★ 见下方「wealth 副作用」

  quest（target_1=1）：
      1→2000  10→20000  50→100000  150→300000  350→700000
      700→1400000  1200→2400000  2000→4000000  3000→6000000  5000→10000000
      Σ = 24,922,000

  realm（target_1=3）：
      3→2000  10→6670  19→12700  28→18700  37→24700
      46→30700  52→34700  56→37300  60→40000  63→42000
      Σ = 249,470

  全 50 项总计 Σ = 12,215,000 + 13,492,000 + 190,422,000 + 24,922,000 + 249,470
                 = 241,300,470 灵石
  （对比旧表全清 723,500 ⇒ 约 ×333.5；其中 wealth 一组独占 78.9%）

★ wealth 副作用（必须显式标注）
--------------------------------------------------------------------------
  wealth 组末档 target=5e8 → reward=1e8，即**奖励 = 需求的 20%**；单组 Σ≈1.90 亿灵石，
  占全 50 项总计的 78.9%。这是**用户规则「奖励与需求严格成正比」直接推导出的结果**，
  本环**照规则实现**，不做隐藏封顶。若用户认为财富组给得过多，备选方案（**仅记录，未实现**）：
    (A) wealth 组改用次线性 sqrt：reward_i = round(2000 × sqrt(target_i / target_1))
        ⇒ 末档 2000×sqrt(50000)≈447,214，单组 Σ≈ 9.4e5 量级；
    (B) wealth 组 reward 封顶 5,000,000（末 3 档同值）；
    (C) 保持正比但把 wealth 组整体权重 ×0.1（末档 1e7，单组 Σ≈1.9e7）。
  以上备选**不写进代码**，主实现严格正比，待用户拍板后再开新环。

红线（一行未动）
--------------------------------------------------------------------------
  ACH_GROUPS / AchMetric / AchTotals / AchDef 接口 / achTotalsFrom / buildAchievementsView /
  ACH_DEFS 的 id·group·name·desc·target / GET /api/achievements / POST /api/achievements/claim /
  所有 target 字面量 —— 全部零改动。本环只重写 50 个 reward 数值 + 插 3 行注释。

CLI 契约（照 srv_patch_r165.py / srv_patch_r163.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（mkstemp + os.replace，写回前生成 .bak-r170-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r170ach] 则 SKIP（直接返回 rc=0，不写盘）。
  退出码：0 = 成功/已应用；1 = 任一依赖/锚点/门禁/自证失败；2 = argparse 用法错误。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII；替换 expect=1；门禁全绿 + round-trip 自证后才原子写回。
  · 50 条锚点用「target: <T>, reward: <R>」；仅 (target=10, reward=1200) 在 quest_10 与
    realm_10 重复，此 2 条改用「… },\n  { id: '<下一 id>'」后缀锚点去歧义。
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（写进 TS 注释行）
MARK = "[r170ach]"

# ============================================================ 数值表（唯一真源）

# 旧 reward 序列（五组共用）
OLD_SEQ = [500, 1200, 2500, 4500, 7000, 10000, 15000, 22000, 32000, 50000]

# (组名, 10 个 target, 10 个新 reward)  —— 新 reward = round3sig(2000 * target / target_1)
GROUPS = [
    ("cultivate", [60, 300, 1200, 3000, 7000, 15000, 30000, 60000, 100000, 150000],
                  [2000, 10000, 40000, 100000, 233000, 500000, 1000000, 2000000, 3330000, 5000000]),
    ("battle", [10, 50, 200, 500, 1200, 2500, 5000, 10000, 18000, 30000],
               [2000, 10000, 40000, 100000, 240000, 500000, 1000000, 2000000, 3600000, 6000000]),
    ("wealth", [10000, 100000, 1000000, 3000000, 8000000, 20000000, 50000000, 120000000, 250000000, 500000000],
               [2000, 20000, 200000, 600000, 1600000, 4000000, 10000000, 24000000, 50000000, 100000000]),
    ("quest", [1, 10, 50, 150, 350, 700, 1200, 2000, 3000, 5000],
              [2000, 20000, 100000, 300000, 700000, 1400000, 2400000, 4000000, 6000000, 10000000]),
    ("realm", [3, 10, 19, 28, 37, 46, 52, 56, 60, 63],
              [2000, 6670, 12700, 18700, 24700, 30700, 34700, 37300, 40000, 42000]),
]

# 歧义锚点（(target=10, reward=1200) 在 quest_10 与 realm_10 各出现 1 次）⇒ 加后缀去歧义
SPECIAL = {
    ("quest", 10): ("target: 10, reward: 1200 },\n  { id: 'quest_50'",
                    "target: 10, reward: 20000 },\n  { id: 'quest_50'"),
    ("realm", 10): ("target: 10, reward: 1200 },\n  { id: 'realm_19'",
                    "target: 10, reward: 6670 },\n  { id: 'realm_19'"),
}

# ============================================================ 改动点（1 插入 + 50 改写）

INSERT_OLD = "const ACH_DEFS: AchDef[] = ["

INSERT_NEW = (
    "// [r170ach] R-170/R-171 成就奖励「按需求次数严格正比」重算：\n"
    "//   reward_i = round3sig(2000 * target_i / target_1)（3 位有效数字取整，见 patches/server/srv_patch_r170.py）；\n"
    "//   每组首档一律 2000 灵石（R-171）。target / id / name / desc / group 一律未动。\n"
    + INSERT_OLD
)


def build_edits():
    """生成 50 条 reward 改写 + 1 条注释插入（顺序：先数值，后插入）。"""
    e = []
    for g, ts, news in GROUPS:
        for i, t in enumerate(ts):
            if (g, t) in SPECIAL:
                old, new = SPECIAL[(g, t)]
            else:
                # 右边界 " }" 必带：否则 reward: 50000 会误命中 reward: 5000000 的前缀
                old = "target: %d, reward: %d }" % (t, OLD_SEQ[i])
                new = "target: %d, reward: %d }" % (t, news[i])
            if old == new:
                continue
            e.append(("R170 %s 第%d档 target=%d reward %d->%d" % (g, i + 1, t, OLD_SEQ[i], news[i]),
                      old, new))
    e.append(("R170 注释插入（含幂等标记）", INSERT_OLD, INSERT_NEW))
    return e


EDITS = build_edits()

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("const ACH_DEFS: AchDef[] = [", "==", 1,
     "成就表必须在位（本环只改其中 50 个 reward 字面量）"),
    ("const ACH_GROUPS: Array<{ key: string; name: string; metric: AchMetric }> = [", "==", 1,
     "分组表必须在位（本环一行未动）"),
    ("interface AchDef { id: string; group: string; name: string; desc: string; target: number; reward: number; }", "==", 1,
     "AchDef 结构必须在位（reward: number，本环只改值）"),
    ("function buildAchievementsView(", "==", 1,
     "成就视图组装必须在位（只读 reward，本环不改逻辑）"),
    ("function achTotalsFrom(", "==", 1,
     "进度聚合必须在位（只读 target，本环不改）"),
    ("app.post('/api/achievements/claim'", "==", 1,
     "领取端点必须在位（只读 reward 结算，本环不改逻辑）"),
    ("[r122ach10]", "==", 1,
     "R-122 十档成就环必须已应用（本环在其之上重算 reward）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 成就核心（本环逻辑一行未动）
    "const ACH_GROUPS: Array<{ key: string; name: string; metric: AchMetric }> = [",
    "interface AchDef { id: string; group: string; name: string; desc: string; target: number; reward: number; }",
    "function achTotalsFrom(",
    "function buildAchievementsView(",
    "app.post('/api/achievements/claim'",
    "[r122ach10]",
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
        ("R170 幂等标记在位", MARK, 1, "==", "本环已应用"),
        ("R170 首档一律 2000（5 组·R-171）", ", reward: 2000 },", 5, "==", "每组最低档 = 2000 灵石"),
        ("R170 旧首档 500 已清除·cultivate", "target: 60, reward: 500 }", 0, "==", "旧值不得残留"),
        ("R170 旧末档 50000 已清除·realm", "target: 63, reward: 50000 }", 0, "==", "旧值不得残留"),
        ("R170 旧末档 50000 已清除·battle", "target: 30000, reward: 50000 }", 0, "==", "旧值不得残留"),
        ("R170 旧末档 50000 已清除·wealth", "target: 500000000, reward: 50000 }", 0, "==", "旧值不得残留"),
        # 抽检新值（每组各 2 条，含 round3sig 生效档）
        ("R170 新值 cultivate 300->10000", "target: 300, reward: 10000 }", 1, "==", "×5 正比"),
        ("R170 新值 cultivate 100000->3330000", "target: 100000, reward: 3330000 }", 1, "==", "round3sig(3333333.33)"),
        ("R170 新值 battle 1200->240000", "target: 1200, reward: 240000 }", 1, "==", "×120 正比"),
        ("R170 新值 battle 30000->6000000", "target: 30000, reward: 6000000 }", 1, "==", "×3000 正比"),
        ("R170 新值 wealth 5e8->1e8", "target: 500000000, reward: 100000000 }", 1, "==", "★ 末档 = 需求的 20%"),
        ("R170 新值 wealth 1e6->200000", "target: 1000000, reward: 200000 }", 1, "==", "×100 正比"),
        ("R170 新值 quest 5000->10000000", "target: 5000, reward: 10000000 }", 1, "==", "×5000 正比"),
        ("R170 新值 quest 10->20000（后缀锚）", "target: 10, reward: 20000 },\n  { id: 'quest_50'", 1, "==", "去歧义锚点"),
        ("R170 新值 realm 10->6670（后缀锚）", "target: 10, reward: 6670 },\n  { id: 'realm_19'", 1, "==", "round3sig(6666.67)"),
        ("R170 新值 realm 63->42000", "target: 63, reward: 42000 }", 1, "==", "×21 正比"),
        # target 一律未动（抽检）
        ("R170 target 未动·cultivate 150000", "target: 150000, reward: 5000000 }", 1, "==", "target 冻结"),
        ("R170 target 未动·realm 3", "target: 3, reward: 2000 }", 1, "==", "target 冻结"),
        # 逻辑/结构冻结
        ("R170 ACH_DEFS 表头仍在", "const ACH_DEFS: AchDef[] = [", 1, "==", "冻结"),
        ("R170 buildAchievementsView 仍在", "function buildAchievementsView(", 1, "==", "冻结"),
        ("R170 领取端点仍在", "app.post('/api/achievements/claim'", 1, "==", "冻结"),
        # 红线
        ("R170 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403（客户端会强制登出）"),
        ("R170 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R170 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        ("R170 红线·无 require(", "require(", 0, "==", "ESM，不新增 require"),
    ]
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-170/R-171 成就奖励按需求次数严格正比重算（服务端环）")
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

    # 7) 每条改动自证：新值恰好 1 次、旧值 0 次（插入型编辑 old ⊂ new，跳过旧值残留检查）
    for name, old, new in EDITS:
        if out.count(new) != 1:
            fail("自证失败：%s 的新值出现 %d 次（期望 1）" % (name, out.count(new)))
        if old not in new and out.count(old) != 0:
            fail("自证失败：%s 的旧值仍残留 %d 次" % (name, out.count(old)))

    # 8) 往返自证：除改动点外其余字节完全一致（正反双向）
    fwd = src
    for name, old, new in EDITS:
        fwd = fwd.replace(old, new, 1)
    if out != fwd:
        fail("round-trip(正向重构) mismatch")
    rev = out
    for name, old, new in reversed(EDITS):
        rev = rev.replace(new, old, 1)
    if rev != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    if out.count(INSERT_NEW) != 1:
        fail("round-trip：INSERT_NEW 出现次数 != 1")
    if out.count(", reward: 2000 },") != 5:
        fail("round-trip：首档 2000 出现次数 != 5")

    print("  已改写 reward 条目 = %d 条" % (len(EDITS) - 1))
    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r170-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r170ach-", suffix=".tmp")
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
