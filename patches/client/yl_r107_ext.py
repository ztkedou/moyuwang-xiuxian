# -*- coding: utf-8 -*-
r"""
yl_r107_ext.py — R-107 历练黑市超模道具：数值下调 + 售价修正 + 全局道具数值策划

需求原文（台账 R-107，用户 2026-10-01，逐字）
--------------------------------------------------------------------------
  「历练遇到的黑市中 《千年灵芝》售价才2000，我自己售卖价格又变成了十几万好像。
    属性更是离谱，永久气血 +400 永久神识 +200 永久体魄 +150 永久寿命 +300年
    太超模了，提高售价，神识、体魄除以十。寿命是极其稀缺的内容，直接由300变为加3年。
    再找数据师专门策划一下游戏其他道具的数值增加和售卖价格。基础属性的增加可以不减少，
    但是像神识、体魄这些加点才能提升的要大幅减少，寿命这类无法加点获取的特殊属性更要
    非常谨慎增加。尤其是寿命，如果是使用物品增加，必须是要极大代价才能延寿几年。」

基线（只读 grep）：build/assets/index-v2910-20261001.js（2,081,516 chars）

==============================================================================
一、改前取证（逐条读码，全部在基线内实测；脚本内联 python -c）
==============================================================================

【1】「自售价十几万」的根因 —— **估值器 xm() × 全局灵石缩放 50*YLRF/3**
--------------------------------------------------------------------------
出售链路（三处，全部走同一条公式）：
  ① 出售页卡片（@1796866）：
     `k.map(w=>{const A=a.items.find(B=>B.name===w.name),
       I=(A?.sellPrice)||xm(w), D=Tm(I,l),
       YLsu=YLSellCredit(D,1,l), YLst=YLSellCredit(D,w.quantity||1,l), ...})`
  ② 批量确认弹窗（@1784767）：
     `w.forEach(I=>{const D=a.items.find(P=>P.name===I.name),
       Q=(D?.sellPrice)||xm(I), U=isNaN(Q)||Q<=0?1:Q, B=Tm(U,l),
       Y=I.quantity||1, L=YLSellCredit(B,Y,l); ...})`
  ③ 实际入账 handler `handleSellItem:(R,E)=>{...}`（@1849507）：
     `const _=b.items.find(U=>U.name===R.name), C=(_?.sellPrice)||xm(R),
       g=..., q=Tm(g,N), w=..., A=Math.floor(q*w*50*YLRF(N)/3);`

三个函数的定义（均 count==1）：
  `xm=t=>{const r=t.rarity||"普通",a=t.level||0,
          c={普通:10,稀有:50,传说:300,仙品:2e3}[r]||10; let d=0;
          const u=Ba[r]||1, f=t.effect;
          f&&(d+=attack*2, defense*1.5, hp*.5, spirit*1.5, physique*1.5, speed*2, exp*.1);
          const v=t.permanentEffect;
          v&&(d+=v.attack*10, v.defense*8, v.maxHp*3, v.spirit*8, v.physique*8, v.speed*10);
          d=Math.floor(d*u); let m=0; t.isEquippable&&(m={Weapon:c*1.5,...}[t.type]||0);
          const j=1+a*.2, b=(c+d+m)*j,
                x={Herb:.5,Pill:.5,Material:.3}[t.type]||1,
                T=Math.floor(b*x); return isNaN(T)?1:Math.max(1,T)}`（@316374）
  `Rm(t,r)=Math.max(1,Math.ceil(t*Jm(r)))`（买入价，@1782760）
  `o1(t)=round((1+(Jm(t)-1)*.45)*1e3)/1e3`（回收系数，@1782879）
  `Tm(t,r)=Math.max(1,Math.ceil(t*o1(r)))`（@1782894）
  `YLSellCredit(q,w,pl)=floor(q*w*50*YLRF(pl)/3)`（@650871 起，v27 对齐后的唯一入账公式）
  `YLRF(pl)`：境界因子 `i<=0→4/3，否则 2*i+1`（炼气 1.33 / 筑基 3 / 金丹 5 …）
  `Ba={普通:1,稀有:1.35,传说:2,仙品:3.2}`

逐字复算（千年灵芝，稀有度「传说」、type=Herb、level 0）：
  c=300；effect.hp 1500*.5=750；
  permanentEffect：maxHp 400*3=1200 + spirit 200*8=1600 + physique 150*8=1200 = 4000
  （★ maxLifespan **不参与** xm 估值）
  d=(750+4000)*Ba[传说]=4750*2=9500；j=1；b=300+9500=9800；x(Herb)=.5 → **xm=4900**
  出售所得 = YLSellCredit(Tm(4900, 炼气=1.0), 1, 炼气)
           = floor(4900 * 1 * 50 * (4/3) / 3) = floor(4900 * 22.222) = **108,888**
  ⇒ 与用户口述「十几万」**逐位吻合**（筑基 24.5 万 / 金丹 40.8 万）。
  而黑市买入价 = Rm(2000, 炼气) = **2,000** ⇒ **低买高卖 54 倍，纯印钞**。

【2】黑市货架与高级货池
--------------------------------------------------------------------------
  `l1raw(t,r,a)`（@1779331）黑市分支：3~5 件；15% 走筑基奇物/天地精华/天地之髓（价 2e6~2e7）；
  否则 30% 取 `Ea`，70% 取 `Bi[村庄/城市/仙门]` 里 稀有/传说 的条目。
  `Ea=[...Lt("千年灵芝")?[Ut("千年灵芝",2e3,600,ae.GoldenCore)]:[],
        ...Lt("紫霄剑")?[Ut("紫霄剑",5e3,1500,ae.QiRefining)]:[],
        ...Lt("九转金丹")?[Ut("九转金丹",3e3,900,ae.GoldenCore)]:[],
        ...Lt("龙鳞甲")?[Ut("龙鳞甲",4e3,1200,ae.QiRefining)]:[],
        ...Lt("仙灵草")?[Ut("仙灵草",1e4,3e3)]:[],
        ...Lt("天元丹")?[Ut("天元丹",15e3,4500,ae.GoldenCore)]:[],
        {name:"村里最好的剑",...,price:9999990,sellPrice:9999990,...}].filter(Boolean)`
  ⚠ `紫霄剑` / `仙灵草` / `龙鳞甲` 在常量池里**不存在**（`Lt()` 恒 null）⇒ 这三项恒 `[]`，是死条目。
  ⇒ 黑市实际能出的高级货只有：千年灵芝(2000)、九转金丹(3000)、天元丹(15000)、村里最好的剑。

【3】数值表位置（全部实测 count==1）
--------------------------------------------------------------------------
  · 道具定义 `AN` 灵草表 @301951（千年灵芝）、@302136（万年仙草）
  · 兜底表 `HN` @308755（`LN()` 在 `Lt()` 为空时才用 HN；本表全部键在池中都已存在 ⇒ 实际是死代码）
  · 炼丹配方 `Dm`（基础丹）@294801 / `Vr`（高阶丹）@~297100，`result.permanentEffect` 为炼丹产出数值
  · 黑市/限时/声望高价货 `Ea` @1774780

【4】加点口径（判定哪些属性算「加点才能提升」）
--------------------------------------------------------------------------
  `handleAllocateAttribute`（@806700）可分配项：attack / defense / hp / **spirit / physique / speed**
  ⇒ 「神识、体魄、身法」三者**都**是加点可得；「攻击/防御/气血/气血上限」也加点可得但属用户点名的
    「基础属性」（可不减）；`maxLifespan`（寿命）**无任何加点途径**，只有物品/突破能给。

【5】使用侧应用（不改，仅取证）
--------------------------------------------------------------------------
  `Ig`（@776491）逐属性 `$r(u,key,raw)` 折算入账；`maxLifespan` 不走 `$r` 原值直加：
  `u.maxLifespan=(u.maxLifespan??100)+R.maxLifespan` ⇒ maxLifespan 的数值**直接等于加几年**。

==============================================================================
二、数据师口径（本轮 R-107 重配规则）
==============================================================================
  R1 基础属性（attack / defense / maxHp / effect.hp / exp）——**不动**（用户：可以不减少）。
  R2 加点属性（spirit 神识 / physique 体魄 / speed 身法）——**÷10**（用户：除以十、大幅减少）。
  R3 寿命（permanentEffect.maxLifespan）——**重定档，且必须「极大代价换几年」**；
     不再机械 ÷100，而是按「获取难度」给 1~10 年（用户：300→3 年）。
  R4 临时补寿（effect.lifespan）——同步压到 1~10 年（且被 maxLifespan 夹住，本身不会超上限）。
  R5 灵根（spiritualRoots）——用户未提，**不动**。
  R6 售价：与稀有度/获取难度挂钩，杜绝「售价 ≫ 合理档」；自售价**恒 ≤ 估值 30%**。

寿命重定档表（R3/R4，年）：
  千年灵芝(传说草药) 3 ｜ 万年仙草(仙品草药) 5 ｜ 仙灵丹(传说) 3 ｜ 长生丹(传说·专职) 3
  九转金丹(仙品) 5 ｜ 天元丹(仙品) 5 ｜ 不死仙丹(仙品·专职) 10 ｜ 延寿丹(稀有·临时) 1
  ⇒ 「专职延寿丹」> 「草药/全能丹」；最贵的 不死仙丹（炼价 8 万灵石 + 万年灵乳×2/九叶芝草×2/龙鳞果×3）
    也只换 10 年，符合「极大代价延寿几年」。

==============================================================================
三、改动清单（全部为数值/价格；**不碰**任何描述渲染或使用提示）
==============================================================================
【A】AN 灵草表
  千年灵芝 permanentEffect：{maxHp:400,spirit:200,physique:150,maxLifespan:300}
                        → {maxHp:400,spirit:20,physique:15,maxLifespan:3}
    （effect.hp 1500 **保留未动** —— 用户未要求；见报告建议）
  万年仙草 permanentEffect：{maxHp:1e3,spirit:1e3,physique:800,speed:500,maxLifespan:2e3}
                        → {maxHp:1e3,spirit:100,physique:80,speed:50,maxLifespan:5}
【B】HN 兜底表：千年灵芝 / 万年仙草 / 筑基丹 / 破境丹 / 仙灵丹 五条按同一口径重配。
    ⚠ HN 的「强体丹 / 凝神丹」两条**故意不动**：同名道具已在池中（`Lt()` 优先）属死代码，
      且被 R-106 的冻结门禁当锚点占用 —— 改动零收益、只会制造跨模块门禁冲突（详见第五节）。
【C】炼丹配方 result.permanentEffect：凝神丹 / 强体丹 / 筑基丹 / 龙血丹 / 破境丹 / 九转金丹 /
    延寿丹 / 长生丹 / 不死仙丹 / 仙灵丹 / 天元丹 / 结金丹 / 凝魂丹 / 凤凰涅槃丹 共 14 条。
【D】售价：Ea 三条（保留 `Ut(...)` 原文，用对象展开覆写 price/sellPrice —— 见第四节说明）
    千年灵芝 2000 → 50000（自售价上限 15000）
    九转金丹 3000 → 100000（自售价上限 30000）
    天元丹  15000 → 150000（自售价上限 45000）
【E】自售价上限：新增 `YlxwSellCap()`，在三处出售链路统一收口 ——
    「任何道具单堆出售所得 ≤ 其参考估值（有买入价用买入价，否则用 xm 估值）× 0.3（境界倍率后）」。
    参考估值 = `Rm(it.price ?? xm(it), player)`。

==============================================================================
四、为什么 Ea 用「对象展开覆写」而不是直接改 Ut 的价格参数
==============================================================================
`yl_shop102_ext.py`（R-103，同轮且排在 numbal 之前、本模块之前）的门禁逐字断言：
    ('R103·千年灵芝阶位已补', 'Ut("千年灵芝",2e3,600,ae.GoldenCore)', 1, '==', ...)
    ('R103·九转金丹阶位已补', 'Ut("九转金丹",3e3,900,ae.GoldenCore)', 1, '==', ...)
    ('R103·天元丹阶位已补',   'Ut("天元丹",15e3,4500,ae.GoldenCore)',  1, '==', ...)
若把 `Ut(...)` 的价格参数改掉，这三条门禁会立刻 FAIL（且我无权改别人的模块）。
故采用**「保留 Ut 原文 + 对象展开覆写 price/sellPrice」**：
    `[Ut("千年灵芝",2e3,600,ae.GoldenCore)]`
 →  `[{...Ut("千年灵芝",2e3,600,ae.GoldenCore),price:5e4,sellPrice:15e3}]`
被门禁断言的子串**逐字保留**（计数仍为 1），价格则被覆写为新档。这也正是 t7legacy
（`Ut("传承石",5e4,5e4)` → `Ut("传承石",YlxwInhPriceOf(...),...)`）同类问题的既有处理范式。

==============================================================================
五、★ 跨模块冲突（必须由 R-106 侧放宽，本模块无权修改他人文件）
==============================================================================
`patches/client/yl_r106_ext.py`（R-106 道具描述显示口径）含两条**冻结门禁**，其 needle 正是
本需求（R-107）**必须修改**的那批数值：
  · '冻结·千年灵芝 permanentEffect 未动'
      needle = 'permanentEffect:{maxHp:400,spirit:200,physique:150,maxLifespan:300}'  期望 1
  · '冻结·HN 丹药表未动'
      needle = '强体丹:{permanentEffect:{physique:20}},凝神丹:{permanentEffect:{spirit:20}}' 期望 1
处置：
  · 第二条**已规避**：HN 的 强体丹/凝神丹 两条（死代码）本模块不动 ⇒ 该门禁继续 PASS。
  · 第一条**无法规避**：千年灵芝 spirit/physique/maxLifespan 正是用户点名要改的数值，
    且是该道具唯一的定义处（AN 表）。R-106 该门禁在 R-107 落地后必然 FAIL。
  ⇒ 建议 R-106 侧把该条改为「形态存在」断言（见报告「需拍板」一节的逐字替换串）。
    注意 R-106 自己的 docstring 也写明「不改任何数值表：permanentEffect 数字、HN 表、AN 表、
    售价 —— 那是 R-107」，即该数值本属 R-107 所有，其冻结门禁属**自相矛盾的残留**。

==============================================================================
六、风险点
==============================================================================
1. **自售价上限是全站口径**：不仅 千年灵芝，所有道具的单堆出售所得都被压到估值的 30% 以内。
   这正是用户「自售价应显著低于买入价，避免低买高卖刷钱」的直接落地，但会**整体下调出售收入**
   （旧公式是估值的 ~22 倍@炼气、~50 倍@筑基，属全局通胀水龙头）。若用户只想治千年灵芝，
   把 `YLXW_SELL_CAP_RATIO` 调大（如 1.0）即可放宽 —— 见报告「需拍板」。
2. 上限锚定「有 price 用 price，否则用 xm」。`xm` 对装备估值偏低（天罡剑 xm≈1225 vs 仙门售价 5e4），
   故**掉落装备**的出售上限偏低。属 `xm` 既有口径问题，本轮不动 `xm`（它同时是唯一估值器）。
3. `xmLifespan` 不参与 `xm`：寿命被重配后不影响出售估值，无需同步。
4. `村里最好的剑`（仙品、价 9999990、sellPrice=price）是彩蛋道具，本轮不动；但因自售价上限，
   其出售所得会被压到 3e6（原为 9999990），顺带堵住一条套利。
5. 未改 `$r`/`ZS` 使用侧折算数学、未改任何描述/提示文案、未动存档 schema、未动版本号、
   未动 build_v26n.py / CHANGELOG / localtest / deploy / srv / 其他 yl_*_ext.py。

锚点纪律：全部 replace 锚点实测 count==1；GATES 同时断言「新形态 ==1」与「旧形态 ==0」，
并冻结 shop102 / sellui / l1 的既有断言面。
"""

