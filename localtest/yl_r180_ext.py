# -*- coding: utf-8 -*-
r"""
yl_r180_ext.py — R-180 自动历练三修（寿命累计 / 灵石产出分布 / 掉血强度）standalone 纯客户端
                    ★★ 本版为「v3 -> v4 升级」+「v0/v2/v3 -> v4」多路径补丁 ★★

==============================================================================
零、本次（v4）只做一件事：把「几千」档的奇遇率从 3% 改成 1%
==============================================================================
用户拍板原话：「改成 1%」—— 指 v3 里控制「几千」档的**奇遇率 EV**。

v4 的唯一数值改动（+ 幂等标记换代）：
  · EV：`V=Math.min(.3,0.03+(t.luck||0)*.001)` → `V=Math.min(.3,0.01+(t.luck||0)*.001)`
  · 幂等标记：`[r180adv3]` → `[r180adv4]`
    （v3 标记已存在于 0.9.32 产物中，沿用会被判「已打过」而跳过 ⇒ 必须换代。）
  · ★ 其余一律逐字保留：E1（寿命累计）、E2（主路中档 `S.spiritStonesChange>=40?x*=0.7`）、
    E3（奇遇灵石量级 `Ge(t,200,500,490)` 保持已回滚态）、E4、
    **E5/E6/E7（掉血几率/带宽、挂机标记、被动回血 —— 用户正在实测，绝不触碰）**。

★ v4 与 v1/v2/v3 的关系：
  · E1（寿命累计）**逐字不动**（仅幂等标记升级到 v4）。
  · E2/E3/E4/E5/E6/E7 与 v3 **逐字相同**。
  · EV 在 v3 基础上只把常数 0.03 换成 0.01。

------------------------------------------------------------------------------
一、机制定位（node 从真实产物抽出 1200 条模板 + 真实 Fm 权重 + 真实 Ym 结算链）
------------------------------------------------------------------------------
  · 模板表：`Oc={NORMAL:720,LUCKY:120,SECRET_REALM:300,SECT_CHALLENGE:60}`（共 1200），
    由 `pw()` 调 `hw`(普通)/`xw`(奇遇)/`gw`/`bw` 生成；每条模板的 raw 灵石/修为由
    `Ge(t,lo,hi,salt)=floor(yy(t*1000+salt)*(hi-lo))+lo` 决定（**对 t 完全确定**）。
  · 档位由**模板自身 raw 灵石量级**决定（玩家结算值 = raw × u × 5.1）：
      - 主路普通 `hw` raw 灵石：battle 10~39 / cave 40~119 / spiritStone 50~149 /
        evilCultivator 50~129 / cultivator 0 或 20~89 / 其余 0；
        另有 `longevityRule` raw 500~999（**仅长生境界可抽**，见下）。
      - 奇遇 `xw` raw 灵石：`spiritStonesChange:Ge(t,200,500,490)` = 200~499。
  · 奇遇率 EV（`handleAdventure`）：`V=Math.min(.3,0.01+(t.luck||0)*.001)`（v4）；
    自动历练会跳过「商铺」分支（`if(Math.random()<.15)` 内 auto 直接 `d(9)` 继续），
    故 `P(奇遇)=V` **全额生效**；随后 `await I(Math.random()<V?"lucky":"normal")`。
  · 选择器 `Fm(type,risk,realm,realmLevel)`：normal 池按「物品稀有度因子 × $ 量级」加权，
    奇遇池（lucky）为**均匀抽取**；`longevityRule`/`heavenEarthSoul` 受境界闸门过滤
    （`S.longevityRuleObtained?b>=j:!0`，j = LongevityRealm 序）⇒ 仅长生可抽 longevityRule。
  · 结算链 `Ym(t,{realm,realmLevel,maxHp},YLXW_STONE_MUL_ADV=0.2)` → `YlxwAdvBoostR44`(×0.85)
    → `YlxwAdvBoostR97`(×3) ⇒ **有效倍率 = u × 5.1**，其中
    `u=[1,1.236928,1.529991,1.892489,2.340873,2.895491,3.581514][realmIdx] × (1+(L-1)*0.3)`。
  · 零灵石模板：Ym 走 R-145 兜底 `min(50,max(1,floor(floor(exp*u)*.5)))` ⇒ 结算 ≤ 127。

------------------------------------------------------------------------------
二、v4 目标概率与设计
------------------------------------------------------------------------------
★ 与 v3 完全相同的设计（只换常数）：档位由模板 raw 量级决定（与境界无关），概率全境界统一，
  数值再由 u 缩放（= 用户要的「不同等级灵石的数量不同」）。

  v3 两处最小改动（v4 逐字沿用）：
    ① 奇遇率 EV 常数化（去 境界/等级 依赖，保留 幸运）：`V=Math.min(.3,BASE+(t.luck||0)*.001)`
       v3 BASE=0.03 → **v4 BASE=0.01**。
    ② 主路中档权重按模板 raw 灵石分档：`$>100?x*=.30` → `S.spiritStonesChange>=40?x*=0.7`。
       ★ `$>500?x*=.5:` 与 `x*=1-f*.3` 为 R-177/R-188 的跨补丁门禁，逐字保留。

------------------------------------------------------------------------------
三、多路径（逐槽位自动识别）
------------------------------------------------------------------------------
  基线 v0 = 装配产物（`build_v26n.build(BASE)` 后再按 `STANDALONE_CLIENT` 套 r116~r179，
            **R-180 之前**；权重块 `$>100?x*=.88`、无 `[r180adv*]`、无 `__ylPD`/`__ylAdvDrain`）
  基线 v2 = `build/assets/index-v2931-20261007.js`（0.9.31，`[r180adv2]`，EV 为境界依赖式）
  基线 v3 = `build/assets/index-v2932-20261008.js`（0.9.32 线上，`[r180adv3]`，EV=0.03 版）
  ⇒ 三条路径产出同一个 v4 形态。

  逐槽位判定（`_slot_state`）：v4 形态在位 → SKIP；否则 v3 → v2 → v1 → v0 依次匹配；
  全缺 → ABORT(rc=2)。全部槽位已 v4 ⇒ 整体 SKIP（rc=3）。

  槽位表：
    | 槽位 | 改动 | v3 | v2 | v0 |
    |---|---|---|---|---|
    | E1 | 幂等标记 -> [r180adv4] | 标记替换 | 标记替换 | 注入（v0 原件） |
    | E2 | 主路中档 -> `stone>=40?x*=.7` | no-op | 改 | 改 |
    | EV | 奇遇率常数 0.03 -> 0.01 | 改 | 改 | 改 |
    | E3 | 奇遇灵石量级 200~500 | no-op | no-op | no-op |
    | E4 | 奇遇气血 0~0 | no-op | no-op | 改 |
    | E5 | Ym 掉血几率/带宽 | no-op | no-op | 改 |
    | E6 | 挂机 effect（去 60 分上限 / 加 __ylAdvDrain） | no-op | no-op | 改 |
    | E7 | 被动回血几率化 | no-op | no-op | 改 |

------------------------------------------------------------------------------
四、v4 实测（node 真跑抽取出的真实 1200 条模板 + 真实 Fm 权重 + 真实 Ym 结算链；
    n=30 万/境界/口径；realmLevel=1；luck=0；自动历练 ⇒ 奇遇率全额生效）
------------------------------------------------------------------------------
  交叉验证：把 normal 池构造逐字切出后采样，与直接调用真实 `Fm('normal',…)` 对比，
  7 境界三档比例**逐位相同**（V=0 全 normal，n=6000/境界）⇒ 采样口径与线上一致。

  A) 参考档口径（结算按 u=1，即炼气 L1；检验「全境界概率统一」）—— 常态 / 几百 / 几千：
       ┌────────┬──────────────┬──────────────┐
       │ 境界    │ v3（3%）      │ v4（1%）      │
       ├────────┼──────────────┼──────────────┤
       │ 炼气L1  │ 82.52/14.49/3.00 │ 84.30/14.71/1.00 │
       │ 筑基L1  │ 83.52/13.44/3.04 │ 85.26/13.73/1.01 │
       │ 金丹L1  │ 84.36/12.64/3.00 │ 86.09/12.92/0.99 │
       │ 元婴L1  │ 85.11/11.81/3.08 │ 86.97/11.99/1.04 │
       │ 化神L1  │ 85.85/11.11/3.05 │ 87.67/11.33/1.00 │
       │ 合道L1  │ 86.47/10.56/2.97 │ 88.20/10.78/1.03 │
       │ 长生L1  │ 85.34/9.81/4.85  │ 87.02/10.03/2.94 │
       └────────┴──────────────┴──────────────┘
     ⇒ **几千 = 1.00%（炼气~合道）**，完全命中期望；长生 2.94%（比 v3 的 4.85% 低约 1.9pp），
       多出的 ~1.9pp 来自 longevityRule 境界闸门（raw 500~999，仅长生可抽）。

  B) 实结算口径（u 随境界，玩家实际看到的值）—— 常态 / 几百 / 几千 / 均值：
       ┌────────┬──────────────────────┬──────────────────────┐
       │ 境界    │ v3（3%）              │ v4（1%）              │
       ├────────┼──────────────────────┼──────────────────────┤
       │ 炼气L1  │ 82.52/14.49/3.00 151.7│ 84.30/14.71/1.00 117.5│
       │ 筑基L1  │ 82.46/14.50/3.04 182.3│ 84.20/14.80/1.01 139.8│
       │ 金丹L1  │ 82.58/14.01/3.41 217.2│ 84.28/14.33/1.40 164.6│
       │ 元婴L1  │ 81.47/14.31/4.22 260.1│ 83.17/14.62/2.21 194.6│
       │ 化神L1  │ 80.91/13.51/5.57 308.4│ 82.61/13.80/3.59 226.4│
       │ 合道L1  │ 81.29/11.47/7.24 360.6│ 82.87/11.74/5.40 263.7│
       │ 长生L1  │ 79.74/9.64/10.62 679.3│ 81.30/9.85/8.84 565.5│
       └────────┴──────────────────────┴──────────────────────┘
     ⇒ 常态稳定占多数（81~88%），均值随境界单调上升（= 用户要的「数量随等级变」）；
       固定绝对阈值下「几千」随境界升（1%→8.8%）是 u 缩放所致（v3 同机制：3%→10.6%）。
       ★ v4 与 v3 的**唯一差异就是奇遇（= 几千载体）概率**：炼气~合道 v3→v4 恰减 2.0pp。

  C) R-184 悟道影响（R-184 挂在「几千」事件，判据 `tpl.spiritStonesChange>=200` ⟺ 奇遇；
     长生另有 longevityRule 亦 ≥200）。一次历练 ≈ 10.75 秒：
       ┌────────┬───────────────┬───────────────┐
       │ 境界    │ v3 触发率 / 平均 │ v4 触发率 / 平均 │
       ├────────┼───────────────┼───────────────┤
       │ 炼气L1  │ 3.00% / 5.98 分  │ 1.00% / 17.99 分 │
       │ 筑基L1  │ 3.04% / 5.90 分  │ 1.01% / 17.82 分 │
       │ 金丹L1  │ 3.00% / 5.97 分  │ 0.97% / 18.38 分 │
       │ 元婴L1  │ 3.06% / 5.86 分  │ 1.02% / 17.49 分 │
       │ 化神L1  │ 3.05% / 5.87 分  │ 1.01% / 17.77 分 │
       │ 合道L1  │ 2.97% / 6.04 分  │ 1.02% / 17.50 分 │
       │ 长生L1  │ 4.85% / 3.70 分  │ 2.93% / 6.11 分  │
       └────────┴───────────────┴───────────────┘
     ⇒ R-184 触发频率随 EV 同步降为 1/3：炼气~合道 约 6 分/次 → 约 18 分/次。
       ★ 本环**只报告、不改 R-184 文件**。

==============================================================================
五、备选（供决策，非本环默认）
==============================================================================
  · 若嫌 1% 太低，可回退到 v3 的 `V_LUCK_BASE = 0.03`（本文件改一个常数即可）。
  · 若连「幸运」项也要常数化：`V=0.01`（一行）。
  · `longevityRule` 境界闸门保留（删它会让炼气期抽到长生规则内容，属内容/进度变更）。

==============================================================================
六、契约
==============================================================================
  · CLI：`--src <bundle.js>`（就地写回）/ `--check`（只校验不写盘）/ `--selftest`。
  · 就地替换，全部纯 ASCII 注入；bytes 层读、就地原子写回（tempfile + os.replace）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 渲染/行为探针（node，真跑抽取出的真实代码）：
      ① YlxwAdvSummary 在 life=-5.5 时渲染「寿命减少 5.5 年」且位于「物品获得」前；
      ② 真实权重块三档倍率（低 1 / 中 .7 / 高 .5，伤害权重 .35 未动）+ 档位按 raw 灵石归属；
      ③ 奇遇率 EV = 0.01（与境界/等级无关，含 `fe.indexOf` 的旧式已消失）；
      ④ 真实 Ym：掉血 = maxHp×(1.0%~3.2%) 且随 maxHp 缩放、奇遇不回血、正向模板回血 = maxHp×(0.05%~0.15%)；
      ⑤ 真实停止判定 D(U)：hp≤maxHp×阈值% 返回 true（阈值逻辑未改）；
      ⑥ 真实被动回血：非挂机 = 0.25% 恒定；挂机 = 25% 几率 × 0.05~0.15%。
  · 不跑网络：只读 --src 指向的本地文件。
"""


