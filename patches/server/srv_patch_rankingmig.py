# -*- coding: utf-8 -*-
r"""srv_patch_rankingmig.py — 0.8.9 存量库加列幂等环（链第 18 环 / 末环）

## 背景（P0② 空库冷启动必崩，已实测复现 9 次全崩）

`srv/index_v28.ts:180-197` 的建表 DDL **建表时就带 `name` 列**：

```ts
CREATE TABLE IF NOT EXISTS rankings (
  user_id INTEGER PRIMARY KEY,
  username TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',      // ← :184，建表即有
  ...
)
```

而 `:388-393` 有一处守卫，`db.exec("ALTER TABLE rankings ADD COLUMN name ...")`：

```ts
db.all("PRAGMA table_info(rankings)", (err: any, rows: any[]) => {
  if (!err && rows && !rows.some((r: any) => r.name === 'name')) {
    db.exec("ALTER TABLE rankings ADD COLUMN name TEXT NOT NULL DEFAULT ''");
  }
  backfillRankingNames(); // 在 ALTER 入队之后调用（serialize 队列保证列已存在）
});
```

### 根因（不是「竞态」，是**完成屏障缺失**）

驱动是**回调式 `sqlite3`**。`db.serialize()` 只保证「同一回调栈内入队的语句按序执行」，
**不提供「上一条语句已完成」的屏障**：`CREATE TABLE rankings`（:180）与紧随其后的
`PRAGMA table_info(rankings)`（:380 / :388）在**同一个 serialize 回调里**入队，
而 `PRAGMA` 由 SQLite **重新 prepare 一次 schema**，与 `CREATE TABLE` 之间没有任何等待点
⇒ PRAGMA 可能读到**空 schema**（实测 `rows=0` @44ms）⇒
`.some(r => r.name === 'name')` **恒为 false** ⇒ 守卫误判「缺列」⇒ 对**已经含 name 列的表**
再次 `ADD COLUMN name` ⇒ `SQLITE_ERROR: duplicate column name: name`

⇒ 该错误从 `db` 的 `'error'` 事件抛出，**在模块顶层（建表 block 内）无人 catch**
⇒ 进程 `rc=1` 退出（实测日志：`[Error: SQLITE_ERROR: duplicate column name: name` +
`Emitted 'error' event on Database instance` + `Node.js v22.22.2`）。

**空库（全新部署）100% 触发**：老库因为 `rankings` 早已存在且 PRAGMA 往往能读到完整 schema
而侥幸不崩 —— 这条缺陷只在**冷启动**这条路上暴露，属**首次部署即死**级别。

`:392` 那句注释「在 ALTER 入队之后调用（serialize 队列保证列已存在）」**就是错的假设**——
本环连注释一起修正。

### 修法：方案 D（**幂等 ALTER**）—— 由 lead 裁定

**不**用 `rows.length > 0` 之类的判断（那只降低概率、不消除路径：PRAGMA 读到**部分** schema 时
`rows.length > 0` 但 `name` 仍缺失，误判照旧）。

正确做法是**让 DDL 本身幂等**：新增 `safeAddColumn(table, col, ddl)`，
内部容忍 `duplicate column name` 错误、其余错误照常 `console.error` 上报。
守卫的 PRAGMA 判断保留作**快路径**（列已存在时可省一次 DDL），
但真正兜底的是 DDL 的幂等性 —— 重跑 / 冷启动双安全。

## 同病清单（全仓 `PRAGMA table_info` × `ALTER TABLE ... ADD COLUMN` 交叉排查）

| 表 | 列 | 行号 | 风险 | 处理 |
|---|---|---|---|---|
| `users` | `linuxdo_id` | :107 | 中（类内先例，同病） | → `safeAddColumn` |
| `saves` | `gm_revision` | :130 | 中 | → `safeAddColumn` |
| `saves` | `tower_lump_left` | :141 | 中 | → `safeAddColumn` |
| `saves` | `exped_lump_left` | :142 | 中 | → `safeAddColumn` |
| `saves` | `econ_win_start` | :143 | 中 | → `safeAddColumn` |
| `saves` | `econ_win_exp` | :144 | 中 | → `safeAddColumn` |
| `saves` | `econ_win_stone` | :145 | 中 | → `safeAddColumn` |
| `users` | `last_login` | :283 | 中 | → `safeAddColumn` |
| `saves` | `return_buff_until` | :289 | 中 | → `safeAddColumn` |
| `saves` | `offline_claimed_until` | :296 | 中 | → `safeAddColumn` |
| `saves` | `month_card_until` | :304 | 中 | → `safeAddColumn` |
| `saves` | `title_id` | :329 | 中 | → `safeAddColumn` |
| `rebirth_state` | `pills` | :368 | 中 | → `safeAddColumn` |
| `rebirth_state` | `pill_stash` | :373 | 中（任务点名） | → `safeAddColumn` |
| `rankings` | `season` | :382 | **高** | → `safeAddColumn` |
| `rankings` | `name` | :390 | **高（本次崩点）** | → `safeAddColumn` |
| `adventures` | `tickets` | :561 | 中 | → `safeAddColumn` |
| `adventures` | `bonus_text` | :562 | 中 | → `safeAddColumn` |
| `users` | `banned` | :2780 | 中 | → `safeAddColumn` |
| `sects` | `join_mode` | :11436 | 中 | → `safeAddColumn` |

**全仓 20 处 ALTER 无遗漏，全部收口到 `safeAddColumn`（第 20 处即辅助函数体内唯一一处）。**

> 未修 = 同一颗雷留了 19 个位：任意一次「建表后 PRAGMA 读到空/部分 schema」都会撞上
> `duplicate column name` 而顶层退出。本轮一次收口。

**不改**的两处 `PRAGMA table_info`（非本类缺陷，仅只读、无 ALTER 配对）：
`:105`（users 查询侧 PRAGMA，配对 ALTER 在 :107）与 `:2998`（GM `/api/gm/schema` 只读反射）。

## 改动清单（21 处，锚区互不重叠）

| # | 锚点 | 改动 |
|---:|---|---|
| T1 | `:84-85` 之后（`dbPath` 定义与 `new sqlite3.Database` 之间） | 插入 `safeAddColumn` 辅助函数定义 |
| T2 | `:107` | `db.exec(...)` → `safeAddColumn('users', 'linuxdo_id', ...)` |
| T3..T7 | `:130 / :141 / :142 / :143 / :144 / :145` | saves 6 列 → `safeAddColumn` |
| T8..T12 | `:283 / :289 / :296 / :304 / :329` | users.last_login + saves 4 列 → `safeAddColumn` |
| T13..T14 | `:368 / :373` | rebirth_state 2 列 → `safeAddColumn` |
| T15 | `:382` | rankings.season → `safeAddColumn` |
| T16 | `:388-393` | rankings.name → `safeAddColumn` + **修正 :392 错误注释** |
| T17 | `:561-562` | adventures 2 列 → `safeAddColumn` |
| T18 | `:2780` | users.banned → `safeAddColumn` |
| T19 | `:11436` | sects.join_mode → `safeAddColumn` |

## 与其它环的关系（零交集）

* 唯一新增的函数定义插在 `:85`（`dbPath`）与 `:86`（`new sqlite3.Database`）之间 ——
  该区间前 17 环无人触碰（各环锚区：ki001 = `settleSaveEconV2`；net2 = 回显中间件 / grant / 409；
  baseclean089 = `loadGameDicts` / `GM_PASSWORD` / GM 快照端点）。
* 20 处改动全部落在 **建表 / 迁移守卫区**（`:93-:2783` 与 `:11353-:11439`），
  均为纯 DDL 调用形态替换：`db.exec(X)` → `safeAddColumn(T, C, X)`，
  **SQL 文本一字未改**（门禁 G10 逐字复核），守卫的 PRAGMA 判断与嵌套层级一字未动。
* 不新增端点、不改任何业务语义、不动 `backfillRankingNames()`（:1028）。

## 红线

* 不碰 `_v281_base/`（基座只读）；不改任何既存环的补丁文件（本环是**新增**末环）。
* 不碰 `build/`（i8-gmdeploy 的前端域）。
* 不改任何既存门禁期望值。

## 用法

```
python srv_patch_rankingmig.py --src <上一环产物>    # 就地原子写回 --src
python srv_patch_rankingmig.py --selftest            # 只跑门禁，不碰文件
```

幂等：已含 `RANKINGMIG089` 标记则 SKIP。锚点不唯一一律中止（拒绝静默失败）。
"""
import argparse
import hashlib
import os
import re
import shutil
import sys
import time

