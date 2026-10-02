# -*- coding: utf-8 -*-
r"""
yl_advend105_ext.py — R-105「自动历练结束」汇总推送（客户端单模块）

需求原文（用户，台账 R-105）
--------------------------------------------------------------------------
  「我要加的内容是**自动历练结束时**展示**本地自动历练的时长以及相关成果**的
    一条推送。**类似自动打坐结束后展示的一条日志内容**。」

  即：玩家**停止自动历练**时，日志里出现**一条汇总**，含
    · 本次自动历练的本地时长（从开启自动历练到关闭的这段时间）
    · 相关成果（本次期间累计的 修为 / 灵石 / 历练次数）
  ★ 刻意**一条**，不是每次历练都刷 —— 每次刷是 R-089 已经做过的事（yl_adv097_ext.py
    的 `YlxwAdvResultLog`），本条是「结束时的那一条」。

基线 = build/assets/index-v299-20261001.js（只读；已含 medlog / adv097 等全部前置模块）

==========================================================================
一、打坐侧参考实现要点（yl_medlog_ext.py —— 本模块照它的形态做）
==========================================================================
  medlog 的做法（R-023）：
    · 模块级注入 `YlxwMedDur / YlxwMedTick / YlxwMedStone / YlxwMedSession`
      + 累加器 `YLXW_MED_ACC`（**不往 player 上加字段**，避免动存档 schema）。
    · 会话边界 = 布尔 `autoMeditate` 的 false→true（记起点、清累加器）/
      true→false（结算 + 写一条日志）。
    · 挂点 = 在打坐 interval effect 之后挂一个**同依赖旁路 effect**
      `,O.useEffect(()=>{YlxwMedSession(t)},[t])`（t = autoMeditate 的 prop），
      **不改任何开关**，只挂旁路。
    · 每跳累加取自 handleMeditate 内已算好的每跳值（就地调用 helper 返回原值）。
    · 汇总一条 `Be.getState().addLog(...)`，风格为
      「<emoji> 本次打坐 <时长>：修为 +N · 灵石 +N · 顿悟 N 次 · 平均每跳 …」。

  本模块**同形态**：旁路 effect + 模块级累计器 + 结束时一条 addLog。
  唯一升级点：历练侧存在「战斗/商店/事件临时暂停」，必须区分「主动关闭 vs 临时暂停」
  （见 §三），medlog 侧因为暂停即结束会话，不存在这个区分需求。

==========================================================================
二、自动历练开关的确切位置（逐字取证）
==========================================================================
  两个**独立** store（同名变量在两个 store 里各有一份，别搞混）：
    · `Ze = Hm((t,r)=>({ modals:{...}, …, autoAdventure:!1, pausedByShop:!1,
        pausedByBattle:!1, pausedByReputationEvent:!1, pausedByHeavenEarthSoul:!1,
        pausedByTribulation:!1, … setAutoAdventure:a=>t({autoAdventure:a}), … }))`
        —— UI/运行态 store：autoAdventure + 5 个 pausedBy* 都在这里。
    · `Be = Hm()(dw((t,r)=>({ player:null, …, logs:[], addLog:(a,l)=>{…} })))`
        —— player/logs store：`Be.getState().player` / `Be.getState().addLog` 在这里
        （medlog 用的就是它）。

  驱动组件（@~609000）：
    `function Hw({autoMeditate:t,autoAdventure:r,player:a,loading:l,cooldown:c,
       …, handleMeditate:T,handleAdventure:$,setCooldown:M,autoAdventureConfig:h,
       setAutoAdventure:R,addLog:E}){ … }`
    内部历练循环：
      `O.useEffect(()=>{ if(!r){q.current=!1;return}
         const U=setInterval(async()=>{ window.__ylLifeAuto=Q(); … await k.current(); … },500);
         return()=>{clearInterval(U),A.current.forEach(B=>clearTimeout(B)),A.current=[]}
       },[r,h,R,E])`
    ⇒ 依赖含 `r`（= autoAdventure）。这是**历练启停的唯一收敛点**，与 medlog 盯的
      打坐 effect 并排（打坐是 `},200)`，历练是 `},500)`，可区分）。

  autoAdventure 的写入点（全文共 29 处 `setAutoAdventure`）：
    · 置 true：**一律走 action** `setAutoAdventure(!0)`（全文 `autoAdventure:!0` 出现 0 次）
      —— 用户开启 / 暂停后恢复都经 action。
    · 置 false（**暂停路径**，均为「先/同提交置 pausedBy*，再置 autoAdventure=false」）：
        - 战斗：store action `openTurnBasedBattle` → `t({autoAdventure:!1,pausedByBattle:!0})`（同一 set）
        - 商店：`onOpenShop:Oe=>{ f&&(j(!0),v(!1)), … }`（先 setPausedByShop(!0)，再 setAutoAdventure(!1)）
        - 声望：`onReputationEvent:Oe=>{ … f&&(b(!0),v(!1)), … }`（先 paused，再 autoAdventure）
        - 天地之魄：`onPauseAutoAdventure` → `R(!0),E(!1)`（先 pausedByHeavenEarthSoul，再 autoAdventure）
        - 渡劫：`Ze.setState({autoAdventure:!1,pausedByTribulation:!0})`（同一 set）
    · 置 false（**用户主动关闭**）：
        - 命令/面板切换 `pk`（@~1918915）`L=()=>{… ge?m(!1):…}`（ge=autoAdventure，m=setAutoAdventure）
        - 底部按钮 `onToggleAutoAdventure`（@~1921332）`N?C(!1):(E&&_(!1),A(!0))`
      —— 这两处置 false 时 **不设置任何 pausedBy***。

==========================================================================
三、如何区分「主动关闭」与「临时暂停」（本模块的核心）
==========================================================================
  挂点与 medlog 同款：在 Hw 的历练 interval effect 之后挂一个**依赖 [r] 的旁路 effect**
      `,O.useEffect(()=>{YlxwAdvSession(r)},[r])`
  effect 在每次 `r`（autoAdventure）变化后执行。`YlxwAdvSession(on)`：
    · on === true（false→true）：会话不存在则**开启会话**（记 Date.now()、清累加器）；
      已存在则视为「暂停后恢复」——**保留会话继续累计**（不重置、不输出）。
    · on === false（true→false）：读 `Ze.getState()` 的 5 个 pausedBy*：
        - **任一 pausedBy* 为 true ⇒ 判定为「临时暂停」⇒ 保留会话、不输出、不结束。**
        - **5 个全为 false ⇒ 判定为「用户主动关闭」⇒ 结束会话并按需输出一条汇总。**
  为什么这样能区分（关键依据，见 §二逐字取证）：**所有暂停路径都在 autoAdventure 变 false
  的同一次 React 提交里把对应 pausedBy* 置为 true**（战斗/渡劫是同一个 set 原子写；商店/
  声望/天地之魄是先置 paused 再置 autoAdventure，两次更新被 React 18 自动批处理成同一次
  渲染）。因此旁路 effect 在 off 边沿读 store 时，暂停必然看得见 pausedBy*；而用户主动关闭
  不设任何 pausedBy* ⇒ 5 个全 false。**判据是「off 边沿那一刻的 pausedBy* 快照」，不靠
  计时器、不靠事件来源猜测。**

  会话存续期间的「时长」：按需求原文「从开启自动历练到关闭的这段时间」，用
  `Date.now() - start`（**墙钟**）。因临时暂停不结束会话，暂停时长会被计入 —— 这是
  对「从开启到关闭」的字面实现，见 §六·风险 2。

==========================================================================
四、成果累计挂点（复用 adv097，不改它）
==========================================================================
  adv097（yl_adv097_ext.py）已把历练结算处的那一行日志替换成
      `…, YlxwAdvResultLog(t,m,d), t.lifespanChange&&d(…), …`（在 `Fg` 内，@~1854307）
  其中 `t` 是 **Pc() 跑完之后的对象** ⇒ expChange/spiritStonesChange 是**实际入账值**
  （已含 `_ylExpCap` 钳制与 r044/adv097 的倍率）。
  本模块**不新增第二行**，只在 adv097 的调用**之后**追加一个纯累计调用：
      `YlxwAdvResultLog(t,m,d), YlxwAdvAcc(t), t.lifespanChange&&d(…`
  ⇒ `YlxwAdvResultLog(t,m,d)` 子串**逐字保留**（adv097 的门禁 `==1` 不破）。
  `YlxwAdvAcc(res)`：会话存续时累加 `res.expChange`（仅 >0）/ `res.spiritStonesChange`
  （仅 >0）+ 计数 `runs`；会话不存在则**丢弃**（防手动/弹窗结算污染汇总）。

==========================================================================
五、汇总字段
==========================================================================
  一条日志：「🗺 本次自动历练 <时长>：修为 +N · 灵石 +N · 历练 N 次」
    · 时长   = YlxwAdvDur(Date.now()-start)：≥1h →「X 小时 Y 分」；≥1min →「M 分 S 秒」；否则「S 秒」
    · 修为   = Σ 本次入账 expChange（>0 部分）
    · 灵石   = Σ 本次入账 spiritStonesChange（>0 部分）
    · 历练次数 = 本次结算次数 runs
  · 过短不记：`el < 3000` 直接丢弃（防误触/瞬时开关噪音，与 medlog 同款）。
  · 日志 type 用 "gain"（与 medlog 一致）。

==========================================================================
六、风险点（★ 上报主控）
==========================================================================
  1. ★ 角例：用户**在某个 pausedBy* 仍为 true 时**主动关闭（如战斗中按底部切换按钮，
     `onToggleAutoAdventure` 的 `if(k){C(!1),q(!1);return}` 分支：先 setAutoAdventure(!1)、
     后 setPausedByBattle(!1)）⇒ off 边沿那一刻 pausedByBattle 仍为 true ⇒ 被判为「临时暂停」⇒
     本次不输出汇总（会话保留，下次开启时重置）。属**漏报**，不崩溃、不刷屏。属可接受的边角。
  2. ★ 时长是**墙钟**：临时暂停（战斗/商店/事件弹窗）期间不结束会话，故暂停时长计入
     「历练时长」。这是对需求「从开启到关闭的这段时间」的字面实现；若要「净运行时长」，
     需额外跟踪暂停区间（会引入跨 store 订阅，复杂度与风险更高，本模块刻意不做）。
  3. ★ 跨模块依赖：本模块锚点依赖 ① medlog 的 `function Hw({autoMeditate:t,` 仍在；
     ② adv097 的调用点 `YlxwAdvResultLog(t,m,d),t.lifespanChange&&d(` 仍在。
     **必须排在 V28_MODULES 里 adv097 之后**（否则 ② 锚点不存在 → FAIL）。二者任一改形态
     都要同步本模块锚点。
  4. ★ 两个 store 别混：`Ze`（autoAdventure/pausedBy*）与 `Be`（player/logs/addLog）是不同
     store；本模块读 paused 用 `Ze.getState()`，写日志用 `Be.getState().addLog`。
  5. 会话存续期内的战斗结算（战斗暂停窗口）也会被计入「历练成果」——这是真实收益，
     视为本次历练产出；`runs` 为结算次数（≈自动历练次数）。
  6. 只新建本文件；不改版本号 / build_v26n.py / CHANGELOG* / EXPECT_0811.env / deploy_v28/* /
     srv/index_v28.ts，不改任何已有 yl_*_ext.py（尤其不动 yl_medlog_ext.py / yl_adv097_ext.py）。
     注入块 zh() 后纯 ASCII、无 fetch、不含 V28_BAN_PATTERNS。
  ★ 局部变量刻意与 medlog 不同名（medlog 用 s/h/m/ss/ms/de/ds/tk/a；本模块用
     tot/hh/mm/qq/el/yz/gx/gs/gr/a），避免门禁串（纯字面计数）与 medlog 同款代码相互干扰。

==========================================================================
七、锚点实测 count（基座 build/assets/index-v299-20261001.js，逐字实测）
==========================================================================
  'function Hw({autoMeditate:t,'                                          → 1（注入锚）
  '},500);return()=>{clearInterval(U),A.current.forEach(B=>clearTimeout(B)),A.current=[]}},[r,h,R,E])}function Lw('
                                                                          → 1（历练 effect 收尾）
  'YlxwAdvResultLog(t,m,d),t.lifespanChange&&d('                          → 1（adv097 结算调用点）
  'setAutoAdventure'                                                      → 29（冻结门禁基线值）
  'YlxwAdvSession' / 'YlxwAdvAcc'                                         → 0（改前）
"""

