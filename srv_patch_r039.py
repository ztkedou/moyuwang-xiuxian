# -*- coding: utf-8 -*-
r"""
srv_patch_r039.py -- R-039 设置「重新开始游戏」⇒ 连服务端一起清干净（保留账号）

只做一件事：新增**自服**清档端点 `POST /api/character/reset`，把该 user 的角色数据全删。

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` / `--selftest` 只校验不写。
  幂等：产物里已含 `/api/character/reset` 或 `[r039reset]` 标记则 SKIP。
  lead 接线：把本环挂在 SRV_CHAIN 链尾（紧接 srv_patch_claimedfix.py 之后）。
  锚点：`// 游戏字典端点 (…)`（全仓唯一），本环**只在其前插入**，不改既有任何行。

为什么改（bug 证据）
--------------------------------------------------------------------------
  客户端「重新开始游戏」的确认回调只调 `handleRebirth()`（`mm()` 是空实现 + 一串
  setPlayer(null)…）⇒ **零服务端请求**，纯前端回到开始界面。于是服务端仍留着：
    player_titles（仙务·称号）/ stats_daily（修行统计）/ wudao（仙务·心法）/
    achievement_claimed（成就）/ player_gongfa（功法）… 一大票行。
  既有 GM 的 `POST /api/gm/players/:id/reset-save` 只重置 `saves` 里的 JSON，
  同样不碰这些独立表；`DELETE /api/gm/players/:id` 才删号（且只清 4 张表）。

本环改点（1 处插入）
--------------------------------------------------------------------------
  在「游戏字典端点」注释之前插入一个自包含块：
    · `R039_SINGLE` / `R039_MULTI` —— 该玩家的归属表清单（表名/列名全为常量）
    · `r039PurgeStatements()`    —— 生成全部 DELETE（含纪事点赞、道侣宴席等复合条件）
    · `r039SocialRepair()`       —— 先处理会影响**他人**的多步语义（宗门让位/解散、结义解散、
                                    悬赏退回、道侣和离）
    · `r039PurgeCharacter()`     —— 修复 → 加 saveLock → `BEGIN IMMEDIATE … COMMIT`
                                    **单脚本**交给 `db.exec`（任一句失败即 ROLLBACK）
    · `app.post('/api/character/reset', authenticateToken, rateLimit(...))`

  清（该角色的行）：
    saves / save_snapshots / rankings / mail / player_titles / daily_quests / rebirth_state /
    achievement_claimed / lottery_history / activity_milestones / activity_rank_settled /
    arena_trials / arena_scores / arena_trial_daily / social_scores / worldboss_hits /
    event_boss_hits / guide_progress / week_goals / teahouse_bets / sect_cooldowns /
    sect_task_claims / sect_welfare_claims / sect_applications / player_sect_gongfa /
    market_payouts / market_listings(seller) / bounties(poster) / stats_daily / alchemy /
    economy_ledger / pets / pet_spirit_exped / pet_play_log / pet_care_log / dungeon_tracker /
    adventures / spirit_farm / farm_unlocks / farm_daily_care / wudao / wudao_log /
    player_gongfa / fun_daily / activity_rain_state / activity_checkin / activity_token /
    activity_token_daily / chronicle / chronicle_praise /
    friendships / friend_gifts / mentorships / mentor_greetings / teach_log /
    arena_battles / arena_snapshots / grudges / couple_feasts / couple_feast_guests /
    sect_members（退宗；若是宗主先让位或解散）/ sworn_members（退结义）

  保留（账号与共享/全局，一概不动）：
    users 行 / refresh_tokens / active_sessions（**账号与登录态**）;
    titles / gongfa（字典表）; worldboss / event_boss / activity_config / events /
    activity_frame（全局）; sect_tasks / sect_ledger（宗门共享账）;
    chat_messages / gm_sessions / gm_audit_logs（全局）; season_archives（历史赛季）。

事务口径（本项目已踩过的坑）
--------------------------------------------------------------------------
  本项目是 node-sqlite3 单连接回调式驱动，**禁止**「跨 await 的裸 BEGIN/COMMIT」
  （中间会让别的请求的裸 db.run 插进同一事务、被一起 ROLLBACK，串号）。
  本环改为：把全部 DELETE 拼成**一条** `BEGIN IMMEDIATE … COMMIT` 脚本，
  **一次性**交给 `db.exec` ⇒ 单次提交、中间无 JS 让出点 ⇒ 不可能被插队；
  任一句失败 ⇒ `sqlite3_exec` 停止 ⇒ 本环 `ROLLBACK`。SQL 里除「校验过的整数 uid」外
  无任何外部输入（表名/列名均为本环常量）。

工程约束
--------------------------------------------------------------------------
  · 回调式 sqlite3 ⇒ 只用 `db.run/db.get/db.all/db.exec`，**不写** `db.run(...).catch(...)`。
  · ESM ⇒ 不写 `require(`（门禁断言其计数不增）。
  · 业务拒绝零 403 纪律 ⇒ **不新增 `res.status(403)`**（基线 11）。
  · 不新增 `setInterval`（基线 3）。
  · 注入块中文一律 `zh()` 转义成 `\uXXXX`（门禁 needle 同步用 ASCII）。
  · 每处替换带 `expect=1`，命中数不符即中止（拒绝静默失败）。
  · ⛔ 不改 `srv/index_v28.ts`（链产物）；⛔ 不改任何既有 `srv_patch_*.py`；⛔ 不改基座指纹。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（同时用于已打补丁判定）
MARK = "[r039reset]"

# ============================================================ 唯一锚点

ANCHOR = "// 游戏字典端点 (成就/称号/洞府/灵宠/功法/物品/抽奖池/宗门/天赋/草药)"


def zh(s: str) -> str:
    """注入块编码纪律：非 ASCII → `\\uXXXX`（与产物既有转义风格一致）。"""
    return ''.join(ch if ord(ch) < 128 else '\\u%04x' % ord(ch) for ch in s)


R039_BLOCK = zh(r"""// ===== [r039reset] R-039 设置「重新开始游戏」⇒ 连服务端一起清干净（保留账号）=====
// 病根：重置按钮只走前端 handleRebirth（mm() 空实现 + setPlayer(null)…），零服务端请求 ⇒
//   仙务·称号(player_titles) / 修行统计(stats_daily) / 仙务·心法(wudao) / 成就(achievement_claimed)
//   / 功法(player_gongfa) 等服务端行原样保留。本环新增 POST /api/character/reset 自服清档。
// 保留（账号与共享/全局，一概不动）：users 行 / refresh_tokens / active_sessions（账号与登录态）;
//   titles / gongfa（字典表）; worldboss / event_boss / activity_config / events / activity_frame;
//   sect_tasks / sect_ledger（宗门共享账）; chat_messages / gm_sessions / gm_audit_logs;
//   season_archives（历史赛季）。
// 事务：全部 DELETE 拼成**一条** BEGIN..COMMIT 脚本交给 db.exec（单次提交 ⇒ 别的请求的裸
//   db.run 不可能插进来；任一句失败 ⇒ sqlite3_exec 停止 ⇒ 本环 ROLLBACK）。SQL 里除「校验过
//   的整数 uid」外无任何外部输入（表名/列名均为本环常量）。
const R039_SINGLE: Array<[string, string]> = [
  // [表, 归属列] —— 玩家单列归属的行，整行删除
  ['saves', 'user_id'], ['save_snapshots', 'user_id'], ['rankings', 'user_id'],
  ['mail', 'user_id'], ['player_titles', 'user_id'], ['daily_quests', 'user_id'],
  ['rebirth_state', 'user_id'], ['achievement_claimed', 'user_id'], ['lottery_history', 'user_id'],
  ['activity_milestones', 'user_id'], ['activity_rank_settled', 'user_id'],
  ['arena_trials', 'user_id'], ['arena_scores', 'user_id'], ['arena_trial_daily', 'user_id'],
  ['social_scores', 'user_id'], ['worldboss_hits', 'user_id'], ['event_boss_hits', 'user_id'],
  ['guide_progress', 'user_id'], ['week_goals', 'user_id'], ['teahouse_bets', 'user_id'],
  ['sect_cooldowns', 'user_id'], ['sect_task_claims', 'user_id'], ['sect_welfare_claims', 'user_id'],
  ['sect_applications', 'user_id'], ['player_sect_gongfa', 'user_id'], ['market_payouts', 'user_id'],
  ['stats_daily', 'player_id'], ['alchemy', 'player_id'], ['economy_ledger', 'player_id'],
  ['pets', 'player_id'], ['pet_spirit_exped', 'player_id'], ['pet_play_log', 'player_id'],
  ['pet_care_log', 'player_id'], ['dungeon_tracker', 'player_id'], ['adventures', 'player_id'],
  ['spirit_farm', 'player_id'], ['farm_unlocks', 'player_id'], ['farm_daily_care', 'player_id'],
  ['wudao', 'player_id'], ['wudao_log', 'player_id'], ['player_gongfa', 'player_id'],
  ['fun_daily', 'player_id'], ['activity_rain_state', 'player_id'], ['activity_checkin', 'player_id'],
  ['activity_token', 'player_id'], ['activity_token_daily', 'player_id'],
  ['chronicle', 'player_id'], ['market_listings', 'seller_id'], ['bounties', 'poster_id'],
  // 退宗 / 退结义：成员行本体（预步骤只负责让位/解散，行本体在这里删）
  ['sect_members', 'user_id'], ['sworn_members', 'user_id'],
];
// 双向归属（该玩家是任一方都算「他的数据」）：对称关系/对战/恩怨删双向（与 /api/friends/remove 同口径）
const R039_MULTI: Array<[string, string]> = [
  ['friendships', 'user_id = ? OR friend_id = ?'],
  ['friend_gifts', 'sender_id = ? OR receiver_id = ?'],
  ['mentorships', 'mentor_id = ? OR apprentice_id = ?'],
  ['mentor_greetings', 'mentor_id = ? OR apprentice_id = ?'],
  ['teach_log', 'user_id = ? OR apprentice_id = ?'],
  ['arena_battles', 'challenger_id = ? OR defender_id = ?'],
  ['arena_snapshots', 'challenger_id = ? OR target_id = ?'],
  ['grudges', 'owner_id = ? OR enemy_id = ?'],
];
// 归属该玩家角色的全部待删语句（顺序：先删引用他表的行，再删主体；本库 FK 未开，顺序仅为稳妥）
function r039PurgeStatements(userId: number): Array<[string, any[]]> {
  const u = userId;
  const out: Array<[string, any[]]> = [];
  out.push(['DELETE FROM chronicle_praise WHERE user_id = ? OR entry_id IN (SELECT id FROM chronicle WHERE player_id = ?)', [u, u]]);
  out.push(['DELETE FROM couple_feast_guests WHERE user_id = ? OR feast_id IN (SELECT f.id FROM couple_feasts f JOIN couples c ON c.id = f.couple_id WHERE c.user_a = ? OR c.user_b = ?)', [u, u, u]]);
  out.push(['DELETE FROM couple_feasts WHERE couple_id IN (SELECT id FROM couples WHERE user_a = ? OR user_b = ?)', [u, u]]);
  for (const pair of R039_SINGLE) out.push(['DELETE FROM ' + pair[0] + ' WHERE ' + pair[1] + ' = ?', [u]]);
  for (const pair of R039_MULTI) {
    const n = (pair[1].match(/\?/g) || []).length;
    const args: any[] = [];
    for (let i = 0; i < n; i++) args.push(u);
    out.push(['DELETE FROM ' + pair[0] + ' WHERE ' + pair[1], args]);
  }
  return out;
}
// 社交关系修复：先处理会影响**他人**的多步语义（幂等；失败只记日志，不阻断主清档）
async function r039SocialRepair(userId: number, nowMs: number, iso: string): Promise<void> {
  // (a) 宗门：宗主让位给最早加入的其它成员；独苗则解散（否则会把别人的宗门弄成无主）
  const sm: any = await dbGet('SELECT sect_id, role FROM sect_members WHERE user_id = ?', [userId]);
  if (sm) {
    const sectId = Number(sm.sect_id);
    if (String(sm.role) === 'leader') {
      const next: any = await dbGet(
        'SELECT user_id FROM sect_members WHERE sect_id = ? AND user_id <> ? ORDER BY joined_at ASC, user_id ASC LIMIT 1',
        [sectId, userId]);
      if (next) {
        await dbRun("UPDATE sect_members SET role = 'leader' WHERE sect_id = ? AND user_id = ?", [sectId, Number(next.user_id)]);
        await dbRun('UPDATE sects SET leader_id = ? WHERE id = ?', [Number(next.user_id), sectId]);
      } else {
        await dbRun('UPDATE sects SET disbanded_at = ? WHERE id = ?', [iso, sectId]);
      }
    }
  }
  // (b) 结义：本人退出后人数不足则解散（与 /api/sworn/leave 同口径）
  const sws: any[] = await dbAll('SELECT group_id FROM sworn_members WHERE user_id = ?', [userId]);
  for (const g of (sws || [])) {
    const c: any = await dbGet('SELECT COUNT(*) AS c FROM sworn_members WHERE group_id = ?', [Number(g.group_id)]);
    if (Number(c && c.c) - 1 < SWORN_MIN) {
      await dbRun('UPDATE sworn_groups SET disbanded = 1 WHERE id = ?', [Number(g.group_id)]);
    }
  }
  // (c) 悬赏：本人「接过」别人的悬赏 → 退回可接状态（不删别人的悬赏单）
  await dbRun("UPDATE bounties SET status = 'open', acceptor_id = NULL, acceptor_name = '' WHERE acceptor_id = ? AND status = 'accepted'", [userId]);
  // (d) 道侣：未成/已成一律和离（沿用 divorce/decline 的 'divorced' 口径，不引入新状态）
  await dbRun("UPDATE couples SET status = 'divorced', ended_at = ? WHERE status IN ('pending','married') AND (user_a = ? OR user_b = ?)", [nowMs, userId, userId]);
}
// 主清档：社交修复 → 加锁 → BEGIN..COMMIT 单脚本（全清或全不动）
function r039PurgeCharacter(userId: number): Promise<{ ok: boolean; error?: string }> {
  const uid = Math.floor(Number(userId));
  if (!Number.isFinite(uid) || uid <= 0) return Promise.resolve({ ok: false, error: 'bad_user' });
  const nowMs = Date.now();
  const iso = nowIso();
  return r039SocialRepair(uid, nowMs, iso).catch((e: any) => {
    console.error('[r039reset] social repair failed:', e && e.message ? e.message : e);
  }).then(() => withSaveLock(uid, () => new Promise<{ ok: boolean; error?: string }>((resolve) => {
    const lines: string[] = ['BEGIN IMMEDIATE;'];   // ★ 2026-10-01 修：必须带分号！join('\n') 不会自动加，
    //   不带就拼成 `BEGIN IMMEDIATE\nDELETE...` ⇒ SQLite 语法错误 ⇒ 接口恒 500
    for (const s of r039PurgeStatements(uid)) {
      const args = s[1];
      let i = 0;
      lines.push(s[0].replace(/\?/g, () => String(args[i++])) + ';');
    }
    lines.push('COMMIT;');
    db.exec(lines.join('\n'), (err: any) => {
      if (!err) return resolve({ ok: true });
      console.error('[r039reset] purge failed, rolling back:', err && err.message ? err.message : err);
      db.run('ROLLBACK', () => resolve({ ok: false, error: 'purge_failed' }));
    });
  })));
}
// R-039 自服清档：清该角色的全部服务端数据（保留账号 / 登录态）
app.post('/api/character/reset', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => 'chreset:' + (req.user?.id ?? req.ip) }), async (req: any, res: any) => {
  try {
    const r = await r039PurgeCharacter(req.user.id);
    if (!r.ok) return res.status(500).json({ error: 'reset_failed' });
    res.json({ ok: true });
  } catch (e: any) {
    console.error('[r039reset] error:', e && e.message ? e.message : e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

""")

EDITS = [
    ("R039 自服清档块（插在「游戏字典端点」之前）", ANCHOR, R039_BLOCK + ANCHOR),
]

# 前置依赖（本环只读这些串做自证，不改）
REQUIRES = [
    (ANCHOR, 1, "唯一插入锚点必须在位"),
    ("const authenticateToken", 1, "鉴权中间件必须在位（本环走它）"),
    ("function withSaveLock", 1, "存档互斥锁必须在位（本环复用它）"),
    ("function dbGet", 1, "promise 化 db.get 必须在位"),
    ("function dbRun", 1, "promise 化 db.run 必须在位"),
    ("function dbAll", 1, "promise 化 db.all 必须在位"),
    ("const db = new sqlite3.Database(", 1, "db 连接必须在位（本环用 db.exec）"),
    ("const nowIso = () => new Date().toISOString();", 1, "nowIso 必须在位"),
    ("const SWORN_MIN = 2, SWORN_MAX = 5;", 1, "结义下限常量必须在位（本环引用）"),
    ("function rateLimit(", 1, "限流中间件必须在位"),
    ("app.post('/api/save', authenticateToken", 1, "玩家存档端点必须在位（本环不得动）"),
    ("app.post('/api/gm/players/:id/reset-save', authenticateGM", 1, "GM 重置存档端点必须在位（本环不得动）"),
]

# 冻结基线（打补丁前统计，打完后必须不变）
BASE_NEEDLES = ["DELETE FROM users", "DELETE FROM refresh_tokens", "res.status(403",
                "require(", "setInterval(", "PRAGMA",
                "DELETE FROM sects", "DELETE FROM chat_messages"]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-039 自服清档环")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：已打过本环
    if ("/api/character/reset" in src) or (MARK in src):
        print("[SKIP] source looks already patched（已含 /api/character/reset 或 %s）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 3) 锚点计数 + 自毁防线（插入式必须把锚点原文带进 new）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)
        if old not in new:
            fail("%s 自毁防线：new 未包含锚点原文 ⇒ 锚点行会被整段删除（不是插入）" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    gates = [
        # ---- 本环改动 ----
        ("R39 端点就位（带鉴权）", "app.post('/api/character/reset', authenticateToken", 1),
        ("R39 限流 key 就位", "keyFn: (req: any) => 'chreset:'", 1),
        ("R39 主清档函数就位", "function r039PurgeCharacter(", 1),
        ("R39 语句表函数就位", "function r039PurgeStatements(", 1),
        ("R39 社交修复函数就位", "async function r039SocialRepair(", 1),
        ("R39 事务 BEGIN IMMEDIATE（带分号）", "BEGIN IMMEDIATE;", 1),
        ("R39 事务 COMMIT（带分号）", "COMMIT;", 1),
        ("R39 旧无分号 BEGIN 已清零", "'BEGIN IMMEDIATE'", 0),
        ("R39 事务 COMMIT（带分号）", "lines.push('COMMIT;')", 1),
        ("R39 失败回滚 ROLLBACK", "db.run('ROLLBACK'", 1),
        ("R39 走 db.exec 单脚本", "db.exec(lines.join('\\n')", 1),
        ("R39 复用 saveLock", "withSaveLock(uid, () => new Promise<{ ok: boolean; error?: string }>", 1),
        # ---- 点名表确实在删除清单里 ----
        ("R39 清单含 saves", "['saves', 'user_id']", 1),
        ("R39 清单含 rankings", "['rankings', 'user_id']", 1),
        ("R39 清单含 player_titles(称号)", "['player_titles', 'user_id']", 1),
        ("R39 清单含 stats_daily(统计)", "['stats_daily', 'player_id']", 1),
        ("R39 清单含 wudao(心法)", "['wudao', 'player_id']", 1),
        ("R39 清单含 achievement_claimed(成就)", "['achievement_claimed', 'user_id']", 1),
        ("R39 清单含 player_gongfa(功法)", "['player_gongfa', 'player_id']", 1),
        ("R39 清单含 pets", "['pets', 'player_id']", 1),
        ("R39 清单含 spirit_farm", "['spirit_farm', 'player_id']", 1),
        ("R39 清单含 mail", "['mail', 'user_id']", 1),
        ("R39 清单含 sect_members(退宗)", "['sect_members', 'user_id']", 1),
        ("R39 清单含 sworn_members(退结义)", "['sworn_members', 'user_id']", 1),
        ("R39 双向删 friendships", "['friendships', 'user_id = ? OR friend_id = ?']", 1),
        ("R39 双向删 mentorships", "['mentorships', 'mentor_id = ? OR apprentice_id = ?']", 1),
        ("R39 删纪事点赞", "DELETE FROM chronicle_praise WHERE user_id = ? OR entry_id IN", 1),
        ("R39 删道侣宴席", "DELETE FROM couple_feasts WHERE couple_id IN", 1),
        ("R39 退宗(删成员行)", "DELETE FROM ' + pair[0] + ' WHERE ' + pair[1] + ' = ?", 1),
        # ---- 冻结：账号 / 登录态 / 共享表不得被本环删除 ----
        ("冻结 不删 users", "DELETE FROM users", base["DELETE FROM users"]),
        ("冻结 不删 refresh_tokens", "DELETE FROM refresh_tokens", base["DELETE FROM refresh_tokens"]),
        ("冻结 不删 active_sessions", "DELETE FROM active_sessions", 0),
        ("冻结 不删 titles 字典", "DELETE FROM titles", 0),
        ("冻结 不删 gongfa 字典", "DELETE FROM gongfa", 0),
        ("冻结 不删 sects 表", "DELETE FROM sects", base["DELETE FROM sects"]),
        ("冻结 不删 chat_messages", "DELETE FROM chat_messages", base["DELETE FROM chat_messages"]),
        ("冻结 不删 worldboss", "DELETE FROM worldboss", 0),
        ("冻结 不删 season_archives", "DELETE FROM season_archives", 0),
        ("冻结 不删 sect_ledger", "DELETE FROM sect_ledger", 0),
        # ---- 红线 ----
        ("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]),
        ("红线 未新增 require(", "require(", base["require("]),
        ("红线 未新增 setInterval", "setInterval(", base["setInterval("]),
        ("红线 未新增 PRAGMA", "PRAGMA", base["PRAGMA"]),
        # ---- 基线端点仍在（只做加法）----
        ("基线 GM reset-save 仍在", "app.post('/api/gm/players/:id/reset-save', authenticateGM", 1),
        ("基线 玩家存档端点仍在", "app.post('/api/save', authenticateToken", 1),
        ("基线 GM 删号端点仍在", "app.delete('/api/gm/players/:id', authenticateGM", 1),
        # ---- 幂等标记 ----
        ("R39 幂等标记就位", "[r039reset] R-039", 1),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-42s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 7) 语义自证：SQL 里除 uid 外无外部输入；users/登录态未被删
    sem_ok = (
        out.count("app.post('/api/character/reset', authenticateToken") == 1
        and out.count("DELETE FROM users") == base["DELETE FROM users"]
        and out.count("DELETE FROM refresh_tokens") == base["DELETE FROM refresh_tokens"]
        and "const uid = Math.floor(Number(userId));" in out
        and "if (!Number.isFinite(uid) || uid <= 0) return Promise.resolve({ ok: false, error: 'bad_user' });" in out
    )
    ok = ok and sem_ok
    print("  [%s] %-42s endpoints=%d users_del=%d"
          % ("OK" if sem_ok else "FAIL", "R39 语义自证(uid 校验 / 账号不删)",
             out.count("app.post('/api/character/reset', authenticateToken"), out.count("DELETE FROM users")))

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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r039reset-", suffix=".tmp")
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
