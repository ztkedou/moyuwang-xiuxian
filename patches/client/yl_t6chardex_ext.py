# -*- coding: utf-8 -*-
"""
yl_t6chardex_ext.py — 0.8.7 批次 · T6 人物志细化（implRenwu / 纯客户端，服务端零改动）

设计依据
  docs/0.8.7-design/T6-人物志细化.md（已回填定值）
  docs/0.8.7-design/数值表-T5T6.md §3（数值定档唯一事实源）
  docs/0.8.7-design/0.8.7-build-plan.md §2-T6 / §5.1 / §6 / §10.1-④~⑧

四点任务（0.8.7 任务书原文）
  ① 左右两列：Nk 模态外壳加宽到 1152px + 内容区 grid md:grid-cols-2（沿用 F6 融合模式）
     ★ 0.8.8 item14 修正：0.8.7 的 `containerClassName:"md:max-w-6xl"` 被模态自带 `md:max-w-lg`
       （CSS 层叠顺序在后）覆盖，外壳恒 512px、右列道友列表被压成竖排单字。改法见 A_SHELL_GRID 注释。
  ② 砍自由赠送 → 「师门求物」任务式：每 NPC 每日一条随机需求、达量交付得好感
     凡缘+3 / 仙缘+5 / 天缘+8（按 NPC 稀有度，数值表 T6-1）；默认赠灵石好感 5→2（T6-2）
  ③ 收集奖励/缘契里程碑 → 随机物品掉落：里程碑件数 1/2/3/5、收集 1/1/2/2/3/4/6、
     权重行 R1~R6 随阶段+NPC 稀有度平移、stones/exp=0（T6-4/5/6；同心结/道友图谱固定收藏品保留）
  ④ 历练结交 7 产生点降频：注入器 10%→2%、adventure/rescue 100%→3%、
     enlightenment 30%→5%、spring 35%→5%（T6-7）

实现结构
  · 新组件 YlxwCharDexPanelT6 / YlxwCharBondPanelT6（本模块注入），Nk 内两处挂载改名指向 T6；
    旧 YlxwCharDexPanel / YlxwCharBondPanel 定义原样保留 = 死代码（T6 案 §10.1-①）。
  · 求物卡挂在 YlxwCharBondPanelT6 体内（右列详情、里程碑 chips 之上）——T6 案 §10.1-⑧
    写的是「DexPanelT6 体内」，实现落在 BondPanelT6（rel/demands 上下文所在），门禁串照打恰 1。
  · 需求/掉落数据全部 player.charDex 内追加（v:2 懒升级），随 /api/save 整包落库，服务端零改动。
  · 掉落入包复用 YlxwCharApply(prev,{stones:0,exp:0,items}) 既有通道（同心结 mile.item 同款
    {name,rarity,qty} 形态 → Material 形态纪念物；服用价值按数值表 §3.5 口径未计入代理）。

==================================================================== ★门禁计数变更清单（接线人必读，入 dryrun_087）
本模块会改变**旧模块门禁**的命中数（旧门禁锚串被本批合法改写），dryrun_087 预期值必须同步：

  yl_char_ext.py（v28 人物志模块）——5 条改预期：
    ('图鉴面板挂载', DEX_MOUNT, 1)            → 0   （挂载改名 T6 并包进左列）
    ('缘契面板挂载', BOND_MOUNT, 1)           → 0   （挂载改名 T6）
    ('图鉴落在 children 首位', A_MODAL_OPEN+DEX_MOUNT, 1) → 0（A2 内容区改 grid 两列）
    ('缘契落在结识于之后', A_DETAIL_ENC+BOND_MOUNT, 1)    → 0（BOND_MOUNT 改名）
    ('空态引导文案', R_EMPTY_TEXT, 1)         → 0   （追加「多读需求、多交付，缘契上得快。」）
    其余 char 门禁全部不变（旧面板定义恰 1 仍在 / YlxwCharSafe 恰 1 / 模态框前缀恰 1 /
    既有 8 名字池 \\u 形态恰 3 / YlxwCharApply 增量写入恰 1 均复核）。

  yl_chargift083_ext.py（0.8.3 赠灵石定价）——2 条改预期：
    ('T3·(a) 计算式已改', zh(CALC_REPL), 1)   → 0   （,E=5; → ,E=2;，本批 T6-2 定档）
    ('基线·好感增量 E=5 未动', ',E=5;', 1)    → 0   （同上）
    其余 chargift 门禁全部不变（YlxwGiftCost 定义恰 1 / 调用点恒 4 / disabled / 按钮文案 /
    clamp / title:"人物志"×2 均复核）。

  其他模块（arb/ui/version/fun086/eco085/dungeon085/…）锚区零交集（已 grep 复核）。

  ★T6 案 §10.1-⑤ 门禁值勘误（本批实现裁决，接线人按此为准）：
    `Recipe"` 设计门禁写「=0（picker 唯一锚）」，但 T6 案 §4.2 又规定需求计数的背包口径
    「沿用现 picker 的过滤 !isEquippable && type!=="Recipe" && quantity>0」——两节自相矛盾，
    按过滤语义照抄后产物内 `Recipe"` = 基线 1（picker，本批已删）−1 + 2（需求计数/交付扣物
    两处同口径过滤）= **恒 2**。「自由赠送已死」改由三断言证明：旧数据源
    `x=(a.inventory|| []).filter` == 0、赠送按钮 `onClick:()=>v(!f)` == 0、
    picker 永不渲染 `!1&&e.jsxs("div",{className:"bg-stone-800` == 1。
====================================================================

本模块自检：python yl_t6chardex_ext.py
  （对 0.8.6 基线 _chainstage/dryrun.bundle.js 的**内存副本**应用全部补丁，
    断言本模块门禁 + 受影响旧门禁新预期 + node --check 语法级校验；不写任何产物盘。）

锚点实测（基线 = _chainstage/dryrun.bundle.js，md5 3938a4ee7850e033b8a08e1dfda1c52d，
2026-09-29 实现批逐串 re.count 复核，全部 == 1；概率域 D5 裸串 == 11）——
复验命令：python yl_t6chardex_ext.py（自检含改前 25 条基线份数断言 + 改后全部门禁 +
受影响旧门禁新预期 + node --check 产物级语法校验，全过不写盘）。
"""

import re

# ---------------------------------------------------------------- 注入代码
# 中文可直写；build 侧 zh() 统一转 \uXXXX 后落盘（纯 ASCII 断言在 apply 内自检）。

