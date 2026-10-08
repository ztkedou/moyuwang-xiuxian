# -*- coding: utf-8 -*-
r"""
yl_r185_ext.py — R-185 **v3**：补齐「洞府升级成功 toast」文案回退（standalone 纯客户端，纯 UI）

★ 版本沿革：
    v1（已并入线上 v2930 产物）：只把文案「可开垦」改成「最大可扩展」（并「块田」→「块」），
                                 共 2 处（右列那一行 + 洞府升级成功 toast），行仍留在右列。
    v2（已并入线上 v2931 产物）：用户拍板「这一条是左边玩法的内容，被错误地归到了右边」⇒ **真搬列**，
                                 并按团队裁决做三件事：**① 去重 ② 口径标注 ③ 换左列原生 YlxwRow 样式**。
                                 ★ 但 v2 的构建基线是**全新装配产物**（v0），v0 的 toast 是**原件形态「可开垦」**，
                                   而 v2 未处理 toast ⇒ 0.9.31 上线包相对 0.9.30 **出现了回退**
                                   （0.9.30 toast =「最大可扩展」，0.9.31 toast =「可开垦」）。
    v3（本文件）：修掉上述回退 —— 把**洞府升级成功 toast** 的措辞改成与左列面板一致的
                                  **「洞府可扩展」**，使全库在洞府语境下**不再出现「可开垦」**，
                                  也不再出现 v1 遗留的「最大可扩展」。三条路径产出**同一个 v3 形态**。

==============================================================================
★★ 零、本轮（v3）要做的唯一一件事 + 三基线差异
==============================================================================
  改动点：洞府升级成功 toast 里的「可开垦 N 块」（v0/v2）或「最大可扩展 N 块」（v1）
          ⇒ 一律改为「洞府可扩展 N 块」。

  三条基线（都要能跑）：
    · v0（构建基线）= `_chainstage/dryrun_087.bundle.js`
        **已含 v2**（标记 `/*[r185farm2]*/`、右列块已删、左列新行已在位）
        toast 文案 = `可开垦 `（原件形态）
    · v2（线上 0.9.31）= `build/assets/index-v2931-20261007.js`
        **与 v0 逐字相同**（len=2140598），同样已含 v2，toast = `可开垦 `
    · v1（更早 0.9.30）= `build/assets/index-v2930-20261007.js`
        **含 v1**（标记 `/*[r185farm]*/`，右列块为 v1 形态「最大可扩展」）
        toast 文案 = `最大可扩展 `

  ⇒ 判定 + 三条路径（**同一 v3 形态**）：

      if [r185farm3] in s:                    → rc=3 SKIP（已是 v3）
      elif [r185farm2] in s:  kind='v2done'   → v2 已就位，**只改 toast**（toast=可开垦）
      elif REMOVE_V1  in s:   kind='v1'       → 先做 v2（删右列块 + 增左列块），再改 toast（toast=最大可扩展）
      elif REMOVE_ORIG in s:  kind='orig'     → 先做 v2（删右列块 + 增左列块），再改 toast（toast=可开垦）
      else:                                   → rc=2（锚点缺失）

  ★ 幂等标记换新为 `/*[r185farm3]*/`（v2 的 `/*[r185farm2]*/` 已在 0.9.31 产物里 ⇒ 沿用它会被判
    「已打过」而 rc=3 跳过，故必须换新）。`/*[r185farm2]*/` **保留在左列新行上**（它是 v2 已交付的
    正确形态标记，逐字保留，不动）。

==============================================================================
零之壹、本环边界（v3 只加 toast 一处）
==============================================================================
  ★ 本环**只改洞府升级成功 toast 一处文案**：
     · 左列新行（`洞府可扩展` + `YlxwRow` + headroom 式）**逐字不动**（v2 已交付的正确形态）。
     · 数值公式（headroom 式 / 催熟式 / 产出式）**一字不改**（只换 toast 的四个/五个中文字）。
     · 右列块搬运（v2 逻辑）、`种植槽位` 卡片、`➕ 扩地（…灵石）` 按钮、`扩地已满`、
       `handleExpandHerbSlots` / `__ylGrottoExpand`、`YlxwFuse` 双列外壳 **全部不动**。
     · 左列灵田页的「开垦」体系（服务端 `/farm/unlock`）**不动**。
     · `[r185farm2]` 标记的存在性**不动**（见 §零）。

==============================================================================
一、取证：那处 toast（对三基线实测）
==============================================================================
  ★ 关键形态差异：bundle 内**同一文件里两种中文字符形态并存** ——
      · **右列（洞府总览）区域 / toast**：中文是 **裸 UTF-8**（raw CJK>0）
      · **左列灵田页 `YlxwTFarmT5` 区域**：中文是 **`\uXXXX` 转义**
    ⇒ 右列/toast 锚点按**裸 UTF-8** 写；左列新块按**字面 `\uXXXX`** 写。
       本 .py 源码保持纯 ASCII：裸 UTF-8 用 `\uXXXX`（Python 级转义 → 真字符），
       字面 `\uXXXX` 用 `\\uXXXX`（双反斜杠 → 输出里就是 `\uXXXX`）。

  (1) 那处 toast 的**完整原串**（三基线实测，裸 UTF-8）：
        v0 / v2（0.9.31）：
          w.push("灵田联动：产出 +" + M + "%、可开垦 " + (3+(M-1)+(M>=9?4:M>=7?2:M>=5?1:0))
                 + " 块、每日催熟 " + (10+3*Math.min(Math.max(0,M-1),4)+2*Math.max(0,M-5)) + " 次")
        v1（0.9.30）：
          w.push("灵田联动：产出 +" + M + "%、最大可扩展 " + (3+(M-1)+(M>=9?4:M>=7?2:M>=5?1:0))
                 + " 块、每日催熟 " + (10+3*Math.min(Math.max(0,M-1),4)+2*Math.max(0,M-5)) + " 次")

  (2) **它就是洞府升级成功提示**：紧跟其后的语句是
        a(`✨ 成功${q}洞府至【${N.name}】！消耗 ${N.cost.toLocaleString()} 灵石。${w.join("，")}。`, "gain"…)
      `w` 是提示条目数组（同段还有 `N.autoHarvest && w.push("支持自动收获")`），
      `M` 即**洞府等级变量**（其 headroom/cui 两式与右列行 `T.level` 版同构）。
      ⇒ 确为「洞府升级成功 toast」，**不是**别处（玩法说明）的文案。

  (3) **计数（改前）**：
        · 裸「可开垦」：  v0=1 · v1=0 · v2=1        （唯一一处 = 本 toast）
        · 裸「最大可扩展」：v0=0 · v1=2 · v2=0        （v1 的两处 = 右列块 + 本 toast）
        · 裸「洞府可扩展」：v0=0 · v1=0 · v2=0
        · 字面 `\u6d1e\u5e9c\u53ef\u6269\u5c55`（左列新行）：v0=1 · v1=0 · v2=1
      **计数（改后，期望）**：
        · 裸「可开垦」=0 · 裸「最大可扩展」=0
        · 「洞府可扩展」合计 ≥ 2（左列面板 1（字面 `\uXXXX`）+ toast 1（裸 UTF-8））

==============================================================================
二、改法（toast 就地替换一处；v1/orig 路径额外做 v2 的删/增两处）
==============================================================================
  E1（REMOVE，右列，仅 kind∈{v1,orig}）：删除右列「灵田联动」整块（含前导逗号，保留后继逗号）。
      · v1 形态用 `REMOVE_V1`（含 `/*[r185farm]*/`、`最大可扩展`、`块 ·`）
      · 原件形态用 `REMOVE_ORIG`（无标记、`可开垦`、`块田 ·`）
  E2（INSERT，左列 T5，仅 kind∈{v1,orig}）：在统计行（`今日催熟 … / 一键变卖`）之后、田位列表之前
      插入「去重 + 口径标注 + YlxwRow 原生容器」的新块（尾带 `/*[r185farm2]*/`）。**逐字沿用 v2。**
  E3（REPLACE，toast，三条路径都做）：把 toast 里 `可开垦` / `最大可扩展` 换成 `洞府可扩展`，
      并在 push 语句尾部追加 `/*[r185farm3]*/`（v3 幂等标记）。

  ★ 数值公式原样保留；toast 替换只动中文字，不动任何 `3+(M-1)+…` / `10+3*Math.min(…M…)` 公式。

==============================================================================
三、改后效果（Lv.3）
==============================================================================
  洞府升级成功 toast：
      `灵田联动：产出 +3%、洞府可扩展 5 块、每日催熟 16 次`
  左列灵田页（v2 已交付，本环不动）：
      `灵田联动          洞府可扩展 5 块`

==============================================================================
四、锚点与冻结针脚（对三基线字符级实测）
==============================================================================
  替换锚点（裸 UTF-8）：
      REMOVE_V1   （右列块，v1 形态）  count：v1=1
      REMOVE_ORIG （右列块，原件形态） count：—（当前三基线均 0，保留历史路径）
      TOAST_ORIG  （toast，`可开垦`）  count：v0=1 · v2=1
      TOAST_V1    （toast，`最大可扩展`）count：v1=1
      INSERT_OLD  （左列统计行尾，字面 \uXXXX）count：三基线均 1
      NEW_BLOCK   （左列新块，字面 \uXXXX）  打后 count==1（v2done 路径改前已 1）
      TOAST_V3    （toast 目标形态 + `/*[r185farm3]*/`）打后 count==1
  往返还原锚：POST_ANCHOR = `,($==null?void 0:$.autoHarvest` count==1（REMOVE 段的唯一后继）

  冻结针脚（对**输入**校验；kind 分档）：
      公共（三基线一致）：
          'YlxwFuse,{k:__xw}'                                        ==1  ← 双列外壳
          'handleExpandHerbSlots:__ylGrottoExpand'                   ==1  ← 扩地处理器
          '➕ 扩地（'                                                  ==1
          '扩地已满'                                                  ==1
          'T.plantedHerbs.length," / ",(($==null?void 0:$.maxHerbSlots)||0)+(T.extraSlots||0)' ==2 ← 槽位显示
          '种植槽位'                                                  ==6
          '3+(M-1)+(M>=9?4:M>=7?2:M>=5?1:0)'                         ==1  ← toast 可扩地上限式
          '10+3*Math.min(Math.max(0,M-1),4)+2*Math.max(0,M-5)'       ==1  ← toast 催熟式
          'function YlxwTFarmT5'                                     ==1
          'function YlxwTFarmT10'                                    ==1
      kind∈{v1,orig}（v2 前形态）：
          '3+(T.level-1)+(T.level>=9?4:T.level>=7?2:T.level>=5?1:0)' ==2  ← 右列行 + 扩地按钮
          '10+3*Math.min(Math.max(0,T.level-1),4)+2*Math.max(0,T.level-5)' ==1 ← 右列行催熟式
      kind=='v2done'（v2 后形态）：
          '3+(T.level-1)+(T.level>=9?4:T.level>=7?2:T.level>=5?1:0)' ==1  ← 仅剩扩地按钮
          '10+3*Math.min(Math.max(0,T.level-1),4)+2*Math.max(0,T.level-5)' ==0
          '3+(gl-1)+(gl>=9?4:gl>=7?2:gl>=5?1:0)'                     ==1  ← 左列新行已在位
  打后（门禁，对**产物**校验）：
      [r185farm3]==1 · [r185farm2]==1 · [r185farm]==0 · REMOVE_V1==0 · REMOVE_ORIG==0 ·
      NEW_BLOCK==1 · `gl>0&&e.jsx(YlxwRow,`==1 · 字面 `\u6d1e\u5e9c\u53ef\u6269\u5c55`==1（左列面板）·
      裸「洞府可扩展」==1（toast）· 「洞府可扩展」两形态合计≥2 ·
      裸「可开垦」==0 · 裸「最大可扩展」==0 · TOAST_ORIG==0 · TOAST_V1==0 · TOAST_V3==1 ·
      `3+(gl-1)+…`==1 · `3+(T.level-1)+…`==1 · T.level 催熟式==0 · M 两式各==1（toast 公式未动）·
      裸「灵田联动」==1（toast）· 字面 `\u7075\u7530\u8054\u52a8`==1（左列新行）

  ★ 等价性（三条路径产物的 R-185 相关区域逐条一致）：
      ① 右列「灵田联动」块两形态皆 0
      ② 左列新行在位（`gl>0&&e.jsx(YlxwRow,`==1 · 字面 `\u6d1e\u5e9c\u53ef\u6269\u5c55`==1 · gl headroom 式==1）
      ③ toast 已是「洞府可扩展」（裸「洞府可扩展」==1 · TOAST_ORIG==0 · TOAST_V1==0）
      ④ `[r185farm]`==0 · `[r185farm2]`==1 · `[r185farm3]`==1

==============================================================================
五、契约
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 探针）。
  · 就地替换（v1/orig：删右列块 + 增左列块；三路径：改 toast）；REMOVE 锚点按输入形态二选一。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r185v3-<时刻>`。
  · 幂等：产物已含标记 `/*[r185farm3]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；
    needle 可为 tuple（多形态合计计数）。
  · 探针：从补丁后产物**实抽**左列 `gl` 版与 toast `M` 版可扩地上限式，node 复算 Lv.1..10 与 Lv.3 文案。
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

# v3 新标记（幂等判据）；v2 / v1 旧标记仅用于形态识别。
IDEMPOTENT_MARK = '/*[r185farm3]*/'
V2_MARK = '/*[r185farm2]*/'
V1_MARK = '/*[r185farm]*/'

# --------------------------------------------------------------------------- 替换项
# ★ 形态约定（见 §一★）：
#   · REMOVE_V1 / REMOVE_ORIG / TOAST_*（右列 + toast）→ **裸 UTF-8**：本 .py 用 Python 级 \uXXXX
#     （真字符），源码纯 ASCII，运行期匹配 bundle 里的裸中文。
#   · INSERT_OLD / NEW_BLOCK（左列 T5）→ **字面 \uXXXX**：本 .py 用 \\uXXXX（双反斜杠），
#     输出里就是 `\uXXXX` 六个字符，运行期被 JS 解析成中文，与 T5 区域风格一致。

# E1（REMOVE）：右列「灵田联动」整块。两套锚点，共用 349 字公共前缀 + `]})})` 公共后缀。
_REMOVE_PREFIX = (
    ',T.level>0&&e.jsx("div",{className:"bg-ink-900 p-4 rounded-lg border border-stone-700 shadow-lg",'
    'children:e.jsxs("div",{className:"flex items-center justify-between gap-2 flex-wrap",children:['
    'e.jsx("span",{className:"text-stone-300 text-sm font-bold",children:"\u7075\u7530\u8054\u52a8"}),'
    'e.jsxs("span",{className:"text-stone-400 text-xs",children:["\u4ea7\u51fa +",T.level,"% \u00b7 '
)
# v1 中段（v1 已把「可开垦」→「最大可扩展」、「块田」→「块」，并加了 /*[r185farm]*/）
_REMOVE_MID_V1 = (
    '\u6700\u5927\u53ef\u6269\u5c55 ",'
    '3+(T.level-1)+(T.level>=9?4:T.level>=7?2:T.level>=5?1:0)," \u5757 \u00b7 \u6bcf\u65e5\u50ac\u719f ",'
    '10+3*Math.min(Math.max(0,T.level-1),4)+2*Math.max(0,T.level-5)," \u6b21"]})/*[r185farm]*/'
)
# 原件中段（无 v1 标记，文案为原始「可开垦」/「块田」）
_REMOVE_MID_ORIG = (
    '\u53ef\u5f00\u57a6 ",'
    '3+(T.level-1)+(T.level>=9?4:T.level>=7?2:T.level>=5?1:0)," \u5757\u7530 \u00b7 \u6bcf\u65e5\u50ac\u719f ",'
    '10+3*Math.min(Math.max(0,T.level-1),4)+2*Math.max(0,T.level-5)," \u6b21"]})'
)
_REMOVE_SUFFIX = ']})})'

REMOVE_V1 = _REMOVE_PREFIX + _REMOVE_MID_V1 + _REMOVE_SUFFIX
REMOVE_ORIG = _REMOVE_PREFIX + _REMOVE_MID_ORIG + _REMOVE_SUFFIX
REMOVE_NEW = ''

# E2（INSERT）：左列 T5 统计行尾部（字面 \uXXXX）。
INSERT_OLD = (
    'children: readyN > 0 ? "\\u4e00\\u952e\\u53d8\\u5356\\uff08" + readyN + "\\uff09" : "\\u4e00\\u952e\\u53d8\\u5356" })\n'
    '    ] }),'
)

# 左列新块（字面 \uXXXX，与 T5 风格一致）：**去重 + 口径标注 + YlxwRow 原生容器**。★ v2 已交付，逐字保留。
NEW_BLOCK = (
    'gl>0&&e.jsx(YlxwRow,{children:e.jsxs("div",{className:"flex items-center justify-between gap-2 flex-wrap",children:['
    'e.jsx("span",{className:"text-stone-300 text-sm font-bold",children:"\\u7075\\u7530\\u8054\\u52a8"}),'
    'e.jsxs("span",{className:"text-stone-400 text-xs",children:["\\u6d1e\\u5e9c\\u53ef\\u6269\\u5c55 ",'
    '3+(gl-1)+(gl>=9?4:gl>=7?2:gl>=5?1:0)," \\u5757"]})]})})/*[r185farm2]*/'
)
INSERT_NEW = INSERT_OLD + '\n    ' + NEW_BLOCK + ','

# E3（REPLACE）：洞府升级成功 toast（裸 UTF-8）。三段拼接：头 / 中段（可开垦|最大可扩展|洞府可扩展）/ 尾。
_TOAST_HEAD = 'w.push("\u7075\u7530\u8054\u52a8\uff1a\u4ea7\u51fa +" + M + "%\u3001'
_TOAST_TAIL = (
    ' " + (3+(M-1)+(M>=9?4:M>=7?2:M>=5?1:0)) + " \u5757\u3001\u6bcf\u65e5\u50ac\u719f "'
    ' + (10+3*Math.min(Math.max(0,M-1),4)+2*Math.max(0,M-5)) + " \u6b21")'
)
TOAST_ORIG = _TOAST_HEAD + '\u53ef\u5f00\u57a6' + _TOAST_TAIL                       # 「可开垦」形态（v0/v2）
TOAST_V1 = _TOAST_HEAD + '\u6700\u5927\u53ef\u6269\u5c55' + _TOAST_TAIL               # 「最大可扩展」形态（v1）
TOAST_V3 = _TOAST_HEAD + '\u6d1e\u5e9c\u53ef\u6269\u5c55' + _TOAST_TAIL + IDEMPOTENT_MARK  # 目标形态 + 标记

# 往返还原锚：REMOVE 段之后的**唯一后继**（删后仍原样存在，用于反向重插 REMOVE 锚点）。
POST_ANCHOR = ',($==null?void 0:$.autoHarvest'

# 冻结针脚（对**输入**校验；kind 分档）。见 §四。
FREEZE_COMMON = [
    ('YlxwFuse,{k:__xw}', 1),                                                   # 双列外壳未动
    ('handleExpandHerbSlots:__ylGrottoExpand', 1),                              # 扩地处理器未动
    ('\u2795 \u6269\u5730\uff08', 1),                                            # 「➕ 扩地（」按钮未动
    ('\u6269\u5730\u5df2\u6ee1', 1),                                             # 「扩地已满」未动
    ('T.plantedHerbs.length," / ",(($==null?void 0:$.maxHerbSlots)||0)+(T.extraSlots||0)', 2),  # 槽位显示未动
    ('\u79cd\u690d\u69fd\u4f4d', 6),                                             # 「种植槽位」6 处未动
    ('3+(M-1)+(M>=9?4:M>=7?2:M>=5?1:0)', 1),                                     # toast 可扩地上限式未动
    ('10+3*Math.min(Math.max(0,M-1),4)+2*Math.max(0,M-5)', 1),                   # toast 催熟式未动
    ('function YlxwTFarmT5', 1),                                                # 左列灵田页（服务端）未动
    ('function YlxwTFarmT10', 1),                                               # 左列灵田页（服务端）未动
]
FREEZE_PRE_V2 = [   # kind∈{v1,orig}：右列行尚未搬走
    ('3+(T.level-1)+(T.level>=9?4:T.level>=7?2:T.level>=5?1:0)', 2),             # 右列行 + 扩地按钮
    ('10+3*Math.min(Math.max(0,T.level-1),4)+2*Math.max(0,T.level-5)', 1),       # 右列行催熟式
]
FREEZE_POST_V2 = [  # kind=='v2done'：右列行已搬走、左列新行已在位
    ('3+(T.level-1)+(T.level>=9?4:T.level>=7?2:T.level>=5?1:0)', 1),             # 仅剩扩地按钮
    ('10+3*Math.min(Math.max(0,T.level-1),4)+2*Math.max(0,T.level-5)', 0),       # 右列行催熟式已清
    ('3+(gl-1)+(gl>=9?4:gl>=7?2:gl>=5?1:0)', 1),                                # 左列新行已在位
]

# 门禁用关键串
_ESC_LINGTIAN = '\\u7075\\u7530\\u8054\\u52a8'                                   # 灵田联动（左列）
_ESC_KOUJING = '\\u6d1e\\u5e9c\\u53ef\\u6269\\u5c55'                              # 洞府可扩展（左列面板，字面 \uXXXX）
_RAW_KOUJING = '\u6d1e\u5e9c\u53ef\u6269\u5c55'                                   # 洞府可扩展（toast，裸 UTF-8）
_RAW_KETAN = '\u53ef\u5f00\u57a6'                                                 # 可开垦（裸）
_RAW_ZUIDA = '\u6700\u5927\u53ef\u6269\u5c55'                                      # 最大可扩展（裸）
_YIXW_ROW_LEFT = 'gl>0&&e.jsx(YlxwRow,'                                          # 左列原生容器
_DEDUP_CHANCHU = '"\\u4ea7\\u51fa +",gl'                                          # 「产出 +gl%」（应已去重）
_DEDUP_CUI = '10+3*Math.min(Math.max(0,gl-1),4)+2*Math.max(0,gl-5)'               # gl 催熟式（应已去重）


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。

    needle 可为 tuple（多形态合计计数）。"""
    return [
        # ---- v2 既有门禁（保留）----
        ('R185v2\u00b7\u5e42\u7b49\u6807\u8bb0 r185farm2', V2_MARK, 1, '==', '[r185farm2] 恰 1 处（左列新行）'),
        ('R185v2\u00b7v1 \u65e7\u6807\u8bb0\u5df2\u9000\u5f79', V1_MARK, 0, '==', '[r185farm] 已随右列块移除'),
        ('R185v2\u00b7\u53f3\u5217\u5757\u5df2\u79fb\u9664\uff08v1 \u5f62\u6001\uff09', REMOVE_V1, 0, '==', '右列块 v1 形态 0 处'),
        ('R185v2\u00b7\u53f3\u5217\u5757\u5df2\u79fb\u9664\uff08\u539f\u4ef6\u5f62\u6001\uff09', REMOVE_ORIG, 0, '==', '右列块原件形态 0 处'),
        ('R185v2\u00b7\u5de6\u5217\u5757\u5df2\u65b0\u589e', NEW_BLOCK, 1, '==', '左列 T5「灵田联动」行 1 处'),
        ('R185v2\u00b7\u5de6\u5217\u7528\u539f\u751f YlxwRow \u5bb9\u5668', _YIXW_ROW_LEFT, 1, '==', '左列原生行容器'),
        ('R185v2\u00b7\u53e3\u5f84\u6807\u6ce8\u5728\u4f4d\uff08\u5de6\u5217\u9762\u677f\uff09', _ESC_KOUJING, 1, '==', '字面 \\uXXXX「洞府可扩展」'),
        ('R185v2\u00b7\u5df2\u53bb\u91cd\u00b7\u65e0\u300c\u4ea7\u51fa +gl\u300d', _DEDUP_CHANCHU, 0, '==', '左列不再重复「产出」'),
        ('R185v2\u00b7\u5df2\u53bb\u91cd\u00b7\u65e0 gl \u50ac\u719f\u5f0f', _DEDUP_CUI, 0, '==', '左列不再重复「每日催熟」'),
        ('R185v2\u00b7\u5de6\u5217 headroom \u5f0f\u5728\u4f4d', '3+(gl-1)+(gl>=9?4:gl>=7?2:gl>=5?1:0)', 1, '==', '左列可扩展式'),
        ('R185v2\u00b7\u88f8\u300c\u7075\u7530\u8054\u52a8\u300d\u4ec5 toast', '\u7075\u7530\u8054\u52a8', 1, '==', 'raw=仅 toast'),
        ('R185v2\u00b7\u8f6c\u4e49\u300c\u7075\u7530\u8054\u52a8\u300d\u5728\u5de6\u5217', _ESC_LINGTIAN, 1, '==', 'esc=左列新块'),
        ('R185v2\u00b7\u53f3\u5217\u65e7 headroom \u4ec5\u5269\u6269\u5730\u6309\u94ae', '3+(T.level-1)+(T.level>=9?4:T.level>=7?2:T.level>=5?1:0)', 1, '==', '右列行已搬走，剩扩地按钮 1 处'),
        ('R185v2\u00b7\u53f3\u5217\u65e7\u50ac\u719f\u5f0f\u5df2\u6e05\u96f6', '10+3*Math.min(Math.max(0,T.level-1),4)+2*Math.max(0,T.level-5)', 0, '==', '右列催熟式 0 处'),
        ('R185v2\u00b7toast headroom \u672a\u52a8', '3+(M-1)+(M>=9?4:M>=7?2:M>=5?1:0)', 1, '==', 'toast 可扩地上限式未动'),
        ('R185v2\u00b7toast \u50ac\u719f\u672a\u52a8', '10+3*Math.min(Math.max(0,M-1),4)+2*Math.max(0,M-5)', 1, '==', 'toast 催熟式未动'),
        ('R185v2\u00b7\u5de6\u5217\u7075\u7530\u9875\u5728\u4f4d', 'function YlxwTFarmT5', 1, '==', 'T5 未动'),
        # ---- v3 新增门禁 ----
        ('R185v3\u00b7\u5e42\u7b49\u6807\u8bb0 r185farm3', IDEMPOTENT_MARK, 1, '==', '[r185farm3] 恰 1 处'),
        ('R185v3\u00b7toast \u5df2\u662f\u300c\u6d1e\u5e9c\u53ef\u6269\u5c55\u300d', TOAST_V3, 1, '==', 'toast 目标形态 + 标记'),
        ('R185v3\u00b7\u65e7 toast \u300c\u53ef\u5f00\u57a6\u300d\u5df2\u6e05\u96f6', TOAST_ORIG, 0, '==', 'v0/v2 toast 原件形态 0 处'),
        ('R185v3\u00b7\u65e7 toast \u300c\u6700\u5927\u53ef\u6269\u5c55\u300d\u5df2\u6e05\u96f6', TOAST_V1, 0, '==', 'v1 toast 形态 0 处'),
        ('R185v3\u00b7\u5168\u5e93\u300c\u53ef\u5f00\u57a6\u300d\u6e05\u96f6', _RAW_KETAN, 0, '==', '裸「可开垦」0 处'),
        ('R185v3\u00b7\u5168\u5e93\u300c\u6700\u5927\u53ef\u6269\u5c55\u300d\u6e05\u96f6', _RAW_ZUIDA, 0, '==', '裸「最大可扩展」0 处'),
        ('R185v3\u00b7toast \u88f8\u300c\u6d1e\u5e9c\u53ef\u6269\u5c55\u300d', _RAW_KOUJING, 1, '==', '裸 UTF-8「洞府可扩展」'),
        ('R185v3\u00b7\u300c\u6d1e\u5e9c\u53ef\u6269\u5c55\u300d\u4e24\u5f62\u6001\u5408\u8ba1', (_ESC_KOUJING, _RAW_KOUJING), 2, '>=', '左列面板 + toast'),
    ]


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


