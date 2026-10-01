# -*- coding: utf-8 -*-
"""yl 0.8.12 char2 —— 角色系统三合一（R-012 / R-014 / R-015）

归属：impl-char。文件所有权：本文件 + localtest/t_char2.py + 报告_char2.md。
不部署上线；不碰 build_v26n.py / deploy_v28 / smoke_* / 其它 yl_*_ext.py。

基线：index-v2811-20260930.js（0.8.11 已装配、未上线，2063352 B）。
本模块必须接在 v2811a **之后**、numbal **之前**装配
（V28_MODULES 追加 ('char2', v28_char2_apply)，插在 ('v2811a', ...) 与 ('numbal', ...) 之间）。

三项需求与落点（口径全部有代码实证，见 报告_char2.md §1）：
  R-012 角色属性面板补说明 + 补隐藏属性
    · 声望 / 幸运 作用说明：按基座真实消费点写，不臆测
        声望 → 声望商店进入门槛 reputationRequired=100（@455333）+ 奇遇结算 reputationChange
        幸运 → 奇遇触发概率 luck*0.001（@1699971，整体上限 .3）
               + 炼丹成功率 luck*0.001 / 品级 luck*0.05（@748497 / @748643）
               + 历练遇敌率 luck*0.00015（@696665）
      **复用 v2810a 的 YlxwStatHintEl(key) + YLXW_STAT_HINT 表**（只往表里追加 reputation/luck
        两个 key，不重定义 helper、不重定义表）——避免全链出现两处同款 10px 灰字小字类，
        打破 v2810a 的「说明小字为 10px 灰字 == 1」唯一性门禁。
    · 隐藏战斗属性：暴击 / 暴伤 / 闪避 / 吸血 / 减伤
        取 YlxwBattleBonus(player) —— 快速战斗 X0（@697616）**唯一**实际消费的战斗增益聚合器
        （来源 = 羁绊 YlxwBondCap + 装备洗炼 reforgeAffixes + 自创神通 customSpells，
          末尾 YlxwBattleCap 统一封顶）
    · 「命中」**玩家侧不存在**：hit 只出现在敌人数据（@987947 enemy.hit / @998944 敌人面板）
        ⇒ 不渲染、不造数；报告 §1.3 明示。
    · 宠物加成 YlxwPetBonusTotal 的 critRate/dodgeRate 本 bundle 中**只被妖灵面板展示**
      （调用点仅 YlxwPetStatRow / YlxwPetLaneBar），未进入任何战斗公式
        ⇒ 不并入本面板（避免误导）；报告 §1.4 单列为待 lead 决策项。
  R-014 「称号系统」区块移到左列「仙务·修行统计」上方
    · 角色系统弹窗外壳已是两列：左列 = YlxwFuse({k:__xw})（仙务·称号 + 仙务·修行统计），
      右列 = 原生内容（... 天赋 → 称号系统）
    · 做法：把 hM 内「称号系统」整块（5818 B，右列数组末元素）**搬进**模块级槽位
      YLXW_C2_FUSE_SLOT（由 hM 渲染期赋值）；YlxwFuse 渲染 "stats" 面板前插入该槽位
      ⇒ 左列顺序变为 仙务·称号 → 称号系统 → 仙务·修行统计
    · 槽位复用原 JSX，L/A/I/B/P/V/d/a/fd/_t/Y/Ln 全部仍取 hM 作用域，零逻辑重写
    · 不改 xw:["titles","stats"]（yl_flow083_ext 门禁要求 count=1）
  R-015 天赋页默认折叠 + 天赋描述标注加成属性
    · 新增 state [YLXW_C2_TAL,YLXW_C2_TALS]（默认 !1 = 折叠）
    · 每条天赋描述行前插入 YlxwTitleEffectsLine(F.effects)（复用 v2810a 的 effects→文本格式化）

注入块 zh() 后纯 ASCII；不含 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-。
每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
"""

import re

# --------------------------------------------------------------------------- 注入块（辅助函数）

