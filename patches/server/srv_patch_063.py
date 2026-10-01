# -*- coding: utf-8 -*-
r"""
srv_patch_063.py -- R-063 秘境：roguelike 地宫「单独算上限」（服务端环）

CLI 契约（与链上其余补丁一致，照 srv_patch_dungeon2.py 抄）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。

=========================================================================== 为什么服务端必须改
R-063：roguelike 地宫单独算上限（最低境界 3 次/日、其他相应增加）；原
[10,12,14,15,17,18,20] 表（R-032 用户拍板）归普通点选秘境。现状两条入口
（经典秘境 XM.handleEnterRealm / 地宫 yk.T，yl_dungeon085_ext 接线）共用
dungeon_tracker.count + dungeonCapForUser ⇒ 拆分必须落在权威账本上，否则
roguelike 第 4 次进地宫仍会吃普通点选的剩余次数（或反之），客户端改 = 死代码
（srv_patch_dungeon2 头部同一论证）。

=========================================================================== 改点（5 组）
  S1  dungeon_tracker 幂等加两列：rogue_count INTEGER NOT NULL DEFAULT 0、
      rogue_last_ts INTEGER（safeAddColumn 惯例，duplicate-column 容忍）。
  S2  新增 DUNGEON_ROGUE_CAP_BY_REALM = [3,5,7,8,10,11,13]（炼气 3 → 长生 13；
      递增节奏沿用普通表 +2,+2,+1,+2,+1,+2 总 +10、基座 3，任何境界严格低于
      普通点选 —— roguelike 单轮收益更高，次数保持更稀缺，AI 代决见拍板文件）
      + dungeonRogueCapForUser()（镜像 dungeonCapForUser；兜底 DUNGEON_DAILY_CAP=3
      恰为 rogue 最低档）。两侧同源：此表 ↔ 客户端 yl_063_ext.py 的 YLXW_DG_ROGUE_CAP。
  S3  GET /api/dungeon/status：SELECT 增取 rogue_count/rogue_last_ts，把
      dungeonRogueCapForUser 挂在**请求本地的 row.__rogueCap** 传给视图
      （不用模块级变量：并发请求会串号；dungeon2 门禁钉死 res.json 那行原样保留）。
  S4  dungeonStatusView：row 参数类型/返回类型扩 rogue 字段；return 增发
      rogueCount / rogueCap / rogueRemaining / rogueCdLeftMs / rogueCanEnter
      （rogueCap 取 row.__rogueCap，缺省兜底 DUNGEON_DAILY_CAP）。
  S5  POST /api/dungeon/entry：SELECT 增取两新列；body.mode==="rogue" 走独立
      判定/落库/403/200（dungeonEntryVerdict 原函数复用，CD 同为
      DUNGEON_ENTRY_CD_MS）；普通点选路径下行**一个字节不动**。

  ★ 403 纪律说明：本环新增恰好 1 处 res.status(403)（rogue 分支超限/过频），
    与该端点既有 403 语义完全同形 —— 客户端 YlxwDungeonEntryGate 对该端点用
    原始 fetch 且 403=拒绝回显（yl_dungeon085_ext 既有设计），不会误登出。
    门禁按 base403+1 断言（基线在打补丁前统计）。

=========================================================================== 链序
  ★ 必须排在 srv_patch_dungeon2.py **之后**（REQUIRES 断言 DUNGEON_CAP_BY_REALM
    已在位）。与 srv_patch_062.py（CD 30s→900s）零锚点交集，先后皆可；
    建议一并挂在 SRV_CHAIN 链尾（dungeon2 → 062 → 063）。
  ★ 本环所有锚点对 CD 常量值不敏感（只引用 DUNGEON_ENTRY_CD_MS 标识符），
    062 先打或后打均成立。

=========================================================================== 上游钉死面（全部逐字保留，门禁双保险）
  · const _dgCap = await dungeonCapForUser(req.user.id);   （dungeon2 "R32 entry 先算 cap" ==1）
  · const verdict = dungeonEntryVerdict(row?.count, …)；    （dungeon2 "R32 entry 传境界 cap" ==1）
  · res.json(dungeonStatusView(row, nowMs, await dungeonCapForUser(req.user.id)));（dungeon2 "R32 status 传境界 cap" ==1）
  · 普通点选 INSERT..ON CONFLICT / 403 体 / 200 体三段（dungeon2 E5 系列）逐字不动。
  · dungeonEntryVerdict / dungeonStatusView 默认参（cap/cdMs）不动（dungeon2 冻结面）。

=========================================================================== 客户端半边
  yl_063_ext.py：YLXW_DG_ROGUE_CAP 同表；入口带 mode 字段；StatusSync 镜像
  rogueCount/rogueCdLeftMs；YlxwDgCap 函数体改读 rogue 表。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ S1 幂等加列

S1_OLD = "  db.run(`CREATE INDEX IF NOT EXISTS idx_dungeon_anomaly ON dungeon_tracker(anomaly, date)`);"
S1_NEW = (
    "  db.run(`CREATE INDEX IF NOT EXISTS idx_dungeon_anomaly ON dungeon_tracker(anomaly, date)`);\n"
    "  // ── [r063] R-063 roguelike 地宫独立账本列（与普通点选 count/last_ts 分账；幂等加列）──\n"
    "  safeAddColumn('dungeon_tracker', 'rogue_count', 'ALTER TABLE dungeon_tracker ADD COLUMN rogue_count INTEGER NOT NULL DEFAULT 0');\n"
    "  safeAddColumn('dungeon_tracker', 'rogue_last_ts', 'ALTER TABLE dungeon_tracker ADD COLUMN rogue_last_ts INTEGER');"
)

# ============================================================ S2 rogue 上限表 + 取值函数

S2_OLD = "  } catch { return DUNGEON_DAILY_CAP; }\n}\n// 存档差值 → 秘境观测增量"

S2_NEW = """  } catch { return DUNGEON_DAILY_CAP; }
}
// ── [r063] R-063 roguelike 地宫「单独算上限」：独立上限表（与客户端 yl_063_ext.py 的
//   YLXW_DG_ROGUE_CAP 同源）。用户拍板口径：最低境界（炼气）一天 3 次、其他相应增加 ——
//   递增节奏沿用普通表（+2,+2,+1,+2,+1,+2，总 +10）、基座 3 ⇒ [3,5,7,8,10,11,13]，
//   任何境界都严格低于普通点选表 [10..20]（roguelike 单轮收益更高，次数保持更稀缺）。
const DUNGEON_ROGUE_CAP_BY_REALM: number[] = [3, 5, 7, 8, 10, 11, 13];
// 玩家境界 → roguelike 每日上限。未知境界 / 无存档 / 解析失败 → 兜底 DUNGEON_DAILY_CAP(=3，恰为 rogue 最低档)。
async function dungeonRogueCapForUser(userId: number): Promise<number> {
  try {
    const row: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row || !row.save_data) return DUNGEON_DAILY_CAP;
    const realm = JSON.parse(String(row.save_data))?.player?.realm;
    const idx = DUNGEON_REALM_ORDER.indexOf(String(realm || ''));
    if (!(idx >= 0)) return DUNGEON_DAILY_CAP;
    const cap = DUNGEON_ROGUE_CAP_BY_REALM[Math.min(idx, DUNGEON_ROGUE_CAP_BY_REALM.length - 1)];
    return Number.isFinite(cap) && cap > 0 ? cap : DUNGEON_DAILY_CAP;
  } catch { return DUNGEON_DAILY_CAP; }
}
// 存档差值 → 秘境观测增量"""

