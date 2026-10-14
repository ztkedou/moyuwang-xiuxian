# -*- coding: utf-8 -*-
r"""
yl_r255_ext.py — R-255 寿命系统重构：剩余寿命递减 → 年龄递增（纯客户端）

需求原文（用户原话，逐条）
--------------------------------------------------------------------------
  1. 寿命不是现在的进度条降低，换成"年龄"，变成增长，新建角色从0岁开始。
  2. 默认寿命区间展示在面板上，比如说炼气1层大概80-100岁。但是实际的初始寿命
     是在区间内随机出一个固定值，只是不展示出来，但是游戏到了固定的寿命值就
     只能重开游戏重修。
  3. 游戏每升一个境界或者吃延长寿命的丹药，就会展示新的寿命区间，并且把寿命
     上限加上。
  4. 现在的打坐、历练这些的减少寿命，就变成了增加年龄。
  5. 寿命的上限区间还是用之前参考实际修仙小说的设定。
  6. 大概按照这样的内容重构。

用户后续裁定（7 + 4 项，见 docs/寿命重构设计方案.md §9）
--------------------------------------------------------------------------
  · 寿终 = 彻底重开，清空一切（成就/图鉴/称号也清）；后续另加「传承」按钮。
  · 战斗死亡不改（气血归零仍走保命法宝 / 重生）。
  · 区间粒度沿用现有 YlxwLifeStep（小境界少量、跨大境界大量补齐）。
  · 区间宽度 = 上限 × 0.9。
  · 面板 = 年龄文字 + 进度条（分母 = 区间上限）。
  · 延寿类丹药重做：既做「减年龄（回春）」，也做「加真实寿元」。
  · 老存档迁移：age = 旧上限 − 旧剩余寿命；deathLine = 旧上限（逐位保留）。
  · 法宝 cost.lifespan 死代码 → 删掉死字段与文案。
  · 年龄增长速率 → 打坐 YLXW_MED_LIFE 0.001 → 0.0002。
  · 丹药数值 → 延寿丹 +3、长生丹 +8、不死仙丹 +20；新增驻颜丹 −3、返春丹 −8。
  · 老存档迁移 → 区间按 lifeBonus 上移，不 clamp age。

==============================================================================
一、核心模型（数学自洽性已验算）
==============================================================================
三个存储字段：
    age        当前年龄（内部小数，面板取整）          —— 可见
    lifeRatio  建号时随机抽定 ∈ [0.9, 1]，终身不变    —— 隐藏
    lifeBonus  丹药 / 永久加寿累计                    —— 间接可见
三个派生量（全部由注入的辅助函数计算，不落盘）：
    U_base(realm, lv) = 境界基准上限（复用 YlxwLifeCur/Next）
    U_display         = U_base + lifeBonus            —— 面板展示的区间上限
    deathLine         = lifeRatio × U_base + lifeBonus —— 真实死线（隐藏）
展示区间 = [floor(0.9 × U_display), floor(U_display)]
寿终条件 = age >= deathLine

恒有  0.9 × U_display ≤ deathLine ≤ U_display（lifeRatio ∈ [0.9,1]、lifeBonus ≥ 0）
⇒ 真实死线永远落在展示区间内，玩家永不看到矛盾（不穿帮）。

`player.maxLifespan` 保留字段名，但语义改为 **deathLine 的落盘副本**
（这样寿终判定、老存档兼容、上游门禁都只需最小改动）。

==============================================================================
二、成长公式：一行不改，复用现有 YlxwLifeStep
==============================================================================
    YlxwLifeStep(i, big) = big ? (next−cur)/2 : (next−cur)/16
    小境界 8 步 + 大境界 1 步 = 8×(d/16) + d/2 = d = next − cur  ← 恰好补齐
⇒ 炼气 100 →(9层) 150 →(筑基) 200；筑基 200 → 325 → 450 …… 与用户第 5 条
  「沿用《凡人修仙传》设定」完全一致，不需要新造步长。

==============================================================================
三、改动面（客户端，全部锚点均经 _r255_verify.py 断言唯一）
==============================================================================
  I0  注入辅助函数块（幂等标记 /*YLXW_R255_V2961*/）
  E1  建号：age:0 / lifeRatio 随机 / lifeBonus:0 / maxLifespan = 上限×ratio
  E2  打坐：寿命 −= → age +=（速率 0.001 → 0.0002）
  E3  历练：寿命 −= → age +=；lifespanChange>0 → lifeBonus +=
  E4  突破：maxLifespan = 旧值 + lifeRatio×步长（age 不变），文案改区间
  E5  传承连跳：同源化 + 删死代码 T.baseMaxLifespan
  E6  丹药 effect.lifespan → effect.ageReduce（减年龄）
  E7  丹药 permanentEffect.maxLifespan → lifeBonus +=（加真实寿元）
  E8  离线结算：lifespanSpent → ageSpent，age +=
  E9  面板：寿命 x/y → 年龄 x 岁 · 寿元 lo-hi 岁（进度条分母 = 区间上限）
  E10 寿元将尽预警：改比较区间下限
  E11 寿终判定：age >= deathLine → 清档重开（复用 /character/reset 链路）
  E12 读档归一 / 老存档迁移
  E13 属性中文名表 + YLXW_PILL_FX 标签表
  E14 法宝 cost:{lifespan:N} 死代码 + 「消耗N年寿命，」文案 + 渲染分支（正则批量）
  E15 丹方：改造延寿丹/长生丹/不死仙丹 + 新增驻颜丹/返春丹 + us 懒取表

==============================================================================
四、契约（standalone，同 localtest/yl_r219_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`；可选 `--dump`（只打印对照，不写盘）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r255-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态；2=前置断言/锚点计数失败；1=其它错误。
  · 纯客户端；不改 build_v26n.py / chain_build.py / dryrun_087.py / 任何 build/assets/*。
"""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 幂等标记
MARK = '/*YLXW_R255_V2961*/'

