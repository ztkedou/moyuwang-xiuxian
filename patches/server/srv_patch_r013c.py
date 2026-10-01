# -*- coding: utf-8 -*-
r"""
srv_patch_r013c.py -- R-028 收尾（服务端环 r013c）：把「整档按月」解耦成「只有传承石按月」

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` / `--selftest` 只校验不写。
  前置依赖：必须在 **r013b** 之后（本环锚点是 r013b 产出的端点发奖体）。
  lead 接线：把本环挂在 SRV_CHAIN 链尾（第 31 环，紧接 srv_patch_r013b.py）。

=========================================================================== 为什么还要改（r013b 的副作用）
用户第一轮拍板原话：「我不管你选择哪个方案，反正就是**最多一个月一个**（传承石）」。
语义是：**只约束传承石**，不约束同档的常规奖励。

但 r013b 把 `MILE_MONTHLY_TIER` 从 1000 改成 2310 后，端点里

    const isMonthly = mdef.tier === MILE_MONTHLY_TIER;
    const claimKey = isMonthly ? ('m' + monthKey + '_' + tier) : ('w' + week + '_' + tier);

是**整行**月频 ⇒ 2,310 档的**全部奖励**（灵石 60k base + 修为等效 600×12 + 抽奖券 30
+ 传承石）都从「每周」变「每月」。周里程碑灵石总额由「160k/周」变成「100k/周 + 60k/月」。
这不是用户要的 —— 用户只要求「传承石最多一个月一个」。

=========================================================================== 本环改点（1 处 replace，端点整块）
把「月频」从**整行**解耦到**仅传承石那一件**：

  ① 常规奖励（wbase / wexp / wtk）**一律按周**（含最高档 2,310，恢复周频）
        claimKey = 'w' + week + '_' + tier          （所有档一致，恢复 T9 原周频）
  ② 传承石**按月**限领一次 —— **独立幂等行**（复用 activity_milestones 的
        UNIQUE(user_id, week, tier)，不新增表 / 列 / 端点）：
        stoneKey = 'm' + weekMonthKey(week) + '_' + tier + '_legacy'
        tier     = -tier                            （负值哨兵，与真实档位/周档行互不冲突）
      · 本月已领过 ⇒ 本次**仍照发常规奖励**，只是不再发石（详情里注明「本月传承石已领取」）
      · 本周首次领 ⇒ 常规奖励 + 传承石一起发（全或无）

  ③ 幂等/回滚保持「全或无」：
      · 周档 INSERT 命中 UNIQUE ⇒ 409「该里程碑本周已领取」（与旧周档语义一致）
      · 传承石行 INSERT 命中 UNIQUE ⇒ 不算错，仅置 stoneDue=false（本月已领）
      · 发石失败 / 发信失败 ⇒ 撤回已发石 + 删除**两条**占位，玩家可重试（防重复发放）

  ★ 为什么不改 `MILE_MONTHLY_TIER`：它仍被 `GET /api/quest/summary` 用作
    `monthly: m.tier === MILE_MONTHLY_TIER`（前端「该档额外奖励按月限领」提示来源）。
    语义仍是「哪个档的 legacy 额外奖励按月」，常量继续成立 ⇒ 一行不动。

  ★ 为什么复用 activity_milestones 而不是 activity_config：
    · 本端点已有 UNIQUE(user_id, week, tier) 幂等表，且「week 列存 claimKey」是既有约定
      （见 DDL 注释）。传承石按月只需**换一个 claimKey + 负值 tier 哨兵**即可，零新表。
    · activity_config 是 KV 计数表（snapself 的周额度用），语义是「计数」不是「已领占位」，
      用在「每月一次占位」上反而绕远。二者都无 DDL 需求，选更贴近既有约定的前者。

=========================================================================== 红线
  · **不新增任何 res.status(403)**（本环只改发奖体，不碰任何权限/次数闸门；基线 = 11）。
  · 不新增表 / 列 / 端点；不动 `mail` / `insertMail` / `mailClaimCore`。
  · 不改档位白名单 / 幂等表 DDL / 周活跃度采集 / 周上限常量 / WEEK_MILESTONES 表值。
  · 业务拒绝码只用 400/409/500，绝不用 403（客户端 Xc() 会把 403 当会话失效强制登出）。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ E1 端点整块（注释 + 发奖体）

E1_OLD = """// POST /api/quest/milestone — 领取周里程碑（{tier:500|1000|1500|1900|2310}）→ 邮件发灵石
//   T9 0.8.8：幂等靠 activity_milestones 的 UNIQUE(user_id, week, tier)（周）；
//   R-013b：最高档 2,310 的「传承石」额外奖励按月限领一次（MILE_MONTHLY_TIER=2310），改发实物。
app.post('/api/quest/milestone', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `quest:ms:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const tier = asInt(req.body?.tier);
  const mdef = WEEK_MILESTONES.find((m) => m.tier === tier);
  if (!mdef) return res.status(400).json({ error: 'tier 非法' });
  const userId = req.user.id;
  const week = bjWeekStart(Date.now());
  const isMonthly = mdef.tier === MILE_MONTHLY_TIER;   // 声明在 try 外，供 catch 的 UNIQUE 分支引用
  try {
    const srow: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    let realm = '';
    try { realm = String(JSON.parse(srow?.save_data || '{}')?.player?.realm || ''); } catch { realm = ''; }
    const rf = ylrf(realm);
    const weekActivity = await collectWeeklyActivity(userId, week);
    if (weekActivity < mdef.tier) return res.status(409).json({ error: '周活跃度不足' });
    const monthKey = weekMonthKey(week);
    const claimKey = isMonthly ? ('m' + monthKey + '_' + tier) : ('w' + week + '_' + tier);
    // 月档：本月内已领过（任意周）⇒ 拒；周档：本周已领 ⇒ 拒。统一用 activity_milestones 的
    //   (user_id, week, tier) 存「claimKey 化后的 week」实现幂等（week 列存 claimKey 可直接复用 UNIQUE）。
    await dbRun('INSERT INTO activity_milestones (user_id, week, tier, claimed_at) VALUES (?, ?, ?, ?)', [userId, claimKey, tier, Date.now()]);
    const baseReward = Math.floor(mdef.wbase * rf);
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
    }
  } catch (e: any) {
    if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: isMonthly ? '该里程碑本月已领取' : '该里程碑本周已领取' });
    console.error('milestone error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});"""

E1_NEW = """// POST /api/quest/milestone — 领取周里程碑（{tier:500|1000|1500|1900|2310}）→ 邮件发灵石
//   T9 0.8.8：幂等靠 activity_milestones 的 UNIQUE(user_id, week, tier)（周）；
//   R-013c：**常规奖励一律按周**（含最高档 2,310，恢复周频）；**仅「传承石」按月**限领一次
//     （独立幂等键 <周一>_legacy，tier 存 -tier 哨兵；用户拍板「传承石最多一个月一个」）。
app.post('/api/quest/milestone', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `quest:ms:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const tier = asInt(req.body?.tier);
  const mdef = WEEK_MILESTONES.find((m) => m.tier === tier);
  if (!mdef) return res.status(400).json({ error: 'tier 非法' });
  const userId = req.user.id;
  const week = bjWeekStart(Date.now());
  const isStoneTier = mdef.legacy === '传承石';   // 声明在 try 外，供 catch 的 UNIQUE 分支引用
  const claimKey = 'w' + week + '_' + tier;                                  // R-013c 常规奖励：每周一次
  const stoneKey = 'm' + weekMonthKey(week) + '_' + tier + '_legacy';        // R-013c 传承石：每月一次
  try {
    const srow: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    let realm = '';
    try { realm = String(JSON.parse(srow?.save_data || '{}')?.player?.realm || ''); } catch { realm = ''; }
    const rf = ylrf(realm);
    const weekActivity = await collectWeeklyActivity(userId, week);
    if (weekActivity < mdef.tier) return res.status(409).json({ error: '周活跃度不足' });
    // R-013c：常规奖励**每周**限领一次（含 2,310 档，恢复周频；T9 原语义）。
    //   week 列存 claimKey 直接复用 UNIQUE(user_id, week, tier) 实现幂等。
    await dbRun('INSERT INTO activity_milestones (user_id, week, tier, claimed_at) VALUES (?, ?, ?, ?)', [userId, claimKey, tier, Date.now()]);
    // R-013c：传承石**每月**限领一次 —— 独立幂等行（week 存 'm<YYYY-MM>_<tier>_legacy'，
    //   tier 存 -tier 哨兵，与周档行互不冲突）。本月已领过 ⇒ 本次仍照发常规奖励，只是不再发石。
    let stoneDue = isStoneTier;
    if (stoneDue) {
      try {
        await dbRun('INSERT INTO activity_milestones (user_id, week, tier, claimed_at) VALUES (?, ?, ?, ?)', [userId, stoneKey, -tier, Date.now()]);
      } catch (e2: any) {
        if (String(e2?.message || '').includes('UNIQUE')) {
          stoneDue = false;   // 本月传承石已领 ⇒ 常规奖励照发，不报错
        } else {
          await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, claimKey, tier]);
          throw e2;           // 真错 ⇒ 撤回周档占位，交外层 500
        }
      }
    }
    const baseReward = Math.floor(mdef.wbase * rf);
    const expStone = Math.floor(mdef.wexp * CHEST_EXP_TO_STONE);
    // R-013b：传承石改发**实物**（走 updatePlayerSave 背包通道，同宗门丹药 sectPillItem），
    //   不再折算成灵石塞邮件附件。实物先发；发信失败则补偿撤回（见下，防重复发放）。
    const totalStone = baseReward + expStone;
    const detail = `灵石 ×${baseReward}、修为等效 ×${mdef.wexp}（折灵石 ×${expStone}）`
      + (stoneDue ? `、传承石 ×1（实物已入背包，每月限一次）` : '')
      + (isStoneTier && !stoneDue ? `、本月传承石已领取` : '')
      + (mdef.wtk > 0 ? `、抽奖券 ×${mdef.wtk}` : '');
    let grantedStoneId = '';
    if (stoneDue) {
      const stone = legacyStoneItem();
      grantedStoneId = stone.id;
      const g = await updatePlayerSave(userId, (sd: any) => {
        if (!sd.player || typeof sd.player !== 'object') sd.player = {};
        sd.player.inventory = Array.isArray(sd.player.inventory) ? sd.player.inventory : [];
        sd.player.inventory.push(stone);
      });
      if (!g.ok) {
        await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, claimKey, tier]);
        await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, stoneKey, -tier]);
        return res.status(500).json({ error: '发奖失败，请重试' });
      }
    }
    try {
      await insertMail(userId, '周里程碑·勤修', `本周活跃度达到 ${tier}，${detail} 已附上（合计灵石 ×${totalStone}），点击领取。`, 'system', totalStone);
      res.json({ ok: true, tier, reward: totalStone, week, weekActivity, monthly: isStoneTier, item: stoneDue ? LEGACY_STONE_NAME : undefined });
    } catch (e: any) {
      console.error('milestone mail error:', e?.message || e);
      // 补偿式回滚（同 mailClaimCore）：撤回已发的传承石，再删两条占位，玩家可重试（防重复发放）
      if (grantedStoneId) {
        await updatePlayerSave(userId, (sd: any) => {
          if (Array.isArray(sd.player?.inventory)) {
            const i = sd.player.inventory.findIndex((x: any) => x && x.id === grantedStoneId);
            if (i >= 0) sd.player.inventory.splice(i, 1);
          }
        }).catch(() => undefined);
      }
      await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, claimKey, tier]);
      if (stoneDue) await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, stoneKey, -tier]);
      res.status(500).json({ error: '发奖失败，请重试' });
    }
  } catch (e: any) {
    if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '该里程碑本周已领取' });
    console.error('milestone error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});"""

EDITS = [
    ("E1 里程碑端点解耦（整档月频→仅传承石月频）", E1_OLD, E1_NEW),
]

# 前置依赖（r013b 之后的形态，必须逐条在位；本环只读这些串做自证，不改）
REQUIRES = [
    ("app.post('/api/quest/milestone'", 1, "里程碑领取端点唯一"),
    ("const mdef = WEEK_MILESTONES.find((m) => m.tier === tier);", 1, "档位白名单仍表驱动"),
    ("const isMonthly = mdef.tier === MILE_MONTHLY_TIER;", 1, "r013b 的整档月频判定必须在位（本环删除）"),
    ("const claimKey = isMonthly ? ('m' + monthKey + '_' + tier) : ('w' + week + '_' + tier);", 1,
     "r013b 的整档月频 claimKey 必须在位（本环改为恒周频）"),
    ("const grantStone = isMonthly && mdef.legacy === '传承石';", 1,
     "r013b 的发石判定必须在位（本环改为按 legacy 判定）"),
    ("const legacyStone = isMonthly && mdef.legacy === '传承石' ? MILE_MONTH_REWARD : 0;", 0,
     "确认 r013b 已删旧折算分支（不应再出现）"),
    ("const MILE_MONTHLY_TIER = 2310;", 1, "r013b 月频档常量必须在位（本环不得改）"),
    ("const LEGACY_STONE_NAME = '传承石';", 1, "传承石实物名常量必须在位"),
    ("function legacyStoneItem(): any {", 1, "传承石实物构造器必须在位"),
    ("const CHEST_EXP_TO_STONE = 12;", 1, "修为等效折算比必须在位"),
    ("const ACTIVITY_MAX = 330;", 1, "周上限基座（330×7=2310）必须在位"),
    ("function updatePlayerSave(", 1, "入档通道 updatePlayerSave 必须在位"),
    ("function weekMonthKey(week: string): string { return week.slice(0, 7); }", 1,
     "周→月键换算必须在位（本环复用为传承石月频键）"),
    ("CREATE TABLE IF NOT EXISTS activity_milestones", 1, "幂等表 DDL 必须在位"),
    ("monthly: m.tier === MILE_MONTHLY_TIER,", 1, "summary 的 monthly 提示仍绑常量（本环不得改）"),
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
    if ("const stoneKey = 'm' + weekMonthKey(week) + '_' + tier + '_legacy';" in src
            or "const isStoneTier = mdef.legacy === '传承石';" in src
            or "let stoneDue = isStoneTier;" in src):
        fail("source looks already patched（已存在 stoneKey / isStoneTier / stoneDue）")

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
        # ---- E1 解耦 ----
        ("R13c 常规奖励恒周频 claimKey", "const claimKey = 'w' + week + '_' + tier;", 1),
        ("R13c 传承石月频独立键",        "const stoneKey = 'm' + weekMonthKey(week) + '_' + tier + '_legacy';", 1),
        ("R13c 发石判定改按 legacy",     "const isStoneTier = mdef.legacy === '传承石';", 1),
        ("R13c stoneDue 初值",           "let stoneDue = isStoneTier;", 1),
        ("R13c 石行幂等 INSERT 就位",    "await dbRun('INSERT INTO activity_milestones (user_id, week, tier, claimed_at) VALUES (?, ?, ?, ?)', [userId, stoneKey, -tier, Date.now()]);", 1),
        ("R13c 石行 UNIQUE 视为已领",    "stoneDue = false;   // 本月传承石已领 ⇒ 常规奖励照发，不报错", 1),
        ("R13c 石行真错撤回周档占位",    "          throw e2;           // 真错 ⇒ 撤回周档占位，交外层 500", 1),
        ("R13c 旧整档月频 claimKey 已删", "const claimKey = isMonthly ? ('m' + monthKey + '_' + tier) : ('w' + week + '_' + tier);", 0),
        ("R13c 旧 isMonthly 判定已删",   "const isMonthly = mdef.tier === MILE_MONTHLY_TIER;", 0),
        ("R13c 旧 grantStone 判定已删",  "const grantStone = isMonthly && mdef.legacy === '传承石';", 0),
        ("R13c 旧月档 409 文案已删",     "'该里程碑本月已领取'", 0),
        ("R13c 周档 409 文案就位",       "return res.status(409).json({ error: '该里程碑本周已领取' });", 1),
        ("R13c 已领月石详情文案",        "、本月传承石已领取", 1),
        ("R13c 发石详情文案保留",        "、传承石 ×1（实物已入背包，每月限一次）", 1),
        # ---- 传承石实物发放链路（r013b 保留，本环不得回踩） ----
        ("冻结 实物构造器未动",          "function legacyStoneItem(): any {", 1),
        ("冻结 实物名常量未动",          "const LEGACY_STONE_NAME = '传承石';", 1),
        ("冻结 实物入背包语句未动",      "sd.player.inventory.push(stone);", 1),
        ("冻结 补偿撤回语句未动",        "const i = sd.player.inventory.findIndex((x: any) => x && x.id === grantedStoneId);", 1),
        ("冻结 月频档常量仍 2310",       "const MILE_MONTHLY_TIER = 2310;", 1),
        ("冻结 summary monthly 仍绑常量", "monthly: m.tier === MILE_MONTHLY_TIER,", 1),
        # ---- 冻结：本环不得回踩的其它语义 ----
        ("冻结 档位白名单仍表驱动",      "const mdef = WEEK_MILESTONES.find((m) => m.tier === tier);", 1),
        ("冻结 活跃度不足仍 409",        "if (weekActivity < mdef.tier) return res.status(409).json({ error: '周活跃度不足' });", 1),
        ("冻结 tier 非法仍 400",         "if (!mdef) return res.status(400).json({ error: 'tier 非法' });", 1),
        ("冻结 幂等表 DDL 未动",         "CREATE TABLE IF NOT EXISTS activity_milestones", 1),
        ("冻结 周上限基座 330 未动",     "const ACTIVITY_MAX = 330;", 1),
        ("冻结 修为等效折算未动",        "const expStone = Math.floor(mdef.wexp * CHEST_EXP_TO_STONE);", 1),
        ("冻结 周→月键换算未动",         "function weekMonthKey(week: string): string { return week.slice(0, 7); }", 1),
        ("冻结 入档通道 updatePlayerSave 唯一", "function updatePlayerSave(", 1),
        ("冻结 邮件通道 insertMail 未动", "function insertMail(userId: number, title: string, content: string, sender: string, lingshi: number", 1),
        ("冻结 mail 表无物品列（未新增）", "attached_item_json", 0),
        ("冻结 WEEK_MILESTONES 顶端仍传承石", "  { tier: 2310, wbase: 60000, wexp: 600, wtk: 30, legacy: '传承石' },", 1),
        ("冻结 1900 档仍承接仙品道具",   "  { tier: 1900, wbase: 40000, wexp: 400, wtk: 21, legacy: '仙品道具+称号' },", 1),
        ("冻结 1000 档 legacy 仍空",     "  { tier: 1000, wbase: 20000, wexp: 200, wtk: 9,  legacy: '' },", 1),
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

    # 7) 语义自证：常规奖励恒周频；传承石按月且仅限 legacy==='传承石' 的档；石行用负值哨兵
    import re as _re
    weekly_keys = out.count("const claimKey = 'w' + week + '_' + tier;")
    stone_keys = out.count("const stoneKey = 'm' + weekMonthKey(week) + '_' + tier + '_legacy';")
    stone_rows = _re.findall(r"\{ tier: (\d+),\s+wbase: (\d+), wexp: (\d+), wtk: (\d+),\s+legacy: '([^']*)' \}", out)
    stone_tiers = [int(r[0]) for r in stone_rows if r[4] == '传承石']
    sem_ok = (
        weekly_keys == 1
        and stone_keys == 1
        and stone_tiers == [2310]                       # 传承石唯一，且挂最高档
        and "mdef.legacy === '传承石'" in out            # 石判定按 legacy
        and "-tier, Date.now()" in out                   # 石行用负值哨兵
        and "const isMonthly" not in out                 # 整档月频判定已彻底消失
        and "isMonthly ?" not in out
    )
    ok = ok and sem_ok
    print("  [%s] %-40s stone_tiers=%r weeklyKeys=%d stoneKeys=%d"
          % ("OK" if sem_ok else "FAIL", "R13c 语义自证(常规周频/石月频)", stone_tiers, weekly_keys, stone_keys))

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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r013c-", suffix=".tmp")
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
