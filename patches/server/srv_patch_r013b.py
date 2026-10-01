# -*- coding: utf-8 -*-
r"""
srv_patch_r013b.py -- R-028 收尾（服务端环 r013b）：传承石移到最高档 + 改发实物

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` / `--selftest` 只校验不写。
  前置依赖：必须在 **econ2** 之后（本环锚点是 econ2 产出的 5 档 WEEK_MILESTONES）。
  lead 接线：把本环挂在 SRV_CHAIN 链尾（第 30 环）。

=========================================================================== 为什么还要改（R-028 两处不符）
用户 2026-09-30 拍板「两处都按 R-028 改」：R-028 原文「仙途任务中把本周勤修的任务奖励
重新规划一下，现在是 3 项内容，改为 5 项，**最高满活跃度才会给 1 个传承石**」。

econ2 已把「3 档 → 5 档」落定，但**传承石的两点仍不符**：

  不符点 1（位置）：传承石仍挂 **1,000 档**，而 R-028 要的是**最高档**。
  不符点 2（形态）：`MILE_MONTH_REWARD = 5000` 把传承石**折算成 5000 灵石**塞邮件附件
      （代码注释自陈是「P0 折算通道；P1 走正规物品通道」）。用户要的是**实物**，
      因为 R-013 要求它能上架交易行（幽灵/折算灵石都不可交易）。

=========================================================================== 改点（3 处 replace）
  E1 里程碑表 + 常量 + 实物构造器（`:4407-4421` 整块）
        · 传承石 `legacy:'传承石'` 由 **1000 档** 移到 **2310 档**（满活跃度）
        · 原 2310 的显示串 `'仙品道具+称号'` **下移 1900 档**保留（见「2310 处置」）
        · `MILE_MONTHLY_TIER` 1000 → **2310**（月限领跟随传承石）
        · 删 `MILE_MONTH_REWARD`（不再折算灵石，已成死常量）
        · 新增 `LEGACY_STONE_NAME` + `legacyStoneItem()`（实物构造器，字段与客户端逐字对齐）
  E2 端点上方注释（`:7020-7021`）：1,000 档 → 最高档 2,310，改发实物
  E3 端点发奖体（`:7041-7055`）：删「折算灵石」分支，改走 updatePlayerSave 背包通道发实物；
        发信失败则**补偿撤回**已发实物再删占位（同 mailClaimCore 补偿式事务，防重复发放）

=========================================================================== ★ 传承石实物的发放通道（侦察结论）
服务端**没有**通用「邮件附件发物品」通道 —— `insertMail()` 只有 `attached_lingshi`，
`mail` 表只有 `attached_lingshi` 列，`mailClaimCore()` 只把灵石加进 `player.spiritStones`。

但服务端**已有**一条现成的「给玩家背包加一件物品」通道，且已在生产使用：

    updatePlayerSave(userId, sd => { sd.player.inventory.push(item); })

  · `POST /api/sect/welfare/claim`（kind='pill'，`:13928-13936`）→ 发 `sectPillItem()`（宗门凝气丹）
  · `POST /api/gm/players/:id/grant`（`:2992-3014`）→ GM 发任意物品

`updatePlayerSave` 自带 saveLock 读改写互斥 + `gm_revision++`（促客户端拉新档）+
upsertRanking + 经济镜像，是**正规入档通道**。本环照此发传承石实物（同宗门丹药范式）。

物品字段与客户端 `yl_r013_ext.py` 的 `YlxwInhStoneItem()` **逐字对齐**：
    name='传承石' / type='材料' / rarity='仙品' / isEquippable=false
    description='先辈传承凝结的灵石，使用后传承等级 +1，亦可于交易行转售。'
  ⇒ 客户端两条链路天然可用：① 使用 +1 传承等级（`if(r.name==="传承石")`，T7 §2.4）；
    ② 交易行上架（服务端 `/api/market/list` 无物品白名单，任意背包物品可上架）。

=========================================================================== 2310 档「仙品道具+称号」的处置（用户未答，本环自定）
**决定：下移到 1900 档保留。**
  · `legacy` 是**单个**字符串，且服务端用它做 `mdef.legacy === '传承石'` 的**相等判定**
    ⇒ 不能把两个值拼进一格（`'传承石+仙品道具+称号'` 会让 `===` 失效，或被迫改判定语义）。
  · `'仙品道具+称号'` 在服务端**只是展示串**（econ2 报告 §52 实证：既不真发仙品道具、
    也不真发称号，仅进 `GET /api/quest/summary` 的 `milestones[].legacy`）⇒ 无行为风险。
  · 下移 1900 保住了原有文案内容，且让 1900 档有了专属标识；2310 档专表传承石，语义唯一。
  · 备选「直接删除」会丢内容；备选「拼接」会破坏相等判定 ⇒ 不取。

=========================================================================== ★ 副作用（必须让 lead / 用户知情）
`MILE_MONTHLY_TIER = 2310` 是**整行**月频：`claimKey` 与 `isMonthly` 都按该档判定
（`const isMonthly = mdef.tier === MILE_MONTHLY_TIER;`）。
  ⇒ **2,310 档的整份奖励（灵石 60k base + 修为等效 + 抽奖券 + 传承石）从「每周」变「每月」。**
按 team-lead 转述的指令「MILE_MONTHLY_TIER 从 1000 改成 2310（月限领跟随）」字面执行。
若用户本意是「只有传承石按月、2310 的灵石仍按周」，需另行解耦（本环未做，见报告 §6 待决）。

=========================================================================== 红线
  · **不新增任何 res.status(403)**（本环只改发奖体，不碰任何权限/次数闸门；基线 = 11）。
  · 不新增表 / 列 / 端点；不动 `mail` / `insertMail` / `mailClaimCore`（零副作用）。
  · 不改档位白名单 / 幂等 DDL / 周活跃度采集 / 403 闸门。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ E1 里程碑表 + 常量 + 实物构造器

E1_OLD = """// 周里程碑档位（门槛 = 周累计活跃度；wbase = 灵石 base；wexp = 打坐等效；wtk = 抽奖券）
//   ★ 1,000 档的「传承石 ×1」按用户拍板**降频为月**（不是每周）：见 MILE_MONTHLY_TIER。
//   ★ R-028（econ2 环）：3 档 → 5 档（500/1000/1500/1900/2310），
//     灵石 base 总额 125k → 160k/周。顶端 2310 = ACTIVITY_MAX(330) × 7（周活跃度打满）。
//     与客户端 YlxwQMile 同表；wexp = wbase/100（沿用旧表比例）。
//     传承石仍挂 1,000 档（MILE_MONTHLY_TIER 未动，按月限领），**不改为周**。
const WEEK_MILESTONES: Array<{ tier: number; wbase: number; wexp: number; wtk: number; legacy: string }> = [
  { tier: 500,  wbase: 10000, wexp: 100, wtk: 4,  legacy: '' },
  { tier: 1000, wbase: 20000, wexp: 200, wtk: 9,  legacy: '传承石' },
  { tier: 1500, wbase: 30000, wexp: 300, wtk: 14, legacy: '' },
  { tier: 1900, wbase: 40000, wexp: 400, wtk: 21, legacy: '' },
  { tier: 2310, wbase: 60000, wexp: 600, wtk: 30, legacy: '仙品道具+称号' },
];
const MILE_MONTHLY_TIER = 1000; // 该档的 legacy 额外奖励（传承石）按「月」限领一次，其余按周
const MILE_MONTH_REWARD = 5000; // 传承石折算灵石（P0 折算通道；P1 走正规物品通道）"""

