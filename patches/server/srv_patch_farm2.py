# -*- coding: utf-8 -*-
r"""
srv_patch_farm2.py -- R-019① 灵田「照料 2 小时冷却」（服务端环 farm2）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  链序：**必须排在 srv_patch_t5_crops.py 之后**（本环依赖其 FARM_TEND_COUNT /
  FARM_TEND_PER / FARM_TEND_CAP 与计次闸门形态），建议挂在链尾（第 24+ 环）。

需求原文
--------------------------------------------------------------------------
  「照料加 2 小时冷却（「之前说」说明之前提过但没做 —— 去查是否有遗留的半成品）」

半成品定位（逐字实证）
--------------------------------------------------------------------------
  · 策划口径：`docs/0.8.8-design/T5-灵田品种重构.md` §62
      「『照料』按物品单独计次、**每 2 小时 1 次**、每次略微增加收益」
    + §7-Q3 裁定 **(a) 每次 +2%、单田当日累计上限 +10%**。
  · 已落的一半（srv_patch_t5_crops.py T5.8/T5.9，链第 15 环）：
      FARM_TEND_PER=0.02 / FARM_TEND_CAP=0.10 / FARM_TEND_COUNT=12；
      tend 端点 `... SET tended=1, tend_count=tend_count+1 WHERE tend_count < 12`
      —— 当日 **12 次封顶**（12 × 2h = 24h，恰是「每 2 小时 1 次」的等价上限）。
  · **缺的正是「时间间隔」**：12 次可同一秒连点完，无 2h 间隔闸门。
    ⇒ 本环补：`farm_daily_care.last_tend_at` 列 + tend 端点 2h 冷却闸门
       + `/api/farm/status` 的 `slots[].care.tendReadyAt`（绝对 epoch ms）。

改点（5 处）
--------------------------------------------------------------------------
  E1  `farm_daily_care` 幂等加列 `last_tend_at INTEGER NOT NULL DEFAULT 0`
      （safeAddColumn，容忍 duplicate column name；与 tend_count 迁移同区）
  E2  常量 `FARM_TEND_CD_MS = 2 * 60 * 60 * 1000`
  E3  status 的 careRows SELECT 增读 `last_tend_at`
  E4  status 的 `care` 对象增 `tendReadyAt`
  E5  tend 端点：进入时校验冷却（未到 → 409 + cooldownMs/tendReadyAt）；
      成功写入时同时落 `last_tend_at = now`

★ 红线
--------------------------------------------------------------------------
  · 业务拒绝一律 **409**（客户端 `Xc()` 把 403 当会话失效强制登出 ⇒ 绝不 403）。
  · 冷却只**限制频率**，不改任何收益公式：`tendBonus = min(FARM_TEND_CAP,
    tend_count × FARM_TEND_PER)` 逐字不动 ⇒ 经济红线（满配 ×1.21 / 六田 117,612/日
    ≤ 150,000）零漂移。
  · 不新增网络/表；不改 farmHarvestOne / harvest/all / boost 任何路径。

客户端配套
--------------------------------------------------------------------------
  `yl_farm2_ext.py`：`YlxwFtTendCdMs(care)` 读 `care.tendReadyAt`，
  冷却期内灰置「照料」按钮并显示剩余；字段缺失恒 0 ⇒ 向后兼容零回归。
"""

import argparse
import io
import os
import re
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ E1 幂等加列 last_tend_at

E1_OLD = """  db.all("PRAGMA table_info(farm_daily_care)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'tend_count')) {
      safeAddColumn('farm_daily_care', 'tend_count', 'ALTER TABLE farm_daily_care ADD COLUMN tend_count INTEGER NOT NULL DEFAULT 0');
    }
  });"""

E1_NEW = """  db.all("PRAGMA table_info(farm_daily_care)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'tend_count')) {
      safeAddColumn('farm_daily_care', 'tend_count', 'ALTER TABLE farm_daily_care ADD COLUMN tend_count INTEGER NOT NULL DEFAULT 0');
    }
  });
  // ── R-019①（farm2 环）灵田照料 2 小时冷却落点：farm_daily_care.last_tend_at 的幂等迁移 ──
  //   口径（T5 §7-Q3 原文「每 2 小时 1 次」）：12 次/日封顶已由 t5_crops 落地，本列补「时间间隔」。
  //   last_tend_at = 该田当日**最近一次照料**的 epoch ms（0 = 今日未照料过）。
  //   幂等 safeAddColumn（容忍 duplicate column name；空库冷启动 / 重跑双安全）。
  db.all("PRAGMA table_info(farm_daily_care)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'last_tend_at')) {
      safeAddColumn('farm_daily_care', 'last_tend_at', 'ALTER TABLE farm_daily_care ADD COLUMN last_tend_at INTEGER NOT NULL DEFAULT 0');
    }
  });"""

