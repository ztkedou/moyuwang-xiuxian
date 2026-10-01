# -*- coding: utf-8 -*-
r"""
yl_r046_ext.py — R-046 仙务·灵田：① 废弃(已停种)的草不再展示 ② 变卖/服用描述只留 hover

需求（台账 R-046 · 洞府 · 无附图）
--------------------------------------------------------------------------
  「仙务·灵田，废弃的草不要展示了直接去掉。变卖和服用的描述只放在鼠标悬停上，
    不要都打在页面里。」
  ⇒ 纯 UI 精简，**不动任何数值**。

「废弃」的确切标识（逐字实证，不猜）
--------------------------------------------------------------------------
  服务端 `srv_patch_t5_crops.py`：
    · §206-215  `crops` 目录里「已停种」品种逐键 `retired: true`
        `for (const legacyKey of Object.keys(out)) { if (isLegacyCrop(legacyKey))
             out[legacyKey] = Object.assign({}, out[legacyKey], { retired: true }); }`
        （5 个旧种 lingcao/lingzhi/qianniancan/taixuguo/zaohuaqinglian；**条目保留不删**，
          因为「存量已种下的旧田仍按旧口径正常收获，槽位回显需要作物名」。）
    · §438-445  `cropList` 数组同源带 `legacy: !FARM_CROPS_NEW[ck]` 与 `plantable: !legacy`。
  客户端既有权威信号：`yl_farm089_ext.py` 的 T5 面板
        `var ret = cd.retired === true;`（据此把按钮置灰 + 文案 ` · 已停种`）。
  ⇒ **「废弃」= `retired === true`**（= 已停种 / legacy / plantable:false）。
     本模块按 `cd.retired === true` 过滤；**显式 true 才剔除**，字段缺失一律保留
     （向后兼容：服务端未上线该标记时零回归）。

现状（bundle index-v28117-20261001 实测，farm2 改造后的形态）
--------------------------------------------------------------------------
  T5 活面板（YlxwTFarmT5）与 T10 死面板共用同一批行；farm2 已在播种单元格挂
  `title: YlxwFtSeedTip(...)`（hover），故**常显标注是冗余的**，正是「都打在页面里」的元凶：
    · 空田每个种子按钮下方常显一行（v2810c 任务 A 加的）
        `e.jsx("span", { className: "text-[10px] text-stone-400 leading-tight",
                         children: YlxwFtHarvestText(g[x] || {}, N.slot) })`   ×2（T5+T10）
    · 成熟田块行内常显一行（farm2 E4 加的）
        `b.ready && e.jsx("span", { className: "text-[10px] text-stone-400 leading-tight",
                                    children: YlxwFtHarvestText(cd, N.slot) })`  ×1（仅 T5）
  两行的文案都由 `YlxwFtHarvestText` 生成 = 「变卖 灵石 +X · 服用 修为 +Y · 气血 +Z」。

改法（3 类 4 处就地替换；锚点全部实测）
--------------------------------------------------------------------------
  ① 播种目录剔除废弃：`h = Object.keys(g);` 之后追加 `h = h.filter(...retired...)`
     —— **两步写**（不重写 `g = YlxwFtCrops(t), h = Object.keys(g);` 这一句），
        以保住 farm2 的 `R19·面板目录已改走合并` 门禁（它逐字断言该句 ×3）。
  ② 播种按钮常显标注：删除 span，hover 由既有的 `title: YlxwFtSeedTip(...)` 承担。
  ③ 成熟行常显标注：删除 span，把描述下沉到两个按钮的 `title`
     （变卖 → `"变卖 " + YlxwFtSellText(cd, slot)`；服用 → `"服用 " + YlxwFtConsumeText(cd)`），
     两个函数**与二次确认弹窗同源**，不新造任何公式。

★ 需主控同步处理（本模块**不碰**上游文件，与 yl_r043/yl_062/yl_068 同一处理方式）
--------------------------------------------------------------------------
  本模块的合法改写会打破 **8 条上游字面门禁**（都是「中间形态」门禁，SKILL §22.5 形态：
  上游断言的是某个中间产物的字面样子，下游一合法改写就假 FAIL）。请主控接线时同步改：

  A) yl_v2810c_ext.py
     1) `('A·标注行已挂到播种按钮', 'children: YlxwFtHarvestText(g[x] || {}, N.slot)', 2, '==')`
        → 改后该串 = 0。删，或改为 0。
     2) `('A·标注列容器已插入', 'e.jsxs("div", { className: "flex flex-col items-start gap-0.5",
            children: [cropBtn(N, x),', 2, '==')`
        → 容器仍在，但子元素只剩 cropBtn（`children: [cropBtn(N, x)]`），该串（含尾逗号）= 0。
        改为 `'children: [cropBtn(N, x)]'` == 2，或删。
  B) yl_farm2_ext.py
     3) `('R19·单元格已挂 hover 提示', r'children: YlxwFtHarvestText(g[x] || {}, N.slot) })],
            title: YlxwFtSeedTip(g[x] || {}, N.slot) }, x);', 2, '==')`
        → 改后 = 0（hover 仍在）。改为
        `'[cropBtn(N, x)], title: YlxwFtSeedTip(g[x] || {}, N.slot) }, x);'` == 2。
     4) `('跨模块·v2810c 容器串未动', 'e.jsxs("div", { className: "flex flex-col items-start
            gap-0.5", children: [cropBtn(N, x),', 2, '==')` → 改后 = 0，同上改法。
     5) `('冻结·v2810c 常显标注未动', 'children: YlxwFtHarvestText(g[x] || {}, N.slot) })]',
            2, '==')` → 改后 = 0，删或改 0。
     6) `('R19·成熟行内预览已插入', r'b.ready && e.jsx("span", { className: "text-[10px]
            text-stone-400 leading-tight", children: YlxwFtHarvestText(cd, N.slot) })', 1, '==')`
        → 改后 = 0（改由两个按钮的 hover 承担），删。
     7) `('R19·变卖按钮本体未动', r'b.ready && e.jsx(YlxwBtn, { disabled: !!u, onClick: function ()
            { doSell(N.slot, cd); }, children: "\u53d8\u5356" })', 1, '==')`
        → 按钮多了一个 `title`，该串 = 0。改含 title 的新形态，或删。
     8) `('R19·服用按钮本体未动', r'b.ready && e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u,
            onClick: function () { doConsume(N.slot, cd); }, children: "\u670d\u7528" })', 1, '==')`
        → 同上。
  ★ farm2 的 `('R19·面板目录已改走合并', 'g = YlxwFtCrops(t), h = Object.keys(g);', 3, '==')`
     **不受影响**（本模块用「两步写」保留了该句字面，见改法①）。

接线（build_v26n.py / localtest/dryrun_087.py 由主控改，本模块不碰主控文件）
--------------------------------------------------------------------------
  · `from yl_r046_ext import apply as v28_r046_apply`
  · `V28_MODULES` 追加 `('r046', v28_r046_apply),` —— ★ **必须排在 `farm2` 之后**
    （锚点取的是 farm2 改造后的形态：单元格 `title: YlxwFtSeedTip` + 成熟行 span）；
    也须晚于 v2810c / farm089，且恒在 `numbal` 之前。建议紧跟 `('farm2', …)` 之后。
  · `localtest/dryrun_087.py` 的 `EXPECTED_ORDER`（第 34 行起）与 `NEW_MODULES` 两处同步。
  · 与 R-047 / R-048（并行的灵田「收益 / 成熟时间」改动）**无锚点交集**：
    本模块只碰播种按钮标注、成熟行标注、两个出口按钮的 title；
    收益/成熟时间函数体、服务端数值、`b.leftMs` 展示表达式一字未动（见冻结门禁）。

硬约束 / 纪律
--------------------------------------------------------------------------
  · INJECT_JS 为空串（纯就地替换）；仍走一遍禁用模式自查。
  · 每个 `p.replace` 带 `expect=` 精确次数（3/2/1/1，均实测）。
  · 锚点里 `变卖/服用` 在 bundle 内是**字面 `\uXXXX` 转义形态**，故锚点/替换串用 raw 串。
  · 只新建本文件；不改 build_v26n.py / build/assets/* / srv/index_v28.ts /
    localtest/* / deploy_v28/* / 任何已有 yl_*_ext.py（尤其 yl_farm2_ext.py）。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = ''          # 本模块只做「就地替换」，无需注入新代码

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- 锚点

# ① 播种目录剔除「废弃(已停种)」。
#    ★ 两步写：保留 `g = YlxwFtCrops(t), h = Object.keys(g);` 字面不动
#      （farm2 的 `R19·面板目录已改走合并` 门禁逐字断言该句 ×3），随后就地过滤。
#      retired 缺字段时 `!(undefined === true)` = true ⇒ 保留（向后兼容零回归）。
A_OLD = 'g = YlxwFtCrops(t), h = Object.keys(g);'
A_NEW = ('g = YlxwFtCrops(t), h = Object.keys(g); '
         'h = h.filter(function (k) { return !(g[k] && g[k].retired === true); });')

# ② 播种按钮下的常显「变卖/服用」标注 → 删除（hover 由既有 title: YlxwFtSeedTip 承担）
#    T5 活面板 + T10 死面板同源行 ⇒ expect=2
B_OLD = ('[cropBtn(N, x), e.jsx("span", { className: "text-[10px] text-stone-400 leading-tight", '
         'children: YlxwFtHarvestText(g[x] || {}, N.slot) })], '
         'title: YlxwFtSeedTip(g[x] || {}, N.slot) }, x);')
B_NEW = '[cropBtn(N, x)], title: YlxwFtSeedTip(g[x] || {}, N.slot) }, x);'

# ③ 成熟田块行内常显标注 → 删除；描述下沉到「变卖」按钮 title（仅 T5 活面板 ⇒ expect=1）
C_OLD = (r'b.ready && e.jsx("span", { className: "text-[10px] text-stone-400 leading-tight", '
         r'children: YlxwFtHarvestText(cd, N.slot) }), '
         r'b.ready && e.jsx(YlxwBtn, { disabled: !!u, onClick: function () { doSell(N.slot, cd); }, '
         r'children: "\u53d8\u5356" }),')
C_NEW = (r'b.ready && e.jsx(YlxwBtn, { title: "\u53d8\u5356 " + YlxwFtSellText(cd, N.slot), '
         r'disabled: !!u, onClick: function () { doSell(N.slot, cd); }, '
         r'children: "\u53d8\u5356" }),')

# ④「服用」按钮 title（仅 T5 活面板 ⇒ expect=1）
D_OLD = (r'b.ready && e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, '
         r'onClick: function () { doConsume(N.slot, cd); }, children: "\u670d\u7528" })')
D_NEW = (r'b.ready && e.jsx(YlxwBtn, { tone: "ghost", '
         r'title: "\u670d\u7528 " + YlxwFtConsumeText(cd), disabled: !!u, '
         r'onClick: function () { doConsume(N.slot, cd); }, children: "\u670d\u7528" })')

# 成熟行常显标注的完整串（用于「已清零」门禁）
MATURE_ANNOT = ('b.ready && e.jsx("span", { className: "text-[10px] text-stone-400 leading-tight", '
                'children: YlxwFtHarvestText(cd, N.slot) })')

EDITS = [
    ('① 播种目录剔除废弃(retired)',  A_OLD, A_NEW, 3),
    ('② 播种常显标注→hover',        B_OLD, B_NEW, 2),
    ('③ 成熟行常显标注→按钮 hover',  C_OLD, C_NEW, 1),
    ('④ 服用按钮 hover',            D_OLD, D_NEW, 1),
]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 farm089 / v2810c / farm2）；
    ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检 1：替换串必须真的变了，且含新特征（防手滑写成恒等 / 写错方向）
    for _nm, _a, _b, _e in EDITS:
        if _a == _b:
            raise AssertionError('r046 %s：锚点替换为恒等（无改动）' % _nm)
    if 'retired' not in A_NEW:
        raise AssertionError('r046 ① 替换串缺 retired 过滤')
    if r'"\u53d8\u5356 " + YlxwFtSellText(cd, N.slot)' not in C_NEW:
        raise AssertionError('r046 ③ 替换串缺「变卖」hover')
    if r'"\u670d\u7528 " + YlxwFtConsumeText(cd)' not in D_NEW:
        raise AssertionError('r046 ④ 替换串缺「服用」hover')
    if 'YlxwFtHarvestText' in B_NEW or 'YlxwFtHarvestText' in C_NEW:
        raise AssertionError('r046 ②③ 常显标注未被移除（仍含 YlxwFtHarvestText）')

    # 自检 2：注入块（空串）禁用模式自查 —— 与其它模块同构
    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r046 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for _pat in BAN_PATTERNS:
        if _pat in blk:
            raise AssertionError('r046 注入块含禁用模式: %s' % _pat)

    # 就地替换
    for name, old, new, exp in EDITS:
        p.replace(name, old, new, expect=exp)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= ① 废弃(已停种) 不再展示 =================
        ('R46·播种目录已过滤废弃',     A_NEW,                                            3, '==', 'retired(已停种/废弃) 从播种列表剔除'),
        ('R46·废弃判据=retired',       '!(g[k] && g[k].retired === true)',               3, '==', '服务端 crops 旧种标记；显式 true 才剔除，缺字段保留'),
        ('R46·合并目录串仍在(未回踩)', 'g = YlxwFtCrops(t), h = Object.keys(g);',         3, '==', 'farm2 R19·面板目录已改走合并 门禁仍成立（两步写）'),
        # ================= ② 变卖/服用描述只留 hover =================
        ('R46·播种常显标注已清零',     'children: YlxwFtHarvestText(g[x] || {}, N.slot)', 0, '==', 'v2810c A 标注行：改由 hover 承担'),
        ('R46·成熟行常显标注已清零',   MATURE_ANNOT,                                      0, '==', 'farm2 R19 成熟行预览：改由按钮 hover 承担'),
        ('R46·常显标注 class 全清',    'text-[10px] text-stone-400 leading-tight',        0, '==', '播种×2 + 成熟×1 全移除'),
        ('R46·标注函数仅余 hover 复用', 'YlxwFtHarvestText',                              2, '==', '定义 1 + YlxwFtSeedTip 复用 1；常显调用点清零'),
        ('R46·播种 hover 保留',        'title: YlxwFtSeedTip(g[x] || {}, N.slot)',        2, '==', 'R-019② 已挂 hover 未动'),
        ('R46·变卖按钮 hover 已挂',    r'title: "\u53d8\u5356 " + YlxwFtSellText(cd, N.slot)', 1, '==', '与二次确认弹窗同源函数'),
        ('R46·服用按钮 hover 已挂',    r'title: "\u670d\u7528 " + YlxwFtConsumeText(cd)', 1, '==', '与二次确认弹窗同源函数'),
        ('R46·播种按钮仍在',           'children: [cropBtn(N, x)]',                       2, '==', 'T5 活 + T10 死（只去标注，不删按钮）'),
        ('R46·变卖按钮仍在',           r'children: "\u53d8\u5356"',                       1, '==', 'farm089 T5·双按钮·变卖 仍成立'),
        ('R46·服用按钮仍在',           r'children: "\u670d\u7528"',                       1, '==', 'farm089 T5·双按钮·服用 仍成立'),
        # ================= 冻结：只碰显示，没动任何数值 =================
        ('冻结·灵田面板函数未动',       'function YlxwTFarmT5() {',                        1, '==', ''),
        ('冻结·面板注册未动',           'YLXW_COMP.farm=YlxwTFarmT5;',                    1, '==', ''),
        ('冻结·变卖收益函数未动',       'function YlxwFtSellText(cd, slot) {',            1, '==', 'R-047 改「值」不改函数；本模块不碰收益口径'),
        ('冻结·服用收益函数未动',       'function YlxwFtConsumeText(cd) {',               1, '==', 'R-047 面：服用收益函数一字未动'),
        ('冻结·收获结算调用未动',       '"/farm/harvest", { slot: q.slot, mode: mode }',  1, '==', ''),
        ('冻结·双出口分流未动',         'var mode = q.kind === "consume" ? "consume" : "sell";', 1, '==', ''),
        ('冻结·弹窗变卖收益同源未动',   'YlxwFtSellText(confirm.cd, confirm.slot)',       1, '==', ''),
        ('冻结·弹窗服用收益同源未动',   'YlxwFtConsumeText(confirm.cd)',                  1, '==', ''),
        ('冻结·种植入口未动',           '"/farm/plant"',                                  3, '==', '种植条件面'),
        ('冻结·开垦入口未动',           '"/farm/unlock"',                                 3, '==', '扩充/开垦入口（R-049 面）'),
        ('冻结·照料入口未动',           '"/farm/tend"',                                   2, '==', ''),
        ('冻结·催熟入口未动',           '"/farm/boost"',                                  2, '==', ''),
        ('冻结·成熟时间展示未动',       'YlxwMin(YlxwNum(b.leftMs))',                     3, '==', 'R-048 改成熟时间「值」，展示表达式一字未动'),
        ('冻结·扩充等级表未动',         'Pr=[{level:1,name:',                            1, '==', 'R-049 面：洞府等级槽位表一字未动'),
    ]
    return gates
