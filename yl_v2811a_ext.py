# -*- coding: utf-8 -*-
r"""yl_v2811a_ext.py -- 「秘境探索」弹窗显示服务端权威每日次数（0.8.11 · 客户端单模块）

## 为什么有这一环

0.8.5（`yl_dungeon085_ext.py`）已经把秘境「每日 3 次 + 30s CD」真正接到服务端账本：
    · GET  /api/dungeon/status   -> { date, count, cap, remaining, cdLeftMs, canEnter }
    · POST /api/dungeon/entry    -> 200 / 403（cap|cd）
并导出了四个可复用函数：`YlxwDungeonToday` / `YlxwDungeonMarkLocal` /
`YlxwDungeonStatusSync`（读 status 并回灌 `window.__ylDg`）/ `YlxwDungeonEntryGate`（入口门禁）。

但那批改动只把 `YlxwDungeonStatusSync()` 挂在了**地宫 Roguelike 弹窗**打开时：

    O.useEffect(()=>{t&&YlxwDungeonStatusSync()},[t])      ← 只有 `vk`（地宫）有

**「秘境探索」弹窗（组件 `cM`）从未拉过** ⇒ 玩家在这个弹窗里既看不到今天还能进几次，
也看不到冷却剩余，只能点了「进入秘境」被服务端 403 顶回来才知道次数用完了。

本模块补齐：弹窗打开时同步一次，并在内容区顶部常驻一条权威次数条；「刷新」按钮顺带刷新次数。

## 改动（3 处，锚点互不重叠；零新增网络调用）

| # | 锚点 | 改动 |
|---:|---|---|
| 1 | `cM` 头部 `const[c,d]=O.useState(0),` | 追加 `[YLXW_DGS,ylxwSetDgs]` state + `ylxwDgRefresh` 闭包（同一条 const 声明内） |
| 2 | 标题栏「刷新」按钮 `v=()=>{d(m=>m+1)};` | ① 按钮内追加 `ylxwDgRefresh()`；② 紧随其后追加 `O.useEffect(()=>{t&&ylxwDgRefresh()},[t,ylxwDgRefresh]);` |
| 3 | 内容网格 `children:[` 之后 | 插入 `col-span-full` 次数条（今日次数 / 剩余 / 冷却 / 用尽 / 未登录占位） |

★ **复用而非新建**：次数全部来自 0.8.5 的 `YlxwDungeonStatusSync()`；
本模块**不新增任何 `fetch`**、不新增端点、不新增常量、服务端零改动。

★ **为什么不用 `Xc()` / `YlxwPost()`**：与 0.8.5 同因 —— `/dungeon/entry` 用 403 表达
「次数用完 / 太频繁」，而 `Xc` 把 403 当会话失效**强制登出玩家**。本模块只读
`/dungeon/status`（GET，不会 403），且走 dg085 已封装的原始 fetch 路径，不重复造轮子。

## ★ 两个注入点为什么这样选（踩过的坑）

1. **不能用 `insert_before` 往 `cM` 前面插 Hook。**
   `cM` 所在语句的起点是 `},oM=Rt.memo(lM),cM=(…)` —— `insert_before` 落在
   `,cM=` 之前 = **同一条语句内**，Hook 会在**模块加载时无条件执行**一次，
   而且拿不到 `t`（isOpen）。故本模块改用 `replace` **原地扩写 `cM` 的函数体头部**。
2. **Hook 必须写在 `const` 声明闭合之后。**
   `cM` 的形参体是 `{const[c,d]=O.useState(0),u=…,f=…,v=…;return e.jsx(ct,{…})}`
   —— 若把 `O.useEffect(…)` 塞进 const 列表中间（如 `…useCallback(…);O.useEffect(…),u=…`），
   会提前闭合语句并把 `u=O.useMemo(…)` 变成**逗号表达式里的裸赋值**（严格模式直接 ReferenceError）。
   故第 2 处改动挂在 `v=…;` 这个**唯一的分号**之后。

## 硬约束遵守

  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/auth_token/X-YL-）。
  · 每个 replace 带 expect=精确次数；`apply()` 返回门禁五元组列表。
  · ★ 坑 2：门禁 needle 落在注入块内 ⇒ 一律写 zh() 之后的**转义形态**（本文件用 `r'...'`）。
  · ★ 坑 26：全部锚点实测 count==1；不动 dg085 / yl_v2810h / t8mentor 依赖的既有 needle。
"""

import re

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# 1) `cM` 函数体头部：`const[c,d]=O.useState(0),` 之后追加 state 与刷新闭包
A1 = 'cM=({isOpen:t,onClose:r,player:a,onEnter:l})=>{const[c,d]=O.useState(0),'

HEAD_JS = (
    '[YLXW_DGS,ylxwSetDgs]=O.useState(null),'
    'ylxwDgRefresh=O.useCallback(()=>{YlxwDungeonStatusSync().then(s=>{s&&ylxwSetDgs(s)})},[]),'
)

