# -*- coding: utf-8 -*-
r"""
yl_r225_ext.py — R-228 修炼效率「明细行」权重与 bd() 同源化（纯客户端）

输入产物：build/assets/index-v2949-20261009.js
          （线上 0.9.49，md5 d8fac7c23951a88c739579726823fb2c，2,326,139 B）
bundle 内中文**混合两种形态**：多数区段为 `\uXXXX` 转义，少数区段（人物志面板等）为
**字面中文**。本环两处锚点形态逐处按实测选取：
  · E1（bd() 聚合尾部，转义区段）：纯 ASCII 锚点（源内写成 `\uXXXX` 字面量或不含中文）；
  · E2（人物志面板明细行，字面区段）：字面态锚点（含非 ASCII 中文，Python 源内用 \uXXXX 转义书写）。
两处锚点均从 bundle 原始文本逐字复制，实测 E1/E2 各唯一（count==1），并在 _precheck 断言形态。

==============================================================================
【问题】R-222 显示口径登记表挖出的「今天第 3 次事故」的根因
==============================================================================
「修炼效率加成」两处显示：
  · @837339  人物面板「修为 (Exp)」条下：主值 `(c.total*YlxwDiffMul(void 0,"expMul")*100)`（r222 已加难度后缀）
  · @1739385 人物志面板：主值 `(T.total*YlxwDiffMul(void 0,"expMul")*100)`（r222 已加难度）
                 + 「明细行」：心法/天赋/称号/洞府/协同/羁绊
两处 `total` = bd()（@617858 聚合，见下）再 × `YlxwDiffMul(void 0,"expMul")`。

★★ 但 **@1739509 的「明细行」把权重 0.26 / 0.6 / 0.6 / 0.1 / 0.32 硬编码在渲染串里**，
与 bd() 聚合表达式**各写一份** ⇒ 改 bd() 必须同步改这里，否则玩家看到的明细与合计对不上。
（今天效率面板显示 22% 的那次事故，根因就是这个「同一个值两处各写一份」。）

==============================================================================
【取证一】bd() 聚合逻辑（bundle @617858，实测源码逐字）
==============================================================================
    function bd(t){
      let r=0,a=0,l=0,c=0,d=1;
      const u=gd(t);
      if(u&&u.effects.expRate){
        const $={天:2,地:1.5,玄:1.2,黄:1}[u.grade]||1;
        r=Math.min(1.25,u.effects.expRate*$);                 // 心法/功法：取值 gd()，封顶 1.25
        const M=t.spiritualRoots||{metal:0,wood:0,water:0,fire:0,earth:0};
        d=go(u,M)                                             // 灵根加成：go()
      }
      const f=t.talentIds||[];
      for(const T of f){                                      // 天赋：Un.find(id).effects.expRate × K
        const $=Un.find(M=>M.id===T);
        $&&$.effects.expRate&&(a+=$.effects.expRate*YLXW_T097_TALENT_K)
      }
      const v=$a(t.titleId,t.unlockedTitles||[]);             // 称号：$a() → expRate
      v.expRate>0&&(l=v.expRate),
      t.grotto&&(c=(t.grotto.expRateBonus||0)+(t.grotto.spiritArrayEnhancement||0));  // 洞府：两项相加
      const m=Pm(t.cultivationArts);
      let b=fy(m).expRate||0, S=0;                            // 协同：fy(Pm(功法))
      try{S+=(typeof YlxwCharDexRate==="function"?YlxwCharDexRate(t):0);}catch(ylCde){}  // 羁绊底：人物志
      if(t.socialRelations)for(const T of t.socialRelations)  // 羁绊：社交关系加成
        T.favorability>=80?S+=.1:T.favorability>=50&&(S+=.05);
      return{total:r*d+a*0.26+l*0.6+c*0.6+Math.min(b,0.1)+S*0.32,
             art:r,talent:a,title:l,grotto:c,synergy:b,npc:S,spiritualRootBonus:d}
    }

各权重来源（合计式 `r*d + a*0.26 + l*0.6 + c*0.6 + min(b,0.1) + S*0.32`）：
  ┌────────┬──────────┬────────┬───────────────────────────────────────────┐
  │ 明细项 │ 字段(返回)│ 权重K  │ 取自                                       │
  ├────────┼──────────┼────────┼───────────────────────────────────────────┤
  │ 心法   │ art=r    │ ×d     │ gd()×grade表，封顶1.25，再×灵根加成 d=go() │
  │ 天赋   │ talent=a │ 0.26   │ Σ Un.find(id).effects.expRate×K           │
  │ 称号   │ title=l  │ 0.60   │ $a(titleId,unlockedTitles).expRate        │
  │ 洞府   │ grotto=c │ 0.60   │ grotto.expRateBonus+spiritArrayEnhancement│
  │ 协同   │ synergy=b│ 0.10(帽)│ fy(Pm(cultivationArts)).expRate（min帽）  │
  │ 羁绊   │ npc=S    │ 0.32   │ YlxwCharDexRate()+社交关系加成             │
  └────────┴──────────┴────────┴───────────────────────────────────────────┘
（bundle @617363 注释自证：`total = r*d + a*0.26 + l*0.60 + c*0.60 + min(b,0.10) + S*0.32`；
  且注释称「与 bd() 内联的 K 表同源」。）

==============================================================================
【取证二】明细行（bundle @1739509，实测源码逐字）
==============================================================================
    T.art>0&&`心法:+${(T.art*T.spiritualRootBonus*100).toFixed(1)}% `,
    T.talent>0&&`天赋:+${(T.talent*0.26*100).toFixed(1)}% `,
    T.title>0&&`称号:+${(T.title*0.6*100).toFixed(1)}% `,
    T.grotto>0&&`洞府:+${(T.grotto*0.6*100).toFixed(1)}% `,
    T.synergy>0&&`协同:+${(Math.min(T.synergy,0.1)*100).toFixed(1)}% `,
    T.npc>0&&`羁绊:+${(T.npc*0.32*100).toFixed(1)}%`
（其后紧跟 r222 追加的 `难度:×N（名）` 段，本环不碰。）

【逐项对照（改前）】—— 6 项一一对应，**数值当前尚未漂移**，但两处各写一份：
  ┌────────┬──────────────────────────────┬───────────────────────────────────┬──────┐
  │ 明细项 │ bd() 合计项                  │ 明细行渲染项                      │ 一致 │
  ├────────┼──────────────────────────────┼───────────────────────────────────┼──────┤
  │ 心法   │ r*d                          │ T.art*T.spiritualRootBonus        │  ✓   │
  │ 天赋   │ a*0.26                       │ T.talent*0.26                     │  ✓   │
  │ 称号   │ l*0.6                        │ T.title*0.6                       │  ✓   │
  │ 洞府   │ c*0.6                        │ T.grotto*0.6                      │  ✓   │
  │ 协同   │ Math.min(b,0.1)              │ Math.min(T.synergy,0.1)           │  ✓   │
  │ 羁绊   │ S*0.32                       │ T.npc*0.32                        │  ✓   │
  └────────┴──────────────────────────────┴───────────────────────────────────┴──────┘
  ⇒ 结论：**改前数值一致、尚未漂移**；但 5 个权重（0.26/0.6/0.6/0.1/0.32）与心法的
     `spiritualRootBonus` 乘法在**两处各写一份** —— 这正是「同一个值两处各写一份」的结构性
     隐患（改 bd() 而忘改明细行 ⇒ 明细与合计对不上）。本环做**同源化**，不改任何数值。

==============================================================================
【改法（治本）】首选方案：bd() 内部单点计算各项明细并随返回值输出，明细行直接渲染
==============================================================================
  · E1（bd()）：把 6 项「已加权贡献」在 bd() 内部**各计算一次**（具名局部量），合计式改为
    **这些局部量之和**（求和顺序与改前逐项一致 ⇒ 浮点结果逐位相同），并把它们**额外返回**：
        const _ar=r*d,_ta=a*0.26,_ti=l*0.6,_gr=c*0.6,_sy=Math.min(b,0.1),_np=S*0.32;
        return{total:_ar+_ta+_ti+_gr+_sy+_np, art:r,...,spiritualRootBonus:d,
               dArt:_ar,dTalent:_ta,dTitle:_ti,dGrotto:_gr,dSynergy:_sy,dNpc:_np}
  · E2（明细行）：6 项改为**直接渲染 bd() 的返回值**（`T.dArt / T.dTalent / … / T.dNpc`），
    明细行**不再自写任何权重**（旧 `*0.26 / *0.6 / *0.1 / *0.32 / *T.spiritualRootBonus` 全部清零）。
  ⇒ 权重与心法乘法在**全 bundle 唯一一处**（bd() 内的具名局部量）定义；合计与明细取自
    **同一批已计算值**（不是各自再算一遍），从结构上杜绝「明细与合计对不上」。
  ★ 为何不用「次选·具名常量」：本方案让明细行消费的是 bd() **实际参与求和的同一个变量**，
    同源程度最高、且不新增任何全局量（零作用域/求值顺序风险）。

==============================================================================
【数值零变化】证据
==============================================================================
  · 求和顺序逐项一致：改前 `r*d + a*0.26 + l*0.6 + c*0.6 + min(b,0.1) + S*0.32`，
    改后 `_ar + _ta + _ti + _gr + _sy + _np`，其中 `_ar=r*d,_ta=a*0.26,_ti=l*0.6,
    _gr=c*0.6,_sy=min(b,0.1),_np=S*0.32` —— 同序同项，IEEE754 逐位相同。
  · 明细行改前 `T.talent*0.26`（T.talent 即 bd 返回的 a），改后 `T.dTalent`（= a*0.26）
    —— 同一浮点运算，结果逐位相同；心法 `T.art*T.spiritualRootBonus` 与 `dArt=r*d` 同理。
  · 模块内 `_numeric_ab()`：从**改前/改后 bundle 各抽取 bd() 源码**，Node 隔离跑一组假 player，
    逐项断言 `改前合计 == 改后合计`、`改前明细 == 改后明细`、且 `Σ明细 == 合计`；不一致即拒写盘。

==============================================================================
【不变量冻结】r222 的难度后缀/标记、r218/r223 标记逐字未动（见 FREEZE）
==============================================================================

==============================================================================
契约（standalone，同 localtest/yl_r216_ext.py / yl_r222_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`（缺省自动探测 PATH 上的 node）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r225-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（含门禁未全绿、往返不一致、node --check 失败、数值 A/B 不一致）。
  · EDITS 四元组 (label, old, new, n)；n=该处旧串期望命中数=替换次数。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证 +
    `node --check` + `_numeric_ab()` 数值同源自证。
  · 纯客户端；不改 build_v26n.py / chain_build.py / dryrun_087.py / sim_remote_check.py /
    任何 build/assets/* / 其它 yl_*_ext.py；不动 r216/r218/r219/r220/r221/r222/r223 已改文案与逻辑。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*YLXW_R225_V2949*/'

# --------------------------------------------------------------------------- E1 · bd() 聚合
# 转义区段、纯 ASCII 锚点。改后：6 项贡献单点计算（具名局部量）→ 合计=各局部量之和
# （同序同项）+ 随返回值额外输出各项明细（dArt…dNpc）；幂等标记落在局部量之前。
BD_OLD = ('if(t.socialRelations)for(const T of t.socialRelations)T.favorability>=80?S+=.1:'
          'T.favorability>=50&&(S+=.05);return{total:r*d+a*0.26+l*0.6+c*0.6+'
          'Math.min(b,0.1)+S*0.32,art:r,talent:a,title:l,grotto:c,synergy:b,npc:S,'
          'spiritualRootBonus:d}')
BD_NEW = ('if(t.socialRelations)for(const T of t.socialRelations)T.favorability>=80?S+=.1:'
          'T.favorability>=50&&(S+=.05);'
          + MARK +
          'const _ar=r*d,_ta=a*0.26,_ti=l*0.6,_gr=c*0.6,_sy=Math.min(b,0.1),_np=S*0.32;'
          'return{total:_ar+_ta+_ti+_gr+_sy+_np,art:r,talent:a,title:l,grotto:c,'
          'synergy:b,npc:S,spiritualRootBonus:d,'
          'dArt:_ar,dTalent:_ta,dTitle:_ti,dGrotto:_gr,dSynergy:_sy,dNpc:_np}')

# --------------------------------------------------------------------------- E2 · 明细行
# 字面区段、字面中文锚点（Python 源内以 \uXXXX 转义书写，保持源纯 ASCII）。
# 改后：6 项直接渲染 bd() 返回值（T.dArt…T.dNpc），不再自写权重。
DET_OLD = ('T.art>0&&`\u5fc3\u6cd5:+${(T.art*T.spiritualRootBonus*100).toFixed(1)}% `,'
           'T.talent>0&&`\u5929\u8d4b:+${(T.talent*0.26*100).toFixed(1)}% `,'
           'T.title>0&&`\u79f0\u53f7:+${(T.title*0.6*100).toFixed(1)}% `,'
           'T.grotto>0&&`\u6d1e\u5e9c:+${(T.grotto*0.6*100).toFixed(1)}% `,'
           'T.synergy>0&&`\u534f\u540c:+${(Math.min(T.synergy,0.1)*100).toFixed(1)}% `,'
           'T.npc>0&&`\u7f81\u7eca:+${(T.npc*0.32*100).toFixed(1)}%`')
DET_NEW = ('T.art>0&&`\u5fc3\u6cd5:+${(T.dArt*100).toFixed(1)}% `,'
           'T.talent>0&&`\u5929\u8d4b:+${(T.dTalent*100).toFixed(1)}% `,'
           'T.title>0&&`\u79f0\u53f7:+${(T.dTitle*100).toFixed(1)}% `,'
           'T.grotto>0&&`\u6d1e\u5e9c:+${(T.dGrotto*100).toFixed(1)}% `,'
           'T.synergy>0&&`\u534f\u540c:+${(T.dSynergy*100).toFixed(1)}% `,'
           'T.npc>0&&`\u7f81\u7eca:+${(T.dNpc*100).toFixed(1)}%`')

EDITS = [
    ('E1 bd() 聚合：6 项贡献单点计算并随返回值输出（同源源点）', BD_OLD, BD_NEW, 1),
    ('E2 明细行：6 项改渲染 bd() 返回值（不再自写权重）',        DET_OLD, DET_NEW, 1),
]

# --------------------------------------------------------------------------- 唯一来源 / 结构等价 断言串
LOCALS = ('const _ar=r*d,_ta=a*0.26,_ti=l*0.6,_gr=c*0.6,'
          '_sy=Math.min(b,0.1),_np=S*0.32;')
NEW_TOTAL = 'total:_ar+_ta+_ti+_gr+_sy+_np'
NEW_DETAIL_TAIL = 'dArt:_ar,dTalent:_ta,dTitle:_ti,dGrotto:_gr,dSynergy:_sy,dNpc:_np}'
OLD_TOTAL_EXPR = 'r*d+a*0.26+l*0.6+c*0.6+Math.min(b,0.1)+S*0.32'
# 改前明细行 6 个「自写权重」渲染项（补丁后必须清零）
OLD_DET_WEIGHTS = [
    'T.art*T.spiritualRootBonus*100',
    'T.talent*0.26*100',
    'T.title*0.6*100',
    'T.grotto*0.6*100',
    'Math.min(T.synergy,0.1)*100',
    'T.npc*0.32*100',
]
# 改后明细行 6 个「同源取值」渲染项（补丁后必须各 1 次）
NEW_DET_REFS = [
    'T.dArt*100', 'T.dTalent*100', 'T.dTitle*100',
    'T.dGrotto*100', 'T.dSynergy*100', 'T.dNpc*100',
]

# --------------------------------------------------------------------------- 冻结门禁串（不得改动）
FREEZE = [
    # r222 显示口径（难度后缀 + 明细段）与标记
    ('冻结·R222 标记未动',        '/*YLXW_R222_V2947*/', 1),
    ('冻结·R222 难度名取值器未动', 'YlxwDiffCn=()=>{', 1),
    ('冻结·R222 面板1主值未动',    '(c.total*YlxwDiffMul(void 0,"expMul")*100).toFixed(1)', 1),
    ('冻结·R222 面板2主值未动',    '(T.total*YlxwDiffMul(void 0,"expMul")*100).toFixed(1)', 1),
    ('冻结·R222 面板2难度段未动',
     '\u96be\u5ea6:\u00d7${YlxwDiffMul(void 0,"expMul").toFixed(1)}', 1),
    ('冻结·R222 面板1难度后缀未动',
     '\uff08\u96be\u5ea6\u00d7"+YlxwDiffMul(void 0,"expMul").toFixed(1)+" "+YlxwDiffCn()+"\uff09', 1),
    # 邻环注入标记（证明未误伤 r218 / r223 注入块）
    ('冻结·R218 标记未动',        '/*YLXW_R218_V2945*/', 1),
    ('冻结·R223 标记未动',        '/*YLXW_R223_V2948*/', 1),
]


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    g = []
    # 同源改造在位 + 旧串清零
    for label, old, new, n in EDITS:
        g.append(('%s · 新串在位' % label, new, n, '==', ''))
        g.append(('%s · 旧串清零' % label, old, 0, '==', ''))
    # 幂等标记唯一
    g.append(('幂等标记唯一', MARK, 1, '==', '/*YLXW_R225_V2949*/'))
    # 唯一来源：bd() 内 6 项贡献仅一处定义；合计=各局部量之和；明细随返回值输出
    g.append(('唯一来源·6 项贡献单点计算', LOCALS, 1, '==', ''))
    g.append(('合计=各贡献之和（同序同项）', NEW_TOTAL, 1, '==', ''))
    g.append(('明细随 bd() 返回值输出', NEW_DETAIL_TAIL, 1, '==', ''))
    # 旧合计式（含旧硬编码权重）已清零
    g.append(('旧合计式清零（无内联权重）', OLD_TOTAL_EXPR, 0, '==', ''))
    # 旧硬编码权重清零
    for w in OLD_DET_WEIGHTS:
        g.append(('旧明细权重清零 %s' % w, w, 0, '==', ''))
    # 新同源取值在位
    for r in NEW_DET_REFS:
        g.append(('新同源取值 %s' % r, r, 1, '==', ''))
    # 明细行结构标签保留（证明只换取值，标签未动）
    for lbl in ('\u5fc3\u6cd5:+', '\u5929\u8d4b:+', '\u79f0\u53f7:+',
                '\u6d1e\u5e9c:+', '\u534f\u540c:+', '\u7f81\u7eca:+'):
        g.append(('明细标签保留 %s' % lbl, lbl, 1, '==', ''))
    # 冻结
    for name, needle, cnt in FREEZE:
        g.append((name, needle, cnt, '==', '冻结未动'))
    return g


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert MARK == '/*YLXW_R225_V2949*/', '幂等标记被改动'
    for name, old, new, n in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old and new, '%s 锚点不得为空' % name
        assert n >= 1, '%s n 必须 >=1' % name
        assert old not in new, '%s old 是 new 的子串，会破坏旧串清零门禁' % name
        ascii_old = all(ord(ch) < 128 for ch in old)
        ascii_new = all(ord(ch) < 128 for ch in new)
        assert ascii_old == ascii_new, '%s 新旧锚点形态（转义/字面）必须一致' % name

    # 形态断言：E1 纯 ASCII；E2 含非 ASCII（字面中文）
    assert all(ord(ch) < 128 for ch in BD_OLD), 'E1 旧锚点必须纯 ASCII'
    assert all(ord(ch) < 128 for ch in BD_NEW), 'E1 新锚点必须纯 ASCII'
    assert any(ord(ch) >= 128 for ch in DET_OLD), 'E2 旧锚点须含非 ASCII'
    assert any(ord(ch) >= 128 for ch in DET_NEW), 'E2 新锚点须含非 ASCII'

    # E1：幂等标记在位 + 唯一来源局部量 + 合计=各贡献之和 + 明细随返回值输出
    assert MARK in BD_NEW, 'E1 缺幂等标记'
    assert LOCALS in BD_NEW, 'E1 缺 6 项贡献单点计算局部量'
    assert NEW_TOTAL in BD_NEW, 'E1 合计式须为各贡献之和'
    assert NEW_DETAIL_TAIL in BD_NEW, 'E1 须随返回值输出 6 项明细'
    # E1：改前合计式的 6 个项必须逐一映射到改后局部量（结构等价 → 数值零变化）
    for old_term, loc in (('r*d', '_ar'), ('a*0.26', '_ta'), ('l*0.6', '_ti'),
                          ('c*0.6', '_gr'), ('Math.min(b,0.1)', '_sy'), ('S*0.32', '_np')):
        assert old_term in OLD_TOTAL_EXPR, 'E1 旧合计式缺项 %s' % old_term
        assert ('%s=%s' % (loc, old_term)) in LOCALS, 'E1 局部量 %s 未与旧项 %s 对应' % (loc, old_term)
    # E1：新锚点不得残留旧合计式（内联权重）
    assert OLD_TOTAL_EXPR not in BD_NEW, 'E1 新锚点残留旧内联权重合计式'
    # E1：art/talent/.../spiritualRootBonus 原样保留（消费点契约不变）
    for keep in ('art:r,talent:a,title:l,grotto:c,synergy:b,npc:S,spiritualRootBonus:d'):
        assert keep in BD_NEW, 'E1 未保留原返回字段 %s' % keep

    # E2：新锚点须逐项引用 bd() 返回值，且不得残留任何自写权重
    for r in NEW_DET_REFS:
        assert r in DET_NEW, 'E2 缺同源取值 %s' % r
    for w in OLD_DET_WEIGHTS:
        assert w not in DET_NEW, 'E2 新锚点残留自写权重 %s' % w
    # E2：明细行结构（条件 + 标签 + 尾随空格/百分号）逐字保留
    for frag in ('T.art>0&&', 'T.talent>0&&', 'T.title>0&&', 'T.grotto>0&&',
                 'T.synergy>0&&', 'T.npc>0&&'):
        assert frag in DET_NEW, 'E2 缺明细条件 %s' % frag
    for lbl in ('\u5fc3\u6cd5:+', '\u5929\u8d4b:+', '\u79f0\u53f7:+',
                '\u6d1e\u5e9c:+', '\u534f\u540c:+', '\u7f81\u7eca:+'):
        assert lbl in DET_NEW, 'E2 缺明细标签 %s' % lbl
    assert DET_NEW.endswith('%`'), 'E2 末项结尾形态被改动'

    # 注入内容不得含网络 / 定时器原语
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


def _extract_bd(txt):
    """从文本中抽取 bd() 完整源码（`function bd(t){` 起，花括号配平；bd 体内无含花括号的字符串）。"""
    i = txt.find('function bd(t){')
    if i < 0:
        raise AssertionError('未找到 bd() 定义')
    j = i + len('function bd(t)')  # 指向 '{'
    depth = 0
    k = j
    while k < len(txt):
        ch = txt[k]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return txt[i:k + 1]
        k += 1
    raise AssertionError('bd() 花括号未配平')


# Node 隔离数值 A/B 脚本（bdOld=改前源码；bdNew=改后源码；桩函数按假 player 字段取值）。
_NUM_AB_BODY = r"""
'use strict';
var __cur = null;
var YLXW_T097_TALENT_K = 1;
function gd(t){ return t.__u; }
function go(u, M){ return __cur.__d; }
var Un = { find: function(f){ return { id: f, effects: { expRate: __cur.__talentRate || 0 } }; } };
function $a(id, list){ return { expRate: __cur.__titleRate || 0 }; }
function Pm(t){ return t.cultivationArts; }
function fy(m){ return { expRate: __cur.__synergyRate || 0 }; }
function YlxwCharDexRate(t){ return __cur.__npcBase || 0; }

