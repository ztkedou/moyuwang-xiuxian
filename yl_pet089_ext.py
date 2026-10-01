# -*- coding: utf-8 -*-
r"""
yl_pet089_ext.py — 0.8.9 T2 灵宠玩法扩展 · 客户端补丁（T2 客户端归属）

接线信息（0.8.9 build-plan 落表用）
--------------------------------------------------------------------------
  模块名 pet089；V28_MODULES 插在 forge088 之后、numbal 之前（numbal 恒最后）。
  apply(p, ctx)：p = yl_patch.Patcher；ctx['zh'] = 中文转 \uXXXX。
  ctx['base_text'] = 冻结基座原文（用于「无附带改动」自查）。

靶点与锚点（全部实测确认，非策划案行号）
--------------------------------------------------------------------------
  A1 秘径消耗（灵兽秘径 = handlePetExpedition，bundle @1567794 区）
      灵石: floor(3e4 + _*45e3 + k.evolutionStage*9e4)   → round100(10000 × P品阶 × P阶段 × P亲密)
      气血: max(200, floor(d.maxHp*(.18 + stage*.07)))    → max(100, floor(maxHp*(.11 + stage*.04)))
      修为: max(100, floor(d.maxExp*(.008 + stage*.004))) → max(50,  floor(maxExp*(.005 + stage*.0025)))
  A2 秘径按钮 title/💰 显示同套公式（两处 JSX：pc 端 / 移动端各一）
  A3 灵宠面板 vM 包装：jM=Rt.memo(vM) → jM=Rt.memo(YlxwPetShell)（新增「融合」页签 + 出战/助战栏）
  A4 角色面板灵宠加成行（YlxwStatExtras 后置包裹：显示主战/助战加成数字）
  A5 妖灵归位客户端动作（YlxwMergeSpiritAway，写 player.pets + activePetId）

★ 零改动区（硬红线）
--------------------------------------------------------------------------
  · 灵兽远征派遣（YlxwExpStart 的 var _expCost = 20000;）—— 一行不动
  · 战斗结算核心 Oy —— 不碰（仅在其上加「灵宠加成」消费入口）
  · 不改 T10 灵田环 / T5 actApplyGain 挂点区

服务端依赖（本模块只做客户端一半，服务端需求另行列出）
--------------------------------------------------------------------------
  S1  GET  /api/pet/spirit/list   读仙务·妖灵列表（id/name/rarity/hunger/bond/merged）
  S2  POST /api/pet/spirit/merge  标记 merged=1（幂等），返回该妖灵快照
  S3  ALTER TABLE pets ADD COLUMN merged INTEGER DEFAULT 0
  若 S1/S2 未就绪：客户端动作按钮仍渲染，点击后 toast 提示「服务端未就绪」（400/409 走既有 Je 通道），
  不阻塞其余 T2 功能（秘径消耗 / 融合 / 出战加成均为纯客户端存档域）。
"""  # noqa: E501
import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-0.8.9 T2: 灵宠玩法扩展（秘径消耗重构 / 出战助战加成 / 融合 / 妖灵归位） =====
   用户 2026-09-29 拍板：秘径基础 10000 灵石起、品阶为主、亲密度影响 ≤5%、总极差 2.0×；
   气血/修为同步下调至现行 ~60%；主战 50% / 助战 15%（洞府 Lv3/Lv6）；融合纯灵石、保持物种、失败保底。
   本块只做客户端存档域（player.pets），不改任何服务端权威口径。 */

/* ---------- T2 系数表（与策划案 §3.1/§2.3 逐位一致；两套系数用途不同，刻意不共用） ---------- */
var YLXW_PET_RARITY = ["普通", "稀有", "传说", "仙品"];
/* 秘径消耗系数（压缩系数：品阶跨度 1.6× > 阶段 1.25× > 亲密 1.05×） */
var YLXW_PET_COST_RARITY = { "普通": 1.00, "稀有": 1.20, "传说": 1.40, "仙品": 1.60 };
var YLXW_PET_COST_STAGE = [1.00, 1.10, 1.25];
/* 属性加成系数（拉开品阶差距，体现养成价值：品阶跨度 2.2×） */
var YLXW_PET_BONUS_RARITY = { "普通": 1.0, "稀有": 1.2, "传说": 1.6, "仙品": 2.2 };
var YLXW_PET_BONUS_STAGE = [1.0, 1.2, 1.5];
/* 出战栏位：主战 1（默认） + 助战 2（洞府 Lv3 / Lv6） */
var YLXW_PET_LANES = [
  { key: "main", label: "主战宠", rate: 0.50, grottoLevel: 0 },
  { key: "aid1", label: "助战位 1", rate: 0.15, grottoLevel: 3 },
  { key: "aid2", label: "助战位 2", rate: 0.15, grottoLevel: 6 }
];
/* 融合费：3000 × K品阶(主宠) × (1 + 副宠品阶序号) */
var YLXW_PET_FUSE_BASE = 3000;

