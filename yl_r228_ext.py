# -*- coding: utf-8 -*-
r"""
yl_r228_ext.py — R-228 修炼效率「明细行」权重硬编码 → 与 bd() 同源（纯客户端）

契约（SKILL §16.2）：导出 `apply(p, ctx) -> gates`
  · p   = yl_patch.Patcher（p.replace(name, old, new, expect=1, note=...)）
  · ctx = {'zh': zh, 'base_text': str}
  · gates = list[(name, needle, expected, op, note)]，op ∈ {'==','>=','<='}
本模块只做文本锚点替换（E1/E2 两处，均断言唯一），**不注入新代码块**（无 INJECT_JS）。
另附 `__main__` 自检：对基线在内存里应用补丁 → 门禁 → node --check → 往返自证 →
**改动前后数值等价性证明（Node 真跑 bd() 与明细行渲染数组）**。全程只读，不落盘。

基线：build/assets/index-v2949-20261009.js（2,326,139 B，md5 d8fac7c23951a88c739579726823fb2c）

==============================================================================
一、缺陷（R-222 显示口径登记表挖出的「今天第 3 次事故」的根因）
==============================================================================
「修炼效率加成」两处显示（均为 bd(player) 再 × 难度倍率）：
  · @837339  人物面板「修为 (Exp)」条下：主值 `(c.total*YlxwDiffMul(void 0,"expMul")*100)`
  · @1739385 人物志面板：主值 `(T.total*YlxwDiffMul(void 0,"expMul")*100)`
                + 「明细行」：心法 / 天赋 / 称号 / 洞府 / 协同 / 羁绊
★ 但 @1739509 的**明细行把权重 0.26 / 0.6 / 0.6 / 0.1 / 0.32 硬编码在渲染串里**，
  而计算这些权重的 `bd()` 里**各写了一份同样的值** ⇒ 同一个值两处各写一份
  ⇒ 改 bd() 忘改明细行 ⇒ 玩家看到的明细与合计对不上（这就是 22% 那次事故的根因）。

==============================================================================
二、取证一：bd() 的实际位置与返回结构（bundle @617858，实测源码逐字）
==============================================================================
    function bd(t){
      let r=0,a=0,l=0,c=0,d=1;
      const u=gd(t);
      if(u&&u.effects.expRate){
        const $={天:2,地:1.5,玄:1.2,黄:1}[u.grade]||1;
        r=Math.min(1.25,u.effects.expRate*$);                 // 心法/功法：gd()，封顶 1.25
        const M=t.spiritualRoots||{metal:0,wood:0,water:0,fire:0,earth:0};
        d=go(u,M)                                             // 灵根加成：go()
      }
      const f=t.talentIds||[];
      for(const T of f){const $=Un.find(M=>M.id===T);
        $&&$.effects.expRate&&(a+=$.effects.expRate*YLXW_T097_TALENT_K)}   // 天赋（K=1/0.26）
      const v=$a(t.titleId,t.unlockedTitles||[]);v.expRate>0&&(l=v.expRate), // 称号
      t.grotto&&(c=(t.grotto.expRateBonus||0)+(t.grotto.spiritArrayEnhancement||0)); // 洞府
      const m=Pm(t.cultivationArts);let b=fy(m).expRate||0,S=0;             // 协同
      try{S+=(typeof YlxwCharDexRate==="function"?YlxwCharDexRate(t):0);}catch(ylCde){}
      if(t.socialRelations)for(const T of t.socialRelations)                // 羁绊
        T.favorability>=80?S+=.1:T.favorability>=50&&(S+=.05);
      return{total:r*d+a*0.26+l*0.6+c*0.6+Math.min(b,0.1)+S*0.32,
             art:r,talent:a,title:l,grotto:c,synergy:b,npc:S,spiritualRootBonus:d}
    }
返回对象 8 个字段：total + art/talent/title/grotto/synergy/npc/spiritualRootBonus。
合计式 `r*d + a*0.26 + l*0.6 + c*0.6 + min(b,0.1) + S*0.32` 里内联了 5 个权重。

==============================================================================
三、取证二：★ 别名区结论（SKILL §12.3 铁律 —— 改前必须读清作用域里的变量是谁）
==============================================================================
明细行所在的组件是 `hM`（@1695616 起），形参解构：
    hM=({isOpen:t,onClose:r,player:a,setPlayer:l,onSelectTalent:c,onSelectTitle:d,
         onAllocateAttribute:u,onAllocateAllAttributes:f,onUseInheritance:v,
         onResetAttributes:m,addLog:j=b=>Vm.log(b)})=>{ ... }
组件体内（@1695712 附近，逐字）：
    const b=O.useMemo(()=>xt(a),[a]),          // ★ b = xt(player) 总属性 —— 不是玩家！
          S=O.useMemo(()=>jd(a.achievements).length,[a.achievements]),
          x=O.useMemo(()=>pM(a),[a]),
          T=O.useMemo(()=>bd(a),[a]),          // ★ T = bd(player)
⇒ 结论：**该作用域里 `a` 才是 player；`b` 是 `xt(a)`（总属性），根本不是玩家**
  （这正是 §12.3 警告的「单字母别名被批量重映射，`b` 根本不是玩家」）。
  明细行引用的 `T` **确实是 `bd(player)` 的返回值** ⇒ 「读 bd() 的结果」这个改法在
  本作用域成立，不会误改到别名。
（`bd(` 另有 3 个**真实调用点** @748542（`m.total`）/ @834518（`c.total`）/ @893618（`h.total`），
  均只消费 `total`；@1503921 与 @392372 只是**注释**里提到 `bd()`，并非调用。
  本环只**新增**返回字段，对任何消费点都无影响。）

==============================================================================
四、取证三：明细行（bundle 数组区间 [1739508, 1739940]，实测逐字，**字面中文**）
==============================================================================
    [T.art>0&&`心法:+${(T.art*T.spiritualRootBonus*100).toFixed(1)}% `,
     T.talent>0&&`天赋:+${(T.talent*0.26*100).toFixed(1)}% `,
     T.title>0&&`称号:+${(T.title*0.6*100).toFixed(1)}% `,
     T.grotto>0&&`洞府:+${(T.grotto*0.6*100).toFixed(1)}% `,
     T.synergy>0&&`协同:+${(Math.min(T.synergy,0.1)*100).toFixed(1)}% `,
     T.npc>0&&`羁绊:+${(T.npc*0.32*100).toFixed(1)}%`,
     YlxwDiffMul(void 0,"expMul")>1&&`难度:×${...}（${YlxwDiffCn()}）`]   ← R-222 追加段，本环不碰
逐项与 bd() 合计项一一对应（心法 r*d / 天赋 a*0.26 / 称号 l*0.6 / 洞府 c*0.6 /
协同 min(b,0.1) / 羁绊 S*0.32）——**改前数值一致、尚未漂移**，但 5 个权重两处各写一份。

==============================================================================
五、改法（治本）
==============================================================================
E1（bd()）：把 6 项「已加权贡献」在 bd() 内部**各计算一次**（具名局部量），合计式改为
  **这些局部量之和**（求和顺序与改前逐项一致 ⇒ IEEE754 逐位相同），并把它们**额外返回**：
      /*YLXW_R228_V2949*/const _ar=r*d,_ta=a*0.26,_ti=l*0.6,_gr=c*0.6,
      _sy=Math.min(b,0.1),_np=S*0.32;
      return{total:_ar+_ta+_ti+_gr+_sy+_np,art:r,...,spiritualRootBonus:d,
             cArt:_ar,cTalent:_ta,cTitle:_ti,cGrotto:_gr,cSynergy:_sy,cNpc:_np}
E2（明细行）：6 项改为**直接渲染 bd() 的返回值**（T.cArt…T.cNpc），明细行**不再自写任何权重**
  （旧 `*0.26 / *0.6 / *0.1 / *0.32 / *T.spiritualRootBonus` 全部清零）。
⇒ 权重与心法乘法在**全 bundle 唯一一处**（bd() 内的具名局部量）定义；合计与明细取自
  **同一批已计算值**（不是各自再算一遍），从结构上杜绝「明细与合计对不上」。数值零变化。
★ 新字段名 `cArt/cTalent/cTitle/cGrotto/cSynergy/cNpc` 在基线里出现 **0** 次（§12.8 防碰撞），
  且均为**对象属性名**（不是自由变量），不与任何压缩短名冲突。

==============================================================================
六、数值等价性证明（不是 Python 复算，而是 Node 真跑产物里的代码）
==============================================================================
从改前 / 改后文本各抽出 **bd() 源码** 与 **明细行渲染数组**（引号感知配平 —— 明细行是
模板串，`${...}` 里的花括号会骗过朴素配平，见 SKILL §25.1），拼成 Node 脚本：
  renderOld = function(T){ return <改前数组>; }   // T = bdOld(player)
  renderNew = function(T){ return <改后数组>; }   // T = bdNew(player)
对同一批（8 个）假 player 断言：
  ① renderOld(bdOld(p)).join(SEP) === renderNew(bdNew(p)).join(SEP)  —— **逐字节一致**
  ② Σ(6 项明细) === total（同源不变量）
  ③ 负向对照：把改前数组的 0.26 扰动成 0.27，必须能检出差异（证明测试非空）
不一致即拒写盘。stub 的 gd/go/Un/$a/Pm/fy/YlxwCharDexRate 与真实闭包同形，取值由 __cur 驱动。

==============================================================================
七、可 grep 的特征串
==============================================================================
  新：/*YLXW_R228_V2949*/  /  const _ar=r*d,_ta=a*0.26  /  cArt:_ar,cTalent:_ta
      /  T.cTalent*100  /  T.cNpc*100
  旧（必须清零）：r*d+a*0.26+l*0.6+c*0.6+Math.min(b,0.1)+S*0.32  /  T.talent*0.26*100
      /  T.npc*0.32*100  /  T.art*T.spiritualRootBonus*100  /  Math.min(T.synergy,0.1)*100

==============================================================================
八、边界
==============================================================================
  · 纯客户端；不改服务端、不改数值、不改存档 schema。
  · 不改 build_v26n.py / chain_build.py / dryrun_087.py / sim_remote_check.py /
    任何 build/assets/* / 其它 yl_*_ext.py；不动 r218/r222/r223 已改文案与逻辑。
  · 本模块**不写盘**（apply() 只改 Patcher 内存文本；__main__ 亦只读）。
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile

# --------------------------------------------------------------------------- 契约常量
MARK = '/*YLXW_R228_V2949*/'

# E1 · bd() 聚合（转义区段 / 纯 ASCII）
BD_OLD = ('return{total:r*d+a*0.26+l*0.6+c*0.6+Math.min(b,0.1)+S*0.32,'
          'art:r,talent:a,title:l,grotto:c,synergy:b,npc:S,spiritualRootBonus:d}')

BD_NEW = (MARK +
          'const _ar=r*d,_ta=a*0.26,_ti=l*0.6,_gr=c*0.6,_sy=Math.min(b,0.1),_np=S*0.32;'
          'return{total:_ar+_ta+_ti+_gr+_sy+_np,art:r,talent:a,title:l,grotto:c,'
          'synergy:b,npc:S,spiritualRootBonus:d,'
          'cArt:_ar,cTalent:_ta,cTitle:_ti,cGrotto:_gr,cSynergy:_sy,cNpc:_np}')

# E2 · 明细行（字面区段 / 字面中文；源内以 \uXXXX 书写，Python 解码为真字符，与 bundle 逐字一致）
DET_OLD = ('T.art>0&&`\u5fc3\u6cd5:+${(T.art*T.spiritualRootBonus*100).toFixed(1)}% `,'
           'T.talent>0&&`\u5929\u8d4b:+${(T.talent*0.26*100).toFixed(1)}% `,'
           'T.title>0&&`\u79f0\u53f7:+${(T.title*0.6*100).toFixed(1)}% `,'
           'T.grotto>0&&`\u6d1e\u5e9c:+${(T.grotto*0.6*100).toFixed(1)}% `,'
           'T.synergy>0&&`\u534f\u540c:+${(Math.min(T.synergy,0.1)*100).toFixed(1)}% `,'
           'T.npc>0&&`\u7f81\u7eca:+${(T.npc*0.32*100).toFixed(1)}%`')

DET_NEW = ('T.art>0&&`\u5fc3\u6cd5:+${(T.cArt*100).toFixed(1)}% `,'
           'T.talent>0&&`\u5929\u8d4b:+${(T.cTalent*100).toFixed(1)}% `,'
           'T.title>0&&`\u79f0\u53f7:+${(T.cTitle*100).toFixed(1)}% `,'
           'T.grotto>0&&`\u6d1e\u5e9c:+${(T.cGrotto*100).toFixed(1)}% `,'
           'T.synergy>0&&`\u534f\u540c:+${(T.cSynergy*100).toFixed(1)}% `,'
           'T.npc>0&&`\u7f81\u7eca:+${(T.cNpc*100).toFixed(1)}%`')

EDITS = [
    ('r228-bd',  BD_OLD,  BD_NEW,  1),
    ('r228-det', DET_OLD, DET_NEW, 1),
]

# --------------------------------------------------------------------------- 同源 / 结构断言串
LOCALS = ('const _ar=r*d,_ta=a*0.26,_ti=l*0.6,_gr=c*0.6,'
          '_sy=Math.min(b,0.1),_np=S*0.32;')
NEW_TOTAL = 'total:_ar+_ta+_ti+_gr+_sy+_np'
NEW_DETAIL_TAIL = 'cArt:_ar,cTalent:_ta,cTitle:_ti,cGrotto:_gr,cSynergy:_sy,cNpc:_np}'
OLD_TOTAL_EXPR = 'r*d+a*0.26+l*0.6+c*0.6+Math.min(b,0.1)+S*0.32'
OLD_RETURN_FIELDS = 'art:r,talent:a,title:l,grotto:c,synergy:b,npc:S,spiritualRootBonus:d'
# 新字段（须在基线出现 0 次；§12.8 防与压缩短名碰撞）
NEW_FIELDS = ['cArt', 'cTalent', 'cTitle', 'cGrotto', 'cSynergy', 'cNpc']
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
    'T.cArt*100', 'T.cTalent*100', 'T.cTitle*100',
    'T.cGrotto*100', 'T.cSynergy*100', 'T.cNpc*100',
]
# 明细行结构标签（证明只换取值，标签/条件未动）
DET_LABELS = ['\u5fc3\u6cd5:+', '\u5929\u8d4b:+', '\u79f0\u53f7:+',
              '\u6d1e\u5e9c:+', '\u534f\u540c:+', '\u7f81\u7eca:+']

# --------------------------------------------------------------------------- 冻结门禁（不得改动）
FREEZE = [
    # ★★ 0.9.50 集成修正（lead）：此处原列 6 条「邻环注入标记 / R-222 显示口径」冻结门禁
    #    （`/*YLXW_R218_V2945*/` / `/*YLXW_R222_V2947*/` / `/*YLXW_R223_V2948*/` /
    #     面板1主值 / 面板2主值 / 面板2难度段）—— **已移除**，原因是**结构性不可满足**：
    #   R-218/R-222/R-223 三者都是 **STANDALONE_CLIENT**（CLI `--src` 契约），
    #   装配序上 `build_v26n` 先跑 V28_MODULES、**再**跑 apply_standalone；
    #   而本模块是 V28_MODULE ⇒ 其 gates() 在**模块段**（standalone 之前）求值
    #   ⇒ 那时这三个标记**尚不存在** ⇒ 6 条必然 FAIL（假 FAIL）。
    #   ★ 这 6 条**并未失去覆盖**：R-222 自己的 FREEZE 列表里有一模一样的 6 条，
    #     且 R-222 apply 时会自检（实测打印 `[OK] 门禁全绿（补丁点 5 处；冻结 11 项）`）。
    #   ★ 通用判据：**模块门禁只能断言「它运行那一刻已存在的东西」**；
    #     断言下游 standalone 的产物 = 把依赖方向写反（技能 §22.5 的镜像形态）。
    # 消费点契约：T 仍是 bd(a) 的 memo（a = player，见 docstring §三）
    ('冻结·明细行消费点 T=bd(player) 未动', 'T=O.useMemo(()=>bd(a),[a])', 1),
    # bd() 原返回字段逐字保留
    ('冻结·bd() 原返回字段未动', OLD_RETURN_FIELDS, 1),
]


def _precheck():
    """模块常量自检（fail-closed；apply 与 __main__ 均调用）。"""
    assert MARK == '/*YLXW_R228_V2949*/', '幂等标记被改动'
    for name, old, new, n in EDITS:
        assert old != new, '%s 新旧锚点相同' % name
        assert old and new, '%s 锚点不得为空' % name
        assert n == 1, '%s n 必须为 1' % name
        assert old not in new, '%s old 是 new 的子串（破坏「旧串清零」门禁）' % name
        # 形态一致性：新旧锚点同为一类（纯 ASCII / 含非 ASCII）
        assert (all(ord(c) < 128 for c in old)
                == all(ord(c) < 128 for c in new)), '%s 新旧锚点形态不一致' % name
    # E1 纯 ASCII；E2 字面中文
    assert all(ord(c) < 128 for c in BD_OLD) and all(ord(c) < 128 for c in BD_NEW), \
        'E1 锚点须纯 ASCII'
    assert any(ord(c) >= 128 for c in DET_OLD) and any(ord(c) >= 128 for c in DET_NEW), \
        'E2 锚点须含非 ASCII（字面中文）'
    # E1 结构：6 项贡献单点计算 + 合计=各贡献之和 + 明细随返回值输出
    assert MARK in BD_NEW, 'E1 缺幂等标记'
    assert LOCALS in BD_NEW, 'E1 缺 6 项贡献单点计算局部量'
    assert NEW_TOTAL in BD_NEW, 'E1 合计式须为各贡献之和'
    assert NEW_DETAIL_TAIL in BD_NEW, 'E1 须随返回值输出 6 项明细'
    for old_term, loc in (('r*d', '_ar'), ('a*0.26', '_ta'), ('l*0.6', '_ti'),
                          ('c*0.6', '_gr'), ('Math.min(b,0.1)', '_sy'), ('S*0.32', '_np')):
        assert old_term in OLD_TOTAL_EXPR, '旧合计式缺项 %s' % old_term
        assert ('%s=%s' % (loc, old_term)) in LOCALS, '局部量 %s 未与旧项 %s 对应' % (loc, old_term)
    assert OLD_TOTAL_EXPR not in BD_NEW, 'E1 残留旧内联权重合计式'
    assert OLD_RETURN_FIELDS in BD_NEW, 'E1 未保留原返回字段'
    # E2 结构：逐项引用 bd() 返回值，且不残留任何自写权重
    for r in NEW_DET_REFS:
        assert r in DET_NEW, 'E2 缺同源取值 %s' % r
    for w in OLD_DET_WEIGHTS:
        assert w not in DET_NEW, 'E2 残留自写权重 %s' % w
    for frag in ('T.art>0&&', 'T.talent>0&&', 'T.title>0&&',
                 'T.grotto>0&&', 'T.synergy>0&&', 'T.npc>0&&'):
        assert frag in DET_NEW, 'E2 缺明细条件 %s' % frag
    for lbl in DET_LABELS:
        assert lbl in DET_NEW, 'E2 缺明细标签 %s' % lbl
    assert DET_NEW.endswith('%`'), 'E2 末项结尾形态被改动'


def apply(p, ctx):
    """R-228：bd() 暴露 6 项已加权贡献（同源源点）→ 明细行改读 bd() 返回值。

    p   = yl_patch.Patcher；ctx = {'zh': zh, 'base_text': str}
    返回 gates = list[(name, needle, expected, op, note)]。
    """
    _precheck()

    # 新字段防碰撞（§12.8）：基线里必须出现 0 次（此处 p.text 仍为基线）
    for f in NEW_FIELDS:
        c = p.count(f)
        if c != 0:
            raise AssertionError('新字段 %r 在基线已出现 %d 次（§12.8 防碰撞）' % (f, c))

    # E1：bd() 聚合同源化
    p.replace('r228-bd', BD_OLD, BD_NEW, expect=1,
              note='bd()：6 项贡献单点计算（具名局部量）+ 随返回值输出 cArt…cNpc')
    # E2：明细行改读 bd() 返回值
    p.replace('r228-det', DET_OLD, DET_NEW, expect=1,
              note='明细行：6 项改渲染 bd() 返回值，不再自写权重')

    gates = []

    # ---- 新写法在位（每项 ==1） ----
    gates.append(('R228·幂等标记唯一', MARK, 1, '==', '/*YLXW_R228_V2949*/'))
    gates.append(('R228·6 项贡献单点计算（唯一来源）', LOCALS, 1, '==', ''))
    gates.append(('R228·合计=各贡献之和（同序同项）', NEW_TOTAL, 1, '==', ''))
    gates.append(('R228·明细随 bd() 返回值输出', NEW_DETAIL_TAIL, 1, '==', ''))
    for r in NEW_DET_REFS:
        gates.append(('R228·明细同源取值 %s' % r, r, 1, '==', ''))

    # ---- 旧硬编码串清零（==0；只断言「新串在位」会被新旧并存骗过） ----
    gates.append(('R228·旧合计式（内联权重）已清零', OLD_TOTAL_EXPR, 0, '==', ''))
    gates.append(('R228·旧 bd() 返回形态已清零', BD_OLD, 0, '==', ''))
    gates.append(('R228·旧明细行形态已清零', DET_OLD, 0, '==', ''))
    for w in OLD_DET_WEIGHTS:
        gates.append(('R228·旧明细权重已清零 %s' % w, w, 0, '==', ''))

    # ---- 结构保留（只换取值，条件/标签未动） ----
    for frag in ('T.art>0&&', 'T.talent>0&&', 'T.title>0&&',
                 'T.grotto>0&&', 'T.synergy>0&&', 'T.npc>0&&'):
        gates.append(('R228·明细条件保留 %s' % frag, frag, 1, '==', ''))
    for lbl in DET_LABELS:
        gates.append(('R228·明细标签保留 %s' % lbl, lbl, 1, '==', ''))

    # ---- 冻结 ----
    for name, needle, cnt in FREEZE:
        gates.append((name, needle, cnt, '==', '冻结未动'))

    return gates


# =========================================================================== 自检（__main__）
# 引号感知的配对匹配（SKILL §25.1：模板串 `${...}` 里的花括号会骗过朴素配平）

def _match(txt, start, open_ch, close_ch):
    """从 txt[start]（== open_ch）起做配对匹配，返回配对 close_ch 的下标；-1 表示未配平。
    引号（' " `）内一律跳过；`\\` 转义跳一个字符。"""
    depth = 0
    i = start
    n = len(txt)
    while i < n:
        c = txt[i]
        if c == '"' or c == "'" or c == '`':
            q = c
            i += 1
            while i < n:
                if txt[i] == '\\':
                    i += 2
                    continue
                if txt[i] == q:
                    break
                i += 1
            i += 1
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _extract_bd(txt):
    """抽取 bd() 完整源码（`function bd(t){` 起，引号感知花括号配平）。"""
    i = txt.find('function bd(t){')
    if i < 0:
        raise AssertionError('未找到 bd() 定义')
    j = txt.index('{', i)
    k = _match(txt, j, '{', '}')
    if k < 0:
        raise AssertionError('bd() 花括号未配平')
    return txt[i:k + 1]