var bdOld = (function(){ __OLD_SRC__ ; return bd; })();
var bdNew = (function(){ __NEW_SRC__ ; return bd; })();

function eq(x, y){ return (x === y) || (Number.isNaN(x) && Number.isNaN(y)); }

var players = [
  { __u: null, __d: 1, __talentRate: 0, __titleRate: 0, __synergyRate: 0, __npcBase: 0,
    talentIds: [], cultivationArts: [] },
  { __u: { effects: { expRate: 0.3 }, grade: '\u5929' }, __d: 1.2, __talentRate: 0.05,
    __titleRate: 0, __synergyRate: 0, __npcBase: 0, talentIds: ['a', 'b'], cultivationArts: [] },
  { __u: { effects: { expRate: 0.9 }, grade: '\u9ec4' }, __d: 0.8, __talentRate: 0.02,
    __titleRate: 0.08, __synergyRate: 0, __npcBase: 0, talentIds: ['x'],
    cultivationArts: [], grotto: { expRateBonus: 0.04, spiritArrayEnhancement: 0.02 },
    titleId: 't1', unlockedTitles: ['t1'] },
  { __u: null, __d: 1, __talentRate: 0, __titleRate: 0, __synergyRate: 0.13,
    __npcBase: 0.2, talentIds: [], cultivationArts: [],
    socialRelations: [{ favorability: 90 }, { favorability: 55 }, { favorability: 10 }] },
  { __u: { effects: { expRate: 1.4 }, grade: '\u5929' }, __d: 1.35, __talentRate: 0.11,
    __titleRate: 0.2, __synergyRate: 0.5, __npcBase: 0.33, talentIds: ['a', 'b', 'c'],
    cultivationArts: [], grotto: { expRateBonus: 0.1, spiritArrayEnhancement: 0.05 },
    titleId: 't2', unlockedTitles: ['t2'], socialRelations: [{ favorability: 100 }] },
  { __u: { effects: { expRate: 0.001 }, grade: 'zz' }, __d: 0.9999, __talentRate: 0.0001,
    __titleRate: 0.0002, __synergyRate: 0.0999999, __npcBase: 0.0001, talentIds: ['q'],
    cultivationArts: [], grotto: { expRateBonus: 0, spiritArrayEnhancement: 0 } },
  { __u: null, __d: 1, __talentRate: 0.26, __titleRate: 0.6, __synergyRate: 0.1,
    __npcBase: 0.32, talentIds: ['a'], cultivationArts: [] },
  { __u: { effects: { expRate: 2.0 }, grade: '\u5929' }, __d: 1, __talentRate: 0.5,
    __titleRate: 0.9, __synergyRate: 0.2, __npcBase: 0.5, talentIds: ['a', 'b'],
    cultivationArts: [], socialRelations: [{ favorability: 80 }, { favorability: 50 }] }
];

