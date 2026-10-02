# -*- coding: utf-8 -*-
r"""
yl_shoprefresh101_ext.py — R-101 历练商店刷新计费：每次进店首次免费，之后收灵石

⚠ 2026-10-01 集成期变更（R-108 接管）：用户台账 R-108 明确「后续之前默认是 2-8W，这个门槛不用改，
  把显示修复了就行」⇒ 本模块「之后固定 500 灵石」的取费与显示口径**已作废**，
  由 patches/client/yl_r108_ext.py 在装配链下游改写为「之后 = YlxwShopRefreshCost(shop) 分级价 2 万~8 万」，
  并清除 `YLXW_SR_PRICE` 常量。**本模块保留且仍然有效的部分 = 「每次进店第 1 次刷新免费、不弹确认框」。**
  下方「一~五」节的历史取证与设计叙述保留原样（作为改动沿革），仅 §三 的 500 灵石定价已失效。

需求原文（台账 R-101，用户 2026-10-01）
--------------------------------------------------------------------------
    「历练中遇到的商店，现在每次可以免费刷新一次，一次过后可以付费灵石刷新」

==============================================================================
一、改前行为取证（逐条读码，基线 build/assets/index-v298-20261001.js）
==============================================================================
① **商店弹窗里有「刷新」按钮，且本来就收费** —— 组件 `OM`（@1771029）的
   `titleExtra` 里渲染刷新按钮，@1774072：
       u&&e.jsxs("button",{onClick:()=>{
         const w=1e5;                                  // ← UI 写死 10 万
         if(l.spiritStones<w){Je(`灵石不足！刷新需要${w}灵石。`);return}
         an(`确定要花费 ${w} 灵石刷新商店物品吗？`,"确认刷新",()=>{
           const A=l1(a.type,l.realm,!0);u(A)})},        // ← 重新生成商品
         ... title:`花费${1e5}灵石刷新`, children:[..., ["(",1e5,")"]] })
   ⇒ **现状是「每次都收费」，没有免费次数**（既不是免费无限，也不是免费有限次）。
     用户说的「免费刷新一次」是**期望**的新行为，不是现状。

② 真正的扣费在父级 hook 里，不在按钮里 —— `ES`（@714117）：
       handleRefreshShop:O.useCallback(u=>{if(!l||!t)return;
         const f=YlxwShopRefreshCost(l);                       // ← 实际扣费额
         if(t.spiritStones<f){a(`灵石不足，无法刷新商店。需要${f}灵石。`,"danger");return}
         c({...l,items:u}),                                    // 落新货架
         r(v=>v&&{...v,spiritStones:v.spiritStones-f}),        // ← 扣 spiritStones（函数式）
         a("商店物品已刷新！","special")},[l,t,a,c,r])
   `YlxwShopRefreshCost`（@566086）读 `YLXW_SHOP_REFRESH`：村庄 20000 / 城市 40000 /
   仙门 60000 / 限时 60000 / 黑市 80000 / 声望 80000。
   ⚠ **既存缺陷**：按钮 UI 显示/校验写死 1e5（10 万），而实际只扣 2 万~8 万 ——
     显示与扣费不一致（0.8.5 经济补丁改了处理器、漏改按钮文案）。

③ 商品池/生成：`Bi`（@1764962）是 `ht.Village/City/Sect` 的静态商品表（`Ut(name,价,售价)`）；
   `l1(t,r,a=!1)`（@1767350）按商店类型 + 境界生成货架：黑市/限时/声望走随机池，
   村庄/城市/仙门走 `Bi[t]`。第三个参数 `a` 为真表示「刷新」（黑市等分支行为略不同）。

④ 入口唯一：全 bundle 只有历练组件 `nk`（@1850427）通过 `onOpenShop` → `FM.handleOpenShop`
   开商店（@1905725 接线，@1833905 定义）。**商店只在历练中开启**，
   所以商店弹窗 `OM` 就是「历练中遇到的商店」，无第二处商店入口。

⑤ 玩家灵石字段：`player.spiritStones`；扣款已有写法 `r(v=>v&&{...v,spiritStones:v.spiritStones-f})`。

==============================================================================
二、改后行为
==============================================================================
每个商店会话（弹窗 `IM`=memo(`OM`) 挂载一次）：
  第 1 次点「刷新」→ **免费**，不弹确认框，直接重新生成货架；
  第 2 次起每次 → 扣 `YLXW_SR_PRICE` 灵石（弹确认框，灵石不足则提示且**不刷新**）。
按钮文案随次数动态：首次显示「本次刷新免费 / (免费)」，之后显示「花费 500 灵石刷新 / (500)」。

实现（3 处就地替换，无新增文件、不动存档 schema）：
  patch ① `sr101-state`：在 `OM` 的 hooks 行追加 `[YLXW_SR_N,YLXW_SR_SET]=O.useState(0)`。
  patch ② `sr101-btn` ：刷新按钮 onClick 改为「首次 0 元、之后 YLXW_SR_PRICE」，
                        费用经 `u(A,w)` 透传给处理器；标题/角标改动态。
  patch ③ `sr101-es`  ：`handleRefreshShop` 增加可选第 2 参 `w`（本次费用）；
                        `w` 为合法数字时用它，否则回退 `YlxwShopRefreshCost(l)`；
                        仅当 `f>0` 才走 `setPlayer` 扣款。

==============================================================================
三、灵石价格（YLXW_SR_PRICE = 500）与理由
==============================================================================
定 **500 灵石 / 次**（单一常量，改常量即可调）。
  理由：商店单件商品价位 —— 村庄 10~50（止血草 10 / 凡铁剑 50）、城市 80~200
  （紫猴花 80 / 青钢剑 200），取 500 约等于「2~3 件高档商品」，有成本感又不肉疼；
  远低于旧价（20000~80000，是村庄单件的 400 倍），符合用户「别太贵」。
  不沿用 `YlxwShopRefreshCost` 的分级价（2 万~8 万）——那正是用户要改掉的「太贵」。

==============================================================================
四、状态存放位置
==============================================================================
计数 `YLXW_SR_N` 放在**商店弹窗组件 `OM` 内的 `useState(0)`**，不写进 `player`。
  · `OM` 由上层按 `isShopOpen && currentShop` **条件渲染**（@1832593），关店即卸载、
    再次进店即重挂载 ⇒ `useState` 自然归零 = 「每次进商店重置为 0」。
  · 刷新只是 `setCurrentShop({...l,items:u})` 换货架（不改组件类型）⇒ 计数在**同一次
    商店会话内累加**，不会因刷新而重置。
  · 全程不动 `player` 对象，**不触碰存档 schema**。

==============================================================================
五、风险点
==============================================================================
1. 本模块改动「所有商店」的首次刷新免费，而不仅是历练商店 —— 但取证 ④ 证明
   全 bundle 只有历练会开商店，故实际影响面 == 需求面（历练商店）。
2. `handleRefreshShop` 签名由 `(u)` 变 `(u,w)`：已确认全 bundle 仅按钮一处调用
   （`onRefreshShop:c.handleRefreshShop`），且保留 `YlxwShopRefreshCost(l)` 回退，
   旧调用不传 `w` 时行为不变。
3. 首次免费分支**不弹确认框**（直接刷新）——避免误触成本为零，且省去新增确认文案；
   付费分支仍保留原确认框与「灵石不足」提示，不会静默失败。
4. 组件卸载即归零：若将来上层改为「常挂载 + isOpen 切换」（不再条件渲染），
   计数将不再自动归零。当前基线为条件渲染，安全；已在门禁冻结 `OM` 签名与
   `isShopOpen` 渲染点做旁证。
5. 未改版本号、未动 `build_v26n.py`/CHANGELOG/EXPECT/deploy/srv。

锚点纪律：3 处锚点实测 count 均为 1；GATES 同时断言新形态存在与旧形态清零。
"""

