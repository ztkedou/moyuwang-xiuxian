# -*- coding: utf-8 -*-
"""
yl_sectgf_ext.py -- v28 宗门功法（宗门「功法阁」）客户端扩展

背景（用户反馈 #6：「宗门玩法中功法内容没有，可以参照网游添加上」）
  可达的宗门玩法 = 底部动作条「宗门」打开的 legacy 宗门模态（组件 lM / oM = memo(lM)），
  子页签为 宗门大殿 / 任务阁 / 藏宝阁 / **功法阁**。功法阁的数据源是
  `L=O.useMemo(()=>a.sectId?is.filter(X=>X.sectId===a.sectId):[],[a.sectId])`
  —— 即心法表 `is` 里带 `sectId` 的那几部。全表只有 `art-spirit-cloud` 绑了静态 id
  `sect-cloud`，而玩家实际入的是**动态生成的宗门 id**（实测 `sect-q07t7uh`），
  因此 `L` 恒为空 → 功法阁永远显示「该宗门暂无专属传承功法」。

本扩展**不改动既有任何宗门逻辑**，只做两件加性的事：
  1. 把功法阁的**空态分支**换成本扩展新增的「宗门传承功法」面板（12 部 · 4 阶 · 每部 5 层）；
  2. 在 xt(player) 的属性构造处叠加宗门功法加成（固定值，与心法六卷的百分比互补）。

设计要点
  * 资源 = **宗门贡献度** `player.sectContribution`（legacy 宗门体系既有字段，任务阁产出、
    藏宝阁消耗），不新增任何计数、不动任何既有数值常量。
  * 与既有「心法六卷」(`/api/gongfa`，页签 `gongfa`=心法，灵石 + 全属性百分比) 完全分离：
    本系统只给**定向固定值**，且受**职衔 + 境界**双门槛约束。
  * 加成挂在 `player.sectGongfa = { "<id>": level }`，由服务端 `updatePlayerSave` 写入
    （gm_revision++ → 客户端拉新档），客户端 xt 直接读该字段。
  * 客户端另有一次「自愈」：xt 首次调用时若 `player.sectId` 存在而 `player.sectGongfa`
    缺失，拉一次 `GET /api/sect/gongfa` 把层数合并回本地 player（每会话至多 1 次请求）。

导出（严格两个符号）：
  INJECT_JS  -- 注入的 JS 块（可含中文，build 侧统一 zh() 转义）
  apply(p, ctx) -> gates
"""

# ---------------------------------------------------------------- 数值表
# 单一事实源：本文件的 SECT_GF_CATALOG 与 srv_patch_sect_gongfa.py 的 SECT_GF_CATALOG
# 必须逐字一致（_test_sectgf.py 会做跨文件一致性断言）。
#
# 阶 → 每层贡献消耗 = TIER_BASE[tier] * level
SECT_GF_TIER_BASE = {1: 100, 2: 250, 3: 600, 4: 1500}
SECT_GF_MAX_LEVEL = 5
SECT_GF_TIER_NAME = {1: "入门", 2: "内门", 3: "真传", 4: "镇宗"}