# ============================================================ S3 status 端点：取列 + rogueCap 挂 row

S3_OLD = """    const row = await dbGet('SELECT count, observed, adventure, last_ts, anomaly FROM dungeon_tracker WHERE player_id = ? AND date = ?', [req.user.id, bjDate(nowMs)]);
    res.json(dungeonStatusView(row, nowMs, await dungeonCapForUser(req.user.id)));"""

S3_NEW = """    const row = await dbGet('SELECT count, observed, adventure, last_ts, anomaly, rogue_count, rogue_last_ts FROM dungeon_tracker WHERE player_id = ? AND date = ?', [req.user.id, bjDate(nowMs)]);
    // [r063] rogueCap 挂在**请求本地**的 row 上传给视图（模块级变量在并发下会串号；
    //   dungeon2 门禁钉死下面这行 res.json 原样保留，只能走 row 携带）
    if (row) (row as any).__rogueCap = await dungeonRogueCapForUser(req.user.id);
    res.json(dungeonStatusView(row, nowMs, await dungeonCapForUser(req.user.id)));"""

# ============================================================ S4 dungeonStatusView 扩 rogue 字段

S4A_OLD = "  row: { count?: unknown; observed?: unknown; adventure?: unknown; last_ts?: unknown; anomaly?: unknown } | null | undefined,"
S4A_NEW = "  row: { count?: unknown; observed?: unknown; adventure?: unknown; last_ts?: unknown; anomaly?: unknown; rogue_count?: unknown; rogue_last_ts?: unknown; __rogueCap?: unknown } | null | undefined,"

