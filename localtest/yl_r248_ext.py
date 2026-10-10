# -*- coding: utf-8 -*-
r"""
yl_r248_ext.py — R-248 钩子层：R-247「先手 / 淬体 / 逆修」三机制的**消费钩子**（纯客户端 · 多点 EDIT）

需求原文（台账 R-247「钩子层」工单 · 2026-10-11）
--------------------------------------------------------------------------
  唯一真相源 = `策划_R247_三机制接口冻结_20261011.md`（本文件**只按它实现**）：
    · §2 字段名（逐字冻结）：firstStrike / nixiuExp / nixiuDef /
      cuitiAttack / cuitiDefense / cuitiHp / cuitiPhysique / cuitiSpirit / cuitiSpeed
    · §3 落点（逐字锚点）：先手 km/zy/历练快速结算；逆修 bd().total + xt() 防御链；淬体 xt() 属性汇总
    · §5 消费通道：新增 helper `YlxwR247Mech(p)`（模块作用域，命名固定），遍历 p.cultivationArts
      的已习得功法 effects，把 §2 字段**求和**；整函数 try/catch 异常返回全 0；**模块级缓存 + 失效判定**
      （照 yl_r238_ext.py 的 YLXW_WUDAO_CULT 写法，避免每帧遍历）。
    · §5：**不修改** yl_r245_ext.py 的 YlxwR245Mech / YlxwBattleBonus / YlxwSpellBuffs（已验证上游）。
      本批**自带** helper，在各自消费点直接读取。

三个机制（§1）
--------------------------------------------------------------------------
  · 先手 firstStrike ：战斗**首回合**伤害 +X%      → km / zy / 历练快速结算首击
  · 淬体 cuiti*      ：**每次突破**永久 +X 属性    → xt() 属性汇总（× breakthroughCount）
  · 逆修 nixiuExp/Def：**修炼 +X% 但防御 −Y%**（双向）→ bd().total（+）/ xt()（−）

取值来源与「首回合」判据
--------------------------------------------------------------------------
  · 回合制（km/zy）：`t` 为战斗状态，`t.round` 为回合数（初始化 round:1；自增 r.round+=1）。
    首回合判据 `r==="player" && t.round<=1`（r = 出手方）。
  · 历练快速结算（X0）：**没有回合概念** ⇒ 首击判据用 `R.length===0`（R = 战报数组，每迭代 push 一条）。
  · ★ 战斗单元 `QS(t)` 不带 `cultivationArts`（只带 YlxwSpellBuffs 推出的 buffs）⇒ 回合制侧
    `YlxwR247Mech(t.player)` 走**缓存回退**（缓存由 xt()/bd()/X0() 以真实玩家预热，见下）。
    这是「模块级缓存」在本环的核心用途：让战斗侧无需玩家引用即可读到机制值。

★ 有意为之（规格 §3.2 修订版）
--------------------------------------------------------------------------
  · 逆修防御扣减**落在 `xt(t)` 属性汇总末尾**（与淬体加成同一处），**不在** `if(goldenCoreMethodCount>0)`
    块内 —— 否则只有带金丹法门的玩家才吃扣减（语义错误）。
  · `xt()` 是**单一来源**，被战斗与显示共用（39 个调用点）⇒ 逆修防御扣减使**显示与战斗同步下降**
    （一致性好），但也会降低秘境/道合的实力估算。**这是有意为之**（「逆修」就该是面板可见的代价）。

★ 落点内顺序（本环自定，规格未强制；已在此写明）
--------------------------------------------------------------------------
  · `xt()` 末尾同一 `try{…}catch{}` 块内：**先加淬体加成，再乘逆修扣减**。
    理由：规格 §3.2 把逆修防御定义为「属性汇总**末尾**」= 所有防御来源（含淬体永久属性）累加完之后
    的最终面板值上扣减 ⇒ 逆修代价对全部防御来源一致生效，与 §3.2「防御累加链末尾」语义一致。
    （若反过来先乘再加，则淬体那部分防御不受逆修扣减，与「末尾」定义不符。）
  · `nixiuDef<=0` 时**严格无操作**（`if(_r248nd>0)` 短路，不产生 `*1` 之外的浮点误差）。

已知边界（规格 §3.3）
--------------------------------------------------------------------------
  · 淬体收益 = `cuiti<Attr> × t.statistics.breakthroughCount`；**转世**会重建玩家对象、不携带
    `statistics` ⇒ 淬体收益归零（与现状 permGain 同）。

不做（有意 · 工单边界 §6）
--------------------------------------------------------------------------
  · 不改数据层（yl_r247_ext.py 的 is[] effects 一字不动）。
  · 不碰 /*[r241enl]*/ /*[r243hook]*/ /*[r244body]*/ /*[r245combat]*/ /*[r188med]*/ /*[r239life]*/
    以及六源（心法/天赋/称号/洞府/协同/羁绊）算式与权重、离线收益。
  · 不碰 build_v26n.py / dryrun_087.py / 任何 build/assets/* / 其它 yl_*_ext.py。

==============================================================================
契约（照 localtest/yl_r245_ext.py 同型）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node 语义实跑）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r248-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；1=其它错误。
  · `gates()` 返回 5 元组 (label, needle, expect_count, op, note)。
  · 全部锚点**运行时**从 bundle 取，并断言 count==1（不硬编码长字面量）。
  · 新代码**纯 ASCII**（规避「裸 UTF-8 / \uXXXX 混合态」坑）；锚点已用 repr() 逐字确认。
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*[r248mech]*/'

# --------------------------------------------------------------------------- E0 新增代码块（纯 ASCII）
HELPER_BLOCK = (
    MARK + ' /* R-248 hook layer for R-247 mechanics (first-strike / body-temper / reverse-cultivation).\n'
    '   Sums firstStrike / nixiuExp / nixiuDef / cuiti* over learned arts\' effects (data: R-247).\n'
    '   Pure reader; never mutates data. Module-level cache keyed by arts signature (avoids per-frame walk).\n'
    '   Every path is guarded; failures are swallowed and yield an all-zero object. */\n'
    'var YLXW_R247_MECH = null, YLXW_R247_SIG = null;\n'
    'function YlxwR247Zero() {\n'
    '  return { firstStrike: 0, nixiuExp: 0, nixiuDef: 0, cuitiAttack: 0, cuitiDefense: 0,\n'
    '           cuitiHp: 0, cuitiPhysique: 0, cuitiSpirit: 0, cuitiSpeed: 0 };\n'
    '}\n'
    'function YlxwR247Mech(p) {\n'
    '  try {\n'
    '    var ids = (p && p.cultivationArts) || null;\n'
    '    if (!ids) { return YLXW_R247_MECH || YlxwR247Zero(); }\n'
    '    var sig = "", i;\n'
    '    for (i = 0; i < ids.length; i++) { sig += ids[i] + ","; }\n'
    '    if (YLXW_R247_MECH && sig === YLXW_R247_SIG) { return YLXW_R247_MECH; }\n'
    '    var o = YlxwR247Zero(), a, e, k, v;\n'
    '    var KEYS = ["firstStrike", "nixiuExp", "nixiuDef", "cuitiAttack", "cuitiDefense",\n'
    '                "cuitiHp", "cuitiPhysique", "cuitiSpirit", "cuitiSpeed"];\n'
    '    for (i = 0; i < ids.length; i++) {\n'
    '      a = null;\n'
    '      try { a = is.find(function (x) { return x.id === ids[i]; }); } catch (e0) { a = null; }\n'
    '      if (!a || !a.effects) continue;\n'
    '      e = a.effects;\n'
    '      for (k = 0; k < KEYS.length; k++) { v = Number(e[KEYS[k]]); if (v > 0) o[KEYS[k]] += v; }\n'
    '    }\n'
    '    YLXW_R247_MECH = o; YLXW_R247_SIG = sig;\n'
    '    return o;\n'
    '  } catch (e1) { return YlxwR247Zero(); }\n'
    '}\n'
)

# --------------------------------------------------------------------------- 锚点（在 index-v2956-20261010.js 上字符级实测 count==1）
# E0 助手注入点（模块作用域；函数声明提升，可被 bd/xt/km/zy/X0 调用）
DECL_OLD = 'function bd(t){'
DECL_NEW = HELPER_BLOCK + DECL_OLD

# E1 先手 · km（回合制普攻）：在「减伤」之后插首回合加成（r==="player" && t.round<=1）
KM_OLD = 'M>0&&(_=Math.round(_*(1-M)));'
KM_SEG = ('var _r248fs=YlxwR247Mech(t.player).firstStrike;'
          'r==="player"&&t.round<=1&&_r248fs>0&&(_=Math.round(_*(1+_r248fs)));')
KM_NEW = KM_OLD + KM_SEG

# E2 先手 · zy（回合制技能）：在「斩杀」之后插首回合加成
ZY_OLD = '_r245ex>0&&d.maxHp>0&&d.hp<=.3*d.maxHp&&(f=Math.round(f*(1+_r245ex)));'
ZY_SEG = ('var _r248fs=YlxwR247Mech(t.player).firstStrike;'
          'r==="player"&&t.round<=1&&_r248fs>0&&(f=Math.round(f*(1+_r248fs)));')
ZY_NEW = ZY_OLD + ZY_SEG

# E3a 先手 · 历练快速结算（X0）：在 const 链里声明 _r248fs（t 即玩家）
FZ_OLD = 'Z=YlxwDOD?0:bo(G?x.attack:m.attack,G?m.defense*(1-YlxwPB.armorPenRate):x.defense),'
FZ_NEW = FZ_OLD + '_r248fs=YlxwR247Mech(t).firstStrike,'

# E3b 先手 · 历练快速结算：IIFE 内按 R.length===0（首击）加成
#   ★ 采用「前置插入」形态（old 作为 new 的后缀）⇒ 满足「old 是 new 子串」的往返自证不变式
FX_OLD = ('return (!G&&!YlxwDOD&&YlxwPB.damageReduction>0)?'
          'Math.round(v*(1-Math.min(.6,YlxwPB.damageReduction))):v;})')
FX_NEW = ('if(G&&R.length===0&&_r248fs>0)v=Math.round(v*(1+_r248fs));' + FX_OLD)

# E4 逆修 · bd() 修炼加成：return 之前求 __nixiu，total 追加 +__nixiu
BD_OLD = 'return{total:_ar+_ta+_ti+_gr+_sy+_np+__wud'
BD_NEW = 'var __nixiu=YlxwR247Mech(t).nixiuExp;return{total:_ar+_ta+_ti+_gr+_sy+_np+__wud+__nixiu'

# E5 淬体 + 逆修防御 · xt() 属性汇总末尾（同一 try 块）
#   ★ 规格 §3.2 修订版：逆修防御扣减**移出** `if(goldenCoreMethodCount>0)` 块，落在属性汇总末尾。
#     原锚点 `r.defense+=Tr(t.defense,c,d)` 位于金丹块内 ⇒ 只有金丹玩家才吃扣减（语义错误）。
#     现与淬体加成合并到同一处（§3.3 的落点）。
#   ★ 顺序：先加淬体加成 → 再乘逆修扣减（理由见文件头「落点内顺序」）。
#   ★ nixiuDef<=0 时严格无操作（if(_r248nd>0) 短路）。
CT_OLD = 'typeof YlxwStatExtras==="function"&&YlxwStatExtras(t,r);'
CT_BLOCK = (
    'try{var _r248bc=Math.floor((t.statistics&&t.statistics.breakthroughCount)||0);'
    'var _r248c=YlxwR247Mech(t);'
    'if(_r248bc>0){'
    'r.attack+=Math.floor((_r248c.cuitiAttack||0)*_r248bc);'
    'r.defense+=Math.floor((_r248c.cuitiDefense||0)*_r248bc);'
    'r.maxHp+=Math.floor((_r248c.cuitiHp||0)*_r248bc);'
    'r.spirit+=Math.floor((_r248c.cuitiSpirit||0)*_r248bc);'
    'r.physique+=Math.floor((_r248c.cuitiPhysique||0)*_r248bc);'
    'r.speed+=Math.floor((_r248c.cuitiSpeed||0)*_r248bc);}'
    'var _r248nd=Number(_r248c.nixiuDef)||0;'
    'if(_r248nd>0)r.defense=Math.round(r.defense*(1-_r248nd));'
    '}catch(_r248e){}'
)
CT_NEW = CT_BLOCK + CT_OLD


# --------------------------------------------------------------------------- 替换表（E0..E5 · 7 处）
def build_reps():
    return [
        ('E0 助手声明（YlxwR247Mech 聚合器，bd 定义前）', DECL_OLD, DECL_NEW),
        ('E1 先手·km 首回合加成', KM_OLD, KM_NEW),
        ('E2 先手·zy 首回合加成', ZY_OLD, ZY_NEW),
        ('E3a 先手·历练 声明 _r248fs', FZ_OLD, FZ_NEW),
        ('E3b 先手·历练 首击(R.length===0)加成', FX_OLD, FX_NEW),
        ('E4 逆修·bd().total 追加 +__nixiu', BD_OLD, BD_NEW),
        ('E5 淬体+逆修防御·xt() 属性汇总末尾（同一 try 块）', CT_OLD, CT_NEW),
    ]


REPS = build_reps()

# --------------------------------------------------------------------------- 冻结针脚（本环一律不动）
FREEZE = [
    ('/*[r241enl]*/', 1),
    ('/*[r243hook]*/', 1),
    ('/*[r244body]*/', 1),
    ('/*[r245combat]*/', 1),
    ('/*[r188med]*/', 1),
    ('/*[r239life]*/', 1),
    # 六源权重式（心法/天赋/称号/洞府/协同/羁绊）
    ('const _ar=r*d,_ta=a*0.26,_ti=l*0.6,_gr=c*0.6,_sy=Math.min(b,0.1),_np=S*0.32;', 1),
    # 悟道禅道并入点（R-238）
    ('YlxwWudaoCultEnsure();var __wud=YlxwWudaoCultPct();', 1),
    # km 既有吸血（R-245 上游未动）
    ('w.lifeLeech&&w.lifeLeech>0&&(l.hp=Math.min(l.maxHp,l.hp+Math.floor(_*w.lifeLeech)))', 1),
    # km 既有反震链（R-245 上游未动）
    ('w.reflectDamage&&w.reflectDamage>h&&(h=w.reflectDamage)', 1),
    # r245 既有钩子（km 斩杀 / 历练斩杀 / 历练反震）
    ('_r245ex>0&&c.maxHp>0&&c.hp<=.3*c.maxHp&&(_=Math.round(_*(1+_r245ex)))', 1),
    ('if(G&&YlxwPB.executeRate>0&&m.maxHp>0&&m.hp<=.3*m.maxHp)', 1),
    ('!G&&X>0&&YlxwPB.reflectDamage>0', 1),
    # 历练防御入参（r245 破甲形态未动）
    ('Z=YlxwDOD?0:bo(G?x.attack:m.attack,G?m.defense*(1-YlxwPB.armorPenRate):x.defense)', 1),
    # ★ 规格 §3.2 修订：逆修防御**不再**落在金丹块内 ⇒ 该块必须逐字未动（证明已移出）
    ('r.attack+=Tr(t.attack,c,d),r.defense+=Tr(t.defense,c,d),r.maxHp+=Tr(t.maxHp,c,d)', 1),
]


# --------------------------------------------------------------------------- 门禁
def gates(out):
    g = []
    g.append(('幂等标记唯一', MARK, 1, '==', ''))
    # 新钩子必须在位
    g.append(('先手·km 表达式', KM_SEG, 1, '==', ''))
    g.append(('先手·zy 表达式', ZY_SEG, 1, '==', ''))
    g.append(('先手·历练 声明', '_r248fs=YlxwR247Mech(t).firstStrike,', 1, '==', ''))
    g.append(('先手·历练 首击', 'if(G&&R.length===0&&_r248fs>0)v=Math.round(v*(1+_r248fs))', 1, '==', ''))
    g.append(('逆修·bd total 追加', '_sy+_np+__wud+__nixiu', 1, '==', ''))
    g.append(('逆修·xt 防御扣减（属性汇总末尾）',
              'var _r248nd=Number(_r248c.nixiuDef)||0;if(_r248nd>0)r.defense=Math.round(r.defense*(1-_r248nd));', 1, '==', ''))
    g.append(('逆修·nixiuDef<=0 严格无操作', 'if(_r248nd>0)r.defense=', 1, '==', '短路，不产生 *1 浮点误差'))
    g.append(('逆修·已移出金丹块', 'r.defense+=Tr(t.defense,c,d),r.defense=', 0, '==', '不得再落在金丹块内'))
    g.append(('淬体·xt 攻击', 'r.attack+=Math.floor((_r248c.cuitiAttack||0)*_r248bc)', 1, '==', ''))
    g.append(('淬体·xt 根骨', 'r.physique+=Math.floor((_r248c.cuitiPhysique||0)*_r248bc)', 1, '==', ''))
    g.append(('顺序·先淬体后逆修',
              '*_r248bc);}var _r248nd=Number(_r248c.nixiuDef)||0;', 1, '==', '先加淬体、再乘逆修'))
    # 值来源 / 容错 / 缓存
    g.append(('聚合器·声明', 'function YlxwR247Mech(p) {', 1, '==', ''))
    g.append(('聚合器·全 0 兜底', 'function YlxwR247Zero() {', 1, '==', ''))
    g.append(('聚合器·异常静默', 'catch (e1) { return YlxwR247Zero(); }', 1, '==', ''))
    g.append(('聚合器·缓存位', 'YLXW_R247_MECH', 3, '>=', '声明/读/写'))
    g.append(('聚合器·失效判定', 'sig === YLXW_R247_SIG', 1, '==', ''))
    return g


def _precheck():
    assert MARK == '/*[r248mech]*/'
    assert len(REPS) == 7, 'REPS 应为 7 条（E0..E5；逆修防御已并入淬体的 xt 末尾块）'
    olds = [r[1] for r in REPS]
    assert len(set(olds)) == len(olds), '锚点重复'
    for label, old, new in REPS:
        assert old and new and old != new, '%s 锚点非法' % label
        assert old in new, '%s 必须为「追加式」（old 是 new 的子串，便于往返自证）' % label
        assert all(ord(ch) < 128 for ch in new), '%s 新串必须纯 ASCII' % label
        assert all(ord(ch) < 128 for ch in old), '%s 旧串必须纯 ASCII' % label
    assert 'firstStrike' in HELPER_BLOCK and 'nixiuDef' in HELPER_BLOCK and 'cuitiSpeed' in HELPER_BLOCK
    return True


def _classify(txt):
    return 'patched' if MARK in txt else 'baseline'


def _apply_reps(txt):
    """返回 (out, err)。"""
    out = txt
    for label, old, new in REPS:
        c = out.count(old)
        if c != 1:
            return None, '%s 锚点出现 %d 次（期望 1）' % (label, c)
        out = out.replace(old, new, 1)
    return out, None


# --------------------------------------------------------------------------- node 工具
def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    node = _find_node()
    if not node:
        print('  [WARN] 未找到 node，跳过 node --check')
        return True, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
        r = subprocess.run([node, '--check', tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            print('  [FAIL] node --check 未通过:\n%s' % r.stderr.decode('utf-8', 'replace')[:2000])
            return False, node
        return True, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# --------------------------------------------------------------------------- 语义实跑（--selftest）
def _semantic_selftest(out_text):
    """从补丁后文本抽出真实钩子片段 + 真实 YlxwR247Mech，包成 function 在 node 真跑。"""
    helper = out_text[out_text.index(MARK):out_text.index(DECL_OLD)]
    FX_SEG = 'if(G&&R.length===0&&_r248fs>0)v=Math.round(v*(1+_r248fs));'
    BD_SEG = 'var __nixiu=YlxwR247Mech(t).nixiuExp;'
    ND_SEG = 'var _r248nd=Number(_r248c.nixiuDef)||0;if(_r248nd>0)r.defense=Math.round(r.defense*(1-_r248nd));'

    def _grab(seg):
        """从**补丁后文本**逐字抽出该片段（不信任常量副本）。"""
        i = out_text.find(seg)
        return out_text[i:i + len(seg)]

    for name, seg in (('KM_SEG', KM_SEG), ('ZY_SEG', ZY_SEG), ('FZ_NEW', FZ_NEW),
                      ('FX_SEG', FX_SEG), ('BD_SEG', BD_SEG), ('ND_SEG', ND_SEG),
                      ('CT_BLOCK', CT_BLOCK)):
        if seg not in out_text:
            print('  [FAIL] 片段缺失: %s' % name)
            return False
    km_seg, zy_seg, fx_seg = _grab(KM_SEG), _grab(ZY_SEG), _grab(FX_SEG)
    bd_seg, nd_seg, ct_block = _grab(BD_SEG), _grab(ND_SEG), _grab(CT_BLOCK)

    harness = (
        helper + '\n'
        'var is = [\n'
        '  { id: "art-fs",  effects: { firstStrike: 0.5 } },\n'
        '  { id: "art-fs2", effects: { firstStrike: 0.25 } },\n'
        '  { id: "art-nxe", effects: { nixiuExp: 0.6 } },\n'
        '  { id: "art-nxd", effects: { nixiuDef: 0.25 } },\n'
        '  { id: "art-mix", effects: { cuitiDefense: 10, nixiuDef: 0.5 } },\n'
        '  { id: "art-ct",  effects: { cuitiAttack: 2, cuitiDefense: 3, cuitiHp: 20, '
        'cuitiPhysique: 1, cuitiSpirit: 4, cuitiSpeed: 5 } }\n'
        '];\n'
        'var P_FS = { cultivationArts: ["art-fs"] };\n'
        'var P_ZERO = { cultivationArts: ["art-none"] };\n'
        'var P_NXE = { cultivationArts: ["art-nxe"] };\n'
        'var P_NXD = { cultivationArts: ["art-nxd"] };\n'
        'var P_SUM = { cultivationArts: ["art-fs", "art-fs2"] };\n'
        'var P_EMPTY = { cultivationArts: [] };\n'
        'function kmSeg(t, r, _) { ' + km_seg + ' return _; }\n'
        'function zySeg(t, r, f) { ' + zy_seg + ' return f; }\n'
        'function bdSeg(t, base) { ' + bd_seg + ' return base + __nixiu; }\n'
        'function xtSeg(t, r) { ' + ct_block + ' return r; }\n'
        'function ndSeg(t, def) { var r = { defense: def }; var _r248c = YlxwR247Mech(t); '
        + nd_seg + ' return r.defense; }\n'
        'function zeroAttrs() { return { attack: 0, defense: 0, maxHp: 0, spirit: 0, physique: 0, speed: 0 }; }\n'
        'function defP(arts, bc, gcm) { return { cultivationArts: arts, '
        'statistics: { breakthroughCount: bc }, goldenCoreMethodCount: gcm }; }\n'
        'var R = {};\n'
        # (1) 先手：round=1 vs round=2；firstStrike=0 时两者相等
        'YlxwR247Mech(P_FS);\n'
        'R.fs_r1 = kmSeg({ round: 1, player: {} }, "player", 100);\n'
        'R.fs_r2 = kmSeg({ round: 2, player: {} }, "player", 100);\n'
        'R.zy_r1 = zySeg({ round: 1, player: {} }, "player", 100);\n'
        'R.zy_r2 = zySeg({ round: 2, player: {} }, "player", 100);\n'
        'YlxwR247Mech(P_ZERO);\n'
        'R.fs0_r1 = kmSeg({ round: 1, player: {} }, "player", 100);\n'
        'R.fs0_r2 = kmSeg({ round: 2, player: {} }, "player", 100);\n'
        # (2) 逆修：nixiuExp 抬高 bd().total；nixiuDef 压低 xt().defense（与金丹无关）；互不干扰
        'R.bd_base = bdSeg(P_ZERO, 1);\n'
        'R.bd_nxe  = bdSeg(P_NXE, 1);\n'
        'R.def_noop = ndSeg(P_ZERO, 1234);\n'
        'R.def_base = xtSeg(defP(["art-none"], 0, 0), { defense: 1000 }).defense;\n'
        'R.def_nxd_gcm0 = xtSeg(defP(["art-nxd"], 0, 0), { defense: 1000 }).defense;\n'
        'R.def_nxd_gcm5 = xtSeg(defP(["art-nxd"], 0, 5), { defense: 1000 }).defense;\n'
        'R.bd_nxd = bdSeg(P_NXD, 1);\n'
        'R.def_nxe = xtSeg(defP(["art-nxe"], 0, 0), { defense: 1000 }).defense;\n'
        # (3) 淬体：breakthroughCount 0 vs 10 的属性差 == 10 × cuiti<Attr>
        'var c0  = xtSeg(defP(["art-ct"], 0, 0), zeroAttrs());\n'
        'var c10 = xtSeg(defP(["art-ct"], 10, 0), zeroAttrs());\n'
        'R.cuiti_diff = { attack: c10.attack - c0.attack, defense: c10.defense - c0.defense, '
        'maxHp: c10.maxHp - c0.maxHp, spirit: c10.spirit - c0.spirit, '
        'physique: c10.physique - c0.physique, speed: c10.speed - c0.speed };\n'
        # (3b) 顺序：基防200 + 淬体(cuitiDefense10×bc10=100) = 300，再逆修 ×(1-0.5) => 150
        'R.order_def = xtSeg(defP(["art-mix"], 10, 0), '
        '{ defense: 200, attack: 0, maxHp: 0, spirit: 0, physique: 0, speed: 0 }).defense;\n'
        # (4) 聚合器：多部求和 / 未知功法 / 空数组
        'R.agg_sum = YlxwR247Mech(P_SUM);\n'
        'R.agg_unknown = YlxwR247Mech({ cultivationArts: ["nope"] });\n'
        'R.agg_empty = YlxwR247Mech(P_EMPTY);\n'
        'console.log(JSON.stringify(R));\n'
    )

    node = _find_node()
    if not node:
        print('  [WARN] 未找到 node，跳过语义实跑')
        return True
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(harness.encode('utf-8'))
        r = subprocess.run([node, tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            print('  [FAIL] 语义实跑 node 退出码 %d:\n%s'
                  % (r.returncode, r.stderr.decode('utf-8', 'replace')[:2000]))
            return False
        data = json.loads(r.stdout.decode('utf-8', 'replace').strip().splitlines()[-1])
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

    def close(a, b, tol=1e-9):
        return abs(a - b) < tol

    ok = True
    # ① 先手
    print('  [语义] 先手: fs=0.5 round1=%s > round2=%s ? %s'
          % (data['fs_r1'], data['fs_r2'], data['fs_r1'] > data['fs_r2']))
    ok = ok and data['fs_r1'] == 150 and data['fs_r2'] == 100
    print('  [语义] 先手·zy: round1=%s > round2=%s ? %s'
          % (data['zy_r1'], data['zy_r2'], data['zy_r1'] > data['zy_r2']))
    ok = ok and data['zy_r1'] == 150 and data['zy_r2'] == 100
    print('  [语义] 先手: fs=0   round1=%s == round2=%s ? %s'
          % (data['fs0_r1'], data['fs0_r2'], data['fs0_r1'] == data['fs0_r2']))
    ok = ok and data['fs0_r1'] == 100 and data['fs0_r2'] == 100
    # ② 逆修
    print('  [语义] 逆修: bd base=%s -> nixiuExp=%s（变大）；def base=%s -> nixiuDef=%s（变小）'
          % (data['bd_base'], data['bd_nxe'], data['def_base'], data['def_nxd_gcm0']))
    ok = ok and close(data['bd_base'], 1.0) and close(data['bd_nxe'], 1.6)
    ok = ok and close(data['def_base'], 1000) and close(data['def_nxd_gcm0'], 750)
    print('  [语义] 逆修·与金丹无关: goldenCoreMethodCount=0 -> %s ；=5 -> %s（应都=750）'
          % (data['def_nxd_gcm0'], data['def_nxd_gcm5']))
    ok = ok and close(data['def_nxd_gcm0'], 750) and close(data['def_nxd_gcm5'], 750)
    print('  [语义] 逆修·严格无操作: nixiuDef=0 时 def=%s（应=1234，整数无浮点漂移）' % data['def_noop'])
    ok = ok and data['def_noop'] == 1234
    print('  [语义] 逆修·互不干扰: bd(nixiuDef only)=%s（应=1，不受影响）；def(nixiuExp only)=%s（应=1000，不受影响）'
          % (data['bd_nxd'], data['def_nxe']))
    ok = ok and close(data['bd_nxd'], 1.0) and close(data['def_nxe'], 1000)
    # ③ 淬体
    cd = data['cuiti_diff']
    exp = {'attack': 20, 'defense': 30, 'maxHp': 200, 'spirit': 40, 'physique': 10, 'speed': 50}
    print('  [语义] 淬体: bc=0 vs bc=10 属性差=%s（应=%s = 10×cuiti<Attr>）' % (cd, exp))
    ok = ok and all(cd[k] == exp[k] for k in exp)
    print('  [语义] 顺序·先淬体后逆修: 基防200+淬体100=300，再×(1-0.5) => %s（应=150；若先乘后加则为200）'
          % data['order_def'])
    ok = ok and data['order_def'] == 150
    # ④ 聚合器
    agg = data['agg_sum']
    print('  [语义] 聚合器·多部求和: firstStrike=%s（应=0.75 = 0.5+0.25）' % agg['firstStrike'])
    ok = ok and close(agg['firstStrike'], 0.75)
    zeros = ('firstStrike', 'nixiuExp', 'nixiuDef', 'cuitiAttack', 'cuitiDefense',
             'cuitiHp', 'cuitiPhysique', 'cuitiSpirit', 'cuitiSpeed')
    unk_ok = all(data['agg_unknown'][k] == 0 for k in zeros)
    emp_ok = all(data['agg_empty'][k] == 0 for k in zeros)
    print('  [语义] 聚合器·未知功法=%s（全 0? %s）；空数组=%s（全 0? %s）'
          % (data['agg_unknown'], unk_ok, data['agg_empty'], emp_ok))
    ok = ok and unk_ok and emp_ok
    return ok


# --------------------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description='R-248 钩子层：R-247 先手/淬体/逆修 消费钩子')
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()

    try:
        _precheck()
    except AssertionError as e:
        print('[FAIL] 断言失败: %s' % e)
        return 1

    if not os.path.exists(a.src):
        print('[FAIL] source not found: %s' % a.src)
        return 2

    with io.open(a.src, 'rb') as f:
        src_bytes = f.read()
    txt0 = src_bytes.decode('utf-8', 'replace')

    if _classify(txt0) == 'patched':
        print('[SKIP] source looks already patched（R-248 三机制消费钩子已在位）')
        return 3

    out, err = _apply_reps(txt0)
    if err is not None:
        print('[FAIL] %s' % err)
        return 2

    # 门禁
    ok = True
    for label, needle, exp, op, note in gates(out):
        act = out.count(needle)
        good = (act >= exp) if op == '>=' else (act == exp)
        ok = ok and good
        if not good:
            print('  [FAIL] %-40s actual=%d expect %s%d' % (label, act, op, exp))
    for needle, cnt in FREEZE:
        act = out.count(needle)
        good = (act == cnt)
        ok = ok and good
        if not good:
            print('  [FAIL] 冻结 %-30s actual=%d expect %d' % (needle[:30], act, cnt))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  [OK] 门禁全绿（%d 替换点；冻结 %d 项）' % (len(REPS), len(FREEZE)))

    # 往返自证
    back = out
    for label, old, new in REPS:
        back = back.replace(new, old, 1)
    if back != txt0:
        print('[FAIL] round-trip mismatch：除改动点外字节被改动')
        return 1
    print('  [OK] 往返自证一致（逆向还原逐字节相等）')

    out_bytes = out.encode('utf-8')
    print('  delta = %+d bytes  (%d -> %d)'
          % (len(out_bytes) - len(src_bytes), len(src_bytes), len(out_bytes)))

    nok, node = _node_check(out)
    if not nok:
        print('[FAIL] node --check 失败，未写盘')
        return 1
    print('  [OK] node --check 通过 (%s)' % (node or 'skipped'))

    if a.selftest:
        print('  [语义] 开始 node 语义实跑（抽取真实钩子片段）...')
        if not _semantic_selftest(out):
            print('[FAIL] 语义实跑未通过')
            return 1
        print('  [OK] 语义实跑通过')

    if a.check or a.selftest:
        print('[r248] check OK: 先手/逆修/淬体 三钩子在位、门禁全绿、往返一致')
        return 0

    # .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = a.src + '.bak-r248-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src_bytes)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(a.src)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r248-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out_bytes)
        os.replace(tmp, a.src)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print('  已原子写回 %s' % a.src)
    return 0


if __name__ == '__main__':
    sys.exit(main())
