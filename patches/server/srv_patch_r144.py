# -*- coding: utf-8 -*-
r"""
srv_patch_r144.py -- R-144 真实在线玩家名单（服务端 · SRV_CHAIN 新环）

台账原文（R-144，逐字）
--------------------------------------------------------------------------
  「现在的在线人物那里只显示数字，把这个做成一个按钮，点击可以展示在线人物列表，
    可以把交友的这些功能做进去」
用户 2026-10-03 二轮拍板（逐字）
  「做真实再现游玩的玩家，因为要加上游戏自带的功能，比如加好友，拜师，演武场这些
    已经加的多人功能」
用户 2026-10-03 23:20 确认在线判定口径：「最近 5 分钟内有活跃上报可以」

本环 = 唯一新增物：GET /api/online/players（真名单来源），字段/常量/SQL 逐字照
_chainstage/_r144_contract.md §2，不得自造。

在线判定（双源 UNION，任一源新鲜即算在线）
--------------------------------------------------------------------------
  ① active_sessions.last_seen（每 15s 心跳写入，ms epoch，权威）
  ② saves.updated_at（存档兜底；SQLite CURRENT_TIMESTAMP = **UTC**，
     ⇒ 必须 CAST(strftime('%s', updated_at) AS INTEGER) * 1000 转 epoch ms，
       不得直接当毫秒用）
  两源 UNION ALL 后 GROUP BY o.id 取 MAX(ts) 去重，ts >= cutoff 才算在线。

名字/境界口径（与 /api/friends/list 同源）
--------------------------------------------------------------------------
  name   = COALESCE(NULLIF(r.name, ''), u.username)
  realmName = realm_index==null ? '尚未入世' : (REALM_ORDER_FOR_RANKING[idx] || '')
  level  = realm_index==null ? null : realm_index*9 + realm_level

锚点唯一性（实测，装配前基座 srv/index_v28.ts）
--------------------------------------------------------------------------
  · app.post('/api/friends/add', authenticateToken, → count == 1（本环插入点之前）
  · 新标识符 ONLINE_WINDOW_MS / ONLINE_LIST_MAX / idx_active_sessions_last_seen
    → 基座 count 全为 0（脚本内断言，防止与既有代码撞名）

CLI 契约（照 srv_patch_r136.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r144-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r144online] 则 SKIP（直接返回，不写盘）。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403)（客户端见 403 强制登出，业务拒绝用 409）；
    不新增 setInterval / PRAGMA（红线相对冻结）。
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
MARK = "[r144online]"

# 新引入的标识符：装配前基座必须 0 次（防撞名）
NEW_IDS = [
    "/api/online/players",
    "ONLINE_WINDOW_MS",
    "ONLINE_LIST_MAX",
    "idx_active_sessions_last_seen",
]

# ============================================================ 改动点（1 替换）

# 插入锚点：好友域第一条路由（同一社交域，便于审阅）。契约实测 count==1。
E1_OLD = "app.post('/api/friends/add', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 15, keyFn: (req: any) => `fr:add:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {"

E1_NEW = """// ── 在线玩家名单（R-144 [r144online]）：最近 5 分钟内有活跃上报的真实玩家 ──
// 双源 UNION：active_sessions.last_seen（心跳，权威）∪ saves.updated_at（存档，兜底，
// UTC CURRENT_TIMESTAMP ⇒ 转 epoch ms）。字段/口径与 /api/friends/list 同源。
const ONLINE_WINDOW_MS = 5 * 60 * 1000;   // 用户拍板：最近 5 分钟内有活跃上报
const ONLINE_LIST_MAX = 50;
db.run('CREATE INDEX IF NOT EXISTS idx_active_sessions_last_seen ON active_sessions(last_seen)');

