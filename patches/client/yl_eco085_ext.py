# -*- coding: utf-8 -*-
r"""
yl_eco085_ext.py — 0.8.5 批次 · 灵石经济放缓（cli-eco）

=========================================================================== 一句话
把**持续获取型（无限次）**的灵石产出统一砍到原来的 1/5，并把商店「刷新一次」的
费用从「全站硬编码 100,000」改成**按商店档位分档 2W / 4W / 6W / 8W**。
每日限次的途径（宗门任务 3 次/日、邮件、交易行、离线收益）**一律不动**。

=========================================================================== 用户拍板（2026-09-28）
1. 「历练灵石获取有重大 bug，灵石怎么都是几千的上涨，进度太快了」
2. 「历练里面遇到的所有商店，刷新一次金额也改低一点，根据稀有度不同，
    最低为 2W，其余的以 2w 为基础比例增加」
5. 「秘境获取的灵石有点超模，要改低」
6. 「如果是持续获取灵石的项目要改低，如果一天有限进入的灵石获取途径，可以不修改」

    → 刷新费档位：**2W / 4W / 6W / 8W**（用户二选一，选了 ×2 阶梯）
    → 削减幅度：**÷5**（用户二选一，选了保守档）

=========================================================================== 定量地图（改动前，基线 0.8.4 bundle `365ef367…`）
完整表见 _stone_map.md（同目录，由 _stone_map.py 从产物公式复算生成）。

| 途径 | 公式落点 | 筑基期 L1 现值 | 改后 |
|---|---|---|---|
| 历练·灵石矿脉 | `Ym` 尾 `*5` | 400~1200 | 80~240 |
| 历练·奇遇 lucky | `Ym` 尾 `*5` | 1600~4000 | 320~800 |
| 秘境·极度危险 | `Ym` 尾 `*5` | 6400~20000 | 1280~4000 |
| 秘境·Roguelike `G3` | `YLRF×8.1833` | 1963~24549 | 393~4909 |
| 秘境·空手兜底 | `150×(1+idx×.5)` | 225 | 45 |
| 跨境界物品折算 | `(800\|300\|80)×5` | 4000/1500/400 | 800/300/80 |
| **不动** 历练战斗 `By` | `…×10` | 300 | 300 |
| **不动** 宗门任务 | `…×50/3` | 3 次/日 | — |
| **不动** 离线收益 | `YLRF×125` | 1 次/日 | — |

> `Ym` 尾部的 `*5`、`G3` 的 `8.1833`、`_ylf` 的 `*5`、`By` 的 `*10` 均为**上游原生**值
> （在 v26m / v26n / v27 / 0.8.1 基座中均存在，**不是本轮引入的回归**）——
> 本模块是**平衡调整**，不是修 bug。

=========================================================================== 关键设计：`Ym` 用「乘子参数」而不是「改常数」
`Ym(t, r)` 有三个调用点，语义完全不同：
  ① 主历练（无限次）      @1405785  `V=Ym(oe,{...})`     → 要砍
  ② 秘境（改后 3 次/日）   @1401241  `C=Ym(k,{...})`      → 用户明确要求砍（超模）
  ③ 宗门任务途中奇遇       @1115952  `D=Ym(A,{...})`      → **3 次/日，不动**

所以**不能**直接改 `Ym` 尾部的 `*5`（会连 ③ 一起砍）。改为给 `Ym` 增加第 3 个
参数 `_ylm`（缺省 1 = 原行为），只在 ①② 两个调用点传 0.2。
⇒ 「一处公式、两个策略」，且 ③ 的行为**逐字节不变**（门禁可证：`D=Ym(A,` 那行未动）。

=========================================================================== 跨境界物品（同时修 #3）
★ 0.8.5 侦察新发现：跨境界过滤器在产物里**有两份**，语义相同但落在两条不同路径：
     ① 战斗结算路径（@638350）  `_ylfb` 过滤 `u.items`，补偿写 `u.spiritChange`
     ② 历练奇遇路径（@1393058） `_ylf`  过滤 `r.itemsObtained`，补偿写 `r.spiritStonesChange`
   历史批次**只改了 ②** ⇒ 用户 #3「之前让修复跨境界物品不获取的问题没有做到」的
   真实原因之一就是**① 从未被修过**（① 仍是 90% 折算 + 10% 放行）。本批两份一起改。

★ 正则锚定 bug（#3 的第二重根因）：
   原 `const _m=/^\[(.+?)\]/.exec(x.name||"")` —— `^` 要求方括号在**字符串开头**，
   而实际物品名是 `【普通】[合道期]凡质木制宝鉴`（稀有度前缀在前）⇒ `_m` 恒 null
   ⇒ `_s` 退化成 `x.realm||x.realmRequirement||""`；两者都空时 `_s===""` ⇒ `return true`
   ⇒ **物品直接放行**。改为 `const _m=/\[([^\[\]]+)\]/`（在名字里找第一对方括号，
   不限位置）；解析不出合法境界时行为与旧版一致（放行）。

★ 过滤强度：原为「90% 折算成灵石 + 10% 放行」，折算额 `(800|300|80)*5` = 4000/1500/400。
   本次：**去掉随机（100% 过滤）**，折算额 ÷5 → `(160|60|16)`。
   折算额必须同步砍，否则「100% 过滤」会让折算**每次都触发**，反而推高收入
   （旧期望值 0.9×4000=3600 → 新值 160，即相对旧实现 ÷22.5，与全站 ÷5 的放缓口径一致）。

=========================================================================== 商店刷新费
`handleRefreshShop` 原为 `const f=1e5`（全站 100,000）。改为查表 `YlxwShopRefreshCost(shop)`：
    村庄杂货铺 20,000 ｜ 城市商会 40,000 ｜ 仙门宝库 60,000
    限时商店   60,000 ｜ 黑市     80,000 ｜ 声望商店 80,000
未知商店回落 40,000（`try/catch` + 兜底，绝不返回 undefined/NaN —— NaN 会毁档）。

=========================================================================== 技术约束遵守
· 纯 ASCII 注入块（注释用英文，中文一律 \\uXXXX，经 zh() 后无非 ASCII）。
· 不含禁用模式：iframe / postMessage / XMLHttpRequest / auth_token / X-YL-。
· 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
· 只新建本文件 + 测试/报告，不修改任何已有模块，不写回 build/assets/。

=========================================================================== 0.8.7 修订（T2 · 2026-09-29，implDrops）：折算三元 → 7×4 查表
《数值表-T2T3》定档：跨阶装备折算灵石 = base[q]×mult[r]
  base=[1,2,3,5,8,12,20]（等阶 q0..q6）× mult=[1,2.5,5,8]（普通/稀有/传说/仙品），
  全表 ≤ 现行顶格 160；每次折算 EV -56%~-81%（数值表 §3.1，tools/_t23_calc.py 复算）。
改动面（**只换折算表**，守卫串/正则/过滤强度零改动 —— v2 评审裁决）：
  1) INJECT_JS 追加 YlxwCvtStones(x,q)（自含常量，注入恰 1 份；T11 的 adv087 模块
     消费同名函数 —— 装配序硬约束 eco → adv087）。
  2) 两份过滤器的 `(_q>=6?160:_q>=4?60:16)` → `YlxwCvtStones(x,_q)`（产物恰 2 处）。
  3) 守卫串 `if(!x||x.isAdvancedItem||...)`（恒 2）零改动：isAdvancedItem 进阶物品
     （坊市 sellPrice 6e5~6e6）在过滤器之前放行、不进折算，防资产蒸发。
★ 表值以《数值表-T2T3》§2.2 表体为定档（28 格字面值注入 = YLXW_CVT_TBL）。
  注意 x.5 歧义格（2.5/7.5/12.5）：表体按 Python round（银行家）定档 = 2/8/12，
  与 JS Math.round 的 3/8/13 在 q0r1/q3r1 两格不同 —— 运行时查字面表，
  Python 侧 apply() 内逐格复算断言，永无舍入漂移。q0 行永不触发（无更低境界）。

0.8.7 T2 门禁清单（供接线人落 dryrun_087；计数口径 grep -o|wc -l）：
  - `(_q>=6?160:_q>=4?60:16)`                     2 → 0
  - `function YlxwCvtStones(`                     0 → 1
  - `YlxwCvtStones(x,_q)`（两份过滤器调用）        0 → 2（adv087 装配后再 +1 = 3）
  - `YLXW_CVT_BASE = [1, 2, 3, 5, 8, 12, 20]`     0 → 1
  - `YLXW_CVT_MULT = [1, 2.5, 5, 8]`              0 → 1
  - `[20, 50, 100, 160]`（定值表顶格行）           0 → 1
  - 守卫串 `if(!x||x.isAdvancedItem||...`          恒 2（禁改）
  - `const _m=/\[([^\[\]]+)\]/.exec(x.name||"");`  恒 2（0.8.5 已定，不动）
"""