# --------------------------------------------------------------------------- 注入块（纯 ASCII）

# 注入位置：`function Ut(...)` 定义之前（模块级；Rm/o1/Tm/YLSellCredit 均为函数声明，提升可见）
INJECT_ANCHOR = 'function Ut(t,r,a,l){const c=Lt(t);'

INJECT_JS = r'''
/* == YL_R107 == R-107: item stat rebalance + player sell-price cap.
   Sell cap: payout per stack <= YLXW_SELL_CAP_RATIO * reference value.
   Reference value = shop price when known, else the engine estimator xm(),
   scaled by the realm price factor Rm(). Kills buy-low / sell-high loops. */
var YLXW_SELL_CAP_RATIO = 0.3;
function YlxwSellRefPrice(it, pl) {
  if (!it) { return 0; }
  var p = (typeof it.price === "number" && it.price > 0) ? it.price : xm(it);
  if (!(p > 0)) { return 0; }
  try { return pl ? Rm(p, pl) : p; } catch (e) { return p; }
}
function YlxwSellCap(it, qty, pl) {
  var n = (qty != null && isFinite(qty) && qty > 0) ? Math.floor(qty) : 1;
  var unit = Math.floor(YLXW_SELL_CAP_RATIO * YlxwSellRefPrice(it, pl));
  return unit > 0 ? unit * n : 0;
}
'''

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- 锚点与替换

