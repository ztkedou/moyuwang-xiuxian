# -*- coding: utf-8 -*-
r"""
yl_v2810a_ext.py -- 称号列表展示「装备后加成数值」+ 角色属性面板补「作用说明/全部属性」

用户原话：
  ①「解锁的称号里展示装备后增加的数值，方便选择装备」
  ②「角色信息中『角色属性』显示神识/体魄/速度对游戏数值的作用描述；
     展示命中/暴击/闪避/吸血等全部属性数值」

=========================================================================== 侦察结论（逐字实证，基座 index-v26m-20260927.js）

【称号列表（任务 A）】
  真身**不是** `YlxwTTitles`（那是「仙务枢钮」页签，@826605，只显示 name/来源/佩戴）。
  用户截图对应的是**角色信息弹窗**里的「已解锁的称号」区块（基座 @1036318），
  其列表项渲染为（逐字）：
      L.map(F=>{const W=F.id===a.titleId, K=...;return e.jsx("button",{...
        children:e.jsxs("div",{className:"flex justify-between items-start",children:[
          e.jsxs("div",{className:"flex-1",children:[
            e.jsxs("div",{className:"flex items-center gap-2 mb-1",children:[
              <span className={font-bold ...}>{F.name}</span>,
              F.rarity && <span>({F.rarity})</span>,
              F.category && <span>[{F.category}]</span>,
              W && <span>已装备</span>,                 ← 现有「已装备」标识（须保留）
              K && !W && <span>套装可用</span>
            ]}),
            e.jsx("p",{className:"text-xs text-stone-400 mb-1",children:F.description}),   ← 无任何数值
            e.jsx("p",{className:"text-xs text-stone-500",children:F.requirement})
          ]}),
          !W && e.jsx("div",{...children:"点击装备"})
        ]})},F.id)})
  ⇒ 每项确实只有「名称+品阶+[分类]+已装备+套装可用+描述+解锁条件+点击装备」，**没有 effects 数值**。

  称号数据表 `Ln`（基座 @376370）形如：
      {id:"title-foundation",name:"筑基修士",description:"...",requirement:"达到筑基期",
       effects:{attack:10,defense:5}}
  称号 effects 实际用到的键（`Ln` 全量扫描）：attack / defense / hp / spirit /
      physique / speed / expRate / luck —— 全部为「数值」，expRate 为小数百分比语义。
  套装表 `fd`（基座 @379149）另含套装 effects（attack/defense/hp/speed/spirit/luck/expRate）。
  全基座 `effects:{...}` 键集合（用于把标签表写全）：specialEffect / spiritBonus / attack /
      hpBonus / defense / attackBonus / defenseBonus / hp / expRate / speedBonus / speed /
      spirit / physiqueBonus / hpPercent / luck / attackPercent / critRate / physique /
      critDamage / damageReduction / defensePercent / dodgeRate / counterRate /
      counterDamage / lifeLeech / spiritPercent / speedPercent / counter。
  现成标签表先例（基座 @866500）：
      {attack:"攻击",defense:"防御",hp:"生命",spirit:"神识",physique:"体魄",speed:"速度",
       expRate:"修炼速度",attackPercent:"攻击%",...,critRate:"暴击率",critDamage:"暴伤",
       damageReduction:"减伤",dodgeRate:"闪避",lifeLeech:"吸血"}
      百分比判定：key 含 "Percent"/"Rate" 或 ∈{expRate,lifeLeech,dodgeRate,damageReduction}
      ⇒ `${Math.round(d*100)}%`，否则 `+${d}`。
  本模块沿用同一口径，但把 hp 标为「气血」（与面板一致）、rate 类不缀「%」字（值本身带 %）。

【角色属性面板（任务 B）】
  面板真身在**角色信息弹窗**（基座 @1024936，标题「角色属性」，tab 名「角色信息」@1007900）：
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm" children:[
        攻击:{b.attack} / 防御:{b.defense} / 气血:{a.hp}/{b.maxHp} /
        神识:{b.spirit} / 体魄:{b.physique} / 速度:{b.speed} / 声望:{a.reputation||0}
      ]>
  其中 `b = O.useMemo(()=>xt(a),[a])`；`xt`（基座 @560874）**只**返回
      {attack, defense, maxHp, spirit, physique, speed}
      —— 没有命中/暴击/闪避/吸血。
  `a` = 玩家对象，其**真实平铺字段**（基座 @495624 默认玩家对象逐字）：
      name, realm, realmLevel, exp, maxExp, hp, maxHp, attack, defense, spirit, physique,
      speed, spiritStones, luck, karma, reputation, attributePoints, ...
      ⇒ 同样**没有** hit/hitRate/critRate/dodgeRate/lifeLeech。
  ⇒ 结论：命中 / 暴击 / 闪避 / 吸血 **在数据模型里不存在**（不是没渲染，是根本没有）。
     实证：全基座 `hitRate`=0 次；`命中` 7 次全为文案（「命中有贵人」「命中注定」）
     或 `specialEffect` 描述串（「法术命中率提升25%」）；`critRate/dodgeRate/lifeLeech`
     只出现在天赋/功法/神通/装备的 `effects` 里，或本模块之前各模块新增的神通融合效果里，
     从未落到玩家对象上。
     ⇒ 遵嘱「不造假数据」：**不渲染**这四项；改为「存在才渲染」的通用渲染器，
        数据模型里当前只有 `luck`（幸运）会真正渲染出来。

  神识/体魄/速度 的作用（按战斗代码实证，而非臆测）：
    · spirit（神识）：
        - 法术攻击 —— @660310 `$ = damage.type==="magical" ? c.spirit : c.attack`
        - 法术防御 —— 同处 `h = damage.type==="magical" ? d.spirit : d.defense`
        - 行动次数 —— @657813 `od(player.speed,enemy.speed,player.spirit,enemy.spirit)`
        - 法力上限 —— @654765 `T = 60 + realm*70 + floor(spirit*0.8)`
        - 神识差 ≥20% 触发「震慑」额外行动 —— @652467
    · physique（体魄）：
        - 只影响**气血上限** —— 属性点表 @627771 `Ps={...,physique:3,physiqueHp:10,...}`，
          分配体魄时 `maxHp += floor(Ps.physiqueHp*g)`（@700342）；
          战斗实体 `QS`（@654765）根本不把 physique 传进战斗。
        - **不影响防御**（用户示例口径「影响气血上限与防御」中「防御」部分与代码不符，已按实证写）
    · speed（速度）：
        - 出手顺序/先手 —— @652467 `T = j.speed >= b.speed`
        - 行动次数 —— `od(speed, ...)`
        - 暴击率 —— @658400 `f += speed/(speed+enemySpeed)*0.1`（上限 0.35）
        - 闪避 —— @658400 `N = min(.15,(enemySpeed-playerSpeed)*5e-4)`

=========================================================================== 改法（最小侵入，不重写组件）

任务 A：在称号列表项**描述行之前**插入一行效果文本。
  锚点 = 描述行 `e.jsx("p",{className:"text-xs text-stone-400 mb-1",children:F.description})`
  （基座/链产物均唯一；注意 `children:F.requirement}` 在「未解锁的称号」区还有一处，
   故不能拿 requirement 行当锚）。
  注入 = `YlxwTitleEffectsLine(F.effects),` + 原描述行 ⇒ 数组子节点由
  `[名字行, 描述, 条件]` 变为 `[名字行, 效果行, 描述, 条件]`。
  `YlxwTitleEffectsLine` 在无 effects / 全 0 时返回 `null`（不产生空 `<p>`，不占位）。

任务 B-1：在 神识 / 体魄 / 速度 的**数值 span 之后**追加一枚 10px 小字说明。
  锚点 = 三个数值 span（各自唯一，含 className）：
    `e.jsx("span",{className:"text-purple-400 font-bold",children:b.spirit})`
    `e.jsx("span",{className:"text-orange-400 font-bold",children:b.physique})`
    `e.jsx("span",{className:"text-yellow-400 font-bold",children:b.speed})`
  注入 = 原 span + `,YlxwStatHintEl("xxx")` ⇒ 单元格子节点
  `[label," ",value]` 变 `[label," ",value,hint]`。原「label: value」结构一字未动，
  不影响 grid 对齐基准；`YlxwStatHintEl` 无文案时返回 `null`。

任务 B-2：在面板 grid 末尾追加「补充属性」单元格。
  锚点 = 声望单元格（唯一）：
    `e.jsxs("div",{children:[e.jsx("span",{className:"text-stone-400",children:"声望:"}),
     " ",e.jsx("span",{className:"text-mystic-gold font-bold",children:a.reputation||0})]})`
  注入 = 原单元格 + `,...YlxwStatExtraCells(a,b)` ⇒ 数组字面量展开，
  `children:[...7 格..., 声望格, ...补充格]`。当前数据模型下只展开出「幸运」一格
  （命中/暴击/闪避/吸血字段不存在 ⇒ 返回空数组 ⇒ 零渲染）。

硬约束遵守：
  · 只新建本文件；不写回 build/assets/；不改 build_v26n.py（接线由 lead 统一做）。
  · 注入块 zh() 后纯 ASCII；不含禁用模式 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-。
  · 不用 require；纯前端 UI，不写存档、不发请求、不改任何战斗数值。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
"""

