# -*- coding: utf-8 -*-
r"""
srv_patch_t8_mentor.py -- 0.8.7 批次 · T8 师徒服务端（环 t8_mentor，SRV_CHAIN 第 10 环）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  不提供 `--out`：`localtest/chain_build.py` 会把上一环产物复制成私有工作副本
  再让本补丁就地改。

覆盖范围（T8 师徒重构 · 拜师改申请-审批制）
--------------------------------------------------------------------------
  C1  POST /api/mentor/apprentice —— INSERT status 'active'→'pending'（守卫条件逐字保留）；
      捕获部分唯一索引 UNIQUE 违规转 409（重复申请兜底，绝不 500）；双方邮件改「申请/回执」语境，
      师傅信指向游戏内仙务·师徒页签（替换 /myxxz/apps/mentor/ 字样）；响应 {ok,status:'pending',mentor}
  N1  POST /api/mentor/decide {apprenticeId,action:'accept'|'decline'} —— 新端点。
      仅被申请师傅可调（他人 400）；无 pending 409；过期（>MENTOR_APPLY_TTL_MS=48h）惰性置 declined+409；
      accept=境界/等级差重验 + 守卫式单语句 UPDATE pending→active（门下<3、双方非 7 天解除冷却，
      并发双审批只一方 changes=1）+ 双方邮件；decline=置 declined（不进冷却）+ 申请人邮件
  N2  POST /api/mentor/cancel —— 徒弟撤回自己的 pending（置 declined，不进冷却，可立即再拜）；409 无 pending
  C2  GET /api/mentor/my 扩展 —— +myPending{mentorId,mentorName,since} +pendingIncoming[
      {apprenticeId,name,realmName,level,since}] +teachDone +taughtApprenticeId
      +consts{teachExpBase,teachVirtue,applyTtlMs}；history 过滤改 NOT IN('pending','declined')；
      读取时惰性把过期 pending 置 declined（零定时任务惯例）
  N3  GET /api/mentor/search 扩展 —— candidates 行 +apprenticeCount +full（每候选一个 COUNT 子查询）
  ——  graduate 补徒弟出师贺礼邮件 floor(MENTOR_GRAD_GIFT_BASE×realmMultOf(徒))，
      每徒弟每日限 1 笔（当日已有 completed 行（不含本次）→ 贺礼置 0，出师不受影响）；
      贺礼发信失败仅日志不回滚出师（小额礼按金额分级缩小补偿面；师傅侧大额回馈回滚保护维持原样）

设计依据：docs/0.8.7-design/T8-师徒重构.md + 数值表-T7T8.md（T8-7 TTL=48h / T8-8 贺礼基数=3000 /
T8-9 每徒每日限 1 笔）。新表 0 张、加列 0 列（mentorships.status='pending' 为 Y6B 预留位；
'declined' 新取值——表无 CHECK 约束，零迁移；冷却查询只认 'expired'，declined 天然不进冷却）。

★ 业务拒绝一律 400/409，绝不 403（客户端 Xc() 把 403 当会话失效强制登出）
--------------------------------------------------------------------------
师徒域存量零业务 403（T8 案 §1.1 全量复核）；本补丁新增端点全部 400/409/401，
门禁以 op='same' 钉死 `res.status(403)` 计数与基线逐字相等。

★ 本批新增/变更的门禁计数清单（供接线人落 check_srv_087；均为对【链尾产物】的 grep -o 计数）
--------------------------------------------------------------------------
  /api/mentor/decide                        0 → 1
  '/api/mentor/cancel'                      0 → 1
  SELECT ?, ?, 'pending', ?                 0 → 1
  SELECT ?, ?, 'active', ?                  1 → 0
  MENTOR_APPLY_TTL_MS                       0 → 6（定义 / mentorApplyExpired 函数体 /
                                            my 惰性归档参数 / C1 邮件 ttl / decide 过期文案 / consts 下发）
                                            ★ 注意：设计案 §8.1④ 写「恰 2（定义+consts）」是起草期估计，
                                            按实现实际应为 6，接线人按 6 落门禁
  MENTOR_GRAD_GIFT_BASE                     0 → 2（定义 + mentorGradGift 函数体）
  function mentorApplyExpired               0 → 1（decide 调用处另计， mentorApplyExpired( 全文 2）
  function mentorGradGift                   0 → 1（graduate 调用处另计， mentorGradGift( 全文 2）
  myPending:                                0 → 1
  pendingIncoming:                          0 → 1
  teachDone:                                0 → 1
  taughtApprenticeId:                       0 → 1
  consts: { teachExpBase                    0 → 1
  m.status != 'active'                      1 → 0（history 过滤改写）
  m.status NOT IN ('pending', 'declined')   0 → 1
  apprentice_count                          0 → 2（search SQL 子查询列 + 映射读值）
  apprenticeCount:                          0 → 1
  status = 'declined'                       0 → 4（my 惰性归档 / decide 过期 / decide decline / cancel）
  app.post('/api/mentor/                    5 → 7（+decide +cancel）
  app.get('/api/mentor/                     3 → 3（不变）
  你已正式拜                                1 → 0（旧即时生效邮件清零）
  res.status(403)                           与基线逐字相等（22，'same' 门禁）
  const MENTOR_MAX_APPRENTICES = 3;         1（基线未动）
  const TEACH_EXP_BASE = 30000;             1（基线未动）
  const GREET_STONES_BASE = 200;            1（基线未动）
"""
import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ E1a [mentorcore] 新常量

