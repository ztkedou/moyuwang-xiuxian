# -*- coding: utf-8 -*-
r"""
yl_r076_ext.py — R-076 秘境：**roguelike 地宫单轮奖励 = 普通点选单次 × 2**

需求原文（需求台账_进行中.md L25，R-076，附图列空）
--------------------------------------------------------------------------
  「roguelike 秘境的奖励为普通秘境的 2 倍。」

现状复算（基座产物 build/assets/index-v291-20261001.js，逐字实证；脚本 _calc_r076c.py）
--------------------------------------------------------------------------
  两条入口**共享同一条 15 分钟冷却**（R-062 拍板，双端同改），所以「单轮/单次」之比
  == 「每小时收益」之比（CD 限速下都是 4 次/h）。

  普通点选（1 次 = 1 个事件结算，Fm→Ym，R-062 后 ×3）：
      u = C_NORM[a] × (1+(层-1)×0.3)，灵石/修为 = 四档风险均值 × u × 3
      炼气 L1：灵石 2662 / 修为 1331（逐字复算）

  roguelike（1 轮 = N 层，每层 3 选 1；N = randint(5, min(12,max(5,(a+3)*2)))）：
      c = YLRF(a)×(1+层×0.2)×1.63666（灵石线，G3 @481043）
      灵石线 battle/treasure/merchant/boss/mystery；修为线 battle/treasure/heal/boss/mystery
      按「理性玩家取 3 选里灵石最高者」建模（灵石向最保守上界）：
      炼气 L1：灵石 6568 / 修为 4466

  ⇒ **现状差距（灵石）：炼气 2.47× / 筑基 5.89× / 金丹 10.19× / 元婴 14.36× /
     化神 15.03× / 合道 14.80× / 长生 14.12×**（修为差距 3.36× ~ 10331×）。
     境界越高差距越大——roguelike 灵石线挂 YLRF（近线性 1.33→13），
     修为线挂 a.maxExp（每境界约 ×4），而普通点选两线都挂 C_NORM（1→3.58）。

本模块动作（1 注入 + 1 就地替换）
--------------------------------------------------------------------------
  ① 注入分境界倍率表 YLXW_ROGUE_GAIN_R76 = 2 / (现状灵石比值)，逐境界精确把
     roguelike 单轮压到「普通点选单次 ×2」（灵石线精确 2×；修为线按同一因子同比例下调）。
  ② G3 返回语句把 expGain / spiritStoneGain 各乘该因子（hpChange / items / 日志不动）。

  ★ 方向选择：**压 roguelike，不抬普通**。理由：R-062 刚把普通 ×3；若再抬普通到
    2× 水位，元婴需 ×7.2 ⇒ 直接放大灵石水龙头，与「本轮刚压过产出」相悖。
    压 roguelike 是净回收，经济方向安全（roguelike 灵石线现状为全站最大单点水龙头之一）。

经济复算（炼气 L1 → 长生，灵石/轮；改前 → 改后）
--------------------------------------------------------------------------
  境界     普通/次(×3)   rogue改前   rogue改后   rogue/普通(改后)
  炼气       2662          6568        5322        2.00
  筑基       3293         19393        6594        2.00
  金丹       4074         41520        8148        2.00
  元婴       5039         72371       10100        2.00
  化神       6233         93669        12465        2.00
  合道       7709        114134        15418        2.00
  长生       9536        134635        19072        2.00
  ⇒ 每小时（CD 4 次/h）：炼气 rogue 2.63万→2.13万；元婴 28.9万→4.04万（普通 2.02万）。
  修为同因子下调（元婴 71.6万→9.95万/轮），但因原修为线挂 maxExp，修为比值仍 >2×
  （元婴 284×→40×），**修为线无法用同一张表压到 2×**，属遗留（见拍板）。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 不碰 R-062 面：`*1.63666;`（roguelike 收益基数）、`var YLXW_SR_GAIN_R62 = 3;`、
    弹窗结算点 `YlxwSrBoostR62` 包裹——全部逐字冻结门禁。
  · 不碰 R-063 面：U3 定义、层数封顶调用点、rogue 上限表 [3..13] —— 逐字冻结。
  · 只改 G3 的 **返回语句**，不改 G3 的 c= 计算式（那行是 R-062/R-063 门禁锚）。
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS；无 fetch。
  · 每个 replace 带 expect= 精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py / localtest/ / deploy_v28/ / srv/index_v28.ts / 产物。
  · 装配序：无硬依赖（G3 是基座原生函数，全链无其它模块改它）；排在 numbal 之前即可。
"""