# ============================================================ E2 常量

E2_OLD = "const FARM_TEND_COUNT = 12;"
E2_NEW = ("const FARM_TEND_COUNT = 12;\n"
          "// ★ R-019①（farm2 环）：照料冷却 2 小时（T5 §7-Q3「每 2 小时 1 次」）。\n"
          "//   只作频率闸门，不参与任何收益公式 ⇒ 满配 ×1.21 经济红线零漂移。\n"
          "const FARM_TEND_CD_MS = 2 * 60 * 60 * 1000;")

# ============================================================ E3 status SELECT

E3_OLD = "dbAll('SELECT slot, tended, boosted FROM farm_daily_care WHERE player_id = ? AND date = ?', [userId, bjDate(Date.now())]),"
E3_NEW = "dbAll('SELECT slot, tended, boosted, last_tend_at FROM farm_daily_care WHERE player_id = ? AND date = ?', [userId, bjDate(Date.now())]),"

# ============================================================ E4 care 对象

E4_OLD = "care: { date: today, tended: tended ? 1 : 0, boosted: boosted ? 1 : 0, pest },"
E4_NEW = ("care: { date: today, tended: tended ? 1 : 0, boosted: boosted ? 1 : 0, pest,\n"
          "          // ★ R-019①：照料冷却绝对就绪时刻（epoch ms；0 = 无冷却）。客户端 YlxwFtTendCdMs 消费。\n"
          "          tendReadyAt: (care && Number(care.last_tend_at) > 0) ? Number(care.last_tend_at) + FARM_TEND_CD_MS : 0 },")

# ============================================================ E5 tend 端点冷却闸门

E5_OLD = """    const r = await dbGet('SELECT id FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 0', [userId, slot]);
    if (!r) return res.status(409).json({ error: '该田空空如也，无需照料' });
    const today = bjDate(Date.now());"""

E5_NEW = """    const r = await dbGet('SELECT id FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 0', [userId, slot]);
    if (!r) return res.status(409).json({ error: '该田空空如也，无需照料' });
    const nowMs = Date.now();
    const today = bjDate(nowMs);
    // ★ R-019①（farm2 环）：2 小时照料冷却闸门（T5 §7-Q3「每 2 小时 1 次」）。
    //   读今日该田最近一次照料时刻；未到冷却直接 409（业务拒绝用 409，**绝不 403**）。
    const cdRow = await dbGet('SELECT last_tend_at FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]);
    const lastTendAt = Number(cdRow?.last_tend_at) || 0;
    if (lastTendAt > 0) {
      const readyAt = lastTendAt + FARM_TEND_CD_MS;
      const leftMs = readyAt - nowMs;
      if (leftMs > 0) {
        return res.status(409).json({
          error: `照料冷却中：还需 ${Math.ceil(leftMs / 60000)} 分钟（每 2 小时可照料 1 次）`,
          cooldownMs: leftMs, tendReadyAt: readyAt, tendCdMs: FARM_TEND_CD_MS,
        });
      }
    }"""

# ============================================================ E5b 成功写入落 last_tend_at

E5B_OLD = """      'INSERT INTO farm_daily_care (player_id, slot, date, tended, boosted, tend_count) VALUES (?, ?, ?, 1, 0, 1) ' +
      'ON CONFLICT(player_id, slot, date) DO UPDATE SET tended = 1, tend_count = tend_count + 1 WHERE tend_count < ?',
      [userId, slot, today, FARM_TEND_COUNT]"""

E5B_NEW = """      'INSERT INTO farm_daily_care (player_id, slot, date, tended, boosted, tend_count, last_tend_at) VALUES (?, ?, ?, 1, 0, 1, ?) ' +
      'ON CONFLICT(player_id, slot, date) DO UPDATE SET tended = 1, tend_count = tend_count + 1, last_tend_at = ? WHERE tend_count < ?',
      [userId, slot, today, nowMs, nowMs, FARM_TEND_COUNT]"""

EDITS = [
    ('E1 farm_daily_care 加 last_tend_at 列', E1_OLD, E1_NEW),
    ('E2 常量 FARM_TEND_CD_MS=2h',            E2_OLD, E2_NEW),
    ('E3 status 读 last_tend_at',             E3_OLD, E3_NEW),
    ('E4 status care 下发 tendReadyAt',       E4_OLD, E4_NEW),
    ('E5 tend 端点 2h 冷却闸门',              E5_OLD, E5_NEW),
    ('E5b tend 成功写 last_tend_at',          E5B_OLD, E5B_NEW),
]

