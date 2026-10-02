# -*- coding: utf-8 -*-
r"""
srv_patch_r123.py -- R-123 仙途指引 8 步加码 + 七日礼加码（服务端 · SRV_CHAIN 新环）

台账原文（R-123，逐字）
--------------------------------------------------------------------------
  「仙途指引也是，奖励档位太少，高档位力度太小，越往上难度其实越大，
    但是现在奖励变化太小了。」

实现口径（0.9.13 数值表 §7 + 拍板/2026-10-02_0246_R116-R131数值代决.md ## R-123）
--------------------------------------------------------------------------
  · srv/index_v28.ts 实读（0.9.13 链头产物，2026-10-02 逐字节）：GUIDE_STEPS 8 步
    （500/800/1500/2000/800/1500/5000/3000 = Σ15,100）；WEEK_REWARDS 7 天
    （[500,800,1200,1800,2500,3500,5000] = Σ15,300）。
  · 新值（拍板定档，只改 reward 数值，id/name/desc/check/arg 一字不动）：
      指引 enter 2000 / lv3 3000 / lv9 6000 / zhuji 8000 / friend 3000 /
           baishi 6000 / jindan 20000 / daolv 12000  → Σ60,000（3.97x）
      七日礼 [2000,3000,4000,6000,8000,12000,15000]      → Σ50,000（3.27x，逐日递增）
  · 零结构风险证据（2026-10-02 实读）：/api/guide/claim 复核条件后按 `st.reward`
    即时入账；/api/week/claim 按 `WEEK_REWARDS[day-1]` 即时入账 —— 两处都是
    "INSERT OR IGNORE 幂等占位 + 按常量即时发奖"，无存量奖励字段，改常量即全生效；
    day===7 赠称号「七日筑基」（grantTitleBySource('week7')）与本环零交集。
  · 不扩天数（7→14 需动客户端 for 1..7 与 /api/week/claim 的 day>7 校验，拍板明确本轮不做）。
  · 相邻系统冻结：R-054「仙缘七日礼」月历签到（[r054sign]/checkin_fest）是另一套
    活动系统，本环锚点不含其任何字符串，BASE_NEEDLES 稳定性断言兜底。
  · 客户端伴生改动：指引面板 R79Box 说明文案硬编码了旧数字（玩法说明与文案.md §A
    #19 提醒"改档位后说明内数字同步"），由本批配套 yl_r123_ext.py 同步，srv 半边零客户端结构改动。

CLI 契约（照 srv_patch_r122.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径（写回前生成 .bak-r123-<时间戳>）；
  `--check` / `--selftest` 只校验不写。幂等：产物含 [r123guide] 则 SKIP。
  lead 接线：SRV_CHAIN 追加 'srv_patch_r123.py'（两锚点全在基座段批5 Y3 段，
  recon 全扫无既有补丁归属；与 R-116/122/124/129 无锚点交集，任意先后均可）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403) / setInterval / PRAGMA。
  · 不改 srv/index_v28.ts 共享产物（lead 跑本环时对链产物写回）；不改任何既有 srv_patch_*.py。
  · 每处替换带精确 expect（各唯一锚点 expect=1），命中数不符即中止；
    语义自证（新旧两块逐行解析比对数值表 §7）+ round-trip 自证通过后才原子写回。
"""

import argparse
import io
import os
import re
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r123guide]"

# ============================================================ 新 GUIDE_STEPS（数值表 §7 定档）

NEW_GUIDE_BLOCK = """const GUIDE_STEPS = [
  { id: 'enter', name: '初入江湖', desc: '创建角色存档', reward: 2000, check: 'has_save' },
  { id: 'lv3', name: '炼气三层', desc: '总等级达到 3', reward: 3000, check: 'lv', arg: 3 },
  { id: 'lv9', name: '炼气圆满', desc: '总等级达到 9', reward: 6000, check: 'lv', arg: 9 },
  { id: 'zhuji', name: '筑基成功', desc: '总等级达到 10', reward: 8000, check: 'lv', arg: 10 },
  { id: 'friend', name: '结识道友', desc: '添加 1 位好友', reward: 3000, check: 'friend' },
  { id: 'baishi', name: '拜入师门', desc: '拥有师傅', reward: 6000, check: 'has_mentor' },
  { id: 'jindan', name: '金丹初成', desc: '总等级达到 19', reward: 20000, check: 'lv', arg: 19 },
  { id: 'daolv', name: '喜结道侣', desc: '结为道侣', reward: 12000, check: 'married' },
]; // [r123guide] R-123 指引 8 步加码（0.9.13 数值表 §7）：Σ60,000（旧 15,100，3.97x）；七日礼同批 Σ15,300→50,000"""

# ============================================================ 旧 GUIDE_STEPS（2026-10-02 实读 0.9.13 链头产物逐字节；count 必须 =1）