import re

# --------------------------------------------------------------------------- 注入块（辅助函数）

INJECT_JS = r'''
/* ===== yl-0.8.10 v2810a =====
   A) 称号列表：每项渲染「装备后加成数值」（effects → 可读文本，覆盖全部属性键）
   B) 角色属性面板：神识/体魄/速度 作用说明（小字）+ 补充命中/暴击/闪避/吸血等
      补充项走「数据模型里存在才渲染」，缺字段则不渲染（不造假数据）。
   纯客户端 UI：不写存档、不发网络请求、不改任何战斗数值。 */

/* --- A1 属性键 → 中文标签（覆盖全基座 effects 键集；口径沿用基座 @866500 的标签表） --- */
var YLXW_TEFF_LABEL = {
  attack: "攻击", defense: "防御", hp: "气血", maxHp: "气血", spirit: "神识",
  physique: "体魄", speed: "速度", luck: "幸运", expRate: "修炼速度",
  attackBonus: "攻击", defenseBonus: "防御", hpBonus: "气血", maxHpBonus: "气血",
  spiritBonus: "神识", physiqueBonus: "体魄", speedBonus: "速度",
  attackPercent: "攻击", defensePercent: "防御", hpPercent: "气血",
  spiritPercent: "神识", physiquePercent: "体魄", speedPercent: "速度",
  critRate: "暴击", critChance: "暴击", critDamage: "暴伤",
  dodgeRate: "闪避", dodge: "闪避", hit: "命中",
  lifeLeech: "吸血", vampire: "吸血", damageReduction: "减伤",
  counterRate: "反击", counterDamage: "反击伤害", counter: "反击",
  damageMultiplier: "伤害倍率", triggerChance: "触发几率", specialEffect: "特殊效果"
};

/* --- A2 百分比语义键（小数 → 百分数展示） --- */
var YLXW_TEFF_PCT = {
  expRate: 1, attackPercent: 1, defensePercent: 1, hpPercent: 1, spiritPercent: 1,
  physiquePercent: 1, speedPercent: 1, critRate: 1, critChance: 1, critDamage: 1,
  dodgeRate: 1, dodge: 1, hit: 1, lifeLeech: 1, vampire: 1,
  damageReduction: 1, counterRate: 1, triggerChance: 1
};

/* --- A3 单项格式化；空值/零值/非有限值一律返回 ""（不渲染噪声项） --- */
function YlxwTitleEffOne(k, v) {
  if (v === void 0 || v === null) return "";
  if (typeof v === "number" && (!isFinite(v) || v === 0)) return "";
  var lb = YLXW_TEFF_LABEL[k] || k;
  if (typeof v !== "number") return lb + " " + String(v);
  if (YLXW_TEFF_PCT[k]) return lb + " +" + Math.round(v * 100) + "%";
  return lb + " +" + v;
}

/* --- A4 整条称号效果 → 一行文本，形如「加成 · 攻击 +10 · 防御 +5」 --- */
function YlxwTitleEffectText(effects) {
  if (!effects) return "";
  var ks = Object.keys(effects), parts = [], i, s;
  for (i = 0; i < ks.length; i++) {
    s = YlxwTitleEffOne(ks[i], effects[ks[i]]);
    if (s) parts.push(s);
  }
  return parts.length ? ("加成：" + parts.join(" · ")) : "";
}

/* --- A5 效果行节点；无内容返回 null（不产生空节点，不破坏原有排版） --- */
function YlxwTitleEffectsLine(effects) {
  var t = YlxwTitleEffectText(effects);
  return t ? e.jsx("p", { className: "text-xs text-emerald-300 mb-1", children: t }) : null;
}

/* --- B1 神识/体魄/速度 的作用说明（按战斗代码实证口径） ---
   注：reputation / luck 两项由 yl_char2_ext（R-012）追加，只加不改已有条目。 --- */
var YLXW_STAT_HINT = {
  spirit: "影响法术攻击/防御与行动次数",
  physique: "影响气血上限",
  speed: "影响出手顺序、暴击与闪避",
  reputation: "影响声望商店门槛与奇遇结算",
  luck: "影响奇遇触发、炼丹成功率与品级"
};

/* --- B2 作用说明节点（10px 小字，紧跟数值；无文案返回 null） --- */
function YlxwStatHintEl(key) {
  var t = YLXW_STAT_HINT[key];
  return t ? e.jsx("span", { className: "text-[10px] text-stone-500 ml-1", children: t }) : null;
}

/* --- B3 补充属性登记表：命中/暴击/闪避/吸血 + 幸运（幸运是玩家真实字段） --- */
var YLXW_STAT_EXTRA = [
  { k: "hit", label: "命中", pct: 1 },
  { k: "critRate", label: "暴击", pct: 1 },
  { k: "dodgeRate", label: "闪避", pct: 1 },
  { k: "lifeLeech", label: "吸血", pct: 1 },
  { k: "luck", label: "幸运", pct: 0 }
];

/* --- B4 补充属性单元格；字段不存在（或非有限数值）⇒ 跳过，绝不造假数据 --- */
function YlxwStatExtraCells(a, b) {
  var out = [], i, d, v, s;
  for (i = 0; i < YLXW_STAT_EXTRA.length; i++) {
    d = YLXW_STAT_EXTRA[i];
    v = (a && a[d.k] !== void 0 && a[d.k] !== null) ? a[d.k]
      : ((b && b[d.k] !== void 0 && b[d.k] !== null) ? b[d.k] : void 0);
    if (v === void 0 || typeof v !== "number" || !isFinite(v)) continue;
    s = d.pct ? (Math.round(v * 100) + "%") : String(v);
    out.push(e.jsxs("div", { key: "ylxw-x-" + d.k, children: [
      e.jsx("span", { className: "text-stone-400", children: d.label + ":" }),
      " ",
      e.jsx("span", { className: "text-cyan-400 font-bold", children: s })
    ] }));
  }
  return out;
}
'''

