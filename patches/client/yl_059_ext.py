# -*- coding: utf-8 -*-
r"""
yl_059_ext.py — R-059 人物志·缘契：寻访好感「首次 15~16、后续递减」+ 每 NPC 解锁档 2→4（全档奖励·**手动领取**）

需求原文（需求台账_进行中.md:25，逐字）
--------------------------------------------------------------------------
  「道友图鉴 · 缘契 首次寻访+15,16点左右可以。但是后续寻访数量要减少。
    并且每个NPC的解锁档位也增加为4个。4个档位都有相应的奖励。」

侦察结论（build/assets/index-v28116-20261001.js 逐字实证，2026-10-01）
--------------------------------------------------------------------------
  寻访好感（结识/重逢两条产生点路径，共 3 处同文代码）——现值全部平给：
    · YlxwCharDexPanelT6.doVisit（t6chardex 注入，现役左列寻访）
        结识 `var gain = 15 + Math.floor(Math.random() * 11);`  ⇒ +15~25
        重逢 `var g0 = 4 + Math.floor(Math.random() * 6);`      ⇒ +4~9
    · 旧 YlxwCharDexPanel（v28 死代码，与 T6 同文 ⇒ 同形替换 ×2）
    · YlxwRnPickVisit（renwu 注入，R34 任务板「提交即寻访」，每日 5+5 条）
        `gain: 15 + Math.floor(Math.random() * 11),` / `gain: 4 + Math.floor(Math.random() * 6),`
      —— 每日可重复的主寻访通道，必须一并递减，否则「后续递减」形同虚设。
  解锁档位（UI 里带「解锁」二字的每 NPC 面）——现值恰 2 档、纯文案零奖励：
    · YlxwCharBondPanelT6（右列详情）：【小传】缘契达 50 解锁 /【秘辛】缘契达 100 解锁
    · YlxwCharDexPanelT6 selBlock（左列图鉴详情）：同两档（selEntry 形态）
    ⇒ 旧 v28 死面板各有 byte 级同形副本，一并替换 ×2（防门禁计数特化）。
  ★「解锁档位」≠ 缘契里程碑：YLXW_CHAR_BOND_MILE=[25,50,75,100] 自 0.8.7 起就是 4 档
    且全有随机物品奖励（R-058 已裁「每 NPC 各阶段领奖已落地」并冻结）；
    本模块不碰里程碑表/件数表/领取 chips，冻结门禁逐条证明。

本模块动作（纯客户端就地替换 + 两小块函数注入，零网络、零服务端改动）
--------------------------------------------------------------------------
  ① 寻访递减（结识增益按「已识道友序号」递减）：
     注入 `function YlxwCharVisitGain(metN)`：base = max(15-2*metN, 4)，+rand(0..1)
       第 1 位 15~16（需求口径「可以」）/ 第 2 位 13~14 / 第 3 位 11~12 / … 第 7 位起 4~5
     · T6 doVisit 结识 → `var gain = YlxwCharVisitGain(YlxwCharMetN(p));`（死面板同形 ×2）
     · renwu YlxwRnPickVisit 结识 → `gain: YlxwCharVisitGain(YlxwCharMetN(p)),`（p 是入参）
     · 重逢（全图鉴集齐后的回访）4~9 → 2+rand(3)=2~4（三处同改）
     递减键选 YlxwCharMetN（派生态，两路自动同源）；不用 ps.visits——任务提交不 increment
     visits，用它会漏掉主通道。
  ② 解锁档 2→4，全档有奖励，**手动领取**（点 NPC 详情面板按钮；照抄「缘契里程碑」chips 交互）：
       【相识】25 → 灵石 ×round(100×rf)
       【小传】50 → 随机物品 ×2（YlxwCharRollRow 行 3）
       【轶事】75 → 灵石 ×round(200×rf)（新档，正文 =「人送雅号「title」，缘起：hint」）
       【秘辛】100 → 随机物品 ×3（行 5）+ 灵石 ×round(300×rf)
     · BondPanelT6 内新增 `claimUnl(at)` + `unlChips`（4 个 button：未达 disabled / 可领 amber /
       已领 ✓ emerald），与同面板「缘契里程碑」chips **完全同款**；**点击才发**，
       幂等落 `player.charDex.unl[relId][at]`，随 /api/save 整包落库。
     · **已自动发过的玩家**：沿用**同一** charDex.unl 字段 ⇒ 已发档位直接显示「已领取」不可重领
       （不会重复发放），未达档位转为手动领取。**服务端零改动**。
     · 四档文案在 4 个面板副本（死/T6 × BondPanel/selBlock）保留为正文展示，锁定态提示各档奖励。

AI 代决（无人值守；详见 拍板/2026-10-01_*_R-059_*.md）
--------------------------------------------------------------------------
  1. 「解锁档位」判为【小传】/【秘辛】UI 面（2→4）；缘契里程碑已是 4 档，不动；
  2. 递减键 = 已识道友数 YlxwCharMetN（全图鉴 24 位，第 7 位起触底 4~5），
     覆盖面板寻访与任务提交两条产生点；重逢另压至 2~4；
  3. 解锁奖励**手动领取**（点 NPC 详情面板按钮；与缘契里程碑 chips 同款交互，幂等落 charDex.unl）；
     非图鉴道友（历练偶遇的无名者）不设解锁档；
  4. 死代码（旧 DexPanel/BondPanel）与现役 T6 同形替换 ×2。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 锚点全部 raw ASCII（bundle 内 \uXXXX 转义形，逐串实测 count：2/2/1/1/1/2/2/1/1，
    见 __main__ 改前断言）；新写入文本含中文一律 zh() 转义，落 bundle 纯 ASCII。
    含中文的锚点一律不写死——本模块锚点全用 ASCII 边界截取（A_UNL_RENDER 取 questCard 行）。
  · 注入/替换内容不含 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-/fetch(
    （BAN_PATTERNS 硬断言 + effect 域内限域门禁）。
  · 不碰 build_v26n.py / localtest/ / deploy_v28/ / srv/index_v28.ts / CHANGELOG.md；
    服务端零改动：srv/index_v28.ts 全文 0 处 charDex / socialRelations（probe 2026-10-01），
    charDex.unl 随整包落库，灵石增量 ≤600×rf 远低于结算配额 ⇒ 无 srv_patch_059。
  · 对相邻模块门禁零影响：renwu/char/t6chardex/chargift083/r058 门禁串一条不改
    （gates 后半逐条冻结；__main__ 另跑「先验门禁重跑」全量复核）。

装配顺序
--------------------------------------------------------------------------
  唯一硬约束：**必须排在 renwu 与 t6chardex 之后**（①④锚在两者注入的代码内）；
  建议紧跟 r058 之后、numbal 之前（第 2 批惯例位）。与 r058 锚区零交集
  （refreshAll/refAll 均在 YlxwCharBoardR34 域内，本模块不进该域，双向已验证）。

导出符号（构建侧契约）
  INJECT_JS : str（''，纯就地替换；YlxwCharVisitGain 经 insert_before 落 char 纯函数层）
  apply(p, ctx) -> list[(name, needle, expect, cmp, note[, within])]
"""

