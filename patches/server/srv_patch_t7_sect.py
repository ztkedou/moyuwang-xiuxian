# -*- coding: utf-8 -*-
r"""
srv_patch_t7_sect.py -- 0.8.7 T7 仙盟重构 · 服务端补丁（SRV_CHAIN 第 9 环 `t7_sect`）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  不提供 `--out`：`localtest/chain_build.py` 会把上一环产物复制成私有工作副本
  再让本补丁就地改。

覆盖范围（设计案《T7-仙盟重构》§4/§6 + 契约 §4.3 C1/C2/N1~N4 + 数值表-T7T8）
--------------------------------------------------------------------------
  S1  常量区：SECT_APPLY_TTL_MS=72h、SECT_DONATE_CONTRIB_RATE=0.02、
      SECT_CONTRIB_CLAMP_PER_MIN=20（=1200/时）、SECT_CONTRIB_CLAMP_BASE=5000
  S2  建表区：sects 建表定义补 join_mode 列（新库双写一致）+ sect_applications 表
      （部分唯一索引 idx_sect_app_user_pending 挡一人多 pending，先例
      idx_mentorships_apprentice_active）+ PRAGMA 守卫 ALTER（存量库加列，先例 saves :139）
  S3  403 改码 13 处（Xc() 把 403 当会话失效强制登出，铁律①）：
      - 对象形式 2 处：sectGfAdvance RANK_TOO_LOW/REALM_TOO_LOW（:9501/:9504）403→400
      - res 形式 11 处：join 冷却 403→409(+cooldownLeftMs)；kick×4/role×2/transfer×2/
        disband/notice 403→400（notice 同步放宽到长老，§3 权限矩阵）
      门禁双计数：res.status(403) 22→11、status: 403 2→0
  S4  C1 list：keyword 检索（mentorSearchName/mentorLikeEscape 同款 1..16 字净化 +
      LIKE \ % _ 转义 ESCAPE '\'）+ 契约响应 rows/page/hasMore/mine(+joinMode 行字段)；
      list/pages/total 与行内 leader/member_count 双发兼容旧伴生页（src/index-v26e 消费 .list）
  S5  C2 join：join_mode 分裂——auto 现状不变；apply 写 pending 申请（部分唯一索引挡
      重复→409）；auto 入盟成功顺手撤本人残留 pending
  S6  N1 mine 扩展：+joinMode/myApplication/applications(仅盟主长老)/cooldownUntil/
      applyTtlMs；无盟 {sect:null} 分支同步扩展（面板无盟视图渲染申请卡/冷却卡）
  S7  N2 applications/cancel、N3 applications/decide（先占位→守卫式插成员→失败回滚
      pending+409 逐项诊断，抄 mentor 拜师 :6510-6523 口径；成功/拒绝邮件通知，
      抄 :6527-6532 先例）、N4 settings（notice≤200=盟主+长老；joinMode=仅盟主）
  S8  捐献回馈 P1：floor(捐献额×2%) 写个人 sectContribution（updatePlayerSave 安全通道，
      失败仅日志不回滚捐献）；日上限=SECT_DONATE_DAILY_CAP×2%=1000（公式值不设新常量）
  S9  G7 硬化：settleSaveEconV2 链尾追加 sectContribution 差值钳
      dContrib ≤ ceil(realMins×20/分)+5000（写法抄 :1736-1739 计数器窗口钳）
  S10 建宗端点注释顺手修正 5000→50000（设计案 §10-5，不改行为）；
      0.8.8 item15 同步把注释口径改为「境界≥元婴 + 1000000 灵石」
  S11 建宗门槛（0.8.8 item15）：SECT_CREATE_COST 50000→1000000、
      SECT_CREATE_MIN_REALM 1→3（元婴期，REALM_ORDER_FOR_RANKING 下标 3）、
      守卫文案「筑基期」→「元婴期」

★ 数值定档 =《数值表-T7T8》：T7-6 申请有效期 72h / T7-7 贡献率 2% / T7-8 回馈日上限
  1000（公式值）/ T7-9 差值钳 1200/时+5000（自纠草稿锚 60/时+200：会误伤职衔晋升单笔 5000）。

★ 门禁计数清单（供 check_srv_087.py / dryrun_087.py 接线人落表）
--------------------------------------------------------------------------
  - res.status(403)          22 → 11（基线 22，改后剩 GM/封禁/会话/称号/秘境 11 处）
  - status: 403              2 → 0
  - CREATE TABLE IF NOT EXISTS sect_applications   == 1
  - idx_sect_app_user_pending                      == 1
  - join_mode TEXT NOT NULL DEFAULT 'auto'         == 2（PRAGMA ALTER + 建表定义）
  - sectExpireStaleApplications                    == 4（定义1 + list/mine无盟/decide 调用3）
  - app.post('/api/sect/applications/cancel'       == 1
  - app.post('/api/sect/applications/decide'       == 1
  - app.post('/api/sect/settings'                  == 1
  - SECT_DONATE_CONTRIB_RATE                       == 2（定义+使用）
  - E2:sectContrib                                 == 2（neg 钳 + 超限钳）
  - 24h 冷却三写入点 upsert 串恒 3（leave/kick/disband，零改动断言）
  - SECT_CREATE_COST = 1000000;                    == 1（0.8.8 item15，旧值 50000 归零）
  - SECT_CREATE_MIN_REALM = 3;                     == 1（0.8.8 item15，旧值 1 归零）
  - 境界需达到元婴期方可开宗立派                    == 1（旧文案「筑基期」归零）
"""
import argparse
import io
import os
import sys
import tempfile

# ============================================================ S1 常量区

S1_OLD = r"const SECT_LEAVE_COOLDOWN_MS = 24 * 3600 * 1000; // 退宗/被踢/解散后 24h 冷却（服务端表约束）"

S1_NEW = S1_OLD + r"""
// 0.8.7 T7：申请审批流与捐献回馈（数值定档=《数值表-T7T8》T7-6/7/8/9，调参只动本区）
const SECT_APPLY_TTL_MS = 72 * 3600 * 1000; // 申请有效期 72h（过期由读取路径惰性置 expired）
const SECT_DONATE_CONTRIB_RATE = 0.02;      // 捐献回馈贡献率 2%；日上限=SECT_DONATE_DAILY_CAP×rate=1000（公式值不设新常量）
const SECT_CONTRIB_CLAMP_PER_MIN = 20;      // E2:sectContrib 差值钳增速：20/分（=1200/时，任务阁稳态）
const SECT_CONTRIB_CLAMP_BASE = 5000;       // E2:sectContrib 兜底（原生职衔晋升单笔 5000 恰容）"""

# ============================================================ S2a sects 建表定义补列（新库双写一致）

S2A_OLD = r"""    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    disbanded_at DATETIME
  )`);"""

S2A_NEW = r"""    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    disbanded_at DATETIME,
    join_mode TEXT NOT NULL DEFAULT 'auto'
  )`);"""

# ============================================================ S2b 申请表 + 索引 + PRAGMA 守卫 + 惰性过期

S2B_OLD = r"""    PRIMARY KEY (user_id, gongfa_id),
    FOREIGN KEY (user_id) REFERENCES users (id)
  )`);
});"""