# --------------------------------------------------------------------------- 注入块

# 注入位置：商店弹窗组件定义之前（模块作用域，早于 OM / ES 的运行时引用）
INJECT_BEFORE_ANCHOR = ('const OM=({isOpen:t,onClose:r,shop:a,player:l,onBuyItem:c,'
                        'onSellItem:d,onRefreshShop:u,onOpenInventory:f})=>{')
INJECT_BLOCK_ID = 'yl-shoprefresh101-block'

INJECT_JS = r'''
/* == YL_SHOP_REFRESH_101 == 历练商店刷新计费：每次进店首次刷新免费，之后收灵石 */
var YLXW_SR_PRICE = 500;
'''

# --------------------------------------------------------------------------- 锚点
# 实测 count（对基线 build/assets/index-v298-20261001.js，2,069,009 chars）：
#   HOOKS_OLD                                  = 1   （@1771035 OM hooks 行）
#   BTN_OLD                                    = 1   （@1773963 刷新按钮整块）
#   ES_OLD                                     = 1   （@714143 handleRefreshShop）
#   INJECT_BEFORE_ANCHOR                       = 1   （@1771029 OM 定义）
#   冻结字面 l1(a.type,l.realm,!0) / l1(R,v.realm,!1) / spiritStones:v.spiritStones-f
#            / c({...l,items:u}) / YlxwShopRefreshCost(l) 均 = 1

