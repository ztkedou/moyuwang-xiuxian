# -*- coding: utf-8 -*-
r"""
yl_adv097_ext.py — R-089（历练成果日志 + 历练灵石/修为上调）+ R-090（顿悟几率小提）

用户原话
--------------------------------------------------------------------------
  R-089：「把每次自动历练的成果也在日志中展示出来。而且我现在实测历练大部分只加的是
         修为。灵石加的次数少并且数量也少。游戏的设计历练应该是自动挂机中灵石获取的
         主要途径，修为比打坐会稍多一点，灵石获取提升会比较大。」
  R-090：「悟道，正常打坐、历练顿悟触发几率现在是多少，可以适当提升一点。」

基线 = build/assets/index-v297-20261001.js（已含 r044 / r042 / medlog / eco085 等全部前置模块）

==========================================================================
一、R-090 取证：两个「顿悟」是两件不同的东西（必须先说清）
==========================================================================
  ① 打坐顿悟（客户端 · 修为爆发）——**唯一存在于客户端的顿悟判定**
       handleMeditate 内 @714525：
         `const j=gd(a),b=Math.random()<.002;let S,x;if(b){const $=30+Math.random()*20;
          S=Math.floor(v*$),x=`✨ 你突然顿悟，灵台清明…`}`
       ⇒ 命中率 **0.2% / 跳**（打坐 tick = 2s ⇒ 约 6%/分钟），命中时修为 ×(30~50)。
       该字面量被 **5 个已接线模块当冻结门禁**（见 §四，改它会连带 FAIL，需主控同步）。

  ② 悟道挂机心得（服务端 · 六系 dao 的 exp）——**用户说的「历练顿悟」其实是这个**
       srv/index_v28.ts：
         `const WUDAO_INSIGHT_CHANCE = 0.04;`  // 每分钟 roll 命中概率（注释：物品概率÷2，0.08→0.04）
         `function ylWudaoIdleDelta(...) { return meditate + adventure; }`  // [v2810] 打坐+历练共用
         `tickWudaoIdle()`：按 playTime 分钟数逐分钟 roll 4% ⇒ +10 exp 随机一系
       ⇒ **打坐与历练共用同一条 4%/分钟 的 roll**，且完全由服务端权威定义。
       ⇒ 本任务是客户端模块，且明令**不得改 srv/index_v28.ts** ⇒ 这一条**本模块无法提升**，
         必须由服务端单独调 `WUDAO_INSIGHT_CHANCE`（本报告已标红，见 §四·风险 D）。

  ③ 历练顿悟事件（客户端 · 历练模板池）——**这条才是本模块能动、也最贴合用户语感的**
       NORMAL 历练池构造器 `hw(t)` @522758 的类型权重数组（36 项）：
         `at(["battle","herb","cultivator","cultivator","cultivator","cave",
              "enlightenment","cultivationArt",…,"lottery"], t)`
       `at(t,r)` @520369：`l=Math.floor(sa(r,600)*t.length); return t[l]` ⇒ **数组重数 = 事件权重**。
       `enlightenment` 在数组中出现 **1 次 / 共 36 项** ⇒ 触发率 **1/36 = 2.78% / 次历练**。
       该事件奖励 `expChange:Ge(t,50,130,150)`（均值 89.5，**只给修为、不给灵石**——
       正好解释用户「历练大部分只加的是修为」的观感）。
       ★ 该类型数组**不被任何模块当门禁**（yl_068/yl_t6chardex 只冻结 `enlightenment` 分支内部的
         `npcRelationChange:fs(t,.0005,160)?`，本模块一字未碰）。

  ⇒ R-090 改动（两项，均约 ×2，刻意保守）：
       · 打坐顿悟 `Math.random()<.002` → `<.004`（0.2%→**0.4%/跳**，6%→12%/分钟）
       · 历练顿悟事件权重 `"cave","enlightenment","cultivationArt"`
                        → `"cave","enlightenment","enlightenment","cultivationArt"`
         ⇒ 1/36 = 2.778% → 2/37 = **5.405%/次**（×1.95）

  收益影响估算（R-090，炼气 L1，u=1）
       · 打坐：每跳基础 v = floor(1×10×(1+1×0.15)) = 11。顿悟期望 40v vs 常规 1.0v。
         Δ率 0.002/跳 × 40v = 0.08v/跳 ⇒ 打坐修为 **+8%**（约 +1.6k 修为/小时，基数 ≈1.98 万/h）。
       · 历练：+2.78% × 89.5 ≈ **+2.5 修为/次** ⇒ ×900 次/h ≈ **+2.2k 修为/小时**。
       ⚠ 两条都**只放大修为**，不放大灵石；顿悟（打坐）虽有 30~50 倍单次爆发，但率只翻一倍、
         期望增益仅 8% —— 刻意不激进，避免重演 0.8.11.9「顿悟 1.5% 导致修为爆炸」。

==========================================================================
二、R-089 取证：历练现在的灵石/修为公式（逐字）
==========================================================================
  · 结算入口 `Pc(t,r,a)` @1833031（`Fg` 内 `c(k=>Pc(k,t,{…}))` 调用）：
        `S.exp = Math.max(0, t.exp + (r.expChange||0))`
        `S.spiritStones = Math.max(0, t.spiritStones + (r.spiritStonesChange||0))`
        `r.expChange>0 && (r.expChange = Math.min(r.expChange, _ylExpCap(t)))`
  · 模板事件线 `Ym(t,r,_ylm)` @562094（**历练灵石/修为的主公式**）：
        `c=[1,1.236928,…,3.581514][a]||1`（r044 统一曲线），`d=1+(realmLevel-1)*.3`，`u=c*d`
        `expChange: Math.floor(t.expChange*u)`
        `spiritStonesChange: Math.floor(Math.floor(t.spiritStonesChange*u)*5*(_ylm==null?1:_ylm))`
        主历练传 `_ylm = YLXW_STONE_MUL_ADV = 0.2` ⇒ 内层 `×5` 与 `÷5` 相抵 ⇒ **净 ×u**。
  · 结算出口（r044 已接线）@1848957 附近：
        `V=(Q==="secret_realm"?V:YlxwAdvBoostR44(V)),await Fg({result:V,…})`
        `YLXW_ADV_STONE_R44 = 0.85`（r044 标定：炼气 L1 ≈98 → 83 灵石/次，≈10 万/h @1200 次/h）
  · 修为硬钳：`_ylCapPct=.25`，`_ylExpCap(t)=max(1,floor(ad(realm,realmLevel)*.25))`
        ⇒ 单次历练修为被钳在「当前层所需修为 ×25%」。
  · 频率：r042 把主循环冷却定在 `d(10)`（R-117 2026-10-02，原 d(4)）⇒ **约 12 秒/次 ≈ 300 次/小时**。

  改动前量级（炼气 L1，u=1；r044 标定值 + r042 的 4s 冷却）
        灵石 ≈ 98 × 0.85 = **83 /次** ⇒ 83 × 900 = **≈7.5 万/h**
        修为 ≈ 模板加权均值 **≈30 /次**（模板池未加权均值 43.1，n=43；`Fm` 对 $>200 的
              高值模板 ×0.5、$>500 的 ×0.2 降权后落到 ≈30）⇒ ×900 = **≈2.7 万/h**
        （对照打坐：11/跳 × 30 跳/min ≈ **1.98 万修为/h** ⇒ 历练本来就「稍多一点」，符合用户预期）

  ⇒ R-089 改动（在 r044 的出口再叠一层，**只缩放正值**）：
        `YLXW_ADV_STONE_MUL_R97 = 4`   ⇒ 灵石净倍率 0.85×4 = **3.4**（相对当前 ×4）
        `YLXW_ADV_EXP_MUL_R97   = 1.2` ⇒ 修为 ×1.2

  改前 → 改后 对照 + 每小时估算（4s/次 = 900 次/h）
    ┌────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
    │ 项         │ 改前/次      │ 改后/次      │ 改前/h       │ 改后/h       │
    ├────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
    │ 灵石 炼气L1│ 83           │ 332          │ 7.5 万       │ 30.0 万      │
    │ 灵石 长生L9│ 1667         │ 6667         │ 150 万       │ 600 万       │
    │ 修为 炼气L1│ ≈30          │ ≈36          │ 2.7 万       │ 3.24 万      │
    └────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
    （长生 L9 = r044 报告 200 万/h @1200 次 ⇒ 150 万 @900 次，再 ×4）

==========================================================================
三、R-089 日志改动（复用既有那一行，不新增第二行）
==========================================================================
  基线 **已经有一行** 历练结算日志（`Fg` 内 @1840434，前序模块引入）：
      `(t.expChange||t.spiritStonesChange||t.hpChange)&&d(\`📊 ${…"历练收获"}：
        ${[修为…,灵石…,气血…].filter(Boolean).join("  · ")}\`,t.eventColor||"normal")`
  两个问题：① `.filter(Boolean)` 把 **0 值字段整段吞掉**（灵石为 0 时完全不显示 ⇒
  用户「灵石加的次数少」无从核对）；② 三项全 0 时**整行不写**，不是「每次都报」。
  ⇒ 本模块把它替换成 `YlxwAdvResultLog(t,m,d)`：**每次结算必写一行**，恒定展示
     `修为 ±N` 与 `灵石 ±N`，气血仅在非 0 时追加（紧凑、一行，与 medlog 风格一致）。
  ★ 数值取自 `Pc()` 跑完之后的对象 ⇒ 是**实际入账值**（已含 `_ylExpCap` 钳制、
    已含越境装备折算成的灵石），不是公式理论值。
  ★ 刻意**不新增第二行**：否则 4 秒/次会出现「历练收获」+「历练成果」双行刷屏。

  ⚠ 刷屏风险（用户明确要求「每次都要报」，照做）：4 秒/次 = 900 行/小时，
    日志上限 1000 条 ⇒ **挂机约 1 小时 7 分钟即挤满**，更早的日志被顶掉。
    这是用户显式选择的代价；若要收敛，改 `YlxwAdvResultLog` 内的写入条件即可（单点）。

==========================================================================
四、风险点（★ 必须上报主控）
==========================================================================
  A. ★★ 服务端经济钳制（本任务最重要风险）：srv/index_v28.ts
       `const E2_ADV_STONE_EACH = 1000;`               // 历练灵石 单次配额（声明 @82174，用 @94216）
       `const E2_STONE_BURST_PER_HOUR = 1250000;`      // 灵石总额兜底 125万×1.5^境界/小时
       `const E2_STONE_BURST_BASE = 6_000_000;`
       `const ylScale = (realmIdx<=0 ? 4/3 : 2*realmIdx+1)/3;`
       `allowStone = floor((floor(1250000*mult*hours) + 6000000) * ylScale);`
       `grantStone = max(0, allowStone - winStone);`   // winStone 是持久化的已发放累计
       `capStone = min(ABS_MAX, grantStone, off.stones + dMed*… + dAdv*1000*ylScale
                       + dKill*500*ylScale + dSR*3000*ylScale + sellAllow*ylScale
                       + 6000000*ylScale + 10000);`
       逐条推算（炼气期 realmIdx=0 ⇒ mult=1、**ylScale=4/9≈0.4444**）：
         · **持续**额度 = 1,250,000 × 0.4444 = **≈55.6 万灵石/小时（全渠道合计）**
           （600万×ylScale = 266.6 万是**一次性**窗口垫底，随 winStone 耗尽后不再补充）
         · 单次额度项 `dAdv*1000*ylScale = 444 灵石/次`，但 `capStone` 里还有
           600万×ylScale 的常量项 ⇒ 单项不构成瓶颈，**瓶颈是上面那条 55.6 万/h**
         · 超限时**静默截断**：`np.spiritStones = ovi + floor(cap)`，只写 `economy_ledger` 的
           `kind='clamp'`（明细前缀 `E2:`），客户端**看不到任何提示**，玩家收益凭空消失。
       ⇒ ×4 后历练单渠道 **30 万/h 占炼气期全局持续额度的 54%**；再叠加出售
         （`E2_SELL_PER_HOUR=1,000,000` → ×ylScale ≈44 万/h 额度）、击杀、秘境、
         打坐灵石，**炼气期很容易触顶被截断**。
       ⇒ 建议：若实测出现截断，把 `YLXW_ADV_STONE_MUL_R97` 下调到 3（22.4 万/h，占 40%），
         或请服务端抬 `ylScale` 的炼气档 / `E2_STONE_BURST_PER_HOUR`（本模块不改 srv）。
       高境界无此问题：长生 L9 mult=1.5^6=11.39、ylScale=13/3 ⇒ 额度 ≈6168 万/h，
       ×4 后 600 万/h 仅占 9.7%。
  B. ★ 修为侧双钳制：客户端 `_ylCapPct=.25`（单次 ≤ 当前层所需×25%）与服务端
       `advEach = max(1, floor(lvlMaxExp*0.025)) + 20`（2.5%/次）。×1.2 只把常见模板
       30→36，通常低于 25% 线；但**奇遇类高修为模板（300~800）本来就被钳**，×1.2 对它们
       **无净效果**（钳制吸收）。故修为增益只体现在中低值模板上 ⇒ 实得增幅 < 1.2×。
  C. ★ 与 R-044（同日）的口径冲突：R-044 刚按用户「历练修复到 1 小时大概 10W」把倍率压到
       0.85（≈10 万/h @1200 次）；R-089 又要「灵石获取提升会比较大」。本模块按 R-089 字面
       执行（净 ×4 ⇒ 30 万/h @900 次），**R-044 的 10 万/h 口径在数值上被覆盖**，请主控确认。
  D. ★ 用户口中的「历练顿悟」= 服务端 `WUDAO_INSIGHT_CHANCE = 0.04`/分钟（打坐+历练共用），
       本模块**改不到**（禁改 srv/index_v28.ts）。若要真正提升「历练顿悟」，需服务端单独调参。
  E. ★ 连带门禁：改 `Math.random()<.002` 会让 **5 个模块**的冻结门禁 FAIL，需主控同步：
       · yl_068_ext.py:116        FRZ_R41_INSIGHT = 'Math.random()<.002'
       · yl_cooldown_ext.py:180   ('冻结·顿悟 0.2% 未动', 'Math.random()<.002', 1)
       · yl_econ2_ext.py:249      ('R22·顿悟改 0.2%', 'Math.random()<.002', 1)
       · yl_r024_ext.py:133       ('冻结·顿悟仍 0.2%', 'Math.random()<.002', 1)
       · yl_r041_ext.py:125       ('R41·顿悟率已回滚 0.2%', 'Math.random()<.002', 1)
       另 r044 的 `SETTLE_PRE_NEW`（'setTimeout(oe,1500)),V=(Q==="secret_realm"?V:YlxwAdvBoostR44(V)),await Fg({result:V,'）
       因本模块在同一出口追加一层而**不再逐字存在** ⇒ r044 的
       `('R44·结算出口已套提升', SETTLE_PRE_NEW, 1)` 亦需同步（其 `YlxwAdvBoostR44(V)` 子串仍为 1 处，其余门禁不受影响）。

==========================================================================
五、锚点纪律 / 接线
==========================================================================
  · 全部锚点实测 count==1（见 apply() 内 expect= 与 §六 实测表）。
  · 注入锚沿用 r044 的 `function fs(t,r,a=0){`（同模块作用域，函数声明提升，位置无关）。
  · 接线：加入 build_v26n.py 的 V28_MODULES，**排在 r044 之后、numbal 之前**
    （依赖 r044 已把出口写成 `V=(Q==="secret_realm"?V:YlxwAdvBoostR44(V)),await Fg({result:V,`）。
  · 只新建本文件；不改版本号 / build_v26n.py / CHANGELOG* / EXPECT_0811.env / deploy_v28/* /
    srv/index_v28.ts / 任何已有 yl_*_ext.py。注入块 zh() 后纯 ASCII、无 fetch、不含禁用模式。
  · 锚点实测 count（基座 build/assets/index-v297-20261001.js）：
      'const j=gd(a),b=Math.random()<.002;let S,x;'                 → 1
      '"cave","enlightenment","cultivationArt"'                     → 1
      'V=(Q==="secret_realm"?V:YlxwAdvBoostR44(V)),await Fg({result:V,' → 1
      'function fs(t,r,a=0){'                                       → 1
      日志整式（489 字符，含 `\ud83d\udcca` 转义与全角 `：`）           → 1
      'Math.random()<.004' / 'YlxwAdvBoostR97' / 'YlxwAdvResultLog'  → 0（改前）
"""

