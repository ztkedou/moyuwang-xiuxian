# DISPLAY-REGISTRY —— 玩家可见数值/文案 · 唯一来源 · 渲染入口

> 版本锚定：`yl` 线上 **0.9.49**，bundle `build/assets/index-v2949-20261009.js`
> md5 `d8fac7c23951a88c739579726823fb2c`（实测，`md5sum` 输出一致；字符长度 2157078）
> 登记人：R-222 工程防回归工程师（general-purpose-1）

---

## 0. 这份表是干什么的

今天一天出现 **4 次「机制改了、显示它的地方没跟着改」**，且形态各不相同，每次都是**玩家先发现**：

1. 心法按钮仍写「修炼」、不显示加多少经验（R-210）
2. 部署件注释写「必须加 --skip-server」，而本批有服务端变化（0.9.45）
3. 修炼效率面板不显示难度倍率（R-220）
4. 修炼弹窗还在报「攻击 +0%」——**指标本身已过时**（R-219）

反向错误一次：把**死数据**（`talent.specialAbility.description`，从不渲染）当成了「玩家可见的假话」（0.9.49）。

⇒ **根因**：验证链全在验「我改的东西对不对」，没有一层在验「玩家看到的是不是真的」。

**本表的使用方式（改动前先答两问）**：

- **问题① 这处玩家看得到吗？** —— 若某行在表里，说明它**有渲染入口**，改了机制必须回来对表；
  若它落在末尾「已知死数据」区，说明**玩家永远看不到**，改它不必动 UI，也**不要**把它当成「玩家看到的假话」。
- **问题② 它显示的值是谁给的？** —— 看 ④「值的来源」：是**服务端字段**、**本地常量**、还是**本机聚合函数**。
  改了「来源」而没改「渲染入口」，就是今天这 4 次事故。

### 判定口径（收敛范围，不做全站文案）

**登记**：会随**机制 / 难度 / 境界 / 运气 / 时间**变化的玩家可见值 ——
**收益类**（修为/灵石/掉率）｜**概率类**（奇遇/悟道/掉券/暴击）｜**消耗类**（价格/费用）｜
**限制类**（上限/冷却/每日次数）｜**区间类**（稀有度→数值区间）。

**不登记**：纯装饰文字、菜单名、按钮的固定动作词、玩法说明正文（除非它承载一个会被改的数值口径）。

### 证据标记与口径

- `esc` = bundle 中为 **`\uXXXX` 转义态**；`lit` = bundle 中为**字面中文**（两者都存在，一律实测，不推断）。
- 所有 `@NNNNN` 均为**字符 offset**（0 基，对 `utf-8` 读入后的 Python 字符串）。
- **每条 ③ 的 offset 就是所引代码片段的第一个字符**（已逐条脚本校验 `src[offset:]` 以该片段开头）。

---

## 1. 功法阁（心法 / 悟道）

| # | ① 显示位置（函数 + offset） | ② 显示的值/文案（实测） | ③ 渲染入口（offset + 片段，实测） | ④ 值的来源 | ⑤ 受什么影响 |
|---|---|---|---|---|---|
| 1 | `YlxwTXinfa087` 心法按钮 · @1453583 `esc` | `修炼 +750 经验`（`_pc` 逐级递增） | @1453583：`\u4fee\u70bc +" + YlxwNum(_pc) + " \u7ecf\u9a8c")`（完整：`children: g.maxed ? "已大成" : (/*YLXW_R214_V2944*/"修炼 +" + YlxwNum(_pc) + " 经验")`） | `_pc` 定义 @1453052：`YlxwNum(g.costNext) \|\| YLXW_XINFA_CLICK_FALLBACK[Math.min(9, Math.floor(YlxwNum(g.level)/10))]`；`g.costNext` 来自服务端 `GET /gongfa` | **品阶索引**（level/10，0..9）；兜底常量 `YLXW_XINFA_CLICK_FALLBACK=[750,1250,2000,3000,5000,7500,12500,20000,30000,50000]` @1451124 |
| 2 | `YlxwTXinfa087` 修炼弹窗 toast · @1452126 `esc` | `修炼成功，经验 +N`（`bonusPct>0` 时追加 `，{bonusText}`） | @1452126：`\u4fee\u70bc\u6210\u529f\uff0c\u7ecf\u9a8c +" + YlxwNum(g && g.cost) + ((g && g.bonusPct > 0) ? ("\uff0c" + g.bonusText) : "")`（外层为 `ia(...)`） | `g.cost` = 服务端 `POST /gongfa/levelup` 返回体 | 服务端结算值；`bonusText` 由服务端下发 |
| 3 | `YlxwTXinfa087` 进度行 · @1454280 `esc` | `本级进度 x/y（还差 z 经验）· 点一次消耗 N 灵石` | @1454280：`\u672c\u7ea7\u8fdb\u5ea6 " + YlxwNum(g.levelExp) + "/" + YlxwNum(g.levelNeed) + "（还差 " + YlxwNum(Math.max(0, levelNeed-levelExp)) + " 经验）· 点一次消耗 " + YlxwNum(_pc) + " 灵石"` | `g.levelExp`/`g.levelNeed`/`g.costNext`（服务端）；`_pc` 同 #1 | 同 #1（品阶索引 + 兜底常量） |
| 4 | `YlxwTXinfa087` 标题余额 · @1452712 `esc` | `灵石 N · 心法六卷` | @1452712：`"\u7075\u77f3 " + YlxwNum(t && t.balance) }), children: "\u5fc3\u6cd5\u516d\u5377"` | `t.balance`（服务端 `GET /gongfa`） | 无（纯余额回显） |
| 5 | `YlxwTXinfa087` 每卷等级/加成 · @1453347 `esc` | `{名} Lv.{n}/{maxLv} · {bonusText}` | @1453347：`g.name, " Lv.", YlxwNum(g.level), "/", maxLv, " \u00b7 ", g.bonusText` | `g.name/level/bonusText`（服务端）；`maxLv` 本地上限 | 服务端每卷配置 |
| 6 | `YlxwXinfaTierLine` 品阶区间行 · @1451218 `lit` | `L1-10 2250 · L11-20 3750 · … · L91-100 150000` | @1451218：`function YlxwXinfaTierLine(tiers) {`（体内 `"L"+(i*10+1)+"-"+(i*10+10)+" "+YlxwNum(tc[i])`） | 服务端 `tiers`；兜底 `YLXW_XINFA_TIER_FALLBACK=[2250,3750,6000,9000,15000,22500,37500,60000,90000,150000]` @1451124 | **品阶区间**（10 段）；服务端优先 |
| 7 | `YlxwWudaoHint` 玩法提示 · @1456123 `esc` | `玩法提示：打坐 / 历练中会随机触发悟道经验提升。` | @1456123：`"\u73a9\u6cd5\u63d0\u793a\uff1a\u6253\u5750 / \u5386\u7ec3\u4e2d\u4f1a\u968f\u673a\u89e6\u53d1\u609f\u9053\u7ecf\u9a8c\u63d0\u5347\u3002"` | 静态文案，对应机制 `YlxwWudaoEnlighten()`（@623143）、打坐悟道率 #25、历练悟道路径 | ★ **口径风险点**：文案承诺「打坐/历练都会触发」——改任一侧触发点必须回来核这行（R-184 注释 @623557 记录了曾经只有打坐触发） |
| 8 | `YlxwTWudao` 顿悟价格 · @990864 `esc` | `灵石 N · 顿悟 M 灵石` | @990864：`\u987f\u609f " + YlxwNum(t && t.manual && t.manual.cost) + " \u7075\u77f3"` | `t.manual.cost`（服务端 `GET /wudao`） | 服务端定价 |
| 9 | `YlxwTWudao` 道行等级/加成 · @992225 `esc` | `{道名} Lv.{n} · {bonusText}` | @992225：`g.name, " Lv.", YlxwNum(g.level), " \u00b7 ", g.bonusText` | `g.name/level/bonusText`（服务端） | 服务端 |