def _extract_detail_array(txt):
    """抽取明细行渲染数组字面量 `[ ... ]`（`children:[T.art>0&&` 之后那个 `[`）。"""
    a = 'children:[T.art>0&&'
    i = txt.find(a)
    if i < 0:
        raise AssertionError('未找到明细行数组（children:[T.art>0&&）')
    j = i + len('children:')
    if txt[j] != '[':
        raise AssertionError('明细行数组起点不是 [')
    k = _match(txt, j, '[', ']')
    if k < 0:
        raise AssertionError('明细行数组未配平（模板串配平失败？）')
    return txt[j:k + 1]


_NUM_AB_BODY = r"""
'use strict';
var __cur = null;
var YLXW_T097_TALENT_K = 1 / 0.26;
function gd(t){ return t.__u; }
function go(u, M){ return __cur.__d; }
var Un = { find: function(f){ return { id: f, effects: { expRate: __cur.__talentRate || 0 } }; } };
function $a(id, list){ return { expRate: __cur.__titleRate || 0 }; }
function Pm(t){ return t.cultivationArts; }
function fy(m){ return { expRate: __cur.__synergyRate || 0 }; }
function YlxwCharDexRate(t){ return __cur.__npcBase || 0; }
var __diff = 1;
function YlxwDiffMul(a, b){ return __diff; }
function YlxwDiffCn(){ return "P"; }

var bdOld = (function(){ __BD_OLD__ ; return bd; })();
var bdNew = (function(){ __BD_NEW__ ; return bd; })();

var renderOld = function(T){ return __DET_OLD__; };
var renderNew = function(T){ return __DET_NEW__; };
var renderOldPert = function(T){ return __DET_OLD_PERT__; };

var SEP = "\u0001";
function arrS(x){ return x.join(SEP); }

var players = [
  { __u: null, __d: 1, __talentRate: 0, __titleRate: 0, __synergyRate: 0, __npcBase: 0,
    talentIds: [], cultivationArts: [] },
  { __u: { effects: { expRate: 0.3 }, grade: '\u5929' }, __d: 1.2, __talentRate: 0.05,
    __titleRate: 0, __synergyRate: 0, __npcBase: 0, talentIds: ['a','b'], cultivationArts: [] },
  { __u: { effects: { expRate: 0.9 }, grade: '\u9ec4' }, __d: 0.8, __talentRate: 0.02,
    __titleRate: 0.08, __synergyRate: 0, __npcBase: 0, talentIds: ['x'],
    cultivationArts: [], grotto: { expRateBonus: 0.04, spiritArrayEnhancement: 0.02 },
    titleId: 't1', unlockedTitles: ['t1'] },
  { __u: null, __d: 1, __talentRate: 0, __titleRate: 0, __synergyRate: 0.13,
    __npcBase: 0.2, talentIds: [], cultivationArts: [],
    socialRelations: [{ favorability: 90 }, { favorability: 55 }, { favorability: 10 }] },
  { __u: { effects: { expRate: 1.4 }, grade: '\u5929' }, __d: 1.35, __talentRate: 0.11,
    __titleRate: 0.2, __synergyRate: 0.5, __npcBase: 0.33, talentIds: ['a','b','c'],
    cultivationArts: [], grotto: { expRateBonus: 0.1, spiritArrayEnhancement: 0.05 },
    titleId: 't2', unlockedTitles: ['t2'], socialRelations: [{ favorability: 100 }] },
  { __u: { effects: { expRate: 0.001 }, grade: 'zz' }, __d: 0.9999, __talentRate: 0.0001,
    __titleRate: 0.0002, __synergyRate: 0.0999999, __npcBase: 0.0001, talentIds: ['q'],
    cultivationArts: [], grotto: { expRateBonus: 0, spiritArrayEnhancement: 0 } },
  { __u: null, __d: 1, __talentRate: 0.26, __titleRate: 0.6, __synergyRate: 0.1,
    __npcBase: 0.32, talentIds: ['a'], cultivationArts: [] },
  { __u: { effects: { expRate: 2.0 }, grade: '\u5929' }, __d: 1, __talentRate: 0.5,
    __titleRate: 0.9, __synergyRate: 0.2, __npcBase: 0.5, talentIds: ['a','b'],
    cultivationArts: [], socialRelations: [{ favorability: 80 }, { favorability: 50 }] }
];

var fails = 0, checks = 0, negDetected = false;
for (var i = 0; i < players.length; i++){
  var p = players[i]; __cur = p;
  var o = bdOld(p), nn = bdNew(p);
  for (var d = 1; d <= 2; d++){
    __diff = d; checks++;
    if (arrS(renderOld(o)) !== arrS(renderNew(nn))) {
      fails++; console.log('DIFF #' + i + ' diff=' + d);
    }
  }
  checks++;
  var sum = nn.cArt + nn.cTalent + nn.cTitle + nn.cGrotto + nn.cSynergy + nn.cNpc;
  if (sum !== nn.total) { fails++; console.log('SUM #' + i); }
  // 负向对照：改前数组的 0.26 扰动为 0.27，必须能检出
  if (arrS(renderOldPert(o)) !== arrS(renderNew(nn))) { negDetected = true; }
  if (i === 4){
    __diff = 2;
    console.log('EVIDENCE p#4 old=' + JSON.stringify(arrS(renderOld(o))));
    console.log('EVIDENCE p#4 new=' + JSON.stringify(arrS(renderNew(nn))));
    console.log('EVIDENCE p#4 same=' + (arrS(renderOld(o)) === arrS(renderNew(nn))) +
                ' oldLen=' + arrS(renderOld(o)).length + ' newLen=' + arrS(renderNew(nn)).length);
  }
}
checks++;
if (!negDetected) { fails++; console.log('NEGCTRL 未检出（测试无区分度）'); }
console.log(fails === 0
  ? ('EQ_OK checks=' + checks + ' players=' + players.length + ' negctrl=detected')
  : ('EQ_FAIL fails=' + fails));
process.exit(fails === 0 ? 0 : 1);
"""


