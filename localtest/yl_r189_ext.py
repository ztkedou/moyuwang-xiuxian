# -*- coding: utf-8 -*-
r"""
yl_r189_ext.py — R-189：妖灵系统「文案/标签」低风险修正（standalone 纯客户端，纯 UI 文案）

★ 需求原文（用户）：「把妖灵系统整体全部排查重整理设计一下吧，现在的功能按钮和说明文字很混乱，
  很多描述和实际内容都对不上。重点修复这些问题」

★ 本环边界（严格）：**只改文案/标签**。
  · 不改任何数值逻辑、不改服务端、不删功能块、不动其它 `yl_r*_ext.py` / `patches/*` / 台账。
  · **不做**（等用户拍板）：结构重排（把灵宠功能移出妖灵页签）、加成模型二选一、
    互动次数是否改逻辑、R-167 免费喂养是否保留。

==============================================================================
零、改动清单（7 条，全部文案/标签）
==============================================================================
  ① 「灵宠作用 / 妖灵本体」块数量级误导（最重要）
     · 区块标题「灵宠作用」→「灵宠口径参考（非当前加成）」
     · 块首新增一句说明，指向真实数值（上方卡片「主人加成」= 妖灵属性 × 6% × 妖灵之力 PP）
     · 「主战出战转化 50%（与灵宠卡片同源同式）」→「（灵宠口径：主战出战转化 50%）」
     · 「妖灵本体：…」→「灵宠本体参考（物种在归位时确定）：…」
     ★ 定位核实（见 §一）：**「归位后预览」不成立** ⇒ 采用中性措辞「灵宠口径参考（非当前加成）」，
       并在说明里写明「归位后实际结算以灵宠本体属性为准」，**不断言该块等于归位结果**。
  ② 互动次数标题与实际模型不符
     「今日互动已用 X/3 次，还剩 Y 次（每种每日首次免费）」
     → 「免费互动已用 F/3 次（逗弄/梳毛/夜话 每种每日 1 次）· 今日已买 B/2 次」
     ★ F 取 `t.playQuota.tease+brush+talk`（**不是** playTimes：playTimes=min(3,times) 且 times 含已买次数，
       用它当「免费已用」会错；详见 §二·②）。
  ③ 进食行补「今日首次免费」提示
     ★ 取证（见 §三）：服务端 `GET /api/pet` **确实返回 `feedQuota`**（srv 13375-13379）⇒ 客户端消费它，
       在进食三档按钮上标「· 今日首次免费」（仅 `feedQuota.free===true` 时）。
  ④ 术语统一
     · 裸「饱食度」→「喂食度」（全库唯一 1 处，在妖灵卡说明）
     · 记录分类标签（YLXW_KIND）对齐按钮用词：adopt 结缘→收养、feed 喂养→进食、play 嬉戏→互动
  ⑤ 两个「秘径」同名不同物
     · 培养块按钮「派遣秘径（5000 灵石 · 4 小时）」→「妖灵秘径 · 派遣（…）」（服务端 /pet/spirit/exped）
     · 灵宠作用块「秘径单次 …」→「灵兽秘径 · 单次 …」（客户端 YlxwPetPathCost）
     · 连带：培养块秘径行标签「秘径」→「妖灵秘径」；玩法说明③「秘径派遣」→「妖灵秘径 · 派遣」
  ⑥ 玩法记录分类标签缺失/错义（YLXW_KIND）
     · battle:「斗法」→「精魄」（服务端用于「妖灵精魄」里程碑，srv 13532）
     · 补 aptitude:「点化」exped:「秘径」away:「归位」release:「放生」rune:「灵纹」
     · **额外补** merge:「融合」merge_fail:「融合失败」（核实中发现审计遗漏的两类，同属 pet_care_log）
  ⑦ 说明②补全 K 定义
     · 补 品阶K（= 1 + 0.5×品阶序 → 凡 1 / 灵 1.5 / 仙 2.5）、等级K（= 1 + 等级÷99）
     · 资质K 补上限（100 封顶 = 1.5）

==============================================================================
一、① 的定位核实：**「归位后预览」不成立**（实测，非推断）
==============================================================================
  对照链（bundle 字符级实抽 + node 复算，见 §五·探针）：
    · 块内显示 = `YlxwSpiritBonusView(YlxwSpiritPetView(sp))`
        其中 `YlxwSpiritPetView` 用 `st = YlxwPetSpeciesStats(species, lv, 0)`（**lv = 妖灵当前等级**）
    · 归位实际写入 = `YlxwMergeSpiritAway` → `YlxwSpiritToPet(sp, rn)`
        其中 `stats = YlxwPetSpeciesStats(species, 1, 0)`（**硬编码 1 级**）
    · 灵宠加成口径 = `YlxwPetBonusTotal`（直接取 `L.pet.stats`，**不按等级重算**）
    ⇒ 块内用「lv 版属性」，归位得到的是「1 级属性」，两者相差 **≈ 1.08^(lv-1)**（攻/防/血）。

  node 实测（同物种、同品阶、同亲密，仅等级口径不同）：
      雪狐 灵 hunger=8000 bond=500：块内 攻+37136 · 归位实际 攻+90      （≈ 413×）
      月狐 仙 hunger=8000 bond=500：块内 攻+140301 · 归位实际 攻+330    （≈ 425×）
  ⇒ 块内数值既**不等于**当前「主人加成」，也**不等于**归位后实际结算。
  ⇒ 依团队指示：**不写「归位后预览」断言**，改用中性措辞，并显式提示「归位后实际结算以灵宠本体属性为准」。

==============================================================================
二、② 的取值核实
==============================================================================
  · srv `playTimes: Math.min(PET_PLAY_DAILY_MAX, Number(play?.times) || 0)`（13360）
  · srv 免费闸门：每种 1 次/日（13574，`tease/brush/talk` 各封顶 1）
  · srv 买额度闸门：`bought < R018_BUY_DAILY_MAX`（13571，每日最多 2）
  · 关键：买额度分支 `SET times = times + 1, bought = bought + 1`（13571）⇒ **`times` 含已买次数**
    ⇒ `playTimes` 不能当「免费已用」；免费已用 = `tease+brush+talk`（来自 `playQuota`，srv 13367-13372）
  ⇒ F 取 `t.playQuota.tease+brush+talk`；B 取 `t.playQuota.bought`；上限取 `t.consts.playDailyMax` / `t.consts.buyDailyMax`。

==============================================================================
三、③ 的取证结论：**服务端有 `feedQuota` 字段**
==============================================================================
  · srv 13373-13379（GET /api/pet 响应组装）：
        feedQuota: { date: today, used: Math.min(1, Number(feed?.times) || 0), free: (Number(feed?.times) || 0) < 1 }
  · 客户端原产物中 `feedQuota` 出现 **0 次**（未被任何 UI 消费）⇒ 本环消费它，进食三档按钮加「· 今日首次免费」。
  · srv 免费闸门（13483-13488）：`_feedFree = _feedGate.changes > 0; if (_feedFree) _feed.cost = 0;`
    ⇒ 「当日首次进食免灵石」规则确实成立。

==============================================================================
四、⑥/⑦ 的核实（贴 srv 行）
==============================================================================
  · kind 字符串（服务端 `logPetCare` 全部调用点，均写 pet_care_log）：
      adopt    srv 13442   feed   srv 13543   play   srv 13612
      battle   srv 13532（「妖灵精魄」里程碑 ⇒ 语义应为「精魄」而非「斗法」）
      aptitude srv 6541    exped  srv 6588/6629  away srv 6665  release srv 6696  rune srv 6817
      merge / merge_fail   srv 13747（**审计未列**，同写 pet_care_log ⇒ 一并补标签）
  · K 公式（srv 6438-6447）：
      品阶K = 1 + 0.5b（b = 凡0/灵1/仙2）→ 凡 1.00 / 灵 1.50 / 仙 2.50
      等级K = 1 + lv/99（lv 0..99）    羁绊K = 1 + bd/1000（bd 上限 500 ⇒ 1.5）
      资质K = 1 + ap/200（ap 上限 100 ⇒ 1.5）

==============================================================================
五、契约
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 探针）。
  · 就地替换 12 处（见 REPLACEMENTS）；每处打前断言 `count == 1`（锚点纯 ASCII）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r189-<时刻>`。
  · 幂等：产物已含标记 `/*[r189ui]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 探针：从补丁后产物实抽 `var YLXW_KIND = {...}`，node 复算并校验 11 个 key → 标签映射。
  · 不跑网络：只读 --src 指向的本地文件。
  · ★ 冻结针脚只钉本批**不动**的稳定形态，**绝不**钉 `[r180adv*]`/`[r185farm*]`/`[r184wudao]`/
    `[r187guide]`/`[r188med*]`/`[r190feed]`。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# 幂等标记（本批）
IDEMPOTENT_MARK = '/*[r189ui]*/'

# ---- 退役针脚标记（0.9.36 起）----
# 语义：本环（R-189）**排在 R-200 之前**套用 ⇒ apply 时下列 3 条针脚指的老形态**仍在**（count==1）；
#   而 R-200（0.9.36）已把 R-167「当日首次免费」**整条移除**：
#     · 删进食按钮后缀 `+ (fq.free ? " · 今日首次免费" : "")`（转义串 `\u4eca\u65e5\u9996\u6b21\u514d\u8d39`）；
#     · 连带删除因此变成死变量的 `var fq = (t && t.feedQuota) || {};`（`fq.free` 一并消失）。
#   ⇒ 终态这 3 个串必须为 0。
# 单条 (needle, expect) 无法同时满足 apply 态(1) 与终态(0)，故退役 = **终态专用**：
#   · dryrun 读 gates() 在终态复核（期望 0，如实反映 R-200 移除后的形态）；
#   · 本环 apply/--check 时跳过（不检、不计 FAIL），避免「老补丁依赖新补丁」——终态形态由 R-200 自己的门禁负责。
RETIRED_TAG = '【已退役·终态专用】'

# --------------------------------------------------------------------------- 替换项
# ★ 形态约定：bundle 妖灵页签区域中文为**字面 `\uXXXX`**（六字符）⇒ 本 .py 源码保持纯 ASCII，
#   用 `\\uXXXX`（双反斜杠）写出，运行期字符串即 `\uXXXX`。
#   仅 ④「饱食度」是**裸 UTF-8** ⇒ 用 `\uXXXX`（单反斜杠）写出，运行期即真中文字符。

# ---- ① YlxwTSpiritUse：标题 + 新增说明 + 转化率行 ----
R1_OLD = (
    '    e.jsx("span", { className: "text-amber-300 font-bold", children: "\\u7075\\u5ba0\\u4f5c\\u7528" }, "t"),\n'
    '    e.jsx("span", { className: "text-stone-500", children: "\\u4e3b\\u6218\\u51fa\\u6218\\u8f6c\\u5316 " + Math.round(b.rate * 100) + "%\\uff08\\u4e0e\\u7075\\u5ba0\\u5361\\u7247\\u540c\\u6e90\\u540c\\u5f0f\\uff09" }, "r"),'
)
R1_NEW = (
    '    e.jsx("span", { className: "text-amber-300 font-bold", children: "\\u7075\\u5ba0\\u53e3\\u5f84\\u53c2\\u8003\\uff08\\u975e\\u5f53\\u524d\\u52a0\\u6210\\uff09" }, "t"),\n'
    '    e.jsx("span", { className: "w-full text-stone-400", children: "\\u4ee5\\u4e0b\\u4e3a\\u6309\\u300c\\u7075\\u5ba0\\u300d\\u516c\\u5f0f\\u6298\\u7b97\\u7684\\u53c2\\u8003\\u503c\\uff0c\\u5f53\\u524d\\u5996\\u7075\\u672c\\u4f53\\u4e0d\\u63d0\\u4f9b\\u8fd9\\u4e9b\\u52a0\\u6210\\uff1b\\u5f53\\u524d\\u5b9e\\u9645\\u52a0\\u6210\\u89c1\\u4e0a\\u65b9\\u5361\\u7247\\u300c\\u4e3b\\u4eba\\u52a0\\u6210\\u300d\\uff08= \\u5996\\u7075\\u5c5e\\u6027 \\u00d7 6% \\u00d7 \\u5996\\u7075\\u4e4b\\u529b PP\\uff09\\uff0c\\u5f52\\u4f4d\\u540e\\u5b9e\\u9645\\u7ed3\\u7b97\\u4ee5\\u7075\\u5ba0\\u672c\\u4f53\\u5c5e\\u6027\\u4e3a\\u51c6\\u3002" }, "n"),\n'
    '    e.jsx("span", { className: "text-stone-500", children: "\\uff08\\u7075\\u5ba0\\u53e3\\u5f84\\uff1a\\u4e3b\\u6218\\u51fa\\u6218\\u8f6c\\u5316 " + Math.round(b.rate * 100) + "%\\uff09" }, "r"),'
)

# ---- ① YlxwTSpiritUse：本体行标题 ----
R2_OLD = '"\\u5996\\u7075\\u672c\\u4f53\\uff1a", pet.species,'
R2_NEW = '"\\u7075\\u5ba0\\u672c\\u4f53\\u53c2\\u8003\\uff08\\u7269\\u79cd\\u5728\\u5f52\\u4f4d\\u65f6\\u786e\\u5b9a\\uff09\\uff1a", pet.species,'

# ---- ② YlxwTPet 标题：互动次数 ----
R3_OLD = (
    'children: ["\\u4eca\\u65e5\\u4e92\\u52a8\\u5df2\\u7528 ", YlxwNum(t && t.playTimes), "/", '
    'YlxwNum(t && t.consts && t.consts.playDailyMax), " \\u6b21\\uff0c\\u8fd8\\u5269 ", '
    '(YlxwNum(t && t.consts && t.consts.playDailyMax) - YlxwNum(t && t.playTimes)), '
    '" \\u6b21\\uff08\\u6bcf\\u79cd\\u6bcf\\u65e5\\u9996\\u6b21\\u514d\\u8d39\\uff09"]'
)
R3_NEW = (
    'children: ["\\u514d\\u8d39\\u4e92\\u52a8\\u5df2\\u7528 ", '
    '(YlxwNum(t && t.playQuota && t.playQuota.tease) + YlxwNum(t && t.playQuota && t.playQuota.brush) + YlxwNum(t && t.playQuota && t.playQuota.talk)), '
    '"/", YlxwNum(t && t.consts && t.consts.playDailyMax), '
    '" \\u6b21\\uff08\\u9017\\u5f04/\\u68b3\\u6bdb/\\u591c\\u8bdd \\u6bcf\\u79cd\\u6bcf\\u65e5 1 \\u6b21\\uff09\\u00b7 \\u4eca\\u65e5\\u5df2\\u4e70 ", '
    'YlxwNum(t && t.playQuota && t.playQuota.bought), "/", YlxwNum(t && t.consts && t.consts.buyDailyMax), " \\u6b21"]'
)

# ---- ③ YlxwR18FeedRow：消费 feedQuota ----
R4A_OLD = 'var ft = c.feedTiers || {};\n  var keys = ["common", "fine", "immortal"];'
R4A_NEW = 'var ft = c.feedTiers || {};\n  var fq = (t && t.feedQuota) || {};\n  var keys = ["common", "fine", "immortal"];'
R4B_OLD = (
    'children: (tier.name || names[k]) + "\\uff08" + YlxwNum(tier.cost) + " \\u7075\\u77f3 \\u00b7 '
    '\\u5582\\u98df\\u5ea6 +" + YlxwNum(tier.hunger) + "\\uff09",'
)
R4B_NEW = (
    'children: (tier.name || names[k]) + "\\uff08" + YlxwNum(tier.cost) + " \\u7075\\u77f3 \\u00b7 '
    '\\u5582\\u98df\\u5ea6 +" + YlxwNum(tier.hunger) + "\\uff09" + (fq.free ? " \\u00b7 \\u4eca\\u65e5\\u9996\\u6b21\\u514d\\u8d39" : ""),'
)

# ---- ④ 术语：裸「饱食度」→「喂食度」（裸 UTF-8） ----
R5_OLD = '\u9971\u98df\u5ea6\uff1d\u5996\u7075\u7ecf\u9a8c\uff1a\u6bcf 100 \u70b9 = 1 \u7ea7'
R5_NEW = '\u5582\u98df\u5ea6\uff1d\u5996\u7075\u7ecf\u9a8c\uff1a\u6bcf 100 \u70b9 = 1 \u7ea7'

# ---- ⑤ 秘径：妖灵秘径（派遣按钮） ----
R6_OLD = 'children: "\\u6d3e\\u9063\\u79d8\\u5f84\\uff08" + cost + " \\u7075\\u77f3 \\u00b7 4 \\u5c0f\\u65f6\\uff09"'
R6_NEW = 'children: "\\u5996\\u7075\\u79d8\\u5f84 \\u00b7 \\u6d3e\\u9063\\uff08" + cost + " \\u7075\\u77f3 \\u00b7 4 \\u5c0f\\u65f6\\uff09"'
# ---- ⑤ 秘径：妖灵秘径（行标签） ----
R7_OLD = '[e.jsx("span", { className: "text-xs text-stone-400 w-12", children: "\\u79d8\\u5f84" }), node]'
R7_NEW = '[e.jsx("span", { className: "text-xs text-stone-400 w-12", children: "\\u5996\\u7075\\u79d8\\u5f84" }), node]'
# ---- ⑤ 秘径：玩法说明③ ----
R8_OLD = '\\u79d8\\u5f84\\u6d3e\\u9063 5000 \\u7075\\u77f3'
R8_NEW = '\\u5996\\u7075\\u79d8\\u5f84 \\u00b7 \\u6d3e\\u9063 5000 \\u7075\\u77f3'
# ---- ⑤ 秘径：灵兽秘径（灵宠作用块单次行） ----
R9_OLD = 'e.jsx("span", { children: "\\u79d8\\u5f84\\u5355\\u6b21 " + YlxwNum(YlxwPetPathCost(pet))'
R9_NEW = 'e.jsx("span", { children: "\\u7075\\u517d\\u79d8\\u5f84 \\u00b7 \\u5355\\u6b21 " + YlxwNum(YlxwPetPathCost(pet))'

# ---- ⑥ 玩法记录分类标签（+ 本批幂等标记） ----
R10_OLD = 'var YLXW_KIND = { adopt: "\\u7ed3\\u7f18", feed: "\\u5582\\u517b", play: "\\u5b09\\u620f", battle: "\\u6597\\u6cd5" };'
R10_NEW = (
    'var YLXW_KIND = { adopt: "\\u6536\\u517b", feed: "\\u8fdb\\u98df", play: "\\u4e92\\u52a8", battle: "\\u7cbe\\u9b44", '
    'aptitude: "\\u70b9\\u5316", exped: "\\u79d8\\u5f84", away: "\\u5f52\\u4f4d", release: "\\u653e\\u751f", '
    'rune: "\\u7075\\u7eb9", merge: "\\u878d\\u5408", merge_fail: "\\u878d\\u5408\\u5931\\u8d25" };' + IDEMPOTENT_MARK
)

# ---- ⑦ 说明②：补 品阶K / 等级K / 资质K 上限 ----
R11_OLD = (
    '"\\u5996\\u7075\\u4e4b\\u529b PP = \\u54c1\\u9636K \\u00d7 \\u7b49\\u7ea7K \\u00d7 \\u7f81\\u7ecaK \\u00d7 '
    '\\u8d44\\u8d28K\\uff08\\u7f81\\u7ecaK = 1 + \\u7f81\\u7eca\\u00f71000\\uff0c500 \\u5c01\\u9876 = 1.5\\uff1b'
    '\\u8d44\\u8d28K = 1 + \\u8d44\\u8d28\\u00f7200\\uff09\\uff1b\\u4e3b\\u4eba\\u52a0\\u6210 = '
    '\\u5996\\u7075\\u5c5e\\u6027 \\u00d7 6% \\u00d7 PP\\uff0c"'
)
R11_NEW = (
    '"\\u5996\\u7075\\u4e4b\\u529b PP = \\u54c1\\u9636K \\u00d7 \\u7b49\\u7ea7K \\u00d7 \\u7f81\\u7ecaK \\u00d7 '
    '\\u8d44\\u8d28K\\uff08\\u54c1\\u9636K = 1 + 0.5\\u00d7\\u54c1\\u9636\\u5e8f\\uff08\\u51e1 1 / \\u7075 1.5 / \\u4ed9 2.5\\uff09\\uff1b'
    '\\u7b49\\u7ea7K = 1 + \\u7b49\\u7ea7\\u00f799\\uff1b'
    '\\u7f81\\u7ecaK = 1 + \\u7f81\\u7eca\\u00f71000\\uff0c500 \\u5c01\\u9876 = 1.5\\uff1b'
    '\\u8d44\\u8d28K = 1 + \\u8d44\\u8d28\\u00f7200\\uff0c100 \\u5c01\\u9876 = 1.5\\uff09\\uff1b\\u4e3b\\u4eba\\u52a0\\u6210 = '
    '\\u5996\\u7075\\u5c5e\\u6027 \\u00d7 6% \\u00d7 PP\\uff0c"'
)

REPLACEMENTS = [
    ('r1_title', R1_OLD, R1_NEW),
    ('r1_body', R2_OLD, R2_NEW),
    ('r2_play', R3_OLD, R3_NEW),
    ('r3_fq', R4A_OLD, R4A_NEW),
    ('r3_btn', R4B_OLD, R4B_NEW),
    ('r4_baoshi', R5_OLD, R5_NEW),
    ('r5_btn', R6_OLD, R6_NEW),
    ('r5_label', R7_OLD, R7_NEW),
    ('r5_guide', R8_OLD, R8_NEW),
    ('r5_lingshou', R9_OLD, R9_NEW),
    ('r6_kind', R10_OLD, R10_NEW),
    ('r7_note', R11_OLD, R11_NEW),
]

# 冻结针脚（对**输入**校验）：本批不动的稳定形态（绝不含 [r180adv*]/[r185farm*]/[r184wudao]/
# [r187guide]/[r188med*]/[r190feed]）。
FREEZE = [
    ('function YlxwTPet(', 1),
    ('function YlxwTSpiritUse(', 1),
    ('function YlxwSpiritBonusView(', 1),
    ('function YlxwSpiritPetView(', 1),
    ('function YlxwR18Card(', 1),
    ('function YlxwR18FeedRow(', 1),
    ('function YlxwR18PlayRows(', 1),
    ('function YlxwR18ExpedRow(', 1),
    ('function YlxwR18MiscRow(', 1),
    ('function YlxwPetBonusTotal(', 1),
    ('function YlxwSpiritToPet(', 1),
    ('function YlxwMergeSpiritAway(', 1),
    ('function YlxwPetShell(', 1),
    ('var YLXW_PET_LANES = [', 1),
    ('YLXW_PET_LANES[0].rate', 1),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    needle 可为 tuple（多形态合计计数）。"""
    return [
        # ---- 幂等标记 ----
        ('R189\u00b7\u5e42\u7b49\u6807\u8bb0 r189ui', IDEMPOTENT_MARK, 1, '==', '[r189ui] 恰 1 处'),
        # ---- ① ----
        ('R189\u2460\u00b7\u65b0\u6807\u9898\u300c\u53c2\u8003\u975e\u5f53\u524d\u52a0\u6210\u300d' + RETIRED_TAG,
         'children: "\\u7075\\u5ba0\\u53e3\\u5f84\\u53c2\\u8003\\uff08\\u975e\\u5f53\\u524d\\u52a0\\u6210\\uff09" }, "t")', 0, '==',
         'R-197（0.9.35）已把该块标题合法改名为『妖灵折算灵宠属性（参考）』⇒ 旧标题终态归 0；新形态由 R197 自己的门禁负责'),
        ('R189\u2460\u00b7\u65e7\u6807\u9898\u300c\u7075\u5ba0\u4f5c\u7528\u300d\u5df2\u6e05\u96f6',
         'children: "\\u7075\\u5ba0\\u4f5c\\u7528" }, "t")', 0, '==', '旧标题 0 处'),
        ('R189\u2460\u00b7\u65b0\u589e\u8bf4\u660e\u53e5', 'children: "\\u4ee5\\u4e0b\\u4e3a\\u6309\\u300c\\u7075\\u5ba0\\u300d', 1, '==', '块首新增说明'),
        ('R189\u2460\u00b7\u7075\u5ba0\u53e3\u5f84\u8f6c\u5316\u7387\u884c',
         '\\uff08\\u7075\\u5ba0\\u53e3\\u5f84\\uff1a\\u4e3b\\u6218\\u51fa\\u6218\\u8f6c\\u5316 ', 1, '==', '（灵宠口径：主战出战转化 '),
        ('R189\u2460\u00b7\u672c\u4f53\u884c\u6539\u300c\u7075\u5ba0\u672c\u4f53\u53c2\u8003\u300d',
         '"\\u7075\\u5ba0\\u672c\\u4f53\\u53c2\\u8003\\uff08\\u7269\\u79cd\\u5728\\u5f52\\u4f4d\\u65f6\\u786e\\u5b9a\\uff09\\uff1a", pet.species,', 1, '==', '本体行标题'),
        # ---- ② ----
        ('R189\u2461\u00b7\u65b0\u4e92\u52a8\u6807\u9898\u300c\u514d\u8d39\u4e92\u52a8\u5df2\u7528\u300d',
         'children: ["\\u514d\\u8d39\\u4e92\\u52a8\\u5df2\\u7528 ", ', 1, '==', '新标题前缀'),
        ('R189\u2461\u00b7\u4eca\u65e5\u5df2\u4e70\u8ba1\u6570\u5728\u4f4d', '\\uff09\\u00b7 \\u4eca\\u65e5\\u5df2\\u4e70 ", ', 1, '==', '）· 今日已买 '),
        ('R189\u2461\u00b7\u65e7\u4e92\u52a8\u6807\u9898\u5df2\u6e05\u96f6', '"\\u4eca\\u65e5\\u4e92\\u52a8\\u5df2\\u7528 ", ', 0, '==', '旧标题 0 处'),
        ('R189\u2461\u00b7\u65b0\u4e92\u52a8\u6807\u9898\u65e0 playTimes',
         'YlxwNum(t && t.playTimes), "/", YlxwNum(t && t.consts && t.consts.playDailyMax), " \\u6b21\\uff0c\\u8fd8\\u5269 "', 0, '==', '旧「已用/还剩」0 处'),
        # ---- ③ ----
        ('R189\u2462\u00b7\u6d88\u8d39 feedQuota' + RETIRED_TAG, 'var fq = (t && t.feedQuota) || {};', 0, '==',
         'R-200（0.9.36）已整条移除 R-167 当日首免 ⇒ 终态归 0；apply 态仍为 1 故本环跳过'),
        ('R189\u2462\u00b7\u300c\u4eca\u65e5\u9996\u6b21\u514d\u8d39\u300d\u6807\u8bb0' + RETIRED_TAG, '\\u4eca\\u65e5\\u9996\\u6b21\\u514d\\u8d39', 0, '==',
         'R-200（0.9.36）已整条移除 R-167 当日首免 ⇒ 终态归 0；apply 态仍为 1 故本环跳过'),
        ('R189\u2462\u00b7free \u5224\u5b9a\u5728\u4f4d' + RETIRED_TAG, 'fq.free ? ', 0, '==',
         'R-200（0.9.36）已整条移除 R-167 当日首免 ⇒ 终态归 0；apply 态仍为 1 故本环跳过'),
        # ---- ④ ----
        ('R189\u2463\u00b7\u88f8\u300c\u9971\u98df\u5ea6\u300d\u6e05\u96f6', '\u9971\u98df\u5ea6', 0, '==', '裸「饱食度」0 处'),
        ('R189\u2463\u00b7\u88f8\u300c\u5582\u98df\u5ea6\uff1d\u5996\u7075\u7ecf\u9a8c\u300d', '\u5582\u98df\u5ea6\uff1d\u5996\u7075\u7ecf\u9a8c', 1, '==', '已改为「喂食度＝妖灵经验」'),
        # ---- ⑤ ----
        ('R189\u2464\u00b7\u5996\u7075\u79d8\u5f84\u00b7\u6d3e\u9063\u6309\u94ae',
         'children: "\\u5996\\u7075\\u79d8\\u5f84 \\u00b7 \\u6d3e\\u9063\\uff08" + cost', 1, '==', '妖灵秘径 · 派遣（'),
        ('R189\u2464\u00b7\u65e7\u300c\u6d3e\u9063\u79d8\u5f84\uff08\u300d\u5df2\u6e05\u96f6',
         'children: "\\u6d3e\\u9063\\u79d8\\u5f84\\uff08" + cost', 0, '==', '旧按钮 0 处'),
        ('R189\u2464\u00b7\u884c\u6807\u7b7e\u300c\u5996\u7075\u79d8\u5f84\u300d',
         'children: "\\u5996\\u7075\\u79d8\\u5f84" }), node]', 1, '==', '秘径行标签'),
        ('R189\u2464\u00b7\u73a9\u6cd5\u8bf4\u660e\u2462\u300c\u5996\u7075\u79d8\u5f84\u00b7\u6d3e\u9063\u300d',
         '\\u5996\\u7075\\u79d8\\u5f84 \\u00b7 \\u6d3e\\u9063 5000 \\u7075\\u77f3', 1, '==', '玩法说明③'),
        ('R189\u2464\u00b7\u7075\u517d\u79d8\u5f84\u00b7\u5355\u6b21',
         'children: "\\u7075\\u517d\\u79d8\\u5f84 \\u00b7 \\u5355\\u6b21 " + YlxwNum(YlxwPetPathCost(pet))', 1, '==', '灵兽秘径 · 单次'),
        ('R189\u2464\u00b7\u65e7\u300c\u79d8\u5f84\u5355\u6b21\u300d\u5df2\u6e05\u96f6',
         'children: "\\u79d8\\u5f84\\u5355\\u6b21 " + YlxwNum(YlxwPetPathCost(pet))', 0, '==', '旧单次行 0 处'),
        # ---- ⑥ ----
        ('R189\u2465\u00b7battle \u2192 \u7cbe\u9b44', 'battle: "\\u7cbe\\u9b44"', 1, '==', 'battle 标签'),
        ('R189\u2465\u00b7\u65e7\u300c\u6597\u6cd5\u300d\u5df2\u6e05\u96f6', 'battle: "\\u6597\\u6cd5"', 0, '==', '旧 battle 标签 0 处'),
        ('R189\u2465\u00b7\u8865 aptitude', 'aptitude: "\\u70b9\\u5316"', 1, '==', 'aptitude 点化'),
        ('R189\u2465\u00b7\u8865 exped', 'exped: "\\u79d8\\u5f84"', 1, '==', 'exped 秘径'),
        ('R189\u2465\u00b7\u8865 away', 'away: "\\u5f52\\u4f4d"', 1, '==', 'away 归位'),
        ('R189\u2465\u00b7\u8865 release', 'release: "\\u653e\\u751f"', 1, '==', 'release 放生'),
        ('R189\u2465\u00b7\u8865 rune', 'rune: "\\u7075\\u7eb9"', 1, '==', 'rune 灵纹'),
        ('R189\u2465\u00b7\u8865 merge/merge_fail', ('merge: "\\u878d\\u5408"', 'merge_fail: "\\u878d\\u5408\\u5931\\u8d25"'), 2, '>=', 'merge + merge_fail'),
        ('R189\u2465\u00b7adopt\u2192\u6536\u517b', 'adopt: "\\u6536\\u517b"', 1, '==', 'adopt 对齐按钮用词'),
        ('R189\u2465\u00b7feed\u2192\u8fdb\u98df', 'feed: "\\u8fdb\\u98df"', 1, '==', 'feed 对齐按钮用词'),
        ('R189\u2465\u00b7play\u2192\u4e92\u52a8', 'play: "\\u4e92\\u52a8"', 1, '==', 'play 对齐按钮用词'),
        ('R189\u2465\u00b7\u65e7\u300c\u7ed3\u7f18/\u5582\u517b/\u5b09\u620f\u300d\u5df2\u6e05\u96f6',
         ('adopt: "\\u7ed3\\u7f18"', 'feed: "\\u5582\\u517b"', 'play: "\\u5b09\\u620f"'), 0, '==', '旧三标签 0 处'),
        # ---- ⑦ ----
        ('R189\u2466\u00b7\u8865\u54c1\u9636K', '\\u54c1\\u9636K = 1 + 0.5\\u00d7\\u54c1\\u9636\\u5e8f', 1, '==', '品阶K 定义'),
        ('R189\u2466\u00b7\u8865\u7b49\u7ea7K', '\\u7b49\\u7ea7K = 1 + \\u7b49\\u7ea7\\u00f799', 1, '==', '等级K 定义'),
        ('R189\u2466\u00b7\u8865\u8d44\u8d28K \u4e0a\u9650', '\\u8d44\\u8d28K = 1 + \\u8d44\\u8d28\\u00f7200\\uff0c100 \\u5c01\\u9876 = 1.5', 1, '==', '资质K 上限'),
        # ---- 未动（冻结针脚对应产物） ----
        ('R189\u00b7YlxwTPet \u672a\u52a8', 'function YlxwTPet(', 1, '==', '函数体未动'),
        ('R189\u00b7YlxwTSpiritUse \u672a\u52a8', 'function YlxwTSpiritUse(', 1, '==', '函数体未动'),
        ('R189\u00b7YlxwPetBonusTotal \u672a\u52a8', 'function YlxwPetBonusTotal(', 1, '==', '加成链未动'),
        ('R189\u00b7YlxwSpiritToPet \u672a\u52a8', 'function YlxwSpiritToPet(', 1, '==', '归位写入未动'),
        ('R189\u00b7YLXW_PET_LANES \u672a\u52a8', 'var YLXW_PET_LANES = [', 1, '==', '主战位系数未动'),
    ]


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


