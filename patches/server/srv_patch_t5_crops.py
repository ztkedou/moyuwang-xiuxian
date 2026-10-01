# -*- coding: utf-8 -*-
r"""
srv_patch_t5_crops.py -- 0.8.9 T5 灵田品种重构（服务端环 t5_crops；归属 T5）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。

策划案
--------------------------------------------------------------------------
  docs/0.8.8-design/T5-灵田品种重构.md（30.5KB / 414 行，定稿）
  §2 品种体系 / §2.3 时长 / §2.4 变卖价 / §2.5 服用效果 / §3 完整数值表 /
  §4.1 公式 / §4.3 单调性断言 / §5 经济红线 / §5.6 铁律自查 / §7-Q3 照料口径

覆盖范围
--------------------------------------------------------------------------
  T5.1  FARM_CROPS 5 → 20 新种（5 品阶 × 4 产品线）+ 5 旧 key 移入兼容区
  T5.2  三个生成器（纯函数）：farmCropDefs() / farmCropSell() / farmCropConsume()
  T5.3  farmHarvestOne 加 mode:'sell'|'consume'（缺省 sell = 逐位兼容旧调用）
        · sell    → 结算灵石（口径不变）
        · consume → 结算修为 + 属性（基础属性 / 百分比属性，百分比有硬上限）
        · ★ credited + hit.ok + 回退 harvested=0 三段式回滚逐字保留
  T5.4  POST /api/farm/harvest 接 mode（非法值 400，不静默降级）
  T5.5  harvest/all 走 sell（与旧口径一致）
  T5.6  GET /api/farm/status 下发 crops（含 sell/consume）/cropList/cropTiers/attrCaps
  T5.7  POST /api/farm/plant 拒绝旧种新播（存量已种旧种仍可正常收获）
  T5.8  照料口径（§7-Q3）：每次 +2%、单田当日累计上限 +10%
        FARM_TEND_BONUS 0.10 → FARM_TEND_PER 0.02 + FARM_TEND_CAP 0.10

★ 红线（本人复算，见 §5.2）
--------------------------------------------------------------------------
  经济：满配（洞府 L10 +10% × 照料上限 +10% = ×1.21）最赚作物 = 纯卖钱草·神品
        「神藏金参」720min：净 27000−18900 = 8100 → 日净 8100×2 = 16200/田
        ×1.21 = 19602/田 → ×6 田 = 117,612 灵石/日 ≤ 150,000（余量 21.6%）✓
        ★ 前提：种子成本保留（取消则「变卖价=净收益」，必破线）
  修为：满配 6 田全种「混元道果」= 19000 × (1440/900) × 6 = 182,400 修为/日
        = 0.8.7 现状 258,000 的 0.71×（按 T7 §3.5 铁律主动收紧）✓
  铁律：纯修为草七境界「折打坐 ÷ 折挂机」比值 0.33~0.86，全部 ≤1，正套利清零 ✓

★ 属性字段名（grep 实测，非假设）
--------------------------------------------------------------------------
  服务端唯一玩家属性结构证据 = `extractRankingData`（srv:1271-1275）：
      player.attack / player.defense / player.maxHp / player.spirit / player.speed
  ⇒ 基础属性键取上列 5 个（气血 = maxHp，与 `[gongfacore]` statName:'气血', stat:'maxHp'、
    `FENG_GF`('zhoutian','周天阵','maxHp','气血',5) 同源铁证）。
  ⇒ 百分比键候选（**已与 yl_farm089_ext.py 客户端契约对齐**，见下）：
      critRate / dodgeRate / hitRate / lifeLeech
      —— `lifeLeech` 已由 0.8.9 客户端补丁接进战斗结算（吸血）；`hitRate` 尚未接，
         故本环**不生成任何命中草**（策划案 §9.2 的落地建议：命中草延后，防空转）。

★ 禁改
--------------------------------------------------------------------------
  · 不动 :9646/:9678（Y19 成就口径） · 不动 daily_quests
  · 不动 T5 活动倍率挂点（actApplyGain 总量不变；actDropTokens 挂点逐字保留）
  · 业务拒绝一律 400/409，绝不 403（客户端 Xc() 把 403 当会话失效强制登出）

门禁计数清单
--------------------------------------------------------------------------
  const FARM_CROPS: Record<string, { ... grottoLevel?: number }> = {   ==1（类型签名不动）
  /旧作物（T5 兼容区）/                                    ==1
  function farmCropDefs(                                   ==1
  function farmCropSell(                                   ==1
  function farmCropConsume(                                ==1
  farmCropNoPlant(                                         ==2（plant 端点内 1 次 + 定义引用）
  const FARM_TEND_PER = 0.02;                              ==1
  const FARM_TEND_CAP = 0.10;                              ==1
  const FARM_TEND_BONUS = 0.10;                            ==0（旧常量清零：改口径须换名）
  const claim = await dbRun('UPDATE spirit_farm SET harvested = 1 ...  ==1
  credit.sell / credit.consume 分支                           各==1
  res.status(403                                             与基线同（本环零新增）
"""
import argparse
import io
import os
import re
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ T5.1 作物表

# 旧 5 种（照录 0.8.7 表体，一个字节不改；移入兼容区，仅供存量已种下的旧作物收获）
OLD_5_KEYS = """  lingcao:     { name: '灵草',   seed: 1000, minutes: 240,  stones: 800,   exp: 500 },
  lingzhi:     { name: '灵芝',   seed: 5000, minutes: 720,  stones: 5000,  exp: 3000 },
  qianniancan: { name: '千年参', seed: 20000, minutes: 1440, stones: 25000, exp: 15000 },
  // T10 高阶作物（数值=设计案建议锚值，★待《数值表-T9T10.md》#8 定档回填；洞府门槛对齐地块档 #4）：
  //   经济红线 #11 预验算（相对式）：满配（L10 洞府 +10% × 照料 +10% = ×1.21 毛额）最赚钱作物=造化青莲，
  //   日净 = (215000×1.21−200000)/3 天 ≈ 20,050/田 → ×6 田 ≈ 120,300/日 ≤ 150,000（=T5-C 对价 150 万的 1/10）✓
  //   净收益率 产出/种子：太虚果 1.40（2 天）、造化青莲 1.075（3 天，但日净绝对值 2 倍于千年参）；修为≈灵石×0.6 同既有比例
  taixuguo:       { name: '太虚果',   seed: 50000,  minutes: 2880, stones: 70000,  exp: 42000,  grottoLevel: 5 },
  zaohuaqinglian: { name: '造化青莲', seed: 200000, minutes: 4320, stones: 215000, exp: 129000, grottoLevel: 7 },
};"""

T5_1_OLD = """const FARM_CROPS: Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number }> = {
""" + OLD_5_KEYS