import re

# --------------------------------------------------------------------------- 可调常量
# 分境界倍率 = 2 / 现状(roguelike 单轮灵石 / 普通点选单次灵石)；炼气→长生（fe 同序）。
# 调参只改这一行（自动拼进 INJECT_JS 与门禁）。
R076_MUL = [0.81, 0.34, 0.20, 0.14, 0.13, 0.14, 0.14]

# --------------------------------------------------------------------------- 注入块（纯 ASCII）

INJECT_JS = r'''
/* ===== yl-R076: roguelike dungeon reward = 2x the popup secret realm =====
   User R-076: the roguelike secret realm reward should be 2x the normal
   (individually-selected) secret realm. Both entries share the same 15-min
   cooldown (R-062), so per-run ratio == per-hour ratio.
   Scope guard: scales ONLY the G3() reward return (roguelike dungeon events).
   NOT touched: the popup realm settlement (YlxwSrBoostR62 / R-062), the G3
   base factor c=YLRF(a)*(1+floor*0.2)*1.63666, the U3() floor roll (R-063),
   and hpChange / items / battle flags inside G3.
   Per-realm factor = 2 / (roguelike-run stones / popup stones); applied to both
   expGain and spiritStoneGain; identity on any malformed realm index. */
var YLXW_ROGUE_GAIN_R76 = %(TBL)s;
function YlxwRogueMulR76(l) {
  try {
    var i = Math.floor(Number(l));
    if (!(i >= 0)) { i = 0; }
    if (i > YLXW_ROGUE_GAIN_R76.length - 1) { i = YLXW_ROGUE_GAIN_R76.length - 1; }
    var v = Number(YLXW_ROGUE_GAIN_R76[i]);
    return (isFinite(v) && v > 0) ? v : 1;
  } catch (e0) { return 1; }
}
''' % {'TBL': '[%s]' % ', '.join('%.2f' % v for v in R076_MUL)}

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- 锚点（均实测 count==1 @ index-v291-20261001.js）

# —— 注入锚：G3 定义行之前（模块级作用域；函数声明提升，位置不影响调用）——
INJECT_ANCHOR = 'function G3(t,r,a){'

# —— G3 返回语句里的两段产出（唯一；l=fe.indexOf(a.realm) 在 G3 内已在作用域）——
RET_OLD = 'logType:j,expGain:d,spiritStoneGain:u,'
RET_NEW = ('logType:j,expGain:Math.floor(d*YlxwRogueMulR76(l)),'
           'spiritStoneGain:Math.floor(u*YlxwRogueMulR76(l)),')

