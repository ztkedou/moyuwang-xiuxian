# -*- coding: utf-8 -*-
r"""
yl_060_ext.py — R-060 人物志·师门任务：好感按「提交物品品阶」结算 + 单条刷新每日限次

需求原文（台账 R-060 逐字，需求台账_进行中.md）
--------------------------------------------------------------------------
  「自带的道友系统，任务提交的物品根据稀有度增加不同的好感度。单条刷新次数也要有限制」

侦察结论（build/assets/index-v28116-20261001.js 逐字实证，2026-10-01）
--------------------------------------------------------------------------
  道友系统 = 人物志模态（Nk）里的 renwu 注入块（yl_renwu_ext，R-034/R-035/R-036）：
    · R-034 寻访任务板 YlxwCharBoardR34：每日 5 条，提交 = 随机寻访结识（缘契+15~25），
      R-058 已加「整体刷新（每日 1 次，refAll 落档）」；提交**不加好感度**，与本需求无关。
    · R-035 师门任务 YlxwCharTasksR35（真缺口所在）：
      每位道友每日 3 条「提交【类别】X以上 ×N」，提交后 socialRelations.favorability
      += gain，而 gain = YLXW_CHAR_FAVOR_GAIN[道友稀有度]（凡缘+3/仙缘+5/天缘+8）
      —— **与提交物品的品阶完全无关**：给天缘道友交 4 个普通草药也 +8。
      任务掷点 YlxwRnRollOne 品阶只出 普通/稀有/传说（ti=floor(random*3)）。
    · 单条刷新 refreshOne(idx)：只按难度收灵石（YlxwRnRowCost，A4 口径），
      **没有次数上限** —— 灵石够就能无限重掷，把 3 条刷成全传说最优解。

本模块动作（纯客户端就地替换 ×10，INJECT_JS=''，零网络、零服务端改动）
--------------------------------------------------------------------------
  ① 好感按品阶：新增纯函数 YlxwRnFavorOf(t) = [3,5,8,12][品阶序]（普通+3/稀有+5/
     传说+8/仙品+12），submit/按钮/header 全部改读它；按道友稀有度的旧 gain 变量
     从 TasksR35 移除（BondPanelT6 死代码里的同形行保留，声明表冻结不删）。
  ② 单条刷新限次：每条每日 3 次（YLXW_RN_REF_CAP=3），计数落
     charDex.tasks[relId].ref[idx]（随 /api/save 整包落库，跨日 YlxwRnTasksOf
     重掷时自然清零）；refreshOne 前置拦截 + updater 内竞态守卫；按钮禁用 + title
     提示；submit 持久化行补 ref 透传（否则交一次任务会把计数抹掉）。

AI 代决（无人值守，详见 拍板/2026-10-01_*_R-060_*.md）
--------------------------------------------------------------------------
  1. 好感按**任务品阶**（t.minRar）而非实扣物品的最高品阶：YlxwRnTake 按「X以上」
     聚合扣包、不回报品阶，改实扣口径要动共享函数并波及 R-034，收益低风险高；
     任务本身的品阶就是"提交物品的稀有度"的既定口径（按钮/日志都标 X以上）。
  2. 好感表 [3,5,8,12]：延续既有 3/5/8 手感，传说档持平旧天缘 +8，仙品 +12 备而不用
     （掷点不出仙品，防"X以上"口径将来放开后无表可查）。
  3. 限次=每条每日 3 次：R-058 整板 1 次/日；单条 3 次 × 3 条 × 3 灵石起价，
     足以阻断"无限刷最优解"，又不把非酋玩家卡死（刷新仍要花灵石，双重闸）。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 锚点全在 renwu 注入块内，逐条实测现行 bundle count==1（probe 2026-10-01，
    __main__ 在「链跑到本模块之前」的内存基线上二次复验）；
  · 不动 renwu/r058 任何门禁串：A4 定价调用 `= YlxwRnRowCost(t, rf);`、
    `var nt = YlxwRnRollOne(false);`、`onClick: function () { refreshOne(idx); },`、
    按钮 `children: "刷新 · " + rc + " 灵石"`、`YlxwRnRollList(3/5, …)` 全部原样；
  · 新增标识符 YLXW_RN_REF_CAP / YlxwRnFavorOf / refUsedOf / refMaxed / taskRef
    全 bundle 改前 count==0（probe 2026-10-01），零碰撞；
  · 注入内容不含 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-/fetch(
    （apply 内自检；含中文一律 zh() 转义，落 bundle 纯 ASCII）；
  · 服务端零改动：srv/index_v28.ts 全文 0 处 charDex/socialRelations（probe
    2026-10-01，存档整包落库无字段白名单），ref 随 /api/save 走，**无 srv_patch_060**；
  · 不碰 build_v26n.py / localtest/ / deploy_v28/ / srv/index_v28.ts / CHANGELOG.md。

装配顺序
--------------------------------------------------------------------------
  唯一硬约束：**必须排在 renwu 之后**（锚点全在其注入块内）；
  建议紧跟 yl_058_ext（r058）之后、numbal 之前 —— 与 r058 同板块，先验门禁重跑
  可一并冻结 R-058 的整体刷新面。对既有模块门禁命中数零影响（gates 后半逐条冻结）。

导出符号（构建侧契约）
  INJECT_JS : str（''，纯就地替换）
  apply(p, ctx) -> list[(name, needle, expect, cmp, note[, within])]
"""

