# -*- coding: utf-8 -*-
r"""
yl_r227_ext.py — R-227「死数据清理：specialAbility 整段」

需求（台账 R-227）
--------------------------------------------------------------------------
  上一轮（R-222）建了「玩家可见值 → 渲染入口」登记表，把 `talent.specialAbility`
  判为**死数据**（`docs/DISPLAY-REGISTRY.md` §13 #D1/#D2）。本轮要求**清理这一段死数据**，
  但必须先分清两种情形：
    (a) 那 2 处 ⭐ 图标判断**仍在渲染** ⇒ 不能直接删字段（否则 ⭐ 消失），
        只能「保留字段 + 显式标注为死数据」或改成不依赖该字段的等价写法；
    (b) 27 处引用**全部**是死路径（含 2 处存在性判断所在分支也不可达）⇒ 才可整段清理。
  纪律（R-222 血的教训）：**动手前必须先用渲染调用点证明目标真的会被渲染**，且要在浏览器里实测。

本会话实测（2026-10-09，线上 bundle index-v2949-20261009.js，
          md5 d8fac7c23951a88c739579726823fb2c，与 https://moyuwang.online/myxxz/ 线上逐字节一致）
--------------------------------------------------------------------------
  ① 全 bundle `specialAbility` 27 处 = 25 处天赋常量定义（表 `Un`，起 @368319）+ 2 处存在性判断。
     `specialAbility.`（属性读取）计数 = **0** ⇒ id/name/description/type/effects/unlockRealm
     全为死载荷，不参与任何结算，其 description 里的数值玩家永远看不到。

  ② 两处存在性判断（唯一消费点，只画 ⭐ lucide-star）：
       · @507859  R-038 注入块 `YlxwR38Card`：
                  `t.specialAbility ? e.jsx(aa,{size:13,...}) : null`
       · @517508  原生 `sw` 卡（`nw` 网格内）：
                  `t.specialAbility&&e.jsx(aa,{size:13,...})`

  ③ **渲染调用点计数（判活/判死）**：
       · `YlxwR38Card` = 定义 1 + 调用 1（在 `YlxwR38TalentStep` 内）；
         `YlxwR38TalentStep` 被建号向导 `rw` 渲染（`rw` 由应用根在
         `!hasSave && (!gameStarted || !player)` 分支渲染）⇒ **活路径**。
       · `nw` 标识符**全 bundle 只出现 1 次**（定义处 @518758），**零调用点**
         —— R-038 已删掉唯一调用点（`yl_r038_ext.py` 门禁「R38·旧天赋池已下线」
         `'e.jsx(nw,{talents:T,selectedIds:d' == 0`）⇒ 原生 `sw` 的 ⭐ 分支**死路径**。

  ④ **线上浏览器实测（决定性证据）**：真实注册临时号 → 走建号向导到「选择你的天赋」步，
     逐个 `svg.lucide-star` 计数：
        round 0 → 0 个；round 1 → 0 个；**round 2 → 2 个**（混沌之体、万劫不灭）；
        **round 3 → 1 个**（万劫不灭）。
     两处命中项都在 25 条带 specialAbility 的名单内（talent-chaos-body / talent-indestructible），
     且卡片文本只显示 name/cost/category/rarity/effects/description，**从不显示 specialAbility 的内容**
     ⇒ ⭐ **确实会渲染**（活路径），而字段载荷**确实不可见**。

决策：选 (a) —— **保留字段，显式标注为死数据**
--------------------------------------------------------------------------
  理由：⭐ 是活路径（线上实测可见），而 25/132 条天赋带 specialAbility ⇒ ⭐ 是有信息量的标记。
  直接删字段/删 25 段数据 = 让这 25 张卡的 ⭐ 消失（玩家可见回退），因此**不做 (b) 整段清理**。
  又因为 25 条是任意子集、无自然等价谓词（rarity/id 前缀都不等价），
  所以也**不改成「不依赖该字段的等价写法」**（会引入新的隐式契约），
  改用「保留字段 + 显式注释标注死数据」——正是 R-222 事故（把死文案当可见文案）的防复发针。

本模块动作（3 处纯注释插入，零逻辑/零数值改动）
--------------------------------------------------------------------------
  A. 天赋表入口 `,Un=[{` 前插死数据标注（中文；该区是 base 字面中文区）；
  B. R-038 活路径 `t.specialAbility ? …` 前插标注（ASCII；该区是 zh() 转义块）；
  C. 原生死路径 `t.specialAbility&&…` 前插标注（中文）。

  注释均以可 grep 的唯一标记 `YLXW_R227_DEADDATA` 起头（A/B/C 各 1 次，合计 3 次）。

硬约束 / 纪律
--------------------------------------------------------------------------
  · **只新建本文件**：不改 build_v26n.py / 产物 / 服务端 / docs/DISPLAY-REGISTRY.md（属 R-222）。
  · 不改任何字段名、不改 25 段数据、不动 2 处存在性判断的字面形态、不动 ⭐ 图标组件 `aa`。
  · 注释里**不得出现** `specialAbility.`（会撞本模块「属性读取 == 0」门禁）、
    `命运点`（撞 R-038 门禁）、`e.jsx(nw,{talents:T,selectedIds:d`（撞 R-038 冻结串）。
  · **接线位置**：必须排在 `V28_MODULES` 的 **r038 之后**（锚点 B 由 r038 注入）。
    与 numbal 无依赖（本模块不碰数值表），排其前后皆可；建议紧随 r038。
  · 锚点唯一性均在本会话对 index-v2949-20261009.js 实测（count 见门禁）。
"""