E1_NEW = """// 周里程碑档位（门槛 = 周累计活跃度；wbase = 灵石 base；wexp = 打坐等效；wtk = 抽奖券）
//   ★ R-028（econ2 环）：3 档 → 5 档（500/1000/1500/1900/2310），灵石 base 总额 125k → 160k/周。
//     顶端 2310 = ACTIVITY_MAX(330) × 7（周活跃度打满）；wexp = wbase/100；与客户端 YlxwQMile 同表。
//   ★ R-013b：传承石移到**最高档 2310**（满活跃度才给），并改发**实物**（背包通道 legacyStoneItem），
//     不再折算灵石。原 2310 的展示串 '仙品道具+称号' 下移 1900 档保留（见 报告_r013b.md §4）。
const WEEK_MILESTONES: Array<{ tier: number; wbase: number; wexp: number; wtk: number; legacy: string }> = [
  { tier: 500,  wbase: 10000, wexp: 100, wtk: 4,  legacy: '' },
  { tier: 1000, wbase: 20000, wexp: 200, wtk: 9,  legacy: '' },
  { tier: 1500, wbase: 30000, wexp: 300, wtk: 14, legacy: '' },
  { tier: 1900, wbase: 40000, wexp: 400, wtk: 21, legacy: '仙品道具+称号' },
  { tier: 2310, wbase: 60000, wexp: 600, wtk: 30, legacy: '传承石' },
];
const MILE_MONTHLY_TIER = 2310; // 该档的 legacy 额外奖励（传承石）按「月」限领一次，其余按周
// R-013b：传承石**实物**发放。名称/类型/稀有度与客户端 yl_r013_ext.py 的 YlxwInhStoneItem 逐字对齐
//   （name='传承石' / type='材料' / rarity='仙品' / isEquippable=false）⇒ 交易行上架、使用 +1 传承等级
//   两条客户端链路天然可用。发放走 updatePlayerSave 背包通道（同宗门丹药 sectPillItem 范式）。
const LEGACY_STONE_NAME = '传承石';
function legacyStoneItem(): any {
  return {
    id: `inh-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`,
    name: LEGACY_STONE_NAME,
    type: '材料',
    description: '先辈传承凝结的灵石，使用后传承等级 +1，亦可于交易行转售。',
    quantity: 1,
    rarity: '仙品',
    effect: {},
    permanentEffect: {},
    isEquippable: false,
    level: 0,
  };
}"""

