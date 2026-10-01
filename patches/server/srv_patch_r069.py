# -*- coding: utf-8 -*-
r"""
srv_patch_r069.py -- R-069 修行统计「时间恒为 0 分钟」修复（服务端半边 · 待 lead 裁定接线）

【根因（线上实测实证，见 报告_R069_R070_20261001.md）】
--------------------------------------------------------------------------
  修行统计面板（客户端 `function YlxwTStats()`，读 GET /api/stats/me → stats_daily）
  的「分钟」列恒为 0。线上库实证：
      SELECT COUNT(*) total, SUM(minutes>0) FROM stats_daily  ->  total=20, mpos=0
      而 saves.save_data.player.playTime 正常非零（玩家 15 = 22,862,787 ms ≈ 381 分钟）
  ⇒ 不是「客户端没上传」，而是服务端差值口径把「不足 1 分钟的余量」逐次丢弃：

      computeStatsDeltas()：
        minutes: Math.floor(up(prev.playTimeMs, next.playTimeMs) / 60000)

      prev = 上一次已落库存档的 playTime（srv:2377 extractCounters(oldSd)），
      而客户端心跳/自动存档约每 10s 一次（`ylHidePush` 10s 节流 + player 变更 1~3s 防抖）
      ⇒ 每次差值的 next-prev ≈ 10,000ms < 60,000ms ⇒ Math.floor 恒 0，
        且每次存档都会把基线推进到新值，余量永远攒不起来 ⇒ minutes 恒 0。

【本环修法：余量携带（内存态，零 schema 迁移）】
--------------------------------------------------------------------------
  把「不足 1 分钟的 playTime 余量」按玩家累加在进程内存里，凑满 60,000ms 才计 1 分钟；
  计掉的部分从余量里扣除，剩余继续留到下一次存档。

      total = carry(userId) + max(0, next.playTimeMs - prev.playTimeMs)
      mins  = floor(total / 60000)
      carry(userId) = total - mins * 60000

  只覆盖 stats_daily.minutes 这一路：computeStatsDeltas 的 exp/silver/kills 一行不动，
  tickMentorTax（用同一 StatsDelta）读的是 exp/silver/kills，minutes 与它无关 ⇒ 零影响。
  不新增列、不改 SELECT/UPDATE/INSERT、不迁移数据库 ⇒ 存档路径零风险。
  代价：进程重启丢「不足 1 分钟」的余量（每人每次重启最多丢 59 秒），可接受。

  ★ 为什么不用新列（stats_play_ms）：要动 saves 的 CREATE/SELECT/UPDATE/INSERT 五处，
    在生产存档主路径上 blast radius 过大；本环取最小面。若日后要「重启不丢」，
    可平滑升级为列存储，本环的纯函数语义不变。

CLI 契约（照 srv_patch_050.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回；`--check` / `--selftest` 只校验不写。
  幂等：产物里已含 `[r069min]` 则 SKIP。
  lead 接线：localtest/chain_build.py 的 SRV_CHAIN 链尾追加 'srv_patch_r069.py'。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval` / `PRAGMA`。
  · 每处替换 expect=1，命中数不符即中止；round-trip 自证后原子写回。
  · ⛔ 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；⛔ 不改任何既有 srv_patch_*.py。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

MARK = "[r069min]"

# ============================================================ 改动点

# ① 余量携带助手：插在 tickStatsDaily 定义之前（函数声明提升，位置安全；
#    常量 STATS_PLAY_CARRY 在模块求值期初始化，路由处理函数在其后执行 ⇒ 无 TDZ 风险）
HELPER_ANCHOR = "async function tickStatsDaily(userId: number, d: StatsDelta): Promise<void> {"

HELPER = (
    "// [r069min] R-069：stats_daily.minutes 余量携带（修「修行统计·时间恒 0 分钟」）\n"
    "//   根因：minutes = floor((next.playTimeMs - prev.playTimeMs)/60000)，而 prev 取自上一次\n"
    "//   已落库存档、客户端约每 10s 存档一次 ⇒ 每次差值 <60s，floor 恒 0，余量被逐次丢弃。\n"
    "//   修法：按玩家在内存里累加余量，凑满 1 分钟才计 1；只作用于 minutes 这一路。\n"
    "//   重启丢 <1 分钟余量，可接受（不引入 schema 迁移）。\n"
    "const STATS_PLAY_CARRY = new Map<number, number>();\n"
    "function statsMinutesCarried(userId: number, prevMs: number, nextMs: number): number {\n"
    "  const up = nextMs > prevMs ? nextMs - prevMs : 0;\n"
    "  const total = (STATS_PLAY_CARRY.get(userId) || 0) + up;\n"
    "  const mins = Math.floor(total / 60000);\n"
    "  STATS_PLAY_CARRY.set(userId, total - mins * 60000);\n"
    "  return mins;\n"
    "}\n"
)

# ② /api/save 的 UPDATE 分支（已有行）：minutes 改走余量携带
E2_OLD = ("if (prevCounters) tickStatsDaily(req.user.id, computeStatsDeltas(prevCounters, "
          "extractCounters(saveData))).catch((e: any) => console.error('stats tick error:', "
          "(e as any)?.message || e)); // Y15 埋点：同源差值，fire-and-forget")
E2_NEW = ("if (prevCounters) { const __sc = extractCounters(saveData); const __sd = "
          "computeStatsDeltas(prevCounters, __sc); __sd.minutes = statsMinutesCarried("
          "req.user.id, prevCounters.playTimeMs, __sc.playTimeMs); tickStatsDaily(req.user.id, __sd)"
          ".catch((e: any) => console.error('stats tick error:', (e as any)?.message || e)); } "
          "// Y15 埋点：同源差值（[r069min] minutes 走余量携带）")

# ③ /api/save 的 INSERT 分支（首存）：同上
E3_OLD = ("if (prevCounters) tickStatsDaily(req.user.id, computeStatsDeltas(prevCounters, "
          "extractCounters(saveData))).catch((e: any) => console.error('stats tick error:', "
          "(e as any)?.message || e)); // Y15 埋点（首存=全零基线）")
E3_NEW = ("if (prevCounters) { const __sc = extractCounters(saveData); const __sd = "
          "computeStatsDeltas(prevCounters, __sc); __sd.minutes = statsMinutesCarried("
          "req.user.id, prevCounters.playTimeMs, __sc.playTimeMs); tickStatsDaily(req.user.id, __sd)"
          ".catch((e: any) => console.error('stats tick error:', (e as any)?.message || e)); } "
          "// Y15 埋点（首存=全零基线；[r069min] minutes 走余量携带）")

EDITS = [
    ("R069 注入余量携带助手", HELPER_ANCHOR, HELPER + HELPER_ANCHOR),
    ("R069 UPDATE 分支 minutes 走余量携带", E2_OLD, E2_NEW),
    ("R069 INSERT 分支 minutes 走余量携带", E3_OLD, E3_NEW),
]

REQUIRES = [
    (HELPER_ANCHOR, 1, "tickStatsDaily 定义必须在位（助手插它之前）"),
    (E2_OLD, 1, "UPDATE 分支的 tickStatsDaily 调用必须在位（本环唯一改点之一）"),
    (E3_OLD, 1, "INSERT 分支的 tickStatsDaily 调用必须在位（本环唯一改点之一）"),
    ("function computeStatsDeltas(prev: StatCounters, next: StatCounters): StatsDelta {", 1,
     "差值纯函数必须在位（本环不改它，只覆盖返回值里的 minutes）"),
    ("minutes: Math.floor(up(prev.playTimeMs, next.playTimeMs) / 60000)", 1,
     "旧 floor 口径必须在位（本环不删它，改为调用侧覆盖）"),
    ("app.post('/api/save'", 1, "/api/save 端点必须在位（改动经它生效）"),
]

BASE_NEEDLES = ["res.status(403", "setInterval(", "PRAGMA", "require(",
                "function computeStatsDeltas(",
                "minutes: Math.floor(up(prev.playTimeMs, next.playTimeMs) / 60000)",
                "app.post('/api/save'"]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-069 修行统计分钟余量携带环")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:90], n, cnt, why))

    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    base = {k: src.count(k) for k in BASE_NEEDLES}

    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    gates = [
        # ---- 本环改动 ----
        ("R69 余量携带助手已注入", "function statsMinutesCarried(userId: number, prevMs: number, nextMs: number): number {", 1),
        ("R69 余量表已注入", "const STATS_PLAY_CARRY = new Map<number, number>();", 1),
        ("R69 余量=总量-整分钟", "STATS_PLAY_CARRY.set(userId, total - mins * 60000);", 1),
        ("R69 UPDATE 分支已改余量携带", E2_NEW, 1),
        ("R69 INSERT 分支已改余量携带", E3_NEW, 1),
        ("R69 调用点已改余量携带（两处）", "__sd.minutes = statsMinutesCarried(req.user.id, prevCounters.playTimeMs, __sc.playTimeMs);", 2),
        ("R69 幂等标记就位", MARK, 3),
        ("R69 旧调用点已清零（两处）",
         "if (prevCounters) tickStatsDaily(req.user.id, computeStatsDeltas(prevCounters, extractCounters(saveData)))", 0),
        # ---- 冻结：差值纯函数与旧 floor 口径一字不动（本环只在调用侧覆盖 minutes）----
        ("冻结 computeStatsDeltas 未动",
         "function computeStatsDeltas(prev: StatCounters, next: StatCounters): StatsDelta {",
         base["function computeStatsDeltas("]),
        ("冻结 旧 minutes floor 口径仍在",
         "minutes: Math.floor(up(prev.playTimeMs, next.playTimeMs) / 60000)",
         base["minutes: Math.floor(up(prev.playTimeMs, next.playTimeMs) / 60000)"]),
        ("冻结 /api/save 端点仍在", "app.post('/api/save'", base["app.post('/api/save'"]),
        # ---- 红线 ----
        ("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]),
        ("红线 未新增 require(", "require(", base["require("]),
        ("红线 未新增 setInterval", "setInterval(", base["setInterval("]),
        ("红线 未新增 PRAGMA", "PRAGMA", base["PRAGMA"]),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-44s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 语义自证：助手定义唯一；两处调用点都在；旧直调 0 处；tickMentorTax 未受影响
    sem_ok = (
        out.count("function statsMinutesCarried(") == 1
        and out.count("statsMinutesCarried(req.user.id,") == 2
        and out.count("if (prevCounters) tickStatsDaily(") == 0
        and out.count("if (prevCounters) tickMentorTax(") == 2
    )
    ok = ok and sem_ok
    print("  [%s] %-44s helper=%d calls=%d mentor=%d"
          % ("OK" if sem_ok else "FAIL", "R69 语义自证(助手唯一/两处生效/师徒链未动)",
             out.count("function statsMinutesCarried("),
             out.count("statsMinutesCarried(req.user.id,"),
             out.count("if (prevCounters) tickMentorTax(")))

    if not ok:
        fail("门禁未全绿，未写回")

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

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r069min-", suffix=".tmp")
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
