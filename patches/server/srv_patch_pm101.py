# -*- coding: utf-8 -*-
r"""
srv_patch_pm101.py -- 玩家私信服务端（第 99 环 / 新末环）

唯一真相源：接口契约 2026-10-21 B 段（字段名冻结）。
本文件只按该契约实现；任何偏离必须先改契约。

背景
--------------------------------------------------------------------------
  玩家之间没有任何站内私信通道。本环补齐服务端侧：mail 表 kind 列 + 玩家发信端点。
  （客户端「仙友录/在线人物/信箱」私信 UI 由兄弟环实现，共用本契约。）

契约（B 段逐条，字段名一个都不能改）
--------------------------------------------------------------------------
  ① mail 表加列：ALTER TABLE mail ADD COLUMN kind TEXT DEFAULT 'system'
     （try/catch 幂等，已有列则跳过 ⇒ 复用既有 safeAddColumn，duplicate column name 自吞）。
     玩家私信行：kind='player'、sender=发信玩家用户名、title='来自 X 的私信'、attached_lingshi=0。
     落库必须走既有 insertMail（index_v28.ts:7563）：lingshi=0 ⇒ attached_lingshi=0，且
     0 < CHRONICLE_MAIL_STONES(10000) ⇒ ≥1000 灵石「鸿函」入志副作用不触发（契约明示）。
  ② 新端点 POST /api/mail/send（authenticateToken）：
     入参 {to, content}；to=目标用户名（users 表校验存在）；to==自己 → 400；
     content 去空格后 2~500 字 → 违规 400；同一发送者 30s 内二连发 → 409 {error}；
     每玩家每日（UTC+8 日期口径）上限 50 条 → 409；成功 → 200 {ok:true,id}。
  ③ 与既有 GM 发信路由（app.post('/api/mail/send', authenticateGM, …)，index_v28.ts:8008）
     同路径共存：本环路由先注册，pm101Dispatch 按 Bearer 是否为合法玩家 access token 分流，
     非玩家 token 原样 next() 落到 GM 路由 —— GM 端点一个字节不动（主控 2026-10-21 裁定）。
     过期 access token 必须直接 401（authenticateToken 同语义：客户端只认 401 走静默续期重试）。

主控裁定存档（2026-10-21 escalate 答复，选 A）
--------------------------------------------------------------------------
  GET /api/gm/messages（index_v28.ts:3857）只读世界聊天表 chat_messages；该表被玩家
  GET /api/messages（:4078）无过滤轮询 ⇒ 私信写入即向全体玩家泄漏。故本环绝不写 chat_messages，
  也不改 GM 端点；GM /api/gm/messages 看不到私信行（自检改为「mail 表落 kind='player' 行 +
  chat_messages 行数与内容零变化」硬断言）。GM 侧如需审核私信，后续批次按
  「UNION + DELETE 分流」另行立项（防 mail.id 与 chat_messages.id 撞号误删）。

插入点（勘察结论，打前 REQUIRES 逐一断言）
--------------------------------------------------------------------------
  · ALTER：mail 表 DDL 块内 idx_mail_user_id（index_v28.ts:308）之后、块收口 `});`（:309）之前
    —— 与 CREATE 同 serialize 串行序，新库/旧库都收敛到同一列集。
  · 端点：GM 发信注释行 + 路由行（:8007-8008）之前整体插入（先注册者先匹配）。
    该处 insertMail(:7563)/dbGet/dbRun/asStr（function 声明，提升）/rateLimit(:3971, function 声明)
    /authenticateToken(:1316)/authenticateGM(:1425)/JWT_SECRET_USED(:53) 全部已初始化（无 TDZ）。

「新写法存在 + 旧写法清零」断言
--------------------------------------------------------------------------
  · 打前：'[r99pm]' / "kind = 'player'" / 'pm101' 全文 0 命中（REQUIRES 硬断言，重名即退出码 2）；
  · 打后：新端点/ALTER/SQL 常量各命中精确次数（门禁表）；"INSERT INTO mail" 总数不变（=2，
    落库仍只经 insertMail 既有通道）；"INSERT INTO chat_messages" 总数不变（=2，绝不写世界聊天）。

CLI 契约（照 srv_patch_feedback.py）
--------------------------------------------------------------------------
  `--src <path>`：就地原子写回该路径（写回前落 `<src>.bak-r99pm-<时间戳>`）。
  `--check` / `--selftest`：只校验不写回（含 Node 语法门禁 + sqlite3 语义真跑）。
  `--reverse <path>`：反向对照——在未打本环的服务端上确认标记缺席（缺席=PASS；
    发现已打痕迹 → 门禁失败，退出码 1）。
  退出码：0=成功 / 3=幂等（产物已含 [r99pm]）/ 2=锚点不符 / 1=门禁失败。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `PRAGMA`；不新增 `res.status(403)`（频控走 409/429，契约明令）。
  · 不新增 `setInterval(`（无定时器需求）；不写 chat_messages；不改 GM 端点。
  · 只改服务端；不改客户端 bundle；不改任何既有 srv_patch_*.py / chain_build.py / deploy_*/。
  · 每处替换 expect=1，命中数不符即中止（退出码 2）；产物 round-trip 自证 + Node 语法门禁
    + sqlite3 语义真跑后原子写回。
"""

