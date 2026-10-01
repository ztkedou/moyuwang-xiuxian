# -*- coding: utf-8 -*-
r"""
yl_v2810e_ext.py — 0.8.10 补丁 e（客户端单模块）

接线：V28_MODULES 插在 pet089 / farm089 … 之后、**numbal 之前**（numbal 恒最后）。
      `_t_mod.py` 的自测位置与此等价。
落点：**只新建本文件**；不写 build/assets/、不改 build_v26n.py。

=========================================================================== 任务 A
「信箱增加删除邮件功能及相关设定」

服务端契约（lead 已定，本模块只做客户端一半）
--------------------------------------------------------------------------
  DELETE /api/mail/:id
    200 { ok: true, id: <number> }
    400 id 非法 / 404 邮件不存在或不属于该玩家 / 409 已领取的邮件不可删除
  鉴权与其它邮件端点一致（走 Xc，自动带 token + Authorization + revision + session）。

现状（基座 @793420 `YlxwTMail`）
--------------------------------------------------------------------------
  列表项 = `e.jsxs(YlxwRow,{children:[ <标题行>, <内容行> ]})`；标题行右侧
  `flex items-center gap-2` 里只有「时间」+「领取」两个节点，**没有删除**。

改法
--------------------------------------------------------------------------
  ① 在「领取」按钮**之后**追加一个节点
     `e.jsx(YlxwMailDelBtn,{mail:g,busy:!!u,onDone:c}, "d"+g.id)`
     —— 只往既有数组追加，「领取」与列表项结构一字不动。
  ② 二次确认沿用项目既有 `an(消息, 标题, onOk, onCancel)`（基座 @249990）——
     它就是全站 13 处在用的那个确认宿主：`xo` 已初始化时走**自绘确认弹窗**，
     否则回落 `window.confirm`。不新造弹窗、不新造 confirm。
  ③ 删除请求走 `Xc(ln + "/mail/" + id, { method: "DELETE" })`：
     `ln`（基座 @597346）= "/yl/api"；`Xc`（基座 @597944）= 全站统一鉴权 fetch 封装
     （自动拼 token / Authorization / X-YL-Base-Revision / X-YL-Session，401 自动刷新）。
     ★ 直接用 `Xc` 而**不是** `YlxwApi`：`YlxwApi` 把非 2xx 折叠成
       `new Error(body.error || "请求失败(N)")`，409/404/400 无法区分，
       而服务端 `error` 文案由服务端决定、客户端不该按文案匹配。
       `Xc` 返回**原始 Response** ⇒ 按 HTTP status 分支，语义稳定。
  ④ 成功后 `props.onDone()`（= `YlxwUseList` 的 `load`）重新拉 `/mail/list`，
     本地列表即刷新；失败按 409/404/400 给可读提示，其余走 body.error。
  ⑤ 相关设定：**已领取奖励的邮件不可删除** —— 按钮置灰（disabled）+ title 说明；
     未领取的可删，但必须过二次确认（防误删奖励）。
     409 仍做兜底提示（服务端若改口径 / 并发窗口）。

=========================================================================== 任务 B
「灵宠系统**左边的没有看到有什么变化**」

版面真相（逐字实证）
--------------------------------------------------------------------------
  用户说的「灵宠系统」= 基座 @1494808 的 modal：`ct` + `xw:"pet"` + `title:"灵宠系统"`。
  0.8.6 fun086 的 F6 把该 modal 内容区改成**两列**：
      children:__xw?e.jsxs("div",{className:"grid grid-cols-1 md:grid-cols-2 …",
        children:[e.jsx("div",{className:"min-w-0",children:e.jsx(YlxwFuse,{k:__xw})}),
                  e.jsx("div",{className:"min-w-0",children:l})]}):l
  ⇒ **左列** = `YlxwFuse({k:"pet"})` → `YlxwFuseOne("pet")` → `YLXW_COMP.pet`
     = 基座 `YlxwTPet`（仙务·妖灵，读 `GET /api/pet`）；
     **右列** = 该 modal 自己的 children（灵宠卡片列表）。
  左列当前只渲染 6 个服务端字段（名字/品阶/等级/饥饿/经验/羁绊）+「喂养」「嬉戏」
  + 行为日志 —— 没有攻击/防御/气血/速度，也没有融合入口。

  0.8.9 pet089 的扩展（`YlxwPetShell` 包壳 + 融合页签 + 秘径公式 + 妖灵归位）
  **全部落在 `jM = Rt.memo(vM)` 这条线上**，从未碰过 `YlxwTPet`
  ⇒ 这正是用户说「左边没变化」的原因。
  ★ 附带发现（本模块不修，仅记录）：pet089 的 `PetTabBar` 渲染在 `vM` **之外**，
    而 `vM` 内部的 modal 走 `Yb.createPortal(…, document.body)`
    ⇒ 页签条被弹窗遮住，「融合」页签用户**根本点不到**。

改法（最小侵入，不重写 YlxwTPet）
--------------------------------------------------------------------------
  A) 作用数值：在左列 children 数组里、喂养/嬉戏那行**之后**追加
     `m && e.jsx(YlxwTSpiritUse,{pet:m})`。
     数值**同源同公式**：物种表用右栏同一张 `rn`（`baseStats`），加成系数用 pet089 的
     `YlxwPetBonusOne` / `YlxwPetBonusCrit` / `YlxwPetBonusDodge`
     + `YLXW_PET_BONUS_RARITY` / `YLXW_PET_BONUS_STAGE` + 主战转化率
     `YLXW_PET_LANES[0].rate`。**不新造任何系数表。**
     妖灵（服务端 `/api/pet` 的 `petView`）**没有 id / species**，故：
       · 品阶映射沿用 pet089 `YLXW_PET_SPIRIT_MAP`（凡→普通 / 灵→稀有 / 传→传说 / 仙→仙品）
       · 物种按「名字+品阶」**稳定散列**从**同品阶池**里选（不用 Math.random，
         否则每次渲染数值抖动）；池的过滤口径与 `YlxwSpiritToPet` 逐字一致
       · 等级 = `floor(饥饿/100)`（= 服务端 `petLevel` 同式）；
         亲密度 = `min(100, floor(羁绊/2))`（= `YlxwSpiritToPet` 同式）
       · 本体属性 = 基座灵宠属性成长式**逐字复刻**（等级 ×1.08/×1.08/×1.08/×1.02；
         阶段1 ×4.5…×2；阶段2 ×5…×2.5）。
         ★ 原式是 hook 内的**闭包局部变量**（模块级不可达），故按同一公式复刻；
           **品阶/阶段加成系数不在此处**，仍走 pet089 同一套函数。
  B) 融合入口：左列**内联展开** —— 复用 pet089 的 `YlxwPetFuseTab` 组件 +
     它的融合执行动作 `onFuse`（把 pet089 的 `var onFuse = function (…)` 改成
     `var onFuse = YlxwPetOnFuseRef = function (…)`，一行；`onFuse` 绑定不变，
     pet089 自身对它的引用一字未动）。
     ⇒ 融合面板出现在**左列内部**（弹窗之内），点了就能看见。
     ★ 为什么**不**用「切到右栏的融合页签」：pet089 的页签条在 modal 之外、被
       `createPortal(document.body)` 的弹窗遮住；一旦切到 fuse 页，
       `YlxwPetShell` 会**整个不再渲染 vM**（弹窗消失），融合面板被丢到 `QM`
       根 Fragment 的行内位置（页面底部）⇒ 用户会看到「点一下弹窗没了、什么都没出现」。
       故改为左列内联展开：同一个组件、同一个动作，只换个能看见的落点。
       另：`wN` 的两列行被 fun086 的 4 条逐字门禁钉死（`F6·…`），改它必破门禁。
  C) 秘径状态：同一块里给一行「秘径（灵兽远征）单次消耗」，
     数值直接调 pet089 的 `YlxwPetPathCost` / `YlxwPetPathHp` / `YlxwPetPathExp`（同源）。

=========================================================================== 与前后模块的边界（装配序核对，逐条 grep 过）
--------------------------------------------------------------------------
  · 锚点 `children: "\u5b09\u620f" })] }),`（喂养/嬉戏行尾）：
    **无任何模块**引用该串 ⇒ 追加不破门禁。
  · 锚点 `function YlxwTPet() {`：fun086 F5a 的锚是
    `'function YlxwTPet() {\n  var r = YlxwUseList("/pet")'`（replace，形态已变），
    本模块用 `insert_before` 插在 `function YlxwTPet() {` **之前**，两者不重叠；
    fun086 的 `F5a·/pet 端点未改` / `F5a·旧全量渲染已清零` 两条门禁均不受影响。
  · 锚点 `function YlxwMailHint() {`：mail_ext 亦以它为 insert_before 锚，
    本模块插在**同一锚之前** ⇒ 落在 mail_ext 块之后，两块同为顶层函数声明，互不覆盖。
  · 锚点 `g.lingshi > 0 && !g.claimed && e.jsx(YlxwBtn, { … "/mail/claim" … })`：
    mail_ext 的门禁只断言 `YlxwMailClaimAllBtn` / 标题文案，**不断言**该串。
  · `var onFuse = function (mainId, subId, cost, rate) {`：pet089 仅在 INJECT_JS 里出现，
    **其门禁清单无 onFuse 条目**；numbal 全文 0 次。
  · **不碰** fun086 的 F6 两列行（`children:__xw?…`）/ `e.jsx(YlxwFuse,{k:__xw})` /
    `xw:` 计数 / T6 人物志两列类串 —— 这些都被逐字门禁钉死。
  · **不碰** pet089 的 shell 分支、`YlxwPetFuseTab` 本体、`YLXW_COMP.pet` 注册字面量。

=========================================================================== 技术约束遵守
  · 注入块经 zh() 后无非 ASCII；不含 V28_BAN_PATTERNS
    （iframe / postMessage / XMLHttpRequest / auth_token / X-YL-）。不用 require。
  · 注入点唯一（expect=1）；apply() 返回门禁五元组列表；本文件不写任何产物。
"""