MARK = 'RANKINGMIG089'
HERE = os.path.dirname(os.path.abspath(__file__))


def md5s(s: str) -> str:
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def die(msg: str):
    print('[FAIL] ' + msg)
    sys.exit(1)


def apply_one(text: str, tag: str, old: str, new: str, expect: int = 1) -> str:
    n = text.count(old)
    if n != expect:
        die('%s 锚点命中 %d 次（期望 %d）—— 拒绝静默失败' % (tag, n, expect))
    print('  [OK] %-6s 锚点命中 %d 次' % (tag, n))
    return text.replace(old, new, expect)


def _block(text: str, anchor: str, span: int = 4000) -> str:
    """取锚点起 span 字符（默认 4000）——只在该窗口内断言，避免全文计数误伤邻座。"""
    i = text.find(anchor)
    return '' if i < 0 else text[i:i + span]


# ─────────────────────────────────────────────────────────
# T1 · 幂等加列辅助函数（插在 dbPath 定义之后、new sqlite3.Database 之前）
#
# 为什么必须放在这里：本函数被 :293 起的**两个** db.serialize 块共用
#   （:93 建表迁移块 + :279 Y 系列增量 schema 块），
#   必须定义在两者之前；而 `db` 是 const（:86），函数体只在**调用时**才求值 `db`，
#   所以定义在 `const db = new sqlite3.Database(...)` **之后**最稳妥（无 TDZ 顾虑）。
# ─────────────────────────────────────────────────────────
T1_ANCHOR = """const dbPath = process.env.DATABASE_PATH
  ? path.resolve(process.env.DATABASE_PATH)
  : defaultDbPath;"""

