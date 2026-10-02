# -*- coding: utf-8 -*-
r"""
yl_r108_ext.py — R-108 历练商店刷新的「显示」修复 + 门槛恢复原值

需求原文（台账 R-108，用户 2026-10-01，逐字）
--------------------------------------------------------------------------
    「R101商店刷新，第一次免费，后续之前默认是2-8W，这个门槛不用改。
      把显示修复了就行」

==============================================================================
一、改前行为取证（基线 build/assets/index-v2910-20261001.js，只读 grep）
==============================================================================
基线 = 现有 33 模块全链产物（含 shoprefresh101 / shop102 / advend105 / numbal）。
本模块被追加在 V28_MODULES 末尾（numbal 之前），即 shoprefresh101 已应用。

0.9.9 的 R-101（`patches/client/yl_shoprefresh101_ext.py`）做了三件事：
  ① OM 内加 `[YLXW_SR_N,YLXW_SR_SET]=O.useState(0)` 作为「本次进店刷新计数」；
  ② 刷新按钮改为「首次免费、之后 `YLXW_SR_PRICE`(=500)」；
  ③ 注入 `var YLXW_SR_PRICE = 500;` 常量。
其中 ①（首次免费）与 ③ 的「费用透传 u(A,w)」是**正确部分**，本轮**保留不动**。
但 ② 把刷新费从 `YlxwShopRefreshCost(shop)` 的分级价（2 万~8 万）**降级**成了
写死的 500 灵石，并且按钮 title / 角标 `(…)` 也只显示这个写死常量。

基线实测（read-only grep，逐字节）：
  · `var YLXW_SR_PRICE = 500;`            = 1（@1783128，R-101 注入块内）
  · `const w=YLXW_SR_N<1?0:YLXW_SR_PRICE;` = 1（@1786214 刷新按钮 onClick 首行）
  · `花费${YLXW_SR_PRICE}灵石刷新`         = 1（@1786628 按钮 title）
  · `YLXW_SR_N<1?"免费":YLXW_SR_PRICE`     = 1（@1786848 按钮角标）
  ⇒ `YLXW_SR_PRICE` 全文 4 处 = 1 处定义 + 3 处引用（与任务书一致）。

分级价真值（R-101 前身 / 0.8.5 eco 注入，基线 @566077）：
    function YlxwShopRefreshCost(shop){ … YLXW_SHOP_REFRESH[shop.id] ||
      YLXW_SHOP_REFRESH_BY_TYPE[shop.type] … }
  村庄 20000 / 城市 40000 / 仙门 60000 / 限时 60000 / 黑市 80000 / 声望 80000。
  该函数是**顶层 function 声明**（列 0），与 OM 同处单一模块作用域 —— 旁证：
  OM（@1783150）已在直接调用同层的 `Rm`（@1782760）/ `fe`（@244726）/ `l1`，
  故 OM 内引用 `YlxwShopRefreshCost` 无作用域风险。

父级 hook `ES.handleRefreshShop`（@716917）当前形态：
    handleRefreshShop:O.useCallback((u,w)=>{ … const f=(typeof w==="number"&&
      isFinite(w)&&w>=0)?Math.floor(w):YlxwShopRefreshCost(l); …
      f>0&&r(v=>v&&{...v,spiritStones:v.spiritStones-f}), …})
  ⇒ 处理器**已经**支持「本次费用由按钮传入 w」，且 `w` 非法时回退 `YlxwShopRefreshCost(l)`。
    因此本轮**无需改处理器**：只要按钮把 w 算成分级价，扣费侧即自动正确。

==============================================================================
二、改后行为
==============================================================================
每个商店会话（弹窗 OM 挂载一次，关店卸载 → 再进店计数归零）：
  第 1 次点「刷新」→ **免费**（title「本次刷新免费」、角标「(免费)」），不弹确认框；
  第 2 次起每次 → 扣 `YlxwShopRefreshCost(shop)`（村庄 2 万 / 城市 4 万 / 仙门·限时 6 万 /
                  黑市·声望 8 万），title「花费 N 灵石刷新」、角标「(N)」；
                  灵石不足则提示且**不刷新**。
  ⇒ 显示口径 == 扣费口径 == 该商店真实分级价（本次修复的核心）。

实现（2 处就地替换，无新增文件、无注入块、不动存档 schema）：
  patch ① `r108-btn`   ：刷新按钮整块替换 ——
                         · `const w=YLXW_SR_N<1?0:YlxwShopRefreshCost(a)`（a = shop prop）
                         · title  `YLXW_SR_N<1?`本次刷新免费`:`花费${YlxwShopRefreshCost(a)}灵石刷新``
                         · 角标   `["(",YLXW_SR_N<1?"免费":YlxwShopRefreshCost(a),")"]`
  patch ② `r108-const` ：删除已废弃的 `var YLXW_SR_PRICE = 500;` 定义行。

==============================================================================
三、常量 `YLXW_SR_PRICE` 的处理口径（任务书 ★ 条款）
==============================================================================
改后该常量**既不再用于显示、也不再用于扣费**，且数值 500 与需求「恢复 2 万~8 万」
**直接矛盾** —— 留着一个「写着 500 却不生效」的常量属**误导性死代码**。
故选择任务书给出的「处理干净」路径：**连同定义行一并移除**（`YLXW_SR_PRICE`
全文计数 → 0）。门禁以 `==0` 断言其定义与引用均已清零，不留歧义。

⚠ 跨模块 needle 撞车（已全目录 grep，详见交付报告）：
  · `patches/client/yl_shoprefresh101_ext.py` 有 2 条 gate 依赖被本模块改掉的串：
      ('R101·首次免费判定', 'YLXW_SR_N<1?0:YLXW_SR_PRICE', 1, '==')
      ('R101·价格常量已注入', 'var YLXW_SR_PRICE = 500;',  1, '==')
    ⇒ 全链门禁清扫时这 2 条将 FAIL。shoprefresh101 属**禁改文件**（硬约束 #1），
      需由 lead 侧同步该 2 条 gate（或接受其为「被 R-108 取代」的历史断言）。
  · `patches/client/yl_shop102_ext.py` 的冻结面**不受影响**：
      ('冻结·刷新扣费回退未动', 'YlxwShopRefreshCost(l)', 1, '==') —— 本模块只新增
      `YlxwShopRefreshCost(a)`（不同串），ES 内 `YlxwShopRefreshCost(l)` 原样保留，仍 ==1。
      ('冻结·刷新仍走 l1', 'l1(a.type,l.realm,!0)', 1, '==') / ('冻结·商店弹窗签名未动',…) 均未动。
  · `deploy_v28/remote_check_v2811.sh:365` 的 `YlxwShopRefreshCost` 断言是 `ge 1`，
      本模块只增不减 ⇒ 仍通过；其余 `remote_check_v28{5,6,7,8,9,10}.sh` 的
      `const f=YlxwShopRefreshCost(l); eq 1` 早已被 shoprefresh101 改为 `(u,w)` 形态，
      属存量失效断言，与本模块无关。

==============================================================================
四、风险点
==============================================================================
1. `a`（OM 的 shop prop）与 ES 里的 `l`（currentShop）是同一对象
   （@1845097：`shop:S.currentShop … onRefreshShop:c.handleRefreshShop`），
   故按钮显示价与处理器回退价同源，不会出现「显示 4 万、扣 2 万」。
2. 分级价最贵 8 万，仍保留「首次免费」兜底，不会把玩家一次刷空。
3. 每次刷新渲染会多调 1~2 次 `YlxwShopRefreshCost`（纯查表 + try/catch，无副作用）；
   已确认该函数注释承诺「Never returns undefined / NaN / non-positive」，无渲染期异常风险。
4. 未改版本号、未动 build_v26n.py / CHANGELOG / EXPECT / deploy / srv / 其他 patch。
5. 门禁已同时断言：新形态 ==1、旧形态（写死 500 三处）==0、常量 ==0、冻结面 ==1。

锚点纪律：2 处锚点实测 count 均为 1；所有 needle 均对基线逐字核过。
"""

