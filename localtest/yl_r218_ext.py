# -*- coding: utf-8 -*-
r"""
yl_r218_ext.py — R-218 开局难度收益倍率（纯客户端，一处定义 · 全局生效 · 易回退）

需求原文（用户原话）
--------------------------------------------------------------------------
    「简单模式不变，普通模式其他惩罚默认，修炼速度+50%，灵石获取+50%。
      困难模式修炼速度+100%，灵石获取+100%。」

口径（与派单一致）
--------------------------------------------------------------------------
  风险补偿：难度越高惩罚越重 ⇒ 收益越高。
    · 「修炼速度」= **一切修为获取**（exp 入账）；
    · 「灵石获取」= **一切灵石获取**（spiritStones 入账）。
  倍率表（easy 不变）：

        difficulty     expMul   stoneMul
        ------------   ------   --------
        easy            1.0      1.0      （不变）
        normal          1.5      1.5      （+50%）
        hard            2.0      2.0      （+100%）

  ★ 注意：本环**不动**任何惩罚项（enemyPower / battleChance / reward /
    skippedBattleReward 一字未改，见冻结门禁 FRZ_DIFF_*）——只做「收益放大」。

输入产物
--------------------------------------------------------------------------
  build/assets/index-v2945-20261009.js
  （线上 0.9.45，md5 e5a451fe35fb7d0ad4422bdd8ddcac9b，2,321,665 B）

实现总览（一处定义 · 全局生效 · 易回退）
--------------------------------------------------------------------------
  1) 难度表 Qr.difficulty（@294234）每档**新增** expMul / stoneMul 两字段；
  2) 紧随 md() 之后**新增两个模块级取值器**（幂等标记 /*YLXW_R218_V2945*/）：
       · YlxwDiffMul(t, r) —— 照 md() 写法；t 缺省时依次读
            (a) Be.getState().settings.difficulty（游戏内权威来源）
            (b) localStorage["xiuxian-game-settings"].difficulty（兜底）
            (c) 都拿不到 → "normal"
          返回 Qr.difficulty[d][r]；d 无法判定时回退 "normal"（= 游戏默认，同 md() 口径）；
          难度表本身不可达 / 字段非法 → 1（恒等，绝不放大）。
       · YlxwDiffGain(x, f) —— 入账收口处的统一乘子：
           x<=0（消耗 / 扣减 / 无收益）→ **原样返回**（绝不放大消耗）；
           x>0 → Math.floor(x * YlxwDiffMul(void 0, f))。
  3) 在每个**修为 / 灵石入账点**用 YlxwDiffGain(...) 包住**增益量**。

  ★ 为什么用「包住增益量」而不是「改玩家对象」：只对**明确的获取量**乘倍率，
    消耗 / 扣减表达式（-w、-cost、-price、-贡献…）**一字不动**，语义边界清晰、
    可回退（删掉全部 EDITS 即还原）。

==============================================================================
入账点清单（本环实际改动 18 处；offset 为基线 build/assets/index-v2945-*.js 字节偏移）
==============================================================================
  —— A. 核心修炼 / 历练循环 ——
  E2  @745984  打坐·修为：把打坐 exp 基数 v 就地乘（覆盖「顿悟 30~50x」与「常规」两分支，
               两者皆由 v 派生；toast 与入账同源 ⇒ 展示=入账）。
  E3  @746781  打坐·灵石：__ylsq = YlxwMedStone2(...) 外包 YlxwDiffGain(...,"stoneMul")
               （toast「打坐时获得了 N 灵石」与 w 入账同源）。
  E4  @1917498 历练 / 秘境 / 奇遇 / 宗门任务奖励·修为收口 Pc()：
               r.expChange 先乘倍率、再套原有 _ylExpCap 上限（不越过既有封顶）。
  E5  @1917603 同上·灵石收口 Pc()：S.spiritStones 的增量包倍率。
  E6  @728264  回合制战斗结算 NS.handleBattleResult：S(exp) / x(灵石) 增量包倍率
               （u.expChange / u.spiritChange 可为负——败北扣 exp——负值原样返回）。

  —— B. 其它明确「获取」处 ——
  E7  @747587  成就奖励（exp / spiritStones）
  E8  @639996  洞府图鉴·自动收获奖励（exp / spiritStones）
  E9  @1976606 图鉴 / 称号奖励（N.exp+=k, N.spiritStones+=_）
  E10 @1940779 宗门·晋升奖励（exp / spiritStones）
  E11 @1942039 宗门·接任宗主奖励（exp / spiritStones）
  E12 @1966273 日常任务·领奖（exp / spiritStones）
  E13 @2029714 通天塔·通关奖励（g.expGain / g.spiritStoneGain，就地改 g 使入账与
               展示 rewards 同源）
  E14 @1952523 灵宠·单只放生补偿（灵石）
  E15 @1953012 灵宠·批量放生补偿（灵石）
  E16 @1939783 宗门任务·完成结算（**兼做消耗**：spiritStones 表达式为 `k.spiritStones-w+D`，
               w=任务花费，D=灵石奖励；本环**只放大 +D / +I**，`-w` 一字不动）。

  —— C. 定义处 ——
  E0a @294298  easy   档追加 expMul:1,   stoneMul:1
  E0b @294368  normal 档追加 expMul:1.5, stoneMul:1.5
  E0c @294444  hard   档追加 expMul:2,   stoneMul:2
  E1  @294933  md() 之后注入 YlxwDiffMul / YlxwDiffGain（幂等标记位）

==============================================================================
「消耗点一律未动」的证据
==============================================================================
  本模块的 EDITS **只**包含上述 18 处；全部替换串的 new 侧都是
  「原增益量外包 YlxwDiffGain(...)」，**没有**任何 new 串出现在下表中。
  门禁对下列「消耗 / 扣减 / 惩罚」表达式做 fail-closed 计数冻结（补丁前后 count 不变）：

    · @738669  `spiritStones:v.spiritStones-f`                    （商店刷新花费）
    · @826796  `spiritStones:j.spiritStones-m.cost`               （炼丹花费）
    · @751366  `exp:Math.floor(q.exp*.7)`                         （突破失败·修为惩罚）
    · @1911364/@1911704 `spiritStones:N.spiritStones-_`           （商店购买，2 处）
    · @1913085 `spiritStones:b.spiritStones-m.cost`               （秘境进入费）
    · @1938289 `spiritStones:h.spiritStones-N`                    （宗门相关扣减）
    · @1942622 `spiritStones:E.spiritStones-Hn.challengeCost.spiritStones`（挑战宗主花费）
    · @1951926 `exp:Math.max(0,ee.exp-q)`                         （灵宠献祭·修为扣减）
    · @1977980 `spiritStones:h.spiritStones-__cost`               （洞府扩展花费）
    · @1979442 `spiritStones:h.spiritStones-A`                    （灵田花费）
    · @2039820 `spiritStones:N.spiritStones-R`                    （赠送灵石）
    · @2121089 `spiritStones:C.spiritStones-k.price`              （交易行购买）
    · @2121812 `spiritStones:k.spiritStones-E`                    （交易行刷新）
    · GM/调试资源包 @2066226/@2066468/@2066985 亦冻结未动（非正常玩法路径）

  另：难度惩罚系数冻结（证明只加收益、未动惩罚）：
    `enemyPower:.9,battleChance:.85,reward:.95,skippedBattleReward:.75`（easy）
    `enemyPower:1,battleChance:1,reward:1,skippedBattleReward:.65`      （normal）
    `enemyPower:1.15,battleChance:1.15,reward:1.1,skippedBattleReward:.5`（hard）

  ★ 未覆盖（有意）：服务端结算的**离线收益**（loadGame 直接 `t({player:...})`，
    绕过客户端 setPlayer 与全部入账点）——属服务端 / 存档层，本环（纯客户端）不涉，
    亦不在派单「客户端入账点」范围内。

==============================================================================
契约（standalone，同 localtest/yl_r216_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`（缺省自动探测 PATH 上的 node）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r218-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（含门禁未全绿、往返不一致、node --check 失败）。
  · EDITS 四元组 (label, old, new, n)；n=该处旧串期望命中数=替换次数。
  · gates() 五元组 (name, needle, count, op, note)；_precheck() + 往返自证 + node 自检。
  · 纯客户端；不改 build_v26n.py / chain_build.py / dryrun_087.py / sim_remote_check.py /
    任何 build/assets/* / 其它 yl_*_ext.py；不动 r219/r220 已改的死亡逻辑与难度文案。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*YLXW_R218_V2945*/'

# --------------------------------------------------------------------------- 定义处
# E0：难度表每档追加收益倍率字段（仅追加，原有惩罚字段一字未改）
E0a_old = 'skippedBattleReward:.75}'
E0a_new = 'skippedBattleReward:.75,expMul:1,stoneMul:1}'
E0b_old = 'skippedBattleReward:.65}'
E0b_new = 'skippedBattleReward:.65,expMul:1.5,stoneMul:1.5}'
E0c_old = 'skippedBattleReward:.5}'
E0c_new = 'skippedBattleReward:.5,expMul:2,stoneMul:2}'

# E1：md() 之后注入取值器（幂等标记 + 两个模块级函数）
E1_old = 'md=(t="normal")=>Qr.difficulty[t]||Qr.difficulty.normal,Lm='
E1_new = (
    'md=(t="normal")=>Qr.difficulty[t]||Qr.difficulty.normal,'
    + MARK +
    'YlxwDiffMul=(t,r)=>{try{var d=t;'
    'if(!d||!Qr.difficulty[d]){try{d=(Be.getState().settings||{}).difficulty}catch(e){}}'
    'if(!d){try{var s=localStorage.getItem("xiuxian-game-settings");'
    'if(s){var o=JSON.parse(s);if(o&&o.difficulty)d=o.difficulty}}catch(e){}}'
    'var q=Qr.difficulty[d]||Qr.difficulty.normal,v=Number(q&&q[r]);'
    'return isFinite(v)&&v>0?v:1}catch(e){return 1}},'
    'YlxwDiffGain=(x,f)=>{try{if(!(x>0))return x;'
    'var m=YlxwDiffMul(void 0,f);'
    'return isFinite(m)&&m>0?Math.floor(x*m):x}catch(e){return x}},Lm=')

# --------------------------------------------------------------------------- A. 核心循环
# E2：打坐·修为（基数 v 派生两分支的 S；就地乘）
E2_old = 'm.total>0&&(v=Math.floor(v*(1+m.total)));const j=gd(a),'
E2_new = ('m.total>0&&(v=Math.floor(v*(1+m.total)));'
          'v=YlxwDiffGain(v,"expMul");const j=gd(a),')

# E3：打坐·灵石
E3_old = '__ylsq=YlxwMedStone2(q,$.realmLevel,C)'
E3_new = '__ylsq=YlxwDiffGain(YlxwMedStone2(q,$.realmLevel,C),"stoneMul")'

# E4：历练/秘境/奇遇/宗门任务·修为收口 Pc()（先乘倍率，再套既有封顶）
E4_old = 'r.expChange>0&&(r.expChange=Math.min(r.expChange,_ylExpCap(t)))'
E4_new = ('r.expChange>0&&(r.expChange=Math.min(YlxwDiffGain(r.expChange,"expMul"),'
          '_ylExpCap(t)))')

# E5：同上·灵石收口 Pc()
E5_old = 'S.spiritStones=Math.max(0,t.spiritStones+(r.spiritStonesChange||0))'
E5_new = ('S.spiritStones=Math.max(0,t.spiritStones+'
          'YlxwDiffGain(r.spiritStonesChange||0,"stoneMul"))')

# E6：回合制战斗结算 NS.handleBattleResult（负增量原样返回）
E6_old = 'S=Math.max(0,v.exp+u.expChange),x=Math.max(0,v.spiritStones+u.spiritChange)'
E6_new = ('S=Math.max(0,v.exp+YlxwDiffGain(u.expChange,"expMul")),'
          'x=Math.max(0,v.spiritStones+YlxwDiffGain(u.spiritChange,"stoneMul"))')

# --------------------------------------------------------------------------- B. 其它获取处
# E7：成就奖励
E7_old = ('exp:R.exp+($.reward.exp||0),spiritStones:R.spiritStones+'
          'Math.floor(($.reward.spiritStones||0)*5*YLRF(R)/3)')
E7_new = ('exp:R.exp+YlxwDiffGain($.reward.exp||0,"expMul"),'
          'spiritStones:R.spiritStones+'
          'YlxwDiffGain(Math.floor(($.reward.spiritStones||0)*5*YLRF(R)/3),"stoneMul")')

# E8：图鉴·自动收获奖励
E8_old = 'exp:T.exp+b,spiritStones:T.spiritStones+S'
E8_new = ('exp:T.exp+YlxwDiffGain(b,"expMul"),'
          'spiritStones:T.spiritStones+YlxwDiffGain(S,"stoneMul")')

# E9：图鉴/称号奖励
E9_old = 'N.exp+=k,N.spiritStones+=_'
E9_new = 'N.exp+=YlxwDiffGain(k,"expMul"),N.spiritStones+=YlxwDiffGain(_,"stoneMul")'

# E10：宗门·晋升奖励
E10_old = 'exp:h.exp+g.exp,spiritStones:h.spiritStones+g.spiritStones'
E10_new = ('exp:h.exp+YlxwDiffGain(g.exp,"expMul"),'
           'spiritStones:h.spiritStones+YlxwDiffGain(g.spiritStones,"stoneMul")')

# E11：宗门·接任宗主奖励
E11_old = ('exp:h.exp+R.exp,spiritStones:h.spiritStones+'
           'Math.floor(R.spiritStones*5*YLRF(h)/3)')
E11_new = ('exp:h.exp+YlxwDiffGain(R.exp,"expMul"),'
           'spiritStones:h.spiritStones+'
           'YlxwDiffGain(Math.floor(R.spiritStones*5*YLRF(h)/3),"stoneMul")')

# E12：日常任务·领奖
E12_old = 'exp:m.exp+b,inventory:M,spiritStones:m.spiritStones+S'
E12_new = ('exp:m.exp+YlxwDiffGain(b,"expMul"),inventory:M,'
           'spiritStones:m.spiritStones+YlxwDiffGain(S,"stoneMul")')

# E13：通天塔·通关奖励（就地改 g，入账与展示同源）
E13_old = 'const g=G3(C,d.currentFloor+1,a);j(g),S("result"),'
E13_new = ('const g=G3(C,d.currentFloor+1,a);'
           'g.expGain=YlxwDiffGain(g.expGain,"expMul"),'
           'g.spiritStoneGain=YlxwDiffGain(g.spiritStoneGain,"stoneMul");'
           'j(g),S("result"),')

# E14：灵宠·单只放生补偿
E14_old = 'spiritStones:C.spiritStones+D'
E14_new = 'spiritStones:C.spiritStones+YlxwDiffGain(D,"stoneMul")'

# E15：灵宠·批量放生补偿
E15_old = 'spiritStones:k.spiritStones+_'
E15_new = 'spiritStones:k.spiritStones+YlxwDiffGain(_,"stoneMul")'

# E16：宗门任务·完成结算（兼做消耗：仅放大 +D / +I，`-w` 不动）
E16_old = 'spiritStones:k.spiritStones-w+D,exp:k.exp+I'
E16_new = ('spiritStones:k.spiritStones-w+YlxwDiffGain(D,"stoneMul"),'
           'exp:k.exp+YlxwDiffGain(I,"expMul")')

EDITS = [
    # 定义处
    ('E0a 难度表 easy 追加 expMul:1,stoneMul:1',            E0a_old, E0a_new, 1),
    ('E0b 难度表 normal 追加 expMul:1.5,stoneMul:1.5',      E0b_old, E0b_new, 1),
    ('E0c 难度表 hard 追加 expMul:2,stoneMul:2',            E0c_old, E0c_new, 1),
    ('E1 md() 后注入 YlxwDiffMul / YlxwDiffGain + 幂等标记', E1_old,  E1_new,  1),
    # A. 核心循环
    ('E2 打坐·修为 基数 v × expMul',                        E2_old,  E2_new,  1),
    ('E3 打坐·灵石 __ylsq × stoneMul',                      E3_old,  E3_new,  1),
    ('E4 历练/秘境·修为 Pc r.expChange × expMul',           E4_old,  E4_new,  1),
    ('E5 历练/秘境·灵石 Pc r.spiritStonesChange × stoneMul', E5_old,  E5_new,  1),
    ('E6 回合制战斗 exp/灵石 × 倍率',                        E6_old,  E6_new,  1),
    # B. 其它获取处
    ('E7 成就奖励 exp/灵石 × 倍率',                          E7_old,  E7_new,  1),
    ('E8 图鉴自动收获 exp/灵石 × 倍率',                      E8_old,  E8_new,  1),
    ('E9 图鉴/称号奖励 exp/灵石 × 倍率',                     E9_old,  E9_new,  1),
    ('E10 宗门晋升奖励 exp/灵石 × 倍率',                     E10_old, E10_new, 1),
    ('E11 宗门接任奖励 exp/灵石 × 倍率',                     E11_old, E11_new, 1),
    ('E12 日常任务领奖 exp/灵石 × 倍率',                     E12_old, E12_new, 1),
    ('E13 通天塔通关奖励 exp/灵石 × 倍率',                   E13_old, E13_new, 1),
    ('E14 灵宠单只放生补偿灵石 × 倍率',                      E14_old, E14_new, 1),
    ('E15 灵宠批量放生补偿灵石 × 倍率',                      E15_old, E15_new, 1),
    ('E16 宗门任务完成（仅放大 +D/+I，保留 -w）',            E16_old, E16_new, 1),
]

# --------------------------------------------------------------------------- 冻结门禁（消耗/惩罚，一字未动）
# 五元组语义：(name, needle, count, op, note)；op 恒为 '=='。
FREEZE = [
    # —— 消耗 / 扣减 / 惩罚（证明「只放大获取，绝不放大消耗」）——
    ('冻结·商店刷新花费',   'spiritStones:v.spiritStones-f',                        1),
    ('冻结·炼丹花费',       'spiritStones:j.spiritStones-m.cost',                   1),
    ('冻结·突破失败惩罚',   'exp:Math.floor(q.exp*.7)',                             1),
    ('冻结·商店购买扣款',   'spiritStones:N.spiritStones-_',                        2),
    ('冻结·秘境进入费',     'spiritStones:b.spiritStones-m.cost',                   1),
    ('冻结·宗门扣减',       'spiritStones:h.spiritStones-N',                        1),
    ('冻结·挑战宗主花费',   'spiritStones:E.spiritStones-Hn.challengeCost.spiritStones', 1),
    ('冻结·灵宠献祭扣修为', 'exp:Math.max(0,ee.exp-q)',                             1),
    ('冻结·洞府扩展花费',   'spiritStones:h.spiritStones-__cost',                   1),
    ('冻结·灵田花费',       'spiritStones:h.spiritStones-A',                        1),
    ('冻结·赠送灵石',       'spiritStones:N.spiritStones-R',                        1),
    ('冻结·交易行购买',     'spiritStones:C.spiritStones-k.price',                  1),
    ('冻结·交易行刷新',     'spiritStones:k.spiritStones-E',                        1),
    ('冻结·GM资源包1',      'spiritStones:a.spiritStones+1e5',                      1),
    ('冻结·GM资源包2',      'spiritStones:a.spiritStones+1e6',                      1),
    ('冻结·GM经验设置',     'exp:Math.max(a.maxExp-1,0)',                           1),
    # —— 难度惩罚系数（证明只加收益、未动惩罚）——
    ('冻结·easy 惩罚系数',   'enemyPower:.9,battleChance:.85,reward:.95,skippedBattleReward:.75',  1),
    ('冻结·normal 惩罚系数', 'enemyPower:1,battleChance:1,reward:1,skippedBattleReward:.65',       1),
    ('冻结·hard 惩罚系数',   'enemyPower:1.15,battleChance:1.15,reward:1.1,skippedBattleReward:.5', 1),
]

# --------------------------------------------------------------------------- 门禁漂移修复（R-246）
# ★ E1「新串在位」针的下游被**合法改写**（补丁按序套用 ⇒ 本环 apply 时刻下游尚未生效，该针
#   当时必然通过；唯有在最终形态重跑才暴露）：
#   · r222（P0）在 `md(...)` 与 `/*YLXW_R218_V2945*/` 之间插入难度中文名取值器 `YlxwDiffCn`；
#   · r232（B）在 `YlxwDiffMul` 的 `var d=t;` 之后插入服务端权威分支
#     `if(!d||!Qr.difficulty[d]){try{d=YlxwServerDiff()}catch(e){}}`；
#   · r232（A）在 `YlxwDiffGain` 的 `}}` 与 `,Lm=` 之间插入
#     `/*YLXW_R232_V2951*/YlxwServerDiff=…,YlxwSrvDiffCapture=…,`。
# ⇒ 该针改 tuple 合计「新旧两形态」（旧形态 = 本环套用时刻的 E1_new；新形态 = 最终产物逐字抽出），
#   计数相加，两种场景均 == 1（**绝不放宽断言**：期望仍为 1、op 仍为 '=='）。
E1_NEW_ALT = 'md=(t="normal")=>Qr.difficulty[t]||Qr.difficulty.normal,/*YLXW_R222_V2947*/YlxwDiffCn=()=>{try{var d;try{d=YlxwServerDiff()}catch(e){}try{d=(Be.getState().settings||{}).difficulty}catch(e){}if(!d){try{var s=localStorage.getItem("xiuxian-game-settings");if(s){var o=JSON.parse(s);if(o&&o.difficulty)d=o.difficulty}}catch(e){}}return d==="easy"?"\\u7b80\\u5355":d==="hard"?"\\u56f0\\u96be":"\\u666e\\u901a"}catch(e){return"\\u666e\\u901a"}},/*YLXW_R218_V2945*/YlxwDiffMul=(t,r)=>{try{var d=t;if(!d||!Qr.difficulty[d]){try{d=YlxwServerDiff()}catch(e){}}if(!d||!Qr.difficulty[d]){try{d=(Be.getState().settings||{}).difficulty}catch(e){}}if(!d){try{var s=localStorage.getItem("xiuxian-game-settings");if(s){var o=JSON.parse(s);if(o&&o.difficulty)d=o.difficulty}}catch(e){}}var q=Qr.difficulty[d]||Qr.difficulty.normal,v=Number(q&&q[r]);return isFinite(v)&&v>0?v:1}catch(e){return 1}},YlxwDiffGain=(x,f)=>{try{if(!(x>0))return x;var m=YlxwDiffMul(void 0,f);return isFinite(m)&&m>0?Math.floor(x*m):x}catch(e){return x}},/*YLXW_R232_V2951*/YlxwServerDiff=()=>{try{var d=window.__ylSrvDiff;return (d==="easy"||d==="normal"||d==="hard")?d:null}catch(e){return null}},YlxwSrvDiffCapture=(j)=>{try{if(!j||typeof j!=="object")return;var d=j.ylDifficulty;if(d==="easy"||d==="normal"||d==="hard")window.__ylSrvDiff=d}catch(e){}},Lm='


def _count(text, needle):
    """门禁计数：tuple/list = 多形态合计计数（R-246 漂移修复）；str = 直接计数。"""
    if isinstance(needle, (tuple, list)):
        return sum(text.count(x) for x in needle)
    return text.count(needle)


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    g = []
    # 每个入账点：新串在位（count=n）+ 旧串清零（count=0）
    for label, old, new, n in EDITS:
        # ★ R-246：E1 的「新串在位」针下游被合法改写（r222/r232）⇒ tuple 合计新旧两形态。
        #   注意用 [:3]=='E1 '（带空格）精确匹配，避免误伤 E10~E16。
        needle = (new, E1_NEW_ALT) if label[:3] == 'E1 ' else new
        g.append(('%s · 新串在位' % label, needle, n, '==', ''))
        g.append(('%s · 旧串清零' % label, old, 0, '==', ''))
    # 幂等标记唯一
    g.append(('幂等标记唯一', MARK, 1, '==', '/*YLXW_R218_V2945*/'))
    # 取值器在位
    g.append(('取值器 YlxwDiffMul 在位', 'YlxwDiffMul=(t,r)=>{', 1, '==', ''))
    g.append(('取值器 YlxwDiffGain 在位', 'YlxwDiffGain=(x,f)=>{', 1, '==', ''))
    # 难度表新字段在位
    g.append(('easy 档 expMul/stoneMul', 'expMul:1,stoneMul:1}', 1, '==', ''))
    g.append(('normal 档 expMul/stoneMul', 'expMul:1.5,stoneMul:1.5}', 1, '==', ''))
    g.append(('hard 档 expMul/stoneMul', 'expMul:2,stoneMul:2}', 1, '==', ''))
    # 冻结（消耗 / 惩罚）
    for name, needle, cnt in FREEZE:
        g.append((name, needle, cnt, '==', '冻结未动'))
    return g


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert MARK == '/*YLXW_R218_V2945*/', '幂等标记被改动'
    for name, old, new, n in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old and new, '%s 锚点不得为空' % name
        assert n >= 1, '%s n 必须 >=1' % name
        # old 不得是 new 的子串（否则「旧串清零」门禁在补丁后仍为 1，破坏幂等判定）
        assert old not in new, '%s old 是 new 的子串，会破坏旧串清零门禁' % name
        # 形态一致性：本环全部为纯 ASCII（无 \uXXXX 转义 / 无字面中文）
        assert all(ord(ch) < 128 for ch in old), '%s old 必须纯 ASCII' % name
        assert all(ord(ch) < 128 for ch in new), '%s new 必须纯 ASCII' % name

    # 取值器必须含关键子串：倍率字段名、store 兜底、恒等兜底
    assert 'Qr.difficulty[d]||Qr.difficulty.normal' in E1_new, '取值器缺难度表回退'
    assert 'xiuxian-game-settings' in E1_new, '取值器缺 localStorage 兜底键'
    assert 'if(!(x>0))return x' in E1_new, '取值器缺「非正值原样返回」保护'
    assert 'Math.floor(x*m)' in E1_new, '取值器缺取整'
    assert MARK in E1_new, '取值器缺幂等标记'

    # 每个入账点新串必须调用 YlxwDiffGain（E0*/E1 为定义处，除外）
    for name, _old, new, _n in EDITS:
        if name.startswith('E0') or name.startswith('E1'):
            continue
        assert 'YlxwDiffGain(' in new, '%s 新串未调用 YlxwDiffGain' % name

    # 倍数正确性：难度表三档
    assert ',expMul:1,stoneMul:1}' in E0a_new, 'easy 倍率有误'
    assert ',expMul:1.5,stoneMul:1.5}' in E0b_new, 'normal 倍率有误'
    assert ',expMul:2,stoneMul:2}' in E0c_new, 'hard 倍率有误'

    # E16 兼做消耗：必须保留 `-w`（消耗不放大）
    assert 'k.spiritStones-w+' in E16_new, 'E16 丢失 -w（消耗被破坏）'
    assert 'k.spiritStones-w+YlxwDiffGain(D,"stoneMul")' in E16_new, 'E16 未只放大 +D'

    # E4 必须先乘倍率再套封顶（不越过 _ylExpCap）
    assert 'Math.min(YlxwDiffGain(r.expChange,"expMul"),_ylExpCap(t))' in E4_new, \
        'E4 未按「先乘倍率再封顶」处理'

    # 注入内容不得含网络 / 定时器原语（localStorage 兜底是**有意**的只读读取，允许）
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
    fd, tmp = tempfile.mkstemp(prefix='.r218chk-', suffix='.js')
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


def _dump_views(txt0, txt1):
    """打印每个入账点补丁前后的解码视图对照（±90 字符窗口）。"""
    print('  --- 入账点补丁前后解码视图（±90 字符）---')
    for name, old, new, _n in EDITS:
        i0 = txt0.find(old)
        i1 = txt1.find(new)
        if i0 < 0 or i1 < 0:
            print('    [WARN] %s 未定位到（%d/%d）' % (name, i0, i1))
            continue
        before = txt0[max(0, i0 - 90):i0 + len(old) + 90]
        after = txt1[max(0, i1 - 90):i1 + len(new) + 90]
        print('    · %s' % name)
        print('        前: %s' % before.replace('\n', '\\n'))
        print('        后: %s' % after.replace('\n', '\\n'))


def main() -> int:
    ap = argparse.ArgumentParser(description='R-218 开局难度收益倍率（客户端 --src 补丁）')
    ap.add_argument('--src', required=True,
                    help='装配产物 js（如 build/assets/index-v2945-20261009.js）')
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
        print('[SKIP] source looks already patched（R-218 倍率表 + 取值器 + 全部入账点已在位）')
        return 3
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 2) 基线碰撞检查：新串不得已在基线出现
    for _name, _old, new, _n in EDITS:
        c = txt0.count(new)
        if c != 0:
            print('[FAIL] 新串已在基线出现 %d 次，拒绝写盘：%s' % (c, new[:60]))
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
        act = _count(out_txt, needle)
        good = (act == exp)
        ok = ok and good
        if not good:
            print('  [FAIL] %-40s actual=%d expect %s %d %s'
                  % (label, act, op, exp, note))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  [OK] 门禁全绿（入账点 %d 处；冻结 %d 项）' % (len(EDITS), len(FREEZE)))

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
    bak = src_path + '.bak-r218-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r218-', suffix='.tmp')
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