import re

INJECT_JS = ''          # 纯就地替换；递减函数经 insert_before 落纯函数层

# --------------------------------------------------------------------------- 锚点
# 含中文锚点 = bundle 内 \uXXXX 转义形（raw ASCII，zh() 恒等）；新文本写中文原文，apply 内 zh()。

# ① 结识增益（死 DexPanel + T6 DexPanel 各 1 ⇒ expect=2）
A_GAIN_VAR = 'var gain = 15 + Math.floor(Math.random() * 11);'
R_GAIN_VAR = 'var gain = YlxwCharVisitGain(YlxwCharMetN(p));'

# ① 重逢增益（死 + T6 ⇒ expect=2）
A_REV_VAR = 'var g0 = 4 + Math.floor(Math.random() * 6);'
R_REV_VAR = 'var g0 = 2 + Math.floor(Math.random() * 3);'

# ① renwu 任务寻访（`gain:` 键值形态，各 ×1）
A_GAIN_KV = 'gain: 15 + Math.floor(Math.random() * 11),'
R_GAIN_KV = 'gain: YlxwCharVisitGain(YlxwCharMetN(p)),'
A_REV_KV = 'gain: 4 + Math.floor(Math.random() * 6),'
R_REV_KV = 'gain: 2 + Math.floor(Math.random() * 3),'

# ① 递减函数落点：char 纯函数层 YlxwCharEntry 定义之前（唯一；函数声明提升，位置不敏感）
A_HELPER = 'function YlxwCharEntry(id) {'
HELPER_JS = (
    '/* R-059 寻访好感递减：结识第 (metN+1) 位道友的缘契增益 15/13/11/…/下限 4，±1 浮动 */\n'
    'function YlxwCharVisitGain(metN) {\n'
    '  var b = 15 - 2 * (Number(metN) || 0);\n'
    '  if (b < 4) b = 4;\n'
    '  return b + Math.floor(Math.random() * 2);\n'
    '}\n'
    '\n'
)   # ← 不拼 A_HELPER：insert_before 语义 = 锚点原样保留 + 前插代码（r058 用 replace 故需拼，此处不同）

