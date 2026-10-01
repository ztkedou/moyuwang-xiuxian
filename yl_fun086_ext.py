# -*- coding: utf-8 -*-
r"""
yl_fun086_ext.py — 0.8.6 批次 · 玩法与面板七项改造（lead 独占）

=========================================================================== 用户原话（2026-09-28）
    「1.洞府"加速"灵草的按钮没有需要多少费用的提示。
      2.日常任务获取的灵石有点偏少。
      3.重构一下每日行乐这个功能，现在的内容太简单了。
      4.奇遇抽奖获取的内容也非常单一，数值都是固定值。
      5.妖灵系日志太长了，折叠或者只显示几条。灵宠秘境改为2W灵石消耗。
      6.所有仙务系统的功能跟现有的融合是排序现在是上下关系，能不能改为左右两列
        并排展示，电脑端页面的宽度其实很够用，这个上下展示怎样都会有不好翻的地方。」

    二次澄清（AskUserQuestion，2026-09-28）：
      · 「灵宠秘境」= **灵兽远征派遣消耗**（全库无「灵宠秘境」字面，用户已确认）
      · 「日常任务」= **游戏原生「日常任务」面板**（顶栏蓝角标按钮），
         **不是**仙务枢纽里的「仙途任务 / 活跃宝箱」
      · 「每日行乐」= 茶馆保留但**数值加大 + 加变数**，再**新增三件套 + 新策划内容**

=========================================================================== 本模块覆盖（客户端 8 处）

  F1 洞府「加速」按钮补费用          @1361456  字面 UTF-8
  F2 原生日常任务灵石 ×5            @455925  字面 UTF-8（hg 奖励公式）
  F3 每日行乐 · 四玩法重写           @840991  转义形态（core_block 注入区）
  F4 奇遇抽奖 · 区间与多样化展示      @836914  转义形态
  F5a 妖灵日志折叠                   @849226  转义形态
  F5b 灵兽远征派遣 20000 灵石         @957688  转义形态（YlxwExpStart + 按钮）
  F6 融合页改左右两列                 @252922  字面形态（modal 外壳 wN：内容区 + 尺寸模板）
       ★ 靶点是 YlxwFuse 融合块，不是 YlxwHub（后者已死代码，见下方决策）
  F7 丹房/炼器坊融合页右侧加宽        @1189577 字面形态（丹房本体 L4：props + 根 div + 三处 className）
       ★ 0.8.8 item18「炼丹炼器右侧 UI 被挤压」；F6 的 1:1 等分网格把丹房本体压到 543px

=========================================================================== 为什么 F1 的锚点是「字面 UTF-8」
bundle 里中文两种形态混用：
  · 基座（vite 产物）自带的字符串 = **字面 UTF-8**（F1 加速按钮、F2 日常任务公式、F6 modal 外壳）
  · 由 build_v26n.py 注入的块（core/exp/tower/…）= `\uXXXX` **转义形态**（F3~F5）
抄写时不要互相转换，否则锚点必然落空 —— 这条教训来自 `UI消耗显示补齐方案.md`。

=========================================================================== 关键设计决策

【F2 灵石 ×5，为什么只动灵石不动修为】
原生日常任务奖励公式 `hg()` 里，灵石档位是 `v*10 ~ v*50`，而 `v = target × 类型倍率
× 品阶倍率 × 境界放大`。实测炼气期「晨光吐纳(普通, target 3~6)」只给 ~113 灵石，
金丹期同款 ~600 灵石 —— 每天 10~20 个任务加起来仍远低于一次秘境收益，确属「偏少」。
用户只提灵石，所以**只乘灵石**（`vs = v*5`），修为档位 `v*20 ~ v*100` 一行未动。
★ 注意（0.8.8 更正）：原注写「`hg()` 的输出同时用于**面板展示**与**领奖结算**，所以在
  `hg()` 里乘 = 展示与到账同步放大，不会脱节」——**这条是错的**。实测：
  · 面板展示 = `reward.spiritStones` 原值（本模块 ×5 后的值）；
  · 领奖结算 = `claimQuestReward` **另起一套**境界换算
    `floor(reward.spiritStones/(1+idx*0.5)*YLRF(realm)*2.13)`。
  ⇒ 两端比值 = `YLRF·2.13/(1+0.5·idx)`：炼气 2.84× / 筑基 4.26× / **金丹 5.33×** / 元婴 5.96× /
    化神 6.39× / 合道 6.69× / **长生 6.92×**（实测 ylt_max 六条 6.9222~6.9225 与
    `13*2.13/(1+3)=6.9225` 四位小数吻合）。即玩家看到 132 灵石、实际到账 913 灵石。
  ⇒ 0.8.8 item8 用户拍板「**以实发为准，改显示端**」，落点见本文件 **F7**：
    显示端改走**与发放端逐字符同序**的同一条公式，两端天然一致，**发放逻辑与数值一行未动**。

【F3 每日行乐为什么必须改服务端】
茶馆的期望值：中奖概率 50%（胜负由日期哈希 `h2 % 2` 决定），赔率 1.9 ⇒ EV = 0.95，
庄家抽水 5%。**任何把赔率抬到 ≥2.0 的「加大」都会变成无限刷灵石漏洞**。
所以本批的「加大」落在**注额区间**（100~10,000 → 500~50,000）与**每日可押次数**
（1 注 → 3 注），赔率**保持 1.9 不动**；「变数」落在**非货币**产出上：
  · 茶运（每日由日期哈希定 0/1/2 档）→ 中奖额外送**修为**（不进灵石经济）
  · 彩头（茶运档 × 8% 概率）→ 中奖额外送 1 张**抽奖券**
新增三玩法同样守住 EV ≤ 1：
  · 掷骰比大小：大/小 1.95（EV 0.975），豹子 25（概率 6/216=2.78%，EV 0.694）
  · 灵石翻牌：3 张牌 4500/1200/0，成本 2000 ⇒ EV = 1900/2000 = 0.95
  · 每日一签：免费，每日 1 次，纯产出（有次数上限，不构成无限 faucet）

【F3/F4 的业务拒绝码为什么用 400/409 而不是 403】
`Xc()`（bundle @594262）把 401/403 一律当**会话失效**处理并**强制登出玩家**。
所以新增端点的「灵石不足 / 今日次数已用尽」一律 409，与既有 `/teahouse/bet`
`/adventure/draw` 同款 —— `YlxwUseAct` 会把 `error` 文案弹成 toast，玩家不掉线。

【F5a 妖灵日志折叠的实现约束】
`YlxwTPet` 是函数组件，React Hook 必须在**任何 return 之前**无条件调用，
所以 `O.useState(!1)` 挂在函数体第一行（与既有 `YlxwUseList/YlxwUseAct` 同序稳定）。

【F6 为什么靶点是 YlxwFuse 而不是 YlxwHub】
用户二次澄清：「分列这个是指**融合**的功能，比如说功法阁，仙务心法放左边，自带功法功能
放右边，实现的目标就是可以打开"功法阁"就能看到所有功能，而不是需要拖到最下面才能看到
所有功能」。
  · `YlxwFuse` = 0.8.3 flow083 置顶进 modal 内容区的「仙务块」（9 个融合页各带一个）。
  · `YlxwHub` = 0.8.x 已被顶栏替代的仙务枢纽，全文件**只出现 1 次**（定义处），
    从未被任何 modal 渲染 = 死代码。改它的页签栏 = 白改（本批用 Playwright 实测确认）。
落点唯一：modal 外壳 `wN` 的内容区 `children:[__xw?e.jsx(YlxwFuse,{k:__xw}):null,l]`
（count=1，实测）。`__xw` 由 9 个页传入 `xw` 键：gongfa / alchemy / sect / dungeon /
["titles","stats"] / ach / pet / farm / rebirth。
改法两条：
  ① 内容区：`__xw` 真 → `[仙务块, 页本体]` 包成 `grid grid-cols-1 md:grid-cols-2`；
     `__xw` 假 → **原样直传 `l`**，非融合页 modal 行为逐字节不变（这是安全底线）。
     两列都加 `min-w-0`：grid item 默认 `min-width:auto`，不加会被内容撑破轨道。
  ② 外壳尺寸：融合页强制 `md:max-w-6xl`。gongfa 原 `size:"3xl"` 仅 768px，塞两列必挤。
     ★ 不能简单并列两个类：编译后 CSS 里 `md:max-w-6xl`@148142 **晚于**
       `md:max-w-3xl`@148050（同特异性 → 后者胜），若两者同时出现，`size:"3xl"` 的
       `md:max-w-3xl` 会赢。所以用三元互斥，只输出一个。
     ★ 实测本 CSS **没有** `md:grid` / `md:items-start` / `md:gap-5` / `md:sticky`，
       故网格用无前缀 `grid`（单列隐式列 ⇒ 移动端天然堆叠，维持 flow083 的置顶观感）
       + 已存在的 `md:grid-cols-2` / `gap-4` / `items-start`。
     ★ **不用 sticky**：左列 23 个仙务页签高于视口，`sticky top-0` 会让它下半截永远够不到。

=========================================================================== 技术约束遵守
· 注入块经 zh() 后无非 ASCII；不含 V28_BAN_PATTERNS。
· 每个 replace 带 expect 精确次数；apply() 返回门禁五元组列表。
· 只新建本文件 + 报告，不写回 build/assets/（产物由 build_v26n.py 统一落盘）。
"""