import re

# --------------------------------------------------------------------------- 可调常量

R097_MED_INSIGHT = '0.004'   # 打坐顿悟率（原 0.002）
R097_ADV_STONE_MUL = 3       # 历练灵石倍率（叠在 r044 的 0.85 之上 ⇒ 净 ×2.55）
#   ★ 2026-10-01 主控下调 4→3：代理实测炼气 ylScale=4/9 ⇒ 服务端灵石持续额度仅 ≈55.6 万/h（全渠道），
#     ×4 时历练一项就独占 54%，叠加出售/击杀/秘境会触发 settleSaveEconV2 静默截断（玩家白打）。
#     ×3 ⇒ 约 22.4 万/h，占 40%，留出安全余量。
R097_ADV_EXP_MUL = '1.2'     # 历练修为倍率

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- 注入块（纯 ASCII）

INJECT_JS = r'''
/* ===== yl-R089/R090 adv097: adventure result log + stone/exp tune + insight rates =====
   R-089(a) one compact result line per adventure settlement: exp + spirit stones are
            ALWAYS printed, hp only when non-zero. This REPLACES the old conditional
            "adventure harvest" line (which swallowed zero fields and skipped the line
            entirely when exp/stone/hp were all zero) so no second line is added.
            Values are read after Pc() ran => they are the amounts actually credited.
       (b) adventure spirit stones x4 and exp x1.2, applied at the SAME settlement exit
            used by yl_r044, so BOTH the template-event path and the real-battle path are
            covered; the daily-capped popup secret realm stays untouched.
   R-090(a) meditate insight roll 0.2% -> 0.4% per 2s tick.
       (b) adventure "enlightenment" event weight 1/36 -> 2/37.
   Only positive expChange / spiritStonesChange are scaled; hp / items / reputation /
   story text are byte-for-byte untouched. Identity on malformed input (never NaN). */
var YLXW_ADV_STONE_MUL_R97 = __STONE__;   /* adventure spirit-stone multiplier (on top of R-044 0.85) */
var YLXW_ADV_EXP_MUL_R97 = __EXP__;       /* adventure exp multiplier */
function YlxwAdvBoostR97(r0) {
  try {
    if (!r0 || typeof r0 !== "object") return r0;
    var o0 = Object.assign({}, r0);
    var gs = Number(YLXW_ADV_STONE_MUL_R97);
    var s0 = Number(o0.spiritStonesChange);
    if (isFinite(gs) && gs > 0 && isFinite(s0) && s0 > 0) o0.spiritStonesChange = Math.floor(s0 * gs);
    var ge = Number(YLXW_ADV_EXP_MUL_R97);
    var e0 = Number(o0.expChange);
    if (isFinite(ge) && ge > 0 && isFinite(e0) && e0 > 0) o0.expChange = Math.floor(e0 * ge);
    return o0;
  } catch (e1) { return r0; }
}
/* R-089(a): exactly one compact result line per adventure settlement.
   exp + stones always printed; hp appended only when non-zero. */
function YlxwAdvResultLog(res, advType, addLog) {
  try {
    if (!res || typeof res !== "object") return;
    if (typeof addLog !== "function") return;
    var label = advType === "secret_realm" ? "\u79d8\u5883\u6536\u83b7"
      : advType === "sect_challenge" ? "\u5b97\u95e8\u6311\u6218\u6536\u83b7"
      : "\u5386\u7ec3\u6536\u83b7";
    var de = Math.floor(Number(res.expChange) || 0);
    var ds = Math.floor(Number(res.spiritStonesChange) || 0);
    var dh = Math.floor(Number(res.hpChange) || 0);
    var parts = ["\u4fee\u4e3a " + (de > 0 ? "+" : "") + de,
                 "\u7075\u77f3 " + (ds > 0 ? "+" : "") + ds];
    if (dh) parts.push("\u6c14\u8840 " + (dh > 0 ? "+" : "") + dh);
    addLog("\ud83d\udcca " + label + "\uff1a" + parts.join("  \u00b7 "), res.eventColor || "normal");
  } catch (e2) {}
}
'''.replace('__STONE__', str(R097_ADV_STONE_MUL)).replace('__EXP__', str(R097_ADV_EXP_MUL))

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# I1 注入锚：沿用 r044 的锚（同一模块作用域；函数声明提升，位置无关）
INJECT_ANCHOR = 'function fs(t,r,a=0){'