S2B_NEW = r"""    PRIMARY KEY (user_id, gongfa_id),
    FOREIGN KEY (user_id) REFERENCES users (id)
  )`);
  // 0.8.7 T7：盟申请审批流。一人一 pending 由部分唯一索引兜底（先例 idx_mentorships_apprentice_active），
  // 并发防重靠主键与部分唯一索引，不靠先查后写（设计案 §2-4）
  db.run(`CREATE TABLE IF NOT EXISTS sect_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sect_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
      CHECK (status IN ('pending','approved','rejected','cancelled','expired')),
    created_at INTEGER NOT NULL,
    handled_at INTEGER,
    handled_by INTEGER
  )`);
  db.run(`CREATE UNIQUE INDEX IF NOT EXISTS idx_sect_app_user_pending ON sect_applications(user_id) WHERE status = 'pending'`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_sect_app_sect ON sect_applications(sect_id, status, created_at)`);
  // 存量库加列守卫（先例 saves :139 PRAGMA table_info）：老库 sects 无 join_mode 时补列（与上方建表定义双写一致）
  db.all("PRAGMA table_info(sects)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'join_mode')) {
      db.exec("ALTER TABLE sects ADD COLUMN join_mode TEXT NOT NULL DEFAULT 'auto'");
    }
  });
});

// 0.8.7 T7：过期申请惰性置 expired（读取路径调用；TTL=SECT_APPLY_TTL_MS=72h。
// 自吞异常绝不影响业务主路径，与 tickSectTasks 同纪律）
async function sectExpireStaleApplications(): Promise<void> {
  try {
    await dbRun("UPDATE sect_applications SET status = 'expired' WHERE status = 'pending' AND created_at + ? <= ?", [SECT_APPLY_TTL_MS, Date.now()]);
  } catch (e: any) {
    console.error('sect applications expire error:', e?.message || e);
  }
}"""

# ============================================================ S3 G7 差值钳（settleSaveEconV2 链尾追加）

S3_OLD = r"    // 5) 物品数量轻钳制（NaN/负→1，单组上限 1e6；不做总量钳制防误伤囤草党）"

S3_NEW = r"""    // 0.8.7 T7 G7 硬化：sectContribution 差值钳（堵「客户端权威可刷」，写法抄上方计数器窗口钳）。
    // 数值定档《数值表-T7T8》T7-9：dContrib ≤ ceil(realMins×20/分)+5000——
    // 兜底 5000=原生职衔晋升单笔恰好放行（bundle 常量实测），增速 1200/时=任务阁稳态贡献（6k/日÷5h）。
    // 超限钳回并记 clamped，计数器本体（负值）一并归零防负刷。
    {
      const oContrib = Math.floor(Number(op.sectContribution) || 0);
      const nContribRaw = Math.floor(Number(np.sectContribution) || 0);
      const nContrib = Math.max(0, nContribRaw);
      if (!Number.isFinite(nContribRaw) || nContribRaw < 0) { np.sectContribution = 0; clamped.push('E2:sectContrib:neg'); }
      else {
        const dContrib = e2Delta(oContrib, nContrib);
        const cContrib = Math.ceil(realMins * SECT_CONTRIB_CLAMP_PER_MIN) + SECT_CONTRIB_CLAMP_BASE;
        if (dContrib > cContrib) {
          np.sectContribution = oContrib + cContrib;
          clamped.push('E2:sectContrib' + dContrib + '>' + cContrib);
        }
      }
    }

    // 5) 物品数量轻钳制（NaN/负→1，单组上限 1e6；不做总量钳制防误伤囤草党）"""

# ============================================================ S4 403 改码（对象形式 2 处：sectGfAdvance）

S4A_OLD = r"return { status: 403, body: { error: '\u804c\u8854\u4e0d\u8db3\uff0c\u9700\u8fbe\u5230' + def.rank, code: 'RANK_TOO_LOW' } };"
S4A_NEW = r"return { status: 400, body: { error: '\u804c\u8854\u4e0d\u8db3\uff0c\u9700\u8fbe\u5230' + def.rank, code: 'RANK_TOO_LOW' } };"

S4B_OLD = r"return { status: 403, body: { error: '\u5883\u754c\u4e0d\u8db3\uff0c\u9700\u8fbe\u5230' + def.realm, code: 'REALM_TOO_LOW' } };"
S4B_NEW = r"return { status: 400, body: { error: '\u5883\u754c\u4e0d\u8db3\uff0c\u9700\u8fbe\u5230' + def.realm, code: 'REALM_TOO_LOW' } };"

# ---- S4c join 冷却 403→409（保留 until + 补 cooldownLeftMs）----

S4C_OLD = r"""        return res.status(403).json({
          error: '退宗冷却中，24 小时后方可加入新宗门', code: 'COOLDOWN_UNTIL',
          until: new Date(untilMs).toISOString(),
        });"""

S4C_NEW = r"""        return res.status(409).json({
          error: '退宗冷却中，24 小时后方可加入新宗门', code: 'COOLDOWN_UNTIL',
          until: new Date(untilMs).toISOString(),
          cooldownLeftMs: Math.max(0, untilMs - Date.now()),
        });"""

# ---- S4d~S4g kick 四处 ----

S4D_OLD = r"    if (!actor || (actor.role !== 'leader' && actor.role !== 'officer')) return res.status(403).json({ error: '无权限' });"
S4D_NEW = r"    if (!actor || (actor.role !== 'leader' && actor.role !== 'officer')) return res.status(400).json({ error: '无权限' });"

S4E_OLD = r"    if (!target || target.sect_id !== actor.sect_id) return res.status(403).json({ error: '目标不在本宗', code: 'NOT_SAME_SECT' });"
S4E_NEW = r"    if (!target || target.sect_id !== actor.sect_id) return res.status(400).json({ error: '目标不在本宗', code: 'NOT_SAME_SECT' });"

S4F_OLD = r"    if (target.role === 'leader') return res.status(403).json({ error: '不能移除宗主' });"
S4F_NEW = r"    if (target.role === 'leader') return res.status(400).json({ error: '不能移除宗主' });"

S4G_OLD = r"    if (actor.role === 'officer' && target.role !== 'member') return res.status(403).json({ error: '长老只能移除普通成员' });"
S4G_NEW = r"    if (actor.role === 'officer' && target.role !== 'member') return res.status(400).json({ error: '长老只能移除普通成员' });"

# ---- S4h role 两处（任免/目标不在本宗，文案相同故整块做锚）----

S4H_OLD = r"""    if (!actor || actor.role !== 'leader') return res.status(403).json({ error: '仅宗主可任免职位' });
    if (targetId === req.user.id) return res.status(400).json({ error: '宗主职位不可变更，请使用转让宗主' });
    const target = await sectMemberOf(targetId);
    if (!target || target.sect_id !== actor.sect_id) return res.status(403).json({ error: '目标不在本宗' });"""

S4H_NEW = r"""    if (!actor || actor.role !== 'leader') return res.status(400).json({ error: '仅宗主可任免职位' });
    if (targetId === req.user.id) return res.status(400).json({ error: '宗主职位不可变更，请使用转让宗主' });
    const target = await sectMemberOf(targetId);
    if (!target || target.sect_id !== actor.sect_id) return res.status(400).json({ error: '目标不在本宗' });"""

# ---- S4i transfer 两处 ----

S4I_OLD = r"""    if (!actor || actor.role !== 'leader') return res.status(403).json({ error: '仅宗主可转让宗主之位' });
    if (targetId === req.user.id) return res.status(400).json({ error: '不能转让给自己' });
    const target = await sectMemberOf(targetId);
    if (!target || target.sect_id !== actor.sect_id) return res.status(403).json({ error: '目标不在本宗' });"""