import re

INJECT_JS = ''          # 纯就地替换，不需要注入块

# --------------------------------------------------------------------------- 锚点
# 含中文的锚点用 raw 中文书写，apply() 内统一 ctx['zh']() 转义（与 bundle 内
# \uXXXX 同形）；纯 ASCII 锚点 zh() 为恒等。

# ① 好感表 + 限次常量：插在 YlxwRnRowCost 定义后（renwu 注入块内，count==1）
A_FUNC_ROWCOST = (
    'function YlxwRnRowCost(t, rf) {\n'
    '  var k = (typeof rf === "number" && isFinite(rf) && rf > 0) ? rf : 1;\n'
    '  return Math.max(1, Math.round(YlxwRnDiff(t) * 3 * k));\n'
    '}'
)
R_FUNC_ROWCOST = (
    A_FUNC_ROWCOST + '\n'
    '/* R-060：师门任务好感改按「提交物品品阶」结算（普通+3/稀有+5/传说+8/仙品+12），\n'
    '   不再按道友稀有度；单条刷新每条每日限 3 次（charDex.tasks[relId].ref 持久化，跨日自然清零）。 */\n'
    'var YLXW_RN_REF_CAP = 3;\n'
    'function YlxwRnFavorOf(t) {\n'
    '  var F = [3, 5, 8, 12];\n'
    '  return F[YlxwRnTierIdx(t && t.minRar)] || 3;\n'
    '}'
)

# ② gain 变量 → 每条刷新计数读取（任务档形参 tk 带 ref）
A_GAIN_VAR = (
    '  var day = tk ? tk.day : "", list = (tk && tk.list) || [];\n'
    '  var gain = YLXW_CHAR_FAVOR_GAIN[rar] || 3;'
)
R_GAIN_VAR = (
    '  var day = tk ? tk.day : "", list = (tk && tk.list) || [];\n'
    '  var taskRef = (tk && tk.ref) || {};\n'
    '  function refUsedOf(idx) { return Number(taskRef[idx]) || 0; }\n'
    '  function refMaxed(idx) { return refUsedOf(idx) >= YLXW_RN_REF_CAP; }'
)

# ③ submit：好感按品阶取值（旧 var g = gain）
A_SUBMIT_G = '    var g = gain, key = t.type, minRar = t.minRar, need = t.need;'
R_SUBMIT_G = '    var g = YlxwRnFavorOf(t), key = t.type, minRar = t.minRar, need = t.need;'