# ============================================================ E2 端点上方注释

E2_OLD = """//   T9 0.8.8：幂等靠 activity_milestones 的 UNIQUE(user_id, week, tier)（周）；
//   1,000 档的「传承石」额外奖励按用户拍板**降频为月**（UNIQUE(user_id, month_key, -tier) 占位）。"""

E2_NEW = """//   T9 0.8.8：幂等靠 activity_milestones 的 UNIQUE(user_id, week, tier)（周）；
//   R-013b：最高档 2,310 的「传承石」额外奖励按月限领一次（MILE_MONTHLY_TIER=2310），改发实物。"""

# ============================================================ E3 端点发奖体

E3_OLD = """    const baseReward = Math.floor(mdef.wbase * rf);
    const expStone = Math.floor(mdef.wexp * CHEST_EXP_TO_STONE);
    const legacyStone = isMonthly && mdef.legacy === '传承石' ? MILE_MONTH_REWARD : 0;
    const totalStone = baseReward + expStone + legacyStone;
    const detail = `灵石 ×${baseReward}、修为等效 ×${mdef.wexp}（折灵石 ×${expStone}）`
      + (legacyStone > 0 ? `、传承石 ×1（折灵石 ×${legacyStone}，每月限一次）` : '')
      + (mdef.wtk > 0 ? `、抽奖券 ×${mdef.wtk}` : '');
    try {
      await insertMail(userId, '周里程碑·勤修', `本周活跃度达到 ${tier}，${detail} 已附上（合计灵石 ×${totalStone}），点击领取。`, 'system', totalStone);
      res.json({ ok: true, tier, reward: totalStone, week, weekActivity, monthly: isMonthly });
    } catch (e: any) {
      console.error('milestone mail error:', e?.message || e);
      await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, claimKey, tier]);
      res.status(500).json({ error: '发奖失败，请重试' });
    }"""

