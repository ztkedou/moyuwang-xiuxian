# -*- coding: utf-8 -*-
r"""
yl_fun2_ext.py — R-029「每日行乐：茶馆结果可查看记录」客户端单模块

需求原文（用户）
--------------------------------------------------------------------------
  「茶馆结果通过信箱发送，或在每日行乐里添加可查看记录（二选一，建议后者，风险低）」
  ⇒ 采纳**后者**（纯展示层，零入账改动）。

侦察（构建产物 index-v2811-20260930.js 逐字实证）
--------------------------------------------------------------------------
  · 每日行乐面板 = `function YlxwTDaily()`（@890979，yl_fun086_ext 注入），
    数据源 `YlxwUseList("/teahouse/today")`，即 `t`。
  · 面板已有 myBet 行：
      `m && e.jsxs(YlxwRow, { children: ["我的下注：" + YlxwSide(...) + " · " + N + " 灵石",
       ..."（已押 x/y 注）", ..."茶运 X ×N"] })`
    —— **只显示下注信息，不显示输赢与派彩**。
  · 服务端 `/api/teahouse/today`（srv:10812）已下发：
      `myBet: { side, stones, won, payout, times }`
      `won` = null（未结算）/ 0（未中）/ 1（中）；`payout` 同。
      ⇒ **结果数据早就在手，只是前端没渲染** ⇒ 本模块零服务端改动即可展示今日结果。
  · 「记录」维度：`teahouse_bets` 表按 (user_id, date) 一行（srv:857），
    天然是逐日流水。可选服务端补丁 `srv_patch_fun2.py` 在 today 响应里补
    `myHistory`（近 14 日）；**缺该字段时本模块自动不渲染历史块**（向后兼容）。

改法（1 处就地追加，锚点实测唯一）
--------------------------------------------------------------------------
  在 myBet 行之后追加两块（均为只读展示，零网络、零入账）：
    A 「茶馆结果」行：待揭晓 / 赢 · 派彩 +N / 未中 · 本金 N
    B 「茶馆记录」折叠块（仅当 `Array.isArray(t.myHistory)` 才渲染）：
        逐日一行：date · 押 N 灵石 · 赢 +M / 未中 / 待结算

硬约束
--------------------------------------------------------------------------
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS。
  · 不改 `/teahouse/bet`、不改结算（teaSettleDue）、不改任何入账口径。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py、不写 build/assets/。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R029: 茶馆结果「可查看记录」=====
   今日结果：服务端 myBet.won/payout（null=待揭晓 / 0=未中 / 1=中）。
   历史记录：服务端可选下发 myHistory（srv_patch_fun2.py）；缺省不渲染历史块。
   纯展示层，零网络零入账。 */
function YlxwTeaResultText(m, t) {
  if (!m) return "";
  if (m.won == null) return "待揭晓（" + YlxwNum((t && t.closesAtUtcHour) || 13) + ":00 UTC 结算）";
  if (Number(m.won) === 1) return "赢 · 派彩 +" + YlxwNum(m.payout).toLocaleString() + " 灵石";
  return "未中 · 本金 " + YlxwNum(m.stones).toLocaleString() + " 灵石";
}
function YlxwTeaHistText(h) {
  var s = (h && h.date ? String(h.date) : "") + " · 押 " + YlxwNum(h && h.stones).toLocaleString() + " 灵石";
  if (!h || h.won == null) return s + " · 待结算";
  if (Number(h.won) === 1) return s + " · 赢 +" + YlxwNum(h.payout).toLocaleString();
  return s + " · 未中";
}
'''

# --------------------------------------------------------------------------- 锚点常量

# 注入锚：v2810c 块内的模块级函数（depth=2）
INJECT_ANCHOR = 'function YlxwFtHarvestText(cd, slot) {'

# myBet 行的尾段（全仓唯一）：其后紧接 YlxwFunBetBar
MYBET_TAIL = (r'children: "\u8336\u8fd0 " + ((t.luck && t.luck.label) || "\u5e73") '
              r'+ " \u00d7" + YlxwNum(t.luck && t.luck.tier) })] }), ')

RESULT_ROW = (r'children: "\u8336\u8fd0 " + ((t.luck && t.luck.label) || "\u5e73") '
              r'+ " \u00d7" + YlxwNum(t.luck && t.luck.tier) })] }), '
              r'm && e.jsxs(YlxwRow, { children: ["\u8336\u9986\u7ed3\u679c\uff1a" '
              r'+ YlxwTeaResultText(m, t)] }), '
              r'Array.isArray(t.myHistory) && e.jsxs("details", '
              r'{ className: "text-xs text-stone-400", children: ['
              r'e.jsx("summary", { children: "\u8336\u9986\u8bb0\u5f55" }), '
              r'e.jsxs("div", { className: "space-y-1 pt-1.5", children: '
              r't.myHistory.length ? t.myHistory.map(function (h) { '
              r'return e.jsx("div", { children: YlxwTeaHistText(h) }, h.date); }) '
              r': e.jsx("div", { children: "\u6682\u65e0\u5386\u53f2\u8bb0\u5f55" }) }) ] }), ')


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 fun086）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('fun2 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 模块级工具函数（depth=2）
    p.insert_before('fun2-helpers', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 YlxwTeaResultText / YlxwTeaHistText')

    # 1) myBet 行后追加「茶馆结果」行 +「茶馆记录」折叠块
    p.replace('fun2-tea-result', MYBET_TAIL, RESULT_ROW, expect=1,
              note='茶馆结果可查看（今日 + 可选历史）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 注入块 =================
        ('R29·今日结果函数已注入',   'function YlxwTeaResultText(m, t) {', 1, '==', ''),
        ('R29·历史行函数已注入',     'function YlxwTeaHistText(h) {', 1, '==', ''),
        ('R29·待揭晓分支',           r'return "\u5f85\u63ed\u6653\uff08"', 1, '==', 'won==null'),
        ('R29·赢分支',               r'return "\u8d62 \u00b7 \u6d3e\u5f69 +"', 1, '==', 'won==1'),
        ('R29·未中分支',             r'return "\u672a\u4e2d \u00b7 \u672c\u91d1 "', 1, '==', 'won==0'),
        # ================= 面板渲染 =================
        ('R29·结果行已挂到面板',     r'm && e.jsxs(YlxwRow, { children: ["\u8336\u9986\u7ed3\u679c\uff1a" + YlxwTeaResultText(m, t)] })', 1, '==', ''),
        ('R29·记录块已挂到面板',     r'Array.isArray(t.myHistory) && e.jsxs("details", { className: "text-xs text-stone-400", children: [e.jsx("summary", { children: "\u8336\u9986\u8bb0\u5f55" })', 1, '==', '缺 myHistory 时整块不渲染'),
        ('R29·历史逐日渲染',         r't.myHistory.length ? t.myHistory.map(function (h) { return e.jsx("div", { children: YlxwTeaHistText(h) }, h.date); })', 1, '==', ''),
        ('R29·空历史兜底',           r': e.jsx("div", { children: "\u6682\u65e0\u5386\u53f2\u8bb0\u5f55" }) }) ] }),', 1, '==', ''),
        # ================= 冻结（不得回踩行乐/茶馆） =================
        ('冻结·每日行乐面板唯一',    'function YlxwTDaily() {', 1, '==', ''),
        ('冻结·茶馆 today 调用未动', 'YlxwUseList("/teahouse/today")', 1, '==', ''),
        ('冻结·下注端点未动',        '"/teahouse/bet"', 2, '==', '两个下注按钮'),
        ('冻结·myBet 行本体未动',    r'children: ["\u6211\u7684\u4e0b\u6ce8\uff1a" + YlxwSide(t && t.topic, m.side)', 1, '==', ''),
        ('冻结·下注按钮守卫未动',    'disabled: !!u || !t.open || (!!m && YlxwNum(m.times) >= YlxwNum(t.maxTimes || 3))', 2, '==', ''),
        ('冻结·行乐三件套未动',      r'children: "\u884c\u4e50\u4e09\u4ef6\u5957"', 1, '==', ''),
        ('冻结·掷骰面板未动',        'function YlxwFunDice', 1, '>=', ''),
        ('R29·未新增网络调用',       'fetch(', 0, '==', '纯展示层，无网络',
         ('/* ===== yl-R029:', 'function YlxwFtHarvestText(cd, slot) {')),
    ]
    return gates
