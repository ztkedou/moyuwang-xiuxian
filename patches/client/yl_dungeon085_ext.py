# -*- coding: utf-8 -*-
"""
yl_dungeon085_ext.py — 0.8.5 批次 · 秘境每日限制真正落地（cli-dg）

=========================================================================== 一句话
把客户端「进入秘境」接到服务端权威账本 `/api/dungeon/entry`，让
「每日 3 次 + 30s CD」真正生效；秘境手札的「今日已进」不再是恒 0。

=========================================================================== 用户原话（2026-09-28，第 4 条）
    「秘境手扎这个今日限制未生效，下面可以点的进入秘境，点了数量没有增加，
      也没有限制可以无限进入。」

=========================================================================== 根因（本会话侦察实证）
服务端 0.8.2 起就已完备（`srv/index_v28.ts`）：
    · GET  /api/dungeon/status   → { date, count, cap:3, remaining, cdLeftMs, canEnter, … }
    · POST /api/dungeon/entry    → 200 { ok, count, cap, remaining, cdMs }
                                   403 { ok:false, reason:'cap'|'cd', error, retryAfterMs }
    · 表 dungeon_tracker 每 (player_id,date) 一行，count/observed/anomaly

客户端**从未调用** `/dungeon/entry`（全产物 0 处）：
    · 「秘境手札」面板 `YlxwTDungeon` 只读 `/dungeon/status` ⇒ count 恒 0 ⇒ 永远显示 0/3
    · 经典秘境入口 `XM.handleEnterRealm` 只扣 `m.cost` 就直接进 ⇒ 无限次
    · 地宫 Roguelike `yk` 用 `window.__ylDg`（纯客户端、刷新页面即清零）⇒ 也无限次

=========================================================================== ★ 关键约束：不能用 Xc() / YlxwPost()
`Xc`（bundle @594262）：
    if(v.status===401||v.status===403)
      throw Et.getState().token!==l ? new Error("Token changed, request aborted")
                                    : (Et.getState().logout(), Je(Hr), new Error(Hr));
⇒ **任何 403 都会强制登出玩家**。而 `/dungeon/entry` 超限/过频正是 403
（服务端刻意用 403 表达"软门槛拒绝"）⇒ 走 `YlxwPost` 会让玩家在**用满 3 次时被踢下线**。

所以本模块改用交易行同款「原始 fetch + 自己看状态码」写法：
    fetch(Nd(ln + "/dungeon/entry"), { method:"POST",
           headers: Object.assign({ "Content-Type": "application/json" }, jo()), body:"{}" })
      · `jo()` = 现有助手，返回 { Authorization: "Bearer <token>" }（服务端 authenticateToken 只认 header）
      · `Nd()` = 现有助手，追加 ?token=…（与 /market/list 一致）
      · 不使用 `X-YL-*` 头（V28_BAN_PATTERNS 禁止）——服务端也不要求

=========================================================================== 策略：403 拒绝 / 其余一律放行（fail-open）
    · 403                → 拒绝进入，把服务端 `error` 原文回显（cap / cd 两种）
    · 401                → 先 `pS()` 静默续期一次再重试（与 Xc 同款），仍失败则放行
    · 其它非 2xx / 网络异常 → **放行**（服务端是"软门槛"，不能因服务端抖动把玩法锁死）
    · 未登录（无 token）    → 放行（本地单机调试场景）
记账由服务端负责：即便客户端放行，服务端仍有 entry 上报 + 存档差值双通道。

=========================================================================== 两个入口 + 本地计数回灌
1) 经典秘境 `XM.handleEnterRealm`（@1390353）
   原：`return t.spiritStones<m.cost ? (提示,!1) : (扣费, 关弹窗, 进秘境, !0)`
   改：扣费判定提到前面（**避免"灵石不足"也消耗一次次数**），再 gate，再进秘境。
       语义与改写前逐字等价（仍是 `return (扣费, 关弹窗, 进秘境, !0)`）。

2) 地宫 Roguelike `yk.T`（@1501754）
   原：`T=O.useCallback(()=>{const q=ylDgGate(); …本地校验… 写 window.__ylDg; u(W)…})`
   改：`async` 化 + 在**本地校验全部通过之后、写本地计数之前**插入服务端 gate；
       把服务端返回的 `count` 回灌进 `window.__ylDg`。
       ⇒ `ylDgGate()` **一行未改**，但它读到的 `day` 从此是服务端权威值，
         既有的 4 处「今日已探索 x/3」展示与 `q.day>=3` 快速预检自动跟着变准。

3) `YlxwDungeonStatusSync()` 在 Roguelike 弹窗打开时拉一次 `/dungeon/status`
   并回灌 `window.__ylDg` ⇒ 打开即可看到真实剩余次数（不再恒 0）。

=========================================================================== 技术约束遵守
· 注入块纯 ASCII（`zh()` 后无非 ASCII）；中文一律走 zh()。
· 注入块不含 V28_BAN_PATTERNS：iframe / postMessage / XMLHttpRequest / auth_token / X-YL-。
· 每个 replace 带 expect 精确次数；apply() 返回门禁五元组列表。
· 只新建本文件 + 侦察/报告，不修改任何已有模块，不写回 build/assets/。
"""

