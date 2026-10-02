# -*- coding: utf-8 -*-
r"""
srv_patch_101.py — R-091 悟道体系重规划（服务端环 · 六道去重 + 稀有道等阶门槛 + 灵石价随境界递增）

需求原文（台账 R-091）
--------------------------------------------------------------------------
  「悟道，花灵石悟道只增加 exp，不要直接提升等级。并且各种道的等级升级经验需求随着等级提升
   要越来越高，而不是现在 100exp 一级。并且我发现现在 6 种道，怎么攻击加成和气血加成有两条。
   彻底重新规划一下悟道的体系，并且稀有属性需要人物等阶高一点才逐步开放，且需求的灵石数量变多。」

前置取证结论（沿用，勿重查）
--------------------------------------------------------------------------
  · 悟道逻辑**全在服务端**（`[wudaocore]` 纯逻辑块 + GET/POST /api/wudao），客户端只渲染
    服务端下发的 `daos[].statName/bonusText`（客户端 bundle 内无 WUDAO_DAOS，仅调用 /api/wudao）。
  · R1（只加 exp、等级由 exp 推导）+ R2（单级增量随等级递增，50L 线性）**基座本就满足**；
    用户所见「100exp 一级」= `WUDAO_MANUAL_EXP=100`（单次手动顿悟给 100 exp）的错觉。

────────────────────────────────────────────────────────────────────────────
改前 6 道结构（基座）
--------------------------------------------------------------------------
  key   名称   加成        basePct/stepPct   门槛
  sword 剑道   攻击        2.0 / 0.5         无
  body  体道   防御        2.0 / 0.5         无
  pill  丹道   气血        2.0 / 0.5         无
  spell 法道   暴击        1.0 / 0.25        无
  array 阵道   攻击 ←①重复  1.0 / 0.25        无
  tame  御道   气血 ←②重复  1.0 / 0.25        无
  ⇒ 阵道与剑道同加成（攻击）、御道与丹道同加成（气血），6 道实为 4 种定位。

改后 6 道结构（本环）
--------------------------------------------------------------------------
  key   名称   加成         basePct/stepPct   定位唯一性
  sword 剑道   攻击        2.0 / 0.5         DPS
  body  体道   防御        2.0 / 0.5         生存
  pill  丹道   气血        2.0 / 0.5         生存上限
  spell 法道   暴击        1.0 / 0.25        输出波动
  array 阵道   修炼速度 ↑  1.0 / 0.25        ★去重①：原「攻击」→「修炼速度」(stat=cultivate)
  tame  御道   资源产出 ↑  1.0 / 0.25        ★去重②：原「气血」→「资源产出」(stat=gather)
  ⇒ 6 道 6 个互不重复定位（攻击 / 防御 / 气血 / 暴击 / 修炼速度 / 资源产出）。

等阶门槛与灵石价格对照表（R4）
--------------------------------------------------------------------------
  稀有道门槛（只挡「从未投入 exp<=0」的新玩家；已投入者祖父放行，不追溯锁死）：
    道      key     开放境界   境界序
    剑道    sword   炼气期     0（默认）
    体道    body    炼气期     0
    丹道    pill    炼气期     0
    法道    spell   炼气期     0
    阵道    array   ★元婴期    3（第 5 条道）
    御道    tame    ★化神期    4（第 6 条道）
  手动顿悟灵石价（原恒定 5000）改为随人物境界递增：
    境界     序   灵石/次
    炼气期   0    5,000
    筑基期   1    8,000
    金丹期   2    12,000
    元婴期   3    18,000
    化神期   4    27,000
    合道期   5    40,000
    长生境   6    60,000      （最高 ≈ 炼气的 12×；稀有道同价——门槛已限人数）

升级曲线对照表（前 10 级；★本环**保持原曲线不动**，理由见下）
--------------------------------------------------------------------------
  等级 L   累计 exp（wudaoExpToReach）   单级增量
    1       0                             —
    2       50                            50
    3       150                           100
    4       300                           150
    5       500                           200
    6       750                           250
    7       1050                          300
    8       1400                          350
    9       1800                          400
    10      2250                          450
  ⇒ 单级增量 = 50L，**本就随等级递增**（R2 满足）。优先级 3 属「可选」，本环**不做**：
    等级由 exp 纯函数推导（`wudaoLevelFromExp`），改曲线会让同一 exp 映射到**更低等级** ⇒
    直接违反「已练等级必须保留」。要安全改曲线必须做 exp 重映射迁移，收益（曲线已递增）
    远小于打坏存量档的风险，故不动（见风险点）。

★老玩家影响评估与祖父条款实现
--------------------------------------------------------------------------
  影响面（改加成 = 变性已投入资源）：
    · 阵道 攻击 → 修炼速度：已练阵道的玩家**当场失去攻击加成**（战力/展示下降）——主要受损点。
    · 御道 气血 → 资源产出：同理失去气血加成。
    · 门槛：低境界且已投入阵/御道者若被硬锁，等于「投了钱的道突然不能继续投」——必须放行。
  祖父条款（三条全部落地）：
    ① 等级/exp 原样保留：**不动升级曲线**，`wudaoLevelFromExp` 逐字未改 ⇒ 同 exp 仍得同级，
       阵/御道已练等级 100% 保留，不清零不降级。
    ② 已投入灵石不追溯作废：新增 `wudaoRespecCompensateOnce()`——按阵/御道「改前已投入 exp」
       × 50 灵石/exp（= 历史手动顿悟等价价 5000/100）**一次性返还**，走 `insertMail`
       （玩家在邮箱领取）。幂等键 `activity_config['r091_wudao_respec:<uid>']`，**先占键后发信**
       ⇒ 至多一次，绝不重复发放。上限：两道各满级 2250 exp ⇒ 单号 ≤ 225,000 灵石
       （≈ 满配灵田半日收益，非主要收入）。
       触发点=GET /api/wudao 与 POST /api/wudao/insight 首次触达（先于本次加 exp 结算，
       保证按「改前」存量计算）；自吞异常，绝不影响悟道主流程。
    ③ 门槛不追溯：GET 返回 `locked = (境界<门槛 && exp<=0)`；POST 放行条件同款——**已投入者
       永远可继续顿悟**，只有从未投入的玩家才受境界限制。挂机心得（`tickWudaoIdle`）也改为
       只在本人已开放的系内随机命中，避免低境界玩家靠挂机偷偷把稀有道喂开、架空门槛。
  结论：可安全上线；不做优先级 3（曲线）以换取存量档零风险。

风险点
--------------------------------------------------------------------------
  · 客户端未同步改：客户端读服务端 `statName/bonusText` 渲染，故显示自动跟随；但若客户端对
    `stat` 值有白名单分支（本项目客户端无悟道结算逻辑，实测仅渲染文本），新 `stat`
    值 `cultivate/gather` 可能落到默认样式——不影响功能，属展示层待观察项。
  · 补偿口径偏宽：按**全部** exp（含免费挂机 exp）以 50/exp 返还，是刻意从宽的祖父补偿；
    一次性、有上限、有幂等键，不构成刷钱口。
  · 挂机埋点新增一次 `saves` 只读 SELECT（fire-and-forget，不阻塞存档路径）。
  · `wudaoPickDao` 纯函数保留但不再被调用（保留以维持 `[wudaocore]` 纯逻辑块可整块提取）。

工程约束（照 srv_patch_064 / r078 惯例）
--------------------------------------------------------------------------
  · `--src <path>` 就地原子写回；`--check` / `--selftest` 只校验不写。
  · 幂等：产物已含 `[r101wudao]` 则 SKIP。每处替换 expect=1，命中数不符即中止；
    round-trip 自证后原子写回。
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval` / `PRAGMA`。
  · ⛔ 不改 srv/index_v28.ts（链产物）；⛔ 不改任何既有 srv_patch_*.py。
  · 链序：挂 SRV_CHAIN 链尾（无硬前置依赖；锚区与既有各环零交集）。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

MARK = "[r101wudao]"

# ============================================================ E1：六道去重（阵/御 定位变更）

E1_OLD = """\
  array: { name: '阵道', stat: 'attack', statName: '攻击', basePct: 1.0, stepPct: 0.25 },
  tame:  { name: '御道', stat: 'maxHp', statName: '气血', basePct: 1.0, stepPct: 0.25 },"""

E1_NEW = """\
  // [r101wudao] R-091 去重：阵道 攻击→修炼速度、御道 气血→资源产出（六道定位互不重复）
  array: { name: '阵道', stat: 'cultivate', statName: '修炼速度', basePct: 1.0, stepPct: 0.25 },
  tame:  { name: '御道', stat: 'gather', statName: '资源产出', basePct: 1.0, stepPct: 0.25 },"""

# ============================================================ E2：门槛/价格纯逻辑（注入 [wudaocore] 块内）

E2_OLD = """\
const WUDAO_LOG_KEEP = 50; // 每玩家悟道日志保留条数（写入后裁剪，防表膨胀）
// [/wudaocore]"""

