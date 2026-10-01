# -*- coding: utf-8 -*-
r"""
yl_arb_ext.py — P1-④⑤ 存档仲裁缺陷修复（客户端侧，v28）

================================================================================
背景（前一轮实测 + 本轮 cli-arb 独立复现，均以「未推档收益被抹掉」为表征）
================================================================================
本服是**客户端权威存档**（服务端 `POST /api/save` 收 body 即落库），服务端只用
`ECON_CLAMP`（`settleSaveEconV2`）对**正增量**做钳制。客户端有两条「权威值绝对覆盖」
通道，会把**本地已产生但尚未推档**的灵石收益静默抹掉：

  通道 A  `YLApplyBalance(j)`（@bundle ~594674）
          服务端 `YL_STONE_ECHO_V26K` 中间件给白名单路径（mail/quest/sect/gongfa/...）
          的成功响应附 `balance = 落库的 player.spiritStones`；客户端
          `Xc()`（非 /save GET 或任意 POST）与 `YlxwApi()` 都把它交给 `YLApplyBalance`，
          而它是**无条件绝对赋值** `Be.setState({player:...spiritStones:n})`。
          ⇒ 玩家在两次自动存档（10s）之间赚到的灵石，只要打开任何面板就归零。

  通道 B  `applyRemoteSave(a,l)`（@bundle ~545390，store 方法）
          6s tick（`jS()`）在 `gm_revision > max(a.current, appliedGmRevision)` 时
          `fetchSave()` + `applyRemoteSave()`，后者 `t({player: ho(a.player), ...})`
          **整包替换 player**，不做任何合并/守卫。
          ⇒ 服务端 rev 前进（另一设备 / 服务端发放 / GM）与 tick 之间产生的本地收益被回退。

本轮独立复现（idx=22，bundle md5 515aaac94f3db6908aac0a728be5a6e1，见
`localtest/_arb_evidence_repro.json`）：
  A  本地 1,013,984（+1,000,000 未推档）→ 调 `/mail/list` → 本地 10,000，**丢 1,003,984**
  B  本地 34,680（+24,680 未推档）→ 外部推进 rev 0→1 → 6s tick → 本地 22,345，**回退 12,335**

================================================================================
修复方案（方案对比见 localtest/report_cli-arb.md，此处只记结论）
================================================================================
选 **(b) 推档优先（flush-before-apply）+ ack 追踪 + 守卫式覆盖（三分支决策）**：

  * 维护 `YLSyncArb.ack` = 「客户端所知的、服务端已落库的 spiritStones」。
    在 载入存档 / 推档成功 / 权威值被采纳 三个时点对齐。
  * 权威值 `S` 到达时（回显或拉档）三分支：
      - `pending = local - ack <= 0` 或 `local <= S`
        ⇒ **apply**：无未推档增量（或权威值本就更高），照旧采纳 `S`。
      - `local > S` 且 `pending > 0` 且 **`S <= ack`**（服务端值持平/下降 = 陈旧回显 / 钳制 / 扣减）
        ⇒ **flush**：不覆盖，把本地（含未推档收益）**先推给服务端**，再 `fetchSave()` 回拉；
          回拉后**仅当服务端值 < 本次推档值**（= 被钳制/扣减）才采纳该权威值，否则**不动本地**
          （保住推档往返期间新产生的合法收益；否则每次 flush 都会丢一个往返窗口的收益）。
      - `local > S` 且 `pending > 0` 且 **`S > ack`**（服务端值上升 = 发放类）
        ⇒ **skip**：既不覆盖本地（保住未推档收益），也不抢先推档（否则盖掉刚发放的收益）；
          交由客户端自己的发放处理（`now === before` 快照守卫）+ 下一次自动推档合并
          —— 与响应处理顺序无关，两种顺序都不双计、不丢。
      - `flushing` 在飞时一律 `skip`，避免抖动/递归。

  **为什么这样能同时满足「不丢收益」与「不绕过 ECON_CLAMP」**：
    - 未推档增量在钳制额度内 ⇒ 服务端受理并落库 ⇒ 回拉到的值 = 本地值 ⇒ **收益保留**。
    - 增量超量（改档/开挂）⇒ 服务端 `settleSaveEconV2` 截断到 `ov + cap` ⇒ 回拉到的值
      **低于**本地 ⇒ 客户端立即采纳该钳制值 ⇒ **钳制不被绕过**（且窗口只有一次往返）。
    - 与既有 3 处乐观写入快照守卫（信箱一键领取 / 交易行货款 / 人物志）不冲突：
      它们走的是「服务端返回值按增量叠加到本地」的通道，本模块只动**绝对覆盖**通道；
      `skip` 分支还刻意为它们让路。

范围：本模块只仲裁 **spiritStones**（flush 后也只对齐灵石，刻意不整包 `applyRemoteSave`，
以免把服务端对 exp 的钳制一并带进本地）。exp / 背包 的同类覆盖问题不在本轮范围，报告里单列残余。

================================================================================
0.8.7 T3 增补：连点失败后存档回拉仲裁强化（pushSave 失败补偿路径）
================================================================================
服务端 0.8.7 起（srv_patch_t3_xinfa.py）修炼/悟道类扣费全部走「占位→扣款→补偿」，扣费即
落库并 `gm_revision++`。但客户端权威档下仍有一个**失败面**：面板动作（YlxwUseAct）失败时
——网络抖动 / 5xx / 响应丢失——服务端可能**已扣费**而客户端不知情，本地灵石仍持旧高值；
若不纠正，下一次自动推档（10s）会把旧高值盖回服务端 = 对已扣费用变相退款（并发修炼时
即「双花」面）。本次增补：

  * 新增 `YLArbPullback()`：动作失败 catch 里触发一次**存档回拉**（Pn.fetchSave），按既有
    仲裁口径对齐灵石——
      - 本地无未推档收益（pending = local - ack ≤ 0，修炼连点场景的常态：灵石回显连续）：
        **采纳服务端值**（含未遂扣费），ack 对齐 → 下一次推档不会再带旧高值；
      - 本地有未推档收益（pending > 0）：**不动本地**（保收益），仅把 ack 下调到服务端真值，
        让后续回显/推档按既有「服务端扣减 → flush」分支收敛（此残余分支与既有口径一致）；
      - 服务端值更高：照常采纳（发放类）。
  * 节流：pullback 5s 内至多一次（`pullCoolUntil`）；flush 在飞时跳过（避免互相踩）。
  * 回拉只对齐 spiritStones，不整包 applyRemoteSave（同 YLArbReconcile 边界：不把服务端对
    exp/背包 的钳制带进本地）。

接线点：`YlxwUseAct` 的 catch（全部仙务面板动作的公共失败路径，恰 1 处）——在 Je 报错前
触发 `YLArbPullback()`（try/catch 包裹，回拉自身异常绝不影响报错提示）。新增门禁四条
（模块尾 _gates 内「T3·」前缀），供 dryrun_087 落表。

================================================================================
0.8.8 增补：灵石归零的**客户端放大器**修复（用户已拍板修进 0.8.8）
================================================================================
服务端根因（`settleSaveEconV2` 把灵石写成 0 / 冻结旧值）由 a1-srv 修。本模块修**客户端把那个
低值无声放大成「本地也归零」的采纳路径**，并保证「**任何静默降余额都留痕**」。

★ 设计上最重要的一条结论（先说不做什么）：
  **「降值」本身不可判定** —— GM 改档 / 服务端合法扣减（0.8.7 T3 连点已扣费）/ 归零 bug
  在数值上**完全无法区分**（都是 remote < local）。因此：
    · 一律拒绝「低于本地的远端值」是**错的**：会 (a) 绕过 ECON_CLAMP（本地永远持高值 + 无限重推）、
      (b) 破坏 T3 双花防护（对已扣费变相退款）、(c) 回滚 GM 改档。
  可判定的是**通道**与**是否推了未推档收益**，据此分三处处置：

  1) `YLArbInit` / 新增 `YLArbInitServer` —— **真正的放大器在这里**：
     boot 路径 `loadGame` 可能被喂**本地遗留档**（`ylDoc`），若拿它做 ack ⇒ `local===ack`
     ⇒ `pending=0` ⇒ 远端任何低值都判 `apply` ⇒ 静默归零，且 flush 保护完全失效。
     修法：boot 里 `const A=await Pn.fetchSave()` 之后立刻 `YLArbInitServer(A.player)`
     （ack = **服务端已确认档**），并让 `YLArbInit` **不覆盖已确认的 ack**（新增 `confirmed` 标志）。
  2) `YLArbReconcile`（本次推档的应答）—— 服务端对**我们刚推的值**的裁决：
     若本次推的是「未推档收益」(`pv > prevAck`) 却被钳低 ⇒ **保留本地 + 有界重推 + 留痕**
     （上限 `YL_ARB_RECONCILE_RETRY_MAX=2`，用尽才采纳 ⇒ **ECON_CLAMP 不被绕过**）；
     采纳后加 6s 冷却，防「tick→flush→被钳→再 flush」推档风暴。
  3) `YLArbPullback` / `applyRemoteSave` / `YLApplyBalance`（通道 A 回显）——
     前者是 T3 恢复路径、后两者由 `gm_revision` 递增 / `balance` 回显触发
     （= GM 改档 / 服务端扣减 / 归零 bug **混流**）⇒ **语义一律不动，只加「降值留痕」**
     （写一条可见日志，`type=danger`，见 `YLArbTrace` / `YLArbTraceAdopt`）。
     ★ 两个实测得来的细节（E2E 逼出来的）：
       · 留痕必须**延后到本轮同步代码之后**写（`YLArbTraceAdopt` 内 `setTimeout(…,0)`）——
         `applyRemoteSave` 同帧会用服务端 logs **整包替换** store.logs，紧挨着写会被立刻抹掉；
       · 通道 A（`YLApplyBalance` 的 `balance` 回显，chan=3）必须一起接留痕 —— 它才是
         a3 复现里真正把本地从高值拉到 155 的那条路径（不是 tick）。

  ⇒ 净效果：**归零 bug 不再「无声」**；服务端修好后第一次重推即可恢复原值；钳制/扣费/GM 三条
     合法路径逐条保真。新增/改动门禁前缀 `归零·`（供 dryrun_087 落表）。

接线点：boot 路径 `const A=await Pn.fetchSave();`（恰 1 处）。

================================================================================
P1-④ 宗门贡献（客户端侧能做的部分）
================================================================================
服务端 `POST /api/sect/contribute` 只扣灵石、写 `sects.funds`，**从不写也不校验
`player.sectContribution`**；`/api/sect/gongfa/learn|upgrade` 只**扣**存档里的贡献值。
⇒ 客户端推多少贡献就被服务端照单全收（`sectContribution` 纯客户端权威）。
真正的权威化必须落 `srv/index_v28.ts`（**不在本模块范围**，报告里列出给 lead 转派）。

本模块做客户端侧能做的：**推档前贡献完整性守卫** `YLArbGuardContrib`：
  - 以 `YLSectContrib.ack`（服务端已落库贡献值，时点同 `YLSyncArb.ack`）为基准；
  - 单次推档增量 `d = local - ack > YL_SECT_CONTRIB_MAX_DELTA`（50000）⇒ **本地拒绝该增量并回拉**
    到 `ack + 上限`，同时把钳后值写回 store 与推档 payload，并提示玩家。
  - 阈值 50000 的**推导过程**（枚举合法入口 → 取单次最大合法值 → 乘富余）与
    **耦合点 C1/C2/C3**（服务端常量 / 客户端职衔表 / 未来服务端权威化）见下方
    `YL_SECT_CONTRIB_MAX_DELTA` 处的注释（就地可查，勿只留在报告里）。
  - 这是**减速带**不是反作弊（改客户端即可绕过）；它挡住的是「客户端逻辑 bug / 数值漂移 /
    朴素改档」导致的超常贡献入库。

================================================================================
契约
================================================================================
    INJECT_JS : str          注入 JS 块（含中文，由构建侧统一 zh() 转义）
    apply(p, ctx) -> gates
        p   : yl_patch.Patcher
        ctx : {'zh': zh 函数, 'base_text': str}
        gates: list[(name, needle, expected, op, note)]，op ∈ {'==','>=','<='}

锚点实测（基线 build/assets/index-v28-20260928.js，md5 515aaac94f3db6908aac0a728be5a6e1）：
    'const Pn={async fetchSave(){const t=await Xc('                       count=1
    'if (Number(s.player.spiritStones) === n) return;'                    count=1（旧无守卫覆盖）
    'try{const c=ho(a.player);t({player:c,'                              count=1
    'var ylPs=await r.json();try{typeof ylPs.gm_revision'                 count=1
    'async pushSave(t){try{t.dungeonGate=window.__ylDg||null'             count=1
    ',gameStarted:!0,hasSave:!0}),c.marketItems&&Ze.getState().setMarketItems(c.marketItems)}else t({hasSave:!1,gameStarted:!1})}catch(c){console.error("加载存档失败:"'
                                                                          count=1
    'YLArb' / 'YLSyncArb' / 'YLSectContrib' 在基线 count=0（无标识符碰撞）
"""