/* ---------- T2 纯函数（可 Node 求值自证；全部防御式，NaN/undefined 一律安全返回） ---------- */

/* 品阶安全化：未知品阶一律按「普通」处理（防 NaN 污染存档） */
function YlxwPetRarityOf(r) {
  var s = String(r == null ? "" : r);
  return YLXW_PET_BONUS_RARITY[s] != null ? s : "\u666e\u901a";
}
/* 阶段安全化：0/1/2 之外一律钳到区间 */
function YlxwPetStageOf(s) {
  var n = Math.floor(Number(s) || 0);
  return n < 0 ? 0 : (n > 2 ? 2 : n);
}
/* 亲密度安全化：0~100 */
function YlxwPetAffectionOf(a) {
  var n = Number(a) || 0;
  return n < 0 ? 0 : (n > 100 ? 100 : n);
}
/* round100：取整到百位（四舍五入，≥50 进） */
function YlxwPetRound100(v) {
  var n = Number(v) || 0;
  return Math.max(0, Math.round(n / 100) * 100);
}
/* 秘径灵石消耗 = round100(7500 × P品阶 × P阶段 × (1 + 亲密度/2000))
   ★ 0.8.10 2b：基础由 10000 下调为 **7500**（用户 2026-09-30 要求）。
     品阶/阶段/亲密三因子不变 ⇒ 同比例下调 25%（普通幼年 10000 → 7500）。
   范围 7,500（普通·幼年·亲密 0）~ 15,750（仙品·完全体·亲密 100），极差 2.1× */
function YlxwPetPathCost(pet) {
  var r = YlxwPetRarityOf(pet && pet.rarity);
  var st = YlxwPetStageOf(pet && pet.evolutionStage);
  var af = YlxwPetAffectionOf(pet && pet.affection);
  return YlxwPetRound100(7500 * YLXW_PET_COST_RARITY[r] * YLXW_PET_COST_STAGE[st] * (1 + af / 2000));
}
/* 秘径气血消耗 = max(100, floor(maxHp × (0.11 + 阶段×0.04)))  （现行 0.18/0.25/0.32 → ~60%） */
function YlxwPetPathHp(maxHp, stage) {
  var st = YlxwPetStageOf(stage);
  return Math.max(100, Math.floor((Number(maxHp) || 0) * (0.11 + st * 0.04)));
}
/* 秘径修为消耗 = max(50, floor(maxExp × (0.005 + 阶段×0.0025)))（现行 0.008/0.012/0.016 → 62.5%） */
function YlxwPetPathExp(maxExp, stage) {
  var st = YlxwPetStageOf(stage);
  return Math.max(50, Math.floor((Number(maxExp) || 0) * (0.005 + st * 0.0025)));
}
/* 主人加成（单属性）= floor(宠物属性 × 转化率 × K品阶 × K阶段 × (1 + 亲密度/200)) */
function YlxwPetBonusOne(value, rate, rarity, stage, affection) {
  var r = YlxwPetRarityOf(rarity);
  var st = YlxwPetStageOf(stage);
  var af = YlxwPetAffectionOf(affection);
  return Math.floor((Number(value) || 0) * rate * YLXW_PET_BONUS_RARITY[r] * YLXW_PET_BONUS_STAGE[st] * (1 + af / 200));
}
/* 亲密度每满 25 点给主人 暴击 +0.5% / 闪避 +0.4%（上限 亲密 100 → 暴击 +2% / 闪避 +1.6%） */
function YlxwPetBonusCrit(affection) {
  return YlxwPetAffectionOf(affection) >= 0 ? Math.floor(YlxwPetAffectionOf(affection) / 25) * 0.005 : 0;
}
function YlxwPetBonusDodge(affection) {
  return YlxwPetAffectionOf(affection) >= 0 ? Math.floor(YlxwPetAffectionOf(affection) / 25) * 0.004 : 0;
}
/* 融合费 = 3000 × K品阶(主宠) × (1 + 副宠品阶序号) */
function YlxwPetFuseCost(mainPet, subPet) {
  var mr = YlxwPetRarityOf(mainPet && mainPet.rarity);
  var si = YLXW_PET_RARITY.indexOf(YlxwPetRarityOf(subPet && subPet.rarity));
  if (si < 0) si = 0;
  return Math.round(YLXW_PET_FUSE_BASE * YLXW_PET_BONUS_RARITY[mr] * (1 + si));
}
/* 融合成功率：副 < 主 → 70% + 15%×差（≤100%）；= → 70%；> → 70% − 20%×差（≥20%） */
function YlxwPetFuseRate(mainPet, subPet) {
  var mi = YLXW_PET_RARITY.indexOf(YlxwPetRarityOf(mainPet && mainPet.rarity));
  var si = YLXW_PET_RARITY.indexOf(YlxwPetRarityOf(subPet && subPet.rarity));
  if (mi < 0) mi = 0;
  if (si < 0) si = 0;
  var d = si - mi, p;
  if (d < 0) p = 0.70 + 0.15 * (-d);
  else if (d === 0) p = 0.70;
  else p = 0.70 - 0.20 * d;
  return Math.max(0.20, Math.min(1.00, p));
}
/* 出战宠是否被远征占用（status !== "claimed" 视为占用，一宠不可多吃） */
function YlxwPetIsBusy(player, petId) {
  try {
    var g = (player && player.grotto) || {};
    var cur = g.petExpeditions || [];
    for (var i = 0; i < cur.length; i++) {
      var e = cur[i];
      if (e && e.petId === petId && String(e.status || "") !== "claimed") return true;
    }
  } catch (err) {}
  return false;
}
/* 洞府等级（安全读取） */
function YlxwPetGrottoLevel(player) {
  try { return Math.max(0, Math.floor(Number(player && player.grotto && player.grotto.level) || 0)); } catch (err) { return 0; }
}
/* 某栏位是否已解锁 */
function YlxwPetLaneUnlocked(player, lane) {
  return YlxwPetGrottoLevel(player) >= (lane ? YlxwPetLaneUnlockedLevel(lane) : 0);
}
function YlxwPetLaneUnlockedLevel(lane) {
  var need = 0, i;
  for (i = 0; i < YLXW_PET_LANES.length; i++) { if (YLXW_PET_LANES[i].key === (lane && lane.key)) need = YLXW_PET_LANES[i].grottoLevel; }
  return need;
}