# --------------------------------------------------------------------------- 注入块（纯 ASCII）

INJECT_JS = r'''
/* ===== yl-0.8.5 eco: continuous stone faucets /5 + per-shop refresh fee =====
   (1) Ym() gains a 3rd arg _ylm (default 1). Only the "unlimited" callers pass 0.2:
         main adventure  -> YLXW_STONE_MUL_ADV
         secret realm    -> YLXW_STONE_MUL_SR
       The sect-quest lucky-encounter caller keeps the default 1 (3/day, not nerfed).
   (2) Per-shop refresh fee replaces the old hard-coded 1e5 for every shop. */
var YLXW_STONE_MUL_ADV = 0.2;   /* main adventure (unlimited)   : stones /5 */
var YLXW_STONE_MUL_SR  = 0.2;   /* secret realm (daily-capped)  : stones /5 (user call) */

var YLXW_SHOP_REFRESH = {
  "shop-village": 20000,        /* common  */
  "shop-city": 40000,           /* rare    */
  "shop-sect": 60000,           /* epic    */
  "shop-limitedtime": 60000,    /* epic    */
  "shop-blackmarket": 80000,    /* mythic  */
  "shop-reputation": 80000      /* mythic  */
};
var YLXW_SHOP_REFRESH_BY_TYPE = {
  "\u6751\u5e84": 20000,        /* 村庄     */
  "\u57ce\u5e02": 40000,        /* 城市     */
  "\u4ed9\u95e8": 60000,        /* 仙门     */
  "\u9650\u65f6\u5546\u5e97": 60000,  /* 限时商店 */
  "\u9ed1\u5e02": 80000,        /* 黑市     */
  "\u58f0\u671b\u5546\u5e97": 80000   /* 声望商店 */
};
var YLXW_SHOP_REFRESH_DEFAULT = 40000;

/* Never returns undefined / NaN / non-positive: NaN would corrupt the save
   (spiritStones - NaN = NaN, which then gets persisted). */
function YlxwShopRefreshCost(shop) {
  try {
    if (!shop || typeof shop !== "object") return YLXW_SHOP_REFRESH_DEFAULT;
    var v = YLXW_SHOP_REFRESH[shop.id];
    if (v == null) v = YLXW_SHOP_REFRESH_BY_TYPE[shop.type];
    if (v == null || !isFinite(v) || v <= 0) v = YLXW_SHOP_REFRESH_DEFAULT;
    return Math.floor(v);
  } catch (e) { return YLXW_SHOP_REFRESH_DEFAULT; }
}

/* ===== T2 (0.8.7): cross-realm equippable -> stones, 7(realm) x 4(rarity) =====
   Doc formula: YLXW_CVT_BASE[q] * YLXW_CVT_MULT[r], rounded to the published
   value table (value-table doc uses banker's rounding: 2.5->2, 7.5->8, 12.5->12;
   JS Math.round would give 3/8/13). Runtime reads the literal YLXW_CVT_TBL
   below, so the two roundings can never drift apart.
   Rarity falls back to index 0 (common) when x.rarity is missing/unknown.
   Cap = 160 = the old top bucket; row q0 never fires (no lower realm exists).
   Shared entry point: adv087 (0.8.7 T11) consumes YlxwCvtStones too, so the
   assembly order must be eco -> adv087. */
var YLXW_CVT_BASE = [1, 2, 3, 5, 8, 12, 20];   /* realm base, q0..q6 */
var YLXW_CVT_MULT = [1, 2.5, 5, 8];            /* common/rare/epic/mythic */
var YLXW_CVT_RAR = ["\u666e\u901a", "\u7a00\u6709", "\u4f20\u8bf4", "\u4ed9\u54c1"];
var YLXW_CVT_TBL = [
  [1, 2, 5, 8],       /* q0 (never fires) */
  [2, 5, 10, 16],     /* q1 */
  [3, 8, 15, 24],     /* q2 */
  [5, 12, 25, 40],    /* q3 */
  [8, 20, 40, 64],    /* q4 */
  [12, 30, 60, 96],   /* q5 */
  [20, 50, 100, 160]  /* q6, cap */
];
function YlxwCvtStones(x, q) {
  try {
    var ri = YLXW_CVT_RAR.indexOf((x && x.rarity) || YLXW_CVT_RAR[0]);
    if (ri < 0) ri = 0;
    var qq = Math.max(0, Math.min(6, q | 0));
    var v = YLXW_CVT_TBL[qq] && YLXW_CVT_TBL[qq][ri];
    return (v == null || !isFinite(v) || v <= 0) ? 1 : v;
  } catch (e) { return 1; }
}
'''

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- 锚点（均取自基线 raw 文本，实测 count==1）