# 2) 标题栏「刷新」按钮 + 紧随其后的 `;`（const 声明唯一闭合处）→ 挂 useEffect
A2 = 'f=m=>fe.indexOf(m),v=()=>{d(m=>m+1)};return e.jsx(ct,{xw:"dungeon",'

EFFECT_JS = 'O.useEffect(()=>{t&&ylxwDgRefresh()},[t,ylxwDgRefresh]);'

A2_NEW = (
    'f=m=>fe.indexOf(m),v=()=>{d(m=>m+1);ylxwDgRefresh()};'
    + EFFECT_JS
    + 'return e.jsx(ct,{xw:"dungeon",'
)

# 3) 内容网格 `children:[` 之后插入次数条（成为网格第一个子元素，col-span-full 通栏）
A3 = ('children:e.jsxs("div",{className:"grid grid-cols-1 md:grid-cols-2 '
      'lg:grid-cols-3 gap-3 md:gap-6",children:[')

BAR_JS = (
    r'e.jsxs("div",{className:"col-span-full flex flex-wrap items-center gap-x-3 gap-y-1 '
    r'px-3 py-2 rounded-lg bg-purple-950/40 border border-purple-900/70 text-xs md:text-sm",'
    r'children:['
    # 标题
    r'e.jsx("span",{className:"text-purple-300 font-bold",children:"\u4eca\u65e5\u79d8\u5883\u6b21\u6570"}),'
    # x / cap（用尽时转红）
    r'e.jsxs("span",{className:"font-mono font-bold "'
    r'+(YLXW_DGS&&YLXW_DGS.remaining<=0?"text-rose-400":"text-emerald-300"),'
    r'children:[YLXW_DGS?YLXW_DGS.count:"\u2014"," / ",YLXW_DGS?YLXW_DGS.cap:3]}),'
    # 剩余
    r'YLXW_DGS&&YLXW_DGS.remaining>0?e.jsx("span",{className:"text-stone-400",'
    r'children:"\u5269\u4f59 "+YLXW_DGS.remaining+" \u6b21"}):null,'
    # 冷却
    r'YLXW_DGS&&YLXW_DGS.cdLeftMs>0?e.jsx("span",{className:"text-amber-300",'
    r'children:"\u51b7\u5374\u4e2d\uff0c\u7ea6 "+Math.ceil(YLXW_DGS.cdLeftMs/1000)'
    r'+" \u79d2\u540e\u53ef\u518d\u8fdb"}):null,'
    # 用尽
    r'YLXW_DGS&&YLXW_DGS.remaining<=0?e.jsx("span",{className:"text-rose-400",'
    r'children:"\u4eca\u65e5\u6b21\u6570\u5df2\u7528\u5b8c\uff0c\u660e\u65e5 0 \u70b9\u6062\u590d"}):null,'
    # 未登录 / 拉取失败占位
    r'!YLXW_DGS?e.jsx("span",{className:"text-stone-500",'
    r'children:"\uff08\u767b\u5f55\u540e\u663e\u793a\u670d\u52a1\u7aef\u6743\u5a01\u6b21\u6570\uff09"}):null'
    r']}),'
)