# --------------------------------------------------------------------------- 注入块（纯 ASCII，中文由 build 侧 zh() 转义）

INJECT_JS = r'''
/* ===== yl-0.8.6: 每日行乐 · 四玩法（茶馆竞猜 / 掷骰比大小 / 每日一签 / 灵石翻牌） =====
   服务端权威：POST /fun/dice | /fun/sign | /fun/card，状态随 /teahouse/today 的 fun 字段下发。
   业务拒绝走 409（不是 403）—— Xc() 会把 403 当会话失效强制登出玩家。 */
var YLXW_FUN_MIN_BET = 1000, YLXW_FUN_MAX_BET = 20000;

function YlxwFunBetBar(props) {
  var v = YlxwNum(props.value) || YLXW_FUN_MIN_BET;
  var opt = props.options || [1000, 5000, 10000, 20000];
  var set = props.onChange || function () {};
  return e.jsxs("div", { className: "flex items-center gap-1.5 flex-wrap", children: [
    e.jsx("span", { className: "text-[11px] text-stone-500", children: props.label || "注额" }),
    opt.map(function (n) {
      return e.jsx("button", { onClick: function () { set(YlxwNum(n)); }, className: "px-2 py-1 rounded border text-[11px] " + (v === YlxwNum(n) ? "bg-amber-600/90 border-amber-400 text-stone-900 font-bold" : "bg-ink-800 border-stone-600 text-stone-300 hover:bg-stone-700"), children: YlxwNum(n) }, "b" + n);
    }),
    e.jsx("span", { className: "text-[11px] text-amber-300 font-bold", children: v + " 灵石" }),
    e.jsx("span", { className: "text-[11px] text-stone-500", children: "（区间 " + YLXW_FUN_MIN_BET + " ~ " + YLXW_FUN_MAX_BET + "）" })
  ] });
}

function YlxwFunDice(props) {
  var d = (props.data && props.data.dice) || {};
  var st = O.useState(5000), bet = st[0], setBet = st[1];
  var pk = O.useState("big"), pick = pk[0], setPick = pk[1];
  var rs = O.useState(null), res = rs[0], setRes = rs[1];
  var bs = O.useState(!1), busy = bs[0], setBusy = bs[1];
  var left = YlxwNum(d.left), max = YlxwNum(d.dailyMax) || 3;
  function roll() {
    if (busy || left <= 0) return;
    setBusy(!0), setRes(null);
    YlxwPost("/fun/dice", { bet: YlxwNum(bet), pick: pick }).then(function (r) {
      setBusy(!1), setRes(r);
      ia("掷骰：" + (r.dice || []).join("+") + " = " + YlxwNum(r.sum) + " · " + (r.kindName || "") + " → " + (r.win ? ("赢 " + YlxwNum(r.payout) + " 灵石") : "未中"));
      if (props.reload) props.reload(); YlxwDirty();
    }, function (er) { setBusy(!1), Je((er && er.message) || "掷骰失败"); });
  }
  var kinds = [["big", "大（11-18）"], ["small", "小（3-10）"], ["triple", "豹子（三同）"]];
  return e.jsxs(YlxwRow, { children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap mb-1.5", children: [
      e.jsx("span", { className: "text-xs text-stone-400", children: "掷骰比大小 · 今日 " + left + "/" + max }),
      e.jsx("span", { className: "text-[11px] text-stone-500", children: "大/小 赔 1.95 · 豹子 赔 25" })
    ] }),
    e.jsx("div", { className: "flex gap-1.5 flex-wrap mb-1.5", children: kinds.map(function (k) {
      return e.jsx("button", { onClick: function () { setPick(k[0]); }, className: "px-2.5 py-1.5 rounded border text-xs " + (pick === k[0] ? "bg-amber-600/90 border-amber-400 text-stone-900 font-bold" : "bg-ink-800 border-stone-600 text-stone-300 hover:bg-stone-700"), children: k[1] }, "k" + k[0]);
    }) }),
    e.jsx(YlxwFunBetBar, { label: "注额", value: bet, onChange: setBet }),
    e.jsxs("div", { className: "flex items-center gap-2 mt-1.5", children: [
      e.jsx(YlxwBtn, { disabled: busy || left <= 0, onClick: roll, children: busy ? "掷骰中…" : (left <= 0 ? "今日已掷完" : "掷一次") }),
      e.jsx("span", { className: "text-[11px] text-stone-500", children: "每次固定押 " + YlxwNum(bet) + " 灵石（此处按钮即注额，点上方档位切换）" })
    ] }),
    res && e.jsxs("div", { className: "mt-2 text-xs " + (res.win ? "text-green-400" : "text-stone-400"), children: [
      "骰面 " + (res.dice || []).join(" + ") + " = " + YlxwNum(res.sum) + "（" + (res.kindName || "") + "）· ",
      res.win ? ("命中，得 " + YlxwNum(res.payout) + " 灵石") : "未命中"
    ] }),
    ((d.history || []).slice(0, 5)).map(function (h, i) {
      return e.jsx("div", { className: "text-[11px] text-stone-500 mt-0.5", children: "#" + YlxwNum(h.count) + " 押" + (h.pickName || "") + " " + YlxwNum(h.bet) + " → " + (h.win ? ("赢 " + YlxwNum(h.payout)) : "输") }, "dh" + i);
    })
  ] });
}

function YlxwFunSign(props) {
  var d = (props.data && props.data.sign) || {};
  var left = YlxwNum(d.left), max = YlxwNum(d.dailyMax) || 1;
  var bs = O.useState(!1), busy = bs[0], setBusy = bs[1];
  var rs = O.useState(null), res = rs[0], setRes = rs[1];
  function draw() {
    if (busy || left <= 0) return;
    setBusy(!0), setRes(null);
    YlxwPost("/fun/sign", {}).then(function (r) {
      setBusy(!1), setRes(r);
      ia("签：" + (r.tierName || "") + " · " + (r.text || ""));
      if (props.reload) props.reload(); YlxwDirty();
    }, function (er) { setBusy(!1), Je((er && er.message) || "求签失败"); });
  }
  var today = d.today;
  return e.jsxs(YlxwRow, { children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap mb-1.5", children: [
      e.jsx("span", { className: "text-xs text-stone-400", children: "每日一签 · 今日 " + left + "/" + max }),
      e.jsx(YlxwBtn, { disabled: busy || left <= 0, onClick: draw, children: busy ? "求签中…" : (left <= 0 ? "明日再来" : "求一签") })
    ] }),
    today ? e.jsxs("div", { className: "text-xs text-amber-300", children: [
      "今日已得：", e.jsx("span", { className: "font-bold", children: today.tierName }),
      " · ", today.text,
      " （修为+", YlxwNum(today.exp), " 灵石+", YlxwNum(today.stones), (YlxwNum(today.tickets) > 0 ? (" 抽奖券+" + YlxwNum(today.tickets)) : ""), "）"
    ] }) : e.jsx("div", { className: "text-[11px] text-stone-500", children: "每日免费一签，签文分上上 / 上 / 中 / 下四档，上上签有几率附赠抽奖券。" }),
    res && e.jsxs("div", { className: "mt-1.5 text-xs text-green-400", children: [
      "【", e.jsx("span", { className: "font-bold", children: res.tierName }), "】", res.text,
      " · 修为+", YlxwNum(res.exp), " 灵石+", YlxwNum(res.stones), (YlxwNum(res.tickets) > 0 ? (" 抽奖券+" + YlxwNum(res.tickets)) : "")
    ] })
  ] });
}

function YlxwFunCard(props) {
  var d = (props.data && props.data.card) || {};
  var left = YlxwNum(d.left), max = YlxwNum(d.dailyMax) || 2, cost = YlxwNum(d.cost) || 2000;
  var bs = O.useState(!1), busy = bs[0], setBusy = bs[1];
  var rs = O.useState(null), res = rs[0], setRes = rs[1];
  function open(i) {
    if (busy || left <= 0) return;
    setBusy(!0), setRes(null);
    YlxwPost("/fun/card", { pick: i }).then(function (r) {
      setBusy(!1), setRes(r);
      ia("翻牌：" + (YlxwNum(r.payout) > 0 ? ("开出 " + YlxwNum(r.payout) + " 灵石") : "空牌，下次好运"));
      if (props.reload) props.reload(); YlxwDirty();
    }, function (er) { setBusy(!1), Je((er && er.message) || "翻牌失败"); });
  }
  var pays = d.pays || [4500, 1200, 0];
  return e.jsxs(YlxwRow, { children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap mb-1.5", children: [
      e.jsx("span", { className: "text-xs text-stone-400", children: "灵石翻牌 · 今日 " + left + "/" + max }),
      e.jsx("span", { className: "text-[11px] text-stone-500", children: "每次 " + cost + " 灵石 · 三张牌 " + pays.map(function (x) { return YlxwNum(x); }).join(" / ") })
    ] }),
    e.jsx("div", { className: "flex gap-2", children: [0, 1, 2].map(function (i) {
      return e.jsx(YlxwBtn, { tone: "ghost", disabled: busy || left <= 0, onClick: function () { open(i); }, children: "牌 " + (i + 1) }, "c" + i);
    }) }),
    res && e.jsxs("div", { className: "mt-1.5 text-xs " + (YlxwNum(res.payout) > 0 ? "text-green-400" : "text-stone-400"), children: [
      "翻开 " + (YlxwNum(res.pick) + 1) + " 号牌 → ", YlxwNum(res.payout) > 0 ? ("得 " + YlxwNum(res.payout) + " 灵石") : "空牌"
    ] })
  ] });
}
/* ===== end yl-0.8.6 每日行乐组件 ===== */
'''