import argparse
import calendar
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

MARK = "[r99pm]"

# ============================================================ 与注入 TS 逐字同源的 SQL 常量
# ★ 这些常量既用于 sqlite3 语义真跑（harness），也由门禁断言「必须出现在产物中」——
#   从而保证「测的就是发出去的逻辑」，不是另一套等价实现。
SQL_ALTER_KIND = "ALTER TABLE mail ADD COLUMN kind TEXT DEFAULT 'system'"
SQL_LAST_SEND = "SELECT created_at FROM mail WHERE kind = 'player' AND sender = ? ORDER BY id DESC LIMIT 1"
SQL_DAILY_COUNT = "SELECT COUNT(*) AS c FROM mail WHERE kind = 'player' AND sender = ? AND created_at >= ?"
SQL_KIND_UPDATE = "UPDATE mail SET kind = 'player' WHERE id = ?"

PM_COOLDOWN_MS = 30 * 1000
PM_DAILY_LIMIT = 50
PM_UTC8_OFFSET_MS = 8 * 60 * 60 * 1000

# ============================================================ 改动点（全部 expect=1）

# 锚点 E1：mail 表 DDL 块内 idx_mail_user_id 行 + 块收口（index_v28.ts:308-309）
E1_OLD = (
    "      db.run(`CREATE INDEX IF NOT EXISTS idx_mail_user_id ON mail(user_id, id)`);\n"
    "    });"
)

E1_NEW = (
    "      db.run(`CREATE INDEX IF NOT EXISTS idx_mail_user_id ON mail(user_id, id)`);\n"
    "      // [r99pm] 玩家私信（服务端第 99 环）：mail 表加 kind 列——'system'=系统/GM 信（默认），\n"
    "      //   'player'=玩家私信。幂等：复用 safeAddColumn（duplicate column name 自吞），\n"
    "      //   与 CREATE 同 serialize 串行序，新库/旧库都收敛到同一列集。\n"
    "      safeAddColumn('mail', 'kind', \"" + SQL_ALTER_KIND + "\");\n"
    "    });"
)

# 锚点 E2：GM 发信注释 + 路由行（index_v28.ts:8007-8008）—— 本环端点整体插在其前（先注册者先匹配）
E2_OLD = (
    "// POST /api/mail/send — GM 发信（authenticateGM）。单发 {userId|username}，全服 {all:true}\n"
    "app.post('/api/mail/send', authenticateGM, (req: any, res: any) => {"
)