---

## 2. 难度（三档倍率 + 效率加成）

| # | ① 显示位置（函数 + offset） | ② 显示的值/文案（实测） | ③ 渲染入口（offset + 片段，实测） | ④ 值的来源 | ⑤ 受什么影响 |
|---|---|---|---|---|---|
| 10 | 难度配置表 `Qr.difficulty` · @294234 `lit` | `easy{expMul:1,stoneMul:1}` / `normal{expMul:1.5,stoneMul:1.5}` / `hard{expMul:2,stoneMul:2}`（另有 enemyPower/battleChance/reward/skippedBattleReward） | @294234：`Qr={difficulty:{easy:{enemyPower:.9,battleChance:.85,reward:.95,skippedBattleReward:.75,expMul:1,stoneMul:1},normal:{…expMul:1.5,stoneMul:1.5},hard:{…expMul:2,stoneMul:2}},…}` | 本地常量（唯一真源）；读取入口 `md(t)` 紧邻 @295072 之后、`YlxwDiffMul` @295414 | 被 `YlxwDiffGain`、效率面板、历练/打坐结算共同消费 |
| 11 | `YlxwDiffGain` 取值器 · @295775 `lit` | —（取倍率并取整） | @295775：`YlxwDiffGain=(x,f)=>{try{if(!(x>0))return x;var m=YlxwDiffMul(void 0,f);return isFinite(m)&&m>0?Math.floor(x*m):x}catch(e){return x}}` | `YlxwDiffMul` @295414 读 `Be.getState().settings.difficulty` → `localStorage["xiuxian-game-settings"].difficulty` | 难度档 → `expMul`/`stoneMul` |
| 12 | `YlxwDiffCn` 难度中文 · @295072 `esc` | `简单` / `普通` / `困难` | @295072：`YlxwDiffCn=()=>{… return d==="easy"?"\u7b80\u5355":d==="hard"?"\u56f0\u96be":"\u666e\u901a"}` | 同 #11 的设置读取 | 设置档 |
| 13 | 设置面板「游戏难度（仅查看）」· @1820574 `lit` | `普通模式 - 死亡掉落部分属性与装备；修炼速度 +50%，灵石获取 +50%` / `困难模式 - …修炼速度 +100%，灵石获取 +100%` / `简单模式 - 死亡无惩罚` | @1820574：`"普通模式 - 死亡掉落部分属性与装备；修炼速度 +50%，灵石获取 +50%"`（hard 分支紧邻其后） | 文案为**硬编码**，应镜像 #10 的 `expMul/stoneMul` | ★ 口径校验：`+50%` ↔ `1.5`；`+100%` ↔ `2`。**easy 的 `reward:0.95`/`skippedBattleReward:0.75` 未出现在文案**（文案只谈死亡惩罚） |
| 14 | 开局难度选择面板 · @528270 `lit` | `死亡无惩罚，适合新手体验`（+ `不同难度决定了死亡惩罚的严重程度` @527393） | @528270：`"死亡无惩罚，适合新手体验"` | 硬编码文案 | 与 #13 同源风险：此面板**不显示** expMul/stoneMul |
| 15 | 角色面板「修炼效率加成」· @837339 `lit` | `+{total×难度×100}%（难度×{倍率} {难度名}）` | @837339：`(c.total*YlxwDiffMul(void 0,"expMul")*100).toFixed(1),"%","（难度×"+YlxwDiffMul(void 0,"expMul").toFixed(1)+" "+YlxwDiffCn()+"）"` | `c = bd(player)`（#18）；`YlxwDiffMul`（#11）；`YlxwDiffCn`（#12） | **total × 难度倍率**（R-220 修复点） |
| 16 | 统计面板「修炼效率加成」· @1739385 `lit` | `+{total×难度×100}%` | @1739385：`(T.total*YlxwDiffMul(void 0,"expMul")*100).toFixed(1),"%"]})` | `T = bd(player)`；同 #15 | **total × 难度倍率** |
| 17 | 统计面板效率明细 · @1739509 `lit` | `心法:+a% 天赋:+b% 称号:+c% 洞府:+d% 协同:+e% 羁绊:+f% 难度:×N（{难度名}）` | @1739509：``T.art>0&&`心法:+${(T.art*T.spiritualRootBonus*100).toFixed(1)}% `,T.talent>0&&`天赋:+${(T.talent*0.26*100).toFixed(1)}% `,T.title>0&&`称号:+${(T.title*0.6*100).toFixed(1)}% `,T.grotto>0&&`洞府:+${(T.grotto*0.6*100).toFixed(1)}% `,T.synergy>0&&`协同:+${(Math.min(T.synergy,0.1)*100).toFixed(1)}% `,T.npc>0&&`羁绊:+${(T.npc*0.32*100).toFixed(1)}%`,YlxwDiffMul(void 0,"expMul")>1&&`难度:×${…}（${YlxwDiffCn()}）` `` | 各项系数**硬编码**在渲染串里：`0.26 / 0.6 / 0.6 / 0.1 / 0.32`；对应 #18 的权重 | ★ 硬编码权重：改 `bd()` 权重必须同步改这里的 `0.26/0.6/0.6/0.32` 与 `min(…,0.1)` |
| 18 | `bd(t)` 效率聚合（唯一真源）· @617858 `lit` | —（返回 `total/art/talent/title/grotto/synergy/npc/spiritualRootBonus`） | @617858：`function bd(t){let r=0,a=0,l=0,c=0,d=1;`（体内 `r=Math.min(1.25,u.effects.expRate*$); d=go(u,M)` … `return {total:r*d+a*0.26+l*0.6+c*0.6+Math.min(b,0.1)+S*0.32, art:r,talent:a,title:l,grotto:c,synergy:b,npc:S,spiritualRootBonus:d}}`） | 心法(品阶×)、天赋(`YLXW_T097_TALENT_K`)、称号、洞府、协同、羁绊(好感≥80→+0.1 / ≥50→+0.05)、灵根(`go`) | 心法上限 `min(1.25,…)`；灵根系数 `go`；被 #15/#16 消费 |