import re

# --------------------------------------------------------------------------- 注入块 A（信箱删除）

INJECT_MAIL_JS = r'''
/* ===== yl-0.8.10e-1: 信箱「删除邮件」 =====
   端点：DELETE /api/mail/:id（200 {ok,id} / 400 id 非法 / 404 不存在或非本人 / 409 已领取不可删）
   设定：已领取奖励的邮件不可删除（按钮置灰）；未领取的可删，但必须二次确认。
   二次确认沿用全站既有 an(消息, 标题, onOk, onCancel)（自绘确认弹窗 + window.confirm 兜底）。
   请求走统一鉴权封装 Xc(ln + 路径, {method:"DELETE"})，直接读 HTTP status 分支 409/404/400
   （YlxwApi 会把非 2xx 折叠成 Error(body.error||"请求失败(N)")，无法区分状态码）。 */
function YlxwMailDelBtn(props) {
  var mail = (props && props.mail) || {};
  var s = O.useState(!1), busy = s[0], setBusy = s[1];
  var claimed = !!mail.claimed;
  function doDel() {
    if (busy || claimed) return;
    an("\u786e\u5b9a\u5220\u9664\u8fd9\u5c01\u90ae\u4ef6\u5417\uff1f\u5220\u9664\u540e\u65e0\u6cd5\u6062\u590d\u3002", "\u5220\u9664\u90ae\u4ef6", function () {
      setBusy(!0);
      Xc(ln + "/mail/" + mail.id, { method: "DELETE" }).then(function (res) {
        return res.json().then(
          function (b) { return { ok: res.ok, status: res.status, body: b }; },
          function () { return { ok: res.ok, status: res.status, body: null }; }
        );
      }).then(function (r) {
        setBusy(!1);
        if (r.ok) {
          ia("\u90ae\u4ef6\u5df2\u5220\u9664");
          if (props.onDone) props.onDone();
          YlxwDirty();
          return;
        }
        if (r.status === 409) { Je("\u8be5\u90ae\u4ef6\u5df2\u9886\u53d6\u5956\u52b1\uff0c\u4e0d\u53ef\u5220\u9664"); return; }
        if (r.status === 404) { Je("\u90ae\u4ef6\u4e0d\u5b58\u5728\u6216\u4e0d\u5c5e\u4e8e\u4f60\uff0c\u8bf7\u5237\u65b0\u540e\u91cd\u8bd5"); return; }
        if (r.status === 400) { Je("\u90ae\u4ef6\u7f16\u53f7\u975e\u6cd5\uff0c\u65e0\u6cd5\u5220\u9664"); return; }
        Je("\u5220\u9664\u5931\u8d25\uff1a" + ((r.body && r.body.error) || ("\u8bf7\u6c42\u5931\u8d25(" + r.status + ")")));
      }, function (e1) {
        setBusy(!1);
        Je("\u5220\u9664\u5931\u8d25\uff1a" + ((e1 && e1.message) || e1));
      });
    });
  }
  var label = claimed ? "\u4e0d\u53ef\u5220\u9664" : (busy ? "\u5220\u9664\u4e2d\u2026" : "\u5220\u9664");
  return e.jsx("span", {
    title: claimed ? "\u5df2\u9886\u53d6\u5956\u52b1\u7684\u90ae\u4ef6\u4e0d\u53ef\u5220\u9664" : "\u5220\u9664\u8fd9\u5c01\u90ae\u4ef6",
    children: e.jsx(YlxwBtn, { tone: "ghost", disabled: busy || claimed || !!(props && props.busy), onClick: doDel, children: label })
  });
}
'''