INJECT_JS = r'''
/* ===== yl-0.8.12 char2 =====
   R-012 角色属性面板补说明 + 补隐藏战斗属性
   R-014 「称号系统」搬到左列「仙务·修行统计」上方
   R-015 天赋默认折叠 + 天赋描述标注加成属性
   纯客户端 UI：不写存档、不发网络请求、不改任何战斗数值。 */

/* R-014 槽位：角色系统左列在「仙务·修行统计」之前插入的节点。
   由 hM（角色系统弹窗组件）在渲染期赋值，YlxwFuse 渲染 "stats" 面板前读取。 */
var YLXW_C2_FUSE_SLOT = null;

/* R-012-A 声望 / 幸运 的作用说明 —— **不在此重定义**：
   复用 v2810a 的 YlxwStatHintEl(key)（同一处 10px 灰字节点，全链唯一），
   两条文案以 key 形式追加在 v2810a 的 YLXW_STAT_HINT 表（只加不改）。 */

/* R-012-B 战斗增益登记表（= 快速战斗实际消费的 YlxwBattleBonus 口径） */
var YLXW_C2_BATTLE = [
  { k: "critRate", label: "暴击" },
  { k: "critDamage", label: "暴伤" },
  { k: "dodgeRate", label: "闪避" },
  { k: "lifeLeech", label: "吸血" },
  { k: "damageReduction", label: "减伤" }
];
function YlxwChar2Bonus(a) {
  try { return (typeof YlxwBattleBonus === "function") ? (YlxwBattleBonus(a) || null) : null; }
  catch (err) { return null; }
}
function YlxwChar2Cells(a, b) {
  var o = YlxwChar2Bonus(a), out = [], i, d, v;
  if (!o) return out;
  for (i = 0; i < YLXW_C2_BATTLE.length; i++) {
    d = YLXW_C2_BATTLE[i];
    v = Number(o[d.k]) || 0;
    out.push(e.jsxs("div", { key: "ylxw-c2-" + d.k, children: [
      e.jsx("span", { className: "text-stone-400", children: d.label + ":" }),
      " ",
      e.jsx("span", { className: "text-cyan-400 font-bold", children: Math.round(v * 100) + "%" })
    ] }));
  }
  return out;
}
function YlxwChar2BattleNote() {
  return e.jsx("div", { className: "text-xs text-stone-500 mt-2", children: "战斗增益（暴击/暴伤/闪避/吸血/减伤）来自羁绊 · 装备洗炼 · 自创神通；玩家无「命中」属性。" });
}
'''

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']