S4I_NEW = r"""    if (!actor || actor.role !== 'leader') return res.status(400).json({ error: '仅宗主可转让宗主之位' });
    if (targetId === req.user.id) return res.status(400).json({ error: '不能转让给自己' });
    const target = await sectMemberOf(targetId);
    if (!target || target.sect_id !== actor.sect_id) return res.status(400).json({ error: '目标不在本宗' });"""

# ---- S4j disband ----

S4J_OLD = r"    if (!actor || actor.role !== 'leader') return res.status(403).json({ error: '仅宗主可解散宗门' });"
S4J_NEW = r"    if (!actor || actor.role !== 'leader') return res.status(400).json({ error: '仅宗主可解散宗门' });"

# ---- S4k notice：改码 + 权限放宽到长老（§3 矩阵「编辑公告：盟主✔ 长老✔」）----

S4K_OLD = r"    if (!actor || actor.role !== 'leader') return res.status(403).json({ error: '仅宗主可编辑公告' });"
S4K_NEW = r"    if (!actor || (actor.role !== 'leader' && actor.role !== 'officer')) return res.status(400).json({ error: '\u4ec5\u76df\u4e3b\u6216\u957f\u8001\u53ef\u7f16\u8f91\u516c\u544a' });"

# ============================================================ S5 C1 list：检索 + 契约响应（整块替换）

S5_OLD = r"""// 宗门列表（分页）：等级降序→资金降序；宗主名/人数实时子查询
app.get('/api/sect/list', authenticateToken, sectReadLimit, async (req: any, res: any) => {
  try {
    const page = Math.max(1, Math.floor(Number(req.query.page)) || 1);
    const totalRow: any = await dbGet('SELECT COUNT(*) AS c FROM sects WHERE disbanded_at IS NULL');
    const total = Number(totalRow?.c) || 0;
    const pages = Math.max(1, Math.ceil(total / SECT_LIST_PAGE_SIZE));
    const rows: any[] = await dbAll(
      `SELECT s.id, s.name, s.level, s.funds, lu.username AS leader,
              (SELECT COUNT(*) FROM sect_members m WHERE m.sect_id = s.id) AS member_count
       FROM sects s LEFT JOIN users lu ON lu.id = s.leader_id
       WHERE s.disbanded_at IS NULL
       ORDER BY s.level DESC, s.funds DESC, s.id ASC
       LIMIT ? OFFSET ?`,
      [SECT_LIST_PAGE_SIZE, (Math.min(page, pages) - 1) * SECT_LIST_PAGE_SIZE]
    );
    res.json({ list: rows, page: Math.min(page, pages), pages, total });
  } catch (e: any) {
    console.error('sect list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});"""

S5_NEW = r"""// 宗门列表（分页+检索，0.8.7 T7）：keyword 走 mentorSearchName/mentorLikeEscape 同款净化
//（trim 后 1..16 字，LIKE \ % _ 前缀 \ 转义 + ESCAPE '\'，防通配注入）；排序维持等级→资金→id，分页 10/页不变。
// 响应=契约 §4.3 C1 {rows:[{id,name,level,funds,memberCount,leaderName,joinMode}],page,hasMore,mine}；
// 兼容旧伴生页（src/index-v26e 消费 list/leader/member_count）：list/pages/total 与行内旧字段双发。
// mine={sectId,myRole,pendingSectId}：「我的盟」标记与「已申请」置灰取全局一份，不在列表行重复。
app.get('/api/sect/list', authenticateToken, sectReadLimit, async (req: any, res: any) => {
  try {
    await sectExpireStaleApplications();
    const page = Math.max(1, Math.floor(Number(req.query.page)) || 1);
    let kw: string | null = null;
    const kwRaw = req.query.keyword;
    if (kwRaw !== undefined && kwRaw !== null && String(kwRaw).trim() !== '') {
      const n = String(kwRaw).trim();
      if (n.length < 1 || n.length > 16) return res.status(400).json({ error: '\u5173\u952e\u8bcd\u9700 1-16 \u4e2a\u5b57', code: 'BAD_KEYWORD' });
      kw = mentorLikeEscape(n);
    }
    const whereSql = kw ? "WHERE s.disbanded_at IS NULL AND s.name LIKE ? ESCAPE '\\'" : 'WHERE s.disbanded_at IS NULL';
    const baseParams: any[] = kw ? ['%' + kw + '%'] : [];
    const totalRow: any = await dbGet(`SELECT COUNT(*) AS c FROM sects s ${whereSql}`, baseParams);
    const total = Number(totalRow?.c) || 0;
    const rows: any[] = await dbAll(
      `SELECT s.id, s.name, s.level, s.funds, s.join_mode, lu.username AS leader,
              (SELECT COUNT(*) FROM sect_members m WHERE m.sect_id = s.id) AS member_count
       FROM sects s LEFT JOIN users lu ON lu.id = s.leader_id
       ${whereSql}
       ORDER BY s.level DESC, s.funds DESC, s.id ASC
       LIMIT ? OFFSET ?`,
      [...baseParams, SECT_LIST_PAGE_SIZE + 1, (page - 1) * SECT_LIST_PAGE_SIZE]
    );
    const hasMore = rows.length > SECT_LIST_PAGE_SIZE;
    const list = (hasMore ? rows.slice(0, SECT_LIST_PAGE_SIZE) : rows).map((r: any) => ({
      id: Number(r.id), name: String(r.name || ''), level: Number(r.level) || 1,
      funds: Number(r.funds) || 0, memberCount: Number(r.member_count) || 0,
      member_count: Number(r.member_count) || 0, leaderName: String(r.leader || ''), leader: String(r.leader || ''),
      joinMode: String(r.join_mode || 'auto') === 'apply' ? 'apply' : 'auto',
    }));
    const member = await sectMemberOf(req.user.id);
    const myApp: any = await dbGet("SELECT sect_id FROM sect_applications WHERE user_id = ? AND status = 'pending' LIMIT 1", [req.user.id]);
    res.json({
      rows: list, list, page, hasMore,
      pages: Math.max(1, Math.ceil(total / SECT_LIST_PAGE_SIZE)), total,
      mine: {
        sectId: member ? member.sect_id : null,
        myRole: member ? member.role : null,
        pendingSectId: myApp ? Number(myApp.sect_id) : null,
      },
    });
  } catch (e: any) {
    console.error('sect list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});"""

# ============================================================ S6 N1 mine 扩展

# ---- S6a 无盟分支（{sect:null} 同步扩展，面板无盟视图渲染申请卡/冷却卡）----

S6A_OLD = r"    if (!member) return res.json({ sect: null });"

S6A_NEW = r"""    if (!member) {
      // 0.8.7 T7 扩展（N1 无盟视图）：myApplication（我的 pending 申请）+ cooldownUntil（退盟冷却截止）。
      await sectExpireStaleApplications();
      const app0: any = await dbGet(
        "SELECT a.id, a.sect_id, a.created_at, s.name AS sect_name FROM sect_applications a LEFT JOIN sects s ON s.id = a.sect_id WHERE a.user_id = ? AND a.status = 'pending' LIMIT 1",
        [req.user.id]
      );
      const cd0: any = await dbGet('SELECT cooldown_until FROM sect_cooldowns WHERE user_id = ?', [req.user.id]);
      const cdMs0 = cd0 ? Date.parse(String(cd0.cooldown_until || '')) : NaN;
      const cdUntil0 = Number.isFinite(cdMs0) && cdMs0 > Date.now() ? new Date(cdMs0).toISOString() : null;
      return res.json({
        sect: null,
        joinMode: null,
        myApplication: app0 ? {
          id: Number(app0.id), sectId: Number(app0.sect_id), sectName: String(app0.sect_name || ''),
          createdAt: Number(app0.created_at) || 0,
          expiresAt: (Number(app0.created_at) || 0) + SECT_APPLY_TTL_MS,
        } : null,
        applications: [],
        cooldownUntil: cdUntil0,
        applyTtlMs: SECT_APPLY_TTL_MS,
      });
    }"""

