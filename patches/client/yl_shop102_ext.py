# -*- coding: utf-8 -*-
r"""
yl_shop102_ext.py — 历练商店三修：名字后的「0」/ 阶位越级与错误标签 / 杂货铺无库存

台账 R-102 / R-103 / R-104（用户 2026-10-01）
--------------------------------------------------------------------------
  R-102「历练遇到的商店，售卖时候物品名字后面的加了 0 是什么意思？」
  R-103「历练商店中遇到了不属于该等阶的装备，右下角还显示了错误的练气期，
         彻底修复这个问题，商店只会出同等阶或者低级的装备，不会出现高的。
         并且售价也要（调整）。」
  R-104「遇到的杂货铺，没有购买库存限制。」

基线：build/assets/index-v299-20261001.js（2,075,818 chars，已含 shoprefresh101）
**不碰 yl_shoprefresh101_ext.py 的任何锚点**（它锚 OM hooks 行 / 刷新按钮 / handleRefreshShop，
本模块锚的是 出售卡片 / l1 函数头 / 静态开店分支 / 两处价格计算）。

==============================================================================
一、改前取证（逐条读码，全部在 index-v299-20261001.js 内实测）
==============================================================================

【R-102】那个「0」到底是什么 —— **是 React 把数字 0 当成文本渲染出来了**
--------------------------------------------------------------------------
商店弹窗 `OM`（@1777573）的**出售页**物品卡片，标题行 @1791842：
    e.jsxs("h4",{className:`font-bold ${_t(Q)}`,
      children:[w.name,
        w.level&&w.level>0&&e.jsxs("span",{className:"text-xs text-stone-500 ml-1",
                                    children:["+",w.level]})]})
守卫写成 `w.level && w.level>0 && X`：
  · `w.level===0` 时短路求值结果是**数字 0**（不是 false/undefined）；
  · React 对 `false/null/undefined/""` 不渲染，但**对数字 0 会渲染成文本 "0"**；
  ⇒ 于是 `[w.name, 0]` 渲染成「凡铁剑0」「布衣0」。
「0」从哪来：物品库里有大量 `level:0` 的装备，例如
  @294462 `凡铁剑{...rarity:"普通",level:0,realmRequirement:ae.QiRefining,...}`
  @294694 `摸鱼宗外门弟子制式道袍{...level:0,...}`
  @332204 生成装备 `{name:"["+rl+"]"+nm,...,level:0,...}`
所以它不是价格后缀、不是数量、不是等级，**是拼接 bug（多余的一次 `w.level&&`）**。
（购买页的标题是纯 `children:w.name`，@1783333 起，无此问题；全 bundle `w.level` 仅 4 处，
 只有这一处是「名字 + level」拼接，count 实测 1。）

【R-103】商品怎么按境界生成 + 为什么右下角是错的「炼气期」
--------------------------------------------------------------------------
① 生成函数 `l1(t,r,a=!1)`（@1773757）：t=商店类型、r=玩家境界串、a=是否刷新。
   `const l=fe.indexOf(r)` 即玩家境界序（fe 是 7 阶境界表 @244726：
   炼气/筑基/金丹/元婴/化神/合道/长生境）。
   各分支的**唯一**阶位过滤都是「只看 item.minRealm」：
     · 黑市   `(!x.minRealm||l>=fe.indexOf(x.minRealm))&&c.push(...)`
     · 限时/声望 `(!T.minRealm||l>=fe.indexOf(T.minRealm))&&c.push(...)`
     · 村庄/城市/仙门（静态池 Bi）
              `if(S.minRealm){const x=fe.indexOf(S.minRealm);if(l<x)continue}`
     · 刷新时的 10% 高级货 `if(a&&Math.random()<.1&&Ea.length>0){...(!j.minRealm||l>=fe.indexOf(j.minRealm))&&c.push(...)}`
② 但高级货池 `Ea`（@1771923）里几个**高品阶物品的 minRealm 是错的 / 干脆没有**：
     Ut("千年灵芝",2e3,600)          ← 稀有度「传说」草药（AN @301570），**无 minRealm**
     Ut("九转金丹",3e3,900)          ← 稀有度「仙品」丹药（@295870），**无 minRealm**
     Ut("天元丹",15e3,4500)          ← 稀有度「仙品」丹药（@298544），**无 minRealm**
     {name:"村里最好的剑",...rarity:"仙品",price:9999990,effect:{attack:1e5,...},
      realmRequirement:ae.SpiritSevering,...,minRealm:ae.QiRefining}
                                     ← 仙品武器，realmRequirement 写「化神期」，
                                        minRealm 却写「炼气期」（自相矛盾）
   ⇒ 过滤条件 `!j.minRealm` 对前三者恒真；`村里最好的剑` 的 minRealm=炼气期 ⇒ 对炼气玩家也放行。
     于是**炼气期玩家在村庄/城市杂货铺刷新时能刷到仙品物品**。
③ 卡片右下角直接渲染 `w.minRealm`（@1786914 `["境界: ",w.minRealm]`，`self-end` 即右下；
   上方 @1786250 还有一处 `["境界要求: ",w.minRealm]`）。
   ⇒ 标签就是池子里那个字段，**池子写错，标签就错**；`村里最好的剑` 因此显示
     「境界: 炼气期」——正是用户看到的「不属于该等阶的装备 + 错误的练气期」。
④ 售价：卡片 `const A=Rm(w.price,l)`（@1783333）、购买处理器 `const _=Rm(R.price,N)*E`
   （@1841131）。`Rm(t,r)=Math.max(1,Math.ceil(t*Jm(r)))`（@1777192），
   `Jm(player)` = 按**玩家**境界/小境界的物价倍率（@1777040）。
   ⇒ 售价只跟玩家境界走，与商品自身阶位无关：高境界玩家在杂货铺买低阶货会被按高境界加价。

【R-104】购买 handler 在哪 + 为什么杂货铺无限买
--------------------------------------------------------------------------
① 购买处理器 `handleBuyItem:(R,E=1)=>{m(N=>{...})}`（@1840956，位于 `handleOpenShop`
   同一个 hook 返回对象里）。它**本来就有库存校验**：
     `if(R.stock!=null){ if(R.stock<=0)return j("该商品已售罄！",...),N;
                        if(E>R.stock)return j(`库存不足！${R.name} 仅剩 ${R.stock} 件。`,...),N }`
   并在成交后**扣减货架库存**（两处同形）：
     `(()=>{if(R.stock!=null){S({...c,items:c.items.map(P=>P.id===R.id?{...P,stock:Math.max(0,(P.stock??0)-E)}:P)})}})()`
   UI 侧同样已接线：卡片 `w.stock!=null&&<div>库存: {w.stock}</div>`、
   `I=R(w)&&(w.stock==null||w.stock>0)` 控制按钮可用、`+` 号上限 `Math.min(w.stock??9999,...)`。
② 缺口在**静态商店**：`handleOpenShop`（@1840714）只在
   `[ht.BlackMarket,ht.LimitedTime,ht.Reputation]` 三个动态商店里走 `l1(...)`，
   这三个的货架经 `_ylStockFn` 自动带上 stock；
   而 村庄/城市/仙门 走 `else S(E)` —— 直接引用常量表 `T3`（@464734）里的原始条目，
   T3 条目**没有 stock 字段**（如 `{id:"shop-herb-1",name:"止血草",...,price:100,...}`）
   ⇒ `R.stock==null` ⇒ handler 的三条库存分支全部跳过 ⇒ **同一件可以无限买**。
   这就是用户说的「杂货铺没有购买库存限制」（村庄杂货铺 = T3[0]，name:"村庄杂货铺"）。

==============================================================================
二、改后行为
==============================================================================

【R-102】`w.level&&w.level>0&&` → `w.level>0&&`。
   level===0（未强化装备）→ `0>0` 为 false → React 不渲染 → 名字后面不再有 0；
   level>0 → 仍渲染「+N」；level 缺失 → `undefined>0` 为 false → 同样不渲染。零副作用。

【R-103】(a) 修正 `Ea` 池里 4 处阶位元数据（只改数据，不动随机与品质分布）：
       千年灵芝/九转金丹/天元丹 补 `ae.GoldenCore`；`村里最好的剑` 的 minRealm
       由「炼气期」改为与其 realmRequirement 一致的 `ae.SpiritSevering`（化神期）。
     (b) 在 `l1` 出口加**统一阶位闸门**（把 `l1` 拆成 `l1`(壳) + `l1raw`(原体)）：
       阶位 `YlxwShopItemTier(it)` = max( index(minRealm), index(realmRequirement),
                                        装备按稀有度兜底：传说→筑基、仙品→金丹 )
       闸门 `YlxwShopRealmGate(items, realm)` **只保留 tier <= 玩家境界序** 的商品，
       并把保留商品的 `minRealm` 规范化为其真实阶位名（右下角标签不再撒谎）。
       ★ 只做「过滤 + 标签纠正」，**不打乱任何随机/权重/品质分布**：
         普通/稀有的非装备物品 tier 仍为 -1（不拦），所以 `Bi[仙门]` 的筑基丹
         （稀有度「传说」但无 minRealm/realmRequirement，本属炼气期可买）**不受影响**。
     (c) 同一闸门也接到静态商店 `else S(E)` → `S({...E,items:YlxwShopRealmGate(E.items,v.realm)})`，
       让「村庄/城市/仙门」的初始货架同样只出同等阶或更低（仙门宝库对炼气玩家只剩筑基丹）。
     (d) 售价调整：卡片与购买处理器统一改用
       `YlxwShopPriceOf(it,player)=ceil(Rm(it.price,player) * YLXW_SHOP_TIER_DOWN^gap)`，
       `gap = clamp(玩家境界序 - 商品阶位, 0, 3)`；
       **同阶（gap=0）与「无阶位信息」（阶位=-1，多为丹药/材料/草药）都保持原价不动**。
       ⇒ 高境界玩家在低阶**装备**上不再被按高境界倍率加价
         （低一阶 ×0.6、二阶 ×0.36、≥三阶 ×0.216）。
       卡片显示价与处理器实扣价用**同一个函数**，不会出现「显示价 ≠ 扣费价」。
       折扣刻意只作用于「有明确阶位元数据」的商品，避免一次性改动全店物价。

【R-104】`handleOpenShop` 入口把 T3 条目复制一遍并过 `_ylStockFn`：
       `const E0=T3.find(...), E=E0?{...E0,items:E0.items.map(it=>_ylStockFn(it))}:E0;`
     复用**既有**的 `_ylStockFn`（@1773674，动态商店在用）与**既有**的 stock 全链路
     （UI 显示 / 数量上限 / 按钮禁用 / handler 校验 / 成交扣减），静态杂货铺一次性补齐。
     不改 `T3` 常量本身、不动 `player` 对象、不碰存档 schema。
     `R.stock!=null` 成立后，`handleBuyItem` 原有的三条分支自动生效，**无需改 handler**。

==============================================================================
三、库存上限取值与理由
==============================================================================
沿用项目既有约定（`_ylStockFn`）：**普通 6 / 稀有 4 / 传说 2 / 仙品 1**。
理由：
  1) **一致性**：黑市/限时/声望三个动态商店早已按这套映射发库存，静态杂货铺沿用后
     玩家不需要学第二套规则，也不会出现「同一个止血草在两处限购不同」的割裂感。
  2) **够用不卡手**：杂货铺主力是普通货（止血草 10 灵石、炼器石 15、聚气丹 30、木剑 500），
     6 件足够一次买齐日常消耗；而高稀有度（仙品 1 件）天然限量。
  3) **防倒卖套利**：售价倍率 `Rm` 与回收价 `Tm` 之间的价差在高稀有度上更大，
     限量 2/1 可避免「刷出仙品 → 全买 → 转卖」的套利。
  4) 每进一次商店重置（`handleOpenShop` 重新生成货架），与动态商店语义一致。

==============================================================================
四、风险点
==============================================================================
1. **闸门是「过滤」而非「降级」**：被判定越级的商品直接从货架消失，不降级保留。
   这与用户「只会出同等阶或者低级的，不会出现高的」一致，但会让**仙门宝库在炼气期
   只剩筑基丹**（其余 传说/仙品 合成石与装备被滤掉）。已用「装备才做稀有度兜底」把
   非装备的高稀有度消耗品（如筑基丹）排除在推断之外，避免误伤炼气期必需品。
2. **售价折扣是新引入的经济面**：`YLXW_SHOP_TIER_DOWN=0.6`、最多累计 3 阶，改常量即可调。
   只影响「商品阶位 < 玩家境界」的成交价（同阶/高阶不受影响），且**只改售价不改回收价**
   （`Tm`/`YLSellCredit` 一行未动），所以不会造成「低价买高价卖」的套利。
3. **标签规范化会改写商品对象的 minRealm**：只发生在 `l1`/静态货架的**货架副本**上
   （`{...it, minRealm: fe[t]}`），不污染 `Bi/Ea/Em/T3` 常量池。
4. **闸门对 `l1` 的所有出口生效**：`l1` 内部有 5 处 `return c`（黑市空池早退 + 三个动态
   分支 + 静态池），拆成壳/体后由壳统一收口，无遗漏；`l1` 的名字与签名不变，
   shoprefresh101 的冻结断言（`l1(a.type,l.realm,!0)` / `l1(R,v.realm,!1)`）继续成立。
5. **R-102 只修了商店出售页这一处**：全 bundle `w.level` 仅 4 处，另外 3 处（角色/背包装备
   列表等）用法不同、不在本次需求范围；若将来发现同类「数字 0 被渲染」的写法，
   根因相同（`x && x>0 && ...`），修法相同。
6. **未持久化**：库存只活在 `currentShop`（本次商店会话），关店即丢；未改 player / 存档 schema。
7. 未改版本号、未动 `build_v26n.py`/CHANGELOG/EXPECT/deploy_v28/srv，未改任何其他模块文件。

锚点纪律：11 处 replace 锚点实测 count 均为 1；GATES 同时断言新形态存在与旧形态清零。
"""