def _is_patched(s):
    """v3 幂等判据：只看新标记 [r185farm3]（v2 的 [r185farm2] 不再作判据）。"""
    return IDEMPOTENT_MARK in s


def _detect_kind(s):
    """按输入形态返回 kind；未识别返回 None。

    · 'v2done' → 已含 v2（含 /*[r185farm2]*/，右列块已删、左列新行已在位）⇒ 只改 toast
    · 'v1'     → 右列块为 v1 形态（含 /*[r185farm]*/、最大可扩展、块 ·）⇒ 先做 v2 再改 toast
    · 'orig'   → 右列块为原件形态（无标记、可开垦、块田 ·）           ⇒ 先做 v2 再改 toast
    优先判 v2done（v2 产物已无 v1 块，不会混淆）。"""
    if V2_MARK in s:
        return 'v2done'
    if REMOVE_V1 in s:
        return 'v1'
    if REMOVE_ORIG in s:
        return 'orig'
    return None


def _detect_toast(s):
    """按 toast 实际形态返回锚点（TOAST_ORIG / TOAST_V1）；未识别返回 None。"""
    if TOAST_ORIG in s:
        return TOAST_ORIG
    if TOAST_V1 in s:
        return TOAST_V1
    return None


def _precheck(s):
    """返回 (err, kind, variant, toast_anchor)。err=None 表示可打；幂等时返回 (None,None,None,None)。"""
    if _is_patched(s):
        return None, None, None, None  # 幂等，交由 main 判 rc=3
    kind = _detect_kind(s)
    if kind is None:
        return ('R-185 \u951a\u70b9\u7f3a\u5931\uff1a\u53f3\u5217\u300c\u7075\u7530\u8054\u52a8\u300d\u5757'
                '\uff08v2 \u5df2\u5c31\u4f4d / v1 \u5f62\u6001 / \u539f\u4ef6\u5f62\u6001\uff09\u5747\u672a\u627e\u5230',
                None, None, None)
    toast_anchor = _detect_toast(s)
    if toast_anchor is None:
        return ('toast \u951a\u70b9\u7f3a\u5931\uff1a\u6d1e\u5e9c\u5347\u7ea7\u6210\u529f toast'
                '\uff08\u300c\u53ef\u5f00\u57a6\u300d/\u300c\u6700\u5927\u53ef\u6269\u5c55\u300d\uff09\u672a\u627e\u5230',
                None, None, None)
    if s.count(toast_anchor) != 1:
        return ('TOAST \u951a\u70b9\u51fa\u73b0 %d \u6b21\uff08\u671f\u671b 1\uff09' % s.count(toast_anchor),
                None, None, None)
    variant = None
    if kind in ('v1', 'orig'):
        variant = kind
        anchor = REMOVE_V1 if kind == 'v1' else REMOVE_ORIG
        if s.count(anchor) != 1:
            return ('REMOVE \u951a\u70b9\uff08%s\uff09\u51fa\u73b0 %d \u6b21\uff08\u671f\u671b 1\uff09'
                    % (variant, s.count(anchor)), None, None, None)
        if s.count(INSERT_OLD) != 1:
            return 'INSERT \u951a\u70b9\u51fa\u73b0 %d \u6b21\uff08\u671f\u671b 1\uff09' % s.count(INSERT_OLD), None, None, None
        if s.count(POST_ANCHOR) != 1:
            return 'POST \u8fd4\u56de\u951a\u70b9\u51fa\u73b0 %d \u6b21\uff08\u671f\u671b 1\uff09' % s.count(POST_ANCHOR), None, None, None
    freeze = list(FREEZE_COMMON) + (FREEZE_POST_V2 if kind == 'v2done' else FREEZE_PRE_V2)
    for needle, cnt in freeze:
        if s.count(needle) != cnt:
            return ('\u51bb\u7ed3\u9488\u811a %r \u51fa\u73b0 %d \u6b21\uff08\u671f\u671b %d\uff09'
                    % (needle, s.count(needle), cnt)), None, None, None
    return None, kind, variant, toast_anchor


