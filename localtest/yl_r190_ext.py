# -*- coding: utf-8 -*-
r"""
yl_r190_ext.py — R-190 「灵宠·血量喂养」收益大幅削减 + 血量喂养不给亲密度（standalone 纯客户端）

需求原文（台账 R-190，逐字，二轮加严后）
--------------------------------------------------------------------------
  「自带的灵宠系统，血量喂养的收益太高了，大幅度降低。这个只是个保底的手段，
    因为气血恢复太快了。用这个喂养几乎是无消耗，所以收益要大幅度削减。」
  「R-190 这个因为血量是打坐就可以恢复的，所以几乎没有任何损失。我的想法是让血量来喂养，
    几乎做不到经验的增长，可能几次 100% 血量的投入才能让宠物升一级，这样可以凸显其他喂养
    方式的重要性。任何东西都不想付出也想升级，就慢慢用血量-恢复-喂养靠时间来慢慢磨。」
  「R-190 ③ 血量喂养直接变成不加亲密度，不然血量会变成刷亲密度的工具。」

目标产物：build/assets/index-v2930-20261007.js（0.9.30 刚上线；2,308,071 B；
          md5 4a765aa197694ff3175f29e8a38cc2c2）

==============================================================================
零、取证（全部对 0.9.30 产物字符级实测 + node 真跑）
==============================================================================
── A. 「血量喂养」在哪、收益公式、成本 ──
  客户端（纯前端本地 setState，**无服务端端点**）：
    · 单次 `handleFeedPet:` @1930597（k==="hp" 分支）
    · 批量 `handleBatchFeedHp:` @1933562（「批量喂血」）
  单次公式（k==="hp"）：
      let A=100; const D=1+fe.indexOf(w.realm)*3; const Q=1+w.realmLevel*.6; A=Math.floor(A*D*Q);
      let U=1; k==="hp"?U=1.5:k==="exp"?U=2:k==="item"&&(U=3.5);   // ★ hp 专属倍率
      let Y=Math.floor(A*U*B); const L=.85+Math.random()*.3; Y=Math.floor(Y*L); Y=Math.max(1,Y);
      ⇒ 灵宠经验 = max(1, floor( floor(100*(1+3·境界序)*(1+0.6·层)) · U · rand[0.85,1.15) ))
  批量：同公式，`let G=Math.floor(B*1.5)`，每次 1000 气血循环累加。
  成本：单次闸门 `if(d.hp>=200)`、实扣 `P=Math.max(0,w.hp-1000)` ⇒ **扣 1000 气血**；批量 `C=1000`/次。
        **无冷却、无次数上限**。★ 闸门 200 与实扣 1000 口径不一致（R-017 遗留），本环不动。
  亲密度：单次 `const Z=Math.floor(1+Math.random()*2),te=w.pets.map(...)`（**三类喂养共用**，+1~2）；
        批量 `A+=G,I+=Math.floor(1+Math.random()*2)`（批量喂血专属）。
  ★「收益」= 灵宠经验（pet.exp） + 亲密度。灵宠经验**只来自喂养**（item/exp/hp 三种 + 各自批量；
    另有「灵兽秘径」给一点），无其它独立来源。

── B. 灵宠升级经验曲线（贴代码行）──
  出生：`{id:St(),name:oy(R),species:...,level:1,exp:0,maxExp:60,...}`  ⇒ 起始 maxExp = **60**
  升级：`for(;oe>=W&&F<100;)oe-=W,F+=1,W=Math.floor(W*1.2),K=!0,...` ⇒ 每级 ×1.2，100 级封顶
  ⇒ 从 L 升到 L+1 需经验 maxExp(L) = floor(60 * 1.2^(L-1))：
        L1=60  L2=72  L3=86  L5=124  L8=214  L10=309  L12=445  L15=770
        L20=1916  L25=4769  L30=11868  L40=73488  L50=455021（指数增长）

── C. 「喂满一整条血（100% maxHp）能换多少经验」 ──
  一条满血 = maxHp 点气血；单次喂养固定扣 1000 ⇒ 满血可喂 `maxHp/1000` 次（maxHp<1000 时一次就抽干 ≈1 次）。
  每次经验均值 = A·U（rand 均值 1.0）⇒ 满血经验 = (maxHp/1000)·A·U。
  各境界 maxHp（`Cs` 表 @248084）与 A(r,层1)=floor(160·(1+3r))：
        境界    maxHp   A(层1)  满血可喂次数
        炼气     100     160     0     ★ 闸门 200 > maxHp ⇒ **永远喂不了**
        筑基     250     640     1
        金丹     625    1120     1
        元婴    1250    1600     1.25
        化神    3125    2080     3.125
        合道    7812    2560     7.812
        长生   19531    3040    19.531
  ★ 关键：满血经验随境界暴涨（maxHp×2.5/境 × A 线性）⇒ **同一条 U 下，「满血条数/级」跨境界差约 370 倍**
    （炼气→长生）。没有单一 U 能让「3~5 条满血换 1 级」在所有境界同时成立（见 §三 边界）。

── D. 气血回复速度（「几乎无消耗」证实）──
  打坐 @744438：`R=2+Math.min($.realmLevel*.1,1.5)`（R∈[2,3.5]），`N=Math.floor(Math.floor(maxHp*.01)*R)`
  ⇒ 每跳回 **maxHp 的 2%~3.5%**，冷却 2s（R-022），支持**自动打坐**（autoMeditate，还同时产修为+灵石）。
  ⇒ 元婴及以上，1000 气血几秒~几十秒回满、边际净成本≈0 ⇒ 用户「几乎没有任何损失」**成立**（中高境界）。

==============================================================================
一、改法（4 处就地替换）
==============================================================================
  E1  单次 hp 经验倍率：`k==="hp"?U=1.5:…`   →  `k==="hp"?U=0.03:…`   （1.5→0.03，÷50）
  E2  批量喂血经验倍率：`Math.floor(B*1.5)`   →  `Math.floor(B*0.03)`   （÷50）
  E3  单次亲密度按类型分支：`const Z=Math.floor(1+Math.random()*2)`  →  `const Z=k==="hp"?0:Math.floor(1+Math.random()*2)`
  E4  批量喂血亲密度归零：`A+=G,I+=Math.floor(1+Math.random()*2)`    →  `A+=G,I+=0`
  E5  单次闸门口径对齐实扣（**用户已授权**）：`if(k==="hp")if(d.hp>=200)g=!0,` → `if(k==="hp")if(d.hp>=1000)g=!0,`
      （R-017 把成本 200→1000 时漏改闸门；现闸门=实扣=1000，低境界 maxHp<1000 彻底喂不了。）
      ★ 批量那处**本已一致**：`const C=1000,g=k||Math.floor(d.hp/C)`（闸门与提示文案均用 C=1000）⇒ 不动。
      ★ 未动（R-189 文案范围）：闸门自身两条提示文案仍写「消耗了 200 点气血」「需要 200 点气血」
        —— 属文案，本环按边界**不碰**；已上报 team-lead 待裁。
  ★ 为什么改 U（hp 专属倍率）而不动基础 A=100：A 是三类喂养**共用**基数，动它连带削修为/物品（越界）。
  ★ 亲密度只对 hp 归零：E3 是**按 k 分支**（hp→0，exp/item→原 1~2 逐字不变）；E4 位于
    `handleBatchFeedHp` 内（该函数**永远**是 hp）⇒ 归零不影响任何其它喂养。
  ★ 未动：修为喂养倍率 U=2、物品喂养倍率 U=3.5、基础 A=100、气血成本 1000、闸门 200、
    物品批量亲密度公式、R-167 的灵石三档喂养（服务端）、任何 UI/文案/结构（留给 R-189）。

==============================================================================
二、降幅依据：U=0.03 是怎么反推的（目标「3~5 条满血换 1 级」）
==============================================================================
  口径：满血条数/级 = maxExp(L) / ((maxHp/1000)·A(r,层1)·U)。
  实测表（玩家层数=1；"--"=炼气喂不了）——只列 U=0.03（选定值）：
        境界    L1    L5    L10   L15   L20   L30
        筑基    3.1   6.5   16.1  40.1  99.8  618.1
        金丹    1.8   3.7   9.2   22.9  57.0  353.2
        元婴    1.0   2.1   5.2   12.8  31.9  197.8
        化神    0.3   0.6   1.6   3.9   9.8   60.9
        合道    0.1   0.2   0.5   1.3   3.2   19.8
        长生    0.0   0.1   0.2   0.4   1.1   6.7
  选 U=0.03 的依据：
    · 取「中游玩家网格」= {金丹/元婴/化神} × {L5/L10/L15}，9 格「满血条数/级」的**几何平均**：
        U=0.05→2.55 | U=0.03→**4.20** | U=0.02→6.3 | U=0.01→12.6
      ⇒ U=0.03 的几何均值 ≈ 4.2，正中用户「**几次**（3~5）」。
    · 相对上一版 U=0.3：再 ÷10；相对原版 1.5：÷50。属「大幅度削减」，且高境界绝对降幅更大。
    · 对照：修为喂养 2 / 物品喂养 3.5 ⇒ 血量喂养只给它们的 **1.5% / 0.86%**，彻底沦为「保底中的保底」。

==============================================================================
三、低/高境界边界说明（★ 数学上「3~5 条」无法跨境界统一）
==============================================================================
  · **炼气期**：maxHp=100 < 闸门 200 ⇒ **一次都喂不了**（血量喂养对炼气玩家天然不可用）。
  · **筑基/金丹**（maxHp 250/625 < 1000）：一条满血**只能喂 1 次**（喂完被 floor 到 0）。
    在 U=0.03 下，筑基 L5=6.5 条、L10=16 条、L30=618 条 —— **比「几次」慢得多**（低境界 A 小）。
  · **合道/长生**（maxHp 7812/19531）：一条满血能喂 7.8/19.5 次 ⇒ **比「几次」快得多**
    （L1~L10 常常 <1 条）。这是 maxHp 暴涨带来的**结构性**差异，非 U 能抹平。
  ⇒ 结论：**「3~5 条满血换 1 级」只在「中游玩家（金丹~化神）× 中低宠物等级（L5~L15）」成立**；
    低境界偏慢、高境界偏快。这**正是用户想要的排序**（不想付出就慢慢磨；境界越高宠物越该靠正路喂养），
    故本环**接受该差异**，不做额外封顶/缩放（那会引入结构改动，越界）。
  ⇒ 若用户希望**跨境界完全统一**，唯一办法是把「收益倍率」改成**随境界/上限缩放**的表达式
    （例如除以 maxHp）——那是**结构改动**，不在本环「只动倍率」边界内，**留待用户拍板**。

==============================================================================
四、锚点与冻结针脚（对 build/assets/index-v2930-20261007.js 字符级实测）
==============================================================================
  替换锚点（打前 count==1，打后旧形态清零）：
    E1 OLD = `let U=1;k==="hp"?U=1.5:k==="exp"?U=2:k==="item"&&(U=3.5);`        → 1
    E2 OLD = `let G=Math.floor(B*1.5);`                                          → 1
    E3 OLD = `const Z=Math.floor(1+Math.random()*2),te=w.pets.map(`              → 1
    E4 OLD = `A+=G,I+=Math.floor(1+Math.random()*2)`                             → 1
    E5 OLD = `if(k==="hp")if(d.hp>=200)g=!0,`                                    → 1
  冻结针脚（对**原件**校验 count，全 ASCII；★ 只钉本批 R-180~R-188 不动、本环也不动的形态）：
    `k==="exp"?U=2:k==="item"&&(U=3.5)`              ← 修为/物品经验倍率未动
    `if(k==="hp")P=Math.max(0,w.hp-1000);`           ← 单次气血成本 1000 未动
    `const C=1000,g=k||Math.floor(d.hp/C);`          ← 批量气血成本 1000/次 未动
    `let A=100;`                                     ← 三类共用基础经验未动
    `if(U.id===N){let B=U.exp+A`                     ← 批量喂血经验入账口径未动
    `Math.floor((2+Math.random()*4)*k.length)`       ← 物品批量亲密度公式未动
  ★ 不钉 `handleFeedPet:` / `handleBatchFeedHp:`（各 5 次=1定义+4透传，计数脆弱）；
    也绝不钉任何 R-180~R-188 会改的字符串（避本批 [r180adv] 那种坑）。本环 6 条针脚全在灵宠喂养体内。

==============================================================================
五、契约（照 localtest/yl_r184_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（就地写回）/ `--check`（只校验不写盘）/ `--selftest`（内存自证）。
  · 纯 ASCII 注入；bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；
    首次改写前落 `<src>.bak-r190-<时刻>`。
  · 幂等：产物已含 `[r190feed]` ⇒ SKIP（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 行为探针（node 真跑，从 bundle 里**逐字抽取**真实表达式再 new Function 求值）：
      ① 经验倍率：单次 hp U：改前 1.5→改后 0.03（÷50），exp/item 倍率逐位不变(=2/3.5)；
         批量 hp 倍率 0.03；并打印 7 境界 改前/改后 期望经验对照表。
      ② 亲密度：单次 Z 表达式断言 == `k==="hp"?0:` + 原表达式（⇒ hp 分支 0、其它逐位不变），
         且真跑 200 次：hp 恒 0、exp/item ∈{1,2}；批量断言 `A+=G,I+=0` 且旧式清零。
      ③ 闸门口径：抽「单次闸门值 / 单次实扣值 / 批量成本(闸门)值」三个整数，断言**三者相等**
         （⇒ 证明闸门不是各写各的），并打印该值（=1000）。
  · 不跑网络：只读 --src 指向的本地文件。

==============================================================================
六、自测记录（本机实测）
==============================================================================
  PY   = C:/Users/<USER>/.workbuddy-ai/binaries/python/versions/3.13.12/python.exe
  NODE = C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe
         （★ 本机只有 22.22.2-6；任务书写的 22.22.2-3 不存在，脚本已自动探测）
  [1] --check 全绿；[2] 对 TMP 副本真实写回；[3] node --check rc=0；[4] 复跑 SKIP(rc=3)；
  [5] 删副本与 .bak。详见交付汇报。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r190feed]'
MARK = '/*[r190feed]*/'

# --------------------------------------------------------------------------- 替换项

# E1：单次喂养 hp 经验倍率 1.5 → 0.03（÷50）
E1_OLD = 'let U=1;k==="hp"?U=1.5:k==="exp"?U=2:k==="item"&&(U=3.5);'
E1_NEW = 'let U=1;k==="hp"?U=0.03:k==="exp"?U=2:k==="item"&&(U=3.5);' + MARK

# E2：批量喂血经验倍率 1.5 → 0.03（÷50）
E2_OLD = 'let G=Math.floor(B*1.5);'
E2_NEW = 'let G=Math.floor(B*0.03);' + MARK

# E3：单次亲密度按类型分支（hp→0，exp/item 逐字不变）
E3_OLD = 'const Z=Math.floor(1+Math.random()*2),te=w.pets.map('
E3_NEW = 'const Z=k==="hp"?0:Math.floor(1+Math.random()*2),te=w.pets.map(' + MARK

# E4：批量喂血亲密度归零（handleBatchFeedHp 恒为 hp）
E4_OLD = 'A+=G,I+=Math.floor(1+Math.random()*2)'
E4_NEW = 'A+=G,I+=0' + MARK

# E5：单次闸门口径对齐实扣（200 → 1000；用户已授权）
#     批量闸门 `const C=1000,g=k||Math.floor(d.hp/C)` 本就用 C=1000（含提示文案 ${C}）⇒ **无需改**。
E5_OLD = 'if(k==="hp")if(d.hp>=200)g=!0,'
E5_NEW = 'if(k==="hp")if(d.hp>=1000)g=!0,' + MARK

REPS = [
    ('R190-E1 单次血量喂养经验 1.5→0.03(÷50)', E1_OLD, E1_NEW),
    ('R190-E2 批量喂血经验 1.5→0.03(÷50)', E2_OLD, E2_NEW),
    ('R190-E3 单次亲密度按类型分支(hp→0)', E3_OLD, E3_NEW),
    ('R190-E4 批量喂血亲密度归零', E4_OLD, E4_NEW),
    ('R190-E5 单次闸门口径对齐实扣(200→1000)', E5_OLD, E5_NEW),
]

# 冻结针脚：本环只动上面五处，下列既有形态必须逐字在位（对**原件**校验，全 ASCII）
FREEZE = [
    # ★ 2026-10-08（0.9.38 / R-197）：原针 `k==="exp"?U=2:k==="item"&&(U=3.5)` 的**修为半边**被
    #   r204 合法改写（`U=2` → `U=0.5`）⇒ 本冻结针**收窄到物品半边**（`k==="item"&&(U=3.5)` 跨 r204 恒成立）。
    #   修为倍率的新值由 r204 自己的门禁负责。
    ('k==="item"&&(U=3.5)', 1),                        # 物品经验倍率未动（修为半边已由 r204 改写）
    ('if(k==="hp")P=Math.max(0,w.hp-1000);', 1),        # 单次气血成本 1000 未动（实扣侧）
    ('const C=1000,g=k||Math.floor(d.hp/C);', 1),       # 批量气血成本/闸门 1000 未动（本已一致）
    ('let A=100;', 1),                                  # 三类共用基础经验未动
    ('if(U.id===N){let B=U.exp+A', 1),                  # 批量喂血经验入账口径未动
    ('Math.floor((2+Math.random()*4)*k.length)', 1),    # 物品批量亲密度公式未动
]

# 闸门/实扣口径探针（抽数字对比）
GATE_HEAD = 'if(k==="hp")if(d.hp>='
GATE_STOP = ')g=!0,'
DEDUCT_HEAD = 'if(k==="hp")P=Math.max(0,w.hp-'
DEDUCT_STOP = ');'
BATCHC_RE = r'const C=(\d+),g=k\|\|Math\.floor\(d\.hp/C\);'   # ★ `const C=` 全 bundle 42 处，用整串正则唯一定位

# 行为探针抽取边界（纯 ASCII）
SINGLE_HEAD = 'let A=100;const D=1+fe.indexOf(w.realm)*3'
SINGLE_TAIL = 'k==="item"&&(U=3.5);'
BATCH_HEAD = 'let B=100;const L=1+fe.indexOf(q.realm)*3'
BATCH_STOP = 'const Z=.85'          # 批量随机步之前截断（只取确定性倍率）
Z_HEAD = 'const Z='
Z_STOP = ',te=w.pets.map('   # ★ 唯一（`const Z=` 有 12 处，故用此唯尾锚反查）


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R190·幂等标记恰好 5 处', IDEMPOTENT_MARK, 5, '==', 'E1~E5 各 1'),
        ('R190·E1 单次 hp 经验倍率已降', 'k==="hp"?U=0.03:', 1, '==', 'hp 分支 0.03'),
        ('R190·E2 批量 hp 经验倍率已降', 'Math.floor(B*0.03)', 1, '==', '批量 0.03'),
        ('R190·E3 单次 hp 亲密度分支', 'const Z=k==="hp"?0:', 1, '==', 'hp→0 分支'),
        ('R190·E4 批量 hp 亲密度归零', 'A+=G,I+=0', 1, '==', '批量 hp 亲密度 0'),
        ('R190·E5 单次闸门已对齐实扣 1000', 'if(k==="hp")if(d.hp>=1000)g=!0,', 1, '==', '闸门 1000'),
        ('R190·旧单次经验倍率已清零', 'U=1.5', 0, '==', '旧 1.5 必须消失'),
        ('R190·旧批量经验倍率已清零', 'Math.floor(B*1.5)', 0, '==', '旧 1.5 必须消失'),
        ('R190·旧单次亲密度形态已清零', 'const Z=Math.floor(1+Math.random()*2)', 0, '==', '旧共用行必须消失'),
        ('R190·旧批量亲密度形态已清零', 'A+=G,I+=Math.floor(1+Math.random()*2)', 0, '==', '旧批量行必须消失'),
        ('R190·旧闸门 200 已清零', 'if(d.hp>=200)', 0, '==', '旧闸门必须消失'),
        # ★ 2026-10-08（0.9.38 / R-197）：r204 把修为喂养倍率 `U=2` → `U=0.5`（合法改写）⇒
        #   本针**收窄到物品半边**（`k==="item"&&(U=3.5)` 跨 r204 恒成立）。修为倍率新值由 r204 门禁负责。
        ('R190·物品经验倍率未动（修为半边已由 R-197 改写）', 'k==="item"&&(U=3.5)', 1, '==', '只削 hp；修为倍率见 r204'),
        ('R190·修为/物品亲密度逐字保留', '?0:Math.floor(1+Math.random()*2),te=w.pets.map(', 1, '==', 'exp/item 分支未动'),
    ]
    for needle, cnt in FREEZE:
        g.append(('冻结 ' + needle[:32], needle, cnt, '==', '既有形态'))
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
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node',
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_run(js):
    node = _find_node()
    if not node:
        return None, None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        return r.returncode, r.stdout.decode('utf-8', 'replace'), r.stderr.decode('utf-8', 'replace')
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _node_check(js_text):
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


def _extract(text, head, tail):
    """从 text 抽 [head .. tail 首次出现] 的片段（含两端）。"""
    i = text.find(head)
    if i < 0:
        return None
    j = text.find(tail, i)
    if j < 0:
        return None
    return text[i:j + len(tail)]


def _z_expr(text):
    """抽单次喂养亲密度表达式：定位唯一尾锚 `,te=w.pets.map(`，向前反查 `const Z=`。"""
    j = text.find(Z_STOP)
    if j < 0:
        return None
    i = text.rfind(Z_HEAD, 0, j)
    if i < 0:
        return None
    return text[i + len(Z_HEAD):j]


_PROBE_STUB = r"""
var fe=["\u70bc\u6c14\u671f","\u7b51\u57fa\u671f","\u91d1\u4e39\u671f","\u5143\u5a74\u671f","\u5316\u795e\u671f","\u5408\u9053\u671f","\u957f\u751f\u5883"];
function chk(n,c){if(!c)throw new Error(n);}
// ---- 单次经验：抽真实片段，包成函数求 A 与 U ----
var SINGLE_FRAG = __SINGLE__;
var singleFn = new Function("fe","w","k", SINGLE_FRAG + "return {A:A,U:U};");
function single(k, realmIdx, realmLevel){
  var w={realm:fe[realmIdx], realmLevel:realmLevel, inventory:[]};
  return singleFn(fe, w, k);
}
// ---- 批量经验：抽真实片段（截到随机步之前），求 B 与 G ----
var BATCH_FRAG = __BATCH__;
var batchFn = new Function("fe","q", BATCH_FRAG + ";return {B:B,G:G};");
function batch(realmIdx, realmLevel){
  var q={realm:fe[realmIdx], realmLevel:realmLevel};
  return batchFn(fe, q);
}
// ---- 亲密度：抽真实 Z 表达式求值 ----
var zFn = new Function("k", "return (" + __ZEXPR__ + ");");
var u_orig_hp=__ORIG_HP__, u_new_hp=__NEW_HP__;
chk("改前 hp 经验 U 应为 1.5", Math.abs(u_orig_hp-1.5)<1e-9);
chk("改后 hp 经验 U 应为 0.03", Math.abs(u_new_hp-0.03)<1e-9);
chk("hp 经验降幅应为 1/50", Math.abs(u_new_hp/u_orig_hp-0.02)<1e-9);
chk("修为喂养经验 U 未变(=2)", Math.abs(single("exp",3,1).U-2)<1e-9);
chk("物品喂养经验 U 未变(=3.5)", Math.abs(single("item",3,1).U-3.5)<1e-9);
var bb=batch(3,1);
chk("批量 hp 经验倍率应为 0.03(改后)", Math.abs(bb.G/bb.B-0.03)<1e-9);
// 亲密度：hp 恒 0；exp/item 仍为 1~2（原逻辑）
for(var i=0;i<200;i++){ chk("hp 亲密度应为 0", zFn("hp")===0); }
var saw1=false,saw2=false;
for(var i=0;i<200;i++){
  var a=zFn("exp"), b=zFn("item");
  chk("exp 亲密度应∈{1,2}", a===1||a===2);
  chk("item 亲密度应∈{1,2}", b===1||b===2);
  if(a===1)saw1=true; if(a===2)saw2=true;
}
chk("exp 亲密度仍随机覆盖 1 与 2", saw1&&saw2);
// 打印 7 境界 改前/改后 期望经验（确定性部分 A*U，不含 0.85~1.15 随机）
var names=["炼气","筑基","金丹","元婴","化神","合道","长生"];
console.log("R190-GAIN 境界   改前(A*1.5)  改后(A*0.03)   降幅");
for(var i=0;i<7;i++){
  var s1=single("hp",i,1);
  var A=s1.A, newExp=Math.floor(A*s1.U), origExp=Math.floor(A*1.5);
  console.log("        "+names[i]+"\t"+origExp+"\t\t"+newExp+"\t\t"+(origExp? (100-newExp/origExp*100).toFixed(0)+"%":"-"));
}
console.log("R190-PROBE OK: hp 经验 1.5->0.03(÷50); 修为/物品经验倍率逐位不变; hp 亲密度=0; exp/item 亲密度仍 1~2; 批量经验 0.03");
"""


def _num_between(text, head, stop):
    """抽 [head .. stop) 之间的整数（用于闸门/实扣口径对比）。"""
    i = text.find(head)
    if i < 0:
        return None
    j = text.find(stop, i)
    if j < 0:
        return None
    try:
        return int(text[i + len(head):j])
    except ValueError:
        return None


def _feed_probe(out, s0):
    """真跑：从**原件 s0**与**产物 out** 逐字抽出喂养经验/亲密度表达式再求值对比。"""
    frag_o = _extract(s0, SINGLE_HEAD, SINGLE_TAIL)
    frag_n = _extract(out, SINGLE_HEAD, SINGLE_TAIL)
    bi = out.find(BATCH_HEAD)
    bj = out.find(BATCH_STOP, bi) if bi >= 0 else -1
    batch_n = out[bi:bj] if (bi >= 0 and bj >= 0) else None
    z_o = _z_expr(s0)
    z_n = _z_expr(out)
    if not frag_o or not frag_n or not batch_n or not z_o or not z_n:
        return False, '探针片段抽取失败（SINGLE/BATCH/Z）'
    # 亲密度逐位校验：hp 分支新增、其余分支逐字不变
    if z_n != 'k==="hp"?0:' + z_o:
        return False, '亲密度表达式非「hp→0 + 原式逐字」：%r' % z_n[:120]
    # 闸门口径校验：单次闸门值 == 单次实扣值 == 批量成本/闸门值（三者必须相等）
    gate = _num_between(out, GATE_HEAD, GATE_STOP)
    ded = _num_between(out, DEDUCT_HEAD, DEDUCT_STOP)
    mb = re.search(BATCHC_RE, out)
    bct = int(mb.group(1)) if mb else None
    if gate is None or ded is None or bct is None:
        return False, '闸门/实扣数字抽取失败: gate=%r ded=%r batch=%r' % (gate, ded, bct)
    if not (gate == ded == bct):
        return False, '闸门与实扣口径不一致: gate=%s ded=%s batch=%s' % (gate, ded, bct)

    def hp_u(frag):
        js = ('var fe=["a","b","c","d","e","f","g"];var k="hp";'
              'var w={realm:"a",realmLevel:1};'
              + frag + '\nconsole.log(U);')
        rc, so, se = _node_run(js)
        if rc != 0:
            raise RuntimeError(se.strip()[:200])
        return float(so.strip().splitlines()[-1])

    try:
        u_orig = hp_u(frag_o)
        u_new = hp_u(frag_n)
    except RuntimeError as e:
        return False, 'eval 单次片段失败: %s' % e

    js = (_PROBE_STUB
          .replace('__SINGLE__', json.dumps(frag_n))
          .replace('__BATCH__', json.dumps(batch_n))
          .replace('__ZEXPR__', json.dumps(z_n))
          .replace('__ORIG_HP__', repr(u_orig))
          .replace('__NEW_HP__', repr(u_new)))
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:400]
    return True, (so.strip() + '\nR190-GATE OK: 单次闸门==单次实扣==批量成本/闸门 = %d（口径一致）' % gate)


def selftest(src):
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r190] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r190] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r190] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r190] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r190] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r190] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _feed_probe(out, s0)
    if ok is False:
        print('[r190] SELFTEST FAIL feed_probe: %s' % pmsg)
        return 1
    print('[r190]   feed_probe -> %s' % pmsg)
    print('[r190] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(gates()), len(out) - len(s0), nmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r190] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r190] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r190] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r190] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r190] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r190] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-48s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r190-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r190] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-48s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