# --------------------------------------------------------------------------- F1 洞府加速按钮

F1_ANCHOR = 'title:"使用灵石加速生长",children:[e.jsx(rm,{size:14}),"加速"]'
F1_REPL = ('title:"使用灵石加速生长",children:[e.jsx(rm,{size:14}),"加速 ",'
           'Math.max(Br.minCost,Math.ceil(I/6e4)*Br.costPerMinute).toLocaleString()," 灵石"]')

# --------------------------------------------------------------------------- F2 原生日常任务灵石 ×5

F2_ANCHOR = 'hg=(t,r,a,l,c)=>{const d=q3[t],u=Ba[a],f=l&&c?A3(l,c):1,v=r*d.rewardMultiplier*u*f;switch(t){'
F2_REPL = ('hg=(t,r,a,l,c)=>{const d=q3[t],u=Ba[a],f=l&&c?A3(l,c):1,v=r*d.rewardMultiplier*u*f,'
           'vs=v*5;switch(t){')
# switch 块整体替换：把 spiritStones 的 v*N 换成 vs*N（exp 档位一行不动）
F2S_ANCHOR = (
    'case"meditate":return{exp:Math.floor(v*20),spiritStones:Math.floor(v*10)};'
    'case"adventure":return{exp:Math.floor(v*30),spiritStones:Math.floor(v*15),lotteryTickets:a==="仙品"?1:0};'
    'case"breakthrough":return{exp:Math.floor(v*100),spiritStones:Math.floor(v*50),lotteryTickets:a==="传说"||a==="仙品"?1:0};'
    'case"alchemy":return{exp:Math.floor(v*25),spiritStones:Math.floor(v*20)};'
    'case"equip":return{exp:Math.floor(v*15),spiritStones:Math.floor(v*30)};'
    'case"pet":return{exp:Math.floor(v*20),spiritStones:Math.floor(v*15)};'
    'case"sect":return{exp:Math.floor(v*40),spiritStones:Math.floor(v*25),lotteryTickets:a==="仙品"?1:0};'
    'case"realm":return{exp:Math.floor(v*50),spiritStones:Math.floor(v*40),lotteryTickets:a==="传说"||a==="仙品"?1:0};'
    'default:return{exp:Math.floor(v*20),spiritStones:Math.floor(v*10)}}'
)
F2S_REPL = (
    'case"meditate":return{exp:Math.floor(v*20),spiritStones:Math.floor(vs*10)};'
    'case"adventure":return{exp:Math.floor(v*30),spiritStones:Math.floor(vs*15),lotteryTickets:a==="仙品"?1:0};'
    'case"breakthrough":return{exp:Math.floor(v*100),spiritStones:Math.floor(vs*50),lotteryTickets:a==="传说"||a==="仙品"?1:0};'
    'case"alchemy":return{exp:Math.floor(v*25),spiritStones:Math.floor(vs*20)};'
    'case"equip":return{exp:Math.floor(v*15),spiritStones:Math.floor(vs*30)};'
    'case"pet":return{exp:Math.floor(v*20),spiritStones:Math.floor(vs*15)};'
    'case"sect":return{exp:Math.floor(v*40),spiritStones:Math.floor(vs*25),lotteryTickets:a==="仙品"?1:0};'
    'case"realm":return{exp:Math.floor(v*50),spiritStones:Math.floor(vs*40),lotteryTickets:a==="传说"||a==="仙品"?1:0};'
    'default:return{exp:Math.floor(v*20),spiritStones:Math.floor(vs*10)}}'
)

# --------------------------------------------------------------------------- F3 每日行乐重写

F3_ANCHOR = 'function YlxwTDaily() {'
F3_REPL = 'function YlxwTDaily() {'   # 只用于定位；真正插入在下方 F3 块

# 茶馆段（保留）+ 三件套挂载。整段替换 YlxwTDaily 函数体。
F3_BODY_ANCHOR = (
    'function YlxwTDaily() {\n'
    '  var r = YlxwUseList("/teahouse/today"), t = r.data, a = r.err, l = r.busy, c = r.load, '
    'd = YlxwUseAct(c), u = d.actKey, f = d.run, m = t && t.myBet;'
)
F3_BODY_REPL = (
    'function YlxwTDaily() {\n'
    '  var r = YlxwUseList("/teahouse/today"), t = r.data, a = r.err, l = r.busy, c = r.load, '
    'd = YlxwUseAct(c), u = d.actKey, f = d.run, m = t && t.myBet;\n'
    '  var fb = O.useState(5000), funBet = fb[0], setFunBet = fb[1];\n'
    '  var fun = (t && t.fun) || null;'
)

# 茶馆注额按钮：从「minBet 单档」升级为「四档 + 每日 3 注」
F3_TEA_ANCHOR = (
    'e.jsxs("div", { className: "flex gap-2", children: ['
    'e.jsx(YlxwBtn, { disabled: !!u || !t.open || !!m, onClick: function() { f("bet1", "/teahouse/bet", '
    '{ side: 0, stones: YlxwNum(t.minBet) || 100 }, "\\u4e0b\\u6ce8\\u6210\\u529f"); }, '
    'children: YlxwSide(t && t.topic, 0) + " \\u00b7 " + YlxwNum(t.minBet) + " \\u7075\\u77f3" }), '
    'e.jsx(YlxwBtn, { disabled: !!u || !t.open || !!m, onClick: function() { f("bet2", "/teahouse/bet", '
    '{ side: 1, stones: YlxwNum(t.minBet) || 100 }, "\\u4e0b\\u6ce8\\u6210\\u529f"); }, '
    'children: YlxwSide(t && t.topic, 1) + " \\u00b7 " + YlxwNum(t.minBet) + " \\u7075\\u77f3" })] })'
)
F3_TEA_REPL = (
    'e.jsx(YlxwFunBetBar, { label: "\\u6ce8\\u989d", value: funBet, options: '
    '[YlxwNum(t.minBet) || 500, 5000, 20000, YlxwNum(t.maxBet) || 50000], onChange: setFunBet }),\n'
    'e.jsxs("div", { className: "flex gap-2", children: ['
    'e.jsx(YlxwBtn, { disabled: !!u || !t.open || (!!m && YlxwNum(m.times) >= YlxwNum(t.maxTimes || 3)), '
    'onClick: function() { f("bet1", "/teahouse/bet", { side: 0, stones: YlxwNum(funBet) }, '
    '"\\u4e0b\\u6ce8\\u6210\\u529f"); }, '
    'children: YlxwSide(t && t.topic, 0) + " \\u00b7 " + YlxwNum(funBet) + " \\u7075\\u77f3" }), '
    'e.jsx(YlxwBtn, { disabled: !!u || !t.open || (!!m && YlxwNum(m.times) >= YlxwNum(t.maxTimes || 3)), '
    'onClick: function() { f("bet2", "/teahouse/bet", { side: 1, stones: YlxwNum(funBet) }, '
    '"\\u4e0b\\u6ce8\\u6210\\u529f"); }, '
    'children: YlxwSide(t && t.topic, 1) + " \\u00b7 " + YlxwNum(funBet) + " \\u7075\\u77f3" })] })'
)

