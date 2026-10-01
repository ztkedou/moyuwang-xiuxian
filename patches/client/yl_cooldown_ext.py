# -*- coding: utf-8 -*-
r"""
yl_cooldown_ext.py — 冷却机制修复（setCooldown 不支持 updater）+ 历练冷却还原**上游原版口径**

★ 这是**真 bug 修复**，不是新功能。发现过程与实测数据见 `报告_冷却失效bug.md`。

根因（代码 + 运行时双重确证）
--------------------------------------------------------------------------
构建产物里 UI store 的三个 setter 写法不一致：

    setPlayer:a=>{t(l=>({player:typeof a=="function"?a(l.player):a}))},      ← 支持 updater ✓
    setSettings:a=>{t(l=>{const c=typeof a=="function"?a(l.settings):a;…})}, ← 支持 updater ✓
    setCooldown:a=>t({cooldown:a}),                                         ← ★ 不支持 updater ✗

而被动回复 `Lw({player:t,setPlayer:r,setCooldown:a})` 每秒调：
    r(x=>{…})          // setPlayer，updater 正常
    a(x=>x>0?x-1:0)    // ★ setCooldown 收到「函数」⇒ 直接把函数写进 cooldown 字段

⇒ `cooldown` 字段变成**函数** ⇒ 全仓所有 `cooldown>0` 守卫恒为 **false**
  ⇒ **冷却机制彻底失效**（自动历练 / 自动打坐 / 手动打坐 / 商店跳过 / 避战 全部不受节流）。

运行时实证（沙盒 s5 / Playwright，见 `报告_冷却失效bug.md`）
  · `typeof Ze.getState().cooldown` === **"function"**（应为 "number"）
  · 自动历练实测周期 **2002ms**（代码意图 6000ms）—— 冷却只挡了约 500ms
  · `cooldown` 采样 450 点中 **430 点(96%) 是 function**，仅 20 点是数字
  · 自动打坐 30 秒产出 修为+107,277 / 灵石+2,103（长生境 9 层）

影响（解释了用户的多条体感）
  · R-026「历练刷太快、内容看不清」← 实际 2 秒/次，不是 6 秒
  · R-024「1 小时打坐灵石 27 万」    ← 冷却失效 ⇒ 跳频远超设计值
  · R-022「打坐降频没效果」          ← `_.current(2)` 同样被覆盖成函数

改法
--------------------------------------------------------------------------
  R1  `setCooldown` 与 `setPlayer` / `setSettings` 同构（支持 updater）
        `setCooldown:a=>t({cooldown:a})`
      → `setCooldown:a=>t(_ylcs=>({cooldown:typeof a=="function"?a(_ylcs.cooldown):a}))`
      ★ 用独立变量名 `_ylcs`，不与 store 创建器内的 `t`(set)/`r`(get)/`l` 撞名。

  R2  历练冷却**还原为上游原版口径**（用户 2026-09-30 拍板：「历练刷新的模式就参照
      上游的原版设置」）。我方 0.8.2 / 0.8.3 曾把 9 个冷却点统一 ×2 到 1/1/2/4/.4/1/2/6/6，
      本环按上游基线 `b822f2d` 的 `views/adventure/useAdventureHandlers.ts` 原值还原：

      | 冷却点                | 我方 0.8.3 现值 | **上游原版** | 证据（b822f2d 行号） |
      |-----------------------|-----------------|--------------|----------------------|
      | ① 避战（A 内）        | `d(6)`          | **`d(1)`**   | `:143` `setCooldown(1)` |
      | ② 避战（DS 分支）     | `d(6)`          | **`d(1)`**   | `:267` `setCooldown(1)` |
      | ③ 正常收尾 finally    | `d(6)`          | **`d(2)`**   | `:501-503` `setCooldown(2)` |
      | ④ 商店跳过            | `d(6)`          | **`d(2)`**   | `:181` `setCooldown(2)` |
      | ⑤ 挑战 boss 初始化    | `d(1)`          | **`d(2)`**   | `:386` `setCooldown(2)` |
      | ⑥ 天地之魄·跳过       | `d(1)`          | `d(1)`（不变）| `:427` `setCooldown(1)` |
      | ⑦ 天地之魄·战后       | `d(4)`          | **`d(2)`**   | `:420` `setCooldown(2)` |
      | ⑧ 天地之魄·避开       | `d(.4)`         | **`d(1)`**   | `:425-427` `setCooldown(1)` |
      | ⑨ 商店访问            | `d(1)`          | **`d(2)`**   | `:181` 同 ④ 的 `setCooldown(2)` |

      ★ 第 ③ 点是**主循环**（每次历练跑完必走 `finally`）⇒ 它决定自动历练的真实节奏。

  R3  同步更新产物里的历史注释 `cooldown=6` → `cooldown=2`（否则注释与代码不符）。

硬约束
--------------------------------------------------------------------------
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py、不写 build/assets/。
  · ★ 本环必须排在 `yl_flow083_ext.py` **之后**（要改它留下的 d(6)/d(4)/d(.4)/d(1)）。
"""

