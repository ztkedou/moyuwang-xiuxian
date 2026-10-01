# -*- coding: utf-8 -*-
r"""
yl_r080_ext.py — R-080 抽奖：补「传说/仙品」保底提示（两行：稀有 + 传说）

复刻目标（上游 JeasonLoop/react-xiuxian-game a8f9810a）
--------------------------------------------------------------------------
  constants/lottery.ts:
      LOTTERY_RARE_PITY_INTERVAL        = 10   // 10 抽必出稀有以上
      LOTTERY_SOFT_PITY_LEGEND_INTERVAL = 50   // 50 抽软保底传说/仙品
      getLotteryPityProgress(count) => { rareRemain, legendRemain }
  components/LotteryModal.tsx: UI 两行提示
      「再抽 N 次必出稀有以上」 + 「再抽 N 次必出传说/仙品」

★ 侦察结论（本次实测，纠正任务书的前提）
--------------------------------------------------------------------------
  任务书以为「缺的是传说/仙品软保底」。**实测：传说保底逻辑早就在我们的冻结基座里**：
      产物（v26m 2026-09-27 起，直到当前 v290）逐字含
          const rk=50,lk=8e3;
          for(let g=0;g<S;g++){const q=T+g+1,
              w=q%rk===0&&M.length>0&&E>0,   // ← 每累计 50 抽，强制从 传说/仙品池(M) 取
              A=q%10===0;                    // ← 每累计 10 抽，强制从 稀有以上池($) 取
            if(w){...N(M,E)...} else if(A){...N($,R)...} else {...N(ms,h)...}}
  ⇒ 「50 抽内必出传说/仙品」**已经满足**（硬保底，每累计 50 抽强制给；q 为累计抽奖序号，
     与上游 `lotteryCount % 50` 口径同源）。
  缺的**只是 UI 文案**：产物里「必出稀有」x2、「必出传说」x0（全仓 grep 实证）。
  ⇒ 本模块**只补 UI**，不动抽奖逻辑 ⇒ **平均每次抽奖期望收益 0 变化**（经济零影响）。

  为什么不加「概率递增式软保底」
      ① 上游常量名虽叫 SOFT_PITY，但 UI 文案是「再抽 N 次**必出**」= 硬保底语义，与基座
         `q%rk===0` 完全一致；我们**没有上游 TSX**，凭空造递增曲线 = 发明行为，不是复刻。
      ② 递增曲线会抬高传说产出 ⇒ 抬高抽奖的灵石/修为折算期望，与本轮「灵石产出刚压过一轮」
         的经济红线冲突（无收益、纯风险）。
      ③ 基座已有硬保底已满足需求，改动面越小越好。
      ⇒ 采用「第 50 抽强制给」的硬保底（= 现有实现），UI 如实展示。

本模块动作（2 处就地替换）
--------------------------------------------------------------------------
  E1 完整抽奖面板（NM）保底行：原「(再抽 N 次必出稀有以上)」单行
     → 「累计抽奖: N 次」+「再抽 N 次必出稀有以上」+「再抽 N 次必出传说/仙品」三行
     （口径严格照上游 getLotteryPityProgress：rareRemain=10-count%10、legendRemain=50-count%50，
       count%10==0 时上式自然得 10/50，与上游三目写法等价。）
  E2 合并面板右列紧凑卡（v2810d 的 YlxwTDrawQuick）静态提示
     → 同一口径的两行动态提示（该卡持有 cnt=lotteryCount）。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 不碰抽奖执行体 `ck` / `handleDraw`、不碰奖品池 `ms`、不碰 `rk`/`q%rk===0`/`q%10===0`。
  · E1 锚点是**基座原文（raw 中文）**；E2 锚点是 **v2810d 注入块（zh() 后的 \uXXXX 字面量）**
    —— 两者形态不同，不可互换（E2 用 raw 字符串保 \u 不被 Python 转义）。
  · 本模块就地替换，无 INJECT_JS；每个 replace 带 expect=精确次数；门禁含冻结证据。
  · 只新建本文件；不改 build_v26n.py / localtest/* / srv/index_v28.ts。
  · 必须排在 `v2810d` 之后（E2 的锚点是它注入的文本）。
"""

import re

INJECT_JS = ''          # 本模块只做就地替换，不需要额外注入块

# --------------------------------------------------------------------------- 锚点

# —— E1 完整抽奖面板（NM）保底行（基座原文，raw 中文）——
PITY_OLD = (
    'e.jsxs("div",{className:"text-xs text-stone-500 mt-2",children:["\u7d2f\u8ba1\u62bd\u5956: ",'
    'a.lotteryCount," \u6b21",a.lotteryCount>=10&&a.lotteryCount%10!==0&&e.jsxs("span",'
    '{className:"text-yellow-400 ml-2",children:["(\u518d\u62bd ",10-a.lotteryCount%10,'
    '" \u6b21\u5fc5\u51fa\u7a00\u6709\u4ee5\u4e0a)"]})]})'
)

