# -*- coding: utf-8 -*-
r"""
yl_changelog_ext.py — 游戏内「更新日志」：**只给玩家看** + **完整不截断**

背景（用户需求，非台账 R-编号）
--------------------------------------------------------------------------
  用户原话：
    「游戏内的更新日志只给玩家看的内容，并且不要截断，保持完整从建游戏项目开始的所有更新日志。」

现状侦察（已实测，锚点见下）
--------------------------------------------------------------------------
  游戏内「更新日志」= 基线组件 CM（`CM=({isOpen:t,onClose:r})=>{...}`），
  由主页头部版本徽标 / 设置页「查看更新日志」按钮经 `YLChgOpen` 打开。
  它做三件事：

    1) fetch("/myxxz/CHANGELOG.md")            ← 读的是**开发者向** CHANGELOG.md
    2) $=v(T) 解析 → l($.slice(0,5))            ← **只保留最近 5 个版本**
    3) a.map(...) 逐版本渲染

  问题 ①：CHANGELOG.md 是写给开发者看的（含 R-编号 / 模块名 / 门禁条数 /
          产物包名 / md5 / 内部事故复盘）。玩家看到「3114 条门禁 FAIL 0」
          「index-v281111-20261001.js」毫无意义。
  问题 ②：`.slice(0,5)` 把历史截断成最近 5 版，与「完整历史」要求相悖。

方案选择（三选一，本项目选 **A**）
--------------------------------------------------------------------------
  A. 另建**玩家向** `CHANGELOG_PLAYER.md`，游戏内读它。  ← **本模块采用**
  B. 在 CHANGELOG.md 里给每条加「玩家向摘要」标记 —— 要动开发者日志格式，
     且每加一条都要双写，最容易漏。
  C. 客户端渲染时过滤技术行 —— 现 CHANGELOG 的每条 bullet **技术细节与玩家
     内容混在同一行**（例：`R-049 …；`R044_ADV_STONE_MUL` 3 → 0.85`），
     按行过滤根本滤不干净，必然漏。

  ⇒ 选 A：内容源头分离，客户端零过滤逻辑，最不容易漏。

  但**保留一条真实兜底**：玩家向文件尚未部署（404）时，回退读开发者向
  CHANGELOG.md —— 面板不至于白屏。此兜底同时**保住 `yl_version_ext.py`
  的两条既有门禁**（该模块断言 `"/myxxz/CHANGELOG.md"` 全文恰 2 处、
  `fetch("/myxxz/CHANGELOG.md")` 恰 1 处）；本模块**不得**破坏它们，
  故兜底串刻意写成 `fetch("/myxxz/CHANGELOG.md")` 的原样形态。

本模块动作（3 处就地替换，无注入块）
--------------------------------------------------------------------------
  ① 载入：`fetch("/myxxz/CHANGELOG.md")` → 先取玩家向文件，失败再回退。
  ② 不截断：`l($.slice(0,5))` → `l($)`（全量历史）。
  ③ 不刷屏：版本卡片 `<div>` → `<details open={T<3}>`，头部 `<div>` → `<summary>`。
     ⇒ 最近 3 版默认展开，更早版本折叠但**可点击展开**，30 版历史一屏可控、
       且一条不少。用原生 `<details>`，**不引入任何 hook / state**（避免动 CM
       顶部的 useState 行——那行是 `yl_version_ext.py` 的门禁锚点）。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 只新建本文件；不改 build_v26n.py / localtest/* / srv/index_v28.ts /
    deploy_v28/* / 其它 yl_*_ext.py。
  · 锚点全 ASCII、实测唯一（见下 expect）。
  · 无 INJECT_JS ⇒ 天然不含 V28_BAN_PATTERNS；替换串里亦无 fetch 新增外联。
  · 不碰 `CM=({isOpen:t,onClose:r})=>` 之后那行 `useState`（version 模块锚点）。
  · 不碰解析器 v(T)、不碰当前版本判定 `b.version)===u`、不碰 `YLChgOpen` 开关。
  · 需要主控：把本模块接进 V28_MODULES，并把 CHANGELOG_PLAYER.md 纳入部署。
"""

# 本模块只做「就地替换」，不需要注入块。
INJECT_JS = ''

# --------------------------------------------------------------------------- 锚点
# 锚点均为纯 ASCII；`<`、`$`、反引号都是产物里的字面字符（Python 原样字符串）。

# ① 载入 + 截断（@1698690 count=1）：开发者向路径 + slice(0,5)
FETCH_OLD = (
    'const x=await fetch("/myxxz/CHANGELOG.md");'
    'if(!x.ok)throw new Error("Failed to fetch changelog");'
    'const T=await x.text(),$=v(T);l($.slice(0,5))'
)
# 玩家向优先 + 开发者向兜底；去掉 slice
FETCH_NEW = (
    'const x=await fetch("/myxxz/CHANGELOG_PLAYER.md")'
    '.then(function(r){return r&&r.ok?r:fetch("/myxxz/CHANGELOG.md")});'
    'if(!x.ok)throw new Error("Failed to fetch changelog");'
    'const T=await x.text(),$=v(T);l($)'
)