S4B_OLD = """  lastTs: number | null; cdLeftMs: number; canEnter: boolean;
} {"""
S4B_NEW = """  lastTs: number | null; cdLeftMs: number; canEnter: boolean;
  rogueCount: number; rogueCap: number; rogueRemaining: number; rogueCdLeftMs: number; rogueCanEnter: boolean;
} {"""

S4C_OLD = """  const cdLeftMs = lastTs != null ? Math.max(0, cdMs - (nowMs - lastTs)) : 0;
  return {
    date: bjDate(nowMs),
    count, cap,
    remaining: Math.max(0, cap - count),
    observed, adventure,
    anomaly: dungeonAnomaly(count, observed) || Number(row?.anomaly) === 1,
    lastTs, cdLeftMs,
    canEnter: count < cap && cdLeftMs === 0,
  };"""

S4C_NEW = """  const cdLeftMs = lastTs != null ? Math.max(0, cdMs - (nowMs - lastTs)) : 0;
  // [r063] roguelike 独立账本字段（rogueCap 由 status 端点挂在 row.__rogueCap；缺省兜底 DUNGEON_DAILY_CAP）
  const rogueCount = Math.max(0, Math.floor(Number(row?.rogue_count) || 0));
  const rogueLastTs = row?.rogue_last_ts != null && Number.isFinite(Number(row.rogue_last_ts)) ? Number(row.rogue_last_ts) : null;
  const rogueCdLeftMs = rogueLastTs != null ? Math.max(0, cdMs - (nowMs - rogueLastTs)) : 0;
  const rogueCap = Math.max(1, Math.floor(Number((row as any)?.__rogueCap) || 0)) || DUNGEON_DAILY_CAP;
  return {
    date: bjDate(nowMs),
    count, cap,
    remaining: Math.max(0, cap - count),
    observed, adventure,
    anomaly: dungeonAnomaly(count, observed) || Number(row?.anomaly) === 1,
    lastTs, cdLeftMs,
    canEnter: count < cap && cdLeftMs === 0,
    rogueCount,
    rogueCap,
    rogueRemaining: Math.max(0, rogueCap - rogueCount),
    rogueCdLeftMs,
    rogueCanEnter: rogueCount < rogueCap && rogueCdLeftMs === 0,
  };"""

# ============================================================ S5 entry 端点：mode=rogue 分流（普通路径零改动）

S5_OLD = """      const row = await dbGet('SELECT count, last_ts FROM dungeon_tracker WHERE player_id = ? AND date = ?', [req.user.id, date]);
      const _dgCap = await dungeonCapForUser(req.user.id);"""

S5_NEW = """      const row = await dbGet('SELECT count, last_ts, rogue_count, rogue_last_ts FROM dungeon_tracker WHERE player_id = ? AND date = ?', [req.user.id, date]);
      // ── [r063] R-063 roguelike 地宫独立账本分流：body.mode==="rogue" 走
      //      rogue_count/rogue_last_ts + DUNGEON_ROGUE_CAP_BY_REALM，判定/落库/403/200
      //      在本分支内自洽结束；普通点选路径下行字节不动（dungeon2 环门禁钉死
      //      _dgCap / verdict / 普通插入 / 普通 403 / 普通 200 五处）。
      if (String((req.body && req.body.mode) || '') === 'rogue') {
        const _rCap = await dungeonRogueCapForUser(req.user.id);
        const rVerdict = dungeonEntryVerdict(row?.rogue_count, row?.rogue_last_ts != null ? Number(row.rogue_last_ts) : null, nowMs, _rCap);
        if (rVerdict.reason !== 'cd') {
          await dbRun(
            `INSERT INTO dungeon_tracker (player_id, date, count, observed, adventure, last_ts, anomaly, rogue_count, rogue_last_ts) VALUES (?, ?, 0, 0, 0, NULL, ?, ?, ?)
             ON CONFLICT(player_id, date) DO UPDATE SET
               rogue_count = excluded.rogue_count,
               rogue_last_ts = excluded.rogue_last_ts,
               anomaly = CASE WHEN excluded.rogue_count > ? THEN 1 ELSE anomaly END`,
            [req.user.id, date, rVerdict.count > DUNGEON_ANOMALY_THRESHOLD ? 1 : 0, rVerdict.count, nowMs, DUNGEON_ANOMALY_THRESHOLD]
          );
        }
        if (!rVerdict.allowed) {
          return res.status(403).json({
            ok: false,
            reason: rVerdict.reason,
            error: rVerdict.reason === 'cap' ? `今日地宫探索次数已用完（上限 ${_rCap} 次）` : '进入过于频繁，请稍候再试',
            count: rVerdict.count,
            cap: _rCap,
            remaining: Math.max(0, _rCap - rVerdict.count),
            retryAfterMs: rVerdict.retryAfterMs ?? 0,
            mode: 'rogue',
          });
        }
        return res.json({ ok: true, count: rVerdict.count, cap: _rCap, remaining: Math.max(0, _rCap - rVerdict.count), cdMs: DUNGEON_ENTRY_CD_MS, mode: 'rogue' });
      }
      const _dgCap = await dungeonCapForUser(req.user.id);"""

