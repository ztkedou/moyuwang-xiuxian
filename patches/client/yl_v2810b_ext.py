# -*- coding: utf-8 -*-
r"""
yl_v2810b_ext.py — 0.8.10 批次 · 「悟道」并入「功法」（客户端 · 去独立入口 + 左栏下方追加区块）

=========================================================================== 任务口径
用户原话：
  「把『**悟道**』加到『**功法**』里，**悟道按钮去掉**，内容放到左栏『仙务·心法』**下方**；
    玩法提示：**打坐/历练中随机触发悟道经验提升**，也可花灵石『顿悟』」

服务端侧（不在本模块范围）：`GET /api/wudao`、`POST /api/wudao/insight` 已存在（扣 500 灵石
→ +100 悟道经验）；挂机触发 `tickWudaoIdle` 目前只认打坐（meditate），历练（adventure）
那半由另一成员在服务端补。**本模块只做客户端装配，不新增/不改任何端点。**

=========================================================================== 侦察结论（基座 index-v26m-20260927.js 逐字实证）
「悟道」在客户端共 **3 处独立入口**（`YlxwOpen("wudao")` 2 处 + 仙务枢页签 1 处）：

  ① 桌面顶栏按钮（基座 @736539，含 `YlxwOpen("wudao")` 之一）
       e.jsxs("button",{onClick:()=>YlxwOpen("wudao"),className:"flex items-center gap-1.5
       px-2 py-1.5 bg-ink-800 …",children:[e.jsx(YlxwIc,{name:"wudao",size:15}),
       e.jsx("span",{children:"悟道"})]}),
     该 className 与「角色 / 灵宠 / 仙友录 / 仙盟 / 挂机收益」等顶栏按钮**逐字同形**，
     故锚点必须带上 `onClick:()=>YlxwOpen("wudao")` 才能唯一（实测 count==1）。

  ② 移动抽屉快捷项（基座 @751249，含 `YlxwOpen("wudao")` 之二）
       {icon:YlxwMk("wudao"),label:"悟道",onClick:()=>YlxwOpen("wudao"),color:"text-amber-300"},

  ③ 仙务枢左栏页签（基座 @792168，YLXW_TABS 的「修行」组）
       { key: "wudao", label: "\u609f\u9053", group: 1 },
     ★ 该行落在 build_v26n 注入的 `var YLXW_TABS = […]` 块内，中文是 **\uXXXX 形态**
       （其余两处是基座原文，中文为 **raw 中文**）—— 锚点写法必须分别对应，写反即恒 0。

`YlxwTWudao` 出现 2 次：① 组件定义（基座 @803776）；② `var YLXW_COMP = {… wudao: YlxwTWudao,
gongfa: YlxwTGongfa, …}` 字面量（基座 @830492）。**组件本体与其注册字面量均不删**
（用户只要求「按钮去掉」，组件要挪进功法面板复用）。

「心法」面板现状：基座 `YlxwTGongfa`（标题「心法六卷」）已被 0.8.7 的
`yl_xinfa087_ext.py` **覆盖注册**为 `YLXW_COMP.gongfa = YlxwTXinfa087;`（其注入块收尾行，
落在 `function YlxwPanelModal(p) {` 之前）。本模块装配序在其之后，锚点即取该收尾行。

=========================================================================== 改法（侵入最小，零锚点冲突）
· **删入口**：三处入口各自整段替换为空串（连同尾随逗号），不触碰相邻元素。
· **并入功法**：**不重写** xinfa087 的心法面板（避免与其注入块互相覆盖），改为
  `insert_after` 落在 `YLXW_COMP.gongfa = YlxwTXinfa087;` 之后，用**包装注册**模式
  （与 xinfa087 / t7sect / t8mentor 同款）把 `YLXW_COMP.gongfa` 指向组合组件
  `YlxwTGongfaWudao` = 「原心法面板 + `e.jsx(YlxwTWudao, {})` + 玩法提示行」。
  `YlxwPanel` 是 `div.space-y-2`，Fragment 直接子节点天然纵向堆叠 ⇒ 悟道区块正好落在
  心法区块**下方**，间距 0.5rem，无需新增 CSS。
· **玩法提示**：新增 `YlxwWudaoHint`（`YlxwRow` 内两行小字），文案对应用户原话。

=========================================================================== 与前后模块的边界（装配序核对）
· 前序 xinfa087：锚点行 `YLXW_COMP.gongfa = YlxwTXinfa087;` 原样保留（insert_after 不破坏）。
· 后序 numbal：其锚点是 `function YlxwPanelModal(p) {`（insert_before）。本模块插在该行**之前**、
  numbal 之前，numbal 的锚点计数不受影响（实测仍 1）。
· 全链 grep 确认：除 xinfa087 外，**无任何模块**读写 `YLXW_COMP.gongfa` / `wudao` 入口，
  亦无模块锚点跨越本模块删除的三段文本（ui_ext 的顶栏/抽屉锚点均为 friends/sect/offline/guide）。

=========================================================================== 门禁计数清单（给接线人）
  ① 三处入口锚点                                       基线 1 → 改后 0
  ② 'YlxwOpen("wudao")'                                基线 2 → 改后 0
  ③ 三处「拼接无缝」串（删完必须与邻项严丝合缝）           基线 0 → 改后 1
  ④ 'function YlxwTWudao() {'                          恒 1（组件本体禁删，复用）
  ⑤ 'e.jsx(YlxwTWudao, {})'                            基线 0 → 改后 1
  ⑥ 'YLXW_COMP.gongfa = YlxwTGongfaWudao;'             基线 0 → 改后 1
  ⑦ 'YLXW_COMP.gongfa = YlxwTXinfa087;'                恒 1（xinfa087 注册行保留）
  ⑧ 'function YlxwTXinfa087('                          恒 1（心法面板未被重写）
  ⑨ 玩法提示两行（zh 转义形态）                          基线 0 → 改后 1
  ⑩ 'gongfa: YlxwTGongfa'                              恒 1（基座旧注册字面量零改动）

=========================================================================== 技术约束遵守
· 注入块经 zh() 后无非 ASCII；不含 V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/
  auth_token/X-YL-）。不用 require。不写 build/assets/，不改 build_v26n.py。
· 注入点唯一（expect=1）；apply() 返回门禁五元组列表；本文件不写任何产物。
"""

