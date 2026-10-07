# -*- coding: utf-8 -*-
r"""
yl_r179_ext.py — R-179 自动历练「结算/汇总文案」重排 + 去重（standalone 纯客户端）

需求原文（台账 R-179，逐字）
--------------------------------------------------------------------------
  「自动历练的结算：〔原文样例〕
   《本次自动历练 7 分 50 秒：修为 +5,741 · 灵石 +25,831 · 历练 39 次 ·
    📊 历练统计：共 39 次 · 耗时 7 分 50 秒 · 气血 +642 · 平均每次 修为 +147 · 灵石 +662 ·
    事件类型：历练 30 · 奇遇 9 · 物品获得（11 种）：[炼气期]精铁指环、灵天灵草、小提速丹、妖道髓、
    凡品合成石、精铁锭、紫府仙莲、精品合成石、[炼气期]青莲葫芦、星辰草、紫猴花 ·
    其他：掉落 11 次 · 奇遇 9 次 · 天地之魄 0 次 · 受伤 4 次》
  **1.重复的信息没有去掉。**
  **2.彻底把这条信息重新排序**按照：「**时长、历练次数、修为、灵石、寿命变化、气血变化、物品获得**」
     然后做一个**明显的分割**。「**次数、奇遇、掉落、天地之魄、受伤**」」

==============================================================================
零、本环边界（★ 与同批「历练事件生成/节奏/三档几率」代理严格不重叠）
==============================================================================
  本环**只动「自动历练结束时的结算/汇总文案」**，锚点落在四处（同属结算展示面）：
      · `YlxwAdvSummary(el)`            —— 汇总块的**文案拼装**（626694 起）
      · `YlxwAdvSession(on)` 的收尾装配 —— 头行 + R-161 去重 + `add(...)`（629144 起）
      · `YlxwAdvStatNew()`              —— 汇总统计模板，**仅新增一个 `life` 字段**（624272）
      · `YlxwAdvStatAcc(res)`           —— 汇总统计累加，**仅新增寿命一项累加**（625137）
  ★ 本环**不碰**：`Hw`（主循环）/ 事件 roll / 三档几率 / `Fg` 结算 / `Pc` 单条结果 /
    `YlxwAdvResultLog` 的单条格式 / `YlxwAdvAcc` / **任何既有数值口径**
    （修为/灵石/气血/次数/时长/掉落/奇遇/天地之魄/受伤的统计与展示**一行不动**）。
  ★ 本环**唯一新增的数值累加** = 「寿命变化」`res.lifespanChange` 累加进 `YLXW_ADV_STAT.life`
    （team-lead 决策：R-179 原文把「寿命变化」逐字列进第 1 段字段顺序，须真渲染）。
    写法照抄同函数内「气血」那一项（`S.hp += dh`）的位置与形态，变量名 `__r179dl` 前缀防撞名。

==============================================================================
一、改前完整文案结构（对 build/assets/index-v2927-20261006.js 实测）
==============================================================================
  ★ 关键实测：该区块中文在 bundle 内是 **\uXXXX 转义形态**（非裸中文）。
    `\u6298...` 不适用；本块所有中文均为 `\uXXXX` ⇒ 锚点**全部纯 ASCII**（见 §六）。

  当前形态 = R-155（7 条 → 1 条）+ R-161（拆寿元行 + 去重）之后的形态。会话结束时：

  `YlxwAdvSession` 组装头行（`_l155[0]`）：
      🗺 本次自动历练 {YlxwAdvDur(el)}：修为 +{gx} · 灵石 +{gs} · 历练 {gr} 次
  再由 `YlxwAdvSummary(el)` 追加 6 条（`YLXW_ADV156_LINES`）：
      L1  📊 历练统计：共 {runs} 次 · 耗时 {YlxwAdvDur(el)}
      L2  修为 +{exp} · 灵石 +{stone}[ · 气血 {±hp}]
      L3  [抽奖券 +{lot} · ][声望 +{rep} · ]平均每次 修为 +{exp/runs} · 灵石 +{stone/runs}
      L4  事件类型：{YlxwAdvTypeName(k)} {types[k]} · …（含「奇遇 N」）
      L5  物品获得（{N} 种）：a、b、c…
      L6  其他：掉落 {drops} 次 · 奇遇 {lucky} 次 · 天地之魄 {soul} 次[ · 受伤 {hpDown} 次]
  最后由 `/*YLXW_R161_DEDUP*/` 剥掉 L2 前缀里与头行重复的 `修为 +X · 灵石 +Y`，
  再 `add(_l155.join(" · "), "gain")` **合成一条日志条目**。

  ⇒ 改前「同一条日志」的**实际渲染**（按 R-179 样例数值）：
      🗺 本次自动历练 7 分 50 秒：修为 +5,741 · 灵石 +25,831 · 历练 39 次 ·
      📊 历练统计：共 39 次 · 耗时 7 分 50 秒 · 气血 +642 · 平均每次 修为 +147 · 灵石 +662 ·
      事件类型：历练 30 · 奇遇 9 · 物品获得（11 种）：… ·
      其他：掉落 11 次 · 奇遇 9 次 · 天地之魄 0 次 · 受伤 4 次

  ★★ 逐处标出的**重复项**：
      (1) 时长   —— 头行「本次自动历练 7 分 50 秒」 vs L1「耗时 7 分 50 秒」        → 同一信息两处
      (2) 历练次数 —— 头行「历练 39 次」          vs L1「共 39 次」               → 同一信息两处
      (3) 奇遇   —— L4「事件类型：… 奇遇 9」       vs L6「其他：… 奇遇 9 次」       → 同一信息两处
      (4) 修为/灵石 —— 头行一处；L2 已由 R-161 去重（故 L2 实际只剩「气血 ±hp」）   → 本环仍需保证只留一处
      另：`修为 +5,741`（总量）与「平均每次 修为 +147」（派生）**数值不同**，非重复，须保留。

==============================================================================
二、改后目标结构（两段 + 明显分割；仍是**一条日志条目**，非弹窗）
==============================================================================
  第 1 段（主结算，字段顺序**固定**）：
      时长 → 历练次数 → 修为 → 灵石 → 寿命变化 → 气血变化 → 物品获得
      额外奖励字段（抽奖券 / 声望，条件出现）插在「气血变化」之后、「物品获得」之前，
      以**保持上面 7 个字段相邻且次序不变**（寿命紧贴灵石、气血紧贴寿命）。
  分割：`——— 明细 ———`（U+2014 三连 em-dash；bundle 已用 em-dash 5 处、`｜`/`【】` 多处，
        故选用**必然可渲染**的字符，避免用 bundle 从未出现过的制表符/盒绘字符）。
  第 2 段（明细/统计）：
      事件类型（各类次数） · 奇遇 · 掉落 · 天地之魄 · 受伤 · 平均每次（派生值）

  ★ 去重落点：
      (1)(2) 删掉旧头行「本次自动历练 … ：修为…灵石…历练 N 次」整条；
             时长/次数/修为/灵石 统一由第 1 段按固定顺序输出一次。
      (3) 删掉「其他：… 奇遇 N 次」里的**显式**奇遇计数；奇遇保留在「事件类型」这一**权威分布**里
             （`YlxwAdvTypeName("lucky")` → 「奇遇」）。⇒ 奇遇全条目只出现 1 次。
      (4) 修为/灵石 只在第 1 段出现一次（R-161 的「前缀去重」随旧头行一并退役，见下）。

  ★ 派生值「平均每次 修为 +147 · 灵石 +662」的归属判定（本环判断，附理由）：
      归入**第 2 段（明细/统计）**。理由：它是「总量 ÷ 次数」的**派生统计量**，不是一次结算的
      真实收支；第 1 段定义为主结算（真实字段），第 2 段定义为明细/统计。且其位置放在
      明细段尾部，不打断「次数/奇遇/掉落/天地之魄/受伤」这组计数的紧凑阅读。

  ★ 寿命变化（本环新增，team-lead 决策：要真渲染）：
      按需求字段顺序放在「灵石」与「气血变化」之间，**条件渲染**（与「气血变化」同一套写法）：
          if (st.life && Math.abs(st.life) >= 0.05)
            push(st.life > 0 ? "寿命增加 X.X 年" : "寿命减少 X.X 年");
      · 正负号与文案**照抄 `Fg` 内的 R-161 寿命行**（@1905666，原文）：
            `t.lifespanChange&&d(t.lifespanChange>0?`✨ 寿命增加 ${t.lifespanChange.toFixed(1)} 年`
              :`⚠️ 寿命减少 ${Math.abs(t.lifespanChange).toFixed(1)} 年`,…)`
        ⇒ 口径：**正=增加 / 负=减少**，`toFixed(1)`，单位「年」。本环**不带**其 ✨/⚠️ emoji
          （那是整条独立日志行的行首图标；主结算段是 ` · ` 字段流，插 emoji 会破坏字段风格）。
      · `Math.abs(st.life) >= 0.05` 守卫：`toFixed(1)` 对 |值|<0.05 会round成「0.0」，
        该守卫确保**永不**打印「寿命增加/减少 0.0 年」这类噪声（team-lead 要求「为 0 不渲染」）。
      · 累加落点（新增，其余口径不动）：
          `YlxwAdvStatNew()` 模板加 `life: 0`；
          `YlxwAdvStatAcc(res)` 在 `if (dh < 0) S.hpDown += 1;` 之后加
              `var __r179dl = Number(res.lifespanChange) || 0; if (__r179dl) S.life += __r179dl;`
        （**不** `Math.floor`——寿命是小数；与 `res.hpChange` 的整数口径不同）。

==============================================================================
三、改后「一条日志」的实际渲染样例（按 R-179 样例数值）
==============================================================================
  第 1 段：
      🗺 时长 7 分 50 秒 · 历练 39 次 · 修为 +5,741 · 灵石 +25,831 · 气血 +642 ·
      物品获得（11 种）：[炼气期]精铁指环、灵天灵草、小提速丹、妖道髓、凡品合成石、精铁锭、
      紫府仙莲、精品合成石、[炼气期]青莲葫芦、星辰草、紫猴花
  分割：
      ——— 明细 ———
  第 2 段：
      事件类型：历练 30 · 奇遇 9 · 掉落 11 次 · 天地之魄 0 次 · 受伤 4 次 ·
      平均每次 修为 +147 · 灵石 +662

  合并成**一条**（`join(" · ")`，换行仅为阅读方便）：
      🗺 时长 7 分 50 秒 · 历练 39 次 · 修为 +5,741 · 灵石 +25,831 · 气血 +642 ·
      物品获得（11 种）：[炼气期]精铁指环、灵天灵草、小提速丹、妖道髓、凡品合成石、精铁锭、
      紫府仙莲、精品合成石、[炼气期]青莲葫芦、星辰草、紫猴花 · ——— 明细 ——— ·
      事件类型：历练 30 · 奇遇 9 · 掉落 11 次 · 天地之魄 0 次 · 受伤 4 次 ·
      平均每次 修为 +147 · 灵石 +662
  （R-179 样例 stat 无寿命变化 ⇒ 第 1 段无「寿命」项。）

  ★ 寿命变化真渲染样例（本环新增，其余数值同 R-179 样例；实跑 `YlxwAdvSummary` 打出）：
      寿命 = -0.3（净减寿）第 1 段：
        🗺 时长 7 分 50 秒 · 历练 39 次 · 修为 +5,741 · 灵石 +25,831 ·
        寿命减少 0.3 年 · 气血 +642 · 物品获得（11 种）：…
      寿命 = +0.5（净增寿）第 1 段：
        🗺 时长 7 分 50 秒 · 历练 39 次 · 修为 +5,741 · 灵石 +25,831 ·
        寿命增加 0.5 年 · 气血 +642 · 物品获得（11 种）：…
      ⇒ 位置恰在「灵石」与「气血」之间；寿命为 0（或 |值|<0.05）时该项整项不出现。

==============================================================================
四、长度 / 行数约束核对（历史「同帧微批 flush」「一条日志」）
==============================================================================
  · R-146 把同一微任务内多条 addLog 合并成 1 条；R-155 进一步把「本次自动历练」汇总
    合成**一条** addLog；R-161 只把「寿元行」单独拆出。本环**沿用「一条日志」约束**：
    仍然只调用 `add(..., "gain")` **一次**，只是其 `_l155` 数组内容改为
    `[主结算段, 分割符, 明细段]` 三段（旧为「头行 + 6 条」7 段）。
  · 日志渲染器 `Py`（LogItem，@839172）把 `t.text` 直接作为 React 子节点渲染，
    className **不含 `whitespace-pre-line/pre-wrap`** ⇒ **`\n` 不会产生视觉换行**。
    故「明显分割」采用**可见分隔符 `——— 明细 ———`**，而非换行（若改用 `\n` 会被折叠成空格）。
  · 条目长度：本环**不新增条目**，且第 1 段不再重复「本次自动历练…：修为…灵石…历练 N 次」
    头行、第 2 段不再重复「耗时 / 共 N 次 / 奇遇」，净文本量略减。

==============================================================================
五、改法（4 处就地替换，纯 ASCII 注入；变量名 `__r179*` 在基线出现 0 次）
==============================================================================
  E1 重写 `YlxwAdvSummary(el)` 的**文案拼装**：
     · 用 `__r179m` 收集主结算段（时长/次数/修为/灵石/[寿命]/[气血]/[抽奖券/声望]/[物品获得]），
       用 `__r179d` 收集明细段（[事件类型]/掉落/天地之魄/[受伤]/平均每次）；
     · `YLXW_ADV156_LINES = [__r179m.join(" · "), "——— 明细 ———", __r179d.join(" · ")]`；
     · 末尾加幂等标记 `/*[r179advlog]*/`。
     · **既有数值口径一字未动**：`st.exp/st.stone/st.runs/st.hp/st.hpDown/st.lot/st.rep/st.drops/
       st.lucky/st.soul/st.items/st.types` 与 `YlxwAdvDur/YlxwAdvNum/YlxwAdvTypeName`
       全部沿用原实现；`YlxwAdvNum(Math.floor(st.exp/st.runs))` 等派生公式逐字保留。

  E2 改写 `YlxwAdvSession` 的**收尾装配**：
     · 删除旧头行 `_l155` 与 `/*YLXW_R161_DEDUP*/` 前缀去重块（其职能随旧头行一并退役）；
     · 改为 `var _l155 = YLXW_ADV156_LINES.slice();`（直接用 E1 产出的三段）；
     · 保留「st 缺失（runs==0）也要有一条日志」的旧行为：`if (!_l155.length)` 时回退为
       一行极简 `🗺 时长 … · 历练 N 次 · 修为 +… · 灵石 +…`（用 `gr/gx/gs`，避免空日志）；
     · 仍**只调用一次** `add(_l155.join(" · "), "gain")`。

  E3 新增 `YlxwAdvStatNew()` 模板字段（**仅加一个 `life: 0`**）：
     `… hp: 0, hpDown: 0, life: 0,\n           lot: 0, …`（其余字段与次序不动）。

  E4 新增 `YlxwAdvStatAcc(res)` 寿命累加（**仅新增一项**，紧跟「气血」之后）：
     在 `if (dh < 0) S.hpDown += 1;` 之后插入
       `var __r179dl = Number(res.lifespanChange) || 0;`
       `if (__r179dl) S.life += __r179dl;`
     · **不** `Math.floor`（寿命是小数）；**不**改 `S.hp/S.hpDown/S.exp/S.stone/S.runs/...` 任何一行。

  ★ 不改：`Hw` / `Fg` / `Pc` / `YlxwAdvResultLog` / `YlxwAdvAcc` / `YlxwAdvTypeName` /
    `YlxwAdvDur` / `YlxwAdvNum` / 事件生成 / 版本号 /
    `build_v26n.py` / `CHANGELOG*` / 其它 `yl_*_ext.py`。
    （`YlxwAdvStatNew` / `YlxwAdvStatAcc` 只做上述**纯新增**，既有统计口径一行不动。）

==============================================================================
六、锚点（对 build/assets/index-v2927-20261006.js 字符级实测）
==============================================================================
  A_OLD  count==1（1574 chars）→ 打后 0      （旧 Summary 的 6 行拼装，纯 ASCII）
  B_OLD  count==1（ 874 chars）→ 打后 0      （旧 头行 + R-161 去重 + add，纯 ASCII）
  C_OLD  count==1（ 123 chars）→ 打后 0      （旧 统计模板 return 行，纯 ASCII）
  D_OLD  count==1（  59 chars）→ 打后 0      （旧 气血累加收尾两行，纯 ASCII）
  ★ 本块中文在 bundle 内是 **\uXXXX 转义**，故 A/B/C/D 的 OLD 与 NEW **全部纯 ASCII**，
    本环**没有**任何含裸中文的锚点（与 R-169b 情形相反）。
  冻结（对**原件**校验，count 必须 == 1）：
      YLXW_R146_V2919                          ← R-146 在位标记
      YLXW_R161_V2924                          ← R-161 在位标记
      function YlxwAdvResultLog                ← 单条结果日志未动
      function YlxwAdvStatAcc                  ← 统计累加器（仅新增寿命一项）
      YLXW_ADV_STAT = YlxwAdvStatNew();        ← 统计模板（仅新增 life:0）
      function YlxwAdvSession                  ← 会话函数未动
      function Hw(                             ← 主循环未动（与另一代理的边界）
      if (el < 3000) return;                   ← 3 秒门槛未动
      S.hp += dh;                              ← 气血口径未动
      if (dh < 0) S.hpDown += 1;               ← 受伤口径未动
  打后：A_OLD==0 · B_OLD==0 · C_OLD==0 · D_OLD==0 · /*YLXW_R161_DEDUP*/==0 ·
        「耗时 」==0 · 「本次自动历练」==0 · 「其他：」==0 · 显式「奇遇 N 次」==0 ·
        [r179advlog]==1 · A_NEW==1 · B_NEW==1 · C_NEW==1 · D_NEW==1

==============================================================================
七、契约（照 localtest/yl_r169b_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 渲染探针）。
  · 4 处就地替换（E1 Summary / E2 Session / E3 统计模板 / E4 寿命累加），全部纯 ASCII 注入。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r179-<时刻>`。
  · 幂等：产物已含标记 `[r179advlog]` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 渲染探针：抽真实 `YlxwAdvSummary` 跑 3 组 stat（寿命 0 / +0.5 / -0.3），
    断言两段结构、字段顺序、去重、寿命项的**出现与位置**、以及 |值|<0.05 不渲染。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r179advlog]'

# --------------------------------------------------------------------------- 替换项

# E1：重写 YlxwAdvSummary 的文案拼装（旧 6 行 → 主结算段 + 分割 + 明细段）
A_OLD = (
    'if (!st || !st.runs) return;\n'
    '    YLXW_ADV156_LINES = ["\\ud83d\\udcca \\u5386\\u7ec3\\u7edf\\u8ba1\\uff1a\\u5171 " + st.runs + " \\u6b21 \\u00b7 \\u8017\\u65f6 " + YlxwAdvDur(el)];\n'
    '    var l2 = "\\u4fee\\u4e3a +" + YlxwAdvNum(st.exp) + " \\u00b7 \\u7075\\u77f3 +" + YlxwAdvNum(st.stone);\n'
    '    if (st.hp) l2 += " \\u00b7 \\u6c14\\u8840 " + (st.hp > 0 ? "+" : "") + YlxwAdvNum(st.hp);\n'
    '    YLXW_ADV156_LINES.push(l2);\n'
    '    var l3 = [];\n'
    '    if (st.lot) l3.push("\\u62bd\\u5956\\u5238 +" + YlxwAdvNum(st.lot));\n'
    '    if (st.rep) l3.push("\\u58f0\\u671b +" + YlxwAdvNum(st.rep));\n'
    '    l3.push("\\u5e73\\u5747\\u6bcf\\u6b21 \\u4fee\\u4e3a +" + YlxwAdvNum(Math.floor(st.exp / st.runs))\n'
    '      + " \\u00b7 \\u7075\\u77f3 +" + YlxwAdvNum(Math.floor(st.stone / st.runs)));\n'
    '    YLXW_ADV156_LINES.push(l3.join(" \\u00b7 "));\n'
    '    var dist = [], k;\n'
    '    for (k in st.types) { if (st.types[k]) dist.push(YlxwAdvTypeName(k) + " " + st.types[k]); }\n'
    '    if (dist.length) YLXW_ADV156_LINES.push("\\u4e8b\\u4ef6\\u7c7b\\u578b\\uff1a" + dist.join(" \\u00b7 "));\n'
    '    var names = [], it;\n'
    '    for (it in st.items) { if (st.items[it]) names.push(it + (st.items[it] > 1 ? " \\u00d7" + st.items[it] : "")); }\n'
    '    if (names.length) YLXW_ADV156_LINES.push("\\u7269\\u54c1\\u83b7\\u5f97\\uff08" + names.length + " \\u79cd\\uff09\\uff1a" + names.join("\\u3001"));\n'
    '    var l6 = ["\\u6389\\u843d " + st.drops + " \\u6b21", "\\u5947\\u9047 " + st.lucky + " \\u6b21",\n'
    '              "\\u5929\\u5730\\u4e4b\\u9b44 " + st.soul + " \\u6b21"];\n'
    '    if (st.hpDown) l6.push("\\u53d7\\u4f24 " + st.hpDown + " \\u6b21");\n'
    '    YLXW_ADV156_LINES.push("\\u5176\\u4ed6\\uff1a" + l6.join(" \\u00b7 "));'
)

A_NEW = (
    'if (!st || !st.runs) return;\n'
    '    var __r179m = ["\\ud83d\\uddfa \\u65f6\\u957f " + YlxwAdvDur(el),\n'
    '      "\\u5386\\u7ec3 " + st.runs + " \\u6b21",\n'
    '      "\\u4fee\\u4e3a +" + YlxwAdvNum(st.exp),\n'
    '      "\\u7075\\u77f3 +" + YlxwAdvNum(st.stone)];\n'
    '    if (st.life && Math.abs(st.life) >= 0.05) __r179m.push(st.life > 0 ? "\\u5bff\\u547d\\u589e\\u52a0 " + st.life.toFixed(1) + " \\u5e74" : "\\u5bff\\u547d\\u51cf\\u5c11 " + Math.abs(st.life).toFixed(1) + " \\u5e74");\n'
    '    if (st.hp) __r179m.push("\\u6c14\\u8840 " + (st.hp > 0 ? "+" : "") + YlxwAdvNum(st.hp));\n'
    '    if (st.lot) __r179m.push("\\u62bd\\u5956\\u5238 +" + YlxwAdvNum(st.lot));\n'
    '    if (st.rep) __r179m.push("\\u58f0\\u671b +" + YlxwAdvNum(st.rep));\n'
    '    var names = [], it;\n'
    '    for (it in st.items) { if (st.items[it]) names.push(it + (st.items[it] > 1 ? " \\u00d7" + st.items[it] : "")); }\n'
    '    if (names.length) __r179m.push("\\u7269\\u54c1\\u83b7\\u5f97\\uff08" + names.length + " \\u79cd\\uff09\\uff1a" + names.join("\\u3001"));\n'
    '    var __r179d = [];\n'
    '    var dist = [], k;\n'
    '    for (k in st.types) { if (st.types[k]) dist.push(YlxwAdvTypeName(k) + " " + st.types[k]); }\n'
    '    if (dist.length) __r179d.push("\\u4e8b\\u4ef6\\u7c7b\\u578b\\uff1a" + dist.join(" \\u00b7 "));\n'
    '    __r179d.push("\\u6389\\u843d " + st.drops + " \\u6b21");\n'
    '    __r179d.push("\\u5929\\u5730\\u4e4b\\u9b44 " + st.soul + " \\u6b21");\n'
    '    if (st.hpDown) __r179d.push("\\u53d7\\u4f24 " + st.hpDown + " \\u6b21");\n'
    '    __r179d.push("\\u5e73\\u5747\\u6bcf\\u6b21 \\u4fee\\u4e3a +" + YlxwAdvNum(Math.floor(st.exp / st.runs))\n'
    '      + " \\u00b7 \\u7075\\u77f3 +" + YlxwAdvNum(Math.floor(st.stone / st.runs)));\n'
    '    YLXW_ADV156_LINES = [__r179m.join(" \\u00b7 "),\n'
    '      "\\u2014\\u2014\\u2014 \\u660e\\u7ec6 \\u2014\\u2014\\u2014",\n'
    '      __r179d.join(" \\u00b7 ")];/*[r179advlog]*/'
)

# E2：改写 YlxwAdvSession 的收尾装配（删旧头行 + R-161 去重；仍只 add 一次）
B_OLD = (
    '    YLXW_ADV156_LINES = [];\n'
    '    YlxwAdvSummary(el);\n'
    '    var _l155 = ["\\ud83d\\uddfa \\u672c\\u6b21\\u81ea\\u52a8\\u5386\\u7ec3 " + YlxwAdvDur(el)\n'
    '      + "\\uff1a\\u4fee\\u4e3a +" + gx.toLocaleString()\n'
    '      + " \\u00b7 \\u7075\\u77f3 +" + gs.toLocaleString()\n'
    '      + " \\u00b7 \\u5386\\u7ec3 " + gr + " \\u6b21"];\n'
    '    for (var _i155 = 0; _i155 < YLXW_ADV156_LINES.length; _i155++) _l155.push(YLXW_ADV156_LINES[_i155]);\n'
    '    /*YLXW_R161_DEDUP*/(function(){var _h=/\\uff1a\\u4fee\\u4e3a \\+([\\d,]+) \\u00b7 \\u7075\\u77f3 \\+([\\d,]+)/.exec(_l155[0]||"");if(!_h)return;var _d="\\u4fee\\u4e3a +"+_h[1]+" \\u00b7 \\u7075\\u77f3 +"+_h[2];for(var _i=1;_i<_l155.length;_i++){var _e=_l155[_i];if(_e.indexOf(_d)===0){var _r=_e.slice(_d.length);if(_r.indexOf(" \\u00b7 ")===0)_r=_r.slice(3);if(_r){_l155[_i]=_r}else{_l155.splice(_i,1);_i--}}}})();\n'
    '    YLXW_ADV156_LINES = [];\n'
    '    add(_l155.join(" \\u00b7 "), "gain");'
)

B_NEW = (
    '    YLXW_ADV156_LINES = [];\n'
    '    YlxwAdvSummary(el);\n'
    '    var _l155 = YLXW_ADV156_LINES.slice();\n'
    '    YLXW_ADV156_LINES = [];\n'
    '    if (!_l155.length) _l155 = ["\\ud83d\\uddfa \\u65f6\\u957f " + YlxwAdvDur(el)\n'
    '      + " \\u00b7 \\u5386\\u7ec3 " + gr + " \\u6b21"\n'
    '      + " \\u00b7 \\u4fee\\u4e3a +" + gx.toLocaleString()\n'
    '      + " \\u00b7 \\u7075\\u77f3 +" + gs.toLocaleString()];\n'
    '    add(_l155.join(" \\u00b7 "), "gain");'
)

# E3：统计模板 YlxwAdvStatNew() —— 仅新增一个 life 字段（其余字段与次序不动）
C_OLD = ('  return { sess: null, runs: 0, exp: 0, stone: 0, hp: 0, hpDown: 0,\n'
         '           lot: 0, rep: 0, drops: 0, lucky: 0, soul: 0, items: {}, types: {} };')
C_NEW = ('  return { sess: null, runs: 0, exp: 0, stone: 0, hp: 0, hpDown: 0, life: 0,\n'
         '           lot: 0, rep: 0, drops: 0, lucky: 0, soul: 0, items: {}, types: {} };')

# E4：统计累加 YlxwAdvStatAcc(res) —— 仅新增寿命一项（紧跟气血之后；不 floor，寿命是小数）
D_OLD = ('  S.hp += dh;\n'
         '  if (dh < 0) S.hpDown += 1;\n')
D_NEW = ('  S.hp += dh;\n'
         '  if (dh < 0) S.hpDown += 1;\n'
         '  var __r179dl = Number(res.lifespanChange) || 0;\n'
         '  if (__r179dl) S.life += __r179dl;\n')

REPS = [
    ('R179-E1 汇总文案重排+去重（Summary）', A_OLD, A_NEW),
    ('R179-E2 会话收尾装配（删旧头行+R161去重）', B_OLD, B_NEW),
    ('R179-E3 统计模板新增 life 字段', C_OLD, C_NEW),
    ('R179-E4 统计累加新增寿命一项', D_OLD, D_NEW),
]

# 冻结针脚：本环只动上面四处，下列既有形态必须逐字在位（对**原件**校验）
FREEZE = [
    ('YLXW_R146_V2919', 1),                          # R-146 在位标记
    ('YLXW_R161_V2924', 1),                          # R-161 在位标记
    ('function YlxwAdvResultLog', 1),                # 单条结果日志未动
    ('function YlxwAdvStatAcc', 1),                  # 统计累加器（仅新增寿命一项）
    ('YLXW_ADV_STAT = YlxwAdvStatNew();', 1),        # 统计模板（仅新增 life:0）
    ('function YlxwAdvSession', 1),                  # 会话函数未动
    ('function Hw(', 1),                             # 主循环未动（与另一代理边界）
    ('if (el < 3000) return;', 1),                   # 3 秒门槛未动
    ('S.hp += dh;', 1),                              # 气血口径未动
    ('if (dh < 0) S.hpDown += 1;', 1),               # 受伤口径未动
]


# ★ 0.9.28 与老环（R-138 / R-155 / R-161）的**交接说明**（老环侧已加 `SUPERSEDED_BY_R179` 过滤，**非静默删除**）：
#   本环重写了「自动历练结束汇总」的装配 ⇒ 下列老环针脚在最终产物上不再成立（实测 actual=0），由本环承接：
#     · R138·汇总含次数/耗时 / R138·汇总含其他计数 / 冻结·R105 汇总头行文案逐字保留
#       → 承接：`R179·★耗时重复已清零` / `R179·★其他行已清零` / `R179·★旧头行已清零` / `R179·时长字段唯一` / `R179·历练次数字段唯一`
#     · R155·统计行已收集 / 修为行已收集 / 均值行已收集 / 事件类型行已收集 / 物品行已收集 / 其他行已收集 / 发送后清空
#       → 承接：`R179·仍只 add 一次` / `R179·空日志回退保留` / `R179·事件类型在明细` / `R179·平均每次在明细` /
#                `R179·物品获得在主结算`；「每会话重置」由老环 `R155·收集器初始化` 继续保证（该针脚仍在位）
#     · R161·去重标记 / 去重取头行总计 / 去重剥前缀 / 冻结·R155发送后清空
#       → 承接：`R179·★R161去重块已清零` / `R179·★耗时重复已清零` / `R179·★显式奇遇重复已清零`
#                （去重**改由构造保证**，不再需要「从 _l155[0] 取头行总计 + 剥前缀」那套字符串去重）


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R179·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r179advlog] 恰好 1 处'),
        ('R179·主结算段已注入', A_NEW, 1, '==', '重排后的 Summary 恰好 1 处'),
        ('R179·会话装配已改写', B_NEW, 1, '==', '收尾装配恰好 1 处'),
        ('R179·旧 Summary 已消失', A_OLD, 0, '==', '旧 6 行拼装已删除'),
        ('R179·旧装配已消失', B_OLD, 0, '==', '旧头行+R161去重已删除'),
        ('R179·★R161去重块已清零', '/*YLXW_R161_DEDUP*/', 0, '==', '随旧头行退役'),
        ('R179·★耗时重复已清零', '\\u8017\\u65f6 ', 0, '==', '旧「耗时 X」重复项已删'),
        ('R179·★旧头行已清零', '\\u672c\\u6b21\\u81ea\\u52a8\\u5386\\u7ec3', 0, '==', '旧「本次自动历练」头行已删'),
        ('R179·★其他行已清零', '\\u5176\\u4ed6\\uff1a', 0, '==', '旧「其他：」行已删'),
        ('R179·★显式奇遇重复已清零', '\\u5947\\u9047 " + st.lucky + " \\u6b21', 0, '==', '显式「奇遇 N 次」已删（保留于事件类型）'),
        ('R179·时长字段唯一', 'var __r179m = ["\\ud83d\\uddfa \\u65f6\\u957f " + YlxwAdvDur(el),', 1, '==', '第1段首字段「时长」'),
        ('R179·历练次数字段唯一', '\\u5386\\u7ec3 " + st.runs + " \\u6b21', 1, '==', '第1段「历练 N 次」'),
        ('R179·修为字段在主结算', '\\u4fee\\u4e3a +" + YlxwAdvNum(st.exp)', 1, '==', '第1段「修为 +exp」'),
        ('R179·灵石字段在主结算', '\\u7075\\u77f3 +" + YlxwAdvNum(st.stone)', 1, '==', '第1段「灵石 +stone」'),
        ('R179·寿命真渲染-增加', '\\u5bff\\u547d\\u589e\\u52a0 ', 1, '==', '第1段「寿命增加 X.X 年」'),
        ('R179·寿命真渲染-减少', '\\u5bff\\u547d\\u51cf\\u5c11 ', 1, '==', '第1段「寿命减少 X.X 年」'),
        ('R179·寿命渲染守卫', 'Math.abs(st.life) >= 0.05', 1, '==', '|值|<0.05 不渲染，避免 0.0 噪声'),
        ('R179·旧寿命占位已清零', '\\u5bff\\u547d " + (st.life', 0, '==', '旧占位写法已删'),
        ('R179·寿命累加已注入', 'var __r179dl = Number(res.lifespanChange) || 0;', 1, '==', 'E4 累加唯一'),
        ('R179·寿命累加不 floor', 'if (__r179dl) S.life += __r179dl;', 1, '==', '小数口径（不 floor）'),
        ('R179·统计模板已加 life', C_NEW, 1, '==', 'YlxwAdvStatNew 模板含 life:0'),
        ('R179·旧统计模板已消失', C_OLD, 0, '==', ''),
        ('R179·气血字段在主结算', '\\u6c14\\u8840 " + (st.hp', 1, '==', '第1段「气血 ±hp」'),
        ('R179·物品获得在主结算', '\\u7269\\u54c1\\u83b7\\u5f97\\uff08', 1, '==', '第1段「物品获得」'),
        ('R179·分割符唯一', '\\u2014\\u2014\\u2014 \\u660e\\u7ec6 \\u2014\\u2014\\u2014', 1, '==', '两段之间明显分割'),
        ('R179·事件类型在明细', '\\u4e8b\\u4ef6\\u7c7b\\u578b\\uff1a', 1, '==', '明细段保留事件类型'),
        ('R179·掉落仍在明细', '\\u6389\\u843d " + st.drops + " \\u6b21', 1, '==', '明细段保留掉落'),
        ('R179·天地之魄仍在明细', '\\u5929\\u5730\\u4e4b\\u9b44 " + st.soul + " \\u6b21', 1, '==', '明细段保留天地之魄'),
        ('R179·受伤条件保留', '\\u53d7\\u4f24 " + st.hpDown + " \\u6b21', 1, '==', '明细段保留受伤'),
        ('R179·平均每次在明细', '\\u5e73\\u5747\\u6bcf\\u6b21 \\u4fee\\u4e3a +', 1, '==', '派生值归入明细段'),
        ('R179·仍只 add 一次', 'add(_l155.join(" \\u00b7 "), "gain");', 1, '==', '一条日志约束保持'),
        ('R179·空日志回退保留', 'if (!_l155.length) _l155 = [', 1, '==', 'st 缺失时仍有一条日志'),
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
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
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


def _summary_probe(patched_text):
    """从补丁后产物抽出**真实** YlxwAdvSummary，用 node 验证：顺序 / 去重 / 分割 / 数值。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。
    """
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    i = patched_text.find('function YlxwAdvSummary(el) {')
    j = patched_text.find('\nfunction YlxwAdvSession', i)
    if i < 0 or j < 0:
        return False, 'YlxwAdvSummary 定义/边界未找到'
    fn = patched_text[i:j]
    js = (
        fn + '\n'
        'var YLXW_ADV156_LINES = [];\n'
        'var Be = { getState: function(){ return { addLog: function(){} }; } };\n'
        'function YlxwAdvDur(ms){ var tot=Math.max(0,Math.floor(Number(ms)||0)/1000);\n'
        '  var hh=Math.floor(tot/3600),mm=Math.floor((tot%3600)/60),qq=Math.floor(tot%60);\n'
        '  if(hh>0)return hh+" \\u5c0f\\u65f6 "+mm+" \\u5206";\n'
        '  if(mm>0)return mm+" \\u5206 "+qq+" \\u79d2"; return qq+" \\u79d2"; }\n'
        'function YlxwAdvNum(n){ return Math.floor(Number(n)||0).toLocaleString(); }\n'
        'function YlxwAdvTypeName(t){ return {normal:"\\u5386\\u7ec3",lucky:"\\u5947\\u9047",'
        'secret_realm:"\\u79d8\\u5883",sect_challenge:"\\u5b97\\u95e8\\u6311\\u6218",'
        'dao_combining_challenge:"\\u5929\\u5730\\u4e4b\\u9b44\\u6311\\u6218"}[t||""]||"\\u5386\\u7ec3"; }\n'
        'function base(){ return { runs:39, exp:5741, stone:25831, hp:642, hpDown:4, life:0,\n'
        '  lot:0, rep:0, drops:11, lucky:9, soul:0,\n'
        '  items:{"\\u7075\\u5929\\u7075\\u8349":1,"\\u7cbe\\u94c1\\u952d":2}, types:{normal:30, lucky:9} }; }\n'
        'function RUN(st){ YLXW_ADV156_LINES=[]; YLXW_ADV_STAT=st; YlxwAdvSummary(470000); return YLXW_ADV156_LINES.slice(); }\n'
        'var A = RUN(base());\n'
        'var out = A.join(" \\u00b7 ");\n'
        'function idx(s){ return out.indexOf(s); }\n'
        'if (A.length !== 3) throw new Error("\\u6bb5\\u6570\\u5e94\\u4e3a3: "+A.length);\n'
        'var main=A[0], div=A[1], det=A[2];\n'
        'if (div !== "\\u2014\\u2014\\u2014 \\u660e\\u7ec6 \\u2014\\u2014\\u2014") throw new Error("\\u5206\\u5272\\u7b26\\u5f02\\u5e38: "+div);\n'
        'var o1=idx("\\u65f6\\u957f "), o2=idx("\\u5386\\u7ec3 39 \\u6b21"), o3=idx("\\u4fee\\u4e3a +5,741"),\n'
        '    o4=idx("\\u7075\\u77f3 +25,831"), o5=idx("\\u6c14\\u8840 +642"), o6=idx("\\u7269\\u54c1\\u83b7\\u5f97\\uff082 \\u79cd\\uff09");\n'
        'if (main.slice(0,3) !== "\\ud83d\\uddfa ") throw new Error("\\u4e3b\\u7ed3\\u7b97\\u6bb5\\u9996\\u5e94\\u4e3a\\u56fe\\u6807+\\u7a7a\\u683c");\n'
        'if (!(o1===3 && o1<o2 && o2<o3 && o3<o4 && o4<o5 && o5<o6)) throw new Error("\\u4e3b\\u7ed3\\u7b97\\u5b57\\u6bb5\\u987a\\u5e8f\\u9519: "+[o1,o2,o3,o4,o5,o6]);\n'
        'if (idx("\\u2014\\u2014\\u2014 \\u660e\\u7ec6 \\u2014\\u2014\\u2014") < o6) throw new Error("\\u5206\\u5272\\u7b26\\u5e94\\u665a\\u4e8e\\u7269\\u54c1\\u83b7\\u5f97");\n'
        'if (!(idx("\\u4e8b\\u4ef6\\u7c7b\\u578b\\uff1a\\u5386\\u7ec3 30 \\u00b7 \\u5947\\u9047 9") > idx("\\u2014\\u2014\\u2014 \\u660e\\u7ec6"))) throw new Error("\\u4e8b\\u4ef6\\u7c7b\\u578b\\u5e94\\u5728\\u660e\\u7ec6\\u6bb5");\n'
        'if (idx("\\u6389\\u843d 11 \\u6b21")<0 || idx("\\u5929\\u5730\\u4e4b\\u9b44 0 \\u6b21")<0 || idx("\\u53d7\\u4f24 4 \\u6b21")<0) throw new Error("\\u660e\\u7ec6\\u8ba1\\u6570\\u7f3a\\u5931");\n'
        'if (idx("\\u5e73\\u5747\\u6bcf\\u6b21 \\u4fee\\u4e3a +147 \\u00b7 \\u7075\\u77f3 +662")<0) throw new Error("\\u5e73\\u5747\\u6bcf\\u6b21\\u5f02\\u5e38");\n'
        'if (out.split("\\u5947\\u9047").length-1 !== 1) throw new Error("\\u5947\\u9047\\u5e94\\u53ea1\\u6b21");\n'
        'if (out.indexOf("\\u8017\\u65f6")>=0 || out.indexOf("\\u672c\\u6b21\\u81ea\\u52a8\\u5386\\u7ec3")>=0 || out.indexOf("\\u5176\\u4ed6\\uff1a")>=0) throw new Error("\\u65e7\\u91cd\\u590d\\u9879\\u4ecd\\u5728");\n'
        'if (out.split("\\u4fee\\u4e3a +5,741").length-1 !== 1) throw new Error("\\u4fee\\u4e3a\\u603b\\u91cf\\u5e94\\u53ea1\\u6b21");\n'
        'if (out.split("\\u7075\\u77f3 +25,831").length-1 !== 1) throw new Error("\\u7075\\u77f3\\u603b\\u91cf\\u5e94\\u53ea1\\u6b21");\n'
        # ---- 寿命变化三态：0 不渲染 / +0.5 增加 / -0.3 减少，且位置在灵石与气血之间 ----
        'if (main.indexOf("\\u5bff\\u547d")>=0) throw new Error("\\u5bff\\u547d=0 \\u4e0d\\u5e94\\u51fa\\u73b0: "+main);\n'
        'var bP=base(); bP.life=0.5; var P=RUN(bP);\n'
        'var pA=P[0].indexOf("\\u7075\\u77f3 +25,831"), pL=P[0].indexOf("\\u5bff\\u547d\\u589e\\u52a0 0.5 \\u5e74"), pB=P[0].indexOf("\\u6c14\\u8840 +642");\n'
        'if (!(pL>=0 && pA>=0 && pB>=0 && pA<pL && pL<pB)) throw new Error("\\u5bff\\u547d\\u589e\\u52a0\\u9879\\u4f4d\\u7f6e\\u9519: "+[pA,pL,pB]+" / "+P[0]);\n'
        'var bN=base(); bN.life=-0.3; var N=RUN(bN);\n'
        'var nA=N[0].indexOf("\\u7075\\u77f3 +25,831"), nL=N[0].indexOf("\\u5bff\\u547d\\u51cf\\u5c11 0.3 \\u5e74"), nB=N[0].indexOf("\\u6c14\\u8840 +642");\n'
        'if (!(nL>=0 && nA>=0 && nB>=0 && nA<nL && nL<nB)) throw new Error("\\u5bff\\u547d\\u51cf\\u5c11\\u9879\\u4f4d\\u7f6e\\u9519: "+[nA,nL,nB]+" / "+N[0]);\n'
        'var bZ=base(); bZ.life=0.02; var Z=RUN(bZ);\n'
        'if (Z[0].indexOf("\\u5bff\\u547d")>=0) throw new Error("|\\u5bff\\u547d|<0.05 \\u4e0d\\u5e94\\u6e32\\u67d3(0.0\\u566a\\u58f0): "+Z[0]);\n'
        'console.log("summary-probe OK");\n'
        'console.log("LIFE0_MAIN>> "+A[0]);\n'
        'console.log("LIFE_POS_MAIN>> "+P[0]);\n'
        'console.log("LIFE_NEG_MAIN>> "+N[0]);\n'
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
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 渲染探针。"""
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r179] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r179] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r179] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r179] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r179] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r179] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _summary_probe(out)
    if ok is False:
        print('[r179] SELFTEST FAIL summary-probe: ' + pmsg)
        return 1
    print('[r179] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s; %s'
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
        print('[r179] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r179] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r179] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r179] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r179] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r179] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-40s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r179-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r179] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-40s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
