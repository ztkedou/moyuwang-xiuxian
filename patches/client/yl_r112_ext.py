# -*- coding: utf-8 -*-
r"""
yl_r112_ext.py — R-112 灵玉产出扩渠道：打坐 / 历练 低概率掉玉（打坐最低，历练略高）

需求原文（台账 R-112，用户 2026-10-02，逐字）
--------------------------------------------------------------------------
    「灵玉产出的产出，打坐、历练也会获得，打坐几率最低，历练比打坐获得几率略高一点。」

==============================================================================
一、改前取证（基线 build/assets/index-v2911-20261001.js，只读 grep，逐字节）
==============================================================================
基线 = 现有全链产物（含 r106 / r107 / r108 / r109，作用面「0.9.11」）。

【1】灵玉是什么、在哪儿产出的
--------------------------------------------------------------------------
灵玉 = 活动中心「灵玉阁」的**代币**，服务端权威：
  · 表 `activity_token`，键 `ACT_TOKEN_KEY = 'lingyu'`（srv/index_v28.ts:470xxx）。
  · 产出唯一挂点 `actDropTokens(userId, stonesSettled, now)`：
      只认活跃 `token_shop` 场次；`floor(结算灵石 × 50 / 10000)`；日上限 300。
    当前**只有 3 个服务端结算点**调它：
      ① 炼丹出炉（yieldStones） ② 灵田收获（gain.stones） ③ 离线收益（applied.stonesGain）。
  · 客户端**没有**任何灵玉字段：bundle 内 `jadeBalance` / `灵玉` 均只出现在
      act087 注入区（`YLACT_LAST_JADE` 掉玉 toast + 灵玉阁面板文案，均读服务端回包）。
  · 服务端回包字段名 = `jadeBalance`（v2810 顶层 `balance` 改名）——
      ★ 0.8.10 资损教训：顶层 `balance` 曾与**灵石** `balance` 撞名，客户端把灵玉余额
        当灵石采纳，导致灵石显示被清零。故本模块新字段**一律叫 `jadeBalance`**，
        绝不复用 `balance` / `spiritStones`。

【2】为什么打坐 / 历练加不了「服务端」掉玉（架构事实，逐字取证）
--------------------------------------------------------------------------
  srv/index_v28.ts 自述（@211519）：
    「客户端权威存档架构下，打坐/历练/战斗结算都在客户端跑，服务端唯一可见的
      结算汇聚点是存档上传」
  ⇒ 打坐 / 历练**没有服务端结算端点**，`actDropTokens` 无法被它们触发；
    服务端只通过 `/api/save` 看到 `statistics.meditateCount / adventureCount` 差值。
    要真正进灵玉阁余额，必须**服务端**新增一条基于存档差值的掉玉挂点
    （本模块无权改 srv/index_v28.ts，已在报告「未决问题」标红）。

【3】两个客户端结算点（本模块就地挂载处，均实测 count==1）
--------------------------------------------------------------------------
  · 打坐：`handleMeditate`（RS 内 `l($=>{…})` 函数式 updater，@724270 起）。
      结算出口（life094 应用后的形态）：
        `return{...$,exp:$.exp+S,hp:k,spiritStones:w,
                lifespan:Math.max(0,($.lifespan??$.maxLifespan??100)-YLXW_MED_LIFE),
                statistics:{...A,meditateCount:A.meditateCount+1}}}`
      循环：`setInterval(…,200)` + 每跳 `setCooldown(2)` ⇒ 约 **2s / 跳 ≈ 30 跳/分**。
  · 历练：`Pc(t,r,a)`（@1856324，`Fg` 内 `c(k=>Pc(k,t,{…}))` 调用）入账行：
        `S.exp=Math.max(0,t.exp+(r.expChange||0)),
         S.spiritStones=Math.max(0,t.spiritStones+(r.spiritStonesChange||0)),
         S.reputation=…`
      循环：`setInterval(…,500)` + 每轮 `d(4)` ⇒ 约 **4s / 次 ≈ 900 次/小时**。

==============================================================================
二、方案（本模块动作）
==============================================================================
注入 4 个顶层 helper（函数声明提升，RS / Pc 同处一个顶层作用域 ⇒ 均可见）：

    var YLXW_JADE_MED_CHANCE  = 0.004;   /* 打坐 每跳(约 2s) 掉玉几率 */
    var YLXW_JADE_ADV_CHANCE  = 0.009;   /* 历练 每次(约 4s) 掉玉几率 */
    var YLXW_JADE_DROP_AMOUNT = 1;       /* 每次掉落灵玉数 */
    function YlxwJadeRoll(chance)        /* 概率 roll，恒返回 0 或正整数，绝不 NaN */
    function YlxwJadeGrant(chance, key)  /* roll 命中则 YlxwToast「灵玉 +N」并返回数量 */
    function YlxwJadeDropMed()           /* 打坐口：roll MED_CHANCE */
    function YlxwJadeDropAdv()           /* 历练口：roll ADV_CHANCE */

两处就地替换（入账字段 `jadeBalance`，与既有口径一致）：
  ① 打坐 updater 出口：`lifespan:…-YLXW_MED_LIFE),statistics:{…}`
     → `lifespan:…-YLXW_MED_LIFE),jadeBalance:($.jadeBalance||0)+YlxwJadeDropMed(),statistics:{…}`
  ② 历练 Pc 入账行：`S.spiritStones=…,S.reputation=…`
     → `S.spiritStones=…,S.jadeBalance=Math.max(0,(t.jadeBalance||0)+YlxwJadeDropAdv()),S.reputation=…`

概率取值与量级（写进常量，便于后续调参）：
  ┌────────┬──────────┬──────────────┬─────────────┬─────────────┐
  │ 渠道   │ 每跳/次率│ 频率         │ 期望/小时   │ 备注        │
  ├────────┼──────────┼──────────────┼─────────────┼─────────────┤
  │ 打坐   │ 0.4%     │ ≈1800 跳/时  │ ≈ 7.2 玉/时 │ **最低**    │
  │ 历练   │ 0.9%     │ ≈ 900 次/时  │ ≈ 8.1 玉/时 │ 比打坐略高  │
  └────────┴──────────┴──────────────┴─────────────┴─────────────┘
  ⇒ 满足用户口径「打坐几率最低，历练比打坐略高一点」（单次率 0.4% < 0.9%）。
  ⚠ 频率不对称：打坐跳数是历练次数的 2 倍 ⇒ 若只按「单次率」比，打坐小时总量会反超。
    故历练单次率取打坐的 ≈2.25 倍，使**小时期望**亦为「历练 ≥ 打坐」（7.2 vs 8.1）。
    若要严格按「单次率略高」而不管小时总量，把 ADV 调到 0.005~0.006 即可（单点常量）。

「在结算日志里体现」：命中时调用 `YlxwToast("灵玉 +N","gain",key)`（沿用 act087 掉玉
toast 的 kind/key 口径），瞬时可见、不新增日志刷屏（历练 4s/次，若写日志会 900 行/时）。

==============================================================================
三、★ 残留风险 / 未决问题（必须上报主控）
==============================================================================
A. ★★ 服务端权威缺口（最重要）：灵玉余额真值在服务端 `activity_token`（key `lingyu`），
   由 `actDropTokens` 写入；而打坐/历练在客户端结算、服务端只能从 `/api/save` 差值看到。
   ⇒ 本模块把掉玉记入**客户端** `player.jadeBalance`，**不会**进入灵玉阁余额/日上限 300。
     要真正闭环，需服务端新增挂点（建议：`/api/save` 结算处按
     `Δstatistics.meditateCount / ΔadventureCount` 各 roll 一次并调 `actDropTokens`，
     概率与 `YLXW_JADE_*_CHANCE` 同源；本模块**不改 srv**，故留作未决）。
     在服务端挂点落地前，本模块的效果 = 客户端掉玉提示 + `jadeBalance` 字段累积。
B. `player.jadeBalance` 是**新字段**，服务端存档会原样保存（未知字段不报错），但灵玉阁面板
   读的是 `/api/activity/shop` 的 `jadeBalance`（服务端 activity_token），两者**不同源**。
   本模块不碰 act087 面板（那是 R-055 的面），避免制造「显示 == 实付」的假象。
C. 打坐/历练频率（2s vs 4s）不对称，见 §二 表下注；若用户想要的是「小时总量」口径，
   按上表调 ADV 常量即可（单点）。
D. 附带发现（**非 R-112 范围，仅记录**）：act087 灵玉阁面板读的是 `d.balance`，而 v2810
   服务端已把顶层字段改名 `jadeBalance` ⇒ 客户端 `bal` 恒为 null、面板「我的灵玉」恒显示 0。
   这是显示侧 bug，属 act087/R-055 面，本模块**不动**，建议另立需求。

==============================================================================
四、跨模块门禁核对（全仓 grep，本模块只做「前缀保持型」插入，不破他人断言）
==============================================================================
  · `yl_life094_ext.py`：gate `('life094·打坐扣寿元已接入',
      'lifespan:Math.max(0,($.lifespan??$.maxLifespan??100)-YLXW_MED_LIFE)', 1)`
    ⇒ 本模块把 `jadeBalance:…` 插在 `-YLXW_MED_LIFE),` 与 `statistics:` **之间**，
      该子串逐字保留，**==1 不变**；其旧形态门禁（MED_OLD ==0）仍为 0。
  · `yl_r114_ext.py`（同批并行）：gate `('冻结·Pc 灵石入账未动',
      'S.spiritStones=Math.max(0,t.spiritStones+(r.spiritStonesChange||0))', 1)`
    ⇒ 本模块在 `S.spiritStones=…` 与 `S.reputation=…` 之间插入 `S.jadeBalance=…`，
      该子串逐字保留，**==1 不变**。
  · `yl_adv097_ext.py`：其冻结面 `YlxwAdvResultLog(t,m,d)` / `Math.random()<.004` /
      `YLXW_ADV_STONE_MUL_R97` 等本模块一字未碰。
  · `yl_eco085_ext.py` / `yl_toast083_ext.py` / `yl_numbal_ext.py`：与本模块锚区零交集。
  · deploy_v28 / localtest / EXPECT_0811.env：无本模块 needle 引用。
  ⇒ **无跨模块门禁冲突**。

锚点纪律：3 个锚点（注入锚 + 2 个替换锚）实测 count 均为 1；所有 needle 逐字核过基线。
本模块只新建本文件；不改版本号 / build_v26n.py / CHANGELOG* / EXPECT / deploy_v28/* /
localtest/* / srv/index_v28.ts / 任何已有 yl_*_ext.py。注入块 zh() 后纯 ASCII、无 fetch、
不含 V28_BAN_PATTERNS。
"""

