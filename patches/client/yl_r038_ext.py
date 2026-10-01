# -*- coding: utf-8 -*-
r"""
yl_r038_ext.py — R-038 新建角色「天赋选择页」彻底重构（含 R-038b 稀有度/颜色按数值重配）

需求原文（台账逐字）
--------------------------------------------------------------------------
  新建角色时选择天赋页面彻底重构，现在的天赋数量足够了。做以下修改：
  1. 有一点 bug 需要求，把需求为 6 点的天赋改成红色字体以及红色边框。
  2. 天赋一个人初始有 6 个天赋，完全随机分配，去掉命运点这种方式。
     新建时候 6 个天赋，随机分配，可以点击刷新天赋，刷新时可加锁，
     最多加锁 3 个天赋。

后续追加（2026-10-01 用户 R-038b，附图：6 点/8 点全是红字红框、没有金色）
--------------------------------------------------------------------------
  > 天赋的颜色弄错了，怎么 6 点 8 点全部都是红色，之前的金色我没刷到，
  > 把这些根据数值高低完全重新配置稀有度和颜色。刷新还是完全随机。

⇒ 四件事
  ① **（R-038b 取代旧①）** 天赋的**稀有度与颜色**改为**按 effects 的数值强度评分动态分档**：
     灰(普通)/蓝(稀有)/紫(传说)/**金(史诗)**/红(仙品) 五档，金色真实存在且刷得到。
     旧①「`fateCost >= 6` 一刀切判红」**已删除**（正是它导致 25 个 6/8 点天赋全红、无金色）。
  ② 初始 6 个天赋**完全随机分配**，**去掉「命运点」整套选购机制**
  ③ **「刷新天赋」**重掷未锁定的；**刷新时可加锁，最多锁 3 个**（锁住的刷新不变）
  ④ 刷新**仍完全随机**：`YLXW_R38_WEIGHT` 全 1，**未动**

侦察（产物 build/assets/index-v26m-20260927.js 逐字实证）
--------------------------------------------------------------------------
  天赋数据表：`Un=[{"id":"nt-31",...,"fateCost":1,...}, ...]`
    · 全文 `"fateCost":` 共 **132** 处（即 132 个天赋条目）；取值 1/2/4/6/8
    · 表体（effects / fateCost 数值）本模块**一字不动**（见冻结门禁）
    · 稀有度字段 `rarity` 现有值：普通36(1点) / 稀有34(2点) / 传说27(4点) /
      史诗15(6点) / 仙品20(6点10个+8点10个) ⇒ **6 点同时是「仙品」和「史诗」**（体系混乱）

  稀有度颜色函数（**本模块不碰**，避免污染日常任务卡等其它 UI）：
    `_t=t=>{switch(t){case"稀有":return"text-blue-400";case"传说":return"text-purple-400";case"仙品":return"text-yellow-400";default:return"text-stone-300"}}`
    `Qm=t=>{...bg-*-900/40 text-*-300 border-*-700...}`
    · 二者**只服务死代码**：`_t(t.rarity)`/`Qm(t.rarity)` 各 1 处在旧天赋池卡 `sw`（R-038 已下线），
      另 1 处 `_t(t.rarity)` 属日常任务卡 `qM`（另一领域，勿动）。
    ⇒ 本模块**自建** `YlxwR38Color(rar)`，只服务天赋卡，**不改 `_t`/`Qm`**。

  建号向导组件：`rw=({onStart:t})=>{...}`（offset ≈ 482.7k）
    步骤 state：`const[r,a]=O.useState(0)` → 0 道号 / 1 天赋 / 2 难度
    已选天赋：`const[d,u]=O.useState([])` —— `d` = 天赋 id 数组（存档口径就是它）
    分类过滤：`[f,v]=O.useState("全部")`
    已用点数：`S=hy(d)`（Σ fateCost）；剩余：`x=xy(d)`（`xy(t){return Wl-hy(t)}`）
    随机函数：`h=()=>{const D=F3(Wl);u(D)}`
    下一步  ：`E=()=>{if(r===0){...a(1);return}if(r===1){...a(2);return}}`
    确认建号：`k=()=>{...t(l.trim(),d,m)}`

  ★ `F3(t)` 原本是什么（**已读实现，非猜测**，offset ≈ 473683）：
      `function F3(t){const r=[];let a=t;const l=[...Un],
        c={普通:40,稀有:30,传说:20,仙品:10},
        d=f=>{...按 c[rarity] 加权抽一个...};
       let u=!1;
       for(;a>0&&l.length>0;){const f=l.filter(j=>!(j.fateCost>a));if(!f.length)break;
         const v=d(f);if(!v)break;r.push(v.id),a-=v.fateCost; ...l.splice(移除)}return r}`
    ⇒ 它是「**按稀有度加权、在不超预算的前提下**贪心抽若干条」，
      **不是**「固定抽 6 条」：预算 `Wl`（`const Wl=200`，offset ≈ 244596）越大抽得越多。
      所以不能直接复用 —— 本模块自带 `YlxwR38Roll`（同样稀有度加权，但**恰好 6 条**）。

  「命运点」UI 共 5 处（全文 `命运点` == 5）：
    474760 `K3`（进度条 `children:"命运点"`）
    481175 `aw`（`children:["已用 ",r,"/",a," 命运点"]`）
    483339 `$`（拦截 `if(S+Q.fateCost>Wl){Je("命运点不足，无法选择此天赋！");return}`）
    488032 步骤 1 副标题 `"消耗命运点来赋予角色独特的天赋能力"`
    488565 步骤 1 尾注 `"* 天赋在游戏开始后不可修改，请谨慎分配命运点"`

R-038b 数值强度评分（★ 评分公式，另见 报告_R038天赋稀有度重配_20261001.md）
--------------------------------------------------------------------------
  评分 = Σ_i  value_i × w_i      ，w_i = 1 / max_i（该属性**全表最大值**，即「满值 = 1.0」）
  量纲归一化后不同属性可比；负向词条（`defense:-10` / `hp:-100` / `speed:-8`）自然扣分。

    attack      max 150    w = 0.00666667
    defense     max 120    w = 0.00833333
    hp          max 400    w = 0.0025
    spirit      max  96    w = 0.01041667
    physique    max  96    w = 0.01041667
    speed       max  96    w = 0.01041667
    luck        max 120    w = 0.00833333
    expRate     max 0.6    w = 1.66666667
    critChance  max 0.48   w = 2.08333333
    critDamage  max 1.2    w = 0.83333333

  档位（沿用游戏既有稀有度词，不新造）：分值区间 → 稀有度 → 颜色
    [0.00, 0.30) 普通 灰   n=46    text-stone-300 / border-stone-600 bg-stone-800
    [0.30, 0.70) 稀有 蓝   n=30    text-blue-400  / border-blue-700 bg-blue-900/20
    [0.70, 1.30) 传说 紫   n=31    text-purple-400/ border-purple-700 bg-purple-900/20
    [1.30, 2.20) 史诗 金★  n=16    text-amber-400 / border-amber-600 bg-amber-900/20
    [2.20, ∞)    仙品 红   n=9     text-red-400   / border-red-500 bg-red-900/20
  ★ 全部颜色类已 Grep 产物 CSS（`build/assets/index-ZuV-l8Gt.css`）**确认存在**，不新造 class。

  为什么走「渲染层动态算」而不改 `Un` 表 132 条 `rarity`：
    · 132 条逐条改 ⇒ 132 次 replace，锚点/门禁风险极高，且要撞 `"fateCost":` 冻结计数面；
    · 渲染层只加 1 个纯函数 + 1 个取色函数，**数据表一字不动**（fateCost/effects 全冻结），
      天然满足「稀有度是展示用、不改点数不改数值」；
    · 分档与配色**单点可调**（只改 `YLXW_R38_THRESH` 一行即可整体平移），便于后续配平。

本模块动作（1 处注入 + 8 处就地替换，锚点全部唯一）
--------------------------------------------------------------------------
  注入块（插在 `const K3=({used:t,total:r})=>{` 之前，与天赋页同一作用域）：
    · `YlxwR38StatW` 表 + `YlxwR38Score/Tier/Color` —— 评分 → 档位 → 颜色
    · `YlxwR38Roll(pool,n,fixedIds)` —— 稀有度加权、**不重复**、恰好 n 条；fixedIds 保留
    · `YlxwR38Roll6()` —— `Un` 里随机 6 条（建号时调用）
    · `YlxwR38Card` —— 单张天赋卡；**颜色 = 评分档位**（名字 / 稀有度 chip / 卡框三处同色）
    · `YlxwR38TalentStep` —— 步骤 1 新 UI：6 张卡 + 每张「锁定/已锁定」+「刷新天赋」按钮
      （锁状态 = 组件本地 `O.useState`，**不落存档字段**；锁上限 3，第 4 个点不动并提示）

  替换：
    A. `E()` 的 `r===0` 分支：进天赋页前 `u(YlxwR38Roll6())` 预掷 6 个
       （⇒ 步骤 1 的 `d.length===0` 守卫、`k()` 的 `d.length===0` 守卫都照旧通过）
    B. 步骤 1 中段：`K3`(命运点条) + `J3`(分类) + `nw`(天赋池) + `aw`(已选) + `iw`(随机/清空)
       → 换成 `e.jsx(YlxwR38TalentStep,{ids:d,setIds:u})`
    C. 步骤 1 副标题：去掉「命运点」字样
    D. 步骤 1 尾注：改为「随机分配 + 刷新锁 3 个」说明
    E. `$` 里的「命运点不足」拦截 → 删除（该函数随天赋池一并成为死代码）
    F. `K3` 定义里的 `children:"命运点"` → `children:"天赋点"`（死代码去字面，便于门禁归零）
    G. `aw` 定义里的 `" 命运点"` → `" 点"`（同上）
    H. 步骤 1 主标题 `"选择你的天赋"` **不动**（只改副标题）

★ 门禁零变更（对既有模块门禁命中数**零影响**）
--------------------------------------------------------------------------
  · 已 Grep 全部 `yl_*.py` / `build_v26n.py` / `localtest/**` / `deploy_v28/**`：
    **无任何模块**把 `fateCost` / `命运点` / `K3` / `nw` / `aw` / `iw` / `J3` / `sw`
    当作锚点或门禁串 ⇒ 本模块不撞任何人的门禁。
  · `sw`(卡片) / `nw`(池) / `K3` / `J3` / `aw` / `iw` 均**只被彼此引用**（各自 `e.jsx(...)`
    全文各 1 处），改掉唯一挂载点后即成死代码 —— 按 renwu 先例**保留死代码**，只去字面。
  ⚠️ 唯一受影响的**非门禁**脚本：`localtest/prod087/prod087_check_{A,B,C}.py` 用
     `document.body.innerText.indexOf('命运点') >= 0` 当「建号页已打开」的探针 ——
     本模块把命运点 UI 下线后该探针恒为 false。**它们不在四道必跑校验内**（见交接手册 §2.6），
     需要时把探针改为 `innerText.indexOf('选择你的天赋')` 即可。

★ 装配顺序
--------------------------------------------------------------------------
  与其它模块锚区零交集（天赋建号页无任何模块触碰）。
  建议排在 `r040` 之后、**`numbal` 之前**（numbal 恒最后）。顺序无硬依赖。

服务端
--------------------------------------------------------------------------
  纯客户端。`d`（6 个天赋 id）仍按原路径经 `t(l.trim(),d,m)` 交给建号回调，
  存档字段**不变**（`player.talents` 之类由既有逻辑写）。**不新建 srv_patch_*，不改服务端。**

导出符号（构建侧契约）
  INJECT_JS : str
  apply(p, ctx) -> list[(name, needle, expect, cmp, note)]
"""

