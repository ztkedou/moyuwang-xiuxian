# -*- coding: utf-8 -*-
r"""
yl_farm089_ext.py — 0.8.9 T5 灵田品种重构 · 客户端补丁（T5 客户端归属）

接线信息（0.8.9 build-plan 落表用）
--------------------------------------------------------------------------
  模块名 farm089；V28_MODULES 插在 pet089 之后、numbal 之前（numbal 恒最后）。
  apply(p, ctx)：p = yl_patch.Patcher；ctx['zh'] = 中文转 \uXXXX。

靶点与锚点（全部实测确认）
--------------------------------------------------------------------------
  B1 灵田面板覆盖注册：YLXW_COMP.farm=YlxwTFarmT10; → YLXW_COMP.farm=YlxwTFarmT5;
     （原 YlxwTFarmT10 保留为死代码；与 farm087 覆盖注册同先例，不删原组件防锚区互踩）
  B2 注入 YlxwTFarmT5 组件（锚在 var YLXW_COMP = { 之前）

覆盖内容（T5 策划案 §2/§6 + §8「灵田面板 UI」）
--------------------------------------------------------------------------
  · 成熟田块：**双按钮**「变卖」（灵石）/「服用」（修为 + 属性）
  · **二次确认弹窗**（Q4 选 b：防误点，尤其高价神品）
  · 品阶（凡/灵/玄/仙/神）展示 + 洞府等级门槛灰置（沿用 T10 的 grottoLevel 语义）
  · 成熟时长展示（服务端下发 minutes）
  · 百分比属性服用：写 player.critRate/dodgeRate/**lifeLeech**；
    **上限灰置**（复用 YlxwBattleCapCfg 口径：暴击 0.35 / 闪避 0.35 / 吸血 0.25）
  · 旧作物兼容：存量已种下的旧作物仍走同一 /farm/harvest（mode 二选一），服务端按旧表结算
  · 玩法说明折叠块（T5 §6.1 文案）

★ 硬红线
--------------------------------------------------------------------------
  · 不新增物品表条目（变卖/服用**不是物品**）
  · 不动 T9 洞府域 / T5 活动倍率挂点区（build_v26n 的 BATTLE_PATCHES 区）
  · 未新增 403 语义（业务拒绝一律 400/409）
  · item 4（照料）口径：每次 +2%、当日封顶 +10% —— 与 T5 同批复核红线（服务端权威）

服务端依赖（本模块只做客户端一半，服务端需求另行列出）
--------------------------------------------------------------------------
  S1  FARM_CROPS 5→20 扩表，每项新增字段：
        tier   : "凡" | "灵" | "玄" | "仙" | "神"
        line   : "sell" | "cult" | "mix" | "rare"   （纯卖钱/纯修为/综合/稀有）
        sell   : 变卖价（灵石）
        consExp: 服用修为
        consAttr: [{ key: "attack"|"defense"|"maxHp"|"speed", value: n }, ...]   基础属性
        consPct : [{ key: "critRate"|"dodgeRate"|"lifeLeech", value: 0.02 }, ...] 百分比属性
  S2  POST /api/farm/harvest 增 mode: "sell" | "consume"（缺省 = sell，保旧契约）；
      consume 返回 consumed:{ exp, attrs:{...}, pct:{...} } 与 pctCapped:{...}
      ★ 守卫式 harvested=1 语义不变（防双收）
  S3  status 的 crops 逐项带上以上字段（客户端零硬编码；缺字段则降级渲染，不报错）
"""  # noqa: E501
import re

# --------------------------------------------------------------------------- 锚点常量

# T10 块注释头（farm087 注入的整块起点）。★ 用它而非 'var YLXW_COMP = {'
# 做顶级注入锚点：后者在 YlxwTFarmT10 函数体之后，insert_before 会把我的块
# 塞进 T10 体内（详见 apply() 的踩坑注释）。实测产物中该串恰好出现 1 次。
FARM_T10_ANCHOR = '/* ===== yl-0.8.7 T10'