app.get('/api/online/players', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `onl:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const selfId = req.user.id;
  try {
    const cutoff = Date.now() - ONLINE_WINDOW_MS;
    const rows = await dbAll(
      `SELECT o.id AS id, COALESCE(NULLIF(r.name, ''), u.username) AS name,
              r.realm_index, r.realm_level, r.combat_power, MAX(o.ts) AS ts
       FROM (
         SELECT user_id AS id, last_seen AS ts FROM active_sessions WHERE last_seen >= ?
         UNION ALL
         SELECT user_id AS id, CAST(strftime('%s', updated_at) AS INTEGER) * 1000 AS ts
           FROM saves WHERE CAST(strftime('%s', updated_at) AS INTEGER) * 1000 >= ?
       ) o
       JOIN users u ON u.id = o.id
       LEFT JOIN rankings r ON r.user_id = o.id
       GROUP BY o.id
       ORDER BY ts DESC
       LIMIT ?`, [cutoff, cutoff, ONLINE_LIST_MAX]);
    const fr = await dbAll('SELECT friend_id FROM friendships WHERE user_id = ?', [selfId]);
    const friendSet = new Set((fr || []).map((x: any) => Number(x.friend_id)));
    const players = (rows || []).map((r: any) => ({
      id: Number(r.id),
      name: String(r.name || ''),
      realmIndex: r.realm_index == null ? null : Number(r.realm_index),
      realmName: r.realm_index == null ? '尚未入世' : (REALM_ORDER_FOR_RANKING[Number(r.realm_index)] || ''),
      realmLevel: r.realm_level == null ? null : Number(r.realm_level),
      level: r.realm_index == null ? null : Number(r.realm_index) * 9 + Number(r.realm_level || 1),
      combatPower: r.combat_power == null ? null : Number(r.combat_power),
      isFriend: Number(r.id) === selfId ? false : friendSet.has(Number(r.id)),
      isSelf: Number(r.id) === selfId,
      online: true,
    }));
    res.json({ now: Date.now(), windowMs: ONLINE_WINDOW_MS, total: players.length, players });
  } catch (e: any) { console.error('online players error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

""" + E1_OLD

EDITS = [
    ("R144 新增 GET /api/online/players", E1_OLD, E1_NEW),
]

# ============================================================ 依赖（绝对在位）

REQUIRES = [
    ("app.post('/api/friends/add', authenticateToken,", 1,
     "本环插入锚点（好友域第一条路由，契约实测 count==1）"),
    ("const REALM_ORDER_FOR_RANKING = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];", 1,
     "境界名表（/friends/list 与在线名单共用口径）"),
    ("function dbAll<T = any>(sql: string, params: any[] = []): Promise<T[]> {", 1,
     "dbAll 收口函数（本环单条查询用）"),
    ("app.get('/api/friends/list', authenticateToken,", 1,
     "名字/境界解析口径参照（COALESCE/REALM_ORDER/level 公式）"),
    ("UPDATE active_sessions SET last_seen = ?", 1,
     "心跳写 last_seen（在线第一源，ms epoch 权威）"),
    ("CREATE TABLE IF NOT EXISTS active_sessions", 1,
     "active_sessions 建表 DDL（本环索引建在其上）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    "/api/friends/add",
    "/api/friends/list",
    "/api/friends/remove",
    "/api/friends/gift",
    "/api/mentor/apprentice",
    "/api/arena/challenge",
    "/api/session/claim",
    "/api/session/heartbeat",
    "/api/session/state",
    "res.status(403",
    "require(",
    "setInterval(",
    "PRAGMA",
    "active_sessions",
    "REALM_ORDER_FOR_RANKING",
    "function dbAll",
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-144 真实在线玩家名单（服务端环）")
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

    # 2) 新标识符必须基座 0 次（防撞名）
    for nid in NEW_IDS:
        n = src.count(nid)
        if n != 0:
            fail("新标识符 %r 在基座出现 %d 次（期望 0，防撞名）" % (nid, n))

    # 3) 依赖（绝对在位）
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 4) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 5) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 6) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 7) 门禁
    gates = [
        ("R144 幂等标记就位", MARK, 1),
        ("R144 端点就位", "app.get('/api/online/players', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `onl:${req.user?.id ?? req.ip}` })", 1),
        ("R144 在线窗口常量", "const ONLINE_WINDOW_MS = 5 * 60 * 1000;", 1),
        ("R144 名单上限常量", "const ONLINE_LIST_MAX = 50;", 1),
        ("R144 索引幂等 DDL", "CREATE INDEX IF NOT EXISTS idx_active_sessions_last_seen ON active_sessions(last_seen)", 1),
        ("R144 双源第一源 last_seen", "SELECT user_id AS id, last_seen AS ts FROM active_sessions WHERE last_seen >= ?", 1),
        ("R144 双源第二源 saves 转 epoch", "CAST(strftime('%s', updated_at) AS INTEGER) * 1000 AS ts", 1),
        ("R144 参数顺序 cutoff/cutoff/limit", "[cutoff, cutoff, ONLINE_LIST_MAX]", 1),
        ("R144 去重聚合", "GROUP BY o.id", 1),
        ("R144 排序", "ORDER BY ts DESC", 1),
        ("R144 响应体字段", "res.json({ now: Date.now(), windowMs: ONLINE_WINDOW_MS, total: players.length, players });", 1),
        ("R144 isSelf 字段", "isSelf: Number(r.id) === selfId,", 1),
        ("R144 isFriend 自己恒 false", "isFriend: Number(r.id) === selfId ? false : friendSet.has(Number(r.id)),", 1),
        ("R144 错误语义 500 服务器繁忙", "console.error('online players error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' });", 1),
        ("R144 锚点原文仍在(1)", "app.post('/api/friends/add', authenticateToken,", 1),
        ("R144 未吞 /api/friends/list", "app.get('/api/friends/list', authenticateToken,", 1),
    ]
    for needle in BASE_NEEDLES:
        # 冻结基线：期望 = 基座计数 + 本环 EDITS 净新增（new-old）。
        # 这样既冻结既有面，又不会因新块合法引用同名标识符而误报。
        delta = sum(new.count(needle) - old.count(needle) for _, old, new in EDITS)
        label = "冻结 " + needle[:34].replace("\n", " ")
        gates.append((label, needle, base[needle] + delta))

    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-46s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    if not ok:
        fail("门禁未全绿，未写回")

    # 8) 语义自证：SQL 占位符数 == 绑定参数数（3 个 ? == [cutoff, cutoff, ONLINE_LIST_MAX]）
    i_mark = out.find("LIMIT ?`, [cutoff, cutoff, ONLINE_LIST_MAX]")
    i0 = out.rfind("SELECT o.id AS id, COALESCE(NULLIF(r.name, ''), u.username) AS name,", 0, i_mark)
    i1 = out.find("`,", i0)
    sql = out[i0:i1] if (i0 >= 0 and i1 > i0) else ""
    q = sql.count("?")
    sem_ok = (q == 3)
    print("  [%s] %-46s SQL?=%d args=3" % ("OK" if sem_ok else "FAIL", "R144 绑定数自证(3)", q))
    if not sem_ok:
        fail("SQL 占位符数与绑定参数数不匹配")

    # 9) 往返自证
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

    # 10) 改前 .bak + 原子写回
    bak = "%s.bak-r144-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r144onl-", suffix=".tmp")
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