EDITS = [
    ("S1 dungeon_tracker 幂等加 rogue 两列", S1_OLD, S1_NEW),
    ("S2 rogue 上限表 + 取值函数",           S2_OLD, S2_NEW),
    ("S3 status 取列 + rogueCap 挂 row",     S3_OLD, S3_NEW),
    ("S4a 视图 row 参数类型扩列",            S4A_OLD, S4A_NEW),
    ("S4b 视图返回类型扩字段",               S4B_OLD, S4B_NEW),
    ("S4c 视图 return 增发 rogue 字段",      S4C_OLD, S4C_NEW),
    ("S5 entry mode=rogue 分流",             S5_OLD, S5_NEW),
]

# 前置依赖（本环只读这些串做自证，不改）
REQUIRES = [
    ("const DUNGEON_CAP_BY_REALM: number[] = [10, 12, 14, 15, 17, 18, 20];", 1,
     "srv_patch_dungeon2.py 必须已在本环之前（链序强制）"),
    ("const DUNGEON_REALM_ORDER: string[] = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];", 1,
     "dungeon2 的境界序必须在位（本环 rogue 表复用它）"),
    ("const DUNGEON_DAILY_CAP = 3;", 1, "0.8.5 DG 环的兜底常量必须在位（rogue 兜底恰为最低档）"),
    ("function dungeonEntryVerdict(", 1, "0.8.5 DG 环的判定函数必须在位（rogue 分支复用）"),
    ("function dungeonStatusView(", 1, "0.8.5 DG 环的状态视图必须在位"),
    ("function dbGet", 1, "promise 化 db.get 必须在位"),
    ("function dbRun", 1, "promise 化 db.run 必须在位"),
    ("const safeAddColumn = (table: string, col: string, ddl: string) => {", 1, "幂等加列助手必须在位"),
    ("app.use(express.json({ limit: '50mb' }));", 1, "body JSON 解析必须在位（rogue 分支读 req.body.mode）"),
    ("app.get('/api/dungeon/status'", 1, "status 端点唯一"),
    ("app.post('/api/dungeon/entry'", 1, "entry 端点唯一"),
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

    # 1) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 2) 幂等
    if "DUNGEON_ROGUE_CAP_BY_REALM" in src or "dungeonRogueCapForUser" in src:
        fail("source looks already patched（已存在 DUNGEON_ROGUE_CAP_BY_REALM / dungeonRogueCapForUser）")

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
        # ---- S1 ----
        ("R63 加列 rogue_count",      "safeAddColumn('dungeon_tracker', 'rogue_count', 'ALTER TABLE dungeon_tracker ADD COLUMN rogue_count INTEGER NOT NULL DEFAULT 0');", 1),
        ("R63 加列 rogue_last_ts",    "safeAddColumn('dungeon_tracker', 'rogue_last_ts', 'ALTER TABLE dungeon_tracker ADD COLUMN rogue_last_ts INTEGER');", 1),
        # ---- S2 ----
        ("R63 rogue 上限表 7 档",     "const DUNGEON_ROGUE_CAP_BY_REALM: number[] = [3, 5, 7, 8, 10, 11, 13];", 1),
        ("R63 rogue 表两端 3/13",     "[3, 5, 7, 8, 10, 11, 13]", 1),
        ("R63 rogue 取值函数已定义",  "async function dungeonRogueCapForUser(userId: number): Promise<number> {", 1),
        ("R63 rogue 无存档兜底=3",    "if (!row || !row.save_data) return DUNGEON_DAILY_CAP;", 2, "rogue 环新增 1 + dungeon2 原 1"),
        ("R63 rogue 未知境界兜底=3",  "if (!(idx >= 0)) return DUNGEON_DAILY_CAP;", 2, "同上"),
        # ---- S3 ----
        ("R63 status 取 rogue 列",    "SELECT count, observed, adventure, last_ts, anomaly, rogue_count, rogue_last_ts FROM dungeon_tracker", 1),
        ("R63 rogueCap 挂 row",       "if (row) (row as any).__rogueCap = await dungeonRogueCapForUser(req.user.id);", 1),
        # ---- S4 ----
        ("R63 视图 row 类型扩列",     "rogue_count?: unknown; rogue_last_ts?: unknown; __rogueCap?: unknown", 1),
        ("R63 视图返回类型扩字段",    "rogueCount: number; rogueCap: number; rogueRemaining: number; rogueCdLeftMs: number; rogueCanEnter: boolean;", 1),
        ("R63 视图增发 rogueCount",   "rogueCount,\n    rogueCap,", 1),
        ("R63 视图增发 rogueCd",      "rogueCdLeftMs,\n    rogueCanEnter: rogueCount < rogueCap && rogueCdLeftMs === 0,", 1),
        # ---- S5 ----
        ("R63 entry 取 rogue 列",     "SELECT count, last_ts, rogue_count, rogue_last_ts FROM dungeon_tracker", 1),
        ("R63 rogue 分流已建",        "if (String((req.body && req.body.mode) || '') === 'rogue') {", 1),
        ("R63 rogue verdict 复用",    "const rVerdict = dungeonEntryVerdict(row?.rogue_count, row?.rogue_last_ts != null ? Number(row.rogue_last_ts) : null, nowMs, _rCap);", 1),
        ("R63 rogue 落库 rogue 列",   "rogue_count = excluded.rogue_count,\n               rogue_last_ts = excluded.rogue_last_ts,", 1),
        ("R63 rogue 403 文案",        "`今日地宫探索次数已用完（上限 ${_rCap} 次）`", 1),
        ("R63 rogue 200 带 mode",     "return res.json({ ok: true, count: rVerdict.count, cap: _rCap, remaining: Math.max(0, _rCap - rVerdict.count), cdMs: DUNGEON_ENTRY_CD_MS, mode: 'rogue' });", 1),
        ("R63 entry 先判 rogue 再算普通 cap", "const _dgCap = await dungeonCapForUser(req.user.id);", 1),
        # ---- 冻结（本环不得回踩；dungeon2 钉死面逐字保留）----
        ("冻结 兜底常量 DUNGEON_DAILY_CAP=3", "const DUNGEON_DAILY_CAP = 3;", 1),
        ("冻结 dungeon2 普通上限表未动",      "const DUNGEON_CAP_BY_REALM: number[] = [10, 12, 14, 15, 17, 18, 20];", 1),
        ("冻结 verdict cap 分支未动",         "if (c >= cap) return { allowed: false, count: c + 1, reason: 'cap', retryAfterMs: 0 };", 1),
        ("冻结 普通点选 verdict 行未动",      "const verdict = dungeonEntryVerdict(row?.count, row?.last_ts != null ? Number(row.last_ts) : null, nowMs, _dgCap);", 1),
        ("冻结 status 视图 res.json 行未动",  "res.json(dungeonStatusView(row, nowMs, await dungeonCapForUser(req.user.id)));", 1),
        ("冻结 status 视图默认参未动",        "cap: number = DUNGEON_DAILY_CAP,\n  cdMs: number = DUNGEON_ENTRY_CD_MS", 1),
        ("冻结 普通 403 文案未动",            "`今日秘境次数已用完（上限 ${_dgCap} 次）`", 1),
        ("冻结 普通 200 体未动",              "res.json({ ok: true, count: verdict.count, cap: _dgCap, remaining: Math.max(0, _dgCap - verdict.count), cdMs: DUNGEON_ENTRY_CD_MS });", 1),
        ("冻结 普通点选落库语句未动",         "INSERT INTO dungeon_tracker (player_id, date, count, observed, adventure, last_ts, anomaly) VALUES (?, ?, ?, 0, 0, ?, ?)", 1),
        ("冻结 anomaly 阈值未动",             "const DUNGEON_ANOMALY_THRESHOLD = 25;", 1),
        # ---- 红线：403 恰 +1（rogue 分支，语义与该端点既有 403 同形）----
        ("红线 res.status(403) 恰 +1", "res.status(403", base403 + 1),
    ]
    ok = True
    for item in gates:
        if len(item) == 3:
            label, needle, exp = item
            why = ""
        else:
            label, needle, exp, why = item
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d expect==%d %s" % ("OK" if good else "FAIL", label, act, exp, why))

    if not ok:
        fail("门禁未全绿，未写回")

    # 6) 往返自证
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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r063-", suffix=".tmp")
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
