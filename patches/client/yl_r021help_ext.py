# -*- coding: utf-8 -*-
r"""
yl_r021help_ext.py — R-021「挂机收益 · 玩法说明」客户端单模块

需求原文（用户）
--------------------------------------------------------------------------
  「挂机收益这一个功能到底是在哪里获得数据，我每次玩这里都是 0，也领取不了，
    没有内容的变化，不知道从哪里玩，如果自带有设计，把玩法说明加上」

现状（审计 2026-09-30）
--------------------------------------------------------------------------
  组件 `YlxwTOffline` 全仓**零个模块改过**（`grep -l YlxwTOffline *.py` = 0）。
  它只做：`YlxwUseList("/offline/report")` → 渲染 7 个 KV（境界/层数/小时/修为可领/
  灵石可领/可领取/已封顶）+ 一个「领取」按钮（POST /offline/claim）⇒ 玩家完全看不出
  「收益从哪来 / 怎么才算离线 / 为什么恒为 0」。

服务端真实规则（逐字读 srv/index_v28.ts，本模块文案的唯一依据）
--------------------------------------------------------------------------
  · 锚点：`offlineAnchor()` —— 优先取客户端上报的真实「离开时刻」`saves.last_seen_at`
    （由 `POST /api/session/presence {state:'away'}` 写入，客户端在
     visibilitychange(hidden)/pagehide/beforeunload 触发）；缺失或已被领取覆盖时
     **逐位回落**存档时间 `updated_at`。窗口末端：已上报「回来」(`last_resume_at`)
     ⇒ 用回来时刻封口；否则 = nowMs。
    ⇒ **页面一直开着不操作 = 没有 away 事件 ⇒ 锚点回落 updated_at（心跳存档每 10s 刷）
      ⇒ 窗口恒 ≈10s < 门槛 ⇒ 面板恒 0**（这正是用户「每次都是 0」的根因，已由
      offline2 环修复为「真实离开时刻」口径）。
  · 门槛：`OFFLINE_MIN_MS = 5 * 60 * 1000` —— 离线不足 **5 分钟**收益归零。
  · 速率：`OFFLINE_RATE_BASE_PER_HOUR = 0.0048`（无月卡，=0.48%/小时当层修为槽）；
          `OFFLINE_RATE_MONTHCARD_PER_HOUR = 0.006`（月卡，0.6%/小时）。
  · 上限：`OFFLINE_CAP_HOURS_BASE = 8`（无月卡）/ `OFFLINE_CAP_HOURS_MONTHCARD = 12`；
          `capped = rawHours > cap` ⇒ 面板「已封顶=是」表示**超出部分不结算**（上限内仍可领）。
  · 收益：`offlineRewards()` —— 修为 = `floor(当层修为槽 × 速率 × 有效小时)`，
          并**钳在槽内**（`min(..., slot - cur)`）⇒ **当前层修为已满时 expGain=0 ⇒
          stonesGain=0 ⇒ claimable=false ⇒ 领不了**（需先消耗/突破）。
          灵石 = `floor(修为 × OFFLINE_STONE_RATIO)`（=10%）。
  · 领取：`POST /api/offline/claim` —— 守卫推进 `saves.offline_claimed_until`
          （已领过的段再领 → 409「该段离线收益已领取」）；成功后修为+灵石直接入档，
          并发一封「闭关修炼 · 离线收益」回执邮件。
  · report 响应还带只读字段：`capHours / ratePerHourPct / stoneRatio / monthCard /
    capped / claimable / hours / breakthrough`（本模块文案**全部取自这些真实字段**，
    不写死数值）。

改法（1 处注入 + 1 处就地替换）
--------------------------------------------------------------------------
  E1 在 `function YlxwTOffline() {` 之前注入 `YlxwOfflineHelp(t)`（原生 `<details>` 折叠块，
     零新依赖、零网络、零副作用）。
  E2 把面板里的**单节点** `e.jsx(YlxwKv, {...})` 包成
     `e.jsxs(e.Fragment, { children: [<YlxwKv/>, YlxwOfflineHelp(t)] })` —— 说明块挂在
     明细表**下方**，`claimable=false`（加载/出错）时说明块仍随面板一起渲染。

口径 / 硬约束
--------------------------------------------------------------------------
  · **只加说明，不改任何收益数值、不改服务端、不改按钮/领取逻辑**。
  · 文案里的「5 分钟」是服务端门槛常量（report 未下发该字段，故写死）；上限/速率/灵石比例
    一律**读 report 的真实字段**（capHours / ratePerHourPct / stoneRatio / monthCard），
    服务端改档时面板文案自动跟随。
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS；每个 replace 带精确 expect。
  · 只新建本文件；不改 build_v26n.py、不写 build/assets/。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R021help: 挂机收益「玩法说明」折叠块 =====
   文案依据 = 服务端 srv/index_v28.ts 的离线收益真实规则（逐字读码）：
     锚点 = 客户端上报的「真实离开时刻」last_seen_at（缺失回落 updated_at）
     门槛 OFFLINE_MIN_MS = 5 分钟；速率 0.0048（月卡 0.006）/小时当层修为槽
     上限 8 小时（月卡 12）；修为 = floor(槽 × 速率 × 小时) 且钳槽内
     灵石 = 修为 × 10%；领取 = POST /offline/claim（守卫推进 offline_claimed_until）
   ★ 只加「说明」，不改任何收益数值 / 不改服务端。
   ★ 上限/速率/灵石比例/月卡 一律读 /offline/report 的真实字段，服务端改档自动跟随。 */
function YlxwOfflineHelp(t) {
  var cap = (t && t.capHours) || 8;
  var rate = (t && t.ratePerHourPct != null) ? t.ratePerHourPct : 0.5;
  var mc = !!(t && t.monthCard);
  var ratio = (t && t.stoneRatio != null) ? Math.round(Number(t.stoneRatio) * 100) : 10;
  return e.jsxs("details", {
    className: "mt-3 rounded border border-stone-700 bg-ink-900/60 px-3 py-2 text-xs text-stone-400",
    children: [
      e.jsx("summary", {
        className: "cursor-pointer select-none font-bold text-amber-300/90",
        children: "玩法说明：收益从哪来 / 为什么有时是 0"
      }),
      e.jsxs("div", { className: "mt-2 space-y-2 leading-relaxed", children: [
        e.jsxs("p", { children: [
          e.jsx("span", { className: "text-stone-300 font-bold", children: "① 收益从哪来：" }),
          "你「离开游戏」期间，天地灵气自行灌体。修为 = 当层修为槽 × 速率 × 离线小时；灵石 = 修为 × " + ratio + "%。"
        ] }),
        e.jsxs("p", { children: [
          e.jsx("span", { className: "text-stone-300 font-bold", children: "② 怎么才能拿到：" }),
          "离线满 5 分钟才开始计（不足 5 分钟收益为 0）；速率 " + rate + "%/小时（当层修为槽" + (mc ? "，月卡已生效" : "，无月卡") + "）；结算上限 " + cap + " 小时，超出部分不结算；回到游戏后在本面板点「领取」，修为与灵石直接入档，并发一封回执邮件。"
        ] }),
        e.jsxs("p", { children: [
          e.jsx("span", { className: "text-stone-300 font-bold", children: "③ 为什么有时是 0 / 领不了：" }),
          "· 页面一直开着、没真正离开 ⇒ 离线不足 5 分钟；· 当前层修为已满（先把修为用掉或突破，再回来领）；· 这一段的收益已经领过；· 「已封顶」= 离线超过上限，超出部分不结算（上限内仍可领）。"
        ] }),
        e.jsx("p", { className: "text-stone-500", children: "提示：收益按你「离开那一刻」的修为槽结算；把页面挂着不操作不算离线，要真正离开（关页面 / 切到后台）才开始计时。" })
      ] })
    ]
  });
}
'''

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# 注入锚：组件定义行（前文是 `YlxwTFarm` 的收尾，安全语句边界）
INJECT_ANCHOR = 'function YlxwTOffline() {'

# E2：面板内的单节点 KV → 包成 Fragment（KV + 说明块）
KV_OLD = (': t ? e.jsx(YlxwKv, { data: { "\u5883\u754c": t.realm, "\u5c42\u6570": t.realmLevel, '
          '"\u5c0f\u65f6": YlxwNum(t.hours), "\u4fee\u4e3a\u53ef\u9886": YlxwNum(t.expGain), '
          '"\u7075\u77f3\u53ef\u9886": YlxwNum(t.stonesGain), "\u53ef\u9886\u53d6": t.claimable ? '
          '"\u662f" : "\u5426", "\u5df2\u5c01\u9876": t.capped ? "\u662f" : "\u5426" } })')

KV_NEW = (': t ? e.jsxs(e.Fragment, { children: [e.jsx(YlxwKv, { data: { "\u5883\u754c": t.realm, '
          '"\u5c42\u6570": t.realmLevel, "\u5c0f\u65f6": YlxwNum(t.hours), '
          '"\u4fee\u4e3a\u53ef\u9886": YlxwNum(t.expGain), "\u7075\u77f3\u53ef\u9886": YlxwNum(t.stonesGain), '
          '"\u53ef\u9886\u53d6": t.claimable ? "\u662f" : "\u5426", "\u5df2\u5c01\u9876": t.capped ? '
          '"\u662f" : "\u5426" } }), YlxwOfflineHelp(t)] })')


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r021help 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    kv_old = zh(KV_OLD)
    kv_new = zh(KV_NEW)

    # 1) 说明块函数（函数声明提升，位置无关）
    p.insert_before('r021help-block', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 YlxwOfflineHelp（折叠玩法说明）')

    # 2) 单节点 KV → Fragment(KV + 说明块)
    p.replace('r021help-kv', kv_old, kv_new, expect=1,
              note='KV 下方挂玩法说明块')

    # ------------------------------------------------------------- 门禁
    _INJ_SCOPE = ('/* ===== yl-R021help:', 'function YlxwTOffline() {')
    gates = [
        # ---- 注入块 ----
        ('R21H·说明块函数已注入',     'function YlxwOfflineHelp(t) {', 1, '==', ''),
        ('R21H·折叠容器 details',     'e.jsxs("details", {', 1, '==', '限域到本模块注入块', _INJ_SCOPE),
        ('R21H·折叠标题 summary',     'e.jsx("summary", {', 1, '==', '限域到本模块注入块', _INJ_SCOPE),
        ('R21H·上限读服务端 capHours', 'var cap = (t && t.capHours) || 8;', 1, '==', '不写死'),
        ('R21H·速率读服务端 ratePerHourPct', 'var rate = (t && t.ratePerHourPct != null) ? t.ratePerHourPct : 0.5;', 1, '==', '不写死'),
        ('R21H·月卡读服务端 monthCard', 'var mc = !!(t && t.monthCard);', 1, '==', ''),
        ('R21H·灵石比例读服务端 stoneRatio', 'var ratio = (t && t.stoneRatio != null) ? Math.round(Number(t.stoneRatio) * 100) : 10;', 1, '==', '不写死'),
        ('R21H·门槛文案 5 分钟',      zh('离线满 5 分钟才开始计'), 1, '==', '服务端 OFFLINE_MIN_MS'),
        ('R21H·收益来源说明',         zh('修为 = 当层修为槽 × 速率 × 离线小时'), 1, '==', ''),
        ('R21H·灵石分项说明',         zh('灵石 = 修为 × ') + '" + ratio', 1, '==', '正文 ① 唯一'),
        ('R21H·已封顶含义说明',       zh('「已封顶」= 离线超过上限，超出部分不结算'), 1, '==', ''),
        ('R21H·修为满槽领不了说明',   zh('当前层修为已满'), 1, '==', ''),
        ('R21H·已领过说明',           zh('这一段的收益已经领过'), 1, '==', ''),
        ('R21H·页面开着不算离线说明', zh('把页面挂着不操作不算离线'), 1, '==', ''),
        # ---- 就地替换 ----
        ('R21H·KV 后已挂说明块',      'YlxwOfflineHelp(t)] })', 1, '==', ''),
        ('R21H·旧单节点 KV 已清零',   kv_old, 0, '==', ''),
        ('R21H·说明块只出现一次(渲染)', 'YlxwOfflineHelp(t)', 2, '==', '定义 1 + 渲染 1'),
        # ---- 基线保护（不得改动其它面板 / 不得引入禁用模式）----
        ('基线·YlxwTOffline 定义仍在', 'function YlxwTOffline() {', 1, '==', ''),
        ('基线·离线报告端点未动',      'YlxwUseList("/offline/report")', 1, '==', ''),
        ('基线·领取按钮未动',          'f("claim", "/offline/claim", {}, ', 1, '==', ''),
        ('基线·领取按钮 disabled 逻辑未动', 'disabled: !!u || l || !t || !t.claimable', 1, '==', ''),
        ('基线·面板标题未动',          r'"\u6302\u673a\u6536\u76ca" }), a ? e.jsx(YlxwErr', 1, '==', ''),
        ('基线·注入块内无 XHR',        'XMLHttpRequest', 0, '==', '', _INJ_SCOPE),
        ('基线·注入块内无 X-YL- 头',    'X-YL-', 0, '==', '', _INJ_SCOPE),
        ('基线·注入块内无 postMessage', 'postMessage', 0, '==', '', _INJ_SCOPE),
        ('基线·注入块内无 fetch',       'fetch(', 0, '==', '纯说明，无网络', _INJ_SCOPE),
    ]
    return gates
