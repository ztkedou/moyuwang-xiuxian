# -*- coding: utf-8 -*-
r"""
yl_p0cmb_ext.py — P0 战斗缺陷双修（apply 模块 · 纯客户端 · 零服务端）

输入产物：build/assets/index-v102-20261022.js
          （线上现态；2,382,638 B；md5 d95e5b5cf509d95e06822d468b25bb80）
本模块**只做 2 处原地字符串替换**，不注入任何 helper（INJECT_JS 有意留空 ⇒ build 侧
`zh('')` 合法、不插入任何注入块）。幂等标记 `/*[p0cmb]*/` 落在第 1 处替换体内。

新模块键名 `p0cmb` 刻意避开 `r258` / `numfix258` / `p0tal`（R-258 已占用 `numfix258`）。

==============================================================================
【改动 1 · 🔴 P0】斩杀（executeRate）永久失效
==============================================================================
  位置：offset 818819（线上现态实测，`const X0=async(...)` 战斗循环内）
  现状原文（逐字）：
    if(G&&YlxwPB.executeRate>0&&m.maxHp>0&&m.hp<=.3*m.maxHp)
      v=Math.round(v*(1+YlxwPB.executeRate));

  根因：`m` 是 `Iy()`（敌人生成，@813327）返回的敌人对象，其字段只有
        `['name','title','realm','attack','defense','maxHp','speed','spirit',
          'strengthMultiplier']`（+ 早退分支的 6 字段兜底对象），**没有 `hp` 字段**。
        ⇒ `m.hp === undefined` ⇒ `undefined <= .3*m.maxHp` 恒为 `false`
        ⇒ 斩杀加成永不触发（暴击流/剑意诀/戮仙剑诀/归墟/炎爆烧天诀 全部零收益）。

  实测确认（本机探针 _p0cmb_probe4.py，X0 函数体花括号配平抽取 3678 字符）：
    · `let h` / `var h` / `const h` 在 X0 体内均为 **0** 次 —— 敌人血量是**隐式**的
      循环外声明 `h=Y0(m.maxHp)`（@818152，与本判定同处 X0 函数作用域，闭包可见）
    · `m.hp` 在 X0 体内 **1** 次（就是本判定这一处）
    · 时序：判定（伤害计算 `X` 内部，@818819）**先于** `h=Math.max(0,(Number(h)||0)-X)`
      （@819145）⇒ 斩杀用的是「本回合开始时」的敌人血量，语义正确。

  改法（改动面最小）：判定里的 `m.hp` → `h`。
    · 不给 `Iy()` 加 `hp` 字段：Iy() 有 3 处构造（早退兜底 / 常规 / 道合挑战），
      加字段要改 3 处且会引入「两份血量」的维护隐患（与 `h` 双写）。
    · 不改 `h` 的维护逻辑、不改战斗节奏、不改任何数值。

  对照（同语义另一路径，证明 `h` 就是那个血量变量）：
    技能路径 @834943 用 `c.hp`/`c.maxHp`，而 `c` 是**持有 hp 字段**的敌人对象；
    普攻路径用的是局部 `h` —— 两者都是「当前血量」，只是表示形式不同。

==============================================================================
【改动 2 · 🔴 P0】`my` 流派阈值表 12 条效果零消费点
==============================================================================
  位置：offset 1614336（流派面板 `B4` 组件内的「Build流派倾向」标题）

  根因（实测底账）：
    · `my` 表 @494388 定义 crit/sustain/counter 各 4 档（共 12 条 effects：
      critRate/critDamage/hpPercent/damageReduction/lifeLeech/
      counterRate/counterDamage/dodgeRate）
    · `my[l]` 全文 **2** 次：
        ① `B3()` 内 `a[l]=my[l].filter(d=>c>=d.threshold)` —— 只算「达到哪几档」
        ② 面板 `B4` 内 `d=my[l]` —— **仅取 name/threshold 显示**
      ⇒ `my` 的 `effects` 对象**没有任何读取点**（`fy()` 只汇总**羁绊套装** `uy[].effects`，
        与 `my` 无关；`xt()` / `YlxwBattleBonus()` / `YlxwR245Mech()` 均不含 `my`）。
    · 玩家按「暴击流 / 续航流 / 反击流」选功法，实际**零收益**，而面板把档位名
      （「一剑封喉」「不灭金身」「万法归宗」）用绿色高亮显示 ⇒ **引导性欺骗**。

  改法（机镜「不接线、不发明机制」原则，选保守侧）：
    **不新增任何战斗逻辑**（把 my.effects 接进战斗 = 发明新机制，会凭空改变全局战力）。
    只改面板文案，在标题行明确标注「仅展示倾向，不提供实战加成」。
    · 不动 `my` 表数据本身（12 条阈值/效果逐字保留，将来接线时直接可用）
    · 不动 `B3()` 计算逻辑、不动 `fy()`、不动档位显示
    · 不改任何战斗/数值/服务端

==============================================================================
【契约】apply(p, ctx) → gates（与 patches/client/yl_numfix_r258_ext.py 同族）
==============================================================================
  · `p` = yl_patch.Patcher；`ctx = {'zh': zh, 'base_text': str}`。
  · 返回 `list[(name, needle, expected, op, note)]`（op ∈ {'==','>=','<='}）。
  · 无 INJECT_JS；不改 chain_build.py / deploy_* / smoke_* / 任何 build/assets/*。
  · `python yl_p0cmb_ext.py [--src ...] [--out ...]` 为独立自检入口（默认只读、dry-run）：
    载入 → 应用 → 门禁 → 往返自证 → `node --check`；`--out` 才落盘。

★★ 装配序：走 **standalone 薄壳** `localtest/yl_p0cmb_run.py`，**不进 V28_MODULES** ★★
------------------------------------------------------------------------------
  与任务书「接进 build_v26n 的 V28_MODULES、放在 numbal 之前」的字面要求**有偏差**，
  装配实测（2026-10-31）如实记录如下：

    · 缺陷 1 的锚点由 **standalone 环 r245** 注入（`localtest/yl_r245_ext.py` 的 E5 fast 斩杀）。
      三阶段实测计数：
        基线 `index-v26m-20260927.js`（B.BASE）  ： **0**
        V28 阶段产物（136 模块跑完、standalone 前）： **0**（`/*[r245combat]*/` 也是 0）
        终态 `index-v102-20261022.js`              ： **1**
      ⇒ 按字面接进 V28_MODULES 必然 `PatchError: 锚点出现 0 次` fail-closed 中止。
    · 缺陷 2 的锚点在 V28 阶段 count=1，本可进 V28；但两处改动同属一个模块，
      统一走 standalone 便于回滚（lead 2026-10-31 裁定）。

  先例：`localtest/yl_pm101_run.py`（PM-101 玩家私信）—— 同一情况（E3 锚在 r144 产物里，
  V28 阶段 count=0），同样改走 standalone 薄壳，接线在 STANDALONE_CLIENT 'r144' 之后。

  ★ 顺序契约：`STANDALONE_CLIENT` 里排在 **'r258' 之后**（表尾）⇒ r245/r247/r248/r254/
    r255/r256/r257/r258 全已套用。`gates()` 首两条「前置依赖·r245 注入块在位」会在
    顺序被调乱时 fail-closed，而不是静默跳过。

⚠️ 门禁计数口径：本模块的 gates() 在 **standalone 补丁后形态**（r245 及全部前置 standalone
   已套用）上执行。所有 expect 按「该阶段实测值」写；V28 阶段才可见的项已剔除或标注。
"""

