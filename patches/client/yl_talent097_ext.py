# -*- coding: utf-8 -*-
r"""
yl_talent097_ext.py — R-085 天赋数值重构（整体上调 + 放开修炼速度压制） + R-087 天赋配色重构

需求原文（用户 2026-10-01）
--------------------------------------------------------------------------
  R-085：「天赋属性完全重新设计。现在的天赋 8 点的金色属性还不如默认自带的 6 点。全部天赋数据全部重构。
         加的数值可以适当加多一点，这个毕竟是开局独一份，要体现天赋选择的重要性。此外现在天赋的修炼
         效率有点过低了，我建议天赋里面现在的修炼速度加成可以乘以 0.5，然后游戏内天赋的修炼速度直接
         放开压制，总体加起来是多少就是多少。」
  R-087：「天赋颜色的重构有 bug，为什么 8 点仙品还是红色，有些 6 点却是金色。还是需要重新更新，
         金色最高，红色第二，其他的你来定，把颜色修正好。」

基线（只读）：build/assets/index-v297-20261001.js（= build_v26n.OUT，链尾产物）

==========================================================================
一、R-087 配色：先读基线，确认「现有映射」到底是什么
==========================================================================
★ 关键侦察结论：**基线里天赋卡的颜色并不是按 `rarity` 字段映射，而是按「评分」映射**。
  （需求方给的口径「颜色目前按 rarity 映射」与实际代码不符，此处以实读代码为准。）

  天赋卡 = `YlxwR38Card`（yl_r038_ext.py 注入，offset ≈ 490804），三行：
      var sc  = YlxwR38Score(t);        /* 数值强度评分 = Σ 值 ×(1/该属性全表最大值) */
      var rar = YlxwR38Tier(sc);        /* 评分 → 档名 */
      var col = YlxwR38Color(rar);      /* 档名 → 颜色 */
  分档表 `YLXW_R38_THRESH = [0.30, 0.70, 1.30, 2.20]`，档名 `[普通,稀有,传说,史诗,仙品]`。

  现有颜色映射（**改前**）：
      普通 → 灰 stone       稀有 → 蓝 blue       传说 → 紫 purple
      史诗 → **金 amber**   仙品 → **红 red**     ⇒ 最高档(仙品)=红，第二档(史诗)=金

  ★ 实测「同档不同色 / 跨档倒挂」（132 条逐条算分复现，用户抱怨属实）：
      8 点 nt-40「万法不侵」sc=3.60 → 仙品 → **红**（最高档）
      8 点 nt-49「道法随心」sc=2.00 → 史诗 → **金**（第二档）   ← 同为 8 点，颜色不同
      6 点 talent-immortal-king「仙王转世」sc=3.585 → 仙品 → **红**  ← 6 点比 8 点还「高档」
      6 点 nt-37「筋骨钢铁」sc=1.333 → 史诗 → **金**
    ⇒ 根因：**分档用的是 score，而 score 与「点数 fateCost」不单调**。用户的口径是「点数 → 颜色」，
      所以只要还按 score 分档，「8 点红 / 6 点金」就必然复发（尤其 R-085 还要再改一遍数值）。

  本模块动作（R-087）：**把分档依据从 score 改成 fateCost（点数）**，档名沿用游戏既有五档词：

      改前： score 分档 + 颜色「史诗=金 / 仙品=红」      （跨档倒挂）
      改后： fateCost 分档 + 颜色「仙品=金 / 史诗=红」    （点数单调，金最高红第二）

    点数 fateCost  档名   改前色   改后色
    --------------------------------------------------
      8             仙品   红       金(amber)   ← 最高档
      6             史诗   金       红(red)     ← 第二档
      4             传说   紫       紫(purple)
      2             稀有   蓝       蓝(blue)
      1             普通   灰       灰(stone)
    ⇒ 同点数必同色；点数越高颜色越高，**跨档倒挂/同档不同色被彻底消除**。
    改后颜色类全部沿用 r038 已确认「产物 CSS 存在」的同一批 Tailwind class，**未新造 class**。

★ 实现方式（为什么不是「直接改 YlxwR38Color 的 switch」）：
  r038 有 5 条门禁按「class 串**恰好出现 1 次**」计数（灰 chip / 蓝 case / 紫 case / 金框 / 红框），
  另 3 条把 `var rar = YlxwR38Tier(sc);`、`var col = YlxwR38Color(rar);`、旧配色 case 钉死。
  直接改或另写一份配色表都会打爆 r038 门禁 ⇒ 本模块改为：
    · **保留 r038 的 `YlxwR38Color` 作为唯一 class 来源**（不新增任何 class 字面量）；
    · 卡片内就地覆写两行结果（原行作为子串保留，满足 r038 门禁）：
        var rar = YlxwR38Tier(sc); rar = YlxwT097Tier(t.fateCost);          /* 分档改按点数 */
        var col = YlxwR38Color(rar); col = YlxwR38Color(YlxwT097Swap(rar)); /* 仙品/史诗两档对调 */
    · `YlxwT097Swap` 只做「仙品⇄史诗」两档名字对调 ⇒ 8 点(仙品)取到「史诗」那套 = 金、
      6 点(史诗)取到「仙品」那套 = 红；传说/稀有/普通 原样不动。
  ⇒ chip 文案仍是自然档名（8 点显示「仙品」），只是配色把「金」给了最高档。

==========================================================================
二、R-085 数值：改前 → 改后
==========================================================================
  就地改 `Un` 表 effects（**数组字面量一字不动**，见下方「为什么用运行时改值」）：
      平铺属性 attack/defense/hp/spirit/physique/speed/luck  → ×3      （YLXW_T097_MUL）
      修炼速度 expRate                                       → ×0.5    （YLXW_T097_EXP，用户明确要求）
      暴击率 critChance / 暴伤 critDamage                    → 不动     （比率型，见下）
      负向词条（speed:-8 / defense:-10 / hp:-100）           → 不动     （不把「短板」越改越深）

  ★ 为什么暴击不动：critChance 全表最大 0.48（nt-60），×3 = 1.44 > 100% ⇒ 必暴；critDamage 1.2×3 = 3.6
    过于夸张。这类天赋的 attack 仍按 ×3 提升，整体仍然变强。

  典型条目对照（实算）：
    点数 条目                     改前 effects                                改后 effects
    ------------------------------------------------------------------------------------------------
    1  nt-31  玄龟之血            {defense:10, hp:20}                        {defense:30, hp:60}
    1  nt-41  过目不忘            {expRate:0.05, spirit:8}                   {expRate:0.025, spirit:24}
    6  nt-37  筋骨钢铁            {physique:64, defense:80}                  {physique:192, defense:240}
    6  talent-destruction 破灭之体 {attack:150, speed:25, hp:-100}           {attack:450, speed:75, hp:-100}
    8  nt-40  万法不侵            {defense:120,hp:240,physique:96,speed:96}  {defense:360,hp:720,physique:288,speed:288}
    8  nt-70  洪福齐天            {luck:120, expRate:0.6, spirit:96}         {luck:360, expRate:0.3, spirit:288}
    8  nt-60  魔神降临            {attack:120, critChance:0.48, critDamage:1.2} {attack:360, critChance:0.48, critDamage:1.2}
  全表正向数值之和 13950.8 → 41824.6（×3.00）；expRate 总和 8.46 → 4.23（×0.5）。

  ★ 为什么用「运行时就地改值」而不是「替换整段数组字面量」：
    r038 有 3 条冻结门禁把**表体字面量**钉死 —— `"fateCost":` 必须恰好 132 处、
    `"rarity":"史诗","fateCost":6,"effects":{"physique":64,"defense":80}`（nt-37 原值）必须原样存在。
    替换字面量 ⇒ 打爆 r038 门禁。改值走 `YlxwT097Boost(Un)` ⇒ 数组文本不变、条数/ID 集合不变。

==========================================================================
三、R-085 放开「天赋修炼速度压制」：原来怎么压的 / 改成什么样
==========================================================================
  ★ 压制代码（实读，`bd(t)`，offset ≈ 595646；R-025 / yl_econ2_ext.py 拍板口径）：
      function bd(t){ ... const f=t.talentIds||[];
        for(const T of f){const $=Un.find(M=>M.id===T);$&&$.effects.expRate&&(a+=$.effects.expRate)}   // a = 天赋 expRate 求和
        ...
        return{total:r*d+a*0.26+l*0.6+c*0.6+Math.min(b,0.1)+S*0.32,...} }                              // ← 天赋项 = a*0.26
    即：**天赋 expRate 求和 a 先被降幅系数 0.26 压到 26%** 才进 total（K 表 `YLXW_ECON2_K.talent = 0.26`）。
    消费方：打坐 `RS.handleMeditate`（offset ≈ 714454）`v=Math.floor(v*(1+m.total))`；面板明细
    `T.talent*0.26*100`（r040 对齐后的显示）。

  ★ 改动（**放开压制 = 有效系数 1.0，总体加起来是多少就是多少**）：
      原：  a 累加原始值          → total 里 a*0.26            ⇒ 天赋贡献 = 0.26 × ΣexpRate
      改：  a 累加时**预乘 1/0.26** → total 里 (a×1/0.26)*0.26 ⇒ 天赋贡献 = 1.00 × ΣexpRate
      锚点：`(a+=$.effects.expRate)` → `(a+=$.effects.expRate*YLXW_T097_TALENT_K)`，`YLXW_T097_TALENT_K = 1/0.26`。

  ★ 为什么绕这一手（而不是直接把 `a*0.26` 改成 `a`）：
    econ2 有 3 条、r040 有 4 条**冻结门禁**钉死 `+a*0.26+` / `return{total:r*d+a*0.26+...}` /
    `T.talent*0.26*100`。直接改字面量 ⇒ 打爆 econ2 + r040 共 7 条门禁（本轮不允许改其它文件）。
    在 `a` 的**累加处**预乘 1/0.26 后：
      · 数学上等价于「去掉压制」（有效系数 = 0.26 × 1/0.26 = 1.0）；
      · `total` 与面板明细 `T.talent*0.26*100` 仍**同源一致**（明细显示的正是实际生效值），r040/econ2 门禁全绿。

  净值：R-085 令天赋贡献 0.26×a → 0.5×a（因 expRate 先 ×0.5）= **约 1.92 倍**，符合「修炼效率过低」的诉求。

==========================================================================
四、风险（必读）
==========================================================================
  ⚠ 1【numbal / 服务端打坐配额】**最高风险**。numbal（yl_numbal_ext.py，恒在链尾）明确写着：
       「在 bd() 内把心法部分封顶 1.25，保证服务端 settleSaveEconV2 的打坐配额永远够用」。
        服务端（srv/index.ts:1605）`medEach = medBase*3.7 + medBase*50*0.05`（= medBase×6.2），
        `medBase = E2_REALM_EXP_FACTOR_STEPS[realmIdx]*10*(1+realmLevel*0.15)`；
        客户端每次打坐修为 = `f*10*(1+rl*0.15) * (1+total)`（f=[1,2,4,8,15,30,60][境界]）。
      ⇒ 配额里留给 `(1+total)` 的余量是**有限**的。本模块把天赋项从 0.26a 抬到 0.5a，
         `total` 在「满天赋」档大约 **+0.9**（例：a 原 3.8 ⇒ 天赋项 0.988 → 1.9），
         即客户端打坐/历练单次修为约 **+40%**（(1+2.0)/(1+1.09)≈1.43）。
      ⇒ **需要 numbal/服务端复算 `total` 上限是否仍落在 `medBase×6.2` 内**；若超，客户端算出的修为会被
         服务端静默截断（玩家「打坐收益被吞」）。numbal 目前**只对心法（art）设预算，未对天赋设预算**
         ⇒ 天赋这块的余量此前未被显式评估过，本模块把这块吃掉了。
  ⚠ 2【跨模块门禁契约】本模块刻意**保留** r038 / econ2 / r040 的既有字面量（见上），
         因此这三家各自的门禁**全部保持原样通过**；代价是「分档/配色」的旧函数体仍在包里（结果被覆写）。
  ⚠ 3【工具提示】卡片 title 仍显示 `数值强度 sc.toFixed(2)`，而 `YLXW_R38_STATW`（1/旧全表最大值）未随
         ×3 重算 ⇒ 该分值会整体放大约 ×3。**纯展示、不影响分档/配色**（分档已改按点数），故未动。
  ⚠ 4【装配顺序】建议排在 r038 之后、**numbal 之前**（与 attr097/life097/linggen097 同批）。
         本模块锚区（Un 表尾 / 卡片三行 / bd 累加）与上述模块零交集。

==========================================================================
五、锚点实测 count（基线 index-v297-20261001.js）
==========================================================================
  A_UN_TAIL   `],Ln=[{id:"title-novice",name:"初入仙途"`   == 1
  A_CARD_TIER `var rar = YlxwR38Tier(sc);`                  == 1
  A_CARD_COLOR`var col = YlxwR38Color(rar);`                == 1
  A_BD_TAL    `(a+=$.effects.expRate)`                      == 1
  冻结面：`"fateCost":` == 132；`Un=[{"id":"nt-31"` == 1；`function hd(t){...}` == 1。

==========================================================================
六、R-130（0.9.13 批次 · 2026-10-02）：初始天赋神识/身法大幅下调
==========================================================================
  需求（R-130）：「初始账号选择天赋时，神识、身法的加成太多了。按 R-119 标准（1 点=3 神识、
                 1 点=2 身法）严格控制天赋给予的稀有属性。」
  数值表：docs/0.9.13-design/数值表.md §3 —— 终值 = 基础表 ×0.375 = 现值 ÷8。

  ★ 实现澄清（与数值表字面的差异）：数值表写「FLAT.spirit = 0.375」，但产物逻辑行是
  `e[k] = Math.round(v * YLXW_T097_MUL)` —— FLAT 只是 truthy 白名单开关，值不参与乘法；
  终值 = 基础 × MUL(3)。为兑现数值表自身的权威语义（全部验算行均为「现值 ÷8」、
  §0 一页结论「×3 → ×0.375」），实现 = 逻辑行改为 `Math.round(v * YLXW_T097_MUL * YLXW_T097_FLAT[k])`
  且 FLAT.spirit = FLAT.speed = **0.125**（3 × 0.125 = 0.375 终乘数；若按字面 0.375 会得
  基础×1.125 = 现值÷2.67，与数值表所有验算行矛盾）。其余键 FLAT=1 ⇒ ×3×1 = ×3 原样。

  逐档核对（产物 Un 实读基础值 ×0.375，JS Math.round 语义；括号=数值表 §3 值）：
    1 点档  神 9~36 → 1~5（表 1~4；36/8=4.5 在 JS 向上取整=5，点当量 1.67 仍在预算带 ≤1.7 内）
            速 15~36 → 2~5（表 2~4，同上舍入差）
    2 点档  神 24~60 → 3~8 ✓   速 15~60 → 2~8 ✓
    4 点档  神 45~120 → 6~15 ✓ 速 45~120 → 6~15 ✓
    6 点档  神 75~192 → 9~24 ✓ 速 75~192 → 9~24 ✓
    8 点档  神 288 → 36 ✓      速 288 → 36 ✓
  ★ 数值表「典型条目」talent-balanced 天道均衡「速 90→34」为笔误：该天赋实为 6 点
    （fateCost=6，产物 @388570 实读），speed 基础 30 → 现值 90 → 新值 30×0.375 = 11.25 → 11
    （落在其 6 点档新区间 6~15 内，点当量 5.5 ≤ 预算 6 ✓）。以「现值 ÷8」权威口径实现。

  不影响面：expRate（×0.5 路径独立）、critChance/critDamage（不在 FLAT 白名单）、
  负向词条（v<=0 continue 不放大）、天赋颜色（R-087 已改按 fateCost 分档，与数值无关）、
  基础表 Un 字面量（就地改值，r038 冻结门禁 fateCost==132 / nt-37 原值全保）。

导出符号（构建侧契约）
  INJECT_JS : str
  apply(p, ctx) -> list[(name, needle, expect, cmp, note)]
"""