# --------------------------------------------------------------------------- 注入块（纯 ASCII，中文由 build 侧 zh() 转义）

INJECT_JS = r'''
/* ===== yl-0.8.5: secret-realm daily cap wired to the server ledger =====
   Server owns the authoritative "entered today" counter:
     GET  /dungeon/status  -> { date, count, cap, remaining, cdLeftMs, canEnter }
     POST /dungeon/entry   -> 200 { ok, count, cap, remaining, cdMs }
                              403 { ok:false, reason:'cap'|'cd', error, retryAfterMs }

   NOTE: we must NOT reuse Xc()/YlxwPost() for the entry call. Xc() treats HTTP 403
   as an unrecoverable session error and force-logs-out the player, while
   /dungeon/entry answers 403 for BOTH "daily cap reached" and "too frequent".
   So we post with the same primitive the trade market uses (jo() header + Nd()
   query) and read the status code ourselves.

   Policy: 403 -> deny (show the server's own message). Anything else -> fail OPEN,
   because the server ledger is a soft gate and a server hiccup must not lock
   players out of the content. The server still keeps its own ledger regardless. */
var YLXW_DG_ENTRY = "/dungeon/entry";
var YLXW_DG_STATUS = "/dungeon/status";

function YlxwDungeonToday() {
  try {
    var W = new Date();
    return W.getFullYear() + "-" + (W.getMonth() + 1) + "-" + W.getDate();
  } catch (e) { return ""; }
}
/* Mirror the server count into window.__ylDg so the pre-existing local gate and
   its "今日已探索 x/3" displays (ylDgGate, unchanged) reflect server truth. */
function YlxwDungeonMarkLocal(count) {
  try {
    var n = Number(count);
    if (!isFinite(n) || n < 0) return;
    window.__ylDg = { d: YlxwDungeonToday(), cnt: Math.floor(n), cd: 0 };
  } catch (e) {}
}
async function YlxwDungeonStatusSync() {
  try {
    var tk = null;
    try { tk = Et.getState().token; } catch (e0) { tk = null; }
    if (!tk) return null;
    var s = await YlxwGet(YLXW_DG_STATUS);
    if (s && typeof s.count === "number") YlxwDungeonMarkLocal(s.count);
    return s || null;
  } catch (e) { return null; }
}
async function YlxwDungeonEntryPost() {
  return await fetch(Nd(ln + YLXW_DG_ENTRY), {
    method: "POST",
    headers: Object.assign({ "Content-Type": "application/json" }, jo()),
    body: "{}"
  });
}
/* -> { ok:true, count?, remaining?, degraded? } | { ok:false, msg } ; never throws */
async function YlxwDungeonEntryGate() {
  try {
    var tk = null;
    try { tk = Et.getState().token; } catch (e0) { tk = null; }
    if (!tk) return { ok: true, degraded: "no-token" };
    var res = await YlxwDungeonEntryPost();
    if (res && res.status === 401) {
      try { await pS(); res = await YlxwDungeonEntryPost(); } catch (eR) {}
    }
    var data = null;
    try { data = await res.json(); } catch (e1) { data = null; }
    try { if (typeof YLApplyBalance === "function") YLApplyBalance(data); } catch (e2) {}
    if (res.status === 403) {
      return { ok: false, msg: (data && data.error) || "今日秘境次数已用完，明日再来。" };
    }
    if (!res.ok) return { ok: true, degraded: "status-" + res.status };
    if (data && typeof data.count === "number") YlxwDungeonMarkLocal(data.count);
    return { ok: true, count: data && data.count, remaining: data && data.remaining };
  } catch (e) {
    return { ok: true, degraded: "network" };
  }
}
'''

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- 锚点（取自 0.8.4 产物，全部实测 count==1）

# —— 注入锚：紧贴 YlxwMin 定义之前（与 YlxwApi/YlxwGet/YlxwPost 同一作用域，函数声明提升）——
INJECT_ANCHOR = 'function YlxwMin(r) { return r >= 6e4 ?'

