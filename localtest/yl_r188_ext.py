# -*- coding: utf-8 -*-
r"""
yl_r188_ext.py — R-188 打坐顿悟（"暴击"）触发率【取证 + 天赋接线 + 数值 v2 修订】

需求原文（台账 R-188，逐字）
--------------------------------------------------------------------------
  「之前让修改降低的是自动历练的几率，是不是做到打坐上面了，我现在挂打坐之前触发
    暴击的几率还是有的，现在挂了很久都还是普通打坐。」

team-lead 交办（三步）
--------------------------------------------------------------------------
  第一步（已完成，本文件保留其取证结论）：
    · 用户怀疑「历练降率被误做到打坐上」⇒ 用代码证据证实/证伪。
    · ★★ 必须实测打坐暴击率（把真实判定从 bundle 抽出，node 跑 10 万次）。
  第二步（已完成，v1 已上线到 0.9.30）：
    · 天赋「一念悟道」(id `instant-dao`) 说明写「打坐修炼时有 15% 几率进入顿悟」，
      但实测该 id 全 bundle 只出现 1 次（仅天赋表定义处），**打坐逻辑从未引用它**。
    · ⇒ 把该天赋接进打坐顿悟判定，照抄既有已接线天赋的范式；v1 = 有天赋 15% / 无天赋 0.4%。
  第三步（本次，v2 数值修订）：
    · 用户拍板：**有天赋几率降到 5%，普通玩家（无天赋）调到 1%**。
    · 即 `0.15 → 0.05`、`0.004 → 0.01`。
    · ★★ 关键：目标产物 `index-v2930-20261007.js`（0.9.30 **已上线版**）**已含 v1**，
      因此本环是「v1 → v2 升级」，不是从原件打补丁。

==============================================================================
零、第一步取证结论（不变）
==============================================================================
  ★★ 用户怀疑【不成立】：没有任何一次改动把「历练降率」做到打坐上。
     打坐顿悟率常量在 0.9.27 → 0.9.29（含 R-177/R-178 落地那版）逐字节未变（`.004`）。
  证据：
   (1) v2927 → v2929 全量 diff 仅 15 处 hunk：R-179 汇总 / 版本号 0.9.27→0.9.29 /
       R-174 签到 / R-175 BOSS榜 / R-176 抽奖。**零打坐改动**。
   (2) 打坐顿悟判定行 v2927/v2929 完全一致：`const j=gd(a),b=Math.random()<.004;let S,x;if(b){`
   (3) R-177/R-178（历练降率）只在历练侧（`[r177adv]`）：
       `}finally{c(!1),d(10)}`→`d(9)`、`$>500?x*=.2+f*1.5:…`→`$>500?x*=.5:$>100?x*=.88:x*=1`。
   (4) 打坐循环 v2923/v2927/v2928/v2929 逐字节一致（`N.current(),_.current(2)`，冷却 2s）。
  打坐顿悟率历史：.01 → .002(R-022) → .015(R-041) → .002(回滚) → .004(R-090，0.9.10 起)；
  最近一次是**上调**（0.2%→0.4%），方向与用户「被降低」的印象相反。
  真实原因：0.4%/次 × ≈20~30 次/分钟 ⇒ 期望约 8~12 分钟才出一次顿悟（正常表现，非 bug）。

==============================================================================
一、天赋接线 + 数值（v1 → v2）
==============================================================================
  ★ 天赋判定 API（bundle 实测）：
     · 玩家天赋存于 `player.talentIds`（字符串数组）。规范化点 @247825：
         `Array.isArray(t.talentIds)&&t.talentIds.length>0?t.talentIds:t.talentId?[t.talentId]:[]`
     · 天赋表 = `Un`（@366952 起的大数组，`instant-dao` 在其中，实测 `'instant-dao' in Un`=True）。
  ★ 照抄的既有范式（**已接线**天赋读法，单天赋布尔判定）：
     · @745383 突破成功率：`(h=t.talentIds)!=null&&h.includes("talent-prodigy")&&(S+=.1)`
     · @745280 突破成功率：`(M=t.talentIds)!=null&&M.includes("talent-firm-heart")&&…&&(S+=.15)`
     ⇒ 范式 = `player.talentIds != null && player.talentIds.includes("<id>")`。
       本环据此写 `a.talentIds!=null&&a.talentIds.includes("instant-dao")`（`a`=player，见下）。
  ★ 判定行所在：`function RS(t)` 的 `handleMeditate`（@742693 `const a=Be.getState().player…`），
     顿悟判定在 @742988。**该判定行全 bundle 仅此 1 处，只被打坐用**（实测 count==1）。
  ★ 随机序列保护（关键，**v1/v2 都不许破**）：
     原式 `b=Math.random()<.004` 恰好 **1 次** `Math.random()`。
     若写成 `Math.random()<.004 || (有天赋 && Math.random()<.15)`，则**有天赋者**在首个判定
     失败时会多消耗 1 次随机 ⇒ 打乱全局随机序列（连带影响后续一切判定）。
     ⇒ 全程改用**单次抽样阈值**：`b = Math.random() < (有天赋 ? TALENT : BASE)`。
     任何玩家都恰好消耗 1 次 `Math.random()` ⇒ 全局随机序列与改前**逐次一致**。
  ★ 数值（用户拍板）：
     · v1：无天赋 0.004（0.4%） / 有天赋 0.15（15%，照抄天赋文案）
     · v2：无天赋 **0.01（1%，普通玩家）** / 有天赋 **0.05（5%）**  ← 本次

==============================================================================
二、改法（1 处就地替换，纯 ASCII 锚点）
==============================================================================
  E1 打坐顿悟判定行（v1 形态 → v2 形态）：
      OLD(v1) = `const j=gd(a),__r188t=a.talentIds!=null&&a.talentIds.includes("instant-dao"),`
                `b=Math.random()<(__r188t?0.15:0.004);/*[r188med]*/let S,x;if(b){`
      NEW(v2) = `const j=gd(a),__r188t=a.talentIds!=null&&a.talentIds.includes("instant-dao"),`
                `b=Math.random()<(__r188t?0.05:0.01);/*[r188med]*//*[r188med2]*/let S,x;if(b){`
  · ★ v1 审计标记 `/*[r188med]*/` **逐字保留**（要求②）；v2 审计标记 `/*[r188med2]*/` 紧邻其后。
    两个块注释相邻是合法 JS；`[r188med]` 与 `[r188med2]` 互不为子串（`]` vs `2`），计数互不污染。
  · ★ 兼容**原件形态**（从未打过 r188 的 bundle）：
      OLD(原件) = `const j=gd(a),b=Math.random()<.004;let S,x;if(b){` → 同一 NEW(v2)。
  · 无天赋玩家：`__r188t=false` ⇒ 阈值 0.01（v2 用户拍板值）。

==============================================================================
三、v1 → v2 升级路径（本次核心）
==============================================================================
  目标产物 v2930 **已含 v1**（`[r188med]` count==1、v1 判定行 count==1）⇒ 直接对 v2930 跑
  旧脚本的 `--check` 会命中幂等分支返回 rc=3。为让 `--check` 能 rc=0，本环：
    · 幂等标记由 `[r188med]` **换新**为 `[r188med2]`（`IDEMPOTENT_MARK`）。
    · 输入锚点 A_OLD 改为 **v1 形态**（保留对 v1 的识别）；同时保留对**原件形态**的识别。
    · 输出统一为 v2 形态（含 `/*[r188med]*/` 与 `/*[r188med2]*/` 双标记）。
  判定逻辑（`_pick`）：
    1) 若 `[r188med2]` 在产物里（或 v2 判定行在位）⇒ 已 v2 ⇒ rc=3（不写盘）。
    2) 否则若 v1 判定行恰 1 处 ⇒ 走 v1→v2（v2930 主路径，`--check` rc=0）。
    3) 否则若原件判定行恰 1 处 ⇒ 走 原件→v2（兼容未打过 r188 的 bundle）。
    4) 否则 ⇒ rc=2（锚点不符，安全失败）。

==============================================================================
四、锚点与冻结针脚（对 build/assets/index-v2930-20261007.js 字符级实测）
==============================================================================
  输入锚点（二选一，恰 1 处）：
      A_V1   count==1  （v2930 走这条）
      A_ORIG count==0  （v2930 已被 v1 覆盖，原件形态不再出现）
  冻结（原件与产物均须精确相等；★ 只钉**与本批补丁无关**的稳定形态）：
      Math.floor(v*(.85+Math.random()*.3))  == 1   （普通打坐修为公式未动）
      const $=30+Math.random()*20;          == 1   （顿悟修为公式未动）
      N.current(),_.current(2)              == 1   （打坐执行 + 冷却 2s）
      _.current(2)}catch(Y){console.error(  == 1   （打坐异常兜底）
      YlxwToast(x,"special","md-exp",4000)  == 1   （顿悟 toast）
      YlxwWudaoEnlighten(c)                 == 1   （顿悟接线）
      YlxwMedTick(S,b);                     == 1   （打坐日志钩子）
      YlxwMedSession(t)                     == 1   （打坐会话钩子）
      function Hw({autoMeditate:t,          == 1   （打坐/历练主循环）
      [r177adv]==1  [r179advlog]==1                    （历练侧邻环标记，本批不动）
      }finally{c(!1),d(9)}==1  }finally{c(!1),d(10)}==0 （R-177 冷却降率在位）
      $>500?x*=.5:==1  $>200?x*=.5+f*1==0  x*=1-f*.3==1 （R-177/R-178 权重）
      Math.random()<.01 == 0                            （远古 1% 形态已不存在）
  ★ 顺序无关性：**不再钉** '[r180adv]'、'$>100?x*=.88'、'Ge(t,200,500,490)/Ge(t,20,70,490)'、
      'hpChange:Ge(t,30,80,470)/hpChange:Ge(t,0,0,470)'、't.hpChange*u*0.25/t.hpChange*u*1)'
      —— 这些字符串会被**并行补丁 R-180** 新增或改写；钉死它们会让「先套 r188 还是先套 r180」
      改变结果（r188 无权断言邻居状态）。
  打后额外断言：Math.random()<.004; ==0；(__r188t?0.15:0.004) ==0；
      b=Math.random()<(__r188t?0.05:0.01) ==1；(?0.05:0.01) ==1；
      Math.random()<(__r188t?0.05:0.01)|| ==0（单次抽样守卫）；
      /*[r188med]*/ ==1（v1 标记保留）；/*[r188med2]*/ ==1；instant-dao ==2。

==============================================================================
五、契约（照 localtest/yl_r179_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 +
    node --check + 天赋探针）/ `--forensics`（只打印取证表）/ `--measure`（只跑三组实测）。
  · 1 处就地替换，纯 ASCII 锚点。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r188-<时刻>`。
  · 幂等：产物已含 v2 标记 `[r188med2]` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 天赋探针：从产物**抽出真实判定表达式**，用 node 抽样 10 万次跑两组：
      ① 无该天赋 → 期望 ≈1.0%   ② 有该天赋 → 期望 ≈5.0%；
      并断言判定表达式全 bundle 仅 1 处（⇒ 打坐以外路径不受影响）。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# ------------------------------------------------------------------ 常量

IDEMPOTENT_MARK = '[r188med2]'      # v2 幂等标记（用于把 v2 与 v1 区分开）
MARK = '/*[r188med2]*/'             # v2 审计标记
MARK_V1 = '/*[r188med]*/'           # v1 审计标记（v2 逐字保留，保留审计链）

TALENT_ID = 'instant-dao'
TALENT_V1 = '0.15'   # v1 有天赋阈值（照抄天赋文案）
BASE_V1 = '0.004'    # v1 无天赋阈值
TALENT = '0.05'      # v2 有天赋阈值（用户拍板：5%）
BASE = '0.01'        # v2 无天赋阈值（用户拍板：普通玩家 1%）

# ---- 退役针脚标记（0.9.36 起）----
# 语义：本环（R-188 v2）**排在 R-199 之前**套用 ⇒ apply 时自动历练冷却 `}finally{c(!1),d(9)}`
#   仍在（count==1，precheck 通过）；而 R-199（0.9.35）已把它合法改写为 `d(7)` ⇒ 终态该形态为 0。
# 单条 (needle, expect) 无法同时满足 apply 态(1) 与终态(0)，故退役 = **终态专用**：
#   · dryrun 读 gates() 在终态复核（期望 0，如实反映 R-199 改写后的形态）；
#   · 本环 apply/--check 时跳过（不检、不计 FAIL），避免「老补丁依赖新补丁」——终态形态由
#     R-199 自己的门禁负责；「冷却块在位」由值无关针脚 `}finally{c(!1),d(` 负责（d(9)/d(7) 皆成立）。
RETIRED_TAG = '【已退役·终态专用】'

# 打坐顿悟判定行：原件形态（从未打过 r188）
A_ORIG = 'const j=gd(a),b=Math.random()<.004;let S,x;if(b){'
# 打坐顿悟判定行：v1 形态（0.15/0.004 + [r188med]，0.9.30 已上线）
A_V1 = ('const j=gd(a),__r188t=a.talentIds!=null&&a.talentIds.includes("%s"),'
        'b=Math.random()<(__r188t?%s:%s);%slet S,x;if(b){'
        % (TALENT_ID, TALENT_V1, BASE_V1, MARK_V1))
# 打坐顿悟判定行：v2 形态（0.05/0.01 + 双标记；单次抽样）
A_V2 = ('const j=gd(a),__r188t=a.talentIds!=null&&a.talentIds.includes("%s"),'
        'b=Math.random()<(__r188t?%s:%s);%s%slet S,x;if(b){'
        % (TALENT_ID, TALENT, BASE, MARK_V1, MARK))

# 输入形态（升级链）：v1 优先（0.9.30 产物已含 v1），其次原件
FORMS = [
    ('R188v2-E1 打坐顿悟判定行·v1(0.15/0.004) → v2(0.05/0.01)', A_V1, A_V2),
    ('R188v2-E1 打坐顿悟判定行·原件(0.004) → v2(0.05/0.01)', A_ORIG, A_V2),
]

# 冻结针脚：本环只动 E1，下列既有形态必须逐字在位（原件与产物均须相等）
# ★ 顺序无关性：只钉**与本批其它补丁无关**的稳定形态。凡会被**并行补丁 R-180**
#   新增或改写的字符串（[r180adv]、$>100?x*=.88、Ge(t,200,500,490)/Ge(t,20,70,490)、
#   hpChange:Ge(t,30,80,470)/hpChange:Ge(t,0,0,470)、t.hpChange*u*0.25/t.hpChange*u*1)）
#   一律**不钉** —— r188 没有资格断言邻居状态，否则「先套 r188 还是先套 r180」会改变结果。
FREEZE = [
    ('Math.floor(v*(.85+Math.random()*.3))', 1),         # 普通打坐修为公式未动
    ('const $=30+Math.random()*20;', 1),                 # 顿悟修为公式未动
    ('N.current(),_.current(2)', 1),                     # 打坐执行 + 冷却 2s
    ('_.current(2)}catch(Y){console.error(', 1),         # 打坐异常兜底
    ('YlxwToast(x,"special","md-exp",4000)', 1),         # 顿悟 toast
    ('YlxwWudaoEnlighten(c)', 1),                        # 顿悟接线
    ('YlxwMedTick(S,b);', 1),                            # 打坐日志钩子
    ('YlxwMedSession(t)', 1),                            # 打坐会话钩子
    ('function Hw({autoMeditate:t,', 1),                 # 打坐/历练主循环
    # ---- 历练侧：证明「降率」留在历练侧、未被搬到打坐（只钉本批不动的稳定形态）----
    ('[r177adv]', 1), ('[r179advlog]', 1),
    # 冷却块用「值无关」前缀：R-188 只保证没碰这个块；冷却值本身由 R-177(9s)/R-199(7s) 负责。
    # （原 `('}finally{c(!1),d(9)}', 1)` 已改立**终态专用**退役门禁，见 gates()）
    ('}finally{c(!1),d(', 1), ('}finally{c(!1),d(10)}', 0),
    ('$>500?x*=.5:', 1),
    ('$>200?x*=.5+f*1', 0), ('x*=1-f*.3', 1),
    # ---- 远古 1% 形态（Math.random()<.01 写法）已不存在 ----
    ('Math.random()<.01', 0),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        # ---- v1 → v2 升级路径 ----
        ('R188v2·幂等标记唯一', MARK, 1, '==', '[r188med2] 恰好 1 处'),
        ('R188v2·v1 标记逐字保留', MARK_V1, 1, '==', '[r188med] 保留（审计链，要求②）'),
        ('R188v2·v2 判定行已注入', A_V2, 1, '==', 'v2 判定行恰好 1 处'),
        ('R188v2·v1 判定行已升级消失', A_V1, 0, '==', 'v1 形态已被替换'),
        ('R188v2·原件判定行已消失', A_ORIG, 0, '==', '原件形态已不存在'),
        ('R188v2·旧 0.004 判定行已清零', 'Math.random()<.004;', 0, '==', '旧写法已不存在'),
        ('R188v2·v1 阈值形态已清零', '(__r188t?0.15:0.004)', 0, '==', 'v1 数值已不存在'),
        # ★ 用户拍板：有天赋分支 = 0.05（5%）
        ('R188v2·★有天赋分支=0.05（用户拍板）', 'b=Math.random()<(__r188t?0.05:0.01)', 1, '==',
         'true 分支恰为 5%'),
        # ★ 用户拍板：无天赋分支 = 0.01（普通玩家 1%）
        ('R188v2·★无天赋分支=0.01（用户拍板）', '(__r188t?0.05:0.01)', 1, '==',
         'false 分支恰为 1%'),
        # ★ 守卫：仍是单次抽样（不得回退成 `||` 两次抽样）
        ('R188v2·★单次抽样（未回退 ||）', 'Math.random()<(__r188t?0.05:0.01)||', 0, '==',
         '仍只调 1 次 Math.random()'),
        ('R188v2·天赋判定用既有范式', 'a.talentIds!=null&&a.talentIds.includes("instant-dao")', 1, '==',
         '照抄 talent-prodigy/talent-firm-heart 范式'),
        ('R188v2·instant-dao 出现 2 处', 'instant-dao', 2, '==', '天赋表定义 + 本环判定'),
        # ---- 终态退役：R-199 已合法改写自动历练冷却 ----
        ('冻结 }finally{c(!1),d(9)}' + RETIRED_TAG, '}finally{c(!1),d(9)}', 0, '==',
         'R-199/0.9.35 已把自动历练冷却 d(9) → d(7) ⇒ 终态归 0（新形态由 R199 自己的门禁负责；'
         '「冷却块在位」由值无关针脚 `}finally{c(!1),d(` 覆盖）'),
    ]
    for needle, cnt in FREEZE:
        g.append(('冻结 ' + needle[:30], needle, cnt, '==', '冻结既有形态'))
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


def _pick(s):
    """判定输入形态。返回 (name, old, new)；
       已是 v2 → ('__idem__', None, None)；无匹配 → None。"""
    if IDEMPOTENT_MARK in s or A_V2 in s:
        return ('__idem__', None, None)
    for name, old, new in FORMS:
        if s.count(old) == 1:
            return (name, old, new)
    return None


def _precheck(s):
    """返回 None=可打；否则返回错误串。对**原件** s 校验锚点与冻结针脚。"""
    p = _pick(s)
    if p is None:
        return ('锚点不符：既非 v1 形态（%r）也非原件形态（%r）（期望其中恰有 1 处）'
                % (A_V1[:48], A_ORIG[:48]))
    if p[0] == '__idem__':
        return None  # 幂等，交由 main 判 rc=3
    for needle, cnt in FREEZE:
        if s.count(needle) != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, s.count(needle), cnt)
    return None


def apply_patch(src):
    """返回 (out, err, picked)；err 非 None 时为错误串，out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err, None
    p = _pick(s)
    if p is None or p[0] == '__idem__':
        return s, None, p
    _, old, new = p
    return s.replace(old, new, 1), None, p


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        if RETIRED_TAG in label:
            # 退役针脚（终态专用）：本环 apply 时 R-199 尚未套用，自产 d(9) 形态仍在 ⇒ 不检；
            # 终态由复核（期望 0）负责，新形态由 R-199 自己的门禁负责。
            continue
        c = out.count(needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0, picked):
    """把 out 逆向回滚为输入形态，应与 s0 逐字节相等。"""
    if picked is None or picked[0] == '__idem__':
        return out == s0
    _, old, new = picked
    return out.replace(new, old, 1) == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node')]
    # 兜底：扫描内置 node 版本目录（不写死具体版本号，避免路径过期）
    cand += sorted(glob.glob('C:/Users/27026/.workbuddy-ai/binaries/node/versions/*/node.exe'),
                   reverse=True)
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


