# -*- coding: utf-8 -*-
"""
yl_v26n_ext.py — v26n 追加注入块：万宝洗炼 + 自创神通 + 战斗/属性消费补丁

上游来源：JeasonLoop/react-xiuxian-game @1ec1b63
  - constants/reforge.ts            (7 词条 / 稀有度配置 / getReforgeCost)
  - utils/reforgeUtils.ts           (rollReforgeCandidate / apply / discard / toggleLock)
  - constants/customSpell.ts        (CUSTOM_SPELL_CONFIG / 词库 / ART_GRADE_MULTIPLIER)
  - services/customSpellService.ts  (fuse / upgrade / forget / calculateAllCustomSpellBonuses)

我方适配要点
  1. 属性层：xt(player) 末尾追加 YlxwStatExtras —— 洗炼 attack/defense/hpPercent（仅已装备件）
     + 神通 attackPercent/speedPercent。两套战斗（快速结算 X0 / 回合制 km）都走 xt，自动生效。
  2. 战斗层：
     - X0（自动历练快速结算）：暴击上限 .2 → .35（对齐上游），并消费 critRate/critDamage/
       dodgeRate/lifeLeech/damageReduction。
     - km（手动历练回合制）：上游已是 .35 上限；玩家增益以 buff 形式在 QS(player) 里注入
       （crit / critDamage / dodge / damageReduction），吸血在 km 命中后补一行。
  3. 上游 4 条特殊词条（critRate/critDamage/dodgeRate/lifeLeech）在 getPlayerTotalStats 里
     只被 getEquippedReforgeSpecialStats 计算、但全项目无调用者（死代码）。此处按用户拍板
     「补齐消费逻辑，7 条全生效」补上真实战斗消费。
"""

# ---------------------------------------------------------------- 共用：属性 / 战斗加成

CORE_JS = r'''
/* ===== yl-v26n 洗炼·神通 属性与战斗加成（共用） ===== */
function YlxwEqItems(p) {
  var out = [], eq = (p && p.equippedItems) || {}, inv = (p && p.inventory) || [], k, i;
  for (k in eq) {
    if (!Object.prototype.hasOwnProperty.call(eq, k)) continue;
    var id = eq[k]; if (!id) continue;
    for (i = 0; i < inv.length; i++) { if (inv[i] && inv[i].id === id) { out.push(inv[i]); break; } }
  }
  return out;
}

/* 属性层：百分比攻防血（洗炼，仅已装备件）+ 神通攻速% */
function YlxwStatExtras(p, r) {
  if (!p || !r) return;
  var eq = YlxwEqItems(p), i, j, it, af;
  for (i = 0; i < eq.length; i++) {
    it = eq[i];
    if (!it || !it.reforgeAffixes) continue;
    for (j = 0; j < it.reforgeAffixes.length; j++) {
      af = it.reforgeAffixes[j];
      if (!af || !af.value) continue;
      if (af.type === "attackPercent") r.attack += Math.floor(p.attack * af.value);
      else if (af.type === "defensePercent") r.defense += Math.floor(p.defense * af.value);
      else if (af.type === "hpPercent") r.maxHp += Math.floor(p.maxHp * af.value);
    }
  }
  var sp = p.customSpells || [], e2;
  for (i = 0; i < sp.length; i++) {
    e2 = (sp[i] && sp[i].effects) || {};
    if (e2.attackPercent) r.attack += Math.floor(p.attack * e2.attackPercent);
    if (e2.speedPercent) r.speed += Math.floor(p.speed * e2.speedPercent);
  }
}

/* 战斗层：洗炼 4 条特殊词条 + 神通战斗增益汇总 */
function YlxwBattleBonus(p) {
  var o = { critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0 };
  if (!p) return o;
  var eq = YlxwEqItems(p), i, j, af;
  for (i = 0; i < eq.length; i++) {
    if (!eq[i] || !eq[i].reforgeAffixes) continue;
    for (j = 0; j < eq[i].reforgeAffixes.length; j++) {
      af = eq[i].reforgeAffixes[j];
      if (!af || !af.value) continue;
      if (af.type === "critRate" || af.type === "critDamage" || af.type === "dodgeRate" || af.type === "lifeLeech") {
        o[af.type] += af.value;
      }
    }
  }
  var sp = p.customSpells || [], e2;
  for (i = 0; i < sp.length; i++) {
    e2 = (sp[i] && sp[i].effects) || {};
    if (e2.critRate) o.critRate += e2.critRate;
    if (e2.critDamage) o.critDamage += e2.critDamage;
    if (e2.dodgeRate) o.dodgeRate += e2.dodgeRate;
    if (e2.lifeLeech) o.lifeLeech += e2.lifeLeech;
    if (e2.damageReduction) o.damageReduction += e2.damageReduction;
  }
  return o;
}

/* 把战斗增益包成 buff 数组，供回合制战斗（读 buffs）消费。
   注意：必须带正 duration，否则 Cm() 的 duration-1 清理会立刻滤掉。 */
function YlxwSpellBuffs(p) {
  var b = YlxwBattleBonus(p), out = [], D = 9999;
  if (b.critRate > 0) out.push({ id: "ylxw-rc", name: "洗炼会心", type: "crit", value: b.critRate, duration: D, source: "ylxw" });
  if (b.critDamage > 0) out.push({ id: "ylxw-rd", name: "洗炼裂魄", critDamage: b.critDamage, duration: D, source: "ylxw" });
  if (b.dodgeRate > 0) out.push({ id: "ylxw-ro", name: "洗炼幻影", dodge: b.dodgeRate, duration: D, source: "ylxw" });
  if (b.lifeLeech > 0) out.push({ id: "ylxw-rl", name: "洗炼噬灵", lifeLeech: b.lifeLeech, duration: D, source: "ylxw" });
  if (b.damageReduction > 0) out.push({ id: "ylxw-sd", name: "神通护体", damageReduction: b.damageReduction, duration: D, source: "ylxw" });
  return out;
}
'''

# ---------------------------------------------------------------- 万宝洗炼

