# -*- coding: utf-8 -*-
r"""
yl_r119_ext.py — R-119 装备特殊属性（神识/身法）全面重配：SPB 等阶基 × 品系数 × 槽系数（0.9.13 批次）

需求原文（台账 R-119 · 物品，逐字）
--------------------------------------------------------------------------
  「这是个打任务，实际游玩发现。所有能使用的物品、装备，对于 神识、身法这两类稀有属性加成太高了。
    我现在的炼气期，属性"攻击: 659 防御: 436 气血: 2718/2718 神识: 681…"。
    找一个数值策划师，专门重新研究策划所有装备和物品的数值，像神识、身法、暴击、闪避、吸血、减伤、
    暴伤这些特殊数值要严格控制增加的数值，可以参照加点1点才得3神识，1点才得2身法的标准来规划。
    同时等阶越往上这些特殊数值增加的数值范围可以略微扩大，毕竟真正的修仙应该是大境界之间数值相差较大。」

数值（docs/0.9.13-design/数值表.md §1/§2 逐项对账）
--------------------------------------------------------------------------
  新公式：spirit = round( SPB[T] × 品系数 × 槽系数 × (0.8+rand×0.4) )
          speed  = round( SPB[T] × 品系数 × 槽系数 × 2/3 × (0.8+rand×0.4) )   （点当量恒等：神3/点、速2/点）
  SPB 等阶基 = [2, 4, 8, 16, 30, 55, 100]                       （T1..T7，≈×1.85/境）
  品系数     = {普通:1, 稀有:1.4, 传说:2, 仙品:3}
  槽系数     = {武器:.5, 护甲:.5, 戒指:2.5, 首饰:2.5, 法宝:2.5}
  矩阵核对（中值）：T1 白戒指 5 / T1 金戒指 15 / T4 白戒指 40 / T7 金戒指 750 / T1 白武器 1 / T7 金武器 150
  —— 与数值表 §2.3 全表逐格一致（见 _precheck 硬断言）；attack/defense/hp/physique 一律不动。

★ 实现层重大代决（与数值表 §2 落地路径不同，已录拍板记录）
--------------------------------------------------------------------------
  数值表 §2.1/§2.6 把病根定位在「随机/锻造装备生成器 ZN(t,r,a)（bundle @325575）」并要求改其 hm/u/m
  参数。产物实证推翻该前提：
  · `ZN` 全产物仅 1 处出现 = 定义本身，零调用点 ⇒ **死代码**（本基线 index-v2912-20261002.js 实测
    \bZN\b 唯一命中 @325584）。照改 ZN = 门禁绿而游戏零变化（假交付）。
  · 活的装备属性生成链 = ry（全产物 20 个调用点：掉落 cy/入包 vs/奖励等）→ iy（@315796）：
    iy 按境界基表 Cs（炼气 baseSpirit=5..）、品级带 mg（普通 .18~.32 等）、等阶乘数 ny=[1,1.25,1.75,
    2.5,3.5,5,7]、品级底价 hm（普通 spirit=20 等）缩放六属性。
  · 因此本补丁改活链 iy：①签名加第 5 参 ty（装备类型）；②ry 调 iy 处补传 c（ry 的 type 形参，
    中文枚举 "武器/护甲/首饰/戒指/法宝"）；③iy 自递归处补传 ty；④iy 循环体内对 spirit/speed 两键
    走新公式分支（模板未定义该键的装备不凭空加词条，词条存在性语义不变）。
  · 数值表 §2.4 的「现值 1020/13100」亦系按死代码公式推算，活链真实现值量级为 T1 白 ≈20~30、
    T7 白 ≈800~1250（hm 底价 floor(20×ny) 与 Cs 基表主导）。这不影响新值矩阵的正确性（矩阵即目标）。
  · 数值表 §2.6「u 上限表同步改」：u 是死代码 ZN 的内部字面量，不适用；活链新公式自带 0.8~1.2 带，
    无需 clamp。hm 表 spirit/speed 底价、ZN 的 m 槽权重表全部冻结不动（门禁证明）。

次级代决（矩阵槽维度在活链的粒度损失）
--------------------------------------------------------------------------
  iy 只知装备类型（H 枚举中文值），不知具体槽位（头/肩/腿/鞋/手与胸甲同属 H.Armor="护甲"）。
  数值表槽系数「头/肩/腿/鞋/手=1.0」无法精确交付 ⇒ 防具类（护甲）统一取 0.5（=矩阵「武器/防具」行，
  保守方向：护甲神识/身法比设计再低一档）。矩阵「戒指/饰品/法宝=2.5」「武器=0.5」两行精确交付。
  若日后要 1.0 档，需把 equipmentSlot 从 vs/cy 传入 ry→iy（结构改动，属 lead 权限）。

锚点（build/assets/index-v2912-20261002.js 逐字实证，2026-10-02，各恰 1 处 / 新形态 0 处）
--------------------------------------------------------------------------
  E1 = iy=(t,r,a,l="普通")=>{                                    → 尾部加 ,ty
  E2 = iy(t,ae.QiRefining,a,l):t                                 → 尾部加 ,ty
  E3 = return{effect:iy(t,a,l,d),permanentEffect:void 0}         → iy(t,a,l,d,c)
  E4 = R.forEach(({key:N,baseValue:k})=>{const _=t[N];…h[N]=Math.min(q,g)}})
       → 在 if(_!==void 0&&typeof _=="number"){ 后插入 spirit/speed 新公式分支
  新分支注入串（raw UTF-8 中文键，产物原生形态）：
    if(N==="spirit"||N==="speed"){const PK={普通:1,稀有:1.4,传说:2,仙品:3}[l]||1,
      SK={武器:.5,护甲:.5,戒指:2.5,首饰:2.5,法宝:2.5}[ty]||1,
      BV=(([2,4,8,16,30,55,100][$]||2)*PK*SK)*(N==="speed"?2/3:1);
      h[N]=Math.round(BV*(.8+Math.random()*.4));return}
  （foreach 回调内 return=跳过该键；$=iy 内既有等阶序变量 0..6；ty 未传时 SK 兜底 1=矩阵「头肩」档）

契约（0.9.13 批次成员补丁脚本，同 localtest/yl_r116_ext.py）
--------------------------------------------------------------------------
  · 命令行只有 --src <装配产物 js>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r119-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 前置依赖：--src 必须含活的 iy/ry 装备缩放链（0.9.12 基线实测满足；装配链无其他模块改此域，
    0.9.13 同样满足）。
  · R-119 无服务端半边：srv/index_v28.ts 实测无任何装备属性生成（hm/baseSpirit/ny/ZN 全部不存在），
    装备数值 100% 客户端生成后随存档保存。

门禁（apply 后形态；供 dryrun 门禁表原样收录）
--------------------------------------------------------------------------
  新形态 4 条 ==1 / 旧形态 4 条 ==0；冻结 14 条 ==1（死代码 ZN 全须全尾、hm/ny/mg/Ba/Cs 原样、
  攻防血体缩放路径原样）—— 证明只动 4 个锚点、只影响 spirit/speed 两键。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# ---- 锚点 / 替换（UTF-8 字节字面量，与压缩产物逐字一致；2026-10-02 实测各恰 1 处）----
A1_OLD = 'iy=(t,r,a,l="普通")=>{'
A1_NEW = 'iy=(t,r,a,l="普通",ty)=>{'
A2_OLD = 'iy(t,ae.QiRefining,a,l):t'
A2_NEW = 'iy(t,ae.QiRefining,a,l,ty):t'
A3_OLD = 'return{effect:iy(t,a,l,d),permanentEffect:void 0}'
A3_NEW = 'return{effect:iy(t,a,l,d,c),permanentEffect:void 0}'
A4_OLD = ('R.forEach(({key:N,baseValue:k})=>{const _=t[N];if(_!==void 0&&typeof _=="number"){'
          'const C=Math.floor(k*x*T*M);let g=Math.floor(k*S.max*T*M),q=_*M;q=Math.max(q,C*.8);'
          'const w=E[N];if(w!==void 0){const A=Math.floor(w*M);q=Math.max(q,A),'
          'g=Math.max(g,Math.floor(A*1.5))}h[N]=Math.min(q,g)}})')
A4_NEW = ('R.forEach(({key:N,baseValue:k})=>{const _=t[N];if(_!==void 0&&typeof _=="number"){'
          # R-119 新公式分支：神识/身法 = SPB[等阶]×品系数×槽系数×(0.8+rand×.4)，身法再×2/3
          'if(N==="spirit"||N==="speed"){const PK={普通:1,稀有:1.4,传说:2,仙品:3}[l]||1,'
          'SK={武器:.5,护甲:.5,戒指:2.5,首饰:2.5,法宝:2.5}[ty]||1,'
          'BV=(([2,4,8,16,30,55,100][$]||2)*PK*SK)*(N==="speed"?2/3:1);'
          'h[N]=Math.round(BV*(.8+Math.random()*.4));return}'
          'const C=Math.floor(k*x*T*M);let g=Math.floor(k*S.max*T*M),q=_*M;q=Math.max(q,C*.8);'
          'const w=E[N];if(w!==void 0){const A=Math.floor(w*M);q=Math.max(q,A),'
          'g=Math.max(g,Math.floor(A*1.5))}h[N]=Math.min(q,g)}})')

EDITS = [('E1 iy签名加ty', A1_OLD, A1_NEW),
         ('E2 iy自递归传ty', A2_OLD, A2_NEW),
         ('E3 ry调用传type', A3_OLD, A3_NEW),
         ('E4 spirit/speed新公式分支', A4_OLD, A4_NEW)]

# ---- 冻结断言串（补丁后必须原样各 1 处）----
FREEZE = [
    ('R119·冻结 ZN死代码原样(不碰)', 'function ZN(t,r,a){const l=Ba[r],c=10+a*5,d=hm[r]',
     'ZN 零调用死代码，本补丁不碰；改它=假交付'),
    ('R119·冻结 ZN内u上限表', 'u={普通:{attack:600,defense:600,hp:600,spirit:600,physique:600,speed:600}',
     '数值表§2.6的u表同步改不适用（死代码内部字面量）'),
    ('R119·冻结 ZN内m权重表weapon', 'weapon:{attack:100,spirit:40,speed:30,physique:10,hp:10,defense:5}', ''),
    ('R119·冻结 ZN内m权重表armor', 'armor:{defense:100,hp:80,physique:40,attack:10,speed:10,spirit:5}', ''),
    ('R119·冻结 ZN内m权重表accessory', 'accessory:{spirit:100,speed:60,hp:40,attack:20,physique:20,defense:10}', ''),
    ('R119·冻结 ZN内m权重表ring', 'ring:{spirit:100,speed:60,hp:40,attack:20,physique:20,defense:10}', ''),
    ('R119·冻结 ZN内m权重表artifact', 'artifact:{spirit:100,attack:80,defense:80,hp:60,physique:50,speed:50}', ''),
    ('R119·冻结 hm品级底价表', 'hm={普通:{attack:20,defense:20,hp:60,spirit:20',
     'hm 六键全部不动：攻防血体继续走底价，spirit/speed 底价不再被活链消费但保留'),
    ('R119·冻结 ny等阶乘数表', 'ny=[1,1.25,1.75,2.5,3.5,5,7]', '攻防血体缩放继续用'),
    ('R119·冻结 mg品级带表', 'mg={普通:{min:.18,max:.32}', '洗炼/iy 品级带未动'),
    ('R119·冻结 Ba品系数表', 'Ba={普通:1,稀有:1.35,传说:2,仙品:3.2}', ''),
    ('R119·冻结 Cs炼气境界基表', 'baseMaxHp:100,baseAttack:10,baseDefense:5,baseSpirit:5,basePhysique:10,baseSpeed:10',
     'Cs 基表未动（spirit/speed 新公式不用它，攻防血体用）'),
    ('R119·冻结 攻防血体缩放路径', 'q=Math.max(q,C*.8)', 'attack/defense/hp/physique 缩放原样'),
    ('R119·冻结 攻防血体clamp', 'h[N]=Math.min(q,g)', 'attack/defense/hp/physique clamp 原样'),
]

# 新公式分支独有信号（铁律⑥：断言打独有信号）
SIG_BRANCH = 'BV=(([2,4,8,16,30,55,100][$]||2)*PK*SK)*(N==="speed"?2/3:1)'


def _js_round(x):
    """JS Math.round 语义（.5 向上），供矩阵对账。"""
    import math
    return math.floor(x + 0.5)


def _matrix_value(tier_idx, rarity, slot_ty, key):
    """新公式中值（roll=1.0），与注入 JS 逐项同构。"""
    SPB = [2, 4, 8, 16, 30, 55, 100]
    PK = {'普通': 1, '稀有': 1.4, '传说': 2, '仙品': 3}
    SK = {'武器': .5, '护甲': .5, '戒指': 2.5, '首饰': 2.5, '法宝': 2.5}
    bv = SPB[tier_idx] * PK[rarity] * SK.get(slot_ty, 1)
    if key == 'speed':
        bv *= 2 / 3
    return _js_round(bv)


def _precheck():
    """补丁前常量自检：数值表 §2.3 矩阵逐格对账 + 锚点互斥（断言失败 → rc=1）。"""
    import math
    SPB = [2, 4, 8, 16, 30, 55, 100]
    PK = {'普通': 1, '稀有': 1.4, '传说': 2, '仙品': 3}
    # 数值表 §2.3 矩阵（key=(等阶0..6, 品, 槽) 期望神识中值；身法=×2/3 取整）
    EXPECT_SPIRIT = {}
    slot_k = {'武器': .5, '护甲': .5, '戒指': 2.5, '首饰': 2.5, '法宝': 2.5}
    for ti in range(7):
        for rn, pk in PK.items():
            for sl, sk in slot_k.items():
                EXPECT_SPIRIT[(ti, rn, sl)] = math.floor(SPB[ti] * pk * sk + 0.5)
    # 抽样硬断言（数值表 §2.3/§2.4 原文数值）
    assert EXPECT_SPIRIT[(0, '普通', '戒指')] == 5, 'T1白戒指应=5'
    assert EXPECT_SPIRIT[(0, '仙品', '戒指')] == 15, 'T1金戒指应=15'
    assert EXPECT_SPIRIT[(3, '普通', '戒指')] == 40, 'T4白戒指应=40'
    assert EXPECT_SPIRIT[(6, '仙品', '戒指')] == 750, 'T7金戒指应=750'
    assert EXPECT_SPIRIT[(0, '普通', '武器')] == 1, 'T1白武器应=1'
    assert EXPECT_SPIRIT[(6, '仙品', '武器')] == 150, 'T7金武器应=150'
    assert EXPECT_SPIRIT[(6, '普通', '戒指')] == 250, 'T7白戒指应=250'
    # 55×3×2.5=412.5，§2.2 公式 round ⇒ 413（数值表 §2.3 表格写 412 系表格取整笔误：
    # 同表 T6 白戒指 137.5→写 138 用的正是 round 口径；按公式交付 413）
    assert EXPECT_SPIRIT[(5, '仙品', '戒指')] == 413, 'T6金戒指应=413(412.5 round)'
    # 身法（数值表 §2.4：T1白戒指身法=3、T7金戒指身法=500、T1金戒指身法=10）
    assert _matrix_value(0, '普通', '戒指', 'speed') == 3, 'T1白戒指身法应=3'
    assert _matrix_value(0, '仙品', '戒指', 'speed') == 10, 'T1金戒指身法应=10'
    assert _matrix_value(6, '仙品', '戒指', 'speed') == 500, 'T7金戒指身法应=500'
    assert _matrix_value(3, '普通', '戒指', 'speed') == 27, 'T4白戒指身法应=27(40×2/3)'
    # 点当量上限自检：T7金戒指 750神识=250点、500身法=250点 —— 数值表§2.3 一致
    assert 750 / 3 == 250 and 500 / 2 == 250
    # 全矩阵单调性：等阶递增不减、品级递增不减
    for sl in slot_k:
        for rn in PK:
            seq = [EXPECT_SPIRIT[(ti, rn, sl)] for ti in range(7)]
            assert all(a <= b for a, b in zip(seq, seq[1:])), ('等阶单调', rn, sl, seq)
        for ti in range(7):
            seq = [EXPECT_SPIRIT[(ti, rn, sl)] for rn in ('普通', '稀有', '传说', '仙品')]
            assert all(a <= b for a, b in zip(seq, seq[1:])), ('品级单调', ti, sl, seq)
    # 锚点互斥
    for _nm, a, b in EDITS:
        assert a != b and a not in b and b not in a, _nm


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 门禁表收录。"""
    out = []
    for label, new in [('E1 iy签名带ty', A1_NEW), ('E2 自递归带ty', A2_NEW),
                       ('E3 ry传type', A3_NEW), ('E4 新公式分支', A4_NEW)]:
        out.append(('R119·新 %s' % label, new, 1, '==', ''))
    out.append(('R119·新公式独有信号', SIG_BRANCH, 1, '==', ''))
    for label, old in [('E1 iy签名旧形态', A1_OLD), ('E2 自递归旧形态', A2_OLD),
                       ('E3 ry调用旧形态', A3_OLD), ('E4 循环体旧形态', A4_OLD)]:
        out.append(('R119·旧 %s 清零' % label, old, 0, '==', ''))
    for name, needle, note in FREEZE:
        out.append((name, needle, 1, '==', note))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description='R-119 装备神识/身法重配 SPB×品×槽（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2913-*.js）')
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
    src_t = src.decode('utf-8', errors='replace')

    # 1) 幂等：已是补丁后形态 → rc=3 不写盘
    if all(new in src_t for _n, _o, new in EDITS) and all(old not in src_t for _n, old, _w in EDITS):
        print('[SKIP] source looks already patched（已含 R119 新形态且旧形态清零）')
        return 3

    # 2) 锚点计数（rc=2 面）
    for name, old, new in EDITS:
        n = src_t.count(old)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）：%r…' % (name, n, old[:60]))
            return 2
    for name, old, new in EDITS:
        if src_t.count(new) != 0:
            print('[FAIL] %s 新形态改前已存在 %d 次（期望 0）' % (name, src_t.count(new)))
            return 2
    for name, needle, _note in FREEZE:
        c = src_t.count(needle)
        if c != 1:
            print('[FAIL] 冻结锚点 %s 出现 %d 次（期望 1）' % (name, c))
            return 2

    # 3) 应用（字节级单点替换）
    out_t = src_t
    for name, old, new in EDITS:
        out_t = out_t.replace(old, new, 1)

    # 4) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        act = out_t.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-28s actual=%d expect==%d' % ('OK' if good else 'FAIL', label, act, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 5) 往返自证（new→old 还原须逐字节等于原文件）
    back = out_t
    for name, old, new in EDITS:
        if back.count(new) != 1:
            print('[FAIL] %s 的 new 出现 %d 次（期望 1）' % (name, back.count(new)))
            return 1
        back = back.replace(new, old, 1)
    if back != src_t:
        print('[FAIL] round-trip mismatch')
        return 1

    out = out_t.encode('utf-8')
    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r119-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r119cli-', suffix='.tmp')
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