/* ---------- T2 出战/助战加成汇总（供角色面板可见化） ---------- */
/* 取三个栏位的实际宠（main = activePetId；aid1/aid2 = player.petAidIds[]，缺省空） */
function YlxwPetLanePets(player) {
  var out = [], i;
  var pets = (player && player.pets) || [];
  var aid = (player && player.petAidIds) || [];
  var mainId = player && player.activePetId;
  for (i = 0; i < YLXW_PET_LANES.length; i++) {
    var lane = YLXW_PET_LANES[i];
    var pid = lane.key === "main" ? mainId : aid[i - 1];
    var pet = null, k;
    for (k = 0; k < pets.length; k++) { if (pets[k] && pets[k].id === pid) pet = pets[k]; }
    out.push({ lane: lane, pet: pet, unlocked: YlxwPetGrottoLevel(player) >= lane.grottoLevel });
  }
  return out;
}
/* 汇总加成对象：attack/defense/maxHp/speed 为绝对值，critRate/dodgeRate 为小数百分比 */
function YlxwPetBonusTotal(player) {
  var o = { attack: 0, defense: 0, maxHp: 0, speed: 0, critRate: 0, dodgeRate: 0, lanes: [] };
  var lanes = YlxwPetLanePets(player), i;
  for (i = 0; i < lanes.length; i++) {
    var L = lanes[i];
    if (!L.pet || !L.unlocked) continue;
    var st = L.pet.stats || {};
    var f = [L.lane.rate, L.pet.rarity, L.pet.evolutionStage, L.pet.affection];
    o.attack += YlxwPetBonusOne(st.attack, f[0], f[1], f[2], f[3]);
    o.defense += YlxwPetBonusOne(st.defense, f[0], f[1], f[2], f[3]);
    o.maxHp += YlxwPetBonusOne(st.hp, f[0], f[1], f[2], f[3]);
    o.speed += YlxwPetBonusOne(st.speed, f[0], f[1], f[2], f[3]);
    o.critRate += YlxwPetBonusCrit(L.pet.affection);
    o.dodgeRate += YlxwPetBonusDodge(L.pet.affection);
    o.lanes.push({ key: L.lane.key, name: L.pet.name || "", rate: L.lane.rate });
  }
  return o;
}

/* ---------- T2 角色面板 · 灵宠加成行（在 YlxwStatExtras 之后包裹，展示具体数字） ---------- */
/* 必须在 YlxwStatExtras 定义之后运行（Patcher 锚点保证），此处只声明包装函数。 */
function YlxwPetStatRow(p) {
  var t;
  try { t = YlxwPetBonusTotal(p); } catch (e) { t = null; }
  if (!t || t.lanes.length === 0) return null;
  var main = t.lanes[0];
  var names = [];
  var i;
  for (i = 0; i < t.lanes.length; i++) names.push(t.lanes[i].name);
  var parts = [];
  if (main) parts.push("\u4e3b\u6218\uff1a" + (main.name || "\u65e0"));
  for (i = 1; i < t.lanes.length; i++) parts.push("\u52a9\u6218\uff1a" + (t.lanes[i].name || "\u65e0"));
  var rows = [];
  rows.push(e.jsx("span", { className: "text-amber-300", children: "\u7075\u5ba0\u52a0\u6210" }, "pt"));
  rows.push(e.jsx("span", { children: "\u653b\u51fb +" + t.attack }, "pa"));
  rows.push(e.jsx("span", { children: "\u9632\u5fa1 +" + t.defense }, "pd"));
  rows.push(e.jsx("span", { children: "\u6c14\u8840 +" + t.maxHp }, "ph"));
  rows.push(e.jsx("span", { children: "\u901f\u5ea6 +" + t.speed }, "ps"));
  if (t.critRate > 0) rows.push(e.jsx("span", { children: "\u66b4\u51fb +" + (t.critRate * 100).toFixed(1) + "%" }, "pc"));
  if (t.dodgeRate > 0) rows.push(e.jsx("span", { children: "\u95ea\u907f +" + (t.dodgeRate * 100).toFixed(1) + "%" }, "po"));
  return e.jsxs("div", { className: "text-xs text-stone-300 flex flex-wrap gap-x-2 gap-y-0.5 bg-ink-800/60 border border-stone-700 rounded px-2 py-1.5", children: [
    e.jsx("span", { className: "text-stone-400", children: parts.join(" \u00b7 ") }),
    e.jsx("span", { className: "w-full" }),
    rows
  ] });
}

