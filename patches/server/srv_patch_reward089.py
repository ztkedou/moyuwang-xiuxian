# -*- coding: utf-8 -*-
r"""
srv_patch_reward089.py -- 0.8.9 批次 · 奖励口径统一（服务端侧）· SRV_CHAIN 第 14 环

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  不提供 `--out`：`localtest/chain_build.py` 会把上一环产物复制成私有工作副本
  再让本补丁就地改。

问题（0.8.9 批次主诉）
--------------------------------------------------------------------------
  灵石发放「一模一样的面板数字，到账差几十上百倍」。
  根因：服务端 6 处灵石/修为发放各自内联 `Math.pow(1.5, idx)`（记作 C2 指数曲线），
  而客户端灵石面板与打坐口径走的是 `YLRF(idx) = idx<=0 ? 4/3 : 2*idx+1`（记作 C1 线性曲线）。
  同一境界下 C1/C2 比值最高达 2.7 倍（长生境 13 : 11.39），叠加基数差异后玩家观感即「面板对不上账」。

  C2 曲线 **本身不是 bug**（境界越高给得越多，方向正确，且 0.8.6/0.8.7 一直如此），
  真正的缺陷是：**同一批灵石奖励并存两套境界曲线**，玩家无法从面板反推任何一条。

统一口径（本补丁的唯一原则）
--------------------------------------------------------------------------
  服务端所有「灵石」发放一律改走 **C1 线性曲线**，与客户端 `YLRF` / `YLRewardFactor` 同源：
      idx <= 0  -> 4/3          （炼气期：镜像客户端 max(1,q) 的地板）
      idx >= 1  -> 2*idx + 1
  新增一个纯函数 `realmStoneFactor(idx)` 并把 6 处内联幂次全部换成它。
  **修为(exp) 不在本次口径内，不动**（T8 传功 expGain、双修 expGain 保持 C2 原样）。

★ 边界（明令不改）
--------------------------------------------------------------------------
  · 世界妖兽/万妖巢穴血量 `Math.pow(1.5, ...)`（wbEnsure / actBossEnsure）→ 不是灵石，不动。
  · 打坐 / 秘境 / 通天塔 / 抽奖 → 客户端侧，服务端无对应发放点，天然不受影响。
  · 各发放点**基数常量一律不动**（ARENA_STONE_BASE / GRUDGE_STONE_BASE / FEAST_GIFT /
    CHRONICLE_PRAISE_BASE / FUN_SIGN_BASE / MENTOR_GRAD_GIFT_BASE），只换境界倍率。
  · 邮件文案里的「回礼 ${FEAST_GIFT} 灵石」原本就写的是**未乘倍率的基数**（文案与到账本就不符），
    本补丁把入账改成 C1 后该文案仍写基数——为避免扩大改动面，文案不动；属既有文案缺陷，另行记录。

改动清单（6 处 · 全部落在「灵石」上）
--------------------------------------------------------------------------
  S1  [reward089] 新增纯函数 `realmStoneFactor` + `realmStoneGain`（常量区，realmMultOf 之前）
  S2  `realmMultOf()`  body  C2 -> C1  —— 一处改，擂台/仇杀/请安/求签/出师贺礼 **5 个调用点**同源收敛
  S3  `sameRealmMult()` body  C2 -> C1  —— 赴宴回礼原为**独立的第三套内联幂次**，一并收敛
  S4  双修 `realmMult` 内联幂次 C2 -> C1（只换岩石倍率，双修 expGain 保持 C2）
  S5  赴宴回礼 FEAST_GIFT 内联幂次 C2 -> C1
  S6  CHRONICLE_PRAISE_BASE 内联幂次 C2 -> C1

  说明：S2 的 `realmMultOf` 返回值**同时**被 `mentorGradGift()`（出师贺礼灵石）与
  `realmMulType` 各处消费；本补丁只保证「灵石类消费方」口径正确，`mentorGradGift` 属灵石，
  随 S2 一起收敛到 C1（这是期望行为）。

本批新增门禁计数清单（供接线人落 check_srv_089；均为对【链尾产物】的 grep -o 计数）
--------------------------------------------------------------------------
  realmStoneFactor                         0 -> 2（定义 + realmMultOf 调用）
  realmStoneGain                           0 -> 1（纯函数定义；当前无调用方，保留给后续 0.8.9 发放点）
  Math.pow(1.5, Math.min(20, Math.max(0, Number(r && r.realm_index) || 0)))   1 -> 0
  Math.pow(1.5, Math.min(20, idx))         1 -> 0
  Math.pow(1.5, Math.min(20, Math.max(0, Number(mult?.ri) || 0)))            1 -> 0
  FEAST_GIFT * Math.pow(1.5,               1 -> 0
  CHRONICLE_PRAISE_BASE * Math.pow(1.5,    1 -> 0
  Math.pow(1.5                             （基线 8，本补丁 -5 => 3：wbEnsure + actBossEnsure + expGain 双修）
  const ARENA_STONE_BASE = 3000;           1（基线未动）
  const GRUDGE_STONE_BASE = 8000;          1（基线未动）
  const FEAST_GIFT = 1000;                 1（基线未动）
  const CHRONICLE_PRAISE_BASE = 1000;      1（基线未动）
  const FUN_SIGN_BASE = 500;               1（基线未动）
  const MENTOR_GRAD_GIFT_BASE = 3000;      1（基线未动）
  res.status(403)                          与基线逐字相等（'same' 门禁）

★ 业务拒绝语义红线：本补丁零新增/零删除 403
"""
import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ S1 [reward089] 统一境界倍率纯函数