# —— 注入锚：紧贴 Ym 定义之前（同作用域；function/var 声明提升，注入位置不影响调用）——
INJECT_ANCHOR = 'function Ym(t,r){const a=fe.indexOf(r.realm),'

# —— (E1) Ym 签名 + 尾部乘子 ——
YM_SIG_ANCHOR = 'function Ym(t,r){const a=fe.indexOf(r.realm),'
YM_SIG_REPL = 'function Ym(t,r,_ylm){const a=fe.indexOf(r.realm),'
YM_MUL_ANCHOR = 'Math.floor(t.spiritStonesChange*u)*5'
# 外层再套一层 Math.floor：`*5*0.2` 在 IEEE754 下理论上可能产出 161.00000000000003
# 这类小数（0.2 非精确二进制），会让 spiritStones 变成小数并影响展示。
# `_ylm==null`（宗门奇遇，3 次/日）时 *1 已是整数 ⇒ 该 Math.floor 是恒等，行为逐字节不变。
YM_MUL_REPL = 'Math.floor(Math.floor(t.spiritStonesChange*u)*5*(_ylm==null?1:_ylm))'

# —— (E1) 两个「无限次」调用点加乘子 ——
ADV_CALL_ANCHOR = 'V=Ym(oe,{realm:t.realm,realmLevel:t.realmLevel,maxHp:F.maxHp})'
ADV_CALL_REPL = 'V=Ym(oe,{realm:t.realm,realmLevel:t.realmLevel,maxHp:F.maxHp},YLXW_STONE_MUL_ADV)'
SR_CALL_ANCHOR = 'C=Ym(k,{realm:l.realm,realmLevel:l.realmLevel,maxHp:_.maxHp})'
SR_CALL_REPL = 'C=Ym(k,{realm:l.realm,realmLevel:l.realmLevel,maxHp:_.maxHp},YLXW_STONE_MUL_SR)'

