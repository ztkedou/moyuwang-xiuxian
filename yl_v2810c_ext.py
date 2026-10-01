# -*- coding: utf-8 -*-
r"""
yl_v2810c_ext.py — 0.8.10 补丁 c（客户端单模块）

接线：V28_MODULES 插在 farm089/pet089… 之后、**numbal 之前**（numbal 恒最后）。
      `_t_mod.py` 的自测位置与此等价。
落点：**只新建本文件**；不写 build/assets/、不改 build_v26n.py。

=========================================================================== 任务 A
「洞府-仙务·灵田：**每种作物收获内容要标注**」

口径勘误（重要）
--------------------------------------------------------------------------
0.8.9（farm089）已把灵田重构为「**变卖 / 服用**」双出口 —— 作物**不再是「收获出物品」**，
而是成熟后二选一：变卖换灵石，或服用加修为 + 属性。所以「收获内容」的正确口径是
**「变卖得多少灵石」+「服用加什么」**，而不是旧口径的「产出 X 个 Y」。

现状（farm089 注入块）
--------------------------------------------------------------------------
  · 播种按钮 cropBtn 文案只有 `name + "（" + seed + " 灵石" + grotto + "）"` —— **无产出标注**；
  · 变卖 / 服用效果只出现在**二次确认弹窗**里，由 `YlxwFtSellText(cd, slot)` /
    `YlxwFtConsumeText(cd)` 生成（farm089 注入块 :129-149）。
  · 同一 `h.map(function (x) { return cropBtn(N, x); })` 行在产物中**出现 2 次**：
    YlxwTFarmT5（活面板，farm089 覆盖注册）与 YlxwTFarmT10（死面板，farm089 有意保留）。
    两行逐字相同 ⇒ 无法用单点锚区分，故本模块 expect=2 同时标注（死面板一并标注可保
    「若回退注册到 T10，标注仍在」；T10 不被渲染，零行为影响）。

改法
--------------------------------------------------------------------------
在空田作物按钮行**追加**一行 10px 灰字标注（不重写按钮、不重写面板）：
    「变卖 灵石 +1,200 · 服用 修为 +80 · 气血 +3」
文案由 `YlxwFtHarvestText(cd, slot)` 生成，内部**直接复用** `YlxwFtSellText` /
`YlxwFtConsumeText`（与二次确认弹窗**同源同函数**），数值全部来自服务端 `crops` 下发的
`sell / consExp / consAttr / consPct` 字段 ⇒ 标注与实发必然一致，本模块**不新造任何公式**。

=========================================================================== 任务 B
「洞府自带灵草种植：**加速用灵石改为只减少小时数**（不是一次累计完成）」

旧行为（基座 @~1703118，`handleSpeedupHerb`）
--------------------------------------------------------------------------
    const q=C.harvestTime-g, w=Math.ceil(q/6e4), A=Math.max(Br.minCost,w*Br.costPerMinute);
    ...
    return _[M]={...C,harvestTime:g}, N+=1, a(`⚡ 使用 ${A} 灵石加速【${C.herbName}】生长，立即成熟！`)
  ⇒ 一次加速 = **直接成熟**（harvestTime 设为 Date.now()），费用按**剩余全长**计。

新行为
--------------------------------------------------------------------------
  1. 每次加速只把 harvestTime **前移固定小时数**（按灵草品阶）：
         普通 1h · 稀有 2h · 传说 4h · 仙品 6h
     取值理由：灵草目录 `wn` 的 growthTime 为 普通 0.5h / 稀有 2.5~4h / 传说 8~15h /
     仙品 18~24h。按 1/2/4/6 取，**全程催熟所需次数 = 1~3 次**（旧口径恒为 1 次），
     每次购买都有可观收益，又不至于把长时灵草一键打完。
  2. 剩余时间**不足**该小时数时直接成熟（`Math.min` 截断，不产生负值）——自然行为。
  3. **计价公式（与旧口径同源，只换计价基准）**：
        实际缩短分钟数 w = Math.ceil(min(剩余ms, 品阶小时数*36e5) / 6e4)
        A = Math.max(Br.minCost, w * Br.costPerMinute)        // 1000 灵石下限，100 灵石/分钟
     ⇒ 单价（costPerMinute / minCost）**完全不动**，只把「剩余全长」换成「实际缩短量」。
     因此「全程催熟总价」与旧口径**完全相等**（可分期、可只买一段），既没有
     「花更少钱却直接成熟」的漏洞，也没有额外涨价。
  4. 文案：`⚡ 使用 N 灵石加速【X】生长，缩短 M 小时！`
     剩余不足而直接成熟时追加 `（剩余不足，灵草已成熟）`；**不再出现「立即成熟」**。
  5. 按钮预览（fun086 F1 补的「加速 N 灵石」）**同步换基准**，否则显示价与实收价不符。

实现要点（为什么这样写：要保住 fun086 / grotto087 的冻结门禁）
--------------------------------------------------------------------------
fun086 有两条冻结门禁（grotto087 又各复述一次）：
    'const q=C.harvestTime-g,w=Math.ceil(q/6e4),'                              == 1
    'Math.max(Br.minCost,Math.ceil(I/6e4)*Br.costPerMinute).toLocaleString()' == 1
两条都是**逐字计数**，一旦被我改掉，**整条 v28 链的落盘门禁就会 FAIL**。
所以本模块**不碰这两个字面串**，改用「换基准」的写法：

  · 加速入口：把 `C` 换成 `C = {...真身, harvestTime: g + min(真剩余, 品阶ms)}` 的**浅拷贝**。
    于是既有的 `q = C.harvestTime - g` **天然等于「实际缩短的 ms」**，
    `w = Math.ceil(q/6e4)` 天然等于「实际缩短的分钟数」，
    `A = Math.max(Br.minCost, w*Br.costPerMinute)` **一字不改**就是正确的新价。
    成熟守卫 `g>=C.harvestTime` 语义不变（真剩余 0 时 C.harvestTime===g ⇒ 仍报「已成熟」）。
    提交处改为 `harvestTime: __C0.harvestTime - q`（真身 - 实际缩短量），
    真剩余不足时恰好落在 `g` ⇒ 直接成熟。
  · 按钮预览：把该卡片行的 `I`（剩余 ms）换成 `min(剩余ms, 品阶ms)`，
    fun086 的 `Math.ceil(I/6e4)*Br.costPerMinute` 即自动按缩短量计价；
    同时把「剩余时间」展示改指新变量 `__left`，避免倒计时被截断。

加速入口盘点（已 grep 全产物）
--------------------------------------------------------------------------
  `handleSpeedupHerb` 共 9 处，全部是「定义 1 处 + 属性透传 8 处」，**唯一逻辑点**就是
  定义体；`onSpeedupHerb` 仅 2 处（modal 形参 + 透传）。全产物**不存在**一键加速 /
  批量加速 / 全部加速 / `SpeedupAll`（`grep` 计数均为 0），故无遗漏入口。

锚点（全部先验 `base.count(anchor)==1`，除标注行 ==2 见上）
--------------------------------------------------------------------------
  注入块：'function Yk(t){'（grotto087 同锚，模块级，加速入口与洞府 modal 同作用域）
  A：'children: h.map(function (x) { return cropBtn(N, x); })'                expect=2
  B1：'const C=_[M],g=Date.now();'                                            expect=1
  B2：'_[M]={...C,harvestTime:g},N+=1,a(`⚡ …立即成熟！`,"gain")'               expect=1
  B3：'T.plantedHerbs.map((g,q)=>{const w=Date.now(),…D=zM(g.plantTime,…);'    expect=1
  B4：'children:r4(I)}'                                                       expect=1
  B5：'title:"使用灵石加速生长",'（fun086 改后的形态）                          expect=1

与 grotto087 / fun086 的关系
--------------------------------------------------------------------------
  · fun086 F1：只改「按钮补费用」，本模块**保留其两个字面串**（见上），零回归；
    仅把按钮 tooltip 从「使用灵石加速生长」扩为「使用灵石加速生长（每次缩短 N 小时）」，
    fun086 的 `'title:"使用灵石加速生长",children:[…"加速"]' == 0` 门禁仍成立。
  · grotto087：改的是「升级列表 / 材料门槛 / 收获懒兼容映射 / 降级文案」，与本模块
    零锚区交集；其复述的两条 fun086 冻结门禁同样保持 == 1。
  · 本模块排在 grotto087、fun086 **之后**（numbal 之前），故锚点取的是它们改后的形态。
"""

