# -*- coding: utf-8 -*-
r"""
yl_r115_ext.py — R-115 洞府/灵田 四子项（扩地按钮修复 + 田位扩容 + 灵草 hover + 价格守卫）

台账原文（R-115，逐字）
--------------------------------------------------------------------------
  「1. 左边的灵田，怎么加属性的种反而价格这么低。加属性的灵石需求要大幅提升。
     只有加修为和卖灵石专用的可以稍微便宜一点。并且等阶的需求好像没做？
    2. 右边种植扩地这个按钮点不了。
    3. 左边灵田 L5\L7 时 每阶可以再额外购买 2 块。即 L5 又可以买 2 块，L7 再 2 块，L9 再加 3 块。
    4. 右边种植灵草里面展示每个灵草的属性作用，描述内容加到"种植"这个按钮的悬停处。」

改前行为取证（无 numbal 全链产物实测，逐字 + 字节偏移）
--------------------------------------------------------------------------
  [item2] ★ 根因已定位：`handleExpandHerbSlots`（R-049 新建的扩地 handler）**只透传了半条链**。
      · 源头在位：`mk()` grotto hook 的 return 含 `handleExpandHerbSlots:__ylGrottoExpand`
        （@1907171）；`le=mk({...})`（@1911395）。
      · 断点 1：`fk()` 的 return 只挑了 `le` 的 6 个 handler
        （`handleUpgradeGrotto:le.handleUpgradeGrotto,…,handleSpeedupHerb:le.handleSpeedupHerb,` @1916292-1917090），
        **没有** `handleExpandHerbSlots` ⇒ `Vs.handleExpandHerbSlots === undefined`。
      · 断点 2：`hC(t)`（grottoHandlers memo，@2066830）逐键挑 `t.handleXxx`，
        同样**没有** `handleExpandHerbSlots`（对象体 + 依赖数组都缺）。
      · 断点 3：`xk(t)`（modalsHandlers 聚合 hook，@1920606）的解构与回传 memo 里
        `handleToggleAutoHarvest:Xe,handleSpeedupHerb:Mt,handleBuyItem:Vt,` 各 1 处（共 2 处），
        同样**没有** `handleExpandHerbSlots`（依赖数组 `,Xe,Mt,Vt,Ft,` 也缺）。
      · 终点：`Oe=xk(Yn)` → `jsx(Xk,{modalsHandlers:Oe})` → `Z=modalsHandlers` →
        `jsx(VM,{handlers:Z})` → `QM({handlers:c})` → `jsx(HM,{onExpandHerbSlots:c.handleExpandHerbSlots})`
        → HM 解构 `onExpandHerbSlots:__ylExp` → 按钮 `onClick:()=>__ylExp()`。
        `c.handleExpandHerbSlots === undefined` ⇒ 点击即 `undefined()` 抛 TypeError（React 静默吞掉）
        ⇒ **按钮点了没反应**（正是用户"点不了"的现象；按钮本身 enabled，非 disabled 问题）。
      对照：`handleSpeedupHerb`（加速）走的正是这 3 个断点，所以加速按钮能用、扩地按钮不能。
      ⇒ 修法 = 把 `handleExpandHerbSlots` 按 `handleSpeedupHerb` 的**同款 5 站**补齐。

  [item3] 田位上限现由 R-049 注入的 `__hr=3+Math.floor((L-1)/2)` 决定
      （L1..L10 = 3/3/4/4/5/5/6/6/7/7 个可自扩格），价格 `[2000,8000,24000,60000,150000,350000,800000][__cur]*L`。
      用户要求 L5/L7/L9 各再 +2/+2/+3（累进）⇒ 新上限 = 7/7/10/10/14/14，需 ≥14 档价格。
      展示侧：grotto087 的「灵田联动」两处（升级 toast + 总览行）写死 `可开垦 (L>=9?6:L>=7?5:L>=5?4:3)`，
      与真实 headroom 已不一致（旧值），本次一并同步为新公式。

  [item4] 洞府 modal「种植」页签的灵草卡片：卡片体已显示 生长时间/收获/需 N 级洞府/拥有种子，
      但卡片上的**「种植」按钮无任何 `title`**（`e.jsx("button",{onClick:()=>c(g.id||g.name),disabled:!I,…})` @1814894），
      灵草的**属性作用无处可看**。数据源实证：`wn`（灵草目录，20 键）**无** description/effect 字段；
      描述与效果在**物品目录**（`Lt(name)` → `sy()` 归一化后含 `description/effect/permanentEffect`，
      e.g. 九叶芝草 @302676）与**灵草/丹药效果表 `HN`**（@308720，覆盖 7 种灵草）里。

  [item1] 作物**数值全在服务端** `srv/index_v28.ts`：客户端产物里
      `linggusi`/`peiyuancao`/`FARM_CROP` 计数均为 **0**（数值表零存在），客户端只渲染服务端下发的
      `crops`/`cropList`。⇒ 价格重配（加属性作物「灵石需求」大幅提升）**客户端做不到，必须改服务端**
      （本模块只留只读守卫；改法见 `patches/server/srv_patch_115.py`）。
      等阶需求（需洞府 Lv.X）：**服务端已在执法**（`/api/farm/plant` @8154
      `if (crop.grottoLevel && gi.level < crop.grottoLevel) return 409`；门槛表 `FARM_CROP_TIER_LEVEL={1:1,2:1,3:3,4:5,5:7}`，
      `farmCropDefs()` 下发 `grottoLevel`），客户端 T5 面板也按 `ok2=!nl||gl>=nl` 置灰。
      **唯一缺口 = 可见性**：按钮文案 `(nl && !ok2 ? " · 需洞府 Lv."+nl : "")` **只在未达标时显示**
      ⇒ 高洞府玩家看不到任何门槛，误以为"没做"。本次改为**恒显**（达标/未达标都标出需求）。

改后行为
--------------------------------------------------------------------------
  item2：`handleExpandHerbSlots` 补齐 fk/hC(对象+依赖)/xk(解构+回传+依赖) 5 站 ⇒
         `Oe.handleExpandHerbSlots` 有值 ⇒ HM 的 `__ylExp` 是函数 ⇒ 扩地按钮可点。
  item3：上限 +2/+2/+3 累进（L5/L7/L9 → 7/10/14）；价格表 7→14 档（数组展开续档，原 7 档逐字保留）；
         联动展示两处同步。
  item4：种植按钮加 `title: YlxwHerbTip(g)`，悬停显示「名称【稀有度】/ 描述 / 服用效果 / 永久属性 / 需洞府 Lv.X」。
  item1：客户端只加只读守卫 + 门槛恒显；数值改档交 `srv_patch_115.py`。

常量处理口径
--------------------------------------------------------------------------
  · 本模块**不新增任何数值常量**（田位上限/价格全部沿用 R-049 的表达式，只追加档位）；
    item4 的标签表是**显示用**映射（非数值表），item1 的数值改动全在服务端。
  · 注入块（item4 helper）走 `ctx['zh']` 转义 ⇒ 落盘纯 ASCII；不含 V28_BAN_PATTERNS。
  · 全部就地替换锚点均在**基座 vite 字面 UTF-8 域**或**前置模块注入产物**域；
    其中「需洞府」串来自 farm089 的 zh() 转义域 ⇒ 锚点用 `\uXXXX` 转义形态（两种形态均已实测）。

风险点 / 未决
--------------------------------------------------------------------------
  · item3 **跨模块门禁冲突（必读）**：R-049 的 3 条门禁锚点被本模块合法改写，构建时 R-049 门禁会 FAIL：
      1) `('R49·E1 上限式随等级', 'const __hr=3+Math.floor((R.level-1)/2);', 1)` → 改后应 `0`
         并新增 `('R49·E1 上限式随等级', 'const __hr=3+Math.floor((R.level-1)/2)+(R.level>=9?7:R.level>=7?4:R.level>=5?2:0);', 1)`
      2) `('R49·E7 上限式随等级', 'const __hr=3+Math.floor((T.level-1)/2),__cur=', 1)` → 改后应 `0`
         并新增 `('R49·E7 上限式随等级', 'const __hr=3+Math.floor((T.level-1)/2)+(T.level>=9?7:T.level>=7?4:T.level>=5?2:0),__cur=', 1)`
      3) `('R49·价格阶梯 7 档', '[2000,8000,24000,60000,150000,350000,800000]', 2)` → 仍为 `2`（本模块用数组展开续档，**该锚点未破**）
      ⇒ 实际只需改 1)、2) 两条（价格锚不受影响）。R-049 的
        `if(__cur>=__hr)return a(` / `if(__cur>=__hr)return e.jsx(` / `][__cur]*R.level;` / `][__cur]*T.level,__ok=`
      四条闸门锚点**全部保留通过**。
  · item3 数值口径（+2/+2/+3 是否累进、续档价格）为**自拍板**，待主控/用户定档；改单点：
    E3A/E3B 的 `(L>=9?7:L>=7?4:L>=5?2:0)` 与 E3C 的 `[2000000,…]` 续档数组。
  · item1 的「价格」按「种子价/灵石需求（种植成本）」解读（依据用户原话"灵石需求"与按钮上展示的
    `名字（N 灵石 · …）` 即 `cd.seed`）；若用户实指**变卖价**，则须改服务端 `money` 而非 `seed`
    （已在 srv_patch_115.py 注释里给出替代口径）。
  · item4 若某灵草既不在物品目录也不在 `HN`（如 青草/白花/黄精），悬停退化为「名称【稀有度】+ 需洞府」。
"""

