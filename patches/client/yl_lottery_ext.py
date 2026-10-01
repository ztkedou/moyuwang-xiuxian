# -*- coding: utf-8 -*-
r"""
yl_lottery_ext.py — R-031「抽奖：默认面板自定义数量 + 完整面板返回精简」客户端单模块

需求原文（用户）
--------------------------------------------------------------------------
  「① 默认抽奖添加自定义数量按钮；② 完整抽奖面板要有返回精简面板的按钮」

侦察（构建产物 index-v2811-20260930.js 逐字实证）
--------------------------------------------------------------------------
  · **精简（默认）面板** = `function YlxwTDrawQuick(p)`（@1286728，v2810d 注入）：
      按钮仅三个：`单抽（1 张）` / `十连抽（10 张）` / `完整抽奖面板`；
      抽奖执行体 `ck(p).handleDraw(N)`（@1720086）**接受任意正整数 N**
      （只校验 `lotteryTickets < N` 与 `Number.isInteger`），
      且抽奖为**纯客户端**（全仓无 `/lottery/draw` 端点）⇒ 无服务端次数上限。
      ⇒ ① 在精简面板补「自定义数量」输入 + 「自定义 N 抽」按钮即可，零服务端改动。
  · **完整面板** = `NM=({isOpen,onClose:r,player:a,onDraw:l})`（@1565556，基座自带）：
      已含 `自定义连抽` 输入框 + `抽 x 次` 按钮（**① 的完整版早已存在**）；
      但**没有**回到精简面板的按钮（只能点遮罩/ESC 关闭）。
      ⇒ ② 在完整面板内容区顶部补「返回精简面板」按钮（`onClick: r`）。

改法（1 处注入 + 3 处就地替换）
--------------------------------------------------------------------------
  E1 精简面板挂 `__qty` state（默认 5）
  E2 精简面板按钮行插入「自定义数量输入 + 自定义 N 抽」控件
  E3 完整面板内容区顶部插入「返回精简面板」按钮

硬约束
--------------------------------------------------------------------------
  · 不改 `ck.handleDraw` 抽奖本体、不改 `NM` 的单抽/十连/自定义连抽、不改奖品池。
  · 抽奖次数上限沿用既有校验（`handleDraw` 内 `lotteryTickets < N`）。
  · 注入块 zh() 后纯 ASCII；每个 replace 带 expect=精确次数。
  · 只新建本文件；不改 build_v26n.py、不写 build/assets/。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R031: 抽奖精简面板「自定义数量」 =====
   精简面板原本只有 单抽(1)/十连抽(10)；本模块补一个自定义数量输入 + 按钮。
   抽奖执行体 ck(p).handleDraw(N) 原生支持任意正整数 N（纯客户端，无服务端上限），
   故本模块只做 UI，不改任何抽奖逻辑。 */
'''

# --------------------------------------------------------------------------- 锚点常量

# 注入锚：v2810c 块内的模块级函数（depth=2）
INJECT_ANCHOR = 'function YlxwFtHarvestText(cd, slot) {'

# E1 精简面板 state
E1_OLD = 'var st = O.useState(!1), open = st[0], setOpen = st[1];'
E1_NEW = ('var st = O.useState(!1), open = st[0], setOpen = st[1];\n'
          '  var __qt = O.useState(5), __qty = __qt[0], __setQty = __qt[1];')

# E2 精简面板按钮行：完整面板按钮之前插入自定义控件
E2_OLD = ('e.jsx("button", { onClick: function () { setOpen(!0); },\n'
          '          className: btn + "bg-ink-800 hover:bg-stone-700 border-stone-600 text-stone-200",\n'
          '          children: "\\u5b8c\\u6574\\u62bd\\u5956\\u9762\\u677f" })')
E2_NEW = ('e.jsxs("div", { className: "flex items-center gap-1", children: [\n'
          '          e.jsx("input", { type: "number", min: "1", value: __qty, title: "\\u81ea\\u5b9a\\u4e49\\u62bd\\u5956\\u6570\\u91cf",\n'
          '            onChange: function (ev) { var __q = parseInt(ev.target.value, 10); __setQty(isNaN(__q) || __q < 1 ? 1 : Math.min(__q, 999)); },\n'
          '            className: "w-16 px-2 py-1.5 bg-ink-800 border border-stone-600 rounded text-xs text-stone-200 focus:outline-none focus:border-yellow-500" }),\n'
          '          e.jsx("button", { onClick: function () { h.handleDraw(__qty); }, disabled: tk < __qty,\n'
          '            className: btn + "bg-purple-900 hover:bg-purple-800 border-purple-600 text-stone-100 " + off,\n'
          '            children: "\\u81ea\\u5b9a\\u4e49 " + __qty + " \\u62bd" })\n'
          '        ] }),\n'
          '        e.jsx("button", { onClick: function () { setOpen(!0); },\n'
          '          className: btn + "bg-ink-800 hover:bg-stone-700 border-stone-600 text-stone-200",\n'
          '          children: "\\u5b8c\\u6574\\u62bd\\u5956\\u9762\\u677f" })')

# E3 完整面板内容区顶部：返回精简面板
E3_OLD = 'closeOnEsc:!c,children:e.jsxs("div",{className:"space-y-6",children:['
E3_NEW = ('closeOnEsc:!c,children:e.jsxs("div",{className:"space-y-6",children:['
          'e.jsx("div",{className:"flex justify-end",children:e.jsx("button",'
          '{onClick:r,disabled:c,className:"px-3 py-1.5 rounded border border-stone-600 bg-ink-800 hover:bg-stone-700 text-xs text-stone-200 disabled:opacity-50 disabled:cursor-not-allowed",'
          'children:"\\u8fd4\\u56de\\u7cbe\\u7b80\\u9762\\u677f"})}),')

EDITS = [
    ('E1 精简面板挂 __qty state', E1_OLD, E1_NEW, 1),
    ('E2 精简面板插自定义数量控件', E2_OLD, E2_NEW, 1),
    ('E3 完整面板插返回精简按钮',  E3_OLD, E3_NEW, 1),
]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('lottery 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 模块级注入（注释块，标记归属）
    p.insert_before('lottery-block', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 R-031 标记块')

    # 1) 就地替换
    for name, old, new, exp in EDITS:
        p.replace(name, old, new, expect=exp)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= E1 =================
        ('R31·精简面板 __qty state',  'var __qt = O.useState(5), __qty = __qt[0], __setQty = __qt[1];', 1, '==', ''),
        # ================= E2 =================
        ('R31·自定义数量输入框',      'e.jsx("input", { type: "number", min: "1", value: __qty,', 1, '==', ''),
        ('R31·自定义抽奖按钮',        r'children: "\u81ea\u5b9a\u4e49 " + __qty + " \u62bd" })', 1, '==', ''),
        ('R31·按钮走既有 handleDraw', 'onClick: function () { h.handleDraw(__qty); }', 1, '==', '不改抽奖本体'),
        ('R31·券不足禁用',            'disabled: tk < __qty,', 1, '==', ''),
        ('R31·输入钳制正整数',        'isNaN(__q) || __q < 1 ? 1 : Math.min(__q, 999)', 1, '==', ''),
        ('R31·完整面板按钮仍唯一',    r'children: "\u5b8c\u6574\u62bd\u5956\u9762\u677f" })', 1, '==', ''),
        # ================= E3 =================
        ('R31·返回精简面板按钮',      r'children:"\u8fd4\u56de\u7cbe\u7b80\u9762\u677f"})}),', 1, '==', ''),
        ('R31·返回按钮走 onClose',    '{onClick:r,disabled:c,className:"px-3 py-1.5 rounded border border-stone-600 bg-ink-800 hover:bg-stone-700 text-xs text-stone-200 disabled:opacity-50 disabled:cursor-not-allowed",', 1, '==', 'r = NM 的 onClose'),
        # ================= 冻结（不得回踩抽奖本体/完整面板） =================
        ('冻结·抽奖执行体未动',       'function ck(t){const r=Be(S=>S.player)', 1, '==', ''),
        ('冻结·handleDraw 券校验未动', 'if(!d||d.lotteryTickets<S){f("抽奖券不足！","danger");return}', 1, '==', ''),
        ('冻结·handleDraw 正整数校验未动', 'if(S<=0||!Number.isInteger(S)){f("抽奖次数必须为正整数！","danger");return}', 1, '==', ''),
        ('冻结·完整面板自定义连抽未动', 'children:"自定义连抽"', 1, '==', '完整面板①早已存在'),
        ('冻结·完整面板抽 x 次按钮未动', 'children:x>0?`抽 ${x} 次`:"输入抽奖次数"', 1, '==', ''),
        ('冻结·单抽按钮未动',         r'children: "\u5355\u62bd\uff081 \u5f20\uff09"', 1, '==', ''),
        ('冻结·十连按钮未动',         r'children: "\u5341\u8fde\u62bd\uff0810 \u5f20\uff09"', 1, '==', ''),
        ('冻结·精简面板唯一',         'function YlxwTDrawQuick(p) {', 1, '==', ''),
        ('冻结·完整面板唯一',         'NM=({isOpen:t,onClose:r,player:a,onDraw:l})=>', 1, '==', ''),
        ('R31·未新增网络调用',        'fetch(', 0, '==', '抽奖纯客户端，无网络',
         ('/* ===== yl-R031:', 'function YlxwFtHarvestText(cd, slot) {')),
    ]
    return gates