# build_v26n 侧会对本串做「zh() 后纯 ASCII」+ 禁词表断言
INJECT_JS = BAR_JS + '\n' + HEAD_JS + '\n' + EFFECT_JS


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含改名 + 全部前置 v28 模块，含 dg085）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('v2811a 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 1) `cM` 头部：追加次数 state + 刷新闭包（原地扩写，不新增语句）
    p.replace('v2811a-head', A1, A1 + HEAD_JS, expect=1,
              note='cM 内追加 [YLXW_DGS,ylxwSetDgs] state 与 ylxwDgRefresh 闭包')

    # 2) 「刷新」按钮顺带刷新次数 + 在 const 声明闭合后挂 useEffect（打开即同步）
    p.replace('v2811a-refresh', A2, A2_NEW, expect=1,
              note='刷新按钮追加 ylxwDgRefresh()，并在 v=…; 之后挂 O.useEffect')

    # 3) 内容网格顶部插入权威次数条
    p.insert_after('v2811a-bar', A3, BAR_JS, expect=1,
                   note='秘境弹窗内容区顶部插入「今日秘境次数 x/3 + 剩余 + 冷却」通栏')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- 改动 1：state + 闭包 ----
        ('V11·次数 state 已加',        '[YLXW_DGS,ylxwSetDgs]=O.useState(null)',  1, '==', ''),
        ('V11·刷新闭包已建',           'ylxwDgRefresh=O.useCallback(()=>{YlxwDungeonStatusSync().then(s=>{s&&ylxwSetDgs(s)})},[])', 1, '==', ''),
        ('V11·刷新闭包只建一次',        'ylxwDgRefresh=O.useCallback(',            1, '==', ''),
        # ---- 改动 2：按钮 + effect ----
        ('V11·刷新按钮顺带拉次数',      'v=()=>{d(m=>m+1);ylxwDgRefresh()}',       1, '==', ''),
        ('V11·打开即同步 effect',       'O.useEffect(()=>{t&&ylxwDgRefresh()},[t,ylxwDgRefresh]);', 1, '==', ''),
        ('V11·effect 挂在 const 之后',  'ylxwDgRefresh()};O.useEffect(()=>{t&&ylxwDgRefresh()},[t,ylxwDgRefresh]);return', 1, '==', '★ 不能插在 const 列表中间'),
        # ---- 改动 3：次数条 ----
        ('V11·次数条已插入',           'col-span-full flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 rounded-lg bg-purple-950/40', 1, '==', ''),
        ('V11·次数条在网格首位',        'gap-3 md:gap-6",children:[e.jsxs("div",{className:"col-span-full flex flex-wrap', 1, '==', ''),
        ('V11·标题（转义）',            r'className:"text-purple-300 font-bold",children:"\u4eca\u65e5\u79d8\u5883\u6b21\u6570"}', 1, '==', '★ 不能用裸「今日秘境次数」——dg085 的 403 文案里也有这 6 个字'),
        ('V11·次数读 count/cap',        r'children:[YLXW_DGS?YLXW_DGS.count:"\u2014"," / ",YLXW_DGS?YLXW_DGS.cap:3]', 1, '==', ''),
        ('V11·剩余文案（转义）',         r'\u5269\u4f59 "+YLXW_DGS.remaining+" \u6b21', 1, '==', ''),
        ('V11·冷却文案（转义）',         r'\u51b7\u5374\u4e2d\uff0c\u7ea6 ',       1, '==', ''),
        ('V11·冷却读 cdLeftMs',         'YLXW_DGS.cdLeftMs>0?e.jsx("span"',      1, '==', ''),
        ('V11·用尽文案（转义）',         r'\u4eca\u65e5\u6b21\u6570\u5df2\u7528\u5b8c\uff0c\u660e\u65e5 0 \u70b9\u6062\u590d', 1, '==', ''),
        ('V11·未登录占位（转义）',       r'\uff08\u767b\u5f55\u540e\u663e\u793a\u670d\u52a1\u7aef\u6743\u5a01\u6b21\u6570\uff09', 1, '==', ''),
        ('V11·用尽时数值转红',          'YLXW_DGS.remaining<=0?"text-rose-400":"text-emerald-300"', 1, '==', ''),
        # ---- 复用而非新建（本模块零新增网络调用） ----
        ('V11·复用 dg085 同步函数',      'YlxwDungeonStatusSync',                  3, '==', '定义 1 + 地宫弹窗 1 + 秘境弹窗 1'),
        ('V11·未新增 status 端点常量',   '"/dungeon/status"',                      2, '==', 'dg085 常量 1 + 手札面板 1；本模块不新增'),
        ('V11·未自造 fetch 调用',        'fetch(Nd(ln + YLXW_DG_ENTRY)',           1, '==', '仅 dg085 入口那处'),
        ('V11·未误用 YlxwPost 打入口',   'YlxwPost(YLXW_DG_ENTRY',                 0, '==', '403 会被 Xc 当会话失效强制登出'),
        ('V11·未新增秘境入口 gate',      '=await YlxwDungeonEntryGate();',         2, '==', '仍只有 dg085 的两处（经典 + 地宫）'),
        # ---- 基线保护 ----
        ('基线·秘境弹窗挂载未动',        'e.jsx(cM,{isOpen:d.isRealmOpen',         1, '==', ''),
        ('基线·地宫弹窗同步仍在',        'O.useEffect(()=>{t&&YlxwDungeonStatusSync()},[t])', 1, '==', 'dg085 E6-3，不得被覆盖'),
        ('基线·cM 原 useState 保留',     'const[c,d]=O.useState(0),',              1, '==', ''),
        ('基线·cM 原 useMemo 保留',      'u=O.useMemo(()=>J4(a.realm,6),[a.realm,c])', 1, '==', ''),
        ('基线·秘境刷新按钮原逻辑保留',   'd(m=>m+1)',                              1, '==', ''),
        ('基线·秘境标题未动',            'title:"秘境探索"',                        1, '==', ''),
        ('基线·秘境标题图标未动',        'titleIcon:e.jsx(Pb,{size:18',            1, '==', ''),
        ('基线·地宫入口未动',            'm("isDungeonOpen",!0),m("isRealmOpen",!1)', 1, '==', ''),
        ('基线·dg085 门禁助手未动',       'async function YlxwDungeonEntryGate() {', 1, '==', ''),
        ('基线·dg085 回灌函数未动',       'function YlxwDungeonMarkLocal(count) {', 1, '==', ''),
        ('基线·dg085 状态常量未动',       'var YLXW_DG_STATUS = "/dungeon/status";', 1, '==', ''),
        ('基线·秘境手札仍读 status',      'YlxwUseList("/dungeon/status")',         1, '==', ''),
        ('基线·YLXW_COMP 原项仍在',      'stats: YlxwTStats }',                    1, '==', 'build_v26n:896 / t8:382 的 needle'),
    ]
    return gates