# 我的下注行：加「已押 n/3 注 + 茶运」
F3_MYBET_ANCHOR = (
    'm && e.jsx(YlxwRow, { children: "\\u6211\\u7684\\u4e0b\\u6ce8\\uff1a" + '
    'YlxwSide(t && t.topic, m.side) + " \\u00b7 " + YlxwNum(m.stones) + " \\u7075\\u77f3" })'
)
F3_MYBET_REPL = (
    'm && e.jsxs(YlxwRow, { children: ["\\u6211\\u7684\\u4e0b\\u6ce8\\uff1a" + '
    'YlxwSide(t && t.topic, m.side) + " \\u00b7 " + YlxwNum(m.stones) + " \\u7075\\u77f3", '
    'e.jsx("span", { className: "ml-2 text-[11px] text-stone-500", children: '
    '"\\uff08\\u5df2\\u62bc " + YlxwNum(m.times) + "/" + YlxwNum(t.maxTimes || 3) + " \\u6ce8\\uff09" }), '
    'e.jsx("span", { className: "ml-2 text-[11px] text-amber-300", children: '
    '"\\u8336\\u8fd0 " + ((t.luck && t.luck.label) || "\\u5e73") + " \\u00d7" + YlxwNum(t.luck && t.luck.tier) })] })'
)

# 三件套挂载：把 pool 列表之后追加 fun 区块
F3_TAIL_ANCHOR = (
    '}), ((t && t.pool) || []).map(function(g) { return e.jsx(YlxwRow, { children: '
    'YlxwSide(t && t.topic, g.side) + "\\uff1a" + YlxwNum(g.bets) + " \\u6ce8 \\u00b7 " + '
    'YlxwNum(g.stones) + " \\u7075\\u77f3" }, "p" + g.side); })] })'
)
F3_TAIL_REPL = (
    '}), ((t && t.pool) || []).map(function(g) { return e.jsx(YlxwRow, { children: '
    'YlxwSide(t && t.topic, g.side) + "\\uff1a" + YlxwNum(g.bets) + " \\u6ce8 \\u00b7 " + '
    'YlxwNum(g.stones) + " \\u7075\\u77f3" }, "p" + g.side); }), '
    'e.jsx("div", { className: "text-xs text-amber-300 pt-2", children: '
    '"\\u884c\\u4e50\\u4e09\\u4ef6\\u5957" }), '
    'e.jsx(YlxwFunDice, { data: fun, reload: c }), '
    'e.jsx(YlxwFunSign, { data: fun, reload: c }), '
    'e.jsx(YlxwFunCard, { data: fun, reload: c })] })'
)

# --------------------------------------------------------------------------- F4 奇遇抽奖展示

F4_TIER_HINT_ANCHOR = (
    'u && e.jsx("div", { className: "text-xs text-red-300", children: u }), '
    'a ? e.jsx(YlxwErr, { retry: c, children: a }) : (t && t.draws || []).slice().reverse().map(function(b) {'
)
F4_TIER_HINT_REPL = (
    'u && e.jsx("div", { className: "text-xs text-red-300", children: u }), '
    'e.jsx("div", { className: "flex gap-1.5 flex-wrap text-[11px] text-stone-500", children: '
    '((t && t.tiers) || []).map(function(T) { return e.jsx("span", { className: "px-1.5 py-0.5 rounded '
    'border border-stone-700 bg-ink-800", children: T.name + " " + YlxwNum(T.weight) + "% \\u00b7 \\u7075\\u77f3 " '
    '+ YlxwNum(T.stonesMin) + "~" + YlxwNum(T.stonesMax) }, "t" + T.key); }) }), '
    'a ? e.jsx(YlxwErr, { retry: c, children: a }) : (t && t.draws || []).slice().reverse().map(function(b) {'
)

# 抽奖记录行：补「抽奖券 / 额外珍宝」展示
F4_ROW_ANCHOR = (
    'return e.jsx(YlxwRow, { children: e.jsxs("span", { children: ["#", YlxwNum(b.count), " ", '
    'e.jsx("span", { className: "text-amber-300", children: b.tierName }), " ", b.text, '
    '" \\uff08\\u7075\\u77f3+", YlxwNum(b.stones), " \\u4fee\\u4e3a+", YlxwNum(b.expGain), "\\uff09"] }) }, '
    '"d" + b.count);'
)
F4_ROW_REPL = (
    'return e.jsx(YlxwRow, { children: e.jsxs("span", { children: ["#", YlxwNum(b.count), " ", '
    'e.jsx("span", { className: "text-amber-300", children: b.tierName }), " ", b.text, '
    '" \\uff08\\u7075\\u77f3+", YlxwNum(b.stones), " \\u4fee\\u4e3a+", YlxwNum(b.expGain), '
    '(YlxwNum(b.tickets) > 0 ? (" \\u62bd\\u5956\\u5238+" + YlxwNum(b.tickets)) : ""), '
    '(b.bonusText ? (" \\u2728" + b.bonusText) : ""), "\\uff09"] }) }, "d" + b.count);'
)

# 抽奖即时 toast：服务端 0.8.6 起 /adventure/draw 回执带 tickets / bonusText，
# 客户端同步展示，玩家不用等列表刷新就知道抽到了券或额外珍宝。
F4B_TOAST_ANCHOR = (
    'ia("\\u5947\\u9047\\uff1a" + (b.tierName || "") + " \\u00b7 " + (b.text || "") + " '
    '\\uff08\\u7075\\u77f3+" + YlxwNum(b.stones) + " \\u4fee\\u4e3a+" + YlxwNum(b.expGain) + '
    '"\\uff09"), await c(), YlxwDirty();'
)
F4B_TOAST_REPL = (
    'ia("\\u5947\\u9047\\uff1a" + (b.tierName || "") + " \\u00b7 " + (b.text || "") + " '
    '\\uff08\\u7075\\u77f3+" + YlxwNum(b.stones) + " \\u4fee\\u4e3a+" + YlxwNum(b.expGain) + '
    '(YlxwNum(b.tickets) > 0 ? " \\u62bd\\u5956\\u5238+" + YlxwNum(b.tickets) : "") + '
    '(b.bonusText ? " \\u2728" + b.bonusText : "") + '
    '"\\uff09"), await c(), YlxwDirty();'
)

# --------------------------------------------------------------------------- F5a 妖灵日志折叠

F5A_HEAD_ANCHOR = 'function YlxwTPet() {\n  var r = YlxwUseList("/pet")'
F5A_HEAD_REPL = ('function YlxwTPet() {\n'
                 '  var _pl = O.useState(!1), _logOpen = _pl[0], _setLogOpen = _pl[1];\n'
                 '  var r = YlxwUseList("/pet")')

F5A_LOG_ANCHOR = (
    '((t && t.careLog) || []).map(function(g, h) { return e.jsx(YlxwRow, { children: "[" + '
    '(YLXW_KIND[g.kind] || "\\u8bb0\\u5f55") + "] " + g.detail }, "l" + h); })'
)
F5A_LOG_REPL = (
    '(function() { var L = (t && t.careLog) || []; var lim = _logOpen ? L.length : Math.min(3, L.length); '
    'var rows = L.slice(0, lim).map(function(g, h) { return e.jsx(YlxwRow, { children: "[" + '
    '(YLXW_KIND[g.kind] || "\\u8bb0\\u5f55") + "] " + g.detail }, "l" + h); }); '
    'if (L.length > 3) rows.push(e.jsx("button", { key: "lmore", onClick: function() { _setLogOpen(!_logOpen); }, '
    'className: "w-full text-xs text-stone-400 hover:text-stone-200 py-1.5 border border-dashed border-stone-700 rounded", '
    'children: _logOpen ? ("\\u6536\\u8d77\\uff08\\u5171 " + L.length + " \\u6761\\uff09") '
    ': ("\\u5c55\\u5f00\\u5168\\u90e8 " + L.length + " \\u6761") })); return rows; })()'
)

# --------------------------------------------------------------------------- F5b 灵兽远征 20000 灵石

