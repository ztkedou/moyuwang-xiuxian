# -*- coding: utf-8 -*-
r"""
yl_049_ext.py — R-049 洞府：灵草种植区花灵石手动扩充（上限按洞府等级，简陋洞府最多 4 块）

需求（台账 R-049，无附图）
--------------------------------------------------------------------------
  「自带的灵草种植区域，可以手动花灵石扩充，总数量根据洞府等级来定，
    最基础的简陋洞府可以最大扩充到 4 个，以此为基础增加。」

现状（bundle index-v28113 实测）
--------------------------------------------------------------------------
  槽位是「纯静态」的：`Pr` 等级表每级带 maxHerbSlots（1/2/3/4/5/6/8/10/12/15），
  全部消费点直接读配置 —— 玩家**没有任何**「花灵石买槽位」的途径，想多种只能升洞府
  （5000 → 2e4 → 8e4 → 25e4 …）。即：需求里的「手动扩充」机制目前不存在，要新建。

设计（对齐 0.8.7 聚灵阵改造 spiritArrayEnhancement 的既有房屋模式）
--------------------------------------------------------------------------
  · 新持久子字段 `grotto.extraSlots`（已购扩地数）。服务端 `/api/save` 对 grotto
    对象**整体透传**（srv/index_v28.ts 注释：「tower/grotto 是会被完整透传的两个」；
    全文 0 处 plantedHerbs/maxHerbSlots 白名单校验）⇒ **无需 srv_patch**，
    老存档缺字段一律 `||0` 兜底（与 spiritArrayEnhancement 完全同款）。
  · 有效槽位 = `Pr[level].maxHerbSlots + (grotto.extraSlots||0)`。
    ★ 2026-10-01 用户新口径返工（上一版「上限 = 基础 + 3」作废）：
      基础槽位 = `Pr` 表默认值，买/升级给的就是默认值，**一字不动**（1/2/3/4/5/6/8/10/12/15）；
      可扩建上限 **headroom(L) = 3 + floor((L-1)/2)**，即「上限(L) = 基础(L) + headroom(L)」：
        L1  简陋洞府 1 → 上限 4（多出的 3 格须玩家花灵石自扩，满足用户明确口径）
        L2  普通洞府 2 → 5     L3 精良 3 → 7     L4 上等 4 → 8     L5 优质 5 → 10
        L6  极品 6 → 11        L7 仙品 8 → 14    L8 天品 10 → 16   L9 圣品 12 → 19
        L10 神品 15 → 22
      headroom 单调不减（恒 ≥3）⇒ 升级洞府只会**放宽**可扩格数、绝不会缩回已扩格，
      故「扩得的地跨洞府等级保留」天然成立（升级缩水检查仍保留作安全网）。
      上限恒 > 基础（headroom>0）⇒ 不存在「上限低于默认槽位、升级反而变差」的坑。
  · 价格：**第 k 格 = P[k-1] × 洞府等级 L**，
      P = [2000, 8000, 24000, 60000, 150000, 350000, 800000]（7 档，覆盖 L10 的 7 格）。
      L1 时 = 2000/8000/24000（与上一版完全一致 ⇒ 低等级玩家零体感变化）；
      高等级随 L 与格序同步抬升，避免满级把「扩地」当廉价刷格（L10 第 1 格 = 2 万）。
  · 入口：种植页签右上「已种植 X / Y」徽章旁加「➕ 扩地」按钮（满级变灰字、
      灵石不足置灰）；新 handler `handleExpandHerbSlots` 走 hook 返回表 →
      modal props → HM 解构，与 handleSpeedupHerb 等完全同一条透传链。

数值地图（本模块动的 11 处 / 不动的 N 处）
--------------------------------------------------------------------------
  动：E1 hook 加 handler+导出；E3 modal 透传；E4 HM 解构；E5 T 默认 grotto 补
      extraSlots:0；E6 总览「种植槽位」卡（显示+已满判定）；E7 种植页签徽章+
      扩地按钮；E8 灵草卡片可种判定；E9 面板 R useMemo 槽位 D；E10 升级时
      「缩水移除」判定 k；E11 种植动作满槽拦截（文案同步提扩地）。
  不动（冻结）：Pr 等级表、升级页每级槽位预览 `children:g.maxHerbSlots`、升级
      toast 基础槽位 `种植槽位 ${N.maxHerbSlots} 个`、灵田联动行、聚灵阵改造、
      handleSpeedupHerb（R-050 的面）。

纪律 / 邻接需求边界
--------------------------------------------------------------------------
  · R-046/047/048（仙务·灵田变卖/服用/品种）与 R-050（加速一次半小时/催熟次数）
    的可变面（YLXW_COMP.farm、变卖/服用文案、Br={dailyLimit…}、加速费用公式串）
    **一律不进我的冻结门禁** —— 它们是并行批次的合法改动面，冻了会假 FAIL 打爆构建；
    我只冻「并行批不会动」的结构不变量（Pr 表 / handler 标识符计数 / grotto087 产物）。
  · 与 yl_v2810c_ext.py（加速改小时数，B_MAP 锚 `T.plantedHerbs.map((g,q)=>…`）、
    yl_grotto087_ext.py（G14 收获兜底 `plantedHerbs:E`）零文本交集（已逐一比对）。
  · 本模块 INJECT_JS 为空：新 handler 必须活在 grotto hook 闭包内（r/a/l/c/d），
    全部为就地替换，锚点区是基座 vite 字面 UTF-8 域（勿转 \u，同 grotto087）。
  · 注入块禁词自查：无 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-。
  · 不改 build_v26n.py / localtest/ / deploy_v28/ / srv/index_v28.ts / CHANGELOG.md。

门禁计数口径（干跑实测于 index-v28113-20260930，1977241 字符基面）
--------------------------------------------------------------------------
  maxHerbSlots：改前 20（Pr 定义 10 + 消费点 10）→ 改后 24（E1 handler 消息 +4：
    上限消息 2 + 成功消息 2，其余 9 处替换全部原样保留子串）；
    extraSlots 改后 12（E5 默认 1 + 消费/写回 11，其中 E7 徽章+守卫各 1）；
    handleUpgradeGrotto / handleSpeedupHerb / handlePlantHerb 等 handler 标识符
    计数一律 9 不变（E1 只在 return 表**追加**键，不增减既有键）。
  ★ 2026-10-01 返工（上限梯度 + 价格阶梯）：只改 E1/E7 内部的两条表达式
    （上限闸门 `Math.min(3,…)` → `Math.min(__hr,…)`；价格 `[3 档]` → `[7 档]×L`），
    **不新增任何符号 / 键** ⇒ 上述全部计数不变。新增门禁：
      __hr 上限式 ×2、价格阶梯串 ×2、`×L` 写法 ×2；
      旧形态清零：`Math.min(3,Math.floor(Number(R/T.extraSlots)`、`[2000,8000,24000][__cur]`、
      `if(__cur>=3)`。
"""