# ① 商店弹窗组件 OM 的 hooks 行：追加「本次会话刷新计数」state
HOOKS_OLD = ('const[v,m]=O.useState("buy"),[j,b]=O.useState({}),'
             '[S,x]=O.useState("all"),[T,$]=O.useState(new Set),'
             '[M,h]=O.useState("all");if(!t)return null;')
HOOKS_NEW = ('const[v,m]=O.useState("buy"),[j,b]=O.useState({}),'
             '[S,x]=O.useState("all"),[T,$]=O.useState(new Set),'
             '[M,h]=O.useState("all"),[YLXW_SR_N,YLXW_SR_SET]=O.useState(0);'
             'if(!t)return null;')

# ② 刷新按钮：首次免费、之后收费；费用透传给处理器；标题/角标动态
BTN_OLD = ('u&&e.jsxs("button",{onClick:()=>{const w=1e5;'
           'if(l.spiritStones<w){Je(`灵石不足！刷新需要${w}灵石。`);return}'
           'an(`确定要花费 ${w} 灵石刷新商店物品吗？`,"确认刷新",()=>{'
           'const A=l1(a.type,l.realm,!0);u(A)})},'
           'className:"flex items-center gap-1 px-2.5 py-1.5 bg-stone-700 '
           'hover:bg-stone-600 text-stone-200 rounded border border-stone-600 '
           'transition-colors text-xs md:text-sm",title:`花费${1e5}灵石刷新`,'
           'children:[e.jsx(Ta,{size:14,className:"md:w-4 md:h-4"}),'
           'e.jsx("span",{className:"hidden sm:inline",children:"刷新"}),'
           'e.jsxs("span",{className:"text-[10px] text-stone-400",'
           'children:["(",1e5,")"]})]})')

BTN_NEW = ('u&&e.jsxs("button",{onClick:()=>{'
           'const w=YLXW_SR_N<1?0:YLXW_SR_PRICE;'
           'if(w>0&&l.spiritStones<w){Je(`灵石不足！刷新需要${w}灵石。`);return}'
           'const YLXW_SR_DO=()=>{const A=l1(a.type,l.realm,!0);'
           'YLXW_SR_SET(n=>n+1);u(A,w)};'
           'w===0?YLXW_SR_DO():'
           'an(`确定要花费 ${w} 灵石刷新商店物品吗？`,"确认刷新",YLXW_SR_DO)},'
           'className:"flex items-center gap-1 px-2.5 py-1.5 bg-stone-700 '
           'hover:bg-stone-600 text-stone-200 rounded border border-stone-600 '
           'transition-colors text-xs md:text-sm",'
           'title:YLXW_SR_N<1?`本次刷新免费`:`花费${YLXW_SR_PRICE}灵石刷新`,'
           'children:[e.jsx(Ta,{size:14,className:"md:w-4 md:h-4"}),'
           'e.jsx("span",{className:"hidden sm:inline",children:"刷新"}),'
           'e.jsxs("span",{className:"text-[10px] text-stone-400",'
           'children:["(",YLXW_SR_N<1?"免费":YLXW_SR_PRICE,")"]})]})')

# ③ 刷新处理器：接受可选「本次费用」参数；f>0 才扣款
ES_OLD = ('handleRefreshShop:O.useCallback(u=>{if(!l||!t)return;'
          'const f=YlxwShopRefreshCost(l);'
          'if(t.spiritStones<f){a(`灵石不足，无法刷新商店。需要${f}灵石。`,"danger");return}'
          'c({...l,items:u}),'
          'r(v=>v&&{...v,spiritStones:v.spiritStones-f}),'
          'a("商店物品已刷新！","special")},[l,t,a,c,r])')