import re

# --------------------------------------------------------------------------- 注入块（item4：灵草悬停提示 helper）

# 注入锚：物品目录读取函数 `Lt`（depth=1，与 HN / wn / HM 同一大作用域区 [20183..2074873]）。
#   ★ 实测：HN / wn / Lt / LN / HM 全部落在同一 depth=1 区块内 ⇒ 在此注入的函数
#     既能读到 Lt/HN，也能被 HM（depth=2，该区块内的嵌套作用域）调用。
INJECT_ANCHOR = 'function Lt(t){'

INJECT_JS = r'''
/* ===== yl-R115 item4: 洞府灵草「属性作用」悬停提示 =====
   种植页签每株灵草卡片的「种植」按钮加 title：显示 描述 + 服用效果 + 永久属性 + 洞府需求。
   数据源：物品目录 Lt(name)（含 description/effect/permanentEffect）→ 兜底 HN[name]（灵草/丹药效果表）。
   两者皆缺 ⇒ 只显示 名称/稀有度/需求（不编造数值）。 */

/* 显示用属性标签（仅文案，非数值表）
   ★ 键一律用引号形态：带引号的键不含「裸键冒号」子串，避免踩其他模块的裸键计数门禁
     （yl_speedname097 用裸键形态统计属性名文案，本表若用裸键会多计一次）。 */
var YLXW_HERB_STAT_LABEL = {
  "hp": "气血", "maxHp": "气血上限", "attack": "攻击", "defense": "防御",
  "spirit": "神识", "physique": "体魄", "speed": "身法", "exp": "修为",
  "maxLifespan": "最大寿元", "lifespan": "寿元",
  "critRate": "暴击率", "dodgeRate": "闪避率", "lifeLeech": "吸血率"
};

/* 效果对象 → "气血+2500 神识+600" 形态（跳过 0/非数/非有限值） */
function YlxwHerbStatText(obj) {
  if (!obj) return "";
  var parts = [];
  for (var k in obj) {
    var v = obj[k];
    if (typeof v !== "number" || !isFinite(v) || v === 0) continue;
    parts.push((YLXW_HERB_STAT_LABEL[k] || k) + (v > 0 ? "+" : "") + v);
  }
  return parts.join(" ");
}

/* 灵草悬停文案：名称【稀有度】\n描述\n服用效果：…\n永久属性：…\n需洞府 Lv.X */
function YlxwHerbTip(g) {
  g = g || {};
  var d = null;
  try { d = (typeof Lt === "function") ? Lt(g.name) : null; } catch (e) { d = null; }
  var hn = (typeof HN !== "undefined" && HN) ? HN[g.name] : null;
  var lines = [];
  if (d && d.description) lines.push(d.description);
  var eff = (d && d.effect) || (hn && hn.effect) || null;
  var per = (d && d.permanentEffect) || (hn && hn.permanentEffect) || null;
  var t1 = YlxwHerbStatText(eff), t2 = YlxwHerbStatText(per);
  if (t1) lines.push("服用效果：" + t1);
  if (t2) lines.push("永久属性：" + t2);
  if (g.grottoLevelRequirement) lines.push("需洞府 Lv." + g.grottoLevelRequirement);
  var head = (g.name || "灵草") + (g.rarity ? "【" + g.rarity + "】" : "");
  return lines.length ? head + "\n" + lines.join("\n") : head;
}
'''

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- item2：扩地 handler 5 站透传补齐