def _is_patched(s):
    return IDEMPOTENT_MARK in s


def _precheck(s):
    """返回 err（None 表示可打）。"""
    for name, old, new in REPLACEMENTS:
        c = s.count(old)
        if c != 1:
            return '锚点 %s 出现 %d 次（期望 1）' % (name, c)
    for needle, cnt in FREEZE:
        c = s.count(needle)
        if c != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, c, cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时 out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPLACEMENTS:
        out = out.replace(old, new, 1)
    return out, None


def _count(out, needle):
    if isinstance(needle, tuple):
        return sum(out.count(x) for x in needle)
    return out.count(needle)


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        if RETIRED_TAG in label:
            # 退役针脚（终态专用）：本环 apply/--check 时 R-200 尚未套用，首免形态仍在（count==1）⇒ 不检；
            # 终态由复核（期望 0）负责，终态形态由 R-200 自己的门禁负责。
            continue
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    """反向还原：把每个 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


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


def _probe_kind(patched_text):
    """从补丁后产物实抽 `var YLXW_KIND = {...};`，node 复算并校验 11 个 key → 标签映射。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。"""
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    m = re.search(r'var YLXW_KIND = \{[^}]*\};', patched_text)
    if not m:
        return False, 'YLXW_KIND 未找到'
    decl = m.group(0)
    js = (
        decl + '\n'
        'var exp = { adopt:"\\u6536\\u517b", feed:"\\u8fdb\\u98df", play:"\\u4e92\\u52a8", battle:"\\u7cbe\\u9b44",'
        ' aptitude:"\\u70b9\\u5316", exped:"\\u79d8\\u5f84", away:"\\u5f52\\u4f4d", release:"\\u653e\\u751f",'
        ' rune:"\\u7075\\u7eb9", merge:"\\u878d\\u5408", merge_fail:"\\u878d\\u5408\\u5931\\u8d25" };\n'
        'var keys = Object.keys(exp);\n'
        'for (var i=0;i<keys.length;i++){ var k=keys[i]; if (YLXW_KIND[k] !== exp[k]) throw new Error("kind 不符: "+k+" -> "+YLXW_KIND[k]); }\n'
        'if (Object.keys(YLXW_KIND).length !== 11) throw new Error("key 数不符: "+Object.keys(YLXW_KIND).length);\n'
        'console.log("kind-map>> " + JSON.stringify(YLXW_KIND));\n'
    )
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:400]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r189] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r189] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r189] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r189] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r189] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r189] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _probe_kind(out)
    if ok is False:
        print('[r189] SELFTEST FAIL kind-probe: ' + pmsg)
        return 1
    print('[r189] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg, pmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r189] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r189] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r189] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r189] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r189] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r189] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            if RETIRED_TAG in label:
                print('    [SKIP] %s 已退役（终态由 R-200 门禁复核）' % label.replace(RETIRED_TAG, ''))
            else:
                print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r189-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r189] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        if RETIRED_TAG in label:
            print('    [SKIP] %s 已退役（终态由 R-200 门禁复核）' % label.replace(RETIRED_TAG, ''))
        else:
            print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
