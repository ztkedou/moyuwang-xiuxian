# -*- coding: utf-8 -*-
r"""
yl_r109_ext.py — R-109 加点后「加点页面」显示的属性没更新

需求原文（台账 R-109，用户 2026-10-01，逐字）
--------------------------------------------------------------------------
    日志中说加点属性提升了，但是加点页面显示还没变。

附件 R-109-1.png：加点面板「可分配属性点: 2」，六项按钮预览
    攻击 337→342 (+5) / 防御 336→339 (+3) / 气血 1,926→1,946 (+20)
    神识 533→536 (+3) / 体魄 315→318 (+3) / 身法 147→149 (+2)

==============================================================================
一、改前取证（全部在产物里逐字 grep，基线 build/assets/index-v2910-20261001.js）
==============================================================================
① 面板预览表 `ne`（@1639785，角色面板组件 `hM` 内；`xM=Rt.memo(hM)` @1685208）：
       ne=O.useMemo(()=>{const F=fe.indexOf(a.realm),K=1+(F>=0?F:0)*2;return{
         attack:Math.floor(5*K),defense:Math.floor(3*K),hp:Math.floor(20*K),
         spirit:Math.floor(3*K),physique:Math.floor(3*K),
         physiqueHp:Math.floor(10*K),speed:Math.floor(2*K)}},[a.realm])
   ⇒ **写死的每点增量 5/3/20/3/3/2**（K = 1+境界序×2，与 Ag 同式）。

② 面板六行渲染（@1668974 起）：
       攻击  _r(b.attack , b.attack +ne.attack ) / ["+",ne.attack ]
       防御  _r(b.defense, b.defense+ne.defense) / ["+",ne.defense]
       气血  _r(b.maxHp  , b.maxHp  +ne.hp     ) / ["+",ne.hp     ]
       神识  _r(b.spirit , b.spirit +ne.spirit ) / ["+",ne.spirit ]
       体魄  _r(b.physique,b.physique+ne.physique)/ ["+",ne.physique]
       身法  _r(b.speed  , b.speed  +ne.speed  ) / ["+",ne.speed  ]
   `b=O.useMemo(()=>xt(a),[a])`（@1634869 组件头）—— **依赖数组正确、与 a 同源**，
   故「b 不重算」「b 与 a 不同源」两条假设均可排除（实测 deps=[a]）。

③ 一键分配确认框 `oe`（@1639900，同组件内）用**同一张写死表**：
       let Re=0,Ie=0,ue=0;
       F==="attack" ?Re=Math.floor(5 *ve*X):F==="defense"?Re=Math.floor(3 *ve*X):
       F==="hp"     ?Re=Math.floor(20*ve*X):F==="spirit" ?Re=Math.floor(3 *ve*X):
       F==="physique"?(Ie=Math.floor(3*ve*X),ue=Math.floor(10*ve*X)):
       F==="speed"&&(Re=Math.floor(2*ve*X));
       const ie=F==="physique"?`+${Ie}体魄, +${ue}气血`:`+${Re}`;
   ⇒ 确认框「预计增加」也按 5/3/20/3/3/2 算，与真实发放不符。

④ 真实发放口径（分配 handler，@806507 / @807587 两处同构）：
       handleAllocateAttribute:T=>{!d||d.attributePoints<=0||u($=>{
         ... const g=Ag($.realm), q=Ps.attack, w=Ps.defense, A=Ps.hp,
                 I=Ps.spirit, D=Ps.physique, Q=Ps.physiqueHp, U=Ps.speed; ... })}
       handleAllocateAllAttributes:T=>{... B=Math.floor(q*g*M) ...}
   每点系数表 `Ps`（@726158，顶层 const）：
       Ps={attack:15,defense:10,hp:100,spirit:3,physique:3,physiqueHp:50,speed:2}
   境界因子 `Ag=t=>1+Xm(t)*2`（`Xm=t=>TS.get(t)??0`，`TS=new Map(fe.map((t,r)=>[t,r]))`）
   ⇒ Ag 与面板的 K **同式**，但基数表不同。

⑤ **根因定位（决定性证据）**：把上游原始包 build/assets/index-v26m-20260927.js
   与产物对比 —— 上游 `Ps={attack:5,defense:3,hp:20,spirit:3,physique:3,
   physiqueHp:10,speed:2}`，面板 `ne` 逐字等于 5/3/20/3/3/2，**两者当时完全一致**。
   0.9.6 `bt096` / 0.9.7 `attr097` 把 `Ps` 抬到 15/10/100/…/50（R-096 气血 60→100、
   体魄附带气血 30→50），并把体魄改成「防御/2 + 气血/2、不再加 physique」（R-095），
   **但面板 `ne` 与确认框 `oe` 这两份「抄来的副本」没有跟着改**。
   ⇒ 加点页面显示的永远是 0.9.5 之前的老数：log 说 +15/+10/+100，页面仍写 +5/+3/+20；
     而体魄一栏预览「+3 体魄」，实际发放的是「+5 防御 / +50 气血」，`physique` 根本不动
     —— 点完体魄后该行**字面意义上一个数字都不变**，正是用户说的「显示还没变」。

⑥ 排除「setter 不支持 updater 函数」（原首要怀疑）：store 定义 @579692 逐字为
       setPlayer:a=>{t(l=>({player:typeof a=="function"?a(l.player):a}))}
   ⇒ **显式支持函数式 updater**（`typeof a=="function"?a(l.player):a`），
     `u($=>{...})` 不会把 player 写成函数。此假设证伪，故不动 setter。

⑦ `Ps` 作用域已证：`fe` 定义在 @244731（顶层 const），面板 @1639785 直接引用 `fe`；
   同文件 head 是顶层 `const`、tail 直接 `createRoot(...).render(...)`，即**单一顶层作用域**，
   故 @1634836 的面板可以安全引用 @726158 的顶层 `Ps`（`xt`@603694 在 @1634869 被引用同证）。

==============================================================================
二、改后行为
==============================================================================
加点面板的「每点增量」与「一键分配确认框」改为**运行时读取权威表 `Ps` + 境界因子**
（面板原有 `K=1+境界序×2` 与 `Ag` 同式，保留以最小化 diff），口径与分配 handler 完全一致：
    攻击 +floor(Ps.attack×K)   防御 +floor(Ps.defense×K)   气血 +floor(Ps.hp×K)
    神识 +floor(Ps.spirit×K)   身法 +floor(Ps.speed×K)
    体魄 +floor(Ps.defense×K/2) 防御 +floor(Ps.hp×K/2) 气血   （R-095 口径）
体魄行不再显示「体魄 315→318 (+3)」这种永不发生的预览，改为「体魄 当前值」+「+X防御/+Y气血」，
与 log（`你分配了1点属性点到体魄 (+5防御, +50气血)`）逐字对齐。

实现（3 处就地替换，无注入块、无新增文件、不动存档 schema）：
  patch ① `r109-preview`  ：`ne` 的基数表 5/3/20/3/3/2 → `Ps.*`；体魄项拆成
                            `physiqueDef=floor(Ps.defense*K/2)` / `physiqueHp=floor(Ps.hp*K/2)`。
  patch ② `r109-physique` ：体魄行的展示与增量文案改为防御/气血。
  patch ③ `r109-all`      ：一键分配确认框的预计增量与文案改为同一 `Ps` 口径。

==============================================================================
三、锚点纪律与撞车检查
==============================================================================
· 三处锚点对基线实测 count 均 == 1（`str.count` 逐字）：
    A1_OLD=1  A2_OLD=1  A3_OLD=1
· 跨模块撞车：`grep -rn -F` 全 patches/ + localtest/（*.py）——
    'Math.floor(5*K)' / 'Math.floor(20*K)' / 'ne=O.useMemo' / '_r(b.physique'
    / 'Math.floor(5*ve*X)' / 'Math.floor(3*ve*X)' / 'Ie}体魄' / 'ne.physique'
    / 'ne.attack' / 'ne.speed'  **全部 0 命中**，无模块以这些串为锚点。
  `yl_attr097_ext.py` 只锚分配 handler 的体魄分支（`Ps.physique` 字面在它注释里出现），
    与本模块锚区零交集；`yl_numbal_ext.py` 只碰心法累加器，不碰面板。
· 本模块不依赖本轮任何其他新模块（纯对既有产物做 3 处字符串替换）。

==============================================================================
四、风险点
==============================================================================
1. 面板引用顶层 `Ps`：已用 `fe` 跨 140 万字符引用同证单一作用域（见 ⑦）。
   若将来打包改成多 chunk 且 `Ps` 被裁出作用域，面板会 ReferenceError（可见、非静默）——
   已加冻结门禁锁 `Ps={attack:15,...}` 存在性。
2. `ne` 去掉 `physique` 键、新增 `physiqueDef`/`physiqueHp`：全产物 `ne.physique` 仅
   体魄行一处消费者（已 grep 确认 1 处），已随之改写，无遗留引用。
3. 体魄行由「315 → 318 (+3)」改为「315」+「+5防御/+50气血」：视觉形态与其他五行略不同，
   属有意为之（physique 不再被加点影响，画箭头会骗人）。
4. 未改版本号、未动 `build_v26n.py` / CHANGELOG / EXPECT / deploy / srv / 其他 `yl_*_ext.py`。

锚点纪律：3 处锚点实测 count 均为 1；GATES 同时断言新形态存在（==1）与旧形态清零（==0），
并冻结 `Ps` 数值表、两个分配 handler、其余五行渲染与 store setter 原文。
"""

