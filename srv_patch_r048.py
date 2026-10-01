# -*- coding: utf-8 -*-
r"""
srv_patch_r048.py -- R-048 灵草分三档（服务端半边 · SRV_CHAIN 链尾，建议排在 r047 之后）

三件事（全部落在服务端权威数值上）：
  ① 综合草（mix）  成熟时长 minutes ×1.5 且 收益（stones/exp）×1.5；
  ② 稀有草（rare） 成熟时长 minutes ×2.5 且 收益（stones/exp）×2.5；
  ③ 稀有草新增**种植门槛**：元婴期（REALM_ORDER_FOR_RANKING 下标 ≥ 3），不足 → 409。
普通（纯卖钱 sell / 纯修为 cult）一字不动。

为什么改这里（口径证据，逐字复核自 srv/index_v28.ts）
--------------------------------------------------------------------------
  R-048 原文（台账 · 仙务·灵田）：「加基础属性的灵草种植条件保持现状，但成熟时间比普通
    专用修为和灵石要增加。特殊属性的灵草必须要玩家等阶很高了才可以种植，而且成熟时间要
    大幅度增加。这两类修为、灵石的数量也相应增加。」
  · 档位判据 = 服务端 farmCropDefs() 的 `FARM_CROPS_NEW[key].k`（sell/cult/mix/rare）；
    客户端只消费下发的 cropList[].line，无任何作物数值（yl_r048_ext.py 已实证）。
  · 成熟时长/收益的**唯一权威源** = farmCropDefs()：`min`（:5657）与 `stones/exp`（:5658-5667）。
    收获入账（farmHarvestOne → farmYield）与 /farm/status 文案同源 ⇒ 只改它两端自动一致。
  · 种植门槛的**唯一权威执法点** = /api/farm/plant（:7967）。客户端置灰只是提示，
    真正的强制在服务端；拒绝码统一 409（**绝不用 403** —— 403 会触发客户端 Xc() 强制登出）。
  · ★ 收益倍率在 out[key] 行施加；**种子价 seed 不动**（只抬产出、不动种植成本）；
    `const min` 行施加时长倍率（与收益同倍 ⇒ 单位时间毛额不变，守经济红线的关键论据）。

经济红线（复算见报告）
--------------------------------------------------------------------------
  · 满配（洞府 L10 六田 + 照料 ×1.21）灵田日净 ≤ 150,000 灵石/日（T9T10 定档）。
  · 本环对 mix/rare **时长与收益同倍放大** ⇒ 单位时间产出（毛额）不变 ⇒ 不额外破线。
  · 净额口径：种子价固定 ⇒ 种子成本被摊薄，mix 日净 ×1.333、rare ×1.764（非绑定线，
    上界仍为纯卖钱草线）。严格「日净」口径的最终结论以报告为准。

CLI 契约（照 srv_patch_050.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` / `--selftest` 只校验不写。
  幂等：产物含 `[r048tier]` 或 `FARM_CROP_TIER_MUL` 定义则 SKIP。
  lead 接线：SRV_CHAIN 链尾追加 'srv_patch_r048.py'（建议排在 srv_patch_r047.py 之后）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403) / setInterval / PRAGMA。
  · 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；不改任何既有 srv_patch_*.py。
  · 每处替换 expect=1，命中数不符即中止；round-trip 自证后原子写回。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r048tier]"

# ============================================================ 唯一调参点
TIER_TIME_MUL = 1.5                # 综合草（mix）成熟时长/收益倍率
TIER_RARE_MUL = 2.5                # 稀有草（rare）成熟时长/收益倍率
RARE_REALM_IDX = 3                 # 稀有草种植门槛：元婴期（REALM_ORDER_FOR_RANKING 下标 / 共 7 档）

# ============================================================ 改动点（一注入 + 三替换）

# ① 注入：档位倍率表 + 境界门槛常量 + 两个纯 helper（插在 farmCropDefs 生成器注释之前）
INJECT_ANCHOR = "// T5：作物定义生成器（纯函数，零副作用；每次调用重算，25 项规模可忽略）。"
INJECT_ADD = (
    "// R-048：灵草分三档——综合草（mix）×1.5 / 稀有草（rare）×2.5；成熟时长与收益同倍放大。[r048tier]\n"
    "//   普通（sell/cult）不动。倍率在下方 farmCropDefs() 内施加；种子价 seed 不动。\n"
    "const FARM_CROP_TIER_MUL: Record<string, number> = { mix: %s, rare: %s };\n"
    "// R-048：特殊属性（rare）灵草种植门槛 = 元婴期（境界序下标 %d / 共 7 档）\n"
    "const FARM_CROP_RARE_REALM = %d;\n"
    "// R-048：是否特殊属性（rare）草（供 /api/farm/plant 门槛判定；非 rare 恒 false）\n"
    "function farmCropIsRare(key: string): boolean {\n"
    "  const c = FARM_CROPS_NEW[asStr(key)];\n"
    "  return !!c && c.k === 'rare';\n"
    "}\n"
    "// R-048：从存档取玩家境界序（读法与 farmGrottoInfo 同款；解析失败/缺档按 0 = 最低境）\n"
    "function farmRealmIndexOf(saveDataJson: string | null | undefined): number {\n"
    "  try {\n"
    "    const r = JSON.parse(saveDataJson || '{}')?.player?.realm;\n"
    "    const i = REALM_ORDER_FOR_RANKING.indexOf(asStr(r));\n"
    "    return i >= 0 ? i : 0;\n"
    "  } catch { return 0; }\n"
    "}\n"
) % (TIER_TIME_MUL, TIER_RARE_MUL, RARE_REALM_IDX, RARE_REALM_IDX)

# ② 成熟时长：施加档位倍率（min 是「成熟时长」唯一来源；farmMatureAt 消费它）
MIN_OLD = "    const min = Math.max(120, Math.ceil((b.min * k.min) / 30) * 30);"
MIN_NEW = ("    const tf = FARM_CROP_TIER_MUL[c.k] || 1; // R-048 档位倍率（mix 1.5 / rare 2.5 / 其余 1）\n"
           "    const min = Math.round(Math.max(120, Math.ceil((b.min * k.min) / 30) * 30) * tf); "
           "// R-048 成熟时长同倍放大")

# ③ 收益：stones/exp 施加档位倍率（seed 保持按未乘倍率的 stones 计算 ⇒ 种植成本不变）
OUT_OLD = ("    out[key] = { name: FARM_CROPS_NEW_NAME[key] || key, seed: Math.round(stones * cs), "
           "minutes: min, stones, exp: cexp, grottoLevel: gl > 1 ? gl : undefined };")
OUT_NEW = ("    out[key] = { name: FARM_CROPS_NEW_NAME[key] || key, seed: Math.round(stones * cs), "
           "minutes: min, stones: Math.round(stones * tf), exp: Math.round(cexp * tf), "
           "grottoLevel: gl > 1 ? gl : undefined };")

# ④ 种植门槛：/api/farm/plant 的 farmCropNoPlant 块之后插境界闸门（409）
GATE_OLD = ("    if (farmCropNoPlant(cropKey)) {\n"
            "      return res.status(409).json({ error: '该灵草品种已停止栽种，请改种新灵草（存量旧作物仍可正常收获）', retired: true });\n"
            "    }")
GATE_ADD = ("\n"
            "    // R-048：特殊属性（rare）灵草需元婴期（境界序 ≥3）方可栽种；不足 → 409（非 403）\n"
            "    if (farmCropIsRare(cropKey)) {\n"
            "      const rIdx = farmRealmIndexOf(saveRow.save_data);\n"
            "      if (rIdx < FARM_CROP_RARE_REALM) {\n"
            "        return res.status(409).json({ error: `【${crop.name}】为特殊属性灵草，需元婴期方可栽种（当前境界不足）`, needRealm: FARM_CROP_RARE_REALM, realmIndex: rIdx });\n"
            "      }\n"
            "    }")

EDITS = [
    ("R048 注入档位/门槛常量与 helper", INJECT_ANCHOR, INJECT_ADD + INJECT_ANCHOR),
    ("R048 成熟时长 ×档位倍率", MIN_OLD, MIN_NEW),
    ("R048 收益 ×档位倍率", OUT_OLD, OUT_NEW),
    ("R048 稀有草境界门槛(409)", GATE_OLD, GATE_OLD + GATE_ADD),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    (INJECT_ANCHOR, 1, "注入锚点（生成器注释）必须在位"),
    (MIN_OLD, 1, "成熟时长行必须在位（唯一锚点）"),
    (OUT_OLD, 1, "out[key] 行必须在位（唯一锚点）"),
    (GATE_OLD, 1, "farmCropNoPlant 块必须在位（播种端点唯一）"),
    ("const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {",
     1, "档位判据表 FARM_CROPS_NEW 必须在位（mix/rare 分类源）"),
    ("app.post('/api/farm/plant'", 1, "播种端点必须在位（门槛唯一执法点）"),
    ("// T5（0.8.9）：旧 5 种已下线，禁止新播（409）；存量已种下的旧田仍可正常收获（兼容）",
     1, "plant 端点内 saveRow 已在位（门槛紧随其后读存档）"),
    ("function farmGrottoInfo(", 1, "同款存档读取函数必须在位（本环读法对齐它）"),
    ("const REALM_ORDER_FOR_RANKING = ", 1, "境界序数组必须在位（门槛判据源）"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "res.status(403", "require(", "setInterval(", "PRAGMA",
    "function farmYield(", "async function farmHarvestOne(userId: number, row: any",
    "const FARM_CROP_KIND: Record<string,", "const FARM_CROP_BASE: Record<number,",
    "const FARM_CROP_ATTRS: Record<string,", "const FARM_CROP_PCT: Record<string,",
    "const FARM_CROP_ATTR_CAP", "const FARM_UNLOCK_COST: Record<number, number>",
    "const FARM_UNLOCK_GROTTO_LEVEL: Record<number, number>",
    "const cs = c.k === 'sell' ? 0.70 : k.seed;",
    "seed: Math.round(stones * cs)",
    "if (crop.grottoLevel && gi.level < crop.grottoLevel) {",
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-048 灵草分三档（时长+收益+rare 门槛）环")
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
    if (MARK in src) or ("const FARM_CROP_TIER_MUL" in src):
        print("[SKIP] source looks already patched（已含 %s 或 FARM_CROP_TIER_MUL）" % MARK)
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
        ("R48 幂等标记就位", MARK, 1),
        ("R48 档位倍率表就位",
         "const FARM_CROP_TIER_MUL: Record<string, number> = { mix: %s, rare: %s };"
         % (TIER_TIME_MUL, TIER_RARE_MUL), 1),
        ("R48 稀有草门槛=元婴期(%d)" % RARE_REALM_IDX,
         "const FARM_CROP_RARE_REALM = %d;" % RARE_REALM_IDX, 1),
        ("R48 稀有草判定 helper 就位", "function farmCropIsRare(key: string): boolean {", 1),
        ("R48 境界序读取 helper 就位", "function farmRealmIndexOf(saveDataJson: string | null | undefined): number {", 1),
        ("R48 时长倍率已施加",
         "const min = Math.round(Math.max(120, Math.ceil((b.min * k.min) / 30) * 30) * tf);", 1),
        ("R48 收益倍率已施加",
         "stones: Math.round(stones * tf), exp: Math.round(cexp * tf),", 1),
        ("R48 播种端点已加境界门槛", "if (farmCropIsRare(cropKey)) {", 1),
        ("R48 门槛拒绝码=409(非 403)", "needRealm: FARM_CROP_RARE_REALM, realmIndex: rIdx", 1),
        ("R48 旧时长形态已清零", MIN_OLD, 0),
        ("R48 旧 out[key] 形态已清零", OUT_OLD, 0),
        # ---- 冻结：种子价（种植成本）一字不动 ----
        ("冻结 种子系数未动", "const cs = c.k === 'sell' ? 0.70 : k.seed;",
         base["const cs = c.k === 'sell' ? 0.70 : k.seed;"]),
        ("冻结 种子价公式未动", "seed: Math.round(stones * cs)",
         base["seed: Math.round(stones * cs)"]),
        # ---- 冻结：普通草种植条件（洞府门槛）一字不动 ----
        ("冻结 普通草洞府门槛未动", "if (crop.grottoLevel && gi.level < crop.grottoLevel) {",
         base["if (crop.grottoLevel && gi.level < crop.grottoLevel) {"]),
        # ---- 冻结：farmHarvestOne / farmYield 其它逻辑一字不动 ----
        ("冻结 farmYield 未动", "function farmYield(", base["function farmYield("]),
        ("冻结 farmHarvestOne 未动",
         "async function farmHarvestOne(userId: number, row: any",
         base["async function farmHarvestOne(userId: number, row: any"]),
        # ---- 冻结：属性值（基础/百分比）不放大 ----
        ("冻结 品阶基准表未动", "const FARM_CROP_BASE: Record<number,",
         base["const FARM_CROP_BASE: Record<number,"]),
        ("冻结 类型系数表未动", "const FARM_CROP_KIND: Record<string,",
         base["const FARM_CROP_KIND: Record<string,"]),
        ("冻结 基础属性表未动", "const FARM_CROP_ATTRS: Record<string,",
         base["const FARM_CROP_ATTRS: Record<string,"]),
        ("冻结 百分比属性表未动", "const FARM_CROP_PCT: Record<string,",
         base["const FARM_CROP_PCT: Record<string,"]),
        ("冻结 属性上限表未动", "const FARM_CROP_ATTR_CAP", base["const FARM_CROP_ATTR_CAP"]),
        # ---- 冻结：洞府扩充（R-049 面）一字不动 ----
        ("冻结 开垦价表未动", "const FARM_UNLOCK_COST: Record<number, number>",
         base["const FARM_UNLOCK_COST: Record<number, number>"]),
        ("冻结 洞府门槛表未动", "const FARM_UNLOCK_GROTTO_LEVEL: Record<number, number>",
         base["const FARM_UNLOCK_GROTTO_LEVEL: Record<number, number>"]),
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

    # 7) 语义自证：倍率表 1 处定义 + 1 处引用（时长行）；门槛常量 3 处（定义 + 闸门判定 + 回执）
    sem_ok = (
        out.count("FARM_CROP_TIER_MUL") == 2
        and out.count("FARM_CROP_RARE_REALM") == 3
        and out.count("farmCropIsRare") == 2      # 定义 + 闸门调用
        and out.count("farmRealmIndexOf") == 2    # 定义 + 闸门调用
    )
    ok = ok and sem_ok
    print("  [%s] %-42s tier=%d realm=%d isRare=%d realmIdx=%d"
          % ("OK" if sem_ok else "FAIL", "R48 语义自证(引用完整)",
             out.count("FARM_CROP_TIER_MUL"), out.count("FARM_CROP_RARE_REALM"),
             out.count("farmCropIsRare"), out.count("farmRealmIndexOf")))

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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r048tier-", suffix=".tmp")
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