def _assert_block_clean(block):
    bad = re.findall(r'[^\x00-\x7f]', block)
    if bad:
        raise AssertionError('char2 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for pat in BAN_PATTERNS:
        if pat in block:
            raise AssertionError('char2 注入块含禁用模式: %s' % pat)


# --------------------------------------------------------------------------- 锚点（基座唯一，逐字）

# --- 注入块落点：v2810a 注入块之前（保持 v2810a 的「}\nfunction YlxwTTitles() {」门禁不变）---
V2810A_BLK_HEAD = '/* ===== yl-0.8.10 v2810a ====='

# --- R-012 ---
# v2810a 补充属性单元格里的数值 span（落点在 v2810a 注入块内）
EXTRA_SPAN = 'e.jsx("span", { className: "text-cyan-400 font-bold", children: s })'
# 面板 grid 末格（声望）收口（v2810a 已在此追加 ...YlxwStatExtraCells(a,b)）
REP_CELL_TAIL = ('e.jsx("span",{className:"text-mystic-gold font-bold",'
                 'children:a.reputation||0})]})')
# 补充属性展开点收口
CELLS_TAIL = '...YlxwStatExtraCells(a,b)]})'
# 「属性来源分解」块起点（战斗增益来源说明插在它之前，作为面板 children 的兄弟）
SRC_NOTE_ANCHOR = (',h&&e.jsxs("div",{className:"mt-3 pt-3 border-t border-stone-700 '
                   'text-xs space-y-1",children:[e.jsx("div",{className:"text-stone-500 '
                   'mb-2",children:"属性来源分解:"})')

# --- R-014 ---
# YlxwFuse 的无槽位原路径（必须原样保留：localtest/t_flow083.py 依赖该串）
FUSE_MAP_LINE = ('return e.jsx(e.Fragment, { children: ks.map(function (k, i) '
                 '{ return YlxwFuseOne(k, k + i); }) });')
# hM 的 return（xw:["titles","stats"] 必须 count=1 —— yl_flow083_ext 门禁）
HM_RETURN = 'return e.jsxs(e.Fragment,{children:[e.jsx(ct,{xw:["titles","stats"],'
# 右列「天赋块 → 称号块」边界（称号块 HEAD）
TITLE_HEAD = 'children:"未选择天赋"})})]}),'
# 称号块 TAIL（其后紧跟 character 分支的 else = 数据统计 tab）
TITLE_TAIL = ']}):e.jsx(e.Fragment,{children:e.jsxs("div",{className:"space-y-4"'

# --- R-015 ---
# 天赋折叠 state 插入点（const 链末）
STATE_ANCHOR = '[A,I]=O.useState(!1);'
# 天赋块标题（h3）
TALENT_H3 = ('e.jsxs("h3",{className:"text-lg font-bold mb-3 flex items-center gap-2",'
             'children:[e.jsx(aa,{className:"text-purple-400",size:20}),"\u5929\u8d4b",'
             'U.length>1&&e.jsxs("span",{className:"text-xs text-stone-500",'
             'children:["(",U.length,")"]})]})')
# 天赋描述行
TALENT_DESC = 'e.jsx("p",{className:"text-sm text-stone-400 mb-2",children:F.description})'
# 折叠包裹起点：h3 之后紧接的 U.length>0? 三元（把三元整体纳入折叠体，避免空数组洞）
TALENT_BODY_ANCHOR = TALENT_H3 + ',U.length>0?'
# 折叠包裹终点：天赋块 children 数组收口（「未选择天赋」空态之后）
TALENT_BLOCK_CLOSE = 'children:"未选择天赋"})})]})'

# YlxwFuse 槽位分支（渲染 "stats" 面板前插入左列槽位）
FUSE_SLOT_JS = (
    'if (YLXW_C2_FUSE_SLOT) {\n'
    '    var _c2o = [], _c2i;\n'
    '    for (_c2i = 0; _c2i < ks.length; _c2i++) {\n'
    '      if (ks[_c2i] === "stats") _c2o.push(e.jsx("div", { key: "ylxw-c2-slot", '
    'className: "pt-4 border-t-2 border-dashed border-stone-600", children: YLXW_C2_FUSE_SLOT }));\n'
    '      _c2o.push(YlxwFuseOne(ks[_c2i], ks[_c2i] + _c2i));\n'
    '    }\n'
    '    return e.jsx(e.Fragment, { children: _c2o });\n'
    '  }\n  '
)


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    _assert_block_clean(blk)

    # 0) 辅助函数块：插在 v2810a 注入块**之前**（顶层同作用域；函数声明提升，
    #    且不会破坏 v2810a 的「}\nfunction YlxwTTitles() {」门禁）
    p.replace('c2-helpers', V2810A_BLK_HEAD, blk + V2810A_BLK_HEAD, expect=1,
              note='v2810a 块前注入 char2 辅助函数（槽位 / 声望幸运说明 / 战斗增益 / 来源说明）')

    # ------------------------------------------------------------------ R-014
    # 1a) 在运行期按 HEAD/TAIL 边界切出「称号系统」整块（避免把 5818 B JSX 硬编码进模块）
    src = p.text
    i = src.index(TITLE_HEAD) + len(TITLE_HEAD)
    j = src.index(TITLE_TAIL, i)
    title_block = src[i:j]
    # 基座自带 UI 文案在 bundle 里是**原始中文**（非 zh() 转义形态）
    if len(title_block) < 2000 or '称号系统' not in title_block:
        raise AssertionError('char2 R-014 抽出的称号块异常（len=%d）' % len(title_block))

    # 1b) 从右列数组移除该块（连前导逗号一并去掉）
    p.replace('c2-title-cut', TITLE_HEAD + title_block, TITLE_HEAD, expect=1,
              note='右列移除「称号系统」整块（%d chars）' % len(title_block))

    # 1c) hM 渲染期把该块交给左列槽位（赋值语句插在 return 之前；此处 L/A/I/B/P/V/d 等均已定义）
    p.replace('c2-title-put', HM_RETURN,
              'YLXW_C2_FUSE_SLOT=[' + title_block + '];' + HM_RETURN, expect=1,
              note='hM 渲染期把「称号系统」块交给 YLXW_C2_FUSE_SLOT')

    # 1d) YlxwFuse 在渲染 "stats" 面板前插入槽位（原 map 路径原样保留）
    p.replace('c2-fuse-slot', FUSE_MAP_LINE, FUSE_SLOT_JS + FUSE_MAP_LINE, expect=1,
              note='YlxwFuse 在 "stats" 面板前插入左列槽位')

    # ------------------------------------------------------------------ R-012
    # 2a) 声望数值后追加作用说明小字（复用 v2810a 的 YlxwStatHintEl，不重定义）
    p.replace('c2-hint-rep', REP_CELL_TAIL,
              REP_CELL_TAIL.replace('})]})', '}),YlxwStatHintEl("reputation")]})'), expect=1,
              note='声望数值后追加 YlxwStatHintEl("reputation")')
    # 2b) v2810a 补充属性项逐项挂说明（复用 v2810a 的 helper；当前仅「幸运」有文案）
    p.replace('c2-hint-extra', EXTRA_SPAN, EXTRA_SPAN + ',YlxwStatHintEl(d.k)', expect=1,
              note='补充属性项追加 YlxwStatHintEl(d.k)（幸运说明）')
    # 2c) 声望格后展开战斗增益单元格（暴击/暴伤/闪避/吸血/减伤）
    p.replace('c2-cells', CELLS_TAIL,
              CELLS_TAIL.replace(']})', ',...YlxwChar2Cells(a,b)]})'), expect=1,
              note='声望格后展开 ...YlxwChar2Cells(a,b)')
    # 2d) 「属性来源分解」之前插入战斗增益来源说明（面板 children 兄弟，常显）
    p.replace('c2-note', SRC_NOTE_ANCHOR,
              ',YlxwChar2BattleNote()' + SRC_NOTE_ANCHOR, expect=1,
              note='属性来源分解前插入战斗增益来源说明')

    # ------------------------------------------------------------------ R-015
    expand = zh('展开')
    collapse = zh('收起')
    # 3a) 天赋折叠 state
    p.replace('c2-tal-state', STATE_ANCHOR,
              STATE_ANCHOR + 'var [YLXW_C2_TAL,YLXW_C2_TALS]=O.useState(!1);', expect=1,
              note='天赋默认折叠 state（初始 false=折叠）')
    # 3b) 天赋标题加 展开/收起 按钮，并把三元整体纳入折叠体
    h3_new = TALENT_H3[:-3] + (',e.jsx("button",{onClick:()=>YLXW_C2_TALS(!YLXW_C2_TAL),'
                                'style:{marginLeft:"auto"},className:"text-xs text-stone-400 '
                                'hover:text-stone-300",children:YLXW_C2_TAL?"' + collapse + '":"'
                                + expand + '"})]})')
    p.replace('c2-tal-h3', TALENT_BODY_ANCHOR,
              h3_new + ',YLXW_C2_TAL&&e.jsxs(e.Fragment,{children:[U.length>0?', expect=1,
              note='天赋标题加 展开/收起 按钮 + 折叠包裹开始')
    # 3c) 折叠包裹收口（插在天赋块 children 数组收口之前）
    p.replace('c2-tal-tail', TALENT_BLOCK_CLOSE, TALENT_BLOCK_CLOSE + ']})', expect=1,
              note='天赋折叠包裹收口')
    # 3d) 天赋描述行前插入加成属性行
    p.replace('c2-tal-desc', TALENT_DESC, 'YlxwTitleEffectsLine(F.effects),' + TALENT_DESC, expect=1,
              note='天赋描述行前插入 YlxwTitleEffectsLine(F.effects)')

    # ------------------------------------------------------------------ 门禁
    gates = [
        # ---- 注入块就位 ----
        ('c2·槽位变量已注入',        'var YLXW_C2_FUSE_SLOT = null;',             1, '==', ''),
        ('c2·战斗增益登记表',        'var YLXW_C2_BATTLE = [',                    1, '==', ''),
        ('c2·战斗增益聚合读取',      'function YlxwChar2Bonus(a) {',              1, '==', ''),
        ('c2·战斗增益单元格函数',    'function YlxwChar2Cells(a, b) {',           1, '==', ''),
        ('c2·战斗增益来源说明函数',  'function YlxwChar2BattleNote() {',          1, '==', ''),
        ('c2·注入块紧贴 v2810a 前',  '}\n' + V2810A_BLK_HEAD,                     1, '==', '顶层同作用域'),

        # ---- R-012 声望 / 幸运说明（复用 v2810a 的 YlxwStatHintEl） ----
        ('c2·声望说明已挂载',        'children:a.reputation||0}),YlxwStatHintEl("reputation")]})', 1, '==', ''),
        ('c2·声望说明文案',          r'reputation: "\u5f71\u54cd\u58f0\u671b\u5546\u5e97\u95e8\u69db\u4e0e\u5947\u9047\u7ed3\u7b97"', 1, '==', '追加在 v2810a 的 YLXW_STAT_HINT 表'),
        ('c2·幸运说明文案',          r'luck: "\u5f71\u54cd\u5947\u9047\u89e6\u53d1\u3001\u70bc\u4e39\u6210\u529f\u7387\u4e0e\u54c1\u7ea7"', 1, '==', '追加在 v2810a 的 YLXW_STAT_HINT 表'),
        ('c2·补充属性项逐项挂说明',  'children: s }),YlxwStatHintEl(d.k)',        1, '==', 'v2810a 补充项挂说明（仅幸运有文案）'),
        ('c2·未另起说明文案表',      'var YLXW_C2_HINT = {',                      0, '==', '复用 v2810a 的 YLXW_STAT_HINT 表'),
        ('c2·未另起说明节点函数',    'function YlxwChar2HintEl(',                  0, '==', '复用 v2810a helper，不重定义'),

        # ---- R-012 隐藏战斗属性 ----
        ('c2·战斗增益已展开进面板',  '...YlxwStatExtraCells(a,b),...YlxwChar2Cells(a,b)]})', 1, '==', ''),
        ('c2·战斗增益来源说明已挂',  ',YlxwChar2BattleNote(),h&&e.jsxs(',         1, '==', ''),
        ('c2·暴击项已登记',          r'{ k: "critRate", label: "\u66b4\u51fb" }',  1, '==', ''),
        ('c2·暴伤项已登记',          r'{ k: "critDamage", label: "\u66b4\u4f24" }', 1, '==', ''),
        ('c2·闪避项已登记',          r'{ k: "dodgeRate", label: "\u95ea\u907f" }', 1, '==', ''),
        ('c2·吸血项已登记',          r'{ k: "lifeLeech", label: "\u5438\u8840" }', 1, '==', ''),
        ('c2·减伤项已登记',          r'{ k: "damageReduction", label: "\u51cf\u4f24" }', 1, '==', ''),
        ('c2·百分比展示',            'children: Math.round(v * 100) + "%"',       1, '==', ''),
        ('c2·v2810a 补充属性调用保留', '...YlxwStatExtraCells(a,b)',               1, '==', 'v2810a 门禁不变'),
        ('c2·战斗表未含命中',        r'label: "\u547d\u4e2d" }',                  0, '==', 'c2 战斗表不含命中（玩家无该字段，不造数）'),
        ('c2·v2810a 命中项原样保留', r'{ k: "hit", label: "\u547d\u4e2d", pct: 1 }', 1, '==', 'v2810a 登记表未动（缺字段⇒运行期不渲染）'),

        # ---- R-014 称号系统移左列 ----
        ('c2·右列已无称号块',        TITLE_HEAD + 'e.jsxs("div",{children:[e.jsxs("div",'
                                     '{className:"flex justify-between items-center mb-3"', 0, '==', '必须为 0'),
        ('c2·称号块已交给左列槽位',  'YLXW_C2_FUSE_SLOT=[e.jsxs("div",{children:[e.jsxs("div",'
                                     '{className:"flex justify-between items-center mb-3"', 1, '==', ''),
        ('c2·YlxwFuse 槽位分支已加', 'if (YLXW_C2_FUSE_SLOT) {',                   1, '==', ''),
        ('c2·槽位插在 stats 面板前', 'ks[_c2i] === "stats"',                       1, '==', ''),
        ('c2·槽位包裹样式已挂',      'className: "pt-4 border-t-2 border-dashed border-stone-600", children: YLXW_C2_FUSE_SLOT', 1, '==', ''),
        ('c2·YlxwFuse 原映射保留',   FUSE_MAP_LINE,                                1, '==', '无槽位时走原路径'),
        ('c2·称号系统标题仍在',      '"称号系统",L.length>0&&e.jsxs("span",{className:"text-xs '
                                     'text-stone-500",children:["(",L.length,"/",Ln.length,")"]})', 1, '==', ''),
        ('c2·角色系统 xw 未动',      'xw:["titles","stats"]',                      1, '==', 'v28/flow083 门禁不变'),
        ('c2·外壳融合调用未动',      'e.jsx(YlxwFuse,{k:__xw})',                   1, '==', 'yl_flow083_ext 门禁不变'),
        ('c2·alchemy 融合调用未动',  'e.jsx(YlxwFuse,{k:"alchemy"})',              1, '==', 'yl_flow083_ext 门禁不变'),

        # ---- R-015 天赋折叠 + 加成标注 ----
        ('c2·天赋折叠 state 已注入', 'var [YLXW_C2_TAL,YLXW_C2_TALS]=O.useState(!1);', 1, '==', ''),
        ('c2·天赋标题加折叠按钮',    'children:YLXW_C2_TAL?"' + collapse + '":"' + expand + '"', 1, '==', ''),
        ('c2·折叠按钮靠右',          'style:{marginLeft:"auto"}',                   1, '==', 'Tailwind 无 ml-auto 场景兜底'),
        ('c2·折叠包裹已开始',        'YLXW_C2_TAL&&e.jsxs(e.Fragment,{children:[U.length>0?', 1, '==', ''),
        ('c2·折叠包裹已收口',        TALENT_BLOCK_CLOSE + ']})',                    1, '==', ''),
        ('c2·天赋加成行已挂',        'YlxwTitleEffectsLine(F.effects),' + TALENT_DESC, 1, '==', ''),
        ('c2·天赋块标题保留',        '"天赋",U.length>1&&e.jsxs("span",{className:"text-xs '
                                     'text-stone-500",children:["(",U.length,")"]})', 1, '==', ''),
        ('c2·天赋空态保留',          'children:"未选择天赋"',                       1, '==', ''),
        ('c2·天赋不可修改注释保留',  'children:"* 天赋在游戏开始时随机生成，之后不可修改"', 1, '==', ''),

        # ---- 基线完整性（防误伤）----
        ('c2·面板攻击项未动',        'children:b.attack})',                          1, '==', ''),
        ('c2·面板防御项未动',        'children:b.defense})',                         1, '==', ''),
        ('c2·面板气血项未动',        'children:[a.hp,"/",b.maxHp]',                  1, '==', ''),
        ('c2·面板声望项未动',        'children:a.reputation||0})',                    1, '==', ''),
        ('c2·v2810a 神识说明保留',   'children:b.spirit}),YlxwStatHintEl("spirit")',   1, '==', ''),
        ('c2·v2810a 体魄说明保留',   'children:b.physique}),YlxwStatHintEl("physique")', 1, '==', ''),
        ('c2·v2810a 速度说明保留',   'children:b.speed}),YlxwStatHintEl("speed")',    1, '==', ''),
        ('c2·v2810a 称号加成行保留', 'YlxwTitleEffectsLine(F.effects),e.jsx("p",{className:"text-xs '
                                     'text-stone-400 mb-1",children:F.description})', 1, '==', ''),
        ('c2·角色系统标题未动',      'title:"角色系统"',                              1, '==', ''),
        ('c2·YlxwFuseOne 未被破坏',  'function YlxwFuseOne(k, key) {',              1, '==', ''),
        ('c2·YlxwTTitles 未被破坏',  'function YlxwTTitles() {',                    1, '==', ''),
    ]
    return gates