# --------------------------------------------------------------------------- 注入块
# 注入位置：`_ylStockFn` 定义之前（模块作用域，早于 l1 / handleOpenShop 的运行时调用）。
# ⚠ INJECT_JS 由 build 侧 zh() 转义后落盘，必须避免 V28_BAN_PATTERNS
#   ('iframe' / 'postMessage' / 'XMLHttpRequest' / 'auth_token' / 'X-YL-')。
INJECT_BEFORE_ANCHOR = 'const _ylStockFn=t=>({...t,stock:t.stock??'
INJECT_BLOCK_ID = 'yl-shop102-block'

INJECT_JS = r'''
/* == YL_SHOP_102 == 历练商店 R-102/103/104：阶位闸门 + 阶位售价 + 库存 */
var YLXW_SHOP_TIER_DOWN = 0.6;   /* 每低一阶的售价折扣（同阶不折） */
var YLXW_SHOP_TIER_MAXGAP = 3;   /* 折扣最多累计阶数 */
/* 商品真实阶位序：优先 minRealm，其次 realmRequirement，装备再按稀有度兜底。
   返回 -1 表示「无阶位信息」= 不参与闸门（如丹药/材料/草药）。 */
function YlxwShopItemTier(it) {
  if (!it) return -1;
  var t = -1, a, b;
  if (it.minRealm != null) { a = fe.indexOf(it.minRealm); if (a > t) t = a; }
  if (it.realmRequirement != null) { b = fe.indexOf(it.realmRequirement); if (b > t) t = b; }
  if (it.isEquippable && it.rarity != null) {
    var r = ({ "传说": 1, "仙品": 2 })[it.rarity];
    if (r != null && r > t) t = r;
  }
  return t;
}
/* 只保留「同等阶或更低」的商品，并把 minRealm 纠正为真实阶位名（右下角标签不再撒谎） */
function YlxwShopRealmGate(items, realm) {
  if (!items) return items;
  var p = fe.indexOf(realm);
  if (p < 0) return items;
  var out = [];
  for (var i = 0; i < items.length; i++) {
    var it = items[i], t = YlxwShopItemTier(it);
    if (t < 0) { out.push(it); continue; }
    if (t <= p) out.push({ ...it, minRealm: fe[t] });
  }
  return out;
}
/* 玩家境界序 - 商品阶位，钳到 [0, YLXW_SHOP_TIER_MAXGAP]。
   返回 0 = 不打折：同阶商品，以及阶位未知(-1)的丹药/材料/草药。 */
function YlxwShopTierGap(it, player) {
  var p = player ? fe.indexOf(player.realm) : -1;
  var t = YlxwShopItemTier(it);
  if (p < 0 || t < 0) return 0;
  var g = p - t;
  if (g < 0) g = 0;
  if (g > YLXW_SHOP_TIER_MAXGAP) g = YLXW_SHOP_TIER_MAXGAP;
  return g;
}
/* 售价：在原境界倍率价上，按「商品比玩家低几阶」打折 */
function YlxwShopPriceOf(it, player) {
  var base = Rm(it.price, player), g = YlxwShopTierGap(it, player);
  if (g <= 0) return base;
  return Math.max(1, Math.ceil(base * Math.pow(YLXW_SHOP_TIER_DOWN, g)));
}
'''