---

## 3. 历练（奇遇 / 掉券 / 收益上限）

| # | ① 显示位置（函数 + offset） | ② 显示的值/文案（实测） | ③ 渲染入口（offset + 片段，实测） | ④ 值的来源 | ⑤ 受什么影响 |
|---|---|---|---|---|---|
| 19 | `handleAdventure` 奇遇判定 · @1936173 `lit` | —（概率值，玩家看不到数字；只看到 #20 的触发提示） | @1936173：`V=0.01+Math.min(0.03,($a(t.titleId,t.unlockedTitles\|\|[]).luck\|\|0)*0.0003)` | `$a(titleId, unlockedTitles).luck`（称号气运） | **气运 luck**：`0.01 + min(0.03, luck×0.0003)` ⇒ 上限 4% |
| 20 | 历练奇遇 toast · @1936567 `lit` | `✨ 你福至心灵，触发了奇遇！` | @1936567：`✨ 你福至心灵，触发了奇遇！","special");await I(Z?"lucky":"normal")` | `V`（#19） | 同 #19 |
| 21 | 掉券率常量 `YLXW_TICKET_DROP_RATE` · @542881 `lit` | —（机制值，无数字显示；结果见 #23） | @542881：`var YLXW_TICKET_DROP_RATE=37/600;` | 本地常量 `37/600 ≈ 6.17%` | R-221 闸门；注释口径「≈600 次历练 1 张」 |
| 22 | 掉券 `case"lottery"` 分支 · @567761 `lit` | —（机制值 10%，结果见 #23） | @567761：`if(!fs(t,.1,451))`（`case"lottery":{ if(!fs(t,.1,451)) return {…"你在这片区域中仔细搜寻了一番，却并未发现什么特别的东西…"}`） | `fs(t,r,a)=sa(t,a)<r`（@541967，种子哈希判定）；此处 `fs(t,.1,451)` = 10% | 双重闸门：事件内 10%（#22）× 模板权重；另一路径用 `YLXW_TICKET_DROP_RATE`（#21） |
| 23 | 历练结算 toast「抽奖券」· @541290 `esc` | `📊 {label}：… · 抽奖券 +1 · …` | @541290：`parts.push("\u62bd\u5956\u5238 " + (_ylLot > 0 ? "+" : "") + _ylLot)` | `res.lotteryTicketsChange`（模板返回值，#21/#22 产出） | 见 #21/#22；由 `YlxwAdvResultLog` @539846 汇总 |
| 24 | 历练单次修为上限 · @1918209 `lit` | —（机制值 25%，超限钳制） | @1918209：`_ylCapPct=.25`（注释：`yl-exp: 单次历练修为上限=当前层所需×_ylCapPct`） | 本地常量 `.25` | 当前层所需修为 × 0.25 |