# ④ submit 持久化行：透传 ref（否则提交一次会把该道友的刷新计数抹掉）
A_SUBMIT_PERSIST = (
    '      m0[relId] = { day: cur.day, list: (cur.list || list).map(function (x, j) {\n'
    '        return j === idx ? Object.assign({}, x, { done: true }) : x;\n'
    '      }) };'
)
R_SUBMIT_PERSIST = (
    '      m0[relId] = { day: cur.day, ref: cur.ref || {}, list: (cur.list || list).map(function (x, j) {\n'
    '        return j === idx ? Object.assign({}, x, { done: true }) : x;\n'
    '      }) };'
)

# ⑤ 提交按钮：好感数字按该条品阶显示
A_BTN_GAIN = '            children: t.done ? "已完成" : (ok ? "提交（好感 +" + gain + "）" : "材料不足")'
R_BTN_GAIN = '            children: t.done ? "已完成" : (ok ? "提交（好感 +" + YlxwRnFavorOf(t) + "）" : "材料不足")'

# ⑥ 板头：品阶好感口径 + 限次提示（旧「交付得好感 +N」按道友稀有度，已不实）
A_HDR_GAIN = '      e.jsxs("span", { className: "text-[10px] text-stone-500", children: ["每日 3 条 · 交付得好感 +", gain, " · 可单条刷新"] })'
R_HDR_GAIN = '      e.jsxs("span", { className: "text-[10px] text-stone-500", children: ["每日 3 条 · 好感按提交品阶：普通+3/稀有+5/传说+8/仙品+12 · 单条刷新每日限 " + YLXW_RN_REF_CAP + " 次"] })'

# ⑦ refreshOne 整体：前置拦截 + updater 竞态守卫 + 计数持久化 + 日志带计数
A_REFRESH_ONE = (
    '  function refreshOne(idx) {\n'
    '    if (!p) return;\n'
    '    var t = list[idx];\n'
    '    if (!t) return;\n'
    '    var c = YlxwRnRowCost(t, rf);\n'
    '    if ((Number(p.spiritStones) || 0) < c) { setNotice("灵石不足，刷新该条需 " + c + " 灵石。"); return; }\n'
    '    var nt = YlxwRnRollOne(false);\n'
    '    setP(function (prev) {\n'
    '      if ((Number(prev.spiritStones) || 0) < c) return prev;\n'
    '      var d0 = YlxwCharDexV2(prev.charDex);\n'
    '      var m0 = Object.assign({}, d0.tasks || {});\n'
    '      var cur = m0[relId] || { day: day, list: list };\n'
    '      var nl = (cur.list || list).map(function (x, j) { return j === idx ? nt : x; });\n'
    '      m0[relId] = { day: cur.day, list: nl };\n'
    '      d0.tasks = m0;\n'
    '      return Object.assign({}, prev, { spiritStones: (Number(prev.spiritStones) || 0) - c, charDex: d0 });\n'
    '    });\n'
    '    log("【人物志·刷新】花费 " + c + " 灵石，为" + rel.name + "刷新了一条师门任务。", "normal");\n'
    '    setNotice("已刷新该条任务（-" + c + " 灵石）。");\n'
    '  }'
)
R_REFRESH_ONE = (
    '  function refreshOne(idx) {\n'
    '    if (!p) return;\n'
    '    var t = list[idx];\n'
    '    if (!t) return;\n'
    '    if (refMaxed(idx)) { setNotice("该条今日已刷新 " + YLXW_RN_REF_CAP + " 次，明天再来。"); return; }\n'
    '    var c = YlxwRnRowCost(t, rf);\n'
    '    if ((Number(p.spiritStones) || 0) < c) { setNotice("灵石不足，刷新该条需 " + c + " 灵石。"); return; }\n'
    '    var nt = YlxwRnRollOne(false);\n'
    '    setP(function (prev) {\n'
    '      if ((Number(prev.spiritStones) || 0) < c) return prev;\n'
    '      var d0 = YlxwCharDexV2(prev.charDex);\n'
    '      var m0 = Object.assign({}, d0.tasks || {});\n'
    '      var cur = m0[relId] || { day: day, list: list };\n'
    '      var r0 = Object.assign({}, cur.ref || {});\n'
    '      if ((Number(r0[idx]) || 0) >= YLXW_RN_REF_CAP) return prev; /* R-060 双击竞态守卫 */\n'
    '      r0[idx] = (Number(r0[idx]) || 0) + 1;\n'
    '      var nl = (cur.list || list).map(function (x, j) { return j === idx ? nt : x; });\n'
    '      m0[relId] = { day: cur.day, list: nl, ref: r0 };\n'
    '      d0.tasks = m0;\n'
    '      return Object.assign({}, prev, { spiritStones: (Number(prev.spiritStones) || 0) - c, charDex: d0 });\n'
    '    });\n'
    '    log("【人物志·刷新】花费 " + c + " 灵石，为" + rel.name + "刷新了一条师门任务（今日该条已刷 " + (refUsedOf(idx) + 1) + "/" + YLXW_RN_REF_CAP + " 次）。", "normal");\n'
    '    setNotice("已刷新该条任务（-" + c + " 灵石）。");\n'
    '  }'
)

