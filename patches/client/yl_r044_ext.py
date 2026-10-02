# -*- coding: utf-8 -*-
r"""
yl_r044_ext.py — R-044 历练灵石产出：**二次下调到 ≈10 万/小时**（原 ×3 太快）

用户原话（2026-10-01 二次调整）
--------------------------------------------------------------------------
  「历练修复到 1 小时大概 10W。」
  背景：上一轮（0.8.11.9）为把历练做成灵石主要来源，把倍率从 ×1 抬到 ×3
  （单次 ≈98 → 294 灵石，≈12 万 → 35 万/小时）。用户现在觉得**产出太快**，
  ⇒ 本轮按**净额/时薪**反推，把倍率降到 **0.85**（单次 ≈98 → 83，≈10 万/小时）。
  ★ 注意：×1 口径本身已 ≈11.8 万/h > 10 万 ⇒ 倍率必然 <1（不是再抬，是往下压）。

侦察结论（基座产物 build/assets/index-v28117-20261001.js，逐字实证）
--------------------------------------------------------------------------
  · 随机数：`function Ge(t,r,a,l=0){const c=a-r;return Math.floor(sa(t,l)*c)+r}`
      ⇒ `Ge(seed, lo, hi, salt)` ∈ [lo, hi-1]；`sa(t,r)=frac(sin(t*1000+r)*1e4)`。
  · 历练结算 = `executeAdventure`（@1809805 `=async(Q,U,B,Z)=>{…}`），两条子路径**汇流到同一个 V**：
      ① 模板事件：`if(V=(Q==="secret_realm"?YlxwSrBoostR62:function(e0){return e0})(Ym(oe,…,YLXW_STONE_MUL_ADV)),ek()){…}`
      ② 真实战斗：`V=oe.result`（`DS` 触发；normal≈25.5% / lucky≈10.8%，奖励走 `By`）
      随后 `V||(V={…}),await new Promise(oe=>setTimeout(oe,1500)),await Fg({result:V,…})`。
  · 灵石最终式（`Ym` 内，@555903）：
      `spiritStonesChange:Math.floor(Math.floor(t.spiritStonesChange*u)*5*(_ylm==null?1:_ylm))`
      u = 境界系数 × 层数系数；主历练/秘境传 `_ylm=YLXW_STONE_MUL_ADV=0.2` ⇒ 内层 ×5 与 ÷5 相抵，**净 ×u**。
  · 难度倍率 `md(a).reward` / `Lm(a).reward` **只出现在 `By`（战斗奖励）**，不叠加到模板灵石
      ⇒ 模板路径无需考虑难度倍率；改「结算出口」可同时覆盖模板与战斗两路。

改动前量级（炼气期 L1，u=1；自动历练）
--------------------------------------------------------------------------
  逐模板复算（720 条 normal 池按 `Fm` 权重 + 120 条 lucky 池均匀）：
      normal 事件 ≈ 74.5%×模板(加权均值 ≈15) + 25.5%×真实战斗(By ≈240) ≈ **75 灵石/次**
      lucky  事件 ≈ 89%×模板(≈350) + 11%×战斗(≈250)                    ≈ **340 灵石/次**
      单次历练（含 15% 商店跳过）= 0.1275×340 + 0.7225×75 ≈ **98 灵石/次**
      冷却 `d(3)`=3 秒/次 ⇒ 1200 次/小时 ⇒ **≈ 12 万灵石/小时**（炼气 L1）。

本模块动作（1 注入 + 3 就地替换；零相邻面改动）
--------------------------------------------------------------------------
  · 在**历练结算出口 V**（`await Fg({result:V,` 之前）按类型分流套一层缩放：
        `V=(Q==="secret_realm"?V:YlxwAdvBoostR44(V)),`
    ⇒ 一次覆盖「模板事件 + 真实战斗」两条子路径；**只缩放正值 spiritStonesChange**，
      hpChange / expChange / itemObtained / reputation / 故事文本**一字不动**。
  · **排除弹窗秘境**（`Q==="secret_realm"`）：每日限次、R-062 刚调过的面，不叠加。
  · 倍率 `R044_ADV_STONE_MUL = 0.85`（单一可调常量，允许 <1）⇒ 单次 ≈ 98 → **≈ 83 灵石**，
    约 **10 万灵石/小时**（炼气 L1）。换算：98 × 0.85 ≈ 83；83 × 1200 次/h ≈ 9.96 万/h。

曲线压缩（2026-10-01 追加：长生 L9 615 万 → 200 万，中间境界等比平滑）
--------------------------------------------------------------------------
  · 用户目标：炼气 L1 = 10 万/h（认可现值，**保持不变**）、长生 L9 = 200 万/h，
    中间境界「在这个区间平滑安排」，不要「低境界涨得少、高境界突然暴涨」。
  · **结构性问题**：模板线 `Ym` 境界因子 `c = 1.6^a`（指数，长生/炼气 = 16.78×），
    真实战斗线 `By` 境界因子 `v = [1,1.25,1.75,2.5,3.5,5,7]`（近线性，长生/炼气 = 7×）。
    两线斜率不一致 ⇒ 叠加 `Fm` 高奖励模板加权后**高境界超线性膨胀**（L9/L1 = 61.5×）。
  · **本模块动作**：把两条线的境界因子**改成同一套** `r(a) = k^a`：
        Ym：`c=[1,1.6,…,16.777216][a]` → `c=[1,k,…,k^6][a]`
        By：`v=[1,1.25,…,7][u]`      → `v=[1,k,…,k^6][u]`
    `k = 1.236928`，由「长生 L9 时薪 = 20 × 炼气 L1 时薪」反解（层因子 d/S 已在乘，故 k 更缓）。
    首元素恒为 1 ⇒ 炼气 L1 端点逐字不变（仍叠加 0.85 得 10 万/h）。
  · **副作用（预期）**：`Ym` 的 `u = c·d` 同时驱动 hpChange / expChange，故历练掉血与历练修为的
    境界倍率也一并压缩；`By` 的 `v` 同时驱动战斗修为，同理。公式**形状**与签名一字未动（见冻结门禁）。
  · 标定脚本 `_calc_r044_curve.py` 先复算旧端点（L1 = 10.0 万 / L9 = 615.1 万，比值 61.53× 与上一轮
    报告吻合），再解出新 k，输出「境界 × 层」表；报告见 `报告_历练曲线压缩_20261001.md`。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 只新建本文件；不改 build_v26n.py / localtest/*.py / srv/index_v28.ts / deploy_v28/* / 任何已有 yl_*_ext.py。
  · 注入块纯 ASCII（zh() 后无非 ASCII）；不含 V28_BAN_PATTERNS；无 fetch。
  · 锚点唯一（count==1），每个 replace 带 expect=。注入锚 `function fs(t,r,a=0){` 与 Ym 同模块
    （515340~555640 之间无模块边界，且与 `executeAdventure` 的 V 点同作用域），
    且不被任何模块改写（yl_068 只把它当**门禁**，不替换 ⇒ 注入不影响其门禁）。
  · ★ 接线：接进 build_v26n.py 的 `V28_MODULES`，放在 **`r062` 之后、`numbal` 之前**
    （依赖 eco085/r062 已把 V 点落成带 `Q==="secret_realm"` 分流的形态；本模块只在其后追加赋值）。
  · 冻结门禁证明相邻需求面逐字未动：R-043 掉血、R-042 频率/冷却、R-041 奇遇几率、灵田、打坐灵石、
    `Ym` 灵石式、`MUL_ADV`、R-062 秘境分流壳/函数/冷却、战斗 `By` 公式。
  · ★ **无需主控同步改任何上游门禁**（本模块未触碰任何被别模块断言的字面量）。
"""