# ① R-090a 打坐顿悟率 0.2% → 0.4%（handleMeditate 内，@714525）
MED_INSIGHT_OLD = 'const j=gd(a),b=Math.random()<.002;let S,x;'
MED_INSIGHT_NEW = 'const j=gd(a),b=Math.random()<.%s;let S,x;' % '004'

# ② R-090b 历练顿悟事件权重 1/36 → 2/37（NORMAL 池构造器 hw 的类型权重数组，@522758）
ENL_TYPES_OLD = '"cave","enlightenment","cultivationArt"'
ENL_TYPES_NEW = '"cave","enlightenment","enlightenment","cultivationArt"'

# ③ R-089b 结算出口：在 r044 的分流之后、`await Fg({result:V,` 之前再叠一层
SETTLE_OLD = 'V=(Q==="secret_realm"?V:YlxwAdvBoostR44(V)),await Fg({result:V,'
SETTLE_NEW = ('V=(Q==="secret_realm"?V:YlxwAdvBoostR44(V)),'
              'V=(Q==="secret_realm"?V:YlxwAdvBoostR97(V)),await Fg({result:V,')

# ④ R-089a 历练成果日志：整式替换为紧凑单行函数调用（489 字符，逐字取证）
#    ★ 原文含 **字面量转义** `\ud83d\udcca`（不是真 emoji 字节）与**真全角冒号** U+FF1A，
#      故用 r'' 保转义 + '\uff1a' 保冒号。
LOG_OLD = (r'(t.expChange||t.spiritStonesChange||t.hpChange)&&d(`\ud83d\udcca '
           r'${m==="secret_realm"?"\u79d8\u5883\u6536\u83b7":'
           r'm==="sect_challenge"?"\u5b97\u95e8\u6311\u6218\u6536\u83b7":'
           r'"\u5386\u7ec3\u6536\u83b7"}'
           '\uff1a'
           r'${[t.expChange?`\u4fee\u4e3a${t.expChange>0?"+":""}${t.expChange}`:"",'
           r't.spiritStonesChange?`\u7075\u77f3${t.spiritStonesChange>0?"+":""}${t.spiritStonesChange}`:"",'
           r't.hpChange?`\u6c14\u8840${t.hpChange>0?"+":""}${t.hpChange}`:""]'
           r'.filter(Boolean).join("  \u00b7 ")}`,t.eventColor||"normal")')
