# -*- coding: utf-8 -*-
r"""
srv_patch_062.py -- R-062 秘境单次进入冷却 30s → 15 分钟（服务端半边）

CLI 契约（与链上其余补丁一致，照 srv_patch_dungeon2.py 抄）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。

=========================================================================== 为什么服务端必须改
经典秘境弹窗入口（XM.handleEnterRealm，yl_dungeon085_ext 接线）本地**不查 cdMin**，
只吃服务端 `/api/dungeon/entry` 的 403（reason:'cd'）——服务端 CD 是该入口
**唯一真实的冷却执行点**。只改客户端 YLXW_DG_CD_MS = 死代码
（与 srv_patch_dungeon2.py 头部「客户端改 = 死代码」同一论证）。

现状链证据（2026-10-01 实测，srv/index_v28.ts）：
  · `const DUNGEON_ENTRY_CD_MS = 30_000;` 恰 1 处（0.8.5 基线，dungeon2 环明确未改它，
    其文件尾「待办」留了这条独立改点 —— 本环就是那条改点）。
  · dungeonEntryVerdict 的 cd 判定 `if (last != null && nowMs - last < cdMs) …
    reason:'cd'` 与 status 视图默认参 `cdMs: number = DUNGEON_ENTRY_CD_MS`（2 处）
    全部取值于该常量 ⇒ 改常量即全链生效。
  · 15 分钟 CD 同时约束 roguelike 入口（共享账本）：R-063 的「最低等级 3 次/日」
    在 15 分钟间隔下 30 分钟即可打满，无冲突。

=========================================================================== 改点（1 处）
  E1  `const DUNGEON_ENTRY_CD_MS = 30_000;` → `const DUNGEON_ENTRY_CD_MS = 900_000;`
      行尾既有注释（「两次进入最小间隔…」）原样保留。

  ★ 不碰：DUNGEON_DAILY_CAP=3 兜底、DUNGEON_CAP_BY_REALM 上限表（R-063 的面）、
    dungeonEntryVerdict / dungeonStatusView 函数体、经济配额 cSR、
    403 语义（不新增 res.status(403)）。

=========================================================================== 链序
  ★ 必须排在 srv_patch_dungeon2.py **之后**（本环 REQUIRES 断言
    DUNGEON_CAP_BY_REALM 已在位；若本环先跑，dungeon2 的 REQUIRES
    「30_000 必须在位」会失败 —— 双向强制正确链序）。
  放 SRV_CHAIN 链尾（与 srv_patch_050/054~057 同区）即可满足。
  ★ 上游门禁同步：srv_patch_dungeon2.py 的
    `("冻结 CD 常量未动", "const DUNGEON_ENTRY_CD_MS = 30_000;", 1)`
    在本环接入后 =0，请 lead 改 0 或删除（本环自带等价正反门禁）。

=========================================================================== 客户端半边
  yl_062_ext.py：YLXW_DG_CD_MS 5→15 分钟 + 展示文案「每次探索后冷却 15 分钟」。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ E1 CD 常量

E1_OLD = "const DUNGEON_ENTRY_CD_MS = 30_000;"
E1_NEW = "const DUNGEON_ENTRY_CD_MS = 900_000;"

EDITS = [
    ("E1 秘境单次冷却 30s → 15 分钟", E1_OLD, E1_NEW),
]

REQUIRES = [
    ("const DUNGEON_ENTRY_CD_MS = 30_000;", 1, "0.8.5 DG 环的 CD 常量必须在位（本环的唯一改点）"),
    ("const DUNGEON_CAP_BY_REALM: number[] = [10, 12, 14, 15, 17, 18, 20];", 1,
     "srv_patch_dungeon2.py 必须已在本环之前（链序强制）"),
    ("const DUNGEON_DAILY_CAP = 3;", 1, "0.8.5 DG 环的兜底常量必须在位"),
    ("function dungeonEntryVerdict(", 1, "0.8.5 DG 环的判定函数必须在位"),
    ("function dungeonStatusView(", 1, "0.8.5 DG 环的状态视图必须在位"),
    ("if (c >= cap) return { allowed: false, count: c + 1, reason: 'cap', retryAfterMs: 0 };", 1,
     "verdict 的 cap 分支必须在位（冻结面）"),
    ("reason: 'cd'", 1, "verdict 的 cd 分支必须在位（冻结面）"),
    ("cdMs: number = DUNGEON_ENTRY_CD_MS", 2, "status/entry 视图默认参都取值于该常量"),
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
    if "const DUNGEON_ENTRY_CD_MS = 900_000;" in src:
        fail("source looks already patched（已存在 900_000 CD 常量）")

    # 3) 锚点计数 + old != new
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
    base403 = src.count("res.status(403")
    gates = [
        # ---- E1 ----
        ("R62 CD 常量 = 15 分钟",        "const DUNGEON_ENTRY_CD_MS = 900_000;", 1),
        ("R62 旧 30_000 常量已清零",     "const DUNGEON_ENTRY_CD_MS = 30_000;", 0),
        # ---- 冻结（本环不得回踩）----
        ("冻结 兜底常量 DUNGEON_DAILY_CAP=3", "const DUNGEON_DAILY_CAP = 3;", 1),
        ("冻结 dungeon2 上限表未动",      "const DUNGEON_CAP_BY_REALM: number[] = [10, 12, 14, 15, 17, 18, 20];", 1),
        ("冻结 verdict cap 分支未动",     "if (c >= cap) return { allowed: false, count: c + 1, reason: 'cap', retryAfterMs: 0 };", 1),
        ("冻结 verdict cd 分支未动",      "reason: 'cd'", 1),
        ("冻结 视图默认参 cdMs 未动",     "cdMs: number = DUNGEON_ENTRY_CD_MS", 2),
        ("冻结 经济配额 cSR 未动",        "const cSR = Math.ceil(", 1),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-38s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 6) 红线：不得新增 403
    a403 = out.count("res.status(403")
    good = (a403 == base403)
    ok = ok and good
    print("  [%s] %-38s actual=%d expect==%d" % ("OK" if good else "FAIL", "红线 未新增 res.status(403)", a403, base403))

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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r062-", suffix=".tmp")
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