REFORGE_JS = r'''
/* ===== yl-v26n 万宝洗炼（上游 0.3.8 reforge） ===== */
var YlxwRF_DEFS = {
  attackPercent: { name: "锋芒", color: "text-red-400", desc: "提升总攻击力百分比" },
  defensePercent: { name: "玄甲", color: "text-blue-400", desc: "提升总防御力百分比" },
  hpPercent: { name: "长生", color: "text-emerald-400", desc: "提升总气血上限百分比" },
  critRate: { name: "天煞", color: "text-amber-400", desc: "提升会心一击几率" },
  critDamage: { name: "裂魄", color: "text-orange-400", desc: "提升会心一击伤害倍率" },
  dodgeRate: { name: "幻影", color: "text-purple-400", desc: "提升身法闪避几率" },
  lifeLeech: { name: "噬灵", color: "text-rose-400", desc: "造成的伤害按比例吸取气血" }
};
var YlxwRF_TYPES = ["attackPercent", "defensePercent", "hpPercent", "critRate", "critDamage", "dodgeRate", "lifeLeech"];
var YlxwRF_RARITY = {
  "普通": { minA: 1, maxA: 1, minV: 0.02, maxV: 0.05 },
  "稀有": { minA: 1, maxA: 2, minV: 0.05, maxV: 0.10 },
  "传说": { minA: 2, maxA: 3, minV: 0.08, maxV: 0.15 },
  "仙品": { minA: 3, maxA: 3, minV: 0.12, maxV: 0.22 }
};

function YlxwRF_Cfg(r) { return YlxwRF_RARITY[r] || YlxwRF_RARITY["普通"]; }

function YlxwRF_Cost(count, locked) {
  count = count || 0; locked = locked || 0;
  var bs = 1 + Math.floor(count / 5);
  var bsp = 500 + Math.min(10000, count * 250);
  return { stones: bs + locked, spiritStones: Math.round(bsp * (1 + 0.5 * locked)) };
}

function YlxwRF_IsReforgeable(it) {
  if (!it) return !1;
  if (it.isEquippable) return !0;
  return it.type === "武器" || it.type === "护甲" || it.type === "首饰" || it.type === "戒指" || it.type === "法宝";
}

function YlxwRF_StoneCount(p) {
  var inv = (p && p.inventory) || [], n = 0, i;
  for (i = 0; i < inv.length; i++) {
    if (inv[i] && (inv[i].name === "太虚洗炼石" || inv[i].id === "taixu-reforge-stone")) n += (inv[i].quantity || 1);
  }
  return n;
}

function YlxwRF_Roll(rarity, count, excluded) {
  var cfg = YlxwRF_Cfg(rarity);
  var n = (count === null || count === void 0)
    ? (Math.floor(Math.random() * (cfg.maxA - cfg.minA + 1)) + cfg.minA) : count;
  var pool = [], i, t;
  for (i = 0; i < YlxwRF_TYPES.length; i++) {
    t = YlxwRF_TYPES[i];
    if (!excluded || !excluded[t]) pool.push(t);
  }
  var chosen = [];
  for (i = 0; i < n && pool.length > 0; i++) {
    var idx = Math.floor(Math.random() * pool.length);
    chosen.push(pool[idx]); pool.splice(idx, 1);
  }
  return chosen.map(function (ty) {
    var d = YlxwRF_DEFS[ty] || {};
    var raw = cfg.minV + Math.random() * (cfg.maxV - cfg.minV);
    return { type: ty, name: d.name || ty, value: Math.round(raw * 1000) / 1000 };
  });
}

function YlxwRF_Idx(p, itemId) {
  var inv = (p && p.inventory) || [], i;
  for (i = 0; i < inv.length; i++) { if (inv[i] && inv[i].id === itemId) return i; }
  return -1;
}

function YlxwRF_Candidate(p, itemId) {
  var idx = YlxwRF_Idx(p, itemId);
  if (idx < 0) return { success: !1, message: "法宝未在背包中找到！", updatedPlayer: p };
  var it = p.inventory[idx];
  if (!YlxwRF_IsReforgeable(it)) return { success: !1, message: "该物品非道兵法宝，无法进行淬火洗炼！", updatedPlayer: p };
  if (it.pendingReforge) return { success: !1, message: "仙炉中尚有未取舍的洗炼候选，请先采纳或舍弃！", updatedPlayer: p };

  var cur = it.reforgeAffixes || [], locks = it.reforgeLocks || [], locked = [], lockedTypes = {}, i;
  for (i = 0; i < cur.length; i++) {
    if (locks[i]) { locked.push(cur[i]); lockedTypes[cur[i].type] = !0; }
  }
  var cost = YlxwRF_Cost(it.reforgeCount || 0, locked.length);
  var have = YlxwRF_StoneCount(p);
  if (have < cost.stones) {
    return { success: !1, message: "太虚洗炼石不足！本次洗炼需 " + cost.stones + " 颗，当前仅有 " + have + " 颗（通天塔与灵兽远征均可获取）。", updatedPlayer: p };
  }
  if ((p.spiritStones || 0) < cost.spiritStones) {
    return { success: !1, message: "灵石不足！本次洗炼需 " + cost.spiritStones.toLocaleString() + " 灵石。", updatedPlayer: p };
  }

  var left = cost.stones, ninv = [], o, q;
  for (i = 0; i < p.inventory.length; i++) {
    o = p.inventory[i];
    if (left > 0 && o && (o.name === "太虚洗炼石" || o.id === "taixu-reforge-stone")) {
      q = o.quantity || 1;
      if (q <= left) { left -= q; continue; }
      ninv.push(Object.assign({}, o, { quantity: q - left })); left = 0; continue;
    }
    ninv.push(o);
  }

  var cfg = YlxwRF_Cfg(it.rarity || "普通");
  var rolled = Math.floor(Math.random() * (cfg.maxA - cfg.minA + 1)) + cfg.minA;
  var target = Math.max(cur.length, rolled, locked.length);
  var free = Math.max(0, target - locked.length);
  var cand = locked.concat(YlxwRF_Roll(it.rarity || "普通", free, lockedTypes));

  var ni = YlxwRF_Idx({ inventory: ninv }, itemId);
  var upd = Object.assign({}, it, { reforgeCount: (it.reforgeCount || 0) + 1, pendingReforge: cand });
  if (ni >= 0) ninv[ni] = upd; else ninv.push(upd);

  return {
    success: !0,
    candidate: cand,
    message: "【万宝淬炼】仙炉神火烈烈！【" + it.name + "】重铸出新的道蕴候选，请取舍！",
    updatedPlayer: Object.assign({}, p, { spiritStones: (p.spiritStones || 0) - cost.spiritStones, inventory: ninv })
  };
}

function YlxwRF_Apply(p, itemId) {
  var idx = YlxwRF_Idx(p, itemId);
  if (idx < 0 || !p.inventory[idx].pendingReforge) return { success: !1, message: "无待采纳的洗炼候选！", updatedPlayer: p };
  var ninv = p.inventory.slice();
  ninv[idx] = Object.assign({}, ninv[idx], { reforgeAffixes: ninv[idx].pendingReforge, pendingReforge: void 0 });
  return { success: !0, message: "【万宝淬炼】天地道蕴已铭刻！【" + ninv[idx].name + "】新词条生效。", updatedPlayer: Object.assign({}, p, { inventory: ninv }) };
}

function YlxwRF_Discard(p, itemId) {
  var idx = YlxwRF_Idx(p, itemId);
  if (idx < 0 || !p.inventory[idx].pendingReforge) return { success: !1, message: "无待舍弃的洗炼候选！", updatedPlayer: p };
  var ninv = p.inventory.slice();
  ninv[idx] = Object.assign({}, ninv[idx], { pendingReforge: void 0 });
  return { success: !0, message: "【万宝淬炼】候选道蕴已散于天地，灵石与洗炼石不予退回。", updatedPlayer: Object.assign({}, p, { inventory: ninv }) };
}

function YlxwRF_ToggleLock(p, itemId, index) {
  var idx = YlxwRF_Idx(p, itemId);
  if (idx < 0) return { success: !1, updatedPlayer: p };
  var it = p.inventory[idx];
  if (it.pendingReforge) return { success: !1, updatedPlayer: p };
  var af = it.reforgeAffixes || [];
  if (index < 0 || index >= af.length) return { success: !1, updatedPlayer: p };
  var locks = (it.reforgeLocks || []).slice(), i;
  while (locks.length < af.length) locks.push(!1);
  locks[index] = !locks[index];
  var lc = 0;
  for (i = 0; i < locks.length; i++) { if (locks[i]) lc++; }
  if (lc >= af.length && af.length > 0) return { success: !1, updatedPlayer: p };
  var ninv = p.inventory.slice();
  ninv[idx] = Object.assign({}, it, { reforgeLocks: locks });
  return { success: !0, updatedPlayer: Object.assign({}, p, { inventory: ninv }) };
}

/* UI：仙务枢纽「万宝洗炼」页 */
function YlxwTReforge() {
  var p = Be(function (s) { return s.player; });
  var st = O.useState(""), selRaw = st[0], setSel = st[1];
  if (!p) return e.jsx(YlxwEmpty, { children: "尚未进入游戏，无法开启万宝仙炉。" });

  var inv = p.inventory || [], eqs = [], i, k;
  for (i = 0; i < inv.length; i++) { if (inv[i] && YlxwRF_IsReforgeable(inv[i])) eqs.push(inv[i]); }
  var sel = selRaw, ok = !1;
  for (i = 0; i < eqs.length; i++) { if (eqs[i].id === sel) { ok = !0; break; } }
  if (!ok) sel = eqs.length ? eqs[0].id : "";
  var it = null;
  for (i = 0; i < eqs.length; i++) { if (eqs[i].id === sel) { it = eqs[i]; break; } }

  var stoneCnt = YlxwRF_StoneCount(p);
  var eqo = p.equippedItems || {}, equipMap = {};
  for (k in eqo) { if (Object.prototype.hasOwnProperty.call(eqo, k) && eqo[k]) equipMap[eqo[k]] = !0; }

  function run(fn) {
    var cp = Be.getState().player; if (!cp) return;
    var r = fn(cp);
    if (r && r.message) Be.getState().addLog(r.message, r.success ? "special" : "normal");
    if (r && r.success && r.updatedPlayer) Be.getState().setPlayer(r.updatedPlayer);
  }

  var lockedCount = 0, lk0 = it ? (it.reforgeLocks || []) : [];
  for (i = 0; i < lk0.length; i++) { if (lk0[i]) lockedCount++; }
  var cost = YlxwRF_Cost(it ? (it.reforgeCount || 0) : 0, lockedCount);
  var head = "洗炼石 " + stoneCnt + " · 灵石 " + (p.spiritStones || 0).toLocaleString() + " · 可洗炼 " + eqs.length + " 件";

  var afRows = [];
  if (it) {
    var af = it.reforgeAffixes || [], lk = it.reforgeLocks || [];
    for (i = 0; i < af.length; i++) {
      afRows.push(e.jsxs(YlxwRow, { children: [
        e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
          e.jsxs("span", { className: "text-xs", children: [
            e.jsx("span", { className: YlxwRF_DEFS[af[i].type] ? YlxwRF_DEFS[af[i].type].color : "text-stone-200", children: ((YlxwRF_DEFS[af[i].type] || {}).name || af[i].type) + " " }),
            e.jsx("span", { className: "text-stone-100 font-mono", children: (Math.round(af[i].value * 1000) / 10) + "%" }),
            e.jsx("span", { className: "text-stone-500 ml-2", children: (YlxwRF_DEFS[af[i].type] || {}).desc || "" })
          ] }),
          e.jsx(YlxwBtn, {
            tone: "ghost",
            disabled: !!it.pendingReforge,
            onClick: (function (idx) { return function () { run(function (cp) { return YlxwRF_ToggleLock(cp, it.id, idx); }); }; })(i),
            children: lk[i] ? "已锁定" : "锁定"
          })
        ] })
      ] }, "af" + i));
    }
  }

  var pdRows = [];
  if (it && it.pendingReforge) {
    for (i = 0; i < it.pendingReforge.length; i++) {
      pdRows.push(e.jsxs("span", { className: "inline-block mr-3 text-xs", children: [
        e.jsx("span", { className: (YlxwRF_DEFS[it.pendingReforge[i].type] || {}).color || "text-stone-200", children: ((YlxwRF_DEFS[it.pendingReforge[i].type] || {}).name || it.pendingReforge[i].type) + " " }),
        e.jsx("span", { className: "text-stone-100 font-mono", children: (Math.round(it.pendingReforge[i].value * 1000) / 10) + "%" })
      ] }, "pd" + i));
    }
  }

  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: head }), children: "万宝洗炼" }),
    eqs.length
      ? e.jsxs(YlxwRow, { children: [
          e.jsx("div", { className: "text-xs text-stone-400 mb-1.5", children: "选择要洗炼的法宝 / 装备（词条仅已装备的生效）" }),
          e.jsx("select", {
            value: sel,
            onChange: function (ev) { setSel(ev.target.value); },
            className: "w-full bg-ink-800 border border-stone-600 rounded px-2 py-1.5 text-sm text-stone-100",
            children: eqs.map(function (x) {
              return e.jsx("option", { value: x.id, children: x.name + "（" + (x.rarity || "普通") + (equipMap[x.id] ? "·已装备" : "") + "）" }, x.id);
            })
          })
        ] })
      : e.jsx(YlxwEmpty, { children: "背包中没有可洗炼的法宝或装备。" }),

    it ? e.jsxs(YlxwRow, { children: [
      e.jsxs("div", { className: "text-xs text-stone-300", children: [
        "已洗炼 ", (it.reforgeCount || 0), " 次 · 下次消耗：太虚洗炼石 x", cost.stones, " + 灵石 ", cost.spiritStones.toLocaleString(),
        lockedCount ? "（锁定 " + lockedCount + " 条加价）" : ""
      ] }),
      e.jsx("div", { className: "text-[11px] text-stone-500 mt-1", children: "洗炼会重掷全部未锁定词条；锁定词条保留且不可重复出现。候选掷出即扣费，舍弃不退。" }),
      e.jsxs("div", { className: "flex items-center gap-2 mt-2 flex-wrap", children: [
        e.jsx(YlxwBtn, {
          disabled: !!it.pendingReforge || stoneCnt < cost.stones || (p.spiritStones || 0) < cost.spiritStones,
          onClick: function () { run(function (cp) { return YlxwRF_Candidate(cp, it.id); }); },
          children: "开炉洗炼"
        }),
        it.pendingReforge ? e.jsx(YlxwBtn, { onClick: function () { run(function (cp) { return YlxwRF_Apply(cp, it.id); }); }, children: "采纳新词条" }) : null,
        it.pendingReforge ? e.jsx(YlxwBtn, { tone: "ghost", onClick: function () { run(function (cp) { return YlxwRF_Discard(cp, it.id); }); }, children: "舍弃候选" }) : null
      ] })
    ] }) : null,

    it && it.pendingReforge ? e.jsxs(YlxwRow, { children: [
      e.jsx("div", { className: "text-xs text-amber-300 mb-1", children: "仙炉中的新道蕴候选" }),
      e.jsx("div", { children: pdRows })
    ] }) : null,

    it && (it.reforgeAffixes || []).length ? e.jsx("div", { className: "text-xs text-amber-300 pt-1", children: "当前词条" }) : null,
    it && (it.reforgeAffixes || []).length ? e.jsx(e.Fragment, { children: afRows }) : null,
    it && !(it.reforgeAffixes || []).length ? e.jsx("div", { className: "text-[11px] text-stone-500 pt-1", children: "该法宝尚无洗炼词条，开炉洗炼即可获得。" }) : null
  ] });
}

YLXW_ICONS.reforge = "M12 2l2.4 5.4L20 9l-4 4 1 6-5-2.8L7 19l1-6-4-4 5.6-1.6z";
YLXW_COMP.reforge = YlxwTReforge;
YLXW_TABS.push({ key: "reforge", label: "万宝洗炼", group: 1 });
'''

