# -*- coding: utf-8 -*-
r"""
yl_r074_ext.py — R-074 妖灵「进食按钮 UI 没对齐」（纯 CSS/布局修复）

需求原文（用户）
--------------------------------------------------------------------------
  「仙务·妖灵 进食的按钮 ui 没有对齐。」

根因（产物 @1385xxx 区，`YlxwR18FeedRow` 的 return，实测原文）
--------------------------------------------------------------------------
      return e.jsxs("div", { className: "flex flex-wrap items-center gap-2", children:
        [e.jsx("span", { className: "text-xs text-stone-400 w-12", children: "进食" })].concat(btns) });
  ⇒ 标签 span(`w-12`) 与 3 个按钮是**同一个** `flex flex-wrap` 的直接子项。
  · 三档按钮文案长度差异很大（「凡品·青草露（5000 灵石 · 喂食度 +30）」
    vs「仙品·九转灵丹（100000 灵石 · 喂食度 +600）」），一行放不下时 `flex-wrap` 会把
    最后一个按钮**换到第二行**；而换行后它从**容器左边缘**起排（x≈0，落在「进食」标签下方），
    第一行按钮却从标签之后起排（x≈56）⇒ 两行按钮左边不对齐。
  · 同面板的「互动 / 秘径 / 点化」行按钮文案短，几乎不换行，所以只有「进食」这一行露馅。

修法（只用**产物 CSS 里已存在**的 Tailwind 类；已逐个 grep 确认，见下）
--------------------------------------------------------------------------
  把 3 个按钮从「行容器的直接子项」改为「标签之后的**一个独立分组**」，分组用栅格三列等宽：
      ...children: "进食" }), e.jsx("div", { className: "grid grid-cols-1 sm:grid-cols-3 gap-2 flex-1 min-w-0", children: btns })] });
  为什么能对齐：
    · `grid-cols-3`（`repeat(3, minmax(0,1fr))`）⇒ 三列**等宽**，按钮作为栅格项默认 stretch
      填满各自列 ⇒ 三按钮左右边缘严格对齐，不再长短不一。
    · `flex-1`（`flex:1 1 0%`）⇒ 分组占满「进食」标签之后的整行宽度，三列才真正等分；
      `min-w-0` 解除栅格项的最小内容宽度下限，窄屏时可继续收缩而不撑破。
    · `grid-cols-1 sm:grid-cols-3` ⇒ 窄屏（<640px）退化成单列纵向堆叠（按钮仍整宽、可读），
      ≥640px 才是三列等宽；避免小屏被强行挤成三窄列。
    · `flex flex-wrap items-center gap-2` 保留在外层（标签与分组之间仍是 flex 行，标签照旧 `w-12`）。

CSS 证据（预生成产物 `build/assets/index-ZuV-l8Gt.css`，逐类 grep 命中）
--------------------------------------------------------------------------
    .grid{display:grid}
    .grid-cols-1{grid-template-columns:repeat(1,minmax(0,1fr))}
    .sm\:grid-cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}
    .gap-2{gap:calc(var(--spacing)*2)}
    .flex-1{flex:1}
    .min-w-0{min-width:calc(var(--spacing)*0)}
  ⇒ 全部已存在，无新造 class（新造 class 在预生成 CSS 里不会生效）。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 锚点纯 ASCII（`.concat(btns) });`，实测全仓 count==1），replace 带 expect=1。
  · 不删任何被 r018 / r045 门禁冻结的串：
      `function YlxwR18FeedRow(t, m, f, u) {` / `f("r18feed-" + k, "/pet/feed", { tier: k }` 原样保留。
  · INJECT_JS 为空 ⇒ 天然不含 V28_BAN_PATTERNS。
  · 只新建本文件；不改 build_v26n.py / localtest/* / srv/index_v28.ts / deploy_v28/*。
  · ★ 接线顺序：必须排在 `r018` 之后（锚在其注入块内）。建议紧接 `r073` 之后、`numbal` 之前。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = ''          # 本模块只做「就地替换」，不注入任何新代码

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# 进食行的收尾：`[标签].concat(btns) });`（全仓唯一 —— 只有进食行用 .concat(btns)）
FEED_TAIL_OLD = '].concat(btns) });'

# 新形态：标签之后追加一个「栅格三列等宽」按钮分组（不改标签、不改按钮本身、不改端点）
FEED_TAIL_NEW = (
    ', e.jsx("div", { className: '
    '"grid grid-cols-1 sm:grid-cols-3 gap-2 flex-1 min-w-0", children: btns })] });'
)

# 门禁串
FEED_GRID_GATE = ('e.jsx("div", { className: '
                  '"grid grid-cols-1 sm:grid-cols-3 gap-2 flex-1 min-w-0", children: btns })')


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 r018）；
    ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检 0：本模块刻意零注入（顺带证明不含 V28_BAN_PATTERNS）
    if INJECT_JS != '':
        raise AssertionError('r074 本应零注入，INJECT_JS 非空')

    # 自检 1：锚点/替换串手滑护栏
    if 'concat(btns)' not in FEED_TAIL_OLD or 'grid-cols-1 sm:grid-cols-3' not in FEED_TAIL_NEW:
        raise AssertionError('r074 锚点/替换串异常：未命中进食行收尾')

    # 唯一一处就地替换：进食按钮改「标签 + 栅格三列等宽分组」
    p.replace('r074-feed-grid', FEED_TAIL_OLD, FEED_TAIL_NEW, expect=1,
              note='进食三档按钮改栅格三列等宽（grid-cols-1 sm:grid-cols-3），修换行错位')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本模块改动 =================
        ('R74·进食按钮已改栅格三列等宽', FEED_GRID_GATE, 1, '==',
         'grid-cols-1 sm:grid-cols-3 gap-2 flex-1 min-w-0（全部已在预生成 CSS 中）'),
        ('R74·分组已占满标签后整行', 'gap-2 flex-1 min-w-0", children: btns })', 1, '==',
         'flex-1 撑满剩余宽度 ⇒ 三列真正等分；min-w-0 允许收缩'),
        ('R74·旧「标签与按钮同层」已清零', '].concat(btns) });', 0, '==',
         '旧形态：3 按钮与标签同属一个 flex-wrap ⇒ 换行后落在标签下方'),
        ('R74·窄屏单列退化', 'grid-cols-1 sm:grid-cols-3 gap-2 flex-1 min-w-0', 1, '==',
         '<640px 单列堆叠，≥640px 三列等宽（基座另有 gap-3 的同类串，故此处带 gap-2 消歧）'),
        # ================= 未动面（冻结） =================
        ('冻结·r018 进食行签名未动', 'function YlxwR18FeedRow(t, m, f, u) {', 1, '==', 'r018/r045 门禁面'),
        ('冻结·r018 进食端点未动', 'f("r18feed-" + k, "/pet/feed", { tier: k }', 1, '==', ''),
        ('冻结·r018 进食三档 key 未动', 'var keys = ["common", "fine", "immortal"];', 1, '==', ''),
        ('冻结·r018 面板签名未动', 'function YlxwR18Panel(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 妖灵卡签名未动', 'function YlxwR18Card(t, m) {', 1, '==', ''),
        ('冻结·r018 互动三选未动', 'function YlxwR18PlayRows(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 秘径行未动', 'function YlxwR18ExpedRow(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 点化归位行未动', 'function YlxwR18MiscRow(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 妖灵面板未整体重写', 'function YlxwTPet() {', 1, '==', ''),
        ('冻结·战斗结算核心未动', 'YlxwBattleBonus(t),YlxwDOD=', 1, '==', ''),
        ('R74·未新增仙途任务', 'QUEST_DEFS', 0, '==', '本环不碰任务'),
    ]
    return gates