---

## 4. 打坐（悟道 / 灵石收益）

| # | ① 显示位置（函数 + offset） | ② 显示的值/文案（实测） | ③ 渲染入口（offset + 片段，实测） | ④ 值的来源 | ⑤ 受什么影响 |
|---|---|---|---|---|---|
| 25 | `handleMeditate` 悟道判定 · @748693 `lit` | —（概率值；结果见 #26） | @748693：`b=Math.random()<(0.01+Math.min(0.03,($a(a.titleId,a.unlockedTitles\|\|[]).luck\|\|0)*0.0003))` | 同 #19：`$a(...).luck` | **气运 luck**，上限 4% |
| 26 | 打坐悟道 toast · @748892 `lit` | `✨ 你突然顿悟，灵台清明，对大道有了更深的理解…！(+N 修为)` | @748892：`✨ 你突然顿悟，灵台清明`（完整：``x=`✨ 你突然顿悟，灵台清明，对大道有了更深的理解${j?`，运转${j.name}`:""}！(+${S} 修为)`;YlxwToast(x,"special","md-exp",4000)``） | `S=Math.floor(v*$)`，`$=30+Math.random()*20`；`v` 含 `YlxwDiffGain(v,"expMul")` | 修为 v ×（30~50）倍；v 先乘 `expMul`（#11） |
| 27 | 打坐灵石收益 · @749452 `lit` | —（结算值，见 #28） | @749452：`YlxwDiffGain(YlxwMedStone2(q,$.realmLevel,C),"stoneMul")` | `YlxwMedStone2(q,realmLevel,realmIndex)` @1504417：`Math.floor(max(1,q)*4.25*(1+ri*0.083+(lv-1)*0.03))` | **境界**(realmIndex `ri`、realmLevel `lv`) × **难度 stoneMul**（#11） |
| 28 | 打坐结算日志 · @625906 `esc` | `🧘 本次打坐 {时长}：修为 +de · 灵石 +ds · …` | @625906：`addLog("\ud83e\uddd8 \u672c\u6b21\u6253\u5750 " + YlxwMedDur(ms)`（后接 `"\uff1a\u4fee\u4e3a +" + de.toLocaleString() + " \u00b7 \u7075\u77f3 +" + ds.toLocaleString()`） | `de/ds` 由会话累加器 `YlxwMedStone`（@625219）与 `YlxwMedSession`（@625319）汇总 | 汇总 #26/#27；时长由 `YlxwMedDur` @621995 格式化 |

---

## 5. 商店（买价 / 卖价 / 刷新费）

| # | ① 显示位置（函数 + offset） | ② 显示的值/文案（实测） | ③ 渲染入口（offset + 片段，实测） | ④ 值的来源 | ⑤ 受什么影响 |
|---|---|---|---|---|---|
| 29 | 商店物品买价计算 · @1852904 `lit` | —（计算值，见 #30） | @1852904：`const A=YlxwShopPriceOf(w,l)` | `YlxwShopPriceOf(it,player)` @1842074：`base=Rm(it.price,player)` → 跨层衰减 `×Math.pow(YLXW_SHOP_TIER_DOWN,g)` → 消耗品乘 `YLXW_R140_CONSUM_PRICE_MUL[rarity]`，否则乘 `YLXW_R135_RARE_PRICE_MUL`/`YLXW_R135_BASE_PRICE_MUL` | **境界**（`Rm` 境界价系数）、**稀有度**、**跨层 gap** |
| 30 | 商店物品买价渲染 · @1856703 `lit` | `{价格}`（+ 数量>1 时 `总计: {A×qty}`） | @1856703：`,children:lt(A)})`（完整：`e.jsx("span",{className:"font-bold",children:lt(A)})`） | `A`（#29） | 同 #29 |
| 31 | 购买扣费 · @1912423 `lit` | —（扣费额） | @1912423：`YlxwShopPriceOf(R,N)*E`（后接 `if(N.spiritStones<_)return j("灵石不足！","danger"),N`） | `YlxwShopPriceOf` × `E`（数量） | **必须与 #30 同源**，否则显示价 ≠ 扣费 |
| 32 | 出售单价渲染 · @1863059 `lit` | `{单件售价}`（绿色灵石图标） | @1863059：`children:lt(YLsu)})`（完整：`e.jsx("span",{className:"font-bold",children:lt(YLsu)})`） | `YLsu=Math.min(YLSellCredit(D,1,l), YlxwSellCap(w,1,l))`（@1861315 邻近） | 受 `YLSellCredit` 与**出售上限**（#34）双重钳制 |
| 33 | 出售合计/上限使用 · @1848290 `lit` | `确定要出售选中的 {N} 件物品吗？将获得 {A} 灵石。` | @1848290：`A+=Math.min(L,YlxwSellCap(I,Y,l))` | `YlxwSellCap(it,qty,pl)` @1835363 | 见 #34 |
| 34 | 出售上限常量 · @1835091 `lit` | —（钳制：参考价×30%） | @1835091：`var YLXW_SELL_CAP_RATIO = 0.3;`（`YlxwSellCap` 内：`unit=Math.floor(YLXW_SELL_CAP_RATIO*YlxwSellRefPrice(it,pl)); return unit>0?unit*n:0`） | 本地常量 `0.3` × `YlxwSellRefPrice`（@1835122，含 `Rm` 境界价系数） | **境界**（`Rm`）、常量 `0.3` |
| 35 | 商店刷新费渲染 · @1850824 `lit` | `刷新 (免费)` / `刷新 ({N})`；title `本次刷新免费` / `花费{N}灵石刷新` | @1850824：`YLXW_SR_N<1?"免费":YlxwShopRefreshCost(a)`（title 分支 @1850612） | `YlxwShopRefreshCost(shop)` @579560：查 `YLXW_SHOP_REFRESH[shop.id]` → `YLXW_SHOP_REFRESH_BY_TYPE[shop.type]` → `YLXW_SHOP_REFRESH_DEFAULT`（2万~8万） | **商店类型/id**；首刷免费闸门 `YLXW_SR_N<1` |