# 本模块纯就地替换，无注入块（保留空块以与同目录其他模块同构）。
INJECT_JS = ''

# --------------------------------------------------------------------------- 锚点

# ① 面板预览表 `ne`：写死的 5/3/20/3/3/2 → 运行时读权威表 Ps
NE_OLD = ('ne=O.useMemo(()=>{const F=fe.indexOf(a.realm),K=1+(F>=0?F:0)*2;'
          'return{attack:Math.floor(5*K),defense:Math.floor(3*K),hp:Math.floor(20*K),'
          'spirit:Math.floor(3*K),physique:Math.floor(3*K),'
          'physiqueHp:Math.floor(10*K),speed:Math.floor(2*K)}},[a.realm])')
NE_NEW = ('ne=O.useMemo(()=>{const F=fe.indexOf(a.realm),K=1+(F>=0?F:0)*2;'
          'return{attack:Math.floor(Ps.attack*K),defense:Math.floor(Ps.defense*K),'
          'hp:Math.floor(Ps.hp*K),spirit:Math.floor(Ps.spirit*K),'
          'physiqueDef:Math.floor(Ps.defense*K/2),physiqueHp:Math.floor(Ps.hp*K/2),'
          'speed:Math.floor(Ps.speed*K)}},[a.realm])')

# ② 体魄行：不再预览「体魄+N」，改展示当前体魄 + 实际发放的防御/气血（R-095 口径）
PHYS_OLD = ('e.jsx("div",{className:"text-xs text-stone-400",children:"体魄"}),'
            'e.jsx("div",{className:"text-sm",'
            'children:_r(b.physique,b.physique+ne.physique)}),'
            'e.jsxs("div",{className:"text-xs text-yellow-300",'
            'children:["+",ne.physique]})')