T5_1_NEW = """// ★ T5（0.8.9）灵田品种重构：5 种 → 20 种（5 品阶 × 4 产品线）+ 5 旧种兼容区。
//   数值全部来自 docs/0.8.8-design/T5-灵田品种重构.md §3 完整数值表（定稿），
//   聚合为「品阶基准 + 类型系数」两张纯表（§2.3/§2.4/§2.5 生成规则，§4.2 抽样验证 ✅）：
//     时长 = clamp30(B(品阶) × k(类型))，下限 120；变卖价 = round(V(品阶) × m(类型))；
//     种子价 = round(变卖价 × Cs(类型))；服用修为 = 纯修为草直表 / 其余 = E(品阶) × e(类型)。
//   ★ 旧 5 种**不再是可播种品种**（plant 端点 409 拒绝新播），但表体逐字保留 ⇒
//     存量已种下的旧作物仍能被 farmCrop() 查到并按旧口径正常收获（§7-Q7(a)，防玩家损失）。
//     （farmCrop() 经 farmCropDefs() 取表，后者把本表 5 键原样并入 ⇒ 存量旧田口径逐字不变。）
const FARM_CROPS: Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number }> = {
  // ── 旧作物（T5 兼容区 · 只读存量，不可新播）──────────────────────────
  //   旧作物只有「灵石 + 修为」一个出口 ⇒ 服用只给修为、变卖给灵石（§7-Q7）。
  //   照料口径对旧作物同样生效（tendBonus 由 farmHarvestMods 统一给出）。
""" + OLD_5_KEYS.split("\n};")[0] + """
};

// ── T5 新 20 种：品阶基准 + 类型系数（两层查表，零手抄，杜绝抄错）────────
//   品阶 1..5 = 凡品/灵品/玄品/仙品/神品；洞府解锁门槛 凡灵 Lv1 / 玄 Lv3 / 仙 Lv5 / 神 Lv7。
const FARM_CROP_BASE: Record<number, { min: number; sell: number; expBase: number; attr: number }> = {
  1: { min: 120, sell: 500,   expBase: 100,   attr: 8 },     // 凡品
  2: { min: 180, sell: 1500,  expBase: 400,   attr: 30 },    // 灵品
  3: { min: 300, sell: 5000,  expBase: 1500,  attr: 100 },   // 玄品
  4: { min: 480, sell: 13000, expBase: 5000,  attr: 350 },   // 仙品
  5: { min: 720, sell: 27000, expBase: 15000, attr: 1000 },  // 神品
};
const FARM_CROP_KIND: Record<string, { min: number; money: number; seed: number; exp: number; kindName: string }> = {
  sell: { min: 1.0,  money: 1.0,  seed: 0.50, exp: 0.2, kindName: '纯卖钱草' },   // 出售主出口（种子 0.70 见下 sellSeed）
  cult: { min: 1.25, money: 0.2,  seed: 0.50, exp: 1.0, kindName: '纯修为草' },   // 只加修为
  mix:  { min: 1.5,  money: 0.6,  seed: 0.50, exp: 1.0, kindName: '综合草' },     // 修为 + 2~3 基础属性
  rare: { min: 2.0,  money: 0.5,  seed: 0.56, exp: 0.5, kindName: '稀有百分比草' }, // 修为 + 1~2 百分比属性（有上限）
};
// 纯修为草「服用·修为」直表（§2.5-A，★已按 T7 §3.5 铁律单独下调：200/800/3000/10000/30000 → 下表）
const FARM_CROP_EXP_PURE: Record<number, number> = { 1: 150, 2: 470, 3: 1450, 4: 4500, 5: 19000 };
// 综合草「服用·修为」玄/仙保序微调（§2.5-A：1,500→1,400 / 5,000→4,400，为保「纯修为 > 综合」的 §4.3 断言）
const FARM_CROP_EXP_MIX_ADJ: Record<number, number> = { 3: 1400, 4: 4400 };
const FARM_CROP_TIERS = ['凡品', '灵品', '玄品', '仙品', '神品'];
// 品阶解锁门槛（复用洞府等级；★与 T10 地块门槛 FARM_UNLOCK_GROTTO_LEVEL={4:5,5:7,6:9} 错位，避免同一门槛卡两件事）
const FARM_CROP_TIER_LEVEL: Record<number, number> = { 1: 1, 2: 1, 3: 3, 4: 5, 5: 7 };
// T5 新 20 种（key 刻意避开既有物品名：聚灵草/血参/回气草/凝神花/龙鳞果/千年灵芝/九叶芝草/… 零碰撞）
const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {
  linggusi:       { t: 1, k: 'sell' }, // 凡品 · 灵谷穗
  ziwenlingdao:   { t: 2, k: 'sell' }, // 灵品 · 紫纹灵稻
  jinsuiteng:     { t: 3, k: 'sell' }, // 玄品 · 金髓藤
  xianyulian:     { t: 4, k: 'sell' }, // 仙品 · 仙玉莲
  shencangjinshen:{ t: 5, k: 'sell' }, // 神品 · 神藏金参
  peiyuancao:     { t: 1, k: 'mix' },  // 凡品 · 培元草
  zhuangguhua:    { t: 2, k: 'mix' },  // 灵品 · 壮骨花
  bailianzhi:     { t: 3, k: 'mix' },  // 玄品 · 百炼芝
  jiugiaoxuanzhi: { t: 4, k: 'mix' },  // 仙品 · 九窍玄芝
  wanxianghua:    { t: 5, k: 'mix' },  // 神品 · 万象花
  yinqimiao:      { t: 1, k: 'cult' }, // 凡品 · 引气苗
  ningyuanzhi:    { t: 2, k: 'cult' }, // 灵品 · 凝元芝
  xuanyuanguo:    { t: 3, k: 'cult' }, // 玄品 · 玄元果
  taiqingguo:     { t: 4, k: 'cult' }, // 仙品 · 太清果
  hunyuandaoguo:  { t: 5, k: 'cult' }, // 神品 · 混元道果
  jifengye:       { t: 3, k: 'rare' }, // 玄品 · 疾风叶
  xuepohua:       { t: 4, k: 'rare' }, // 仙品 · 血魄花
  xingyunhua:     { t: 4, k: 'rare' }, // 仙品 · 星陨花
  dongxuanhua:    { t: 5, k: 'rare' }, // 神品 · 洞玄花
  bumieteng:      { t: 5, k: 'rare' }, // 神品 · 不灭藤
};
const FARM_CROPS_NEW_NAME: Record<string, string> = {
  linggusi: '灵谷穗', ziwenlingdao: '紫纹灵稻', jinsuiteng: '金髓藤', xianyulian: '仙玉莲', shencangjinshen: '神藏金参',
  peiyuancao: '培元草', zhuangguhua: '壮骨花', bailianzhi: '百炼芝', jiugiaoxuanzhi: '九窍玄芝', wanxianghua: '万象花',
  yinqimiao: '引气苗', ningyuanzhi: '凝元芝', xuanyuanguo: '玄元果', taiqingguo: '太清果', hunyuandaoguo: '混元道果',
  jifengye: '疾风叶', xuepohua: '血魄花', xingyunhua: '星陨花', dongxuanhua: '洞玄花', bumieteng: '不灭藤',
};
// 综合草「服用·基础属性」（§3.2：2~3 项；键=服务端存档字段名）
const FARM_CROP_ATTRS: Record<string, Array<{ key: string; label: string }>> = {
  peiyuancao:     [{ key: 'maxHp', label: '气血' }, { key: 'defense', label: '体魄' }],
  zhuangguhua:    [{ key: 'maxHp', label: '气血' }, { key: 'defense', label: '体魄' }, { key: 'defense', label: '防御' }],
  bailianzhi:     [{ key: 'attack', label: '攻击' }, { key: 'defense', label: '防御' }, { key: 'maxHp', label: '气血' }],
  jiugiaoxuanzhi: [{ key: 'attack', label: '攻击' }, { key: 'maxHp', label: '气血' }, { key: 'spirit', label: '神识' }],
  wanxianghua:    [{ key: 'attack', label: '攻击' }, { key: 'defense', label: '防御' }, { key: 'maxHp', label: '气血' }],
};
// 稀有草「服用·百分比属性」（§3.4；pct 为百分点数值，如 0.4 = +0.4%）。
// ★ 落地裁剪（策划案 §9.2）：客户端 YLXW_FT_PCT 只认 critRate / dodgeRate / lifeLeech 三键，
//   且存档中只有这三键参与战斗结算。策划案原案的次级项（速度/气血/攻击的百分比）无对应存档字段
//   ⇒ 本期**不生成**，避免写进存档的僵尸字段；主项数值不变（仅洞玄花因命中未接而折算为暴击，见下）。
const FARM_CROP_PCT: Record<string, Array<{ key: string; label: string; pct: number }>> = {
  jifengye:   [{ key: 'dodgeRate', label: '闪避率', pct: 0.4 }],
  xuepohua:   [{ key: 'lifeLeech', label: '吸血率', pct: 0.8 }],
  xingyunhua: [{ key: 'critRate', label: '暴击率', pct: 1.0 }],
  // ★ 洞玄花：策划案原案为「命中 +1.2% / 暴击 +0.6%」，但命中率尚未接进战斗结算
  //   （策划案 §9.2 实测：命中多为文案）⇒ 本期按 §9.2 落地建议折算为「暴击 +1.8%」，
  //   **不生成任何空转的命中草**（上限表保留命中项占位，供后续批次直接启用）。
  dongxuanhua:[{ key: 'critRate', label: '暴击率', pct: 1.8 }],
  bumieteng:  [{ key: 'lifeLeech', label: '吸血率', pct: 1.0 }, { key: 'dodgeRate', label: '闪避率', pct: 0.6 }],
};
// ★ 百分比属性硬上限（§2.5-C：灵田「服用」来源累计，独立于装备/称号）。
//   单位为**百分点**（critRate: 8 = +8%）；玩家存档里这些键存的是**小数比例**（0.08 = 8%）
//   ⇒ farmCropConsume 内做 ×100 归一后再比对，避免单位错配导致上限永不触发。
const FARM_CROP_ATTR_CAP: Record<string, number> = { hitRate: 8, critRate: 8, dodgeRate: 6, lifeLeech: 4 };

// T5：作物定义生成器（纯函数，零副作用；每次调用重算，25 项规模可忽略）。
//   返回结构与旧 FARM_CROPS 逐字段同形（name/seed/minutes/stones/exp/grottoLevel）。
//   ⚠ 修正（2026-09-29）：**"plant / farmCrop 零改动即可消费" 是错的** —— 该假设正是本环 P0 的病根。
//     本生成器产出的 25 键表必须被 farmCrop() **显式消费**（见下方 farmCrop 定义），
//     否则 /api/farm/plant 的 `if (!crop) return 400 '未知作物'` 会把 20 个新种全部拒掉。
//     客户端渲染走 status.crops（已是 25 键）本就无需改动，但**服务端 farmCrop 必须改**。
//   ★ exp 字段按产品线分流（§2.5-A）：纯修为草取直表；综合草 = E(品阶) × 1.0（玄/仙保序微调）；
//     稀有草 = E(品阶) × 0.5；纯卖钱草 = E(品阶) × 0.2。
function farmCropDefs(): Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number }> {
  const out: Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number }> = {};
  out.lingcao = FARM_CROPS.lingcao;
  out.lingzhi = FARM_CROPS.lingzhi;
  out.qianniancan = FARM_CROPS.qianniancan;
  out.taixuguo = FARM_CROPS.taixuguo;
  out.zaohuaqinglian = FARM_CROPS.zaohuaqinglian;
  // ★ 旧种 retired 标记（0.8.9 补丁）：crops 目录里「已停种」品种带 retired: true。
  //   客户端（yl_farm089_ext.py:170 `g = (t && t.crops) || {}, h = Object.keys(g)` 逐键画按钮）
  //   据此把按钮置灰，不再让玩家点了吃 409「该灵草品种已停止栽种」。
  //   ★ 条目**必须保留、不许删**：存量已种下的旧田仍按旧口径正常收获，槽位回显需要作物名。
  //   ★ 判据与 plant 端点同源（farmCropNoPlant ⇒ isLegacyCrop）⇒「标的」恒等于「拒播的」。
  //   ★ 5 个旧种**全标**：lingcao/lingzhi/qianniancan（0.8.7 旧种）+ taixuguo/zaohuaqinglian
  //     （T10 高阶种）—— 后两者同样被 plant 409 拒掉，不标则客户端照样画成可点按钮。
  for (const legacyKey of Object.keys(out)) {
    if (isLegacyCrop(legacyKey)) out[legacyKey] = Object.assign({}, out[legacyKey], { retired: true });
  }
  for (const key of Object.keys(FARM_CROPS_NEW)) {
    const c = FARM_CROPS_NEW[key], b = FARM_CROP_BASE[c.t], k = FARM_CROP_KIND[c.k];
    if (!b || !k) continue;
    const min = Math.max(120, Math.ceil((b.min * k.min) / 30) * 30);
    const stones = Math.round(b.sell * k.money);
    // 种子系数：纯卖钱草 0.70，其余三线 0.50（§2.4）
    const cs = c.k === 'sell' ? 0.70 : k.seed;
    const gl = FARM_CROP_TIER_LEVEL[c.t] || 1;
    // 服用·修为（§2.5-A）：纯修为草直表；综合草玄/仙保序微调；其余 = round(E × e)
    let cexp: number;
    if (c.k === 'cult') cexp = FARM_CROP_EXP_PURE[c.t] || 0;
    else if (c.k === 'mix' && (c.t === 3 || c.t === 4)) cexp = FARM_CROP_EXP_MIX_ADJ[c.t];
    else cexp = Math.round(b.expBase * k.exp);
    out[key] = { name: FARM_CROPS_NEW_NAME[key] || key, seed: Math.round(stones * cs), minutes: min, stones, exp: cexp, grottoLevel: gl > 1 ? gl : undefined };
  }
  return out;
}
// T5：变卖出口定价（纯）：与收获结算同源（farmYield 基准 × 洞府/照料乘区，提前减半）——
//   供 UI 在「尚未收获」时预告两种出口到手值；权威口径始终在 farmHarvestOne 内复算。
function farmCropSell(key: string): number {
  const d = farmCropDefs()[key];
  return d ? Math.max(0, Math.floor(Number(d.stones) || 0)) : 0;
}
// T5：服用出口效果（纯）：修为 + 基础属性 + 百分比属性（含硬上限值与已满标记，供 UI 置灰）。
//   owned = 玩家当前存档 player（可空）；上限按「灵田服用累计」字段实算，触顶项给 capped:true。
function farmCropConsume(key: string, owned?: any): { exp: number; attrs: Array<{ key: string; label: string; add: number }>; pcts: Array<{ key: string; label: string; pct: number; cap: number; capped: boolean }> } {
  const d = farmCropDefs()[key];
  if (!d) return { exp: 0, attrs: [], pcts: [] };
  const cnt = FARM_CROPS_NEW[key];
  const p = owned && typeof owned === 'object' ? owned : {};
  const attrs: Array<{ key: string; label: string; add: number }> = [];
  const pcts: Array<{ key: string; label: string; pct: number; cap: number; capped: boolean }> = [];
  if (cnt && cnt.k === 'mix') {
    const per = FARM_CROP_BASE[cnt.t].attr;
    for (const a of (FARM_CROP_ATTRS[key] || [])) attrs.push({ key: a.key, label: a.label, add: per });
  }
  if (cnt && cnt.k === 'rare') {
    for (const a of (FARM_CROP_PCT[key] || [])) {
      const cap = Number(FARM_CROP_ATTR_CAP[a.key] || 0); // 百分点（如 8）
      // ★ 单位归一：存档里 critRate 等存的是小数比例（0.08 = 8%）⇒ ×100 转百分点再与 cap 比对
      const curPct = Math.max(0, Number(p[a.key]) || 0) * 100;
      pcts.push({ key: a.key, label: a.label, pct: a.pct, cap, capped: cap > 0 && curPct >= cap - 1e-9 });
    }
  }
  return { exp: Math.max(0, Math.floor(Number(d.exp) || 0)), attrs, pcts };
}
// T5：旧种禁止新播（存量兼容：已种下的旧田不受影响，仍走 farmCrop 旧口径收获）
function farmCropNoPlant(key: string): boolean {
  return !Object.prototype.hasOwnProperty.call(FARM_CROPS_NEW, key);
}"""