# --------------------------------------------------------------------------- 注入的辅助函数块
# 注入位置：YL_LIFE_097 块内 YlxwLifeStep 之后（fe / YlxwLifeCur / YlxwLifeNext 均已可见）。
# ★ 块内必须为纯 ASCII：所有中文一律写成 \uXXXX 转义（源码里就是反斜杠 + u）。
HELPER = (
    MARK + '\n'
    'var YLXW_AGE_MIN = 0.9;\n'
    'function YlxwAgeRoll() { return YLXW_AGE_MIN + Math.random() * (1 - YLXW_AGE_MIN); }\n'
    'function YlxwLifeUpper(realm, lv) {\n'
    '  var i = fe.indexOf(realm); if (i < 0) i = 0;\n'
    '  var L = Math.floor(Number(lv)); if (!isFinite(L) || L < 1) L = 1; if (L > 9) L = 9;\n'
    '  var cur = YlxwLifeCur(i), nxt = YlxwLifeNext(i);\n'
    '  return cur + (L - 1) * ((nxt - cur) / 16);\n'
    '}\n'
    'function YlxwLifeBonus(p) { var n = Number(p && p.lifeBonus); return isFinite(n) ? n : 0; }\n'
    'function YlxwLifeShow(p) {\n'
    '  if (!p) return 100;\n'
    '  return YlxwLifeUpper(p.realm, p.realmLevel) + YlxwLifeBonus(p);\n'
    '}\n'
    'function YlxwLifeDeathLine(p) {\n'
    '  if (!p) return 100;\n'
    '  var r = Number(p.lifeRatio);\n'
    '  if (!isFinite(r) || r < YLXW_AGE_MIN || r > 1) r = 1;\n'
    '  return r * YlxwLifeUpper(p.realm, p.realmLevel) + YlxwLifeBonus(p);\n'
    '}\n'
    'function YlxwLifeRange(upper) {\n'
    '  var u = Number(upper); if (!isFinite(u) || u < 1) u = 1;\n'
    '  var lo = Math.floor(u * YLXW_AGE_MIN); if (lo < 0) lo = 0;\n'
    '  var hi = Math.ceil(u); if (hi < lo) hi = lo;\n'
    '  return [lo, hi];\n'
    '}\n'
    'function YlxwLifeTextOf(upper) { var r = YlxwLifeRange(upper); return r[0] + "-" + r[1] + " \\u5c81"; }\n'
    'function YlxwLifeText(p) { return YlxwLifeTextOf(YlxwLifeShow(p)); }\n'
    'function YlxwLifeMigrate(t) {\n'
    '  if (!t) return { age: 0, lifeRatio: 1, lifeBonus: 0, maxLifespan: 100 };\n'
    '  var n = YlxwLifeBonus(t), r = Number(t.lifeRatio);\n'
    '  if (!isFinite(r) || r < YLXW_AGE_MIN || r > 1) r = 1;\n'
    '  var a = Number(t.age);\n'
    '  if (isFinite(a) && t.age !== null && t.age !== void 0) {\n'
    '    var d0 = Number(t.maxLifespan);\n'
    '    if (!isFinite(d0)) d0 = YlxwLifeDeathLine({ realm: t.realm, realmLevel: t.realmLevel, lifeRatio: r, lifeBonus: n });\n'
    '    return { age: a, lifeRatio: r, lifeBonus: n, maxLifespan: d0 };\n'
    '  }\n'
    '  var base = YlxwLifeUpper(t.realm, t.realmLevel);\n'
    '  var old = Number(t.maxLifespan); if (!isFinite(old) || old <= 0) old = base;\n'
    '  var left = Number(t.lifespan); if (!isFinite(left)) left = old;\n'
    '  var age = old - left; if (age < 0) age = 0;\n'
    '  var ratio = old / base;\n'
    '  if (!isFinite(ratio) || ratio < YLXW_AGE_MIN) ratio = YLXW_AGE_MIN; if (ratio > 1) ratio = 1;\n'
    '  var bonus = old - ratio * base; if (bonus < 0) bonus = 0;\n'
    '  return { age: age, lifeRatio: ratio, lifeBonus: bonus, maxLifespan: ratio * base + bonus };\n'
    '}\n'
)

# --------------------------------------------------------------------------- 锚点（补丁前）
# I0 注入点：YL_LIFE_097 块的 YlxwLifeStep 收尾（纯 ASCII，唯一）
A_INJ = '  return big ? half : half / 8;\n}'
N_INJ = A_INJ + '\n' + HELPER

# E1 建号（纯 ASCII，各唯一）
A_NEW1 = '$=b.baseMaxLifespan,M=$;'
N_NEW1 = '$=b.baseMaxLifespan,M=$*YlxwAgeRoll();'
A_NEW2 = 'lifespan:M,maxLifespan:$'
N_NEW2 = 'age:0,maxLifespan:M,lifeRatio:M/$||1,lifeBonus:0'

# E2 打坐（纯 ASCII，唯一）
A_MED = 'lifespan:Math.max(0,($.lifespan??$.maxLifespan??100)-YLXW_MED_LIFE)'
N_MED = 'age:($.age??0)+YLXW_MED_LIFE'
A_MEDC = 'var YLXW_MED_LIFE = 0.001;'
N_MEDC = 'var YLXW_MED_LIFE = 0.0002;'

# E3 历练（字面中文区段，各唯一）
A_ADV = ('if(S.lifespan=Math.max(0,Math.min(t.maxLifespan,'
         '(t.lifespan??t.maxLifespan)+(r.lifespanChange||0)-h)),/*[r180adv4]*/')
N_ADV = ('if(S.age=(t.age??0)+h+(r.lifespanChange<0?-r.lifespanChange:0),'
         'r.lifespanChange>0&&(S.lifeBonus=(t.lifeBonus??0)+r.lifespanChange,'
         'S.maxLifespan=(t.maxLifespan??0)+r.lifespanChange),/*[r180adv4]*/')
A_ADVLOG = ('h>0&&m("⚠️ 寿元 -"+h.toFixed(2)+" 年（危险度："+(u||"普通")+"）","danger")')
N_ADVLOG = ('h>0&&m("⚠️ 年龄 +"+h.toFixed(2)+" 岁（危险度："+(u||"普通")+"）","danger")')

# E4 突破（字面中文区段，各唯一）
A_BT = ('const Ne=g.maxLifespan||100;let _e=0;'
        '_e=YlxwLifeStep(fe.indexOf(g.realm),m);'
        'const st=Ne+_e,ke=(g.lifespan??Ne)+_e;')
N_BT = ('const Ne=g.maxLifespan||100;let _e=0;'
        '_e=YlxwLifeStep(fe.indexOf(g.realm),m);'
        'const st=Ne+(g.lifeRatio??1)*_e,ke=g.age??0;')
A_BTLOG = ('if(_e>0&&a(`✨ 突破成功！你的寿命增加了 ${Math.floor(_e)} 年！'
           '当前寿命：${Math.floor(ke)}/${Math.floor(st)} 年`,"gain"),m){')
N_BTLOG = ('if(_e>0&&a(`✨ 突破成功！寿元增长，当前寿元区间：'
           '${YlxwLifeTextOf(YlxwLifeUpper(g.realm,g.realmLevel)+_e+(g.lifeBonus||0))}`,"gain"),m){')
A_BTRET = 'maxLifespan:st,lifespan:ke,'
N_BTRET = 'maxLifespan:st,age:ke,'

# E5 传承连跳（字面中文 + \uXXXX 混合）
A_INHDEAD = 'T.baseMaxLifespan;'
N_INHDEAD = ''
A_INH = 'const Ie=le+ge,ue=(f.lifespan??le)+ge;'
N_INH = 'const Ie=le+(f.lifeRatio??1)*ge,ue=f.age??0;'
A_INHLOG = ('ge>0&&a(`\\u2728 \\u4f20\\u627f\\u7a81\\u7834\\u6210\\u529f\\uff01'
            '\\u4f60\\u7684\\u5bff\\u547d\\u589e\\u52a0\\u4e86 ${ge} \\u5e74\\uff01'
            '\\u5f53\\u524d\\u5bff\\u547d\\uff1a${Math.floor(ue)}/${Ie} \\u5e74`,"gain")')
N_INHLOG = ('ge>0&&a(`\\u2728 \\u4f20\\u627f\\u7a81\\u7834\\u6210\\u529f\\uff01'
            '\\u5bff\\u5143\\u589e\\u957f\\uff0c\\u5f53\\u524d\\u5bff\\u5143\\u533a\\u95f4\\uff1a'
            '${YlxwLifeText({realm:b,realmLevel:S,lifeBonus:f.lifeBonus})}`,"gain")')

# E6 丹药 effect.lifespan → effect.ageReduce（字面中文，唯一）
A_PILLEFF = ('($=r.effect)!=null&&$.lifespan){const h=u.lifespan??u.maxLifespan??100,'
             'R=u.maxLifespan??100,E=r.effect.lifespan,N=Math.min(R,h+E);'
             'u.lifespan=Math.max(u.lifespan??0,N),m.push(`寿命增加了 ${E} 年。`)}')
N_PILLEFF = ('($=r.effect)!=null&&$.ageReduce){const E=$.ageReduce;'
             'u.age=Math.max(0,(u.age??0)-E),m.push(`年龄减少了 ${E} 岁。`)}')

# E7 丹药 permanentEffect.maxLifespan → lifeBonus（字面中文，唯一）
A_PILLPERM = ('if(R.maxLifespan&&(u.maxLifespan=(u.maxLifespan??100)+R.maxLifespan,'
              'u.lifespan=Math.min(u.maxLifespan,(u.lifespan??u.maxLifespan??100)+R.maxLifespan),'
              'h.push(`最大寿命永久 +${R.maxLifespan} 年`)),')