E3_NEW = """    const baseReward = Math.floor(mdef.wbase * rf);
    const expStone = Math.floor(mdef.wexp * CHEST_EXP_TO_STONE);
    // R-013b：传承石改发**实物**（走 updatePlayerSave 背包通道，同宗门丹药 sectPillItem），
    //   不再折算成灵石塞邮件附件。实物先发；发信失败则补偿撤回（见下，防重复发放）。
    const grantStone = isMonthly && mdef.legacy === '传承石';
    const totalStone = baseReward + expStone;
    const detail = `灵石 ×${baseReward}、修为等效 ×${mdef.wexp}（折灵石 ×${expStone}）`
      + (grantStone ? `、传承石 ×1（实物已入背包，每月限一次）` : '')
      + (mdef.wtk > 0 ? `、抽奖券 ×${mdef.wtk}` : '');
    let grantedStoneId = '';
    if (grantStone) {
      const stone = legacyStoneItem();
      grantedStoneId = stone.id;
      const g = await updatePlayerSave(userId, (sd: any) => {
        if (!sd.player || typeof sd.player !== 'object') sd.player = {};
        sd.player.inventory = Array.isArray(sd.player.inventory) ? sd.player.inventory : [];
        sd.player.inventory.push(stone);
      });
      if (!g.ok) {
        await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, claimKey, tier]);
        return res.status(500).json({ error: '发奖失败，请重试' });
      }
    }
    try {
      await insertMail(userId, '周里程碑·勤修', `本周活跃度达到 ${tier}，${detail} 已附上（合计灵石 ×${totalStone}），点击领取。`, 'system', totalStone);
      res.json({ ok: true, tier, reward: totalStone, week, weekActivity, monthly: isMonthly, item: grantStone ? LEGACY_STONE_NAME : undefined });
    } catch (e: any) {
      console.error('milestone mail error:', e?.message || e);
      // 补偿式回滚（同 mailClaimCore）：撤回已发的传承石，再删占位，玩家可重试（防重复发放）
      if (grantedStoneId) {
        await updatePlayerSave(userId, (sd: any) => {
          if (Array.isArray(sd.player?.inventory)) {
            const i = sd.player.inventory.findIndex((x: any) => x && x.id === grantedStoneId);
            if (i >= 0) sd.player.inventory.splice(i, 1);
          }
        }).catch(() => undefined);
      }
      await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, claimKey, tier]);
      res.status(500).json({ error: '发奖失败，请重试' });
    }"""

EDITS = [
    ("E1 里程碑表+常量+实物构造器", E1_OLD, E1_NEW),
    ("E2 端点上方注释",             E2_OLD, E2_NEW),
    ("E3 端点发奖体改实物",         E3_OLD, E3_NEW),
]