# --------------------------------------------------------------------------- R1 冷却 setter

CD_OLD = 'setCooldown:a=>t({cooldown:a})'
CD_NEW = 'setCooldown:a=>t(_ylcs=>({cooldown:typeof a=="function"?a(_ylcs.cooldown):a}))'

# --------------------------------------------------------------------------- R2 历练冷却还原上游原版

# ① 避战（A 内，A=async(...) 的首个 return）
AV1_OLD = 'd(6),{result:{},battleContext:null,shouldReturn:!0}'
AV1_NEW = 'd(1),{result:{},battleContext:null,shouldReturn:!0}'
# ② 避战（DS 分支）—— ★ 锚点必须带后文 `const oe=await A(`，否则与 ⑥ 天地之魄跳过撞车
AV2_OLD = 'c(!1),d(6);return}const oe=await A('
AV2_NEW = 'c(!1),d(1);return}const oe=await A('
# ③ 正常收尾 finally（★ 主循环，决定自动历练节奏）
AV3_OLD = '}finally{c(!1),d(6)}};'
AV3_NEW = '}finally{c(!1),d(2)}};'
# ④ 商店跳过
AV4_OLD = 'c(!1),d(6);else{'
AV4_NEW = 'c(!1),d(2);else{'
# ⑤ 挑战 boss 初始化
AV5_OLD = 'c(!1)}}),d(1),{resu'
AV5_NEW = 'c(!1)}}),d(2),{resu'
# ⑦ 天地之魄 · 战后 —— ★ 锚点必须带 `.finally(()=>{…})` 外壳，否则 `c(!1),d(2)` 会撞 4 处
AV7_OLD = '}).finally(()=>{c(!1),d(4)})'
AV7_NEW = '}).finally(()=>{c(!1),d(2)})'
# ⑧ 天地之魄 · 避开
AV8_OLD = 'c(!1),d(.4),R&&E'
AV8_NEW = 'c(!1),d(1),R&&E'
# ⑨ 商店访问
AV9_OLD = 'v(ee),c(!1),d(1)},3e2'
AV9_NEW = 'v(ee),c(!1),d(2)},3e2'

# --------------------------------------------------------------------------- R3 注释同步

CMT_OLD = 'cooldown=6'
CMT_NEW = 'cooldown=2'

# --------------------------------------------------------------------------- 参照串（只断言、不改）