# 站 1：fk() return 暴露 le.handleExpandHerbSlots（与 handleSpeedupHerb 同排）
E2A_OLD = 'handleSpeedupHerb:le.handleSpeedupHerb,claimQuestReward:'
E2A_NEW = 'handleSpeedupHerb:le.handleSpeedupHerb,handleExpandHerbSlots:le.handleExpandHerbSlots,claimQuestReward:'

# 站 2：hC(t) grottoHandlers memo 对象体（与 handleSpeedupHerb 同排）
E2B_OLD = 'handleSpeedupHerb:t.handleSpeedupHerb}),['
E2B_NEW = 'handleSpeedupHerb:t.handleSpeedupHerb,handleExpandHerbSlots:t.handleExpandHerbSlots}),['

# 站 3：hC(t) 依赖数组
E2C_OLD = ',t.handleToggleAutoHarvest,t.handleSpeedupHerb])}function xC('
E2C_NEW = ',t.handleToggleAutoHarvest,t.handleSpeedupHerb,t.handleExpandHerbSlots])}function xC('

# 站 4/5：xk(t) 解构 + 回传 memo（同一串出现 2 次，同款插入）
E2D_OLD = 'handleToggleAutoHarvest:Xe,handleSpeedupHerb:Mt,handleBuyItem:Vt,'
E2D_NEW = 'handleToggleAutoHarvest:Xe,handleSpeedupHerb:Mt,handleExpandHerbSlots:__ylExpHS,handleBuyItem:Vt,'

