# -*- coding: utf-8 -*-
r"""
yl_r120_ext.py — R-120「灵宠（妖灵）羁绊的作用没有写」客户端补丁脚本（0.9.13 批次）

需求原文（台账 R-120 · 灵宠）
--------------------------------------------------------------------------
  「灵宠系统羁绊的作用没有写」

设计依据（docs/0.9.13-design/玩法说明与文案.md §二 R-120，逐字）
--------------------------------------------------------------------------
  落点1（短版，就地说明）：妖灵卡「羁绊」字段旁补说明——
    羁绊：与妖灵的情谊。每 1 点羁绊，妖灵之力 +0.1%（500 封顶时 +50%）；
    妖灵之力再按 6% 把妖灵属性折算给你。互动、秘径、妖灵精魄都能提升羁绊。
  落点2（长版，补系数）：PP 公式行按长版补羁绊系数细节——
    羁绊K = 1 + 羁绊÷1000（500 封顶 = 1.5）；资质K = 1 + 资质÷200。
  §四.4 验收：不改服务端；产物内新串唯一；文案系数与 r018SpiritPP 一致。

系数实证（2026-10-02 逐字实读，文案=代码，无需改文案对齐）
--------------------------------------------------------------------------
  srv/index_v28.ts（只读核对，本补丁零改动）：
    r018SpiritPP: k = r018RarityK × (1+lv/99) × (1+bd/1000) × (1+ap/200)
      ⇒ 羁绊K = 1 + 羁绊/1000 ✓；每点羁绊 = PP +0.1% ✓
    R018_BOND_MAX = 500 ⇒ 封顶 bondK = 1.5 = +50% ✓
    R018_APTITUDE_MAX/资质K = 1 + ap/200 ✓
    R018_CONVERT = 0.06（6% 折算，r018SpiritBonus）✓
    羁绊获取：互动三选各日免 1 次 +5（tease/brush/talk bond:5）✓；
      秘径归来 R018_EXPED_BOND = +15 ✓；每升 10 级精魄 R018_MILESTONE_BOND = +20 ✓

实现形态（对设计文档落点的一处代决适配）
--------------------------------------------------------------------------
  设计建议落点1 = 给「羁绊」字段加 title 悬浮；但六字段卡经 YlxwKv 纯 data
  对象渲染（label→字符串，无 per-field title 槽），加 title 须改共享组件
  YlxwKv = 超出零布局承诺。按设计文档明示的备选「一行小字皆可」：
  在妖灵卡内 PP 公式行之后追加同款 text-[11px] text-stone-500 一行（短版）。
  落点3（§F-37 灵宠视图亲密度文案）不在本条范围：§一清单把 #37 归 R-121
  （17 处补说明之一，标注「与 R-120 联动」）；为防跨成员双写撞锚，本脚本
  以冻结门禁钉住亲密度侧不动，归属代决已登记拍板记录.md。

锚点侦察（build/assets/index-v2912-20261002.js 逐字实证，2026-10-02）
--------------------------------------------------------------------------
  ANCH_A（PP 行第一段，count==1 @1132842，\uXXXX 转义形态）：
      "\u5996\u7075\u4e4b\u529b PP = \u54c1\u9636K × … × \u8d44\u8d28K\uff1b… × 6% × PP\uff0c"
  ANCH_C（PP 行第二段 + 卡闭合，count==1 @1133039）：
      + "\u76f4\u63a5\u52a0\u7b97…\u3002" }),
  ] });
}
  新串改前 count==0（「每 1 点羁绊」「羁绊K = 1 + 羁绊÷1000」全产物 0 处 ⇒ 独有信号，铁律⑥）。
  跨模块撞锚（坑 26）：全仓扫描 yl_*.py / srv_patch_*.py / patches/ 零命中。

契约（0.9.13 批次 STANDALONE_CLIENT 成员补丁脚本，同 yl_r118_ext.py）
--------------------------------------------------------------------------
  · 命令行只有 --src <文件>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r120-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 前置依赖：--src 须含 r018 妖灵卡展开块（0.9.12 index-v2912-20261002.js 实测满足；
    0.9.13 装配链 r018 在链内同样满足）。与同批 standalone 脚本（r116/r118/r119/r125/r126）
    锚区零交集，列表序无关。

门禁（apply 后形态；供 dryrun 门禁表原样收录，needle 全 ASCII）
--------------------------------------------------------------------------
  ('R120·PP行羁绊系数换算',        '<羁绊K = 1 + 羁绊÷1000 转义>', 1, '==', …)
  ('R120·PP行资质系数换算',        '<资质K = 1 + 资质÷200 转义>', 1, '==', …)
  ('R120·PP行旧形态清零',          '<资质K；主人加成 转义>',       0, '==', …)
  ('R120·PP行主人加成保留',        '<主人加成 = 妖灵属性 × 6% × PP 转义>', 1, '==', …)
  ('R120·卡片含羁绊短版说明',      '<每 1 点羁绊，妖灵之力 +0.1% 转义>', 1, '==', …)
  ('R120·短版行挂在卡内',          '<整行 jsx 转义>',              1, '==', …)
  ('R120·冻结·妖灵帮助②未动', …1) ('R120·冻结·妖灵帮助④未动', …1)
  ('R120·冻结·R18Card定义未动', …1) ('R120·冻结·YlxwKv调用未动', …1)
  ('R120·冻结·亲密度侧未动(归R-121)', …1)
"""