# ---------------------------------------------------------------- 自创神通

SPELL_JS = r'''
/* ===== yl-v26n 自创神通（上游 0.3.8 customSpell） ===== */
var YlxwSP_CFG = {
  minRealm: "金丹期", baseCost: 50000, maxLevel: 10, upgradeBase: 30000,
  slots: { "炼气期": 0, "筑基期": 0, "金丹期": 1, "元婴期": 2, "化神期": 3, "合道期": 4, "长生境": 5 }
};
var YlxwSP_PREFIX = ["九天", "太虚", "万象", "混沌", "玄天", "诛仙", "造化", "紫霄", "纯阳", "太阴", "八荒", "乾坤", "幽冥", "寂灭", "罗睺", "天罡", "地煞", "大衍", "无极", "鸿蒙"];
var YlxwSP_SUFFIX = ["破界引", "斩道决", "真解", "化极典", "神印", "法象", "灭度光", "玄罡印", "无量法", "洞虚诀"];
var YlxwSP_GRADE = { "黄": 1.0, "玄": 1.35, "地": 1.8, "天": 2.4 };

function YlxwSP_MaxSlots(realm) { return YlxwSP_CFG.slots[realm] || 0; }
function YlxwSP_UpgradeCost(lv) { return Math.floor(YlxwSP_CFG.upgradeBase * Math.pow(1.5, lv)); }

function YlxwSP_Art(id) {
  for (var i = 0; i < is.length; i++) { if (is[i].id === id) return is[i]; }
  return null;
}

function YlxwSP_GenName(a1, a2) {
  var pf = YlxwSP_PREFIX[Math.floor(Math.random() * YlxwSP_PREFIX.length)];
  var sf = YlxwSP_SUFFIX[Math.floor(Math.random() * YlxwSP_SUFFIX.length)];
  return pf + "·" + a1.name.slice(0, 2) + a2.name.slice(-2) + sf;
}

function YlxwSP_FuseEffects(a1, a2) {
  var m1 = YlxwSP_GRADE[a1.grade] || 1, m2 = YlxwSP_GRADE[a2.grade] || 1;
  var avg = (m1 + m2) / 2, ef = {};
  var e1 = a1.effects || {}, e2 = a2.effects || {};
  if (e1.attack || e2.attack || e1.attackPercent || e2.attackPercent) {
    ef.attackPercent = Number((0.08 * avg).toFixed(3));
    ef.critRate = Number((0.04 * avg).toFixed(3));
  } else {
    ef.attackPercent = Number((0.05 * avg).toFixed(3));
  }
  if (e1.defense || e2.defense || e1.hp || e2.hp || e1.physique) {
    ef.damageReduction = Number((0.05 * avg).toFixed(3));
    ef.lifeLeech = Number((0.03 * avg).toFixed(3));
  }
  if (e1.speed || e2.speed || e1.speedPercent || e2.speedPercent) {
    ef.dodgeRate = Number((0.04 * avg).toFixed(3));
    ef.speedPercent = Number((0.06 * avg).toFixed(3));
  }
  ef.critDamage = Number((0.15 * avg).toFixed(3));
  return ef;
}

function YlxwSP_CanFuse(p, id1, id2) {
  var pi = fe.indexOf(p.realm), mi = fe.indexOf(YlxwSP_CFG.minRealm);
  if (pi < mi) return { canFuse: !1, reason: "境界未达【" + YlxwSP_CFG.minRealm + "】，无法参悟天道融合神通！" };
  if (id1 === id2) return { canFuse: !1, reason: "必须选择两门不同的功法进行道蕴融汇！" };
  var cur = p.customSpells || [], mx = YlxwSP_MaxSlots(p.realm);
  if (cur.length >= mx) return { canFuse: !1, reason: "当前境界最多可参悟 " + mx + " 门自创神通，道心已满！" };
  var learned = p.cultivationArts || [];
  if (learned.indexOf(id1) < 0 || learned.indexOf(id2) < 0) return { canFuse: !1, reason: "只能融合已习得的功法！" };
  if ((p.spiritStones || 0) < YlxwSP_CFG.baseCost) return { canFuse: !1, reason: "灵石不足，参悟融合需要 " + YlxwSP_CFG.baseCost.toLocaleString() + " 灵石！" };
  return { canFuse: !0 };
}

function YlxwSP_Fuse(p, id1, id2, customName) {
  var ck = YlxwSP_CanFuse(p, id1, id2);
  if (!ck.canFuse) return { success: !1, updatedPlayer: p, message: ck.reason || "无法融合" };
  var a1 = YlxwSP_Art(id1), a2 = YlxwSP_Art(id2);
  if (!a1 || !a2) return { success: !1, updatedPlayer: p, message: "选择的功法不存在！" };
  var nm = (customName || "").replace(/^\s+|\s+$/g, "");
  if (!nm) nm = YlxwSP_GenName(a1, a2);
  if (nm.length > 14) nm = nm.slice(0, 14);
  var sp = {
    id: "custom-spell-" + Date.now(),
    name: nm,
    description: "由【" + a1.name + "】与【" + a2.name + "】万千真意融汇贯通所创之无上神通。",
    sourceArtIds: [a1.id, a2.id],
    effects: YlxwSP_FuseEffects(a1, a2),
    level: 1, proficiency: 0
  };
  var ninv = p.inventory.slice(), si = -1, i;
  for (i = 0; i < ninv.length; i++) {
    if (ninv[i] && ninv[i].id === "taixu-comprehension-scroll" && (ninv[i].quantity || 1) >= 1) { si = i; break; }
  }
  if (si >= 0) {
    var q = ninv[si].quantity || 1;
    if (q > 1) ninv[si] = Object.assign({}, ninv[si], { quantity: q - 1 }); else ninv.splice(si, 1);
  }
  return {
    success: !0, spell: sp,
    message: "道法归一，神念通达！你成功自创神通【" + sp.name + "】！",
    updatedPlayer: Object.assign({}, p, {
      spiritStones: Math.max(0, (p.spiritStones || 0) - YlxwSP_CFG.baseCost),
      inventory: ninv,
      customSpells: (p.customSpells || []).concat([sp])
    })
  };
}

function YlxwSP_Upgrade(p, sid) {
  var sp = p.customSpells || [], idx = -1, i;
  for (i = 0; i < sp.length; i++) { if (sp[i].id === sid) { idx = i; break; } }
  if (idx < 0) return { success: !1, updatedPlayer: p, message: "未找到该自创神通！" };
  var t = sp[idx];
  if (t.level >= YlxwSP_CFG.maxLevel) return { success: !1, updatedPlayer: p, message: "该神通已领悟至第十重圆满极境！" };
  var cost = YlxwSP_UpgradeCost(t.level);
  if ((p.spiritStones || 0) < cost) {
    return { success: !1, updatedPlayer: p, message: "灵石不足，提升至第 " + (t.level + 1) + " 重需要 " + cost.toLocaleString() + " 灵石！" };
  }
  var ne = {}, k;
  for (k in t.effects) {
    if (Object.prototype.hasOwnProperty.call(t.effects, k) && typeof t.effects[k] === "number") {
      ne[k] = Number((t.effects[k] * 1.12).toFixed(3));
    }
  }
  var ns = sp.slice();
  ns[idx] = Object.assign({}, t, { level: t.level + 1, effects: ne });
  return {
    success: !0,
    updatedPlayer: Object.assign({}, p, { spiritStones: (p.spiritStones || 0) - cost, customSpells: ns }),
    message: "神通突破！【" + t.name + "】晋升至第 " + (t.level + 1) + " 重，威能大幅激增！"
  };
}

function YlxwSP_Forget(p, sid) {
  var sp = p.customSpells || [], t = null, i;
  for (i = 0; i < sp.length; i++) { if (sp[i].id === sid) { t = sp[i]; break; } }
  if (!t) return { success: !1, updatedPlayer: p, message: "未找到该自创神通！" };
  var refund = Math.floor(YlxwSP_CFG.baseCost * 0.4 * t.level);
  var ns = sp.filter(function (s) { return s.id !== sid; });
  return {
    success: !0,
    updatedPlayer: Object.assign({}, p, { spiritStones: (p.spiritStones || 0) + refund, customSpells: ns }),
    message: "你斩断神念因果，遗忘了神通【" + t.name + "】，返还散功灵石 " + refund.toLocaleString() + "！"
  };
}

var YlxwSP_EFFNAME = {
  attackPercent: "攻击", critRate: "会心", critDamage: "裂魄", damageReduction: "减伤",
  lifeLeech: "噬灵", dodgeRate: "幻影", speedPercent: "身法"
};

/* UI：仙务枢纽「自创神通」页 */
function YlxwTSpell() {
  var p = Be(function (s) { return s.player; });
  var s1 = O.useState(""), a1r = s1[0], setA1 = s1[1];
  var s2 = O.useState(""), a2r = s2[0], setA2 = s2[1];
  var s3 = O.useState(""), nmr = s3[0], setNm = s3[1];
  if (!p) return e.jsx(YlxwEmpty, { children: "尚未进入游戏，无法参悟自创神通。" });

  var arts = p.cultivationArts || [], spells = p.customSpells || [];
  var maxSlots = YlxwSP_MaxSlots(p.realm);
  var a1 = a1r || (arts[0] || ""), a2 = a2r || (arts[1] || "");
  var scrolls = 0, i;
  for (i = 0; i < (p.inventory || []).length; i++) {
    var o = p.inventory[i];
    if (o && (o.id === "taixu-comprehension-scroll" || o.name === "太虚悟道卷")) scrolls += (o.quantity || 1);
  }
  var ck = (a1 && a2) ? YlxwSP_CanFuse(p, a1, a2) : { canFuse: !1, reason: "请选择两门不同的已习得功法。" };

  function run(fn) {
    var cp = Be.getState().player; if (!cp) return;
    var r = fn(cp);
    if (r && r.message) Be.getState().addLog(r.message, r.success ? "special" : "normal");
    if (r && r.success && r.updatedPlayer) Be.getState().setPlayer(r.updatedPlayer);
  }

  var artOpts = function (v) {
    return arts.map(function (id) {
      var a = YlxwSP_Art(id);
      return e.jsx("option", { value: id, children: (a ? a.name + "（" + a.grade + "）" : id) }, id);
    });
  };

  var head = "境界 " + p.realm + " · 神通 " + spells.length + "/" + maxSlots + " · 悟道卷 " + scrolls + " · 灵石 " + (p.spiritStones || 0).toLocaleString();

  var spRows = spells.map(function (sp) {
    var ef = sp.effects || {}, ks = Object.keys(ef), effSpans = [];
    for (var j = 0; j < ks.length; j++) {
      if (!ef[ks[j]]) continue;
      effSpans.push(e.jsx("span", {
        className: "inline-block mr-2 text-[11px] text-amber-300",
        children: (YlxwSP_EFFNAME[ks[j]] || ks[j]) + " +" + (Math.round(ef[ks[j]] * 1000) / 10) + "%"
      }, ks[j]));
    }
    var cost = YlxwSP_UpgradeCost(sp.level);
    return e.jsxs(YlxwRow, { children: [
      e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsxs("span", { children: [sp.name + " · 第 " + sp.level + " 重"] }),
        e.jsxs("span", { className: "flex items-center gap-1.5", children: [
          e.jsx(YlxwBtn, {
            disabled: sp.level >= YlxwSP_CFG.maxLevel || (p.spiritStones || 0) < cost,
            onClick: (function (id) { return function () { run(function (cp) { return YlxwSP_Upgrade(cp, id); }); }; })(sp.id),
            children: sp.level >= YlxwSP_CFG.maxLevel ? "已圆满" : ("参悟 +" + cost.toLocaleString())
          }),
          e.jsx(YlxwBtn, {
            tone: "ghost",
            onClick: (function (id) { return function () { run(function (cp) { return YlxwSP_Forget(cp, id); }); }; })(sp.id),
            children: "遗忘"
          })
        ] })
      ] }),
      e.jsx("div", { className: "text-[11px] text-stone-500 mt-1", children: sp.description }),
      e.jsx("div", { className: "mt-1", children: effSpans })
    ] }, sp.id);
  });

  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: head }), children: "自创神通" }),

    e.jsx(YlxwRow, { children: [
      e.jsx("div", { className: "text-[11px] text-stone-500 mb-1.5", children: "自创神通需【金丹期】以上，融汇两门已习得功法（品级越高威能越强），消耗 灵石 " + YlxwSP_CFG.baseCost.toLocaleString() + "（有悟道卷时额外消耗 1 张）。" })
    ] }),

    arts.length < 2
      ? e.jsx(YlxwEmpty, { children: "至少需习得两门功法方可融汇自创神通。" })
      : e.jsxs(YlxwRow, { children: [
          e.jsxs("div", { className: "grid grid-cols-1 md:grid-cols-3 gap-2", children: [
            e.jsxs("div", { children: [
              e.jsx("div", { className: "text-xs text-stone-400 mb-1", children: "源功法一" }),
              e.jsx("select", { value: a1, onChange: function (ev) { setA1(ev.target.value); }, className: "w-full bg-ink-800 border border-stone-600 rounded px-2 py-1.5 text-sm text-stone-100", children: artOpts(a1) })
            ] }),
            e.jsxs("div", { children: [
              e.jsx("div", { className: "text-xs text-stone-400 mb-1", children: "源功法二" }),
              e.jsx("select", { value: a2, onChange: function (ev) { setA2(ev.target.value); }, className: "w-full bg-ink-800 border border-stone-600 rounded px-2 py-1.5 text-sm text-stone-100", children: artOpts(a2) })
            ] }),
            e.jsxs("div", { children: [
              e.jsx("div", { className: "text-xs text-stone-400 mb-1", children: "神通名（留空则天赐）" }),
              e.jsx("input", {
                value: nmr, maxLength: 14,
                onChange: function (ev) { setNm(ev.target.value); },
                placeholder: "如：九天·焚天诀",
                className: "w-full bg-ink-800 border border-stone-600 rounded px-2 py-1.5 text-sm text-stone-100"
              })
            ] })
          ] }),
          e.jsxs("div", { className: "flex items-center justify-between gap-2 mt-2 flex-wrap", children: [
            e.jsx("span", { className: "text-[11px] " + (ck.canFuse ? "text-emerald-300" : "text-rose-300"), children: ck.canFuse ? "道蕴契合，可以参悟融汇。" : (ck.reason || "") }),
            e.jsx(YlxwBtn, {
              disabled: !ck.canFuse,
              onClick: function () { run(function (cp) { return YlxwSP_Fuse(cp, a1, a2, nmr); }); setNm(""); },
              children: "融汇参悟"
            })
          ] })
        ] }),

    spells.length ? e.jsx("div", { className: "text-xs text-amber-300 pt-1", children: "已参悟神通" }) : null,
    spells.length ? e.jsx(e.Fragment, { children: spRows }) : e.jsx("div", { className: "text-[11px] text-stone-500 pt-1", children: "尚未参悟任何自创神通。" })
  ] });
}

YLXW_ICONS.spell = "M12 2a7 7 0 0 0-4 12.7V19h8v-4.3A7 7 0 0 0 12 2zM9 21h6M12 6v3";
YLXW_COMP.spell = YlxwTSpell;
YLXW_TABS.push({ key: "spell", label: "自创神通", group: 1 });
'''

