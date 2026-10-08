# -*- coding: utf-8 -*-
r"""
yl_r212_ext.py — R-212：历练结算「分档」概率调频为 **常态 85% / 稀有 14% / 奇遇 1%**（全境界统一）

（standalone 纯客户端；本补丁排在 R-191 / R-208 / R-209 / R-211 **之后**套用）

==============================================================================
零、问题与目标
==============================================================================
  用户（原话）：「以我现在炼气1以200以下的定义，把常态概率到85左右，稀有14%」；
  追问后明确：**所有境界**都要 85 / 14 / 1。

  ★★ 硬约束：**边界不动，只调频率**。
    · 分档边界（常态 0~200 / 稀有 200~1000 / 奇遇）由 R-211 钉死，并做了「随境界归一化」
      （判定输入 `ds/u`，见 yl_r211_ext.py）。**本环绝不改阈值、绝不改归一化。**
    · 概率是「频率」：要把稀有从 **~32.5%** 压到 **14%**，只能改**事件的相对权重/频率**。

==============================================================================
一、基线复现（node 真跑真实产物抽出的 1200 模板 + 真实 Fm 权重 + 真实 Ym 结算链 + 真实 DS）
==============================================================================
  口径：realmLevel=1 / luck=0 / 自动历练（奇遇率全额生效）；分档按 R-211 归一化 `ds/u` 判定。
  ┌────────┬────────┬────────┬────────┬───────────────┬───────────────┐
  │ 境界    │ 常态    │ 稀有    │ 奇遇    │ 战斗路贡献 pp  │ 中档模板 pp    │
  ├────────┼────────┼────────┼────────┼───────────────┼───────────────┤
  │ 炼气L1  │ 67.15  │ 31.91  │ 0.94   │ 24.17          │ 7.74          │
  │ 筑基L1  │ 65.40  │ 33.57  │ 1.03   │ 26.55          │ 7.03          │
  │ 金丹L1  │ 63.38  │ 35.65  │ 0.97   │ 28.52          │ 7.13          │
  │ 元婴L1  │ 61.41  │ 37.61  │ 0.97   │ 30.86          │ 6.75          │
  │ 化神L1  │ 58.70  │ 40.29  │ 1.00   │ 33.90          │ 6.39          │
  │ 合道L1  │ 53.53  │ 45.45  │ 1.02   │ 39.96          │ 5.49          │
  │ 长生L1  │ 43.35  │ 54.71  │ 1.93   │ 50.48          │ 5.13          │
  └────────┴────────┴────────┴────────┴───────────────┴───────────────┘
  ⇒ 炼气 67.15/31.91/0.94 ≈ 任务书给的 **66.7/32.5/0.9**，**基线复现成立**。

  ★★ 「稀有」两路占比（炼气 L1）：**战斗路胜场 ≈ 24pp** + **中档模板路 ≈ 7.7pp**。
     光压中档模板权重（7.7→0）**最多到 24%**，远到不了 14% ⇒ **必须同时处理战斗路**。

  ★★ 稀有占比**随境界单调上升**（31.9 → 54.7pp），主因是 `DS()` 里的
     `c = fe.indexOf(t.realm)*.02`（触发率随境界递增）。若不处理，**到不了「所有境界 85/14」**。

==============================================================================
二、三处最小改动（对 index-v2941-20261008.js 字符级实测，打前 count == 1）
==============================================================================
  · A：`DS()` 战斗触发率乘子 —— 抑制「随境界递增」并把触发压到下限。
      锚点：  v=Math.min(.7,(l+c+d-u)*f)
      改后：  v=Math.min(.7,(l+c+d-u)*f)*0.15/*[r212prob]*/

      ★ 形态零改动：`Math.min(.7,…)`、`fe.indexOf(t.realm)*.02`、`Math.max(.1,v)` 全部**逐字保留**，
        只在 `v` 赋值尾部追加乘子 ⇒ 无锚点冲突（等价改写）。
      ★ 0.15 使 7 境界的 `v` 全部落进既有下限 `Math.max(.1,v)` 的 0.1 内 ⇒ **触发率恒 10%**，
        境界项被下限吸收 ⇒ 稀有占比**跨境界近乎持平**（这正是「所有境界 85/14」的关键）。

  · B：`Fm()` 主路「中档」权重 —— 把「几百」档模板的抽取频率压下来。
      锚点：  S.spiritStonesChange>=40?x*=0.7
      改后：  S.spiritStonesChange>=40?x*=0.32

      ★ 该串被 **yl_r180_ext.py 的 gates 钉死**（E2_MID_NEW）。本环把 r180 的那条针
        **收窄成值无关形态** `S.spiritStonesChange>=40?x*=`（形态仍在、常量可变）——
        属「形态还在、只是常量变了 ⇒ 收窄」，非退役（详见 §四）。

  · C：`Fm()` 长生专属模板 `longevityRule` 降权 —— 抹平长生境奇遇虚高。
      锚点：  S.petObtained&&(x*=.3+f*1.2),S.hpChange<0&&(x*=0.35)
      改后：  S.petObtained&&(x*=.3+f*1.2),S.longevityRuleObtained&&(x*=0.05),S.hpChange<0&&(x*=0.35)

      ★ 长生境可抽 `longevityRule`（raw 500~999，仅长生，境界闸门 `S.longevityRuleObtained?b>=j:!0`），
        结算 >1000 ⇒ 计入**奇遇**。基线长生奇遇 1.93%（其余境界 ~1.0%）即由此而来。
      ★ 插入位置**必须在 `S.petObtained&&(x*=.3+f*1.2),` 之后、`S.hpChange<0&&(x*=0.35)` 之前** ——
        这两串被 **yl_r177_ext.py 的 FREEZE** 钉死，插在它们**之间**可保证两串**逐字连续**、r177 冻结针不破。

==============================================================================
三、参数扫描（N=40000；dsmul=DS 乘子 / midw=中档权重；`稀有%` 炼气→长生 序列）
==============================================================================
  固定 mmul=10（杠杆 B 被 _e2e_t11_adv.py 钉死，见 §四），winp≈0.97~0.99：
    dsmul=0.15  midw=0.9   21.26 21.28 20.67 20.77 20.51 20.29 19.79  (spread 1.49)
    dsmul=0.20  midw=0.9   21.58 21.05 20.69 20.71 20.59 20.04 20.20  (spread 1.54)
    dsmul=0.30  midw=0.9   21.13 21.10 20.63 20.48 20.79 22.60 25.09  (spread 4.61)
    dsmul=0.40  midw=0.9   21.51 21.80 22.21 23.27 24.18 25.72 29.30  (spread 7.79)
    dsmul=0.20  midw=0.6   17.66 17.64 17.42 17.24 16.94 17.23 17.04  (spread 0.72)
    dsmul=0.20  midw=0.4   15.26 15.15 15.02 14.97 14.94 15.16 14.93
    dsmul=0.20  midw=0.35  14.52 14.88 14.51 14.38 14.18 14.10 14.56
    dsmul=0.20  midw=0.30  13.94 13.91 13.85 13.77 13.90 13.56 13.91
    dsmul=0.20  midw=0.25  13.48 13.38 13.44 13.10 12.84 13.00 13.24
  ⇒ **dsmul=0.15~0.20** 把稀有跨境界 spread 从 ~23pp 压到 ~0.5~1.5pp；
     **midw≈0.30~0.33** 把稀有压到 ~14%，常态同步落 ~85%（恒等式 常态+稀有+奇遇=100）。
  ★ 在**真实终态文本**上对 midw 复扫（N=80000）：
       midw=0.30 稀有均值 13.82 / 常态均值 85.17
       midw=0.32 稀有均值 14.04 / 常态均值 84.94   ← **最终取值（最贴 85/14）**
       midw=0.33 稀有均值 14.26 / 常态均值 84.73
       midw=0.35 稀有均值 14.48 / 常态均值 84.51

  长生境 `longevityRule` 降权扫描（dsmul=0.20, midw=0.32, N=60000）——`奇遇%` 炼气→长生：
    lrw=1.0   1.03 0.96 1.03 0.98 0.99 1.00 3.03
    lrw=0.3   1.01 1.04 1.01 0.98 0.98 1.03 1.61
    lrw=0.15  1.01 1.00 1.02 0.96 0.98 1.00 1.30
    lrw=0.10  1.10 0.95 0.93 1.01 1.00 1.02 1.22
    lrw=0.05  1.00 1.00 0.98 1.04 0.95 1.08 1.14
  ⇒ `W_LR=0.05` 时 7 境界奇遇全部 ≈1.0~1.15%。

==============================================================================
四、为什么 **不** 用杠杆 B、不破 r177 / r180（关键决策，务必先读）
==============================================================================
  · 杠杆 B（`By()` 的 `M=Math.max(10,Math.round($*b))*10`）：被 **localtest/_e2e_t11_adv.py**
    判据钉死（`n('M=Math.max(10,Math.round($*b))*10') == 1`），且**不在本环可改文件清单内**
    ⇒ **禁用**。故「战斗胜场压进常态」不可行，只能走「触发率」路（本环 A）。
  · r177 FREEZE 钉死 `S.petObtained&&(x*=.3+f*1.2)` 与 `S.hpChange<0&&(x*=0.35)`：
    本环 C 的插入点选在**二者之间**，两串逐字连续 ⇒ **r177 冻结针不破**。
  · r180 gates 钉死 `S.spiritStonesChange>=40?x*=0.7`：本环 B 改其常量 ⇒ 必须**收窄**该针
    （见 §五），属「形态还在、常量变了」。

==============================================================================
五、收窄的既有针（唯一一处）
==============================================================================
  文件：`localtest/yl_r180_ext.py`
    · 原针：`('R180v4·E2 中档按 raw 灵石分档在位', E2_MID_NEW, 1, '==', E2_MID_NEW)`
      （`E2_MID_NEW = 'S.spiritStonesChange>=40?x*=0.7'`，钉死了常量 0.7）
    · 收窄：新增 `E2_MID_FORM = 'S.spiritStonesChange>=40?x*='`，针改用该**值无关形态**。
    · 理由：**形态整体仍在、只是常量变了**（0.7 → 0.3）⇒ 按本仓惯例属「收窄」而非「退役」。
    · `E2_MID_NEW` 仍用于**注入**（r180 自身仍注入 0.7，随后由本环改成 0.3）⇒ 注入逻辑零改动。

==============================================================================
六、终态实测（N=120000；dsmul=0.15 / midw=0.32 / W_LR=0.05；winp=0.99；
    在 v2941 套用 r212 后的**真实终态文本**上跑真实 1200 模板 + 真实 Fm/DS/Ym/By）
==============================================================================
  ┌────────┬────────┬────────┬────────┬────────┬──────────┐
  │ 境界    │ 常态    │ 稀有    │ 奇遇    │ 战触发  │ 均值灵石 │
  ├────────┼────────┼────────┼────────┼────────┼──────────┤
  │ 炼气L1  │ 84.95  │ 14.06  │ 0.99   │ 9.76   │ 147.1    │
  │ 筑基L1  │ 84.70  │ 14.29  │ 1.00   │ 9.97   │ 179.9    │
  │ 金丹L1  │ 84.86  │ 14.16  │ 0.98   │ 9.93   │ 215.6    │
  │ 元婴L1  │ 84.94  │ 14.09  │ 0.97   │ 9.87   │ 257.1    │
  │ 化神L1  │ 85.20  │ 13.81  │ 0.99   │ 9.87   │ 308.3    │
  │ 合道L1  │ 85.08  │ 13.86  │ 1.06   │ 9.87   │ 373.4    │
  │ 长生L1  │ 85.12  │ 13.76  │ 1.12   │ 9.87   │ 456.7    │
  └────────┴────────┴────────┴────────┴────────┴──────────┘
  ⇒ **7 境界全部命中 85 / 14 / 1**（常态均值 84.98、稀有均值 14.00、奇遇均值 1.02）。

  ★ 经济影响（同口径均值对比，N=120000）：
      基线 均值 = 235.7 302.6 384.4 482.3 638.0 860.4 1398.5
      终态 均值 = 147.1 179.9 215.6 257.1 308.3 373.4  456.7
    ⇒ **总灵石收入约 −38%（炼气）~ −67%（长生）**。
      主因：DS 触发率 25%→10%（下限吸收）⇒ 战斗胜场收益被削约 60%。
      这是「把稀有从 32.5% 压到 14%」的**必然代价**（战斗路是稀有最大来源）。

==============================================================================
七、契约（照 localtest/yl_r211_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 探针）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r212-<时刻>`。
  · 幂等：产物已含标记 `/*[r212prob]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r212prob]*/'

# --------------------------------------------------------------------------- 参数

DS_MUL = 0.15    # DS() 战斗触发率乘子（乘子后落进既有下限 Math.max(.1,v) ⇒ 触发率恒 10%）
MID_W = 0.32     # Fm() 主路「中档」（raw 灵石 ≥ 40）权重（实测最优：稀有均值 14.04 / 常态均值 84.94）
W_LR = 0.05      # Fm() 长生专属模板 longevityRule 的降权因子（抹平长生奇遇虚高）


def _num(x):
    """浮点转纯 ASCII JS 字面量（去尾 0），保证注入串可复现。"""
    s = ('%.6f' % float(x)).rstrip('0').rstrip('.')
    return s or '0'


# --------------------------------------------------------------------------- 替换项（纯 ASCII）

# ---- A：DS 战斗触发率乘子（形态零改动，仅尾部追加乘子）----
A_OLD = 'v=Math.min(.7,(l+c+d-u)*f)'
A_NEW = A_OLD + '*' + _num(DS_MUL) + IDEMPOTENT_MARK

# ---- B：主路「中档」权重 0.7 -> 0.3 ----
B_OLD = 'S.spiritStonesChange>=40?x*=0.7'
B_NEW = 'S.spiritStonesChange>=40?x*=' + _num(MID_W)

# ---- C：longevityRule 降权（插在 petObtained 与 hpChange 之间，保 r177 两串连续）----
C_OLD = 'S.petObtained&&(x*=.3+f*1.2),S.hpChange<0&&(x*=0.35)'
C_NEW = ('S.petObtained&&(x*=.3+f*1.2),'
         'S.longevityRuleObtained&&(x*=' + _num(W_LR) + '),'
         'S.hpChange<0&&(x*=0.35)')

REPLACEMENTS = [
    ('A DS \u89e6\u53d1\u7387\u4e58\u5b50', A_OLD, A_NEW),
    ('B \u4e2d\u6863\u6743\u91cd 0.7->0.3', B_OLD, B_NEW),
    ('C longevityRule \u964d\u6743', C_OLD, C_NEW),
]

# 冻结针脚（对**输入**校验，全 ASCII，count 实测）：本环不动的形态/锚点
FREEZE = [
    ('Math.max(.1,v)', 1),                            # DS 下限仍在（乘子后靠它吸收境界项）
    ('fe.indexOf(t.realm)*.02', 1),                   # DS 境界项仍在（形态未消失）
    ('zS={normal:.25', 1),                            # DS 档位系数表仍在
    ('function Fm(', 1),                              # 模板选择器仍在
    ('function Ym(', 1),                              # 结算链仍在
    ('S.petObtained&&(x*=.3+f*1.2)', 1),              # r177 FREEZE：宠物因子
    ('S.hpChange<0&&(x*=0.35)', 1),                   # r177/r180 FREEZE：伤害权重
    ('$>500?x*=.5:', 1),                              # r177/r180 FREEZE：高档权重
    ('x*=1-f*.3', 1),                                 # r188/r180 FREEZE：普通物品因子
    ('M=Math.max(10,Math.round($*b))*10', 1),         # 杠杆 B：_e2e_t11_adv 钉死，绝不动
    # ---- R-211 归一化痕迹：本环**一字不动**（回归底线）----
    ('/*[r211tieru]*/', 1),
    ('/*[r209tier]*/', 1),
    ('if (ds <= 200) S.tierLow += 1;', 1),
    ('__dsRaw', 2),
    ('__ylU', 6),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    return [
        # ---- 幂等标记 ----
        ('R212-mark', IDEMPOTENT_MARK, 1, '==', '[r212prob] exactly once'),
        # ---- A：DS 触发率乘子 ----
        ('R212-ds mul', 'v=Math.min(.7,(l+c+d-u)*f)*' + _num(DS_MUL), 1, '==', 'DS v 乘子'),
        ('R212-ds floor kept', 'Math.max(.1,v)', 1, '==', 'DS 下限逐字保留'),
        ('R212-ds realm term kept', 'fe.indexOf(t.realm)*.02', 1, '==', 'DS 境界项形态未消失'),
        ('R212-ds zS kept', 'zS={normal:.25', 1, '==', '档位系数表未动'),
        # ---- B：中档权重 ----
        ('R212-mid weight', 'S.spiritStonesChange>=40?x*=' + _num(MID_W), 1, '==', '中档权重 0.3'),
        ('R212-mid old 0.7 gone', 'S.spiritStonesChange>=40?x*=0.7', 0, '==', '旧 0.7 已清零'),
        ('R212-high weight kept', '$>500?x*=.5:', 1, '==', 'r177/r180 高档权重未动'),
        ('R212-normal factor kept', 'x*=1-f*.3', 1, '==', 'r188 普通物品因子未动'),
        # ---- C：longevityRule 降权 ----
        ('R212-lr weight', 'S.longevityRuleObtained&&(x*=' + _num(W_LR) + ')', 1, '==', '长生降权'),
        ('R212-pet adjacency kept',
         'S.petObtained&&(x*=.3+f*1.2),S.longevityRuleObtained', 1, '==', 'r177 宠物因子逐字连续'),
        ('R212-hp adjacency kept',
         'S.longevityRuleObtained&&(x*=' + _num(W_LR) + '),S.hpChange<0&&(x*=0.35)', 1, '==',
         'r177 伤害权重逐字连续'),
        ('R212-hp weight kept', 'S.hpChange<0&&(x*=0.35)', 1, '==', 'r177/r180 伤害权重未动'),
        # ---- 杠杆 B 与结算链未动 ----
        ('R212-by M untouched', 'M=Math.max(10,Math.round($*b))*10', 1, '==', '杠杆 B 未动（e2e 钉死）'),
        ('R212-Fm kept', 'function Fm(', 1, '==', '模板选择器仍在'),
        ('R212-Ym kept', 'function Ym(', 1, '==', '结算链仍在'),
        # ---- R-211 归一化：一字不动（回归底线）----
        ('R212-r211 mark kept', '/*[r211tieru]*/', 1, '==', 'R-211 标记未动'),
        ('R212-r209 mark kept', '/*[r209tier]*/', 1, '==', 'R-209 标记未动'),
        ('R212-tier 200 kept', 'if (ds <= 200) S.tierLow += 1;', 1, '==', '分档下界=200 未动'),
        ('R212-dsRaw kept', '__dsRaw', 2, '==', '归一化输入未动'),
        ('R212-ylU kept', '__ylU', 6, '==', '境界系数归一化未动'),
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
    """反向还原：把 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    import shutil
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
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