def verify_equivalence(base_text, out_text, node_bin=None):
    """Node 真跑：改前 bd()/明细行 vs 改后 bd()/明细行，逐字节一致 + Σ明细==合计 + 负向对照。"""
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过数值等价性证明')
        return None
    try:
        bd_old = _extract_bd(base_text)
        bd_new = _extract_bd(out_text)
        det_old = _extract_detail_array(base_text)
        det_new = _extract_detail_array(out_text)
    except AssertionError as e:
        print('  [FAIL] 抽取失败：%s' % e)
        return False
    if 'T.talent*0.26*100' not in det_old:
        print('  [FAIL] 改前明细数组未含 0.26 权重（基线形态不对？）')
        return False
    det_old_pert = det_old.replace('T.talent*0.26*100', 'T.talent*0.27*100', 1)
    if det_old_pert == det_old:
        print('  [FAIL] 负向对照串未能构造')
        return False
    body = (_NUM_AB_BODY
            .replace('__BD_OLD__', bd_old)
            .replace('__BD_NEW__', bd_new)
            .replace('__DET_OLD_PERT__', det_old_pert)
            .replace('__DET_OLD__', det_old)
            .replace('__DET_NEW__', det_new))
    fd, tmp = tempfile.mkstemp(prefix='.r228ab-', suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(body.encode('utf-8'))
        pr = subprocess.run([node_bin, tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = pr.stdout.decode('utf-8', 'replace')
        err = pr.stderr.decode('utf-8', 'replace')
        for line in out.strip().splitlines():
            print('    ' + line)
        if pr.returncode != 0 or 'EQ_OK' not in out:
            print('  [FAIL] 数值等价性证明未通过:\n%s' % err[:2000])
            return False
        print('  [OK] 数值等价性证明通过（改前/改后渲染输出逐字节一致；Σ明细==合计；负向对照可检出）')
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _node_check(out_bytes, node_bin=None):
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check')
        return None
    fd, tmp = tempfile.mkstemp(prefix='.r228chk-', suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out_bytes)
        pr = subprocess.run([node_bin, '--check', tmp],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if pr.returncode != 0:
            print('  [FAIL] node --check 未通过:\n%s'
                  % pr.stderr.decode('utf-8', 'replace')[:2000])
            return False
        print('  [OK] node --check 通过')
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _main(argv):
    import argparse
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description='R-228 自检（只读：门禁 + node --check + 数值等价证明）')
    ap.add_argument('--src', default=os.path.join(here, 'build', 'assets',
                                                  'index-v2949-20261009.js'))
    ap.add_argument('--node', default=None)
    a = ap.parse_args(argv)

    sys.path.insert(0, here)
    from yl_patch import Patcher, Gates, zh, md5_file, load_text  # noqa: E402

    if not os.path.exists(a.src):
        print('[FAIL] source not found: %s' % a.src)
        return 2
    base = load_text(a.src)
    print('=== 基线 ===')
    print('  %s' % a.src)
    print('  chars=%d  md5=%s' % (len(base), md5_file(a.src)))

    p = Patcher(base)
    gates = apply(p, {'zh': zh, 'base_text': base})
    out_text = p.text
    out = out_text.encode('utf-8')

    print()
    print('=== 应用补丁 ===')
    print(p.report())

    print()
    print('=== 门禁（%d 条）===' % len(gates))
    g = Gates(out_text)
    for t in gates:
        g.check(t[0], t[1], t[2], t[3], t[4])
    print(g.report())
    print('门禁结果: %s' % ('PASS' if g.passed() else 'FAIL'))

    print()
    print('=== 往返自证（新串换回旧串 == 基线）===')
    back = out_text
    for _n, old, new, cnt in reversed(EDITS):
        if back.count(new) != cnt:
            print('[FAIL] 往返：new 计数 != %d' % cnt)
            return 1
        back = back.replace(new, old, cnt)
    rt_ok = (back == base)
    print('  %s' % ('OK' if rt_ok else 'FAIL'))

    print()
    print('=== node --check ===')
    nchk = _node_check(out, a.node)

    print()
    print('=== 数值等价性证明（Node 真跑 bd() 与明细行渲染数组）===')
    eq = verify_equivalence(base, out_text, a.node)

    print()
    print('=== 汇总 ===')
    print('  chars %d -> %d (delta %+d)  bytes %d -> %d'
          % (len(base), len(out_text), len(out_text) - len(base),
             len(base.encode('utf-8')), len(out)))
    ok = g.passed() and rt_ok and (nchk is not False) and (eq is not False)
    print('  结论: %s' % ('ALL PASS' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