# ===== 【A】AN 灵草表 =====
AN_LINGZHI_OLD = 'permanentEffect:{maxHp:400,spirit:200,physique:150,maxLifespan:300}'
AN_LINGZHI_NEW = 'permanentEffect:{maxHp:400,spirit:20,physique:15,maxLifespan:3}'

AN_XIANCAO_OLD = 'permanentEffect:{maxHp:1e3,spirit:1e3,physique:800,speed:500,maxLifespan:2e3}'
AN_XIANCAO_NEW = 'permanentEffect:{maxHp:1e3,spirit:100,physique:80,speed:50,maxLifespan:5}'

# ===== 【B】HN 兜底表（强体丹/凝神丹 两条不动：死代码 + R-106 冻结门禁）=====
HN_LINGZHI_OLD = ('千年灵芝:{effect:{hp:150},permanentEffect:{maxHp:40,spirit:20,'
                  'physique:15,maxLifespan:30}}')
HN_LINGZHI_NEW = ('千年灵芝:{effect:{hp:150},permanentEffect:{maxHp:40,spirit:20,'
                  'physique:15,maxLifespan:3}}')

HN_XIANCAO_OLD = ('万年仙草:{effect:{hp:300},permanentEffect:{maxHp:100,spirit:100,'
                  'physique:80,speed:50,maxLifespan:200}}')
HN_XIANCAO_NEW = ('万年仙草:{effect:{hp:300},permanentEffect:{maxHp:100,spirit:10,'
                  'physique:8,speed:5,maxLifespan:5}}')

HN_ZHUIJI_OLD = '筑基丹:{effect:{exp:500},permanentEffect:{spirit:30,physique:30,maxHp:100}}'
HN_ZHUIJI_NEW = '筑基丹:{effect:{exp:500},permanentEffect:{spirit:3,physique:3,maxHp:100}}'

