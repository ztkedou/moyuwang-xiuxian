# -*- coding: utf-8 -*-
r"""
yl_r183_ext.py — R-183 「升级所需经验曲线」分级上调（standalone 纯客户端）

需求原文（台账 R-183，逐字）
--------------------------------------------------------------------------
  「把现在升级所需经验乘以10，高阶段的你算一下现在的修炼体系大概所需耗时，
    如果太长就适当减少提升倍数。现在的经验体系还是升级太快了，我原本计划的是
    炼气提升一层都需要挂机5,6小时以上，结果我今天历练挂机了50分钟就提升了2层。」

==============================================================================
零、本环边界（★ 只动「升到下一层所需修为」这一条曲线）
==============================================================================
  本环**唯一改动点** = 客户端 `ad(realm, lv)`（升级所需修为函数）。
  ★ 明确**不碰**（全部逐字冻结，见 §五 FREEZE）：
      · 打坐收益（`YlxwMedTick` / 打坐 tick 公式 / 洞府灵田）
      · 历练收益（`By` 战斗收益、`Ym` 事件放大、`hw/xw/gw/bw` 事件模板 exp、
        `YLXW_ADV_EXP_MUL_R97` / `YLXW_ADV_STONE_MUL_R97` / `YLXW_ADV_STONE_R44` /
        `YLXW_SR_GAIN_R62`）
      · 挂机（离线修炼 / 自动历练节奏 `d(9)` / `Hw` 主循环 / `[r177adv]`）
      · 单次历练修为上限 `_ylCapPct=.25`（它是「上限」，不是收益；见 §四 说明）
      · 服务端 `srv/index_v28.ts`（本环禁止改；同源曲线不同步问题见 §六）

==============================================================================
一、取证（对 build/assets/index-v2929-20261007.js 字符级实测，非猜测）
==============================================================================
  1.1 曲线函数（bundle 原文，@246945 起，纯 ASCII 锚点，count==1）：
        pN=.24,
        ad=(t,r=1)=>{const a=Cs[t]||Cs[ae.QiRefining],
                     l=Math.min(9,Math.max(1,Math.floor(r)));
                     return Math.floor(a.maxExpBase*(1+(l-1)*pN))}
      ⇒ 升到下一层所需修为 = floor(maxExpBase[境界] × (1 + (层-1) × 0.24))

  1.2 七档基数 `Cs[*].maxExpBase`（实测，七档各出现 1 次）：
        炼气期 60000 · 筑基期 390000 · 金丹期 1521000 · 元婴期 6592000
        化神期 26775000 · 合道期 104430000 · 长生境 452500000
      （注意：服务端注释显示 v26f 已把 6000…45250000「再×10」到现值，
        即用户现在说的「再×10」是在这个已经×10过的基数上再×10。）

  1.3 等级判定链（实测）：
        `ho()` 归一化 @247758：j=ad(m,v), b=Math.max(j, ea(t.maxExp,j))  ⇒ maxExp = max(新算, 存档)
        升级触发 @658919：if(t&&t.exp>=t.maxExp){…}                      ⇒ exp 到 maxExp 即升层
      ⇒ 因为取 max(新算, 存档)，把 ad 调大后，**新算值必然 ≥ 旧存档值**，
        老存档也会立刻按新曲线要求（不会因为存档里的小 maxExp 而漏网）。

  1.4 派生点（随曲线一起变，方向正确，不是「收益」）：
        `_ylExpCap = max(1, floor(ad(realm,lv) × 0.25))` @1899592 —— 单次历练修为**上限**
             （上限随门槛等比抬高；当前实际单次收益 ≈ 门槛的 0.0004，离上限差 ~600 倍，
              抬高上限不改变任何实际收益 ⇒ 不是「改收益」。）
        `YlxwInhInject = floor(ad(realm,lv) × 0.25)` @1440575 —— 传承注入量
             （设计上就是「当前小境界门槛的 25%」，等比抬升是正确语义。）
        `YlxwDrawExpNeed(g)` @1473104 —— 抽奖折算「升到下一级所需修为」，
             **优先取 player.maxExp**（已被 ho 写成 ×K 后的值），
             仅当 maxExp 缺失时才回落到内联公式（该回落路径对真实玩家不可达，本环不动）。

  1.5 单次历练收益（★ 必须实测，不许只读代码猜）：
      用 node 从 bundle 里**抽出真实函数**（`sa/yy/at/Ge/fs/Le/vy/U0/pw/hw/xw/gw/bw/yw/hi/Fm`
      逐字抽取，物品池打桩），把 `Fm` 跑 **400000 次/格**，量出「normal 事件模板」的真实
      exp 分布；战斗侧用 bundle 原式 `By()`；事件放大用 bundle 原式 `Ym()`。实测表见 §三。
      （可复现 LCG 替换 Math.random；物品池只保留「稀有度分布」这一影响权重的语义。）

==============================================================================
二、改法（1 处就地替换，纯 ASCII 注入；变量名 `__r183*` / `YLXW_R183_K` 基线 0 次）
==============================================================================
  把 `ad()` 乘上一个**按境界分级的收敛倍率** `K[境界序]`：

      YLXW_R183_K = [14, 6, 4, 2.5, 1.5, 1, 1]
                    炼气 筑基 金丹 元婴 化神 合道 长生

  新式：ad(t,r=1) = floor( maxExpBase[t] × (1+(lv-1)×0.24) × K[fe.indexOf(t)] )

  ★ 为什么不是一律 ×10（用户第 3 句「如果太长就适当减少提升倍数」的落点）：
      见 §三 表。结论：炼气/筑基 是「太快」的那一段（单层仅数百~数千次历练），
      炼气取 **×14** 把它推到用户要的「5~6 小时**以上**」（≈5.8h，留有余量）；
      而**金丹起，单层历练次数已到 1.5 万次、元婴 5.2 万次、化神 15.8 万次、
      合道 50.6 万次、长生 167 万次**——高阶段「挂机耗时」本来就以「天」计，
      再一律 ×10 会直接变成「年」级，不可玩。故取「低境界足额、逐档收敛、
      高境界维持 1×（只收紧不放松）」的分级方案。

  ★ 为什么炼气取 14 而不是 10/12：
      用户自报实测「炼气 25 分钟/层」⇒ ×K 后 = 25×K 分钟/层。
        K=10 → 250 分 = 4.2h  ← 低于用户目标，不达标
        K=12 → 300 分 = 5.0h  ← 正好卡区间下限，模型差 10% 就掉出「5~6h」
        K=14 → 350 分 = 5.8h  ← 落在「5~6 小时以上」的中上部，有余量 ✓
      故选 14。（该推断只用「用户数据点 × 倍数」的线性关系，与模型绝对精度无关。）

==============================================================================
三、改前 / 改后「单层挂机耗时」实测表（★ 本条重点）
==============================================================================
  3.1 节奏口径（bundle 实测）：
      自动历练 tick 500ms；单次结算展示 1.5s（`setTimeout(oe,1500)`）；
      收尾冷却 `}finally{c(!1),d(9)}` = **9 秒**（R-177 统一到 9s）。
      ⇒ 单次历练 ≈ 1.5 + 9 = 10.5 s ⇒ **5.71 次/分**。
      （另：`localtest/t_edgeecon_legacy_conc_out.json` 里旧版实测「你走出洞府」间隔
        中位数 5.49 s ⇒ 约 11 次/分；该文件是 R-177 之前的旧产物，仅作旁证。）

  3.2 单次历练期望修为 E 与改前耗时（node 实测，400000 次/格；含 15% 商店跳过 /
      奇遇分支 / DS 战斗 roll，战斗按全胜计——全胜是「最快」侧，用来判断「会不会太快」
      最保守；capHit% 全为 0，即单次收益远不触 `_ylCapPct` 上限）：

  境界    层  需要修为(改前)   E[修为/次]   次/层      分钟/层   小时/层
  炼气    1      60,000        60.86        986       172.5     2.88
  炼气    9     175,200       336.91        520        91.0     1.52
  筑基    1     390,000        80.22      4,862       850.8    14.18
  筑基    9   1,138,800       429.76      2,650       463.7     7.73
  金丹    1   1,521,000       102.55     14,832     2,595.7    43.26
  金丹    9   4,441,320       557.56      7,966     1,394.0    23.23
  元婴    1   6,592,000       125.65     52,465     9,181.4   153.02
  元婴    9  19,248,640       732.09     26,293     4,601.2    76.69
  化神    1  26,775,000       169.34    158,116    27,670.3   461.17
  化神    9  78,183,000       918.19     85,149    14,901.1   248.35
  合道    1 104,430,000       206.54    505,611    88,481.9  1474.70
  合道    9 304,935,600     1,144.13    266,523    46,641.5   777.36
  长生    1 452,500,000       270.47  1,673,013   292,777.2  4879.62
  长生    9 1,321,300,000   1,444.22    914,889   160,105.6  2668.43

  ★ 交叉校准（与用户体感对齐）：
      用户实测「炼气 50 分钟升 2 层」⇒ 约 **25 分钟/层** = 0.417 h。
      本模型炼气 L1 = 2.88 h/层 ⇒ 用户当时的实际节奏约为本模型节奏的 **6.91 倍**
      （≈ 1.5 s/次历练；与「R-177 之前冷却更短 / 存在未建模加成」一致）。
      ⇒ 下表「用户实测节奏」= 模型节奏 ÷ 6.91。

  3.3 改后对比（本环方案 K=[14,6,4,2.5,1.5,1,1]）：

  境界    倍率K  改前(模型h/层) → 改后(模型h/层)   改后(用户实测节奏 h/层)
  炼气     14      2.88 →  40.32        5.8   ← 用户目标 5~6h 以上 ✓
  炼气L9   14      1.52 →  21.28        3.1
  筑基      6     14.18 →  85.08       12.3
  金丹      4     43.26 → 173.04       25.0  (1.0 天)
  元婴    2.5    153.02 → 382.55       55.4  (2.3 天)
  化神    1.5    461.17 → 691.76      100.1  (4.2 天)
  合道      1   1474.70 →1474.70      213.4  (8.9 天)
  长生      1   4879.62 →4879.62      706.2  (29.4 天)
  （「模型h/层」= 3.2 表的模型口径；「用户实测节奏」= 模型 ÷ 6.91，
    对齐用户 25 分钟/层的体感。高阶段 K=1 ⇒ 改后 = 改前，未被放大。）

  ★ 若一律 ×10（用户原话版本）——同时算出，供对比（= 3.2 表改前列 × 10）：
  境界    模型节奏(h/层)          用户实测节奏(h/层)
  炼气    28.8   (1.2 天)         4.2   ← 低于用户「5~6h以上」目标
  筑基    141.8  (5.9 天)         20.5
  金丹    432.6  (18.0 天)        62.6
  元婴    1530.2 (63.8 天)        221.4
  化神    4611.7 (192 天)         667.2
  合道    14747.0 (614 天)        2133.7
  长生    48796.2 (2033 天 = 5.6 年) 7060.7
  ⇒ 一律 ×10 把「炼气 4.2 小时」（还**低于**用户目标）与「长生 5.6 年/层」
    这种完全不可玩的档位捆在同一条曲线上。故**不采用一律 ×10**，采用 §二 的分级收敛倍率。
    若用户坚持一律 ×10，只改 `YLXW_R183_K` 一个数组即可（[10,10,10,10,10,10,10]）。

  3.4 收益侧未动的证明（冻结针脚，见 §五）：
      `By` 战斗收益式、`Ym` 事件放大式、`hw/xw/gw/bw` 事件 exp 区间、
      `YLXW_ADV_EXP_MUL_R97=1.2`、`YLXW_ADV_STONE_MUL_R97=3`、`YLXW_ADV_STONE_R44=0.85`、
      `YLXW_SR_GAIN_R62=3`、历练冷却 `d(9)`、打坐 `YlxwMedTick` —— 全部逐字在位。

==============================================================================
四、锚点（对 build/assets/index-v2929-20261007.js 字符级实测）
==============================================================================
  A_OLD  count==1 @246945（纯 ASCII）→ 打后 0
      = 原 `pN=.24,ad=(t,r=1)=>{…}` 整条（不含结尾逗号）
  A_NEW  count==1（打后）＝ 插在 `pN=.24` 与 `ad=` 之间的倍率表 + 乘 K + 幂等标记 `/*[r183exp]*/`
  冻结（对**原件**校验，count 必须 == 给定值，全部逐字）：
      Cs 七档基数 7 条（各 1）
      var YLXW_ADV_STONE_R44 = 0.85;            ← 历练灵石下调（收益）
      var YLXW_ADV_EXP_MUL_R97 = 1.2;           ← 历练修为倍率（收益）
      var YLXW_ADV_STONE_MUL_R97 = 3;           ← 历练灵石倍率（收益）
      var YLXW_SR_GAIN_R62 = 3;                 ← 秘境收益倍率（收益）
      expChange:Math.floor(t.expChange*u)       ← Ym 事件放大（收益）
      function Ym(t,r,_ylm){                     ← 事件放大函数未动
      function By(t,r,a,l,c=1,d="normal"){       ← 战斗收益函数未动
      function hw(t) / function Fm(              ← 事件模板 / 事件选择未动
      }finally{c(!1),d(                      ← 历练冷却**块**未动（值无关；R-177=9s / R-199=7s 皆成立）
      [r177adv] / [r179advlog]                  ← 既有环在位标记
      _ylCapPct=.25                             ← 单次历练修为上限口径未动
      function YlxwMedTick / function YlxwAdvSession / YLXW_ADV_STAT = YlxwAdvStatNew();
      Cs={[ae.QiRefining]:{baseMaxHp:100       ← Cs 境界表本体未动
  ★ 终态交接（0.9.35 / R-199，照 r177 的 RETIRED_TAG 写法）：
      本环排在 R-199 之前 ⇒ apply 态 `}finally{c(!1),d(9)}` 仍在（precheck count==1）；
      终态 R-199 已合法改为 d(7) ⇒ 该形态终态为 0。
      故 d(9) 那条另立**终态专用**退役门禁（`RETIRED_TAG`，终态期望 0），
      `_run_gates` 命中标签即跳过；非退役门禁用「值无关」形态 `}finally{c(!1),d(`，
      跨 R-199 恒成立 ⇒ 不会因 R-199 落地而变红。

==============================================================================
五、契约（照 localtest/yl_r179_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 曲线探针）。
  · 1 处就地替换（E1 `ad()` 乘分级倍率），纯 ASCII 注入。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r183-<时刻>`。
  · 幂等：产物已含标记 `[r183exp]` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 曲线探针：从补丁后产物抽出**真实** `fe/Cs/ad` 三件套，用 node 逐格断言
      ad(realm,lv) == floor(maxExpBase × (1+(lv-1)×0.24) × K[realm])，并打出 7×9 曲线表。
  · 不跑网络：只读 --src 指向的本地文件。

==============================================================================
六、★ 需用户/team-lead 决策的点：客户端与服务端「同源曲线」不同步
==============================================================================
  `srv/index_v28.ts` 有**逐档同源**的另一份曲线：
      const TRIB_REALM_BASES = { '炼气期': {maxExpBase:60000, …}, …, '长生境': {maxExpBase:452500000} };
      const TRIB_LEVEL_EXP_FACTOR = 0.24;   // 注释原文「客户端 ad(realm,lv)=… 同源」
      function realmMaxExp(realm, lv) { … }
  服务端 `normalizeRealm(p)` 会**用自己的公式重算** maxExp（= 未乘 K 的旧值），
  并用于：渡劫就绪判定 `expOk = nr.exp >= nr.maxExp`、师门纳税槽位钳制等。
  本环被限定「只改客户端一个文件」，故**服务端仍是旧曲线**。后果：
      · 客户端显示「还差很多」，服务端却已认为「修为已满」⇒ 渡劫判定会出现口径不一致；
      · 反之若后续服务端也 ×K，客户端未更新时又会反向不一致。
  ⇒ 建议：客户端落 K 后，**服务端 `TRIB_REALM_BASES` 需同步乘同一张 K 表**（另开一条服务端工单）。
     在此之前，本条只影响「客户端显示/本地判定」，不阻塞上线，但请知悉。

==============================================================================
七、已知未证实（留档，不影响本环定档）
==============================================================================
  · 收益侧存在 `yd()` 类经验加成：粗看炼气期经验侧放大约 **×22**，但**未定位**其最终
    乘入 `expChange` 的落点（`Ay`/`Fg` 段只涉及 story/资源消耗）。
    影响面：只影响各档**绝对**时长；不改变「升级门槛 ×K ⇒ 挂机时长 ×K」的线性关系。
    故 §三 的「改前/改后对照」与「K=14 ⇒ 5.8h」的**相对**结论不受影响；
    若该加成真实且随境界变化，§三 的绝对小时数需整体按同一因子平移。
  · 「用户实测节奏 = 模型 ÷ 6.91」这一因子来自单一用户数据点（炼气 25 分钟/层），
    非多档实测；作为交叉校准使用，不作为独立证据。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r183exp]'

# ★ 0.9.35（R-199）交接：R-199 把自动历练冷却 d(9)→d(7)。
#   本环排在 R-199 之前 ⇒ **apply 态** d(9) 形态仍在（count==1，precheck 通过）；
#   而 **终态** d(9)==0。故：
#     · 输入前置检查 / 非退役门禁用「冷却无关」形态 `}finally{c(!1),d(`（d(9)/d(7) 皆 count==1）
#       —— 它证明「R-183 没有碰冷却块」，且跨 R-199 依然成立；
#     · d(9) 形态另立一条**终态专用**退役门禁（终态期望 0），由本环 apply 跳过、由终态复核负责。
RETIRED_TAG = '【已退役·终态专用】'

# --------------------------------------------------------------------------- 替换项

# E1：ad() 乘「按境界分级收敛倍率」
A_OLD = (
    'pN=.24,ad=(t,r=1)=>{const a=Cs[t]||Cs[ae.QiRefining],'
    'l=Math.min(9,Math.max(1,Math.floor(r)));'
    'return Math.floor(a.maxExpBase*(1+(l-1)*pN))}'
)

A_NEW = (
    'pN=.24,YLXW_R183_K=[14,6,4,2.5,1.5,1,1],'
    'ad=(t,r=1)=>{const a=Cs[t]||Cs[ae.QiRefining],'
    'l=Math.min(9,Math.max(1,Math.floor(r))),'
    '__r183i=fe.indexOf(t),'
    '__r183k=(__r183i>=0&&YLXW_R183_K[__r183i])||1;'
    'return Math.floor(a.maxExpBase*(1+(l-1)*pN)*__r183k)}/*' + IDEMPOTENT_MARK + '*/'
)

REPS = [
    ('R183-E1 升级所需修为曲线乘分级倍率 K', A_OLD, A_NEW),
]

# 冻结针脚：本环只动上面一处，下列既有形态必须逐字在位（对**原件**校验）
FREEZE = [
    # --- Cs 七档基数（曲线基数本体，不动） ---
    ('maxExpBase:60000', 1),
    ('maxExpBase:390000', 1),
    ('maxExpBase:1521000', 1),
    ('maxExpBase:6592000', 1),
    ('maxExpBase:26775e3', 1),
    ('maxExpBase:104430e3', 1),
    ('maxExpBase:45250e4', 1),
    ('Cs={[ae.QiRefining]:{baseMaxHp:100', 1),
    # --- 历练收益（★ 一律不许动） ---
    ('var YLXW_ADV_STONE_R44 = 0.85;', 1),        # 历练灵石下调
    ('var YLXW_ADV_EXP_MUL_R97 = 1.2;', 1),       # 历练修为倍率
    ('var YLXW_ADV_STONE_MUL_R97 = 3;', 1),       # 历练灵石倍率
    ('var YLXW_SR_GAIN_R62 = 3;', 1),             # 秘境收益倍率
    ('expChange:Math.floor(t.expChange*u)', 1),   # Ym 事件放大式
    ('function Ym(t,r,_ylm){', 1),                # 事件放大函数
    ('function By(t,r,a,l,c=1,d="normal"){', 1),  # 战斗收益函数
    ('function hw(t)', 1),                        # 事件模板池
    ('function Fm(', 1),                          # 事件选择器
    ('function YlxwAdvBoostR44', 1),
    ('function YlxwAdvBoostR97', 1),
    ('function YlxwSrBoostR62', 1),
    # --- 节奏 / 挂机 / 打坐（不动） ---
    # 冷却块用「值无关」前缀：R-183 只保证没碰这个块；冷却值本身由 R-177(9s)/R-199(7s) 负责。
    ('}finally{c(!1),d(', 1),
    ('function YlxwMedTick', 1),                  # 打坐 tick 累加
    ('function YlxwAdvSession', 1),               # 历练会话
    ('YLXW_ADV_SESS = { t: Date.now() };', 1),
    ('YLXW_ADV_STAT = YlxwAdvStatNew();', 1),
    # --- 既有环在位标记 / 上限口径 ---
    ('[r177adv]', 1),
    ('[r179advlog]', 1),
    ('_ylCapPct=.25', 1),                         # 单次历练修为上限（口径不动）
]

# 期望的 K 表（探针用）
K_EXPECT = [14, 6, 4, 2.5, 1.5, 1, 1]
BASES = [60000, 390000, 1521000, 6592000, 26775000, 104430000, 452500000]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R183·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r183exp] 恰好 1 处'),
        ('R183·新曲线已注入', A_NEW, 1, '==', 'ad() 已乘分级倍率 K'),
        ('R183·旧曲线已消失', A_OLD, 0, '==', '旧 ad()（无 K）已清零'),
        ('R183·倍率表唯一', 'YLXW_R183_K=[14,6,4,2.5,1.5,1,1]', 1, '==', 'K 表恰好 1 处'),
        ('R183·乘数已接入返回值', 'return Math.floor(a.maxExpBase*(1+(l-1)*pN)*__r183k)}', 1, '==', '乘 K 落点唯一'),
        ('R183·境界索引落点唯一', '__r183i=fe.indexOf(t)', 1, '==', '按境界取 K'),
        ('R183·旧返回式已清零', 'return Math.floor(a.maxExpBase*(1+(l-1)*pN))}', 0, '==', '旧返回式已删'),
        # ★ 收益侧「一行未动」的可证针脚
        ('R183·历练修为倍率未动', 'var YLXW_ADV_EXP_MUL_R97 = 1.2;', 1, '==', '收益冻结'),
        ('R183·历练灵石倍率未动', 'var YLXW_ADV_STONE_MUL_R97 = 3;', 1, '==', '收益冻结'),
        ('R183·历练灵石下调未动', 'var YLXW_ADV_STONE_R44 = 0.85;', 1, '==', '收益冻结'),
        ('R183·秘境收益未动', 'var YLXW_SR_GAIN_R62 = 3;', 1, '==', '收益冻结'),
        ('R183·事件放大未动', 'expChange:Math.floor(t.expChange*u)', 1, '==', '收益冻结'),
        ('R183·战斗收益式未动', 'function By(t,r,a,l,c=1,d="normal"){', 1, '==', '收益冻结'),
        ('R183·历练冷却块未动', '}finally{c(!1),d(', 1, '==', '节奏冻结（值无关：R-177=9s / R-199=7s 皆成立）'),
        ('R183·历练冷却9s形态已退役' + RETIRED_TAG, '}finally{c(!1),d(9)}', 0, '==',
         'R-199/0.9.35 已合法改写为 d(7) ⇒ 终态清零（新形态由 R199 自己的门禁负责；本环 apply 跳过）'),
        ('R183·单次上限口径未动', '_ylCapPct=.25', 1, '==', '上限冻结'),
        ('R183·打坐未动', 'function YlxwMedTick', 1, '==', '打坐冻结'),
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
        if RETIRED_TAG in label:
            # 退役针脚（终态专用）：本环 apply 时 R-199 尚未套用，自产 d(9) 形态仍在 ⇒ 不检；
            # 终态由复核（期望 0）负责，新形态由 R-199 自己的门禁负责。
            continue
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
    """定位 node：env NODE → PATH → 本机 binaries 下**任意**版本（版本目录会随升级改名，
    故用 glob 取最新一个，而不是写死某个版本号）。"""
    import glob
    cand = [os.environ.get('NODE'), shutil.which('node')]
    cand += sorted(glob.glob('C:/Users/27026/.workbuddy-ai/binaries/node/versions/*/node.exe'),
                   reverse=True)
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


def _curve_probe(patched_text):
    """从补丁后产物抽出**真实** fe/Cs/ad 三件套，用 node 逐格断言新曲线。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。
    """
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    i0 = patched_text.find('const fe=[ae.QiRefining')
    i1 = patched_text.find(IDEMPOTENT_MARK)
    if i0 < 0 or i1 < 0:
        return False, 'fe/Cs/ad 区块或幂等标记未找到'
    seg = patched_text[i0:i1 + len(IDEMPOTENT_MARK) + 2]  # +2 吃掉 `*/`
    js = (
        'var ae = {QiRefining:"\\u70bc\\u6c14\\u671f",Foundation:"\\u7b51\\u57fa\\u671f",'
        'GoldenCore:"\\u91d1\\u4e39\\u671f",NascentSoul:"\\u5143\\u5a74\\u671f",'
        'SpiritSevering:"\\u5316\\u795e\\u671f",DaoCombining:"\\u5408\\u9053\\u671f",'
        'LongevityRealm:"\\u957f\\u751f\\u5883"};\n'
        + seg + '\n'
        'var K_EXPECT = ' + repr(K_EXPECT).replace('[', '[').replace(']', ']') + ';\n'
        'var BASES = ' + repr(BASES) + ';\n'
        'var out = [];\n'
        'if (JSON.stringify(YLXW_R183_K) !== JSON.stringify(K_EXPECT))'
        '  throw new Error("K \\u8868\\u4e0d\\u7b26: " + JSON.stringify(YLXW_R183_K));\n'
        'for (var ri = 0; ri < 7; ri++) {\n'
        '  var row = [];\n'
        '  for (var lv = 1; lv <= 9; lv++) {\n'
        '    var want = Math.floor(BASES[ri] * (1 + (lv - 1) * 0.24) * K_EXPECT[ri]);\n'
        '    var got  = ad(fe[ri], lv);\n'
        '    if (got !== want) throw new Error("ri=" + ri + " lv=" + lv + " got=" + got + " want=" + want);\n'
        '    row.push(got);\n'
        '  }\n'
        '  out.push("K=" + K_EXPECT[ri] + " :: " + row.join(" "));\n'
        '}\n'
        # 反证：旧式（无 K）必须与新式不同（除非 K==1 的档）
        'var raw1 = Math.floor(BASES[0] * 1 * 1);\n'
        'if (ad(fe[0], 1) === raw1) throw new Error("\\u70bc\\u6c14 L1 \\u672a\\u4e58 K");\n'
        # 边界：非法/越界境界回落到 1x，不抛异常
        'if (ad("\\u4e0d\\u5b58\\u5728", 1) !== 60000) throw new Error("\\u672a\\u77e5\\u5883\\u754c\\u5e94\\u56de\\u843d\\u70bc\\u6c14\\u57fa\\u6570");\n'
        'if (ad(fe[0], 99) !== Math.floor(BASES[0] * (1 + 8 * 0.24) * ' + str(K_EXPECT[0]) + ')) throw new Error("\\u5c42\\u6570\\u5e94\\u88ab clamp \\u5230 9");\n'
        'console.log("curve-probe OK");\n'
        'console.log(out.join("\\n"));\n'
    )
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
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 曲线探针。"""
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r183] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r183] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r183] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r183] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r183] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r183] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _curve_probe(out)
    if ok is False:
        print('[r183] SELFTEST FAIL curve-probe: ' + pmsg)
        return 1
    print('[r183] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print(pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r183] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r183] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r183] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r183] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r183] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r183] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-40s %s' % (label.replace(RETIRED_TAG, ''),
                                         'SKIP(退役·终态复核)' if RETIRED_TAG in label else 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r183-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r183] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-40s %s' % (label.replace(RETIRED_TAG, ''),
                                     'SKIP(退役·终态复核)' if RETIRED_TAG in label else 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