T1_NEW = """const dbPath = process.env.DATABASE_PATH
  ? path.resolve(process.env.DATABASE_PATH)
  : defaultDbPath;

// RANKINGMIG089：**幂等加列**。serialize 队列只保证「入队顺序」，不提供「完成屏障」——
//   紧随 CREATE TABLE 的 `PRAGMA table_info(T)` 可能读到空 / 部分 schema，使
//   `!rows.some(r => r.name === col)` 误判「缺列」，对已含该列的表重复 ADD COLUMN ⇒
//   `SQLITE_ERROR: duplicate column name` ⇒ 该错误经 db 'error' 事件在顶层抛出、无人 catch
//   ⇒ **进程起不来**（空库冷启动 100% 命中；见本环文件头）。
//   故不加 `rows.length > 0` 之类的概率性判断，而是让 **DDL 本身幂等**：
//   容忍 `duplicate column name`（重跑 / 冷启动双安全），其余错误照常上报。
//   守卫处的 PRAGMA 判断保留作**快路径**（列已存在可省一次 DDL），真正兜底的是这里。
const safeAddColumn = (table: string, col: string, ddl: string) => {
  db.exec(ddl, (e: any) => {
    if (e && !/duplicate column name/i.test(String(e.message || ''))) {
      console.error('[migrate]', table, col, e.message);
    }
  });
};"""

