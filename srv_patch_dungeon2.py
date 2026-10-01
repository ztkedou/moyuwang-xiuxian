# -*- coding: utf-8 -*-
r"""
srv_patch_dungeon2.py -- R-032 秘境「每日上限随等阶」（服务端环 dungeon2）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  无前置依赖（本环只碰 DUNGEON_* 常量与 /dungeon 两个端点，不依赖别的环）。

=========================================================================== 为什么服务端必须改
前一个执行者写的「需服务端+客户端同改」是**对的**。任务书里「服务端无需改动」的判断
不成立 —— 你查的 `srv/index.new.ts:1541` 的 `const cSR = Math.ceil(mins*4)+6` 确实是
**capExp 经济配额**（不是次数闸门），但**每日次数硬闸门在别处**：

  · `POST /api/dungeon/entry` → `dungeonEntryVerdict(...)`：
        if (c >= cap) return { allowed:false, reason:'cap' }  →  403
    其中 `cap` 默认 = `DUNGEON_DAILY_CAP = 3`。
  · `yl_dungeon085_ext.py`（已接线，V28_MODULES 第 15 位）把**两条入口**都接到该端点，
    且 **403 即拒绝**（经典秘境 `if(!_ylg.ok){…return!1}` / 地宫 `if(!_ylg.ok){…return}`）。
    ⇒ 只改客户端 cap，玩家第 4 次进秘境仍被服务端 403 挡回 ⇒ **客户端改 = 死代码**。

=========================================================================== 改点（5 处）
  E1  新增境界→上限映射（`DUNGEON_CAP_BY_REALM`）与 `dungeonCapForUser(userId)`
  E2  `DUNGEON_ANOMALY_THRESHOLD` 10 → 25（合法上限 20 > 10，否则满次数的长生玩家
      会被误标 anomaly=1 冲进 GM 异常清单）
  E3  `GET /dungeon/status`：把境界映射后的 cap 传给 `dungeonStatusView`（第 3 参）
      ⇒ 客户端 v2811a 信息条「今日秘境次数 x/cap」显示正确上限
  E4  `POST /dungeon/entry`：把境界映射后的 cap 传给 `dungeonEntryVerdict`（第 4 参）
  E5  该端点 403 / 200 响应体里的 `DUNGEON_DAILY_CAP` 一律改用本次算出的 `_dgCap`

  ★ `DUNGEON_DAILY_CAP = 3` **保留**作未知境界 / 无存档 / 解析失败的兜底
    （与 0.8.5 现状一致，零行为漂移）。
  ★ `dungeonStatusView` / `dungeonEntryVerdict` 的**默认参数**（= DUNGEON_DAILY_CAP）
    与函数体一行未动 —— 本环只在调用点传参。
  ★ `/api/dungeon/anomalies`（GM 清单）的 `cap` 字段未动（多玩家混表，单值无意义）。

=========================================================================== 上限表（与客户端 yl_dungeon2_ext.py 同一张表）
  用户最新拍板：**炼气基数 10 次、长生 20 次**，中间 5 档递增。
  `[10, 12, 14, 15, 17, 18, 20]`（6 段总增 10 ⇒ 平均 1.67/档，取整后严格单调递增）。
  ★ 与策划案《策划_R032秘境配平与R019R023口径.md》定档 D13-A
    （`min(20, 3+3×境界序)` = `[3,6,9,12,15,18,20]`，炼气 3 起）**不一致** ——
    以用户最新拍板为准；两侧唯一改点在此常量与客户端 `YLXW_DG_CAP`。

=========================================================================== 红线
  · **不新增任何 res.status(403)**（403 语义在本环完全不变，只是 cap 变大）。
  · 不改 `srEach` / `cSR` 经济配额（策划 §1.6：只松 9.8%，不引入新夹取风险）。
  · 不改 `DUNGEON_ENTRY_CD_MS`（冷却时长由客户端 `YLXW_DG_CD_MS` 与服务端常量同源；
    本环**不改**它 —— 若要把 30s 抬到 5 分钟，是另一条独立改点，见文件末尾「待办」）。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ E1 境界→上限映射 + 取值函数

E1_OLD = "const DUNGEON_ANOMALY_THRESHOLD = 10; // 单日 count 或 observed 超此值 → anomaly=1（GM /api/dungeon/anomalies 可查）"

E1_NEW = """const DUNGEON_ANOMALY_THRESHOLD = 25; // 单日 count 或 observed 超此值 → anomaly=1（GM /api/dungeon/anomalies 可查）
// ── R-032（dungeon2 环）每日上限**按境界**下发：客户端 yl_dungeon2_ext.py 用同一张表 ──
//   用户最新拍板：炼气基数 10 次、长生 20 次，中间 5 档递增（[10,12,14,15,17,18,20]）。
//   ★ 与策划案 D13-A（min(20,3+3×境界序)=[3,6,9,12,15,18,20]，炼气 3 起）不一致 ——
//     以用户最新拍板为准。两侧同源：此处 DUNGEON_CAP_BY_REALM ↔ 客户端 YLXW_DG_CAP。
//   境界序自持（不依赖 ECON_REALM_ORDER，避免与其它环的加载顺序耦合）。
const DUNGEON_REALM_ORDER: string[] = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];
const DUNGEON_CAP_BY_REALM: number[] = [10, 12, 14, 15, 17, 18, 20];
// 玩家境界 → 每日上限。未知境界 / 无存档 / 解析失败 → 兜底 DUNGEON_DAILY_CAP(=3)。
async function dungeonCapForUser(userId: number): Promise<number> {
  try {
    const row: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!row || !row.save_data) return DUNGEON_DAILY_CAP;
    const realm = JSON.parse(String(row.save_data))?.player?.realm;
    const idx = DUNGEON_REALM_ORDER.indexOf(String(realm || ''));
    if (!(idx >= 0)) return DUNGEON_DAILY_CAP;
    const cap = DUNGEON_CAP_BY_REALM[Math.min(idx, DUNGEON_CAP_BY_REALM.length - 1)];
    return Number.isFinite(cap) && cap > 0 ? cap : DUNGEON_DAILY_CAP;
  } catch { return DUNGEON_DAILY_CAP; }
}"""

# ============================================================ E3 status 传 cap

E3_OLD = """    const row = await dbGet('SELECT count, observed, adventure, last_ts, anomaly FROM dungeon_tracker WHERE player_id = ? AND date = ?', [req.user.id, bjDate(nowMs)]);
    res.json(dungeonStatusView(row, nowMs));"""

E3_NEW = """    const row = await dbGet('SELECT count, observed, adventure, last_ts, anomaly FROM dungeon_tracker WHERE player_id = ? AND date = ?', [req.user.id, bjDate(nowMs)]);
    res.json(dungeonStatusView(row, nowMs, await dungeonCapForUser(req.user.id)));"""

# ============================================================ E4 entry 传 cap

E4_OLD = "      const verdict = dungeonEntryVerdict(row?.count, row?.last_ts != null ? Number(row.last_ts) : null, nowMs);"

E4_NEW = ("      const _dgCap = await dungeonCapForUser(req.user.id);\n"
          "      const verdict = dungeonEntryVerdict(row?.count, row?.last_ts != null ? Number(row.last_ts) : null, nowMs, _dgCap);")

# ============================================================ E5 响应体用本次 cap

E5A_OLD = "          error: verdict.reason === 'cap' ? `今日秘境次数已用完（上限 ${DUNGEON_DAILY_CAP} 次）` : '进入过于频繁，请稍候再试',"
E5A_NEW = "          error: verdict.reason === 'cap' ? `今日秘境次数已用完（上限 ${_dgCap} 次）` : '进入过于频繁，请稍候再试',"

E5B_OLD = """          cap: DUNGEON_DAILY_CAP,
          remaining: Math.max(0, DUNGEON_DAILY_CAP - verdict.count),"""
E5B_NEW = """          cap: _dgCap,
          remaining: Math.max(0, _dgCap - verdict.count),"""

E5C_OLD = "      res.json({ ok: true, count: verdict.count, cap: DUNGEON_DAILY_CAP, remaining: Math.max(0, DUNGEON_DAILY_CAP - verdict.count), cdMs: DUNGEON_ENTRY_CD_MS });"
E5C_NEW = "      res.json({ ok: true, count: verdict.count, cap: _dgCap, remaining: Math.max(0, _dgCap - verdict.count), cdMs: DUNGEON_ENTRY_CD_MS });"

EDITS = [
    ("E1 境界→上限映射 + 取值函数", E1_OLD, E1_NEW),
    ("E3 status 传境界 cap",        E3_OLD, E3_NEW),
    ("E4 entry 传境界 cap",         E4_OLD, E4_NEW),
    ("E5a 403 文案用 _dgCap",       E5A_OLD, E5A_NEW),
    ("E5b 403 体用 _dgCap",         E5B_OLD, E5B_NEW),
    ("E5c 200 体用 _dgCap",         E5C_OLD, E5C_NEW),
]

REQUIRES = [
    ("const DUNGEON_DAILY_CAP = 3;", 1, "0.8.5 DG 环的基线常量必须在位"),
    ("const DUNGEON_ENTRY_CD_MS = 30_000;", 1, "0.8.5 DG 环的 CD 常量必须在位"),
    ("function dungeonEntryVerdict(", 1, "0.8.5 DG 环的判定函数必须在位"),
    ("function dungeonStatusView(", 1, "0.8.5 DG 环的状态视图必须在位"),
    ("app.get('/api/dungeon/status'", 1, "status 端点唯一"),
    ("app.post('/api/dungeon/entry'", 1, "entry 端点唯一"),
    ("function dbGet<T = any>(sql: string, params: any[] = []): Promise<T | undefined> {", 1, "dbGet 原语必须在位"),
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
    if "DUNGEON_CAP_BY_REALM" in src or "dungeonCapForUser" in src:
        fail("source looks already patched（已存在 DUNGEON_CAP_BY_REALM / dungeonCapForUser）")

    # 3) 境界序自检（两侧同源的表必须对得上 TRIB_REALM_BASES 的键序）
    trib_order = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境']
    pos = [src.find("'" + r + "': { maxExpBase") for r in trib_order]
    if any(p < 0 for p in pos) or pos != sorted(pos):
        fail("TRIB_REALM_BASES 键序与本环 DUNGEON_REALM_ORDER 不一致：%r" % (pos,))

    # 4) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    base403 = src.count("res.status(403")
    gates = [
        # ---- E1 ----
        ("R32 上限表 7 档",              "const DUNGEON_CAP_BY_REALM: number[] = [10, 12, 14, 15, 17, 18, 20];", 1),
        ("R32 上限表两端 10/20",         "[10, 12, 14, 15, 17, 18, 20]", 1),
        ("R32 旧 3 起步表已清零",        "[3, 6, 9, 12, 15, 18, 20]", 0),
        ("R32 境界序自持",               "const DUNGEON_REALM_ORDER: string[] = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];", 1),
        ("R32 取值函数已定义",           "async function dungeonCapForUser(userId: number): Promise<number> {", 1),
        ("R32 无存档兜底=3",             "if (!row || !row.save_data) return DUNGEON_DAILY_CAP;", 1),
        ("R32 未知境界兜底=3",           "if (!(idx >= 0)) return DUNGEON_DAILY_CAP;", 1),
        ("R32 anomaly 阈值抬到 25",      "const DUNGEON_ANOMALY_THRESHOLD = 25;", 1),
        ("R32 旧 anomaly 阈值已清零",    "const DUNGEON_ANOMALY_THRESHOLD = 10;", 0),
        # ---- E3/E4 调用点 ----
        ("R32 status 传境界 cap",        "res.json(dungeonStatusView(row, nowMs, await dungeonCapForUser(req.user.id)));", 1),
        ("R32 entry 传境界 cap",         "const verdict = dungeonEntryVerdict(row?.count, row?.last_ts != null ? Number(row.last_ts) : null, nowMs, _dgCap);", 1),
        ("R32 entry 先算 cap",           "const _dgCap = await dungeonCapForUser(req.user.id);", 1),
        # ---- E5 响应体 ----
        ("R32 403 文案用 _dgCap",        "`今日秘境次数已用完（上限 ${_dgCap} 次）`", 1),
        ("R32 403 体 cap 用 _dgCap",     "cap: _dgCap,\n          remaining: Math.max(0, _dgCap - verdict.count),", 1),
        ("R32 200 体 cap 用 _dgCap",     "res.json({ ok: true, count: verdict.count, cap: _dgCap, remaining: Math.max(0, _dgCap - verdict.count), cdMs: DUNGEON_ENTRY_CD_MS });", 1),
        ("R32 entry 体旧 cap 已清零",    "cap: DUNGEON_DAILY_CAP, remaining: Math.max(0, DUNGEON_DAILY_CAP - verdict.count)", 0),
        # ---- 冻结（本环不得回踩）----
        ("冻结 兜底常量 DUNGEON_DAILY_CAP=3", "const DUNGEON_DAILY_CAP = 3;", 1),
        ("冻结 CD 常量本环未动（R-062 第 41 环改 900_000）", "const DUNGEON_ENTRY_CD_MS = 30_000;", 1),
        ("冻结 verdict 函数体未动",      "if (c >= cap) return { allowed: false, count: c + 1, reason: 'cap', retryAfterMs: 0 };", 1),
        ("冻结 status 视图默认参未动",   "cap: number = DUNGEON_DAILY_CAP,\n  cdMs: number = DUNGEON_ENTRY_CD_MS", 1),
        ("冻结 403 reason 语义未动",     "reason: verdict.reason,", 1),
        ("冻结 经济配额 cSR 未动",       "const cSR = Math.ceil(", 1),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-38s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 7) 红线：不得新增 403
    a403 = out.count("res.status(403")
    good = (a403 == base403)
    ok = ok and good
    print("  [%s] %-38s actual=%d expect==%d" % ("OK" if good else "FAIL", "红线 未新增 res.status(403)", a403, base403))

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

    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".dungeon2-", suffix=".tmp")
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