# —— (E2a) 跨境界物品：正则不再锚定串首（两份共用，expect=2）——
YLF_REGEX_ANCHOR = 'const _m=/^\\[(.+?)\\]/.exec(x.name||"");'
YLF_REGEX_REPL = 'const _m=/\\[([^\\[\\]]+)\\]/.exec(x.name||"");'

# —— (E2b) 跨境界物品 · ① 战斗结算路径（补偿写 u.spiritChange）——
# 0.8.7 T2：折算三元 → 7×4 查表 YlxwCvtStones(x,_q)（x=过滤函数入参物品对象，
# 与守卫串同作用域；守卫串/正则/_q 语义零改动）。
YLFB_ANCHOR = (
    'if(_q<=_ylpk)return true;'
    'if(Math.random()<.9){u.spiritChange=(u.spiritChange||0)+(_q>=6?800:_q>=4?300:80)*5;return false}'
    'return true'
)
YLFB_REPL = (
    'if(_q<=_ylpk)return true;'
    'u.spiritChange=(u.spiritChange||0)+YlxwCvtStones(x,_q);'
    'return false'
)

# —— (E2c) 跨境界物品 · ② 历练奇遇路径（补偿写 r.spiritStonesChange）——
YLF_ANCHOR = (
    'if(_q<=_ylpk)return true;'
    'if(Math.random()<.9){r.spiritStonesChange=(r.spiritStonesChange||0)+(_q>=6?800:_q>=4?300:80)*5;return false}'
    'return true'
)
YLF_REPL = (
    'if(_q<=_ylpk)return true;'
    'r.spiritStonesChange=(r.spiritStonesChange||0)+YlxwCvtStones(x,_q);'
    'return false'
)

# —— (E3) 秘境 Roguelike G3 系数 ÷5 ——
G3_ANCHOR = 'const l=fe.indexOf(a.realm),c=YLRF(a)*(1+r*.2)*8.1833;'
G3_REPL = 'const l=fe.indexOf(a.realm),c=YLRF(a)*(1+r*.2)*1.63666;'