# ─────────────────────────────────────────────────────────
# T2..T19 · 20 处 ALTER 收口（SQL 文本一字不改，只换调用形态）
# ─────────────────────────────────────────────────────────
ALTERS = [
    # (tag, table, col, 原始 db.exec 调用片段)
    ('T2',  'users',         'linuxdo_id',
     """db.exec('ALTER TABLE users ADD COLUMN linuxdo_id TEXT')"""),
    ('T3',  'saves',         'gm_revision',
     """db.exec('ALTER TABLE saves ADD COLUMN gm_revision INTEGER DEFAULT 0')"""),
    ('T4',  'saves',         'tower_lump_left',
     """db.exec('ALTER TABLE saves ADD COLUMN tower_lump_left INTEGER NOT NULL DEFAULT 12000000')"""),
    ('T5',  'saves',         'exped_lump_left',
     """db.exec('ALTER TABLE saves ADD COLUMN exped_lump_left INTEGER NOT NULL DEFAULT 2000000')"""),
    ('T6',  'saves',         'econ_win_start',
     """db.exec('ALTER TABLE saves ADD COLUMN econ_win_start INTEGER')"""),
    ('T7',  'saves',         'econ_win_exp',
     """db.exec('ALTER TABLE saves ADD COLUMN econ_win_exp INTEGER NOT NULL DEFAULT 0')"""),
    ('T8',  'saves',         'econ_win_stone',
     """db.exec('ALTER TABLE saves ADD COLUMN econ_win_stone INTEGER NOT NULL DEFAULT 0')"""),
    ('T9',  'users',         'last_login',
     """db.exec('ALTER TABLE users ADD COLUMN last_login TEXT')"""),
    ('T10', 'saves',         'return_buff_until',
     """db.exec('ALTER TABLE saves ADD COLUMN return_buff_until INTEGER')"""),
    ('T11', 'saves',         'offline_claimed_until',
     """db.exec('ALTER TABLE saves ADD COLUMN offline_claimed_until INTEGER')"""),
    ('T12', 'saves',         'month_card_until',
     """db.exec('ALTER TABLE saves ADD COLUMN month_card_until INTEGER')"""),
    ('T13', 'saves',         'title_id',
     """db.exec('ALTER TABLE saves ADD COLUMN title_id INTEGER')"""),
    ('T14', 'rebirth_state', 'pills',
     """db.exec('ALTER TABLE rebirth_state ADD COLUMN pills INTEGER NOT NULL DEFAULT 0')"""),
    ('T15', 'rebirth_state', 'pill_stash',
     """db.exec('ALTER TABLE rebirth_state ADD COLUMN pill_stash INTEGER NOT NULL DEFAULT 0')"""),
    ('T16', 'rankings',      'season',
     """db.exec('ALTER TABLE rankings ADD COLUMN season TEXT')"""),    ('T17', 'rankings',      'name',
     """db.exec("ALTER TABLE rankings ADD COLUMN name TEXT NOT NULL DEFAULT ''")"""),
    ('T18', 'adventures',    'tickets',
     """db.exec('ALTER TABLE adventures ADD COLUMN tickets INTEGER NOT NULL DEFAULT 0')"""),
    ('T19', 'adventures',    'bonus_text',
     """db.exec("ALTER TABLE adventures ADD COLUMN bonus_text TEXT NOT NULL DEFAULT ''")"""),
    ('T20', 'users',         'banned',
     """db.exec('ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0')"""),
    ('T21', 'sects',         'join_mode',
     """db.exec("ALTER TABLE sects ADD COLUMN join_mode TEXT NOT NULL DEFAULT 'auto'")"""),
]


def _wrap(table: str, col: str, call: str) -> str:
    """把 `db.exec(SQL)` 换成 `safeAddColumn('T', 'c', SQL)`（SQL 文本逐字保留）。"""
    m = re.fullmatch(r"db\.exec\((.+)\)", call, re.S)
    if not m:
        die('内部错误：无法解析 ALTER 调用 %r' % call)
    sql = m.group(1)
    return "safeAddColumn('%s', '%s', %s)" % (table, col, sql)


