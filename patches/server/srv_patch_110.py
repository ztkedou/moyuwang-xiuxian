# -*- coding: utf-8 -*-
r"""
srv_patch_110.py — R-110 悟道体系十道化（服务端环 · 新增暴伤/闪避/减伤/吸血 + 排序 + 境界门槛 + 逐道重命名）

需求原文（台账 R-110，逐字）
--------------------------------------------------------------------------
  「悟道干脆把暴伤  闪避  吸血 减伤  这几项内容也加上，并且按照这样上下排序：
   气血（炼气可买顿悟）攻击 、防御（筑基解锁这两项）暴击 暴伤（金丹解锁）
   闪避 减伤 吸血 （元婴）修炼（化神）资源（长生）。并且重构每一种道的名称」

前置取证结论（本轮独立复核，见 报告_R110_悟道十道_20261001.md）
--------------------------------------------------------------------------
  · 悟道系统**全在服务端** `[wudaocore]` 块 + GET/POST /api/wudao。
    客户端 `YlxwTWudao` 是**纯视图**：`((t && t.daos) || []).map(...)` 动态枚举，只渲染
    `g.name / g.level / g.exp / g.expToNext / g.bonusText`，点按钮 POST `{dao: g.key}`。
    客户端 bundle 实测：WUDAO_DAOS / wudaoExpToReach / WUDAO_MANUAL_COST / wudaoBonusPct 均 **0 次**，
    未硬编码道 id（'array:'/'tame:' = 0）⇒ **展示顺序与名称完全由服务端下发数组决定，客户端零改动**。
  · 现有 6 道的加成**在服务端无任何战斗/属性消费点**：`wudaoBonusPct()` 只被 GET/POST 端点用于
    生成 `bonusPct` / `bonusText` 两个**展示字段**下发给客户端；客户端也**不消费** daos[].stat/bonusPct
    （只当文本渲染）。即「加成」当前是「权威数值 + 伴生页展示」架构（与 [gongfacore] 同边界，注释自述
    "客户端接管后即插即用"），**并无 wudao→战斗 的结算管线**。
  · 新 4 stat 在客户端战斗模型里的既有字段名（供未来接线）：critDamage ✓（49 处）、
    damageReduction ✓（47 处）、dodge/dodgeRate ✓（74/42 处）；**吸血**客户端既有键为 `lifeLeech`
    （38 处），无 `lifesteal`。本环 `stat` 仅作元数据（无消费方），按需求表取 critDamage/dodge/
    damageReduction/lifesteal；接线时吸血需 1 行映射 lifesteal→lifeLeech（见报告「残余风险」）。

────────────────────────────────────────────────────────────────────────────
改前 6 道结构（基座 + R-091 环 srv_patch_101.py 产物）
--------------------------------------------------------------------------
  序 key    名称    stat        statName    门槛(R-091)
  1  sword  剑道    attack      攻击        炼气 0
  2  body   体道    defense     防御        炼气 0
  3  pill   丹道    maxHp       气血        炼气 0
  4  spell  法道    crit        暴击        炼气 0
  5  array  阵道    cultivate   修炼速度    元婴 3
  6  tame   御道    gather      资源产出    化神 4

改后 10 道结构（本环，顺序即客户端展示顺序）
--------------------------------------------------------------------------
  序 key    道名   stat             statName  解锁境界(序)   basePct/stepPct  来源
  1  pill   血道   maxHp            气血      炼气期 0       2.0 / 0.5        旧键保留（改名）
  2  sword  剑道   attack           攻击      筑基期 1       2.0 / 0.5        旧键保留
  3  body   体道   defense          防御      筑基期 1       2.0 / 0.5        旧键保留
  4  spell  法道   crit             暴击      金丹期 2       1.0 / 0.25       旧键保留
  5  edge   锋道   critDamage       暴伤      金丹期 2       1.0 / 0.25       ★新增
  6  shadow 影道   dodge            闪避      元婴期 3       1.0 / 0.25       ★新增
  7  armor  甲道   damageReduction  减伤      元婴期 3       1.0 / 0.25       ★新增
  8  devour 噬道   lifesteal        吸血      元婴期 3       1.0 / 0.25       ★新增
  9  array  禅道   cultivate        修炼      化神期 4       1.0 / 0.25       旧键保留（改名+门槛 3→4）
  10 tame   丰道   gather           资源      长生境 6       1.0 / 0.25       旧键保留（改名+门槛 4→6）

  ★ 门槛序澄清：游戏真实境界序为 7 档 —— 炼气0/筑基1/金丹2/元婴3/化神4/合道5/长生境6
    （REALM_ORDER_FOR_RANKING / DUNGEON_REALM_ORDER / WUDAO_REALM_ORDER 三处同源同序，已核）。
    需求表第 10 行「长生期 (5)」名称与序号自相矛盾（序 5 = 合道期）；用户原文为「资源（长生）」，
    且其余 9 行「名称↔序号」全部自洽 ⇒ 判定「(5)」系按 6 档误数，取**名称**口径 = 长生境(6)。

★存量兼容策略（关键，零丢失）
--------------------------------------------------------------------------
  · **保留全部旧 key**（pill/sword/body/spell/array/tame）与其 level/exp 不变 —— 玩家进度存于
    `wudao(player_id, dao_type, level, exp)`，按 dao_type 存续；本环**只改 name/statName**，
    不动 key ⇒ 存量等级 100% 保留（升级曲线 wudaoExpToReach 亦逐字未动）。
  · 新 4 键（edge/shadow/armor/devour）**追加**在对象字面量末尾；展示顺序 = `Object.keys(WUDAO_DAOS)`
    插入序（JS 字符串键有序），故把 10 条按目标顺序重写字面量即得目标展示顺序，**客户端自动跟随**。
  · 境界门槛只挡「从未投入(exp<=0)」者：GET 下发 `locked = realmIdx<gate && exp<=0`，POST 对
    exp>0 者祖父放行（R-091 既有语义，逐字未动）。故 array 门槛 3→4、tame 门槛 4→6 **不会**锁死
    已投入的存量玩家。R-091 的一次性灵石补偿（幂等键 r091_wudao_respec）**原样保留**，不重复触发。

手动顿悟灵石价
--------------------------------------------------------------------------
  · 沿用 `WUDAO_MANUAL_COST_BY_REALM`（随**人物境界**递增：炼气 5000 → 长生 60000，≈12×），本环不改。
    新增道门槛落在高境界（金丹/元婴/化神/长生），玩家须达该境界方可顿悟 ⇒ 天然「高境界道更贵」，
    无需另设按道定价。

★本次改动清单（E1..E9，每处锚点 count==1）
--------------------------------------------------------------------------
  E1 WUDAO_DAOS 字面量：6 道 → 10 道（重排 + 重命名 + 追加 4 新键）
  E2 门槛表 WUDAO_DAO_REALM_GATE：6 项 → 10 项（含新道门槛）
  E3 GET /api/wudao 取数 `LIMIT 6` → 全量（否则新增 4 道被静默截断）
  E4..E9 文案/注释同步（六系→十系 / 六系之一→本人已开放的系之一 / 建表注释）

工程约束（照 srv_patch_101.py / srv_patch_064 / r078 惯例）
--------------------------------------------------------------------------
  · `--src <path>` 就地原子写回；`--check` / `--selftest` 只校验不写。
  · 幂等：产物已含 `[r110wudao]` 则 SKIP。每处替换 expect=1，命中数不符即中止；round-trip 自证后原子写回。
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval` / `PRAGMA`。
  · ⛔ 不改 srv/index_v28.ts（链产物）；⛔ 不改任何既有 srv_patch_*.py；⛔ 客户端零改动。
  · 链序：挂 SRV_CHAIN 链尾（锚区 [wudaocore] 块 / wudao 两端点 / tickWudaoIdle，与既有各环零交集）。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

MARK = "[r110wudao]"

# ============================================================ E1：十道字面量（重排 + 重命名 + 追加 4 新键）

E1_OLD = """\
const WUDAO_DAOS: Record<string, { name: string; stat: string; statName: string; basePct: number; stepPct: number }> = {
  sword: { name: '剑道', stat: 'attack', statName: '攻击', basePct: 2.0, stepPct: 0.5 },
  body:  { name: '体道', stat: 'defense', statName: '防御', basePct: 2.0, stepPct: 0.5 },
  pill:  { name: '丹道', stat: 'maxHp', statName: '气血', basePct: 2.0, stepPct: 0.5 },
  spell: { name: '法道', stat: 'crit', statName: '暴击', basePct: 1.0, stepPct: 0.25 },
  // [r101wudao] R-091 去重：阵道 攻击→修炼速度、御道 气血→资源产出（六道定位互不重复）
  array: { name: '阵道', stat: 'cultivate', statName: '修炼速度', basePct: 1.0, stepPct: 0.25 },
  tame:  { name: '御道', stat: 'gather', statName: '资源产出', basePct: 1.0, stepPct: 0.25 },
};"""

E1_NEW = """\
const WUDAO_DAOS: Record<string, { name: string; stat: string; statName: string; basePct: number; stepPct: number }> = {
  // [r110wudao] R-110 悟道十道：顺序即客户端展示顺序（客户端动态枚举 daos[]，零改动自动跟随）。
  //   ① 旧 6 键（pill/sword/body/spell/array/tame）原样保留 —— 其 level/exp 存于 wudao 表（按 key 存续），
  //      本环只改 name/statName、绝不改 key ⇒ 存量等级 100% 不丢；
  //   ② 新增 4 键（edge/shadow/armor/devour）追加于后，接同一条加成/展示管线（wudaoBonusPct → bonusText）；
  //   ③「重构每一种道的名称」：十道各取语义匹配且互不重复的道名（血/剑/体/法/锋/影/甲/噬/禅/丰）。
  pill:   { name: '血道', stat: 'maxHp',           statName: '气血', basePct: 2.0, stepPct: 0.5  }, // 1 气血（炼气期开放）
  sword:  { name: '剑道', stat: 'attack',          statName: '攻击', basePct: 2.0, stepPct: 0.5  }, // 2 攻击（筑基期）
  body:   { name: '体道', stat: 'defense',         statName: '防御', basePct: 2.0, stepPct: 0.5  }, // 3 防御（筑基期）
  spell:  { name: '法道', stat: 'crit',            statName: '暴击', basePct: 1.0, stepPct: 0.25 }, // 4 暴击（金丹期）
  edge:   { name: '锋道', stat: 'critDamage',      statName: '暴伤', basePct: 1.0, stepPct: 0.25 }, // 5 暴伤（金丹期·新增）
  shadow: { name: '影道', stat: 'dodge',           statName: '闪避', basePct: 1.0, stepPct: 0.25 }, // 6 闪避（元婴期·新增）
  armor:  { name: '甲道', stat: 'damageReduction', statName: '减伤', basePct: 1.0, stepPct: 0.25 }, // 7 减伤（元婴期·新增）
  devour: { name: '噬道', stat: 'lifesteal',       statName: '吸血', basePct: 1.0, stepPct: 0.25 }, // 8 吸血（元婴期·新增）
  array:  { name: '禅道', stat: 'cultivate',       statName: '修炼', basePct: 1.0, stepPct: 0.25 }, // 9 修炼（化神期）
  tame:   { name: '丰道', stat: 'gather',          statName: '资源', basePct: 1.0, stepPct: 0.25 }, // 10 资源（长生境）
};"""

# ============================================================ E2：门槛表（6 项 → 10 项）

E2A_OLD = """\
// 稀有道门槛（境界序）：剑/体/丹/法 自炼气期(0)开放；阵道(第5道)元婴期(3)、御道(第6道)化神期(4)起开放。"""

