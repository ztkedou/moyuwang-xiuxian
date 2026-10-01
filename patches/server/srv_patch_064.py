# -*- coding: utf-8 -*-
r"""
srv_patch_064.py — R-064 炼丹三修：服务端环（丹炉出炉加丹道造诣 + 丹方 3→9 扩容 + 门槛权威化）

CLI 契约（与链上其余补丁一致，照 srv_patch_063.py 抄）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径（默认 srv/index_v28.ts）；`--check` 只校验不写。

=========================================================================== 为什么服务端必须改
R-064「炼丹出炉好像没加丹道造诣」——实测根因：POST /api/alchemy/claim 全程只
结算「灵石×1.5 邮件 +（凝元丹）丹囊」，全文 0 处 alchemyLevel/alchemyProficiency
（本会话探针实测）。丹房（客户端 handleCraft）有完整熟练度入账（ug 表 + pm 门槛），
丹炉漏了。熟练度是**存档字段**（saves.save_data JSON），只有服务端能跨端权威入账
（客户端改动 = 死代码：srv_patch_dungeon2 / mail claim 报告 §7.2 同一论证）。
写档走 updatePlayerSave（saveLock 互斥 + gm_revision++ 促客户端拉新档 + 409
版本冲突护栏）——与 /alchemy/claim 扣灵石同一套已验证机制。

=========================================================================== 改点（5 组）
  S1  ALCHEMY_RECIPES 3→9 方 + AlchemyRecipeDef 类型（rarity/unlockLevel/summary/
      profGain 四展示与结算字段）+ 两条新常量：
      · ALCHEMY_PROF_GATE = [0,100,300,800,2000,5000,12000,30000,80000]
        （与客户端丹房 pm 同表，bundle @293419 实测逐字）；
      · ALCHEMY_PROF_FURNACE_MULT = 1.2（兑现 t17 玩法说明「丹炉造诣涨得快 20%」）。
      扩容定档（AI 代决，见 拍板/2026-10-01_*_R-064_*.md）：新 6 方按
      「净收益 ≈83.3 灵石/分钟」定价（= 既有 3 方同收益率，只扩便利性不通胀，
      YIELD_RATE=1.5 不动）：
        huichun 回春丹   60min  10000   xisui 洗髓丹  150min  25000
        yanshou 延寿丹  180min  30000   zhuji 筑基丹  240min  40000
        longxue 龙血丹  360min  60000   jiuzhuan 九转金丹 720min 120000
      unlockLevel 与客户端丹方书 YlxwAlcUnlockLv 同表（聚气1/回春1/凝元1/洗髓3/
      延寿4/筑基4/龙血6/破境5/九转8）；summary 与丹房配方表数值同源（Qt 表）。
  S2  alchemyRecipe 返回类型 → AlchemyRecipeDef（函数体零改动，p2_api 的 asStr
      收口原样保留）。
  S3  alchemyRecipeByName 返回类型 → AlchemyRecipeDef（同上）。
  S4  /api/alchemy/start：灵石预检同一行扩展解析 alchemyLevel，开炉前权威校验
      unlockLevel（此前门槛只是客户端展示；服务端放行 = 任何改包客户端都能
      提前开高级丹）。
  S5  /api/alchemy/claim：灵石/丹囊发放后补熟练度入账——
      gain = floor(profGain × 1.2)（普通12/稀有36/传说120/仙品500 档），pm 同表
      升层、上限 9 层；失败不阻塞出炉本体（灵石/丹囊已发，只记日志）；
      响应追加 prof{gained,level,proficiency,nextAt,leveledUp} 供客户端 toast
      （客户端半边 yl_064_ext.py C1 已接）。

=========================================================================== 链序
  ★ 挂 SRV_CHAIN 链尾（srv_patch_063.py 之后）。与 061/062/063 零锚点交集；
    activity087 的领取挂点（actDropTokens）与 409 守卫是本环锚点的一部分，
    必须已在其位（REQUIRES 断言）。

=========================================================================== 客户端半边
  yl_064_ext.py：出炉 toast（claim 响应 prof 字段）、开炉预览药效/产出行、
  丹方书药效+获取途径行、丹房配方卡药效行、YLXW_PILL_FX/FXN 助手。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ S1 配方表扩容 + 常量

S1_OLD = """const ALCHEMY_RECIPES: Record<string, { name: string; minutes: number; cost: number }> = {
  juqi:     { name: '聚气丹', minutes: 30,  cost: 5000 },
  ningyuan: { name: '凝元丹', minutes: 120, cost: 20000 },
  pojing:   { name: '破境丹', minutes: 480, cost: 80000 },
};"""

S1_NEW = """// [r064] R-064 丹炉扩容 3→9 方 + 出炉丹道造诣常量（拍板 2026-10-01）：
//   收益率定档口径 = 净收益 ≈83.3 灵石/分钟（与既有 3 方同率，不通胀；YIELD_RATE 不动）；
//   profGain = 熟练度基础档（同丹房 ug 表），实际入账 ×ALCHEMY_PROF_FURNACE_MULT；
//   unlockLevel 与客户端丹方书同表；summary 数值与丹房配方表同源。
type AlchemyRecipeDef = { name: string; minutes: number; cost: number; rarity?: string; unlockLevel?: number; summary?: string; profGain?: number };
const ALCHEMY_PROF_GATE: number[] = [0, 100, 300, 800, 2000, 5000, 12000, 30000, 80000]; // 与客户端丹房 pm 同表（9 层）
const ALCHEMY_PROF_FURNACE_MULT = 1.2; // 兑现 t17 玩法说明「丹炉造诣涨得快 20%」
const ALCHEMY_RECIPES: Record<string, AlchemyRecipeDef> = {
  juqi:     { name: '聚气丹',   minutes: 30,  cost: 5000,   rarity: '普通', unlockLevel: 1, summary: '服用 修为+150', profGain: 10 },
  huichun:  { name: '回春丹',   minutes: 60,  cost: 10000,  rarity: '稀有', unlockLevel: 1, summary: '服用 气血+200', profGain: 30 },
  ningyuan: { name: '凝元丹',   minutes: 120, cost: 20000,  rarity: '稀有', unlockLevel: 1, summary: '出炉入丹囊：渡劫垫刀，每颗天劫成功率+3%', profGain: 30 },
  xisui:    { name: '洗髓丹',   minutes: 150, cost: 25000,  rarity: '稀有', unlockLevel: 3, summary: '永久 气血上限+50', profGain: 30 },
  yanshou:  { name: '延寿丹',   minutes: 180, cost: 30000,  rarity: '稀有', unlockLevel: 4, summary: '服用 寿命+10年', profGain: 30 },
  zhuji:    { name: '筑基丹',   minutes: 240, cost: 40000,  rarity: '传说', unlockLevel: 4, summary: '服用 修为+500｜永久 神识+300 体魄+30 气血上限+100', profGain: 100 },
  longxue:  { name: '龙血丹',   minutes: 360, cost: 60000,  rarity: '传说', unlockLevel: 6, summary: '永久 气血上限+500 体魄+50', profGain: 100 },
  pojing:   { name: '破境丹',   minutes: 480, cost: 80000,  rarity: '传说', unlockLevel: 5, summary: '服用 修为+1万｜永久 神识+50 体魄+50 攻击+30 防御+30', profGain: 100 },
  jiuzhuan: { name: '九转金丹', minutes: 720, cost: 120000, rarity: '仙品', unlockLevel: 8, summary: '服用 修为+5万｜永久 全属性+1000 寿命上限+1000年', profGain: 500 },
};"""

# ============================================================ S2/S3 函数签名放宽（函数体不动）

S2_OLD = "function alchemyRecipe(key: unknown): { name: string; minutes: number; cost: number } | null {"
S2_NEW = "function alchemyRecipe(key: unknown): AlchemyRecipeDef | null {"

S3_OLD = "function alchemyRecipeByName(name: unknown): { name: string; minutes: number; cost: number } | null {"
S3_NEW = "function alchemyRecipeByName(name: unknown): AlchemyRecipeDef | null {"

# ============================================================ S4 start：造诣门槛权威校验

S4_OLD = """    let bal = 0;
    try { bal = Number(JSON.parse(row.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < recipe.cost) return res.status(409).json({ error: `灵石不足：需 ${recipe.cost}，现有 ${bal}` });"""

S4_NEW = """    let bal = 0;
    let alcLv = 1;
    try {
      const sd0 = JSON.parse(row.save_data);
      bal = Number(sd0?.player?.spiritStones) || 0;
      alcLv = Math.max(1, Math.min(9, Number(sd0?.player?.alchemyLevel) || 1));
    } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < recipe.cost) return res.status(409).json({ error: `灵石不足：需 ${recipe.cost}，现有 ${bal}` });
    // [r064] 造诣门槛服务端权威（此前只是客户端展示；unlockLevel 缺省视为 1）
    if (alcLv < (recipe.unlockLevel || 1)) return res.status(409).json({ error: `丹道造诣不足：此方需第 ${recipe.unlockLevel || 1} 层，你当前第 ${alcLv} 层` });"""

# ============================================================ S5 claim：出炉熟练度入账 + 响应扩字段

S5_OLD = """    if (yieldStones > 0) actDropTokens(userId, yieldStones, now).catch((e: any) => console.error('act drop tokens (alchemy) error:', e?.message || e));
    res.json({ ok: true, slot, pill, yieldStones, pillsGained, eventMults: { exp: evMult.expMult, stones: evMult.stonesMult } });"""

S5_NEW = """    if (yieldStones > 0) actDropTokens(userId, yieldStones, now).catch((e: any) => console.error('act drop tokens (alchemy) error:', e?.message || e));
    // [r064] R-064 出炉加丹道造诣（用户报「出炉没加造诣」）：熟练度 = 方子档位 profGain ×1.2，
    //   门槛与丹房 pm 同表、上限 9 层；updatePlayerSave 落档（saveLock + gm_revision++ 拉新档）。
    //   入账失败不阻塞出炉本体（灵石/丹囊已发，只记日志——拍板 2026-10-01）。
    let profGained = 0, profLevel = 0, profNow = 0, profNext = 0, profUp = false;
    try {
      const profGain = Math.max(0, Math.floor((recipe ? (recipe.profGain || 0) : 0) * ALCHEMY_PROF_FURNACE_MULT));
      if (profGain > 0) {
        const up = await updatePlayerSave(userId, (sd: any) => {
          const pl = sd.player || (sd.player = {});
          let lv = Math.max(1, Math.min(9, Number(pl.alchemyLevel) || 1));
          let prof = Math.max(0, Number(pl.alchemyProficiency != null ? pl.alchemyProficiency : pl.alchemyExp) || 0) + profGain;
          let nextAt = ALCHEMY_PROF_GATE[lv] || 0;
          while (lv < 9 && nextAt > 0 && prof >= nextAt) { prof -= nextAt; lv += 1; profUp = true; nextAt = ALCHEMY_PROF_GATE[lv] || 0; }
          if (lv >= 9) { nextAt = 0; }
          pl.alchemyLevel = lv; pl.alchemyProficiency = prof;
          profGained = profGain; profLevel = lv; profNow = prof; profNext = nextAt;
        });
        if (!up.ok) { profGained = 0; profLevel = 0; profNow = 0; profNext = 0; profUp = false; console.error('alchemy claim prof save error:', up.error); }
      }
    } catch (e: any) { console.error('alchemy claim prof error:', e?.message || e); }
    res.json({ ok: true, slot, pill, yieldStones, pillsGained, eventMults: { exp: evMult.expMult, stones: evMult.stonesMult }, prof: profGained > 0 ? { gained: profGained, level: profLevel, proficiency: profNow, nextAt: profNext, leveledUp: profUp } : null });"""

EDITS = [
    ("S1 配方表 3→9 + 造诣常量",  S1_OLD, S1_NEW),
    ("S2 alchemyRecipe 类型放宽",  S2_OLD, S2_NEW),
    ("S3 alchemyRecipeByName 类型放宽", S3_OLD, S3_NEW),
    ("S4 start 造诣门槛权威校验",  S4_OLD, S4_NEW),
    ("S5 claim 出炉熟练度入账",   S5_OLD, S5_NEW),
]

# 前置依赖（本环只读这些串做自证，不改）
REQUIRES = [
    ("const ALCHEMY_SLOTS = 3;", 1, "炉位数常量必须在位（本环不动）"),
    ("const ALCHEMY_YIELD_RATE = 1.5;", 1, "出炉灵石返还率必须在位（本环不动）"),
    ("function updatePlayerSave(", 1, "存档互斥写入助手必须在位（S5 熟练度落档用它）"),
    ("Object.prototype.hasOwnProperty.call(ALCHEMY_RECIPES, asStr(key))", 1,
     "p2_api 的 asStr 收口必须在位（S2/S3 只放宽返回类型，函数体不动）"),
    ("if (!del.changes) return res.status(409).json({ error: '该炉已领取' });", 1,
     "activity087 的 claim 并发守卫必须在位（本环锚点在其后）"),
    ("app.post('/api/alchemy/start'", 1, "start 端点唯一"),
    ("app.post('/api/alchemy/claim'", 1, "claim 端点唯一"),
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
    if "[r064]" in src or "ALCHEMY_PROF_GATE" in src:
        fail("source looks already patched（已存在 [r064] / ALCHEMY_PROF_GATE 标记）")

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 5) 门禁
    gates = [
        # ---- S1 ----
        ("R64 类型 AlchemyRecipeDef",        "type AlchemyRecipeDef = { name: string; minutes: number; cost: number; rarity?: string; unlockLevel?: number; summary?: string; profGain?: number };", 1),
        ("R64 造诣门槛表同丹房 pm",           "const ALCHEMY_PROF_GATE: number[] = [0, 100, 300, 800, 2000, 5000, 12000, 30000, 80000];", 1),
        ("R64 丹炉造诣倍率 1.2",             "const ALCHEMY_PROF_FURNACE_MULT = 1.2;", 1),
        ("R64 新方 回春丹",                  "huichun:  { name: '回春丹',   minutes: 60,  cost: 10000,  rarity: '稀有', unlockLevel: 1, summary: '服用 气血+200', profGain: 30 },", 1),
        ("R64 新方 洗髓丹",                  "xisui:    { name: '洗髓丹',   minutes: 150, cost: 25000,  rarity: '稀有', unlockLevel: 3, summary: '永久 气血上限+50', profGain: 30 },", 1),
        ("R64 新方 延寿丹",                  "yanshou:  { name: '延寿丹',   minutes: 180, cost: 30000,  rarity: '稀有', unlockLevel: 4, summary: '服用 寿命+10年', profGain: 30 },", 1),
        ("R64 新方 筑基丹",                  "zhuji:    { name: '筑基丹',   minutes: 240, cost: 40000,  rarity: '传说', unlockLevel: 4, summary: '服用 修为+500｜永久 神识+300 体魄+30 气血上限+100', profGain: 100 },", 1),
        ("R64 新方 龙血丹",                  "longxue:  { name: '龙血丹',   minutes: 360, cost: 60000,  rarity: '传说', unlockLevel: 6, summary: '永久 气血上限+500 体魄+50', profGain: 100 },", 1),
        ("R64 新方 九转金丹",                "jiuzhuan: { name: '九转金丹', minutes: 720, cost: 120000, rarity: '仙品', unlockLevel: 8, summary: '服用 修为+5万｜永久 全属性+1000 寿命上限+1000年', profGain: 500 },", 1),
        ("R64 旧方 聚气丹 带 rarity/unlock",  "juqi:     { name: '聚气丹',   minutes: 30,  cost: 5000,   rarity: '普通', unlockLevel: 1, summary: '服用 修为+150', profGain: 10 },", 1),
        ("R64 旧方 凝元丹 丹囊语义保留",       "ningyuan: { name: '凝元丹',   minutes: 120, cost: 20000,  rarity: '稀有', unlockLevel: 1, summary: '出炉入丹囊：渡劫垫刀，每颗天劫成功率+3%', profGain: 30 },", 1),
        ("R64 旧方 破境丹 带 summary",        "pojing:   { name: '破境丹',   minutes: 480, cost: 80000,  rarity: '传说', unlockLevel: 5, summary: '服用 修为+1万｜永久 神识+50 体魄+50 攻击+30 防御+30', profGain: 100 },", 1),
        # ---- S2/S3 ----
        ("R64 alchemyRecipe 返回类型放宽",    "function alchemyRecipe(key: unknown): AlchemyRecipeDef | null {", 1),
        ("R64 alchemyRecipeByName 类型放宽",  "function alchemyRecipeByName(name: unknown): AlchemyRecipeDef | null {", 1),
        # ---- S4 ----
        ("R64 start 解析 alchemyLevel",     "alcLv = Math.max(1, Math.min(9, Number(sd0?.player?.alchemyLevel) || 1));", 1),
        ("R64 start 门槛 409",              "if (alcLv < (recipe.unlockLevel || 1)) return res.status(409).json({ error: `丹道造诣不足：此方需第 ${recipe.unlockLevel || 1} 层，你当前第 ${alcLv} 层` });", 1),
        # ---- S5 ----
        ("R64 claim 熟练度入账块",           "const profGain = Math.max(0, Math.floor((recipe ? (recipe.profGain || 0) : 0) * ALCHEMY_PROF_FURNACE_MULT));", 1),
        ("R64 claim 兼容旧档 alchemyExp",    "Number(pl.alchemyProficiency != null ? pl.alchemyProficiency : pl.alchemyExp) || 0", 1),
        ("R64 claim 升层循环",              "while (lv < 9 && nextAt > 0 && prof >= nextAt) { prof -= nextAt; lv += 1; profUp = true; nextAt = ALCHEMY_PROF_GATE[lv] || 0; }", 1),
        ("R64 claim 写回双字段",             "pl.alchemyLevel = lv; pl.alchemyProficiency = prof;", 1),
        ("R64 claim 失败不阻塞出炉",         "if (!up.ok) { profGained = 0; profLevel = 0; profNow = 0; profNext = 0; profUp = false; console.error('alchemy claim prof save error:', up.error); }", 1),
        ("R64 claim 响应带 prof",           "prof: profGained > 0 ? { gained: profGained, level: profLevel, proficiency: profNow, nextAt: profNext, leveledUp: profUp } : null", 1),
        # ---- 冻结（本环不得回踩）----
        ("冻结 炉位数 ALCHEMY_SLOTS=3",      "const ALCHEMY_SLOTS = 3;", 1),
        ("冻结 返还率 YIELD_RATE=1.5",       "const ALCHEMY_YIELD_RATE = 1.5;", 1),
        ("冻结 asStr 收口未回退",            "Object.prototype.hasOwnProperty.call(ALCHEMY_RECIPES, asStr(key))", 1),
        ("冻结 claim 409 并发守卫未动",       "if (!del.changes) return res.status(409).json({ error: '该炉已领取' });", 1),
        ("冻结 claim 删行语句未动",           "DELETE FROM alchemy WHERE id = ? AND player_id = ?", 1),
        ("冻结 claim 凝元丹入囊未动",         "pill_stash = pill_stash + 1", 1),
        ("冻结 start 补偿删炉语句未动",       "await dbRun('DELETE FROM alchemy WHERE id = ?', [ins.lastID]);", 1),
        ("冻结 成熟判定纯函数未动",           "function alchemyIsReady(matureAt: number, nowMs: number): boolean { return nowMs >= matureAt; }", 1),
        # ---- 红线：claim 失败路径 403 计数不变（本环只新增 409）----
    ]
    base409 = src.count("res.status(409")
    gates.append(("红线 res.status(409) 恰 +1（仅 S4 门槛；S5 不加 409）", "res.status(409", base409 + 1))
    ok = True
    for item in gates:
        if len(item) == 3:
            label, needle, exp = item
            why = ""
        else:
            label, needle, exp, why = item
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d expect==%d %s" % ("OK" if good else "FAIL", label, act, exp, why))

    if not ok:
        fail("门禁未全绿，未写回")

    # 6) 往返自证
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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r064-", suffix=".tmp")
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
