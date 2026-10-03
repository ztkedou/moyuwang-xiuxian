# -*- coding: utf-8 -*-
r"""
yl_r140b_ext.py — R-140 消耗品数值重构 · 经济部分（批 1）+ 永久属性硬顶机制（批 2）

唯一真源：docs/0.9.17-design/R140-消耗品数值重构.md
本脚本只实现其中属于「批 1 经济」与「批 2 硬顶」的锚点：
  §4  售价        → 清单 #8
  §5  掉率        → 清单 #9 / #10
  §3.4 硬顶机制   → 清单 #11 / #12 / #13(仅门禁) / #14
  §8.2 存档兼容   → permGain ?? {} 迁移

不属于本脚本（由同批其它成员负责，本脚本不碰）：
  #1 fg / #2 Rr,mw / #3 Ic / #4 DN / #5 yg / #6 丹药表 / #7 草药表 / #15 game-dicts / #16 死键

基线 = build/assets/index-v2916-20261003.js（2,285,822 B，md5 a59ac4496ab0e8ab81fdb147b45488ec）
所有锚点均已在该基线上逐字复核，count==1。

==============================================================================
改动清单（14 处锚点）
==============================================================================
【批 1 · 售价】@1811587 附近
  A1  新增品质阶梯常量 YLXW_R140_CONSUM_PRICE_MUL（普通1.5/稀有3/传说6/仙品12）
      + YLXW_R140_CONSUM_PRICE_KEYS=["丹药","草药"]
  A2  YlxwShopPriceOf 出口：消耗品（type==="丹药"||"草药"）走品质阶梯；
      装备/其它类型走【原 R-135 二元三元式，逐字不动】（保 R-141 装备经济逐位不变）

【批 1 · 掉率】§5.2
  B1  hw 普通历练   .88/.98 → .92/.99   （普通92/稀有7/传说1）
  B2  xw 大机缘     .8/.85  → .88/.90   （稀有88/传说10.8/仙品1.2）
  B3  gw 秘境掉落门 .6 → .45
  B4  bw 宗门掉落门 .4 → .30
  B5  vg 升档率     .05+u*.35 → .02+u*.15

【批 2 · 硬顶】§3.4
  C1  $r 递减下限   0.25 → 0.10
  C2  ZS 声明前注入常量 YLXW_R140_PERM_CAP_RATIO=1.0 + 助手 YlxwR140PermRoom / YlxwR140AddPerm
  C3  六个永久属性分支（attack/defense/spirit/physique/speed/maxHp）改为硬顶调用；
      初始化 u.permGain={...(u.permGain||{})}
  C4  存档归一化：permGain:t.permGain||{}（旧档 undefined → {}，零崩溃）

==============================================================================
契约（standalone · 同 localtest/yl_r135_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r140b-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · `gates()` 返回五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
  · 不进 V28_MODULES（standalone，由装配层 apply_standalone() 套用）。
  · 纯客户端；不改 srv/**、build_v26n.py、CHANGELOG*、其它 yl_*_ext.py、产物本体。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 在位标记

MARK = 'YLXW_R140B_V2916'   # ★ 带 B 的裸串：与 r140a 的 '/*YLXW_R140_V2916*/'、r141 的 'YLXW_R141_V2916' 互不包含（集成时实测：旧裸串 'YLXW_R140_V2916' 是 r140a 标记的子串 ⇒ 串行叠加误判部分补丁态）

# =========================================================================== 【A1】售价常量
A1_OLD = 'var YLXW_R135_RARE_KEYS = ["spirit", "speed", "physique"];'
A1_NEW = (
    A1_OLD + '\n'
    '/* YLXW_R140B_V2916[r140b] R-140 batch1: consumable price ladder (Pill/Herb only). */\n'
    '/* == YL_R140 == Consumables get a rarity ladder; equipment keeps the R-135 x6/x1.5\n'
    '   ternary verbatim (else-branch) so R-141 equipment economy is bit-identical. */\n'
    'var YLXW_R140_CONSUM_PRICE_MUL = { "普通": 1.5, "稀有": 3, "传说": 6, "仙品": 12 };\n'
    'var YLXW_R140_CONSUM_PRICE_KEYS = ["丹药", "草药"];'
)

# =========================================================================== 【A2】售价分支
A2_OLD = (
    '  var mul = YlxwR135HasRareAttr(it) ? YLXW_R135_RARE_PRICE_MUL : YLXW_R135_BASE_PRICE_MUL;\n'
    '  return Math.max(1, Math.ceil(base * mul));'
)
A2_NEW = (
    '  var isConsum = !!(it && (it.type === "丹药" || it.type === "草药"));\n'
    '  var mul;\n'
    '  if (isConsum) {\n'
    '    mul = YLXW_R140_CONSUM_PRICE_MUL[it.rarity] || YLXW_R140_CONSUM_PRICE_MUL["普通"];\n'
    '  } else {\n'
    '    mul = YlxwR135HasRareAttr(it) ? YLXW_R135_RARE_PRICE_MUL : YLXW_R135_BASE_PRICE_MUL;\n'
    '  }\n'
    '  return Math.max(1, Math.ceil(base * mul));'
)

# =========================================================================== 【B1】hw 普通历练
B1_OLD = 'l=sa(t,1),c=l<.88?"普通":l<.98?"稀有":"传说",d=vy();'
B1_NEW = 'l=sa(t,1),c=l<.92?"普通":l<.99?"稀有":"传说",d=vy();'

# =========================================================================== 【B2】xw 大机缘
B2_OLD = 'j=fs(t,.8,460)?"稀有":fs(t,.85,461)?"传说":"仙品"'
B2_NEW = 'j=fs(t,.88,460)?"稀有":fs(t,.90,461)?"传说":"仙品"'

# =========================================================================== 【B3】gw 秘境掉落门
B3_OLD = 'itemObtained:fs(t,.6,580)?ui(v,t):void 0'
B3_NEW = 'itemObtained:fs(t,.45,580)?ui(v,t):void 0'

# =========================================================================== 【B4】bw 宗门掉落门
B4_OLD = 'itemObtained:fs(t,.4,670)?ui("稀有",t):void 0'
B4_NEW = 'itemObtained:fs(t,.30,670)?ui("稀有",t):void 0'

# =========================================================================== 【B5】vg 升档率
B5_OLD = 'const m=.05+u*.35'
B5_NEW = 'const m=.02+u*.15'

# =========================================================================== 【C1】$r 递减下限
C1_OLD = 'const d=Math.max(.25,Math.min(1,c/l));'
C1_NEW = 'const d=Math.max(.10,Math.min(1,c/l));'

# =========================================================================== 【C2】ZS 前注入硬顶常量 + 助手
#   注意：ZS/$r/Ig 是**同一条逗号分隔的 const 声明**（const ZS=...,$r=...,Ig=...），
#   不能在中间插入语句；因此助手定义放在整条声明**之前**（语句级），函数体在服用时才求值。
C2_OLD = 'const ZS=(t,r)=>{const a=Cs[t.realm]||Cs[ae.QiRefining]'
C2_DEFS = (
    '/* R-140 batch2: per-attribute permanent-gain hard cap. */\n'
    'var YLXW_R140_PERM_CAP_RATIO = 1.0;\n'
    'function YlxwR140PermRoom(p, key) {\n'
    '  var cap = YLXW_R140_PERM_CAP_RATIO * ZS(p, key);\n'
    '  var used = (p.permGain && Number(p.permGain[key])) || 0;\n'
    '  return Math.max(0, cap - used);\n'
    '}\n'
    'function YlxwR140AddPerm(p, key, raw, label, logs, isBatch, addLog, itemName) {\n'
    '  var g = $r(p, key, raw);\n'
    '  var g2 = Math.min(g, YlxwR140PermRoom(p, key));\n'
    '  if (g2 > 0) {\n'
    '    p.permGain = p.permGain || {};\n'
    '    p.permGain[key] = (Number(p.permGain[key]) || 0) + g2;\n'
    '    p[key] = (Number(p[key]) || 0) + g2;\n'
    '    if (key === "maxHp") p.hp = (Number(p.hp) || 0) + g2;\n'
    '    logs.push(label + "永久 +" + g2 + (g2 < raw ? "（原值 +" + raw + "，按当前属性折算）" : ""));\n'
    '  } else if (!isBatch) {\n'
    '    addLog("【" + itemName + "】的" + label + "增益已达本境界上限，未生效。", "normal");\n'
    '  }\n'
    '}\n'
)
C2_NEW = C2_DEFS + C2_OLD

# =========================================================================== 【C3】六分支硬顶
C3_ATK_OLD = (
    'if(r.permanentEffect&&!r.isEquippable){const h=[],R=r.permanentEffect;'
    'if(R.attack){const E=$r(u,"attack",R.attack);u.attack+=E,'
    'h.push(`攻击力永久 +${E}${E<R.attack?"（原值 +"+R.attack+"，按当前属性折算）":""}`)}'
)
C3_ATK_NEW = (
    'if(r.permanentEffect&&!r.isEquippable){const h=[],R=r.permanentEffect;'
    'u.permGain={...(u.permGain||{})};'
    'if(R.attack)YlxwR140AddPerm(u,"attack",R.attack,"攻击力",h,d,l,r.name);'
)

C3_DEF_OLD = (
    'if(R.defense){const E=$r(u,"defense",R.defense);u.defense+=E,'
    'h.push(`防御力永久 +${E}${E<R.defense?"（原值 +"+R.defense+"，按当前属性折算）":""}`)}'
)
C3_DEF_NEW = 'if(R.defense)YlxwR140AddPerm(u,"defense",R.defense,"防御力",h,d,l,r.name);'

C3_SPI_OLD = (
    'if(R.spirit){const E=$r(u,"spirit",R.spirit);u.spirit+=E,'
    'h.push(`神识永久 +${E}${E<R.spirit?"（原值 +"+R.spirit+"，按当前属性折算）":""}`)}'
)
C3_SPI_NEW = 'if(R.spirit)YlxwR140AddPerm(u,"spirit",R.spirit,"神识",h,d,l,r.name);'

C3_PHY_OLD = (
    'if(R.physique){const E=$r(u,"physique",R.physique);u.physique+=E,'
    'h.push(`体魄永久 +${E}${E<R.physique?"（原值 +"+R.physique+"，按当前属性折算）":""}`)}'
)
C3_PHY_NEW = 'if(R.physique)YlxwR140AddPerm(u,"physique",R.physique,"体魄",h,d,l,r.name);'

C3_SPD_OLD = (
    'if(R.speed){const E=$r(u,"speed",R.speed);u.speed+=E,'
    'h.push(`身法永久 +${E}${E<R.speed?"（原值 +"+R.speed+"，按当前属性折算）":""}`)}'
)
C3_SPD_NEW = 'if(R.speed)YlxwR140AddPerm(u,"speed",R.speed,"身法",h,d,l,r.name);'

C3_MHP_OLD = (
    'if(R.maxHp){const E=$r(u,"maxHp",R.maxHp);u.maxHp+=E,u.hp+=E,'
    'h.push(`气血上限永久 +${E}${E<R.maxHp?"（原值 +"+R.maxHp+"，按当前属性折算）":""}`)}'
)
C3_MHP_NEW = 'if(R.maxHp)YlxwR140AddPerm(u,"maxHp",R.maxHp,"气血上限",h,d,l,r.name);'

# =========================================================================== 【C4】存档迁移
C4_OLD = 'alchemyProficiency:t.alchemyProficiency||t.alchemyExp||0,'
C4_NEW = C4_OLD + 'permGain:t.permGain||{},'

EDITS = [
    ('R140-A1 售价品质阶梯常量', A1_OLD, A1_NEW),
    ('R140-A2 售价分支（消耗品阶梯/装备沿用R135）', A2_OLD, A2_NEW),
    ('R140-B1 hw 普通历练 88/10/2→92/7/1', B1_OLD, B1_NEW),
    ('R140-B2 xw 大机缘 80/17/3→88/10.8/1.2', B2_OLD, B2_NEW),
    ('R140-B3 gw 秘境掉落门 .6→.45', B3_OLD, B3_NEW),
    ('R140-B4 bw 宗门掉落门 .4→.30', B4_OLD, B4_NEW),
    ('R140-B5 vg 升档率 .05+.35u→.02+.15u', B5_OLD, B5_NEW),
    ('R140-C1 $r 递减下限 .25→.10', C1_OLD, C1_NEW),
    ('R140-C2 ZS 声明前注入硬顶常量+助手', C2_OLD, C2_NEW),
    ('R140-C3a attack 硬顶 + permGain 初始化', C3_ATK_OLD, C3_ATK_NEW),
    ('R140-C3b defense 硬顶', C3_DEF_OLD, C3_DEF_NEW),
    ('R140-C3c spirit 硬顶', C3_SPI_OLD, C3_SPI_NEW),
    ('R140-C3d physique 硬顶', C3_PHY_OLD, C3_PHY_NEW),
    ('R140-C3e speed 硬顶', C3_SPD_OLD, C3_SPD_NEW),
    ('R140-C3f maxHp 硬顶', C3_MHP_OLD, C3_MHP_NEW),
    ('R140-C4 存档迁移 permGain||{}', C4_OLD, C4_NEW),
]

# --------------------------------------------------------------------------- 门禁串（补丁后形态）
FR_MARK = MARK
FR_PRICE_MUL = 'var YLXW_R140_CONSUM_PRICE_MUL = { "普通": 1.5, "稀有": 3, "传说": 6, "仙品": 12 };'
FR_PRICE_KEYS = 'var YLXW_R140_CONSUM_PRICE_KEYS = ["丹药", "草药"];'
FR_PRICE_BRANCH = 'var isConsum = !!(it && (it.type === "丹药" || it.type === "草药"));'
FR_PRICE_CONSUM_LINE = 'mul = YLXW_R140_CONSUM_PRICE_MUL[it.rarity] || YLXW_R140_CONSUM_PRICE_MUL["普通"];'
FR_R135_TERNARY = 'YlxwR135HasRareAttr(it) ? YLXW_R135_RARE_PRICE_MUL : YLXW_R135_BASE_PRICE_MUL'
FR_R135_RARE_MUL = 'var YLXW_R135_RARE_PRICE_MUL = 6;'
FR_R135_BASE_MUL = 'var YLXW_R135_BASE_PRICE_MUL = 1.5;'
FR_PRICE_FN = 'function YlxwShopPriceOf(it, player) {'

FR_CAP_RATIO = 'var YLXW_R140_PERM_CAP_RATIO = 1.0;'
FR_CAP_ROOM = 'function YlxwR140PermRoom(p, key) {'
FR_CAP_ADD = 'function YlxwR140AddPerm(p, key, raw, label, logs, isBatch, addLog, itemName) {'
FR_CAP_INIT = 'u.permGain={...(u.permGain||{})};'
FR_CAP_ATK = 'if(R.attack)YlxwR140AddPerm(u,"attack",R.attack,"攻击力",h,d,l,r.name);'
FR_CAP_MHP = 'if(R.maxHp)YlxwR140AddPerm(u,"maxHp",R.maxHp,"气血上限",h,d,l,r.name);'
FR_SR_NEW = 'const d=Math.max(.10,Math.min(1,c/l));'
FR_SR_OLD = 'const d=Math.max(.25,Math.min(1,c/l));'
FR_SAVE_MIG = 'permGain:t.permGain||{},'

# 冻结：R-140 明确不改 / 必须逐位保留
FRZ_ZS = 'const ZS=(t,r)=>{const a=Cs[t.realm]||Cs[ae.QiRefining]'
FRZ_LIFE = 'if(R.maxLifespan&&(u.maxLifespan=(u.maxLifespan??100)+R.maxLifespan'
FRZ_ROOTS = 'R.spiritualRoots){const E={metal:"金",wood:"木",water:"水",fire:"火",earth:"土"}'
FRZ_GW_QUAL = 'v=a==="极度危险"?"传说":"稀有"'
FRZ_FS = 'function fs(t,r,a=0){return sa(t,a)<r}'
FRZ_UI = 'function ui(t,r){const a=pi();'
FRZ_OC = 'Oc={NORMAL:720,LUCKY:120,SECRET_REALM:300,SECT_CHALLENGE:60}'
FRZ_TIER_DOWN = 'var YLXW_SHOP_TIER_DOWN = 0.6;'
FRZ_CARD = 'const A=YlxwShopPriceOf(w,l),'
FRZ_BUY = 'const _=YlxwShopPriceOf(R,N)*E;'
FRZ_IG_HEAD = 'Ig=(t,r,a)=>{var x,T,$,M;'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note) —— 供 dryrun 门禁表收录。"""
    return [
        # ===================== 【A】售价 =====================
        ('R140A·品质阶梯常量已注入', FR_PRICE_MUL, 1, '==', '普通1.5/稀有3/传说6/仙品12'),
        ('R140A·消耗品类型键已注入', FR_PRICE_KEYS, 1, '==', '["丹药","草药"]'),
        ('R140A·消耗品判定分支已注入', FR_PRICE_BRANCH, 1, '==', 'type===丹药||草药'),
        ('R140A·消耗品走品质阶梯', FR_PRICE_CONSUM_LINE, 1, '==', ''),
        ('R140A·装备沿用R135三元（逐字）', FR_R135_TERNARY, 1, '==', '装备行为逐位不变'),
        ('R140A·R135稀有倍率字面量仍在', FR_R135_RARE_MUL, 1, '==', ''),
        ('R140A·R135基础倍率字面量仍在', FR_R135_BASE_MUL, 1, '==', ''),
        ('R140A·售价函数结构未变', FR_PRICE_FN, 1, '==', ''),
        ('R140A·旧二元出口已清零', A2_OLD, 0, '==', ''),
        ('R140A·在位标记存在', FR_MARK, 1, '==', ''),

        # ===================== 【B】掉落率 =====================
        ('R140B1·普通池品质已收紧', B1_NEW, 1, '==', '普通92/稀有7/传说1'),
        ('R140B1·旧普通池品质已清零', B1_OLD, 0, '==', 'R135 88/10/2'),
        ('R140B2·大机缘品质已收紧', B2_NEW, 1, '==', '稀有88/传说10.8/仙品1.2'),
        ('R140B2·旧大机缘品质已清零', B2_OLD, 0, '==', 'R135 80/17/3'),
        ('R140B3·秘境掉落门已下调', B3_NEW, 1, '==', '.6→.45'),
        ('R140B3·旧秘境掉落门已清零', B3_OLD, 0, '==', ''),
        ('R140B4·宗门掉落门已下调', B4_NEW, 1, '==', '.4→.30'),
        ('R140B4·旧宗门掉落门已清零', B4_OLD, 0, '==', ''),
        ('R140B5·升档率已减半', B5_NEW, 1, '==', '.05+.35u→.02+.15u'),
        ('R140B5·旧升档率已清零', B5_OLD, 0, '==', ''),

        # ===================== 【C】硬顶 =====================
        ('R140C1·$r下限已降至.10', FR_SR_NEW, 1, '==', ''),
        ('R140C1·旧$r下限已清零', FR_SR_OLD, 0, '==', ''),
        ('R140C2·硬顶比例常量已注入', FR_CAP_RATIO, 1, '==', '1.0 × ZS'),
        ('R140C2·余量助手已注入', FR_CAP_ROOM, 1, '==', ''),
        ('R140C2·累加助手已注入', FR_CAP_ADD, 1, '==', ''),
        ('R140C3·permGain 已初始化', FR_CAP_INIT, 1, '==', '浅拷贝防污染入参'),
        ('R140C3·attack 分支已硬顶化', FR_CAP_ATK, 1, '==', ''),
        ('R140C3·maxHp 分支已硬顶化', FR_CAP_MHP, 1, '==', ''),
        ('R140C3·旧 attack 结算块已清零', C3_ATK_OLD, 0, '==', ''),
        ('R140C3·旧 maxHp 结算块已清零', C3_MHP_OLD, 0, '==', ''),
        ('R140C4·存档迁移已注入', FR_SAVE_MIG, 1, '==', '旧档 undefined → {}'),

        # ===================== 冻结 =====================
        ('冻结·ZS 未动（被 Ig 调用）', FRZ_ZS, 1, '==', '§3.4② 复用'),
        ('冻结·maxLifespan 分支未动', FRZ_LIFE, 1, '==', '§3.4⑤ 本轮不做'),
        ('冻结·spiritualRoots 分支未动', FRZ_ROOTS, 1, '==', 'R4 灵根不动'),
        ('冻结·gw 品档未动', FRZ_GW_QUAL, 1, '==', '仅下调掉落门'),
        ('冻结·伪随机 fs 未动', FRZ_FS, 1, '==', ''),
        ('冻结·取物 ui 未动', FRZ_UI, 1, '==', ''),
        ('冻结·事件池规模未动', FRZ_OC, 1, '==', '720/120/300/60'),
        ('冻结·阶位折扣常量未动', FRZ_TIER_DOWN, 1, '==', 'R103 面'),
        ('冻结·卡片价格调用未动', FRZ_CARD, 1, '==', 'R103 面'),
        ('冻结·购买扣费调用未动', FRZ_BUY, 1, '==', 'R103 面'),
        ('冻结·Ig 函数头未动', FRZ_IG_HEAD, 1, '==', ''),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert new not in old, '%s 新锚点被旧锚点包含' % name
        if not name.startswith('R140-A1') and not name.startswith('R140-C4') \
                and not name.startswith('R140-C2'):
            assert old not in new, '%s 旧锚点被新锚点包含' % name
    # A1 / C4 属「前缀追加」型：旧锚点必为新锚点前缀
    assert A1_NEW.startswith(A1_OLD), 'A1 应为前缀追加'
    assert C4_NEW.startswith(C4_OLD), 'C4 应为前缀追加'
    assert MARK in A1_NEW, '在位标记须植入 A1_NEW'
    assert A1_NEW.count(FR_PRICE_MUL) == 1 and A1_NEW.count(FR_PRICE_KEYS) == 1
    assert C2_NEW.count(FR_CAP_ROOM) == 1 and C2_NEW.count(FR_CAP_ADD) == 1
    assert C2_NEW.count('const ZS=(t,r)=>{const a=Cs[t.realm]||Cs[ae.QiRefining]') == 1, \
        'C2_NEW 应恰含一处 ZS 声明头（助手须在语句级前置）'
    assert C2_NEW.count('function YlxwR140AddPerm') == 1, 'C2_NEW 应恰含一处累加助手定义'
    # 六个硬顶调用点齐备
    for key in ('attack', 'defense', 'spirit', 'physique', 'speed', 'maxHp'):
        assert ('YlxwR140AddPerm(u,"%s"' % key) in (
            C3_ATK_NEW + C3_DEF_NEW + C3_SPI_NEW + C3_PHY_NEW + C3_SPD_NEW + C3_MHP_NEW
        ), '缺 %s 硬顶调用点' % key
    # A2 装备分支逐字保留 R-135 三元
    assert FR_R135_TERNARY in A2_NEW, 'A2 装备分支须逐字保留 R-135 三元'
    assert A2_NEW.count('YLXW_R140_CONSUM_PRICE_MUL[it.rarity]') == 1
    assert 'fetch(' not in A2_NEW and 'fetch(' not in C2_NEW, '注入块不得含 fetch('
    # 掉率新常量与 §5.2 逐字一致
    assert B1_NEW == 'l=sa(t,1),c=l<.92?"普通":l<.99?"稀有":"传说",d=vy();'
    assert B2_NEW == 'j=fs(t,.88,460)?"稀有":fs(t,.90,461)?"传说":"仙品"'
    assert B5_NEW == 'const m=.02+u*.15'


def simulate_cap():
    """R-140 §3.4 算例 A 的纯 Python 复现：炼气期 L1 连吃 100 颗九转金丹。

    用「批 1 后」的九转金丹数值（perm 经新 Ic ×0.8、新 yg 地板 Rr=40 后）与
    本脚本的 ZS/$r/cap 逻辑，输出每颗后的 attack 增量。返回 (final, rows)。
    """
    cs = {'baseMaxHp': 100, 'baseAttack': 10, 'baseDefense': 5,
          'baseSpirit': 5, 'basePhysique': 10, 'baseSpeed': 10}
    realm_level = 1
    ratio = 1.0

    def ZS(key):
        c = 1 + (max(1, realm_level) - 1) * 0.14
        d = cs['baseMaxHp'] if key == 'maxHp' else cs['base' + key[0].upper() + key[1:]]
        floor = 300 if key == 'maxHp' else 60
        return max(floor, int(d * 1.35 * c))

    def sr(p, key, a):
        if not (a > 0):
            return 0
        l = p.get(key, 0) or 0
        c = ZS(key)
        if l <= c:
            return int(a)
        d = max(0.10, min(1, c / l))
        return max(1, int(a * d))

    def cap(key):
        return ratio * ZS(key)

    # 九转金丹（批1 后）：perm 经新 Ic(perm×0.8) → ×0.8；经新 yg(Rr=40) 地板 → max(v,40)
    raw_perm = {'attack': 120, 'defense': 120, 'spirit': 20, 'physique': 20, 'speed': 20}
    gains = {}
    for k, v in raw_perm.items():
        v = int(v * 0.8)
        gains[k] = max(v, 40)

    p = {'attack': 10, 'defense': 5, 'spirit': 5, 'physique': 10, 'speed': 10}
    pg = {}
    rows = []
    for n in range(1, 101):
        delta = {}
        for k in ('attack', 'defense', 'spirit', 'physique', 'speed'):
            g = sr(p, k, gains[k])
            room = max(0, cap(k) - pg.get(k, 0))
            g2 = min(g, room)
            if g2 > 0:
                p[k] += g2
                pg[k] = pg.get(k, 0) + g2
            delta[k] = g2
        if n <= 4 or n in (5, 10, 100):
            rows.append((n, dict(p), dict(delta), dict(pg)))
    return {'attack': p['attack'], 'cap_attack': cap('attack'), 'rows': rows,
            'ZS_attack': ZS('attack'), 'gain_attack': gains['attack']}


def main() -> int:
    ap = argparse.ArgumentParser(
        description='R-140 消耗品经济（售价/掉率）+ 永久属性硬顶（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2916-*.js）')
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

    text = src.decode('utf-8', errors='replace')
    patched = (MARK in text)

    if patched:
        # 已补丁：全部新形态齐备且关键旧形态清零 → 幂等 rc=3；否则疑部分补丁态 → rc=2
        cleared = [A2_OLD, B1_OLD, B2_OLD, B3_OLD, B4_OLD, B5_OLD, C1_OLD,
                   C3_ATK_OLD, C3_DEF_OLD, C3_SPI_OLD, C3_PHY_OLD, C3_SPD_OLD, C3_MHP_OLD]
        if all(n in text for n in [A1_NEW, A2_NEW, B1_NEW, B2_NEW, B3_NEW, B4_NEW, B5_NEW,
                                   C1_NEW, C2_NEW, C3_ATK_NEW, C3_DEF_NEW, C3_SPI_NEW,
                                   C3_PHY_NEW, C3_SPD_NEW, C3_MHP_NEW, C4_NEW]) \
                and all(c not in text for c in cleared):
            print('[SKIP] source looks already patched（R-140 全 16 处新形态齐备且旧形态清零）')
            return 3
        print('[FAIL] 在位标记 %r 存在但补丁形态不完整（疑部分补丁态）' % MARK)
        return 2

    # 锚点计数（rc=2 面）
    for (name, _old, _new), ob in zip(EDITS, olds):
        n = src.count(ob)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）' % (name, n))
            return 2

    # 应用（字节级单点替换）
    out = src
    for ob, nb in zip(olds, news):
        out = out.replace(ob, nb, 1)

    # 门禁
    ok = True
    out_text = out.decode('utf-8', errors='replace')
    for label, needle, exp, op, note in gates():
        act = out_text.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-34s actual=%d expect==%d' % ('OK' if good else 'FAIL', label, act, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 往返自证
    back = out
    for ob, nb in zip(olds, news):
        back = back.replace(nb, ob, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r140b-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r140b-', suffix='.tmp')
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