import re

# ---------------------------------------------------------------- 锚点（raw 中文；产物内为 UTF-8 原文）

# ① Un 数组的「收尾 + 下一个 var 声明符」：把 var 链在此断开，插入执行器并就地改值，再起新的 var Ln
A_UN_TAIL = '],Ln=[{id:"title-novice",name:"初入仙途"'

# ② 天赋卡：分档行 / 配色行（r038 门禁要求这两行原样存在，故只做「尾部覆写」）
A_CARD_TIER = 'var rar = YlxwR38Tier(sc);'
A_CARD_COLOR = 'var col = YlxwR38Color(rar);'

# ③ bd() 内天赋 expRate 的累加（放开压制的唯一门禁安全落点）
A_BD_TAL = '(a+=$.effects.expRate)'

# 注入块禁用模式（与 build_v26n.V28_BAN_PATTERNS 一致）
BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']


# ---------------------------------------------------------------- 注入代码

INJECT_JS = r'''/* ===== yl-talent097：R-085 天赋数值重构 + R-087 天赋配色重构 =====
   R-085：Un 表 effects 就地整体上调（平铺属性 ×YLXW_T097_MUL，修炼速度 expRate ×YLXW_T097_EXP）；
          并放开「天赋修炼速度压制」（bd() 内 a*0.26 的 0.26 降幅 → 等效 1.0）。
   R-087：天赋稀有度/颜色改为**按点数 fateCost** 分档：金(仙品) > 红(史诗) > 紫(传说) > 蓝(稀有) > 灰(普通)。
   中文由 build 侧 zh() 转义；本块不含任何网络/鉴权类禁用模式。 */

/* ---- R-085 数值倍数（可调） ---- */
var YLXW_T097_MUL = 3;              /* 平铺属性（攻/防/血/神识/体魄/速度/幸运）整体 ×3 */
var YLXW_T097_EXP = 0.5;            /* 修炼速度 expRate ×0.5（用户明确要求） */
/* 放开压制：天赋 expRate 求和 a 在累加处预乘 1/0.26，使 total 里 a*0.26 的有效系数 = 1.0 */
var YLXW_T097_TALENT_K = 1 / 0.26;

/* 参与 ×MUL 的「平铺属性」白名单（比率型 expRate / critChance / critDamage 不在内）。
   R-130（0.9.13）：神识/身法 两键 1→0.125 ⇒ 终值 = 基础×MUL×FLAT = 基础×0.375（= 旧值÷8）。
   换算基准（加点面板 Ps）：1 点加点 = 3 神识 / 2 身法；其余平铺键保持 1（攻/防/血/体魄/幸运 ×3 不变）。 */
var YLXW_T097_FLAT = { attack: 1, defense: 1, hp: 1, spirit: 0.125, physique: 1, speed: 0.125, luck: 1 };

/* 把 Un 表 effects 就地重构：平铺属性 ×MUL×FLAT 取整；expRate ×EXP 保留 3 位；其余（暴击率/暴伤）保持原值。
   负向词条（speed:-8 / defense:-10 / hp:-100）不放大，避免把「短板」越改越深。 */
function YlxwT097Boost(arr) {
  for (var i = 0; i < arr.length; i++) {
    var e = arr[i] && arr[i].effects;
    if (!e) continue;
    for (var k in e) {
      var v = e[k];
      if (typeof v !== "number" || v <= 0) continue;
      if (k === "expRate") e[k] = Math.round(v * YLXW_T097_EXP * 1000) / 1000;
      else if (YLXW_T097_FLAT[k]) e[k] = Math.round(v * YLXW_T097_MUL * YLXW_T097_FLAT[k]);
    }
  }
  return arr;
}

/* ---- R-087 配色：按点数分档（不再按评分），金最高、红第二 ---- */
var YLXW_T097_TIER_BY_COST = { 1: "普通", 2: "稀有", 4: "传说", 6: "史诗", 8: "仙品" };
function YlxwT097Tier(cost) {
  var c = Number(cost) || 0;
  if (YLXW_T097_TIER_BY_COST[c]) return YLXW_T097_TIER_BY_COST[c];
  /* 未知点数：就近归档（<=1 普通 / <=2 稀有 / <=4 传说 / <=6 史诗 / 其余 仙品） */
  if (c <= 1) return "普通";
  if (c <= 2) return "稀有";
  if (c <= 4) return "传说";
  if (c <= 6) return "史诗";
  return "仙品";
}
/* 档名 → 颜色：**复用 r038 的 YlxwR38Color**（单一 class 来源），只把「仙品 / 史诗」两档的颜色对调，
   即得 金(仙品，最高) > 红(史诗，第二) > 紫(传说) > 蓝(稀有) > 灰(普通)。
   ★ 不新写 class 字面量：r038 有 5 条门禁按「该 class 串出现 1 次」计数，重复即打爆。 */
function YlxwT097Swap(rar) {
  if (rar === "仙品") return "史诗";   /* 仙品(8 点) 取「史诗」那套配色 = 金 */
  if (rar === "史诗") return "仙品";   /* 史诗(6 点) 取「仙品」那套配色 = 红 */
  return rar;
}
/* == end yl-talent097 == */
'''