import re

# 本模块无模块级注入块（handler 需 grotto hook 闭包变量，全部就地替换）
INJECT_JS = ''

# --------------------------------------------------------------------------- E1 hook：新 handler + 导出

E1_OLD = 'N};return{handleUpgradeGrotto:v,handlePlantHerb:m,'
E1_NEW = (
    'N};const __ylGrottoExpand=()=>{r(h=>{const R=h.grotto||c();'
    'if(R.level===0)return a("请先购买洞府才能扩充灵草种植区。","danger"),'
    'l&&l({text:"请先购买洞府才能扩充灵草种植区。",type:"danger"}),h;'
    'const E=d(R.level);if(!E)return a("洞府配置异常，请重新加载游戏。","danger"),h;'
    'const __hr=3+Math.floor((R.level-1)/2);'
    'const __cur=Math.max(0,Math.min(__hr,Math.floor(Number(R.extraSlots)||0)));'
    'if(__cur>=__hr)return a(`当前洞府种植区已扩至上限（基础 ${E.maxHerbSlots} 块 + 扩充 ${__cur} 块 = 共 ${E.maxHerbSlots+__cur} 块）。升级洞府可提高基础槽位与可扩建上限。`,"danger"),h;'
    'const __cost=[2000,8000,24000,60000,150000,350000,800000][__cur]*R.level;'
    'if(h.spiritStones<__cost)return a(`灵石不足！开垦新灵草田需要 ${__cost.toLocaleString()} 灵石，当前拥有 ${h.spiritStones.toLocaleString()} 灵石。`,"danger"),h;'
    'const __msg=`✨ 花费 ${__cost.toLocaleString()} 灵石开垦了一块新灵草田！种植槽位 ${E.maxHerbSlots+__cur} → ${E.maxHerbSlots+__cur+1} 块。`;'
    'return a(__msg,"gain"),l&&l({text:__msg,type:"gain"}),'
    '{...h,spiritStones:h.spiritStones-__cost,grotto:{...R,extraSlots:__cur+1}}})};'
    'return{handleUpgradeGrotto:v,handlePlantHerb:m,handleExpandHerbSlots:__ylGrottoExpand,'
)