PHYS_NEW = ('e.jsx("div",{className:"text-xs text-stone-400",children:"体魄"}),'
            'e.jsx("div",{className:"text-sm",children:lt(b.physique)}),'
            'e.jsxs("div",{className:"text-xs text-yellow-300",'
            'children:["+",ne.physiqueDef,"防御/+",ne.physiqueHp,"气血"]})')

# ③ 一键分配确认框 `oe`：预计增量与文案改用同一 Ps 口径
ALL_OLD = ('let Re=0,Ie=0,ue=0;'
           'F==="attack"?Re=Math.floor(5*ve*X):F==="defense"?Re=Math.floor(3*ve*X):'
           'F==="hp"?Re=Math.floor(20*ve*X):F==="spirit"?Re=Math.floor(3*ve*X):'
           'F==="physique"?(Ie=Math.floor(3*ve*X),ue=Math.floor(10*ve*X)):'
           'F==="speed"&&(Re=Math.floor(2*ve*X));'
           'const ie=F==="physique"?`+${Ie}体魄, +${ue}气血`:`+${Re}`;')
ALL_NEW = ('let Re=0,Ie=0,ue=0;'
           'F==="attack"?Re=Math.floor(Ps.attack*ve*X):'
           'F==="defense"?Re=Math.floor(Ps.defense*ve*X):'
           'F==="hp"?Re=Math.floor(Ps.hp*ve*X):F==="spirit"?Re=Math.floor(Ps.spirit*ve*X):'
           'F==="physique"?(Ie=Math.floor(Ps.defense*ve*X/2),'
           'ue=Math.floor(Ps.hp*ve*X/2)):'
           'F==="speed"&&(Re=Math.floor(Ps.speed*ve*X));'
           'const ie=F==="physique"?`+${Ie}防御, +${ue}气血`:`+${Re}`;')

# 冻结面：权威每点系数表（本模块只读、不改）
PS_TABLE = 'Ps={attack:15,defense:10,hp:100,spirit:3,physique:3,physiqueHp:50,speed:2}'
# 冻结面：store setter 原文（证明「setter 不支持 updater」假设已证伪，本模块不动它）
SETPLAYER = 'setPlayer:a=>{t(l=>({player:typeof a=="function"?a(l.player):a}))}'