REF_SETPLAYER = 'setPlayer:a=>{t(l=>({player:typeof a=="function"?a(l.player):a}))}'
REF_SETSETTINGS = 'setSettings:a=>{t(l=>{const c=typeof a=="function"?a(l.settings):a;'
REF_CD_INIT = 'cooldown:0,fastBattleSettlement:!1'
REF_UPDATER_CALL = 'a(x=>x>0?x-1:0)'
REF_PASSIVE = 'function Lw({player:t,setPlayer:r,setCooldown:a}){'
REF_MED_AUTO = '_.current(2)'
REF_MED_MANUAL = 'updateQuestProgress("meditate",1),M(2)'
REF_TDP_SKIP = 'bossId:le,difficulty:h}),c(!1),d(1);return}'   # ⑥ 上游原版也是 1 ⇒ 本环不动它
REF_NK_SIG = 'autoAdventure:M=!1,difficulty:h="normal"'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""

    # ---- R1：setCooldown 支持 updater 函数 ----
    p.replace('cd-updater', CD_OLD, CD_NEW, expect=1,
              note='setCooldown 补 updater 支持（治 cooldown 被写成函数）')

    # ---- R2：历练冷却还原上游原版（9 点中 8 点要改，⑥ 本就是 1）----
    p.replace('cd-adv-1-avoid-a',   AV1_OLD, AV1_NEW, expect=1, note='① 避战A内 6→1（上游 :143）')
    p.replace('cd-adv-2-avoid-ds',  AV2_OLD, AV2_NEW, expect=1, note='② 避战DS 6→1（上游 :267）')
    p.replace('cd-adv-3-finally',   AV3_OLD, AV3_NEW, expect=1, note='③ 正常收尾 6→2（上游 :501-503，★主循环）')
    p.replace('cd-adv-4-shopskip',  AV4_OLD, AV4_NEW, expect=1, note='④ 商店跳过 6→2（上游 :181）')
    p.replace('cd-adv-5-bossinit',  AV5_OLD, AV5_NEW, expect=1, note='⑤ boss初始化 1→2（上游 :386）')
    p.replace('cd-adv-7-tdpfight',  AV7_OLD, AV7_NEW, expect=1, note='⑦ 天地之魄战后 4→2（上游 :420）')
    p.replace('cd-adv-8-tdpavoid',  AV8_OLD, AV8_NEW, expect=1, note='⑧ 天地之魄避开 .4→1（上游 :425-427）')
    p.replace('cd-adv-9-shopvisit', AV9_OLD, AV9_NEW, expect=1, note='⑨ 商店访问 1→2（上游 :181）')

    # ---- R3：历史注释同步 ----
    p.replace('cd-comment', CMT_OLD, CMT_NEW, expect=1,
              note='历史注释 cooldown=6 → cooldown=2（与代码一致）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= R1 冷却修复 =================
        ('CD·setCooldown 已支持 updater', CD_NEW, 1, '==', '与 setPlayer/setSettings 同构'),
        ('CD·旧 setCooldown 写法已清零', CD_OLD, 0, '==', '必须为 0（否则 cooldown 会被写成函数）'),
        ('CD·updater 分支在位', 'cooldown:typeof a=="function"?a(_ylcs.cooldown):a', 1, '==', ''),
        ('CD·独立变量名 _ylcs（不撞名）', 't(_ylcs=>({cooldown:', 1, '==', ''),
        ('CD·setCooldown 出现次数未变', 'setCooldown', 12, '==', '基座 12'),
        # ---- 参照物：另两个 setter 本来就是对的（不得回踩）----
        ('CD·setPlayer updater 未动', REF_SETPLAYER, 1, '==', '参照物：写法正确'),
        ('CD·setSettings updater 未动', REF_SETSETTINGS, 1, '==', '参照物：写法正确'),
        ('CD·cooldown 初值 0 未动', REF_CD_INIT, 1, '==', ''),
        ('CD·被动回复仍传 updater', REF_UPDATER_CALL, 1, '==', '★ 正是它把函数写进 cooldown'),
        ('CD·被动回复函数未动', REF_PASSIVE, 1, '==', ''),
        # ================= R2 历练冷却 = 上游原版 =================
        ('R26·①避战A内=1', AV1_NEW, 1, '==', '上游 :143'),
        ('R26·②避战DS=1', AV2_NEW, 1, '==', '上游 :267'),
        ('R26·③正常收尾=3（R-042 改后）', '}finally{c(!1),d(3)}};', 1, '==', 'cooldown 先还原 2，R-042 再改 3'),
        ('R26·④商店跳过=2', AV4_NEW, 1, '==', '上游 :181'),
        ('R26·⑤boss初始化=2', AV5_NEW, 1, '==', '上游 :386'),
        ('R26·⑥天地之魄跳过=1（本就一致）', REF_TDP_SKIP, 1, '==', '上游 :427'),
        ('R26·⑦天地之魄战后=2', AV7_NEW, 1, '==', '上游 :420'),
        ('R26·⑧天地之魄避开=1', AV8_NEW, 1, '==', '上游 :425-427'),
        ('R26·⑨商店访问=2', AV9_NEW, 1, '==', '上游 :181'),
        ('R26·nk 形参 autoAdventure 在位', REF_NK_SIG, 1, '==', '锚点自证'),
        # ---- 旧值清零 ----
        ('R26·旧 d(6) 已清零', 'c(!1),d(6)', 0, '==', '0.8.3 的 ×2 值已还原'),
        ('R26·旧 d(4) 已清零', AV7_OLD, 0, '==', ''),
        ('R26·旧 d(.4) 已清零', AV8_OLD, 0, '==', ''),
        ('R26·旧 boss d(1) 已清零', AV5_OLD, 0, '==', ''),
        ('R26·旧商店访问 d(1) 已清零', AV9_OLD, 0, '==', ''),
        # ---- R3 注释 ----
        ('R26·注释 cooldown=2 已同步', CMT_NEW, 1, '==', ''),
        ('R26·注释 cooldown=6 已清零', CMT_OLD, 0, '==', ''),
        # ================= 冻结：R-022 打坐冷却（econ2 已改，不得回踩） =================
        ('冻结·自动打坐冷却 2 秒未动', REF_MED_AUTO, 1, '==', 'R-022：1s→2s'),
        ('冻结·手动打坐冷却 2 秒未动', REF_MED_MANUAL, 1, '==', 'R-022：1s→2s'),
        # ================= 冻结：打坐本体/收益 =================
        ('冻结·打坐每跳灵石未动', 'w=$.spiritStones+__ylsq', 1, '==', 'R-024 口径'),
        ('冻结·顿悟 0.2% 未动', 'Math.random()<.002', 1, '==', 'R-022 口径（R-041 已回滚，本行同步改回 1）'),
        ('冻结·历练 handler 未破坏', 'handleAdventure:async()=>{if(u||f>0)return;', 1, '==', ''),
        # ================= 无新增网络调用 =================
        ('CD·未新增网络调用', 'fetch(', 0, '==', '纯本地状态层',
         ('/* ===== yl-R027:', 'function YlxwFtHarvestText(cd, slot) {')),
    ]
    return gates