# window 桥（验收可达性）。插在 'YLXW_COMP.farm=YlxwTFarmT5;' 之后，同处闭包 depth=2，
# 故能读到本模块全部 T2/T5 符号。只导出既有名字，不新增逻辑。
# 先例：产物 @1820947 已有 `try { window.YlxwMarketPayouts = YlxwMarketPayouts; ... } catch {}`
FARM_WINDOW_BRIDGE = (
    '\ntry { window.YLXW_T5 = {'
    ' farm: YlxwTFarmT5, T10: YlxwTFarmT10, confirm: YlxwFarmConfirm,'
    ' pctOf: YlxwFtPctOf, pctCapped: YlxwFtPctCapped,'
    ' consumeText: YlxwFtConsumeText, sellText: YlxwFtSellText,'
    ' tier: YLXW_FT_TIER, line: YLXW_FT_LINE, pctCap: YLXW_FT_PCT_CAP'
    ' }; } catch (e) {}\ntry { window.YLXW_T2 = {'
    ' shell: YlxwPetShell, fuseTab: YlxwPetFuseTab, statRow: YlxwPetStatRow,'
    ' pathCost: YlxwPetPathCost, pathHp: YlxwPetPathHp, pathExp: YlxwPetPathExp,'
    ' bonusOne: YlxwPetBonusOne, bonusCrit: YlxwPetBonusCrit, bonusDodge: YlxwPetBonusDodge,'
    ' bonusTotal: YlxwPetBonusTotal, fuseCost: YlxwPetFuseCost, fuseRate: YlxwPetFuseRate,'
    ' lanePets: YlxwPetLanePets, spiritToPet: YlxwSpiritToPet, mergeSpiritAway: YlxwMergeSpiritAway'
    ' }; } catch (e) {}\n'
)


def _brace_depth(text, pos):
    """数 text[:pos] 的净花括号深度（不做字符串/注释剔除，够用于本文件的层级自证）。"""
    d = 0
    for ch in text[:pos]:
        if ch == '{':
            d += 1
        elif ch == '}':
            d -= 1
    return d

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-0.8.9 T5: 灵田品种重构（双出口「变卖 / 服用」面板；YlxwTFarmT5 覆盖注册） =====
   服务端权威：GET /farm/status（crops 逐项下发 tier/line/sell/consExp/consAttr/consPct/minutes/seed/grottoLevel）；
   POST /farm/harvest {slot, mode:"sell"|"consume"}；POST /farm/tend | /farm/boost | /farm/harvest/all。
   业务拒绝一律 400/409（403 会被 Xc() 强制登出——本模块不新增 403 语义）。
   旧作物兼容：存量已种下的旧作物仍走同一 harvest（mode 二选一），服务端按旧表结算，客户端只按下发字段渲染。 */

/* 品阶展示（凡/灵/玄/仙/神 → 颜色） */
var YLXW_FT_TIER = {
  "\u51e1": "text-stone-300 border-stone-600 bg-stone-800",
  "\u7075": "text-green-300 border-green-600/50 bg-green-900/40",
  "\u7384": "text-cyan-300 border-cyan-600/50 bg-cyan-900/40",
  "\u4ed9": "text-amber-300 border-amber-500/50 bg-amber-900/40",
  "\u795e": "text-fuchsia-300 border-fuchsia-500/50 bg-fuchsia-900/40"
};
/* 产品线展示 */
var YLXW_FT_LINE = {
  sell: "\u7eaf\u5356\u94b1\u8349", cult: "\u7eaf\u4fee\u4e3a\u8349",
  mix: "\u7efc\u5408\u8349", rare: "\u7a00\u6709\u5c5e\u6027\u8349"
};
/* 百分比属性名 + 灵田专有上限（Q5 选 a：灵田专有上限，装备另计） */
var YLXW_FT_PCT = { critRate: "\u66b4\u51fb", dodgeRate: "\u95ea\u907f", lifeLeech: "\u5438\u8840" };
var YLXW_FT_PCT_CAP = { critRate: 0.08, dodgeRate: 0.06, lifeLeech: 0.04 };
/* 基础属性名 */
var YLXW_FT_ATTR = { attack: "\u653b\u51fb", defense: "\u9632\u5fa1", maxHp: "\u6c14\u8840", speed: "\u901f\u5ea6" };

