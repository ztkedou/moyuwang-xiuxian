# -*- coding: utf-8 -*-
r"""srv_patch_gmclean_srvadmin.py — R-006 GM 会话过期清理环（0.8.11 服务端 / srv-admin 独占）

只做一件事：给 `gm_sessions` 补**批量过期清理**（0.8.10 只做了「用到时惰性删一行」）。

## 缺口（为什么需要本环）

0.8.10（链第 21 环 s21 ⑥）给 `gm_sessions` 加了 `expires_at` 列 + 登录写 7 天 + `authenticateGM`
里**惰性**删「本次请求用到的那一行」。但：

* **惰性删只清「被使用到」的行**。GM 每次登录 `INSERT` 一条新 token；旧 token 若不再被使用，
  其行**永不删除** ⇒ 表随登录次数单调增长（运维红线：无界增长 + 失效 token 长留）。
* 线上实测（2026-09-30，只读）：`gm_sessions` 存在 1 行 `expires_at = NULL` 的**存量行**
  （0.8.10 上线前签发）。惰性路径只在该 token 被使用时才删它 ⇒ 该行会一直留着。

## 本环改动（2 处插入，锚区与前 23 环零交集）

| # | 锚点 | 改动 |
|---:|---|---|
| C1 | `gm_sessions.expires_at` 幂等加列块（s21 注入）之后 | 新增 `purgeExpiredGmSessions()` 定义 + **启动时**调用一次 |
| C2 | `POST /api/gm/login` 的 `INSERT INTO gm_sessions` 之前 | **每次 GM 登录前**清一次 |

## 为什么「启动 + 登录」两处就够（不新增 setInterval）

`gm_sessions` 的行**只由 GM 登录写入**（全仓唯一 `INSERT INTO gm_sessions` 就是登录端点）。
于是：

* 启动清理 ⇒ 每次发版重启都会把存量失效行清掉。
* 登录清理 ⇒ 表大小在任意时刻 ≤ 「最近 7 天内登录次数 + 1」，**有界**。

两者叠加即封顶，无需再引入定时器（本项目对新增 `setInterval` 有额外审查成本）。

## 判定口径（与 authenticateGM 完全一致，不另立一套）

`expires_at IS NULL`（存量旧行）**或** `expires_at <= now` ⇒ 已失效 ⇒ 删。
`expires_at` 一律由本仓写 `new Date(...).toISOString()`（ISO-8601 UTC，定长）
⇒ **字符串比较等价于时间比较**（同格式下字典序 = 时间序）。

★ 与 s21 ⑥ 的「NULL 视为已过期」策略一致：不改变任何语义，只是把惰性删提前批量做掉。

## 工程约束（本项目已踩过的坑，本环逐条遵守）

1. **回调式 sqlite3** ⇒ `db.run(sql, params, cb)`；`db.run(...).catch(...)` **禁止**。
2. **ESM** ⇒ `require(` **禁止**（门禁断言其计数不增加）。
3. **不新增 `res.status(403)`**（业务拒绝零 403 纪律，`check_srv_087.py` 硬断言计数 == 11）。
4. **不读 PRAGMA**（serialize 无完成屏障，坑 12）；本环只读/写 `gm_sessions` 行，不碰 schema。
5. **注入块里的中文一律转义成 `\uXXXX`**（本模块的 `zh()`），门禁 needle 同样用 `zh()`。
6. **锚点**：每处替换带 `expect=1`，改动前先验证 `count` 等于期望值，否则中止（拒绝静默失败）。
7. ⛔ 不改 `srv/index_v28.ts`（链产物）；⛔ 不改前 23 环补丁；⛔ 不改基座指纹。

## 用法

```
python srv_patch_gmclean_srvadmin.py --src <上一环产物> [--out <本环产物>]  # 就地原子写回 --src（缺省）
python srv_patch_gmclean_srvadmin.py --selftest                            # 只跑门禁，不碰文件
```

幂等：已含 `[v2811srv]` 标记则 SKIP。
"""
import argparse
import hashlib
import os
import re
import shutil
import sys
import time

MARK = '[v2811srv]'
HERE = os.path.dirname(os.path.abspath(__file__))