# --------------------------------------------------------------------------- 锚点
_ANCHOR_PN = 'const Pn={async fetchSave(){const t=await Xc('

# --- 通道 A：YLApplyBalance 的无守卫绝对覆盖 ---
_OLD_ECHO = ('    if (Number(s.player.spiritStones) === n) return;\n'
             '    Be.setState({ player: Object.assign({}, s.player, { spiritStones: n }) });')
_NEW_ECHO = ('    if (!YLStoneEchoPathOk(ylP)) return;\n'
             '    var cur = Number(s.player.spiritStones) || 0;\n'
             '    if (cur === n) return;\n'
             '    var ylArbD = YLArbDecide(cur, n);\n'
             "    if (ylArbD === 'flush') { YLArbFlush(); return; }\n"
             "    if (ylArbD === 'skip') return;\n"
             '    try { YLArbTraceAdopt(cur, n, 3); } catch (ylArbE7) {}\n'
             '    YLArbOnApplied(n);\n'
             '    Be.setState({ player: Object.assign({}, s.player, { spiritStones: n }) });')

# --- ★ 0.8.10 B1：灵石归零修复 —— 采纳器加「路径白名单」 ---
# 事故（用户截图 2026-09-30 01:36）：
#   `[灵石] 权威采纳后本地灵石下调：94729 → 0（服务端权威变更，已留痕）`
# 根因：`YLApplyBalance(j)` 读的是**裸顶层 `balance`**，而 `/api/activity/shop`（灵玉阁）
#   的响应把**灵玉余额**（玩家通常为 0）也放在顶层 `balance` ⇒ 字段名撞车。
#   `Xc()` 对「非 /save GET 或任意 POST」的**全部**响应调用采纳器 ⇒ 打开灵玉阁即把灵石采纳成 0。
#   （服务端 `STONE_ECHO_RE`（index_v28.ts:1546）**不含 `activity`**，故回显中间件不管它；
#     而 activity 端点自报的 `balance` 语义是灵玉，与灵石无关。）
# 修法：采纳器只认「灵石域」路径；`/api/activity/*` 一律拒绝采纳。
#   注意：`ln = "/yl/api"` ⇒ 实际路径形如 `/yl/api/activity/shop`，故正则匹配 `api/activity` 段。
#   路径缺失（undefined）时**保持旧行为放行** —— 现有 4 个调用点已全部显式传路径，
#   放行只为向后兼容（例如第三方注入块直接调 YLApplyBalance 而不传参）。
_OLD_ECHO_HEAD = ('function YLApplyBalance(j) {\n'
                  '  try {\n'
                  "    if (!j || typeof j !== 'object') return;\n"
                  '    var n = j.balance;')