# ② 版本卡片容器（count=1）：div → details（open = 最近 3 版）
CARD_OLD = (
    'a.map((x,T)=>e.jsxs("div",{className:`border rounded-lg overflow-hidden '
    '${T===0&&S?"border-green-700/50 bg-green-900/10":"border-stone-700 bg-stone-900/30"}`'
    ',children:['
)
CARD_NEW = (
    'a.map((x,T)=>e.jsxs("details",{open:T<3,className:`border rounded-lg overflow-hidden '
    '${T===0&&S?"border-green-700/50 bg-green-900/10":"border-stone-700 bg-stone-900/30"}`'
    ',children:['
)

# ③ 版本头（count=1）：div → summary（可点击折叠 / 展开）
HEAD_OLD = (
    'children:[e.jsx("div",{className:"bg-stone-800/50 border-b border-stone-700 px-4 py-3"'
    ',children:e.jsxs("div",{className:"flex items-center justify-between",'
)
HEAD_NEW = (
    'children:[e.jsx("summary",{className:"bg-stone-800/50 border-b border-stone-700 px-4 py-3 '
    'cursor-pointer select-none",children:e.jsxs("div",{className:"flex items-center justify-between",'
)


def apply(p, ctx):
    zh = ctx['zh']

    # 纯 ASCII 自检：锚点/替换串都不该含非 ASCII（本模块不经 zh()）
    for tag, s in (('FETCH_OLD', FETCH_OLD), ('FETCH_NEW', FETCH_NEW),
                   ('CARD_OLD', CARD_OLD), ('CARD_NEW', CARD_NEW),
                   ('HEAD_OLD', HEAD_OLD), ('HEAD_NEW', HEAD_NEW)):
        assert all(ord(c) < 128 for c in s), 'rchg %s 含非 ASCII，锚点必须纯 ASCII' % tag

    p.replace('rchg-player-fetch', FETCH_OLD, FETCH_NEW, expect=1,
              note='游戏内更新日志改读玩家向 CHANGELOG_PLAYER.md（开发者向留作兜底），并去掉 slice(0,5)')
    p.replace('rchg-card-details', CARD_OLD, CARD_NEW, expect=1,
              note='版本卡片改为 <details open={T<3}>：最近 3 版展开、更早折叠可展开')
    p.replace('rchg-head-summary', HEAD_OLD, HEAD_NEW, expect=1,
              note='版本头改为 <summary>：原生折叠开关，不引入 hook')

    gates = [
        # ================= 本模块改动 =================
        ('Rchg·玩家向日志入口',      '"/myxxz/CHANGELOG_PLAYER.md"',                       1, '==', '游戏内读玩家向日志'),
        ('Rchg·开发者向兜底仍在',    'fetch("/myxxz/CHANGELOG.md")',                       1, '==', '玩家向文件缺失时回退；同时是 version 模块门禁'),
        ('Rchg·旧路径串仍共 2 处',   '"/myxxz/CHANGELOG.md"',                              2, '==', 'version INJECT 1 + 本模块兜底 1，勿破坏 yl_version_ext 门禁'),
        ('Rchg·截断已移除',          'l($.slice(0,5))',                                   0, '==', '旧形态清零'),
        ('Rchg·全量历史载入',        'v(T);l($)',                                         1, '==', '不再 slice(0,5)'),
        ('Rchg·按版本折叠(details)', 'e.jsxs("details",{open:T<3,',                       1, '==', '最近 3 版展开，更早折叠可展开'),
        ('Rchg·折叠头(summary)',     'e.jsx("summary",{className:"bg-stone-800/50',       1, '==', '原生折叠开关'),
        ('Rchg·旧版本卡片已清零',    'a.map((x,T)=>e.jsxs("div",{className:`border rounded-lg overflow-hidden', 0, '==', '旧形态'),
        ('Rchg·旧版本头已清零',      'e.jsx("div",{className:"bg-stone-800/50 border-b border-stone-700 px-4 py-3"', 0, '==', '旧形态'),
        # ================= 冻结：别动别人的面 =================
        ('冻结·CM 解析器未动',       'const f=async()=>{d(!0);try{const x=await fetch',    1, '==', 'version 模块门禁锚点'),
        ('冻结·当前版本判定未动',    'b.version)===u',                                    1, '==', ''),
        ('冻结·面板开关未动',        'YLChgOpen',                                         2, '==', ''),
        ('冻结·版本弹窗动态版本未动', 'u=YlxwVersionGet();',                              1, '==', 'yl_version_ext 门禁锚点'),
        ('冻结·version helper 未动', 'function YlxwVersionLoad(',                         1, '==', ''),
    ]
    return gates