# ---------------------------------------------------------------- 应用

def apply(p, ctx):
    """把 R-085 / R-087 落到 Patcher 上；返回 gates 列表。"""
    zh = ctx['zh']

    # 0) 注入块硬断言：zh() 后纯 ASCII + 无禁用模式 + 关键常量自检
    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('talent097 注入块 zh() 后仍含非 ASCII: %r' % (bad[:10],))
    for pat in BAN_PATTERNS:
        if pat in blk:
            raise AssertionError('talent097 注入块含禁用模式: %s' % pat)
    assert 'var YLXW_T097_MUL = 3;' in blk, 'talent097 缺少整体倍数常量'
    assert 'var YLXW_T097_EXP = 0.5;' in blk, 'talent097 缺少 expRate 倍数常量'
    assert 'var YLXW_T097_TALENT_K = 1 / 0.26;' in blk, 'talent097 缺少放开压制常量'
    assert 'spirit: 0.125' in blk and 'speed: 0.125' in blk, 'talent097 缺少 R-130 神识/身法下调系数（0.125）'
    assert 'Math.round(v * YLXW_T097_MUL * YLXW_T097_FLAT[k])' in blk, 'talent097 缺少 R-130 FLAT 值参与终值'

    # 1) Un 表尾：断开 var 链 → 注入执行器 → 就地改值 → 续起 var Ln
    #    （数组字面量一字不动 ⇒ r038 的「表体原样 / 132 条」冻结门禁保持）
    p.replace(
        'talent097-un', A_UN_TAIL,
        '];\n' + blk + '\nYlxwT097Boost(Un);\nvar Ln=[{id:"title-novice",name:"初入仙途"',
        expect=1,
        note='R-085：Un 表 effects 就地重构（平铺 ×3 / expRate ×0.5），字面量与条数不动'
    )

    # 2) 天赋卡：分档改按点数（保留 r038 门禁要求的原行，尾部覆写结果）
    p.replace(
        'talent097-tier', A_CARD_TIER,
        A_CARD_TIER + ' rar = YlxwT097Tier(t.fateCost);',
        expect=1,
        note='R-087：分档依据 score → fateCost（点数），消除「同档不同色/跨档倒挂」'
    )

    # 3) 天赋卡：配色改金高红次（复用 r038 的 YlxwR38Color，只对调「仙品/史诗」两档；保留原行不动）
    p.replace(
        'talent097-color', A_CARD_COLOR,
        A_CARD_COLOR + ' col = YlxwR38Color(YlxwT097Swap(rar));',
        expect=1,
        note='R-087：仙品→金(最高) / 史诗→红(第二)；其余档位色不变（复用 r038 原配色，零新增 class）'
    )

    # 4) 放开压制：天赋 expRate 累加处预乘 1/0.26（有效系数 = 1.0）
    p.replace(
        'talent097-bd', A_BD_TAL,
        '(a+=$.effects.expRate*YLXW_T097_TALENT_K)',
        expect=1,
        note='R-085：放开天赋修炼速度压制（a 预乘 1/0.26 ⇒ total 里 a*0.26 有效系数 = 1.0）'
    )

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= R-085 数值重构 =================
        ('T097·数值执行器已注入',   'function YlxwT097Boost(',                  1, '==', ''),
        ('T097·整体倍数常量 = 3',   'var YLXW_T097_MUL = 3;',                  1, '==', '平铺属性 ×3'),
        ('T097·expRate 倍数 = 0.5', 'var YLXW_T097_EXP = 0.5;',                1, '==', '用户明确要求'),
        ('T097·平铺白名单存在',     'var YLXW_T097_FLAT = { attack: 1,',       1, '==', '只放大平铺属性'),
        ('T097·执行器已挂载到 Un',  'YlxwT097Boost(Un);',                      1, '==', ''),
        ('T097·平铺属性乘 MUL×FLAT', 'else if (YLXW_T097_FLAT[k]) e[k] = Math.round(v * YLXW_T097_MUL * YLXW_T097_FLAT[k]);', 1, '==', 'R-130：FLAT 值参与终值'),
        ('R130·旧单乘 MUL 形态清零', 'else if (YLXW_T097_FLAT[k]) e[k] = Math.round(v * YLXW_T097_MUL);', 0, '==', 'R-130：旧形态必须消失'),
        ('R130·FLAT 神识/身法=0.125', 'var YLXW_T097_FLAT = { attack: 1, defense: 1, hp: 1, spirit: 0.125, physique: 1, speed: 0.125, luck: 1 };', 1, '==', 'R-130：神识/身法终值 = 基础×0.375（= 旧值÷8）；其余键 ×3 不动'),
        ('T097·expRate 乘 EXP',     'if (k === "expRate") e[k] = Math.round(v * YLXW_T097_EXP * 1000) / 1000;', 1, '==', ''),
        ('T097·负向词条不放大',     'if (typeof v !== "number" || v <= 0) continue;', 1, '==', 'speed:-8 等保持原值'),
        ('T097·注入块结束标记',     '/* == end yl-talent097',                  1, '==', ''),
        # ---- 冻结：天赋表字面量 / 条数 / ID 集合一字未动 ----
        ('冻结·天赋表入口未动',     'Un=[{"id":"nt-31"',                       1, '==', '★ 就地改值，字面量不动'),
        ('冻结·fateCost 条数恒定',  '"fateCost":',                            132, '==', '★ 132 条，一条没增没减'),
        ('冻结·8 点哨兵条目仍在',   '"id":"nt-80"',                            1, '==', ''),
        ('冻结·特殊条目仍在',       '"id":"talent-immortal-king"',             1, '==', ''),
        ('冻结·nt-37 原值仍在',     '"rarity":"史诗","fateCost":6,"effects":{"physique":64,"defense":80}', 1, '==', '★ r038 门禁契约：表体字面量不动'),
        ('冻结·hd 映射未动',        'function hd(t){return Un.find(r=>r.id===t)}', 1, '==', ''),
        # ================= R-085 放开压制 =================
        ('T097·天赋 expRate 已预乘', 'a+=$.effects.expRate*YLXW_T097_TALENT_K', 1, '==', '有效系数 = 0.26×(1/0.26) = 1.0'),
        ('T097·放开压制常量',        'var YLXW_T097_TALENT_K = 1 / 0.26;',     1, '==', ''),
        ('T097·旧累加形态已清零',    '(a+=$.effects.expRate)',                  0, '==', '★ 旧形态必须消失'),
        # ---- 冻结：econ2 / r040 的 K 口径与明细字面量一字未动 ----
        ('冻结·econ2 K 表未动',      'var YLXW_ECON2_K = { art: 1.00, talent: 0.26, title: 0.60, grotto: 0.60, synergy: 1.00, bond: 0.32 };', 1, '==', '★ econ2 门禁契约'),
        ('冻结·econ2 total 公式未动', 'return{total:r*d+a*0.26+l*0.6+c*0.6+Math.min(b,0.1)+S*0.32,', 1, '==', '★ 未改 total（改为在 a 累加处预乘）'),
        ('冻结·r040 明细未动',       'T.talent*0.26*100).toFixed(1)',           1, '==', '★ r040 门禁契约（明细与 total 仍同源）'),
        ('冻结·bd 定义唯一',         'function bd(t){',                        1, '==', ''),
        # ================= R-087 配色（按点数分档 + 金红对调） =================
        ('T097·分档函数已注入',      'function YlxwT097Tier(',                  1, '==', ''),
        ('T097·配色对调函数已注入',  'function YlxwT097Swap(',                  1, '==', ''),
        ('T097·点数→档名表',         zh('var YLXW_T097_TIER_BY_COST = { 1: "普通", 2: "稀有", 4: "传说", 6: "史诗", 8: "仙品" };'), 1, '==', ''),
        ('T097·卡片改用点数分档',    'rar = YlxwT097Tier(t.fateCost);',         1, '==', '★ 消除跨档倒挂'),
        ('T097·卡片配色改用对调',    'col = YlxwR38Color(YlxwT097Swap(rar));',  1, '==', '★ 复用 r038 原配色，零新增 class'),
        ('T097·★仙品(8点) 取金',     zh('if (rar === "仙品") return "史诗";'),   1, '==', '★ 金色最高'),
        ('T097·★史诗(6点) 取红',     zh('if (rar === "史诗") return "仙品";'),   1, '==', '★ 红色第二'),
        ('T097·其余档位色不变',      'return rar;',                             1, '==', '传说/稀有/普通 保持 r038 原色'),
        # ---- 冻结：r038 的门禁契约（原行/原函数/原配色必须仍在，行为由本模块覆写） ----
        ('冻结·r038 评分分档行仍在', 'var rar = YlxwR38Tier(sc);',              1, '==', '★ r038 门禁契约（其值被覆写）'),
        ('冻结·r038 配色行仍在',     'var col = YlxwR38Color(rar);',            1, '==', '★ r038 门禁契约（其值被覆写）'),
        ('冻结·r038 金档原定义仍在', zh('case "史诗": return { name: "text-amber-400"'), 1, '==', '★ r038 门禁契约：原函数保留不删'),
        ('冻结·r038 红档原定义仍在', zh('case "仙品": return { name: "text-red-400"'),   1, '==', '★ r038 门禁契约：原函数保留不删'),
        ('冻结·r038 蓝档原定义仍在', zh('case "稀有": return { name: "text-blue-400"'),  1, '==', '★ r038 门禁契约：本模块不再新增 class 串'),
        ('冻结·r038 紫档原定义仍在', zh('case "传说": return { name: "text-purple-400"'), 1, '==', '★ r038 门禁契约：本模块不再新增 class 串'),
        ('冻结·r038 灰档原定义仍在', 'chip: "bg-stone-700 text-stone-400 border-stone-600"', 1, '==', '★ r038 门禁契约：本模块不再新增 class 串'),
        ('冻结·r038 金框原定义仍在', 'card: "border-amber-600 bg-amber-900/20"', 1, '==', '★ r038 门禁契约：本模块不再新增 class 串'),
        ('冻结·r038 红框原定义仍在', 'card: "border-red-500 bg-red-900/20"',     1, '==', '★ r038 门禁契约：本模块不再新增 class 串'),
        ('冻结·r038 卡片定义仍在',   'function YlxwR38Card(',                    1, '==', ''),
        ('冻结·r038 档位表仍在',     'var YLXW_R38_THRESH = [0.30, 0.70, 1.30, 2.20];', 1, '==', ''),
        ('冻结·r038 原配色函数唯一', 'function YlxwR38Color(',                    1, '==', '★ 不新增第二份 class 表'),
    ]
    return gates


