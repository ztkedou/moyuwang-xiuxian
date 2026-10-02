# -*- coding: utf-8 -*-
r"""
yl_r131_ext.py — R-131「道友图鉴·缘契里程碑大幅加码 + 上限 100→200」客户端补丁脚本（0.9.13 批次）

需求原文（台账 R-131 · 人物志/道友图鉴，逐字）
--------------------------------------------------------------------------
  「R-084 漏项补做：道友图鉴·缘契里的人物每一段解锁的奖励要扩展到很高且非常丰富
   （缘契值只能靠任务加，每日只有 10 次，获取困难）。当前【小传】50 解锁 随机物品×2、
   【轶事】75 解锁 灵石×267、【秘辛】100 解锁 随机物品×3 与灵石——奖励太少。
   先排查是显示问题还是实际内容未修改，再修。」

设计依据（docs/0.9.13-design/数值表.md §13，逐字）
--------------------------------------------------------------------------
  YLXW_CHAR_DEXMILE 4 档→7 档（25/50/75/100/125/150/200）：
    25  相识        石 600            → 石 2,000                  物品×3 行4
    50  相知【小传】 修为 2,500        → 修为 12,000               物品×4 行5
    75  莫逆【轶事】 石 1,500          → 石 16,000                 物品×5 行5
    100 道侣【秘辛】 石 3,000+修 5,000  → 石 12,000 + 修 25,000     物品×6 行6
    125 生死之交（新增）               → 修为 60,000               物品×6 行6
    150 灵魂伴侣（新增）               → 石 40,000 + 修 30,000     物品×8 行6
    200 天命道侣（新增·满契）           → 石 150,000 + 修 200,000   物品×10 行7
  验算（表原文）：单 NPC 全清 灵 5,100→220,000（43x）/ 修 7,500→327,000（44x）/
  物品 18→42 件；档位总值严格递增；25 档 ≤2,500 平缓入口。数值均再 ×YLRF。
  上限 100→200：缘契展示串、aff clamp、100 段判定同步放开（§13.3）。

★ 对数值表 §13.1 排查结论的三点实况纠正（2026-10-02 对 0.9.12 产物逐字节实测，
  以实测为准；结论已记拍板文件）：
  1. 「轶事段不存在」已过时：0.9.12 中【轶事】75 段**已存在**（R-059 做的，
     selBlock 四段文案 25/50/75/100 齐全，死面板+T6 各一份 = ×2）。
     「补 75 段文案」一项已满足，无需再做。
  2. 「段位解锁零奖励」需修正为「两侧分账」：图鉴侧真实发放 = YLXW_CHAR_DEXMILE
     （chardex101，chips 动态遍历表）；**用户抱怨的三个数字（×2 / 灵石×267 / ×3与灵石）
     实为右侧人物志 R-059 解锁档 UNL59 = claimUnl 的 rw 提示串**
     （「灵石×267」= Math.round(200 * rf)，rf≈1.335 炼气）。只加码图鉴侧、
     不加码 UNL59，用户验收时看到的数字不会变 ⇒ 本补丁将 UNL59 四档发放
     对齐 DEXMILE 前四档（同段同奖，两侧一致）。UNL59 仍 4 档不扩 7 档：
     右侧 favorability clamp ±100（R-036/R-059 域）⇒ 125+ 档在右侧不可达，
     扩了是死档；图鉴侧 7 档走 DEXMILE（aff clamp 放开到 200）。
  3. 「row7 存在性」实测：YlxwCharRollRow `row = Math.max(1, Math.min(6, row|0))`
     钳 1..6，行 7 不存在 ⇒ 200 档 row:7 收编进行 6（表内直接写 row:6，
     避免留一个靠 clamp 兜底的假值；权重行 6 = [1,12,49,38] 仙品率 38% 为全表最高带）。

★ 补齐 selBlock 四段解锁 hint 的「虚假宣传」（代决）：
  现状四段锁定文案写的奖励数字（灵石×100rf / 物品×2 / 灵石×200rf / 物品×3与灵石）
  与图鉴侧真实发放（DEXMILE 表值）完全不符——玩家解锁后领到的是表值，
  锁定时看到的却是 UNL59 旧值。本补丁把左右面板四段 hint 数字全部对齐新表值
  （×rf 动态，与既有 25/75 段风格一致），解锁前看到什么、解锁后就领到什么。

服务端：零改动（charDex / socialRelations 随 /api/save 整包落库，chardex101 同判例；
  srv 对 charDex 零命中）。

锚点侦察（基线 build/assets/index-v2912-20261002.js，2,259,531 B，
  本地 0.9.12 + R116/R118/R119/R125/R126 成员补丁，2026-10-02 逐字节实测）
--------------------------------------------------------------------------
  · DEXMILE 表声明 `var YLXW_CHAR_DEXMILE = [` ×1（chardex101 注入块 @1334024）；
    4 条旧行各 ×1（对齐空格按产物 repr 逐字转写）。
  · aff clamp（YlxwCharMeet 图鉴分支）×1：`aff[entry.id] = Math.max(-100, Math.min(100, …))`。
  · 「缘契 N / 100」×2（selBlock 头部，死面板+T6；selMet 形态）。
  · 四段 hint：selEntry.* 形态 ×2（图鉴 selBlock，rf 局部量）；
    entry.* 形态 ×2（右侧 BondPanel，YlxwCharRf(p) 内联）——两族字节不同互不撞
    （`? entry.` 不匹配 `? selEntry.`，`+ entry.` 不匹配 `+ selEntry.`，实测计数锁定）。
  · claimUnl 发放分支 ×1（st59/rf59/items59 变量名 R-059 独占）；
    rw 三元 ×1（UNL59 chips 唯一）。
  · 新标识零碰撞：ex59=0 / 「/ 200」=0 / Math.round(2000 * rf)=0（改前逐串断言）。
  · 全仓反查（patches/client/*.py + localtest/yl_*.py + localtest/srv_patch_*.py）：
    r126 门禁只钉 DEXMILE 声明 ==1（本补丁保留声明）；r059 门禁钉「解锁 · 奖励」×16、
    「缘契达 25 解锁」×4、claimUnl/UNL59 函数头与幂等串（本补丁全数保留）；
    r068/chardex101 其余门禁零交集。

跨模块门禁放宽清单（接线人必读，入 dryrun 同步预期；r117「属主侧放宽」同款）
--------------------------------------------------------------------------
  yl_chardex101_ext.py：
    ('R084·详情头部判定×2', 'children: selMet ? ("\u7f18\u5951 " + bond + " / 100") : "\u672a\u7ed3\u8bc6"', 2)
      → 0   （「/ 100」→「/ 200」为 R-131 §13.3 属主改写；新门禁
               R131·缘契展示 /200 ==2 接管）
  其余全部模块门禁零漂移（r059 十六字提示串计数不变、r126 冻结声明仍在，
  改后先验门禁在演练中逐条复核）。

装配顺序（lead 接线 V28_MODULES）
--------------------------------------------------------------------------
  import: from yl_r131_ext import apply as v28_r131_apply  # noqa: E402
  entry : ('r131', v28_r131_apply),
  ★ 必须排在 chardex101 之后（锚点 = DEXMILE 注入块 + r059 的 UNL59/四段文案
    复合产物形态）；建议紧邻 r126 之后的成员段末位。

契约（0.9.13 批次成员补丁脚本，同 yl_r126_ext.py）
--------------------------------------------------------------------------
  · 命令行只有 --src <文件>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r131-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；
    1=断言失败；4=形态异常。
  · 前置依赖：--src 必须是已含 chardex101 + r059 展开块的装配产物
    （0.9.12 原版即满足；0.9.13 装配链中两者均在先，同样满足）。

门禁（apply 后形态；供 dryrun 门禁表原样收录）
--------------------------------------------------------------------------
  见 gates()。数值总账断言在 _assert_values()（表常量级，逐项核对数值表 §13.2）。
"""