import argparse
import io
import os
import sys

# ---------------------------------------------------------------- 注入块（有意留空）

INJECT_JS = ''      # 本模块零注入：build 侧 zh('') 合法、不插块、不跑 BAN 模式

# ---------------------------------------------------------------- 幂等标记

MARK = '/*[p0cmb]*/'

# ---------------------------------------------------------------- 改动 1：斩杀判定 m.hp → h

# 锚点：X0 战斗循环内斩杀判定（全文唯一；V28 阶段与终态均 == 1）
EXEC_OLD = ('if(G&&YlxwPB.executeRate>0&&m.maxHp>0&&m.hp<=.3*m.maxHp)'
            'v=Math.round(v*(1+YlxwPB.executeRate))')
# 新形态：同一位置插入幂等标记 + `m.hp` → `h`
EXEC_NEW = ('if(G&&YlxwPB.executeRate>0&&m.maxHp>0&&h<=.3*m.maxHp)'
            'v=Math.round(v*(1+YlxwPB.executeRate))' + MARK)

# 短串（门禁/守卫用，纯 ASCII）
EXEC_NEEDLE_OLD = 'm.hp<=.3*m.maxHp'
EXEC_NEEDLE_NEW = 'm.maxHp>0&&h<=.3*m.maxHp'

# ---------------------------------------------------------------- 改动 2：流派面板文案

