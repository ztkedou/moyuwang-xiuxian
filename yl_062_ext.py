# -*- coding: utf-8 -*-
r"""
yl_062_ext.py — R-062 秘境：**单独点选收益 ×3 + 冷却改 15 分钟**

需求原文（需求台账_进行中.md L28，R-062，附图列为空）
--------------------------------------------------------------------------
  「秘境roguelinke和下面单独选择的秘境，收益差距过大。可以把下面单独选的收益提升。
    秘境冷却时间一次为15分钟。这一个也是游戏主要的稀有物品、修为和灵石的获取途径。」

    ⇒ ① 提升单独点选秘境的收益（roguelike 侧不动）
       ② 秘境单次进入冷却 = 15 分钟

侦察结论（基座产物 build/assets/index-v28116-20261001.js，1,988,572 B，逐字实证）
--------------------------------------------------------------------------
  ★ 关键发现：经典秘境弹窗入口走的是**主历练结算点**，不是 eco085 注释说的 SR 点。
    · 弹窗入口 XM.handleEnterRealm（@1760304）→ `await f("secret_realm",m.name,
      m.riskLevel,m.minRealm,…)` → executeAdventure = ge 钩子的 `I=async(Q,U,B,Y)=>{…}`
      → `const oe=Fm(Q,B,t.realm,t.realmLevel)`（@539833 按 riskLevel 过滤秘境池）
      → **`if(V=Ym(oe,{realm:t.realm,realmLevel:t.realmLevel,maxHp:F.maxHp},
         YLXW_STONE_MUL_ADV),ek()){`**（@1775826，count==1）
      ⇒ 单独点选的结算乘子是 YLXW_STONE_MUL_ADV(0.2)，与无限次主历练共用一个调用点。
    · `C=Ym(k,…,YLXW_STONE_MUL_SR)`（@1771270，count==1）是**历练奇遇 5% 触发的
      「秘境深处」奖励**（`t.triggerSecretRealm`），不是弹窗入口 —— 不在本需求面。
  · `Ym(` 全产物仅 3 个调用点（§21.4 防漏查）：D=lucky 宗门奇遇 / C=秘境深处 / V=主历练
    （含弹窗秘境）。弹窗秘境与主历练共用 V 点 ⇒ 只能**按 Q==="secret_realm" 条件分流**，
    绝不能改 Ym 本体或 MUL_ADV 常量（会连带主历练，那是 R-044 的面）。
  · 战斗分支（DS→X0→By）的秘境奖励已带风险乘子 `w=secret_realm?$y(a):1`
    （$y={低:.6,中:1,高:1.5,极度危险:2.2}）⇒ 本模块**不碰**（By 是 eco085 冻结面）。
  · 收益现状（炼气 L1，u=1）：事件路径 exp 444 / 灵石 887（四档风险均值）+ 60% 掉品；
    roguelike 一轮 5~12 层 × 每层 3 事件（xg=5,z3=12 @469829），灵石 ~1.5 万~5 万。
    ⇒ 弹窗单次 ≈ roguelike 单轮的 1/20~1/60，用户「差距过大」成立。

本模块动作（1 注入 + 3 就地替换）
--------------------------------------------------------------------------
  ① 收益 ×3（只弹窗事件路径）：注入 YLXW_SR_GAIN_R62=3 + YlxwSrBoostR62(ev)
     （只放大**正值** expChange / spiritStonesChange，hpChange / itemObtained /
     reputationEvent / 其余字段逐字保留；输入异常恒等返回），
     V 点改为 `V=(Q==="secret_realm"?YlxwSrBoostR62:function(e0){return e0})(Ym(…))`。
     ⇒ 净效果：弹窗秘境事件收益 = 0.8.5 现状 ×3（仍为 0.8.5 砍幅前的 0.6×，未回到超模）。
  ② 冷却 15 分钟：
     · 客户端 `var YLXW_DG_CD_MS = 5 * 60 * 1000;`（dungeon2 注入，count==1）→ 15 分钟。
       该变量同时是 dungeon2 E4 `cd:Date.now()+YLXW_DG_CD_MS`（roguelike 本地冷却写入）
       的取值源 ⇒ 改常量即全链生效，表达式零改动。
     · 展示文案「每次探索后冷却 5 分钟」（\u 转义形态，count==1）→「15 分钟」。
     · 服务端 `DUNGEON_ENTRY_CD_MS = 30_000` → `900_000`（srv_patch_062.py）：
       服务端 403 reason:'cd' 是弹窗秘境入口**唯一真实的 CD 执行点**
       （handleEnterRealm 本地不查 cdMin，只吃服务端 403）。

★ 需主控同步处理（本模块**不碰**上游文件，与 yl_r043_ext.py 同一处理方式）
--------------------------------------------------------------------------
  本模块的合法改写会打破 3 条上游字面门禁，请主控在接线时同步改：
  1) yl_eco085_ext.py  `('E·主历练调用带乘子', ADV_CALL_REPL, 1)` → 改后该串=0。
     改为 `('E·主历练调用带乘子（R-062 已按类型分流包裹）',
           'if(V=(Q==="secret_realm"?YlxwSrBoostR62:function(e0){return e0})(Ym(oe,{realm:t.realm,realmLevel:t.realmLevel,maxHp:F.maxHp},YLXW_STONE_MUL_ADV)),ek(){', 1, '==', '')`
     （eco085 其余门禁全部仍成立：内层 `Ym(oe,…,MUL_ADV)` 调用串仍在且恰 1。）
  2) yl_dungeon2_ext.py `('R32·冷却常量 5 分钟', 'var YLXW_DG_CD_MS = 5 * 60 * 1000;', 1)`
     → 改为 15 分钟形态（本模块门禁 'R62·冷却常量 15 分钟' 已有等价断言）。
  3) yl_dungeon2_ext.py `('R32·提示文案冷却改 5 分钟', r'…\u5374 5 \u5206\u949f', 1)`
     → 改为 15 分钟形态（同上）。
  4) srv_patch_dungeon2.py `("冻结 CD 常量未动", "const DUNGEON_ENTRY_CD_MS = 30_000;", 1)`
     → srv_patch_062.py 接入后该串=0，改 0 或删除（srv_patch_062 自己有等价正反门禁）。
  另：若 R-063（秘境上限拆分）重写 roguelike 展示行，其锚区与本模块的 CD 文案子串
  （`\u6bcf\u6b21\u63a2\u7d22\u540e\u51b7\u5374 15 \u5206\u949f`）同行 —— 请 lead 让
  两者错开装配序或合并改点；本模块只动 CD 子串，行内其余字节不动。

拍板口径（2026-10-01，AI 代决，详见 拍板/2026-10-01_*_R-062_*.md）
--------------------------------------------------------------------------
  · 收益倍率 **×3**：弹窗日收益（cap 10/日）≈ 2.66 万灵石/1.33 万修为（炼气），
    与 roguelike（R-063 后 3 次/日）量级拉近但仍低一档；且仅为 0.8.5 砍幅前 0.6×，
    未回到用户 0.8.5 明确否决过的「超模」水位。调参只需改 R062_SR_GAIN_R62 一行。
  · 冷却 15 分钟**双端同改**：服务端 403 cd 是弹窗入口唯一执行点，只改客户端=死代码
    （srv_patch_dungeon2 头部同款论证）。
  · 15 分钟 CD 同时作用于 roguelike 入口（共享账本）：R-063 的 3 次/日在 15 分钟
    间隔下仍可完成（30 分钟打满 3 次），无冲突；R-063 未提 CD，不算越界。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 只新建本文件 + srv_patch_062.py；不改 build_v26n.py / build/assets/* / srv/index_v28.ts /
    localtest/* / deploy_v28/* / 任何已有 yl_*_ext.py / srv_patch_*.py。
  · 注入块纯 ASCII（zh() 后无非 ASCII 自检）；不含 V28_BAN_PATTERNS；无 fetch。
  · 锚点全 ASCII 或 \u 转义形态；每个 replace 带 expect= 精确次数。
  · 冻结门禁证明相邻需求面逐字未动：R-063（上限表/计数回灌）、R-044（Ym exp/stones 路径）、
    R-043（Ym hp 折算）、0.8.5 eco（秘境深处/roguelike G3/宗门奇遇/战斗 By）、dungeon2（E4 表达式）。
"""