/* ---------- T2 融合页签（新增；纯灵石 / 保持主宠物种 / 失败保底 pet.fusePity） ---------- */
function YlxwPetFuseTab(props) {
  var player = props.player || {};
  var pets = player.pets || [];
  var st = O.useState(null), mainId = st[0], setMain = st[1];
  var st2 = O.useState(null), subId = st2[0], setSub = st2[1];
  var mainPet = null, subPet = null, i;
  for (i = 0; i < pets.length; i++) {
    if (pets[i] && pets[i].id === mainId) mainPet = pets[i];
    if (pets[i] && pets[i].id === subId) subPet = pets[i];
  }
  var cost = mainPet && subPet ? YlxwPetFuseCost(mainPet, subPet) : 0;
  var rate = mainPet && subPet ? YlxwPetFuseRate(mainPet, subPet) : 0;
  var pity = Math.max(0, Math.floor(Number((mainPet && mainPet.fusePity) || 0)));
  var canFuse = !!(mainPet && subPet && mainPet.id !== subPet.id && !YlxwPetIsBusy(player, subId));
  var have = YlxwNum(player.spiritStones);
  var enough = have >= cost;

  var pickRow = function (pet, sel, onPick) {
    return e.jsx(YlxwBtn, { tone: sel ? "solid" : "ghost", onClick: onPick,
      children: (pet.name || "") + " \u00b7 " + YlxwPetRarityOf(pet.rarity) + " \u00b7 Lv." + YlxwNum(pet.level) }, pet.id);
  };
  return e.jsxs(YlxwPanel, { children: [
    e.jsx("div", { className: "text-xs text-stone-400", children: "\u4e3b\u5ba0\u4fdd\u7559\u3001\u526f\u5ba0\u6d88\u8017\uff0c\u53e6\u4ed8\u878d\u5408\u8d39\uff1b\u4fdd\u6301\u4e3b\u5ba0\u7269\u79cd\uff0c\u4e0d\u8de8\u7269\u79cd\u3002\u8fde\u7eed\u5931\u8d25 3 \u6b21\u540e\u7b2c 4 \u6b21\u5fc5\u6210\u529f\u3002" }),
    e.jsx(YlxwKv, { data: { "\u878d\u5408\u8d39": YlxwNum(cost) + " \u7075\u77f3", "\u6210\u529f\u7387": Math.round(rate * 100) + "%", "\u4fdd\u5e95\u8ba1\u6570": pity + " / 3", "\u5f53\u524d\u7075\u77f3": YlxwNum(have) } }),
    e.jsx("div", { className: "text-xs text-amber-300 pt-1", children: "\u4e3b\u5ba0\uff08\u4fdd\u7559\uff09" }),
    e.jsx("div", { className: "flex flex-wrap gap-1.5", children: pets.map(function (p) { return pickRow(p, p.id === mainId, function () { setMain(p.id); if (subId === p.id) setSub(null); }); }) }),
    e.jsx("div", { className: "text-xs text-amber-300 pt-1", children: "\u526f\u5ba0\uff08\u6d88\u8017\uff09" }),
    e.jsx("div", { className: "flex flex-wrap gap-1.5", children: pets.filter(function (p) { return p.id !== mainId; }).map(function (p) { return pickRow(p, p.id === subId, function () { setSub(p.id); }); }) }),
    e.jsx(YlxwBtn, { disabled: !canFuse || !enough, onClick: function () { props.onFuse(mainId, subId, cost, rate); },
      children: !canFuse ? "\u8bf7\u9009\u62e9\u4e3b\u5ba0\u4e0e\u526f\u5ba0" : (!enough ? "\u7075\u77f3\u4e0d\u8db3\uff08\u9700 " + YlxwNum(cost) + "\uff09" : "\u878d\u5408\uff08" + YlxwNum(cost) + " \u7075\u77f3\uff0c" + Math.round(rate * 100) + "%\uff09") }),
    e.jsxs("details", { className: "text-xs text-stone-400", children: [
      e.jsx("summary", { children: "\u878d\u5408\u89c4\u5219" }),
      e.jsxs("div", { className: "space-y-1 pt-1.5", children: [
        e.jsx("div", { children: "\u00b7 \u526f\u5ba0\u54c1\u9636\u8d8a\u4f4e\u8d8a\u7a33\uff08\u6700\u9ad8 100%\uff09\uff0c\u8d8a\u9ad8\u8d8a\u9669\uff08\u6700\u4f4e 20%\uff09\u3002" }),
        e.jsx("div", { children: "\u00b7 \u6210\u529f\uff1a\u7b49\u7ea7\u53d6\u9ad8\u3001\u4eb2\u5bc6\u5ea6\u53d6\u9ad8\u3001\u7ee7\u627f\u526f\u5ba0\u72ec\u6709\u6280\u80fd\uff1b\u526f\u5ba0\u54c1\u9636\u66f4\u9ad8\u65f6\u6709\u673a\u4f1a\u5347\u54c1\u9636/\u9636\u6bb5\u3002" }),
        e.jsx("div", { children: "\u00b7 \u5931\u8d25\uff1a\u526f\u5ba0\u6d88\u5931\uff0c\u4e3b\u5ba0\u4e0d\u53d7\u635f\u3002\u8fde\u7eed\u5931\u8d25 3 \u6b21\uff0c\u7b2c 4 \u6b21\u5fc5\u5b9a\u6210\u529f\u3002" })
      ] })
    ] })
  ] });
}

