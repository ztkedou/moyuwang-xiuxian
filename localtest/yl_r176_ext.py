# -*- coding: utf-8 -*-
r"""
yl_r176_ext.py — R-176（真对象）：抽奖券抽奖「奖品池按玩家境界收敛」（standalone 纯客户端）

需求原文（台账 R-176，逐字）
--------------------------------------------------------------------------
  「抽奖这个是不是以为之前融合了保底因素。设计完全违反了原则：原则是抽奖券抽奖，
    根据等阶绝大多数情况只能抽到比自身高2个大境界的物品，同等阶物品以及低等阶物品。
    比如炼气能抽到筑基的几率已经非常小，金丹的几率几乎微乎其微。再往上一层几率就掉为
    千万分之一。获得的高等阶物品以后不要再折算灵石，就在几率上控制到几乎不可能的状态。」

==============================================================================
零、为什么改客户端（而不是服务端）
==============================================================================
  · 「抽奖券抽奖」= 客户端纯前端逻辑：抽奖执行体 `ck(p).handleDraw(N)`（bundle @1934938），
    全仓**无** `/lottery/draw` 一类服务端端点；券的消耗、奖品入账、奖池全在 bundle 内。
  · 服务端 `srv/index_v28.ts` 里的 `drawAdventureTier` 是**奇遇**（`/api/adventure/draw`，每日 3 次）
    的品阶分布 —— 奇遇 ≠ 抽奖券抽奖，**本环不动服务端**（srv_patch_r176.py 不接 SRV_CHAIN）。

==============================================================================
一、奖品池 ms 的真实结构（本环实测重建 · Node vm 执行真实构造代码）
==============================================================================
  来源：`ms=[...]`（@465075 起）+ 之后 5 组 `cy({type,rarity,count:99,allowDuplicates:false})` 生成段
        （`S3` 装备五类 / `k3` 丹 / `C3` 草 / `E3` 材 / `R3` 合成石）。
  实测重建结果（`ms.length = 1193`；脚本见 §七「实测重建法」）：
      · 装备类（Weapon/Armor/Accessory/Ring/Artifact，来自 `Yr`，`Yr.length = 1356`）：
        每类每稀有度在 7 个境界上**均匀分布**；池内约 900 条，带 `realm`（`WN()` 生成）
        或 `realmRequirement`（静态模板），名字形如 `[炼气期]精铁指环`（与 R-179 日志样例一致）。
      · 境界无关类（无 realm 字段）：灵石 / 修为 / 丹药 / 灵草 / 材料 / 灵宠 / 抽奖券 /
        进阶物品（筑基奇物 ft_40 / 天地精华 hee_40 / 天地之髓 hem_40 / 规则之力 lr_10），共 293 条。
      · 池权重和（按境界桶，实测）：
            炼气期 342.10 | 筑基期 358.625 | 金丹期 344.40 | 元婴期 378.75
            化神期 349.55 | 合道期 386.40 | 长生境 332.05 | 无境界 1151.88
            合计 3643.755
      ⇒ **结论：奖品池确有「境界」维度**（装备类），但**无统一 realm 字段**：
        装备按 realm/realmRequirement/名字 [境界] 前缀判定；其余物品境界无关。

==============================================================================
二、改前抽取逻辑（实测原文）
==============================================================================
  唯一抽样器（权重区间选择，count==1）：
      N=(g,q)=>{if(q>0&&g.length>0){let w=Math.random()*q;for(const A of g)if(w-=A.weight,w<=0)return A}
                return g.length>0?g[0]:null}
  handleDraw 抽取循环（原文）：
      const $=ms.filter(g=>g.rarity!=="普通"),M=ms.filter(g=>g.rarity==="传说"||g.rarity==="仙品"),
            h=ms.reduce((g,q)=>g+q.weight,0),R=$.reduce(...),E=M.reduce(...);
      for(let g=0;g<S;g++){const q=T+g+1,w=q%rk===0&&M.length>0&&E>0,A=q%10===0;
        if(w){...N(M,E)...} else if(A){...N($,R)...} else {...N(ms,h)...}}
      （`rk=50`：每 50 抽保底传说/仙品；每 10 抽保底非普通；其余走全池）
  ⇒ **改前完全不看玩家境界**：炼气期玩家单抽有 **59.12%** 概率抽到越阶物品，
     其中 d>=3（高 3 个大境界以上）占 **39.81%** —— 正是台账所指「设计完全违反了原则」。

==============================================================================
三、新权重表 + 各境界差实测概率表（本环实测）
==============================================================================
  权重表（整数倍率，集中成常量 `YLXW_R176_MUL`，防浮点漂移；下标 = d = 奖品境界序 − 玩家境界序）：
      ┌──────────┬────────────┬──────────────────────────────┐
      │  d       │  倍率       │  语义                          │
      ├──────────┼────────────┼──────────────────────────────┤
      │  d <= 0  │ 10,000,000 │ 主体（同等阶 + 更低 + 境界无关） │
      │  d = 1   │ 10,000     │ 相对 d<=0 ≈ 1e-3（非常小）      │
      │  d = 2   │ 100        │ 相对 d<=0 ≈ 1e-5（微乎其微）    │
      │  d >= 3  │ 1          │ 相对 d<=0 ≈ 1e-7（千万分之一）  │
      └──────────┴────────────┴──────────────────────────────┘
  实测概率表（对真实池 ms，含保底，50 抽周期平均；单位 %）：
      玩家=炼气期  改前: d<=0 9.355 / d=1 9.826 / d=2 9.481 / d>=3 39.815 / 无关 31.523
                   改后: d<=0 22.879 / d=1 0.024033 / d=2 0.000232 / d>=3 0.000010 / 无关 77.097
      玩家=筑基期  改后: d<=0 37.823 / d=1 0.018698 / d=2 0.000205 / d>=3 0.000006 / 无关 62.158
      玩家=金丹期  改后: d<=0 47.616 / d=1 0.017306 / d=2 0.000158 / d>=3 0.000003 / 无关 52.366
      玩家=元婴期  改后: d<=0 55.344 / d=1 0.013470 / d=2 0.000150 / d>=3 0.000001 / 无关 44.642
      玩家=长生境  改后: d<=0 68.477 / 无越阶（其上无境界，不削弱）       / 无关 31.523
  ⇒ 越阶合计：炼气期 59.12% → **0.024%**；d>=3：39.81% → **1.0e-5 %（≈1e-7 相对）**。

  两种解读（本环采用 A）：
      解读 A（采用）：「绝大多数 = 抽到 ≤ 自身境界」；+1 非常小 / +2 微乎其微 / +3+ 千万分之一。
      解读 B（不采用）：按字面「绝大多数只能抽到比自身高 2 个大境界的物品」= 以 d=2 为主体。
         该读法与同句后半「炼气抽筑基已非常小、金丹微乎其微」自相矛盾，
         且会把全池压成"只出高 2 阶"，属用户未要求的重大削弱，风险不对等 ⇒ 不采用。

==============================================================================
四、「越阶 → 折算灵石」兜底：**存在**，本环已改掉
==============================================================================
  唯一出处 = `handleDraw` 入账分支内的 `_ylr` 折算段（本环锚点 C，741 chars，count==1）：
      依据 item 的 realm / realmRequirement / [境界] 名缀推断其境界，若高于玩家境界 ⇒
      `YlxwCvtStones(U,_ylq)` + `YlxwDrawValue(...)` 折算成 灵石 + 修为，并提示
      「感应到【X】蕴含高阶气息，机缘未至，化作 N 灵石 与 M 修为 消散。」后 `continue`（不入包）。
  ⇒ 台账要求「获得的高等阶物品以后不要再折算灵石，就在几率上控制到几乎不可能的状态」：
     **整段删除**（改为不折算）——越阶物品若真被抽到（≈1e-7），按普通路径正常入包，
     走既有 `q=vs(q,U,1,{realm:g.realm,realmLevel:g.realmLevel}),f("获得 X！","gain")`。
     概率压缩由 §三 的倍率表承担（这就是台账「就在几率上控制」的落点）。
  · 未动：抽奖券校验 `lotteryTickets < N`、次数校验、券消耗口径 `lotteryTickets:D-S,...`、
    奖品自身数值、保底逻辑 `q%rk===0 / q%10===0`、入账聚合 `const C=Array.from(_.values())`。
  · `YlxwDrawValue` / `YlxwDrawExpNeed` / `YLXW_DRAW_STONES` 等函数与表**保留在位**（仅不再被本路径调用）。

==============================================================================
五、改动点（3 处就地替换；锚点均对原件 count==1）
==============================================================================
  E1（注入常量与两个纯函数，插在 `YlxwDrawValue` 收尾处）
      锚点 A_OLD（纯 ASCII，40 chars）:
          '  return { stones: stones, exp: exp };\n}'
      A_NEW = A_OLD + 注释块 + `YLXW_R176_MUL` + `YlxwR176RealmIdx(x)` + `YlxwR176Mul(itemIdx,playerIdx)`
      （A_NEW 以 A_OLD 为前缀 ⇒ 补后 A_OLD count 仍为 1，故不设 A_OLD==0 门禁）

  E2（唯一抽样器按境界差重加权）
      锚点 B_OLD（纯 ASCII，126 chars，count==1）:
          'N=(g,q)=>{if(q>0&&g.length>0){let w=Math.random()*q;for(const A of g)'
          'if(w-=A.weight,w<=0)return A}return g.length>0?g[0]:null}'
      B_NEW：签名保持 (g,q)（调用点不变），改为先算 total=Σ weight*YlxwR176Mul(...) 再区间抽样；
             `q` 参数不再使用（保留以零改动调用点）。

  E3（删除越阶折算灵石段）
      锚点 C_OLD（741 chars，count==1；**含 `\uXXXX` 转义形态的裸模板串**）→ C_NEW = `/*[r176lot]*/`

  ★ 幂等标记 `[r176lot]` 在 E1 注释块、E2、E3 各 1 处 ⇒ 补后 count==3。
  ★ 中文形态（本环实测）：E1/E2 锚点**纯 ASCII**；E3 锚点所在块的中文在 bundle 内为
    `\u611f\u5e94\u5230` 这类**转义形态**（位于 JS 模板字符串内），故 C_OLD 用 Python raw 串
    写 `\uXXXX` 字面量；而冻结针脚里的 `抽奖券不足` / `奖品池为空` 等为**裸中文**（count 已实测）。

==============================================================================
六、契约（照 localtest/yl_r169b_ext.py）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 权重函数探针）。
  · 二进制读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 <src>.bak-r176-<时刻>。
  · 幂等：产物已含标记 `[r176lot]` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 不跑网络：只读 --src 指向的本地文件。

==============================================================================
七、实测重建法（可复现；用于得到 §一/§三 的数字）
==============================================================================
  从 bundle 抽取 5 段纯代码：`Vn/En/on/Qn` 字典、`function WN(){...}`+`Yr=[...]`、`function cy(t){...}`、
  `ms=[...]` 字面量、`S3/k3/C3/E3/R3` 生成段；在 Node `vm` 中以最小桩（`ce/H/Ct/KN/JN/St/ry/N3`）
  执行，得到**真实 ms**（1193 条），再按 `handleDraw` 原循环（含 rk=50 保底）对改前/改后抽样器
  做解析式 + 蒙特卡洛（400k 轮，误差 <0.1%）测量。上述数字即由此得出。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r176lot]'

# --------------------------------------------------------------------------- 替换项

# E1：注入常量 + 两个纯函数（插在 YlxwDrawValue 收尾处）
A_OLD = '  return { stones: stones, exp: exp };\n}'

A_NEW = A_OLD + (
    '\n\n'
    '/* ===== R-176 [r176lot] 抽奖券抽奖：奖品池按「玩家境界 <-> 奖品等阶」差距收敛 =====\n'
    '   目标：绝大多数抽到 <= 自身境界的奖品；比自身高 1 个大境界已非常小，高 2 个几乎微乎其微，\n'
    '   高 3 个及以上约千万分之一；获得的高阶物品不再折算灵石（改由概率收敛）。\n'
    '   实现：唯一抽样器 N() 内，把每件奖品 weight 乘以「境界差倍率」（整数，防浮点漂移）。\n'
    '   倍率表 YLXW_R176_MUL 下标 d = 奖品境界序 - 玩家境界序（d<0 归 0；d>3 收口末位）：\n'
    '        d<=0 : 10000000  主体（同等阶 + 更低 + 境界无关物品）\n'
    '        d=1  : 10000     相对 d<=0 约 1e-3（非常小）\n'
    '        d=2  : 100       相对 d<=0 约 1e-5（微乎其微）\n'
    '        d>=3 : 1         相对 d<=0 约 1e-7（千万分之一）\n'
    '   实测（真实奖品池 ms，1193 条；含保底、50 抽周期平均，单抽概率）：\n'
    '        玩家 炼气期：改前越阶 59.12%（其中 d>=3 占 39.81%）-> 改后越阶 0.024%\n'
    '           改后 d<=0 22.879% / d=1 0.024033% / d=2 0.000232% / d>=3 0.000010% / 境界无关 77.097%\n'
    '        玩家 筑基期：改后 d<=0 37.823% / d=1 0.018698% / d=2 0.000205% / d>=3 0.000006%\n'
    '        玩家 金丹期：改后 d<=0 47.616% / d=1 0.017306% / d=2 0.000158% / d>=3 0.000003%\n'
    '        玩家 长生境：其上无境界，全部落 d<=0（不削弱）\n'
    '   判定：装备类按 realm / realmRequirement / 名字 [境界] 前缀；境界无关物品（灵石/修为/丹药/\n'
    '         灵草/材料/灵宠/抽奖券/进阶物品，共 293 条）无 realm 字段，视为永远可抽（归 d<=0）。 */\n'
    'var YLXW_R176_MUL = [10000000, 10000, 100, 1];\n'
    'function YlxwR176RealmIdx(x) {\n'
    '  try {\n'
    '    if (!x) return -1;\n'
    '    var y = (x.value && x.value.item) ? x.value.item : x;\n'
    '    var s = String(y.realm || y.realmRequirement || "").trim();\n'
    '    if (!s) { var m = /\\[([^\\[\\]]+)\\]/.exec(String(y.name || x.name || "")); if (m) s = String(m[1]).trim(); }\n'
    '    if (!s) return -1;\n'
    '    if (s === "\\u957f\\u751f") s = "\\u957f\\u751f\\u5883";\n'
    '    var i = fe.indexOf(s);\n'
    '    if (i >= 0) return i;\n'
    '    return fe.indexOf(s + "\\u671f");\n'
    '  } catch (e) { return -1; }\n'
    '}\n'
    'function YlxwR176Mul(itemIdx, playerIdx) {\n'
    '  if (itemIdx < 0 || playerIdx < 0) return YLXW_R176_MUL[0];\n'
    '  var d = itemIdx - playerIdx;\n'
    '  if (d <= 0) return YLXW_R176_MUL[0];\n'
    '  return YLXW_R176_MUL[d < YLXW_R176_MUL.length ? d : YLXW_R176_MUL.length - 1];\n'
    '}\n'
)

# E2：唯一抽样器按境界差重加权（签名 (g,q) 不变；q 不再使用）
B_OLD = (
    'N=(g,q)=>{if(q>0&&g.length>0){let w=Math.random()*q;for(const A of g)'
    'if(w-=A.weight,w<=0)return A}return g.length>0?g[0]:null}'
)

B_NEW = (
    'N=(g,q)=>{/*[r176lot]*/if(!(g&&g.length>0))return null;'
    'const _pr=YlxwR176RealmIdx(d);let _tot=0;const _ws=new Array(g.length);'
    'for(let _i=0;_i<g.length;_i++){const _it=g[_i];'
    'const _ew=(Number(_it.weight)||0)*YlxwR176Mul(YlxwR176RealmIdx(_it),_pr);'
    '_ws[_i]=_ew;_tot+=_ew}'
    'if(!(_tot>0))return g[0];'
    'let w=Math.random()*_tot;'
    'for(let _i=0;_i<g.length;_i++){w-=_ws[_i];if(w<=0)return g[_i]}'
    'return g[0]}'
)

# E3：删除「越阶 -> 折算灵石」兜底（中文在 bundle 内为 \uXXXX 转义形态）
C_OLD = (
    r'const _ylr=(()=>{const _ylm=/\[([^\[\]]+)\]/.exec(U.name||"");'
    r'const _yls=String(U.realm||U.realmRequirement||(_ylm?_ylm[1]:"")||"").trim();'
    r'if(!_yls)return null;if(fe.includes(_yls))return _yls;'
    r'if(_yls==="\u957f\u751f")return"\u957f\u751f\u5883";'
    r'return fe.find(_ylR=>_ylR===_yls+"\u671f")||null})();'
    r'const _ylpi=fe.indexOf(g.realm),_ylq=fe.indexOf(_ylr);'
    r'if(_ylr&&_ylpi>=0&&_ylq>_ylpi){'
    r'const _ylk=YlxwCvtStones(U,_ylq),_ylv=YlxwDrawValue(U,_ylq,_ylpi,g,_ylk);'
    r'A+=_ylv.exp,w+=_ylv.stones,'
    r'f(`\u611f\u5e94\u5230\u3010${U.name}\u3011\u8574\u542b\u9ad8\u9636\u6c14\u606f\uff0c'
    r'\u673a\u7f18\u672a\u81f3\uff0c\u5316\u4f5c ${_ylv.stones.toLocaleString()} \u7075\u77f3 '
    r'\u4e0e ${_ylv.exp.toLocaleString()} \u4fee\u4e3a \u6d88\u6563\u3002`,"gain");continue}'
)

C_NEW = '/*[r176lot] \u8d8a\u9636\u4e0d\u518d\u6298\u7b97\u7075\u77f3\uff0c\u6539\u7531\u6982\u7387\u6536\u655b*/'

REPS = [
    ('R176-1 注入境界差倍率与纯函数', A_OLD, A_NEW),
    ('R176-2 抽样器按境界差重加权', B_OLD, B_NEW),
    ('R176-3 删除越阶折算灵石段', C_OLD, C_NEW),
]

# 冻结针脚：本环只动上面 3 处，下列既有形态必须逐字在位（**补前补后计数不变**，故同时用于
#           _precheck（原件）与 gates（产物）；会随补丁增减计数的针脚改由 gates() 显式断言）
FREEZE = [
    # 抽奖校验 / 券消耗口径 / 保底 —— 一律未动
    ('if(!d||d.lotteryTickets<S){f("抽奖券不足！","danger");return}', 1),
    ('if(S<=0||!Number.isInteger(S)){f("抽奖次数必须为正整数！","danger");return}', 1),
    ('if(ms.length===0){f("奖品池为空，无法抽奖！","danger");return}', 1),
    ('lotteryTickets:D-S,lotteryCount:g.lotteryCount+S', 1),
    ('const q=T+g+1,w=q%rk===0&&M.length>0&&E>0,A=q%10===0;', 1),
    ('const C=Array.from(_.values());', 1),
    # 折算相关函数与表保留在位（仅不再被本路径调用）
    ('function YlxwDrawValue(x, q, pi, g, legacy) {', 1),
    ('function YlxwDrawExpNeed(g) {', 1),
    ('var YLXW_DRAW_STONES = [', 1),
    ('YlxwDrawExpNeed', 2),
    # 奖品池本体未动（抽样几条 count==1 的锚）
    ('lottery-ticket-1', 1),
    ('lottery-pet-fox', 1),
    ('lottery-material-snow-lotus', 1),
    # 中文形态登记：裸中文（转义形态会随 E3 减 1，改由 gates 断言）
    ('感应到', 1),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R176·幂等标记', IDEMPOTENT_MARK, 3, '==', 'E1注释块/E2/E3 各 1 处'),
        ('R176·倍率表已注入', 'var YLXW_R176_MUL = [10000000, 10000, 100, 1];', 1, '==', '整数倍率表恰好 1 处'),
        ('R176·境界判定已注入', 'function YlxwR176RealmIdx(x) {', 1, '==', '恰好 1 处'),
        ('R176·倍率函数已注入', 'function YlxwR176Mul(itemIdx, playerIdx) {', 1, '==', '恰好 1 处'),
        ('R176·抽样器已重加权', B_NEW, 1, '==', '新抽样器恰好 1 处'),
        ('R176·旧抽样器已消失', B_OLD, 0, '==', '旧 N() 已不存在'),
        ('R176·折算段已删除', C_OLD, 0, '==', '越阶折算段已不存在'),
        ('R176·★折算调用已清零', 'YlxwDrawValue(U,_ylq,_ylpi,g,_ylk)', 0, '==', '红线：不再折算高阶物品'),
        ('R176·★越阶文案已清零', r'\u8574\u542b\u9ad8\u9636\u6c14\u606f', 0, '==', '红线：不得再有折算提示'),
        ('R176·★感应到转义已减半', r'\u611f\u5e94\u5230', 1, '==', '原 2 处 -> 删 1 处'),
        ('R176·CvtStones 调用减少', 'YlxwCvtStones(U,_ylq)', 1, '==', '原 2 处 -> 删 1 处'),
        ('R176·CvtStones 定义仍在', 'YlxwCvtStones', 6, '==', '函数保留在位（7 -> 6）'),
        ('R176·DrawValue 仅剩定义', 'YlxwDrawValue', 1, '==', '原 2 处 -> 删调用 1 处'),
        # 未动项（补后仍需在位）
        ('R176·抽奖券校验未动', 'if(!d||d.lotteryTickets<S){f("抽奖券不足！","danger");return}', 1, '==', ''),
        ('R176·次数校验未动', 'if(S<=0||!Number.isInteger(S)){f("抽奖次数必须为正整数！","danger");return}', 1, '==', ''),
        ('R176·池空校验未动', 'if(ms.length===0){f("奖品池为空，无法抽奖！","danger");return}', 1, '==', ''),
        ('R176·券消耗口径未动', 'lotteryTickets:D-S,lotteryCount:g.lotteryCount+S', 1, '==', ''),
        ('R176·保底逻辑未动', 'const q=T+g+1,w=q%rk===0&&M.length>0&&E>0,A=q%10===0;', 1, '==', ''),
        ('R176·入账聚合未动', 'const C=Array.from(_.values());', 1, '==', ''),
        ('R176·正常入包仍在', r'q=vs(q,U,1,{realm:g.realm,realmLevel:g.realmLevel}),f(`\u83b7\u5f97 ${U.name}\uff01`,"gain")', 1, '==', '越阶物品改走此路'),
        ('R176·抽奖入口仍在', 'handleDraw:S=>{', 1, '==', ''),
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


def _r176_probe(patched_text):
    """从补丁后产物抽出**真实**注入块，用 node 验证境界判定/倍率/实测比例。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。
    """
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    i = patched_text.find('var YLXW_R176_MUL = [')
    if i < 0:
        return False, 'YLXW_R176_MUL 未找到'
    k = patched_text.find('function YlxwR176Mul', i)
    if k < 0:
        return False, 'YlxwR176Mul 未找到'
    j = patched_text.find('\n}\n', k)
    if j < 0:
        return False, 'YlxwR176Mul 结束边界未找到'
    blk = patched_text[i:j + 2]
    js = (
        'const fe=["\\u70bc\\u6c14\\u671f","\\u7b51\\u57fa\\u671f","\\u91d1\\u4e39\\u671f",'
        '"\\u5143\\u5a74\\u671f","\\u5316\\u795e\\u671f","\\u5408\\u9053\\u671f","\\u957f\\u751f\\u5883"];\n'
        + blk + r'''
// 1) 境界判定
const cases=[
  [{name:"[\u70bc\u6c14\u671f]\u7cbe\u94c1\u6307\u73af"},0],
  [{realm:"\u91d1\u4e39\u671f"},2],
  [{realmRequirement:"\u7b51\u57fa\u671f"},1],
  [{realm:"\u957f\u751f"},6],
  [{name:"10\u7075\u77f3",value:{spiritStones:10}},-1],
  [{name:"\u805a\u6c14\u4e39",value:{item:{name:"\u805a\u6c14\u4e39"}}},-1],
  [{name:"\u4ed9\u54c1",value:{item:{realm:"\u957f\u751f\u5883"}}},6],
];
for(const [x,want] of cases){const got=YlxwR176RealmIdx(x);if(got!==want)throw new Error("RealmIdx "+JSON.stringify(x)+" got "+got+" want "+want);}
// 2) 倍率表
const want={0:10000000,1:10000,2:100,3:1,6:1};
for(const d in want){ if(d==="0"){ for(const p of [0,3,6]) if(YlxwR176Mul(0,p)!==want[0]) throw new Error("mul d<=0"); continue; }
  const got=YlxwR176Mul(Number(d),0); if(got!==want[d])throw new Error("mul d="+d+" got "+got); }
if(YlxwR176Mul(-1,0)!==10000000)throw new Error("realm-less should be max");
if(YlxwR176Mul(3,-1)!==10000000)throw new Error("unknown player realm should be max");
// 3) 解析式：等权 7 境界池，各境界差相对概率（确定性，不依赖随机）
const pool=fe.map(r=>({name:"["+r+"]x",realm:r,weight:1}));
function dist(pi){var tot=0,acc={};for(var n=0;n<pool.length;n++){var it=pool[n];var ii=YlxwR176RealmIdx(it);
  var w=it.weight*YlxwR176Mul(ii,pi);var d=ii-pi;var k=d<=0?"d<=0":d===1?"d=1":d===2?"d=2":"d>=3";
  acc[k]=(acc[k]||0)+w;tot+=w}
  var o={};for(var k2 in acc)o[k2]=acc[k2]/tot;return o}
const D=dist(0);
if(Math.abs(D["d=1"]/D["d<=0"]-1e-3)>1e-9)throw new Error("d=1 ratio "+ (D["d=1"]/D["d<=0"]));
if(Math.abs(D["d=2"]/D["d<=0"]-1e-5)>1e-9)throw new Error("d=2 ratio "+ (D["d=2"]/D["d<=0"]));
if(!(D["d>=3"]/D["d<=0"]<1e-6))throw new Error("d>=3 ratio "+ (D["d>=3"]/D["d<=0"]));
if(!(D["d<=0"]>0.998))throw new Error("d<=0 too small "+D["d<=0"]);
if(!((D["d=1"]+D["d=2"]+D["d>=3"])<2e-3))throw new Error("above-realm too big");
// 4) 蒙特卡洛抽检：确认抽样器确实按倍率走（只验 d=1，样本充足）
function pick(pi){var tot=0,ws=[];for(var n=0;n<pool.length;n++){
  var w=pool[n].weight*YlxwR176Mul(YlxwR176RealmIdx(pool[n]),pi);ws.push(w);tot+=w}
  var w=Math.random()*tot;for(var i=0;i<pool.length;i++){w-=ws[i];if(w<=0)return i}return 0}
var N=1000000,c0=0,c1=0;
for(var t=0;t<N;t++){var i=pick(0);if(i===0)c0++;else if(i===1)c1++}
var r1=(c1/N)/(c0/N);
if(!(r1>5e-4&&r1<2e-3))throw new Error("MC d=1 ratio "+r1);
console.log("r176-probe OK analytic d<=0="+D["d<=0"].toFixed(9)+" d=1="+D["d=1"].toExponential(3)
  +" d=2="+D["d=2"].toExponential(3)+" d>=3="+D["d>=3"].toExponential(3)+" MC d=1 ratio="+r1.toExponential(3));
''')
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:400]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 权重函数探针。"""
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r176] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r176] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r176] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r176] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r176] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r176] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _r176_probe(out)
    if ok is False:
        print('[r176] SELFTEST FAIL r176-probe: ' + pmsg)
        return 1
    print('[r176] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s; %s'
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
        print('[r176] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r176] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r176] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r176] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r176] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r176] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-40s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r176-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r176] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-40s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