# ---- S6b 有盟分支（扩展查询 + 响应加根级字段）----

S6B_OLD = r"""    const level = Number(sect.level) || 1;
    res.json({
      sect: {
        id: sect.id, name: sect.name, level, funds: Number(sect.funds) || 0,
        notice: String(sect.notice || ''), memberCount: members.length,
        memberCap: SECT_MEMBER_CAP(level), createdAt: sect.created_at ?? null,
      },
      myRole: member.role,
      members,
      tasks,
      welfare: {
        salary: { amount: level * SECT_SALARY_PER_LEVEL, claimed: claimedKinds.has('salary') },
        pill: { unlocked: level >= SECT_PILL_MIN_LEVEL, claimed: claimedKinds.has('pill'), name: SECT_PILL_NAME },
      },
    });"""

S6B_NEW = r"""    const level = Number(sect.level) || 1;
    // 0.8.7 T7 扩展（N1 有盟视图）：joinMode / applications（仅盟主长老可见，成员得空数组）/
    // cooldownUntil（我方退盟冷却截止）/ applyTtlMs。在盟时 myApplication 恒 null
    //（join 直进成功会撤残留申请、审批入盟时申请行已 approved，无 pending 残留）。
    const isMgr = member.role === 'leader' || member.role === 'officer';
    const cdRow: any = await dbGet('SELECT cooldown_until FROM sect_cooldowns WHERE user_id = ?', [req.user.id]);
    const cdMs = cdRow ? Date.parse(String(cdRow.cooldown_until || '')) : NaN;
    const cooldownUntil = Number.isFinite(cdMs) && cdMs > Date.now() ? new Date(cdMs).toISOString() : null;
    const apps: any[] = isMgr ? await dbAll(
      `SELECT a.id, a.user_id, a.created_at,
              COALESCE(NULLIF(r.name, ''), u.username) AS name,
              r.realm_index, r.realm_level, r.combat_power
       FROM sect_applications a
       LEFT JOIN users u ON u.id = a.user_id
       LEFT JOIN rankings r ON r.user_id = a.user_id
       WHERE a.sect_id = ? AND a.status = 'pending'
       ORDER BY a.created_at ASC
       LIMIT 50`,
      [member.sect_id]
    ) : [];
    const joinModeNow = String(sect.join_mode || 'auto') === 'apply' ? 'apply' : 'auto';
    res.json({
      sect: {
        id: sect.id, name: sect.name, level, funds: Number(sect.funds) || 0,
        notice: String(sect.notice || ''), memberCount: members.length,
        memberCap: SECT_MEMBER_CAP(level), createdAt: sect.created_at ?? null,
        joinMode: joinModeNow,
      },
      myRole: member.role,
      members,
      tasks,
      joinMode: joinModeNow,
      myApplication: null,
      applications: apps.map((a: any) => ({
        id: Number(a.id), userId: Number(a.user_id), name: String(a.name || ''),
        realmName: REALM_ORDER_FOR_RANKING[Number(a.realm_index)] || '',
        level: mentorLevelOf(a.realm_index, a.realm_level),
        combatPower: Math.max(0, Math.floor(Number(a.combat_power) || 0)),
        createdAt: Number(a.created_at) || 0,
        expiresAt: (Number(a.created_at) || 0) + SECT_APPLY_TTL_MS,
      })),
      cooldownUntil,
      applyTtlMs: SECT_APPLY_TTL_MS,
      welfare: {
        salary: { amount: level * SECT_SALARY_PER_LEVEL, claimed: claimedKinds.has('salary') },
        pill: { unlocked: level >= SECT_PILL_MIN_LEVEL, claimed: claimedKinds.has('pill'), name: SECT_PILL_NAME },
      },
    });"""

# ============================================================ S7 C2 join：join_mode 分裂

# ---- S7a sect 查询加 join_mode 列 ----

S7A_OLD = r"    const sect: any = await dbGet('SELECT id, level, disbanded_at FROM sects WHERE id = ?', [sectId]);"
S7A_NEW = r"    const sect: any = await dbGet('SELECT id, level, disbanded_at, join_mode FROM sects WHERE id = ?', [sectId]);"

# ---- S7b 入盟分裂：apply 写申请 / auto 现状（成功顺手撤残留 pending）----

S7B_OLD = r"""    try {
      await dbRun('INSERT INTO sect_members (sect_id, user_id, role) VALUES (?, ?, ?)', [sectId, req.user.id, 'member']);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(400).json({ error: '你已在宗门中', code: 'ALREADY_IN_SECT' });
      throw e;
    }
    res.json({ message: '入宗成功' });"""

S7B_NEW = r"""    const joinMode = String(sect.join_mode || 'auto') === 'apply' ? 'apply' : 'auto';
    if (joinMode === 'apply') {
      // 0.8.7 T7：审批制盟 → 写 pending 申请（一人一 pending 由用户侧部分唯一索引
      // 兜底挡重复→409；72h 有效期由读取路径惰性置 expired）。满员/冷却/已在盟检查已在上方与 auto 共用。
      try {
        await dbRun('INSERT INTO sect_applications (sect_id, user_id, status, created_at) VALUES (?, ?, ?, ?)', [sectId, req.user.id, 'pending', Date.now()]);
      } catch (e: any) {
        if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '\u5df2\u6709\u5f85\u5904\u7406\u7684\u7533\u8bf7\uff0c\u8bf7\u5148\u64a4\u9500\u6216\u7b49\u5f85\u5ba1\u6279', code: 'APP_PENDING' });
        throw e;
      }
      return res.json({ ok: true, message: '\u7533\u8bf7\u5df2\u63d0\u4ea4\uff0c\u7b49\u5f85\u76df\u4e3b/\u957f\u8001\u5ba1\u6838', joinMode });
    }
    try {
      await dbRun('INSERT INTO sect_members (sect_id, user_id, role) VALUES (?, ?, ?)', [sectId, req.user.id, 'member']);
    } catch (e: any) {
      if (String(e?.message || '').includes('UNIQUE')) return res.status(400).json({ error: '你已在宗门中', code: 'ALREADY_IN_SECT' });
      throw e;
    }
    // 0.8.7 T7：直进入盟成功即撤销本人残留 pending 申请（防审批竞态产生死申请；fire-and-forget）
    await dbRun("UPDATE sect_applications SET status = 'cancelled', handled_at = ?, handled_by = ? WHERE user_id = ? AND status = 'pending'", [Date.now(), req.user.id, req.user.id]).catch(() => undefined);
    res.json({ message: '入宗成功' });"""

# ============================================================ S8 N2/N3/N4 三新端点（插在全局错误处理之前）

S8_OLD = r"""// 全局错误处理（P1-1）：不再向客户端回显 err.stack/内部信息"""