E2_NEW = r"""// ─────────────────────────────────────────────────────────
// [r99pm] 玩家私信（服务端第 99 环 · 接口契约 2026-10-21 B 段）
//   POST /api/mail/send（authenticateToken）：入参 {to, content}
//   · 与下方既有 GM 发信路由同路径：本环路由先注册，pm101Dispatch 按 Authorization Bearer 是否为
//     合法玩家 access token 分流——是 → authenticateToken → pm101Send（本环业务，绝不 next）；
//     否（GM 串/垃圾/无 Bearer）→ 原样 next() 落到下方既有 GM 路由，GM 端点一个字节不动。
//   · 校验：to=目标用户名（users 表校验存在，不存在 400）；to==自己 400；content 去空格后 2~500 字
//     400；同一发送者 30s 内二连发 409；每玩家每日（UTC+8 日期口径）上限 50 条 409；成功 200 {ok,id}。
//   · 落库走既有 insertMail（lingshi=0 ⇒ attached_lingshi=0 且 0 < CHRONICLE_MAIL_STONES(10000)，
//     ≥1000 灵石「鸿函」入志副作用不触发），行 kind 由补写 UPDATE 置 'player'（insertMail 零改动）。
//   · 本环绝不写 chat_messages：该表是玩家可见世界聊天（GET /api/messages 无过滤轮询），写入即泄漏
//     私信；GM GET /api/gm/messages 依旧只读世界聊天、看不到私信行（主控 2026-10-21 裁定 A：GM 侧
//     如需审核私信，后续批次按「UNION + DELETE 分流」另行立项）。
// ─────────────────────────────────────────────────────────
const PM_COOLDOWN_MS = 30 * 1000; // [r99pm] 同一发送者二连发冷却
const PM_DAILY_LIMIT = 50; // [r99pm] 每玩家每日私信上限
const PM_UTC8_OFFSET_MS = 8 * 60 * 60 * 1000; // [r99pm] 日限按 UTC+8 日期口径
// [r99pm] created_at 为 SQLite CURRENT_TIMESTAMP（UTC 'YYYY-MM-DD HH:MM:SS'）；按 id DESC 取最近一封
const PM_LAST_SEND_SQL = "SELECT created_at FROM mail WHERE kind = 'player' AND sender = ? ORDER BY id DESC LIMIT 1";
const PM_DAILY_COUNT_SQL = "SELECT COUNT(*) AS c FROM mail WHERE kind = 'player' AND sender = ? AND created_at >= ?";
// [r99pm] 防刷安全网：合法路径被 30s 冷却压到 ≤2 条/分钟，20 条/分钟仅拦异常轰炸（同族 mail:* 端点同风格）
const pm101Rate = rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => 'pm:send:' + (req.user?.id ?? req.ip) });

// [r99pm] 玩家私信落库：insertMail 零改动复用 + 补写 kind='player'（insertMail 的 INSERT 不含 kind ⇒ 默认 'system'）
async function pm101InsertPlayerMail(targetUserId: number, senderName: string, content: string): Promise<number> {
  const mailId = await insertMail(targetUserId, '来自 ' + senderName + ' 的私信', content, senderName, 0);
  await dbRun("UPDATE mail SET kind = 'player' WHERE id = ?", [mailId]);
  return mailId;
}

// [r99pm] 玩家私信业务体（仅在 Bearer 为合法玩家 access token 时被 pm101Dispatch 调用）
async function pm101Send(req: any, res: any) {
  try {
    const body = req.body || {};
    const to = asStr(body.to).trim();
    const content = asStr(body.content).trim();
    if (!to) return res.status(400).json({ error: '需要收件人' });
    const stripped = content.replace(/\s/g, '').length;
    if (stripped < 2 || stripped > 500) {
      return res.status(400).json({ error: '私信内容去空格后需 2~500 字' });
    }
    const row: any = await dbGet('SELECT id, username FROM users WHERE username = ?', [to]);
    if (!row) return res.status(400).json({ error: '收件人不存在' });
    if (Number(row.id) === Number(req.user.id)) return res.status(400).json({ error: '不能给自己发私信' });
    const nowMs = Date.now();
    const last: any = await dbGet(PM_LAST_SEND_SQL, [req.user.username]);
    if (last && last.created_at != null) {
      const lastMs = Date.parse(String(last.created_at).replace(' ', 'T') + 'Z');
      if (Number.isFinite(lastMs) && nowMs - lastMs < PM_COOLDOWN_MS) {
        return res.status(409).json({ error: '发送太频繁，请稍后再试' });
      }
    }
    // [r99pm] UTC+8 当日零点（折回 UTC 毫秒再格式化成 SQLite CURRENT_TIMESTAMP 同构文本）
    const d8 = new Date(nowMs + PM_UTC8_OFFSET_MS);
    const dayStartUtcMs = Date.UTC(d8.getUTCFullYear(), d8.getUTCMonth(), d8.getUTCDate()) - PM_UTC8_OFFSET_MS;
    const dayStartSql = new Date(dayStartUtcMs).toISOString().slice(0, 19).replace('T', ' ');
    const cnt: any = await dbGet(PM_DAILY_COUNT_SQL, [req.user.username, dayStartSql]);
    if (Number(cnt && cnt.c) >= PM_DAILY_LIMIT) {
      return res.status(409).json({ error: '今日私信已达上限（50 条）' });
    }
    const mailId = await pm101InsertPlayerMail(Number(row.id), req.user.username, content);
    return res.json({ ok: true, id: mailId });
  } catch (e: any) {
    console.error('pm send error:', e?.message || e);
    return res.status(500).json({ error: '服务器繁忙' });
  }
}

// [r99pm] 玩家/GM 分流：过期 access token 必须直接 401（客户端只认 401 走 /api/auth/refresh 静默
//   续期并重试一次）；GM 串/垃圾 token 原样 next() 交给 GM 层（其 401/403 语义不变）。
const pm101Dispatch = (req: any, res: any, next: any) => {
  const authHeader = req.headers['authorization'] || '';
  const token = authHeader && authHeader.split(' ')[1];
  if (token == null) return next();
  jwt.verify(token, JWT_SECRET_USED, (err: any, payload: any) => {
    if (err) {
      if (err.name === 'TokenExpiredError') return res.sendStatus(401);
      return next();
    }
    if (!payload || payload.type !== 'access') return next();
    authenticateToken(req, res, (merr: any) => {
      if (merr) return next(merr);
      pm101Rate(req, res, () => { pm101Send(req, res); });
    });
  });
};
app.post('/api/mail/send', pm101Dispatch);
""" + E2_OLD