import re

# ---------------------------------------------------------------- 注入代码
# 中文可直写；build 侧统一走 zh() 转义为 \uXXXX 后落盘（与本文件内其它 v28 模块一致）。
# ★ 注入块内不得含 V28_BAN_PATTERNS：iframe / postMessage / XMLHttpRequest / auth_token / X-YL-

INJECT_JS = r'''/* ===== yl-r038 R-038 新建角色·天赋页重构 =====
   ① R-038b：天赋稀有度/颜色按「数值强度评分」动态分档（灰/蓝/紫/金/红 五档，金色真实存在）
   ② 去掉「命运点」选购机制；建号时随机分配 6 个天赋
   ③ 「刷新天赋」重掷未锁定的；最多锁定 3 个（锁住的刷新时保持不变）
   锁状态为组件本地 state，不写入存档字段。 */

/* ★ 2026-10-01 用户要求：**完全随机，不设权重**。
   原本按稀有度加权（40/30/20/10）⇒ 刷出仙品只有 10% 太难。
   现全置 1 ⇒ 等概率。结构保留（加权抽取器退化为均匀），以后想改回加权只改这一行。 */
var YLXW_R38_WEIGHT = { "普通": 1, "稀有": 1, "传说": 1, "仙品": 1 };
var YLXW_R38_N = 6;
var YLXW_R38_LOCKMAX = 3;

/* ★ R-038b 数值强度评分：每属性「每点价值」= 1 / 该属性全表最大值（满值 = 1.0）。
   量纲不同的词条（hp 几十~几百、expRate 0.03~0.6 …）折算后可直接相加。 */
var YLXW_R38_STATW = {
  attack: 0.00666667, defense: 0.00833333, hp: 0.0025,
  spirit: 0.01041667, physique: 0.01041667, speed: 0.01041667,
  luck: 0.00833333, expRate: 1.66666667,
  critChance: 2.08333333, critDamage: 0.83333333
};
/* 五档稀有度（沿用游戏既有词，不新造）+ 分值区间下界 */
var YLXW_R38_TIERS = ["普通", "稀有", "传说", "史诗", "仙品"];
var YLXW_R38_THRESH = [0.30, 0.70, 1.30, 2.20];

function YlxwR38Name(id) {
  var t = hd(id);
  return t ? t.name : id;
}
/* 数值强度评分（effects 里未知字段不计分） */
function YlxwR38Score(t) {
  var eff = (t && t.effects) || {}, s = 0, k;
  for (k in eff) { if (YLXW_R38_STATW[k]) s += (Number(eff[k]) || 0) * YLXW_R38_STATW[k]; }
  return s;
}
/* 评分 → 稀有度档位（★ 展示用，不改 Un 表里的 rarity 字段） */
function YlxwR38Tier(s) {
  for (var i = 0; i < YLXW_R38_THRESH.length; i++) { if (s < YLXW_R38_THRESH[i]) return YLXW_R38_TIERS[i]; }
  return YLXW_R38_TIERS[YLXW_R38_TIERS.length - 1];
}
/* 档位 → 颜色（★ 全部为产物 CSS 已编译的 Tailwind 类，不新造 class） */
function YlxwR38Color(rar) {
  switch (rar) {
    case "稀有": return { name: "text-blue-400", chip: "bg-blue-900/40 text-blue-300 border-blue-700", card: "border-blue-700 bg-blue-900/20" };
    case "传说": return { name: "text-purple-400", chip: "bg-purple-900/40 text-purple-300 border-purple-700", card: "border-purple-700 bg-purple-900/20" };
    case "史诗": return { name: "text-amber-400", chip: "bg-amber-900/40 text-amber-300 border-amber-600", card: "border-amber-600 bg-amber-900/20" };
    case "仙品": return { name: "text-red-400", chip: "bg-red-950/40 text-red-400 border-red-500", card: "border-red-500 bg-red-900/20" };
    default: return { name: "text-stone-300", chip: "bg-stone-700 text-stone-400 border-stone-600", card: "border-stone-600 bg-stone-800" };
  }
}
/* 稀有度加权、不重复地随机取 n 条；fixedIds 原样保留（刷新时锁定的那几条） */
function YlxwR38Roll(pool, n, fixedIds) {
  var out = [], seen = {}, i, k;
  for (i = 0; i < (fixedIds || []).length && out.length < n; i++) {
    if (!seen[fixedIds[i]]) { seen[fixedIds[i]] = 1; out.push(fixedIds[i]); }
  }
  var cand = [];
  for (i = 0; i < pool.length; i++) { if (!seen[pool[i].id]) cand.push(pool[i]); }
  while (out.length < n && cand.length > 0) {
    var total = 0;
    for (k = 0; k < cand.length; k++) total += (YLXW_R38_WEIGHT[cand[k].rarity] || 1);
    var roll = Math.random() * total, pick = cand.length - 1;
    for (k = 0; k < cand.length; k++) {
      roll -= (YLXW_R38_WEIGHT[cand[k].rarity] || 1);
      if (roll <= 0) { pick = k; break; }
    }
    out.push(cand[pick].id);
    cand.splice(pick, 1);
  }
  return out;
}
/* 新建角色时：从全表随机 6 条 */
function YlxwR38Roll6() {
  return YlxwR38Roll(Un, YLXW_R38_N, []);
}
/* 单张天赋卡：稀有度与颜色按「数值强度评分」动态分档（灰→蓝→紫→金→红） */
function YlxwR38Card(props) {
  var t = props.talent, locked = props.locked, onLock = props.onLock;
  var sc = YlxwR38Score(t);
  var rar = YlxwR38Tier(sc);
  var col = YlxwR38Color(rar);
  var effs = Object.entries(t.effects || {}).filter(function (kv) { return kv[1] !== void 0 && kv[1] !== 0; });
  var cardCls = col.card + (locked ? " ring-2 ring-amber-400" : "");
  var nameCls = col.name;
  var chipCls = col.chip;
  var costCls = "border-stone-600 bg-stone-950/60 text-stone-300";
  return e.jsxs("div", { className: "relative flex min-h-[126px] flex-col rounded-lg border-2 p-3 transition-all duration-200 select-none " + cardCls, title: "数值强度 " + sc.toFixed(2) + " · " + rar, children: [
    e.jsxs("div", { className: "mb-2 flex items-start justify-between gap-2", children: [
      e.jsxs("div", { className: "flex min-w-0 items-start gap-1.5", children: [
        e.jsx("span", { className: "break-words text-sm font-bold leading-tight " + nameCls, children: t.name }),
        t.specialAbility ? e.jsx(aa, { size: 13, className: "mt-0.5 flex-shrink-0 fill-amber-400 text-amber-400" }) : null
      ] }),
      e.jsxs("span", { className: "flex-shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-bold " + costCls, children: [t.fateCost, "点"] })
    ] }),
    e.jsxs("div", { className: "mb-2 flex items-center gap-1.5 flex-wrap", children: [
      e.jsx("span", { className: "px-1.5 py-0.5 text-[10px] font-medium rounded border bg-stone-800/80 text-stone-400 border-stone-600", children: t.category }),
      e.jsx("span", { className: "px-1.5 py-0.5 text-[10px] font-medium rounded border " + chipCls, children: rar })
    ] }),
    effs.length > 0 ? e.jsx("div", { className: "mt-auto grid grid-cols-1 gap-x-2 gap-y-0.5 border-t border-stone-700/50 pt-1.5 min-[420px]:grid-cols-2", children: effs.map(function (kv) {
      var Ic = tw[kv[0]] || jt;
      return e.jsxs("div", { className: "flex min-w-0 items-center gap-1", children: [
        e.jsx(Ic, { size: 11, className: "text-stone-500 flex-shrink-0" }),
        e.jsx("span", { className: "text-[11px] text-stone-500 truncate", children: Y3(kv[0]) }),
        e.jsx("span", { className: "text-[11px] font-medium text-emerald-400 ml-auto", children: X3(kv[0], kv[1]) })
      ] }, kv[0]);
    }) }) : null,
    t.description ? e.jsx("p", { className: "mt-1.5 text-[10px] text-stone-500 leading-relaxed line-clamp-2", children: t.description }) : null,
    e.jsx("button", {
      onClick: function () { onLock(t.id); },
      className: "mt-2 self-start rounded border px-2 py-1 text-[10px] font-bold " + (locked ? "border-amber-500 bg-amber-900/30 text-amber-300" : "border-stone-600 bg-stone-900/60 text-stone-400 hover:text-stone-200 hover:border-stone-500"),
      children: locked ? "已锁定" : "锁定"
    })
  ] });
}
/* 步骤 1：6 个随机天赋 + 锁定 + 刷新（锁状态仅本地 state，不入存档） */
function YlxwR38TalentStep(props) {
  var ids = props.ids || [], setIds = props.setIds;
  var s1 = O.useState([]), locks = s1[0], setLocks = s1[1];
  var s2 = O.useState(""), msg = s2[0], setMsg = s2[1];

  function toggleLock(id) {
    if (locks.indexOf(id) >= 0) {
      setLocks(locks.filter(function (x) { return x !== id; }));
      setMsg("已解锁【" + YlxwR38Name(id) + "】。");
      return;
    }
    if (locks.length >= YLXW_R38_LOCKMAX) {
      var full = "最多只能锁定 " + YLXW_R38_LOCKMAX + " 个天赋，请先解锁一个。";
      setMsg(full);
      Je(full);
      return;
    }
    setLocks(locks.concat([id]));
    setMsg("已锁定【" + YlxwR38Name(id) + "】，刷新时保持不变。");
  }
  function refresh() {
    var keep = locks.filter(function (id) { return ids.indexOf(id) >= 0; });
    setIds(YlxwR38Roll(Un, YLXW_R38_N, keep));
    setMsg(keep.length > 0 ? ("已刷新天赋，保留锁定 " + keep.length + " 个。") : "已刷新天赋。");
  }

  var cards = [];
  for (var i = 0; i < ids.length; i++) {
    (function (id) {
      var t = hd(id);
      if (!t) return;
      cards.push(e.jsx(YlxwR38Card, { talent: t, locked: locks.indexOf(id) >= 0, onLock: toggleLock }, "ylxw-r38-" + id));
    })(ids[i]);
  }

  return e.jsxs("div", { className: "space-y-3", children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      e.jsxs("span", { className: "text-xs text-stone-400", children: ["已随机分配 ", ids.length, " 个天赋（已锁定 ", locks.length, "/", YLXW_R38_LOCKMAX, "）"] }),
      e.jsx("button", {
        onClick: refresh,
        className: "px-3 py-1.5 rounded-lg text-sm font-medium bg-amber-500/15 text-amber-400 border border-amber-500/40 hover:bg-amber-500/25 hover:border-amber-500/60 active:scale-95 transition-all duration-150",
        children: "刷新天赋"
      })
    ] }),
    e.jsx("div", { className: "grid grid-cols-1 min-[560px]:grid-cols-2 lg:grid-cols-3 gap-3", children: cards }),
    e.jsx("div", { className: "text-[10px] md:text-xs text-stone-500", children: "刷新会重掷未锁定的天赋；已锁定的天赋保持不变（最多锁定 3 个）。" }),
    msg ? e.jsx("div", { className: "text-[11px] text-amber-300", children: msg }) : null
  ] });
}
/* == end yl-r038 == */
'''