E2A_NEW = """\
// [r110wudao] R-110 十道境界门槛（境界序）：血道(序1)炼气0；剑/体(2-3)筑基1；法/锋(4-5)金丹2；
//   影/甲/噬(6-8)元婴3；禅(9)化神4；丰(10)长生境6（★注：WUDAO_REALM_ORDER 序5=合道期、序6=长生境；
//   用户原文「资源（长生）」，故取长生境=6，与「名称」口径一致）。"""

E2B_OLD = """\
const WUDAO_DAO_REALM_GATE: Record<string, number> = { sword: 0, body: 0, pill: 0, spell: 0, array: 3, tame: 4 };"""

E2B_NEW = """\
const WUDAO_DAO_REALM_GATE: Record<string, number> = { pill: 0, sword: 1, body: 1, spell: 2, edge: 2, shadow: 3, armor: 3, devour: 3, array: 4, tame: 6 };"""

# ============================================================ E3：GET 取数 LIMIT 6 → 全量（否则新增 4 道被截断）

E3_OLD = """\
      dbAll('SELECT dao_type, exp FROM wudao WHERE player_id = ? LIMIT 6', [userId]),"""

E3_NEW = """\
      dbAll('SELECT dao_type, exp FROM wudao WHERE player_id = ?', [userId]), // [r110wudao] R-110：原 LIMIT 6 会截断新增四道，改全量（PK(player_id,dao_type) 天然限 10 行）"""