# 前置依赖（econ2 之后的形态，必须逐条在位；本环只读这些串做自证，不改）
REQUIRES = [
    ("const WEEK_MILESTONES: Array<{ tier: number; wbase: number; wexp: number; wtk: number; legacy: string }> = [", 1,
     "econ2 里程碑表表头必须在位"),
    ("  { tier: 2310, wbase: 60000, wexp: 600, wtk: 30, legacy: '仙品道具+称号' },", 1,
     "econ2 顶端档必须在位（本环把 legacy 换成传承石）"),
    ("  { tier: 1000, wbase: 20000, wexp: 200, wtk: 9,  legacy: '传承石' },", 1,
     "econ2 传承石挂 1000 档必须在位（本环把它移到 2310）"),
    ("const MILE_MONTHLY_TIER = 1000;", 1, "传承石月频档常量必须在位（本环改 2310）"),
    ("const MILE_MONTH_REWARD = 5000;", 1, "传承石折算常量必须在位（本环删除）"),
    ("const CHEST_EXP_TO_STONE = 12;", 1, "修为等效折算比必须在位"),
    ("const ACTIVITY_MAX = 330;", 1, "周上限基座（330×7=2310）必须在位"),
    ("function updatePlayerSave(", 1, "入档通道 updatePlayerSave 必须在位（本环复用它发实物）"),
    ("function sectPillItem(): any {", 1, "宗门丹药实物范式必须在位（本环照抄）"),
    ("app.post('/api/quest/milestone'", 1, "里程碑领取端点唯一"),
    ("const mdef = WEEK_MILESTONES.find((m) => m.tier === tier);", 1, "档位白名单仍表驱动"),
    ("const isMonthly = mdef.tier === MILE_MONTHLY_TIER;", 1, "月频判定必须在位"),
    ("const legacyStone = isMonthly && mdef.legacy === '传承石' ? MILE_MONTH_REWARD : 0;", 1,
     "旧「折算灵石」分支必须在位（本环删除）"),
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：已打过本环（先于依赖检查，给出明确诊断）
    if ("const MILE_MONTHLY_TIER = 2310;" in src
            or "function legacyStoneItem(): any {" in src
            or "const grantStone = isMonthly && mdef.legacy === '传承石';" in src):
        fail("source looks already patched（已存在 2310 档 / legacyStoneItem / grantStone）")

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 5) 门禁
    base403 = src.count("res.status(403")
    gates = [
        # ---- E1 表结构 / 常量 / 构造器 ----
        ("R13b 表头仍在位且唯一", "const WEEK_MILESTONES: Array<{ tier: number; wbase: number; wexp: number; wtk: number; legacy: string }> = [", 1),
        ("R13b 1000 档 legacy 已清空", "  { tier: 1000, wbase: 20000, wexp: 200, wtk: 9,  legacy: '' },", 1),
        ("R13b 1900 档承接仙品道具", "  { tier: 1900, wbase: 40000, wexp: 400, wtk: 21, legacy: '仙品道具+称号' },", 1),
        ("R13b 2310 档挂传承石", "  { tier: 2310, wbase: 60000, wexp: 600, wtk: 30, legacy: '传承石' },", 1),
        ("R13b 月频档改 2310", "const MILE_MONTHLY_TIER = 2310;", 1),
        ("R13b 实物名常量", "const LEGACY_STONE_NAME = '传承石';", 1),
        ("R13b 实物构造器", "function legacyStoneItem(): any {", 1),
        ("R13b 旧 1000 挂传承石已清零", "  { tier: 1000, wbase: 20000, wexp: 200, wtk: 9,  legacy: '传承石' },", 0),
        ("R13b 旧 2310 挂仙品已清零", "  { tier: 2310, wbase: 60000, wexp: 600, wtk: 30, legacy: '仙品道具+称号' },", 0),
        ("R13b 旧月频档 1000 已清零", "const MILE_MONTHLY_TIER = 1000;", 0),
        ("R13b 死常量 MILE_MONTH_REWARD 已删", "MILE_MONTH_REWARD", 0),
        # ---- E2 注释 ----
        ("R13b 端点注释已改", "R-013b：最高档 2,310 的「传承石」额外奖励按月限领一次", 1),
        ("R13b 旧注释「1,000 档」已清零", "//   1,000 档的「传承石」额外奖励按用户拍板", 0),
        # ---- E3 发奖体 ----
        ("R13b grantStone 判定", "const grantStone = isMonthly && mdef.legacy === '传承石';", 1),
        ("R13b totalStone 不再含 legacyStone", "const totalStone = baseReward + expStone;", 1),
        ("R13b 实物入背包语句", "sd.player.inventory.push(stone);", 1),
        ("R13b 发奖回执带 item", "item: grantStone ? LEGACY_STONE_NAME : undefined", 1),
        ("R13b 补偿撤回已发实物", "const i = sd.player.inventory.findIndex((x: any) => x && x.id === grantedStoneId);", 1),
        ("R13b 旧折算分支已清零", "const legacyStone = isMonthly && mdef.legacy === '传承石' ? MILE_MONTH_REWARD : 0;", 0),
        ("R13b 旧折算文案已清零", "、传承石 ×1（折灵石 ×", 0),
        # ---- 冻结：本环不得回踩 ----
        ("冻结 月频判定仍绑常量", "const isMonthly = mdef.tier === MILE_MONTHLY_TIER;", 1),
        ("冻结 档位白名单仍表驱动", "const mdef = WEEK_MILESTONES.find((m) => m.tier === tier);", 1),
        ("冻结 活跃度不足仍 409", "if (weekActivity < mdef.tier) return res.status(409).json({ error: '周活跃度不足' });", 1),
        ("冻结 幂等占位 INSERT 未动", "INSERT INTO activity_milestones (user_id, week, tier, claimed_at) VALUES (?, ?, ?, ?)", 1),
        ("冻结 幂等表 DDL 未动", "CREATE TABLE IF NOT EXISTS activity_milestones", 1),
        ("冻结 summary monthly 仍表驱动", "monthly: m.tier === MILE_MONTHLY_TIER,", 1),
        ("冻结 周上限基座 330 未动", "const ACTIVITY_MAX = 330;", 1),
        ("冻结 修为等效折算未动", "const expStone = Math.floor(mdef.wexp * CHEST_EXP_TO_STONE);", 1),
        ("冻结 宗门丹药范式未动", "function sectPillItem(): any {", 1),
        ("冻结 入档通道 updatePlayerSave 唯一", "function updatePlayerSave(", 1),
        ("冻结 邮件通道 insertMail 未动", "function insertMail(userId: number, title: string, content: string, sender: string, lingshi: number", 1),
        ("冻结 mail 表无物品列（未新增）", "attached_item_json", 0),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 6) 红线：不得新增 403
    a403 = out.count("res.status(403")
    good = (a403 == base403)
    ok = ok and good
    print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", "红线 未新增 res.status(403)", a403, base403))

    # 7) 语义自证：表内 5 档不变；传承石唯一且挂在最高档；月频档 == 传承石档 == 顶端
    import re as _re
    rows = _re.findall(r"\{ tier: (\d+),\s+wbase: (\d+), wexp: (\d+), wtk: (\d+),\s+legacy: '([^']*)' \}", out)
    tiers = [int(r[0]) for r in rows]
    legacies = [r[4] for r in rows]
    wbases = [int(r[1]) for r in rows]
    stone_rows = [i for i, lg in enumerate(legacies) if lg == '传承石']
    monthly_m = _re.search(r"const MILE_MONTHLY_TIER = (\d+);", out)
    monthly_tier = int(monthly_m.group(1)) if monthly_m else -1
    sem_ok = (
        tiers == [500, 1000, 1500, 1900, 2310]
        and wbases == [10000, 20000, 30000, 40000, 60000]
        and sum(wbases) == 160000
        and stone_rows == [4]                     # 传承石恰好 1 处，且在第 5 档
        and tiers[stone_rows[0]] == 2310          # 且是最顶档
        and monthly_tier == tiers[stone_rows[0]]  # 月频档 == 传承石档
        and tiers[-1] == 330 * 7                  # 顶端 = ACTIVITY_MAX × 7
        and "legacy === '传承石'" in out          # 发放判定与表内串一致
        and "LEGACY_STONE_NAME = '传承石'" in out  # 实物名与 legacy 串一致
    )
    ok = ok and sem_ok
    print("  [%s] %-40s tiers=%r stone_row=%r monthly=%d top==330*7"
          % ("OK" if sem_ok else "FAIL", "R13b 语义自证(传承石挂顶端/月频跟随)", tiers, stone_rows, monthly_tier))

    if not ok:
        fail("门禁未全绿，未写回")

    # 8) 往返自证
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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r013b-", suffix=".tmp")
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