EDITS = [
    ("E1 mail 表 kind 列（DDL 块内 idx_mail_user_id 之后）", E1_OLD, E1_NEW),
    ("E2 玩家私信端点（GM 发信路由之前）", E2_OLD, E2_NEW),
]

# ============================================================ 前置依赖（只读自证，不改；不符 ⇒ 退出码 2）
REQUIRES = [
    (E1_OLD, 1, "mail DDL 块锚点（idx_mail_user_id 行 + serialize 收口）必须唯一"),
    (E2_OLD, 1, "GM 发信路由锚点（注释行 + app.post 行）必须唯一"),
    (MARK, 0, "patch 前 [r99pm] 必须全文 0 命中（无重名，契约前提）"),
    ("kind = 'player'", 0, "patch 前 kind='player' 写法必须 0 命中"),
    ("pm101", 0, "patch 前 pm101 前缀必须 0 命中"),
    ("function insertMail(userId: number, title: string, content: string, sender: string, lingshi: number, opts?: { noChronicle?: boolean }): Promise<number> {", 1, "insertMail 勘察签名在位（落库唯一通道）"),
    ("INSERT INTO mail (user_id, sender, title, content, attached_lingshi) VALUES (?, ?, ?, ?, ?)", 1, "insertMail 体 INSERT 在位（本环不改它）"),
    ("const CHRONICLE_MAIL_STONES = 10000;", 1, "入志阈值常量在位（lingshi=0 必不触发）"),
    ("const authenticateToken = (req: any, res: any, next: any) => {", 1, "玩家鉴权中间件在位"),
    ("const authenticateGM = (req: any, res: any, next: any) => {", 1, "GM 鉴权中间件在位（GM 路由自带，不动）"),
    ("const JWT_SECRET_USED = JWT_SECRET;", 1, "JWT 密钥常量在位（dispatch 验签用）"),
    ("import jwt from 'jsonwebtoken';", 1, "jwt 已由文件头 import"),
    ("const safeAddColumn = (table: string, col: string, ddl: string) => {", 1, "safeAddColumn 在位（kind 列幂等 ALTER 复用）"),
    ("function dbGet<T = any>(sql: string, params: any[] = []): Promise<T | undefined> {", 1, "dbGet 在位"),
    ("function dbRun(sql: string, params: any[] = []): Promise<{ lastID: number; changes: number }> {", 1, "dbRun 在位"),
    ("function asStr(x: unknown): string {", 1, "asStr 在位（不可信请求值安全取串）"),
    ("function rateLimit({ windowMs, max, keyFn }: { windowMs: number; max: number; keyFn?: (req: any) => string }) {", 1, "rateLimit 工厂在位（function 声明，提升无 TDZ）"),
    ("app.post('/api/mail/send', authenticateGM,", 1, "GM 发信路由恰一处（本环在其前注册玩家层）"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "CREATE TABLE IF NOT EXISTS mail (",
    "CREATE INDEX IF NOT EXISTS idx_mail_user_id ON mail(user_id, id)",
    "INSERT INTO mail (user_id, sender, title, content, attached_lingshi) VALUES (?, ?, ?, ?, ?)",
    "function insertMail(userId: number, title: string, content: string, sender: string, lingshi: number, opts?: { noChronicle?: boolean }): Promise<number> {",
    "const CHRONICLE_MAIL_STONES = 10000;",
    "const authenticateToken = (req: any, res: any, next: any) => {",
    "const authenticateGM = (req: any, res: any, next: any) => {",
    "const JWT_SECRET_USED = JWT_SECRET;",
    "import jwt from 'jsonwebtoken';",
    "app.post('/api/mail/send', authenticateGM,",
    "app.get('/api/gm/messages'",
    "SELECT id, username AS user, text, created_at FROM chat_messages ORDER BY id DESC LIMIT ?",
    "INSERT INTO chat_messages (username, text) VALUES (?, ?)",
    "app.post('/api/gm/login'",
    "const safeAddColumn = (table: string, col: string, ddl: string) => {",
    "function rateLimit({ windowMs, max, keyFn }: { windowMs: number; max: number; keyFn?: (req: any) => string }) {",
]


def fail(msg, code=1):
    print("[FAIL] " + msg)
    sys.exit(code)


# ============================================================ Node 语法门禁
def node_bin():
    root = r"C:/Users/<USER>/.workbuddy-ai/binaries/node/versions"
    env = os.environ.get("YL_NODE")
    if env:
        return env
    pinned = os.path.join(root, "22.22.2-6", "node.exe")
    if os.path.isfile(pinned):
        return pinned  # 任务指定 22.22.2-6，钉死不用「目录排序取最大」
    fail("node 22.22.2-6 not found: %s（可用 YL_NODE 覆盖）" % pinned)


def node_syntax_check(text):
    """产物必须过 node --experimental-strip-types --check。"""
    d = tempfile.mkdtemp(prefix="r99pmchk-")
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
# 用内存库跑与注入 TS **逐字同源**的 SQL 决策逻辑（kind 列幂等/冷却/UTC+8 日限/kind 补写）。
def semantic_harness():
    results = []

    def ck(name, fn):
        try:
            ok = bool(fn())
            results.append((name, ok, ""))
        except Exception as e:
            results.append((name, False, "throw:" + repr(e)))

    MAIL_DDL = ("CREATE TABLE IF NOT EXISTS mail (\n"
                "      id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
                "      user_id INTEGER NOT NULL,\n"
                "      sender TEXT NOT NULL DEFAULT 'system',\n"
                "      title TEXT NOT NULL,\n"
                "      content TEXT NOT NULL DEFAULT '',\n"
                "      attached_lingshi INTEGER NOT NULL DEFAULT 0,\n"
                "      claimed INTEGER NOT NULL DEFAULT 0,\n"
                "      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,\n"
                "      read_at DATETIME,\n"
                "      FOREIGN KEY (user_id) REFERENCES users (id)\n"
                "    )")
    INSERT_MAIL = "INSERT INTO mail (user_id, sender, title, content, attached_lingshi) VALUES (?, ?, ?, ?, ?)"

    def utc_str(ms):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ms / 1000.0))

    def day_start_sql(now_ms):
        # 与 TS 逐字同源：+8h 取 UTC 日零点再 -8h，格式化成 SQLite CURRENT_TIMESTAMP 同构文本
        d8 = time.gmtime((now_ms + PM_UTC8_OFFSET_MS) / 1000.0)
        day_start_utc_ms = calendar.timegm((d8.tm_year, d8.tm_mon, d8.tm_mday, 0, 0, 0)) * 1000 - PM_UTC8_OFFSET_MS
        return utc_str(day_start_utc_ms)

    def cooldown_hit(con, sender, now_ms):
        # 与 TS 逐字同源：last && created_at != null && Date.parse(...'Z') 有限 && now-last < 30000
        row = con.execute(SQL_LAST_SEND, [sender]).fetchone()
        if row is None or row[0] is None:
            return False
        try:
            last_ms = calendar.timegm(time.strptime(str(row[0]), "%Y-%m-%d %H:%M:%S")) * 1000
        except ValueError:
            return False
        return (now_ms - last_ms) < PM_COOLDOWN_MS

    def fresh():
        con = sqlite3.connect(":memory:")
        con.execute(MAIL_DDL)
        con.commit()
        return con

    # ① ALTER 加 kind 列：列存在 + 默认 'system'（新行走默认）
    def h1():
        con = fresh()
        con.execute(SQL_ALTER_KIND)
        con.commit()
        cols = con.execute("PRAGMA table_info(mail)").fetchall()
        names = [c[1] for c in cols]
        dflt = {c[1]: c[4] for c in cols}
        cur = con.execute(INSERT_MAIL, [7, "system", "标题", "正文", 0])
        row = con.execute("SELECT kind FROM mail WHERE id = ?", [cur.lastrowid]).fetchone()
        return "kind" in names and dflt.get("kind") == "'system'" and row[0] == "system"

    # ② ALTER 幂等：二跑必抛 duplicate column（= safeAddColumn 自吞的那个错）
    def h2():
        con = fresh()
        con.execute(SQL_ALTER_KIND)
        try:
            con.execute(SQL_ALTER_KIND)
            return False
        except sqlite3.OperationalError as e:
            return "duplicate column name" in str(e)

    # ③ kind 补写：INSERT（默认 system）→ UPDATE by id → kind='player'
    def h3():
        con = fresh()
        con.execute(SQL_ALTER_KIND)
        cur = con.execute(INSERT_MAIL, [7, "甲", "来自 甲 的私信", "内容内容", 0])
        con.execute(SQL_KIND_UPDATE, [cur.lastrowid])
        con.commit()
        row = con.execute("SELECT kind, sender, attached_lingshi, title FROM mail WHERE id = ?",
                          [cur.lastrowid]).fetchone()
        return row == ("player", "甲", 0, "来自 甲 的私信")

    # ④ 冷却：30s 内最近一封 → 409 分支命中
    def h4():
        con = fresh()
        con.execute(SQL_ALTER_KIND)
        now = int(time.time() * 1000)
        con.execute(INSERT_MAIL, [7, "甲", "t", "c", 0])
        con.execute("UPDATE mail SET kind = 'player', created_at = ? WHERE id = 1", [utc_str(now - 10_000)])
        con.commit()
        return cooldown_hit(con, "甲", now) is True

    # ⑤ 冷却：最近一封 31s 前 → 放行
    def h5():
        con = fresh()
        con.execute(SQL_ALTER_KIND)
        now = int(time.time() * 1000)
        con.execute(INSERT_MAIL, [7, "甲", "t", "c", 0])
        con.execute("UPDATE mail SET kind = 'player', created_at = ? WHERE id = 1", [utc_str(now - 31_000)])
        con.commit()
        return cooldown_hit(con, "甲", now) is False

    # ⑥ 冷却按 sender 隔离 + 按 id DESC 取最近（旧时间戳但 id 更大的行才算「最近」）
    def h6():
        con = fresh()
        con.execute(SQL_ALTER_KIND)
        now = int(time.time() * 1000)
        con.execute(INSERT_MAIL, [7, "甲", "t", "c", 0])  # id=1，-10s
        con.execute("UPDATE mail SET kind = 'player', created_at = ? WHERE id = 1", [utc_str(now - 10_000)])
        con.execute(INSERT_MAIL, [7, "甲", "t", "c", 0])  # id=2，-120s（时间更旧、id 更大）
        con.execute("UPDATE mail SET kind = 'player', created_at = ? WHERE id = 2", [utc_str(now - 120_000)])
        con.execute(INSERT_MAIL, [8, "乙", "t", "c", 0])  # 乙的一封，-3s
        con.execute("UPDATE mail SET kind = 'player', created_at = ? WHERE id = 3", [utc_str(now - 3_000)])
        con.commit()
        return cooldown_hit(con, "甲", now) is False and cooldown_hit(con, "乙", now) is True

    # ⑦ 日限：当日（UTC+8）50 条 → 达上限；49 条 → 未达
    def h7():
        con = fresh()
        con.execute(SQL_ALTER_KIND)
        now = int(time.time() * 1000)
        ds = day_start_sql(now)
        mid_day_ms = calendar.timegm(time.strptime(ds, "%Y-%m-%d %H:%M:%S")) * 1000 + PM_UTC8_OFFSET_MS + 12 * 3600 * 1000
        for n in range(50):
            con.execute(INSERT_MAIL, [7, "甲", "t", "c", 0])
            con.execute("UPDATE mail SET kind = 'player', created_at = ? WHERE id = ?", [utc_str(mid_day_ms + n * 1000), n + 1])
        con.commit()
        c50 = con.execute(SQL_DAILY_COUNT, ["甲", ds]).fetchone()[0]
        con.execute("DELETE FROM mail WHERE id = 50")
        con.commit()
        c49 = con.execute(SQL_DAILY_COUNT, ["甲", ds]).fetchone()[0]
        return c50 == 50 and c49 == 49

    # ⑧ 日限边界：恰好当日零点（UTC+8）的行计入（>=）；零点前 1s 的不计
    def h8():
        con = fresh()
        con.execute(SQL_ALTER_KIND)
        now = int(time.time() * 1000)
        ds = day_start_sql(now)
        ds_ms = calendar.timegm(time.strptime(ds, "%Y-%m-%d %H:%M:%S")) * 1000
        con.execute(INSERT_MAIL, [7, "甲", "t", "c", 0])
        con.execute("UPDATE mail SET kind = 'player', created_at = ? WHERE id = 1", [ds])
        c1 = con.execute(SQL_DAILY_COUNT, ["甲", ds]).fetchone()[0]
        con.execute(INSERT_MAIL, [7, "甲", "t", "c", 0])
        con.execute("UPDATE mail SET kind = 'player', created_at = ? WHERE id = 2", [utc_str(ds_ms - 1000)])
        c2 = con.execute(SQL_DAILY_COUNT, ["甲", ds]).fetchone()[0]
        return c1 == 1 and c2 == 1

    # ⑨ 日限只数 kind='player'：50 条 system 同 sender 同日不占额
    def h9():
        con = fresh()
        con.execute(SQL_ALTER_KIND)
        now = int(time.time() * 1000)
        ds = day_start_sql(now)
        for n in range(50):
            con.execute(INSERT_MAIL, [7, "甲", "t", "c", 0])
            con.execute("UPDATE mail SET created_at = ? WHERE id = ?", [utc_str(now - n * 1000), n + 1])
        con.commit()
        c = con.execute(SQL_DAILY_COUNT, ["甲", ds]).fetchone()[0]
        return c == 0

    # ⑩ 日限按 UTC+8 而非 UTC：UTC 22:00（=UTC+8 次日 06:00）发的信不计入「UTC+8 昨天」窗口
    def h10():
        # 构造时刻：UTC+8 的今天 06:00 = UTC 昨天 22:00
        now = int(time.time() * 1000)
        d8 = time.gmtime((now + PM_UTC8_OFFSET_MS) / 1000.0)
        today8_utc_ms = calendar.timegm((d8.tm_year, d8.tm_mon, d8.tm_mday, 0, 0, 0)) * 1000 - PM_UTC8_OFFSET_MS
        send_ms = today8_utc_ms + 6 * 3600 * 1000  # UTC+8 今天 06:00
        con = fresh()
        con.execute(SQL_ALTER_KIND)
        con.execute(INSERT_MAIL, [7, "甲", "t", "c", 0])
        con.execute("UPDATE mail SET kind = 'player', created_at = ? WHERE id = 1", [utc_str(send_ms)])
        con.commit()
        c_today = con.execute(SQL_DAILY_COUNT, ["甲", day_start_sql(send_ms)]).fetchone()[0]
        return c_today == 1

    ck("① ALTER kind 列存在 + 默认 system 生效", h1)
    ck("② ALTER 二跑抛 duplicate column（幂等吞错依据）", h2)
    ck("③ kind 补写 'player' + 字段落库一致", h3)
    ck("④ 冷却 30s 内 → 409 分支", h4)
    ck("⑤ 冷却 31s 前 → 放行", h5)
    ck("⑥ 冷却按 sender 隔离 + 按 id DESC 取最近", h6)
    ck("⑦ 日限 50 达限 / 49 未达", h7)
    ck("⑧ 日限边界：UTC+8 零点整计入、前 1s 不计", h8)
    ck("⑨ 日限只数 kind='player'（system 不占额）", h9)
    ck("⑩ 日限按 UTC+8 口径（UTC 22:00=次日 06:00）", h10)

    total = len(results)
    nfail = sum(1 for _, ok, _ in results if not ok)
    for name, ok, extra in results:
        print(("  [OK] " if ok else "  [FAIL] ") + name + (("  <" + extra + ">") if extra else ""))
    print("HARNESS_RESULT " + json.dumps({"total": total, "fail": nfail}))
    return total, nfail