import argparse
import os
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r180adv4]'   # v4 新幂等标记（E1 注释内）
V3_MARK = '[r180adv3]'           # v3 旧幂等标记
V2_MARK = '[r180adv2]'           # v2 旧幂等标记
V1_MARK = '[r180adv]'            # v1 旧幂等标记

# ---- 退役针脚标记（0.9.36 起）----
# 语义：本环（R-180 v4）**排在 R-191 / R-193 之前**套用 ⇒ apply 时 EV 的 1% 形态**仍在**（count==1）；
#   而 R-191（0.9.32）先把它重写为「有界幸运项」，R-193（0.9.33）最终把 EV 换成「纯称号来源」公式
#   （`V=0.01+Math.min(0.03,$a(titleId,unlockedTitles).luck*0.0003)`，默认 1% / 顶配称号 4%）
#   ⇒ 本环注入的 1% 形态在终态为 0。
# 单条 (needle, expect) 无法同时满足 apply 态(1) 与终态(0)，故退役 = **终态专用**：
#   · dryrun 读 gates() 在终态复核（期望 0，如实反映 R-191/R-193 改写后的形态）；
#   · 本环 apply/--check 时跳过（不检、不计 FAIL），避免「老补丁依赖新补丁」——新形态由
#     R-191 / R-193 自己的门禁负责。
RETIRED_TAG = '【已退役·终态专用】'