# --------------------------------------------------------------------------- 锚点
# 实测 count（基线 build/assets/index-v299-20261001.js，2,075,818 chars）：
#   SELL_H4_OLD            = 1   （@1791842 出售卡片标题行）
#   EA_LINGZHI / EA_JZD / EA_TYD / EA_VILLAGE = 1 / 1 / 1 / 1（@1771923 Ea 池）
#   L1_HEAD_OLD            = 1   （@1773757 l1 函数头）
#   STATIC_SHELF_OLD       = 1   （@1840714 else S(E);）
#   CARD_PRICE_OLD         = 1   （@1783333 卡片价格）
#   BUY_PRICE_OLD          = 1   （@1841131 购买扣费）
#   OPEN_HEAD_OLD          = 1   （@1840714 handleOpenShop 头）
#   INJECT_BEFORE_ANCHOR   = 1   （@1773674 _ylStockFn 定义）
#   冻结面：l1( =3、l1(a.type,l.realm,!0)=1、l1(R,v.realm,!1)=1、
#          spiritStones:v.spiritStones-f=1、YlxwShopRefreshCost(l)=1、c({...l,items:u})=1、
#          既有 _ylStockFn 定义=1、YlxwInhStock(it,v)=1、
#          function Rm(t,r){...}=1、l.spiritStones<Rm(w.price,l)=1、
#          OM 签名=1、const T3=[{id:"shop-village"=1  —— 均实测

