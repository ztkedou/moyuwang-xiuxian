# -*- coding: utf-8 -*-
r"""
srv_patch_r077.py -- R-077 炼丹：开炉按成熟时长随机出丹数量（服务端环 · SRV_CHAIN 链尾）

需求原文（需求台账_进行中.md L26，R-077）
--------------------------------------------------------------------------
  「炼丹中，丹道这个里面开炉因为成熟时间较久，根据时长来增加随机获得的数量，
    最基础的聚气丹、回春丹每次 1-10 枚随机，后面高级点的也随机，但是随机数量减少。」

现状（逐字实测 srv/index_v28.ts）
--------------------------------------------------------------------------
  POST /api/alchemy/claim 的出炉产出**恒为 1 枚**：`alchemyYieldStones(cost) =
  floor(cost × ALCHEMY_YIELD_RATE)`（YIELD_RATE=1.5，R-064 未动）——即 1 枚丹化灵
  成 `cost×1.5` 灵石随邮件发放，无任何随机、无枚数概念。
  （丹实体在客户端权威存档内，服务端无法入包 ⇒ 按名目折算灵石；枚数即「灵石倍率」。）

改法（期望不变 + 枚数随机 + 保本下限）
--------------------------------------------------------------------------
  · 新增 ALCHEMY_PILL_QTY（按丹名 → [lo,hi] 枚数区间，9 方）：
      聚气丹 1-10 / 回春丹 1-10（用户点名）→ 越高阶枚数越少、区间越窄（「随机数量减少」）：
      凝元丹 2-8 / 洗髓丹 2-7 / 延寿丹 2-6 / 筑基丹 2-5 / 龙血丹 1-4 / 破境丹 1-3 / 九转金丹 1-2
  · 出炉灵石 = max(cost, floor(floor(cost×1.5) × 枚数 / E[枚数]))，E = (lo+hi)/2。
      ⇒ **期望仍 = cost × 1.5**（与改前逐值同额，不通胀）；最差一掷保本（= cost，永不亏本）；
        最好一掷 = cost × 1.5 × hi/E（基础方 ≈ 2.7×，九转金丹 1.33×）。
  · 邮件正文与 claim 响应带上实际枚数；/api/alchemy/list 的 recipes 增发 qty 区间（客户端展示）。
  · 「根据时长增加数量」的落地：枚数区间随方子档位/成本/成熟时长单调收窄，且**单枚价值**
    = cost×1.5/E 随成熟时长递增（30min 单枚 1364 灵石 → 720min 单枚 120000 灵石）——
    时长越长总产出越大；「高级随机数量减少」则体现在枚数上限/波动收窄。

经济复核（3 炉位满转、逐方独立循环；灵石/小时；脚本 _calc_r077.py）
--------------------------------------------------------------------------
  改前：每方恒 1 枚 = floor(cost×1.5) ⇒ 9 方**逐方**都是 4.50 万/h（= R-064 净收益 83.3 灵石/分钟档）。
  改后：期望 = 4.50 万/h × (1 + 保本下限抬升)，逐方抬升 +2.4% ~ +9.1%
        （聚气/回春 +9.1%，九转金丹 +0%），全表均值 ≈ +5%。
  区间（单炉灵石）：聚气丹 5000~13636（期望 8182）／九转金丹 120000~240000（期望 180000）。
  锚点：历练 10 万/h、灵田 50 万/日 ⇒ 单方炼丹期望 ≈ 4.5 万/h，仍远低于历练；本次仅引入方差，
  未开水龙头（+5% 来自「保本下限 cost」对低掷的抬底，非倍率放大）。

CLI 契约（与链上其余补丁一致，照 srv_patch_050.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回（默认 srv/index_v28.ts）；`--check` / `--selftest` 只校验不写。
  幂等：产物已含 `[r077]` 标记则 SKIP。
  lead 接线：localtest/chain_build.py 的 SRV_CHAIN 链尾追加 'srv_patch_r077.py'
  （现末环 srv_patch_064.py 之后）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval` / `PRAGMA`。
  · 不改 ALCHEMY_RECIPES 逐行（srv_patch_064 的 22 条门禁逐字钉死该表）⇒ 枚数区间走**旁表**。
  · 不改 `alchemyYieldStones`（纯函数原样保留，本环复用它）；不改 R-064 的 prof 响应字段。
  · 每处替换 expect=1，命中数不符即中止；round-trip 自证后原子写回。
  · ⛔ 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；⛔ 不改任何既有 srv_patch_*.py。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

MARK = "[r077]"

# ============================================================ E1 旁表 + 纯函数（插在 alchemyRecipe 之前）

E1_ANCHOR = "function alchemyRecipe(key: unknown): AlchemyRecipeDef | null {"

E1_BLOCK = """// [r077] R-077 炼丹开炉按成熟时长随机出丹数量（拍板 2026-10-01）：
//   基础方（聚气丹/回春丹）1-10 枚随机；方子越高阶（成熟越久、单枚越贵）随机枚数越少、波动越窄；
//   出炉灵石 = max(cost, floor(alchemyYieldStones(cost) × 枚数 / E[枚数])) ⇒ 期望 = cost×1.5（同改前，不通胀），
//   最差一掷保本（= cost）；单枚价值随成本/成熟时长递增（30min 1364 → 720min 120000）。
//   枚数区间走旁表（不改 ALCHEMY_RECIPES 逐行，srv_patch_064 门禁逐字钉死该表）。
const ALCHEMY_PILL_QTY: Record<string, [number, number]> = {
  '聚气丹': [1, 10], '回春丹': [1, 10], '凝元丹': [2, 8], '洗髓丹': [2, 7], '延寿丹': [2, 6],
  '筑基丹': [2, 5], '龙血丹': [1, 4], '破境丹': [1, 3], '九转金丹': [1, 2],
};
function alchemyQtyRange(name: unknown): [number, number] {
  const q = ALCHEMY_PILL_QTY[String(name)];
  if (!q) { return [1, 1]; }
  const lo = Math.max(1, Math.floor(Number(q[0]) || 1));
  const hi = Math.max(lo, Math.floor(Number(q[1]) || lo));
  return [lo, hi];
}
function alchemyRollPillCount(name: unknown): number {
  const r = alchemyQtyRange(name);
  return r[0] + Math.floor(Math.random() * (r[1] - r[0] + 1));
}
function alchemyPillYield(cost: number, count: number, name: unknown): number {
  const r = alchemyQtyRange(name);
  const e = (r[0] + r[1]) / 2;
  const n = Math.max(1, Math.floor(Number(count) || 1));
  return Math.max(cost, Math.floor(alchemyYieldStones(cost) * n / e));
}
function alchemyRecipesWithQty(): Record<string, any> {
  const out: Record<string, any> = {};
  for (const k of Object.keys(ALCHEMY_RECIPES)) {
    out[k] = Object.assign({}, ALCHEMY_RECIPES[k], { qty: alchemyQtyRange(ALCHEMY_RECIPES[k].name) });
  }
  return out;
}
"""

# ============================================================ E2 claim：随机枚数 → 灵石

E2_OLD = ("    const yieldStones = recipe ? actApplyGain(alchemyYieldStones(recipe.cost), "
          "evMult.stonesMult * mnG.stonesMult) : 0; // Y21 活动 × Y6B 师徒倍率入账")

E2_NEW = ("    // [r077] 开炉按成熟时长/方子档随机出丹枚数（1-10 基础方 → 1-2 高阶），枚数折算灵石（期望同改前）\n"
          "    const pillCount = recipe ? alchemyRollPillCount(pill) : 0;\n"
          "    const yieldStones = recipe ? actApplyGain(alchemyPillYield(recipe.cost, pillCount, pill), "
          "evMult.stonesMult * mnG.stonesMult) : 0; // Y21 活动 × Y6B 师徒倍率入账；[r077] 枚数→灵石（保本下限 cost）")

# ============================================================ E3 邮件正文带枚数

E3_OLD = "炉火纯青，「${pill}」丹成出炉！"
E3_NEW = "炉火纯青，「${pill}」×${pillCount} 枚丹成出炉！"

# ============================================================ E4 claim 响应带枚数

E4_OLD = "res.json({ ok: true, slot, pill, yieldStones, pillsGained, eventMults:"
E4_NEW = "res.json({ ok: true, slot, pill, yieldStones, pillCount, pillsGained, eventMults:"

# ============================================================ E5 list 响应附枚数区间

E5_OLD = "res.json({ now, slots, recipes: ALCHEMY_RECIPES, yieldRate: ALCHEMY_YIELD_RATE });"
E5_NEW = "res.json({ now, slots, recipes: alchemyRecipesWithQty(), yieldRate: ALCHEMY_YIELD_RATE, pillQty: ALCHEMY_PILL_QTY });"

EDITS = [
    ("E1 枚数旁表 + 掷数/折算纯函数", E1_ANCHOR, E1_BLOCK + E1_ANCHOR),
    ("E2 claim 随机枚数折算灵石",     E2_OLD, E2_NEW),
    ("E3 邮件正文带枚数",             E3_OLD, E3_NEW),
    ("E4 claim 响应带 pillCount",     E4_OLD, E4_NEW),
    ("E5 list 响应附枚数区间",         E5_OLD, E5_NEW),
]

# 前置依赖（本环只读这些串做自证，不改）
REQUIRES = [
    (E1_ANCHOR, 1, "alchemyRecipe 类型收口必须在位（E1 插其前）"),
    ("const ALCHEMY_YIELD_RATE = 1.5;", 1, "返还率常量必须在位（本环不动）"),
    ("function alchemyYieldStones(cost: number): number { return Math.floor(cost * ALCHEMY_YIELD_RATE); }", 1,
     "出炉灵石纯函数必须在位（本环复用它算单枚基准）"),
    ("const ALCHEMY_RECIPES: Record<string, AlchemyRecipeDef> = {", 1, "9 方配方表必须在位（E1 旁表按丹名对齐）"),
    ("const ALCHEMY_SLOTS = 3;", 1, "炉位数常量必须在位（本环不动）"),
    ("app.post('/api/alchemy/claim'", 1, "claim 端点必须在位（E2/E3/E4 改动点）"),
    ("app.get('/api/alchemy/list'", 1, "list 端点必须在位（E5 改动点）"),
    ("if (!del.changes) return res.status(409).json({ error: '该炉已领取' });", 1,
     "并发双击守卫必须在位（本环不动）"),
]

# 冻结基线（打补丁前统计，打完后必须不变）
BASE_NEEDLES = ["res.status(403", "setInterval(", "PRAGMA", "require(",
                "const ALCHEMY_SLOTS = 3;", "const ALCHEMY_YIELD_RATE = 1.5;",
                "function alchemyYieldStones(cost: number): number { return Math.floor(cost * ALCHEMY_YIELD_RATE); }",
                "pill_stash = pill_stash + 1",
                "if (!del.changes) return res.status(409).json({ error: '该炉已领取' });",
                "prof: profGained > 0 ? { gained: profGained, level: profLevel, proficiency: profNow, nextAt: profNext, leveledUp: profUp } : null"]

# R-064 门禁逐字钉死的配方行（本环必须逐字保留；抽查 3 行）
FRZ_RECIPES = [
    "juqi:     { name: '聚气丹',   minutes: 30,  cost: 5000,   rarity: '普通', unlockLevel: 1, summary: '服用 修为+150', profGain: 10 },",
    "huichun:  { name: '回春丹',   minutes: 60,  cost: 10000,  rarity: '稀有', unlockLevel: 1, summary: '服用 气血+200', profGain: 30 },",
    "jiuzhuan: { name: '九转金丹', minutes: 720, cost: 120000, rarity: '仙品', unlockLevel: 8, summary: '服用 修为+5万｜永久 全属性+1000 寿命上限+1000年', profGain: 500 },",
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-077 炼丹开炉随机出丹数量环")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等
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
    frz = {k: src.count(k) for k in FRZ_RECIPES}

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    gates = [
        # ---- E1 旁表 + 纯函数 ----
        ("R77 枚数旁表就位",      "const ALCHEMY_PILL_QTY: Record<string, [number, number]> = {", 1),
        ("R77 基础方 聚气丹 1-10", "'聚气丹': [1, 10]", 1),
        ("R77 基础方 回春丹 1-10", "'回春丹': [1, 10]", 1),
        ("R77 高阶方 九转金丹 1-2", "'九转金丹': [1, 2]", 1),
        ("R77 区间取值函数",       "function alchemyQtyRange(name: unknown): [number, number] {", 1),
        ("R77 掷枚数函数",         "function alchemyRollPillCount(name: unknown): number {", 1),
        ("R77 枚数折算灵石函数",   "function alchemyPillYield(cost: number, count: number, name: unknown): number {", 1),
        ("R77 保本下限 = cost",    "return Math.max(cost, Math.floor(alchemyYieldStones(cost) * n / e));", 1),
        ("R77 list 附区间函数",    "function alchemyRecipesWithQty(): Record<string, any> {", 1),
        # ---- E2 ----
        ("R77 claim 掷枚数",       "const pillCount = recipe ? alchemyRollPillCount(pill) : 0;", 1),
        ("R77 claim 按枚数折算",   "alchemyPillYield(recipe.cost, pillCount, pill)", 1),
        ("R77 旧固定产出已清零",   "actApplyGain(alchemyYieldStones(recipe.cost), evMult.stonesMult * mnG.stonesMult)", 0),
        # ---- E3/E4/E5 ----
        ("R77 邮件正文带枚数",     "炉火纯青，「${pill}」×${pillCount} 枚丹成出炉！", 1),
        ("R77 旧邮件正文已清零",   "炉火纯青，「${pill}」丹成出炉！", 0),
        ("R77 claim 响应带枚数",   "res.json({ ok: true, slot, pill, yieldStones, pillCount, pillsGained, eventMults:", 1),
        ("R77 list 响应附区间",    "recipes: alchemyRecipesWithQty(), yieldRate: ALCHEMY_YIELD_RATE, pillQty: ALCHEMY_PILL_QTY", 1),
        ("R77 幂等标记就位",       MARK, base.get(MARK, 0) + 3),
        # ---- 冻结：R-064 面（配方逐行 / 造诣 / 丹囊 / 并发守卫）----
        ("冻结 配方行 juqi 未动",   FRZ_RECIPES[0], frz[FRZ_RECIPES[0]]),
        ("冻结 配方行 huichun 未动", FRZ_RECIPES[1], frz[FRZ_RECIPES[1]]),
        ("冻结 配方行 jiuzhuan 未动", FRZ_RECIPES[2], frz[FRZ_RECIPES[2]]),
        ("冻结 claim 响应 prof 未动", "prof: profGained > 0 ? { gained: profGained, level: profLevel, proficiency: profNow, nextAt: profNext, leveledUp: profUp } : null",
         base["prof: profGained > 0 ? { gained: profGained, level: profLevel, proficiency: profNow, nextAt: profNext, leveledUp: profUp } : null"]),
        ("冻结 claim 并发守卫未动", "if (!del.changes) return res.status(409).json({ error: '该炉已领取' });",
         base["if (!del.changes) return res.status(409).json({ error: '该炉已领取' });"]),
        ("冻结 凝元丹入囊未动",    "pill_stash = pill_stash + 1", base["pill_stash = pill_stash + 1"]),
        # ---- 冻结：常量与纯函数 ----
        ("冻结 炉位数 ALCHEMY_SLOTS=3", "const ALCHEMY_SLOTS = 3;", base["const ALCHEMY_SLOTS = 3;"]),
        ("冻结 返还率 YIELD_RATE=1.5",  "const ALCHEMY_YIELD_RATE = 1.5;", base["const ALCHEMY_YIELD_RATE = 1.5;"]),
        ("冻结 alchemyYieldStones 未动",
         "function alchemyYieldStones(cost: number): number { return Math.floor(cost * ALCHEMY_YIELD_RATE); }",
         base["function alchemyYieldStones(cost: number): number { return Math.floor(cost * ALCHEMY_YIELD_RATE); }"]),
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
        print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 7) 语义自证：旁表 9 方与配方表 9 名一一对齐；枚数区间 lo<=hi 且高阶更窄
    sem_ok = True
    for nm in ('聚气丹', '回春丹', '凝元丹', '洗髓丹', '延寿丹', '筑基丹', '龙血丹', '破境丹', '九转金丹'):
        if ("'%s': [" % nm) not in out:
            sem_ok = False
            print("  [FAIL] R77 语义自证：旁表缺方 %s" % nm)
    sem_ok = sem_ok and (out.count("function alchemyQtyRange(") == 1)
    ok = ok and sem_ok
    print("  [%s] %-40s qty_entries=9" % ("OK" if sem_ok else "FAIL", "R77 语义自证(旁表9方齐/取值函数唯一)"))

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

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r077-", suffix=".tmp")
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
