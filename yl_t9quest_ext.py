# -*- coding: utf-8 -*-
"""
yl_t9quest_ext.py -- T9「仙途任务 · 活跃度」客户端侧（0.8.8 / C 组，i3-cli）

范围（严格限定）：**只改显示/交互层**，不动任何写入逻辑。
  见《T9-实现批改动清单》§2：
    C1  客户端 `YlxwTQuest` 渲染组件：宝箱 4→6 档；任务 4→18 条（分组折叠）；
        每档显示 灵石 + 修为 + 抽奖券；新增周活跃度进度条 + 3 档里程碑卡；
        标题加分母 / 330。
    C2  顶栏「仙途任务」按钮角标（可领档位数）—— 可选，本模块做轻量版。
    C3  原生「日常任务」改名「每日功课」（§5.4 方案 A）—— ★ **不在本模块**：
        那是另一系统（`dailyQuests`），归 i6-gm/服务端批；且改名会碰 item8 已收敛区，
        改由 team-lead 决定是否单列。本模块**不碰**。

★ 硬纪律（T9 §7.6 / 清单 §7 必改点③）：
  · **不改 `daily_quests` 写入逻辑** —— Y19 成就靠 `daily_quests` 累计行，
    新 14 项刻意不落行（否则 quest_200 从 50 天加速到 ~11 天）。
  · 本模块是**纯客户端**：不含 `daily_quests` / `tickDailyQuests` / `QUEST_DEFS` /
    `activityFromQuests` 任何字符串（三条 n=0 断言）。
  · 领奖仍走存量 `POST /quest/chest`（`{tier}`），新增的是一键循环 + 周里程碑
    `POST /quest/milestone`（服务端 E3，i6-gm）与可选 `POST /quest/claim-all`。

★ 优雅降级：服务端未上线时（`chests` 仍是 4 档、无 `week`/`milestones`/`points`/`group`），
  面板照常渲染 4 档 4 项，不白屏。分组/分值/周进度全部**字段存在才渲染**。

=========================================================================== 与客户端既有表同源（镜像，不改公式）
  · 6 档门槛 `[30, 60, 100, 150, 200, 260]`（T9 §4.2 镜像服务端 `CHEST_TIERS`）
  · 档位灵石 base `{30:1000,60:2000,100:4000,150:7000,200:11000,260:16000}`（T9 §4.2）
  · 周里程碑 `[{500,'勤修·初'},{1000,'勤修·中'},{1800,'勤修·满'}]`（T9 §4.4）
  · 分组名 A 核心 / B 进阶 / C 社交 / D 休闲（T9 §3.1-§3.4）
  · `YLRF(realm)` 客户端已有（产物 @605252）⇒ **不重复定义**，回落到存档 realm 求值。
    ★ 但为「服务端不下发 reward 时也能显示」保留一份本地镜像表。

=========================================================================== 装配落点（grep -n 于 build/assets/index-v26m-20260927.js 实证）
  锚点 1：`function YlxwTQuest(r) {`（组件定义起点，唯一，@795214）→ 整体替换。
  锚点 2：`"仙途任务"` ×2（工具栏按钮 + 面板标题）→ 仅面板标题处已在替换体内。

硬约束（同 T17/T16）：
  · 只新建本文件 + 修改 build_v26n.py 接线；**不写回 build/assets/**。
  · 注入块 zh() 后纯 ASCII；不含禁用模式 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
"""

import re