import os
import sys
import argparse
import shutil
from datetime import datetime

NL = b"\n"

# ---- P1 DEXMILE 表：4 档 → 7 档（整块替换；旧行对齐空格 = 产物 repr 逐字）----
T_OLD = (rb'var YLXW_CHAR_DEXMILE = [' + NL +
         rb'  { at: 25,  label: "\u76f8\u8bc6", stones: 600,  exp: 0,    n: 3, row: 4 },' + NL +
         rb'  { at: 50,  label: "\u76f8\u77e5", stones: 0,    exp: 2500, n: 4, row: 5 },' + NL +
         rb'  { at: 75,  label: "\u83ab\u9006", stones: 1500, exp: 0,    n: 5, row: 5 },' + NL +
         rb'  { at: 100, label: "\u9053\u4fa3", stones: 3000, exp: 5000, n: 6, row: 6 }' + NL +
         rb'];')
T_NEW = (rb'var YLXW_CHAR_DEXMILE = [' + NL +
         rb'  { at: 25,  label: "\u76f8\u8bc6", stones: 2000,  exp: 0,      n: 3,  row: 4 },' + NL +
         rb'  { at: 50,  label: "\u76f8\u77e5", stones: 0,     exp: 12000,  n: 4,  row: 5 },' + NL +
         rb'  { at: 75,  label: "\u83ab\u9006", stones: 16000, exp: 0,      n: 5,  row: 5 },' + NL +
         rb'  { at: 100, label: "\u9053\u4fa3", stones: 12000, exp: 25000,  n: 6,  row: 6 },' + NL +
         rb'  { at: 125, label: "\u751f\u6b7b\u4e4b\u4ea4", stones: 0,     exp: 60000,  n: 6,  row: 6 },' + NL +
         rb'  { at: 150, label: "\u7075\u9b42\u4f34\u4fa3", stones: 40000, exp: 30000,  n: 8,  row: 6 },' + NL +
         rb'  { at: 200, label: "\u5929\u547d\u9053\u4fa3", stones: 150000, exp: 200000, n: 10, row: 6 }' + NL +
         rb'];')

# ---- P2 图鉴 aff clamp 上限 100→200（YlxwCharMeet 图鉴分支，×1）----
C_OLD = rb'aff[entry.id] = Math.max(-100, Math.min(100, (Number(aff[entry.id]) || 0) + gain));'
C_NEW = rb'aff[entry.id] = Math.max(-100, Math.min(200, (Number(aff[entry.id]) || 0) + gain));'

# ---- P3 缘契展示上限（selBlock 头部，死面板+T6 ×2）----
H_OLD = rb'("\u7f18\u5951 " + bond + " / 100")'
H_NEW = rb'("\u7f18\u5951 " + bond + " / 200")'