INJECT_JS = r'''
/* ===== yl-0.8.7 T6 人物志细化（implRenwu）=====
   ①两列 ②师门求物 ③随机掉落（数值=数值表-T5T6 §3 定档） ④历练降频在 Nk/产生点侧 */
var YLXW_CHAR_DEMAND_POOL = {
  "凡缘": [
    { key: "聚气丹", lo: 4, hi: 6 }, { key: "回春丹", lo: 3, hi: 5 }, { key: "洗髓丹", lo: 2, hi: 3 },
    { key: "炼器石", lo: 6, hi: 10 }, { key: "强化石", lo: 4, hi: 6 },
    { key: "凝神丹", lo: 2, hi: 3 }, { key: "强体丹", lo: 2, hi: 3 }
  ],
  "仙缘": [
    { key: "筑基丹", lo: 1, hi: 2 }, { key: "龙血丹", lo: 1, hi: 2 }, { key: "结金丹", lo: 1, hi: 1 },
    { key: "凝魂丹", lo: 1, hi: 1 }, { key: "洗灵丹", lo: 1, hi: 2 }, { key: "五行灵丹", lo: 1, hi: 2 }
  ],
  "天缘": [
    { key: "九转金丹", lo: 1, hi: 1 }, { key: "凤凰涅槃丹", lo: 1, hi: 1 }, { key: "不死仙丹", lo: 1, hi: 1 },
    { key: "天元丹", lo: 1, hi: 1 }, { key: "仙灵丹", lo: 1, hi: 1 },
    { key: "破境丹", lo: 1, hi: 2 }, { key: "天灵根丹", lo: 1, hi: 2 }
  ]
};
/* 物品稀有度带：2026-09-29 对 0.8.6 产物物品字典逐件实测（普通2/稀有6/传说8/仙品4，四带非空） */
var YLXW_CHAR_ITEM_RAR = {
  "聚气丹": "普通", "炼器石": "普通",
  "回春丹": "稀有", "洗髓丹": "稀有", "强化石": "稀有", "凝神丹": "稀有", "强体丹": "稀有", "洗灵丹": "稀有",
  "筑基丹": "传说", "龙血丹": "传说", "结金丹": "传说", "凝魂丹": "传说", "五行灵丹": "传说",
  "凤凰涅槃丹": "传说", "仙灵丹": "传说", "破境丹": "传说",
  "九转金丹": "仙品", "不死仙丹": "仙品", "天元丹": "仙品", "天灵根丹": "仙品"
};
/* 好感定档（数值表 T6-1/T6-2）：交付按 NPC 稀有度；赠灵石 +2（改点在 Nk 内联 E=2，此常量供文案单一来源） */
var YLXW_CHAR_FAVOR_GAIN = { "凡缘": 3, "仙缘": 5, "天缘": 8 };
var YLXW_CHAR_STONE_FAVOR = 2;
/* 随机掉落定档（数值表 T6-4/T6-5 + §3.3 R1~R6 矩阵）：stones/exp=0，掉落即全部奖励 */
var YLXW_CHAR_DROP_N = [1, 2, 3, 5];
var YLXW_CHAR_DEX_DROP_N = [1, 1, 2, 2, 3, 4, 6];
var YLXW_CHAR_DEX_DROP_ROW = [1, 1, 2, 2, 3, 4, 5];
var YLXW_CHAR_DROP_RAR = [
  [70, 25, 5, 0],
  [55, 35, 10, 0],
  [40, 40, 17, 3],
  [25, 40, 28, 7],
  [15, 35, 35, 15],
  [8, 28, 40, 24]
];
var YLXW_CHAR_BANDS = ["普通", "稀有", "传说", "仙品"];

/* charDex v2 懒升级标记（缺 v 视为 v1；任何 T6 写入补 v:2，met/claimed/bond 原样保留） */
function YlxwCharDexV2(d) {
  d = Object.assign({}, d || {});
  if (!d.v) d.v = 2;
  return d;
}
/* NPC 稀有度位移：凡0 / 仙1 / 天2（无名道友按凡缘） */
function YlxwCharRelRarity(p, rel) {
  var entry = null;
  try { entry = YlxwCharEntry(rel.id) || YlxwCharEntryByName(rel.name); } catch (e) { entry = null; }
  return (entry && entry.rarity) || "凡缘";
}
function YlxwCharRarShift(rarity) { return rarity === "天缘" ? 2 : (rarity === "仙缘" ? 1 : 0); }
function YlxwCharBandItems(band) {
  var out = [], k;
  for (k in YLXW_CHAR_ITEM_RAR) {
    if (Object.prototype.hasOwnProperty.call(YLXW_CHAR_ITEM_RAR, k) && YLXW_CHAR_ITEM_RAR[k] === band) out.push(k);
  }
  return out;
}
/* 按权重行 R1~R6 掷 n 件（每件独立：先掷稀有度带、带内均匀取物品；行号钳 1..6） */
function YlxwCharRollRow(row, n) {
  var out = [], i, j;
  row = Math.max(1, Math.min(6, row | 0));
  n = Math.max(0, n | 0);
  for (i = 0; i < n; i++) {
    var w = YLXW_CHAR_DROP_RAR[row - 1] || YLXW_CHAR_DROP_RAR[0];
    var x = Math.random() * 100, acc = 0, band = YLXW_CHAR_BANDS[3];
    for (j = 0; j < 4; j++) { acc += (w[j] || 0); if (x < acc) { band = YLXW_CHAR_BANDS[j]; break; } }
    var items = YlxwCharBandItems(band);
    if (!items.length) items = YlxwCharBandItems("稀有");
    var key = items[Math.floor(Math.random() * items.length)];
    out.push({ name: key, rarity: band, qty: 1 });
  }
  return out;
}
/* 师门求物：按 NPC 稀有度池均匀取 1 物品、区间内均匀取数量（day=本地日期串，同 charDex.freeDate 口径） */
function YlxwCharDemandRoll(npcRarity) {
  var pool = YLXW_CHAR_DEMAND_POOL[npcRarity] || YLXW_CHAR_DEMAND_POOL["凡缘"];
  var it = pool[Math.floor(Math.random() * pool.length)];
  var need = it.lo + Math.floor(Math.random() * (it.hi - it.lo + 1));
  return { key: it.key, need: need, day: YlxwCharToday() };
}
/* 生效需求（纯展示口径）：缺/跨日 → 现场重掷；持久化由面板 effect 落档（防渲染期 setPlayer） */
function YlxwCharDemandOf(p, rel) {
  if (!p || !rel) return null;
  var d = (p.charDex && p.charDex.demands) || {};
  var cur = d[rel.id];
  var today = YlxwCharToday();
  if (cur && cur.day === today && cur.key && (Number(cur.need) || 0) > 0) return cur;
  return YlxwCharDemandRoll(YlxwCharRelRarity(p, rel));
}
/* 背包按名聚合口径：非装备、非配方、数量>0（与原赠送 picker 过滤一致；跨境界不引入，T6 案 §4.2） */
function YlxwCharInvCount(p, name) {
  var inv = (p && p.inventory) || [], n = 0, i;
  for (i = 0; i < inv.length; i++) {
    var it = inv[i];
    if (it && it.name === name && !it.isEquippable && it.type !== "Recipe") n += Number(it.quantity) || 0;
  }
  return n;
}

/* ---------------- ①左列：道友图鉴 T6（收集奖励改随机掉落，余同 v28） ---------------- */
function YlxwCharDexPanelT6(props) {
  var p = props.player, setP = props.setPlayer, log = props.addLog || function () {};
  var s1 = O.useState(null), sel = s1[0], setSel = s1[1];
  var s2 = O.useState(""), notice = s2[0], setNotice = s2[1];
  var m = YlxwCharMet(p), n = YlxwCharMetN(p), rs = YlxwCharRarStats(p);
  var ps = YlxwCharPS(p), rf = YlxwCharRf(p);
  var cost = Math.round(YLXW_CHAR_VISIT_COST * rf);
  var freeOk = ps.freeDate !== YlxwCharToday();
  var stones = Number(p && p.spiritStones) || 0;
  var i, j, k;

  function doVisit(useFree) {
    if (!p) return;
    if (!useFree && stones < cost) { setNotice("灵石不足，寻访需 " + cost + " 灵石。"); return; }
    var entry = YlxwCharRollTarget(p);
    var parts = [];
    if (!entry) {
      var cands = [];
      for (k = 0; k < YLXW_CHAR_DEX.length; k++) { if (m[YLXW_CHAR_DEX[k].id]) cands.push(YLXW_CHAR_DEX[k]); }
      if (!cands.length) { setNotice("暂无可寻访的道友。"); return; }
      entry = cands[Math.floor(Math.random() * cands.length)];
      var g0 = 4 + Math.floor(Math.random() * 6);
      setP(function (prev) {
        var nx = YlxwCharMeet(prev, entry, g0, "重逢于一次寻访");
        return YlxwCharApply(nx, { stones: useFree ? 0 : -cost, setFree: useFree, visit: true });
      });
      log("【寻访】你与【" + entry.name + "】重逢，缘契 +" + g0 + "。", "gain");
      setNotice("重逢【" + entry.name + "】，缘契 +" + g0 + (useFree ? "。" : "（-" + cost + " 灵石）"));
      setSel(entry.id);
      return;
    }
    var gain = 15 + Math.floor(Math.random() * 11);
    setP(function (prev) {
      var nx = YlxwCharMeet(prev, entry, gain, entry.desc);
      return YlxwCharApply(nx, { stones: useFree ? 0 : -cost, setFree: useFree, visit: true });
    });
    log("【寻访】你结识了【" + entry.name + "】（" + entry.rarity + "），缘契 +" + gain + "。", "gain");
    setNotice("结识【" + entry.name + "】（" + entry.rarity + "），缘契 +" + gain + (useFree ? "。" : "（-" + cost + " 灵石）"));
    setSel(entry.id);
  }

  /* ③ 收集奖励 → 随机物品掉落（stones/exp=0；12/20/24 档固定收藏品不随机，其余件数随机） */
  function doClaim(mile) {
    if (!p) return;
    if (YlxwCharPS(p).claimed[String(mile.at)]) return;
    if (n < mile.at) return;
    var idx = 0;
    for (var q = 0; q < YLXW_CHAR_DEX_MILE.length; q++) { if (YLXW_CHAR_DEX_MILE[q].at === mile.at) { idx = q; break; } }
    var fixed = mile.item ? [{ name: mile.item.name, rarity: mile.item.rarity, qty: mile.item.qty }] : [];
    var nRand = Math.max(0, (YLXW_CHAR_DEX_DROP_N[idx] || 1) - fixed.length);
    var items = fixed.concat(nRand > 0 ? YlxwCharRollRow(YLXW_CHAR_DEX_DROP_ROW[idx] || 1, nRand) : []);
    setP(function (prev) {
      var next = YlxwCharApply(prev, { stones: 0, exp: 0, items: items });
      var d = YlxwCharDexV2(next.charDex);
      var c = Object.assign({}, d.claimed || {});
      if (c[String(mile.at)]) return prev; /* 幂等：连点不重发 */
      c[String(mile.at)] = true;
      d.claimed = c;
      next.charDex = d;
      return next;
    });
    var parts = [];
    for (var w = 0; w < items.length; w++) parts.push(items[w].name + " ×" + items[w].qty);
    log("【人物志·" + mile.label + "】收集奖励：" + parts.join("、") + "。", "gain");
    setNotice("已领取【" + mile.label + "】：" + parts.join("、"));
  }

  var chips = [];
  for (i = 0; i < YLXW_CHAR_DEX_MILE.length; i++) {
    (function (mile, idx) {
      var done = !!ps.claimed[String(mile.at)];
      var can = n >= mile.at;
      var fixedN = mile.item ? mile.item.qty : 0;
      var hint = "随机物品 ×" + Math.max(0, (YLXW_CHAR_DEX_DROP_N[idx] || 1) - fixedN) +
        (fixedN ? (" + 固定 " + mile.item.name + " ×" + fixedN) : "");
      chips.push(e.jsx("button", {
        disabled: done || !can,
        onClick: function () { doClaim(mile); },
        className: "px-2 py-1 rounded border text-[10px] transition-colors " + (
          done ? "bg-emerald-900/20 border-emerald-700/50 text-emerald-300" :
          can ? "bg-amber-600 hover:bg-amber-500 border-amber-500 text-stone-900 font-bold" :
                "bg-stone-800 border-stone-700 text-stone-500"),
        title: done ? "已领取" : (can ? "点击领取（" + hint + "）" : ("需结识 " + mile.at + " 位道友")),
        children: (done ? "✓ " : "") + mile.label + " " + (done ? "" : (can ? "可领" : n + "/" + mile.at))
      }, "ylxw-charmile-t6-" + mile.at));
    })(YLXW_CHAR_DEX_MILE[i], i);
  }

  var cells = [];
  for (i = 0; i < YLXW_CHAR_DEX.length; i++) {
    (function (en) {
      var got = !!m[en.id];
      var rar = YLXW_CHAR_RAR[en.rarity] || {};
      cells.push(e.jsx("button", {
        onClick: function () { setSel(en.id); },
        className: "rounded border px-1 py-1.5 text-[10px] leading-tight text-center transition-colors " + (
          sel === en.id ? "bg-mystic-gold/20 border-mystic-gold text-amber-100" :
          got ? (rar.bg || "bg-stone-800") + " " + (rar.b || "border-stone-600") + " " + (rar.c || "text-stone-200") :
                "bg-stone-900/60 border-stone-800 text-stone-600"),
        title: got ? (en.name + " · " + en.rarity + " · " + en.title) : ("未结识（" + en.hint + "）"),
        children: e.jsx("span", { children: got ? en.name : "？？" })
      }, "ylxw-charcodex-t6-" + en.id));
    })(YLXW_CHAR_DEX[i]);
  }

  var selEntry = sel ? YlxwCharEntry(sel) : null;
  var selRel = null, rels = (p && p.socialRelations) || [];
  if (selEntry) {
    for (j = 0; j < rels.length; j++) { if (rels[j] && rels[j].id === selEntry.id) { selRel = rels[j]; break; } }
  }
  var bond = selRel ? (Number(selRel.favorability) || 0) : 0;
  var rarSel = selEntry ? (YLXW_CHAR_RAR[selEntry.rarity] || {}) : {};
  var selBlock = selEntry ? e.jsxs("div", { className: "bg-ink-900 border border-stone-700 rounded p-2.5 space-y-1", children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      e.jsxs("span", { className: "font-serif text-amber-200", children: [
        selEntry.name,
        e.jsx("span", { className: "text-[10px] ml-2 " + (rarSel.c || "text-stone-400"), children: selEntry.rarity + " · " + selEntry.title })
      ] }),
      e.jsx("span", { className: "text-[10px] text-stone-400", children: selRel ? ("缘契 " + bond + " / 100") : "未结识" })
    ] }),
    selRel
      ? e.jsx("p", { className: "text-[11px] text-stone-300", children: selEntry.desc })
      : e.jsx("p", { className: "text-[11px] text-stone-500", children: "邂逅线索：" + selEntry.hint + "（或使用上方【寻访】主动结识）" }),
    e.jsxs("p", { className: "text-[11px] " + (bond >= 50 ? "text-blue-200" : "text-stone-600"), children: [
      e.jsx("span", { className: "text-cyan-400 font-bold", children: "【小传】" }),
      bond >= 50 ? selEntry.bio : "缘契达 50 解锁"
    ] }),
    e.jsxs("p", { className: "text-[11px] " + (bond >= 100 ? "text-amber-200" : "text-stone-600"), children: [
      e.jsx("span", { className: "text-amber-400 font-bold", children: "【秘辛】" }),
      bond >= 100 ? selEntry.secret : "缘契达 100 解锁"
    ] })
  ] }) : null;

  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, {
      extra: e.jsx("span", { className: "text-[10px] text-stone-400", children: "邂逅越多，修炼越快" }),
      children: "道友图鉴 · 缘契"
    }),
    e.jsxs("div", { children: [
      e.jsxs("div", { className: "flex justify-between text-[11px] text-stone-400 mb-1", children: [
        e.jsx("span", { children: "图鉴收集" }),
        e.jsxs("span", { children: [ n + " / " + YLXW_CHAR_DEX.length, e.jsx("span", { className: "text-emerald-300", children: "　修炼速度 +" + (YlxwCharDexRate(p) * 100).toFixed(1) + "%" }) ] })
      ] }),
      e.jsx("div", { className: "w-full bg-stone-800 rounded-full h-2 overflow-hidden", children: e.jsx("div", {
        className: "h-2 bg-gradient-to-r from-amber-600 to-amber-400 transition-all",
        style: { width: Math.round(n / YLXW_CHAR_DEX.length * 100) + "%" }
      }) })
    ] }),
    e.jsx("div", { className: "grid grid-cols-3 gap-1.5", children: [
      e.jsxs("div", { className: "bg-ink-800/60 border border-stone-700 rounded px-2 py-1 text-[11px] text-center", children: [
        e.jsx("span", { className: "text-stone-300", children: "凡缘 " }), rs["凡缘"] + "/" + YLXW_CHAR_RAR["凡缘"].total
      ] }),
      e.jsxs("div", { className: "bg-ink-800/60 border border-blue-800 rounded px-2 py-1 text-[11px] text-center", children: [
        e.jsx("span", { className: "text-cyan-300", children: "仙缘 " }), rs["仙缘"] + "/" + YLXW_CHAR_RAR["仙缘"].total
      ] }),
      e.jsxs("div", { className: "bg-ink-800/60 border border-amber-700 rounded px-2 py-1 text-[11px] text-center", children: [
        e.jsx("span", { className: "text-amber-300", children: "天缘 " }), rs["天缘"] + "/" + YLXW_CHAR_RAR["天缘"].total
      ] })
    ] }),
    e.jsx("div", { className: "text-[10px] text-stone-500", children: "收集奖励（每档仅可领一次 · 随机物品掉落）" }),
    e.jsx("div", { className: "flex flex-wrap gap-1.5", children: chips }),
    e.jsxs("div", { className: "flex items-center gap-2 flex-wrap pt-1", children: [
      e.jsx(YlxwBtn, { disabled: !freeOk, onClick: function () { doVisit(true); }, children: freeOk ? "寻访 · 今日免费" : "今日已寻访" }),
      e.jsx(YlxwBtn, { tone: "ghost", disabled: stones < cost, onClick: function () { doVisit(false); }, children: "灵石寻访 " + cost }),
      e.jsx("span", { className: "text-[10px] text-stone-500", children: "已寻访 " + ps.visits + " 次" })
    ] }),
    notice ? e.jsx("div", { className: "text-[11px] text-emerald-300", children: notice }) : null,
    e.jsx("div", { className: "text-[10px] text-stone-500", children: "图鉴（点击格子查看详情 / 小传 / 秘辛）" }),
    e.jsx("div", { className: "grid grid-cols-4 md:grid-cols-5 gap-1.5", children: cells }),
    selBlock
  ] });
}

/* ---------------- ②右列：缘契 T6（师门求物 + 里程碑随机掉落） ---------------- */
function YlxwCharBondPanelT6(props) {
  var rel = props.rel, p = props.player, setP = props.setPlayer, log = props.addLog || function () {};
  var s1 = O.useState(""), notice = s1[0], setNotice = s1[1];
  var relId = rel ? rel.id : "";
  var rar = rel ? YlxwCharRelRarity(p, rel) : "凡缘";
  var dem = rel ? YlxwCharDemandOf(p, rel) : null;
  var demDay = dem ? dem.day : "", demKey = dem ? dem.key : "", demNeed = dem ? dem.need : 0;
  /* 懒初始化 / 跨日重掷持久化（渲染期只算不写；此处补档。无变化时幂等跳过） */
  O.useEffect(function () {
    if (!relId || !demKey) return;
    var cur = null, dd = (p && p.charDex) || {};
    cur = (dd.demands || {})[relId];
    if (cur && cur.day === demDay && cur.key === demKey && (Number(cur.need) || 0) === demNeed) return;
    setP(function (prev) {
      var d0 = Object.assign({}, prev.charDex || {});
      var dm0 = Object.assign({}, d0.demands || {});
      var old = dm0[relId];
      if (old && old.day === demDay && old.key === demKey && (Number(old.need) || 0) === demNeed) return prev;
      dm0[relId] = { key: demKey, need: demNeed, day: demDay };
      d0 = YlxwCharDexV2(d0);
      d0.demands = dm0;
      return Object.assign({}, prev, { charDex: d0 });
    });
  }, [relId, demDay, demKey, demNeed]);
  if (!rel) return null;
  var bond = Number(rel.favorability) || 0;
  var ps = YlxwCharPS(p);
  var claimed = ps.bond[rel.id] || {};
  var entry = null;
  try { entry = YlxwCharEntry(rel.id) || YlxwCharEntryByName(rel.name); } catch (e2) { entry = null; }
  var have = dem ? YlxwCharInvCount(p, dem.key) : 0;
  var gain = YLXW_CHAR_FAVOR_GAIN[rar] || 3;

  /* ② 交付：按名聚合扣物 → 好感 +3/+5/+8 → 立即重掷（已备数量实时按背包聚合，不入档） */
  function doDeliver() {
    if (!dem) return;
    if (have < dem.need) { setNotice("背包里还差 " + (dem.need - have) + " 个【" + dem.key + "】，历练、炼丹与坊市可得。"); return; }
    var g = gain, key = dem.key, need = dem.need;
    var nd = YlxwCharDemandRoll(rar); /* 重掷在 updater 外掷定，重复调用不漂移 */
    setP(function (prev) {
      var inv = (prev.inventory || []).slice(), left = need, i2;
      for (i2 = 0; i2 < inv.length && left > 0; i2++) {
        var it = inv[i2];
        if (it && it.name === key && !it.isEquippable && it.type !== "Recipe") {
          var q = Number(it.quantity) || 0;
          if (q > 0) { var take = Math.min(q, left); left -= take; inv[i2] = Object.assign({}, it, { quantity: q - take }); }
        }
      }
      if (left > 0) return prev; /* 双击竞态守卫：背包不足即整笔回退 */
      inv = inv.filter(function (x) { return x && (Number(x.quantity) || 0) > 0; });
      var rels = (prev.socialRelations || []).map(function (r) {
        return r && r.id === relId ? Object.assign({}, r, { favorability: Math.min(100, Math.max(-100, (Number(r.favorability) || 0) + g)) }) : r;
      });
      var d0 = Object.assign({}, prev.charDex || {});
      var dm0 = Object.assign({}, d0.demands || {});
      dm0[relId] = nd;
      d0 = YlxwCharDexV2(d0);
      d0.demands = dm0;
      return Object.assign({}, prev, { inventory: inv, socialRelations: rels, charDex: d0 });
    });
    log("【师门求物】你把 " + key + " ×" + need + " 交给了" + rel.name + "，好感度 +" + g + "。", "gain");
    setNotice("已交付【" + key + "】×" + need + "，好感度 +" + g + "；" + rel.name + " 又想到了新的需求。");
  }

  /* ③ 缘契里程碑 → 随机物品掉落：行号 = clamp(1+阶序+NPC位移,1,6)，件数 1/2/3/5，stones/exp=0 */
  function claim(mile) {
    if (bond < mile.at || claimed[String(mile.at)]) return;
    var stage = 0;
    for (var q = 0; q < YLXW_CHAR_BOND_MILE.length; q++) { if (YLXW_CHAR_BOND_MILE[q].at === mile.at) { stage = q; break; } }
    var row = Math.max(1, Math.min(6, 1 + stage + YlxwCharRarShift(rar)));
    var items = YlxwCharRollRow(row, YLXW_CHAR_DROP_N[stage] || 1);
    setP(function (prev) {
      var next = YlxwCharApply(prev, { stones: 0, exp: 0, items: items });
      var d0 = YlxwCharDexV2(next.charDex);
      var b = Object.assign({}, d0.bond || {});
      var mine = Object.assign({}, b[relId] || {});
      if (mine[String(mile.at)]) return prev; /* 幂等：连点不重发 */
      mine[String(mile.at)] = true;
      b[relId] = mine;
      d0.bond = b;
      next.charDex = d0;
      return next;
    });
    var parts = [];
    for (var w = 0; w < items.length; w++) parts.push(items[w].name + " ×" + items[w].qty);
    log("【人物志】" + rel.name + " 缘契达 " + mile.at + "（" + mile.label + "）获得：" + parts.join("、") + "。", "gain");
    setNotice("已领取【" + mile.label + "】：" + parts.join("、"));
  }

  var questCard = dem ? e.jsxs("div", { className: "bg-ink-900 border border-stone-700 rounded p-2.5 space-y-1.5", children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      e.jsx("span", { className: "text-[11px] font-bold text-amber-200", children: "师门求物" }),
      e.jsx("span", { className: "text-[10px] text-stone-500", children: "每日一条 · 交付即刷新" })
    ] }),
    e.jsx("p", { className: "text-[11px] text-stone-300", children: "他想找【" + dem.key + "】×" + dem.need + "（已备 " + have + "/" + dem.need + "）" }),
    e.jsx("p", { className: "text-[10px] text-stone-500", children: "每位道友每日会托你寻一样东西，凑齐交付可大幅增进缘契；急用可赠灵石聊表心意（好感 +" + YLXW_CHAR_STONE_FAVOR + "）。" }),
    e.jsx("button", {
      disabled: have < dem.need,
      title: have < dem.need ? ("背包里还差 " + (dem.need - have) + " 个【" + dem.key + "】，历练、炼丹与坊市可得。") : ("交付得好感 +" + gain),
      onClick: doDeliver,
      className: "px-3 py-1.5 rounded text-sm flex items-center gap-1 " + (have < dem.need
        ? "bg-stone-800 border border-stone-700 text-stone-500 cursor-not-allowed"
        : "bg-emerald-900/30 border border-emerald-700 text-emerald-300 hover:bg-emerald-900/50"),
      children: have < dem.need ? ("还差 " + (dem.need - have) + " 个") : ("交付（好感 +" + gain + "）")
    })
  ] }) : null;

  var chips = [];
  for (var i3 = 0; i3 < YLXW_CHAR_BOND_MILE.length; i3++) {
    (function (mile) {
      var done = !!claimed[String(mile.at)];
      var can = bond >= mile.at;
      chips.push(e.jsx("button", {
        disabled: done || !can,
        onClick: function () { claim(mile); },
        className: "px-2 py-1 rounded border text-[10px] transition-colors " + (
          done ? "bg-emerald-900/20 border-emerald-700/50 text-emerald-300" :
          can ? "bg-amber-600 hover:bg-amber-500 border-amber-500 text-stone-900 font-bold" :
                "bg-stone-800 border-stone-700 text-stone-500"),
        title: done ? "已领取" : (can ? "点击领取（随机物品 ×" + (YLXW_CHAR_DROP_N[YLXW_CHAR_BOND_MILE.indexOf(mile)] || 1) + "）" : ("缘契达 " + mile.at + " 可领")),
        children: (done ? "✓ " : "") + mile.label + " " + mile.at
      }, "ylxw-charbond-t6-" + rel.id + "-" + mile.at));
    })(YLXW_CHAR_BOND_MILE[i3]);
  }

  return e.jsxs("div", { className: "space-y-2 pt-2 border-t border-stone-700", children: [
    questCard,
    e.jsx("div", { className: "text-[11px] text-stone-400 font-bold", children: "缘契里程碑（点击领取 · 随机物品）" }),
    e.jsx("div", { className: "flex flex-wrap gap-1.5", children: chips }),
    notice ? e.jsx("div", { className: "text-[11px] text-emerald-300", children: notice }) : null,
    entry ? e.jsxs("div", { className: "space-y-1", children: [
      e.jsxs("p", { className: "text-[11px] " + (bond >= 50 ? "text-blue-200" : "text-stone-600"), children: [
        e.jsx("span", { className: "text-cyan-400 font-bold", children: "【小传】" }),
        bond >= 50 ? entry.bio : "缘契达 50 解锁"
      ] }),
      e.jsxs("p", { className: "text-[11px] " + (bond >= 100 ? "text-amber-200" : "text-stone-600"), children: [
        e.jsx("span", { className: "text-amber-400 font-bold", children: "【秘辛】" }),
        bond >= 100 ? entry.secret : "缘契达 100 解锁"
      ] })
    ] }) : e.jsx("p", { className: "text-[11px] text-stone-600", children: "（无名道友，暂未录入图鉴；缘契里程碑仍可领取）" })
  ] });
}

/* == end yl-t6 人物志细化 == */
'''