INJECT_JS = r"""
/* ===== yl-0.8.9 T9: 仙途任务·活跃度 客户端显示层（18 项 / 6 档宝箱 / 周里程碑） =====
   纯显示与交互：不改任务落库写入（保 Y19 成就零回归）、不新增活跃度埋点。
   服务端未上线时按旧 4 档 4 项渲染，字段存在才渲染新增部分（优雅降级）。 */

/* --- 6 档门槛与灵石 base（T9 §4.2 镜像服务端 CHEST_TIERS / CHEST_REWARDS） --- */
var YlxwQ6Tiers = [30, 60, 100, 150, 200, 260];
var YlxwQ6Base = { 30: 1000, 60: 2000, 100: 4000, 150: 7000, 200: 11000, 260: 16000 };
/* 修为（打坐等效次数）与抽奖券（T9 §4.2 表） */
var YlxwQ6Exp = { 30: 60, 60: 120, 100: 240, 150: 360, 200: 480, 260: 600 };
var YlxwQ6Ticket = { 30: 0, 60: 1, 100: 2, 150: 3, 200: 5, 260: 8 };
/* 高价值档附加（T9 §9.2 文案） */
var YlxwQ6Extra = { 200: "随机珍宝 ×1", 260: "随机珍宝 ×1" };

/* --- 周里程碑（T9 §4.4） --- */
var YlxwQMile = [
  { tier: 500,  name: "勤修·初", base: 20000, ticket: 8,  extra: "" },
  { tier: 1000, name: "勤修·中", base: 45000, ticket: 15, extra: "传承石 ×1" },
  { tier: 1800, name: "勤修·满", base: 60000, ticket: 30, extra: "仙品珍宝 ×1 · 称号「勤修不辍」" }
];
var YlxwQMax = 330;        /* 日名义满分（T9 §3.5） */
var YlxwQWeekMax = 2310;   /* 周名义满分 = 7 × 330 */

/* --- YLRF 本地镜像（服务端不下发 reward 时兜底；与产物 @605252 同源） --- */
var YlxwQRF = [4 / 3, 3, 5, 7, 9, 11, 13];
function YlxwQRFOf(realmIndex) {
  var i = Math.max(0, Math.min(YlxwQRF.length - 1, YlxwNum(realmIndex) || 0));
  return YlxwQRF[i];
}

/* --- 分组元数据（T9 §3.1-§3.4） --- */
var YlxwQGroups = [
  { key: "A", name: "核心", max: 110, color: "text-amber-300" },
  { key: "B", name: "进阶", max: 86,  color: "text-sky-300" },
  { key: "C", name: "社交", max: 80,  color: "text-violet-300" },
  { key: "D", name: "休闲", max: 54,  color: "text-emerald-300" }
];
/* 项目 → 分组 兜底映射（服务端未下发 group 时按 key 归类） */
var YlxwQGroupOf = {
  login: "A", meditate: "A", kill: "A", adventure: "A", exp: "A",
  dungeon: "B", alchemy: "B", farm: "B", pet: "B", grotto: "B",
  sect: "C", arena: "C", mentor: "C", bounty: "C", chat: "C",
  fun: "B", lottery: "D", spend: "D"
};

/* --- 纯函数 --- */
function YlxwQTierList(chests) {
  /* 服务端下发优先；缺失回落本地 6 档镜像 */
  if (chests && chests.length) return chests.map(function(c) { return c.tier; });
  return YlxwQ6Tiers.slice();
}
function YlxwQStoneOf(tier, realmIndex, serverReward) {
  if (serverReward != null && YlxwNum(serverReward) > 0) return YlxwNum(serverReward);
  var base = YlxwQ6Base[tier];
  return base == null ? 0 : Math.floor(base * YlxwQRFOf(realmIndex));
}
function YlxwQMileStoneOf(base, realmIndex) { return Math.floor(base * YlxwQRFOf(realmIndex)); }
function YlxwQGroupSum(quests, gkey) {
  var s = 0;
  (quests || []).forEach(function(q) {
    var g = q.group || YlxwQGroupOf[q.key] || "A";
    if (g === gkey) s += YlxwNum(q.points);
  });
  return s;
}
function YlxwQGroupDone(quests, gkey) {
  var d = 0, n = 0;
  (quests || []).forEach(function(q) {
    var g = q.group || YlxwQGroupOf[q.key] || "A";
    if (g === gkey) { n++; if (q.done) d++; }
  });
  return { done: d, total: n };
}
/* 可领档位数（C2 角标用） */
function YlxwQClaimable(chests) {
  var n = 0;
  (chests || []).forEach(function(c) { if (c.unlocked && !c.claimed) n++; });
  return n;
}

/* --- 进度条组件 --- */
function YlxwQBar(cur, max, color) {
  var pct = max > 0 ? Math.min(100, Math.floor(YlxwNum(cur) * 100 / max)) : 0;
  return e.jsx("div", { className: "h-2 w-full bg-ink-900 rounded overflow-hidden", children:
    e.jsx("div", { className: (color || "bg-amber-500") + " h-full transition-all", style: { width: pct + "%" } }) });
}

/* --- 玩法说明折叠块（T9 §9.5 文案） --- */
function YlxwQHelp() {
  var s = O.useState(!1), open = s[0], set = s[1];
  return e.jsxs("div", { className: "border border-stone-700 rounded", children: [
    e.jsxs("button", { onClick: function() { set(!open); },
      className: "w-full text-left px-2 py-1.5 text-xs text-amber-300 font-bold hover:bg-ink-800/60 rounded",
      children: (open ? "▾ " : "▸ ") + "玩法说明" }),
    open ? e.jsxs("div", { className: "px-2 pb-2 text-xs text-stone-300 space-y-1.5 leading-relaxed", children: [
      e.jsx("div", { children: "每日完成游戏内的各种玩法都会累积「活跃度」，活跃度越高，可领取的活跃宝箱越多。今日活跃度上限 330。" }),
      e.jsxs("ul", { className: "list-disc list-inside space-y-1", children: [
        e.jsx("li", { children: "活跃度按玩法分别计分，每项每日有次数上限（见列表）" }),
        e.jsx("li", { children: "活跃宝箱共 6 档：30 / 60 / 100 / 150 / 200 / 260" }),
        e.jsx("li", { children: "宝箱奖励随你的境界提升（灵石按境界倍率放大）" }),
        e.jsx("li", { children: "每周一 0 点重置周活跃度，累计达标可领「勤修」里程碑大奖" }),
        e.jsx("li", { children: "奖励通过邮件发放，请到信箱领取" })
      ] }),
      e.jsx("div", { className: "text-stone-400", children: "※ 本系统的「活跃度」只记录你在游戏里的行为，与「每日功课」里的具体任务（打坐 N 次、历练 N 次）互不影响。" })
    ] }) : null
  ] });
}

/* --- 周里程碑区 --- */
function YlxwQMileZone(props) {
  var week = props.week, realm = props.realm, claims = props.claims || {}, busy = props.busy, onClaim = props.onClaim;
  var cards = YlxwQMile.map(function(m, i) {
    var ratio = week / m.tier;
    var reached = week >= m.tier;
    var claimed = !!claims[m.tier] || !!claims[String(m.tier)];
    var stone = YlxwQMileStoneOf(m.base, realm);
    return e.jsxs(YlxwRow, { children: [
      e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsxs("span", { className: "text-sm", children: [
          e.jsx("span", { className: "text-amber-200 font-bold", children: m.name }),
          e.jsx("span", { className: "text-xs text-stone-400 ml-2", children: "周活跃度 " + m.tier })
        ] }),
        claimed ? e.jsx("span", { className: "text-xs text-stone-500", children: "已领取" })
          : reached ? e.jsx(YlxwBtn, { disabled: busy,
              onClick: function() { onClaim(m.tier); }, children: "领取" })
            : e.jsx("span", { className: "text-xs text-stone-500", children: "未达成" })
      ] }),
      e.jsx("div", { className: "text-xs text-stone-400 pt-1", children:
        "灵石 " + stone + " · 抽奖券 ×" + m.ticket + (m.extra ? " · " + m.extra : "") }),
      e.jsx("div", { className: "pt-1", children: YlxwQBar(week, m.tier, reached ? "bg-emerald-500" : "bg-amber-500") }),
      e.jsx("div", { className: "text-[11px] text-stone-500 pt-0.5", children:
        Math.min(100, Math.floor(ratio * 100)) + "% · 还差 " + Math.max(0, m.tier - week) })
    ] }, "m" + i);
  });
  return e.jsxs("div", { className: "space-y-1.5", children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2", children: [
      e.jsx("span", { className: "text-xs text-amber-300 font-bold", children: "本周勤修" }),
      e.jsx("span", { className: "text-xs text-stone-400", children: week + " / " + YlxwQWeekMax })
    ] }),
    e.jsx(YlxwQBar, { cur: week, max: YlxwQWeekMax, color: "bg-violet-500" }),
    e.jsx("div", { className: "space-y-1.5", children: cards })
  ] });
}

/* --- 任务列表（分组折叠） --- */
function YlxwQQuestList(props) {
  var quests = props.quests || [];
  var s = O.useState({ A: !0, B: !1, C: !1, D: !1 }), open = s[0], setOpen = s[1];
  var hasGroup = quests.some(function(q) { return !!q.group; });
  if (!hasGroup) {
    /* 降级：服务端未下发 group ⇒ 平铺（旧 4 项形态） */
    return e.jsx("div", { className: "space-y-1.5", children: quests.map(function(q) {
      return e.jsxs(YlxwRow, { children: e.jsxs("div", { className: "flex justify-between", children: [
        e.jsx("span", { children: q.name }),
        e.jsx("span", { className: "text-xs " + (q.done ? "text-green-400" : "text-stone-400"),
          children: q.done ? "已完成" : q.progress + "/" + q.target })
      ] }) }, "q" + q.key);
    }) });
  }
  return e.jsxs("div", { className: "space-y-1.5", children: YlxwQGroups.map(function(g) {
    var sum = YlxwQGroupSum(quests, g.key);
    var cnt = YlxwQGroupDone(quests, g.key);
    var isOpen = !!open[g.key];
    var rows = quests.filter(function(q) {
      return (q.group || YlxwQGroupOf[q.key] || "A") === g.key;
    }).map(function(q) {
      return e.jsxs(YlxwRow, { children: e.jsxs("div", { className: "flex justify-between items-center gap-2", children: [
        e.jsxs("span", { className: "text-sm", children: [
          e.jsx("span", { children: q.name }),
          e.jsx("span", { className: "text-xs text-stone-500 ml-2", children: "+" + YlxwNum(q.points) + "/次" })
        ] }),
        e.jsx("span", { className: "text-xs " + (q.done ? "text-green-400" : "text-stone-400"),
          children: q.done ? "已完成" : q.progress + "/" + q.target })
      ] }) }, "q" + q.key);
    });
    return e.jsxs("div", { className: "border border-stone-700 rounded", children: [
      e.jsxs("button", { onClick: function() { var o = {}; for (var k in open) o[k] = open[k]; o[g.key] = !isOpen; setOpen(o); },
        className: "w-full text-left px-2 py-1.5 text-xs font-bold hover:bg-ink-800/60 rounded flex items-center justify-between gap-2",
        children: [
          e.jsxs("span", { className: g.color, children: [ (isOpen ? "▾ " : "▸ ") + "【" + g.name + "】" ] }),
          e.jsx("span", { className: "text-stone-400", children: sum + " / " + g.max + "  ·  " + cnt.done + "/" + cnt.total })
        ] }),
      isOpen ? e.jsx("div", { className: "space-y-1.5 px-1 pb-1", children: rows }) : null
    ] }, "g" + g.key);
  }) });
}

/* --- 主面板 --- */
function YlxwTQuest2(r) {
  /* ★ 变量名保留 t：基座 3 个面板共用同一邮件跳转回调，flow083 的 F6 门禁断言该串恰 3 处
     —— 改名会静默破坏它。 */
  var t = r.go;
  var a = YlxwUseList("/quest/summary"), l = a.data, c = a.err, busy = a.busy, reload = a.load;
  var f = YlxwUseAct(reload), actKey = f.actKey, run = f.run;
  var quests = (l && l.quests) || [];
  var chests = (l && l.chests) || [];
  var activity = YlxwNum(l && l.activity);
  var week = YlxwNum(l && l.week);
  var realm = YlxwNum(l && l.realmIndex);
  var actMax = YlxwNum(l && l.activityMax) || YlxwQMax;
  var claims = (l && l.milestones) || {};
  var claimable = YlxwQClaimable(chests);

  /* 一键领取：循环调存量 /quest/chest（服务端 E4 若上线则优先，客户端兜底循环） */
  var claimAll = async function() {
    var targets = chests.filter(function(cb) { return cb.unlocked && !cb.claimed; });
    if (!targets.length) { ia("暂无可领取的宝箱"); return; }
    try {
      if (l && l.claimAllSupported) {
        await YlxwPost("/quest/claim-all", {});
      } else {
        for (var i = 0; i < targets.length; i++) {
          await YlxwPost("/quest/chest", { tier: targets[i].tier });
        }
      }
      ia("已领取 " + targets.length + " 档，奖励已发至信箱"), await reload(), YlxwDirty();
    } catch (e2) { Je((e2 && e2.message) || "领取失败"); }
  };
  var claimMile = function(tier) {
    run("mile" + tier, "/quest/milestone", { tier: tier }, "里程碑奖励已发至信箱");
  };

  var head = e.jsx(YlxwTitle, { extra: e.jsx("div", { className: "flex items-center gap-2", children: [
    claimable > 0 ? e.jsx("span", { className: "px-1.5 py-0.5 rounded bg-amber-600 text-stone-900 text-[11px] font-bold",
      children: "可领 " + claimable }) : null,
    e.jsx(YlxwBtn, { tone: "ghost", disabled: !!actKey, onClick: claimAll, children: "一键领取" }),
    e.jsx(YlxwBtn, { tone: "ghost", onClick: function() { t("mail"); }, children: "去信箱" })
  ] }), children: "仙途任务 · 活跃度 " + activity + " / " + actMax });

  var dayBar = e.jsxs(YlxwRow, { children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2", children: [
      e.jsx("span", { className: "text-xs text-amber-300 font-bold", children: "今日进度" }),
      e.jsx("span", { className: "text-xs text-stone-400", children: activity + " / " + actMax })
    ] }),
    e.jsx("div", { className: "pt-1", children: YlxwQBar(activity, actMax, "bg-amber-500") })
  ] });

  var chestRows = chests.map(function(b) {
    var tier = b.tier;
    var stone = YlxwQStoneOf(tier, realm, b.reward);
    var expN = YlxwQ6Exp[tier], ticket = YlxwQ6Ticket[tier], extra = YlxwQ6Extra[tier];
    var parts = ["灵石 " + stone];
    if (expN != null) parts.push("修为 " + expN + " 次");
    if (ticket != null && ticket > 0) parts.push("抽奖券 ×" + ticket);
    if (extra) parts.push(extra);
    return e.jsxs(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      e.jsxs("span", { className: "text-sm", children: [
        e.jsx("span", { className: "px-1.5 py-0.5 rounded bg-ink-900 border border-stone-600 text-amber-200 font-mono text-xs mr-2", children: tier }),
        e.jsx("span", { className: "text-stone-300 text-xs", children: parts.join(" · ") })
      ] }),
      b.claimed ? e.jsx("span", { className: "text-xs text-stone-500", children: "已领取" })
        : b.unlocked ? e.jsx(YlxwBtn, { disabled: !!actKey,
            onClick: function() { run("chest" + tier, "/quest/chest", { tier: tier }, "已领取，奖励已发至信箱"); },
            children: "领取" })
          : e.jsx("span", { className: "text-xs text-stone-500", children: "活跃度未达" })
    ] }) }, "ch" + tier);
  });

  return e.jsxs(YlxwPanel, { children: [
    head,
    e.jsx(YlxwMailHint, {}),
    c ? e.jsx(YlxwErr, { retry: reload, children: c }) : e.jsxs(e.Fragment, { children: [
      dayBar,
      (l && (l.week != null || (l.milestones != null))) ? e.jsx(YlxwRow, { children: e.jsx(YlxwQMileZone, {
        week: week, realm: realm, claims: claims, busy: !!actKey, onClaim: claimMile }) }) : null,
      e.jsx("div", { className: "text-xs text-amber-300 font-bold pt-1", children: "活跃宝箱" }),
      chests.length ? e.jsx("div", { className: "space-y-1.5", children: chestRows }) : e.jsx(YlxwEmpty, { children: "暂无宝箱数据" }),
      e.jsx("div", { className: "text-xs text-amber-300 font-bold pt-1", children: "活跃度来源" }),
      quests.length ? e.jsx(YlxwQQuestList, { quests: quests }) : e.jsx(YlxwEmpty, { children: "暂无任务数据" }),
      e.jsx("div", { className: "pt-1", children: e.jsx(YlxwQHelp, {}) })
    ] })
  ] });
}

/* 兼容旧名（存量引用点若仍叫 YlxwTQuest 也不至白屏） */
function YlxwTQuest(r) { return YlxwTQuest2(r); }
/* ★ 不在此处写组件挂载语句：组件表的 var 声明位置在文件更后面（@1025083），
   在此处赋值会命中 TDZ/undefined ⇒ 整包运行时报错（Node --check 查不出，真浏览器才暴露）。
   组件映射表本就在声明处引用同名函数，我们已整体重写它，无需挂载语句。 */
"""

