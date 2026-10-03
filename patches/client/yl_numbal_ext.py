# -*- coding: utf-8 -*-
"""
yl_numbal_ext.py — v28 数值重规划（客户端侧）

对应需求：
  #8「仙务心法的数值太简单粗暴了，找一个数值策划重新规划一下」
  #9「之前仙务做了很多新的功能，数值都没有精心设计，把所有数值都优化成比较合理的玩法」

本模块**只做数值**，不碰任何 UI 结构 / 入口 / 面板渲染 / 存档上报。
它由 build 侧在「主注入块」之后调用：
    p.insert_before('numbal-block', 'function YlxwPanelModal(p) {', zh(INJECT_JS) + '\\n')
    gates += numbal.apply(p, {'zh': zh, 'base_text': base})
（本模块不修改 build_v26n.py / yl_v26n_ext.py，锚点全部落在基线 bundle 或既有注入块的字面量上。）

--------------------------------------------------------------------------
一、心法（cultivationArts / is[]）重规划
--------------------------------------------------------------------------
现状（实测，见 _numbal_dump.js 输出）：
  同一「品级」内的「攻击当量总值」极度离散 ——
    黄 17 本：中位 16.8，范围 5~38        （7.6x）
    玄 19 本：中位 78  ，范围 20~150      （7.5x）
    地 18 本：中位 250 ，范围 48~2240     （46.7x，炼魂诀 spirit800/defense400 离群）
    天 28 本：中位 4800，范围 700~120000  （171.4x，混沌归元功 attack2e4/def1.5e4/hp8e4 离群）
  且：
    * 属性加成与玩家境界/等级**完全无关**（Cg() 里只乘 go(art,roots)=1+灵根*0.005），
      炼气期学到「天品 attack 12000」即平推全境界 —— 没有成长曲线。
    * 学习数量无上限、所有心法属性**全部线性叠加**（Cg 对 cultivationArts 全量 forEach）
      —— 最优解恒为「全学」，没有任何取舍空间。
    * expRate 无递减、无上限；bd() 只取 activeArtId，但再乘一个品级系数 {天:2,地:1.5,玄:1.2,黄:1}
      —— 学满后永远挂 art-five-elements / art-universe-devour（expRate 1 × 2 = +200%）。

重规划（本次改动）：
  1. 【同档同强】按 (品级, 境界需求) 单元格的**均值**重算每本心法的属性预算，
     保留各自「侧重」（原 effects 的各维度权重不变），只把总量对齐到单元格均值。
     → 同品级同门槛的心法强度一致，玩家按「流派侧重」而非「数值大小」选心法。
  2. 【门槛补偿】带 spiritualRoot ×1.15 / buildAffinity ×1.10 / sectId ×1.15 预算加成，
     天地之魄专属心法（isHeavenEarthSoulArt，boss 掉落）单独一档，预算 = 自身单元格均值（≈7x 天品）。
  3. 【成长】叠加 (1 + 0.06 × (境界等级-1))，满级 +48%（随境界等级成长，不再是死数）。
  4. 【取舍】按强度降序，第 i 本生效系数 1/(1+0.15i) —— 学满的边际收益递减，
     「精选 3~5 本 + 搭配流派」优于「无脑全学」。
  5. 【expRate 收敛】按品级 黄0.10 / 玄0.16 / 地0.28 / 天0.45（原 0.1~1.0 且再乘品级系数），
     并在 bd() 内把「心法部分」封顶 1.25，保证服务端 settleSaveEconV2 的打坐配额永远够用。

总量影响（_numbal_calib.js 实测，学满可学集合 + 满级 + 递减后）：
    炼气 -26% / 筑基 -26% / 金丹 -27% / 元婴 -13% / 化神 +5% / 合道 -0% / 长生 -0%
  —— 前期小幅收紧，中后期与现状同量级，不改变既有战斗难度基准。

--------------------------------------------------------------------------
二、仙务新玩法数值（万宝洗炼 / 自创神通 / 通天塔扫荡）
--------------------------------------------------------------------------
  * 万宝洗炼：4 条「特殊词条」（会心/裂魄/幻影/噬灵）与 3 条「百分比词条」共用同一档位区间，
    仙品单条最高 0.22 → 单件 3 条 + 多件装备叠加，会心/闪避/吸血可轻易超过 60%，
    战斗层只能靠 .35/.25 硬顶，等于「洗出来就溢出」。改为特殊词条按 YlxwRF_SPECIAL 缩放
    （会心 ×0.35 / 裂魄 ×0.50 / 幻影 ×0.30 / 噬灵 ×0.25），百分比词条不变。
    同时把洗炼的灵石消耗上限 10000 → 40000、斜率 250 → 400（洗炼是灵石回收口，旧值太便宜）。
  * 自创神通：基础系数整体收敛（攻% 0.08→0.05、暴伤 0.15→0.09、减伤 0.05→0.03、
    吸血 0.03→0.02、闪避 0.04→0.025、身法 0.06→0.035），每重成长 1.12→1.06
    （旧值 1.12^9 = 2.77 倍，10 重神通攻% 可到 53%，5 门叠满 265%），
    并对「每门神通的词条值」与「战斗层总增益」双向封顶。
  * 通天塔每日扫荡：旧公式 (150*1.045^f + 50f) 与首通公式 (600*1.065^f + 500f) 完全脱钩，
    100 层扫荡只有首通累计的 6.8%，与「每日扫荡 35% 累计」的设计说明不符。
    改为**统一取首通曲线的 30%**，让扫荡随层数线性可信。

--------------------------------------------------------------------------
三、服务端经济钳制（settleSaveEconV2）核对
--------------------------------------------------------------------------
本次客户端改动中「调大产出」的只有：通天塔每日扫荡（修为/灵石）。
  扫荡修为（100 层）≈ Σ(600·1.065^f + 500f)·0.3 ≈ 2.34M，旧值 ≈ 533k（+1.81M）
  配额 = E2_TOWER_EXP_PER_MIN · mult · mins + E2_TOWER_EXP_LUMP = 20000·mult·mins + 12,000,000
    · 炼气档（mult=1）最短存盘间隔 mins=0.5 → 配额 12,010,000 > 单日扫荡上限 2.34M ✓
    · 长生境（mult=1.5^6=11.39）mins=0.5 → 配额 12,113,900 ✓
  灵石：扫荡灵石（100 层）≈ Σ(400·1.055^f + 300f)·0.3 ≈ 942k，由 capStone 的
    E2_LUMP_STONE_ALLOWANCE(1.2M) × ylScale 项覆盖（炼气 ylScale=1 → 1.2M）✓
  ⇒ 无需改服务端配额常量；但仍写进报告核对表，并保留 E2_TOWER_EXP_LUMP=12M 作为硬兜底。
"""