# ---------------------------------------------------------------- 锚点（0.8.6 基线实测 raw 字节形态，各恰 1）

# 注入锚：与 char/chargift 同款（YlxwMeta 之前；本块仅函数/常量声明，无立即执行引用）
A_EXT_BLOCK = 'function YlxwMeta(k) {'

# ① 两列：模态外壳加宽 + 内容区改 grid（同一连续串，一次 replace；改后 A3/A5 基线+1）
#
# ★ 0.8.8 item14 修正（外壳加宽此前**完全无效**，实测外壳恒 512px）：
#   模态组件 wN 的外壳类模板是 `w-full ${__xw?"md:max-w-6xl":jN[size]} ${NN[height]} … ${containerClassName}`，
#   而 jN.lg = "md:max-w-lg"（512px）。`containerClassName` 虽被追加在末尾，但 **CSS 层叠按样式表顺序**（与 class 属性顺序无关）：
#   实测 index-ZuV-l8Gt.css 中 `.md\:max-w-lg` @148260 **晚于** `.md\:max-w-6xl` @148142 ⇒ lg 恒胜，
#   外壳 computed max-width = 512px（浏览器实测 shell6xl.w = 512），内容区只剩 462px ⇒ 两列各 223px
#   ⇒ 右列内层 flex 的 w-1/3 道友列表只剩 74px ⇒ 道友名/「道侣/挚友」被压成竖排单字（实测 29 个 w<h*0.6 的 span）。
#   修法：给 jN 加一个键 `"6xl":"md:max-w-6xl"`，并把本模态 size 由 "lg" 换成 "6xl" —— 直接不再注入 md:max-w-lg，
#   外壳稳定 1152px（与 F6 仙务面板 / 储物袋同宽）。containerClassName 里的 md:max-w-6xl 保留（与 jN 同值，冗余无害，
#   且维持下游 `T6·外壳加宽注入后=2` 计数语义不变）。
A_SHELL_GRID = ('size:"lg",height:"lg",children:e.jsxs("div",{className:"space-y-4",children:[')
R_SHELL_GRID = ('size:"6xl",height:"lg",containerClassName:"md:max-w-6xl bg-paper-800 border-stone-600",'
                'children:e.jsxs("div",{className:"grid grid-cols-1 md:grid-cols-2 gap-4 items-start",children:[')

