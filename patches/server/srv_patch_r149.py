# -*- coding: utf-8 -*-
r"""
srv_patch_r149.py -- R-149 修「挂机收益恒 0」：away 不得丢弃未领取的离线窗口（SRV_CHAIN 第 69 环，新末环）

问题（新机线上实测复现 + 迁移快照对账）
--------------------------------------------------------------------------
  现象：玩家离线两天后上线，「挂机收益」面板恒 0。

  机制（R-021 的离线窗口锚点）：
    · away（POST /api/session/presence {state:'away'}）把 last_seen_at 写成
      **本行当前 updated_at**；客户端在线时每 10s 心跳存档会刷新 updated_at，
      所以「在线时点 away」⇒ last_seen_at ≈ 现在。
    · back 把 last_resume_at 写成 Date.now()。
    · 窗口 = [max(last_seen_at, offline_claimed_until), last_resume_at]。

  客户端上报 away 的时机包含 visibilitychange→hidden、pagehide、beforeunload。
  于是「登录 → 切走一次（或刷新一次）→ 切回」就会产生一对 away/back：
      last_seen_at 被前移到「现在」，last_resume_at 又紧跟其后，
      窗口被压成几十秒 < OFFLINE_MIN_MS(5min) ⇒ 面板恒 0。
  ★ 更致命的是：上一个**尚未领取**的离线窗口会被这一对事件永久丢弃——
    而客户端只在「打开挂机收益面板」时才 GET /api/offline/report，
    所以玩家根本来不及领，窗口就没了。

  实测证据（user_id=13 ztkedou）：
    · 迁移快照 opt-yl_sqlsnap_20261004：last_seen_at = 2026-10-03 07:04:53Z（= 本地 15:04:53，正是"两天前"）
      ⇒ 迁移**没有**破坏状态，锚点本来是健康的。
    · 当前线上库：last_seen_at = 2026-10-05 15:52:39Z、last_resume_at = 2026-10-05 15:53:14Z
      ⇒ 被今天的一次 away/back（相隔 35 秒）冲掉。
    · nginx access.log 实证：23:52:42 presence、23:53:14 presence、23:53:49 GET /api/offline/report → 0。
    · 测试账号复现：造「last_seen_at=2天前 + updated_at=现在」→ 报告 hours=8/expGain=2304/claimable=true；
      再发一次 away+back → hours=0/claimable=false。100% 复现。

修法（1 处精确替换）
--------------------------------------------------------------------------
  away 分支：若存在**尚未领取**的待结算窗口
    （last_seen_at 有效且 > offline_claimed_until，或 offline_claimed_until 非法/为空），
  则保持较早的锚点（anchor = min(last_seen_at, 当前 updated_at)）；否则照旧前移。

  语义：away 只表示「此刻离开」，不得把一段**还没结算**的离线时长作废。
  领取过（offline_claimed_until 已覆盖旧锚点）后，锚点照常前移 ⇒ 正常玩法逐位不变。

  ★ 红线：offlineRewards()（expGain/stoneGain 公式）、offlineWindow() 本体、
    offlineAnchor() 本体、OFFLINE_* 常量、月卡判定、入账与钳制逻辑 **一行未动**。
    本环只改 away 分支里 last_seen_at 的**取值**，不新增端点、不改响应结构。

CLI 契约（照 srv_patch_r148.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r149-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r149anchor] 则 SKIP（直接返回，不写盘）。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII；替换 expect=1；门禁全绿 + round-trip 自证后才原子写回。
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（写进替换新增的独立注释行；TS 源码 ⇒ 用 //）
MARK = "[r149anchor]"

# ============================================================ 改动点（1 替换）

# 替换 ①：away 分支。旧口径无条件前移 last_seen_at（丢弃未领取窗口）。
E1_OLD = (
    "    if (st === 'away') {\n"
    "      const row: any = await dbGet('SELECT updated_at FROM saves WHERE user_id = ?', [req.user.id]);\n"
    "      const at = parseDbTimeMs(row && row.updated_at);\n"
    "      if (row && at != null) await dbRun('UPDATE saves SET last_seen_at = ? WHERE user_id = ?', [at, req.user.id]);\n"
    "    } else {\n"
)

E1_NEW = (
    "    if (st === 'away') {\n"
    "      // [r149anchor] R-149：away 不得丢弃「尚未领取」的离线窗口。\n"
    "      //   旧口径无条件把 last_seen_at 前移到当前 updated_at ⇒ 登录后只要切走一次再切回\n"
    "      //   （visibilitychange hidden→visible / pagehide / 刷新），之前攒下的离线窗口就被压成\n"
    "      //   几十秒 ⇒ /api/offline/report 恒 0（真 bug）。\n"
    "      //   新口径：若存在未领取的待结算窗口（last_seen_at 有效且 > offline_claimed_until），\n"
    "      //   保持较早锚点；否则照旧前移。\n"
    "      //   ★ 红线：offlineRewards()/offlineWindow()/offlineAnchor()/OFFLINE_* 常量 一行未动。\n"
    "      const row: any = await dbGet('SELECT updated_at, last_seen_at, offline_claimed_until FROM saves WHERE user_id = ?', [req.user.id]);\n"
    "      const at = parseDbTimeMs(row && row.updated_at);\n"
    "      if (row && at != null) {\n"
    "        const prev = Number(row.last_seen_at);\n"
    "        const cl = Number(row.offline_claimed_until);\n"
    "        const hasPending = Number.isFinite(prev) && prev > 0 && (!Number.isFinite(cl) || prev > cl);\n"
    "        const anchor = hasPending ? Math.min(prev, at) : at;\n"
    "        await dbRun('UPDATE saves SET last_seen_at = ? WHERE user_id = ?', [anchor, req.user.id]);\n"
    "      }\n"
    "    } else {\n"
)

EDITS = [
    ("R149 away 分支保持未领取锚点", E1_OLD, E1_NEW),
]

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("app.post('/api/session/presence'", 1,
     "presence 端点仍在（本环唯一改动点）"),
    ("app.get('/api/offline/report'", 1,
     "离线报告端点仍在（不得被误伤）"),
    ("app.post('/api/offline/claim'", 1,
     "离线领取端点仍在（不得被误伤）"),
    ("function offlineAnchor(", 1,
     "锚点纯函数仍在（本环不得改其本体）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    "function offlineAnchor(",
    "function offlineWindow(",
    "function offlineRewards(",
    "function hasMonthCard(",
    "function offlineCapHours(",
    "function offlineRatePerHour(",
    "const OFFLINE_MIN_MS = 5 * 60 * 1000;",
    "const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;",
    "const OFFLINE_RATE_MONTHCARD_PER_HOUR = 0.006;",
    "const OFFLINE_STONE_RATIO = 0.1;",
    "offline_claimed_until",
    "parseDbTimeMs",
    "res.status(403",
    "require(",
    "setInterval(",
    "PRAGMA",
    # ★ 这行 SELECT 在别处还有 2 处合法使用（7840 每日任务 / 10128 师徒），
    #   所以只冻结总数（本环删 1 补 1，净 0），**不能**断言清零。
    "SELECT updated_at FROM saves WHERE user_id = ?",
]

# 用于门禁的稳定针脚（纯 ASCII）
NEW_SQL_NEEDLE = "SELECT updated_at, last_seen_at, offline_claimed_until FROM saves WHERE user_id = ?"
NEW_GUARD_NEEDLE = "const hasPending = Number.isFinite(prev) && prev > 0 && (!Number.isFinite(cl) || prev > cl);"
NEW_ANCHOR_NEEDLE = "const anchor = hasPending ? Math.min(prev, at) : at;"
OLD_ASSIGN_NEEDLE = "if (row && at != null) await dbRun('UPDATE saves SET last_seen_at = ? WHERE user_id = ?', [at, req.user.id]);"


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out: str, base: dict) -> list:
    """返回五元组列表 (label, needle, expect, op, note)。"""
    g = [
        ("R149 旧无条件前移语句已清零", OLD_ASSIGN_NEEDLE, 0, "==",
         "旧那行（丢弃未领取窗口的根因）必须消失"),
        ("R149 新 SELECT 列清单就位", NEW_SQL_NEEDLE, 1, "==",
         "须同时取 last_seen_at 与 offline_claimed_until"),
        ("R149 未领取判定就位", NEW_GUARD_NEEDLE, 1, "==",
         "hasPending 判定恰好 1 处"),
        ("R149 锚点取值就位", NEW_ANCHOR_NEEDLE, 1, "==",
         "anchor = 较早者，恰好 1 处"),
        ("R149 幂等标记就位", MARK, 1, "==",
         "标记恰好 1 处，供幂等 SKIP 使用"),
        ("R149 presence 端点未误伤", "app.post('/api/session/presence'", 1, "==",
         "端点仍在"),
        ("R149 report 端点未误伤", "app.get('/api/offline/report'", 1, "==",
         "端点仍在"),
        ("R149 claim 端点未误伤", "app.post('/api/offline/claim'", 1, "==",
         "端点仍在"),
    ]
    for needle in BASE_NEEDLES:
        # 冻结基线：期望 = 基座计数 + 本环 EDITS 净新增（new-old）。
        delta = sum(new.count(needle) - old.count(needle) for _, old, new in EDITS)
        label = "冻结 " + needle[:34].replace("\n", " ")
        g.append((label, needle, base[needle] + delta, "==", "冻结既有面"))
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-149 修挂机收益恒 0（服务端环）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：产物含标记则 SKIP（直接返回，不写盘，rc=0）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖（绝对在位）
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点计数（纯 ASCII，必须恰好 1）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:200]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁（五元组，op 支持 == / >=）
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-42s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证：除这一处外其余字节完全一致
    if out != src.replace(E1_OLD, E1_NEW, 1):
        fail("round-trip(正向重构) mismatch")
    #    逆向：去掉新增内容应逐字节还原原文
    if out.replace(E1_NEW, E1_OLD, 1) != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    #    改动点必须真的只动了 E1_OLD 那一段
    if out.count(E1_NEW) != 1:
        fail("round-trip：E1_NEW 出现次数 != 1")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r149-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r149anchor-", suffix=".tmp")
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
