# -*- coding: utf-8 -*-
r"""
yl_daily_ext.py — R-027「日常任务：把每一项获取方式写进描述」客户端单模块

需求原文（用户）
--------------------------------------------------------------------------
  「日常任务把每一项获取方式写进描述中」

侦察（构建产物 index-v2811-20260930.js 逐字实证）
--------------------------------------------------------------------------
  · 任务模板数组 `$3=[{type:"meditate",name:"晨光吐纳",description:"在清晨完成打坐修炼，吸收天地灵气",...}]`
    （@457030）—— `description` 是**风味文案**，不含「怎么完成」。
  · **「获取方式」现成表**：`q3={meditate:{type,name,description:"完成指定次数的打坐修炼",rewardMultiplier:1},
    adventure:{…"完成指定次数的历练"},breakthrough:{…"完成指定次数的境界突破"},alchemy:{…"炼制指定数量的丹药"},
    equip:{…"强化指定次数的装备"},pet:{…"喂养或进化灵宠指定次数"},sect:{…"完成指定次数的宗门任务"},
    realm:{…"探索指定次数的秘境"}}`（@455358，**depth=1**，全仓仅此一处 depth≤1 的 q3；
    另一处 q3 在 @1322139 是 depth=7 的局部 const，不构成遮蔽）。
  · 任务实例在 `uk({player,setPlayer,addLog})` 内构造（@1728681），
    `description` 直接取模板 `x.description`（两处 push）。
  · 卡片渲染 `qM=({quest:t,...})`（@1606695，depth=2）：
    `e.jsx("p",{className:"text-stone-400 text-sm mb-2",children:t.description})`（全仓恰好 1 处，
    另一处同名 className 在丹方面板 @1656049，children 不同）。
  · 日常任务弹窗 `$.map(R=>e.jsx(qM,{quest:R,...}))`（@1606526）—— `qM` 是**唯一**的日常任务卡。

改法（1 处注入 + 1 处渲染改写）
--------------------------------------------------------------------------
  注入 `YLXW_QuestGuide(type)`（函数声明提升；**惰性**读 `q3`，调用时必已初始化），
  在卡片渲染时把「获取方式」追加进描述：
      `在清晨完成打坐修炼，吸收天地灵气（获取方式：完成指定次数的打坐修炼）`

  ★ 为什么改**渲染**而不是改**构造**：
    构造只在「新生成任务」时生效（旧档当日任务文案不变）；渲染改写对
    **存量存档 + 新生成任务一律生效**，且不动任何存档字段（纯展示层）。

硬约束
--------------------------------------------------------------------------
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS。
  · 只读 `q3`（try/catch 兜底，取不到则**原样输出**，绝不抛错）。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py、不写 build/assets/。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R027: 日常任务「获取方式」写进描述 =====
   现成表 q3[type].description 即「完成指定次数的打坐修炼」等获取方式；
   本函数惰性读取（调用发生在渲染期，q3 必已初始化），try/catch 兜底。 */
function YLXW_QuestGuide(type) {
  try {
    var d = q3 && q3[type] && q3[type].description;
    return d ? String(d) : "";
  } catch (e) { return ""; }
}
'''

# --------------------------------------------------------------------------- 锚点常量

# 注入锚：v2810c 块内的模块级函数（depth=2；q3 在 depth=1，可被本函数读到）
INJECT_ANCHOR = 'function YlxwFtHarvestText(cd, slot) {'

# 渲染改写：日常任务卡片 qM 的描述行（全仓唯一）
DESC_OLD = 'e.jsx("p",{className:"text-stone-400 text-sm mb-2",children:t.description})'
DESC_NEW = (r'e.jsx("p",{className:"text-stone-400 text-sm mb-2",'
            r'children:(t.description||"")+(YLXW_QuestGuide(t.type)?"\uff08\u83b7\u53d6\u65b9\u5f0f\uff1a"+YLXW_QuestGuide(t.type)+"\uff09":"")})')


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('daily 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 模块级工具函数（depth=2；函数声明提升，位置无关）
    p.insert_before('daily-guide-helper', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 YLXW_QuestGuide（惰性读 q3）')

    # 1) 渲染改写
    p.replace('daily-desc-render', DESC_OLD, DESC_NEW, expect=1,
              note='日常任务卡描述追加「获取方式」')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 注入块 =================
        ('R27·获取方式函数已注入',   'function YLXW_QuestGuide(type) {', 1, '==', ''),
        ('R27·惰性读 q3（不写死）',  'var d = q3 && q3[type] && q3[type].description;', 1, '==', '现成表 q3 即获取方式'),
        ('R27·取不到原样输出',       r'return d ? String(d) : "";', 1, '==', ''),
        ('R27·异常兜底',             'return d ? String(d) : "";\n  } catch (e) { return ""; }\n}', 1, '==', ''),
        # ================= 渲染改写 =================
        ('R27·描述已追加获取方式',   r'children:(t.description||"")+(YLXW_QuestGuide(t.type)?"\uff08\u83b7\u53d6\u65b9\u5f0f\uff1a"+YLXW_QuestGuide(t.type)+"\uff09":"")})', 1, '==', ''),
        ('R27·旧描述渲染仅余 3 处',  'children:t.description})', 3, '==', '原 4 处，qM 那处已改写为追加式'),
        ('R27·标签文案为「获取方式」', r'"\uff08\u83b7\u53d6\u65b9\u5f0f\uff1a"', 1, '==', ''),
        # ================= q3 现成表在位（8 类获取方式；q3 用字面中文） =================
        ('R27·q3 表在位',            'q3={meditate:{type:"meditate",name:"打坐修炼"', 1, '==', ''),
        ('R27·8 类·打坐',            'description:"完成指定次数的打坐修炼"', 1, '==', ''),
        ('R27·8 类·历练',            'description:"完成指定次数的历练"', 1, '==', ''),
        ('R27·8 类·突破',            'description:"完成指定次数的境界突破"', 1, '==', ''),
        ('R27·8 类·炼丹',            'description:"炼制指定数量的丹药"', 1, '==', ''),
        ('R27·8 类·强化',            'description:"强化指定次数的装备"', 1, '==', ''),
        ('R27·8 类·灵宠',            'description:"喂养或进化灵宠指定次数"', 1, '==', ''),
        ('R27·8 类·宗门',            'description:"完成指定次数的宗门任务"', 1, '==', ''),
        ('R27·8 类·秘境',            'description:"探索指定次数的秘境"', 1, '==', ''),
        # ================= 冻结（不得回踩任务本体） =================
        ('冻结·任务模板 $3 未动',    '$3=[{type:"meditate",name:"', 1, '==', ''),
        ('冻结·任务构造未动（分支1）', 'description:x.description,target:T,progress:0', 1, '==', ''),
        ('冻结·任务构造未动（分支2）', 'description:M.description,target:h,progress:0', 1, '==', ''),
        ('冻结·任务卡 qM 唯一',      'qM=({quest:t,onClaimReward:r,isClaimed:a,realm:YlqR})=>{', 1, '==', ''),
        ('冻结·进度条渲染未动',      'children:[t.progress," / ",t.target]', 1, '==', ''),
        ('冻结·日常任务弹窗未动',    '$.map(R=>{var E;return e.jsx(qM,{quest:R,', 1, '==', ''),
        ('R27·未新增网络调用',       'fetch(', 0, '==', '纯展示层，无网络',
         ('/* ===== yl-R027:', 'function YlxwFtHarvestText(cd, slot) {')),
    ]
    return gates