E1A_OLD = "const MENTOR_EXPIRE_COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000; // 解除后双方冷却 7 天"

E1A_NEW = E1A_OLD + """
// 0.8.7 申请-审批制新增常量（数值定档《数值表-T7T8》T8-7/T8-8/T8-9；declined 不进冷却，冷却只认 expired）
const MENTOR_APPLY_TTL_MS = 48 * 3600 * 1000;   // 拜师申请有效期 48 小时（超时惰性置 declined）
const MENTOR_GRAD_GIFT_BASE = 3000;             // 徒弟出师贺礼基数：贺礼=floor(基数×realmMultOf(徒弟))，每徒每日限 1 笔"""

# ============================================================ E1b [mentorcore] 纯函数

E1B_OLD = """// 搜索词规范化（纯）：trim 后 1..16 字；空/超长/null → null"""

E1B_NEW = """// 申请过期（纯）：pending 行 created_at 距今超过申请有效期（48h）即过期（恰满算过期；脏数据按过期）
function mentorApplyExpired(createdAtMs: unknown, nowMs: number): boolean {
  const t = Number(createdAtMs);
  return !(Number.isFinite(t) && t > 0) || nowMs - t >= MENTOR_APPLY_TTL_MS;
}
// 出师贺礼（纯）：floor(基数 × realmMultOf(徒弟))，负值钳 0
function mentorGradGift(realmMult: unknown): number {
  return Math.floor(Math.max(0, Number(realmMult) || 0) * MENTOR_GRAD_GIFT_BASE);
}
// 搜索词规范化（纯）：trim 后 1..16 字；空/超长/null → null"""

# ============================================================ E2 C1 INSERT 'active'→'pending' + UNIQUE 兜底

E2_OLD = """    const now = Date.now();
    const coolSince = now - MENTOR_EXPIRE_COOLDOWN_MS;
    // 守卫式单语句插入：全部门槛一次原子生效（并发双拜只一方 changes=1）
    const ins = await dbRun(
      `INSERT INTO mentorships (mentor_id, apprentice_id, status, created_at)
       SELECT ?, ?, 'active', ?
       WHERE (SELECT COUNT(*) FROM mentorships WHERE mentor_id = ? AND status = 'active') < ?
         AND NOT EXISTS (SELECT 1 FROM mentorships WHERE apprentice_id = ? AND status = 'active')
         AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))
         AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))`,
      [targetId, userId, now, targetId, MENTOR_MAX_APPRENTICES, userId, coolSince, userId, userId, coolSince, targetId, targetId]
    );
"""

E2_NEW = """    const now = Date.now();
    const coolSince = now - MENTOR_EXPIRE_COOLDOWN_MS;
    // 0.8.7 拜师改申请-审批制：status 由 'active' 改 'pending'（守卫条件逐字保留；并发双拜只一方 changes=1）。
    // 部分唯一索引 idx_mentorships_apprentice_active(pending,active) 兜底「重复申请」：
    // 守卫只挡 active，已有 pending 行时 INSERT 撞索引 ⇒ 捕获 UNIQUE 转 409（绝不 500 / 绝不白扣）。
    let ins: { lastID: number; changes: number };
    try {
      ins = await dbRun(
        `INSERT INTO mentorships (mentor_id, apprentice_id, status, created_at)
         SELECT ?, ?, 'pending', ?
         WHERE (SELECT COUNT(*) FROM mentorships WHERE mentor_id = ? AND status = 'active') < ?
           AND NOT EXISTS (SELECT 1 FROM mentorships WHERE apprentice_id = ? AND status = 'active')
           AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))
           AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))`,
        [targetId, userId, now, targetId, MENTOR_MAX_APPRENTICES, userId, coolSince, userId, userId, coolSince, targetId, targetId]
      );
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '你已有一份待处理的拜师申请，可先撤回再重新申请' });
      throw e;
    }
"""

# ============================================================ E3 C1 邮件 + 响应

E3_OLD = """    insertMail(targetId, '拜师',
      `道友「${myName}」仰慕你修行精深，正式拜入你门下。\\n\\n· 徒弟收益的 ${MENTOR_TAX_RATE * 100}%（修为/灵石）将自动奉上\\n· 师徒同行（双方在线）时，徒弟服务端结算收益 +${Math.round((MENTOR_BONUS_MULT - 1) * 100)}%\\n· 徒弟金丹期出师时：你将获得其拜师以来累计灵石收益 ${MENTOR_GRAD_RATE * 100}% 的出师回馈 + 7 天 ×${MENTOR_BUFF_MULT} 收益增益 + 称号「良师益友」\\n\\n（若不欲收徒，可在 /myxxz/apps/mentor/ 解除关系；解除后双方冷却 7 天）`,
      'system', 0).catch((e: any) => console.error('mentor bind mail(target) error:', e?.message || e));
    insertMail(userId, '拜师成功',
      `你已正式拜「${targetName}」为师。\\n\\n· 师徒同行（双方在线）时，你的服务端结算收益 +${Math.round((MENTOR_BONUS_MULT - 1) * 100)}%\\n· 师傅将抽成你收益的 ${MENTOR_TAX_RATE * 100}%（师傅入账）\\n· 修至金丹期后可在师徒页出师\\n\\n尊师重道，修行有道。`,
      'system', 0).catch((e: any) => console.error('mentor bind mail error:', e?.message || e));
    res.json({ ok: true, mentor: { id: targetId, name: targetName }, since: now });
"""

