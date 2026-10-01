# -*- coding: utf-8 -*-
r"""
yl_053_ext.py — R-053 每日行乐·茶馆：押注按钮全灰的「灰因动态提示」+ 玩法说明补齐

需求（台账 R-053 原文）
--------------------------------------------------------------------------
  「每日行乐茶馆怎么押注按钮都是灰色的。是时间太晚了吗，把玩法说明要加上。」

根因（已侦察证实，用户猜测完全正确——是时间问题，且 UI 从不解释）
--------------------------------------------------------------------------
  · 按钮灰三因（bundle YlxwTDaily，fun086 注入段）：
      disabled: !!u || !t.open || (!!m && YlxwNum(m.times) >= YlxwNum(t.maxTimes || 3))
      = 请求中 / 非开放时段 / 今日 3 注用尽
  · 服务端权威（srv/index_v28.ts:11316、:11537）：
      const TEA_OPEN_UTC = 13;  const open = new Date().getUTCHours() < TEA_OPEN_UTC;
    ⇒ 开放窗 = UTC 0:00~12:59 = 北京时间 08:00~20:59；21:00 开盅后按钮全灰。
    ⇒ 用户晚上打开 → 恒灰。面板只有一行「下注中: 否」，没有任何规则说明。
  · 服务端已下发 closesAtUtcHour（=13），客户端从未展示 → 可用来做动态文案。

本模块动作（纯客户端就地替换 ×2，INJECT_JS=''，零网络、零服务端改动）
--------------------------------------------------------------------------
  ① 玩法说明块：插在「下注中/赔率/单注上限/最低」Kv 行之后、「我的下注」行之前。
     5 行说明：玩法与赔率 / 注额与次数 / 开放时间（回应"按钮为什么灰"）/
     茶运加成 / 行乐三件套互不占用。
  ② 动态灰因提示行：插在 A/B 押注按钮行之前。
     !t.open → 红字「茶馆已开盅：每日 21:00 结算，明日 08:00 起可再押」
     （21:00 由服务端下发的 closesAtUtcHour 动态计算，不写死）；
     次数用尽 → 灰字「今日 3 注已用完，明日赶早」（3 动态取 maxTimes）。

硬约束 / 纪律
--------------------------------------------------------------------------
  · **不改按钮 disabled 表达式本身** —— 那是 yl_fun2_ext.py 冻结门禁串
    （expect==2），动了打爆 R-029。本模块只在按钮行之前插入提示。
  · 次数判断刻意写成 `YlxwNum(m.times) >= (YlxwNum(t.maxTimes) || 3)`
    （括号位置与 fun2 冻结串不同），语义等价、字面零重叠。
  · 文案数值全部与服务端常量对齐：TEA_MIN_BET=500 / TEA_MAX_BET=50000 /
    TEA_MAX_BETS=3 / TEA_PAYOUT=1.9 / 茶运修为=注额×档位×2（teaSettleDue）。
  · 新串中文字面全部经 ctx['zh'] 转义成 \uXXXX，落 bundle 后为纯 ASCII，
    与 fun086 注入段形态一致；apply 内自检 isascii。
  · 样式类只用编译后 CSS 已验证存在的：text-[11px] / leading-relaxed /
    text-stone-400 / bg-ink-900/60 / border-stone-600 / rounded / p-2 /
    space-y-1 / text-red-300 / pb-1 / text-xs（build/assets/index-ZuV-l8Gt.css
    逐一 grep 通过；border-stone-700/60 不存在故弃用）。
  · 不碰 build_v26n.py / localtest/ / srv/index_v28.ts / CHANGELOG.md。
"""

import re

INJECT_JS = ''          # 纯就地替换，不需要注入块

# --------------------------------------------------------------------------- 锚点

# ① Kv 行尾部（「下注中/赔率/单注上限/最低」的 data 收尾）→「我的下注」行开头。
#    侦察：链上前态 count==1（2026-10-01 复验：v28114 构建产物逆向剥离本模块两补丁
#    得链上前态，两锚各 count==1；Patcher 重放后与 v28114 逐字节一致）。
A_KV_TAIL = '"\\u6700\\u4f4e": t.minBet } }), m && e.jsxs(YlxwRow,'

# ② A/B 押注按钮行 div 开头。注意：只取前缀做插入点，**不含完整 disabled 表达式**，
#    fun2 冻结串（… || (!!m && YlxwNum(m.times) >= …）保持原样 2 次。
#    侦察：链上前态 count==1（复验口径同上）。
A_BTN_ROW = ('e.jsxs("div", { className: "flex gap-2", children: ['
             'e.jsx(YlxwBtn, { disabled: !!u || !t.open')


# --------------------------------------------------------------------------- 组装

def _help_block(zh):
    """玩法说明块（5 行，样式类全部已在编译 CSS 验证存在）。"""
    lines = [
        '【玩法说明】每天一道茶馆话题，押 A 或 B 一方；每日 21:00 开盅，押中按注额 ×1.9 返还（含本金）。',
        '注额 500～50000 灵石，每日最多 3 注，只能追加同一边，累计上限 150000 灵石。',
        '开放时间：每日 08:00～21:00（北京时间）。时段外按钮为灰色属正常，不是故障。',
        '茶运每日随机「平 / 旺 / 大旺」：押中额外送修为（注额 × 档位 × 2），旺/大旺有机会附送抽奖券。',
        '下方「行乐三件套」（掷骰比大小 / 每日一签 / 灵石翻牌）各有独立次数，与茶馆下注互不占用。',
    ]
    inner = ''.join('e.jsx("div", { children: "%s" }),' % zh(x) for x in lines)
    return (
        'e.jsx("div", { className: "text-[11px] leading-relaxed text-stone-400 '
        'bg-ink-900/60 border border-stone-600 rounded p-2 space-y-1", '
        'children: [' + inner + '] })'
    )