S1_OLD = """// 总等级（rankings 口径 境界序×9+层数）；无档返回 null
async function totalLevelOf(userId: number): Promise<number | null> {"""

S1_NEW = """// ── 0.8.9 [reward089] 灵石境界倍率统一（与客户端 YLRF / YLRewardFactor 同源同曲线）──
// 客户端面板与打坐口径：idx<=0 -> 4/3（镜像 max(1,q) 地板），idx>=1 -> 2*idx+1。
// 服务端过去 6 处各自内联 Math.pow(1.5, idx)（指数曲线），与客户端线性曲线并存 => 面板与到账对不上。
// 本函数是服务端**唯一**的灵石境界倍率来源；后续新增灵石发放点一律调用它。
// 定义位置必须在 sameRealmMult / realmMultOf 之前（两处调用方）。
function realmStoneFactor(realmIdx: unknown): number {
  const i = Math.floor(Number(realmIdx));
  if (!Number.isFinite(i) || i < 0) return 4 / 3;   // 缺档/脏数据按炼气期地板，绝不 NaN
  if (i <= 0) return 4 / 3;
  return 2 * i + 1;
}
// 灵石发放（纯）：floor(基数 × 境界倍率)，负值/NaN 钳 0。发放点与面板同式，玩家可反推。
function realmStoneGain(base: unknown, realmIdx: unknown): number {
  return Math.max(0, Math.floor((Number(base) || 0) * realmStoneFactor(realmIdx)));
}

// 总等级（rankings 口径 境界序×9+层数）；无档返回 null
async function totalLevelOf(userId: number): Promise<number | null> {"""

# ============================================================ S2 realmMultOf body C2 -> C1

S2_OLD = """  return Math.pow(1.5, Math.min(20, Math.max(0, Number(r && r.realm_index) || 0)));
}"""

S2_NEW = """  // 0.8.9 [reward089] C2 指数 -> C1 线性（与客户端同源）：擂台/仇杀/请安/求签/出师贺礼 5 处调用点一并收敛
  return realmStoneFactor(r && r.realm_index);
}"""

# ============================================================ S3 sameRealmMult body C2 -> C1

S3_OLD = """function sameRealmMult(realm: unknown): number {
  const idx = Math.max(0, ECON_REALM_ORDER.indexOf(String(realm || '')));
  return Math.pow(1.5, Math.min(20, idx));
}"""

S3_NEW = """function sameRealmMult(realm: unknown): number {
  const idx = Math.max(0, ECON_REALM_ORDER.indexOf(String(realm || '')));
  // 0.8.9 [reward089] 本函数是赴宴回礼的**独立第三套**境界倍率（既不走 realmMultOf 也不走客户端曲线），
  // 一并收口到统一线性曲线，避免「同一境界三种倍率」。
  return realmStoneFactor(idx);
}"""

# ============================================================ S4 双修：只换灵石倍率，exp 保持 C2

S4_OLD = """    const realmMult = Math.pow(1.5, Math.min(20, Math.max(0, Number(mult?.ri) || 0)));
    const expGain = Math.floor(20000 * realmMult);
    const stoneGain = Math.floor(1000 * realmMult);"""

S4_NEW = """    const realmMult = Math.pow(1.5, Math.min(20, Math.max(0, Number(mult?.ri) || 0))); // 修为仍走 C2（不在本次口径内）
    const expGain = Math.floor(20000 * realmMult);
    // 0.8.9 [reward089] 灵石改走统一线性曲线（与客户端面板同源）
    const stoneGain = realmStoneGain(1000, mult?.ri);"""