import re

# --------------------------------------------------------------------------- 可调常量（单点调参）

JADE_MED_CHANCE = '0.004'   # 打坐 每跳(约 2s) 掉玉几率 0.4%
JADE_ADV_CHANCE = '0.009'   # 历练 每次(约 4s) 掉玉几率 0.9%（比打坐略高）
JADE_DROP_AMOUNT = '1'      # 每次掉落灵玉数量

# --------------------------------------------------------------------------- 注入块（纯 ASCII）

# 注入位：RS 为顶层函数声明，其前后即模块作用域（YlxwToast 定义于此区）。
# 本块用**函数声明**（提升），故 RS / Pc（顶层 const）内均可直接调用。
INJECT_ANCHOR = 'function RS(t){return Be(a=>a.player)'

INJECT_JS = r'''
/* == YL_R112 == R-112: 打坐/历练 低概率掉落灵玉（jade）。
   灵玉 = 活动中心「灵玉阁」代币（服务端 activity_token, key "lingyu"）。
   本块只做【客户端】掉玉 roll + 提示，入账到 player.jadeBalance。
   ★ 字段名严格用 jadeBalance：0.8.10 曾因顶层 balance 与灵石撞名造成资损。 */
var YLXW_JADE_MED_CHANCE = __MED__;   /* 打坐 每跳(约 2s) 掉玉几率 */
var YLXW_JADE_ADV_CHANCE = __ADV__;   /* 历练 每次(约 4s) 掉玉几率（略高于打坐） */
var YLXW_JADE_DROP_AMOUNT = __AMT__;  /* 每次掉落灵玉数 */
function YlxwJadeRoll(chance) {
  try {
    var c = Number(chance);
    if (!isFinite(c) || c <= 0) return 0;
    if (Math.random() >= c) return 0;
    var n = Math.floor(Number(YLXW_JADE_DROP_AMOUNT) || 1);
    return n > 0 ? n : 1;
  } catch (e) { return 0; }
}
function YlxwJadeGrant(chance, key) {
  var g = YlxwJadeRoll(chance);
  if (g > 0) {
    try { YlxwToast("\u7075\u7389 +" + g, "gain", key); } catch (e) {}
  }
  return g;
}
function YlxwJadeDropMed() { return YlxwJadeGrant(YLXW_JADE_MED_CHANCE, "r112-jade-med"); }
function YlxwJadeDropAdv() { return YlxwJadeGrant(YLXW_JADE_ADV_CHANCE, "r112-jade-adv"); }
'''.replace('__MED__', JADE_MED_CHANCE).replace('__ADV__', JADE_ADV_CHANCE) \
   .replace('__AMT__', JADE_DROP_AMOUNT)

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# ① 打坐 updater 出口（life094 应用后的形态）：在 `-YLXW_MED_LIFE),` 与 `statistics:` 之间插入 jadeBalance
MED_OLD = ('lifespan:Math.max(0,($.lifespan??$.maxLifespan??100)-YLXW_MED_LIFE),'
           'statistics:{...A,meditateCount:A.meditateCount+1}')