# --------------------------------------------------------------------------- 锚点

# ① 刷新按钮整块（shoprefresh101 应用后的形态，逐字节取自基线 @1786200 起）
BTN_OLD = (
    'u&&e.jsxs("button",{onClick:()=>{const w=YLXW_SR_N<1?0:YLXW_SR_PRICE;'
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
    'children:["(",YLXW_SR_N<1?"免费":YLXW_SR_PRICE,")"]})]})'
)

# 费用口径统一为「本商店分级价」：onClick 取费、title、角标三处同一表达式
BTN_NEW = (
    'u&&e.jsxs("button",{onClick:()=>{const w=YLXW_SR_N<1?0:YlxwShopRefreshCost(a);'
    'if(w>0&&l.spiritStones<w){Je(`灵石不足！刷新需要${w}灵石。`);return}'
    'const YLXW_SR_DO=()=>{const A=l1(a.type,l.realm,!0);'
    'YLXW_SR_SET(n=>n+1);u(A,w)};'
    'w===0?YLXW_SR_DO():'
    'an(`确定要花费 ${w} 灵石刷新商店物品吗？`,"确认刷新",YLXW_SR_DO)},'
    'className:"flex items-center gap-1 px-2.5 py-1.5 bg-stone-700 '
    'hover:bg-stone-600 text-stone-200 rounded border border-stone-600 '
    'transition-colors text-xs md:text-sm",'
    'title:YLXW_SR_N<1?`本次刷新免费`:`花费${YlxwShopRefreshCost(a)}灵石刷新`,'
    'children:[e.jsx(Ta,{size:14,className:"md:w-4 md:h-4"}),'
    'e.jsx("span",{className:"hidden sm:inline",children:"刷新"}),'
    'e.jsxs("span",{className:"text-[10px] text-stone-400",'
    'children:["(",YLXW_SR_N<1?"免费":YlxwShopRefreshCost(a),")"]})]})'
)