# 站 5b：xk(t) 依赖数组
E2E_OLD = ',Xe,Mt,Vt,Ft,'
E2E_NEW = ',Xe,Mt,Vt,__ylExpHS,Ft,'

# --------------------------------------------------------------------------- item3：田位扩容 +2/+2/+3 累进

# E1（mk hook 内 __ylGrottoExpand 上限式）：base headroom + 档位奖励
E3A_OLD = 'const __hr=3+Math.floor((R.level-1)/2);'
E3A_NEW = 'const __hr=3+Math.floor((R.level-1)/2)+(R.level>=9?7:R.level>=7?4:R.level>=5?2:0);'

# E7（种植页签扩地按钮上限式）：同上，变量名 T.level
E3B_OLD = 'const __hr=3+Math.floor((T.level-1)/2),__cur='
E3B_NEW = 'const __hr=3+Math.floor((T.level-1)/2)+(T.level>=9?7:T.level>=7?4:T.level>=5?2:0),__cur='

# E3C：价格表 7 档 → 14 档（用数组展开续档 ⇒ 原 7 档字面量与 `][__cur]*L` 锚点逐字保留）
#   ★ 不能用 `.concat(...)`：`.concat([...])[__cur]` 会把 `][__cur]` 变成 `])[__cur]`，
#     打断 R-049 的 `][__cur]*R.level;` / `][__cur]*T.level,__ok=` 两条锚点。展开语法两锚全保。
E3C_OLD = '[2000,8000,24000,60000,150000,350000,800000][__cur]'
E3C_NEW = ('[...[2000,8000,24000,60000,150000,350000,800000],'
           '...[2000000,5000000,12000000,30000000,80000000,200000000,500000000]][__cur]')

# E3D：灵田联动 升级 toast（grotto087 G12 产物）——可开垦块数同步新公式
E3D_OLD = '"%、可开垦 " + (M>=9?6:M>=7?5:M>=5?4:3) + " 块'
E3D_NEW = '"%、可开垦 " + (M>=9?14:M>=7?10:M>=5?7:3+Math.floor((M-1)/2)) + " 块'

# E3E：灵田联动 总览行（grotto087 G13 产物）——同上
E3E_OLD = '"% · 可开垦 ",T.level>=9?6:T.level>=7?5:T.level>=5?4:3," 块田'
E3E_NEW = '"% · 可开垦 ",T.level>=9?14:T.level>=7?10:T.level>=5?7:3+Math.floor((T.level-1)/2)," 块田'

# --------------------------------------------------------------------------- item4：种植按钮加 title