# ② 手动领取：解锁档奖励 chips（★ 照抄同面板「缘契里程碑」chips 交互，不自创）。
#    领取函数 + chips 构造插在里程碑 chips 循环之后（BondPanelT6 独有；锚点纯 ASCII，count=1）。
A_UNL_FN = (
    '      }, "ylxw-charbond-t6-" + rel.id + "-" + mile.at));\n'
    '    })(YLXW_CHAR_BOND_MILE[i3]);\n'
    '  }'
)
UNL_FN_JS = A_UNL_FN + '\n' + (
    '\n'
    '  /* R-059 解锁档奖励（手动领取 · 与缘契里程碑 chips 同款交互）：缘契跨过 25/50/75/100 后\n'
    '     在 NPC 详情面板点按钮领取，幂等落 charDex.unl[relId][at]；奖励物品在 updater 外掷定 */\n'
    '  function claimUnl(at) {\n'
    '    if (bond < at || unlState[String(at)]) return;\n'
    '    var rf59 = 1;\n'
    '    try { rf59 = YlxwCharRf(p); } catch (e59) { rf59 = 1; }\n'
    '    var st59 = 0, items59 = [];\n'
    '    if (at === 25) st59 = Math.round(100 * rf59);\n'
    '    else if (at === 50) items59 = YlxwCharRollRow(3, 2);\n'
    '    else if (at === 75) st59 = Math.round(200 * rf59);\n'
    '    else { items59 = YlxwCharRollRow(5, 3); st59 = Math.round(300 * rf59); }\n'
    '    setP(function (prev) {\n'
    '      var rs59 = (prev.socialRelations || []), cur59 = -101, j59;\n'
    '      for (j59 = 0; j59 < rs59.length; j59++) { if (rs59[j59] && rs59[j59].id === relId) { cur59 = Number(rs59[j59].favorability) || 0; break; } }\n'
    '      if (cur59 < at) return prev; /* 守卫：关系已消失或缘契回退 */\n'
    '      var d59 = YlxwCharDexV2(prev.charDex);\n'
    '      var u59 = Object.assign({}, d59.unl || {});\n'
    '      var m59 = Object.assign({}, u59[relId] || {});\n'
    '      if (m59[String(at)]) return prev; /* 幂等：连点不重发 */\n'
    '      m59[String(at)] = true;\n'
    '      u59[relId] = m59;\n'
    '      d59.unl = u59;\n'
    '      var nx59 = Object.assign({}, prev, { charDex: d59 });\n'
    '      if (st59) nx59.spiritStones = Math.max(0, (Number(prev.spiritStones) || 0) + st59);\n'
    '      if (items59.length) nx59.inventory = YlxwCharPushItems(prev.inventory, items59);\n'
    '      return nx59;\n'
    '    });\n'
    '    var parts59 = [];\n'
    '    if (st59) parts59.push("灵石 ×" + st59);\n'
    '    for (var w59 = 0; w59 < items59.length; w59++) parts59.push(items59[w59].name + " ×" + items59[w59].qty);\n'
    '    log("【人物志】与" + rel.name + "缘契达 " + at + "，解锁奖励：" + parts59.join("、") + "。", "gain");\n'
    '    setNotice("🎉 缘契达 " + at + "，解锁奖励已发放：" + parts59.join("、"));\n'
    '  }\n'
    '\n'
    '  var unlState = ((p && p.charDex && p.charDex.unl) || {})[relId] || {};\n'
    '  var UNL59 = [25, 50, 75, 100];\n'
    '  var unlChips = [];\n'
    '  for (var i59 = 0; i59 < UNL59.length; i59++) {\n'
    '    (function (at) {\n'
    '      var done = !!unlState[String(at)];\n'
    '      var can = bond >= at;\n'
    '      var label = at === 25 ? "【相识】" : (at === 50 ? "【小传】" : (at === 75 ? "【轶事】" : "【秘辛】"));\n'
    '      var rw = at === 25 ? ("灵石 ×" + Math.round(100 * YlxwCharRf(p))) :\n'
    '               at === 50 ? "随机物品 ×2" :\n'
    '               at === 75 ? ("灵石 ×" + Math.round(200 * YlxwCharRf(p))) : "随机物品 ×3 与灵石";\n'
    '      unlChips.push(e.jsx("button", {\n'
    '        disabled: done || !can,\n'
    '        onClick: function () { claimUnl(at); },\n'
    '        className: "px-2 py-1 rounded border text-[10px] transition-colors " + (\n'
    '          done ? "bg-emerald-900/20 border-emerald-700/50 text-emerald-300" :\n'
    '          can ? "bg-amber-600 hover:bg-amber-500 border-amber-500 text-stone-900 font-bold" :\n'
    '                "bg-stone-800 border-stone-700 text-stone-500"),\n'
    '        title: done ? "已领取" : (can ? ("点击领取（" + rw + "）") : ("缘契达 " + at + " 可领")),\n'
    '        children: (done ? "✓ " : "") + label + " " + at\n'
    '      }, "ylxw-charunl-t6-" + relId + "-" + at));\n'
    '    })(UNL59[i59]);\n'
    '  }'
)

# ② 渲染落点：BondPanelT6 return 的 questCard 之后（T6 独有 count=1；锚点纯 ASCII，
#    用 questCard 行做 ASCII 边界——不写死含中文的里程碑标题行）。
A_UNL_RENDER = (
    '  return e.jsxs("div", { className: "space-y-2 pt-2 border-t border-stone-700", children: [\n'
    '    questCard,'
)
UNL_RENDER_JS = A_UNL_RENDER + '\n' + (
    '    e.jsx("div", { className: "text-[11px] text-stone-400 font-bold", children: "缘契解锁档（点击领取）" }),\n'
    '    e.jsx("div", { className: "flex flex-wrap gap-1.5", children: unlChips }),'
)