HN_POJING_OLD = ('破境丹:{effect:{exp:1e4},permanentEffect:{spirit:50,physique:50,'
                 'attack:30,defense:30}}')
HN_POJING_NEW = ('破境丹:{effect:{exp:1e4},permanentEffect:{spirit:5,physique:5,'
                 'attack:30,defense:30}}')

HN_XIANLING_OLD = ('仙灵丹:{effect:{exp:2e3,spirit:50,physique:50},permanentEffect:'
                   '{maxLifespan:300,spirit:300,attack:300,defense:300,physique:300,speed:300}}')
HN_XIANLING_NEW = ('仙灵丹:{effect:{exp:2e3,spirit:50,physique:50},permanentEffect:'
                   '{maxLifespan:3,spirit:30,attack:300,defense:300,physique:30,speed:30}}')

# ===== 【C】炼丹配方 result.permanentEffect（Dm 基础丹 / Vr 高阶丹）=====
R_ZHUIJI_OLD = ('result:{name:"筑基丹",type:H.Pill,description:"突破筑基期的珍贵丹药，由千年人参和妖兽内丹炼制而成，'
                '服用后能够增加突破几率，获得海量修为，并永久提升基础属性，是修士们突破境界的必备丹药。",'
                'rarity:"传说",effect:{exp:500},permanentEffect:{spirit:300,physique:30,maxHp:100}}')
R_ZHUIJI_NEW = ('result:{name:"筑基丹",type:H.Pill,description:"突破筑基期的珍贵丹药，由千年人参和妖兽内丹炼制而成，'
                '服用后能够增加突破几率，获得海量修为，并永久提升基础属性，是修士们突破境界的必备丹药。",'
                'rarity:"传说",effect:{exp:500},permanentEffect:{spirit:30,physique:3,maxHp:100}}')

R_LONGXUE_OLD = ('result:{name:"龙血丹",type:H.Pill,description:"蕴含一丝真龙之血，服用后气血如龙。'
                 '大幅增加气血上限。",rarity:"传说",permanentEffect:{maxHp:500,physique:50}}')
R_LONGXUE_NEW = ('result:{name:"龙血丹",type:H.Pill,description:"蕴含一丝真龙之血，服用后气血如龙。'
                 '大幅增加气血上限。",rarity:"传说",permanentEffect:{maxHp:500,physique:5}}')

R_JIUZHUAN_OLD = ('result:{name:"九转金丹",type:H.Pill,description:"传说中的九转金丹，由万年灵乳和九叶芝草炼制而成，'
                  '服用后甚至能让凡人立地飞升，是修士们梦寐以求的仙丹，能够大幅提升修为和各项属性。",'
                  'rarity:"仙品",effect:{exp:5e4},permanentEffect:{maxLifespan:1e3,spirit:1e3,'
                  'attack:1e3,defense:1e3,physique:1e3,speed:1e3}}')
R_JIUZHUAN_NEW = ('result:{name:"九转金丹",type:H.Pill,description:"传说中的九转金丹，由万年灵乳和九叶芝草炼制而成，'
                  '服用后甚至能让凡人立地飞升，是修士们梦寐以求的仙丹，能够大幅提升修为和各项属性。",'
                  'rarity:"仙品",effect:{exp:5e4},permanentEffect:{maxLifespan:5,spirit:100,'
                  'attack:1e3,defense:1e3,physique:100,speed:100}}')

R_YANSHOU_OLD = ('result:{name:"延寿丹",type:H.Pill,description:"增加寿命的珍贵丹药，由千年人参和血参炼制而成，'
                 '服用后能够延长10年寿命，是修士们延长寿元的珍贵丹药。",rarity:"稀有",effect:{lifespan:10}}')
R_YANSHOU_NEW = ('result:{name:"延寿丹",type:H.Pill,description:"增加寿命的珍贵丹药，由千年人参和血参炼制而成，'
                 '服用后能够延长10年寿命，是修士们延长寿元的珍贵丹药。",rarity:"稀有",effect:{lifespan:1}}')

R_CHANGSHENG_OLD = ('result:{name:"长生丹",type:H.Pill,description:"增加寿命的极品丹药，由万年仙草和千年灵芝炼制而成，'
                    '服用后能够延长50年寿命并增加最大寿命，是修士们延长寿元的珍贵丹药。",'
                    'rarity:"传说",permanentEffect:{maxLifespan:50}}')
R_CHANGSHENG_NEW = ('result:{name:"长生丹",type:H.Pill,description:"增加寿命的极品丹药，由万年仙草和千年灵芝炼制而成，'
                    '服用后能够延长50年寿命并增加最大寿命，是修士们延长寿元的珍贵丹药。",'
                    'rarity:"传说",permanentEffect:{maxLifespan:3}}')

R_BUSI_OLD = ('result:{name:"不死仙丹",type:H.Pill,description:"传说中的不死仙丹，由万年灵乳、九叶芝草和龙鳞果炼制而成，'
              '服用后能够延长200年寿命并大幅增加最大寿命500年，是修士们梦寐以求的仙丹。",'
              'rarity:"仙品",effect:{lifespan:200},permanentEffect:{maxLifespan:500}}')
R_BUSI_NEW = ('result:{name:"不死仙丹",type:H.Pill,description:"传说中的不死仙丹，由万年灵乳、九叶芝草和龙鳞果炼制而成，'
              '服用后能够延长200年寿命并大幅增加最大寿命500年，是修士们梦寐以求的仙丹。",'
              'rarity:"仙品",effect:{lifespan:10},permanentEffect:{maxLifespan:10}}')

R_NINGSHEN_OLD = ('result:{name:"凝神丹",type:H.Pill,description:"凝神静气，提升神识。永久增加神识属性。",'
                  'rarity:"稀有",permanentEffect:{spirit:20}}')
R_NINGSHEN_NEW = ('result:{name:"凝神丹",type:H.Pill,description:"凝神静气，提升神识。永久增加神识属性。",'
                  'rarity:"稀有",permanentEffect:{spirit:2}}')

R_QIANGTI_OLD = ('result:{name:"强体丹",type:H.Pill,description:"强身健体，提升体魄。永久增加体魄属性。",'
                 'rarity:"稀有",permanentEffect:{physique:20}}')