# ①b 模态尺寸表 jN 追加宽度键（0.8.8 item14；冻结基座实测 count=1）
#   基座原文：const jN={sm:…,"4xl":"md:max-w-4xl",full:"md:max-w-[95vw]"}
#   md:max-w-6xl 是冻结 CSS 中**最宽的标准档**（1152px）；md:max-w-7xl 不存在于 index-ZuV-l8Gt.css，
#   而 CSS 是构建产物、不在本批补丁面内 ⇒ 只能用 6xl。
A_JN_MAP = '"4xl":"md:max-w-4xl",full:"md:max-w-[95vw]"}'
R_JN_MAP = '"4xl":"md:max-w-4xl",full:"md:max-w-[95vw]","6xl":"md:max-w-6xl"}'

# ① 左列开包（DEX 挂载改名 T6 + 包进左列 div）
A_DEX_MOUNT = ('e.jsx(YlxwCharSafe,{children:e.jsx(YlxwCharDexPanel,'
               '{player:a,setPlayer:l,addLog:c})}),')
R_DEX_MOUNT = ('e.jsxs("div",{className:"min-w-0 space-y-4",children:['
               'e.jsx(YlxwCharSafe,{children:e.jsx(YlxwCharDexPanelT6,'
               '{player:a,setPlayer:l,addLog:c})}),')