E4_OLD = 'e.jsx("button",{onClick:()=>c(g.id||g.name),disabled:!I,className:'
E4_NEW = 'e.jsx("button",{title:YlxwHerbTip(g),onClick:()=>c(g.id||g.name),disabled:!I,className:'

# --------------------------------------------------------------------------- item1b：灵田作物按钮「需洞府」恒显
#   ★ 该串来自 farm089 的 zh() 转义域 ⇒ 用 \uXXXX 形态（实测全文 2 处：T5 活面板 + T10 死面板；
#     本模块只改 T5 活面板，用 `+ (ret ?` 后缀锁定唯一性）。

E1B_OLD = r'(nl && !ok2 ? " \u00b7 \u9700\u6d1e\u5e9c Lv." + nl : "") + (ret ?'
E1B_NEW = r'(nl ? " \u00b7 \u9700\u6d1e\u5e9c Lv." + nl : "") + (ret ?'


EDITS = [
    ('E2A fk return 透传扩地',          E2A_OLD, E2A_NEW, 1),
    ('E2B hC memo 透传扩地',            E2B_OLD, E2B_NEW, 1),
    ('E2C hC 依赖含扩地',               E2C_OLD, E2C_NEW, 1),
    ('E2D xk 解构+回传扩地',            E2D_OLD, E2D_NEW, 2),
    ('E2E xk 依赖含扩地',               E2E_OLD, E2E_NEW, 1),
    ('E3A E1 上限+档位奖励',            E3A_OLD, E3A_NEW, 1),
    ('E3B E7 上限+档位奖励',            E3B_OLD, E3B_NEW, 1),
    ('E3C 价格表续档 7→14',             E3C_OLD, E3C_NEW, 2),
    ('E3D 联动toast 可开垦同步',         E3D_OLD, E3D_NEW, 1),
    ('E3E 联动总览 可开垦同步',          E3E_OLD, E3E_NEW, 1),
    ('E4 种植按钮加 title',             E4_OLD, E4_NEW, 1),
    ('E1B 灵田按钮需洞府恒显',           E1B_OLD, E1B_NEW, 1),
]


