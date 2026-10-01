# -*- coding: utf-8 -*-
r"""
srv_patch_econ2.py -- R-028 周里程碑 3 档 → 5 档（服务端环 econ2）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  无前置依赖（只碰 `WEEK_MILESTONES` 常量表与端点注释，不依赖别的环）。

=========================================================================== 为什么服务端必须改
R-028 的「3 档 → 5 档」是**双端同表**：

  · 客户端 `yl_econ2_ext.py` 改的是 `var YlxwQMile = [...]`（t9quest 注入块内），
    它只驱动**里程碑列表的展示**（档位名 / 门槛 / 预计奖励 / 能否点）。
  · 服务端 `WEEK_MILESTONES` 才是**权威**：
        ① `GET /api/quest/summary` 用 `WEEK_MILESTONES.map(...)` 生成 `milestones`
           （客户端拿它渲染；表不改则列表仍是 3 档）；
        ② `POST /api/quest/milestone` 用 `WEEK_MILESTONES.find((m) => m.tier === tier)`
           做**档位白名单**——不在表里的 tier 直接 400 `tier 非法`；
        ③ 发奖金额 `Math.floor(mdef.wbase * rf)` / 修为等效 `mdef.wexp` / 抽奖券 `mdef.wtk`
           全部取自该行。

  ⇒ 只改客户端 = 5 档只是「画」出来的，1500/1900/2310 三个新档**点不动**（服务端 400），
    且 500/1000 档发放金额仍是旧的 20000/45000 ⇒ 客户端改 = 死代码。两端必须同改。

=========================================================================== 改点（2 处 + 0 处冻结）
  E1  `WEEK_MILESTONES` 常量表 3 档 → 5 档（含上方两行注释同步刷新）：
        旧 500/1000/1800，wbase 20000/45000/60000（合计 125k/周）
        新 500/1000/1500/1900/2310，wbase 10000/20000/30000/40000/60000（合计 160k/周）
        wexp = wbase/100（沿用旧表比例：20000→200 / 45000→450 / 60000→600 均成立）
        wtk  ≈ 旧档位值按比例下调（8→4 / 15→9 / 30→30 顶端保号）
  E2  `/api/quest/milestone` 端点上方注释里的档位枚举
        `{tier:500|1000|1800}` → `{tier:500|1000|1500|1900|2310}`

  ★ `MILE_MONTHLY_TIER = 1000` **一行未动**（用户明确要求传承石保持「月」限领，
    不改为周）⇒ 传承石仍挂 1,000 档、仍按月限领一次。
  ★ `MILE_MONTH_REWARD = 5000` 未动。
  ★ 发奖逻辑（`baseReward` / `expStone` / `legacyStone` / `detail` 拼串）**一行未动**，
    全部由表驱动 ⇒ 新档自动生效。
  ★ `ACTIVITY_MAX = 330` 未动；顶端档 2310 = 330 × 7（周活跃度打满才可领），
    与 `weekMax: ACTIVITY_MAX * 7` 自洽。

=========================================================================== 与客户端同一张表（必须逐字对齐）
  客户端 YlxwQMile.tier/base/ticket  ↔  服务端 WEEK_MILESTONES.tier/wbase/wtk
        tier 500  base 10000  ticket 4
        tier 1000 base 20000  ticket 9   legacy '传承石'（按月）
        tier 1500 base 30000  ticket 14
        tier 1900 base 40000  ticket 21
        tier 2310 base 60000  ticket 30  legacy '仙品道具+称号'
  （服务端多一列 `wexp` = wbase/100，客户端不展示，属既有结构。）

=========================================================================== 已知边界（本环不引入、不修复）
  · `legacy: '仙品道具+称号'`（原 1800 档，现移至 2310 档）在服务端**只进响应/邮件文案**，
    并不真的发「仙品道具 / 称号」——这是 T9 0.8.8 既有行为，本环仅把该 legacy 串
    随档位一并上移，**不新增也不删除发奖路径**（零行为漂移）。
  · 老玩家本周若已领过旧 1800 档：`activity_milestones` 里存的是 `w<week>_1800`，
    新表已无 1800 ⇒ 该占位成孤儿行（不影响新档领取；清理不在本环范围）。

=========================================================================== 红线
  · **不新增任何 res.status(403)**（本环不碰任何权限/次数闸门）。
  · 不改 `MILE_MONTHLY_TIER`（保持 1000 = 月频）。
  · 不改 `collectWeeklyActivity` / `collectDailyActivity` / 幂等表 DDL / 发奖表达式。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ E1 周里程碑表 3 → 5 档

E1_OLD = """// 周里程碑档位（门槛 = 周累计活跃度；wbase = 灵石 base；wexp = 打坐等效；wtk = 抽奖券）
//   ★ 1,000 档的「传承石 ×1」按用户拍板**降频为月**（不是每周）：见 MILE_MONTHLY_TIER。
const WEEK_MILESTONES: Array<{ tier: number; wbase: number; wexp: number; wtk: number; legacy: string }> = [
  { tier: 500,  wbase: 20000, wexp: 200, wtk: 8,  legacy: '' },
  { tier: 1000, wbase: 45000, wexp: 450, wtk: 15, legacy: '传承石' },
  { tier: 1800, wbase: 60000, wexp: 600, wtk: 30, legacy: '仙品道具+称号' },
];"""

E1_NEW = """// 周里程碑档位（门槛 = 周累计活跃度；wbase = 灵石 base；wexp = 打坐等效；wtk = 抽奖券）
//   ★ 1,000 档的「传承石 ×1」按用户拍板**降频为月**（不是每周）：见 MILE_MONTHLY_TIER。
//   ★ R-028（econ2 环）：3 档 → 5 档（500/1000/1500/1900/2310），
//     灵石 base 总额 125k → 160k/周。顶端 2310 = ACTIVITY_MAX(330) × 7（周活跃度打满）。
//     与客户端 YlxwQMile 同表；wexp = wbase/100（沿用旧表比例）。
//     传承石仍挂 1,000 档（MILE_MONTHLY_TIER 未动，按月限领），**不改为周**。
const WEEK_MILESTONES: Array<{ tier: number; wbase: number; wexp: number; wtk: number; legacy: string }> = [
  { tier: 500,  wbase: 10000, wexp: 100, wtk: 4,  legacy: '' },
  { tier: 1000, wbase: 20000, wexp: 200, wtk: 9,  legacy: '传承石' },
  { tier: 1500, wbase: 30000, wexp: 300, wtk: 14, legacy: '' },
  { tier: 1900, wbase: 40000, wexp: 400, wtk: 21, legacy: '' },
  { tier: 2310, wbase: 60000, wexp: 600, wtk: 30, legacy: '仙品道具+称号' },
];"""

# ============================================================ E2 端点注释档位枚举

E2_OLD = "// POST /api/quest/milestone — 领取周里程碑（{tier:500|1000|1800}）→ 邮件发灵石"
E2_NEW = "// POST /api/quest/milestone — 领取周里程碑（{tier:500|1000|1500|1900|2310}）→ 邮件发灵石"

EDITS = [
    ("E1 周里程碑表 3→5 档", E1_OLD, E1_NEW),
    ("E2 端点注释档位枚举",   E2_OLD, E2_NEW),
]

REQUIRES = [
    ("const WEEK_MILESTONES: Array<{ tier: number; wbase: number; wexp: number; wtk: number; legacy: string }> = [", 1,
     "T9 0.8.8 里程碑表表头必须在位"),
    ("const MILE_MONTHLY_TIER = 1000;", 1, "传承石月频档常量必须在位（本环不得改）"),
    ("const MILE_MONTH_REWARD = 5000;", 1, "传承石折算常量必须在位"),
    ("const ACTIVITY_MAX = 330;", 1, "周上限基座（330×7=2310）必须在位"),
    ("const CHEST_EXP_TO_STONE = 12;", 1, "修为等效折算比必须在位"),
    ("async function collectWeeklyActivity(userId: number, weekStart: string): Promise<number> {", 1,
     "周活跃度采集函数必须在位"),
    ("app.post('/api/quest/milestone'", 1, "里程碑领取端点唯一"),
    ("const baseReward = Math.floor(mdef.wbase * rf);", 1, "发奖表达式（表驱动）必须在位"),
    ("const expStone = Math.floor(mdef.wexp * CHEST_EXP_TO_STONE);", 1, "修为等效折算表达式必须在位"),
    ("const legacyStone = isMonthly && mdef.legacy === '传承石' ? MILE_MONTH_REWARD : 0;", 1,
     "传承石月频发奖表达式必须在位"),
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
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
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 2) 幂等
    if "{ tier: 2310," in src or "wbase: 10000, wexp: 100" in src:
        fail("source looks already patched（已存在 2310 档 / 新 wbase 10000）")

    # 3) 端点注释与表同源自检（枚举档位必须与表内 tier 一致）
    if "{tier:500|1000|1800}" not in src:
        fail("端点注释档位枚举与预期基线不符（未找到 {tier:500|1000|1800}）")

    # 4) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    base403 = src.count("res.status(403")
    gates = [
        # ---- E1 表结构 ----
        ("R28 表头仍在位且唯一",        "const WEEK_MILESTONES: Array<{ tier: number; wbase: number; wexp: number; wtk: number; legacy: string }> = [", 1),
        ("R28 新档 500",                "  { tier: 500,  wbase: 10000, wexp: 100, wtk: 4,  legacy: '' },", 1),
        ("R28 新档 1000(传承石)",       "  { tier: 1000, wbase: 20000, wexp: 200, wtk: 9,  legacy: '传承石' },", 1),
        ("R28 新档 1500",               "  { tier: 1500, wbase: 30000, wexp: 300, wtk: 14, legacy: '' },", 1),
        ("R28 新档 1900",               "  { tier: 1900, wbase: 40000, wexp: 400, wtk: 21, legacy: '' },", 1),
        ("R28 新档 2310(满)",           "  { tier: 2310, wbase: 60000, wexp: 600, wtk: 30, legacy: '仙品道具+称号' },", 1),
        ("R28 旧档 1800 已清零",        "tier: 1800, wbase: 60000, wexp: 600, wtk: 30", 0),
        ("R28 旧档 500 base 已清零",    "  { tier: 500,  wbase: 20000, wexp: 200, wtk: 8,  legacy: '' },", 0),
        ("R28 旧档 1000 base 已清零",   "  { tier: 1000, wbase: 45000, wexp: 450, wtk: 15, legacy: '传承石' },", 0),
        # ---- E2 注释 ----
        ("R28 端点注释 5 档",           "// POST /api/quest/milestone — 领取周里程碑（{tier:500|1000|1500|1900|2310}）→ 邮件发灵石", 1),
        ("R28 旧端点注释已清零",        "{tier:500|1000|1800}", 0),
        # ---- 冻结：本环不得回踩 ----
        ("冻结 传承石月频档=1000",      "const MILE_MONTHLY_TIER = 1000;", 1),
        ("冻结 传承石折算=5000",        "const MILE_MONTH_REWARD = 5000;", 1),
        ("冻结 周上限基座=330",         "const ACTIVITY_MAX = 330;", 1),
        ("冻结 发奖表达式未动",         "const baseReward = Math.floor(mdef.wbase * rf);", 1),
        ("冻结 修为等效折算未动",       "const expStone = Math.floor(mdef.wexp * CHEST_EXP_TO_STONE);", 1),
        ("冻结 传承石月频发奖未动",     "const legacyStone = isMonthly && mdef.legacy === '传承石' ? MILE_MONTH_REWARD : 0;", 1),
        ("冻结 档位白名单仍表驱动",     "const mdef = WEEK_MILESTONES.find((m) => m.tier === tier);", 1),
        ("冻结 月频判定仍绑 1000",      "const isMonthly = mdef.tier === MILE_MONTHLY_TIER;", 1),
        ("冻结 weekMax=330*7 未动",     "weekMax: ACTIVITY_MAX * 7,", 1),
        ("冻结 幂等表 DDL 未动",        "CREATE TABLE IF NOT EXISTS activity_milestones", 1),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-38s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 7) 红线：不得新增 403
    a403 = out.count("res.status(403")
    good = (a403 == base403)
    ok = ok and good
    print("  [%s] %-38s actual=%d expect==%d" % ("OK" if good else "FAIL", "红线 未新增 res.status(403)", a403, base403))

    # 8) 语义自证：表内 5 档 tier 严格递增、wbase 合计 160k、wexp=wbase/100
    import re as _re
    rows = _re.findall(r"\{ tier: (\d+),\s+wbase: (\d+), wexp: (\d+), wtk: (\d+),\s+legacy: '([^']*)' \}", out)
    tiers = [int(r[0]) for r in rows]
    wbases = [int(r[1]) for r in rows]
    wexps = [int(r[2]) for r in rows]
    sem_ok = (tiers == [500, 1000, 1500, 1900, 2310]
              and wbases == [10000, 20000, 30000, 40000, 60000]
              and sum(wbases) == 160000
              and all(w // 100 == e for w, e in zip(wbases, wexps))
              and tiers[-1] == 330 * 7)
    ok = ok and sem_ok
    print("  [%s] %-38s tiers=%r sum=%d top==330*7" % ("OK" if sem_ok else "FAIL", "R28 语义自证(5档/160k/wexp)", tiers, sum(wbases)))

    if not ok:
        fail("门禁未全绿，未写回")

    # 9) 往返自证
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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".econ2-", suffix=".tmp")
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