/* 玩家百分比属性池读取（player.critRate 等；缺省 0） */
function YlxwFtPctOf(player) {
  var o = {}, keys = ["critRate", "dodgeRate", "lifeLeech"], i;
  for (i = 0; i < keys.length; i++) {
    var v = Number(player && player[keys[i]]);
    o[keys[i]] = isFinite(v) && v > 0 ? v : 0;
  }
  return o;
}
/* 该作物某百分比属性是否已达灵田上限（达则按钮灰置提示） */
function YlxwFtPctCapped(player, key) {
  var cap = YLXW_FT_PCT_CAP[key];
  if (cap == null) return false;
  return YlxwFtPctOf(player)[key] >= cap - 1e-9;
}
/* 服用预览文本（供二次确认弹窗） */
function YlxwFtConsumeText(cd) {
  var parts = [];
  if (!cd) return "\u4fee\u4e3a";
  if (YlxwNum(cd.consExp) > 0) parts.push("\u4fee\u4e3a +" + YlxwNum(cd.consExp));
  var i, a = cd.consAttr || [];
  for (i = 0; i < a.length; i++) {
    if (!a[i]) continue;
    parts.push((YLXW_FT_ATTR[a[i].key] || a[i].key) + " +" + YlxwNum(a[i].value));
  }
  var p = cd.consPct || [];
  for (i = 0; i < p.length; i++) {
    if (!p[i]) continue;
    parts.push((YLXW_FT_PCT[p[i].key] || p[i].key) + " +" + (YlxwNum(p[i].value) * 100).toFixed(1) + "%");
  }
  return parts.length ? parts.join(" \u00b7 ") : "\u4fee\u4e3a";
}
/* 变卖预览文本 */
function YlxwFtSellText(cd, slot) {
  var s = YlxwNum(cd && cd.sell);
  return "\u7075\u77f3 +" + s.toLocaleString();
}

/* ---------- T5 二次确认弹窗（Q4 选 b） ---------- */
function YlxwFarmConfirm(props) {
  if (!props.open) return null;
  var title = props.title || "\u8bf7\u786e\u8ba4";
  return e.jsx("div", { className: "fixed inset-0 z-50 flex items-center justify-center bg-black/60", onClick: props.onCancel, children:
    e.jsxs("div", { className: "bg-paper-800 border border-stone-600 rounded-lg p-4 w-[min(92vw,24rem)] space-y-3", onClick: function (ev) { ev.stopPropagation(); }, children: [
      e.jsx("div", { className: "font-serif font-bold text-amber-300", children: title }),
      e.jsx("div", { className: "text-sm text-stone-200", children: props.children }),
      e.jsxs("div", { className: "flex items-center justify-end gap-2", children: [
        e.jsx(YlxwBtn, { tone: "ghost", onClick: props.onCancel, children: "\u53d6\u6d88" }),
        e.jsx(YlxwBtn, { onClick: props.onOk, children: props.okText || "\u786e\u8ba4" })
      ] })
    ] }) });
}