# ---------------------------------------------------------------- 战斗 / 属性 消费补丁

# (name, anchor, replacement, note)
BATTLE_PATCHES = [
    (
        'xt 属性层：洗炼%+神通%',
        'r.speed+=Tr(t.speed,c,d)}return r};',
        'r.speed+=Tr(t.speed,c,d)}typeof YlxwStatExtras==="function"&&YlxwStatExtras(t,r);return r};',
        'xt(player) 末尾挂载 YlxwStatExtras（攻防血% + 神通攻速%）'
    ),
    (
        'X0 暴击/闪避/暴伤/减伤',
        'const G=E==="player",Z=bo(G?x.attack:m.attack,G?m.defense:x.defense),te=Number(x.speed)||0,'
        'ee=Number(m.speed)||0,ne=Math.max(1,te+ee),F=.1+(G?te:ee)/ne*.1,W=Math.max(0,Math.min(.2,F)),'
        'K=Math.random()<W,X=K?Math.round(Z*1.5):Z;',
        'const G=E==="player",YlxwPB=YlxwBattleBonus(t),'
        'YlxwDOD=!G&&YlxwPB.dodgeRate>0&&Math.random()<YlxwPB.dodgeRate,'
        'Z=YlxwDOD?0:bo(G?x.attack:m.attack,G?m.defense:x.defense),'
        'te=Number(x.speed)||0,ee=Number(m.speed)||0,ne=Math.max(1,te+ee),'
        'F=.1+(G?te:ee)/ne*.1+(G?YlxwPB.critRate:0),W=Math.max(0,Math.min(.35,F)),'
        'K=!YlxwDOD&&Math.random()<W,'
        'X=(function(v){return (!G&&!YlxwDOD&&YlxwPB.damageReduction>0)'
        '?Math.round(v*(1-Math.min(.6,YlxwPB.damageReduction))):v;})'
        '(YlxwDOD?0:(K?Math.round(Z*(1.5+(G?YlxwPB.critDamage:0))):Z));',
        '冒险快速结算：暴击上限 .2→.35（对齐上游）+ 暴击率/暴伤/闪避/减伤'
    ),
    (
        'X0 吸血+闪避文案',
        'if(G?h=Math.max(0,(Number(h)||0)-X):M=Math.max(0,(Number(M)||0)-X),'
        'R.push({id:Os(),attacker:E,damage:X,crit:K,description:G?`你发动灵力攻势，造成 ${X}${K?"（暴击）":""} 点伤害。`:'
        '`${m.title}${m.name}反扑，造成 ${X}${K?"（暴击）":""} 点伤害。`,playerHpAfter:M,enemyHpAfter:h}),',
        'if(G?h=Math.max(0,(Number(h)||0)-X):M=Math.max(0,(Number(M)||0)-X),'
        'G&&X>0&&YlxwPB.lifeLeech>0&&(M=Math.min(S,M+Math.floor(X*YlxwPB.lifeLeech))),'
        'R.push({id:Os(),attacker:E,damage:X,crit:K,description:G?`你发动灵力攻势，造成 ${X}${K?"（暴击）":""} 点伤害。`:'
        '(YlxwDOD?`${m.title}${m.name}反扑，被你身法闪避，毫发无伤！`:`${m.title}${m.name}反扑，造成 ${X}${K?"（暴击）":""} 点伤害。`),'
        'playerHpAfter:M,enemyHpAfter:h}),',
        '冒险快速结算：噬灵吸血（上限为战前气血）+ 闪避文案'
    ),
    (
        'km 回合制：噬灵吸血',
        'c.hp=Math.max(0,Math.floor(c.hp-_));let C=0;',
        'c.hp=Math.max(0,Math.floor(c.hp-_)),'
        'r==="player"&&_>0&&l.buffs.forEach(function(w){w.lifeLeech&&w.lifeLeech>0&&(l.hp=Math.min(l.maxHp,l.hp+Math.floor(_*w.lifeLeech)))});'
        'let C=0;',
        '回合制战斗命中后按噬灵比例回血'
    ),
    (
        'QS 回合制：注入洗炼/神通 buff',
        'buffs:m,debuffs:[],skills:f,cooldowns:{},mana:$,maxMana:T,isDefending:!1}',
        'buffs:m.concat(typeof YlxwSpellBuffs==="function"?YlxwSpellBuffs(t):[]),debuffs:[],skills:f,cooldowns:{},mana:$,maxMana:T,isDefending:!1}',
        '玩家战斗实体挂上 crit/critDamage/dodge/damageReduction buff（km/zy 直接消费）'
    ),
]