# --------------------------------------------------------------------------- 锚点（基座唯一，逐字）

# 辅助函数注入点：顶层函数 `YlxwTTitles` 定义之前（同模块作用域，函数声明提升）
HELPERS_ANCHOR = 'function YlxwTTitles() {'

# A：称号列表项描述行（唯一；requirement 行在「未解锁的称号」区另有同款，故不用它）
TITLE_DESC_ANCHOR = ('e.jsx("p",{className:"text-xs text-stone-400 mb-1",'
                     'children:F.description})')
TITLE_DESC_REPL = 'YlxwTitleEffectsLine(F.effects),' + TITLE_DESC_ANCHOR

# B1：三个属性数值 span（各自唯一）
SPIRIT_VAL_ANCHOR = 'e.jsx("span",{className:"text-purple-400 font-bold",children:b.spirit})'
SPIRIT_VAL_REPL = SPIRIT_VAL_ANCHOR + ',YlxwStatHintEl("spirit")'

PHYSIQUE_VAL_ANCHOR = 'e.jsx("span",{className:"text-orange-400 font-bold",children:b.physique})'
PHYSIQUE_VAL_REPL = PHYSIQUE_VAL_ANCHOR + ',YlxwStatHintEl("physique")'

SPEED_VAL_ANCHOR = 'e.jsx("span",{className:"text-yellow-400 font-bold",children:b.speed})'
SPEED_VAL_REPL = SPEED_VAL_ANCHOR + ',YlxwStatHintEl("speed")'

