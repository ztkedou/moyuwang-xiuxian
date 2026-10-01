# -*- coding: utf-8 -*-
r"""
yl_051_ext.py — R-051 日常任务奖励增加：修为与灵石整体 ×1.5（产生点一处放大）

需求原文（用户，台账 R-051，附图列空）
--------------------------------------------------------------------------
  「日常任务中修为和灵石的获取数量也增加一点，这也是游戏获得灵石和修为的重要途径，
    毕竟每天只能完成一次。」

侦察（构建产物 index-v28113-20260930.js 逐字实证，探针见 %TEMP%/yl051_probe*.py）
--------------------------------------------------------------------------
  · 奖励**产生点**是生成器 `hg=(t,r,a,l,c)=>{const d=q3[t],u=Ba[a],f=l&&c?A3(l,c):1,
    v=r*d.rewardMultiplier*u*f,vs=v*5;switch(t){...}`（@456138，全仓唯一）：
    8 个类型分支的修为全是 `Math.floor(v*系数)`、灵石全是 `Math.floor(vs*系数)`，
    即 **修为与灵石同源于 v**（vs=v*5）。
  · `hg` 仅 2 个调用点（`hg(x.type` / `hg(M.type`，各唯一），都在 `uk()` 内的
    日常任务生成器（主循环 + 补位分支）；生成按日历日键 `Gc`（yyyy-mm-dd）触发。
  · 领奖**入账点** `claimQuestReward:v=>{...const b=j.reward.exp||0,
    S=Math.floor((j.reward.spiritStones||0)/(1+Math.max(0,fe.indexOf(m.realm))*.5)
    *YLRF(m.realm)*2.13),x=j.reward.lotteryTickets||0...`（@1801158，全仓唯一）：
    这是灵石缩放方案 P5 的入账公式，显示 helper `YlxwDailyStones`（fun086 F2b 注入）
    与它「逐位一致」。**本模块不动入账点** —— 只改产生点，卡面显示
    （`children:[t.reward.exp," 修为"]` / `YlxwDailyStones(t.reward.spiritStones,YlqR)`）、
    领奖实付、排序比较器三者自动保持「显示==实付」（v288 不变式）。
  · 服务端 `srv/index_v28.ts` 无 dailyQuest/claimQuest 逻辑（count=0，客户端权威）；
    经济钳制 `capStone` 兜底 = E2_STONE_BURST_PER_HOUR(1,250,000/时) + BASE(6,000,000)，
    日常任务增量（最大档 ~8.8k×0.5 ≈ +4.4k/日）远在富余内 ⇒ **无需服务端补丁**。

方案（拍板文件 2026-10-01_0255_R-051_日常任务奖励增幅与落点.md，AI 代决）
--------------------------------------------------------------------------
  在 v 的定义处乘 1.5：`v=r*d.rewardMultiplier*u*f*1.5,vs=v*5` ——
  一处替换同时放大修为（v*系数）与灵石（vs=5v），抽奖券掉率不动；
  生效从下一次日常任务生成起（最晚次日，当日已生成任务保持旧值，显示实付仍一致）。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 锚点全 ASCII、全仓唯一（count==1 已实测）；每个 replace 带 expect=。
  · 注入块为空（INJECT_JS=''，本模块纯就地替换，无 zh() 面）。
  · 冻结面：fun086 F2（vs=v*5 门禁形态）、R-027（q3/$3/构造）、reward089 基线、
    P5 入账公式、claimQuestReward 全函数、YlxwDailyStones helper 与卡面显示 ——
    门禁逐条证明未碰。
  · 只新建本文件；不改 build_v26n.py / localtest/ / srv/index_v28.ts / build/assets/。
"""

# --------------------------------------------------------------------------- 注入块
# 本模块纯就地替换，不注入新代码。
INJECT_JS = ''