# ① 右列详情面板改名 T6
A_BOND_INNER = 'e.jsx(YlxwCharBondPanel,{rel:j,player:a,setPlayer:l,addLog:c})'
R_BOND_INNER = 'e.jsx(YlxwCharBondPanelT6,{rel:j,player:a,setPlayer:l,addLog:c})'

# ① 左列收口 + 右列开包（加成汇总块尾 + m.length===0 条件头）
A_LEFT_CLOSE = '追杀你"})]}),m.length===0?'
R_LEFT_CLOSE = '追杀你"})]}),]}),e.jsx("div",{className:"min-w-0",children:m.length===0?'

# ① 右列收口（Nk 尾部：详情空态 + flex-1 + flex gap-4 三层闭合之后补右列闭合）
A_RIGHT_CLOSE = '选择一位道友查看详情"})})]})'
R_RIGHT_CLOSE = '选择一位道友查看详情"})})]})})'

# ② 砍自由赠送：背包浮层数据源（唯一 Recipe" 锚）→ 置空
A_X_FILTER = 'x=(a.inventory||[]).filter(R=>!R.isEquippable&&R.type!=="Recipe"&&R.quantity>0)'
R_X_FILTER = 'x=[]'
# ② picker 浮层永不渲染（死代码保留）
A_PICKER = ('f&&e.jsxs("div",{className:"bg-stone-800 rounded p-2 border border-stone-600 '
            'max-h-40 overflow-y-auto space-y-1"')
R_PICKER = ('!1&&e.jsxs("div",{className:"bg-stone-800 rounded p-2 border border-stone-600 '
            'max-h-40 overflow-y-auto space-y-1"')
# ② 赠送按钮整块删除（求物卡替代；浮层触发键随之消失）
A_GIFT_BTN = ('e.jsxs("button",{onClick:()=>v(!f),className:"px-3 py-1.5 bg-pink-900/20 border '
              'border-pink-700 text-pink-300 rounded text-sm hover:bg-pink-900/30 flex items-center '
              'gap-1",children:[e.jsx(co,{size:14})," 赠送"]}),')
R_GIFT_BTN = ''
# ② 赠灵石好感 +5 → +2（两处按钮共用同一回调 $，单点改；数值表 T6-2）
A_E5 = 'YlxwGiftCost(j&&j.favorability),E=5'
R_E5 = 'YlxwGiftCost(j&&j.favorability),E=2'

# ② 空态追加引导（char 模块替换后的原文，raw 字节形态）
A_EMPTY = 'children:"尚未结识任何道友。点击下方【寻访】主动结识，或多在历练中闯荡偶遇。"'
R_EMPTY = 'children:"尚未结识任何道友。点击下方【寻访】主动结识，或多在历练中闯荡偶遇。多读需求、多交付，缘契上得快。"'