def _hint_row(zh):
    """动态灰因提示行：!t.open → 开盅提示（结算时点动态）；否则次数用尽提示。"""
    return (
        '!t.open ? e.jsx("div", { className: "text-xs text-red-300 pb-1", children: "'
        + zh('茶馆已开盅：每日 ')
        + '" + (((Number(t.closesAtUtcHour) || 13) + 8) % 24) + "'
        + zh(':00 结算，明日 08:00 起可再押')
        + '" }) : (m && YlxwNum(m.times) >= (YlxwNum(t.maxTimes) || 3)) ? '
        'e.jsx("div", { className: "text-xs text-stone-400 pb-1", children: "'
        + zh('今日 ')
        + '" + (YlxwNum(t.maxTimes) || 3) + "'
        + zh(' 注已用完，明日赶早')
        + '" }) : null,'
    )


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    zh = ctx['zh']

    help_block = _help_block(zh)
    hint_row = _hint_row(zh)

    # 自检：两个新串落 bundle 必须纯 ASCII（与 fun086 注入段形态一致）；
    # 且不得含 V28_BAN_PATTERNS 与任何已知 0-期望门禁的字面。
    for tag, s in (('help', help_block), ('hint', hint_row)):
        if not s.isascii():
            raise AssertionError('r053 新串(%s)含非 ASCII：zh() 转义失效' % tag)
        for bad in ('iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-',
                    'fetch(', 'disabled:', 'spiritStones', 'md:grid', 'md:sticky'):
            if bad in s:
                raise AssertionError('r053 新串(%s)含危险/撞门禁字面: %r' % (tag, bad))

    # 说明块：插在 Kv 行之后、我的下注行之前
    p.replace('r053-help', A_KV_TAIL,
              '"\\u6700\\u4f4e": t.minBet } }), ' + help_block + ', m && e.jsxs(YlxwRow,',
              expect=1, note='茶馆玩法说明块（开放时间/赔率/次数/茶运/三件套）')

    # 动态灰因提示：插在 A/B 按钮行之前（disabled 表达式原样保留）
    p.replace('r053-hint', A_BTN_ROW, hint_row + ' ' + A_BTN_ROW,
              expect=1, note='按钮灰因动态提示（已开盅 / 次数用尽）')

    gates = [
        # ================= 本模块改动 =================
        ('R53·说明块已插入',          zh('【玩法说明】'), 1, '==', '5 行说明块标题'),
        ('R53·灰因解释到位',          zh('时段外按钮为灰色属正常'), 1, '==', '正面回答「按钮为什么灰」'),
        ('R53·赔率与开盅写明',        zh('押中按注额 ×1.9 返还'), 1, '==', 'TEA_PAYOUT=1.9 含本金'),
        ('R53·次数与注额写明',        zh('每日最多 3 注'), 1, '==', 'TEA_MAX_BETS=3'),
        ('R53·开盅提示动态时点',      '(((Number(t.closesAtUtcHour) || 13) + 8) % 24)', 1, '==', 'closesAtUtcHour+8 %24，不写死'),
        ('R53·明日可押文案',          zh('明日 08:00 起可再押'), 1, '==', 'UTC 日切 08:00 重开'),
        ('R53·次数用尽提示',          zh(' 注已用完，明日赶早'), 1, '==', ''),
        ('R53·茶运说明',              zh('押中额外送修为'), 1, '==', 'teaSettleDue luckExp=注额×tier×2'),
        ('R53·三件套互不占用',        zh('与茶馆下注互不占用'), 1, '==', ''),
        ('R53·说明块类串唯一',        'bg-ink-900/60 border border-stone-600 rounded p-2 space-y-1', 1, '==', '全部为编译 CSS 已验证类'),
        # ================= 冻结：相邻需求面一字未动 =================
        ('冻结·fun2 按钮守卫串仍 2',  'disabled: !!u || !t.open || (!!m && YlxwNum(m.times) >= YlxwNum(t.maxTimes || 3))', 2, '==', 'R-029 冻结门禁同串，本模块只在行前插入'),
        ('冻结·bet1 调用未动',        'f("bet1", "/teahouse/bet", { side: 0', 1, '==', ''),
        ('冻结·bet2 调用未动',        'f("bet2", "/teahouse/bet", { side: 1', 1, '==', ''),
        ('冻结·myBet 行未动',         r'children: ["\u6211\u7684\u4e0b\u6ce8\uff1a" + YlxwSide(t && t.topic, m.side)', 1, '==', 'R-029'),
        ('冻结·下注中 KV 未动',       r'"\u4e0b\u6ce8\u4e2d": t.open ? "\u662f" : "\u5426"', 1, '==', ''),
        ('冻结·注额条未动',           'e.jsx(YlxwFunBetBar, { label: "\\u6ce8\\u989d", value: funBet', 1, '==', 'fun086 F3'),
        ('冻结·行乐三件套挂载未动',   r'children: "\u884c\u4e50\u4e09\u4ef6\u5957"', 1, '==', 'fun086 F3'),
        ('冻结·茶馆记录块未动',       r'children: "\u8336\u9986\u8bb0\u5f55"', 1, '==', 'R-029'),
        ('冻结·茶馆标题未动',         r'children: "\u6bcf\u65e5\u884c\u4e50 \u00b7 \u8336\u9986"', 1, '==', ''),
        ('冻结·面板函数仍唯一',       'function YlxwTDaily() {', 1, '==', ''),
    ]
    return gates
