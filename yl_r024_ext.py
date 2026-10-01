# -*- coding: utf-8 -*-
r"""
yl_r024_ext.py — R-024 打坐灵石：把「大境界序号」纳入每跳因子（修正「跨大境界回落」）

背景（2026-09-30 审计 + team-lead 指派）
--------------------------------------------------------------------------
  econ2 落的 R-024 公式只吃 `realmLevel`（境界内 1~9 层）：

      function YlxwMedStone2(q, realmLevel) {
        var lv = Math.max(1, Math.floor(Number(realmLevel) || 1));
        return Math.floor(Math.max(1, Number(q) || 1) * 4.25 * (1 + (lv - 1) * 0.03));
      }

  而 `realmLevel` 突破时 `st>=9 → st=1`（跨大境界归 1）⇒ **因子本身每跨一个大境界就回落到底**，
  与用户口径「小境界变化不大、跨大境界时变化略微增大」在**因子这一层**方向相反。

  ★ 实测补充（本模块复算，见 报告_w2_r024.md）：大境界的总量增长**由 q 承载**
    （`q = max(1, fe.indexOf(realm)*2+1) + rand(-1..1)`，E[q] = 4/3,3,5,7,9,11,13），
    故「灵石/h 总量」当前**确实**随大境界上升（炼气 L1 10107 → 长生 L1 98547）。
    但把「跨大境界」与「层内」两个跳幅并排看：
        层内 L1→L9   = ×1.240（恒定）
        跨大境界 L1→L1 = ×2.250 / 1.667 / 1.400 / 1.286 / **1.222 / 1.182**
    最高两段（化神→合道、合道→长生）**已经跌破层内 1.24** ⇒ 「跨大境界变化 > 小境界变化」
    在高段不成立。本模块即修这一条。

本模块动作（就地改 econ2 落的形态，锚点 = econ2 之后的文本）
--------------------------------------------------------------------------
  1) `YlxwMedStone2` 升为三参 `(q, realmLevel, realmIndex)`，因子改为
         `1 + realmIndex * K + (realmLevel - 1) * 0.03`
  2) 调用点补传 `realmIndex = C`（调用点上一句 `const C=fe.indexOf($.realm)` 已有该值）
  3) 新增常量 `var YLXW_R024_K = 0.083;`

K 的选择（理由见 报告_w2_r024.md §3）
--------------------------------------------------------------------------
  · 硬约束：炼气 1 层（realmIndex=0, lv=1）必须 = ×1.00 ⇒ 因子不得有常数项。
  · 用户要「略微增大」⇒ 取最小 K 使**最高一段**跨大境界跳幅 ≥ 层内跳幅：
        (13/11) · (1+6K)/(1+5K) ≥ 1.240  ⇒  K ≥ 0.0653
  · 取 K = 0.083（= 6K ≈ 0.50）⇒ 长生因子 = 1.498 ≈ 1.5×，同时满足两条。
  · 效果：跨大境界 L1→L1 跳幅 = 2.437 / 1.794 / 1.500 / 1.371 / 1.299 / 1.251，**全部 > 1.240**。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 注入块中文走 zh()，注入后纯 ASCII；不含 V28_BAN_PATTERNS；块内无 fetch。
  · 每个 replace 带 expect 精确次数。
  · 只新建本文件；不改 build_v26n.py / localtest/chain_build.py / srv/index_v28.ts。
  · 必须排在 `yl_econ2_ext.py` 之后（锚点是 econ2 的产物形态）。
"""

import re

# --------------------------------------------------------------------------- 注入文本

# 说明注释（中文 → 由 zh() 转义）
NOTE = (
    '/* R-024v2\uff08yl_r024_ext\uff09\uff1a\u6bcf\u8df3\u7075\u77f3\u56e0\u5b50'
    '\u52a0\u5165\u5927\u5883\u754c\u5e8f\u53f7 realmIndex\uff0c\u4fee\u6b63'
    '\u300c\u8de8\u5927\u5883\u754c\u56de\u843d\u300d\u3002'
    '\u56e0\u5b50 = 1 + realmIndex*K + (\u5883\u754c\u5c42-1)*0.03\uff0cK=0.083\uff1b'
    '\u70bc\u6c14 L1\uff08realmIndex=0, lv=1\uff09\u4ecd = \u00d71.00\u3002 */\n'
)

# 纯 ASCII：新常量 + 三参函数
INJECT_JS = (
    'var YLXW_R024_K = 0.083;\n'
    'function YlxwMedStone2(q, realmLevel, realmIndex) {\n'
    '  var lv = Math.max(1, Math.floor(Number(realmLevel) || 1));\n'
    '  var ri = Math.max(0, Math.floor(Number(realmIndex) || 0));\n'
    '  return Math.floor(Math.max(1, Number(q) || 1) * 4.25 * (1 + ri * YLXW_R024_K + (lv - 1) * 0.03));\n'
    '}'
)