# --------------------------------------------------------------------------- 锚点

# A：天赋常量表入口（base 原文，唯一）
ANCHOR_TABLE = ',Un=[{'

# B：R-038 活路径（注入块内，唯一；由 r038 生成 ⇒ 本模块必须排其后）
ANCHOR_R38_STAR = ('t.specialAbility ? e.jsx(aa, { size: 13, '
                   'className: "mt-0.5 flex-shrink-0 fill-amber-400 text-amber-400" }) : null')

# C：原生 sw 死路径（base 原文，唯一）
ANCHOR_SW_STAR = ('t.specialAbility&&e.jsx(aa,{size:13,'
                  'className:"mt-0.5 flex-shrink-0 fill-amber-400 text-amber-400"})')

# --------------------------------------------------------------------------- 注释

MARK = 'YLXW_R227_DEADDATA'

NOTE_TABLE = (
    '/*' + MARK + '-TABLE 死数据标注（R-227, 2026-10-09）===== '
    '本表各条的 specialAbility 是【死数据】：'
    '其 id / name / description / type / effects / unlockRealm 全 bundle 属性读取 = 0，不参与任何结算；'
    '其中的数值（如「30%」「15%」）玩家永远看不到。'
    '它唯一的作用 = 下方两处【存在性判断】画一个 ⭐（lucide star）：'
    '(1) YlxwR38Card（本文件注入块内, R-038）→ ★ 活路径：新建角色「选择你的天赋」步真会渲染（线上实测 ⭐ 出现）；'
    '(2) 原生 sw 卡（nw 网格）→ 死路径：nw 的渲染调用点已被 R-038 删除，全 bundle 零调用。'
    '⇒ R-227 决定【保留字段】：直接删除会让活路径的 ⭐ 消失。'
    '⇒ 纪律：不要再把本字段当成「玩家可见文案」来改。 ===== */'
)

NOTE_R38 = (
    '/*' + MARK + '-R38 R-227: this existence test is the ONLY live consumer of the '
    'specialAbility payload (which has 0 property reads); it draws the star. '
    'Keep the field - removing it makes this star disappear. '
    'Do NOT treat its description as player-visible text. */'
)