# ---------------------------------------------------------------- 锚点（raw 中文；产物内为 UTF-8 原文，非 \uXXXX）

# 注入锚：与天赋页同一作用域（K3 / Z3 / J3 / _t / … / rw 属同一条 const 声明链）
A_INJECT = 'const K3=({used:t,total:r})=>{'

# A. 建号向导「下一步」：r===0 分支 —— 进天赋页前预掷 6 个
A_STEP0_NEXT = 'E=()=>{if(r===0){if(!l.trim()){Je("请输入你的道号！");return}a(1);return}'
R_STEP0_NEXT = 'E=()=>{if(r===0){if(!l.trim()){Je("请输入你的道号！");return}u(YlxwR38Roll6());a(1);return}'

# B. 步骤 1 中段（命运点条 + 分类 + 天赋池 + 已选 + 随机/清空）→ 新组件
A_STEP1_MID = (
    'e.jsx(K3,{used:S,total:Wl}),e.jsx(J3,{selected:f,onSelect:v}),'
    'e.jsx("div",{className:"max-h-[260px] md:max-h-[340px] overflow-y-auto pr-1 mt-2 '
    'scrollbar-thin scrollbar-thumb-stone-600 scrollbar-track-stone-800",'
    'children:e.jsx(nw,{talents:T,selectedIds:d,remainingPoints:x,onToggle:$})}),'
    'e.jsx(aw,{selectedIds:d,totalCost:S,totalPoints:Wl,onRemove:M}),'
    'e.jsx(iw,{onRandom:h,onClear:R,hasSelection:d.length>0})'
)
R_STEP1_MID = 'e.jsx(YlxwR38TalentStep,{ids:d,setIds:u})'