# --------------------------------------------------------------------------- 注入块 B（灵宠左栏）

INJECT_PET_JS = r'''
/* ===== yl-0.8.10e-2: 左栏「仙务·妖灵」补出灵宠作用 + 融合 / 秘径入口 =====
   左栏 = YlxwTPet（GET /api/pet），原先只有 6 个服务端字段 + 喂养/嬉戏。
   本块在其 children 里追加一块「灵宠作用」：
     · 加成数值与右栏灵宠卡片**同源同公式**（物种表 rn.baseStats + pet089 的
       品阶/阶段加成系数 + 主战转化率），不新造任何系数表；
     · 内联展开 pet089 的**真实融合面板**（同一个组件 YlxwPetFuseTab + 同一个融合动作）；
     · 一行秘径（灵兽远征）单次消耗，数值同调 pet089 的 YlxwPetPathCost/Hp/Exp。 */

/* 融合执行动作的发布点：pet089 YlxwPetShell 每次渲染都会把它的 onFuse 赋到这里 */
var YlxwPetOnFuseRef = null;

/* 稳定散列：妖灵无物种字段，用「名字+品阶」定一个物种
   （不用 Math.random —— 否则每次渲染数值都会抖动） */
function YlxwSpiritHash(v) {
  var s = String(v == null ? "" : v), h = 0, i;
  for (i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) % 2147483647; }
  return h;
}
/* 物种基准属性：与基座灵宠属性成长式**逐字同式**
   （等级 ×1.08/×1.08/×1.08/×1.02；阶段1 ×4.5/×4.5/×4.5/×2；阶段2 ×5/×5/×5/×2.5）。
   原式是 hook 内的闭包局部变量（模块级不可达），故按同一公式复刻，数值一字未改。 */
function YlxwPetSpeciesStats(species, level, stage) {
  var C = null, i;
  for (i = 0; i < rn.length; i++) { if (rn[i] && rn[i].species === species) { C = rn[i]; break; } }
  if (!C || !C.baseStats) return null;
  var b = C.baseStats;
  var g = Number(b.attack) || 0, q = Number(b.defense) || 0, w = Number(b.hp) || 0, A = Number(b.speed) || 0;
  var lv = Math.max(1, Math.floor(Number(level) || 1)), st = YlxwPetStageOf(stage);
  for (i = 1; i < lv; i++) { g = Math.floor(g * 1.08); q = Math.floor(q * 1.08); w = Math.floor(w * 1.08); A = Math.floor(A * 1.02); }
  if (st >= 1) { g = Math.floor(g * 4.5); q = Math.floor(q * 4.5); w = Math.floor(w * 4.5); A = Math.floor(A * 2); }
  if (st >= 2) { g = Math.floor(g * 5); q = Math.floor(q * 5); w = Math.floor(w * 5); A = Math.floor(A * 2.5); }
  return { attack: g, defense: q, hp: w, speed: A };
}
/* 妖灵（GET /pet 的 pet）→ 灵宠视图
   品阶映射 / 等级 / 亲密度 与 pet089 YlxwSpiritToPet 同口径；
   物种取「同品阶池」里的稳定项（池过滤口径与 YlxwSpiritToPet 逐字一致） */
function YlxwSpiritPetView(sp) {
  var raw = String((sp && sp.rarity) || "");
  var mapped = YLXW_PET_SPIRIT_MAP[raw] || (YLXW_PET_BONUS_RARITY[raw] ? raw : "\u666e\u901a");
  var pool = [], i;
  for (i = 0; i < rn.length; i++) { if (rn[i] && YlxwPetRarityOf(rn[i].rarity) === mapped) pool.push(rn[i]); }
  if (pool.length === 0) pool = rn.slice();
  var pick = pool.length ? pool[YlxwSpiritHash(String((sp && sp.name) || "") + "|" + mapped) % pool.length] : null;
  var lv = Math.max(1, Math.min(100, Math.floor((Number(sp && sp.hunger) || 0) / 100) || 1));
  var af = Math.min(100, Math.max(0, Math.floor((Number(sp && sp.bond) || 0) / 2)));
  var st = (pick && YlxwPetSpeciesStats(pick.species, lv, 0)) || (pick && pick.baseStats) || { attack: 50, defense: 25, hp: 500, speed: 30 };
  return { name: (sp && sp.name) || "\u5996\u7075", species: pick ? pick.species : "\u7075\u517d",
    rarity: mapped, level: lv, evolutionStage: 0, affection: af, stats: st };
}
/* 出战加成：与右栏灵宠卡片同源同公式（pet089 的系数函数 + 主战转化率） */
function YlxwSpiritBonusView(pet) {
  var rate = YLXW_PET_LANES[0].rate;
  var st = (pet && pet.stats) || {};
  return {
    rate: rate,
    attack: YlxwPetBonusOne(st.attack, rate, pet.rarity, pet.evolutionStage, pet.affection),
    defense: YlxwPetBonusOne(st.defense, rate, pet.rarity, pet.evolutionStage, pet.affection),
    maxHp: YlxwPetBonusOne(st.hp, rate, pet.rarity, pet.evolutionStage, pet.affection),
    speed: YlxwPetBonusOne(st.speed, rate, pet.rarity, pet.evolutionStage, pet.affection),
    critRate: YlxwPetBonusCrit(pet.affection),
    dodgeRate: YlxwPetBonusDodge(pet.affection),
  };
}
/* 左栏作用块：加成数值 + 妖灵本体 + 融合/秘径入口（内联展开 pet089 融合面板） */
function YlxwTSpiritUse(props) {
  var sp = props && props.pet;
  var player = Be(function (s) { return s.player; });
  var sst = O.useState(!1), open = sst[0], setOpen = sst[1];
  var pet = YlxwSpiritPetView(sp);
  var b = YlxwSpiritBonusView(pet);
  var body = pet.stats || {};
  var pets = (player && player.pets) || [];
  var lines = [
    e.jsx("span", { className: "text-amber-300 font-bold", children: "\u7075\u5ba0\u4f5c\u7528" }, "t"),
    e.jsx("span", { className: "text-stone-500", children: "\u4e3b\u6218\u51fa\u6218\u8f6c\u5316 " + Math.round(b.rate * 100) + "%\uff08\u4e0e\u7075\u5ba0\u5361\u7247\u540c\u6e90\u540c\u5f0f\uff09" }, "r"),
    e.jsx("span", { className: "w-full" }, "br"),
    e.jsx("span", { children: "\u653b\u51fb +" + b.attack }, "a"),
    e.jsx("span", { children: "\u9632\u5fa1 +" + b.defense }, "d"),
    e.jsx("span", { children: "\u6c14\u8840 +" + b.maxHp }, "h"),
    e.jsx("span", { children: "\u901f\u5ea6 +" + b.speed }, "s"),
    e.jsx("span", { children: "\u66b4\u51fb +" + (b.critRate * 100).toFixed(1) + "%" }, "c"),
    e.jsx("span", { children: "\u95ea\u907f +" + (b.dodgeRate * 100).toFixed(1) + "%" }, "o")
  ];
  var fuse = [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      e.jsx("span", { className: "text-amber-300 font-bold", children: "\u878d\u5408\u73a9\u6cd5" }),
      e.jsx(YlxwBtn, { tone: open ? "ghost" : "solid", onClick: function () { setOpen(!open); },
        children: open ? "\u6536\u8d77\u878d\u5408\u9762\u677f" : "\u878d\u5408" })
    ] }, "fh"),
    e.jsxs("div", { className: "text-[11px] text-stone-400 flex flex-wrap gap-x-2 gap-y-0.5", children: [
      e.jsx("span", { children: "\u53ef\u878d\u5408\u7075\u5ba0 " + pets.length + " \u53ea" }, "fc"),
      e.jsx("span", { children: "\u878d\u5408\u8d39 " + YlxwNum(YLXW_PET_FUSE_BASE) + " \u7075\u77f3\u8d77" }, "ff"),
      e.jsx("span", { children: "\u79d8\u5f84\u5355\u6b21 " + YlxwNum(YlxwPetPathCost(pet)) + " \u7075\u77f3 + " + YlxwNum(YlxwPetPathHp(player && player.maxHp, pet.evolutionStage)) + " \u6c14\u8840 + " + YlxwNum(YlxwPetPathExp(player && player.maxExp, pet.evolutionStage)) + " \u4fee\u4e3a" }, "fp")
    ] }, "fl")
  ];
  if (open) {
    fuse.push(YlxwPetOnFuseRef
      ? e.jsx(YlxwPetFuseTab, { player: player, onFuse: YlxwPetOnFuseRef }, "fx")
      : e.jsx("div", { className: "text-[11px] text-stone-500", children: "\u878d\u5408\u9762\u677f\u672a\u5c31\u7eea\uff0c\u8bf7\u5173\u95ed\u540e\u91cd\u65b0\u6253\u5f00\u7075\u5ba0\u7cfb\u7edf\u3002" }, "fx"));
  }
  return e.jsxs("div", { className: "space-y-2 bg-ink-800/60 border border-stone-700 rounded p-2.5", children: [
    e.jsxs("div", { className: "text-xs flex flex-wrap gap-x-2 gap-y-0.5", children: lines }),
    e.jsxs("div", { className: "text-[11px] text-stone-500", children: [
      "\u5996\u7075\u672c\u4f53\uff1a", pet.species, " \u00b7 ", pet.rarity, " \u00b7 Lv." + pet.level, " \u00b7 \u4eb2\u5bc6 " + pet.affection,
      " \u00b7 \u653b\u51fb " + YlxwNum(body.attack), " \u00b7 \u9632\u5fa1 " + YlxwNum(body.defense),
      " \u00b7 \u6c14\u8840 " + YlxwNum(body.hp), " \u00b7 \u901f\u5ea6 " + YlxwNum(body.speed)
    ] }),
    e.jsxs("div", { className: "space-y-1.5 pt-1.5 border-t border-dashed border-stone-700", children: fuse })
  ] });
}
'''