# ===== R-102：出售卡片标题行，去掉多余的 w.level&&（level===0 会被 React 渲染成 "0"） =====
SELL_H4_OLD = ('children:[w.name,w.level&&w.level>0&&e.jsxs("span",'
               '{className:"text-xs text-stone-500 ml-1",children:["+",w.level]})]')
SELL_H4_NEW = ('children:[w.name,w.level>0&&e.jsxs("span",'
               '{className:"text-xs text-stone-500 ml-1",children:["+",w.level]})]')

# ===== R-103(a)：修正 Ea 高级货池里 4 处错误/缺失的阶位元数据 =====
EA_LINGZHI_OLD = 'Ut("千年灵芝",2e3,600)'
EA_LINGZHI_NEW = 'Ut("千年灵芝",2e3,600,ae.GoldenCore)'
EA_JZD_OLD = 'Ut("九转金丹",3e3,900)'
EA_JZD_NEW = 'Ut("九转金丹",3e3,900,ae.GoldenCore)'
EA_TYD_OLD = 'Ut("天元丹",15e3,4500)'
EA_TYD_NEW = 'Ut("天元丹",15e3,4500,ae.GoldenCore)'
EA_VILLAGE_OLD = 'reviveChances:5,minRealm:ae.QiRefining}'
EA_VILLAGE_NEW = 'reviveChances:5,minRealm:ae.SpiritSevering}'