# ---------------------------------------------------------------------------
# 注入块：心法重规划执行器 + 洗炼/神通调参表
# 中文由 build 侧 zh() 统一转义；本块自身不含 fetch/localStorage 等禁用模式。
# ---------------------------------------------------------------------------
INJECT_JS = r'''
/* ===== yl-v28 数值重规划（心法重算 + 洗炼/神通调参）===== */
var YlxwArtW = { attack: 1, defense: 1.6, hp: 0.35, spirit: 2, speed: 1.8 };
var YlxwArtBudgetByCell = {
  "黄|炼气期": 17,
  "玄|炼气期": 73,
  "地|金丹期": 395,
  "天|元婴期": 3338,
  "天|化神期": 11134,
  "天|合道期": 10003,
  "天|长生境": 10003
};
var YlxwArtBudgetByGrade = { "黄": 17, "玄": 73, "地": 395, "天": 10003 };
/* 天地之魄（boss 掉落）单独成「格」——不再与同品级同境界的普通心法混在同一单元格里，
   否则会把 boss 本 ≈7x 的当量算进普通单元格的离散度（旧实现即因此产生 6.975x 假超限）。 */
var YlxwArtBossCell = "天地之魄";
/* boss 格预算 = 该格全部心法**原始**攻击当量的均值，由 YlxwArtBudgetCompute() 在
   模块加载时动态推导（旧实现把它写成一个与注释「预算 = 自身单元格均值」不符的魔数常量）。 */
var YlxwArtBossBudget = 0;
/* 运行时复算得到的「真实单元格均值」（不含 boss 格）；与设计表不一致时记入 Drift 并以设计表为准。 */
var YlxwArtBudgetLive = {};
var YlxwArtBudgetDrift = [];
var YlxwArtExpRate = { "黄": 0.10, "玄": 0.16, "地": 0.28, "天": 0.45 };
var YlxwArtDiminish = 0.15;
var YlxwArtLevelGrowth = 0.06;

/* 心法所属「数值单元格」：boss 掉落本单独成格，其余按 品级|境界需求 */
function YlxwArtCellOf(a) {
  if (!a) return "";
  if (a.isHeavenEarthSoulArt) return YlxwArtBossCell;
  return a.grade + "|" + a.realmRequirement;
}

/* 动态复算各单元格预算 = 该单元格内**全部**心法原始攻击当量的均值（四舍五入，含当量=0 的纯修速本）。
   必须在 YlxwArtBalance() 之前调用（此时 is[].effects 仍是原始值）。
   非 boss 格：设计表 YlxwArtBudgetByCell 为「文档基线」，动态值只用于校验（不一致 → Drift + 以基线为准，
   保证已上线数值零漂移）；设计表未覆盖的格用动态值兜底。boss 格：直接用动态均值。 */
function YlxwArtBudgetCompute() {
  var acc = {}, i, a, k, v, base;
  for (i = 0; i < is.length; i++) {
    a = is[i]; if (!a || !a.effects) continue;
    k = YlxwArtCellOf(a);
    if (!acc[k]) acc[k] = { n: 0, s: 0 };
    acc[k].n++; acc[k].s += YlxwArtValue(a);
  }
  for (k in acc) {
    v = Math.round(acc[k].s / acc[k].n);
    if (k === YlxwArtBossCell) {
      if (v > 0) YlxwArtBossBudget = v;
    } else {
      base = YlxwArtBudgetByCell[k];
      if (typeof base === "number" && base !== v) YlxwArtBudgetDrift.push(k + ":" + v + "!=" + base);
      YlxwArtBudgetLive[k] = (typeof base === "number") ? base : v;
    }
  }
  return YlxwArtBudgetLive;
}

function YlxwArtBudgetOf(a) {
  if (!a) return 0;
  if (a.isHeavenEarthSoulArt) return YlxwArtBossBudget;
  var v = YlxwArtBudgetLive[YlxwArtCellOf(a)];
  if (typeof v === "number") return v;
  v = YlxwArtBudgetByCell[YlxwArtCellOf(a)];
  if (typeof v === "number") return v;
  v = YlxwArtBudgetByGrade[a.grade];
  return typeof v === "number" ? v : 17;
}

/* 单元格离散自检（boss 单独成格）：{cell: {n, min, max, ratio}}，供运行时断言 ≤1.3x */
function YlxwArtCellReport() {
  var by = {}, i, a, k, v, out = {}, mn, mx;
  for (i = 0; i < is.length; i++) {
    a = is[i]; if (!a || !a.effects) continue;
    v = YlxwArtValue(a); if (!(v > 0)) continue;
    k = YlxwArtCellOf(a);
    (by[k] = by[k] || []).push(v);
  }
  for (k in by) {
    mn = Math.min.apply(null, by[k]); mx = Math.max.apply(null, by[k]);
    out[k] = { n: by[k].length, min: mn, max: mx, ratio: +(mx / mn).toFixed(3) };
  }
  return out;
}

function YlxwArtGate(a) {
  var m = 1;
  if (!a) return m;
  if (a.spiritualRoot) m *= 1.15;
  if (a.buildAffinity) m *= 1.10;
  if (a.sectId) m *= 1.15;
  return m;
}

/* 单本心法的「攻击当量总值」 */
function YlxwArtValue(a) {
  var e = (a && a.effects) || {}, v = 0, k;
  for (k in YlxwArtW) { if (e[k]) v += e[k] * YlxwArtW[k]; }
  return v;
}

/* 把一本心法的属性重算到「单元格均值 × 门槛系数」，保留原有侧重 */
function YlxwArtRebalance(a) {
  if (!a || !a.effects) return;
  var e = a.effects, stats = ["attack", "defense", "hp", "spirit", "speed"];
  var i, k, has = 0, wsum = 0, prof = {};
  for (i = 0; i < stats.length; i++) { if (e[stats[i]]) has = 1; }
  if (has) {
    var budget = YlxwArtBudgetOf(a) * YlxwArtGate(a);
    for (i = 0; i < stats.length; i++) {
      k = stats[i];
      prof[k] = (e[k] || 0) * YlxwArtW[k];
      wsum += prof[k];
    }
    if (wsum > 0) {
      for (i = 0; i < stats.length; i++) {
        k = stats[i];
        if (!e[k]) continue;
        e[k] = Math.max(1, Math.round(budget * (prof[k] / wsum) / YlxwArtW[k]));
      }
    }
  }
  if (e.expRate) {
    var er = YlxwArtExpRate[a.grade];
    e.expRate = typeof er === "number" ? er : 0.10;
  }
}

function YlxwArtBalance() {
  try {
    /* 先按「原始当量」复算各单元格预算（boss 格预算在此动态推导），再执行重算改写 effects。
       顺序不可颠倒：一旦 effects 被改写，均值就不复存在。 */
    YlxwArtBudgetCompute();
    for (var i = 0; i < is.length; i++) { YlxwArtRebalance(is[i]); }
  } catch (e) { /* 数值重算失败绝不阻断启动 */ }
}
YlxwArtBalance();

/* 玩家境界等级成长：满级(9) +48% */
function YlxwArtGrowth(p) {
  var lv = Math.max(1, Math.min(9, Math.floor(Number(p && p.realmLevel) || 1)));
  return 1 + YlxwArtLevelGrowth * (lv - 1);
}

/* 已学心法按强度降序（递减系数按此顺序施加） */
function YlxwArtRanked(p) {
  var ids = (p && p.cultivationArts) || [], out = [], i, a;
  for (i = 0; i < ids.length; i++) {
    a = null;
    try { a = is.find(function (x) { return x.id === ids[i]; }); } catch (e) { a = null; }
    out.push({ id: ids[i], v: a ? YlxwArtValue(a) : 0 });
  }
  out.sort(function (x, y) { return y.v - x.v; });
  return out.map(function (o) { return o.id; });
}

/* 第 i 本（0 起）的生效系数 */
function YlxwArtFactor(i) { return 1 / (1 + YlxwArtDiminish * (i || 0)); }

/* 属性面板累加器（供展示侧与结算侧共用同一套系数）。
   ★ 累加口径 = Cg()/xt() 的**应用口径**（6 项，含 physique），不是 YlxwArtW 的「攻击当量」权重口径（5 项）。
   旧实现直接 `for (k in YlxwArtW)` → 漏掉 physique，使属性明细面板「功法」通道的心法体魄加成凭空消失
   （补丁前的原代码显式累加过 X.physique+=ue.effects.physique||0，属本补丁引入的回归）。 */
var YlxwArtStats = ["attack", "defense", "hp", "spirit", "physique", "speed"];
function YlxwArtAdd(acc, e, f) {
  if (!acc || !e) return;
  for (var i = 0; i < YlxwArtStats.length; i++) {
    var k = YlxwArtStats[i];
    if (e[k]) acc[k] = (acc[k] || 0) + Math.floor(e[k] * f);
  }
}

/* ---- 万宝洗炼：4 条特殊词条缩放（百分比词条不缩放）---- */
var YlxwRF_SPECIAL = { critRate: 0.35, critDamage: 0.5, dodgeRate: 0.3, lifeLeech: 0.25 };

/* ---- 自创神通：词条值封顶 + 战斗层总增益封顶 ---- */
var YlxwSP_CAP = {
  attackPercent: 0.30, speedPercent: 0.20, critRate: 0.15, critDamage: 0.50,
  damageReduction: 0.20, lifeLeech: 0.10, dodgeRate: 0.15
};
function YlxwSP_CapEffects(ef) {
  var o = {}, k;
  if (!ef) return o;
  for (k in ef) {
    if (typeof ef[k] !== "number") { o[k] = ef[k]; continue; }
    var cap = YlxwSP_CAP[k];
    o[k] = (typeof cap === "number") ? Math.min(cap, Number(ef[k].toFixed(3))) : ef[k];
  }
  return o;
}
/* R-141 稀有属性封顶 ≤80%：用户要求「稀有属性整体数值不能太多，就算装备满配也不能超过 80%」。
   4 类稀有键 critRate/critDamage/dodgeRate/lifeLeech 中仅 critDamage 原为 1.0(100%) 超 80% ⇒ 收到 0.8；
   critRate 0.35 / dodgeRate 0.35 / lifeLeech 0.25 本就 ≤80% ⇒ 保持；damageReduction 不属这 4 类稀有属性，保持 0.5。 */
var YlxwBattleCapCfg = { critRate: 0.35, critDamage: 0.8, dodgeRate: 0.35, lifeLeech: 0.25, damageReduction: 0.5 };
function YlxwBattleCap(o) {
  var k;
  for (k in YlxwBattleCapCfg) { if (o[k] > YlxwBattleCapCfg[k]) o[k] = YlxwBattleCapCfg[k]; }
  return o;
}
/* == end YL_NUMBAL_V28 == */
'''