import os
import sys
import argparse
import shutil
from datetime import datetime


def esc(s):
    """中文 → \\uXXXX（产物字节形态）；ASCII 原样。"""
    return ''.join(ch if ord(ch) < 128 else '\\u%04x' % ord(ch) for ch in s)


def E(s):
    return esc(s).encode('ascii')


# ---- 短版说明（设计文档 §二 逐字）----
SHORT = ('羁绊：与妖灵的情谊。每 1 点羁绊，妖灵之力 +0.1%（500 封顶时 +50%）；'
         '妖灵之力再按 6% 把妖灵属性折算给你。互动、秘径、妖灵精魄都能提升羁绊。')
# ---- PP 行补入的系数括注（长版细节；K 记法与该行既有「品阶K/等级K」同风格）----
K_DETAIL = '（羁绊K = 1 + 羁绊÷1000，500 封顶 = 1.5；资质K = 1 + 资质÷200）'

# ---- 锚点 / 替换（rb 字面量：\u 保持 backslash+u 两字符，与产物字节一致）----
PP_SEG1 = E('妖灵之力 PP = 品阶K × 等级K × 羁绊K × 资质K；主人加成 = 妖灵属性 × 6% × PP，')
PP_SEG1_NEW = E('妖灵之力 PP = 品阶K × 等级K × 羁绊K × 资质K' + K_DETAIL + '；主人加成 = 妖灵属性 × 6% × PP，')
ANCH_A = b'"' + PP_SEG1 + b'"'
ANCH_A_NEW = b'"' + PP_SEG1_NEW + b'"'

PP_SEG2 = E('直接加算到战斗属性（快速结算与回合制同时生效）。')
ANCH_C = b'+ "' + PP_SEG2 + b'" }),\n  ] });\n}'
NEWLINE_JS = (b'    e.jsx("div", { className: "text-[11px] text-stone-500", children: "'
              + E(SHORT) + b'" }),')
ANCH_C_NEW = b'+ "' + PP_SEG2 + b'" }),\n' + NEWLINE_JS + b'\n  ] });\n}'

# ---- 前置/冻结断言串 ----
PRE = [
    ('R18Card定义',  b'function YlxwR18Card(t, m) {'),
    ('YlxwKv调用',   b'e.jsx(YlxwKv, { data: data })'),
    ('R79Box妖灵',   b'YlxwR79Box("' + E('妖灵') + b'"'),
    ('帮助②',       E('② 互动：逗弄（Lv.0）/ 梳毛（Lv.10，另 +20 喂食度）')),
    ('帮助④',       E('④ 妖灵之力 = 品阶 × 等级 × 羁绊 × 资质（羁绊上限 500）')),
    ('亲密度注释',   E('亲密度每满 25 点')),
]