# ============================================================ E4：模块头注释（六系 → 十系）

E4_OLD = """\
// 六系悟道（剑/丹/体/法/阵/御），每系独立 1..10 级，exp 只增不减；数值为本次定档，常量集中可调。"""

E4_NEW = """\
// 十系悟道（血/剑/体/法/锋/影/甲/噬/禅/丰），每系独立 1..10 级，exp 只增不减；数值为本次定档，常量集中可调。"""

# ============================================================ E5：挂机心得注释（随机落入六系之一 → 已开放的系）

E5_OLD = """\
// 挂机心得：每分钟 roll 一次，8% 命中=1 条心得（=期望 4.8 条/小时），随机落入六系之一；"""

E5_NEW = """\
// 挂机心得：每分钟 roll 一次，8% 命中=1 条心得（=期望 4.8 条/小时），随机落入本人已开放的系之一；"""

# ============================================================ E6：tickWudaoIdle 注释（同上）

E6_OLD = """\
// 每分钟 roll 8% 得 1 条心得（+10 exp），随机落入六系之一。fire-and-forget 自吞异常，绝不阻塞存档路径；"""

E6_NEW = """\
// 每分钟 roll 8% 得 1 条心得（+10 exp），随机落入本人已开放的系之一。fire-and-forget 自吞异常，绝不阻塞存档路径；"""