E2_NEW = """\
const WUDAO_LOG_KEEP = 50; // 每玩家悟道日志保留条数（写入后裁剪，防表膨胀）
// ── [r101wudao] R-091 悟道体系重规划：稀有道等阶门槛 + 灵石价随境界递增 ──
// 境界序自持镜像（与 REALM_ORDER_FOR_RANKING / DUNGEON_REALM_ORDER 同源同序；本块不引用外部符号）
const WUDAO_REALM_ORDER: string[] = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];
// 稀有道门槛（境界序）：剑/体/丹/法 自炼气期(0)开放；阵道(第5道)元婴期(3)、御道(第6道)化神期(4)起开放。
// ★ 门槛只挡「从未投入(exp<=0)」的玩家；已投入者由调用方按 exp>0 祖父放行，不追溯锁死。
const WUDAO_DAO_REALM_GATE: Record<string, number> = { sword: 0, body: 0, pill: 0, spell: 0, array: 3, tame: 4 };
function wudaoRealmIndex(realm: unknown): number {
  const i = WUDAO_REALM_ORDER.indexOf(String(realm == null ? '' : realm));
  return i >= 0 ? i : 0; // 未知境界按最低档（炼气期），与 dungeon 同口径
}
function wudaoDaoGateRealm(daoKey: string): number {
  const g = WUDAO_DAO_REALM_GATE[daoKey];
  return typeof g === 'number' && g > 0 ? Math.min(g, WUDAO_REALM_ORDER.length - 1) : 0;
}
// 手动顿悟灵石价：随人物境界递增（炼气 5000 → 长生 60000，≈12×；稀有道同价——门槛已限人数）
const WUDAO_MANUAL_COST_BY_REALM: number[] = [WUDAO_MANUAL_COST, 8000, 12000, 18000, 27000, 40000, 60000];
function wudaoManualCost(realmIdx: unknown): number {
  const i = Math.min(WUDAO_MANUAL_COST_BY_REALM.length - 1, Math.max(0, Math.floor(Number(realmIdx) || 0)));
  return WUDAO_MANUAL_COST_BY_REALM[i];
}
// [/wudaocore]"""