import re

# --------------------------------------------------------------------------- 注入块（纯 ASCII；zh() 后仍纯 ASCII）

INJECT_JS = r'''
/* ===== yl-R105 advend105: one summary log when the user STOPS auto-adventure =====
   Mirrors yl-R023 medlog (which hooks autoMeditate). Here we hook the autoAdventure
   prop of component Hw via a side effect with dependency [r] (r = autoAdventure).
   A session starts on false->true and ends only on a real user stop. Every temporary
   auto-pause (battle / shop / reputation event / heaven-earth-soul / tribulation)
   commits its pausedBy* flag in the SAME React commit that sets autoAdventure=false,
   so on the off-edge we read Ze.getState(): if ANY pausedBy* is true we KEEP the
   session (temporary pause, no log); only when all pausedBy* are false is it a real
   user stop => emit exactly one summary line. Accumulation reuses R-089's settlement
   point (right after the YlxwAdvResultLog call) so the numbers are the amounts
   actually credited. No player field is added (no save-schema change). */
var YLXW_ADV_SESS = null;
var YLXW_ADV_ACC = { exp: 0, stone: 0, runs: 0 };
function YlxwAdvDur(ms) {
  var tot = Math.max(0, Math.floor(Number(ms) || 0) / 1000);
  var hh = Math.floor(tot / 3600), mm = Math.floor((tot % 3600) / 60), qq = Math.floor(tot % 60);
  if (hh > 0) return hh + " \u5c0f\u65f6 " + mm + " \u5206";
  if (mm > 0) return mm + " \u5206 " + qq + " \u79d2";
  return qq + " \u79d2";
}
/* Accumulate one settlement while a session is live; drop otherwise. */
function YlxwAdvAcc(res) {
  if (!YLXW_ADV_SESS) return;
  if (!res || typeof res !== "object") return;
  var de = Math.floor(Number(res.expChange) || 0);
  var ds = Math.floor(Number(res.spiritStonesChange) || 0);
  if (de > 0) YLXW_ADV_ACC.exp += de;
  if (ds > 0) YLXW_ADV_ACC.stone += ds;
  YLXW_ADV_ACC.runs += 1;
}
/* Session boundary driven by the autoAdventure prop (false->true start, true->false end). */
function YlxwAdvSession(on) {
  try {
    if (on) {
      if (!YLXW_ADV_SESS) {
        YLXW_ADV_SESS = { t: Date.now() };
        YLXW_ADV_ACC = { exp: 0, stone: 0, runs: 0 };
      }
      return;
    }
    var st = YLXW_ADV_SESS;
    if (!st) return;
    var yz = Ze.getState();
    if (yz.pausedByBattle || yz.pausedByShop || yz.pausedByReputationEvent ||
        yz.pausedByHeavenEarthSoul || yz.pausedByTribulation) return;  /* temporary pause: keep session */
    YLXW_ADV_SESS = null;
    var el = Math.max(0, Date.now() - st.t);
    if (el < 3000) return;
    var a = YLXW_ADV_ACC, gr = a.runs;
    var gx = Math.floor(a.exp), gs = Math.floor(a.stone);
    var add = Be.getState().addLog;
    if (typeof add !== "function") return;
    add("\ud83d\uddfa \u672c\u6b21\u81ea\u52a8\u5386\u7ec3 " + YlxwAdvDur(el)
      + "\uff1a\u4fee\u4e3a +" + gx.toLocaleString()
      + " \u00b7 \u7075\u77f3 +" + gs.toLocaleString()
      + " \u00b7 \u5386\u7ec3 " + gr + " \u6b21", "gain");
  } catch (e) {}
}
'''

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# 注入锚：模块级函数声明 `function Hw(`，与 medlog 同锚（medlog 亦在其前注入）。
#   ★ 本模块沿用 bt096 的「INJECT_BEFORE_ANCHOR + build 侧补插」形态，故 apply() 内不再自行插入。
INJECT_BEFORE_ANCHOR = 'function Hw({autoMeditate:t,'

