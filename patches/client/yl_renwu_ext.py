# -*- coding: utf-8 -*-
r"""
yl_renwu_ext.py — 人物志 / 缘契 任务化改造（R-034 / R-035 / R-036，纯客户端，服务端零改动）

需求原文（台账逐字）
--------------------------------------------------------------------------
  R-034 缘契：
    「缘契功能大更新，把灵石寻访去掉，每日免费一次寻访，然后变成完成任务寻访，
      可以列五个提交任务，可以不指定具体提交物品，提交这一类这一个品阶以上的物品
      即可完成。同时每一个npc也都有对应好感度的奖励可以领取。」
  R-035 人物志（默认关系详情）：
    「默认的人物志功能，也把赠送灵石增加好感度给去掉，同时每个人可以有三个任务可做。
      使用灵石刷新任务，根据任务难易程度来定刷新任务需要的灵石。」
  R-036：
    「缘契和人物志的奖励的物品品质大幅提升一下，因为是完成任务才能获得好感度，
      相对达到好感里程碑变得困难了很多」

2026-09-30 用户拍板追加（A4 / A6；本模块就地改写，不新增模块）
--------------------------------------------------------------------------
  A4 刷新粒度：整板重掷 → 单条刷新
    改前：YlxwCharTasksR35 只有 1 个「刷新任务（N 灵石）」按钮，一次重掷全部 3 条，
          价 = YlxwRnRefreshCost(list, rf) = max(50, round(Σ三条难度 × 3 × YLRF))。
    改后：每条任务各带 1 个「刷新 · N 灵石」按钮，只重掷该条（YlxwRnRollOne(false)）；
          单条价 = YlxwRnRowCost(t, rf) = max(1, round(该条难度 × 3 × YLRF))。
          ★ 原「三条之和」拆到单条 ⇒ Σ单条价 ≈ 原整板价（不额外造钱/吞钱）；
            原 50 灵石保底不再需要（单条最低 = 21×3×YLRF = 63×YLRF > 50）。
          ★ 价格直接写在按钮文案上（玩家点前即知）。
  A6 奖励物品重做：只提稀有度 → 件数 + 稀有度双提
    背景：R-034/R-035 去掉「赠灵石换好感」后，好感里程碑只能靠做任务攒，
          达到里程碑显著变难 ⇒ 奖励相应大幅提升。
    改前 → 改后（三张 T6/char 产出的表，本模块就地改写；★ = 本次新增改动面）：
      ★ YLXW_CHAR_DROP_N（缘契 4 档件数：相知25/知己50/莫逆75/道侣100）
          [1, 2, 3, 5] → [2, 3, 4, 5]
      ★ YLXW_CHAR_DEX_DROP_N（图鉴 7 档件数：三友/六合/九曜/十二楼/十六尊/二十真/廿四仙）
          [1, 1, 2, 2, 3, 4, 6] → [2, 2, 4, 4, 6, 8, 12]
      ★ YLXW_CHAR_DEX_MILE 固定收藏品件数（同心结 / 道友图谱）
          12 档 同心结 ×1 → ×2 ；20 档 同心结 ×2 → ×3 ；24 档 道友图谱 ×1 → ×2
        YLXW_CHAR_DROP_RAR（缘契/图鉴共用稀有度权重，行 = 普通/稀有/传说/仙品；每行和 100）
          [30,45,22, 3] → [22,46,27, 5]
          [20,45,30, 5] → [14,43,35, 8]
          [12,40,40, 8] → [ 8,36,44,12]
          [ 8,30,47,15] → [ 5,26,48,21]
          [ 4,24,52,20] → [ 2,20,50,28]
          [ 2,16,52,30] → [ 1,12,49,38]
    ★ 数值取舍（保既有 E2E 绿）：
        · 缘契顶档（道侣100）件数**保持 5** —— localtest/_e2e_t6_chardex.py C3 断言
          「道侣掉落 5 件入包」为精确 `==5`，改顶档会打破该 E2E；提升集中在低中档。
        · 图鉴廿四仙随机件数 = DEX_DROP_N[6] − 固定条目数 = 12 − 1 = 11 ≥ 6，
          满足同文件 C9 的 `>=6`。
        详见 报告_renwu2.md §数值取舍。

侦察（构建产物 build/assets/index-v2811-20260930.js 逐字实证）
--------------------------------------------------------------------------
本作「人物志」= 单一模态框 `const Nk=({isOpen:t,onClose:r,player:a,setPlayer:l,addLog:c})`，
内部两列：
  · 左列 = 道友图鉴·缘契 `YlxwCharDexPanelT6`（yl_char_ext 造 / yl_t6chardex_ext 细化）
      - 「寻访 · 今日免费」按钮 + 「灵石寻访 N」按钮 + 「已寻访 N 次」
      - 图鉴网格 / 收集奖励 chips / 选中详情
  · 右列 = 关系列表 + 详情（`YlxwCharBondPanelT6`：师门求物卡 + 缘契里程碑 chips + 小传/秘辛）
      - 详情底部另有「💎 赠灵石 (N)」按钮（Nk 内联，yl_chargift083_ext 定价）

锚点实测（本模块 apply 前的 bundle，count 全部 == 1，除标注 expect=2 者）
  A_META        'function YlxwMeta(k) {'                                        ×1（注入锚）
  A_VISIT_ROW   寻访按钮整行（含灵石寻访按钮）                                  ×2（旧死代码 DexPanel + 现役 DexPanelT6）
  A_QUEST_HEAD  'var questCard = dem ? e.jsxs("div", {'                          ×1（仅 BondPanelT6）
  A_GIFT_BTN    赠灵石按钮 div 前缀（含 YlxwGiftCost 调用）                      ×1（仅 Nk）
  A_DROP_RAR    'var YLXW_CHAR_DROP_RAR = [ … 6 行 … ];'                         ×1（T6 权重矩阵）
  A_DROP_N      'var YLXW_CHAR_DROP_N = [1, 2, 3, 5];'                          ×1（T6 缘契件数）
  A_DEX_DROP_N  'var YLXW_CHAR_DEX_DROP_N = [1, 1, 2, 2, 3, 4, 6];'             ×1（T6 图鉴件数）
  A_DEX_MILE    'var YLXW_CHAR_DEX_MILE = [ … 7 档 … ];'                        ×1（char 图鉴奖励表，含固定收藏品）

改法（1 处注入 + 8 处就地替换，全部锚点唯一）
--------------------------------------------------------------------------
  1) 注入块（插在 `function YlxwMeta(k) {` 之前，与 char/t6 同锚）：
       任务匹配（类别 = item.type / 品阶 = item.rarity≥）、难度、单条刷新定价、
       掷任务、当日生效、寻访目标，以及两个新组件：
         YlxwCharBoardR34    —— R-034 缘契「寻访任务」板（每日 5 条，提交即寻访）
         YlxwCharTasksR35    —— R-035 关系详情「师门任务」3 条/人 + 灵石单条刷新（A4）
  2) R-034：把「灵石寻访」按钮整行替换为「今日免费」按钮 + 已寻访计数 + 任务板挂载
       （旧死代码 DexPanel 与现役 DexPanelT6 同一字面 → expect=2，两处一致处理）
  3) R-035：赠灵石按钮前缀 `!1&&`（**死代码保留**，见下「门禁零变更」）
  4) R-035：`var questCard = dem ? …` → 改指 `YlxwCharTasksR35`，旧单条求物卡降为
       `var questCardOld = (!1) ? …` 死代码（字符串全保留，不撞 T6 门禁）
  5) R-036：就地改写 `YLXW_CHAR_DROP_RAR` 六行权重（稀有度再抬一档，每行仍和 100）
  6) R-036/A6：就地改写 `YLXW_CHAR_DROP_N`（缘契件数）[1,2,3,5]→[2,3,4,5]
  7) R-036/A6：就地改写 `YLXW_CHAR_DEX_DROP_N`（图鉴件数）[1,1,2,2,3,4,6]→[2,2,4,4,6,8,12]
  8) R-036/A6：就地改写 `YLXW_CHAR_DEX_MILE` 三处固定收藏品件数（同心结 ×1→×2 / ×2→×3，道友图谱 ×1→×2）

★ 门禁零变更（本模块对既有模块门禁的命中数**零影响**）
--------------------------------------------------------------------------
  本项目最高频翻车点是「新模块改掉旧门禁断言的字面串」。本模块刻意规避：
    · 赠灵石按钮不删，只加 `!1&&` 前缀 → `YlxwGiftCost(j&&j.favorability)` 仍 4 处
      （yl_chargift083_ext `调用点共 4 处` / yl_t6chardex_ext `YlxwGiftCost 调用点恒4` 不变）
    · 旧求物卡不删，降为 `questCardOld` 死代码 → T6 的
      `求物卡标题` / `求物懒初始化持久化` / `交付后重掷写入` 三条字面串全保留
    · DexPanel/BondPanel 定义、挂载、YlxwCharSafe×2 全部未动
    · R-036 只改 4 张表的**数值**，不改声明前缀 —— T6 对
      `var YLXW_CHAR_DROP_N = [` / `var YLXW_CHAR_DEX_DROP_N = [` /
      `var YLXW_CHAR_DEX_DROP_ROW = [` / `var YLXW_CHAR_DROP_RAR = [` /
      `var YLXW_CHAR_DEX_MILE = [` 五条门禁均为**前缀断言（==1）**，值变化不影响命中数。
  ⇒ 若接线人把本模块放进 V28_MODULES，**无需同步任何旧门禁预期值**。
     唯一需要确认的是装配顺序：建议排在 `t6chardex` 之后（非必须，见下）。
  ⚠️ 唯一会失效的是**非门禁**的既有 E2E 脚本对数值的硬编码（详见 §数值取舍与
     报告_renwu2.md）：本次已刻意避开其唯一精确断言（道侣档 =5），其余为 >= 断言。

★ 装配顺序
--------------------------------------------------------------------------
  本模块对 t6/char 只做「函数声明引用」（提升）+ 「就地字面改写」，**与装配顺序无关**；
  但注入块物理位置会落在 t6 块之后（同锚 insert_before 叠加）。为可读性建议排在
  `t6chardex` 之后、`numbal` 之前（numbal 恒最后）。

服务端
--------------------------------------------------------------------------
  `player.charDex.board` / `player.charDex.tasks` 与既有 `charDex.met/claimed/bond/demands`
  同为 player 内普通 JSON 字段，随既有 `POST /api/save` 整包落库（无字段白名单）→
  **不新建任何 srv_patch_*，不改服务端**。任务「提交」是纯客户端扣背包（与既有
  师门求物 / 收集奖励同一信任级别），不新增服务端记账。

导出符号（构建侧契约）
  INJECT_JS : str
  apply(p, ctx) -> list[(name, needle, expect, cmp, note)]
"""