# ============================================================ E3：祖父条款补偿助手（GET 端点前）

E3_OLD = """\
// GET /api/wudao — 六系等级+exp+加成列表+悟道日志+灵石余额（一页全量，不落账）"""

E3_NEW = """\
// ── [r101wudao] R-091 祖父条款：阵道/御道定位变更（攻击/气血 → 修炼速度/资源产出）一次性灵石补偿 ──
//   规则：按两条道「改前已投入 exp」× 50 灵石/exp（= 历史手动顿悟等价 5000/100）一次性返还，
//   走 insertMail（玩家在邮件里领取）。幂等键 = activity_config['r091_wudao_respec:<uid>']，
//   首次触达悟道面（GET/POST）即结算一次；**先占键后发信** ⇒ 至多一次（绝不重复发放）。
//   已练等级/exp 原样保留（升级曲线未动），本条仅补偿「加成语义变更」的定位损失。
const WUDAO_RESPEC_REFUND_PER_EXP = 50;
async function wudaoRespecCompensateOnce(userId: number): Promise<void> {
  try {
    const key = 'r091_wudao_respec:' + userId;
    const seen = await dbGet('SELECT value FROM activity_config WHERE key = ?', [key]).catch(() => null);
    if (seen) return;
    // 先占键（INSERT OR IGNORE，changes=0 ⇒ 已被并发/前次占位），保证至多一次发放
    const claim = await dbRun("INSERT OR IGNORE INTO activity_config (key, value) VALUES (?, '1')", [key]).catch(() => null);
    if (!claim || Number(claim.changes) <= 0) return;
    const rows = await dbAll('SELECT dao_type, exp FROM wudao WHERE player_id = ? AND dao_type IN (?, ?)', [userId, 'array', 'tame']);
    let expSum = 0;
    for (const r of rows || []) expSum += Math.max(0, Math.floor(Number(r.exp) || 0));
    const refund = Math.floor(expSum * WUDAO_RESPEC_REFUND_PER_EXP);
    if (refund > 0) {
      await insertMail(userId, '悟道体系重规划补偿',
        `阵道/御道定位已重规划（阵道→修炼速度、御道→资源产出）。按你此前投入的 ${expSum} 点道行，一次性返还灵石 ×${refund}。`,
        '天机阁', refund);
    }
  } catch (e: any) {
    console.error('wudao respec compensate error:', e?.message || e);
  }
}

// GET /api/wudao — 六系等级+exp+加成列表+悟道日志+灵石余额（一页全量，不落账）"""