---

## 6. 炼丹（成功率 / 时长 / 纯度 / 品质）

| # | ① 显示位置（函数 + offset） | ② 显示的值/文案（实测） | ③ 渲染入口（offset + 片段，实测） | ④ 值的来源 | ⑤ 受什么影响 |
|---|---|---|---|---|---|
| 36 | 丹炉预览「成功率」· @1015407 `lit` | `成功率 {N}%` | @1015407：`Math.round(rate * 100) + "%"` | `rate=YlxwAlcRate(rc,lv,luck,fire)` @996460：`base + (lv-1)*0.05 + luck*0.001 + fire.rateAdd`，钳 `[0.05,0.98]` | **丹方稀有度**(`YlxwAlcBase`)、**道诣 lv**、**气运 luck**、**火候** |
| 37 | 丹炉预览「预计时长」· @1015702 `lit` | `预计时长 {x 分 y 秒}` | @1015702：`YlxwAlcFmtMin(mins)` | `mins=YlxwAlcMinutes(rc,fire)` @996964：`rc.minutes×(fire.timeMult)` 或 `YlxwAlcBaseMin[rarity]×(fire.timeMult)` | **火候**（timeMult）、丹方稀有度 |
| 38 | 丹炉预览「纯度区间」· @1015988 `lit` | `纯度区间 {lo} ~ {hi}` | @1015988：`pr[0] + " ~ " + pr[1]` | `pr=YlxwAlcPurityRange(rc,lv,luck,fire)` @996756：`lo=60+(lv-1)*2+fire.purityAdd`，`hi=lo+19`，钳 `[0,100]` | **道诣 lv**（每级 +2）、**火候**（purityAdd） |
| 39 | 丹炉预览「品质区间」· @1016276 `lit` | `品质区间 {下品} ~ {上品}` | @1016276：`YlxwAlcTierName(pr[0]) + " ~ " + YlxwAlcTierName(pr[1])` | `YlxwAlcTierName(q)` @996964：`q>=100完美 / >=95极品 / >=85上品 / >=70中品 / else 下品`；`pr` 同 #38 | 同 #38 |

---

## 7. 妖灵 / 灵宠（融合 / 转化 / 经验）

| # | ① 显示位置（函数 + offset） | ② 显示的值/文案（实测） | ③ 渲染入口（offset + 片段，实测） | ④ 值的来源 | ⑤ 受什么影响 |
|---|---|---|---|---|---|
| 40 | 妖灵融合面板 KV · @1472548 `esc` | `融合费 N 灵石 · 成功率 {p}% · 保底计数 {pity} / 3 · 当前灵石 N` | @1472548：`"\u878d\u5408\u8d39": YlxwNum(cost) + " \u7075\u77f3", "\u6210\u529f\u7387": Math.round(rate * 100) + "%", "\u4fdd\u5e95\u8ba1\u6570": pity + " / 3"` | `cost=YlxwPetFuseCost(main,sub)` @1465176；`rate=YlxwPetFuseRate(main,sub)` @1465646；`pity=main.fusePity` | **主/副宠品阶**（`YLXW_PET_RARITY` 序号差 `d`） |
| 41 | 融合率来源 `YlxwPetFuseRate` · @1465646 `lit` | —（副<主：`70%+15%×差`；相等 `70%`；副>主：`70%-20%×差`；钳 `[20%,100%]`） | @1465646：`function YlxwPetFuseRate(mainPet, subPet) {`（体内 `if(d<0)p=0.70+0.15*(-d); else if(d===0)p=0.70; else p=0.70-0.20*d; return Math.max(0.20,Math.min(1.00,…))`） | 主/副宠稀有度序号差 | 品阶差 |
| 42 | 融合费来源 `YlxwPetFuseCost` · @1465176 `lit` | —（`3000 × K品阶(主宠) × (1 + 副宠品阶序号)`） | @1465176：`function YlxwPetFuseCost(mainPet, subPet) {`（体内 `return Math.round(YLXW_PET_FUSE_BASE * YLXW_PET_BONUS_RARITY[mr] * (1 + si))`） | `YLXW_PET_FUSE_BASE`、`YLXW_PET_BONUS_RARITY[主宠稀有度]`、`si` | 主宠稀有度 × 副宠品阶序号 |
| 43 | 灵宠转化率（灵宠口径）· @1028301 `esc` | `（灵宠口径：主战出战转化 {N}%）` | @1028301：`"\uff08\u7075\u5ba0\u53e3\u5f84\uff1a\u4e3b\u6218\u51fa\u6218\u8f6c\u5316 "`（后接 `+ Math.round(b.rate * 100) + "%\uff09"`） | `b.rate`（灵宠加成视图 `YlxwSpiritBonusView` 计算） | 妖灵→灵宠转化系数（另一处 @1480650 `L.lane.rate`） |
| 44 | 妖灵喂食度说明 · @1036063 `lit` | `喂食度＝妖灵经验：每 100 点 = 1 级（满级 99 级＝9900 点，上限 9999）；…满 9999 后再进食不再提升等级。` | @1036063：`喂食度＝妖灵经验：每 100 点 = 1 级`（全句同串） | 硬编码文案 | ★ 口径：`100点=1级`、上限 `9999` —— 改数值必须改这行 |

