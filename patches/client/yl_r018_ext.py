# -*- coding: utf-8 -*-
r"""
yl_r018_ext.py — R-018「妖灵培养重设计」客户端单模块（出口 + 6 维入口）

需求原文（用户）
--------------------------------------------------------------------------
  「妖灵培养可操作的选项太少了，只有喂养和嬉戏两个功能，拉策划师完全重新设计」

★ 打中的是「仙务·妖灵」（服务端 `pets` 表 / 面板 `YlxwTPet`），
  **不是**「灵宠系统」（客户端 `player.pets` / `YlxwPetShell`，R-017 地盘）。
  妖灵现值：喂满级 = 334 次 × 5,000 = 167 万灵石，`level/bond/rarity`
  **不进任何战斗公式 ⇒ 产出 0**。本案第一步造出口，第二步加投入。

设计案：`策划_妖灵培养重设计.md`（10 个决策点全部按建议执行）
--------------------------------------------------------------------------
  1 A 不合并        2 A 独立加算      3 A 转化率 0.06    4 A bond 封顶 500
  5 A 30k+随机+1~3  6 A 秘径 4 小时    7 A 买额度可接受   8 A 本批不做仙途任务
  9 A D5 灵纹第二版 10 C 精魄改为每 10 级一次

本模块（第一版范围：出口 + D1 + D2 + D3 + D4 + D6 归位）
--------------------------------------------------------------------------
  C0  注入模块级助手（`YlxwSpiritExtras` + 妖灵卡 / 入口 / 秘径 / 点化归位 行）
  C1  `YlxwTPet` 妖灵卡：`YlxwKv` 六字段 → `YlxwR18Card`（含妖灵之力 PP + 主人加成）
      + 紧接 `YlxwR18Panel`（三档进食 / 三种互动 / 买额度 / 秘径 / 点化 / 归位）
  C2  标题「今日嬉戏 x/y」→「今日互动 x/y」（D2 语义：嬉戏 → 三种互动）
  C3  `xt()` 末尾追加 `YlxwSpiritExtras(t, r)` ⇒ 快速结算 `X0` 与回合制 `QS`
      两套战斗**同时**吃妖灵加成（与既有 `YlxwStatExtras` 同挂点、同风格）
  D5 灵纹：**本批不做**（决策点 9 = A 第二版）

★ 出口口径（服务端权威，客户端只读）
--------------------------------------------------------------------------
  `player.petSpirit` 由服务端 `r018SpiritSync()` 写入存档；`xt()` 只读加算：
    r.attack  += petSpirit.attack
    r.defense += petSpirit.defense
    r.maxHp   += petSpirit.maxHp
    r.speed   += petSpirit.speed
  面板显示的 PP / 加成一律取 `GET /api/pet` 回显的 `t.spirit`（服务端纯函数产物），
  **客户端不复制 PP 公式** ⇒ 展示与实际入账永不漂移。

★ 与上游硬门禁的锚区冲突检查（本模块最关键的约束）
--------------------------------------------------------------------------
  `yl_v2810e_ext.py` 逐字冻结了 `YlxwTPet` 内两处（**不可删**）：
    G-a  `children: "\u5b09\u620f" })] }), m && e.jsx(YlxwTSpiritUse, { pet: m }),`
    G-b  `f("play", "/pet/play", {}, "\u5b09\u620f\u6210\u529f");`
  另有 `E·红线 YlxwTPet 未整体重写`（`function YlxwTPet() {` == 1）与
  `fun086 F5a` 的 `YlxwUseList("/pet")` / 折叠 state 两条。
  ⇒ 本模块**绝不删除原「喂养 / 嬉戏」按钮行**（它是 G-a/G-b 的载体），
     新 UI 挂在**妖灵卡**位置（`YlxwKv` 六字段，全仓无任何模块引用，可安全替换）。
     原「喂养」= 服务端缺省 `tier:'common'`（凡品），原「嬉戏」= 缺省 `kind:'tease'`（逗弄），
     在新后端下语义自洽（等价于凡品进食 / 逗弄），故保留为「快捷行」不构成口径冲突。
  `yl_pet089_ext.py` / `yl_bond_ext.py`：改 `YlxwStatExtras` 签名之后 / `xt` 之外，
  与本模块的 `xt` 末尾挂点、`YlxwTPet` 卡位**零交集**。

硬约束
--------------------------------------------------------------------------
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py、不写 build/assets/。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R018: 妖灵培养重设计（出口「妖灵之力 PP」+ 6 维入口）=====
   出口：服务端 r018SpiritSync() 写 player.petSpirit，客户端 xt() 加算
         ⇒ 快速结算 X0 与回合制 QS 两套战斗同时生效。
   面板：妖灵卡（品阶/等级/喂食度/羁绊/资质/妖灵之力 PP/当前主人加成）
         + 入口（三档进食 / 三种互动 / 买额度 / 秘径 / 点化 / 归位）。
   本块纯展示 + 调服务端端点；数值口径一律取服务端回显 t.spirit，不复制 PP 公式。 */

/* ---------- 出口：xt() 属性层加算（与 YlxwStatExtras 同挂点、同风格） ---------- */
function YlxwSpiritExtras(p, r) {
  if (!p || !r) return;
  var s = p.petSpirit;
  if (!s) return;
  r.attack += Number(s.attack) || 0;
  r.defense += Number(s.defense) || 0;
  r.maxHp += Number(s.maxHp) || 0;
  r.speed += Number(s.speed) || 0;
}

/* ---------- 妖灵卡：六字段 + 妖灵之力 PP + 当前主人加成 ---------- */
function YlxwR18Fix(v, d) { return (Number(v) || 0).toFixed(d == null ? 2 : d); }
function YlxwR18Card(t, m) {
  var c = (t && t.consts) || {};
  var s = t && t.spirit;
  var hungerMax = YlxwNum(c.hungerMax) || 9999;
  var lvMax = Math.floor(hungerMax / (YlxwNum(c.levelDivisor) || 100));
  var data = {
    "名字": String(m.name),
    "品阶": String(m.rarity),
    "等级": YlxwNum(m.level) + " / " + lvMax,
    "喂食度": YlxwNum(m.hunger) + " / " + hungerMax,
    "羁绊": YlxwNum(m.bond) + " / " + (YlxwNum(c.bondMax) || 500),
    "资质": YlxwNum(m.aptitude) + " / " + (YlxwNum(c.aptitudeMax) || 100),
    "妖灵之力 PP": s ? YlxwR18Fix(s.pp) : "—",
    "主人加成": s ? ("攻 +" + YlxwNum(s.attack) + " · 防 +" + YlxwNum(s.defense)
                   + " · 血 +" + YlxwNum(s.maxHp) + " · 速 +" + YlxwNum(s.speed)) : "—",
  };
  return e.jsxs("div", { className: "space-y-2", children: [
    e.jsx(YlxwKv, { data: data }),
    e.jsx("div", { className: "text-[11px] text-stone-500", children:
      "妖灵之力 PP = 品阶K × 等级K × 羁绊K × 资质K；主人加成 = 妖灵属性 × 6% × PP，"
      + "直接加算到战斗属性（快速结算与回合制同时生效）。" }),
  ] });
}

/* ---------- D1 进食：三档灵食（单价完全一致，只买批量便利） ---------- */
function YlxwR18FeedRow(t, m, f, u) {
  var c = (t && t.consts) || {};
  var ft = c.feedTiers || {};
  var keys = ["common", "fine", "immortal"];
  var names = { common: "凡品·青草露", fine: "灵品·玉髓羹", immortal: "仙品·九转灵丹" };
  var btns = keys.map(function (k) {
    var tier = ft[k] || {};
    return e.jsx(YlxwBtn, {
      disabled: !!u,
      onClick: function () { f("r18feed-" + k, "/pet/feed", { tier: k }, "已进食 · " + (tier.name || names[k])); },
      children: (tier.name || names[k]) + "（" + YlxwNum(tier.cost) + " 灵石 · 喂食度 +" + YlxwNum(tier.hunger) + "）",
    }, k);
  });
  return e.jsxs("div", { className: "flex flex-wrap items-center gap-2", children:
    [e.jsx("span", { className: "text-xs text-stone-400 w-12", children: "进食" })].concat(btns) });
}

/* ---------- D2 互动：三种各 1 次/日免费 + 买额度 2 次/日 ---------- */
function YlxwR18PlayRows(t, m, f, u) {
  var c = (t && t.consts) || {};
  var pk = c.playKinds || {};
  var q = (t && t.playQuota) || {};
  var lvl = YlxwNum(m.level);
  var tease = pk.tease || {}, brush = pk.brush || {}, talk = pk.talk || {};
  var buyCost = YlxwNum(c.buyCost) || 20000;
  var buyMax = YlxwNum(c.buyDailyMax) || 2;
  var bought = YlxwNum(q.bought);
  function lbl(k, d) {
    if (lvl < YlxwNum(d.unlock)) return "（需 Lv" + YlxwNum(d.unlock) + "）";
    if (YlxwNum(q[k]) >= 1) return "（今日已用）";
    if (d.extra === "hunger") return "（羁绊 +5 · 喂食度 +" + YlxwNum(d.hunger) + "）";
    if (d.extra === "exp") return "（羁绊 +5 · 修为 +" + YlxwNum(d.exp) + "）";
    return "（羁绊 +5）";
  }
  function dis(k, d) { return !!u || YlxwNum(q[k]) >= 1 || lvl < YlxwNum(d.unlock); }
  var free = [
    e.jsx("span", { className: "text-xs text-stone-400 w-12", children: "互动" }, "lbl"),
    e.jsx(YlxwBtn, { tone: "ghost", disabled: dis("tease", tease),
      onClick: function () { f("r18play-tease", "/pet/play", { kind: "tease" }, "已逗弄"); },
      children: (tease.name || "逗弄") + lbl("tease", tease) }, "tease"),
    e.jsx(YlxwBtn, { tone: "ghost", disabled: dis("brush", brush),
      onClick: function () { f("r18play-brush", "/pet/play", { kind: "brush" }, "已梳毛"); },
      children: (brush.name || "梳毛") + lbl("brush", brush) }, "brush"),
    e.jsx(YlxwBtn, { tone: "ghost", disabled: dis("talk", talk),
      onClick: function () { f("r18play-talk", "/pet/play", { kind: "talk" }, "已夜话"); },
      children: (talk.name || "夜话") + lbl("talk", talk) }, "talk"),
  ];
  var buy = [
    e.jsx("span", { className: "text-xs text-stone-400 w-12", children: "买额度" }, "lbl"),
    e.jsx(YlxwBtn, { disabled: !!u || bought >= buyMax,
      onClick: function () { f("r18buy-tease", "/pet/play", { kind: "tease", buy: true }, "已买额度"); },
      children: "买·逗弄（" + buyCost + "）" }, "bt"),
    e.jsx(YlxwBtn, { disabled: !!u || bought >= buyMax,
      onClick: function () { f("r18buy-brush", "/pet/play", { kind: "brush", buy: true }, "已买额度"); },
      children: "买·梳毛（" + buyCost + "）" }, "bb"),
    e.jsx(YlxwBtn, { disabled: !!u || bought >= buyMax,
      onClick: function () { f("r18buy-talk", "/pet/play", { kind: "talk", buy: true }, "已买额度"); },
      children: "买·夜话（" + buyCost + "）" }, "bk"),
    e.jsx("span", { className: "text-[11px] text-stone-500", children: "今日已买 " + bought + "/" + buyMax }, "q"),
  ];
  return e.jsxs("div", { className: "space-y-2", children: [
    e.jsx("div", { className: "flex flex-wrap items-center gap-2", children: free }),
    e.jsx("div", { className: "flex flex-wrap items-center gap-2", children: buy }),
  ] });
}

/* ---------- D4 秘径：每日 1 次、4 小时、服务端到点判定 ---------- */
function YlxwR18ExpedRow(t, m, f, u) {
  var c = (t && t.consts) || {};
  var ex = t && t.exped;
  var cost = YlxwNum(c.expedCost) || 5000;
  var ms = YlxwNum(c.expedMs) || 14400000;
  var node;
  if (!ex) {
    node = e.jsx(YlxwBtn, { disabled: !!u,
      onClick: function () { f("r18exped", "/pet/spirit/exped", {}, "妖灵已踏上秘径（4 小时）"); },
      children: "派遣秘径（" + cost + " 灵石 · 4 小时）" });
  } else if (YlxwNum(ex.claimed) > 0) {
    node = e.jsx(YlxwBtn, { tone: "ghost", disabled: true, children: "今日秘径已完成" });
  } else if (ex.ready) {
    node = e.jsx(YlxwBtn, { disabled: !!u,
      onClick: function () { f("r18expedc", "/pet/spirit/exped/claim", {}, "秘径归来"); },
      children: "领取秘径奖励（喂食度 +80 · 羁绊 +15 · 修为 +800）" });
  } else {
    var left = Math.max(0, Math.ceil((YlxwNum(ex.startedAt) + ms - Date.now()) / 60000));
    node = e.jsx(YlxwBtn, { tone: "ghost", disabled: true, children: "秘径中… 还需 " + left + " 分钟" });
  }
  return e.jsxs("div", { className: "flex flex-wrap items-center gap-2", children:
    [e.jsx("span", { className: "text-xs text-stone-400 w-12", children: "秘径" }), node] });
}

/* ---------- D3 点化 + D6 归位 ---------- */
function YlxwR18MiscRow(t, m, f, u) {
  var c = (t && t.consts) || {};
  var cost = YlxwNum(c.aptitudeCost) || 30000;
  var aptMax = YlxwNum(c.aptitudeMax) || 100;
  var apt = YlxwNum(m.aptitude);
  var merged = YlxwNum(m.merged) > 0;
  return e.jsxs("div", { className: "flex flex-wrap items-center gap-2", children: [
    e.jsx("span", { className: "text-xs text-stone-400 w-12", children: "点化" }),
    e.jsx(YlxwBtn, { disabled: !!u || merged || apt >= aptMax,
      onClick: function () { f("r18apt", "/pet/aptitude", {}, "点化成功（资质 +1~3）"); },
      children: "点化资质（" + cost + " 灵石 · +1~3 · " + apt + "/" + aptMax + "）" }),
    e.jsx("span", { className: "text-xs text-stone-400 ml-2", children: "归位" }),
    e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u || merged,
      onClick: function () {
        f("r18away", "/pet/spirit/away", {}, "妖灵已归位").then(function (res) {
          if (res) { try { YlxwMergeSpiritAway(m); YlxwDirty(); } catch (err) {} }
        });
      },
      children: merged ? "已归位" : "归位为灵宠（一次性）" }),
  ] });
}

/* ---------- 面板：妖灵卡之后的完整培养入口 ---------- */
function YlxwR18Panel(t, m, f, u) {
  return e.jsxs("div", { className: "space-y-2 bg-ink-800/60 border border-stone-700 rounded p-2.5", children: [
    e.jsx("div", { className: "text-xs text-amber-300 font-bold", children: "培养（出口：妖灵之力 PP）" }),
    YlxwR18FeedRow(t, m, f, u),
    YlxwR18PlayRows(t, m, f, u),
    YlxwR18ExpedRow(t, m, f, u),
    YlxwR18MiscRow(t, m, f, u),
  ] });
}
'''

# --------------------------------------------------------------------------- 锚点常量（实测 count==1）

# C0 注入锚：`YlxwTPet` 定义之前（顶层同作用域；v2810e 亦用此锚 insert_before，两者顺序无关）
ANCHOR_TPET = 'function YlxwTPet() {'

# C1 妖灵卡：六字段 `YlxwKv`（全仓无任何模块引用 ⇒ 可安全替换）
CARD_OLD = (r'm ? e.jsx(YlxwKv, { data: { "\u540d\u5b57": m.name, "\u54c1\u9636": m.rarity, '
            r'"\u7b49\u7ea7": m.level, "\u9965\u997f": m.hunger, "\u7ecf\u9a8c": m.exp, '
            r'"\u7f81\u7eca": m.bond } })')
CARD_NEW = 'm ? e.jsxs(e.Fragment, { children: [YlxwR18Card(t, m), YlxwR18Panel(t, m, f, u)] })'

# C2 标题：今日嬉戏 → 今日互动
TITLE_OLD = (r'e.jsxs("span", { className: "text-xs text-stone-400", children: ["\u4eca\u65e5\u5b09\u620f ", '
             r'YlxwNum(t && t.playTimes), "/", YlxwNum(t && t.consts && t.consts.playDailyMax)] })')
TITLE_NEW = (r'e.jsxs("span", { className: "text-xs text-stone-400", children: ["\u4eca\u65e5\u4e92\u52a8 ", '
             r'YlxwNum(t && t.playTimes), "/", YlxwNum(t && t.consts && t.consts.playDailyMax)] })')

# C3 出口：xt() 末尾追加妖灵加成（保留 YlxwStatExtras 原串 ⇒ build_v26n 门禁不变）
XT_OLD = r'typeof YlxwStatExtras==="function"&&YlxwStatExtras(t,r);return r}'
XT_NEW = (r'typeof YlxwStatExtras==="function"&&YlxwStatExtras(t,r);'
          r'typeof YlxwSpiritExtras==="function"&&YlxwSpiritExtras(t,r);return r}')

EDITS = [
    ('C1 妖灵卡 + 培养入口', CARD_OLD, CARD_NEW),
    ('C2 标题今日互动',      TITLE_OLD, TITLE_NEW),
    ('C3 xt 加算妖灵加成',   XT_OLD, XT_NEW),
]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 fun086 / v2810e / pet089）；
    ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r018 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # C0) 模块级助手（顶层同作用域，函数声明提升 ⇒ 面板可引用）
    p.insert_before('r018-helpers', ANCHOR_TPET, blk + '\n',
                    expect=1, note='注入 YlxwSpiritExtras + 妖灵卡 / 6 维入口')

    # C1-C3) 就地替换
    for name, old, new in EDITS:
        p.replace(name, old, new, expect=1)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 注入块 · 出口 =================
        ('R18·妖灵加成纯函数已注入', 'function YlxwSpiritExtras(p, r) {', 1, '==', ''),
        ('R18·加成加算攻',           'r.attack += Number(s.attack) || 0;', 1, '==', ''),
        ('R18·加成加算防',           'r.defense += Number(s.defense) || 0;', 1, '==', ''),
        ('R18·加成加算血',           'r.maxHp += Number(s.maxHp) || 0;', 1, '==', ''),
        ('R18·加成加算速',           'r.speed += Number(s.speed) || 0;', 1, '==', ''),
        ('R18·只读 player.petSpirit', 'var s = p.petSpirit;', 1, '==', '不复制 PP 公式'),
        # ================= 注入块 · 面板 =================
        ('R18·妖灵卡已注入',         'function YlxwR18Card(t, m) {', 1, '==', ''),
        ('R18·PP 取服务端回显',       'var s = t && t.spirit;', 1, '==', '不本地算 PP'),
        ('R18·面板已注入',           'function YlxwR18Panel(t, m, f, u) {', 1, '==', ''),
        ('R18·进食三档已注入',        'function YlxwR18FeedRow(t, m, f, u) {', 1, '==', ''),
        ('R18·互动三选已注入',        'function YlxwR18PlayRows(t, m, f, u) {', 1, '==', ''),
        ('R18·秘径行已注入',          'function YlxwR18ExpedRow(t, m, f, u) {', 1, '==', ''),
        ('R18·点化归位行已注入',      'function YlxwR18MiscRow(t, m, f, u) {', 1, '==', ''),
        # ================= 挂载点 =================
        ('R18·xt 末尾挂载',           'typeof YlxwSpiritExtras==="function"&&YlxwSpiritExtras(t,r)', 1, '==', ''),
        ('R18·妖灵卡挂到面板',        'm ? e.jsxs(e.Fragment, { children: [YlxwR18Card(t, m), YlxwR18Panel(t, m, f, u)] })', 1, '==', ''),
        ('R18·标题改为今日互动',      r'"\u4eca\u65e5\u4e92\u52a8 "', 1, '==', ''),
        ('R18·旧标题今日嬉戏已清零',  r'"\u4eca\u65e5\u5b09\u620f "', 0, '==', ''),
        # ================= 端点路径 =================
        ('R18·进食端点',              'f("r18feed-" + k, "/pet/feed", { tier: k }', 1, '==', ''),
        ('R18·互动端点',              'f("r18play-tease", "/pet/play", { kind: "tease" }', 1, '==', ''),
        ('R18·买额度端点',            'f("r18buy-tease", "/pet/play", { kind: "tease", buy: true }', 1, '==', ''),
        ('R18·点化端点',              'f("r18apt", "/pet/aptitude"', 1, '==', ''),
        ('R18·秘径派遣端点',          'f("r18exped", "/pet/spirit/exped"', 1, '==', ''),
        ('R18·秘径领取端点',          'f("r18expedc", "/pet/spirit/exped/claim"', 1, '==', ''),
        ('R18·归位端点',              'f("r18away", "/pet/spirit/away"', 1, '==', ''),
        ('R18·归位后调客户端桥',      'YlxwMergeSpiritAway(m); YlxwDirty();', 1, '==', ''),
        # ================= 冻结（本环不得回踩上游门禁面）=================
        ('冻结·v2810e YlxwTPet 未整体重写', 'function YlxwTPet() {', 1, '==', ''),
        ('冻结·v2810e 嬉戏按钮未动',        r'f("play", "/pet/play", {}, "\u5b09\u620f\u6210\u529f");', 1, '==', ''),
        ('冻结·v2810e 作用块挂载未动',
         r'children: "\u5b09\u620f" })] }), m && e.jsx(YlxwTSpiritUse, { pet: m }),', 1, '==', ''),
        ('冻结·fun086 /pet 端点未改',       'YlxwUseList("/pet")', 1, '==', ''),
        ('冻结·fun086 日志折叠 state 未动',
         'var _pl = O.useState(!1), _logOpen = _pl[0], _setLogOpen = _pl[1];', 1, '==', ''),
        ('冻结·fun086 旧全量渲染未回潮',
         '((t && t.careLog) || []).map(function(g, h) { return e.jsx(YlxwRow,', 0, '==', ''),
        ('冻结·v2810e 作用块组件未动',      'function YlxwTSpiritUse(props) {', 1, '==', ''),
        ('冻结·pet089 归位桥未动',          'function YlxwMergeSpiritAway(sp) {', 1, '==', ''),
        ('冻结·pet089 融合页签未动',        'function YlxwPetFuseTab(props) {', 1, '==', ''),
        ('冻结·pet089 面板包壳未动',        'function YlxwPetShell(p) {', 1, '==', ''),
        ('冻结·pet089 memo 未动',           'jM=Rt.memo(YlxwPetShell)', 1, '==', ''),
        ('冻结·妖灵面板注册未动',           'pet: YlxwTPet', 1, '==', ''),
        ('冻结·bond YlxwStatExtras 未动',   'YlxwStatExtras(t,r)', 1, '==', ''),
        ('冻结·战斗结算核心未动',           'YlxwBattleBonus(t),YlxwDOD=', 1, '==', ''),
        ('冻结·远征 20000 未动',            'var _expCost = 20000;', 1, '==', ''),
        ('R18·未新增仙途任务',              'QUEST_DEFS', 0, '==', 'D8 = 本批不做'),
        # ---- 注入块内不得自建网络调用（走 YlxwUseAct / Xc 统一鉴权层）----
        ('R18·注入块未自建 fetch',  'fetch(', 0, '==', '统一走 YlxwUseAct',
         ('/* ===== yl-R018:', 'function YlxwTPet() {')),
    ]
    return gates