# ① 历练 interval effect 收尾（`},500)` 与打坐 `},200)` 区分；后随 `}function Lw(` 收尾，
#    把它纳入锚点，替换后旧形态才真正清零（否则旧串是新串的前缀）。
EFFECT_OLD = ('},500);return()=>{clearInterval(U),A.current.forEach(B=>clearTimeout(B)),'
              'A.current=[]}},[r,h,R,E])}function Lw(')
EFFECT_NEW = ('},500);return()=>{clearInterval(U),A.current.forEach(B=>clearTimeout(B)),'
              'A.current=[]}},[r,h,R,E]),O.useEffect(()=>{YlxwAdvSession(r)},[r])}function Lw(')

# ② 历练结算调用点（adv097 注入的整式）：在其后追加纯累计调用。
#    `YlxwAdvResultLog(t,m,d)` 子串逐字保留 ⇒ adv097 的门禁不被打破。
ACC_OLD = 'YlxwAdvResultLog(t,m,d),t.lifespanChange&&d('
ACC_NEW = 'YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),t.lifespanChange&&d('

# 注入块禁词（与 build 的 V28_BAN_PATTERNS 对齐）
BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}

    ★ INJECT_JS 由 build 侧按 INJECT_BEFORE_ANCHOR 自动 zh() 并补插（bt096 形态），
      故本函数**不再自行插入注入块**，只做两处就地替换 + 门禁。
    """
    zh = ctx['zh']

    # 自检 1：替换串必须真的变了（防手滑写成恒等）
    if EFFECT_OLD == EFFECT_NEW or 'YlxwAdvSession(r)' not in EFFECT_NEW:
        raise AssertionError('advend105 锚点异常：历练 effect 未挂 YlxwAdvSession 旁路')
    if ACC_OLD == ACC_NEW or 'YlxwAdvAcc(t)' not in ACC_NEW:
        raise AssertionError('advend105 锚点异常：结算点未追加 YlxwAdvAcc')
    if 'YlxwAdvResultLog(t,m,d)' not in ACC_NEW:
        raise AssertionError('advend105 锚点异常：必须逐字保留 YlxwAdvResultLog(t,m,d)（adv097 门禁）')

    # 自检 2：注入块 zh() 后纯 ASCII 且不含禁用模式
    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('advend105 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for pat in BAN_PATTERNS:
        if pat in blk:
            raise AssertionError('advend105 注入块含禁用模式 %r' % pat)
    if 'fetch(' in blk:
        raise AssertionError('advend105 注入块不得含 fetch(')

    # 1) 在历练 interval effect 之后挂旁路 effect（依赖 [r]=autoAdventure）
    p.replace('advend105-session-effect', EFFECT_OLD, EFFECT_NEW, expect=1,
              note='历练启停旁路 effect：autoAdventure 变化即驱动 YlxwAdvSession')

    # 2) 在 adv097 的结算调用之后追加纯累计调用（不新增第二行日志）
    p.replace('advend105-acc', ACC_OLD, ACC_NEW, expect=1,
              note='每次历练结算就地累计（修为/灵石/次数），不改日志行')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 注入块（新形态 ==1） =================
        ('R105·时长文案函数已注入',   'function YlxwAdvDur(ms) {',                       1, '==', ''),
        ('R105·累计函数已注入',       'function YlxwAdvAcc(res) {',                      1, '==', ''),
        ('R105·会话函数已注入',       'function YlxwAdvSession(on) {',                   1, '==', ''),
        ('R105·会话状态变量',         'var YLXW_ADV_SESS = null;',                       1, '==', ''),
        ('R105·累加器变量',           'var YLXW_ADV_ACC = { exp: 0, stone: 0, runs: 0 };', 1, '==', ''),
        ('R105·开始清累加器',         'YLXW_ADV_ACC = { exp: 0, stone: 0, runs: 0 };',    2, '==', 'var 初始化 + 会话起点清零'),

        # ================= 区分「主动关闭 vs 临时暂停」（核心） =================
        ('R105·暂停判据=读 Ze 的 paused 快照', 'var yz = Ze.getState();',                 1, '==', '与 Be(玩家/日志) 是两个 store'),
        ('R105·5 个 pausedBy* 全查',  'if (yz.pausedByBattle || yz.pausedByShop || yz.pausedByReputationEvent ||', 1, '==', ''),
        ('R105·暂停则保留会话',       'yz.pausedByTribulation) return;  /* temporary pause: keep session */', 1, '==', '任一暂停标志 ⇒ 不结束、不输出'),
        ('R105·仅主动关闭才结算',     'YLXW_ADV_SESS = null;',                           2, '==', '声明 1 + off 边沿结束 1（★ 仅当 5 个 paused 全 false 才走到）'),
        ('R105·会话存续时保留',       'if (!YLXW_ADV_SESS) {',                           1, '==', 'false→true 时：已存在则视为恢复、不重置'),

        # ================= 累计（成果取自 adv097 实际入账值） =================
        ('R105·累计修为',             'if (de > 0) YLXW_ADV_ACC.exp += de;',             1, '==', 'res.expChange（仅 >0）'),
        ('R105·累计灵石',             'if (ds > 0) YLXW_ADV_ACC.stone += ds;',           1, '==', 'res.spiritStonesChange（仅 >0）'),
        ('R105·累计次数',             'YLXW_ADV_ACC.runs += 1;',                         1, '==', 'runs = 本次结算次数'),
        ('R105·会话外丢弃',           'if (!YLXW_ADV_SESS) return;',                     1, '==', '防手动/弹窗结算污染汇总'),

        # ================= 一条汇总 =================
        ('R105·写日志',               r'add("\ud83d\uddfa ',                             1, '==', '复用既有 addLog（只读+写日志）'),
        ('R105·日志含时长',           r'\u672c\u6b21\u81ea\u52a8\u5386\u7ec3 " + YlxwAdvDur(el)', 1, '==', '字段①：本次自动历练 <时长>'),
        ('R105·日志含修为',           r'"\uff1a\u4fee\u4e3a +" + gx.toLocaleString()',    1, '==', '字段②：修为 +N'),
        ('R105·日志含灵石',           r'" \u00b7 \u7075\u77f3 +" + gs.toLocaleString()',  1, '==', '字段③：灵石 +N'),
        ('R105·日志含历练次数',       r'" \u00b7 \u5386\u7ec3 " + gr + " \u6b21"',        1, '==', '字段④：历练 N 次'),
        ('R105·过短不记（3s）',       'if (el < 3000) return;',                          1, '==', '防误点/瞬时开关噪音'),
        ('R105·时长≥1h 用「小时/分」', r'return hh + " \u5c0f\u65f6 " + mm + " \u5206";',  1, '==', 'X 小时 Y 分'),

        # ================= 挂点（新形态 ==1 / 旧形态 ==0） =================
        ('R105·旁路 effect 已挂',     ',O.useEffect(()=>{YlxwAdvSession(r)},[r])}function Lw(', 1, '==', ''),
        ('R105·旧 effect 收尾已清零', EFFECT_OLD,                                        0, '==', '旧形态必须为 0'),
        ('R105·结算累计已挂',         ACC_NEW,                                           1, '==', ''),
        ('R105·旧结算点形态已清零',   ACC_OLD,                                           0, '==', '旧形态必须为 0'),

        # ================= 冻结：不得动别人的面 =================
        ('冻结·adv097 调用点逐字保留', 'YlxwAdvResultLog(t,m,d)',                         1, '==', '本模块只在其后追加，子串不动'),
        ('冻结·adv097 日志函数仍在',   'function YlxwAdvResultLog(res, advType, addLog) {', 1, '==', '不改 yl_adv097_ext.py'),
        ('冻结·medlog 日志仍在',       r'Be.getState().addLog("\ud83e\uddd8',             1, '==', '不改 yl_medlog_ext.py'),
        ('冻结·medlog 会话变量仍在',   'var YLXW_MED_SESS = null;',                       1, '==', ''),
        ('冻结·setAutoAdventure setter 未动', 'setAutoAdventure:a=>t({autoAdventure:a})', 1, '==', '本模块不改开关'),
        ('冻结·paused 初值未动',       'pausedByShop:!1,pausedByBattle:!1,pausedByReputationEvent:!1,pausedByHeavenEarthSoul:!1,pausedByTribulation:!1', 1, '==', ''),
        # ★ 关键冻结：确保 setAutoAdventure 既有调用次数未异常变化（实测基线值 29）
        ('冻结·setAutoAdventure 调用点未增减', 'setAutoAdventure',                        29, '==', '本模块不新增/删除任何 setAutoAdventure 调用点'),

        # ================= 限域：注入块内不得出现网络调用 =================
        ('R105·注入块内无网络调用',   'fetch(',                                          0, '==', '纯客户端',
         ('/* ===== yl-R105 advend105:', 'function Hw({autoMeditate:t,')),
    ]
    return gates