# ② BondPanel 两档块 → 四档（死 v28 + T6 byte 级同文 ⇒ expect=2）。
#    奖励价内联 YlxwCharRf(p)：T6 BondPanel 无 rf 局部量，死面板有 rf 也不冲突。
A_BOND2 = (
    'entry ? e.jsxs("div", { className: "space-y-1", children: [\n'
    '      e.jsxs("p", { className: "text-[11px] " + (bond >= 50 ? "text-blue-200" : "text-stone-600"), children: [\n'
    '        e.jsx("span", { className: "text-cyan-400 font-bold", children: "\\u3010\\u5c0f\\u4f20\\u3011" }),\n'
    '        bond >= 50 ? entry.bio : "\\u7f18\\u5951\\u8fbe 50 \\u89e3\\u9501"\n'
    '      ] }),\n'
    '      e.jsxs("p", { className: "text-[11px] " + (bond >= 100 ? "text-amber-200" : "text-stone-600"), children: [\n'
    '        e.jsx("span", { className: "text-amber-400 font-bold", children: "\\u3010\\u79d8\\u8f9b\\u3011" }),\n'
    '        bond >= 100 ? entry.secret : "\\u7f18\\u5951\\u8fbe 100 \\u89e3\\u9501"\n'
    '      ] })\n'
    '    ] })'
)
R_BOND4 = (
    'entry ? e.jsxs("div", { className: "space-y-1", children: [\n'
    '      e.jsxs("p", { className: "text-[11px] " + (bond >= 25 ? "text-stone-300" : "text-stone-600"), children: [\n'
    '        e.jsx("span", { className: "text-emerald-400 font-bold", children: "【相识】" }),\n'
    '        bond >= 25 ? entry.desc : "缘契达 25 解锁 · 奖励 灵石×" + Math.round(100 * YlxwCharRf(p))\n'
    '      ] }),\n'
    '      e.jsxs("p", { className: "text-[11px] " + (bond >= 50 ? "text-blue-200" : "text-stone-600"), children: [\n'
    '        e.jsx("span", { className: "text-cyan-400 font-bold", children: "【小传】" }),\n'
    '        bond >= 50 ? entry.bio : "缘契达 50 解锁 · 奖励 随机物品×2"\n'
    '      ] }),\n'
    '      e.jsxs("p", { className: "text-[11px] " + (bond >= 75 ? "text-stone-300" : "text-stone-600"), children: [\n'
    '        e.jsx("span", { className: "text-pink-400 font-bold", children: "【轶事】" }),\n'
    '        bond >= 75 ? ("人送雅号「" + entry.title + "」，缘起：" + entry.hint) : "缘契达 75 解锁 · 奖励 灵石×" + Math.round(200 * YlxwCharRf(p))\n'
    '      ] }),\n'
    '      e.jsxs("p", { className: "text-[11px] " + (bond >= 100 ? "text-amber-200" : "text-stone-600"), children: [\n'
    '        e.jsx("span", { className: "text-amber-400 font-bold", children: "【秘辛】" }),\n'
    '        bond >= 100 ? entry.secret : "缘契达 100 解锁 · 奖励 随机物品×3 与灵石"\n'
    '      ] })\n'
    '    ] })'
)

# ② DexPanel selBlock：邂逅线索行保留 + 两档 → 四档（死 v28 + T6 ⇒ expect=2）。
#    两副本 DexPanel 均有 rf 局部量（`var ps = YlxwCharPS(p), rf = YlxwCharRf(p);`）。
A_SEL2 = (
    'selRel\n'
    '      ? e.jsx("p", { className: "text-[11px] text-stone-300", children: selEntry.desc })\n'
    '      : e.jsx("p", { className: "text-[11px] text-stone-500", children: "\\u9082\\u9005\\u7ebf\\u7d22\\uff1a" + selEntry.hint + "\\uff08\\u6216\\u4f7f\\u7528\\u4e0a\\u65b9\\u3010\\u5bfb\\u8bbf\\u3011\\u4e3b\\u52a8\\u7ed3\\u8bc6\\uff09" }),\n'
    '    e.jsxs("p", { className: "text-[11px] " + (bond >= 50 ? "text-blue-200" : "text-stone-600"), children: [\n'
    '      e.jsx("span", { className: "text-cyan-400 font-bold", children: "\\u3010\\u5c0f\\u4f20\\u3011" }),\n'
    '      bond >= 50 ? selEntry.bio : "\\u7f18\\u5951\\u8fbe 50 \\u89e3\\u9501"\n'
    '    ] }),\n'
    '    e.jsxs("p", { className: "text-[11px] " + (bond >= 100 ? "text-amber-200" : "text-stone-600"), children: [\n'
    '      e.jsx("span", { className: "text-amber-400 font-bold", children: "\\u3010\\u79d8\\u8f9b\\u3011" }),\n'
    '      bond >= 100 ? selEntry.secret : "\\u7f18\\u5951\\u8fbe 100 \\u89e3\\u9501"\n'
    '    ] })'
)
R_SEL4 = (
    'selRel\n'
    '      ? e.jsx("p", { className: "text-[11px] " + (bond >= 25 ? "text-stone-300" : "text-stone-600"), children: bond >= 25 ? selEntry.desc : "缘契达 25 解锁 · 奖励 灵石×" + Math.round(100 * rf) })\n'
    '      : e.jsx("p", { className: "text-[11px] text-stone-500", children: "\\u9082\\u9005\\u7ebf\\u7d22\\uff1a" + selEntry.hint + "\\uff08\\u6216\\u4f7f\\u7528\\u4e0a\\u65b9\\u3010\\u5bfb\\u8bbf\\u3011\\u4e3b\\u52a8\\u7ed3\\u8bc6\\uff09" }),\n'
    '    e.jsxs("p", { className: "text-[11px] " + (bond >= 50 ? "text-blue-200" : "text-stone-600"), children: [\n'
    '      e.jsx("span", { className: "text-cyan-400 font-bold", children: "【小传】" }),\n'
    '      bond >= 50 ? selEntry.bio : "缘契达 50 解锁 · 奖励 随机物品×2"\n'
    '    ] }),\n'
    '    e.jsxs("p", { className: "text-[11px] " + (bond >= 75 ? "text-stone-300" : "text-stone-600"), children: [\n'
    '      e.jsx("span", { className: "text-pink-400 font-bold", children: "【轶事】" }),\n'
    '      bond >= 75 ? ("人送雅号「" + selEntry.title + "」，缘起：" + selEntry.hint) : "缘契达 75 解锁 · 奖励 灵石×" + Math.round(200 * rf)\n'
    '    ] }),\n'
    '    e.jsxs("p", { className: "text-[11px] " + (bond >= 100 ? "text-amber-200" : "text-stone-600"), children: [\n'
    '      e.jsx("span", { className: "text-amber-400 font-bold", children: "【秘辛】" }),\n'
    '      bond >= 100 ? selEntry.secret : "缘契达 100 解锁 · 奖励 随机物品×3 与灵石"\n'
    '    ] })'
)