_NEW_ECHO_HEAD = ('/* == YL_STONE_ECHO_GUARD_V2810 (0.8.10 B1) == */\n'
                  'function YLStoneEchoPathOk(ylP) {\n'
                  '  try {\n'
                  "    if (typeof ylP !== 'string' || !ylP) return true;\n"
                  "    var ylU = ylP.split('?')[0];\n"
                  '    return !/(^|\\/)api\\/activity(\\/|$)/.test(ylU);\n'
                  '  } catch (ylE) { return true; }\n'
                  '}\n'
                  '/* == end YL_STONE_ECHO_GUARD_V2810 == */\n'
                  'function YLApplyBalance(j, ylP) {\n'
                  '  try {\n'
                  "    if (!j || typeof j !== 'object') return;\n"
                  '    var n = j.balance;')

# 调用点：`Xc` 拦截器（全部非 /save GET + 全部 POST）——把路径 `t` 传进去
_OLD_CALL_XC = 'v.clone().json().then(YLApplyBalance).catch(function(){})'
_NEW_CALL_XC = 'v.clone().json().then(function(ylJ){YLApplyBalance(ylJ,t)}).catch(function(){})'

# 调用点：`YlxwApi(r,t)` 通用包装——把路径 `r` 传进去（灵玉阁走的就是这条）
_OLD_CALL_API = '  YLApplyBalance(l);'
_NEW_CALL_API = '  YLApplyBalance(l, r);'

# --- 通道 B：applyRemoteSave 的整包替换 ---
# ★ 0.8.8：本通道由 gm_revision 递增触发 = **GM 改档 / 服务端扣减 / 归零 bug 混流**，
#   数值上不可区分 ⇒ 只**留痕**、不阻断（阻断会回滚 GM 改档、破坏 0.8.7 T3 恢复语义）。
_OLD_ARS = 'try{const c=ho(a.player);t({player:c,'
_NEW_ARS = ('try{const c=ho(a.player);'
            'var ylArbD=YLArbDecide(Number((r().player||{}).spiritStones)||0,Number(c.spiritStones)||0);'
            'if(ylArbD!=="apply"){if(ylArbD==="flush")YLArbFlush();return}'
            'try{YLArbNoteSect(c.sectContribution)}catch(ylArbE0){}'
            'try{YLArbTraceAdopt(Number((r().player||{}).spiritStones)||0,Number(c.spiritStones)||0,1)}catch(ylArbE6){}'
            'YLArbOnApplied(c.spiritStones);'
            't({player:c,')

# --- 启动路径：ack 基准取「服务端已确认档」（GET /save 返回值） ---
# ★ 0.8.8 归零修复的关键锚点：boot 里 `const A=await Pn.fetchSave();` 拿到的就是服务端档，
#   在此立刻 YLArbInitServer(A.player)。此后 loadGame(ylDoc)（本地遗留档）里的 YLArbInit
#   不会覆盖已确认的 ack ⇒ 离线/未推档收益的 pending 保护重新生效（不再被判 apply 静默归零）。
_OLD_BOOT = 'const A=await Pn.fetchSave();var ylPd=null;'
_NEW_BOOT = ('const A=await Pn.fetchSave();try{YLArbInitServer(A&&A.player)}catch(ylArbE5){}'
             'var ylPd=null;')

# --- pushSave：推档前贡献完整性守卫 ---
_OLD_PUSH_HEAD = ('async pushSave(t){try{t.dungeonGate=window.__ylDg||null,t.settings='
                  'Be.getState().settings}catch(l){}const r=await YLSaveRetryPush(t);')
_NEW_PUSH_HEAD = ('async pushSave(t){try{t.dungeonGate=window.__ylDg||null,t.settings='
                  'Be.getState().settings}catch(l){}'
                  'try{t.player=YLArbGuardContrib(t.player)}catch(ylArbE1){}'
                  'const r=await YLSaveRetryPush(t);')

# --- pushSave：成功后对齐 ack ---
_OLD_PUSH_OK = 'var ylPs=await r.json();try{typeof ylPs.gm_revision'
_NEW_PUSH_OK = ('var ylPs=await r.json();try{YLArbOnPushOk(t)}catch(ylArbE2){}'
                'try{typeof ylPs.gm_revision')

# --- loadGame：以服务端档（未含离线收益）为 ack 基准 ---
_OLD_LOAD = (',gameStarted:!0,hasSave:!0}),c.marketItems&&Ze.getState().setMarketItems(c.marketItems)}'
             'else t({hasSave:!1,gameStarted:!1})}catch(c){console.error("加载存档失败:')
_NEW_LOAD = (',gameStarted:!0,hasSave:!0});try{YLArbInit(d)}catch(ylArbE3){}'
             'c.marketItems&&Ze.getState().setMarketItems(c.marketItems)}'
             'else t({hasSave:!1,gameStarted:!1})}catch(c){console.error("加载存档失败:')