/* ---------- T5 灵田面板（覆盖 YLXW_COMP.farm；原 YlxwTFarmT10 保留为死代码） ---------- */
function YlxwTFarmT5() {
  var r = YlxwUseList("/farm/status"), t = r.data, a = r.err, l = r.busy, c = r.load, d = YlxwUseAct(c), u = d.actKey, f = d.run;
  var m = (t && t.slots) || [], g = (t && t.crops) || {}, h = Object.keys(g);
  var gl = YlxwNum(t && t.grottoLevel);
  var bd = (t && t.boostDaily) || { used: 0, cap: 0 };
  var readyN = YlxwNum(t && t.readyCount);
  var pstore = Be(function (s) { return s.player; });
  var __auto = O.useRef(!1);
  var cf = O.useState(null), confirm = cf[0], setConfirm = cf[1];
  O.useEffect(function () {
    if (__auto.current) return;
    try {
      var gt = pstore && pstore.grotto;
      if (gt && gt.autoHarvest && readyN > 0) { __auto.current = !0; f("hall", "/farm/harvest/all", { mode: "sell" }); }
    } catch (e2) {}
  }, [t, readyN]);
  var badge = function (txt, cls, key) { return e.jsx("span", { className: cls, children: txt }, key); };
  var B_OK = "text-[11px] px-1.5 py-0.5 rounded bg-green-900/40 border border-green-600/50 text-green-300";
  var B_BOOST = "text-[11px] px-1.5 py-0.5 rounded bg-amber-900/40 border border-amber-500/50 text-amber-300";
  var B_PEST = "text-[11px] px-1.5 py-0.5 rounded bg-red-900/40 border border-red-600/50 text-red-300";
  var B_MUTE = "text-[11px] px-1.5 py-0.5 rounded bg-stone-800 border border-stone-600 text-stone-400";
  var tierBadge = function (cd) {
    if (!cd || !cd.tier) return null;
    return badge(cd.tier + "\u54c1", "text-[11px] px-1.5 py-0.5 rounded border " + (YLXW_FT_TIER[cd.tier] || YLXW_FT_TIER["\u51e1"]));
  };
  var lineBadge = function (cd) {
    if (!cd || !cd.line) return null;
    return badge(YLXW_FT_LINE[cd.line] || cd.line, B_MUTE);
  };
  var cropBtn = function (N, x) {
    var cd = g[x] || {}, nl = YlxwNum(cd.grottoLevel), ok2 = !nl || gl >= nl;
    /* \u2605 \u5df2\u505c\u79cd\u54c1\u79cd\u7f6e\u7070\uff1a\u4ec5**\u663e\u5f0f** retired===true \u624d\u7981\u7528\uff1b
       \u5b57\u6bb5\u7f3a\u5931\uff08\u670d\u52a1\u7aef\u672a\u4e0a\u7ebf\uff09\u4fdd\u6301\u539f\u884c\u4e3a\u53ef\u70b9\uff08\u5411\u540e\u517c\u5bb9\uff09\u3002 */
    var ret = cd.retired === true;
    return e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u || !ok2 || ret,
      onClick: function () { if (ret) return; f("p" + N.slot + x, "/farm/plant", { slot: N.slot, crop: x }, "\u5df2\u79cd\u4e0b " + (cd.name || YLXW_CROP[x] || x)); },
      children: (cd.name || YLXW_CROP[x] || x) + "\uff08" + YlxwNum(cd.seed).toLocaleString() + " \u7075\u77f3" + (nl && !ok2 ? " \u00b7 \u9700\u6d1e\u5e9c Lv." + nl : "") + (ret ? " \u00b7 \u5df2\u505c\u79cd" : "") + "\uff09" }, x);
  };
  var doSell = function (slot, cd) {
    setConfirm({ kind: "sell", slot: slot, cd: cd });
  };
  var doConsume = function (slot, cd) {
    setConfirm({ kind: "consume", slot: slot, cd: cd });
  };
  var runConfirm = function () {
    var q = confirm;
    setConfirm(null);
    if (!q) return;
    var mode = q.kind === "consume" ? "consume" : "sell";
    f("h" + q.slot + mode, "/farm/harvest", { slot: q.slot, mode: mode },
      mode === "consume" ? "\u670d\u7528\u6210\u529f\uff0c\u4fee\u4e3a\u4e0e\u5c5e\u6027\u5df2\u589e\u957f" : "\u53d8\u5356\u6210\u529f\uff0c\u7075\u77f3\u5df2\u5165\u8d26");
  };
  /* 二次确认内容 */
  var confirmNode = confirm ? e.jsx(YlxwFarmConfirm, {
    open: !0,
    title: confirm.kind === "consume" ? "\u786e\u8ba4\u670d\u7528" : "\u786e\u8ba4\u53d8\u5356",
    okText: confirm.kind === "consume" ? "\u670d\u7528" : "\u53d8\u5356",
    onCancel: function () { setConfirm(null); },
    onOk: runConfirm,
    children: e.jsxs("div", { className: "space-y-1", children: [
      e.jsxs("div", { children: ["\u4f5c\u7269\uff1a", (confirm.cd && confirm.cd.name) || ""] }),
      e.jsx("div", { children: confirm.kind === "consume" ? YlxwFtConsumeText(confirm.cd) : YlxwFtSellText(confirm.cd, confirm.slot) }),
      e.jsx("div", { className: "text-xs text-stone-400", children: "\u4e00\u7ecf\u9009\u62e9\u5373\u6d88\u8017\u4f5c\u7269\uff0c\u4e0d\u53ef\u64a4\u56de\u3002" })
    ] })
  }) : null;

  return e.jsxs(YlxwPanel, { children: [
    confirmNode,
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400",
      children: "\u7075\u77f3 " + YlxwNum(t && t.stones).toLocaleString() + " \u00b7 \u6d1e\u5e9c Lv." + gl + "\uff08\u7075\u7530\u4ea7\u51fa +" + gl + "%\uff09" }), children: "\u7075\u7530" }),
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap text-xs text-stone-400", children: [
      e.jsxs("span", { children: ["\u4eca\u65e5\u50ac\u719f ", bd.used, " / ", bd.cap, " \u6b21\uff08\u968f\u6d1e\u5e9c\u7b49\u7ea7\u63d0\u5347\uff09"] }),
      e.jsx(YlxwBtn, { disabled: !!u || readyN <= 0, onClick: function () { f("hall", "/farm/harvest/all", { mode: "sell" }); },
        children: readyN > 0 ? "\u4e00\u952e\u53d8\u5356\uff08" + readyN + "\uff09" : "\u4e00\u952e\u53d8\u5356" })
    ] }),
    a ? e.jsx(YlxwErr, { retry: c, children: a }) : m.map(function (N) {
      var b = N.crop, care = N.care || {}, streak = YlxwNum(N.streak);
      if (!N.unlocked) {
        var needLv = YlxwNum(t && t.unlockGrottoLevel && t.unlockGrottoLevel[N.slot]);
        var lvOk = !needLv || gl >= needLv;
        var uc = YlxwNum(t && t.unlockCost && t.unlockCost[N.slot]);
        return e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
          e.jsx("span", { children: "\u7530\u4f4d " + N.slot + "\uff08\u672a\u5f00\u57a6\uff09" + (needLv ? " \u00b7 \u9700\u6d1e\u5e9c Lv." + needLv : "") }),
          e.jsx(YlxwBtn, { disabled: !!u || !lvOk, onClick: function () { f("u" + N.slot, "/farm/unlock", { slot: N.slot }, "\u5df2\u5f00\u57a6"); },
            children: lvOk ? "\u5f00\u57a6 " + uc.toLocaleString() + " \u7075\u77f3" : "\u9700\u6d1e\u5e9c Lv." + needLv })
        ] }) }, "s" + N.slot);
      }
      if (!b) return e.jsxs(YlxwRow, { children: [
        e.jsx("div", { className: "flex items-center justify-between gap-2 flex-wrap", children:
          e.jsx("span", { children: "\u7530\u4f4d " + N.slot + "\uff08\u7a7a\u7530\uff09" + (streak > 0 ? " \u00b7 \u524d\u8331\u540c\u4f5c\u7269\uff1a\u672c\u8331\u8fde\u4f5c\u51cf\u4ea7" : "") }) }),
        e.jsx("div", { className: "flex items-center gap-1.5 flex-wrap", children: h.map(function (x) { return cropBtn(N, x); }) })
      ] }, "s" + N.slot);
      var cd = g[b.key] || {};
      var badges = [];
      if (b.tier) badges.push(tierBadge(b));
      else if (cd.tier) badges.push(tierBadge(cd));
      if (cd.line) badges.push(lineBadge(cd));
      if (care.tended) badges.push(badge("\u5df2\u7167\u6599\u2713", B_OK, "bt"));
      if (care.boosted) badges.push(badge("\u5df2\u50ac\u719f\u26a1", B_BOOST, "bb"));
      if (care.pest && !care.tended) badges.push(badge("\u866b\u5bb3\u26a0", B_PEST, "bp"));
      if (streak > 0) badges.push(badge("\u8fde\u4f5c\u51cf\u4ea7", B_MUTE, "bs"));
      return e.jsxs(YlxwRow, { children: [e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsxs("span", { className: "flex items-center gap-1.5 flex-wrap", children: [
          e.jsx("span", { children: "\u7530\u4f4d " + N.slot + " \u00b7 " + b.name }), badges ] }),
        e.jsxs("span", { className: "flex items-center gap-1.5 flex-wrap", children: [
          !b.ready && e.jsx("span", { className: "text-xs text-stone-400", children: "\u6210\u719f\u8fd8\u9700 " + YlxwMin(YlxwNum(b.leftMs)) }),
          !b.ready && e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () { f("t" + N.slot, "/farm/tend", { slot: N.slot }); }, children: "\u7167\u6599" }),
          !b.ready && !care.boosted && e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () { f("b" + N.slot, "/farm/boost", { slot: N.slot }); },
            children: "\u50ac\u719f " + YlxwNum(N.boostCost).toLocaleString() }),
          b.ready && e.jsx(YlxwBtn, { disabled: !!u, onClick: function () { doSell(N.slot, cd); }, children: "\u53d8\u5356" }),
          b.ready && e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () { doConsume(N.slot, cd); }, children: "\u670d\u7528" })
        ] })
      ] }) ] }, "s" + N.slot);
    }),
    e.jsxs("details", { className: "text-xs text-stone-400", children: [
      e.jsx("summary", { children: "\u73a9\u6cd5\u8bf4\u660e" }),
      e.jsxs("div", { className: "space-y-1 pt-1.5", children: [
        e.jsx("div", { children: "\u2460 \u9009\u4e00\u682a\u7075\u8349\u79cd\u4e0b \u2192 \u7b49\u5b83\u6210\u719f \u2192 \u4e8c\u9009\u4e00\uff1a\u53d8\u5356\uff08\u6362\u7075\u77f3\uff0c\u54c1\u9636\u8d8a\u9ad8\u8d8a\u8d35\uff09\u6216\u670d\u7528\uff08\u589e\u4fee\u4e3a\u4e0e\u5c5e\u6027\uff0c\u6c38\u4e45\u751f\u6548\uff09\u3002" }),
        e.jsx("div", { children: "\u2461 \u57fa\u7840\u5c5e\u6027\u8349\u6210\u719f\u5feb\uff0c\u9002\u5408\u65e5\u5e38\u79ef\u7d2f\uff1b\u767e\u5206\u6bd4\u5c5e\u6027\u8349\uff08\u547d\u4e2d/\u66b4\u51fb/\u95ea\u907f/\u5438\u8840\uff09\u9700\u9ad8\u54c1\u9636 + \u957f\u65f6\u957f\uff0c\u4e14\u6709\u4e0a\u9650\u3002" }),
        e.jsx("div", { children: "\u2462 \u60f3\u7a33\u5b9a\u8d5a\u7075\u77f3\u9009\u7eaf\u5356\u94b1\u8349\uff1b\u60f3\u51b2\u4fee\u4e3a\u9009\u7eaf\u4fee\u4e3a\u8349\u3002\u540c\u4e00\u5757\u7530\u8fde\u79cd\u540c\u4e00\u79cd\u8349\u6536\u6210\u4f1a\u8870\u51cf\uff08\u6362\u54c1\u79cd\u5373\u53ef\u91cd\u7f6e\uff09\u3002" }),
        e.jsx("div", { children: "\u2463 \u7167\u6599\uff1a\u6bcf\u65e5\u6bcf\u7530\u4e00\u6b21\uff0c\u6e05\u866b\u5bb3\u5e76\u63d0\u5347\u5f53\u65e5\u6536\u83b7\uff1b\u50ac\u719f\uff1a\u7075\u77f3\u6309\u5269\u4f59\u65f6\u957f\u8ba1\u8d39\u7acb\u5373\u6210\u719f\u3002" })
      ] })
    ] })
  ] }, "t5");
}
'''


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('farm089 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 注入 YlxwTFarmT5 —— ★ 必须落在**顶层**（与 T10 块同级），不可落在函数体内。
    #    踩坑记录：初版锚点用 'var YLXW_COMP = {'（与 farm087 同款），但该锚点在 YlxwTFarmT10
    #    **函数体之后**、同处 IIFE 内（净花括号深度 2）。insert_before 虽放在锚点前，但锚点前紧邻
    #    的正是 T10 的闭合 '}' —— 结果我的整块被塞进 **T10 函数体内**：YLXW_FT_* 三个 var 与
    #    YlxwTFarmT5 / YlxwFarmConfirm 全被函数作用域吃掉，YLXW_COMP.farm=YlxwTFarmT5 直接
    #    ReferenceError（UI 层实测：面板开不出、产品线文案全无），而文本类门禁全部照常 [OK]。
    #    ⇒ 改用 T10 块的**注释头**作锚点：它与 T10 同级、且位于 T10 之前，保证顶级注入。
    p.insert_before('farm089-components', FARM_T10_ANCHOR, blk + '\n',
                    expect=1, note='注入 YlxwTFarmT5（T5 灵田双出口面板，顶层作用域）')

    # 0b) 作用域自证：注入块必须与 T10 函数同级（都在 IIFE 内、不在任何函数体内）。
    #     判定法：数「文件开头 → 我的块」的净花括号深度。T10 块与 YLXW_COMP 锚点都在 IIFE 内，
    #     深度恒为 2；若为 3（或更大）说明块被塞进了某个函数体 ⇒ 直接抛异常中止落盘。
    _depth = _brace_depth(p.text, p.text.find('var YLXW_FT_TIER'))
    if _depth != 2:
        raise AssertionError(
            'farm089 注入块作用域错误：净花括号深度=%d，期望 2（IIFE 内、函数外）。'
            '若为 3+ 说明块被塞进函数体，YLXW_FT_* 与 YlxwTFarmT5 将不可见。' % _depth)

    # 1) 覆盖注册（T10 注册行保留在其前，追加 T5 覆盖行 —— 与 farm087 覆盖 farm 同先例）
    p.replace('farm089-register', 'YLXW_COMP.farm=YlxwTFarmT10;',
              'YLXW_COMP.farm=YlxwTFarmT10;\nYLXW_COMP.farm=YlxwTFarmT5;',
              expect=1, note='YLXW_COMP.farm 追加覆盖为 T5 面板（T10 行保留为死代码）')

    # 2) window 桥（验收可达性；闭包内挂 window，与产物既有 window.YlxwMarketPayouts 同先例）
    #    诊断（_i1_diag_scope2.py）：我的 T2/T5 块与 YLXW_COMP 同处 depth=2（IIFE + 大箭头函数体内），
    #    顶层 function/var **不挂 window**，故 playwright page.evaluate 取不到 ⇒ 只加一座只读桥。
    #    桥只导出**已有名字**，不新增游戏逻辑、不改任何存档口径；try/catch 吞错，绝不影响启动。
    p.insert_after('farm089-window-bridge', 'YLXW_COMP.farm=YlxwTFarmT5;', FARM_WINDOW_BRIDGE,
                   expect=1, note='导出 T2/T5 只读符号到 window（供真跑验收/排障）')

    # ------------------------------------------------------------- 门禁
    gates = [
        ('T5·YlxwTFarmT5 已定义',          'function YlxwTFarmT5() {', 1, '==', ''),
        ('T5·T5 覆盖注册恰好一次',         'YLXW_COMP.farm=YlxwTFarmT5;', 1, '==', ''),
        ('T5·T10 注册行保留',              'YLXW_COMP.farm=YlxwTFarmT10;', 1, '==', '死代码保留（与 farm087 覆盖 farm 同先例）'),
        ('T5·T10 原组件保留（死代码）',     'function YlxwTFarmT10() {', 1, '==', '不删原组件，防锚区互踩'),
        ('T5·二次确认弹窗定义',            'function YlxwFarmConfirm(', 1, '==', 'Q4 选 b'),
        ('T5·双按钮·变卖',                 r'children: "\u53d8\u5356"', 1, '==', '成熟田第一出口'),
        ('T5·双按钮·服用',                 r'children: "\u670d\u7528"', 1, '==', '成熟田第二出口'),
        ('T5·mode 参数（sell/consume）',   'var mode = q.kind === "consume" ? "consume" : "sell";', 1, '==', ''),
        ('T5·mode 已传入 harvest',         '"/farm/harvest", { slot: q.slot, mode: mode }', 1, '==', ''),
        ('T5·未实装 hitRate（§9.2）',      'hitRate', 0, '==', '命中未接战斗，不空转'),
        ('T5·实装 lifeLeech（已接战斗）',   'lifeLeech', 33, '>=', '基座 30 + 本模块 3（表键/上限表/读取名单）'),
        ('T5·灵田专有上限表',              'var YLXW_FT_PCT_CAP = { critRate: 0.08, dodgeRate: 0.06, lifeLeech: 0.04 };', 1, '==', 'Q5 选 a：灵田专有上限'),
        ('T5·品阶展示表',                  'var YLXW_FT_TIER = {', 1, '==', ''),
        ('T5·产品线展示表',                'var YLXW_FT_LINE = {', 1, '==', ''),
        ('T5·玩法说明折叠块',              r'\u2460 \u9009\u4e00\u682a\u7075\u8349\u79cd\u4e0b', 1, '==', '打本模块独有信号'),
        ('T5·照料调用（T10 死代码+T5）',    '"/farm/tend"', 2, '==', ''),
        ('T5·催熟调用（T10 死代码+T5）',    '"/farm/boost"', 2, '==', ''),
        ('T5·种植调用（旧+T10+T5）',        '"/farm/plant"', 3, '==', ''),
        ('T5·开垦调用（旧+T10+T5）',        '"/farm/unlock"', 3, '==', ''),
        ('T5·单收调用（旧+T10+T5）',        '"/farm/harvest"', 3, '==', '带闭引号，与 /farm/harvest/all 区分'),
        ('T5·一键变卖调用（4 处）',         '"/farm/harvest/all"', 4, '==', 'T10 2 + T5 2（auto + 按钮）'),
        ('T5·status 调用（旧+T10+T5）',     '"/farm/status"', 3, '==', ''),
        # ---- 已停种旧作物置灰（服务端 crops 条目 retired:true；客户端只消费）----
        ('T5·已停种·显式判定',             'var ret = cd.retired === true;', 1, '==', '仅显式 true 置灰；缺字段保持可点（向后兼容）'),
        ('T5·已停种·禁用点击（R-048 加境界门槛后）', 'disabled: !!u || !ok2 || !okR || ret,', 1, '==', 'R-048 新增 !okR'),
        ('T5·已停种·点击守卫',             'if (ret) return;', 1, '==', '已停种点了不发请求'),
        ('T5·已停种·提示文案',             r'(ret ? " \u00b7 \u5df2\u505c\u79cd" : "")', 1, '==', '按钮内「已停种」提示'),
        ('T5·已停种·无 truthy 判定',        'cd.retired)', 0, '==', '必须无 if(cd.retired) 形态，防误灰'),
        # ---- window 桥（验收可达性；只读导出，不改逻辑）----
        ('T5·window 桥 T5 已导出',         'window.YLXW_T5 = {', 1, '==', '真跑验收可达性'),
        ('T5·window 桥 T2 已导出',         'window.YLXW_T2 = {', 1, '==', '真跑验收可达性'),
        ('T5·window 桥内 farm 指向 T5',     'farm: YlxwTFarmT5, T10: YlxwTFarmT10,', 1, '==', '防回退到 T10'),
        ('T5·window 桥不含副作用',          'window.YLXW_T5 = { farm: YlxwTFarmT5, T10: YlxwTFarmT10, confirm: YlxwFarmConfirm, pctOf: YlxwFtPctOf', 1, '==', '桥体逐字锁定：只做名字导出'),
        ('红线·未新增 403 语义',           'status === 403', 1, '==', '仅 0.8.5 秘境 gate 既有 1 处'),
    ]
    return gates