def md5s(s: str) -> str:
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def die(msg: str):
    print('[FAIL] ' + msg)
    sys.exit(1)


def zh(s: str) -> str:
    """注入块编码纪律：非 ASCII → `\\uXXXX`（与产物既有转义风格一致）。"""
    return ''.join(ch if ord(ch) < 128 else '\\u%04x' % ord(ch) for ch in s)


def apply_one(text: str, tag: str, old: str, new: str, expect: int = 1) -> str:
    n = text.count(old)
    if n != expect:
        die('%s 锚点命中 %d 次（期望 %d）—— 拒绝静默失败' % (tag, n, expect))
    print('  [OK] %-4s 锚点命中 %d 次' % (tag, n))
    return text.replace(old, new, expect)


def _assert_anchor_kept(tag: str, old: str, new: str) -> None:
    """自毁防线：插入式改动必须把锚点原文带进 new。"""
    if old not in new:
        die('%s 自毁防线：new 未包含锚点原文 ⇒ 锚点行会被整段删除（不是插入）。' % tag)
    print('  [OK] %-4s 自毁防线通过（插入式）' % tag)


# ═══════════════════════════════════════════════════════════════════════
# C1：helper 定义 + 启动时清理
# ═══════════════════════════════════════════════════════════════════════
C1_ANCHOR = ("  safeAddColumn('gm_sessions', 'expires_at', "
             "\"ALTER TABLE gm_sessions ADD COLUMN expires_at DATETIME\");\n"
             "});")

C1_BODY = zh("""

// [v2811srv] R-006 GM \u4f1a\u8bdd\u8fc7\u671f\u6e05\u7406\u3002
//   \u75c5\u56e0\uff1agm_sessions \u884c\u53ea\u7531\u767b\u5f55\u5199\u5165\uff0c\u800c 0.8.10 \u53ea\u5728
//   authenticateGM \u91cc\u300c\u7528\u5230\u54ea\u884c\u624d\u60f0\u6027\u5220\u54ea\u884c\u300d
//   \u21d2 \u4e0d\u518d\u88ab\u4f7f\u7528\u7684\u65e7 token \u884c\u6c38\u4e0d\u5220\u3001\u8868\u5355\u8c03\u589e\u957f\u3002
//   \u672c\u73af\u8865\u6279\u91cf\u6e05\u7406\uff1a\u542f\u52a8\u65f6\u4e00\u6b21 + \u6bcf\u6b21\u767b\u5f55\u524d\u4e00\u6b21
//   \uff08gm_sessions \u4ec5\u7531\u767b\u5f55\u5199\u5165 \u21d2 \u4e24\u5904\u5373\u5c01\u9876\u8868\u5927\u5c0f\uff0c\u65e0\u9700\u65b0\u589e\u5b9a\u65f6\u5668\uff09\u3002
//   \u5224\u5b9a\u53e3\u5f84\u4e0e authenticateGM \u4e00\u81f4\uff1aexpires_at \u4e3a NULL\uff08\u5b58\u91cf\u65e7\u884c\uff09
//   \u6216 <= \u5f53\u524d\u65f6\u523b = \u5df2\u5931\u6548\u3002expires_at \u4e00\u5f8b\u5199 ISO-8601 UTC
//   \u5b9a\u957f\u5b57\u7b26\u4e32 \u21d2 \u5b57\u7b26\u4e32\u6bd4\u8f83\u7b49\u4ef7\u4e8e\u65f6\u95f4\u6bd4\u8f83\u3002
function purgeExpiredGmSessions(): void {
  db.run(
    'DELETE FROM gm_sessions WHERE expires_at IS NULL OR expires_at <= ?',
    [new Date().toISOString()],
    (e: any) => { if (e) console.error('[gmclean] purge failed:', e.message); }
  );
}
purgeExpiredGmSessions();
""")

C1_NEW = C1_ANCHOR + C1_BODY

# ═══════════════════════════════════════════════════════════════════════
# C2：登录前清理
# ═══════════════════════════════════════════════════════════════════════
C2_ANCHOR = ("  db.run('INSERT INTO gm_sessions (token, expires_at) VALUES (?, ?)', "
             "[token, new Date(Date.now() + 7 * 86400e3).toISOString()], (err: any) => {")