# ============================================================ E4：GET 端点（境界/门槛/价格/补偿触发）

E4_OLD = """\
    const expByDao: Record<string, number> = {};
    for (const r of rows || []) expByDao[String(r.dao_type)] = Math.max(0, Math.floor(Number(r.exp) || 0));
    let balance: number | null = null;
    if (saveRow) {
      try { balance = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { balance = null; }
    }
    const daos = Object.keys(WUDAO_DAOS).map((k) => {
      const d = WUDAO_DAOS[k];
      const exp = expByDao[k] || 0;
      const level = wudaoLevelFromExp(exp);
      const next = level < WUDAO_MAX_LEVEL ? wudaoExpToReach(level + 1) : null;
      return {
        key: k,
        name: d.name,
        stat: d.stat,
        statName: d.statName,
        level,
        exp,
        expToNext: next == null ? 0 : next - exp,
        bonusUnlocked: level >= WUDAO_BONUS_UNLOCK_LEVEL,
        bonusPct: wudaoBonusPct(k, level),
        bonusText: level >= WUDAO_BONUS_UNLOCK_LEVEL
          ? `${d.statName} +${wudaoBonusPct(k, level)}%`
          : `${d.statName}加成（${d.statName} +${d.basePct}%，Lv${WUDAO_BONUS_UNLOCK_LEVEL} 解锁）`,
      };
    });
    res.json({
      now: Date.now(),
      daos,
      maxLevel: WUDAO_MAX_LEVEL,
      bonusUnlockLevel: WUDAO_BONUS_UNLOCK_LEVEL,
      maxExpTotal: WUDAO_MAX_EXP_TOTAL,
      insight: { chancePerMinute: WUDAO_INSIGHT_CHANCE, exp: WUDAO_INSIGHT_EXP, capMinutesPerUpload: WUDAO_IDLE_CAP_MINUTES },
      manual: { cost: WUDAO_MANUAL_COST, exp: WUDAO_MANUAL_EXP },"""