# B2：面板 grid 末格（声望），在其后展开补充属性单元格
REP_CELL_ANCHOR = ('e.jsxs("div",{children:[e.jsx("span",{className:"text-stone-400",'
                   'children:"声望:"})," ",e.jsx("span",{className:"text-mystic-gold '
                   'font-bold",children:a.reputation||0})]})')
REP_CELL_REPL = REP_CELL_ANCHOR + ',...YlxwStatExtraCells(a,b)'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('v2810a 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 辅助函数块（zh() 后纯 ASCII，中文全为 \uXXXX；INJECT_JS 自身以换行收尾）
    p.replace('v2810a-helpers', HELPERS_ANCHOR, blk + HELPERS_ANCHOR, expect=1,
              note='YlxwTTitles 定义前注入 称号效果文案 + 属性说明 + 补充属性 辅助函数')

    # 1) 任务 A：称号列表项插入「加成：…」效果行（描述行之前）
    p.replace('v2810a-title-eff', TITLE_DESC_ANCHOR, TITLE_DESC_REPL, expect=1,
              note='称号列表项插入 YlxwTitleEffectsLine(F.effects)')

    # 2) 任务 B-1：神识/体魄/速度 数值后追加作用说明小字
    p.replace('v2810a-hint-spirit', SPIRIT_VAL_ANCHOR, SPIRIT_VAL_REPL, expect=1,
              note='神识 数值后追加作用说明')
    p.replace('v2810a-hint-physique', PHYSIQUE_VAL_ANCHOR, PHYSIQUE_VAL_REPL, expect=1,
              note='体魄 数值后追加作用说明')
    p.replace('v2810a-hint-speed', SPEED_VAL_ANCHOR, SPEED_VAL_REPL, expect=1,
              note='速度 数值后追加作用说明')

    # 3) 任务 B-2：面板 grid 末格后展开补充属性（当前数据模型仅「幸运」命中）
    p.replace('v2810a-extra', REP_CELL_ANCHOR, REP_CELL_REPL, expect=1,
              note='声望格后展开 ...YlxwStatExtraCells(a,b)')

    # ------------------------------------------------------------- 门禁
    # 锚点纪律：needle 若落在**本模块注入块**内（或落在基座里被别的模块以转义形态写过的位置），
    #   基座里并**不存在**该串；且注入块已 zh() 转义，故必须写成 \uXXXX 转义形态（下方 r'' 原始串）。
    #   而基座自带的 UI 文案（如「已装备」「点击装备」）在基座里是**原始中文**（非转义），
    #   故这部分 needle 用原始中文字面串。两条口径已逐条实测计数（见交付说明）。
    gates = [
        # ---- 注入块就位 ----
        ('v2810a·标签表已注入',              'var YLXW_TEFF_LABEL = {',                  1, '==', ''),
        ('v2810a·百分比键表已注入',          'var YLXW_TEFF_PCT = {',                    1, '==', ''),
        ('v2810a·单项格式化函数',            'function YlxwTitleEffOne(k, v) {',         1, '==', ''),
        ('v2810a·称号效果文案函数',          'function YlxwTitleEffectText(effects) {',  1, '==', ''),
        ('v2810a·称号效果行函数',            'function YlxwTitleEffectsLine(effects) {', 1, '==', ''),
        ('v2810a·属性作用说明表',            'var YLXW_STAT_HINT = {',                   1, '==', ''),
        ('v2810a·作用说明节点函数',          'function YlxwStatHintEl(key) {',           1, '==', ''),
        ('v2810a·补充属性登记表',            'var YLXW_STAT_EXTRA = [',                  1, '==', ''),
        ('v2810a·补充属性渲染函数',          'function YlxwStatExtraCells(a, b) {',      1, '==', ''),
        ('v2810a·辅助块紧贴 YlxwTTitles 前',
         '}\nfunction YlxwTTitles() {',                                                 1, '==', '顶层同作用域（函数声明提升）'),

        # ---- 任务 A：称号列表（needle 全落注入块内 ⇒ 转义形态） ----
        ('v2810a·称号列表已插入效果行',
         'YlxwTitleEffectsLine(F.effects),' + TITLE_DESC_ANCHOR,                        1, '==', ''),
        ('v2810a·效果行文案「加成：」+ 分隔符「·」',
         r'return parts.length ? ("\u52a0\u6210\uff1a" + parts.join(" \u00b7 ")) : "";',  1, '==', ''),
        ('v2810a·无效果时返回 null(不占位)',
         'return t ? e.jsx("p", { className: "text-xs text-emerald-300 mb-1", children: t }) : null;', 1, '==', ''),
        ('v2810a·标签表覆盖攻击/防御/气血/神识',
         r'attack: "\u653b\u51fb", defense: "\u9632\u5fa1", hp: "\u6c14\u8840", maxHp: "\u6c14\u8840", spirit: "\u795e\u8bc6",', 1, '==', ''),
        ('v2810a·标签表覆盖体魄/速度/幸运/修炼速度',
         r'physique: "\u4f53\u9b44", speed: "\u901f\u5ea6", luck: "\u5e78\u8fd0", expRate: "\u4fee\u70bc\u901f\u5ea6",', 1, '==', ''),
        ('v2810a·标签表覆盖暴击/暴伤',
         r'critRate: "\u66b4\u51fb", critChance: "\u66b4\u51fb", critDamage: "\u66b4\u4f24",', 1, '==', ''),
        ('v2810a·标签表覆盖闪避/命中',
         r'dodgeRate: "\u95ea\u907f", dodge: "\u95ea\u907f", hit: "\u547d\u4e2d",', 1, '==', ''),
        ('v2810a·标签表覆盖吸血/减伤',
         r'lifeLeech: "\u5438\u8840", vampire: "\u5438\u8840", damageReduction: "\u51cf\u4f24",', 1, '==', ''),
        ('v2810a·百分比语义键表(命中/暴击/闪避/吸血)',
         r'dodgeRate: 1, dodge: 1, hit: 1, lifeLeech: 1, vampire: 1,',    1, '==', ''),
        ('v2810a·百分比格式化(小数→%)',
         r'if (YLXW_TEFF_PCT[k]) return lb + " +" + Math.round(v * 100) + "%";',       1, '==', ''),

        # ---- 任务 B-1：作用说明 ----
        ('v2810a·神识说明已挂载',           'children:b.spirit}),YlxwStatHintEl("spirit")',      1, '==', ''),
        ('v2810a·体魄说明已挂载',           'children:b.physique}),YlxwStatHintEl("physique")',  1, '==', ''),
        ('v2810a·速度说明已挂载',           'children:b.speed}),YlxwStatHintEl("speed")',        1, '==', ''),
        ('v2810a·神识文案(法术攻击/防御+行动次数)',
         r'spirit: "\u5f71\u54cd\u6cd5\u672f\u653b\u51fb/\u9632\u5fa1\u4e0e\u884c\u52a8\u6b21\u6570",', 1, '==', ''),
        ('v2810a·体魄文案(气血上限)',        r'physique: "\u5f71\u54cd\u6c14\u8840\u4e0a\u9650",', 1, '==', ''),
        ('v2810a·速度文案(出手顺序/暴击/闪避)',
         r'speed: "\u5f71\u54cd\u51fa\u624b\u987a\u5e8f\u3001\u66b4\u51fb\u4e0e\u95ea\u907f"', 1, '==', ''),
        ('v2810a·说明小字为 10px 灰字',      'className: "text-[10px] text-stone-500 ml-1"',      1, '==', ''),

        # ---- 任务 B-2：补充属性 ----
        ('v2810a·补充属性已展开进面板',      '...YlxwStatExtraCells(a,b)',                        1, '==', ''),
        ('v2810a·命中项已登记',              r'{ k: "hit", label: "\u547d\u4e2d", pct: 1 },',     1, '==', '数据模型缺该字段⇒运行期不渲染'),
        ('v2810a·暴击项已登记',              r'{ k: "critRate", label: "\u66b4\u51fb", pct: 1 },', 1, '==', '数据模型缺该字段⇒运行期不渲染'),
        ('v2810a·闪避项已登记',              r'{ k: "dodgeRate", label: "\u95ea\u907f", pct: 1 },', 1, '==', '数据模型缺该字段⇒运行期不渲染'),
        ('v2810a·吸血项已登记',              r'{ k: "lifeLeech", label: "\u5438\u8840", pct: 1 },', 1, '==', '数据模型缺该字段⇒运行期不渲染'),
        ('v2810a·幸运项已登记',              r'{ k: "luck", label: "\u5e78\u8fd0", pct: 0 }',     1, '==', '玩家真实字段⇒会渲染'),
        ('v2810a·缺字段即跳过(不造假数据)',   'if (v === void 0 || typeof v !== "number" || !isFinite(v)) continue;', 1, '==', ''),
        ('v2810a·补充项按百分比/原值分流',
         r's = d.pct ? (Math.round(v * 100) + "%") : String(v);',                            1, '==', ''),
        ('v2810a·补充项带稳定 key',          'key: "ylxw-x-" + d.k',                              1, '==', ''),

        # ---- 基线未动（只加不改；基座自带文案为**原始中文**） ----
        ('v2810a·基线「已装备」标识保留',     'children:"已装备"',                                  1, '>=', '称号列表原有装备态标识（已解锁/未解锁两区）'),
        ('v2810a·基线「套装可用」标识保留',   'children:"套装可用"',                                1, '>=', ''),
        ('v2810a·基线「点击装备」保留',       'children:"点击装备"',                                1, '>=', ''),
        ('v2810a·基线称号描述行保留',         '{className:"text-xs text-stone-400 mb-1",children:F.description})', 1, '==', '效果行插在它之前'),
        ('v2810a·基线解锁条件行保留',         'children:F.requirement})',                           2, '==', '已解锁+未解锁两处'),
        ('v2810a·基线面板攻击项未动',         'children:b.attack})',                                1, '==', ''),
        ('v2810a·基线面板防御项未动',         'children:b.defense})',                               1, '==', ''),
        ('v2810a·基线面板气血项未动',         'children:[a.hp,"/",b.maxHp]',                        1, '==', ''),
        ('v2810a·基线面板声望项未动',         'children:a.reputation||0})',                         1, '==', ''),
    ]
    return gates