OLD_GUIDE_BLOCK = """const GUIDE_STEPS = [
  { id: 'enter', name: '初入江湖', desc: '创建角色存档', reward: 500, check: 'has_save' },
  { id: 'lv3', name: '炼气三层', desc: '总等级达到 3', reward: 800, check: 'lv', arg: 3 },
  { id: 'lv9', name: '炼气圆满', desc: '总等级达到 9', reward: 1500, check: 'lv', arg: 9 },
  { id: 'zhuji', name: '筑基成功', desc: '总等级达到 10', reward: 2000, check: 'lv', arg: 10 },
  { id: 'friend', name: '结识道友', desc: '添加 1 位好友', reward: 800, check: 'friend' },
  { id: 'baishi', name: '拜入师门', desc: '拥有师傅', reward: 1500, check: 'has_mentor' },
  { id: 'jindan', name: '金丹初成', desc: '总等级达到 19', reward: 5000, check: 'lv', arg: 19 },
  { id: 'daolv', name: '喜结道侣', desc: '结为道侣', reward: 3000, check: 'married' },
];"""

OLD_WEEK = "const WEEK_REWARDS = [500, 800, 1200, 1800, 2500, 3500, 5000];"
NEW_WEEK = ("const WEEK_REWARDS = [2000, 3000, 4000, 6000, 8000, 12000, 15000];"
            " // [r123guide] R-123 七日礼加码：Σ50,000（旧 15,300，3.27x，逐日递增）")

# ============================================================ 改动点（name, old, new, expect）