C2_NEW = zh("  purgeExpiredGmSessions(); // [v2811srv] R-006 \u767b\u5f55\u524d\u6e05\u4e00\u6b21\u5931\u6548\u4f1a\u8bdd\n") + C2_ANCHOR

EDITS = [
    ('C1', C1_ANCHOR, C1_NEW, 1, True),
    ('C2', C2_ANCHOR, C2_NEW, 1, True),
]

DELETE_SQL = "DELETE FROM gm_sessions WHERE expires_at IS NULL OR expires_at <= ?"


def _base_counts(src: str) -> dict:
    return {
        'res.status(403)': src.count('res.status(403)'),
        'require(': src.count('require('),
        'status: 403': src.count('status: 403'),
        'PRAGMA': src.count('PRAGMA'),
    }


def _gates(text: str, base: dict, delta: int, gate) -> None:
    # ── C1 ──
    gate('C1 helper purgeExpiredGmSessions 定义恰 1 处',
         text.count('function purgeExpiredGmSessions(): void {') == 1)
    gate('C1 启动时清理调用恰 1 处',
         text.count('purgeExpiredGmSessions();\nfunction') == 0
         and text.count('\npurgeExpiredGmSessions();\n') == 1)
    gate('C1 DELETE SQL 恰 1 处（NULL 或已过期）',
         text.count(DELETE_SQL) == 1)
    gate('C1 清理失败只记日志、不抛出',
         text.count("if (e) console.error('[gmclean] purge failed:', e.message);") == 1)

    # ── C2 ──
    gate('C2 登录前清理调用恰 1 处',
         text.count('purgeExpiredGmSessions(); // [v2811srv]') == 1)
    gate('C2 purgeExpiredGmSessions 出现恰 3 处（定义 + 启动调用 + 登录调用）',
         text.count('purgeExpiredGmSessions()') == 3)

    # ── 语义不变量（不得误伤既有 GM 会话逻辑）──
    gate('C3 GM 登录 INSERT 一字未动',
         text.count("db.run('INSERT INTO gm_sessions (token, expires_at) VALUES (?, ?)', "
                    "[token, new Date(Date.now() + 7 * 86400e3).toISOString()]") == 1)
    gate('C3 authenticateGM 惰性删仍保留',
         text.count('SELECT token, expires_at FROM gm_sessions WHERE token = ?') == 1
         and text.count("db.run('DELETE FROM gm_sessions WHERE token = ?', [token]);") == 2)
    gate('C3 GM 登出端点未动',
         text.count("app.post('/api/gm/logout', authenticateGM") == 1)
    gate('C3 全仓 INSERT INTO gm_sessions 仍恰 1 处（清理不改写入面）',
         text.count('INSERT INTO gm_sessions') == 1)

    # ── 坑门禁 ──
    gate('G1 [坑] res.status(403) 计数 == 基线（本环不新增 403）',
         text.count('res.status(403)') == base['res.status(403)'],
         '实际 %d（基线 %d）' % (text.count('res.status(403)'), base['res.status(403)']))
    gate('G2 [坑] require( 计数 == 基线（ESM 下未定义）',
         text.count('require(') == base['require('], '实际 %d' % text.count('require('))
    gate('G3 [坑] db.run(...).catch( == 0',
         len(re.findall(r'db\.run\([^\n]*\)\.catch\(', text)) == 0)
    gate('G4 [坑] 未新增 PRAGMA 读取',
         text.count('PRAGMA') == base['PRAGMA'], '实际 %d（基线 %d）' % (text.count('PRAGMA'), base['PRAGMA']))
    gate('G5 [坑] 未新增 setInterval',
         text.count('setInterval(') == 3, '实际 %d' % text.count('setInterval('))

    # ── 幂等 / 规模 ──
    gate('G6 幂等标记就位（重复跑 SKIP）', MARK in text)
    gate('G7 增量字节 ∈ [400, 4000] B', 400 <= delta <= 4000, 'delta = %+d B' % delta)

    # ── 前 23 环关键锚点未丢（只做加法）──
    gate('G8 前环关键锚点未丢',
         text.count('const safeAddColumn = (table: string, col: string, ddl: string) => {') == 1
         and text.count('function settleSaveEconV2') == 1
         and text.count("app.delete('/api/gm/activity/:id', authenticateGM") == 1
         and text.count("app.post('/api/gm/players/:id/mute', authenticateGM") == 1
         and text.count("app.get('/api/snapshots', authenticateToken") == 1
         and text.count("app.get('/api/arena/week', authenticateToken") == 1)
    gate('G9 锚点原文仍在（C1/C2 锚点各 1 处）',
         text.count(C1_ANCHOR) == 1 and text.count(C2_ANCHOR) == 1)