# —— 冻结门禁锚点（只读；相邻需求面逐字未动的证据）——
# R-062 面
FRZ_R62_G3 = '*1.63666;'                                  # roguelike 收益基数（R-062/R-063 双门禁）
FRZ_R62_MUL = 'var YLXW_SR_GAIN_R62 = 3;'                 # 弹窗收益 ×3
FRZ_R62_FN = 'function YlxwSrBoostR62(e0) {'              # 弹窗分流包裹
FRZ_R62_SPLIT = 'Q==="secret_realm"?YlxwSrBoostR62:function(e0){return e0})('
# R-063 面
FRZ_R63_U3 = 'function U3(t,r){const a=Math.min(r>0?r:z3,xg+Math.floor(Math.random()*(z3-xg+1))),'
FRZ_R63_CALL = 'const z=fe.indexOf(a.realm),W=U3(0,Math.min(z3,Math.max(xg,(z+3)*2))),'
FRZ_R63_CAP = 'var YLXW_DG_ROGUE_CAP = [3, 5, 7, 8, 10, 11, 13];'
FRZ_R63_NORM = 'var YLXW_DG_CAP = [10, 12, 14, 15, 17, 18, 20];'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检 1：替换串必须真的变了（防手滑写成恒等）
    if RET_OLD == RET_NEW or 'YlxwRogueMulR76(l)' not in RET_NEW:
        raise AssertionError('r076 锚点异常：G3 返回未接入倍率函数')
    if len(R076_MUL) != 7 or any((not (0 < v <= 1)) for v in R076_MUL):
        raise AssertionError('r076 常量异常：倍率表须 7 项且落在 (0,1]（本需求是净回收）')

    blk = zh(INJECT_JS)
    # 自检 2：注入块 zh() 后纯 ASCII 且不含禁用模式
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r076 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for pat in BAN_PATTERNS:
        if pat in blk:
            raise AssertionError('r076 注入块含禁用模式 %r' % pat)
    if 'fetch(' in blk:
        raise AssertionError('r076 注入块不得含 fetch(')

    # 0) 注入分境界倍率表 + 取值函数
    p.insert_before('r076-mul-fn', INJECT_ANCHOR, blk + '\n', expect=1,
                    note='注入 YLXW_ROGUE_GAIN_R76 + YlxwRogueMulR76（roguelike 单轮奖励 = 普通 ×2）')

    # 1) G3 返回：expGain / spiritStoneGain 各乘分境界因子
    p.replace('r076-g3-return', RET_OLD, RET_NEW, expect=1,
              note='roguelike 单轮 exp/灵石按分境界因子折算（灵石精确 2× 普通）')

    tbl_lit = 'var YLXW_ROGUE_GAIN_R76 = [%s];' % ', '.join('%.2f' % v for v in R076_MUL)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本模块改动 =================
        ('R76·分境界倍率表就位',   tbl_lit, 1, '==', '炼气→长生；= 2 / 现状灵石比值'),
        ('R76·表 7 项且全 ≤1',     'YLXW_ROGUE_GAIN_R76 = [%s];' % ', '.join('%.2f' % v for v in R076_MUL), 1, '==', ''),
        ('R76·取值函数已定义',     'function YlxwRogueMulR76(l)', 1, '==', ''),
        ('R76·非法境界恒等返回',   'return (isFinite(v) && v > 0) ? v : 1;', 1, '==', '防 NaN/越界毁档'),
        ('R76·G3 修为已折算',      'expGain:Math.floor(d*YlxwRogueMulR76(l))', 1, '==', ''),
        ('R76·G3 灵石已折算',      'spiritStoneGain:Math.floor(u*YlxwRogueMulR76(l))', 1, '==', ''),
        ('R76·旧 G3 返回已清零',   RET_OLD, 0, '==', '旧未折算形态'),
        ('R76·G3 仍唯一',          'function G3(', 1, '==', ''),
        ('R76·倍率函数引用恰 3 处', 'YlxwRogueMulR76', 3, '==', '定义 1 + 两处调用'),
        # ================= 冻结：R-062 面（弹窗收益 / 基数 / 分流）=================
        ('冻结·R62 roguelike 基数未动', FRZ_R62_G3, 1, '==', 'G3 的 c= 计算式一字未动'),
        ('冻结·R62 弹窗倍率常量未动',   FRZ_R62_MUL, 1, '==', '普通点选仍 ×3'),
        ('冻结·R62 提升函数未动',       FRZ_R62_FN, 1, '==', ''),
        ('冻结·R62 弹窗分流未动',       FRZ_R62_SPLIT, 1, '==', ''),
        # ================= 冻结：R-063 面（层数 / 上限）=================
        ('冻结·R63 U3 定义未动',       FRZ_R63_U3, 1, '==', '层数因子（R-063 的活）'),
        ('冻结·R63 层数封顶调用未动',   FRZ_R63_CALL, 1, '==', ''),
        ('冻结·R63 rogue 上限表未动',   FRZ_R63_CAP, 1, '==', ''),
        ('冻结·R63 普通上限表未动',     FRZ_R63_NORM, 1, '==', ''),
    ]
    return gates