# ===== R-103(b)：l1 拆成 壳(l1) + 原体(l1raw)，出口统一过阶位闸门 =====
L1_HEAD_OLD = 'function l1(t,r,a=!1){const l=fe.indexOf(r),c=[],d=new Set;'
L1_HEAD_NEW = ('function l1(t,r,a=!1){return YlxwShopRealmGate(l1raw(t,r,a),r)}'
               'function l1raw(t,r,a=!1){const l=fe.indexOf(r),c=[],d=new Set;')

# ===== R-103(c)：静态商店（村庄/城市/仙门）初始货架同样过闸门 =====
STATIC_SHELF_OLD = 'else S(E);'
STATIC_SHELF_NEW = 'else S({...E,items:YlxwShopRealmGate(E.items,v.realm)});'

# ===== R-103(d)：售价改走阶位函数（卡片显示价 == 处理器实扣价） =====
CARD_PRICE_OLD = 'const A=Rm(w.price,l),I=R(w)&&(w.stock==null||w.stock>0);'
CARD_PRICE_NEW = 'const A=YlxwShopPriceOf(w,l),I=R(w)&&(w.stock==null||w.stock>0);'
BUY_PRICE_OLD = 'const _=Rm(R.price,N)*E;'
BUY_PRICE_NEW = 'const _=YlxwShopPriceOf(R,N)*E;'