def _apply_all(text: str) -> str:
    for tag, old, new, expect, insertion in EDITS:
        if insertion:
            _assert_anchor_kept(tag, old, new)
        text = apply_one(text, tag, old, new, expect)
    return text


def _run(src: str, label: str) -> int:
    gates = []
    ok = True

    def gate(name, cond, detail=''):
        nonlocal ok
        gates.append((name, bool(cond), detail))
        if not cond:
            ok = False

    before = len(src.encode('utf-8'))
    print('  %s bytes=%d md5=%s' % (label, before, md5s(src)))

    if MARK in src:
        print('  [SKIP] 已含 %s 标记，无需重复打补丁' % MARK)
        return 0

    for tag, old, new, expect, insertion in EDITS:
        if src.count(old) != expect:
            print('  [FAIL] 前置守卫 %s 锚点命中 %d 次（期望 %d）' % (tag, src.count(old), expect))
            return 1
    print('  [OK]   前置守卫：%d 处锚点命中数全部符合期望' % len(EDITS))

    base = _base_counts(src)
    text = _apply_all(src)
    delta = len(text.encode('utf-8')) - before
    _gates(text, base, delta, gate)

    print('\n  --- 门禁 ---')
    for name, c, detail in gates:
        print('  [%s] %s%s' % ('OK' if c else 'FAIL', name, ('  ' + detail) if detail else ''))
    print('\n  自证结果：%s（delta %+d B）' % ('全 PASS' if ok else '存在 FAIL', delta))
    return 0 if ok else 1


def selftest() -> int:
    print('R-006 GM 会话过期清理环 — 自证')
    cand = None
    for p in (os.path.join(HERE, '_chainstage', 's23.snapself.ts'),
              os.path.join(HERE, 'srv', 'index_v28.ts')):
        if os.path.isfile(p):
            cand = p
            break
    if not cand:
        print('  [FAIL] 找不到上一环产物')
        return 1
    src = open(cand, encoding='utf-8').read()
    return _run(src, '上一环产物 %s' % os.path.basename(cand))


def main() -> int:
    ap = argparse.ArgumentParser(description='R-006 GM 会话过期清理环')
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
    print('R-006 GM 会话过期清理环')
    print('  source : %s  bytes=%d md5=%s' % (src, before_bytes, md5s(text)))

    if MARK in text:
        print('  [SKIP] 已包含 %s 标记，无需重复打补丁' % MARK)
        return 0

    for tag, old, new, expect, insertion in EDITS:
        if text.count(old) != expect:
            die('前置守卫失败：%s 锚点命中 %d 次（期望 %d）—— 基线不符' % (tag, text.count(old), expect))
    print('  [OK]   前置守卫：%d 处锚点命中数全部符合期望' % len(EDITS))

    base = _base_counts(text)
    text = _apply_all(text)
    delta = len(text.encode('utf-8')) - before_bytes
    gates = []

    def gate(name, cond, detail=''):
        gates.append((name, bool(cond), detail))

    _gates(text, base, delta, gate)

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
        bak = '%s.bak-v2811srv-%s' % (src, time.strftime('%Y%m%d-%H%M%S'))
        shutil.copy2(src, bak)
        print('\n  [备份] %s' % bak)
        open(src, 'wb').write(text.encode('utf-8'))
        print('  [写出] %s  bytes=%d  md5=%s' % (src, len(text.encode('utf-8')), md5s(text)))

    print('  [PASS] R-006 GM 会话过期清理环落地（delta %+d B）' % delta)
    return 0


if __name__ == '__main__':
    sys.exit(main())
