# -*- coding: utf-8 -*-
r"""
yl_r181_ext.py — R-181 筑基奇物(foundationTreasure)属性接入角色面板 + 神识/身法压缩（standalone 纯客户端）

需求原文（台账 R-181，逐字）
--------------------------------------------------------------------------
  「我刚才炼化了筑基奇物 "女娲之石"，内容写的气血+2000 防御+600 神识+1000。
   实际我神识还是166，不知道这些属性到底生效到哪里了。而且我之前让压缩神识的加成，
   这个竟然也没变还有1000这么高。」

拆两条：
  (1) 「女娲之石」的属性（气血+2000 / 防御+600 / 神识+1000）到底有没有生效到角色面板？
      用户实测炼化后神识仍是 166 ⇒ 属性根本没进面板。
  (2) 此前要求「压缩神识的加成」也没生效 —— 女娲之石的「神识+1000」依然是 1000。

==============================================================================
零、取证结论（对 build/assets/index-v2929-20261007.js 字符级实测；★非猜测）
==============================================================================
  [0.1] 物品身份确认
    · 用户口中的「女娲之石」= `Vn.ft_034`（**目录名为「女娲石」**，用户口述加了「之」）：
        ft_034:{id:"ft_034",name:"女娲石",description:"女娲补天所用的神石，可增强灵力",
                rarity:"传说",advancedItemType:"foundationTreasure",
                effects:{spiritBonus:1e3,defenseBonus:600,hpBonus:2e3,
                         specialEffect:"灵力恢复速度提升80%，法术防御提升50%"},
                battleEffect:{...}}
      ⇒ 气血+2000 / 防御+600 / 神识+1000 与用户描述**逐字吻合**（另有一个 `hee_021` 天地精华
        也叫「女娲石」，但那是 heavenEarthEssence，不是「筑基奇物」，排除）。
    · `Vn` = 筑基奇物目录（`Vn={ft_001:...}` @410156..424795，共 40 件 ft_001..ft_040）。

  [0.2] 根因①：定义有、**没接线**（属性从未进入任何派生属性）
    · 炼化只写「id」不写属性 —— `handleRefineAdvancedItem` @~801850：
        if(M.advancedItemType==="foundationTreasure"){_=M.advancedItemId; ...}
        return {...N, foundationTreasure:_ , ...}
      ⇒ `player.foundationTreasure` 只是一个**字符串 id**（`ft_034`）。
    · `Vn[player.foundationTreasure]` 的**全部**读取点（grep 实测 9 处，逐一核对）：
        @1691435 属性总览 tooltip  —— 只把 `W.spiritBonus` 等 push 成**文案**，不加属性
        @1668953/@1668987 战斗技能栏 —— 只读 `battleEffect`
        @1511000 库存物品卡 / @1836324 物品详情 / @1525701 筛选 —— 只做**展示**
        @634182 库存补 `effect`（供 `xs` 反查）
      ⇒ **没有任何一处把 effects 加进角色有效属性**。
    · 角色有效属性的**唯一汇聚点** = `xt(t)` @615579（面板 `l4` @828519 读 `xt(t)`，
      主界面/战斗/突破/打坐/历练共约 30 处调用）。`xt` **完全不读奇物**。
    · `xs()` @319836 理论上能由 `advancedItemId` 反查目录 effects，但（a）需 `t.effect` 为空、
      （b）调用点一律 `if(E && E.effect)` 守卫，（c）炼化后的奇物**不在库存、不被装备**（是独立字段）
      ⇒ 根本不走 `xs`。**结论：定义在、没接线。**（用户「神识还是 166」= 面板根本没变。）

  [0.3] 根因②：「1000 没被压缩」= 展示与实扣**双双未压缩**
    · 用户看到的 1000 来自 `Vn.ft_034.effects.spiritBonus` 的**原值直显**（@1691435 等展示位）。
    · 既有的两条「压缩神识」决策**都没有覆盖「筑基奇物」这一类**：
        R-107（0.9.11）—「神识、体魄除以十」：只针对**可使用物品（丹药/药草）**。
        R-119（0.9.13）— 装备神/速重配：只改活链 `iy`（`iy` @316706 内的
                         `if(N==="spirit"||N==="speed"){...BV=(([2,4,8,16,30,55,100][$]||2)*PK*SK)...}`），
                         **只作用于装备**；`Vn` 目录不经过 `iy`。
        R-130（0.9.13）— 天赋神/速 ×0.375（=÷8，`YLXW_T097_FLAT={...,spirit:0.125,speed:0.125,...}`）。
        R-140（0.9.17）— 要点③「升段位只能使用一次的『奇物类』道具不改」、要点④「装备上的
                         神识/身法不动」⇒ 奇物当时**被刻意排除**在压缩之外。
      ⇒ 用户现在**明确要求**压缩奇物的神识（R-181 原文），故本环按 R-130 口径补上。

  [0.4] 服务端：`srv/index_v28.ts`（865,436 B）实测 `foundationTreasure`/`女娲石`/`ft_034`/
        `spiritBonus` **全部 0 命中** ⇒ 奇物属性 100% 客户端，**无需 srv_patch**。

  [0.5] 既有「扩展钩子」——本环的落点（★这是关键发现）
    `xt(t)` 尾部预留两个**派生属性扩展钩子**（@616859/@616915，纯 ASCII）：
        ...r.speed+=Tr(t.speed,c,d)}
        typeof YlxwStatExtras==="function"&&YlxwStatExtras(t,r);
        typeof YlxwSpiritExtras==="function"&&YlxwSpiritExtras(t,r);return r};
    · `YlxwStatExtras(p,r)` @1319769 —— 羁绊攻防血% / R-141 天生词条 / 自创神通攻速%。
      **已被两处包裹**（LG 灵根元素 @1492144、T2 灵宠 @1450584，范式 = "Wrap, never clobber"）。
    · `YlxwSpiritExtras(p,r)` @1024533 —— 目前只做 `p.petSpirit`（妖灵之力 PP）四项加算，
      **尚无任何包裹**（`YlxwSpiritExtras` 全文仅 3 处：定义 1 + xt 调用 2）。
    ⇒ 本环**包裹 `YlxwSpiritExtras`**（不碰已被包两次的 `YlxwStatExtras`，避免与既有链抢挂点），
      与 R-018 妖灵那套「同挂点、同风格」的写法逐字一致。

==============================================================================
一、改动点（1 处就地替换，纯 ASCII 注入）
==============================================================================
  E1 在 `YlxwSpiritExtras` 定义**之后**追加一个 IIFE（**不改原函数体一个字**）：
      (1) 目录归一：`for (id in Vn)` 把 `Vn[id].effects.spiritBonus / speedBonus`
          ×0.125（=÷8）取整；`attack/defense/hp/physique` **一律不动**（R-107 R1 口径）。
          ★ 归一的是**运行时目录对象**，`Vn` 的**字面量**（`spiritBonus:1e3,...`）**一字未改**
            ⇒ 幂等/往返天然成立，且所有展示位（@1691435/@1511000/@1836324）读的就是同一个
              `Vn[id].effects`，**展示与实扣自动一致**（用户不会再看到 1000）。
      (2) 接入：包裹 `YlxwSpiritExtras`，先 `__r181prev(p,r)`（原妖灵四项照旧），
          再把 `Vn[p.foundationTreasure].effects` 的六项加进 `r`
          （attackBonus→r.attack、defenseBonus→r.defense、hpBonus→r.maxHp、
            physiqueBonus→r.physique、spiritBonus→r.spirit、speedBonus→r.speed）。
          守卫：`!p || !r` / 无 `foundationTreasure` / 目录无此 id ⇒ 直接 return（零副作用）。

  ★ 不改：`Vn` 字面量 / `YlxwStatExtras`（含 LG·T2 两处包裹）/ `xt` 本身 / `xs` / `iy` /
    `handleRefineAdvancedItem` / `battleEffect` / 任何展示位 / 任何其它 `yl_*_ext.py` / 服务端。
  ★ 不碰 `YLXW_T097_FLAT`（R-130 的天赋系数）；本环只是**采用同一系数值 0.125**。

==============================================================================
二、数值口径（★需用户拍板复核）
==============================================================================
  采用系数 `K = 0.125`（= ÷8），与 **R-130 天赋神识/身法** 的
  `YLXW_T097_FLAT.spirit = YLXW_T097_FLAT.speed = 0.125`（=「现值 ÷8」）**同口径**。
  · 依据（设计红线，`docs/0.9.13-design/数值表.md` §2/§3）：
      「1 点加点 = 神识 3 / 身法 2」⇒ 女娲石 `spiritBonus:1000` = **333 点当量**，
      而设计目标是「任何单件装备/单个天赋的特殊属性点当量，不得超过玩家该阶段总点数的一个
      可见小头」。÷8 后 = 125 神识 ≈ **42 点当量**，落回「可见小头」量级。
  · 女娲石（ft_034）实算：神识 1000 → **125**；身法 无 → 无；气血 2000 / 防御 600 **不动**。
  · **单旋钮**：`var __r181K = 0.125;` —— 若用户想更狠，改这一个数即可
      （备选 ÷10，即 `0.10`，对应 R-107「神识、体魄除以十」的物品侧旧口径 ⇒ 女娲石 100）。
  · 身法（speedBonus）与神识**同系数**处理：R-130/R-119 都把 spirit/speed 视为同一类
      「稀有属性」同口径压缩；若用户只认可压缩神识、身法保留原值，改一行即可（见 §四 E1(1)）。
  · 体魄（physiqueBonus）**不压缩**：R-130 的 `YLXW_T097_FLAT.physique = 1`，
      R-119 拍板「attack/defense/hp/physique 一律不动」。（女娲石本就无体魄词条。）

==============================================================================
三、契约（照 localtest/yl_r179_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填，就地写回）/ `--check`（只验不写）/ `--selftest`（内存自证）。
  · 1 处就地替换（E1），纯 ASCII 注入（变量名 `__r181*` 在基线出现 0 次；注释亦全 ASCII）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r181-<时刻>`。
  · 幂等：产物已含标记 `[r181equip]` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 探针：从**真实产物**抽出 `Vn` 目录字面量 + 真实 `YlxwSpiritExtras` + 注入块，在 node 里
      (a) 逐件比对「压缩前 vs 压缩后」；只允许 spirit/speed 变、其余键逐字相同；
      (b) 用 `{foundationTreasure:"ft_034"}` 的角色对象跑真实钩子，断言面板属性 166→291 等。

==============================================================================
四、锚点（对 build/assets/index-v2929-20261007.js 字符级实测）
==============================================================================
  E1_OLD  count==1（247 chars，纯 ASCII）→ 打后仍为 1（NEW = OLD + 注入块，OLD 作为前缀保留）
      = `function YlxwSpiritExtras(p, r) {...}` 整段定义（见 E1_OLD 常量）
  冻结（对**原件**校验，count 必须 == 1，另 ft_034==2 / YLXW_T097_FLAT==3）：
      function YlxwSpiritExtras(p, r) {                    ← 原始钩子定义未动
      r.speed += Number(s.speed) || 0;                     ← 原钩子函数体未动
      function YlxwStatExtras(p, r) {                      ← 另一钩子未动（LG/T2 包裹面）
      typeof YlxwSpiritExtras==="function"&&YlxwSpiritExtras(t,r)   ← xt 调用点未动
      typeof YlxwStatExtras==="function"&&YlxwStatExtras(t,r)       ← xt 调用点未动
      Vn={ft_001:                                          ← 奇物目录定义未动
      spiritBonus:1e3,defenseBonus:600,hpBonus:2e3         ← ft_034 字面量未动（只运行时归一）
      YLXW_T097_FLAT                                       ← R-130 天赋系数未动（==3）
      [r179advlog] / [r174act] / [r175bossui] / [r177adv] / [r169herb] / [r169bherb]  ← 邻环在位
  打后：`[r181equip]`==1 · 注入块签名各==1 · 上述冻结针脚全部保持原位。

==============================================================================
五、自证顺序（缺一不可）
==============================================================================
  ① `--check` 全绿 ② 对系统临时目录里的副本真实写回 ③ `node --check <产物>` rc=0
  ④ 复跑 → SKIP（rc=3，不写盘）⑤ 删掉临时副本与 `.bak`（仓库不留任何临时物）
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r181equip]'

# --------------------------------------------------------------------------- 替换项

# E1：在 YlxwSpiritExtras 定义之后追加注入块（原定义逐字保留，作为 NEW 的前缀）
E1_OLD = (
    'function YlxwSpiritExtras(p, r) {\n'
    '  if (!p || !r) return;\n'
    '  var s = p.petSpirit;\n'
    '  if (!s) return;\n'
    '  r.attack += Number(s.attack) || 0;\n'
    '  r.defense += Number(s.defense) || 0;\n'
    '  r.maxHp += Number(s.maxHp) || 0;\n'
    '  r.speed += Number(s.speed) || 0;\n'
    '}\n'
)

# 注入块（纯 ASCII）：① Vn 目录归一（神识/身法 ÷8）② 包裹钩子把奇物 effects 接入派生属性
E1_BLOCK = (
    '\n'
    '/* [r181equip] R-181 foundationTreasure: (1) normalize Vn spirit/speed x0.125 (= /8, same as R-130); */\n'
    '/* (2) wire Vn[player.foundationTreasure].effects into xt() via the existing YlxwSpiritExtras hook. */\n'
    '(function () {\n'
    '  if (typeof YlxwSpiritExtras !== "function") return;\n'
    '  var __r181K = 0.125; /* = 1/8, same coefficient as R-130 talent spirit/speed (0.125) */\n'
    '  if (typeof Vn === "object" && Vn) {\n'
    '    for (var __r181id in Vn) {\n'
    '      var __r181ef = Vn[__r181id] && Vn[__r181id].effects;\n'
    '      if (!__r181ef) continue;\n'
    '      if (typeof __r181ef.spiritBonus === "number" && __r181ef.spiritBonus > 0)\n'
    '        __r181ef.spiritBonus = Math.round(__r181ef.spiritBonus * __r181K);\n'
    '      if (typeof __r181ef.speedBonus === "number" && __r181ef.speedBonus > 0)\n'
    '        __r181ef.speedBonus = Math.round(__r181ef.speedBonus * __r181K);\n'
    '    }\n'
    '  }\n'
    '  var __r181prev = YlxwSpiritExtras;\n'
    '  YlxwSpiritExtras = function (p, r) {\n'
    '    __r181prev(p, r);\n'
    '    if (!p || !r) return;\n'
    '    var __r181fx = (typeof Vn === "object" && Vn && p.foundationTreasure)\n'
    '      ? (Vn[p.foundationTreasure] || {}).effects : null;\n'
    '    if (!__r181fx) return;\n'
    '    if (typeof __r181fx.attackBonus === "number") r.attack += __r181fx.attackBonus;\n'
    '    if (typeof __r181fx.defenseBonus === "number") r.defense += __r181fx.defenseBonus;\n'
    '    if (typeof __r181fx.hpBonus === "number") r.maxHp += __r181fx.hpBonus;\n'
    '    if (typeof __r181fx.physiqueBonus === "number") r.physique += __r181fx.physiqueBonus;\n'
    '    if (typeof __r181fx.spiritBonus === "number") r.spirit += __r181fx.spiritBonus;\n'
    '    if (typeof __r181fx.speedBonus === "number") r.speed += __r181fx.speedBonus;\n'
    '  };\n'
    '})();\n'
    '/*[/r181equip]*/\n'
)

E1_NEW = E1_OLD + E1_BLOCK

REPS = [
    ('R181-E1 奇物属性接入+神识压缩（包裹 YlxwSpiritExtras）', E1_OLD, E1_NEW),
]

# 冻结针脚：本环只动上面一处，下列既有形态必须逐字在位（对**原件**校验）
FREEZE = [
    ('function YlxwSpiritExtras(p, r) {', 1),                        # 原始钩子定义未动
    ('r.speed += Number(s.speed) || 0;', 1),                          # 原钩子函数体未动
    ('function YlxwStatExtras(p, r) {', 1),                           # 另一钩子未动
    ('typeof YlxwSpiritExtras==="function"&&YlxwSpiritExtras(t,r)', 1),  # xt 调用点未动
    ('typeof YlxwStatExtras==="function"&&YlxwStatExtras(t,r)', 1),      # xt 调用点未动
    ('Vn={ft_001:', 1),                                              # 奇物目录定义未动
    ('spiritBonus:1e3,defenseBonus:600,hpBonus:2e3', 1),              # ft_034 字面量未动
    ('ft_034', 2),                                                   # 女娲石条目仍在
    ('YLXW_T097_FLAT', 3),                                           # R-130 天赋系数未动
    ('[r179advlog]', 1),                                             # 邻环 R-179 在位
    ('[r174act]', 1),                                                # 邻环 R-174 在位
    ('[r175bossui]', 1),                                             # 邻环 R-175 在位
    ('[r177adv]', 1),                                                # 邻环 R-177 在位
    ('[r169herb]', 1),                                               # 邻环 R-169 在位
    ('[r169bherb]', 1),                                              # 邻环 R-169b 在位
]

# 仅对**原件**成立的断言（本环注入后会改变计数，故不进 gates 的产物侧校验）
ORIG_ONLY = [
    ('p.foundationTreasure', 0),                                     # 注入块之外无此写法（两处均出自本环）
]

_BLOCK_SIG = '/* [r181equip] R-181 foundationTreasure: (1) normalize Vn spirit/speed x0.125 (= /8, same as R-130); */'
_BLOCK_END = '/*[/r181equip]*/'


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R181·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r181equip] 恰好 1 处'),
        ('R181·注入块起始唯一', _BLOCK_SIG, 1, '==', '注入块签名恰好 1 处'),
        ('R181·注入块结束唯一', _BLOCK_END, 1, '==', '结束哨兵恰好 1 处'),
        ('R181·压缩系数常量唯一', 'var __r181K = 0.125;', 1, '==', '单旋钮 K=÷8'),
        ('R181·目录归一-神识', '__r181ef.spiritBonus = Math.round(__r181ef.spiritBonus * __r181K);', 1, '==', '神识 ×0.125'),
        ('R181·目录归一-身法', '__r181ef.speedBonus = Math.round(__r181ef.speedBonus * __r181K);', 1, '==', '身法 ×0.125'),
        ('R181·钩子包裹唯一', 'YlxwSpiritExtras = function (p, r) {', 1, '==', 'Wrap, never clobber'),
        ('R181·原钩子链保留', '__r181prev(p, r);', 1, '==', '先跑原妖灵四项'),
        ('R181·奇物读取（守卫+取值）', 'p.foundationTreasure', 2, '==', '读 player.foundationTreasure'),
        ('R181·接入-气血', 'r.maxHp += __r181fx.hpBonus;', 1, '==', 'hpBonus -> maxHp'),
        ('R181·接入-防御', 'r.defense += __r181fx.defenseBonus;', 1, '==', 'defenseBonus -> defense'),
        ('R181·接入-攻击', 'r.attack += __r181fx.attackBonus;', 1, '==', 'attackBonus -> attack'),
        ('R181·接入-体魄', 'r.physique += __r181fx.physiqueBonus;', 1, '==', 'physiqueBonus -> physique'),
        ('R181·接入-神识', 'r.spirit += __r181fx.spiritBonus;', 1, '==', 'spiritBonus -> spirit'),
        ('R181·接入-身法', 'r.speed += __r181fx.speedBonus;', 1, '==', 'speedBonus -> speed'),
        ('R181·原始钩子定义仍在', 'function YlxwSpiritExtras(p, r) {', 1, '==', 'E1_OLD 作为 NEW 前缀保留'),
        ('R181·原始钩子体仍在', 'r.speed += Number(s.speed) || 0;', 1, '==', '原函数体一字未改'),
        ('R181·ft_034 字面量未改', 'spiritBonus:1e3,defenseBonus:600,hpBonus:2e3', 1, '==', '只运行时归一，数据字面量不动'),
        ('R181·另一钩子未动', 'function YlxwStatExtras(p, r) {', 1, '==', '不碰 LG/T2 包裹面'),
        ('R181·xt 调用点未动', 'typeof YlxwSpiritExtras==="function"&&YlxwSpiritExtras(t,r)', 1, '==', 'xt 尾钩子调用原样'),
    ]
    for needle, cnt in FREEZE:
        g.append(('冻结 ' + needle[:26], needle, cnt, '==', '冻结既有形态'))
    return g


# --------------------------------------------------------------------------- 主流程

def _read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


def _write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(text.encode('utf-8'))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _precheck(s):
    """返回 None=可打；否则返回错误串。对**原件** s 校验锚点与冻结针脚。"""
    if IDEMPOTENT_MARK in s or all(new in s for _, _, new in REPS):
        return None  # 幂等，交由 main 判 rc=3
    for name, old, new in REPS:
        if new in s:
            continue
        if s.count(old) != 1:
            return '%s 锚点出现 %d 次（期望 1）' % (name, s.count(old))
    for needle, cnt in FREEZE:
        if s.count(needle) != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, s.count(needle), cnt)
    for needle, cnt in ORIG_ONLY:
        if s.count(needle) != cnt:
            return '原件断言 %r 出现 %d 次（期望 %d）' % (needle, s.count(needle), cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时为错误串，out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPS:
        if new in out:
            continue
        out = out.replace(old, new, 1)
    return out, None


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        c = out.count(needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    rev = out
    for name, old, new in reversed(REPS):
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    """对 js_text 跑 node --check；返回 (rc, node_path) 或 (None, None) 当无 node。"""
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
        r = subprocess.run([node, '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _vn_literal(text):
    """抽出 `Vn={ft_001:...}` 的**对象字面量**（不含 `Vn=` 与尾随 `,`）。"""
    a = text.find('Vn={ft_001:')
    b = text.find('En={hee_001:')
    if a < 0 or b < 0:
        return None
    if text[a + 3] != '{' or text[b - 1] != ',':
        return None
    return text[a + 3:b - 1]


def _r181_probe(patched_text, orig_text):
    """从**真实产物**抽 Vn 目录 + 真实钩子 + 注入块，在 node 里验证压缩与接入。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。
    """
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'

    vn_new = _vn_literal(patched_text)
    vn_old = _vn_literal(orig_text)
    if not vn_new or not vn_old:
        return False, 'Vn 目录边界未找到'

    i = patched_text.find(E1_OLD)
    if i < 0:
        return False, 'YlxwSpiritExtras 定义未找到'
    blk_start = i + len(E1_OLD)
    blk_end = patched_text.find(_BLOCK_END, blk_start)
    if blk_end < 0:
        return False, '注入块结束哨兵未找到'
    blk = patched_text[blk_start:blk_end + len(_BLOCK_END)]
    if _BLOCK_SIG not in blk:
        return False, '注入块签名未找到'

    js = (
        'var VnOld = ' + vn_old + ';\n'
        'var Vn = ' + vn_new + ';\n'
        'var YLXW_T097_FLAT = { attack:1, defense:1, hp:1, spirit:0.125, physique:1, speed:0.125, luck:1 };\n'
        + E1_OLD + '\n'
        + blk + '\n'
        'function fail(m){ throw new Error(m); }\n'
        '/* (a) 逐件比对：只允许 spirit/speed 变，其余键逐字相同 */\n'
        'var ko = Object.keys(VnOld), kn = Object.keys(Vn);\n'
        'if (kn.length !== ko.length) fail("entry count changed: " + ko.length + " -> " + kn.length);\n'
        'var nsp = 0, nk = 0;\n'
        'for (var x = 0; x < ko.length; x++) {\n'
        '  var id = ko[x], eo = VnOld[id] && VnOld[id].effects, en = Vn[id] && Vn[id].effects;\n'
        '  if (!eo) { if (en) fail("effects appeared on " + id); continue; }\n'
        '  if (!en) fail("effects vanished on " + id);\n'
        '  if (eo.spiritBonus !== undefined) {\n'
        '    nsp++;\n'
        '    if (en.spiritBonus !== Math.round(eo.spiritBonus * 0.125)) fail("spirit norm " + id + ": " + eo.spiritBonus + " -> " + en.spiritBonus);\n'
        '  }\n'
        '  if (eo.speedBonus !== undefined) {\n'
        '    nk++;\n'
        '    if (en.speedBonus !== Math.round(eo.speedBonus * 0.125)) fail("speed norm " + id + ": " + eo.speedBonus + " -> " + en.speedBonus);\n'
        '  }\n'
        '  if (eo.attackBonus !== en.attackBonus || eo.defenseBonus !== en.defenseBonus ||\n'
        '      eo.hpBonus !== en.hpBonus || eo.physiqueBonus !== en.physiqueBonus)\n'
        '    fail("non spirit/speed key changed on " + id);\n'
        '  if (eo.specialEffect !== en.specialEffect) fail("specialEffect changed on " + id);\n'
        '}\n'
        'if (nsp < 10) fail("too few spiritBonus entries normalized: " + nsp);\n'
        '/* (b) 女娲石 ft_034 前后值 */\n'
        'var rawS = VnOld.ft_034.effects.spiritBonus, newS = Vn.ft_034.effects.spiritBonus;\n'
        'if (rawS !== 1000) fail("raw ft_034 spirit != 1000: " + rawS);\n'
        'if (newS !== 125) fail("norm ft_034 spirit != 125: " + newS);\n'
        'if (Vn.ft_034.effects.hpBonus !== 2000) fail("ft_034 hp changed: " + Vn.ft_034.effects.hpBonus);\n'
        'if (Vn.ft_034.effects.defenseBonus !== 600) fail("ft_034 def changed: " + Vn.ft_034.effects.defenseBonus);\n'
        '/* (c) 真实钩子：带女娲石的角色对象 -> 面板属性 */\n'
        'function mk(){ return { attack:0, defense:0, maxHp:0, spirit:166, physique:0, speed:0 }; }\n'
        'var r1 = mk(); YlxwSpiritExtras({ petSpirit:null, foundationTreasure:"ft_034" }, r1);\n'
        'if (r1.spirit !== 291) fail("panel spirit != 291: " + r1.spirit);\n'
        'if (r1.maxHp !== 2000) fail("panel maxHp != 2000: " + r1.maxHp);\n'
        'if (r1.defense !== 600) fail("panel defense != 600: " + r1.defense);\n'
        'if (r1.attack !== 0 || r1.physique !== 0 || r1.speed !== 0) fail("unexpected extra stats: " + JSON.stringify(r1));\n'
        '/* (d) 无奇物 -> 面板不动 */\n'
        'var r2 = mk(); YlxwSpiritExtras({ petSpirit:null }, r2);\n'
        'if (r2.spirit !== 166 || r2.maxHp !== 0 || r2.defense !== 0) fail("no-treasure path leaked: " + JSON.stringify(r2));\n'
        '/* (e) 原妖灵四项仍生效（wrap 不吞） */\n'
        'var r3 = mk(); YlxwSpiritExtras({ petSpirit:{ attack:5, defense:6, maxHp:7, speed:8 }, foundationTreasure:"ft_034" }, r3);\n'
        'if (r3.attack !== 5 || r3.defense !== 606 || r3.maxHp !== 2007 || r3.speed !== 8 || r3.spirit !== 291)\n'
        '  fail("base hook chained wrong: " + JSON.stringify(r3));\n'
        '/* (f) 另一件奇物也走同一压缩 */\n'
        'var r4 = mk(); YlxwSpiritExtras({ petSpirit:null, foundationTreasure:"ft_012" }, r4);\n'
        'if (r4.spirit !== 166 + Math.round(VnOld.ft_012.effects.spiritBonus * 0.125))\n'
        '  fail("ft_012 spirit wrong: " + r4.spirit);\n'
        '/* (g) 空/坏入参不炸 */\n'
        'YlxwSpiritExtras(null, mk()); YlxwSpiritExtras({ foundationTreasure:"no_such_id" }, mk());\n'
        'console.log("r181-probe OK");\n'
        'console.log("  entries=" + ko.length + "  spiritNormalized=" + nsp + "  speedNormalized=" + nk);\n'
        'console.log("  ft_034 spiritBonus: " + rawS + " -> " + newS + "  (hp 2000 / def 600 unchanged)");\n'
        'console.log("  panel: spirit 166 -> " + r1.spirit + " (+" + (r1.spirit - 166) + ")  maxHp 0 -> " + r1.maxHp + "  defense 0 -> " + r1.defense);\n'
        'console.log("  petSpirit chain: " + JSON.stringify(r3));\n'
    )
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:500]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 真实数据探针。"""
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r181] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r181] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r181] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r181] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r181] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r181] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _r181_probe(out, s0)
    if ok is False:
        print('[r181] SELFTEST FAIL r181-probe: ' + pmsg)
        return 1
    print('[r181] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print('[r181] probe: ' + pmsg.replace('\n', '\n[r181] probe: '))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r181] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r181] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r181] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r181] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r181] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r181] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-40s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r181-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r181] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-40s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