import re

# --------------------------------------------------------------------------- 注入块
# 说明：注释里的中文由 ctx['zh'] 转 \uXXXX；代码里的中文一律**直接写 \uXXXX**，
#       保证 zh() 后整块纯 ASCII（_t_mod.py / build_v26n.py 都会自检）。

INJECT_JS = r'''
/* ===== yl-0.8.10c-1: 洞府灵草「加速」改为只缩短固定小时数（按品阶） =====
   旧：一次加速 = harvestTime 置为 Date.now()（直接成熟），费用按剩余全长计。
   新：一次加速只前移 N 小时；剩余不足 N 小时则自然成熟。N = 普通1/稀有2/传说4/仙品6。
   计价基准同步换成「实际缩短的分钟数」（单价 costPerMinute / 下限 minCost 均不动），
   故全程催熟总价与旧口径一致，不会出现「花更少钱却直接成熟」的漏洞。 */
function YlxwHerbSpeedHours(h) {
  var r = "";
  try {
    var id = h && h.herbId, nm = h && h.herbName;
    var c = wn.find(function (Q) { return Q.id === id; })
         || wn.find(function (Q) { return Q.id === String(id == null ? "" : id).replace(/^herb-/, ""); })
         || wn.find(function (Q) { return Q.name === nm; });
    r = (c && c.rarity) || "";
  } catch (e) { r = ""; }
  if (r === "\u4ed9\u54c1") return 6;
  if (r === "\u4f20\u8bf4") return 4;
  if (r === "\u7a00\u6709") return 2;
  return 1;
}
/* 品阶小时数 -> 毫秒 */
function YlxwHerbSpeedMs(h) { return YlxwHerbSpeedHours(h) * 36e5; }
/* 毫秒 -> 文案小时数（整数不带小数点，非整数保留 1 位） */
function YlxwHerbHoursText(ms) {
  var v = Math.max(0, Number(ms) || 0) / 36e5, r = Math.round(v * 10) / 10;
  return r % 1 === 0 ? r.toFixed(0) : r.toFixed(1);
}

/* ===== yl-0.8.10c-2: 灵田作物卡片「收获内容」标注 =====
   0.8.9 起灵田作物是「变卖 / 服用」双出口（不再收获出物品），
   故收获内容 = 变卖得多少灵石 + 服用加什么。文案**直接复用二次确认弹窗的两个函数**
   （YlxwFtSellText / YlxwFtConsumeText），数值全部来自服务端 crops 字段，本模块不另造公式。 */
function YlxwFtHasConsume(cd) {
  if (!cd) return false;
  if (YlxwNum(cd.consExp) > 0) return true;
  var i, a = cd.consAttr || [], p = cd.consPct || [];
  for (i = 0; i < a.length; i++) { if (a[i] && YlxwNum(a[i].value) > 0) return true; }
  for (i = 0; i < p.length; i++) { if (p[i] && YlxwNum(p[i].value) > 0) return true; }
  return false;
}
function YlxwFtHarvestText(cd, slot) {
  var parts = [];
  if (YlxwNum(cd && cd.sell) > 0) parts.push("\u53d8\u5356 " + YlxwFtSellText(cd, slot));
  if (YlxwFtHasConsume(cd)) parts.push("\u670d\u7528 " + YlxwFtConsumeText(cd));
  return parts.join(" \u00b7 ");
}
'''

