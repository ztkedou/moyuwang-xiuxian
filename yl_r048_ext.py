# -*- coding: utf-8 -*-
r"""
yl_r048_ext.py — R-048 仙务·灵田：灵草分三档（普通 / 加基础属性 / 特殊属性）

需求（台账 R-048 · 仙务·灵田 · 无附图）
--------------------------------------------------------------------------
  「① 加基础属性的灵草：**种植条件保持现状**，但**成熟时间比普通（专供修为/灵石的）要增加**；
    ② 特殊属性的灵草：**必须要玩家等阶很高了才可以种植**，且**成熟时间要大幅度增加**；
    ③ 这两类的修为、灵石数量也相应增加。」
  ⇒ 三档差异化：普通（不动）／基础属性（时间长一点、收益同步）／
     特殊属性（新增高境界门槛 + 时间大幅增加 + 收益同步）。

★ 关键事实（逐字实证）：**数值全在服务端**
--------------------------------------------------------------------------
  · 客户端产物 `build/assets/index-v28118-20261001.js` 里**没有任何**作物数值表：
      `linggusi` / `peiyuancao` / `jifengye` / `FARM_CROP*` 计数均为 **0**；
      只有展示用映射 `YLXW_FT_LINE / YLXW_FT_TIER / YLXW_FT_PCT / YLXW_FT_ATTR`。
  · 权威数值在服务端 `srv/index_v28.ts` 的 `farmCropDefs()`（@5637）：
      时长 = clamp30(B(品阶).min × k(类型).min)；变卖 = V(品阶).sell × k.money；
      种子 = 变卖 × Cs；服用修为按产品线分流（@5553-5569）。
      `/farm/status` 把 `crops`(25 键) + `cropList` 下发给客户端，客户端只渲染。
      `/farm/plant`（@7967）结算种植、`farmHarvestOne` 结算收获 —— 均服务端权威。
  ⇒ **成熟时间 / 灵石 / 修为 的改档，客户端做不到，必须改服务端**（本模块**不改服务端**，
     已在本文件与报告里写明给主控的精确改法与锚点）。

三档的确切判据（客户端可直接消费）
--------------------------------------------------------------------------
  `/farm/status` 的 `cropList[].line` ∈ {sell, cult, mix, rare}（`yl_farm089_ext.py` 的
  `YlxwFtCrops()` 已把它并入 `crops`，故面板内 `cd.line` 即可判档）：
    · sell 纯卖钱草 / cult 纯修为草 ⇒ **普通**（专供修为/灵石）—— 不动
    · mix  综合草（修为 + 基础属性 攻/防/血/神识）⇒ **加基础属性**
    · rare 稀有属性草（修为 + 百分比属性 暴击/闪避/吸血）⇒ **特殊属性**

本模块动作（客户端一半，只做 UI；数值改档交主控）
--------------------------------------------------------------------------
  E0 注入档位/境界工具函数（模块级，与 farm2 的 YlxwFt* 同作用域）：
       YLXW_FT_REALM（境界序，兜底用；优先用游戏权威 `fe`）、YLXW_FT_RARE_REALM=3、
       YLXW_FT_GRADE_CN、YlxwFtRealmIdx / YlxwFtGrade / YlxwFtRealmReq /
       YlxwFtRealmOk / YlxwFtRealmHint。
  E1 T5 活面板播种按钮 `cropBtn`：特殊属性（rare）草**境界不足 ⇒ 置灰**（新增门槛），
      并在按钮文案尾部提示「· 需 元婴期」。
  E2 播种 hover（farm2 的 `YlxwFtSeedTip`）补「【档位 · 成熟 N 分】」，
      让「基础属性/特殊属性比普通更长」这件事对玩家**可见**（时长仍取服务端下发值）。

★ 门槛定档（自己拍板，理由见报告）
--------------------------------------------------------------------------
  「等阶很高」= **元婴期**（境界序第 4 档 / index 3；`fe` 共 7 档）。
  理由：与游戏既有惯例一致（建宗门槛 `SECT_CREATE_MIN_REALM` = 元婴期，下标 3），
        且特殊属性草给的是**永久百分比属性**（暴击/闪避/吸血，有硬上限），
        属后期成长，放元婴期可避免中前期属性膨胀。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 只新建本文件；不改 build_v26n.py / build/assets/* / srv/index_v28.ts /
    localtest/* / deploy_v28/* / 任何已有 yl_*_ext.py（尤其 yl_farm2/yl_r046）。
  · 注入块走 zh()，注入后纯 ASCII；不含 V28_BAN_PATTERNS。
  · 每个 replace 带 expect= 精确次数（1/1/1，均实测）。
  · 锚点里中文/特殊符号在 bundle 内是**字面 `\uXXXX` 转义形态**，故用 raw 串。
  · 留冻结门禁：变卖/服用收益（R-047）、灵田显示（R-046）、普通灵草种植条件、
    收获结算、洞府扩充。

需主控同步处理（本模块不碰上游文件）
--------------------------------------------------------------------------
  A) `yl_farm089_ext.py` 的门禁 `('T5·已停种·禁用点击', 'disabled: !!u || !ok2 || ret,', 1)`
     会被本模块的合法改写打破（新增 `!okR` 分支）⇒ 该串改后 = 0，请改为
     `'disabled: !!u || !ok2 || !okR || ret,'` == 1，或删除该条。
     ★ farm089 其余门禁（已停种判定/点击守卫/提示文案/各端点计数）**全部不受影响**。
  B) 接线：`from yl_r048_ext import apply as v28_r048_apply`；
     `V28_MODULES` 追加 `('r048', v28_r048_apply),` —— **必须排在 `farm2` 之后**
     （E2 改的是 farm2 注入的 `YlxwFtSeedTip`），且恒在 `numbal` 之前。
     `localtest/dryrun_087.py` 的 EXPECTED_ORDER / NEW_MODULES 两处同步。
  C) **服务端配套（数值改档 + 门槛强制）见文件末尾《给主控的服务端改法》**。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R048: 灵草三档（普通 / 基础属性 / 特殊属性）客户端一半 =====
   档位判据 = 服务端下发的 cropList[].line（farm2 的 YlxwFtCrops 已并入 crops）：
     sell/cult = 普通（专供修为/灵石）；mix = 加基础属性；rare = 特殊属性。
   ★ 成熟时间 / 灵石 / 修为 的数值改档在服务端 farmCropDefs()（本块不改数值）。
   本块只做两件事：① 特殊属性草的高境界种植门槛 UI；② 播种 hover 标档位 + 成熟时长。 */

/* 境界序（兜底表；优先用游戏权威境界表 fe，见 YlxwFtRealmIdx） */
var YLXW_FT_REALM = ["炼气期", "筑基期", "金丹期", "元婴期", "化神期", "合道期", "长生境"];
/* 特殊属性草种植所需境界 = 元婴期（fe 第 4 档 / index 3） */
var YLXW_FT_RARE_REALM = 3;
/* 三档显示名 */
var YLXW_FT_GRADE_CN = { normal: "普通", attr: "基础属性", rare: "特殊属性" };

/* 玩家境界序（优先游戏权威 fe；取不到退回本地表，缺省 0 = 最低） */
function YlxwFtRealmIdx(player) {
  var r = player && player.realm;
  if (typeof fe !== "undefined" && fe && fe.indexOf) {
    var i = fe.indexOf(r);
    if (i >= 0) return i;
  }
  var j = YLXW_FT_REALM.indexOf(r);
  return j >= 0 ? j : 0;
}
/* 作物档位：normal（专供修为/灵石）/ attr（加基础属性）/ rare（特殊属性） */
function YlxwFtGrade(cd) {
  var ln = cd && cd.line;
  if (ln === "rare") return "rare";
  if (ln === "mix") return "attr";
  return "normal";
}
/* 该作物种植所需境界 index：**只有特殊属性草有门槛**；普通/基础属性保持现状(=0) */
function YlxwFtRealmReq(cd) { return YlxwFtGrade(cd) === "rare" ? YLXW_FT_RARE_REALM : 0; }
/* 境界是否达标（未达标 ⇒ 播种按钮置灰） */
function YlxwFtRealmOk(player, cd) { return YlxwFtRealmIdx(player) >= YlxwFtRealmReq(cd); }
/* 未达标提示：需 元婴期 */
function YlxwFtRealmHint(cd) {
  var i = YlxwFtRealmReq(cd);
  return "需 " + (YLXW_FT_REALM[i] || "高境界");
}
'''

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- 锚点

# 注入锚：v2810c 块内的模块级函数（depth=2 顶层；与 farm2 的 YlxwFt* 同作用域）。
#   farm2 也插在此锚点前（其 YlxwFtTendCdMs/CdText/SeedTip/Tick/Crops），
#   insert_before 把本块放到 farm2 块之后、锚点之前 —— 同处模块级，函数提升可用。
INJECT_ANCHOR = 'function YlxwFtHasConsume(cd) {'

# E1 T5 活面板 cropBtn：加「特殊属性草境界门槛」。
#   ★ 唯一性：`var ret = cd.retired === true;` + 紧随的 `disabled: !!u || !ok2 || ret,`
#     只出现在 T5 活面板（T10 死面板的 cropBtn 无 ret，disabled 形态也不同）。
E1_OLD = ('    var ret = cd.retired === true;\n'
          '    return e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u || !ok2 || ret,')
E1_NEW = ('    var ret = cd.retired === true;\n'
          '    var rq = YlxwFtRealmReq(cd), okR = YlxwFtRealmOk(pstore, cd);\n'
          '    return e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u || !ok2 || !okR || ret,')

# E2 T5 cropBtn 文案尾部补「· 需 元婴期」。
#   ★ 唯一性：带 `(ret ? " · 已停种" : "")` 的尾串只有 T5（T10 无 retired 分支）。
E2_OLD = r'(ret ? " \u00b7 \u5df2\u505c\u79cd" : "") + "\uff09" }, x);'
E2_NEW = (r'(ret ? " \u00b7 \u5df2\u505c\u79cd" : "") '
          r'+ (!okR ? " \u00b7 " + YlxwFtRealmHint(cd) : "") + "\uff09" }, x);')

# E3 farm2 的 YlxwFtSeedTip：hover 文案补「【档位 · 成熟 N 分】」（只加不改原有元数据）。
#   ★ 只动 return 行；`var meta = ...` / `var body = ...` / 函数签名 / 空数据兜底串逐字保留
#     （farm2 的四条 hover 门禁不受影响）。
E3_OLD = (r'  return (cd.name || "\u7075\u8349") + (meta ? "\uff08" + meta + "\uff09" : "") '
          r'+ "\uff1a" + (body || "\u6682\u65e0\u4ea7\u51fa\u6570\u636e");')
E3_NEW = (r'  return (cd.name || "\u7075\u8349") + (meta ? "\uff08" + meta + "\uff09" : "") '
          r'+ "\u3010" + YLXW_FT_GRADE_CN[YlxwFtGrade(cd)] + " \u00b7 \u6210\u719f " '
          r'+ YlxwNum(cd.minutes) + " \u5206\u3011" + "\uff1a" + (body || "\u6682\u65e0\u4ea7\u51fa\u6570\u636e");')

EDITS = [
    ('E1 播种按钮加「特殊属性境界门槛」', E1_OLD, E1_NEW, 1),
    ('E2 按钮文案补「需 元婴期」',        E2_OLD, E2_NEW, 1),
    ('E3 播种 hover 标档位+成熟时长',     E3_OLD, E3_NEW, 1),
]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 farm089 / v2810c / farm2 / r046）；
    ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检 1：替换串必须真的变了，且含新特征（防手滑写成恒等 / 写错方向）
    for _nm, _a, _b, _e in EDITS:
        if _a == _b:
            raise AssertionError('r048 %s：锚点替换为恒等（无改动）' % _nm)
    if 'okR' not in E1_NEW or '!okR' not in E1_NEW:
        raise AssertionError('r048 E1 替换串缺 okR 门槛')
    if 'YlxwFtRealmHint(cd)' not in E2_NEW:
        raise AssertionError('r048 E2 替换串缺境界提示')
    if 'YlxwFtGrade(cd)' not in E3_NEW or 'cd.minutes' not in E3_NEW:
        raise AssertionError('r048 E3 替换串缺档位/成熟时长')

    # 自检 2：注入块 zh() 后必须纯 ASCII，且不含禁用模式
    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r048 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for _pat in BAN_PATTERNS:
        if _pat in blk:
            raise AssertionError('r048 注入块含禁用模式: %s' % _pat)

    # 0) 模块级工具函数（与 farm2 的 YlxwFt* 同作用域，函数提升，位置无关）
    p.insert_before('r048-helpers', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 档位/境界 工具函数（YLXW_FT_REALM/GRADE/REALM_REQ 等）')

    # 1) 就地替换
    for name, old, new, exp in EDITS:
        p.replace(name, old, new, expect=exp)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 注入块 =================
        ('R48·境界序表已注入',       'var YLXW_FT_REALM = [', 1, '==', '兜底表；优先用 fe'),
        ('R48·门槛=元婴期(index3)',  'var YLXW_FT_RARE_REALM = 3;', 1, '==', 'fe 第 4 档 / 7 档'),
        ('R48·三档显示名已注入',     'var YLXW_FT_GRADE_CN = { normal:', 1, '==', '普通/基础属性/特殊属性'),
        ('R48·境界序读取函数已注入', 'function YlxwFtRealmIdx(player) {', 1, '==', ''),
        ('R48·境界序优先读 fe',      'var i = fe.indexOf(r);', 1, '==', '游戏权威境界表'),
        ('R48·fe 命中即返回',        'if (i >= 0) return i;', 1, '==', ''),
        ('R48·fe 缺失兜底本地表',    'var j = YLXW_FT_REALM.indexOf(r);', 1, '==', 'minify 名变更时不崩面板'),
        ('R48·档位判定函数已注入',   'function YlxwFtGrade(cd) {', 1, '==', 'sell/cult=普通, mix=基础属性, rare=特殊属性'),
        ('R48·mix→基础属性',         'if (ln === "mix") return "attr";', 1, '==', ''),
        ('R48·rare→特殊属性',        'if (ln === "rare") return "rare";', 1, '==', ''),
        ('R48·仅特殊属性有门槛',     'return YlxwFtGrade(cd) === "rare" ? YLXW_FT_RARE_REALM : 0;', 1, '==', '普通/基础属性 = 保持现状(0)'),
        ('R48·境界达标判定已注入',   'function YlxwFtRealmOk(player, cd) {', 1, '==', ''),
        ('R48·境界提示函数已注入',   'function YlxwFtRealmHint(cd) {', 1, '==', ''),
        # ================= E1 特殊属性草：高境界门槛（UI 置灰） =================
        ('R48·按钮已加境界灰置',     'disabled: !!u || !ok2 || !okR || ret,', 1, '==', '仅 rare 未达标时灰'),
        ('R48·旧 disabled 已清零',   'disabled: !!u || !ok2 || ret,', 0, '==', '旧形态（无 okR）'),
        ('R48·门槛按玩家境界实算',   'var rq = YlxwFtRealmReq(cd), okR = YlxwFtRealmOk(pstore, cd);', 1, '==', '读玩家存档境界'),
        # ================= E2 按钮文案：境界提示 =================
        ('R48·按钮显示境界提示',     r'(!okR ? " \u00b7 " + YlxwFtRealmHint(cd) : "")', 1, '==', '「· 需 元婴期」'),
        ('R48·已停种提示仍保留',     r'(ret ? " \u00b7 \u5df2\u505c\u79cd" : "")', 1, '==', 'R-046 面未动'),
        # ================= E3 播种 hover：档位 + 成熟时长 =================
        ('R48·hover 标档位',         'YLXW_FT_GRADE_CN[YlxwFtGrade(cd)]', 1, '==', ''),
        ('R48·hover 标成熟时长',     '+ YlxwNum(cd.minutes) +', 1, '==', '服务端下发值，自动反映改档后时长'),
        ('R48·hover 原元数据仍保留', r'var meta = [tier, line].filter(function (x) { return !!x; }).join(" \u00b7 ");', 1, '==', 'farm2 门禁串'),
        ('R48·hover 空数据兜底保留', r'|| "\u6682\u65e0\u4ea7\u51fa\u6570\u636e");', 1, '==', 'farm2 门禁串'),
        # ================= 冻结：R-047 变卖/服用收益（在做） =================
        ('冻结·R47 变卖收益函数未动', 'function YlxwFtSellText(cd, slot) {', 1, '==', ''),
        ('冻结·R47 服用收益函数未动', 'function YlxwFtConsumeText(cd) {', 1, '==', ''),
        ('冻结·R47 双出口分流未动',   'var mode = q.kind === "consume" ? "consume" : "sell";', 1, '==', ''),
        # ================= 冻结：R-046 灵田显示（只改显示，本模块不碰） =================
        ('冻结·R46 播种容器未动',     'children: [cropBtn(N, x)]', 2, '==', 'T5 活 + T10 死'),
        ('冻结·R46 常显标注已清零',   'text-[10px] text-stone-400 leading-tight', 0, '==', 'R-046 已删，本模块不恢复'),
        ('冻结·R46 播种 hover 未动',  'title: YlxwFtSeedTip(g[x] || {}, N.slot)', 2, '==', '只改函数体，不改调用点'),
        ('冻结·R46 变卖按钮未动',     r'children: "\u53d8\u5356"', 1, '==', ''),
        ('冻结·R46 服用按钮未动',     r'children: "\u670d\u7528"', 1, '==', ''),
        # ================= 冻结：普通灵草种植条件 / 洞府门槛 =================
        ('冻结·种植入口未动',         '"/farm/plant"', 3, '==', '旧 + T10 + T5'),
        ('冻结·洞府门槛判定未动',     'ok2 = !nl || gl >= nl;', 2, '==', '普通/基础属性种植条件保持现状'),
        # ================= 冻结：收获结算 =================
        ('冻结·收获结算未动',         '"/farm/harvest", { slot: q.slot, mode: mode }', 1, '==', ''),
        ('冻结·单收端点未动',         '"/farm/harvest"', 3, '==', ''),
        ('冻结·一键收取未动',         '"/farm/harvest/all"', 4, '==', ''),
        # ================= 冻结：洞府扩充（R-049 面） =================
        ('冻结·开垦入口未动',         '"/farm/unlock"', 3, '==', ''),
        ('冻结·扩充等级表未动',       'Pr=[{level:1,name:', 1, '==', '洞府等级槽位表'),
        # ================= 冻结：面板注册 / 组件本体 =================
        ('冻结·T5 面板函数未动',      'function YlxwTFarmT5() {', 1, '==', ''),
        ('冻结·T5 注册未动',          'YLXW_COMP.farm=YlxwTFarmT5;', 1, '==', ''),
        ('冻结·成熟时间展示未动',     'YlxwMin(YlxwNum(b.leftMs))', 3, '==', '改「值」不改展示表达式'),
    ]
    return gates