# ---- P4~P7 四段解锁 hint 对齐新表值（左 selBlock selEntry.*×rf ×2 / 右 BondPanel entry.*×Rf ×2）----
# 25 相识：石 600→2000
S25_OLD = (rb'bond >= 25 ? selEntry.desc : "\u7f18\u5951\u8fbe 25 \u89e3\u9501 \u00b7 \u5956\u52b1 \u7075\u77f3\u00d7" + Math.round(100 * rf)')
S25_NEW = (rb'bond >= 25 ? selEntry.desc : "\u7f18\u5951\u8fbe 25 \u89e3\u9501 \u00b7 \u5956\u52b1 \u7075\u77f3\u00d7" + Math.round(2000 * rf)')
B25_OLD = (rb'bond >= 25 ? entry.desc : "\u7f18\u5951\u8fbe 25 \u89e3\u9501 \u00b7 \u5956\u52b1 \u7075\u77f3\u00d7" + Math.round(100 * YlxwCharRf(p))')
B25_NEW = (rb'bond >= 25 ? entry.desc : "\u7f18\u5951\u8fbe 25 \u89e3\u9501 \u00b7 \u5956\u52b1 \u7075\u77f3\u00d7" + Math.round(2000 * YlxwCharRf(p))')
# 50 小传：物×2 → 修 12000 + 物×4
S50_OLD = (rb'bond >= 50 ? selEntry.bio : "\u7f18\u5951\u8fbe 50 \u89e3\u9501 \u00b7 \u5956\u52b1 \u968f\u673a\u7269\u54c1\u00d72"')
S50_NEW = (rb'bond >= 50 ? selEntry.bio : "\u7f18\u5951\u8fbe 50 \u89e3\u9501 \u00b7 \u5956\u52b1 \u4fee\u4e3a\u00d7" + Math.round(12000 * rf) + " \u4e0e\u968f\u673a\u7269\u54c1\u00d74"')
B50_OLD = (rb'bond >= 50 ? entry.bio : "\u7f18\u5951\u8fbe 50 \u89e3\u9501 \u00b7 \u5956\u52b1 \u968f\u673a\u7269\u54c1\u00d72"')
B50_NEW = (rb'bond >= 50 ? entry.bio : "\u7f18\u5951\u8fbe 50 \u89e3\u9501 \u00b7 \u5956\u52b1 \u4fee\u4e3a\u00d7" + Math.round(12000 * YlxwCharRf(p)) + " \u4e0e\u968f\u673a\u7269\u54c1\u00d74"')
# 75 轶事：石 200→16000 + 物×5
S75_OLD = (rb'bond >= 75 ? ("\u4eba\u9001\u96c5\u53f7\u300c" + selEntry.title + "\u300d\uff0c\u7f18\u8d77\uff1a" + selEntry.hint) : "\u7f18\u5951\u8fbe 75 \u89e3\u9501 \u00b7 \u5956\u52b1 \u7075\u77f3\u00d7" + Math.round(200 * rf)')
S75_NEW = (rb'bond >= 75 ? ("\u4eba\u9001\u96c5\u53f7\u300c" + selEntry.title + "\u300d\uff0c\u7f18\u8d77\uff1a" + selEntry.hint) : "\u7f18\u5951\u8fbe 75 \u89e3\u9501 \u00b7 \u5956\u52b1 \u7075\u77f3\u00d7" + Math.round(16000 * rf) + " \u4e0e\u968f\u673a\u7269\u54c1\u00d75"')
B75_OLD = (rb'bond >= 75 ? ("\u4eba\u9001\u96c5\u53f7\u300c" + entry.title + "\u300d\uff0c\u7f18\u8d77\uff1a" + entry.hint) : "\u7f18\u5951\u8fbe 75 \u89e3\u9501 \u00b7 \u5956\u52b1 \u7075\u77f3\u00d7" + Math.round(200 * YlxwCharRf(p))')
B75_NEW = (rb'bond >= 75 ? ("\u4eba\u9001\u96c5\u53f7\u300c" + entry.title + "\u300d\uff0c\u7f18\u8d77\uff1a" + entry.hint) : "\u7f18\u5951\u8fbe 75 \u89e3\u9501 \u00b7 \u5956\u52b1 \u7075\u77f3\u00d7" + Math.round(16000 * YlxwCharRf(p)) + " \u4e0e\u968f\u673a\u7269\u54c1\u00d75"')
# 100 秘辛：物×3与灵石 → 石 12000、修 25000、物×6
S100_OLD = (rb'bond >= 100 ? selEntry.secret : "\u7f18\u5951\u8fbe 100 \u89e3\u9501 \u00b7 \u5956\u52b1 \u968f\u673a\u7269\u54c1\u00d73 \u4e0e\u7075\u77f3"')
S100_NEW = (rb'bond >= 100 ? selEntry.secret : "\u7f18\u5951\u8fbe 100 \u89e3\u9501 \u00b7 \u5956\u52b1 \u7075\u77f3\u00d7" + Math.round(12000 * rf) + "\u3001\u4fee\u4e3a\u00d7" + Math.round(25000 * rf) + " \u4e0e\u968f\u673a\u7269\u54c1\u00d76"')
B100_OLD = (rb'bond >= 100 ? entry.secret : "\u7f18\u5951\u8fbe 100 \u89e3\u9501 \u00b7 \u5956\u52b1 \u968f\u673a\u7269\u54c1\u00d73 \u4e0e\u7075\u77f3"')
B100_NEW = (rb'bond >= 100 ? entry.secret : "\u7f18\u5951\u8fbe 100 \u89e3\u9501 \u00b7 \u5956\u52b1 \u7075\u77f3\u00d7" + Math.round(12000 * YlxwCharRf(p)) + "\u3001\u4fee\u4e3a\u00d7" + Math.round(25000 * YlxwCharRf(p)) + " \u4e0e\u968f\u673a\u7269\u54c1\u00d76"')