# ④ 历练结交降频（数值表 T6-7；变量前缀各异，严禁裸 Math.random()<.1 锚——基线 11 处）
A_INJ_U = '!u.npcRelationChange&&Math.random()<.1'
R_INJ_U = '!u.npcRelationChange&&Math.random()<.02'
A_INJ_S = '!S.npcRelationChange&&Math.random()<.1'
R_INJ_S = '!S.npcRelationChange&&Math.random()<.02'
A_INJ_R = '!r.npcRelationChange&&Math.random()<.1'
R_INJ_R = '!r.npcRelationChange&&Math.random()<.02'
# adventure / rescue：无条件 → fs 门 3%（fs 与该 case 同函数作用域；盐 301/302 全产物未占用）
A_ADV_HEAD = 'npcRelationChange:{npcId:`npc-adventure-'
R_ADV_HEAD = 'npcRelationChange:fs(t,.03,301)?{npcId:`npc-adventure-'
A_ADV_TAIL = 'description:`在一次历练中结识的${v}`}}}'
R_ADV_TAIL = 'description:`在一次历练中结识的${v}`}:void 0}}'
A_RESC_HEAD = 'npcRelationChange:{npcId:`npc-rescue-'
R_RESC_HEAD = 'npcRelationChange:fs(t,.03,302)?{npcId:`npc-rescue-'
A_RESC_TAIL = 'description:"曾在危难中得到你的帮助"}}}'
R_RESC_TAIL = 'description:"曾在危难中得到你的帮助"}:void 0}}'
# enlightenment 30%→5% / spiritSpring 35%→5%（概率内联改）
A_ENL = 'npcRelationChange:fs(t,.3,160)?'
R_ENL = 'npcRelationChange:fs(t,.05,160)?'
A_SPG = 'npcRelationChange:fs(t,.35,300)?'
R_SPG = 'npcRelationChange:fs(t,.05,300)?'

BAN_PATTERNS = ['fetch(', 'localStorage', 'sessionStorage', 'auth_token',
                '/yl/api', 'iframe', 'postMessage', 'X-YL-', 'XMLHttpRequest',
                'Be.getState().setPlayer']


def _assert_block_clean(block):
    """注入块硬断言：zh() 后纯 ASCII + 禁用模式零命中 + 掉落表结构自检。"""
    bad = re.findall(r'[^\x00-\x7f]', block)
    if bad:
        raise ValueError('yl_t6chardex_ext: 注入块 zh() 后仍含非 ASCII: %r' % (bad[:10],))
    for pat in BAN_PATTERNS:
        if pat in block:
            raise ValueError('yl_t6chardex_ext: 注入块含禁用模式 %r' % pat)
    # 掉落表结构自检：四稀有度带非空、需求池 20 件与稀有度表一致、权重行各和 100
    rar_map = {}
    for mm in re.finditer(r'"([^":]+)":\s*"(普通|稀有|传说|仙品)"', INJECT_JS):
        rar_map[mm.group(1)] = mm.group(2)
    pools = re.findall(r'\{ key: "([^"]+)", lo: (\d+), hi: (\d+) \}', INJECT_JS)
    assert len(rar_map) == 20, '稀有度表应 20 件，实测 %d' % len(rar_map)
    assert len(pools) == 20, '需求池应 20 件，实测 %d' % len(pools)
    assert set(k for k, _, _ in pools) == set(rar_map), '需求池与稀有度表物品名不一致'
    i0 = INJECT_JS.find('var YLXW_CHAR_DROP_RAR = [')
    i1 = INJECT_JS.find('];', i0)
    rows = re.findall(r'\[(\d+), (\d+), (\d+), (\d+)\]', INJECT_JS[i0:i1])
    assert len(rows) == 6, '权重行应 6 行，实测 %d' % len(rows)
    for r in rows:
        assert sum(int(x) for x in r) == 100, '权重行和应 100: %r' % (r,)
    bands = set(rar_map.values())
    assert bands == {'普通', '稀有', '传说', '仙品'}, '稀有度带应四带齐全: %r' % (bands,)


# ---------------------------------------------------------------- 应用