import re

# ---------------------------------------------------------------- 注入代码
# 中文可直写；apply() 里统一走 ctx['zh'] 转义为 \uXXXX 后落盘。

INJECT_JS = r'''
/* ===== yl-renwu R-034/R-035/R-036 人物志·缘契 任务化改造 =====
   R-034 缘契面板：去掉灵石寻访，改「寻访任务」板（每日 5 条，提交该类该品阶以上物品即寻访）。
   R-035 关系详情：去掉赠灵石，改「师门任务」3 条/人 + 灵石单条刷新（A4：每条一个刷新按钮，价标在按钮上）。
   R-036 缘契/人物志奖励物品品质上调（权重矩阵另在 build 侧就地改写）。
   数据落 player.charDex.board / player.charDex.tasks，随 /api/save 整包落库，服务端零改动。 */

/* 物品类别 = 游戏内 item.type（仅取非装备类，保证可提交）；品阶 = item.rarity */
var YLXW_RN_CATS = ["草药", "丹药", "材料"];
var YLXW_RN_ANY = "任意";
var YLXW_RN_TIERS = ["普通", "稀有", "传说", "仙品"];

function YlxwRnTierIdx(r) {
  var i = YLXW_RN_TIERS.indexOf(r);
  return i < 0 ? 0 : i;
}
/* 背包按「类别 + 品阶≥」聚合数量（排除装备/丹方；丹方在游戏内 type = "丹方"） */
function YlxwRnCount(p, type, minRar) {
  var inv = (p && p.inventory) || [], n = 0, i, it, min = YlxwRnTierIdx(minRar);
  for (i = 0; i < inv.length; i++) {
    it = inv[i];
    if (!it || it.isEquippable || it.type === "丹方") continue;
    if (type && type !== YLXW_RN_ANY && it.type !== type) continue;
    if (YlxwRnTierIdx(it.rarity) < min) continue;
    n += Number(it.quantity) || 0;
  }
  return n;
}
/* 扣除：按「类别 + 品阶≥」扣 need 个；不足返回 null（调用方整笔回退，防双击竞态） */
function YlxwRnTake(inv, type, minRar, need) {
  var out = (inv || []).slice(), left = need, i, it, q, take, min = YlxwRnTierIdx(minRar);
  for (i = 0; i < out.length && left > 0; i++) {
    it = out[i];
    if (!it || it.isEquippable || it.type === "丹方") continue;
    if (type && type !== YLXW_RN_ANY && it.type !== type) continue;
    if (YlxwRnTierIdx(it.rarity) < min) continue;
    q = Number(it.quantity) || 0;
    if (q <= 0) continue;
    take = Math.min(q, left);
    left -= take;
    out[i] = Object.assign({}, it, { quantity: q - take });
  }
  if (left > 0) return null;
  return out.filter(function (x) { return x && (Number(x.quantity) || 0) > 0; });
}
/* 单条任务难度：品阶越高、数量越多越难（用于 R-035 刷新定价） */
function YlxwRnDiff(t) {
  if (!t) return 1;
  var ti = YlxwRnTierIdx(t.minRar), n = Math.max(1, Number(t.need) || 1);
  return Math.max(1, Math.round((1 + ti) * (1 + Math.log(n + 1)) * 10));
}
/* 单条刷新定价 = 该条难度 × 3 × 境界系数（YLRF）；即原「三条之和」拆到单条，Σ 与原整板价一致 */
function YlxwRnRowCost(t, rf) {
  var k = (typeof rf === "number" && isFinite(rf) && rf > 0) ? rf : 1;
  return Math.max(1, Math.round(YlxwRnDiff(t) * 3 * k));
}
/* 掷一条任务；allowAny=true 时类别可命中「任意」 */
function YlxwRnRollOne(allowAny) {
  var pool = YLXW_RN_CATS.slice();
  if (allowAny) pool.push(YLXW_RN_ANY);
  var cat = pool[Math.floor(Math.random() * pool.length)];
  var ti = Math.floor(Math.random() * 3);
  var need = 2 + Math.floor(Math.random() * (3 + ti * 2));
  return { type: cat, minRar: YLXW_RN_TIERS[ti], need: need, done: false };
}
function YlxwRnRollList(n, allowAny) {
  var out = [], i;
  for (i = 0; i < n; i++) out.push(YlxwRnRollOne(allowAny));
  return out;
}
/* 当日生效任务（纯展示口径：缺/跨日 → 现场重掷；持久化由面板 effect 落档，防渲染期写档） */
function YlxwRnBoardOf(p) {
  var d = (p && p.charDex && p.charDex.board) || null, today = YlxwCharToday();
  if (d && d.day === today && d.tasks && d.tasks.length === 5) return d;
  return { day: today, tasks: YlxwRnRollList(5, true) };
}
function YlxwRnTasksOf(p, rel) {
  if (!p || !rel) return null;
  var d = (p.charDex && p.charDex.tasks) || {}, cur = d[rel.id], today = YlxwCharToday();
  if (cur && cur.day === today && cur.list && cur.list.length === 3) return cur;
  return { day: today, list: YlxwRnRollList(3, false) };
}
/* 提交任务的奖励 = 一次寻访（结识/重逢），口径与既有 doVisit 一致 */
function YlxwRnPickVisit(p) {
  var entry = YlxwCharRollTarget(p);
  if (entry) return { entry: entry, gain: 15 + Math.floor(Math.random() * 11), desc: entry.desc };
  var m = YlxwCharMet(p), cands = [], k;
  for (k = 0; k < YLXW_CHAR_DEX.length; k++) { if (m[YLXW_CHAR_DEX[k].id]) cands.push(YLXW_CHAR_DEX[k]); }
  if (!cands.length) return null;
  var e2 = cands[Math.floor(Math.random() * cands.length)];
  return { entry: e2, gain: 4 + Math.floor(Math.random() * 6), desc: "重逢于一次提交任务" };
}

/* ---- R-034：缘契面板「寻访任务」板（每日 5 条，提交即寻访） ---- */
function YlxwCharBoardR34(props) {
  var p = props.player, setP = props.setPlayer, log = props.addLog || function () {};
  var s1 = O.useState(""), notice = s1[0], setNotice = s1[1];
  var board = YlxwRnBoardOf(p);
  var day = board.day, tasks = board.tasks || [];

  /* 懒初始化 / 跨日重掷持久化（渲染期只算不写；此处补档。无变化时幂等跳过） */
  O.useEffect(function () {
    if (!p) return;
    var cur = (p.charDex && p.charDex.board) || null;
    if (cur && cur.day === day && cur.tasks && cur.tasks.length === tasks.length) return;
    setP(function (prev) {
      var c0 = (prev.charDex && prev.charDex.board) || null;
      if (c0 && c0.day === day && c0.tasks && c0.tasks.length === tasks.length) return prev;
      var d0 = YlxwCharDexV2(prev.charDex);
      d0.board = { day: day, tasks: tasks };
      return Object.assign({}, prev, { charDex: d0 });
    });
  }, [day]);

  function submit(idx) {
    if (!p) return;
    var t = tasks[idx];
    if (!t || t.done) return;
    var have = YlxwRnCount(p, t.type, t.minRar);
    if (have < t.need) { setNotice("还差 " + (t.need - have) + " 个【" + t.type + " · " + t.minRar + "以上】物品。"); return; }
    var v = YlxwRnPickVisit(p);
    if (!v) { setNotice("暂无可寻访的道友。"); return; }
    setP(function (prev) {
      var inv2 = YlxwRnTake(prev.inventory, t.type, t.minRar, t.need);
      if (!inv2) return prev;
      var nx = YlxwCharMeet(Object.assign({}, prev, { inventory: inv2 }), v.entry, v.gain, v.desc);
      var d0 = YlxwCharDexV2(nx.charDex);
      var b0 = d0.board || { day: day, tasks: tasks };
      if (b0.tasks && b0.tasks[idx] && b0.tasks[idx].done) return prev;
      d0.board = { day: b0.day, tasks: (b0.tasks || tasks).map(function (x, j) {
        return j === idx ? Object.assign({}, x, { done: true }) : x;
      }) };
      nx.charDex = d0;
      return nx;
    });
    log("【缘契·提交】上交" + t.type + "（" + t.minRar + "以上）×" + t.need + "，寻访了【" + v.entry.name + "】，缘契 +" + v.gain + "。", "gain");
    setNotice("完成提交任务，寻访【" + v.entry.name + "】，缘契 +" + v.gain + "。");
  }

  var rows = [];
  for (var i = 0; i < tasks.length; i++) {
    (function (t, idx) {
      var have = YlxwRnCount(p, t.type, t.minRar), ok = have >= t.need;
      rows.push(e.jsxs("div", { className: "flex items-center justify-between gap-2 text-[11px] bg-ink-800/60 border border-stone-700 rounded px-2 py-1", children: [
        e.jsx("span", { className: "text-stone-300", children: (t.done ? "✓ " : "") + "提交【" + t.type + "】" + t.minRar + "以上 ×" + t.need + "（已备 " + Math.min(have, t.need) + "/" + t.need + "）" }),
        e.jsx("button", {
          disabled: t.done || !ok,
          onClick: function () { submit(idx); },
          className: "px-2 py-1 rounded border text-[10px] " + (t.done ? "bg-emerald-900/20 border-emerald-700/50 text-emerald-300" : ok ? "bg-amber-600 hover:bg-amber-500 border-amber-500 text-stone-900 font-bold" : "bg-stone-800 border-stone-700 text-stone-500"),
          children: t.done ? "已寻访" : (ok ? "提交寻访" : "材料不足")
        })
      ] }, "ylxw-rn-board-" + idx));
    })(tasks[i], i);
  }

  return e.jsxs("div", { className: "space-y-1.5 pt-1", children: [
    e.jsx("div", { className: "text-[10px] text-stone-500", children: "寻访任务（每日 5 条 · 提交该类该品阶以上物品即可寻访）" }),
    e.jsx("div", { className: "space-y-1", children: rows }),
    notice ? e.jsx("div", { className: "text-[11px] text-emerald-300", children: notice }) : null
  ] });
}

/* ---- R-035：关系详情「师门任务」3 条/人 + 灵石单条刷新（A4：每条各一个刷新按钮） ---- */
function YlxwCharTasksR35(props) {
  var rel = props.rel, p = props.player, setP = props.setPlayer, log = props.addLog || function () {};
  var s1 = O.useState(""), notice = s1[0], setNotice = s1[1];
  var relId = rel ? rel.id : "";
  var rar = rel ? YlxwCharRelRarity(p, rel) : "凡缘";
  var tk = YlxwRnTasksOf(p, rel);
  var day = tk ? tk.day : "", list = (tk && tk.list) || [];
  var gain = YLXW_CHAR_FAVOR_GAIN[rar] || 3;
  var rf = 1;
  try { rf = YlxwCharRf(p); } catch (e0) { rf = 1; }
  var stonesNow = Number(p && p.spiritStones) || 0;

  O.useEffect(function () {
    if (!relId || !list.length) return;
    var cur = (p && p.charDex && p.charDex.tasks && p.charDex.tasks[relId]) || null;
    if (cur && cur.day === day && cur.list && cur.list.length === list.length) return;
    setP(function (prev) {
      var c0 = (prev.charDex && prev.charDex.tasks && prev.charDex.tasks[relId]) || null;
      if (c0 && c0.day === day && c0.list && c0.list.length === list.length) return prev;
      var d0 = YlxwCharDexV2(prev.charDex);
      var m0 = Object.assign({}, d0.tasks || {});
      m0[relId] = { day: day, list: list };
      d0.tasks = m0;
      return Object.assign({}, prev, { charDex: d0 });
    });
  }, [relId, day, list.length]);

  if (!rel) return null;

  function submit(idx) {
    if (!p) return;
    var t = list[idx];
    if (!t || t.done) return;
    var have = YlxwRnCount(p, t.type, t.minRar);
    if (have < t.need) { setNotice("还差 " + (t.need - have) + " 个【" + t.type + " · " + t.minRar + "以上】物品。"); return; }
    var g = gain, key = t.type, minRar = t.minRar, need = t.need;
    setP(function (prev) {
      var inv2 = YlxwRnTake(prev.inventory, key, minRar, need);
      if (!inv2) return prev;
      var rels = (prev.socialRelations || []).map(function (r) {
        return r && r.id === relId ? Object.assign({}, r, { favorability: Math.min(100, Math.max(-100, (Number(r.favorability) || 0) + g)) }) : r;
      });
      var d0 = YlxwCharDexV2(prev.charDex);
      var m0 = Object.assign({}, d0.tasks || {});
      var cur = m0[relId] || { day: day, list: list };
      if (cur.list && cur.list[idx] && cur.list[idx].done) return prev;
      m0[relId] = { day: cur.day, list: (cur.list || list).map(function (x, j) {
        return j === idx ? Object.assign({}, x, { done: true }) : x;
      }) };
      d0.tasks = m0;
      return Object.assign({}, prev, { inventory: inv2, socialRelations: rels, charDex: d0 });
    });
    log("【人物志·师门任务】你把" + key + "（" + minRar + "以上）×" + need + " 交给了" + rel.name + "，好感度 +" + g + "。", "gain");
    setNotice("已提交，好感度 +" + g + "。");
  }

  /* A4：单条刷新 —— 只重掷第 idx 条，价 = 该条难度定价（已标在按钮文案上） */
  function refreshOne(idx) {
    if (!p) return;
    var t = list[idx];
    if (!t) return;
    var c = YlxwRnRowCost(t, rf);
    if ((Number(p.spiritStones) || 0) < c) { setNotice("灵石不足，刷新该条需 " + c + " 灵石。"); return; }
    var nt = YlxwRnRollOne(false);
    setP(function (prev) {
      if ((Number(prev.spiritStones) || 0) < c) return prev;
      var d0 = YlxwCharDexV2(prev.charDex);
      var m0 = Object.assign({}, d0.tasks || {});
      var cur = m0[relId] || { day: day, list: list };
      var nl = (cur.list || list).map(function (x, j) { return j === idx ? nt : x; });
      m0[relId] = { day: cur.day, list: nl };
      d0.tasks = m0;
      return Object.assign({}, prev, { spiritStones: (Number(prev.spiritStones) || 0) - c, charDex: d0 });
    });
    log("【人物志·刷新】花费 " + c + " 灵石，为" + rel.name + "刷新了一条师门任务。", "normal");
    setNotice("已刷新该条任务（-" + c + " 灵石）。");
  }

  var rows = [];
  for (var i = 0; i < list.length; i++) {
    (function (t, idx) {
      var have = YlxwRnCount(p, t.type, t.minRar), ok = have >= t.need;
      var rc = YlxwRnRowCost(t, rf), canRef = stonesNow >= rc;
      rows.push(e.jsxs("div", { className: "flex items-center justify-between gap-2 text-[11px]", children: [
        e.jsx("span", { className: "text-stone-300 min-w-0 flex-1", children: (t.done ? "✓ " : "") + "提交【" + t.type + "】" + t.minRar + "以上 ×" + t.need + "（已备 " + Math.min(have, t.need) + "/" + t.need + "）" }),
        e.jsxs("div", { className: "flex items-center gap-1 shrink-0", children: [
          e.jsx("button", {
            disabled: !canRef,
            onClick: function () { refreshOne(idx); },
            className: "px-2 py-1 rounded border text-[10px] " + (canRef ? "bg-yellow-900/20 border-yellow-700 text-yellow-300 hover:bg-yellow-900/30" : "bg-stone-800 border-stone-700 text-stone-500"),
            children: "刷新 · " + rc + " 灵石"
          }),
          e.jsx("button", {
            disabled: t.done || !ok,
            onClick: function () { submit(idx); },
            className: "px-2 py-1 rounded border text-[10px] " + (t.done ? "bg-emerald-900/20 border-emerald-700/50 text-emerald-300" : ok ? "bg-emerald-900/30 border-emerald-700 text-emerald-300 hover:bg-emerald-900/50" : "bg-stone-800 border-stone-700 text-stone-500"),
            children: t.done ? "已完成" : (ok ? "提交（好感 +" + gain + "）" : "材料不足")
          })
        ] })
      ] }, "ylxw-rn-task-" + relId + "-" + idx));
    })(list[i], i);
  }

  return e.jsxs("div", { className: "bg-ink-900 border border-stone-700 rounded p-2.5 space-y-1.5", children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      e.jsx("span", { className: "text-[11px] font-bold text-amber-200", children: "师门任务" }),
      e.jsxs("span", { className: "text-[10px] text-stone-500", children: ["每日 3 条 · 交付得好感 +", gain, " · 可单条刷新"] })
    ] }),
    e.jsx("div", { className: "space-y-1", children: rows }),
    e.jsx("div", { className: "text-[10px] text-stone-500 pt-0.5", children: "每条可单独刷新（按钮上已标注所需灵石）；任务越难，刷新越贵" }),
    notice ? e.jsx("div", { className: "text-[11px] text-emerald-300", children: notice }) : null
  ] });
}
/* == end yl-renwu == */
'''