# --------------------------------------------------------------------------- E3/E4 透传链

E3_OLD = 'onSpeedupHerb:c.handleSpeedupHerb})'
E3_NEW = 'onSpeedupHerb:c.handleSpeedupHerb,onExpandHerbSlots:c.handleExpandHerbSlots})'

E4_OLD = 'onToggleAutoHarvest:v,onSpeedupHerb:m})=>{var N,k,_,C;'
E4_NEW = 'onToggleAutoHarvest:v,onSpeedupHerb:m,onExpandHerbSlots:__ylExp})=>{var N,k,_,C;'

# --------------------------------------------------------------------------- E5 T 默认 grotto 形状补字段（老存档 ||0 兜底之外的形状卫生）

E5_OLD = 'lastHarvestTime:null,spiritArrayEnhancement:0,herbarium:[],dailySpeedupCount:0,lastSpeedupResetDate:""}'
E5_NEW = 'lastHarvestTime:null,spiritArrayEnhancement:0,herbarium:[],dailySpeedupCount:0,lastSpeedupResetDate:"",extraSlots:0}'

# --------------------------------------------------------------------------- E6 总览「种植槽位」卡（显示 + 已满判定 → 有效槽位）

E6_OLD = ('children:[T.plantedHerbs.length," / ",($==null?void 0:$.maxHerbSlots)||0]}),'
          'e.jsx("p",{className:"text-xs text-stone-500 mt-1",'
          'children:T.plantedHerbs.length>=(($==null?void 0:$.maxHerbSlots)||0)?"已满":"可用"})')
E6_NEW = ('children:[T.plantedHerbs.length," / ",(($==null?void 0:$.maxHerbSlots)||0)+(T.extraSlots||0)]}),'
          'e.jsx("p",{className:"text-xs text-stone-500 mt-1",'
          'children:T.plantedHerbs.length>=((($==null?void 0:$.maxHerbSlots)||0)+(T.extraSlots||0))?"已满":"可用"})')

# --------------------------------------------------------------------------- E7 种植页签徽章 → 徽章 + 扩地按钮

E7_OLD = ('T.level>0&&e.jsxs("div",{className:"text-stone-400 text-sm bg-stone-800 px-3 py-1 rounded border border-stone-700",'
          'children:["已种植: ",T.plantedHerbs.length," / ",($==null?void 0:$.maxHerbSlots)||0]})')