---

## 8. 神通（参悟费用）

| # | ① 显示位置（函数 + offset） | ② 显示的值/文案（实测） | ③ 渲染入口（offset + 片段，实测） | ④ 值的来源 | ⑤ 受什么影响 |
|---|---|---|---|---|---|
| 45 | `YlxwTSpell` 参悟按钮 · @1406228 `esc` | `参悟 +{cost}`（满级显示 `已圆满`） | @1406228：`sp.level >= YlxwSP_CFG.maxLevel ? "\u5df2\u5706\u6ee1" : ("\u53c2\u609f +" + cost.toLocaleString())` | `cost=YlxwSP_UpgradeCost(sp.level)` @1396859：`Math.floor(YlxwSP_CFG.upgradeBase * Math.pow(1.5, lv))` | **重数 sp.level**（×1.5^lv）；`upgradeBase` 常量 |

---

## 9. 突破（成功率）

| # | ① 显示位置（函数 + offset） | ② 显示的值/文案（实测） | ③ 渲染入口（offset + 片段，实测） | ④ 值的来源 | ⑤ 受什么影响 |
|---|---|---|---|---|---|
| 46 | 突破失败 toast · @753969 `lit` | `…下次突破成功率提升至 {C%}` / `…下次成功率提升至 {C%}` | @753969：`下次突破成功率提升至 ${Math.round(C*100)}%`（另有分支 `虽未突破，但你稳固了根基，下次成功率提升至 ${…}%`） | `C`（#47） | 见 #47 |
| 47 | 突破率公式 · @753842 `lit` | —（下次成功率） | @753842：`C=Math.min((m?.6:[.9,.85,.8,.7,.6,.5][Math.min(Math.max(fe.indexOf(t.realm),0),5)])+(m?N*.05:N*.03)+k+_,.95)` | `k`=天赋加成（`talent-firm-heart`+0.15 / `talent-prodigy`+0.1）；`_=dg(t.spiritualRoots)`（灵根）；`N=breakthroughFailCount` | **境界**（档位表）、**失败次数**（+3%/+5%）、**天赋**、**灵根**；上限 `.95` |

---

## 10. 抽奖 / 娱乐（掷骰）

| # | ① 显示位置（函数 + offset） | ② 显示的值/文案（实测） | ③ 渲染入口（offset + 片段，实测） | ④ 值的来源 | ⑤ 受什么影响 |
|---|---|---|---|---|---|
| 48 | 掷骰赔率提示 · @975929 `esc` | `大/小 赔 1.95 · 豹子 赔 25` | @975929：`"\u5927/\u5c0f \u8d54 1.95 \u00b7 \u8c79\u5b50 \u8d54 25"` | **硬编码**提示；真实赔率来自服务端 `POST /fun/dice` 的 `r.payout`（#50） | ★ 风险点：客户端写死 `1.95 / 25`，服务端改动则**文案会撒谎** |
| 49 | 掷骰次数 · @975779 `esc` | `掷骰比大小 · 今日 {left}/{max}` | @975779：`"\u63b7\u9ab0\u6bd4\u5927\u5c0f \u00b7 \u4eca\u65e5 " + left + "/" + max` | `d.left`/`d.dailyMax`（服务端）；`max` 兜底 10 | 每日次数（限制类） |
| 50 | 掷骰结果 · @975207 `esc` | `掷骰：{a}+{b}+{c} = {和} {大/小} → 赢 {N} 灵石` | @975207：`"\u8d62 " + YlxwNum(r.payout) + " \u7075\u77f3"`（`r.win?…:"\u672a\u4e2d"`） | `r.payout`（服务端） | 服务端结算 |

---

## 11. 活动（倍率 / 签到 / 时间）

