# -*- coding: utf-8 -*-
r"""srv_patch_gmmute_srvadmin.py — R-008 GM 禁言状态回显环（0.8.11 服务端 / srv-admin 独占）

只做一件事：给 `GET /api/gm/players` 的响应补一个 `mutedUntil` 字段，
让 GM 后台能**看见**某玩家是否被禁言、禁到何时。

## 缺口（为什么需要本环）

0.8.10（链第 21 环 s21 ⑧）已经把「禁言」的服务端能力做齐：
`POST /api/gm/players/:id/mute`（写 `users.muted_until`）+ `POST /api/messages` 拦截 + `GET /api/me/mute`。

但 **`GET /api/gm/players` 的响应不含 `muted_until`**（只 select 了 `u.banned`）⇒ GM 后台
**看不到禁言状态**：列表无徽标、详情页无从判断当前是否禁言，「解除禁言」只能盲点。
`GET /api/me/mute` 是 `authenticateToken`（**玩家自己的** token），GM 无法用它查他人 ⇒
必须由 GM 列表端点回显。

## 本环改动（2 处插入，锚区与前 24 环零交集）

| # | 锚点 | 改动 |
|---:|---|---|
| M1 | `GET /api/gm/players` 的 `listSql` SELECT 列表（`u.banned,` 之后） | 加选 `u.muted_until` |
| M2 | 同端点的 `players.map` 对象（`banned: !!r.banned,` 之后） | 加 `mutedUntil: r.muted_until \|\| null,` |

## 为什么安全

* `users.muted_until` 列由**前环 s21 ⑧** 的 `safeAddColumn('users','muted_until', ...)` 幂等建立，
  本环在其之后运行 ⇒ 列必存在。本环门禁硬断言该迁移仍在（顺序守卫，跑错位置会当场 FAIL）。
* 纯**追加字段**，既有字段与语义一字不动 ⇒ 向后兼容，前端旧代码不受影响。
* 不新增端点、不新增写路径、不读 PRAGMA、不加 `res.status(403)`。

## 工程约束（本项目已踩过的坑，本环逐条遵守）

1. **回调式 sqlite3** ⇒ 本环不改任何 `db.run` 调用（只改 SELECT 文本与 map 字面量）。
2. **ESM** ⇒ `require(` **禁止**（门禁断言其计数不增加）。
3. **不新增 `res.status(403)`**（业务拒绝零 403 纪律，`check_srv_087.py` 硬断言计数 == 11）。
4. **不读 PRAGMA**（serialize 无完成屏障，坑 12）。
5. **注入块里的中文一律转义成 `\uXXXX`**（本模块的 `zh()`）。
6. **锚点**：每处替换带 `expect=1`，改动前先验证 `count` 等于期望值，否则中止（拒绝静默失败）。
7. ⛔ 不改 `srv/index_v28.ts`（链产物）；⛔ 不改前 24 环补丁；⛔ 不改基座指纹。

## 用法

```
python srv_patch_gmmute_srvadmin.py --src <上一环产物> [--out <本环产物>]  # 就地原子写回 --src（缺省）
python srv_patch_gmmute_srvadmin.py --selftest                            # 只跑门禁，不碰文件
```

幂等：已含 `[v2811srvm]` 标记则 SKIP。
"""
import argparse
import hashlib
import os
import re
import shutil
import sys
import time

MARK = '[v2811srvm]'
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
# M1：SELECT 列表加选 u.muted_until（纯插入：在 gm_revision 行前插一行新列）
#   ★ 该行落在 `listSql` 模板字符串**内部** ⇒ 绝不能带 `//` 或 `--` 注释
#     （`//` 会被当 SQL 文本 ⇒ SQLite 语法错 ⇒ 端点 500；`--` 虽合法但不必要）。
#     追溯标记由 M2 的 JS 注释承担。
# ═══════════════════════════════════════════════════════════════════════
M1_OLD = "           s.gm_revision, s.save_data,\n"

M1_NEW = ("           u.muted_until,\n"
          "           s.gm_revision, s.save_data,\n")

# ═══════════════════════════════════════════════════════════════════════
# M2：map 对象加 mutedUntil
# ═══════════════════════════════════════════════════════════════════════
M2_OLD = "          banned: !!r.banned,\n"

M2_NEW = ("          banned: !!r.banned,\n"
          "          mutedUntil: r.muted_until || null, // [v2811srvm] R-008\uff08ISO \u6216 null\uff09\n")

EDITS = [
    ('M1', M1_OLD, M1_NEW, 1, True),
    ('M2', M2_OLD, M2_NEW, 1, True),
]


