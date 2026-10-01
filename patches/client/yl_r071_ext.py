# -*- coding: utf-8 -*-
r"""
yl_r071_ext.py — 妖灵「收养 / 归位 / 放生」一条流程线（R-071 + R-072 + R-075）

需求（用户原话）
--------------------------------------------------------------------------
  R-071：「收养灵宠需要花灵石。随机品种和品阶。」
  R-072：「仙务·妖灵 归位后要再可以重新收养，现在的状态是归位后左边变成已归位，
          数值显示内容却没变，直接妖灵系统就没用了。」（bug + 功能缺失）
  R-075：「仙务·妖灵 归位也需要花灵石，增加一个放生的功能，让玩家可以重新花灵石收养新的妖灵。」

★ 打中的是「仙务·妖灵」（服务端 `pets` 表 / 面板 `YlxwTPet`，`GET /api/pet` 的 `t.pet`），
  **不是**客户端 `player.pets` 那套「灵宠」（R-017/pet089 地盘）。三条是同一套流程，故合一个模块。

R-072 根因（客户端侧，逐条给证据）
--------------------------------------------------------------------------
  · 服务端 `GET /api/pet` 在 `merged=1`（已归位）时**仍返回 `pet`**（`petView` 带 `merged` 字段，
    `spirit` 才置 null）⇒ 客户端 `m = t && t.pet` 仍为真。
  · 于是 `YlxwTPet` 里 `m ? [YlxwR18Card, YlxwR18Panel] : [收养行]` 走**前者**：
    妖灵卡继续显示旧 `品阶/等级/喂食度/羁绊/资质`（只有 PP/主人加成变「—」），
    培养面板里归位按钮文字变「已归位」——即用户看到的「左边变成已归位，数值却没变」。
  · 且收养行只在 `!m` 时渲染 ⇒ 归位后**永远看不到「收养」按钮**，妖灵系统成一次性。
  （服务端收养端点 `if (existed) 409` 另有一道锁，见 srv_patch_r071.py，两端都要放行才能重收养。）

本模块动作（三处就地替换 + 一个纯展示注入块，零新增网络调用）
--------------------------------------------------------------------------
  C0  注入模块级助手 `YlxwR18AdoptBtn` / `YlxwR18AdoptRow` / `YlxwR18AwayReleaseRow`
      （顶层同作用域，函数声明提升 ⇒ YlxwTPet / YlxwR18MiscRow 可引用）。
  C1  收养行：`e.jsx(YlxwRow,{children:e.jsx(YlxwBtn,{...f("adopt",...)})})`
      → `YlxwR18AdoptRow(t, f, u)`：显示消耗（`t.consts.adoptCost`），归位后补一行「已归位」提示。
  C2  `m = t && t.pet;` → `m = (t && t.pet && YlxwNum(t.pet.merged) > 0) ? null : (t && t.pet);`
      ⇒ 归位后 `m` 视为「无妖灵」：妖灵卡 + 培养面板 + 旧「喂养/嬉戏」快捷行 + 妖灵作用块
      **一起隐藏**（这几块都是 `m && ...`），回到「收养」态。数值不再残留。
  C3  归位按钮行 → `YlxwR18AwayReleaseRow(t, m, f, u)`：归位按钮显示消耗（`t.consts.awayCost`），
      并**新增「放生」按钮**（`POST /pet/spirit/release`）。

★ 归位 vs 放生 的语义区别（本模块与 srv_patch_r071.py 共同定义）
--------------------------------------------------------------------------
  · 归位 = **转化**：妖灵 → 可出战灵宠（`YlxwMergeSpiritAway` 继承属性），**有产出、花灵石**（30000）。
  · 放生 = **舍弃**：直接丢弃当前妖灵，**无产出、免费**（0），只为腾出妖灵槽位重抽。
  · 两者都释放槽位、都可重新收养。凡品/没养过的妖灵用「放生」腾位最划算；
    养成的妖灵才值得花 30000 归位换灵宠。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 不改 r018 / r018b / r045 任何门禁串：
      `function YlxwR18Card(t, m) {` / `function YlxwR18Panel(t, m, f, u) {` /
      `function YlxwR18MiscRow(t, m, f, u) {` / `function YlxwTPet() {` / `YlxwUseList("/pet")` /
      `m ? e.jsxs(e.Fragment, { children: [YlxwR18Card(t, m), YlxwR18Panel(t, m, f, u)] })` /
      `YlxwR18MiscRow(t, m, f, u), YlxwR18bRuneRow(t, m, f, u),` /
      `f("r18away", "/pet/spirit/away"` / `YlxwMergeSpiritAway(m); YlxwDirty();`
      全部原样保留（本模块只**搬动**归位按钮到注入块，字符串计数仍为 1）。
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/auth_token/X-YL-）。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py / localtest/* / srv/index_v28.ts / deploy_v28/*。
  · ★ 接线顺序：必须排在 r018 / r018b / r045 / pet089 / fun086 / v2810e **之后**
    （锚点是它们的产物；建议紧接 r048 之后、r050 之前）。服务端配套 = SRV_CHAIN 的 srv_patch_r071.py。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R071: 妖灵 收养 / 归位 / 放生（R-071 + R-072 + R-075）=====
   服务端权威：/pet/adopt 扣费 + 随机品种品阶；/pet/spirit/away 扣费；/pet/spirit/release 放生。
   本块只做展示与调端点；数值/扣费一律以服务端回显为准。 */

/* ---------- R-071 收养按钮：显示消耗 + 把抽到的品种/品阶 toast 出来 ---------- */
function YlxwR18AdoptBtn(t, f, u) {
  var cost = YlxwNum(t && t.consts && t.consts.adoptCost);
  return e.jsx(YlxwBtn, {
    disabled: !!u,
    onClick: function () {
      f("adopt", "/pet/adopt", {}, "已收养妖灵").then(function (res) {
        if (res && res.pet) { try { ia("已收养「" + res.pet.name + "」（" + res.pet.rarity + "品）"); } catch (err) {} }
      });
    },
    children: "收养妖灵" + (cost ? ("（消耗 " + cost + " 灵石 · 随机品种品阶）") : ""),
  });
}

/* ---------- R-072 收养行：归位后（merged=1）补一行提示，其余同收养 ---------- */
function YlxwR18AdoptRow(t, f, u) {
  var p = t && t.pet;
  var merged = !!(p && YlxwNum(p.merged) > 0);
  return e.jsxs(YlxwRow, { children: [
    merged ? e.jsx("div", { className: "text-[11px] text-stone-500 mb-1",
      children: "上一只「" + String(p.name) + "」已归位为灵宠，可重新花灵石收养新的妖灵。" }) : null,
    YlxwR18AdoptBtn(t, f, u),
  ] });
}

/* ---------- R-075 归位 + 放生 行：归位花灵石转灵宠；放生免费丢弃 ---------- */
function YlxwR18AwayReleaseRow(t, m, f, u) {
  var c = (t && t.consts) || {};
  var awayCost = YlxwNum(c.awayCost) || 30000;
  var merged = YlxwNum(m.merged) > 0;
  return e.jsxs(e.Fragment, { children: [
    e.jsx("span", { className: "text-xs text-stone-400 ml-2", children: "归位" }),
    e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u || merged,
      onClick: function () {
        f("r18away", "/pet/spirit/away", {}, "妖灵已归位").then(function (res) {
          if (res) { try { YlxwMergeSpiritAway(m); YlxwDirty(); } catch (err) {} }
        });
      },
      children: merged ? "已归位" : ("归位为灵宠（" + awayCost + " 灵石）") }),
    e.jsx("span", { className: "text-xs text-stone-400 ml-2", children: "放生" }),
    e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u || merged,
      onClick: function () {
        f("r18release", "/pet/spirit/release", {}, "已放生妖灵").then(function (res) {
          if (res) { try { YlxwDirty(); } catch (err) {} }
        });
      },
      children: "放生妖灵（放弃当前妖灵 · 免费 · 可重新收养）" }),
  ] });
}
'''

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# C1 收养行（fun086 F5a 注入块内；全仓唯一）
ADOPT_OLD = ('e.jsx(YlxwRow, { children: e.jsx(YlxwBtn, { disabled: !!u, onClick: function() '
             '{ f("adopt", "/pet/adopt", {}, "\\u5df2\\u6536\\u517b\\u5996\\u7075"); }, '
             'children: "\\u6536\\u517b\\u5996\\u7075" }) })')
ADOPT_NEW = 'YlxwR18AdoptRow(t, f, u)'

# C2 妖灵「有/无」判定（fun086 F5a 注入块内；全仓唯一）
M_OLD = 'm = t && t.pet;'
M_NEW = 'm = (t && t.pet && YlxwNum(t.pet.merged) > 0) ? null : (t && t.pet);'

# C3 归位按钮行（r018 注入块 YlxwR18MiscRow 内；全仓唯一，多行锚点）
AWAY_OLD = (
    '    e.jsx("span", { className: "text-xs text-stone-400 ml-2", children: "\\u5f52\\u4f4d" }),\n'
    '    e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u || merged,\n'
    '      onClick: function () {\n'
    '        f("r18away", "/pet/spirit/away", {}, "\\u5996\\u7075\\u5df2\\u5f52\\u4f4d").then(function (res) {\n'
    '          if (res) { try { YlxwMergeSpiritAway(m); YlxwDirty(); } catch (err) {} }\n'
    '        });\n'
    '      },\n'
    '      children: merged ? "\\u5df2\\u5f52\\u4f4d" : "\\u5f52\\u4f4d\\u4e3a\\u7075\\u5ba0\\uff08\\u4e00\\u6b21\\u6027\\uff09" }),'
)
AWAY_NEW = '    YlxwR18AwayReleaseRow(t, m, f, u),'

# 注入锚：`YlxwTPet` 定义之前（r018/r018b/v2810e/pet089 同锚；本模块最后插 ⇒ 落其块之后）
ANCHOR_TPET = 'function YlxwTPet() {'

# 旧归位按钮文案（应清零）
OLD_AWAY_TEXT = '\\u5f52\\u4f4d\\u4e3a\\u7075\\u5ba0\\uff08\\u4e00\\u6b21\\u6027\\uff09'

EDITS = [
    ('C1 收养行改走助手', ADOPT_OLD, ADOPT_NEW),
    ('C2 归位后 m 视为无妖灵', M_OLD, M_NEW),
    ('C3 归位行改走 归位+放生', AWAY_OLD, AWAY_NEW),
]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 fun086 / pet089 / v2810e / r018 / r018b / r045）；
    ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r071 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 自检：锚点/替换串的手滑护栏（防写成空串或漏改）
    if 'f("adopt", "/pet/adopt"' not in ADOPT_OLD or 'YlxwR18AdoptRow(t, f, u)' != ADOPT_NEW:
        raise AssertionError('r071 C1 锚点/替换串异常')
    if 'm = t && t.pet;' != M_OLD or 'YlxwNum(t.pet.merged) > 0' not in M_NEW:
        raise AssertionError('r071 C2 锚点/替换串异常')
    if 'f("r18away", "/pet/spirit/away"' not in AWAY_OLD or 'YlxwR18AwayReleaseRow(t, m, f, u)' not in AWAY_NEW:
        raise AssertionError('r071 C3 锚点/替换串异常')

    # C0) 模块级助手（顶层同作用域；函数声明提升 ⇒ 面板可引用）
    p.insert_before('r071-helpers', ANCHOR_TPET, blk + '\n',
                    expect=1, note='注入 YlxwR18AdoptBtn / YlxwR18AdoptRow / YlxwR18AwayReleaseRow')

    # C1-C3) 就地替换
    for name, old, new in EDITS:
        p.replace(name, old, new, expect=1)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 注入块 =================
        ('R71·收养按钮助手已注入',   'function YlxwR18AdoptBtn(t, f, u) {', 1, '==', ''),
        ('R71·收养行助手已注入',     'function YlxwR18AdoptRow(t, f, u) {', 1, '==', ''),
        ('R71·归位放生行已注入',     'function YlxwR18AwayReleaseRow(t, m, f, u) {', 1, '==', ''),
        ('R71·收养显示消耗',         't && t.consts && t.consts.adoptCost', 1, '==', '服务端回显 consts.adoptCost'),
        ('R71·归位显示消耗',         'YlxwNum(c.awayCost) || 30000', 1, '==', '服务端回显 consts.awayCost'),
        ('R71·收养 toast 带品种品阶', 'res.pet.rarity + "', 1, '==', '抽到的 品阶 即时可见'),
        # ================= 端点 =================
        ('R71·收养端点',             'f("adopt", "/pet/adopt", {}, "\\u5df2\\u6536\\u517b\\u5996\\u7075")', 1, '==', ''),
        ('R71·放生端点',             'f("r18release", "/pet/spirit/release", {}, "\\u5df2\\u653e\\u751f\\u5996\\u7075")', 1, '==', ''),
        # ================= 挂载点 =================
        ('R71·收养行已挂到面板',     ': YlxwR18AdoptRow(t, f, u),', 1, '==', '替换原收养行挂载点'),
        ('R71·归位放生行已挂到点化行', 'YlxwR18AwayReleaseRow(t, m, f, u),', 1, '==', ''),
        ('R71·归位后 m 视为无妖灵',  'm = (t && t.pet && YlxwNum(t.pet.merged) > 0) ? null : (t && t.pet);', 1, '==', 'R-072 根因修复'),
        ('R71·旧 m 定义已清零',      'm = t && t.pet;', 0, '==', '旧形态'),
        ('R71·旧归位文案已清零',     OLD_AWAY_TEXT, 0, '==', '旧「归位为灵宠（一次性）」'),
        # ================= 冻结：上游门禁面（本环只搬动，不改语义）=================
        ('冻结·r018/r045 归位端点未动', 'f("r18away", "/pet/spirit/away"', 1, '==', '搬到注入块后仍恰 1 处'),
        ('冻结·r018/r045 归位客户端桥未动', 'YlxwMergeSpiritAway(m); YlxwDirty();', 1, '==', ''),
        ('冻结·r018 妖灵卡挂载未动',
         'm ? e.jsxs(e.Fragment, { children: [YlxwR18Card(t, m), YlxwR18Panel(t, m, f, u)] })', 1, '==', ''),
        ('冻结·r018b 换纹行挂载未动',
         'YlxwR18MiscRow(t, m, f, u), YlxwR18bRuneRow(t, m, f, u),', 1, '==', ''),
        ('冻结·r018 点化行签名未动', 'function YlxwR18MiscRow(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 妖灵卡签名未动', 'function YlxwR18Card(t, m) {', 1, '==', ''),
        ('冻结·r018 培养面板签名未动', 'function YlxwR18Panel(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 点化端点未动',   'f("r18apt", "/pet/aptitude"', 1, '==', ''),
        ('冻结·v2810e YlxwTPet 未整体重写', 'function YlxwTPet() {', 1, '==', ''),
        ('冻结·v2810e 嬉戏按钮未动', 'f("play", "/pet/play", {}, "\\u5b09\\u620f\\u6210\\u529f");', 1, '==', ''),
        ('冻结·v2810e 作用块挂载未动',
         'children: "\\u5b09\\u620f" })] }), m && e.jsx(YlxwTSpiritUse, { pet: m }),', 1, '==', ''),
        ('冻结·fun086 /pet 端点未改', 'YlxwUseList("/pet")', 1, '==', ''),
        ('冻结·fun086 折叠 state 未动',
         'var _pl = O.useState(!1), _logOpen = _pl[0], _setLogOpen = _pl[1];', 1, '==', ''),
        ('冻结·r045 归位属性桥未动', 'YlxwPetSpeciesStats(pick.species, 1, 0)', 1, '==', ''),
        ('冻结·pet089 归位桥未动',   'function YlxwMergeSpiritAway(sp) {', 1, '==', ''),
        ('冻结·战斗结算核心未动',    'YlxwBattleBonus(t),YlxwDOD=', 1, '==', ''),
        ('冻结·R018 未新增仙途任务', 'QUEST_DEFS', 0, '==', '本环不碰任务'),
        # ---- 注入块内不得自建网络调用（走 YlxwUseAct / Xc 统一鉴权层）----
        ('R71·注入块未自建 fetch',   'fetch(', 0, '==', '统一走 YlxwUseAct',
         ('/* ===== yl-R071:', 'function YlxwTPet() {')),
    ]
    return gates