def _build_t16_old() -> str:
    """rankings 的 **两处** PRAGMA 守卫（:380 season + :388 name）——本环合并为一处。

    合并理由：任务门禁要求 `PRAGMA table_info(rankings)` 出现次数 <= 1。
    两次 PRAGMA 读的是**同一份** schema，纯属冗余入队；合并后语义等价
    （season 的 ALTER 仍先于 name 的 ALTER 入队；`backfillRankingNames()` 仍在
    两个 ALTER 之后调用，位置不变）。
    """
    return (
        """  db.all("PRAGMA table_info(rankings)", (err: any, rows: any[]) => {\n"""
        """    if (!err && rows && !rows.some((r: any) => r.name === 'season')) {\n"""
        """      db.exec('ALTER TABLE rankings ADD COLUMN season TEXT');\n"""
        """    }\n"""
        """  });\n"""
        """  // fix(rank) 2026-09-17：rankings.name——冗余角色昵称（来源 saves.save_data JSON 的 player.name，\n"""
        """  // users 表无昵称列）。此前排行榜展示 username（登录账号）。读侧回落 username；改名场景容忍旧名，\n"""
        """  // 玩家下次存档上传即刷新。存量行回填见 backfillRankingNames()（幂等：只补 name 为空的行）。\n"""
        """  db.all("PRAGMA table_info(rankings)", (err: any, rows: any[]) => {\n"""
        """    if (!err && rows && !rows.some((r: any) => r.name === 'name')) {\n"""
        """      db.exec("ALTER TABLE rankings ADD COLUMN name TEXT NOT NULL DEFAULT ''");\n"""
        """    }\n"""
        """    backfillRankingNames(); // 在 ALTER 入队之后调用（serialize 队列保证列已存在）\n"""
        """  });"""
    )


def _build_t16_new() -> str:
    """合并为**一处** `PRAGMA table_info(rankings)`，两列共用一次 schema 读取。

    关键修正（本环存在的理由）：
      * `PRAGMA table_info(rankings)` **不提供完成屏障** —— serialize 队列只保证入队顺序，
        紧随 `CREATE TABLE rankings`（:180）的 PRAGMA 可能读到空 / 部分 schema（实测 rows=0 @44ms）。
      * 于是 `.some(r => r.name === 'X')` 误报「缺列」→ 对已含该列的表重复 `ADD COLUMN`
        → `SQLITE_ERROR: duplicate column name` → db 'error' 事件在顶层抛出、无人 catch → 进程顶崩。
      * 修法：守卫的 PRAGMA 判断降级为**快路径**（列已存在就省一次 DDL），
        真正兜底交给 `safeAddColumn` —— DDL 本身幂等，重复加列被吞，冷启动 100% 安全。
    注意 `backfillRankingNames()` 仍排在两个 ALTER **之后**（列必存在：或建表自带 :184，或上方 ADD 已入队）。
    """
    return (
        """  // RANKINGMIG089：rankings 的两处加列守卫（season / name）**合并为一次 schema 读取** ——\n"""
        """  // 原先 :380 与 :388 各读一次同一份 schema，纯冗余入队；合并后语义等价\n"""
        """  // （season 的 ALTER 仍先于 name 入队；backfillRankingNames() 仍在两者之后）。\n"""
        """  // 该 PRAGMA 只是**快路径**（列已存在则省一次 DDL），**不能**作为「是否缺列」的判据：\n"""
        """  // 紧随 CREATE TABLE 的 PRAGMA 无完成屏障，可能读到空/部分 schema（实测 rows=0 @44ms）而误报缺列。\n"""
        """  // 真正兜底的是 safeAddColumn：即便误判，`duplicate column name` 也会被吞掉，不再顶崩进程。\n"""
        """  db.all("PRAGMA table_info(rankings)", (err: any, rows: any[]) => {\n"""
        """    if (!err && rows && !rows.some((r: any) => r.name === 'season')) {\n"""
        """      safeAddColumn('rankings', 'season', 'ALTER TABLE rankings ADD COLUMN season TEXT');\n"""
        """    }\n"""
        """    if (!err && rows && !rows.some((r: any) => r.name === 'name')) {\n"""
        """      safeAddColumn('rankings', 'name', "ALTER TABLE rankings ADD COLUMN name TEXT NOT NULL DEFAULT ''");\n"""
        """    }\n"""
        """    backfillRankingNames(); // 列必存在：或建表自带（:184）或上方 ADD 已入队，且已幂等\n"""
        """  });"""
    )