# 注入/替换内容禁用模式（ask 铁律 4 项 + 本项目纯客户端口径补充）
BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-',
                'fetch(', 'localStorage', 'sessionStorage', '/yl/api',
                'Be.getState().setPlayer']


def _zh_new_blocks(zh):
    """返回经 zh() 转义的新文本块，并做纯 ASCII + 禁用模式硬断言。"""
    blocks = {
        'helper': zh(HELPER_JS),
        'unl_fn': zh(UNL_FN_JS),
        'unl_render': zh(UNL_RENDER_JS),
        'bond4': zh(R_BOND4),
        'sel4': zh(R_SEL4),
        'gain_var': zh(R_GAIN_VAR),
        'rev_var': zh(R_REV_VAR),
        'gain_kv': zh(R_GAIN_KV),
        'rev_kv': zh(R_REV_KV),
    }
    for tag, s in blocks.items():
        if not s.isascii():
            raise AssertionError('r059 新串(%s) 含非 ASCII：zh() 转义失效' % tag)
        for pat in BAN_PATTERNS:
            if pat in s:
                raise AssertionError('r059 新串(%s) 含禁用模式: %s' % (tag, pat))
    return blocks


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """把 R-059 落到 Patcher 上；返回 gates 列表。"""
    zh = ctx['zh']
    b = _zh_new_blocks(zh)

    # ① 递减函数（char 纯函数层，Entry 之前；函数声明提升，位置仅求可读）
    p.insert_before('r059-visit-gain-fn', A_HELPER, b['helper'],
                    note='R-059① YlxwCharVisitGain：结识增益按已识道友序号递减')
    # ① 结识 15~25 → 递减（死 DexPanel + T6 各 1）；任务寻访通道（renwu）同改
    p.replace('r059-gain-var', A_GAIN_VAR, b['gain_var'], expect=2,
              note='R-059① 结识增益 15~25 → YlxwCharVisitGain(已识数)（死面板+T6）')
    p.replace('r059-gain-kv', A_GAIN_KV, b['gain_kv'], expect=1,
              note='R-059① 任务提交寻访的结识增益同步递减（YlxwRnPickVisit）')
    # ① 重逢 4~9 → 2~4（三处）
    p.replace('r059-rev-var', A_REV_VAR, b['rev_var'], expect=2,
              note='R-059① 重逢增益 4~9 → 2~4（死面板+T6）')
    p.replace('r059-rev-kv', A_REV_KV, b['rev_kv'], expect=1,
              note='R-059① 任务提交寻访的重逢增益同步 2~4')

    # ② 解锁档奖励：**手动领取** chips（替换原 useEffect 自动发放）
    #    函数 + chips 构造（BondPanelT6 体内，里程碑 chips 循环之后）
    p.replace('r059-unlock-claim', A_UNL_FN, b['unl_fn'], expect=1,
              note='R-059② claimUnl + unlChips：解锁档改手动领取（照抄缘契里程碑 chips 交互，幂等落 charDex.unl）')
    #    渲染：缘契面板 return 的 questCard 之后加「缘契解锁档」标题 + chips 行
    p.replace('r059-unlock-render', A_UNL_RENDER, b['unl_render'], expect=1,
              note='R-059② 缘契面板渲染「缘契解锁档（点击领取）」chips 行')

    # ② 解锁档 UI 2→4（死/T6 × BondPanel/selBlock，各 expect=2）
    p.replace('r059-bond-4tier', A_BOND2, b['bond4'], expect=2,
              note='R-059② 缘契详情解锁档 2→4：相识25/小传50/轶事75/秘辛100，锁定态标奖励')
    p.replace('r059-sel-4tier', A_SEL2, b['sel4'], expect=2,
              note='R-059② 图鉴详情 selBlock 解锁档 2→4（同四档，邂逅线索行保留）')

    # ----------------------------------------------------------------- 门禁
    gates = [
        # ================= 本模块改动 =================
        ('R59·递减函数已注入',        'function YlxwCharVisitGain(', 1, '==', ''),
        ('R59·递减公式',              'var b = 15 - 2 * (Number(metN) || 0);', 1, '==', '第1位15/第2位13/…下限4'),
        ('R59·结识增益已递减×2',      R_GAIN_VAR, 2, '==', '死 DexPanel + T6'),
        ('R59·任务结识增益已递减',    R_GAIN_KV, 1, '==', 'YlxwRnPickVisit'),
        ('R59·重逢已压 2~4×2',        R_REV_VAR, 2, '==', '死面板 + T6'),
        ('R59·任务重逢已压 2~4',      R_REV_KV, 1, '==', ''),
        ('R59·旧结识 15~25 已清零',   '15 + Math.floor(Math.random() * 11)', 0, '==', '三处全改'),
        ('R59·旧重逢 4~9 已清零',     '4 + Math.floor(Math.random() * 6)', 0, '==', '三处全改'),
        ('R59·解锁奖励落档',          'charDex.unl', 2, '==', 'claim 注释1 + 读点1（沿用同一字段）'),
        ('R59·unl 写回',              'd59.unl = u59;', 1, '==', ''),
        ('R59·手动领取函数',          'function claimUnl(at) {', 1, '==', '与里程碑 claim(mile) 同款'),
        ('R59·领取档位表',            'var UNL59 = [25, 50, 75, 100];', 1, '==', ''),
        ('R59·领取 chips 键',         '"ylxw-charunl-t6-" + relId + "-" + at', 1, '==', '4 档同一循环'),
        ('R59·解锁档标题',            zh('缘契解锁档（点击领取）'), 1, '==', ''),
        ('R59·自动发放已移除',        'pend59', 0, '==', '★ 原 useEffect 自动发放已删除，改手动领取'),
        ('R59·幂等标记',              'if (m59[String(at)]) return prev;', 1, '==', '连点/重复渲染不重发'),
        ('R59·缘契回退守卫',          'if (cur59 < at) return prev;', 1, '==', ''),
        ('R59·奖励日志',              zh('解锁奖励已发放'), 1, '==', ''),
        ('R59·相识档标签×3',          zh('【相识】'), 3, '==', 'Bond×2 + 领取 chips 标签×1'),
        ('R59·轶事档标签×5',          zh('【轶事】'), 5, '==', 'Bond×2 + sel×2 + chips×1'),
        ('R59·四档锁定提示×16',       zh('解锁 · 奖励'), 16, '==', '4档 × 4面板副本'),
        ('R59·25档提示×4',            zh('缘契达 25 解锁'), 4, '==', 'Bond+sel 各×2'),
        ('R59·旧两档(bio)清零',       r'bond >= 50 ? entry.bio : "\u7f18\u5951\u8fbe 50 \u89e3\u9501"', 0, '==', '引号收尾=旧形态'),
        ('R59·旧两档(secret)清零',    r'bond >= 100 ? entry.secret : "\u7f18\u5951\u8fbe 100 \u89e3\u9501"', 0, '==', ''),
        ('R59·旧两档(sel.bio)清零',   r'selEntry.bio : "\u7f18\u5951\u8fbe 50 \u89e3\u9501"', 0, '==', ''),
        ('R59·旧两档(sel.secret)清零', r'selEntry.secret : "\u7f18\u5951\u8fbe 100 \u89e3\u9501"', 0, '==', ''),
        ('R59·旧desc无门槛行清零',    'children: selEntry.desc })', 0, '==', '相识档补 25 门槛'),
        ('R59·域内无网络调用',        'fetch(', 0, '==', '纯客户端（BondPanelT6..t6 尾）',
         ('function YlxwCharBondPanelT6(', '/* == end yl-t6')),
        # ================= 冻结：寻访骨架（只改增益公式，骨架不动） =================
        ('冻结·寻访单价常量',         'var YLXW_CHAR_VISIT_COST = 200;', 1, '==', ''),
        ('冻结·每日免费日期函数',     'function YlxwCharToday(', 1, '==', ''),
        ('冻结·已寻访计数×2',         zh('children: "已寻访 " + ps.visits + " 次" })'), 2, '==', 'renwu 门禁同串'),
        ('冻结·寻访目标函数',         'function YlxwCharRollTarget(', 1, '==', '稀有度权重池不动'),
        ('冻结·结识 upsert 函数',     'function YlxwCharMeet(', 1, '==', 'clamp ±100 不动'),
        ('冻结·结算助手',             'function YlxwCharApply(', 1, '==', 'visits 自增通道不动'),
        # ================= 冻结：renwu（R-034/035 面板与任务机制） =================
        ('冻结·R34 组件定义',         'function YlxwCharBoardR34(', 1, '==', ''),
        ('冻结·R35 组件定义',         'function YlxwCharTasksR35(', 1, '==', ''),
        ('冻结·R34 挂载×2',           'e.jsx(YlxwCharBoardR34, { player: p, setPlayer: setP, addLog: log }),', 2, '==', 'renwu 门禁同串'),
        ('冻结·R34 板标题',           zh('寻访任务（每日 5 条 · 提交该类该品阶以上物品即可寻访）'), 1, '==', 'renwu 门禁同串'),
        ('冻结·R34 每日5条',          'YlxwRnRollList(5, true)', 1, '==', ''),
        ('冻结·R35 每日3条',          'YlxwRnRollList(3, false)', 1, '==', ''),
        ('冻结·A4 单条重掷',          'var nt = YlxwRnRollOne(false);', 1, '==', ''),
        ('冻结·PickVisit 函数',       'function YlxwRnPickVisit(', 1, '==', '只改 gain 行'),
        ('冻结·师门任务标题',         zh('children: "师门任务" })'), 1, '==', ''),
        ('冻结·交付后重掷写入',       zh('dm0[relId] = nd;'), 1, '==', ''),
        # ================= 冻结：r058（整体刷新，本批兄弟需求） =================
        ('冻结·R58 refreshAll',       'function refreshAll() {', 1, '==', ''),
        ('冻结·R58 refAll 落档',      'refAll: day', 1, '==', ''),
        ('冻结·R58 disabled',         'disabled: refUsed,', 1, '==', ''),
        ('冻结·R58 上限提示',         zh('每日限 1 次 · 最多可做 10 条'), 1, '==', ''),
        ('冻结·R58 已刷文案',         zh('今日已整体刷新'), 1, '==', ''),
        # ================= 冻结：t6chardex（宿主面板骨架与数值定档） =================
        ('冻结·T6 DexPanelT6 定义',   'function YlxwCharDexPanelT6(', 1, '==', ''),
        ('冻结·T6 BondPanelT6 定义',  'function YlxwCharBondPanelT6(', 1, '==', ''),
        ('冻结·旧 DexPanel 定义',     'function YlxwCharDexPanel(', 1, '==', '死代码保留'),
        ('冻结·旧 BondPanel 定义',    'function YlxwCharBondPanel(', 1, '==', '死代码保留'),
        ('冻结·缘契里程碑表',         'var YLXW_CHAR_BOND_MILE = [', 1, '==', '25/50/75/100 不动（R-058 同冻结）'),
        ('冻结·缘契件数表',           'var YLXW_CHAR_DROP_N = [2, 3, 4, 5];', 1, '==', 'R-036 拍板值'),
        ('冻结·图鉴件数表',           'var YLXW_CHAR_DEX_DROP_N = [2, 2, 4, 4, 6, 8, 12];', 1, '==', ''),
        ('冻结·权重矩阵常量',         'var YLXW_CHAR_DROP_RAR = [', 1, '==', 'R1~R6 各和 100'),
        ('冻结·需求池常量',           'var YLXW_CHAR_DEMAND_POOL = {', 1, '==', ''),
        ('冻结·里程碑标题',           zh('缘契里程碑（点击领取 · 随机物品）'), 1, '==', '每 NPC 领奖入口（R-058 裁已落地）'),
        ('冻结·里程碑领取入口×2',     'onClick: function () { claim(mile); },', 2, '==', '死面板+T6 各 1'),
        ('冻结·掷件函数',             'function YlxwCharRollRow(', 1, '==', '本模块只调用不改动'),
        ('冻结·入包函数',             'function YlxwCharPushItems(', 1, '==', ''),
        ('冻结·DexV2 归一函数',       'function YlxwCharDexV2(', 1, '==', ''),
        ('冻结·求物卡标题',           'children: "' + zh('师门求物') + '"', 1, '==', ''),
        ('冻结·空态引导',             '多读需求、多交付，缘契上得快。', 1, '==', '压缩区原生 UTF-8 中文（不经 zh）——T6② 追加文案'),
        ('冻结·无名道友兜底×2',       zh('（无名道友，暂未录入图鉴；缘契里程碑仍可领取）'), 2, '==', ''),
        # ================= 冻结：char / chargift083（更远邻面） =================
        ('冻结·赠灵石好感 E=2',       'YlxwGiftCost(j&&j.favorability),E=2', 1, '==', 'T6② 定档'),
        ('冻结·旧 E=5 已清零',        ',E=5;', 0, '==', ''),
        ('冻结·YlxwGiftCost 调用×4',  'YlxwGiftCost(j&&j.favorability)', 4, '==', 'chargift 门禁同串'),
        ('冻结·赠灵石 clamp',         'favorability:Math.min(100,Math.max(-100,_.favorability+E))', 1, '==', ''),
        ('冻结·Recipe" 恒 2',         'Recipe"', 2, '==', 'T6 门禁口径'),
        ('冻结·好感 buff 公式',       'T.favorability>=80?S+=.1:T.favorability>=50&&(S+=.05);', 1, '==', 'char 门禁同串'),
        ('冻结·图鉴 24 位',           '"npc-dex-24"', 1, '==', ''),
        ('冻结·图鉴条目数 24',        'id: "npc-', 24, '==', '本模块不新增条目'),
        ('冻结·图鉴加成函数',         'function YlxwCharDexRate(', 1, '==', 'numbal 域禁碰复核'),
        ('冻结·YlxwMeta 未破坏',      'function YlxwMeta(k) {', 1, '==', ''),
        ('冻结·人物志模态标题前缀',   'title:"人物志",titleIcon:e.jsx(um,{size:18})', 1, '==', ''),
    ]
    return gates