LOG_NEW = 'YlxwAdvResultLog(t,m,d)'

# --------------------------------------------------------------------------- 冻结门禁（只读）

FRZ_MED_INSIGHT_TEXT = '✨ 你突然顿悟，灵台清明'                 # 顿悟文案未动（toast083/r041 面）
FRZ_MED_INSIGHT_LOG = ',YlxwToast(x,"special","md-exp",4000),c(x,"special")}else'  # 顿悟双写未动
FRZ_MED_EXP = 'S=Math.floor(v*(.85+Math.random()*.3))'          # 打坐常规修为公式未动
FRZ_MED_STONE = '__ylsq=YlxwMedStone2(q,$.realmLevel,C),'       # R-024 打坐灵石未动
FRZ_R041_RATE = ('B=.05,Y=U*.02,L=(t.realmLevel-1)*.01,P=t.luck*.001,'
                 'V=Math.min(.3,B+Y+L+P)')                      # R-041 奇遇几率未动
FRZ_R042_CD = '}finally{c(!1),d(10)}'                           # R-042 历练冷却 10s 未动（R-117 调整后）
FRZ_R043_HP = 'hpChange:t.hpChange<0?Math.floor(t.hpChange*u*0.25):Math.floor(t.hpChange*u)'  # R-043 掉血
FRZ_R044_MUL = 'var YLXW_ADV_STONE_R44 = 0.85;'                 # R-044 倍率常量未动
FRZ_YM_STONE = 'Math.floor(Math.floor(t.spiritStonesChange*u)*5*(_ylm==null?1:_ylm))'  # Ym 灵石式未动
FRZ_MUL_ADV = 'var YLXW_STONE_MUL_ADV = 0.2;'                   # 主历练乘子未动
FRZ_R062 = 'Q==="secret_realm"?YlxwSrBoostR62:function(e0){return e0})('  # R-062 秘境分流壳
FRZ_YL_CAP = '_ylCapPct=.25'                                    # 历练修为硬钳未动
FRZ_ENL_NPC = 'npcRelationChange:fs(t,.0005,160)?'              # yl_068 的 enlightenment 面（未碰）


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检 1：替换串必须真的变了（防手滑写成恒等）
    if MED_INSIGHT_OLD == MED_INSIGHT_NEW or '0.002' in MED_INSIGHT_NEW:
        raise AssertionError('adv097 锚点异常：打坐顿悟率未从 .002 改到 .004')
    if ENL_TYPES_OLD == ENL_TYPES_NEW or ENL_TYPES_NEW.count('"enlightenment"') != 2:
        raise AssertionError('adv097 锚点异常：历练顿悟事件权重未翻倍')
    if SETTLE_OLD == SETTLE_NEW or 'YlxwAdvBoostR97' not in SETTLE_NEW:
        raise AssertionError('adv097 锚点异常：结算出口未叠加 R97 提升层')
    if LOG_OLD == LOG_NEW or 'YlxwAdvResultLog' not in LOG_NEW:
        raise AssertionError('adv097 锚点异常：历练成果日志未替换')
    if float(R097_ADV_STONE_MUL) <= 1 or float(R097_ADV_EXP_MUL) <= 1:
        raise AssertionError('adv097 常量异常：倍率必须 > 1（本次是上调）')

    blk = zh(INJECT_JS)
    # 自检 2：注入块 zh() 后纯 ASCII 且不含禁用模式
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('adv097 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for pat in BAN_PATTERNS:
        if pat in blk:
            raise AssertionError('adv097 注入块含禁用模式 %r' % pat)
    if 'fetch(' in blk:
        raise AssertionError('adv097 注入块不得含 fetch(')

    # 0) 注入倍率常量 + 提升函数 + 成果日志函数（模块级；与 Ym / 结算出口同作用域）
    p.insert_before('adv097-block', INJECT_ANCHOR, blk + '\n', expect=1,
                    note='注入 YLXW_ADV_STONE_MUL_R97 / YLXW_ADV_EXP_MUL_R97 / '
                         'YlxwAdvBoostR97 / YlxwAdvResultLog')

    # 1) R-090a 打坐顿悟率 0.2% → 0.4%
    p.replace('adv097-med-insight', MED_INSIGHT_OLD, MED_INSIGHT_NEW, expect=1,
              note='打坐顿悟率 .002 → .004（0.2%→0.4%/跳；R-090 适当提升）')

    # 2) R-090b 历练顿悟事件权重 1/36 → 2/37
    p.replace('adv097-enl-weight', ENL_TYPES_OLD, ENL_TYPES_NEW, expect=1,
              note='历练 enlightenment 事件权重 1/36 → 2/37（2.78%→5.41%/次）')

    # 3) R-089b 结算出口叠层：灵石 ×4 / 修为 ×1.2（覆盖模板 + 真实战斗两路；秘境恒等）
    p.replace('adv097-settle-boost', SETTLE_OLD, SETTLE_NEW, expect=1,
              note='结算出口叠 R97 层：灵石 ×4（净 ×3.4）、修为 ×1.2；secret_realm 恒等')

    # 4) R-089a 历练成果日志：每次结算必写一行（修为 + 灵石，气血非 0 时追加）
    p.replace('adv097-result-log', LOG_OLD, LOG_NEW, expect=1,
              note='历练成果日志改为每次必写、恒定含修为+灵石（不新增第二行）')

    gates = [
        # ================= 注入块 =================
        ('R97·灵石倍率常量已注入',  'var YLXW_ADV_STONE_MUL_R97 = %s;' % R097_ADV_STONE_MUL, 1, '==', ''),
        ('R97·修为倍率常量已注入',  'var YLXW_ADV_EXP_MUL_R97 = %s;' % R097_ADV_EXP_MUL,     1, '==', ''),
        ('R97·提升函数已定义',      'function YlxwAdvBoostR97(r0)',          1, '==', ''),
        ('R97·成果日志函数已定义',  'function YlxwAdvResultLog(res, advType, addLog)', 1, '==', ''),
        ('R97·只放大正灵石',        'if (isFinite(gs) && gs > 0 && isFinite(s0) && s0 > 0)', 1, '==', '负值/NaN 不放大'),
        ('R97·只放大正修为',        'if (isFinite(ge) && ge > 0 && isFinite(e0) && e0 > 0)', 1, '==', ''),
        ('R97·提升函数不碰气血',    'o0.hpChange',                            0, '==', '只写 spiritStonesChange / expChange'),

        # ================= R-090 顿悟几率 =================
        ('R90·打坐顿悟已=0.4%',     MED_INSIGHT_NEW,                          1, '==', '原 .002（0.2%/跳 = 6%/分钟）'),
        ('R90·旧打坐顿悟 0.2% 清零', 'Math.random()<.002',                     0, '==', '★ 连带 5 个模块门禁需主控同步（见 docstring §四·E）'),
        ('R90·历练顿悟权重已翻倍',  ENL_TYPES_NEW,                            1, '==', '1/36 = 2.778% → 2/37 = 5.405%/次'),
        ('R90·旧历练顿悟权重清零',  ENL_TYPES_OLD,                            0, '==', ''),
        ('R90·历练顿悟池仍 37 项',  'at(["battle","herb","cultivator","cultivator","cultivator","cave","enlightenment","enlightenment","cultivationArt"', 1, '==', '只加一项，其余 35 项逐字未动'),

        # ================= R-089 灵石 / 修为 =================
        ('R89·结算出口已叠 R97 层', SETTLE_NEW,                               1, '==', 'r044 分流后追加，模板 + 真实战斗两路同源'),
        ('R89·旧结算出口形态清零',  SETTLE_OLD,                               0, '==', '★ r044 的 SETTLE_PRE_NEW 门禁需主控同步（见 §四·E）'),
        ('R89·R97 层排除秘境',      'V=(Q==="secret_realm"?V:YlxwAdvBoostR97(V)),', 1, '==', '弹窗秘境恒等返回'),

        # ================= R-089 日志 =================
        ('R89·成果日志已接管',      'YlxwAdvResultLog(t,m,d)',                1, '==', '每次结算必写一行'),
        ('R89·旧条件日志已清零',    LOG_OLD,                                  0, '==', 'filter(Boolean) 吞字段的旧式已消失'),
        ('R89·日志恒定含修为',      r'"\u4fee\u4e3a " + (de > 0 ? "+" : "") + de',   1, '==', '必给字段①'),
        ('R89·日志恒定含灵石',      r'"\u7075\u77f3 " + (ds > 0 ? "+" : "") + ds',   1, '==', '必给字段②'),
        ('R89·日志气血仅非 0 追加', 'if (dh) parts.push(',                    1, '==', '紧凑一行'),
        ('R89·日志复用既有 addLog', r'addLog("\ud83d\udcca " + label',         1, '==', '只读+写日志，不改入账'),

        # ================= 冻结：R-090 未越界 =================
        ('冻结·顿悟文案未动',       FRZ_MED_INSIGHT_TEXT,                     1, '==', 'toast083 / r041 面'),
        ('冻结·顿悟双写未动',       FRZ_MED_INSIGHT_LOG,                      1, '==', 'toast083 T1②'),
        ('冻结·打坐常规修为式未动', FRZ_MED_EXP,                              1, '==', '只动顿悟率，不动公式'),

        # ================= 冻结：相邻需求面 =================
        ('冻结·打坐灵石未动',       FRZ_MED_STONE,                            1, '==', 'R-024 面'),
        ('冻结·R41 奇遇几率未动',   FRZ_R041_RATE,                            1, '==', 'R-041 面'),
        ('冻结·R42 历练冷却仍 10s', FRZ_R042_CD,                              1, '==', 'R-117 2026-10-02 定 10s（≈300 次/小时的口径来源），由属主侧放宽'),
        ('冻结·R43 历练掉血未动',   FRZ_R043_HP,                              1, '==', 'R-043 面'),
        ('冻结·R44 倍率常量未动',   FRZ_R044_MUL,                             1, '==', '本模块只在出口叠层，不改它'),
        ('冻结·Ym 灵石式未动',      FRZ_YM_STONE,                             1, '==', 'eco085 / R-043 / R-062 共同断言面'),
        ('冻结·主历练乘子仍 0.2',   FRZ_MUL_ADV,                              1, '==', ''),
        ('冻结·R62 秘境分流壳未动', FRZ_R062,                                 1, '==', 'R-062 面'),
        ('冻结·历练修为硬钳未动',   FRZ_YL_CAP,                               1, '==', '客户端 .25 上限（风险 B）'),
        ('冻结·enlightenment 分支未动', FRZ_ENL_NPC,                          1, '==', 'yl_068 的 npc 几率面，只改类型权重'),

        # ================= 限域：注入块内不得出现网络调用 =================
        ('R97·注入块内无网络调用',  'fetch(',                                 0, '==', '纯客户端',
         ('/* ===== yl-R089/R090 adv097:', 'function fs(t,r,a=0){')),
    ]
    return gates