# --------------------------------------------------------------------------- 参数（v4 灵石档位）

# 奇遇率 V（「几千」档载体）常数化：base + 幸运项（幸运非「境界」，保留其作用）
V_LUCK_BASE = 0.01               # 全境界统一基线 1%（v4：3% -> 1%）
# 主路中档（「几百」档）权重：按模板 raw 灵石量分档
MID_STONE_MIN = 40               # raw 灵石 ≥ 40 记为中档（炼气结算 ≈ 204~765 = 几百）
MID_W = 0.7                      # 中档权重（低档 ×1 不变）


def _num(x):
    """浮点转纯 ASCII JS 字面量（去尾 0），保证注入串可复现。"""
    s = ('%.6f' % float(x)).rstrip('0').rstrip('.')
    return s or '0'

# --------------------------------------------------------------------------- 槽位锚点

# ── E1 寿命累计 + 幂等标记 ───────────────────────────────────────────────────
E1_SIG_V4 = '/*' + IDEMPOTENT_MARK + '*/(h>0&&typeof YLXW_ADV_STAT'
E1_SIG_V3 = '/*' + V3_MARK + '*/(h>0&&typeof YLXW_ADV_STAT'
E1_SIG_V2 = '/*' + V2_MARK + '*/(h>0&&typeof YLXW_ADV_STAT'
E1_SIG_V1 = '/*' + V1_MARK + '*/(h>0&&typeof YLXW_ADV_STAT'
E1_SIG_V0 = '-h)),h>0&&m('
# v0 -> v4 注入块（= v1/v2/v3 注入块，仅标记换成 v4；纯 ASCII）
E1_V4_BLOCK = ('/*' + IDEMPOTENT_MARK + '*/'
               '(h>0&&typeof YLXW_ADV_STAT==="object"&&YLXW_ADV_STAT'
               '&&YLXW_ADV_STAT.sess&&typeof YLXW_ADV_SESS!=="undefined"'
               '&&YLXW_ADV_STAT.sess===YLXW_ADV_SESS&&(YLXW_ADV_STAT.life-=h)),h>0&&m(')
E1_INJECT = 'YLXW_ADV_STAT.sess===YLXW_ADV_SESS&&(YLXW_ADV_STAT.life-=h)'  # 门禁用

# ── E2 主路中档权重：$ 口径 -> raw 灵石口径（档位与境界无关）────────────────────
E2_MID_NEW = 'S.spiritStonesChange>=%d?x*=%s' % (MID_STONE_MIN, _num(MID_W))
E2_SIG_V4 = E2_MID_NEW
E2_MID_V2 = '$>100?x*=.30'      # A 基线（v2 产物）
E2_MID_V1 = '$>100?x*=.30'      # v1 产物同形
E2_MID_V0 = '$>100?x*=.88'      # B 基线（R-180 之前）

# ── EV 奇遇率 V 常数化（去 境界/等级 依赖，保留 幸运）─────────────────────────
V_OLD = ('B=.05,Y=U*.02,L=(t.realmLevel-1)*.01,P=t.luck*.001,'
         'V=Math.min(.3,B+Y+L+P)')                 # v0/v2 的境界依赖式
V_V3 = 'V=Math.min(.3,0.03+(t.luck||0)*.001)'      # v3 的 3% 形态（v4 待清零）
V_NEW = 'V=Math.min(.3,%s+(t.luck||0)*.001)' % _num(V_LUCK_BASE)   # v4 目标（1%）
V_SIG_V4 = V_NEW + ';if(Math.random()<.15)'

# ── E3 奇遇灵石量级 20~70 -> 200~500（回滚 v1 的方向性错误；v3 保持回滚态）──────
E3_SIG_V2 = 'spiritStonesChange:Ge(t,200,500,490)'
E3_SIG_V1 = 'spiritStonesChange:Ge(t,20,70,490)'

# ── E4 奇遇气血 30~80 -> 0~0 ─────────────────────────────────────────────────
E4_SIG_V2 = 'hpChange:Ge(t,0,0,470)'
E4_SIG_V0 = 'hpChange:Ge(t,30,80,470)'

# ── E5 Ym 掉血几率 / 带宽（★ 逐字不动）──────────────────────────────────────
PD = 0.40
DRAIN_LO = 0.010
DRAIN_SPAN = 0.022
E5_PD_LIT = '__ylPD=%s/(1-__ylV)' % _num(PD)
E5_SIG_V2 = E5_PD_LIT
E5_SIG_V1 = '__ylPD=.14/(1-__ylV)'
E5_SIG_V0 = ('u=c*d,f={story:t.story,hpChange:t.hpChange<0?Math.floor(t.hpChange*u*0.25):'
             'Math.floor(t.hpChange*u),expChange:')