E4_NEW = """\
    const expByDao: Record<string, number> = {};
    for (const r of rows || []) expByDao[String(r.dao_type)] = Math.max(0, Math.floor(Number(r.exp) || 0));
    let balance: number | null = null;
    let realmIdx = 0;
    if (saveRow) {
      try {
        const p = JSON.parse(saveRow.save_data)?.player;
        balance = Math.max(0, Math.floor(Number(p?.spiritStones) || 0));
        realmIdx = wudaoRealmIndex(p?.realm);
      } catch { balance = null; }
    }
    await wudaoRespecCompensateOnce(userId); // [r101wudao] 祖父条款：首次触达即一次性补偿（幂等，自吞异常）
    const daos = Object.keys(WUDAO_DAOS).map((k) => {
      const d = WUDAO_DAOS[k];
      const exp = expByDao[k] || 0;
      const level = wudaoLevelFromExp(exp);
      const next = level < WUDAO_MAX_LEVEL ? wudaoExpToReach(level + 1) : null;
      const gateRealm = wudaoDaoGateRealm(k);
      const locked = realmIdx < gateRealm && exp <= 0; // 已投入者祖父放行，不追溯锁死
      return {
        key: k,
        name: d.name,
        stat: d.stat,
        statName: d.statName,
        level,
        exp,
        expToNext: next == null ? 0 : next - exp,
        bonusUnlocked: level >= WUDAO_BONUS_UNLOCK_LEVEL,
        bonusPct: wudaoBonusPct(k, level),
        locked,
        gateRealmIndex: gateRealm,
        gateRealmName: gateRealm > 0 ? WUDAO_REALM_ORDER[gateRealm] : null,
        bonusText: level >= WUDAO_BONUS_UNLOCK_LEVEL
          ? `${d.statName} +${wudaoBonusPct(k, level)}%`
          : `${d.statName}加成（${d.statName} +${d.basePct}%，Lv${WUDAO_BONUS_UNLOCK_LEVEL} 解锁）`,
      };
    });
    res.json({
      now: Date.now(),
      daos,
      maxLevel: WUDAO_MAX_LEVEL,
      bonusUnlockLevel: WUDAO_BONUS_UNLOCK_LEVEL,
      maxExpTotal: WUDAO_MAX_EXP_TOTAL,
      realmIndex: realmIdx,
      insight: { chancePerMinute: WUDAO_INSIGHT_CHANCE, exp: WUDAO_INSIGHT_EXP, capMinutesPerUpload: WUDAO_IDLE_CAP_MINUTES },
      manual: { cost: wudaoManualCost(realmIdx), exp: WUDAO_MANUAL_EXP },"""

# ============================================================ E5：POST 端点（门槛放行 + 价格随境界）

E5_OLD = """\
    const daoKey = asStr(req.body?.dao);
    if (!wudaoDaoOk(daoKey)) return res.status(400).json({ error: '未知的悟道系别' });
    // 预检：角色与灵石余额（并发窗口由 updatePlayerSave 锁内二次校验兜底）
    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(row.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < WUDAO_MANUAL_COST) return res.status(409).json({ error: `灵石不足：需 ${WUDAO_MANUAL_COST}，现有 ${bal}` });
    // 1) 扣灵石（saveLock 互斥 + gm_revision++ 促客户端拉新档；锁内余额不足拒绝）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') { short = true; return; }
      const b = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0));
      if (b < WUDAO_MANUAL_COST) { short = true; return; }
      sd.player.spiritStones = b - WUDAO_MANUAL_COST;
    });"""

E5_NEW = """\
    const daoKey = asStr(req.body?.dao);
    if (!wudaoDaoOk(daoKey)) return res.status(400).json({ error: '未知的悟道系别' });
    // 预检：角色与灵石余额（并发窗口由 updatePlayerSave 锁内二次校验兜底）
    const row = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    let realmIdx = 0;
    try { const p = JSON.parse(row.save_data)?.player; bal = Math.max(0, Math.floor(Number(p?.spiritStones) || 0)); realmIdx = wudaoRealmIndex(p?.realm); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    await wudaoRespecCompensateOnce(userId); // [r101wudao] 祖父条款：一次性补偿（先于本次加 exp，按改前已投入结算）
    // [r101wudao] R-091 稀有道等阶门槛：阵道/御道按境界逐步开放；已投入(exp>0)者祖父放行，不追溯锁死
    const gateRealm = wudaoDaoGateRealm(daoKey);
    if (gateRealm > 0 && realmIdx < gateRealm) {
      const own: any = await dbGet('SELECT exp FROM wudao WHERE player_id = ? AND dao_type = ?', [userId, daoKey]);
      const ownExp = Math.max(0, Math.floor(Number(own?.exp) || 0));
      if (ownExp <= 0) return res.status(409).json({ error: `此道需 ${WUDAO_REALM_ORDER[gateRealm]} 起方可参悟`, code: 'DAO_LOCKED', gateRealmIndex: gateRealm });
    }
    const cost = wudaoManualCost(realmIdx); // [r101wudao] 灵石价随境界递增
    if (bal < cost) return res.status(409).json({ error: `灵石不足：需 ${cost}，现有 ${bal}` });
    // 1) 扣灵石（saveLock 互斥 + gm_revision++ 促客户端拉新档；锁内余额不足拒绝）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') { short = true; return; }
      const b = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0));
      if (b < cost) { short = true; return; }
      sd.player.spiritStones = b - cost;
    });"""