# --------------------------------------------------------------------------- 注入块（纯 ASCII 载体，中文由 build 侧 zh() 转义）

INJECT_JS = r'''
/* ===== yl-0.8.10 v2810b: 「悟道」并入「功法」 =====
   独立入口三处已删（桌面顶栏按钮 / 移动抽屉快捷项 / 仙务枢左栏页签）。
   组件本体 YlxwTWudao 保留并复用：包装注册 YLXW_COMP.gongfa，
   在原「心法」面板下方追加「悟道」区块与玩法提示。
   数据来源不变：GET /wudao（等级/经验/顿悟价）、POST /wudao/insight（花灵石顿悟）。 */
var YlxwGongfaWudaoBase = YLXW_COMP.gongfa;

function YlxwWudaoHint() {
  return e.jsx(YlxwRow, { children: e.jsxs("div", { className: "text-[11px] text-stone-400 leading-5", children: [
    e.jsx("div", { children: "玩法提示：打坐 / 历练中会随机触发悟道经验提升。" }),
    e.jsx("div", { children: "也可花灵石顿悟（消耗以面板标价为准），顿悟后立即提升悟道修为。" })
  ] }) });
}

function YlxwTGongfaWudao(p) {
  return e.jsxs(e.Fragment, { children: [
    e.jsx(YlxwGongfaWudaoBase, p),
    e.jsx(YlxwTWudao, {}),
    e.jsx(YlxwWudaoHint, {})
  ] });
}
YLXW_COMP.gongfa = YlxwTGongfaWudao;
'''

# --------------------------------------------------------------------------- 锚点常量
#
# ★ 转义纪律：③ 号锚点落在 build_v26n 注入的 YLXW_TABS 块内 ⇒ 中文是 \uXXXX 形态；
#   ① ② 号锚点是基座原文 ⇒ 中文是 raw 中文。两者不可互换。