NOTE_SW = (
    '/*' + MARK + '-SW 死数据标注（R-227）：此处的 specialAbility 存在性判断位于原生 nw 网格组件内；'
    'nw 的渲染调用点已被 R-038 删除（全 bundle 零调用）⇒ 本分支永不执行，⭐ 不会渲染；'
    '保留仅为不改动字面形态。 */'
)


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """把 R-227 死数据标注落到 Patcher 上；返回 gates 列表。"""
    # 前置：本模块必须排在 r038 之后（锚点 B 由 r038 注入）。缺失即报清晰错误，不静默。
    if p.count(ANCHOR_R38_STAR) != 1:
        raise AssertionError(
            '[R-227] 未找到 R-038 活路径锚点（出现 %d 次，期望 1）。'
            '本模块必须排在 V28_MODULES 的 r038 之后。' % p.count(ANCHOR_R38_STAR))

    # A：天赋表入口前插死数据标注
    p.replace('r227-note-table', ANCHOR_TABLE, ',' + NOTE_TABLE + 'Un=[{', expect=1,
              note='R-227：天赋表 Un 入口前标注 specialAbility 为死数据（唯一用途 = 画 ⭐）')

    # B：R-038 活路径前插标注
    p.replace('r227-note-r38', ANCHOR_R38_STAR, NOTE_R38 + ANCHOR_R38_STAR, expect=1,
              note='R-227：R-038 卡 ⭐ 是 specialAbility 的唯一活消费点（载荷为死数据）')

    # C：原生死路径前插标注
    p.replace('r227-note-sw', ANCHOR_SW_STAR, NOTE_SW + ANCHOR_SW_STAR, expect=1,
              note='R-227：原生 sw 卡 ⭐ 分支所在的 nw 零调用，属死路径')

    gates = [
        # ================= 本模块改动（3 处标注就位）=================
        ('R227·死数据标注@天赋表',      MARK + '-TABLE',   1, '==', '天赋表入口注释'),
        ('R227·死数据标注@R38活路径',   MARK + '-R38',     1, '==', '唯一活消费点注释'),
        ('R227·死数据标注@原生死路径',  MARK + '-SW',      1, '==', 'nw 死路径注释'),
        ('R227·标注总数 = 3',           MARK,              3, '==', 'A/B/C 各 1'),
        # ================= 字段本体：一字未删（这就是「保留」的证据）=================
        ('R227·25 条 specialAbility 数据段仍在', '"specialAbility":{', 25, '==', '132 条天赋中 25 条带该字段'),
        ('R227·两处存在性判断仍在',      't.specialAbility', 2, '==', '唯一两个消费点未增未减'),
        ('R227·属性读取仍为 0（载荷确为死数据）', 'specialAbility.', 0, '==', 'id/name/description/effects 全无读取'),
        # ================= 两处 ⭐ 判断字面形态未动 =================
        ('R227·R38 ⭐ 判断字面未动',     ANCHOR_R38_STAR,   1, '==', '活路径：删字段会让它消失'),
        ('R227·原生 ⭐ 判断字面未动',    ANCHOR_SW_STAR,    1, '==', '死路径：保留字面形态'),
        ('R227·⭐ 图标组件仍在',         'aa=Me("star"',    1, '==', 'lucide star，两处判断共用'),
        # ================= 冻结：别人模块的冻结面 / 死路径事实 =================
        ('冻结·天赋表入口未动',          'Un=[{"id":"nt-31"', 1, '==', 'R-038 / talent097 / r132 共同冻结串'),
        ('冻结·fateCost 计数未动',       '"fateCost":',     132, '==', 'talent097 冻结面'),
        ('R227·原生卡 nw 零调用（死路径）', 'e.jsx(nw',      0, '==', 'R-038 已删唯一调用点'),
        ('冻结·R-038「命运点」仍为 0',    '命运点',          0, '==', '本模块注释不得引入该词'),
    ]
    return gates