# ============================================================ E6：退款补偿行（用 cost 变量）

E6_OLD = """\
        sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + WUDAO_MANUAL_COST;"""

E6_NEW = """\
        sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + cost;"""

# ============================================================ E7：POST 回执 cost 字段

E7_OLD = """\
      bonusText: added.level >= WUDAO_BONUS_UNLOCK_LEVEL ? `${d.statName} +${wudaoBonusPct(daoKey, added.level)}%` : null,
      cost: WUDAO_MANUAL_COST,"""

E7_NEW = """\
      bonusText: added.level >= WUDAO_BONUS_UNLOCK_LEVEL ? `${d.statName} +${wudaoBonusPct(daoKey, added.level)}%` : null,
      cost,"""

# ============================================================ E8：挂机心得只在已开放的系内随机（防架空门槛）

E8_OLD = """\
    const hits = wudaoIdleInsights(Math.floor((Number(playTimeDeltaMs) || 0) / 60000), Math.random);
    if (hits <= 0) return;
    const perDao: Record<string, number> = {};
    for (let i = 0; i < hits; i++) {
      const k = wudaoPickDao(Math.random);
      perDao[k] = (perDao[k] || 0) + WUDAO_INSIGHT_EXP;
    }
    for (const k of Object.keys(perDao)) await wudaoAddExp(userId, k, perDao[k], 'idle');"""

E8_NEW = """\
    const hits = wudaoIdleInsights(Math.floor((Number(playTimeDeltaMs) || 0) / 60000), Math.random);
    if (hits <= 0) return;
    // [r101wudao] R-091：挂机心得只落入本人已开放的系（稀有道未达境界不随机命中；已投入者仍可手动顿悟）
    let realmIdx = 0;
    try {
      const srow: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
      realmIdx = wudaoRealmIndex(JSON.parse(String(srow?.save_data || '{}'))?.player?.realm);
    } catch { realmIdx = 0; }
    const openKeys = Object.keys(WUDAO_DAOS).filter((k) => realmIdx >= wudaoDaoGateRealm(k));
    const pool = openKeys.length > 0 ? openKeys : [Object.keys(WUDAO_DAOS)[0]];
    const perDao: Record<string, number> = {};
    for (let i = 0; i < hits; i++) {
      const k = pool[Math.min(pool.length - 1, Math.max(0, Math.floor(Math.random() * pool.length)))];
      perDao[k] = (perDao[k] || 0) + WUDAO_INSIGHT_EXP;
    }
    for (const k of Object.keys(perDao)) await wudaoAddExp(userId, k, perDao[k], 'idle');"""

EDITS = [
    ("E1 六道去重（阵→修炼速度 / 御→资源产出）", E1_OLD, E1_NEW),
    ("E2 门槛/价格纯逻辑注入 [wudaocore]", E2_OLD, E2_NEW),
    ("E3 祖父条款补偿助手", E3_OLD, E3_NEW),
    ("E4 GET 端点：境界/门槛/价格/补偿触发", E4_OLD, E4_NEW),
    ("E5 POST 端点：门槛放行 + 价格随境界", E5_OLD, E5_NEW),
    ("E6 退款补偿行用 cost", E6_OLD, E6_NEW),
    ("E7 POST 回执 cost 字段", E7_OLD, E7_NEW),
    ("E8 挂机心得只落已开放的系", E8_OLD, E8_NEW),
]