E3_NEW = """    // 0.8.7：信只告知「收到申请」——正式生效以师傅在游戏内仙务·师徒页签收纳为准
    const rnName = (i: unknown) => (Number.isInteger(Number(i)) && Number(i) >= 0 ? REALM_ORDER_FOR_RANKING[Number(i)] || '' : '');
    const ttlH = Math.round(MENTOR_APPLY_TTL_MS / 3600000);
    insertMail(targetId, '拜师申请',
      `道友「${myName}」（${rnName(mine.realm_index)}${Number(mine.realm_level) || ''}层）仰慕你修行精深，递交了拜师申请。\\n\\n· 申请 ${ttlH} 小时内有效，逾期自动作废\\n· 游戏内「仙务 → 师徒」页签可收纳或婉拒（收纳前关系不生效，双方无福利/抽成）\\n· 收纳后：徒弟收益的 ${MENTOR_TAX_RATE * 100}%（修为/灵石）将自动奉上；师徒同行（双方在线）时徒弟结算收益 +${Math.round((MENTOR_BONUS_MULT - 1) * 100)}%；其金丹期出师时你将获得累计灵石收益 ${MENTOR_GRAD_RATE * 100}% 回馈 + 7 天 ×${MENTOR_BUFF_MULT} 收益增益 + 称号「良师益友」`,
      'system', 0).catch((e: any) => console.error('mentor bind mail(target) error:', e?.message || e));
    insertMail(userId, '拜师申请已提交',
      `你已向「${targetName}」递交拜师申请，等待对方收纳。\\n\\n· 申请 ${ttlH} 小时内有效，期间可在游戏内师徒页签撤回\\n· 被婉拒或撤回均不进冷却，可立刻改投他人\\n· 对方收纳后即刻生效，届时将另收到拜师成功信`,
      'system', 0).catch((e: any) => console.error('mentor bind mail error:', e?.message || e));
    res.json({ ok: true, status: 'pending', mentor: { id: targetId, name: targetName }, since: now });
"""

# ============================================================ E4a C2 my：惰性归档 + 扩展查询（上半）

E4A_OLD = """    const now = Date.now();
    const rn = (i: unknown) => (Number.isInteger(Number(i)) && Number(i) >= 0 ? REALM_ORDER_FOR_RANKING[Number(i)] || '' : '');
    const [meRow, mentorRow, appRows, histRows, coolRow] = await Promise.all([
"""

E4A_NEW = """    const now = Date.now();
    const rn = (i: unknown) => (Number.isInteger(Number(i)) && Number(i) >= 0 ? REALM_ORDER_FOR_RANKING[Number(i)] || '' : '');
    // 0.8.7 申请-审批制：惰性归档——读取时把超过申请有效期（48h，见 [mentorcore] 常量区）的 pending 置 declined
    //（幂等，零定时任务惯例；declined 不进冷却，部分唯一索引位随之释放，申请人可立刻改投他人）
    await dbRun("UPDATE mentorships SET status = 'declined' WHERE status = 'pending' AND created_at < ?", [now - MENTOR_APPLY_TTL_MS]).catch(() => {});
    const [meRow, mentorRow, appRows, histRows, coolRow, pendRow, incRows, teachRow] = await Promise.all([
"""

# ============================================================ E4b C2 my：扩展查询（下半）

E4B_OLD = """      dbGet("SELECT MAX(ended_at) AS e FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND (mentor_id = ? OR apprentice_id = ?)", [userId, userId]),
    ]);
"""

E4B_NEW = """      dbGet("SELECT MAX(ended_at) AS e FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND (mentor_id = ? OR apprentice_id = ?)", [userId, userId]),
      // 0.8.7：我发出的待审申请（作为徒弟；过期行已被上方惰性归档，此处必是新申请）
      dbGet(
        `SELECT m.created_at, m.mentor_id, COALESCE(NULLIF(r.name, ''), u.username) AS name
         FROM mentorships m JOIN users u ON u.id = m.mentor_id LEFT JOIN rankings r ON r.user_id = m.mentor_id
         WHERE m.apprentice_id = ? AND m.status = 'pending' LIMIT 1`,
        [userId]
      ),
      // 0.8.7：我（作为师傅）收到的待审申请
      dbAll(
        `SELECT m.created_at, u.id AS uid, COALESCE(NULLIF(r.name, ''), u.username) AS name, r.realm_index, r.realm_level
         FROM mentorships m JOIN users u ON u.id = m.apprentice_id LEFT JOIN rankings r ON r.user_id = m.apprentice_id
         WHERE m.mentor_id = ? AND m.status = 'pending' ORDER BY m.created_at LIMIT 10`,
        [userId]
      ),
      // 0.8.7：今日传功状态（与 /api/mentor/teach 同用 teach_log UNIQUE(user_id,date) 的 UTC 日切口径）
      dbGet('SELECT apprentice_id FROM teach_log WHERE user_id = ? AND date = ? LIMIT 1', [userId, utcDateStr()]),
    ]);
"""