F5B_START_ANCHOR = (
    'var now = Date.now();\n'
    '  var ne = { id: St(), petId: pet.id, petName: pet.name, locationId: loc.id, locationName: loc.name,\n'
    '    startTime: now, duration: loc.durationMs, endTime: now + loc.durationMs, status: "exploring" };\n'
    '  return { success: !0, message: "\\u3010\\u7075\\u517d\\u8fdc\\u5f81\\u3011\\u4f60\\u6d3e\\u9063\\u3010" '
    '+ pet.name + "\\u3011\\u524d\\u5f80\\u3010" + loc.name + "\\u3011\\u8e0f\\u4e0a\\u5bfb\\u73cd\\u4e4b\\u65c5\\uff01",\n'
    '    updatedPlayer: Object.assign({}, p, { grotto: Object.assign({}, g, '
    '{ petExpeditions: cur.concat([ne]) }) }) };'
)
F5B_START_REPL = (
    'var _expCost = 20000;\n'
    '  var _bal = Math.max(0, Math.floor(Number(p.spiritStones) || 0));\n'
    '  if (_bal < _expCost) {\n'
    '    return { success: !1, message: "\\u7075\\u77f3\\u4e0d\\u8db3\\uff1a\\u6d3e\\u9063\\u8fdc\\u5f81\\u9700 " '
    '+ _expCost + " \\u7075\\u77f3\\uff0c\\u5f53\\u524d\\u4ec5\\u6709 " + _bal + "\\u3002", updatedPlayer: p };\n'
    '  }\n'
    '  var now = Date.now();\n'
    '  var ne = { id: St(), petId: pet.id, petName: pet.name, locationId: loc.id, locationName: loc.name,\n'
    '    startTime: now, duration: loc.durationMs, endTime: now + loc.durationMs, status: "exploring" };\n'
    '  return { success: !0, message: "\\u3010\\u7075\\u517d\\u8fdc\\u5f81\\u3011\\u6d88\\u8017 " + _expCost '
    '+ " \\u7075\\u77f3\\uff0c\\u6d3e\\u9063\\u3010" + pet.name + "\\u3011\\u524d\\u5f80\\u3010" + loc.name '
    '+ "\\u3011\\u8e0f\\u4e0a\\u5bfb\\u73cd\\u4e4b\\u65c5\\uff01",\n'
    '    updatedPlayer: Object.assign({}, p, { spiritStones: _bal - _expCost, '
    'grotto: Object.assign({}, g, { petExpeditions: cur.concat([ne]) }) }) };'
)

F5B_BTN_ANCHOR = 'onClick: function () { doStart(L.id); }, children: "\\u6d3e\\u9063" })'
F5B_BTN_REPL = ('onClick: function () { doStart(L.id); }, children: "\\u6d3e\\u9063\\uff08 20000 \\u7075\\u77f3\\uff09" })')

# --------------------------------------------------------------------------- F6 融合页左右两列
# ① modal 内容区：`__xw` 真 → 两列（左仙务块 / 右页本体）；假 → 原样直传 l。
F6_FUSE_ANCHOR = 'children:[__xw?e.jsx(YlxwFuse,{k:__xw}):null,l]'
F6_FUSE_REPL = ('children:__xw?e.jsxs("div",{className:"grid grid-cols-1 md:grid-cols-2 gap-4 items-start",'
                'children:[e.jsx("div",{className:"min-w-0",children:e.jsx(YlxwFuse,{k:__xw})}),'
                'e.jsx("div",{className:"min-w-0",children:l})]}):l')

# ② modal 外壳尺寸：融合页强制 6xl（三元互斥，避免与 size 键的 md:max-w-3xl 撞车）
F6_SIZE_ANCHOR = 'w-full ${jN[c]} ${NN[d]}'
F6_SIZE_REPL = 'w-full ${__xw?"md:max-w-6xl":jN[c]} ${NN[d]}'

# --------------------------------------------------------------------------- F7 日常任务奖励「显示 == 实发」（0.8.8 item8）

# 显示端 helper：公式与发放端 `claimQuestReward` 里那条**逐字符同序**，
# 同输入下 IEEE-754 结果必然一致 ⇒ 「面板显示值」恒等于「点击后余额增量」。
# 落点必须与 fe / YLRF 同作用域（两者都是基座 module 级），故插在 YlxwTDaily 之前（module 级）。
# ★ 只读：本 helper 不改任何落盘/发放路径；发放端 `S=Math.floor(...)` 一行未动。
F7_HELPER_ANCHOR = 'function YlxwTDaily() {'
F7_HELPER_JS = (
    '/* == YL_DAILY_DISPLAY_ALIGN_V288 (item8: quest card shows the amount actually paid) == */\n'
    '/* same formula, same operand order as claimQuestReward -> display == payout, bit for bit */\n'
    'function YlxwDailyStones(base, realm) {\n'
    '  return Math.floor((base || 0) / (1 + Math.max(0, fe.indexOf(realm)) * 0.5) * YLRF(realm) * 2.13);\n'
    '}\n'
    '/* == end YL_DAILY_DISPLAY_ALIGN_V288 == */\n'
)

# ① 卡片组件签名：收下 realm（由父组件 TM 的 player.realm 传入）
F7_CARD_SIG_ANCHOR = 'qM=({quest:t,onClaimReward:r,isClaimed:a})=>{'
F7_CARD_SIG_REPL = 'qM=({quest:t,onClaimReward:r,isClaimed:a,realm:YlqR})=>{'

# ② 渲染点：把玩家 realm 透传进卡片
F7_CALL_ANCHOR = 'e.jsx(qM,{quest:R,onClaimReward:l,isClaimed:'
F7_CALL_REPL = 'e.jsx(qM,{quest:R,realm:a.realm,onClaimReward:l,isClaimed:'

# ③ 灵石显示值：原值 → 实发值（修为 / 抽奖券两档一行不动）
F7_VALUE_ANCHOR = 'children:[t.reward.spiritStones," 灵石"]'
F7_VALUE_REPL = 'children:[YlxwDailyStones(t.reward.spiritStones,YlqR)," 灵石"]'

# ④ 「奖励价值」排序键里的灵石项也走实发值 —— 否则排序与卡片显示自相矛盾
#   （同境界下灵石被同倍放大，但灵石权重 0.1 vs 修为 1 不等比，跨档排序会翻转）
F7SORT_A_ANCHOR = ('const k=(R.reward.exp||0)+(R.reward.spiritStones||0)*.1+'
                   '(R.reward.lotteryTickets||0)*10;')
F7SORT_A_REPL = ('const k=(R.reward.exp||0)+YlxwDailyStones(R.reward.spiritStones,a.realm)*.1+'
                 '(R.reward.lotteryTickets||0)*10;')
F7SORT_B_ANCHOR = ('return(E.reward.exp||0)+(E.reward.spiritStones||0)*.1+'
                   '(E.reward.lotteryTickets||0)*10-k;')
F7SORT_B_REPL = ('return(E.reward.exp||0)+YlxwDailyStones(E.reward.spiritStones,a.realm)*.1+'
                 '(E.reward.lotteryTickets||0)*10-k;')


# --------------------------------------------------------------------------- F7 丹房/炼器坊融合页右侧加宽（0.8.8 item18）