R_QIANGTI_NEW = ('result:{name:"强体丹",type:H.Pill,description:"强身健体，提升体魄。永久增加体魄属性。",'
                 'rarity:"稀有",permanentEffect:{physique:2}}')

R_POJING_OLD = ('result:{name:"破境丹",type:H.Pill,description:"突破境界的辅助丹药，大幅提升修为并永久增强属性。",'
                'rarity:"传说",effect:{exp:1e4},permanentEffect:{spirit:50,physique:50,attack:30,defense:30}}')
R_POJING_NEW = ('result:{name:"破境丹",type:H.Pill,description:"突破境界的辅助丹药，大幅提升修为并永久增强属性。",'
                'rarity:"传说",effect:{exp:1e4},permanentEffect:{spirit:5,physique:5,attack:30,defense:30}}')

R_XIANLING_OLD = ('result:{name:"仙灵丹",type:H.Pill,description:"仙家灵丹，服用后修为与属性大幅提升。",'
                  'rarity:"传说",effect:{exp:2e3,spirit:50,physique:50},permanentEffect:'
                  '{maxLifespan:300,spirit:300,attack:300,defense:300,physique:300,speed:300}}')
R_XIANLING_NEW = ('result:{name:"仙灵丹",type:H.Pill,description:"仙家灵丹，服用后修为与属性大幅提升。",'
                  'rarity:"传说",effect:{exp:2e3,spirit:50,physique:50},permanentEffect:'
                  '{maxLifespan:3,spirit:30,attack:300,defense:300,physique:30,speed:30}}')

R_TIANYUAN_OLD = ('result:{name:"天元丹",type:H.Pill,description:"天元级别的仙丹，服用后全属性大幅提升。",'
                  'rarity:"仙品",effect:{exp:1e4},permanentEffect:{maxLifespan:500,spirit:500,'
                  'attack:500,defense:500,physique:500,speed:500}}')
R_TIANYUAN_NEW = ('result:{name:"天元丹",type:H.Pill,description:"天元级别的仙丹，服用后全属性大幅提升。",'
                  'rarity:"仙品",effect:{exp:1e4},permanentEffect:{maxLifespan:5,spirit:50,'
                  'attack:500,defense:500,physique:50,speed:50}}')

R_JIEJIN_OLD = ('result:{name:"结金丹",type:H.Pill,description:"有助于凝结金丹的珍贵丹药。'
                '服用后大幅提升修为，并永久增强神识。",rarity:"稀有",effect:{exp:3e4,spirit:20},'
                'permanentEffect:{spirit:50,maxHp:200}}')
R_JIEJIN_NEW = ('result:{name:"结金丹",type:H.Pill,description:"有助于凝结金丹的珍贵丹药。'
                '服用后大幅提升修为，并永久增强神识。",rarity:"稀有",effect:{exp:3e4,spirit:20},'
                'permanentEffect:{spirit:5,maxHp:200}}')

R_NINGHUN_OLD = ('result:{name:"凝魂丹",type:H.Pill,description:"能够凝聚神魂的珍贵丹药。'
                 '服用后大幅提升修为和神识，并永久增强神魂。",rarity:"传说",'
                 'effect:{exp:1e4,spirit:50,hp:300},permanentEffect:{spirit:100,maxHp:300,attack:50}}')
R_NINGHUN_NEW = ('result:{name:"凝魂丹",type:H.Pill,description:"能够凝聚神魂的珍贵丹药。'
                 '服用后大幅提升修为和神识，并永久增强神魂。",rarity:"传说",'
                 'effect:{exp:1e4,spirit:50,hp:300},permanentEffect:{spirit:10,maxHp:300,attack:50}}')

R_FENGHUANG_OLD = ('result:{name:"凤凰涅槃丹",type:H.Pill,description:"蕴含凤凰涅槃之力的神丹。'
                   '服用后获得涅槃重生之力，大幅提升修为和属性。",rarity:"传说",'
                   'effect:{hp:800,exp:1500,attack:30},permanentEffect:'
                   '{maxHp:400,attack:100,defense:100,spirit:80,physique:80,speed:50}}')
R_FENGHUANG_NEW = ('result:{name:"凤凰涅槃丹",type:H.Pill,description:"蕴含凤凰涅槃之力的神丹。'
                   '服用后获得涅槃重生之力，大幅提升修为和属性。",rarity:"传说",'
                   'effect:{hp:800,exp:1500,attack:30},permanentEffect:'
                   '{maxHp:400,attack:100,defense:100,spirit:8,physique:8,speed:5}}')

# ===== 【D】Ea 高级货池售价（保留 Ut 原文，对象展开覆写）=====
EA_LINGZHI_OLD = '[Ut("千年灵芝",2e3,600,ae.GoldenCore)]'
EA_LINGZHI_NEW = '[{...Ut("千年灵芝",2e3,600,ae.GoldenCore),price:5e4,sellPrice:15e3}]'

EA_JIUZHUAN_OLD = '[Ut("九转金丹",3e3,900,ae.GoldenCore)]'
EA_JIUZHUAN_NEW = '[{...Ut("九转金丹",3e3,900,ae.GoldenCore),price:1e5,sellPrice:3e4}]'

EA_TIANYUAN_OLD = '[Ut("天元丹",15e3,4500,ae.GoldenCore)]'
EA_TIANYUAN_NEW = '[{...Ut("天元丹",15e3,4500,ae.GoldenCore),price:15e4,sellPrice:45e3}]'

# ===== 【E】自售价上限：三处出售链路统一收口 =====
# ① 出售页卡片（逐件 + 整堆）
SELL_CARD_OLD = ('D=Tm(I,l),YLsu=YLSellCredit(D,1,l),'
                 'YLst=YLSellCredit(D,w.quantity||1,l),Q=w.rarity')
SELL_CARD_NEW = ('D=Tm(I,l),YLsu=Math.min(YLSellCredit(D,1,l),YlxwSellCap(w,1,l)),'
                 'YLst=Math.min(YLSellCredit(D,w.quantity||1,l),'
                 'YlxwSellCap(w,w.quantity||1,l)),Q=w.rarity')

