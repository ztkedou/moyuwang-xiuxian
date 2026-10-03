# -*- coding: utf-8 -*-
r"""
srv_patch_r148.py -- R-148 修复空库启动崩溃（服务端 · SRV_CHAIN 第 68 环，新末环）

问题（主控三组对照实测确认）
--------------------------------------------------------------------------
  0.9.20 的 R-144 在 srv/index_v28.ts 里加了一行 **模块加载期（顶层）** 语句：

      db.run('CREATE INDEX IF NOT EXISTS idx_active_sessions_last_seen ON active_sessions(last_seen)');

  它位于 active_sessions 建表语句 **之前** 执行（建表在 new sqlite3.Database(...)
  的 open 回调里 db.serialize(() => {...}) 块内，行 ~189）。结果：**全新/空数据库
  启动时服务端直接崩溃**：

      [Error: SQLITE_ERROR: no such table: main.active_sessions
       Emitted 'error' event on Statement instance at: ]

  对照实验：0.9.20+空库 → 崩溃；0.9.19+空库 → 正常(84 表)；删掉该行+空库 → 正常；
  把该行移入建表块内(紧跟 active_sessions 的 CREATE TABLE 之后)+空库 → 正常，84 表，
  且 idx_active_sessions_last_seen 成功创建。 ⇒ 采用“移入建表块内”修法。

本环 = 两处精确替换（各 expect == 1）
--------------------------------------------------------------------------
  ① 删除顶层那一行（连同换行）——它在建表前执行，空库必崩。
  ② 在 active_sessions 建表块内（CREATE TABLE 之后）补回同一句建索引 DDL，
     缩进 6 空格、用反引号模板串，与同块其它语句风格一致。语义完全等价，
     仅执行时机挪到建表之后。

CLI 契约（照 srv_patch_r144.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r148-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r148boot] 则 SKIP（直接返回，不写盘）。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII；每处替换 expect=1；门禁全绿 + round-trip 自证后才原子写回。
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（写进替换②新增语句上方的独立注释行；TS 源码 ⇒ 用 //）
MARK = "[r148boot]"

# ============================================================ 改动点（2 替换）

# 替换 ①：顶层那行（建表前执行，空库崩溃的根因）——整行删除（连同换行）。
E1_OLD = "db.run('CREATE INDEX IF NOT EXISTS idx_active_sessions_last_seen ON active_sessions(last_seen)');\n"
E1_NEW = ""

# 替换 ②：active_sessions 建表块（缩进 6 空格起，逐字）。
E2_OLD = (
    "      db.run(`\n"
    "        CREATE TABLE IF NOT EXISTS active_sessions (\n"
    "          user_id INTEGER PRIMARY KEY,\n"
    "          session_id TEXT NOT NULL,\n"
    "          device TEXT,\n"
    "          claimed_at INTEGER NOT NULL,\n"
    "          last_seen INTEGER NOT NULL\n"
    "        )\n"
    "      `);\n"
)

# 在 CREATE TABLE 之后补回建索引语句；上方加独立注释行承载幂等标记。
R148_ADDED = (
    "      // [r148boot] R-148：在线索引从模块顶层移到建表之后，空库启动不再 no such table\n"
    "      db.run(`CREATE INDEX IF NOT EXISTS idx_active_sessions_last_seen ON active_sessions(last_seen)`);\n"
)
E2_NEW = E2_OLD + R148_ADDED

EDITS = [
    ("R148 删除顶层建索引行", E1_OLD, E1_NEW),
    ("R148 建表块内补回建索引", E2_OLD, E2_NEW),
]

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("const ONLINE_LIST_MAX = 50;", 1,
     "R-144 常量仍在（顶层行删除点的上下文）"),
    ("app.get('/api/online/players', authenticateToken,", 1,
     "R-144 在线名单端点仍在（不得被误伤）"),
    ("UPDATE active_sessions SET last_seen = ?", 1,
     "心跳写 last_seen（active_sessions 索引目标列）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    "idx_active_sessions_last_seen",
    "CREATE TABLE IF NOT EXISTS active_sessions",
    "active_sessions",
    "app.get('/api/online/players'",
    "/api/friends/list",
    "res.status(403",
    "require(",
    "setInterval(",
    "PRAGMA",
]

# 用于 round-trip 与门禁的稳定针脚（纯 ASCII）
TOPLEVEL_NEEDLE = "db.run('CREATE INDEX IF NOT EXISTS idx_active_sessions_last_seen ON active_sessions(last_seen)');"
BLOCK_NEEDLE = "      db.run(`CREATE INDEX IF NOT EXISTS idx_active_sessions_last_seen ON active_sessions(last_seen)`);"


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out: str, base: dict) -> list:
    """返回五元组列表 (label, needle, expect, op, note)。"""
    g = [
        ("R148 顶层建索引行已清零", TOPLEVEL_NEEDLE, 0, "==",
         "顶层那行（单引号版）必须消失，否则空库仍崩"),
        ("R148 建表块内建索引行就位", BLOCK_NEEDLE, 1, "==",
         "反引号版 + 6 空格缩进，必须恰好 1 处"),
        ("R148 索引标识符总数 == 1", "idx_active_sessions_last_seen", 1, "==",
         "删 1 补 1，净 0；最终必须恰好 1 处"),
        ("R148 索引标识符仍在(>=1)", "idx_active_sessions_last_seen", 1, ">=",
         "保险：标识符不得被整段删光"),
        ("R148 建表语句未误伤", "CREATE TABLE IF NOT EXISTS active_sessions", 1, "==",
         "active_sessions 建表 DDL 必须仍在"),
        ("R148 幂等标记就位", MARK, 1, "==",
         "标记恰好 1 处，供幂等 SKIP 使用"),
        ("R148 R-144 端点未误伤", "app.get('/api/online/players', authenticateToken,", 1, "==",
         "在线名单端点仍在"),
        ("R148 R-144 常量未误伤", "const ONLINE_LIST_MAX = 50;", 1, "==",
         "R-144 常量仍在"),
    ]
    for needle in BASE_NEEDLES:
        # 冻结基线：期望 = 基座计数 + 本环 EDITS 净新增（new-old）。
        delta = sum(new.count(needle) - old.count(needle) for _, old, new in EDITS)
        label = "冻结 " + needle[:34].replace("\n", " ")
        g.append((label, needle, base[needle] + delta, "==", "冻结既有面"))
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-148 修复空库启动崩溃（服务端环）")
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
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
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

    # 7) 往返自证：除两处外其余字节完全一致
    #    out 应 == src 删 E1_OLD 后、再把 E2_OLD 换成 E2_NEW
    expected = src.replace(E1_OLD, E1_NEW, 1).replace(E2_OLD, E2_NEW, 1)
    if out != expected:
        fail("round-trip(正向重构) mismatch")
    #    逆向：去掉新增行应还原为 “src 去掉顶层那行”
    stripped = out.replace(R148_ADDED, "", 1)
    if stripped != src.replace(E1_OLD, "", 1):
        fail("round-trip(逆向) mismatch：新增内容之外字节被改动")
    #    再把顶层那行按原位置插回，必须与原文逐字节相同
    i = src.find(E1_OLD)
    if i < 0:
        fail("round-trip：原文找不到 E1_OLD 位置")
    if src != stripped[:i] + E1_OLD + stripped[i:]:
        fail("round-trip(回插) mismatch：除两处外字节不一致")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r148-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r148boot-", suffix=".tmp")
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