# ---- P8 claimUnl 发放分支加码（R-059 域属主代决，×1；UNL59 档位表不动）----
U_OLD = (rb'    var st59 = 0, items59 = [];' + NL +
         rb'    if (at === 25) st59 = Math.round(100 * rf59);' + NL +
         rb'    else if (at === 50) items59 = YlxwCharRollRow(3, 2);' + NL +
         rb'    else if (at === 75) st59 = Math.round(200 * rf59);' + NL +
         rb'    else { items59 = YlxwCharRollRow(5, 3); st59 = Math.round(300 * rf59); }')
U_NEW = (rb'    var st59 = 0, ex59 = 0, items59 = [];' + NL +
         rb'    if (at === 25) st59 = Math.round(2000 * rf59);' + NL +
         rb'    else if (at === 50) { ex59 = Math.round(12000 * rf59); items59 = YlxwCharRollRow(5, 4); }' + NL +
         rb'    else if (at === 75) { st59 = Math.round(16000 * rf59); items59 = YlxwCharRollRow(5, 5); }' + NL +
         rb'    else { st59 = Math.round(12000 * rf59); ex59 = Math.round(25000 * rf59); items59 = YlxwCharRollRow(6, 6); }')

# ---- P9 claimUnl updater 落修为（×1）----
UP_OLD = (rb'      if (st59) nx59.spiritStones = Math.max(0, (Number(prev.spiritStones) || 0) + st59);' + NL +
          rb'      if (items59.length) nx59.inventory = YlxwCharPushItems(prev.inventory, items59);')
UP_NEW = (rb'      if (st59) nx59.spiritStones = Math.max(0, (Number(prev.spiritStones) || 0) + st59);' + NL +
          rb'      if (ex59) nx59.exp = Math.max(0, (Number(prev.exp) || 0) + ex59);' + NL +
          rb'      if (items59.length) nx59.inventory = YlxwCharPushItems(prev.inventory, items59);')

# ---- P10 claimUnl 日志补修为（×1；「解锁奖励已发放」日志头不动）----
L_OLD = rb'if (st59) parts59.push("\u7075\u77f3 \u00d7" + st59);'
L_NEW = (rb'if (st59) parts59.push("\u7075\u77f3 \u00d7" + st59);' + NL +
         rb'    if (ex59) parts59.push("\u4fee\u4e3a \u00d7" + ex59);')

# ---- P11 UNL59 chips rw 提示对齐（×1；「解锁 · 奖励」×16 / 「缘契达 25 解锁」×4 不变）----
RW_OLD = (rb'      var rw = at === 25 ? ("\u7075\u77f3 \u00d7" + Math.round(100 * YlxwCharRf(p))) :' + NL +
          rb'               at === 50 ? "\u968f\u673a\u7269\u54c1 \u00d72" :' + NL +
          rb'               at === 75 ? ("\u7075\u77f3 \u00d7" + Math.round(200 * YlxwCharRf(p))) : "\u968f\u673a\u7269\u54c1 \u00d73 \u4e0e\u7075\u77f3";')
RW_NEW = (rb'      var rw = at === 25 ? ("\u7075\u77f3 \u00d7" + Math.round(2000 * YlxwCharRf(p))) :' + NL +
          rb'               at === 50 ? ("\u4fee\u4e3a \u00d7" + Math.round(12000 * YlxwCharRf(p)) + " \u4e0e\u968f\u673a\u7269\u54c1 \u00d74") :' + NL +
          rb'               at === 75 ? ("\u7075\u77f3 \u00d7" + Math.round(16000 * YlxwCharRf(p)) + " \u4e0e\u968f\u673a\u7269\u54c1 \u00d75") : ("\u7075\u77f3 \u00d7" + Math.round(12000 * YlxwCharRf(p)) + "\u3001\u4fee\u4e3a \u00d7" + Math.round(25000 * YlxwCharRf(p)) + " \u4e0e\u968f\u673a\u7269\u54c1 \u00d76");')

# ---- 全部替换（顺序无关，锚点互不重叠；expect 见 REPLACES 第三元）----
REPLACES = [
    ('P1 表7档',        T_OLD, T_NEW, 1),
    ('P2 aff clamp200', C_OLD, C_NEW, 1),
    ('P3 缘契/200',     H_OLD, H_NEW, 2),
    ('P4a sel25',       S25_OLD, S25_NEW, 2),
    ('P4b bond25',      B25_OLD, B25_NEW, 2),
    ('P5a sel50',       S50_OLD, S50_NEW, 2),
    ('P5b bond50',      B50_OLD, B50_NEW, 2),
    ('P6a sel75',       S75_OLD, S75_NEW, 2),
    ('P6b bond75',      B75_OLD, B75_NEW, 2),
    ('P7a sel100',      S100_OLD, S100_NEW, 2),
    ('P7b bond100',     B100_OLD, B100_NEW, 2),
    ('P8 claimUnl加码', U_OLD, U_NEW, 1),
    ('P9 updater修为',  UP_OLD, UP_NEW, 1),
    ('P10 日志修为',    L_OLD, L_NEW, 1),
    ('P11 rw提示',      RW_OLD, RW_NEW, 1),
]