# C. 步骤 1 副标题（去「命运点」字样）
A_SUB = 'children:"消耗命运点来赋予角色独特的天赋能力"'
R_SUB = 'children:"天赋将随机分配，可刷新并锁定心仪的天赋"'

# D. 步骤 1 尾注（去「命运点」字样）
A_TAIL = ('e.jsx("p",{className:"text-[10px] md:text-xs text-stone-500 text-center",'
          'children:"* 天赋在游戏开始后不可修改，请谨慎分配命运点"})')
R_TAIL = ('e.jsx("p",{className:"text-[10px] md:text-xs text-stone-500 text-center",'
          'children:"* 天赋将随机分配，可刷新并在刷新时锁定最多 3 个；游戏开始后不可修改"})')

# E. `$` 内的「命运点不足」拦截（该函数随天赋池一并成为死代码）
A_INTERCEPT = 'if(S+Q.fateCost>Wl){Je("命运点不足，无法选择此天赋！");return}'
R_INTERCEPT = ''

# F. K3 定义里的「命运点」标签（死代码去字面，便于门禁归零）
A_K3_LABEL = 'children:"命运点"'
R_K3_LABEL = 'children:"天赋点"'

# G. aw 定义里的「已用 r/a 命运点」标签（死代码去字面）
A_AW_LABEL = 'children:["已用 ",r,"/",a," 命运点"]'
R_AW_LABEL = 'children:["已用 ",r,"/",a," 点"]'

