# -*- coding: utf-8 -*-
r"""
srv_patch_r124.py -- R-124 灵田种植 BUG（服务端半边 · SRV_CHAIN 新环，必须排在 t5_crops 之后）

台账原文（R-124，逐字）
--------------------------------------------------------------------------
  「左边 仙务·灵田 里面的种植有大BUG不知道上一轮修复没，壮骨花加了两次防御+30，
    培元草防御只加了8.有些描述还出现了英文，总之这一块数值、灵石极度不平衡疑似是bug。」

根因（2026-10-02 逐字实读 srv/index_v28.ts = 0.9.12 线上 b2e472c5…）
--------------------------------------------------------------------------
  [bug1 · 壮骨花防御加两次] 不是结算逻辑双 apply，而是**数据表键重复**：
    FARM_CROP_ATTRS.zhuangguhua 有三项，其中两项 key 同为 'defense'
    （label 分别「体魄」「防御」）：
      zhuangguhua: [{ maxHp,气血 }, { defense,体魄 }, { defense,防御 }],   // ← 3 项，defense ×2
    服用结算 farmHarvestOne：`for (const a of credit.attrs) sd.player[a.key] += a.add`
    —— 每项各加 FARM_CROP_BASE[t].attr（灵品=30）⇒ defense 实得 +60；
    客户端弹窗/悬浮（consAttr 逐项渲染）也把「防御 +30」显示两条。
    ⇒ 修法 = 删掉重复的第三项（{ defense,防御 }），留 2 项（气血+30 / 体魄+30）。
    设计口径「综合草服用 2~3 项属性」（t5_crops §3.2）仍满足；培元草同构 2 项。
  [现象2 · 培元草防御只加 8] **非 bug**：培元草=凡品（t=1），attr 基准=8；
    壮骨花=灵品（t=2）attr=30。品阶曲线 8/30/100/350/1000（FARM_CROP_BASE）是设计值
    （0.9.13 数值表 §13.4 同结论：数值本身与描述一致）。此前用户感知的「不平衡」
    主要来自壮骨花被双倍加成；本环去重后 30 vs 8 即为正常品阶差。数值不动。

英文描述半边（客户端）：见 localtest/yl_r124_ext.py
--------------------------------------------------------------------------
  九窍玄芝（jiugiaoxuanzhi）consAttr 含 key='spirit'，客户端标签表 YLXW_FT_ATTR
  只映射 attack/defense/maxHp/speed，`|| a[i].key` 回退把裸键 `spirit` 当文案显示。
  属客户端显示面，由 yl_r124_ext.py 补 spirit:"神识" 映射（服务端零改动）。

为什么改这里
--------------------------------------------------------------------------
  · FARM_CROP_ATTRS 是服用效果的**唯一权威源**：farmCropConsume（预览/UI 下发）
    与 farmHarvestOne credit.attrs（实际入账）同读此表 ⇒ 改一处两端自动一致。
  · 本环**只删重复项，不动任何数值**：FARM_CROP_BASE attr、FARM_CROP_PCT、
    farmHarvestOne / farmCropConsume 结算逻辑一字不动（R-129 收益线另环处理，
    与本环零交集；R-107/R-106 permanentEffect 冻结面零交集）。

CLI 契约（照 srv_patch_r048.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径（写回前生成 .bak-r124-<时间戳>）；
  `--check` / `--selftest` 只校验不写。幂等：产物含 [r124attrfix] 则 SKIP。
  lead 接线：SRV_CHAIN 追加 'srv_patch_r124.py'（排在 srv_patch_t5_crops.py 之后任意位置）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403) / setInterval / PRAGMA。
  · 不改 srv/index_v28.ts 共享产物（lead 跑本环时对链产物写回）；不改任何既有 srv_patch_*.py。
  · 每处替换 expect=1，命中数不符即中止；round-trip 自证后原子写回。
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r124attrfix]"

# ============================================================ 改动点（一替换）

# 壮骨花行：删去与第二项同键（key='defense'）的第三项。
# 锚点 = 整行字面（2026-10-02 实测 0.9.12 产物内恰好 1 处；含行尾逗号与缩进）。
ZGH_OLD = ("zhuangguhua:    [{ key: 'maxHp', label: '气血' }, "
           "{ key: 'defense', label: '体魄' }, { key: 'defense', label: '防御' }],")
ZGH_NEW = ("zhuangguhua:    [{ key: 'maxHp', label: '气血' }, { key: 'defense', label: '体魄' }], "
           "// R-124：原第三项 { defense,防御 } 与第二项同键重复 ⇒ 服用防御被 +30 两次（实得 +60）"
           "，去重后单次 +30 [r124attrfix]")

EDITS = [
    ("R124 壮骨花去重 defense", ZGH_OLD, ZGH_NEW),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    (ZGH_OLD, 1, "壮骨花行（含重复 defense 项）必须在位且唯一"),
    ("const FARM_CROP_ATTRS: Record<string,", 1, "综合草属性表定义必须在位"),
    ("peiyuancao:     [{ key: 'maxHp', label: '气血' }, { key: 'defense', label: '体魄' }],",
     1, "培元草行（对照组，本环不动）必须在位且唯一"),
    ("jiugiaoxuanzhi: [{ key: 'attack', label: '攻击' }, { key: 'maxHp', label: '气血' }, { key: 'spirit', label: '神识' }],",
     1, "九窍玄芝行（spirit 键来源，本环不动）必须在位且唯一"),
    ("const FARM_CROP_BASE: Record<number,", 1, "品阶基准表必须在位（attr 数值不动）"),
    ("for (const a of credit.attrs) sd.player[a.key] = Math.max(0, Math.floor(Number(sd.player[a.key]) || 0)) + a.add;",
     1, "服用结算 attrs 入账行必须在位（结算逻辑不动，唯一入账点）"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "res.status(403", "require(", "setInterval(", "PRAGMA",
    "const FARM_CROP_BASE: Record<number,",
    "const FARM_CROP_KIND: Record<string,",
    "const FARM_CROP_PCT: Record<string,",
    "const FARM_CROP_ATTR_CAP",
    "function farmCropConsume(key: string, owned?: any)",
    "async function farmHarvestOne(userId: number, row: any",
    "for (const a of credit.attrs) sd.player[a.key] = Math.max(0, Math.floor(Number(sd.player[a.key]) || 0)) + a.add;",
    "peiyuancao:     [{ key: 'maxHp', label: '气血' }, { key: 'defense', label: '体魄' }],",
    "jiugiaoxuanzhi: [{ key: 'attack', label: '攻击' }, { key: 'maxHp', label: '气血' }, { key: 'spirit', label: '神识' }],",
    "bailianzhi:     [{ key: 'attack', label: '攻击' }, { key: 'defense', label: '防御' }, { key: 'maxHp', label: '气血' }],",
    "wanxianghua:    [{ key: 'attack', label: '攻击' }, { key: 'defense', label: '防御' }, { key: 'maxHp', label: '气血' }],",
    "1: { min: 120, sell: 500,   expBase: 100,   attr: 8 },",
    "2: { min: 180, sell: 1500,  expBase: 400,   attr: 30 },",
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-124 灵田壮骨花重复 defense 修复环（服务端）")
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
        ("R124 幂等标记就位", MARK, 1),
        ("R124 壮骨花行已去重(2 项)", ZGH_NEW, 1),
        ("R124 重复 defense 行已清零", ZGH_OLD, 0),
        ("R124 相邻重复 defense 对已清零", "{ key: 'defense', label: '体魄' }, { key: 'defense', label: '防御' }", 0),
        # ---- 冻结：attr 数值/其它作物/结算逻辑一字不动 ----
        ("冻结 品阶基准表未动", "const FARM_CROP_BASE: Record<number,", base["const FARM_CROP_BASE: Record<number,"]),
        ("冻结 类型系数表未动", "const FARM_CROP_KIND: Record<string,", base["const FARM_CROP_KIND: Record<string,"]),
        ("冻结 百分比属性表未动", "const FARM_CROP_PCT: Record<string,", base["const FARM_CROP_PCT: Record<string,"]),
        ("冻结 属性上限表未动", "const FARM_CROP_ATTR_CAP", base["const FARM_CROP_ATTR_CAP"]),
        ("冻结 farmCropConsume 未动", "function farmCropConsume(key: string, owned?: any)",
         base["function farmCropConsume(key: string, owned?: any)"]),
        ("冻结 farmHarvestOne 未动", "async function farmHarvestOne(userId: number, row: any",
         base["async function farmHarvestOne(userId: number, row: any"]),
        ("冻结 attrs 入账行未动",
         "for (const a of credit.attrs) sd.player[a.key] = Math.max(0, Math.floor(Number(sd.player[a.key]) || 0)) + a.add;",
         base["for (const a of credit.attrs) sd.player[a.key] = Math.max(0, Math.floor(Number(sd.player[a.key]) || 0)) + a.add;"]),
        ("冻结 培元草行未动",
         "peiyuancao:     [{ key: 'maxHp', label: '气血' }, { key: 'defense', label: '体魄' }],",
         base["peiyuancao:     [{ key: 'maxHp', label: '气血' }, { key: 'defense', label: '体魄' }],"]),
        ("冻结 九窍玄芝行未动",
         "jiugiaoxuanzhi: [{ key: 'attack', label: '攻击' }, { key: 'maxHp', label: '气血' }, { key: 'spirit', label: '神识' }],",
         base["jiugiaoxuanzhi: [{ key: 'attack', label: '攻击' }, { key: 'maxHp', label: '气血' }, { key: 'spirit', label: '神识' }],"]),
        ("冻结 百炼芝行未动",
         "bailianzhi:     [{ key: 'attack', label: '攻击' }, { key: 'defense', label: '防御' }, { key: 'maxHp', label: '气血' }],",
         base["bailianzhi:     [{ key: 'attack', label: '攻击' }, { key: 'defense', label: '防御' }, { key: 'maxHp', label: '气血' }],"]),
        ("冻结 万象花行未动",
         "wanxianghua:    [{ key: 'attack', label: '攻击' }, { key: 'defense', label: '防御' }, { key: 'maxHp', label: '气血' }],",
         base["wanxianghua:    [{ key: 'attack', label: '攻击' }, { key: 'defense', label: '防御' }, { key: 'maxHp', label: '气血' }],"]),
        ("冻结 凡品 attr=8 未动", "1: { min: 120, sell: 500,   expBase: 100,   attr: 8 },",
         base["1: { min: 120, sell: 500,   expBase: 100,   attr: 8 },"]),
        ("冻结 灵品 attr=30 未动", "2: { min: 180, sell: 1500,  expBase: 400,   attr: 30 },",
         base["2: { min: 180, sell: 1500,  expBase: 400,   attr: 30 },"]),
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

    # 7) 语义自证：壮骨花行内 defense 键恰 1 次；其余 4 株综合草 defense 键数不变
    sem_ok = (
        out.count("zhuangguhua:    [{ key: 'maxHp', label: '气血' }, { key: 'defense', label: '体魄' }],") == 1
        and out.count("{ key: 'defense', label: '防御' }") == 2   # 百炼芝 + 万象花
    )
    ok = ok and sem_ok
    print("  [%s] %-42s zgh2项=%d 防御项余=%d"
          % ("OK" if sem_ok else "FAIL", "R124 语义自证(去重后计数)",
             out.count("zhuangguhua:    [{ key: 'maxHp', label: '气血' }, { key: 'defense', label: '体魄' }],"),
             out.count("{ key: 'defense', label: '防御' }")))

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

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r124-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r124attrfix-", suffix=".tmp")
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