# --------------------------------------------------------------------------- 锚点常量

# 注入锚：与 grotto087 同锚（模块级，洞府 modal 与加速入口同作用域可见）
INJECT_ANCHOR = 'function Yk(t){'

# ---- 任务 A：空田作物按钮行（T5 活面板 + T10 死面板，两行逐字相同 ⇒ expect=2）----
A_ROW_ANCHOR = 'children: h.map(function (x) { return cropBtn(N, x); })'
A_ROW_REPL = (
    'children: h.map(function (x) { return e.jsxs("div", '
    '{ className: "flex flex-col items-start gap-0.5", children: [cropBtn(N, x), '
    'e.jsx("span", { className: "text-[10px] text-stone-400 leading-tight", '
    'children: YlxwFtHarvestText(g[x] || {}, N.slot) })] }, x); })'
)

# ---- 任务 B1：把 C 换成「harvestTime 已截断到本次缩短量」的浅拷贝 ----
B_C_ANCHOR = 'const C=_[M],g=Date.now();'
B_C_REPL = ('const __C0=_[M],g=Date.now(),'
            'C={...__C0,harvestTime:g+Math.min(Math.max(0,__C0.harvestTime-g),YlxwHerbSpeedMs(__C0))};')

# ---- 任务 B2：提交（不再置为 Date.now()）+ 文案改为「缩短 M 小时」 ----
B_COMMIT_ANCHOR = ('_[M]={...C,harvestTime:g},N+=1,'
                   'a(`\u26a1 \u4f7f\u7528 ${A.toLocaleString()} \u7075\u77f3\u52a0\u901f\u3010'
                   '${C.herbName}\u3011\u751f\u957f\uff0c\u7acb\u5373\u6210\u719f\uff01`,"gain")')