def _extract_judgment(text):
    """从产物抽出**真实**判定表达式（__r188t=…,b=Math.random()<(…);）。"""
    m = re.search(
        r'__r188t=a\.talentIds!=null&&a\.talentIds\.includes\("%s"\),'
        r'b=Math\.random\(\)<\(__r188t\?[0-9.]+:[0-9.]+\);' % re.escape(TALENT_ID), text)
    return m.group(0) if m else None


def _talent_probe(text, samples=100000):
    """抽出真实判定表达式，node 抽样三组：① 无天赋 ② 有天赋；并断言判定行唯一。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。
    """
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    expr = _extract_judgment(text)
    if expr is None:
        return False, '判定表达式未找到（可能未打补丁）'
    # 判定行唯一性 ⇒ 打坐以外路径不受影响
    cnt = text.count(expr)
    js = (
        'var __r188t, b;\n'
        'function roll(a){ ' + expr + ' return b; }\n'
        'var N=' + str(samples) + ', h0=0, h1=0;\n'
        'for (var i=0;i<N;i++){ if (roll({talentIds:null})) h0++; }\n'
        'for (var i=0;i<N;i++){ if (roll({talentIds:["' + TALENT_ID + '"]})) h1++; }\n'
        'var r0=h0/N*100, r1=h1/N*100;\n'
        'console.log("R188-TALENT 无天赋 rate=" + r0.toFixed(4) + "% (期望 1.0000%)");\n'
        'console.log("R188-TALENT 有天赋 rate=" + r1.toFixed(4) + "% (期望 5.0000%)");\n'
        'if (r0 < 0.85 || r0 > 1.15) { console.error("FAIL 无天赋应≈1.0%"); process.exit(1); }\n'
        'if (r1 < 4.60 || r1 > 5.40) { console.error("FAIL 有天赋应≈5.0%"); process.exit(1); }\n'
    )
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:400]
        msg = r.stdout.decode('utf-8', 'replace').strip()
        msg += '\n判定表达式全 bundle 出现 %d 次（==1 ⇒ 仅打坐使用，其它路径不受影响）' % cnt
        if cnt != 1:
            return False, '判定表达式出现 %d 次（期望 1）' % cnt
        return True, msg
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _forensics(src):
    """打印取证表（各锚点/针脚计数 + 天赋接线信息）。"""
    s = _read(src)
    print('[r188] === R-188 取证表（%s）===' % os.path.basename(src))
    print('[r188] 判定行 count：原件(0.004)=%d  v1(0.15/0.004)=%d  v2(0.05/0.01)=%d'
          % (s.count(A_ORIG), s.count(A_V1), s.count(A_V2)))
    print('[r188] 审计标记：/*[r188med]*/=%d  /*[r188med2]*/=%d'
          % (s.count(MARK_V1), s.count(MARK)))
    print('[r188] 天赋 id "%s" 出现 %d 次（原件应为 1=仅天赋表定义；v1/v2 应为 2）'
          % (TALENT_ID, s.count(TALENT_ID)))
    for needle, cnt in FREEZE:
        c = s.count(needle)
        flag = 'OK ' if c == cnt else '!! '
        print('[r188]   %s %-42s count=%d（期望 %d）' % (flag, needle[:42], c, cnt))
    print('[r188] 结论：打坐链无「降率」痕迹；R-177/R-178 降率在历练侧（[r177adv] 在位）；'
          '「一念悟道」已接线，v2 数值 = 无天赋 1% / 有天赋 5%。')


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 天赋探针。"""
    s0 = _read(src)
    p = _pick(s0)
    if p is None:
        print('[r188] SELFTEST FAIL precheck: 锚点不符（既非 v1 也非原件形态）')
        return 1
    if p[0] == '__idem__':
        print('[r188] SELFTEST SKIP: src already patched (v2)')
        return 0
    out, err, picked = apply_patch(src)
    if err is not None:
        print('[r188] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r188] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0, picked):
        print('[r188] SELFTEST FAIL round-trip mismatch')
        return 1
    if IDEMPOTENT_MARK not in out:
        print('[r188] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r188] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _talent_probe(out)
    if ok is False:
        print('[r188] SELFTEST FAIL talent-probe: ' + pmsg)
        return 1
    print('[r188] SELFTEST OK: gates=%d path=%s roundtrip=True delta=%+d chars; %s'
          % (len(gates()), picked[0], len(out) - len(s0), nmsg))
    if pmsg:
        for ln in pmsg.splitlines():
            print('[r188]   ' + ln)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--forensics', action='store_true', help='只打印取证表')
    ap.add_argument('--measure', action='store_true', help='只跑天赋三组实测')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r188] src not found: %s' % src)
        return 2

    if args.forensics:
        _forensics(src)
        return 0
    if args.measure:
        # 兼容原件/v1/v2：非 v2 则内存打补丁后再实测（不落盘）
        s = _read(src)
        p = _pick(s)
        if p is not None and p[0] == '__idem__':
            out = s
        else:
            out, err, _ = apply_patch(src)
            if err is not None:
                print('[r188] ABORT: ' + err)
                return 2
        ok, msg = _talent_probe(out)
        print('[r188] ' + (msg if msg else 'no node'))
        return 0 if ok in (True, None) else 1
    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    p = _pick(s0)
    if p is None:
        print('[r188] ABORT: 锚点不符：既非 v1 形态也非原件形态（期望恰 1 处）')
        return 2
    if p[0] == '__idem__':
        print('[r188] already patched v2 (idempotent skip)')
        return 3

    out, err, picked = apply_patch(src)
    if err is not None:
        print('[r188] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r188] ' + e)
        return 1
    if not _roundtrip_ok(out, s0, picked):
        print('[r188] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        tag = 'v1->v2' if picked[1] == A_V1 else 'orig->v2'
        print('[r188] check OK [%s] (%d -> %d chars, %+d)'
              % (tag, len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            if RETIRED_TAG in label:
                print('    [SKIP] %s 已退役（终态由 R-199 门禁复核）' % label.replace(RETIRED_TAG, ''))
            else:
                print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r188-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r188] patched (v1 -> v2): %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        if RETIRED_TAG in label:
            print('    [SKIP] %s 已退役（终态由 R-199 门禁复核）' % label.replace(RETIRED_TAG, ''))
        else:
            print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