# --------------------------------------------------------------------------- 自检（python yl_059_ext.py）

# 受影响旧门禁（无 —— 本模块不改任何相邻模块的门禁串；先验门禁重跑是最终证明）

if __name__ == '__main__':
    import io
    import os
    import subprocess
    import sys
    import tempfile
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from yl_patch import Patcher, Gates, zh  # noqa: E402

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    HERE = os.path.dirname(os.path.abspath(__file__))
    os.chdir(HERE)

    # 基线 = 「链跑到本模块之前」：本模块已接线则截到本模块前；未接线则全链
    #（r058 自检同款逻辑，见 yl_058_ext.py __main__）
    import build_v26n as B  # noqa: E402
    _saved = B.V28_MODULES
    _pos = None
    for _i, _e in enumerate(_saved):
        if getattr(_e[1], '__module__', '') == __name__:
            _pos = _i
            break
    B.V28_MODULES = _saved[:_pos] if _pos is not None else _saved
    try:
        _base_in = io.open(B.BASE, encoding='utf-8').read()
        base, prior_gates = B.build(_base_in)
        n_prior_modules = len(B.V28_MODULES)
    finally:
        B.V28_MODULES = _saved
    print('=== r059 自检：基线 = 链跑到 r059 之前（%d chars，前置 %d 模块，先验门禁 %d 条）'
          % (len(base), n_prior_modules, len(prior_gates)))

    # 锚点基线份数断言（改前）
    print('=== 改前锚点份数（链上前态） ===')
    pre = [
        ('A_GAIN_VAR', A_GAIN_VAR, 2), ('A_REV_VAR', A_REV_VAR, 2),
        ('A_GAIN_KV', A_GAIN_KV, 1), ('A_REV_KV', A_REV_KV, 1),
        ('A_HELPER', A_HELPER, 1), ('A_UNL_FN', A_UNL_FN, 1),
        ('A_UNL_RENDER', A_UNL_RENDER, 1),
        ('A_BOND2', A_BOND2, 2), ('A_SEL2', A_SEL2, 2),
    ]
    bad = 0
    for name, s, exp in pre:
        n = base.count(s)
        ok = n == exp
        bad += (not ok)
        print('  [%s] %-12s actual=%d expect=%d' % ('OK' if ok else 'FAIL', name, n, exp))
    for name, s in (('YlxwCharVisitGain', 'YlxwCharVisitGain'),
                    ('claimUnl', 'claimUnl'), ('unlChips', 'unlChips'),
                    ('UNL59', 'UNL59'), ('unlState', 'unlState'),
                    ('charDex.unl', 'charDex.unl'),
                    ('相识', zh('【相识】')), ('轶事', zh('【轶事】')),
                    ('解锁·奖励', zh('解锁 · 奖励')),
                    ('解锁档标题', zh('缘契解锁档（点击领取）'))):
        n = base.count(s)
        ok = n == 0
        bad += (not ok)
        print('  [%s] 新标识/新文案无碰撞 %-14s actual=%d expect=0' % ('OK' if ok else 'FAIL', name, n))
    if bad:
        print('  [ABORT] 链上前态与设计不符（%d 条）' % bad)
        sys.exit(2)

    # 沙盘应用（内存副本，不写盘）
    print('=== 应用补丁（内存副本，不写盘） ===')
    pt = Patcher(base, label='r059-selfcheck')
    gts = apply(pt, {'zh': zh, 'base_text': base})
    print(pt.report())

    # ★ Yl* 引用核查：新块里调用的 Yl* 函数必须全部存在于基线。
    #   node --check 只验语法不验引用；手转写漂移（拼写形近）只能在这里机械拦截。
    import re as _re
    blocks = _zh_new_blocks(zh)
    newtxt = ''.join(blocks[k] for k in ('helper', 'unl_fn', 'unl_render', 'bond4', 'sel4',
                                         'gain_var', 'rev_var', 'gain_kv', 'rev_kv'))
    ycalls = sorted(set(_re.findall(r'\b(Yl[A-Za-z]\w{2,40})\s*\(', newtxt)))
    m_def = _re.search(r'function\s+(Yl\w+)\s*\(', blocks['helper'])
    assert m_def, '递减函数定义未被识别'
    new_fns = {m_def.group(1)}
    miss = [c for c in ycalls if c not in new_fns and base.count(c) == 0]
    if miss:
        print('  [ABORT] 新代码引用了基线中不存在的 Yl* 函数: %r' % (miss,))
        sys.exit(2)
    print('=== Yl* 引用核查 PASS：调用 %r；新增 %r' % (ycalls, sorted(new_fns)))
    assert base.count('O.useEffect') >= 1, 'React 句柄 O 形态漂移'

    g = Gates(pt.text)
    for t in gts:
        name, s, expect, cmp, note = t[:5]
        g.check(name, s, expect, cmp, note, within=(t[5] if len(t) > 5 else None))
    print(g.report())
    ok = g.passed()

    # ★ 冻结证明的链级形态：把「本模块之前全部模块的先验门禁」在新文本上重跑一遍，
    #   任何一条因本模块 additions 漂移都会在此 FAIL（§22.5 下游字面门禁保护）。
    gp = Gates(pt.text)
    for t in prior_gates:
        name, s, expect, cmp, note = t[:5]
        gp.check('[先验] ' + name, s, expect, cmp, note, within=(t[5] if len(t) > 5 else None))
    print('=== 先验门禁重跑（%d 条，证明没碰任何相邻需求的面） ===' % len(prior_gates))
    print(gp.report())
    ok = ok and gp.passed()

    # node --check 产物级语法校验
    if ok:
        tmp = os.path.join(tempfile.gettempdir(), 'yl_r059_selfcheck.js')
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