B_COMMIT_REPL = ('_[M]={...C,harvestTime:__C0.harvestTime-q},N+=1,'
                 'a(`\u26a1 \u4f7f\u7528 ${A.toLocaleString()} \u7075\u77f3\u52a0\u901f\u3010'
                 '${C.herbName}\u3011\u751f\u957f\uff0c\u7f29\u77ed ${YlxwHerbHoursText(q)} '
                 '\u5c0f\u65f6${q>=__C0.harvestTime-g?"\uff08\u5269\u4f59\u4e0d\u8db3\uff0c'
                 '\u7075\u8349\u5df2\u6210\u719f\uff09":""}\uff01`,"gain")')

# ---- 任务 B3：灵草卡片行：I 换成「本次缩短量」，剩余时间另存 __left ----
B_MAP_ANCHOR = ('T.plantedHerbs.map((g,q)=>{const w=Date.now(),A=w>=g.harvestTime,'
                'I=Math.max(0,g.harvestTime-w),D=zM(g.plantTime,g.harvestTime);')
B_MAP_REPL = ('T.plantedHerbs.map((g,q)=>{const w=Date.now(),A=w>=g.harvestTime,'
              '__left=Math.max(0,g.harvestTime-w),I=Math.min(__left,YlxwHerbSpeedMs(g)),'
              'D=zM(g.plantTime,g.harvestTime);')

# ---- 任务 B4：剩余时间展示改指 __left（防倒计时被截断）----
B_R4_ANCHOR = 'children:r4(I)}'
B_R4_REPL = 'children:r4(__left)}'

# ---- 任务 B5：按钮 tooltip 补「每次缩短 N 小时」----
B_TITLE_ANCHOR = 'title:"\u4f7f\u7528\u7075\u77f3\u52a0\u901f\u751f\u957f",'
B_TITLE_REPL = ('title:"\u4f7f\u7528\u7075\u77f3\u52a0\u901f\u751f\u957f\uff08\u6bcf\u6b21'
                '\u7f29\u77ed " + YlxwHerbSpeedHours(g) + " \u5c0f\u65f6\uff09",')