N_PILLPERM = ('if(R.maxLifespan&&(u.lifeBonus=(u.lifeBonus??0)+R.maxLifespan,'
              'u.maxLifespan=(u.maxLifespan??100)+R.maxLifespan,'
              'h.push(`寿元上限永久 +${R.maxLifespan} 年`)),')

# E8 离线结算（纯 ASCII，各唯一）
A_OFFDEF = 'lifespanSpent:S}'
N_OFFDEF = 'ageSpent:S}'
A_OFFUSE = 'a.lifespan=Math.max(0,(a.lifespan||100)-r.lifespanSpent),a}'
N_OFFUSE = 'a.age=(a.age??0)+r.ageSpent,a}'

# E9 面板（纯 ASCII + 字面中文）
A_PANELF = ('f=O.useMemo(()=>{const j=t.maxLifespan??100,b=t.lifespan??j;'
            'return Math.min(100,b/j*100)},[t.lifespan,t.maxLifespan])')
N_PANELF = ('f=O.useMemo(()=>{const j=YlxwLifeShow(t)||100,b=t.age??0;'
            'return Math.min(100,b/j*100)},[t.age,t.maxLifespan,t.lifeBonus,t.realm,t.realmLevel])')
A_PANELUI = ('e.jsx("span",{children:"寿命 (年)"}),e.jsxs("span",{children:'
             '[lt(Math.floor(t.lifespan??t.maxLifespan??100))," / ",'
             'lt(Math.floor(t.maxLifespan??100))]})')
N_PANELUI = ('e.jsx("span",{children:"年龄 / 寿元"}),e.jsxs("span",{children:'
             '["年龄 ",Math.floor(t.age??0)," 岁 · 寿元 ",YlxwLifeText(t)]})')

# E10 预警（字面中文，唯一）
A_WARN = ('u.lifespan<Math.max(5,(u.maxLifespan||100)*.1)&&e.jsxs(e.Fragment,{children:'
          '[e.jsx("div",{className:"lifespan-warning"}),'
          'e.jsxs("div",{className:"lifespan-warning-text animate-pulse",children:'
          '["⚠️ 寿元将尽 (剩余 ",u.lifespan.toFixed(1)," 年)"]})]})')
N_WARN = ('(u.age??0)>=YlxwLifeRange(YlxwLifeShow(u))[0]&&e.jsxs(e.Fragment,{children:'
          '[e.jsx("div",{className:"lifespan-warning"}),'
          'e.jsxs("div",{className:"lifespan-warning-text animate-pulse",children:'
          '["⚠️ 寿元将尽（已入暮年，速寻延寿之法）"]})]})')

# E11 寿终判定（字面中文，唯一）—— 整段替换为「清档重开」
A_DEATH = 'if(t.lifespan!==void 0&&t.lifespan<=0){'
DEATH_TAIL_MARK = 'v($),f(null),m(!1),j(!1),b(!1)}return}'
DEATH_TAILS = [
    'v(T+`但你的灵魂尚未完全消散，在付出代价后得以重生。`),f(null),mm(),m(!1),j(!1),b(!1);',
    'v($),f(null),m(!1),j(!1),b(!1)}return}',
]
DEATH_MID_A = ('c("⏰ 你的寿命已尽，寿终正寝 还是无缘窥探大道...","danger");'
               'const x=["你的寿命已尽，大限将至。在生命的最后时刻，你盘膝而坐，试图突破境界以延寿，'
               '但终究未能成功，最终寿终正寝。","你的寿命已尽，体内的生机逐渐消散。尽管你拼尽全力想要延续生命，'
               '但天道无情，你最终还是走到了生命的尽头，寿终正寝。","你的寿命已尽，岁月在你身上留下了无法磨灭的痕迹。'
               '你的修为虽高，但终究无法突破寿命的桎梏，最终寿终正寝。","你的寿命已尽，体内的真元逐渐枯竭。'
               '你尝试了各种延寿之法，但都未能成功，最终在遗憾中寿终正寝。"],'
               'T=x[Math.floor(Math.random()*x.length)];')
DEATH_MID_B = ('if(d.difficulty==="hard")l(!0),r($=>$&&YLXW_R219_HARD($,!0,c)),'
               'v(T+`但你的灵魂尚未完全消散，在付出代价后得以重生。`),f(null),mm(),m(!1),j(!1),b(!1);'
               'else{l(!0),r(M=>{if(!M)return M;const h=Math.max(1,Math.floor(M.maxHp*.1)),'
               'R=Math.min(M.maxLifespan||100,10);return{...M,hp:h,lifespan:R}});'
               'const $=`${T}但天道的仁慈让你得以重生，继续你的修仙之路。`;'
               'v($),f(null),m(!1),j(!1),b(!1)}return}')

N_DEATH = (
    'if(t.age!==void 0&&t.age>=YlxwLifeDeathLine(t)){'
    # ★ 一次性闩锁：寿终只处理一次。**不能**用 setIsDead(true) 当闩锁 ——
    #   那会同时把旧的「身死道消 / 涅槃重生」弹窗 `bk` 渲染到本弹窗**背后**（双弹窗叠层，
    #   2026-10-14 本地联调截图实测到的真缺陷）。改用 window 上的标记，`bk` 保持不渲染。
    'if(window.__ylR255Ended)return;window.__ylR255Ended=1;'
    'c("⏰ 你的寿命已尽，寿终正寝，还是无缘窥探大道...","danger");'
    'const x=["你的寿命已尽，大限将至。在生命的最后时刻，你盘膝而坐，试图突破境界以延寿，'
    '但终究未能成功，最终寿终正寝。","你的寿命已尽，体内的生机逐渐消散。尽管你拼尽全力想要延续生命，'
    '但天道无情，你最终还是走到了生命的尽头，寿终正寝。","你的寿命已尽，岁月在你身上留下了无法磨灭的痕迹。'
    '你的修为虽高，但终究无法突破寿命的桎梏，最终寿终正寝。","你的寿命已尽，体内的真元逐渐枯竭。'
    '你尝试了各种延寿之法，但都未能成功，最终在遗憾中寿终正寝。"],'
    'T=x[Math.floor(Math.random()*x.length)];'
    'v(T+"寿元已尽，此身道消。此世的修为、法宝、机缘皆随风而散，唯有转世重修，方能再续仙途。"),'
    'f(null),mm(),m(!1),j(!1),b(!1);'
    'Ui("⏰ 你的寿元已尽\\n\\n"+T+"\\n\\n此世的修为、法宝、机缘皆随风而散。'
    '唯有转世重修，方能再续仙途。","转世重修",()=>{'
    'const __r255done=()=>{try{localStorage.removeItem(et.SAVE),'
    'localStorage.removeItem(et.SAVE_BACKUP),localStorage.removeItem(et.SAVE_OWNER)}catch(e){}'
    'try{window.location.reload()}catch(e){}};'
    'if(!Et.getState().token){__r255done();return}'
    'Xc(`${ln}/character/reset`,{method:"POST"}).then(__r255done,()=>{'
    'Je("服务端角色数据清除失败，请稍后重试（本次未重置）")})});'
    'return}'
)

# E12 读档归一 / 老存档迁移（纯 ASCII，唯一）
A_MIG = 'lifespan:t.lifespan??t.maxLifespan??100,maxLifespan:t.maxLifespan??100,'
N_MIG = '...YlxwLifeMigrate(t),'

# E13 属性中文名表（\uXXXX 转义形态，唯一）
A_NAME = '"maxLifespan": "\\u6700\\u5927\\u5bff\\u5143", "lifespan": "\\u5bff\\u5143",'
N_NAME = '"maxLifespan": "\\u5bff\\u5143\\u4e0a\\u9650", "lifespan": "\\u5e74\\u9f84",'