def _ds_probe(out):
    """抽真实 DS() 箭头函数，验证乘子生效：固定 Math.random=0.2 时**不**触发（乘子后落进 0.1 下限），
    固定 0.05 时触发；且 7 境界的触发概率恒为下限 0.1。"""
    i = out.find('DS=(t,r,a="normal")=>{')
    if i < 0:
        return False, 'DS 定义未找到'
    j = out.find('};function ', i)
    if j < 0:
        return False, 'DS 定义边界未找到'
    src = out[i:j + 1]
    if '*0.15' not in src and ('*' + _num(DS_MUL)) not in src:
        return False, 'DS 乘子未注入'
    if 'Math.max(.1,v)' not in src:
        return False, 'DS 下限被破坏'
    js = (
        'var fe=["\\u70bc\\u6c14\\u671f","\\u7b51\\u57fa\\u671f","\\u91d1\\u4e39\\u671f",'
        '"\\u5143\\u5a74\\u671f","\\u5316\\u795e\\u671f","\\u5408\\u9053\\u671f","\\u957f\\u751f\\u5883"];\n'
        'var zS={normal:.25,lucky:.12,secret_realm:.45,sect_challenge:.3,dao_combining_challenge:.3};\n'
        'function md(a){return {battleChance:1};}\n'
        'function Lm(r){return {battleChance:1};}\n'
        'var ' + src + '\n'
        'function chk(n,c){if(!c)throw new Error(n);}\n'
        'var _r=Math.random;\n'
        'Math.random=function(){return 0.2;};\n'
        'var high=DS({realm:"\\u957f\\u751f\\u5883",speed:300,luck:0},"normal","normal");\n'
        'Math.random=function(){return 0.05;};\n'
        'var low=DS({realm:"\\u70bc\\u6c14\\u671f",speed:0,luck:0},"normal","normal");\n'
        'Math.random=_r;\n'
        'chk("rnd0.2 \\u5e94\\u4e0d\\u89e6\\u53d1\\uff08\\u4e58\\u5b50\\u540e\\u843d\\u8fdb 0.1 \\u4e0b\\u9650\\uff09", high===false);\n'
        'chk("rnd0.05 \\u5e94\\u89e6\\u53d1", low===true);\n'
        'console.log("ds-probe OK: mul=' + _num(DS_MUL) + ' floor=0.1 (rnd0.2 no-trigger, rnd0.05 trigger)");\n'
    )
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:300]
    return True, so.strip()