def _base_counts(src: str) -> dict:
    return {
        'res.status(403)': src.count('res.status(403)'),
        'require(': src.count('require('),
        'status: 403': src.count('status: 403'),
        'PRAGMA': src.count('PRAGMA'),
        'mutedUntil': src.count('mutedUntil'),
    }


def _gates(text: str, base: dict, delta: int, gate) -> None:
    # ── M1 ──
    gate('M1 GM 玩家列表 SELECT 加选 u.muted_until 恰 1 处',
         text.count('           u.muted_until,\n') == 1)
    gate('M1 u.muted_until 全仓恰 1 处（只此一处读取）',
         text.count('u.muted_until') == 1)
    gate('M1 SELECT 仍在 GM 玩家列表端点内（banned 行紧随其后）',
         text.count("SELECT u.id, u.username, u.created_at, u.banned,\n") == 1)
    gate('M1 [坑] SQL 模板串内无 `//` 注释（否则 SQLite 语法错 → 端点 500）',
         'u.muted_until, //' not in text)
    # ── M2 ──
    gate('M2 map 输出 mutedUntil 恰 1 处',
         text.count('mutedUntil: r.muted_until || null,') == 1)
    gate('M2 mutedUntil 出现数 == 基线 + 1（本环只加 GM 列表这一处）',
         text.count('mutedUntil') == base['mutedUntil'] + 1,
         '实际 %d（基线 %d）' % (text.count('mutedUntil'), base['mutedUntil']))
    gate('M2 /api/me/mute 的 mutedUntil 字段名未动（前端契约稳定）',
         text.count('res.json({ muted: active, mutedUntil: active ? new Date(t).toISOString() : null });') == 1)

    # ── 语义不变量（不得误伤既有 GM 列表/禁言逻辑）──
    gate('M3 GM 玩家列表端点结构未动',
         text.count("app.get('/api/gm/players', authenticateGM") == 1
         and text.count('const listSql = `') == 1
         and text.count('const countSql = `SELECT COUNT(*) AS c FROM users u ${where}`;') == 1)
    gate('M3 既有 banned 字段仍在（未替换）',
         text.count('banned: !!r.banned,') == 1
         and text.count("if (bannedFilter === '1') { wheres.push('u.banned = 1'); }") == 1)
    gate('M3 禁言写端点一字未动',
         text.count("app.post('/api/gm/players/:id/mute', authenticateGM") == 1
         and text.count("UPDATE users SET muted_until = ? WHERE id = ?") == 1)
    gate('M3 [顺序守卫] users.muted_until 迁移仍在（本环必须在 s21 之后）',
         text.count("safeAddColumn('users', 'muted_until',") == 1)

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
    gate('G7 增量字节 ∈ [80, 1200] B', 80 <= delta <= 1200, 'delta = %+d B' % delta)

    # ── 前 24 环关键锚点未丢（只做加法）──
    gate('G8 前环关键锚点未丢',
         text.count('function purgeExpiredGmSessions(): void {') == 1
         and text.count('const safeAddColumn = (table: string, col: string, ddl: string) => {') == 1
         and text.count("app.delete('/api/gm/activity/:id', authenticateGM") == 1
         and text.count("app.get('/api/me/mute', authenticateToken") == 1
         and text.count("app.get('/api/snapshots', authenticateToken") == 1
         and text.count("app.get('/api/arena/week', authenticateToken") == 1)
    gate('G9 锚点原文仍在（M1/M2 锚点各 1 处）',
         text.count(M1_OLD) == 1 and text.count(M2_OLD) == 1)


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
    print('R-008 GM 禁言状态回显环 — 自证')
    cand = None
    for p in (os.path.join(HERE, '_chainstage_srvadmin', 's24.gmclean.ts'),
              os.path.join(HERE, '_chainstage', 's23.snapself.ts'),
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
    ap = argparse.ArgumentParser(description='R-008 GM 禁言状态回显环')
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
    print('R-008 GM 禁言状态回显环')
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
        bak = '%s.bak-v2811srvm-%s' % (src, time.strftime('%Y%m%d-%H%M%S'))
        shutil.copy2(src, bak)
        print('\n  [备份] %s' % bak)
        open(src, 'wb').write(text.encode('utf-8'))
        print('  [写出] %s  bytes=%d  md5=%s' % (src, len(text.encode('utf-8')), md5s(text)))

    print('  [PASS] R-008 GM 禁言状态回显环落地（delta %+d B）' % delta)
    return 0


if __name__ == '__main__':
    sys.exit(main())