# 用户原话（2026-09-29）：「炼丹炼器右侧 UI 被挤压了。」
#
# ★ 复现实测（沙盒 idx=2 / bundle index-v287-20260929.js / Playwright 1440×900，脚本 _a4_recon.py）：
#   dialog 外壳 = **1152px**（= F6 的 md:max-w-6xl），内容区 1102px，F6 两列 **543 / 543**。
#   左列 = 仙务·丹炉 融合块，右列 = 丹房本体（炼丹/炼器两页签 + 4 套子布局）只剩 543px：
#     · 炼器·材料合成：左右各 ≈250px；品级筛选「全部/普通/稀有/传说/仙品」被压成竖排单字方块；
#       造化炼器 8 格投料槽每格 ≈50px；名称/部位输入框各 ≈100px。
#     · 炼器·装备融合：左列 w-1/3 = 181px，「装备与合成石」标题竖排（实测 span w=14 h=120），
#       品级 chip 竖排（w=10 h=30）。
#     · 炼丹：丹方卡 2 列各 ≈250px，「预计成丹率」徽标把丹名挤成两行。
#   ⇒ 根因**不是** c4 案《T17-丹炉重构.md》§4.2 G2 写的 `size:"4xl"` = 896px：
#     0.8.3 flow083 置顶 + 0.8.6 本模块 F6 之后，本页带 `xw:"alchemy"` ⇒ 外壳被 F6 的
#     三元互斥式 `w-full ${__xw?"md:max-w-6xl":jN[c]}` 强制 1152px，`size` 键**完全失效**。
#     真正的挤压源是 **F6 的两列网格是 1:1 等分**，而丹房本体是「宽屏多列」布局
#     （内部 md:grid-cols-2 / md:grid-cols-3 / md:flex-row / w-1/3 / grid-cols-4 全是
#      **视口**断点，1440 ≥ 768 恒成立 ⇒ 容器只有 543px 也照样排多列）。
#
# ★ 修法（只用**冻结 CSS 里已存在**的类，不新增 CSS、不改共享外壳 wN 对其它 8 页的行为）：
#   ① 本页不再走 F6 的两列等分网格：L4 的 props 去掉 `xw:"alchemy"`
#      （⇒ 外壳回落到 jN[size]，不再被强制 6xl）；`size:"4xl"` → `"full"`
#      （`md:max-w-[95vw]`，与「储物袋」同档；CSS @148188 晚于 6xl @148142 ⇒ 同特异性下 95vw 胜）。
#   ② 仙务·丹炉 融合块改由 L4 **自己**渲染成「固定 320px 左列 + flex-1 右列」：
#        e.jsx(YlxwFuse,{k:"alchemy"}) —— 与 wN 内 `e.jsx(YlxwFuse,{k:__xw})` 同一组件、
#        同一「仙务·丹炉 已融合至本页」标题 ⇒ 视觉与行为不变。
#        作用域依据：`function YlxwFuse` 是基座顶层函数声明，与 wN(@251742) 同作用域 ——
#        wN 早已**前向引用**它且在线上正常渲染 ⇒ L4(@1189577) 必然可见（同一扁平模块作用域）。
#        `md:w-80` = 320px 是本 CSS 里**唯一**存在的 md: 固定宽度档（无 md:w-64 / md:w-72）。
#      ⇒ 实测 1440：外壳 1368 / 内容 1318 / 左列 320 + **右列 982**（丹房本体 +439px，+81%）；
#         1280 → 右列 830；1024 → 右列 587；768 → 344（与改前 335 基本持平）；
#         390 → `flex-col` 单列堆叠，丹房本体 358 满宽（移动端不回归）。
#   ③ 顺手补两处既有隐患（c4 案 F2/F4，只加类不改结构）：
#      · 材料合成两列 `flex-1` 各补 `min-w-0`（flex 子项默认 min-width:auto，会被内容撑破轨道）；
#      · 造化炼器右列补 `overflow-y-auto`（原容器 h-full overflow-hidden 但右列无滚动 ⇒ 超高被裁）。
#   ★ 不改：炼丹 tab 的 `md:grid-cols-2` 丹方卡（与 c4 案 F6 同结论）、炼器三处逻辑、
#     装备融合行的 `w-1/3`（改它需 `md:w-1/3`，本 CSS **不存在**；390/768 下装备融合仍为
#     既存横排挤压 —— 属 T17 丹炉重构范围，本批不动，以免在 768 引入新的横向溢出）。
#   ★ 勘误（供 T17 接线人）：c4 案 §4.2 的 F1「新增 jN["5xl"]="md:max-w-5xl"」与
#     F3「md:grid-cols-[minmax(240px,1fr)_minmax(360px,1.3fr)]」**在冻结 CSS 里都不存在**
#     （实测 max-w 档只有 2xl/3xl/4xl/6xl/[95vw]/[500px]/lg/md/sm/xl；grid-cols 任意值
#      只有 `grid-cols-[minmax(0,1fr)_92px_auto]`）⇒ 照抄会得到「无 max-width」或「退化为单列」。

# ① 本页不再挂 F6 融合网格（去掉 xw 键；后随的中文标题串原样保留，不进 zh()）
F7_XW_ANCHOR = 'xw:"alchemy",isOpen:t,onClose:r,title:f==="alchemy"?"'
F7_XW_REPL = 'isOpen:t,onClose:r,title:f==="alchemy"?"'

# ② 外壳宽度 4xl → full（95vw），根 div 改「左固定 320px 仙务块 + 右 flex-1 丹房本体」
F7_ROOT_ANCHOR = 'size:"4xl",height:"2xl",children:e.jsxs("div",{className:"flex flex-col h-full",children:['
F7_ROOT_REPL = ('size:"full",height:"2xl",children:e.jsxs("div",{className:"flex flex-col md:flex-row gap-4 h-full",children:['
                'e.jsx("div",{className:"md:w-80 shrink-0 min-w-0",children:e.jsx(YlxwFuse,{k:"alchemy"})}),'
                'e.jsxs("div",{className:"flex-1 min-w-0 flex flex-col h-full",children:[')

# ② 根 div 收口：多包一层 e.jsxs ⇒ 尾闭合由 `]})})}` 变 `]})]})})}`
F7_TAIL_ANCHOR = ']})})},D4=Rt.memo(L4)'
F7_TAIL_REPL = ']})]})})},D4=Rt.memo(L4)'

