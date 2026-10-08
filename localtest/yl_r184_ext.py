# -*- coding: utf-8 -*-
r"""
yl_r184_ext.py — R-184 「功法悟道」经验挂到自动历练「高价值稀有事件」standalone 纯客户端

需求原文（台账 R-184，逐字）
--------------------------------------------------------------------------
  「功法悟道这个，在我挂机50分钟自动历练中一次都没有触发，把这个加经验的触发设置到
    自动历练 加几千灵石的稀有事件当中触发。R180的项目已经让这些出现几率降低了，
    跟这个触发应该频率也不会太高」

目标产物：build/assets/index-v2930-20261007.js（0.9.30 刚上线；2,308,071 B；
          md5 4a765aa197694ff3175f29e8a38cc2c2）

==============================================================================
零、三问取证（全部对 0.9.30 产物字符级实测 + node 真跑）
==============================================================================
── 问 1：「功法悟道」当前是怎么触发的？「挂 50 分钟一次没触发」的根因？──
  [结论] ★ 根因 = **历练侧从未接线**（不是概率低、也不是被门槛挡住）。
         这是一起典型的「写了但没接线」——与本批 R-181 奇物属性、R-188「一念悟道」同类。
  [证据 A] 「功法悟道」= 悟道（wudao）子系统，已并入「功法」面板：
      @1439883 `var YlxwGongfaWudaoBase = YLXW_COMP.gongfa;` … `YLXW_COMP.gongfa = YlxwTGongfaWudao;`
      （0.8.10 注释：「『悟道』并入『功法』…独立入口三处已删」）
  [证据 B] 该面板的**玩法提示**明确承诺了「历练」也会触发（用户据此才期待历练触发）：
      @1440079 `function YlxwWudaoHint(){ … "玩法提示：打坐 / 历练中会随机触发悟道经验提升。" … }`
  [证据 C] 但真正入账的唯一通路 `YlxwWudaoEnlighten(addLog)` 全 bundle 只出现 **2 次**：
        · @620308 定义（fire-and-forget `YlxwPost("/wudao/enlighten", {})`，成功才补一条日志）
        · @744132 **唯一调用点 = 打坐顿悟分支**（`…,c(x,"special"),YlxwWudaoEnlighten(c)}`）
      ⇒ **历练（adventure）路径一次都没调用过** ⇒ 自动历练期间悟道心得日志永不出现。
        「挂 50 分钟一次没触发」= 结构性为 0，与概率无关。
  [证据 D] 旁证（R-165 的历史决策，说明「历练侧不挂即时点」是有意为之，且用户现在要推翻它）：
      yl_r165_ext.py 文件头 §二 明写：「**为什么『只挂 1 处（打坐顿悟），不挂历练』**…
        3) 历练的即时事件『奇遇』概率 V=min(.3,…) 最高 30%/次 ⇒ 若同点入账会严重破坏悟道曲线。
        故历练不挂即时点，继续走服务端已定档的挂机 roll（0.04/min ⇒ ~24 exp/小时）。」
      ⇒ 用户 R-184 正是要**挂到稀有事件（而非奇遇）**以避开该频率问题。
  [证据 E] 服务端侧确有「历练时间型」悟道入账（R-165 记录 srv/index_v28.ts:7193
      `ylWudaoIdleDelta()` = 打坐+历练 计数器差值 → tickWudaoIdle），但它**慢且无客户端日志**：
      ~0.04 exp/min ⇒ 50 分钟仅 ~2 exp，且玩家完全看不到。这就是用户「一次都没有触发」的体感来源。

── 问 2：0.9.30 里「灵石 +几千」的稀有事件是哪些？判定标准 + 实测概率 ──
  ★★ 本节已在 **R-180 v2（E3 回滚）之后**重做；v1 的旧结论（「几千已不存在」）**已作废**。★★
  用户澄清 R-180 原意（台账 R-180）：「只要求降低概率，并没有降低灵石的数」。R-180 已出 v2
  并**回滚 E3**：奇遇(lucky) 模板基础灵石从 `Ge(t,20,70,490)` 恢复为 `Ge(t,200,500,490)`。
  ⇒ 本节全部数字均在**「E3 已回滚」**前提下实测（node 真跑 bundle 模板表 + 结算链）。
  [口径] 用 node 真跑 bundle 内模板表（yy/sa/at/Ge/fs/Le/vy/fw/U0/pw/hw/xw/gw/bw/yw/yg + Fm
         权重块，逐字抽取；其中 xw 的 `Ge(t,20,70,490)` 就地换成 `Ge(t,200,500,490)` 以模拟
         R-180 v2）+ 真实结算链（Ym ×u×10×0.2 → YlxwAdvBoostR44 ×0.85 → YlxwAdvBoostR97 ×3，
         即 **×u×5.1**，u=境界系数×境界内系数），Monte-Carlo 30 万次/境界。
  [模板表实测] 1200 条：normal 650 / lucky 120 / secret_realm 300 / dao_combining 70 / sect 60。
      奇遇(lucky) 模板基础灵石 raw ∈ **[202, 497]**（120/120 全 ≥200；≥300 占 70.8%）。
      主路(normal) 模板基础灵石 raw 分桶：0:461 · 1-50:90 · 51-100:59 · 101-150:16 ·
        151-200:0 · 201-500:0 · 501-1000:24 · >1000:0
      ⇒ 主路**唯一 ≥200 的 24 条 raw 501~1000 全是 longevityRule**（`Ge(t,500,1e3,540)`），
        被 Fm 门禁 `S.longevityRuleObtained?b>=j:!0`（j=长生境）挡在长生境之外 ⇒ 炼气~合道 0 条。
  [★ 关键结论] 「加几千灵石」的事件 = **奇遇(lucky)**：raw 202~497 ×结算 ×5.1 ⇒
      **结算 ≈1030~2535（炼气L1）**，正是 R-180 docstring 原文「『加几千』就是这个」。
      （境界越高 u 越大 ⇒ 结算越高；长生另加 longevityRule ⇒ 结算上万。）
  [实测：结算值(set) 阈值 vs 模板 raw 阈值]（= 每次历练的命中概率，N=30 万/境界）

      阈值                      炼气L1    筑基L1    元婴L1    长生L1
      ─────────────────────────────────────────────────────────────
      set >= 1000               5.03%     7.01%    11.58%    22.36%
        ⇒ 次/50min              14.0      19.6     32.2      62.3
      set >= 2000               1.99%     4.67%    10.76%    19.42%
        ⇒ 次/50min               5.5      13.0     30.0      54.2
      set >= 3000               0.00%     0.36%     7.44%    19.03%
        ⇒ 次/50min               0.0       1.0     20.8      53.1
      ─────────────────────────────────────────────────────────────
      raw >= 100（v1 旧判据）    5.88%     7.86%    11.80%    19.75%
        ⇒ 次/50min              16.4      21.9     32.9      55.1
      raw >= 200（★本环选用）    5.01%     7.01%    11.04%    19.03%
        ⇒ 次/50min              14.0      19.6     30.8      53.1
      raw >= 300                3.53%     4.94%     7.85%    14.00%
        ⇒ 次/50min               9.8      13.8     21.9      39.1
      raw >= 400                1.79%     2.53%     3.92%     8.07%
        ⇒ 次/50min               5.0       7.1     10.9      22.5
      ─────────────────────────────────────────────────────────────
      ★ 为什么**不**用「结算值」判据：set 阈值随境界**单调暴涨**（set>=1000：炼气 5%→长生 22%；
        set>=3000：炼气 0%→长生 19%）——低境界「一次不触发」、高境界「约 1 分钟一次」，两个极端
        都违背用户「几千 + 频率不高」的意图；且 set 依赖 u 的实时公式，跨版本易碎。
      ★ 为什么用 **raw>=200**：raw 是**模板自身量级**，与境界系数无关 ⇒ 跨境界频率稳定。
        且 raw>=200 在本模板表里**恰好等价于「奇遇事件」**（奇遇 raw 恒 202~497；主路非长生档
        最高仅 150），即用户口中的「稀有事件」；又因 u≥1 恒成立 ⇒ raw>=200 必推出结算 ≥ ~1030
        （真「几千」）。旧判据 raw>=100 会额外纳入主路 raw 101~150 的 16 条（炼气结算仅
        515~765 =「几百」），与「几千」不符 ⇒ 故**上调到 200**。
      ★ 低境界可观测性：炼气L1 命中 5.01%（≈14 次/50min，≈每 3.6 min 一次）——**不再为 0**，
        用户不会再遇到「挂 50 分钟一次不触发」。

── 问 3：「悟道加经验」的加成量是多少？（挂上去之后每次多拿多少经验）──
  [取证] 客户端**拿不到确定数值**：入账在服务端。`YlxwWudaoEnlighten` 只 POST
      `/wudao/enlighten`，由服务端随机挑一个**本人已开放**的道（境界门槛在服务端），
      经 `wudaoAddExp(userId, daoKey, WUDAO_INSIGHT_EXP, 'idle')` 入账，并把
      `{ok, daoName, expGain}` 回给客户端；客户端仅把 `expGain` 显示成
      「☯ 悟道【X道】心得 +N」。**WUDAO_INSIGHT_EXP 是服务端常量**（srv/index_v28.ts 内），
      本环是纯客户端补丁，**不改服务端** ⇒ 每次加成量 = 服务端既定的 WUDAO_INSIGHT_EXP
      （R-165 文件头按 ~10 exp/次 估算：`10 exp ⇒ ~1800 exp/小时`）。
  [★ 对本环的意义] 本环**不新增任何数值**，只是「多打一次既有请求」；且该端点
      **自带服务端频控**（R-165 原文「self-throttles」），所以客户端触发频率再高也不会线性放大收益。
      ⇒ 本环的收益增量 = （新触发次数 × 服务端实际放行率 × WUDAO_INSIGHT_EXP），
        远小于「每次都入账」的估算，不会破坏悟道曲线。

==============================================================================
一、改法（2 处就地替换 · 只挂 1 个客户端触发点）
==============================================================================
  E1  自动历练「模板事件」结算入口（`I()` 的 else 块，bundle @1916201 锚点 / @1916325 结算）挂一次 fire-and-forget：
        原： `const oe=Fm(Q,B,t.realm,t.realmLevel);if(oe){`
        新： `const oe=Fm(Q,B,t.realm,t.realmLevel);if(oe){YlxwWudaoMaybe(oe,Q,a);`
      作用域证据：`oe`=**原始模板**（含 `spiritStonesChange` 基础值）、`Q`=adventureType、
        `a`=addLog，三者均在此块内可用；且**只有此块能同时拿到原始模板与 addLog**
        （`Fg` 只有结算值 `t`、且无境界系数 ⇒ 用结算值判阈值会跨境界爆频，见 §零 问 2）。
  E2  在 `function YlxwMedTick(S, insight) {` 之前声明助手 `YlxwWudaoMaybe(tpl, advType, addLog)`：
        条件 = `advType` 为 `"normal"|"lucky"`（= 自动历练）且模板基础灵石
        `>= YLXW_WUDAO_ADV_STONE_MIN (=200)` ⇒ 调 `YlxwWudaoEnlighten(addLog)`；
        全 try/catch 包裹，任何异常静默，绝不影响历练主流程。
  ★ 判据为何是 **raw>=200**（而非 v1 的 raw>=100、也非结算值）：见 §零 问 2 的实测表——
    raw>=200 ⟺ 「奇遇事件」（结算 ≥ ~1030，真「几千」），跨境界频率稳定（5%~19%/次）。
  ★ 为什么「顺着 R-180 现状挂」而不是把概率改回去：本环**只读** Fm 抽出的模板，
     **一行都不碰** Fm 权重 / 事件种类 / 次数 / 任何数值结算。
  ★ 与 R-165 的关系：R-165 当年因「奇遇 30%/次 太频」而**故意不挂历练**。本环现在**正是挂奇遇**
     （R-180 v2 已把奇遇灵石恢复到 200~500 ⇒ 达 raw>=200 阈值）⇒ 触发率 = 奇遇触发率 V
     （炼气 5% → 长生 19%/次）。这是**用户明确要求的**（R-184 原文「设置到…稀有事件当中触发」），
     且入账端点自带服务端频控（见 §零 问 3）⇒ 不会线性放大收益。

==============================================================================
二、锚点与冻结针脚（对 build/assets/index-v2930-20261007.js 字符级实测）
==============================================================================
  ★★★ 集成顺序前提（务必遵守；本批已因「顺序 / 幂等」踩坑多次）★★★
  · 本补丁的**判据与实测都建立在「R-180 v2（E3 回滚：奇遇灵石 `Ge(t,20,70,490)`
    → `Ge(t,200,500,490)`）已先套用」**的前提上。若 R-180 v2 未先套用（产物仍是 v1 的
    `Ge(t,20,70,490)`），则奇遇 raw 仅 20~69，**达不到 200 阈值 ⇒ 悟道在自动历练里仍然
    一次都不触发**（等于没修）。
  · 因此集成顺序必须是：**先 R-180（v2）→ 再 R-184**。本批 STANDALONE_CLIENT 的追加顺序
    （R-180 在前、R-184 在末尾）天然满足；**请勿把 R-184 排到 R-180 之前**。
  · 本补丁**不**依赖 `Ge(t,200,500,490)` 字面串（v2930 里尚不存在该串）——判据是**数值阈值**
    `tpl.spiritStonesChange >= 200`，故无论 E3 是否已回滚，`--check` 都不会因字面串失败；
    但**行为正确性**（能否真触发）依赖 E3 已回滚。
  · 频率探针（`_freq_probe`）已内置兼容：抽出的 `xw` 若仍是 v1 的 `Ge(t,20,70,490)`，探针会
    就地换成 `Ge(t,200,500,490)` 再测，从而**无论集成到哪一步都给出 v2 口径的数字**。
  替换锚点（打前 count==1，打后 E1 锚 count==0）：
    E1 OLD = `const oe=Fm(Q,B,t.realm,t.realmLevel);if(oe){`          → 1
    E2 ANC = `function YlxwMedTick(S, insight) {`                      → 1
  冻结针脚（对**原件**校验 count 必须 == 1；★ 只钉**本批其它补丁不动**的稳定形态）：
    `/*[r177adv]*/`                         ← R-177 在位标记（R-188 也钉，稳定）
    `/*[r179advlog]*/`                      ← R-179 在位标记
    `function YlxwWudaoEnlighten(addLog) {` ← R-165 助手定义未动
    `YlxwWudaoEnlighten(c)`                 ← R-165/R-188 打坐接线未动（R-188 也钉）
    `YlxwPost("/wudao/enlighten", {})`      ← 入账端点未动（禁裸 fetch）
    `function YlxwMedTick(S, insight) {`    ← E2 注入点右侧未动
    `YlxwAdvResultLog(t,m,d)`               ← R-089 结算日志未动
    `YlxwAdvAcc(t)`                         ← 会话累加器未动
    `function Fm(` / `function Ym(` / `function Hw(`   ← 三个被引用函数签名未动
    `var YLXW_ADV_SESS = null;`             ← R-179 会话变量未动
  ★ 针脚选择原则·不钉邻居（吸取本批 yl_r188_ext.py 把 `[r180adv]` 钉成 0 导致 ABORT 的教训）：
    **绝不**钉 `[r180adv]` / `$>100?x*=.30` / `Ge(t,20,70,490)` / `hpChange:Ge(t,0,0,470)` /
    `t.adventureType==="normal"&&Math.random()<__ylPD` / `window.__ylAdvDrain` 等
    —— 这些会被并行补丁 R-180 新增或改写，本环无权断言邻居状态。
  ★ 与并行补丁的锚点冲突检查（实测）：R-179/R-180/R-181/R-183/R-185/R-188 的锚点与
    E1/E2 均不重叠（R-181 动 `YlxwSpiritExtras`、R-183 动 `ad=` 经验曲线、R-185 动灵田文案、
    R-188 动打坐顿悟判定行、R-180 动 Fm 权重/奇遇量级/掉血/Pc/Hw/Lw）。
    ★ 集成顺序要求（实测更正，勿删）：R-184 必须**晚于** R-165（本批 STANDALONE_CLIENT
      追加在末尾即天然满足）。
      原因：r184 在共用锚点 `function YlxwMedTick(S, insight) {` **之前**插入 HELPER_BLOCK，
      会**打断 r165 的幂等判据**（r165 靠 `all(new in s)` 判定，其 new 串含该锚点 ⇒ 插入后
      两者不再相邻 ⇒ 重跑 r165 会判定「未打过」而**再插一次**，导致 `YlxwWudaoEnlighten`
      重复声明、产物字节与另一顺序不同：实测 order[165,184]=2140717/DEF=1（正确）、
      order[184,165]=2141599/DEF=2）。
      ★ 反向顺序的产物 `node --check` 仍 rc=0、行为不变（重复声明在非严格模式下合法、后者
        覆盖前者），但会多一份冗余块 ⇒ **只有「逐位相同」级校验能抓到它**。
      ★ R-184 自身的幂等是健壮的：用 marker `/*[r184wudao]*/` 判定，**不依赖任何邻居补丁的形态**。

==============================================================================
三、契约（照 localtest/yl_r180_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（就地写回）/ `--check`（只校验不写盘）/ `--selftest`（内存自证）。
  · 就地替换，全部纯 ASCII 注入；bytes 层读、就地原子写回
    （tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r184-<时刻>`。
  · 幂等：产物已含 `[r184wudao]` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 行为探针（node，全部真跑抽取出的真实代码）：
      ① `YlxwWudaoMaybe` 抽取后跑 12 组：normal/lucky 且模板基础灵石 ≥200 ⇒ 恰好调用 1 次
         （含边界 200、奇遇实测区间 202/497）；<200（199 / 150 / 69 / 0）/ null / 无字段 /
         secret_realm / sect_challenge / dao_combining ⇒ 0 次；
         `YlxwWudaoEnlighten` 抛异常 ⇒ 被吞掉不外抛。
      ② 频率探针：真跑 bundle 模板表 + Fm 权重块（xw 就地模拟 R-180 v2 回滚），
         混合 normal/lucky 抽样 30 万次/境界，实测 `raw>=200` 命中率
         （炼气L1 / 长生L1）并断言落在合理区间。
  · 不跑网络：只读 --src 指向的本地文件。

==============================================================================
四、自测记录（本机实测 · 2026-10-07 · R-184 v2 重做）
==============================================================================
  PY   = C:/Users/27026/.workbuddy-ai/binaries/python/versions/3.13.12/python.exe
  NODE = C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe
  SRC  = build/assets/index-v2930-20261007.js（2,308,071 B；md5 4a765aa197694ff3175f29e8a38cc2c2）
  TMP  = 系统临时目录副本（跑完删）
  [1] --check（对 SRC，只校验不写盘）：rc=0；门禁 26/26 全绿；chars 2,139,575 -> 2,140,981 (+1,406)。
  [2] 对 TMP 副本真实写回：rc=0；2,308,071 -> 2,309,531 B（+1,460 B，UTF-8 下 +1,406 chars）；
      md5 9bd6949b252ea4097689ec71f07baf15；已落 .bak-r184-<时刻>。
  [3] node --check TMP：rc=0。
  [4] 复跑 TMP：`already patched (idempotent skip)`，rc=3（幂等，不写盘）。
  [5] 删 TMP 与 .bak；SRC 复验 md5 不变（未被误写）。
  [selftest] gates=26 roundtrip=True delta=+1,406 chars；node --check rc=0；
      helper-probe 12 组全过；freq-probe：炼气L1 raw>=200 = 5.02%（≈14.0 次/50min）、
      长生L1 = 18.99%（≈53.0 次/50min）。
  [集成前提实测] 在**未回滚 E3** 的 v1 产物上，raw>=200 命中率：炼气L1 = 0.000%
      （长生L1 = 1.96%，只命中 longevityRule）⇒ 证实「R-180 v2 必须先套用」，否则炼气期永不触发。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r184wudao]'
MARK = '/*[r184wudao]*/'

# --------------------------------------------------------------------------- 替换项

# E1：自动历练模板事件结算入口（I() 的 else 块）—— oe=原始模板 / Q=adventureType / a=addLog
E1_OLD = 'const oe=Fm(Q,B,t.realm,t.realmLevel);if(oe){'
E1_NEW = 'const oe=Fm(Q,B,t.realm,t.realmLevel);if(oe){YlxwWudaoMaybe(oe,Q,a);'
# E1 旧形态（打后必须清零，证明挂点确实落在此处）
E1_OLD_TAIL = E1_OLD + 'const F=xt(t);'

# E2：助手声明插入点（YlxwMedTick 之前，同模块作用域，函数提升可被 E1 调用；
#     与 R-165 共用该锚点，两者均为「前置插入」，顺序无关）
DECL_ANCHOR = 'function YlxwMedTick(S, insight) {'

HELPER_BLOCK = (
    MARK + '\n'
    '/* ===== yl-R184 wudao-on-rare-adventure =====\n'
    '   The 悟道 panel hint promises "打坐 / 历练中会随机触发悟道经验提升", but\n'
    '   YlxwWudaoEnlighten() was wired ONLY to the meditate insight point (R-165/R-188);\n'
    '   the adventure path never called it => 悟道 never fired during auto-adventure.\n'
    '   This wires it into the auto-adventure TEMPLATE-EVENT path (executeAdventure),\n'
    '   firing ONLY on the rare high-value events the player calls "加几千灵石":\n'
    '   advType normal/lucky AND template base spirit stones >= YLXW_WUDAO_ADV_STONE_MIN.\n'
    '   JUDGE = template RAW stones (not settled): raw>=200 <=> the 奇遇(lucky) event\n'
    '   (lucky raw 202..497 after R-180 v2), which settles to ~1030..2535 stones at\n'
    '   QiRefining (settle = raw * u * 5.1, u>=1). Realm-stable rate ~5%..19%/run.\n'
    '   INTEGRATION ORDER: requires R-180 v2 (E3 rollback, lucky 20-70 -> 200-500) to be\n'
    '   applied FIRST; otherwise lucky raw stays 20-69 and this never fires.\n'
    '   Fire-and-forget + server-side self-throttle; any failure is swallowed and never\n'
    '   affects the adventure loop. MUST reuse YlxwWudaoEnlighten (no raw fetch). */\n'
    'var YLXW_WUDAO_ADV_STONE_MIN = 200;\n'
    'function YlxwWudaoMaybe(tpl, advType, addLog) {\n'
    '  try {\n'
    '    if (!tpl) return;\n'
    '    if (advType !== "normal" && advType !== "lucky") return;\n'
    '    if ((Number(tpl.spiritStonesChange) || 0) < YLXW_WUDAO_ADV_STONE_MIN) return;\n'
    '    YlxwWudaoEnlighten(addLog);\n'
    '  } catch (e) {}\n'
    '}\n'
)

REPS = [
    ('R184-E1 自动历练高价值事件挂悟道入账', E1_OLD, E1_NEW),
    ('R184-E2 悟道挂载助手声明', DECL_ANCHOR, HELPER_BLOCK + DECL_ANCHOR),
]

# 冻结针脚：本环只动上面两处，下列既有形态必须逐字在位（对**原件**校验，全 ASCII）
FREEZE = [
    ('/*[r177adv]*/', 1),                                     # R-177 在位标记
    ('/*[r179advlog]*/', 1),                                  # R-179 在位标记
    ('function YlxwWudaoEnlighten(addLog) {', 1),             # R-165 助手定义未动
    ('YlxwWudaoEnlighten(c)', 1),                             # 打坐顿悟接线未动
    ('YlxwPost("/wudao/enlighten", {})', 1),                  # 入账端点未动
    ('function YlxwMedTick(S, insight) {', 1),                # E2 注入点右侧未动
    ('YlxwAdvResultLog(t,m,d)', 1),                           # R-089 结算日志未动
    ('YlxwAdvAcc(t)', 1),                                     # 会话累加器未动
    ('function Fm(', 1),                                      # 模板选择器仍在
    ('function Ym(', 1),                                      # 结算器仍在
    ('function Hw(', 1),                                      # 自动循环仍在
    ('var YLXW_ADV_SESS = null;', 1),                         # R-179 会话变量未动
]

# 供行为探针使用
HELPER_SIG = 'function YlxwWudaoMaybe(tpl, advType, addLog) {'
HELPER_CALL = 'YlxwWudaoEnlighten(addLog);'

# 频率探针：真跑 bundle 模板表所需的生成器/辅助函数（逐字抽取）
GEN_NAMES = ['yy', 'sa', 'at', 'Ge', 'fs', 'Le', 'vy', 'fw', 'U0',
             'pw', 'hw', 'xw', 'gw', 'bw', 'yw', 'yg', 'Fm']


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R184·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r184wudao] 恰好 1 处'),
        # ---- E1 挂点 ----
        ('R184·E1 挂点已注入', 'if(oe){YlxwWudaoMaybe(oe,Q,a);', 1, '==', '模板事件入口恰好 1 处'),
        ('R184·E1 旧挂点已清零', E1_OLD_TAIL, 0, '==', '旧无挂点形态必须消失'),
        # ---- E2 助手 ----
        ('R184·E2 助手已声明', HELPER_SIG, 1, '==', '助手声明块恰好 1 处'),
        ('R184·E2 阈值常量在位', 'var YLXW_WUDAO_ADV_STONE_MIN = 200;', 1, '==',
         'raw>=200（⟺奇遇事件，结算>=~1030）'),
        ('R184·E2 旧阈值 100 已退役', 'var YLXW_WUDAO_ADV_STONE_MIN = 100;', 0, '==',
         'v1 的 100 不得残留'),
        ('R184·E2 助手复用入账函数', HELPER_CALL, 1, '==', '必须走 YlxwWudaoEnlighten，禁裸 fetch'),
        ('R184·E2 仅自动历练触发',
         'if (advType !== "normal" && advType !== "lucky") return;', 1, '==', '排除秘境/宗门/天地之魄'),
        ('R184·E2 按模板基础灵石判阈',
         'if ((Number(tpl.spiritStonesChange) || 0) < YLXW_WUDAO_ADV_STONE_MIN) return;',
         1, '==', '用原始模板值（跨境界稳定）'),
        ('R184·E2 异常静默', '    YlxwWudaoEnlighten(addLog);\n  } catch (e) {}\n}', 1, '==',
         'try/catch 包裹，绝不影响历练主流程'),
        # ---- 既有悟道链路保持 ----
        ('R184·打坐顿悟接线仍在位', 'YlxwWudaoEnlighten(c)', 1, '==', 'R-165/R-188 未被动'),
        ('R184·入账端点仍在位', 'YlxwPost("/wudao/enlighten", {})', 1, '==', '未改端点'),
        # ---- 本环未碰的既有形态 ----
        ('R184·结算日志未动', 'YlxwAdvResultLog(t,m,d)', 1, '==', 'R-089 单条日志未改'),
        ('R184·会话累加器未动', 'YlxwAdvAcc(t)', 1, '==', ''),
    ]
    for needle, cnt in FREEZE:
        g.append(('冻结 ' + needle[:28], needle, cnt, '==', '冻结既有形态'))
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
    if s.count(E1_OLD_TAIL) != 1:
        return 'E1 旧形态出现 %d 次（期望 1）' % s.count(E1_OLD_TAIL)
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
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _fn_src(text, name):
    """从 text 中按花括号配对精确抽出 `function <name>(...) {...}` 源码。"""
    i = text.find('function %s(' % name)
    if i < 0:
        return None
    j = text.find('{', i)
    if j < 0:
        return None
    depth = 0
    k = j
    n = len(text)
    mode = None
    while k < n:
        c = text[k]
        if mode is None:
            if c == '"' or c == "'":
                mode = c
            elif c == '`':
                mode = '`'
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return text[i:k + 1]
            elif c == '/' and k + 1 < n and text[k + 1] == '/':
                k = text.find('\n', k)
                if k < 0:
                    return text[i:n]
            elif c == '/' and k + 1 < n and text[k + 1] == '*':
                k = text.find('*/', k)
                if k < 0:
                    return text[i:n]
                k += 1
        else:
            if c == '\\':
                k += 1
            elif c == mode:
                mode = None
        k += 1
    return text[i:n]


def _node_run(js):
    """跑一段 js；返回 (rc, stdout, stderr) 或 (None, None, None) 当无 node。"""
    node = _find_node()
    if not node:
        return None, None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        return r.returncode, r.stdout.decode('utf-8', 'replace'), r.stderr.decode('utf-8', 'replace')
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _node_check(js_text):
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


def _helper_probe(patched_text):
    """抽真实 YlxwWudaoMaybe，验证：仅 normal/lucky 且模板基础灵石>=200 才调 YlxwWudaoEnlighten
    （恰好 1 次，含边界 200 与奇遇实测区间 202/497）；其余全部不调；入账函数抛异常被吞掉。"""
    fn = _fn_src(patched_text, 'YlxwWudaoMaybe')
    if not fn:
        return False, 'YlxwWudaoMaybe 定义未找到'
    js = (
        'var CALLS=0;\n'
        'function YlxwWudaoEnlighten(addLog){ CALLS++; }\n'
        'var YLXW_WUDAO_ADV_STONE_MIN = 200;\n'
        + fn + '\n'
        'function chk(n,c){if(!c)throw new Error(n);}\n'
        'function reset(){CALLS=0;}\n'
        'reset(); YlxwWudaoMaybe({spiritStonesChange:200},"normal",function(){}); chk("normal 200 (boundary) should fire",CALLS===1);\n'
        'reset(); YlxwWudaoMaybe({spiritStonesChange:202},"lucky",function(){});  chk("lucky 202 (R-180v2 min) should fire",CALLS===1);\n'
        'reset(); YlxwWudaoMaybe({spiritStonesChange:497},"lucky",function(){});  chk("lucky 497 (R-180v2 max) should fire",CALLS===1);\n'
        'reset(); YlxwWudaoMaybe({spiritStonesChange:199},"normal",function(){}); chk("normal 199 should NOT fire",CALLS===0);\n'
        'reset(); YlxwWudaoMaybe({spiritStonesChange:150},"normal",function(){}); chk("normal 150 (top non-lucky) should NOT fire",CALLS===0);\n'
        'reset(); YlxwWudaoMaybe({spiritStonesChange:69},"lucky",function(){});   chk("lucky 69 (R-180v1 cap) should NOT fire",CALLS===0);\n'
        'reset(); YlxwWudaoMaybe({spiritStonesChange:0},"normal",function(){});   chk("normal 0 should NOT fire",CALLS===0);\n'
        'reset(); YlxwWudaoMaybe({spiritStonesChange:9999},"secret_realm",function(){}); chk("secret_realm should NOT fire",CALLS===0);\n'
        'reset(); YlxwWudaoMaybe({spiritStonesChange:9999},"sect_challenge",function(){}); chk("sect_challenge should NOT fire",CALLS===0);\n'
        'reset(); YlxwWudaoMaybe({spiritStonesChange:9999},"dao_combining_challenge",function(){}); chk("dao_combining should NOT fire",CALLS===0);\n'
        'reset(); YlxwWudaoMaybe(null,"normal",function(){}); chk("null should NOT fire",CALLS===0);\n'
        'reset(); YlxwWudaoMaybe({},"normal",function(){});   chk("missing field should NOT fire",CALLS===0);\n'
        'reset();\n'
        'var _o=YlxwWudaoEnlighten;\n'
        'YlxwWudaoEnlighten=function(){throw new Error("boom")};\n'
        'YlxwWudaoMaybe({spiritStonesChange:300},"normal",function(){});\n'
        'YlxwWudaoEnlighten=_o;\n'
        'console.log("wudao-helper-probe OK: fire only on normal/lucky with template RAW stones >= 200 (boundary 200 fires; 199/150/69/0 do not); throw swallowed");\n'
    )
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:400]
    return True, so.strip()


_FREQ_STUB = r"""
var fe=["\u70bc\u6c14\u671f","\u7b51\u57fa\u671f","\u91d1\u4e39\u671f","\u5143\u5a74\u671f","\u5316\u795e\u671f","\u5408\u9053\u671f","\u957f\u751f\u5883"];
var ae={QiRefining:"\u70bc\u6c14\u671f",Foundation:"\u7b51\u57fa\u671f",GoldenCore:"\u91d1\u4e39\u671f",NascentSoul:"\u5143\u5a74\u671f",SpiritSevering:"\u5316\u795e\u671f",DaoCombining:"\u5408\u9053\u671f",LongevityRealm:"\u957f\u751f\u5883"};
var H={Pill:"Pill",Herb:"Herb",Material:"Material",AdvancedItem:"AdvancedItem",Armor:"Armor",Weapon:"Weapon"};
function pi(){return [];}
function ui(rarity,t){return {name:"item",type:H.Material,rarity:rarity};}
var Vn={a:{id:"v1",name:"n1",description:"d",effects:{}}};
var En={a:{id:"e1",name:"n1",description:"d",effects:{}}};
var on={a:{id:"m1",name:"n1",description:"d",effects:{}}};
var Qn={a:{id:"q1",name:"n1",description:"d",effects:{}}};
var qa={a:{id:"s1",name:"n1",description:"d",effects:{}}};
var rn=[{id:"p1"},{id:"p2"},{id:"p3"}];
var uw=["u1","u2"], as=["a1","a2"], ns=["n1","n2"], bg=["b1","b2"], D0=["d1","d2"], Bn=["bn1","bn2"];
var z0=null, mw=1200, Rr=40;
var Oc={NORMAL:720,LUCKY:120,SECRET_REALM:300,SECT_CHALLENGE:60};
var fi=[], jm=false;
function hi(){ fi=pw(); }
hi();
var MIN=200, RUNS=Math.round(3000/10.75);
function measure(realm, idx, level, N){
  var V=Math.min(.3,.05+idx*.02+(level-1)*.01);
  var hit=0;
  for(var i=0;i<N;i++){
    var isLucky=Math.random()<V;
    var T=Fm(isLucky?"lucky":"normal", void 0, realm, level);
    if(!T) continue;
    if((Number(T.spiritStonesChange)||0)>=MIN) hit++;
  }
  return {p:hit/N, per50:hit/N*RUNS, V:V};
}
var N=300000;
var q=measure("\u70bc\u6c14\u671f",0,1,N);
var c=measure("\u957f\u751f\u5883",6,1,N);
console.log("R184-FREQ 炼气L1  P(template raw>=200)="+(q.p*100).toFixed(3)+"%  (~"+q.per50.toFixed(1)+" 次/50min)");
console.log("R184-FREQ 长生L1  P(template raw>=200)="+(c.p*100).toFixed(3)+"%  (~"+c.per50.toFixed(1)+" 次/50min)");
if(!(q.p>=0.030 && q.p<=0.080)){ console.error("FAIL 炼气L1 命中率越界: "+q.p); process.exit(1); }
if(!(c.p>=0.120 && c.p<=0.280)){ console.error("FAIL 长生L1 命中率越界: "+c.p); process.exit(1); }
console.log("R184-FREQ OK: 炼气~5%（≈14 次/50min），长生~19%（longevityRule 解锁）");
"""


def _freq_probe(patched_text):
    """真跑 bundle 模板表 + Fm 权重块，实测自动历练命中「模板基础灵石>=200」的概率。
    ★ xw（奇遇模板）若仍是 R-180 v1 的 Ge(t,20,70,490)，就地换成 Ge(t,200,500,490)
      以模拟 R-180 v2 的 E3 回滚 —— 保证无论集成到哪一步都给出 v2 口径的数字。"""
    parts = []
    for nm in GEN_NAMES:
        src = _fn_src(patched_text, nm)
        if not src:
            return False, '生成器 %s 未找到（频率探针无法运行）' % nm
        if nm == 'xw' and 'Ge(t,20,70,490)' in src:
            src = src.replace('Ge(t,20,70,490)', 'Ge(t,200,500,490)')
        parts.append(src)
    js = _FREQ_STUB + '\n' + '\n'.join(parts)
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:400]
    return True, so.strip()


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 2 个探针。"""
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r184] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r184] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r184] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r184] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r184] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r184] SELFTEST FAIL ' + nmsg)
        return 1
    for probe in (_helper_probe, _freq_probe):
        ok, pmsg = probe(out)
        if ok is False:
            print('[r184] SELFTEST FAIL %s: %s' % (probe.__name__, pmsg))
            return 1
        print('[r184]   %s -> %s' % (probe.__name__, pmsg))
    print('[r184] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(gates()), len(out) - len(s0), nmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r184] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r184] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r184] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r184] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r184] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r184] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-44s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r184-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r184] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-44s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