# ② 废弃常量定义行（连同其后一个空行一起收掉，保持 OM 前缩排不变）
CONST_OLD = 'var YLXW_SR_PRICE = 500;\n\nconst OM=('
# 注：标记文案刻意**不含** `YLXW_SR_PRICE` 字样，否则会把「常量零残留」门禁顶成 1
CONST_NEW = ('/* R108: 旧写死刷新费常量已废弃移除，刷新费恢复为 '
             'YlxwShopRefreshCost(shop) 分级价（2 万~8 万） */\nconst OM=(')

# 冻结面（别动别人的面）
OM_SIG = ('const OM=({isOpen:t,onClose:r,shop:a,player:l,onBuyItem:c,onSellItem:d,'
          'onRefreshShop:u,onOpenInventory:f})=>{')
ES_SIG = 'handleRefreshShop:O.useCallback((u,w)=>{'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    # ① 刷新按钮：恢复分级价 + 显示真实费用
    p.replace('r108-btn', BTN_OLD, BTN_NEW, expect=1,
              note='刷新按钮：首次仍免费；之后取 YlxwShopRefreshCost(a)；title/角标同步显示该价')

    # ② 移除已废弃的写死价常量（连同定义行，杜绝死代码）
    p.replace('r108-const', CONST_OLD, CONST_NEW, expect=1,
              note='删除 var YLXW_SR_PRICE = 500;（改后既不计费也不显示，且数值与需求矛盾）')

    return [
        # ================= 新形态（==1） =================
        ('R108·取费恢复分级价',      'YLXW_SR_N<1?0:YlxwShopRefreshCost(a)', 1, '==',
         '首次免费（0），之后 = 本商店 YlxwShopRefreshCost(shop) 分级价'),
        ('R108·标题显示真实费用',
         'title:YLXW_SR_N<1?`本次刷新免费`:`花费${YlxwShopRefreshCost(a)}灵石刷新`', 1, '==',
         '收费时 title 显示该商店真实分级价，不再是写死的 500'),
        ('R108·角标显示真实费用',
         'children:["(",YLXW_SR_N<1?"免费":YlxwShopRefreshCost(a),")"]', 1, '==',
         '角标与 title / 实扣三者同源'),
        ('R108·费用透传未断',        'u(A,w)',                                 1, '==',
         '本次费用仍经 u(A,w) 交给 handleRefreshShop'),
        ('R108·废弃标记已落',        '/* R108: 旧写死刷新费常量已废弃移除',  1, '==',
         '常量定义行被就地替换为标记，便于 grep 追溯'),

        # ================= 旧形态（==0） =================
        ('R108·旧固定价取费已清零',  'YLXW_SR_N<1?0:YLXW_SR_PRICE',           0, '==',
         '旧「之后一律 500」必须消失'),
        ('R108·旧固定价标题已清零',  '花费${YLXW_SR_PRICE}灵石刷新',           0, '==', ''),
        ('R108·旧固定价角标已清零',  'YLXW_SR_N<1?"免费":YLXW_SR_PRICE',      0, '==', ''),
        ('R108·常量定义行已清零',    'var YLXW_SR_PRICE = 500;',              0, '==', ''),
        ('R108·常量已彻底无残留',    'YLXW_SR_PRICE',                         0, '==',
         '定义 + 3 处引用全部清掉，不留「写着 500 却不生效」的死代码'),

        # ================= 冻结（保留 R-101 正确部分 + 别人的面） =================
        ('冻结·首次免费分支保留',    'w===0?YLXW_SR_DO():',                   1, '==',
         'R-101 正确部分：首次免费、不弹确认框'),
        ('冻结·刷新计数 state 保留', '[YLXW_SR_N,YLXW_SR_SET]=O.useState(0)', 1, '==',
         '关店卸载即归零 = 每次进店重置'),
        ('冻结·计数自增保留',        'YLXW_SR_SET(n=>n+1)',                   1, '==', ''),
        ('冻结·刷新沿用原生成逻辑',  'l1(a.type,l.realm,!0)',                 1, '==',
         '商品重新生成仍走 l1(...,!0)'),
        ('冻结·处理器签名未动',      ES_SIG,                                  1, '==',
         'handleRefreshShop 仍收 (u,w)，本轮不改处理器'),
        ('冻结·无费用时回退分级价',  'YlxwShopRefreshCost(l)',                1, '==',
         'ES 兜底未动（同时是 shop102 的冻结面）'),
        ('冻结·分级价表本体未动',    'function YlxwShopRefreshCost(shop)',    1, '==', ''),
        ('冻结·扣款走 setPlayer 函数式更新',
         'r(v=>v&&{...v,spiritStones:v.spiritStones-f})',                    1, '==', ''),
        ('冻结·灵石扣款写入未动',    'spiritStones:v.spiritStones-f',         1, '==', ''),
        ('冻结·货架落库写法未动',    'c({...l,items:u})',                     1, '==', ''),
        ('冻结·商店弹窗签名未动',    OM_SIG,                                  1, '==',
         'OM props 未动，isShopOpen 条件渲染点因此保持有效'),
        ('冻结·l1 调用点计数未变',   'l1(',                                   3, '==',
         '定义(壳)1 + 开架 l1(R,v.realm,!1) + 刷新 l1(a.type,l.realm,!0)'),
    ]