def _weight_probe(out):
    """抽真实权重块，验证：低档 ×1 / 中档 ×0.3（raw>=40）/ 高档 ×.5 / 伤害 ×.35 /
    长生 longevityRule ×.5×0.05。"""
    i = out.find('v.map(S=>{')
    j = out.find(',{template:S,weight:x}})', i)
    if i < 0 or j < 0:
        return False, '权重块未找到'
    inner = out[i + len('v.map(S=>{'):j]
    inner = inner.replace(';return ', ';', 1)
    js = ('function W(S){var f=.3;' + inner + ';return x;}\n'
          'function chk(n,a,b){if(Math.abs(a-b)>1e-9)throw new Error(n+": "+a+" != "+b);}\n'
          'chk("low0",W({expChange:0,spiritStonesChange:0}),1);\n'
          'chk("low39",W({expChange:0,spiritStonesChange:39}),1);\n'
          'chk("mid40",W({expChange:0,spiritStonesChange:40}),' + _num(MID_W) + ');\n'
          'chk("mid149",W({expChange:0,spiritStonesChange:149}),' + _num(MID_W) + ');\n'
          'chk("high",W({expChange:300,spiritStonesChange:600}),.5);\n'
          'chk("dmg",W({expChange:0,spiritStonesChange:0,hpChange:-40}),0.35);\n'
          'chk("longevityRule",W({expChange:300,spiritStonesChange:600,longevityRuleObtained:true}),'
          '.5*' + _num(W_LR) + ');\n'
          'console.log("weight-probe OK: low=1 mid=' + _num(MID_W) + '(raw>=40) high=.5 dmg=.35 '
          'longevityRule=.5*' + _num(W_LR) + '");\n')
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:300]
    return True, so.strip()