E5_BAND_LIT = '%s+Math.random()*%s' % (_num(DRAIN_LO), _num(DRAIN_SPAN))
E5B_DRAIN_LIT = 'Math.floor(r.maxHp*(%s))' % E5_BAND_LIT   # 门禁/探针复用
E5_V2_BLOCK = ('u=c*d,__ylV=Math.min(.3,.05+a*.02+(r.realmLevel-1)*.01+(r.luck||0)*.001),'
               + E5_PD_LIT + ',f={story:t.story,hpChange:(t.adventureType==="normal"'
               '&&Math.random()<__ylPD)?-Math.max(1,Math.floor(r.maxHp*(' + E5_BAND_LIT + ')))'
               ':t.hpChange>0?Math.max(1,Math.floor(r.maxHp*.001*(.5+Math.random()))):0,expChange:')

# ── E6 删「60 分钟硬上限」整套 / 加挂机标记 __ylAdvDrain（★ 逐字不动）────────
E6_SIG_V2 = 'window.__ylAdvDrain=!0;const U='
E6_SIG_V1 = 'window.__ylAdvStart=0;return}'
E6_SIG_V0 = ('O.useEffect(()=>{if(!r){q.current=!1;return}const U=YlxwBgInterval(async()=>'
             '{window.__ylLifeAuto=Q();if(Q()){q.current&&(q.current=!1);return}')
E6_V2_HEAD = ('O.useEffect(()=>{if(!r){q.current=!1,window.__ylAdvDrain=!1;return}'
              'window.__ylAdvDrain=!0;const U=YlxwBgInterval(async()=>'
              '{window.__ylLifeAuto=Q();if(Q()){q.current&&(q.current=!1);return}')
E6_V0_CLEANUP = 'return()=>{YlxwBgClear(U),A.current.forEach(B=>clearTimeout(B)),A.current=[]}'
E6_V2_CLEANUP = 'return()=>{window.__ylAdvDrain=!1,YlxwBgClear(U),A.current.forEach(B=>clearTimeout(B)),A.current=[]}'

# v1 注入的 60 分上限中文串以 \uXXXX 转义形式存在于产物内（纯 ASCII）
_CN60 = ('\\u81ea\\u52a8\\u5386\\u7ec3\\u5df2\\u8fbe 60 \\u5206\\u949f\\u4e0a\\u9650'
         '\\uff0c\\u5df2\\u81ea\\u52a8\\u505c\\u6b62\\u3002')
E6A_V1_OLD = ('O.useEffect(()=>{if(!r){q.current=!1,window.__ylAdvDrain=!1,'
              'window.__ylAdvStart=0;return}'
              'window.__ylAdvDrain=!0;window.__ylAdvStart||(window.__ylAdvStart=Date.now());'
              'const U=YlxwBgInterval(async()=>{window.__ylLifeAuto=Q();'
              'if(h&&h.minHpThreshold>0&&window.__ylAdvStart&&'
              'Date.now()-window.__ylAdvStart>=36e5){'
              'q.current=!1,window.__ylAdvStart=0,R&&R(!1),E&&E("' + _CN60 + '","warning");return}'
              'if(Q()){q.current&&(q.current=!1);return}')
E6A_V1_NEW = E6_V2_HEAD

# ── E7 被动回血几率化（★ 逐字不动）──────────────────────────────────────────
E7_SIG_V2 = 'window.__ylAdvDrain)?(Math.random()<.25?'
E7_SIG_V0 = 'const T=Math.max(1,Math.floor(S*.0025));return x.hp<S?'
E7_V0 = ('const T=Math.max(1,Math.floor(S*.0025));'
         'return x.hp<S?{...x,hp:Math.min(S,x.hp+T)}:x}')
E7_V2 = ('const T=(typeof window!=="undefined"&&window.__ylAdvDrain)?'
         '(Math.random()<.25?Math.max(1,Math.floor(S*.001*(.5+Math.random()))):0)'
         ':Math.max(1,Math.floor(S*.0025));'
         'return x.hp<S&&T>0?{...x,hp:Math.min(S,x.hp+T)}:x}')

# --------------------------------------------------------------------------- 槽位表

SLOTS = [
    {
        'name': 'E1 寿命累计注入 + 幂等标记 ->[r180adv4]',
        'sig_v2': E1_SIG_V4,
        'variants': [
            ('v3', E1_SIG_V3, [(V3_MARK, IDEMPOTENT_MARK)]),
            ('v2', E1_SIG_V2, [(V2_MARK, IDEMPOTENT_MARK)]),
            ('v1', E1_SIG_V1, [(V1_MARK, IDEMPOTENT_MARK)]),
            ('v0', E1_SIG_V0, [(E1_SIG_V0, '-h)),' + E1_V4_BLOCK)]),
        ],
    },
    {
        'name': 'E2 主路中档权重按 raw 灵石分档',
        'sig_v2': E2_SIG_V4,
        'variants': [
            ('v2', E2_MID_V2, [(E2_MID_V2, E2_MID_NEW)]),
            ('v0', E2_MID_V0, [(E2_MID_V0, E2_MID_NEW)]),
        ],
    },
    {
        'name': 'EV 奇遇率 V 常数化（去境界/等级依赖；3% -> 1%）',
        'sig_v2': V_SIG_V4,
        'variants': [
            ('v3', V_V3, [(V_V3, V_NEW)]),      # v3 产物（0.03 版）
            ('pre', V_OLD, [(V_OLD, V_NEW)]),   # v0/v2 基线同形（均为境界依赖式）
        ],
    },
    {
        'name': 'E3 奇遇灵石量级保持回滚态 200~500',
        'sig_v2': E3_SIG_V2,
        'variants': [
            ('v1', E3_SIG_V1, [(E3_SIG_V1, E3_SIG_V2)]),
        ],
    },
    {
        'name': 'E4 奇遇气血 30~80 -> 0~0',
        'sig_v2': E4_SIG_V2,
        'variants': [
            ('v0', E4_SIG_V0, [(E4_SIG_V0, E4_SIG_V2)]),
        ],
    },
    {
        'name': 'E5 Ym 掉血几率/带宽（不动）',
        'sig_v2': E5_SIG_V2,
        'variants': [
            ('v1', E5_SIG_V1, [(E5_SIG_V1, E5_PD_LIT),
                               ('.03+Math.random()*.06', E5_BAND_LIT)]),
            ('v0', E5_SIG_V0, [(E5_SIG_V0, E5_V2_BLOCK)]),
        ],
    },
    {
        'name': 'E6 挂机 effect（删 60 分上限 / 加 __ylAdvDrain；不动）',
        'sig_v2': E6_SIG_V2,
        'variants': [
            ('v1', E6_SIG_V1, [(E6A_V1_OLD, E6A_V1_NEW)]),
            ('v0', E6_SIG_V0, [(E6_SIG_V0, E6_V2_HEAD),
                               (E6_V0_CLEANUP, E6_V2_CLEANUP)]),
        ],
    },
    {
        'name': 'E7 被动回血几率化（不动）',
        'sig_v2': E7_SIG_V2,
        'variants': [
            ('v0', E7_SIG_V0, [(E7_V0, E7_V2)]),
        ],
    },
]