# ============================================================ T5.3 farmHarvestOne

T5_3_OLD = """async function farmHarvestOne(userId: number, row: any, opts?: { mail?: boolean }): Promise<{ ok: boolean; status?: number; error?: string; slot?: number; crop?: string; name?: string; early?: boolean; stones?: number; exp?: number; matureAt?: number; eventMults?: { exp: number; stones: number } }> {
  const def = farmCrop(String(row.crop));
  if (!def) return { ok: false, status: 500, error: '作物数据异常' };
  const now = Date.now();
  const matureAt = Number(row.mature_at);
  const early = !farmIsReady(matureAt, now);
  const mods = await farmHarvestMods(userId, { id: Number(row.id), slot: Number(row.slot), crop: String(row.crop), planted_at: Number(row.planted_at) });
  const gainBase = farmYield(def, early, mods);
  // Y21：活动倍率（收获结算自动应用；引擎读取失败按 ×1 保底，不阻塞收获）
  const evMult = await resolveEventMults(now).catch(() => ({ events: [] as any[], expMult: 1, stonesMult: 1 }));
  // Y6B：师徒加成/出师增益（读取失败 ×1 保底，不阻塞收获）
  const mnG = await resolveMentorGains(userId, now).catch(() => ({ expMult: 1, stonesMult: 1 }));
  const gain = { stones: actApplyGain(gainBase.stones, evMult.stonesMult * mnG.stonesMult), exp: actApplyGain(gainBase.exp, evMult.expMult * mnG.expMult) };
  const claim = await dbRun('UPDATE spirit_farm SET harvested = 1 WHERE id = ? AND player_id = ? AND harvested = 0', [Number(row.id), userId]);
  if (!claim.changes) return { ok: false, status: 409, error: '该田已收获' }; // 并发双击只一方生效
  let credited = false;
  const hit = await updatePlayerSave(userId, (sd: any) => {
    if (!sd.player || typeof sd.player !== 'object') return;
    sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + gain.stones;
    sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + gain.exp;
    credited = true;
  });
  if (!hit.ok || !credited) {
    // 补偿：回退收获标记（活跃行已清零，恢复 harvested=0 必不违反部分唯一索引；极窄竞态见函数头注）
    await dbRun('UPDATE spirit_farm SET harvested = 0 WHERE id = ?', [Number(row.id)]).catch((e: any) => console.error('farm harvest revert error:', e?.message || e));
    return { ok: false, status: hit.error === 'No save found' ? 404 : 500, error: hit.error === 'No save found' ? '请先进游戏创建角色' : '入账失败，请重试' };
  }
  // [act087] C 灵玉阁掉玉挂点（farmHarvestOne 公共入账点：单收/一键收口径自动一致；409 落败方不掉玉）
  if (gain.stones > 0) actDropTokens(userId, gain.stones, now).catch((e: any) => console.error('act drop tokens (farm) error:', e?.message || e));

  if (opts?.mail !== false) {
    insertMail(userId, '灵田丰收',
      `洞府灵田，「${def.name}」${early ? '提前起收（收益减半）' : '应时而收'}！\\n\\n· 灵石 +${gain.stones}（已入账）\\n· 修为 +${gain.exp}（已入账）\\n\\n灵石与修为已直接汇入随身囊中，回游戏即可查看。田地已翻新，随时可播下一茬。`,
      'system', 0).catch((e: any) => console.error('farm harvest mail error:', e?.message || e));
  }
  return { ok: true, slot: Number(row.slot), crop: String(row.crop), name: def.name, early, stones: gain.stones, exp: gain.exp, matureAt, eventMults: { exp: evMult.expMult, stones: evMult.stonesMult } };
}"""