import re

# --------------------------------------------------------------------------- 可调常量
# 主控调参只需改这一行（自动拼进 INJECT_JS，无需改其它地方）
R044_ADV_STONE_MUL = 0.85   # 历练（主冒险循环）灵石倍率（★ 二次下调到 ≈10 万/h；允许 <1）

# ---- 境界因子统一曲线（2026-10-01 曲线压缩）----
# 目标：炼气 L1 = 10 万/h（保持不变）、长生 L9 = 200 万/h；中间境界等比平滑。
#   两条线改用**同一套**境界因子 r(a) = k^a：
#     模板事件线 Ym 的 c（旧 [1,1.6,…,16.777216] = 1.6^a，指数，长生/炼气 = 16.78×）
#     真实战斗线 By 的 v（旧 [1,1.25,1.75,2.5,3.5,5,7]，近线性，长生/炼气 = 7×）
#   旧结构问题：两线斜率不一致 ⇒ 高境界超线性膨胀（长生 L9 达 615 万/h，为炼气 L1 的 61.5×）。
#   k 由「长生 L9 时薪 = 20 × 炼气 L1 时薪」反解（层因子 d=1+(L-1)*0.3 / S=1+(L-1)*0.15 已在乘，
#   故 k 远小于 20^(1/6)）；标定脚本 = 同目录 `_calc_r044_curve.py`（复算旧端点 10.0/615.1 万吻合）。
#   首元素恒为 1 ⇒ 炼气 L1 端点逐字不变（叠加 R044_ADV_STONE_MUL=0.85 仍是 10 万/h）。
R044_REALM_CURVE = [1.0, 1.236928, 1.529991, 1.892489, 2.340873, 2.895491, 3.581514]