# E14 YLXW_PILL_FX 标签表（\uXXXX 转义形态，唯一）
A_FX = ('      lifespan: "\\u5bff\\u547d(\\u5e74)", '
        'maxLifespan: "\\u5bff\\u547d\\u4e0a\\u9650(\\u5e74)"')
N_FX = ('      lifespan: "\\u5e74\\u9f84(\\u5c81)", '
        'maxLifespan: "\\u5bff\\u5143\\u4e0a\\u9650(\\u5e74)", '
        'ageReduce: "\\u5e74\\u9f84\\u51cf\\u5c11(\\u5c81)"')

# E15 丹方改造（字面中文，各唯一）
A_PILL_YS = ('result:{name:"延寿丹",type:H.Pill,description:"增加寿命的珍贵丹药，由千年人参和血参炼制而成，'
             '服用后能够延长10年寿命，是修士们延长寿元的珍贵丹药。",rarity:"稀有",effect:{lifespan:1}}')
N_PILL_YS = ('result:{name:"延寿丹",type:H.Pill,description:"增加寿元的珍贵丹药，由千年人参和血参炼制而成，'
             '服用后永久增加 3 年寿元上限，是修士们延长寿元的珍贵丹药。",rarity:"稀有",'
             'permanentEffect:{maxLifespan:3}}')
A_PILL_CS = ('result:{name:"长生丹",type:H.Pill,description:"增加寿命的极品丹药，由万年仙草和千年灵芝炼制而成，'
             '服用后能够延长50年寿命并增加最大寿命，是修士们延长寿元的珍贵丹药。",rarity:"传说",'
             'permanentEffect:{maxLifespan:3}}')
N_PILL_CS = ('result:{name:"长生丹",type:H.Pill,description:"增加寿元的极品丹药，由万年仙草和千年灵芝炼制而成，'
             '服用后永久增加 8 年寿元上限，是修士们延长寿元的珍贵丹药。",rarity:"传说",'
             'permanentEffect:{maxLifespan:8}}')
A_PILL_BS = ('result:{name:"不死仙丹",type:H.Pill,description:"传说中的不死仙丹，由万年灵乳、九叶芝草和龙鳞果炼制而成，'
             '服用后能够延长200年寿命并大幅增加最大寿命500年，是修士们梦寐以求的仙丹。",rarity:"仙品",'
             'effect:{lifespan:5},permanentEffect:{maxLifespan:8}}')
N_PILL_BS = ('result:{name:"不死仙丹",type:H.Pill,description:"传说中的不死仙丹，由万年灵乳、九叶芝草和龙鳞果炼制而成，'
             '服用后永久增加 20 年寿元上限，是修士们梦寐以求的仙丹。",rarity:"仙品",'
             'permanentEffect:{maxLifespan:20}}')

# E15b 新增减年龄丹（插入 Vr 数组尾，紧跟凤凰涅槃丹）
A_VR_END = 'speed:3}}}],qN=[...Dm,...Vr]'
NEW_PILLS = (
    ',{name:"驻颜丹",cost:6000,ingredients:[{name:"凝神花",qty:3},{name:"千年人参",qty:2}],'
    'result:{name:"驻颜丹",type:H.Pill,description:"驻颜有术的珍稀丹药，由凝神花与千年人参炼制而成，'
    '服用后可令容颜与年岁一同回转，减少 3 岁年龄。",rarity:"稀有",effect:{ageReduce:3}}}'
    ',{name:"返春丹",cost:30000,ingredients:[{name:"万年仙草",qty:2},{name:"千年灵芝",qty:3}],'
    'result:{name:"返春丹",type:H.Pill,description:"逆转光阴的传说丹药，由万年仙草与千年灵芝炼制而成，'
    '服用后可返老还童，减少 8 岁年龄。",rarity:"传说",effect:{ageReduce:8}}}'
)
N_VR_END = 'speed:3}}}' + NEW_PILLS + '],qN=[...Dm,...Vr]'

# E15c us 懒取表
A_US = '凤凰涅槃丹:()=>Qt("凤凰涅槃丹")},'
N_US = '凤凰涅槃丹:()=>Qt("凤凰涅槃丹"),驻颜丹:()=>Qt("驻颜丹"),返春丹:()=>Qt("返春丹")},'

# --------------------------------------------------------------------------- E17~E27 残留清理
# E17 $w 死亡 useEffect 依赖数组（★ 致命：不改则 age 变化不触发 effect，寿终永不判定）
A_DEP = 't==null?void 0:t.lifespan'
N_DEP = 't==null?void 0:t.age'

# E18 YLXW_R219_HARD 的 nat 分支（R-219 现仅剩 nat=false 调用点，需自洽）
A_R219NAT = 'nat&&(o.lifespan=Math.min(o.maxLifespan||100,10))'
N_R219NAT = 'nat&&(o.age=0)'

# E19 传承连跳 return 对象
A_INHRET = 'maxLifespan:Ie,lifespan:ue,'
N_INHRET = 'maxLifespan:Ie,age:ue,'

# E20 丹药 tooltip 即时效果（字面中文区段）
A_FXRENDER = ('t.effect.lifespan&&t.effect.lifespan>0&&'
              'e.jsxs("span",{children:["寿 +",Math.floor(t.effect.lifespan)]})')
N_FXRENDER = ('t.effect.ageReduce&&t.effect.ageReduce>0&&'
              'e.jsxs("span",{children:["年龄 -",Math.floor(t.effect.ageReduce)," 岁"]})')

# E21 iy 物品数值缩放尾部
A_IY = 't.lifespan!==void 0&&(h.lifespan=t.lifespan),h}'
N_IY = 't.ageReduce!==void 0&&(h.ageReduce=t.ageReduce),h}'

# E22 ry 丹药数值缩放
A_RY = 't.lifespan!==void 0&&(T.lifespan=t.lifespan)}'
N_RY = 't.ageReduce!==void 0&&(T.ageReduce=t.ageReduce)}'

# E23 法宝结算的死逗号表达式
A_COSTCOMMA = 'if(u.cost.lifespan,u.cost.maxHp){'
N_COSTCOMMA = 'if(u.cost.maxHp){'

# E24 Ic 品质缩放：maxLifespan 小值会被 l*0.8 抹成 0，加保底
A_ICMAX = 'd.maxLifespan!==void 0&&(d.maxLifespan=Math.floor(d.maxLifespan*u))'
N_ICMAX = 'd.maxLifespan!==void 0&&(d.maxLifespan=Math.max(1,Math.floor(d.maxLifespan*u)))'

# E25 丹药 tooltip 永久项文案（字面中文）
A_FXPERM = '"✨ 寿命上限永久 +",t.permanentEffect.maxLifespan'
N_FXPERM = '"✨ 寿元上限永久 +",t.permanentEffect.maxLifespan'

# E26 物品详情永久项文案（\uXXXX 转义区段）
A_ITEMPERM = ('["\\u6c38\\u4e45\\u5bff\\u547d +",'
              'w.permanentEffect.maxLifespan+"\\u5e74"]')
N_ITEMPERM = ('["\\u6c38\\u4e45\\u5bff\\u5143\\u4e0a\\u9650 +",'
              'w.permanentEffect.maxLifespan]')

# E27 sy() 内死映射表（装备加寿从未生效，已查实为死路径）
A_DEADMAP = ('speedBonus:"speed",maxHpBonus:"hp",'
             'maxLifespanBonus:"maxLifespan"}')
N_DEADMAP = 'speedBonus:"speed",maxHpBonus:"hp"}'