# build 侧插入约定：本模块的 apply() 只做 PATCHES，INJECT_JS 由 build 侧在下面锚点前插入
# （与 _test_numbal.py 的验证顺序一致：先注入块，再 apply）。
INJECT_BLOCK_ID = 'numbal-block'
INJECT_BEFORE_ANCHOR = 'function YlxwPanelModal(p) {'

# ---------------------------------------------------------------------------
# 客户端补丁表：(name, old, new, expect, note)
# 锚点全部为 ASCII，且先在「主注入块已应用」的文本上实测 count。
# ---------------------------------------------------------------------------
PATCHES = [
    # ---------------- 心法：结算侧 ----------------
    (
        '心法·属性结算(成长+递减)',
        't.cultivationArts.forEach(E=>{const N=is.find(k=>k.id===E);if(N){const k=go(N,f);',
        'YlxwArtRanked(t).forEach((E,YAq)=>{const N=is.find(k=>k.id===E);if(N){const k=go(N,f)*YlxwArtGrowth(t)*YlxwArtFactor(YAq);',
        1,
        '心法属性：全量线性叠加 → 按强度降序递减(1/(1+0.15i)) + 境界等级成长(满级+48%)',
    ),
    # ---------------- 心法：属性面板展示侧（与结算同系数）----------------
    (
        '心法·属性面板对齐',
        'a.cultivationArts.forEach(Ie=>{const ue=is.find(ie=>ie.id===Ie);ue&&(X.attack+=ue.effects.attack||0,X.defense+=ue.effects.defense||0,X.hp+=ue.effects.hp||0,X.spirit+=ue.effects.spirit||0,X.physique+=ue.effects.physique||0,X.speed+=ue.effects.speed||0)',
        'YlxwArtRanked(a).forEach((Ie,YAq)=>{const ue=is.find(ie=>ie.id===Ie);ue&&YlxwArtAdd(X,ue.effects,YlxwArtGrowth(a)*YlxwArtFactor(YAq))',
        1,
        '属性面板心法加成与结算侧同系数（旧面板显示的是未递减的原始和，会与实战不符）',
    ),
    # ---------------- 心法：修炼速度（expRate）----------------
    (
        '心法·修炼速度封顶',
        'r=u.effects.expRate*$;',
        'r=Math.min(1.25,u.effects.expRate*$);',
        1,
        '心法 expRate 有效值封顶 1.25（保证服务端 settleSaveEconV2 打坐配额 medEach=medBase*3.7 永远够用）',
    ),
    # ---------------- 万宝洗炼 ----------------
    (
        '洗炼·特殊词条缩放',
        'var raw = cfg.minV + Math.random() * (cfg.maxV - cfg.minV);',
        'var raw = (cfg.minV + Math.random() * (cfg.maxV - cfg.minV)) * (YlxwRF_SPECIAL[ty] || 1);',
        1,
        '会心/裂魄/幻影/噬灵 4 条特殊词条按 YlxwRF_SPECIAL 缩放（仙品单条 0.22 → 会心 0.077/裂魄 0.11/幻影 0.066/噬灵 0.055），百分比词条不变',
    ),
    (
        '洗炼·灵石消耗抬高',
        'var bsp = 500 + Math.min(10000, count * 250);',
        'var bsp = 500 + Math.min(40000, count * 400);',
        1,
        '洗炼灵石消耗：上限 10000→40000、斜率 250→400（洗炼是灵石回收口，旧值相对打坐收益过便宜）',
    ),
    # ---------------- 自创神通 ----------------
    (
        '神通·基础系数(攻%·非攻源)',
        'ef.attackPercent = Number((0.05 * avg).toFixed(3));',
        'ef.attackPercent = Number((0.03 * avg).toFixed(3));',
        1,
        '神通融合 攻%(无攻击源分支) 0.05→0.03（必须先于 0.08→0.05，否则锚点由 1 处变 2 处）',
    ),
    (
        '神通·基础系数(攻%)',
        'ef.attackPercent = Number((0.08 * avg).toFixed(3));',
        'ef.attackPercent = Number((0.05 * avg).toFixed(3));',
        1,
        '神通融合 攻% 系数 0.08→0.05（天+天 avg=2.4：0.192→0.120）',
    ),
    (
        '神通·基础系数(会心)',
        'ef.critRate = Number((0.04 * avg).toFixed(3));',
        'ef.critRate = Number((0.025 * avg).toFixed(3));',
        1,
        '神通融合 会心 0.04→0.025',
    ),
    (
        '神通·基础系数(减伤)',
        'ef.damageReduction = Number((0.05 * avg).toFixed(3));',
        'ef.damageReduction = Number((0.03 * avg).toFixed(3));',
        1,
        '神通融合 减伤 0.05→0.03',
    ),
    (
        '神通·基础系数(噬灵)',
        'ef.lifeLeech = Number((0.03 * avg).toFixed(3));',
        'ef.lifeLeech = Number((0.02 * avg).toFixed(3));',
        1,
        '神通融合 噬灵 0.03→0.02',
    ),
    (
        '神通·基础系数(幻影)',
        'ef.dodgeRate = Number((0.04 * avg).toFixed(3));',
        'ef.dodgeRate = Number((0.025 * avg).toFixed(3));',
        1,
        '神通融合 幻影 0.04→0.025',
    ),
    (
        '神通·基础系数(身法)',
        'ef.speedPercent = Number((0.06 * avg).toFixed(3));',
        'ef.speedPercent = Number((0.035 * avg).toFixed(3));',
        1,
        '神通融合 身法% 0.06→0.035',
    ),
    (
        '神通·基础系数(裂魄)',
        'ef.critDamage = Number((0.15 * avg).toFixed(3));',
        'ef.critDamage = Number((0.09 * avg).toFixed(3));',
        1,
        '神通融合 裂魄 0.15→0.09',
    ),
    (
        '神通·每重成长',
        'ne[k] = Number((t.effects[k] * 1.12).toFixed(3));',
        'ne[k] = Number((t.effects[k] * 1.06).toFixed(3));',
        1,
        '神通参悟每重成长 1.12→1.06（旧值 10 重 ×2.77 倍，5 门叠满攻% 可到 265%）',
    ),
    (
        '神通·融合产物封顶',
        'effects: YlxwSP_FuseEffects(a1, a2),',
        'effects: YlxwSP_CapEffects(YlxwSP_FuseEffects(a1, a2)),',
        1,
        '新神通词条按 YlxwSP_CAP 逐项封顶',
    ),
    (
        '神通·升级产物封顶',
        'var ns = sp.slice();\n  ns[idx] = Object.assign({}, t, { level: t.level + 1, effects: ne });',
        'var ns = sp.slice();\n  ne = YlxwSP_CapEffects(ne);\n  ns[idx] = Object.assign({}, t, { level: t.level + 1, effects: ne });',
        1,
        '升级后同样逐项封顶（防止 1.06^9 累积越界）',
    ),
    (
        '神通·属性层攻速%封顶',
        '  var sp = p.customSpells || [], e2;\n  for (i = 0; i < sp.length; i++) {\n    e2 = (sp[i] && sp[i].effects) || {};\n    if (e2.attackPercent) r.attack += Math.floor(p.attack * e2.attackPercent);\n    if (e2.speedPercent) r.speed += Math.floor(p.speed * e2.speedPercent);\n  }',
        '  var sp = p.customSpells || [], e2, YAsumA = 0, YAsumS = 0;\n  for (i = 0; i < sp.length; i++) {\n    e2 = (sp[i] && sp[i].effects) || {};\n    if (e2.attackPercent) YAsumA += e2.attackPercent;\n    if (e2.speedPercent) YAsumS += e2.speedPercent;\n  }\n  r.attack += Math.floor(p.attack * Math.min(0.6, YAsumA));\n  r.speed += Math.floor(p.speed * Math.min(0.4, YAsumS));',
        1,
        '多门神通攻%/身法% 先求和再封顶（攻% ≤60%、身法% ≤40%）',
    ),
    (
        '神通·战斗层增益封顶',
        '    if (e2.lifeLeech) o.lifeLeech += e2.lifeLeech;\n    if (e2.damageReduction) o.damageReduction += e2.damageReduction;\n  }\n  return o;\n}',
        '    if (e2.lifeLeech) o.lifeLeech += e2.lifeLeech;\n    if (e2.damageReduction) o.damageReduction += e2.damageReduction;\n  }\n  return YlxwBattleCap(o);\n}',
        1,
        '洗炼+神通战斗增益总封顶（会心35%/暴伤80%/闪避35%/噬灵25%/减伤50%）',
    ),
    # ---------------- 通天塔每日扫荡 ----------------
    (
        '通天塔·扫荡修为对齐首通30%',
        'e += Math.floor(150 * Math.pow(1.045, f) + f * 50);',
        'e += Math.floor((600 * Math.pow(1.065, f) + f * 500) * 0.3);',
        1,
        '扫荡修为公式与首通脱钩(旧≈首通累计6.8%) → 统一取首通曲线30%',
    ),
    (
        '通天塔·扫荡灵石对齐首通30%',
        's += Math.floor(100 * Math.pow(1.04, f) + f * 35);',
        's += Math.floor((400 * Math.pow(1.055, f) + f * 300) * 0.3);',
        1,
        '扫荡灵石公式同上对齐',
    ),
]

