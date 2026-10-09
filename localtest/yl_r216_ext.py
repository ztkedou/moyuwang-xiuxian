# -*- coding: utf-8 -*-
r"""
yl_r216_ext.py — R-213 文案与实现不一致：6 处客户端文案同步（纯客户端）

背景
--------------------------------------------------------------------------
R-213 审计（报告见 localtest/report_r213_*.md）确认 **6 处「文案与实现不一致」**：
服务端已改/已是新语义，客户端文案仍停留在旧口径。本模块只做**纯客户端文案同步**，
不碰服务端、不碰数值、不碰逻辑。

输入产物：build/assets/index-v2944-20261009.js（线上 0.9.44，
          md5 7dec9546b3b9849063338558ee8eadac，2,321,459 B）
bundle 内中文**混合两种形态**：多数区段为 `\uXXXX` 转义形态，少数区段（如 F4 投喂
弹窗列表）为**字面中文**。故锚点形态逐处按实测选取：
  · 转义态锚点（纯 ASCII，源内写成 `\\uXXXX` 字面量）：F1/F2/F3/F5/F6；
  · 字面态锚点（含非 ASCII 中文）：F4（该区段 bundle 内即字面中文）。
所有锚点均从 bundle 原始文本逐字复制（A1…A6 / N1…N6），并在 _precheck 中断言形态。

==============================================================================
F1 · 交易行弹窗「手续费」（交易行 subHeader 文案）
==============================================================================
  旧（解码）：成交收取 10% 手续费；
  新（解码）：挂售成交全额入账、不收取手续费；
  位置：交易行弹窗组件 `Lk` 的 subHeader 内，
        「玩家之间的集市：可以买别人挂售的货，也能自己挂售换灵石。**成交收取 10% 手续费；**
          你的货款托管在行里，记得去「交易行货款」手动领取。」

  依据（服务端全额入账、零手续费）：
    · srv/index_v28.ts:4285  `const amount = Math.max(0, Math.floor(Number(listing.price) || 0));`
      —— /api/market/purchase/confirm 按 listing.price **全额**结算，未乘任何费率；
    · :4290 全额写入 market_payouts；
    · :4366-4430 领取时全额入账；
    · 上架 /market/list 无任何费用扣减。
    ⇒ 实际**零手续费**，文案里的「10%」是旧口径（旧版曾按 10% 抽成）。

  ★ 命中数说明（与派单口径的差异，已实测取证）：
     派单称「同一字符串出现 2 次：同一组件两个分支」，但本 bundle（0.9.44）实测
     `成交收取 10% 手续费；` **count==1**（offset 2089117）。全 bundle `手续费` 仅 3 处：
     2 处在【赏金】组件（`需冻结…灵石（手续费 10%）` : `需全额冻结赏金，完成方实得 90%
     （手续费 10%）`，三元两分支各 1 次，offset 1148174 / 1148295），1 处在【交易行】。
     派单所述「2 次/两个分支」实为**赏金**组件，与 F1 依据（market 全额入账）不符；
     赏金 feeRate 仍为 0.1，其文案不在本环范围，故**未动**（见冻结门禁 FRZ_BOUNTY_FEE）。
     ⇒ 本模块 F1 按**交易行 1 处**实现，fail-closed 断言 `count==1`。

==============================================================================
F2 · 奇遇抽奖规则行「5%」
==============================================================================
  旧（解码）：每次抽取消耗当层修为 5%
  新（解码）：每次抽取消耗当层修为 1%
  位置：奇遇面板规则行「每次抽取消耗当层修为 5%，冷却 30 分钟，每日最多 10 次；
        15% 几率暴击双倍。」

  依据：R-212 已把服务端常量 `ADVENTURE_COST_RATE` 由 0.05 改为 0.01
        （srv/index_v28.ts:5417），但同批只改了服务端常量，**客户端文案未同步**，
        仍写 5%。⇒ 同步为 1%。
  ★ 命中数：1（offset 961756）。

==============================================================================
F3 · 灵田 T5 说明④「照料频率」（只改现役 T5，不碰 T10 死代码）
==============================================================================
  旧（解码）：照料：每日每田一次，清虫害并提升当日收获
  新（解码）：照料：每 2 小时一次（每次 +2%，单田当日封顶 +10%），清虫害并提升当日收获
  位置：灵田面板 `YlxwTFarmT5` 说明区第 ④ 行，
        「④ 照料：每日每田一次，清虫害并提升当日收获；催熟：…」

  依据：
    · FARM_TEND_CD_MS = 2*60*60*1000（srv/index_v28.ts:8673）→ 冷却 2 小时；
    · FARM_TEND_PER = 0.02（srv:6140）→ 每次 +2%；
    · FARM_TEND_CAP = 0.10（srv:6141）→ 单田当日封顶 +10%。
    ⇒ 旧文案「每日每田一次」与实现（每 2 小时一次、可多次、当日封顶 +10%）不符。

  ★★ 陷阱（已规避）：
     死代码 `YlxwTFarmT10` 里有一条**近似但不同**的串：
       「照料：每日每田一次，清虫害并使当日收获提升」  ← 多一个「使」字
     本模块 A3 为 T5 原串（…\u5e76\u63d0\u5347…），与 T10 串（…\u5e76\u4f7f\u63d0\u5347…）
     互不包含；_precheck 里对 A3 与 FRZ_T10 做 fail-closed 区分断言。
     ★ 裁决结论：`YLXW_COMP.farm` 先赋 `YlxwTFarmT10` 后赋 `YlxwTFarmT5`
       ⇒ **T5 现役、T10 死代码**（T5 自己的头注释亦自证「原 YlxwTFarmT10 保留为死代码」）。
       故只改 T5，T10 死代码一字不动（冻结门禁 FRZ_T10）。
  ★ 命中数：1（offset 1190604）。

==============================================================================
F4 · 天地之髓投喂弹窗「稀有度→进度区间」（4 个片段，各自独立替换）
==============================================================================
  旧（解码）→ 新（解码）：
        · 普通物品：+1-2% 进度  →  · 普通物品：+1% 进度
        · 稀有物品：+3-5% 进度  →  · 稀有物品：+3-4% 进度
        · 传说物品：+6-10% 进度 →  · 传说物品：+6-9% 进度
        · 仙品物品：+15-25% 进度 → · 仙品物品：+16-23% 进度
  位置：投喂弹窗说明「根据物品稀有度提升炼化进度：」下的 4 条 <li> 列表
        （bundle@1739821 起，本区段为**字面中文**）。

  依据（映射表已定位）：
    · `const D=O.useMemo(...)`（bundle@1494059）：逐件 `F[W.id]=Math.floor(ge*(.8+X*.4))`，
      `X`=id 字符码和 `%1000/1000` ∈ [0,1)，`ge`：普通 1.5 / 稀有 4 / 传说 8 / 仙品 20；
    · 投喂增量 `le=Math.min(100,X+K)` 亦为客户端本地计算（无服务端对照），故 `D` 即权威口径；
    ⇒ 实际区间：**普通 1；稀有 3–4；传说 6–9；仙品 16–23**。
       旧文案 4 档**上界全部不可达**（2/5/10/25 均取不到），仙品下界 15 亦不可达。

  ★ 陷阱（已规避，与派单口径一致）：
     短串 `+1-2%` / `+3-5%` / `+6-10%` / `+15-25%` 本身在基线**恰 1 次**（可唯一命中）；
     但**新串 `+1%` 在基线已出现 2 次**（他处）⇒ 若只用 `+1-2% → +1%` 裸替换，
     产物中 `+1%` 计数不唯一，门禁无法 fail-closed。故 F4 一律**带上下文锚点**
     （前缀「• <档位>物品：」+ 后缀「 进度」），实测：
       旧上下文锚点 literal==1 / escaped==0；新上下文锚点 literal==0 / escaped==0。
     字面态锚点含非 ASCII，_precheck 对其形态单列断言。

==============================================================================
F5 · 人物志·缘契任务板脚注「最多可做 10 条」
==============================================================================
  旧（解码）：最多可做 10 条
  新（解码）：最多可做 5 条
  位置：缘契任务板脚注「每日限 1 次 · 最多可做 10 条」（bundle@1323026），
        及同组件整体刷新后的 log/notice「…寻访任务（已完成的不动），今日最多可做 10 条。」
        （bundle@1320645）。**两处同替**。

  依据（产物内不存在「10 条/日」上限）：
    · 棋盘恒 5 条：`YlxwRnBoardOf→YlxwRnRollList(5,true)`（bundle@1169257）；
      模块注释「R-034…（每日 5 条）」（bundle@1170127）、组件头「寻访任务（每日 5 条…）」
      （bundle@1174882）三方一致；
    · 「整体刷新」每日 1 次且**原地重掷未完成条**（`nl=tasks.map(x=>(x&&!x.done)?YlxwRnRollOne(true):x)`，
      长度恒 5，bundle@1172950）⇒ 当日最多完成 5 条；
    · 「10 条」仅出现在两处展示串（脚注 / log），无实现支撑；服务端无 charDex/缘契/寻访（grep 0 命中），纯客户端自持。
    ⇒ 同步为 5 条。
  ★ 命中数：**2**（旧串两处，均替换；新串门禁期望 2）。

==============================================================================
F6 · 丹炉说明「仙品大丹要 9 层造诣才炼得动」
==============================================================================
  旧（解码）：仙品大丹要 9 层造诣才炼得动
  新（解码）：九转金丹需 8 层造诣；不死仙丹·天灵根丹·天元丹需 9 层
  位置：丹炉/炼丹说明「…还能解锁更高级的丹方：仙品大丹要 9 层造诣才炼得动。」
        （bundle@999006）。

  依据（`YlxwAlcUnlockLv`，bundle@935169）：
    · 九转金丹 = **8 层**（rarity 仙品）；
    · 不死仙丹 = 9、天灵根丹 = 9、天元丹 = 9（均仙品）；
    · 仙灵丹 = 8（rarity **传说**，非仙品；上游报告误标为仙品）；
    ⇒ **仙品丹实际跨 8~9 层**（九转金丹 8 层），「仙品大丹要 9 层」对九转金丹不成立。
  ★ 命中数：1（offset 999006）。

==============================================================================
契约（standalone，同 localtest/yl_r214_ext.py / yl_r215_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`（缺省自动探测 PATH 上的 node）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r216-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（含门禁未全绿、往返不一致、node --check 失败）。
  · EDITS 四元组 (label, old, new, n)；n=该处旧串期望命中数=替换次数（F5 为 2）。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证 + node 自检。
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

# --------------------------------------------------------------------------- 锚点
# 转义态锚点（纯 ASCII，源内即 bundle 中的 \uXXXX 字面量）；字面态锚点（含非 ASCII，F4）

# F1：交易行 subHeader 内的手续费句（仅交易行 1 处）
A1 = '\\u6210\\u4ea4\\u6536\\u53d6 10% \\u624b\\u7eed\\u8d39\\uff1b'
N1 = '\\u6302\\u552e\\u6210\\u4ea4\\u5168\\u989d\\u5165\\u8d26\\u3001\\u4e0d\\u6536\\u53d6\\u624b\\u7eed\\u8d39\\uff1b'

# F2：奇遇抽奖规则行「每次抽取消耗当层修为 5%」
A2 = '\\u6bcf\\u6b21\\u62bd\\u53d6\\u6d88\\u8017\\u5f53\\u5c42\\u4fee\\u4e3a 5%'
N2 = '\\u6bcf\\u6b21\\u62bd\\u53d6\\u6d88\\u8017\\u5f53\\u5c42\\u4fee\\u4e3a 1%'

# F3：灵田 T5 说明④（现役；注意与 T10 死代码串「…并使…」互斥）
A3 = ('\\u7167\\u6599\\uff1a\\u6bcf\\u65e5\\u6bcf\\u7530\\u4e00\\u6b21\\uff0c'
      '\\u6e05\\u866b\\u5bb3\\u5e76\\u63d0\\u5347\\u5f53\\u65e5\\u6536\\u83b7')
N3 = ('\\u7167\\u6599\\uff1a\\u6bcf 2 \\u5c0f\\u65f6\\u4e00\\u6b21\\uff08\\u6bcf\\u6b21 +2%\\uff0c'
      '\\u5355\\u7530\\u5f53\\u65e5\\u5c01\\u9876 +10%\\uff09\\uff0c'
      '\\u6e05\\u866b\\u5bb3\\u5e76\\u63d0\\u5347\\u5f53\\u65e5\\u6536\\u83b7')

# F4：投喂弹窗稀有度→进度区间（字面中文；带上下文锚点保证唯一，见 docstring F4 陷阱）
A4a = '\u2022 \u666e\u901a\u7269\u54c1\uff1a+1-2% \u8fdb\u5ea6'    # • 普通物品：+1-2% 进度
N4a = '\u2022 \u666e\u901a\u7269\u54c1\uff1a+1% \u8fdb\u5ea6'
A4b = '\u2022 \u7a00\u6709\u7269\u54c1\uff1a+3-5% \u8fdb\u5ea6'    # • 稀有物品：+3-5% 进度
N4b = '\u2022 \u7a00\u6709\u7269\u54c1\uff1a+3-4% \u8fdb\u5ea6'
A4c = '\u2022 \u4f20\u8bf4\u7269\u54c1\uff1a+6-10% \u8fdb\u5ea6'   # • 传说物品：+6-10% 进度
N4c = '\u2022 \u4f20\u8bf4\u7269\u54c1\uff1a+6-9% \u8fdb\u5ea6'
A4d = '\u2022 \u4ed9\u54c1\u7269\u54c1\uff1a+15-25% \u8fdb\u5ea6'  # • 仙品物品：+15-25% 进度
N4d = '\u2022 \u4ed9\u54c1\u7269\u54c1\uff1a+16-23% \u8fdb\u5ea6'

# F5：人物志·缘契任务板脚注「最多可做 10 条」（两处同替）
A5 = '\\u6700\\u591a\\u53ef\\u505a 10 \\u6761'
N5 = '\\u6700\\u591a\\u53ef\\u505a 5 \\u6761'

# F6：丹炉说明「仙品大丹要 9 层造诣才炼得动」
A6 = ('\\u4ed9\\u54c1\\u5927\\u4e39\\u8981 9 \\u5c42\\u9020\\u8be3'
      '\\u624d\\u70bc\\u5f97\\u52a8')
N6 = ('\\u4e5d\\u8f6c\\u91d1\\u4e39\\u9700 8 \\u5c42\\u9020\\u8be3\\uff1b'
      '\\u4e0d\\u6b7b\\u4ed9\\u4e39\\u00b7\\u5929\\u7075\\u6839\\u4e39\\u00b7\\u5929\\u5143\\u4e39'
      '\\u9700 9 \\u5c42')

EDITS = [
    ('F1 交易行「成交收取 10% 手续费；」→ 全额入账、不收取手续费', A1, N1, 1),
    ('F2 奇遇抽奖「每次抽取消耗当层修为 5%」→ 1%', A2, N2, 1),
    ('F3 灵田 T5 照料「每日每田一次」→「每 2 小时一次…」', A3, N3, 1),
    ('F4a 投喂「• 普通物品：+1-2% 进度」→ +1%', A4a, N4a, 1),
    ('F4b 投喂「• 稀有物品：+3-5% 进度」→ +3-4%', A4b, N4b, 1),
    ('F4c 投喂「• 传说物品：+6-10% 进度」→ +6-9%', A4c, N4c, 1),
    ('F4d 投喂「• 仙品物品：+15-25% 进度」→ +16-23%', A4d, N4d, 1),
    ('F5 缘契任务板「最多可做 10 条」→ 5 条（两处）', A5, N5, 2),
    ('F6 丹炉「仙品大丹要 9 层造诣才炼得动」→ 点名分层', A6, N6, 1),
]

# --------------------------------------------------------------------------- 冻结门禁串（不得改动）

# F3：T10 死代码近似串（多「使」字）——必须保持 1，证明死代码未被动
FRZ_T10 = ('\\u7167\\u6599\\uff1a\\u6bcf\\u65e5\\u6bcf\\u7530\\u4e00\\u6b21\\uff0c'
           '\\u6e05\\u866b\\u5bb3\\u5e76\\u4f7f\\u5f53\\u65e5\\u6536\\u83b7\\u63d0\\u5347')
# F1：交易行同句的头/尾（证明只换中段，上下文未动）
FRZ_MKT_HEAD = '\\u73a9\\u5bb6\\u4e4b\\u95f4\\u7684\\u96c6\\u5e02'
FRZ_MKT_TAIL = ('\\u4f60\\u7684\\u8d27\\u6b3e\\u6258\\u7ba1\\u5728\\u884c\\u91cc\\uff0c'
                '\\u8bb0\\u5f97\\u53bb\\u300c\\u4ea4\\u6613\\u884c\\u8d27\\u6b3e\\u300d'
                '\\u624b\\u52a8\\u9886\\u53d6\\u3002')
# F1：赏金组件的「手续费 10%」两分支（不在本环范围，必须保持 2）
FRZ_BOUNTY_FEE = '\\u624b\\u7eed\\u8d39 10%'
# F2：抽奖规则行的后半句（证明只换 5%→1%，其余未动）
FRZ_F2_TAIL = ('\\uff0c\\u51b7\\u5374 30 \\u5206\\u949f\\uff0c\\u6bcf\\u65e5\\u6700\\u591a 10 '
               '\\u6b21\\uff1b15% \\u51e0\\u7387\\u66b4\\u51fb\\u53cc\\u500d\\u3002')
# F3：T5 说明区的③行与催熟句（催熟句 T5/T10 各 1，共 2）
FRZ_T5_LINE3 = '\\u60f3\\u7a33\\u5b9a\\u56de\\u6536\\u7075\\u77f3\\u9009\\u7eaf\\u5356\\u94b1\\u8349'
FRZ_T5_TEND = ('\\u50ac\\u719f\\uff1a\\u7075\\u77f3\\u6309\\u5269\\u4f59\\u65f6\\u957f'
               '\\u8ba1\\u8d39\\u7acb\\u5373\\u6210\\u719f')

# F4：投喂列表的标题句 / 收尾 / 两个档位标签（证明只换区间数字，列表结构与标签未动）
FRZ_F4_TITLE = '\u6839\u636e\u7269\u54c1\u7a00\u6709\u5ea6\u63d0\u5347\u70bc\u5316\u8fdb\u5ea6\uff1a'  # 根据物品稀有度提升炼化进度：
FRZ_F4_TAIL = '\u8fdb\u5ea6"})]})]}),e.jsx("div",{className:"mb-4 space-y-2"'
FRZ_F4_LABEL_CHUAN = '\u4f20\u8bf4\u7269\u54c1'   # 传说物品
FRZ_F4_LABEL_XIAN = '\u4ed9\u54c1\u7269\u54c1'    # 仙品物品
# F5：脚注前缀 / log 前缀（证明只换数字，两处上下文未动）
FRZ_F5_PREFIX = '\\u6bcf\\u65e5\\u9650 1 \\u6b21 \\u00b7 '
FRZ_F5_LOG = ('\\u8bbf\\u4efb\\u52a1\\uff08\\u5df2\\u5b8c\\u6210\\u7684\\u4e0d\\u52a8\\uff09'
              '\\uff0c\\u4eca\\u65e5')
# F6：丹炉说明的前句 / 后句（证明只换该句，邻句未动）
FRZ_F6_HEAD = '\\u8fd8\\u80fd\\u89e3\\u9501\\u66f4\\u9ad8\\u7ea7\\u7684\\u4e39\\u65b9\\uff1a'
FRZ_F6_NEXT = '\\u3010\\u4e39\\u836f\\u6709\\u4ec0\\u4e48\\u7528\\u3011'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    return [
        # ---- F1 ----
        ('F1·新串在位', N1, 1, '==', '挂售成交全额入账、不收取手续费；'),
        ('F1·旧串清零', A1, 0, '==', '10% 手续费旧口径必须为 0'),
        ('冻结·F1交易行头未动', FRZ_MKT_HEAD, 1, '==', '玩家之间的集市'),
        ('冻结·F1交易行尾未动', FRZ_MKT_TAIL, 1, '==', '货款托管句'),
        ('冻结·F1赏金手续费未动', FRZ_BOUNTY_FEE, 2, '==', '赏金两分支 10% 保持'),
        # ---- F2 ----
        ('F2·新串在位', N2, 1, '==', '每次抽取消耗当层修为 1%'),
        ('F2·旧串清零', A2, 0, '==', '5% 旧口径必须为 0'),
        ('冻结·F2抽奖规则尾未动', FRZ_F2_TAIL, 1, '==', '冷却 30 分钟…'),
        # ---- F3 ----
        ('F3·新串在位', N3, 1, '==', '每 2 小时一次（每次 +2%，单田当日封顶 +10%）'),
        ('F3·旧串清零', A3, 0, '==', 'T5 旧照料口径必须为 0'),
        ('冻结·F3 T10死代码未动', FRZ_T10, 1, '==', '…并使… 保持 1'),
        ('冻结·F3 T5③行未动', FRZ_T5_LINE3, 1, '==', ''),
        ('冻结·F3 催熟句未动', FRZ_T5_TEND, 2, '==', 'T5/T10 各 1'),
        # ---- F4 ----
        ('F4a·新串在位', N4a, 1, '==', '• 普通物品：+1% 进度'),
        ('F4a·旧串清零', A4a, 0, '==', '+1-2% 必须为 0'),
        ('F4b·新串在位', N4b, 1, '==', '• 稀有物品：+3-4% 进度'),
        ('F4b·旧串清零', A4b, 0, '==', '+3-5% 必须为 0'),
        ('F4c·新串在位', N4c, 1, '==', '• 传说物品：+6-9% 进度'),
        ('F4c·旧串清零', A4c, 0, '==', '+6-10% 必须为 0'),
        ('F4d·新串在位', N4d, 1, '==', '• 仙品物品：+16-23% 进度'),
        ('F4d·旧串清零', A4d, 0, '==', '+15-25% 必须为 0'),
        ('冻结·F4标题句未动', FRZ_F4_TITLE, 1, '==', '根据物品稀有度提升炼化进度：'),
        ('冻结·F4列表收尾未动', FRZ_F4_TAIL, 1, '==', ''),
        ('冻结·F4传说标签未动', FRZ_F4_LABEL_CHUAN, 1, '==', '传说物品'),
        ('冻结·F4仙品标签未动', FRZ_F4_LABEL_XIAN, 1, '==', '仙品物品'),
        # ---- F5 ----
        ('F5·新串在位', N5, 2, '==', '最多可做 5 条（两处）'),
        ('F5·旧串清零', A5, 0, '==', '10 条旧口径必须为 0'),
        ('冻结·F5脚注前缀未动', FRZ_F5_PREFIX, 1, '==', '每日限 1 次 · '),
        ('冻结·F5 log前缀未动', FRZ_F5_LOG, 1, '==', '寻访任务（已完成的不动），今日'),
        # ---- F6 ----
        ('F6·新串在位', N6, 1, '==', '九转金丹需 8 层造诣；不死仙丹·天灵根丹·天元丹需 9 层'),
        ('F6·旧串清零', A6, 0, '==', '「仙品大丹要 9 层」旧口径必须为 0'),
        ('冻结·F6前句未动', FRZ_F6_HEAD, 1, '==', '还能解锁更高级的丹方：'),
        ('冻结·F6后句未动', FRZ_F6_NEXT, 1, '==', '【丹药有什么用】'),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new, n in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old and new, '%s 锚点不得为空' % name
        assert n >= 1, '%s n 必须 >=1' % name
        ascii_old = all(ord(ch) < 128 for ch in old)
        ascii_new = all(ord(ch) < 128 for ch in new)
        assert ascii_old == ascii_new, \
            '%s 新旧锚点形态（转义/字面）必须一致' % name

    # 形态断言：F1/F2/F3/F5/F6 为转义态（纯 ASCII）；F4 为字面态（含非 ASCII）
    for tag, s in (('A1', A1), ('N1', N1), ('A2', A2), ('N2', N2),
                   ('A3', A3), ('N3', N3), ('A5', A5), ('N5', N5),
                   ('A6', A6), ('N6', N6)):
        assert all(ord(ch) < 128 for ch in s), '%s 转义态锚点必须纯 ASCII' % tag
    for tag, s in (('A4a', A4a), ('N4a', N4a), ('A4b', A4b), ('N4b', N4b),
                   ('A4c', A4c), ('N4c', N4c), ('A4d', A4d), ('N4d', N4d)):
        assert any(ord(ch) >= 128 for ch in s), '%s 字面态锚点须含非 ASCII' % tag

    # F1：旧串含「10%」，新串必须不含；新串须点明「不收取手续费」
    assert '10%' in A1, 'F1 旧串应含 10%'
    assert '10%' not in N1, 'F1 新串不应再出现 10%'
    assert '\\u4e0d\\u6536\\u53d6\\u624b\\u7eed\\u8d39' in N1, 'F1 新串须含「不收取手续费」'

    # F2：5% → 1%
    assert '5%' in A2 and '5%' not in N2, 'F2 旧 5% 应清除'
    assert '1%' in N2, 'F2 新串须含 1%'

    # F3：新串须含 2 小时 / +2% / +10% 三要素
    assert '2 \\u5c0f\\u65f6' in N3, 'F3 新串须含「2 小时」'
    assert '+2%' in N3 and '+10%' in N3, 'F3 新串须含 +2% 与 +10%'

    # F3 陷阱：A3（T5）与 FRZ_T10（T10 死代码）必须互不包含，保证只命中 T5
    assert A3 != FRZ_T10, 'F3 锚点与 T10 死代码串不得相同'
    assert FRZ_T10 not in A3 and A3 not in FRZ_T10, 'F3 锚点与 T10 死代码串不得互相包含'

    # F4：四档区间数字正确，且标签保留
    assert A4a.endswith('+1-2% \u8fdb\u5ea6') and N4a.endswith('+1% \u8fdb\u5ea6'), 'F4a 区间有误'
    assert A4b.endswith('+3-5% \u8fdb\u5ea6') and N4b.endswith('+3-4% \u8fdb\u5ea6'), 'F4b 区间有误'
    assert A4c.endswith('+6-10% \u8fdb\u5ea6') and N4c.endswith('+6-9% \u8fdb\u5ea6'), 'F4c 区间有误'
    assert A4d.endswith('+15-25% \u8fdb\u5ea6') and N4d.endswith('+16-23% \u8fdb\u5ea6'), 'F4d 区间有误'
    for lbl in ('\u666e\u901a\u7269\u54c1', '\u7a00\u6709\u7269\u54c1',
                '\u4f20\u8bf4\u7269\u54c1', '\u4ed9\u54c1\u7269\u54c1'):
        assert sum(1 for _l, o, nw, _c in EDITS if lbl in o and lbl in nw) == 1, \
            'F4 档位标签 %r 须在新旧锚点中各保留一次' % lbl

    # F5：10 → 5（两处）
    assert ' 10 ' in A5 and ' 5 ' in N5 and ' 10 ' not in N5, 'F5 数字替换有误'

    # F6：新串须点名九转金丹 8 层 + 其余三丹 9 层
    assert '\\u4e5d\\u8f6c\\u91d1\\u4e39\\u9700 8 \\u5c42' in N6, 'F6 新串须含「九转金丹需 8 层」'
    assert '\\u9700 9 \\u5c42' in N6, 'F6 新串须含「需 9 层」'

    # 注入内容不得含网络/存储原语（纯文案替换，理应都不含）
    for _n, _o, nw, _c in EDITS:
        for ban in ('fetch(', 'localStorage', 'XMLHttpRequest', 'setInterval(', 'setTimeout('):
            assert ban not in nw, '注入内容不得含 %s' % ban


def _classify(txt):
    """判定基线态：'patched' / 'baseline' / 'partial'。"""
    n_new_ok = sum(1 for _t, _o, n, c in EDITS if txt.count(n) == c)
    n_old_ok = sum(1 for _t, o, _n, c in EDITS if txt.count(o) == c)
    if n_new_ok == len(EDITS) and n_old_ok == 0:
        return 'patched'
    if n_new_ok == 0 and n_old_ok == len(EDITS):
        return 'baseline'
    return 'partial'


def _node_check(out_bytes, node_bin):
    """对产物跑 `node --check`（fail-closed）；找不到 node 则告警跳过。"""
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check（可用 --node 显式指定）')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r216chk-', suffix='.js')
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


def main() -> int:
    ap = argparse.ArgumentParser(description='R-213 文案同步（6 处，客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2944-20261009.js）')
    ap.add_argument('--node', default=None, help='node 可执行文件（缺省自动探测 PATH）')
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
        print('[SKIP] source looks already patched（R-213 六处文案已在位）')
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

    # 5) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-28s actual=%d expect %s %d' % ('OK' if good else 'FAIL', label, act, op, exp))
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
    bak = src_path + '.bak-r216-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r216-', suffix='.tmp')
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