E7_NEW = (
    'T.level>0&&e.jsxs("div",{className:"flex items-center gap-2",children:['
    'e.jsxs("div",{className:"text-stone-400 text-sm bg-stone-800 px-3 py-1 rounded border border-stone-700",'
    'children:["已种植: ",T.plantedHerbs.length," / ",(($==null?void 0:$.maxHerbSlots)||0)+(T.extraSlots||0)]}),'
    '(()=>{const __hr=3+Math.floor((T.level-1)/2),__cur=Math.max(0,Math.min(__hr,Math.floor(Number(T.extraSlots)||0)));'
    'if(__cur>=__hr)return e.jsx("span",{className:"text-xs text-stone-500 bg-stone-800/60 px-2 py-1 rounded border border-stone-700/60",children:"扩地已满"});'
    'const __cost=[2000,8000,24000,60000,150000,350000,800000][__cur]*T.level,__ok=__cost>0&&a.spiritStones>=__cost;'
    'return e.jsx("button",{onClick:()=>__ylExp(),disabled:!__ok,'
    'className:`px-3 py-1.5 text-xs font-bold rounded border transition-colors '
    '${__ok?"bg-green-900/40 text-green-300 border-green-600/50 hover:bg-green-800/60":"bg-stone-800 text-stone-500 border-stone-700 cursor-not-allowed"}`,'
    'children:`➕ 扩地（${__cost.toLocaleString()} 灵石）`})})()]})'
)

# --------------------------------------------------------------------------- E8 灵草卡片可种判定

E8_OLD = 'w=T.plantedHerbs.length>=(($==null?void 0:$.maxHerbSlots)||0)'
E8_NEW = 'w=T.plantedHerbs.length>=((($==null?void 0:$.maxHerbSlots)||0)+(T.extraSlots||0))'

# --------------------------------------------------------------------------- E9 面板 R useMemo 槽位 D（种子列表 Q 满槽判定）

E9_OLD = 'D=(I==null?void 0:I.maxHerbSlots)||0,Q=A.plantedHerbs.length>=D'
E9_NEW = 'D=((I==null?void 0:I.maxHerbSlots)||0)+(A.extraSlots||0),Q=A.plantedHerbs.length>=D'

# --------------------------------------------------------------------------- E10 升级时「缩水移除最早种植」判定 → 有效槽位

E10_OLD = 'const k=N.maxHerbSlots,_=R.plantedHerbs.length;'
E10_NEW = 'const k=N.maxHerbSlots+(R.extraSlots||0),_=R.plantedHerbs.length;'

# --------------------------------------------------------------------------- E11 种植动作满槽拦截（+文案提示扩地）

E11_OLD = ('if(R.plantedHerbs.length>=E.maxHerbSlots)return a(`种植槽位已满！当前已种植 ${R.plantedHerbs.length} 个，'
           '最多可种植 ${E.maxHerbSlots} 个。请先收获成熟的灵草或升级洞府。`,"danger"),h;')
E11_NEW = ('if(R.plantedHerbs.length>=E.maxHerbSlots+(R.extraSlots||0))return a(`种植槽位已满！当前已种植 ${R.plantedHerbs.length} 个，'
           '最多可种植 ${E.maxHerbSlots+(R.extraSlots||0)} 个。可收获成熟灵草、扩地或升级洞府。`,"danger"),h;')


EDITS = [
    ('E1 hook加扩地handler+导出',        E1_OLD, E1_NEW),
    ('E3 modal透传onExpandHerbSlots',    E3_OLD, E3_NEW),
    ('E4 HM解构onExpandHerbSlots',       E4_OLD, E4_NEW),
    ('E5 默认grotto补extraSlots:0',      E5_OLD, E5_NEW),
    ('E6 总览槽位卡用有效槽位',           E6_OLD, E6_NEW),
    ('E7 种植页签徽章+扩地按钮',          E7_OLD, E7_NEW),
    ('E8 灵草卡片可种判定',              E8_OLD, E8_NEW),
    ('E9 R useMemo槽位D',               E9_OLD, E9_NEW),
    ('E10 升级缩水判定用有效槽位',        E10_OLD, E10_NEW),
    ('E11 种植满槽拦截+文案',            E11_OLD, E11_NEW),
]