DRAWER_ITEM_REF = '{icon:YlxwMk("reforge"),label:"万宝洗炼",onClick:()=>YlxwOpen("reforge"),color:"text-amber-300"},'
DRAWER_ITEM_SPELL = '{icon:YlxwMk("spell"),label:"自创神通",onClick:()=>YlxwOpen("spell"),color:"text-amber-300"},'

# ================================================================ 交易行货款（V27 卖家收益）
# 上游 1ec1b63 服务端把卖家货款托管到 market_payouts（claim 时才入账），客户端必须有领取入口，
# 否则货款永久锁死在托管表里。
#
# 为什么网络调用不放进主注入块：
#   build 的 BAN_PATTERNS 禁止注入块出现 'fetch(' 与 '/yl/api'（防止注入块自造网络层、绕过统一鉴权）。
#   故这里单独做一条锚点补丁，插在交易行 API 函数 Fk 之后 —— Nd()/jo()/ln 与之一同作用域，
#   直接复用其 token 拼接与 Bearer 鉴权头，风格与既有 Qk/Vk/Gk 完全一致；
#   再挂到 window 暴露，主注入块侧零作用域假设地调用（不依赖跨作用域 hoisting）。
PAYOUT_API_ANCHOR = 'function Yk(t){const r=Be(E=>E'
PAYOUT_API_JS = r'''
/* ===== yl-v26n 交易行货款 API (V27 卖家收益，对齐上游 1ec1b63) ===== */
async function YlxwMarketPayouts() {
  try {
    var r = await fetch(Nd(`${ln}/market/payouts`), { headers: { ...jo() } });
    if (!r.ok) return { ok: !1, error: "查询收益失败(" + r.status + ")" };
    var j = null; try { j = await r.json(); } catch (ylxwPoE1) { j = null; }
    if (!j) return { ok: !1, error: "收益数据解析失败" };
    return { ok: !0, total: Number(j.total) || 0, count: Number(j.count) || 0, items: Array.isArray(j.items) ? j.items : [] };
  } catch (ylxwPoE2) { return { ok: !1, error: "网络异常：" + ((ylxwPoE2 && ylxwPoE2.message) ? ylxwPoE2.message : String(ylxwPoE2)) }; }
}
async function YlxwMarketClaim() {
  try {
    var r = await fetch(Nd(`${ln}/market/payouts/claim`), { method: "POST", headers: { "Content-Type": "application/json", ...jo() }, body: "{}" });
    var j = null; try { j = await r.json(); } catch (ylxwPoE3) { j = null; }
    if (!r.ok) return { ok: !1, error: (j && j.error) || ("领取失败(" + r.status + ")") };
    return { ok: !0, amount: Number(j && j.amount) || 0, stones: (j && j.stones == null) ? null : Number(j.stones) };
  } catch (ylxwPoE4) { return { ok: !1, error: "网络异常：" + ((ylxwPoE4 && ylxwPoE4.message) ? ylxwPoE4.message : String(ylxwPoE4)) }; }
}
try { window.YlxwMarketPayouts = YlxwMarketPayouts; window.YlxwMarketClaim = YlxwMarketClaim; } catch (ylxwPoE5) {}
'''