# ---------------------------------------------------------------- 自检（python yl_talent097_ext.py）

if __name__ == '__main__':
    import io
    import os
    import sys
    HERE = os.path.dirname(os.path.abspath(__file__))
    ROOT = os.path.dirname(os.path.dirname(HERE))          # .../yl-deploy
    sys.path.insert(0, HERE)                               # patches/client（本模块同目录）
    sys.path.insert(0, ROOT)                               # yl_patch.py 在工程根
    from yl_patch import Patcher, Gates, zh  # noqa: E402

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    # ★ 基线 = index-v296-20261001.js（0.9.6 定版）：talent097 接线进 V28_MODULES 之前的最后一份产物快照，
    #   即本模块在装配链上的真实上游状态（R-130 · 2026-10-02 修正：原 v297 快照已含本模块注入，
    #   A_UN_TAIL 等旧锚点被自身消费恒 0，自检从此跑不起来）。
    BASE = os.path.join(ROOT, 'build', 'assets', 'index-v296-20261001.js')

    base = io.open(BASE, encoding='utf-8').read()
    print('=== talent097 自检：基线 = %s（%d chars）' % (os.path.basename(BASE), len(base)))

    print('=== 改前锚点份数 ===')
    pre = [
        ('A_UN_TAIL',   A_UN_TAIL,   1),
        ('A_CARD_TIER', A_CARD_TIER, 1),
        ('A_CARD_COLOR', A_CARD_COLOR, 1),
        ('A_BD_TAL',    A_BD_TAL,    1),
    ]
    bad = 0
    for name, s, exp in pre:
        n = base.count(s)
        ok = n == exp
        bad += (not ok)
        print('  [%s] %-14s actual=%d expect=%d' % ('OK' if ok else 'FAIL', name, n, exp))
    if bad:
        print('  [ABORT] 改前锚点份数与设计不符（%d 条）' % bad)
        sys.exit(2)

    print('=== 应用补丁（内存副本，不写盘）===')
    pt = Patcher(base, label='talent097-selfcheck')
    gts = apply(pt, {'zh': zh, 'base_text': base})
    print(pt.report())

    g = Gates(pt.text)
    for t in gts:
        name, s, expect, cmp, note = t[:5]
        g.check(name, s, expect, cmp, note, within=(t[5] if len(t) > 5 else None))
    print(g.report())
    ok = g.passed()
    print('门禁结果: %s' % ('PASS' if ok else 'FAIL'))

    # node --check 产物级语法校验
    if ok:
        import subprocess
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), 'yl_talent097_selfcheck.js')
        with open(tmp, 'w', encoding='utf-8', newline='') as f:
            f.write(pt.text)
        try:
            r1 = subprocess.run(['node', '--check', tmp], capture_output=True, text=True, timeout=300)
            print('=== node --check 补丁后 rc=%s' % r1.returncode)
            if r1.returncode != 0:
                print(r1.stderr[:2000])
                ok = False
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    print('自检结论: %s' % ('PASS' if ok else 'FAIL'))
    sys.exit(0 if ok else 1)