# ============================================================ E4c C2 my：响应扩展

E4C_OLD = """      cooldownUntil,
      rules: {
"""

E4C_NEW = """      cooldownUntil,
      // ── 0.8.7 申请-审批制扩展（契约 C2）──
      myPending: pendRow ? { mentorId: Number(pendRow.mentor_id), mentorName: String(pendRow.name || ''), since: Number(pendRow.created_at) || 0 } : null,
      pendingIncoming: (incRows || []).map((r) => ({ apprenticeId: Number(r.uid), name: String(r.name || ''), realmName: rn(r.realm_index), level: mentorLevelOf(r.realm_index, r.realm_level), since: Number(r.created_at) || 0 })),
      teachDone: !!teachRow,
      taughtApprenticeId: teachRow ? Number(teachRow.apprentice_id) : null,
      consts: { teachExpBase: TEACH_EXP_BASE, teachVirtue: TEACH_VIRTUE, applyTtlMs: MENTOR_APPLY_TTL_MS },
      rules: {
"""

# ============================================================ E5 C2 my：history 过滤改写

E5_OLD = """         WHERE (m.mentor_id = ? OR m.apprentice_id = ?) AND m.status != 'active'"""

E5_NEW = """         WHERE (m.mentor_id = ? OR m.apprentice_id = ?) AND m.status NOT IN ('pending', 'declined')"""

# ============================================================ E6 新端点 N1 decide + N2 cancel

E6_OLD = """// POST /api/mentor/graduate {apprenticeId?} — 出师：徒弟本人调用，或师傅指定徒弟。
"""