SECT_GF_CATALOG = [
    # ---- 一阶 · 入门（外门弟子 / 炼气期）每层 100 贡献起 ----
    {"id": "sgf-t1-atk", "tier": 1, "name": "淬体拳谱", "grade": "黄",
     "rank": "外门弟子", "realm": "炼气期",
     "desc": "外门弟子入门拳谱，以拳意淬炼筋骨，出手更疾更重。",
     "per": {"attack": 8, "speed": 2}},
    {"id": "sgf-t1-def", "tier": 1, "name": "玄龟吐纳诀", "grade": "黄",
     "rank": "外门弟子", "realm": "炼气期",
     "desc": "效玄龟闭息之法，吐纳绵长，皮糙肉厚，耐打耐磨。",
     "per": {"defense": 6, "maxHp": 30}},
    {"id": "sgf-t1-psi", "tier": 1, "name": "引气归元篇", "grade": "黄",
     "rank": "外门弟子", "realm": "炼气期",
     "desc": "引天地灵气归入丹田，神识渐明，体魄日固。",
     "per": {"spirit": 5, "physique": 4}},
    # ---- 二阶 · 内门（内门弟子 / 筑基期）每层 250 贡献起 ----
    {"id": "sgf-t2-atk", "tier": 2, "name": "破军剑诀", "grade": "玄",
     "rank": "内门弟子", "realm": "筑基期",
     "desc": "内门剑修必修，剑走破军之势，一往无前，锋锐逼人。",
     "per": {"attack": 25, "speed": 6}},
    {"id": "sgf-t2-def", "tier": 2, "name": "磐石金身诀", "grade": "玄",
     "rank": "内门弟子", "realm": "筑基期",
     "desc": "以磐石之意铸身，气血浑厚，寻常法宝难伤分毫。",
     "per": {"defense": 20, "maxHp": 120}},
    {"id": "sgf-t2-psi", "tier": 2, "name": "灵犀通神篇", "grade": "玄",
     "rank": "内门弟子", "realm": "筑基期",
     "desc": "灵台通明，神识如犀，可窥敌先机，可养自身根骨。",
     "per": {"spirit": 16, "physique": 13}},
    # ---- 三阶 · 真传（真传弟子 / 金丹期）每层 600 贡献起 ----
    {"id": "sgf-t3-atk", "tier": 3, "name": "焚天烈焰经", "grade": "地",
     "rank": "真传弟子", "realm": "金丹期",
     "desc": "真传绝学，一身真火焚天灼地，出手便是燎原之势。",
     "per": {"attack": 80, "speed": 18}},
    {"id": "sgf-t3-def", "tier": 3, "name": "玄天不灭体", "grade": "地",
     "rank": "真传弟子", "realm": "金丹期",
     "desc": "玄天护体之法，肉身几近不灭，气血如渊，历劫不损。",
     "per": {"defense": 65, "maxHp": 420}},
    {"id": "sgf-t3-psi", "tier": 3, "name": "太虚元神篇", "grade": "地",
     "rank": "真传弟子", "realm": "金丹期",
     "desc": "凝炼太虚元神，神识外放可覆百里，根骨亦随之脱胎换骨。",
     "per": {"spirit": 50, "physique": 40}},
    # ---- 四阶 · 镇宗（长老 / 元婴期）每层 1500 贡献起 ----
    {"id": "sgf-t4-atk", "tier": 4, "name": "九霄戮仙典", "grade": "天",
     "rank": "长老", "realm": "元婴期",
     "desc": "镇宗杀伐之典，剑意直上九霄，仙神亦可戮之。",
     "per": {"attack": 250, "speed": 55}},
    {"id": "sgf-t4-def", "tier": 4, "name": "混沌镇岳经", "grade": "天",
     "rank": "长老", "realm": "元婴期",
     "desc": "以混沌之气镇守肉壳，一身气血重逾山岳，万法难侵。",
     "per": {"defense": 200, "maxHp": 1400}},
    {"id": "sgf-t4-psi", "tier": 4, "name": "万灵归元录", "grade": "天",
     "rank": "长老", "realm": "元婴期",
     "desc": "万灵归元，元神圆满，神识与根骨同臻化境。",
     "per": {"spirit": 160, "physique": 130}},
]