# --------------------------------------------------------------------------- 锚点（全部实测 count==1）

# 注入锚 A：信箱面板之前（mail_ext 同锚 insert_before；两块同为顶层函数声明，互不覆盖）
ANCHOR_MAIL_HINT = 'function YlxwMailHint() {'

# A-挂载：列表项「领取」按钮整段（唯一）—— 在其后追加删除按钮
ANCHOR_MAIL_CLAIM_BTN = (
    'g.lingshi > 0 && !g.claimed && e.jsx(YlxwBtn, { disabled: !!u, onClick: function() { '
    'f("c" + g.id, "/mail/claim", { id: g.id }, "\\u5df2\\u9886\\u53d6\\uff0c\\u7075\\u77f3'
    '\\u5df2\\u5165\\u8d26"); }, children: "\\u9886\\u53d6" })'
)
REPL_MAIL_CLAIM_BTN = (
    ANCHOR_MAIL_CLAIM_BTN + ', e.jsx(YlxwMailDelBtn, { mail: g, busy: !!u, onDone: c }, "d" + g.id)'
)

# 注入锚 B：YlxwTPet 定义之前（顶层同作用域；函数声明提升，pet089 的组件/系数均可引用）
ANCHOR_TPET = 'function YlxwTPet() {'

# B-挂载：喂养/嬉戏那一行 div 的收尾（唯一）—— 在其后追加作用块
ANCHOR_PET_ACT_ROW = 'children: "\\u5b09\\u620f" })] }),'
REPL_PET_ACT_ROW = ANCHOR_PET_ACT_ROW + ' m && e.jsx(YlxwTSpiritUse, { pet: m }),'