# ① 桌面顶栏「悟道」按钮（整段 + 尾随逗号）
_TOPBAR_WUDAO = (
    'e.jsxs("button",{onClick:()=>YlxwOpen("wudao"),'
    'className:"flex items-center gap-1.5 px-2 py-1.5 bg-ink-800 hover:bg-stone-700 '
    'rounded border border-stone-600 transition-colors text-xs min-w-[34px] min-h-[32px] '
    'justify-center whitespace-nowrap",children:[e.jsx(YlxwIc,{name:"wudao",size:15}),'
    'e.jsx("span",{children:"悟道"})]}),'
)

# ② 移动抽屉「悟道」快捷项（整段 + 尾随逗号）
_QUICK_WUDAO = (
    '{icon:YlxwMk("wudao"),label:"悟道",onClick:()=>YlxwOpen("wudao"),'
    'color:"text-amber-300"},'
)

# ③ 仙务枢左栏「修行」组页签（整行 + 换行；label 为 \uXXXX 形态）
_TAB_WUDAO = '  { key: "wudao", label: "\\u609f\\u9053", group: 1 },\n'

# —— 拼接无缝断言（只可能在「删干净且与邻项相邻」时成立）——
_TOPBAR_JOIN = (
    'children:Ts(Rs.PET,t.realm)&&A>0?A:void 0})]}),'
    'e.jsxs(Q,{locked:!Ts(Rs.GROTTO,t.realm),requirement:Dn(),onClick:j,'
    'children:[e.jsx(zr,{size:15})'
)
#   抽屉列表里「悟道」项的前后邻项实测为 活动中心(events) / 仙盟(sect)（events 的 label
#   已被 act087 由「限时活动」改名为「活动中心」；sect 项由 ui_ext 注入、中文为 \uXXXX 形态）。
_QUICK_JOIN = (
    'label:"活动中心",onClick:()=>YlxwOpen("events"),color:"text-amber-300"},'
    '{icon:YlxwMk("sect"),'
)
#   页签表里「悟道」项的前后邻项实测为 活动中心(events) / 心法(gongfa)（同为 \uXXXX 形态）。
_TAB_JOIN = (
    '  { key: "events", label: "\\u6d3b\\u52a8\\u4e2d\\u5fc3", group: 0 },\n'
    '  { key: "gongfa", label: "\\u5fc3\\u6cd5", group: 1 },'
)

# —— 邻项零误删断言 ——
_FRIENDS_DESK_BTN = 'e.jsxs("button",{onClick:()=>YlxwOpen("friends"),'
_FRIENDS_DRAWER = (
    '{icon:YlxwMk("friends"),label:"仙友录",onClick:()=>YlxwOpen("friends"),'
    'color:"text-amber-300"},'
)
_TAB_GONGFA = '  { key: "gongfa", label: "\\u5fc3\\u6cd5", group: 1 },'
_ICON_WUDAO = 'wudao: "M12 21a9 9 0 1 0 0-18'