import re

# --------------------------------------------------------------------------- 可调常量
# 主控调参只需改这一行（自动拼进 INJECT_JS，无需改其它地方）
R062_SR_GAIN_R62 = 3       # 弹窗秘境事件收益倍率（exp + 灵石；0.8.5 现状 ×3）
R062_CD_MIN = 15           # 秘境单次进入冷却（分钟）——用户指定值，勿调

# --------------------------------------------------------------------------- 注入块（纯 ASCII）

INJECT_JS = r'''
/* ===== yl-R062: individually-selected secret realm income boost =====
   User R-062: the roguelike secret realm yields far more than the
   individually-selected (popup) realm; raise the popup realm income.
   Scope guard (all call sites verified single-copy in the assembled bundle):
     - boosted ONLY here: executeAdventure settlement when adventureType is
       "secret_realm" (popup entry, event branch Fm()/Ym()).
     - NOT boosted: the 5-percent-lucky "realm depths" delve (its own call site passes
       YLXW_STONE_MUL_SR), the roguelike dungeon (G3), sect quests, main
       adventures (normal/lucky), battle rewards (By), and Ym() internals
       (hp/exp/stones paths, incl. the R-043 hp nerf).
   Positive-only scaling; identity on any malformed input. */
var YLXW_SR_GAIN_R62 = %(GAIN)s;   /* popup realm exp+stones multiplier */
function YlxwSrBoostR62(e0) {
  try {
    if (!e0 || typeof e0 !== "object") return e0;
    var g0 = Number(YLXW_SR_GAIN_R62);
    if (!isFinite(g0) || g0 <= 0) return e0;
    var o0 = Object.assign({}, e0);
    var x0 = Number(o0.expChange);
    if (isFinite(x0) && x0 > 0) o0.expChange = Math.floor(x0 * g0);
    var s0 = Number(o0.spiritStonesChange);
    if (isFinite(s0) && s0 > 0) o0.spiritStonesChange = Math.floor(s0 * g0);
    return o0;
  } catch (e1) { return e0; }
}
''' % {'GAIN': R062_SR_GAIN_R62}

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- 锚点（均实测 count==1 @ index-v28116-20261001.js）