# ⑧ 行内 canRef：灵石够 且 未达每日限次
A_CANREF = (
    '      var have = YlxwRnCount(p, t.type, t.minRar), ok = have >= t.need;\n'
    '      var rc = YlxwRnRowCost(t, rf), canRef = stonesNow >= rc;'
)
R_CANREF = (
    '      var have = YlxwRnCount(p, t.type, t.minRar), ok = have >= t.need;\n'
    '      var rc = YlxwRnRowCost(t, rf), canRef = stonesNow >= rc && !refMaxed(idx);'
)

# ⑨ 刷新按钮：title 提示剩余次数（文案本体冻结不动，renwu/r058 门禁同串）
A_BTN_DIS = (
    '            disabled: !canRef,\n'
    '            onClick: function () { refreshOne(idx); },'
)
R_BTN_DIS = (
    '            disabled: !canRef,\n'
    '            title: refMaxed(idx) ? "该条今日已刷新 " + YLXW_RN_REF_CAP + " 次（明日恢复）" : "重掷该条任务",\n'
    '            onClick: function () { refreshOne(idx); },'
)

# ⑩ 脚注：补限次说明
A_FOOTER = '    e.jsx("div", { className: "text-[10px] text-stone-500 pt-0.5", children: "每条可单独刷新（按钮上已标注所需灵石）；任务越难，刷新越贵" }),'
R_FOOTER = '    e.jsx("div", { className: "text-[10px] text-stone-500 pt-0.5", children: "每条可单独刷新（按钮上已标注所需灵石）；任务越难，刷新越贵；每条刷新每日限 " + YLXW_RN_REF_CAP + " 次" }),'

# 注入内容禁用模式（与 V28_BAN_PATTERNS + 本项目纯客户端口径一致）
BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-',
                'fetch(', 'localStorage', 'sessionStorage', '/yl/api',
                'Be.getState().setPlayer']