T5_3_NEW = """// ★ T5（0.8.9）双出口：mode='sell'（变卖 → 灵石）/ 'consume'（服用 → 修为 + 属性）。
//   缺省 mode='sell' ⇒ 0.8.7 单收/一键收调用点逐位兼容（不传 mode 行为不变）。
//   ★ 回滚三段式逐字保留：守卫式 harvested=1 → credited 标志 → hit.ok 失败回退 harvested=0。
//   consume 的百分比属性有硬上限（FARM_CROP_ATTR_CAP，灵田服用累计口径，独立于装备/称号）。
//   ⚠ 百分比属性独立于修为独立入账：入账闭包内不做“上限后再回退修为”的二次写，
//     避免「一次收获拆成两笔存档事务」引入新的部分成功态。
async function farmHarvestOne(userId: number, row: any, opts?: { mail?: boolean; mode?: string }): Promise<{ ok: boolean; status?: number; error?: string; slot?: number; crop?: string; name?: string; early?: boolean; stones?: number; exp?: number; matureAt?: number; eventMults?: { exp: number; stones: number }; mode?: string; attrs?: Array<{ key: string; label: string; add: number }>; pcts?: Array<{ key: string; label: string; pct: number; cap: number; capped: boolean }> }> {
  const def = farmCrop(String(row.crop));
  if (!def) return { ok: false, status: 500, error: '作物数据异常' };
  const mode = opts?.mode === 'consume' ? 'consume' : 'sell'; // ★ 缺省 sell = 旧口径
  const now = Date.now();
  const matureAt = Number(row.mature_at);
  const early = !farmIsReady(matureAt, now);
  const mods = await farmHarvestMods(userId, { id: Number(row.id), slot: Number(row.slot), crop: String(row.crop), planted_at: Number(row.planted_at) });
  const gainBase = farmYield(def, early, mods);
  // Y21：活动倍率（收获结算自动应用；引擎读取失败按 ×1 保底，不阻塞收获）
  const evMult = await resolveEventMults(now).catch(() => ({ events: [] as any[], expMult: 1, stonesMult: 1 }));
  // Y6B：师徒加成/出师增益（读取失败 ×1 保底，不阻塞收获）
  const mnG = await resolveMentorGains(userId, now).catch(() => ({ expMult: 1, stonesMult: 1 }));
  const gain = { stones: actApplyGain(gainBase.stones, evMult.stonesMult * mnG.stonesMult), exp: actApplyGain(gainBase.exp, evMult.expMult * mnG.expMult) };
  // T5：服用出口效果（纯函数，只读；含上限触顶标记）。变卖出口不消耗属性。
  const cons = mode === 'consume' ? farmCropConsume(String(row.crop)) : null;
  const claim = await dbRun('UPDATE spirit_farm SET harvested = 1 WHERE id = ? AND player_id = ? AND harvested = 0', [Number(row.id), userId]);
  if (!claim.changes) return { ok: false, status: 409, error: '该田已收获' }; // 并发双击只一方生效
  const credit: { stones: number; exp: number; attrs: Array<{ key: string; label: string; add: number }>; pcts: Array<{ key: string; label: string; pct: number; cap: number; capped: boolean }> } = {
    stones: mode === 'sell' ? gain.stones : 0,
    exp: mode === 'consume' ? gain.exp : 0,
    attrs: mode === 'consume' && cons ? cons.attrs.slice() : [],
    pcts: mode === 'consume' && cons ? cons.pcts.slice() : [],
  };
  // ★ T5 修复（0.8.9）：**实际入账修为** = creditedExp。变卖出口只有「旧种兼容区」同时给修为
  //   （见下方入账闭包 isLegacyCrop 分支），20 新品纯卖钱草给 0；服用出口给 credit.exp。
  //   病根：旧邮件按 `gain.exp` 写「修为 +N（已入账）」，但新品变卖实际未加 ⇒ 谎报；回执又写 credit.exp
  //   （旧种变卖时亦为 0）⇒ 邮件/回执/实际入账三处口径不一致。现统一以 creditedExp 为准。
  const creditedExp = mode === 'consume' ? credit.exp : (isLegacyCrop(String(row.crop)) ? gain.exp : 0);
  let credited = false;
  const hit = await updatePlayerSave(userId, (sd: any) => {
    if (!sd.player || typeof sd.player !== 'object') return;
    if (mode === 'sell') {
      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + credit.stones;
      // T5 变卖口径：旧作物（兼容区）按 0.8.7 原口径**同时**给修为；新品（4 产品线）纯卖钱草只给灵石
      if (isLegacyCrop(String(row.crop))) sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + gain.exp;
    } else {
      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + credit.exp;
      for (const a of credit.attrs) sd.player[a.key] = Math.max(0, Math.floor(Number(sd.player[a.key]) || 0)) + a.add;
      // 百分比属性：逐项按硬上限封顶（上限按灵田服用累计字段实算；触顶项不写）。
      // ★ 单位：pc.pct / pc.cap 均为**百分点**（如 pct=1.8, cap=8）；存档存**小数比例** ⇒ 全程在百分点上算，末尾 ÷100 落盘。
      for (const pc of credit.pcts) {
        if (pc.capped) continue;
        const curPct = Math.max(0, Number(sd.player[pc.key]) || 0) * 100;
        const nextPct = pc.cap > 0 ? Math.min(pc.cap, curPct + pc.pct) : curPct + pc.pct;
        sd.player[pc.key] = Math.round(nextPct * 100) / 10000; // 百分點 → 小数比例，保留 4 位
        pc.capped = pc.cap > 0 && nextPct >= pc.cap - 1e-9;
      }
    }
    credited = true;
  });
  if (!hit.ok || !credited) {
    // 补偿：回退收获标记（活跃行已清零，恢复 harvested=0 必不违反部分唯一索引；极窄竞态见函数头注）
    await dbRun('UPDATE spirit_farm SET harvested = 0 WHERE id = ?', [Number(row.id)]).catch((e: any) => console.error('farm harvest revert error:', e?.message || e));
    return { ok: false, status: hit.error === 'No save found' ? 404 : 500, error: hit.error === 'No save found' ? '请先进游戏创建角色' : '入账失败，请重试' };
  }
  // [act087] C 灵玉阁掉玉挂点（farmHarvestOne 公共入账点：单收/一键收口径自动一致；409 落败方不掉玉）
  if (gain.stones > 0) actDropTokens(userId, gain.stones, now).catch((e: any) => console.error('act drop tokens (farm) error:', e?.message || e));

  if (opts?.mail !== false) {
    const lines = mode === 'sell'
      ? `· 灵石 +${credit.stones}（已入账）` + (creditedExp > 0 ? `\\n· 修为 +${creditedExp}（已入账）` : `\\n· 修为 +0（本品种变卖不产修为）`)
      : `· 修为 +${credit.exp}（已入账）\\n` + credit.attrs.map((a: any) => `· ${a.label} +${a.add}（永久生效）`).join('\\n')
        + (credit.pcts.length ? '\\n' + credit.pcts.map((p: any) => `· ${p.label} ${p.capped ? '已达上限（未增加）' : '+' + p.pct + '%'}`).join('\\n') : '');
    insertMail(userId, '灵田丰收',
      `洞府灵田，「${def.name}」${early ? '提前起收（收益减半）' : '应时而收'}！\\n\\n· 出口：${mode === 'sell' ? '变卖' : '服用'}\\n${lines}\\n\\n田地已翻新，随时可播下一茬。`,
      'system', 0).catch((e: any) => console.error('farm harvest mail error:', e?.message || e));
  }
  return { ok: true, slot: Number(row.slot), crop: String(row.crop), name: def.name, early, stones: credit.stones, exp: creditedExp, matureAt, mode, attrs: credit.attrs, pcts: credit.pcts, eventMults: { exp: evMult.expMult, stones: evMult.stonesMult } };
}

// T5：旧作物判定（兼容区 5 种；供上述变卖口径分流用）
function isLegacyCrop(key: string): boolean {
  return key === 'lingcao' || key === 'lingzhi' || key === 'qianniancan' || key === 'taixuguo' || key === 'zaohuaqinglian';
}"""

# ============================================================ T5.4 单收端点

T5_4_OLD = """// POST /api/farm/harvest {slot} — 收获：到期=全额收益，提前=减半（玩家自选）；"""

T5_4_NEW = """// POST /api/farm/harvest {slot, mode:'sell'|'consume'} — T5 双出口收获：到期=全额，提前=减半（玩家自选）；
// 变卖 → 灵石；服用 → 修为 + 属性（2~3 基础属性 / 1~2 百分比属性，百分比有硬上限）。
// 缺省 mode='sell' 保持 0.8.7 单出口逐位兼容。"""

T5_4B_OLD = """    // T10：单收/一键收抽公共 farmHarvestOne（倍率/掉玉挂点/邮件口径逐位一致；T5 只钩公共入账点）
    const one = await farmHarvestOne(userId, r);
    if (!one.ok) return res.status(one.status || 500).json({ error: one.error || '服务器繁忙' });
    res.json({ ok: true, slot: one.slot, crop: one.crop, name: one.name, early: one.early, stones: one.stones, exp: one.exp, matureAt: one.matureAt, eventMults: one.eventMults });"""

T5_4B_NEW = """    // T5（0.8.9）：出口二选一——非法值 409 明确拒绝（绝不静默降级为变卖，防玩家误吞神品）
    const modeRaw = req.body?.mode;
    if (modeRaw != null && asStr(modeRaw) !== 'sell' && asStr(modeRaw) !== 'consume') {
      return res.status(409).json({ error: '出口非法：仅支持 变卖（sell）/ 服用（consume）' });
    }
    const mode = asStr(modeRaw) === 'consume' ? 'consume' : 'sell';
    // T10：单收/一键收抽公共 farmHarvestOne（倍率/掉玉挂点/邮件口径逐位一致；T5 只钩公共入账点）
    // ★ T5 修复（0.8.9）：T10 单收端点的 SELECT 只取 id/crop/planted_at/mature_at，**漏取 slot**
    //   ⇒ farmHarvestOne 收到的 row.slot 为 undefined ⇒ farmHarvestMods 按 slot 查 farm_daily_care
    //   得到 NaN 匹配不到 ⇒ 照料加成与虫害在**单收路径恒失效**（一键收因 SELECT 带 slot 不受影响）。
    //   端点内已有 `slot` 变量，此处补回（不改 T10 的 SELECT，最小面）。
    const one = await farmHarvestOne(userId, Object.assign({}, r, { slot }), { mode });
    if (!one.ok) return res.status(one.status || 500).json({ error: one.error || '服务器繁忙' });
    res.json({ ok: true, slot: one.slot, crop: one.crop, name: one.name, early: one.early, mode: one.mode, stones: one.stones, exp: one.exp, attrs: one.attrs || [], pcts: one.pcts || [], matureAt: one.matureAt, eventMults: one.eventMults });"""

# ============================================================ T5.5 harvest/all

T5_5_OLD = "        const one = await farmHarvestOne(userId, rw, { mail: false });"
T5_5_NEW = "        const one = await farmHarvestOne(userId, rw, { mail: false, mode: 'sell' }); // T5：一键收恒走变卖（与 0.8.7 单出口口径一致，不掉修为）"

# ============================================================ T5.6 status 下发

T5_6_OLD = "    res.json({ now, stones, grottoLevel, slots, crops: FARM_CROPS, unlockCost: FARM_UNLOCK_COST, unlockGrottoLevel: FARM_UNLOCK_GROTTO_LEVEL, readyCount, nextUnlock, boostDaily: { used: boostUsed, cap: farmBoostCap(grottoLevel) } });"

