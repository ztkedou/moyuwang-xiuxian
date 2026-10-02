# -*- coding: utf-8 -*-
r"""
yl_attr097_ext.py — R-096 气血单点加成提升 + R-095 体魄重做

背景（用户 2026-10-01）
--------------------------------------------------------------------------
  R-096：每点「气血」的属性加成偏低，把单点气血收益从 60 抬到 100。
  R-095：原话「体魄名称不变，内容变成同时 +防御 与 +气血上限。两项平均加，
         数值为单独加防御和单独加气血的一半。」
         ⇒ 1 点体魄 = +防御(单点防御的一半) + +气血上限(单点气血的一半)，
           **不再加 physique 本身**（原来加的是 `Ps.physique`）。

基线取证（build/assets/index-v296-20261001.js，2,060,466 字符）
--------------------------------------------------------------------------
  两个分配函数（`handleAllocateAttribute` / `handleAllocateAllAttributes`）
  顶部同构地声明了每点加成系数与累加器：
      const g=Ag($.realm),
            q=Ps.attack, w=Ps.defense, A=Ps.hp, I=Ps.spirit,
            D=Ps.physique, Q=Ps.physiqueHp, U=Ps.speed;   // 每点系数
      let   h=$.attack, R=$.defense, E=$.maxHp, N=$.hp,
            k=$.spirit, _=$.physique, C=$.speed;          // 累加器
  ⇒ 本模块用到的映射：`w=Ps.defense`、`A=Ps.hp`、`R=防御累加`、`E=maxHp 累加`、
     `N=hp 累加`、`_=physique 累加`、`D=Ps.physique`、`Q=Ps.physiqueHp`。
  原体魄分支把 `floor(D*g)` 加到 `_`（physique）上、把 `floor(Q*g)` 加到 `E/N`（气血）。
  R-095 改为：把 `floor(w*g/2)` 加到 `R`（防御）、把 `floor(A*g/2)` 加到 `E/N`（气血）。

本模块动作（3 处就地替换，无注入）
--------------------------------------------------------------------------
  patch ① `attr096-hp`    ：Ps 表 `hp:60→100`、`physiqueHp:30→50`（同一对象字面量内）。
  patch ② `attr095-single`：单点分配（handleAllocateAttribute）体魄分支重做。
  patch ③ `attr095-all`   ：一键分配（handleAllocateAllAttributes）体魄分支重做（**同构，最易漏**）。

锚点实测计数（str.count，基线）
--------------------------------------------------------------------------
  OLD_096（hp:60, physiqueHp:30）           = 1
  NEW_096（hp:100, physiqueHp:50）          = 0
  OLD_095a（单点：`_+=B` … `(+${B}体魄`）    = 1
  NEW_095a（单点：`R+=B` … `(+${B}防御`）    = 0
  OLD_095b（一键：`_+=Y` … `(+${Y}体魄`）    = 1
  NEW_095b（一键：`R+=B` … `(+${B}防御`）    = 0
  （冻结门禁串 FZ1 / FZ2 在**打补丁后**为 1，故此处基线计数为 0。）

⚠ 一键分配分支与单点分支**不是**同一段文本（临时变量名不同：单点用 `B/Y`，
  一键用 `Y/L`，且带 `*M`），因此必须各写一条替换，不能只改一处。
  替换后一键分支统一改用 `B/Y`（`let B=0,Y=0,L=0` 已在作用域内声明，`L` 弃用不影响 return）。

锚点纪律：三处锚点实测 count==1；GATES 同时断言新形态存在与旧形态清零。
"""

# 本模块纯就地替换，无注入块（保留空块以与同目录其他模块同构）。
INJECT_JS = ''

# --------------------------------------------------------------------------- 锚点

# ① 每点属性加成表：气血 60→100、体魄附带气血 30→50
#    ⚠ 内联数字（对象字面量在模块加载时求值，注入锚点在其之后，引用常量会拿到 undefined）
ATTR096_OLD = 'Ps={attack:15,defense:10,hp:60,spirit:3,physique:3,physiqueHp:30,speed:2}'
ATTR096_NEW = 'Ps={attack:15,defense:10,hp:100,spirit:3,physique:3,physiqueHp:50,speed:2}'

