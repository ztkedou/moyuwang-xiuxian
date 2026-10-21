# -*- coding: utf-8 -*-
r"""
srv_patch_feedback.py -- 玩家反馈三件套（服务端第 98 环 / 新末环）

唯一真相源：三端接口契约（2026-10-21 下发，字段名冻结）。
本文件只按该契约实现；任何偏离必须先改契约。

背景
--------------------------------------------------------------------------
  玩家没有任何站内渠道把 bug / 需求建议递到开发者手里。本环补齐服务端侧：
  feedback 表 + 玩家提交端点 + GM 列表/改状态端点 + AI 免后台直读的 JSONL 通道。
  （客户端「反馈」卡片与 gm-pro.html「反馈」页由兄弟环实现，共用本契约。）

契约（逐条，字段名一个都不能改）
--------------------------------------------------------------------------
  ① 表（启动 DDL 自建，CREATE TABLE IF NOT EXISTS，回滚不删表）：
     feedback(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT,
              kind TEXT, content TEXT, contact TEXT, version TEXT, realm TEXT,
              ua TEXT, status TEXT DEFAULT 'open', created_at INTEGER)
     created_at = Date.now() 毫秒；kind ∈ {'bug','suggestion'}；status ∈ {'open','resolved','closed'}
  ② POST /api/feedback（authenticateToken 必须登录）：
     入参 {kind, content, contact?}；content 去空格后 5~2000 字、contact ≤100 字，违规 → 400 {error}；
     同一 user_id 60 秒内重复提交 → 409 {error:'提交太频繁，请稍后再试'}（查表实现，勿用 403）；
     成功 → 200 {ok:true,id}；同时追加一行 JSON 到 <server目录>/feedback_inbox.jsonl：
     {"ts":毫秒,"id":n,"user":用户名,"kind","content","contact","version","realm","ua"}；
     追加失败 try/catch 吞掉 + console.error，绝不影响 200 响应。
  ③ GET /api/gm/feedback?limit=50&offset=0&status= → {items:[...全字段],total:N}（created_at 倒序）
     POST /api/gm/feedback/:id/status {status} → 200 {ok:true}；非法 status → 400
     两端点都挂现有 authenticateGM（srv/index_v28.ts:1405，const 箭头函数）。

插入点（勘察结论，打前 REQUIRES 逐一断言）
--------------------------------------------------------------------------
  · DDL：GM 表 db.serialize 块（index_v28.ts:1354-1402）内、gm_audit_logs 的 db.run 闭合
    （L1401 `);`）之后、块收口 `});`（L1402）之前 —— 与既有 GM 表同生命周期。
    竞争块已逐一排除：L109 主 DDL / L316 / L3273（users.banned）/ L3282（safeAddColumn）/
    L3339（GM delete_user 清理）/ L14922（宗门 sects 系）；patch 前 `feedback` 全文 0 命中。
  · 端点：logGmAction() 函数（L1448-1453）之后、`// 存档读改写互斥（P1-2）` 之前。
    该位置 authenticateToken(:1316)/authenticateGM(:1405) 两个 const 已初始化（无 TDZ）；
    dbGet/dbRun/dbAll/logGmAction 是 function 声明（提升，请求期才调用）⇒ 定义在 L4625+ 无碍。
  · JSONL 路径 = path.join(__dirname, 'feedback_inbox.jsonl')（__dirname 由基座 :17-18
    fileURLToPath(import.meta.url) 自建，BASECLEAN089 注释在案）。

「新写法存在 + 旧写法清零」断言（本环无旧写法，等价断言）
--------------------------------------------------------------------------
  · 打前：`feedback` 全文 0 命中（REQUIRES 硬断言，重名即退出码 2）；
  · 打后：`feedback` 总出现次数 == 注入文本贡献的精确 delta（防重复插入/插错处），
    且每条新端点/DDL/SQL 常量各命中预期次数（门禁表）。

CLI 契约（照 srv_patch_r249.py）
--------------------------------------------------------------------------
  `--src <path>`：就地原子写回该路径（写回前落 `<src>.bak-r98fb-<时间戳>`）。
  `--check` / `--selftest`：只校验不写回（含 Node 语法门禁 + sqlite3 语义真跑）。
  `--reverse <path>`：反向对照——在未打本环的服务端上确认标记缺席（缺席=PASS；
    发现已打痕迹 → 门禁失败，退出码 1）。
  退出码：0=成功 / 3=幂等（产物已含 [r98fb]）/ 2=锚点不符 / 1=门禁失败。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `PRAGMA`；不新增 `res.status(403)`（频控走 409，契约明令）。
  · 不新增 `setInterval(`（无定时器需求）。
  · 只改服务端；不改客户端 bundle；不改任何既有 srv_patch_*.py / chain_build.py / deploy_*/。
  · 每处替换 expect=1，命中数不符即中止（退出码 2）；产物 round-trip 自证 + Node 语法门禁
    + sqlite3 语义真跑后原子写回。
"""

