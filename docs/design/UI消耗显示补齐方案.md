# yl 界面消耗显示补齐方案（4 处）

**目标 bundle**：`build/assets/index-v26k-20260927.js`（1416782 字符，1189 行）
**本文档性质**：只读分析 + 精确 old/new 片段，**不修改 bundle**（改由 team-lead 执行）。

---

## 0. 校验结论（先看这里）

对本文 5 条 old 锚点（4 处分节共 5 条编辑，其中「挑战禁地」有 2 个入口）已做机械校验：

| 项 | 结果 |
|---|---|
| 每条 old 在 bundle 中的命中次数 | **全部 = 1**（唯一，可直接 `str.replace`） |
| 新增字符中的非 ASCII 字符 | **0**（中文一律写成 `\uXXXX`） |
| 往返等价（new→old 还原后与原文逐字节相同） | **通过** |
| `node --check` 对打完补丁的产物 | **语法通过** |

> 说明：bundle 里中文**两种形态混用**。本文 old 片段**原样逐字**抄自 bundle —— 灵宠/灵田/悬赏在**伴生页**里是 `\uXXXX` 转义形态；宗门相关（挑战禁地）是**字面 UTF-8** 形态。抄写时不要互相转换，否则锚点必然落空。

### 一个真实踩坑记录（已修正，供参考）
第一版草稿里「悬赏发布」的 new 片段漏了一个收尾双引号（`children: "\u53d1\u5e03 }), ...`），
`node --check` 报 `SyntaxError: Unexpected identifier 'span'`。
**结论：改完 bundle 后务必跑一次 `node --check`，纯字符串替换极易吃掉引号。**

---

## 1. 妖灵喂养（灵宠面板「喂养」按钮）

### 位置说明
- 组件：伴生页「妖灵」面板 `YlxwTPet`（路由 `/yl/apps/pet/`）。
- 渲染点：offset **806754**，第 **988** 行。该行是 `m && e.jsxs("div",{className:"flex gap-2",children:[ ...喂养按钮..., ...嬉戏按钮... ]})`。
- 当前界面：只有两个按钮 `喂养` / `嬉戏`，**没有任何金额**。

### 成本来源
- 服务端 `srv/index.ts:4000` `const PET_FEED_COST = 5000`；`srv/index.ts:7602` 在 `GET /api/pet` 响应里返回
  `consts: { feedCost: PET_FEED_COST, ... }`。
- 客户端 `YlxwTPet` 里已有 `t = r.data`（即 `/pet` 响应），并且**同一函数内已经在用** `t.consts.playDailyMax`。
- **结论：成本值客户端已可得，无需新增接口字段**，直接读 `t.consts.feedCost`。

### old 片段（转义形态，命中 **1** 次）
```
f("feed", "/pet/feed", {}, "\u5df2\u5582\u517b"); }, children: "\u5582\u517b" })
```

### new 片段
```
f("feed", "/pet/feed", {}, "\u5df2\u5582\u517b"); }, children: "\u5582\u517b\uff08\u6d88\u8017 " + YlxwNum(t && t.consts && t.consts.feedCost) + " \u7075\u77f3\uff09" })
```

**渲染效果**：按钮文案由 `喂养` → `喂养（消耗 5000 灵石）`

### 风险提示
- `YlxwNum(r)` 定义在 bundle offset 784941，是模块级函数：`function YlxwNum(r) { return Number(r) || 0; }`，可直接引用。
- `t` 为 `null`（接口未返回）时 `t && t.consts && t.consts.feedCost` 短路为 `undefined` → `YlxwNum` 得 `0` → 显示「消耗 0 灵石」。**不会抛异常，但会显示 0**。若要避免，把 `t.consts.feedCost` 换成 `(t && t.consts && t.consts.feedCost) || 5000`（硬编码服务端常量兜底）。
- 按钮的 `disabled: !!u` 逻辑未动，`/pet/feed` 请求体未动，**只改文案**。
- 同类样板：`xianwu_fix5.py` 的 B6（创建宗门文案 5000→50000），本次是同族最小改动。

---

## 2. 灵田种植（选择作物 / 种植按钮）