S8_NEW = r"""// 0.8.7 T7 N2：撤销我的 pending 申请（部分唯一索引保证一人最多一条；撤销后可立即再申请——
// 拒绝/撤销不进 24h 冷却，冷却只由 leave/kick/disband 三个写入点产生）
app.post('/api/sect/applications/cancel', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const up = await dbRun("UPDATE sect_applications SET status = 'cancelled', handled_at = ?, handled_by = ? WHERE user_id = ? AND status = 'pending'", [Date.now(), req.user.id, req.user.id]);
    if (!up.changes) return res.status(409).json({ error: '\u6ca1\u6709\u5f85\u5904\u7406\u7684\u7533\u8bf7', code: 'NO_PENDING' });
    res.json({ ok: true });
  } catch (e: any) {
    console.error('sect app cancel error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 0.8.7 T7 N3：审批入盟申请（approve/reject；权限=盟主+长老，§3 权限矩阵）。
// 顺序契约=先占位（单语句守卫 UPDATE 防并发双批/重复审批，changes=1 者才有资格动成员表）
// → 守卫式 INSERT 成员行（已在盟/冷却/满员三门槛一次原子生效，并发靠唯一索引兜底）
// → 插入失败回滚申请行 pending + 409 逐项诊断（口径抄 /api/mentor/apprentice :6510-6523）
// → 成功/拒绝均邮件通知申请人（先例 :6527-6532，fire-and-forget 不阻塞响应）。
// 错误码纪律：业务拒绝一律 400/409，绝不用 403（Xc() 会把 403 当会话失效强制登出）
app.post('/api/sect/applications/decide', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const appId = Math.floor(asNum(req.body?.id));
    const action = asStr(req.body?.action);
    if (!Number.isInteger(appId) || appId <= 0) return res.status(400).json({ error: '参数非法', code: 'BAD_PARAMS' });
    if (action !== 'approve' && action !== 'reject') return res.status(400).json({ error: '参数非法', code: 'BAD_ACTION' });
    const actor = await sectMemberOf(userId);
    if (!actor || (actor.role !== 'leader' && actor.role !== 'officer')) {
      return res.status(400).json({ error: '\u4ec5\u76df\u4e3b\u6216\u957f\u8001\u53ef\u5ba1\u6279\u7533\u8bf7', code: 'FORBIDDEN' });
    }
    await sectExpireStaleApplications();
    const appRow: any = await dbGet('SELECT id, sect_id, user_id, status, created_at FROM sect_applications WHERE id = ?', [appId]);
    if (!appRow) return res.status(404).json({ error: '\u7533\u8bf7\u4e0d\u5b58\u5728\u6216\u5df2\u64a4\u9500', code: 'NO_SUCH_APP' });
    if (Number(appRow.sect_id) !== actor.sect_id) return res.status(400).json({ error: '\u8be5\u7533\u8bf7\u4e0d\u5c5e\u4e8e\u672c\u76df', code: 'NOT_SAME_SECT' });
    // 占位：pending→approved/rejected 单语句守卫（并发双批/重复审批只一方 changes=1；过期行已被惰性置 expired 同样挡下）
    const newStatus = action === 'approve' ? 'approved' : 'rejected';
    const up = await dbRun(
      "UPDATE sect_applications SET status = ?, handled_at = ?, handled_by = ? WHERE id = ? AND status = 'pending'",
      [newStatus, Date.now(), userId, appId]
    );
    if (!up.changes) return res.status(409).json({ error: '\u8be5\u7533\u8bf7\u5df2\u88ab\u5904\u7406\u6216\u5df2\u8fc7\u671f', code: 'ALREADY_HANDLED' });
    const applicantId = Number(appRow.user_id);
    const sectRow: any = await dbGet('SELECT id, name, level, disbanded_at FROM sects WHERE id = ?', [actor.sect_id]);
    const sectName = String(sectRow?.name || '');
    if (action === 'reject') {
      insertMail(applicantId, '\u5165\u76df\u7533\u8bf7\u672a\u901a\u8fc7',
        `\u5f88\u9057\u61be\uff0c\u300c${sectName}\u300d\u672c\u6b21\u672a\u901a\u8fc7\u4f60\u7684\u5165\u76df\u7533\u8bf7\u3002\u4f60\u4ecd\u53ef\u7533\u8bf7\u5176\u4ed6\u4ed9\u76df\uff0c\u4ed9\u8def\u5e7f\u9614\uff0c\u4f55\u5fc5\u4e00\u5904\u3002`,
        'system', 0).catch((e: any) => console.error('sect decide reject mail error:', e?.message || e));
      return res.json({ ok: true, message: '\u5df2\u62d2\u7edd\u8be5\u7533\u8bf7' });
    }
    // approve：守卫式插入成员行（三门槛一次原子判定；冷却用 ISO 串字典序比较，与 join 端点 Date.parse 同构）
    const nowMs = Date.now();
    const ins = await dbRun(
      `INSERT INTO sect_members (sect_id, user_id, role)
       SELECT ?, ?, 'member'
       WHERE NOT EXISTS (SELECT 1 FROM sect_members WHERE user_id = ?)
         AND NOT EXISTS (SELECT 1 FROM sect_cooldowns WHERE user_id = ? AND cooldown_until > ?)
         AND (SELECT COUNT(*) FROM sect_members WHERE sect_id = ?) < ?`,
      [actor.sect_id, applicantId, applicantId, applicantId, new Date(nowMs).toISOString(), actor.sect_id, SECT_MEMBER_CAP(Number(sectRow?.level) || 1)]
    );
    if (!ins.changes) {
      // 补偿：回滚申请行 pending（满员等场景可恢复重批），再逐项诊断
      await dbRun("UPDATE sect_applications SET status = 'pending', handled_at = NULL, handled_by = NULL WHERE id = ?", [appId]).catch(() => undefined);
      const [inRow, cdRow, cntRow] = await Promise.all([
        dbGet('SELECT 1 AS x FROM sect_members WHERE user_id = ? LIMIT 1', [applicantId]),
        dbGet('SELECT cooldown_until FROM sect_cooldowns WHERE user_id = ? LIMIT 1', [applicantId]),
        dbGet('SELECT COUNT(*) AS c FROM sect_members WHERE sect_id = ?', [actor.sect_id]),
      ]);
      let msg = '\u5165\u76df\u672a\u6210\uff0c\u6761\u4ef6\u6709\u53d8\uff0c\u8bf7\u5237\u65b0\u91cd\u8bd5';
      let code = 'CONFLICT';
      let cooldownLeftMs: number | undefined = undefined;
      if (inRow) { msg = '\u5bf9\u65b9\u5df2\u52a0\u5165\u5176\u4ed6\u4ed9\u76df'; code = 'ALREADY_IN_SECT'; }
      else {
        const cdLeftMs = cdRow ? Date.parse(String(cdRow.cooldown_until || '')) - nowMs : NaN;
        if (Number.isFinite(cdLeftMs) && cdLeftMs > 0) { msg = '\u5bf9\u65b9\u9000\u76df\u51b7\u5374\u4e2d\uff0c\u6682\u4e0d\u53ef\u52a0\u5165'; code = 'COOLDOWN_UNTIL'; cooldownLeftMs = cdLeftMs; }
        else if ((Number(cntRow?.c) || 0) >= SECT_MEMBER_CAP(Number(sectRow?.level) || 1)) { msg = '\u8be5\u76df\u4eba\u6570\u5df2\u6ee1'; code = 'SECT_FULL'; }
      }
      const body: any = { error: msg, code };
      if (cooldownLeftMs !== undefined) body.cooldownLeftMs = cooldownLeftMs;
      return res.status(409).json(body);
    }
    insertMail(applicantId, '\u5165\u76df\u7533\u8bf7\u5df2\u901a\u8fc7',
      `\u9053\u53cb\u606d\u559c\uff01\u300c${sectName}\u300d\u7684\u76df\u4e3b/\u957f\u8001\u5df2\u901a\u8fc7\u4f60\u7684\u5165\u76df\u7533\u8bf7\uff0c\u4f60\u5df2\u6b63\u5f0f\u52a0\u5165\u672c\u76df\u3002\n\n\u6bcf\u65e5\u4ff8\u7984\u3001\u76df\u4efb\u52a1\u5956\u52b1\u4e0e\u5b97\u95e8\u4e39\u836f\u8bb0\u5f97\u9886\u53d6\uff0c\u613f\u4e0e\u76df\u4e2d\u9053\u53cb\u5171\u8bc1\u4ed9\u9014\u3002`,
      'system', 0).catch((e: any) => console.error('sect decide approve mail error:', e?.message || e));
    return res.json({ ok: true, message: '\u5df2\u901a\u8fc7\u7533\u8bf7\uff0c\u5bf9\u65b9\u5df2\u52a0\u5165\u672c\u76df', member: { sectId: actor.sect_id, userId: applicantId } });
  } catch (e: any) {
    console.error('sect decide error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 0.8.7 T7 N4：盟设置。notice（≤200 字）=盟主+长老（§3 权限矩阵，放宽自 V27 仅盟主，
// /api/sect/notice 保留为公告子集等价端点）；joinMode（'auto'|'apply'）=仅盟主。
// 两字段至少传一个；各自独立校验权限（长老传 joinMode → 400）
app.post('/api/sect/settings', authenticateToken, sectWriteLimit, async (req: any, res: any) => {
  try {
    const actor = await sectMemberOf(req.user.id);
    if (!actor || (actor.role !== 'leader' && actor.role !== 'officer')) {
      return res.status(400).json({ error: '\u4ec5\u76df\u4e3b\u6216\u957f\u8001\u53ef\u4fee\u6539\u76df\u8bbe\u7f6e', code: 'FORBIDDEN' });
    }
    const sectRow: any = await dbGet('SELECT id, notice, join_mode, disbanded_at FROM sects WHERE id = ?', [actor.sect_id]);
    if (!sectRow || sectRow.disbanded_at) return res.status(400).json({ error: '宗门不存在或已解散' });
    const hasNotice = req.body != null && req.body.notice !== undefined && req.body.notice !== null;
    const hasMode = req.body != null && req.body.joinMode !== undefined && req.body.joinMode !== null;
    if (!hasNotice && !hasMode) return res.status(400).json({ error: '参数非法', code: 'BAD_PARAMS' });
    let notice = String(sectRow.notice || '');
    if (hasNotice) notice = asStr(req.body.notice).trim().slice(0, 200);
    let joinMode = String(sectRow.join_mode || 'auto') === 'apply' ? 'apply' : 'auto';
    if (hasMode) {
      const m = asStr(req.body.joinMode);
      if (m !== 'auto' && m !== 'apply') return res.status(400).json({ error: 'joinMode \u4ec5\u652f\u6301 auto/apply', code: 'BAD_JOIN_MODE' });
      if (actor.role !== 'leader') return res.status(400).json({ error: '\u4ec5\u76df\u4e3b\u53ef\u5207\u6362\u52a0\u5165\u6a21\u5f0f', code: 'FORBIDDEN' });
      joinMode = m;
    }
    await dbRun('UPDATE sects SET notice = ?, join_mode = ? WHERE id = ?', [notice, joinMode, actor.sect_id]);
    res.json({ ok: true, notice, joinMode });
  } catch (e: any) {
    console.error('sect settings error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 全局错误处理（P1-1）：不再向客户端回显 err.stack/内部信息"""