def _norm_probe(out):
    """回归底线：R-211 归一化块逐字在位（`ds <= 200` / `__dsRaw` / `__ylU`）。"""
    m = re.search(r'var __dsRaw = ds;\n\s*\{ let ds = __dsRaw / __ylU; if \(ds <= (\d+)\) '
                  r'S\.tierLow \+= 1;[^\n]*', out)
    if not m:
        return False, '归一化分档块未找到'
    block = m.group(0)
    if m.group(1) != '200':
        return False, '分档下界被改动: %s' % m.group(1)
    for frag in ('var __dsRaw = ds;', 'let ds = __dsRaw / __ylU;', 'ds >= 1000',
                 'S.tierMid += 1;', '/*[r209tier]*/'):
        if frag not in block:
            return False, '结构片段缺失: %s' % frag
    if 'if (!isFinite(__ylU) || __ylU <= 0) __ylU = 1;' not in out[:m.start()]:
        return False, 'ylU 兜底缺失'
    return True, 'normalized tier block intact (ds<=200, __dsRaw/__ylU)'


def selftest(src):
    """内存自证：锚点 -> 补丁 -> 门禁 -> 往返 -> 幂等 -> node --check -> 探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r212prob] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r212prob] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r212prob] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r212prob] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r212prob] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r212prob] SELFTEST FAIL ' + nmsg)
        return 1
    for probe in (_ds_probe, _weight_probe, _norm_probe):
        ok, pmsg = probe(out)
        if ok is False:
            print('[r212prob] SELFTEST FAIL %s: %s' % (probe.__name__, pmsg))
            return 1
        print('[r212prob]   %s -> %s' % (probe.__name__, pmsg))
    print('[r212prob] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r212prob] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r212prob] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r212prob] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r212prob] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r212prob] round-trip mismatch: bytes outside the edit points changed')
        return 1

    if args.check:
        print('[r212prob] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-42s %s' % (label, 'OK'))
        for probe in (_ds_probe, _weight_probe, _norm_probe):
            ok, pmsg = probe(out)
            print('    probe %-41s %s' % (probe.__name__, 'OK' if ok else 'FAIL'))
            print('    >> ' + pmsg)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r212-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r212prob] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-42s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
