# -*- coding: utf-8 -*-
r"""
srv_patch_r136.py -- R-136 B：新开局「普通秘境冷却 800+ 秒」根因修复（服务端 · SRV_CHAIN 新环，第 66 环）

台账原文（R-136，逐字）
--------------------------------------------------------------------------
  「秘境手札中也记录 roguelike 的冷却时间，并且我刚进游戏，怎么普通秘境的冷却还有 800 多秒」
  （A 半 = 手札加「地宫冷却」行 → 客户端环 localtest/yl_r136_ext.py，本环只做 B 半）

根因（逐字实证，srv/index_v28.ts 装配前基座）
--------------------------------------------------------------------------
  · 冷却真值 = dungeon_tracker.last_ts，读点在 dungeonStatusView：
        const cdLeftMs = lastTs != null ? Math.max(0, cdMs - (nowMs - lastTs)) : 0;
    （cdMs = DUNGEON_ENTRY_CD_MS = 900000 = 15 分钟 ⇒ 刚写过就是 900 秒，衰减到 800 余秒
      正好对上用户看到的「800 多秒」）
  · last_ts 有 **两个写入者**：
      ① POST /api/dungeon/entry（真正的「进入秘境」上报）—— count 与 last_ts 同写。**这是唯一语义正确的写入者**。
      ② tickDungeonTracker()（由 /api/save 的存档差值驱动）—— 只要存档里
         `realm`（观测）或 `adventure`（历练）有**任何**增量就 upsert 一行，
         且 ON CONFLICT 里无条件 `last_ts = excluded.last_ts`。
  · ⇒ **没进过秘境、只是在历练的玩家，last_ts 被 tickDungeonTracker 每几秒刷一次**
    ⇒ cdLeftMs 恒在 800~900 秒之间回满 ⇒ 普通秘境永远显示「冷却中」，进不去。
    这正是用户「我刚进游戏」的实况（新号只历练，从未进秘境）。
  · 旁证（同一函数的注释自陈）：「无增量的存档上传不落行不刷 last_ts（last_ts 只反映秘境/历练活动，
    不是存档活跃）」—— 作者本意就是「历练也算活动」，但那个语义**不能**拿来当「进入冷却」用。

修法（两处，均为单行；语义上「把 last_ts 的写权收归 entry 端点」）
--------------------------------------------------------------------------
  ① tickDungeonTracker：观测累加**不再触碰 last_ts**
       · ON CONFLICT 删去 `last_ts = excluded.last_ts,`
       · VALUES 的 last_ts 位由 `nowMs` 改为 `null`（新建行也留 NULL）
       · 列清单/占位符数**一字不动**（VALUES 6 + CASE 2 = 8 的绑定纪律保持）
     ⇒ 观测行 last_ts 恒为 NULL ⇒ cdLeftMs = 0；真进入过秘境的行由 entry 端点写 last_ts，
       冷却语义恢复正确（进一次 = 15 分钟）。
  ② dungeonStatusView：cdLeftMs 加 `count > 0` 前置条件
       · 兜底历史脏数据（0.9.15 之前 last_ts 已被历练污染、且 15 分钟内还没自然过期）
       · 语义：**没进过（count=0）就没有冷却**，与「冷却只在进入后开始」一致
       · `canEnter: count < cap && cdLeftMs === 0` 一行未动 ⇒ 自动同口径
  ③ 顺带修正 tickDungeonTracker 上方那条已失效的注释（文档准确性，非行为）

  · rogue 半边（rogue_last_ts / rogueCdLeftMs）**只由 entry 的 mode==="rogue" 分支写**，
    本来就没有本缺陷 ⇒ **一字不动**（r063 门禁面保持）。
  · /api/dungeon/entry 的读→判→写、403/200 语义、dungeonEntryVerdict、DDL **全部不动**。

锚点唯一性（实测，装配前基座 srv/index_v28.ts）
--------------------------------------------------------------------------
  · `const cdLeftMs = lastTs != null ? Math.max(0, cdMs - (nowMs - lastTs)) : 0;` → count == 1
  · `last_ts = excluded.last_ts,` → count == 2（另一处在 r063 的 rogue 分支，**不是**本环目标）
    ⇒ 本环锚点带上 `observed/adventure` 两行做区隔，锚点块实测 count == 1
  · tickDungeonTracker 绑定数组那一行 → count == 1

CLI 契约（照 srv_patch_r128.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回（写回前生成 .bak-r136-<时间戳>）；
  `--check` / `--selftest` 只校验不写。幂等：产物含 [r136dg] 则 SKIP（直接返回，不写盘）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403) / setInterval / PRAGMA（红线相对冻结）。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 每处替换 expect=1；门禁全绿 + round-trip 自证后才原子写回。
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r136dg]"

# ============================================================ 改动点（3 替换）

# ---- ① tickDungeonTracker：ON CONFLICT 不再写 last_ts + VALUES 传 null ----
E1_OLD = """       observed = observed + excluded.observed,
       adventure = adventure + excluded.adventure,
       last_ts = excluded.last_ts,
       anomaly = CASE WHEN observed + excluded.observed > ? OR count > ? THEN 1 ELSE anomaly END`,
    [userId, bjDate(nowMs), realm, adventure, nowMs,"""

E1_NEW = """       observed = observed + excluded.observed,   /* [r136dg] */
       adventure = adventure + excluded.adventure,
       anomaly = CASE WHEN observed + excluded.observed > ? OR count > ? THEN 1 ELSE anomaly END`,
    [userId, bjDate(nowMs), realm, adventure, null,"""

# ---- ② dungeonStatusView：cdLeftMs 只在「今天真进过」时才计 ----
E2_OLD = "  const cdLeftMs = lastTs != null ? Math.max(0, cdMs - (nowMs - lastTs)) : 0;"

E2_NEW = ("  /* [r136dg] last_ts 只由 /api/dungeon/entry 写入（观测累加不再刷它）；"
          "count=0 = 今天没进过 = 无冷却 */\n"
          "  const cdLeftMs = lastTs != null && count > 0 ? Math.max(0, cdMs - (nowMs - lastTs)) : 0;")

# ---- ③ 修正 tickDungeonTracker 上方已失效的注释 ----
E3_OLD = "// 无增量的存档上传不落行不刷 last_ts（last_ts 只反映秘境/历练活动，不是存档活跃）；"

E3_NEW = "// [r136dg] 观测累加**不再触碰 last_ts**（last_ts 写权收归 /api/dungeon/entry，即真正的「上次进入」）；"

EDITS = [
    ("R136B tickDungeonTracker 不再刷 last_ts", E1_OLD, E1_NEW),
    ("R136B cdLeftMs 加 count>0 前置", E2_OLD, E2_NEW),
    ("R136B 注释修正", E3_OLD, E3_NEW),
]

# ============================================================ 依赖（绝对在位）

REQUIRES = [
    ("const cdLeftMs = lastTs != null ? Math.max(0, cdMs - (nowMs - lastTs)) : 0;", 1,
     "dungeonStatusView 普通冷却行（r063 已扩 rogue 字段，此行未被动过）"),
    ("last_ts = excluded.last_ts,", 2,
     "dungeon_tracker 两处 last_ts 赋值（r063 rogue 分支 + tickDungeonTracker）"),
    ("const rogueCdLeftMs = rogueLastTs != null ? Math.max(0, cdMs - (nowMs - rogueLastTs)) : 0;", 1,
     "r063 rogue 冷却行（本环不动，仅证明在位）"),
    ("async function tickDungeonTracker(userId: number, d: { realm: number; adventure: number }): Promise<void> {", 1,
     "观测累加函数（r063 之后的形态）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    "DUNGEON_ENTRY_CD_MS",
    "DUNGEON_DAILY_CAP",
    "DUNGEON_ANOMALY_THRESHOLD",
    "dungeonEntryVerdict(",
    "dungeonStatusView(",
    "tickDungeonTracker(",
    "rogue_last_ts",
    "rogue_count",
    "observed = observed + excluded.observed,",
    "adventure = adventure + excluded.adventure,",
    "canEnter: count < cap && cdLeftMs === 0,",
    "rogueCanEnter: rogueCount < rogueCap && rogueCdLeftMs === 0,",
    "/api/dungeon/status",
    "INSERT INTO dungeon_tracker",
    "SELECT count, last_ts, rogue_count, rogue_last_ts FROM dungeon_tracker",
    "res.status(403",
    "require(",
    "setInterval(",
    "PRAGMA",
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-136B 普通秘境冷却恒 800s 根因修复（服务端环）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖（绝对在位）
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    gates = [
        ("R136B 幂等标记就位(x3)", MARK, 3),
        ("R136B cdLeftMs 新形态", "const cdLeftMs = lastTs != null && count > 0 ?", 1),
        ("R136B 旧 cdLeftMs 形态清零",
         "const cdLeftMs = lastTs != null ? Math.max(0, cdMs - (nowMs - lastTs)) : 0;", 0),
        ("R136B tickDungeonTracker 传 null", "realm, adventure, null,", 1),
        ("R136B tickDungeonTracker 传 nowMs 清零", "realm, adventure, nowMs,", 0),
        ("R136B 旧注释清零",
         "// 无增量的存档上传不落行不刷 last_ts（last_ts 只反映秘境/历练活动，不是存档活跃）；", 0),
        # rogue 半边一字未动（r063 面）
        ("冻结 r063 rogue 冷却行",
         "const rogueCdLeftMs = rogueLastTs != null ? Math.max(0, cdMs - (nowMs - rogueLastTs)) : 0;", 1),
        ("冻结 r063 rogue 写 last_ts", "rogue_last_ts = excluded.rogue_last_ts,", 1),
        ("冻结 entry 端点 last_ts 写入", "last_ts = excluded.last_ts,", 1),
        ("冻结 canEnter 口径", "canEnter: count < cap && cdLeftMs === 0,", 1),
    ]
    for needle in BASE_NEEDLES:
        label = "冻结 " + needle[:34].replace("\n", " ")
        gates.append((label, needle, base[needle]))

    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-46s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 语义自证：绑定数与占位符数仍精确相等（VALUES 6 + CASE 2 = 8）
    i_mark = out.find("observed = observed + excluded.observed,   /* [r136dg] */")
    i0 = out.rfind("INSERT INTO dungeon_tracker", 0, i_mark)
    i1 = out.find("`,", i0)
    sql = out[i0:i1] if (i0 >= 0 and i1 > i0) else ""
    q = sql.count("?")
    case_q = sql.count("CASE WHEN observed + excluded.observed > ? OR count > ?")
    blk = out[out.find("async function tickDungeonTracker"):]
    blk = blk[:blk.find("\n}\n") + 3]
    a0 = blk.find("[userId, bjDate(nowMs), realm, adventure, null,")
    args_line = blk[a0:blk.find("]", a0) + 1] if a0 >= 0 else ""
    n_args = args_line.count(",") + 1 if args_line else 0
    sem_ok = (q == 8 and case_q == 1 and n_args == 8)
    print("  [%s] %-46s VALUES?=%d CASE=%d args=%d" % ("OK" if sem_ok else "FAIL",
                                                       "R136B 绑定数自证(6+2=8)", q, case_q, n_args))
    if not sem_ok:
        fail("绑定数与占位符数不匹配")

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

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r136-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r136dg-", suffix=".tmp")
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