# ② 单点分配 · 体魄分支：1 点体魄 = 防御(w)/2 + 气血(A)/2，累加进 R 与 E/N
ATTR095_SINGLE_OLD = (
    'else if(T==="physique"){const B=Math.floor(D*g),Y=Math.floor(Q*g);'
    '_+=B,E+=Y,N+=Y;const L={...$,maxHp:E},V=xt(L).maxHp;N=Math.min(N,V),'
    'f(`你分配了1点属性点到体魄 (+${B}体魄, +${Y}气血)`,"gain")}'
)
ATTR095_SINGLE_NEW = (
    'else if(T==="physique"){const B=Math.floor(w*g/2),Y=Math.floor(A*g/2);'
    'R+=B,E+=Y,N+=Y;const L={...$,maxHp:E},V=xt(L).maxHp;N=Math.min(N,V),'
    'f(`你分配了1点属性点到体魄 (+${B}防御, +${Y}气血)`,"gain")}'
)

# ③ 一键分配 · 体魄分支（同构；临时变量名为 Y/L 且带 *M）
ATTR095_ALL_OLD = (
    'else if(T==="physique"){Y=Math.floor(D*g*M),L=Math.floor(Q*g*M),'
    '_+=Y,E+=L,N+=L;const P={...$,maxHp:E},G=xt(P).maxHp;N=Math.min(N,G),'
    'f(`你一键分配了 ${M} 点属性点到体魄 (+${Y}体魄, +${L}气血)`,"gain")}'
)
ATTR095_ALL_NEW = (
    'else if(T==="physique"){B=Math.floor(w*g*M/2),Y=Math.floor(A*g*M/2);'
    'R+=B,E+=Y,N+=Y;const P={...$,maxHp:E},G=xt(P).maxHp;N=Math.min(N,G),'
    'f(`你一键分配了 ${M} 点属性点到体魄 (+${B}防御, +${Y}气血)`,"gain")}'
)

# 冻结门禁串（打补丁后应各为 1）：确认 Ps 里其余键未被牵连
ATTR_FREEZE_1 = 'attack:15,defense:10,hp:100,spirit:3,physique:3'   # 仅 hp 由 60→100
ATTR_FREEZE_2 = 'physiqueHp:50,speed:2}'                            # 速度=2 保持原值


def apply(p, ctx):
    # ---- ① 每点加成：气血 60→100、体魄附带气血 30→50 ----
    p.replace('attr096-hp', ATTR096_OLD, ATTR096_NEW, expect=1,
              note='每点加成：气血 60→100、体魄附带气血 30→50')

    # ---- ② 单点分配体魄：改为 +防御(Ps.defense/2) +气血(Ps.hp/2) ----
    p.replace('attr095-single', ATTR095_SINGLE_OLD, ATTR095_SINGLE_NEW, expect=1,
              note='单点体魄重做：floor(w*g/2)→R(防御)、floor(A*g/2)→E/N(气血)，不再加 physique')

    # ---- ③ 一键分配体魄：同构重做（临时变量 Y/L → B/Y） ----
    p.replace('attr095-all', ATTR095_ALL_OLD, ATTR095_ALL_NEW, expect=1,
              note='一键体魄重做：floor(w*g*M/2)→R(防御)、floor(A*g*M/2)→E/N(气血)，不再加 physique')

    return [
        # ---- ① R-096 每点加成 ----
        ('attr097·新每点加成已就位', ATTR096_NEW,  1, '==', '气血100 / 体魄附带气血50'),
        ('attr097·旧每点加成已清零', ATTR096_OLD,  0, '==', 'hp:60 形态必须为 0'),
        # ---- ② R-095 单点分配 ----
        ('attr095·单点体魄已重做',   ATTR095_SINGLE_NEW, 1, '==', '+防御/2 与 +气血/2'),
        ('attr095·旧单点体魄已清零', ATTR095_SINGLE_OLD, 0, '==', ''),
        # ---- ③ R-095 一键分配 ----
        ('attr095·一键体魄已重做',   ATTR095_ALL_NEW, 1, '==', '同构分支，最易漏'),
        ('attr095·旧一键体魄已清零', ATTR095_ALL_OLD, 0, '==', ''),
        # ---- 冻结：Ps 里其他键未被动过 ----
        ('冻结·Ps 攻/防/神识/体魄未动', ATTR_FREEZE_1, 1, '==', '仅 hp 由 60→100'),
        ('冻结·Ps 速度/体魄血未动',     ATTR_FREEZE_2, 1, '==', 'speed=2 保持原值'),
    ]