# --- 0.8.7 T3：动作失败（连点/网络抖动/响应丢失）后的存档回拉（pushSave 失败补偿路径） ---
# YlxwUseAct 的 catch 是全部仙务面板动作的公共失败路径；bundle 内中文为 \u 转义形态，锚点按真实字节抄。
_OLD_ACT_CATCH = ('catch (h) { return Je((h && h.message) || "\\u64cd\\u4f5c\\u5931\\u8d25"), null; }'
                  ' finally { l(""); }')
_NEW_ACT_CATCH = ('catch (h) { try { YLArbPullback(); } catch (ylArbE4) {}'
                  ' return Je((h && h.message) || "\\u64cd\\u4f5c\\u5931\\u8d25"), null; }'
                  ' finally { l(""); }')


# --------------------------------------------------------------------------- 注入块
INJECT_JS = r'''
/* == YL_ARB_V28 (未推档收益仲裁：推档优先 + 守卫式权威覆盖；宗门贡献推档完整性守卫) == */
var YLSyncArb = { ack: null, confirmed: false, reconcileDrops: 0, flushing: false, coolUntil: 0, pullCoolUntil: 0, pullbacks: 0, flushes: 0, applies: 0, skips: 0, lastSkipAt: 0 };
var YLSectContrib = { ack: null, clamps: 0, lastClamp: null };
/* ============================ 0.8.8 灵石归零修复（客户端放大器）============================
   服务端根因（settleSaveEconV2 把灵石写成 0 / 冻结旧值）由 a1-srv 修；本模块修**客户端
   把那个低值无声放大成「本地也归零」的三条采纳路径**，并保证「任何静默降余额都留痕」。

   关键设计点（为什么不是「一律拒绝低于本地的远端值」）：
     ① **ECON_CLAMP 不能被绕过**：改档/开挂推超量 ⇒ 服务端截断 ⇒ 客户端必须采纳截断值，
        否则本地永远持高值、无限重推（推档风暴）。故守卫只能是**有界重推**，不能是永久拒绝。
     ② **不能误伤「服务端合法扣减」**（0.8.7 T3：连点/响应丢失后服务端已扣费，本地仍持旧高值，
        回拉时必须采纳低值 —— 否则是对已扣费的变相退款 = 双花面）。
     ③ **不能误伤 GM 改档**（合法的降余额场景）。
     ⇒ 结论：**降值本身不可判定**（GM 改档 / 服务端扣减 / 归零 bug 在数值上无法区分，见报告）。
        可判定的只有**通道**与**是否推了未推档收益**：
          · `applyRemoteSave`（gm_revision 递增触发）= GM 改档 + 服务端扣减 + 归零 bug **混流**
            ⇒ **只留痕，不阻断**（阻断会回滚 GM 改档 / 破坏 T3）。
          · `YLArbReconcile`（本次推档的应答）= 服务端对**我们刚推的值**的裁决
            ⇒ 若推的是「未推档收益」却被钳低 ⇒ **有界重推 + 留痕**，上限用尽才采纳（保钳制）。
          · `YLArbPullback`（动作失败后的回拉）= T3 恢复路径 ⇒ 保留「pending≤0 采纳」语义，只留痕。
     ④ **留痕必须延后写**（`YLArbTraceAdopt` 内 `setTimeout(…,0)`）：`applyRemoteSave` 在同一次
        同步执行里会用服务端 logs **整包替换** store.logs，紧接着写留痕会被立刻抹掉（E2E 实测）。
        通道 A（`YLApplyBalance` 的 balance 回显，chan=3）同样接留痕 —— 它才是 a3 复现里
        真正把本地拉到 155 的那条路径。
     ⑤ **真正的放大器是 ack 基准错**（见 YLArbInitServer / YLArbInit）：
        `loadGame` 可能被喂**本地遗留档**（ylDoc），若拿它做 ack ⇒ local===ack ⇒ pending=0
        ⇒ 远端任何低值都判 `apply` ⇒ 静默归零，且 flush 保护完全失效。修法：ack 一律取
        「服务端已确认档」（GET /save 返回值），且**加载档不得覆盖已确认的 ack**。
   ================================================================================ */
/* reconcile 有界重推上限：连续这么多次「推未推档收益 → 服务端仍钳低」才采纳服务端值 */
var YL_ARB_RECONCILE_RETRY_MAX = 2;
/* ============================ YL_SECT_CONTRIB_MAX_DELTA = 50000 ============================
   【这个数是怎么推出来的（推导过程，不是结论）】
   目标：给「单次推档的宗门贡献正增量」定一个上界——大到不误伤任何合法玩法，小到能挡住改档/漂移。
   取上界 = max(所有合法来源的「单次正变动量级」) × 安全富余。逐步推：

   step1 枚举「宗门贡献」在客户端/服务端的**合法变动入口**（grep contribution 得到仅三类）：
         (a) 宗门职衔奖励：接任/晋升时一次性发放 contribution；
         (b) 宗门任务 / 每日任务完成奖励（reward.contribution，单笔几十~几百）；
         (c) 宗门功法升级：**扣** contribution（负向，与本守卫同向的是正增量，故不计入上界）。
   step2 取每个入口的**单次最大合法值**（读源码常量，不估）：
         (a) 客户端宗门职衔奖励表 `[ot.Leader] = {exp:1e4, spiritStones:5e4, contribution:5e3}`
             → 单笔最大 5000（宗主是最高职衔，见 bundle `宗门职衔奖励表`，0.8.2 约 offset 332385）。
         (b) 任务奖励 contribution 为个位~三位数量级，远小于 (a)。
         (c) 宗门功法扣减上界 = `sectGfCost(4, 5)` = `SECT_GF_TIER_BASE[4] × 5` = 1500 × 5 = 7500
             （服务端常量 `SECT_GF_MAX_LEVEL = 5`、`SECT_GF_TIER_BASE = {1:100,2:250,3:600,4:1500}`、
              函数 `sectGfCost()` —— **按符号名定位**：0.8.1 在 `srv/index_v28.ts:8892-8893 / :8920`，
              0.8.2 在 `_chainstage/index_v28.v282.ts:9047-9048 / :9075`；行号随装配漂移）
             ——**负向**，仅用于确认「合法单次变动量级」不超过 ~7500。
   step3 取 step2 的**正向上界** = max(5000, 任务奖励) = 5000（扣减 7500 是反向，不构成正增量上界）。
   step4 乘安全富余：一次推档间隔（最长 10s 自动推档 / 更长的离线）内**可能合并多次合法操作**
         （连任多职、连交多个任务），故取 10x → 50000。既能容纳合并，又把「改档 1e6」这类
         超常增量挡在入库前（实测 T4：+1,000,000 被回拉到 ack+50000）。
   ── 耦合点（★ 服务端/客户端改了下面任一处，必须同步改这个常量）────────────────────────
     C1 服务端常量 `SECT_GF_MAX_LEVEL` / `SECT_GF_TIER_BASE`（+ 函数 `sectGfCost()`）
        —— 若宗门功法单层消耗上调（如四阶 base 1500 → 3000），合法变动量级随之翻倍，需重估富余。
     C2 客户端宗门职衔奖励表 `[ot.Leader].contribution`（0.8.2 bundle 约 offset 332385）
        —— 若最高职衔奖励上调（如 5000 → 50000），本阈值必须 ≥ 其 10x，否则会误伤接任。
     C3 服务端若将来**权威化** sectContribution（校验来源/上限），本客户端守卫应降级为纯 UI 提示，
        阈值改由服务端返回（避免两处阈值打架）。本守卫当前只是**减速带**，不是反作弊
        （改客户端即可绕过）；真正的权威化必须落服务端（见模块头 P1-④ 与报告 §6）。
   ========================================================================================= */
var YL_SECT_CONTRIB_MAX_DELTA = 50000;

function YLArbNum(v) { var n = Number(v); return isFinite(n) ? Math.floor(n) : 0; }
function YLArbNotice(msg) {
  try { if (typeof Je === 'function') { Je(msg); return; } } catch (e) {}
  try { console.warn('[YLArb] ' + msg); } catch (e) {}
}
/* 降值留痕：任何「本地灵石被下调」都必须写进**可见日志**（玩家不该在不知情的情况下少钱）。
   日志面板的 type ∈ {normal, gain, danger, special}（见产物日志渲染 switch）—— 下调用 danger。 */
function YLArbTrace(msg) {
  try {
    var st = Be.getState();
    if (st && typeof st.addLog === 'function') st.addLog('[灵石] ' + msg, 'danger');
  } catch (e) {}
  try { console.warn('[YLArb] ' + msg); } catch (e) {}
}
/* 采纳路径的降值留痕助手：只有「采纳后确实比采纳前低」才留痕（避免噪声）。
   chan 用**数字码**（1=云端拉档 / 2=动作失败回拉 / 3=权威采纳）—— 保持接线点纯 ASCII。
   ★ 实测坑：`applyRemoteSave` 在同一次**同步**执行里紧接着 `t({player:c,logs:(a.logs||[]).slice(-1000),…})`
     把 store.logs **整包替换**成服务端 logs ⇒ 刚写进去的留痕会被立刻抹掉（E2E S4 实测
     `danger_logs_after=[]`）。故留痕统一 **延后到本轮同步代码之后**（setTimeout 0）再写。 */
function YLArbTraceAdopt(localBefore, remoteAfter, chan) {
  try {
    var lb = YLArbNum(localBefore), ra = YLArbNum(remoteAfter);
    if (ra >= lb) return;
    var name = (chan === 1) ? '云端拉档' : (chan === 2) ? '动作失败回拉' : '权威采纳';
    var msg = name + '后本地灵石下调：' + lb + ' → ' + ra + '（服务端权威变更，已留痕）';
    setTimeout(function () { YLArbTrace(msg); }, 0);
  } catch (e) {}
}
/* ack 取「服务端已确认档」（GET /save 的返回值）：boot 路径在 fetchSave() 之后立刻调用。
   ★ 这是 0.8.8 归零修复的关键：loadGame 可能被喂**本地遗留档**（ylDoc），
     若拿它做 ack ⇒ local===ack ⇒ pending=0 ⇒ 远端任何低值都判 apply ⇒ 静默归零。 */
function YLArbInitServer(player) {
  try {
    if (!player) return;
    YLSyncArb.ack = { stones: YLArbNum(player.spiritStones) };
    YLSyncArb.confirmed = true;
    YLSectContrib.ack = YLArbNum(player.sectContribution);
  } catch (e) {}
}
/* 载入存档：ack 取**服务端档**（不含客户端离线收益 v），这样离线收益算作「未推档增量」而被保留。
   ★ 若 ack 已由 YLArbInitServer 用服务端档确认过，则**不覆盖**（loadGame 可能是本地遗留档）。 */
function YLArbInit(player) {
  try {
    if (!player) return;
    if (YLSyncArb.confirmed) return;
    YLSyncArb.ack = { stones: YLArbNum(player.spiritStones) };
    YLSectContrib.ack = YLArbNum(player.sectContribution);
  } catch (e) {}
}
/* 惰性兜底：首次需要而尚未初始化时，以当前本地值为基准（避免误判成「超量未推档增量」） */
function YLArbAck() {
  try {
    if (!YLSyncArb.ack) {
      var p = (Be.getState() || {}).player;
      if (!p) return null;
      YLSyncArb.ack = { stones: YLArbNum(p.spiritStones) };
    }
  } catch (e) { return null; }
  return YLSyncArb.ack;
}
/* pushSave 成功 ⇒ 本地这一份已被服务端受理，ack 对齐；被钳制后的真实值由随后回显/回拉纠正 */
function YLArbOnPushOk(payload) {
  try {
    if (payload && payload.player) {
      YLSyncArb.ack = { stones: YLArbNum(payload.player.spiritStones) };
      YLSectContrib.ack = YLArbNum(payload.player.sectContribution);
    }
  } catch (e) {}
}
/* 权威值被采纳 ⇒ ack 对齐（且标记为「服务端已确认」） */
function YLArbOnApplied(stones) { try { YLSyncArb.ack = { stones: YLArbNum(stones) }; YLSyncArb.confirmed = true; } catch (e) {} }
function YLArbNoteSect(v) { try { if (v != null) YLSectContrib.ack = YLArbNum(v); } catch (e) {} }
function YLArbJustSkipped() { return (Date.now() - YLSyncArb.lastSkipAt) < 2000; }

/* 决策：'apply'（无未推档增量，照旧采纳权威值）
        | 'flush'（本地有未推档正增量，且服务端值**未上升** ⇒ 先推档，不覆盖）
        | 'skip' （推档在飞；或服务端值**上升**〔发放类〕⇒ 本轮不覆盖也不推档）
   三分支的依据：
     * 服务端值上升（remote > ack）⇒ 是服务端新增（邮件/货款/宗门/另一设备加钱）。
       本轮 skip：不覆盖本地（保住未推档收益），也不抢先推档（否则会把刚发放的收益盖掉）；
       由客户端自己的发放处理（`now === before` 快照守卫）与下一次自动推档去合并 —— 与响应
       处理顺序无关，两种顺序都不双计、不丢。
     * 服务端值持平或下降（remote <= ack）⇒ 是陈旧回显 / 钳制 / 服务端扣减 ⇒ flush：
       把本地（含未推档收益）推给服务端裁决，再回拉钳制后的权威值。 */
function YLArbDecide(localStones, remoteStones) {
  try {
    if (YLSyncArb.flushing) { YLSyncArb.skips++; YLSyncArb.lastSkipAt = Date.now(); return 'skip'; }
    var ack = YLArbAck();
    if (!ack) return 'apply';
    var local = YLArbNum(localStones), remote = YLArbNum(remoteStones);
    if (local > remote && (local - ack.stones) > 0) {
      if (remote > ack.stones) { YLSyncArb.skips++; YLSyncArb.lastSkipAt = Date.now(); return 'skip'; }
      return 'flush';
    }
    return 'apply';
  } catch (e) { return 'apply'; }
}
/* 推档后收敛：**只把 spiritStones 对齐到服务端落库值**，且**仅在服务端钳制/下调时**才改本地。
   `pushed` = 本次 flush 推上去的灵石数（推档那一刻的本地值）。
     * `srv < pushed` ⇒ 服务端**截断（钳制）或扣减** ⇒ 采纳权威值 srv（**钳制不被绕过**）。
     * `srv >= pushed` ⇒ 服务端**受理了本次推档** ⇒ **不动本地**，只对齐 ack ——
       这样「推档往返期间新产生的合法收益」不会被 `srv` 覆盖掉（否则每次 flush 都会丢掉
       一个往返窗口的收益，实测约 60 灵石/次，违反「单调不减」）。
       未推档的那部分留待下一次推档（由下一次陈旧回显触发 flush）。
   刻意不整包 applyRemoteSave —— 否则会把服务端对 exp/背包 的钳制一并带进本地，
   把「本模块只仲裁灵石」的边界撑破（exp 的同类覆盖问题另案，见模块头）。 */
function YLArbReconcile(save, pushed) {
  try {
    if (!save || !save.player) return;
    var n = YLArbNum(save.player.spiritStones);
    var pv = YLArbNum(pushed);
    var prevAck = YLSyncArb.ack ? YLArbNum(YLSyncArb.ack.stones) : null;
    var pushedGains = (prevAck != null) && (pv > prevAck);
    YLSyncArb.ack = { stones: n };
    YLSyncArb.confirmed = true;
    YLArbNoteSect(save.player.sectContribution);
    var s = Be.getState();
    if (!s || !s.player) return;
    var local = YLArbNum(s.player.spiritStones);
    if (n < pv) {
      /* 服务端把本次推档**钳到了比推档值更低**。
         ★ 0.8.8 归零修复：若本次推的是「未推档收益」（pv > prevAck），先**保留本地并重推**，
           给服务端一次受理机会（服务端修好后即可恢复原值）；连续 YL_ARB_RECONCILE_RETRY_MAX
           次仍被钳 ⇒ 才采纳服务端值（**ECON_CLAMP 不被绕过**）。全程留痕。 */
      if (pushedGains && local > n && YLSyncArb.reconcileDrops < YL_ARB_RECONCILE_RETRY_MAX) {
        YLSyncArb.reconcileDrops++;
        YLArbTrace('服务端未受理本地灵石（' + local + ' → ' + n + '），已保留本地并重新推档（第 ' + YLSyncArb.reconcileDrops + ' 次）');
        YLArbFlush();
        return;
      }
      YLArbTrace('灵石被服务端下调：' + local + ' → ' + n + (pushedGains ? '（推档被钳制/未受理）' : '（服务端扣减）'));
      if (local !== n) {
        Be.setState({ player: Object.assign({}, s.player, { spiritStones: n }) });
      }
      /* 采纳后短暂冷却，避免「tick → flush → 被钳 → 再 flush」形成推档风暴 */
      YLSyncArb.coolUntil = Date.now() + 6000;
    } else {
      YLSyncArb.reconcileDrops = 0;
    }
  } catch (e) {}
}
/* 0.8.7 T3 连点失败补偿：动作失败后服务端可能已扣费而客户端不知情（本地灵石仍持旧高值）。
   不回拉 ⇒ 下一次自动推档把旧高值盖回服务端 = 对已扣费用变相退款（修炼连点时即双花面）。
   口径：pending≤0（无未推档收益，连点场景常态）⇒ 采纳服务端值（含扣费）；pending>0（本地有
   合法未推档收益）⇒ 不动本地只下调 ack，交由既有 flush/skip 分支收敛；服务端更高 ⇒ 照常采纳。
   只对齐 spiritStones，不整包 applyRemoteSave；5s 节流；flush 在飞时跳过。 */
function YLArbPullback() {
  if (YLSyncArb.flushing) return;
  if (Date.now() < YLSyncArb.pullCoolUntil) return;
  YLSyncArb.pullCoolUntil = Date.now() + 5000;
  Pn.fetchSave().then(function (save) {
    try {
      if (!save || !save.player) return;
      var srv = YLArbNum(save.player.spiritStones);
      var s = Be.getState();
      var local = s && s.player ? YLArbNum(s.player.spiritStones) : 0;
      var ack = YLArbAck();
      var ackSt = ack ? YLArbNum(ack.stones) : local;
      if (srv >= local || (local - ackSt) <= 0) {
        /* 无未推档收益（或服务端更高）：采纳服务端真值 = 把失应扣费同步进本地
           ★ 0.8.8：采纳即留痕（本分支是 T3 恢复路径，语义不动；只在「确实下调」时记一条） */
        YLArbTraceAdopt(local, srv, 2);
        YLSyncArb.ack = { stones: srv };
        YLSyncArb.confirmed = true;
        if (s && s.player && YLArbNum(s.player.spiritStones) !== srv) {
          Be.setState({ player: Object.assign({}, s.player, { spiritStones: srv }) });
        }
      } else {
        /* 本地有未推档收益：不动本地（保收益），ack 下调到服务端真值，
           后续回显/推档按「服务端扣减 → flush」既有分支收敛 */
        YLSyncArb.ack = { stones: srv };
        YLSyncArb.confirmed = true;
      }
    } catch (e) {}
  }, function () {});
}
/* 推档优先：本地（含未推档收益）先推给服务端 → 服务端 ECON_CLAMP 钳制 → 回拉钳制后的权威值并采纳。
   钳制额度内 ⇒ 收益保留；超量 ⇒ 被服务端截断后立即回拉纠正（钳制不被绕过）。 */
function YLArbFlush() {
  if (YLSyncArb.flushing) return;
  if (Date.now() < YLSyncArb.coolUntil) return;
  var s;
  try { s = Be.getState(); } catch (e) { return; }
  if (!s || !s.player) return;
  try { if (YLSync.isBlocked()) return; } catch (e) {}   /* 只读态不推档，也不覆盖本地 */
  YLSyncArb.flushing = true; YLSyncArb.flushes++;
  var payload = { player: s.player, logs: s.logs, marketItems: (Ze.getState() || {}).marketItems,
                  timestamp: Date.now(), lastActiveTime: Date.now() };
  var pushStones = YLArbNum(s.player.spiritStones);
  var done = function (ok) { YLSyncArb.flushing = false; if (!ok) YLSyncArb.coolUntil = Date.now() + 1500; };
  YLSync.pushNow(payload).then(function () { return Pn.fetchSave(); }).then(function (save) {
    done(true);
    YLArbReconcile(save, pushStones);
  }, function () { done(false); });
}
/* P1-④ 客户端侧：宗门贡献单次推档增量超常 ⇒ 本地拒绝并回拉到「服务端基准 + 上限」。
   （服务端不校验贡献来源，真正的权威化需服务端配合，见模块头注释与报告。） */
function YLArbGuardContrib(p) {
  try {
    if (!p) return p;
    var cur = YLArbNum(p.sectContribution);
    if (YLSectContrib.ack == null) { YLSectContrib.ack = cur; return p; }
    var d = cur - YLSectContrib.ack;
    if (d > YL_SECT_CONTRIB_MAX_DELTA) {
      var capped = YLSectContrib.ack + YL_SECT_CONTRIB_MAX_DELTA;
      YLSectContrib.clamps++;
      YLSectContrib.lastClamp = { from: cur, to: capped, ack: YLSectContrib.ack, delta: d };
      try {
        Be.getState().setPlayer(function (prev) {
          return prev ? Object.assign({}, prev, { sectContribution: capped }) : prev;
        });
      } catch (e) {}
      YLArbNotice('检测到宗门贡献异常增长，已回拉到服务端基准');
      return Object.assign({}, p, { sectContribution: capped });
    }
    return p;
  } catch (e) { return p; }
}
/* == end YL_ARB_V28 == */
'''


