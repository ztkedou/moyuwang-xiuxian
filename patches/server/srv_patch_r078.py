# -*- coding: utf-8 -*-
r"""
srv_patch_r078.py — 灵宠·妖灵「收养 / 归位」消耗回显（R-078 服务端环）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  前置依赖：必须在 **r071**（本环锚点用到 `R071_ADOPT_COST` / `R071_AWAY_COST` 两常量）之后。
  挂 SRV_CHAIN 链尾即可（或紧随 srv_patch_r071.py 之后）。

本环做什么
--------------------------------------------------------------------------
  R-078 玩家看不到「收养妖灵要花多少灵石」。
  ★ 根因在服务端：`GET /api/pet` 的 `consts` 表**没带** `adoptCost`，
    而客户端 R-071 按钮读的正是 `t.consts.adoptCost` ⇒ 恒 undefined ⇒ 显示空白。
    （服务端只在 `POST /api/pet/adopt` 的回执里带 `cost`，点击之后才拿得到，太晚。）
  ⇒ 修法：把 `adoptCost` / `awayCost` 补进 `GET /api/pet` 的 `consts`，
    **直接引用 r071 既有常量**（`R071_ADOPT_COST` / `R071_AWAY_COST`），零硬编码 ——
    以后调价只改 r071 常量，客户端显示自动跟着变。
  客户端配套 = `yl_r078_ext.py`（显示消耗 + 灵石不足置灰/提示）。

锚区（与既有环零交集，已 grep 确认唯一）
--------------------------------------------------------------------------
  S1  `GET /api/pet` 的 `consts` 表末行 `runeCost: R018B_RUNE_COST, runeTable: R018B_RUNE_TABLE,`
      之后追加 `adoptCost` / `awayCost`。
  ★ 不改任何既有端点签名 / 常量 / 门禁串（r018 / r018b / r071 门禁面全部保留）。
  ★ 不新增 `res.status(403)`（403 会被客户端 Xc() 当会话失效强制登出）。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ S1 consts 表补两字段

S1_OLD = "        runeCost: R018B_RUNE_COST, runeTable: R018B_RUNE_TABLE,\n"

S1_NEW = ("        runeCost: R018B_RUNE_COST, runeTable: R018B_RUNE_TABLE,\n"
          "        // [r078] R-078 消耗回显：收养 / 归位 的灵石价（引用 r071 常量，客户端按钮据此显示与置灰）\n"
          "        adoptCost: R071_ADOPT_COST, awayCost: R071_AWAY_COST,\n")

EDITS = [
    ("S1 consts 补 adoptCost/awayCost", S1_OLD, S1_NEW),
]

REQUIRES = [
    ("const R071_ADOPT_COST = 20000;", 1, "r071 收养价常量（本环引用源）"),
    ("const R071_AWAY_COST = 30000;", 1, "r071 归位价常量（本环引用源）"),
    ("app.get('/api/pet', authenticateToken", 1, "GET /api/pet 端点唯一"),
    ("runeCost: R018B_RUNE_COST, runeTable: R018B_RUNE_TABLE,", 1, "consts 表末行（本环 S1 锚点）"),
    ("feedCost: PET_FEED_COST", 1, "consts 表既有首行（冻结面）"),
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description='R-078 灵宠收养/归位 消耗回显（服务端环 r078）')
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
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:70], n, cnt, why))

    # 2) 幂等
    if "adoptCost: R071_ADOPT_COST" in src:
        fail("source looks already patched（已存在 adoptCost: R071_ADOPT_COST）")

    # 3) 锚点计数（恰 1）
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
        # ---- 本环改动 ----
        ("R78 consts 带 adoptCost/awayCost", "        adoptCost: R071_ADOPT_COST, awayCost: R071_AWAY_COST,", 1),
        ("R78 consts 引用 r071 常量(非硬编码)", "adoptCost: R071_ADOPT_COST, awayCost: R071_AWAY_COST,", 1),
        ("R78 旧 consts 末行形态已清零", "runeCost: R018B_RUNE_COST, runeTable: R018B_RUNE_TABLE,\n      },", 0),
        # ---- 冻结：r071 / r018 门禁面 ----
        ("冻结 r071 收养价常量未动", "const R071_ADOPT_COST = 20000;", 1),
        ("冻结 r071 归位价常量未动", "const R071_AWAY_COST = 30000;", 1),
        ("冻结 r071 收养回执未动", "res.json({ ok: true, pet: petView({ name, rarity, hunger: 0, exp: 0, bond: 0 }), cost: R071_ADOPT_COST });", 1),
        ("冻结 r018 转化率常量未动", "const R018_CONVERT = 0.06;", 1),
        ("冻结 pets UNIQUE 防线未动", "player_id INTEGER NOT NULL UNIQUE", 1),
        ("冻结 consts 表既有字段未动", "feedCost: PET_FEED_COST", 1),
        ("冻结 consts 表 runeCost 未动", "runeCost: R018B_RUNE_COST", 1),
        ("冻结 GET /api/pet 端点签名未动", "app.get('/api/pet', authenticateToken", 1),
        ("R78 不新增仙途任务", "QUEST_DEFS", src.count("QUEST_DEFS")),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-42s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 6) 红线：不得新增 403
    a403 = out.count("res.status(403")
    good = (a403 == base403)
    ok = ok and good
    print("  [%s] %-42s actual=%d expect==%d" % ("OK" if good else "FAIL", "红线 未新增 res.status(403)", a403, base403))

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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r078-", suffix=".tmp")
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
