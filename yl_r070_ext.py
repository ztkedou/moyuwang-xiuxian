# -*- coding: utf-8 -*-
r"""
yl_r070_ext.py — R-070 升级点（可分配属性点）获取途径重做（客户端单模块）

需求原文（用户）
--------------------------------------------------------------------------
  「由于现在升级比较困难，升级点的获取完全策划一下，增加一些其他的方式可以获取升级点。」

现状侦察（构建产物 index-v281113-20261001.js 逐字实证）
--------------------------------------------------------------------------
  升级点 = `player.attributePoints`（面板文案「可分配属性点」，@1624668）。
  现获取途径只有 3 条：

  ① 境界突破（主来源，@708152 / @710996）
        F0=(t,r,a=0)=>{Xm(r);const l=x3[r],d=Math.min(t?2:1,l-a);return Math.max(0,d)}
        小突破（境界内升 1 层）= min(1, x3[境界]) ⇒ **+1**
        大突破（跨大境界）      = min(2, x3[新境界]) ⇒ **+2**
        （x3={炼气5,筑基10,金丹20,元婴30,化神40,合道50,长生60} 被 min 帽死，实际只出 1/2）
        ⇒ 一生合计 6×(8×1+2) + 8×1 = **68 点**（7 境界 × 9 层）。
  ② 灵草图鉴（Um，@474669）：灵草收集 10/15/20/25 → +1/+2/+3/+5，一次性共 **11 点**。
  ③ 传承（@715728）：消耗传承点突破时按 F0 给点（本质同 ①）。

  ⇒ 服务端对 attributePoints **零处理**（`grep attributePoints srv/index_v28.ts` = 0 命中）
    ⇒ 该字段是**纯客户端权威**，随 /api/save 整包落库（`ho()` 用 `{...t,...}` 展开 ⇒ 新字段可存活）。

本模块动作（5 条新途径，全部客户端可观测状态驱动）
--------------------------------------------------------------------------
  只做「纯增量发放」：不动突破/图鉴/传承三条既有来源，不碰任何妖灵代码。
  全部计数落 `player.ylAp`（随存档持久化），日/周切按**北京时区**，发放点唯一且幂等。

  途径            触发条件（客户端可观测）              给点   上限          防刷
  ---------------------------------------------------------------------------------
  甲 每日任务全清   player.dailyQuests 全部 completed      +2    每日 1 次     ylAp.q 日期戳幂等
  乙 在线修行       playTime 当日增量 ≥ 3600000ms          +1    每日 1 次     ylAp.pBase 基准 + pGrant 计数
  丙 今日首斩       statistics.killCount > 当日基准        +1    每日 1 次     ylAp.k + ylAp.kBase
  丁 周常在线       本周 playTime 增量 ≥ 18000000ms        +3    每周 1 次     ylAp.wBase + wGrant（北京周一 0 点切）
  戊 里程碑（一次） 见下表                                 +16   一次性        ylAp.miles[] 永久去重
  ---------------------------------------------------------------------------------
  日上限 = 2+1+1 = **4 点/天**；周上限 = 4×7+3 = **31 点/周**；一次性合计 **+16 点**。

  戊 里程碑 7 项（一次性，全部用既有 statistics/realm 判定）：
     首次踏入筑基期 +2 ｜ 首次踏入金丹期 +3 ｜ 首次踏入元婴期 +3
     累计击杀 100 +1 ｜ 累计击杀 500 +2 ｜ 累计击杀 2000 +3 ｜ 累计突破 20 次 +2

  ★ 数值理由（为什么这个量级）：现有「一生 68 点」是纯突破供给，且突破越到后期越慢
    （R-044 历练曲线压缩后仍在拉长）。新增供给定位为「日常稳定滴灌」——
    日活玩家约 +4/天（≈ 28/周），一个月 ≈ 120 点 ≈ 把「一生 68 点」压缩成「约 2 个月可再攒一份」。
    既明显缓解「升级点太少」，又不让突破（+1/+2 一次）贬值到无意义；
    里程碑 16 点为长线目标，一次性、不构成持续放水。

  防刷设计：
    · 全部按**北京日/周**切（`YlxwApDay` / `YlxwApWeekKey`），跨日跨周才重置；
    · 每条途径有**独立幂等戳**（`q` / `pGrant` / `k` / `wGrant` / `miles`），发过即写，
      同一条日内/周内不可重复触发（即便玩家反复刷新日常任务、反复进出战斗）；
    · 乙/丁 用「playTime 增量 + 基准」，**不按在线次数**计，多开/切窗口不重复给；
    · 丙 用「当日 killCount 相对当日基准的增量 > 0」判定，只认「当日第一杀」；
    · 发放写在同一笔 `setPlayer` 里（`attributePoints += add` 与 `ylAp` 原子落存档）。

实现（1 处插入块 + 1 处订阅挂点）
--------------------------------------------------------------------------
  I1  在 `Be.subscribe(t=>t.logs,…)` 之前插入模块块：
      `YLXW_AP_REALM` / `YlxwApDay` / `YlxwApWeekKey` / `YlxwApHint` / `YlxwApTick`
  E1  紧接其后挂第二个 player 订阅：`Be.subscribe(t=>t.player,…YlxwApTick())`
      —— 只读比较 + 有变化才写，`YLXW_AP_BUSY` 防 setPlayer 自触发递归。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/auth_token/X-YL-）。
  · 锚点 `Be.subscribe(t=>t.logs,…)` 全目录仅此 1 处、无其它 yl_* 模块占用（已 grep 复核）。
  · 不碰突破给点（`attributePoints:g.attributePoints+Ae`）、传承给点、图鉴给点、分配逻辑。
  · 只新建本文件；不改 build_v26n.py / localtest/* / srv/index_v28.ts / deploy_v28/*。
  · 接线（lead 做）：build_v26n.py 加
        from yl_r070_ext import apply as v28_r070_apply
        V28_MODULES 里加 ('r070', v28_r070_apply),   # 恒在 numbal 之前，无前置依赖
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R070 apgain: 升级点（可分配属性点）多渠道获取 =====
   现状只有「境界突破 +1/+2」「灵草图鉴」「传承」三条来源，一生约 68 点、节奏极慢。
   本块新增 5 条客户端可观测途径（日上限 4 点 / 周上限 31 点 / 里程碑一次性 +16 点）：
     甲 每日任务全清 +2（每日 1 次）  乙 在线满 1 小时 +1（每日 1 次）
     丙 今日首斩 +1（每日 1 次）      丁 本周在线满 5 小时 +3（每周 1 次）
     戊 里程碑 7 项一次性 +16
   计数全部落 player.ylAp（随存档持久化），日/周切按北京时区，每条独立幂等戳防刷。
   只做纯增量发放：不改突破/图鉴/传承任何既有给点逻辑。 */
var YLXW_AP_REALM = ["\u70bc\u6c14\u671f", "\u7b51\u57fa\u671f", "\u91d1\u4e39\u671f", "\u5143\u5a74\u671f", "\u5316\u795e\u671f", "\u5408\u9053\u671f", "\u957f\u751f\u5883"];
var YLXW_AP_BUSY = false;
/* 北京时区（UTC+8）的 YYYY-MM-DD */
function YlxwApDay(ms) {
  var t = (Number(ms) || Date.now()) + 28800000;
  return new Date(t).toISOString().slice(0, 10);
}
/* 北京时区「本周一」的 YYYY-MM-DD（周一 0 点跨周） */
function YlxwApWeekKey(ms) {
  var t = (Number(ms) || Date.now()) + 28800000;
  var dow = (new Date(t).getUTCDay() + 6) % 7;
  return new Date(t - dow * 86400000).toISOString().slice(0, 10);
}
function YlxwApHint() {
  return "\u5347\u7ea7\u70b9\u83b7\u53d6\uff1a\u6bcf\u65e5\u4efb\u52a1\u5168\u6e05 +2 \uff5c \u5728\u7ebf\u6ee1 1 \u5c0f\u65f6 +1 \uff5c \u4eca\u65e5\u9996\u65a9 +1 \uff5c \u672c\u5468\u5728\u7ebf\u6ee1 5 \u5c0f\u65f6 +3 \uff5c \u91cc\u7a0b\u7891\u4e00\u6b21\u6027 +16";
}
function YlxwApTick() {
  if (YLXW_AP_BUSY) return;
  var st = Be.getState();
  var p = st && st.player;
  if (!p || typeof st.setPlayer !== "function") return;
  var today = YlxwApDay(), week = YlxwApWeekKey();
  var prev = (p.ylAp && typeof p.ylAp === "object") ? p.ylAp : {};
  var ap = {
    d: prev.d || "", w: prev.w || "",
    pBase: Number(prev.pBase) || 0, pGrant: Number(prev.pGrant) || 0,
    kBase: Number(prev.kBase) || 0, q: !!prev.q, k: !!prev.k,
    wBase: Number(prev.wBase) || 0, wGrant: !!prev.wGrant,
    miles: Array.isArray(prev.miles) ? prev.miles.slice() : [],
    intro: !!prev.intro
  };
  var pt = Math.max(0, Number(p.playTime) || 0);
  var stt = p.statistics || {};
  var kc = Math.max(0, Number(stt.killCount) || 0);
  var bt = Math.max(0, Number(stt.breakthroughCount) || 0);
  var changed = false;
  if (ap.d !== today) { ap.d = today; ap.pBase = pt; ap.pGrant = 0; ap.kBase = kc; ap.q = false; ap.k = false; changed = true; }
  if (ap.w !== week) { ap.w = week; ap.wBase = pt; ap.wGrant = false; changed = true; }
  var add = 0, notes = [];
  /* 甲 每日任务全清 */
  var dq = p.dailyQuests;
  if (!ap.q && dq && dq.length > 0) {
    var allDone = true;
    for (var i = 0; i < dq.length; i++) { if (!dq[i] || !dq[i].completed) { allDone = false; break; } }
    if (allDone) { ap.q = true; add += 2; notes.push("\u6bcf\u65e5\u4efb\u52a1\u5168\u6e05 +2"); changed = true; }
  }
  /* 乙 在线修行（当日增量满 1 小时，日上限 1） */
  if (ap.pGrant < 1 && pt - ap.pBase >= 3600000) { ap.pGrant = 1; add += 1; notes.push("\u5728\u7ebf\u4fee\u884c\u6ee1 1 \u5c0f\u65f6 +1"); changed = true; }
  /* 丙 今日首斩 */
  if (!ap.k && kc > ap.kBase) { ap.k = true; add += 1; notes.push("\u4eca\u65e5\u9996\u65a9 +1"); changed = true; }
  /* 丁 周常（本周增量满 5 小时，周上限 1） */
  if (!ap.wGrant && pt - ap.wBase >= 18000000) { ap.wGrant = true; add += 3; notes.push("\u672c\u5468\u5728\u7ebf\u6ee1 5 \u5c0f\u65f6 +3"); changed = true; }
  /* 戊 里程碑（一次性，7 项） */
  var ridx = YLXW_AP_REALM.indexOf(p.realm);
  var MILE = [
    ["realm1", ridx >= 1, 2, "\u9996\u6b21\u8e0f\u5165\u7b51\u57fa\u671f"],
    ["realm2", ridx >= 2, 3, "\u9996\u6b21\u8e0f\u5165\u91d1\u4e39\u671f"],
    ["realm3", ridx >= 3, 3, "\u9996\u6b21\u8e0f\u5165\u5143\u5a74\u671f"],
    ["kill100", kc >= 100, 1, "\u7d2f\u8ba1\u51fb\u6740 100"],
    ["kill500", kc >= 500, 2, "\u7d2f\u8ba1\u51fb\u6740 500"],
    ["kill2000", kc >= 2000, 3, "\u7d2f\u8ba1\u51fb\u6740 2000"],
    ["bt20", bt >= 20, 2, "\u7d2f\u8ba1\u7a81\u7834 20 \u6b21"]
  ];
  for (var j = 0; j < MILE.length; j++) {
    var m = MILE[j];
    if (m[1] && ap.miles.indexOf(m[0]) < 0) { ap.miles.push(m[0]); add += m[2]; notes.push("\u91cc\u7a0b\u7891\u00b7" + m[3] + " +" + m[2]); changed = true; }
  }
  if (!ap.intro) { ap.intro = true; changed = true; }
  if (!changed) return;
  YLXW_AP_BUSY = true;
  try {
    st.setPlayer(function (T) {
      if (!T) return null;
      return Object.assign({}, T, { attributePoints: (Number(T.attributePoints) || 0) + add, ylAp: ap });
    });
    if (add > 0) { st.addLog("\u2728 \u5347\u7ea7\u70b9 +" + add + "\uff08" + notes.join(" \u00b7 ") + "\uff09", "gain"); }
    if (prev.intro !== true) { st.addLog("\ud83d\udcd6 " + YlxwApHint(), "special"); }
  } finally { YLXW_AP_BUSY = false; }
}
'''

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# 挂块锚：基础 bundle 里已有的 logs 订阅（顶层语句边界；全目录仅此 1 处，无其它模块占用）
HOOK_ANCHOR = ('Be.subscribe(t=>t.logs,(t,r)=>{t&&r&&t.length>r.length&&Ny()},'
               '{equalityFn:Object.is});')

# 新订阅：player 变化时跑一次发放评估（只读比较 + 有变化才写，BUSY 防自触发递归）
HOOK_NEW = (HOOK_ANCHOR + '\n'
            'Be.subscribe(t=>t.player,(t,r)=>{if(t&&r&&t!==r){try{YlxwApTick()}catch(e){}}},'
            '{equalityFn:Object.is});')


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r070 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 1) 模块块（函数声明提升；插在顶层 logs 订阅语句之前）
    p.insert_before('r070-block', HOOK_ANCHOR, blk + '\n',
                    expect=1, note='注入 YLXW_AP_REALM / YlxwApDay / YlxwApWeekKey / YlxwApHint / YlxwApTick')

    # 2) 挂 player 订阅（评估 + 发放）
    p.replace('r070-hook', HOOK_ANCHOR, HOOK_NEW, expect=1,
              note='player 变更时评估升级点发放（幂等，BUSY 防递归）')

    gates = [
        # ================= 本模块改动 =================
        ('R70·境界表已注入',        'var YLXW_AP_REALM = [', 1, '==', ''),
        ('R70·北京日函数已注入',    'function YlxwApDay(ms) {', 1, '==', ''),
        ('R70·北京周键函数已注入',  'function YlxwApWeekKey(ms) {', 1, '==', ''),
        ('R70·主评估函数已注入',    'function YlxwApTick() {', 1, '==', ''),
        ('R70·递归护栏已注入',      'var YLXW_AP_BUSY = false;', 1, '==', ''),
        ('R70·护栏生效',            'if (YLXW_AP_BUSY) return;', 1, '==', ''),
        ('R70·说明文案函数已注入',  'function YlxwApHint() {', 1, '==', ''),
        # ---- 甲：每日任务全清 ----
        ('R70·甲 判定全清',         'if (!dq[i] || !dq[i].completed) { allDone = false; break; }', 1, '==', ''),
        ('R70·甲 给 2 点',          'if (allDone) { ap.q = true; add += 2;', 1, '==', ''),
        # ---- 乙：在线修行 ----
        ('R70·乙 满 1 小时',        'if (ap.pGrant < 1 && pt - ap.pBase >= 3600000) { ap.pGrant = 1; add += 1;', 1, '==', ''),
        # ---- 丙：今日首斩 ----
        ('R70·丙 当日首斩',         'if (!ap.k && kc > ap.kBase) { ap.k = true; add += 1;', 1, '==', ''),
        # ---- 丁：周常在线 ----
        ('R70·丁 本周满 5 小时',    'if (!ap.wGrant && pt - ap.wBase >= 18000000) { ap.wGrant = true; add += 3;', 1, '==', ''),
        # ---- 戊：里程碑 ----
        ('R70·戊 去重表',           'ap.miles.indexOf(m[0]) < 0', 1, '==', ''),
        ('R70·戊 首次筑基',         '["realm1", ridx >= 1, 2,', 1, '==', ''),
        ('R70·戊 累计击杀 2000',    '["kill2000", kc >= 2000, 3,', 1, '==', ''),
        ('R70·戊 累计突破 20 次',   '["bt20", bt >= 20, 2,', 1, '==', ''),
        # ---- 发放 / 持久化 ----
        ('R70·发放写属性点+计数',   '{ attributePoints: (Number(T.attributePoints) || 0) + add, ylAp: ap }', 1, '==', ''),
        ('R70·发点日志',            zh('\u5347\u7ea7\u70b9 +'), 1, '==', ''),
        ('R70·首启说明日志',        zh('\u5347\u7ea7\u70b9\u83b7\u53d6\uff1a'), 1, '==', ''),
        # ---- 挂点 ----
        ('R70·player 订阅已挂',     'Be.subscribe(t=>t.player,(t,r)=>{if(t&&r&&t!==r){try{YlxwApTick()}catch(e){}}},{equalityFn:Object.is});', 1, '==', ''),
        ('R70·原 logs 订阅未动',    HOOK_ANCHOR, 1, '==', '基础 bundle 语句，逐字保留'),
        # ================= 冻结：既有给点来源一个字不动 =================
        ('冻结·突破给点未动',       'attributePoints:g.attributePoints+Ae', 1, '==', 'R-070 不动突破'),
        ('冻结·传承给点未动',       'attributePoints:f.attributePoints+ie', 1, '==', 'R-070 不动传承'),
        ('冻结·图鉴给点未动',       'attributePoints:T.attributePoints+x', 1, '==', 'R-070 不动灵草图鉴'),
        ('冻结·突破给点函数未动',   'F0=(t,r,a=0)=>{', 1, '==', ''),
        ('冻结·属性分配逻辑未动',   'handleAllocateAttribute:', 5, '==', '定义 + 4 个调用点'),
        ('冻结·初始/一键分配清零未动', 'attributePoints:0,', 2, '==', '新号初始值 + 一键分配后清零'),
        # 注入块限域内不得出现任何网络调用 / 禁用模式（纯客户端）
        ('R70·注入块内无网络调用',  'fetch(', 0, '==', '本模块纯本地发放',
         ('/* ===== yl-R070 apgain:', 'function YlxwApTick() {')),
        ('R70·注入块内无禁用模式',  'X-YL-', 0, '==', '', ('/* ===== yl-R070 apgain:', 'function YlxwApTick() {')),
    ]
    return gates
