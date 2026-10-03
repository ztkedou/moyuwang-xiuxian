# -*- coding: utf-8 -*-
r"""
yl_r143_ext.py — R-143 用技能打怪不吸血（技能伤害补吸血分支）

需求原文（台账 R-143）
--------------------------------------------------------------------------
  回合制战斗里「普通攻击」有吸血分支，但「技能」没有 ⇒ 用技能打怪不回血。
  0.9.17 刚实装的「噬元（吸血）」装备词条对偏好技能输出的玩家收益直接对折。
  本补丁把 km() 的吸血语义补进 zy()（技能结算函数）。

基线 = build/assets/index-v2917-20261003.js
       2,288,389 B / 2,121,495 chars
       md5 0470077292ba4ca446f92897257e0c54

==============================================================================
一、侦察结论（字符级实测，全部 count==1）
==============================================================================

【1】普通攻击 `function km(t,r,a)` @779350（1835 字符）—— 已有吸血分支：
      c.hp=Math.max(0,Math.floor(c.hp-_));
      r==="player"&&_>0&&l.buffs.forEach(function(w){
        w.lifeLeech&&w.lifeLeech>0&&(l.hp=Math.min(l.maxHp,l.hp+Math.floor(_*w.lifeLeech)))});
      · `l` = 攻击方（r==="player"?t.player:t.enemy），`_` = 本次伤害。

【2】技能 `function zy(t,r,a,l)` @781185（2890 字符，单行压缩）—— 无吸血分支：
      · c = 施法者（r==="player"?t.player:t.enemy）
      · d = 目标  （l==="player"?t.player:t.enemy）
      · f = 本次技能最终伤害（顶部 `let f=0`，在 if(u.damage){...} 内算出）
      · m = 反弹伤害
      伤害结算 + 反弹段落（if(u.damage){...} 块末尾、块闭合 } 之前）：
        if(d.hp=Math.max(0,Math.floor(d.hp-f)),f>0&&d.buffs.some(A=>A.reflectDamage&&A.reflectDamage>0)){const A=Math.max(...d.buffs.filter(I=>I.reflectDamage&&I.reflectDamage>0).map(I=>I.reflectDamage));A>0&&(m=Math.floor(f*A),c.hp=Math.max(0,Math.floor(c.hp-m)))}

【3】唯一注入点 = 上述结算段之后（仍在 if(u.damage){...} 内）。
      ⇒ 锚点取「结算段整段」257 字符，实测全产物 count==1、纯 ASCII；
        且 **在 km 内不命中**（km 用 forEach 聚合、无 d.buffs.some(A=>A.reflectDamage) 形态）。

==============================================================================
二、改动（1 处锚点，append 型：new = old + 注入块）
==============================================================================
  注入块（对齐 km 语义，但只对玩家生效 + 取最强单条吸血）：
    /*YLXW_R143_V2918*/if(r==="player"&&f>0){let _yl143ll=0;
      c.buffs.forEach(A=>{A.lifeLeech&&A.lifeLeech>0&&A.lifeLeech>_yl143ll&&(_yl143ll=A.lifeLeech)});
      _yl143ll>0&&(c.hp=Math.min(c.maxHp,Math.floor(c.hp+Math.floor(f*_yl143ll))))}

  ★ 设计说明①：只对玩家生效（r==="player"），与 km 一致，敌方技能不吸血。
  ★ 设计说明②：用「取最大值」(_yl143ll = max) 而非 km 的 forEach 逐条回血。
     理由：km 在存在多条 lifeLeech buff 时会重复回血（每条各回一次）；
     当前实际只有一条（ylxw-rl，来自 YlxwSpellBuffs），两者数值等价，
     但 Math.max 在未来新增来源时不会叠加 —— 这是刻意的、更正确的选择。
  ★ 变量名 _yl143ll 在基线产物中出现 0 次（防与压缩短名碰撞，脚本硬断言）。

  ★ 不改：km() / 反弹逻辑 / u.heal 分支 / 战斗核心公式 / 服务端。

==============================================================================
三、契约（standalone，同 localtest/yl_r141_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r143-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言失败（锚点/部分补丁态）；1=其他错误。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
  · 纯客户端；不改 build_v26n.py / dryrun_087.py / build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 锚点（字符级实测 count==1、纯 ASCII、km 内不命中）

# zy() 内「伤害结算 + 反弹」整段（if(u.damage){...} 块末尾）
ANCHOR = (
    'if(d.hp=Math.max(0,Math.floor(d.hp-f)),f>0&&d.buffs.some(A=>A.reflectDamage&&A.reflectDamage>0))'
    '{const A=Math.max(...d.buffs.filter(I=>I.reflectDamage&&I.reflectDamage>0).map(I=>I.reflectDamage));'
    'A>0&&(m=Math.floor(f*A),c.hp=Math.max(0,Math.floor(c.hp-m)))}'
)

# 注入块：紧跟结算段之后（仍在 if(u.damage){...} 内）
INJECT = (
    '/*YLXW_R143_V2918*/'
    'if(r==="player"&&f>0){'
    'let _yl143ll=0;'
    'c.buffs.forEach(A=>{A.lifeLeech&&A.lifeLeech>0&&A.lifeLeech>_yl143ll&&(_yl143ll=A.lifeLeech)});'
    '_yl143ll>0&&(c.hp=Math.min(c.maxHp,Math.floor(c.hp+Math.floor(f*_yl143ll))))}'
)

NEW = ANCHOR + INJECT

EDITS = [
    ('R143 技能结算后注入吸血分支', ANCHOR, NEW),
]

# --------------------------------------------------------------------------- 在位标记 / 新增 needle / 冻结门禁串

MARK = 'YLXW_R143_V2918'  # 全局唯一，与 R140_V2916 / R141_V2916 互不包含

M_INJECT = 'if(r==="player"&&f>0){let _yl143ll=0;'
M_MAX = 'A.lifeLeech>_yl143ll&&(_yl143ll=A.lifeLeech)'
M_HEAL = 'c.hp=Math.min(c.maxHp,Math.floor(c.hp+Math.floor(f*_yl143ll)))'

# 冻结：km() 既有吸血分支（不得改动）
FRZ_KM_LEECH = (
    'r==="player"&&_>0&&l.buffs.forEach(function(w){w.lifeLeech&&w.lifeLeech>0&&'
    '(l.hp=Math.min(l.maxHp,l.hp+Math.floor(_*w.lifeLeech)))});'
)
FRZ_ZY_FN = 'function zy(t,r,a,l){'
FRZ_KM_FN = 'function km(t,r,a){'
FRZ_HEAL_BRANCH = 'if(u.heal){'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note) —— 供 dryrun 门禁表收录。"""
    return [
        ('R143·在位标记存在', MARK, 1, '==', 'YLXW_R143_V2918'),
        ('R143·吸血分支已注入', M_INJECT, 1, '==', '只对 r==="player" 生效'),
        ('R143·取最强吸血值', M_MAX, 1, '==', 'Math.max 语义，不叠加'),
        ('R143·回血语句已注入', M_HEAL, 1, '==', 'min(maxHp, floor(hp+floor(f*ll)))'),
        ('R143·锚点原样保留', ANCHOR, 1, '==', '结算+反弹段未改动'),
        ('R143·旧压缩短名未碰撞', '_yl143ll', 5, '==', '5 处引用全在注入块内'),
        ('冻结·km 吸血分支未动', FRZ_KM_LEECH, 1, '==', ''),
        ('冻结·zy 函数头未动', FRZ_ZY_FN, 1, '==', ''),
        ('冻结·km 函数头未动', FRZ_KM_FN, 1, '==', ''),
        ('冻结·u.heal 分支未动', FRZ_HEAL_BRANCH, 1, '==', ''),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old in new, '%s 必须为 append 型（old 为 new 前缀）' % name
    # 锚点纯 ASCII
    assert all(ord(ch) < 128 for ch in ANCHOR), 'ANCHOR 必须纯 ASCII'
    # 新增 needle 必须落在 NEW 内、且不在 ANCHOR 内
    assert MARK in NEW and M_INJECT in NEW and M_MAX in NEW and M_HEAL in NEW
    assert M_INJECT not in ANCHOR and M_MAX not in ANCHOR and M_HEAL not in ANCHOR
    assert NEW.count(M_INJECT) == 1 and NEW.count(M_MAX) == 1 and NEW.count(M_HEAL) == 1
    # 注入块只对玩家生效：必须恰好一处 r==="player"，且不含 r==="enemy"
    assert INJECT.count('r==="player"') == 1, '注入块必须恰好一处 r==="player"'
    assert 'r==="enemy"' not in INJECT, '注入块不得含 r==="enemy"'
    assert '_yl143ll' in INJECT
    # 注入块不得引入网络调用
    for _n, _o, nw in EDITS:
        assert 'fetch(' not in nw, '注入块不得含 fetch('


def main() -> int:
    ap = argparse.ArgumentParser(description='R-143 技能吸血（客户端 --src 补丁）')
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

    txt0 = src.decode('utf-8', errors='replace')
    ob = ANCHOR.encode('utf-8')
    nb = NEW.encode('utf-8')

    # 1) 幂等 / 部分补丁态判定（append 型：ANCHOR 在补丁后仍存在，故以 INJECT 为判据）
    if INJECT in txt0:
        if MARK in txt0 and txt0.count(ANCHOR) == 1:
            print('[SKIP] source looks already patched（R-143 注入块已在位）')
            return 3
        print('[FAIL] 检测到部分补丁态（注入块存在但标记/锚点不自洽），拒绝写盘')
        return 2
    if MARK in txt0:
        print('[FAIL] 检测到部分补丁态（在位标记存在但注入块缺失），拒绝写盘')
        return 2

    # 2) 锚点计数（rc=2 面）
    n = src.count(ob)
    if n != 1:
        print('[FAIL] 锚点出现 %d 次（期望 1）' % n)
        return 2
    if txt0.count('_yl143ll') != 0:
        print('[FAIL] 变量名 _yl143ll 已存在于基线产物（疑碰撞），拒绝写盘')
        return 2
    # 锚点必须在 km 内不命中（交叉证明）
    km_i = txt0.find('function km(')
    if km_i >= 0:
        km_tail = txt0[km_i:]
        nxt = km_tail.find('function ', 10)
        km_body = km_tail[:nxt] if nxt > 0 else km_tail
        if ANCHOR in km_body:
            print('[FAIL] 锚点在 km 内命中（不够独特），拒绝写盘')
            return 2

    # 3) 应用（字节级单点替换，append）
    out = src.replace(ob, nb, 1)

    # 4) 门禁
    ok = True
    text = out.decode('utf-8', errors='replace')
    for label, needle, exp, op, note in gates():
        act = text.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-30s actual=%d expect %s %d' % ('OK' if good else 'FAIL', label, act, op, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 5) 往返自证：new → old，必须与源逐字节相同
    back = out.replace(nb, ob, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r143-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r143-', suffix='.tmp')
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