MED_NEW = ('lifespan:Math.max(0,($.lifespan??$.maxLifespan??100)-YLXW_MED_LIFE),'
           'jadeBalance:($.jadeBalance||0)+YlxwJadeDropMed(),'
           'statistics:{...A,meditateCount:A.meditateCount+1}')

# ② 历练 Pc 入账行：在 `S.spiritStones=…` 与 `S.reputation=…` 之间插入 jadeBalance
ADV_OLD = ('S.spiritStones=Math.max(0,t.spiritStones+(r.spiritStonesChange||0)),'
           'S.reputation=Math.max(0,(t.reputation||0)+(r.reputationChange||0)),')
ADV_NEW = ('S.spiritStones=Math.max(0,t.spiritStones+(r.spiritStonesChange||0)),'
           'S.jadeBalance=Math.max(0,(t.jadeBalance||0)+YlxwJadeDropAdv()),'
           'S.reputation=Math.max(0,(t.reputation||0)+(r.reputationChange||0)),')

# --------------------------------------------------------------------------- 冻结面（只读，别人的断言）

FRZ_MED_LIFE = 'lifespan:Math.max(0,($.lifespan??$.maxLifespan??100)-YLXW_MED_LIFE)'
FRZ_MED_LIFE_CONST = 'var YLXW_MED_LIFE = 0.001;'
FRZ_PC_STONE = 'S.spiritStones=Math.max(0,t.spiritStones+(r.spiritStonesChange||0))'
FRZ_PC_REP = 'S.reputation=Math.max(0,(t.reputation||0)+(r.reputationChange||0)),'
FRZ_MED_STONE = '__ylsq=YlxwMedStone2(q,$.realmLevel,C),'
FRZ_ADV_LOG = 'YlxwAdvResultLog(t,m,d)'
FRZ_MED_INSIGHT = 'Math.random()<.004'
FRZ_MED_CNT = 'meditateCount:A.meditateCount+1'
FRZ_RS_SIG = 'function RS(t){return Be(a=>a.player)'
FRZ_ACT087_JADE_TOAST = r'YlxwToast("\u7075\u7389 +" + (bal - YLACT_LAST_JADE)'
FRZ_SHOP_DEF = 'function YlxwTActShop('


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检 1：替换串必须真的变了（防手滑写成恒等）
    if MED_OLD == MED_NEW or 'YlxwJadeDropMed' not in MED_NEW:
        raise AssertionError('r112 锚点异常：打坐出口未插入 jadeBalance')
    if ADV_OLD == ADV_NEW or 'YlxwJadeDropAdv' not in ADV_NEW:
        raise AssertionError('r112 锚点异常：历练入账未插入 jadeBalance')
    # 自检 2：新串不得用灵石口径（撞名红线）
    if 't.balance' in (MED_NEW + ADV_NEW) or 'spiritStones:' in MED_NEW:
        raise AssertionError('r112 锚点异常：疑似误用灵石字段（balance / spiritStones）')
    # 自检 3：打坐掉率必须 < 历练掉率（用户口径）
    if not (float(JADE_MED_CHANCE) < float(JADE_ADV_CHANCE)):
        raise AssertionError('r112 常量异常：打坐掉率必须低于历练掉率')

    blk = zh(INJECT_JS)
    # 自检 4：注入块 zh() 后纯 ASCII 且不含禁用模式
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r112 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for pat in BAN_PATTERNS:
        if pat in blk:
            raise AssertionError('r112 注入块含禁用模式 %r' % pat)
    if 'fetch(' in blk:
        raise AssertionError('r112 注入块不得含 fetch(')

    # 0) 注入掉玉常量 + roll/入账 helper（顶层；RS / Pc 同作用域，函数声明提升）
    p.insert_before('r112-jade-block', INJECT_ANCHOR, blk + '\n', expect=1,
                    note='注入 YLXW_JADE_*_CHANCE / YLXW_JADE_DROP_AMOUNT / '
                         'YlxwJadeRoll / YlxwJadeGrant / YlxwJadeDropMed / YlxwJadeDropAdv')

    # ① 打坐：每跳低概率掉玉，入账 player.jadeBalance
    p.replace('r112-med-jade', MED_OLD, MED_NEW, expect=1,
              note='打坐出口插入 jadeBalance += YlxwJadeDropMed()（保留 -YLXW_MED_LIFE 面）')

    # ② 历练：每次低概率掉玉，入账 player.jadeBalance
    p.replace('r112-adv-jade', ADV_OLD, ADV_NEW, expect=1,
              note='历练 Pc 入账行插入 jadeBalance += YlxwJadeDropAdv()（保留灵石/声望面）')

    return [
        # ================= 注入块：新形态（==1） =================
        ('R112·打坐掉率常量已注入',   'var YLXW_JADE_MED_CHANCE = %s;' % JADE_MED_CHANCE,
         1, '==', '打坐 每跳(约2s) 0.4%%'),
        ('R112·历练掉率常量已注入',   'var YLXW_JADE_ADV_CHANCE = %s;' % JADE_ADV_CHANCE,
         1, '==', '历练 每次(约4s) 0.9%%（比打坐略高）'),
        ('R112·掉落量常量已注入',     'var YLXW_JADE_DROP_AMOUNT = %s;' % JADE_DROP_AMOUNT,
         1, '==', '每次掉落灵玉数'),
        ('R112·roll 函数已定义',      'function YlxwJadeRoll(chance)',   1, '==',
         '恒返回 0 或正整数，绝不 NaN'),
        ('R112·入账 helper 已定义',   'function YlxwJadeGrant(chance, key)', 1, '==', ''),
        ('R112·打坐 helper 已定义',   'function YlxwJadeDropMed()',      1, '==', ''),
        ('R112·历练 helper 已定义',   'function YlxwJadeDropAdv()',      1, '==', ''),
        ('R112·打坐已入账 jadeBalance',
         'jadeBalance:($.jadeBalance||0)+YlxwJadeDropMed(),',           1, '==',
         '打坐每跳结算追加灵玉'),
        ('R112·历练已入账 jadeBalance',
         'S.jadeBalance=Math.max(0,(t.jadeBalance||0)+YlxwJadeDropAdv()),', 1, '==',
         '历练每次结算追加灵玉'),
        ('R112·掉玉 toast 已就绪',    r'"\u7075\u7389 +" + g',           1, '==',
         '与 act087 掉玉 toast 同 kind（gain）'),
        ('R112·字段口径为 jadeBalance', 'jadeBalance',                   4, '>=',
         '代码面 ≥4 处（MED 2 + ADV 2）；严禁 balance / spiritStones 撞名'),

        # ================= 旧形态（==0） =================
        ('R112·旧打坐出口已清零',     MED_OLD,                            0, '==',
         '打坐出口已含 jadeBalance 追加'),
        ('R112·旧历练入账已清零',     ADV_OLD,                            0, '==',
         '历练入账已含 jadeBalance 追加'),
        ('R112·未误用灵石 balance',   'jadeBalance=Math.max(0,(t.balance||0)', 0, '==',
         '撞名红线：jadeBalance 不得读 t.balance'),

        # ================= 冻结：别人的面（==1） =================
        ('冻结·life094 打坐扣寿元未动', FRZ_MED_LIFE,                     1, '==',
         '本模块只在其后插 jadeBalance，子串逐字保留'),
        ('冻结·life094 打坐常量未动',   FRZ_MED_LIFE_CONST,               1, '==', ''),
        ('冻结·R114 Pc 灵石入账未动',   FRZ_PC_STONE,                     1, '==',
         '本模块只在其后插 S.jadeBalance，子串逐字保留'),
        ('冻结·Pc 声望入账未动',        FRZ_PC_REP,                       1, '==', ''),
        ('冻结·R024 打坐灵石未动',      FRZ_MED_STONE,                    1, '==', ''),
        ('冻结·打坐统计计数未动',       FRZ_MED_CNT,                      1, '==', ''),
        ('冻结·RS 打坐处理器签名未动',  FRZ_RS_SIG,                       1, '==',
         '注入锚所在行原样保留'),
        ('冻结·adv097 成果日志未动',    FRZ_ADV_LOG,                      1, '==',
         'R-089 / R-105 / R-114 共同断言面'),
        ('冻结·adv097 打坐顿悟率未动',  FRZ_MED_INSIGHT,                  1, '==',
         'R-090 面，本模块不碰'),
        ('冻结·act087 掉玉 toast 未动', FRZ_ACT087_JADE_TOAST,            1, '==',
         '灵玉阁面板 toast（本模块新增的是不同串）'),
        ('冻结·灵玉阁面板未动',         FRZ_SHOP_DEF,                     1, '==',
         'R-055 面；本模块不碰面板'),
    ]