# —— (E6-1) 经典秘境入口 ——
# 原文：return t.spiritStones<m.cost?(a("囊中羞涩…","danger"),!1):(扣费,关弹窗,进秘境,!0)
ENTER_ANCHOR = 'return t.spiritStones<m.cost?(a("囊中羞涩，无法支付开启秘境的灵石。","danger"),!1):('
ENTER_REPL = (
    'if(t.spiritStones<m.cost){a("囊中羞涩，无法支付开启秘境的灵石。","danger");return!1}'
    'const _ylg=await YlxwDungeonEntryGate();'
    'if(!_ylg.ok){a(_ylg.msg,"danger");return!1}'
    'return ('
)

# —— (E6-2) 地宫 Roguelike 入口 T 回调 ——
YK_T_ANCHOR = 'T=O.useCallback(()=>{const q=ylDgGate();'
YK_T_REPL = 'T=O.useCallback(async()=>{const q=ylDgGate();'

YK_WRITE_ANCHOR = (
    'const X=new Date();try{window.__ylDg={d:X.getFullYear()+"-"+(X.getMonth()+1)+"-"+X.getDate(),'
    'cnt:q.day+1,cd:Date.now()}}catch(KS){}'
)
YK_WRITE_REPL = (
    'const _ylg=await YlxwDungeonEntryGate();'
    'if(!_ylg.ok){c(_ylg.msg,"danger");return}'
    'const X=new Date();'
    'try{window.__ylDg={d:X.getFullYear()+"-"+(X.getMonth()+1)+"-"+X.getDate(),'
    'cnt:(typeof _ylg.count==="number"?_ylg.count:q.day+1),cd:Date.now()}}catch(KS){}'
)

