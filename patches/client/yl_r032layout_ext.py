# -*- coding: utf-8 -*-
r"""
yl_r032layout_ext.py — R-032③「秘境弹窗右侧内容被压缩」客户端单模块（纯布局，1 处替换）

需求原文（用户）
--------------------------------------------------------------------------
  「秘境探索改为冷却制度，每日上限 20 次。随着等阶提升次数。
    顺便把右侧面板被压缩了修复一下。」

★ 成因（真机实测，非推测）
--------------------------------------------------------------------------
  · 秘境探索弹窗组件 `cM`（`cM=({isOpen:t,onClose:r,player:a,onEnter:l})=>…`）把
    `xw:"dungeon"` 传给模态壳 `wN`（导出名 `ct`）。而 `wN` 对**任何**带 `xw` 的弹窗
    都会把 children 塞进一个「左：仙务融合面板 / 右：原 children」的两列外壳：
        children: __xw
          ? e.jsxs("div",{className:"grid grid-cols-1 md:grid-cols-2 gap-4 items-start",
              children:[ e.jsx("div",{className:"min-w-0",children:e.jsx(YlxwFuse,{k:__xw})}),
                         e.jsx("div",{className:"min-w-0",children:l}) ]})
          : l
    且 `__xw` 为真时宽度改用 `md:max-w-6xl`（1152px）。
    ⇒ 秘境弹窗实际布局 = 左「仙务·秘境手札」+ 右「秘境列表」，**右列只有 ≈50% 宽**。
  · 但 `cM` 自己的卡片网格仍是 `lg:grid-cols-3`，而 `lg:` 断点看的是**视口**（≥1024px），
    不是容器 ⇒ 视口一过 1024，右列（≈543px）里硬排 3 列卡片。
  · 真机实测（沙盒 idx=5，1440×900，`build/assets/index-v28111-20260930.js`）：
      融合外壳 `grid grid-cols-1 md:grid-cols-2 gap-4 items-start` → 列宽 `543px 543px`
      卡片网格 `… lg:grid-cols-3 gap-3 md:gap-6` → 列宽 `138.3px 138.3px 138.3px`
      卡片 h4 标题被压成两行（`h=56px`，单行应为 24~28px）；文案「极度危险 风险」竖排折断。
    1024 视口同样 138px；900 视口（<lg）退 2 列 → 188px（反而更好）。
    ⇒ 这就是用户说的「右侧面板被压缩」。

修法（最小、可回退：只把「秘境卡片网格」的 `lg:grid-cols-3` 去掉）
--------------------------------------------------------------------------
  `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-6`
  → `grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-6`
  理由：右列上限 ≈ 1152px/2 ≈ 576px，**永远放不下 3 列**（每列 <200px）；2 列才是
  该容器下的正解。改后实测：1440 → 260px/列、1024 → 220px/列，标题恢复单行。
  · 不碰融合外壳（`wN`），故 gongfa/sect/pet/farm/ach/rebirth 等其它 `xw` 弹窗**零影响**。
  · 不改断点 `grid-cols-1`（手机）/`md:grid-cols-2`（平板）行为，仅去掉 `lg` 那一档。

锚点唯一性（实测）
--------------------------------------------------------------------------
  · `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-6` → 产物 count **1**（= cM）。
  · 全仓 `grep -rn --include=*.py -F 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3' .` = **0**
    ⇒ 无其它模块把它当 needle。
  · 另 3 处同前缀三列网格（修炼系统 / 灵宠页 / 出售页）用的是 `gap-4 relative` / `gap-3"`，
    **不含** `md:gap-6` 后缀 ⇒ 不在本锚点内，保持原样（门禁 3 条）。

硬约束
--------------------------------------------------------------------------
  · 无注入块（`INJECT_JS = ''`）：本模块纯就地替换，不新增任何 JS。
  · 每个 replace 带精确 expect；只新建本文件；不改 build_v26n.py、不写 build/assets/。
"""

import re

# 无注入块（build_v26n.py 对空 INJECT_JS 安全：zh('')=''，无禁用模式）
INJECT_JS = ''

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# cM（秘境探索）卡片网格：唯一带 `md:gap-6` 后缀的三列网格
GRID_OLD = 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-6'
GRID_NEW = 'grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-6'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    # 1) 秘境卡片网格 3 列 → 2 列（右列容器上限 ≈576px，放不下 3 列）
    p.replace('r032layout-grid', GRID_OLD, GRID_NEW, expect=1,
              note='cM 秘境卡片网格去 lg:grid-cols-3（右列仅 ≈50% 宽）')

    # ------------------------------------------------------------- 门禁
    gates = [
        ('R32L·秘境网格已降为两列',   GRID_NEW, 1, '==', ''),
        ('R32L·秘境旧三列网格已清零', GRID_OLD, 0, '==', ''),
        # 另 3 处同前缀三列网格（修炼系统 / 灵宠页 / 出售页）必须保持原样
        ('R32L·其它三列网格保持原样', 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3', 3, '==', '修炼/灵宠/出售 共 3 处未动'),
        # 融合外壳（wN）逐字未动 —— 保证其它 xw 弹窗零影响
        ('跨模块·融合外壳未动',       'grid grid-cols-1 md:grid-cols-2 gap-4 items-start', 2, '==', 'wN 外壳 + 人物志'),
        ('跨模块·融合左列未动',       'children:e.jsx(YlxwFuse,{k:__xw})', 1, '==', ''),
        # 秘境弹窗的其它结构（信息条 / 入口 / 卡片）不得被本模块改动
        ('跨模块·cM 信息条未动',
         r'children:[YLXW_DGS?YLXW_DGS.count:"\u2014"," / ",YLXW_DGS?YLXW_DGS.cap:3]', 1, '==', 'dungeon2/v2811a 门禁串'),
        ('跨模块·Roguelike 入口未动', 'children:"\U0001f3f0 \u79d8\u5883 Roguelike \u63a2\u7d22"', 1, '==', ''),
        ('跨模块·进入秘境按钮未动',   'children:[T?"\u5883\u754c\u4e0d\u8db3":x?"\u8fdb\u5165\u79d8\u5883":"\u7075\u77f3\u4e0d\u8db3"', 1, '==', 'cM 卡片按钮（字面中文）'),
        # 红线：本模块不注入任何 JS
        ('R32L·无注入块',             '/* ===== yl-R032L', 0, '==', '本模块纯就地替换，无 JS'),
    ]
    return gates
