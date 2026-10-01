# -*- coding: utf-8 -*-
"""
yl 服务端补丁 —— 单写者会话锁（session-lock / 顶号机制）

输入  src/index-session-base.ts   (从 /opt/yl/server/index.ts scp 的原始副本)
输出  src/index-session.new.ts

契约：
  1. 新表 active_sessions（user_id PK / session_id / device / claimed_at / last_seen，毫秒时间戳）
  2. POST /api/session/claim     -> { ok, sessionId, superseded }
  3. POST /api/session/heartbeat -> 200 { ok } | 409 { error:'session_superseded' }
  4. GET  /api/session/state     -> { sessionId, active }
  5. POST /api/save 前置会话校验：带头且不匹配 -> 409；头缺失/无行 -> 放行

所有替换均带唯一性断言（old 必须恰好出现 N 次），任一不符立即 sys.exit(1)，绝不产出半成品。
同时硬校验输入文件 md5，防止在错版本上打补丁。
"""
import sys, hashlib

SRC = 'src/index-session-base.ts'
DST = 'src/index-session.new.ts'

# 线上基线版本硬校验（scp 自 /opt/yl/server/index.ts，2026-09-27）
EXPECT_MD5 = '1cebe6277955554d4387ff7691f0e49c'
EXPECT_SIZE = 515383


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


# ─────────────── 新代码块 ───────────────

# A. active_sessions 建表 DDL（插在 save_snapshots 索引之后）
DDL_OLD = "      db.run(`CREATE INDEX IF NOT EXISTS idx_save_snapshots_user ON save_snapshots(user_id, id DESC)`);"
DDL_NEW = DDL_OLD + """

      // 单写者会话锁（session-lock）：同一账号当前活跃写入会话（顶号判定）。
      // 时间戳统一毫秒（Date.now()，与本文件其它 INTEGER 时间戳口径一致）。
      db.run(`
        CREATE TABLE IF NOT EXISTS active_sessions (
          user_id INTEGER PRIMARY KEY,
          session_id TEXT NOT NULL,
          device TEXT,
          claimed_at INTEGER NOT NULL,
          last_seen INTEGER NOT NULL
        )
      `);"""

# B. 会话路由（插在 POST /api/save 之前）
ROUTES_OLD = "app.post('/api/save', authenticateToken, (req: any, res: any) => {\n  const saveData = req.body;"
ROUTES_NEW = """// ── 单写者会话锁（session-lock）：同一账号仅一个活跃写入会话，支持跨端顶号 ──
// claim 认领会话 / heartbeat 每 ≤60s 续期 / save 带 X-YL-Session 校验归属。
// 兼容：不带 X-YL-Session 的 /api/save 一律放行（老客户端、GM 脚本、/yl/apps/* 等调用方）。
const SESSION_STALE_MS = 60000; // 心跳静默超过 60s 视为会话已失效

app.post('/api/session/claim', authenticateToken, async (req: any, res: any) => {
  try {
    const device = typeof req.body?.device === 'string' ? req.body.device : null;
    const now = Date.now();
    const row: any = await dbGet('SELECT session_id, last_seen FROM active_sessions WHERE user_id = ?', [req.user.id]);
    const superseded = !!(row && Number(row.last_seen) > now - SESSION_STALE_MS);
    const sessionId = crypto.randomUUID();
    await dbRun(
      'INSERT OR REPLACE INTO active_sessions (user_id, session_id, device, claimed_at, last_seen) VALUES (?, ?, ?, ?, ?)',
      [req.user.id, sessionId, device, now, now]
    );
    res.json({ ok: true, sessionId, superseded });
  } catch (e: any) {
    console.error('session claim error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

app.post('/api/session/heartbeat', authenticateToken, async (req: any, res: any) => {
  try {
    const sid = req.headers['x-yl-session'];
    const row: any = await dbGet('SELECT session_id FROM active_sessions WHERE user_id = ?', [req.user.id]);
    if (!row || !sid || row.session_id !== sid) {
      return res.status(409).json({ error: 'session_superseded' });
    }
    await dbRun('UPDATE active_sessions SET last_seen = ? WHERE user_id = ?', [Date.now(), req.user.id]);
    res.json({ ok: true });
  } catch (e: any) {
    console.error('session heartbeat error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

app.get('/api/session/state', authenticateToken, async (req: any, res: any) => {
  try {
    const row: any = await dbGet('SELECT session_id, last_seen FROM active_sessions WHERE user_id = ?', [req.user.id]);
    const active = !!(row && Number(row.last_seen) > Date.now() - SESSION_STALE_MS);
    res.json({ sessionId: row ? row.session_id : null, active });
  } catch (e: any) {
    console.error('session state error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

app.post('/api/save', authenticateToken, async (req: any, res: any) => {
  // 单写者会话锁：带 X-YL-Session 时校验归属；头缺失放行（兼容老客户端/GM/其它调用方）
  const reqSessionId = req.headers['x-yl-session'];
  if (reqSessionId) {
    try {
      const srow: any = await dbGet('SELECT session_id FROM active_sessions WHERE user_id = ?', [req.user.id]);
      if (srow && srow.session_id !== reqSessionId) {
        return res.status(409).json({ error: 'session_superseded' });
      }
    } catch (e: any) {
      console.error('save session check error:', e?.message || e); // 会话锁查询异常不阻塞存档路径
    }
  }
  const saveData = req.body;"""