# 锚点：流派面板标题行（`dm` 图标 + " Build流派倾向"），全文唯一
TITLE_OLD = ('children:[e.jsx(dm,{size:14})," Build\u6d41\u6d3e\u503e\u5411"]})')
# 新形态：标题后追加一行说明（同一 h4 内，flex-col 不引入 ⇒ 用 `flex-wrap` 保布局安全）
#   ★ 只加文案，不改 h4 的既有 class、不动 grid 列数、不动档位渲染
TITLE_NEW = ('children:[e.jsx(dm,{size:14})," Build\u6d41\u6d3e\u503e\u5411",'
             'e.jsx("span",{className:"text-stone-500 text-[10px] font-normal",'
             'children:"\uff08\u5f53\u524d\u7248\u672c\u4ec5\u5c55\u793a\u503e\u5411'
             '\uff0c\u4e0d\u63d0\u4f9b\u5b9e\u6218\u52a0\u6210\uff09"' + MARK + '})]})')

# 文案串（门禁用）
NOTE_TXT = '\uff08\u5f53\u524d\u7248\u672c\u4ec5\u5c55\u793a\u503e\u5411\uff0c\u4e0d\u63d0\u4f9b\u5b9e\u6218\u52a0\u6210\uff09'
NOTE_FRAG1 = '\u4ec5\u5c55\u793a\u503e\u5411'          # 仅展示倾向
NOTE_FRAG2 = '\u4e0d\u63d0\u4f9b\u5b9e\u6218\u52a0\u6210'  # 不提供实战加成

EDITS = [
    ('p0cmb·斩杀判定 m.hp→h', EXEC_OLD, EXEC_NEW, 1,
     'P0① 斩杀读敌人局部血量 h（Iy() 无 hp 字段），恢复暴击流/剑意诀等斩杀收益'),
    ('p0cmb·流派面板文案', TITLE_OLD, TITLE_NEW, 1,
     'P0② my 表 effects 零消费点 ⇒ 面板明确标注「仅展示倾向，不提供实战加成」'),
]

# ---------------------------------------------------------------- 冻结锚点（逐字实测，禁改）

# `Iy()` 三处 return 的收尾字段（改动 1 的根因证据：**三处都没有 hp 字段**；本模块不加）
#   ① 兜底（REALM_ORDER 空）  ② 常规  ③ 精英/宗门分支
IY_RET_FALLBACK = 'maxHp:50,speed:10,spirit:5,strengthMultiplier:1'
IY_RET_NORMAL = ('maxHp:Math.round(A*Z),speed:Math.round(I*Z),'
                 'spirit:Math.round(D*Z),strengthMultiplier:V')
IY_RET_ELITE = ('spirit:Math.max(5,Math.round(D*B*N)),strengthMultiplier:h}}')
# 敌人血量局部变量声明（改动 1 的**依据**；**不动**，只证明 h 在作用域内）
HP_DECL = 'let M=Math.max(0,Math.min(T,S)),h=Y0(m.maxHp)'
# 技能路径的敌人血量（`c` 是带 hp 字段的对象；**不动**，作对照）
#   注意：这里没有 `if(` 包裹 —— 是逗号表达式 `_r245ex>0&&…&&(_=Math.round(…))`
SKILL_EXEC = '_r245ex>0&&c.maxHp>0&&c.hp<=.3*c.maxHp'

# `my` 表（改动 2 的**数据源**；**不动**，12 条阈值逐字保留）
MY_TABLE = 'my={crit:[{threshold:3,name:'
MY_TABLE_TAIL = ('{threshold:15,name:"\u4e07\u6cd5\u5f52\u5b97",'
                 'effects:{counterRate:.35,counterDamage:.75,dodgeRate:.1}}]};')