# —— 注入锚：Ym 定义之前（模块级作用域，与 eco085 注入块同区）——
INJECT_ANCHOR = 'function Ym(t,r,_ylm){'

# —— ① 弹窗秘境结算点：按类型分流包裹（内层 Ym 调用串逐字保留）——
V_OLD = ('if(V=Ym(oe,{realm:t.realm,realmLevel:t.realmLevel,maxHp:F.maxHp},'
         'YLXW_STONE_MUL_ADV),ek()){')
V_NEW = ('if(V=(Q==="secret_realm"?YlxwSrBoostR62:function(e0){return e0})'
         '(Ym(oe,{realm:t.realm,realmLevel:t.realmLevel,maxHp:F.maxHp},'
         'YLXW_STONE_MUL_ADV)),ek()){')

# —— ② 冷却常量（dungeon2 注入的取值源；E4 表达式 cd:Date.now()+YLXW_DG_CD_MS 不动）——
CD_VAR_OLD = 'var YLXW_DG_CD_MS = 5 * 60 * 1000;'
CD_VAR_NEW = 'var YLXW_DG_CD_MS = %d * 60 * 1000;' % R062_CD_MIN

# —— ③ 冷却展示文案（bundle 内为字面 \uXXXX 转义形态，必须用 raw 串匹配）——
CD_TXT_OLD = r'\u6bcf\u6b21\u63a2\u7d22\u540e\u51b7\u5374 5 \u5206\u949f'
CD_TXT_NEW = r'\u6bcf\u6b21\u63a2\u7d22\u540e\u51b7\u5374 %d \u5206\u949f' % R062_CD_MIN

# —— 冻结门禁锚点（只读；相邻需求面逐字未动的证据）——
# 0.8.5 eco：秘境深处奖励站（5% 奇遇触发，不 boost）
FRZ_DELVE_CALL = ('C=Ym(k,{realm:l.realm,realmLevel:l.realmLevel,maxHp:_.maxHp},'
                  'YLXW_STONE_MUL_SR);')
FRZ_DELVE_MUL = 'var YLXW_STONE_MUL_SR  = 0.2;'
# 0.8.5 eco：roguelike G3 收益（不 boost）
FRZ_G3 = '*1.63666;'
# 0.8.5 eco：宗门奇遇（3 次/日，不 boost）
FRZ_SECT_YM = 'D=Ym(A,{realm:l.realm,realmLevel:l.realmLevel,maxHp:I.maxHp})'
# R-044 面：Ym 内部 exp / stones 路径（一字未动）
FRZ_YM_EXP = 'expChange:Math.floor(t.expChange*u)'
FRZ_YM_STONE = ('spiritStonesChange:Math.floor(Math.floor(t.spiritStonesChange*u)'
                '*5*(_ylm==null?1:_ylm))')