var fails = 0;
for (var i = 0; i < players.length; i++){
  var p = players[i]; __cur = p;
  var o = bdOld(p), n = bdNew(p);
  var od = { art: o.art * o.spiritualRootBonus, talent: o.talent * 0.26,
             title: o.title * 0.6, grotto: o.grotto * 0.6,
             synergy: Math.min(o.synergy, 0.1), npc: o.npc * 0.32 };
  var nd = { art: n.dArt, talent: n.dTalent, title: n.dTitle,
             grotto: n.dGrotto, synergy: n.dSynergy, npc: n.dNpc };
  var ok = eq(o.total, n.total);
  for (var k in od){ if (!eq(od[k], nd[k])) ok = false; }
  var sum = nd.art + nd.talent + nd.title + nd.grotto + nd.synergy + nd.npc;
  if (!eq(sum, n.total)) ok = false;
  if (!ok){
    fails++;
    console.log('MISMATCH #' + i + ' ' + JSON.stringify(
      { oldTotal: o.total, newTotal: n.total, od: od, nd: nd, sum: sum }));
  }
}
console.log(fails === 0 ? ('NUMAB_OK players=' + players.length) : ('NUMAB_FAIL fails=' + fails));
process.exit(fails === 0 ? 0 : 1);
"""


def _numeric_ab(txt0, out_txt, node_bin):
    """Node 隔离数值 A/B：改前 bd() vs 改后 bd()，逐项断言合计与明细完全相同（fail-closed）。"""
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过数值 A/B（可用 --node 显式指定）')
        return True
    try:
        src_old = _extract_bd(txt0)
        src_new = _extract_bd(out_txt)
    except AssertionError as e:
        print('  [FAIL] 抽取 bd() 失败：%s' % e)
        return False
    # 以「源码原样」注入（非 JSON 字符串）：IIFE 内 `function bd(...){...}` 即为可执行代码。
    assert '__OLD_SRC__' not in src_old and '__NEW_SRC__' not in src_old, 'bd() 源码含占位符'
    assert '__OLD_SRC__' not in src_new and '__NEW_SRC__' not in src_new, 'bd() 源码含占位符'
    body = (_NUM_AB_BODY
            .replace('__OLD_SRC__', src_old)
            .replace('__NEW_SRC__', src_new))
    fd, tmp = tempfile.mkstemp(prefix='.r225ab-', suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(body.encode('utf-8'))
        p = subprocess.run([node_bin, tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = p.stdout.decode('utf-8', 'replace')
        err = p.stderr.decode('utf-8', 'replace')
        for line in out.strip().splitlines():
            print('    ' + line)
        if p.returncode != 0:
            print('  [FAIL] 数值 A/B 不一致（合计或明细漂移）:\n%s' % err[:2000])
            return False
        if 'NUMAB_OK' not in out:
            print('  [FAIL] 数值 A/B 未产出 OK 标记:\n%s' % err[:2000])
            return False
        print('  [OK] 数值 A/B 通过（合计与 6 项明细逐项完全一致，且 Σ明细==合计）')
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _node_check(out_bytes, node_bin):
    """对产物跑 `node --check`（fail-closed）；找不到 node 则告警跳过。"""
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check（可用 --node 显式指定）')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r225chk-', suffix='.js')
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
    """打印每个补丁点补丁前后的解码视图对照（±60 字符窗口）。"""
    print('  --- 补丁点补丁前后解码视图（±60 字符）---')
    for name, old, new, _n in EDITS:
        i0 = txt0.find(old)
        i1 = txt1.find(new)
        if i0 < 0 or i1 < 0:
            print('    [WARN] %s 未定位到（%d/%d）' % (name, i0, i1))
            continue
        before = txt0[max(0, i0 - 60):i0 + len(old) + 60]
        after = txt1[max(0, i1 - 60):i1 + len(new) + 60]
        print('    · %s' % name)
        print('        前: %s' % _decode(before).replace('\n', '\\n'))
        print('        后: %s' % _decode(after).replace('\n', '\\n'))


def main() -> int:
    ap = argparse.ArgumentParser(description='R-228 修炼效率明细行与 bd() 同源化（--src 补丁）')
    ap.add_argument('--src', required=True,
                    help='装配产物 js（如 build/assets/index-v2949-20261009.js）')
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
        print('[SKIP] source looks already patched（R-228 同源化已在位）')
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
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        if not good:
            print('  [FAIL] %-46s actual=%d expect %s %d %s'
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

    # 8) 数值 A/B（fail-closed）：改前 bd() vs 改后 bd()，合计与明细逐项一致
    if not _numeric_ab(txt0, out_txt, a.node):
        print('[FAIL] 数值 A/B 失败，未写盘')
        return 1

    # 9) 视图对照
    _dump_views(txt0, out_txt)

    # 10) 改前 .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r225-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r225-', suffix='.tmp')
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