# V28_BAN_PATTERNS（交接手册 §2.4）：注入串不得含
BAN = [b'iframe', b'postMessage', b'XMLHttpRequest', b'auth_token', b'X-YL-']


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 表收录。"""
    return [
        ('R120·PP行羁绊系数换算', E('羁绊K = 1 + 羁绊÷1000').decode('ascii'), 1, '==',
         'bondK=1+bd/1000（srv r018SpiritPP 实证）'),
        ('R120·PP行资质系数换算', E('资质K = 1 + 资质÷200').decode('ascii'), 1, '==',
         'aptK=1+ap/200（srv r018SpiritPP 实证）'),
        ('R120·PP行旧形态清零', E('资质K；主人加成').decode('ascii'), 0, '==',
         '旧串已扩写为带系数形态'),
        ('R120·PP行主人加成保留', E('主人加成 = 妖灵属性 × 6% × PP').decode('ascii'), 1, '==',
         '6% 口径不动（R018_CONVERT=0.06）'),
        ('R120·卡片含羁绊短版说明', E('每 1 点羁绊，妖灵之力 +0.1%').decode('ascii'), 1, '==',
         '每点 +0.1%/500 封顶 +50% 与 R018_BOND_MAX=500 一致'),
        ('R120·短版行挂在卡内', NEWLINE_JS.decode('ascii'), 1, '==',
         '短版=卡内 text-[11px] 一行（YlxwKv 无 title 槽的代决适配）'),
        ('R120·冻结·妖灵帮助②未动', E('② 互动：逗弄（Lv.0）/ 梳毛（Lv.10，另 +20 喂食度）').decode('ascii'),
         1, '==', 'R79Box 帮助面不动'),
        ('R120·冻结·妖灵帮助④未动', E('④ 妖灵之力 = 品阶 × 等级 × 羁绊 × 资质（羁绊上限 500）').decode('ascii'),
         1, '==', '面板级帮助不动'),
        ('R120·冻结·R18Card定义未动', 'function YlxwR18Card(t, m) {', 1, '==', '组件定义一字未动'),
        ('R120·冻结·YlxwKv调用未动', 'e.jsx(YlxwKv, { data: data })', 1, '==', '六字段卡数据面不动'),
        ('R120·冻结·亲密度侧未动(归R-121)', E('亲密度每满 25 点').decode('ascii'), 1, '==',
         '§F-37/#37 归 R-121，本条不碰灵宠视图'),
    ]


def fail(rc, msg):
    print('[yl_r120_ext] FAIL rc=%d: %s' % (rc, msg))
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True, description='R-120 妖灵羁绊作用说明（--src 就地原子补丁）')
    ap.add_argument('--src', required=True, help='要打补丁的 bundle 文件路径（需已含 r018 妖灵卡展开块）')
    a = ap.parse_args(argv)

    src = a.src
    if not os.path.isfile(src):
        return fail(2, '文件不存在: %s' % src)

    # 注入串自检：不含 V28_BAN_PATTERNS、纯 ASCII（铁律⑥：新串=独有信号）
    for blob in (ANCH_A_NEW, ANCH_C_NEW):
        for pat in BAN:
            if pat.lower() in blob.lower():
                return fail(1, '新串含禁用模式 %r' % pat)

    with open(src, 'rb') as f:
        b = f.read()

    c_a, c_a_new = b.count(ANCH_A), b.count(ANCH_A_NEW)
    c_c, c_c_new = b.count(ANCH_C), b.count(ANCH_C_NEW)
    for nm, v in (('ANCH_A', c_a), ('ANCH_A_NEW', c_a_new), ('ANCH_C', c_c), ('ANCH_C_NEW', c_c_new)):
        if v > 1:
            return fail(4, '形态异常：%s count=%d（应 ≤1），拒绝续写' % (nm, v))
    if c_a_new == 1 and c_c_new == 1:
        print('[yl_r120_ext] ALREADY-PATCHED（两处新形态已在，未写盘）: %s' % src)
        return 3
    if c_a == 0 or c_c == 0:
        return fail(2, '锚点不符：ANCH_A=%d ANCH_A_NEW=%d ANCH_C=%d ANCH_C_NEW=%d'
                       '（文件是否含 r018 妖灵卡展开块？src=%s）' % (c_a, c_a_new, c_c, c_c_new, src))
    if c_a_new == 1 or c_c_new == 1:
        return fail(4, '半补丁形态（两处只中一处），拒绝续写：ANCH_A_NEW=%d ANCH_C_NEW=%d'
                       % (c_a_new, c_c_new))
    # 此处必为 c_a==1 且 c_c==1 且两新形态均 0：正常补丁路径

    # 前置：冻结面各恰 1（被重构过就拒绝，防打爆他人门禁）
    for nm, nd in PRE:
        got = b.count(nd)
        if got != 1:
            return fail(2, '前置失败：%s count=%d（期望 1）' % (nm, got))

    patched = b.replace(ANCH_A, ANCH_A_NEW, 1).replace(ANCH_C, ANCH_C_NEW, 1)
    if patched == b:
        return fail(1, '替换未产生变化（不应发生）')

    # 内存自检：门禁全过才写盘
    for name, needle, want, op, _note in gates():
        got = patched.count(needle.encode('ascii'))
        if op == '==' and got != want:
            return fail(1, '门禁自检 FAIL：%s count=%d（期望 %d）' % (name, got, want))

    # 改前 .bak（只在真写盘前落）
    bak = '%s.bak-r120-%s' % (src, datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(src, bak)

    # 就地原子写回（同卷临时文件 + os.replace）
    tmp = '%s.tmp-r120' % src
    with open(tmp, 'wb') as f:
        f.write(patched)
    os.replace(tmp, src)

    # 落盘复核（重读现盘字节再验一遍）
    with open(src, 'rb') as f:
        back = f.read()
    if back != patched:
        return fail(1, '落盘复核失败：磁盘字节 != 预期补丁结果')
    for name, needle, want, op, _note in gates():
        got = back.count(needle.encode('ascii'))
        if got != want:
            return fail(1, '落盘门禁 FAIL：%s count=%d（期望 %d）' % (name, got, want))

    print('[yl_r120_ext] OK 已补丁并原子写回: %s' % src)
    print('[yl_r120_ext] 备份: %s' % bak)
    print('[yl_r120_ext] 产物增量 %d 字节（PP 行 +系数括注 %d B、羁绊短版行 %d B）'
          % (len(patched) - len(b), len(ANCH_A_NEW) - len(ANCH_A), len(NEWLINE_JS) + 1))
    print('[yl_r120_ext] 门禁表（供 dryrun 收录）:')
    for g in gates():
        print('    %r' % (g,))
    return 0


if __name__ == '__main__':
    sys.exit(main())