# 注入块禁用模式（与 build_v26n.V28_BAN_PATTERNS + 既有模块自检口径一致）
BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']


# ---------------------------------------------------------------- 应用

def apply(p, ctx):
    """把 R-038 落到 Patcher 上；返回 gates 列表。"""
    zh = ctx['zh']

    # 0) 注入块硬断言：zh() 后纯 ASCII + 无禁用模式 + 关键常量自检
    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r038 注入块 zh() 后仍含非 ASCII: %r' % (bad[:10],))
    for pat in BAN_PATTERNS:
        if pat in blk:
            raise AssertionError('r038 注入块含禁用模式: %s' % pat)
    assert 'var YLXW_R38_N = 6;' in blk, 'r038 注入块缺少 6 个天赋常量'
    assert 'var YLXW_R38_LOCKMAX = 3;' in blk, 'r038 注入块缺少锁上限常量'
    assert 'var YLXW_R38_STATW = {' in blk, 'r038 注入块缺少评分权重表'
    assert 'var YLXW_R38_THRESH = [0.30, 0.70, 1.30, 2.20];' in blk, 'r038 注入块缺少档位分值区间'

    # 1) 注入块：评分/档位/配色 + 新卡片组件 + 步骤 1 组件 + 随机函数（插在 const K3 之前，同作用域）
    p.insert_before(
        'r038-block', A_INJECT, blk + '\n', expect=1,
        note='R-038b：YlxwR38Score/Tier/Color（按数值强度分 5 档配色）+ 卡片/步骤组件 + 6 随机+刷新+锁≤3'
    )

    # 2) A：建号「下一步」r===0 分支预掷 6 个（保证步骤 1 的 d.length 守卫照旧通过）
    p.replace(
        'r038-preroll', A_STEP0_NEXT, R_STEP0_NEXT, expect=1,
        note='R-038 进天赋页前 u(YlxwR38Roll6()) 预掷 6 个天赋'
    )

    # 3) B：步骤 1 中段 → 新组件（命运点条/分类/天赋池/已选/随机清空 一并下线）
    p.replace(
        'r038-step1', A_STEP1_MID, R_STEP1_MID, expect=1,
        note='R-038 步骤 1 换成 YlxwR38TalentStep（去命运点选购，改随机+刷新+锁）'
    )

    # 4) C：副标题去「命运点」
    p.replace('r038-sub', A_SUB, R_SUB, expect=1,
              note='R-038 步骤 1 副标题去「命运点」字样')

    # 5) D：尾注去「命运点」并写明刷新/锁规则
    p.replace('r038-tail', A_TAIL, R_TAIL, expect=1,
              note='R-038 步骤 1 尾注改为「随机分配 + 刷新锁 3 个」')

    # 6) E：删除「命运点不足」拦截
    p.replace('r038-intercept', A_INTERCEPT, R_INTERCEPT, expect=1,
              note='R-038 去掉「命运点不足」拦截（该函数随天赋池成为死代码）')

    # 7) F：K3 定义里的「命运点」标签去字面（死代码）
    p.replace('r038-k3label', A_K3_LABEL, R_K3_LABEL, expect=1,
              note='R-038 死代码 K3 去「命运点」字面（便于门禁归零）')

    # 8) G：aw 定义里的「命运点」标签去字面（死代码）
    p.replace('r038-awlabel', A_AW_LABEL, R_AW_LABEL, expect=1,
              note='R-038 死代码 aw 去「命运点」字面（便于门禁归零）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 注入块本体 =================
        ('R38·步骤组件已注入',   'function YlxwR38TalentStep(',        1, '==', ''),
        ('R38·卡片组件已注入',   'function YlxwR38Card(',              1, '==', ''),
        ('R38·随机函数已注入',   'function YlxwR38Roll(',              1, '==', ''),
        ('R38·6 条随机入口',     'function YlxwR38Roll6(',             1, '==', ''),
        ('R38·6 个天赋常量',     'var YLXW_R38_N = 6;',                1, '==', ''),
        ('R38·锁上限 = 3',       'var YLXW_R38_LOCKMAX = 3;',          1, '==', ''),
        ('R38·稀有度权重表',     'var YLXW_R38_WEIGHT = {',            1, '==', ''),
        ('R38·★完全随机（权重全 1）', 'YLXW_R38_WEIGHT = { ', 1, '==', '★ 纯 ASCII 锚点：zh() 会把中文转 \\uXXXX，裸中文匹不上'),
        ('R38·旧加权值已清零',     '": 40, ',  0, '==', '旧权重 40/30/20/10 已作废（纯 ASCII 锚点）'),
        ('R38·新权重值全 1',        '": 1 };', 1, '==', '★ 纯 ASCII 尾部锚点（最后一项的尾巴，唯一）'),
        ('R38·兼底也是 1',        'YLXW_R38_WEIGHT[cand[k].rarity] || 1', 2, '==', '未知稀有度不能被放大'),
        ('R38·注入块结束标记',   '/* == end yl-r038',                  1, '==', ''),
        # ================= ① R-038b 数值强度评分 → 五档配色 =================
        ('R38·评分权重表已注入',   'var YLXW_R38_STATW = {',            1, '==', '★ 每点价值 = 1 / 该属性全表最大值'),
        ('R38·五档稀有度表',       zh('var YLXW_R38_TIERS = ["普通", "稀有", "传说", "史诗", "仙品"];'), 1, '==', '★ 沿用游戏既有词，不新造'),
        ('R38·分值区间(4 条分界)', 'var YLXW_R38_THRESH = [0.30, 0.70, 1.30, 2.20];', 1, '==', '灰/蓝/紫/金/红 分界'),
        ('R38·评分函数',           'function YlxwR38Score(',             1, '==', ''),
        ('R38·分档函数',           'function YlxwR38Tier(',              1, '==', ''),
        ('R38·配色函数',           'function YlxwR38Color(',             1, '==', ''),
        ('R38·评分公式(加权求和)', 'YLXW_R38_STATW[k]) s += (Number(eff[k]) || 0) * YLXW_R38_STATW[k];', 1, '==', 'Σ value×w'),
        ('R38·卡片按评分取档',     'var rar = YlxwR38Tier(sc);',         1, '==', ''),
        ('R38·卡片取色',           'var col = YlxwR38Color(rar);',       1, '==', ''),
        ('R38·卡片用动态档色',     'var cardCls = col.card + (locked ?', 1, '==', '卡框随档位'),
        ('R38·稀有度 chip 用档色', 'children: rar })',                   1, '==', 'chip 文案 = 动态档位名'),
        ('R38·点数徽标改中性色',   'var costCls = "border-stone-600 bg-stone-950/60 text-stone-300";', 1, '==', '★ 点数徽标不再按点数染红'),
        ('R38·卡片 tooltip 带强度', zh('数值强度 '),                     1, '==', '悬停可见分值'),
        # ---- 五档颜色（★ 全部经产物 CSS 确认存在）----
        ('R38·灰档(普通)存在',     'chip: "bg-stone-700 text-stone-400 border-stone-600"', 1, '==', ''),
        ('R38·蓝档(稀有)存在',     zh('case "稀有": return { name: "text-blue-400"'), 1, '==', '★ zh() 转义：档位名是中文'),
        ('R38·紫档(传说)存在',     zh('case "传说": return { name: "text-purple-400"'), 1, '==', ''),
        ('R38·★金档(史诗)存在',   zh('case "史诗": return { name: "text-amber-400"'), 1, '==', '★ 用户要的金色：必须真存在'),
        ('R38·金档卡框存在',       'card: "border-amber-600 bg-amber-900/20"', 1, '==', 'border-amber-600 已确认在产物 CSS'),
        ('R38·红档(仙品)存在',     zh('case "仙品": return { name: "text-red-400"'), 1, '==', ''),
        ('R38·红档卡框存在',       'card: "border-red-500 bg-red-900/20"', 1, '==', ''),
        ('R38·锁定态用 ring',      '(locked ? " ring-2 ring-amber-400" : "")', 1, '==', '★ 原产物 sw 卡已有同类串，须用本模块特有形态'),
        # ---- 旧「按点数一刀切判红」彻底下线 ----
        ('R38·旧「6 点判红」已清零', 'Number(t.fateCost) || 0) >= 6',    0, '==', '★ 旧一刀切逻辑删除（正是它导致无金色）'),
        ('R38·旧红字回退已清零',   'text-red-400" : _t(t.rarity)',       0, '==', ''),
        ('R38·旧锁色已清零',       'locked ? "border-amber-500 bg-amber-950/30" : "border-stone-600 bg-stone-800"', 0, '==', '★ 原产物 sw 卡另有同色串，故用旧卡片整段形态'),
        ('R38·旧「红判定」变量已清零', 'var red = (Number(t.fateCost)',   0, '==', ''),
        # ================= ② 6 个随机 + 去命运点 =================
        ('R38·进天赋页预掷 6 个', 'u(YlxwR38Roll6());a(1);return}',     1, '==', ''),
        ('R38·步骤 1 已换新组件', 'e.jsx(YlxwR38TalentStep,{ids:d,setIds:u})', 1, '==', ''),
        ('R38·副标题已改',        'children:"天赋将随机分配，可刷新并锁定心仪的天赋"', 1, '==', ''),
        ('R38·尾注已改',          '* 天赋将随机分配，可刷新并在刷新时锁定最多 3 个',   1, '==', ''),
        ('R38·随机分配 6 条',     'YlxwR38Roll(Un, YLXW_R38_N, keep)', 1, '==', '刷新时保留锁定项'),
        ('R38·命运点全文清零',    '命运点',                             0, '==', '★ 旧机制彻底下线'),
        ('R38·命运点不足已清零',  '命运点不足',                         0, '==', '拦截逻辑删除'),
        ('R38·旧命运点条已下线',  'e.jsx(K3,{used:S,total:Wl})',        0, '==', ''),
        ('R38·旧分类条已下线',    'e.jsx(J3,{selected:f,onSelect:v})',  0, '==', ''),
        ('R38·旧天赋池已下线',    'e.jsx(nw,{talents:T,selectedIds:d',  0, '==', ''),
        ('R38·旧已选面板已下线',  'e.jsx(aw,{selectedIds:d,totalCost:S', 0, '==', ''),
        ('R38·旧随机/清空已下线', 'e.jsx(iw,{onRandom:h,onClear:R',     0, '==', ''),
        ('R38·「清空重选」仅剩死代码', '清空重选',                       1, '==', 'iw 组件定义保留（已无挂载点）'),
        # ================= ③ 刷新 + 加锁（≤3） =================
        ('R38·刷新按钮',          zh('children: "刷新天赋"'),           1, '==', ''),
        ('R38·锁定/解锁按钮',     zh('children: locked ? "已锁定" : "锁定"'), 1, '==', '卡片按钮文案'),
        ('R38·锁上限提示',        zh('最多只能锁定 '),                   1, '==', '第 4 个点不动并提示'),
        ('R38·已锁定计数',        zh('已随机分配 '),                     1, '==', ''),
        ('R38·锁状态为本地 state', 'O.useState([]), locks = s1[0]',      1, '==', '★ 不入存档字段'),
        ('R38·刷新保留锁定项',    'locks.filter(function (id) { return ids.indexOf(id) >= 0; })', 1, '==', ''),
        # ================= 冻结：建号流程不得破坏 =================
        ('冻结·道号输入提示',      '请输入你的道号！',                    1, '==', ''),
        ('冻结·天赋/难度守卫',     '请至少选择一个天赋，或使用随机分配！',  2, '==', 'E() 与 k() 各 1'),
        ('冻结·建号确认提示',      '请输入修仙者名称！',                  1, '==', ''),
        ('冻结·建号回调未动',      't(l.trim(),d,m)',                    1, '==', 'd 仍原样交给 onStart'),
        ('冻结·步骤 1 主标题未动', '选择你的天赋',                       1, '==', '只改副标题'),
        ('冻结·步骤 0 标题未动',   '为你的修仙者取名',                   1, '==', ''),
        ('冻结·步骤 2 标题未动',   '选择游戏难度',                       1, '==', ''),
        ('冻结·副标题(踏长生路)',  '踏上你的长生之路',                    2, '==', ''),
        # ================= 冻结：天赋数据表 / 数值一字未动 =================
        ('冻结·天赋表入口未动',    'Un=[{"id":"nt-31"',                  1, '==', ''),
        ('冻结·fateCost 字段数恒定', '"fateCost":',                      132, '==', '★ 132 个天赋条目，一个没增没减'),
        ('冻结·nt-37 数值未动',    '"rarity":"史诗","fateCost":6,"effects":{"physique":64,"defense":80}', 1, '==', '★ 数据表原样（含旧 rarity 值，本模块不改表）'),
        ('冻结·F3 实现未动',       'function F3(t){const r=[];let a=t;', 1, '==', '旧随机函数保留（已成死代码）'),
        ('冻结·Wl 预算未动',       'const Wl=200;',                      1, '==', ''),
        ('冻结·hd 映射未动',       'function hd(t){return Un.find(r=>r.id===t)}', 1, '==', ''),
        ('冻结·sw 卡片定义仍在',   'sw=({talent:t,selected:r,canAfford:a,onToggle:l})', 1, '==', '死代码保留证据'),
        ('冻结·nw 天赋池定义仍在', 'nw=({talents:t,selectedIds:r,remainingPoints:a,onToggle:l})', 1, '==', '死代码保留证据'),
        ('冻结·K3 定义仍在',       'const K3=({used:t,total:r})=>{',     1, '==', '死代码保留证据（仅去字面）'),
        ('冻结·rw 建号组件仍在',   'rw=({onStart:t})=>{const[r,a]=O.useState(0)', 1, '==', ''),
        ('冻结·_t 稀有度色函数未动', 'case"仙品":return"text-yellow-400"', 1, '==', '★ 不碰全局 _t（日常任务卡等共用）'),
        ('冻结·Qm 徽标色函数未动',   'case"仙品":return"bg-yellow-900/40 text-yellow-300 border-yellow-700"', 1, '==', '★ 不碰全局 Qm'),
    ]
    return gates