/* ---------- T2 灵宠面板外壳：包裹原 vM（替代其 memo 包装行），加「我的灵宠 / 融合」页签 ---------- */
/* 设计：不改原 vM 一行（30KB 巨型组件），仅在其外层加页签壳 + 出战/助战栏 + 融合页。 */
function YlxwPetShell(p) {
  var st = O.useState("list"), tab = st[0], setTab = st[1];
  var player = (p && p.player) || {};
  var bond = Be(function (s) { return s.player; });
  var doToast = function (msg, tone) { try { Je(msg); } catch (e) {} };
  /* 融合执行：纯客户端存档域（player.pets + spiritStones），失败保底 fusePity 落存档。 */
  var onFuse = function (mainId, subId, cost, rate) {
    if (!mainId || !subId || mainId === subId) return;
    Be.setState(function (s) {
      if (!s || !s.player) return s;
      var pl = s.player;
      if (YlxwNum(pl.spiritStones) < cost) return s;
      var pets = (pl.pets || []).slice();
      var mi = -1, si = -1, i;
      for (i = 0; i < pets.length; i++) {
        if (pets[i].id === mainId) mi = i;
        if (pets[i].id === subId) si = i;
      }
      if (mi < 0 || si < 0 || mi === si) return s;
      var mp = pets[mi], sp = pets[si];
      var pity = Math.max(0, Math.floor(Number(mp.fusePity) || 0));
      var forced = pity >= 3;
      var ok = forced || Math.random() < rate;
      var next = { text: "", tone: "gain" };
      if (ok) {
        /* 成功：等级取高、亲密度取高、物种保持主宠、继承副宠独有技能（上限 6） */
        var skills = (mp.skills || []).slice();
        var ss = sp.skills || [], k;
        for (k = 0; k < ss.length && skills.length < 6; k++) {
          var has = false, q;
          for (q = 0; q < skills.length; q++) { if (skills[q] && ss[k] && skills[q].id === ss[k].id) has = true; }
          if (!has) skills.push(ss[k]);
        }
        var mrIdx = YLXW_PET_RARITY.indexOf(YlxwPetRarityOf(mp.rarity));
        var srIdx = YLXW_PET_RARITY.indexOf(YlxwPetRarityOf(sp.rarity));
        var newRarity = mp.rarity;
        if (srIdx > mrIdx && Math.random() < 0.25 * (srIdx - mrIdx)) {
          newRarity = YLXW_PET_RARITY[Math.min(YLXW_PET_RARITY.length - 1, mrIdx + 1)];
        }
        var newStage = YlxwPetStageOf(mp.evolutionStage);
        if (newStage < 2 && YlxwPetStageOf(sp.evolutionStage) >= newStage && Math.random() < 0.30) newStage += 1;
        var merged = Object.assign({}, mp, {
          rarity: newRarity,
          level: Math.max(YlxwNum(mp.level), YlxwNum(sp.level)),
          evolutionStage: newStage,
          affection: Math.max(YlxwPetAffectionOf(mp.affection), YlxwPetAffectionOf(sp.affection)),
          skills: skills,
          fusePity: 0
        });
        pets[mi] = merged;
        pets.splice(si, 1);
        next.text = "\u878d\u5408\u6210\u529f\uff01\u3010" + (merged.name || "") + "\u3011\u54c1\u9636 " + YlxwPetRarityOf(newRarity) + "\u3001\u9636\u6bb5 " + newStage;
      } else {
        pets[mi] = Object.assign({}, mp, { fusePity: pity + 1 });
        pets.splice(si, 1);
        next.text = "\u878d\u5408\u5931\u8d25\uff0c\u526f\u5ba0\u5df2\u6d88\u6563\uff08\u4fdd\u5e95 " + (pity + 1) + " / 3\uff09";
        next.tone = "danger";
      }
      doToast(next.text, next.tone);
      return Object.assign({}, s, { player: Object.assign({}, pl, { pets: pets, spiritStones: Math.max(0, YlxwNum(pl.spiritStones) - cost) }) });
    });
    try { YlxwDirty(); } catch (e) {}
  };

  if (tab === "fuse") {
    return e.jsxs(e.Fragment, { children: [
      PetTabBar(tab, setTab),
      e.jsx(YlxwPetFuseTab, { player: player, onFuse: onFuse })
    ] });
  }
  return e.jsxs(e.Fragment, { children: [
    PetTabBar(tab, setTab),
    e.jsx(YlxwPetLaneBar, { player: bond || player }),
    e.jsx(vM, p)
  ] });
}
/* 页签条（我的灵宠 / 融合） */
function PetTabBar(tab, setTab) {
  var mk = function (key, label) {
    return e.jsx(YlxwBtn, { tone: tab === key ? "solid" : "ghost", onClick: function () { setTab(key); }, children: label }, key);
  };
  return e.jsxs("div", { className: "flex items-center gap-1.5 pb-2", children: [mk("list", "\u6211\u7684\u7075\u5ba0"), mk("fuse", "\u878d\u5408")] });
}
/* 出战 / 助战栏提示（洞府 Lv3 / Lv6 解锁；远征中的宠不可出战） */
function YlxwPetLaneBar(props) {
  var player = props.player || {};
  var lanes = YlxwPetLanePets(player);
  return e.jsxs("div", { className: "text-xs text-stone-400 bg-ink-800/60 border border-stone-700 rounded px-2 py-1.5 space-y-1", children: [
    e.jsx("div", { className: "text-amber-300", children: "\u51fa\u6218 / \u52a9\u6218\uff08\u52a0\u6210\u76f4\u63a5\u8ba1\u5165\u4f60\u7684\u5c5e\u6027\uff0c\u89d2\u8272\u9762\u677f\u53ef\u89c1\uff09" }),
    lanes.map(function (L) {
      return e.jsxs("div", { className: "flex items-center justify-between gap-2", children: [
        e.jsx("span", { children: L.lane.label + "\uff08\u8f6c\u5316 " + Math.round(L.lane.rate * 100) + "%\uff09" }),
        e.jsx("span", { children: L.unlocked ? (L.pet ? (L.pet.name || "") + (YlxwPetIsBusy(player, L.pet.id) ? " \u00b7 \u8fdc\u5f81\u4e2d" : "") : "\u672a\u6302\u7075\u5ba0") : "\u9700\u6d1e\u5e9c Lv." + L.lane.grottoLevel })
      ] }, L.lane.key);
    })
  ] });
}