# --------------------------------------------------------------------------- 门禁
def _gates():
    return [
        # ---- 注入块本体 ----
        ('仲裁·决策助手定义',        'function YLArbDecide(',        1, '==', ''),
        ('仲裁·推档优先定义',        'function YLArbFlush(',         1, '==', ''),
        ('仲裁·推档后只对齐灵石',     'function YLArbReconcile(',     1, '==', '刻意不整包 applyRemoteSave（不把 exp 钳制带进本地）'),
        ('仲裁·flush 不整包回拉',     'YLArbReconcile(save, pushStones);', 1, '==', ''),
        ('仲裁·收敛仅在服务端下调时', 'if (n < pv) {',                1, '==', '服务端受理(srv>=pushed)时不动本地，保住往返期新收益'),
        ('仲裁·贡献守卫定义',        'function YLArbGuardContrib(',  1, '==', ''),
        ('仲裁·ack 惰性兜底',        'function YLArbAck()',          1, '==', ''),
        ('仲裁·未重复注入',          'var YLSyncArb = { ack: null',  1, '==', ''),
        ('仲裁·无标识符碰撞(旧名)',   'YLArbLegacy',                  0, '==', '占位，恒 0'),

        # ---- 0.8.8 灵石归零修复（客户端放大器：ack 基准 + 有界重推 + 降值留痕）----
        ('归零·ack 取服务端确认档',    'function YLArbInitServer(',    1, '==', 'ack 基准 = GET /save 返回值'),
        ('归零·启动路径已接',          'try{YLArbInitServer(A&&A.player)}catch(ylArbE5){}', 1, '==', 'boot fetchSave 之后立刻确认'),
        ('归零·加载档不覆盖已确认 ack', 'if (YLSyncArb.confirmed) return;', 1, '==', 'loadGame 可能是本地遗留档 ylDoc'),
        ('归零·confirmed 标志已引入',  'ack: null, confirmed: false',  1, '==', ''),
        ('归零·降值留痕函数',          'function YLArbTrace(',         1, '==', '写可见日志（type=danger）'),
        ('归零·采纳留痕助手',          'function YLArbTraceAdopt(',    1, '==', '只在确实下调时留痕，避免噪声'),
        ('归零·reconcile 有界重推',    'YLSyncArb.reconcileDrops++;',  1, '==', '推未推档收益被钳 ⇒ 先保本地重推'),
        ('归零·重推上限常量',          'var YL_ARB_RECONCILE_RETRY_MAX = 2;', 1, '==', '上限用尽才采纳（ECON_CLAMP 不被绕过）'),
        ('归零·旧无痕采纳形态已清零',   'if (YLArbNum(s.player.spiritStones) !== n) {', 0, '==', '旧 reconcile 静默采纳必须清零'),
        ('归零·拉档降值留痕',          'YLArbTraceAdopt(Number((r().player||{}).spiritStones)||0,Number(c.spiritStones)||0,1)', 1, '==', 'GM/扣减/归零混流 ⇒ 只留痕不阻断'),
        ('归零·回显采纳降值留痕',       'try { YLArbTraceAdopt(cur, n, 3); } catch (ylArbE7) {}', 1, '==', '通道 A（balance 回显）采纳低值也必须留痕'),
        ('归零·留痕延后到 store 覆盖后', 'setTimeout(function () { YLArbTrace(msg', 1, '>=', 'applyRemoteSave 会同帧整包替换 logs，必须延后写；★ 放宽为前缀匹配（原断言写死了 `YLArbTrace(msg);`，而 offline2 会往这个调用点补 level/tag 参数 ⇒ 字面量失配。语义不变：仍是「setTimeout 0 延后写」）'),
        ('归零·回拉降值留痕',          'YLArbTraceAdopt(local, srv, 2);', 1, '==', 'T3 恢复路径采纳时留痕（语义不动）'),
        ('归零·仲裁分支未改',          'if (remote > ack.stones) { YLSyncArb.skips++;', 1, '==', 'YLArbDecide 判定分支未动'),
        ('归零·推档采纳后冷却',        'YLSyncArb.coolUntil = Date.now() + 6000;', 1, '==', '防「tick→flush→被钳→再 flush」推档风暴'),

        # ---- 通道 A：旧的无守卫绝对覆盖必须清零 + 新写法必须在位 ----
        ('通道A·旧无守卫覆盖已清零',  'if (Number(s.player.spiritStones) === n) return;', 0, '==', '必须为 0'),
        ('通道A·回显已接守卫',        'var ylArbD = YLArbDecide(cur, n);', 1, '==', ''),
        ('通道A·采纳时对齐 ack',      'YLArbOnApplied(n);',          1, '==', ''),
        # ---- ★ 0.8.10 B1：路径白名单（活动域「灵玉 balance」不得被当灵石采纳）----
        ('B1·路径门函数已定义',        'function YLStoneEchoPathOk(ylP) {', 1, '==', ''),
        ('B1·采纳器已收路径参数',      'function YLApplyBalance(j, ylP) {',  1, '==', ''),
        ('B1·采纳器已接路径门',        'if (!YLStoneEchoPathOk(ylP)) return;', 1, '==', ''),
        ('B1·活动域拒绝正则',          'return !/(^|\\/)api\\/activity(\\/|$)/.test(ylU);', 1, '==', 'ln="/yl/api" ⇒ 匹配 api/activity 段'),
        ('B1·Xc 调用点已传路径',       'v.clone().json().then(function(ylJ){YLApplyBalance(ylJ,t)}).catch(function(){})', 1, '==', ''),
        ('B1·YlxwApi 调用点已传路径',   '  YLApplyBalance(l, r);',      1, '==', ''),
        ('B1·旧无参采纳器已清零',       'function YLApplyBalance(j) {', 0, '==', '必须为 0'),
        ('B1·旧无参 Xc 调用已清零',     'then(YLApplyBalance).catch',   0, '==', '必须为 0'),
        # ---- 通道 B：整包替换前必须过守卫 ----
        ('通道B·拉档已接守卫',
         'var ylArbD=YLArbDecide(Number((r().player||{}).spiritStones)||0,Number(c.spiritStones)||0);',
         1, '==', ''),
        ('通道B·旧整包替换已接守卫',  'try{const c=ho(a.player);var ylArbD=YLArbDecide(', 1, '==', ''),
        ('通道B·采纳时对齐 ack',      'YLArbOnApplied(c.spiritStones);', 1, '==', ''),
        # ---- pushSave 接线 ----
        ('推档·成功回写 ack',         'try{YLArbOnPushOk(t)}catch(ylArbE2){}', 1, '==', ''),
        ('推档·贡献完整性守卫',       'try{t.player=YLArbGuardContrib(t.player)}catch(ylArbE1){}', 1, '==', ''),
        # ---- loadGame 基准 ----
        ('载入·以服务端档初始化基准',  'try{YLArbInit(d)}catch(ylArbE3){}', 1, '==', ''),

        # ---- 0.8.7 T3 连点失败补偿（新增四条，供 dryrun_087 落表）----
        ('T3·回拉函数定义',           'function YLArbPullback(',                            1, '==', '存档回拉（pushSave 失败补偿路径）'),
        ('T3·回拉节流 5s',            'YLSyncArb.pullCoolUntil = Date.now() + 5000;',       1, '==', ''),
        ('T3·失败路径已接回拉',        'catch (h) { try { YLArbPullback(); } catch (ylArbE4) {}', 1, '==', 'YlxwUseAct catch 恰 1 处'),
        ('T3·回拉采纳服务端真值',       'Be.setState({ player: Object.assign({}, s.player, { spiritStones: srv }) });', 1, '==', 'pending≤0 时把失应扣费同步进本地'),
        ('T3·回拉双分支判定',          'if (srv >= local || (local - ackSt) <= 0) {',        1, '==', 'pending>0 不动本地走既有 flush 口径'),

        # ---- 回归：既有 3 处乐观写入快照守卫（不得被破坏）----
        ('回归·信箱/货款快照守卫',    'if (now === before) {',        2, '==', '信箱一键领取 + 交易行货款'),
        ('回归·人物志增量写入',
         'if (opt.stones) next.spiritStones = Math.max(0, (Number(prev.spiritStones) || 0) + opt.stones);',
         1, '==', '增量式（函数式 setPlayer），天然防竞态'),
        ('回归·宗门功法扣贡献快照守卫', 'if (now !== contribBefore) return cur;', 1, '==', ''),
        # ---- 回归：前序补丁不得被误伤 ----
        ('回归·5xx 重试助手',         'function YLSaveRetryPush(',    1, '==', ''),
        ('回归·409 冲突标志',         'ylCe.__ylConflict=!0',         1, '==', ''),
        ('回归·setAppliedGmRevision', 'setAppliedGmRevision(ylPs.gm_revision)', 1, '==', ''),
        ('回归·离线结算 YLSettledExp', 'YLSettledExp(ylPs)',          1, '==', ''),
    ]