# 替换清单：(label, old, new, 期望命中数)
R = [
    ('DDL-active_sessions', DDL_OLD, DDL_NEW, 1),
    ('ROUTES+SAVE-guard', ROUTES_OLD, ROUTES_NEW, 1),
]


def main() -> None:
    raw = open(SRC, 'rb').read()
    got_md5 = md5(raw)
    if got_md5 != EXPECT_MD5 or len(raw) != EXPECT_SIZE:
        print('=== 基线版本校验失败，未写任何文件 ===')
        print('  期望 md5 %s / %d bytes' % (EXPECT_MD5, EXPECT_SIZE))
        print('  实际 md5 %s / %d bytes' % (got_md5, len(raw)))
        sys.exit(1)

    s = raw.decode('utf-8')

    fails = []
    for lbl, old, new, n in R:
        c = s.count(old)
        if c != n:
            fails.append('  [FAIL] %-24s old 出现 %d 次（期望 %d）' % (lbl, c, n))
    if fails:
        print('=== 断言失败，未写任何文件 ===')
        print('\n'.join(fails))
        sys.exit(1)

    for lbl, old, new, n in R:
        s = s.replace(old, new, n)

    out = s.encode('utf-8')
    open(DST, 'wb').write(out)

    print('=== 全部 %d 条替换成功 ===' % len(R))
    print('输入 md5 %s  %d bytes' % (got_md5, len(raw)))
    print('输出 md5 %s  %d bytes' % (md5(out), len(out)))

    # 反查：旧锚点应消失 / 新代码应出现指定次数
    chk = [
        (DDL_OLD, 1),   # DDL_NEW 以 DDL_OLD 为前缀，替换后该锚点仍保留 1 次
        ("CREATE TABLE IF NOT EXISTS active_sessions", 1),
        ("app.post('/api/session/claim'", 1),
        ("app.post('/api/session/heartbeat'", 1),
        ("app.get('/api/session/state'", 1),
        ("app.post('/api/save', authenticateToken, (req: any, res: any) => {", 0),
        ("app.post('/api/save', authenticateToken, async (req: any, res: any) => {", 1),
        ("x-yl-session", 2),           # heartbeat 头读取 1 + save 头读取 1（注释为 X-YL-Session 大写不计）
        ("session_superseded", 2),     # heartbeat 1 + save 1
        ("INSERT OR REPLACE INTO active_sessions", 1),
        ("const SESSION_STALE_MS = 60000;", 1),
    ]
    bad = []
    for k, want in chk:
        got = out.decode('utf-8').count(k)
        if got != want:
            bad.append('  [CHK-FAIL] %-52r 出现 %d 次（期望 %d）' % (k, got, want))
    if bad:
        print('=== 反查失败 ===')
        print('\n'.join(bad))
        sys.exit(2)
    print('=== 反查 %d 项全部通过 ===' % len(chk))


main()
