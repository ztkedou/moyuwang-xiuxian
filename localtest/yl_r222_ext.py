# -*- coding: utf-8 -*-
r"""
yl_r222_ext.py — R-222 两处客户端显示口径修复（纯客户端）

输入产物：build/assets/index-v2947-20261009.js
          （线上 0.9.47，md5 b0f4de2a25150f1dff7c94d2d967a10b，2,325,448 B）
bundle 内中文**混合两种形态**：多数区段为 `\uXXXX` 转义，少数区段（功法面板 / 难度表 /
人物志面板等）为**字面中文**。锚点形态逐处按实测选取：
  · 转义态 / 纯 ASCII 锚点（源内写成 `\\uXXXX` 字面量或不含中文）：P0（难度表区）、
    P1（功法弹窗 toast，位于手写注入模块）、P3（面板2 主值表达式）；
  · 字面态锚点（含非 ASCII 中文）：P2（面板1 修为条标签）、P4（面板2 明细行）。
所有锚点均从 bundle 原始文本逐字复制，并在 _precheck 中断言形态与唯一性。

==============================================================================
问题 ①：修炼弹窗显示「修炼成功，攻击 +0%」
==============================================================================
【现象】用户截图：一个「成功」弹窗，正文 `修炼成功，攻击 +0%`。`+0%` 看着像 bug。

【生成点（实测定位）】功法面板组件 `YlxwTXinfa087`（手写注入模块）内，修炼按钮回调
  `run(key)` 的 toast 收口（bundle 偏移 @1451614，转义态）：
      var g = await YlxwPost("/gongfa/levelup", { gongfa: key });
      ia("修炼成功" + ((g && g.bonusText) ? ("，" + g.bonusText) : ""));
  —— 即 `修炼成功` 是**拼出来的**（bundle 里 `\u4fee\u70bc\u6210\u529f` 全量仅 2 处：
     本 toast + 功法列表按钮的 onClick 成功文案，均不含 `+0%` 字面），正文由服务端响应
     字段 `g.bonusText` 拼出。

【根因：服务端按「等级加成」出文案，而一次点击不必然升级】
  · `/api/gongfa/levelup` 响应（srv/index_v28.ts:9302-9303）：
        bonusPct:  gongfaBonusPct(key, newLevel)
        bonusText: `${d.statName} +${gongfaPctStr(gongfaBonusPct(key, newLevel))}%`
  · `gongfaBonusPct(key, lv) = (主功法?1:0.2) * lv`（srv:7019）——**纯按等级**，Lv0 ⇒ 0。
  · R-198（C 方案，srv:6964-6970）已把心法改成「点一次 +经验」，`GONGFA_TIER_COST[0]=2250`
    而 `GONGFA_CLICK_COST[0]=750` ⇒ **每级恒 3 次点击**；点击后 `newLevel = gongfaLevelFromExp(exp)`
    （srv:9242），**前 2 次点击等级仍为 0**（750 / 1500 < 2250）。
  ⇒ 新入门功法（Lv0）点击时，服务端如实返回 `bonusPct=0`、`bonusText="攻击 +0%"`；
    客户端原样拼接 ⇒ 弹窗显示「修炼成功，攻击 +0%」。
  ★ 结论：**不是数值没算对**（Lv0 的加成确实为 0，`gongfaBonusPct` 正确），而是
    **展示口径**：把「等级加成（Lv0=0）」当成「本次修炼所得」展示，语义不通。
    ⇒ 属显示问题，本环按「显示口径」修复，**不动任何数值逻辑**（未碰服务端、未碰 exp/等级公式）。

【修法（A 方案：与按钮同口径显示「经验」）】toast 收口改为：
      `修炼成功，经验 +<本次经验增量>`；**仅当真正升级（`g.bonusPct > 0`）**时才追加 `，攻击 +N%`。
      攻击为 0（未入门 / 进度积累）时**不提攻击** —— 上一版的「本次为进度积累（入门后获得加成）」
      措辞已**删除**（不换说法，直接不提）。
  ★ 经验增量的来源（**与按钮同源、同值、同格式化**）：
      按钮文案（bundle @1453051，`YlxwTXinfa087` 行内 `.map` 局部量）：
          `"修炼 +" + YlxwNum(_pc) + " 经验"`，其中
          `_pc = YlxwNum(g.costNext) || YLXW_XINFA_CLICK_FALLBACK[floor(level/10)]`
          （此处 `g` = `/gongfa` **列表行**数据）。
      `/gongfa` 列表（srv:9180）：`costNext = gongfaClickCost(shown + 1)`；
      `/gongfa/levelup` 响应（srv:9240）：`cost = gongfaClickCost(curLevel + 1)`，且
      R-198（C 方案，srv:9241）为 `exp += cost` ⇒ **本次经验增量 ≡ 本次消耗灵石 ≡ 响应 `g.cost`**。
      而 `shown`（列表，srv:9177）与 `curLevel`（升级，srv:9233）同取 `player_gongfa.level`，
      两处 `gongfaClickCost(level + 1)` 是**同一函数、同一入参** ⇒ 响应 `g.cost` 与按钮 `_pc`
      **数值恒等**（`YlxwNum(r){return Number(r)||0}`，同一格式化函数）。
      ⇒ toast 直接用响应字段 `g.cost`（`YlxwNum(g && g.cost)`）：与按钮**同一取值来源**，
        杜绝「按钮说 +750、弹窗说 +800」这类新不一致；**不另算一套**。
  —— 不硬改数字：`g.bonusPct > 0` 分支仍拼服务端权威 `bonusText`
     （= `${statName} +${pct}%`，即 `攻击 +N%`，statName 随功法而变），0 分支不追加任何攻击文本。

==============================================================================
问题 ②：「修炼效率加成」面板不显示难度倍率
==============================================================================
【用户疑问】「上一轮难度选的是最高（困难），改版后修炼效率还是 22%，是因为只有新开号才会加
修炼效率吗？」

【(a) 实测结论：难度倍率对「老号」同样生效，与账号新旧**无关**（严重问题排除）】
  取值器 `YlxwDiffMul(t,r)`（R-218 注入，bundle @295072，标记 `/*YLXW_R218_V2945*/`）取值来源
  依次为：
      (1) 显式入参 t；
      (2) `Be.getState().settings.difficulty`（游戏内权威 store）；
      (3) `localStorage["xiuxian-game-settings"].difficulty`（兜底）；
      (4) 都拿不到 ⇒ 回退 `"normal"`；未知键 ⇒ 回退 normal；难度表不可达/字段非法 ⇒ 1。
  **隔离跑实测**（从 bundle 逐字提取 `YlxwDiffMul` 源码 + `Qr.difficulty` 表，Node 里注入
  mock 的 `Be` / `localStorage` 运行；脚本见 C:/Users/<USER>/AppData/Local/Temp/yl_r222_diffmul.js）：
      explicit easy / normal / hard   ⇒ expMul 1 / 1.5 / 2（stoneMul 同）
      store=easy / normal / hard      ⇒ expMul 1 / 1.5 / 2
      ls=hard / normal / easy         ⇒ expMul 2 / 1.5 / 1
      两者皆空 / 坏 JSON              ⇒ expMul 1.5（回退 normal，= 游戏默认）
  **与账号新旧无关的代码依据**：
      · 取值器源码 `regex /save|player|SAVE/i` 命中 = **false** —— 它**不读任何存档字段**；
      · 难度写入点在 `localStorage.SETTINGS`（bundle @523222：`U.difficulty=D,
        localStorage.setItem(et.SETTINGS,JSON.stringify(U))`），`et.SETTINGS="xiuxian-game-settings"`
        （@247256）—— **难度是设备级设置，不是存档字段**；
      · 实测：给「老号存档 `{realmLevel:99}`」与「新号存档 `{realmLevel:0}`」各塞一个无关的
        `difficulty:"easy"` 字段，二者调用结果**完全一致**（都随 store 的 hard 取 2）。
  ⇒ 用户看到的 22% 不变，**不是**因为老号不加倍，而是**面板显示口径未含难度倍率**
    （R-217/R-218 把倍率加在「修为/灵石入账点」上，没碰这个面板）。排除严重问题。

【(b) 显示点（实测两处，与派单一致）】
  · @836885  人物面板「修为 (Exp)」条下的「修炼效率加成」：`["+",(c.total*100).toFixed(1),"%"]`
  · @1738742 人物志面板「修炼效率加成」卡：主值 `["+",(T.total*100).toFixed(1),"%"]`
    + 明细行（心法/天赋/称号/洞府/协同/羁绊）
  两处的 `total` 均为 `YlxwCharDexRate`（bundle @618285）汇总的**天赋/功法那部分 expRate 之和**，
  **不含**难度倍率（R-218 的难度倍率只乘在入账点上）。

【修法（只改显示口径，不动 total 计算）】
  · P2 面板1：`(c.total*100)` ⇒ `(c.total*YlxwDiffMul(void 0,"expMul")*100)`，并在值后追加
    `（难度×N 名）`；
  · P3 面板2 主值：`(T.total*100)` ⇒ `(T.total*YlxwDiffMul(void 0,"expMul")*100)`；
  · P4 面板2 明细行：追加一段 `难度:×N（名）`（仅在 expMul>1，即非简单档时显示）。
  · P0：在难度表区（`md(...)` 之后、R-218 标记之前）注入中文名取值器
    `YlxwDiffCn()`（读取同一来源，返回 简单/普通/困难），供两处面板注释复用；
    幂等标记 `/*YLXW_R222_V2947*/` 随之落位。
  ⇒ 面板显示值与「实际到账口径（total × 难度 expMul）」一致，并注明难度那部分。
  ★ `total` 的**计算式一字未动**（冻结门禁 FRZ_TOTAL）；R-218 的**入账点逐字未动**
    （冻结门禁 FRZ_R218_*）。未碰服务端、未碰任何数值逻辑。

==============================================================================
契约（standalone，同 localtest/yl_r216_ext.py / yl_r218_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`（缺省自动探测 PATH 上的 node）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r222-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（含门禁未全绿、往返不一致、node --check 失败）。
  · EDITS 四元组 (label, old, new, n)；n=该处旧串期望命中数=替换次数。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证 + node 自检。
  · 纯客户端；不改 build_v26n.py / chain_build.py / dryrun_087.py / sim_remote_check.py /
    任何 build/assets/* / 其它 yl_*_ext.py；不动 r216/r218/r219/r220/r221 已改文案与逻辑。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*YLXW_R222_V2947*/'

# --------------------------------------------------------------------------- P0 难度中文名取值器
# 锚点：难度表区 `md(...)` 定义之后紧接 R-218 标记处（两处皆实测唯一）。
# 在 `md(...)` 与 R-218 标记之间注入 YlxwDiffCn（与 YlxwDiffMul 同源读法：store → localStorage）。
P0_old = ('md=(t="normal")=>Qr.difficulty[t]||Qr.difficulty.normal,'
          '/*YLXW_R218_V2945*/')
P0_new = ('md=(t="normal")=>Qr.difficulty[t]||Qr.difficulty.normal,'
          + MARK +
          'YlxwDiffCn=()=>{try{var d;'
          'try{d=(Be.getState().settings||{}).difficulty}catch(e){}'
          'if(!d){try{var s=localStorage.getItem("xiuxian-game-settings");'
          'if(s){var o=JSON.parse(s);if(o&&o.difficulty)d=o.difficulty}}catch(e){}}'
          'return d==="easy"?"\\u7b80\\u5355":d==="hard"?"\\u56f0\\u96be":"\\u666e\\u901a"}'
          'catch(e){return"\\u666e\\u901a"}},'
          '/*YLXW_R218_V2945*/')

# --------------------------------------------------------------------------- P1 功法弹窗 toast
# 转义态锚点（手写注入模块区，bundle 内为 \uXXXX 字面量）。
# A 方案：与按钮同口径显示「经验」。经验增量取自服务端响应 g.cost
# （= 本次消耗灵石 = 本次 exp 增量，与按钮 _pc = YlxwNum(g.costNext) 同源同值）。
# 仅真正升级（g.bonusPct > 0）时追加服务端 bonusText（=「攻击 +N%」，statName 随功法）。
P1_old = ('ia("\\u4fee\\u70bc\\u6210\\u529f" + ((g && g.bonusText) ? '
          '("\\uff0c" + g.bonusText) : ""));')
P1_new = ('ia("\\u4fee\\u70bc\\u6210\\u529f\\uff0c\\u7ecf\\u9a8c +" + '
          'YlxwNum(g && g.cost) + '
          '((g && g.bonusPct > 0) ? ("\\uff0c" + g.bonusText) : ""));')

# --------------------------------------------------------------------------- P2 面板1（修为条）
# 字面态锚点。值 = total × 难度 expMul，并追加「（难度×N 名）」。
P2_old = ('e.jsx("span",{children:"\u4fee\u70bc\u6548\u7387\u52a0\u6210"}),'
          'e.jsxs("span",{children:["+",(c.total*100).toFixed(1),"%"]})')
P2_new = ('e.jsx("span",{children:"\u4fee\u70bc\u6548\u7387\u52a0\u6210"}),'
          'e.jsxs("span",{children:["+",'
          '(c.total*YlxwDiffMul(void 0,"expMul")*100).toFixed(1),"%",'
          '"\uff08\u96be\u5ea6\u00d7"+YlxwDiffMul(void 0,"expMul").toFixed(1)+'
          '" "+YlxwDiffCn()+"\uff09"]})')

# --------------------------------------------------------------------------- P3 面板2 主值
# 字面态锚点。值 = total × 难度 expMul。
P3_old = '(T.total*100).toFixed(1)'
P3_new = '(T.total*YlxwDiffMul(void 0,"expMul")*100).toFixed(1)'

# --------------------------------------------------------------------------- P4 面板2 明细行
# 字面态锚点。明细行末追加「难度:×N（名）」段（仅 expMul>1 时显示）。
P4_old = 'T.npc>0&&`\u7f81\u7eca:+${(T.cNpc*100).toFixed(1)}%`]'
P4_new = ('T.npc>0&&`\u7f81\u7eca:+${(T.cNpc*100).toFixed(1)}%`,'
          'YlxwDiffMul(void 0,"expMul")>1&&'
          '`\u96be\u5ea6:\u00d7${YlxwDiffMul(void 0,"expMul").toFixed(1)}'
          '\uff08${YlxwDiffCn()}\uff09`]')

EDITS = [
    ('P0 注入难度中文名取值器 YlxwDiffCn（幂等标记位）',            P0_old, P0_new, 1),
    ('P1 功法弹窗「修炼成功，攻击 +0%」→ 经验口径（与按钮同源）',    P1_old, P1_new, 1),
    ('P2 修炼效率面板1（修为条）值计入难度倍率 + 难度注释',          P2_old, P2_new, 1),
    ('P3 修炼效率面板2（人物志）主值计入难度倍率',                   P3_old, P3_new, 1),
    ('P4 修炼效率面板2 明细行追加「难度:×N（名）」',                 P4_old, P4_new, 1),
]

# --------------------------------------------------------------------------- 冻结门禁串（不得改动）
# total 计算式（YlxwCharDexRate 汇总）——证明只改显示口径，未动计算。
# ★ R-228/0.9.50（r225）已把该式**同源化**（拆成具名局部量 `_ar/_ta/…`，**数值零变化**）
#   ⇒ 本环那条「total 计算式未动」冻结门禁**退役**：apply 态仍按旧式校验，终态改检**新式**。
RETIRED_TAG = '【已退役·终态专用】'
FRZ_TOTAL_NEW = 'const _ar=r*d,_ta=a*0.26,_ti=l*0.6,_gr=c*0.6,_sy=Math.min(b,0.1),_np=S*0.32;return{total:_ar+_ta+_ti+_gr+_sy+_np,'
FRZ_TOTAL = ('return{total:r*d+a*0.26+l*0.6+c*0.6+Math.min(b,0.1)+S*0.32,'
             'art:r,talent:a,title:l,grotto:c,synergy:b,npc:S,spiritualRootBonus:d}')
# R-218 标记 + 两个取值器定义（证明 R-218 注入块逐字未动）。
FRZ_R218_MARK = '/*YLXW_R218_V2945*/'
FRZ_R218_MUL_DEF = 'YlxwDiffMul=(t,r)=>{'
FRZ_R218_GAIN_DEF = 'YlxwDiffGain=(x,f)=>{'
# R-218 代表性入账点（证明入账逻辑逐字未动）。
FRZ_R218_MEDIT_EXP = 'v=YlxwDiffGain(v,"expMul")'
FRZ_R218_MEDIT_STONE = '__ylsq=YlxwDiffGain(YlxwMedStone2(q,$.realmLevel,C),"stoneMul")'
FRZ_R218_PC_EXP = ('r.expChange>0&&(r.expChange=Math.min('
                   'YlxwDiffGain(r.expChange,"expMul"),_ylExpCap(t)))')
FRZ_R218_PC_STONE = ('S.spiritStones=Math.max(0,t.spiritStones+'
                     'YlxwDiffGain(r.spiritStonesChange||0,"stoneMul"))')
# 难度表三档倍率（证明未动数值表）。
FRZ_DIFF_EASY = 'expMul:1,stoneMul:1}'
FRZ_DIFF_NORMAL = 'expMul:1.5,stoneMul:1.5}'
FRZ_DIFF_HARD = 'expMul:2,stoneMul:2}'

# 弹窗 A 方案断言串（转义态）——门禁用。
# 新文案前缀「修炼成功，经验 +」（转义态）。
TOAST_EXP = '\\u4fee\\u70bc\\u6210\\u529f\\uff0c\\u7ecf\\u9a8c +'
# 经验增量取值（与按钮 _pc 同源）：响应 g.cost。
TOAST_COST = 'YlxwNum(g && g.cost)'
# 分支 A（升级）：bonusPct > 0 ⇒ 追加服务端 bonusText（=「攻击 +N%」）。
TOAST_BRANCH_LVLUP = '((g && g.bonusPct > 0) ? ("\\uff0c" + g.bonusText) : "")'
# 分支 B（普通点击）：经验恒显、攻击段为空（三元 else 为空串）。
TOAST_BRANCH_EXPONLY = ('YlxwNum(g && g.cost) + '
                        '((g && g.bonusPct > 0) ? ("\\uff0c" + g.bonusText) : "")')
# 上一版（R-222 v1）的 0 加成兜底文案（转义态）——本次**必须清零**（A 方案删掉该措辞）。
TOAST_ZERO = ('\\uff0c\\u672c\\u6b21\\u4e3a\\u8fdb\\u5ea6\\u79ef\\u7d2f'
              '\\uff08\\u5165\\u95e8\\u540e\\u83b7\\u5f97\\u52a0\\u6210\\uff09')

FREEZE = [
    ('冻结·total 计算式未动' + RETIRED_TAG,  FRZ_TOTAL_NEW,        1,
     'R-228 已同源化（拆具名局部量，数值零变化）⇒ 终态期望新式；本环 apply 仍按旧式冻结'),
    ('冻结·R218 标记未动',                 FRZ_R218_MARK,        1),
    ('冻结·R218 YlxwDiffMul 定义未动',     FRZ_R218_MUL_DEF,     1),
    ('冻结·R218 YlxwDiffGain 定义未动',    FRZ_R218_GAIN_DEF,    1),
    ('冻结·R218 打坐修为入账未动',         FRZ_R218_MEDIT_EXP,   1),
    ('冻结·R218 打坐灵石入账未动',         FRZ_R218_MEDIT_STONE, 1),
    ('冻结·R218 历练修为收口未动',         FRZ_R218_PC_EXP,      1),
    ('冻结·R218 历练灵石收口未动',         FRZ_R218_PC_STONE,    1),
    ('冻结·难度表 easy 倍率未动',          FRZ_DIFF_EASY,        1),
    ('冻结·难度表 normal 倍率未动',        FRZ_DIFF_NORMAL,      1),
    ('冻结·难度表 hard 倍率未动',          FRZ_DIFF_HARD,        1),
]


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    g = []
    for label, old, new, n in EDITS:
        g.append(('%s · 新串在位' % label, new, n, '==', ''))
        g.append(('%s · 旧串清零' % label, old, 0, '==', ''))
    # 幂等标记唯一 + 取值器在位
    g.append(('幂等标记唯一', MARK, 1, '==', '/*YLXW_R222_V2947*/'))
    g.append(('难度中文名取值器在位', 'YlxwDiffCn=()=>{', 1, '==', ''))
    # 弹窗 A 方案：新文案在位 + 经验增量与按钮同源 + **两条分支**断言
    g.append(('弹窗·新文案（经验）在位', TOAST_EXP, 1, '==', '修炼成功，经验 +'))
    g.append(('弹窗·经验增量取自响应 g.cost（与按钮 _pc 同源同值）',
              TOAST_COST, 1, '==', ''))
    g.append(('弹窗·分支A 升级：bonusPct>0 追加服务端 bonusText',
              TOAST_BRANCH_LVLUP, 1, '==', '升级时仍出「攻击 +N%」'))
    g.append(('弹窗·分支B 普通点击：经验恒显、攻击段为空',
              TOAST_BRANCH_EXPONLY, 1, '==', ''))
    g.append(('弹窗·旧「攻击 +0%」路径清零', P1_old, 0, '==', '无条件拼 bonusText 已删除'))
    g.append(('弹窗·v1「进度积累」兜底清零', TOAST_ZERO, 0, '==', 'A 方案删除该措辞'))
    # 两处面板难度口径
    g.append(('面板1 计入难度倍率',
              '(c.total*YlxwDiffMul(void 0,"expMul")*100).toFixed(1)', 1, '==', ''))
    g.append(('面板2 计入难度倍率',
              '(T.total*YlxwDiffMul(void 0,"expMul")*100).toFixed(1)', 1, '==', ''))
    g.append(('面板2 难度明细段',
              '\u96be\u5ea6:\u00d7${YlxwDiffMul(void 0,"expMul").toFixed(1)}', 1, '==', ''))
    # 旧显示口径清零
    g.append(('面板1 旧显示清零', '(c.total*100).toFixed(1)', 0, '==', ''))
    g.append(('面板2 旧显示清零', '(T.total*100).toFixed(1)', 0, '==', ''))
    # 冻结
    # ★ 兼容 3 元组 (name, needle, cnt) 与 4 元组 (name, needle, cnt, note)：
    #   0.9.50 为 R-228 预留的那条「冻结·total 计算式未动」带 RETIRED_TAG + note（4 元组），
    #   而旧循环写死 3 元组解包 ⇒ ValueError（此前被更早的 _classify rc=2 掩盖，从未暴露）。
    for item in FREEZE:
        name, needle, cnt = item[0], item[1], item[2]
        note = item[3] if len(item) > 3 else '冻结未动'
        g.append((name, needle, cnt, '==', note))
    return g


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert MARK == '/*YLXW_R222_V2947*/', '幂等标记被改动'
    for name, old, new, n in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old and new, '%s 锚点不得为空' % name
        assert n >= 1, '%s n 必须 >=1' % name
        # old 不得是 new 的子串（否则「旧串清零」门禁在补丁后仍为 1，破坏幂等判定）
        assert old not in new, '%s old 是 new 的子串，会破坏旧串清零门禁' % name
        # 形态一致性：新旧锚点必须同为「转义态（纯 ASCII）」或「字面态（含非 ASCII）」
        ascii_old = all(ord(ch) < 128 for ch in old)
        ascii_new = all(ord(ch) < 128 for ch in new)
        assert ascii_old == ascii_new, '%s 新旧锚点形态（转义/字面）必须一致' % name

    # 形态断言：P0/P1/P3 为纯 ASCII 锚点；P2/P4 为字面中文锚点
    for tag, s in (('P0_old', P0_old), ('P0_new', P0_new),
                   ('P1_old', P1_old), ('P1_new', P1_new),
                   ('P3_old', P3_old), ('P3_new', P3_new)):
        assert all(ord(ch) < 128 for ch in s), '%s 锚点必须纯 ASCII' % tag
    for tag, s in (('P2_old', P2_old), ('P2_new', P2_new),
                   ('P4_old', P4_old), ('P4_new', P4_new)):
        assert any(ord(ch) >= 128 for ch in s), '%s 字面态锚点须含非 ASCII' % tag

    # P0：注入块必须保留 R218 标记、含中文名取值器三档、含幂等标记
    assert MARK in P0_new, 'P0 缺幂等标记'
    assert FRZ_R218_MARK in P0_new, 'P0 未保留 R218 标记'
    assert 'YlxwDiffCn=()=>{' in P0_new, 'P0 缺取值器定义'
    assert 'xiuxian-game-settings' in P0_new, 'P0 取值器缺 localStorage 兜底键'
    assert 'd==="easy"?' in P0_new and 'd==="hard"?' in P0_new, 'P0 取值器缺难度名映射'

    # P1（A 方案）：新串必须含「经验」文案 + 与按钮同源的取值 g.cost + 两条分支，
    #   且不再无条件拼 bonusText、不再出现上一版的「进度积累」兜底措辞。
    assert TOAST_EXP in P1_new, 'P1 缺「修炼成功，经验 +」新文案'
    assert TOAST_COST in P1_new, 'P1 缺经验增量取值 YlxwNum(g && g.cost)'
    assert TOAST_BRANCH_LVLUP in P1_new, 'P1 缺升级分支（bonusPct>0 追加 bonusText）'
    assert 'g.bonusPct > 0' in P1_new, 'P1 缺升级判据 g.bonusPct > 0'
    assert 'g.bonusText' in P1_new, 'P1 升级分支须保留服务端 bonusText（=攻击 +N%）'
    assert '\\u6210\\u529f' in P1_new, 'P1 新串须保留「成功」'
    assert '\\u7ecf\\u9a8c' in P1_new, 'P1 新串须含「经验」'
    assert '((g && g.bonusText)' not in P1_new, 'P1 不得残留无条件拼 bonusText 的旧判据'
    assert TOAST_ZERO not in P1_new, 'P1 不得含上一版「进度积累」兜底文案'
    assert P1_old not in P1_new, 'P1 旧串残留'

    # P2/P3：新串须把 total 乘难度 expMul
    assert 'c.total*YlxwDiffMul(void 0,"expMul")*100' in P2_new, 'P2 未计入难度倍率'
    assert 'T.total*YlxwDiffMul(void 0,"expMul")*100' in P3_new, 'P3 未计入难度倍率'
    assert 'YlxwDiffCn()' in P2_new, 'P2 缺难度名注释'
    assert 'YlxwDiffCn()' in P4_new, 'P4 缺难度名注释'

    # 注入内容不得含网络 / 定时器原语（localStorage 只读兜底是**有意**的，允许）
    for _n, _o, nw, _c in EDITS:
        for ban in ('fetch(', 'XMLHttpRequest', 'setInterval(', 'setTimeout('):
            assert ban not in nw, '注入内容不得含 %s' % ban


def _classify(txt):
    """判定基线态：'patched' / 'baseline' / 'partial'。"""
    n_new_ok = sum(1 for _t, _o, n, c in EDITS if txt.count(n) == c)
    n_old_ok = sum(1 for _t, o, _n, c in EDITS if txt.count(o) == c)
    if n_new_ok == len(EDITS) and n_old_ok == 0:
        return 'patched'
    if n_new_ok == 0 and n_old_ok == len(EDITS):
        return 'baseline'
    return 'partial'


def _node_check(out_bytes, node_bin):
    """对产物跑 `node --check`（fail-closed）；找不到 node 则告警跳过。"""
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check（可用 --node 显式指定）')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r222chk-', suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out_bytes)
        p = subprocess.run([node_bin, '--check', tmp],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            print('  [FAIL] node --check 未通过:\n%s'
                  % p.stderr.decode('utf-8', 'replace')[:2000])
            return False
        print('  [OK] node --check 通过')
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _decode(s):
    """把 \\uXXXX 转成真实字符，便于人读（仅用于打印视图）。"""
    out = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 5 < len(s) and s[i + 1] == 'u':
            try:
                out.append(chr(int(s[i + 2:i + 6], 16)))
                i += 6
                continue
            except ValueError:
                pass
        out.append(s[i])
        i += 1
    return ''.join(out)


def _dump_views(txt0, txt1):
    """打印每个补丁点补丁前后的**解码视图**对照（±80 字符窗口）。"""
    print('  --- 补丁点补丁前后解码视图（±80 字符）---')
    for name, old, new, _n in EDITS:
        i0 = txt0.find(old)
        i1 = txt1.find(new)
        if i0 < 0 or i1 < 0:
            print('    [WARN] %s 未定位到（%d/%d）' % (name, i0, i1))
            continue
        before = txt0[max(0, i0 - 80):i0 + len(old) + 80]
        after = txt1[max(0, i1 - 80):i1 + len(new) + 80]
        print('    · %s' % name)
        print('        前: %s' % _decode(before).replace('\n', '\\n'))
        print('        后: %s' % _decode(after).replace('\n', '\\n'))


def main() -> int:
    ap = argparse.ArgumentParser(description='R-222 两处客户端显示口径修复（--src 补丁）')
    ap.add_argument('--src', required=True,
                    help='装配产物 js（如 build/assets/index-v2947-20261009.js）')
    ap.add_argument('--node', default=None, help='node 可执行文件（缺省自动探测 PATH）')
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

    # 1) 幂等 / 部分补丁态
    st = _classify(txt0)
    if st == 'patched':
        print('[SKIP] source looks already patched（R-222 弹窗 + 两处面板 + 取值器已在位）')
        return 3
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 2) 基线碰撞检查：新串不得已在基线出现
    for _name, _old, new, _n in EDITS:
        c = txt0.count(new)
        if c != 0:
            print('[FAIL] 新串已在基线出现 %d 次，拒绝写盘：%s' % (c, _decode(new)[:60]))
            return 2

    # 3) 锚点计数（rc=2 面）
    for name, old, _new, n in EDITS:
        c = txt0.count(old)
        if c != n:
            print('[FAIL] %s 锚点出现 %d 次（期望 %d）' % (name, c, n))
            return 2

    # 4) 应用
    out_txt = txt0
    for _name, old, new, n in EDITS:
        out_txt = out_txt.replace(old, new, n)
    out = out_txt.encode('utf-8')

    # 5) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        if RETIRED_TAG in label:
            continue  # 退役针脚（终态专用）：本环 apply 时下游尚未套用 ⇒ 不检，终态由复核负责
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        if not good:
            print('  [FAIL] %-44s actual=%d expect %s %d %s'
                  % (label, act, op, exp, note))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  [OK] 门禁全绿（补丁点 %d 处；冻结 %d 项）' % (len(EDITS), len(FREEZE)))

    # 6) 往返自证
    back = out_txt
    for _name, old, new, n in reversed(EDITS):
        assert back.count(new) == n, '往返自证：new 在产物中计数 != %d' % n
        back = back.replace(new, old, n)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 7) node 自检（fail-closed）
    if not _node_check(out, a.node):
        print('[FAIL] node --check 失败，未写盘')
        return 1

    # 8) 视图对照
    _dump_views(txt0, out_txt)

    # 9) 改前 .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r222-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r222-', suffix='.tmp')
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