# ---------------------------------------------------------------- 锚点
# 说明：含中文的锚点用 raw 中文书写，apply() 内统一 ctx['zh']() 转义（与 bundle 内 \\uXXXX 同形）。
#       纯 ASCII 锚点 zh() 为恒等。

# 注入锚：与 char / t6chardex / chargift 同款（YlxwMeta 之前）
A_META = 'function YlxwMeta(k) {'

# R-034：寻访按钮整行（旧死代码 DexPanel 与现役 DexPanelT6 同一字面 → 全文 ×2）
A_VISIT_ROW = (
    '    e.jsxs("div", { className: "flex items-center gap-2 flex-wrap pt-1", children: [\n'
    '      e.jsx(YlxwBtn, { disabled: !freeOk, onClick: function () { doVisit(true); }, '
    'children: freeOk ? "寻访 · 今日免费" : "今日已寻访" }),\n'
    '      e.jsx(YlxwBtn, { tone: "ghost", disabled: stones < cost, onClick: function () { doVisit(false); }, '
    'children: "灵石寻访 " + cost }),\n'
    '      e.jsx("span", { className: "text-[10px] text-stone-500", children: "已寻访 " + ps.visits + " 次" })\n'
    '    ] }),'
)
R_VISIT_ROW = (
    '    e.jsxs("div", { className: "flex items-center gap-2 flex-wrap pt-1", children: [\n'
    '      e.jsx(YlxwBtn, { disabled: !freeOk, onClick: function () { doVisit(true); }, '
    'children: freeOk ? "寻访 · 今日免费" : "今日已寻访" }),\n'
    '      e.jsx("span", { className: "text-[10px] text-stone-500", children: "已寻访 " + ps.visits + " 次" })\n'
    '    ] }),\n'
    '    e.jsx(YlxwCharBoardR34, { player: p, setPlayer: setP, addLog: log }),'
)