# ============================================================ S9 P1 捐献回馈

S9A_OLD = r"    await dbRun('INSERT INTO sect_ledger (sect_id, user_id, amount, after_funds) VALUES (?, ?, ?, ?)', [member.sect_id, req.user.id, amount, funds]);"

S9A_NEW = S9A_OLD + r"""
    // 0.8.7 T7 P1 捐献回馈：floor(捐献额×2%) 写个人 sectContribution（两套宗门唯一经济互通点；
    // 数值定档《数值表-T7T8》T7-7/8）。日上限=SECT_DONATE_DAILY_CAP×2%=1000，由上方日捐献累计
    // 上限天然钳制（常量单一来源，调贡献率时上限自动跟随），不另设常量不另加查询。
    // 顺序契约：先扣款成功、再发回馈；回馈写失败仅日志不回滚捐献（贡献无灵石回流路径，无对价风险为零）
    const contribBack = Math.floor(amount * SECT_DONATE_CONTRIB_RATE);
    if (contribBack > 0) {
      const rb = await updatePlayerSave(req.user.id, (sd: any) => {
        const p = sd && sd.player;
        if (p) p.sectContribution = Math.max(0, Math.floor(Number(p.sectContribution) || 0)) + contribBack;
      });
      if (!rb.ok) console.error('sect contribute contrib-back error:', rb.error || 'unknown');
    }"""

S9B_OLD = r"""    res.json({
      message: '捐献成功', funds, level: newLevel, levelUp,
      donated: donated + amount, dailyCap: SECT_DONATE_DAILY_CAP, spiritStones: spend.spiritStones ?? null,
    });"""

S9B_NEW = r"""    res.json({
      message: '捐献成功', funds, level: newLevel, levelUp,
      donated: donated + amount, dailyCap: SECT_DONATE_DAILY_CAP, spiritStones: spend.spiritStones ?? null,
      contribBack,
    });"""

# ============================================================ S10 建宗注释修正（§10-5；0.8.8 item15 同步新门槛口径）

S10_OLD = r"// 创建宗门：境界≥筑基 + 名称唯一 + 5000 灵石（服务端结算：spendFromSave 失败即无宗）"
S10_NEW = r"// 创建宗门：境界≥元婴 + 名称唯一 + 1000000 灵石（服务端结算：spendFromSave 失败即无宗；0.8.7 T7 顺手修正注释 5000→50000；0.8.8 item15 门槛 50000→1000000、筑基→元婴）"

# ============================================================ S11 建宗门槛：元婴期 + 100W 灵石（0.8.8 item15）

S11A_OLD = r"const SECT_CREATE_COST = 50000;      // 建宗灵石（一次性；不进 sect_ledger、不推进捐献任务；物价×10）"
S11A_NEW = r"const SECT_CREATE_COST = 1000000;    // 建宗灵石（一次性；不进 sect_ledger、不推进捐献任务；0.8.8 item15 50000→1000000）"

S11B_OLD = r"const SECT_CREATE_MIN_REALM = 1;     // 建宗境界门槛：REALM_ORDER_FOR_RANKING 下标 ≥1（筑基期）"
S11B_NEW = r"const SECT_CREATE_MIN_REALM = 3;     // 建宗境界门槛：REALM_ORDER_FOR_RANKING 下标 ≥3（元婴期；0.8.8 item15）"