# ---- 已补丁检测（改前应全 0、改后各恰 1；铁律⑥独有信号；不选双面板同文串）----
ALREADY = [
    rb'{ at: 200, label: "\u5929\u547d\u9053\u4fa3", stones: 150000, exp: 200000, n: 10, row: 6 }',
    rb'Math.min(200, (Number(aff[entry.id]) || 0) + gain)',
    rb'if (ex59) nx59.exp = Math.max(0, (Number(prev.exp) || 0) + ex59);',
    rb'var st59 = 0, ex59 = 0, items59 = [];',
]

# ---- 冻结面前置（改前必须逐位在位；改后逐位保留）----
FR_BOND_MILE = rb'var YLXW_CHAR_BOND_MILE = ['                 # R-036 冻结表（本轮只登记不动，§13.3 挂账）
FR_DEX_MILE_DEF = rb'var YLXW_CHAR_DEX_MILE = ['               # 收集表声明（r126 门禁共面）
FR_DEX_MILE_AT3 = rb'{ at: 3, label: "\u4e09\u53cb", stones: 1500, exp: 1000, item: null },'  # r126 产物新值
FR_ROLLROW_CLAMP = rb'row = Math.max(1, Math.min(6, row | 0));'  # 行钳 1..6（row7 收编证据）
FR_RAR_DEF = rb'var YLXW_CHAR_DROP_RAR = ['                    # 权重矩阵声明
FR_DROP_N = rb'var YLXW_CHAR_DROP_N = [2, 3, 4, 5];'           # 右侧里程碑件数表（R-036 拍板值）
FR_DEX_DROP_N = rb'var YLXW_CHAR_DEX_DROP_N = [2, 2, 4, 4, 6, 8, 12];'  # r126 门禁共面
FR_CLAIM_FN = rb'function YlxwCharDexMileClaim('               # 图鉴发放函数（表驱动，不加行即生效）
FR_CHIPS_MOUNT = (rb'YlxwCharDexMileChips(p, setP, log, setNotice, selEntry, bond, rf) }) : null')  # ×2
FR_CHIPS_TITLE = rb'\u7f18\u5951\u91cc\u7a0b\u7891\uff08\u5230\u8fbe\u5373\u5728\u56fe\u9274\u9886\u53d6 \u00b7 \u56fe\u9274\u4e13\u5c5e\u5956\u52b1\uff09'
FR_BONDOF = rb'function YlxwCharBondOf('
FR_UNL59 = rb'var UNL59 = [25, 50, 75, 100];'                  # 右侧解锁档 4 档不动（favor clamp 100）
FR_CLAIMUNL = rb'function claimUnl(at) {'
FR_UNL_IDEM = rb'if (m59[String(at)]) return prev;'
FR_AFF_WRITE = rb'd.aff = aff;'                                # chardex101 解耦写入
FR_END101 = rb'/* == end YL_CHARDEX101 == */'
FR_REL_CLAMP = (rb'favorability: Math.min(100, Math.max(-100, (Number(r.favorability) || 0) + g))')  # ×2 右侧 100 上限
FR_REL_WRITE = rb'socialRelations: rels, charDex: d0 });'      # ×2 renwu 门禁共面
FR_MEET_FN = rb'function YlxwCharMeet('
FR_MILE_HINT_UNLOCK = rb'\u89e3\u9501 \u00b7 \u5956\u52b1'     # 「解锁 · 奖励」×16（r059 门禁共面）
FR_MILE_25 = rb'\u7f18\u5951\u8fbe 25 \u89e3\u9501'            # 「缘契达 25 解锁」×4（r059 门禁共面）

# V28_BAN_PATTERNS（交接手册 §2.4）：新字节不得含
BAN = [b'iframe', b'postMessage', b'XMLHttpRequest', b'auth_token', b'X-YL-']

# 数值表 §13.2 权威值（_assert_values 与 ROWS 双向核对）
DESIGN = {
    'at':    [25, 50, 75, 100, 125, 150, 200],
    'stones': [2000, 0, 16000, 12000, 0, 40000, 150000],
    'exp':   [0, 12000, 0, 25000, 60000, 30000, 200000],
    'n':     [3, 4, 5, 6, 6, 8, 10],
    'row':   [4, 5, 5, 6, 6, 6, 6],
    # UNL59 右侧解锁档（代决：对齐 DEXMILE 前四档）
    'unl_stones': [2000, 0, 16000, 12000],
    'unl_exp':    [0, 12000, 0, 25000],
    'unl_n':      [0, 4, 5, 6],
    'unl_row':    [0, 5, 5, 6],
}