# R-043 面：Ym hp 折算 + 单次钳制（一字未动）
FRZ_R043_HP = 'hpChange:t.hpChange<0?Math.floor(t.hpChange*u*0.25):Math.floor(t.hpChange*u)'
FRZ_YM_CAP = 'v=Math.floor(r.maxHp*.5)'
# 战斗 By（秘境战斗分支已带风险乘子，不 boost；eco085 冻结面）
FRZ_BY = 'M=Math.max(10,Math.round($*b))*10'
# R-063 面：dungeon2 上限表 + 计数回灌（上限拆分是 R-063 的活）
FRZ_DG_CAP = 'var YLXW_DG_CAP = [10, 12, 14, 15, 17, 18, 20];'
FRZ_DG_CAP_CALLS = 'YlxwDgCap(a&&a.realm)'          # 恒 6（disabled/className/children/E2b/E2c/E9）
FRZ_DG_CNT = 'cnt:(typeof _ylg.count==="number"?_ylg.count:q.day+1)'
# dungeon2 E4：roguelike 本地冷却写入表达式（值源自常量，表达式不动）
FRZ_DG_CD_WRITE = 'cd:Date.now()+YLXW_DG_CD_MS}}catch(KS){}'
# 弹窗挂载（dg085 冻结面）
FRZ_REALM_MOUNT = 'e.jsx(cM,{isOpen:d.isRealmOpen'
FRZ_DG_MOUNT = 'e.jsx(vk,{isOpen:c.isDungeonOpen'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 eco085/dungeon085/dungeon2）；
    ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检 1：替换串必须真的变了，且倍率/分钟数真的拼了进去（防手滑写成恒等）
    if V_OLD == V_NEW or 'YlxwSrBoostR62' not in V_NEW:
        raise AssertionError('r062 锚点异常：V 点分流包裹未生效')
    if CD_VAR_OLD == CD_VAR_NEW or ('= %d * 60 * 1000;' % R062_CD_MIN) not in CD_VAR_NEW:
        raise AssertionError('r062 锚点异常：CD 常量未改')
    if CD_TXT_OLD == CD_TXT_NEW or (' %d ' % R062_CD_MIN) not in CD_TXT_NEW:
        raise AssertionError('r062 锚点异常：CD 文案未改')
    if R062_SR_GAIN_R62 <= 0 or R062_CD_MIN <= 0:
        raise AssertionError('r062 常量异常：倍率/分钟数必须为正')

    blk = zh(INJECT_JS)
    # 自检 2：注入块 zh() 后纯 ASCII 且不含禁用模式
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r062 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for pat in BAN_PATTERNS:
        if pat in blk:
            raise AssertionError('r062 注入块含禁用模式 %r' % pat)
    if 'fetch(' in blk:
        raise AssertionError('r062 注入块不得含 fetch(')

    # 0) 注入倍率常量 + 提升函数（模块级，函数声明提升，位置不影响调用）
    p.insert_before('r062-boost-fn', INJECT_ANCHOR, blk + '\n', expect=1,
                    note='注入 YLXW_SR_GAIN_R62 + YlxwSrBoostR62（弹窗秘境事件收益 ×%d）' % R062_SR_GAIN_R62)

    # 1) ① 弹窗秘境结算点按类型分流（只包 secret_realm；其它类型恒等）
    p.replace('r062-v-boost', V_OLD, V_NEW, expect=1,
              note='弹窗秘境事件收益 ×%d（Q==="secret_realm" 分流；主历练/lucky/宗门恒等）' % R062_SR_GAIN_R62)

    # 2) ② 冷却常量 5→15 分钟（E4 表达式与门禁文案的取值源）
    p.replace('r062-cd-var', CD_VAR_OLD, CD_VAR_NEW, expect=1,
              note='YLXW_DG_CD_MS 5→%d 分钟（服务端 DUNGEON_ENTRY_CD_MS=900_000 由 srv_patch_062.py 同改）' % R062_CD_MIN)

    # 3) ② 冷却展示文案 5→15 分钟（\u 转义形态）
    p.replace('r062-cd-text', CD_TXT_OLD, CD_TXT_NEW, expect=1,
              note='展示文案「每次探索后冷却 %d 分钟」' % R062_CD_MIN)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本模块改动：收益 ×%d =================
        ('R62·提升函数已定义',        'function YlxwSrBoostR62(e0)',                     1, '==', ''),
        ('R62·倍率常量=3',            'var YLXW_SR_GAIN_R62 = %d;' % R062_SR_GAIN_R62,   1, '==', '调参只改 R062_SR_GAIN_R62'),
        ('R62·倍率非有限/非正恒等',    'if (!isFinite(g0) || g0 <= 0) return e0;',        1, '==', '防 NaN 毁档'),
        ('R62·exp 正值才放大',        'if (isFinite(x0) && x0 > 0) o0.expChange = Math.floor(x0 * g0);', 1, '==', 'hpChange/负值不碰'),
        ('R62·灵石正值才放大',        'if (isFinite(s0) && s0 > 0) o0.spiritStonesChange = Math.floor(s0 * g0);', 1, '==', ''),
        ('R62·V 点已按类型分流',      V_NEW,                                             1, '==', '只包 secret_realm；内层 Ym 串逐字保留'),
        ('R62·分流条件串',            'Q==="secret_realm"?YlxwSrBoostR62:function(e0){return e0})(', 1, '==', ''),
        ('R62·旧 V 点形态已清零',     V_OLD,                                             0, '==', 'eco085 门禁需主控同步改（见文件头）'),
        ('R62·内层 Ym 主历练调用仍在', 'Ym(oe,{realm:t.realm,realmLevel:t.realmLevel,maxHp:F.maxHp},YLXW_STONE_MUL_ADV)', 1, '==', '仅被包裹，未改调用'),
        ('R62·倍率引用恰2处',         'YLXW_SR_GAIN_R62',                                2, '==', '声明 + 函数内 1 用'),
        # ================= 本模块改动：冷却 15 分钟 =================
        ('R62·冷却常量 15 分钟',      CD_VAR_NEW,                                        1, '==', 'dungeon2 门禁需主控同步改（见文件头）'),
        ('R62·旧 5 分钟常量已清零',   CD_VAR_OLD,                                        0, '==', ''),
        ('R62·冷却文案 15 分钟',      CD_TXT_NEW,                                        1, '==', ''),
        ('R62·旧 5 分钟文案已清零',   CD_TXT_OLD,                                        0, '==', ''),
        ('R62·CD 标识符恒 2 处',      'YLXW_DG_CD_MS',                                   2, '==', '声明 + E4 写入（probe 实测 2；改值不改标识符）'),

        # ================= 冻结：0.8.5 eco（秘境深处 / roguelike / 宗门 / 战斗）=================
        ('冻结·秘境深处调用未动',     FRZ_DELVE_CALL,                                    1, '==', '5% 奇遇触发站，YLXW_STONE_MUL_SR 面，不 boost'),
        ('冻结·秘境深处乘子未动',     FRZ_DELVE_MUL,                                     1, '==', ''),
        ('冻结·roguelike G3 未动',    FRZ_G3,                                            1, '==', 'roguelike 收益面，不 boost'),
        ('冻结·宗门奇遇未动',         FRZ_SECT_YM,                                       1, '==', '3 次/日，eco085 明确不动'),
        ('冻结·战斗 By 未动',         FRZ_BY,                                            1, '==', '秘境战斗分支已带 $y 风险乘子'),
        # ================= 冻结：Ym 内部（R-044 / R-043 面）=================
        ('冻结·Ym 签名未动',          'function Ym(t,r,_ylm){',                          1, '==', ''),
        ('冻结·Ym exp 路径未动',      FRZ_YM_EXP,                                        1, '==', 'R-044 历练修为产出面'),
        ('冻结·Ym 灵石路径未动',      FRZ_YM_STONE,                                      1, '==', ''),
        ('冻结·Ym hp 折算未动',       FRZ_R043_HP,                                       1, '==', 'R-043 掉血改缓面'),
        ('冻结·Ym 单次钳制未动',      FRZ_YM_CAP,                                        1, '==', 'R-043 冻结面'),
        # ================= 冻结：R-063 面（上限/计数拆分）=================
        ('冻结·上限表 10→20 未动',    FRZ_DG_CAP,                                        1, '==', 'R-063 的活，别越界'),
        ('冻结·上限调用点恒 6',       FRZ_DG_CAP_CALLS,                                  6, '==', 'disabled/className/children/E2b/E2c/E9'),
        ('冻结·计数回灌未动',         FRZ_DG_CNT,                                        1, '==', 'R-063 上限拆分的主锚，一字未动'),
        ('冻结·roguelike 冷却写入表达式未动', FRZ_DG_CD_WRITE,                           1, '==', 'dungeon2 E4；15 分钟来自常量值'),
        # ================= 冻结：弹窗挂载 =================
        ('冻结·经典秘境弹窗挂载未动', FRZ_REALM_MOUNT,                                   1, '==', 'dg085 冻结面'),
        ('冻结·roguelike 弹窗挂载未动', FRZ_DG_MOUNT,                                    1, '==', 'dg085 冻结面'),
    ]
    return gates