OLD_QUEST_HEAD = 'function YlxwTQuest(r) {'


def extract_old_quest(text):
    r"""从当前文本里**逐字**截取旧 YlxwTQuest 的完整源码（花括号配对）。

    返回 (源码, 起始偏移)；找不到/未闭合一律抛异常（不许静默失败）。
    """
    i = text.find(OLD_QUEST_HEAD)
    if i < 0:
        raise AssertionError('t9quest：旧 YlxwTQuest 未找到（锚点已漂移）')
    j = text.find('{', i)
    depth, k = 0, j
    while k < len(text):
        ch = text[k]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[i:k + 1], i
        k += 1
    raise AssertionError('t9quest：旧 YlxwTQuest 花括号未闭合')


def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('t9quest 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 面板重写：整体替换旧 YlxwTQuest（花括号配对截取，逐字锚点，唯一）。
    old_fn, off = extract_old_quest(p.text)
    new_all = zh(INJECT_JS).strip()
    p.replace('t9quest-panel', old_fn, new_all, expect=1,
              note='重写 YlxwTQuest：18 项分组折叠 / 6 档宝箱 / 周里程碑 / 一键领取 / 帮助块')

    # ------------------------------------------------------------- 门禁
    gates = [
        # —— T9 面板重写 ——
        ('T9·组件表仍指向 YlxwTQuest',     'quest: YlxwTQuest,',             1, '==', '映射表在后，引用同名重写函数'),
        ('T9·未在声明前误挂 YLXW_COMP',    'YLXW_COMP.quest = YlxwTQuest2;', 0, '==', '必须为 0（早于声明=运行时报错）'),
        ('T9·YlxwTQuest 重写后定义',       'function YlxwTQuest2(r) {',      1, '==', ''),
        # —— 6 档宝箱 ——
        ('T9·6 档门槛表',                 'var YlxwQ6Tiers = [30, 60, 100, 150, 200, 260];', 1, '==', ''),
        ('T9·灵石 base 表 6 档',           'var YlxwQ6Base = { 30: 1000, 60: 2000, 100: 4000, 150: 7000, 200: 11000, 260: 16000 };', 1, '==', ''),
        ('T9·修为等效表',                 'var YlxwQ6Exp = {',              1, '==', ''),
        ('T9·抽奖券表',                   'var YlxwQ6Ticket = {',           1, '==', ''),
        ('T9·档位显示修为+券',            'parts.push("\\u62bd\\u5956\\u5238 \\u00d7" + ticket)', 1, '==', ''),
        # —— 18 项分组折叠 ——
        ('T9·分组元数据 4 组',            'var YlxwQGroups = [',            1, '==', ''),
        ('T9·分组归类兜底表',             'var YlxwQGroupOf = {',           1, '==', ''),
        ('T9·分组折叠组件',               'function YlxwQQuestList(',       1, '==', ''),
        ('T9·分组求和纯函数',             'function YlxwQGroupSum(',        1, '==', ''),
        # —— 周里程碑 ——
        ('T9·周里程碑 3 档',              'var YlxwQMile = [',              1, '==', ''),
        ('T9·周里程碑卡组件',             'function YlxwQMileZone(',        1, '==', ''),
        ('T9·周里程碑端点',               '"/quest/milestone"',             1, '==', ''),
        ('T9·周上限 2310',                'var YlxwQWeekMax = 2310;',       1, '==', ''),
        # —— 标题分母 / 进度条 ——
        ('T9·标题带分母 / 330',           '\\u4ed9\\u9014\\u4efb\\u52a1 \\u00b7 \\u6d3b\\u8dc3\\u5ea6 " + activity + " / " + actMax', 1, '==', ''),
        ('T9·日进度条',                   '今日进度',                       1, '==', ''),
        ('T9·进度条组件',                 'function YlxwQBar(',             1, '==', ''),
        # —— 一键领取 ——
        ('T9·一键领取按钮',               '一键领取',                       1, '==', ''),
        ('T9·一键领取循环兜底',           'YlxwPost("/quest/chest", { tier: targets[i].tier })', 1, '==', ''),
        ('T9·可领角标纯函数',             'function YlxwQClaimable(',       1, '==', ''),
        ('T9·claimAll 端点优先',          '"/quest/claim-all"',             1, '==', ''),
        # —— 帮助 ——
        ('T9·玩法说明折叠块',             'function YlxwQHelp(',            1, '==', ''),
        # —— 优雅降级 ——
        ('T9·无 group 时平铺降级',         'if (!hasGroup) {',               1, '==', ''),
        ('T9·宝箱门槛回落本地镜像',        'function YlxwQTierList(',        1, '==', ''),
        # —— ★ 硬纪律：不许碰写入端 / 不许新增埋点 ——
        ('T9·未碰 daily_quests',          'daily_quests',                   0, '==', '保 Y19 零回归'),
        ('T9·未碰 tickDailyQuests',       'tickDailyQuests',                0, '==', ''),
        ('T9·未碰 QUEST_DEFS',            'QUEST_DEFS',                     0, '==', ''),
        ('T9·未碰 activityFromQuests',    'activityFromQuests',             0, '==', ''),
        # —— 基线未动 ——
        ('基线·存量 chest 端点仍用',       '"/quest/chest"',                 1, '>=', '领奖仍走存量端点'),
        ('基线·邮件跳转按钮仍在',          't("mail")',                      3, '==', '与 flow083 F6 三处守恒'),
        ('基线·信箱发放提示仍在',          'YlxwMailHint',                   2, '>=', '定义宿主体 + 本面板使用'),
    ]
    return gates