# --------------------------------------------------------------------------- 锚点常量

# econ2 落的函数原文（锚点 = econ2 之后形态，count 必须 ==1）
FN_OLD = (
    'function YlxwMedStone2(q, realmLevel) {\n'
    '  var lv = Math.max(1, Math.floor(Number(realmLevel) || 1));\n'
    '  return Math.floor(Math.max(1, Number(q) || 1) * 4.25 * (1 + (lv - 1) * 0.03));\n'
    '}'
)

# econ2 落的调用点（入账 + medlog 日志一次改完）
CALL_OLD = ('__ylsq=YlxwMedStone2(q,$.realmLevel),'
            'w=$.spiritStones+__ylsq,'
            '__ylms=YlxwMedStone(__ylsq),')
CALL_NEW = ('__ylsq=YlxwMedStone2(q,$.realmLevel,C),'
            'w=$.spiritStones+__ylsq,'
            '__ylms=YlxwMedStone(__ylsq),')

# realmIndex 来源（调用点上一句已算好 C；本模块只引用，不改这一句）
REALM_IDX_SRC = 'const C=fe.indexOf($.realm),q=Math.max(1,C*2+1)'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含 econ2 及其全部前置模块）；ctx = {'zh': zh, ...}"""
    zh = ctx['zh']

    new_fn = zh(NOTE) + INJECT_JS
    bad = re.findall(r'[^\x00-\x7f]', new_fn)
    if bad:
        raise AssertionError('r024 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 1) 函数：二参 → 三参 + 大境界因子
    p.replace('r024-fn', FN_OLD, new_fn, expect=1,
              note='YlxwMedStone2 三参 + realmIndex*K 因子')

    # 2) 调用点：补传 realmIndex=C
    p.replace('r024-call', CALL_OLD, CALL_NEW, expect=1,
              note='调用点传 realmIndex=C')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本模块改动 =================
        ('R24v2·函数升三参',        'function YlxwMedStone2(q, realmLevel, realmIndex) {', 1, '==', ''),
        ('R24v2·大境界因子已入公式', 'ri * YLXW_R024_K + (lv - 1) * 0.03', 1, '==', ''),
        ('R24v2·K 常量 = 0.083',    'var YLXW_R024_K = 0.083;', 1, '==', ''),
        ('R24v2·旧二参签名已清零',   'function YlxwMedStone2(q, realmLevel) {', 0, '==', 'econ2 旧形态'),
        ('R24v2·旧公式已清零',       'Math.max(1, Number(q) || 1) * 4.25 * (1 + (lv - 1) * 0.03)', 0, '==', 'econ2 旧形态'),
        ('R24v2·调用点已传 realmIndex', '__ylsq=YlxwMedStone2(q,$.realmLevel,C),', 1, '==', ''),
        ('R24v2·旧调用点已清零',     '__ylsq=YlxwMedStone2(q,$.realmLevel),', 0, '==', 'econ2 旧形态'),
        ('R24v2·realmIndex 取自 fe.indexOf', REALM_IDX_SRC, 1, '==', 'C 已在调用点前算好'),
        ('R24v2·函数定义仍唯一',     'function YlxwMedStone2(', 1, '==', ''),
        ('R24v2·炼气1层锚点（ri=0 直乘）', '* (1 + ri * YLXW_R024_K + (lv - 1) * 0.03)', 1, '==', 'ri=0,lv=1 ⇒ ×1.00'),
        # ================= 冻结：R-024 三处同源 / R-022 打坐面不动 =================
        ('冻结·入账与日志同源',      'w=$.spiritStones+__ylsq,__ylms=YlxwMedStone(__ylsq),', 1, '==', ''),
        ('冻结·旧 ×5 已清零',        'Math.max(1,q)*5', 0, '==', ''),
        ('冻结·toast 走 __ylsq',     'YlxwToast(`\U0001f4b0 \u6253\u5750\u65f6\u83b7\u5f97\u4e86 ${__ylsq} \u7075\u77f3`,"gain","md-stone",2400)', 1, '==', ''),
        ('冻结·打坐修为基座未动',     'Math.floor(f*10*(1+a.realmLevel*.15))', 1, '==', 'R-022 每跳修为不变'),
        ('冻结·打坐修为每跳未动',     'S=Math.floor(v*(.85+Math.random()*.3))', 1, '==', ''),
        ('冻结·打坐间隔仍 2s（自动）', '_.current(2)', 1, '==', 'R-022 不动'),
        ('冻结·顿悟仍 0.2%',         'Math.random()<.002', 1, '==', 'R-022 不动（R-041 已回滚，本行同步改回 1）'),
    ]
    return gates
