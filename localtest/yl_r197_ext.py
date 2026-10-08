# -*- coding: utf-8 -*-
r"""
yl_r197_ext.py — R-197：妖灵/灵宠 面板两处「整块搬移」（standalone 纯客户端，纯 UI 结构重排）

★ 需求原文（用户，逐字，唯一依据）：
  「② 根据当前上线的最新版本，做下面的调整：
    1. 「灵宠口径参考（非当前加成）」这个实际上就是妖灵折算灵宠的属性，直接显示在（截图 #1 的红框位置）。
    2. 「融合玩法」因为是灵宠的融合，直接全部移到右侧「我的灵宠」上方。其他 ui 不用变。」

★ 本环边界（严格）：
  · 只做上面两件事：① 折算属性块挪到妖灵卡片正下方（红框位置）；② 融合玩法块整块搬进灵宠弹窗右列。
  · **不碰**「培养」区（进食/互动/买额度行）、「灵纹」行、卡片本身、说明文字内容、秘径行、记录列表。
  · 不改任何数值逻辑、不改服务端、不删功能块、不动其它 `yl_r*_ext.py` / `patches/*` / 台账。

==============================================================================
零、改动清单（2 条，均为「整块移动」而非复制）
==============================================================================
  ① 「灵宠口径参考（非当前加成）」块（= `YlxwTSpiritUse` 里的 `lines` 数组）
     · 从 `YlxwTSpiritUse` **拆出**为独立组件 `YlxwSpiritFoldView`，**整块**移到
       `YlxwTPet` 的 children 里、`YlxwR18Card(t, m)`（妖灵卡片 + 其说明文字）**正下方**。
     · 改名：`灵宠口径参考（非当前加成）` → **`妖灵折算灵宠属性（参考）`**（理由见 §二）。
     · 说明句里的「上方卡片」**保留不改**（搬移后卡片仍在其正上方，方位词依然成立；见 §二·②）。
  ② 「融合玩法」块（= `YlxwTSpiritUse` 里的 `fuse` 数组 + 折叠内联 `YlxwPetFuseTab`）
     · 从 `YlxwTSpiritUse` **拆出**为独立组件 `YlxwSpiritFuseView`，**整块**移到
       灵宠弹窗（`vM`，即 `ct` 的 `xw:"pet"` 内容）**右列**、`我的灵宠 (N)` 标题块**正上方**。
     · 妖灵页签（`YlxwTPet`）里**不再保留**该块（不是留两份）。
  · 拆出后 `YlxwTSpiritUse` 只剩「灵宠本体参考」一行，仍留在妖灵面板原位置（用户只点名要搬折算块）。

==============================================================================
一、面板实际渲染顺序 + 各块锚点（取证，非推断）
==============================================================================
  · `YlxwTPet`（@1051185 附近，单行 minified）children 顺序：
      YlxwTitle(妖灵)
      YlxwR79Box(妖灵, 玩法说明…)
      [ m ? ( YlxwR18Card(t, m) , YlxwR18Panel(t, m, f, u) ) : YlxwR18AdoptRow(t, f, u) ]
      /* [r167pet] … */ m && e.jsx(YlxwTSpiritUse, { pet: m })      ← 折算块 + 本体行 + 融合块 都在这里
      (function(){ … 记录列表 … })()
    ⇒ 锚点：`[YlxwR18Card(t, m), YlxwR18Panel(t, m, f, u)]`（唯一，ASCII）。
    ⇒ 说明文字（喂食度＝妖灵经验… / 妖灵之力 PP = … / 羁绊：…）在 `YlxwR18Card` **内部尾部**
      ⇒ 「妖灵卡片正下方、说明文字那一带」= `YlxwR18Card(...)` 之后、`YlxwR18Panel(...)` 之前。

  · `YlxwTSpiritUse`（@1022938）结构：
      var lines = [ … 折算块（标题+说明+转化率+攻/防/血/身法/暴击/闪避）… ];
      var fuse  = [ … 融合玩法（标题+按钮 / 可融合数 / 融合费 / 灵兽秘径 / 内联 YlxwPetFuseTab）… ];
      return <div class="space-y-2 bg-ink-800/60 …">
               <div class="text-xs flex …">{lines}</div>
               <div class="text-[11px] …">灵宠本体参考（物种在归位时确定）：…</div>
               <div class="space-y-1.5 pt-1.5 border-t border-dashed …">{fuse}</div>
             </div>;

  · 灵宠弹窗布局（关键取证）：
      `YlxwPetShell`（@1462552 附近）返回 Fragment[ PetTabBar, YlxwPetLaneBar, vM ]。
      `vM`（@1756822）= 灵宠系统弹窗组件，内部 `e.jsxs(ct, { xw: "pet", … })`。
      `ct = O.memo(wN)`，`wN` **走 `Yb.createPortal(A, document.body)`**（@256058）。
      `wN` 在 `__xw` 非空时把内容渲染为**两列 grid**：
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
          <div class="min-w-0">{ e.jsx(YlxwFuse, { k: __xw }) }</div>   ← 左列 = 妖灵面板（YLXW_COMP.pet = YlxwTPet）
          <div class="min-w-0">{ l }</div>                             ← 右列 = 弹窗 children（灵宠列表）
        </div>
      ⇒ **「右侧」= 灵宠系统弹窗的右列**；左列就是妖灵面板（所以截图 #1 的妖灵卡片与红框都在左列）。
      ⇒ 右列 children 顶层恰 2 个元素（字符级切分验证）：
           child0 = `I&&e.jsxs("div",{className:"bg-stone-900 rounded p-4 border-2 border-yellow-600", …` （已激活灵宠卡）
           child1 = `e.jsxs("div",{children:[e.jsxs("div",{className:"flex items-center justify-between mb-3",
                       children:[e.jsxs("h3",{className:"text-lg font-bold",children:["我的灵宠 (",a.pets.length,")"]}) …` （我的灵宠区）
      ⇒ 锚点（含字面 UTF-8「我的灵宠」，唯一）：
         `,e.jsxs("div",{children:[e.jsxs("div",{className:"flex items-center justify-between mb-3",children:[e.jsxs("h3",{className:"text-lg font-bold",children:["我的灵宠 (",a.pets.length,")"]})`

==============================================================================
二、① 的搬移方案 + 新标题 + 「上方卡片」那句的处理
==============================================================================
  ① 方案：`lines` 数组原样（仅改标题字符串）搬进新组件 `YlxwSpiritFoldView(props)`；
     props.pet = 妖灵对象（与旧 `YlxwTSpiritUse` 的 `sp` 同源）；
     组件返回 `<div class="space-y-2 bg-ink-800/60 border border-stone-700 rounded p-2.5">
                  <div class="text-xs flex flex-wrap gap-x-2 gap-y-0.5">{lines}</div></div>`
     —— 沿用原容器样式，保证「整块」观感一致。
     挂载点：`[YlxwR18Card(t, m), e.jsx(YlxwSpiritFoldView, { pet: m }), YlxwR18Panel(t, m, f, u)]`
     —— 紧贴妖灵卡片（含其尾部说明文字）正下方，即红框位置。

  ② 新标题：**「妖灵折算灵宠属性（参考）」**
     理由：用户原话「这个实际上就是**妖灵折算灵宠的属性**」——新标题直接复述用户定义；
       保留「（参考）」是因为该块数值**既不是**当前「主人加成」（= 妖灵属性 × 10% × PP），
       **也不是**归位后实际结算（见 yl_r189 的定位核实：块内用 lv 版属性、归位写入用 1 级属性，差 ≈1.08^(lv-1)）；
       去掉「非当前加成」是因为块内说明句已逐字写清「当前妖灵本体不提供这些加成…」，标题不必再否定式提示。

  ③ 「上方卡片」那句的处理：**保留不改**。
     该句在块内（`lines[1]`）：「…当前实际加成见**上方卡片**「主人加成」（= 妖灵属性 × 10% × 妖灵之力 PP）…」。
     搬移后本块就贴在 `YlxwR18Card` 正下方 ⇒ 「上方卡片」指的仍是那块妖灵卡片，方位词**依然成立**（且比原先更贴切）。
     ⇒ 不改字符串，`/*[r189conv]*/` 标记亦原样保留。

==============================================================================
三、② 的落点判断（「右侧『我的灵宠』上方」的两种解释与取舍）
==============================================================================
  · 解释 A：弹窗**顶部**（`PetTabBar` 页签栏之前）。
  · 解释 B（**本环采用**）：弹窗**右列**、`我的灵宠 (N)` 标题块**正上方**。
  取舍理由：
    1. 取证显示「我的灵宠」是**右列内的字面标题**（`h3`「我的灵宠 (N)」），且弹窗内容在 `xw:"pet"` 时是
       **两列 grid**（左=妖灵面板、右=灵宠列表）⇒ 用户口中的「右侧」= 右列，不是整屏居中弹窗的顶部。
    2. `PetTabBar`/`YlxwPetLaneBar` 渲染在 `vM` **之前**，而 `vM` 走 `createPortal(document.body)` 且
       `fixed inset-0 z-[60]` ⇒ 页签栏实际落在 portal 之外、被遮罩压在下面（本次取证发现，非本环引入，
       本环不动它）。若按解释 A 插到 `PetTabBar` 之前，块会落在 portal 外 ⇒ **不可见**。故 A 不可行。
    3. 用户原话带书名号「我的灵宠」，指向的是那个字面标题 ⇒ 贴其正上方最贴字面。
  · 解释 A 的位置坐标（供用户确认，本环未采用）：
       `YlxwPetShell` 的 `return e.jsxs(e.Fragment, { children: [ PetTabBar(tab, setTab), … ] })`
       —— 即 `PetTabBar(tab, setTab),` 之前一行；**注意**：该处位于 portal 之外，实际会被弹窗遮罩盖住。

  · 秘径行的处理（必要交代）：
     融合块内有一行「灵兽秘径 · 单次 N 灵石 + M 气血 + K 修为」，原以 `YlxwSpiritPetView(sp)`
     （妖灵折算视图）为基准。右列**拿不到**妖灵数据（`/pet` 由左列 `YlxwTPet` 拉取）。
     本环做法：`YlxwSpiritFuseView` 新增可选 prop `pet`（基准灵宠），**行内文案与算式逐字未改**
     （仍写作 `YlxwPetPathCost(pet)` / `pet.evolutionStage`），仅把基准来源换成**当前出战灵宠**
     （`vM` 内既有的 `I = a.pets.find(p => p.id === a.activePetId)`）；无出战灵宠时回退
     `{ rarity:"普通", evolutionStage:0, affection:0 }`。⇒ 行本身「未动」，基准随所在面板语义自然改为灵宠。

==============================================================================
四、`YlxwPetOnFuseRef` 隐式依赖：**已消除**（确认）
==============================================================================
  · 旧形态：融合块在**妖灵页签**内，靠模块级 `YlxwPetOnFuseRef`（由 `YlxwPetShell` 渲染时赋值）拿到融合动作
    ⇒ 必须先打开过灵宠弹窗，妖灵页签里的融合面板才可用（否则显示「融合面板未就绪…」）。
  · 搬入灵宠弹窗右列后：该块与 `YlxwPetShell` **同处一个弹窗子树**，`YlxwPetShell` 渲染时
    `var onFuse = YlxwPetOnFuseRef = function (…) {…}`（@1464993）**必然先于** `vM` 渲染执行
    ⇒ `YlxwPetOnFuseRef` 恒非空 ⇒ **隐式依赖天然消失**，不会再出现「融合面板未就绪」。
  · 本环保留 `YlxwPetOnFuseRef` 三元兜底分支（不改逻辑），仅作为防御性死分支。

==============================================================================
五、契约
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 结构探针）。
  · 就地替换 7 处（见 REPLACEMENTS）；每处打前断言 `count == 1`（锚点纯 ASCII；含字面中文的仅 R7，用 \uXXXX 写出）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r197-<时刻>`。
  · 幂等：产物已含标记 `/*[r197ui]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 探针：从补丁后产物实抽 `YlxwSpiritFoldView` / `YlxwSpiritFuseView` / `YlxwTSpiritUse` 三段源码，
    node 桩化依赖后真实调用，校验三者的渲染内容（折算块含新标题不含融合玩法；融合块含融合玩法；
    本体行组件两者皆不含）。**真执行、非 grep**。
  · 不跑网络：只读 --src 指向的本地文件。
  · ★ 冻结针脚只钉本批**不动**的稳定形态，**绝不**钉 `[r180adv*]`/`[r185farm*]`/`[r184wudao]`/`[r187guide]`/
    `[r188med*]`/`[r190feed]`/`[r189ui]`/`[r189conv]`/`[r189rune]`/`[r192fuse]`/`[r193qy]`/`[r195away]`/`[r196rune]`。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# 幂等标记（本批）
IDEMPOTENT_MARK = '/*[r197ui]*/'

# --------------------------------------------------------------------------- 替换项
# ★ 形态约定：bundle 妖灵面板区域中文为**字面 `\uXXXX`**（六字符）⇒ 用 `\\uXXXX`（双反斜杠）写出；
#   灵宠弹窗右列（vM 区域）中文为**裸 UTF-8** ⇒ 用 `\uXXXX`（单反斜杠）写出，运行期即真中文字符。

# ---- R1：YlxwTSpiritUse 头部 → YlxwSpiritFoldView 头部（拆出折算块） ----
R1_OLD = (
    'function YlxwTSpiritUse(props) {\n'
    '  var sp = props && props.pet;\n'
    '  var player = Be(function (s) { return s.player; });\n'
    '  var sst = O.useState(!1), open = sst[0], setOpen = sst[1];\n'
    '  var pet = YlxwSpiritPetView(sp);\n'
    '  var b = YlxwSpiritBonusView(pet);\n'
    '  var body = pet.stats || {};\n'
    '  var pets = (player && player.pets) || [];\n'
    '  var lines = [\n'
)
R1_NEW = (
    'function YlxwSpiritFoldView(props) {\n'
    '  var sp = props && props.pet;\n'
    '  var pet = YlxwSpiritPetView(sp);\n'
    '  var b = YlxwSpiritBonusView(pet);\n'
    '  var lines = [\n'
)

# ---- R2：折算块标题改名 ----
R2_OLD = '    e.jsx("span", { className: "text-amber-300 font-bold", children: "\\u7075\\u5ba0\\u53e3\\u5f84\\u53c2\\u8003\\uff08\\u975e\\u5f53\\u524d\\u52a0\\u6210\\uff09" }, "t"),'
R2_NEW = '    e.jsx("span", { className: "text-amber-300 font-bold", children: "\\u5996\\u7075\\u6298\\u7b97\\u7075\\u5ba0\\u5c5e\\u6027\\uff08\\u53c2\\u8003\\uff09" }, "t"),'

# ---- R3：lines 收尾 → 折算块 return；并起 YlxwSpiritFuseView 头部（拆出融合块） ----
R3_OLD = (
    '    e.jsx("span", { children: "\\u95ea\\u907f +" + (b.dodgeRate * 100).toFixed(1) + "%" }, "o")\n'
    '  ];\n'
    '  var fuse = [\n'
)
R3_NEW = (
    '    e.jsx("span", { children: "\\u95ea\\u907f +" + (b.dodgeRate * 100).toFixed(1) + "%" }, "o")\n'
    '  ];\n'
    '  return e.jsxs("div", { className: "space-y-2 bg-ink-800/60 border border-stone-700 rounded p-2.5", children: [\n'
    '    e.jsxs("div", { className: "text-xs flex flex-wrap gap-x-2 gap-y-0.5", children: lines })\n'
    '  ] });' + IDEMPOTENT_MARK + '\n'
    '}\n'
    'function YlxwSpiritFuseView(props) {\n'
    '  var player = (props && props.player) || Be(function (s) { return s.player; });\n'
    '  var sst = O.useState(!1), open = sst[0], setOpen = sst[1];\n'
    '  var pets = (player && player.pets) || [];\n'
    '  var pet = (props && props.pet) || { rarity: "\\u666e\\u901a", evolutionStage: 0, affection: 0 };\n'
    '  var fuse = [\n'
)

# ---- R4：融合块 if(open) 尾 → 融合块 return；并起 YlxwTSpiritUse 新头部（仅本体行） ----
R4_OLD = (
    '  if (open) {\n'
    '    fuse.push(YlxwPetOnFuseRef\n'
    '      ? e.jsx(YlxwPetFuseTab, { player: player, onFuse: YlxwPetOnFuseRef }, "fx")\n'
    '      : e.jsx("div", { className: "text-[11px] text-stone-500", children: "\\u878d\\u5408\\u9762\\u677f\\u672a\\u5c31\\u7eea\\uff0c\\u8bf7\\u5173\\u95ed\\u540e\\u91cd\\u65b0\\u6253\\u5f00\\u7075\\u5ba0\\u7cfb\\u7edf\\u3002" }, "fx"));\n'
    '  }\n'
    '  return e.jsxs("div", { className: "space-y-2 bg-ink-800/60 border border-stone-700 rounded p-2.5", children: [\n'
    '    e.jsxs("div", { className: "text-xs flex flex-wrap gap-x-2 gap-y-0.5", children: lines }),\n'
    '    e.jsxs("div", { className: "text-[11px] text-stone-500", children: [\n'
)
R4_NEW = (
    '  if (open) {\n'
    '    fuse.push(YlxwPetOnFuseRef\n'
    '      ? e.jsx(YlxwPetFuseTab, { player: player, onFuse: YlxwPetOnFuseRef }, "fx")\n'
    '      : e.jsx("div", { className: "text-[11px] text-stone-500", children: "\\u878d\\u5408\\u9762\\u677f\\u672a\\u5c31\\u7eea\\uff0c\\u8bf7\\u5173\\u95ed\\u540e\\u91cd\\u65b0\\u6253\\u5f00\\u7075\\u5ba0\\u7cfb\\u7edf\\u3002" }, "fx"));\n'
    '  }\n'
    '  return e.jsxs("div", { className: "space-y-1.5 bg-ink-800/60 border border-stone-700 rounded p-2.5", children: fuse });' + IDEMPOTENT_MARK + '\n'
    '}\n'
    'function YlxwTSpiritUse(props) {\n'
    '  var sp = props && props.pet;\n'
    '  var pet = YlxwSpiritPetView(sp);\n'
    '  var body = pet.stats || {};\n'
    '  return e.jsxs("div", { className: "space-y-2 bg-ink-800/60 border border-stone-700 rounded p-2.5", children: [\n'
    '    e.jsxs("div", { className: "text-[11px] text-stone-500", children: [\n'
)

# ---- R5：本体行收尾（去掉 fuse 容器） ----
R5_OLD = (
    '      " \\u00b7 \\u6c14\\u8840 " + YlxwNum(body.hp), " \\u00b7 \\u8eab\\u6cd5 " + YlxwNum(body.speed)\n'
    '    ] }),\n'
    '    e.jsxs("div", { className: "space-y-1.5 pt-1.5 border-t border-dashed border-stone-700", children: fuse })\n'
    '  ] });\n'
    '}'
)
R5_NEW = (
    '      " \\u00b7 \\u6c14\\u8840 " + YlxwNum(body.hp), " \\u00b7 \\u8eab\\u6cd5 " + YlxwNum(body.speed)\n'
    '    ] })\n'
    '  ] });\n'
    '}'
)

# ---- R6：折算块挂到妖灵卡片正下方（红框位置） ----
R6_OLD = '[YlxwR18Card(t, m), YlxwR18Panel(t, m, f, u)]'
R6_NEW = '[YlxwR18Card(t, m), e.jsx(YlxwSpiritFoldView, { pet: m }), YlxwR18Panel(t, m, f, u)]'

# ---- R7：融合块挂到灵宠弹窗右列「我的灵宠」正上方（字面中文，单反斜杠写出） ----
R7_OLD = (
    ',e.jsxs("div",{children:[e.jsxs("div",{className:"flex items-center justify-between mb-3",'
    'children:[e.jsxs("h3",{className:"text-lg font-bold",children:["\u6211\u7684\u7075\u5ba0 (",a.pets.length,")"]})'
)
R7_NEW = (
    ',e.jsx(YlxwSpiritFuseView,{player:a,pet:I}),'
    'e.jsxs("div",{children:[e.jsxs("div",{className:"flex items-center justify-between mb-3",'
    'children:[e.jsxs("h3",{className:"text-lg font-bold",children:["\u6211\u7684\u7075\u5ba0 (",a.pets.length,")"]})'
)

REPLACEMENTS = [
    ('r1_fold_head', R1_OLD, R1_NEW),
    ('r2_title', R2_OLD, R2_NEW),
    ('r3_fuse_head', R3_OLD, R3_NEW),
    ('r4_use_head', R4_OLD, R4_NEW),
    ('r5_use_tail', R5_OLD, R5_NEW),
    ('r6_mount_fold', R6_OLD, R6_NEW),
    ('r7_mount_fuse', R7_OLD, R7_NEW),
]

# 冻结针脚（对**输入**校验）：本批不动的稳定形态（绝不含 [r180adv*]/[r185farm*]/[r184wudao]/
# [r187guide]/[r188med*]/[r190feed]/[r189ui]/[r189conv]/[r189rune]/[r192fuse]/[r193qy]/[r195away]/[r196rune]）。
FREEZE = [
    ('function YlxwSpiritPetView(', 1),
    ('function YlxwSpiritBonusView(', 1),
    ('function YlxwR18Card(', 1),
    ('function YlxwR18Panel(', 1),
    ('function YlxwTPet(', 1),
    ('function YlxwPetShell(', 1),
    ('function YlxwPetFuseTab(', 1),
    ('function PetTabBar(', 1),
    ('function YlxwPetLaneBar(', 1),
    ('function YlxwPetPathCost(', 1),
    ('function YlxwPetPathHp(', 1),
    ('function YlxwPetPathExp(', 1),
    ('function YlxwSpiritToPet(', 1),
    ('function YlxwMergeSpiritAway(', 1),
    ('var YlxwPetOnFuseRef = null;', 1),
    ('var YLXW_PET_FUSE_BASE = 3000;', 1),
]

# 新标题逐字（产物中为字面 \uXXXX）
_NEW_TITLE = '\\u5996\\u7075\\u6298\\u7b97\\u7075\\u5ba0\\u5c5e\\u6027\\uff08\\u53c2\\u8003\\uff09'
_OLD_TITLE = '\\u7075\\u5ba0\\u53e3\\u5f84\\u53c2\\u8003\\uff08\\u975e\\u5f53\\u524d\\u52a0\\u6210\\uff09'


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    needle 可为 tuple（多形态合计计数）。"""
    return [
        # ---- 幂等标记 ----
        ('R197\u00b7\u5e42\u7b49\u6807\u8bb0 r197ui', IDEMPOTENT_MARK, 2, '==', '[r197ui] 恰 2 处'),
        # ---- ① 折算块 ----
        ('R197\u2460\u00b7\u65b0\u6807\u9898\u300c\u5996\u7075\u6298\u7b97\u7075\u5ba0\u5c5e\u6027\uff08\u53c2\u8003\uff09\u300d',
         'children: "' + _NEW_TITLE + '" }, "t")', 1, '==', '新标题'),
        ('R197\u2460\u00b7\u65e7\u6807\u9898\u300c\u7075\u5ba0\u53e3\u5f84\u53c2\u8003\u300d\u5df2\u6e05\u96f6',
         'children: "' + _OLD_TITLE + '" }, "t")', 0, '==', '旧标题 0 处'),
        ('R197\u2460\u00b7\u65b0\u7ec4\u4ef6 YlxwSpiritFoldView',
         'function YlxwSpiritFoldView(props) {', 1, '==', '折算块组件定义'),
        ('R197\u2460\u00b7\u6298\u7b97\u5757\u6302\u5230\u5361\u7247\u6b63\u4e0b\u65b9',
         '[YlxwR18Card(t, m), e.jsx(YlxwSpiritFoldView, { pet: m }), YlxwR18Panel(t, m, f, u)]',
         1, '==', '卡片\u2192折算块\u2192培养区'),
        ('R197\u2460\u00b7\u8bf4\u660e\u53e5\u300c\u4e0a\u65b9\u5361\u7247\u300d\u4fdd\u7559',
         '\\u5f53\\u524d\\u5b9e\\u9645\\u52a0\\u6210\\u89c1\\u4e0a\\u65b9\\u5361\\u7247', 1, '==', '方位词未改'),
        ('R197\u2460\u00b7\u8f6c\u5316\u7387\u884c\u672a\u52a8',
         '\\uff08\\u7075\\u5ba0\\u53e3\\u5f84\\uff1a\\u4e3b\\u6218\\u51fa\\u6218\\u8f6c\\u5316 ', 1, '==', '（灵宠口径：主战出战转化 '),
        # ---- ② 融合块 ----
        ('R197\u2461\u00b7\u65b0\u7ec4\u4ef6 YlxwSpiritFuseView',
         'function YlxwSpiritFuseView(props) {', 1, '==', '融合块组件定义'),
        ('R197\u2461\u00b7\u878d\u5408\u5757\u6302\u5230\u5f39\u7a97\u53f3\u5217',
         'e.jsx(YlxwSpiritFuseView,{player:a,pet:I})', 1, '==', '右列插入点'),
        ('R197\u2461\u00b7\u63d2\u5165\u70b9\u7d27\u90bb\u300c\u6211\u7684\u7075\u5ba0\u300d',
         ',e.jsx(YlxwSpiritFuseView,{player:a,pet:I}),e.jsxs("div",{children:[e.jsxs("div",{className:"flex items-center justify-between mb-3",children:[e.jsxs("h3",{className:"text-lg font-bold",children:["\u6211\u7684\u7075\u5ba0 (",a.pets.length,")"]})',
         1, '==', '紧贴「我的灵宠 (N)」标题'),
        ('R197\u2461\u00b7\u5996\u7075\u9875\u7b7e\u5185\u878d\u5408\u5757\u5df2\u79fb\u9664',
         'var fuse = [', 1, '==', 'fuse 数组仅在新组件'),
        ('R197\u2461\u00b7\u878d\u5408\u73a9\u6cd5\u6807\u9898\u4ecd\u5728',
         '\\u878d\\u5408\\u73a9\\u6cd5', 1, '==', '融合玩法'),
        ('R197\u2461\u00b7\u79d8\u5f84\u884c\u9010\u5b57\u4fdd\u7559',
         '\\u7075\\u517d\\u79d8\\u5f84 \\u00b7 \\u5355\\u6b21 ', 1, '==', '灵兽秘径 · 单次'),
        ('R197\u2461\u00b7\u878d\u5408\u9762\u677f\u672a\u5c31\u7eea\u5151\u5e95\u5206\u652f\u4fdd\u7559',
         '\\u878d\\u5408\\u9762\\u677f\\u672a\\u5c31\\u7eea', 1, '==', '防御性死分支保留'),
        # ---- 本体行 / 未动项 ----
        ('R197\u00b7YlxwTSpiritUse \u4ecd\u5728\uff08\u4ec5\u672c\u4f53\u884c\uff09',
         'function YlxwTSpiritUse(props) {', 1, '==', '本体行组件'),
        ('R197\u00b7\u672c\u4f53\u884c\u9010\u5b57\u4fdd\u7559',
         '"\\u7075\\u5ba0\\u672c\\u4f53\\u53c2\\u8003\\uff08\\u7269\\u79cd\\u5728\\u5f52\\u4f4d\\u65f6\\u786e\\u5b9a\\uff09\\uff1a", pet.species,',
         1, '==', '本体行标题'),
        ('R197\u00b7YlxwPetOnFuseRef \u4ecd 4 \u5904',
         'YlxwPetOnFuseRef', 4, '==', 'ref 定义/赋值/使用'),
        ('R197\u00b7YlxwSpiritPetView 3 \u5904', 'YlxwSpiritPetView', 3, '==', '定义 + FoldView + TSpiritUse'),
        ('R197\u00b7YlxwSpiritBonusView 2 \u5904', 'YlxwSpiritBonusView', 2, '==', '定义 + FoldView'),
        ('R197\u00b7\u5361\u7247/\u57f9\u517b\u533a/\u5f39\u7a97\u672a\u52a8',
         ('function YlxwR18Card(', 'function YlxwR18Panel(', 'function YlxwPetShell(',
          'function YlxwPetFuseTab(', 'function PetTabBar('), 5, '>=', '各 1 处'),
        ('R197\u00b7\u57f9\u517b\u533a\u79d8\u5f84\u884c\u672a\u52a8',
         'children: "\\u5996\\u7075\\u79d8\\u5f84" }), node]', 1, '==', '妖灵秘径行标签'),
        ('R197\u00b7\u8bb0\u5f55\u5217\u8868\u672a\u52a8', 'YLXW_KIND[g.kind]', 1, '==', '玩法记录'),
        ('R197\u00b7[r189conv] \u6807\u8bb0\u672a\u52a8', '/*[r189conv]*/', 4, '==', 'r189conv 4 处'),
        ('R197\u00b7[r192fuse] \u6807\u8bb0\u672a\u52a8', '/*[r192fuse]*/', 1, '==', 'r192fuse 1 处'),
    ]