E6_NEW = """// 师傅处理拜师申请（0.8.7 新增 N1，POST，入参 {apprenticeId, action:'accept'|'decline'}）。
// 仅被申请的师傅本人可调（他人 400）；无 pending 409；过期（超 48h）惰性置 declined + 409。
// accept=申请门槛重验（师傅境界/等级差）+ 守卫式单语句 UPDATE pending→active（门下<3、双方非 7 天解除
// 冷却，并发双审批只一方 changes=1）+ 双方邮件；decline=置 declined（不进 7 天冷却）+ 申请人邮件。
app.post('/api/mentor/decide', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `mentor:bind:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const appId = Math.floor(asNum(req.body?.apprenticeId));
    const action = asStr(req.body?.action);
    if (!Number.isInteger(appId) || appId <= 0) return res.status(400).json({ error: '参数非法' });
    if (action !== 'accept' && action !== 'decline') return res.status(400).json({ error: 'action 须为 accept 或 decline' });
    const rel: any = await dbGet("SELECT id, mentor_id, apprentice_id, created_at FROM mentorships WHERE apprentice_id = ? AND status = 'pending' LIMIT 1", [appId]);
    if (!rel) return res.status(409).json({ error: '对方没有待处理的拜师申请' });
    if (Number(rel.mentor_id) !== userId) return res.status(400).json({ error: '只有被申请的师傅本人可以处理该申请' });
    if (mentorApplyExpired(rel.created_at, Date.now())) {
      await dbRun("UPDATE mentorships SET status = 'declined' WHERE id = ? AND status = 'pending'", [Number(rel.id)]);
      return res.status(409).json({ error: `申请已过期（超过 ${Math.round(MENTOR_APPLY_TTL_MS / 3600000)} 小时未处理），已自动作废` });
    }
    const [aU, mNameRow] = await Promise.all([
      dbGet("SELECT u.username, COALESCE(NULLIF(r.name, ''), u.username) AS name, r.realm_index, r.realm_level FROM users u LEFT JOIN rankings r ON r.user_id = u.id WHERE u.id = ?", [appId]),
      dbGet("SELECT COALESCE(NULLIF(r.name, ''), u.username) AS name FROM users u LEFT JOIN rankings r ON r.user_id = u.id WHERE u.id = ?", [userId]),
    ]);
    const aName = String(aU?.name || '').slice(0, 32);
    const mName = String(mNameRow?.name || '').slice(0, 32);
    if (action === 'decline') {
      const dn = await dbRun("UPDATE mentorships SET status = 'declined' WHERE id = ? AND status = 'pending'", [Number(rel.id)]);
      if (!dn.changes) return res.status(409).json({ error: '该申请已被处理，请刷新' });
      // declined 不进 7 天冷却（冷却只认 expired），申请人可立刻改投他人
      insertMail(appId, '拜师申请被婉拒',
        `很遗憾，「${mName}」婉拒了你的拜师申请。\\n\\n· 婉拒不进冷却，你现在就可以在师徒页签改投其他师傅\\n· 仙路广阔，总有投缘的师门`,
        'system', 0).catch((e: any) => console.error('mentor decide decline mail error:', e?.message || e));
      return res.json({ ok: true, apprentice: { id: appId, name: aName }, status: 'declined' });
    }
    // accept：申请门槛重验（境界/等级差——申请后 48h 内境界可能变动），失败给可读 409
    if (!aU || aU.realm_index == null) return res.status(409).json({ error: '对方角色档案缺失，无法收纳' });
    const myRank = await dbGet('SELECT realm_index, realm_level FROM rankings WHERE user_id = ?', [userId]);
    if (!myRank || !mentorRealmOk(myRank.realm_index)) return res.status(409).json({ error: '你的境界未达筑基期，尚不可收徒' });
    if (!mentorGapOk(mentorLevelOf(aU.realm_index, aU.realm_level), mentorLevelOf(myRank.realm_index, myRank.realm_level))) {
      return res.status(409).json({ error: `你的总等级须比对方高 ${MENTOR_LEVEL_GAP} 级（申请后条件已变化）` });
    }
    // 守卫式单语句 UPDATE：门下<3、双方非 7 天解除冷却，全部原子重验（并发双审批只一方 changes=1）
    const now = Date.now();
    const coolSince = now - MENTOR_EXPIRE_COOLDOWN_MS;
    const up = await dbRun(
      `UPDATE mentorships SET status = 'active'
       WHERE id = ? AND status = 'pending'
         AND (SELECT COUNT(*) FROM mentorships WHERE mentor_id = ? AND status = 'active') < ?
         AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))
         AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))`,
      [Number(rel.id), userId, MENTOR_MAX_APPRENTICES, coolSince, userId, userId, coolSince, appId, appId]
    );
    if (!up.changes) {
      // 失败逐项诊断（口径抄拜师失败诊断）
      const [cntRow, myCoolRow, tCoolRow] = await Promise.all([
        dbGet("SELECT COUNT(*) AS c FROM mentorships WHERE mentor_id = ? AND status = 'active'", [userId]),
        dbGet("SELECT 1 AS x FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?) LIMIT 1", [coolSince, userId, userId]),
        dbGet("SELECT 1 AS x FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?) LIMIT 1", [coolSince, appId, appId]),
      ]);
      let msg = '收纳未成，条件有变，请刷新重试';
      if (Number(cntRow?.c) >= MENTOR_MAX_APPRENTICES) msg = `门下弟子已满（${MENTOR_MAX_APPRENTICES}/${MENTOR_MAX_APPRENTICES}），无法再收`;
      else if (myCoolRow) msg = '你刚解除师徒关系，冷却中（7 天）';
      else if (tCoolRow) msg = '对方刚解除师徒关系，冷却中（7 天）';
      return res.status(409).json({ error: msg });
    }
    insertMail(appId, '拜师成功',
      `「${mName}」已收纳你为徒，师徒关系即刻生效。\\n\\n· 师徒同行（双方在线）时，你的服务端结算收益 +${Math.round((MENTOR_BONUS_MULT - 1) * 100)}%\\n· 师傅将抽成你收益的 ${MENTOR_TAX_RATE * 100}%（师傅入账）\\n· 修至金丹期后可在师徒页出师\\n\\n尊师重道，修行有道。`,
      'system', 0).catch((e: any) => console.error('mentor decide accept mail(a) error:', e?.message || e));
    insertMail(userId, '新徒入门',
      `你已收纳「${aName}」为徒。\\n\\n· 徒弟收益的 ${MENTOR_TAX_RATE * 100}%（修为/灵石）将自动奉上\\n· 师徒同行（双方在线）时，徒弟服务端结算收益 +${Math.round((MENTOR_BONUS_MULT - 1) * 100)}%\\n· 徒弟金丹期出师时：你将获得其拜师以来累计灵石收益 ${MENTOR_GRAD_RATE * 100}% 的出师回馈 + 7 天 ×${MENTOR_BUFF_MULT} 收益增益 + 称号「良师益友」`,
      'system', 0).catch((e: any) => console.error('mentor decide accept mail(m) error:', e?.message || e));
    res.json({ ok: true, apprentice: { id: appId, name: aName, realmIndex: aU.realm_index == null ? null : Number(aU.realm_index), realmLevel: aU.realm_level == null ? null : Number(aU.realm_level) }, status: 'active' });
  } catch (e: any) { console.error('mentor decide error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// POST /api/mentor/cancel — 徒弟撤回自己的待处理拜师申请（0.8.7 新增 N2）。
// 撤回=置 declined：不进 7 天冷却、部分唯一索引位随即释放，可立刻改投他人。
app.post('/api/mentor/cancel', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `mentor:bind:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const up = await dbRun("UPDATE mentorships SET status = 'declined' WHERE apprentice_id = ? AND status = 'pending'", [userId]);
    if (!up.changes) return res.status(409).json({ error: '没有待处理的拜师申请' });
    res.json({ ok: true });
  } catch (e: any) { console.error('mentor cancel error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// POST /api/mentor/graduate {apprenticeId?} — 出师：徒弟本人调用，或师傅指定徒弟。
"""

# ============================================================ E7 N3 search：SQL 加 apprentice_count

E7_OLD = """        `SELECT u.id, COALESCE(NULLIF(r.name, ''), u.username) AS name, r.realm_index, r.realm_level
         FROM users u LEFT JOIN rankings r ON r.user_id = u.id
"""

E7_NEW = """        `SELECT u.id, COALESCE(NULLIF(r.name, ''), u.username) AS name, r.realm_index, r.realm_level,
           (SELECT COUNT(*) FROM mentorships ms WHERE ms.mentor_id = u.id AND ms.status = 'active') AS apprentice_count
         FROM users u LEFT JOIN rankings r ON r.user_id = u.id
"""

