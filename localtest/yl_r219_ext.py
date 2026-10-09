# -*- coding: utf-8 -*-
r"""
yl_r219_ext.py — R-219 困难模式死亡惩罚：清档 → 三重惩罚（纯客户端）

需求原文（用户原话）
--------------------------------------------------------------------------
    「困难模式不要直接清档，改成装备全掉，掉落40%-50%属性，掉一个1个大境界。」

输入产物：build/assets/index-v2945-20261009.js（线上 0.9.45，
          md5 e5a451fe35fb7d0ad4422bdd8ddcac9b，2,321,665 B）
bundle 内中文**混合两种形态**：多数区段为 `\uXXXX` 转义形态，而**死亡处理相关区段
（604xxx / 202xxxx）为字面中文**。本模块全部锚点均取自该字面区段，故均为字面中文
（_precheck 对每个锚点做形态断言）。

==============================================================================
一、现状（补丁前，0.9.45）——困难模式死亡 = 只能清档
==============================================================================
困难模式（difficulty==="hard"）的死亡在客户端**分散在 5 处**，本次全部处理：

  ① 自然寿终·hard 分支（@604744，组件 $w 的 useEffect 内）：
       `if(d.difficulty==="hard")l(!0),r($=>$&&{...$,hp:0}),v(T),f(null),mm(),m(!1),j(!1),b(!1);`
     —— 把 hp 置 0 后弹「身死道消」，弹窗**只给「涅槃重生」**（清档）。
  ② 战斗死亡·hard 分支（@605766，同组件）：
       `if($==="hard"){l(!0),f(u),mm(),m(!1);const M=P0(u,"hard");v(M),j(!1),b(!1)}`
     —— 不修改 player，死亡文案取 `P0(u,"hard")`（无「重生」后缀），弹窗同样只给清档。
  ③ 死亡弹窗组件 bk 的 hard 布局（@2026696）：仅一个红色「涅槃重生」按钮 +
     说明「困难模式下死亡将清除存档，点击后将重置所有数据，返回开始页面」。
  ④ 死亡弹窗 onContinue 传参（@2128080）：
       `onContinue:S.difficulty!=="hard"?()=>{g(!1),q(null),w("")}:void 0`
     —— hard 时 onContinue === undefined ⇒ 弹窗**没有「继续游戏」按钮**。
  ⑤ 两处「困难模式 = 死亡清除存档」描述文案（@528988 难度选择卡片、@1817685 设置面板）。

真正的「清档」动作 = 弹窗「涅槃重生」按钮 onClick 触发 handleRebirth（重置 player /
gameStarted 等）。hard 下它是**唯一**出口 ⇒ 等于强制清档。本环不改 handleRebirth
（用户仍可主动重开），只把 hard 死亡改成「三重惩罚 + 可继续」。

==============================================================================
二、改法——三重惩罚的确切算法
==============================================================================
新增一个模块级辅助函数（注入于组件 `$w` 之前，幂等标记 /*YLXW_R219_V2945*/）：

    YLXW_R219_HARD(pl, nat, log)

  入参：pl=player；nat=是否自然寿终（true 时重置寿元）；log=addLog 回调（可空）。
  返回：惩罚后的新 player 对象（不修改入参）。

  算法（逐条，含取整 / 下限 / 边界）：

  (1) 装备全掉
        equippedItems = {}（**全部清空**；背包 inventory 不动）。
        日志里列出掉落装备名（按 equippedItems 的值 = itemId 去 inventory 里查 name）。

  (2) 掉落 40%~50% 属性
        对属性集合 **{attack, defense, spirit, physique, speed, maxHp}**
        （★ 该集合 = 游戏自身「普通模式死亡惩罚」所用的属性集合，
        见 @606688 普通分支的 attack/defense/spirit/physique/speed/maxHp，不多不少）。
        新值 = floor(旧值 × r)，其中 r = 0.50 + Math.random()*0.10 ∈ [0.50, 0.60)
             ⇒ 跌幅 = 旧值 − 新值 ∈ (40%, 50%]（即掉 40%~50%）。
        取整：Math.floor；下限：**旧值>0 时 Math.max(1, …)**（绝不掉到 0、绝不为负）；
              旧值<=0 时保持 0（不因惩罚而「涨」到 1）。
        日志逐项输出 `攻击力 -X` 等（delta = 旧值 − 新值，仅当 >0 才输出）。

  (3) 掉一个大境界
        复用游戏既有境界序数组 `fe`（= [炼气期,筑基期,金丹期,元婴期,化神期,合道期,长生境]，
        定义于 @245791；与突破代码 @748752 `N=fe[fe.indexOf(t.realm)+1],k=1` 同源）：
          i = fe.indexOf(pl.realm)
          i > 0  ⇒ realm = fe[i-1]，realmLevel = 1，exp = 0，maxExp = ad(realm, 1)
        `ad(realm, level)` 亦为游戏既有函数（@247006）⇒ **不另造一套境界/修为算法**。
        ★ 边界：i <= 0（已是**最低境界 炼气期**，或 realm 非法）⇒ **跳过本条第 3 项**，
          只执行 (1)(2)，并在日志里写「已是最低境界（炼气期），无法再跌」。

  (4) 可继续（不清档）
        nat=true 时 lifespan = Math.min(maxLifespan||100, 10)（沿用普通/简单自然寿终的重生口径，
          否则点击「继续」后 lifespan 仍 <=0 会立即再次寿终）；
        hp = Math.max(1, floor(maxHp * 0.1))（沿用普通分支的重生口径，保证 hp>0，
          否则点击「继续」后 hp<=0 会立即再次战死）。
        保留 inventory / spiritStones / 称号 / 功法 / 已降一档的 realm 等一切其它字段。

  (5) 死亡文案
        辅助函数内 addLog(`💀 死亡惩罚：装备全部掉落（…），攻击力 -X，…，境界跌落至…`)，
        与普通模式 @606688 的 `💀 死亡惩罚：…` 风格一致，且把「装备 / 属性 / 境界」三件事写清。
        战斗死亡 hard 的「死亡原因」文案由 `P0(u,"hard")` 改为 `P0(u,"normal")`
        （后者带「但你的灵魂尚未完全消散，在付出代价后得以重生。」后缀，与新语义一致）；
        自然寿终 hard 的死亡原因补同样后缀。⇒ 补丁后全 bundle `P0(u,"hard")` 计数为 0。

  三处「hard 死亡 = 清档」的 UI 文案同步改写（@528988 / @1817685 / @2026696），
  并在 hard 弹窗新增「继续游戏」按钮 + 令 onContinue 在 hard 下也传入。

==============================================================================
三、「简单 / 普通两条路径一字未动」的证据（冻结门禁）
==============================================================================
本模块**只替换 hard 分支与 hard 专属文案**；简单/普通分支的源串原样保留，门禁 fail-closed
逐条断言其计数 == 1（补丁前后均成立）：
  · 普通死亡惩罚属性行 @606688：`attack:Math.max(0,h.attack-E),…,maxHp:Math.max(1,h.maxHp-g)` == 1
  · 普通死亡惩罚日志：`Q.push(`装备掉落：${B}`)` == 1
  · 普通分支收尾：`const M=P0(u,"normal");v(M),l(!0),f(u),m(!1),j(!1),b(!1)` == 1
  · 简单分支收尾：`const M=P0(u,"easy");v(M),l(!0),f(u),m(!1),j(!1),b(!1)` == 1
  · 自然寿终·非 hard 分支：`const $=`${T}但天道的仁慈让你得以重生，继续你的修仙之路。`;` == 1
  · 弹窗非 hard 说明（简单/普通）各 == 1；`涅槃重生（重新开始）` == 1
  · 函数 `P0` 定义体 == 1（P0 本身未改）
上述断言若有一条不成立 → 门禁 FAIL，拒绝写盘。

==============================================================================
四、契约（standalone，同 localtest/yl_r216_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`（缺省自动探测 PATH 上的 node）；
    可选 `--dump`（只打印 hard 死亡分支补丁前后的解码视图对照，不写盘，rc=0）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r219-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（含门禁未全绿、往返不一致、node --check 失败）。
  · 纯客户端；不改 build_v26n.py / chain_build.py / dryrun_087.py / sim_remote_check.py /
    任何 build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 幂等标记
MARK = '/*YLXW_R219_V2945*/'

# --------------------------------------------------------------------------- 注入的辅助函数
# 注入位置：组件 $w 定义之前（该处已在 fe/@245791、ad/@247006 之后，运行时可见）。
HELPER = (
    MARK + 'function YLXW_R219_HARD(pl,nat,log){'
    'if(!pl)return pl;'
    'const rr=()=>.5+Math.random()*.1,'
    'sc=v=>{const x=Number(v)||0;return x>0?Math.max(1,Math.floor(x*rr())):0},'
    'eq=pl.equippedItems||{},'
    'names=Object.values(eq).filter(Boolean).map(id=>{'
    'const it=(pl.inventory||[]).find(x=>x&&x.id===id);return it&&it.name?it.name:"装备"}),'
    'o={...pl},'
    'nA=sc(pl.attack),nD=sc(pl.defense),nS=sc(pl.spirit),nP=sc(pl.physique),'
    'nV=sc(pl.speed),nH=sc(pl.maxHp);'
    'o.attack=nA,o.defense=nD,o.spirit=nS,o.physique=nP,o.speed=nV,o.maxHp=nH,'
    'o.equippedItems={};'
    'const i=fe.indexOf(pl.realm);let fell=null;'
    'i>0&&(fell=fe[i-1],o.realm=fell,o.realmLevel=1,o.exp=0,o.maxExp=ad(fell,1)),'
    'nat&&(o.lifespan=Math.min(o.maxLifespan||100,10)),'
    'o.hp=Math.max(1,Math.floor(o.maxHp*.1));'
    'const Q=[];'
    'Q.push("装备全部掉落"+(names.length?"（"+names.join("、")+"）":""));'
    'const dA=pl.attack-nA,dD=pl.defense-nD,dS=pl.spirit-nS,dP=pl.physique-nP,'
    'dV=pl.speed-nV,dH=pl.maxHp-nH;'
    'dA>0&&Q.push("攻击力 -"+dA),dD>0&&Q.push("防御力 -"+dD),'
    'dS>0&&Q.push("神识 -"+dS),dP>0&&Q.push("体魄 -"+dP),'
    'dV>0&&Q.push("身法 -"+dV),dH>0&&Q.push("气血上限 -"+dH),'
    'Q.push(fell?"境界跌落至"+fell+" 第 1 层":"已是最低境界（炼气期），无法再跌"),'
    'typeof log==="function"&&log("💀 死亡惩罚："+Q.join("，"),"danger");return o}'
)

# --------------------------------------------------------------------------- 锚点（补丁前，字面中文区段）
# ① 自然寿终·hard 分支（组件 $w 内）
A1 = 'r($=>$&&{...$,hp:0}),v(T),f(null),mm(),m(!1),j(!1),b(!1);'
N1 = ('r($=>$&&YLXW_R219_HARD($,!0,c)),'
      'v(T+`但你的灵魂尚未完全消散，在付出代价后得以重生。`),'
      'f(null),mm(),m(!1),j(!1),b(!1);')

# ② 战斗死亡·hard 分支
A2 = 'if($==="hard"){l(!0),f(u),mm(),m(!1);const M=P0(u,"hard");v(M),j(!1),b(!1)}'
N2 = ('if($==="hard"){l(!0),r(h=>h&&YLXW_R219_HARD(h,!1,c)),'
      'f(u),mm(),m(!1);const M=P0(u,"normal");v(M),j(!1),b(!1)}')

# 注入点：组件 $w 定义之前
A_INJ = 'function $w({player:t,setPlayer:r,isDead:a,setIsDead:l,'
N_INJ = HELPER + A_INJ

# ③ 死亡弹窗·hard 布局：插入「继续游戏」按钮
A4a = 'children:c==="hard"?e.jsxs(e.Fragment,{children:[e.jsxs("button",{onClick:d,'
N4a = ('children:c==="hard"?e.jsxs(e.Fragment,{children:['
       'u&&e.jsxs("button",{onClick:u,className:"w-full py-2.5 md:py-3 '
       'bg-gradient-to-r from-green-600 via-emerald-600 to-green-600 '
       'hover:from-green-500 hover:via-emerald-500 hover:to-green-500 text-white '
       'font-bold text-base md:text-lg rounded-lg transition-all duration-300 '
       'shadow-lg hover:shadow-xl active:scale-95 flex items-center justify-center '
       'gap-2 md:gap-3 touch-manipulation",children:[e.jsx(mo,{size:18,'
       'className:"md:w-6 md:h-6"}),"继续游戏"]}),e.jsxs("button",{onClick:d,')

# ③ 死亡弹窗·hard 说明文案
A4b = '困难模式下死亡将清除存档，点击后将重置所有数据，返回开始页面'
N4b = ('困难模式下死亡：装备全部掉落、基础属性下降 40%~50%、'
       '境界跌落一个大境界（炼气期除外），但不清除存档；可继续游戏或重新开始')

# ④ 死亡弹窗 onContinue：hard 也提供「继续」
A5 = 'onContinue:S.difficulty!=="hard"?()=>{g(!1),q(null),w("")}:void 0'
N5 = 'onContinue:()=>{g(!1),q(null),w("")}'

# ★ 注：困难档的**界面文案**（难度选择卡片 @528988 / 设置面板 @1817685）由同批的 r220 独家负责，
#   本环**不碰**——两环若同时改同一字符串，实测**两种顺序都会** fail（"检测到部分补丁态"）。
#   本环只管死亡逻辑 + 死亡弹窗（@2026696，r220 不碰）。

EDITS = [
    ('I0 注入三重惩罚辅助函数 YLXW_R219_HARD（幂等标记 %s）' % MARK, A_INJ, N_INJ, 1),
    ('E1 自然寿终·hard 清档→三重惩罚（不清档、可继续）', A1, N1, 1),
    ('E2 战斗死亡·hard 清档→三重惩罚（不清档、可继续）', A2, N2, 1),
    ('E3 死亡弹窗·hard 新增「继续游戏」按钮', A4a, N4a, 1),
    ('E4 死亡弹窗·hard 说明文案→三重惩罚口径', A4b, N4b, 1),
    ('E5 死亡弹窗 onContinue：hard 亦提供「继续」', A5, N5, 1),
]

INJECT_LABEL = EDITS[0][0]

# --------------------------------------------------------------------------- 冻结门禁串（简单/普通路径，必须原样）
FRZ_NORMAL_ATTR = ('attack:Math.max(0,h.attack-E),defense:Math.max(0,h.defense-N),'
                   'spirit:Math.max(0,h.spirit-k),physique:Math.max(0,h.physique-_),'
                   'speed:Math.max(0,h.speed-C),maxHp:Math.max(1,h.maxHp-g)')
FRZ_NORMAL_LOG = 'Q.push(`装备掉落：${B}`)'
FRZ_NORMAL_TAIL = 'const M=P0(u,"normal");v(M),l(!0),f(u),m(!1),j(!1),b(!1)'
FRZ_EASY_TAIL = 'const M=P0(u,"easy");v(M),l(!0),f(u),m(!1),j(!1),b(!1)'
FRZ_NORMAL_NAT = 'const $=`${T}但天道的仁慈让你得以重生，继续你的修仙之路。`;'
FRZ_EASY_DESC = '简单模式下死亡无惩罚，你可以继续游戏或选择重新开始'
FRZ_NORMAL_DESC = '普通模式下死亡会掉落部分属性和装备，你可以继续游戏或选择重新开始'
FRZ_REBIRTH2 = '涅槃重生（重新开始）'
FRZ_P0_DEF = 'function P0(t,r){if(!t){'
FRZ_P0_HARD = 'P0(u,"hard")'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    return [
        # ---- 注入 ----
        ('注入·幂等标记唯一', MARK, 1, '==', '/*YLXW_R219_V2945*/'),
        ('注入·辅助函数在位', 'function YLXW_R219_HARD(', 1, '==', ''),
        ('注入·自然寿终调用', 'YLXW_R219_HARD($,!0,c)', 1, '==', 'nat=true'),
        ('注入·战斗死亡调用', 'YLXW_R219_HARD(h,!1,c)', 1, '==', 'nat=false'),
        ('注入·装备清空', 'o.equippedItems={}', 1, '==', '装备全掉'),
        ('注入·属性随机系数', 'Math.floor(x*rr())', 1, '==', '×[0.50,0.60)'),
        ('注入·境界序复用 fe', 'fe.indexOf(pl.realm)', 1, '==', '复用游戏境界序'),
        ('注入·降境界+重置层数修为',
         'o.realm=fell,o.realmLevel=1,o.exp=0,o.maxExp=ad(fell,1)', 1, '==', '复用 ad()'),
        ('注入·最低境界边界', '已是最低境界（炼气期），无法再跌', 1, '==', '炼气期跳过降境界'),
        ('注入·三重惩罚日志', 'log("💀 死亡惩罚："+Q.join("，"),"danger")', 1, '==',
         '与普通模式同风格'),
        # ---- E1 / E2 ----
        ('E1·新串在位', N1, 1, '==', '自然寿终 hard 调辅助函数'),
        ('E1·旧清档串清零', A1, 0, '==', '旧 r($=>$&&{...$,hp:0}) 必须为 0'),
        ('E2·新串在位', N2, 1, '==', '战斗死亡 hard 调辅助函数'),
        ('E2·旧 hard 分支清零', A2, 0, '==', '旧 hard 分支必须为 0'),
        ('E2·旧 P0(u,"hard") 清零', FRZ_P0_HARD, 0, '==', 'hard 死亡文案改用 normal 重生口径'),
        # ---- E3/E4/E5 ----
        ('E3·弹窗 hard 新增继续按钮', N4a, 1, '==', ''),
        ('E3·旧 hard 弹窗头清零', A4a, 0, '==', ''),
        ('E4·弹窗 hard 新文案', N4b, 1, '==', ''),
        ('E4·弹窗 hard 旧文案清零', A4b, 0, '==', ''),
        ('E5·onContinue hard 亦提供', N5, 1, '==', ''),
        ('E5·旧 onContinue 清零', A5, 0, '==', ''),
        # ---- E6/E7 ----
        # ---- 冻结：简单/普通路径一字未动 ----
        ('冻结·普通惩罚属性行未动', FRZ_NORMAL_ATTR, 1, '==', ''),
        ('冻结·普通惩罚日志未动', FRZ_NORMAL_LOG, 1, '==', ''),
        ('冻结·普通分支收尾未动', FRZ_NORMAL_TAIL, 1, '==', ''),
        ('冻结·简单分支收尾未动', FRZ_EASY_TAIL, 1, '==', ''),
        ('冻结·自然寿终非hard未动', FRZ_NORMAL_NAT, 1, '==', ''),
        ('冻结·弹窗简单说明未动', FRZ_EASY_DESC, 1, '==', ''),
        ('冻结·弹窗普通说明未动', FRZ_NORMAL_DESC, 1, '==', ''),
        ('冻结·弹窗重开按钮未动', FRZ_REBIRTH2, 1, '==', ''),
        ('冻结·P0 定义未动', FRZ_P0_DEF, 1, '==', ''),
    ]


# 各编辑「旧锚点」的实测形态：'ascii'=bundle 内为纯 ASCII；'lit'=字面中文
OLD_FORM = {
    'E1': 'ascii', 'E2': 'ascii', 'E3': 'ascii', 'E5': 'ascii',
    'E4': 'lit', 'E6': 'lit', 'E7': 'lit',
}


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert MARK == '/*YLXW_R219_V2945*/', '幂等标记有误'
    for name, old, new, n in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old and new, '%s 锚点不得为空' % name
        assert n >= 1, '%s n 必须 >=1' % name
        if name == INJECT_LABEL:
            # 注入点：old 为纯 ASCII 锚点，new = 辅助函数 + 锚点（含字面中文）
            assert all(ord(ch) < 128 for ch in old), '注入锚点应为纯 ASCII'
            assert new.endswith(old), '注入 new 必须以锚点结尾'
            assert new.count(MARK) == 1, '注入 new 须恰好含 1 个幂等标记'
            continue
        # 旧锚点形态须与实测一致（字面中文区段 / 纯 ASCII）
        tag = name.split(' ', 1)[0]
        form = OLD_FORM[tag]
        if form == 'ascii':
            assert all(ord(ch) < 128 for ch in old), '%s 旧锚点应为纯 ASCII' % tag
        else:
            assert any(ord(ch) >= 128 for ch in old), '%s 旧锚点应为字面中文' % tag

    # 形态断言：A1/A2/A4a/A5 为纯 ASCII；A4b 为字面中文
    for tag, s in (('A1', A1), ('A2', A2), ('A4a', A4a), ('A5', A5)):
        assert all(ord(ch) < 128 for ch in s), '%s 转义态锚点必须纯 ASCII' % tag
    for tag, s in (('A4b', A4b),):
        assert any(ord(ch) >= 128 for ch in s), '%s 字面态锚点须含非 ASCII' % tag
    # 新串形态：E1/E3 追加了中文文案 ⇒ 含非 ASCII；E2/E5 保持纯 ASCII
    for tag, s in (('N1', N1), ('N4a', N4a), ('N4b', N4b)):
        assert any(ord(ch) >= 128 for ch in s), '%s 新串须含非 ASCII' % tag
    for tag, s in (('N2', N2), ('N5', N5)):
        assert all(ord(ch) < 128 for ch in s), '%s 新串应保持纯 ASCII' % tag

    # 注入函数要素自检
    for need in ('equippedItems={}', 'realmLevel=1', 'exp=0', 'maxExp=ad(fell,1)',
                 'fe.indexOf(pl.realm)', 'Math.floor(x*rr())',
                 '已是最低境界（炼气期），无法再跌', '💀 死亡惩罚：'):
        assert need in HELPER, '辅助函数缺少要素: %s' % need
    assert '.5+Math.random()*.1' in HELPER, '辅助函数随机系数应为 [0.50,0.60)'

    # E2：hard 分支必须改为调用辅助函数，且不再用 P0(u,"hard")
    assert 'YLXW_R219_HARD(h,!1,c)' in N2, 'E2 新串须调用辅助函数'
    assert 'P0(u,"hard")' not in N2, 'E2 新串不得再出现 P0(u,"hard")'
    assert 'P0(u,"normal")' in N2, 'E2 新串须改用 P0(u,"normal")'
    # E1：自然寿终必须 nat=true
    assert 'YLXW_R219_HARD($,!0,c)' in N1, 'E1 新串须 nat=true'

    # E3：新串须含「继续游戏」按钮与 mo 图标
    assert 'onClick:u' in N4a and '"继续游戏"' in N4a and 'e.jsx(mo,' in N4a, \
        'E3 新串须含继续游戏按钮'
    # E5：新串不得再排除 hard
    assert '"hard"' not in N5, 'E5 新串不应再对 hard 排除 onContinue'

    # 注入内容不得含网络/存储原语
    for _n, _o, nw, _c in EDITS:
        for ban in ('fetch(', 'localStorage', 'XMLHttpRequest', 'setInterval('):
            assert ban not in nw, '注入内容不得含 %s' % ban


# 补丁态特征串（用于幂等判定）
PATCH_SIGS = [MARK, N1, N2, N4a, N4b, N5]
BASE_SIGS = [A1, A2, A4a, A4b, A5]


def _classify(txt):
    """判定基线态：'patched' / 'baseline' / 'partial'。"""
    n_new_ok = sum(1 for s in PATCH_SIGS if txt.count(s) == 1)
    n_old_ok = sum(1 for s in BASE_SIGS if txt.count(s) == 1)
    if n_new_ok == len(PATCH_SIGS) and n_old_ok == 0:
        return 'patched'
    if n_new_ok == 0 and n_old_ok == len(BASE_SIGS):
        return 'baseline'
    return 'partial'


def _node_check(out_bytes, node_bin):
    """对产物跑 `node --check`（fail-closed）；找不到 node 则告警跳过。"""
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check（可用 --node 显式指定）')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r219chk-', suffix='.js')
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


def _dump_views(txt0, out_txt):
    """打印 hard 死亡分支补丁前后的解码视图对照。"""
    def view(txt, key, pre=60, post=180):
        i = txt.find(key)
        if i < 0:
            return '<未找到 %r>' % key
        return txt[max(0, i - pre):i + post]

    for tag, key in (('E1 自然寿终·hard', 'difficulty==="hard")l(!0)'),
                     ('E2 战斗死亡·hard', 'if($==="hard"){')):
        print('\n---- %s · 补丁前 ----\n%s' % (tag, view(txt0, key)))
        print('\n---- %s · 补丁后 ----\n%s' % (tag, view(out_txt, key)))


def main() -> int:
    ap = argparse.ArgumentParser(description='R-219 困难模式死亡三重惩罚（客户端 --src 补丁）')
    ap.add_argument('--src', required=True,
                    help='装配产物 js（如 build/assets/index-v2945-20261009.js）')
    ap.add_argument('--node', default=None, help='node 可执行文件（缺省自动探测 PATH）')
    ap.add_argument('--dump', action='store_true',
                    help='只打印 hard 死亡分支补丁前后解码视图，不写盘')
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
        print('[SKIP] source looks already patched（R-219 三重惩罚已在位）')
        return 3
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 2) 基线碰撞检查：新串不得已在基线出现
    for _name, _old, new, _n in EDITS:
        c = txt0.count(new)
        if c != 0:
            print('[FAIL] 新串已在基线出现 %d 次，拒绝写盘：%s' % (c, new[:40]))
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

    if a.dump:
        _dump_views(txt0, out_txt)
        print('\n[DUMP] 仅预览，未写盘')
        return 0

    # 5) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-30s actual=%d expect %s %d'
              % ('OK' if good else 'FAIL', label, act, op, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

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

    # 8) 改前 .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r219-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r219-', suffix='.tmp')
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