# ============================================================ E7：API 头注释（六系 → 十系）

E7_OLD = """\
// WUDAO（R-GAME3）悟道 API（伴生页 /yl/apps/wudao/）：六系悟道（剑/丹/体/法/阵/御）各 1..10 级。"""

E7_NEW = """\
// WUDAO（R-GAME3）悟道 API（伴生页 /yl/apps/wudao/）：十系悟道（血/剑/体/法/锋/影/甲/噬/禅/丰）各 1..10 级。"""

# ============================================================ E8：GET 端点注释（六系 → 十系）

E8_OLD = """\
// GET /api/wudao — 六系等级+exp+加成列表+悟道日志+灵石余额（一页全量，不落账）"""

E8_NEW = """\
// GET /api/wudao — 十系等级+exp+加成列表+悟道日志+灵石余额（一页全量，不落账）"""

# ============================================================ E9：建表注释（悟道六系 → 十系）

E9_OLD = """\
  // WUDAO（R-GAME3）：悟道六系——每玩家每系至多一行（PK 幂等）；exp=该系累计修为（只增不减，"""

E9_NEW = """\
  // WUDAO（R-GAME3）：悟道十系——每玩家每系至多一行（PK 幂等）；exp=该系累计修为（只增不减，"""

EDITS = [
    ("E1 十道字面量（重排+重命名+追加4新键）", E1_OLD, E1_NEW),
    ("E2A 门槛注释（十道境界档）", E2A_OLD, E2A_NEW),
    ("E2B 门槛表（6项→10项）", E2B_OLD, E2B_NEW),
    ("E3 GET 取数 LIMIT 6→全量", E3_OLD, E3_NEW),
    ("E4 模块头注释（六系→十系）", E4_OLD, E4_NEW),
    ("E5 挂机心得注释", E5_OLD, E5_NEW),
    ("E6 tickWudaoIdle 注释", E6_OLD, E6_NEW),
    ("E7 API 头注释（六系→十系）", E7_OLD, E7_NEW),
    ("E8 GET 端点注释（六系→十系）", E8_OLD, E8_NEW),
    ("E9 建表注释（六系→十系）", E9_OLD, E9_NEW),
]