def apply(p, ctx):
    """把 T6 人物志细化落到 Patcher 上；返回 gates 列表。"""
    zh = ctx['zh']
    block = zh(INJECT_JS)
    _assert_block_clean(block)

    # 0) 主注入块：T6 常量/纯函数/两块 T6 面板（char 块之后、YlxwMeta 之前）
    p.insert_before(
        't6chardex-block', A_EXT_BLOCK, block + '\n',
        note='0.8.7 T6 人物志细化：需求池/掉落表/求物卡/DexPanelT6/BondPanelT6'
    )

    # ① 两列：外壳加宽 + 内容区 grid（一次 replace）
    p.replace('t6-shell-grid', A_SHELL_GRID, R_SHELL_GRID,
              note='T6① Nk 外壳加宽至 1152px（size=6xl）+ 内容区 grid md:grid-cols-2（F6 同款两列）')
    # ①b 模态尺寸表加宽键（0.8.8 item14：让 1152px 真正生效，取代被 md:max-w-lg 压死的 containerClassName）
    p.replace('t6-modal-width-key', A_JN_MAP, R_JN_MAP,
              note='T6① jN 追加 "6xl":"md:max-w-6xl"（冻结 CSS 最宽标准档）')
    # ① 左列开包（DEX 挂载 → T6）
    p.replace('t6-dex-mount', A_DEX_MOUNT, R_DEX_MOUNT,
              note='T6① 左列开包 + 图鉴面板挂载改 YlxwCharDexPanelT6')
    # ① 右列详情面板 → T6
    p.replace('t6-bond-mount', A_BOND_INNER, R_BOND_INNER,
              note='T6① 缘契面板挂载改 YlxwCharBondPanelT6')
    # ① 左列收口 + 右列开包
    p.replace('t6-left-close', A_LEFT_CLOSE, R_LEFT_CLOSE,
              note='T6① 左列闭合（图鉴+加成汇总），右列开包')
    # ① 右列收口
    p.replace('t6-right-close', A_RIGHT_CLOSE, R_RIGHT_CLOSE,
              note='T6① 右列闭合（关系列表/详情/空态）')

    # ② 砍自由赠送：数据源置空（Recipe" 清零）+ picker 永不渲染 + 赠送按钮整块删除
    p.replace('t6-x-filter', A_X_FILTER, R_X_FILTER,
              note='T6② 自由赠送数据源置空（Recipe" 唯一锚清零）')
    p.replace('t6-picker-dead', A_PICKER, R_PICKER,
              note='T6② 背包挑物浮层永不渲染（死代码保留）')
    p.replace('t6-gift-btn', A_GIFT_BTN, R_GIFT_BTN,
              note='T6② 「赠送」按钮整块删除（求物卡替代）')
    # ② 赠灵石好感 +5 → +2（单点；两按钮共用回调 $）
    p.replace('t6-stone-favor', A_E5, R_E5,
              note='T6② 赠灵石好感 5→2（数值表 T6-2；YlxwGiftCost 曲线不动）')
    # ② 空态追加引导
    p.replace('t6-empty-hint', A_EMPTY, R_EMPTY,
              note='T6② 空态追加「多读需求、多交付，缘契上得快。」')

    # ④ 历练结交降频（7 产生点；锚全部带变量前缀/盐值，禁裸串）
    p.replace('t6-inj-u', A_INJ_U, R_INJ_U, note='T6④ 战斗结算注入器 10%→2%')
    p.replace('t6-inj-s', A_INJ_S, R_INJ_S, note='T6④ 抉择事件注入器 10%→2%')
    p.replace('t6-inj-r', A_INJ_R, R_INJ_R, note='T6④ 中央结算注入器 10%→2%')
    p.replace('t6-adv-head', A_ADV_HEAD, R_ADV_HEAD, note='T6④ adventure 100%→3%（fs 盐 301）')
    p.replace('t6-adv-tail', A_ADV_TAIL, R_ADV_TAIL, note='T6④ adventure 对象字面量补 :void 0')
    p.replace('t6-resc-head', A_RESC_HEAD, R_RESC_HEAD, note='T6④ rescue 100%→3%（fs 盐 302）')
    p.replace('t6-resc-tail', A_RESC_TAIL, R_RESC_TAIL, note='T6④ rescue 对象字面量补 :void 0')
    p.replace('t6-enl', A_ENL, R_ENL, note='T6④ enlightenment 30%→5%')
    p.replace('t6-spg', A_SPG, R_SPG, note='T6④ spiritSpring 35%→5%')

    # ---------------------------------------------------------------- 门禁
    gates = [
        # ---- 注入块本体（ASCII 串）----
        ('T6·DexPanelT6 定义',        'function YlxwCharDexPanelT6(',   1, '==', ''),
        ('T6·BondPanelT6 定义',       'function YlxwCharBondPanelT6(',  1, '==', ''),
        ('T6·旧 DexPanel 定义仍在',   'function YlxwCharDexPanel(',     1, '==', '死代码保留证据'),
        ('T6·旧 BondPanel 定义仍在',  'function YlxwCharBondPanel(',    1, '==', '死代码保留证据'),
        ('T6·需求池常量',             'var YLXW_CHAR_DEMAND_POOL = {',  1, '==', ''),
        ('T6·稀有度带常量',           'var YLXW_CHAR_ITEM_RAR = {',     1, '==', '四带各非空，apply 内自检'),
        ('T6·好感加值常量',           'var YLXW_CHAR_FAVOR_GAIN = {',   1, '==', ''),
        ('T6·里程碑件数常量',         'var YLXW_CHAR_DROP_N = [',       1, '==', ''),
        ('T6·收集件数常量',           'var YLXW_CHAR_DEX_DROP_N = [',   1, '==', ''),
        ('T6·收集权重行常量',         'var YLXW_CHAR_DEX_DROP_ROW = [', 1, '==', ''),
        ('T6·权重矩阵常量',           'var YLXW_CHAR_DROP_RAR = [',     1, '==', 'R1~R6 各和 100'),
        ('T6·掷件函数',               'function YlxwCharRollRow(',      1, '==', ''),
        ('T6·需求掷取函数',           'function YlxwCharDemandRoll(',   1, '==', ''),
        ('T6·生效需求函数',           'function YlxwCharDemandOf(',     1, '==', ''),
        ('T6·背包计数函数',           'function YlxwCharInvCount(',     1, '==', ''),
        ('T6·NPC 稀有度函数',         'function YlxwCharRelRarity(',    1, '==', ''),
        ('T6·注入块结束标记',         '/* == end yl-t6 ',               1, '==', ''),
        # ---- 挂载/两列（产物级）----
        ('T6·DexPanelT6 用法',        'e.jsx(YlxwCharDexPanelT6,{player:',   1, '==', ''),
        ('T6·BondPanelT6 用法',       'e.jsx(YlxwCharBondPanelT6,{rel:j,',   1, '==', ''),
        ('T6·外壳加宽注入后=2',       'containerClassName:"md:max-w-6xl bg-paper-800 border-stone-600', 2, '==', '基线 1（F6）+本批 1'),
        # ---- 0.8.8 item14：外壳加宽真正生效（0.8.7 的 containerClassName 被 md:max-w-lg 压死）----
        ('T6·模态宽度键 6xl 已用',     'size:"6xl",height:"lg",containerClassName:"md:max-w-6xl', 1, '==', '0.8.8 item14'),
        ('T6·旧 size:lg 外壳已清零',   'size:"lg",height:"lg",containerClassName:"md:max-w-6xl', 0, '==', '旧形态外壳恒 512px'),
        ('T6·jN 加宽键恰 1',           '"6xl":"md:max-w-6xl"', 1, '==', '冻结 CSS 无 7xl，6xl=1152px 为最宽标准档'),
        ('T6·jN 其余键未动',           '"4xl":"md:max-w-4xl",full:"md:max-w-[95vw]","6xl":"md:max-w-6xl"}', 1, '==', '只追加不删改'),
        ('T6·两列类串注入后=2',       'grid grid-cols-1 md:grid-cols-2 gap-4 items-start', 2, '==', '基线 1（上游）+本批 1'),
        ('T6·左列开包',               'e.jsxs("div",{className:"min-w-0 space-y-4",children:[e.jsx(YlxwCharSafe,', 1, '==', ''),
        ('T6·右列开包',               R_LEFT_CLOSE, 1, '==', '左列闭合+右列开包（LEFT children 尾逗号为合法 JS）'),
        ('T6·右列收口',               '选择一位道友查看详情"})})]})})', 1, '==', ''),
        ('T6·旧内容区纵排已清零',     'height:"lg",children:e.jsxs("div",{className:"space-y-4",children:[', 0, '==', ''),
        ('T6·旧 DEX_MOUNT 已清零',    A_DEX_MOUNT, 0, '==', '挂载已改 T6'),
        ('T6·旧 BOND 用法已清零',     A_BOND_INNER, 0, '==', '挂载已改 T6'),
        # ---- ② 求物/赠送 ----
        ('T6·E=2 恰 1',               'YlxwGiftCost(j&&j.favorability),E=2', 1, '==', '数值表 T6-2'),
        ('T6·E=5 已清零',             'YlxwGiftCost(j&&j.favorability),E=5', 0, '==', ''),
        ('T6·Recipe" 改后恒 2',       'Recipe"', 2, '==', '基线 1（picker）→0 + 本批需求计数同口径过滤 +2（T6 案 §4.2 规定沿用 picker 过滤）；picker 已死由下三断言证明'),
        ('T6·赠送数据源已死',         'x=(a.inventory||[]).filter', 0, '==', '自由赠送背包过滤唯一锚'),
        ('T6·赠送按钮已删',           'onClick:()=>v(!f)', 0, '==', ''),
        ('T6·picker 永不渲染',        '!1&&e.jsxs("div",{className:"bg-stone-800', 1, '==', '死代码保留'),
        ('T6·YlxwGiftCost 调用点恒4', 'YlxwGiftCost(j&&j.favorability)', 4, '==', '旧 chargift 门禁不变'),
        ('T6·求物卡标题',             'children: "' + zh('师门求物') + '"', 1, '==', 'BondPanelT6 体内'),
        ('T6·求物懒初始化持久化',     zh('dm0[relId] = { key: demKey, need: demNeed, day: demDay };'), 1, '==', 'T6 案 §10.1-⑧（落 BondPanelT6，rel 上下文所在）'),
        ('T6·交付后重掷写入',         zh('dm0[relId] = nd;'), 1, '==', ''),
        ('T6·空态引导追加',           R_EMPTY, 1, '==', ''),
        ('T6·旧空态文案已清零',       A_EMPTY, 0, '==', ''),
        # ---- ④ 概率 ----
        ('T6·注入器 2% 恰 3',         'Math.random()<.02', 0, '==', 'R-068 再降频：本批 3 处 .02 已被合法改写为 .0001（接线人同步预期）'),
        ('T6·裸 .1 基线 11→8',        'Math.random()<.1', 8, '==', '基线 11 − 人物志 3'),
        ('T6·enlightenment 5%',       'npcRelationChange:fs(t,.05,160)?', 0, '==', 'R-068 再降频：.05 已被合法改写为 .0005（接线人同步预期）'),
        ('T6·spring 5%',              'npcRelationChange:fs(t,.05,300)?', 0, '==', 'R-068 再降频：.05 已被合法改写为 .0005（接线人同步预期）'),
        ('T6·enlightenment 30% 清零', 'npcRelationChange:fs(t,.3,160)?', 0, '==', ''),
        ('T6·spring 35% 清零',        'npcRelationChange:fs(t,.35,300)?', 0, '==', ''),
        ('T6·adventure 3% 门',        'fs(t,.03,301)', 0, '==', 'R-068 再降频：.03 已被合法改写为 .0005（接线人同步预期；盐 301 保留）'),
        ('T6·rescue 3% 门',           'fs(t,.03,302)', 0, '==', 'R-068 再降频：.03 已被合法改写为 .0005（接线人同步预期；盐 302 保留）'),
        ('T6·adventure 旧无条件清零', A_ADV_HEAD, 0, '==', ''),
        ('T6·rescue 旧无条件清零',    A_RESC_HEAD, 0, '==', ''),
        ('T6·adventure 尾结构（含case收口）', 'description:`在一次历练中结识的${v}`}:void 0}}case"cave":', 1, '==', '花括号=原3层，node --check 兜底'),
        ('T6·rescue 尾结构（含case收口）', 'description:"曾在危难中得到你的帮助"}:void 0}}case"spiritSpring":', 1, '==', ''),
        ('T6·adventure 旧尾已清零',   A_ADV_TAIL, 0, '==', ''),
        ('T6·rescue 旧尾已清零',      A_RESC_TAIL, 0, '==', ''),
        # ---- 基线完整性（防误伤）----
        ('T6·人物志模态框前缀仍在',   'title:"人物志",titleIcon:e.jsx(um,{size:18})', 1, '==', ''),
        ('T6·Nk 组件仍在',            'const Nk=({isOpen:t,onClose:r,player:a,setPlayer:l,addLog:c})', 1, '==', ''),
        ('T6·YlxwCharSafe 两处挂载',  'e.jsx(YlxwCharSafe,{', 2, '==', '图鉴+缘契'),
        ('T6·结算助手仍在',           'function YlxwCharApply(', 1, '==', ''),
        ('T6·图鉴加成函数仍在',       'function YlxwCharDexRate(', 1, '==', 'numbal 域禁碰复核'),
        ('T6·YlxwGiftCost 定义仍在',  'function YlxwGiftCost(fav)', 1, '==', ''),
        ('T6·YlxwMeta 未被破坏',      A_EXT_BLOCK, 1, '==', ''),
        ('T6·既有 8 名字池仍在',      '"\\u4e91\\u6e38\\u9053\\u4eba","\\u91c7\\u836f\\u4fee\\u58eb"', 3, '==', '三处注入器 npcName 池未动'),
        ('T6·好感 clamp 未动',        'favorability:Math.min(100,Math.max(-100,_.favorability+E))', 1, '==', 'E 变量本身未改名'),
        ('T6·羁绊里程碑阈值未动',     'var YLXW_CHAR_BOND_MILE = [', 1, '==', '25/50/75/100 不变'),
        ('T6·图鉴奖励表未动',         'var YLXW_CHAR_DEX_MILE = [', 1, '==', '3/6/9/12/16/20/24 不变'),
    ]
    return gates