# —— (E6-3) Roguelike 弹窗打开时同步服务端次数 ——
YK_EFFECT_ANCHOR = 'O.useEffect(()=>{t&&(u(null),S("intro"),v(null),j(null))},[t])'
YK_EFFECT_REPL = (
    'O.useEffect(()=>{t&&(u(null),S("intro"),v(null),j(null))},[t]),'
    'O.useEffect(()=>{t&&YlxwDungeonStatusSync()},[t])'
)


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含改名 + 全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 0) 注入服务端门禁助手（同 YlxwApi/YlxwPost/YlxwMin 作用域）
    p.insert_before(
        'dg085-helper',
        INJECT_ANCHOR,
        zh(INJECT_JS) + '\n',
        expect=1,
        note='注入 YlxwDungeonEntryGate / YlxwDungeonStatusSync / YlxwDungeonMarkLocal'
    )

    # 1) (E6-1) 经典秘境：扣费判定前置（不浪费次数）→ 服务端 gate → 再进
    p.replace('dg085-enter', ENTER_ANCHOR, ENTER_REPL, expect=1,
              note='handleEnterRealm 扣费前/后加服务端每日 gate')

    # 2) (E6-2) 地宫 Roguelike：T 回调 async 化 + 写本地计数前 gate
    p.replace('dg085-yk-async', YK_T_ANCHOR, YK_T_REPL, expect=1,
              note='T=O.useCallback(()=>{ -> async()=>{')
    p.replace('dg085-yk-gate', YK_WRITE_ANCHOR, YK_WRITE_REPL, expect=1,
              note='写 window.__ylDg 前先过服务端 gate，并把服务端 count 回灌')

    # 3) (E6-3) 弹窗打开时拉一次 /dungeon/status 回灌本地计数
    p.replace('dg085-yk-sync', YK_EFFECT_ANCHOR, YK_EFFECT_REPL, expect=1,
              note='打开 Roguelike 时同步服务端次数（展示不再恒 0）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- 注入块本体 ----
        ('E6·gate 函数已定义',        'async function YlxwDungeonEntryGate() {', 1, '==', ''),
        ('E6·status 同步函数已定义',   'async function YlxwDungeonStatusSync() {', 1, '==', ''),
        ('E6·本地计数回灌函数已定义',   'function YlxwDungeonMarkLocal(count) {', 1, '==', ''),
        ('E6·入口路径常量',           'var YLXW_DG_ENTRY = "/dungeon/entry";', 1, '==', ''),
        ('E6·状态路径常量',           'var YLXW_DG_STATUS = "/dungeon/status";', 1, '==', ''),
        ('E6·入口走 Nd+jo 原始 fetch', 'fetch(Nd(ln + YLXW_DG_ENTRY), {', 1, '==', ''),
        ('E6·403 单独识别',           'if (res.status === 403) {', 1, '==', ''),
        ('E6·401 续期后重试',          'try { await pS(); res = await YlxwDungeonEntryPost(); } catch (eR) {}', 1, '==', ''),
        ('E6·非 403 失败放行',         'return { ok: true, degraded: "status-" + res.status };', 1, '==', ''),
        ('E6·网络异常放行',            'return { ok: true, degraded: "network" };', 1, '==', ''),
        ('E6·未登录放行',              'return { ok: true, degraded: "no-token" };', 1, '==', ''),
        ('E6·403 回显服务端原文',      'return { ok: false, msg: (data && data.error) ||', 1, '==', ''),
        ('E6·★未误用 YlxwPost 打入口', 'YlxwPost(YLXW_DG_ENTRY', 0, '==', '403 会被 Xc 当会话失效强制登出'),
        ('E6·助手块未自造鉴权头',
         'headers: Object.assign({ "Content-Type": "application/json" }, jo())', 1, '==', '复用 jo()，不新增头名'),

        # ---- (E6-1) 经典秘境 ----
        ('E6·经典入口已过服务端 gate',
         'const _ylg=await YlxwDungeonEntryGate();if(!_ylg.ok){a(_ylg.msg,"danger");return!1}', 1, '==', ''),
        ('E6·扣费判定已前置',          'if(t.spiritStones<m.cost){a("囊中羞涩，无法支付开启秘境的灵石。","danger");return!1}', 1, '==', ''),
        ('E6·旧三元扣费写法已清零',     'return t.spiritStones<m.cost?(a(', 0, '==', ''),

        # ---- (E6-2)(E6-3) 地宫 Roguelike ----
        ('E6·地宫 T 回调已 async',     'T=O.useCallback(async()=>{const q=ylDgGate();', 1, '==', ''),
        ('E6·地宫入口已过服务端 gate',
         'const _ylg=await YlxwDungeonEntryGate();if(!_ylg.ok){c(_ylg.msg,"danger");return}', 1, '==', ''),
        ('E6·地宫计数回灌服务端值',     'cnt:(typeof _ylg.count==="number"?_ylg.count:q.day+1)', 1, '==', ''),
        ('E6·旧地宫计数写法已清零',     'cnt:q.day+1,cd:Date.now()}}catch(KS){}', 0, '==', ''),
        ('E6·打开时同步 status',       'O.useEffect(()=>{t&&YlxwDungeonStatusSync()},[t])', 1, '==', ''),
        ('E6·服务端 gate 调用点共 2 处', '=await YlxwDungeonEntryGate();', 2, '==', '经典秘境 + 地宫'),

        # ---- 基线未被破坏 ----
        ('基线·秘境扣费逻辑未动',
         'spiritStones:b.spiritStones-m.cost})),u(!1),await f("secret_realm",m.name,m.riskLevel,m.minRealm,m.description),!0)', 1, '==', ''),
        ('基线·秘境气血门槛未动',      'if(t.hp<j.maxHp*.3){const b="你气血不足，此时进入秘境无异于自寻死路！"', 1, '==', ''),
        ('基线·秘境入场守卫未动',      'handleEnterRealm:async m=>{if(c||d>0||!t)return!1;const j=xt(t);', 1, '==', ''),
        ('基线·ylDgGate 定义未动',
         'function ylDgGate(){const q=window.__ylDg||(window.__ylDg={d:"",cnt:0,cd:0}),W=new Date(),X=W.getFullYear()+"-"+(W.getMonth()+1)+"-"+W.getDate(),Y=q.cd||0;return{day:q.d===X?q.cnt||0:0,cdMin:Date.now()<Y?Math.ceil((Y-Date.now())/6e4):0}}',
         1, '==', '只回灌数据源，函数体一行未改'),
        ('基线·地宫境界门槛未动',      'if(z<J){c(', 1, '==', ''),
        # ★ 2026-09-30 约束权移交：本条原为 `'ylDgGate().day+"/3 ' == 1`，
        #   语义是「dungeon085 只改数据源 ylDgGate()，不越界改展示文案」。
        #   但 dungeon2（R-032）**必须**把这行改成动态 `x/cap` ⇒ 全链装配后该字面量 = 0。
        #   两个模块都断言同一字面量 = 跨模块 needle 撞车（本项目反复踩的坑）。
        #   ⇒ 本条删除，正向约束（「已改动态」）移交 dungeon2 的门禁。
        #   dungeon085 自身的保护仍由上面「ylDgGate 函数体一行未改」那条覆盖。
        # ('基线·地宫展示文案未动',    'ylDgGate().day+"/3 ', 1, '==', '「今日已探索 x/3」'),
        ('基线·秘境手札面板未动',      'function YlxwTDungeon() {', 1, '==', ''),
        ('基线·手札仍读 status',       'YlxwUseList("/dungeon/status")', 1, '==', ''),
        ('基线·Roguelike 弹窗挂载未动', 'e.jsx(vk,{isOpen:c.isDungeonOpen', 1, '==', ''),
        ('基线·秘境弹窗挂载未动',      'e.jsx(cM,{isOpen:d.isRealmOpen', 1, '==', ''),
        ('基线·Xc 403 语义未动',       'if(v.status===401||v.status===403)', 1, '==', '本模块绕开它，但不改它'),
    ]
    return gates