# 冻结针脚：本环只动 E1 标记 / E2 中档 / EV 奇遇率，下列既有稳定形态必须逐字在位。
#   ★ 只钉本批不动的函数签名 / 结构锚，**不钉** R-181/183/184/185/187/188/190 会新增或改写的串。
FREEZE = [
    ('function Fm(', 1),                 # 模板选择器仍在（E2 所在）
    ('function xw(', 1),                 # 奇遇模板生成器仍在（E3/E4 所在）
    ('function Hw(', 1),                 # 自动历练循环仍在（E6 所在）
    ('function Ym(', 1),                 # 事件结算仍在（E5 所在）
    ('function Lw(', 1),                 # 被动回血仍在（E7 所在）
    ('function YlxwAdvSummary(el)', 1),  # R-179 汇总未动
    ('var YLXW_ADV_SESS', 1),            # 会话变量未动
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R180v4·新幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r180adv4] 恰好 1 处'),
        ('R180v4·v3 旧标记已清零', V3_MARK, 0, '==', '[r180adv3] 不再出现'),
        ('R180v4·v2 旧标记已清零', V2_MARK, 0, '==', '[r180adv2] 不再出现'),
        ('R180v4·v1 旧标记已清零', V1_MARK, 0, '==', '[r180adv] 不再出现'),
        ('R180v4·E1 寿命累加逻辑仍在位', E1_INJECT, 1, '==', 'E1 逐字不动'),
        ('R180v4·E1 裸锚点已消失', '-h)),h>0&&m(', 0, '==', ''),
        # ---- E2 主路中档（v3：按 raw 灵石分档）----
        ('R180v4·E2 中档按 raw 灵石分档在位', E2_MID_NEW, 1, '==', E2_MID_NEW),
        ('R180v4·E2 旧中档 .30 已清零', E2_MID_V2, 0, '==', ''),
        ('R180v4·E2 旧中档 .88 已清零', E2_MID_V0, 0, '==', ''),
        ('R180v4·★ 高档权重未动（R-177 门禁）', '$>500?x*=.5:', 1, '==', ''),
        ('R180v4·★ 普通物品因子未动（R-188 门禁）', 'x*=1-f*.3', 1, '==', ''),
        ('R180v4·★ R-177 旧高档已清零', '$>500?x*=.2+f*1.5', 0, '==', ''),
        ('R180v4·★ R-177 旧中档阈值已清零', '$>200?x*=.5+f', 0, '==', ''),
        # ---- EV 奇遇率（★ 终态退役：R-191/R-193 已合法重写 EV 公式）----
        ('R180v4·EV 奇遇率已常数化 1%' + RETIRED_TAG, V_SIG_V4, 0, '==',
         'R-191/R-193 已合法重写奇遇率公式（R-193 终态 = 纯称号来源、封顶 3%）⇒ 旧 1% 形态终态归 0；'
         '新形态由 R191/R193 自己的门禁负责（本环 apply 跳过）'),
        ('R180v4·EV 旧 3% 形态已清零', V_V3, 0, '==', 'v3 的 0.03 版已清除'),
        ('R180v4·EV 旧境界依赖式已清零', 'V=Math.min(.3,B+Y+L+P)', 0, '==', ''),
        ('R180v4·EV 旧境界序依赖项已清零', 'Y=U*.02', 0, '==', ''),
        # ---- E3/E4/E5/E6/E7 保持（不动）----
        ('R180v4·E3 已回滚（原量级在位）', E3_SIG_V2, 1, '==', 'spiritStonesChange:Ge(t,200,500,490)'),
        ('R180v4·E3 误改量级已清零', E3_SIG_V1, 0, '==', 'Ge(t,20,70,490) 已清除'),
        ('R180v4·E4 奇遇气血 0 在位', E4_SIG_V2, 1, '==', 'E4 保留'),
        ('R180v4·E4 旧奇遇气血已清零', E4_SIG_V0, 0, '==', ''),
        ('R180v4·E5a 新 PD 在位', E5_SIG_V2, 1, '==', E5_SIG_V2),
        ('R180v4·E5a 旧 PD=.14 已清零', E5_SIG_V1, 0, '==', ''),
        ('R180v4·E5b 新掉血带宽在位', E5B_DRAIN_LIT, 1, '==', '掉血随 maxHp 缩放'),
        ('R180v4·E5b 旧带宽已清零', '.03+Math.random()*.06', 0, '==', ''),
        ('R180v4·E5b 掉血仍按普通历练几率触发', 't.adventureType==="normal"&&Math.random()<__ylPD', 1, '==', ''),
        ('R180v4·E5b 回血仍为 maxHp 百分比', 'Math.floor(r.maxHp*.001*(.5+Math.random()))', 1, '==', ''),
        ('R180v4·E6a 挂机标记已置', 'window.__ylAdvDrain=!0;const U=', 1, '==', ''),
        ('R180v4·E6b 挂机标记已清', 'window.__ylAdvDrain=!1', 2, '==', 'r=false 与 cleanup 各一处'),
        ('R180v4·E6a 60 分上限记账已整体移除', '__ylAdvStart', 0, '==', ''),
        ('R180v4·E6a 计时器分支已移除', '>=36e5', 0, '==', ''),
        ('R180v4·E6a 阈值守卫已移除', 'minHpThreshold>0&&window.__ylAdvStart', 0, '==', ''),
        ('R180v4·E7 被动回血已几率化', 'window.__ylAdvDrain)?(Math.random()<.25?', 1, '==', ''),
        ('R180v4·E7 非挂机保持 0.25%/s', ':Math.max(1,Math.floor(S*.0025))', 1, '==', ''),
        ('R180v4·★ 停止阈值逻辑未被改', 'D=U=>{if(!h||h.minHpThreshold<=0)return!1;', 1, '==', ''),
        ('R180v4·★ 阈值百分比公式未被改', 'P=L*(h.minHpThreshold/100);return B<=P?', 1, '==', ''),
        ('R180v4·Fm 伤害权重未被改', 'S.hpChange<0&&(x*=0.35)', 1, '==', ''),
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