# 十道展示顺序（用于语义自证：字面量中各行出现位置必须严格递增）
ORDER_MARKERS = [
    "pill:   { name: '血道'",
    "sword:  { name: '剑道'",
    "body:   { name: '体道'",
    "spell:  { name: '法道'",
    "edge:   { name: '锋道'",
    "shadow: { name: '影道'",
    "armor:  { name: '甲道'",
    "devour: { name: '噬道'",
    "array:  { name: '禅道'",
    "tame:   { name: '丰道'",
]

REQUIRES = [
    ("const WUDAO_MAX_LEVEL = 10;", 1, "等级上限（冻结面，本环不动）"),
    ("const WUDAO_BONUS_UNLOCK_LEVEL = 3;", 1, "加成解锁级（冻结面，本环不动）"),
    ("  return 25 * (l - 1) * l;", 1, "升级曲线纯函数（★本环刻意不动，保存量等级零降级）"),
    ("const WUDAO_INSIGHT_CHANCE = 0.04;", 1, "挂机命中率（冻结面，本环不动）"),
    ("const WUDAO_INSIGHT_EXP = 10;", 1, "心得修为（冻结面，本环不动）"),
    ("const WUDAO_MANUAL_COST = 5000;", 1, "手动顿悟基础价（价格表首档，本环不动）"),
    ("const WUDAO_MANUAL_EXP = 100;", 1, "手动顿悟单次 exp（冻结面，本环不动）"),
    ("const WUDAO_LOG_KEEP = 50;", 1, "日志裁剪条数（冻结面）"),
    ("const WUDAO_MANUAL_COST_BY_REALM: number[] = [WUDAO_MANUAL_COST, 8000, 12000, 18000, 27000, 40000, 60000];", 1, "灵石价随境界递增表（沿用，本环不动）"),
    ("function wudaoDaoGateRealm(daoKey: string): number {", 1, "门槛取用函数（逐字不动）"),
    ("const WUDAO_RESPEC_REFUND_PER_EXP = 50;", 1, "R-091 祖父条款补偿率（原样保留）"),
    ("async function wudaoRespecCompensateOnce(userId: number): Promise<void> {", 1, "R-091 祖父条款补偿助手（原样保留）"),
    ("app.get('/api/wudao', authenticateToken", 1, "GET 端点唯一"),
    ("app.post('/api/wudao/insight', authenticateToken", 1, "POST 端点唯一"),
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-110 悟道十道环（服务端 r110）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点计数（恰 1）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    base403 = src.count("res.status(403")
    base_req = src.count("require(")
    base_itv = src.count("setInterval(")
    base_prg = src.count("PRAGMA")

    # 4) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 5) 门禁
    gates = [
        # ---- 新十道齐备（逐行）----
        ("R110 血道(气血)@1", "  pill:   { name: '血道', stat: 'maxHp',           statName: '气血', basePct: 2.0, stepPct: 0.5  },", 1),
        ("R110 剑道(攻击)@2", "  sword:  { name: '剑道', stat: 'attack',          statName: '攻击', basePct: 2.0, stepPct: 0.5  },", 1),
        ("R110 体道(防御)@3", "  body:   { name: '体道', stat: 'defense',         statName: '防御', basePct: 2.0, stepPct: 0.5  },", 1),
        ("R110 法道(暴击)@4", "  spell:  { name: '法道', stat: 'crit',            statName: '暴击', basePct: 1.0, stepPct: 0.25 },", 1),
        ("R110 锋道(暴伤)@5★新", "  edge:   { name: '锋道', stat: 'critDamage',      statName: '暴伤', basePct: 1.0, stepPct: 0.25 },", 1),
        ("R110 影道(闪避)@6★新", "  shadow: { name: '影道', stat: 'dodge',           statName: '闪避', basePct: 1.0, stepPct: 0.25 },", 1),
        ("R110 甲道(减伤)@7★新", "  armor:  { name: '甲道', stat: 'damageReduction', statName: '减伤', basePct: 1.0, stepPct: 0.25 },", 1),
        ("R110 噬道(吸血)@8★新", "  devour: { name: '噬道', stat: 'lifesteal',       statName: '吸血', basePct: 1.0, stepPct: 0.25 },", 1),
        ("R110 禅道(修炼)@9", "  array:  { name: '禅道', stat: 'cultivate',       statName: '修炼', basePct: 1.0, stepPct: 0.25 },", 1),
        ("R110 丰道(资源)@10", "  tame:   { name: '丰道', stat: 'gather',          statName: '资源', basePct: 1.0, stepPct: 0.25 },", 1),
        # ---- 旧形态清零 ----
        ("R110 旧丹道名已清零", "  pill:  { name: '丹道'", 0),
        ("R110 旧阵道名已清零", "  array: { name: '阵道'", 0),
        ("R110 旧御道名已清零", "  tame:  { name: '御道'", 0),
        ("R110 旧修炼速度名已清零", "statName: '修炼速度'", 0),
        ("R110 旧资源产出名已清零", "statName: '资源产出'", 0),
        ("R110 旧字面量头已清零", "const WUDAO_DAOS: Record<string, { name: string; stat: string; statName: string; basePct: number; stepPct: number }> = {\n  sword:", 0),
        # ---- 新 stat 落点 ----
        ("R110 stat critDamage", "stat: 'critDamage'", 1),
        ("R110 stat dodge(含gongfa御灵术)", "stat: 'dodge'", 2),
        ("R110 stat damageReduction", "stat: 'damageReduction'", 1),
        ("R110 stat lifesteal", "stat: 'lifesteal'", 1),
        # ---- 门槛表 ----
        ("R110 十项门槛表", "const WUDAO_DAO_REALM_GATE: Record<string, number> = { pill: 0, sword: 1, body: 1, spell: 2, edge: 2, shadow: 3, armor: 3, devour: 3, array: 4, tame: 6 };", 1),
        ("R110 旧六项门槛表已清零", "const WUDAO_DAO_REALM_GATE: Record<string, number> = { sword: 0, body: 0, pill: 0, spell: 0, array: 3, tame: 4 };", 0),
        # ---- GET 取数 ----
        ("R110 GET 取数改全量", "dbAll('SELECT dao_type, exp FROM wudao WHERE player_id = ?', [userId]), // [r110wudao]", 1),
        ("R110 GET 旧 LIMIT 6 已清零", "SELECT dao_type, exp FROM wudao WHERE player_id = ? LIMIT 6", 0),
        # ---- 文案同步 ----
        ("R110 模块头十系", "// 十系悟道（血/剑/体/法/锋/影/甲/噬/禅/丰），每系独立 1..10 级", 1),
        ("R110 API 头十系", "// WUDAO（R-GAME3）悟道 API（伴生页 /yl/apps/wudao/）：十系悟道", 1),
        ("R110 GET 注释十系", "// GET /api/wudao — 十系等级+exp+", 1),
        ("R110 挂机注释(已开放的系)", "随机落入本人已开放的系之一；", 1),
        ("R110 tick 注释(已开放的系)", "随机落入本人已开放的系之一。fire-and-forget", 1),
        ("R110 建表注释十系", "// WUDAO（R-GAME3）：悟道十系——每玩家每系至多一行（PK 幂等）", 1),
        ("R110 旧「六系」注释清零", "六系", 0),
        ("R110 旧「六道」注释清零", "六道", 0),
        # ---- 冻结：曲线/常量/R-091 补偿一字不动 ----
        ("冻结 升级曲线未动", "  return 25 * (l - 1) * l;", 1),
        ("冻结 等级上限未动", "const WUDAO_MAX_LEVEL = 10;", 1),
        ("冻结 加成解锁级未动", "const WUDAO_BONUS_UNLOCK_LEVEL = 3;", 1),
        ("冻结 手动 exp 未动", "const WUDAO_MANUAL_EXP = 100;", 1),
        ("冻结 基础价常量未动", "const WUDAO_MANUAL_COST = 5000;", 1),
        ("冻结 灵石价表未动", "const WUDAO_MANUAL_COST_BY_REALM: number[] = [WUDAO_MANUAL_COST, 8000, 12000, 18000, 27000, 40000, 60000];", 1),
        ("冻结 R-091 补偿助手未动", "async function wudaoRespecCompensateOnce(userId: number): Promise<void> {", 1),
        ("冻结 R-091 补偿触发仍 2 处", "await wudaoRespecCompensateOnce(userId);", 2),
        ("冻结 GET locked 祖父放行", "const locked = realmIdx < gateRealm && exp <= 0; // 已投入者祖父放行，不追溯锁死", 1),
        ("冻结 幂等标记就位", MARK, 3),
        # ---- 红线 ----
        ("红线 未新增 res.status(403)", "res.status(403", base403),
        ("红线 未新增 require(", "require(", base_req),
        ("红线 未新增 setInterval", "setInterval(", base_itv),
        ("红线 未新增 PRAGMA", "PRAGMA", base_prg),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 6) 语义自证：十道在产物中的出现位置必须严格递增（= 展示顺序）
    positions = [out.find(m) for m in ORDER_MARKERS]
    mono = all(p >= 0 for p in positions) and all(positions[i] < positions[i + 1] for i in range(len(positions) - 1))
    ok = ok and mono
    print("  [%s] %-40s %s" % ("OK" if mono else "FAIL", "R110 十道展示顺序严格递增", positions))

    # 语义自证：新 4 stat 各恰好 1 次，且首尾道就位
    stat_ok = (
        out.count("stat: 'critDamage'") == 1
        and out.count("stat: 'damageReduction'") == 1
        and out.count("stat: 'lifesteal'") == 1
        and out.count("  pill:   { name: '血道'") == 1
        and out.count("  tame:   { name: '丰道'") == 1
    )
    ok = ok and stat_ok
    print("  [%s] %-40s critDmg=%d dodge=%d dmgRed=%d lifesteal=%d"
          % ("OK" if stat_ok else "FAIL", "R110 新 4 stat 各就位",
             out.count("stat: 'critDamage'"), out.count("stat: 'dodge'"),
             out.count("stat: 'damageReduction'"), out.count("stat: 'lifesteal'")))

    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r110wudao-", suffix=".tmp")
    try:
        with io.open(fd, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print("  已原子写回 %s" % src_path)


if __name__ == "__main__":
    main()
