# -*- coding: utf-8 -*-
r"""
yl_r013_ext.py — R-013「传承石可交易」客户端模块（角色系统）

========================================================================= 需求原文
  「传承系统中是不是系统已有"传承石"这种道具，把历练获得机缘这个事情改为获得
   "传承石"，并且这个传承石可以通过贸易上架交易，获取几率设置成跟中彩票几率
   差不多，让玩家获得这个自己不用时候可以售卖」

========================================================================= 侦察结论（构建产物 index-v2811-20260930.js 逐字实证）
  R1 「传承石」当前是**幽灵道具**：全产物仅 2 处出现，都在 @1632084 的商店池
      `AM=[...Lt("传承石")?[Ut("传承石",YlxwInhPriceOf(ae.QiRefining),...)]:[], ...]`。
      而 `Lt(name)` = `pi()` 建池后 `Fc.get(name)`；物品池由
      `ta/Zb/AN/Vn/En/on/Qn/Dm/Vr/ms/f3/Yr` 拼成，**这些池里都没有"传承石"**
      ⇒ `Lt("传承石")` 恒 null ⇒ `AM` 那项恒 `[]`（T7 §2.6 分层定价改的是一段死表达式）。
  R2 「历练获得机缘」= 幸运历练事件生成器 `function xw(t)` 内
      `inheritanceLevelChange:fs(t,.1,510)?1:void 0` —— 10% 直接 +1 传承等级。
  R3 事件池**有限且确定性**：`Oc={NORMAL:720,LUCKY:120,SECRET_REALM:300,SECT_CHALLENGE:60}`
      ⇒ 幸运事件恰好 120 个，`fs(t,r,a)=sa(t,a)<r=yy(t*1000+a)<r`（`yy(t)=frac(sin(t)*1e4)`）
      ⇒ 对给定 t 恒真/恒假。**故「彩票级掉率」绝不能写成 `fs(t,1e-5,510)`**
      （120×1e-5≈0.0012 ⇒ 期望命中 0 个事件 ⇒ 永不掉落）。原 10% 能生效正是因为
      0.1×120≈12 个事件带奖。
  R4 结算链路：`handleAdventure` → `Fm(type,...)` 抽事件 → `Ym(ev,...)` 缩放 →
      `await Fg({result:V,...,adventureType:Q,...})` → `Fg` 内 `c(k=>Pc(k,t,{...}))`。
      `Pc` 内 `S.inventory=KM(t.inventory,r,t)` 把 `r.itemsObtained`/`r.itemObtained`
      经 `vs()` 并入背包。`Fg` 是**唯一**的历练结算入口，且带 `adventureType` 形参。
  R5 交易行是**通用架构**：客户端 `handleListItem` 把背包任意物品的
      `{itemName,itemType,description,rarity,price,quantity,effect,isEquippable,
        equipmentSlot,advancedItemType,advancedItemId,itemSourceJson}` POST 到
      `/api/market/list`；服务端该端点**无物品白名单**（只校验 name 非空 + price>0）。
      上架候选列表 `Y` 只排除 locked/已装备 ⇒ 任何普通背包物品都可上架。
  R6 传承石「使用」分支已存在（T7 §2.4，@728802）：
      `if(r.name==="传承石"){...inheritanceLevel:Math.min(4,(t.inheritanceLevel||0)+1)}`
      ⇒ 掉落物只要 `name==="传承石"`，玩家即可用之 +1 传承等级，不用则可挂交易行。

========================================================================= 改法（4 处，锚点全部实测唯一）
  A 注入 3 个模块级符号（掉率常量 / 道具构造 / 结算掷骰），锚在
    `function YlxwPanelModal(p) {` 之前（与 T7 同区；该锚点在 `Fg`(@1710134)
    之前，且本块只依赖 Math.random 与字面量，无外部依赖）。
  B 删除幸运事件里的直接传承：`,inheritanceLevelChange:fs(t,.1,510)?1:void 0,` → `,`
    （「改为」= 替换，不是叠加；改后 `inheritanceLevelChange` 全文 5→4，
      仍 ≥1，T7 门禁『基线·历练获得传承仍在』不受影响）
  C 结算期掷骰：`Fg` 首行 `const $=t.hpChange||0;` 前插 `YlxwInhStoneRoll(t,m);`
    （`t`=本次奖励对象，`m`=adventureType；只在 `m==="lucky"` 时判定）
  D 传承面板静态说明文案改为与现状一致（T7 原文宣称「仙盟声望商店可换取传承石」，
    但该商店项是 R1 的死表达式；改为说明历练掉落 + 交易行转售）。

========================================================================= 掉率（2026-10-01 三次修订：换成「双色球二等奖」档）
  ★ 用户 2026-10-01 决定：「换成 11 个月那个」—— 上一版 1/17,721,088（双色球头奖）
    约 14 年一颗、太稀有；改为 **1/1,181,406**（= 双色球二等奖精确赔率）。

  周期 = 1.5s 结算展示 + 6s 冷却 ≈ 7.5s/次 ⇒ 480 次/小时 ⇒ 上限 345,600 次/月
  幸运占比 p = min(.30, .05 + idx*.02 + (lv-1)*.01 + luck*.001)
  月期望 = 345,600 × p × rate：
    · 极端 p=.30 ⇒ 0.0876/月 ≈ **11.4 个月一个**
    · 金丹  p≈.13 ⇒ 0.0380/月 ≈ 26.3 个月
    · 炼气  p=.05 ⇒ 0.0146/月 ≈ 68.4 个月
  ⇒ 「挂机党约一年一颗、低境界几年一颗」—— 稀有但可获得。
  ⇒ 若日后再调，**只改这一个常量即可**（`YlxwInhStoneRate`）。

========================================================================= 与既有模块的锚区关系
  · yl_t7legacy_ext.py：本模块**后置**于它（V28_MODULES 中 t7legacy 在 r013 之前）。
    T7 的门禁 `('基线·历练获得传承仍在','inheritanceLevelChange',1,'>=','不动')` 在本
    模块改后仍为 4 次 ⇒ 通过（但其 note「不动」的语义被 R-013 显式取代，见报告）。
    ★ 硬约束：本模块必须在 t7legacy **之后**装配（D 锚定 T7 产出的面板文案）。
  · yl_adv087_ext.py：锚区在战斗结算点/YLRF，与本模块零重叠。
  · 交易行/传承石使用分支：只读，未改。

========================================================================= 硬纪律
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS。
  · 不重新定义任何既有符号；新增符号一律 YlxwInh* 前缀。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py / chain_build.py / srv/index_v28.ts。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R013: 历练机缘 -> 掉落「传承石」（可上架交易行）=====
   掉率（2026-10-01 三次修订）= **1/1,181,406**（双色球二等奖精确赔率）。
   用户决定「换成 11 个月那个」——上一版 1/17,721,088（头奖）约 14 年一颗、太稀有。
   月期望（p=.30）≈ 0.0876 ⇒ 约 11.4 个月一个；命中走既有入包 + 日志链路。
   ★ 想再调只改这一个常量。 */
var YlxwInhStoneRate = 1 / 1181406;

/* 传承石：**不入物品池**（避免 ui() 随机掉落 / 声望商店刷出，破坏「≤1 个/月」）。
   直接构造为「材料 · 仙品」普通背包物品：
     · 名称含「石」⇒ ay() 归类为 材料(H.Material)，isEquippable=false
     · rarity=仙品 ⇒ Ym() 的 vg() 恒原样返回（不升阶、不被池内随机物替换）
     · 非装备 ⇒ Pc() 的 _ylf 过滤器恒放行；KM() 正常并入背包
     · 字段齐备 ⇒ 交易行上架端点与「使用传承石 +1 传承等级」两条链路天然可用 */
function YlxwInhStoneItem() {
  return { name: "传承石", type: "材料",
    description: "先辈传承凝结的灵石，使用后传承等级 +1，亦可于交易行转售。",
    rarity: "仙品", effect: {}, permanentEffect: {}, isEquippable: !1 };
}

/* 历练结算期掷骰（在 Fg 内、Pc 之前调用）：仅「幸运历练」判定，
   命中则把传承石追加进本次奖励的 itemsObtained，走既有入包 + 日志链路。 */
function YlxwInhStoneRoll(reward, advType) {
  if (!reward || advType !== "lucky") return;
  if (!(Math.random() < YlxwInhStoneRate)) return;
  reward.itemsObtained = [...(reward.itemsObtained || []), YlxwInhStoneItem()];
}
'''

# --------------------------------------------------------------------------- 锚点常量

# A 注入锚（module 级；Fg @1710134 在其后，函数声明提升 + 运行时调用，安全）
INJECT_ANCHOR = 'function YlxwPanelModal(p) {'

# B 旧「历练直接给传承等级」整段（含右侧逗号，保证删后语法完整）
XW_ANCHOR = ',inheritanceLevelChange:fs(t,.1,510)?1:void 0,'
XW_REPL = ','

# C 历练结算入口 Fg 首行（实测全文唯一）
FG_ANCHOR = 'const $=t.hpChange||0;'
FG_REPL = 'YlxwInhStoneRoll(t,m);const $=t.hpChange||0;'

# D 传承面板静态说明（T7 产出形态，转义串；改后不再宣称声望商店可换传承石）
PANEL_ANCHOR = (r'\u4ed9\u76df\u58f0\u671b\u5546\u5e97\u4ea6\u53ef\u6362\u53d6\u300c'
                r'\u4f20\u627f\u77f3\u300d\uff08\u6bcf\u5468\u9650 1 \u4e2a\uff09'
                r'\u2014\u2014\u4f20\u627f\u4e4b\u529b\u73cd\u8d35\uff0c\u5151\u6362'
                r'\u4ee3\u4ef7\u6781\u9ad8\uff0c\u8bf7\u8c28\u614e\u659f\u914c\u3002')
PANEL_REPL = (r'\u4f20\u627f\u77f3\u6781\u4e3a\u7a00\u6709\uff0c\u4ec5\u53ef\u4e8e'
              r'\u5386\u7ec3\u4e2d\u5076\u9047\u5148\u8f88\u673a\u7f18\u83b7\u5f97'
              r'\uff08\u6982\u7387\u6781\u4f4e\uff09\uff1b\u591a\u4f59\u7684\u4f20'
              r'\u627f\u77f3\u53ef\u4e8e\u4ea4\u6613\u884c\u4e0a\u67b6\u8f6c\u552e\u3002')


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 t7legacy）；
    ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r013 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # A) 注入 掉率常量 / 道具构造 / 结算掷骰
    p.insert_before('r013-helpers', INJECT_ANCHOR, blk.strip() + '\n', expect=1,
                    note='注入 YlxwInhStoneRate / YlxwInhStoneItem / YlxwInhStoneRoll')

    # B) 移除幸运历练的直接传承（「机缘」改为「传承石」掉落）
    p.replace('r013-drop-remove', XW_ANCHOR, XW_REPL, expect=1,
              note='xw(): 删 inheritanceLevelChange:fs(t,.1,510)?1:void 0')

    # C) 历练结算期掷骰（Fg 首行；仅 lucky 判定）
    p.replace('r013-drop-roll', FG_ANCHOR, FG_REPL, expect=1,
              note='Fg(): 首行前插 YlxwInhStoneRoll(t,m)')

    # D) 传承面板静态说明改为与现状一致
    p.replace('r013-panel-text', PANEL_ANCHOR, PANEL_REPL, expect=1,
              note='面板文案：声望商店可换传承石 -> 历练掉落 + 交易行转售')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= A 注入块 =================
        ('R013·掉率常量',            'YlxwInhStoneRate = 1 / 1181406',             1, '==', '双色球二等奖赔率（2026-10-01 三次修订）'),
        ('R013·旧掉率已清零',        'YlxwInhStoneRate = 1 / 120000',              0, '==', '旧值作废'),
        ('R013·旧头奖赔率已清零',    '1 / 17721088',                               0, '==', '上一版（14 年一颗）作废'),
        ('R013·道具构造函数',        'function YlxwInhStoneItem() {',              1, '==', ''),
        ('R013·结算掷骰函数',        'function YlxwInhStoneRoll(reward, advType) {', 1, '==', ''),
        ('R013·仅幸运历练判定',      'advType !== "lucky"',                        1, '==', ''),
        ('R013·传承石入包语句',      'reward.itemsObtained = [...(reward.itemsObtained || []), YlxwInhStoneItem()]', 1, '==', ''),
        ('R013·道具名=传承石',       zh('name: "传承石"'),                         1, '==', ''),
        ('R013·道具稀有度=仙品',     zh('rarity: "仙品", effect: {}'),              1, '==', 'vg 不升阶/不替换'),
        ('R013·道具类型=材料',       zh('name: "传承石", type: "材料"'),            1, '==', 'ay 归类 Material'),
        # ================= B 旧机制已移除 =================
        ('R013·旧历练给传承已移除',  'inheritanceLevelChange:fs(t,.1,510)?1:void 0', 0, '==', '改为掉落传承石'),
        ('R013·旧掉率字面量已消失',  'fs(t,.1,510)',                               0, '==', ''),
        # ================= C 结算挂骰 =================
        ('R013·Fg 首行挂骰',        'YlxwInhStoneRoll(t,m);const $=t.hpChange||0;', 1, '==', ''),
        # ================= D 面板文案 =================
        ('R013·面板新文案',          zh('可于交易行上架转售'),                     1, '>=', ''),
        ('R013·旧声望商店文案已消失', zh('仙盟声望商店亦可换取'),                   0, '==', ''),
        # ================= 基线守恒 =================
        ('基线·传承石使用分支仍在',  'r.name==="\\u4f20\\u627f\\u77f3"',            1, '==', 'T7 §2.4，使用即 +1 传承等级'),
        ('基线·传承石使用文案仍在',  zh('你使用了传承石，传承等级 +1'),             1, '>=', ''),
        ('基线·inheritanceLevelChange 仍在', 'inheritanceLevelChange',             4, '==', 'Ym×3 + Pc×1（原 5，删 xw 1）'),
        ('基线·历练结算入口仍在',    'async function Fg({result:t,',               1, '==', ''),
        ('基线·幸运事件池仍 120',    'LUCKY:120',                                  1, '==', '掉率不得写成 fs(t,r,510)'),
        ('基线·传承面板仍在',        zh('传承系统'),                               1, '>=', ''),
        ('基线·注入锚仍唯一',        INJECT_ANCHOR,                                1, '==', ''),
        # ================= 交易行只读（本模块不碰） =================
        ('基线·上架端点未动',        'market/list',                                1, '==', '服务端通用端点，无白名单'),
        ('基线·上架候选未加限制',    'a.inventory.filter(P=>!(P.locked||Object.values(a.equippedItems).includes(P.id)))', 1, '==', '任意背包物品可上架'),
    ]
    return gates