def apply(p, ctx):
    """就地改造 bundle 文本，返回门禁列表。ctx = {'zh': zh, 'base_text': str}。"""
    zh = ctx['zh']
    block = zh(INJECT_JS)

    # 1) 助手注入：放在 `const Pn={...}` 之前（同一模块作用域，Be / Ze / ln / Xc / YLSync 均可见）
    p.insert_before(
        'arb-helper',
        _ANCHOR_PN,
        block + '\n',
        expect=1,
        note='注入 YLSyncArb（推档优先仲裁）/ YLSectContrib（贡献完整性守卫）',
    )

    # 2) 通道 A：YLApplyBalance 接守卫
    p.replace('arb-echo-guard', _OLD_ECHO, _NEW_ECHO,
              expect=1, note='回显不再无条件绝对覆盖：先 flush / 后采纳')

    # 2a) ★ 0.8.10 B1：采纳器加路径白名单（拒绝把活动域「灵玉 balance」当灵石采纳）
    p.replace('arb-echo-pathhead', _OLD_ECHO_HEAD, _NEW_ECHO_HEAD,
              expect=1, note='YLApplyBalance(j, ylP) + YLStoneEchoPathOk 路径门（/api/activity 拒绝采纳）')
    p.replace('arb-echo-call-xc', _OLD_CALL_XC, _NEW_CALL_XC,
              expect=1, note='Xc 拦截器把请求路径 t 传进采纳器')
    p.replace('arb-echo-call-api', _OLD_CALL_API, _NEW_CALL_API,
              expect=1, note='YlxwApi 把请求路径 r 传进采纳器（灵玉阁走这条）')

    # 3) 通道 B：applyRemoteSave 接守卫
    p.replace('arb-ars-guard', _OLD_ARS, _NEW_ARS,
              expect=1, note='整包替换前先仲裁：有未推档收益则推档优先')

    # 4) pushSave：推档前贡献完整性守卫
    p.replace('arb-push-contrib', _OLD_PUSH_HEAD, _NEW_PUSH_HEAD,
              expect=1, note='超常贡献增量本地拒绝并回拉')

    # 5) pushSave：成功后对齐 ack
    p.replace('arb-push-ack', _OLD_PUSH_OK, _NEW_PUSH_OK,
              expect=1, note='ack 与服务端受理值对齐')

    # 6) loadGame：以服务端档为 ack 基准（离线收益算未推档增量）
    p.replace('arb-loadgame-init', _OLD_LOAD, _NEW_LOAD,
              expect=1, note='ack 基准取服务端档，离线收益视为未推档增量')

    # 7) 0.8.7 T3：动作失败（连点/响应丢失）后的存档回拉（pushSave 失败补偿路径）
    p.replace('arb-act-fail-pullback', _OLD_ACT_CATCH, _NEW_ACT_CATCH,
              expect=1, note='YlxwUseAct catch（全部面板动作公共失败路径）触发 YLArbPullback')

    # 8) 0.8.8：boot 路径以「服务端已确认档」为 ack 基准（loadGame 可能是本地遗留档）
    p.replace('arb-boot-ack', _OLD_BOOT, _NEW_BOOT,
              expect=1, note='ack 取 GET /save 返回值，修掉「local===ack ⇒ 静默归零」放大器')

    return _gates()
