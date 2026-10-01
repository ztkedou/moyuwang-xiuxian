# -*- coding: utf-8 -*-
r"""
srv_patch_offline2.py -- R-021「离线窗口锚点改用真实离开时刻」服务端环（offline2）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回；`--check` 只校验不写。
  目标文件 = `srv/index_v28.ts`（线上 node --experimental 运行的那份）。
  链序：**无前置依赖**（只碰 saves 迁移 / /api/session/* / /api/offline/*），
  建议挂在链尾，且必须晚于 srv_patch_session.py（本环在其 session 区块后新增路由）。

问题原文（诊断报告 报告_bug诊断.md §R-021）
--------------------------------------------------------------------------
  「挂机收益面板恒为 0（可领取=否 + 已封顶=否）」
  根因：`/api/offline/report|claim` 的离线窗口锚点 = `saves.updated_at`，而客户端每 10s
  自动存档（心跳存档，bundle `setInterval(...,1e4)`）都会把 `updated_at` 刷成"现在"
  ⇒ 窗口恒 ≈10s < `OFFLINE_MIN_MS`(5min) ⇒ 全 0。
  反证：直连 `GET /api/offline/report`（无客户端在跑）返回 windowMs=1325954 / expGain=11654
  / claimable=true；线上 economy_ledger 的 save_freq 间隔恰好 10s。

改法（5 处，锚点互不重叠）
--------------------------------------------------------------------------
  E1  saves 迁移：新增 `last_seen_at` / `last_resume_at`（INTEGER 毫秒，NULL=未知）。
  E2  新增纯函数 `offlineAnchor()` + `POST /api/session/presence`（away/back 事件源）。
  E3  `/api/offline/report`：SELECT 补两列 + 锚点改走 `offlineAnchor()`。
  E4  `/api/offline/claim`：同上（预览与领取必须同口径）。
  E5  report 响应体补只读诊断字段 `anchorSource`。

★ 红线（违反会打坏玩家收益）
--------------------------------------------------------------------------
  · **只改「离线时长」的判定**：
      - `offlineRewards()`（expGain / stonesGain 公式）**一行未动**；
      - `offlineWindow()`（起点= max(上次存档, 已领截止)；时长= now-start）**一行未动**；
      - `OFFLINE_RATE_*` / `OFFLINE_CAP_*` / `OFFLINE_STONE_RATIO` / `OFFLINE_MIN_MS` 常量未动；
      - `hasMonthCard()` / `offlineCapHours()` / `offlineRatePerHour()` / 活动倍率 / 师徒加成未动；
      - `/api/save` 的 `settleSaveEconV2()` / `calcOfflineGainV2()`（E2 配额与钳制）未动；
      - 入账路径 `updatePlayerSave()` 与 `offline_claimed_until` 守卫语句未动。
  · 锚点取值为**服务端权威**：`away` 事件写入的是「上报那一刻本行的 updated_at」，
    客户端只能触发事件、不能自带时间戳 ⇒ 无法伪造离线时长（不引入新的刷分面）。
  · `last_seen_at` 缺失 / 已被 `offline_claimed_until` 覆盖 ⇒ **逐位回落旧口径 updated_at**，
    老客户端（不报 presence）与崩溃未上报场景行为与改前完全一致。

客户端配套
--------------------------------------------------------------------------
  `yl_offline2_ext.py`：visibilitychange(hidden) / pagehide / beforeunload 上报 away，
  可见 + 启动上报 back（顺带修 R-020 灵石下调日志文案/等级）。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ E1 迁移：新增两列

E1_OLD = """          if (!rows.some((r: any) => r.name === 'econ_win_stone')) safeAddColumn('saves', 'econ_win_stone', 'ALTER TABLE saves ADD COLUMN econ_win_stone INTEGER NOT NULL DEFAULT 0');
        }
      });"""

E1_NEW = """          if (!rows.some((r: any) => r.name === 'econ_win_stone')) safeAddColumn('saves', 'econ_win_stone', 'ALTER TABLE saves ADD COLUMN econ_win_stone INTEGER NOT NULL DEFAULT 0');
          // ★ R-021（offline2 环）：真实「离开 / 回来」时刻（毫秒，NULL=未知）。
          //   last_seen_at ：客户端在 visibilitychange(hidden)/pagehide/beforeunload 上报离开；
          //                  服务端落的是**上报那一刻本行的 updated_at**（服务端权威时间轴，
          //                  客户端只能触发事件、不能自带时间戳 ⇒ 无法伪造离线时长）。
          //   last_resume_at：客户端可见 / 启动时上报回来（Date.now()），用于给离线段封口。
          //   二者只服务 /api/offline/report|claim 的**离线窗口锚点**，不参与任何收益公式。
          if (!rows.some((r: any) => r.name === 'last_seen_at')) safeAddColumn('saves', 'last_seen_at', 'ALTER TABLE saves ADD COLUMN last_seen_at INTEGER');
          if (!rows.some((r: any) => r.name === 'last_resume_at')) safeAddColumn('saves', 'last_resume_at', 'ALTER TABLE saves ADD COLUMN last_resume_at INTEGER');
        }
      });"""

# ============================================================ E2 锚点纯函数 + presence 路由

E2_OLD = "// ── Y3A 离线收益报告：按上次存档(saves.updated_at)到当前的离线时长结算收益（修为+灵石分项）──"

E2_NEW = """// ─────────────────────────────────────────────────────────
// ★ R-021（offline2 环）离线窗口锚点修正
//   旧口径：锚点 = saves.updated_at。而客户端每 10s 自动存档（心跳存档）都会刷新 updated_at，
//     于是「挂机 / 离开」期间窗口恒 ≈10s < OFFLINE_MIN_MS(5min) ⇒ 面板恒 0（真 bug）。
//   新口径：优先取客户端上报的「真实离开时刻」last_seen_at（心跳存档不再能移动锚点）；
//     缺失 / 已被领取覆盖时**逐位回落**旧口径 updated_at —— 老客户端零行为变更。
//   ★ 红线：本环只改「离线时长」的判定。offlineRewards()（expGain/stoneGain 公式）、
//     offlineWindow() 本体、OFFLINE_* 常量、月卡判定、活动/师徒倍率、入账与钳制逻辑一行未动。
// ─────────────────────────────────────────────────────────
// 离线窗口锚点（纯函数）：返回 { anchorMs, endMs, source }
//   · last_seen_at 有效条件：非空、且尚未被 offline_claimed_until 覆盖（该段还没领过）。
//     → 窗口 = [max(last_seen_at, claimed_until), endMs]
//   · 无效 / 缺失 → 回落 updated_at，窗口末端 = nowMs（与改前逐位一致）
//   · endMs：已上报「回来」且晚于离开 → 用 last_resume_at 封口（离线段冻结，不随在线时长增长）；
//            否则 = nowMs（玩家仍在离线中，窗口自然增长）
function offlineAnchor(
  updatedAtMs: number | null, lastSeenAtMs: unknown, lastResumeAtMs: unknown,
  claimedUntilMs: unknown, nowMs: number
): { anchorMs: number | null; endMs: number; source: string } {
  const u = (updatedAtMs != null && Number.isFinite(updatedAtMs)) ? updatedAtMs : null;
  const lRaw = Number(lastSeenAtMs);
  const l = (lastSeenAtMs != null && Number.isFinite(lRaw) && lRaw > 0) ? lRaw : null;
  const rRaw = Number(lastResumeAtMs);
  const r = (lastResumeAtMs != null && Number.isFinite(rRaw) && rRaw > 0) ? rRaw : null;
  const cl = (claimedUntilMs != null && Number.isFinite(Number(claimedUntilMs))) ? Number(claimedUntilMs) : 0;
  if (l != null && l > cl) {
    const end = (r != null && r > l) ? r : nowMs;
    return { anchorMs: Math.max(l, cl), endMs: end, source: 'last_seen_at' };
  }
  return { anchorMs: u, endMs: nowMs, source: 'updated_at' };
}

