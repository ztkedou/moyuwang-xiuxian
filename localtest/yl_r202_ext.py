# -*- coding: utf-8 -*-
r"""
yl_r202_ext.py — R-195：灵兽（灵宠）喂养「玩家可见文字 vs 实际实现」审计与修复（standalone 纯客户端，纯文案/口径）

★ 用户原话（逐字，唯一依据）：
  「灵兽喂养里面文字内容未更新到最新的实际内容。同时排查一下游戏的所有内容里面，还有没有遗漏的
    文字说明没有更新到最新的地方。」

★ 本环边界（严格）：
  · **只改玩家可见的文案/提示里的数值与规则**，使文字与「实际实现」一致。
  · 唯一一处非文案改动：修为喂养「闸门比例」`.05 → .25`——它**只驱动提示数字**（闸门 `d.exp>=w`
    对 exp≥1 恒真，改前改后都不改变「能否喂养」的行为），目的是让 toast/报错里显示的「消耗了 N 点修为」
    与真实扣除（`w.exp*.25`）一致。见 §三。
  · 不改服务端 / 数值表 / 其它 `yl_r*_ext.py` / `patches/*` / 台账 / `build/assets/*` / 其它玩法。
  · **不碰任何「冷却倒计时渲染」表达式**（免费进食 `cdLeft` / 奇遇抽奖 `" · 冷却 "` / 秘境 `"冷却中"` /
    灵田 `YlxwFtCdText` / 妖巢 `freeCoolLeft`·`paidCoolLeft` / 渡劫 `cooldownLeft`）——那是 R-196 的活。

==============================================================================
零、目标产物与取证口径
==============================================================================
  目标：build/assets/index-v2936-20261008.js（2,315,801 B，Oct 8 11:33）。
  本环全部结论均对该文件**字符级实测**（Python 解码 utf-8 后按 char 计偏移）。
  ★ 灵宠喂养区（UI 说明 + handler）在 bundle 里是**裸 UTF-8 中文**（非 \uXXXX 转义）⇒ 本 .py 源码
    用单反斜杠 `\uXXXX` 写出（运行期即真中文），**锚点源码形态为纯 ASCII**。

==============================================================================
一、根因：R-017 / R-190 改了实现，漏改玩家可见文字（4 条链路）
==============================================================================
  A. 血量喂养**单次成本** 200 → 1000（R-017，patch `patches/client/yl_econ2_ext.py` HPCOST：
       `if(k==="hp")P=Math.max(0,w.hp-200);` → `w.hp-1000`；R-190 E5 再把**闸门** 200→1000）。
     ⇒ 实扣=闸门=1000，但**两条提示文案仍写 200**（R-190 docstring 明确「属文案，本环不碰，已上报待裁」）。
  B. 血量喂养**批量每次气血** 200 → 1000（R-017 BATCHC：`const C=200` → `C=1000`）。
     ⇒ 但 UI 的「批量喂血」按钮说明仍写 `Math.floor(a.hp/200)` 与「每次200点」。
  C. **修为喂养消耗** 5% → 25%（R-017 EXPCOST：`w.exp*.05` → `w.exp*.25`，**只改了实扣侧**）。
     ⇒ UI 说明仍写「消耗 5% 当前修为」，且闸门仍 `.05`（⇒ toast 显示的「消耗了 N 点修为」按 5% 算，与实际 25% 不符）。
  D. **亲密度**：单次 E3.5→E1.5（R-017 INTIM1：`floor(2+rand*4)` → `floor(1+rand*2)` ⇒ +2~5 → +1~2）；
     血量喂养亲密度再归 0（R-190 E3：`const Z=k==="hp"?0:...`）。
     ⇒ UI 三处仍写「+2~5亲密度」（血量应为「不加亲密度」，物品/修为应为「+1~2亲密度」）。

==============================================================================
二、全游戏「玩家可见文字 vs 实际实现」审计（本轮共核 8 个玩法说明块 + 灵宠喂养 + 妖灵面板）
==============================================================================
  ── 不符 · 已改（8 处，全部在「灵宠喂养」）──
   #  位置（实现锚点）                        文案原文（截断）                    实现真值           判定
   1  UI「血量喂养」按钮说明                  「消耗 200 点气血 (…+2~5亲密度)」    1000 / 不加亲密度   不符→改
   2  UI「批量喂血」title（可喂次数）         `…a.hp/200…`                         /1000              不符→改
   3  UI「批量喂血」按钮说明                  「(可喂 a.hp/200 次，每次200点)」      /1000 / 1000点      不符→改
   4  UI「物品喂养」按钮说明                  「…+2~5亲密度」                       +1~2               不符→改
   5  UI「修为喂养」按钮说明                  「消耗 5% 当前修为 (…+2~5亲密度)」     25% / +1~2         不符→改
   6  handler 血量喂养 toast                  `q="消耗了 200 点气血"`               实扣 1000           不符→改
   7  handler 血量喂养 报错                    「需要 200 点气血…」                  实扣 1000           不符→改
   8  handler 修为喂养闸门（驱动提示数字）     `Math.floor(d.exp*.05)`              实扣 25%            不符→改

  ── 一致 · 未改（逐条核过，重点列 10 条）──
   · 妖灵 玩法说明①（进食三档）：凡品·青草露 3000/+30、灵品·玉髓羹 15000/+150、仙品·九转灵丹 60000/+600、
     等级=喂食度÷100（上限99）、封顶9999 ⇒ 与 srv `R018_FEED_TIERS` / `PET_HUNGER_PER_FEED` /
     `PET_HUNGER_MAX` / `PET_LEVEL_DIVISOR` 逐字一致。
   · 妖灵 玩法说明②（免费玩法）：免费进食 +100/每日3次/冷却30分 ⇒ srv `R198_FREE_FEED_MAX=3`、
     `R198_FREE_FEED_CD_MS=30*60*1000`、`R198_FREE_FEED_HUNGER=100`；买额度 20000、3种共用每日≤5 ⇒
     `R018_BUY_COST=20000`、`R018_BUY_DAILY_MAX=5`；互动逗弄/梳毛/夜话 Lv.0/10/30、+5羁绊 ⇒ `R018_PLAY_KINDS`。一致。
   · 妖灵 玩法说明③④⑤：点化 30000/+1~3/上限100 ⇒ `R018_APTITUDE_COST/STEP/MAX`；妖灵秘径 5000/4h/+80/+15/+800 ⇒
     `R018_EXPED_COST/MS/HUNGER/BOND/EXP`；PP 公式与 srv `r018SpiritPP` 同式；收养 20000/归位 30000/放生免费 ⇒
     `R071_ADOPT_COST`/`R071_AWAY_COST`。一致（R-189/R-195 已修过）。
   · 灵兽远征 玩法说明：派遣 20000 ⇒ `_expCost=20000`；槽位 Lv.1~2/3~5/6~8/9+ = 1/2/3/4 ⇒ `YlxwExpSlots` 同式；
     三地点 Lv.1·30分 / Lv.15·2时 / Lv.30·4时 ⇒ `YlxwExpLocations` 同值。一致。
   · 渡劫台 玩法说明：最多10颗、每颗 +3% ⇒ srv `TRIB_PILL_MAX=10`、`TRIB_PILL_BONUS=0.03`（服务端注释
     「落实为我方三维各 +3%」⇒「攻/防/血各+3%」与实现一致）；失败冷却 10 分 ⇒ `TRIBULATION_FAIL_COOLDOWN_MS`。一致。
   · 悬赏 玩法说明：100~1000000 / 90%·10%税 / 挂5单 / 接3单 / 24h ⇒ srv `BOUNTY_*` 全一致。
   · 江湖志 玩法说明：每页50 / 传阅限1次 / 恰10次奖 1000×1.5^境界 ⇒ srv `CHRONICLE_PAGE_SIZE`、
     `CHRONICLE_PRAISE_GOAL=10`、`CHRONICLE_PRAISE_BASE=1000`。一致。
   · 九天通天塔 玩法说明：100层 / 气血≤50 / 每10层Boss×1.4 / 每25层太虚悟道卷 / 第100层九天通天令 / 每日扫荡1次
     ⇒ 客户端 `YlxwTowerFloor`（`isBoss=sf%10===0`、`isMile=sf%25===0`、`bm=1.4`、`sf===100`）、
     `cur.hp<=50`、`YlxwTowerSweep` 单日幂等。一致。
   · 仙途指引 玩法说明：里程碑 2000/3000/8600/9900/3000/6000/61000/12000 ⇒ srv `GUIDE_STEPS` 逐档一致；
     七日礼 2000/3000/4000/6000/8000/12000/15000 + 第7天「七日筑基」 ⇒ `WEEK_REWARDS` 一致。
   · 交易行货款 玩法说明：无数值断言（仅流程），无过期风险。
   · 全库残留扫描：`首次免费` / `首免` / `当日首次` / `首次进食` 计数 **均为 0**（R-192 移除 R-167 首免已彻底，
     无过期文字）。妖灵面板 PP 说明、点化按钮（`+cost+` 动态）与 srv 同源。一致。

  ── 需用户拍板（本环**未改**）──
   · 「灵宠·修为喂养」的真实消耗是 **25% 当前修为**（实扣），但该口径来自 R-017 一次「只改实扣、漏改闸门/文案」
     的经济下调。本环已把**文字**与**闸门**对齐到 25%（不改实扣）。若用户本意其实是 5%，则应回退实扣——那属
     **数值**决策，非文案，留给用户拍板。

==============================================================================
三、为什么「闸门 .05→.25」不算改数值（仅改提示数字）
==============================================================================
  闸门 `const w=Math.max(1,Math.floor(d.exp*.05));if(d.exp>=w)g=!0,q=\`消耗了 ${w} 点修为\`;`
  对任意 exp≥1：`floor(exp*.05) <= exp` 恒真 ⇒ 闸门**从不拦截**（唯一拦截点是 exp=0，两版行为相同）。
  ⇒ 改 `.05→.25` 只让 `w`（以及 toast/报错里的数字）等于真实扣除 `Math.floor(w.exp*.25)`，**行为零变化**。

==============================================================================
四、锚点（对 index-v2936-20261008.js 字符级实测，count 全 == 1）
==============================================================================
  替换锚点（打前 count==1；打后旧形态 count==0）：
    A1 `消耗 200 点气血 (经验根据境界计算，+2~5亲密度)`
    A2 `批量喂血：可喂 ${Math.floor(a.hp/200)} 次`
    A3 `消耗所有可用气血 (可喂 ",Math.floor(a.hp/200)," 次，每次200点)`
    A4 `消耗物品 (经验根据境界和物品品质计算，+2~5亲密度)`
    A5 `消耗 5% 当前修为 (经验根据境界计算，+2~5亲密度)`
    B1 `q="消耗了 200 点气血"`
    B2 `需要 200 点气血，当前只有 ${d.hp} 点`
    C  `Math.floor(d.exp*.05)`（幂等标记 `/*[r202txt]*/` 落此，代码上下文，合法 JS 注释）
  冻结针脚（对**输入**校验，全 ASCII，count==1；钉本环不动的喂养公式/函数，**绝不**钉任何冷却渲染）：
    `if(k==="hp")P=Math.max(0,w.hp-1000);` ｜ `const C=1000,g=k||Math.floor(d.hp/C);`
    ｜ `const Z=k==="hp"?0:Math.floor(1+Math.random()*2),te=w.pets.map(` ｜ `let A=100;` ｜ `let B=100;`
    ｜ `k==="exp"?U=2:k==="item"&&(U=3.5);` ｜ `handleFeedPet:(N,k,_)=>` ｜ `handleBatchFeedHp:(N,k)=>`
    ｜ `Math.floor(1+Math.random()*2)` ｜ `Math.floor((2+Math.random()*4)*k.length)`

==============================================================================
五、契约（照 localtest/yl_r189_ext.py + yl_r199_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 口径探针）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r195-<时刻>`。
  · 幂等：产物已含标记 `/*[r202txt]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 口径探针：从补丁后产物**实抽**「单次闸门值 / 单次实扣值 / 批量成本值 / 修为喂养闸门比例 / 修为实扣比例」
    再比对，断言 `gate==deduct==batch==1000` 且 `exp_gate==exp_deduct`，并断言提示文案里出现的数字与实扣一致。
  · 不跑网络：只读 --src 指向的本地文件。
  · ★ 本文件为「**R-195 文案环**」，**落盘号 r202**（不是 r195）。原因：`localtest/yl_r195_ext.py` 已被
    另一个**已上线**的 R-195（「妖灵归位」，标记 `[r195away]`）占用 ⇒ 本环取**下一个空闲号** r202，
    幂等标记 `/*[r202txt]*/`，需在 `STANDALONE_CLIENT` 末位追加
    `('r202', os.path.join(HERE, 'localtest', 'yl_r202_ext.py')),`。
    ★ 教训：本仓「需求台账 R 号」与「补丁脚本 r 号」是**两套已漂移的编号**，补丁名一律取「下一个空闲号」。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r202txt]*/'

# --------------------------------------------------------------------------- 替换项
# ★ bundle 灵宠喂养区为**裸 UTF-8** ⇒ 用单反斜杠 \uXXXX 写出（运行期即真中文），源码保持 ASCII。

# A1 血量喂养按钮说明：200→1000；hp 喂养已不给亲密度（R-190）⇒ 「+2~5亲密度」→「不加亲密度」
A1_OLD = '\u6d88\u8017 200 \u70b9\u6c14\u8840 (\u7ecf\u9a8c\u6839\u636e\u5883\u754c\u8ba1\u7b97\uff0c+2~5\u4eb2\u5bc6\u5ea6)'
A1_NEW = '\u6d88\u8017 1000 \u70b9\u6c14\u8840 (\u7ecf\u9a8c\u6839\u636e\u5883\u754c\u8ba1\u7b97\uff0c\u4e0d\u52a0\u4eb2\u5bc6\u5ea6)'

# A2 批量喂血 title：可喂次数 hp/200 → hp/1000
A2_OLD = '\u6279\u91cf\u5582\u8840\uff1a\u53ef\u5582 ${Math.floor(a.hp/200)} \u6b21'
A2_NEW = '\u6279\u91cf\u5582\u8840\uff1a\u53ef\u5582 ${Math.floor(a.hp/1000)} \u6b21'

# A3 批量喂血按钮说明：可喂次数 /200→/1000；每次 200点→1000点
A3_OLD = '\u6d88\u8017\u6240\u6709\u53ef\u7528\u6c14\u8840 (\u53ef\u5582 ",Math.floor(a.hp/200)," \u6b21\uff0c\u6bcf\u6b21200\u70b9)'
A3_NEW = '\u6d88\u8017\u6240\u6709\u53ef\u7528\u6c14\u8840 (\u53ef\u5582 ",Math.floor(a.hp/1000)," \u6b21\uff0c\u6bcf\u6b211000\u70b9)'

# A4 物品喂养按钮说明：亲密度 +2~5 → +1~2（R-017 E1.5）
A4_OLD = '\u6d88\u8017\u7269\u54c1 (\u7ecf\u9a8c\u6839\u636e\u5883\u754c\u548c\u7269\u54c1\u54c1\u8d28\u8ba1\u7b97\uff0c+2~5\u4eb2\u5bc6\u5ea6)'
A4_NEW = '\u6d88\u8017\u7269\u54c1 (\u7ecf\u9a8c\u6839\u636e\u5883\u754c\u548c\u7269\u54c1\u54c1\u8d28\u8ba1\u7b97\uff0c+1~2\u4eb2\u5bc6\u5ea6)'

# A5 修为喂养按钮说明：5% → 25%（对齐实扣）；亲密度 +2~5 → +1~2
A5_OLD = '\u6d88\u8017 5% \u5f53\u524d\u4fee\u4e3a (\u7ecf\u9a8c\u6839\u636e\u5883\u754c\u8ba1\u7b97\uff0c+2~5\u4eb2\u5bc6\u5ea6)'
A5_NEW = '\u6d88\u8017 25% \u5f53\u524d\u4fee\u4e3a (\u7ecf\u9a8c\u6839\u636e\u5883\u754c\u8ba1\u7b97\uff0c+1~2\u4eb2\u5bc6\u5ea6)'

# B1 handler 血量喂养 toast：200 → 1000
B1_OLD = 'q="\u6d88\u8017\u4e86 200 \u70b9\u6c14\u8840"'
B1_NEW = 'q="\u6d88\u8017\u4e86 1000 \u70b9\u6c14\u8840"'

# B2 handler 血量喂养 报错：200 → 1000
B2_OLD = '\u9700\u8981 200 \u70b9\u6c14\u8840\uff0c\u5f53\u524d\u53ea\u6709 ${d.hp} \u70b9'
B2_NEW = '\u9700\u8981 1000 \u70b9\u6c14\u8840\uff0c\u5f53\u524d\u53ea\u6709 ${d.hp} \u70b9'

# C 修为喂养闸门 .05 → .25（只让 toast/报错数字对齐实扣；行为零变化，见 docstring §三）+ 幂等标记
C_OLD = 'Math.floor(d.exp*.05)'
C_NEW = 'Math.floor(d.exp*.25)' + IDEMPOTENT_MARK

REPLACEMENTS = [
    ('A1 \u8840\u91cf\u5582\u517b\u8bf4\u660e 200->1000 \u4e14\u4e0d\u52a0\u4eb2\u5bc6\u5ea6', A1_OLD, A1_NEW),
    ('A2 \u6279\u91cf\u5582\u8840 title /200->/1000', A2_OLD, A2_NEW),
    ('A3 \u6279\u91cf\u5582\u8840\u8bf4\u660e /200->/1000 \u4e14 200\u70b9->1000\u70b9', A3_OLD, A3_NEW),
    ('A4 \u7269\u54c1\u5582\u517b\u8bf4\u660e \u4eb2\u5bc6\u5ea6 +2~5->+1~2', A4_OLD, A4_NEW),
    ('A5 \u4fee\u4e3a\u5582\u517b\u8bf4\u660e 5%->25% \u4e14\u4eb2\u5bc6\u5ea6 +2~5->+1~2', A5_OLD, A5_NEW),
    ('B1 handler \u8840\u91cf toast 200->1000', B1_OLD, B1_NEW),
    ('B2 handler \u8840\u91cf \u62a5\u9519 200->1000', B2_OLD, B2_NEW),
    ('C \u4fee\u4e3a\u5582\u517b\u95f8\u95e8 .05->.25 + \u5e42\u7b49\u6807\u8bb0', C_OLD, C_NEW),
]

# 冻结针脚（对**输入**校验，全 ASCII，count==1）：本环不动的喂养公式 / 函数签名 / 亲密度公式
FREEZE = [
    ('if(k==="hp")P=Math.max(0,w.hp-1000);', 1),                                # 单次实扣 1000 未动
    ('const C=1000,g=k||Math.floor(d.hp/C);', 1),                               # 批量实扣 1000 未动
    ('const Z=k==="hp"?0:Math.floor(1+Math.random()*2),te=w.pets.map(', 1),     # hp 亲密度=0 未动
    ('let A=100;', 1),                                                          # 单次基础经验未动
    ('let B=100;', 1),                                                          # 批量基础经验未动
    ('k==="exp"?U=2:k==="item"&&(U=3.5);', 1),                                  # 修为/物品经验倍率未动
    ('handleFeedPet:(N,k,_)=>', 1),                                             # 单次喂养函数未删
    ('handleBatchFeedHp:(N,k)=>', 1),                                           # 批量喂血函数未删
    ('Math.floor(1+Math.random()*2)', 1),                                       # E1.5 亲密度公式未动
    ('Math.floor((2+Math.random()*4)*k.length)', 1),                            # 物品批量亲密度公式未动
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    needle 可为 tuple（多形态合计计数）。"""
    return [
        # ---- 幂等标记 ----
        ('R195txt-mark', IDEMPOTENT_MARK, 1, '==', '[r202txt] exactly once'),
        # ---- A1 ----
        ('R195txt-A1 hp desc 1000', '\u6d88\u8017 1000 \u70b9\u6c14\u8840', 1, '==', ''),
        ('R195txt-A1 old 200 cleared', '\u6d88\u8017 200 \u70b9\u6c14\u8840', 0, '==', ''),
        ('R195txt-A1 hp no intimacy', '\u4e0d\u52a0\u4eb2\u5bc6\u5ea6', 1, '==', ''),
        # ---- A2 ----
        ('R195txt-A2 batch title /1000', 'a.hp/1000', 2, '==', 'title + desc'),
        ('R195txt-A2 old /200 cleared', 'a.hp/200', 0, '==', ''),
        # ---- A3 ----
        ('R195txt-A3 each 1000 pt', '\u6bcf\u6b211000\u70b9', 1, '==', ''),
        ('R195txt-A3 old each 200 pt cleared', '\u6bcf\u6b21200\u70b9', 0, '==', ''),
        # ---- A4/A5 intimacy ----
        ('R195txt-A4/A5 intimacy +1~2', '+1~2\u4eb2\u5bc6\u5ea6', 2, '==', 'item + exp'),
        ('R195txt-old intimacy +2~5 cleared', '+2~5\u4eb2\u5bc6\u5ea6', 0, '==', ''),
        # ---- A5 ----
        ('R195txt-A5 exp desc 25%', '\u6d88\u8017 25% \u5f53\u524d\u4fee\u4e3a', 1, '==', ''),
        ('R195txt-A5 old 5% cleared', '\u6d88\u8017 5% \u5f53\u524d\u4fee\u4e3a', 0, '==', ''),
        # ---- B1/B2 ----
        ('R195txt-B1 hp toast 1000', 'q="\u6d88\u8017\u4e86 1000 \u70b9\u6c14\u8840"', 1, '==', ''),
        ('R195txt-B1 old toast cleared', 'q="\u6d88\u8017\u4e86 200 \u70b9\u6c14\u8840"', 0, '==', ''),
        ('R195txt-B2 hp err 1000', '\u9700\u8981 1000 \u70b9\u6c14\u8840', 1, '==', ''),
        ('R195txt-B2 old err cleared', '\u9700\u8981 200 \u70b9\u6c14\u8840', 0, '==', ''),
        # ---- C ----
        ('R195txt-C exp gate .25', 'Math.floor(d.exp*.25)', 1, '==', ''),
        ('R195txt-C old gate .05 cleared', 'Math.floor(d.exp*.05)', 0, '==', ''),
        ('R195txt-C deduct still .25', 'Math.floor(w.exp*.25)', 1, '==', 'untouched'),
        # ---- 冻结（对应产物）----
        ('R195txt-hp deduct 1000 kept', 'if(k==="hp")P=Math.max(0,w.hp-1000);', 1, '==', ''),
        ('R195txt-batch C=1000 kept', 'const C=1000,g=k||Math.floor(d.hp/C);', 1, '==', ''),
        ('R195txt-hp intimacy 0 kept', 'const Z=k==="hp"?0:Math.floor(1+Math.random()*2),te=w.pets.map(', 1, '==', ''),
        ('R195txt-feed base A=100 kept', 'let A=100;', 1, '==', ''),
        ('R195txt-feed base B=100 kept', 'let B=100;', 1, '==', ''),
        ('R195txt-exp/item mult kept', 'k==="exp"?U=2:k==="item"&&(U=3.5);', 1, '==', ''),
        ('R195txt-handleFeedPet kept', 'handleFeedPet:(N,k,_)=>', 1, '==', ''),
        ('R195txt-handleBatchFeedHp kept', 'handleBatchFeedHp:(N,k)=>', 1, '==', ''),
        ('R195txt-item batch intimacy kept', 'Math.floor((2+Math.random()*4)*k.length)', 1, '==', ''),
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
    """返回 err（None 表示可打）。对**原件** s 校验锚点与冻结针脚。"""
    if _is_patched(s):
        return None  # 幂等，交由 main 判 rc=3
    for name, old, new in REPLACEMENTS:
        c = s.count(old)
        if c != 1:
            return 'anchor %s count=%d (expect 1)' % (name, c)
    for needle, cnt in FREEZE:
        c = s.count(needle)
        if c != cnt:
            return 'freeze pin %r count=%d (expect %d)' % (needle, c, cnt)
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


def _num_between(text, head, stop):
    """抽 [head .. stop) 之间的整数。"""
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


def _rate(text, pat):
    """从 `Math.floor(<x>.exp*.<digits>)` 抽比例（如 '25' → 0.25）。"""
    m = re.search(pat, text)
    if not m:
        return None
    return int(m.group(1)) / 100.0


def _feed_probe(out):
    """从补丁后产物**实抽**喂养口径再比对：闸门==实扣==批量（=1000）；修为喂养闸门比例==实扣比例（=0.25）；
    并断言玩家可见提示里的数字与实扣一致。返回 (ok, msg)；ok=None 表示无 node 依赖（本探针纯文本，始终可跑）。"""
    gate = _num_between(out, 'if(k==="hp")if(d.hp>=', ')g=!0,')
    ded = _num_between(out, 'if(k==="hp")P=Math.max(0,w.hp-', ');')
    mb = re.search(r'const C=(\d+),g=k\|\|Math\.floor\(d\.hp/C\);', out)
    bct = int(mb.group(1)) if mb else None
    exp_gate = _rate(out, r'Math\.floor\(d\.exp\*\.(\d+)\)')
    exp_ded = _rate(out, r'Math\.floor\(w\.exp\*\.(\d+)\)')
    if None in (gate, ded, bct, exp_gate, exp_ded):
        return False, 'extract failed: gate=%r ded=%r batch=%r eg=%r ed=%r' % (gate, ded, bct, exp_gate, exp_ded)
    if not (gate == ded == bct):
        return False, 'hp cost mismatch: gate=%s ded=%s batch=%s' % (gate, ded, bct)
    if abs(exp_gate - exp_ded) > 1e-9:
        return False, 'exp rate mismatch: gate=%s ded=%s' % (exp_gate, exp_ded)
    # 提示文案里的数字必须等于实扣
    if ('q="\u6d88\u8017\u4e86 %d \u70b9\u6c14\u8840"' % gate) not in out:
        return False, 'hp toast number != cost %d' % gate
    if ('\u9700\u8981 %d \u70b9\u6c14\u8840' % gate) not in out:
        return False, 'hp error number != cost %d' % gate
    msg = ('hp-cost>> gate=deduct=batch=%d ; exp-rate>> gate=deduct=%.2f ; '
           'toast/err numbers == %d' % (gate, exp_gate, gate))
    return True, msg


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 口径探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r202txt] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r202txt] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r202txt] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r202txt] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r202txt] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r202txt] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _feed_probe(out)
    if ok is False:
        print('[r202txt] SELFTEST FAIL feed-probe: ' + pmsg)
        return 1
    print('[r202txt] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print('[r202txt] probe>> ' + pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r202txt] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r202txt] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r202txt] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r202txt] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r202txt] round-trip mismatch: bytes outside the edit points changed')
        return 1

    if args.check:
        print('[r202txt] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-40s %s' % (label, 'OK'))
        ok, pmsg = _feed_probe(out)
        print('    probe %-39s %s' % ('feed-cost/rate consistency', 'OK' if ok else 'FAIL'))
        print('    >> ' + pmsg)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r195-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r202txt] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-40s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