### 位置说明
- 组件：伴生页「灵田」面板 `YlxwTFarm`（路由 `/yl/apps/farm/`）。
- 渲染点：offset **798715**，第 **951** 行。对每个「已解锁且空闲」的田位，为每种作物渲染一个按钮：
  `N.unlocked && !b && h.map(function(x){ return e.jsx(YlxwBtn,{ tone:"ghost", ..., children: (g[x]&&g[x].name)||YLXW_CROP[x]||x }, x); })`
- 当前界面：按钮只写作物名（`灵草` / `灵芝` / `千年参`），**没有种子价**。
- 同行旁边的「开垦」按钮**已经**显示了 `unlockCost[N.slot]`，本次不动。

### 成本来源
- 服务端 `srv/index.ts:3971` `FARM_CROPS`，每项含 `seed`（灵石种子价）：
  | key | name | seed |
  |---|---|---|
  | `lingcao` | 灵草 | **1000** |
  | `lingzhi` | 灵芝 | **5000** |
  | `qianniancan` | 千年参 | **20000** |
- `srv/index.ts:5246` `GET /api/farm/status` 返回 `{ ..., crops: FARM_CROPS, unlockCost: FARM_UNLOCK_COST }`。
- 客户端 `YlxwTFarm` 里已有 `g = (t && t.crops) || {}`、`h = Object.keys(g)`。
- **结论：成本值客户端已可得**，直接读 `g[x].seed`，无需新增接口字段。

### old 片段（ASCII 形态，命中 **1** 次）
```
children: (g[x] && g[x].name) || YLXW_CROP[x] || x }
```

### new 片段
```
children: ((g[x] && g[x].name) || YLXW_CROP[x] || x) + "\uff08" + YlxwNum(g[x] && g[x].seed) + " \u7075\u77f3\uff09" }
```

**渲染效果**：按钮文案 `灵草` → `灵草（1000 灵石）`；`灵芝` → `灵芝（5000 灵石）`；`千年参` → `千年参（20000 灵石）`

### 风险提示
- **必须加外层括号**。原 `children:` 的值是 `a || b || c` 表达式，若不包括号直接接 `+ "..."`，`+` 优先级高于 `||`，会变成 `a || b || (c + "...")` —— 只有第三种回退分支才带金额，前两种（正常情况）不带。这是本处最容易写错的地方。
- `g[x]` 不存在时 `YlxwNum(undefined) = 0`；但此时 `h = Object.keys(g)` 为空数组，按钮根本不渲染，**该分支不可达**。
- 同一函数内 `YLXW_CROP` 是本地兜底表（作物 key→中文名），`seed` 只能从 `g[x]` 取（服务端权威值），不要用 `YLXW_CROP` 兜底数字。

---

## 3. 挑战禁地（宗主挑战入口）

### 位置说明（成本待确认项 —— 已确认）
先澄清：**服务端没有这个扣费**。
- 在 `srv/index.ts` 搜 `禁地 / forbidden / trial / dungeon`：
  - `/api/dungeon/*`（`srv/index.ts:7904-7966`）是「秘境/地宫」的**软门槛计数与异常标记**，只上报次数，**无任何灵石消耗**。
  - `srv/index.ts:7792` `/api/rebirth/challenge` 是**渡劫天劫**，与「挑战禁地」无关。
- 真实扣费在**客户端**：`Hn` 常量（bundle offset **332002**，第 **641** 行）：
  ```js
  Hn = {
    minRealm: ae.NascentSoul,        // 元婴
    minContribution: 1e4,            // 10000 宗门贡献
    challengeCost: { spiritStones: 5e5 },   // ★ 500000 灵石
    victoryReward: { exp: 5e4, spiritStones: 1e5 },
    defeatPenalty: { contributionLoss: 2e3, hpLossPercent: .3 },
  }
  ```
  实扣点在 `handleChallengeLeader`（offset 1234357）：
  `r(E=>({...E,spiritStones:E.spiritStones-Hn.challengeCost.spiritStones}))`
  → **实扣 500000 灵石**。

**两个 UI 入口（都在主应用宗门面板，都是字面 UTF-8 形态）：**