# TasksR35 域窗口（域内门禁用）
DOM_TASKS35 = ('function YlxwCharTasksR35(', '/* == end yl-renwu')
DOM_RENWU = ('/* ===== yl-renwu ', 'function YlxwMeta(k) {')


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """把 R-060 落到 Patcher 上；返回 gates 列表。"""
    zh = ctx['zh']

    pairs = [
        ('r060-favor-fn', A_FUNC_ROWCOST, R_FUNC_ROWCOST),
        ('r060-gain-to-ref', A_GAIN_VAR, R_GAIN_VAR),
        ('r060-submit-g', A_SUBMIT_G, R_SUBMIT_G),
        ('r060-submit-persist', A_SUBMIT_PERSIST, R_SUBMIT_PERSIST),
        ('r060-btn-gain', A_BTN_GAIN, R_BTN_GAIN),
        ('r060-header', A_HDR_GAIN, R_HDR_GAIN),
        ('r060-refresh-one', A_REFRESH_ONE, R_REFRESH_ONE),
        ('r060-canref', A_CANREF, R_CANREF),
        ('r060-btn-title', A_BTN_DIS, R_BTN_DIS),
        ('r060-footer', A_FOOTER, R_FOOTER),
    ]
    for i, (name, old, new) in enumerate(pairs):
        o = zh(old)
        n = zh(new)
        # 新串硬断言：落 bundle 形态纯 ASCII + 无禁用模式（旧串里本来就有 zh 转义中文，同样过一遍）
        for tag, s in (('old', o), ('new', n)):
            if not s.isascii():
                raise AssertionError('r060 %s %s 串含非 ASCII：zh() 转义失效' % (name, tag))
            if tag == 'new':
                for pat in BAN_PATTERNS:
                    if pat in s:
                        raise AssertionError('r060 %s 新串含禁用模式: %s' % (name, pat))
        notes = [
            'R-060① 品阶好感函数+限次常量（插 YlxwRnRowCost 后）',
            'R-060② gain 变量 → 每条刷新计数读取（taskRef/refUsedOf/refMaxed）',
            'R-060③ submit 好感按该条品阶取值',
            'R-060④ submit 持久化透传 ref（防提交抹计数）',
            'R-060⑤ 提交按钮好感数字按品阶',
            'R-060⑥ 板头改「好感按提交品阶 + 单条刷新每日限 3 次」',
            'R-060⑦ refreshOne：前置拦截 + 竞态守卫 + ref 落档 + 日志带计数',
            'R-060⑧ 行内 canRef 接 refMaxed',
            'R-060⑨ 刷新按钮 title 提示（文案本体不动）',
            'R-060⑩ 脚注补限次说明',
        ]
        p.replace(name, o, n, expect=1, note=notes[i])

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本模块改动 =================
        ('R60·品阶好感函数',        'function YlxwRnFavorOf(', 1, '==', ''),
        ('R60·品阶好感表',          '[3, 5, 8, 12]', 1, '==', '普通+3/稀有+5/传说+8/仙品+12'),
        ('R60·刷新上限常量',        'var YLXW_RN_REF_CAP = 3;', 1, '==', '每条每日 3 次'),
        ('R60·submit 按品阶取好感', 'var g = YlxwRnFavorOf(t), key = t.type', 1, '==', ''),
        ('R60·按钮品阶好感',        zh('提交（好感 +" + YlxwRnFavorOf(t) + "）'), 1, '==', ''),
        ('R60·板头品阶口径',        zh('好感按提交品阶：普通+3/稀有+5/传说+8/仙品+12'), 1, '==', '需求主诉求文案'),
        ('R60·板头限次提示',        zh('单条刷新每日限 " + YLXW_RN_REF_CAP + " 次'), 1, '==', ''),
        ('R60·脚注限次提示',        zh('每条刷新每日限 " + YLXW_RN_REF_CAP + " 次'), 1, '==', ''),
        ('R60·上限前置拦截',        zh('该条今日已刷新 " + YLXW_RN_REF_CAP + " 次，明天再来。'), 1, '==', ''),
        ('R60·竞态守卫',            'if ((Number(r0[idx]) || 0) >= YLXW_RN_REF_CAP) return prev;', 1, '==', 'updater 内复核，双击不漂移'),
        ('R60·计数落档(refresh)',   'm0[relId] = { day: cur.day, list: nl, ref: r0 };', 1, '==', 'charDex.tasks[relId].ref'),
        ('R60·计数透传(submit)',    'ref: cur.ref || {}', 1, '==', '提交不抹计数'),
        ('R60·canRef 接限次',       'canRef = stonesNow >= rc && !refMaxed(idx);', 1, '==', '到限即禁用'),
        ('R60·按钮 title 提示',     zh('次（明日恢复）'), 1, '==', ''),
        ('R60·重掷 title 提示',     zh('重掷该条任务'), 1, '==', ''),
        ('R60·计数读取函数',        'function refUsedOf(idx) { return Number(taskRef[idx]) || 0; }', 1, '==', ''),
        ('R60·限次判定函数',        'function refMaxed(idx) { return refUsedOf(idx) >= YLXW_RN_REF_CAP; }', 1, '==', ''),
        ('R60·日志带计数',          zh('（今日该条已刷 " + (refUsedOf(idx) + 1) + "/" + YLXW_RN_REF_CAP + " 次）'), 1, '==', ''),
        ('R60·旧按NPC好感已清除',   'var gain = YLXW_CHAR_FAVOR_GAIN', 0, '==', 'TasksR35 域内', ) + (DOM_TASKS35,),
        ('R60·旧 gain 传参已清除',  'var g = gain,', 0, '==', 'TasksR35 域内') + (DOM_TASKS35,),
        ('R60·旧 gain 插值已清除',  '"+ gain + "', 0, '==', 'TasksR35 域内（按钮/板头）') + (DOM_TASKS35,),
        ('R60·全局旧 gain 仅剩死代码', 'var gain = YLXW_CHAR_FAVOR_GAIN[rar] || 3;', 1, '==', 'BondPanelT6 死代码保留 1 处'),
        ('R60·域内无网络调用',      'fetch(', 0, '==', '纯客户端', ) + (DOM_RENWU,),
        # ================= 冻结：renwu（宿主）一字未动 =================
        ('冻结·R35 组件定义',       'function YlxwCharTasksR35(', 1, '==', 'renwu 门禁同串'),
        ('冻结·R34 组件定义',       'function YlxwCharBoardR34(', 1, '==', 'renwu 门禁同串'),
        ('冻结·R34 板标题未动',     zh('寻访任务（每日 5 条 · 提交该类该品阶以上物品即可寻访）'), 1, '==', 'renwu/r058 门禁同串'),
        ('冻结·R34 挂载×2 未动',    'e.jsx(YlxwCharBoardR34, { player: p, setPlayer: setP, addLog: log }),', 2, '==', 'renwu 门禁同串'),
        ('冻结·R35 挂载未动',       'e.jsx(YlxwCharTasksR35, { rel: rel, player: p, setPlayer: setP, addLog: log, rarity: rar })', 1, '==', 'renwu 门禁同串'),
        ('冻结·师门任务标题未动',   zh('children: "师门任务" }),'), 1, '==', 'renwu 门禁同串'),
        ('冻结·A4 定价调用未动',    '= YlxwRnRowCost(t, rf);', 1, '==', 'renwu 门禁同串'),
        ('冻结·A4 单条重掷未动',    'var nt = YlxwRnRollOne(false);', 1, '==', 'renwu/r058 门禁同串'),
        ('冻结·A4 每条按钮未动',    'onClick: function () { refreshOne(idx); },', 1, '==', 'renwu/r058 门禁同串'),
        ('冻结·A4 价标未动',        zh('children: "刷新 · " + rc + " 灵石"'), 1, '==', 'renwu/r058 门禁同串'),
        ('冻结·R35 每日3条未动',    'YlxwRnRollList(3, false)', 1, '==', 'renwu 门禁同串'),
        ('冻结·R34 每日5条未动',    'YlxwRnRollList(5, true)', 1, '==', 'renwu 门禁同串'),
        ('冻结·品阶表未动',         'var YLXW_RN_TIERS = [', 1, '==', 'renwu 门禁同串'),
        ('冻结·品阶序函数未动',     'function YlxwRnTierIdx(', 1, '==', '本模块复用，不改其体'),
        ('冻结·定价函数定义未动',   'function YlxwRnRowCost(', 1, '==', 'renwu 门禁同串'),
        ('冻结·好感加值表声明未动', 'var YLXW_CHAR_FAVOR_GAIN = {', 1, '==', 't6 门禁同串（死代码引用保留）'),
        ('冻结·注入块结束标记',     '/* == end yl-renwu', 1, '==', 'renwu 门禁同串'),
        # ================= 冻结：r058（近邻）一字未动 =================
        ('冻结·R58 refreshAll',     'function refreshAll() {', 1, '==', ''),
        ('冻结·R58 按钮挂载',       'onClick: function () { refreshAll(); },', 1, '==', ''),
        ('冻结·R58 refAll 落档',    'refAll: day', 1, '==', ''),
        ('冻结·R58 上限提示',       zh('每日限 1 次 · 最多可做 10 条'), 1, '==', ''),
        # ================= 冻结：t6 / chargift（更远邻） =================
        ('冻结·T6 图鉴面板定义',    'function YlxwCharDexPanelT6(', 1, '==', ''),
        ('冻结·T6 缘契面板定义',    'function YlxwCharBondPanelT6(', 1, '==', ''),
        ('冻结·GiftCost 调用恒4',   'YlxwGiftCost(j&&j.favorability)', 4, '==', '停用而非删除 → 计数不变'),
    ]
    return gates