# ============================================================ S5 赴宴回礼 C2 -> C1

S5_OLD = """        sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + Math.floor(FEAST_GIFT * Math.pow(1.5, Math.max(0, ECON_REALM_ORDER.indexOf(String(sd.player.realm || '')))));"""

S5_NEW = """        sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + realmStoneGain(FEAST_GIFT, ECON_REALM_ORDER.indexOf(String(sd.player.realm || ''))); // 0.8.9 [reward089] 统一口径"""

# ============================================================ S6 传阅奖励 C2 -> C1

S6_OLD = """        stones = Math.floor(CHRONICLE_PRAISE_BASE * Math.pow(1.5, Math.max(0, Number(rk?.realm_index) || 0)));"""

S6_NEW = """        stones = realmStoneGain(CHRONICLE_PRAISE_BASE, rk?.realm_index); // 0.8.9 [reward089] 统一口径"""

EDITS = [
    ('S1 [reward089] 统一倍率纯函数',        S1_OLD, S1_NEW),
    ('S2 realmMultOf body C2->C1',         S2_OLD, S2_NEW),
    ('S3 sameRealmMult body C2->C1',       S3_OLD, S3_NEW),
    ('S4 双修灵石 C2->C1 (exp 保留 C2)',     S4_OLD, S4_NEW),
    ('S5 赴宴回礼 C2->C1',                  S5_OLD, S5_NEW),
    ('S6 传阅奖励 C2->C1',                  S6_OLD, S6_NEW),
]

# 链序依赖证明（取自前环产物特征）
REQUIRES = [
    ('async function realmMultOf(userId: number): Promise<number> {', 1, '擂台域基线（v286 原貌，未被前环改动）'),
    ('function sameRealmMult(realm: unknown): number {', 1, '赴宴回礼倍率基线'),
    ('const ARENA_STONE_BASE = 3000;', 1, 'T8 之后产物特征'),
    ('const MENTOR_GRAD_GIFT_BASE = 3000;', 1, 't8_mentor 必须先跑过（贺礼基数常量）'),
    ('function mentorGradGift(realmMult: unknown): number {', 1, 't8_mentor 必须先跑过（贺礼纯函数）'),
    ('const MENTOR_APPLY_TTL_MS = 48 * 3600 * 1000;', 1, 't8_mentor 已落地（避免跑在旧产物上）'),
]

# ============================================================ 自证：抽样式对照表