- **3a 确认框**：offset **946620**，第 **1123** 行。长老点「申请晋升」且下一阶是宗主时弹出：
  ``an(`宗主之位需通过挑战禁地并战胜上代宗主方可继任。\n\n挑战失败将损失贡献和气血，是否确认挑战？`,"挑战宗主",()=>{j()})``
  → 只讲失败惩罚，**不提 500000 灵石**。
- **3b 按钮**：offset **947453**，第 **1126** 行。长老面板里的 `🔥 挑战宗主 🔥` 按钮 `onClick:j`，**连确认框都没有**，点了直接进扣费流程，界面上零提示。

### 成本来源
`Hn` 是**模块顶层常量**（与两处 UI 同模块），两处都可直接引用 `Hn.challengeCost.spiritStones`。
**结论：成本值客户端已可得，无需新增接口字段，也不需要硬编码。**

### 3a old 片段（**字面 UTF-8** 形态，命中 **1** 次）
```
是否确认挑战？
```

### 3a new 片段
```
是否确认挑战？\uff08\u9700\u6d88\u8017 ${Hn.challengeCost.spiritStones} \u7075\u77f3\uff09
```

**渲染效果**：`……是否确认挑战？（需消耗 500000 灵石）`

> 关键：该串位于**模板字面量**（反引号）内，`${...}` 会被求值，不需要改成字符串拼接。

### 3b old 片段（**字面 UTF-8 + 字面 emoji**，命中 **1** 次）
```
children:"🔥 挑战宗主 🔥"
```

### 3b new 片段
```
children:["🔥 挑战宗主 🔥","\uff08\u6d88\u8017 "+Hn.challengeCost.spiritStones+" \u7075\u77f3\uff09"]
```

**渲染效果**：按钮文案 `🔥 挑战宗主 🔥` → `🔥 挑战宗主 🔥（消耗 500000 灵石）`

### 风险提示
- **形态混用是合法的**：3a/3b 命中处原本是字面 UTF-8，新增部分用 `\uXXXX`，同一字符串里混用 JS 完全合法。这样既满足「新增代码无非 ASCII 字符」，又不用改动原有中文形态。
- **3b 把 `children` 从字符串改成数组**，React 渲染等价（`["a","b"]` 与 `"ab"` 视觉相同）。按钮 `className` 含 `w-full py-3`，宽度足够，文案变长大概率不换行；若线上发现换行，可把新增文案移到按钮下方加一行 `<p>`。
- **文案与实际不会脱节**：`handleChallengeLeader` 内已有「境界 / 贡献 / 灵石」三重预检并以 `f()` 报错，按钮上写的 500000 与预检读的是同一个 `Hn.challengeCost.spiritStones`，后续调参自动跟随（3a 用插值、3b 用变量），**无需二次改文案**。
- 另有第三处同源文案（**本次建议不改**）：`handleSectPromote` 里 `f("宗主之位需通过挑战禁地并战胜上代宗主方可继任。","danger")`（offset 1231862，第 1150 行附近），是「晋升到宗主被拦」的提示。注意它的短锚点 `宗主之位需通过挑战禁地并战胜上代宗主方可继任。` 有 **2 次命中**，若要改必须用更长上下文区分（如带 `,"danger"` 后缀）。
- 3b 按钮只在 `a.sectRank === ot.Elder`（长老）时渲染，普通弟子看不到，属预期。

---

## 4. 悬赏发布（发布悬赏面板）

### 位置说明
- 组件：伴生页「悬赏」面板 `YlxwTBounty`（路由 `/yl/apps/bounty/`）。
- 渲染点：offset **820006**，第 **1018** 行。该行是发布行：
  `[悬赏标题 input] [赏金 input] [发布 button]`
- 当前界面：只有标题输入、赏金输入、`发布` 按钮，**完全没提托管与手续费**。

### 成本来源
- 服务端 `srv/index.ts:3936-3941`：`BOUNTY_FEE_RATE = 0.1`、`BOUNTY_MIN_REWARD = 100`、`BOUNTY_MAX_REWARD = 1000000`。
- `srv/index.ts:8176` `GET /api/bounty/list` 返回 `consts: { minReward, maxReward, feeRate, acceptMax, posterOpenMax }`。
- 口径（`srv/index.ts:3934-3935`）：**发布即全额托管**（扣 `reward`），发布者确认完成后接受者得 `payout = floor(reward × 90%)`，差额 10% 为系统税；取消 / 24h 过期退全款。
- 客户端 `YlxwTBounty` 里 `t = r.data` 正是 `/bounty/list` 的响应。
- **结论：`t.consts.feeRate` 客户端已可得，无需新增接口字段。**