def _slot_state(s, slot):
    """返回 TARGET(=目标态) / variant 名 / None（None = 该槽位锚点全缺）。"""
    if slot['sig_v2'] in s:
        return 'TARGET'
    for variant, sig, _reps in slot['variants']:
        if sig in s:
            return variant
    return None


def _baseline_kind(states):
    st = set(states)
    if st == {'TARGET'}:
        return 'v4'
    if st <= {'v3', 'TARGET'} and 'v3' in st:
        return 'v3'
    if st <= {'v1', 'v2', 'pre', 'TARGET'} and 'v1' in st:
        return 'v1'   # v1 产物：E2 与 v2 同形（.30），故集合含 v2
    if st <= {'v0', 'pre', 'TARGET'} and 'v0' in st:
        return 'v0'
    if st <= {'v2', 'pre', 'TARGET'} and 'v2' in st:
        return 'v2'
    return 'mixed'


def _check_freeze(s):
    for needle, cnt in FREEZE:
        if s.count(needle) != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, s.count(needle), cnt)
    return None


def _transform(s):
    """对基线 s 做逐槽位就地替换，返回 (out, applied, states, err)。"""
    err = _check_freeze(s)
    if err is not None:
        return None, None, None, err
    out = s
    applied = []
    states = []
    for slot in SLOTS:
        st = _slot_state(s, slot)
        states.append(st)
        if st == 'TARGET':
            continue
        if st is None:
            return None, None, states, ('槽位「%s」既非目标形态，也未找到 v1/v2/v0 锚点：'
                                        '请确认 --src 是本游戏的可识别 bundle' % slot['name'])
        reps = None
        for variant, _sig, r in slot['variants']:
            if variant == st:
                reps = r
                break
        for old, new in reps:
            c = out.count(old)
            if c != 1:
                return None, None, states, ('槽位「%s」（%s 路径）锚点出现 %d 次（期望 1）：%r'
                                            % (slot['name'], st, c, old[:70]))
            out = out.replace(old, new, 1)
            applied.append((old, new))
    return out, applied, states, None


def _run_gates(out):
    for label, needle, expect, op, note in gates():
        if RETIRED_TAG in label:
            # 退役针脚（终态专用）：本环 apply 时 R-191/R-193 尚未套用，自产 1% 形态仍在 ⇒ 不检；
            # 终态由复核（期望 0）负责，新形态由 R-191/R-193 自己的门禁负责。
            continue
        c = out.count(needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0, applied):
    rev = out
    for old, new in reversed(applied):
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), _shutil_which('node'),
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _shutil_which(name):
    try:
        import shutil
        return shutil.which(name)
    except Exception:
        return None


def _fn_src(text, name):
    """从 text 中按花括号配对精确抽出 `function <name>(...) {...}` 源码。"""
    i = text.find('function %s(' % name)
    if i < 0:
        return None
    j = text.find('{', i)
    if j < 0:
        return None
    depth = 0
    k = j
    n = len(text)
    mode = None
    while k < n:
        c = text[k]
        if mode is None:
            if c == '"' or c == "'":
                mode = c
            elif c == '`':
                mode = '`'
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return text[i:k + 1]
            elif c == '/' and k + 1 < n and text[k + 1] == '/':
                k = text.find('\n', k)
                if k < 0:
                    return text[i:n]
            elif c == '/' and k + 1 < n and text[k + 1] == '*':
                k = text.find('*/', k)
                if k < 0:
                    return text[i:n]
                k += 1
        else:
            if c == '\\':
                k += 1
            elif c == mode:
                mode = None
        k += 1
    return text[i:n]


def _brace_src(text, start_needle):
    """从 start_needle 首次出现处起，按花括号配对抽出 `...{...}` 片段（含 start）。"""
    i = text.find(start_needle)
    if i < 0:
        return None
    j = text.find('{', i)
    if j < 0:
        return None
    depth = 0
    k = j
    n = len(text)
    mode = None
    while k < n:
        c = text[k]
        if mode is None:
            if c == '"' or c == "'":
                mode = c
            elif c == '`':
                mode = '`'
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return text[i:k + 1]
            elif c == '/' and k + 1 < n and text[k + 1] == '/':
                k = text.find('\n', k)
                if k < 0:
                    return text[i:n]
            elif c == '/' and k + 1 < n and text[k + 1] == '*':
                k = text.find('*/', k)
                if k < 0:
                    return text[i:n]
                k += 1
        else:
            if c == '\\':
                k += 1
            elif c == mode:
                mode = None
        k += 1
    return text[i:n]


def _node_run(js):
    """跑一段 js；返回 (rc, stdout, stderr) 或 (None, None, None) 当无 node。"""
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


