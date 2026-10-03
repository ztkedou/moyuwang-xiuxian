# -*- coding: utf-8 -*-
r"""
yl_r142_ext.py — R-142 灵田稀有草是「白种」的（玩家暴击率/闪避/吸血死字段接线）

需求原文（台账 R-142）
--------------------------------------------------------------------------
  玩家在洞府灵田种出的稀有草，服用后服务端会把暴击率/闪避/吸血写进存档的玩家对象
  （srv/index_v28.ts 约 8453-8465 行，`sd.player[pc.key] = ...`）。服务端在**百分点**上
  计算、末尾 ÷100 落盘 ⇒ 存档里存的是**小数比例**（例如 0.06 表示 6%）。
  但**客户端战斗层从来不读这三个玩家字段** ⇒ 玩家辛苦种田种出来的稀有属性完全无效。

服务端侧上限（已在服务端钳制，本补丁不需要管）：
  FARM_CROP_ATTR_CAP = { hitRate: 8, critRate: 8, dodgeRate: 6, lifeLeech: 4 }  （百分点）

基线 = build/assets/index-v2917-20261003.js
       2,288,389 B / 2,121,765 chars（真中文 + \uXXXX 混排）
       md5 0470077292ba4ca446f92897257e0c54

==============================================================================
一、侦察结论（全部字符级实测 count，见脚本运行输出）
==============================================================================

【0】唯一有效注入点 = `YlxwBattleBonus(p)`（@1318584 一带，未压缩多行格式）
--------------------------------------------------------------------------
  该函数是战斗加成的**唯一聚合层**，链路：
    YlxwBattleBonus(p) → YlxwSpellBuffs(p) 把结果转成战斗 buff 数组
      （{id:"ylxw-rc", type:"crit", value:..., duration:9999} 等）
      → 注入回合制战斗玩家对象 buffs（注入点约 @777152：
         m.concat(typeof YlxwSpellBuffs==="function"?YlxwSpellBuffs(t):[])）
      → km/zy 读 buffs 消费。
  函数体顺序：羁绊五项累加 → `YlxwR18bRuneBattle(o, p);`（R-018b 灵纹）
              → 装备 reforgeAffixes ∪ innateAffixes 循环 → customSpells 循环
              → `return YlxwBattleCap(o);`
  ⇒ 在 `YlxwR18bRuneBattle(o, p);` 之后插入三行把 p 的三个字段累加进 o，
    末尾 `YlxwBattleCap(o)` 天然统一封顶。**只改这一处**。

【1】封顶不会撞顶（证明只需一处）
--------------------------------------------------------------------------
  YlxwBattleCapCfg = { critRate: 0.35, critDamage: 1.0, dodgeRate: 0.35,
                       lifeLeech: 0.25, damageReduction: 0.5 }
  灵田上限（小数比例）0.08 / 0.06 / 0.04 远低于封顶 0.35 / 0.35 / 0.25 ⇒ 不会撞顶。

【2】hitRate 无客户端消费点 ⇒ 不接线（明确结论 + grep 证据）
--------------------------------------------------------------------------
  在基线产物上 grep 计数实测：`hitRate` = **0 次**。
  ⇒ 客户端战斗**没有命中率机制**，没有任何消费点。本补丁**不为它发明机制**，
    只接线 critRate / dodgeRate / lifeLeech 三个有消费链路的字段。
  （因此本补丁注入的 JS 文本刻意**不含** `hitRate` 字样，以让门禁 'hitRate'==0 在
    补丁后依然成立——这正是「客户端无消费点」的机器可复核证据。）

==============================================================================
二、改动清单（1 处锚点，纯 ASCII，count==1）
==============================================================================
  锚点（ASCII 两行，实测 count==1）：
      '  YlxwR18bRuneBattle(o, p);\n  var eq = YlxwEqItems(p), i, j, af;'
  在锚点两行之间插入注释 + 三行累加，中文/缩进保持原样。

  ★ 不改：YlxwBattleCap / YlxwBattleCapCfg / 羁绊层 / R-018b 灵纹层 /
     装备层循环 / customSpells 循环 / 战斗核心公式 / 服务端 srv/**。

==============================================================================
三、契约（standalone · 同 localtest/yl_r141_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r142-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；
            1=断言失败或门禁/往返失败。
  · `gates()` 返回五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
  · 纯客户端；不改 srv/**、build_v26n.py、dryrun_087.py、其它 yl_*_ext.py、产物本体。
  · 不进 V28_MODULES（standalone）。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 锚点（ASCII，字符级实测 count==1）

ANCHOR_OLD = (
    '  YlxwR18bRuneBattle(o, p);\n'
    '  var eq = YlxwEqItems(p), i, j, af;'
)

# 在 YlxwR18bRuneBattle(o, p); 之后、装备层之前插入（注释 + 三行累加）
ANCHOR_NEW = (
    '  YlxwR18bRuneBattle(o, p);\n'
    '  /* YLXW_R142_V2918 R-142 灵田稀有草接线：服务端在 sd.player[pc.key] 写\n'
    '     critRate/dodgeRate/lifeLeech（服务端按百分点算、末尾 \u00f7100 落盘 ⇒ 存档存的是\n'
    '     小数比例，如 0.06 表示 6%）。此前客户端战斗层从不读这三个玩家字段 ⇒ 玩家辛苦种田\n'
    '     种出的稀有属性完全无效（死字段）。此处累加进 o，末尾由 YlxwBattleCap 统一封顶\n'
    '     （灵田上限 critRate 0.08 / dodgeRate 0.06 / lifeLeech 0.04 远低于封顶\n'
    '      0.35 / 0.35 / 0.25，不会撞顶）。命中率字段客户端无消费点，故不接线（见脚本注释）。 */\n'
    '  if (typeof p.critRate === "number" && p.critRate > 0) o.critRate += p.critRate;\n'
    '  if (typeof p.dodgeRate === "number" && p.dodgeRate > 0) o.dodgeRate += p.dodgeRate;\n'
    '  if (typeof p.lifeLeech === "number" && p.lifeLeech > 0) o.lifeLeech += p.lifeLeech;\n'
    '  var eq = YlxwEqItems(p), i, j, af;'
)

EDITS = [
    ('R142 灵田稀有草接线（YlxwBattleBonus 累加玩家字段）', ANCHOR_OLD, ANCHOR_NEW),
]

# --------------------------------------------------------------------------- 在位标记 / 新增 needle / 冻结门禁串

# ⚠️ 在位标记必须全局唯一且与既有标记互不包含（血泪教训：裸串会误判部分补丁态）。
#    实测：YLXW_R142_V2918 在基线 count==0；
#    与 YLXW_R140_V2916 / YLXW_R141_V2916 互不为子串。
MARK = 'YLXW_R142_V2918'

M_C1 = 'if (typeof p.critRate === "number" && p.critRate > 0) o.critRate += p.critRate;'
M_C2 = 'if (typeof p.dodgeRate === "number" && p.dodgeRate > 0) o.dodgeRate += p.dodgeRate;'
M_C3 = 'if (typeof p.lifeLeech === "number" && p.lifeLeech > 0) o.lifeLeech += p.lifeLeech;'
M_ANCHOR = 'YlxwR18bRuneBattle(o, p);'

# 冻结：封顶表 / 封顶函数 / 灵纹战斗层调用点 / 装备层循环 / hitRate 无消费点
FRZ_CAPCFG = 'var YlxwBattleCapCfg = { critRate: 0.35, critDamage: 1.0, dodgeRate: 0.35, lifeLeech: 0.25, damageReduction: 0.5 };'
FRZ_CAPFN = 'function YlxwBattleCap(o) {'
FRZ_EQ = 'var eq = YlxwEqItems(p), i, j, af;'
FRZ_R18B = 'YlxwR18bRuneBattle(o, p);'
FRZ_HITRATE = 'hitRate'  # 客户端无消费点：补丁前后均应为 0 次


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note) —— 供 dryrun 门禁表收录。"""
    return [
        ('R142·在位标记唯一存在', MARK, 1, '==', 'YLXW_R142_V2918'),
        ('R142·critRate 累加已注入', M_C1, 1, '==', ''),
        ('R142·dodgeRate 累加已注入', M_C2, 1, '==', ''),
        ('R142·lifeLeech 累加已注入', M_C3, 1, '==', ''),
        ('R142·灵纹锚点行仍唯一', M_ANCHOR, 1, '==', '插入点上下文'),
        ('冻结·YlxwBattleCapCfg 未动', FRZ_CAPCFG, 1, '==', '封顶值不变'),
        ('冻结·YlxwBattleCap 未动', FRZ_CAPFN, 1, '==', '统一封顶语义不变'),
        ('冻结·装备层循环未动', FRZ_EQ, 1, '==', ''),
        ('冻结·R-018b 灵纹层未动', FRZ_R18B, 1, '==', ''),
        ('冻结·hitRate 客户端无消费点', FRZ_HITRATE, 0, '==', '基线 grep=0，不接线'),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert ANCHOR_OLD != ANCHOR_NEW, '新旧锚点相同（恒等替换）'
    # 新增 needle 必须落在 NEW 内，且不在 OLD 内
    assert MARK in ANCHOR_NEW
    assert M_C1 in ANCHOR_NEW and M_C2 in ANCHOR_NEW and M_C3 in ANCHOR_NEW
    assert M_C1 not in ANCHOR_OLD and M_C2 not in ANCHOR_OLD and M_C3 not in ANCHOR_OLD
    # NEW 中每个新增 needle 恰出现一次
    assert ANCHOR_NEW.count(MARK) == 1, '在位标记在 NEW 中必须恰出现一次'
    assert ANCHOR_NEW.count(M_C1) == 1, 'critRate 累加行必须恰出现一次'
    assert ANCHOR_NEW.count(M_C2) == 1, 'dodgeRate 累加行必须恰出现一次'
    assert ANCHOR_NEW.count(M_C3) == 1, 'lifeLeech 累加行必须恰出现一次'
    # NEW 保留锚点原文（OLD 为 NEW 的前缀 + 后续行）
    assert ANCHOR_NEW.startswith('  YlxwR18bRuneBattle(o, p);\n')
    assert ANCHOR_NEW.endswith('  var eq = YlxwEqItems(p), i, j, af;')
    # 注入文本不得含 hitRate（保护 'hitRate'==0 门禁）
    assert FRZ_HITRATE not in ANCHOR_NEW, '注入文本不得含 hitRate（否则门禁 0 次不成立）'
    # 注入块不得引入网络调用
    assert 'fetch(' not in ANCHOR_NEW, '注入块不得含 fetch('


def _count(txt, needle):
    n, i = 0, 0
    while True:
        i = txt.find(needle, i)
        if i < 0:
            return n
        n += 1
        i += len(needle)


def _gate_ok(act, exp, op):
    if op == '==':
        return act == exp
    if op == '>=':
        return act >= exp
    if op == '<=':
        return act <= exp
    raise ValueError('unknown op: %r' % op)


def main() -> int:
    ap = argparse.ArgumentParser(description='R-142 灵田稀有草接线（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2917-*.js）')
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

    txt0 = src.decode('utf-8', errors='replace')

    # 1) 幂等：在位标记齐备 + 三行 needle 齐备 → rc=3 不写盘
    needles = [MARK, M_C1, M_C2, M_C3]
    if MARK in txt0:
        if all(m in txt0 for m in needles):
            print('[SKIP] source looks already patched（R-142 在位标记与新增 needle 齐备）')
            return 3
        print('[FAIL] 检测到部分补丁态（在位标记存在但新增 needle 不齐），拒绝写盘')
        return 2

    # 2) 锚点计数（rc=2 面）
    for (name, _old, _new), ob in zip(EDITS, olds):
        n = src.count(ob)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）' % (name, n))
            return 2
    # 新增 needle 在补丁前必须为 0（防重复注入 / 混入其它补丁）
    for nm, s in (('在位标记', MARK), ('critRate 累加行', M_C1),
                  ('dodgeRate 累加行', M_C2), ('lifeLeech 累加行', M_C3)):
        if txt0.count(s) != 0:
            print('[FAIL] %s %r 已存在（疑部分补丁态）' % (nm, s))
            return 2

    # 3) 应用（字节级单点替换）
    out = src
    for (name, _old, _new), ob, nb in zip(EDITS, olds, news):
        out = out.replace(ob, nb, 1)

    # 4) 门禁
    ok = True
    text = out.decode('utf-8', errors='replace')
    gs = gates()
    for label, needle, exp, op, note in gs:
        act = _count(text, needle)
        good = _gate_ok(act, exp, op)
        ok = ok and good
        print('  [%s] %-30s actual=%d expect%s%d %s' % (
            'OK' if good else 'FAIL', label, act, op, exp, note))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  门禁: %d/%d PASS, FAIL 0' % (len(gs), len(gs)))

    # 5) 往返自证
    back = out
    for ob, nb in zip(olds, news):
        back = back.replace(nb, ob, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1
    print('  往返自证: 新串→旧串 与源逐字节相同 OK')

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r142-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r142-', suffix='.tmp')
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