### old 片段（转义形态，命中 **1** 次）
```
children: "\u53d1\u5e03" })] })
```

### new 片段
```
children: "\u53d1\u5e03" }), e.jsx("span", { className: "text-xs text-stone-400 ml-2", children: T ? "\u9700\u51bb\u7ed3 " + YlxwNum(T) + " \u7075\u77f3\uff0c\u5b8c\u6210\u65b9\u5b9e\u5f97 " + YlxwNum(Math.floor(T * (1 - ((t && t.consts && t.consts.feeRate) || 0.1)))) + " \u7075\u77f3\uff08\u624b\u7eed\u8d39 10%\uff09" : "\u9700\u5168\u989d\u51bb\u7ed3\u8d4f\u91d1\uff0c\u5b8c\u6210\u65b9\u5b9e\u5f97 90%\uff08\u624b\u7eed\u8d39 10%\uff09" })] })
```

**渲染效果**：
- 未填赏金：`需全额冻结赏金，完成方实得 90%（手续费 10%）`
- 赏金填 500：`需冻结 500 灵石，完成方实得 450 灵石（手续费 10%）`

### 风险提示
- `T` 是 `O.useState("")` 的第 0 位，但 `onChange` 里已做 `$(Math.floor(Number(M.target.value) || 0))`，所以**运行时 T 恒为数字**；`T` 为 `0`（未填）时走静态分支，逻辑正确。
- 手续费率用 `(t && t.consts && t.consts.feeRate) || 0.1` 兜底（`t` 未加载时取 0.1），与服务端 `BOUNTY_FEE_RATE = 0.1` 一致；`Math.floor(reward × (1-fee))` 与服务端 `bountyPayout()` 同口径，**显示值不会和到账值打架**。
- 新 span 的 `className` 沿用同页其它提示的风格（`text-xs text-stone-400`）。`YlxwRow` 渲染的是普通 `div`（非 flex），span 会跟在发布按钮同一行流式排列；若嫌挤可把 `ml-2` 换成 `ml-2 block` 让它独占一行。
- 未做（可选增强，不在本次最小改动内）：把 `minReward` / `maxReward` 通过 `title` 属性挂到赏金输入框上，提示「100 ~ 1000000」的合法区间。服务端越界会返回 400 错误文案，属可接受的现状。

---

## 附录 A：补丁脚本骨架（供 team-lead 直接改用）