# 链序依赖（取自 0.8.9 t5_crops 后的实测计数）
REQUIRES = [
    ("const FARM_TEND_COUNT = 12;", 1, "t5_crops 环必须先跑过（本环为其后继）"),
    ("const FARM_TEND_PER = 0.02;", 1, "t5_crops 环必须先跑过"),
    ("const FARM_TEND_CAP = 0.10;", 1, "t5_crops 环必须先跑过"),
    ("ON CONFLICT(player_id, slot, date) DO UPDATE SET tended = 1, tend_count = tend_count + 1 WHERE tend_count < ?", 1,
     "t5_crops 计次闸门必须在位（本环在其上补时间间隔）"),
    ("const safeAddColumn = (table: string, col: string, ddl: string) => {", 1, "rankingmig 环必须先跑过（幂等加列原语）"),
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
    if "last_tend_at" in src or "FARM_TEND_CD_MS" in src:
        fail("source looks already patched（已存在 last_tend_at / FARM_TEND_CD_MS）")

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
    base403 = src.count('res.status(403')
    gates = [
        # ---- E1 迁移 ----
        ('R19 加列 last_tend_at',           "ALTER TABLE farm_daily_care ADD COLUMN last_tend_at INTEGER NOT NULL DEFAULT 0", 1, None),
        ('R19 加列走 safeAddColumn',        "safeAddColumn('farm_daily_care', 'last_tend_at'", 1, None),
        ('R19 原 tend_count 迁移未动',      "safeAddColumn('farm_daily_care', 'tend_count'", 1, None),
        # ---- E2 常量 ----
        ('R19 冷却常量 2h',                 'const FARM_TEND_CD_MS = 2 * 60 * 60 * 1000;', 1, None),
        ('R19 计次常量未动',                'const FARM_TEND_COUNT = 12;', 1, None),
        ('R19 单次加成未动',                'const FARM_TEND_PER = 0.02;', 1, None),
        ('R19 当日封顶未动',                'const FARM_TEND_CAP = 0.10;', 1, None),
        # ---- E3/E4 status ----
        ('R19 status 读 last_tend_at',      "dbAll('SELECT slot, tended, boosted, last_tend_at FROM farm_daily_care WHERE player_id = ? AND date = ?'", 1, None),
        ('R19 status 下发 tendReadyAt',     'tendReadyAt: (care && Number(care.last_tend_at) > 0) ? Number(care.last_tend_at) + FARM_TEND_CD_MS : 0', 1, None),
        # ---- E5 tend 端点 ----
        ('R19 冷却读上次照料时刻',          "dbGet('SELECT last_tend_at FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?'", 1, None),
        ('R19 冷却拒绝走 409',              'if (leftMs > 0) {', 1, None),
        ('R19 冷却拒绝带剩余',              'cooldownMs: leftMs, tendReadyAt: readyAt, tendCdMs: FARM_TEND_CD_MS,', 1, None),
        ('R19 冷却文案含 2 小时',           '（每 2 小时可照料 1 次）', 1, None),
        ('R19 成功写 last_tend_at',         'DO UPDATE SET tended = 1, tend_count = tend_count + 1, last_tend_at = ? WHERE tend_count < ?', 1, None),
        ('R19 插入值含 nowMs×2',            '[userId, slot, today, nowMs, nowMs, FARM_TEND_COUNT]', 1, None),
        # ---- 冻结（本环不得回踩）----
        ('冻结 计次闸门条件未动',           'tend_count + 1, last_tend_at = ? WHERE tend_count < ?', 1, None),
        ('冻结 照料收益公式未动',           'tendBonus: Math.min(FARM_TEND_CAP, tendCount * FARM_TEND_PER),', 1, None),
        ('冻结 farmHarvestMods 仍读 tend_count', "dbGet('SELECT tended, tend_count FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?'", 1, None),
        ('冻结 一键收未动',                 "app.post('/api/farm/harvest/all'", 1, None),
        ('冻结 boost 端点未动',             "app.post('/api/farm/boost'", 1, None),
        ('冻结 plant 端点未动',             "app.post('/api/farm/plant'", 1, None),
        ('冻结 照料端点唯一',               "app.post('/api/farm/tend'", 1, None),
    ]
    ok = True
    for g in gates:
        label, needle, exp = g[0], g[1], g[2]
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 6) 红线：不得新增 403
    a403 = out.count('res.status(403')
    good = (a403 == base403)
    ok = ok and good
    print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", '红线 未新增 res.status(403)', a403, base403))

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

    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".farm2-", suffix=".tmp")
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