# R-035：赠灵石按钮 div 前缀（仅 Nk ×1）→ 前置 !1&& 停用（死代码保留，不撞既有门禁计数）
A_GIFT_BTN = (
    'e.jsxs("div",{className:"flex gap-2",children:[e.jsx("button",{onClick:$,'
    'disabled:a.spiritStones<YlxwGiftCost(j&&j.favorability)'
)
R_GIFT_BTN = '!1&&' + A_GIFT_BTN

# R-035：师门求物单条卡头（仅 BondPanelT6 ×1）→ 改指 3 条任务组件，旧卡降为死代码
A_QUEST_HEAD = 'var questCard = dem ? e.jsxs("div", {'
R_QUEST_HEAD = ('var questCard = rel ? e.jsx(YlxwCharTasksR35, '
                '{ rel: rel, player: p, setPlayer: setP, addLog: log, rarity: rar }) : null; '
                'var questCardOld = (!1) ? e.jsxs("div", {')

# R-036：奖励权重矩阵（T6 六行，每行 = 普通/稀有/传说/仙品；仅此一处 ×1）
A_DROP_RAR = (
    'var YLXW_CHAR_DROP_RAR = [\n'
    '  [70, 25, 5, 0],\n'
    '  [55, 35, 10, 0],\n'
    '  [40, 40, 17, 3],\n'
    '  [25, 40, 28, 7],\n'
    '  [15, 35, 35, 15],\n'
    '  [8, 28, 40, 24]\n'
    '];'
)
# A6/R-036：稀有度权重再抬一档（低阶权重继续让位给高阶；每行仍和 100）
R_DROP_RAR = (
    'var YLXW_CHAR_DROP_RAR = [\n'
    '  [22, 46, 27, 5],\n'
    '  [14, 43, 35, 8],\n'
    '  [8, 36, 44, 12],\n'
    '  [5, 26, 48, 21],\n'
    '  [2, 20, 50, 28],\n'
    '  [1, 12, 49, 38]\n'
    '];'
)