EDITS = [
    ("E1 指引8步加码", OLD_GUIDE_BLOCK, NEW_GUIDE_BLOCK, 1),
    ("E2 七日礼加码", OLD_WEEK, NEW_WEEK, 1),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    ("app.post('/api/guide/claim'", 1, "指引领取复核端点必须在位（本环零结构改动）"),
    ("app.post('/api/week/claim'", 1, "七日领取端点必须在位（本环零结构改动）"),
    ("INSERT OR IGNORE INTO guide_progress (user_id, step_id, claimed_at) VALUES (?, ?, ?)", 1,
     "指引领取幂等占位必须在位（不改）"),
    ("INSERT OR IGNORE INTO week_goals (user_id, day, claimed_at) VALUES (?, ?, ?)", 1,
     "七日领取幂等占位必须在位（不改）"),
    ("res.json({ ok: true, reward: st.reward });", 1, "指引按常量即时发奖（无存量奖励字段，改常量即全生效）"),
    ("res.json({ ok: true, reward, title: day === 7 ? '七日筑基' : null });", 1, "七日按常量即时发奖"),
    ("if (day === 7) await grantTitleBySource(userId, 'week7').catch(() => {});", 1, "第 7 天称号赠予面（不改）"),
    ("if (!Number.isInteger(day) || day < 1 || day > 7) return res.status(400).json({ error: '参数非法' });", 1,
     "day 1..7 校验在位（不扩天数的结构证据）"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "INSERT OR IGNORE INTO guide_progress (user_id, step_id, claimed_at) VALUES (?, ?, ?)",
    "INSERT OR IGNORE INTO week_goals (user_id, day, claimed_at) VALUES (?, ?, ?)",
    "res.json({ ok: true, reward: st.reward });",
    "res.json({ ok: true, reward, title: day === 7 ? '七日筑基' : null });",
    "if (day === 7) await grantTitleBySource(userId, 'week7').catch(() => {});",
    "if (!Number.isInteger(day) || day < 1 || day > 7) return res.status(400).json({ error: '参数非法' });",
    "app.get('/api/guide/status'",
    # 相邻系统冻结（R-054 仙缘七日礼月历签到是另一套活动，勿碰）
    "[r054sign]",
    "checkin_fest: { name: '仙缘七日礼'",
    # 红线
    "res.status(403",
    "require(",
    "setInterval(",
    "PRAGMA",
]

# ============================================================ 数值表 §7 权威数值（逐行比对用）
GUIDE_NEW = [("enter", 2000), ("lv3", 3000), ("lv9", 6000), ("zhuji", 8000),
             ("friend", 3000), ("baishi", 6000), ("jindan", 20000), ("daolv", 12000)]
GUIDE_OLD_SUM = 15100   # 500+800+1500+2000+800+1500+5000+3000
WEEK_NEW = [2000, 3000, 4000, 6000, 8000, 12000, 15000]
WEEK_OLD_SUM = 15300    # 500+800+1200+1800+2500+3500+5000


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def parse_guide(block):
    return re.findall(r"\{ id: '([^']+)', name: '[^']*', desc: '[^']*', reward: (\d+), check", block)


def verify(out):
    """语义自证：对写入文本里的实际新旧块解析，比对数值表 §7（行数/顺序/数值/合计/倍率/递增）。"""
    # 新指引块
    i0 = out.find("const GUIDE_STEPS = [")
    i1 = out.find("\n];", i0)
    if i0 < 0 or i1 < 0:
        return False, "打后找不到 GUIDE_STEPS 块边界"
    new_block = out[i0:i1 + 3]
    rows = parse_guide(new_block)
    if len(rows) != 8:
        return False, "指引行数 %d != 8" % len(rows)
    if [r[0] for r in rows] != [g[0] for g in GUIDE_NEW]:
        return False, "指引 id 顺序不符：%s" % [r[0] for r in rows]
    got = [int(r[1]) for r in rows]
    want = [g[1] for g in GUIDE_NEW]
    if got != want:
        return False, "指引奖励不符：%s != %s" % (got, want)
    if sum(got) != 60000:
        return False, "指引合计 %d != 60000" % sum(got)
    print("  [OK] 指引 8 步 = %s Σ=%d（旧 Σ%d，x%.2f）"
          % (got, sum(got), GUIDE_OLD_SUM, sum(got) / GUIDE_OLD_SUM))
    # 旧值反证：数值表口径的旧 Σ 必须等于旧块实算
    old_rows = parse_guide(OLD_GUIDE_BLOCK)
    if sum(int(r[1]) for r in old_rows) != GUIDE_OLD_SUM:
        return False, "旧指引块 Σ != %d（锚点被污染？）" % GUIDE_OLD_SUM
    # 新七日礼
    j0 = out.find("const WEEK_REWARDS = ")
    j1 = out.find("\n", j0)
    m = re.match(r"const WEEK_REWARDS = \[([\d, ]+)\];", out[j0:j1])
    if not m:
        return False, "打后 WEEK_REWARDS 行形态不符"
    week = [int(x) for x in m.group(1).split(",")]
    if week != WEEK_NEW:
        return False, "七日礼不符：%s != %s" % (week, WEEK_NEW)
    if sum(week) != 50000:
        return False, "七日礼合计 %d != 50000" % sum(week)
    if week != sorted(week):
        return False, "七日礼非逐日递增"
    print("  [OK] 七日礼 = %s Σ=%d（旧 Σ%d，x%.2f，逐日递增）"
          % (week, sum(week), WEEK_OLD_SUM, sum(week) / WEEK_OLD_SUM))
    return True, ""


def main() -> None:
    ap = argparse.ArgumentParser(description="R-123 指引/七日礼加码环（服务端）")
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
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点计数
    for name, old, new, expect in EDITS:
        n = src.count(old)
        if n != expect:
            fail("%s 锚点出现 %d 次（期望 %d）：%r" % (name, n, expect, old[:120]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用
    out = src
    for name, old, new, expect in EDITS:
        out = out.replace(old, new, expect)

    # 6) 语义自证（对写入文本实解析）
    ok, why = verify(out)
    if not ok:
        fail("语义自证失败：" + why)

    # 7) 门禁
    gates = [
        # ---- 本环改动 ----
        ("R123 幂等标记就位", MARK, 2),
        ("R123 新指引块在位", NEW_GUIDE_BLOCK, 1),
        ("R123 旧指引块清零", OLD_GUIDE_BLOCK, 0),
        ("R123 enter=2000", "{ id: 'enter', name: '初入江湖', desc: '创建角色存档', reward: 2000, check: 'has_save' },", 1),
        ("R123 lv3=3000", "{ id: 'lv3', name: '炼气三层', desc: '总等级达到 3', reward: 3000, check: 'lv', arg: 3 },", 1),
        ("R123 lv9=6000", "{ id: 'lv9', name: '炼气圆满', desc: '总等级达到 9', reward: 6000, check: 'lv', arg: 9 },", 1),
        ("R123 zhuji=8000", "{ id: 'zhuji', name: '筑基成功', desc: '总等级达到 10', reward: 8000, check: 'lv', arg: 10 },", 1),
        ("R123 friend=3000", "{ id: 'friend', name: '结识道友', desc: '添加 1 位好友', reward: 3000, check: 'friend' },", 1),
        ("R123 baishi=6000", "{ id: 'baishi', name: '拜入师门', desc: '拥有师傅', reward: 6000, check: 'has_mentor' },", 1),
        ("R123 jindan=20000", "{ id: 'jindan', name: '金丹初成', desc: '总等级达到 19', reward: 20000, check: 'lv', arg: 19 },", 1),
        ("R123 daolv=12000", "{ id: 'daolv', name: '喜结道侣', desc: '结为道侣', reward: 12000, check: 'married' },", 1),
        ("R123 旧enter行清零", "desc: '创建角色存档', reward: 500,", 0),
        ("R123 旧jindan行清零", "desc: '总等级达到 19', reward: 5000,", 0),
        ("R123 旧daolv行清零", "desc: '结为道侣', reward: 3000,", 0),
        ("R123 七日礼新行在位", NEW_WEEK, 1),
        ("R123 七日礼旧行清零", OLD_WEEK, 0),
        ("R123 七日礼头档2000", "WEEK_REWARDS = [2000, 3000, 4000, 6000, 8000, 12000, 15000];", 1),
        # ---- 冻结：领取链路 / 相邻系统 / 红线（打前==打后）----
    ] + [("冻结 " + k[:44], k, base[k]) for k in BASE_NEEDLES]

    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-46s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    if not ok:
        fail("门禁未全绿，未写回")

    # 8) 往返自证（新→旧逐环还原，必须 == 原文）
    back = out
    for name, old, new, expect in reversed(EDITS):
        if back.count(new) != expect:
            fail("%s 的 new 在产物中出现 %d 次（期望 %d）" % (name, back.count(new), expect))
        for _ in range(expect):
            back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r123-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r123guide-", suffix=".tmp")
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