def _js_num(x):
    """把 Python float 渲染成最短的 JS 数字字面量（去掉多余 0）。"""
    s = ('%.6f' % x).rstrip('0').rstrip('.')
    return s or '0'


R044_CURVE_JS = '[' + ','.join(_js_num(x) for x in R044_REALM_CURVE) + ']'

# --------------------------------------------------------------------------- 注入块（纯 ASCII）

INJECT_JS = r'''
/* ===== yl-R044: adventure spirit-stone income tune =====
   R-044 retune (2026-10-01): adventure was too fast after the x3 bump;
   scale the settlement exit to land near 100k stones / hour at QiRefining L1.
   The multiplier may be < 1 (a downward tune).
   Applied at the main-adventure settlement exit V, so it covers BOTH the
   template-event path and the real-battle path of the normal/lucky loop.
   The daily-capped popup secret realm (adventureType "secret_realm") keeps
   its own R-062 tuning and is deliberately NOT scaled here.
   Only a positive spiritStonesChange is scaled; hpChange / expChange /
   items / reputation / story text are byte-for-byte untouched.
   Identity on any malformed input (never returns undefined / NaN). */
var YLXW_ADV_STONE_R44 = %(MUL)s;   /* adventure spirit-stone multiplier */
function YlxwAdvBoostR44(r0) {
  try {
    if (!r0 || typeof r0 !== "object") return r0;
    var g0 = Number(YLXW_ADV_STONE_R44);
    if (!isFinite(g0) || g0 <= 0) return r0;
    var s0 = Number(r0.spiritStonesChange);
    if (!isFinite(s0) || s0 <= 0) return r0;
    var o0 = Object.assign({}, r0);
    o0.spiritStonesChange = Math.floor(s0 * g0);
    return o0;
  } catch (e1) { return r0; }
}
''' % {'MUL': R044_ADV_STONE_MUL}

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- 锚点（均实测 count==1）

# —— 注入锚：与 Ym 同模块作用域（function/var 声明提升，注入位置不影响调用）——
INJECT_ANCHOR = 'function fs(t,r,a=0){'

# —— 历练结算出口：V 分流包裹（保留 `await Fg({result:V,` 字面量，只在其前加一段赋值）——
SETTLE_OLD = 'await Fg({result:V,'
SETTLE_NEW = 'V=(Q==="secret_realm"?V:YlxwAdvBoostR44(V)),await Fg({result:V,'
SETTLE_PRE_OLD = 'setTimeout(oe,1500)),await Fg({result:V,'
# ★ 0.9.8 adv097(R-089b) 在本模块 R44 层之后又叠了一层 R97 提升，结算出口最终形态含两层；
#   本门禁锚点同步为该最终形态（R44 层仍在，语义不变：结算出口已套提升）。
SETTLE_PRE_NEW = ('setTimeout(oe,1500)),V=(Q==="secret_realm"?V:YlxwAdvBoostR44(V)),'
                  'V=(Q==="secret_realm"?V:YlxwAdvBoostR97(V)),await Fg({result:V,')