```python
# -*- coding: utf-8 -*-
import hashlib, io, os, sys
SRC = "build/assets/index-v26k-20260927.js"
DST = "build/assets/index-v26k-<下一版>.js"
B = chr(92)
def e(u): return B + "u" + u
YANG     = e("5582") + e("517b")               # 喂养
YANGDONE = e("5df2") + e("5582") + e("517b")   # 已喂养
FABU     = e("53d1") + e("5e03")               # 发布
XIAOHAO  = e("6d88") + e("8017")               # 消耗
LINGSHI  = e("7075") + e("77f3")               # 灵石
LP, RP   = e("ff08"), e("ff09")                # （ ）

EDITS = [
  # 1 妖灵喂养（伴生页 /pet）—— 转义形态
  ('f("feed", "/pet/feed", {}, "'+YANGDONE+'"); }, children: "'+YANG+'" })',
   'f("feed", "/pet/feed", {}, "'+YANGDONE+'"); }, children: "'+YANG+LP+XIAOHAO+' " + YlxwNum(t && t.consts && t.consts.feedCost) + " '+LINGSHI+RP+'" })'),
  # 2 灵田种植（伴生页 /farm）—— ASCII
  ('children: (g[x] && g[x].name) || YLXW_CROP[x] || x }',
   'children: ((g[x] && g[x].name) || YLXW_CROP[x] || x) + "'+LP+'" + YlxwNum(g[x] && g[x].seed) + " '+LINGSHI+RP+'" }'),
  # 3a 挑战禁地·确认框 —— 字面 UTF-8
  ("\u662f\u5426\u786e\u8ba4\u6311\u6218\uff1f",
   "\u662f\u5426\u786e\u8ba4\u6311\u6218\uff1f"+LP+e("9700")+XIAOHAO+" ${Hn.challengeCost.spiritStones} "+LINGSHI+RP),
  # 3b 挑战禁地·按钮 —— 字面 UTF-8 + 字面 emoji
  ("children:\"\U0001f525 \u6311\u6218\u5b97\u4e3b \U0001f525\"",
   "children:[\"\U0001f525 \u6311\u6218\u5b97\u4e3b \U0001f525\",\""+LP+XIAOHAO+' "+Hn.challengeCost.spiritStones+" '+LINGSHI+RP+'"]'),
  # 4 悬赏发布（伴生页 /bounty）—— 转义形态
  ('children: "'+FABU+'" })] })',
   'children: "'+FABU+'" }), e.jsx("span", { className: "text-xs text-stone-400 ml-2", children: T ? "'
   +e("9700")+e("51bb")+e("7ed3")+' " + YlxwNum(T) + " '+LINGSHI+e("ff0c")+e("5b8c")+e("6210")+e("65b9")+e("5b9e")+e("5f97")+' " + YlxwNum(Math.floor(T * (1 - ((t && t.consts && t.consts.feeRate) || 0.1)))) + " '
   +LINGSHI+LP+e("624b")+e("7eed")+e("8d39")+' 10%'+RP+'" : "'
   +e("9700")+e("5168")+e("989d")+e("51bb")+e("7ed3")+e("8d4f")+e("91d1")+e("ff0c")+e("5b8c")+e("6210")+e("65b9")+e("5b9e")+e("5f97")+' 90%'+LP+e("624b")+e("7eed")+e("8d39")+' 10%'+RP+'" })] })'),
]

s = io.open(SRC, encoding="utf-8").read()
for i, (old, new) in enumerate(EDITS, 1):
    got = s.count(old)
    assert got == 1, "edit%d 命中 %d（期望 1）" % (i, got)
    assert all(ord(c) < 128 for c in set(new) - set(old)), "edit%d 新增了非 ASCII" % i
out = s
for i, (old, new) in enumerate(EDITS, 1):
    out = out.replace(old, new, 1)
back = out
for old, new in EDITS:
    back = back.replace(new, old, 1)
assert back == s, "往返不等价"
io.open(DST, "w", encoding="utf-8", newline="").write(out)
print("[ok] %s  %d -> %d chars" % (DST, len(s), len(out)))
```

**收尾必做**：`node --check <产物>` 通过后再部署（本次已在本机对 5 条编辑的合成产物验证通过）。

---

## 附录 B：核对用索引

| # | 项目 | bundle offset | 行号 | 中文形态 | old 命中 |
|---|---|---|---|---|---|
| 1 | 妖灵喂养按钮（`YlxwTPet`） | 806754 | 988 | `\uXXXX` 转义 | 1 |
| 2 | 灵田种植按钮（`YlxwTFarm`） | 798715 | 951 | ASCII | 1 |
| 3a | 挑战宗主确认框 | 946620 | 1123 | 字面 UTF-8 | 1 |
| 3b | 🔥 挑战宗主 🔥 按钮 | 947453 | 1126 | 字面 UTF-8 + emoji | 1 |
| 4 | 悬赏发布按钮（`YlxwTBounty`） | 820006 | 1018 | `\uXXXX` 转义 | 1 |
| — | `Hn` 常量（挑战禁地成本） | 332002 | 641 | — | — |
| — | `YlxwNum` 工具函数 | 784941 | — | — | — |

**未纳入本次的相邻项（避免误伤）**：
- 主应用「洞府 → 种植」不消耗灵石，消耗的是背包物品（`inventory` 数量 -1，见 offset 1262086 附近），**无需补显示**。
- 灵田「开垦」按钮已显示 `unlockCost[N.slot]`，**无需补显示**。
- `/api/dungeon/*`（秘境/地宫）无灵石消耗，**不属于本需求**。
- `SECT_CREATE_COST`（建宗 50000）已在上一版补齐，**本次不动**。