# `B3()` 计算逻辑（**不动**）
B3_BODY = 'function B3(t){const r={crit:0,sustain:0,counter:0}'
B3_CONSUME = 'a[l]=my[l].filter(d=>c>=d.threshold)'
# 面板档位渲染（**不动**）
PANEL_GRID = 'e.jsx("div",{className:"grid grid-cols-3 gap-2"'
PANEL_TIERNAME = 'children:["\u4e0b\u7ea7: ",v.name,"(",v.threshold'

# ---------------------------------------------------------------- 计数指纹（线上现态实测 → 改后）

M_HP_BEFORE, M_HP_AFTER = 9, 8         # `m.hp` 全文：改动 1 去掉 1 处
EXEC_NEEDLE_BEFORE, EXEC_NEEDLE_AFTER = 1, 0
HP_DECL_COUNT = 1                       # `h=Y0(m.maxHp)` 声明恒 1
MY_L_COUNT = 2                          # `my[l]` 恒 2（B3 + 面板），改动 2 不加读取点
NOTE_BEFORE, NOTE_AFTER = 0, 1          # 新文案：无 → 1

# 禁用模式（无注入，但编辑串同样过一遍；与 build_v26n.V28_BAN_PATTERNS 口径一致）
BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']


# ---------------------------------------------------------------- 自检

def _precheck():
    """常量自检（失败 → 抛 AssertionError；apply 会先跑它）。"""
    # 1) 编辑串有效性
    for name, old, new, n, _note in EDITS:
        assert old and new, '%s 锚点不得为空' % name
        assert old != new, '%s 新旧相同（恒等替换）' % name
        assert n == 1, '%s 期望命中数必须为 1' % name
        assert new not in old, '%s 新串是旧串子串（防 replace 顺序踩空）' % name
    # 2) 改动 1：只把 `m.hp` 换成 `h`，其余逐字不变；标记恰 1 次
    assert EXEC_NEW.replace(MARK, '').replace('m.maxHp>0&&h<=', 'm.maxHp>0&&m.hp<=', 1) \
        == EXEC_OLD, 'p0cmb① 除 m.hp→h 外必须逐字相同'
    assert EXEC_NEW.count(MARK) == 1, 'p0cmb① 幂等标记必须恰 1 次'
    assert MARK not in EXEC_OLD, 'p0cmb① 旧串不应含标记'
    assert 'm.hp' not in EXEC_NEW, 'p0cmb① 新串不得残留 m.hp'
    assert 'h<=.3*m.maxHp' in EXEC_NEW, 'p0cmb① 新串必须判局部血量 h'
    # 3) 改动 2：只加一行 span 说明，标题原文逐字保留；标记恰 1 次
    assert 'Build\u6d41\u6d3e\u503e\u5411' in TITLE_NEW, 'p0cmb② 标题原文必须保留'
    assert TITLE_NEW.count(MARK) == 1, 'p0cmb② 幂等标记必须恰 1 次'
    assert MARK not in TITLE_OLD, 'p0cmb② 旧串不应含标记'
    assert TITLE_NEW.startswith('children:[e.jsx(dm,{size:14})," Build\u6d41\u6d3e\u503e\u5411",'), \
        'p0cmb② 必须保持标题在首位（只追加兄弟节点）'
    assert TITLE_NEW.count('e.jsx("span"') == 1, 'p0cmb② 只追加 1 个 span'
    assert NOTE_TXT in TITLE_NEW, 'p0cmb② 文案串必须与 TITLE_NEW 一致'
    assert NOTE_FRAG1 in NOTE_TXT and NOTE_FRAG2 in NOTE_TXT, 'p0cmb② 文案要点缺失'
    # 4) 幂等标记两处形态互不相同（各自只在自己那一处）
    assert EXEC_NEW.count(MARK) == 1 and TITLE_NEW.count(MARK) == 1
    # 5) 冻结锚点必须与新串不相交（防误伤）
    for _f in (IY_RET_FALLBACK, IY_RET_NORMAL, IY_RET_ELITE, HP_DECL, SKILL_EXEC,
               MY_TABLE, MY_TABLE_TAIL, B3_BODY, B3_CONSUME, PANEL_GRID,
               PANEL_TIERNAME):
        for name, _o, _w, _n, _note in EDITS:
            assert _f not in _w, '%s 新串误含冻结锚点 %r' % (name, _f[:40])
    # 6) 禁用模式（编辑串侧）
    for _pat in BAN_PATTERNS:
        for name, _o, _w, _n, _note in EDITS:
            assert _pat not in _w, '%s 新串含禁用模式 %s' % (name, _pat)
    # 7) 计数指纹自洽
    assert M_HP_AFTER == M_HP_BEFORE - 1, '`m.hp` 应减 1（只改斩杀判定）'
    assert EXEC_NEEDLE_AFTER == EXEC_NEEDLE_BEFORE - 1, '斩杀旧短串应清零'
    assert NOTE_AFTER == NOTE_BEFORE + 1, '新文案应从 0 变 1'