# 三行：累计次数 / 稀有保底 / 传说保底（照上游 getLotteryPityProgress 口径）
PITY_NEW = (
    'e.jsxs("div",{className:"text-xs text-stone-500 mt-2",children:["\u7d2f\u8ba1\u62bd\u5956: ",'
    'a.lotteryCount," \u6b21"]}),'
    'e.jsxs("div",{className:"text-xs text-yellow-400 mt-1",children:["\u518d\u62bd ",'
    '10-a.lotteryCount%10," \u6b21\u5fc5\u51fa\u7a00\u6709\u4ee5\u4e0a"]}),'
    'e.jsxs("div",{className:"text-xs text-purple-400 mt-0.5",children:["\u518d\u62bd ",'
    '50-a.lotteryCount%50," \u6b21\u5fc5\u51fa\u4f20\u8bf4/\u4ed9\u54c1"]})'
)

# —— E2 合并面板右列紧凑卡静态提示（v2810d 注入块，\uXXXX 字面量；raw 字符串保 \u 原样）——
QUICK_HINT_OLD = (
    r'"\u5341\u8fde\u62bd\u5fc5\u51fa\u7a00\u6709\u4ee5\u4e0a\u54c1\u8d28\uff1b'
    r'\u62bd\u5230\u9ad8\u9636\u7269\u54c1\u4f1a\u6298\u7b97\u4e3a\u7075\u77f3\u4e0e\u4fee\u4e3a\u3002"'
)
QUICK_HINT_NEW = (
    r'("\u518d\u62bd " + (10 - cnt % 10) + " \u6b21\u5fc5\u51fa\u7a00\u6709\u4ee5\u4e0a\uff1b'
    r'\u518d\u62bd " + (50 - cnt % 50) + " \u6b21\u5fc5\u51fa\u4f20\u8bf4/\u4ed9\u54c1\u3002")'
)

# —— 冻结证据（只读，不动）——
RK_KEEP = 'const rk=50,lk=8e3;'
LEGEND_BRANCH_KEEP = 'q%rk===0&&M.length>0&&E>0'
RARE_BRANCH_KEEP = 'q%10===0'
CK_KEEP = 'function ck(t){const r=Be(S=>S.player)'
QUICK_DEF_KEEP = 'function YlxwTDrawQuick(p) {'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    zh = ctx['zh']

    # 就地替换锚点里本来就有中文（E1 是 raw 中文，E2 是 \uXXXX 字面量），
    # 故不做 zh() ASCII 自检；改为验「替换串非空且含预期片段」防手滑。
    if '\u518d\u62bd ' not in PITY_NEW:
        raise AssertionError('r080 E1 替换串异常：没找到「再抽」')
    if '50-a.lotteryCount%50' not in PITY_NEW:
        raise AssertionError('r080 E1 替换串异常：缺传说保底表达式')
    if '50 - cnt % 50' not in QUICK_HINT_NEW:
        raise AssertionError('r080 E2 替换串异常：缺传说保底表达式')

    p.replace('r080-nm-pity', PITY_OLD, PITY_NEW, expect=1,
              note='完整抽奖面板保底行：稀有单行 -> 稀有 + 传说 两行（照上游口径）')
    p.replace('r080-quick-hint', QUICK_HINT_OLD, QUICK_HINT_NEW, expect=1,
              note='合并面板右列紧凑卡静态提示 -> 两行动态保底提示')

    gates = [
        # ================= E1 完整面板 =================
        ('R80·稀有保底行已就位',   '10-a.lotteryCount%10',                      1, '==', '照上游 rareRemain'),
        ('R80·传说保底行已就位',   '50-a.lotteryCount%50',                      1, '==', '照上游 legendRemain'),
        ('R80·传说行样式已就位',   'text-purple-400 mt-0.5',                    1, '==', '与稀有行区分'),
        ('R80·旧单行稀有条件已清零', 'a.lotteryCount>=10&&a.lotteryCount%10!==0', 0, '==', '旧单行展示条件'),
        ('R80·旧稀有 span 已清零',  '(\u518d\u62bd ',                            0, '==', '旧「(再抽 N 次必出稀有以上)」'),
        # ================= E2 紧凑卡 =================
        ('R80·紧凑卡传说行已就位', '50 - cnt % 50',                             1, '==', '同一口径'),
        ('R80·紧凑卡稀有行已就位', '10 - cnt % 10',                             1, '==', ''),
        ('R80·紧凑卡旧静态提示已清零', QUICK_HINT_OLD,                          0, '==', 'v2810d 静态文案'),
        # ================= 冻结：抽奖逻辑一字不动 =================
        ('冻结·传说硬保底常数 rk=50 未动', RK_KEEP,                             1, '==', '基座已实装，不动'),
        ('冻结·传说保底分支未动',   LEGEND_BRANCH_KEEP,                         1, '==', 'q%rk===0 强制传说/仙品'),
        ('冻结·稀有保底分支未动',   RARE_BRANCH_KEEP,                           1, '==', 'q%10===0 强制稀有以上'),
        ('冻结·抽奖执行体 ck 未动', CK_KEEP,                                    1, '==', ''),
        ('冻结·券不足校验未动',     'if(!d||d.lotteryTickets<S){f("\u62bd\u5956\u5238\u4e0d\u8db3\uff01","danger");return}', 1, '==', ''),
        ('冻结·紧凑卡未重写',       QUICK_DEF_KEEP,                             1, '==', ''),
        ('冻结·完整面板未重写',     'NM=({isOpen:t,onClose:r,player:a,onDraw:l})', 1, '==', ''),
    ]
    return gates