REQUIRES = [
    ("const WUDAO_MAX_LEVEL = 10;", 1, "等级上限（冻结面，本环不动）"),
    ("const WUDAO_BONUS_UNLOCK_LEVEL = 3;", 1, "加成解锁级（冻结面，本环不动）"),
    ("  return 25 * (l - 1) * l;", 1, "升级曲线纯函数（★本环刻意不动）"),
    ("const WUDAO_INSIGHT_CHANCE = 0.04;", 1, "挂机命中率（冻结面，本环不动）"),
    ("const WUDAO_INSIGHT_EXP = 10;", 1, "心得修为（冻结面，本环不动）"),
    ("const WUDAO_MANUAL_COST = 5000;", 1, "手动顿悟基础价（改后作价格表首档）"),
    ("const WUDAO_MANUAL_EXP = 100;", 1, "手动顿悟单次 exp（冻结面，本环不动）"),
    ("const WUDAO_LOG_KEEP = 50;", 1, "日志裁剪条数（冻结面）"),
    ("function wudaoPickDao(rng: () => number = Math.random): string {", 1, "纯逻辑块既有函数（保留定义）"),
    ("function insertMail(userId: number, title: string, content: string, sender: string, lingshi: number, opts?: { noChronicle?: boolean }): Promise<number> {", 1, "邮件通道（祖父补偿走它）"),
    ("function updatePlayerSave(", 1, "存档写通道（扣款用）"),
    ("CREATE TABLE IF NOT EXISTS activity_config (", 1, "KV 表（补偿幂等键载体）"),
    ("app.get('/api/wudao', authenticateToken", 1, "GET 端点唯一"),
    ("app.post('/api/wudao/insight', authenticateToken", 1, "POST 端点唯一"),
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-091 悟道体系重规划环（服务端 r101）")
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
        # ---- 本环改动：去重 ----
        ("R101 阵道改修炼速度", "  array: { name: '阵道', stat: 'cultivate', statName: '修炼速度', basePct: 1.0, stepPct: 0.25 },", 1),
        ("R101 御道改资源产出", "  tame:  { name: '御道', stat: 'gather', statName: '资源产出', basePct: 1.0, stepPct: 0.25 },", 1),
        ("R101 旧阵道(攻击)已清零", "  array: { name: '阵道', stat: 'attack'", 0),
        ("R101 旧御道(气血)已清零", "  tame:  { name: '御道', stat: 'maxHp'", 0),
        # ---- 门槛/价格 ----
        ("R101 境界序表", "const WUDAO_REALM_ORDER: string[] = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];", 1),
        ("R101 稀有道门槛表", "const WUDAO_DAO_REALM_GATE: Record<string, number> = { sword: 0, body: 0, pill: 0, spell: 0, array: 3, tame: 4 };", 1),
        ("R101 境界序解析", "function wudaoRealmIndex(realm: unknown): number {", 1),
        ("R101 门槛取用", "function wudaoDaoGateRealm(daoKey: string): number {", 1),
        ("R101 灵石价表(随境界)", "const WUDAO_MANUAL_COST_BY_REALM: number[] = [WUDAO_MANUAL_COST, 8000, 12000, 18000, 27000, 40000, 60000];", 1),
        ("R101 灵石价取用", "function wudaoManualCost(realmIdx: unknown): number {", 1),
        ("R101 长生档 60000", "60000];", 1),
        # ---- 祖父条款 ----
        ("R101 补偿助手定义", "async function wudaoRespecCompensateOnce(userId: number): Promise<void> {", 1),
        ("R101 补偿幂等键", "'r091_wudao_respec:' + userId", 1),
        ("R101 补偿先占键(INSERT OR IGNORE)",
         "const claim = await dbRun(\"INSERT OR IGNORE INTO activity_config (key, value) VALUES (?, '1')\", [key]).catch(() => null);", 1),
        ("R101 补偿走 insertMail", "await insertMail(userId, '悟道体系重规划补偿',", 1),
        ("R101 补偿率 50/exp", "const WUDAO_RESPEC_REFUND_PER_EXP = 50;", 1),
        ("R101 补偿在 GET 触发", "await wudaoRespecCompensateOnce(userId); // [r101wudao] 祖父条款：首次触达即一次性补偿", 1),
        ("R101 补偿在 POST 触发", "await wudaoRespecCompensateOnce(userId); // [r101wudao] 祖父条款：一次性补偿", 1),
        ("R101 补偿共 2 处触发", "await wudaoRespecCompensateOnce(userId);", 2),
        # ---- 门槛放行/锁定 ----
        ("R101 GET locked 计算(祖父放行)", "const locked = realmIdx < gateRealm && exp <= 0; // 已投入者祖父放行，不追溯锁死", 1),
        ("R101 GET 下发 gateRealmName", "gateRealmName: gateRealm > 0 ? WUDAO_REALM_ORDER[gateRealm] : null,", 1),
        ("R101 GET 下发 realmIndex", "realmIndex: realmIdx,", 1),
        ("R101 POST 门槛拦截(已投入放行)", "if (ownExp <= 0) return res.status(409).json({ error: `此道需 ${WUDAO_REALM_ORDER[gateRealm]} 起方可参悟`, code: 'DAO_LOCKED', gateRealmIndex: gateRealm });", 1),
        ("R101 POST cost 变量就位", "    const cost = wudaoManualCost(realmIdx); // [r101wudao] 灵石价随境界递增", 1),
        ("R101 POST 余额校验用 cost",
         "    const cost = wudaoManualCost(realmIdx); // [r101wudao] 灵石价随境界递增\n    if (bal < cost) return res.status(409).json({ error: `灵石不足：需 ${cost}，现有 ${bal}` });", 1),
        ("R101 POST 旧固定价校验已清零", "if (bal < WUDAO_MANUAL_COST)", 0),
        ("R101 POST 退款用 cost",
         "        sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + cost;\n      }).catch((e: any) => console.error('wudao insight refund error:', e?.message || e));", 1),
        ("R101 POST 回执 cost 字段",
         "      bonusText: added.level >= WUDAO_BONUS_UNLOCK_LEVEL ? `${d.statName} +${wudaoBonusPct(daoKey, added.level)}%` : null,\n      cost,", 1),
        ("R101 GET 下发 manual.cost 随境界", "manual: { cost: wudaoManualCost(realmIdx), exp: WUDAO_MANUAL_EXP },", 1),
        ("R101 旧 manual 固定价已清零", "manual: { cost: WUDAO_MANUAL_COST, exp: WUDAO_MANUAL_EXP },", 0),
        # ---- 挂机门槛 ----
        ("R101 挂机只落已开放的系", "const openKeys = Object.keys(WUDAO_DAOS).filter((k) => realmIdx >= wudaoDaoGateRealm(k));", 1),
        # ---- 冻结：曲线/常量一字不动 ----
        ("冻结 升级曲线未动", "  return 25 * (l - 1) * l;", 1),
        ("冻结 等级上限未动", "const WUDAO_MAX_LEVEL = 10;", 1),
        ("冻结 加成解锁级未动", "const WUDAO_BONUS_UNLOCK_LEVEL = 3;", 1),
        ("冻结 挂机命中率未动", "const WUDAO_INSIGHT_CHANCE = 0.04;", 1),
        ("冻结 手动 exp 未动", "const WUDAO_MANUAL_EXP = 100;", 1),
        ("冻结 基础价常量未动", "const WUDAO_MANUAL_COST = 5000;", 1),
        ("冻结 六道齐备(剑/体/丹/法)", "  sword: { name: '剑道', stat: 'attack', statName: '攻击', basePct: 2.0, stepPct: 0.5 },", 1),
        ("冻结 幂等标记就位", MARK, 8),
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
        print("  [%s] %-44s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 6) 语义自证
    sem_ok = (
        out.count("stat: 'cultivate'") == 1
        and out.count("stat: 'gather'") == 1
        and out.count("sword: { name: '剑道', stat: 'attack'") == 1
        and out.count("pill:  { name: '丹道', stat: 'maxHp'") == 1
        and out.count("await wudaoRespecCompensateOnce(userId);") == 2
        and out.count("wudaoManualCost(realmIdx)") == 2
    )
    ok = ok and sem_ok
    print("  [%s] %-44s cultivate=%d gather=%d sword=%d pill=%d comp=%d cost=%d"
          % ("OK" if sem_ok else "FAIL", "R101 语义自证(去重/补偿/价格各就位)",
             out.count("stat: 'cultivate'"), out.count("stat: 'gather'"),
             out.count("sword: { name: '剑道', stat: 'attack'"),
             out.count("pill:  { name: '丹道', stat: 'maxHp'"),
             out.count("await wudaoRespecCompensateOnce(userId);"),
             out.count("wudaoManualCost(realmIdx)")))

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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r101wudao-", suffix=".tmp")
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