# —— (E4) 秘境「空手而归」兜底 ÷5 ——
SRFB_ANCHOR = 'spiritStonesChange:Math.floor(150*(1+fe.indexOf(l.realm)*.5)),eventColor:"normal"'
SRFB_REPL = 'spiritStonesChange:Math.floor(30*(1+fe.indexOf(l.realm)*.5)),eventColor:"normal"'

# —— (E5) 商店刷新费 ——
REFRESH_ANCHOR = 'if(!l||!t)return;const f=1e5;'
REFRESH_REPL = 'if(!l||!t)return;const f=YlxwShopRefreshCost(l);'

# —— 基线未动断言用锚 ——
SECT_YM_ANCHOR = 'D=Ym(A,{realm:l.realm,realmLevel:l.realmLevel,maxHp:I.maxHp})'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含改名 + 全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # ----------------------------------------------------------- T2 表值复算（非 grep，装配期硬断言）
    # 《数值表-T2T3》§2.2 表体定档：值 = round(base[q]*mult[r])（Python/银行家舍入口径，
    # 2.5->2、7.5->8、12.5->12 与表体逐格一致）；顶格 160 = 现行顶格；行列单调不减；全正整数。
    _cvt_base = [1, 2, 3, 5, 8, 12, 20]
    _cvt_mult = [1, 2.5, 5, 8]
    _cvt_tbl = [[1, 2, 5, 8], [2, 5, 10, 16], [3, 8, 15, 24], [5, 12, 25, 40],
                [8, 20, 40, 64], [12, 30, 60, 96], [20, 50, 100, 160]]
    for _q in range(7):
        for _r in range(4):
            _exp = round(_cvt_base[_q] * _cvt_mult[_r])
            assert _cvt_tbl[_q][_r] == _exp, \
                'T2 表值漂移: tbl[%d][%d]=%r != round(%r*%r)=%r' % (
                    _q, _r, _cvt_tbl[_q][_r], _cvt_base[_q], _cvt_mult[_r], _exp)
    assert max(max(r) for r in _cvt_tbl) == 160, 'T2 顶格必须=160'
    assert all(_cvt_tbl[q][r] <= _cvt_tbl[q][r + 1] for q in range(7) for r in range(3)), 'T2 行单调'
    assert all(_cvt_tbl[q][r] <= _cvt_tbl[q + 1][r] for q in range(6) for r in range(4)), 'T2 列单调'
    assert all(v == int(v) and v > 0 for row in _cvt_tbl for v in row), 'T2 全正整数'

    # 0) 注入乘子常量 + 商店刷新费查表（同 Ym 作用域）
    p.insert_before(
        'eco085-consts',
        INJECT_ANCHOR,
        zh(INJECT_JS) + '\n',
        expect=1,
        note='注入 YLXW_STONE_MUL_* / YLXW_SHOP_REFRESH* / YlxwShopRefreshCost'
    )

    # 1) (E1) Ym 签名加第 3 参 + 尾部乘子
    p.replace('eco085-ym-sig', YM_SIG_ANCHOR, YM_SIG_REPL, expect=1,
              note='function Ym(t,r) -> function Ym(t,r,_ylm)')
    p.replace('eco085-ym-mul', YM_MUL_ANCHOR, YM_MUL_REPL, expect=1,
              note='尾部 *5 -> *5*(_ylm==null?1:_ylm)')

    # 2) (E1) 两个无限次调用点传 0.2；宗门奇遇调用点**不动**
    p.replace('eco085-call-adv', ADV_CALL_ANCHOR, ADV_CALL_REPL, expect=1,
              note='主历练 Ym 调用传 YLXW_STONE_MUL_ADV')
    p.replace('eco085-call-sr', SR_CALL_ANCHOR, SR_CALL_REPL, expect=1,
              note='秘境 Ym 调用传 YLXW_STONE_MUL_SR')

    # 3) (E2a) 跨境界物品：正则不再锚定串首（两份过滤器共用同一段正则文本）
    p.replace('eco085-ylf-regex', YLF_REGEX_ANCHOR, YLF_REGEX_REPL, expect=2,
              note='^\\[ -> \\[  (名字里的第一对方括号，不限位置)；两份过滤器同时生效')

    # 3b) (E2b) 战斗结算路径：100% 过滤 + 折算额 ÷5
    p.replace('eco085-ylfb', YLFB_ANCHOR, YLFB_REPL, expect=1,
              note='战斗路径 去掉 10% 漏网；(800|300|80)*5 -> (160|60|16)')

    # 3c) (E2c) 历练奇遇路径：100% 过滤 + 折算额 ÷5
    p.replace('eco085-ylf', YLF_ANCHOR, YLF_REPL, expect=1,
              note='奇遇路径 去掉 10% 漏网；(800|300|80)*5 -> (160|60|16)')

    # 4) (E3) 秘境 Roguelike 系数 ÷5
    p.replace('eco085-g3', G3_ANCHOR, G3_REPL, expect=1, note='8.1833 -> 1.63666')

    # 5) (E4) 秘境空手兜底 ÷5
    p.replace('eco085-srfb', SRFB_ANCHOR, SRFB_REPL, expect=1, note='150 -> 30')

    # 6) (E5) 商店刷新费分档
    p.replace('eco085-refresh', REFRESH_ANCHOR, REFRESH_REPL, expect=1,
              note='const f=1e5 -> const f=YlxwShopRefreshCost(l)')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- 注入块 ----
        ('E·刷新费函数已定义',        'function YlxwShopRefreshCost(shop)',   1, '==', ''),
        ('E·六家商店 id 全在表内',    '"shop-village": 20000',                1, '==', ''),
        ('E·黑市/声望 = 8W',          '"shop-blackmarket": 80000',            1, '==', ''),
        ('E·仙门/限时 = 6W',          '"shop-limitedtime": 60000',            1, '==', ''),
        ('E·城市商会 = 4W',           '"shop-city": 40000',                   1, '==', ''),
        ('E·未知商店兜底 4W',         'var YLXW_SHOP_REFRESH_DEFAULT = 40000;', 1, '==', ''),
        ('E·非有限值兜底',            'if (v == null || !isFinite(v) || v <= 0)', 1, '==', ''),
        ('E·主历练乘子 0.2',          'var YLXW_STONE_MUL_ADV = 0.2;',        1, '==', ''),
        ('E·秘境乘子 0.2',            'var YLXW_STONE_MUL_SR  = 0.2;',        1, '==', ''),

        # ---- (E1) Ym ----
        ('E·Ym 签名已加 _ylm',        'function Ym(t,r,_ylm){',               1, '==', ''),
        ('E·Ym 尾乘子已生效',         'Math.floor(Math.floor(t.spiritStonesChange*u)*5*(_ylm==null?1:_ylm))', 1, '==', '外层 floor 防 IEEE754 小数'),
        ('E·主历练调用带乘子（R-062 已按类型分流包裹）',
         'if(V=(Q==="secret_realm"?YlxwSrBoostR62:function(e0){return e0})(Ym(oe,{realm:t.realm,realmLevel:t.realmLevel,maxHp:F.maxHp},YLXW_STONE_MUL_ADV)),ek()){',
         1, '==', 'R-062 把 V 点包了分流壳；内层 Ym(…,MUL_ADV) 调用串由 r062 自带门禁另断在位'),
        ('E·秘境调用带乘子',          SR_CALL_REPL,                           1, '==', ''),
        ('E·宗门奇遇调用未动',        SECT_YM_ANCHOR,                         1, '==', '3 次/日，按用户要求不改'),
        ('E·旧 Ym 签名已清零',        'function Ym(t,r){const a=fe.indexOf(r.realm),', 0, '==', ''),

        # ---- (E2) 跨境界物品（两份过滤器 + 正则 + T2 查表）----
        ('E·正则不再锚定串首',        'const _m=/\\[([^\\[\\]]+)\\]/.exec(x.name||"");', 2, '==', '战斗 + 奇遇 两份'),
        ('E·旧锚定串首正则已清零',     'const _m=/^\\[(.+?)\\]/.exec(x.name||"");', 0, '==', ''),
        ('E·战斗路径已 100% 过滤',     'if(_q<=_ylpk)return true;u.spiritChange=(u.spiritChange||0)+YlxwCvtStones(x,_q);return false', 1, '==', 'T2 查表形态'),
        ('E·奇遇路径已 100% 过滤',     'if(_q<=_ylpk)return true;r.spiritStonesChange=(r.spiritStonesChange||0)+YlxwCvtStones(x,_q);return false', 1, '==', 'T2 查表形态'),
        ('T2·查表调用恰2（两份）',     'YlxwCvtStones(x,_q)',                   2, '==', 'adv087(T11) 装配后全产物再 +1=3'),
        ('T2·查表函数定义恰1',        'function YlxwCvtStones(',                1, '==', 'T11 复用此定义'),
        ('T2·等阶基数表',             'var YLXW_CVT_BASE = [1, 2, 3, 5, 8, 12, 20];', 1, '==', ''),
        ('T2·稀有度乘数表',           'var YLXW_CVT_MULT = [1, 2.5, 5, 8];',   1, '==', ''),
        ('T2·稀有度名表(转义形态)',    'var YLXW_CVT_RAR = ["\\u666e\\u901a", "\\u7a00\\u6709", "\\u4f20\\u8bf4", "\\u4ed9\\u54c1"];', 1, '==', ''),
        ('T2·定值表顶格行160',        '[20, 50, 100, 160]',                    1, '==', '全表顶格=现行顶格'),
        ('T2·NaN 兜底',              '(v == null || !isFinite(v) || v <= 0) ? 1 : v;', 1, '==', '折算永不 undefined/NaN'),
        ('T2·旧三元折算已清零',       '(_q>=6?160:_q>=4?60:16)',               0, '==', '0.8.7 换 7x4 查表'),
        ('E·旧 10% 漏网已清零',       'if(Math.random()<.9){u.spiritChange=',  0, '==', '战斗路径'),
        ('E·旧 10% 漏网已清零②',      'if(Math.random()<.9){r.spiritStonesChange=', 0, '==', '奇遇路径'),
        ('E·旧折算额已清零',          '(_q>=6?800:_q>=4?300:80)*5',           0, '==', '两份都必须清零'),

        # ---- (E3)(E4) 秘境 ----
        ('E·G3 系数已 ÷5',            'YLRF(a)*(1+r*.2)*1.63666;',            1, '==', ''),
        ('E·旧 G3 系数已清零',        '*8.1833;',                             0, '==', ''),
        ('E·秘境兜底已 ÷5',           SRFB_REPL,                              1, '==', ''),
        ('E·旧兜底 150 已清零',       'Math.floor(150*(1+fe.indexOf(l.realm)*.5))', 0, '==', ''),

        # ---- (E5) 商店刷新 ----
        # ★ 2026-10-01 0.9.9：shoprefresh101 改了 handleRefreshShop 的签名与取费行
        #   （`u=>` → `(u,w)=>`，并支持透传免费/付费），故本模块不再断言该形态；
        #   最终形态由 shoprefresh101 断言。
        ('E·刷新费已被 shoprefresh101 接管', REFRESH_REPL,                   0, '==', '0.9.9 由 shoprefresh101 接管'),
        ('E·旧硬编码 1e5 已清零',     'const f=1e5;',                         0, '==', ''),
        ('E·刷新提示文案仍在',        '无法刷新商店。需要',                    1, '==', '模板串保留，仅 f 换来源'),

        # ---- 基线未被破坏 ----
        ('基线·历练战斗 By 未动',     'M=Math.max(10,Math.round($*b))*10',    1, '==', '战斗奖励本轮不改'),
        ('基线·宗门任务未动',         'stoneGain:Math.floor(u*YLRF(t)*50/3)', 1, '==', '3 次/日'),
        ('基线·离线收益未动',         'm=Math.floor(YLRF(t)*125)',            1, '==', '每日 1 次（≤24h 封顶）'),
        # ★ 2026-09-30 约束权移交：R-024 把每跳灵石 ×5 换成 __ylsq（含境界内因子）
        ('基线·打坐灵石（R-024 已接管）', 'w=$.spiritStones+__ylsq',           1, '==', 'R-024 已接管该表达式'),
        ('基线·YLRF 定义未动',        'function YLRF(j) {',                   1, '==', ''),
        ('基线·_ylExpCap 未动',       '_ylCapPct=.25',                        1, '==', ''),
        ('基线·秘境事件 base 未动',   'stones:[800,2500]',                    1, '==', '只改境界放大，不改 base'),
        ('基线·_ylf 守卫未动',        'if(!x||x.isAdvancedItem||!(x.isEquippable||x.equipmentSlot))return true;', 2, '==', '两份过滤器的守卫都必须原样保留'),
        ('基线·_ylf 过滤只作用于装备',  'x.isEquippable||x.equipmentSlot',     2, '>=', ''),
    ]
    return gates
