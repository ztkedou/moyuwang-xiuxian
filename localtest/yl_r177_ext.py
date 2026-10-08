# -*- coding: utf-8 -*-
r"""
yl_r177_ext.py — R-177（自动历练节奏稳定）+ R-178（三档奖励概率收敛）
                 standalone 纯客户端补丁

需求原文（台账，逐字）
--------------------------------------------------------------------------
  R-177：「自动历练现在有一个明显的卡顿感，是一种频率不一样的感觉，感觉有的时候
          2,3秒出一条，有的时候可能十秒才会出一条。」
  R-178：「三条历练方式变化有点过大：〔三条真实日志样例，低/中/高三档收益〕……
          把这三档几率做一个大幅度调整，第一档大部分情况。第二档偶尔会出现。
          第三档很少出现。不要像现在一样感觉经常被触发高档位加成。」

  三条样例（用户原话，作为三档量级参照）：
      ① 采到紫猴花：修为 +22 / 灵石 +21 / 气血 +19 / 掉落      ← 第一档（低）
      ② 小灵石矿脉：修为 +91 / 灵石 +732                      ← 第二档（中）
      ③ 古洞府传承：修为 +367 / 灵石 +3302 / 气血 +97 / 奇遇   ← 第三档（高）

==============================================================================
一、目标 bundle 与实测口径
==============================================================================
  目标：build/assets/index-v2927-20261006.js（2,302,499 B / 2,134,727 chars）
  本环全部结论均在本机对上述文件**字符级实测**；R-178 的概率表由 node 22.22.2
  **真实执行 bundle 内模板表**（pw/hw/xw/gw/bw/Fm 逐字抽取）后解析求得，
  并与真实 Fm() 抽样对拍一致（见 §三）。

==============================================================================
二、R-177 根因（证据链，全部为 bundle 内真实代码行）
==============================================================================
  [证据 1] 自动历练驱动循环（组件 Hw，@632075 定义，@632309 起循环）：
      function Hw({autoMeditate:t,autoAdventure:r,player:a,loading:l,cooldown:c,
                   ...,handleMeditate:T,handleAdventure:$,setCooldown:M,...}){
        const N=O.useRef(T),k=O.useRef($),...
        const U=YlxwBgInterval(async()=>{window.__ylLifeAuto=Q();if(Q()){...}
          if(q.current)return; ... try{await k.current(); ...} ...},500);
      ⇒ 每 500 ms 轮询一次，调用 k.current() = 入参 handleAdventure。
        （YlxwBgInterval 为 R-139 的 Worker 心跳计时器，绕过隐藏页节流；非本环改动对象。）
  [证据 2] handleAdventure 的来源（@1964053）：
      ge=nk({player:r,setPlayer:a,addLog:l,triggerVisual:c,setLoading:$,setCooldown:M,
             loading:x,cooldown:T,onOpenShop:...,skipBattle:(E==null?void 0:E.skipBattle)||!1,
             fleeOnBattle:(E==null?void 0:E.fleeOnBattle)||!1,
             skipShop:(E==null?void 0:E.skipShop)||!1,autoAdventure:f,...})
      nk（@1908569）返回 {handleAdventure:async()=>{...}, executeAdventure:I}。
      ⇒ Hw 的 handleAdventure 就是 nk 返回的那个。
  [证据 3] handleAdventure 门禁与两条互斥路径（@1914750 起）：
      handleAdventure:async()=>{
        if(u||f>0)return;                          // u=loading, f=cooldown；冷却未到即跳过
        ... const V=Math.min(.3,B+Y+L+P);
        if(Math.random()<.15)
          if(c(!0),a("你在路上发现了一处商铺...","normal"),_)
            a("你选择跳过商店，继续历练...","normal"),c(!1),d(2);      // 分支A 冷却 2 秒
          else{setTimeout(()=>{...v(ee),c(!1),d(2)},3e2);return}       // 分支B 冷却 2 秒
        const Z=Math.random()<V;Z&&a("✨ 你福至心灵，触发了奇遇！","special");
        await I(Z?"lucky":"normal")                                    // 分支C 主路
      }
  [证据 4] 主路 I 的收尾冷却（@1914231）：
      }catch{a("历练途中突发异变，你神识受损，不得不返回。","danger")}finally{c(!1),d(10)}};
  [证据 5] 主路 I 内的结算展示固定延时（@1914217，本环**不动**）：
      await new Promise(oe=>setTimeout(oe,1500)),V=(Q==="secret_realm"?V:YlxwAdvBoostR44(V)),...
  [证据 6] 商店跳过开关默认值（@638705 Uw.DEFAULT_CONFIG / @2061653 zk）：
      {skipBattle:!0, fleeOnBattle:!1, skipShop:!0, skipReputationEvent:!0, minHpThreshold:20}
      ⇒ 默认 skipShop=true ⇒ _=M&&x=true ⇒ 15% 分支走「跳过商店」路径（d(2)，不弹窗、无收益）。

  ── 结论（根因）──
  两条**并存的冷却档位**：
      主路 85%  ：轮询 0~0.5s + 结算展示 1.5s + 冷却 10s ≈ 11.5~12.0 s/条  →「十秒才出一条」
      商店跳过 15%：轮询 0~0.5s + 冷却 2s             ≈ 2.0~2.5 s/条（无收益）→「2,3秒出一条」
    加权平均周期 = 0.85×11.75 + 0.15×2.25 ≈ 10.33 s。
  ⇒ 「频率不一样」不是随机抖动、也不是网络（循环体内无网络 await；YlxwInhStoneRoll / sk AI
    均为 fire-and-forget 不阻塞），而是 15% 的商店跳过分支把节奏从 ~11.5s 拉到 ~2.2s。
  另有 3 处 d(1)/d(2)（避战 @1909381 / @1910721、挑战初始化 @1909786、天地之魄弹窗
    @1913287 / @1913346）仅在**手动模式**（fleeOnBattle / onOpenTurnBasedBattle / 弹窗确认）
    可达；默认自动历练（skipBattle=true, fleeOnBattle=false）走不到，故本环不动。

  ── 改法（只调节奏，不改任何收益数值）──
  统一冷却到 9 秒：主路 d(10)→d(9)；商店跳过 / 商店访问 d(2)→d(9)。
  1.5s 结算展示延时保持不变（属结算展示区，非本环范围）。
  收益中性核算（轮询取区间中点 0.25s）：
      旧：0.85×(0.25+1.5+10) + 0.15×(0.25+2)  = 0.85×11.75 + 0.15×2.25 = 10.325 s
      新：0.85×(0.25+1.5+ 9) + 0.15×(0.25+9)  = 0.85×10.75 + 0.15×9.25 = 10.525 s
      Δ = +0.20 s（+1.9%）⇒ 单位时间收益 −1.9%，视为中性（略偏保守，不放大收益）。
  节奏带宽：由「2.25 s ↔ 11.75 s（5.2 倍）」收敛为「9.25 s ↔ 10.75 s（1.16 倍）」。

==============================================================================
三、R-178 根因与三档概率表
==============================================================================
  [证据 7] Fm() 的三档加权（@574713，t==="normal" 分支）：
      if(t==="normal"&&v.length>0){const m=v.map(S=>{...
        const $=Math.abs(S.expChange)+Math.abs(S.spiritStonesChange);
        return $>500?x*=.2+f*1.5:$>200?x*=.5+f*1:x*=1-f*.3,
        S.petObtained&&(x*=.3+f*1.2),S.hpChange<0&&(x*=0.35),{template:S,weight:x}}),...
    ⇒ 三档 = 按 $（|修为变动|+|灵石变动|）分桶：高 $>500 / 中 $>200 / 低 其余。
      其中 f=((c>=0?c:0)+((lv||1)-1)/9)/fe.length（境界进度 0~0.984，fe 为 7 境界数组）。
    ⇒ **判定条件是确定性的奖励量级 $**（由事件本身决定），不是一次随机 roll；
      本环只改「按 $ 分桶后的权重」，不改任何事件的奖励数值。
  [证据 8] 模板表真实构造（@541236）：
      pw(){for(r=0;r<720;r++)push(hw(r));for(r<120)push(xw(r));for(r<300)push(gw(r));for(r<60)push(bw(r))}
      Oc={NORMAL:720,LUCKY:120,SECRET_REALM:300,SECT_CHALLENGE:60}
  [证据 9] Fm() 的境界门禁（在加权之前执行，@574713）：
      if(a){const m=fe.indexOf(ae.SpiritSevering),j=fe.indexOf(ae.LongevityRealm),b=fe.indexOf(a);
        v=v.filter(S=>S.heavenEarthSoulEncounter?b>=m:S.longevityRuleObtained?b>=j:!0)}
    ⇒ 该门禁把 heavenEarthSoul（≥化神）与 longevityRule（≥长生）模板在低境界剔除。本环不改门禁。

  ── 实测（node 执行真实模板表；解析式加权=精确值，与 Fm() 抽样对拍一致）──
  1200 条模板中 adventureType==="normal" 共 650 条。$ 直方图：
      (0,50]:332 (50,100]:177 (100,150]:90 (150,200]:27
      (200,300]:0 (300,500]:0 (500,800]:1 (800,1200]:17 (1200,2000]:6
  ⇒ **200~500 区间为空**，原「中档 $>200」是**死代码**：原始人口 t1/t2/t3 = 626/0/24。
    24 条高档模板**全部**是 longevityRule（门禁 ≥长生）⇒ 第三档只在长生境界出现；
    其 story 前缀即用户样例③的「你在一处古洞府中探索时，突然感受到…」。

  旧行为（现网）实测 [低/中/高 %]：
      炼气 [80.1/19.9/0.0]  筑基 [80.7/19.3/0.0]  金丹 [81.2/18.8/0.0]
      元婴 [81.8/18.2/0.0]  化神 [82.3/17.7/0.0]  合道 [82.8/17.2/0.0]
      长生 [76.7/15.4/8.0]  长生9 [76.0/14.7/9.3]
  ⇒ 长生境界高档位 8.0~9.3% —— 即「经常被触发高档位加成」的量化证据。

  ── 改法 ──
  权重块替换（中档阈值 200→100：因 200~500 为空，只有下移到 100 才能让中档「活」起来）：
      旧： $>500?x*=.2+f*1.5 : $>200?x*=.5+f*1 : x*=1-f*.3
      新： $>500?x*=.5        : $>100?x*=.88   : x*=1
  高档 ×0.50（大幅抑制）、中档 ×0.88（轻微抑制）、低档 ×1（基准）。
  稀有度 / 灵宠 / 负气血 三个对比因子**原样保留**（仙品/传说/稀有物品、灵宠、负气血仍被压制）。
  中档人口 117/650 = 18.0%、高档人口 24/650 = 3.7%，经 ×0.88 / ×0.50 抑制后落在需求区间。

  三档最终概率表（低/中/高，%；node 解析式精确值，[ ] 内为 Fm() 抽样对拍）：
      炼气 82.1/17.9/0.0    筑基 82.6/17.4/0.0    金丹 83.1/16.9/0.0
      元婴 83.6/16.4/0.0    化神 84.1/15.9/0.0    合道 84.6/15.4/0.0
      长生 83.2/14.7/2.2    长生9 83.6/14.3/2.1
  全境界×等级(1~9)扫描边界：低 [82.1, 85.0] / 中 [14.2, 17.9] / 高 [0.0, 2.4]
  ⇒ 落在需求区间 80~85 / 13~18 / 1~3 之内。高档在低境界为 0.0 是**既有境界门禁**所致
     （本环不改门禁）；在长生境界为 2.1~2.2%，满足「第三档很少出现」。
  抽样对拍（Fm() 400k 次 vs 解析式）：
      炼气 80.1/19.9/0.0 vs 80.1/19.9/0.0；金丹5 81.5/18.5/0.0 vs 81.5/18.5/0.0；
      长生 76.6/15.4/8.0 vs 76.7/15.4/8.0  （旧权重，验证模型正确）

==============================================================================
四、锚点（对 build/assets/index-v2927-20261006.js 字符级实测，替换锚点全为纯 ASCII）
==============================================================================
  替换锚点（打前 count==1，打后 count==0）：
    A1 `}finally{c(!1),d(10)}`                                   ← R-177 主路冷却
    A2 `c(!1),d(2);else{`                                        ← R-177 商店跳过冷却
    A3 `v(ee),c(!1),d(2)},3e2);return}`                          ← R-177 商店访问冷却
    A4 `const $=Math.abs(S.expChange)+Math.abs(S.spiritStonesChange);return $>500?x*=.2+f*1.5:$>200?x*=.5+f*1:x*=1-f*.3,`
                                                                 ← R-178 三档权重块
  冻结针脚（对**原件**校验，count 必须 == 1；全为纯 ASCII）：
    function Fm(t="normal",r,a,l){          ← Fm 签名未动
    Oc={NORMAL:720,LUCKY:120,SECRET_REALM:300,SECT_CHALLENGE:60}
    function hw(t){const a=at([             ← 事件类型表未动
    const m=v.map(S=>{var M,h,R;let x=1;    ← Fm 加权入口未动
    S.petObtained&&(x*=.3+f*1.2)            ← 灵宠对比因子未动
    S.hpChange<0&&(x*=0.35)                 ← 负气血对比因子未动
    ?x*=.1+f*2:                             ← 稀有度对比因子未动（ASCII 片段）
    x*=.3+f*1.5                             ← 传说对比因子未动
    x*=.5+f*1:                              ← 稀有对比因子未动
    E==="稀有"?x*=.5+f*1:                   ← 稀有对比因子（唯一形态；含裸中文，见 ★）
    const U=YlxwBgInterval(async()=>{window.__ylLifeAuto=Q();   ← 自动历练循环未动
    if(u||f>0)return;                       ← handleAdventure 门禁未动
    return{handleAdventure:async()=>{       ← 返回结构未动
    executeAdventure:I}                     ← 返回结构未动
    await new Promise(oe=>setTimeout(oe,1500)),V=   ← 结算展示 1.5s 延时未动
  ★ 本环**替换锚点**（A1~A4）全为纯 ASCII，无需中文登记。
  ★ 唯一含裸中文的针脚：冻结 `E==="稀有"?x*=.5+f*1:`（以及同族的 `?x*=.1+f*2:`、`x*=.3+f*1.5`
     两条为 ASCII 片段）。原因：稀有度对比因子 `E==="稀有"` 的裸中文形态在 bundle 内 count==1，
     而纯 ASCII 片段 `x*=.5+f*1:` 在 bundle 内 count==2（稀有度分支与量级分支各一次），
     无法唯一锚定；故该条冻结针脚采用带裸中文的唯一形态，如实登记于此。
  ★ 跨环冲突声明：本环只动「冷却/权重」两处；**未触碰**结算汇总相关函数
     YlxwAdvSummary / YlxwAdvStatNew / YlxwAdvStatAcc（另一并行改动对象），
     门禁中仅以 >=1 断言其存在。A1 与 `await Fg({...})`（@1914217 同一行）相邻但不同区间：
     A1 位于该行**之后**的 finally 内（@1914231），二者不重叠。

==============================================================================
五、契约（照 localtest/yl_r169b_ext.py）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 权重探针）。
  · 二进制读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 <src>.bak-r177-<时刻>。
  · 幂等：产物已含标记 `[r177adv]` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r177adv]'

# --------------------------------------------------------------------------- 替换项

# R-177：主路收尾冷却 10s → 9s，并落幂等标记。
A1_OLD = '}finally{c(!1),d(10)}'
A1_NEW = '}finally{c(!1),d(9)}/*' + IDEMPOTENT_MARK + '*/'

# R-177：商店跳过分支冷却 2s → 9s。
A2_OLD = 'c(!1),d(2);else{'
A2_NEW = 'c(!1),d(9);else{'

# R-177：商店访问（setTimeout 300ms）分支冷却 2s → 9s。
A3_OLD = 'v(ee),c(!1),d(2)},3e2);return}'
A3_NEW = 'v(ee),c(!1),d(9)},3e2);return}'

# R-178：Fm() 三档权重块（中档阈值 200→100；高档 ×0.50、中档 ×0.88、低档 ×1）。
A4_OLD = ('const $=Math.abs(S.expChange)+Math.abs(S.spiritStonesChange);'
          'return $>500?x*=.2+f*1.5:$>200?x*=.5+f*1:x*=1-f*.3,')
A4_NEW = ('const $=Math.abs(S.expChange)+Math.abs(S.spiritStonesChange);'
          'return $>500?x*=.5:$>100?x*=.88:x*=1,')

# 供权重探针使用的**打后**表达式（不含尾逗号）
A4_CORE = ('const $=Math.abs(S.expChange)+Math.abs(S.spiritStonesChange);'
           'return $>500?x*=.5:$>100?x*=.88:x*=1')

REPS = [
    ('R177-1 主路收尾冷却 d(10)->d(9) + 幂等标记', A1_OLD, A1_NEW),
    ('R177-2 商店跳过冷却 d(2)->d(9)', A2_OLD, A2_NEW),
    ('R177-3 商店访问冷却 d(2)->d(9)', A3_OLD, A3_NEW),
    ('R178-1 Fm 三档权重收敛', A4_OLD, A4_NEW),
]

# 冻结针脚：本环只动上面四处，下列既有形态必须逐字在位（对**原件**校验，全 ASCII）
FREEZE = [
    ('function Fm(t="normal",r,a,l){', 1),                 # Fm 签名未动
    ('Oc={NORMAL:720,LUCKY:120,SECRET_REALM:300,SECT_CHALLENGE:60}', 1),  # 模板表规模未动
    ('function hw(t){const a=at([', 1),                    # 事件类型表未动
    ('const m=v.map(S=>{var M,h,R;let x=1;', 1),           # Fm 加权入口未动
    ('S.petObtained&&(x*=.3+f*1.2)', 1),                   # 灵宠对比因子未动
    ('S.hpChange<0&&(x*=0.35)', 1),                        # 负气血对比因子未动
    ('?x*=.1+f*2:', 1),                                    # 稀有度对比因子未动
    ('x*=.3+f*1.5', 1),                                    # 传说对比因子未动
    ('E==="稀有"?x*=.5+f*1:', 1),                          # 稀有对比因子未动（含中文，见 §四 ★）
    ('const U=YlxwBgInterval(async()=>{window.__ylLifeAuto=Q();', 1),  # 自动历练循环未动
    ('if(u||f>0)return;', 1),                              # handleAdventure 门禁未动
    ('return{handleAdventure:async()=>{', 1),              # 返回结构未动
    ('executeAdventure:I}', 1),                            # 返回结构未动
    ('await new Promise(oe=>setTimeout(oe,1500)),V=', 1),  # 结算展示 1.5s 延时未动
]


# ---- 退役针脚标记（0.9.30 起）----
# 语义：本环（R-177/R-178）**排在 R-180 之前**套用 ⇒ apply 时这三条自产形态**仍在**（count==1）；
#   而 R-180（0.9.30）已**合法改写**它们（E2：Fm 中档权重 `$>100?x*=.88` → `$>100?x*=.30`，
#   整个权重块随之变化）⇒ 终态（dryrun 复核）必须为 0。单条 (needle, expect) 无法同时满足
#   apply 态(1) 与终态(0)，故退役 = **终态专用**：dryrun 在终态复核（期望 0）；
#   本环 apply 时跳过（不检），避免「老补丁依赖新补丁」——新形态由 R-180 自己的门禁负责。
#
# ★ 0.9.35 扩充（R-199）：本环排在 R-199 之前 ⇒ apply 时自产的 3 条 d(9) 形态**仍在**（各 count==1）；
#   而 R-199（0.9.35）已**合法改写**为 d(7)（正常收尾 finally / 商店跳过 / 商店访问）⇒ 终态必须为 0。
#   同理由：3 条「已 9s」门禁退役 = 终态专用（dryrun 终态复核期望 0；本环 apply 跳过）；
#   新形态由 R-199 自己的门禁负责（R199·主路冷却已 7s / 商店跳过已 7s / 商店访问已 7s == 1，且 全库 d(9)==0 / d(7)==3）。
RETIRED_TAG = '【已退役·终态专用】'


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R177·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r177adv] 恰好 1 处'),
        ('R177·主路冷却已 9s' + RETIRED_TAG, '}finally{c(!1),d(9)}', 0, '==',
         'R-199/0.9.35 已合法改写为 d(7) ⇒ 本环自产 9s 形态终态清零（新形态由 R199·主路冷却已 7s 覆盖）'),
        ('R177·主路冷却旧值已清零', '}finally{c(!1),d(10)}', 0, '==', 'd(10) 已消失'),
        ('R177·商店跳过已 9s' + RETIRED_TAG, 'c(!1),d(9);else{', 0, '==',
         'R-199/0.9.35 已合法改写为 d(7) ⇒ 本环自产 9s 形态终态清零（新形态由 R199·商店跳过已 7s 覆盖）'),
        ('R177·商店跳过旧值已清零', 'c(!1),d(2);else{', 0, '==', 'd(2) 已消失'),
        ('R177·商店访问已 9s' + RETIRED_TAG, 'v(ee),c(!1),d(9)},3e2);return}', 0, '==',
         'R-199/0.9.35 已合法改写为 d(7) ⇒ 本环自产 9s 形态终态清零（新形态由 R199·商店访问已 7s 覆盖）'),
        ('R177·商店访问旧值已清零', 'v(ee),c(!1),d(2)},3e2);return}', 0, '==', 'd(2) 已消失'),
        ('R177·结算展示延时未动', 'await new Promise(oe=>setTimeout(oe,1500)),V=', 1, '==', '1.5s 延时保持'),
        ('R178·权重块已替换' + RETIRED_TAG, A4_NEW, 0, '==', 'R-180/0.9.30 已合法改写此形态 ⇒ 本环冻结针脚退役'),
        ('R178·权重块旧值已清零', A4_OLD, 0, '==', '旧权重块已消失'),
        ('R178·高档权重 .5', '$>500?x*=.5:', 1, '==', '高档 ×0.50'),
        ('R178·中档权重 .88' + RETIRED_TAG, '$>100?x*=.88:', 0, '==', 'R-180/0.9.30 已合法改写此形态 ⇒ 本环冻结针脚退役'),
        ('R178·旧高档权重已清零', '$>500?x*=.2+f*1.5', 0, '==', ''),
        ('R178·旧中档阈值已清零', '$>200?x*=.5+f', 0, '==', ''),
        ('R178·中档阈值已下移' + RETIRED_TAG, '$>100?x*=.88', 0, '==', 'R-180/0.9.30 已合法改写此形态 ⇒ 本环冻结针脚退役'),
        ('冲突·结算汇总函数仍在', 'YlxwAdvSummary', 1, '>=', '未触碰并行改动对象'),
        ('冲突·结算统计函数仍在', 'YlxwAdvStatNew', 1, '>=', '未触碰并行改动对象'),
        ('冲突·结算累计函数仍在', 'YlxwAdvStatAcc', 1, '>=', '未触碰并行改动对象'),
    ]
    for needle, cnt in FREEZE:
        g.append(('冻结 ' + needle[:24], needle, cnt, '==', '冻结既有形态'))
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
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        if RETIRED_TAG in label:
            # 退役针脚（终态专用）：本环 apply 时 R-180 尚未套用，自产形态仍在 ⇒ 不检；
            # 终态由 dryrun 复核（期望 0），新形态由 R-180 自己的门禁负责。
            continue
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
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
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


def _weight_probe(patched_text):
    """从补丁后产物抽出**真实**权重块，用 node 验证三档倍率与边界。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。
    """
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    i = patched_text.find(A4_CORE)
    if i < 0:
        return False, '权重块未找到'
    core = patched_text[i:i + len(A4_CORE)]
    core = core.replace(';return ', ';', 1)  # 变成语句序列，便于取回 x
    js = ('function W(S){let x=1,f=.3;' + core + ';return x;}\n'
          'function chk(n,a,b){if(a!==b)throw new Error(n+": "+a+" != "+b);}\n'
          'chk("low<=100",W({expChange:0,spiritStonesChange:50}),1);\n'
          'chk("low boundary 100",W({expChange:100,spiritStonesChange:0}),1);\n'
          'chk("mid 150",W({expChange:0,spiritStonesChange:150}),.88);\n'
          'chk("mid 500",W({expChange:250,spiritStonesChange:250}),.88);\n'
          'chk("high 600",W({expChange:0,spiritStonesChange:600}),.5);\n'
          'chk("high 3669",W({expChange:367,spiritStonesChange:3302}),.5);\n'
          'console.log("weight-probe OK: low=1 mid=.88 high=.5");\n')
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:300]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 权重探针。"""
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r177] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r177] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r177] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r177] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r177] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r177] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _weight_probe(out)
    if ok is False:
        print('[r177] SELFTEST FAIL weight-probe: ' + pmsg)
        return 1
    print('[r177] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s; %s'
          % (len(gates()), len(out) - len(s0), nmsg, pmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r177] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r177] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r177] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r177] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r177] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r177] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-40s %s' % (label.replace(RETIRED_TAG, ''),
                                         'SKIP(退役·终态复核)' if RETIRED_TAG in label else 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r177-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r177] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-40s %s' % (label.replace(RETIRED_TAG, ''),
                                     'SKIP(退役·终态复核)' if RETIRED_TAG in label else 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