def main() -> None:
    ap = argparse.ArgumentParser(description="玩家私信服务端（第 99 环）")
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
        print("== 反向对照（未打第 99 环的服务端）：%s ==" % path)
        has_mark = rev.count(MARK)
        has_ep = rev.count("app.post('/api/mail/send', pm101Dispatch")
        has_col = rev.count(SQL_ALTER_KIND)
        print("  [r99pm] 计数 = %d（期望 0）" % has_mark)
        print("  app.post('/api/mail/send', pm101Dispatch 计数 = %d（期望 0）" % has_ep)
        print("  ADD COLUMN kind 计数 = %d（期望 0）" % has_col)
        if has_mark == 0 and has_ep == 0 and has_col == 0:
            print("  [REVERSE] PASS（基线确实未打第 99 环，标记缺席）")
        else:
            print("  [REVERSE] FAIL（★ 该源已含第 99 环痕迹，不构成基线）")
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
    base_player = src.count("kind = 'player'")     # = 0（REQUIRES 已断言）
    base_403 = src.count("res.status(403")
    base_require = src.count("require(")
    base_pragma = src.count("PRAGMA")
    base_interval = src.count("setInterval(")
    base_chat_insert = src.count("INSERT INTO chat_messages")
    base_mail_insert = src.count("INSERT INTO mail")
    base_expired = src.count("TokenExpiredError")
    base_expired_line = src.count("if (err.name === 'TokenExpiredError') return res.sendStatus(401);")
    base_users_lookup = src.count("SELECT id, username FROM users WHERE username = ?")
    base_send_route = src.count("app.post('/api/mail/send'")

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁（新写法存在 + 旧写法清零 + 冻结基线 + 红线）
    mark_n = sum(new.count(MARK) for _, _, new in EDITS)
    delta_player = sum(new.count("kind = 'player'") for _, _, new in EDITS)
    gates = [
        ("标记 [r99pm] 就位", MARK, mark_n),
        # ALTER（E1）
        ("ALTER kind 列（幂等 safeAddColumn）", SQL_ALTER_KIND, 1),
        ("kind 默认 system 注释口径", "'system'=系统/GM 信（默认）", 1),
        # 端点（E2）
        ("玩家层注册（在 GM 路由之前）", "app.post('/api/mail/send', pm101Dispatch);", 1),
        ("GM 路由原样恰一处", "app.post('/api/mail/send', authenticateGM,", 1),
        ("同路径路由总数 = 2", "app.post('/api/mail/send'", base_send_route + 1),
        ("dispatch 定义", "const pm101Dispatch = (req: any, res: any, next: any) => {", 1),
        ("业务体定义", "async function pm101Send(req: any, res: any) {", 1),
        ("落库函数定义+调用", "pm101InsertPlayerMail(", 2),
        ("落库走 insertMail（零改动复用）", "await insertMail(targetUserId, '来自 ' + senderName + ' 的私信', content, senderName, 0);", 1),
        ("kind 补写 UPDATE", SQL_KIND_UPDATE, 1),
        ("冷却常量 30s", "const PM_COOLDOWN_MS = 30 * 1000;", 1),
        ("日限常量 50", "const PM_DAILY_LIMIT = 50;", 1),
        ("UTC+8 口径常量", "const PM_UTC8_OFFSET_MS = 8 * 60 * 60 * 1000;", 1),
        ("SQL 同源 SQL_LAST_SEND（定义恰一处，按名引用）", SQL_LAST_SEND, 1),
        ("SQL 同源 SQL_DAILY_COUNT（定义恰一处，按名引用）", SQL_DAILY_COUNT, 1),
        ("SQL 常量按名引用 PM_LAST_SEND_SQL", "PM_LAST_SEND_SQL", 2),
        ("SQL 常量按名引用 PM_DAILY_COUNT_SQL", "PM_DAILY_COUNT_SQL", 2),
        ("限流安全网挂接", "pm101Rate(req, res, () => { pm101Send(req, res); });", 1),
        ("过期 token 直接 401（续期链路）", "if (err.name === 'TokenExpiredError') return res.sendStatus(401);", base_expired_line + 1),
        ("TokenExpiredError 总数 = base+1", "TokenExpiredError", base_expired + 1),
        ("400 需要收件人", "'需要收件人'", 1),
        ("400 收件人不存在", "'收件人不存在'", 1),
        ("400 不能给自己发私信", "'不能给自己发私信'", 1),
        ("400 内容 2~500", "if (stripped < 2 || stripped > 500) {", 1),
        ("409 发送太频繁", "'发送太频繁，请稍后再试'", 1),
        ("409 日限 50 条", "'今日私信已达上限（50 条）'", 1),
        ("200 {ok,id}", "return res.json({ ok: true, id: mailId });", 1),
        ("users 表存在性校验", "SELECT id, username FROM users WHERE username = ?", base_users_lookup + 1),
        # 落库通道不变（绝不经第二条 INSERT）
        ("INSERT INTO mail 总数不变（仍走 insertMail）", "INSERT INTO mail", base_mail_insert),
        # 隐私红线：绝不写世界聊天
        ("INSERT INTO chat_messages 总数不变", "INSERT INTO chat_messages", base_chat_insert),
        ("kind='player' 总数 = 注入精确 delta", "kind = 'player'", base_player + delta_player),
    ]
    # 冻结：既有 GM/邮件基座一字不动（主控裁定 A：GM 端点一个字节不动）
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
    bak = "%s.bak-r99pm-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r99pm-", suffix=".tmp")
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