# ---------------------------------------------------------------------------
# 门禁：(name, needle, expect, cmp, note)
# ---------------------------------------------------------------------------
GATES = [
    ('numbal·心法重算执行器',      'function YlxwArtBalance()',              1, '==', ''),
    ('numbal·心法预算表',          'YlxwArtBudgetByCell',                    2, '>=', '定义+引用'),
    ('numbal·洗炼特殊缩放表',      'YlxwRF_SPECIAL',                         2, '>=', ''),
    ('numbal·神通封顶表',          'YlxwSP_CapEffects',                      3, '>=', '定义+融合+升级'),
    ('numbal·战斗封顶表',          'YlxwBattleCap(',                         2, '>=', ''),
    ('numbal·结算侧已递减',        'YlxwArtFactor(YAq)',                     2, '==', '结算+面板'),
    ('numbal·旧全量叠加已移除(结算)', 't.cultivationArts.forEach(E=>{const N=is.find', 0, '==', '必须为 0'),
    ('numbal·旧全量叠加已移除(面板)', 'a.cultivationArts.forEach(Ie=>{const ue=is.find', 0, '==', '必须为 0'),
    ('numbal·expRate 已封顶',      'r=Math.min(1.25,u.effects.expRate*$);',  1, '==', ''),
    ('numbal·洗炼词条已缩放',      '(YlxwRF_SPECIAL[ty] || 1)',              1, '==', ''),
    ('numbal·洗炼消耗已抬高',      'Math.min(40000, count * 400)',           1, '==', ''),
    ('numbal·神通成长已收敛',      't.effects[k] * 1.06',                    1, '==', ''),
    ('numbal·扫荡修为已对齐',      '(600 * Math.pow(1.065, f) + f * 500) * 0.3', 1, '==', ''),
    ('numbal·扫荡灵石已对齐',      '(400 * Math.pow(1.055, f) + f * 300) * 0.3', 1, '==', ''),
    # ---- P2-⑩：boss 本单独成格 + 预算改为「自身单元格均值」动态推导 ----
    ('numbal·单元格划分已显式化',  'function YlxwArtCellOf(a)',              1, '==', 'boss 本返回「天地之魄」独立格键'),
    ('numbal·单元格划分被引用',    'YlxwArtCellOf(a)',                       4, '>=', '划分+预算查找+离散自检'),
    ('numbal·boss 格键已定义',     'var YlxwArtBossCell =',                  1, '==', 'boss 本独立格键（值含中文，只断言 ASCII 前缀）'),
    ('numbal·预算均值动态复算',    'function YlxwArtBudgetCompute()',        1, '==', ''),
    ('numbal·动态复算已执行',      'YlxwArtBudgetCompute();',                1, '==', '必须早于 YlxwArtBalance'),
    ('numbal·离散自检已提供',      'function YlxwArtCellReport()',           1, '==', ''),
    ('numbal·旧硬编码 boss 预算已清零', 'var YlxwArtBossBudget = 77650;',     0, '==', '必须为 0（改为运行时动态推导）'),
    ('numbal·boss 预算不再为字面量',   'YlxwArtBossBudget = 77650',           0, '==', '必须为 0'),
    ('numbal·boss 预算初值 0 待推导',  'var YlxwArtBossBudget = 0;',          1, '==', ''),
    # ---- P2-⑧：属性累加口径必须覆盖 physique（= Cg()/xt() 的 6 项应用口径）----
    ('numbal·累加口径含 physique',  'var YlxwArtStats = ["attack", "defense", "hp", "spirit", "physique", "speed"];', 1, '==', ''),
    ('numbal·累加器已用 6 项口径',  'YlxwArtStats.length',                   1, '==', ''),
    ('numbal·旧 5 项累加器已清零',  'for (k in YlxwArtW) { if (e[k]) acc[k] = (acc[k] || 0) + Math.floor(e[k] * f); }', 0, '==', '必须为 0（会漏 physique）'),
    # ---- 反回归：不得破坏他人区域 ----
    ('numbal·未动通天塔首通公式',  'var expReward = Math.floor(600 * Math.pow(1.065, sf) + sf * 500);', 1, '==', ''),
    ('numbal·未动远征灵石缩放',    'Math.floor(stones * rf)',                1, '==', ''),
    ('numbal·未动洗炼词条区间表',  'YlxwRF_RARITY',                          2, '>=', ''),
    ('numbal·未动神通槽位表',      'YlxwSP_CFG.slots[realm]',                1, '==', ''),
]


def apply(p, ctx):
    """p = Patcher（文本已含全部主注入块）；ctx = {'zh': zh, 'base_text': str}"""
    for name, old, new, expect, note in PATCHES:
        p.replace(name, old, new, expect=expect, note=note)
    return list(GATES)