# E28 历练单次结算日志（字面中文）：+寿命 → 寿元上限 / −寿命 → 年龄
A_ADVCHLOG = ('t.lifespanChange&&d(t.lifespanChange>0?`✨ 寿命增加 '
              '${t.lifespanChange.toFixed(1)} 年`:`⚠️ 寿命减少 '
              '${Math.abs(t.lifespanChange).toFixed(1)} 年`,'
              't.lifespanChange>0?"gain":"danger")')
N_ADVCHLOG = ('t.lifespanChange&&d(t.lifespanChange>0?`✨ 寿元上限 +'
              '${t.lifespanChange.toFixed(1)} 年`:`⚠️ 年龄 +'
              '${Math.abs(t.lifespanChange).toFixed(1)} 岁`,'
              't.lifespanChange>0?"gain":"danger")')

# E29 历练会话汇总行（\uXXXX 转义区段）
A_ADVSUM = ('if (st.life && Math.abs(st.life) >= 0.05) __r179m.push(st.life > 0 ? '
            '"\\u5bff\\u547d\\u589e\\u52a0 " + st.life.toFixed(1) + " \\u5e74" : '
            '"\\u5bff\\u547d\\u51cf\\u5c11 " + Math.abs(st.life).toFixed(1) + " \\u5e74");')
N_ADVSUM = ('if (st.life && Math.abs(st.life) >= 0.05) __r179m.push(st.life > 0 ? '
            '"\\u5bff\\u5143\\u4e0a\\u9650 +" + st.life.toFixed(1) + " \\u5e74" : '
            '"\\u5e74\\u9f84 +" + Math.abs(st.life).toFixed(1) + " \\u5c81");')

EDITS = [
    ('I0 注入辅助函数块 YL_AGE_255（幂等标记 %s）' % MARK, A_INJ, N_INJ, 1),
    ('E1a 建号·寿命上限抽定隐藏比例', A_NEW1, N_NEW1, 1),
    ('E1b 建号·age:0 / lifeRatio / lifeBonus', A_NEW2, N_NEW2, 1),
    ('E2a 打坐·寿命−= → 年龄+=', A_MED, N_MED, 1),
    ('E2b 打坐速率 0.001 → 0.0002', A_MEDC, N_MEDC, 1),
    ('E3a 历练·寿命−= → 年龄+= / lifespanChange', A_ADV, N_ADV, 1),
    ('E3b 历练日志·寿元− → 年龄+', A_ADVLOG, N_ADVLOG, 1),
    ('E4a 突破·死线按 lifeRatio 增长', A_BT, N_BT, 1),
    ('E4b 突破日志·改寿元区间', A_BTLOG, N_BTLOG, 1),
    ('E4c 突破返回·lifespan → age', A_BTRET, N_BTRET, 1),
    ('E5a 传承·删死代码 T.baseMaxLifespan', A_INHDEAD, N_INHDEAD, 1),
    ('E5b 传承·死线按 lifeRatio 增长', A_INH, N_INH, 1),
    ('E5c 传承日志·改寿元区间', A_INHLOG, N_INHLOG, 1),
    ('E6 丹药 effect.lifespan → effect.ageReduce', A_PILLEFF, N_PILLEFF, 1),
    ('E7 丹药 permanentEffect.maxLifespan → lifeBonus', A_PILLPERM, N_PILLPERM, 1),
    ('E8a 离线·lifespanSpent → ageSpent', A_OFFDEF, N_OFFDEF, 1),
    ('E8b 离线·年龄 += ageSpent', A_OFFUSE, N_OFFUSE, 1),
    ('E9a 面板·进度条分母改区间上限', A_PANELF, N_PANELF, 1),
    ('E9b 面板·寿命 x/y → 年龄 · 寿元区间', A_PANELUI, N_PANELUI, 1),
    ('E10 预警·改比较区间下限', A_WARN, N_WARN, 1),
    ('E11 寿终·age>=deathLine → 清档重开', A_DEATH, N_DEATH, 1),
    ('E12 读档归一 / 老存档迁移', A_MIG, N_MIG, 1),
    ('E13 属性中文名表', A_NAME, N_NAME, 1),
    ('E14 YLXW_PILL_FX 标签表', A_FX, N_FX, 1),
    ('E15a 延寿丹 → 真实寿元 +3', A_PILL_YS, N_PILL_YS, 1),
    ('E15b 长生丹 → 真实寿元 +8', A_PILL_CS, N_PILL_CS, 1),
    ('E15c 不死仙丹 → 真实寿元 +20', A_PILL_BS, N_PILL_BS, 1),
    ('E15d 新增驻颜丹 / 返春丹（减年龄）', A_VR_END, N_VR_END, 1),
    ('E15e us 懒取表补两条新丹', A_US, N_US, 1),
    # ---- E17~E27 残留清理 ----
    ('E17 寿终 effect 依赖数组 lifespan→age', A_DEP, N_DEP, 1),
    ('E18 R-219 nat 分支 lifespan→age', A_R219NAT, N_R219NAT, 1),
    ('E19 传承返回 lifespan→age', A_INHRET, N_INHRET, 1),
    ('E20 丹药 tooltip 即时项→年龄', A_FXRENDER, N_FXRENDER, 1),
    ('E21 iy 缩放 lifespan→ageReduce', A_IY, N_IY, 1),
    ('E22 ry 缩放 lifespan→ageReduce', A_RY, N_RY, 1),
    ('E23 法宝结算删死逗号表达式', A_COSTCOMMA, N_COSTCOMMA, 1),
    ('E24 Ic 加寿保底 Math.max(1,...)', A_ICMAX, N_ICMAX, 1),
    ('E25 丹药 tooltip 永久项文案', A_FXPERM, N_FXPERM, 1),
    ('E26 物品详情永久项文案', A_ITEMPERM, N_ITEMPERM, 1),
    ('E27 sy() 删死映射 maxLifespanBonus', A_DEADMAP, N_DEADMAP, 1),
    ('E28 历练单次结算日志改年龄/寿元上限', A_ADVCHLOG, N_ADVCHLOG, 1),
    ('E29 历练会话汇总行改年龄/寿元上限', A_ADVSUM, N_ADVSUM, 1),
]

INJECT_LABEL = EDITS[0][0]

# --------------------------------------------------------------------------- E11 寿终块：整段替换
# 该块在 bundle 中是一整段连续文本，用「起点 + 中间段 + 尾部」三段拼接精确锚定。
A_DEATH_FULL = A_DEATH + DEATH_MID_A + DEATH_MID_B

# --------------------------------------------------------------------------- E16 法宝死代码（正则批量）
RE_TREASURE_COST = re.compile(r'cost:\{lifespan:\d+\},')
RE_TREASURE_DESC = re.compile(r'消耗\d+年寿命，')
A_TREASURE_RENDER = ('((Ye=se.battleEffect.cost)==null?void 0:Ye.lifespan)&&'
                     '`消耗寿命: ${se.battleEffect.cost.lifespan}年`,')