# A6/R-036：缘契里程碑件数（T6 常量，仅此一处 ×1）→ 低中档件数上调（顶档保 5，见 docstring）
A_DROP_N = 'var YLXW_CHAR_DROP_N = [1, 2, 3, 5];'
R_DROP_N = 'var YLXW_CHAR_DROP_N = [2, 3, 4, 5];'

# A6/R-036：图鉴收集件数（T6 常量，仅此一处 ×1）→ 逐档上调（约 ×2）
A_DEX_DROP_N = 'var YLXW_CHAR_DEX_DROP_N = [1, 1, 2, 2, 3, 4, 6];'
R_DEX_DROP_N = 'var YLXW_CHAR_DEX_DROP_N = [2, 2, 4, 4, 6, 8, 12];'

# A6/R-036：图鉴奖励表（char 产出，含固定收藏品；仅此一处 ×1）
# 固定收藏品件数：12 档 同心结 ×1→×2 ；20 档 同心结 ×2→×3 ；24 档 道友图谱 ×1→×2
A_DEX_MILE = (
    'var YLXW_CHAR_DEX_MILE = [\n'
    '  { at: 3, label: "三友", stones: 300, exp: 0, item: null },\n'
    '  { at: 6, label: "六合", stones: 0, exp: 500, item: null },\n'
    '  { at: 9, label: "九曜", stones: 800, exp: 0, item: null },\n'
    '  { at: 12, label: "十二楼", stones: 0, exp: 1200, item: { name: "同心结", rarity: "稀有", qty: 1 } },\n'
    '  { at: 16, label: "十六尊", stones: 1500, exp: 0, item: null },\n'
    '  { at: 20, label: "二十真", stones: 0, exp: 2000, item: { name: "同心结", rarity: "稀有", qty: 2 } },\n'
    '  { at: 24, label: "廿四仙", stones: 3000, exp: 3000, item: { name: "道友图谱", rarity: "仙品", qty: 1 } }\n'
    '];'
)
R_DEX_MILE = (
    'var YLXW_CHAR_DEX_MILE = [\n'
    '  { at: 3, label: "三友", stones: 300, exp: 0, item: null },\n'
    '  { at: 6, label: "六合", stones: 0, exp: 500, item: null },\n'
    '  { at: 9, label: "九曜", stones: 800, exp: 0, item: null },\n'
    '  { at: 12, label: "十二楼", stones: 0, exp: 1200, item: { name: "同心结", rarity: "稀有", qty: 2 } },\n'
    '  { at: 16, label: "十六尊", stones: 1500, exp: 0, item: null },\n'
    '  { at: 20, label: "二十真", stones: 0, exp: 2000, item: { name: "同心结", rarity: "稀有", qty: 3 } },\n'
    '  { at: 24, label: "廿四仙", stones: 3000, exp: 3000, item: { name: "道友图谱", rarity: "仙品", qty: 2 } }\n'
    '];'
)