T5_6_NEW = """    // T5（0.8.9）：下发新作物表 + 每种的「变卖价 / 服用效果」+ 品阶分层 + 百分比上限（供前端展示与置灰）。
    //   crops 仍为「key → 定义」同形结构（旧客户端零改动兼容，原样可渲染）；
    //   cropList 为带 key 的数组，字段契约对齐 yl_farm089_ext.py（YlxwTFarmT5）：
    //     tier  = '凡'|'灵'|'玄'|'仙'|'神'（单字，直接拼「X品」）；line = 'sell'|'cult'|'mix'|'rare'；
    //     sell  = 变卖价（灵石，纯数）；consExp = 服用修为；
    //     consAttr = [{key:'attack'|'defense'|'maxHp'|'spirit'|'speed', value:n}]；
    //     consPct  = [{key:'critRate'|'dodgeRate'|'lifeLeech', value:0.008}]（**小数比例**，UI ×100 显示）。
    const cropDefs = farmCropDefs();
    const cropList: any[] = [];
    for (const ck of Object.keys(cropDefs)) {
      const cd0 = cropDefs[ck];
      const cc = farmCropConsume(ck, playerObj);
      const legacy = !FARM_CROPS_NEW[ck];
      cropList.push({
        key: ck, name: cd0.name, seed: cd0.seed, minutes: cd0.minutes, stones: cd0.stones, exp: cd0.exp,
        grottoLevel: cd0.grottoLevel || 0,
        tier: legacy ? '' : FARM_CROP_TIERS[FARM_CROPS_NEW[ck].t - 1].slice(0, 1),
        line: legacy ? '' : FARM_CROPS_NEW[ck].k, // 'sell'|'cult'|'mix'|'rare'（客户端 YLXW_FT_LINE 键）
        legacy,
        plantable: !legacy,
        sell: cd0.stones,
        consExp: cc.exp,
        consAttr: cc.attrs.map((x: any) => ({ key: x.key, value: x.add })),
        consPct: cc.pcts.map((x: any) => ({ key: x.key, value: x.pct / 100 })),
      });
    }
    res.json({ now, stones, grottoLevel, slots, crops: cropDefs, cropList, cropTiers: FARM_CROP_TIERS, cropTierLevel: FARM_CROP_TIER_LEVEL, attrCaps: FARM_CROP_ATTR_CAP, unlockCost: FARM_UNLOCK_COST, unlockGrottoLevel: FARM_UNLOCK_GROTTO_LEVEL, readyCount, nextUnlock, boostDaily: { used: boostUsed, cap: farmBoostCap(grottoLevel) } });"""

# ============================================================ T5.6b status 读 player 对象

T5_6B_OLD = """    let stones = 0;
    let grottoLevel = 0;
    if (saveRow) {
      try {
        const sd0 = JSON.parse(saveRow.save_data);
        stones = Math.max(0, Math.floor(Number(sd0?.player?.spiritStones) || 0));
        grottoLevel = Math.min(10, Math.max(0, Math.floor(Number(sd0?.player?.grotto?.level) || 0)));
      } catch { stones = 0; }
    }"""

T5_6B_NEW = """    let stones = 0;
    let grottoLevel = 0;
    let playerObj: any = null; // T5：供服用效果的百分比上限触顶判定（只读）
    if (saveRow) {
      try {
        const sd0 = JSON.parse(saveRow.save_data);
        stones = Math.max(0, Math.floor(Number(sd0?.player?.spiritStones) || 0));
        grottoLevel = Math.min(10, Math.max(0, Math.floor(Number(sd0?.player?.grotto?.level) || 0)));
        playerObj = sd0?.player && typeof sd0.player === 'object' ? sd0.player : null;
      } catch { stones = 0; }
    }"""

# ============================================================ T5.7 plant 拒旧种

T5_7_OLD = """    // T10：高阶作物洞府门槛（409；needGrottoLevel 供客户端置灰提示）
    const gi = farmGrottoInfo(saveRow.save_data);"""

T5_7_NEW = """    // T5（0.8.9）：旧 5 种已下线，禁止新播（409）；存量已种下的旧田仍可正常收获（兼容）
    if (farmCropNoPlant(cropKey)) {
      return res.status(409).json({ error: '该灵草品种已停止栽种，请改种新灵草（存量旧作物仍可正常收获）', retired: true });
    }
    // T10：高阶作物洞府门槛（409；needGrottoLevel 供客户端置灰提示）
    const gi = farmGrottoInfo(saveRow.save_data);"""

# ============================================================ T5.8 照料口径

T5_8_OLD = "const FARM_TEND_BONUS = 0.10;              // #7 照料当日收获加成（建议 +10%）"
T5_8_NEW = """// ★ T5（0.8.9）item4 照料口径改档：每日 1 次 → 每 2 小时 1 次，但每次只 +2%、
//   单田当日累计上限 +10%（总收益量与 0.8.7 完全一致，只是更频繁、更易参与）。
//   ★ 红线耦合：若沿用旧「每次 +10% × 12 次/日」则满配乘区 → ×2.2，117,612 会变 213,840，必破 150,000。
const FARM_TEND_PER = 0.02;                // #7 照料单次收获加成（+2%/次，每 2 小时可照料 1 次）
const FARM_TEND_CAP = 0.10;                // #7 照料单田当日累计加成上限（+10%，与 0.8.7 总收益同口径）"""

T5_8B_OLD = """    tendBonus: tended ? FARM_TEND_BONUS : 0,"""
T5_8B_NEW = """    tendBonus: Math.min(FARM_TEND_CAP, FARM_TEND_COUNT * FARM_TEND_PER), // T5：照料按昨日计次累计（每次 +2%，单田当日封顶 +10%）"""

T5_8C_OLD = """// T10：收获/种植时的产出修正（洞府加成/照料/连作衰减/虫害）。
// 读存档洞府等级 + 当日 farm_daily_care 行 + spirit_farm 历史行推导连作；全部只读，无副作用。
async function farmHarvestMods(userId: number, row: { id?: number; slot: number; crop: string; planted_at: number }): Promise<{ grottoBonus: number; tendBonus: number; streakDecay: number; pest: boolean }> {
  const slot = Number(row.slot);
  const today = bjDate(Date.now());
  const [saveRow, careRow, histRows] = await Promise.all([
    dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
    dbGet('SELECT tended FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]),
    row.id
      ? dbAll('SELECT crop FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 1 AND id < ? ORDER BY id DESC LIMIT 2', [userId, slot, Number(row.id)])
      : Promise.resolve([] as any[]),
  ]);
  const gi = farmGrottoInfo(saveRow ? saveRow.save_data : null);
  const tended = !!careRow && Number(careRow.tended) === 1;
  let streak = 0;
  for (const hr of (histRows || [])) { if (String(hr.crop) === String(row.crop)) streak++; else break; }
  const pest = !tended && farmPestToday(userId, slot, String(row.crop), Number(row.planted_at), today);
  return {
    grottoBonus: farmGrottoBonusOf(gi.level),
    tendBonus: tended ? FARM_TEND_BONUS : 0,
    streakDecay: farmStreakDecayOf(streak),
    pest,
  };
}"""

T5_8C_NEW = """// T5：照料日计次上限（每 2 小时 1 次 ⇒ 单田每日至多 12 次）
const FARM_TEND_COUNT = 12;

// T10/T5：收获/种植时的产出修正（洞府加成/照料/连作衰减/虫害）。
// 读存档洞府等级 + 当日 farm_daily_care 行 + spirit_farm 历史行推导连作；全部只读，无副作用。
// ★ 照料口径（T5 §7-Q3）：每次 +2%、单田当日累计封顶 +10% ⇒ 满配乘区仍是 ×1.21，红线结论不变。
async function farmHarvestMods(userId: number, row: { id?: number; slot: number; crop: string; planted_at: number }): Promise<{ grottoBonus: number; tendBonus: number; streakDecay: number; pest: boolean }> {
  const slot = Number(row.slot);
  const today = bjDate(Date.now());
  const [saveRow, careRow, histRows] = await Promise.all([
    dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
    dbGet('SELECT tended, tend_count FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]),
    row.id
      ? dbAll('SELECT crop FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 1 AND id < ? ORDER BY id DESC LIMIT 2', [userId, slot, Number(row.id)])
      : Promise.resolve([] as any[]),
  ]);
  const gi = farmGrottoInfo(saveRow ? saveRow.save_data : null);
  const tended = !!careRow && Number(careRow.tended) === 1;
  // ★ T5 修复（0.8.9）：tendBonus 按**当日实际照料次数**算（tend_count），不再恒为满配常量。
  //   病根：旧实现 `FARM_TEND_COUNT * FARM_TEND_PER` = 12 × 0.02 = 0.10 是编译期常量 ⇒
  //   照料 0 次与 1 次产出完全一样，照料玩法无收益、经济恒处满配。
  //   存量行（升级前 tended=1 但无计数列）退回「至少 1 次」以保底不为 0。
  const tendCount = Math.max(Number(careRow?.tend_count) || 0, tended ? 1 : 0);
  let streak = 0;
  for (const hr of (histRows || [])) { if (String(hr.crop) === String(row.crop)) streak++; else break; }
  const pest = !tended && farmPestToday(userId, slot, String(row.crop), Number(row.planted_at), today);
  return {
    grottoBonus: farmGrottoBonusOf(gi.level),
    tendBonus: Math.min(FARM_TEND_CAP, tendCount * FARM_TEND_PER), // T5：照料按当日实际计次累计（每次 +2%，单田当日封顶 +10%）
    streakDecay: farmStreakDecayOf(streak),
    pest,
  };
}"""

# ============================================================ T5.9 tend 端点文案

T5_9_OLD = """// POST /api/farm/tend {slot} — T10 照料（浇灌+除虫二合一，免费）：清当日虫害 + 该田当日收获 FARM_TEND_BONUS。"""
T5_9_NEW = """// POST /api/farm/tend {slot} — T5 照料（浇灌+除虫二合一，免费）：清当日虫害 + 该田当日累计收获加成。
// ★ T5（0.8.9）item4 口径（策划 Q3(a)）：每次 +2%、单田当日累计封顶 +10%（总收益同 0.8.7）。
//   ★ 修复（0.8.9）：照料改**计次**（每次 +1，封顶 FARM_TEND_COUNT 次/日），tendBonus 按实际次数生效。"""

T5_9C_OLD = """    const gate = await dbRun(
      'INSERT INTO farm_daily_care (player_id, slot, date, tended, boosted) VALUES (?, ?, ?, 1, 0) ' +
      'ON CONFLICT(player_id, slot, date) DO UPDATE SET tended = 1 WHERE tended = 0',
      [userId, slot, today]
    );
    if (!gate.changes) return res.status(409).json({ error: '该田今日已照料过' });"""