# ---------------------------------------------------------------- 自检（python yl_r038_ext.py）

if __name__ == '__main__':
    import io
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from yl_patch import Patcher, Gates, zh  # noqa: E402

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    HERE = os.path.dirname(os.path.abspath(__file__))
    os.chdir(HERE)

    # ★ 基线 = 链跑到「本模块之前」的中间产物。
    #   本模块应排在 numbal 之前；若已接线则从 'r038' 处切，否则从 'numbal' 处切。
    #   （只读内存，不落盘 —— 不触碰 build/assets 里的共享产物。）
    import build_v26n as B  # noqa: E402
    _saved = B.V28_MODULES
    _names = [n for n, _ in _saved]
    if 'r038' in _names:
        _cut = _names.index('r038')
    elif 'numbal' in _names:
        _cut = _names.index('numbal')
    else:
        _cut = len(_names)
    B.V28_MODULES = _saved[:_cut]
    try:
        _base_in = io.open(B.BASE, encoding='utf-8').read()
        base, _ = B.build(_base_in)
    finally:
        B.V28_MODULES = _saved
    print('=== r038 自检：基线 = 链跑到 r038 之前（%d chars，前置 %d 模块）'
          % (len(base), _cut))

    # 改前锚点份数断言（本模块锚点均为 raw 中文/ASCII，不做 zh()）
    print('=== 改前锚点份数 ===')
    pre = [
        ('A_INJECT', A_INJECT, 1),
        ('A_STEP0_NEXT', A_STEP0_NEXT, 1),
        ('A_STEP1_MID', A_STEP1_MID, 1),
        ('A_SUB', A_SUB, 1),
        ('A_TAIL', A_TAIL, 1),
        ('A_INTERCEPT', A_INTERCEPT, 1),
        ('A_K3_LABEL', A_K3_LABEL, 1),
        ('A_AW_LABEL', A_AW_LABEL, 1),
    ]
    bad = 0
    for name, s, exp in pre:
        n = base.count(s)
        ok = n == exp
        bad += (not ok)
        print('  [%s] %-14s actual=%d expect=%d' % ('OK' if ok else 'FAIL', name, n, exp))
    if bad:
        print('  [ABORT] 改前锚点份数与设计不符（%d 条）' % bad)
        sys.exit(2)

    # ---- 档位分布自检（读 base 里的 Un 表，纯读；确认「每档都有天赋」）----
    _u = base.find('Un=[{"id":"nt-31"')
    if _u >= 0:
        _j = base.find('[', _u)
        _d = 0
        _k = _j
        _in = False
        _es = False
        while _k < len(base):
            _c = base[_k]
            if _in:
                if _es:
                    _es = False
                elif _c == '\\':
                    _es = True
                elif _c == '"':
                    _in = False
            else:
                if _c == '"':
                    _in = True
                elif _c == '[':
                    _d += 1
                elif _c == ']':
                    _d -= 1
                    if _d == 0:
                        break
            _k += 1
        import json as _json
        _arr = _json.loads(base[_j:_k + 1])
        _W = {'attack': 1 / 150.0, 'defense': 1 / 120.0, 'hp': 1 / 400.0, 'spirit': 1 / 96.0,
              'physique': 1 / 96.0, 'speed': 1 / 96.0, 'luck': 1 / 120.0,
              'expRate': 1 / 0.6, 'critChance': 1 / 0.48, 'critDamage': 1 / 1.2}
        _TH = [0.30, 0.70, 1.30, 2.20]
        _TIERS = ['普通', '稀有', '传说', '史诗', '仙品']
        _cnt = [0, 0, 0, 0, 0]
        for _it in _arr:
            _sc = sum((_v or 0) * _W[_kk] for _kk, _v in (_it.get('effects') or {}).items() if _kk in _W)
            _ti = 4
            for _i2, _t2 in enumerate(_TH):
                if _sc < _t2:
                    _ti = _i2
                    break
            _cnt[_ti] += 1
        print('=== 档位分布（%d 条天赋）===' % len(_arr))
        for _i3 in range(5):
            print('  %-4s [%s, %s)  n=%d' % (
                _TIERS[_i3],
                ('0' if _i3 == 0 else _TH[_i3 - 1]),
                (_TH[_i3] if _i3 < 4 else 'inf'), _cnt[_i3]))
        if 0 in _cnt:
            print('  [FAIL] 存在 0 个天赋的档位')
            sys.exit(3)

    print('=== 应用补丁（内存副本，不写盘）===')
    pt = Patcher(base, label='r038-selfcheck')
    gts = apply(pt, {'zh': zh, 'base_text': base})
    print(pt.report())

    g = Gates(pt.text)
    for t in gts:
        name, s, expect, cmp, note = t[:5]
        g.check(name, s, expect, cmp, note, within=(t[5] if len(t) > 5 else None))
    print(g.report())
    ok = g.passed()
    print('门禁结果: %s' % ('PASS' if ok else 'FAIL'))

    # node --check 产物级语法校验
    if ok:
        import subprocess
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), 'yl_r038_selfcheck.js')
        with open(tmp, 'w', encoding='utf-8', newline='') as f:
            f.write(pt.text)
        try:
            r1 = subprocess.run(['node', '--check', tmp], capture_output=True, text=True, timeout=300)
            print('=== node --check 补丁后 rc=%s' % r1.returncode)
            if r1.returncode != 0:
                print(r1.stderr[:2000])
                ok = False
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    print('自检结论: %s' % ('PASS' if ok else 'FAIL'))
    sys.exit(0 if ok else 1)