S11C_OLD = r"return res.status(400).json({ error: '境界需达到筑基期方可开宗立派', code: 'REALM_TOO_LOW' });"
S11C_NEW = r"return res.status(400).json({ error: '境界需达到元婴期方可开宗立派', code: 'REALM_TOO_LOW' });"

EDITS = [
    ('S1 常量区', S1_OLD, S1_NEW),
    ('S2a sects 建表定义加列', S2A_OLD, S2A_NEW),
    ('S2b 申请表+索引+PRAGMA+惰性过期', S2B_OLD, S2B_NEW),
    ('S3 G7 差值钳', S3_OLD, S3_NEW),
    ('S4a gongfa RANK_TOO_LOW 403→400', S4A_OLD, S4A_NEW),
    ('S4b gongfa REALM_TOO_LOW 403→400', S4B_OLD, S4B_NEW),
    ('S4c join 冷却 403→409+cooldownLeftMs', S4C_OLD, S4C_NEW),
    ('S4d kick 无权限 403→400', S4D_OLD, S4D_NEW),
    ('S4e kick 目标不在本宗 403→400', S4E_OLD, S4E_NEW),
    ('S4f kick 不能移除宗主 403→400', S4F_OLD, S4F_NEW),
    ('S4g kick 长老只能移除成员 403→400', S4G_OLD, S4G_NEW),
    ('S4h role 两处 403→400', S4H_OLD, S4H_NEW),
    ('S4i transfer 两处 403→400', S4I_OLD, S4I_NEW),
    ('S4j disband 403→400', S4J_OLD, S4J_NEW),
    ('S4k notice 403→400+放宽长老', S4K_OLD, S4K_NEW),
    ('S5 list 检索+契约响应', S5_OLD, S5_NEW),
    ('S6a mine 无盟分支扩展', S6A_OLD, S6A_NEW),
    ('S6b mine 有盟分支扩展', S6B_OLD, S6B_NEW),
    ('S7a join sect 查询加 join_mode', S7A_OLD, S7A_NEW),
    ('S7b join join_mode 分裂', S7B_OLD, S7B_NEW),
    ('S8 N2/N3/N4 三新端点', S8_OLD, S8_NEW),
    ('S9a 捐献回馈', S9A_OLD, S9A_NEW),
    ('S9b 捐献响应加 contribBack', S9B_OLD, S9B_NEW),
    ('S10 建宗注释修正', S10_OLD, S10_NEW),
    ('S11a 建宗灵石 50000→1000000', S11A_OLD, S11A_NEW),
    ('S11b 建宗境界门槛 1→3（元婴期）', S11B_OLD, S11B_NEW),
    ('S11c 建宗境界文案 筑基→元婴', S11C_OLD, S11C_NEW),
]