# ============================================================ E8 N3 search：映射加 apprenticeCount/full

E8_OLD = """          eligible: r.realm_index != null && realmOk && gapOk,
          reason: r.realm_index == null ? '对方尚未踏入仙途（无角色存档）' : (!realmOk ? '境界未达筑基期' : (!gapOk ? `总等级须比你高 ${MENTOR_LEVEL_GAP} 级` : '')),
        };
"""

E8_NEW = """          apprenticeCount: Math.max(0, Math.floor(Number(r.apprentice_count) || 0)),
          full: Math.max(0, Math.floor(Number(r.apprentice_count) || 0)) >= MENTOR_MAX_APPRENTICES,
          eligible: r.realm_index != null && realmOk && gapOk,
          reason: r.realm_index == null ? '对方尚未踏入仙途（无角色存档）' : (!realmOk ? '境界未达筑基期' : (!gapOk ? `总等级须比你高 ${MENTOR_LEVEL_GAP} 级` : '')),
        };
"""

# ============================================================ E9 graduate 徒弟出师贺礼（每日 1 笔频控）

E9_OLD = """    grantTitleBySource(mentorId, 'mentor_grad').catch((e: any) => console.error('mentor grad title error:', e?.message || e));
    insertMail(apprenticeId, '出师',
      `恭喜道友修至金丹，今日出师，自立门户！\\n\\n师恩已报于传承之中：师傅获得了你拜师以来累计收益的 ${MENTOR_GRAD_RATE * 100}% 作为出师回馈。\\n\\n愿仙路漫漫，各自精进，他日江湖再见。`,
      'system', 0).catch((e: any) => console.error('mentor graduate mail(app) error:', e?.message || e));
"""

E9_NEW = """    grantTitleBySource(mentorId, 'mentor_grad').catch((e: any) => console.error('mentor grad title error:', e?.message || e));
    // 0.8.7 徒弟出师贺礼（《数值表-T7T8》T8-8）：floor(贺礼基数 × realmMultOf(徒弟))，见 [mentorcore] 常量区。
    // 频控=每徒弟每日限 1 笔（T8-9）：当日已有 completed 行（不含本次）→ 贺礼置 0，出师本身不受影响。
    // 发信失败仅日志不回滚出师（小额礼按金额分级缩小补偿面；师傅侧大额回馈的回滚保护维持原样）。
    let gift = mentorGradGift(await realmMultOf(apprenticeId));
    try {
      const dupGift: any = await dbGet(
        "SELECT COUNT(*) AS c FROM mentorships WHERE apprentice_id = ? AND status = 'completed' AND graduated_at IS NOT NULL AND graduated_at >= ? AND id != ?",
        [apprenticeId, utcDayStartMs(), Number(rel.id)]
      );
      if (Number(dupGift?.c) >= 1) gift = 0;
    } catch { /* 频控查询异常不影响出师 */ }
    insertMail(apprenticeId, '出师',
      `恭喜道友修至金丹，今日出师，自立门户！\\n\\n师恩已报于传承之中：师傅获得了你拜师以来累计收益的 ${MENTOR_GRAD_RATE * 100}% 作为出师回馈。\\n\\n${gift > 0 ? `另奉上出师贺礼 灵石 ×${gift}（每徒弟每日至多一份），点击下方领取。\\n\\n` : ''}愿仙路漫漫，各自精进，他日江湖再见。`,
      'system', gift).catch((e: any) => console.error('mentor graduate mail(app) error:', e?.message || e));
"""

EDITS = [
    ('E1a [mentorcore] 申请/贺礼常量',        E1A_OLD, E1A_NEW),
    ('E1b [mentorcore] 过期/贺礼纯函数',      E1B_OLD, E1B_NEW),
    ('E2  C1 INSERT pending + UNIQUE 兜底',   E2_OLD, E2_NEW),
    ('E3  C1 邮件改申请语境 + 响应',           E3_OLD, E3_NEW),
    ('E4a C2 my 惰性归档 + 查询扩展(上)',      E4A_OLD, E4A_NEW),
    ('E4b C2 my 查询扩展(下)',               E4B_OLD, E4B_NEW),
    ('E4c C2 my 响应扩展',                   E4C_OLD, E4C_NEW),
    ('E5  C2 my history 过滤改写',            E5_OLD, E5_NEW),
    ('E6  N1 decide + N2 cancel 新端点',      E6_OLD, E6_NEW),
    ('E7  N3 search SQL 加弟子数',            E7_OLD, E7_NEW),
    ('E8  N3 search 映射加 apprenticeCount/full', E8_OLD, E8_NEW),
    ('E9  graduate 徒弟出师贺礼 + 频控',       E9_OLD, E9_NEW),
]

# 链序依赖证明（取自前环产物特征）
REQUIRES = [
    ("isValidSavePayload", 2, "p0_save 必须先跑过"),
    ("Object.create(null)", 1, "p2b_hardening 必须先跑过"),
    ("const TEA_MAX_BETS = 3;", 1, "fun086 必须先跑过"),
    ("SELECT ?, ?, 'active', ?", 1, "拜师守卫语句基线（v286 原貌）——T8 只改 status 字面量"),
    ("const MENTOR_EXPIRE_COOLDOWN_MS", 1, "[mentorcore] 常量区基线"),
    ("INSERT OR IGNORE INTO teach_log", 1, "teach_log 频控基线（贺礼频控同口径 UTC 日切）"),
]