def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}。返回 gates 列表。"""
    _precheck()

    # ---- 幂等 / 基线碰撞守卫：新形态在基线里必须为 0（防重复应用）----
    if MARK in p.text:
        raise AssertionError('[p0cmb] 幂等标记 %s 已在基线出现，拒绝重复应用' % MARK)
    for name, old, new, _n, _note in EDITS:
        c = p.count(new)
        if c != 0:
            raise AssertionError('[%s] 新串在基线已出现 %d 次，拒绝替换' % (name, c))

    # ---- 改前计数底账（硬断言：与设计口径逐字一致，不符立即中止）----
    n_hp0 = p.count('m.hp')
    if n_hp0 != M_HP_BEFORE:
        raise AssertionError('[p0cmb] 改前 `m.hp` 计数 %d（期望 %d）' % (n_hp0, M_HP_BEFORE))
    if p.count(EXEC_NEEDLE_OLD) != EXEC_NEEDLE_BEFORE:
        raise AssertionError('[p0cmb] 改前斩杀短串计数 %d（期望 %d）'
                             % (p.count(EXEC_NEEDLE_OLD), EXEC_NEEDLE_BEFORE))
    if p.count(HP_DECL) != HP_DECL_COUNT:
        raise AssertionError('[p0cmb] 敌人血量声明 %d（期望 %d）—— '
                             '改动 1 的前提（h 在同作用域）不成立，中止'
                             % (p.count(HP_DECL), HP_DECL_COUNT))
    if p.count(NOTE_TXT) != NOTE_BEFORE:
        raise AssertionError('[p0cmb] 新文案基线计数 %d（期望 %d）'
                             % (p.count(NOTE_TXT), NOTE_BEFORE))
    n_myl0 = p.count('my[l]')
    if n_myl0 != MY_L_COUNT:
        raise AssertionError('[p0cmb] 改前 `my[l]` 计数 %d（期望 %d）' % (n_myl0, MY_L_COUNT))

    # ---- 应用两条替换 ----
    for name, old, new, exp, note in EDITS:
        p.replace(name, old, new, expect=exp, note=note)

    # ---- 改后计数底账（硬断言）----
    n_hp1 = p.count('m.hp')
    if n_hp1 != M_HP_AFTER:
        raise AssertionError('[p0cmb] 改后 `m.hp` 计数 %d（期望 %d）' % (n_hp1, M_HP_AFTER))
    if p.count(EXEC_NEEDLE_OLD) != EXEC_NEEDLE_AFTER:
        raise AssertionError('[p0cmb] 改后斩杀旧短串计数 %d（期望 %d）'
                             % (p.count(EXEC_NEEDLE_OLD), EXEC_NEEDLE_AFTER))
    n_myl1 = p.count('my[l]')
    if n_myl1 != n_myl0:
        raise AssertionError('[p0cmb] `my[l]` 读取点被改变：%d → %d（本模块不得新增消费点）'
                             % (n_myl0, n_myl1))
    if p.count(HP_DECL) != HP_DECL_COUNT:
        raise AssertionError('[p0cmb] 敌人血量声明被改动（%d → %d）'
                             % (HP_DECL_COUNT, p.count(HP_DECL)))

    return gates()


def gates():
    """补丁后形态门禁（5 元组 name/needle/expected/op/note）。"""
    g = []

    # ============ 前置依赖：standalone 顺序（fail-closed，防静默跳过）============
    #   ★ 本模块两处锚点的**注入者**是 standalone 环，不是 V28 阶段：
    #     改动 1 的斩杀判定由 **r245**（`/*[r245combat]*/`，E5 fast 斩杀）注入；
    #     V28 阶段该锚点 count=0（实测 2026-10-31：V28 产物 EXEC_SHORT=0，终态=1）
    #     ⇒ 本模块**不能**进 V28_MODULES，只能走 standalone 薄壳 yl_p0cmb_run.py，
    #       排在 STANDALONE_CLIENT 'r245' 之后（实际接线位 = 'r258' 之后）。
    #   若将来有人调换顺序把本模块排到 r245 之前，下面这条会立刻 FAIL（而不是静默跳过）。
    g.append(('前置依赖·r245 注入块在位（r245combat）', '/*[r245combat]*/', 1, '==',
              '★ standalone 顺序契约：本模块必须排在 STANDALONE_CLIENT r245 之后；'
              '该标记 count=0 说明 r245 尚未套用 ⇒ 顺序被调乱，必须 fail-closed'))
    g.append(('前置依赖·r245 E5 fast 斩杀标记在位',
              '_r245ex>0&&c.maxHp>0&&c.hp<=.3*c.maxHp', 1, '==',
              'r245 技能路径斩杀（c 带 hp 字段）—— 与普攻 h 同语义的对照，且证明 r245 已跑'))

    # ============ 改动 1：斩杀判定 m.hp → h ============
    g.append(('P0CMB①·斩杀判定读局部血量 h', EXEC_NEW, 1, '==',
              '@818819 `m.hp` → `h`（X0 内 h=Y0(m.maxHp) 声明的敌人血量）'))
    g.append(('P0CMB①·斩杀旧形态清零', EXEC_OLD, 0, '==',
              '旧 `m.hp` 判定必须彻底消失，否则仍是死条件'))
    g.append(('P0CMB①·斩杀短串新形态在位', EXEC_NEEDLE_NEW, 1, '==', ''))
    g.append(('P0CMB①·斩杀短串旧形态清零', EXEC_NEEDLE_OLD, EXEC_NEEDLE_AFTER, '==',
              '`m.hp<=.3*m.maxHp` 全文清零'))
    g.append(('P0CMB①·`m.hp` 全文 9→8', 'm.hp', M_HP_AFTER, '==',
              '其余 8 处为「有 hp 字段的对象」（技能路径 c.hp 等），禁改'))
    g.append(('P0CMB①·幂等标记恰 1（斩杀处）',
              'v=Math.round(v*(1+YlxwPB.executeRate))' + MARK, 1, '==',
              '标记落在斩杀加成语句末尾（同一表达式内），重复应用会被 apply 守卫拦下'))

    # ---- 冻结：改动 1 的前提与对照，一律不动 ----
    g.append(('冻结·敌人血量声明 h=Y0(m.maxHp) 恒1', HP_DECL, HP_DECL_COUNT, '==',
              '改动 1 的依据：h 在 X0 作用域内可见；本模块只读不改'))
    g.append(('冻结·Iy() 兜底 return 未加 hp 字段', IY_RET_FALLBACK, 1, '==',
              '刻意不给 Iy() 加 hp：3 处构造 + 双份血量隐患'))
    g.append(('冻结·Iy() 常规 return 未加 hp 字段', IY_RET_NORMAL, 1, '==', ''))
    g.append(('冻结·Iy() 精英 return 未加 hp 字段', IY_RET_ELITE, 1, '==', ''))
    g.append(('冻结·技能路径 c.hp 斩杀恒1', SKILL_EXEC, 1, '==',
              '`c` 是带 hp 字段的对象，与普攻的 h 同语义，禁改'))

    # ============ 改动 2：流派面板文案 ============
    g.append(('P0CMB②·流派面板新文案在位', TITLE_NEW, 1, '==',
              '「仅展示倾向，不提供实战加成」标注已加'))
    g.append(('P0CMB②·流派面板旧标题清零', TITLE_OLD, 0, '==', ''))
    g.append(('P0CMB②·文案串全文 0→1', NOTE_TXT, NOTE_AFTER, '==', ''))
    g.append(('P0CMB②·要点「仅展示倾向」在位', NOTE_FRAG1, 1, '==', ''))
    g.append(('P0CMB②·要点「不提供实战加成」在位', NOTE_FRAG2, 1, '==', ''))
    g.append(('P0CMB②·幂等标记恰 1（文案处）',
              'children:"' + NOTE_TXT + '"' + MARK, 1, '==',
              '标记落在文案字符串之后（同一 JSX 属性内）'))

    # ---- 冻结：my 表数据 / B3 计算 / 面板档位渲染，一律不动 ----
    g.append(('冻结·my 表定义未动', MY_TABLE, 1, '==',
              '12 条阈值/effects 逐字保留（将来接线时可直接用）'))
    g.append(('冻结·my 表尾（万法归宗）未动', MY_TABLE_TAIL, 1, '==', ''))
    g.append(('冻结·B3() 计算逻辑未动', B3_BODY, 1, '==', '不接线、不改阈值判定'))
    g.append(('冻结·B3() 唯一消费点未动', B3_CONSUME, 1, '==', ''))
    g.append(('冻结·`my[l]` 读取点恒 2（不新增）', 'my[l]', MY_L_COUNT, '==',
              'B3 算档 + 面板取名；本模块**不新增**任何 my.effects 消费点'))
    g.append(('冻结·流派面板三列网格未动', PANEL_GRID, 1, '==', 'grid-cols-3 布局不变'))
    g.append(('冻结·档位名渲染未动', PANEL_TIERNAME, 1, '==',
              '「下级: 名(阈值)」显示逻辑不变'))

    # ---- 冻结：不得新增战斗逻辑（本模块零战斗改动，除改动 1 的判定变量）----
    g.append(('冻结·无新增战斗函数（YlxwP0Cmb 不存在）', 'YlxwP0Cmb', 0, '==',
              '「不接线、不发明机制」：不得注入任何新战斗 helper'))

    return g


# ---------------------------------------------------------------- 独立自检入口

def _load(path):
    with io.open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def _main(argv):
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    sys.path.insert(0, root)
    sys.path.insert(0, here)
    from yl_patch import Patcher, Gates, zh  # noqa: E402

    ap = argparse.ArgumentParser(description='yl_p0cmb_ext 独立自检')
    ap.add_argument('--src', default=os.path.join(root, 'build', 'assets',
                                                  'index-v102-20261022.js'))
    ap.add_argument('--out', default=None, help='给了才落盘（默认 dry-run）')
    args = ap.parse_args(argv)

    src = _load(args.src)
    print('=== 源：%s' % args.src)
    print('    chars=%d' % len(src))

    pt = Patcher(src, label='p0cmb-selfcheck')
    gts = apply(pt, {'zh': zh, 'base_text': src})
    print(pt.report())

    g = Gates(pt.text)
    for t in gts:
        name, s, expect, cmp, note = t[:5]
        g.check(name, s, expect, cmp, note)
    print(g.report())
    ok = g.passed()
    print('门禁结果: %s（%d 条）' % ('PASS' if ok else 'FAIL', len(gts)))

    # ---- 往返自证：把新串换回旧串，须与源逐字节一致 ----
    rt = pt.text
    for _name, _old, _new, _n, _note in EDITS:
        rt = rt.replace(_new, _old, 1)
    rt_ok = (rt == src)
    print('=== 往返自证（新→旧 逐字节还原）: %s' % ('PASS' if rt_ok else 'FAIL'))
    ok = ok and rt_ok

    # ---- node --check（★ 独立语法门禁，字面门禁替代不了）----
    if ok:
        import subprocess
        import tempfile
        fd, tmp = tempfile.mkstemp(prefix='.p0cmbchk-', suffix='.js')
        os.close(fd)
        try:
            with io.open(tmp, 'w', encoding='utf-8', newline='') as f:
                f.write(pt.text)
            r = subprocess.run(['node', '--check', tmp],
                               capture_output=True, text=True, timeout=600)
            print('=== node --check rc=%s' % r.returncode)
            if r.returncode != 0:
                print((r.stderr or '')[:2000])
                ok = False
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    if ok and args.out:
        with io.open(args.out, 'wb') as f:
            f.write(pt.text.encode('utf-8'))
        import hashlib
        print('=== 已落盘：%s（md5 %s）'
              % (args.out, hashlib.md5(pt.text.encode('utf-8')).hexdigest()))

    print('自检结论: %s' % ('PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
