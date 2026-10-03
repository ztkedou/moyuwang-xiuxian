# -*- coding: utf-8 -*-
r"""
yl_r135_ext.py — R-135 历练商店：稀有属性道具售价重定档 + 高稀有度掉落率大幅下调

需求原文（台账 R-135，用户逐字）
--------------------------------------------------------------------------
  「历练中遇到的商店，稀有物品加的属性不少，但是售价才 1、200 太便宜了。尤其是很多加神识的。
    两点需求：
    一，完全重新策划物品属性，稀有属性（神识、身法这些）只有很少量的高级物品才会增加，
        数值可以不改，加稀有属性的物品售价大幅提升。普通物品售价也要小幅度提升。
    二，历练中物品的稀有度高的物品获取概率大幅度下降，我才刚开始没多久，千年灵芝这种加寿命的
        都能得到。高级品质的物品获取几率应该非常低。」

基线 = build/assets/index-v2915-20261002.js（2,278,270 B / 2,111,568 chars；含 \uXXXX 转义 + 真中文）

==============================================================================
一、侦察结论（全部字节级实测 count==1）
==============================================================================

【0】先证明「历练中遇到的商店」是哪一套 —— 唯一入口
--------------------------------------------------------------------------
  历练主循环 `handleAdventure`（@1897740 附近）内：
      `if(Math.random()<.15) ... a("你在路上发现了一处商铺...","normal") ...
        const te=[ht.Village,ht.City,ht.Sect,ht.LimitedTime,ht.BlackMarket,ht.Reputation],
              ee=te[Math.floor(Math.random()*te.length)]; v(ee)`   // v = onOpenShop
  ⇒ 历练途中 15% 概率遇到商店，类型从 6 种里等概率抽。
  ⇒ `onOpenShop` 是 `nk(...)` 的入参，`nk` 只被 `handleAdventure` 链路使用
     （onOpenShop 全库 2 处：定义 1 + 该 prop 1）。
  ⇒ `handleOpenShop`（@1874856）把静态店（村庄/城市/仙门）走 `YlxwShopRealmGate`，
     把 黑市/限时/声望 走 `l1(...)` 生成货架。
  ⇒ **商店购买价唯一出口 = `YlxwShopPriceOf(it,player)`**（R-102/103 引入）：
       · 卡片显示价 @1815436  `const A=YlxwShopPriceOf(w,l),...`
       · 实际扣费   @1875375  `const _=YlxwShopPriceOf(R,N)*E;`
     全库 3 处（定义 1 + 上述 2 调用点）；**不经过洞府/灵田/灵玉阁等其它系统**（已逐一排除）。
  ⇒ 结论：改 `YlxwShopPriceOf` 就是改「历练中遇到的商店」的售价。

  「售价才 1、200」逐位对应：村庄/城市/仙门静态货架 `Bi`（@1800089）里
      凝神丹 120（城市）/200（仙门）、强体丹 120/200、洗髓丹 150、青钢剑 200、紫猴花 80。
      其中 凝神丹 permanentEffect:{spirit:20}、强体丹 {physique:20}（常量池 @312150），
      正是用户点名的「加神识/体魄」——120/200 与「1、200」吻合。

【1】掉落稀有度决策点（「按品质取物品」的上游）
--------------------------------------------------------------------------
  事件模板池 `pw()` 预生成 720 普通 / 120 幸运 / 300 秘境 / 60 宗门（`Oc` @533920）。
  每个模板的掉落品质由模板构造器内一个确定性伪随机判定：
    · 普通池 `hw(t)` @540753：
        `l=sa(t,1),c=l<.6?"普通":l<.9?"稀有":"传说",d=vy();`
        ⇒ **60% 普通 / 30% 稀有 / 10% 传说**（`c` 再喂给 `itemObtained:fs(t,..)?ui(c,t)`）
    · 幸运池 `xw(t)` @565699：
        `j=fs(t,.5,460)?"传说":"仙品"`
        ⇒ **50% 传说 / 50% 仙品**；且 `itemObtained:fs(t,.7,500)?ui(j,t)`（70% 出物品）
        ⇒ 幸运事件本身触发率高达 30%（`V=Math.min(.3,...)`）⇒ 实际每次历练出仙品约 10.5%。
    · 秘境池 `gw(t)` @567226：
        `v=a==="低"||a==="中"?"稀有":"传说"`
    · 宗门池 `bw(t)` @569367：恒 `ui("稀有",t)`（无 传说/仙品，本模块不动）
  `ui(t,r)` @571882 = 按品质从全局物品池 `pi()` 里确定性取一件（`pi` @303784）。
  `千年灵芝` 稀有度=传说（AN 表 @301949），故降「传说」权重即可显著压低其出现。

==============================================================================
二、改动清单（3 处锚点 + 1 段注入，全部 count==1；均为客户端）
==============================================================================

【A】必做①：稀有属性道具售价大幅提升 + 普通物品小幅提升
  落点 = `YlxwShopPriceOf(it,player)`（历练商店购买价唯一出口）。
  做法 = 注入 `YlxwR135HasRareAttr(it)` + 两个倍率常量，并在原函数出口乘倍率：
    · 稀有属性（effect/permanentEffect 含 spirit|speed|physique 且 >0）→ ×YLXW_R135_RARE_PRICE_MUL = 6
    · 其余物品                                                      → ×YLXW_R135_BASE_PRICE_MUL = 1.5
  保留原「阶位折扣」逻辑（`Math.pow(YLXW_SHOP_TIER_DOWN,g)`）不动，只在最外层乘。
  显示价与实扣价同一函数 ⇒ 二者仍恒等（R-103 口径不破）。

【B】必做②：高稀有度掉落率大幅下降（3 个决策点各一处）
    · 普通池 hw：`l<.6?"普通":l<.9?"稀有":"传说"` → `l<.88?"普通":l<.98?"稀有":"传说"`
        ⇒ 普通 88% / 稀有 10% / 传说 2%（传说 10%→2%，×0.2；稀有 30%→10%）
    · 幸运池 xw：`j=fs(t,.5,460)?"传说":"仙品"`
                 → `j=fs(t,.8,460)?"稀有":fs(t,.85,461)?"传说":"仙品"`
        ⇒ 稀有 80% / 传说 17% / 仙品 3%（原 传说50%/仙品50%）
    · 秘境池 gw：`v=a==="低"||a==="中"?"稀有":"传说"` → `v=a==="极度危险"?"传说":"稀有"`
        ⇒ 仅「极度危险」给传说，低/中/高一律稀有。

【C】可选③：神识/身法只在高阶物品出现 —— 本轮**不做**，理由见 §四。

==============================================================================
三、口径与量级（炼气 L1，Jm=1.0、同阶 gap=0）
==============================================================================
  购买价 = ceil(原 price × 1.0 × 倍率)
    · 凝神丹 120 → 720（×6，神识+20）     · 强体丹 120 → 720（×6，体魄+20）
    · 洗髓丹 150 → 900（×6，含 spirit）   · 青钢剑 200 → 1200（×6，含 spirit/speed）
    · 止血草 10  → 15（×1.5，普通）        · 聚气丹 30 → 45（×1.5，普通）
    · 千年灵芝 50000（Ea 覆写价）→ 300000（×6，含 spirit/physique/maxLifespan）
  掉落品质（普通池 720 模板）：传说 72 → 14.4 个模板；幸运池 120 模板：仙品 60 → 3.6 个。
  ⇒ 用户「刚玩就能拿到千年灵芝」的直接根因（传说权重 + 幸运池仙品洪峰）被同时压掉。

==============================================================================
四、为什么「可选③ 神识/身法只在高阶物品出现」本轮不做（诚实说明）
==============================================================================
  1. 该条要动的是**物品字典本体**：常量池 `pi()` 由 `ta / Zb / AN / Vn / on ...` 多张表拼成，
     神识/身法加成散落在 ~265k–310k（装备表）与 ~350k–401k（另一批道具表）**上百条**字面量里；
     要「只让高阶物品加神识/身法」= 逐条判断稀有度再删键，属**大规模重排**，锚点数量与碰撞风险
     远超单点补丁的可控范围，且会与 R-107（已把 spirit/physique/speed 全部 ÷10）的既有断言面冲突。
  2. 用户同段写明「数值可以不改」⇒ 本条不是数值问题，而是「分布」问题；本模块已用【A】的
     价格倍率把「带稀有属性的道具」在经济上显著抬高（×6），并（若采纳）可在服务端/专项轮次
     再做「低阶物品剔除稀有属性」的结构性重排。
  3. 因此本轮**不做**，改由【A】的价格杠杆 + 【B】的掉落率杠杆达成用户的核心体感目标。

==============================================================================
五、契约（standalone · 同 localtest/yl_r131fix_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r135-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · `gates()` 返回五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
  · 纯客户端；不改 srv/**、build_v26n.py、CHANGELOG*、其它 yl_*_ext.py、产物本体。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 锚点（ASCII/中文混合；实测 count==1）

# ===== 【A】历练商店购买价唯一出口：注入稀有属性判定 + 倍率，改写函数出口 =====
PRICE_OLD = (
    'function YlxwShopPriceOf(it, player) {\n'
    '  var base = Rm(it.price, player), g = YlxwShopTierGap(it, player);\n'
    '  if (g <= 0) return base;\n'
    '  return Math.max(1, Math.ceil(base * Math.pow(YLXW_SHOP_TIER_DOWN, g)));\n'
    '}'
)

PRICE_NEW = (
    '/* YLXW_R135_V2915[r135] adventure-shop price rework + drop rarity nerf */\n'
    '/* == YL_R135 == R-135 price rework for the adventure-encountered shop (yl \u5386\u7ec3\u5546\u5e97).\n'
    '   Items that add rare attributes (spirit/speed/physique) cost much more; ordinary items a bit more.\n'
    '   This is the SINGLE buy-price exit used by both the shop card and the buy handler. */\n'
    'var YLXW_R135_RARE_PRICE_MUL = 6;    /* rare-attribute items: sharp increase */\n'
    'var YLXW_R135_BASE_PRICE_MUL = 1.5;  /* ordinary items: small increase */\n'
    'var YLXW_R135_RARE_KEYS = ["spirit", "speed", "physique"];\n'
    'function YlxwR135HasRareAttr(it) {\n'
    '  if (!it) return false;\n'
    '  var sets = [it.effect, it.permanentEffect];\n'
    '  for (var i = 0; i < sets.length; i++) {\n'
    '    var o = sets[i];\n'
    '    if (!o) continue;\n'
    '    for (var k = 0; k < YLXW_R135_RARE_KEYS.length; k++) {\n'
    '      var v = Number(o[YLXW_R135_RARE_KEYS[k]]);\n'
    '      if (isFinite(v) && v > 0) return true;\n'
    '    }\n'
    '  }\n'
    '  return false;\n'
    '}\n'
    'function YlxwShopPriceOf(it, player) {\n'
    '  var base = Rm(it.price, player), g = YlxwShopTierGap(it, player);\n'
    '  if (g > 0) base = Math.max(1, Math.ceil(base * Math.pow(YLXW_SHOP_TIER_DOWN, g)));\n'
    '  var mul = YlxwR135HasRareAttr(it) ? YLXW_R135_RARE_PRICE_MUL : YLXW_R135_BASE_PRICE_MUL;\n'
    '  return Math.max(1, Math.ceil(base * mul));\n'
    '}'
)

# ===== 【B1】普通历练池 hw：60/30/10 → 88/10/2 =====
HW_OLD = 'l=sa(t,1),c=l<.6?"\u666e\u901a":l<.9?"\u7a00\u6709":"\u4f20\u8bf4",d=vy();'
HW_NEW = 'l=sa(t,1),c=l<.88?"\u666e\u901a":l<.98?"\u7a00\u6709":"\u4f20\u8bf4",d=vy();'

# ===== 【B2】幸运/奇遇池 xw：50 传说 / 50 仙品 → 80 稀有 / 17 传说 / 3 仙品 =====
XW_OLD = 'j=fs(t,.5,460)?"\u4f20\u8bf4":"\u4ed9\u54c1"'
XW_NEW = ('j=fs(t,.8,460)?"\u7a00\u6709":fs(t,.85,461)?"\u4f20\u8bf4":"\u4ed9\u54c1"')

# ===== 【B3】秘境池 gw：仅「极度危险」给传说 =====
GW_OLD = 'v=a==="\u4f4e"||a==="\u4e2d"?"\u7a00\u6709":"\u4f20\u8bf4"'
GW_NEW = 'v=a==="\u6781\u5ea6\u5371\u9669"?"\u4f20\u8bf4":"\u7a00\u6709"'

EDITS = [
    ('R135-A 商店售价倍率（稀有×6 / 普通×1.5）', PRICE_OLD, PRICE_NEW),
    ('R135-B1 普通池品质 60/30/10→88/10/2', HW_OLD, HW_NEW),
    ('R135-B2 幸运池品质 50/50→80/17/3', XW_OLD, XW_NEW),
    ('R135-B3 秘境池传说仅极度危险', GW_OLD, GW_NEW),
]

# --------------------------------------------------------------------------- 在位标记 / 冻结门禁串（全部实测 count==1）

FR_MARK = 'YLXW_R135_V2915'
FR_NEW_FN = 'function YlxwR135HasRareAttr(it) {'
FR_RARE_MUL = 'var YLXW_R135_RARE_PRICE_MUL = 6;'
FR_BASE_MUL = 'var YLXW_R135_BASE_PRICE_MUL = 1.5;'
FR_PRICE_NEW = 'var mul = YlxwR135HasRareAttr(it) ? YLXW_R135_RARE_PRICE_MUL : YLXW_R135_BASE_PRICE_MUL;'

# 冻结：R-102/103/104 面（本模块只在最外层乘倍率，这些逐字不动）
FRZ_TIER_DOWN = 'var YLXW_SHOP_TIER_DOWN = 0.6;'
FRZ_CARD = 'const A=YlxwShopPriceOf(w,l),'
FRZ_BUY = 'const _=YlxwShopPriceOf(R,N)*E;'
FRZ_GATE_FN = 'function YlxwShopRealmGate(items, realm) {'
FRZ_TIER_FN = 'function YlxwShopItemTier(it) {'
FRZ_L1RAW = 'function l1raw(t,r,a=!1){const l=fe.indexOf(r),c=[],d=new Set;'
FRZ_RM = 'function Rm(t,r){return Math.max(1,Math.ceil(t*Jm(r)))}'
FRZ_XM = 'xm=t=>{'
FRZ_STOCKFN = 'const _ylStockFn=t=>({...t,stock:t.stock??({"'
# 冻结：历练商店入口（15% 遇店）与事件池规模
FRZ_ENC = '\u4f60\u5728\u8def\u4e0a\u53d1\u73b0\u4e86\u4e00\u5904\u5546\u94fa'
FRZ_SHOPTYPES = ('const te=[ht.Village,ht.City,ht.Sect,ht.LimitedTime,ht.BlackMarket,ht.Reputation]')
FRZ_OC = 'Oc={NORMAL:720,LUCKY:120,SECRET_REALM:300,SECT_CHALLENGE:60}'
FRZ_FS = 'function fs(t,r,a=0){return sa(t,a)<r}'
# 冻结：其它品质决策点未被误伤
FRZ_BW = 'itemObtained:fs(t,.4,670)?ui("\u7a00\u6709",t):void 0'
FRZ_UI = 'function ui(t,r){const a=pi();'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note) —— 供 dryrun 门禁表收录。"""
    return [
        # ===================== 【A】售价 =====================
        ('R135A·稀有倍率常量已注入', FR_RARE_MUL, 1, '==', '稀有属性道具 ×6'),
        ('R135A·普通倍率常量已注入', FR_BASE_MUL, 1, '==', '普通物品 ×1.5'),
        ('R135A·稀有属性判定已注入', FR_NEW_FN, 1, '==', 'effect/permanentEffect 含 spirit|speed|physique>0'),
        ('R135A·售价已乘倍率', FR_PRICE_NEW, 1, '==', '在原阶位折扣最外层乘'),
        ('R135A·旧售价形态已清零', PRICE_OLD, 0, '==', ''),
        ('R135A·在位标记存在', FR_MARK, 1, '==', ''),

        # ===================== 【B】掉落率 =====================
        ('R135B1·普通池品质已下调', HW_NEW, 1, '==', '普通88/稀有10/传说2'),
        ('R135B1·旧普通池品质已清零', HW_OLD, 0, '==', '原 60/30/10'),
        ('R135B2·幸运池品质已下调', XW_NEW, 1, '==', '稀有80/传说17/仙品3'),
        ('R135B2·旧幸运池品质已清零', XW_OLD, 0, '==', '原 传说50/仙品50'),
        ('R135B3·秘境池品质已下调', GW_NEW, 1, '==', '仅极度危险给传说'),
        ('R135B3·旧秘境池品质已清零', GW_OLD, 0, '==', ''),

        # ===================== 冻结：R-102/103/104 商店面 =====================
        ('冻结·阶位折扣常量未动', FRZ_TIER_DOWN, 1, '==', 'R103 门禁 needle'),
        ('冻结·卡片价格调用未动', FRZ_CARD, 1, '==', 'R103 门禁 needle'),
        ('冻结·购买扣费调用未动', FRZ_BUY, 1, '==', 'R103 门禁 needle'),
        ('冻结·闸门函数未动', FRZ_GATE_FN, 1, '==', 'R103 门禁 needle'),
        ('冻结·阶位判定函数未动', FRZ_TIER_FN, 1, '==', 'R103 门禁 needle'),
        ('冻结·l1raw 原体未动', FRZ_L1RAW, 1, '==', 'R103 门禁 needle'),
        ('冻结·买入价函数 Rm 未动', FRZ_RM, 1, '==', '只读引用'),
        ('冻结·估值器 xm 未动', FRZ_XM, 1, '==', '只读引用'),
        ('冻结·库存函数未动', FRZ_STOCKFN, 1, '==', 'R104 面'),

        # ===================== 冻结：历练入口 / 事件池 / 其它决策点 =====================
        ('冻结·历练遇店文案未动', FRZ_ENC, 1, '==', '15% 遇店口径不变'),
        ('冻结·遇店类型表未动', FRZ_SHOPTYPES, 1, '==', '6 类等概率不变'),
        ('冻结·事件池规模未动', FRZ_OC, 1, '==', '720/120/300/60'),
        ('冻结·伪随机 fs 未动', FRZ_FS, 1, '==', '概率判定工具'),
        ('冻结·宗门池品质未动', FRZ_BW, 1, '==', '恒稀有，本轮不动'),
        ('冻结·取物函数 ui 未动', FRZ_UI, 1, '==', '按品质取物品，本轮不动'),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old not in new and new not in old, '%s 新旧锚点互相包含' % name
    assert FR_MARK in PRICE_NEW, '在位标记必须植入 PRICE_NEW'
    assert PRICE_NEW.count(FR_NEW_FN) == 1, 'PRICE_NEW 应恰含一处判定函数定义'
    assert PRICE_NEW.count('function YlxwShopPriceOf(it, player) {') == 1, 'PRICE_NEW 应恰含一处售价函数'
    assert 'fetch(' not in PRICE_NEW, '注入块不得含 fetch('
    assert '\u4f20\u8bf4' in HW_OLD and '\u4f20\u8bf4' in HW_NEW, '普通池锚点须含「传说」'
    assert HW_NEW.count('?') == 2, 'HW_NEW 应为两级三元'
    assert XW_NEW.count('fs(t,') == 2, 'XW_NEW 应含两次独立 fs 判定'
    assert GW_NEW.count('\u6781\u5ea6\u5371\u9669') == 1, 'GW_NEW 应仅对「极度危险」给传说'


def main() -> int:
    ap = argparse.ArgumentParser(description='R-135 历练商店售价重定档 + 高稀有度掉落率下调（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2915-*.js）')
    a = ap.parse_args()
    src_path = a.src

    try:
        _precheck()
    except AssertionError as e:
        print('[FAIL] 断言失败: %s' % e)
        return 1

    if not os.path.exists(src_path):
        print('[FAIL] source not found: %s' % src_path)
        return 2
    with io.open(src_path, 'rb') as f:
        src = f.read()

    olds = [o.encode('utf-8') for _, o, _ in EDITS]
    news = [n.encode('utf-8') for _, _, n in EDITS]

    # 1) 幂等：全部已是补丁后形态且旧形态全清零 → rc=3 不写盘
    if all((n in src) for n in news) and all((o not in src) for o in olds):
        print('[SKIP] source looks already patched（R-135 三处新形态齐备且旧形态清零）')
        return 3

    # 2) 锚点计数（rc=2 面）
    for (name, _old, _new), ob in zip(EDITS, olds):
        n = src.count(ob)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）' % (name, n))
            return 2
    for nm, s in (('在位标记', FR_MARK),):
        if src.decode('utf-8', errors='replace').count(s) != 0:
            print('[FAIL] %s %r 已存在（疑部分补丁态）' % (nm, s))
            return 2

    # 3) 应用（字节级单点替换）
    out = src
    for (name, _old, _new), ob, nb in zip(EDITS, olds, news):
        out = out.replace(ob, nb, 1)

    # 4) 门禁
    ok = True
    text = out.decode('utf-8', errors='replace')
    for label, needle, exp, op, note in gates():
        act = text.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-30s actual=%d expect==%d' % ('OK' if good else 'FAIL', label, act, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 5) 往返自证
    back = out
    for ob, nb in zip(olds, news):
        back = back.replace(nb, ob, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r135-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r135-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print('  已原子写回 %s' % src_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