# ---------------------------------------------------------------- 注入代码
INJECT_JS = r'''
/* ===== yl-v28 宗门功法（宗门 · 功法阁 · 宗门传承） ===== */
/* 加性系统：只新增「功法阁」内的面板与 xt 固定值加成，不改动既有宗门任何逻辑。
   资源=player.sectContribution（宗门贡献度），加成落在 player.sectGongfa = {id: level}。 */
var YLXW_SECT_GF_MAX = 5;
var YLXW_SECT_GF_TIERS = [1, 2, 3, 4];
var YLXW_SECT_GF_TIER_BASE = { 1: 100, 2: 250, 3: 600, 4: 1500 };
var YLXW_SECT_GF_TIER_NAME = { 1: "入门", 2: "内门", 3: "真传", 4: "镇宗" };
var YLXW_SECT_GF_RANKS = ["外门弟子", "内门弟子", "真传弟子", "长老", "宗主"];
var YLXW_SECT_GF_STAT = { attack: "攻击", defense: "防御", maxHp: "气血", spirit: "神识", physique: "体魄", speed: "速度" };
var YLXW_SECT_GF = [
  { id: "sgf-t1-atk", tier: 1, name: "淬体拳谱", grade: "黄", rank: "外门弟子", realm: "炼气期", desc: "外门弟子入门拳谱，以拳意淬炼筋骨，出手更疾更重。", per: { attack: 8, speed: 2 } },
  { id: "sgf-t1-def", tier: 1, name: "玄龟吐纳诀", grade: "黄", rank: "外门弟子", realm: "炼气期", desc: "效玄龟闭息之法，吐纳绵长，皮糙肉厚，耐打耐磨。", per: { defense: 6, maxHp: 30 } },
  { id: "sgf-t1-psi", tier: 1, name: "引气归元篇", grade: "黄", rank: "外门弟子", realm: "炼气期", desc: "引天地灵气归入丹田，神识渐明，体魄日固。", per: { spirit: 5, physique: 4 } },
  { id: "sgf-t2-atk", tier: 2, name: "破军剑诀", grade: "玄", rank: "内门弟子", realm: "筑基期", desc: "内门剑修必修，剑走破军之势，一往无前，锋锐逼人。", per: { attack: 25, speed: 6 } },
  { id: "sgf-t2-def", tier: 2, name: "磐石金身诀", grade: "玄", rank: "内门弟子", realm: "筑基期", desc: "以磐石之意铸身，气血浑厚，寻常法宝难伤分毫。", per: { defense: 20, maxHp: 120 } },
  { id: "sgf-t2-psi", tier: 2, name: "灵犀通神篇", grade: "玄", rank: "内门弟子", realm: "筑基期", desc: "灵台通明，神识如犀，可窥敌先机，可养自身根骨。", per: { spirit: 16, physique: 13 } },
  { id: "sgf-t3-atk", tier: 3, name: "焚天烈焰经", grade: "地", rank: "真传弟子", realm: "金丹期", desc: "真传绝学，一身真火焚天灼地，出手便是燎原之势。", per: { attack: 80, speed: 18 } },
  { id: "sgf-t3-def", tier: 3, name: "玄天不灭体", grade: "地", rank: "真传弟子", realm: "金丹期", desc: "玄天护体之法，肉身几近不灭，气血如渊，历劫不损。", per: { defense: 65, maxHp: 420 } },
  { id: "sgf-t3-psi", tier: 3, name: "太虚元神篇", grade: "地", rank: "真传弟子", realm: "金丹期", desc: "凝炼太虚元神，神识外放可覆百里，根骨亦随之脱胎换骨。", per: { spirit: 50, physique: 40 } },
  { id: "sgf-t4-atk", tier: 4, name: "九霄戮仙典", grade: "天", rank: "长老", realm: "元婴期", desc: "镇宗杀伐之典，剑意直上九霄，仙神亦可戮之。", per: { attack: 250, speed: 55 } },
  { id: "sgf-t4-def", tier: 4, name: "混沌镇岳经", grade: "天", rank: "长老", realm: "元婴期", desc: "以混沌之气镇守肉壳，一身气血重逾山岳，万法难侵。", per: { defense: 200, maxHp: 1400 } },
  { id: "sgf-t4-psi", tier: 4, name: "万灵归元录", grade: "天", rank: "长老", realm: "元婴期", desc: "万灵归元，元神圆满，神识与根骨同臻化境。", per: { spirit: 160, physique: 130 } }
];

function YlxwSectGfById(id) {
  for (var i = 0; i < YLXW_SECT_GF.length; i++) { if (YLXW_SECT_GF[i].id === id) return YLXW_SECT_GF[i]; }
  return null;
}
function YlxwSectGfCost(tier, level) {
  var b = YLXW_SECT_GF_TIER_BASE[tier] || 0;
  var l = Math.max(1, Math.floor(Number(level) || 1));
  return b * l;
}
function YlxwSectGfLv(p, id) {
  var g = (p && p.sectGongfa) || {};
  return Math.min(YLXW_SECT_GF_MAX, Math.max(0, Math.floor(Number(g[id]) || 0)));
}
function YlxwSectGfRankIdx(r) { return YLXW_SECT_GF_RANKS.indexOf(String(r || "")); }
function YlxwSectGfRealmIdx(r) { return fe.indexOf(String(r || "")); }

/* 宗门功法总加成（固定值）。memo 以 player.sectGongfa 的引用为键：玩家对象不可变更新，
   层数不变时引用不变 → 缓存命中，避免 xt 热路径重复遍历。 */
var YlxwSectGfMemoRef = null, YlxwSectGfMemoVal = null;
function YlxwSectGfTotals(p) {
  var g = (p && p.sectGongfa) || null;
  if (g && YlxwSectGfMemoRef === g && YlxwSectGfMemoVal) return YlxwSectGfMemoVal;
  var out = { attack: 0, defense: 0, maxHp: 0, spirit: 0, physique: 0, speed: 0 };
  if (g) {
    for (var i = 0; i < YLXW_SECT_GF.length; i++) {
      var d = YLXW_SECT_GF[i], lv = YlxwSectGfLv(p, d.id);
      if (lv <= 0) continue;
      for (var k in d.per) { if (Object.prototype.hasOwnProperty.call(d.per, k)) out[k] += d.per[k] * lv; }
    }
    YlxwSectGfMemoRef = g; YlxwSectGfMemoVal = out;
  }
  YlxwSectGfEnsure(p);
  return out;
}
/* xt 单属性取值入口（6 次/次 xt 调用，内部走 memo） */
function YlxwSectGfV(p, k) { var t = YlxwSectGfTotals(p); return t[k] || 0; }

/* 会话内一次性自愈：若已入宗门但本地 player 缺 sectGongfa（例如被客户端权威存档覆盖），
   拉一次服务端层数并合并回本地 player。至多 1 次请求（成功/失败都不再重试；
   失败可由打开功法阁面板补拉）。 */
var YlxwSectGfBoot = 0;
function YlxwSectGfEnsure(p) {
  if (YlxwSectGfBoot !== 0) return;
  if (!p || !p.sectId) return;
  YlxwSectGfBoot = 1;
  try {
    YlxwSectGfList().then(function (j) { YlxwSectGfApply(j); YlxwSectGfBoot = 2; },
      function () { YlxwSectGfBoot = 2; });
  } catch (e) { YlxwSectGfBoot = 2; }
}

/* 把服务端层数合并进本地 player（只写层数，绝不回写贡献度：
   贡献度是客户端权威字段，回写服务端绝对值会抹掉尚未推送的本地收益）。 */
function YlxwSectGfApply(j) {
  if (!j || typeof j !== "object" || !j.levels) return;
  try {
    var st = Be.getState();
    if (!st || !st.player) return;
    var cur = st.player.sectGongfa || {}, next = {}, k, changed = false;
    for (k in cur) { if (Object.prototype.hasOwnProperty.call(cur, k)) next[k] = cur[k]; }
    for (k in j.levels) {
      if (!Object.prototype.hasOwnProperty.call(j.levels, k)) continue;
      var v = Math.min(YLXW_SECT_GF_MAX, Math.max(0, Math.floor(Number(j.levels[k]) || 0)));
      if (next[k] !== v) { next[k] = v; changed = true; }
    }
    if (!changed) return;
    st.setPlayer(function (p) { return p ? Object.assign({}, p, { sectGongfa: next }) : p; });
  } catch (e) {}
}

/* 复用既有鉴权封装 YlxwGet / YlxwPost（内部走 Xc：Bearer 头 + token 查询串 + 基础修订号头，
   不自造任何请求头，与既有仙务页签完全同一条通道） */
function YlxwSectGfList() { return YlxwGet("/sect/gongfa"); }
function YlxwSectGfLearn(id) { return YlxwPost("/sect/gongfa/learn", { id: id }); }
function YlxwSectGfUpgrade(id) { return YlxwPost("/sect/gongfa/upgrade", { id: id }); }

function YlxwSectGfPanel(props) {
  var p = (props && props.player) || null;
  var s1 = O.useState(null), data = s1[0], setData = s1[1];
  var s2 = O.useState(""), err = s2[0], setErr = s2[1];
  var s3 = O.useState(!1), busy = s3[0], setBusy = s3[1];
  var s4 = O.useState(0), ver = s4[0], setVer = s4[1];

  O.useEffect(function () {
    var alive = true;
    setBusy(!0); setErr("");
    YlxwSectGfList().then(function (j) {
      if (!alive) return;
      setData(j); YlxwSectGfApply(j);
    }, function (e) {
      if (alive) setErr((e && e.message) || "加载失败");
    }).then(function () { if (alive) setBusy(!1); });
    return function () { alive = !1; };
  }, [ver]);

  var act = function (gf, isUp) {
    if (busy || !gf) return;
    setBusy(!0); setErr("");
    // v28.1：本地扣贡献的**快照守卫**（与「交易行货款」同款）。
    var contribBefore = Math.max(0, Math.floor(Number((Be.getState().player || {}).sectContribution) || 0));
    var run = isUp ? YlxwSectGfUpgrade : YlxwSectGfLearn;
    run(gf.id).then(function (j) {
      try { ia((j && j.message) || "领悟成功"); } catch (e0) {}
      YlxwSectGfApply(j);
      // 本地同步扣除贡献：服务端已在同一笔请求里扣过。但若此时 6s 拉档已把服务端存档
      // 整包覆盖下来（sectContribution 已含这笔扣减），本地再减一次就是**双扣**。
      // 故只在「本地值仍等于请求前快照」时才落本地扣减，否则视为已同步、跳过。
      var lv = Math.min(YLXW_SECT_GF_MAX, Math.max(1, Math.floor(Number(j && j.level) || 1)));
      var cost = YlxwSectGfCost(gf.tier, lv);
      try {
        Be.getState().setPlayer(function (cur) {
          if (!cur) return cur;
          var now = Math.max(0, Math.floor(Number(cur.sectContribution) || 0));
          if (now !== contribBefore) return cur;
          return Object.assign({}, cur, { sectContribution: Math.max(0, now - cost) });
        });
      } catch (e1) {}
      try { YlxwDirty(); } catch (e2) {}
      setVer(function (v) { return v + 1; });
    }, function (e) {
      setErr((e && e.message) || "操作失败");
      try { Je((e && e.message) || "操作失败"); } catch (e3) {}
    }).then(function () { setBusy(!1); });
  };

  var contrib = Math.max(0, Math.floor(Number(p && p.sectContribution) || 0));
  var myRank = YlxwSectGfRankIdx(p && p.sectRank);
  var myRealm = YlxwSectGfRealmIdx(p && p.realm);
  var lvOf = function (id) { return YlxwSectGfLv(p, id); };
  var fmtPer = function (gf, n) {
    var o = [];
    for (var k in gf.per) { if (Object.prototype.hasOwnProperty.call(gf.per, k)) o.push((YLXW_SECT_GF_STAT[k] || k) + " +" + (gf.per[k] * n)); }
    return o.join("、");
  };
  var gradeCls = function (g) {
    return g === "天" ? "text-yellow-400" : g === "地" ? "text-purple-400" : g === "玄" ? "text-blue-400" : "text-stone-400";
  };

  var card = function (gf) {
    var L = lvOf(gf.id), maxed = L >= YLXW_SECT_GF_MAX, nextL = maxed ? L : L + 1;
    var cost = maxed ? 0 : YlxwSectGfCost(gf.tier, nextL);
    var realmOk = myRealm >= YlxwSectGfRealmIdx(gf.realm);
    var rankOk = myRank >= YlxwSectGfRankIdx(gf.rank);
    var payOk = contrib >= cost;
    var can = !maxed && realmOk && rankOk && payOk && !busy;
    var label = maxed ? "已大成" : !rankOk ? "职衔不足" : !realmOk ? "境界不足" : !payOk ? "贡献不足" : (L > 0 ? "领悟" : "学习");
    var btnCls = maxed
      ? "bg-mystic-jade/20 text-mystic-jade border border-mystic-jade/30 cursor-default"
      : (can ? "bg-mystic-gold/20 text-mystic-gold border border-mystic-gold hover:bg-mystic-gold/30"
             : "bg-stone-800 text-stone-600 border border-stone-700 cursor-not-allowed");
    return e.jsxs("div", {
      className: "bg-ink-800 p-4 rounded border flex flex-col " + (maxed ? "border-mystic-jade/30 bg-mystic-jade/5" : "border-stone-700"),
      children: [
        e.jsxs("div", { className: "flex justify-between items-start mb-2", children: [
          e.jsx("h5", { className: "font-serif font-bold text-stone-200", children: gf.name }),
          e.jsxs("span", {
            className: "text-[10px] px-1.5 py-0.5 rounded border border-stone-600 bg-stone-900/50 " + gradeCls(gf.grade),
            children: [gf.grade, "阶功法"]
          })
        ] }),
        e.jsx("p", { className: "text-xs text-stone-500 mb-3 flex-1", children: gf.desc }),
        e.jsxs("div", { className: "space-y-1 mb-3 text-[10px] text-stone-400", children: [
          e.jsxs("div", { children: ["层数: ", e.jsxs("span", { className: "text-stone-200 font-bold", children: [L, " / ", YLXW_SECT_GF_MAX] })] }),
          e.jsxs("div", { children: ["当前加成: ", e.jsx("span", { className: "text-mystic-gold", children: L > 0 ? fmtPer(gf, L) : "—" })] }),
          maxed ? null : e.jsxs("div", { children: ["下级加成: ", e.jsx("span", { className: "text-stone-300", children: fmtPer(gf, nextL) })] }),
          e.jsxs("div", { children: ["要求: ", e.jsx("span", { className: (realmOk && rankOk) ? "text-stone-300" : "text-red-400", children: [gf.rank, " · ", gf.realm] })] }),
          maxed ? null : e.jsxs("div", { children: ["消耗: ", e.jsxs("span", { className: payOk ? "text-mystic-gold" : "text-red-400", children: [cost, " 贡献"] })] })
        ] }),
        e.jsx("button", {
          onClick: function () { if (can) act(gf, L > 0); },
          disabled: !can,
          className: "w-full py-2 rounded text-xs transition-colors " + btnCls,
          children: label
        })
      ]
    }, gf.id);
  };

  var tierBlock = function (t) {
    var items = YLXW_SECT_GF.filter(function (gf) { return gf.tier === t; });
    var head = items[0] || {};
    return e.jsxs("div", { children: [
      e.jsxs("div", { className: "text-xs text-stone-400 mb-2", children: [
        YLXW_SECT_GF_TIER_NAME[t] + "功法 · 需 " + head.rank + " · " + head.realm + " · 每层 " + YLXW_SECT_GF_TIER_BASE[t] + " 贡献起"
      ] }),
      e.jsx("div", { className: "grid grid-cols-1 md:grid-cols-2 gap-4", children: items.map(card) })
    ] }, "sgft" + t);
  };

  var loaded = !!data;
  return e.jsxs("div", { className: "space-y-4", children: [
    e.jsxs("div", { className: "flex items-start justify-between gap-2 flex-wrap", children: [
      e.jsxs("div", { children: [
        e.jsx("h4", { className: "font-serif text-lg text-stone-200", children: "宗门传承功法" }),
        e.jsx("p", { className: "text-xs text-stone-500 mt-1", children: "宗门历代长老所留绝学，需以宗门贡献领悟；每部可领悟 5 层，加成随层数递增。" })
      ] }),
      e.jsxs("div", { className: "text-[10px] text-stone-400 text-right", children: [
        e.jsxs("div", { children: ["宗门贡献: ", e.jsx("span", { className: "text-white font-bold", children: contrib })] }),
        e.jsxs("div", { children: ["当前职衔: ", e.jsx("span", { className: "text-stone-200", children: (p && p.sectRank) || "—" })] })
      ] })
    ] }),
    err ? e.jsx(YlxwErr, { retry: function () { setVer(function (v) { return v + 1; }); }, children: err }) : null,
    err ? null : YLXW_SECT_GF_TIERS.map(tierBlock),
    (!loaded && !err) ? e.jsx("div", { className: "text-xs text-stone-500 text-center py-6", children: "加载中…" }) : null,
    busy ? e.jsx("div", { className: "text-[10px] text-stone-500 text-center", children: "同步中…" }) : null
  ] });
}
/* ===== end yl-v28 宗门功法 ===== */
'''


