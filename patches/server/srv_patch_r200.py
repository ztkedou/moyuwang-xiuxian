# -*- coding: utf-8 -*-
r"""
srv_patch_r200.py -- R-200 移除 R-167「喂养当日首次免费」（服务端环）

  ★ 用户原话（逐字，唯一依据）：
    「R-167「当日首次免费」这个去掉，前面有专门的免费档了」

  ★ 背景：R-198（0.9.35 已上线）已在「培养」区加了**专门的免费进食**
    （+100 喂食度 / 每日 3 次 / 冷却 30 分钟 / 免灵石）。R-167 那套「每日第一次喂养不花灵石」
    于是成为**冗余的第二套免费机制** ⇒ 本环把 R-167 整条移除（只拆 R-198 闸门的 else 半边）。

  ★ 环号说明：测试基座 _chainstage/s85.r198.ts（当前 SRV_CHAIN 链尾 = 85 环，末环 R-198）。
    本环顺延 **第 86 环**。锚点全部落在「POST /api/pet/feed 的喂养闸门 / 回退」这一小块，
    与其余任何环零交集。

==============================================================================
零、改前取证（s85.r198.ts 字符级实测）
==============================================================================
  · R-167 首免闸门（else 分支）：`INSERT INTO pet_feed_log (player_id, date, times) VALUES (?, ?, 1)
    ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1 WHERE times < 1` + `_feedFree = ...`
    + `if (_feedFree) _feed.cost = 0;`（count==1）。
  · R-167 付费额度回退 SQL：`UPDATE pet_feed_log SET times = MAX(0, times - 1) ...`（count==2：
    回退闭包 else 分支 + catch 三目兜底）。
  · R-198 免费进食闸门：`ON CONFLICT(player_id, date) DO UPDATE SET free_times = free_times + 1,
    last_free_at = excluded.last_free_at WHERE free_times < ? AND (...)`（count==1，**逐字保留**）。
  · R-198 free_times 回退 SQL：`UPDATE pet_feed_log SET free_times = MAX(0, free_times - 1),
    last_free_at = NULL ...`（count==2，**逐字保留**）。

==============================================================================
一、改动点（5 处；锚点全部纯 ASCII 且唯一）
==============================================================================
  [1] `_feedDate = petDate(Date.now());` 前补一行「R-167 已整段移除」口径说明（锚点纯 ASCII）。
  [2] else 分支头 `    } else {\n      // ` → 收成 `    }` + 一行留档注释（原 [r167feed] 注释作留档）。
  [3] R-167 首免闸门代码块（const _feedGate … if (_feedFree) _feed.cost = 0; + 其闭合 `    }`）
      → 删净，原位落幂等标记 /*[r200free]*/。
  [4] `_feedRollback` 闭包：删掉 else 分支（付费回退 times），保留 R-198 的 free_times 回退。
  [5] catch 三目兜底：删掉 `: '... times = MAX(0, times - 1) ...'` 半边，保留 free_times 半边。

  ★ 保留不动（避免与既有门禁冲突）：pet_feed_log 建表、times 列、safeAddColumn 的 free_times /
    last_free_at、`feedQuota: {` 回显块、`SELECT times, free_times, last_free_at ...` 查询、
    PET_HUNGER_PER_FEED 等常量、R-198 免费闸门与其 free_times 回退、freeFeed 回显与 helper。
  ⇒ **不删表、不删列、不删回显**。

  ★ 语义：`_feedFree` 现在**只**在 R-198 免费进食分支置真 ⇒ `_feedFree ⇒ _freeReq` 恒成立，
    故 [4]/[5] 去掉 `_freeReq ?` 分支判断后行为等价（付费进食恒按档位扣费，不再有首免）。

==============================================================================
二、注释口径（★ 与「纯 ASCII 锚点」的取舍，明说）
==============================================================================
  · 现场 [r167feed] 注释多为**裸中文**，无法作为 ASCII 锚点 ⇒ 本环对注释只做
    「ASCII 锚点可及」的改写：在 `_feedDate` 前插一行明确「R-167 已整段移除」，
    并在 else 头把原注释收进一行「留档」注释；闸门代码块本身连同其紧邻注释一并消失。
  · 残留的几处 `// [r167feed] …`（回退调用点、状态声明）描述的是**回退额度**这一仍存在的行为，
    仅标签过期，不影响语义（详见交付报告「最可能踩的坑」）。

==============================================================================
契约
==============================================================================
  CLI：--src <path>（就地原子写回；写回前落 .bak-r200-<时间戳>）/ --check / --selftest（只验不写）。
  幂等：产物含 /*[r200free]*/ ⇒ SKIP（不写盘，rc=3）。
  退出码：0=成功；3=幂等跳过（产物已含标记）；1=契约/门禁失败；2=意外异常（IO/写回）。
  · 锚点唯一（count==1，纯 ASCII）；round-trip 正反双向自证后才原子写回。
  · 工程红线：不新增 require(（ESM 直跑）/ 不新增 res.status(403 / 不动 PRAGMA / 不新增 setInterval。
  · 服务端自证五步：--check rc=0 → 临时副本写回 → node --experimental-strip-types --check rc=0
    → 复跑 SKIP（rc=3）→ 清理（--selftest 内置同款语法校验）。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（TS 源码合法块注释）
MARK = "/*[r200free]*/"

# ============================================================ 改动点（5 处）

# ── [1] 在 _feedDate 行前补「已整段移除」口径说明（锚点纯 ASCII）────────────────
E1_OLD = "    _feedDate = petDate(Date.now());"
E1_NEW = (
    "    // [r200free] R-200：R-167「喂养当日首次免费」已整段移除（免费进食由 R-198「免费玩法」独立提供；\n"
    "    //   上方 [r167feed] 闸门说明已作废，保留仅作历史留档）。付费进食恒按档位扣费。\n"
    "    _feedDate = petDate(Date.now());"
)

# ── [2] else 分支头收成 `    }` + 留档注释（原 [r167feed] 注释作留档）────────────
E2_OLD = "    } else {\n      // "
E2_NEW = "    }\n    // [r200free] 原 [r167feed] 注释留档（该分支已删）："

# ── [3] R-167 首免闸门代码块删净，原位落幂等标记 ────────────────────────────────
E3_OLD = (
    "      const _feedGate = await dbRun(\n"
    "        'INSERT INTO pet_feed_log (player_id, date, times) VALUES (?, ?, 1) ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1 WHERE times < 1',\n"
    "        [userId, _feedDate]\n"
    "      );\n"
    "      _feedFree = _feedGate.changes > 0;\n"
    "      if (_feedFree) _feed.cost = 0;\n"
    "    }"
)
E3_NEW = "    " + MARK

# ── [4] 回退闭包：删 else（付费回退 times），保留 R-198 free_times 回退 ──────────
E4_OLD = (
    "      if (_freeReq) {\n"
    "        await dbRun('UPDATE pet_feed_log SET free_times = MAX(0, free_times - 1), last_free_at = NULL WHERE player_id = ? AND date = ?', [userId, _feedDate]);\n"
    "      } else {\n"
    "        await dbRun('UPDATE pet_feed_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?', [userId, _feedDate]);\n"
    "      }"
)
E4_NEW = (
    "      // [r200free] R-167 付费回退已移除（_feedFree 仅在 R-198 免费进食时置真）\n"
    "      await dbRun('UPDATE pet_feed_log SET free_times = MAX(0, free_times - 1), last_free_at = NULL WHERE player_id = ? AND date = ?', [userId, _feedDate]);"
)

# ── [5] catch 三目兜底：删 times 半边，保留 free_times 半边 ─────────────────────
E5_OLD = (
    "try { await dbRun(_freeReq ? 'UPDATE pet_feed_log SET free_times = MAX(0, free_times - 1), last_free_at = NULL WHERE player_id = ? AND date = ?' : 'UPDATE pet_feed_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?', [userId, _feedDate]); } catch {}"
)
E5_NEW = (
    "try { await dbRun('UPDATE pet_feed_log SET free_times = MAX(0, free_times - 1), last_free_at = NULL WHERE player_id = ? AND date = ?', [userId, _feedDate]); } catch {}"
)

EDITS = [
    ("R200 _feedDate 前补「已整段移除」口径", E1_OLD, E1_NEW),
    ("R200 else 分支头收成 } + 留档注释", E2_OLD, E2_NEW),
    ("R200 R-167 首免闸门代码块删净（MARK）", E3_OLD, E3_NEW),
    ("R200 回退闭包删 else（保留 free_times 回退）", E4_OLD, E4_NEW),
    ("R200 catch 三目删 times 半边", E5_OLD, E5_NEW),
]

# ============================================================ 依赖（绝对在位，锚点唯一）

REQUIRES = [
    ("const R018_FEED_TIERS", "==", 1, "付费三档表必须在位（本环一行未动）"),
    ("function r018FeedTier(", "==", 1, "喂养档位函数必须在位（本环只读）"),
    ("const PET_HUNGER_PER_FEED = 30;", "==", 1, "付费喂食度常量必须在位（本环一行未动）"),
    ("const PET_HUNGER_MAX = 9999;", "==", 1, "喂食度上限必须在位（本环一行未动）"),
    ("const PET_LEVEL_DIVISOR = 100;", "==", 1, "升级除数必须在位（本环一行未动）"),
    ("CREATE TABLE IF NOT EXISTS pet_feed_log (", "==", 1, "pet_feed_log 建表必须在位（本环不删表）"),
    ("const safeAddColumn = (table: string, col: string, ddl: string) => {", "==", 1,
     "既有幂等建列器必须在位（R-198 复用，本环不动）"),
    ("app.post('/api/pet/feed', authenticateToken", "==", 1, "feed 端点必须在位（本环改其闸门/回退）"),
    ("app.post('/api/pet/play', authenticateToken", "==", 1, "play 端点必须在位（本环一行未动）"),
    ("app.get('/api/pet', authenticateToken", "==", 1, "GET /api/pet 必须在位（本环不删 feedQuota 回显）"),
    ("function dbGet<T = any>(sql: string, params: any[] = []): Promise<T | undefined> {", "==", 1,
     "dbGet 必须在位（本环不动）"),
    ("function dbRun(", "==", 1, "dbRun 必须在位（本环不动）"),
    ("function petDate(", "==", 1, "日期键换算必须在位（本环不动）"),
    ("INSERT INTO pet_play_log (player_id, date, times, bought) VALUES (?, ?, 1, 1)", "==", 1,
     "买额度闸门必须在位（本环一行未动）"),
    ("const R198_FREE_FEED_MAX = 3;", "==", 1, "R-198 免费进食上限必须在位（本环一行未动）"),
    ("const R198_FREE_FEED_CD_MS = 30 * 60 * 1000;", "==", 1, "R-198 冷却常量必须在位（本环一行未动）"),
    ("const R198_FREE_FEED_HUNGER = 100;", "==", 1, "R-198 单次喂食度必须在位（本环一行未动）"),
    ("async function r198FreeFeedQuota(", "==", 1, "R-198 额度视图 helper 必须在位（本环一行未动）"),
    ("ON CONFLICT(player_id, date) DO UPDATE SET free_times = free_times + 1, last_free_at = excluded.last_free_at WHERE free_times < ? AND (last_free_at IS NULL OR (? - last_free_at) >= ?)",
     "==", 1, "R-198 免费闸门必须在位（本环逐字保留）"),
    ("[r198free]", ">=", 1, "R-198 环必须已应用（链序约束：本环排其后）"),
    ("[r167feed]", ">=", 1, "R-167 环必须已应用（本环移除其闸门）"),
    ("[r194dao]", ">=", 1, "R-194 环必须已应用（链序约束）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 付费进食（本环一行未动）
    "const R018_FEED_TIERS",
    "function r018FeedTier(",
    "const PET_HUNGER_PER_FEED = 30;",
    "const PET_HUNGER_MAX = 9999;",
    "const PET_LEVEL_DIVISOR = 100;",
    # pet_feed_log 表 / 列 / 回显（本环不删表/列/回显）
    "CREATE TABLE IF NOT EXISTS pet_feed_log (",
    "'ALTER TABLE pet_feed_log ADD COLUMN free_times INTEGER NOT NULL DEFAULT 0'",
    "'ALTER TABLE pet_feed_log ADD COLUMN last_free_at INTEGER'",
    "SELECT times, free_times, last_free_at FROM pet_feed_log WHERE player_id = ? AND date = ?",
    "feedQuota: {",
    # R-198 免费闸门 / 回退 / helper / 回显（本环逐字保留）
    "ON CONFLICT(player_id, date) DO UPDATE SET free_times = free_times + 1, last_free_at = excluded.last_free_at WHERE free_times < ? AND (last_free_at IS NULL OR (? - last_free_at) >= ?)",
    "UPDATE pet_feed_log SET free_times = MAX(0, free_times - 1), last_free_at = NULL WHERE player_id = ? AND date = ?",
    "_feedFree = true; // [r198free]",
    "async function r198FreeFeedQuota(",
    "freeFeed: (() => {",
    # 买额度闸门 / 端点（本环一行未动）
    "INSERT INTO pet_play_log (player_id, date, times, bought) VALUES (?, ?, 1, 1)",
    "app.post('/api/pet/play', authenticateToken",
    "app.post('/api/pet/feed', authenticateToken",
    "app.get('/api/pet', authenticateToken",
    # 工程红线（相对计数）
    "res.status(403",
    "setInterval(",
    "PRAGMA",
    "require(",
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out: str, base):
    """五元组 (label, needle, expect, op, note)；base = 冻结针脚在**基座**上的计数。"""
    return [
        ("R200 幂等标记在位", MARK, 1, "==", "本环已应用"),
        # ── R-167 闸门 / 回退 / 置零 全部清零 ──
        ("R200 R-167 首免闸门 SQL 清零",
         "INSERT INTO pet_feed_log (player_id, date, times) VALUES (?, ?, 1) ON CONFLICT(player_id, date) DO UPDATE SET times = times + 1 WHERE times < 1",
         0, "==", "闸门 SQL 已删净"),
        ("R200 R-167 付费回退 times SQL 清零",
         "UPDATE pet_feed_log SET times = MAX(0, times - 1) WHERE player_id = ? AND date = ?",
         0, "==", "回退 SQL 已删净（闭包 else + catch 三目）"),
        ("R200 R-167 首次免费置 0 清零", "if (_feedFree) _feed.cost = 0;", 0, "==", "首免置 0 已删净"),
        ("R200 R-167 闸门变量清零", "_feedGate", 0, "==", "const _feedGate / _feedGate.changes 均已删净"),
        # ── R-198 免费进食半边逐字保留 ──
        ("R200 R-198 免费闸门逐字保留",
         "ON CONFLICT(player_id, date) DO UPDATE SET free_times = free_times + 1, last_free_at = excluded.last_free_at WHERE free_times < ? AND (last_free_at IS NULL OR (? - last_free_at) >= ?)",
         1, "==", "免费闸门未动"),
        ("R200 R-198 免费分支占用标记保留", "_feedFree = true; // [r198free]", 1, "==", "R-198 分支未动"),
        ("R200 R-198 free_times 回退保留 ×2",
         "UPDATE pet_feed_log SET free_times = MAX(0, free_times - 1), last_free_at = NULL WHERE player_id = ? AND date = ?",
         2, "==", "闭包 + catch 各一处，逐字保留"),
        ("R200 R-198 helper 保留", "async function r198FreeFeedQuota(", 1, "==", "额度视图未动"),
        ("R200 R-198 freeFeed 回显保留", "freeFeed: (() => {", 1, "==", "GET /api/pet 未动"),
        # ── 不删表 / 列 / 回显 ──
        ("R200 冻结·pet_feed_log 建表保留", "CREATE TABLE IF NOT EXISTS pet_feed_log (", 1, "==", "不删表"),
        ("R200 冻结·free_times 列保留", "'ALTER TABLE pet_feed_log ADD COLUMN free_times INTEGER NOT NULL DEFAULT 0'", 1, "==", "不删列"),
        ("R200 冻结·last_free_at 列保留", "'ALTER TABLE pet_feed_log ADD COLUMN last_free_at INTEGER'", 1, "==", "不删列"),
        ("R200 冻结·GET 查询源保留", "SELECT times, free_times, last_free_at FROM pet_feed_log WHERE player_id = ? AND date = ?", 1, "==", "不删回显查询"),
        ("R200 冻结·feedQuota 回显保留", "feedQuota: {", 1, "==", "不删回显块"),
        # ── 付费进食 / 买额度 / 端点未动 ──
        ("R200 冻结·R018_FEED_TIERS", "const R018_FEED_TIERS", 1, "==", "三档表未动"),
        ("R200 冻结·r018FeedTier", "function r018FeedTier(", 1, "==", "未动"),
        ("R200 冻结·PET_HUNGER_PER_FEED", "const PET_HUNGER_PER_FEED = 30;", 1, "==", "未动"),
        ("R200 冻结·PET_HUNGER_MAX", "const PET_HUNGER_MAX = 9999;", 1, "==", "未动"),
        ("R200 冻结·PET_LEVEL_DIVISOR", "const PET_LEVEL_DIVISOR = 100;", 1, "==", "未动"),
        ("R200 冻结·买额度闸门 SQL", "INSERT INTO pet_play_log (player_id, date, times, bought) VALUES (?, ?, 1, 1)", 1, "==", "未动"),
        ("R200 冻结·play 端点", "app.post('/api/pet/play', authenticateToken", 1, "==", "未动"),
        ("R200 冻结·feed 端点仍在", "app.post('/api/pet/feed', authenticateToken", 1, "==", "未动"),
        ("R200 冻结·GET /api/pet 仍在", "app.get('/api/pet', authenticateToken", 1, "==", "未动"),
        # ── 工程红线（相对计数）──
        ("R200 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403"),
        ("R200 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R200 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        ("R200 红线·无 require", "require(", 0, "==", "ESM 不新增 require"),
    ]


def _apply(src: str) -> str:
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)
    return out


def _roundtrip(out: str, src: str):
    back = out
    for name, old, new in reversed(EDITS):
        if back.count(new) != 1:
            return False, "逆向：%s 的新块出现 %d 次（期望 1）" % (name, back.count(new))
        back = back.replace(new, old, 1)
    return (back == src), "逆向逐字节还原"


def _find_node():
    cand = [os.environ.get('YL_NODE'), os.environ.get('NODE'), shutil.which('node')]
    nroot = 'C:/Users/27026/.workbuddy-ai/binaries/node/versions'
    if os.path.isdir(nroot):
        subs = sorted(os.path.join(nroot, d, 'node.exe') for d in os.listdir(nroot))
        cand += [p for p in reversed(subs) if os.path.isfile(p)]
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(text: str):
    """在临时副本上跑 node --experimental-strip-types --check；返回 (rc, node)（node 缺失 → (None,None)）。"""
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.ts')
    try:
        with io.open(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        r = subprocess.run([node, '--experimental-strip-types', '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description="R-200 移除 R-167「喂养当日首次免费」（服务端环）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：产物含标记 ⇒ SKIP（不写盘，rc=3）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        sys.exit(3)

    # 2) 依赖（绝对在位）
    for needle, op, cnt, why in REQUIRES:
        n = src.count(needle)
        good = (n == cnt) if op == "==" else (n >= cnt)
        if not good:
            fail("依赖未满足（%r 出现 %d 次，期望 %s %d）：%s" % (needle[:80], n, op, cnt, why))

    # 3) 锚点唯一 + 纯 ASCII
    for name, old, new in EDITS:
        if not all(ord(c) < 128 for c in old):
            fail("%s 锚点含非 ASCII 字符（违反工程约束）" % name)
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线（针脚必须在基座真实存在，防拼错导致冻结静默失效）
    base = {k: src.count(k) for k in BASE_NEEDLES}
    for k in BASE_NEEDLES:
        if base[k] <= 0 and k != "require(":  # require( 合法基线 = 0（ESM 红线）
            fail("冻结针脚在基座不存在（拼写错误？）：%r" % k[:90])

    # 5) 应用
    out = _apply(src)

    # 6) 门禁（五元组）
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-46s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证（正向重放一致 + 逆向逐字节还原）
    if out != _apply(src):
        fail("round-trip(正向重构) mismatch")
    rt_ok, rt_msg = _roundtrip(out, src)
    if not rt_ok:
        fail("round-trip(逆向) mismatch：%s" % rt_msg)

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    # 8) 语法自证（node --experimental-strip-types --check；node 缺失则跳过）
    if a.check or a.selftest:
        rc, node = _node_check(out)
        print("  node --check rc=%s (%s)" % (rc, node or 'node not found (skipped)'))
        if rc not in (None, 0):
            fail("node --experimental-strip-types --check 未通过")
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r200-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r200free-", suffix=".tmp")
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
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        print("[ERROR] %s: %s" % (type(e).__name__, e))
        sys.exit(2)