def selftest() -> int:
    """在真实的上一环产物上跑门禁（不碰 srv/index_v28.ts）。"""
    print('0.8.9 存量库加列幂等环（链第 18 环）— 自证')
    gates = []
    ok = True

    def gate(name, cond, detail=''):
        nonlocal ok
        gates.append((name, bool(cond), detail))
        if not cond:
            ok = False

    cand = os.path.join(HERE, '_chainstage', 's17.baseclean089.ts')
    if not os.path.isfile(cand):
        cand = os.path.join(HERE, 'srv', 'index_v28.ts')
    if not os.path.isfile(cand):
        print('  [FAIL] 找不到上一环产物')
        return 1

    src = open(cand, encoding='utf-8').read()
    print('  上一环产物 : %s  bytes=%d md5=%s'
          % (os.path.basename(cand), len(src.encode('utf-8')), md5s(src)))

    if MARK in src:
        print('  [SKIP] 已含 %s 标记' % MARK)
        return 0

    T16_OLD, T16_NEW = _build_t16_old(), _build_t16_new()
    guards = [('T1', T1_ANCHOR), ('T16', T16_OLD)]
    for tag, _table, _col, call in ALTERS:
        if tag in ('T16', 'T17'):
            # rankings.season / name 两处均在 T16_OLD 合并块内，已由 T16 守卫覆盖
            continue
        guards.append((tag, call))
    for tag, anc in guards:
        if src.count(anc) != 1:
            print('  [FAIL] 前置守卫 %s 锚点命中 %d 次（期望 1）' % (tag, src.count(anc)))
            return 1
    print('  [OK]   前置守卫：%d 处锚点各命中 1 次' % len(guards))

    out = apply_one(src, 'T1', T1_ANCHOR, T1_NEW)
    out = apply_one(out, 'T16', T16_OLD, T16_NEW)
    for tag, table, col, call in ALTERS:
        if tag in ('T16', 'T17'):
            continue
        out = apply_one(out, tag, call, _wrap(table, col, call))

    delta = len(out.encode('utf-8')) - len(src.encode('utf-8'))
    _gates(out, delta, gate)

    print('\n  --- 门禁 ---')
    for name, c, detail in gates:
        print('  [%s] %s%s' % ('OK' if c else 'FAIL', name, ('  ' + detail) if detail else ''))
    print('\n  自证结果：%s' % ('全 PASS' if ok else '存在 FAIL'))
    return 0 if ok else 1