def apply(p, ctx):
    """p = yl_patch.Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 注入块禁词自查（本模块 INJECT_JS 为空，走一遍流程保持与其他模块同构）
    blk = zh(INJECT_JS)
    for _pat in ('iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-'):
        assert _pat not in blk, 'r049 注入块含禁用模式: %s' % _pat

    # 结构自检：新 handler 名必须出现在 E1/E3 的替换串里（防手滑改名）
    assert 'handleExpandHerbSlots:__ylGrottoExpand' in E1_NEW
    assert 'onExpandHerbSlots:c.handleExpandHerbSlots' in E3_NEW

    for name, old, new in EDITS:
        p.replace(name, old, new, expect=1)

    # ------------------------------------------------------------------ 门禁
    gates = [
        # ---- 本模块改动（正面特征）----
        ('R49·扩地handler定义',            'const __ylGrottoExpand=', 1, '==', 'hook 闭包内，用 r/a/l/c/d'),
        ('R49·hook返回表导出',             'handleExpandHerbSlots:__ylGrottoExpand', 1, '==', ''),
        ('R49·modal透传',                 'onExpandHerbSlots:c.handleExpandHerbSlots', 1, '==', 'E3'),
        ('R49·HM解构',                    'onExpandHerbSlots:__ylExp', 1, '==', 'E4'),
        ('R49·扩地按钮onClick',            'onClick:()=>__ylExp()', 1, '==', 'E7'),
        ('R49·扩地按钮文案',               '➕ 扩地（', 1, '==', ''),
        ('R49·满级文案',                  'children:"扩地已满"', 1, '==', '上限=基础+headroom(L)'),
        ('R49·扣灵石写回',                'spiritStones:h.spiritStones-__cost', 1, '==', '产生点扣费，走 YLApplyBalance 回显'),
        ('R49·购地写回grotto',            'grotto:{...R,extraSlots:__cur+1}', 1, '==', 'extraSlots 随 grotto 整体透传存档'),
        ('R49·成功日志',                  '灵石开垦了一块新灵草田', 1, '==', '模板复用于 toast+聊天框，仅 1 处定义'),
        ('R49·灵石不足拦截',              '灵石不足！开垦新灵草田需要', 1, '==', ''),
        ('R49·满上限拦截',                '已扩至上限', 1, '==', ''),
        ('R49·默认grotto补字段',           'lastSpeedupResetDate:"",extraSlots:0}', 1, '==', 'E5 形状卫生'),
        ('R49·总览卡有效槽位',            '||0)+(T.extraSlots||0)]}),e.jsx("p",{className:"text-xs text-stone-500 mt-1"', 1, '==', 'E6 显示（长针与 E7 徽章区分）'),
        ('R49·E8 可种判定',               'w=T.plantedHerbs.length>=((($==null?void 0:$.maxHerbSlots)||0)+(T.extraSlots||0))', 1, '==', ''),
        ('R49·E9 R useMemo',             'D=((I==null?void 0:I.maxHerbSlots)||0)+(A.extraSlots||0)', 1, '==', ''),
        ('R49·E10 升级缩水判定',           'const k=N.maxHerbSlots+(R.extraSlots||0),_', 1, '==', '扩得的地跨升级保留'),
        ('R49·E11 满槽拦截',              'length>=E.maxHerbSlots+(R.extraSlots||0)', 1, '==', ''),
        # ---- R-049 返工：上限随洞府等级梯度 + 价格阶梯（2026-10-01）----
        ('R49·E1 上限式随等级',            'const __hr=3+Math.floor((R.level-1)/2)+(R.level>=9?7:R.level>=7?4:R.level>=5?2:0);', 1, '==', 'R-115 式在 V28 装配态仍在位；R-125（standalone 阶段）改写为 3+(L-1)+档位奖，终态旧式清零断言归 yl_r125_ext.gates()（接线层修正 2026-10-02：成员把本表当终态评估，实际本表跑在 standalone 之前）'),
        ('R49·E7 上限式随等级',            'const __hr=3+Math.floor((T.level-1)/2)+(T.level>=9?7:T.level>=7?4:T.level>=5?2:0),__cur=', 1, '==', '同上：装配态在位，终态清零归 yl_r125_ext.gates()'),
        ('R49·E1 上限闸门用__hr',          'if(__cur>=__hr)return a(', 1, '==', '旧 if(__cur>=3) 已废'),
        ('R49·E7 上限闸门用__hr',          'if(__cur>=__hr)return e.jsx(', 1, '==', ''),
        ('R49·价格阶梯 7 档',              '[2000,8000,24000,60000,150000,350000,800000]', 2, '==', 'E1+E7 各 1'),
        ('R49·E1 价格随等级 ×L',           '][__cur]*R.level;', 1, '==', 'L1 时退化为旧价 2000/8000/24000'),
        ('R49·E7 价格随等级 ×L',           '][__cur]*T.level,__ok=', 1, '==', ''),
        ('R49·旧固定上限3已清零(E1)',      'Math.min(3,Math.floor(Number(R.extraSlots)', 0, '==', '返工前形态'),
        ('R49·旧固定上限3已清零(E7)',      'Math.min(3,Math.floor(Number(T.extraSlots)', 0, '==', '返工前形态'),
        ('R49·旧三档价格已清零',           '[2000,8000,24000][__cur]', 0, '==', '返工前形态'),
        ('R49·旧 if(__cur>=3) 已清零',     'if(__cur>=3)', 0, '==', '返工前形态'),
        # ---- 计数不变量 ----
        ('R49·maxHerbSlots 计数 20→24',   'maxHerbSlots', 24, '==', '10 Pr定义 + 10 消费点 + 4 handler消息（上限2+成功2）'),
        ('R49·extraSlots 计数 12',        'extraSlots', 12, '==', '1 E5默认 + 11 各消费/写回点（E7 含徽章+守卫 2 处）'),
        ('R49·T.extraSlots 计数 5',       'T.extraSlots', 5, '==', 'E6×2 + E7×2 + E8×1'),
        ('R49·badge 文案仍唯一',           '已种植: ', 1, '==', 'E7 改容器不改徽章文本'),
        ('R49·满槽拦截文案仍唯一',          '种植槽位已满', 1, '==', 'E11 原地改写'),
        # ---- 冻结：并行批不会动的结构不变量 ----
        ('冻结·Pr 等级表未动',             'Pr=[{level:1,name:"简陋洞府"', 1, '==', '基础槽位=默认值，等级表一字不动（grotto087 同款冻结）'),
        ('冻结·handleUpgradeGrotto=9',    'handleUpgradeGrotto', 9, '==', 'grotto087 门禁同值；E1 只追加键'),
        ('冻结·handlePlantHerb=9',        'handlePlantHerb', 9, '==', ''),
        ('冻结·handleSpeedupHerb=9',      'handleSpeedupHerb', 9, '==', 'R-050 的面：我未增减该标识符（v2810c 同款冻结）'),
        ('冻结·灵田联动行(grotto087)',     '灵田联动：产出 +', 1, '==', 'E10 锚点在其之前，互不重叠'),
        ('冻结·升级页槽位预览未动',         'children:g.maxHerbSlots', 1, '==', '每级基础槽位预览保留原样'),
        ('冻结·升级 toast 基础槽位未动',    '种植槽位 ${N.maxHerbSlots} 个', 1, '==', 'toast 描述该级基础值，扩地另行提示'),
        ('冻结·收获兜底(grotto087 G14)',  '||wn.find(Q=>Q.name===N.herbName)', 1, '==', 'T4 兜底映射零回归'),
        ('冻结·聚灵阵改造 handler',        'handleEnhanceSpiritArray', 9, '==', '0.8.7 聚灵阵面零回归'),
    ]
    return gates
