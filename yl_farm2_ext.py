# -*- coding: utf-8 -*-
r"""
yl_farm2_ext.py — R-019「洞府·灵田」客户端单模块

需求原文（用户）
--------------------------------------------------------------------------
  「① 照料加 2 小时冷却（「之前说」说明之前提过但没做 —— 去查是否有遗留的半成品）
    ② 种子 hover 要显示成品属性/售价（现在只有名字）
    ③ 成熟后「变卖/服用」面板要显示价格和服用效果」

侦察结论（逐字实证）
--------------------------------------------------------------------------
① **半成品找到了**：
   · 设计口径（`docs/0.8.8-design/T5-灵田品种重构.md` §62 + §7-Q3(a) +
     `0.8.9-策划案统一审阅清单.md` T5-Q3）原文：
       「『照料』按物品单独计次、**每 2 小时 1 次**、每次略微增加收益」
       裁定 = **(a) 每次 +2%、单田当日累计上限 +10%**。
   · 服务端已落「计次」的一半：`srv_patch_t5_crops.py` T5.8/T5.9 把
     `FARM_TEND_BONUS=0.10` 换成 `FARM_TEND_PER=0.02 + FARM_TEND_CAP=0.10`，
     tend 端点 SQL 变 `... SET tended=1, tend_count=tend_count+1 WHERE tend_count < 12`
     —— 即**当日 12 次封顶**（12 × 2h = 24h，正是「每 2 小时 1 次」的等价上限）。
   · **缺的正是「时间间隔」**：12 次可以在同一秒内连点完（无 2h 间隔闸门）。
     ⇒ R-019① = 给 tend 端点补 **2 小时时间冷却**，并在 status 里下发冷却剩余；
       客户端把「照料」按钮在冷却期内灰置并显示剩余。
   · 客户端现状：照料按钮 `disabled: !!u`（仅防重复点击），无任何冷却展示。

② 现状：空田播种按钮文案 = `名字（N 灵石 · 需洞府 Lv.x）`，**只有名字 + 种子价**；
   产出信息只在按钮下方一行**常显**小字（v2810c 加的 `YlxwFtHarvestText`），
   **按钮本身没有 hover 提示**。⇒ R-019② = 给播种按钮套一层带 `title` 的容器，
   hover 显示「成品属性（服用效果）+ 售价（变卖价）」。

③ 现状：点击「变卖 / 服用」→ `YlxwFarmConfirm` 二次确认弹窗**已显示**
   `YlxwFtSellText`（灵石 +X）/ `YlxwFtConsumeText`（修为 +Y · 气血 +Z）。
   ⇒ 弹窗口径已满足；本模块**再补**成熟田块行内一行小字预览（不必点开即可见价与效果），
     使「成熟后变卖/服用面板」在**列表层**也直接显示价格与服用效果。

改法（5 处就地替换 + 1 处模块级注入；锚点全部实测）
--------------------------------------------------------------------------
  注入：`function YlxwFtHasConsume(cd) {` 之前（v2810c 块内，depth=2 顶层，函数提升）
  E0 ★ 作物目录合并：`g = (t && t.crops) || {}` → `g = YlxwFtCrops(t)`（expect=2）
      —— **R-019②③ 的真正前置修复**：服务端 `/farm/status` 的 `crops` 只是基础定义，
      售价/服用/品阶/产品线在 `cropList[]`；不合并则 `cd.sell`/`cd.consExp` 恒 undefined，
      常显标注为空、二次确认弹窗恒「灵石 +0」。合并后 4 个消费点全部同源拿到真数字。
  E1 单元格 div 补 title（hover 显示成品属性/售价）        expect=2（T5 活面板 + T10 死面板）
  E2 面板内挂 20s 心跳（让冷却倒计时/按钮态自动刷新）      expect=2（同上）
  E3 照料按钮加冷却灰置 + 剩余文案                        expect=2（同上）
  E4 成熟田块行内加「变卖价 · 服用效果」预览               expect=1（仅 T5 活面板）

服务端依赖（本模块只做客户端一半；服务端另有 srv_patch_farm2.py）
--------------------------------------------------------------------------
  · status 的 slots[].care 增 `tendReadyAt`（绝对 epoch ms，= 上次照料 + 2h）。
    缺该字段 ⇒ 客户端 `YlxwFtTendCdMs` 恒 0 ⇒ 按钮照常可点（**向后兼容，零回归**）。
  · tend 端点在 2h 内重复照料 ⇒ 409（业务拒绝，**不得 403**，否则 Xc() 强制登出）。

硬约束
--------------------------------------------------------------------------
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py、不写 build/assets/。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R019: 灵田「照料 2h 冷却」+「种子 hover 成品/售价」+「成熟行价格预览」 =====
   设计口径（T5 §7-Q3(a)）：照料每 2 小时 1 次、每次 +2%、单田当日累计封顶 +10%。
   服务端已落「12 次/日封顶」，缺「2h 时间间隔」；本模块做客户端一半：
   status.slots[].care.tendReadyAt（绝对 ms）存在时，冷却期内灰置照料按钮并显示剩余。
   字段缺失 ⇒ 恒 0 ⇒ 按钮照常可点（向后兼容）。 */

/* 照料冷却剩余（ms）。服务端下发绝对就绪时刻 tendReadyAt；缺省 0（无冷却）。 */
function YlxwFtTendCdMs(care) {
  var v = Number(care && care.tendReadyAt);
  if (!isFinite(v) || v <= 0) return 0;
  return Math.max(0, v - Date.now());
}
/* 冷却剩余文案：1小时23分 / 45分10秒 / 12秒 */
function YlxwFtCdText(ms) {
  var s = Math.max(0, Math.floor(Number(ms) || 0) / 1000);
  var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = Math.floor(s % 60);
  if (h > 0) return h + "小时" + m + "分";
  if (m > 0) return m + "分" + ss + "秒";
  return ss + "秒";
}
/* 播种按钮 hover 文案：作物名（品阶 · 产品线）：变卖 灵石 +X · 服用 修为 +Y · 气血 +Z */
function YlxwFtSeedTip(cd, slot) {
  cd = cd || {};
  var tier = cd.tier ? (cd.tier + "品") : "";
  var line = (cd.line && YLXW_FT_LINE[cd.line]) ? YLXW_FT_LINE[cd.line] : "";
  var meta = [tier, line].filter(function (x) { return !!x; }).join(" · ");
  var body = YlxwFtHarvestText(cd, slot);
  return (cd.name || "灵草") + (meta ? "（" + meta + "）" : "") + "：" + (body || "暂无产出数据");
}
/* 20s 心跳：冷却倒计时与按钮灰置态随渲染自动刷新（面板本身不轮询） */
function YlxwFtTick() {
  var st = O.useState(0), set = st[1];
  O.useEffect(function () {
    var id = setInterval(function () { set(function (x) { return x + 1; }); }, 20000);
    return function () { clearInterval(id); };
  }, []);
  return st[0];
}
/* ★ R-019②③ 关键修复：作物目录合并。
   /farm/status 的 `crops` 只是**基础定义**（name/seed/minutes/stones/exp/grottoLevel），
   策划 §2.2 要的「售价/服用修为/属性/品阶/产品线」实际在 `cropList[]`（按 key 索引，字段
   sell/consExp/consAttr/consPct/tier/line/plantable/legacy）。面板原本直接读 `t.crops[x]`
   ⇒ `cd.sell`/`cd.consExp` 恒 undefined ⇒ 常显标注为空、二次确认弹窗恒显示「灵石 +0」。
   本函数把 cropList 按 key 并入 crops，使 v2810c 常显标注 / R-019 hover / 成熟行预览 /
   二次确认弹窗**同源取到同一份数字**（策划 §2.2 铁律：卡片与弹窗必须调同一函数）。
   cropList 缺失时原样返回 crops（向后兼容零回归）。 */
function YlxwFtCrops(t) {
  var base = (t && t.crops) || {};
  var list = (t && t.cropList) || [];
  if (!list || !list.length) return base;
  var byKey = {};
  for (var i = 0; i < list.length; i++) { if (list[i] && list[i].key) byKey[list[i].key] = list[i]; }
  var out = {};
  for (var k in base) {
    var m = byKey[k];
    out[k] = m ? Object.assign({}, base[k], {
      tier: m.tier, line: m.line, sell: m.sell, consExp: m.consExp,
      consAttr: m.consAttr, consPct: m.consPct, plantable: m.plantable, legacy: m.legacy
    }) : base[k];
  }
  return out;
}
'''

# --------------------------------------------------------------------------- 锚点常量

# 注入锚：v2810c 块内的模块级函数（depth=2 顶层；函数声明提升，位置无关）
INJECT_ANCHOR = 'function YlxwFtHasConsume(cd) {'

# E0 作物目录合并：`t.crops`（基础定义）→ 并入 `t.cropList`（含 sell/consExp/tier/line）
#   ★ 单点修复：面板内所有 `g[x]` 消费点（v2810c 常显标注 / R-019 hover / 成熟行预览 /
#     二次确认弹窗）随之同源拿到售价与服用效果，且不改任何被别的模块冻结的调用串。
#   ★ 全仓共 3 个灵田面板（基座 YlxwTFarm 死代码 + farm087 的 T10 死代码 + v2810c 的 T5 活面板），
#     三者共用后缀 `, g = (t && t.crops) || {}, h = Object.keys(g);` ⇒ 用后缀锚一次替换 3 处。
E0_OLD = ', g = (t && t.crops) || {}, h = Object.keys(g);'
E0_NEW = ', g = YlxwFtCrops(t), h = Object.keys(g);'

# E1 播种按钮套 title 容器（hover 成品属性/售价）
#   ★ 不包住 cropBtn 本体 —— `e.jsxs("div", { className: "flex flex-col items-start
#     gap-0.5", children: [cropBtn(N, x),` 是 v2810c「A·标注列容器已插入」的门禁串，
#     必须逐字保留。改为给**外层单元格 div** 补一个 `title` 属性（hover 整格即出提示），
#     插在 children 数组之后，既满足需求又不回踩 v2810c。
E1_OLD = 'children: YlxwFtHarvestText(g[x] || {}, N.slot) })] }, x);'
E1_NEW = ('children: YlxwFtHarvestText(g[x] || {}, N.slot) })]'
          ', title: YlxwFtSeedTip(g[x] || {}, N.slot) }, x);')

# E2 面板组件内挂心跳（T5 + T10 同款行 ⇒ expect=2）
E2_OLD = 'var pstore = Be(function (s) { return s.player; });'
E2_NEW = 'var pstore = Be(function (s) { return s.player; }); var __ftTick = YlxwFtTick();'

# E3 照料按钮：加冷却灰置 + 剩余文案（T5 + T10 ⇒ expect=2）
E3_OLD = (r'!b.ready && e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, '
          r'onClick: function () { f("t" + N.slot, "/farm/tend", { slot: N.slot }); }, '
          r'children: "\u7167\u6599" })')
E3_NEW = (r'!b.ready && e.jsx(YlxwBtn, { tone: "ghost", '
          r'disabled: !!u || YlxwFtTendCdMs(care) > 0, '
          r'onClick: function () { f("t" + N.slot, "/farm/tend", { slot: N.slot }); }, '
          r'children: YlxwFtTendCdMs(care) > 0 ? "\u51b7\u5374 " + YlxwFtCdText(YlxwFtTendCdMs(care)) '
          r': "\u7167\u6599" })')

# E4 成熟田块行内预览（仅 T5 活面板 ⇒ expect=1）
E4_OLD = (r'b.ready && e.jsx(YlxwBtn, { disabled: !!u, '
          r'onClick: function () { doSell(N.slot, cd); }, children: "\u53d8\u5356" })')
E4_NEW = (r'b.ready && e.jsx("span", '
          r'{ className: "text-[10px] text-stone-400 leading-tight", '
          r'children: YlxwFtHarvestText(cd, N.slot) }), '
          r'b.ready && e.jsx(YlxwBtn, { disabled: !!u, '
          r'onClick: function () { doSell(N.slot, cd); }, children: "\u53d8\u5356" })')

EDITS = [
    ('E0 作物目录并入 cropList（售价/服用同源）',   E0_OLD, E0_NEW, 3),
    ('E1 播种按钮套 title 容器（hover 成品/售价）', E1_OLD, E1_NEW, 2),
    ('E2 面板内挂 20s 心跳（冷却倒计时刷新）',      E2_OLD, E2_NEW, 2),
    ('E3 照料按钮加冷却灰置 + 剩余文案',            E3_OLD, E3_NEW, 2),
    ('E4 成熟行内加变卖价/服用效果预览',            E4_OLD, E4_NEW, 1),
]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 farm089/v2810c）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('farm2 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 模块级工具函数（与 v2810c 的 YlxwFtHarvestText 同作用域）
    p.insert_before('farm2-helpers', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 YlxwFtTendCdMs/CdText/SeedTip/Tick')

    # 1) 就地替换
    for name, old, new, exp in EDITS:
        p.replace(name, old, new, expect=exp)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 注入块 =================
        ('R19·冷却剩余函数已注入',     'function YlxwFtTendCdMs(care) {', 1, '==', ''),
        ('R19·冷却文案函数已注入',     'function YlxwFtCdText(ms) {',     1, '==', ''),
        ('R19·hover 文案函数已注入',   'function YlxwFtSeedTip(cd, slot) {', 1, '==', ''),
        ('R19·20s 心跳 hook 已注入',   'function YlxwFtTick() {',         1, '==', ''),
        ('R19·冷却读服务端字段',       'var v = Number(care && care.tendReadyAt);', 1, '==', '绝对就绪时刻（缺省 0 兼容）'),
        ('R19·冷却缺省零（向后兼容）', 'if (!isFinite(v) || v <= 0) return 0;', 1, '==', '服务端未下发 ⇒ 恒 0 ⇒ 按钮可点'),
        # ================= E0 作物目录合并（售价/服用同源） =================
        ('R19·目录合并函数已注入',     'function YlxwFtCrops(t) {', 1, '==', '把 cropList 并入 crops'),
        ('R19·合并读 cropList',        'var list = (t && t.cropList) || [];', 1, '==', '服务端权威售价/服用字段所在'),
        ('R19·合并缺省向后兼容',       'if (!list || !list.length) return base;', 1, '==', 'cropList 缺失时原样返回 crops'),
        ('R19·合并带入 sell/consExp',  'tier: m.tier, line: m.line, sell: m.sell, consExp: m.consExp,', 1, '==', '与二次确认弹窗同源'),
        ('R19·面板目录已改走合并',     'g = YlxwFtCrops(t), h = Object.keys(g);', 3, '==', '基座死代码 + T10 死 + T5 活，全仓 3 处'),
        ('R19·旧 t.crops 直读已清零',  'g = (t && t.crops) || {}, h', 0, '==', '旧直读会漏 sell/consExp'),
        # ================= E1 种子 hover =================
        ('R19·单元格 hover 已清零（R-046）', r'children: YlxwFtHarvestText(g[x] || {}, N.slot) })], title: YlxwFtSeedTip(g[x] || {}, N.slot) }, x);', 0, '==', '被 R-046 取代'),
        ('跨模块·v2810c 容器串已变（R-046 插入 title）',  'e.jsxs("div", { className: "flex flex-col items-start gap-0.5", children: [cropBtn(N, x),', 0, '==', 'v2810c 门禁串：只加 title 属性，不重写 children'),
        ('R19·hover 含成品/售价',       r'var body = YlxwFtHarvestText(cd, slot);', 1, '==', '与二次确认弹窗同源'),
        ('R19·hover 含品阶/产品线',     r'var meta = [tier, line].filter(function (x) { return !!x; }).join(" \u00b7 ");', 1, '==', ''),
        ('R19·hover 空数据兜底',        r'|| "\u6682\u65e0\u4ea7\u51fa\u6570\u636e");', 1, '==', ''),
        # ================= E2 心跳 =================
        ('R19·面板挂心跳（T5+T10）',    'var pstore = Be(function (s) { return s.player; }); var __ftTick = YlxwFtTick();', 2, '==', ''),
        # ================= E3 照料冷却 =================
        ('R19·照料按钮冷却灰置',        'disabled: !!u || YlxwFtTendCdMs(care) > 0,', 2, '==', ''),
        ('R19·照料按钮冷却文案',        r'children: YlxwFtTendCdMs(care) > 0 ? "\u51b7\u5374 " + YlxwFtCdText(YlxwFtTendCdMs(care)) : "\u7167\u6599" })', 2, '==', ''),
        ('R19·冷却文案单位·小时',       r'return h + "\u5c0f\u65f6" + m + "\u5206";', 1, '==', ''),
        ('R19·照料端点未改',            '"/farm/tend"', 2, '==', 'T10 死代码 + T5 活面板，路径不变'),
        # ================= E4 成熟行预览 =================
        ('R19·成熟行内预览已清零（R-046）',      r'b.ready && e.jsx("span", { className: "text-[10px] text-stone-400 leading-tight", children: YlxwFtHarvestText(cd, N.slot) })', 0, '==', '被 R-046 改成 hover'),
        ('R19·变卖按钮本体已变（R-046 插入 title）',        r'b.ready && e.jsx(YlxwBtn, { disabled: !!u, onClick: function () { doSell(N.slot, cd); }, children: "\u53d8\u5356" })', 0, '==', ''),
        ('R19·服用按钮本体已变（R-046 插入 title）',        r'b.ready && e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () { doConsume(N.slot, cd); }, children: "\u670d\u7528" })', 0, '==', ''),
        ('R19·二次确认弹窗未动',        'function YlxwFarmConfirm(', 1, '==', '价格/效果展示沿用 farm089 弹窗'),
        ('R19·弹窗变卖文本同源',        'YlxwFtSellText(confirm.cd, confirm.slot)', 1, '==', ''),
        ('R19·弹窗服用文本同源',        'YlxwFtConsumeText(confirm.cd)', 1, '==', ''),
        # ---- 冻结（本模块不得回踩）----
        ('冻结·farm089 T5 注册未动',    'YLXW_COMP.farm=YlxwTFarmT5;', 1, '==', ''),
        ('冻结·v2810c 常显标注已清零（R-046）',    'children: YlxwFtHarvestText(g[x] || {}, N.slot) })]', 0, '==', '被 R-046 取代'),
        ('冻结·T5 面板函数仍唯一',      'function YlxwTFarmT5() {', 1, '==', ''),
    ]
    return gates