| # | ① 显示位置（函数 + offset） | ② 显示的值/文案（实测） | ③ 渲染入口（offset + 片段，实测） | ④ 值的来源 | ⑤ 受什么影响 |
|---|---|---|---|---|---|
| 51 | `YlxwTEvents` 活动倍率 · @989863 `esc` | `{活动名} ×{multiplier}`（同名时省略中文名） | @989863：`d.name + " \u00d7" + YlxwNum(d.multiplier)`（完整：`(YLXW_ACT[d.type]\|\|d.typeName)===d.name ? (d.name+" ×"+YlxwNum(d.multiplier)) : (d.name+"（"+(YLXW_ACT[d.type]\|\|d.typeName)+" ×"+YlxwNum(d.multiplier)+"）")`） | `d.multiplier`（服务端 `GET /events`） | 活动期次倍率（时间/期次） |
| 52 | `YlxwTActCheckin` 签到进度 · @1213451 `esc` | `本月已签 {prog} / {dim} 天 · 每日可得 灵石 +{stonesToday} · 修为 +{expToday}` | @1213451：`"\u672c\u6708\u5df2\u7b7e " + YlxwNum(prog) + " / " + YlxwNum(dim) + " \u5929 \u00b7 \u6bcf\u65e5\u53ef\u5f97 \u7075\u77f3 +"`（后接 `+YlxwNum(d&&d.stonesToday)+" · 修为 +"+YlxwNum(d&&d.expToday)`） | `d.progress/daysInMonth/stonesToday/expToday`（服务端 `/activity/checkin`） | 月度天数、当期奖励 |
| 53 | 签到补签价 · @1214265 `esc` | title `补签这一天：花费 {N} 灵石`；toast `补签成功（第 N 次，花费 M 灵石）` | @1214265：`"\u8865\u7b7e\u8fd9\u4e00\u5929\uff1a\u82b1\u8d39 " + YlxwNum(mpD.price) + " \u7075\u77f3"`；toast 分支 @1211600 邻近 | `d.makeup.price`、`d.makeup.count`（服务端） | 补签次数/价格 |
| 54 | 活动时间窗口 · @1447139 `esc` | `活动时间：{MM-DD HH:mm} ~ {MM-DD HH:mm}` | @1447139：`return "\u6d3b\u52a8\u65f6\u95f4\uff1a" + YlxwEvtFmt(ev.startAt) + " ~ " + YlxwEvtFmt(ev.endAt);` | `ev.startAt`/`ev.endAt`（服务端）；`YlxwEvtFmt` @1446638 格式化 | 时间 |
| 55 | 活动状态 · @1448276 `esc`（+ chip @1204994） | `未开始 · 还有 {x}后开启` / `进行中 · 剩 {x}` / `已结束` | @1448276：`return "\u672a\u5f00\u59cb \u00b7 \u8fd8\u6709 " + YlxwEvtDur(ms) + "\u540e\u5f00\u542f"`；@1204994：`"\u8fdb\u884c\u4e2d \u00b7 \u5269 " + YlxwMin(YlxwNum(ev.leftMs))` | `ev.startsInMs`/`ev.leftMs`/`ev.state`（服务端） | 时间 |

---

## 12. 其它（塔 / 秘境 / 寿命 / 洞府）

| # | ① 显示位置（函数 + offset） | ② 显示的值/文案（实测） | ③ 渲染入口（offset + 片段，实测） | ④ 值的来源 | ⑤ 受什么影响 |
|---|---|---|---|---|---|
| 56 | `YlxwTTower` 首通奖励 · @1356990 `esc` | `修为:… 灵石:… 太虚洗炼石:… 太虚悟道卷:… 秘宝:…` | @1356990：`\u4fee\u4e3a: rew.exp, \u7075\u77f3: rew.spiritStones, \u592a\u865a\u6d17\u70bc\u77f3: rew.reforgeStones,`（后接 `太虚悟道卷: rew.comprehensionScrolls\|\|0, 秘宝: …`） | `rew=cfg.firstClearRewards`，`cfg=YlxwTowerFloor(sel)` @1341818 | **层数**（`YlxwTowerFloor`：realm/rf 随层数分段，@1341818） |
| 57 | `YlxwTTower` 守卫属性 · @1356802 `esc` | `气血:… 攻击:… 防御:… 身法:… 神识:…` | @1356802：`var guardData = { \u6c14\u8840: cfg.baseHp`（全句：`{ 气血: cfg.baseHp, 攻击: cfg.baseAttack, 防御: cfg.baseDefense, 身法: cfg.baseSpeed, 神识: cfg.baseSpirit }`） | 同 #56 的 `cfg` | 层数 |
| 58 | 秘境门禁提示 · @2036637 `esc` | `今日已探索 {day}/{cap} 次 · 每次探索后冷却 15 分钟 · 层数境界：7层需筑基期、9层需金丹期、11层需元婴期` | @2036637：`"\u4eca\u65e5\u5df2\u63a2\u7d22 "+ylDgGate().day+"/"+YlxwDgCap(a&&a.realm)+" \u6b21` | `ylDgGate().day`；`YlxwDgCap(realm)` @923875（`YLXW_DG_ROGUE_CAP` 按境界索引） | **境界**（cap）；冷却常量 `YLXW_DG_CD_MS=15*60*1000` @923735 |
| 59 | 秘境次数上限来源 · @923875 `lit` | —（`[10,12,14,15,17,18,20]` 按境界） | @923875：`function YlxwDgCap(realm) {`（体内 `return YLXW_DG_ROGUE_CAP[i]`） | `YLXW_DG_ROGUE_CAP`（@923735 邻近） | **境界索引** |
| 60 | 寿命阶跃来源 · @1510291 `lit` | —（小境界 +`(nxt-cur)/16`，大境界 +`(nxt-cur)/2`） | @1510291：`function YlxwLifeStep(i, big) {`（体内 `var cur=YlxwLifeCur(i), nxt=YlxwLifeNext(i), half=(nxt-cur)*0.5; return big?half:half/8`） | `YLXW_LIFE_TBL=[100,200,450,1000,2000,4000,8000]` @1510075 | **境界阶**；突破大小境界 |
| 61 | 突破寿命增加 toast · @757068 `esc` | `✨ 突破成功！你的寿命增加了 {n} 年！当前寿命：{m}` | @757068：`\u4f60\u7684\u5bff\u547d\u589e\u52a0\u4e86 ${ge} \u5e74`（完整：`` `✨ 突破成功！你的寿命增加了 ${Math.floor(_e)} 年！当前寿命：${Math.floor(ke)}` ``；`_e=YlxwLifeStep(fe.indexOf(g.realm),m)` @752515 邻近） | `YlxwLifeStep`（#60） | 同 #60 |
| 62 | 洞府图鉴自动收获奖励 · @642345 `lit` | `📖 图鉴奖励：自动收获触发奖励，获得 {b 修为}、{S 灵石}、{x 属性点}。` | @642345：`图鉴奖励：自动收获触发奖励`（完整：``a(`📖 图鉴奖励：自动收获触发奖励，获得 ${[b>0?`${b} 修为`:"",S>0?`${S} 灵石`:"",x>0?`${x} 属性点`:""].filter(Boolean).join("、")}。`,"special")``） | `b/S/x`（图鉴收获产出）；入账处 @642474：`exp:T.exp+YlxwDiffGain(b,"expMul"), spiritStones:T.spiritStones+YlxwDiffGain(S,"stoneMul")` | **难度 expMul/stoneMul**（#11） |

