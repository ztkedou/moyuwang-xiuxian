# -*- coding: utf-8 -*-
"""
yl_entry_ext.py — v28 客户端改造 T1：新玩法入口可发现性（用户反馈 #1 / #5）

用户原话
  #1 「AI 新增的游戏功能入口太靠下，第一次玩都不知道下面还有别的功能」
  #5 「新加的几个玩法入口在哪啊我不知道怎么进」

------------------------------------------------------------------ 侦察结论（实测）
线上 bundle：https://moyuwang.online/yl/assets/index-v27-20260928.js
（= build_v26n.build(BASE) 的产出，md5 9df2572b38bf5c10bc1b5d3e1b09825d，已核对一致）

A. 移动端（viewport 390x844）「功能菜单」抽屉
   容器 `.flex-1 overflow-y-auto p-2`：clientHeight=767 / scrollHeight=1996
   30 个入口，每个 58px 高、间距 8px（步进 66px）；首屏只能看到 #0~#10（约 11 个）
   5 个新玩法入口的位置（1-based 第 15~19 位）：
       #14 交易行货款 y=1009   （需下滑 248px）
       #15 自创神通   y=1075
       #16 万宝洗炼   y=1141
       #17 灵兽远征   y=1207
       #18 通天塔     y=1273   （需下滑 512px）
   → 结论：5 个新玩法全部在首屏之下，且列表里没有任何「新」标记/分组，玩家不可能发现。

B. 桌面端（viewport 1440x900）
   抽屉是 `md:hidden`（w=0/h=0，完全不渲染）；桌面用的是 header 里**另一份硬编码 JSX 导航**
   （`.hidden md:flex gap-1 flex-wrap`）。那份导航里 **根本没有这 5 个入口**。
   → 结论：桌面端玩家 100% 无法进入这 5 个新玩法，比「太靠下」更严重。

C. 预构建 CSS `index-ZuV-l8Gt.css` 是**固定资产**（线上/本地 md5 同为
   5a3cbb4feb479e085b36e3ade6f68e6c），Tailwind 不会为新注入的类名补规则，
   因此本模块只用**已确认存在规则**的类名（见 _test_entry.py 的 CLASS 校验）。

------------------------------------------------------------------ 改造（4 处）
1. 抽屉：把 5 个新玩法入口从列表尾部**摘除**，改到列表**最顶部**，并在其上方加
   「新玩法」分组标题（需要 4. 渲染器支持）。
2. 抽屉开关（☰）右上角加红色「新」角标 —— 关上抽屉也能看到「里面有新东西」。
3. 桌面 header 导航：在既有「仙途指引」按钮后插入分隔符 + 5 个金色高亮、带「新」角标的按钮
   （由注入块里的 YlxwNewNavButtons() 生成，与抽屉入口指向同一批 YlxwOpen(key)）。
4. 抽屉渲染器加一个 `q.group` 分支，用于渲染分组标题（不改任何既有分支）。

------------------------------------------------------------------ 锚点实测（在 build_v26n 补丁后的文本上 count()）
  '{icon:YlxwMk("guide"),label:"仙途指引",onClick:()=>YlxwOpen("guide"),color:"text-amber-300"},'   -> 1
  guide 锚 + 5 个已追加项 的整块                                                                    -> 1
  '{icon:sm,label:"属性",onClick:a,color:"text-mystic-gold"},'                                       -> 1
  'children:C.map((q,w)=>{const A=q.icon;return q.locked?'                                          -> 1
  'e.jsx(YlxwIc,{name:"guide",size:15}),e.jsx("span",{children:"仙途指引"})]}),'                     -> 1
  'md:hidden ... w-12 h-12 ... touch-manipulation'（抽屉开关按钮）                                   -> 1
  'function YlxwPanelModal(p) {'（主注入锚，与 YlxwOpen 同作用域）                                     -> 1

所有替换均为 expect=1，命中数不符立即中止、不落盘。
"""

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-v28 T1：新玩法入口可发现性（反馈 #1 / #5） ===== */
var YLXW_NEW_FEATURES = [
  { key: "tower",      icon: "tower",      label: "通天塔" },
  { key: "expedition", icon: "expedition", label: "灵兽远征" },
  { key: "reforge",    icon: "reforge",    label: "万宝洗炼" },
  { key: "spell",      icon: "spell",      label: "自创神通" },
  { key: "payout",     icon: "payout",     label: "交易行货款" }
];

