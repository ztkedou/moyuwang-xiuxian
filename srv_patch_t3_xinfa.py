# -*- coding: utf-8 -*-
r"""
srv_patch_t3_xinfa.py -- 0.8.7 批次 · 环 t3_xinfa087（T3 心法六卷 100 级 + 连点并发根治）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  不提供 `--out`：`localtest/chain_build.py` 会把上一环产物复制成私有工作副本
  再让本补丁就地改。

覆盖范围（0.8.7-build-plan §2-T3 / §4.1 契约）
--------------------------------------------------------------------------
  E1 [gongfacore] 数值重做：GONGFA_MAX_LEVEL 10→100；升级消耗 = TIER[floor((L-1)/10)]
      ×品级乘数（六卷未设品级，按玄 ×1 计；乘数表随公式留档）；攻/防/血 +1%/级（满级恰
      ×2.00），暴击/命中/闪避 +0.2%/级（满级恰 ×1.20）；expRate 通道本就不存在于六卷（不涉及）。
      数值来源《数值表-T2T3》§5（tools/_t23_calc.py 复算），满级累计投入：玄 528,000 /
      天 2,112,000（×4）。
  E2 GET /api/gongfa 扩展：契约字段 costNext（costToNext 保留为别名）；bonusPct 改双档；
      展示等级改以 level 列为准（旧档 exp 是 0.8.6 旧曲线累计值，与新曲线不可换算，从 exp
      反推会把旧 L10 玩家凭空抬到 L50+；level 列由守卫推进维护、逐行正确）；响应补
      tierCost/gradeMult 供客户端渲染价目曲线。伴生页 /myxxz/apps/gongfa/ 已于 0.8.3 退役
      （2026-09-29 实测：3 秒重定向回 /myxxz/），旧字段无线上消费方。
  E3 POST /api/gongfa/levelup 升级为严格三段式（铁律③）＋连点幂等：
      【占位】守卫推进等级位（UPDATE ... WHERE level=旧值；首建 INSERT level=1，UNIQUE 兜底）
              —— 同档并发/连点只一方生效，落败方在占位即 409，**未扣款**；
      【扣款】updatePlayerSave saveLock 互斥 + 锁内余额二次校验；
      【补偿】扣款失败守卫回退等级位（守卫式 WHERE level=新值；首建行直接删行），可重试。
      与旧序（先扣款后推进→落败退款）的差异：退款失败=玩家白扣（玩家受损且不可逆），
      回退失败=服务端白送一级（量级轻、有日志可查）——失败面从玩家侧挪到服务端侧。
      连点幂等：同档重复请求在占位即被守卫拒绝，零扣费零叠加；响应丢失后的重试会读到
      新等级、按新档计价，属「买下一级」而非重复扣费。
      频控 max 20→60/min（与 GET 同口径）：连点根治靠幂等占位而非限流硬拦，30 连点专项
      （e2e E4）的合法连发不再被令牌桶截胡。
  E4 全端点连点竞态盘点（sweep）——结论见下方 sweep 表。

★ sweep 表（2026-09-29 对 _chainstage/index_v28.v286.ts 全 165 端点盘点；行号=v286 现行）
--------------------------------------------------------------------------
  已合规（占位→扣款→补偿 / 守卫置状态→入账→失败回退，零改动）：
    /api/alchemy/start        :5595  占炉 INSERT(UNIQUE) → 扣款 → 补偿删炉
    /api/teahouse/bet         :7722  fun086 ORDER_CONTRACT（占次数位→注池 upsert→扣款→补偿）
    /api/fun/dice|sign|card   :7789/:7832/:7872  同上（占次数位→扣款→补偿删行 ×5）
    /api/farm/plant           :5745  INSERT(UNIQUE) → 扣种子 → 补偿删行（T10 扩田时保持此形态）
    /api/farm/harvest         :5796  守卫 harvested=1 → 入账 → 补偿回退标记
    /api/pet/play             :8592  gate upsert(times<max) → 入账 → 补偿回退占位
    /api/feast/attend         :7131  INSERT OR IGNORE 占位 → 入账 → 补偿删行
    /api/bounty/create        :9097  占单 INSERT → 扣费 → 补偿删单（bountyCreateCore）
    /api/bounty/cancel|complete  守卫置状态 → 退款/入账 → 失败回退状态可重试
    /api/market/purchase/confirm :3386  买家扣款在客户端权威档（本服既定架构边界，:3380 注释）；
                                      服务端原子锁定 listing + 托管入账，changes>0 全局唯一=天然幂等
  观察项（无「白扣无服务」面——服务无独占位、补偿退费在位；不构成本批修因，零改动）：
    /api/wudao/insight        :5940  先扣款后 exp 单语句 upsert（无独占位，退款失败仅日志）
    /api/pet/feed             :8528  先扣款后单语句 UPDATE（同上）
    /api/feast/open           :7085  扣A→扣B→失败退A / UNIQUE 冲突退双方（一生一次位在最后，
                                      补偿面完备；退款失败仅日志）
    /api/couple/propose       :6971  聘礼托管扣款后 INSERT pending（无 UNIQUE，同人并发可双托管，
                                      decline 逐单退回可回收；couple 域不在 0.8.7 任何环）
    /api/friends/gift         :6778  正向赠送（非扣款；每日上限为读检查，并发可超限 1~2 次）
  ★ 移交清单（环域内禁改，v2 评审中危-2；登记如下，由各环主在各自环内按铁律③自查）：
    - T10 域（环主 implGrotto）：/api/farm/unlock :5841（扣款形态未逐行审；plant/harvest 已合规）
    - T5 域（环主 implEventsSrv）：新 8 端点按铁律③设计（eventboss/talisman 三段式已写入契约 §4.2）
    - T7 域（环主 implSectSrv）：/api/sect/create :9696（INSERT 宗门→spendFromSave→补偿删宗，
      现状已合规，改造时保持）；/api/sect/gongfa/learn|upgrade :9594/:9605（贡献值扣减，归并 403 改码批）
    - T8 域（环主 implMentorSrv）：mentor 域 0 处扣款写端点（teach/greet 均为增益面），无移交修因

★ 业务拒绝一律 400/409，绝不 403
--------------------------------------------------------------------------
  客户端 Xc() 把 403 当会话失效强制登出。本补丁拒绝码全部保持 400/409/404/500，
  且门禁断言产物内 res.status(403) 计数与原文逐字相等（'same' 口径）。
"""
import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ 数值自检（《数值表-T2T3》§5.2）