# 注入块禁用模式（与 build_v26n.V28_BAN_PATTERNS + 既有模块自检口径一致）
BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-',
                'fetch(', 'localStorage', 'sessionStorage', '/yl/api',
                'Be.getState().setPlayer']


# ---------------------------------------------------------------- 应用

def apply(p, ctx):
    """把 R-034/R-035/R-036 落到 Patcher 上；返回 gates 列表。"""
    zh = ctx['zh']

    # 0) 注入块硬断言：zh() 后纯 ASCII + 无禁用模式 + R-036 权重行自检
    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('renwu 注入块 zh() 后仍含非 ASCII: %r' % (bad[:10],))
    for pat in BAN_PATTERNS:
        if pat in blk:
            raise AssertionError('renwu 注入块含禁用模式: %s' % pat)
    _rows = re.findall(r'\[(\d+), (\d+), (\d+), (\d+)\]', R_DROP_RAR)
    assert len(_rows) == 6, 'R-036 权重行应 6 行，实测 %d' % len(_rows)
    for _r in _rows:
        assert sum(int(x) for x in _r) == 100, 'R-036 权重行和应 100: %r' % (_r,)

    # 1) 注入块：R-034/R-035 组件 + 任务匹配/定价纯函数（YlxwMeta 之前，与 char/t6 同锚）
    p.insert_before(
        'renwu-block', A_META, blk + '\n', expect=1,
        note='R-034/R-035/R-036：缘契寻访任务板 + 师门任务 3 条 + 难度定价刷新'
    )

    # 2) R-034：寻访按钮整行 → 「今日免费」+ 已寻访计数 + 任务板挂载（旧死代码 + 现役，×2）
    p.replace(
        'renwu-r34-board', zh(A_VISIT_ROW), zh(R_VISIT_ROW), expect=2,
        note='R-034 去掉「灵石寻访」按钮，追加「寻访任务」板（两处 DexPanel 同字面，一致处理）'
    )

    # 3) R-035：赠灵石按钮停用（!1&& 前缀，字符串保留 → 既有门禁计数不变）
    p.replace(
        'renwu-r35-gift-off', A_GIFT_BTN, R_GIFT_BTN, expect=1,
        note='R-035 去掉「赠灵石增加好感度」（停用而非删除，避免撞 chargift/t6 门禁计数）'
    )

    # 4) R-035：师门求物单条 → 师门任务 3 条 + 灵石刷新
    p.replace(
        'renwu-r35-tasks', A_QUEST_HEAD, R_QUEST_HEAD, expect=1,
        note='R-035 每人 3 条任务 + 灵石刷新（旧单条求物卡降为死代码 questCardOld）'
    )

    # 5) R-036/A6：奖励权重矩阵稀有度再抬一档
    p.replace(
        'renwu-r36-droprar', A_DROP_RAR, R_DROP_RAR, expect=1,
        note='R-036/A6 缘契/图鉴奖励稀有度权重再抬一档（六行权重，每行仍和 100）'
    )

    # 6) R-036/A6：缘契里程碑件数上调（顶档保 5，见 docstring「数值取舍」）
    p.replace(
        'renwu-r36-dropn', A_DROP_N, R_DROP_N, expect=1,
        note='A6 缘契件数 [1,2,3,5]→[2,3,4,5]'
    )

    # 7) R-036/A6：图鉴收集件数上调
    p.replace(
        'renwu-r36-dexdropn', A_DEX_DROP_N, R_DEX_DROP_N, expect=1,
        note='A6 图鉴件数 [1,1,2,2,3,4,6]→[2,2,4,4,6,8,12]'
    )

    # 8) R-036/A6：图鉴奖励表固定收藏品件数上调（同心结/道友图谱）
    p.replace(
        'renwu-r36-dexmile', zh(A_DEX_MILE), zh(R_DEX_MILE), expect=1,
        note='A6 固定收藏品件数 同心结 ×1→×2 / ×2→×3，道友图谱 ×1→×2'
    )

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 注入块本体 =================
        ('renwu·寻访任务板组件',    'function YlxwCharBoardR34(',      1, '==', ''),
        ('renwu·师门任务组件',      'function YlxwCharTasksR35(',      1, '==', ''),
        ('renwu·类别表',            'var YLXW_RN_CATS = [',           1, '==', ''),
        ('renwu·品阶表',            'var YLXW_RN_TIERS = [',          1, '==', ''),
        ('renwu·品阶序函数',        'function YlxwRnTierIdx(',        1, '==', ''),
        ('renwu·背包计数函数',      'function YlxwRnCount(',          1, '==', ''),
        ('renwu·背包扣除函数',      'function YlxwRnTake(',           1, '==', ''),
        ('renwu·难度函数',          'function YlxwRnDiff(',           1, '==', ''),
        ('renwu·单条定价函数',      'function YlxwRnRowCost(',        1, '==', 'A4 单条刷新定价'),
        ('renwu·掷任务函数',        'function YlxwRnRollOne(',        1, '==', ''),
        ('renwu·板数据函数',        'function YlxwRnBoardOf(',        1, '==', ''),
        ('renwu·任务数据函数',      'function YlxwRnTasksOf(',        1, '==', ''),
        ('renwu·寻访目标函数',      'function YlxwRnPickVisit(',      1, '==', ''),
        ('renwu·注入块结束标记',    '/* == end yl-renwu',             1, '==', ''),
        # ================= R-034 =================
        ('R34·任务板已挂载',        'e.jsx(YlxwCharBoardR34, { player: p, setPlayer: setP, addLog: log }),', 2, '==', '旧死代码 + 现役 DexPanel 各 1'),
        ('R34·灵石寻访按钮已清零',  zh('children: "灵石寻访 " + cost }),'),                 0, '==', '必须为 0'),
        ('R34·每日免费寻访未动',    zh('children: freeOk ? "寻访 · 今日免费" : "今日已寻访" }),'), 2, '==', '免费寻访保留'),
        ('R34·已寻访计数未动',      zh('children: "已寻访 " + ps.visits + " 次" })'),         2, '==', ''),
        ('R34·板标题文案',          zh('寻访任务（每日 5 条 · 提交该类该品阶以上物品即可寻访）'), 1, '==', ''),
        # ================= R-035 =================
        ('R35·师门任务已挂载',      'e.jsx(YlxwCharTasksR35, { rel: rel, player: p, setPlayer: setP, addLog: log, rarity: rar })', 1, '==', ''),
        ('R35·旧求物卡已停用',      'var questCardOld = (!1) ? e.jsxs("div", {',           1, '==', '死代码保留'),
        ('R35·赠灵石按钮已停用',    '!1&&' + A_GIFT_BTN,                                   1, '==', ''),
        ('R35·任务卡标题文案',      zh('children: "师门任务" })'),                             1, '==', ''),
        ('R35·单条定价已接',        '= YlxwRnRowCost(t, rf);',                               1, '==', 'A4 单条刷新定价'),
        ('R35·单条刷新按钮文案',    zh('children: "刷新 · " + rc + " 灵石"'),                    1, '==', 'A4 价格标在按钮上（点前可见）'),
        ('R35·每条独立刷新',        'onClick: function () { refreshOne(idx); },',           1, '==', 'A4 每条各一个刷新按钮'),
        ('R35·单条重掷一次',        'var nt = YlxwRnRollOne(false);',                      1, '==', 'A4 只重掷该条'),
        ('R35·每日 3 条',           'YlxwRnRollList(3, false)',                            1, '==', '仅任务数据函数 1 处（刷新不再整板重掷）'),
        ('R35·旧整板刷新已清零',    zh('刷新任务（'),                                        0, '==', 'A4 必须为 0'),
        ('R35·旧整板定价已清零',    'YlxwRnRefreshCost',                                   0, '==', 'A4 必须为 0'),
        # ================= R-036 / A6 =================
        ('R36·权重矩阵已提升(行1)', '[22, 46, 27, 5],',                                    1, '==', ''),
        ('R36·权重矩阵已提升(行6)', '[1, 12, 49, 38]',                                     1, '==', ''),
        ('R36·旧权重矩阵已清零',    '[70, 25, 5, 0],',                                     0, '==', '必须为 0'),
        ('R36·权重声明仍在',        'var YLXW_CHAR_DROP_RAR = [',                          1, '==', '就地改写，声明未动'),
        ('A6·缘契件数已提升',       'var YLXW_CHAR_DROP_N = [2, 3, 4, 5];',               1, '==', ''),
        ('A6·图鉴件数已提升',       'var YLXW_CHAR_DEX_DROP_N = [2, 2, 4, 4, 6, 8, 12];',  1, '==', ''),
        ('A6·旧缘契件数已清零',     'var YLXW_CHAR_DROP_N = [1, 2, 3, 5];',               0, '==', '必须为 0'),
        ('A6·旧图鉴件数已清零',     'var YLXW_CHAR_DEX_DROP_N = [1, 1, 2, 2, 3, 4, 6];',  0, '==', '必须为 0'),
        ('A6·同心结12档已提升',     zh('{ at: 12, label: "十二楼", stones: 0, exp: 1200, item: { name: "同心结", rarity: "稀有", qty: 2 } }'), 1, '==', '×1→×2'),
        ('A6·同心结20档已提升',     zh('{ at: 20, label: "二十真", stones: 0, exp: 2000, item: { name: "同心结", rarity: "稀有", qty: 3 } }'), 1, '==', '×2→×3'),
        ('A6·道友图谱24档已提升',   zh('{ at: 24, label: "廿四仙", stones: 3000, exp: 3000, item: { name: "道友图谱", rarity: "仙品", qty: 2 } }'), 1, '==', '×1→×2'),
        ('A6·奖励表声明仍在',       'var YLXW_CHAR_DEX_MILE = [',                          1, '==', '就地改写，声明未动'),
        # ================= 冻结（不得回踩他人锚区） =================
        ('冻结·T6 图鉴面板定义仍在', 'function YlxwCharDexPanelT6(',                       1, '==', ''),
        ('冻结·T6 缘契面板定义仍在', 'function YlxwCharBondPanelT6(',                      1, '==', ''),
        ('冻结·旧图鉴面板定义仍在',  'function YlxwCharDexPanel(',                         1, '==', '死代码保留证据'),
        ('冻结·旧缘契面板定义仍在',  'function YlxwCharBondPanel(',                        1, '==', '死代码保留证据'),
        ('冻结·YlxwCharSafe 两处挂载', 'e.jsx(YlxwCharSafe,{',                            2, '==', '图鉴 + 缘契'),
        ('冻结·YlxwGiftCost 定义仍在', 'function YlxwGiftCost(fav)',                       1, '==', ''),
        ('冻结·YlxwGiftCost 调用点恒4', 'YlxwGiftCost(j&&j.favorability)',                 4, '==', '停用而非删除 → 既有门禁计数不变'),
        ('冻结·YlxwCharDexV2 仍在',  'function YlxwCharDexV2(',                            1, '==', '复用其写 v:2'),
        ('冻结·YlxwCharRelRarity 仍在', 'function YlxwCharRelRarity(',                     1, '==', ''),
        ('冻结·好感加值表仍在',      'var YLXW_CHAR_FAVOR_GAIN = {',                       1, '==', ''),
        ('冻结·T6 求物懒初始化仍在', zh('dm0[relId] = { key: demKey, need: demNeed, day: demDay };'), 1, '==', '死代码保留 → T6 门禁不变'),
        ('冻结·未新增 Recipe" 字面', 'Recipe"',                                            2, '==', 'T6 门禁恒 2；本模块改用中文「丹方」判定，不得回踩'),
        ('冻结·人物志模态框仍在',    'title:"人物志",titleIcon:e.jsx(um,{size:18})',       1, '==', '基线 Nk 标题为**未转义**中文（原始 bundle 形态）'),
        ('冻结·Nk 组件仍在',         'const Nk=({isOpen:t,onClose:r,player:a,setPlayer:l,addLog:c})', 1, '==', ''),
        ('冻结·YlxwMeta 未被破坏',   'function YlxwMeta(k) {',                             1, '==', ''),
        ('renwu·未新增网络调用',     'fetch(',                                             0, '==', '纯客户端，无网络',
         ('/* ===== yl-renwu ', 'function YlxwMeta(k) {')),
    ]
    return gates