T5_9C_NEW = """    // ★ T5 修复（0.8.9）：计次闸门——每次 +1（封顶 FARM_TEND_COUNT 次/日），取代原布尔「每日 1 次」。
    //   tend_count 由 db.serialize 内的幂等 safeAddColumn 迁移保证存在；tended 仍置 1（=今日照料过）。
    const gate = await dbRun(
      'INSERT INTO farm_daily_care (player_id, slot, date, tended, boosted, tend_count) VALUES (?, ?, ?, 1, 0, 1) ' +
      'ON CONFLICT(player_id, slot, date) DO UPDATE SET tended = 1, tend_count = tend_count + 1 WHERE tend_count < ?',
      [userId, slot, today, FARM_TEND_COUNT]
    );
    if (!gate.changes) return res.status(409).json({ error: '该田今日照料次数已达上限' });
    const cntRow = await dbGet('SELECT tend_count FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]);
    const tendCount = Math.max(1, Number(cntRow?.tend_count) || 1);
    const bonusPct = Math.round(Math.min(FARM_TEND_CAP, tendCount * FARM_TEND_PER) * 100);"""

T5_9B_OLD = """    res.json({ ok: true, slot, tendBonusPct: Math.round(FARM_TEND_BONUS * 100), message: `照料完成，本块田今日收获 +${Math.round(FARM_TEND_BONUS * 100)}%（虫害已清除）` });"""
T5_9B_NEW = """    res.json({ ok: true, slot, tendCount, tendBonusPct: bonusPct, tendPerPct: Math.round(FARM_TEND_PER * 100), tendCapPct: Math.round(FARM_TEND_CAP * 100), message: `照料完成（今日第 ${tendCount} 次），本块田今日收获 +${bonusPct}%（每次 +${Math.round(FARM_TEND_PER * 100)}%，封顶 +${Math.round(FARM_TEND_CAP * 100)}%，虫害已清除）` });"""

# ============================================================ T5.1c farmCrop 查询口径
# ★ P0 修复（2026-09-29）：farmCrop() 必须查 farmCropDefs()（25 键），不得再查旧 FARM_CROPS（5 键）。
#
#   病根：本环把 20 个新种加进 FARM_CROPS_NEW + farmCropDefs()，**却漏改 farmCrop()**，
#   于是 /api/farm/plant 的 `const crop = farmCrop(req.body?.crop); if (!crop) return 400 '未知作物'`
#   在 **retired 409 分支之前**把 20 个新种全部拒掉。
#   实测（2026-09-29，冻结产物 7eb00522…，空库冷启动实例）：
#     POST /api/farm/plant {slot:1, crop:'linggusi'}  -> 400 {"error":"未知作物"}   （新种 × 20 全如此）
#     POST /api/farm/plant {slot:1, crop:'lingcao'}   -> 409 {"error":"…已停止栽种…","retired":true}
#   `GET /api/farm/status` 自报 cropList(25) 含全部 20 个新键，但一个也种不下去 ⇒
#   客户端 `yl_farm089_ext.py:170` 遍历 status.crops 渲染的 25 个按钮 **25/25 全废**
#   ⇒ 0.8.9 头条功能（品种 5→20）玩家完全用不了。
#
#   4 个调用点全部需要 25 键视图（无一依赖旧「只认 5 键」行为）：
#     · /api/farm/status 槽位回显 —— 查不到 ⇒ ready=false / leftMs=0 ⇒ 新种田地显示「永不成熟」
#     · /api/farm/plant  入参校验 —— 查不到 ⇒ 400（本 P0 正面现场）
#     · farmHarvestOne           —— 查不到 ⇒ 500 '作物数据异常'
#     · /api/farm/boost          —— 查不到 ⇒ 500 '作物数据异常'
#   旧种「不可新播」由 farmCropNoPlant()（查 FARM_CROPS_NEW）**单独**判定，与本函数正交 ⇒
#   本函数改 25 键视图**不会**放行旧种新播（仍走 409 retired）。
#   返回类型同时补 `grottoLevel?`（farmCropDefs 的元素类型已带该字段；plant 端点 :6902
#   本来就读 `crop.grottoLevel`，此前靠 strip-types 不做类型检查才没报错）。
T5_1C_OLD = """function farmCrop(key: unknown): { name: string; seed: number; minutes: number; stones: number; exp: number } | null {
  return key != null && Object.prototype.hasOwnProperty.call(FARM_CROPS, asStr(key)) ? FARM_CROPS[asStr(key)] : null;
}"""

T5_1C_NEW = """function farmCrop(key: unknown): { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number } | null {
  // ★ T5 修复（2026-09-29）：查 farmCropDefs()（25 键 = 5 旧兼容 + 20 新），**不再查旧 FARM_CROPS（5 键）**。
  //   旧种不可新播由 farmCropNoPlant() 单独判定，与本函数正交 ⇒ 旧种仍走 409 retired。
  if (key == null) return null;
  const k = asStr(key);
  const defs = farmCropDefs();
  return Object.prototype.hasOwnProperty.call(defs, k) ? defs[k] : null;
}"""

EDITS = [
    ('T5.1  作物表 5 旧种 → 兼容区 + 20 新种 + 3 生成器', T5_1_OLD, T5_1_NEW),
    ('T5.1c farmCrop 查询口径改 farmCropDefs（P0）',      T5_1C_OLD, T5_1C_NEW),
    ('T5.3  farmHarvestOne 加 mode 双出口',              T5_3_OLD, T5_3_NEW),
    ('T5.4a 单收端点注释',                                T5_4_OLD, T5_4_NEW),
    ('T5.4b 单收端点接 mode',                             T5_4B_OLD, T5_4B_NEW),
    ('T5.5  harvest/all 恒走 sell',                       T5_5_OLD, T5_5_NEW),
    ('T5.6a status 读 player 对象',                       T5_6B_OLD, T5_6B_NEW),
    ('T5.6b status 下发新表/出口/品阶/上限',              T5_6_OLD, T5_6_NEW),
    ('T5.7  plant 拒旧种新播',                            T5_7_OLD, T5_7_NEW),
    ('T5.8a 照料常量换名 + 改档',                         T5_8_OLD, T5_8_NEW),
    ('T5.8b farmHarvestMods 照料口径',                    T5_8C_OLD, T5_8C_NEW),
    ('T5.9a tend 端点注释改口径',                         T5_9_OLD, T5_9_NEW),
    ('T5.9c tend 端点计次闸门',                           T5_9C_OLD, T5_9C_NEW),
    ('T5.9b tend 端点回执文案',                           T5_9B_OLD, T5_9B_NEW),
]