// POST /api/session/presence —— 客户端上报「离开 / 回来」（R-021 锚点事件源）
//   body { state: 'away' | 'back' }
//   away：last_seen_at = 本行当前 updated_at（服务端权威；客户端只能触发，不能带时间戳）
//   back：last_resume_at = Date.now()
// 幂等、无副作用：不写存档、不记账、不影响经济；尚未建角（无行）直接 ok。
app.post('/api/session/presence', authenticateToken, async (req: any, res: any) => {
  try {
    const st = req.body && req.body.state;
    if (st !== 'away' && st !== 'back') return res.status(400).json({ error: 'state must be away|back' });
    if (st === 'away') {
      const row: any = await dbGet('SELECT updated_at FROM saves WHERE user_id = ?', [req.user.id]);
      const at = parseDbTimeMs(row && row.updated_at);
      if (row && at != null) await dbRun('UPDATE saves SET last_seen_at = ? WHERE user_id = ?', [at, req.user.id]);
    } else {
      await dbRun('UPDATE saves SET last_resume_at = ? WHERE user_id = ?', [Date.now(), req.user.id]);
    }
    res.json({ ok: true, state: st });
  } catch (e: any) {
    console.error('session presence error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

// ── Y3A 离线收益报告：按上次存档(saves.updated_at)到当前的离线时长结算收益（修为+灵石分项）──"""

# ============================================================ E3 report：SELECT 补列 + 锚点

E3A_OLD = "db.get('SELECT save_data, updated_at, offline_claimed_until, month_card_until FROM saves WHERE user_id = ?', [req.user.id], async (err: any, row: any) => {"
E3A_NEW = "db.get('SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at FROM saves WHERE user_id = ?', [req.user.id], async (err: any, row: any) => {"

E3B_OLD = """    const win = offlineWindow(parseDbTimeMs(row.updated_at), row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, nowMs);
    const rw = win ? offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour) : null;"""

E3B_NEW = """    // ★ R-021：锚点优先取「真实离开时刻」last_seen_at（心跳存档不再刷新它）；
    //   缺失 / 已领覆盖时逐位回落 updated_at。offlineWindow/offlineRewards 本体未动。
    const ylAnc = offlineAnchor(parseDbTimeMs(row.updated_at), row.last_seen_at, row.last_resume_at, row.offline_claimed_until, nowMs);
    const win = offlineWindow(ylAnc.anchorMs, row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, ylAnc.endMs);
    const rw = win ? offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour) : null;"""

# ============================================================ E4 claim：SELECT 补列 + 锚点

E4A_OLD = "const row = await dbGet('SELECT save_data, updated_at, offline_claimed_until, month_card_until FROM saves WHERE user_id = ?', [userId]);"
E4A_NEW = "const row = await dbGet('SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at FROM saves WHERE user_id = ?', [userId]);"

E4B_OLD = """    const win = offlineWindow(parseDbTimeMs(row.updated_at), row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, nowMs);
    if (!win) return res.status(409).json({ error: '暂无可领的离线收益' });"""

E4B_NEW = """    // ★ R-021：与 /api/offline/report 同一锚点口径（预览与领取必须一致，否则出现"看得到领不到"）
    const ylAnc = offlineAnchor(parseDbTimeMs(row.updated_at), row.last_seen_at, row.last_resume_at, row.offline_claimed_until, nowMs);
    const win = offlineWindow(ylAnc.anchorMs, row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, ylAnc.endMs);
    if (!win) return res.status(409).json({ error: '暂无可领的离线收益' });"""

# ============================================================ E5 report 响应体补诊断字段

E5_OLD = """      from: win ? win.startMs : null,
      windowMs: win ? win.windowMs : 0,"""

E5_NEW = """      from: win ? win.startMs : null,
      windowMs: win ? win.windowMs : 0,
      anchorSource: ylAnc.source, // R-021 只读诊断：last_seen_at=用真实离开时刻 / updated_at=回落旧口径
      anchorAt: ylAnc.anchorMs,   // R-021 只读诊断：实际锚点毫秒
      windowEndAt: ylAnc.endMs,   // R-021 只读诊断：窗口末端毫秒"""

# (标签, old, new, 该 edit 落地后必现且唯一的门禁串)
EDITS = [
    ('E1 saves 迁移：last_seen_at / last_resume_at', E1_OLD, E1_NEW,
     "safeAddColumn('saves', 'last_seen_at', 'ALTER TABLE saves ADD COLUMN last_seen_at INTEGER')"),
    ('E2 offlineAnchor + /api/session/presence',     E2_OLD, E2_NEW,
     'function offlineAnchor('),
    ('E3a report SELECT 补两列',                     E3A_OLD, E3A_NEW,
     'last_seen_at, last_resume_at FROM saves WHERE user_id = ?\', [req.user.id]'),
    ('E3b report 锚点改走 offlineAnchor',            E3B_OLD, E3B_NEW,
     'const win = offlineWindow(ylAnc.anchorMs, row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, ylAnc.endMs);\n    const rw = win'),
    ('E4a claim SELECT 补两列',                      E4A_OLD, E4A_NEW,
     'last_seen_at, last_resume_at FROM saves WHERE user_id = ?\', [userId]'),
    ('E4b claim 锚点改走 offlineAnchor',             E4B_OLD, E4B_NEW,
     "const win = offlineWindow(ylAnc.anchorMs, row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, ylAnc.endMs);\n    if (!win) return res.status(409).json({ error: '暂无可领的离线收益' });"),
    ('E5 report 响应体补 anchorSource',              E5_OLD, E5_NEW,
     'anchorSource: ylAnc.source,'),
]

REQUIRES = [
    ("app.post('/api/session/heartbeat'", 1, "session 环（srv_patch_session.py）必须先跑过"),
    ("const SESSION_STALE_MS = 60000;", 1, "session 环标志常量在位"),
    ("function offlineWindow(", 1, "离线窗口原语在位（本环不改它）"),
    ("function offlineRewards(", 1, "离线收益公式在位（本环不改它）"),
    ("const OFFLINE_MIN_MS = 5 * 60 * 1000;", 1, "离线门槛常量在位（本环不改它）"),
    ("function parseDbTimeMs(", 1, "DB 时间解析原语在位"),
    ("app.get('/api/offline/report'", 1, "离线报告端点唯一"),
    ("app.post('/api/offline/claim'", 1, "离线领取端点唯一"),
]

# 红线：这些串在改前/改后必须逐字不变（公式与常量本体）
FROZEN = [
    ('冻结 offlineRewards 公式行', 'const expGain = enough ? Math.max(0, Math.min(Math.floor(slot * rate * effHours), slot - cur)) : 0;'),
    ('冻结 灵石分项公式',          'const stonesGain = Math.floor(expGain * OFFLINE_STONE_RATIO);'),
    ('冻结 门槛判定',              'const enough = (Number(windowMs) || 0) >= OFFLINE_MIN_MS;'),
    ('冻结 速率常量',              'const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;'),
    ('冻结 上限常量',              'const OFFLINE_CAP_HOURS_BASE = 8;'),
    ('冻结 灵石比例常量',          'const OFFLINE_STONE_RATIO = 0.1;'),
    ('冻结 窗口原语',              'const startMs = Math.max(Number(lastSaveMs), cl);'),
    ('冻结 领取守卫推进',          "'UPDATE saves SET offline_claimed_until = ? WHERE user_id = ? AND (offline_claimed_until IS NULL OR offline_claimed_until < ?)'"),
    ('冻结 /api/save 未新增调用',  "app.post('/api/save', authenticateToken, rateLimit(", 1),
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

    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    if "last_seen_at" in src or "offlineAnchor" in src or "/api/session/presence" in src:
        fail("source looks already patched（已存在 last_seen_at / offlineAnchor / presence）")

    for name, old, new in [(e[0], e[1], e[2]) for e in EDITS]:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    out = src
    for name, old, new in [(e[0], e[1], e[2]) for e in EDITS]:
        out = out.replace(old, new, 1)

    # 红线：改前先记录「未被本环触碰」的敏感串基线
    base_save_route = src.count("app.post('/api/save', authenticateToken, rateLimit(")
    base_updatesave = src.count("function updatePlayerSave(")
    base_settle = src.count("function settleSaveEconV2(")
    base_calc = src.count("function calcOfflineGainV2(")

    gates = []
    for name, old, new, gneedle in EDITS:
        gates.append(('R21 %s 已应用' % name.split()[0], gneedle, 1, None))
    gates += [
        ('R21 迁移含 last_seen_at',    "safeAddColumn('saves', 'last_seen_at', 'ALTER TABLE saves ADD COLUMN last_seen_at INTEGER')", 1, None),
        ('R21 迁移含 last_resume_at',  "safeAddColumn('saves', 'last_resume_at', 'ALTER TABLE saves ADD COLUMN last_resume_at INTEGER')", 1, None),
        ('R21 锚点函数已注入',          'function offlineAnchor(', 1, None),
        ('R21 presence 路由已注入',     "app.post('/api/session/presence', authenticateToken, async (req: any, res: any) => {", 1, None),
        ('R21 away 取服务端 updated_at', "const at = parseDbTimeMs(row && row.updated_at);", 1, None),
        ('R21 away 写入 last_seen_at',  "await dbRun('UPDATE saves SET last_seen_at = ? WHERE user_id = ?', [at, req.user.id]);", 1, None),
        ('R21 back 写入 last_resume_at', "await dbRun('UPDATE saves SET last_resume_at = ? WHERE user_id = ?', [Date.now(), req.user.id]);", 1, None),
        ('R21 有效条件=未被领取覆盖',   'if (l != null && l > cl) {', 1, None),
        ('R21 回来封口',               'const end = (r != null && r > l) ? r : nowMs;', 1, None),
        ('R21 回落旧口径',             "return { anchorMs: u, endMs: nowMs, source: 'updated_at' };", 1, None),
        ('R21 report SELECT 补两列',   'SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at FROM saves WHERE user_id = ?', 2, None),
        ('R21 report/claim 同锚点',     'const win = offlineWindow(ylAnc.anchorMs, row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, ylAnc.endMs);', 2, None),
        ('R21 report 诊断字段',         'anchorSource: ylAnc.source,', 1, None),
    ]
    # 冻结（逐字不变）
    for item in FROZEN:
        if len(item) == 2:
            label, needle = item
            exp = src.count(needle)
        else:
            label, needle, exp = item
        act = out.count(needle)
        gates.append((label, needle, exp, act))

    ok = True
    for label, needle, exp, act_override in gates:
        act = out.count(needle) if act_override is None else act_override
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-44s actual=%s expect==%s" % ("OK" if good else "FAIL", label, act, exp))

    # 红线：入口未新增
    for label, needle, base_cnt in [
        ('红线 /api/save 路由未增', "app.post('/api/save', authenticateToken, rateLimit(", base_save_route),
        ('红线 updatePlayerSave 未增', 'function updatePlayerSave(', base_updatesave),
        ('红线 settleSaveEconV2 未增', 'function settleSaveEconV2(', base_settle),
        ('红线 calcOfflineGainV2 未增', 'function calcOfflineGainV2(', base_calc),
    ]:
        act = out.count(needle)
        good = (act == base_cnt)
        ok = ok and good
        print("  [%s] %-44s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, base_cnt))

    if not ok:
        fail("门禁未全绿，未写回")

    back = out
    for name, old, new in [(e[0], e[1], e[2]) for e in EDITS]:
        if back.count(new) != 1:
            fail("%s 的 new 出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))
    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".offline2-", suffix=".tmp")
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