# --------------------------------------------------------------------------- 锚点
# 旧形态：fun086 F2 改造后的 hg() 变量声明行（全仓唯一，count=1 实测 @index-v28113）
ANCHOR_OLD = 'v=r*d.rewardMultiplier*u*f,vs=v*5'
# 新形态：v 乘 1.5 ⇒ 修为（v*系数）与灵石（vs=v*5）同源放大；旧串不是新串的子串
# （`*1.5` 恰好断在 `u*f,` 处），「旧形态清零」门禁无自碰撞（§7.5）。
ANCHOR_NEW = 'v=r*d.rewardMultiplier*u*f*1.5,vs=v*5'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    p.replace('r051-daily-reward', ANCHOR_OLD, ANCHOR_NEW, expect=1,
              note='日常任务奖励产生点 hg() 整体 ×1.5（修为+灵石同源）')

    gates = [
        # ================= 本模块改动 =================
        ('R51·生成器已×1.5',            ANCHOR_NEW, 1, '==', '修为与灵石同源于 v，一处放大'),
        ('R51·旧形态已清零',            ANCHOR_OLD, 0, '==', '替换目标旧形态'),
        ('R51·exp/灵石仍同源(vs=v*5)',  'vs=v*5;switch(t){', 1, '==', '未把灵石拆成独立常数'),
        # ================= 冻结：入账点/显示面（灵石缩放方案 P5 + v288 对齐 + fun086/R-027/reward089） =================
        ('冻结·P5 领奖入账公式未动',     'S=Math.floor((j.reward.spiritStones||0)/(1+Math.max(0,fe.indexOf(m.realm))*.5)*YLRF(m.realm)*2.13)', 1, '==', '缩放方案 P5 入账点，动了破坏显示==实付'),
        ('冻结·领奖函数未动',           'claimQuestReward:v=>{', 1, '==', ''),
        ('冻结·领奖修为 b 未动',        'const b=j.reward.exp||0', 1, '==', ''),
        ('冻结·余额修为入账未动',       'exp:m.exp+b', 1, '==', ''),
        ('冻结·余额灵石入账未动',       'spiritStones:m.spiritStones+S', 1, '==', ''),
        ('冻结·显示 helper 未动',       'function YlxwDailyStones(base, realm) {', 1, '==', 'fun086 F2b 注入的显示对齐函数'),
        ('冻结·卡面修为显示未动',       'children:[t.reward.exp," \u4fee\u4e3a"]', 1, '==', 'reward089 基线'),
        ('冻结·卡面灵石显示未动',       'YlxwDailyStones(t.reward.spiritStones,YlqR)', 1, '==', 'reward089 基线'),
        ('冻结·fun086 vs 门禁形态未动', 'vs=v*5;switch(t){', 1, '==', 'fun086 F2 自己的门禁串'),
        # ================= 冻结：R-027 任务本体 =================
        ('冻结·R27 q3 类型表未动',      'q3={meditate:{type:"meditate",name:"\u6253\u5750\u4fee\u70bc"', 1, '==', '获取方式模块的面'),
        ('冻结·任务模板 $3 未动',       '$3=[{type:"meditate",name:"', 1, '==', ''),
        # ================= 冻结：生成器调用面与掉率 =================
        ('冻结·生成分支1仍走 hg',       'hg(x.type', 1, '==', 'uk() 主循环'),
        ('冻结·生成分支2仍走 hg',       'hg(M.type', 1, '==', 'uk() 补位分支'),
        ('冻结·hg 定义头未动',          'hg=(t,r,a,l,c)=>{const d=q3[t]', 1, '==', ''),
        ('冻结·抽奖券·仙品档掉率未动',   'lotteryTickets:a==="\u4ed9\u54c1"?1:0', 2, '==', 'adventure/sect 两处'),
        ('冻结·抽奖券·传说/仙品档未动',  'lotteryTickets:a==="\u4f20\u8bf4"||a==="\u4ed9\u54c1"?1:0', 2, '==', 'breakthrough/realm 两处'),
        ('冻结·逐类型系数未动(v*20)',   'Math.floor(v*20)', 3, '==', 'meditate/pet/default，放大只走 v 本身'),
    ]
    return gates
