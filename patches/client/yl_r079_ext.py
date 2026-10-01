# -*- coding: utf-8 -*-
r"""
yl_r079_ext.py — R-079 玩法说明补齐（多面板「玩法说明」折叠块）

需求原文（用户）
--------------------------------------------------------------------------
  「同时排查所有功能项目，把没有玩法介绍的都补上玩法介绍。」

本模块范围（★ 只做「补说明」，不改任何数值 / 不改服务端 / 不动按钮逻辑）
--------------------------------------------------------------------------
  照 `yl_r021help_ext.py`（R-021 挂机收益）的做法：在面板里加**常显说明块**。
  本轮补齐 8 个此前无玩法说明的页签面板（逐个从代码读出真实规则）：

    1. 渡劫台（YlxwTRebirth）   —— 服务端 srv/index_v28.ts /api/rebirth/*
    2. 悬赏（YlxwTBounty）       —— 服务端 /api/bounty/*（BOUNTY_* 常量）
    3. 江湖志（YlxwTChronicle）  —— 服务端 /api/chronicle*（CHRONICLE_PRAISE_*）
    4. 仙途指引（YlxwTGuide）    —— 服务端 /api/guide/*（GUIDE_STEPS / WEEK_REWARDS）
    5. 九天通天塔（YlxwTTower）  —— 客户端 YlxwTowerFloor / YlxwTowerChallenge（v26n）
    6. 灵兽远征（YlxwTPetExp）   —— 客户端 YlxwExpSlots / YlxwExpLocations / YlxwExpStart（v26n）
    7. 交易行货款（YlxwTPayout） —— 客户端 YlxwTPayout（v26n 卖家收益托管）
    8. 妖灵（YlxwTPet）          —— 服务端 R-018/R-071 培养体系（常量逐条核对）

  文案里的每个数值都来自上列源码常量 / 客户端字面量，**不臆造**。
  规则复杂读不出的项（见报告）**不写**，宁缺勿编。

改法（1 处注入 + 8 处「就地追加」）
--------------------------------------------------------------------------
  E0 在 `function YlxwTRebirth() {` 之前注入通用折叠块 `YlxwR79Box(t, L)`
     （原生 `<details>`，零新依赖、零网络、零副作用；类名全部取自产物既有 Tailwind 类）。
  E1~E8 把每个面板标题节点（`e.jsx(YlxwTitle, {...})`）**后面追加**一个
     `, YlxwR79Box("标题", ["...","..."])` —— 标题节点本身**原样保留**，
     说明块作为 children 数组的新成员插在标题下方（`[<Title>, <Help>, ...]`）。

口径 / 硬约束
--------------------------------------------------------------------------
  · **只加说明，不改任何收益/概率/上限数值，不改服务端，不改按钮/领取逻辑**。
  · 追加式替换 ⇒ 标题锚点计数不变，不会打爆任何 `== 1` 的既有门禁。
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS；每个 replace 带精确 expect。
  · 只新建本文件；不改 build_v26n.py（接线由主控做）/ 不写 build/assets/。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R079: 通用「玩法说明」折叠块（多面板复用） =====
   纯展示：原生 <details> 折叠，默认展开标题、点开看细则；无状态、无网络、无副作用。
   类名全部取自产物既有 Tailwind 类（与 R-021 挂机收益说明同款）。
   ★ 只加「说明」，不改任何数值 / 不改服务端。 */
function YlxwR79Box(t, L) {
  return e.jsxs("details", {
    className: "mt-3 rounded border border-stone-700 bg-ink-900/60 px-3 py-2 text-xs text-stone-400",
    children: [
      e.jsx("summary", { className: "cursor-pointer select-none font-bold text-amber-300/90", children: "玩法说明：" + t }),
      e.jsx("div", { className: "mt-2 space-y-1.5 leading-relaxed", children: L.map(function (x, i) { return e.jsx("div", { children: x }, "r79" + i); }) })
    ]
  });
}
'''

# --------------------------------------------------------------------------- 注入锚

# 渡劫台组件定义行（前文是主屏收尾；全仓无其它模块引用此串，唯一）
INJECT_ANCHOR = 'function YlxwTRebirth() {'

# --------------------------------------------------------------------------- 各面板说明
# (patch_id, 标题节点锚点(自然中文), 标题, [正文行...])
# ★ 锚点 = 产物里该标题节点的**结尾片段**（追加式替换，锚点本身保留）。
PANELS = [
    (
        'r079-rebirth',
        'children: "\u6e21\u52ab\u53f0" })',
        '\u6e21\u52ab\u53f0',
        [
            '\u2460 \u4f55\u65f6\u80fd\u6e21\uff1a\u987b\u4fee\u81f3\u5f53\u524d\u5883\u754c\u7b2c\u4e5d\u5c42\u3001\u4e14\u4fee\u4e3a\u5706\u6ee1\uff08\u4fee\u4e3a \u2265 \u4e0a\u9650\uff09\u624d\u300c\u51c6\u5907\u5c31\u7eea\u300d\uff0c\u5426\u5219\u6309\u94ae\u7f6e\u7070\u3002',
            '\u2461 \u57ab\u5200\uff1a\u70b9\u300c\u57ab\u51dd\u5143\u4e39\u300d\u628a\u4ed3\u5e93\u51dd\u5143\u4e39\u8f6c\u5165\u5df2\u57ab\uff08\u6700\u591a 10 \u9897\uff09\uff0c\u6bcf\u9897\u4f7f\u6211\u65b9\u653b/\u9632/\u8840\u5404 +3%\uff1b\u80dc\u8d25\u7686\u711a\u3002',
            '\u2462 \u6210\u529f\uff1a\u664b\u5165\u76ee\u6807\u5883\u754c\u3001\u5c42\u6570\u5f52 1\u3001\u6ea2\u51fa\u4fee\u4e3a\u7ed3\u8f6c\uff0c\u5e76\u5168\u670d\u516c\u544a\u3001\u83b7\u300c\u6e21\u52ab\u98de\u5347\u300d\u79f0\u53f7\u3002',
            '\u2463 \u5931\u8d25\uff1a\u4fee\u4e3a\u6563\u529f\u4e94\u6210\uff08\u5f53\u5c42\u4fee\u4e3a\u69fd\u9707\u6563\u540e\u8fd4\u8fd8 50%\uff09\uff0c\u5e76\u51b7\u5374 10 \u5206\u949f\u3002',
            '\u2464 \u5df2\u81f3\u957f\u751f\u5883\u5373\u4ed9\u8def\u5c3d\u5934\uff0c\u65e0\u9700\u518d\u6e21\u52ab\u3002',
        ],
    ),
    (
        'r079-bounty',
        'e.jsx(YlxwTitle, { children: "\u60ac\u8d4f" })',
        '\u60ac\u8d4f',
        [
            '\u2460 \u53d1\u8d4f\uff1a\u586b\u6807\u9898\u4e0e\u8d4f\u91d1\uff08100 ~ 1000000 \u7075\u77f3\uff09\uff0c\u53d1\u5e03\u5373\u5168\u989d\u6258\u7ba1\u51bb\u7ed3\u3002',
            '\u2461 \u5206\u8d26\uff1a\u5b8c\u6210\u65b9\u5b9e\u5f97 90%\uff0c10% \u4e3a\u7cfb\u7edf\u7a0e\uff1b\u53d1\u5e03\u8005\u540c\u65f6\u6700\u591a\u6302 5 \u5355\u3002',
            '\u2462 \u63a5\u53d6\uff1a\u4e0d\u80fd\u63a5\u81ea\u5df1\u7684\u60ac\u8d4f\uff0c\u540c\u65f6\u6700\u591a\u63a5 3 \u5355\uff1b\u987b\u53d1\u5e03\u8005\u300c\u9a8c\u6536\u5b8c\u6210\u300d\u624d\u53d1\u653e\u8d4f\u91d1\u3002',
            '\u2463 \u9000\u5355\uff1a\u672a\u88ab\u63a5\u53d6\u72b6\u6001\u53ef\u64a4\u5355\u9000\u5168\u6b3e\uff1b\u60ac\u8d4f 24 \u5c0f\u65f6\u8fc7\u671f\u81ea\u52a8\u9000\u5168\u6b3e\u9000\u5355\u3002',
        ],
    ),
    (
        'r079-chronicle',
        'children: "\u6c5f\u6e56\u5fd7" })',
        '\u6c5f\u6e56\u5fd7',
        [
            '\u2460 \u8bb0\u5f55\u5168\u670d\u4fee\u58eb\u5927\u4e8b\uff08\u7a81\u7834\u3001\u98de\u5347\u3001\u5947\u9047\u7b49\uff09\uff0c\u6bcf\u9875 50 \u6761\u3001\u65b0\u4e8b\u4ef6\u5728\u524d\uff0c\u516c\u5f00\u53ef\u8bfb\u3002',
            '\u2461 \u4f20\u9605\uff1a\u6bcf\u6761\u53ef\u300c\u4f20\u9605\u300d\u4e00\u6b21\uff0c\u6bcf\u4eba\u6bcf\u6761\u9650\u4e00\u6b21\u3002',
            '\u2462 \u5956\u52b1\uff1a\u67d0\u6761\u4f20\u9605\u6570\u6070\u597d\u8fbe\u5230 10 \u65f6\uff0c\u8be5\u6761\u4e3b\u89d2\u5f97\u4e00\u6b21\u6027\u7075\u77f3\u5956\uff081000 \u00d7 1.5^\u5883\u754c\uff09\uff1b\u7cfb\u7edf\u516c\u544a\u6761\u76ee\u65e0\u5956\u52b1\u3002',
        ],
    ),
    (
        'r079-guide',
        'e.jsx(YlxwTitle, { children: "\u4ed9\u9014\u6307\u5f15" })',
        '\u4ed9\u9014\u6307\u5f15',
        [
            '\u2460 \u91cc\u7a0b\u7891\uff1a\u521b\u5efa\u89d2\u8272 500 / \u603b\u7b49\u7ea7 3 \u5f97 800 / \u603b\u7b49\u7ea7 9 \u5f97 1500 / \u603b\u7b49\u7ea7 10 \u5f97 2000 / \u52a0 1 \u4f4d\u597d\u53cb 800 / \u62dc\u5e08 1500 / \u603b\u7b49\u7ea7 19 \u5f97 5000 / \u7ed3\u9053\u4fa3 3000\uff0c\u8fbe\u6807\u540e\u624b\u52a8\u9886\u53d6\u3001\u5404\u4e00\u6b21\u6027\u3002',
            '\u2461 \u4e03\u65e5\u793c\uff1a\u4ee5\u9996\u6b21\u5b58\u6863\u65e5\u4e3a\u7b2c 1 \u5929\uff0c\u9010\u65e5\u53ef\u9886 500 / 800 / 1200 / 1800 / 2500 / 3500 / 5000 \u7075\u77f3\uff0c\u7b2c 7 \u5929\u53e6\u8d60\u79f0\u53f7\u300c\u4e03\u65e5\u7b51\u57fa\u300d\u3002',
        ],
    ),
    (
        'r079-tower',
        'children: "\u4e5d\u5929\u901a\u5929\u5854" })',
        '\u4e5d\u5929\u901a\u5929\u5854',
        [
            '\u2460 \u5171 100 \u5c42\uff0c\u9010\u5c42\u6311\u6218\u5b88\u5173\u8005\uff1b\u5f53\u524d\u6c14\u8840 \u2264 50 \u65f6\u65e0\u6cd5\u6311\u6218\uff08\u5148\u7597\u4f24\u6216\u6253\u5750\uff09\u3002',
            '\u2461 \u6bcf 10 \u5c42\u4e3a\u9547\u5854\u9053\u5c0a\uff08Boss\uff0c\u5c5e\u6027 \u00d71.4\uff09\uff1b\u6bcf 25 \u5c42\u91cc\u7a0b\u7891\u989d\u5916\u6389\u843d\u592a\u865a\u609f\u9053\u5377\u3002',
            '\u2462 \u9996\u901a\u5956\u52b1\uff1a\u4fee\u4e3a\u3001\u7075\u77f3\u3001\u592a\u865a\u6d17\u70bc\u77f3\u3001\u592a\u865a\u609f\u9053\u5377\u4e0e\u79d8\u5b9d\uff1b\u7b2c 100 \u5c42\u901a\u5173\u5f97\u4ed9\u54c1\u6cd5\u5b9d\u300c\u4e5d\u5929\u901a\u5929\u4ee4\u300d\u3002',
            '\u2463 \u6bcf\u65e5\u53ef\u300c\u4e00\u952e\u626b\u8361\u300d\u4e00\u6b21\uff08\u9700\u5df2\u901a\u5173\u81f3\u5c11 1 \u5c42\uff09\uff0c\u76f4\u63a5\u7ed3\u7b97\u5df2\u901a\u5173\u5c42\u6536\u76ca\u3002',
        ],
    ),
    (
        'r079-petexp',
        'children: "\u7075\u517d\u8fdc\u5f81" })',
        '\u7075\u517d\u8fdc\u5f81',
        [
            '\u2460 \u524d\u63d0\uff1a\u987b\u5df2\u5f00\u8f9f\u6d1e\u5e9c\uff1b\u6bcf\u6b21\u6d3e\u9063\u6d88\u8017 20000 \u7075\u77f3\u3002',
            '\u2461 \u961f\u4f0d\u69fd\u4f4d\u968f\u6d1e\u5e9c\u7b49\u7ea7\uff1aLv.1~2 \u4e00\u961f\u3001Lv.3~5 \u4e24\u961f\u3001Lv.6~8 \u4e09\u961f\u3001Lv.9+ \u56db\u961f\u3002',
            '\u2462 \u4e09\u4e2a\u5730\u70b9\uff1a\u5341\u4e07\u5927\u5c71\u5916\u56f4\uff08\u7075\u517d Lv.1 \u00b7 30 \u5206\u949f\uff09\u3001\u4e1c\u6d77\u6f5c\u9f99\u6df1\u6e0a\uff08Lv.15 \u00b7 2 \u5c0f\u65f6\uff09\u3001\u592a\u865a\u9668\u661f\u7981\u5730\uff08Lv.30 \u00b7 4 \u5c0f\u65f6\uff09\uff1b\u8d8a\u4e45\u6389\u843d\u8d8a\u597d\u3002',
            '\u2463 \u5f52\u6765\u70b9\u300c\u9886\u53d6\u6218\u679c\u300d\u5f97\u7075\u77f3/\u4fee\u4e3a/\u7269\u54c1\uff1b\u672a\u7ed3\u675f\u53ef\u300c\u53ec\u56de\u300d\u4e2d\u6b62\u3002',
        ],
    ),
    (
        'r079-payout',
        'e.jsx(YlxwTitle, { children: "\u4ea4\u6613\u884c\u8d27\u6b3e\uff08\u5f85\u9886\u6536\u76ca\uff09" })',
        '\u4ea4\u6613\u884c\u8d27\u6b3e',
        [
            '\u2460 \u4f60\u5728\u4ea4\u6613\u884c\u6302\u552e\u7684\u7269\u54c1\u552e\u51fa\u540e\uff0c\u8d27\u6b3e\u5148\u6258\u7ba1\u5728\u6b64\uff0c\u4e0d\u4f1a\u81ea\u52a8\u5165\u8d26\u3002',
            '\u2461 \u70b9\u300c\u9886\u53d6\u300d\u628a\u5168\u90e8\u5f85\u9886\u8d27\u6b3e\u4e00\u6b21\u6027\u5165\u8d26\uff0c\u4e5f\u53ef\u300c\u5237\u65b0\u300d\u67e5\u770b\u6700\u65b0\u5f85\u9886\u3002',
            '\u2462 \u9886\u53d6\u53ea\u6309\u672c\u6b21\u589e\u91cf\u5165\u8d26\uff1b\u82e5\u521a\u6709\u672a\u540c\u6b65\u6536\u76ca\uff0c\u4e0d\u4f1a\u88ab\u91cd\u590d\u8ba1\u7b97\u6216\u62b9\u6389\u3002',
        ],
    ),
    (
        'r079-pet',
        'children: "\u5996\u7075" })',
        '\u5996\u7075',
        [
            '\u2460 \u8fdb\u98df\uff1a\u4e09\u6863\u7075\u98df\u63d0\u5347\u5582\u98df\u5ea6\u2014\u2014\u51e1\u54c1\u00b7\u9752\u8349\u9732 3000 \u7075\u77f3 / +30\uff0c\u7075\u54c1\u00b7\u7389\u9ad3\u7fb9 15000 / +150\uff0c\u4ed9\u54c1\u00b7\u4e5d\u8f6c\u7075\u4e39 60000 / +600\uff1b\u7b49\u7ea7 = \u5582\u98df\u5ea6 \u00f7 100\uff08\u4e0a\u9650 99 \u7ea7\uff09\uff0c\u5582\u98df\u5ea6\u5c01\u9876 9999\u3002',
            '\u2461 \u4e92\u52a8\uff1a\u9017\u5f04\uff08Lv.0\uff09/ \u68b3\u6bdb\uff08Lv.10\uff0c\u53e6 +20 \u5582\u98df\u5ea6\uff09/ \u591c\u8bdd\uff08Lv.30\uff0c\u53e6 +200 \u4fee\u4e3a\uff09\uff0c\u6bcf\u79cd\u6bcf\u65e5\u514d\u8d39 1 \u6b21\u3001\u5404 +5 \u7f81\u7eca\uff1b\u514d\u8d39\u6b21\u6570\u7528\u5b8c\u53ef\u82b1 20000 \u7075\u77f3\u4e70\u989d\u5ea6\uff0c\u6bcf\u65e5\u6700\u591a 2 \u6b21\u3002',
            '\u2462 \u57f9\u517b\uff1a\u70b9\u5316 30000 \u7075\u77f3/\u6b21\uff0c\u8d44\u8d28\u968f\u673a +1~3\uff08\u4e0a\u9650 100\uff09\uff1b\u79d8\u5f84\u6d3e\u9063 5000 \u7075\u77f3\u30014 \u5c0f\u65f6\uff0c\u5f52\u6765\u5582\u98df\u5ea6 +80\u3001\u7f81\u7eca +15\u3001\u4fee\u4e3a +800\uff08\u6bcf\u65e5\u4e00\u6b21\uff09\u3002',
            '\u2463 \u5996\u7075\u4e4b\u529b = \u54c1\u9636 \u00d7 \u7b49\u7ea7 \u00d7 \u7f81\u7eca \u00d7 \u8d44\u8d28\uff08\u7f81\u7eca\u4e0a\u9650 500\uff09\uff0c\u6309 6% \u6298\u7b97\u52a0\u6210\u4e3b\u4eba\u5c5e\u6027\uff1b\u6bcf\u5347 10 \u7ea7\u89e6\u53d1\u4e00\u6b21\u300c\u5996\u7075\u7cbe\u9b44\u300d\uff0c\u7f81\u7eca +20 \u5e76\u90ae\u4ef6\u9001 1000 \u7075\u77f3\u3002',
            '\u2464 \u6536\u517b 20000 \u7075\u77f3 / \u5f52\u4f4d 30000 \u7075\u77f3 / \u653e\u751f\u514d\u8d39\u3002',
        ],
    ),
]


# --------------------------------------------------------------------------- 主入口

def _call_js(title, lines):
    """生成 `YlxwR79Box("标题", ["行1","行2",...])`（自然中文，稍后整体 zh()）。"""
    body = ', '.join('"%s"' % ln for ln in lines)
    return 'YlxwR79Box("%s", [%s])' % (title, body)


def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r079 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 1) 通用折叠块（函数声明提升，位置无关）
    p.insert_before('r079-box', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 YlxwR79Box（通用玩法说明折叠块）')

    # 2) 逐面板：标题节点后追加说明块（锚点原样保留 ⇒ 计数不变）
    markers = []
    for pid, anchor_nat, title, lines in PANELS:
        a = zh(anchor_nat)
        call = zh(_call_js(title, lines))
        p.replace(pid, a, a + ', ' + call, expect=1,
                  note='标题下追加玩法说明块')
        markers.append(zh('YlxwR79Box("%s"' % title))

    # ------------------------------------------------------------- 门禁
    _SCOPE = ('/* ===== yl-R079:', 'function YlxwTRebirth() {')
    gates = [
        # ---- 注入块 ----
        ('R79·折叠块函数已注入',   'function YlxwR79Box(t, L) {', 1, '==', ''),
        ('R79·折叠容器 details',   'e.jsxs("details", {', 1, '==', '限域到本模块注入块', _SCOPE),
        ('R79·折叠标题 summary',   'e.jsx("summary", {', 1, '==', '限域到本模块注入块', _SCOPE),
        ('R79·说明块前缀',         zh('\u73a9\u6cd5\u8bf4\u660e\uff1a'), 1, '>=', ''),
        # ---- 各面板说明已挂 ----
        ('R79·渡劫台说明',   zh('YlxwR79Box("\u6e21\u52ab\u53f0"'), 1, '==', ''),
        ('R79·悬赏说明',     zh('YlxwR79Box("\u60ac\u8d4f"'), 1, '==', ''),
        ('R79·江湖志说明',   zh('YlxwR79Box("\u6c5f\u6e56\u5fd7"'), 1, '==', ''),
        ('R79·仙途指引说明', zh('YlxwR79Box("\u4ed9\u9014\u6307\u5f15"'), 1, '==', ''),
        ('R79·通天塔说明',   zh('YlxwR79Box("\u4e5d\u5929\u901a\u5929\u5854"'), 1, '==', ''),
        ('R79·灵兽远征说明', zh('YlxwR79Box("\u7075\u517d\u8fdc\u5f81"'), 1, '==', ''),
        ('R79·交易行货款说明', zh('YlxwR79Box("\u4ea4\u6613\u884c\u8d27\u6b3e"'), 1, '==', ''),
        ('R79·妖灵说明',     zh('YlxwR79Box("\u5996\u7075"'), 1, '==', ''),
        ('R79·说明块共 8 处',  'YlxwR79Box("', 8, '==', '定义 1 + 调用 8 = 9 次，此处数调用前缀'),
        # ---- 锚点保留（追加式替换不破坏标题节点）----
        ('R79·标题·渡劫台在',   zh('children: "\u6e21\u52ab\u53f0" })'), 1, '==', ''),
        ('R79·标题·悬赏在',     zh('e.jsx(YlxwTitle, { children: "\u60ac\u8d4f" })'), 1, '==', ''),
        ('R79·标题·江湖志在',   zh('children: "\u6c5f\u6e56\u5fd7" })'), 1, '==', ''),
        ('R79·标题·仙途指引在', zh('e.jsx(YlxwTitle, { children: "\u4ed9\u9014\u6307\u5f15" })'), 1, '==', ''),
        ('R79·标题·通天塔在',   zh('children: "\u4e5d\u5929\u901a\u5929\u5854" })'), 1, '==', ''),
        ('R79·标题·灵兽远征在', zh('children: "\u7075\u517d\u8fdc\u5f81" })'), 1, '==', ''),
        ('R79·标题·货款在',     zh('e.jsx(YlxwTitle, { children: "\u4ea4\u6613\u884c\u8d27\u6b3e\uff08\u5f85\u9886\u6536\u76ca\uff09" })'), 1, '==', ''),
        ('R79·标题·妖灵在',     zh('children: "\u5996\u7075" })'), 1, '==', ''),
        # ---- 基线保护 ----
        ('基线·渡劫台定义仍在', 'function YlxwTRebirth() {', 1, '==', ''),
        ('基线·悬赏定义仍在',   'function YlxwTBounty() {', 1, '==', ''),
        ('基线·江湖志定义仍在', 'function YlxwTChronicle() {', 1, '==', ''),
        ('基线·仙途指引定义仍在', 'function YlxwTGuide() {', 1, '==', ''),
        ('基线·通天塔定义仍在', 'function YlxwTTower() {', 1, '==', ''),
        ('基线·灵兽远征定义仍在', 'function YlxwTPetExp() {', 1, '==', ''),
        ('基线·货款定义仍在',   'function YlxwTPayout() {', 1, '==', ''),
        ('基线·妖灵定义仍在',   'function YlxwTPet() {', 1, '==', ''),
        ('基线·注入块内无 XHR',  'XMLHttpRequest', 0, '==', '', _SCOPE),
        ('基线·注入块内无 X-YL-', 'X-YL-', 0, '==', '', _SCOPE),
        ('基线·注入块内无 postMessage', 'postMessage', 0, '==', '', _SCOPE),
        ('基线·注入块内无 fetch', 'fetch(', 0, '==', '纯说明，无网络', _SCOPE),
    ]
    return gates
