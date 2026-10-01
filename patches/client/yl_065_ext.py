# -*- coding: utf-8 -*-
r"""
yl_065_ext.py — R-065 宗门：已有独立「仙盟」按钮，宗门页只做宗门内容

需求（台账 R-065，无附图）
--------------------------------------------------------------------------
  「宗门这个既然有单独的"仙盟"按钮，宗门这个就专门只做宗门的内容。」

现状（bundle index-v28117-20261001.js 实测，本会话侦察）
--------------------------------------------------------------------------
  「宗门」弹窗（原生 lM 组件，SKILL §6.3：宗门列表是客户端本地伪造的）的
  **未入宗分支**带了一个仙务融合标记：

      if(!a.sectId)return e.jsx(ct,{xw:"sect",isOpen:t,onClose:r,title:"寻访仙门",...

  外壳 wN/ct 的内容区（fun086 F6 两列网格）据此渲染左列「仙务·仙盟」融合块：

      children:__xw?e.jsxs("div",{...grid...,children:[e.jsx("div",{...,children:e.jsx(YlxwFuse,{k:__xw})}),e.jsx("div",{...,children:l})]}):l}
      容器宽度：${__xw?"md:max-w-6xl":jN[c]}

  ⇒ 未入宗玩家打开「宗门」时，看到的是「仙务·仙盟」块 + 宗门列表挤在一页 ——
     这就是用户说的「宗门页混了仙盟内容」。
  已入宗分支本来就不带 xw（SKILL §6.2），不受影响。

  而「仙盟」早有**独立入口**（yl_ui_ext.py T2 / P1-⑥ 于 0.8.2 加的，实测在位）：
    · 桌面顶栏按钮   e.jsxs("button",{onClick:()=>YlxwOpen("sect")       （唯一）
    · ☰ 抽屉菜单项   {icon:YlxwMk("sect"),label:"仙盟",onClick:...        （唯一）
  两处都调 YlxwOpen("sect") → setModal("xianwuTab","sect") 打开仙务枢纽的
  独立仙盟面板（0.8.7 T7 重构版 `YLXW_COMP.sect = YlxwTSectT7`，含 in/noSectView）。

本模块动作（最小 diff，仅 1 处替换）
--------------------------------------------------------------------------
  e.jsx(ct,{xw:"sect",isOpen:t   →   e.jsx(ct,{isOpen:t

  即把 xw:"sect" 融合标记从未入宗分支摘掉。效果：
    · __xw 为 undefined → 内容区走 `:l}` 直传分支（fun086 门禁「非融合页直传 l」），
      容器宽度回到 jN[c]（size:"4xl" 档）⇒ 宗门弹窗恢复纯宗门列表，不再渲染仙盟块；
    · YlxwFuse({k:"sect"}) 失去唯一渲染途径 ⇒ 宗门页 0 仙盟内容；
    · 仙盟功能不受损：2 处独立按钮 + 仙务枢纽 T7 面板原样可达。

  先例：0.8.8 item18 丹房同型操作（yl_fun086_ext F7 摘 xw:"alchemy"，
  flow083 门禁 1→0）——本模块是对 sect 键的同型处置。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 不碰 2 处 YlxwOpen("sect") 独立入口、YLXW_COMP.sect=T7 面板、Fuse 渲染链、
    外壳 memo、其余 7 个融合键（gongfa/dungeon/ach/pet/farm/rebirth/titles+stats/alchemy）
    —— 门禁逐条冻结。
  · ★ 已知耦合（需 lead 接线时处置，SKILL §22.5 惯例）：yl_flow083_ext.py:303
    `('F7·sect 融合', 'xw:"sect"', 1, '==', '')` 断言的是「中间形态字面串」，
    被本模块合法改写打破 ⇒ 装配前须按同文件 301 行 alchemy 先例把 1 改 0
    （本模块第 1 条门禁已按最终语义断言 ==0）。
  · 纯就地替换：INJECT_JS 为空，无注入块（无 BAN_PATTERNS / zh() 面）。
  · 锚点唯一性均在本会话对 index-v28117-20261001.js 实测（count 见门禁）。
  · 只新建本文件；不改 build_v26n.py / yl_flow083_ext.py / 产物 / 服务端。
"""