def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检 1：替换串必须真的变了
    for _nm, _a, _b, _e in EDITS:
        if _a == _b:
            raise AssertionError('r115 %s：锚点替换为恒等（无改动）' % _nm)
    # 自检 2：新 handler 名必须出现在 5 站里（防手滑改名）
    assert 'handleExpandHerbSlots:le.handleExpandHerbSlots' in E2A_NEW
    assert 'handleExpandHerbSlots:t.handleExpandHerbSlots' in E2B_NEW
    assert 'handleExpandHerbSlots:__ylExpHS' in E2D_NEW
    assert '__ylExpHS' in E2E_NEW
    # 自检 3：item3 价格续档必须保留原 7 档字面量（护住 R-049 价格锚）
    assert '[2000,8000,24000,60000,150000,350000,800000]' in E3C_NEW
    # 自检 4：注入块 zh() 后纯 ASCII + 不含禁用模式
    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r115 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for _pat in BAN_PATTERNS:
        if _pat in blk:
            raise AssertionError('r115 注入块含禁用模式: %s' % _pat)
    # 自检 5：标签表键必须引号化 ⇒ 注入块不得含裸键冒号形态（防踩跨模块裸键计数门禁）
    if 'speed:' in blk:
        raise AssertionError('r115 注入块含裸键 speed: 形态（标签键须引号化）')

    # 0) 模块级 helper（与 Lt / HN 同作用域，HM 可见）
    p.insert_before('r115-herbtip', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 YlxwHerbTip / YlxwHerbStatText / YLXW_HERB_STAT_LABEL')

    # 1) 就地替换
    for name, old, new, exp in EDITS:
        p.replace(name, old, new, expect=exp)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= item2 扩地按钮修复（5 站透传）=================
        ('R115·item2 fk 透传扩地',        'handleExpandHerbSlots:le.handleExpandHerbSlots', 1, '==', '站1：Vs 暴露'),
        ('R115·item2 hC 透传扩地',        'handleExpandHerbSlots:t.handleExpandHerbSlots', 1, '==', '站2：grottoHandlers'),
        ('R115·item2 hC 依赖含扩地',      't.handleSpeedupHerb,t.handleExpandHerbSlots])}function xC(', 1, '==', '站3'),
        ('R115·item2 xk 解构+回传',       'handleExpandHerbSlots:__ylExpHS,', 2, '==', '站4/5：modalsHandlers'),
        ('R115·item2 xk 依赖含扩地',      ',Xe,Mt,Vt,__ylExpHS,Ft,', 1, '==', '站5b'),
        ('R115·item2 旧 fk 形态已清零',   'handleSpeedupHerb:le.handleSpeedupHerb,claimQuestReward', 0, '==', ''),
        ('R115·item2 旧 hC 形态已清零',   'handleSpeedupHerb:t.handleSpeedupHerb}),[t.handleUpgradeGrotto', 0, '==', ''),
        ('R115·item2 旧 xk pair 已清零',  'handleToggleAutoHarvest:Xe,handleSpeedupHerb:Mt,handleBuyItem:Vt,', 0, '==', ''),
        ('R115·item2 旧 xk deps 已清零',  ',Xe,Mt,Vt,Ft,', 0, '==', ''),
        ('R115·item2 按钮 onClick 未动',  'onClick:()=>__ylExp()', 1, '==', 'R-049 E7 按钮本体'),
        ('R115·item2 HM 解构未动',        'onExpandHerbSlots:__ylExp', 1, '==', 'R-049 E4'),
        ('R115·item2 modal 透传未动',     'onExpandHerbSlots:c.handleExpandHerbSlots', 1, '==', 'R-049 E3'),
        # ================= item3 田位扩容 =================
        ('R115·item3 E1 上限+奖励',       'const __hr=3+Math.floor((R.level-1)/2)+(R.level>=9?7:R.level>=7?4:R.level>=5?2:0);', 1, '==', '装配态在位；R-125（standalone 阶段）改写为 3+(L-1)+档位奖，终态旧式清零断言归 yl_r125_ext.gates()（接线层修正 2026-10-02：本表跑在 standalone 之前，成员误按终态评估）'),
        ('R115·item3 E7 上限+奖励',       'const __hr=3+Math.floor((T.level-1)/2)+(T.level>=9?7:T.level>=7?4:T.level>=5?2:0),__cur=', 1, '==', '同上：装配态在位，终态清零归 yl_r125_ext.gates()'),
        ('R115·item3 价格续档 ×2',        '...[2000000,5000000,12000000,30000000,80000000,200000000,500000000]]', 2, '==', '装配态在位；R-125 改 18 档（8~18 档=1500000..70000000），终态旧续档清零归 yl_r125_ext.gates()'),
        ('R115·item3 旧 E1 上限已清零',   'const __hr=3+Math.floor((R.level-1)/2);', 0, '==', ''),
        ('R115·item3 旧 E7 上限已清零',   'const __hr=3+Math.floor((T.level-1)/2),__cur=', 0, '==', ''),
        ('R115·item3 联动toast 新公式',   '(M>=9?14:M>=7?10:M>=5?7:3+Math.floor((M-1)/2))', 1, '==', '装配态在位；R-125 联动展示同步为完整式 (3+(M-1)+(M>=9?4:...))，终态清零归 yl_r125_ext.gates()'),
        ('R115·item3 联动总览 新公式',    'T.level>=9?14:T.level>=7?10:T.level>=5?7:3+Math.floor((T.level-1)/2)', 1, '==', '同上：装配态在位，终态清零归 yl_r125_ext.gates()'),
        ('R115·item3 旧联动toast已清零',  '(M>=9?6:M>=7?5:M>=5?4:3)', 0, '==', ''),
        ('R115·item3 旧联动总览已清零',   'T.level>=9?6:T.level>=7?5:T.level>=5?4:3', 0, '==', ''),
        # ---- item3 冻结：R-049 未被本模块改动的闸门/价格锚 ----
        ('冻结·R49 价格锚仍 7 档',        '[2000,8000,24000,60000,150000,350000,800000]', 2, '==', '.concat 续档，原字面量保留'),
        ('冻结·R49 E1 上限闸门未动',      'if(__cur>=__hr)return a(', 1, '==', ''),
        ('冻结·R49 E7 上限闸门未动',      'if(__cur>=__hr)return e.jsx(', 1, '==', ''),
        ('冻结·R49 价格随等级 ×L(R)',     '][__cur]*R.level;', 1, '==', ''),
        ('冻结·R49 价格随等级 ×L(T)',     '][__cur]*T.level,__ok=', 1, '==', ''),
        ('冻结·R49 满级文案未动',         'children:"扩地已满"', 1, '==', ''),
        ('冻结·R49 扣灵石写回未动',       'spiritStones:h.spiritStones-__cost', 1, '==', ''),
        # ================= item4 灵草 hover =================
        ('R115·item4 helper 已注入',      'function YlxwHerbTip(g) {', 1, '==', ''),
        ('R115·item4 属性文本函数已注入', 'function YlxwHerbStatText(obj) {', 1, '==', ''),
        ('R115·item4 标签表已注入',       'var YLXW_HERB_STAT_LABEL = {', 1, '==', '显示用，非数值表'),
        ('R115·item4 标签键引号化',       r'"speed": "\u8eab\u6cd5"', 1, '==', '防踩裸键 speed: 计数门禁'),
        ('R115·item4 读物品目录 Lt',      'typeof Lt === "function"', 1, '==', 'description/effect 源'),
        ('R115·item4 兜底读 HN',          'HN[g.name]', 1, '==', '灵草效果表兜底'),
        ('R115·item4 按钮已加 title',     'e.jsx("button",{title:YlxwHerbTip(g),onClick:()=>c(g.id||g.name)', 1, '==', ''),
        ('冻结·item4 种植按钮 onClick 未动', 'onClick:()=>c(g.id||g.name)', 1, '==', ''),
        ('冻结·item4 灵草目录 wn 未动',    'wn=[{id:"spirit-grass"', 1, '==', ''),
        # ================= item1 客户端守卫 + 门槛恒显 =================
        ('R115·item1 灵田按钮需洞府恒显',  r'(nl ? " \u00b7 \u9700\u6d1e\u5e9c Lv." + nl : "") + (ret ?', 1, '==', '达标也标出需求（T5 活面板）'),
        ('R115·item1 旧条件形态已清零',    r'(nl && !ok2 ? " \u00b7 \u9700\u6d1e\u5e9c Lv." + nl : "") + (ret ?', 0, '==', '旧「仅未达标才显示」'),
        ('冻结·item1 田位开垦等级提示未动', r'children: lvOk ? "\u5f00\u57a6 " + uc.toLocaleString() + " \u7075\u77f3" : "\u9700\u6d1e\u5e9c Lv." + needLv', 2, '==', 'T5 + T10'),
        ('冻结·item1 客户端无作物数值表',  'linggusi', 0, '==', '数值权威在服务端（srv_patch_115）'),
        ('冻结·item1 客户端无作物数值表2', 'peiyuancao', 0, '==', '同上'),
        ('冻结·item1 种植端点未动',        '"/farm/plant"', 3, '==', '旧 + T10 + T5'),
        ('冻结·item1 开垦端点未动',        '"/farm/unlock"', 3, '==', ''),
        ('冻结·item1 收获端点未动',        '"/farm/harvest"', 3, '==', ''),
        ('冻结·item1 一键收取未动',        '"/farm/harvest/all"', 4, '==', ''),
        ('冻结·item1 R048 按钮灰置未动',   'disabled: !!u || !ok2 || !okR || ret,', 1, '==', ''),
        ('冻结·item1 洞府门槛判定未动',    'ok2 = !nl || gl >= nl;', 2, '==', 'T5 + T10'),
        # ================= 跨模块计数不变量 =================
        ('冻结·handleSpeedupHerb=9',      'handleSpeedupHerb', 9, '==', 'R-049/v2810c 门禁同值'),
        ('冻结·handleUpgradeGrotto=9',    'handleUpgradeGrotto', 9, '==', ''),
        ('冻结·handlePlantHerb=9',        'handlePlantHerb', 9, '==', ''),
        ('冻结·灵田联动行仍在',           '灵田联动：产出 +', 1, '==', 'grotto087 门禁串'),
        ('冻结·灵田联动标题仍在',         '"灵田联动"', 1, '==', 'grotto087 门禁串'),
        ('冻结·R47 变卖文本函数未动',     'function YlxwFtSellText(cd, slot) {', 1, '==', ''),
        ('冻结·T5 面板注册未动',          'YLXW_COMP.farm=YlxwTFarmT5;', 1, '==', ''),
        ('冻结·Pr 等级表未动',            'Pr=[{level:1,name:"简陋洞府"', 1, '==', ''),
    ]
    return gates