def _assert_values():
    """数值表 §13.2 逐项核对（表常量级，静态断言，不依赖 bundle）。"""
    import re as _re
    errs = []
    rows = []
    for ln in T_NEW.split(NL):
        m = _re.search(rb'\{ at: (\d+),\s+label: "((?:\\u[0-9a-f]{4})+)", stones: (\d+),\s+exp: (\d+),\s+n: (\d+),\s+row: (\d+) \}', ln)
        if m:
            rows.append((int(m.group(1)), int(m.group(3)), int(m.group(4)),
                         int(m.group(5)), int(m.group(6)), m.group(2).decode('ascii')))
    if len(rows) != 7:
        errs.append('新表应 7 行，实得 %d' % len(rows))
        return errs
    got = {
        'at': [r[0] for r in rows],
        'stones': [r[1] for r in rows],
        'exp': [r[2] for r in rows],
        'n': [r[3] for r in rows],
        'row': [r[4] for r in rows],
    }
    for k in ('at', 'stones', 'exp', 'n', 'row'):
        if got[k] != DESIGN[k]:
            errs.append('%s 列 %s != 设计 %s' % (k, got[k], DESIGN[k]))
    if sum(got['stones']) != 220000:
        errs.append('灵石总账 %d != 220000' % sum(got['stones']))
    if sum(got['exp']) != 327000:
        errs.append('修为总账 %d != 327000' % sum(got['exp']))
    if sum(got['n']) != 42:
        errs.append('物品总账 %d != 42' % sum(got['n']))
    old_s, old_e, old_n = 5100, 7500, 18
    if old_s >= sum(got['stones']) or old_e >= sum(got['exp']) or old_n >= sum(got['n']):
        errs.append('未体现 43x/44x 加码（旧 5100/7500/18）')
    totals = [s + e for s, e in zip(got['stones'], got['exp'])]
    if totals != sorted(totals) or len(set(totals)) != 7:
        errs.append('档位总值不严格递增: %s' % totals)
    if totals[0] > 2500:
        errs.append('25 档总值 %d > 2500 平缓入口上限' % totals[0])
    # UNL59 代决档（发放分支 U_NEW 逐项）
    unl = [
        (2000, 0, 0, 0),      # at25  石2000
        (0, 12000, 4, 5),     # at50  修12000 物×4 行5
        (16000, 0, 5, 5),     # at75  石16000 物×5 行5
        (12000, 25000, 6, 6),  # at100 石12000 修25000 物×6 行6
    ]
    _m100 = _re.search(rb'else \{ st59 = Math.round\((\d+) \* rf59\); ex59 = Math.round\((\d+) \* rf59\)', U_NEW)
    if (int(_re.search(rb'at === 25\) st59 = Math.round\((\d+) \* rf59\)', U_NEW).group(1)) != unl[0][0] or
            int(_re.search(rb'at === 50\) \{ ex59 = Math.round\((\d+) \* rf59\)', U_NEW).group(1)) != unl[1][1] or
            int(_re.search(rb'at === 75\) \{ st59 = Math.round\((\d+) \* rf59\)', U_NEW).group(1)) != unl[2][0] or
            (int(_m100.group(1)), int(_m100.group(2))) != (unl[3][0], unl[3][1])):
        errs.append('UNL59 发放分支与代决档不符')
    for pat, want in ((rb'RollRow\(5, 4\)', 4), (rb'RollRow\(5, 5\)', 5), (rb'RollRow\(6, 6\)', 6)):
        if len(_re.findall(pat, U_NEW)) != 1:
            errs.append('UNL59 物品行 %s 缺失' % pat)
    return errs


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 表收录。"""
    return [
        # ================= P1 表 =================
        ('R131·表声明仍在', 'var YLXW_CHAR_DEXMILE = [', 1, '==', 'r126 冻结门禁共面'),
        ('R131·at25 新值', 'stones: 2000,  exp: 0,      n: 3,  row: 4', 1, '==', '石600→2000'),
        ('R131·at50 新值', 'stones: 0,     exp: 12000,  n: 4,  row: 5', 1, '==', '修2500→12000'),
        ('R131·at75 新值', 'stones: 16000, exp: 0,      n: 5,  row: 5', 1, '==', '石1500→16000'),
        ('R131·at100 新值', 'stones: 12000, exp: 25000,  n: 6,  row: 6', 1, '==', '石3000+修5000→12000+25000'),
        ('R131·at125 新增', r'\u751f\u6b7b\u4e4b\u4ea4', 1, '==', '修60000 物×6'),
        ('R131·at150 新增', r'\u7075\u9b42\u4f34\u4fa3', 1, '==', '石40000+修30000 物×8'),
        ('R131·at200 新增', r'\u5929\u547d\u9053\u4fa3', 1, '==', '石150000+修200000 物×10（row7 收编行6）'),
        ('R131·旧at25 行清零', 'stones: 600,  exp: 0,    n: 3, row: 4', 0, '==', ''),
        ('R131·旧at50 行清零', 'stones: 0,    exp: 2500, n: 4, row: 5', 0, '==', ''),
        ('R131·旧at75 行清零', 'stones: 1500, exp: 0,    n: 5, row: 5', 0, '==', ''),
        ('R131·旧at100 行清零', 'stones: 3000, exp: 5000, n: 6, row: 6', 0, '==', ''),
        # ================= P2/P3 上限 200 =================
        ('R131·aff clamp200', C_NEW.decode('ascii'), 1, '==', '图鉴缘契上限 100→200'),
        ('R131·aff clamp100 清零', 'Math.min(100, (Number(aff[entry.id])', 0, '==', ''),
        ('R131·缘契展示/200', H_NEW.decode('ascii'), 2, '==', 'selBlock 头部 死+T6'),
        ('R131·缘契展示/100 清零', H_OLD.decode('ascii'), 0, '==', '★ chardex101「R084·详情头部判定×2」属主放宽 2→0'),
        # ================= P4~P7 四段 hint =================
        ('R131·sel25 hint', S25_NEW.decode('ascii'), 2, '==', '图鉴 selBlock ×2'),
        ('R131·bond25 hint', B25_NEW.decode('ascii'), 2, '==', '右侧 BondPanel ×2'),
        ('R131·sel50 hint', S50_NEW.decode('ascii'), 2, '==', ''),
        ('R131·bond50 hint', B50_NEW.decode('ascii'), 2, '==', ''),
        ('R131·sel75 hint', S75_NEW.decode('ascii'), 2, '==', ''),
        ('R131·bond75 hint', B75_NEW.decode('ascii'), 2, '==', ''),
        ('R131·sel100 hint', S100_NEW.decode('ascii'), 2, '==', ''),
        ('R131·bond100 hint', B100_NEW.decode('ascii'), 2, '==', ''),
        ('R131·旧100rf 清零', 'Math.round(100 * rf)', 0, '==', ''),
        ('R131·旧200rf 清零', 'Math.round(200 * rf)', 0, '==', ''),
        ('R131·旧100Rf 清零', 'Math.round(100 * YlxwCharRf(p))', 0, '==', ''),
        ('R131·旧200Rf 清零', 'Math.round(200 * YlxwCharRf(p))', 0, '==', ''),
        # ================= P8~P11 UNL59 =================
        ('R131·claimUnl 新分支', U_NEW.decode('ascii'), 1, '==', 'R-059 域属主代决：对齐 DEXMILE 前四档'),
        ('R131·claimUnl 旧分支清零', U_OLD.decode('ascii'), 0, '==', ''),
        ('R131·ex59 落修为', 'if (ex59) nx59.exp =', 1, '==', '右侧解锁档开始发修为'),
        ('R131·ex59 日志', 'if (ex59) parts59.push(', 1, '==', ''),
        ('R131·旧 RollRow(3,2) 清零', 'YlxwCharRollRow(3, 2)', 0, '==', ''),
        ('R131·旧 RollRow(5,3) 清零', 'YlxwCharRollRow(5, 3)', 0, '==', ''),
        ('R131·rw 新串', RW_NEW.decode('ascii'), 1, '==', 'UNL59 chips 提示对齐'),
        ('R131·rw 旧串清零', RW_OLD.decode('ascii'), 0, '==', ''),
        # ================= 冻结面（改后逐位保留） =================
        ('冻结·R036 BOND_MILE 未动', FR_BOND_MILE.decode('ascii'), 1, '==', '右侧里程碑表（60/120/200/300）本轮登记不动'),
        ('冻结·收集表声明仍在', FR_DEX_MILE_DEF.decode('ascii'), 1, '==', 'r126 门禁共面'),
        ('冻结·r126 at3 新行仍在', FR_DEX_MILE_AT3.decode('ascii'), 1, '==', 'r126 产物'),
        ('冻结·RollRow 行钳 1..6', FR_ROLLROW_CLAMP.decode('ascii'), 1, '==', 'row7 收编证据'),
        ('冻结·权重矩阵声明仍在', FR_RAR_DEF.decode('ascii'), 1, '==', 'R1~R6'),
        ('冻结·右侧件数表仍在', FR_DROP_N.decode('ascii'), 1, '==', 'R-036 拍板值'),
        ('冻结·收集件数表仍在', FR_DEX_DROP_N.decode('ascii'), 1, '==', 'r126 门禁共面'),
        ('冻结·图鉴发放函数仍在', FR_CLAIM_FN.decode('ascii'), 1, '==', '表驱动，扩档自动生效'),
        ('冻结·chips 挂载×2', FR_CHIPS_MOUNT.decode('ascii'), 2, '==', '死面板+T6'),
        ('冻结·chips 标题×2', FR_CHIPS_TITLE.decode('ascii'), 2, '==', '「到达即在图鉴领取」'),
        ('冻结·BondOf 未动', FR_BONDOF.decode('ascii'), 1, '==', '本就无 clamp'),
        ('冻结·UNL59 档位表未动', FR_UNL59.decode('ascii'), 1, '==', '右侧保持 4 档（favor clamp 100）'),
        ('冻结·claimUnl 函数头仍在', FR_CLAIMUNL.decode('ascii'), 1, '==', 'r059 门禁共面'),
        ('冻结·UNL 幂等标记仍在', FR_UNL_IDEM.decode('ascii'), 1, '==', 'r059 门禁共面'),
        ('冻结·Meet 解耦写入仍在', FR_AFF_WRITE.decode('ascii'), 1, '==', 'chardex101 门禁共面'),
        ('冻结·chardex101 结束标记', FR_END101.decode('ascii'), 1, '==', ''),
        ('冻结·右侧 favor clamp100 ×2', FR_REL_CLAMP.decode('ascii'), 2, '==', '右侧人物志上限不动'),
        ('冻结·右侧关系收口 ×2', FR_REL_WRITE.decode('ascii'), 2, '==', 'renwu 门禁共面'),
        ('冻结·Meet 函数头仍在', FR_MEET_FN.decode('ascii'), 1, '==', 'r059 门禁共面'),
        ('冻结·解锁奖励提示 ×16', FR_MILE_HINT_UNLOCK.decode('ascii'), 16, '==', 'r059 门禁共面：4 段 × 4 面板副本'),
        ('冻结·缘契达25解锁 ×4', FR_MILE_25.decode('ascii'), 4, '==', 'r059 门禁共面'),
    ]


def fail(rc, msg):
    print('[yl_r131_ext] FAIL rc=%d: %s' % (rc, msg))
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True, description='R-131 缘契里程碑 7 档加码 + 上限 200 + UNL59 对齐（--src 就地原子补丁）')
    ap.add_argument('--src', required=True, help='要打补丁的 bundle 文件路径（需已含 chardex101 + r059 展开块）')
    a = ap.parse_args(argv)

    errs = _assert_values()
    if errs:
        for e in errs:
            print('[yl_r131_ext] 数值断言: ' + e)
        return fail(1, '数值表 §13.2 逐项核对未过（见上）')

    src = a.src
    if not os.path.isfile(src):
        return fail(2, '文件不存在: %s' % src)

    # 注入串自检：新字节不得含 V28_BAN_PATTERNS、纯 ASCII
    for _, _, new, _e in REPLACES:
        for pat in BAN:
            if pat.lower() in new.lower():
                return fail(1, '新串含禁用模式 %r' % pat)

    with open(src, 'rb') as f:
        b = f.read()

    c_al = [b.count(r) for r in ALREADY]
    c_old = [b.count(o) for _n, o, _nw, _e in REPLACES]
    if max(c_al) > 1:
        return fail(4, '形态异常：已补丁检测串计数 >1（%s），拒绝续写' % (c_al,))
    if all(n == 1 for n in c_al):
        print('[yl_r131_ext] ALREADY-PATCHED（4 检测串全在，未写盘）: %s' % src)
        return 3
    if any(c_al):
        return fail(4, '部分补丁形态（检测=%s），疑似半成品，拒绝续写' % (c_al,))

    # 前置：全部锚点计数逐一核对（expect=1/2）
    for nm, old, _new, want in REPLACES:
        got = b.count(old)
        if got != want:
            return fail(2, '锚点计数不符：%s expect=%d got=%d。文件是否为 chardex101+r059 展开后的装配产物？src=%s'
                        % (nm, want, got, src))
    # 冻结面前置（改前逐位在位）
    pre = [
        ('BOND_MILE', FR_BOND_MILE, 1), ('收集表声明', FR_DEX_MILE_DEF, 1),
        ('r126 at3', FR_DEX_MILE_AT3, 1), ('RollRow 行钳', FR_ROLLROW_CLAMP, 1),
        ('权重矩阵', FR_RAR_DEF, 1), ('右侧件数表', FR_DROP_N, 1),
        ('收集件数表', FR_DEX_DROP_N, 1), ('发放函数', FR_CLAIM_FN, 1),
        ('chips 挂载', FR_CHIPS_MOUNT, 2), ('chips 标题', FR_CHIPS_TITLE, 2),
        ('BondOf', FR_BONDOF, 1), ('UNL59', FR_UNL59, 1),
        ('claimUnl 头', FR_CLAIMUNL, 1), ('UNL 幂等', FR_UNL_IDEM, 1),
        ('aff 写入', FR_AFF_WRITE, 1), ('end101', FR_END101, 1),
        ('favor clamp', FR_REL_CLAMP, 2), ('关系收口', FR_REL_WRITE, 2),
        ('Meet 头', FR_MEET_FN, 1), ('解锁提示', FR_MILE_HINT_UNLOCK, 16),
        ('缘契达25', FR_MILE_25, 4),
    ]
    for nm, nd, want in pre:
        got = b.count(nd)
        if got != want:
            return fail(2, '冻结面前置失败：%s count=%d（期望 %d）' % (nm, got, want))

    # 打补丁（15 组，逐组 expect 复核）
    patched = b
    for nm, old, new, want in REPLACES:
        if patched.count(old) != want:
            return fail(2, '%s 锚点中途失配（不应发生）' % nm)
        patched = patched.replace(old, new)

    # 内存自检：门禁全过才写盘
    for name, needle, want, op, _note in gates():
        got = patched.count(needle.encode('ascii'))
        if op == '==' and got != want:
            return fail(1, '门禁自检 FAIL：%s count=%d（期望 %d）' % (name, got, want))

    # 改前 .bak（只在真写盘前落；重跑不覆盖已有备份）
    bak = '%s.bak-r131-%s' % (src, datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(src, bak)

    # 就地原子写回（同卷临时文件 + os.replace，二进制）
    tmp = '%s.tmp-r131' % src
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

    print('[yl_r131_ext] OK 已补丁并原子写回: %s' % src)
    print('[yl_r131_ext] 备份: %s' % bak)
    print('[yl_r131_ext] 产物新增 %d 字节（DEXMILE 7 档 + 上限 200 + 四段 hint 对齐 + UNL59 对齐）'
          % (len(patched) - len(b)))
    print('[yl_r131_ext] 数值总账：单 NPC 全清 灵 5100→220000（43x）修 7500→327000（44x）物 18→42 件，'
          '发放 ×YLRF（rf=YlxwCharRf/YLRF）；UNL59 右侧四档同批对齐（代决）')
    print('[yl_r131_ext] 门禁表（供 dryrun 收录）:')
    for g in gates():
        print('    %r' % (g,))
    print('[yl_r131_ext] 跨模块放宽（接线人同步 dryrun）:')
    print('    chardex101 (\'R084·详情头部判定×2\', "/ 100 串", 2) → 0（/100→/200 属主改写）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