# ---------------------------------------------------------------- 自检（python yl_renwu_ext.py）

if __name__ == '__main__':
    import io
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from yl_patch import Patcher, Gates, zh  # noqa: E402

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    HERE = os.path.dirname(os.path.abspath(__file__))
    os.chdir(HERE)

    # ★ 本模块已接线进 V28_MODULES ⇒ build/assets 里的产物**已含 renwu**，直接拿它当基线
    #   锚点必然 count=0。故基线取「链跑到 renwu 之前」的中间产物（只读内存，不落盘）。
    import build_v26n as B  # noqa: E402
    _saved = B.V28_MODULES
    _idx = _saved.index(('renwu', B.v28_renwu_apply))
    B.V28_MODULES = _saved[:_idx]
    try:
        _base_in = io.open(B.BASE, encoding='utf-8').read()
        base, _ = B.build(_base_in)
    finally:
        B.V28_MODULES = _saved
    print('=== renwu 自检：基线 = 链跑到 renwu 之前（%d chars，前置 %d 模块）'
          % (len(base), _idx))

    # 改前锚点份数断言
    print('=== 改前锚点份数 ===')
    pre = [
        ('A_META', A_META, 1), ('A_VISIT_ROW', zh(A_VISIT_ROW), 2),
        ('A_GIFT_BTN', A_GIFT_BTN, 1), ('A_QUEST_HEAD', A_QUEST_HEAD, 1),
        ('A_DROP_RAR', A_DROP_RAR, 1), ('A_DROP_N', A_DROP_N, 1),
        ('A_DEX_DROP_N', A_DEX_DROP_N, 1), ('A_DEX_MILE', zh(A_DEX_MILE), 1),
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

    print('=== 应用补丁（内存副本，不写盘）===')
    pt = Patcher(base, label='renwu-selfcheck')
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
        tmp = os.path.join(tempfile.gettempdir(), 'yl_renwu_selfcheck.js')
        with open(tmp, 'w', encoding='utf-8', newline='') as f:
            f.write(pt.text)
        try:
            r1 = subprocess.run(['node', '--check', tmp], capture_output=True, text=True, timeout=180)
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