# ③ 材料合成两列补 min-w-0 / 造化炼器补滚动
F7_CRAFT_L_ANCHOR = 'className:"flex-1 flex flex-col overflow-hidden bg-ink-900/50 p-3 rounded border border-stone-800"'
F7_CRAFT_L_REPL = 'className:"flex-1 min-w-0 flex flex-col overflow-hidden bg-ink-900/50 p-3 rounded border border-stone-800"'
F7_CRAFT_R_ANCHOR = 'className:"flex-1 flex flex-col bg-ink-800 border border-stone-700 p-4 rounded relative"'
F7_CRAFT_R_REPL = 'className:"flex-1 min-w-0 overflow-y-auto flex flex-col bg-ink-800 border border-stone-700 p-4 rounded relative"'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 0) 注入「每日行乐」四玩法组件（必须在 YlxwTDaily 之前定义）
    p.insert_before('fun086-components', F3_ANCHOR, zh(INJECT_JS) + '\n',
                    expect=1, note='注入 YlxwFunDice / YlxwFunSign / YlxwFunCard / YlxwFunBetBar')

    # 1) F1 洞府加速按钮补费用提示
    p.replace('fun086-F1-accel', F1_ANCHOR, F1_REPL, expect=1,
              note='加速按钮文案补「加速 N 灵石」')

    # 2) F2 原生日常任务灵石 ×5（只乘灵石，修为不动）
    p.replace('fun086-F2a-var', F2_ANCHOR, F2_REPL, expect=1, note='hg() 增 vs=v*5')
    p.replace('fun086-F2b-switch', F2S_ANCHOR, F2S_REPL, expect=1, note='spiritStones 档位 v→vs')

    # 3) F3 每日行乐
    p.replace('fun086-F3-head', F3_BODY_ANCHOR, F3_BODY_REPL, expect=1, note='YlxwTDaily 加 fun 状态')
    p.replace('fun086-F3-tea', F3_TEA_ANCHOR, F3_TEA_REPL, expect=1, note='茶馆注额四档 + 每日 3 注')
    p.replace('fun086-F3-mybet', F3_MYBET_ANCHOR, F3_MYBET_REPL, expect=1, note='我的下注加次数与茶运')
    p.replace('fun086-F3-tail', F3_TAIL_ANCHOR, F3_TAIL_REPL, expect=1, note='挂载行乐三件套')

    # 4) F4 奇遇抽奖
    p.replace('fun086-F4-tier', F4_TIER_HINT_ANCHOR, F4_TIER_HINT_REPL, expect=1,
              note='奇遇面板加品阶区间条')
    p.replace('fun086-F4-row', F4_ROW_ANCHOR, F4_ROW_REPL, expect=1,
              note='抽奖记录补抽奖券与额外珍宝')
    p.replace('fun086-F4b-toast', F4B_TOAST_ANCHOR, F4B_TOAST_REPL, expect=1,
              note='抽奖即时 toast 补抽奖券/额外珍宝')

    # 5) F5a 妖灵日志折叠
    p.replace('fun086-F5a-head', F5A_HEAD_ANCHOR, F5A_HEAD_REPL, expect=1, note='YlxwTPet 加折叠 state')
    p.replace('fun086-F5a-log', F5A_LOG_ANCHOR, F5A_LOG_REPL, expect=1, note='careLog 默认 3 条 + 展开')

    # 6) F5b 灵兽远征 20000 灵石
    p.replace('fun086-F5b-start', F5B_START_ANCHOR, F5B_START_REPL, expect=1,
              note='YlxwExpStart 加 20000 灵石消耗与扣费')
    p.replace('fun086-F5b-btn', F5B_BTN_ANCHOR, F5B_BTN_REPL, expect=1, note='派遣按钮显示 20000 灵石')

    # 7) F6 融合页左右两列
    p.replace('fun086-F6-fuse', F6_FUSE_ANCHOR, F6_FUSE_REPL, expect=1,
              note='modal 内容区 [仙务块, 页本体] → 桌面两列（非融合页直传 l）')
    p.replace('fun086-F6-size', F6_SIZE_ANCHOR, F6_SIZE_REPL, expect=1,
              note='融合页外壳 md:max-w-6xl（768px → 1152px）')

    # 8) F7 丹房/炼器坊融合页右侧加宽（0.8.8 item18）
    p.replace('fun086-F7-xw', F7_XW_ANCHOR, F7_XW_REPL, expect=1,
              note='丹房去掉 xw 键（不再走 F6 两列等分网格，改由 L4 自渲染仙务块）')
    p.replace('fun086-F7-root', F7_ROOT_ANCHOR, F7_ROOT_REPL, expect=1,
              note='丹房外壳 4xl→full(95vw) + 根 div 改「左固定 320px 仙务块 + 右 flex-1 本体」')
    p.replace('fun086-F7-tail', F7_TAIL_ANCHOR, F7_TAIL_REPL, expect=1,
              note='根 div 收口补一层 e.jsxs 闭合')
    p.replace('fun086-F7-craft-l', F7_CRAFT_L_ANCHOR, F7_CRAFT_L_REPL, expect=1,
              note='材料合成左列补 min-w-0')
    p.replace('fun086-F7-craft-r', F7_CRAFT_R_ANCHOR, F7_CRAFT_R_REPL, expect=1,
              note='造化炼器右列补 min-w-0 + overflow-y-auto')

    # 8) F7 日常任务奖励「显示 == 实发」（0.8.8 item8；只改显示端，发放逻辑零改动）
    p.insert_before('fun086-F7-helper', F7_HELPER_ANCHOR, F7_HELPER_JS,
                    expect=1, note='注入 YlxwDailyStones（与 claimQuestReward 同式同序）')
    p.replace('fun086-F7-card-sig', F7_CARD_SIG_ANCHOR, F7_CARD_SIG_REPL, expect=1,
              note='日常任务卡片收 realm 入参')
    p.replace('fun086-F7-call', F7_CALL_ANCHOR, F7_CALL_REPL, expect=1,
              note='渲染点透传 player.realm')
    p.replace('fun086-F7-value', F7_VALUE_ANCHOR, F7_VALUE_REPL, expect=1,
              note='灵石显示值改走实发公式（修为/抽奖券不动）')
    p.replace('fun086-F7-sort-a', F7SORT_A_ANCHOR, F7SORT_A_REPL, expect=1,
              note='「奖励价值」排序键的灵石项改走实发值（与卡片显示自洽）')
    p.replace('fun086-F7-sort-b', F7SORT_B_ANCHOR, F7SORT_B_REPL, expect=1,
              note='排序比较项同步改走实发值')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- 注入块本体 ----
        ('F·YlxwFunDice 已定义',       'function YlxwFunDice(props) {', 1, '==', ''),
        ('F·YlxwFunSign 已定义',       'function YlxwFunSign(props) {', 1, '==', ''),
        ('F·YlxwFunCard 已定义',       'function YlxwFunCard(props) {', 1, '==', ''),
        ('F·YlxwFunBetBar 已定义',     'function YlxwFunBetBar(props) {', 1, '==', ''),
        ('F·三玩法端点路径',           'YlxwPost("/fun/dice"', 1, '==', ''),
        ('F·求签端点路径',             'YlxwPost("/fun/sign"', 1, '==', ''),
        ('F·翻牌端点路径',             'YlxwPost("/fun/card"', 1, '==', ''),
        ('F·未误用 403 语义',          'res.status === 403', 1, '==', '仅 0.8.5 秘境 gate 有，本模块不新增'),

        # ---- F1 ----
        ('F1·加速按钮带费用',
         'Math.max(Br.minCost,Math.ceil(I/6e4)*Br.costPerMinute).toLocaleString()', 1, '==', ''),
        ('F1·旧无费用按钮已清零',
         'title:"使用灵石加速生长",children:[e.jsx(rm,{size:14}),"加速"]', 0, '==', ''),
        ('F1·加速扣费逻辑未动',
         'const q=C.harvestTime-g,w=Math.ceil(q/6e4),', 1, '==', '服务端/客户端口径一致'),
        ('F1·Br 常量未动', 'Br={dailyLimit:10,costPerMinute:100,minCost:1000}', 1, '==', ''),

        # ---- F2 ----
        ('F2·vs 变量已引入', 'vs=v*5;switch(t){', 1, '==', ''),
        ('F2·灵石档位全走 vs', 'spiritStones:Math.floor(v*10)}', 0, '==', 'meditate/default 旧档已清零'),
        ('F2·修为档位未动', 'exp:Math.floor(v*20),spiritStones:Math.floor(vs*10)}', 2, '==', 'meditate + default'),
        ('F2·灵石档位共 9 处', 'spiritStones:Math.floor(vs*', 9, '==', '8 类型 + default'),
        ('F2·日常任务模板未动', '$3=[{type:"meditate",name:"晨光吐纳"', 1, '==', ''),
        ('F2·领奖折算公式未动',
         'S=Math.floor((j.reward.spiritStones||0)/(1+Math.max(0,fe.indexOf(m.realm))*.5)*YLRF(m.realm)*2.13)',
         1, '==', '展示与到账同源'),

        # ---- F3 ----
        ('F3·面板已挂三件套', 'e.jsx(YlxwFunDice, { data: fun, reload: c })', 1, '==', ''),
        ('F3·求签已挂', 'e.jsx(YlxwFunSign, { data: fun, reload: c })', 1, '==', ''),
        ('F3·翻牌已挂', 'e.jsx(YlxwFunCard, { data: fun, reload: c })', 1, '==', ''),
        ('F3·fun 状态已引入', 'var fun = (t && t.fun) || null;', 1, '==', ''),
        ('F3·茶馆注额改四档', 'e.jsx(YlxwFunBetBar, { label: "\\u6ce8\\u989d", value: funBet', 1, '==', ''),
        ('F3·茶馆每日 3 注', 'YlxwNum(m.times) >= YlxwNum(t.maxTimes || 3)', 2, '==', 'A/B 两个按钮'),
        ('F3·旧固定 minBet 下注已清零',
         '{ side: 0, stones: YlxwNum(t.minBet) || 100 }', 0, '==', ''),
        ('F3·茶馆端点未改', 'YlxwUseList("/teahouse/today")', 1, '==', ''),
        ('F3·我的下注带茶运标签', '"\\u8336\\u8fd0 " + ((t.luck && t.luck.label) || "\\u5e73") + " \\u00d7"', 1, '==', ''),

        # ---- F4 ----
        ('F4·品阶区间条已加', '((t && t.tiers) || []).map(function(T)', 1, '==', ''),
        ('F4·区间用 stonesMin', 'YlxwNum(T.stonesMin) + "~" + YlxwNum(T.stonesMax)', 1, '==', ''),
        ('F4·记录行带抽奖券', '(YlxwNum(b.tickets) > 0 ? (" \\u62bd\\u5956\\u5238+"', 1, '==', ''),
        ('F4b·抽奖 toast 带券', 'YlxwNum(b.expGain) + (YlxwNum(b.tickets) > 0 ? " \\u62bd\\u5956\\u5238+"', 1, '==', ''),
        ('F4b·抽奖 toast 带珍宝', '(b.bonusText ? " \\u2728" + b.bonusText : "") + "\\uff09"), await c(), YlxwDirty();', 1, '==', ''),
        ('F4b·旧 toast 已清零', 'YlxwNum(b.expGain) + "\\uff09"), await c(), YlxwDirty();', 0, '==', ''),
        ('F4·抽一次按钮未动', 'children: "\\u62bd\\u4e00\\u6b21"', 1, '==', ''),
        ('F4·奇遇端点未改', 'YlxwGet("/adventure/draw")', 1, '==', ''),

        # ---- F5a ----
        ('F5a·折叠 state 已加', 'var _pl = O.useState(!1), _logOpen = _pl[0], _setLogOpen = _pl[1];', 1, '==', ''),
        ('F5a·默认只渲染 3 条', 'var lim = _logOpen ? L.length : Math.min(3, L.length);', 1, '==', ''),
        ('F5a·展开按钮已加', '"\\u5c55\\u5f00\\u5168\\u90e8 " + L.length + " \\u6761"', 1, '==', ''),
        ('F5a·旧全量渲染已清零',
         '((t && t.careLog) || []).map(function(g, h) { return e.jsx(YlxwRow,', 0, '==', ''),
        ('F5a·/pet 端点未改', 'YlxwUseList("/pet")', 1, '==', ''),

        # ---- F5b ----
        ('F5b·远征 20000 消耗已加', 'var _expCost = 20000;', 1, '==', ''),
        ('F5b·灵石不足拒绝', 'if (_bal < _expCost) {', 1, '==', ''),
        ('F5b·扣费已入 updatedPlayer', 'spiritStones: _bal - _expCost,', 1, '==', ''),
        ('F5b·派遣按钮显示消耗', 'children: "\\u6d3e\\u9063\\uff08 20000 \\u7075\\u77f3\\uff09"', 1, '==', ''),
        ('F5b·旧无消耗派遣已清零',
         'updatedPlayer: Object.assign({}, p, { grotto: Object.assign({}, g, { petExpeditions: cur.concat([ne]) }) }) }',
         0, '==', ''),
        ('F5b·远征结算未动', 'function YlxwExpClaim(', 1, '==', ''),
        ('F5b·远征到期结算未动', 'function YlxwExpTick(', 1, '==', ''),

        # ---- F6 融合页左右两列 ----
        # ★ 0.8.7 T6（yl_t6chardex_ext.py）人物志两列**逐字复用**了同一套类串
        #   ⇒ 本模块注入 1 处 + T6 人物志 1 处 = 2。此处断言总数 2，
        #   本模块自身的唯一性由下一条「左列仙务块」锚（含 YlxwFuse）单独钉死。
        ('F6·两列类串总数（本模块 1 + T6 人物志 1）',
         'grid grid-cols-1 md:grid-cols-2 gap-4 items-start', 2, '==', '0.8.7 T6 复用同串'),
        ('F6·本模块两列类串落在 Fuse 分支内',
         'className:"grid grid-cols-1 md:grid-cols-2 gap-4 items-start",children:[e.jsx("div",{className:"min-w-0",children:e.jsx(YlxwFuse,{k:__xw})})',
         1, '==', ''),
        ('F6·左列仙务块带 min-w-0',
         'e.jsx("div",{className:"min-w-0",children:e.jsx(YlxwFuse,{k:__xw})})', 1, '==', ''),
        ('F6·右列页本体带 min-w-0', 'e.jsx("div",{className:"min-w-0",children:l})', 1, '==', ''),
        ('F6·非融合页仍直传 children', ']}):l', 1, '==', '非融合页 modal 行为不变'),
        ('F6·旧单列 children 已清零',
         'children:[__xw?e.jsx(YlxwFuse,{k:__xw}):null,l]', 0, '==', ''),
        ('F6·融合页宽度放开 6xl',
         'w-full ${__xw?"md:max-w-6xl":jN[c]} ${NN[d]}', 1, '==', ''),
        ('F6·旧尺寸模板已清零', 'w-full ${jN[c]} ${NN[d]}', 0, '==', ''),
        ('F6·YlxwFuse 唯一渲染点', 'e.jsx(YlxwFuse,{k:__xw})', 1, '==', ''),
        ('F6·9 个融合页 xw 键未动', 'xw:', 8, '==', '签名 1 + 融合页 10 − item18 丹房 1 − R-065 sect 1 = 8（接线人校准：R-065 yl_065_ext 合法摘除宗门融合键）'),
        ('F6·未误用不存在的 md:grid', 'className:"md:grid ', 0, '==', '本 CSS 无 md:grid'),
        ('F6·未误用不存在的 md:sticky', 'md:sticky', 0, '==', '左列高于视口，禁用 sticky'),

        # ---- F7 丹房/炼器坊融合页右侧加宽（0.8.8 item18）----
        ('F7·丹房不再挂 xw 融合键', 'xw:"alchemy"', 0, '==', '改由 L4 自渲染仙务块'),
        ('F7·丹房外壳宽度放开 95vw', 'size:"full",height:"2xl"', 1, '==', ''),
        ('F7·丹房左右两栏容器', 'className:"flex flex-col md:flex-row gap-4 h-full"', 1, '==', ''),
        ('F7·左列仙务块固定 320px', 'e.jsx("div",{className:"md:w-80 shrink-0 min-w-0",children:e.jsx(YlxwFuse,{k:"alchemy"})})', 1, '==', '与 wN 内同组件'),
        ('F7·右列丹房本体 flex-1', 'e.jsxs("div",{className:"flex-1 min-w-0 flex flex-col h-full",children:[', 1, '==', ''),
        ('F7·根 div 尾闭合已补层', F7_TAIL_REPL, 1, '==', ''),
        ('F7·材料合成左列补 min-w-0', F7_CRAFT_L_REPL, 1, '==', 'c4 案 F2'),
        ('F7·造化炼器补 min-w-0+滚动', F7_CRAFT_R_REPL, 1, '==', 'c4 案 F2/F4'),
        ('F7·旧 4xl 外壳已清零', F7_ROOT_ANCHOR, 0, '==', ''),
        ('F7·旧无下限左列已清零', F7_CRAFT_L_ANCHOR, 0, '==', ''),
        ('F7·旧无下限右列已清零', F7_CRAFT_R_ANCHOR, 0, '==', ''),
        ('F7·未误用不存在的 md:w-64', 'md:w-64', 0, '==', '本 CSS 只有 md:w-80 固定档'),
        ('F7·未误用不存在的 md:w-72', 'md:w-72', 0, '==', '同上'),
        ('F7·未误用不存在的 md:max-w-5xl', 'md:max-w-5xl', 0, '==', 'c4 案 F1 的 5xl 档不可用'),
        ('F7·未误用不存在的 md:w-1/3', 'md:w-1/3', 0, '==', '本 CSS 无此类'),
        ('F7·未误用不存在的 grid-cols minmax', 'md:grid-cols-[minmax(', 0, '==', 'c4 案 F3 不可用'),
        ('F7·wN 内仙务块渲染点未动', 'e.jsx(YlxwFuse,{k:__xw})', 1, '==', '其余 8 融合页不受影响'),
        ('F7·炼器三处逻辑未动', 'zg.craftFromMaterials(m,j,b)', 1, '==', ''),

        # ---- F7 日常任务奖励显示对齐实发（0.8.8 item8）----
        ('F2b·helper 已注入', 'function YlxwDailyStones(base, realm) {', 1, '==', ''),
        ('F2b·helper 与发放端同式同序',
         '(base || 0) / (1 + Math.max(0, fe.indexOf(realm)) * 0.5) * YLRF(realm) * 2.13', 1, '==',
         '与 claimQuestReward 的 S=Math.floor(...) 逐字符同序'),
        ('F2b·卡片取值走 helper', 'children:[YlxwDailyStones(t.reward.spiritStones,YlqR)," 灵石"]', 1, '==', ''),
        ('F2b·旧原值显示已清零', 'children:[t.reward.spiritStones," 灵石"]', 0, '==', ''),
        ('F2b·卡片签名已收 realm', 'qM=({quest:t,onClaimReward:r,isClaimed:a,realm:YlqR})=>{', 1, '==', ''),
        ('F2b·渲染点已传 realm', 'e.jsx(qM,{quest:R,realm:a.realm,onClaimReward:l,isClaimed:', 1, '==', ''),
        ('F2b·修为档未动', 'children:[t.reward.exp," 修为"]', 1, '==', '修为直接透传'),
        ('F2b·抽奖券档未动', 'children:[t.reward.lotteryTickets," 抽奖券"]', 1, '==', '抽奖券直接透传'),
        ('F2b·发放端公式仍原样', 'S=Math.floor((j.reward.spiritStones||0)/'
                                '(1+Math.max(0,fe.indexOf(m.realm))*.5)*YLRF(m.realm)*2.13)', 1, '==',
         '发放逻辑一行未动（数值不变）'),
        ('F2b·一键领取未被破坏', 'e.jsx(Lb,{size:14}),"一键领取 ("', 1, '==', ''),
        ('F2b·奖励价值排序键已走实发值',
         'const k=(R.reward.exp||0)+YlxwDailyStones(R.reward.spiritStones,a.realm)*.1+', 1, '==', ''),
        ('F2b·排序比较项已走实发值',
         'return(E.reward.exp||0)+YlxwDailyStones(E.reward.spiritStones,a.realm)*.1+', 1, '==', ''),
        ('F2b·旧排序键已清零',
         'const k=(R.reward.exp||0)+(R.reward.spiritStones||0)*.1+', 0, '==', ''),

        # ---- 基线未被破坏 ----
        ('基线·仙务枢纽入口未动', 'function YlxwHub({ isOpen: t, onClose: r, player: a }) {', 1, '==', ''),
        ('基线·YXW 页签总数 23', 'YLXW_COMP = { mail: YlxwTMail', 1, '==', ''),
        ('基线·秘境每日限制模块未动', 'async function YlxwDungeonEntryGate() {', 1, '==', '0.8.5 成果'),
        ('基线·Xc 403 语义未动', 'if(v.status===401||v.status===403)', 1, '==', '本模块绕开它，不改它'),
    ]
    return gates