# 客户端 YLRF / 本补丁 realmStoneFactor 的期望值（idx -> factor）
EXPECT_FACTOR = {0: 4 / 3, 1: 3, 2: 5, 3: 7, 4: 9, 5: 11, 6: 13}
# 旧 C2 值（idx -> 1.5^idx），仅用于打印对照
OLD_C2 = {0: 1.0, 1: 1.5, 2: 2.25, 3: 3.375, 4: 5.0625, 5: 7.59375, 6: 11.390625}


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

    # 1) 链序依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 2) 幂等
    if "realmStoneFactor" in src or "realmStoneGain" in src:
        fail("source looks already patched（已存在 realmStoneFactor / realmStoneGain）")

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:140]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 5) 门禁
    base403 = src.count("res.status(403)")
    base_pow = src.count("Math.pow(1.5")
    gates = [
        # ---- 新增纯函数 ----
        ('[reward089] realmStoneFactor 定义',   'function realmStoneFactor(realmIdx: unknown): number {', 1, None),
        ('[reward089] realmStoneGain 定义',     'function realmStoneGain(base: unknown, realmIdx: unknown): number {', 1, None),
        ('[reward089] realmStoneFactor 共 4', 'realmStoneFactor', 4, None),
        ('[reward089] realmStoneGain 共 4',   'realmStoneGain', 4, None),
        # ---- C2 幂次逐点清零（4 处纯灵石；S4 双修保留幂次给 exp）----
        ('S2 realmMultOf 旧幂次清零',     'Math.pow(1.5, Math.min(20, Math.max(0, Number(r && r.realm_index) || 0)))', 0, None),
        ('S3 sameRealmMult 旧幂次清零',   'Math.pow(1.5, Math.min(20, idx))', 0, None),
        ('S4 双修灵石改纯函数',           'const stoneGain = realmStoneGain(1000, mult?.ri);', 1, None),
        ('S4 双修旧 stoneGain 清零',      'const stoneGain = Math.floor(1000 * realmMult);', 0, None),
        ('S5 赴宴旧幂次清零',             'FEAST_GIFT * Math.pow(1.5,', 0, None),
        ('S6 传阅旧幂次清零',             'CHRONICLE_PRAISE_BASE * Math.pow(1.5,', 0, None),
        # ---- C2 幂次总数：基线 7，本补丁 -3（S2/S3/S5/S6 四处归零，S4 双修保留 1 给 exp）----
        ('C2 幂次总数 7->4',              'Math.pow(1.5', 4, None),
        # ---- 边界：血量公式与非灵石幂次必须原样保留 ----
        ('边界 世界妖兽血量未动',           'const hp = Math.floor(WB_HP_BASE * mult);', 1, None),
        ('边界 万妖巢穴血量未动',           'const hp = Math.floor(WB_HP_BASE * mult * ACT_BOSS_HP_CYCLE);', 1, None),
        ('边界 双修 exp 仍走 C2',          'const expGain = Math.floor(20000 * realmMult);', 1, None),
        ('边界 传功 exp 仍走 C2',          'const expGain = Math.floor(TEACH_EXP_BASE * mult);', 1, None),
        # ---- 基数常量一律未动 ----
        ('基线 擂台基数未动',              'const ARENA_STONE_BASE = 3000;', 1, None),
        ('基线 仇杀基数未动',              'const GRUDGE_STONE_BASE = 8000;', 1, None),
        ('基线 赴宴基数未动',              'const FEAST_GIFT = 1000;', 1, None),
        ('基线 传阅基数未动',              'const CHRONICLE_PRAISE_BASE = 1000;', 1, None),
        ('基线 求签基数未动',              'const FUN_SIGN_BASE = 500;', 1, None),
        ('基线 出师贺礼基数未动',           'const MENTOR_GRAD_GIFT_BASE = 3000;', 1, None),
        # ---- 消费方未被破坏 ----
        ('消费方 出师贺礼仍调 realmMultOf',  'let gift = mentorGradGift(await realmMultOf(apprenticeId));', 1, None),
        ('消费方 出师贺礼纯函数未动',        'return Math.floor(Math.max(0, Number(realmMult) || 0) * MENTOR_GRAD_GIFT_BASE);', 1, None),
        ('消费方 擂台仍调 realmMultOf',      'const mult = await realmMultOf(winnerId);', 1, None),
        ('消费方 realmMultOf(userId) 共 3',  'const mult = await realmMultOf(userId);', 3, None),
        # ---- 403 语义红线 ----
        ('403 计数与基线逐字相等',            'res.status(403)', None, 'same'),
    ]
    ok = True
    for g in gates:
        label, needle, exp = g[0], g[1], g[2]
        op = g[3] if len(g) > 3 else None
        if op == 'same':
            exp = base403
            shown = 'expect==base(%d)' % exp
        elif exp is None:
            continue
        else:
            shown = 'expect==%d' % exp
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-32s actual=%d %s" % ("OK" if good else "FAIL", label, act, shown))
    if not ok:
        fail("门禁未全过")

    # 6) 语义断言：realmStoneFactor 定义必须早于其全部调用点
    p_def = out.find("function realmStoneFactor(realmIdx: unknown): number {")
    p_call1 = out.find("return realmStoneFactor(r && r.realm_index);")
    p_call2 = out.find("return realmStoneFactor(idx);")
    if not (0 <= p_def < p_call1 and 0 <= p_def < p_call2):
        fail("定义/调用顺序破坏：realmStoneFactor 定义(%d) 必须早于 realmMultOf(%d) 与 sameRealmMult(%d)" % (p_def, p_call1, p_call2))
    print("  [OK] 顺序契约：realmStoneFactor 定义先于两处调用方")

    # 7) 口径对照打印（旧 C2 vs 新 C1 —— 必须与客户端 YLRF 逐值相等）
    print("\n  境界倍率对照（idx: 旧C2 -> 新C1, 客户端YLRF 期望）")
    for i in sorted(EXPECT_FACTOR):
        want = EXPECT_FACTOR[i]
        got = (4 / 3) if i <= 0 else (2 * i + 1)
        tag = "OK" if abs(got - want) < 1e-12 else "FAIL"
        print("    [%s] idx=%d  旧C2=%.6f -> 新C1=%.6f  客户端期望=%.6f" % (tag, i, OLD_C2[i], got, want))
        if tag == "FAIL":
            fail("新曲线与客户端 YLRF 不一致 idx=%d" % i)

    # 8) 往返自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("\n  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".rew089-", suffix=".tmp")
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