def _summary_probe(patched_text):
    """抽真实 YlxwAdvSummary，验证「寿命减少」项渲染且位于「物品获得」之前。"""
    i = patched_text.find('function YlxwAdvSummary(el) {')
    j = patched_text.find('\nfunction YlxwAdvSession', i)
    if i < 0 or j < 0:
        return False, 'YlxwAdvSummary 定义/边界未找到'
    fn = patched_text[i:j]
    js = (
        fn + '\n'
        'var YLXW_ADV156_LINES = [];\n'
        'var Be = { getState: function(){ return { addLog: function(){} }; } };\n'
        'function YlxwAdvDur(ms){ return Math.floor(Number(ms)||0)+" ms"; }\n'
        'function YlxwAdvNum(n){ return Math.floor(Number(n)||0).toLocaleString(); }\n'
        'function YlxwAdvTypeName(t){ return {normal:"\\u5386\\u7ec3",lucky:"\\u5947\\u9047"}[t||""]||"\\u5386\\u7ec3"; }\n'
        'function base(){ return { runs:276, exp:46219, stone:210034, hp:5017, hpDown:4,\n'
        '  life:-5.5, lot:0, rep:230, drops:30, lucky:80, soul:0,\n'
        '  items:{"\\u7075\\u5929\\u7075\\u8349":1}, types:{normal:190, lucky:80} }; }\n'
        'function RUN(ST){ YLXW_ADV156_LINES=[]; YLXW_ADV_STAT=ST; YlxwAdvSummary(3030000); return YLXW_ADV156_LINES.slice(); }\n'
        'var A = RUN(base());\n'
        'var out = A.join(" \\u00b7 ");\n'
        'var pLife = out.indexOf("\\u5bff\\u547d\\u51cf\\u5c11 5.5 \\u5e74");\n'
        'var pItem = out.indexOf("\\u7269\\u54c1\\u83b7\\u5f97\\uff08");\n'
        'var pStone = out.indexOf("\\u7075\\u77f3 +210,034");\n'
        'if (pLife < 0) throw new Error("\\u5bff\\u547d\\u51cf\\u5c11\\u672a\\u6e32\\u67d3: "+out);\n'
        'if (pItem < 0) throw new Error("\\u7269\\u54c1\\u83b7\\u5f97\\u672a\\u6e32\\u67d3: "+out);\n'
        'if (!(pStone < pLife && pLife < pItem)) throw new Error("\\u5bff\\u547d\\u9879\\u672a\\u5728\\u7075\\u77f3\\u4e0e\\u7269\\u54c1\\u83b7\\u5f97\\u4e4b\\u95f4: "+[pStone,pLife,pItem]);\n'
        'var b0 = base(); b0.life = 0; var Z = RUN(b0)[0];\n'
        'if (Z.indexOf("\\u5bff\\u547d") >= 0) throw new Error("life=0 \\u4e0d\\u5e94\\u6e32\\u67d3");\n'
        'console.log("summary-probe OK");\n'
        'console.log("LIFE_MAIN>> " + A[0]);\n'
    )
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:400]
    return True, so.strip()


def _weight_probe(patched_text):
    """抽真实权重块，验证：低档 ×1 / 中档 ×.7（按 raw 灵石）/ 高档 ×.5；伤害权重 .35 未动。"""
    i = patched_text.find('v.map(S=>{')
    j = patched_text.find(',{template:S,weight:x}})', i)
    if i < 0 or j < 0:
        return False, '权重块未找到'
    inner = patched_text[i + len('v.map(S=>{'):j]
    inner = inner.replace(';return ', ';', 1)  # 去掉 return，使逗号表达式变语句序列
    js = ('function W(S){var f=.3;' + inner + ';return x;}\n'
          'function chk(n,a,b){if(a!==b)throw new Error(n+": "+a+" != "+b);}\n'
          'chk("low0",W({expChange:0,spiritStonesChange:0}),1);\n'
          'chk("low39",W({expChange:0,spiritStonesChange:39}),1);\n'
          'chk("mid40",W({expChange:0,spiritStonesChange:40}),' + _num(MID_W) + ');\n'
          'chk("mid149",W({expChange:0,spiritStonesChange:149}),' + _num(MID_W) + ');\n'
          'chk("high_longevity",W({expChange:300,spiritStonesChange:600}),.5);\n'
          'chk("dmgWeightUntouched",W({expChange:0,spiritStonesChange:0,hpChange:-40}),0.35);\n'
          'console.log("weight-probe OK: low=1 mid=' + _num(MID_W) + '(raw>=%d) high=.5 dmg=.35(untouched)");\n'
          % MID_STONE_MIN)
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:300]
    return True, so.strip()


def _v_probe(patched_text):
    """抽真实 handleAdventure 的奇遇率表达式，验证其与境界/等级无关（只依赖幸运）。"""
    i = patched_text.find('handleAdventure:async()=>{')
    if i < 0:
        return False, 'handleAdventure 未找到'
    seg = patched_text[i:i + 700]
    m = seg.find('V=')
    if m < 0:
        return False, 'V 表达式未找到'
    # V 表达式到下一个 ';'
    vexpr = seg[m + 2:seg.find(';', m)]
    if 'fe.indexOf' in vexpr or 'realmLevel' in vexpr or 'realm' in vexpr:
        return False, '奇遇率仍含境界依赖: ' + vexpr
    js = ('function V_(t){return ' + vexpr + ';}\n'
          'function chk(n,a,b){if(a!==b)throw new Error(n+": "+a+" != "+b);}\n'
          'chk("luck0",V_({luck:0}),' + _num(V_LUCK_BASE) + ');\n'
          'chk("luck100",V_({luck:100}),' + _num(V_LUCK_BASE) + '+0.1);\n'
          'console.log("v-probe OK: V(realm-independent) base=' + _num(V_LUCK_BASE) + ' +luck*0.001");\n')
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:300]
    return True, so.strip()


def _hp_probe(patched_text):
    """抽真实 Ym，验证：掉血=maxHp 百分比(DRAIN_LO~HI)且随 maxHp 缩放、奇遇不回血、
    正向模板回血=maxHp 百分比(0.05%~0.15%)。"""
    fn = _fn_src(patched_text, 'Ym')
    if not fn:
        return False, 'Ym 定义未找到'
    lo, hi = _num(DRAIN_LO), _num(DRAIN_LO + DRAIN_SPAN)
    js = ('var fe=["\\u70bc\\u6c14\\u671f","\\u7b51\\u57fa\\u671f","\\u91d1\\u4e39\\u671f",'
          '"\\u5143\\u5a74\\u671f","\\u5316\\u795e\\u671f","\\u5408\\u9053\\u671f","\\u957f\\u751f\\u5883"];\n'
          'var H={Pill:"Pill",Herb:"Herb"};\n'
          'function vg(){return "\\u666e\\u901a";}\n'
          'function pi(){return [];}\n'
          'function Ic(a,b){return {effect:a,permanentEffect:b};}\n'
          'function at(a,b){return a[0];}\n'
          + fn + '\n'
          'function run(tpl,maxHp,adv){return Ym(Object.assign({story:"",expChange:0,'
          'spiritStonesChange:0,eventColor:"normal"},tpl),'
          '{realm:"\\u70bc\\u6c14\\u671f",realmLevel:1,maxHp:maxHp,luck:0},0.2);}\n'
          'function hit(maxHp){for(var i=0;i<1200;i++){var r=run({adventureType:"normal",hpChange:-50},maxHp);'
          'if(r.hpChange<0)return r;}return null;}\n'
          'var a=hit(1e6); if(!a) throw new Error("\\u6389\\u8840 1200 \\u6b21\\u672a\\u89e6\\u53d1");\n'
          'var pct=-a.hpChange/1e6; if(!(pct>=' + lo + '&&pct<=' + hi + ')) throw new Error("\\u6389\\u8840\\u975e\\u767e\\u5206\\u6bd4: "+a.hpChange);\n'
          'var b=hit(1e8); var pct2=-b.hpChange/1e8; if(!(pct2>=' + lo + '&&pct2<=' + hi + ')) throw new Error("\\u6389\\u8840\\u672a\\u968f maxHp \\u7f29\\u653e: "+b.hpChange);\n'
          'var c=run({adventureType:"lucky",hpChange:0},1e6); if(c.hpChange!==0) throw new Error("\\u5947\\u9047\\u5e94\\u4e0d\\u56de\\u8840: "+c.hpChange);\n'
          'function heal(maxHp){for(var i=0;i<1200;i++){var r=run({adventureType:"normal",hpChange:40},maxHp);'
          'if(r.hpChange>0)return r;}return null;}\n'
          'var d=heal(1e6); if(!d) throw new Error("\\u56de\\u8840 1200 \\u6b21\\u672a\\u89e6\\u53d1");\n'
          'var hpct=d.hpChange/1e6; if(!(hpct>=0.0005&&hpct<=0.0015)) throw new Error("\\u56de\\u8840\\u975e\\u767e\\u5206\\u6bd4: "+d.hpChange);\n'
          'console.log("hp-probe OK: dmg="+(pct*100).toFixed(2)+"% of maxHp (scaled "+(pct2*100).toFixed(2)+"%), heal="+(hpct*100).toFixed(3)+"%, lucky=0");\n')
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:300]
    return True, so.strip()