EDITS = [
    ('A  作物按钮行追加收获内容标注',  A_ROW_ANCHOR,     A_ROW_REPL,     2),
    ('B1 C 截断为本次缩短量',          B_C_ANCHOR,       B_C_REPL,       1),
    ('B2 提交按缩短量前移 + 新文案',   B_COMMIT_ANCHOR,  B_COMMIT_REPL,  1),
    ('B3 卡片行 I 换缩短量',           B_MAP_ANCHOR,     B_MAP_REPL,     1),
    ('B4 剩余时间展示改指 __left',     B_R4_ANCHOR,      B_R4_REPL,      1),
    ('B5 加速按钮 tooltip 补小时数',   B_TITLE_ANCHOR,   B_TITLE_REPL,   1),
]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 fun086/grotto087）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('v2810c 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 模块级工具函数（洞府 modal 与加速入口同作用域；函数声明提升，位置无关）
    p.insert_before('v2810c-helpers', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 YlxwHerbSpeedHours/Ms/HoursText + YlxwFtHarvestText/HasConsume')

    # 1) 就地替换
    for name, old, new, exp in EDITS:
        p.replace(name, old, new, expect=exp)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 任务 A：灵田作物「收获内容」标注 =================
        ('A·收获标注函数已注入',     'function YlxwFtHarvestText(cd, slot) {',  1, '==', ''),
        ('A·服用有无判定函数',       'function YlxwFtHasConsume(cd) {',         1, '==', ''),
        ('A·变卖标注与弹窗同源',     r'parts.push("\u53d8\u5356 " + YlxwFtSellText(cd, slot));', 1, '==', '直接复用二次确认弹窗同款函数'),
        ('A·服用标注与弹窗同源',     r'parts.push("\u670d\u7528 " + YlxwFtConsumeText(cd));',    1, '==', '不另造公式'),
        ('A·标注行已清零（R-046 改 hover）',   'children: YlxwFtHarvestText(g[x] || {}, N.slot)', 0, '==', '被 R-046 显示精简取代'),
        ('A·标注列容器已清零（R-046）',       'e.jsxs("div", { className: "flex flex-col items-start gap-0.5", children: [cropBtn(N, x),', 0, '==', '被 R-046 显示精简取代'),
        ('A·播种按钮原文案未动',     r'children: (cd.name || YLXW_CROP[x] || x) + "\uff08"', 2, '==', '按钮本体零改动'),
        # ---- farm089 冻结（本模块不得回踩）----
        ('冻结·farm089 T5 注册未动',  'YLXW_COMP.farm=YlxwTFarmT5;',            1, '==', ''),
        ('冻结·farm089 二次确认弹窗', 'function YlxwFarmConfirm(',               1, '==', ''),
        ('冻结·farm089 已停种判定',   'var ret = cd.retired === true;',          1, '==', ''),
        # ================= 任务 B：加速改为只减少小时数 =================
        ('B·品阶->小时 函数已注入',   'function YlxwHerbSpeedHours(h) {',        1, '==', ''),
        ('B·品阶->毫秒 函数已注入',   'function YlxwHerbSpeedMs(h) { return YlxwHerbSpeedHours(h) * 36e5; }', 1, '==', ''),
        ('B·品阶->小时 文案函数',     'function YlxwHerbHoursText(ms) {',        1, '==', ''),
        ('B·小时表·仙品 6h',          r'if (r === "\u4ed9\u54c1") return 6;',    1, '==', '最终取值 普通1/稀有2/传说4/仙品6'),
        ('B·小时表·传说 4h',          r'if (r === "\u4f20\u8bf4") return 4;',    1, '==', ''),
        ('B·小时表·稀有 2h',          r'if (r === "\u7a00\u6709") return 2;',    1, '==', ''),
        ('B·C 已截断为缩短量',        'const __C0=_[M],g=Date.now(),C={...__C0,harvestTime:g+Math.min(Math.max(0,__C0.harvestTime-g),YlxwHerbSpeedMs(__C0))};', 1, '==', 'q 天然 = 实际缩短 ms'),
        ('B·提交不再置为 Date.now()', '_[M]={...C,harvestTime:__C0.harvestTime-q}', 1, '==', '真身 harvestTime - 缩短量'),
        ('B·旧「立即成熟」文案清零',  '立即成熟',                                 0, '==', '改为「缩短 M 小时」'),
        ('B·新文案含缩短小时数',      '缩短 ${YlxwHerbHoursText(q)} 小时',        1, '==', ''),
        ('B·剩余不足兜底文案',        '（剩余不足，灵草已成熟）',                 1, '==', '真剩余 < 品阶小时数时直接成熟'),
        ('B·按钮预览同口径计价',      'I=Math.min(__left,YlxwHerbSpeedMs(g))',   1, '==', '否则显示价与实收价不符'),
        ('B·剩余时间展示未截断',      'children:r4(__left)}',                    1, '==', ''),
        ('B·tooltip 补每次缩短小时',  'title:"使用灵石加速生长（每次缩短 " + YlxwHerbSpeedHours(g) + " 小时）",', 1, '==', ''),
        ('B·成熟守卫未动',            '该灵草已经成熟，无需加速。',               2, '==', 'toast + log 各 1'),
        ('B·灵石不足文案未动',        '灵石不足！加速需要',                      1, '==', ''),
        ('B·加速入口数未变',          'handleSpeedupHerb',                       9, '==', '定义 1 + 透传 8'),
        ('B·每日次数计数未变',        'dailySpeedupCount',                       10, '==', ''),
        ('B·无其它加速入口',          'SpeedupAll',                              0, '==', '全产物无一键/批量加速，唯一逻辑点即 handleSpeedupHerb'),
        # ---- fun086 / grotto087 冻结（两条逐字门禁必须原样保留）----
        ('冻结·fun086 扣费前缀未动',  'const q=C.harvestTime-g,w=Math.ceil(q/6e4),', 1, '==', 'fun086 F1 + grotto087 各断言一次'),
        ('冻结·fun086 按钮费用串未动', 'Math.max(Br.minCost,Math.ceil(I/6e4)*Br.costPerMinute).toLocaleString()', 1, '==', 'fun086 F1 + grotto087 各断言一次'),
        ('冻结·Br 常量未动',          'Br={dailyLimit:10,costPerMinute:100,minCost:1000}', 1, '==', '单价/下限零改动'),
    ]
    return gates
