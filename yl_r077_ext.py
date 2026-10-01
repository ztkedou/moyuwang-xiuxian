# -*- coding: utf-8 -*-
r"""
yl_r077_ext.py — R-077 炼丹：开炉「出丹数量」区间展示（客户端半边）

需求原文（需求台账_进行中.md L26，R-077）
--------------------------------------------------------------------------
  「炼丹中，丹道这个里面开炉因为成熟时间较久，根据时长来增加随机获得的数量，
    最基础的聚气丹、回春丹每次 1-10 枚随机，后面高级点的也随机，但是随机数量减少。」

分工
--------------------------------------------------------------------------
  · **服务端半边**（srv_patch_r077.py，SRV_CHAIN 链尾）才是权威：claim 由「恒 1 枚」
    改为按成熟时长/方子档掷 [lo,hi] 枚、枚数折算灵石（期望 = cost×1.5 不变，保本下限 cost）；
    /api/alchemy/list 的 recipes 逐方增发 `qty: [lo,hi]` 区间。
  · 本模块只做**客户端展示**：在 R-064 的「出炉产出」行**之后**插一行「出丹数量 lo ~ hi 枚（随机）」，
    读服务端下发的 `rc.qty`（缺省回落「—」）。**不修改 R-064 的任何既有串**（其门禁逐字钉死）。

锚点（实测 count==1 @ build/assets/index-v291-20261001.js）
--------------------------------------------------------------------------
  R-064 C3 产物的「出炉产出」行（灵石 ×floor(cost×yieldRate)）——本模块把该行**原样保留**
  （R-064 门禁 `"\u7075\u77f3 \u00d7" + YlxwNum(...)` 仍恰 1），只在其闭合 `] })` 之后追加新行。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 不改 R-064 的既有锚点串（出炉产出行、丹方书行、丹房卡药效行、YLXW_PILL_FX/FXN）。
  · 不改 t17 面（YlxwAlcFire / 成功率 / 纯度 / 玩法说明）。
  · 替换串为 bundle 内字面 `\uXXXX` 形态（raw 串匹配）；本模块不做 zh() 注入。
  · 每个 replace 带 expect=1；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py / localtest/ / deploy_v28/ / srv/index_v28.ts / 产物。
  · 装配序：必须排在 r064 之后（锚点是 R-064 的产物形态）；排在 numbal 之前即可。
"""

import re

# --------------------------------------------------------------------------- 锚点（bundle 内为字面 \uXXXX，用 raw 串匹配）

# R-064 C3 产物：「出炉产出」行（原样保留）
ROW_OLD = r'''        e.jsx("span", { className: "shrink-0 text-amber-300 font-mono", children: "\u7075\u77f3 \u00d7" + YlxwNum(Math.floor((rc.cost || 0) * ((l && l.yieldRate) || 1.5))) + (rc.name === "\u51dd\u5143\u4e39" ? " + \u4e39\u56ca\u00d71" : "") })
      ] })'''

# 追加：出丹数量行（读服务端 rc.qty；缺省 —）
ROW_NEW = ROW_OLD + r''',
      e.jsxs("div", { className: "flex justify-between gap-2", children: [
        e.jsx("span", { className: "text-stone-500", children: "\u51fa\u4e39\u6570\u91cf" }),
        e.jsx("span", { className: "shrink-0 text-amber-300 font-mono", children: (rc.qty ? (rc.qty[0] + " ~ " + rc.qty[1] + " \u679a\uff08\u968f\u673a\uff09") : "\u2014") })
      ] })'''

# —— 冻结门禁锚点（只读；R-064 / t17 面逐字未动的证据）——
FRZ_R64_YIELD = r'"\u7075\u77f3 \u00d7" + YlxwNum(Math.floor((rc.cost || 0) * ((l && l.yieldRate) || 1.5)))'
FRZ_R64_FX = 'children:YLXW_PILL_FX(W.result)||""'
FRZ_R64_BOOK = r'"\u836f\u6548\uff1a" + (R.summary || YLXW_PILL_FXN(R.name) || "\u2014")'
FRZ_T17_FIRE = 'var YlxwAlcFire = ['
FRZ_T17_PANEL = 'function YlxwTAlchemy(r) {'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 r064）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检：替换串必须真的变了，且带 rc.qty 分支（防手滑写成恒等）
    if ROW_OLD == ROW_NEW or 'rc.qty' not in ROW_NEW:
        raise AssertionError('r077 锚点异常：出丹数量行未接入 rc.qty')
    if r'\u51fa\u4e39\u6570\u91cf' not in ROW_NEW:
        raise AssertionError('r077 锚点异常：缺「出丹数量」标签')

    p.replace('r077-qty-row', ROW_OLD, ROW_NEW, expect=1,
              note='开炉预览补「出丹数量 lo~hi 枚（随机）」行（读服务端 recipe.qty）')

    gates = [
        # ================= 本模块改动 =================
        ('R77·出丹数量行已注入',   r'"\u51fa\u4e39\u6570\u91cf"', 1, '==', ''),
        ('R77·区间渲染',          r'rc.qty[0] + " ~ " + rc.qty[1] + " \u679a\uff08\u968f\u673a\uff09"', 1, '==', ''),
        ('R77·无 qty 兜底',       '(rc.qty ? (', 1, '==', '服务端未下发时显示 —'),
        ('R77·原产出行仍在',      ROW_OLD, 1, '==', 'ROW_OLD 是 ROW_NEW 的前缀，应恰 1'),
        # ================= 冻结：R-064 面（本模块不得回踩）=================
        ('冻结·R64 出炉产出行未动', FRZ_R64_YIELD, 1, '==', '只在其后追加，未改该行'),
        ('冻结·R64 收益率引用未动', 'yieldRate', 1, '==', ''),
        ('冻结·R64 丹方书药效行未动', FRZ_R64_BOOK, 1, '==', ''),
        ('冻结·R64 丹房卡药效行未动', FRZ_R64_FX, 1, '==', ''),
        ('冻结·R64 药效助手未动',   'function YLXW_PILL_FX(d) {', 1, '==', ''),
        # ================= 冻结：t17 丹炉面 =================
        ('冻结·t17 火候表未动',     FRZ_T17_FIRE, 1, '==', ''),
        ('冻结·t17 主面板唯一',     FRZ_T17_PANEL, 1, '==', ''),
        ('冻结·t17 开炉请求契约未动', '{ recipeKey: selRecipe, slot: pickSlot, fire: selFire, pill: selRecipe }', 1, '==', ''),
    ]
    return gates