# ---------------------------------------------------------------- 补丁
# 1) 注入块：放在 YLXW 组件区（e / O / YlxwGet / YlxwPost / YlxwErr / fe / Be 均已在同模块作用域）
ANCHOR_INJECT = 'function YlxwTSect() {'

# 2) 功法阁空态 → 宗门传承功法面板（anchor 含中文，BASE 与 v27 实测各出现 1 次）
ANCHOR_LIBRARY_EMPTY = (
    'e.jsxs("div",{className:"text-center py-12 bg-ink-800 rounded border border-stone-700",'
    'children:[e.jsx(Sn,{className:"mx-auto text-stone-600 mb-4",size:48}),'
    'e.jsx("p",{className:"text-stone-500 font-serif",children:"该宗门暂无专属传承功法"})]})'
)
LIBRARY_EMPTY_NEW = 'e.jsx(YlxwSectGfPanel,{player:a})'

# 3) xt(player) 属性构造处叠加宗门功法固定值。
#    锚点是 xt 内 r 的字面构造式（早于心法/金丹法分支），与 v26n 的 YlxwStatExtras 补丁
#    互不重叠 → 与 build_v26n 的先后顺序无关。
ANCHOR_XT = ('const r={attack:t.attack,defense:t.defense,maxHp:t.maxHp,'
             'spirit:t.spirit,physique:t.physique,speed:t.speed}')