/* ---------- T2 妖灵归位（服务端妖灵 → 客户端灵宠；一次性写入，不做双向同步） ---------- */
/* 映射：rarity 凡→普通 / 灵→稀有 / 仙→仙品；hunger/100 → level；亲密度 = min(100, floor(bond/2)) */
var YLXW_PET_SPIRIT_MAP = { "\u51e1": "\u666e\u901a", "\u7075": "\u7a00\u6709", "\u4f20": "\u4f20\u8bf4", "\u4ed9": "\u4ed9\u54c1" };
function YlxwSpiritToPet(sp, speciesPool) {
  var raw = String((sp && sp.rarity) || "");
  var mapped = YLXW_PET_SPIRIT_MAP[raw] || (YLXW_PET_BONUS_RARITY[raw] ? raw : "\u666e\u901a");
  var pool = (speciesPool || []).filter(function (s) { return YlxwPetRarityOf(s.rarity) === mapped; });
  if (pool.length === 0) pool = speciesPool || [];
  var pick = pool.length ? pool[Math.floor(Math.random() * pool.length)] : null;
  var lv = Math.max(1, Math.min(100, Math.floor((Number(sp && sp.hunger) || 0) / 100) || 1));
  var aff = Math.min(100, Math.max(0, Math.floor((Number(sp && sp.bond) || 0) / 2)));
  return {
    id: "pet-spirit-" + St(),
    name: (sp && sp.name) || (pick && pick.name) || "\u5996\u7075",
    species: pick ? pick.species : "\u7075\u517d",
    rarity: mapped,
    level: lv,
    exp: 0,
    maxExp: 100,
    evolutionStage: 0,
    affection: aff,
    stats: pick ? (j(pick.species, 1, 0) || pick.baseStats || { attack: 50, defense: 25, hp: 500, speed: 30 }) : { attack: 50, defense: 25, hp: 500, speed: 30 },
    skills: (pick && pick.skills) || [],
    fusePity: 0,
    spiritId: (sp && sp.id) || null
  };
}
function YlxwMergeSpiritAway(sp) {
  var ok = false;
  try {
    Be.setState(function (s) {
      if (!s || !s.player) return s;
      var pl = s.player;
      var pet = YlxwSpiritToPet(sp, rn);
      var pets = (pl.pets || []).slice();
      pets.push(pet);
      ok = true;
      return Object.assign({}, s, { player: Object.assign({}, pl, { pets: pets, activePetId: pl.activePetId || pet.id }) });
    });
  } catch (e) {}
  return ok;
}
'''


# --------------------------------------------------------------------------- 门禁/替换定义

# A1 秘径消耗三公式（handlePetExpedition 内，实测 @1567794 区）
A1_ANCHOR = (
    'const _=Math.max(0,fe.indexOf(d.realm)),C=Math.floor(3e4+_*45e3+k.evolutionStage*9e4),'
    'g=Math.max(200,Math.floor(d.maxHp*(.18+k.evolutionStage*.07))),'
    'q=Math.max(100,Math.floor(d.maxExp*(.008+k.evolutionStage*.004)));'
)
A1_REPL = (
    'const _=Math.max(0,fe.indexOf(d.realm)),'
    'C=YlxwPetPathCost(k),'
    'g=YlxwPetPathHp(d.maxHp,k.evolutionStage),'
    'q=YlxwPetPathExp(d.maxExp,k.evolutionStage);'
)
# A2 秘径按钮显示（两处：PC @1402509 / 移动 @1409753；replace expect=2）
A2_ANCHOR = (
    '${Math.floor(3e4+Math.max(0,fe.indexOf(a.realm))*45e3+I.evolutionStage*9e4)} '
    '\u7075\u77f3 + ${Math.max(200,Math.floor(a.maxHp*(.18+I.evolutionStage*.07)))} '
    '\u6c14\u8840 + ${Math.max(100,Math.floor(a.maxExp*(.008+I.evolutionStage*.004)))} \u4fee\u4e3a'
)
A2_REPL = (
    '${YlxwPetPathCost(I)} '
    '\u7075\u77f3 + ${YlxwPetPathHp(a.maxHp,I.evolutionStage)} '
    '\u6c14\u8840 + ${YlxwPetPathExp(a.maxExp,I.evolutionStage)} \u4fee\u4e3a'
)
# 移动端那条（变量名 P / 略不同）：单独一条
A2B_ANCHOR = (
    '${Math.floor(3e4+Math.max(0,fe.indexOf(a.realm))*45e3+P.evolutionStage*9e4)} '
    '\u7075\u77f3 + ${Math.max(200,Math.floor(a.maxHp*(.18+P.evolutionStage*.07)))} '
    '\u6c14\u8840 + ${Math.max(100,Math.floor(a.maxExp*(.008+P.evolutionStage*.004)))} \u4fee\u4e3a'
)
A2B_REPL = (
    '${YlxwPetPathCost(P)} '
    '\u7075\u77f3 + ${YlxwPetPathHp(a.maxHp,P.evolutionStage)} '
    '\u6c14\u8840 + ${YlxwPetPathExp(a.maxExp,P.evolutionStage)} \u4fee\u4e3a'
)
# 💰 徽标（两处同形态，变量 I / P）
A2C_ANCHOR = '["\U0001f4b0",Math.floor(3e4+Math.max(0,fe.indexOf(a.realm))*45e3+I.evolutionStage*9e4)]'
A2C_REPL = '["\U0001f4b0",YlxwPetPathCost(I)]'
A2D_ANCHOR = '["\U0001f4b0",Math.floor(3e4+Math.max(0,fe.indexOf(a.realm))*45e3+P.evolutionStage*9e4)]'
A2D_REPL = '["\U0001f4b0",YlxwPetPathCost(P)]'


def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('pet089 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 注入 T2 函数与组件块（锚在 YlxwPanelModal 之前：此后 YlxwPanet/VlxwBtn/rn/j/St/Be/Je 均已定义）
    p.insert_before('pet089-block', 'function YlxwPanelModal(p) {', blk + '\n',
                    expect=1, note='注入 T2 灵宠扩展（秘径消耗/出战加成/融合/妖灵归位）')

    # 1) A1 秘径三公式（handlePetExpedition）
    p.replace('pet089-path-cost', A1_ANCHOR, A1_REPL, expect=1,
              note='秘径灵石/气血/修为三项消耗改为 T2 新公式')

    # 2) A2 秘径按钮 title（PC + 移动两条）
    p.replace('pet089-btn-pc', A2_ANCHOR, A2_REPL, expect=1, note='秘径按钮 title 消耗（PC）')
    p.replace('pet089-btn-mb', A2B_ANCHOR, A2B_REPL, expect=1, note='秘径按钮 title 消耗（移动）')
    p.replace('pet089-coin-pc', A2C_ANCHOR, A2C_REPL, expect=1, note='秘径 💰 徽标（PC）')
    p.replace('pet089-coin-mb', A2D_ANCHOR, A2D_REPL, expect=1, note='秘径 💰 徽标（移动）')

    # 3) A3 灵宠面板包装（jM=Rt.memo(vM) → jM=Rt.memo(YlxwPetShell)）
    p.replace('pet089-shell', 'jM=Rt.memo(vM)', 'jM=Rt.memo(YlxwPetShell)', expect=1,
              note='灵宠面板外层包 YlxwPetShell（加「融合」页签 + 出战/助战栏；原 vM 零改动）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- 秘径消耗（A1/A2）----
        ('T2·秘径成本改用 YlxwPetPathCost', 'C=YlxwPetPathCost(k),', 1, '==', ''),
        ('T2·秘径气血改用 YlxwPetPathHp', 'g=YlxwPetPathHp(d.maxHp,k.evolutionStage),', 1, '==', ''),
        ('T2·秘径修为改用 YlxwPetPathExp', 'q=YlxwPetPathExp(d.maxExp,k.evolutionStage);', 1, '==', ''),
        ('T2·旧秘径灵石公式清零', 'Math.floor(3e4+_*45e3+k.evolutionStage*9e4)', 0, '==', '原式必须彻底消失'),
        ('T2·旧气血系数清零', '.18+k.evolutionStage*.07', 0, '==', ''),
        ('T2·旧修为系数清零', '.008+k.evolutionStage*.004', 0, '==', ''),
        ('T2·旧秘径按钮式清零', 'Math.floor(3e4+Math.max(0,fe.indexOf(a.realm))*45e3', 0, '==', 'title+徽标共 4 处全改'),
        # ---- 纯函数就位 ----
        ('T2·YlxwPetPathCost 定义', 'function YlxwPetPathCost(', 1, '==', ''),
        # —— 0.8.10 2b：秘径基础 10000 → 7500 ——
        ('2b·秘径基础 7500', 'YlxwPetRound100(7500 * YLXW_PET_COST_RARITY[r]', 1, '==', ''),
        ('2b·旧基础 10000 已清零', 'YlxwPetRound100(10000 * YLXW_PET_COST_RARITY[r]', 0, '==', '必须为 0'),
        ('T2·YlxwPetPathHp 定义', 'function YlxwPetPathHp(', 1, '==', ''),
        ('T2·YlxwPetPathExp 定义', 'function YlxwPetPathExp(', 1, '==', ''),
        ('T2·YlxwPetBonusOne 定义', 'function YlxwPetBonusOne(', 1, '==', ''),
        ('T2·YlxwPetFuseCost 定义', 'function YlxwPetFuseCost(', 1, '==', ''),
        ('T2·YlxwPetFuseRate 定义', 'function YlxwPetFuseRate(', 1, '==', ''),
        ('T2·YlxwPetBonusTotal 定义', 'function YlxwPetBonusTotal(', 1, '==', ''),
        ('T2·YlxwPetLanePets 定义', 'function YlxwPetLanePets(', 1, '==', ''),
        ('T2·YlxwSpiritToPet 定义', 'function YlxwSpiritToPet(', 1, '==', ''),
        ('T2·YlxwMergeSpiritAway 定义', 'function YlxwMergeSpiritAway(', 1, '==', ''),
        # ---- 面板 / 融合 / 角色面板 ----
        ('T2·YlxwPetShell 定义', 'function YlxwPetShell(', 1, '==', ''),
        ('T2·融合页签定义', 'function YlxwPetFuseTab(', 1, '==', ''),
        ('T2·角色面板加成行定义', 'function YlxwPetStatRow(', 1, '==', ''),
        ('T2·面板包装生效', 'jM=Rt.memo(YlxwPetShell)', 1, '==', ''),
        ('T2·原 memo(vM) 清零', 'jM=Rt.memo(vM)', 0, '==', ''),
        ('T2·原 vM 组件保留', 'vM=({isOpen:t,onClose:r,player:a,onActivatePet', 1, '==', '不删原面板，仅外层包装'),
        # ---- 硬红线：远征/战斗 零改动 ----
        ('红线·远征派遣 20000 未动', 'var _expCost = 20000;', 1, '==', '洞府灵兽远征一行不动'),
        ('红线·远征结算未动', 'function YlxwExpClaim(', 1, '==', ''),
        ('红线·战斗结算核心 Oy 未动', 'YlxwBattleBonus(t),YlxwDOD=', 1, '==', '战斗环零改动'),
        ('红线·未新增 403 语义', 'status === 403', 1, '==', '仅 0.8.5 秘境 gate 既有 1 处'),
    ]
    return gates