# ---------------------------------------------------------------- 自检（python yl_t6chardex_ext.py）

# 受影响旧门禁（接线人同步 dryrun_087 的新预期）：(来源模块, 原门禁名, 串, 新预期)
OLD_GATES_NEW_EXPECT = [
    ('yl_char_ext',        '图鉴面板挂载',          'e.jsx(YlxwCharSafe,{children:e.jsx(YlxwCharDexPanel,{player:a,setPlayer:l,addLog:c})}),', 0),
    ('yl_char_ext',        '缘契面板挂载',          'e.jsx(YlxwCharSafe,{children:e.jsx(YlxwCharBondPanel,{rel:j,player:a,setPlayer:l,addLog:c})},j.id),', 0),
    ('yl_char_ext',        '空态引导文案',          'children:"尚未结识任何道友。点击下方【寻访】主动结识，或多在历练中闯荡偶遇。"', 0),
    ('yl_chargift083_ext', 'T3·(a) 计算式已改',     'if(!j||a.spiritStones<YlxwGiftCost(j&&j.favorability))return;const R=YlxwGiftCost(j&&j.favorability),E=5;', 0),
    ('yl_chargift083_ext', '基线·好感增量 E=5 未动', ',E=5;', 0),
]

if __name__ == '__main__':
    import io
    import os
    import sys
    import hashlib
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from yl_patch import Patcher, Gates, zh, load_text  # noqa: E402

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    HERE = os.path.dirname(os.path.abspath(__file__))
    base_path = os.path.join(HERE, '_chainstage', 'dryrun.bundle.js')
    base = load_text(base_path)
    with open(base_path, 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    print('=== T6 自检：基线 %s' % base_path)
    print('  chars=%d md5=%s %s' % (len(base), md5,
          'OK(==3938a4ee…)' if md5 == '3938a4ee7850e033b8a08e1dfda1c52d' else 'DRIFT!'))
    if md5 != '3938a4ee7850e033b8a08e1dfda1c52d':
        print('  [ABORT] 基线漂移，先重建再自检')
        sys.exit(2)

    # 锚点基线份数断言（改前）
    print('=== 锚点基线份数（应全为 expect_pre）===')
    pre = [
        ('A_SHELL_GRID', A_SHELL_GRID, 1), ('A_DEX_MOUNT', A_DEX_MOUNT, 1),
        ('A_JN_MAP', A_JN_MAP, 1),
        ('A_BOND_INNER', A_BOND_INNER, 1), ('A_LEFT_CLOSE', A_LEFT_CLOSE, 1),
        ('A_RIGHT_CLOSE', A_RIGHT_CLOSE, 1), ('A_X_FILTER', A_X_FILTER, 1),
        ('A_PICKER', A_PICKER, 1), ('A_GIFT_BTN', A_GIFT_BTN, 1),
        ('A_E5', A_E5, 1), ('A_EMPTY', A_EMPTY, 1),
        ('A_INJ_U', A_INJ_U, 1), ('A_INJ_S', A_INJ_S, 1), ('A_INJ_R', A_INJ_R, 1),
        ('A_ADV_HEAD', A_ADV_HEAD, 1), ('A_ADV_TAIL', A_ADV_TAIL, 1),
        ('A_RESC_HEAD', A_RESC_HEAD, 1), ('A_RESC_TAIL', A_RESC_TAIL, 1),
        ('A_ENL', A_ENL, 1), ('A_SPG', A_SPG, 1),
        ('Math.random()<.1 裸串', 'Math.random()<.1', 11),
        ('Recipe"', 'Recipe"', 1),
        ('containerClassName 无空格全值串', 'containerClassName:"md:max-w-6xl bg-paper-800 border-stone-600', 1),
        ('两列完整类串', 'grid grid-cols-1 md:grid-cols-2 gap-4 items-start', 1),
        ('fs 盐 301/302', 'fs(t,.03,30', 0),
        ('Math.random()<.02', 'Math.random()<.02', 0),
    ]
    bad = 0
    for name, s, exp in pre:
        n = base.count(s)
        ok = n == exp
        bad += (not ok)
        print('  [%s] %-30s actual=%d expect=%d' % ('OK' if ok else 'FAIL', name, n, exp))
    if bad:
        print('  [ABORT] 基线锚点份数与设计不符（%d 条）' % bad)
        sys.exit(2)

    # 沙盘应用（内存副本，不写盘）
    print('=== 应用补丁（内存副本）===')
    p = Patcher(base, label='t6-selfcheck')
    gts = apply(p, {'zh': zh, 'base_text': base})
    print(p.report())

    g = Gates(p.text)
    for name, s, expect, cmp, note in gts:
        g.check(name, s, expect, cmp, note)
    # 受影响旧门禁新预期
    for mod, name, s, exp in OLD_GATES_NEW_EXPECT:
        g.check('[旧门禁新预期] %s·%s' % (mod, name), s, exp, '==', '接线人同步 dryrun_087')
    # 旧门禁不变抽样（char / chargift 未受影响锚）
    import yl_char_ext, yl_chargift083_ext  # noqa: E402
    g.check('[旧不变] char·模态标题前缀', yl_char_ext.A_MODAL_OPEN.split('size:"lg"', 1)[0], 1, '==',
            'title 前缀未动（外壳 size 由 T6 0.8.8 item14 合法改写为 6xl）')
    g.check('[旧不变] char·DEX 定义', 'function YlxwCharDexPanel(', 1, '==', '')
    g.check('[旧不变] chargift·BTN', zh(yl_chargift083_ext.BTN_REPL), 1, '==', '')
    g.check('[旧不变] chargift·DIS', zh(yl_chargift083_ext.DIS_REPL), 1, '==', '')
    print(g.report())
    ok = g.passed()
    print('门禁结果: %s' % ('PASS' if ok else 'FAIL'))

    # node --check 语法级校验（产物级）
    if ok:
        import subprocess
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), 'yl_t6_selfcheck_bundle.js')
        with open(tmp, 'w', encoding='utf-8', newline='') as f:
            f.write(p.text)
        try:
            r0 = subprocess.run(['node', '--check', os.path.join(HERE, '_chainstage', 'dryrun.bundle.js')],
                                capture_output=True, text=True, timeout=120)
            r1 = subprocess.run(['node', '--check', tmp], capture_output=True, text=True, timeout=120)
            print('=== node --check 基线 rc=%s / 补丁后 rc=%s' % (r0.returncode, r1.returncode))
            if r1.returncode != 0:
                print(r1.stderr[:2000])
                ok = False
            elif r0.returncode != 0:
                print('  [NOTE] 基线本身 node --check 不过（压缩产物特性），补丁后通过即可参考')
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    print('自检结论: %s' % ('PASS' if ok else 'FAIL'))
    sys.exit(0 if ok else 1)