/* 桌面端（md+）header 导航用的 5 个「新玩法」按钮：金色高亮 + 红色「新」角标。
   与移动端抽屉顶部「新玩法」分组里的入口指向同一批 YlxwOpen(key)。 */
function YlxwNewNavButtons() {
  return YLXW_NEW_FEATURES.map(function (f) {
    return e.jsxs("button", {
      key: "ylxw-new-" + f.key,
      onClick: function () { YlxwOpen(f.key); },
      title: "新玩法：" + f.label,
      className: "flex items-center gap-1.5 px-2 py-1.5 bg-amber-500/15 hover:bg-stone-700 rounded border border-amber-500 transition-colors text-xs justify-center whitespace-nowrap text-amber-200",
      children: [
        e.jsx(YlxwIc, { name: f.icon, size: 15 }),
        e.jsx("span", { children: f.label }),
        e.jsx("span", { className: "text-[10px] leading-none bg-red-500 text-white px-1 py-0.5 rounded-full font-bold", children: "新" })
      ]
    });
  });
}
'''

# --------------------------------------------------------------------------- 锚点常量

# 抽屉列表里既有的「仙途指引」入口（v26n 的 5 个新入口就是 append 在它之后）
GUIDE_ANCHOR = ('{icon:YlxwMk("guide"),label:"仙途指引",'
                'onClick:()=>YlxwOpen("guide"),color:"text-amber-300"},')

# v26n 追加的 5 项，在文本里的**实际顺序**是 payout/spell/reforge/expedition/tower
# （每次 append_to 都紧贴锚点插入，所以最后 append 的排最前）——实测 count == 1
APPENDED_TAIL = (
    '{icon:YlxwMk("payout"),label:"交易行货款",onClick:()=>YlxwOpen("payout"),color:"text-amber-300"},'
    '{icon:YlxwMk("spell"),label:"自创神通",onClick:()=>YlxwOpen("spell"),color:"text-amber-300"},'
    '{icon:YlxwMk("reforge"),label:"万宝洗炼",onClick:()=>YlxwOpen("reforge"),color:"text-amber-300"},'
    '{icon:YlxwMk("expedition"),label:"灵兽远征",onClick:()=>YlxwOpen("expedition"),color:"text-amber-300"},'
    '{icon:YlxwMk("tower"),label:"通天塔",onClick:()=>YlxwOpen("tower"),color:"text-amber-300"},'
)

# 抽屉列表的**首项**（列表字面量以它开头）——实测 count == 1
LIST_HEAD = '{icon:sm,label:"属性",onClick:a,color:"text-mystic-gold"},'

# 抽屉渲染器的分支开头——实测 count == 1
RENDER_OLD = 'children:C.map((q,w)=>{const A=q.icon;return q.locked?'
RENDER_NEW = ('children:C.map((q,w)=>{const A=q.icon;'
              'return q.group?e.jsx("div",{className:"px-3 pt-2 pb-1 text-[11px] '
              'font-bold tracking-widest text-amber-300",children:q.group},w):q.locked?')

# 桌面 header 导航里既有的「仙途指引」按钮尾部——实测 count == 1
DESK_GUIDE = 'e.jsx(YlxwIc,{name:"guide",size:15}),e.jsx("span",{children:"仙途指引"})]}),'

# 桌面导航既有的竖分隔符（原样复用，保证类名一定在 CSS 里）
DESK_SEP = 'e.jsx("span",{className:"w-px h-5 bg-stone-700 mx-0.5 shrink-0","aria-hidden":!0})'

# 抽屉开关按钮（☰）——实测 count == 1
TOGGLE_OLD = ('e.jsx("button",{onClick:r,className:"md:hidden flex items-center justify-center '
              'w-12 h-12 bg-ink-800 active:bg-stone-700 rounded border border-stone-600 '
              'touch-manipulation",children:e.jsx(f5,{size:24,className:"text-stone-200"})})')
TOGGLE_NEW = ('e.jsxs("button",{onClick:r,className:"md:hidden relative flex items-center '
              'justify-center w-12 h-12 bg-ink-800 active:bg-stone-700 rounded border '
              'border-stone-600 touch-manipulation",children:[e.jsx(f5,{size:24,'
              'className:"text-stone-200"}),e.jsx("span",{className:"absolute -top-1 -right-1 '
              'bg-red-500 text-white text-[10px] leading-none px-1 py-0.5 rounded-full '
              'font-bold",children:"新"})]})')

# 主注入锚：与 YlxwOpen / YLXW_ICONS / xt 等同作用域
MAIN_ANCHOR = 'function YlxwPanelModal(p) {'

# --------------------------------------------------------------------------- 新增的抽屉分组

GROUP_HEADER = ('{group:"新玩法 · 全新开放",icon:YlxwMk("dot"),'
                'color:"text-amber-300",label:"新玩法"},')


def _entry(icon, label, key):
    """置顶分组里的单条入口（金色 + 红色「新」角标）。"""
    return ('{icon:YlxwMk("%s"),label:"%s",onClick:()=>YlxwOpen("%s"),'
            'color:"text-amber-300",badge:"新"},' % (icon, label, key))


# 展示顺序：与 YLXW_NEW_FEATURES 一致
NEW_ENTRIES = [
    _entry('tower', '通天塔', 'tower'),
    _entry('expedition', '灵兽远征', 'expedition'),
    _entry('reforge', '万宝洗炼', 'reforge'),
    _entry('spell', '自创神通', 'spell'),
    _entry('payout', '交易行货款', 'payout'),
]
NEW_GROUP = GROUP_HEADER + ''.join(NEW_ENTRIES)

BAN_PATTERNS = ['fetch(', 'localStorage', 'sessionStorage', 'auth_token',
                '/yl/api', 'iframe', 'postMessage', 'X-YL-', 'XMLHttpRequest']


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含改名 + v26n 全部补丁）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 0) 注入 helper 块（与 YlxwOpen 同作用域，供桌面导航复用）
    p.insert_before(
        't1-entry-helper',
        MAIN_ANCHOR,
        zh(INJECT_JS) + '\n',
        note='注入 YLXW_NEW_FEATURES + YlxwNewNavButtons（新玩法入口单一数据源）'
    )

    # 1) 抽屉：把 v26n 追加在「仙途指引」之后的 5 项整块摘掉（锚点本身保留）
    p.replace(
        't1-drawer-untail',
        GUIDE_ANCHOR + APPENDED_TAIL,
        GUIDE_ANCHOR,
        expect=1,
        note='摘除列表尾部的 5 个新玩法入口（count(%r) 实测 1）' % (GUIDE_ANCHOR + APPENDED_TAIL)[:40]
    )

    # 2) 抽屉：把「新玩法」分组（标题 + 5 个入口）置顶到列表最前面
    p.replace(
        't1-drawer-topgroup',
        LIST_HEAD,
        zh(NEW_GROUP) + LIST_HEAD,
        expect=1,
        note='在列表首项「属性」之前插入新玩法分组（count(%r) 实测 1）' % LIST_HEAD
    )

    # 3) 抽屉渲染器：加 q.group 分支（既有 q.locked / 普通按钮分支原样保留）
    p.replace(
        't1-drawer-render',
        RENDER_OLD,
        RENDER_NEW,
        expect=1,
        note='抽屉渲染器支持分组标题（count 实测 1）'
    )

    # 4) 桌面 header 导航：既有「仙途指引」按钮之后插入 分隔符 + 5 个新玩法按钮
    #    注意：DESK_GUIDE 结尾已带一个数组元素分隔逗号，所以分隔符之后要再补一个逗号，
    #    否则会变成 `e.jsx(...)...YlxwNewNavButtons()`（实测就是「Unexpected token '...'」）。
    p.insert_after(
        't1-desktop-nav',
        DESK_GUIDE,
        DESK_SEP + ',...YlxwNewNavButtons(),',
        note='桌面导航补 5 个新玩法入口（原导航完全没有它们；count 实测 1）'
    )

    # 5) 抽屉开关（☰）加红色「新」角标：关上抽屉也能看到「里面有新东西」
    p.replace(
        't1-drawer-toggle',
        TOGGLE_OLD,
        zh(TOGGLE_NEW),
        expect=1,
        note='抽屉开关加「新」角标（count 实测 1）'
    )

    # ------------------------------------------------------------- 门禁
    gates = [
        # --- 注入块 ---
        ('T1·helper 定义',            'function YlxwNewNavButtons()',              1, '==', ''),
        ('T1·新玩法数据表',           'var YLXW_NEW_FEATURES',                     1, '==', ''),
        ('T1·桌面导航已展开',         '...YlxwNewNavButtons(),',                   1, '==', ''),
        ('T1·桌面导航分隔符',         DESK_SEP,                                    2, '>=', '原有 1 处 + 新增 1 处'),
        # --- 抽屉 ---
        ('T1·渲染器支持分组',         'return q.group?e.jsx("div"',                1, '==', ''),
        ('T1·分组标题条目',           zh(GROUP_HEADER),                            1, '==', ''),
        ('T1·列表首项仍为「属性」',    LIST_HEAD,                                   1, '==', ''),
        ('T1·尾部旧入口已摘除',       GUIDE_ANCHOR + APPENDED_TAIL,                0, '==', '必须为 0'),
        ('T1·开关红点已加',           zh('absolute -top-1 -right-1 bg-red-500'),   1, '==', ''),
        # --- 5 个新玩法入口（置顶分组里各 1 条；YlxwOpen(key) 字面量各保留 1 次）---
        ('T1·置顶入口 tower',         zh(NEW_ENTRIES[0]),                          1, '==', ''),
        ('T1·置顶入口 expedition',    zh(NEW_ENTRIES[1]),                          1, '==', ''),
        ('T1·置顶入口 reforge',       zh(NEW_ENTRIES[2]),                          1, '==', ''),
        ('T1·置顶入口 spell',         zh(NEW_ENTRIES[3]),                          1, '==', ''),
        ('T1·置顶入口 payout',        zh(NEW_ENTRIES[4]),                          1, '==', ''),
        ('T1·YlxwOpen("tower")',      'YlxwOpen("tower")',                         1, '==', ''),
        ('T1·YlxwOpen("expedition")', 'YlxwOpen("expedition")',                    1, '==', ''),
        ('T1·YlxwOpen("reforge")',    'YlxwOpen("reforge")',                       1, '==', ''),
        ('T1·YlxwOpen("spell")',      'YlxwOpen("spell")',                         1, '==', ''),
        ('T1·YlxwOpen("payout")',     'YlxwOpen("payout")',                        1, '==', ''),
        # --- 基线完整性（不碰别人的地盘）---
        ('基线·guide 抽屉入口仍在',    GUIDE_ANCHOR,                                1, '==', ''),
        ('基线·guide 桌面按钮仍在',    DESK_GUIDE,                                  1, '==', ''),
        ('基线·抽屉开关仍在',         'md:hidden relative flex items-center justify-center w-12 h-12', 1, '==', ''),
        ('基线·YLXW_TABS 原项仍在',   '{ key: "mail", label:',                     1, '==', ''),
        ('基线·YlxwPanelModal 未破坏', 'function YlxwPanelModal(p) {',              1, '==', ''),
        ('基线·xt 未破坏',            'const xt=t=>{',                              1, '==', ''),
        ('基线·pushSave 原样',        'body:JSON.stringify({player:',               1, '==', ''),
    ]
    return gates