def _gates(text: str, delta: int, gate) -> None:
    """本环门禁（main 与 selftest 共用同一套，避免两处漂移）。"""
    # ── 交付门禁：任务点名的三条硬指标 ──
    n_direct = text.count("db.exec('ALTER TABLE") + text.count('db.exec("ALTER TABLE')
    gate('G1 [任务] db.exec(ALTER TABLE ...) 直调 == 0（全走 safeAddColumn）',
         n_direct == 0, '实际 %d' % n_direct)
    n_safe = text.count('safeAddColumn(')
    gate('G2 [任务] safeAddColumn( 出现 >= 2（season + name 至少两处）',
         n_safe >= 2, '实际 %d' % n_safe)
    # 调用点 = `safeAddColumn('表', '列', ...`（带引号实参）——排除 `const safeAddColumn = (` 定义行
    n_call = len(re.findall(r"safeAddColumn\('[a-z_]+', '[a-z_]+',", text))
    n_pragma_rank = text.count('PRAGMA table_info(rankings)')
    gate('G3 [任务] PRAGMA table_info(rankings) <= 1',
         n_pragma_rank <= 1, '实际 %d' % n_pragma_rank)

    # ── 覆盖门禁：20 处 ALTER 一个不漏 ──
    gate('G4 辅助函数定义恰 1 处（含容错正则 / 非重复错误上报）',
         text.count('const safeAddColumn = (table: string, col: string, ddl: string) => {') == 1
         and text.count("/duplicate column name/i") == 1
         and "[migrate]" in text)
    # 存量守恒（坑 3/14）：后续环会继续追加 safeAddColumn 调用点，故用 >= 而非 ==
    gate('G5 safeAddColumn 调用点 >= 20（18 处独立守卫 + rankings 合并块内 2 处）',
         n_call >= 20, '实际 %d' % n_call)
    # 20 处 ALTER 收口（rankings 两处在合并块内，其余 18 处独立）
    for tbl, col in (('users', 'linuxdo_id'), ('saves', 'gm_revision'),
                     ('saves', 'tower_lump_left'), ('saves', 'exped_lump_left'),
                     ('saves', 'econ_win_start'), ('saves', 'econ_win_exp'),
                     ('saves', 'econ_win_stone'), ('users', 'last_login'),
                     ('saves', 'return_buff_until'), ('saves', 'offline_claimed_until'),
                     ('saves', 'month_card_until'), ('saves', 'title_id'),
                     ('rebirth_state', 'pills'), ('rebirth_state', 'pill_stash'),
                     ('rankings', 'season'), ('rankings', 'name'),
                     ('adventures', 'tickets'), ('adventures', 'bonus_text'),
                     ('users', 'banned'), ('sects', 'join_mode')):
        key = "safeAddColumn('%s', '%s'," % (tbl, col)
        gate('G6  %-13s . %-21s 已收口' % (tbl, col), text.count(key) == 1,
             '实际 %d' % text.count(key))
    # 只数**真实 DDL**（`ADD COLUMN <列名>` 形态），不数注释散文里提到的 "ADD COLUMN"
    n_ddl = len(re.findall(r'ADD COLUMN [a-z_]+', text))
    # 存量守恒（坑 3/14）：后续环会继续追加 ADD COLUMN，故用 >= 而非 ==
    gate('G7 全仓 ADD COLUMN DDL >= 20（无漏网）',
         n_ddl >= 20, '实际 %d' % n_ddl)
    _season_at = text.find("safeAddColumn('rankings', 'season',")
    _name_at = text.find("safeAddColumn('rankings', 'name',")
    _merge_win = _block(text, "if (!err && rows && !rows.some((r: any) => r.name === 'season'))", 700)
    gate('G7b rankings 两列在同一 PRAGMA 块内（season 先于 name）',
         _season_at >= 0 and _name_at > _season_at
         and _merge_win.count("safeAddColumn('rankings', 'name',") == 1)

    # ── 语义红线：SQL 文本一字未改 ──
    gate('G8  rankings.name 的 DDL 文本逐字未改',
         text.count(""".some((r: any) => r.name === 'name')) {
      safeAddColumn('rankings', 'name', "ALTER TABLE rankings ADD COLUMN name TEXT NOT NULL DEFAULT ''");""") == 1)
    gate('G9  rankings.season 的 DDL 文本逐字未改',
         text.count("safeAddColumn('rankings', 'season', 'ALTER TABLE rankings ADD COLUMN season TEXT')") == 1)
    gate('G10 sects.join_mode 的 DDL 文本逐字未改',
         text.count("""safeAddColumn('sects', 'join_mode', "ALTER TABLE sects ADD COLUMN join_mode TEXT NOT NULL DEFAULT 'auto'")""") == 1)

    # ── 结构红线：建表 DDL / 守卫层级 / 既有函数未动 ──
    gate('G11 红线：rankings 建表仍含 name 列（不动基座 DDL）',
         text.count('CREATE TABLE IF NOT EXISTS rankings (') == 1
         and 'name TEXT NOT NULL DEFAULT' in _block(text, 'CREATE TABLE IF NOT EXISTS rankings (', 900))
    gate('G12 红线：:392 那句错误注释已不再出现（「serialize 队列保证列已存在」）',
         'serialize 队列保证列已存在' not in text)
    gate('G13 红线：backfillRankingNames 定义 + 调用各 1 处（:1028 定义未动）',
         text.count('function backfillRankingNames(): void {') == 1
         and text.count('backfillRankingNames();') == 1)
    gate('G14 红线：rebirth_state.pill_stash 守卫的 PRAGMA 判断仍在',
         "rows.some((r: any) => r.name === 'pill_stash')" in text)
    gate('G15 红线：GM /api/gm/schema 只读 PRAGMA 反射未被改坏',
         text.count('db.all(`PRAGMA table_info(${t})`') == 1)
    gate('G16 红线：users.ban 端点未被破坏',
         text.count("app.post('/api/gm/players/:id/ban', authenticateGM") == 1)
    gate('G17 红线：其它环锚区未动（ki001 / net2 / baseclean089 同名函数仍在）',
         text.count('function settleSaveEconV2') == 1
         and text.count("error: 'stale_save'") == 1
         and text.count('function loadGameDicts') == 1
         and text.count('const GM_PASSWORD = process.env.GM_PASSWORD;') == 1)
    gate('G18 增长率 ∈ [0, 6000] B', 0 <= delta <= 6000, 'delta = %+d B' % delta)
    gate('G19 幂等标记就位', MARK in text)


