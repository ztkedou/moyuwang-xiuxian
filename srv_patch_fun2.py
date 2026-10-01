# -*- coding: utf-8 -*-
r"""
srv_patch_fun2.py -- R-029 茶馆「可查看记录」服务端环（fun2）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回；`--check` 只校验不写。
  链序：**必须排在 srv_patch_fun086.py 之后**（本环依赖其 `/api/teahouse/today`
  响应体形态与 teahouse_bets 表），建议挂链尾（第 24+ 环）。

需求原文
--------------------------------------------------------------------------
  「茶馆结果通过信箱发送，或在每日行乐里添加可查看记录（二选一，建议后者，风险低）」
  ⇒ 采纳后者。客户端 `yl_fun2_ext.py` 已展示「今日结果」；
     本环为「记录」维度补 `myHistory`（近 14 日逐日流水）。

改点（2 处，纯只读投影）
--------------------------------------------------------------------------
  E1  today 处理器在 Promise.all 之后补一条只读查询：
        `SELECT date, side, stones, won, payout FROM teahouse_bets WHERE user_id=? ORDER BY date DESC LIMIT 14`
  E2  响应体 myBet 之后补 `myHistory`（逐字段 Number 归一；won/payout 保留 null=待结算）

★ 红线
--------------------------------------------------------------------------
  · **只读**：不写任何表、不改结算（teaSettleDue）、不改 /teahouse/bet、不动入账。
  · 业务拒绝语义零改动；不新增 403。
  · 客户端缺 myHistory 时自动不渲染历史块 ⇒ 本环可与前端**分别上线**。

客户端配套
--------------------------------------------------------------------------
  `yl_fun2_ext.py`：`Array.isArray(t.myHistory)` 为真才渲染「茶馆记录」折叠块。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ E1 只读历史查询

E1_OLD = """      dbAll('SELECT count, cost, payout, detail FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ? ORDER BY count DESC LIMIT ?', [userId, today, 'dice', 10]),
    ]);"""

E1_NEW = """      dbAll('SELECT count, cost, payout, detail FROM fun_daily WHERE player_id = ? AND date = ? AND kind = ? ORDER BY count DESC LIMIT ?', [userId, today, 'dice', 10]),
    ]);
    // ★ R-029（fun2 环）：茶馆「可查看记录」——近 14 日逐日流水（**纯只读投影**，
    //   不写表、不改结算、不改 /teahouse/bet）。客户端 yl_fun2_ext.py 消费 myHistory。
    const teaHist = await dbAll('SELECT date, side, stones, won, payout FROM teahouse_bets WHERE user_id = ? ORDER BY date DESC LIMIT 14', [userId]);"""

# ============================================================ E2 响应体补 myHistory

E2_OLD = "      myBet: mine ? { side: Number(mine.side), stones: Number(mine.stones), won: mine.won == null ? null : Number(mine.won), payout: mine.payout == null ? null : Number(mine.payout), times } : null,"

E2_NEW = ("      myBet: mine ? { side: Number(mine.side), stones: Number(mine.stones), won: mine.won == null ? null : Number(mine.won), payout: mine.payout == null ? null : Number(mine.payout), times } : null,\n"
          "      // ★ R-029：茶馆历史记录（逐字段 Number 归一；won/payout 保留 null = 待结算）\n"
          "      myHistory: (teaHist || []).map((x: any) => ({ date: String(x.date), side: Number(x.side) || 0, stones: Number(x.stones) || 0, won: x.won == null ? null : Number(x.won), payout: x.payout == null ? null : Number(x.payout) })),")

EDITS = [
    ('E1 today 补只读历史查询', E1_OLD, E1_NEW),
    ('E2 响应体补 myHistory',   E2_OLD, E2_NEW),
]

REQUIRES = [
    ("app.get('/api/teahouse/today'", 1, "fun086 环必须先跑过（本环为其后继）"),
    ("await teaSettleDue(today);", 1, "结算原语在位（本环不改它）"),
    ("CREATE TABLE IF NOT EXISTS teahouse_bets (", 1, "茶馆流水表在位（本环只读）"),
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

    if "myHistory" in src or "teaHist" in src:
        fail("source looks already patched（已存在 myHistory / teaHist）")

    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    base403 = src.count('res.status(403')
    gates = [
        ('R29 历史查询为只读 SELECT',  "SELECT date, side, stones, won, payout FROM teahouse_bets WHERE user_id = ? ORDER BY date DESC LIMIT 14", 1, None),
        ('R29 响应体含 myHistory',     'myHistory: (teaHist || []).map((x: any) => ({ date: String(x.date)', 1, None),
        ('R29 待结算保留 null',        'won: x.won == null ? null : Number(x.won), payout: x.payout == null ? null : Number(x.payout) })),', 1, None),
        ('冻结 结算原语未动',          'await teaSettleDue(today);', 1, None),
        ('冻结 下注端点未动',          "app.post('/api/teahouse/bet'", 1, None),
        ('冻结 today 端点唯一',        "app.get('/api/teahouse/today'", 1, None),
        ('冻结 myBet 字段未动',        'myBet: mine ? { side: Number(mine.side), stones: Number(mine.stones), won: mine.won == null ? null : Number(mine.won), payout: mine.payout == null ? null : Number(mine.payout), times } : null,', 1, None),
        ('冻结 无写表新增',            'INSERT INTO teahouse_bets', 1, None),
    ]
    ok = True
    for g in gates:
        label, needle, exp = g[0], g[1], g[2]
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))
    a403 = out.count('res.status(403')
    good = (a403 == base403)
    ok = ok and good
    print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", '红线 未新增 res.status(403)', a403, base403))
    if not ok:
        fail("门禁未全绿，未写回")

    back = out
    for name, old, new in EDITS:
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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".fun2-", suffix=".tmp")
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