# ===== R-104：静态商店（T3 表）货架过既有 _ylStockFn，补上库存 =====
OPEN_HEAD_OLD = 'handleOpenShop:R=>{const E=T3.find(N=>N.type===R);if(E){'
OPEN_HEAD_NEW = ('handleOpenShop:R=>{const E0=T3.find(N=>N.type===R),'
                 'E=E0?{...E0,items:E0.items.map(it=>_ylStockFn(it))}:E0;if(E){')


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    # ---------- R-102 ----------
    p.replace('r102-sell-level', SELL_H4_OLD, SELL_H4_NEW, expect=1,
              note='出售卡片：w.level&&w.level>0&& → w.level>0&&（level===0 不再渲染出 "0"）')

    # ---------- R-103(a) 数据修正 ----------
    p.replace('r103-ea-lingzhi', EA_LINGZHI_OLD, EA_LINGZHI_NEW, expect=1,
              note='千年灵芝（传说草药）补 minRealm=金丹期')
    p.replace('r103-ea-jzd', EA_JZD_OLD, EA_JZD_NEW, expect=1,
              note='九转金丹（仙品丹药）补 minRealm=金丹期')
    p.replace('r103-ea-tyd', EA_TYD_OLD, EA_TYD_NEW, expect=1,
              note='天元丹（仙品丹药）补 minRealm=金丹期')
    p.replace('r103-ea-village', EA_VILLAGE_OLD, EA_VILLAGE_NEW, expect=1,
              note='村里最好的剑（仙品武器）minRealm 炼气期→化神期，与其 realmRequirement 对齐')

    # ---------- R-103(b) l1 出口闸门 ----------
    p.replace('r103-l1-gate', L1_HEAD_OLD, L1_HEAD_NEW, expect=1,
              note='l1 拆壳：出口统一过 YlxwShopRealmGate（只出同等阶或更低 + 纠正标签）')

    # ---------- R-103(c) 静态货架闸门 ----------
    p.replace('r103-static-gate', STATIC_SHELF_OLD, STATIC_SHELF_NEW, expect=1,
              note='静态商店初始货架也过闸门')

    # ---------- R-103(d) 售价 ----------
    p.replace('r103-price-card', CARD_PRICE_OLD, CARD_PRICE_NEW, expect=1,
              note='卡片价格 → YlxwShopPriceOf（按商品阶位打折）')
    p.replace('r103-price-buy', BUY_PRICE_OLD, BUY_PRICE_NEW, expect=1,
              note='购买扣费 → YlxwShopPriceOf（与卡片同函数，显示价==实扣价）')

    # ---------- R-104 库存 ----------
    p.replace('r104-static-stock', OPEN_HEAD_OLD, OPEN_HEAD_NEW, expect=1,
              note='handleOpenShop 入口把 T3 条目过 _ylStockFn，静态杂货铺补齐库存')

    return [
        # ===================== R-102 =====================
        ('R102·旧 level 守卫已清零', 'children:[w.name,w.level&&w.level>0&&', 0, '==',
         'level===0 时 `0&&x` 求值为数字 0，React 会渲染成文本 "0"'),
        ('R102·新 level 守卫已生效', 'children:[w.name,w.level>0&&', 1, '==',
         'level>0 才渲染 +N；level 缺失/为 0 一律不渲染'),

        # ===================== R-103(a) 池数据 =====================
        ('R103·千年灵芝阶位已补', EA_LINGZHI_NEW, 1, '==', '传说草药 → 金丹期'),
        ('R103·九转金丹阶位已补', EA_JZD_NEW, 1, '==', '仙品丹药 → 金丹期'),
        ('R103·天元丹阶位已补', EA_TYD_NEW, 1, '==', '仙品丹药 → 金丹期'),
        ('R103·村里最好的剑阶位已修正', EA_VILLAGE_NEW, 1, '==',
         '仙品武器 minRealm 炼气期→化神期（与 realmRequirement 一致）'),
        ('R103·旧村里最好的剑阶位已清零', EA_VILLAGE_OLD, 0, '==', ''),
        ('R103·旧千年灵芝形态已清零', EA_LINGZHI_OLD, 0, '==', ''),
        ('R103·旧九转金丹形态已清零', EA_JZD_OLD, 0, '==', ''),
        ('R103·旧天元丹形态已清零', EA_TYD_OLD, 0, '==', ''),

        # ===================== R-103(b)(c) 闸门 =====================
        ('R103·l1 出口闸门已接', 'function l1(t,r,a=!1){return YlxwShopRealmGate(l1raw(t,r,a),r)}',
         1, '==', 'l1 名字/签名不变，内部转 l1raw 后统一收口'),
        ('R103·l1raw 原体已就位', 'function l1raw(t,r,a=!1){const l=fe.indexOf(r),c=[],d=new Set;',
         1, '==', ''),
        ('R103·旧 l1 函数头已清零', L1_HEAD_OLD, 0, '==', ''),
        ('R103·静态货架已过闸门', 'else S({...E,items:YlxwShopRealmGate(E.items,v.realm)});',
         1, '==', '村庄/城市/仙门 初始货架同样只出同等阶或更低'),
        ('R103·旧静态货架已清零', STATIC_SHELF_OLD, 0, '==', ''),
        ('R103·闸门函数已注入', 'function YlxwShopRealmGate(items, realm) {', 1, '==', ''),
        ('R103·阶位判定已注入', 'function YlxwShopItemTier(it) {', 1, '==',
         'minRealm > realmRequirement > 装备稀有度兜底；-1 表示无阶位信息不拦'),

        # ===================== R-103(d) 售价 =====================
        ('R103·卡片价格已走阶位函数', 'const A=YlxwShopPriceOf(w,l),', 1, '==', ''),
        ('R103·购买扣费已走阶位函数', 'const _=YlxwShopPriceOf(R,N)*E;', 1, '==',
         '与卡片同一函数，显示价 == 实扣价'),
        ('R103·旧卡片价格已清零', CARD_PRICE_OLD, 0, '==', ''),
        ('R103·旧扣费形态已清零', BUY_PRICE_OLD, 0, '==', ''),
        ('R103·折扣常量已注入', 'var YLXW_SHOP_TIER_DOWN = 0.6;', 1, '==',
         '每低一阶 ×0.6，最多累计 3 阶；同阶 gap=0 与原价完全一致'),

        # ===================== R-104 =====================
        ('R104·静态商店已上库存', OPEN_HEAD_NEW, 1, '==',
         'T3 条目过既有 _ylStockFn：普通6/稀有4/传说2/仙品1'),
        ('R104·旧开店头已清零', OPEN_HEAD_OLD, 0, '==', ''),
        ('R104·库存仍走既有 stock 链路', 'if(R.stock!=null){if(R.stock<=0)return j("该商品已售罄！","danger"),N;',
         1, '==', 'handler 原有库存校验未动，补齐 stock 后自动生效'),
        ('R104·库存扣减仍在', 'stock:Math.max(0,(P.stock??0)-E)', 2, '==',
         '成交后扣减货架库存（高级物品分支 + 普通分支，各 1 处）'),

        # ===================== 冻结（别动别人的面） =====================
        ('冻结·l1 调用点计数未变', 'l1(', 3, '==',
         '定义(壳)1 + 开架 l1(R,v.realm,!1) + 刷新 l1(a.type,l.realm,!0)'),
        ('冻结·刷新仍走 l1', 'l1(a.type,l.realm,!0)', 1, '==', 'shoprefresh101 冻结面'),
        ('冻结·开架仍走 l1', 'l1(R,v.realm,!1)', 1, '==', 'shoprefresh101 冻结面'),
        ('冻结·灵石扣款写入未动', 'spiritStones:v.spiritStones-f', 1, '==',
         'spiritStones 相关既有扣款写法计数未变'),
        ('冻结·刷新扣费回退未动', 'YlxwShopRefreshCost(l)', 1, '==', 'shoprefresh101 冻结面'),
        ('冻结·货架落库写法未动', 'c({...l,items:u})', 1, '==', 'shoprefresh101 冻结面'),
        ('冻结·既有库存函数未动',
         'const _ylStockFn=t=>({...t,stock:t.stock??({"普通":6,"稀有":4,"传说":2,"仙品":1}[t.rarity]??6)});',
         1, '==', 'R-104 复用它，不改它'),
        ('冻结·继承石库存钩子未动', 'YlxwInhStock(it,v)', 1, '==', ''),
        ('冻结·价格函数本体未动', 'function Rm(t,r){return Math.max(1,Math.ceil(t*Jm(r)))}',
         1, '==', '只在外面套阶位折扣，Rm 本身未动'),
        ('冻结·可购判定未动', 'l.spiritStones<Rm(w.price,l)', 1, '==',
         '卡片可购判定（用原价）未动，扣费侧由同一函数保证一致'),
        ('冻结·回收价函数未动', 'function Tm(t,r){return Math.max(1,Math.ceil(t*o1(r)))}',
         1, '==', '售价改了、回收价一行未动，不产生套利'),
        ('冻结·商店弹窗签名未动',
         'const OM=({isOpen:t,onClose:r,shop:a,player:l,onBuyItem:c,onSellItem:d,'
         'onRefreshShop:u,onOpenInventory:f})=>{', 1, '==', 'OM props 未动'),
        ('冻结·静态商店常量表未动', 'const T3=[{id:"shop-village"', 1, '==',
         'T3 原表未改，只在开店时复制一份上库存'),
    ]