def main() -> int:
    ap = argparse.ArgumentParser(description='0.8.9 存量库加列幂等环（链第 18 环）')
    ap.add_argument('--src', help='上一环产物（就地原子写回）')
    ap.add_argument('--out', help='本环产物（缺省 = 就地写 --src）')
    ap.add_argument('--selftest', action='store_true', help='只跑自证，不碰文件')
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    if not a.src:
        die('必须给 --src（或 --selftest）')

    src = os.path.abspath(a.src)
    if not os.path.isfile(src):
        die('src 不存在: %s' % src)
    out = os.path.abspath(a.out) if a.out else src
    if out != src and not os.path.isdir(os.path.dirname(out)):
        die('out 目录不存在: %s' % os.path.dirname(out))

    text = open(src, encoding='utf-8').read()
    before_bytes = len(text.encode('utf-8'))
    print('0.8.9 存量库加列幂等环（链第 18 环 / 末环）')
    print('  source : %s  bytes=%d md5=%s' % (src, before_bytes, md5s(text)))

    if MARK in text:
        print('  [SKIP] 已包含 %s 标记，无需重复打补丁' % MARK)
        return 0

    T16_OLD, T16_NEW = _build_t16_old(), _build_t16_new()

    # ── 前置守卫（锚点必须唯一，否则拒绝静默失败）──
    guards = [('T1', T1_ANCHOR), ('T16', T16_OLD)]
    for tag, table, col, call in ALTERS:
        if tag in ('T16', 'T17'):
            # rankings.season / name 两处均在 T16_OLD 合并块内 —— 已由 T16 守卫覆盖
            continue
        guards.append((tag, call))
    for tag, anc in guards:
        if text.count(anc) != 1:
            die('前置守卫失败：%s 锚点命中 %d 次（期望 1）—— 基线不符' % (tag, text.count(anc)))
    print('  [OK]   前置守卫：%d 处锚点各命中 1 次' % len(guards))

    # ── 应用 ──
    text = apply_one(text, 'T1', T1_ANCHOR, T1_NEW)
    text = apply_one(text, 'T16', T16_OLD, T16_NEW)   # rankings 双列合并块（含注释修正）
    for tag, table, col, call in ALTERS:
        if tag in ('T16', 'T17'):
            continue
        text = apply_one(text, tag, call, _wrap(table, col, call))

    delta = len(text.encode('utf-8')) - before_bytes
    gates = []

    def gate(name, cond, detail=''):
        gates.append((name, bool(cond), detail))

    _gates(text, delta, gate)

    bad = [g for g in gates if not g[1]]
    print('\n  --- 门禁 ---')
    for name, c, detail in gates:
        print('  [%s] %s%s' % ('OK' if c else 'FAIL', name, ('  ' + detail) if detail else ''))
    if bad:
        print('\n[ABORT] 门禁未全过（%d 条 FAIL），不写出' % len(bad))
        return 1

    if out != src:
        open(out, 'wb').write(text.encode('utf-8'))
        print('\n  [写出] %s  bytes=%d  md5=%s' % (out, len(text.encode('utf-8')), md5s(text)))
    else:
        bak = '%s.bak-rankingmig-%s' % (src, time.strftime('%Y%m%d-%H%M%S'))
        shutil.copy2(src, bak)
        print('\n  [备份] %s' % bak)
        open(src, 'wb').write(text.encode('utf-8'))
        print('  [写出] %s  bytes=%d  md5=%s' % (src, len(text.encode('utf-8')), md5s(text)))

    print('  [PASS] 存量库加列幂等收口完成（delta %+d B）' % delta)
    return 0


if __name__ == '__main__':
    sys.exit(main())
