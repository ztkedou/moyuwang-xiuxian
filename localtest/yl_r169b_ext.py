# -*- coding: utf-8 -*-
r"""
yl_r169b_ext.py — R-169 第二环（根治）：洞府灵草收获路径与种植路径对称化（standalone 纯客户端）

需求原文（台账 R-169，逐字）
--------------------------------------------------------------------------
  「没有映射的就补上这个道具，如果不好补就删除这个灵草选项。总之不要再出现现在这种情况。」

  「现在这种情况」= 洞府灵草收获时弹：
      ⚠️ 灵草【X】的配置信息缺失，已按 N 灵石折算回收（每个 300 灵石）。

==============================================================================
一、上一环（R-169 一环，localtest/yl_r169_ext.py，已上线）遗留
==============================================================================
  一环只给 `__halias` 补了 5 条**确定**映射（血参草→血参 / 紫猴草→紫猴花 /
  凝神草→凝神花 / 灵止血草→止血草 / 灵回气草→回气草），并**故意未写** 5 个拿不准的旧名：
      天灵草 / 星辰草 / 凤羽草 / 灵凤羽草 / 雪莲花
  ⇒ 这 5 个名字一旦走到收获，仍会落进「配置信息缺失 · 折算回收」兜底。

==============================================================================
二、根因（本环复核实测 · 与一环结论一致）
==============================================================================
  · 「折算回收」唯一出处 = 客户端 bundle 洞府灵草**单株收获**分支（函数 `j`）。
    全量 grep（本环实测，对 build/assets/index-v2926-20261006.js，2,302,495 B / 2,134,706 chars）：
        "折算回收"       count == 1   (@1954110，仅在 j 内)
        "配置信息缺失"   count == 1   (@1954073，仅在 j 内)
        服务端 srv/       count == 0
    ⇒ 只有一条路径。其它收获路径**本来就没有**这个兜底：
        · 批量收获 `b`（"一键收获/批量收获"按钮）：`(Q==null?void 0:Q.name)||D.herbName` +
          `rarity:(Q==null?void 0:Q.rarity)||"普通"` —— 未知名直接按原名入包，无警告。
        · 自动收获 useEffect（@637490）：`(g==null?void 0:g.name)||C.herbName` +
          `rarity:(g==null?void 0:g.rarity)||"普通"` —— 同上，无警告。
      ⇒ 即：**只有手动单株收获 `j` 是异类**。

  · 根因 = **种植与收获不对称**：
      种植 `m`（@1951428 起）在 `wn` 查不到时，调 `f(name, rarity)`（@1948652）**现场合成**
      灵草定义（`id = "herb-" + name.toLowerCase().replace(/\s+/g,"-")`）⇒ 任意「草药类」背包
      物品都能种下，`plantedHerbs[].herbName` 存下这个杂名；而收获 `j` **没有** 这个 `f()` 合成
      兜底，只查 `wn` ⇒ 旧名/杂名一到收获就折算回收。
    `wn` = 客户端**内嵌**灵草总表（20 味，bundle @485901 `wn=[{id:"spirit-grass"…}]`）。

==============================================================================
三、f() 签名与返回结构（本环实测 · @1948652）
==============================================================================
  f=(M,h="普通")=>{
    const E={普通:{growthTime:18e5,harvestQuantity:{min:2,max:5},grottoLevelRequirement:1},
             稀有:{growthTime:108e5,harvestQuantity:{min:1,max:3},grottoLevelRequirement:3},
             传说:{growthTime:288e5,harvestQuantity:{min:1,max:2},grottoLevelRequirement:5},
             仙品:{growthTime:648e5,harvestQuantity:{min:1,max:2},grottoLevelRequirement:6}}[h];
    return {id:`herb-${M.toLowerCase().replace(/\s+/g,"-")}`, name:M,
            growthTime:E.growthTime, harvestQuantity:E.harvestQuantity,
            rarity:h, grottoLevelRequirement:E.grottoLevelRequirement}
  }
  · 入参 M = 灵草名（字符串），h = 稀有度（普通/稀有/传说/仙品），默认 "普通"。
  · 返回对象含 id/name/growthTime/harvestQuantity/rarity/grottoLevelRequirement，
    与 `wn` 条目**同构**，收获成功路径只读 `_.name`（描述）与 `_.rarity`（道具稀有度），可复用。
  · **幂等**：`id` 仅由名字决定（中文 toLowerCase 无副作用、无空白符），同名每次同 id 同属性。
  · `f` 与 `j` 是 `function mk({...}){const c=…,d=…,u=…,f=…,v=…,m=…,j=…,b=…}` 同一 const 声明链里的
    兄弟绑定 ⇒ `j` 内可直接引用 `f`（无 TDZ 问题：`j` 仅在用户点击时调用，届时 `f` 已初始化）。
  · `plantedHerbs[]` 条目（种植处 B 对象）只存 `{herbId,herbName,plantTime,harvestTime,
    quantity,isMutated,mutationBonus}` —— **不存 rarity** ⇒ 收获时取不到稀有度，按需求用 "普通"
    （与批量收获 `b` / 自动收获的 `||"普通"` 口径一致）。

==============================================================================
四、改法
==============================================================================
  腿 ①（首选 = 「补上这个道具」）：让收获与种植对称
      j 内四级查找（id → id去herb-前缀 → name → 别名归一）全落空时，**先调 f(__hn,"普通")**
      现场合成灵草定义；合成成功 ⇒ 走**正常收获路径**，进背包为真实道具（不再折算回收）。
      · `_` 由 `const` 改 `let` 以便回填；空名（`__hn===""`）不合成，直接进腿 ②。
      · 合成结果与批量收获 `b`、自动收获的行为**逐字一致**（name=原名，rarity=普通）。

  腿 ②（兜底 = 「不好补就删除这个灵草选项」）：连 f() 都合成不了（名字非法/为空）
      · **删除**整段「配置信息缺失 · 折算回收」分支（红线：不允许存在任何仍会触发折算回收的路径）。
      · 该条目从 `plantedHerbs` 移除（数据层删除「灵草选项」），给一条**中性**日志：
            🍂 灵草【X】已失效，已从灵田移除。      （type="normal"，无灵石补偿、无警告字样）
      · UI 层再补一道过滤：洞府「灵田」列表（`T.plantedHerbs.map(...)`，@1855513）对
        `herbName` 为空/缺失的条目 **返回 null**（不渲染为可操作选项）。
        —— 该处是本作唯一「可操作灵草选项」列表（收获/加速按钮所在）；
           「图鉴（herbarium）」列表实际 `wn.map(...)`（@1872525）遍历的是 20 味正式表，
           旧名/杂名**本就不会出现**，无需额外过滤（已天然过滤）。
      · 过滤用 `return null` 而非 `.filter()`：保留原数组下标 `q`，收获/加速按钮的 `d(q)/m(q)`
        仍指向正确槽位。

  腿 ③（把 5 个名字补进 `wn` 正式灵草表）：**本环补 0 个**，逐个结论见 §五。
      依据需求「语义明确、不与现行物品冲突」两条同时满足才补；5 个名字**无一同时满足**，
      故一律不补，全部交由腿 ① 的合成兜底（= 需求「补上这个道具」已由腿 ① 对**任意**名字达成）。
      · 额外理由：`wn.length` 被图鉴进度（`已收集 / wn.length`、`% 完成`）与「已收集的灵草」
        网格直接使用；向 `wn` 增条目会把进度分母 20→N，属可见副作用，非必要不动。

==============================================================================
五、5 个旧名逐个结论（本环复核实测）
==============================================================================
  · 天灵草   —— **不补 wn**。它是**现行商店灵草**：`ys("天灵草",35)||{name:"天灵草",cost:35,
                item:{name:"天灵草",type:H.Herb,description:"珍贵的灵草，可用于炼制高级丹药。",
                quantity:1,rarity:"稀有"}}`（@1599530）。与 wn 的 `天灵果(spirit-fruit)`
                并非同物（名字不同）。名字与现行商品/系统重名，且补 wn 会改图鉴分母 ⇒ 有冲突，不补。
                靠腿 ①：种植/收获均合成同名 `herb-天灵草`，往返一致。
  · 雪莲花   —— **不补 wn**。它是**现行抽奖物品**：`{id:"lottery-material-snow-lotus",
                name:"雪莲花",type:"item",rarity:"稀有",weight:3,value:{item:{name:"雪莲花",
                type:H.Herb,description:"生长在极寒之地的灵花，药效极强",quantity:2,rarity:"稀有"}}}`
                （@470991）。与现行物品重名，wn 亦无「雪莲」系灵草 ⇒ 有冲突，不补。靠腿 ①。
  · 星辰草   —— **不补 wn**。wn 无「星辰」系灵草（`星辰石` 是炼器材料）。该名是**随机词缀生成**
                （herbEffects 含「星辰」+ herbTypes 含「草」），非设计品种，语义不明确 ⇒ 不补。靠腿 ①。
  · 凤羽草   —— **不补 wn**。同上（herbEffects 含「凤羽」，`凤羽` 亦为 materialBases 材料关键词）。
  · 灵凤羽草 —— **不补 wn**。同上（稀有前缀「灵」+「凤羽」+「草」）。
  ⇒ 结论：腿 ③ = 补 0 个；5 个名字全部由腿 ① 的合成兜底覆盖，不再有折算回收。

==============================================================================
六、锚点（对 build/assets/index-v2926-20261006.js 字符级实测）
==============================================================================
  R1_OLD  count==1（470 chars）→ 打后 0
  R2_OLD  count==1（ 65 chars）→ 打后 0
  ★ bundle 内本块中文是**裸中文**（非 \uXXXX）：`\u6298\u7b97\u56de\u6536` 形态 count==0，
    `折算回收` 形态 count==1 ⇒ 锚点采用实际存在的裸中文形态（本批踩过的坑）。
  ★ ASCII 说明（如实登记）：R2 锚点 = 纯 ASCII（65 chars）。R1 锚点**含裸中文**——因为它要
    删除的正是「⚠️ 灵草【…】的配置信息缺失…折算回收…」这串裸中文，而 Python 的 replace 是
    **连续区间**替换，无法在绕开这串中文的同时把它删掉（\uXXXX 转义形态在 bundle 里 count==0，
    不匹配）；故 R1 锚点只能采用实际存在的裸中文形态，这是本环唯一无法纯 ASCII 化的锚点。
    同理，少数 gate/冻结针脚（折算回收 / 配置信息缺失 / 成功批量收获 / f=(M,h="普通")=> /
    rarity:(g==null?void 0:g.rarity)||"普通" / 已失效，已从灵田移除）也含裸中文，均按 bundle 实态选取。
  冻结（对**原件**校验，count 必须 == 1）：
      const __hn=String(N.herbName==null?"":N.herbName);
      const __hnc=__halias[__hn]||__hn;
      ||wn.find(Q=>Q.name===__hnc);
      wn=[{id:"spirit-grass"
      const __halias={
      [r169herb]                                     ← 一环幂等标记仍在
      f=(M,h="普通")=>                               ← 合成函数未动
      const C=N.isMutated&&N.mutationBonus?…:N.quantity,   ← 收获成功路径未动
      q.includes(N.herbName)||q.push(N.herbName)      ← 图鉴记录未动
      const Q=wn.find(B=>B.id===D.herbId)             ← 批量收获未动
      成功批量收获                                     ← 批量收获文案未动
      rarity:(g==null?void 0:g.rarity)||"普通"          ← 自动收获未动
  打后：折算回收==0 · 配置信息缺失==0 · h.spiritStones+__sv==0 · R1_OLD==0 · R2_OLD==0
        [r169bherb]==1 · R1_NEW==1 · R2_NEW==1

==============================================================================
七、契约（照 localtest/yl_r169_ext.py）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + f() 逻辑探针）。
  · 二进制读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 <src>.bak-r169b-<时刻>。
  · 幂等：产物已含标记 `[r169bherb]` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r169bherb]'

# --------------------------------------------------------------------------- 替换项

# 腿 ①+②：收获 j 的四级查找 + 「配置信息缺失·折算回收」整段删除，改为「合成兜底 + 中性移除」。
# 锚点含裸中文（bundle 实际形态），见文件头 §六。
R1_OLD = (
    'const _=wn.find(Q=>Q.id===N.herbId)'
    '||wn.find(Q=>Q.id===String(N.herbId==null?"":N.herbId).replace(/^herb-/,""))'
    '||wn.find(Q=>Q.name===N.herbName)||wn.find(Q=>Q.name===__hnc);'
    'if(!_){const __sv=Math.max(100,N.quantity*300);E.splice(M,1);'
    'const __msg=`\u26a0\ufe0f \u7075\u8349\u3010${N.herbName}\u3011\u7684\u914d\u7f6e\u4fe1\u606f\u7f3a\u5931'
    '\uff0c\u5df2\u6309 ${__sv.toLocaleString()} \u7075\u77f3\u6298\u7b97\u56de\u6536'
    '\uff08\u6bcf\u4e2a 300 \u7075\u77f3\uff09\u3002`;'
    'return a(__msg,"warning"),l&&l({text:__msg,type:"warning"}),'
    '{...h,spiritStones:h.spiritStones+__sv,grotto:{...R,plantedHerbs:E,lastHarvestTime:k}}}'
)

R1_NEW = (
    'let _=wn.find(Q=>Q.id===N.herbId)'
    '||wn.find(Q=>Q.id===String(N.herbId==null?"":N.herbId).replace(/^herb-/,""))'
    '||wn.find(Q=>Q.name===N.herbName)||wn.find(Q=>Q.name===__hnc);'
    'if(!_&&__hn){try{_=f(__hn,"\u666e\u901a")}catch(__e){_=null}}'
    'if(!_){E.splice(M,1);'
    'const __msg2=`\U0001f342 \u7075\u8349\u3010${__hn||"\u672a\u77e5"}\u3011'
    '\u5df2\u5931\u6548\uff0c\u5df2\u4ece\u7075\u7530\u79fb\u9664\u3002`;'
    'return a(__msg2,"normal"),l&&l({text:__msg2,type:"normal"}),'
    '{...h,grotto:{...R,plantedHerbs:E,lastHarvestTime:k}}}'
    '/*[r169bherb]*/'
)

# 腿 ②：洞府「灵田」列表（唯一可操作灵草选项）过滤掉 herbName 为空的失效条目。
R2_OLD = 'T.plantedHerbs.map((g,q)=>{const w=Date.now(),A=w>=g.harvestTime,'
R2_NEW = ('T.plantedHerbs.map((g,q)=>{'
          'const __ghn=String(g.herbName==null?"":g.herbName);if(!__ghn)return null;'
          'const w=Date.now(),A=w>=g.harvestTime,')

REPS = [
    ('R169b-1 收获路径对称化（f() 合成兜底 + 中性移除，删折算回收）', R1_OLD, R1_NEW),
    ('R169b-2 灵田列表过滤失效条目', R2_OLD, R2_NEW),
]

# 冻结针脚：本环只动上面两处，下列既有形态必须逐字在位（对**原件**校验）
FREEZE = [
    ('const __hn=String(N.herbName==null?"":N.herbName);', 1),   # 空名安全化未动
    ('const __hnc=__halias[__hn]||__hn;', 1),                    # 一环别名归一未动
    ('||wn.find(Q=>Q.name===__hnc);', 1),                        # 第四级别名兜底仍在
    ('wn=[{id:"spirit-grass"', 1),                               # wn 20 味表本体未动
    ('const __halias={', 1),                                     # 一环别名表仍在
    ('[r169herb]', 1),                                           # 一环幂等标记仍在
    ('f=(M,h="普通")=>', 1),                                     # 种植合成函数未动
    ('const C=N.isMutated&&N.mutationBonus?Math.floor(N.quantity*N.mutationBonus):N.quantity,', 1),
    ('q.includes(N.herbName)||q.push(N.herbName)', 1),           # 图鉴记录未动
    ('const Q=wn.find(B=>B.id===D.herbId)', 1),                  # 批量收获未动
    ('成功批量收获', 1),                                          # 批量收获文案未动
    ('rarity:(g==null?void 0:g.rarity)||"普通"', 1),              # 自动收获未动
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R169b·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r169bherb] 恰好 1 处'),
        ('R169b·收获已对称化', R1_NEW, 1, '==', '合成兜底 + 中性移除，恰好 1 处'),
        ('R169b·灵田过滤已注入', R2_NEW, 1, '==', '灵田列表空名过滤，恰好 1 处'),
        ('R169b·★折算回收已清零', '折算回收', 0, '==', '红线：不得再存在折算回收字样'),
        ('R169b·★配置缺失文案清零', '配置信息缺失', 0, '==', '红线：不得再存在该警告'),
        ('R169b·★灵石补偿已清零', 'h.spiritStones+__sv', 0, '==', '不再发放折算灵石'),
        ('R169b·合成兜底唯一', 'if(!_&&__hn){try{_=f(__hn,"普通")}catch(__e){_=null}}', 1, '==',
         'f() 合成兜底恰好 1 处'),
        ('R169b·let 化查找唯一', 'let _=wn.find(Q=>Q.id===N.herbId)', 1, '==', '查找改为可回填'),
        ('R169b·旧 const 查找已消失', 'const _=wn.find(Q=>Q.id===N.herbId)', 0, '==', ''),
        ('R169b·旧兜底块已消失', R1_OLD, 0, '==', '整段折算回收已删除'),
        ('R169b·旧UI锚已消失', R2_OLD, 0, '==', '灵田旧渲染头已被替换'),
        ('R169b·中性提示已注入', '已失效，已从灵田移除', 1, '==', '中性文案恰好 1 处'),
        ('R169b·批量收获未受影响', '成功批量收获', 1, '==', ''),
        ('R169b·自动收获未受影响', 'rarity:(g==null?void 0:g.rarity)||"普通"', 1, '==', ''),
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
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
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


def _f_probe(patched_text):
    """从补丁后产物里抽出**真实** f() 定义，用 node 验证其确定性/字段/空名行为。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。
    """
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    i = patched_text.find('f=(M,h="普通")=>{')
    if i < 0:
        return False, 'f() 定义未找到'
    j = patched_text.find(',v=M=>{', i)
    if j < 0:
        return False, 'f() 结束边界未找到'
    fdef = 'const ' + patched_text[i:j] + ';'
    js = fdef + r'''
const A=f("天灵草","普通"),B=f("天灵草","普通"),C=f("星辰草","普通"),D=f("雪莲花","普通");
if(A.id!==B.id||A.id!=="herb-天灵草")throw new Error("id 不稳定: "+A.id);
if(A.name!=="天灵草"||A.rarity!=="普通")throw new Error("字段异常");
if(C.id!=="herb-星辰草")throw new Error("星辰草 id: "+C.id);
if(D.name!=="雪莲花")throw new Error("雪莲花 name: "+D.name);
if(!f("","普通"))throw new Error("空名应可合成（由 &&__hn 守卫拦截）");
console.log("f-probe OK");
'''
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
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → f() 逻辑探针。"""
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r169b] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r169b] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r169b] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r169b] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r169b] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r169b] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _f_probe(out)
    if ok is False:
        print('[r169b] SELFTEST FAIL f-probe: ' + pmsg)
        return 1
    print('[r169b] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s; %s'
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
        print('[r169b] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r169b] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r169b] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r169b] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r169b] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r169b] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-36s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r169b-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r169b] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-36s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