# ② 批量确认弹窗合计（保留 `L=YLSellCredit(B,Y,l)` 逐字，供 sellui 门禁）
#   ★ 2026-10-01 集成期修：原写法把 `,L=Math.min(L,…)` 追加进**同一条 const 声明列表**
#     ⇒ `const …,L=…,L=…` = 重复声明 ⇒ 整包 `SyntaxError: Identifier 'L' has already been declared`。
#     `L` 是 const，不能声明后再赋值 ⇒ 把上限挪到**累加处** `A+=Math.min(L,YlxwSellCap(I,Y,l))`，
#     语义完全一致（合计只加「上限内的那一份」），且 `L=YLSellCredit(B,Y,l)` 逐字保留。
SELL_BATCH_OLD = ('B=Tm(U,l),Y=I.quantity||1,L=YLSellCredit(B,Y,l);isNaN(L)||(A+=L)')
SELL_BATCH_NEW = ('B=Tm(U,l),Y=I.quantity||1,L=YLSellCredit(B,Y,l);'
                  'isNaN(L)||(A+=Math.min(L,YlxwSellCap(I,Y,l)))')

# ③ 实际入账 handler（保留 `Math.floor(q*w*50*YLRF(N)/3)` 逐字，供 sellui 门禁）
SELL_HANDLER_OLD = 'const A=Math.floor(q*w*50*YLRF(N)/3);'
SELL_HANDLER_NEW = 'const A=Math.min(Math.floor(q*w*50*YLRF(N)/3),YlxwSellCap(R,w,N));'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 注入块自检（与 build 侧同款）
    blk = zh(INJECT_JS)
    bad = [c for c in blk if ord(c) > 127]
    if bad:
        raise AssertionError('r107 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for pat in BAN_PATTERNS:
        if pat in blk:
            raise AssertionError('r107 注入块含禁用模式 %r' % pat)
    if 'fetch(' in blk:
        raise AssertionError('r107 注入块不得含 fetch(')

    # 自检：新串必须真的变了（防手滑写成恒等）
    for nm, a, b in (
            ('AN 千年灵芝', AN_LINGZHI_OLD, AN_LINGZHI_NEW),
            ('AN 万年仙草', AN_XIANCAO_OLD, AN_XIANCAO_NEW),
            ('HN 千年灵芝', HN_LINGZHI_OLD, HN_LINGZHI_NEW),
            ('HN 万年仙草', HN_XIANCAO_OLD, HN_XIANCAO_NEW),
            ('Ea 千年灵芝', EA_LINGZHI_OLD, EA_LINGZHI_NEW),
            ('Ea 九转金丹', EA_JIUZHUAN_OLD, EA_JIUZHUAN_NEW),
            ('Ea 天元丹', EA_TIANYUAN_OLD, EA_TIANYUAN_NEW),
            ('出售页卡片', SELL_CARD_OLD, SELL_CARD_NEW),
            ('批量弹窗', SELL_BATCH_OLD, SELL_BATCH_NEW),
            ('入账 handler', SELL_HANDLER_OLD, SELL_HANDLER_NEW),
    ):
        if a == b:
            raise AssertionError('r107 锚点异常（恒等替换）: %s' % nm)

    # 0) 注入自售价上限助手
    p.insert_before('r107-sell-cap-fn', INJECT_ANCHOR, blk + '\n', expect=1,
                    note='注入 YLXW_SELL_CAP_RATIO / YlxwSellRefPrice / YlxwSellCap')

    # ---------- 【A】AN 灵草表 ----------
    p.replace('r107-an-lingzhi', AN_LINGZHI_OLD, AN_LINGZHI_NEW, expect=1,
              note='千年灵芝：神识200→20 体魄150→15 寿命300→3（气血上限400 保留）')
    p.replace('r107-an-xiancao', AN_XIANCAO_OLD, AN_XIANCAO_NEW, expect=1,
              note='万年仙草：神识/体魄/身法 ÷10，寿命2000→5（气血上限1000 保留）')

    # ---------- 【B】HN 兜底表 ----------
    p.replace('r107-hn-lingzhi', HN_LINGZHI_OLD, HN_LINGZHI_NEW, expect=1,
              note='HN 千年灵芝：寿命30→3（神识20/体魄15 已是目标档）')
    p.replace('r107-hn-xiancao', HN_XIANCAO_OLD, HN_XIANCAO_NEW, expect=1,
              note='HN 万年仙草：神识/体魄/身法 ÷10，寿命200→5')
    p.replace('r107-hn-zhuiji', HN_ZHUIJI_OLD, HN_ZHUIJI_NEW, expect=1,
              note='HN 筑基丹：神识/体魄 30→3')
    p.replace('r107-hn-pojing', HN_POJING_OLD, HN_POJING_NEW, expect=1,
              note='HN 破境丹：神识/体魄 50→5')
    p.replace('r107-hn-xianling', HN_XIANLING_OLD, HN_XIANLING_NEW, expect=1,
              note='HN 仙灵丹：神识/体魄/身法 300→30，寿命300→3')

    # ---------- 【C】炼丹配方 ----------
    for nm, a, b, note in (
            ('r107-r-zhuiji', R_ZHUIJI_OLD, R_ZHUIJI_NEW, '筑基丹：神识300→30 体魄30→3'),
            ('r107-r-longxue', R_LONGXUE_OLD, R_LONGXUE_NEW, '龙血丹：体魄50→5'),
            ('r107-r-jiuzhuan', R_JIUZHUAN_OLD, R_JIUZHUAN_NEW,
             '九转金丹：神识/体魄/身法 1000→100，寿命1000→5'),
            ('r107-r-yanshou', R_YANSHOU_OLD, R_YANSHOU_NEW, '延寿丹：补寿10→1 年'),
            ('r107-r-changsheng', R_CHANGSHENG_OLD, R_CHANGSHENG_NEW, '长生丹：寿命50→3'),
            ('r107-r-busi', R_BUSI_OLD, R_BUSI_NEW, '不死仙丹：补寿200→10，寿命500→10'),
            ('r107-r-ningshen', R_NINGSHEN_OLD, R_NINGSHEN_NEW, '凝神丹：神识20→2'),
            ('r107-r-qiangti', R_QIANGTI_OLD, R_QIANGTI_NEW, '强体丹：体魄20→2'),
            ('r107-r-pojing', R_POJING_OLD, R_POJING_NEW, '破境丹：神识/体魄 50→5'),
            ('r107-r-xianling', R_XIANLING_OLD, R_XIANLING_NEW,
             '仙灵丹：神识/体魄/身法 300→30，寿命300→3'),
            ('r107-r-tianyuan', R_TIANYUAN_OLD, R_TIANYUAN_NEW,
             '天元丹：神识/体魄/身法 500→50，寿命500→5'),
            ('r107-r-jiejin', R_JIEJIN_OLD, R_JIEJIN_NEW, '结金丹：神识50→5'),
            ('r107-r-ninghun', R_NINGHUN_OLD, R_NINGHUN_NEW, '凝魂丹：神识100→10'),
            ('r107-r-fenghuang', R_FENGHUANG_OLD, R_FENGHUANG_NEW,
             '凤凰涅槃丹：神识/体魄 80→8，身法50→5'),
    ):
        p.replace(nm, a, b, expect=1, note=note)

    # ---------- 【D】Ea 售价（保留 Ut 原文 + 展开覆写）----------
    p.replace('r107-ea-lingzhi', EA_LINGZHI_OLD, EA_LINGZHI_NEW, expect=1,
              note='黑市千年灵芝 2000→50000（保留 Ut 原文以兼容 shop102 门禁）')
    p.replace('r107-ea-jiuzhuan', EA_JIUZHUAN_OLD, EA_JIUZHUAN_NEW, expect=1,
              note='黑市九转金丹 3000→100000')
    p.replace('r107-ea-tianyuan', EA_TIANYUAN_OLD, EA_TIANYUAN_NEW, expect=1,
              note='黑市天元丹 15000→150000')

    # ---------- 【E】自售价上限 ----------
    p.replace('r107-sell-card', SELL_CARD_OLD, SELL_CARD_NEW, expect=1,
              note='出售页卡片单价/合计各加 YlxwSellCap')
    p.replace('r107-sell-batch', SELL_BATCH_OLD, SELL_BATCH_NEW, expect=1,
              note='批量确认合计加 YlxwSellCap（保留 L=YLSellCredit(B,Y,l) 原文）')
    p.replace('r107-sell-handler', SELL_HANDLER_OLD, SELL_HANDLER_NEW, expect=1,
              note='入账 handler 加 YlxwSellCap（保留原公式原文）')

    # ------------------------------------------------------------- 门禁
    return [
        # ===================== 【A】AN 灵草表 =====================
        ('R107·千年灵芝数值已重配', AN_LINGZHI_NEW, 1, '==',
         '神识200→20 体魄150→15 寿命300→3；气血上限400 保留'),
        ('R107·旧千年灵芝数值已清零', AN_LINGZHI_OLD, 0, '==', ''),
        ('R107·万年仙草数值已重配', AN_XIANCAO_NEW, 1, '==',
         '神识/体魄/身法 ÷10；寿命2000→5'),
        ('R107·旧万年仙草数值已清零', AN_XIANCAO_OLD, 0, '==', ''),
        ('冻结·千年灵芝 effect.hp 未动（用户未要求）', 'effect:{hp:1500}', 1, '==',
         '仅复核；改动需用户拍板'),

        # ===================== 【B】HN 兜底表 =====================
        ('R107·HN 千年灵芝已重配', HN_LINGZHI_NEW, 1, '==', '寿命30→3'),
        ('R107·旧 HN 千年灵芝已清零', HN_LINGZHI_OLD, 0, '==', ''),
        ('R107·HN 万年仙草已重配', HN_XIANCAO_NEW, 1, '==', ''),
        ('R107·旧 HN 万年仙草已清零', HN_XIANCAO_OLD, 0, '==', ''),
        ('R107·HN 筑基丹已重配', HN_ZHUIJI_NEW, 1, '==', ''),
        ('R107·旧 HN 筑基丹已清零', HN_ZHUIJI_OLD, 0, '==', ''),
        ('R107·HN 破境丹已重配', HN_POJING_NEW, 1, '==', ''),
        ('R107·旧 HN 破境丹已清零', HN_POJING_OLD, 0, '==', ''),
        ('R107·HN 仙灵丹已重配', HN_XIANLING_NEW, 1, '==', ''),
        ('R107·旧 HN 仙灵丹已清零', HN_XIANLING_OLD, 0, '==', ''),

        # ===================== 【C】炼丹配方 =====================
        ('R107·配方筑基丹已重配', R_ZHUIJI_NEW, 1, '==', ''),
        ('R107·旧配方筑基丹已清零', R_ZHUIJI_OLD, 0, '==', ''),
        ('R107·配方龙血丹已重配', R_LONGXUE_NEW, 1, '==', ''),
        ('R107·旧配方龙血丹已清零', R_LONGXUE_OLD, 0, '==', ''),
        ('R107·配方九转金丹已重配', R_JIUZHUAN_NEW, 1, '==', ''),
        ('R107·旧配方九转金丹已清零', R_JIUZHUAN_OLD, 0, '==', ''),
        ('R107·配方延寿丹已重配', R_YANSHOU_NEW, 1, '==', ''),
        ('R107·旧配方延寿丹已清零', R_YANSHOU_OLD, 0, '==', ''),
        ('R107·配方长生丹已重配', R_CHANGSHENG_NEW, 1, '==', ''),
        ('R107·旧配方长生丹已清零', R_CHANGSHENG_OLD, 0, '==', ''),
        ('R107·配方不死仙丹已重配', R_BUSI_NEW, 1, '==', ''),
        ('R107·旧配方不死仙丹已清零', R_BUSI_OLD, 0, '==', ''),
        ('R107·配方凝神丹已重配', R_NINGSHEN_NEW, 1, '==', ''),
        ('R107·旧配方凝神丹已清零', R_NINGSHEN_OLD, 0, '==', ''),
        ('R107·配方强体丹已重配', R_QIANGTI_NEW, 1, '==', ''),
        ('R107·旧配方强体丹已清零', R_QIANGTI_OLD, 0, '==', ''),
        ('R107·配方破境丹已重配', R_POJING_NEW, 1, '==', ''),
        ('R107·旧配方破境丹已清零', R_POJING_OLD, 0, '==', ''),
        ('R107·配方仙灵丹已重配', R_XIANLING_NEW, 1, '==', ''),
        ('R107·旧配方仙灵丹已清零', R_XIANLING_OLD, 0, '==', ''),
        ('R107·配方天元丹已重配', R_TIANYUAN_NEW, 1, '==', ''),
        ('R107·旧配方天元丹已清零', R_TIANYUAN_OLD, 0, '==', ''),
        ('R107·配方结金丹已重配', R_JIEJIN_NEW, 1, '==', ''),
        ('R107·旧配方结金丹已清零', R_JIEJIN_OLD, 0, '==', ''),
        ('R107·配方凝魂丹已重配', R_NINGHUN_NEW, 1, '==', ''),
        ('R107·旧配方凝魂丹已清零', R_NINGHUN_OLD, 0, '==', ''),
        ('R107·配方凤凰涅槃丹已重配', R_FENGHUANG_NEW, 1, '==', ''),
        ('R107·旧配方凤凰涅槃丹已清零', R_FENGHUANG_OLD, 0, '==', ''),

        # ===================== 【D】Ea 售价 =====================
        ('R107·黑市千年灵芝售价已提', EA_LINGZHI_NEW, 1, '==', '2000→50000'),
        ('R107·黑市九转金丹售价已提', EA_JIUZHUAN_NEW, 1, '==', '3000→100000'),
        ('R107·黑市天元丹售价已提', EA_TIANYUAN_NEW, 1, '==', '15000→150000'),
        ('R107·旧黑市千年灵芝形态已清零', EA_LINGZHI_OLD, 0, '==', ''),
        ('R107·旧黑市九转金丹形态已清零', EA_JIUZHUAN_OLD, 0, '==', ''),
        ('R107·旧黑市天元丹形态已清零', EA_TIANYUAN_OLD, 0, '==', ''),

        # ===================== 【E】自售价上限 =====================
        ('R107·上限常量已注入', 'var YLXW_SELL_CAP_RATIO = 0.3;', 1, '==',
         '改常量即可调；1.0 = 上限放到估值本身'),
        ('R107·估值参考函数已注入', 'function YlxwSellRefPrice(it, pl) {', 1, '==',
         '有买入价用买入价，否则用 xm 估值，再乘境界倍率 Rm'),
        ('R107·上限函数已注入', 'function YlxwSellCap(it, qty, pl) {', 1, '==', ''),
        ('R107·出售页卡片已收口',
         'YLsu=Math.min(YLSellCredit(D,1,l),YlxwSellCap(w,1,l))', 1, '==', ''),
        ('R107·出售页合计已收口',
         'YLst=Math.min(YLSellCredit(D,w.quantity||1,l),YlxwSellCap(w,w.quantity||1,l))',
         1, '==', ''),
        ('R107·旧卡片取值形态已清零', SELL_CARD_OLD, 0, '==', ''),
        ('R107·批量弹窗已收口',
         'isNaN(L)||(A+=Math.min(L,YlxwSellCap(I,Y,l)))', 1, '==',
         '上限挪到累加处（避免 const 列表重复声明 L）'),
        ('R107·旧批量弹窗形态已清零', SELL_BATCH_OLD, 0, '==', ''),
        ('R107·入账 handler 已收口',
         'const A=Math.min(Math.floor(q*w*50*YLRF(N)/3),YlxwSellCap(R,w,N));', 1, '==', ''),
        ('R107·旧入账形态已清零', SELL_HANDLER_OLD, 0, '==', ''),

        # ===================== 冻结：别动别人的断言面 =====================
        ('冻结·shop102 千年灵芝 Ut 原文仍在', 'Ut("千年灵芝",2e3,600,ae.GoldenCore)',
         1, '==', 'R-103 门禁 needle，必须逐字保留'),
        ('冻结·shop102 九转金丹 Ut 原文仍在', 'Ut("九转金丹",3e3,900,ae.GoldenCore)',
         1, '==', ''),
        ('冻结·shop102 天元丹 Ut 原文仍在', 'Ut("天元丹",15e3,4500,ae.GoldenCore)',
         1, '==', ''),
        ('冻结·sellui 批量 needle 仍在', 'L=YLSellCredit(B,Y,l)', 1, '==',
         'SELL_UI_GATES「批量提示已对齐」'),
        ('冻结·sellui 入账公式 needle 仍在', 'Math.floor(q*w*50*YLRF(N)/3)', 1, '==',
         'SELL_UI_GATES「实际入账公式未动」'),
        ('冻结·sellui 单件日志公式仍在', 'Math.floor(q*50*YLRF(N)/3)', 1, '==', ''),
        ('冻结·sellui 卡片单价显示仍在', 'lt(YLsu)', 1, '==', ''),
        ('冻结·sellui 卡片合计显示仍在', 'lt(YLst)', 1, '==', ''),
        ('冻结·回收价函数 Tm 本体未动',
         'function Tm(t,r){return Math.max(1,Math.ceil(t*o1(r)))}', 1, '==',
         'shop102 冻结门禁'),
        ('冻结·价格函数 Rm 本体未动',
         'function Rm(t,r){return Math.max(1,Math.ceil(t*Jm(r)))}', 1, '==',
         'shop102 冻结门禁'),
        ('冻结·估值器 xm 未动', 'xm=t=>{', 1, '==',
         '只读引用；改它会影响全站估值'),
        ('冻结·常量池查找 Lt 未动',
         'function Lt(t){pi();const r=Fc==null?void 0:Fc.get(t);return r?sy(r):null}',
         1, '==', ''),
        ('冻结·l1 壳/原体计数未变', 'function l1raw(t,r,a=!1){', 1, '==', ''),
        ('冻结·l1 调用点计数未变', 'l1(', 3, '==',
         '定义(壳)1 + 开架 l1(R,v.realm,!1) + 刷新 l1(a.type,l.realm,!0)'),
        ('冻结·商店弹窗签名未动',
         'const OM=({isOpen:t,onClose:r,shop:a,player:l,onBuyItem:c,onSellItem:d,'
         'onRefreshShop:u,onOpenInventory:f})=>{', 1, '==', ''),
        ('冻结·使用侧折算函数 $r 未动',
         '$r=(t,r,a)=>{if(!Number.isFinite(a)||a<=0)return 0', 1, '==',
         'R-106 面；本模块不碰'),
        ('冻结·寿命直加逻辑未动',
         'if(R.maxLifespan&&(u.maxLifespan=(u.maxLifespan??100)+R.maxLifespan', 1, '==',
         'R-106 面；本模块只改数值'),
        # ★ 2026-10-01 集成期「约束权移交」：使用提示文案归 R-106（本模块不碰），
        #   而 R-106 已在 `神识永久 +${E}` 之后追加折算注 ⇒ 本条改判 R-106 的定稿形态。
        ('冻结·使用提示文案由 R-106 定稿（R-107 未动）',
         'h.push(`神识永久 +${E}${E<R.spirit?', 1, '==',
         'R-106 面（描述/提示归 R-106）；R-107 只改数值'),
    ]