# --------------------------------------------------------------------------- 主流程

def _read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


def _write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(text.encode('utf-8'))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _is_patched(s):
    return IDEMPOTENT_MARK in s


def _precheck(s):
    """返回 err（None 表示可打）。"""
    for name, old, new in REPLACEMENTS:
        c = s.count(old)
        if c != 1:
            return '锚点 %s 出现 %d 次（期望 1）' % (name, c)
    for needle, cnt in FREEZE:
        c = s.count(needle)
        if c != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, c, cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时 out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPLACEMENTS:
        out = out.replace(old, new, 1)
    return out, None


def _count(out, needle):
    if isinstance(needle, tuple):
        return sum(out.count(x) for x in needle)
    return out.count(needle)


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    """反向还原：把每个 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
        r = subprocess.run([node, '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _extract_fn(s, name):
    """按大括号配平抽出 `function <name>(...) {...}` 源码；找不到返回 None。"""
    i = s.find('function ' + name + '(')
    if i < 0:
        return None
    j = s.find('{', i)
    if j < 0:
        return None
    depth = 0
    k = j
    while k < len(s):
        ch = s[k]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return s[i:k + 1]
        k += 1
    return None


_PROBE_STUBS = (
    'var __out = [];\n'
    'function __collect(n) {\n'
    '  if (n == null) return;\n'
    '  if (typeof n === "string") { __out.push(n); return; }\n'
    '  if (typeof n === "number" || typeof n === "boolean") { __out.push(String(n)); return; }\n'
    '  if (Object.prototype.toString.call(n) === "[object Array]") { for (var i = 0; i < n.length; i++) __collect(n[i]); return; }\n'
    '  if (typeof n === "object" && n.props) { __collect(n.props.children); }\n'
    '}\n'
    'function __mk(t, p, k) { return { type: t, props: p || {}, key: k }; }\n'
    'var e = { jsx: __mk, jsxs: __mk, Fragment: "Fragment" };\n'
    'var O = { useState: function (v) { return [v, function () {}]; } };\n'
    'function Be() { return null; }\n'
    'function YlxwSpiritPetView(sp) { return { name: "N", species: "SP", rarity: "\\u7a00\\u6709", level: 5,'
    ' evolutionStage: 0, affection: 100, stats: { attack: 1, defense: 2, hp: 3, speed: 4 } }; }\n'
    'function YlxwSpiritBonusView(pet) { return { rate: 0.5, attack: 11, defense: 22, maxHp: 33,'
    ' speed: 44, critRate: 0.05, dodgeRate: 0.06 }; }\n'
    'function YlxwNum(v) { return String(v); }\n'
    'function YlxwBtn() {}\n'
    'var YLXW_PET_FUSE_BASE = 3000;\n'
    'function YlxwPetPathCost(p) { return 7500; }\n'
    'function YlxwPetPathHp(m, s) { return 100; }\n'
    'function YlxwPetPathExp(m, s) { return 50; }\n'
    'var YlxwPetOnFuseRef = null;\n'
    'function YlxwPetFuseTab() {}\n'
)

_PROBE_TAIL = (
    '__out = []; __collect(YlxwSpiritFoldView({ pet: { name: "x" } }));\n'
    'var foldText = __out.join("");\n'
    'if (foldText.indexOf("\u5996\u7075\u6298\u7b97\u7075\u5ba0\u5c5e\u6027") < 0) throw new Error("FoldView 缺新标题");\n'
    'if (foldText.indexOf("\u53c2\u8003") < 0) throw new Error("FoldView 缺（参考）");\n'
    'if (foldText.indexOf("\u653b\u51fb +11") < 0) throw new Error("FoldView 缺攻击折算");\n'
    'if (foldText.indexOf("\u9632\u5fa1 +22") < 0) throw new Error("FoldView 缺防御折算");\n'
    'if (foldText.indexOf("\u6c14\u8840 +33") < 0) throw new Error("FoldView 缺气血折算");\n'
    'if (foldText.indexOf("\u8eab\u6cd5 +44") < 0) throw new Error("FoldView 缺身法折算");\n'
    'if (foldText.indexOf("\u878d\u5408\u73a9\u6cd5") >= 0) throw new Error("FoldView 混入融合玩法");\n'
    '__out = []; __collect(YlxwSpiritFuseView({ player: { pets: [{}, {}], maxHp: 1000, maxExp: 500 }, pet: null }));\n'
    'var fuseText = __out.join("");\n'
    'if (fuseText.indexOf("\u878d\u5408\u73a9\u6cd5") < 0) throw new Error("FuseView 缺融合玩法");\n'
    'if (fuseText.indexOf("\u53ef\u878d\u5408\u7075\u5ba0 2 \u53ea") < 0) throw new Error("FuseView 缺可融合计数: " + fuseText);\n'
    'if (fuseText.indexOf("\u7075\u517d\u79d8\u5f84") < 0) throw new Error("FuseView 缺秘径行");\n'
    'if (fuseText.indexOf("\u5996\u7075\u6298\u7b97\u7075\u5ba0\u5c5e\u6027") >= 0) throw new Error("FuseView 混入折算块");\n'
    '__out = []; __collect(YlxwTSpiritUse({ pet: { name: "x" } }));\n'
    'var useText = __out.join("");\n'
    'if (useText.indexOf("\u7075\u5ba0\u672c\u4f53\u53c2\u8003") < 0) throw new Error("TSpiritUse 缺本体行");\n'
    'if (useText.indexOf("\u878d\u5408\u73a9\u6cd5") >= 0) throw new Error("TSpiritUse 仍含融合玩法");\n'
    'if (useText.indexOf("\u5996\u7075\u6298\u7b97\u7075\u5ba0\u5c5e\u6027") >= 0) throw new Error("TSpiritUse 仍含折算块");\n'
    'console.log("r197-struct>> fold/fuse/use OK");\n'
)


def _probe_structure(patched_text):
    """从补丁后产物实抽三个函数源码，node 桩化依赖后真实调用并校验渲染内容。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。"""
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    parts = []
    for nm in ('YlxwSpiritFoldView', 'YlxwSpiritFuseView', 'YlxwTSpiritUse'):
        src = _extract_fn(patched_text, nm)
        if not src:
            return False, '%s 源码未找到' % nm
        parts.append(src)
    js = _PROBE_STUBS + '\n'.join(parts) + '\n' + _PROBE_TAIL
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:400]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 结构探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r197] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r197] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r197] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r197] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r197] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r197] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _probe_structure(out)
    if ok is False:
        print('[r197] SELFTEST FAIL struct-probe: ' + pmsg)
        return 1
    print('[r197] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg, pmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r197] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r197] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r197] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r197] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r197] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r197] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-52s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r197-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r197] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-52s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
