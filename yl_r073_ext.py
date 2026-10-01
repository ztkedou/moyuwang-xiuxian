# -*- coding: utf-8 -*-
r"""
yl_r073_ext.py — R-073 妖灵「进食」线（客户端半边）

需求原文（用户）
--------------------------------------------------------------------------
  「仙务·妖灵 进食的成本降低，这个饱食度实际作用是什么？
    此外还发现一个 bug，妖灵归位的种族和名字不匹配。」

本模块 = R-073 的**客户端两件事**（进食成本降低是服务端半边，见 srv_patch_r073.py）：
  A) 「饱食度」作用说明 —— 在妖灵卡上常显（原 UI 只写「喂食度 x / 9999」，没说它干嘛）
  B) 修「归位后种族与名字不匹配」—— `YlxwSpiritToPet` 的 name/species 取值错位

A) 饱食度的实际作用（**读代码得出的事实，不是编的**）
--------------------------------------------------------------------------
  · 服务端 `petLevel(hunger) = floor(hunger / PET_LEVEL_DIVISOR)`，`PET_LEVEL_DIVISOR = 100`
    （`srv/index_v28.ts:5852` / `:5827`）⇒ **饱食度就是妖灵的「经验值」，每 100 点 = 1 级**。
  · 等级 → 妖灵之力 PP：`r018SpiritPP()` 的 `(1 + lv/99)`（`srv_patch_r018.py:127`）。
  · 等级 → 妖灵本体属性：`r018SpiritStats()` 的 `(1 + lv*0.06)`（攻/防/血）、`(1 + lv*0.03)`（速）
    （`srv_patch_r018.py:135-138`）。
  · 主人加成 = 妖灵属性 × 0.06 × PP（`r018SpiritBonus()`，`:147-150`）→ 写存档 `player.petSpirit`
    → 客户端 `YlxwSpiritExtras()` 直接加算到 attack/defense/maxHp/speed（`yl_r018_ext.py:74-82`）。
  ⇒ 结论：**饱食度不是装饰，它决定等级，等级决定 PP 与主人属性加成**。
     上限 `PET_HUNGER_MAX = 9999`（`:5826`），满级 99 级 = 9900 点 ⇒ 超过 9900 再喂纯属浪费。

B) 根因（**字段错位**，证据 = 产物字节偏移）
--------------------------------------------------------------------------
  `yl_pet089_ext.py` 注入的 `YlxwSpiritToPet(sp, speciesPool)`（产物 @1384713 区）里：
      var pick = pool.length ? pool[Math.floor(Math.random() * pool.length)] : null;   ← 种族：同品阶池里**随机**挑
      ...
      name: (sp && sp.name) || (pick && pick.name) || "妖灵",   ← 名字：取**妖灵自己的名字**
      species: pick ? pick.species : "灵兽",                      ← 种族：取上面那个随机 pick
  ⇒ 名字与种族来自**两个互不相干的来源**（`sp.name` vs 随机 `pick`）：
     妖灵「灵狐」归位后可能变成「名字=灵狐、种族=虎族」，玩家一眼看出不匹配。
  · 而 v2810e 的**预览**函数 `YlxwSpiritPetView()`（@973252 区）用的是**确定性**选种：
      pool[YlxwSpiritHash(String((sp && sp.name) || "") + "|" + mapped) % pool.length]
    ⇒ 预览显示的种族 与 实际归位得到的种族 还会**不一致**（一处随机、一处稳定）。

B) 修法（只改「名字/种族的取值」，不动归位流程）
--------------------------------------------------------------------------
  · 选种改为与预览**逐字同一式**（`YlxwSpiritHash`，v2810e 已造、r045 已证可达）⇒ 预览 = 结果。
  · 名字改为**从选中的那个物种派生**（`pick.nameVariants` 取一变体，兜底 `pick.name`）——
    这是基座自己的惯例（`const oy = t => t.nameVariants ? ... : t.name`；孵化/获得灵宠处全是
    `name: oy(物种), species: 物种.species`）。名字与种族从此**同源**，必然匹配。
    （副作用：妖灵原名字被物种名替换。若主控要「保名」，需给 10 个妖灵名建种族映射表 ——
      但那 10 个名字里只有「灵狐 / 玉兔」能对上现有 23 物种，映射表覆盖不了，故按基座惯例走。）
  · `stats:` 行（含 `pick.species`）**一字不动** —— 那是 r045 的门禁面。

硬约束 / 纪律
--------------------------------------------------------------------------
  · INJECT_JS 为空 ⇒ 天然不含 V28_BAN_PATTERNS，也不新增任何网络调用。
  · 锚点/门禁串全 ASCII（含中文的地方一律用 ASCII 边界截断），每处 replace 带 expect=1。
  · 不删任何被 r018 / r018b / r045 门禁冻结的串：
      `function YlxwR18Card(t, m) {` / `function YlxwR18FeedRow(t, m, f, u) {` /
      `f("r18feed-" + k, "/pet/feed", { tier: k }` / `YlxwPetSpeciesStats(pick.species, 1, 0)` 等
      全部原样保留（本模块只改相邻取值，不碰这些串）。
  · 只新建本文件；不改 build_v26n.py / localtest/* / srv/index_v28.ts / deploy_v28/*。
  · ★ 接线顺序：必须排在 `r018`（锚在其注入块内）与 `pet089`（锚在其注入块内）之后；
    与 `r045` / `r071` 零锚点交集，先后皆可。建议 `r073` → `r074`，都排在 `r071` 之后、`numbal` 之前。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = ''          # 本模块只做「就地替换」，不注入任何新代码

# --------------------------------------------------------------------------- A 锚点：妖灵卡六字段之后（r018 注入块内；全仓唯一）

CARD_KV_OLD = 'e.jsx(YlxwKv, { data: data }),'

# 在六字段卡片与「PP 说明」之间插一行常显说明：把饱食度的实际作用讲清楚
CARD_KV_NEW = (
    'e.jsx(YlxwKv, { data: data }), '
    'e.jsx("div", { className: "text-[11px] text-stone-500", children: '
    '"饱食度＝妖灵经验：每 100 点 = 1 级（满级 99 级＝9900 点，上限 9999）；'
    '等级越高 → 妖灵之力 PP 越高 → 主人属性加成越高。满 9999 后再进食不再提升等级。" }),'
)

# A 门禁串（ASCII 边界：锚点 + 新插入元素的开头，替换前全仓 0 次）
CARD_KV_GATE = ('e.jsx(YlxwKv, { data: data }), '
                'e.jsx("div", { className: "text-[11px] text-stone-500", children: "')

# --------------------------------------------------------------------------- B 锚点：归位取值（pet089 注入块内；全仓唯一）

# B1 选种：随机 → 与 v2810e 预览逐字同式的确定性散列
PICK_OLD = '  var pick = pool.length ? pool[Math.floor(Math.random() * pool.length)] : null;'
PICK_NEW = ('  var pick = pool.length ? pool['
            'YlxwSpiritHash(String((sp && sp.name) || "") + "|" + mapped) % pool.length'
            '] : null;')

# B2 名字：取妖灵名 → 从选中的物种派生（同源 ⇒ 名字与种族必然匹配）
#    ★ 锚点止于 `|| `（纯 ASCII），保留其后的 `"\u5996\u7075",` 兜底字面量原样
NAME_OLD = '    name: (sp && sp.name) || (pick && pick.name) || '
NAME_NEW = ('    name: (pick && pick.nameVariants && pick.nameVariants.length '
            '? pick.nameVariants[Math.floor(Math.random() * pick.nameVariants.length)] '
            ': (pick && pick.name)) || (sp && sp.name) || ')

# B 门禁串
PICK_GATE = 'pool[YlxwSpiritHash(String((sp && sp.name) || "") + "|" + mapped) % pool.length]'
NAME_GATE = 'pick.nameVariants[Math.floor(Math.random() * pick.nameVariants.length)]'

# 依赖：v2810e 的稳定散列（r045 已证：同块函数在 pet089 注入块内可达）
DEP_SPIRIT_HASH = 'function YlxwSpiritHash(v) {'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 pet089 / v2810e / r018 / r018b / r045）；
    ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检 0：本模块刻意零注入（顺带证明不含 V28_BAN_PATTERNS）
    if INJECT_JS != '':
        raise AssertionError('r073 本应零注入，INJECT_JS 非空')

    # 自检 1：锚点/替换串手滑护栏（防写成空串或漏改）
    if 'YlxwKv, { data: data }' not in CARD_KV_OLD:
        raise AssertionError('r073 A 锚点异常：未命中妖灵卡六字段行')
    if 'Math.random() * pool.length' not in PICK_OLD or 'YlxwSpiritHash' not in PICK_NEW:
        raise AssertionError('r073 B1 锚点/替换串异常：未命中「随机选种 → 稳定散列」')
    if 'pick && pick.name' not in NAME_OLD or 'pick.nameVariants' not in NAME_NEW:
        raise AssertionError('r073 B2 锚点/替换串异常：未命中「名字取值」')

    # A) 妖灵卡：补一行饱食度作用说明（常显）
    p.replace('r073-hunger-note', CARD_KV_OLD, CARD_KV_NEW, expect=1,
              note='妖灵卡补「饱食度＝经验，每 100 点 1 级，决定 PP 与主人加成」常显说明')

    # B) 归位取值：选种确定性（与预览同式）+ 名字从选中物种派生（名字↔种族同源）
    p.replace('r073-away-pick', PICK_OLD, PICK_NEW, expect=1,
              note='归位选种改走 YlxwSpiritHash（与 v2810e 预览 YlxwSpiritPetView 逐字同式）')
    p.replace('r073-away-name', NAME_OLD, NAME_NEW, expect=1,
              note='归位名字改从选中物种派生 ⇒ 名字与种族不再错位')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= A 饱食度说明 =================
        ('R73·饱食度说明已常显', CARD_KV_GATE, 1, '==',
         '插在妖灵卡六字段之后；文本见 yl_r073_ext.py CARD_KV_NEW'),
        # ================= B 归位取值 =================
        ('R73·选种改走稳定散列', PICK_GATE, 2, '==',
         '预览 1 处 + 归位 1 处（本模块新增），两处逐字同式'),
        ('R73·归位随机选种已清零',
         'var pick = pool.length ? pool[Math.floor(Math.random() * pool.length)] : null;', 0, '==',
         '旧形态：同品阶池内随机 ⇒ 与预览不一致'),
        ('R73·名字改从物种派生', NAME_GATE, 1, '==',
         '名字与种族同源（基座 oy() 同惯例）'),
        ('R73·旧「名字取妖灵名」已清零',
         'name: (sp && sp.name) || (pick && pick.name) || ', 0, '==', '旧形态：与随机种族错位'),
        ('R73·名字兜底链保留', 'pick && pick.name)) || (sp && sp.name) || ', 1, '==',
         '`|| (sp && sp.name)` 兜底仍在（pick 为 null 时）'),
        # ================= 依赖（上游函数在位） =================
        ('依赖·v2810e 稳定散列在位', DEP_SPIRIT_HASH, 1, '==', '本模块替换目标；缺则硬失败'),
        ('依赖·归位桥在位', 'function YlxwSpiritToPet(sp, speciesPool) {', 1, '==', ''),
        # ================= 冻结：本模块不得回踩上游门禁面 =================
        ('冻结·r045 归位属性桥未动', 'YlxwPetSpeciesStats(pick.species, 1, 0)', 1, '==', 'r045 门禁面'),
        ('冻结·r018 妖灵卡签名未动', 'function YlxwR18Card(t, m) {', 1, '==', ''),
        ('冻结·r018 培养面板签名未动', 'function YlxwR18Panel(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 进食三档未动', 'function YlxwR18FeedRow(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 进食端点未动', 'f("r18feed-" + k, "/pet/feed", { tier: k }', 1, '==', ''),
        ('冻结·r018 互动三选未动', 'function YlxwR18PlayRows(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 秘径行未动', 'function YlxwR18ExpedRow(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 点化归位行未动', 'function YlxwR18MiscRow(t, m, f, u) {', 1, '==', ''),
        ('冻结·r018 妖灵面板未整体重写', 'function YlxwTPet() {', 1, '==', ''),
        ('冻结·r018 出口加算未动', 'function YlxwSpiritExtras(p, r) {', 1, '==', ''),
        ('冻结·r018b 灵纹战斗层未动', 'function YlxwR18bRuneBattle(o, p) {', 1, '==', ''),
        ('冻结·归位端点未动', 'f("r18away", "/pet/spirit/away"', 1, '==', 'r018/r071 共同冻结面'),
        ('冻结·归位客户端桥未动', 'YlxwMergeSpiritAway(m); YlxwDirty();', 1, '==', ''),
        ('冻结·战斗结算核心未动', 'YlxwBattleBonus(t),YlxwDOD=', 1, '==', ''),
        ('R73·未新增仙途任务', 'QUEST_DEFS', 0, '==', '本环不碰任务'),
    ]
    return gates