# —— 境界因子（两线统一到同一套 r=k^a）——
# 模板事件线 Ym 头：const a=fe.indexOf(r.realm),c=[1,1.6,…][a]||1,
R044_YM_ARR_OLD = ('const a=fe.indexOf(r.realm),'
                   'c=[1,1.6,2.56,4.096,6.5536,10.48576,16.777216][a]||1,')
R044_YM_ARR_NEW = 'const a=fe.indexOf(r.realm),c=%s[a]||1,' % R044_CURVE_JS
# 真实战斗线 By 头：const u=fe.indexOf(t.realm),v=[1,1.25,…][u]||1,
R044_BY_ARR_OLD = ('const u=fe.indexOf(t.realm),'
                   'v=[1,1.25,1.75,2.5,3.5,5,7][u]||1,')
R044_BY_ARR_NEW = 'const u=fe.indexOf(t.realm),v=%s[u]||1,' % R044_CURVE_JS
# 冻结：两线函数签名（本模块只换境界因子，签名一字不动）
FRZ_YM_SIG = 'function Ym(t,r,_ylm){'
FRZ_BY_SIG = 'function By(t,r,a,l,c=1,d="normal"){'

# —— 冻结门禁锚点（只读；相邻需求面逐字未动的证据）——
# R-043 历练掉血（模板 + 真实战斗 + hpChange=-q 同源）
FRZ_R043_HP = 'hpChange:t.hpChange<0?Math.floor(t.hpChange*u*0.25):Math.floor(t.hpChange*u)'
FRZ_R043_BQ = 'q=Math.max(0,Math.floor((C-g)*0.25))'
FRZ_R043_BL = 'L=-q,'
# R-042 历练频率 / 冷却
FRZ_R042_CD = '}finally{c(!1),d(10)}'
FRZ_R042_POLL = '},500);return()=>{clearInterval(U)'
# R-041 历练奇遇几率 + 触发日志（★ 2026-10-01 R-041 已回滚：率回 5%/30%，日志保留）
FRZ_R041_RATE = ('B=.05,Y=U*.02,L=(t.realmLevel-1)*.01,P=t.luck*.001,'
                 'V=Math.min(.3,B+Y+L+P)')
FRZ_R041_LOG = ('Z&&a("\u2728 \u4f60\u798f\u81f3\u5fc3\u7075\uff0c'
                '\u89e6\u53d1\u4e86\u5947\u9047\uff01","special");')