def _stop_probe(patched_text):
    """抽真实停止判定 D(U)，验证阈值逻辑未被改：hp<=maxHp×阈值% 返回 true。"""
    src = _brace_src(patched_text, 'D=U=>{if(!h||h.minHpThreshold<=0)return!1;')
    if not src or not src.startswith('D=U=>{'):
        return False, 'D(U) 定义未找到'
    js = ('var h={minHpThreshold:10};\n'
          'function xt(U){return {maxHp:U.__maxHp};}\n'
          'var R=function(){},E=function(){};\n'
          'var ' + src + ';\n'
          'function chk(n,c){if(!c)throw new Error(n);}\n'
          'chk("below",D({hp:50,__maxHp:1000})===true);\n'
          'chk("at",D({hp:100,__maxHp:1000})===true);\n'
          'chk("above",D({hp:200,__maxHp:1000})===false);\n'
          'h={minHpThreshold:0}; chk("disabled",D({hp:1,__maxHp:1000})===false);\n'
          'h={minHpThreshold:10}; chk("again",D({hp:99,__maxHp:1000})===true);\n'
          'console.log("stop-probe OK: D(U) threshold=10% intact (10% of 1000 = 100)");\n')
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:300]
    return True, so.strip()


def _regen_probe(patched_text):
    """抽真实被动回血表达式：非挂机 = 0.25% 恒定；挂机 = 25% 几率 × 0.05~0.15%。"""
    i = patched_text.find('const T=(typeof window!=="undefined"&&window.__ylAdvDrain)?')
    if i < 0:
        return False, '新回血表达式未找到'
    j = patched_text.find(';return x.hp<S', i)
    if j < 0:
        return False, '新回血表达式边界未找到'
    expr = patched_text[i + len('const T='):j]
    js = ('function REGEN(S,adv,rnd){var window={__ylAdvDrain:adv};'
          'var _r=Math.random;Math.random=function(){return rnd;};'
          'var T=' + expr + ';Math.random=_r;return T;}\n'
          'function chk(n,c){if(!c)throw new Error(n);}\n'
          'chk("idle should be 0.25% maxHp", REGEN(1e6,false,0.5)===2500);\n'
          'chk("drain+rnd.5 should be 0", REGEN(1e6,true,0.5)===0);\n'
          'var h=REGEN(1e6,true,0.1); chk("drain heal pct", h>=500&&h<=1500);\n'
          'console.log("regen-probe OK: idle="+REGEN(1e6,false,0.5)+" drain="+REGEN(1e6,true,0.5)+" heal="+h);\n')
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:300]
    return True, so.strip()


def selftest(src):
    """内存自证：锚点 -> 补丁 -> 门禁 -> 往返 -> 幂等 -> node --check -> 6 个探针。"""
    s0 = _read(src)
    out, applied, states, err = _transform(s0)
    if err is not None:
        print('[r180v4] SELFTEST FAIL precheck: ' + err)
        return 1
    if not applied:
        print('[r180v4] SELFTEST SKIP: src already patched (v4)')
        return 0
    kind = _baseline_kind(states)
    e = _run_gates(out)
    if e is not None:
        print('[r180v4] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0, applied):
        print('[r180v4] SELFTEST FAIL round-trip mismatch')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r180v4] SELFTEST FAIL ' + nmsg)
        return 1
    for probe in (_summary_probe, _weight_probe, _v_probe, _hp_probe, _stop_probe, _regen_probe):
        ok, pmsg = probe(out)
        if ok is False:
            print('[r180v4] SELFTEST FAIL %s: %s' % (probe.__name__, pmsg))
            return 1
        print('[r180v4]   %s -> %s' % (probe.__name__, pmsg))
    print('[r180v4] SELFTEST OK [%s 基线]: gates=%d roundtrip=True delta=%+d chars; %s'
          % (kind, len(gates()), len(out) - len(s0), nmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r180v4] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    out, applied, states, err = _transform(s0)
    if err is not None:
        print('[r180v4] ABORT: ' + err)
        return 2
    if not applied:
        print('[r180v4] already upgraded to v4 (idempotent skip)')
        return 3
    kind = _baseline_kind(states)

    e = _run_gates(out)
    if e is not None:
        print('[r180v4] ' + e)
        return 1
    if not _roundtrip_ok(out, s0, applied):
        print('[r180v4] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r180v4] check OK [%s 基线] (%d -> %d chars, %+d)'
              % (kind, len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            if RETIRED_TAG in label:
                print('    [SKIP] %s 已退役（终态由 R-191/R-193 门禁复核）' % label.replace(RETIRED_TAG, ''))
            else:
                print('    gate %-44s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r180v4-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r180v4] patched [%s 基线]: %d -> %d chars (%+d) (backup %s)'
          % (kind, len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        if RETIRED_TAG in label:
            print('    [SKIP] %s 已退役（终态由 R-191/R-193 门禁复核）' % label.replace(RETIRED_TAG, ''))
        else:
            print('    gate %-44s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