N_TREASURE_RENDER = ''


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。

    ★ 契约：dryrun_087 的 standalone 门禁 runner 只支持**字符串 needle**
      （`final_text.count(s)`）⇒ 本表不得出现 None 哨兵 / 正则分支 / 自算逻辑。
      注入块「纯 ASCII」与 E16 两条**正则计数**属本脚本内部断言，
      放在 `_self_checks()` 里由 main() fail-closed 调用，不混进本表。
    """
    return [
        # ---- 注入 ----
        ('注入·幂等标记唯一', MARK, 1, '==', ''),
        ('注入·YlxwAgeRoll 在位', 'function YlxwAgeRoll()', 1, '==', ''),
        ('注入·YlxwLifeUpper 在位', 'function YlxwLifeUpper(realm, lv)', 1, '==', ''),
        ('注入·YlxwLifeShow 在位', 'function YlxwLifeShow(p)', 1, '==', ''),
        ('注入·YlxwLifeDeathLine 在位', 'function YlxwLifeDeathLine(p)', 1, '==', ''),
        ('注入·YlxwLifeMigrate 在位', 'function YlxwLifeMigrate(t)', 1, '==', ''),
        ('注入·区间下限比例 0.9', 'var YLXW_AGE_MIN = 0.9;', 1, '==', ''),
        # ---- E1 ----
        ('E1a 新串在位', N_NEW1, 1, '==', ''),
        ('E1a 旧串清零', A_NEW1, 0, '==', ''),
        ('E1b 新串在位', N_NEW2, 1, '==', ''),
        ('E1b 旧串清零', A_NEW2, 0, '==', ''),
        # ---- E2 ----
        ('E2a 打坐新串在位', N_MED, 1, '==', ''),
        ('E2a 打坐旧串清零', A_MED, 0, '==', ''),
        ('E2b 打坐速率新值', N_MEDC, 1, '==', ''),
        ('E2b 打坐速率旧值清零', A_MEDC, 0, '==', ''),
        # ---- E3 ----
        ('E3a 历练新串在位', N_ADV, 1, '==', ''),
        ('E3a 历练旧串清零', A_ADV, 0, '==', ''),
        ('E3b 历练日志新串在位', N_ADVLOG, 1, '==', ''),
        ('E3b 历练日志旧串清零', A_ADVLOG, 0, '==', ''),
        # ---- E4 ----
        ('E4a 突破新串在位', N_BT, 1, '==', ''),
        ('E4a 突破旧串清零', A_BT, 0, '==', ''),
        ('E4b 突破日志新串在位', N_BTLOG, 1, '==', ''),
        ('E4b 突破日志旧串清零', A_BTLOG, 0, '==', ''),
        ('E4c 突破返回新串在位', N_BTRET, 1, '==', ''),
        ('E4c 突破返回旧串清零', A_BTRET, 0, '==', ''),
        # ---- E5 ----
        ('E5a 传承死代码清零', A_INHDEAD, 0, '==', ''),
        ('E5b 传承新串在位', N_INH, 1, '==', ''),
        ('E5b 传承旧串清零', A_INH, 0, '==', ''),
        ('E5c 传承日志新串在位', N_INHLOG, 1, '==', ''),
        ('E5c 传承日志旧串清零', A_INHLOG, 0, '==', ''),
        # ---- E6 / E7 ----
        ('E6 丹药减年龄新串在位', N_PILLEFF, 1, '==', ''),
        ('E6 丹药 effect.lifespan 清零', A_PILLEFF, 0, '==', ''),
        ('E7 丹药加寿新串在位', N_PILLPERM, 1, '==', ''),
        ('E7 丹药旧加寿串清零', A_PILLPERM, 0, '==', ''),
        # ---- E8 ----
        ('E8a 离线新串在位', N_OFFDEF, 1, '==', ''),
        ('E8a 离线旧串清零', A_OFFDEF, 0, '==', ''),
        ('E8b 离线消费新串在位', N_OFFUSE, 1, '==', ''),
        ('E8b 离线消费旧串清零', A_OFFUSE, 0, '==', ''),
        # ---- E9 / E10 ----
        ('E9a 面板进度条新串在位', N_PANELF, 1, '==', ''),
        ('E9a 面板进度条旧串清零', A_PANELF, 0, '==', ''),
        ('E9b 面板文案新串在位', N_PANELUI, 1, '==', ''),
        ('E9b 面板文案旧串清零', A_PANELUI, 0, '==', ''),
        ('E10 预警新串在位', N_WARN, 1, '==', ''),
        ('E10 预警旧串清零', A_WARN, 0, '==', ''),
        # ---- E11 ----
        ('E11 寿终新判定在位', 'if(t.age!==void 0&&t.age>=YlxwLifeDeathLine(t)){', 1, '==', ''),
        ('E11 寿终旧判定清零', A_DEATH, 0, '==', ''),
        ('E11 一次性闩锁在位', 'if(window.__ylR255Ended)return;window.__ylR255Ended=1;', 1, '==',
         '★ 不得用 setIsDead 当闩锁（会把旧 bk 弹窗叠在背后）'),
        ('E11 旧「重生」分支清零', 'R=Math.min(M.maxLifespan||100,10);return{...M,hp:h,lifespan:R}', 0, '==', ''),
        ('E11 清档链路在位', 'Xc(`${ln}/character/reset`,{method:"POST"})', 2, '==', '设置面板 1 处 + 寿终 1 处'),
        # ---- E12 / E13 / E14 ----
        ('E12 迁移 spread 在位', N_MIG, 1, '==', ''),
        ('E12 旧读档归一清零', A_MIG, 0, '==', ''),
        ('E13 属性名表新串在位', N_NAME, 1, '==', ''),
        ('E13 属性名表旧串清零', A_NAME, 0, '==', ''),
        ('E14 PILL_FX 新标签在位', N_FX, 1, '==', ''),
        ('E14 PILL_FX 旧标签清零', A_FX, 0, '==', ''),
        # ---- E15 ----
        ('E15a 延寿丹新定义在位', N_PILL_YS, 1, '==', ''),
        ('E15a 延寿丹旧定义清零', A_PILL_YS, 0, '==', ''),
        ('E15b 长生丹新定义在位', N_PILL_CS, 1, '==', ''),
        ('E15b 长生丹旧定义清零', A_PILL_CS, 0, '==', ''),
        ('E15c 不死仙丹新定义在位', N_PILL_BS, 1, '==', ''),
        ('E15c 不死仙丹旧定义清零', A_PILL_BS, 0, '==', ''),
        ('E15d 驻颜丹在位', 'name:"驻颜丹"', 2, '==', '配方名 + result.name'),
        ('E15d 返春丹在位', 'name:"返春丹"', 2, '==', '配方名 + result.name'),
        ('E15e us 表新条目', '驻颜丹:()=>Qt("驻颜丹"),返春丹:()=>Qt("返春丹")', 1, '==', ''),
        # ---- E16 法宝死代码（渲染分支逐字；两条正则计数见 _self_checks）----
        ('E16 法宝渲染分支清零', A_TREASURE_RENDER, 0, '==', ''),
        # ---- E17~E29 残留清理 ----
        ('E17 依赖数组新串在位', N_DEP, 1, '==', '寿终 effect 必须监听 age'),
        ('E17 依赖数组旧串清零', A_DEP, 0, '==', ''),
        ('E18 R219 nat 新串在位', N_R219NAT, 1, '==', ''),
        ('E18 R219 nat 旧串清零', A_R219NAT, 0, '==', ''),
        ('E19 传承返回新串在位', N_INHRET, 1, '==', ''),
        ('E19 传承返回旧串清零', A_INHRET, 0, '==', ''),
        ('E20 tooltip 新串在位', N_FXRENDER, 1, '==', ''),
        ('E20 tooltip 旧串清零', A_FXRENDER, 0, '==', ''),
        ('E21 iy 新串在位', N_IY, 1, '==', ''),
        ('E21 iy 旧串清零', A_IY, 0, '==', ''),
        ('E22 ry 新串在位', N_RY, 1, '==', ''),
        ('E22 ry 旧串清零', A_RY, 0, '==', ''),
        ('E23 法宝结算新串在位', N_COSTCOMMA, 1, '==', ''),
        ('E23 法宝结算旧串清零', A_COSTCOMMA, 0, '==', ''),
        ('E24 Ic 保底新串在位', N_ICMAX, 1, '==', '加寿不得被品质缩放抹成 0'),
        ('E24 Ic 保底旧串清零', A_ICMAX, 0, '==', ''),
        ('E25 永久项文案新串在位', N_FXPERM, 1, '==', ''),
        ('E25 永久项文案旧串清零', A_FXPERM, 0, '==', ''),
        ('E26 物品详情新串在位', N_ITEMPERM, 1, '==', ''),
        ('E26 物品详情旧串清零', A_ITEMPERM, 0, '==', ''),
        ('E27 死映射表清零', A_DEADMAP, 0, '==', '装备加寿死路径'),
        ('E28 历练日志新串在位', N_ADVCHLOG, 1, '==', ''),
        ('E28 历练日志旧串清零', A_ADVCHLOG, 0, '==', ''),
        ('E29 历练汇总新串在位', N_ADVSUM, 1, '==', ''),
        ('E29 历练汇总旧串清零', A_ADVSUM, 0, '==', ''),
        # ---- 全局残留 ----
        ('全局·player.lifespan 读取清零', '.lifespan??', 0, '==', '年龄制下不得再读 lifespan'),
        ('全局·lifespanSpent 清零', 'lifespanSpent', 0, '==', '已改名 ageSpent'),
        ('全局·maxLifespanBonus 清零', 'maxLifespanBonus', 0, '==', '死路径已删'),
        ('全局·法宝 cost.lifespan 清零', 'cost.lifespan', 0, '==', ''),
    ]


def _self_checks(out_txt):
    r"""本脚本内部断言（不属 dryrun 收录范围）：返回失败串列表（空 = 全绿）。

    ① 注入块「纯 ASCII」——块内中文必须全部 \uXXXX 转义（§9.2 纪律）。
    ② E16 法宝死代码两条**正则计数**（各 109 处，须清零）。
    ③ 注入块不得含网络/存储原语。
    """
    errs = []
    nb = sum(1 for ch in HELPER if ord(ch) >= 128)
    if nb:
        errs.append('注入块含非 ASCII 字符 %d 处（须全部 \\uXXXX 转义）' % nb)
    c_cost = len(RE_TREASURE_COST.findall(out_txt))
    if c_cost:
        errs.append('E16 法宝 cost:{lifespan:N} 残留 %d 处（须 0）' % c_cost)
    c_desc = len(RE_TREASURE_DESC.findall(out_txt))
    if c_desc:
        errs.append('E16 法宝「消耗N年寿命」残留 %d 处（须 0）' % c_desc)
    for ban in ('fetch(', 'XMLHttpRequest', 'setInterval('):
        if ban in HELPER:
            errs.append('注入块不得含 %s' % ban)
    return errs


# 各编辑「旧锚点」的实测形态：'ascii'=纯 ASCII；'lit'=字面中文；'esc'=\uXXXX 转义态
OLD_FORM = {
    'I0': 'ascii', 'E1a': 'ascii', 'E1b': 'ascii', 'E2a': 'ascii', 'E2b': 'ascii',
    'E3a': 'ascii', 'E3b': 'lit', 'E4a': 'ascii', 'E4b': 'lit', 'E4c': 'ascii',
    'E5a': 'ascii', 'E5b': 'ascii', 'E5c': 'esc',
    'E6': 'lit', 'E7': 'lit', 'E8a': 'ascii', 'E8b': 'ascii',
    'E9a': 'ascii', 'E9b': 'lit', 'E10': 'lit', 'E11': 'ascii',
    'E12': 'ascii', 'E13': 'esc', 'E14': 'esc',
    'E15a': 'lit', 'E15b': 'lit', 'E15c': 'lit', 'E15d': 'ascii', 'E15e': 'lit',
    'E17': 'ascii', 'E18': 'ascii', 'E19': 'ascii', 'E20': 'lit', 'E21': 'ascii',
    'E22': 'ascii', 'E23': 'ascii', 'E24': 'ascii', 'E25': 'lit', 'E26': 'esc',
    'E27': 'ascii', 'E28': 'lit', 'E29': 'esc',
}


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert MARK == '/*YLXW_R255_V2961*/', '幂等标记有误'

    # 注入块必须纯 ASCII（源码里所有中文均已 \uXXXX 转义）
    bad = [c for c in HELPER if ord(c) >= 128]
    assert not bad, '注入块含非 ASCII 字符: %r' % bad
    assert HELPER.count(MARK) == 1, '注入块须恰好含 1 个幂等标记'

    for name, old, new, n in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old, '%s 锚点不得为空' % name
        assert n >= 1, '%s n 必须 >=1' % name
        if name == INJECT_LABEL:
            assert all(ord(ch) < 128 for ch in old), '注入锚点应为纯 ASCII'
            assert new.startswith(old), '注入 new 必须以锚点开头'
            continue
        if not new:
            # 纯删除类编辑（如 E5a 删死代码），只允许已知项
            assert name.startswith('E5a'), '%s 不得为空串（仅 E5a 允许删除）' % name
            continue
        tag = name.split(' ', 1)[0]
        form = OLD_FORM[tag]
        if form == 'ascii':
            assert all(ord(ch) < 128 for ch in old), '%s 旧锚点应为纯 ASCII' % tag
        elif form == 'lit':
            assert any(ord(ch) >= 128 for ch in old), '%s 旧锚点应为字面中文' % tag
        else:
            assert all(ord(ch) < 128 for ch in old), '%s 转义态锚点必须纯 ASCII' % tag
            assert '\\u' in old, '%s 转义态锚点须含 \\uXXXX' % tag

    # E11 寿终块必须整体锚定（三段拼接后仍在 EDITS 中）
    assert A_DEATH_FULL == A_DEATH + DEATH_MID_A + DEATH_MID_B
    assert 'YLXW_R219_HARD($,!0,c)' in A_DEATH_FULL, 'E11 旧锚点须含 R-219 hard 分支'
    assert '但天道的仁慈让你得以重生' in A_DEATH_FULL, 'E11 旧锚点须含旧重生文案'
    assert 'YLXW_R219_HARD' not in N_DEATH, 'E11 新串不得再走 R-219 hard 重生'
    assert 'lifespan' not in N_DEATH, 'E11 新串不得残留 lifespan'

    # E1：两次抽取必须共用同一个随机值
    assert 'YlxwAgeRoll()' in N_NEW1, 'E1a 须抽定随机比例'
    assert 'YlxwAgeRoll()' not in N_NEW2, 'E1b 不得二次抽取（须复用 M/$）'
    assert 'age:0' in N_NEW2 and 'lifeBonus:0' in N_NEW2, 'E1b 须 age:0 / lifeBonus:0'

    # E2：年龄递增
    assert N_MED.startswith('age:'), 'E2a 必须写 age 而非 lifespan'
    assert 'lifespan' not in N_MED, 'E2a 不得残留 lifespan'

    # E4：死线按 lifeRatio 增长、age 不变
    assert 'g.lifeRatio??1' in N_BT, 'E4a 死线须按 lifeRatio 增长'
    assert 'ke=g.age??0' in N_BT, 'E4a 突破不得改变年龄'

    # E9/E10：面板与预警只读派生量（注意 CSS 类名 lifespan-warning 是合法的，只查字段访问）
    for tag, s in (('E9a', N_PANELF), ('E9b', N_PANELUI), ('E10', N_WARN)):
        assert '.lifespan' not in s, '%s 不得残留 .lifespan 字段访问' % tag

    # E15d：新丹效果键必须是 ageReduce
    assert N_VR_END.count('ageReduce') == 2, 'E15d 两条新丹都须用 ageReduce'
    assert 'name:"驻颜丹"' in N_VR_END and 'name:"返春丹"' in N_VR_END

    # E16 正则：旧态计数必须在基线为 109，新态为 0
    assert RE_TREASURE_COST.pattern and RE_TREASURE_DESC.pattern

    # 注入内容不得含网络/存储原语（E11 是有意为之，属既有区块改写，不计入）
    for _n, _o, nw, _c in EDITS:
        if _n.startswith('E11'):
            continue
        for ban in ('fetch(', 'XMLHttpRequest', 'setInterval('):
            assert ban not in nw, '注入内容不得含 %s' % ban


# 补丁态特征串（用于幂等判定）
PATCH_SIGS = [MARK, N_NEW2, N_MED, N_PANELUI,
              'if(t.age!==void 0&&t.age>=YlxwLifeDeathLine(t)){']
BASE_SIGS = [A_NEW2, A_MED, A_PANELUI, A_DEATH]


def _classify(txt):
    """判定基线态：'patched' / 'baseline' / 'partial'。"""
    n_new_ok = sum(1 for s in PATCH_SIGS if txt.count(s) == 1)
    n_old_ok = sum(1 for s in BASE_SIGS if txt.count(s) == 1)
    if n_new_ok == len(PATCH_SIGS) and n_old_ok == 0:
        return 'patched'
    if n_new_ok == 0 and n_old_ok == len(BASE_SIGS):
        return 'baseline'
    return 'partial'


def _apply(txt):
    """应用全部编辑（EDITS + E11 整段 + E16 正则批量）。返回 (新文本, 统计)。"""
    stats = {}
    out = txt
    for name, old, new, n in EDITS:
        if name.startswith('E11'):
            continue
        out = out.replace(old, new, n)
    # E11：寿终块整段替换（EDITS 中只登记了起点，避免重复替换）
    out, c11 = _replace_span(out, A_DEATH_FULL, N_DEATH)
    stats['E11'] = c11
    # E16：法宝死代码正则批量
    out, c16a = RE_TREASURE_COST.subn('', out)
    out, c16b = RE_TREASURE_DESC.subn('', out)
    out, c16c = _replace_span(out, A_TREASURE_RENDER, N_TREASURE_RENDER)
    stats['E16'] = (c16a, c16b, c16c)
    return out, stats


def _replace_span(txt, old, new):
    """把 old 的每一处出现整体替换为 new，返回 (新文本, 替换处数)。"""
    if not old:
        return txt, 0
    cnt = txt.count(old)
    if cnt:
        txt = txt.replace(old, new)
    return txt, cnt


def _node_check(out_bytes, node_bin):
    """对产物跑 `node --check`（fail-closed）；找不到 node 则告警跳过。"""
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check（可用 --node 显式指定）')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r255chk-', suffix='.js')
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
    """打印关键落点补丁前后的对照。"""
    def view(txt, key, pre=60, post=260):
        i = txt.find(key)
        if i < 0:
            return '<未找到 %r>' % key
        return txt[max(0, i - pre):i + post]

    pairs = [
        ('E9b 面板', '年龄 / 寿元'),
        ('E11 寿终', 'if(t.age!==void 0&&t.age>=YlxwLifeDeathLine(t)){'),
        ('E12 迁移', '...YlxwLifeMigrate(t),'),
        ('E15d 新丹', 'name:"驻颜丹"'),
    ]
    for tag, key in pairs:
        print('\n---- %s · 补丁后 ----\n%s' % (tag, view(out_txt, key)))
    print('\n---- 面板 · 补丁前 ----\n%s' % view(txt0, '寿命 (年)'))


def main() -> int:
    ap = argparse.ArgumentParser(description='R-255 寿命重构（年龄制）（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js')
    ap.add_argument('--node', default=None, help='node 可执行文件（缺省自动探测 PATH）')
    ap.add_argument('--dump', action='store_true', help='只打印对照，不写盘')
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
        print('[SKIP] source looks already patched（R-255 年龄制已在位）')
        return 3
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 2) 基线碰撞检查：新串不得已在基线出现
    #    例外：纯收缩类编辑（new 是 old 的子串，如 E26/E27 只删尾部），new 必然已在基线出现
    for _name, _old, new, _n in EDITS:
        if _name.startswith('E11') or not new:
            continue
        if new in _old:
            continue
        c = txt0.count(new)
        if c != 0:
            print('[FAIL] 新串已在基线出现 %d 次，拒绝写盘：%s' % (c, new[:60]))
            return 2

    # 3) 锚点计数（rc=2 面）
    for name, old, _new, n in EDITS:
        if name.startswith('E11'):
            continue
        c = txt0.count(old)
        if c != n:
            print('[FAIL] %s 锚点出现 %d 次（期望 %d）' % (name, c, n))
            return 2
    # E11 整段
    c11 = txt0.count(A_DEATH_FULL)
    if c11 != 1:
        print('[FAIL] E11 寿终块整段锚点出现 %d 次（期望 1）' % c11)
        return 2
    # E16 正则基线计数
    c16a = len(RE_TREASURE_COST.findall(txt0))
    c16b = len(RE_TREASURE_DESC.findall(txt0))
    c16c = txt0.count(A_TREASURE_RENDER)
    print('  E16 基线计数：cost=%d desc=%d render=%d' % (c16a, c16b, c16c))
    if not (c16a == c16b == 109 and c16c == 1):
        print('[FAIL] E16 基线计数不符（期望 109/109/1）')
        return 2

    # 4) 应用
    out_txt, stats = _apply(txt0)
    out = out_txt.encode('utf-8')

    if a.dump:
        _dump_views(txt0, out_txt)
        print('\n  E11 替换 %d 处；E16 正则 %r' % (stats['E11'], stats['E16']))
        print('\n[DUMP] 仅预览，未写盘')
        return 0

    # 5) 门禁（字符串 needle，dryrun 可收录）
    ok = True
    for label, needle, exp, op, note in gates():
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-34s actual=%d expect %s %d'
              % ('OK' if good else 'FAIL', label, act, op, exp))
    # 5b) 本脚本内部断言（非 ASCII / E16 两条正则 / 注入块禁用原语）
    for _e in _self_checks(out_txt):
        ok = False
        print('  [FAIL] 自查·%s' % _e)
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 6) 往返自证
    #    6a) 逐条 EDITS 反向替换必须逐字节回到基线
    back = out_txt
    for _name, old, new, n in reversed(EDITS):
        if _name.startswith('E11'):
            continue
        if not new:
            continue
        assert back.count(new) == n, '往返自证：%s new 计数 != %d' % (_name, n)
        back = back.replace(new, old, n)
    # E5a 纯删除项：把删掉的死代码补回原位置
    assert back.count('const X=Math.max(0,f.exp-f.maxExp)') == 1, \
        '往返自证：E5a 回填位置不唯一'
    back = back.replace('const X=Math.max(0,f.exp-f.maxExp)',
                        A_INHDEAD + 'const X=Math.max(0,f.exp-f.maxExp)', 1)
    # 6b) E11 寿终块整段回滚
    back, r11 = _replace_span(back, N_DEATH, A_DEATH_FULL)
    if r11 != 1:
        print('[FAIL] 往返自证：E11 回滚失败（%d 处）' % r11)
        return 1
    # 6c) E16 为正则批量删除，不可逐字回滚；改用强不变量：
    #     「回滚后的文本」必须逐字节等于「基线文本先做同样的 E16 剥离」
    exp = txt0
    exp, _ = RE_TREASURE_COST.subn('', exp)
    exp, _ = RE_TREASURE_DESC.subn('', exp)
    exp, _ = _replace_span(exp, A_TREASURE_RENDER, N_TREASURE_RENDER)
    if back != exp:
        d = next((i for i in range(min(len(back), len(exp))) if back[i] != exp[i]),
                 min(len(back), len(exp)))
        print('[FAIL] 往返自证：E16 剥离后与基线不等（首个差异 @%d）' % d)
        print('   back: %r' % back[max(0, d - 60):d + 60])
        print('   exp : %r' % exp[max(0, d - 60):d + 60])
        return 1
    print('  [OK] 往返自证：除 E16 正则批量外，逐字节回到基线')

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 7) node 自检（fail-closed）
    if not _node_check(out, a.node):
        print('[FAIL] node --check 失败，未写盘')
        return 1

    # 8) 改前 .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r255-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r255-', suffix='.tmp')
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