# 0.8.5 eco / R-043 / R-062 共同断言的 Ym 灵石式 + 主历练乘子（**一字未动**）
FRZ_YM_STONE = 'Math.floor(Math.floor(t.spiritStonesChange*u)*5*(_ylm==null?1:_ylm))'
FRZ_MUL_ADV = 'var YLXW_STONE_MUL_ADV = 0.2;'
# R-062 秘境面（分流壳 / 提升函数 / 冷却常量）
FRZ_R062_DISPATCH = 'Q==="secret_realm"?YlxwSrBoostR62:function(e0){return e0})('
FRZ_R062_FN = 'function YlxwSrBoostR62(e0)'
FRZ_R062_CD = 'var YLXW_DG_CD_MS = 15 * 60 * 1000;'
# 战斗 By（只缩放结算出口，By 公式本身不动）
FRZ_BY = 'M=Math.max(10,Math.round($*b))*10'
# R-024 打坐灵石（YlxwMedStone2 面）
FRZ_MED_STONE = '__ylsq=YlxwMedStone2(q,$.realmLevel,C),'
# R-047/R-048 灵田面（灵草种植核心）
FRZ_FARM = 'function YlxwTFarm('


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检 1：替换串必须真的变了，且提升函数真的进了串（防手滑写成恒等）
    if SETTLE_OLD == SETTLE_NEW or 'YlxwAdvBoostR44' not in SETTLE_NEW:
        raise AssertionError('r044 锚点异常：结算出口分流包裹未生效')
    if SETTLE_PRE_OLD == SETTLE_PRE_NEW or 'YlxwAdvBoostR44' not in SETTLE_PRE_NEW:
        raise AssertionError('r044 锚点异常：结算出口前置形态未生效')
    if R044_ADV_STONE_MUL <= 0:
        raise AssertionError('r044 常量异常：倍率必须为正')

    # 自检 3：曲线本身合法（7 档、炼气因子恒 1、严格递增）
    if len(R044_REALM_CURVE) != 7 or abs(R044_REALM_CURVE[0] - 1.0) > 1e-12:
        raise AssertionError('r044 曲线异常：必须 7 档且首元素 = 1（炼气端点不变）')
    if any(R044_REALM_CURVE[i] >= R044_REALM_CURVE[i + 1] for i in range(6)):
        raise AssertionError('r044 曲线异常：境界因子必须严格递增')
    # 自检 4：两处替换串必须真的变了，且新曲线真的进了串
    if R044_YM_ARR_OLD == R044_YM_ARR_NEW or R044_CURVE_JS not in R044_YM_ARR_NEW:
        raise AssertionError('r044 锚点异常：模板境界因子未换新曲线')
    if R044_BY_ARR_OLD == R044_BY_ARR_NEW or R044_CURVE_JS not in R044_BY_ARR_NEW:
        raise AssertionError('r044 锚点异常：战斗境界因子未换新曲线')

    blk = zh(INJECT_JS)
    # 自检 2：注入块 zh() 后纯 ASCII 且不含禁用模式
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r044 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for pat in BAN_PATTERNS:
        if pat in blk:
            raise AssertionError('r044 注入块含禁用模式 %r' % pat)
    if 'fetch(' in blk:
        raise AssertionError('r044 注入块不得含 fetch(')

    # 0) 注入倍率常量 + 提升函数（模块级；与 Ym 同作用域）
    p.insert_before('r044-boost-fn', INJECT_ANCHOR, blk + '\n', expect=1,
                    note='注入 YLXW_ADV_STONE_R44 + YlxwAdvBoostR44（历练灵石 ×%s）' % R044_ADV_STONE_MUL)

    # 1) 历练结算出口 V 按类型分流（只包非秘境；弹窗秘境恒等）
    p.replace('r044-settle-boost', SETTLE_OLD, SETTLE_NEW, expect=1,
              note='结算出口套提升：模板事件 + 真实战斗两路同源；secret_realm 恒等')

    # 2) 模板事件线境界因子：指数 1.6^a → 统一曲线 r=k^a
    #    （★ 注意：Ym 的 u=c*d 同时驱动 hpChange / expChange / spiritStonesChange，
    #     本替换会一并压缩历练掉血与历练修为的境界倍率——这是「曲线压缩」的预期副作用）
    p.replace('r044-ym-realm', R044_YM_ARR_OLD, R044_YM_ARR_NEW, expect=1,
              note='模板线境界因子改统一曲线（c=k^a）；签名与灵石式形状不变')

    # 3) 真实战斗线境界因子：近线性 v → 同一套统一曲线 r=k^a
    p.replace('r044-by-realm', R044_BY_ARR_OLD, R044_BY_ARR_NEW, expect=1,
              note='战斗线境界因子改同一套（v=k^a）；By 奖励公式形状不变')

    gates = [
        # ================= 本模块改动 =================
        ('R44·提升函数已定义',        'function YlxwAdvBoostR44(r0)',                   1, '==', ''),
        ('R44·倍率常量=0.85',        'var YLXW_ADV_STONE_R44 = %s;' % R044_ADV_STONE_MUL, 1, '==', '调参只改 R044_ADV_STONE_MUL'),
        ('R44·倍率非有限/非正恒等',    'if (!isFinite(g0) || g0 <= 0) return r0;',      1, '==', '防 NaN 毁档'),
        ('R44·只放大正值灵石',        'if (!isFinite(s0) || s0 <= 0) return r0;',      1, '==', '负值(战败扣石)不放大'),
        ('R44·结算出口已套提升',      SETTLE_PRE_NEW,                                  1, '==', '模板事件 + 真实战斗两路都覆盖；0.9.8 adv097 再叠 R97 层，锚点同步最终形态'),
        ('R44·分流条件串',            'V=(Q==="secret_realm"?V:YlxwAdvBoostR44(V)),',  1, '==', '弹窗秘境排除，恒等返回'),
        ('R44·旧结算出口形态已清零',   SETTLE_PRE_OLD,                                  0, '==', '已被分流包裹'),
        ('R44·倍率引用恰2处',         'YLXW_ADV_STONE_R44',                            2, '==', '声明 + 函数内 1 用'),
        ('R44·hp 字段未被触碰',       'o0.hpChange',                                   0, '==', '提升函数只写 spiritStonesChange'),

        # ================= R-044 曲线压缩：两线统一境界因子 =================
        ('R44·模板境界因子已换统一曲线', R044_YM_ARR_NEW,                                1, '==', 'c=k^a'),
        ('R44·模板旧指数因子已清零',     R044_YM_ARR_OLD,                                0, '==', '1.6^a 已消失'),
        ('R44·战斗境界因子已换统一曲线', R044_BY_ARR_NEW,                                1, '==', 'v=k^a'),
        ('R44·战斗旧线性因子已清零',     R044_BY_ARR_OLD,                                0, '==', '旧 v 已消失'),
        ('R44·两线共用同一套因子',       R044_CURVE_JS,                                  2, '==', '模板 + 战斗各 1 处'),

        # ================= 冻结：R-043 历练掉血 =================
        ('冻结·R43 模板掉血折算未动',  FRZ_R043_HP,                                    1, '==', 'R-043 面'),
        ('冻结·R43 战斗掉血折算未动',  FRZ_R043_BQ,                                    1, '==', ''),
        ('冻结·R43 战斗 hpChange=-q 未动', FRZ_R043_BL,                                1, '==', ''),

        # ================= 冻结：R-042 历练频率 / 冷却 =================
        ('冻结·R42 历练冷却仍 10s',    FRZ_R042_CD,                                    1, '==', 'R-042 面（R-117 2026-10-02 调 10s，属主侧放宽）'),
        ('冻结·R42 自动轮询仍 500ms',  FRZ_R042_POLL,                                  1, '==', ''),

        # ================= 冻结：R-041 历练奇遇几率 / 日志 =================
        ('冻结·R41 奇遇几率未动',      FRZ_R041_RATE,                                  1, '==', 'R-041 面'),
        ('冻结·R41 奇遇日志未动',      FRZ_R041_LOG,                                   1, '==', ''),

        # ================= 冻结：Ym 灵石式 / MUL_ADV（eco085 + R-043 + R-062 共同断言面）=================
        ('冻结·Ym 灵石式未动',        FRZ_YM_STONE,                                   1, '==', '本模块只在结算出口缩放，不改公式'),
        ('冻结·主历练乘子仍 0.2',      FRZ_MUL_ADV,                                    1, '==', ''),
        ('冻结·Ym 签名未动',          FRZ_YM_SIG,                                     1, '==', '只换境界因子数组'),
        ('冻结·By 签名未动',          FRZ_BY_SIG,                                     1, '==', '只换境界因子数组'),

        # ================= 冻结：R-062 秘境面 =================
        ('冻结·R62 秘境分流壳未动',    FRZ_R062_DISPATCH,                              1, '==', 'R-062 面'),
        ('冻结·R62 提升函数未动',      FRZ_R062_FN,                                    1, '==', ''),
        ('冻结·R62 秘境冷却未动',      FRZ_R062_CD,                                    1, '==', ''),

        # ================= 冻结：战斗 By（只缩放出口，不改公式）=================
        ('冻结·战斗 By 公式未动',      FRZ_BY,                                         1, '==', 'eco085 冻结面'),

        # ================= 冻结：打坐灵石 / 灵田 =================
        ('冻结·打坐灵石未动',         FRZ_MED_STONE,                                  1, '==', 'R-024 面'),
        ('冻结·灵田核心未动',         FRZ_FARM,                                       1, '==', 'R-047/R-048 面'),
    ]
    return gates