# B-发布点：pet089 shell 内的融合动作（把 onFuse 同时挂到模块级 ref；绑定本身不变）
ANCHOR_ONFUSE = 'var onFuse = function (mainId, subId, cost, rate) {'
REPL_ONFUSE = 'var onFuse = YlxwPetOnFuseRef = function (mainId, subId, cost, rate) {'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 mail_ext / fun086 / pet089）；ctx = {'zh': zh, ...}"""
    zh = ctx['zh']

    mail_js = zh(INJECT_MAIL_JS)
    pet_js = zh(INJECT_PET_JS)
    for tag, blk in (('mail', mail_js), ('pet', pet_js)):
        bad = re.findall(r'[^\x00-\x7f]', blk)
        if bad:
            raise AssertionError('v2810e %s 注入块 zh() 后仍含非 ASCII: %r' % (tag, bad[:10]))

    # 1) 注入信箱删除组件（顶层，紧贴 YlxwMailHint 之前）
    p.insert_before('v2810e-mail-block', ANCHOR_MAIL_HINT, mail_js + '\n',
                    expect=1, note='注入 YlxwMailDelBtn（Xc DELETE + an() 二次确认 + 409/404/400 分支）')

    # 2) 信箱列表项：在「领取」之后追加删除按钮（只加节点，不重写列表项）
    p.replace('v2810e-mail-mount', ANCHOR_MAIL_CLAIM_BTN, REPL_MAIL_CLAIM_BTN, expect=1,
              note='列表项 flex 行尾追加「删除」按钮')

    # 3) 注入灵宠左栏作用块（顶层，紧贴 YlxwTPet 之前）
    p.insert_before('v2810e-pet-block', ANCHOR_TPET, pet_js + '\n',
                    expect=1, note='注入 YlxwTSpiritUse + 物种属性/妖灵视图/加成视图 三个纯函数')

    # 4) 左栏 children：喂养/嬉戏之后追加作用块
    p.replace('v2810e-pet-mount', ANCHOR_PET_ACT_ROW, REPL_PET_ACT_ROW, expect=1,
              note='YlxwTPet children 追加「灵宠作用 + 融合/秘径入口」')

    # 5) 发布 pet089 的融合动作（onFuse 绑定不变，仅多挂一个模块级 ref）
    p.replace('v2810e-onfuse-publish', ANCHOR_ONFUSE, REPL_ONFUSE, expect=1,
              note='YlxwPetShell 的 onFuse 同时发布到 YlxwPetOnFuseRef，供左栏内联融合面板复用')

    # ------------------------------------------------------------- 门禁
    # 转义纪律：needle 落在**本模块注入块内**的，一律写 \uXXXX 转义形态（zh() 后即该形态）；
    #   落在基座 / 其它模块产物里的，按其在产物中的真实形态（原样）写。
    gates = [
        # ================= 任务 A：信箱「删除邮件」 =================
        ('E·A 删除按钮组件已注入',   'function YlxwMailDelBtn(props) {',                         1, '==', ''),
        ('E·A 删除按钮已挂到列表项', 'e.jsx(YlxwMailDelBtn, { mail: g, busy: !!u, onDone: c }, "d" + g.id)', 1, '==', '追加在「领取」之后'),
        ('E·A 请求走统一鉴权 Xc+ln', 'Xc(ln + "/mail/" + mail.id, { method: "DELETE" })',        1, '==', 'ln="/yl/api"，不自己拼前缀'),
        ('E·A 直接读 HTTP status',   'if (r.status === 409) {',                                  1, '==', 'YlxwApi 会折叠状态码，故直接用 Xc'),
        ('E·A 二次确认走 an() 宿主',
         r'an("\u786e\u5b9a\u5220\u9664\u8fd9\u5c01\u90ae\u4ef6\u5417\uff1f\u5220\u9664\u540e\u65e0\u6cd5\u6062\u590d\u3002", "\u5220\u9664\u90ae\u4ef6", function () {',
         1, '==', '与全站 13 处同款（自绘弹窗 + window.confirm 兜底）'),
        ('E·A 设定·已领取判定',      'var claimed = !!mail.claimed;',                            1, '==', ''),
        ('E·A 设定·按钮文案分流',
         r'var label = claimed ? "\u4e0d\u53ef\u5220\u9664" : (busy ? "\u5220\u9664\u4e2d\u2026" : "\u5220\u9664");',
         1, '==', '已领取 → 「不可删除」（置灰）'),
        ('E·A 设定·置灰原因 title',
         r'title: claimed ? "\u5df2\u9886\u53d6\u5956\u52b1\u7684\u90ae\u4ef6\u4e0d\u53ef\u5220\u9664" : "\u5220\u9664\u8fd9\u5c01\u90ae\u4ef6",',
         1, '==', ''),
        ('E·A 设定·置灰 disabled',
         'disabled: busy || claimed || !!(props && props.busy), onClick: doDel',               1, '==', ''),
        ('E·A 409 提示（已领取不可删）',
         r'if (r.status === 409) { Je("\u8be5\u90ae\u4ef6\u5df2\u9886\u53d6\u5956\u52b1\uff0c\u4e0d\u53ef\u5220\u9664"); return; }',
         1, '==', '服务端兜底：并发窗口 / 口径变更'),
        ('E·A 404 提示（不存在/非本人）',
         r'if (r.status === 404) { Je("\u90ae\u4ef6\u4e0d\u5b58\u5728\u6216\u4e0d\u5c5e\u4e8e\u4f60\uff0c\u8bf7\u5237\u65b0\u540e\u91cd\u8bd5"); return; }',
         1, '==', ''),
        ('E·A 400 提示（id 非法）',
         r'if (r.status === 400) { Je("\u90ae\u4ef6\u7f16\u53f7\u975e\u6cd5\uff0c\u65e0\u6cd5\u5220\u9664"); return; }',
         1, '==', ''),
        ('E·A 成功 toast',           r'ia("\u90ae\u4ef6\u5df2\u5220\u9664");',                   1, '==', ''),
        ('E·A 成功后刷新列表',       'if (props.onDone) props.onDone();',                        1, '==', 'onDone = YlxwUseList.load ⇒ 重拉 /mail/list'),
        ('E·A 成功后通知脏标记',     'if (props.onDone) props.onDone();\n          YlxwDirty();', 1, '==', ''),
        ('E·A 未新造邮件路径',       '/mail/delete',                                             0, '==', '契约是 DELETE /api/mail/:id'),
        ('E·A 鉴权全交给 Xc',        'Xc(ln + "/mail/" + mail.id, { method: "DELETE" })',        1, '==', '不自己拼 token / 请求头'),
        # ---- 基线未动 ----
        ('E·A 基线「领取」按钮未动',  'f("c" + g.id, "/mail/claim", { id: g.id }',                1, '==', ''),
        ('E·A 基线列表项标题未动',
         'e.jsx("span", { className: "font-bold " + (g.claimed ? "text-stone-500" : "text-stone-100")',
         1, '==', ''),
        ('E·A 基线「全部已读」未动',  'f("readall", "/mail/read", { all: !0 }',                   1, '==', ''),
        ('E·A 基线一键领取未动',      'e.jsx(YlxwMailClaimAllBtn, { count:',                     1, '==', 'mail_ext 成果保留'),
        ('E·A 基线 /mail/list 未动',  'YlxwUseList("/mail/list?page=1&pageSize=20")',            1, '==', ''),

        # ================= 任务 B：灵宠左栏作用 =================
        ('E·B 作用块组件已注入',     'function YlxwTSpiritUse(props) {',                          1, '==', ''),
        ('E·B 作用块已挂到左栏',
         'children: "\\u5b09\\u620f" })] }), m && e.jsx(YlxwTSpiritUse, { pet: m }),',           1, '==', '追加在喂养/嬉戏之后'),
        ('E·B 物种属性复刻函数',     'function YlxwPetSpeciesStats(species, level, stage) {',      1, '==', '基座属性成长式逐字复刻（原式是闭包局部量）'),
        ('E·B 妖灵视图函数',         'function YlxwSpiritPetView(sp) {',                          1, '==', ''),
        ('E·B 加成视图函数',         'function YlxwSpiritBonusView(pet) {',                      1, '==', ''),
        ('E·B 稳定散列（不随机）',   'function YlxwSpiritHash(v) {',                             1, '==', '避免每次渲染数值抖动'),
        # ---- 同源同公式（全部指向 pet089 的既有函数/表） ----
        ('E·B 加成走 pet089 系数',
         'attack: YlxwPetBonusOne(st.attack, rate, pet.rarity, pet.evolutionStage, pet.affection),',
         1, '==', ''),
        ('E·B 气血/速度同源',
         'speed: YlxwPetBonusOne(st.speed, rate, pet.rarity, pet.evolutionStage, pet.affection),',
         1, '==', ''),
        ('E·B 暴击走 pet089 函数',   'critRate: YlxwPetBonusCrit(pet.affection),',                1, '==', ''),
        ('E·B 闪避走 pet089 函数',   'dodgeRate: YlxwPetBonusDodge(pet.affection),',              1, '==', ''),
        ('E·B 主战转化率取 pet089 表', 'var rate = YLXW_PET_LANES[0].rate;',                      1, '==', '不硬编码 50%'),
        ('E·B 品阶映射取 pet089 表',
         r'var mapped = YLXW_PET_SPIRIT_MAP[raw] || (YLXW_PET_BONUS_RARITY[raw] ? raw : "\u666e\u901a");',
         2, '==', '本模块 1 处 + pet089 YlxwSpiritToPet 1 处（逐字同源）'),
        ('E·B 物种池过滤同 pet089 口径',
         'if (rn[i] && YlxwPetRarityOf(rn[i].rarity) === mapped) pool.push(rn[i]);',            1, '==', ''),
        ('E·B 等级同服务端 petLevel', 'Math.floor((Number(sp && sp.hunger) || 0) / 100) || 1',   2, '==', '本模块 1 处 + pet089 YlxwSpiritToPet 1 处（同式）'),
        ('E·B 亲密度同 YlxwSpiritToPet', 'Math.min(100, Math.max(0, Math.floor((Number(sp && sp.bond) || 0) / 2)))', 2, '==', '本模块 1 处 + pet089 YlxwSpiritToPet 1 处（同式）'),
        ('E·B 物种表用右栏同一张 rn', 'for (i = 0; i < rn.length; i++) { if (rn[i] && rn[i].species === species) { C = rn[i]; break; } }', 1, '==', ''),
        # ---- 融合入口 ----
        ('E·B 融合动作已发布',       'var onFuse = YlxwPetOnFuseRef = function (mainId, subId, cost, rate) {', 1, '==', 'onFuse 绑定不变'),
        ('E·B pet089 原声明形态已清零', 'var onFuse = function (mainId, subId, cost, rate) {',    0, '==', '必须为 0（否则 onFuse 未被发布）'),
        ('E·B 融合面板内联展开',
         'e.jsx(YlxwPetFuseTab, { player: player, onFuse: YlxwPetOnFuseRef }, "fx")',           1, '==', '复用 pet089 组件 + 其动作'),
        ('E·B 融合入口按钮',
         r'children: open ? "\u6536\u8d77\u878d\u5408\u9762\u677f" : "\u878d\u5408"',           1, '==', ''),
        ('E·B 融合面板未就绪兜底',
         r'children: "\u878d\u5408\u9762\u677f\u672a\u5c31\u7eea\uff0c\u8bf7\u5173\u95ed\u540e\u91cd\u65b0\u6253\u5f00\u7075\u5ba0\u7cfb\u7edf\u3002"',
         1, '==', ''),
        ('E·B 融合费同源常量',       'YlxwNum(YLXW_PET_FUSE_BASE)',                               1, '==', 'pet089 的 3000 基础费'),
        ('E·B pet089 融合组件保留',  'function YlxwPetFuseTab(props) {',                          1, '==', '未重写'),
        ('E·B pet089 自身调用未动',  'e.jsx(YlxwPetFuseTab, { player: player, onFuse: onFuse })', 1, '==', 'shell 内原调用保留'),
        ('E·B pet089 shell 未重写',  'function YlxwPetShell(p) {',                                1, '==', ''),
        # ---- 秘径状态（同源） ----
        ('E·B 秘径灵石同源',         'YlxwNum(YlxwPetPathCost(pet))',                             1, '==', 'pet089 YlxwPetPathCost'),
        ('E·B 秘径气血同源',
         'YlxwNum(YlxwPetPathHp(player && player.maxHp, pet.evolutionStage))',                    1, '==', 'pet089 YlxwPetPathHp'),
        ('E·B 秘径修为同源',
         'YlxwNum(YlxwPetPathExp(player && player.maxExp, pet.evolutionStage))',                  1, '==', 'pet089 YlxwPetPathExp'),
        # ---- 硬红线：不碰别人的门禁面 ----
        ('E·红线 YlxwTPet 未整体重写', 'function YlxwTPet() {',                                    1, '==', '只往 children 追加节点'),
        ('E·红线 YlxwTPet 喂养/嬉戏未动', 'f("play", "/pet/play", {}, "\\u5b09\\u620f\\u6210\\u529f");', 1, '==', ''),
        ('E·红线 YlxwTPet /pet 端点未动', 'YlxwUseList("/pet")',                                   1, '==', 'fun086 F5a 门禁面'),
        ('E·红线 fun086 日志折叠未动', 'var _pl = O.useState(!1), _logOpen = _pl[0], _setLogOpen = _pl[1];', 1, '==', 'fun086 F5a 成果保留'),
        ('E·红线 fun086 F6 两列行未动',
         'children:__xw?e.jsxs("div",{className:"grid grid-cols-1 md:grid-cols-2 gap-4 items-start",children:[e.jsx("div",{className:"min-w-0",children:e.jsx(YlxwFuse,{k:__xw})}),e.jsx("div",{className:"min-w-0",children:l})]}):l',
         1, '==', 'fun086 4 条逐字门禁面，一行未动'),
        ('E·红线 融合页 xw 键计数未变', 'xw:',                                                    8, '==', 'fun086 F6 门禁面；R-065 摘 sect 融合键后 9→8（接线人校准）'),
        ('E·红线 YLXW_COMP.pet 注册未动', 'pet: YlxwTPet',                                         1, '==', ''),
        ('E·红线 灵宠面板 memo 未动',  'jM=Rt.memo(YlxwPetShell)',                                1, '==', 'pet089 成果保留'),
        ('E·红线 战斗结算核心未动',    'YlxwBattleBonus(t),YlxwDOD=',                              1, '==', ''),
    ]
    return gates
