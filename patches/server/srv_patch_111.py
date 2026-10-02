# -*- coding: utf-8 -*-
r"""
srv_patch_111.py -- R-111「每日签到不能使用」服务端根因修复（SRV_CHAIN 链尾）

需求（台账 R-111，逐字）
--------------------------------------------------------------------------
  「每日签到有bug，实际不能使用。」

根因（本轮独立取证，逐字证据）
--------------------------------------------------------------------------
  `actSignDaysInMonth` / `actSignEnsureMonth` 两处构造「下月字符串」写成：

      const nextMonth = mo === 12 ? (y + 1) + '-01' : month.slice(0, 4) + String(mo + 1).padStart(2, '0');

  其中 `month = bjDate(nowMs).slice(0, 7)`，形如 `"2026-11"`（7 字符）。
  ⇒ `month.slice(0, 4)` = `"2026"`（**丢掉了 `-`**）⇒ 拼出 `"202611"`
  ⇒ `Date.parse("202611-01T00:00:00+08:00")` = **NaN**
  ⇒ `endAt` = NaN ⇒ `if (!Number.isFinite(startAt) || !Number.isFinite(endAt) || endAt <= startAt) return null;`
  ⇒ `actSignEnsureMonth()` **恒返 null** ⇒ `actSignEnsureMonth` 的 INSERT 分支永远走不到，
     即便走到也会因 `events.end_at` 为 NULL 撞 `SQLITE_CONSTRAINT: NOT NULL constraint failed: events.end_at`
  ⇒ `GET /api/activity/checkin` 恒 **409** `{"error":"签到暂未开放"}`
  ⇒ 客户端红字「签到暂未开放」+「重试」（见台账附图 R-111-1.png）。

  ★ 只有 `mo === 12` 分支（`(y + 1) + '-01'`）是对的 ⇒ **1~11 月全坏、12 月正常**（典型月长算式抄漏分隔符）。

修法（最小面）
--------------------------------------------------------------------------
  两处 `month.slice(0, 4)` → `month.slice(0, 5)`：
  `"2026-" + "11"` = `"2026-11"` ✓。只改字符串构造，**不动** DDL / 端点 / 计费 / 幂等键。

契约：`--src <path>` 就地原子写回；`--check` / `--selftest` 只校验不写。
"""

import argparse
import io
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, 'srv', 'index_v28.ts')

# --------------------------------------------------------------------------- 编辑
OLD = ("const nextMonth = mo === 12 ? (y + 1) + '-01' : "
       "month.slice(0, 4) + String(mo + 1).padStart(2, '0');")
NEW = ("const nextMonth = mo === 12 ? (y + 1) + '-01' : "
       "month.slice(0, 5) + String(mo + 1).padStart(2, '0');")

EDITS = [
    ('R111-nextMonth', OLD, NEW),
]

# --------------------------------------------------------------------------- 冻结面（打补丁前后都不许变）
FREEZE = [
    ("冻结 actSignDaysInMonth 函数名", "function actSignDaysInMonth(nowMs: number): number", 1),
    ("冻结 actSignEnsureMonth 函数名", "async function actSignEnsureMonth(nowMs: number): Promise<any | null>", 1),
    ("冻结 月长下限 28", "return Math.max(28, Math.round(", 1),
    ("冻结 无效窗口早退", "|| endAt <= startAt) return null;", 1),
    ("冻结 当月场查询", "FROM events WHERE type = 'checkin_fest' AND start_at = ? AND end_at = ?", 2),
    ("冻结 签到端点文案", '签到暂未开放', 2),
    ("冻结 403 红线未动", "res.status(403", None),   # None = 与基线同值
    ("冻结 PRAGMA 未新增", "PRAGMA", None),
]


def fail(msg):
    print("[FAIL] " + msg)
    raise SystemExit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-111 签到当月场 nextMonth 修复环")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = os.path.abspath(a.src)
    with io.open(src_path, encoding="utf-8") as f:
        src = f.read()

    base = {}
    for label, needle, _ in FREEZE:
        base[label] = src.count(needle)

    out = src
    for name, old, new in EDITS:
        n = out.count(old)
        if n != 2:
            fail("%s 的 old 在源中出现 %d 次（期望 2：daysInMonth + ensureMonth 各 1）" % (name, n))
        out = out.replace(old, new)
        print("  [OK] %-22s 替换 %d 处" % (name, n))

    # ---- 门禁 ----
    gates = [
        ("R111·下月串已补全分隔符", NEW, 2),
        ("R111·旧截断形态已清零", "month.slice(0, 4)", 0),
        ("R111·12 月分支保留", "(y + 1) + '-01'", 2),
        ("R111·padStart 保留", "String(mo + 1).padStart(2, '0')", 2),
    ]
    for label, needle, exp in FREEZE:
        gates.append((label, needle, base[label] if exp is None else exp))

    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # ---- 往返自证 ----
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 2:
            fail("%s 的 new 在产物中出现 %d 次（期望 2）" % (name, back.count(new)))
        back = back.replace(new, old)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r111sign-", suffix=".tmp")
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