ES_NEW = ('handleRefreshShop:O.useCallback((u,w)=>{if(!l||!t)return;'
          'const f=(typeof w==="number"&&isFinite(w)&&w>=0)?Math.floor(w):YlxwShopRefreshCost(l);'
          'if(t.spiritStones<f){a(`灵石不足，无法刷新商店。需要${f}灵石。`,"danger");return}'
          'c({...l,items:u}),'
          'f>0&&r(v=>v&&{...v,spiritStones:v.spiritStones-f}),'
          'a("商店物品已刷新！","special")},[l,t,a,c,r])')


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    # ① 计数 state（组件内，随商店弹窗挂载归零；不动 player/schema）
    p.replace('sr101-state', HOOKS_OLD, HOOKS_NEW, expect=1,
              note='OM 内加 [YLXW_SR_N,YLXW_SR_SET]=useState(0) 作为本会话刷新计数')

    # ② 刷新按钮：首次免费 / 之后 YLXW_SR_PRICE；费用透传 u(A,w)
    p.replace('sr101-btn', BTN_OLD, BTN_NEW, expect=1,
              note='刷新按钮：去掉写死的 1e5，改首次免费、之后收 YLXW_SR_PRICE')

    # ③ 刷新处理器：接受可选费用参数，f>0 才走 setPlayer 扣款
    p.replace('sr101-es', ES_OLD, ES_NEW, expect=1,
              note='handleRefreshShop 增可选第 2 参 w（本次费用）；无参回退原分级价')

    return [
        # ================= 新形态（==1） =================
        ('R101·刷新计数 state 已加',  '[YLXW_SR_N,YLXW_SR_SET]=O.useState(0)', 1, '==',
         '组件内 state，商店弹窗重挂载即归零'),
        # ★ 2026-10-01 集成期「约束权移交」：用户台账 R-108（「后续之前默认是 2-8W，这个门槛不用改，
        #   把显示修复了就行」）推翻了本条原定的「之后一律 500 灵石」。取费形态与显示口径由
        #   patches/client/yl_r108_ext.py 接管 ⇒ 本条 needle 改判 R-108 的定稿形态。
        #   （R-101 的正确部分——「每次进店第 1 次免费」——由下方「冻结」组继续守着。）
        ('R101·首次免费判定（取费形态已移交 R-108）',
         'YLXW_SR_N<1?0:YlxwShopRefreshCost(a)',           1, '==',
         '第 1 次 w=0（免费）；之后 = 本商店分级价 2 万~8 万（R-108 恢复）'),
        ('R101·计数自增',            'YLXW_SR_SET(n=>n+1)',                   1, '==',
         '每次刷新 +1'),
        ('R101·费用透传给处理器',    'u(A,w)',                                 1, '==',
         '把本次费用交给 handleRefreshShop'),
        ('R101·免费分支不弹确认',    'w===0?YLXW_SR_DO():',                   1, '==',
         '免费直接刷新；付费才弹确认框'),
        ('R101·处理器已收费用参数',  'handleRefreshShop:O.useCallback((u,w)=>{', 1, '==',
         ''),
        ('R101·固定价常量已由 R-108 废弃', 'YLXW_SR_PRICE',                     0, '==',
         'R-108 恢复分级价后该常量定义 + 3 处引用已全部清除'),

        # ================= 旧形态（==0） =================
        ('R101·旧写死 1e5 已清零',   'const w=1e5;',                           0, '==',
         '旧「每次都收 10 万」必须消失'),
        ('R101·旧标题文案已清零',    '花费${1e5}灵石刷新',                     0, '==', ''),
        ('R101·旧处理器签名已清零',  'handleRefreshShop:O.useCallback(u=>{',   0, '==', ''),

        # ================= 冻结（别动别人的面） =================
        ('冻结·刷新沿用原生成逻辑',  'l1(a.type,l.realm,!0)',                   1, '==',
         '商品重新生成仍走 l1(...,!0)，未自造一套'),
        ('冻结·开架生成未动',        'l1(R,v.realm,!1)',                       1, '==',
         'handleOpenShop 初始货架生成未动'),
        ('冻结·灵石扣款写入未动',    'spiritStones:v.spiritStones-f',          1, '==',
         'spiritStones 相关既有扣款写法计数未变'),
        ('冻结·扣款走 setPlayer 函数式更新',
         'r(v=>v&&{...v,spiritStones:v.spiritStones-f})',                    1, '==', ''),
        ('冻结·无费用时回退原分级价', 'YlxwShopRefreshCost(l)',                 1, '==',
         '旧调用不传 w 时行为不变'),
        ('冻结·货架落库写法未动',    'c({...l,items:u})',                      1, '==', ''),
        ('冻结·商店弹窗签名未动',    INJECT_BEFORE_ANCHOR,                     1, '==',
         'OM props 未动，isShopOpen 条件渲染点因此保持有效'),
    ]
