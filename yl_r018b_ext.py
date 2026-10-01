# -*- coding: utf-8 -*-
r"""
yl_r018b_ext.py — R-018 D5 灵纹（客户端单模块）

需求（用户原话，台账 R-018）
--------------------------------------------------------------------------
  「妖灵培养可操作的选项太少了，只有喂养和嬉戏两个功能，拉策划师完全重新设计」

本模块补齐设计案 `策划_妖灵培养重设计.md` §2 D5 中**上一批刻意未做**的「灵纹」整维：
  「妖灵每 10 级解锁 1 条「灵纹」，从已解锁的灵纹中任选 1 条生效；花 50,000 灵石可换纹。」
    | 灵纹 | 解锁 | 效果 | 落点 |
    | 锐纹 | Lv10 | 主人暴击率 +1.5% | 客户端 |
    | 御纹 | Lv20 | 主人减伤 +2%    | 客户端 |
    | 疾纹 | Lv30 | 主人闪避 +1.5% | 客户端 |
    | 噬纹 | Lv40 | 主人吸血 +1%    | 客户端 |
    | 蕴纹 | Lv50 | 妖灵秘径修为产出 +30% | 服务端（srv_patch_r018b.py） |
    | 天纹 | Lv60 | 妖灵之力 PP ×1.10 | 服务端（srv_patch_r018b.py） |
  ★ 全部数值照设计原文，**未发明任何数值**。

本模块（客户端半边）
--------------------------------------------------------------------------
  C0  注入模块级助手（`YlxwR18bRuneBattle` + `YlxwR18bRuneRow`）
  C1  `YlxwR18Panel` 培养入口块追加「灵纹」换纹行（不删任何既有行）
  C2  `YlxwBattleBonus(p)` 接入 4 条战斗类灵纹（锐/御/疾/噬）

★ 4 条战斗类灵纹为什么只挂 `YlxwBattleBonus` 一处就能「两套战斗同时生效」
--------------------------------------------------------------------------
  · 快速结算 `X0`（@706966）直接读 `YlxwBattleBonus(t)` 的 critRate / dodgeRate /
    lifeLeech / damageReduction。
  · 回合制 `QS` 经 `YlxwSpellBuffs(p)` 把 `YlxwBattleBonus(p)` 包成 duration:9999 的 buff
    （bundle 内 `YlxwSpellBuffs` 定义注释即写明「供回合制战斗（读 buffs）消费」）。
  ⇒ 在 `YlxwBattleBonus` 的聚合末尾（`YlxwBattleCap(o)` 封顶之前）加一层灵纹，
     两套战斗**同时**吃到（与 r018 出口 PP 的挂点风格一致）。
  · 服务端把灵纹战斗类写进 `player.petSpirit.rune*`；客户端**只读**，不复制服务端公式。

★ 与上游硬门禁的锚区冲突检查
--------------------------------------------------------------------------
  · `yl_bond_ext.py`：改的是 `YlxwBattleBonus(p)` **签名之后的前 3 行**（`_OLD_BATTLE_BONUS`），
    本模块改的是该函数**中后段**（`var eq = YlxwEqItems(p), i, j, af;` 之前插入）。
    两处零重叠；bond 门禁 `ylxwBond.*` 计数不受影响。
  · `yl_r018_ext.py`：本模块只**追加**一行 `YlxwR18bRuneRow(...)` 到 `YlxwR18Panel`，
    不改其任何函数签名 / 门禁串（`YlxwR18Panel` / `YlxwR18MiscRow` / `YlxwSpiritExtras` 原样保留）。
  · `yl_char2_ext.py`：其面板战斗增益 `YlxwChar2Cells` 读 `YlxwBattleBonus` ⇒ 灵纹战斗类
    会自动出现在角色面板的暴击/闪避/吸血/减伤里（同源，无需改 char2）。

硬约束
--------------------------------------------------------------------------
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/auth_token/X-YL-）。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py、不写 build/assets/。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R018b: D5 灵纹（6 条被动 · 任选 1 条生效 · 每 10 级解锁）=====
   数据源：GET /api/pet 回显 t.rune = { active, list:[{key,name,unlock,desc,unlocked}] }；
   换纹：POST /api/pet/rune { rune }（首次激活免费，此后 50000 灵石/次，服务端权威）。
   战斗类灵纹（锐/御/疾/噬）：服务端写入 player.petSpirit 的 rune* 字段，
   由本模块挂进 YlxwBattleBonus ⇒ 快速结算 X0 与回合制（YlxwSpellBuffs）同时生效。 */

/* ---------- 战斗层：灵纹战斗类加成（锐/御/疾/噬）—— 只读 player.petSpirit，不复制服务端公式 ---------- */
function YlxwR18bRuneBattle(o, p) {
  var s = p && p.petSpirit;
  if (!o || !s) return;
  if (s.runeCrit) o.critRate += Number(s.runeCrit) || 0;
  if (s.runeDodge) o.dodgeRate += Number(s.runeDodge) || 0;
  if (s.runeLeech) o.lifeLeech += Number(s.runeLeech) || 0;
  if (s.runeDR) o.damageReduction += Number(s.runeDR) || 0;
}

/* ---------- 面板：灵纹换纹行 ---------- */
function YlxwR18bRuneRow(t, m, f, u) {
  var r = t && t.rune;
  if (!r) return null;
  var cost = YlxwNum(t && t.consts && t.consts.runeCost) || 50000;
  var list = r.list || [];
  var active = r.active || "";
  var btns = list.map(function (d) {
    var on = (active === d.key);
    return e.jsx(YlxwBtn, {
      tone: on ? undefined : "ghost",
      disabled: !!u || !d.unlocked || on,
      onClick: function () { f("r18brune-" + d.key, "/pet/rune", { rune: d.key }, "已激活「" + d.name + "」"); },
      children: d.name + "（" + d.desc + (d.unlocked ? "" : " · 需 Lv" + YlxwNum(d.unlock)) + "）",
    }, d.key);
  });
  return e.jsxs("div", { className: "space-y-2", children: [
    e.jsxs("div", { className: "flex flex-wrap items-center gap-2", children:
      [e.jsx("span", { className: "text-xs text-stone-400 w-12", children: "灵纹" })].concat(btns) }),
    e.jsx("div", { className: "text-[11px] text-stone-500", children:
      "每 10 级解锁 1 条，任选 1 条生效；首次激活免费，换纹 " + cost + " 灵石/次。当前：" + (active ? active : "未激活") }),
  ] });
}
'''

# --------------------------------------------------------------------------- 锚点常量（实测 count==1）

# C0 注入锚：`YlxwTPet` 定义之前（与 r018 同锚；r018 先插 ⇒ 本块落在 r018 块之后）
ANCHOR_TPET = 'function YlxwTPet() {'

# C1 面板培养入口块末行（r018 注入块内；全仓唯一）
PANEL_TAIL = 'YlxwR18MiscRow(t, m, f, u),'

# C2 战斗聚合函数中后段（bond 模块改的是该函数开头 3 行，两者零重叠）
BATTLE_ANCHOR = '  var eq = YlxwEqItems(p), i, j, af;'
BATTLE_NEW = (
    '  /* R-018b D5 灵纹战斗类：锐/御/疾/噬（服务端写 player.petSpirit.rune*；末尾由 YlxwBattleCap 统一封顶） */\n'
    '  YlxwR18bRuneBattle(o, p);\n'
    + BATTLE_ANCHOR
)

EDITS = [
    ('C1 灵纹换纹行挂进培养面板', PANEL_TAIL, PANEL_TAIL + ' YlxwR18bRuneRow(t, m, f, u),'),
    ('C2 战斗聚合接入灵纹',       BATTLE_ANCHOR, BATTLE_NEW),
]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 r018 / bond / char2）；
    ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r018b 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # C0) 模块级助手（顶层同作用域；函数声明提升 ⇒ YlxwBattleBonus / 面板均可引用）
    p.insert_before('r018b-helpers', ANCHOR_TPET, blk + '\n',
                    expect=1, note='注入 YlxwR18bRuneBattle + YlxwR18bRuneRow')

    # C1-C2) 就地替换
    for name, old, new in EDITS:
        p.replace(name, old, new, expect=1)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 注入块 · 战斗层 =================
        ('R18b·灵纹战斗层函数已注入', 'function YlxwR18bRuneBattle(o, p) {', 1, '==', ''),
        ('R18b·只读 player.petSpirit', 'var s = p && p.petSpirit;', 1, '==', '不复制服务端公式'),
        ('R18b·灵纹暴击',             'if (s.runeCrit) o.critRate += Number(s.runeCrit) || 0;', 1, '==', ''),
        ('R18b·灵纹闪避',             'if (s.runeDodge) o.dodgeRate += Number(s.runeDodge) || 0;', 1, '==', ''),
        ('R18b·灵纹吸血',             'if (s.runeLeech) o.lifeLeech += Number(s.runeLeech) || 0;', 1, '==', ''),
        ('R18b·灵纹减伤',             'if (s.runeDR) o.damageReduction += Number(s.runeDR) || 0;', 1, '==', ''),
        # ================= 注入块 · 面板 =================
        ('R18b·灵纹换纹行已注入',     'function YlxwR18bRuneRow(t, m, f, u) {', 1, '==', ''),
        ('R18b·灵纹数据取服务端回显',  'var r = t && t.rune;', 1, '==', ''),
        ('R18b·换纹端点',             'f("r18brune-" + d.key, "/pet/rune", { rune: d.key }', 1, '==', ''),
        ('R18b·已解锁才可点',          'disabled: !!u || !d.unlocked || on,', 1, '==', ''),
        # ================= 挂载点 =================
        ('R18b·换纹行挂进培养面板',    'YlxwR18MiscRow(t, m, f, u), YlxwR18bRuneRow(t, m, f, u),', 1, '==', ''),
        ('R18b·战斗聚合已挂灵纹',      'YlxwR18bRuneBattle(o, p);', 1, '==', ''),
        # ================= 冻结（本环不得回踩上游门禁面）=================
        ('冻结·r018 妖灵卡挂载未动',   'm ? e.jsxs(e.Fragment, { children: [YlxwR18Card(t, m), YlxwR18Panel(t, m, f, u)] })', 1, '==', ''),
        ('冻结·r018 面板签名未动',     'function YlxwR18Panel(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 点化归位行未动',   'function YlxwR18MiscRow(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 出口加算未动',     'function YlxwSpiritExtras(p, r) {', 1, '==', ''),
        ('冻结·r018 xt 末尾挂载未动',  'typeof YlxwSpiritExtras==="function"&&YlxwSpiritExtras(t,r)', 1, '==', ''),
        ('冻结·r018 妖灵面板未整体重写', 'function YlxwTPet() {', 1, '==', ''),
        ('冻结·r018 /pet 端点未改',    'YlxwUseList("/pet")', 1, '==', ''),
        ('冻结·bond 战斗层消费点未动', 'var ylxwBond = YlxwBondCap(fy(Pm((p && p.cultivationArts) || [])));', 2, '==', '属性层 + 战斗层'),
        ('冻结·bond 战斗层封顶未动',   'return YlxwBattleCap(o);', 1, '==', ''),
        ('冻结·战斗结算核心未动',      'YlxwBattleBonus(t),YlxwDOD=', 1, '==', ''),
        ('冻结·战斗聚合函数仍在',      'function YlxwBattleBonus(p) {', 1, '==', ''),
        ('冻结·战斗 buff 包装仍在',    'function YlxwSpellBuffs(p) {', 1, '==', ''),
        ('冻结·YlxwStatExtras 未动',   'function YlxwStatExtras(p, r) {', 1, '==', ''),
        ('R18b·未新增仙途任务',        'QUEST_DEFS', 0, '==', '不碰任务'),
        # ---- 注入块内不得自建网络调用（走 YlxwUseAct / Xc 统一鉴权层）----
        ('R18b·注入块未自建 fetch',    'fetch(', 0, '==', '统一走 YlxwUseAct',
         ('/* ===== yl-R018b:', 'function YlxwTPet() {')),
    ]
    return gates