def apply_patch(src):
    """返回 (out, err, kind, variant, toast_anchor)；err 非 None 时 out 为 None。"""
    s = _read(src)
    err, kind, variant, toast_anchor = _precheck(s)
    if err is not None:
        return None, err, None, None, None
    out = s
    if kind in ('v1', 'orig'):
        out = out.replace(REMOVE_V1 if kind == 'v1' else REMOVE_ORIG, REMOVE_NEW, 1)
        out = out.replace(INSERT_OLD, INSERT_NEW, 1)
    out = out.replace(toast_anchor, TOAST_V3, 1)
    return out, None, kind, variant, toast_anchor


def _count(out, needle):
    if isinstance(needle, tuple):
        return sum(out.count(x) for x in needle)
    return out.count(needle)


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0, kind, variant, toast_anchor):
    """反向还原：撤 toast（V3→实际形态）；若做过 v2，再撤 INSERT、据 POST_ANCHOR 重插本次用的 REMOVE 锚点。
    应逐字回到 s0。"""
    rev = out.replace(TOAST_V3, toast_anchor, 1)
    if kind in ('v1', 'orig'):
        rev = rev.replace(INSERT_NEW, INSERT_OLD, 1)
        anchor = REMOVE_V1 if kind == 'v1' else REMOVE_ORIG
        rev = rev.replace(POST_ANCHOR, anchor + POST_ANCHOR, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
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


def _render_probe(patched_text):
    """从补丁后产物**实抽**左列 gl 版与 toast M 版可扩地上限式，用 node 复算 Lv.1..10 与 Lv.3 文案。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。
    """
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    m1 = re.search(r'3\+\(gl-1\)\+\(gl>=9\?4:gl>=7\?2:gl>=5\?1:0\)', patched_text)
    if not m1:
        return False, 'gl \u7248 headroom \u516c\u5f0f\u672a\u627e\u5230'
    hf = m1.group(0)
    m2 = re.search(r'3\+\(M-1\)\+\(M>=9\?4:M>=7\?2:M>=5\?1:0\)', patched_text)
    m3 = re.search(r'10\+3\*Math\.min\(Math\.max\(0,M-1\),4\)\+2\*Math\.max\(0,M-5\)', patched_text)
    if not m2 or not m3:
        return False, 'toast M \u7248\u516c\u5f0f\u672a\u627e\u5230'
    hfm, cfm = m2.group(0), m3.group(0)
    js = (
        'var hf = function(gl){ return ' + hf + '; };\n'
        'var hfm = function(M){ return ' + hfm + '; };\n'
        'var cfm = function(M){ return ' + cfm + '; };\n'
        'var exp = [3,4,5,6,8,9,11,12,15,16];\n'
        'var got = [];\n'
        'for (var L=1; L<=10; L++) got.push(hf(L));\n'
        'if (JSON.stringify(got) !== JSON.stringify(exp)) throw new Error("\u53ef\u6269\u5730\u4e0a\u9650\u8868\u4e0d\u7b26: "+JSON.stringify(got));\n'
        'var row = "\\u7075\\u7530\\u8054\\u52a8  \\u6d1e\\u5e9c\\u53ef\\u6269\\u5c55 " + hf(3) + " \\u5757";\n'
        'var toast = "\\u7075\\u7530\\u8054\\u52a8\\uff1a\\u4ea7\\u51fa +3%\\u3001\\u6d1e\\u5e9c\\u53ef\\u6269\\u5c55 " + hfm(3) + " \\u5757\\u3001\\u6bcf\\u65e5\\u50ac\\u719f " + cfm(3) + " \\u6b21";\n'
        'console.log("headroom-table>> " + got.join(","));\n'
        'console.log("row-Lv3>> " + row);\n'
        'console.log("toast-Lv3>> " + toast);\n'
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
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r185v3] SELFTEST SKIP: src already patched')
        return 0
    out, err, kind, variant, toast_anchor = apply_patch(src)
    if err is not None:
        print('[r185v3] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r185v3] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0, kind, variant, toast_anchor):
        print('[r185v3] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r185v3] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r185v3] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _render_probe(out)
    if ok is False:
        print('[r185v3] SELFTEST FAIL render-probe: ' + pmsg)
        return 1
    print('[r185v3] SELFTEST OK [kind=%s variant=%s]: gates=%d roundtrip=True delta=%+d chars; %s; %s'
          % (kind, variant, len(gates()), len(out) - len(s0), nmsg, pmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r185v3] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r185v3] already patched (idempotent skip)')
        return 3

    out, err, kind, variant, toast_anchor = apply_patch(src)
    if err is not None:
        print('[r185v3] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r185v3] ' + e)
        return 1
    if not _roundtrip_ok(out, s0, kind, variant, toast_anchor):
        print('[r185v3] round-trip mismatch\uff1a\u9664\u6539\u52a8\u70b9\u5916\u5b57\u8282\u88ab\u6539\u52a8')
        return 1

    if args.check:
        print('[r185v3] check OK [kind=%s variant=%s] (%d -> %d chars, %+d)'
              % (kind, variant, len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r185v3-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r185v3] patched [kind=%s variant=%s]: %d -> %d chars (%+d) (backup %s)'
          % (kind, variant, len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