def fail(msg):
    print('[FAIL] %s' % msg)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    src_path = a.src
    if not os.path.isfile(src_path):
        fail('源文件不存在：%s' % src_path)
    with io.open(src_path, 'r', encoding='utf-8', newline='') as f:
        src = f.read()

    # 1) 幂等
    if 'sect_applications' in src or 'SECT_APPLY_TTL_MS' in src:
        fail('source looks already patched（已存在 sect_applications / SECT_APPLY_TTL_MS）')

    # 2) 锚点计数（铁律④口径：逐串计数，必须恰 1）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail('%s 锚点出现 %d 次（期望 1）：%r' % (name, n, old[:120]))
        if old == new:
            fail('%s old == new' % name)

    # 3) 基线 403 双计数前置确认（锚区漂移即停手）
    b_res403 = src.count('res.status(403)')
    b_obj403 = src.count('status: 403')
    if b_res403 != 22 or b_obj403 != 2:
        fail('基线 403 计数漂移：res.status(403)=%d（期望 22）、status: 403=%d（期望 2）——先查后动' % (b_res403, b_obj403))

    # 4) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 5) 门禁
    gates = [
        # ---- 403 双计数（本补丁存在的第一理由，铁律①）----
        ('403 改码 res 形式 22→11', 'res.status(403)', 11, None),
        ('403 改码 对象形式 2→0', 'status: 403', 0, None),
        ('旧 kick 无权限 403 已清零', "res.status(403).json({ error: '无权限' })", 0, None),
        ('旧 join 冷却 403 已清零', "res.status(403).json({\n          error: '退宗冷却中", 0, None),
        ('409 语义就位（join 冷却）', "res.status(409).json({\n          error: '退宗冷却中", 1, None),
        # ---- S2 表/列 ----
        ('S2b 申请表建表串恰 1', 'CREATE TABLE IF NOT EXISTS sect_applications', 1, None),
        ('S2b 部分唯一索引裸串恰 1（设计案 §9.1④ 字面）', 'idx_sect_app_user_pending', 1, None),
        ('S2b 盟侧索引恰 1', 'idx_sect_app_sect', 1, None),
        ('S2 join_mode 加列串恰 2（ALTER+建表）', "join_mode TEXT NOT NULL DEFAULT 'auto'", 2, None),
        ('S2b PRAGMA 守卫', 'PRAGMA table_info(sects)', 1, None),
        ('S2b 惰性过期函数', 'async function sectExpireStaleApplications()', 1, None),
        ('S2b 惰性过期调用 3 处', 'await sectExpireStaleApplications()', 3, None),
        # ---- S1 常量（数值表-T7T8 定档）----
        ('S1 申请有效期 72h', 'const SECT_APPLY_TTL_MS = 72 * 3600 * 1000;', 1, None),
        ('S1 贡献率 2%', 'const SECT_DONATE_CONTRIB_RATE = 0.02;', 1, None),
        ('S1 钳增速 20/分', 'const SECT_CONTRIB_CLAMP_PER_MIN = 20;', 1, None),
        ('S1 钳兜底 5000', 'const SECT_CONTRIB_CLAMP_BASE = 5000;', 1, None),
        # ---- S3 G7 钳 ----
        ('S3 E2:sectContrib 钳 2 处', "clamped.push('E2:sectContrib", 2, None),
        # ---- S5 list ----
        ('S5 list keyword 净化', 'kw = mentorLikeEscape(n);', 1, None),
        ('S5 list LIKE 转义', "s.name LIKE ? ESCAPE '\\\\'", 1, None),
        ('S5 list hasMore 模式', 'const hasMore = rows.length > SECT_LIST_PAGE_SIZE;', 1, None),
        ('S5 list mine.pendingSectId', 'pendingSectId: myApp ? Number(myApp.sect_id) : null,', 1, None),
        ('S5 list 旧字段双发 leader', 'leaderName: String(r.leader || \'\'), leader: String(r.leader || \'\'),', 1, None),
        # ---- S6 mine ----
        ('S6a 无盟 myApplication', 'myApplication: app0 ? {', 1, None),
        ('S6b 有盟 applications 查询', "WHERE a.sect_id = ? AND a.status = 'pending'", 1, None),
        ('S6b applyTtlMs 下发 2 处', 'applyTtlMs: SECT_APPLY_TTL_MS,', 2, None),
        ('S6b 有盟根级 cooldownUntil 邻接 applyTtlMs', 'cooldownUntil,\n      applyTtlMs: SECT_APPLY_TTL_MS,', 1, None),
        ('S6b mentorLevelOf 复用', 'level: mentorLevelOf(a.realm_index, a.realm_level),', 1, None),
        # ---- S7 join ----
        ('S7a join 查询带 join_mode', 'SELECT id, level, disbanded_at, join_mode FROM sects WHERE id = ?', 1, None),
        ('S7b 申请提交文案', "\\u7533\\u8bf7\\u5df2\\u63d0\\u4ea4\\uff0c\\u7b49\\u5f85\\u76df\\u4e3b/\\u957f\\u8001\\u5ba1\\u6838", 1, None),
        ('S7b 重复申请 409', "code: 'APP_PENDING'", 1, None),
        ('S7b auto 成功撤残留申请', "UPDATE sect_applications SET status = 'cancelled', handled_at = ?, handled_by = ? WHERE user_id = ? AND status = 'pending'", 2, None),
        # ---- S8 三新端点 ----
        ('S8 cancel 端点', "app.post('/api/sect/applications/cancel'", 1, None),
        ('S8 decide 端点', "app.post('/api/sect/applications/decide'", 1, None),
        ('S8 settings 端点', "app.post('/api/sect/settings'", 1, None),
        ('S8 无 pending 409', "code: 'NO_PENDING'", 1, None),
        ('S8 占位守卫 UPDATE', "UPDATE sect_applications SET status = ?, handled_at = ?, handled_by = ? WHERE id = ? AND status = 'pending'", 1, None),
        ('S8 失败回滚 pending', "UPDATE sect_applications SET status = 'pending', handled_at = NULL, handled_by = NULL WHERE id = ?", 1, None),
        ('S8 守卫式插成员', "INSERT INTO sect_members (sect_id, user_id, role)\n       SELECT ?, ?, 'member'", 1, None),
        ('S8 冷却 409 带 cooldownLeftMs', 'body.cooldownLeftMs = cooldownLeftMs;', 1, None),
        ('S8 双邮件通知', "insertMail(applicantId,", 2, None),
        ('S8 approve 附成员行', 'member: { sectId: actor.sect_id, userId: applicantId }', 1, None),
        ('S8 settings 双字段写库', "UPDATE sects SET notice = ?, join_mode = ? WHERE id = ?", 1, None),
        # ---- S9 捐献回馈 ----
        ('S9 贡献率使用', 'Math.floor(amount * SECT_DONATE_CONTRIB_RATE)', 1, None),
        ('S9 回馈响应字段', 'contribBack,', 1, None),
        # ---- 基线未被破坏 ----
        ('基线 24h 冷却三写入点恒 3', 'INSERT INTO sect_cooldowns (user_id, cooldown_until) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET cooldown_until = excluded.cooldown_until', 3, None),
        ('基线 建宗守卫链未动', 'const spend = await spendFromSave(req.user.id, SECT_CREATE_COST);', 1, None),
        ('基线 任务占位-发奖-删行未动', "DELETE FROM sect_task_claims WHERE user_id = ? AND date = ? AND task_key = ?", 1, None),
        ('基线 福利占位-发奖-删行未动', "DELETE FROM sect_welfare_claims WHERE user_id = ? AND date = ? AND kind = ?", 1, None),
        ('基线 mine 端点仍在', "app.get('/api/sect/mine'", 1, None),
        ('基线 join 端点仍在', "app.post('/api/sect/join'", 1, None),
        ('基线 gongfa 端点仍在（T3 禁改域）', "app.get('/api/sect/gongfa'", 1, None),
        ('S10 注释修正', '境界≥元婴 + 名称唯一 + 1000000 灵石', 1, None),
        # ---- S11 建宗门槛（0.8.8 item15：元婴期 + 100W 灵石）----
        ('S11a 建宗灵石=1000000', 'const SECT_CREATE_COST = 1000000;', 1, None),
        ('S11a 旧值 50000 已清零', 'const SECT_CREATE_COST = 50000;', 0, None),
        ('S11b 建宗境界门槛=3（元婴期）', 'const SECT_CREATE_MIN_REALM = 3;', 1, None),
        ('S11b 旧值 1 已清零', 'const SECT_CREATE_MIN_REALM = 1;', 0, None),
        ('S11c 境界不足文案=元婴期', '境界需达到元婴期方可开宗立派', 1, None),
        ('S11c 旧文案 筑基期 已清零', '境界需达到筑基期方可开宗立派', 0, None),
    ]
    ok = True
    for g in gates:
        label, needle, exp = g[0], g[1], g[2]
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-36s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))
    if not ok:
        fail('门禁未全过')

    # 6) ★ 顺序契约位置断言（比计数更强：计数对、次序错照样是缺陷）
    # 6a) contribute：spendFromSave（扣款）→ sect_ledger 流水 → 回馈（先扣款后发回馈）
    i = out.find("app.post('/api/sect/contribute'")
    j = out.find("app.post(", i + 30)
    seg = out[i:j if j > 0 else len(out)]
    p_spend = seg.find('spendFromSave(req.user.id, amount)')
    p_ledger = seg.find("INSERT INTO sect_ledger")
    p_back = seg.find('SECT_DONATE_CONTRIB_RATE')
    if not (0 <= p_spend < p_ledger < p_back):
        fail('捐献顺序契约被破坏：扣款(%d) → 流水(%d) → 回馈(%d) 必须严格递增' % (p_spend, p_ledger, p_back))
    print('  [OK] 顺序契约：contribute 为「扣款 → 流水 → 回馈」，回馈失败不回滚捐献（无对价风险为零）')

    # 6b) decide：占位 UPDATE → 守卫式 INSERT 成员 → 邮件（先占位再动成员表）
    i = out.find("app.post('/api/sect/applications/decide'")
    j = out.find("app.post(", i + 40)
    seg = out[i:j if j > 0 else len(out)]
    p_hold = seg.find("UPDATE sect_applications SET status = ?, handled_at = ?, handled_by = ? WHERE id = ? AND status = 'pending'")
    p_ins = seg.find("SELECT ?, ?, 'member'")
    p_mail = seg.rfind('insertMail(applicantId,')  # approve 分支的邮件（reject 分支邮件在前属正常）
    if not (0 <= p_hold < p_ins < p_mail):
        fail('审批顺序契约被破坏：占位(%d) → 插成员(%d) → 邮件(%d) 必须严格递增' % (p_hold, p_ins, p_mail))
    print('  [OK] 顺序契约：decide 为「占位 → 守卫式插成员 → 邮件」，插入失败回滚 pending + 逐项诊断')

    # 6c) join：满员检查（SECT_MEMBER_CAP）早于申请占位 INSERT（apply 与 auto 共用前置检查）
    i = out.find("app.post('/api/sect/join'")
    j = out.find("app.post(", i + 30)
    seg = out[i:j if j > 0 else len(out)]
    p_cap = seg.find('SECT_MEMBER_CAP')
    p_app = seg.find('INSERT INTO sect_applications')
    p_mem = seg.find('INSERT INTO sect_members')
    if not (0 <= p_cap < p_app < p_mem):
        fail('join 顺序契约被破坏：满员检查(%d) → 申请分支(%d) → auto 入盟(%d) 必须严格递增' % (p_cap, p_app, p_mem))
    print('  [OK] 顺序契约：join 满员/冷却/已在盟前置检查为 auto 与 apply 共用')

    # 7) 往返自证：把每个 new 换回 old 必须逐字复现原文
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail('%s 的 new 在产物中出现 %d 次（期望 1）' % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail('round-trip mismatch')

    print('  delta = %+d chars  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    if a.check:
        print('  --check：未写回 %s' % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".t7sect-", suffix=".tmp")
    try:
        with io.open(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print('  已原子写回 %s' % src_path)


if __name__ == '__main__':
    main()