# —— 注入锚：xinfa087 覆盖注册的收尾行（本模块 insert_after 其后）——
_ANCHOR_XINFA_REG = 'YLXW_COMP.gongfa = YlxwTXinfa087;'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 xinfa087）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 0) 玩法提示两行（zh 转义形态；门禁 needle 必须用同一形态，否则恒 0 假 FAIL）
    hint_l1 = zh('玩法提示：打坐 / 历练中会随机触发悟道经验提升。')
    hint_l2 = zh('也可花灵石顿悟（消耗以面板标价为准），顿悟后立即提升悟道修为。')

    # 1) 删三处独立入口（各自整段替换为空串，含尾随逗号）
    p.replace('v2810b-del-topbar', _TOPBAR_WUDAO, '', expect=1,
              note='删桌面顶栏「悟道」按钮（独立入口 ①）')
    p.replace('v2810b-del-quick', _QUICK_WUDAO, '', expect=1,
              note='删移动抽屉「悟道」快捷项（独立入口 ②）')
    p.replace('v2810b-del-tab', _TAB_WUDAO, '', expect=1,
              note='删仙务枢左栏「悟道」页签（独立入口 ③）')

    # 2) 在 xinfa087 覆盖注册行之后注入包装块（组合心法面板 + 悟道区块 + 玩法提示）
    p.insert_after('v2810b-block', _ANCHOR_XINFA_REG, '\n' + zh(INJECT_JS) + '\n',
                   expect=1, note='包装 YLXW_COMP.gongfa = 心法面板 + 悟道区块 + 玩法提示')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- 独立入口三处已删（本模块唯一破坏性改动）----
        ('V2810B·顶栏悟道按钮已删',     _TOPBAR_WUDAO,  0, '==', '独立入口 ①（含 YlxwOpen("wudao") 之一）'),
        ('V2810B·抽屉快捷项已删',       _QUICK_WUDAO,   0, '==', '独立入口 ②（含 YlxwOpen("wudao") 之二）'),
        ('V2810B·仙务枢悟道页签已删',   _TAB_WUDAO,     0, '==', '独立入口 ③（YLXW_TABS 修行组）'),
        ('V2810B·YlxwOpen("wudao") 归零', 'YlxwOpen("wudao")', 0, '==', '三处独立入口全清'),

        # ---- 删除后与邻项严丝合缝（语法零破坏）----
        ('V2810B·顶栏拼接无缝',         _TOPBAR_JOIN,   1, '==', '灵宠按钮 → 秘境按钮 直接相邻'),
        ('V2810B·抽屉拼接无缝',         _QUICK_JOIN,    1, '==', '限时活动 → 仙友录 直接相邻'),
        ('V2810B·页签拼接无缝',         _TAB_JOIN,      1, '==', '限时活动 → 心法 直接相邻'),

        # ---- 悟道组件本体保留并复用（禁删）----
        ('V2810B·悟道组件本体保留',     'function YlxwTWudao() {',                1, '==', '用户只要求去按钮，组件要挪进功法面板'),
        ('V2810B·悟道注册字面量保留',   'wudao: YlxwTWudao',                      1, '==', 'YLXW_COMP 字面量零改动'),
        ('V2810B·复用悟道组件渲染',     'e.jsx(YlxwTWudao, {})',                  1, '==', '直接复用，不复制其 JSX'),

        # ---- 心法面板零重写 + 包装注册 ----
        ('V2810B·心法面板函数保留',     'function YlxwTXinfa087(',                1, '==', 'xinfa087 产物原样'),
        ('V2810B·心法注册行保留',       _ANCHOR_XINFA_REG,                        1, '==', 'insert_after 不破坏该行'),
        ('V2810B·功法面板包装注册',     'YLXW_COMP.gongfa = YlxwTGongfaWudao;',   1, '==', '心法面板 + 悟道区块 + 提示'),
        ('V2810B·基座心法注册未动',     'gongfa: YlxwTGongfa',                    1, '==', '基座旧注册字面量零改动'),

        # ---- 玩法提示（zh 转义形态）----
        ('V2810B·提示·打坐历练随机悟道', hint_l1,                                  1, '==', 'zh() 形态 needle'),
        ('V2810B·提示·花灵石顿悟',       hint_l2,                                  1, '==', 'zh() 形态 needle'),
        ('V2810B·提示块已挂载',         'e.jsx(YlxwWudaoHint, {})',               1, '==', ''),

        # ---- 相邻入口零误删 ----
        ('V2810B·顶栏仙友录入口仍在',   _FRIENDS_DESK_BTN,                        1, '==', '仅删悟道，邻项不动'),
        ('V2810B·抽屉仙友录入口仍在',   _FRIENDS_DRAWER,                          1, '==', '仅删悟道，邻项不动'),
        ('V2810B·页签心法项仍在',       _TAB_GONGFA,                              1, '==', '仅删悟道，邻项不动'),
        ('V2810B·悟道图标资源保留',     _ICON_WUDAO,                              1, '==', 'YLXW_ICONS 不动（无入口后成闲置资源，无害）'),
    ]
    return gates