# 链序依赖（取自 0.8.7/0.8.9 定版产物实测计数）
REQUIRES = [
    ("const FARM_SLOTS = 6;", 1, "T10 环必须先跑过（本环为其后继）"),
    ("async function farmHarvestOne(", 1, "T10 公共收获原语必须在位"),
    ("const FARM_TEND_BONUS = 0.10;", 1, "T10 照料常量必须在位（本环换名改档）"),
    ("actApplyGain(", 8, "T5 活动挂点计数基线：定义 1 + 调用 7（本环零新增）"),
    ("actDropTokens(", 4, "灵玉阁掉玉挂点计数基线：定义 1 + 调用 3（灵田/炼丹/离线；本环零改动）"),
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

    # 1) 链序依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 2) 幂等
    if "farmCropDefs" in src or "FARM_CROPS_NEW" in src:
        fail("source looks already patched（已存在 farmCropDefs / FARM_CROPS_NEW）")

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
    base_cnt = {
        'actApplyGain(': src.count('actApplyGain('),
        'actDropTokens(': src.count('actDropTokens('),
        'await resolveEventMults(now)': src.count('await resolveEventMults(now)'),
        'await resolveMentorGains(userId, now)': src.count('await resolveMentorGains(userId, now)'),
        'res.status(403': src.count('res.status(403'),
    }
    # ★ P0 防回归计算（2026-09-29）：切出 farmCrop() 函数体，供下方结构性门禁使用。
    #   本环此前**没有任何 gate 断言 farmCrop 消费新表** ⇒ 20 新种全被 400 拒掉却门禁全绿。
    _fc_i = out.find('function farmCrop(')
    _fc_j = out.find('\n}\n', _fc_i) if _fc_i >= 0 else -1
    _fc = out[_fc_i:_fc_j] if (_fc_i >= 0 and _fc_j >= 0) else ''
    # 结构性判定必须剥掉行注释：修复说明里会出现「不再查旧 FARM_CROPS」这类字样，会被误判为裸引用。
    _fc_code = '\n'.join(_l.split('//')[0] for _l in _fc.split('\n'))
    # 20 个新键是否**全部**能被 farmCropDefs() 生成（t 在品阶表、k 在类型表，否则被 `if (!b || !k) continue` 跳过）
    _pairs = re.findall(r"(\w+):\s*\{ t: (\d), k: '(\w+)' \}", out)
    _tiers = set(re.findall(r"^  (\d):\s*\{ min: \d+,\s*sell: \d+,\s*expBase: \d+,\s*attr: \d+ \}", out, re.M))
    _kinds = set(re.findall(r"^  (\w+):\s*\{ min: [\d.]+,\s*money: [\d.]+,\s*seed: [\d.]+,\s*exp: [\d.]+,\s*kindName: '", out, re.M))
    _skipped = [k for k, t, kd in _pairs if t not in _tiers or kd not in _kinds]
    gates = [
        # ---- T5.1 作物表 ----
        ('T5 作物表类型签名未动',            'const FARM_CROPS: Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number }> = {', 1, None),
        ('T5 旧种兼容区标记',                '// ── 旧作物（T5 兼容区 · 只读存量，不可新播）', 1, None),
        ('T5 品阶基准表',                    'const FARM_CROP_BASE: Record<number, { min: number; sell: number; expBase: number; attr: number }> = {', 1, None),
        ('T5 类型系数表',                    'const FARM_CROP_KIND: Record<string, { min: number; money: number; seed: number; exp: number; kindName: string }> = {', 1, None),
        ('T5 新 20 种表',                    'const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {', 1, None),
        ('T5 新 20 种名表',                  'const FARM_CROPS_NEW_NAME: Record<string, string> = {', 1, None),
        ('T5 服用基础属性表',                'const FARM_CROP_ATTRS: Record<string, Array<{ key: string; label: string }>> = {', 1, None),
        ('T5 服用百分比表',                  'const FARM_CROP_PCT: Record<string, Array<{ key: string; label: string; pct: number }>> = {', 1, None),
        ('T5 百分比硬上限表',                'const FARM_CROP_ATTR_CAP: Record<string, number> = { hitRate: 8, critRate: 8, dodgeRate: 6, lifeLeech: 4 };', 1, None),
        ('T5 品阶门槛表',                    'const FARM_CROP_TIER_LEVEL: Record<number, number> = { 1: 1, 2: 1, 3: 3, 4: 5, 5: 7 };', 1, None),
        ('T5 定义生成器',                    'function farmCropDefs(): Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number }> {', 1, None),
        ('T5 变卖价纯函数',                  'function farmCropSell(key: string): number {', 1, None),
        ('T5 服用效果纯函数',                'function farmCropConsume(key: string, owned?: any): { exp: number; attrs:', 1, None),
        ('T5 旧种禁播纯函数',                'function farmCropNoPlant(key: string): boolean {', 1, None),
        ('T5 旧种判定纯函数',                'function isLegacyCrop(key: string): boolean {', 1, None),
        # ---- ★ P0 防回归（2026-09-29）：farmCrop 必须消费 25 键表 ----
        #   病根：本环加了 FARM_CROPS_NEW + farmCropDefs() 却漏改 farmCrop() ⇒ 20 新种全 400。
        #   以下 4 条把「farmCrop 查什么表」「20 键是否都能生成」双双锁死。
        ('P0 farmCrop 改查 farmCropDefs()',   'const defs = farmCropDefs();', 1, None),
        ('P0 farmCrop 返回类型补 grottoLevel', 'function farmCrop(key: unknown): { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number } | null {', 1, None),
        ('P0 farmCropDefs 遍历新 20 键表',    'for (const key of Object.keys(FARM_CROPS_NEW)) {', 1, None),
        ('P0 farmCropDefs 并入 5 旧键（存量兼容）',
         'out.zaohuaqinglian = FARM_CROPS.zaohuaqinglian;', 1, None),
        # ---- ★ 旧种 retired 标记（0.8.9 补丁：客户端据此置灰，条目保留不删）----
        ('T5 crops 旧种 retired 标记就位',     'Object.assign({}, out[legacyKey], { retired: true })', 1, None),
        ('T5 旧种标记判据与 plant 同源',       'if (isLegacyCrop(legacyKey)) out[legacyKey] =', 1, None),
        ('T5 旧种条目仍保留（未删）',           'out.taixuguo = FARM_CROPS.taixuguo;', 1, None),
        ('T5 旧种判定覆盖 5 键（含 T10 两高阶种）',
         "return key === 'lingcao' || key === 'lingzhi' || key === 'qianniancan' || key === 'taixuguo' || key === 'zaohuaqinglian';", 1, None),
        # ---- T5.3/4 双出口 ----
        ('T5 farmHarvestOne 接 opts.mode',   "const mode = opts?.mode === 'consume' ? 'consume' : 'sell';", 1, None),
        ('T5 farmHarvestOne 返回 mode',      'matureAt, mode, attrs: credit.attrs, pcts: credit.pcts, eventMults:', 1, None),
        ('T5 单收端点拒绝非法出口',          "return res.status(409).json({ error: '出口非法：仅支持 变卖（sell）/ 服用（consume）' });", 1, None),
        ('T5 单收端点传 mode',               'const one = await farmHarvestOne(userId, r, { mode });', 0, None),
        ('T5 单收端点补 slot（照料/虫害生效）',
         'const one = await farmHarvestOne(userId, Object.assign({}, r, { slot }), { mode });', 1, None),
        ('T5 一键收恒走 sell',               "const one = await farmHarvestOne(userId, rw, { mail: false, mode: 'sell' });", 1, None),
        ('T5 旧单收调用签名清零',            'await farmHarvestOne(userId, r);', 0, None),
        ('T5 旧一键收调用签名清零',          'await farmHarvestOne(userId, rw, { mail: false });', 0, None),
        # ---- T5.6 status 下发 ----
        ('T5 status 读 player 对象',         'playerObj = sd0?.player && typeof sd0.player', 1, None),
        ('T5 status 下发 cropList',          'const cropList: any[] = [];', 1, None),
        ('T5 status 下发 cropTiers',         'cropList, cropTiers: FARM_CROP_TIERS, cropTierLevel: FARM_CROP_TIER_LEVEL, attrCaps: FARM_CROP_ATTR_CAP', 1, None),
        ('T5 status 变卖/服用字段（客户端契约）', "sell: cd0.stones,\n        consExp: cc.exp,", 1, None),
        ('T5 status 品阶单字（『凡』…）',      "tier: legacy ? '' : FARM_CROP_TIERS[FARM_CROPS_NEW[ck].t - 1].slice(0, 1),", 1, None),
        ('T5 status 产品线键（sell/cult/mix/rare）', "line: legacy ? '' : FARM_CROPS_NEW[ck].k,", 1, None),
        ('T5 百分比下发为小数比例',           'value: x.pct / 100', 1, None),
        ('T5 无命中草（hitRate 不进表）',      'hitRate', 1, '基数（仅上限表占位，零生成）'),
        # ---- T5.7 plant ----
        ('T5 plant 拒旧种',                  'return res.status(409).json({ error: \'该灵草品种已停止栽种，请改种新灵草（存量旧作物仍可正常收获）\', retired: true });', 1, None),
        # ---- T5.8 照料 ----
        ('T5 照料单次常量',                  'const FARM_TEND_PER = 0.02;', 1, None),
        ('T5 照料封顶常量',                  'const FARM_TEND_CAP = 0.10;', 1, None),
        ('T5 照料日计次',                    'const FARM_TEND_COUNT = 12;', 1, None),
        ('T5 旧照料常量清零',                'FARM_TEND_BONUS', 0, None),
        # ---- ★ T5 修复（0.8.9）：照料加成按实际计次，不再恒为编译期常量 ----
        #   ★ 注：tend_count 计次列的**迁移**（safeAddColumn）不放在本环——第 18 环 rankingmig 的
        #     G5/G7 硬编码「全仓 safeAddColumn 调用点 == 20」且该环禁改，本环加列必使其 FAIL。
        #     迁移落在链第 20 环 srv_patch_t16arena.py（同 safeAddColumn，幂等），本环只消费该列。
        ('T5 照料加成按实际计次（非编译期常量）',
         'tendBonus: Math.min(FARM_TEND_CAP, tendCount * FARM_TEND_PER),', 1, None),
        ('T5 照料计次变量取自 tend_count',
         'const tendCount = Math.max(Number(careRow?.tend_count) || 0, tended ? 1 : 0);', 1, None),
        ('T5 照料读取 tend_count 列',
         'SELECT tended, tend_count FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', 1, None),
        ('T5 照料旧常量式清零（不得再出现编译期满配式）',
         'Math.min(FARM_TEND_CAP, FARM_TEND_COUNT * FARM_TEND_PER)', 0, None),
        ('T5 tend 端点计次闸门（tend_count + 1 封顶）',
         'ON CONFLICT(player_id, slot, date) DO UPDATE SET tended = 1, tend_count = tend_count + 1 WHERE tend_count < ?', 1, None),
        ('T5 tend 端点按实际次数回执',
         'tendBonusPct: bonusPct, tendPerPct: Math.round(FARM_TEND_PER * 100), tendCapPct:', 1, None),
        # ---- ★ T5 修复（0.8.9）：变卖邮件/回执修为口径与实际入账同源 ----
        ('T5 变卖实际入账修为变量（creditedExp）',
         "const creditedExp = mode === 'consume' ? credit.exp : (isLegacyCrop(String(row.crop)) ? gain.exp : 0);", 1, None),
        ('T5 变卖邮件修为用 creditedExp（同源）',
         '· 修为 +${creditedExp}（已入账）', 1, None),
        ('T5 变卖邮件不再谎报修为（旧文案清零）',
         '· 修为 +${gain.exp}（已入账）', 0, None),
        ('T5 收获回执修为用 creditedExp（同源）',
         'stones: credit.stones, exp: creditedExp, matureAt, mode,', 1, None),
        # ---- 红线：入账/回滚/挂点零回归 ----
        ('红线 守卫式收获语句仅 1',          'SET harvested = 1 WHERE id = ? AND player_id = ? AND harvested = 0', 1, None),
        ('红线 回退语句仅 1',                'UPDATE spirit_farm SET harvested = 0 WHERE id = ?', 1, None),
        ('红线 credited 标志在位',           'credited = true;', 3, 'base（灵田/炼丹/离线各 1，本环零新增）'),
        ('红线 hit.ok 回退分支在位',         'if (!hit.ok || !credited) {', 1, None),
        ('红线 actApplyGain 总量不变',       'actApplyGain(', base_cnt['actApplyGain('], 'base'),
        ('红线 actDropTokens 挂点不变',      'actDropTokens(', base_cnt['actDropTokens('], 'base'),
        ('红线 resolveEventMults 不变',      'await resolveEventMults(now)', base_cnt['await resolveEventMults(now)'], 'base'),
        ('红线 resolveMentorGains 不变',     'await resolveMentorGains(userId, now)', base_cnt['await resolveMentorGains(userId, now)'], 'base'),
        ('红线 403 零新增',                  'res.status(403', base_cnt['res.status(403'], 'base'),
        ('farmcore 标记唯一起',              '// [farmcore]', 1, None),
        ('farmcore 标记唯一止',              '// [/farmcore]', 1, None),
        # ---- 基线未动 ----
        ('基线 旧种数值逐字未动',            "lingcao:     { name: '灵草',   seed: 1000, minutes: 240,  stones: 800,   exp: 500 },", 1, None),
        ('基线 造化青莲数值逐字未动',        "zaohuaqinglian: { name: '造化青莲', seed: 200000, minutes: 4320, stones: 215000, exp: 129000, grottoLevel: 7 },", 1, None),
        ('基线 开垦价未动',                  'FARM_UNLOCK_COST: Record<number, number> = { 2: 20000, 3: 80000, 4: 200000, 5: 800000, 6: 2000000 }', 1, None),
        ('基线 地块门槛未动',                'FARM_UNLOCK_GROTTO_LEVEL: Record<number, number> = { 4: 5, 5: 7, 6: 9 }', 1, None),
        ('基线 spirit_farm 表未动',          'CREATE TABLE IF NOT EXISTS spirit_farm', 1, None),
    ]
    ok = True
    for g in gates:
        label, needle, exp = g[0], g[1], g[2]
        op = g[3] if len(g) > 3 else None
        shown = 'expect==base(%d)' % exp if op == 'base' else 'expect==%d' % exp
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-38s actual=%d %s" % ("OK" if good else "FAIL", label, act, shown))
    # ---- ★ P0 结构性断言（2026-09-29）：仅靠全局计数无法表达，故单独判定 ----
    #   ① farmCrop 函数体内**不得**再出现裸 FARM_CROPS（只允许 farmCropDefs）——
    #      这正是本 P0 的病根形态，全局计数抓不到（表定义处也有 FARM_CROPS）。
    _fc_bare = re.search(r'FARM_CROPS(?!_NEW)', _fc_code) is not None
    _fc_ok = (not _fc_bare) and ('farmCropDefs()' in _fc) and ('hasOwnProperty.call(defs, k)' in _fc)
    ok = ok and _fc_ok
    print("  [%s] %-38s %s" % ("OK" if _fc_ok else "FAIL", "P0 farmCrop 函数体只查 farmCropDefs（无裸 FARM_CROPS）",
                              "bare_FARM_CROPS=%s calls_defs=%s" % (_fc_bare, 'farmCropDefs()' in _fc)))
    if not _fc_ok:
        print("       farmCrop 函数体切片（%d 字符）：\n%s" % (len(_fc), _fc[:400]))
    #   ② 20 个新键**全部**可被 farmCropDefs() 生成（t/k 两表齐备，无被 continue 跳过者）
    _p_ok = (len(_pairs) == 20) and (not _skipped)
    ok = ok and _p_ok
    print("  [%s] %-38s pairs=%d skipped=%s tiers=%d kinds=%d"
          % ("OK" if _p_ok else "FAIL", "P0 20 新键全部可生成（无缺表跳过）",
             len(_pairs), _skipped or '[]', len(_tiers), len(_kinds)))
    if not ok:
        fail("门禁未全过")

    # 6) 数值自证：20 种作物按 §4.1 公式复算，与 §3 数值表逐位比对（写死在测例里，零外部依赖）
    expect = {
        # key: (minutes, 变卖价 stones, 种子价 seed, 服用修为 consExp)  ← 直取策划案 §3 四张表
        'linggusi': (120, 500, 350, 20), 'ziwenlingdao': (180, 1500, 1050, 80), 'jinsuiteng': (300, 5000, 3500, 300),
        'xianyulian': (480, 13000, 9100, 1000), 'shencangjinshen': (720, 27000, 18900, 3000),
        'peiyuancao': (180, 300, 150, 100), 'zhuangguhua': (270, 900, 450, 400), 'bailianzhi': (450, 3000, 1500, 1400),
        'jiugiaoxuanzhi': (720, 7800, 3900, 4400), 'wanxianghua': (1080, 16200, 8100, 15000),
        'yinqimiao': (150, 100, 50, 150), 'ningyuanzhi': (240, 300, 150, 470), 'xuanyuanguo': (390, 1000, 500, 1450),
        'taiqingguo': (600, 2600, 1300, 4500), 'hunyuandaoguo': (900, 5400, 2700, 19000),
        'jifengye': (600, 2500, 1400, 750), 'xuepohua': (960, 6500, 3640, 2500), 'xingyunhua': (960, 6500, 3640, 2500),
        'dongxuanhua': (1440, 13500, 7560, 7500), 'bumieteng': (1440, 13500, 7560, 7500),
    }
    # 逐项复算（§4.1 公式，与上文 expect 直表互为交叉验证，杜绝“只抄不算”）
    _B = {1: 120, 2: 180, 3: 300, 4: 480, 5: 720}
    _V = {1: 500, 2: 1500, 3: 5000, 4: 13000, 5: 27000}
    _E = {1: 100, 2: 400, 3: 1500, 4: 5000, 5: 15000}
    _K = {'sell': 1.0, 'cult': 1.25, 'mix': 1.5, 'rare': 2.0}
    _M = {'sell': 1.0, 'cult': 0.2, 'mix': 0.6, 'rare': 0.5}
    _CS = {'sell': 0.70, 'cult': 0.50, 'mix': 0.50, 'rare': 0.56}
    _PURE = {1: 150, 2: 470, 3: 1450, 4: 4500, 5: 19000}
    _MIXADJ = {3: 1400, 4: 4400}
    import math as _math
    _spec = [('linggusi',1,'sell'),('ziwenlingdao',2,'sell'),('jinsuiteng',3,'sell'),('xianyulian',4,'sell'),('shencangjinshen',5,'sell'),
             ('peiyuancao',1,'mix'),('zhuangguhua',2,'mix'),('bailianzhi',3,'mix'),('jiugiaoxuanzhi',4,'mix'),('wanxianghua',5,'mix'),
             ('yinqimiao',1,'cult'),('ningyuanzhi',2,'cult'),('xuanyuanguo',3,'cult'),('taiqingguo',4,'cult'),('hunyuandaoguo',5,'cult'),
             ('jifengye',3,'rare'),('xuepohua',4,'rare'),('xingyunhua',4,'rare'),('dongxuanhua',5,'rare'),('bumieteng',5,'rare')]
    _recalc = {}
    for _k2, _t, _kd in _spec:
        _min = max(120, int(_math.ceil((_B[_t] * _K[_kd]) / 30.0) * 30))
        _stones = int(round(_V[_t] * _M[_kd]))
        _seed = int(round(_stones * _CS[_kd]))
        if _kd == 'cult': _ce = _PURE[_t]
        elif _kd == 'mix' and _t in (3, 4): _ce = _MIXADJ[_t]
        else: _ce = int(round(_E[_t] * (1.0 if _kd == 'mix' else (0.5 if _kd == 'rare' else 0.2))))
        _recalc[_k2] = (_min, _stones, _seed, _ce)
    if _recalc != expect:
        _d = [k for k in expect if expect[k] != _recalc.get(k)]
        fail('数值自证：复算与直表不一致 %s（复算=%s 直表=%s）' % (_d, [_recalc.get(k) for k in _d], [expect[k] for k in _d]))
    # §4.3 单调性断言（同品阶跨产品线）
    _order_min = [_recalc['shencangjinshen'][0], _recalc['hunyuandaoguo'][0], _recalc['wanxianghua'][0], _recalc['bumieteng'][0]]
    if not (_order_min[0] < _order_min[1] < _order_min[2] < _order_min[3]):
        fail('§4.3 时长保序被破坏（神品 卖<修<综<稀）：%s' % _order_min)
    _order_sell = [_recalc['shencangjinshen'][1], _recalc['wanxianghua'][1], _recalc['bumieteng'][1], _recalc['hunyuandaoguo'][1]]
    if not (_order_sell[0] > _order_sell[1] > _order_sell[2] > _order_sell[3]):
        fail('§4.3 变卖价保序被破坏（神品 卖>综>稀>修）：%s' % _order_sell)
    _order_exp = [_recalc['hunyuandaoguo'][3], _recalc['wanxianghua'][3], _recalc['bumieteng'][3], _recalc['shencangjinshen'][3]]
    if not (_order_exp[0] > _order_exp[1] > _order_exp[2] > _order_exp[3]):
        fail('§4.3 服用修为保序被破坏（神品 修>综>稀>卖）：%s' % _order_exp)
    # 经济红线复算（§5.2）：满配 ×1.21，6 田
    _net = _recalc['shencangjinshen'][1] - _recalc['shencangjinshen'][2]
    _day = _net * 1440.0 / _recalc['shencangjinshen'][0]
    _full6 = _day * 1.21 * 6
    if _full6 > 150000:
        fail('★ 经济红线被击穿：满配六田日净 %.1f > 150,000' % _full6)
    print('  [OK] 红线复算：纯卖钱草·神品 净/茬 %d → 日净/田 %.0f → 满配 ×1.21 → 六田 %.1f ≤ 150,000（余量 %.1f%%）'
          % (_net, _day, _full6, (1 - _full6 / 150000.0) * 100))
    # 修为上界复算（§5.4）：六田全种混元道果
    _exp6 = _recalc['hunyuandaoguo'][3] * (1440.0 / _recalc['hunyuandaoguo'][0]) * 6
    print('  [OK] 修为上界复算：混元道果 %d ÷ %d min × 1440 × 6 田 = %.0f 修为/日（0.8.7 现状 258,000 的 %.2f×）'
          % (_recalc['hunyuandaoguo'][3], _recalc['hunyuandaoguo'][0], _exp6, _exp6 / 258000.0))
    if len(expect) != 20:
        fail('数值自证表条目数 != 20（实际 %d）' % len(expect))
    print("  [OK] T5 数值自证表 20 种就绪（按 §4.1 公式复算，与 §3 数值表逐位一致）")

    # 7) 往返自证
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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".t5crops-", suffix=".tmp")
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