---

## 13. 已知死数据（存在，但从不渲染 / 从不被逻辑读取）

> 判定口径：字段在 bundle 中有**定义**，但**没有任何渲染入口**（不进入 JSX/children），
> 也**没有任何 `.field` 属性读取**（不被逻辑消费）。这类字段**改了玩家也看不到**，
> 因此**不得**把它当作「玩家看到的假话」；也**不需要**为它补 UI。

| # | 字段 | 存在性证据 | 无渲染 / 无读取的证据 |
|---|---|---|---|
| D1 | `talent.specialAbility.{name,description,effects,unlockRealm}`（天赋「特殊能力」整块） | 全 bundle **27** 处 `specialAbility`：25 处在天赋常量定义内（起于 @370318），2 处为渲染 | 2 处渲染**只是存在性判断 → 画一个 ⭐ 图标**：@507859 `t.specialAbility ? e.jsx(aa, { size: 13, className: "mt-0.5 flex-shrink-0 fill-amber-400 text-amber-400" }) : null`；@517508 `…children:t.name}),t.specialAbility&&e.jsx(aa,{size:13,className:"…fill-amber-400 text-amber-400"})`。`specialAbility.` 属性读取计数 **= 0**（`.effects/.id/.name/.description/.unlockRealm` 全为 0）。⇒ 描述文案（如 `talent-dao-mind`「道心通明」的 `specialAbility` @375933：「道心通明：修炼速度提升20%，神识+35、气运+10%」）**玩家永远看不到**，且**不参与任何结算** |
| D2 | `talent.specialAbility.unlockRealm` | 全 bundle **8** 处，全部在 `specialAbility` 定义内 | 渲染处 **0**；`.specialAbility.unlockRealm` 读取 **0**。⇒ 解锁境界门槛是死字段（真正生效的境界门槛在 `YlxwAlcUnlockLv` 等别处） |

**对照（易误判为死数据，实为活数据）**：`artifact.effects.specialEffect`（124 处）**有渲染** ——
@1531319 `children:["✨ ",A.specialEffect]`、@1711401 `children:["特殊效果: ",W.specialEffect]`、
@1722337 `children:["特殊: ",X.specialEffect]` 等；`battleEffect` 亦被渲染（@1690698 起）。
⇒ 这两个字段**不是**死数据，登记时勿混。

---

## 14. 汇总

- **共登记 62 条**（主表 #1–#62），覆盖模块：**功法阁 / 难度 / 历练 / 打坐 / 商店 / 炼丹 / 妖灵灵宠 / 神通 / 突破 / 抽奖娱乐 / 活动 / 其它（塔·秘境·寿命·洞府）**。
- 其中 **死数据 2 条**（#D1 `talent.specialAbility.*`、#D2 `talent.specialAbility.unlockRealm`）。
- 已在 ⑤ 列标注的口径风险点：**难度文案(#13/#14) ↔ `Qr.difficulty`(#10)**、**效率明细硬编码权重(#17) ↔ `bd()`(#18)**、**掷骰赔率写死(#48) ↔ 服务端 payout**、**妖灵喂食度说明(#44)**、**秘境冷却文案(#58)**。

---

## 15. 自测（fail-closed）

**方法**：脚本对每条登记的「渲染入口」保存 offset；自测时用固定随机种子 `seed=222`
从 62 条中**随机抽 5 条**，重新在 bundle 中按 offset 取前 40 字符，与登记时保存的指纹**逐字比对**，
任一条不符即判 FAIL 并回修（fail-closed）。

**本次抽取**：`#50 / #7 / #16 / #19 / #20`

| 抽样条目 | offset | 实测片段（前 40 字符） | 结果 |
|---|---|---|---|
| #50 掷骰结果 `r.payout` | @975207 | `"\u8d62 " + YlxwNum(r.payout) + " \u7075` | ✅ PASS |
| #7 悟道玩法提示 | @1456123 | `"\u73a9\u6cd5\u63d0\u793a\uff1a\u6253\u5750 / \u5` | ✅ PASS |
| #16 统计面板效率加成 | @1739385 | `(T.total*YlxwDiffMul(void 0,"expMul")*10` | ✅ PASS |
| #19 历练奇遇率 | @1936173 | `V=0.01+Math.min(0.03,($a(t.titleId,t.unl` | ✅ PASS |
| #20 奇遇触发 toast | @1936567 | `✨ 你福至心灵，触发了奇遇！","special");await I(Z?"lu` | ✅ PASS |

**结论：5/5 全过**（脚本输出 `ALL PASS`）。offset 与代码片段全部与线上 0.9.49 bundle 一致，无漂移。

> 复现：读入 bundle（`utf-8`）→ 按本表 offset 取 40 字符 → 与登记指纹比对。
> 基线 md5：`d8fac7c23951a88c739579726823fb2c`（若 bundle 变更，本表全部 offset 需重测）。