# --------------------------------------------------------------------------- 自检

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
    # （r058 自检同款逻辑，见 yl_058_ext.py __main__）
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
    print('=== r060 自检：基线 = 链跑到 r060 之前（%d chars，前置 %d 模块，先验门禁 %d 条）'
          % (len(base), n_prior_modules, len(prior_gates)))

    print('=== 改前锚点份数（链上前态） ===')
    pre = [
        ('A_FUNC_ROWCOST', A_FUNC_ROWCOST, 1),
        ('A_GAIN_VAR', A_GAIN_VAR, 1),
        ('A_SUBMIT_G', A_SUBMIT_G, 1),
        ('A_SUBMIT_PERSIST', A_SUBMIT_PERSIST, 1),
        ('A_BTN_GAIN', A_BTN_GAIN, 1),
        ('A_HDR_GAIN', A_HDR_GAIN, 1),
        ('A_REFRESH_ONE', A_REFRESH_ONE, 1),
        ('A_CANREF', A_CANREF, 1),
        ('A_BTN_DIS', A_BTN_DIS, 1),
        ('A_FOOTER', A_FOOTER, 1),
    ]
    bad = 0
    for name, s, exp in pre:
        n = base.count(zh(s))
        ok = n == exp
        bad += (not ok)
        print('  [%s] %-18s actual=%d expect=%d' % ('OK' if ok else 'FAIL', name, n, exp))
    for name, s in (('YLXW_RN_REF_CAP', 'YLXW_RN_REF_CAP'), ('YlxwRnFavorOf', 'YlxwRnFavorOf'),
                    ('refUsedOf', 'refUsedOf'), ('refMaxed', 'refMaxed'), ('taskRef', 'taskRef')):
        n = base.count(s)
        ok = n == 0
        bad += (not ok)
        print('  [%s] 新标识符无碰撞 %-16s actual=%d expect=0' % ('OK' if ok else 'FAIL', name, n))
    if bad:
        print('  [ABORT] 链上前态与设计不符（%d 条）' % bad)
        sys.exit(2)

    print('=== 应用补丁（内存副本，不写盘）===')
    pt = Patcher(base, label='r060-selfcheck')
    gts = apply(pt, {'zh': zh, 'base_text': base})
    print(pt.report())

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
        tmp = os.path.join(tempfile.gettempdir(), 'yl_r060_selfcheck.js')
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