def fail(msg):
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

    # 1) 链序依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 2) 幂等
    if "/api/mentor/decide" in src or "MENTOR_APPLY_TTL_MS" in src:
        fail("source looks already patched（已存在 /api/mentor/decide / MENTOR_APPLY_TTL_MS）")

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
    base403 = src.count("res.status(403)")
    gates = [
        # ---- 新端点 ----
        ('N1 decide 端点',                  "/api/mentor/decide", 1, None),
        ('N2 cancel 端点',                  "'/api/mentor/cancel'", 1, None),
        ('mentor POST 端点 5→7',            "app.post('/api/mentor/", 7, None),
        ('mentor GET 端点恒 3',             "app.get('/api/mentor/", 3, None),
        # ---- C1 改写证据 ----
        ("C1 INSERT 'pending'",             "SELECT ?, ?, 'pending', ?", 1, None),
        ("C1 旧 INSERT 'active' 清零",       "SELECT ?, ?, 'active', ?", 0, None),
        ('C1 重复申请 UNIQUE 兜底',           "你已有一份待处理的拜师申请", 1, None),
        ('C1 响应带 status pending',         "res.json({ ok: true, status: 'pending', mentor:", 1, None),
        ('C1 旧即时生效邮件清零',             '你已正式拜', 0, None),
        ('C1 邮件指向游戏内页签',             '游戏内「仙务 → 师徒」页签可收纳', 1, None),
        # ---- 守卫语句逐字保留（基线碎片恒在）----
        ('守卫 门下<3 子查询（C1+decide）',   "(SELECT COUNT(*) FROM mentorships WHERE mentor_id = ? AND status = 'active') < ?", 2, None),
        ('守卫 徒弟无师傅子查询',             "AND NOT EXISTS (SELECT 1 FROM mentorships WHERE apprentice_id = ? AND status = 'active')", 1, None),
        ('守卫 冷却子查询（双份）',           "AND NOT EXISTS (SELECT 1 FROM mentorships WHERE status = 'expired' AND ended_at IS NOT NULL AND ended_at > ? AND (mentor_id = ? OR apprentice_id = ?))", 4, None),
        # ---- N1 decide ----
        ('N1 仅师傅可调 400',                '只有被申请的师傅本人可以处理该申请', 1, None),
        ('N1 无 pending 409',               '对方没有待处理的拜师申请', 1, None),
        ('N1 过期判定走纯函数',               'if (mentorApplyExpired(rel.created_at, Date.now()))', 1, None),
        ('N1 accept 守卫式 UPDATE',          "UPDATE mentorships SET status = 'active'\n       WHERE id = ? AND status = 'pending'", 1, None),
        ('N1 accept 门下<3 重验',            "AND (SELECT COUNT(*) FROM mentorships WHERE mentor_id = ? AND status = 'active') < ?", 1, None),
        ('N1 并发双审批逐项诊断',             '收纳未成，条件有变，请刷新重试', 1, None),
        ('N1 双方邮件（拜师成功）',           '「${mName}」已收纳你为徒', 1, None),
        ('N1 双方邮件（新徒入门）',           '你已收纳「${aName}」为徒', 1, None),
        ('N1 decline 邮件',                 '拜师申请被婉拒', 1, None),
        # ---- N2 cancel ----
        ('N2 撤回 UPDATE',                  "UPDATE mentorships SET status = 'declined' WHERE apprentice_id = ? AND status = 'pending'", 1, None),
        ('N2 无 pending 409',               "error: '没有待处理的拜师申请'", 1, None),
        # ---- C2 my ----
        ('C2 惰性归档 UPDATE',               "UPDATE mentorships SET status = 'declined' WHERE status = 'pending' AND created_at < ?", 1, None),
        ('C2 myPending 下发',               'myPending: pendRow ?', 1, None),
        ('C2 pendingIncoming 下发',          'pendingIncoming: (incRows || []).map', 1, None),
        ('C2 teachDone 下发',                'teachDone: !!teachRow,', 1, None),
        ('C2 taughtApprenticeId 下发',       'taughtApprenticeId: teachRow ? Number(teachRow.apprentice_id) : null,', 1, None),
        ('C2 consts 下发',                  'consts: { teachExpBase: TEACH_EXP_BASE, teachVirtue: TEACH_VIRTUE, applyTtlMs: MENTOR_APPLY_TTL_MS },', 1, None),
        ('C2 history 过滤改写',              "AND m.status NOT IN ('pending', 'declined')", 1, None),
        ('C2 旧 history 过滤清零',            "AND m.status != 'active'", 0, None),
        # ---- N3 search ----
        ('N3 弟子数子查询',                  "SELECT COUNT(*) FROM mentorships ms WHERE ms.mentor_id = u.id AND ms.status = 'active') AS apprentice_count", 1, None),
        ('N3 apprenticeCount 下发',          'apprenticeCount: Math.max(0, Math.floor(Number(r.apprentice_count) || 0)),', 1, None),
        ('N3 full 下发',                    'full: Math.max(0, Math.floor(Number(r.apprentice_count) || 0)) >= MENTOR_MAX_APPRENTICES,', 1, None),
        # ---- graduate 贺礼 ----
        ('贺礼纯函数',                      'function mentorGradGift(realmMult: unknown): number {', 1, None),
        ('贺礼计算调用',                    'let gift = mentorGradGift(await realmMultOf(apprenticeId));', 1, None),
        ('贺礼每日 1 笔频控',                'AND graduated_at >= ? AND id != ?', 1, None),
        ('贺礼置 0 分支',                   'if (Number(dupGift?.c) >= 1) gift = 0;', 1, None),
        ('贺礼入邮件 attached_lingshi',      "'system', gift).catch((e: any) => console.error('mentor graduate mail(app) error:'", 1, None),
        # ---- 常量 ----
        ('TTL 常量定义',                    'const MENTOR_APPLY_TTL_MS = 48 * 3600 * 1000;', 1, None),
        ('贺礼基数常量定义',                 'const MENTOR_GRAD_GIFT_BASE = 3000;', 1, None),
        ('MENTOR_APPLY_TTL_MS 引用共 6',     'MENTOR_APPLY_TTL_MS', 6, None),
        ('MENTOR_GRAD_GIFT_BASE 引用共 2',   'MENTOR_GRAD_GIFT_BASE', 2, None),
        # ---- 基线未被破坏 ----
        ('基线 部分唯一索引未动',             "CREATE UNIQUE INDEX IF NOT EXISTS idx_mentorships_apprentice_active ON mentorships(apprentice_id) WHERE status IN ('pending','active')", 1, None),
        ('基线 teach_log 未动',              "INSERT OR IGNORE INTO teach_log (user_id, apprentice_id, date)", 1, None),
        ('基线 弟子上限 3 未动',             'const MENTOR_MAX_APPRENTICES = 3;', 1, None),
        ('基线 传功常量未动',                'const TEACH_EXP_BASE = 30000;', 1, None),
        ('基线 请安常量未动',                'const GREET_STONES_BASE = 200;', 1, None),
        ('基线 出师回馈 30% 未动',            'const MENTOR_GRAD_RATE = 0.30;', 1, None),
        ('基线 解除冷却 7 天未动',            'const MENTOR_EXPIRE_COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000;', 1, None),
        ('基线 搜索 LIKE 转义未动',          "mentorLikeEscape(q)", 1, None),
        # ---- 403 语义红线：本补丁零新增 403 ----
        ('403 计数与基线逐字相等',            'res.status(403)', None, 'same'),
    ]
    ok = True
    for g in gates:
        label, needle, exp = g[0], g[1], g[2]
        op = g[3] if len(g) > 3 else None
        if op == 'same':
            exp = base403
            shown = 'expect==base(%d)' % exp
        else:
            shown = 'expect==%d' % exp
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-30s actual=%d %s" % ("OK" if good else "FAIL", label, act, shown))
    if not ok:
        fail("门禁未全过")

    # 6) 语义顺序断言：C1 端点内 status='pending' 的 INSERT 必须早于两封邮件（先落库后发信）
    i = out.find("app.post('/api/mentor/apprentice'")
    j = out.find("app.post(", i + 30)
    seg = out[i:j if j > 0 else len(out)]
    p1 = seg.find("SELECT ?, ?, 'pending', ?")
    p2 = seg.find("insertMail(targetId, '拜师申请'")
    if p1 < 0 or p2 < 0 or p1 > p2:
        fail("顺序契约破坏：C1 的 pending INSERT(%d) 必须早于邮件(%d)" % (p1, p2))
    # decide 端点内：accept 的守卫 UPDATE 必须早于两封收纳邮件
    i = out.find("app.post('/api/mentor/decide'")
    j = out.find("app.post(", i + 30)
    seg = out[i:j if j > 0 else len(out)]
    p1 = seg.find("UPDATE mentorships SET status = 'active'")
    p2 = seg.find("insertMail(appId, '拜师成功'")
    if p1 < 0 or p2 < 0 or p1 > p2:
        fail("顺序契约破坏：decide accept 的守卫 UPDATE(%d) 必须早于邮件(%d)" % (p1, p2))
    # graduate 端点内：贺礼频控 SELECT 必须早于出师邮件
    i = out.find("app.post('/api/mentor/graduate'")
    j = out.find("app.post(", i + 30)
    seg = out[i:j if j > 0 else len(out)]
    p1 = seg.find("SELECT COUNT(*) AS c FROM mentorships WHERE apprentice_id = ? AND status = 'completed'")
    p2 = seg.find("insertMail(apprenticeId, '出师'")
    p3 = seg.find("UPDATE mentorships SET status = 'completed'")
    if p1 < 0 or p2 < 0 or not (p3 < p1 < p2):
        fail("顺序契约破坏：graduate 必须 出师UPDATE(%d) → 频控SELECT(%d) → 贺礼邮件(%d)" % (p3, p1, p2))
    print("  [OK] 顺序契约：C1 先落 pending 行后发信；decide accept 先守卫 UPDATE 后发信；graduate 先出师后频控后贺礼")

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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".t8mentor-", suffix=".tmp")
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