TIER = [300, 500, 800, 1200, 2000, 3000, 5000, 8000, 12000, 20000]
GRADE = {"huang": 0.5, "xuan": 1, "di": 2, "tian": 4}


def _cum(lv, mult=1.0):
    return int(round(sum(TIER[(i - 1) // 10] * mult for i in range(1, lv + 1))))


# ============================================================ E1a [gongfacore] 头注释 + 常量

E1A_OLD = """// 六部功法（焚天诀/御剑术/不灭体/大衍诀/周天阵/御灵术）各 1..10 级，level 0=未入门；"""
E1A_NEW = """// 六部功法（焚天诀/御剑术/不灭体/大衍诀/周天阵/御灵术）各 1..100 级（0.8.7 T3），level 0=未入门；"""

E1B_OLD = """const GONGFA_MAX_LEVEL = 10;
const GONGFA_STEP_COST = 1000;  // 升到 L 级耗灵石 1000×L（L1=1000 … L10=10000；物价×10）
const GONGFA_BONUS_STEP_PCT = 2; // 每级对应属性 +2%（任务书"+2%×level"口径，Lv10=+20%）"""
E1B_NEW = """const GONGFA_MAX_LEVEL = 100;
// 0.8.7 T3（《数值表-T2T3》§5.2）：升到 L 级的单级消耗 = TIER[floor((L-1)/10)] × 品级乘数。
// TIER = 每 10 级一档的每级基价（L1-10 每级 300 … L91-100 每级 20000，玄品口径）；
// 满级累计投入：黄 264,000 / 玄 528,000 / 地 1,056,000 / 天 2,112,000。
const GONGFA_TIER_COST = [300, 500, 800, 1200, 2000, 3000, 5000, 8000, 12000, 20000];
const GONGFA_GRADE_MULT: Record<string, number> = { huang: 0.5, xuan: 1, di: 2, tian: 4 };
const GONGFA_GRADE_DEFAULT = 'xuan'; // 六卷未设品级，一律按玄（×1）计；乘数表随公式留档，定品级时直接挂表
// 属性成长（《数值表-T2T3》§5.1）：攻/防/血 +1%/级（满级恰 ×2.00），其余三卷 +0.2%/级（满级恰 ×1.20）
const GONGFA_MAIN_KEYS: Record<string, boolean> = { fentian: true, bumie: true, zhoutian: true };
const GONGFA_MAIN_STEP_PCT = 1;    // 焚天诀(攻击)/不灭体(防御)/周天阵(气血)
const GONGFA_MINOR_STEP_PCT = 0.2; // 御剑术(暴击)/大衍诀(命中)/御灵术(闪避)"""

# ============================================================ E1b [gongfacore] 纯函数

E1C_OLD = """// 升到 L 级本级消耗（纯）：100×L；非法输入钳 1..10
function gongfaCostToReach(level: unknown): number {
  const l = Math.min(GONGFA_MAX_LEVEL, Math.max(1, Math.floor(Number(level) || 1)));
  return GONGFA_STEP_COST * l;
}
// 升到 L 级累计投入 exp（纯）：Σ 100×i = 50×L×(L+1)（L1=100 … L10=5500）
function gongfaExpToReach(level: unknown): number {
  const l = Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(level) || 0)));
  // v28.1: exp curve MUST scale with GONGFA_STEP_COST. Was hard-coded 50*L*(L+1) (= 100/level) while cost is 1000/level -> 10x mismatch,
  return (GONGFA_STEP_COST / 2) * l * (l + 1);
}
// 由累计 exp 推导等级（纯）：0=未入门；恰达阈值升级（>=）；非法/负数安全
function gongfaLevelFromExp(exp: unknown): number {
  const e = Math.max(0, Math.floor(Number(exp) || 0));
  let lv = 0;
  while (lv < GONGFA_MAX_LEVEL && e >= gongfaExpToReach(lv + 1)) lv++;
  return lv;
}
const GONGFA_MAX_EXP_TOTAL = gongfaExpToReach(GONGFA_MAX_LEVEL); // 55000：满级累计投入
// 属性被动（纯）：+2%×level（0..20%，非法输入按 0 计）
function gongfaBonusPct(level: unknown): number {
  const lv = Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(level) || 0)));
  return GONGFA_BONUS_STEP_PCT * lv;
}"""
E1C_NEW = """// 升到 L 级的单级消耗（纯）：TIER[floor((L-1)/10)] × 品级乘数（缺省玄 ×1）；非法输入钳 1..100
function gongfaCostToReach(level: unknown): number {
  const l = Math.min(GONGFA_MAX_LEVEL, Math.max(1, Math.floor(Number(level) || 1)));
  const seg = Math.min(GONGFA_TIER_COST.length - 1, Math.floor((l - 1) / 10));
  const mult = GONGFA_GRADE_MULT[GONGFA_GRADE_DEFAULT] || 1;
  return Math.round(GONGFA_TIER_COST[seg] * mult);
}
// 升到 L 级累计投入（纯）：按段求和（玄品：L10=3,000 / L50=48,000 / L100=528,000）
function gongfaExpToReach(level: unknown): number {
  const l = Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(level) || 0)));
  let total = 0;
  for (let i = 1; i <= l; i++) total += gongfaCostToReach(i);
  return total;
}
// 由累计 exp 推导等级（纯）：0=未入门；恰达阈值升级（>=）；非法/负数安全。
// 0.8.7 起仅作无行兜底：旧档 exp 是 0.8.6 旧曲线（1000×L 累计）值，与新曲线不可换算，
// 展示等级一律以 level 列（守卫推进维护）为准，从 exp 反推会凭空涨级。
function gongfaLevelFromExp(exp: unknown): number {
  const e = Math.max(0, Math.floor(Number(exp) || 0));
  let lv = 0;
  while (lv < GONGFA_MAX_LEVEL && e >= gongfaExpToReach(lv + 1)) lv++;
  return lv;
}
const GONGFA_MAX_EXP_TOTAL = gongfaExpToReach(GONGFA_MAX_LEVEL); // 528000：满级累计投入（玄品口径）
// 属性被动（纯）：攻/防/血 +1%/级、其余 +0.2%/级（非法输入按 0 计；key 非法按小卷计）
function gongfaBonusPct(key: unknown, level: unknown): number {
  const lv = Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(level) || 0)));
  const main = key != null && Object.prototype.hasOwnProperty.call(GONGFA_MAIN_KEYS, asStr(key));
  return (main ? GONGFA_MAIN_STEP_PCT : GONGFA_MINOR_STEP_PCT) * lv;
}
// 展示辅助（纯）：百分比去浮点尾零（0.2→"0.2"、5→"5"、100→"100"）
function gongfaPctStr(n: unknown): string {
  const v = Number(n) || 0;
  return String(Math.round(v * 10) / 10);
}"""

# ============================================================ E2 API 区头注释 + GET 扩展

E2A_OLD = """// Y20 功法系统 API（伴生页 /yl/apps/gongfa/）：六部功法（焚天诀/御剑术/不灭体/大衍诀/周天阵/御灵术）
// 各 1..10 级；修炼即时完成，升到 L 级耗灵石 100×L，对应属性被动 +2%×level——
// 客户端权威架构下实际属性结算在客户端（与称号 attr_json/悟道加成同边界），服务端出权威数值+伴生页展示。
// 升级=扣灵石先行（updatePlayerSave saveLock 互斥+锁内二次校验）→ 守卫式推进（WHERE level=旧值，
// 并发双升只一方生效）→ 推进失败补偿退灵石可重试（wudao/insight 同款全或无）。"""
E2A_NEW = """// Y20 功法系统 API：六部功法（焚天诀/御剑术/不灭体/大衍诀/周天阵/御灵术）各 1..100 级（0.8.7 T3）。
// 修炼即时完成，升到 L 级耗 TIER[floor((L-1)/10)] 灵石（玄品口径），攻/防/血 +1%/级、其余 +0.2%/级——
// 客户端权威架构下实际属性结算在客户端（与称号 attr_json/悟道加成同边界），服务端出权威数值。
// 升级（0.8.7 严格三段式，见 levelup 处注释）：【占位】守卫推进等级位 →【扣款】锁内二次校验扣灵石
// →【补偿】扣款失败守卫回退等级位。同档连点在占位即被拒（零扣费零叠加）。"""

E2B_OLD = """    const gongfas = Object.keys(GONGFA_LIST).map((k) => {
      const d = GONGFA_LIST[k];
      const exp = byKey[k]?.exp || 0;
      const shown = gongfaLevelFromExp(exp); // 展示以 exp 推导为准（level 列仅为冗余缓存）
      const next = shown < GONGFA_MAX_LEVEL ? gongfaCostToReach(shown + 1) : null;
      return {
        key: k,
        name: d.name,
        stat: d.stat,
        statName: d.statName,
        level: shown,
        exp,
        costToNext: next == null ? 0 : next,
        bonusPct: gongfaBonusPct(shown),
        bonusText: shown > 0 ? `${d.statName} +${gongfaBonusPct(shown)}%` : `${d.statName}加成（修炼后 +2%/级）`,
        maxed: shown >= GONGFA_MAX_LEVEL,
      };
    });
    res.json({
      now: Date.now(),
      gongfas,
      maxLevel: GONGFA_MAX_LEVEL,
      stepCost: GONGFA_STEP_COST,
      bonusStepPct: GONGFA_BONUS_STEP_PCT,
      maxExpTotal: GONGFA_MAX_EXP_TOTAL,
      balance,
      hasSave: !!saveRow,
    });"""
E2B_NEW = """    const gongfas = Object.keys(GONGFA_LIST).map((k) => {
      const d = GONGFA_LIST[k];
      const exp = byKey[k]?.exp || 0;
      // 0.8.7：展示等级以 level 列为准（守卫推进维护）；无行=未入门 0 级
      const shown = byKey[k]
        ? Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(byKey[k].level) || 0)))
        : 0;
      const next = shown < GONGFA_MAX_LEVEL ? gongfaCostToReach(shown + 1) : null;
      const stepPct = shown > 0 ? gongfaBonusPct(k, shown) : (GONGFA_MAIN_KEYS[k] ? GONGFA_MAIN_STEP_PCT : GONGFA_MINOR_STEP_PCT);
      return {
        key: k,
        name: d.name,
        stat: d.stat,
        statName: d.statName,
        level: shown,
        exp,
        costNext: next == null ? 0 : next,
        costToNext: next == null ? 0 : next,
        bonusPct: gongfaBonusPct(k, shown),
        bonusText: shown > 0 ? `${d.statName} +${gongfaPctStr(gongfaBonusPct(k, shown))}%` : `${d.statName}加成（修炼后 +${gongfaPctStr(stepPct)}%/级）`,
        maxed: shown >= GONGFA_MAX_LEVEL,
      };
    });
    res.json({
      now: Date.now(),
      gongfas,
      maxLevel: GONGFA_MAX_LEVEL,
      tierCost: GONGFA_TIER_COST,
      gradeMult: GONGFA_GRADE_MULT,
      maxExpTotal: GONGFA_MAX_EXP_TOTAL,
      balance,
      hasSave: !!saveRow,
    });"""

# ============================================================ E3 levelup 严格三段式（整段重写）

E3_OLD = """// POST /api/gongfa/levelup {gongfa:'fentian'|...} — 修炼升级：灵石 100×目标级 → level+1（即时完成）。
// 顺序=先扣灵石（防白嫖）后守卫推进；推进失败补偿退灵石（退款失败仅记日志，不产生复制收益）
app.post('/api/gongfa/levelup', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `gongfa:levelup:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const key = asStr(req.body?.gongfa);
    if (!gongfaOk(key)) return res.status(400).json({ error: '未知的功法' });
    const g = await dbGet('SELECT id FROM gongfa WHERE key = ?', [key]);
    if (!g) return res.status(500).json({ error: '功法目录缺失' });
    const gid = Number(g.id);
    // 当前等级（无行=未入门 0 级）
    const row = await dbGet('SELECT level, exp FROM player_gongfa WHERE player_id = ? AND gongfa_id = ?', [userId, gid]);
    const curLevel = Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(row?.level) || 0)));
    if (curLevel >= GONGFA_MAX_LEVEL) return res.status(409).json({ error: '该功法已大成（Lv10），无法再进阶' });
    const cost = gongfaCostToReach(curLevel + 1);
    // 预检：角色与灵石余额（并发窗口由 updatePlayerSave 锁内二次校验兜底）
    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < cost) return res.status(409).json({ error: `灵石不足：需 ${cost}，现有 ${bal}` });
    // 1) 扣灵石（saveLock 互斥 + gm_revision++ 促客户端拉新档；锁内余额不足拒绝）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') { short = true; return; }
      const b = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0));
      if (b < cost) { short = true; return; }
      sd.player.spiritStones = b - cost;
    });
    if (!paid.ok || short) {
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '修炼失败，请重试') });
    }
    // 2) 守卫式推进：WHERE level=旧值（并发双升只一方生效）；无行则首建（PK 冲突=他人已建→视为并发失败）
    let advanced = false;
    if (row) {
      const up = await dbRun(
        'UPDATE player_gongfa SET level = level + 1, exp = exp + ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?',
        [cost, userId, gid, curLevel]
      );
      advanced = up.changes > 0;
    } else {
      try {
        const ins = await dbRun('INSERT INTO player_gongfa (player_id, gongfa_id, level, exp) VALUES (?, ?, 1, ?)', [userId, gid, cost]);
        advanced = ins.changes > 0;
      } catch (e: any) {
        if (String(e?.message || '').includes('UNIQUE')) advanced = false;
        else throw e;
      }
    }
    if (!advanced) {
      // 补偿：并发他手已推进，本次灵石退还，不作数可重试
      await updatePlayerSave(userId, (sd: any) => {
        if (!sd.player || typeof sd.player !== 'object') return;
        sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + cost;
      }).catch((e: any) => console.error('gongfa levelup refund error:', e?.message || e));
      return res.status(409).json({ error: '修炼并发冲突，灵石已退还，请重试' });
    }
    const newLevel = curLevel + 1;
    const d = GONGFA_LIST[key];
    res.json({
      ok: true,
      gongfa: key,
      name: d.name,
      level: newLevel,
      exp: gongfaExpToReach(newLevel),
      cost,
      bonusPct: gongfaBonusPct(newLevel),
      bonusText: `${d.statName} +${gongfaBonusPct(newLevel)}%`,
      maxed: newLevel >= GONGFA_MAX_LEVEL,
    });
  } catch (e: any) {
    console.error('gongfa levelup error:', e?.message || e);
    if (!res.headersSent) res.status(500).json({ error: '服务器繁忙' });
  }
});"""

E3_NEW = """// POST /api/gongfa/levelup {gongfa:'fentian'|...} — 修炼升级（0.8.7 T3 重做：严格三段式 + 连点幂等）。
// 顺序=【占位】守卫推进等级位（WHERE level=旧值；首建 INSERT level=1）→【扣款】saveLock 锁内二次校验
// 扣灵石 →【补偿】扣款失败守卫回退等级位（首建行删行），可重试。
// 同档并发/连点只一方赢占位，落败方**未扣款**直接 409（幂等：同档重复请求零扣费零叠加）；
// 响应丢失后的重试读到新等级按新档计价，属买下一级而非重复扣费。
// 旧序（先扣款后推进→落败退款）的退款失败=玩家白扣且不可逆；占位优先把失败面挪到服务端侧
// （回退失败=白送一级，量级轻且留日志）。
app.post('/api/gongfa/levelup', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `gongfa:levelup:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const key = asStr(req.body?.gongfa);
    if (!gongfaOk(key)) return res.status(400).json({ error: '未知的功法' });
    const g = await dbGet('SELECT id FROM gongfa WHERE key = ?', [key]);
    if (!g) return res.status(500).json({ error: '功法目录缺失' });
    const gid = Number(g.id);
    // 当前等级（level 列=守卫推进维护的权威值；无行=未入门 0 级）
    const row = await dbGet('SELECT level, exp FROM player_gongfa WHERE player_id = ? AND gongfa_id = ?', [userId, gid]);
    const curLevel = Math.min(GONGFA_MAX_LEVEL, Math.max(0, Math.floor(Number(row?.level) || 0)));
    if (curLevel >= GONGFA_MAX_LEVEL) return res.status(409).json({ error: '该功法已大成（Lv100），无法再进阶' });
    const cost = gongfaCostToReach(curLevel + 1);
    // 预检：角色与灵石余额（只读快查；权威校验在【扣款】锁内二次进行）
    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < cost) return res.status(409).json({ error: `灵石不足：需 ${cost}，现有 ${bal}` });
    // 1)【占位】守卫推进：WHERE level=旧值（同档并发/连点只一方生效）；无行则首建 L1（PK 冲突=他人已建→占位失败）
    let advanced = false;
    let inserted = false;
    if (row) {
      const up = await dbRun(
        'UPDATE player_gongfa SET level = level + 1, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?',
        [userId, gid, curLevel]
      );
      advanced = up.changes > 0;
    } else {
      try {
        const ins = await dbRun('INSERT INTO player_gongfa (player_id, gongfa_id, level, exp) VALUES (?, ?, 1, 0)', [userId, gid]);
        advanced = ins.changes > 0;
        inserted = advanced;
      } catch (e: any) {
        if (String(e?.message || '').includes('UNIQUE')) advanced = false;
        else throw e;
      }
    }
    if (!advanced) {
      // 并发他手已推进同档：未扣款直接 409（连点幂等；客户端刷新后按新档续买）
      return res.status(409).json({ error: '修炼并发冲突，请刷新后重试' });
    }
    // 2)【扣款】saveLock 互斥 + 锁内余额二次校验；gm_revision++ 促客户端拉新档
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') { short = true; return; }
      const b = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0));
      if (b < cost) { short = true; return; }
      sd.player.spiritStones = b - cost;
    });
    if (!paid.ok || short) {
      // 3)【补偿】扣款失败：守卫回退等级位（本次占位不作数可重试）；首建行直接删行
      const rev = inserted
        ? await dbRun('DELETE FROM player_gongfa WHERE player_id = ? AND gongfa_id = ? AND level = 1', [userId, gid])
        : await dbRun('UPDATE player_gongfa SET level = level - 1, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?', [userId, gid, curLevel + 1]);
      if (!rev.changes) console.error('gongfa levelup revert failed: user=%s gongfa=%s level=%s', userId, key, curLevel + 1);
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '修炼失败，请重试') });
    }
    // 投入入账：exp=累计投入，服务端侧累加（守卫 WHERE level=新值，防并发串档）；失败仅日志（展示面）
    await dbRun(
      'UPDATE player_gongfa SET exp = exp + ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?',
      [cost, userId, gid, curLevel + 1]
    ).catch((e: any) => console.error('gongfa exp update error:', e?.message || e));
    const newLevel = curLevel + 1;
    const d = GONGFA_LIST[key];
    res.json({
      ok: true,
      gongfa: key,
      name: d.name,
      level: newLevel,
      exp: Math.max(0, Math.floor(Number(row?.exp) || 0)) + cost,
      cost,
      spent: cost,
      bonusPct: gongfaBonusPct(key, newLevel),
      bonusText: `${d.statName} +${gongfaPctStr(gongfaBonusPct(key, newLevel))}%`,
      maxed: newLevel >= GONGFA_MAX_LEVEL,
    });
  } catch (e: any) {
    console.error('gongfa levelup error:', e?.message || e);
    if (!res.headersSent) res.status(500).json({ error: '服务器繁忙' });
  }
});"""

EDITS = [
    ("E1a-core头注释", E1A_OLD, E1A_NEW),
    ("E1b-常量区", E1B_OLD, E1B_NEW),
    ("E1c-纯函数区", E1C_OLD, E1C_NEW),
    ("E2a-API区头注释", E2A_OLD, E2A_NEW),
    ("E2b-GET扩展", E2B_OLD, E2B_NEW),
    ("E3-levelup三段式", E3_OLD, E3_NEW),
]

REQUIRES = [
    ("function gongfaCostToReach(", 1, "基线 [gongfacore] 必须在位（环序：本环为 0.8.7 第一环）"),
    ("CREATE TABLE IF NOT EXISTS fun_daily", 1, "fun086 环必须先跑（chain 序 p0→p2→p2b→p3→fun086→t3_xinfa087）"),
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 0) 数值表自检（《数值表-T2T3》§5.2 / tools/_t23_calc.py 同口径，玄品 ×1）
    assert _cum(10) == 3000, _cum(10)
    assert _cum(20) == 8000, _cum(20)
    assert _cum(50) == 48000, _cum(50)
    assert _cum(100) == 528000, _cum(100)
    assert _cum(100, 0.5) == 264000 and _cum(100, 4) == 2112000
    assert _cum(90) == 328000, _cum(90)
    assert TIER[0] == 300 and TIER[-1] == 20000
    print("  [OK] 数值表自检：玄品累计 L10=3000 / L50=48000 / L90=328000 / L100=528000；黄 264000 / 天 2112000")

    # 1) 链序依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 2) 幂等
    if "GONGFA_TIER_COST" in src or "GONGFA_MAIN_STEP_PCT" in src:
        fail("source looks already patched（已存在 GONGFA_TIER_COST / GONGFA_MAIN_STEP_PCT）")

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:120]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 5) 门禁
    gates = [
        # ---- E1 数值 ----
        ("E1 GONGFA_MAX_LEVEL=100", "const GONGFA_MAX_LEVEL = 100;", 1, None),
        ("E1 旧 MAX_LEVEL=10 清零", "const GONGFA_MAX_LEVEL = 10;", 0, None),
        ("E1 TIER 十档", "const GONGFA_TIER_COST = [300, 500, 800, 1200, 2000, 3000, 5000, 8000, 12000, 20000];", 1, None),
        ("E1 品级乘数表", "const GONGFA_GRADE_MULT: Record<string, number> = { huang: 0.5, xuan: 1, di: 2, tian: 4 };", 1, None),
        ("E1 缺省玄 ×1", "const GONGFA_GRADE_DEFAULT = 'xuan';", 1, None),
        ("E1 主卷集合", "const GONGFA_MAIN_KEYS: Record<string, boolean> = { fentian: true, bumie: true, zhoutian: true };", 1, None),
        ("E1 主卷 +1%/级", "const GONGFA_MAIN_STEP_PCT = 1;", 1, None),
        ("E1 副卷 +0.2%/级", "const GONGFA_MINOR_STEP_PCT = 0.2;", 1, None),
        ("E1 旧 STEP_COST 清零", "const GONGFA_STEP_COST", 0, None),
        ("E1 旧 BONUS_STEP_PCT 清零", "GONGFA_BONUS_STEP_PCT", 0, None),
        ("E1 单级消耗走 TIER 段价", "const seg = Math.min(GONGFA_TIER_COST.length - 1, Math.floor((l - 1) / 10));", 1, None),
        ("E1 满级累计注释 528000", "const GONGFA_MAX_EXP_TOTAL = gongfaExpToReach(GONGFA_MAX_LEVEL); // 528000", 1, None),
        ("E1 bonusPct 双参签名", "function gongfaBonusPct(key: unknown, level: unknown): number {", 1, None),
        ("E1 pct 去尾零辅助", "function gongfaPctStr(n: unknown): string {", 1, None),
        # ---- E2 GET ----
        ("E2 契约字段 costNext", "costNext: next == null ? 0 : next,", 1, None),
        ("E2 costToNext 别名保留", "costToNext: next == null ? 0 : next,", 1, None),
        ("E2 等级以 level 列为准", "Math.floor(Number(byKey[k].level) || 0)", 1, None),
        ("E2 旧 exp 反推展示清零", "const shown = gongfaLevelFromExp(exp); // 展示以 exp 推导为准", 0, None),
        ("E2 bonusPct 带 key", "bonusPct: gongfaBonusPct(k, shown),", 1, None),
        ("E2 价目表下发", "tierCost: GONGFA_TIER_COST,", 1, None),
        ("E2 品级表下发", "gradeMult: GONGFA_GRADE_MULT,", 1, None),
        ("E2 旧 stepCost 字段清零", "stepCost: GONGFA_STEP_COST,", 0, None),
        ("E2 旧 bonusStepPct 字段清零", "bonusStepPct: GONGFA_BONUS_STEP_PCT,", 0, None),
        # ---- E3 levelup ----
        ("E3 满级口径 Lv100", "该功法已大成（Lv100），无法再进阶", 1, None),
        ("E3 旧 Lv10 满级口径清零", "该功法已大成（Lv10），无法再进阶", 0, None),
        ("E3 占位守卫推进", "UPDATE player_gongfa SET level = level + 1, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?", 1, None),
        ("E3 占位首建 L1 零投入", "INSERT INTO player_gongfa (player_id, gongfa_id, level, exp) VALUES (?, ?, 1, 0)", 1, None),
        ("E3 旧首建带投入清零", "VALUES (?, ?, 1, ?)", 0, None),
        ("E3 并发落败未扣款 409", "return res.status(409).json({ error: '修炼并发冲突，请刷新后重试' });", 1, None),
        ("E3 旧退款话术清零", "修炼并发冲突，灵石已退还，请重试", 0, None),
        ("E3 补偿·首建删行", "DELETE FROM player_gongfa WHERE player_id = ? AND gongfa_id = ? AND level = 1", 1, None),
        ("E3 补偿·守卫回退", "UPDATE player_gongfa SET level = level - 1, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?", 1, None),
        ("E3 回退失败留日志", "gongfa levelup revert failed", 1, None),
        ("E3 投入服务端累加", "UPDATE player_gongfa SET exp = exp + ?, updated_at = CURRENT_TIMESTAMP WHERE player_id = ? AND gongfa_id = ? AND level = ?", 1, None),
        ("E3 契约字段 spent", "spent: cost,", 1, None),
        ("E3 频控放宽到 60/min", "rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `gongfa:levelup:", 1, None),
        ("E3 旧频控 20/min 清零", "rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `gongfa:levelup:", 0, None),
        # ---- 403 语义红线：本补丁不新增任何 403（与原文逐字相等）----
        ("E 未新增 403 拒绝", "res.status(403)", None, "same"),
        # ---- 基线未被破坏 ----
        ("基线 六卷目录未动", "fentian:  { name: '焚天诀', stat: 'attack',  statName: '攻击' },", 1, None),
        ("基线 player_gongfa 表未动", "CREATE TABLE IF NOT EXISTS player_gongfa", 1, None),
        ("基线 wudao 未动", "app.post('/api/wudao/insight'", 1, None),
        ("基线 预检余额闸门仍在", "if (bal < cost) return res.status(409).json({ error: `灵石不足：需 ${cost}，现有 ${bal}` });", 2, None),  # 基线 2 处：farm/unlock :5852 + gongfa/levelup（同款行，铁律⑤不得误伤）
    ]
    ok = True
    for g in gates:
        label, needle, exp = g[0], g[1], g[2]
        op = g[3] if len(g) > 3 else None
        if op == "same":
            exp = src.count(needle)
            shown = "expect==base(%d)" % exp
        else:
            shown = "expect==%d" % exp
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-32s actual=%d %s" % ("OK" if good else "FAIL", label, act, shown))
    if not ok:
        fail("门禁未全过")

    # 6) ★ 顺序契约位置断言：levelup 端点内 占位 < 扣款 < 补偿（计数对、次序错照样是缺陷）
    i = out.find("app.post('/api/gongfa/levelup'")
    if i < 0:
        fail("顺序契约校验：找不到 levelup 端点")
    j = out.find("app.post(", i + 30)
    seg = out[i:j if j > 0 else len(out)]
    p_place = seg.find("1)【占位】")
    p_deduct = seg.find("2)【扣款】")
    p_comp = seg.find("3)【补偿】")
    if not (0 <= p_place < p_deduct < p_comp):
        fail("顺序契约被破坏：占位(%d) → 扣款(%d) → 补偿(%d) 必须严格递增" % (p_place, p_deduct, p_comp))
    q_upd = seg.find("updatePlayerSave(userId")
    q_adv = seg.find("UPDATE player_gongfa SET level = level + 1")
    if not (0 <= q_adv < q_upd):
        fail("顺序契约被破坏：守卫推进(%d) 必须早于扣款(%d)" % (q_adv, q_upd))
    print("  [OK] 顺序契约：levelup 为「先占等级位 → 再扣款 → 失败补偿回退」（铁律③）")

    # 6b) 幂等断言：占位失败路径必须先于扣款 return（落败方零扣费）
    p409 = seg.find("return res.status(409).json({ error: '修炼并发冲突，请刷新后重试' });")
    if not (0 <= q_adv < p409 < q_upd):
        fail("幂等契约被破坏：并发落败 409(%d) 必须在扣款(%d) 之前返回" % (p409, q_upd))
    print("  [OK] 幂等契约：同档并发落败在扣款前返回（零扣费零叠加）")

    # 7) 往返自证：把每个 new 换回 old 必须逐字复现原文
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".t3xinfa-", suffix=".tmp")
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
