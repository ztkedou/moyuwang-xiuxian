# -*- coding: utf-8 -*-
r"""
yl_r198_ext.py — R-198 妖灵「培养」区新增「免费玩法」分组 + 买额度上限 2 → 5（standalone 纯客户端）

★ 用户原话（逐字，唯一依据）：
  「③④ 我一起说，现在的妖灵玩法，在「培养（出口：妖灵之力 PP）」加一栏「免费玩法」，
   里面放一个免费进食的按钮，喂食度一次加 100，一日 3 次，冷却 30 分钟。接着是免费互动的
   三个按钮，逗弄、梳毛、夜话。然后再接现在的「进食」和「买额度」，买额度改成 5 次，
   3 个选项共用 5 次上限。」

目标产物：build/assets/index-v2934-20261008.js（0.9.34；md5 550efc63d2289efa2795b1dc1bbda115）

==============================================================================
零、改前取证（对 0.9.34 产物字符级实测）
==============================================================================
  「培养（出口：妖灵之力 PP）」面板 = `function YlxwR18Panel(t, m, f, u)`，子节点顺序：
      [ 标题「培养（出口：妖灵之力 PP）」,
        YlxwR18FeedRow(t, m, f, u),        // D1 进食：三档付费（凡品/灵品/仙品）
        YlxwR18PlayRows(t, m, f, u),       // D2 互动（免费三按钮）+ 买额度（三按钮 + 今日已买 X/Y）
        YlxwR18ExpedRow(t, m, f, u),       // D4 妖灵秘径
        YlxwR18MiscRow(...), YlxwR18bRuneRow(...) ]
  · `YlxwR18PlayRows` 内部 `var free = [...]`（互动三按钮，`/pet/play` kind=tease/brush/talk）
    与 `var buy = [...]`（买额度三按钮，`/pet/play` kind+buy:true）两行。
  · 买额度上限 `var buyMax = YlxwNum(c.buyDailyMax) || 2;`（服务端 consts.buyDailyMax 权威，
    回退值 2）；三按钮共用同一 `bought` 计数（服务端 `WHERE bought < ?`）⇒「3 选项共用」本已成立。
  · 进食三档的按钮文案由服务端 feedTiers 下发；`[r189ui]` 已在其后追加「· 今日首次免费」后缀
    （本环**不动**，见 §二）。

==============================================================================
一、改法（4 处就地替换）
==============================================================================
  C1  把 `YlxwR18PlayRows` 头部的「免费互动」代码**整体前移**为新函数 `YlxwR18FreeRow`，
      并在其内新增「免费玩法」分组标题 + 「免费进食」按钮；`YlxwR18PlayRows` 只保留「买额度」。
        · 免费进食：读 `t.freeFeed`（服务端回显 {used,left,cdLeftMs,max,cdMs}）
          + `c.freeFeedMax/freeFeedHunger`（服务端常量表）；点击 `f("r18freefeed","/pet/feed",{free:true},…)`。
          ★ 字段名与服务端一致：`freeFeed`（新）与 R-167 的 `feedQuota`（旧，{date,used,free}）**并列**回显。
        · 免费互动三按钮：逐字搬移（tease/brush/talk 的 onClick/禁用/文案一律不变），
          故**不是新增**，避免重复入口。
  C2  去掉 `YlxwR18PlayRows` 里对 `free` 的渲染（`children: free })` 一行）。
  C3  `YlxwR18Panel` 子节点插入 `YlxwR18FreeRow(t, m, f, u),`（在进食之前）⇒ 顺序变为
        免费玩法 → 进食 → 买额度 → 妖灵秘径 → 点化/归位·灵纹。
  C4  「玩法说明」折叠块 `YlxwR79Box("\u5996\u7075", [...])` 的**第 ② 条**：原文写「互动…免费次数
      用完可花 20000 灵石买额度，每日最多 2 次。」（过时，未含免费进食）→ 改为如实反映本环后规则：
      「免费玩法：免费进食 +100 喂食度 / 每日 3 次 / 冷却 30 分钟（免灵石）；免费互动——逗弄/梳毛/
      夜话，每种每日免费 1 次、各 +5 羁绊。互动免费次数用完可花 20000 灵石买额度，3 种共用每日最多 5 次。」
      ★ 只改这一条；①②③④ 其余条目 / `YlxwR79Box` 折叠块标题一律不动（见门禁冻结）。
  · 买额度上限回退值 `|| 2` → `|| 5`（服务端已发 5；回退值同步防旧档）。

==============================================================================
二、边界（严格）
==============================================================================
  · **只碰「培养」区的进食 / 互动 / 买额度行**（`YlxwR18PlayRows` 拆分为 `YlxwR18FreeRow`+买额度行
    + `YlxwR18Panel` 子节点插入）。
  · **不动**：卡片（YlxwR18Card）、灵宠作用块、融合块、灵纹行（YlxwR18bRuneRow）、
    妖灵秘径行（YlxwR18ExpedRow）、点化/归位行（YlxwR18MiscRow）。
  · **仅动**「玩法说明」折叠块的第 ② 条（C4）——其余说明条目（① 进食 / ③ 培养 / ④ 妖灵之力 /
    ⑤ 收养 20000）与折叠块标题 `YlxwR79Box("\u5996\u7075"` 均**冻结不动**。
  · **保留** `[r189ui]` 给进食三档加的「· 今日首次免费」后缀（R-167 当日首免仍在，与新增的
    免费进食**独立共存**；是否由免费进食取代首免 = 待用户拍板，见 R-198 服务端环文件头 §一）。
  · 冻结针脚只钉本批**不动**的稳定形态；**绝不**钉 `[r180adv*]`/`[r185farm*]`/`[r184wudao]`/
    `[r187guide]`/`[r188med*]`/`[r190feed]`/`[r189ui]`/`[r189conv]`/`[r189rune]`/`[r192fuse]`/
    `[r193qy]`/`[r195away]`/`[r196rune]`。

==============================================================================
三、契约
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check）。
  · 就地替换 4 处（见 REPLACEMENTS）；每处打前断言 `count == 1`（锚点纯 ASCII，中文用 `\uXXXX` 六字符）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r198-<时刻>`。
  · 幂等：产物已含标记 `/*[r198free]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# 幂等标记（本批）
IDEMPOTENT_MARK = '/*[r198free]*/'

# ---- 退役针脚标记（0.9.36 起）----
# 语义：本环（R-198）**排在 R-200 之前**套用 ⇒ apply 时 `保留 r189ui 首免后缀` 针脚指的老形态**仍在**（count==1）；
#   而 R-200（0.9.36）已把 R-167「当日首次免费」整条移除（删进食按钮后缀 `\u4eca\u65e5\u9996\u6b21\u514d\u8d39`）
#   ⇒ 终态该串必须为 0。
# 单条 (needle, expect) 无法同时满足 apply 态(1) 与终态(0)，故退役 = **终态专用**：
#   · dryrun 读 gates() 在终态复核（期望 0，如实反映 R-200 移除后的形态）；
#   · 本环 apply/--check 时跳过（不检、不计 FAIL），避免「老补丁依赖新补丁」——终态形态由 R-200 自己的门禁负责。
RETIRED_TAG = '【已退役·终态专用】'

# --------------------------------------------------------------------------- 替换项
# ★ 形态约定：bundle 妖灵页签区域中文为**字面 `\uXXXX`**（六字符）⇒ 本 .py 源码保持纯 ASCII，
#   用 `\\uXXXX`（双反斜杠）写出，运行期字符串即 `\uXXXX`。

# ---- C1 YlxwR18PlayRows → 拆分出 YlxwR18FreeRow（免费进食 + 免费互动）+ 买额度行 ----
C1_OLD = (
    '/* ---------- D2 \\u4e92\\u52a8\\uff1a\\u4e09\\u79cd\\u5404 1 \\u6b21/\\u65e5\\u514d\\u8d39 + \\u4e70\\u989d\\u5ea6 2 \\u6b21/\\u65e5 ---------- */\n'
    'function YlxwR18PlayRows(t, m, f, u) {\n'
    '  var c = (t && t.consts) || {};\n'
    '  var pk = c.playKinds || {};\n'
    '  var q = (t && t.playQuota) || {};\n'
    '  var lvl = YlxwNum(m.level);\n'
    '  var tease = pk.tease || {}, brush = pk.brush || {}, talk = pk.talk || {};\n'
    '  var buyCost = YlxwNum(c.buyCost) || 20000;\n'
    '  var buyMax = YlxwNum(c.buyDailyMax) || 2;\n'
    '  var bought = YlxwNum(q.bought);\n'
    '  function lbl(k, d) {\n'
    '    if (lvl < YlxwNum(d.unlock)) return "\\uff08\\u9700 Lv" + YlxwNum(d.unlock) + "\\uff09";\n'
    '    if (YlxwNum(q[k]) >= 1) return "\\uff08\\u4eca\\u65e5\\u5df2\\u7528\\uff09";\n'
    '    if (d.extra === "hunger") return "\\uff08\\u7f81\\u7eca +5 \\u00b7 \\u5582\\u98df\\u5ea6 +" + YlxwNum(d.hunger) + "\\uff09";\n'
    '    if (d.extra === "exp") return "\\uff08\\u7f81\\u7eca +5 \\u00b7 \\u4fee\\u4e3a +" + YlxwNum(d.exp) + "\\uff09";\n'
    '    return "\\uff08\\u7f81\\u7eca +5\\uff09";\n'
    '  }\n'
    '  function dis(k, d) { return !!u || YlxwNum(q[k]) >= 1 || lvl < YlxwNum(d.unlock); }\n'
    '  var free = [\n'
    '    e.jsx("span", { className: "text-xs text-stone-400 w-12", children: "\\u4e92\\u52a8" }, "lbl"),\n'
    '    e.jsx(YlxwBtn, { tone: "ghost", disabled: dis("tease", tease),\n'
    '      onClick: function () { f("r18play-tease", "/pet/play", { kind: "tease" }, "\\u5df2\\u9017\\u5f04"); },\n'
    '      children: (tease.name || "\\u9017\\u5f04") + lbl("tease", tease) }, "tease"),\n'
    '    e.jsx(YlxwBtn, { tone: "ghost", disabled: dis("brush", brush),\n'
    '      onClick: function () { f("r18play-brush", "/pet/play", { kind: "brush" }, "\\u5df2\\u68b3\\u6bdb"); },\n'
    '      children: (brush.name || "\\u68b3\\u6bdb") + lbl("brush", brush) }, "brush"),\n'
    '    e.jsx(YlxwBtn, { tone: "ghost", disabled: dis("talk", talk),\n'
    '      onClick: function () { f("r18play-talk", "/pet/play", { kind: "talk" }, "\\u5df2\\u591c\\u8bdd"); },\n'
    '      children: (talk.name || "\\u591c\\u8bdd") + lbl("talk", talk) }, "talk"),\n'
    '  ];\n'
    '  var buy = ['
)
C1_NEW = (
    '/* ---------- D2a \\u514d\\u8d39\\u73a9\\u6cd5\\uff1a\\u514d\\u8d39\\u8fdb\\u98df\\uff08\\u6bcf\\u65e5 3 \\u6b21 \\u00b7 30 \\u5206\\u51b7\\u5374 \\u00b7 +100\\uff09+ \\u514d\\u8d39\\u4e92\\u52a8\\u4e09\\u79cd\\uff08\\u5404 1 \\u6b21/\\u65e5\\uff09 ---------- */\n'
    'function YlxwR18FreeRow(t, m, f, u) {\n'
    '  var c = (t && t.consts) || {};\n'
    '  var pk = c.playKinds || {};\n'
    '  var q = (t && t.playQuota) || {};\n'
    '  var lvl = YlxwNum(m.level);\n'
    '  var tease = pk.tease || {}, brush = pk.brush || {}, talk = pk.talk || {};\n'
    '  function lbl(k, d) {\n'
    '    if (lvl < YlxwNum(d.unlock)) return "\\uff08\\u9700 Lv" + YlxwNum(d.unlock) + "\\uff09";\n'
    '    if (YlxwNum(q[k]) >= 1) return "\\uff08\\u4eca\\u65e5\\u5df2\\u7528\\uff09";\n'
    '    if (d.extra === "hunger") return "\\uff08\\u7f81\\u7eca +5 \\u00b7 \\u5582\\u98df\\u5ea6 +" + YlxwNum(d.hunger) + "\\uff09";\n'
    '    if (d.extra === "exp") return "\\uff08\\u7f81\\u7eca +5 \\u00b7 \\u4fee\\u4e3a +" + YlxwNum(d.exp) + "\\uff09";\n'
    '    return "\\uff08\\u7f81\\u7eca +5\\uff09";\n'
    '  }\n'
    '  function dis(k, d) { return !!u || YlxwNum(q[k]) >= 1 || lvl < YlxwNum(d.unlock); }\n'
    '  var ff = (t && t.freeFeed) || {};\n'
    '  var ffMax = YlxwNum(c.freeFeedMax) || 3;\n'
    '  var ffHunger = YlxwNum(c.freeFeedHunger) || 100;\n'
    '  var ffLeft = (ff.left == null) ? ffMax : YlxwNum(ff.left);\n'
    '  var cdLeft = YlxwNum(ff.cdLeftMs);\n'
    '  var ffTxt = "\\u514d\\u8d39\\u8fdb\\u98df\\uff08\\u5582\\u98df\\u5ea6 +" + ffHunger + " \\u00b7 \\u5269\\u4f59 " + ffLeft + "/" + ffMax + " \\u6b21";\n'
    '  if (cdLeft > 0) ffTxt += " \\u00b7 \\u51b7\\u5374 " + Math.ceil(cdLeft / 60000) + " \\u5206";\n'
    '  ffTxt += "\\uff09";\n'
    '  return e.jsxs("div", { className: "space-y-2", children: [\n'
    '    e.jsx("div", { className: "text-xs text-amber-200 font-bold", children: "\\u514d\\u8d39\\u73a9\\u6cd5" }),\n'
    '    e.jsx("div", { className: "flex flex-wrap items-center gap-2", children: [\n'
    '      e.jsx("span", { className: "text-xs text-stone-400 w-12", children: "\\u514d\\u8d39\\u8fdb\\u98df" }),\n'
    '      e.jsx(YlxwBtn, { disabled: !!u || ffLeft <= 0 || cdLeft > 0,\n'
    '        onClick: function () { f("r18freefeed", "/pet/feed", { free: true }, "\\u5df2\\u514d\\u8d39\\u8fdb\\u98df \\u00b7 \\u5582\\u98df\\u5ea6 +" + ffHunger); },\n'
    '        children: ffTxt }),\n'
    '    ] }),\n'
    '    e.jsx("div", { className: "flex flex-wrap items-center gap-2", children: [\n'
    '      e.jsx("span", { className: "text-xs text-stone-400 w-12", children: "\\u4e92\\u52a8" }, "lbl"),\n'
    '      e.jsx(YlxwBtn, { tone: "ghost", disabled: dis("tease", tease),\n'
    '        onClick: function () { f("r18play-tease", "/pet/play", { kind: "tease" }, "\\u5df2\\u9017\\u5f04"); },\n'
    '        children: (tease.name || "\\u9017\\u5f04") + lbl("tease", tease) }, "tease"),\n'
    '      e.jsx(YlxwBtn, { tone: "ghost", disabled: dis("brush", brush),\n'
    '        onClick: function () { f("r18play-brush", "/pet/play", { kind: "brush" }, "\\u5df2\\u68b3\\u6bdb"); },\n'
    '        children: (brush.name || "\\u68b3\\u6bdb") + lbl("brush", brush) }, "brush"),\n'
    '      e.jsx(YlxwBtn, { tone: "ghost", disabled: dis("talk", talk),\n'
    '        onClick: function () { f("r18play-talk", "/pet/play", { kind: "talk" }, "\\u5df2\\u591c\\u8bdd"); },\n'
    '        children: (talk.name || "\\u591c\\u8bdd") + lbl("talk", talk) }, "talk"),\n'
    '    ] }),\n'
    '  ] }); ' + IDEMPOTENT_MARK + '\n'
    '}\n'
    '/* ---------- D2b \\u4e70\\u989d\\u5ea6\\uff1a3 \\u9009\\u9879\\u5171\\u7528\\u6bcf\\u65e5\\u4e0a\\u9650\\uff082\\u21925\\uff09 ---------- */\n'
    'function YlxwR18PlayRows(t, m, f, u) {\n'
    '  var c = (t && t.consts) || {};\n'
    '  var q = (t && t.playQuota) || {};\n'
    '  var buyCost = YlxwNum(c.buyCost) || 20000;\n'
    '  var buyMax = YlxwNum(c.buyDailyMax) || 5;\n'
    '  var bought = YlxwNum(q.bought);\n'
    '  var buy = ['
)

# ---- C2 买额度行：去掉对 free 的渲染（free 已搬入 FreeRow） ----
C2_OLD = (
    '  return e.jsxs("div", { className: "space-y-2", children: [\n'
    '    e.jsx("div", { className: "flex flex-wrap items-center gap-2", children: free }),\n'
    '    e.jsx("div", { className: "flex flex-wrap items-center gap-2", children: buy }),\n'
    '  ] });\n'
    '}'
)
C2_NEW = (
    '  return e.jsxs("div", { className: "space-y-2", children: [\n'
    '    e.jsx("div", { className: "flex flex-wrap items-center gap-2", children: buy }),\n'
    '  ] });\n'
    '}'
)

# ---- C3 Panel：免费玩法分组插到进食之前 ----
C3_OLD = (
    '    YlxwR18FeedRow(t, m, f, u),\n'
    '    YlxwR18PlayRows(t, m, f, u),'
)
C3_NEW = (
    '    YlxwR18FreeRow(t, m, f, u),\n'
    '    YlxwR18FeedRow(t, m, f, u),\n'
    '    YlxwR18PlayRows(t, m, f, u),'
)

# ---- C4 玩法说明②：过时文案（每日最多 2 次、未提免费进食）→ 如实反映本环后规则 ----
C4_OLD = (
    '"\\u2461 \\u4e92\\u52a8\\uff1a\\u9017\\u5f04\\uff08Lv.0\\uff09/ \\u68b3\\u6bdb\\uff08Lv.10\\uff0c\\u53e6 +20 '
    '\\u5582\\u98df\\u5ea6\\uff09/ \\u591c\\u8bdd\\uff08Lv.30\\uff0c\\u53e6 +200 \\u4fee\\u4e3a\\uff09\\uff0c\\u6bcf\\u79cd'
    '\\u6bcf\\u65e5\\u514d\\u8d39 1 \\u6b21\\u3001\\u5404 +5 \\u7f81\\u7eca\\uff1b\\u514d\\u8d39\\u6b21\\u6570\\u7528\\u5b8c'
    '\\u53ef\\u82b1 20000 \\u7075\\u77f3\\u4e70\\u989d\\u5ea6\\uff0c\\u6bcf\\u65e5\\u6700\\u591a 2 \\u6b21\\u3002"'
)
C4_NEW = (
    '"\\u2461 \\u514d\\u8d39\\u73a9\\u6cd5\\uff1a\\u514d\\u8d39\\u8fdb\\u98df +100 \\u5582\\u98df\\u5ea6 / '
    '\\u6bcf\\u65e5 3 \\u6b21 / \\u51b7\\u5374 30 \\u5206\\u949f\\uff08\\u514d\\u7075\\u77f3\\uff09\\uff1b'
    '\\u514d\\u8d39\\u4e92\\u52a8\\u2014\\u2014\\u9017\\u5f04\\uff08Lv.0\\uff09/ \\u68b3\\u6bdb\\uff08Lv.10\\uff0c\\u53e6 +20 '
    '\\u5582\\u98df\\u5ea6\\uff09/ \\u591c\\u8bdd\\uff08Lv.30\\uff0c\\u53e6 +200 \\u4fee\\u4e3a\\uff09\\uff0c\\u6bcf\\u79cd'
    '\\u6bcf\\u65e5\\u514d\\u8d39 1 \\u6b21\\u3001\\u5404 +5 \\u7f81\\u7eca\\u3002'
    '\\u4e92\\u52a8\\u514d\\u8d39\\u6b21\\u6570\\u7528\\u5b8c\\u53ef\\u82b1 20000 \\u7075\\u77f3\\u4e70\\u989d\\u5ea6\\uff0c'
    '3 \\u79cd\\u5171\\u7528\\u6bcf\\u65e5\\u6700\\u591a 5 \\u6b21\\u3002"'
)

REPLACEMENTS = [
    ('c1_freerow', C1_OLD, C1_NEW),
    ('c2_buy_only', C2_OLD, C2_NEW),
    ('c3_panel', C3_OLD, C3_NEW),
    ('c4_guide2', C4_OLD, C4_NEW),
]

# 冻结针脚（对**输入**校验）：本批不动的稳定形态（绝不含 [r180adv*]/[r185farm*]/[r184wudao]/
# [r187guide]/[r188med*]/[r190feed]/[r189ui]/[r189conv]/[r189rune]/[r192fuse]/[r193qy]/
# [r195away]/[r196rune]）。
FREEZE = [
    ('function YlxwR18Card(', 1),
    ('function YlxwR18FeedRow(', 1),
    ('function YlxwR18PlayRows(', 1),
    ('function YlxwR18ExpedRow(', 1),
    ('function YlxwR18MiscRow(', 1),
    ('function YlxwR18bRuneRow(', 1),
    ('function YlxwR18Panel(', 1),
    ('function YlxwPetShell(', 1),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    needle 可为 tuple（多形态合计计数）。"""
    return [
        # ---- 幂等标记 ----
        ('R198\u00b7\u5e42\u7b49\u6807\u8bb0 r198free', IDEMPOTENT_MARK, 1, '==', '[r198free] 恰 1 处'),
        # ---- 免费玩法分组 ----
        ('R198\u00b7\u514d\u8d39\u73a9\u6cd5\u5206\u7ec4\u6807\u9898',
         'children: "\\u514d\\u8d39\\u73a9\\u6cd5" })', 1, '==', '「免费玩法」标题'),
        ('R198\u00b7\u65b0\u51fd\u6570 YlxwR18FreeRow', 'function YlxwR18FreeRow(', 1, '==', '免费玩法行'),
        ('R198\u00b7Panel \u63d2\u5165 FreeRow', 'YlxwR18FreeRow(t, m, f, u),', 1, '==', 'Panel 子节点'),
        # ---- 免费进食 ----
        ('R198\u00b7\u514d\u8d39\u8fdb\u98df\u6309\u94ae\u6807\u7b7e',
         'children: "\\u514d\\u8d39\\u8fdb\\u98df" })', 1, '==', '「免费进食」行标签'),
        ('R198\u00b7\u514d\u8d39\u8fdb\u98df\u8bf7\u6c42',
         'f("r18freefeed", "/pet/feed", { free: true }', 1, '==', 'POST /pet/feed {free:true}'),
        ('R198\u00b7\u6d88\u8d39 freeFeed \u989d\u5ea6',
         'var ffLeft = (ff.left == null) ? ffMax : YlxwNum(ff.left);', 1, '==', '读服务端 freeFeed 回显'),
        ('R198\u00b7\u6d88\u8d39 consts \u5e38\u91cf',
         'var ffMax = YlxwNum(c.freeFeedMax) || 3;', 1, '==', '读服务端常量表'),
        # ---- 免费互动三按钮搬入（各恰好 1 处，防重复）----
        ('R198\u00b7\u4e92\u52a8\u9017\u5f04\u6070 1 \u5904',
         'f("r18play-tease", "/pet/play", { kind: "tease" }', 1, '==', '未重复'),
        ('R198\u00b7\u4e92\u52a8\u68b3\u6bdb\u6070 1 \u5904',
         'f("r18play-brush", "/pet/play", { kind: "brush" }', 1, '==', '未重复'),
        ('R198\u00b7\u4e92\u52a8\u591c\u8bdd\u6070 1 \u5904',
         'f("r18play-talk", "/pet/play", { kind: "talk" }', 1, '==', '未重复'),
        # ---- 买额度 2 -> 5 ----
        ('R198\u00b7\u4e70\u989d\u5ea6\u56de\u9000\u503c=5', 'buyMax = YlxwNum(c.buyDailyMax) || 5;', 1, '==', '回退值同步 5'),
        ('R198\u00b7\u4e70\u989d\u5ea6\u65e7\u56de\u9000\u503c 2 \u6e05\u96f6', 'buyMax = YlxwNum(c.buyDailyMax) || 2;', 0, '==', '旧值消失'),
        # ---- 旧形态清零 ----
        ('R198\u00b7\u65e7 free \u6e32\u67d3\u6e05\u96f6', 'children: free })', 0, '==', 'free 已搬入 FreeRow'),
        ('R198\u00b7\u65e7 var free \u6e05\u96f6', 'var free = [', 0, '==', 'free 数组已移走'),
        ('R198\u00b7\u65e7\u6807\u9898\u201c\u4e70\u989d\u5ea6 2 \u6b21\u201d\u6e05\u96f6',
         '\\u4e70\\u989d\\u5ea6 2 \\u6b21/\\u65e5', 0, '==', '旧注释已换'),
        # ---- 冻结针脚（本批不动的函数仍在）----
        ('R198\u00b7YlxwR18FeedRow \u672a\u52a8', 'function YlxwR18FeedRow(', 1, '==', '进食行未动'),
        ('R198\u00b7YlxwR18Card \u672a\u52a8', 'function YlxwR18Card(', 1, '==', '卡片未动'),
        ('R198\u00b7YlxwR18bRuneRow \u672a\u52a8', 'function YlxwR18bRuneRow(', 1, '==', '灵纹行未动'),
        ('R198\u00b7YlxwR18ExpedRow \u672a\u52a8', 'function YlxwR18ExpedRow(', 1, '==', '秘径行未动'),
        ('R198\u00b7YlxwR18MiscRow \u672a\u52a8', 'function YlxwR18MiscRow(', 1, '==', '点化/归位行未动'),
        ('R198\u00b7YlxwPetShell \u672a\u52a8', 'function YlxwPetShell(', 1, '==', '融合壳未动'),
        # ---- 既有 r189ui 首免后缀保留（本环不动进食文案）----
        ('R198\u00b7\u4fdd\u7559 r189ui \u9996\u514d\u540e\u7f00' + RETIRED_TAG, '\\u4eca\\u65e5\\u9996\\u6b21\\u514d\\u8d39', 0, '==',
         'R-200（0.9.36）已移除首免后缀 ⇒ 终态归 0；apply 态仍为 1 故本环跳过'),
        # ---- 玩法说明②：过时文案已修（买额度 2→5 + 免费玩法）----
        ('R198\u00b7\u8bf4\u660e\u2461\u5df2\u6539\u300c\u514d\u8d39\u73a9\u6cd5\u300d',
         '\\u2461 \\u514d\\u8d39\\u73a9\\u6cd5\\uff1a', 1, '==', '说明②新前缀「② 免费玩法：」'),
        ('R198\u00b7\u8bf4\u660e\u2461\u5df2\u5199 5 \u6b21',
         '3 \\u79cd\\u5171\\u7528\\u6bcf\\u65e5\\u6700\\u591a 5 \\u6b21\\u3002', 1, '==', '「3 种共用每日最多 5 次。」'),
        ('R198\u00b7\u8bf4\u660e\u2461\u63d0\u514d\u8d39\u8fdb\u98df',
         '\\u514d\\u8d39\\u8fdb\\u98df +100 \\u5582\\u98df\\u5ea6 / \\u6bcf\\u65e5 3 \\u6b21 / \\u51b7\\u5374 30 \\u5206\\u949f',
         1, '==', '免费进食 +100 / 每日 3 次 / 冷却 30 分钟'),
        ('R198\u00b7\u65e7\u300c\u6bcf\u65e5\u6700\u591a 2 \u6b21\u300d\u6e05\u96f6',
         '\\u6bcf\\u65e5\\u6700\\u591a 2 \\u6b21', 0, '==', '旧表述「每日最多 2 次」已清零'),
        # ---- 冻结其余说明条目（①②③④ 除 ② 外均未动）----
        ('R198\u00b7\u8bf4\u660e\u2460\u672a\u52a8', '\\u2460 \\u8fdb\\u98df\\uff1a\\u4e09\\u6863\\u7075\\u98df', 1, '==', '① 进食未动'),
        ('R198\u00b7\u8bf4\u660e\u2462\u672a\u52a8', '\\u2462 \\u57f9\\u517b\\uff1a\\u70b9\\u5316', 1, '==', '③ 培养未动'),
        ('R198\u00b7\u8bf4\u660e\u2463\u672a\u52a8', '\\u2463 \\u5996\\u7075\\u4e4b\\u529b', 1, '==', '④ 妖灵之力未动'),
        ('R198\u00b7\u8bf4\u660e\u2464\u672a\u52a8', '\\u2464 \\u6536\\u517b 20000', 1, '==', '⑤ 收养 20000 未动'),
        ('R198\u00b7\u8bf4\u660e\u5757 YlxwR79Box \u672a\u52a8', 'YlxwR79Box("\\u5996\\u7075"', 1, '==', '折叠块标题未动'),
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
        if RETIRED_TAG in label:
            # 退役针脚（终态专用）：本环 apply/--check 时 R-200 尚未套用，首免后缀仍在（count==1）⇒ 不检；
            # 终态由复核（期望 0）负责，终态形态由 R-200 自己的门禁负责。
            continue
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    """反向还原：把每个 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in reversed(REPLACEMENTS):
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('YL_NODE'), os.environ.get('NODE'), shutil.which('node'),
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


def _probe_freerow(patched_text):
    """从补丁后产物实抽 `function YlxwR18FreeRow(...) {...}`，node 复算结构（不依赖 React 运行时）。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。"""
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    m = re.search(r'function YlxwR18FreeRow\(t, m, f, u\) \{', patched_text)
    if not m:
        return False, 'YlxwR18FreeRow 未找到'
    # 截取该函数体（到下一个顶层 `\n}` 为止），做「结构探针」：把 e.jsx/e.jsxs/YlxwBtn/YlxwNum 打桩后实跑。
    start = m.start()
    end = patched_text.find('\n}\n', start)
    if end < 0:
        return False, 'YlxwR18FreeRow 函数体未闭合'
    body = patched_text[start:end + 3]
    js = (
        'var CLICKS = [];\n'
        'function stub(tag, props) { if (tag === YlxwBtn && props && props.onClick) CLICKS.push(props.children); return { tag: tag, props: props }; }\n'
        'function e() { return stub(arguments[0], arguments[1]); }\n'
        'e.jsx = function (tag, props) { return stub(tag, props); };\n'
        'e.jsxs = function (tag, props) { return stub(tag, props); };\n'
        'function YlxwBtn() {}\n'
        'function YlxwNum(v) { return Number(v) || 0; }\n'
        'function YlxwKv() {}\n'
        + body + '\n'
        'var calls = [];\n'
        'var f = function (key, url, body2, msg) { calls.push([key, url, body2]); };\n'
        'var T = { consts: { freeFeedMax: 3, freeFeedHunger: 100, playKinds: { tease:{name:"\\u9017\\u5f04",unlock:0,bond:5,extra:"none"}, brush:{name:"\\u68b3\\u6bdb",unlock:10,bond:5,extra:"hunger",hunger:20}, talk:{name:"\\u591c\\u8bdd",unlock:30,bond:5,extra:"exp",exp:200} }, playQuota:{tease:0,brush:0,talk:0,bought:0} }, freeFeed: { used:1, left:2, cdLeftMs:0, max:3, cdMs:1800000 } };\n'
        'var out = YlxwR18FreeRow(T, { level: 50 }, f, false);\n'
        'if (!out || out.tag !== "div") throw new Error("FreeRow 未返回 div");\n'
        'console.log("freerow>> children=" + out.props.children.length + " clicks=" + CLICKS.length);\n'
    )
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
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r198] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r198] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r198] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r198] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r198] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r198] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _probe_freerow(out)
    if ok is False:
        print('[r198] SELFTEST FAIL freerow-probe: ' + pmsg)
        return 1
    print('[r198] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s; %s'
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
        print('[r198] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r198] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r198] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r198] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r198] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r198] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            if RETIRED_TAG in label:
                print('    [SKIP] %s 已退役（终态由 R-200 门禁复核）' % label.replace(RETIRED_TAG, ''))
            else:
                print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r198-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r198] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        if RETIRED_TAG in label:
            print('    [SKIP] %s 已退役（终态由 R-200 门禁复核）' % label.replace(RETIRED_TAG, ''))
        else:
            print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