XT_NEW = ('const r={attack:t.attack+YlxwSectGfV(t,"attack"),'
          'defense:t.defense+YlxwSectGfV(t,"defense"),'
          'maxHp:t.maxHp+YlxwSectGfV(t,"maxHp"),'
          'spirit:t.spirit+YlxwSectGfV(t,"spirit"),'
          'physique:t.physique+YlxwSectGfV(t,"physique"),'
          'speed:t.speed+YlxwSectGfV(t,"speed")}')


def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}。返回 gates 列表。"""
    zh = ctx['zh']
    block = zh(INJECT_JS)

    # --- 1) 注入功法阁面板 + xt 取值入口 ---
    p.insert_before('sectgf-block', ANCHOR_INJECT, block + '\n',
                    note='宗门功法：功法阁面板 + xt 固定值加成入口')

    # --- 2) 功法阁空态 → 宗门传承功法面板 ---
    p.replace('sectgf-library', ANCHOR_LIBRARY_EMPTY, LIBRARY_EMPTY_NEW,
              expect=1, note='功法阁空态替换为宗门传承功法面板')

    # --- 3) xt 叠加宗门功法 ---
    p.replace('sectgf-xt', ANCHOR_XT, XT_NEW,
              expect=1, note='xt 属性构造处叠加宗门功法固定值')

    gates = [
        ('宗门功法注入块已入',        'function YlxwSectGfPanel(',            1, '==', ''),
        ('宗门功法 12 部目录',        'sgf-t4-psi',                          1, '>=', ''),
        ('功法阁空态已替换',          'e.jsx(YlxwSectGfPanel,{player:a})',   1, '==', ''),
        ('功法阁空态原句已消失',      zh('该宗门暂无专属传承功法'),            0, '==', '必须为 0（原空态已被面板取代）'),
        ('xt 已叠加宗门功法·攻击',    'attack:t.attack+YlxwSectGfV(t,"attack")',   1, '==', ''),
        ('xt 已叠加宗门功法·防御',    'defense:t.defense+YlxwSectGfV(t,"defense")', 1, '==', ''),
        ('xt 已叠加宗门功法·气血',    'maxHp:t.maxHp+YlxwSectGfV(t,"maxHp")',     1, '==', ''),
        ('xt 已叠加宗门功法·神识',    'spirit:t.spirit+YlxwSectGfV(t,"spirit")',   1, '==', ''),
        ('xt 已叠加宗门功法·体魄',    'physique:t.physique+YlxwSectGfV(t,"physique")', 1, '==', ''),
        ('xt 已叠加宗门功法·速度',    'speed:t.speed+YlxwSectGfV(t,"speed")',     1, '==', ''),
        ('xt 原构造式已消失',         'const r={attack:t.attack,defense:t.defense,maxHp:t.maxHp}', 0, '==', '必须为 0'),
        ('服务端接口·列表',           'YlxwGet("/sect/gongfa")',              1, '==', ''),
        ('服务端接口·学习',           'YlxwPost("/sect/gongfa/learn"',        1, '==', ''),
        ('服务端接口·升级',           'YlxwPost("/sect/gongfa/upgrade"',      1, '==', ''),
        ('加成读 player.sectGongfa',  'p && p.sectGongfa',                   1, '>=', ''),
        ('自愈拉取每会话至多一次',     'var YlxwSectGfBoot = 0;',              1, '==', ''),
        # v28.1 客户端扣贡献快照守卫（防与 6s 拉档整包覆盖叠加造成双扣）
        ('宗门功法·扣贡献快照守卫',    'if (now !== contribBefore) return cur;', 1, '==', ''),
        ('宗门功法·快照取自 store',    'var contribBefore = Math.max(0, Math.floor(Number((Be.getState().player || {}).sectContribution) || 0));', 1, '==', ''),
        ('宗门功法·旧无守卫扣减已清除', 'sectContribution: Math.max(0, Math.floor(Number(cur.sectContribution) || 0) - cost)', 0, '==', '必须为 0'),
        # 既有结构未被破坏
        ('功法阁原 grid 分支仍在',    'className:"grid grid-cols-1 md:grid-cols-2 gap-4",children:L.map', 1, '==', ''),
        ('宗门模态组件仍在',          'onLearnArt:m,onChallengeLeader:j,setItemActionLog:b', 1, '==', ''),
        ('xt 总属性函数仍在',         'const xt=t=>{',                        1, '==', ''),
        ('YlxwTSect 仍在',            'function YlxwTSect() {',               1, '==', ''),
    ]
    return gates