import argparse
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# 本脚本位于 <repo>/patches/server/，服务端源码在 <repo>/srv/index_v28.ts ⇒ 上跳两级到仓库根再拼。
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), "srv", "index_v28.ts")

MARK = "[r98fb]"

# ============================================================ 与注入 TS 逐字同源的 SQL 常量
# ★ 这些常量既用于 sqlite3 语义真跑（harness），也由门禁断言「必须出现在产物中」——
#   从而保证「测的就是发出去的逻辑」，不是另一套等价实现。
SQL_COOLDOWN = "SELECT created_at FROM feedback WHERE user_id = ? ORDER BY created_at DESC LIMIT 1"
SQL_INSERT = ("INSERT INTO feedback (user_id, username, kind, content, contact, version, realm, ua,"
              " status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
SQL_LIST_BASE = ("SELECT id, user_id, username, kind, content, contact, version, realm, ua,"
                 " status, created_at FROM feedback")
SQL_COUNT_BASE = "SELECT COUNT(*) AS c FROM feedback"
SQL_WHERE_STATUS = " WHERE status = ?"
SQL_ORDER_PAGE = " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
SQL_UPDATE_STATUS = "UPDATE feedback SET status = ? WHERE id = ?"

FEEDBACK_KINDS = ["bug", "suggestion"]
FEEDBACK_STATUSES = ["open", "resolved", "closed"]
FEEDBACK_COOLDOWN_MS = 60 * 1000

# ============================================================ 改动点（全部 expect=1）

# 锚点 E1：GM 表 db.serialize 块内 gm_audit_logs 的 db.run 闭合 + 块收口（index_v28.ts:1392-1402）
E1_OLD = (
    "  db.run(`\n"
    "    CREATE TABLE IF NOT EXISTS gm_audit_logs (\n"
    "      id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
    "      gm_username TEXT NOT NULL DEFAULT 'gm',\n"
    "      action TEXT NOT NULL,\n"
    "      target TEXT,\n"
    "      detail TEXT,\n"
    "      created_at DATETIME DEFAULT CURRENT_TIMESTAMP\n"
    "    )\n"
    "  `);\n"
    "});"
)

E1_NEW = (
    "  db.run(`\n"
    "    CREATE TABLE IF NOT EXISTS gm_audit_logs (\n"
    "      id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
    "      gm_username TEXT NOT NULL DEFAULT 'gm',\n"
    "      action TEXT NOT NULL,\n"
    "      target TEXT,\n"
    "      detail TEXT,\n"
    "      created_at DATETIME DEFAULT CURRENT_TIMESTAMP\n"
    "    )\n"
    "  `);\n"
    "  // [r98fb] 玩家反馈表（三端契约 2026-10-21）：CREATE TABLE IF NOT EXISTS 幂等自建，回滚不删表。\n"
    "  //   created_at = Date.now() 毫秒；kind ∈ {bug,suggestion}；status ∈ {open,resolved,closed}（默认 open）。\n"
    "  //   60s 频控按 user_id 查最近一条、GM 列表按 created_at 倒序 ⇒ 建两个索引（与同块 idx_lottery_history_* 同风格）。\n"
    "  db.run(`\n"
    "    CREATE TABLE IF NOT EXISTS feedback (\n"
    "      id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
    "      user_id INTEGER,\n"
    "      username TEXT,\n"
    "      kind TEXT,\n"
    "      content TEXT,\n"
    "      contact TEXT,\n"
    "      version TEXT,\n"
    "      realm TEXT,\n"
    "      ua TEXT,\n"
    "      status TEXT DEFAULT 'open',\n"
    "      created_at INTEGER\n"
    "    )\n"
    "  `);\n"
    "  db.run(`CREATE INDEX IF NOT EXISTS idx_feedback_user_created ON feedback(user_id, created_at)`);\n"
    "  db.run(`CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at)`);\n"
    "});"
)

# 锚点 E2：logGmAction() 函数（index_v28.ts:1448-1453）—— 端点插在其后
E2_OLD = (
    "function logGmAction(action: string, target?: string, detail?: any) {\n"
    "  db.run(\n"
    "    'INSERT INTO gm_audit_logs (action, target, detail) VALUES (?, ?, ?)',\n"
    "    [action, target || null, detail ? JSON.stringify(detail) : null]\n"
    "  );\n"
    "}"
)

E2_NEW = E2_OLD + "\n" + (
    "\n"
    "// ─────────────────────────────────────────────────────────\n"
    "// [r98fb] 玩家反馈（服务端第 98 环 · 三端契约 2026-10-21）\n"
    "//   POST /api/feedback                玩家提交（authenticateToken 必须登录）\n"
    "//   GET  /api/gm/feedback             GM 列表（authenticateGM，created_at 倒序）\n"
    "//   POST /api/gm/feedback/:id/status  GM 改状态（authenticateGM）\n"
    "//   每条成功提交同步追加一行 JSON 到 <server目录>/feedback_inbox.jsonl（AI 免后台直读通道）；\n"
    "//   追加失败 try/catch 吞掉 + console.error，绝不影响 200 响应。60s 频控查表实现（勿用 403）。\n"
    "// ─────────────────────────────────────────────────────────\n"
    "const FEEDBACK_KINDS = ['bug', 'suggestion']; // [r98fb] kind 白名单\n"
    "const FEEDBACK_STATUSES = ['open', 'resolved', 'closed']; // [r98fb] status 白名单\n"
    "const FEEDBACK_COOLDOWN_MS = 60 * 1000; // [r98fb] 同一 user_id 提交冷却\n"
    "\n"
    "// [r98fb] JSONL 追加（AI 直读通道）：尽力而为，失败自吞\n"
    "function feedbackInboxAppend(entry: Record<string, unknown>): void {\n"
    "  try {\n"
    "    fs.appendFileSync(path.join(__dirname, 'feedback_inbox.jsonl'), JSON.stringify(entry) + '\\n', 'utf8');\n"
    "  } catch (e: any) {\n"
    "    console.error('feedback inbox append error:', e?.message || e);\n"
    "  }\n"
    "}\n"
    "\n"
    "// [r98fb] 玩家提交反馈\n"
    "app.post('/api/feedback', authenticateToken, async (req: any, res: any) => {\n"
    "  try {\n"
    "    const body = req.body || {};\n"
    "    const kind = asStr(body.kind);\n"
    "    const content = asStr(body.content);\n"
    "    const contact = asStr(body.contact);\n"
    "    const version = asStr(body.version).slice(0, 64);\n"
    "    const realm = asStr(body.realm).slice(0, 64);\n"
    "    if (!FEEDBACK_KINDS.includes(kind)) {\n"
    "      return res.status(400).json({ error: 'kind 必须是 bug 或 suggestion' });\n"
    "    }\n"
    "    const contentLen = content.replace(/\\s/g, '').length;\n"
    "    if (contentLen < 5 || contentLen > 2000) {\n"
    "      return res.status(400).json({ error: '反馈内容去空格后需 5~2000 字' });\n"
    "    }\n"
    "    if (contact.length > 100) {\n"
    "      return res.status(400).json({ error: '联系方式不能超过 100 字' });\n"
    "    }\n"
    "    // 60s 频控：查表（本用户最近一条 created_at 距今不足 60s ⇒ 409；契约明令勿用 403）\n"
    "    const last: any = await dbGet('SELECT created_at FROM feedback WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', [req.user.id]);\n"
    "    if (last && last.created_at != null && Date.now() - Number(last.created_at) < FEEDBACK_COOLDOWN_MS) {\n"
    "      return res.status(409).json({ error: '提交太频繁，请稍后再试' });\n"
    "    }\n"
    "    const ua = asStr(req.headers['user-agent']);\n"
    "    const ins = await dbRun('INSERT INTO feedback (user_id, username, kind, content, contact, version, realm, ua, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', [req.user.id, req.user.username, kind, content, contact || null, version || null, realm || null, ua ? ua.slice(0, 256) : null, 'open', Date.now()]);\n"
    "    const fid = Number(ins.lastID);\n"
    "    feedbackInboxAppend({ ts: Date.now(), id: fid, user: req.user.username, kind: kind, content: content, contact: contact, version: version, realm: realm, ua: ua });\n"
    "    return res.json({ ok: true, id: fid });\n"
    "  } catch (e: any) {\n"
    "    console.error('feedback submit error:', e?.message || e);\n"
    "    return res.status(500).json({ error: '服务器繁忙' });\n"
    "  }\n"
    "});\n"
    "\n"
    "// [r98fb] GM 反馈列表（created_at 倒序；status 可选过滤；limit 默认 50 上限 200）\n"
    "app.get('/api/gm/feedback', authenticateGM, async (req: any, res: any) => {\n"
    "  try {\n"
    "    const status = asStr(req.query.status);\n"
    "    const limit = Math.min(Math.max(asInt(req.query.limit) || 50, 1), 200);\n"
    "    const offset = Math.max(asInt(req.query.offset) || 0, 0);\n"
    "    const hasStatus = FEEDBACK_STATUSES.includes(status);\n"
    "    const where = hasStatus ? ' WHERE status = ?' : '';\n"
    "    const base: any[] = hasStatus ? [status] : [];\n"
    "    const total: any = await dbGet('SELECT COUNT(*) AS c FROM feedback' + where, base);\n"
    "    const items = await dbAll('SELECT id, user_id, username, kind, content, contact, version, realm, ua, status, created_at FROM feedback' + where + ' ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?', base.concat([limit, offset]));\n"
    "    return res.json({ items: items, total: Number(total && total.c) || 0 });\n"
    "  } catch (e: any) {\n"
    "    console.error('gm feedback list error:', e?.message || e);\n"
    "    return res.status(500).json({ error: '服务器繁忙' });\n"
    "  }\n"
    "});\n"
    "\n"
    "// [r98fb] GM 改反馈状态（非法 status ⇒ 400；不存在 ⇒ 404）\n"
    "app.post('/api/gm/feedback/:id/status', authenticateGM, async (req: any, res: any) => {\n"
    "  try {\n"
    "    const id = asInt((req.params || {}).id);\n"
    "    const status = asStr((req.body || {}).status);\n"
    "    if (!Number.isFinite(id)) return res.status(400).json({ error: '无效的反馈 id' });\n"
    "    if (!FEEDBACK_STATUSES.includes(status)) return res.status(400).json({ error: 'status 必须是 open/resolved/closed' });\n"
    "    const r = await dbRun('UPDATE feedback SET status = ? WHERE id = ?', [status, id]);\n"
    "    if (!r || r.changes === 0) return res.status(404).json({ error: '反馈不存在' });\n"
    "    logGmAction('feedback_status', 'feedback:' + id, { status: status });\n"
    "    return res.json({ ok: true });\n"
    "  } catch (e: any) {\n"
    "    console.error('gm feedback status error:', e?.message || e);\n"
    "    return res.status(500).json({ error: '服务器繁忙' });\n"
    "  }\n"
    "});"
)

EDITS = [
    ("E1 feedback 表 DDL（GM serialize 块内，gm_audit_logs 之后）", E1_OLD, E1_NEW),
    ("E2 反馈三端点（logGmAction 之后）", E2_OLD, E2_NEW),
]

# ============================================================ 前置依赖（只读自证，不改；不符 ⇒ 退出码 2）
REQUIRES = [
    (E1_OLD, 1, "GM DDL 块锚点（gm_audit_logs db.run 闭合 + serialize 收口）必须唯一"),
    (E2_OLD, 1, "logGmAction 函数锚点（端点插入点）必须唯一"),
    ("feedback", 0, "patch 前 feedback 必须全文 0 命中（无重名，契约前提）"),
    ("const authenticateGM = (req: any, res: any, next: any) => {", 1, "GM 鉴权中间件在位（GM 端点挂它）"),
    ("const authenticateToken = (req: any, res: any, next: any) => {", 1, "玩家鉴权中间件在位（提交端点挂它）"),
    ("const GM_PASSWORD = process.env.GM_PASSWORD;", 1, "GM 口令硬失败模式在位（无弱口令兜底）"),
    ("function dbGet<T = any>(sql: string, params: any[] = []): Promise<T | undefined> {", 1, "dbGet 在位"),
    ("function dbRun(sql: string, params: any[] = []): Promise<{ lastID: number; changes: number }> {", 1, "dbRun 在位"),
    ("function dbAll<T = any>(sql: string, params: any[] = []): Promise<T[]> {", 1, "dbAll 在位（GM 列表用）"),
    ("function asStr(x: unknown): string {", 1, "asStr 在位（不可信请求值安全取串）"),
    ("function asInt(x: unknown): number {", 1, "asInt 在位"),
    ("function logGmAction(action: string, target?: string, detail?: any) {", 1, "logGmAction 在位（GM 状态变更审计复用）"),
    ("import fs from 'fs';", 1, "fs 已由文件头 import（JSONL 追加用）"),
    ("import path from 'path';", 1, "path 已由文件头 import（__dirname 拼 JSONL 路径用）"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "CREATE TABLE IF NOT EXISTS gm_sessions (",
    "CREATE TABLE IF NOT EXISTS refresh_tokens (",
    "CREATE TABLE IF NOT EXISTS lottery_history (",
    "CREATE TABLE IF NOT EXISTS gm_audit_logs (",
    "const authenticateGM = (req: any, res: any, next: any) => {",
    "const authenticateToken = (req: any, res: any, next: any) => {",
    "const GM_PASSWORD = process.env.GM_PASSWORD;",
    "app.post('/api/gm/login'",
    "app.listen(PORT",
    "gm_audit_logs",
    "  if (token == null) return res.sendStatus(401);",
    "if (!GM_PASSWORD) {",
]


def fail(msg, code=1):
    print("[FAIL] " + msg)
    sys.exit(code)


# ============================================================ Node 语法门禁
def node_bin():
    root = r"C:/Users/<USER>/.workbuddy-ai/binaries/node/versions"
    cands = []
    if os.path.isdir(root):
        cands = sorted(os.path.join(root, d, "node.exe") for d in os.listdir(root))
        cands = [c for c in cands if os.path.isfile(c)]
    return os.environ.get("YL_NODE") or (cands[-1] if cands else "node")


def node_syntax_check(text):
    """产物必须过 node --experimental-strip-types --check。"""
    d = tempfile.mkdtemp(prefix="r98fbchk-")
    try:
        p = os.path.join(d, "c.ts")
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        r = subprocess.run([node_bin(), "--experimental-strip-types", "--check", p],
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ============================================================ sqlite3 语义真跑
# 用内存库跑与注入 TS **逐字同源**的 SQL 决策逻辑（DDL/频控/列表分页过滤/改状态）。
def semantic_harness():
    results = []

    def ck(name, fn):
        try:
            ok = bool(fn())
            results.append((name, ok, ""))
        except Exception as e:
            results.append((name, False, "throw:" + repr(e)))

    DDL = ("CREATE TABLE IF NOT EXISTS feedback (\n"
           "      id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
           "      user_id INTEGER,\n"
           "      username TEXT,\n"
           "      kind TEXT,\n"
           "      content TEXT,\n"
           "      contact TEXT,\n"
           "      version TEXT,\n"
           "      realm TEXT,\n"
           "      ua TEXT,\n"
           "      status TEXT DEFAULT 'open',\n"
           "      created_at INTEGER\n"
           "    )")
    IDX1 = "CREATE INDEX IF NOT EXISTS idx_feedback_user_created ON feedback(user_id, created_at)"
    IDX2 = "CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at)"

    def fresh():
        con = sqlite3.connect(":memory:")
        con.execute(DDL)
        con.execute(IDX1)
        con.execute(IDX2)
        con.commit()
        return con

    def cooldown_hit(con, user_id, now_ms):
        # 与 TS 逐字同源：last && last.created_at != null && Date.now()-Number < 60000
        row = con.execute(SQL_COOLDOWN, [user_id]).fetchone()
        return row is not None and row[0] is not None and (now_ms - int(row[0])) < FEEDBACK_COOLDOWN_MS

    # ① 建表：列序/类型/默认值/索引
    def h1():
        con = fresh()
        cols = con.execute("PRAGMA table_info(feedback)").fetchall()
        names = [c[1] for c in cols]
        expect_names = ["id", "user_id", "username", "kind", "content", "contact",
                        "version", "realm", "ua", "status", "created_at"]
        dflt = {c[1]: c[4] for c in cols}
        idxs = [r[1] for r in con.execute("PRAGMA index_list(feedback)").fetchall()]
        return (names == expect_names and dflt.get("status") == "'open'"
                and "idx_feedback_user_created" in idxs and "idx_feedback_created" in idxs)

    # ② 空表 ⇒ 无频控（可提交）
    def h2():
        con = fresh()
        return cooldown_hit(con, 1, int(time.time() * 1000)) is False

    # ③ 60s 内有提交 ⇒ 409 分支命中
    def h3():
        con = fresh()
        now = int(time.time() * 1000)
        con.execute(SQL_INSERT, [1, "甲", "bug", "内容内容内容", None, None, None, None, "open", now - 30_000])
        con.commit()
        return cooldown_hit(con, 1, now) is True

    # ④ 61s 前的提交 ⇒ 不再拦（冷却只看最近一条）
    def h4():
        con = fresh()
        now = int(time.time() * 1000)
        con.execute(SQL_INSERT, [1, "甲", "bug", "内容内容内容", None, None, None, None, "open", now - 61_000])
        con.commit()
        return cooldown_hit(con, 1, now) is False

    # ⑤ 频控按 user_id 隔离：别人的 30s 前提交不拦我
    def h5():
        con = fresh()
        now = int(time.time() * 1000)
        con.execute(SQL_INSERT, [7, "乙", "bug", "内容内容内容", None, None, None, None, "open", now - 30_000])
        con.commit()
        return cooldown_hit(con, 1, now) is False

    # ⑥ INSERT 落库 + status 默认链路（显式 'open'）+ 回读一致
    def h6():
        con = fresh()
        now = int(time.time() * 1000)
        cur = con.execute(SQL_INSERT, [3, "丙", "suggestion", "建议建议建议内容", "qq:123",
                                       "0.9.62", "炼气期", "UA-TEST", "open", now])
        con.commit()
        rid = cur.lastrowid
        row = con.execute("SELECT user_id, username, kind, content, contact, version, realm, ua, status, created_at"
                          " FROM feedback WHERE id = ?", [rid]).fetchone()
        return (row == (3, "丙", "suggestion", "建议建议建议内容", "qq:123", "0.9.62", "炼气期", "UA-TEST", "open", now)
                and rid >= 1)

    # ⑦ GM 列表：created_at 倒序 + LIMIT/OFFSET + status 过滤 + total
    def h7():
        con = fresh()
        now = int(time.time() * 1000)
        for uid, ts in [(1, now - 1000), (2, now - 2000), (3, now - 3000)]:
            con.execute(SQL_INSERT, [uid, "u%d" % uid, "bug", "内容内容内容%d" % uid,
                                     None, None, None, None, "open", ts])
        con.execute(SQL_UPDATE_STATUS, ["closed", 3])  # 自增序：id=1 最新 / id=3 最旧；把最旧的 id=3 置 closed
        con.commit()
        total_all = con.execute(SQL_COUNT_BASE, []).fetchone()[0]
        total_open = con.execute(SQL_COUNT_BASE + SQL_WHERE_STATUS, ["open"]).fetchone()[0]
        first2 = con.execute(SQL_LIST_BASE + SQL_ORDER_PAGE, [2, 0]).fetchall()
        open_1st = con.execute(SQL_LIST_BASE + SQL_WHERE_STATUS + SQL_ORDER_PAGE, ["open", 1, 0]).fetchall()
        open_2nd = con.execute(SQL_LIST_BASE + SQL_WHERE_STATUS + SQL_ORDER_PAGE, ["open", 1, 1]).fetchall()
        return (total_all == 3 and total_open == 2
                and [r[0] for r in first2] == [1, 2]     # created_at 倒序：id1(最新) → id2
                and [r[0] for r in open_1st] == [1]      # open 过滤后最新仍是 id1
                and [r[0] for r in open_2nd] == [2])     # open 过滤翻页(offset1) ⇒ id2

    # ⑧ 改状态：存在 ⇒ changes=1 且生效；不存在 ⇒ changes=0（端点 404 分支）
    def h8():
        con = fresh()
        now = int(time.time() * 1000)
        con.execute(SQL_INSERT, [9, "丁", "bug", "内容内容内容", None, None, None, None, "open", now])
        rid = con.execute("SELECT id FROM feedback").fetchone()[0]
        r1 = con.execute(SQL_UPDATE_STATUS, ["closed", rid]).rowcount
        st = con.execute("SELECT status FROM feedback WHERE id = ?", [rid]).fetchone()[0]
        r2 = con.execute(SQL_UPDATE_STATUS, ["resolved", 99999]).rowcount
        return r1 == 1 and st == "closed" and r2 == 0

    ck("① 建表：列序/默认 open/两索引", h1)
    ck("② 空表 ⇒ 无频控", h2)
    ck("③ 60s 内重复 ⇒ 409 分支", h3)
    ck("④ 61s 前提交 ⇒ 放行", h4)
    ck("⑤ 频控按 user_id 隔离", h5)
    ck("⑥ INSERT 落库字段回读一致", h6)
    ck("⑦ GM 列表：倒序/分页/过滤/total", h7)
    ck("⑧ 改状态：changes 语义（1/0）", h8)

    total = len(results)
    nfail = sum(1 for _, ok, _ in results if not ok)
    for name, ok, extra in results:
        print(("  [OK] " if ok else "  [FAIL] ") + name + (("  <" + extra + ">") if extra else ""))
    print("HARNESS_RESULT " + json.dumps({"total": total, "fail": nfail}))
    return total, nfail


def main() -> None:
    ap = argparse.ArgumentParser(description="玩家反馈三件套（服务端第 98 环）")
    ap.add_argument("--src", default=SRC, help="待打补丁的服务端源码（装配器会传私有副本）")
    ap.add_argument("--check", action="store_true", help="只校验不写回")
    ap.add_argument("--selftest", action="store_true", help="只校验不写回（含 Node 语法 + sqlite3 语义真跑）")
    ap.add_argument("--reverse", default=None, metavar="PATH",
                    help="反向对照：在未打本环的服务端上确认标记缺席（只校验不写回）")
    a = ap.parse_args()

    # ---- 反向对照模式 ----
    if a.reverse:
        path = a.reverse
        if not os.path.exists(path):
            fail("reverse source not found: " + path)
        with io.open(path, "r", encoding="utf-8", newline="") as f:
            rev = f.read()
        print("== 反向对照（未打第 98 环的服务端）：%s ==" % path)
        has_mark = rev.count(MARK)
        has_ep = rev.count("app.post('/api/feedback'")
        has_ddl = rev.count("CREATE TABLE IF NOT EXISTS feedback")
        print("  [r98fb] 计数 = %d（期望 0）" % has_mark)
        print("  app.post('/api/feedback' 计数 = %d（期望 0）" % has_ep)
        print("  CREATE TABLE IF NOT EXISTS feedback 计数 = %d（期望 0）" % has_ddl)
        if has_mark == 0 and has_ep == 0 and has_ddl == 0:
            print("  [REVERSE] PASS（基线确实未打第 98 环，标记缺席）")
        else:
            print("  [REVERSE] FAIL（★ 该源已含第 98 环痕迹，不构成基线）")
            sys.exit(1)
        return

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等（★ 已打 ⇒ 退出码 3，由调用方区分「已打」与「失败」）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        sys.exit(3)

    # 2) 依赖（不符 ⇒ 退出码 2）
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（needle 出现 %d 次，期望 %d）：%s" % (n, cnt, why), 2)

    # 3) 锚点计数（不符 ⇒ 退出码 2）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）" % (name, n), 2)
        if old == new:
            fail("%s old == new" % name, 2)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}
    base_fb = src.count("feedback")           # = 0（REQUIRES 已断言）
    base_403 = src.count("res.status(403")
    base_require = src.count("require(")
    base_pragma = src.count("PRAGMA")
    base_interval = src.count("setInterval(")

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁（新写法存在 + 旧写法清零 + 冻结基线 + 红线）
    mark_n = sum(new.count(MARK) for _, _, new in EDITS)
    delta_fb = sum(new.count("feedback") for _, _, new in EDITS)
    gates = [
        ("标记 [r98fb] 就位", MARK, mark_n),
        # DDL
        ("DDL feedback 表", "CREATE TABLE IF NOT EXISTS feedback (", 1),
        ("DDL status 默认 open", "status TEXT DEFAULT 'open',", 1),
        ("DDL created_at INTEGER（毫秒）", "created_at INTEGER\n    )", 1),
        ("DDL 索引 user_created", "CREATE INDEX IF NOT EXISTS idx_feedback_user_created ON feedback(user_id, created_at)", 1),
        ("DDL 索引 created", "CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at)", 1),
        # 端点
        ("玩家端点挂 authenticateToken", "app.post('/api/feedback', authenticateToken,", 1),
        ("GM 列表端点挂 authenticateGM", "app.get('/api/gm/feedback', authenticateGM,", 1),
        ("GM 状态端点挂 authenticateGM", "app.post('/api/gm/feedback/:id/status', authenticateGM,", 1),
        ("409 契约文案", "提交太频繁，请稍后再试", 1),
        ("400 kind 白名单", "if (!FEEDBACK_KINDS.includes(kind)) {", 1),
        ("400 content 5~2000", "if (contentLen < 5 || contentLen > 2000) {", 1),
        ("400 contact ≤100", "if (contact.length > 100) {", 1),
        ("60s 频控查表判定", "if (last && last.created_at != null && Date.now() - Number(last.created_at) < FEEDBACK_COOLDOWN_MS) {", 1),
        ("200 响应 {ok,id}", "return res.json({ ok: true, id: fid });", 1),
        ("kind 白名单常量", "const FEEDBACK_KINDS = ['bug', 'suggestion'];", 1),
        ("status 白名单常量", "const FEEDBACK_STATUSES = ['open', 'resolved', 'closed'];", 1),
        ("冷却常量 60s", "const FEEDBACK_COOLDOWN_MS = 60 * 1000;", 1),
        # JSONL 通道
        ("JSONL 通道路径", "feedback_inbox.jsonl", 2),
        ("JSONL 追加自吞", "console.error('feedback inbox append error:', e?.message || e);", 1),
        ("JSONL 追加函数+调用", "feedbackInboxAppend(", 2),
        # SQL 同源（harness 测的就是产物里的 SQL）
        ("SQL 同源 SQL_COOLDOWN", SQL_COOLDOWN, 1),
        ("SQL 同源 SQL_INSERT", SQL_INSERT, 1),
        ("SQL 同源 SQL_LIST_BASE", SQL_LIST_BASE, 1),
        ("SQL 同源 SQL_COUNT_BASE", SQL_COUNT_BASE, 1),
        ("SQL 同源 SQL_UPDATE_STATUS", SQL_UPDATE_STATUS, 1),
        # 旧写法清零的等价断言：feedback 总数 == 打前(0) + 注入精确 delta（防重复插入/插错处）
        ("feedback 总数 = base+delta（无重复插入）", "feedback", base_fb + delta_fb),
    ]
    # 冻结：既有 GM 基座一字不动
    for needle in BASE_NEEDLES:
        gates.append(("冻结 " + needle[:44].replace("\n", " "), needle, base[needle]))
    # 红线：不新增 403 / require( / PRAGMA / setInterval(
    gates.append(("红线 未新增 res.status(403)", "res.status(403", base_403))
    gates.append(("红线 未新增 require(", "require(", base_require))
    gates.append(("红线 未新增 PRAGMA", "PRAGMA", base_pragma))
    gates.append(("红线 未新增 setInterval(", "setInterval(", base_interval))

    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        if not good:
            print("  [FAIL] %-58s actual=%d expect==%d" % (label, act, exp))
    print("  [%s] 门禁 %d 条" % ("OK" if ok else "FAIL", len(gates)))

    # 7) round-trip 自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    # 8) node --check 语法门禁
    syn_ok, syn_msg = node_syntax_check(out)
    if not syn_ok:
        sys.stdout.write(syn_msg)
    print("  [%s] node --experimental-strip-types --check" % ("OK" if syn_ok else "FAIL"))
    ok = ok and syn_ok

    # 9) sqlite3 语义真跑
    total, nfail = semantic_harness()
    sem_ok = (nfail == 0)
    print("  [%s] sqlite3 语义真跑  (total=%d fail=%d)" % ("OK" if sem_ok else "FAIL", total, nfail))
    ok = ok and sem_ok

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if not ok:
        fail("门禁未全绿，未写回", 1)

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 10) 改前 .bak + 原子写回
    bak = "%s.bak-r98fb-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r98fb-", suffix=".tmp")
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