def apply(p, ctx):
    # ① 预览表接权威 Ps 口径（含 R-095 体魄 = 防御/2 + 气血/2）
    p.replace('r109-preview', NE_OLD, NE_NEW, expect=1,
              note='面板 ne 由写死 5/3/20/3/3/2 改为运行时读 Ps（+Ag 同式的 K），'
                   '体魄拆成 physiqueDef/physiqueHp')

    # ② 体魄行改展示真实发放（防御/气血），不再预览永不发生的 physique 增长
    p.replace('r109-physique', PHYS_OLD, PHYS_NEW, expect=1,
              note='体魄行：lt(b.physique) + 「+X防御/+Y气血」，与 log 逐字对齐')

    # ③ 一键分配确认框的预计增量与文案同口径
    p.replace('r109-all', ALL_OLD, ALL_NEW, expect=1,
              note='一键确认框预计增量 5/3/20/3/3/2 → Ps.*，体魄文案 体魄→防御')

    return [
        # ================= 新形态（==1） =================
        ('R109·预览表接权威 Ps.attack',  'attack:Math.floor(Ps.attack*K),defense:Math.floor(Ps.defense*K),'
                                        'hp:Math.floor(Ps.hp*K),spirit:Math.floor(Ps.spirit*K)', 1, '==',
         '面板每点增量改为读 Ps，与分配 handler 同源'),
        ('R109·体魄预览=防御/2+气血/2',  'physiqueDef:Math.floor(Ps.defense*K/2)', 1, '==',
         'R-095 口径：体魄不再加 physique'),
        ('R109·体魄行显示当前体魄值',    'children:lt(b.physique)', 1, '==',
         '不再画「315 → 318」这种永不发生的箭头'),
        ('R109·体魄行增量文案',          '"+",ne.physiqueDef,"防御/+",ne.physiqueHp,"气血"', 1, '==',
         '与 log「(+5防御, +50气血)」对齐'),
        ('R109·一键确认框接 Ps.attack',  'F==="attack"?Re=Math.floor(Ps.attack*ve*X)', 1, '==',
         '确认框预计增量同口径'),
        ('R109·一键确认框体魄口径',      'Ie=Math.floor(Ps.defense*ve*X/2),ue=Math.floor(Ps.hp*ve*X/2)',
         1, '==', ''),
        ('R109·一键确认文案已改防御',    '`+${Ie}防御, +${ue}气血`', 1, '==', ''),
        ('R109·四处同源（handler×2+面板×2）', 'Ps.attack', 4, '>=',
         '两处分配 handler + 面板 ne + 面板 oe 全部引用同一 Ps'),

        # ================= 旧形态（==0） =================
        ('R109·旧预览 attack +5 已清零', 'Math.floor(5*K)', 0, '==', ''),
        ('R109·旧预览 hp +20 已清零',    'Math.floor(20*K)', 0, '==', ''),
        ('R109·旧预览 spirit/physique +3 已清零', 'Math.floor(3*K)', 0, '==', ''),
        ('R109·旧 ne.physique 预览已清零', 'b.physique+ne.physique)', 0, '==', ''),
        ('R109·旧体魄增量标签已清零',    '["+",ne.physique]', 0, '==', ''),
        ('R109·旧确认框 attack +5 已清零', 'Math.floor(5*ve*X)', 0, '==', ''),
        ('R109·旧确认框 hp +20 已清零',  'Math.floor(20*ve*X)', 0, '==', ''),
        ('R109·旧确认框体魄 +10气血已清零', 'Math.floor(10*ve*X)', 0, '==', ''),
        ('R109·旧确认文案已清零',        '`+${Ie}体魄, +${ue}气血`', 0, '==', ''),

        # ================= 冻结（别动别人的面） =================
        ('冻结·每点系数表 Ps 未动',      PS_TABLE, 1, '==',
         '本模块只读 Ps，不改数值表'),
        ('冻结·store setter 未动',       SETPLAYER, 1, '==',
         'setPlayer 原生支持 updater ⇒ 原首要怀疑已证伪，无需改 setter'),
        ('冻结·单点分配 handler 未动',   'handleAllocateAttribute:T=>{!d||d.attributePoints<=0||u($=>{',
         1, '==', ''),
        ('冻结·一键分配 handler 未动',   'handleAllocateAllAttributes:T=>{', 1, '==', ''),
        ('冻结·分配返回体未动',          'attributePoints:M,attack:h', 1, '==', ''),
        ('冻结·分配日志文案未动',        '你分配了1点属性点到攻击力', 1, '==', ''),
        ('冻结·一键分配日志文案未动',    '你一键分配了 ${M} 点属性点到', 6, '>=', ''),
        ('冻结·可分配属性点计数行未动',  '可分配属性点: ', 1, '==', ''),
        ('冻结·攻击行未动',              '_r(b.attack,b.attack+ne.attack)', 1, '==', ''),
        ('冻结·防御行未动',              '_r(b.defense,b.defense+ne.defense)', 1, '==', ''),
        ('冻结·气血行未动',              '_r(b.maxHp,b.maxHp+ne.hp)', 1, '==', ''),
        ('冻结·神识行未动',              '_r(b.spirit,b.spirit+ne.spirit)', 1, '==', ''),
        ('冻结·身法行未动',              '_r(b.speed,b.speed+ne.speed)', 1, '==', ''),
        ('冻结·面板派生 b=xt(a) 未动',   'const b=O.useMemo(()=>xt(a),[a])', 1, '==',
         'b 依赖数组本就正确，非根因'),
    ]