# --------------------------------------------------------------------------- 锚点

# 旧形态：未入宗分支的宗门模态带仙务融合标记（bundle 实测唯一，count=1）
ANCHOR_OLD = 'e.jsx(ct,{xw:"sect",isOpen:t'

# 新形态：摘除融合标记，宗门模态直连纯外壳（摘除后唯一，count=1）
ANCHOR_NEW = 'e.jsx(ct,{isOpen:t'

# 需求语义锚：新形态的完整可判定串（含中文原文「寻访仙门」；bundle 中此处为 UTF-8 原文）
R65_NEW_SECT_MODAL = 'e.jsx(ct,{isOpen:t,onClose:r,title:"\u5bfb\u8bbf\u4ed9\u95e8"'

# 冻结·独立仙盟入口（yl_ui_ext T2 产物，唯一）
UI_SECT_DESK = 'e.jsxs("button",{onClick:()=>YlxwOpen("sect")'
UI_SECT_DRAWER = '{icon:YlxwMk("sect"),label:'

# 冻结·独立仙盟面板（0.8.7 T7 重构注册，唯一）
T7_SECT_COMP = 'YLXW_COMP.sect = YlxwTSectT7'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    p.replace('r065-sect-fuse-off', ANCHOR_OLD, ANCHOR_NEW, expect=1,
              note='R-065：宗门弹窗摘除 xw:"sect" 融合标记，宗门页只做宗门内容')

    gates = [
        # ================= 本模块改动 =================
        ('R65·sect 融合键已摘除',       'xw:"sect"',                 0, '==', '宗门页只做宗门内容；仙盟走独立按钮'),
        ('R65·旧带 xw 调用点清零',      ANCHOR_OLD,                  0, '==', '替换后旧形态不存在'),
        ('R65·寻访仙门直连纯外壳',      R65_NEW_SECT_MODAL,          1, '==', '未入宗分支新形态唯一（bundle 中文为 UTF-8 原文）'),
        # ================= 冻结：仙盟独立入口不因摘融合而受损 =================
        ('冻结·桌面仙盟按钮仍在',       UI_SECT_DESK,                1, '==', 'yl_ui_ext T2 桌面入口未动'),
        ('冻结·抽屉仙盟项仍在',         UI_SECT_DRAWER,              1, '==', 'yl_ui_ext T2 抽屉入口未动'),
        ('冻结·YlxwOpen("sect") 恒2处', 'YlxwOpen("sect")',          2, '==', '与 yl_ui_ext 门禁同值：入口数不变'),
        ('冻结·仙盟 T7 面板注册',       T7_SECT_COMP,                1, '==', '0.8.7 独立仙盟面板不受影响'),
        # ================= 冻结：融合机制本体与其余融合键一字不动 =================
        ('冻结·Fuse 渲染点唯一',        'e.jsx(YlxwFuse,{k:__xw})',  1, '==', '与 flow083 F7 同值；渲染链未动'),
        ('冻结·外壳 memo 未动',         'ct=O.memo(wN)',             1, '==', '与 flow083 F7 同值'),
        ('冻结·gongfa 融合',            'xw:"gongfa"',               1, '==', '功法阁融合（R-066 相邻面，勿碰）'),
        ('冻结·dungeon 融合',           'xw:"dungeon"',              1, '==', ''),
        ('冻结·ach 融合',               'xw:"ach"',                  1, '==', ''),
        ('冻结·pet 融合',               'xw:"pet"',                  1, '==', ''),
        ('冻结·farm 融合',              'xw:"farm"',                 1, '==', ''),
        ('冻结·rebirth 融合',           'xw:"rebirth"',              1, '==', ''),
        ('冻结·titles+stats 融合',      'xw:["titles","stats"]',     1, '==', '角色系统融合页'),
        ('冻结·alchemy 由 L4 渲染',     'e.jsx(YlxwFuse,{k:"alchemy"})', 1, '==', 'fun086 item18 形态未动'),
    ]
    return gates