PAYOUT_JS = r'''
/* ===== yl-v26n 交易行货款（待领收益）===== */
function YlxwPayoutsFetch() {
  try { return window.YlxwMarketPayouts ? window.YlxwMarketPayouts() : Promise.resolve({ ok: !1, error: "交易行接口不可用" }); }
  catch (e1) { return Promise.resolve({ ok: !1, error: String((e1 && e1.message) || e1) }); }
}
function YlxwPayoutsClaim() {
  try { return window.YlxwMarketClaim ? window.YlxwMarketClaim() : Promise.resolve({ ok: !1, error: "交易行接口不可用" }); }
  catch (e2) { return Promise.resolve({ ok: !1, error: String((e2 && e2.message) || e2) }); }
}

function YlxwTPayout() {
  var p = Be(function (s) { return s.player; });
  var s1 = O.useState(null), info = s1[0], setInfo = s1[1];
  var s2 = O.useState(""), err = s2[0], setErr = s2[1];
  var s4 = O.useState(""), notice = s4[0], setNotice = s4[1];
  var s3 = O.useState(!0), busy = s3[0], setBusy = s3[1];

  function refresh() {
    setBusy(!0);
    YlxwPayoutsFetch().then(function (r) {
      setBusy(!1);
      if (!r || !r.ok) { setInfo(null); setErr((r && r.error) || "查询失败"); return; }
      setInfo(r); setErr("");
    });
  }
  O.useEffect(function () { refresh(); }, []);

  function doClaim() {
    if (busy) return;
    setBusy(!0);
    setNotice("");
    // 竞态守卫（与信箱一键领取同款）：本路由走服务端 updatePlayerSave，必然 gm_revision++，
    // 客户端 6s tick 可能在响应到达前先拉档 ⇒ 本地余额已含这笔货款，再叠加即双计。
    // 故请求前快照 before，响应后仅当本地未被改动（now === before）才做乐观叠加。
    var before = Number((Be.getState().player || {}).spiritStones) || 0;
    YlxwPayoutsClaim().then(function (r) {
      setBusy(!1);
      if (!r || !r.ok) { setErr((r && r.error) || "领取失败"); return; }
      setErr("");
      if (r.amount > 0) {
        var cur = Be.getState().player;
        if (cur) {
          // 只按 amount 增量入账，不采纳服务端绝对余额：
          // 本服存档是客户端权威（冲突时客户端重推本地档、不拉取覆盖），
          // 若采纳服务端绝对 stones，会把本地尚未同步的收益抹掉。
          var now = Number(cur.spiritStones) || 0;
          if (now === before) {
            var next = Object.assign({}, cur);
            next.spiritStones = now + r.amount;
            Be.getState().setPlayer(next);
          }
          /* now !== before ⇒ 权威存档已包含这笔，跳过本地叠加 */
        }
        Be.getState().addLog("【交易行货款】领取售出货款 " + r.amount + " 灵石。", "gain");
        setNotice("已领取 " + r.amount + " 灵石。");
      } else { setNotice("暂无可领取的货款。"); }
      refresh();
    });
  }

  if (!p) return e.jsx(YlxwEmpty, { children: "尚未进入游戏，无法查看交易行货款。" });
  var total = info ? info.total : 0;
  var cnt = info ? info.count : 0;
  var items = (info && info.items) || [];
  var rows = [];
  for (var i = 0; i < items.length; i++) {
    rows.push(e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2", children: [
      e.jsx("span", { children: "货款 · 挂单 #" + (items[i].listingId == null ? "-" : items[i].listingId) }),
      e.jsx("span", { className: "text-amber-300 font-bold shrink-0", children: "+" + (Number(items[i].amount) || 0) + " 灵石" })
    ] }) }, "ylxw-po-" + items[i].id));
  }
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { children: "交易行货款（待领收益）" }),
    e.jsx(YlxwKv, { data: { "待领总额": (info ? total : 0) + " 灵石", "待领笔数": cnt } }),
    e.jsxs("div", { className: "flex items-center gap-2 pt-1 flex-wrap", children: [
      e.jsx(YlxwBtn, { disabled: busy || total <= 0, onClick: doClaim, children: total > 0 ? ("领取 " + total + " 灵石") : "暂无可领" }),
      e.jsx(YlxwBtn, { tone: "ghost", disabled: busy, onClick: refresh, children: busy ? "查询中…" : "刷新" })
    ] }),
    notice ? e.jsx("div", { className: "text-xs text-emerald-300 pt-1", children: notice }) : null,
    err ? e.jsx("div", { className: "text-xs text-rose-300 pt-1", children: err }) : null,
    rows.length ? e.jsx("div", { className: "text-xs text-stone-400 pt-1", children: "未领取明细" }) : null,
    rows.length ? e.jsx(e.Fragment, { children: rows }) : e.jsx("div", { className: "text-[11px] text-stone-500 pt-1", children: "暂无未领取的货款。物品售出后货款会先托管在此，需手动领取。" })
  ] });
}

YLXW_ICONS.payout = "M3 6h18v12H3zM3 10h18M7 14h4";
YLXW_COMP.payout = YlxwTPayout;
YLXW_TABS.push({ key: "payout", label: "交易行货款", group: 1 });
'''

DRAWER_ITEM_PAYOUT = '{icon:YlxwMk("payout"),label:"交易行货款",onClick:()=>YlxwOpen("payout"),color:"text-amber-300"},'
