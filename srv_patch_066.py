# -*- coding: utf-8 -*-
r"""
srv_patch_066.py -- R-066 宗门「功法阁」：贡献值整体重做 + 修满化形（服务端环）

CLI 契约（与链上其余补丁一致，照 srv_patch_063.py 抄）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径（默认 srv/index_v28.ts）；`--check` 只校验不写。

=========================================================================== 为什么服务端必须改
R-066 两件事都落服务端：
  ① 贡献值重做 —— 客户端面板的消耗只是显示；真实扣费在 /api/sect/gongfa/learn|upgrade
     里走 sectGfAdvance → sectGfCost(SECT_GF_TIER_BASE)。只改客户端 = 面板显示新价、
     服务端按旧价扣费（或反之被服务端拒绝），两头不一致必炸。
  ② 修满化形 —— unlockedArts 虽是客户端权威字段，但「化形」是服务端才能盖章的
     一次性事件（权威层数在 player_sect_gongfa 表）：不落服务端，改档刷新即可
     白嫖重复化形。故新增 /api/sect/gongfa/convert 端点。

=========================================================================== 改点（4 组）
  T1  SECT_GF_TIER_BASE = {1:100,2:250,3:600,4:1500} → {1:200,2:600,3:1500,4:4000}
      （与客户端 yl_066_ext.py 同源）。
  T2  sectGfCost：线性 base×level → 指数 floor(base×2^(level-1))（客户端同式）。
      新满级总耗：一阶 6200 / 二阶 18600 / 三阶 46500 / 四阶 124000；
      12 部全满 585900（旧 110250，×5.3）。AI 代决依据见拍板文件
      《2026-10-01_*_R-066_功法阁贡献重做与修满化形.md》。
  T3  GET /api/sect/gongfa 响应下发 converted（player.sectGfConverted 整表），
      供客户端面板渲染「已化形/可化为」。
  T4  新增 POST /api/sect/gongfa/convert：5 层大成 → **消耗宗门贡献**（化形费 =
      f(品阶) = SECT_GF_TIER_BASE[tier] × SECT_GF_CONVERT_MULT(16) = 第 5 层单价；
      黄 3200 / 玄 9600 / 地 24000 / 天 64000）把 SECT_GF_CONVERT[id] 实装功法写入
      player.unlockedArts + 盖章 player.sectGfConverted[id]=1。
      定价理由：修满一部总耗 = 基价 × (1+2+4+8+16) = 基价 × 31，化形费 = 基价 × 16
      = 修满总耗的 51.6%（同量级、恒低于修满，不会贵到没人转化）；与品阶同源，
      天品是黄品的 20 倍。贡献日收入实测 1.2k~6k ⇒ 黄品约 0.5~2.7 天、天品约 11~53 天。
      权威扣费在 updatePlayerSave 锁内（客户端只显示、不拦）；未修满/已化形/贡献不足
      一律 409（**绝不用 403**：Xc 对 403 强制登出，0.8.5 §21.3 / 0.8.6 §22.7 纪律）。
      R-067 扩品阶只需加 SECT_GF_TIER_BASE 键，化形费自动跟随（与客户端 YlxwSectGfCvtFee 同源）。

=========================================================================== 链序
  ★ 依赖 sectgf 链已在位（REQUIRES 断言 SECT_GF_BY_ID / player_sect_gongfa /
    sectGfPlayerOf / sectGfWriteLimit / updatePlayerSave）。与 srv_patch_061/062/063
    （演武场/秘境/地宫）零锚点交集，先后皆可；建议一并挂 SRV_CHAIN 链尾。

=========================================================================== 扩充留口（R-067）
  SECT_GF_CONVERT 是纯数据表：R-067 功法大重做扩数量时，与客户端
  yl_066_ext.py 的 YLXW_SECT_GF_CONVERT 同源同扩（键=sgf id，值=基座 is 表 id），
  端点与校验逻辑零改动。TIER_BASE 新档位直接加键即可。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ REQUIRES / 幂等

REQUIRES = [
    ("sectgf 目录已在位", "SECT_GF_BY_ID", 2, ">="),
    ("权威层数表已在位", "player_sect_gongfa", 5, ">="),
    ("sectGfPlayerOf 可用", "async function sectGfPlayerOf", 1, "=="),
    ("sectGfRows 可用", "async function sectGfRows", 1, "=="),
    ("sectGfLevel 可用", "function sectGfLevel", 1, "=="),
    ("写档器可用", "function updatePlayerSave(", 1, "=="),
    ("写限流可用", "sectGfWriteLimit", 3, ">="),
]
NOT_PATCHED = ["[r066]", "ALREADY_CONVERTED", "SECT_GF_CONVERT"]

# ============================================================ T1 档位基价

T1_OLD = "const SECT_GF_TIER_BASE: Record<number, number> = { 1: 100, 2: 250, 3: 600, 4: 1500 };"
T1_NEW = ("const SECT_GF_TIER_BASE: Record<number, number> = { 1: 200, 2: 600, 3: 1500, 4: 4000 }; "
          "// [r066] R-066 贡献重做：基价 ×2~×2.7（与客户端 yl_066_ext.py 同源）")

# ============================================================ T2 消耗公式（线性 → 指数）

T2_OLD = (
    "function sectGfCost(tier: unknown, level: unknown): number {\n"
    "  return (SECT_GF_TIER_BASE[Math.floor(Number(tier) || 0)] || 0) * Math.max(1, Math.floor(Number(level) || 1));\n"
    "}"
)
T2_NEW = (
    "function sectGfCost(tier: unknown, level: unknown): number {\n"
    "  const base = SECT_GF_TIER_BASE[Math.floor(Number(tier) || 0)] || 0;\n"
    "  const lv = Math.max(1, Math.floor(Number(level) || 1));\n"
    "  return Math.floor(base * Math.pow(2, lv - 1)); // [r066] 每层 ×2 指数递增（客户端同式）\n"
    "}"
)

# ============================================================ T3 GET 下发 converted

T3_OLD = "      levels: sectGfMirror(levels),\n    });"
T3_NEW = (
    "      // [r066] 化形盖章表随目录下发，面板据此渲染「已化形 / 可化为」\n"
    "      converted: (pl.sectGfConverted && typeof pl.sectGfConverted === 'object') ? pl.sectGfConverted : {},\n"
    "      levels: sectGfMirror(levels),\n"
    "    });"
)

# ============================================================ T4 化形表 + 端点

T4_OLD = "// ── V27 限流：读 60/min、写 20/min（按用户分桶；rateLimit 实现见 P1-4/P1-5 段）──"

T4_NEW = """// ── [r066] R-066 修满化形：宗门功法 5 层大成 → 消耗宗门贡献解锁对应「游戏实装」功法（基座 is 表 id，
//   写入 player.unlockedArts，功法界面即可修炼）。幂等：sectGfConverted 真值表，已化形原地不动。
//   化形费 = f(品阶) = 基价 × 16（= 第 5 层单价，= 修满总耗 基价×31 的 51.6%）；贡献不足/未修满/已化形一律 409。
//   权威扣费在 updatePlayerSave 锁内（客户端只显示、不拦）；绝不用 403（Xc 对 403 强制登出）。
//   R-067 功法大重做扩表：与客户端 yl_066_ext.py 的 YLXW_SECT_GF_CONVERT 同源同扩，端点零改动。
const SECT_GF_CONVERT_MULT = 16; // [r066] 化形费倍数（= 第 5 层 2^4；与客户端 yl_066_ext.py 的 YlxwSectGfCvtFee 同源）
function sectGfConvertFee(tier: unknown): number {
  return (SECT_GF_TIER_BASE[Math.floor(Number(tier) || 0)] || 0) * SECT_GF_CONVERT_MULT;
}
const SECT_GF_CONVERT: Record<string, string> = {
  'sgf-t1-atk': 'art-sharp-blade',
  'sgf-t1-def': 'art-earth-core',
  'sgf-t1-psi': 'art-moonlight-refine',
  'sgf-t2-atk': 'art-wind-sword',
  'sgf-t2-def': 'art-golden-protection',
  'sgf-t2-psi': 'art-frost-breath',
  'sgf-t3-atk': 'art-sword-intent',
  'sgf-t3-def': 'art-earth-mountain',
  'sgf-t3-psi': 'art-starlight-gather',
  'sgf-t4-atk': 'art-immortal-sword',
  'sgf-t4-def': 'art-earth-immortal',
  'sgf-t4-psi': 'art-dao-heart',
};
const SECT_GF_CONVERT_NAMES: Record<string, string> = {
  'art-sharp-blade': '锐刃诀',
  'art-earth-core': '土核功',
  'art-moonlight-refine': '月华淬炼诀',
  'art-wind-sword': '疾风剑',
  'art-golden-protection': '金甲护体',
  'art-frost-breath': '寒冰吐息',
  'art-sword-intent': '剑意诀',
  'art-earth-mountain': '山岳功',
  'art-starlight-gather': '聚星诀',
  'art-immortal-sword': '斩仙剑诀',
  'art-earth-immortal': '土仙体',
  'art-dao-heart': '道心诀',
};
app.post('/api/sect/gongfa/convert', authenticateToken, sectGfWriteLimit, async (req: any, res: any) => {
  try {
    const id = String(req.body?.id || '');
    const def = SECT_GF_BY_ID[id];
    const artId = SECT_GF_CONVERT[id];
    if (!def || !artId) return res.status(400).json({ error: '未知的宗门功法', code: 'BAD_GONGFA' });
    const pl = await sectGfPlayerOf(req.user.id);
    if (!pl || !pl.sectId) return res.status(400).json({ error: '你还没有加入宗门', code: 'NO_SECT' });
    const levels = await sectGfRows(req.user.id);
    const cur = sectGfLevel(levels[id]);
    if (cur < SECT_GF_MAX_LEVEL) {
      return res.status(409).json({ error: '该功法尚未修满（需 5 层大成）', code: 'NOT_MAXED', level: cur });
    }
    const fee = sectGfConvertFee(def.tier); // [r066] 化形费 = f(品阶) = 基价 × 16
    const contrib = Math.max(0, Math.floor(Number(pl.sectContribution) || 0));
    const prevCvt = (pl.sectGfConverted && typeof pl.sectGfConverted === 'object') ? pl.sectGfConverted : {};
    if (prevCvt[id]) {
      return res.status(409).json({ error: '该功法已化形，无需重复转化', code: 'ALREADY_CONVERTED' });
    }
    if (contrib < fee) {
      // [r066] 贡献不足 → 409（**绝不用 403**：Xc 对 403 强制登出）
      return res.status(409).json({ error: '宗门贡献不足（需 ' + fee + '）', code: 'INSUFFICIENT_CONTRIBUTION', cost: fee, contribution: contrib });
    }
    let done = false;
    let shortfall = false;
    const r = await updatePlayerSave(req.user.id, (sd: any) => {
      const p = sd && sd.player;
      if (!p) return;
      const prev = (p.sectGfConverted && typeof p.sectGfConverted === 'object') ? p.sectGfConverted : {};
      if (prev[id]) return; // 锁内幂等闸：已化形 → 原地不动、零副作用
      const bal = Math.max(0, Math.floor(Number(p.sectContribution) || 0));
      if (bal < fee) { shortfall = true; return; } // 锁内二次校验：余额不足 → 原地不动、零副作用
      p.sectContribution = bal - fee; // [r066] 权威扣费（客户端只显示，不拦）
      const cvt: Record<string, number> = Object.assign({}, prev);
      cvt[id] = 1;
      const arts: string[] = Array.isArray(p.unlockedArts) ? p.unlockedArts.slice() : [];
      if (arts.indexOf(artId) < 0) arts.push(artId);
      p.unlockedArts = arts;
      p.sectGfConverted = cvt;
      done = true;
    });
    if (!r.ok) return res.status(400).json({ error: r.error || '入账失败' });
    if (!done) {
      if (shortfall) return res.status(409).json({ error: '宗门贡献不足（需 ' + fee + '）', code: 'INSUFFICIENT_CONTRIBUTION', cost: fee, contribution: contrib });
      return res.status(409).json({ error: '该功法已化形，无需重复转化', code: 'ALREADY_CONVERTED' });
    }
    const fresh = await sectGfPlayerOf(req.user.id);
    const freshCvt = (fresh && fresh.sectGfConverted && typeof fresh.sectGfConverted === 'object') ? fresh.sectGfConverted : {};
    const artName = SECT_GF_CONVERT_NAMES[artId] || artId;
    return res.status(200).json({
      message: '【' + def.name + '】大成化形！已耗 ' + fee + ' 贡献，将可用功法【' + artName + '】收入囊中，可在【功法】界面修炼。',
      id, art: artId, artName, cost: fee, contribution: contrib - fee,
      converted: freshCvt,
      levels: await sectGfRows(req.user.id),
    });
  } catch (e: any) {
    console.error('sect gongfa convert error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// ── V27 限流：读 60/min、写 20/min（按用户分桶；rateLimit 实现见 P1-4/P1-5 段）──"""

EDITS = [
    ("T1_tier_base", T1_OLD, T1_NEW),
    ("T2_cost_formula", T2_OLD, T2_NEW),
    ("T3_get_converted", T3_OLD, T3_NEW),
    ("T4_convert_endpoint", T4_OLD, T4_NEW),
]

# 冻结基线（打补丁前后计数必须不变）：证明本环没碰相邻需求 / 既有路由的面。
# 注意：本环 T4 会新增一条 convert 路由 → sectGfWriteLimit 计数 +1（下方按 base+1 校验），
#       故它不进「不变」基线，仅纳入 base 供 +1 派生；其余均为本环不得触碰的既有面。
FREEZE_NEEDLES = [
    "res.status(403",                       # 红线：不得新增 403（Xc 对 403 强制登出）
    "require(",                             # ESM 约束：不得引入 CommonJS require
    "app.post('/api/sect/gongfa/learn'",
    "app.post('/api/sect/gongfa/upgrade'",
    "p.sectContribution = bal - cost;",     # learn/upgrade 扣费路径（本环不得改动）
    "SECT_GF_LIST",                         # 目录表（本环不得改动）
    "sectGfAdvance",                        # learn/upgrade 共用核心（本环不得改动）
    "sectGfWriteLimit",                     # 写限流（本环新增路由会 +1，按 base+1 校验）
]


def fail(msg: str) -> None:
    sys.stderr.write("FAIL: " + msg + "\n")
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-066 sect gongfa: contribution rework + maxed-convert (srv ring)")
    ap.add_argument("--src", default=SRC, help="chain tip to patch in place (default: %(default)s)")
    ap.add_argument("--check", action="store_true", help="validate only, write nothing")
    ap.add_argument("--selftest", action="store_true", help="alias of --check (validate only, write nothing)")
    args = ap.parse_args()
    src_path = args.src

    if not os.path.isfile(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 幂等：不允许重复打
    for marker in NOT_PATCHED:
        if marker in src:
            fail("source already contains %r; refusing to double-patch" % marker)

    # REQUIRES：sectgf 链必须在位
    for label, needle, expect, op in REQUIRES:
        n = src.count(needle)
        ok = (n == expect) if op == "==" else (n >= expect)
        if not ok:
            fail("REQUIRES %s: %r occurs %d (expect %s %d)" % (label, needle, n, op, expect))

    # 锚点唯一
    for label, old, _new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("anchor %s occurs %d times (expected exactly 1)" % (label, n))

    # 冻结基线：打补丁前统计（打完后必须不变）
    base = {k: src.count(k) for k in FREEZE_NEEDLES}

    out = src
    for label, old, new in EDITS:
        out = out.replace(old, new, 1)

    # round-trip：逆序还原必须逐字节等于原文
    rt = out
    for label, old, new in reversed(EDITS):
        if rt.count(new) != 1:
            fail("round-trip: %s fragment occurs %d in product" % (label, rt.count(new)))
        rt = rt.replace(new, old, 1)
    if rt != src:
        fail("round-trip mismatch")

    # 新端点必须出现在既有 gongfa 路由之后、V27 限流段之前（同作用域）
    if out.index("app.post('/api/sect/gongfa/convert'") < out.index("app.post('/api/sect/gongfa/upgrade'"):
        fail("convert endpoint must be registered after the upgrade route")

    # 语义门禁：化形费落地 + 贡献不足走 409 + 红线 + 冻结面
    gates = [
        ("T4 化形费倍数常量就位", "const SECT_GF_CONVERT_MULT = 16;", 1),
        ("T4 化形费函数就位", "function sectGfConvertFee(tier: unknown): number {", 1),
        ("T4 化形费倍数引用完整", "SECT_GF_CONVERT_MULT", 2),
        ("T4 端点内调用化形费", "const fee = sectGfConvertFee(def.tier);", 1),
        ("T4 贡献不足走 409(两处)", "code: 'INSUFFICIENT_CONTRIBUTION', cost: fee, contribution: contrib", 2),
        ("T4 锁内权威扣费就位", "p.sectContribution = bal - fee;", 1),
        ("T4 回执带化形费/余额", "id, art: artId, artName, cost: fee, contribution: contrib - fee,", 1),
        ("T4 未修满 409 仍在", "code: 'NOT_MAXED', level: cur", 1),
        ("T4 已化形 409 仍在(两处)", "code: 'ALREADY_CONVERTED'", 2),
        ("T4 幂等盖章仍在", "p.sectGfConverted = cvt;", 1),
        ("T4 旧免费文案已清零", "不扣贡献 = 修满的奖励", 0),
        ("T4 映射名表就位", "const SECT_GF_CONVERT_NAMES: Record<string, string> = {", 1),
        ("T4 新路由挂写限流(+1)", "sectGfWriteLimit", base["sectGfWriteLimit"] + 1),
        # ---- 冻结：相邻需求 / 既有路由一字不动 ----
        ("冻结 化形映射末条未动", "'sgf-t4-psi': 'art-dao-heart',", 1),
        ("冻结 learn/upgrade 扣费未动", "p.sectContribution = bal - cost;", base["p.sectContribution = bal - cost;"]),
        ("冻结 目录表未动", "SECT_GF_LIST", base["SECT_GF_LIST"]),
        ("冻结 学习/升级核心未动", "sectGfAdvance", base["sectGfAdvance"]),
        ("冻结 learn 路由未动", "app.post('/api/sect/gongfa/learn'", base["app.post('/api/sect/gongfa/learn'"]),
        ("冻结 upgrade 路由未动", "app.post('/api/sect/gongfa/upgrade'", base["app.post('/api/sect/gongfa/upgrade'"]),
        # ---- 红线 ----
        ("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]),
        ("红线 未新增 require(", "require(", base["require("]),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    print("OK  %s: anchors unique, requires satisfied, round-trip byte-exact, delta=+%d chars"
          % (src_path, len(out) - len(src)))
    for label, old, new in EDITS:
        print("    + %-18s +%d chars" % (label, len(new) - len(old)))

    if args.check or args.selftest:
        print("OK  --check/--selftest: no write performed")
        return

    # 原子写回
    d = os.path.dirname(os.path.abspath(src_path)) or "."
    fd, tmp = tempfile.mkstemp(prefix="_r066_", suffix=".ts", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(out.encode("utf-8"))
        os.replace(tmp, src_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print("OK  written: %s" % src_path)


if __name__ == "__main__":
    main()
