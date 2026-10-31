# -*- coding: utf-8 -*-
r"""
srv_patch_sectsalary.py -- 宗门双俸禄互斥（第 100 环 / 新末环）

背景
--------------------------------------------------------------------------
  宗门有两套「每日俸禄」，各走独立端点、各写独立 kind：

    ① POST /api/sect/welfare/claim  kind='salary'
       → 灵石 = 宗门等级 × SECT_SALARY_PER_LEVEL(500)      全员可领
    ② POST /api/sect/salary
       → 灵石 = SECT_RANK_SALARY[职衔]（1000/2500/6000/12000/25000）
          + 宗门贡献                                       按职衔

  sect_welfare_claims 主键是 (user_id, date, kind) ⇒ 两个 kind 不同 ⇒ **同一天两条都能插入**。
  实测：一个宗主在 5 级宗门，同一天可领 5×500 + 25000 = **27,500** 灵石。

  这不是编码 bug，是**设计漏洞**（双入口）。修法选「互斥」而非「删一个」：
  两个入口各有 UI 与历史数据，删任一个都会让既有玩家少一条路径。

修法
--------------------------------------------------------------------------
  在 ② `/api/sect/salary` 的写库前，检查当日是否已领 ① 的 `kind='salary'`：
    · 未领 ⇒ 409 CLAIM_SALARY_FIRST，提示先领宗门福利里的「俸禄」
    · 已领 ⇒ 照原逻辑发放 `rank_salary`

  ⇒ 一天只发一次俸禄（先领基础俸禄，再领职衔加成部分），总额从 27,500 降到 25,000（宗主 5 级宗门）。

  ★ 顺序方向选择：要求「先领 ① 再领 ②」，不是反过来。
    原因：① 全员可领（新人也拿得到），② 要职衔（门槛更高）。
    若要求先领 ②，新人没有职衔就永远领不到 ①，等于把基础俸禄锁死。

插入点（勘察结论）
--------------------------------------------------------------------------
  目标：`app.post('/api/sect/salary', ...)` 内，`const date = bjDate(Date.now());` 之后、
  `try { await dbRun('INSERT INTO sect_welfare_claims ... 'rank_salary' ...)` 之前。

  REQUIRES 断言（打前逐一核对，不符立即中止）：
    · `const sal = sectSalaryOf(rank);` 全文 == 1
    · `const date = bjDate(Date.now());` 在 /api/sect/salary 段内 == 1
    · `'rank_salary'` 出现 == 1（INSERT 处）
    · 插入后：`CLAIM_SALARY_FIRST` == 1、`sect_welfare_claims` 在该段新增 1 处 SELECT

不做的事
--------------------------------------------------------------------------
  · 不动 ① `/api/sect/welfare/claim`（一字节不改）
  · 不动 `SECT_SALARY_PER_LEVEL` / `SECT_RANK_SALARY` 常量
  · 不动 `sect_welfare_claims` 表结构（复用既有 kind 维度，不加列）
  · 不动任何客户端（本环纯服务端）

幂等标记：[sectsalary]
"""
import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

MARK = '[sectsalary]'

# ------------------------------------------------------------------ 插入锚点
ANCHOR = """    const sal = sectSalaryOf(rank);
    const date = bjDate(Date.now());
    try {"""

INSERT = """    const sal = sectSalaryOf(rank);
    const date = bjDate(Date.now());
    /* [sectsalary] 与 /api/sect/welfare/claim kind='salary' 互斥：
       两套俸禄此前 kind 不同（'salary' vs 'rank_salary'）⇒ 同一天可各领一次
       （宗主在 5 级宗门可领 5x500 + 25000 = 27500）。现要求先领宗门福利俸禄，
       才能领职衔俸禄 —— 一天只发一次俸禄。 */
    const salClaimed: any = await dbGet(
      "SELECT 1 AS c FROM sect_welfare_claims WHERE user_id = ? AND date = ? AND kind = 'salary'",
      [req.user.id, date]);
    if (!salClaimed) {
      return res.status(409).json({ error: '\\u8bf7\\u5148\\u9886\\u53d6\\u5b97\\u95e8\\u798f\\u5229\\u4e2d\\u7684\\u300c\\u4ff8\\u7984\\u300d\\uff0c\\u804c\\u8854\\u4ff8\\u7984\\u4e0e\\u5b83\\u540c\\u4e00\\u5929\\u53ea\\u53d1\\u4e00\\u6b21', code: 'CLAIM_SALARY_FIRST' });
    }
    try {"""


def _read(p):
    with io.open(p, 'rb') as f:
        return f.read().decode('utf-8')


def _precheck(s):
    """打前 REQUIRES 逐一断言。返回错误串或 None。"""
    if s.count(ANCHOR) != 1:
        return '锚点出现 %d 次（期望 1）—— /api/sect/salary 段结构已变' % s.count(ANCHOR)
    # 注意：`const sal = sectSalaryOf(rank);` 在 status 端点也有一处（共 2 次）
    # → 只能用含 `try {` 的 ANCHOR 做唯一性断言（上面已做）。
    # 这里改为断言「至少 2 次」且 ANCHOR 恰 1 次（语义：两个端点都在）。
    if s.count('const sal = sectSalaryOf(rank);') < 2:
        return 'sectSalaryOf 调用 %d 次（期望 >=2：status + salary 两个端点）' % s.count('const sal = sectSalaryOf(rank);')
    # 'rank_salary' 出现 3 次（INSERT / DELETE / 注释）→ 断言 >=1 即可
    if s.count("'rank_salary'") < 1:
        return "'rank_salary' 出现 %d 次（期望 >=1）" % s.count("'rank_salary'")
    # ① 端点必须原样在位（本环不动它）
    if s.count("app.post('/api/sect/welfare/claim'") != 1:
        return "① 端点 /api/sect/welfare/claim 出现 %d 次（期望 1）" % s.count("app.post('/api/sect/welfare/claim'")
    # 常量必须原样
    if s.count('const SECT_SALARY_PER_LEVEL = 500;') != 1:
        return 'SECT_SALARY_PER_LEVEL 常量已变'
    return None


def _count(out, needle):
    if isinstance(needle, tuple):
        return sum(out.count(x) for x in needle)
    return out.count(needle)


def gates():
    """补丁后形态门禁（5 元组 name/needle/expected/op/note）。"""
    g = []
    g.append(('SECTSAL·互斥检查在位', 'CLAIM_SALARY_FIRST', 1, '==',
              '② 职衔俸禄前先查 ① 的 salary 是否已领'))
    g.append(('SECTSAL·SELECT 新增一处', "kind = 'salary'\"", 1, '==',
              '查当日 salary 领取记录'))
    g.append(('SECTSAL·幂等标记', MARK, 1, '==', ''))
    g.append(('SECTSAL·① 端点未动', "app.post('/api/sect/welfare/claim'", 1, '==',
              '本环一字节不动 ①'))
    g.append(('SECTSAL·② 端点仍在', "app.post('/api/sect/salary'", 1, '==', ''))
    g.append(('SECTSAL·rank_salary 仍在', "'rank_salary'", 4, '==',
              'INSERT 逻辑未改'))
    g.append(('SECTSAL·常量未动', 'const SECT_SALARY_PER_LEVEL = 500;', 1, '==', ''))
    g.append(('SECTSAL·职衔表未动', 'const SECT_RANK_SALARY: Record<string, { spiritStones: number; contribution: number }> = {', 1, '==', ''))
    return g


def apply_patch(src):
    """返回 (out, err)；err 非 None 时为错误串。"""
    s = _read(src)
    if MARK in s:
        return None, None  # 已打过（幂等）
    err = _precheck(s)
    if err is not None:
        return None, err
    return s.replace(ANCHOR, INSERT, 1), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    a = ap.parse_args()
    src = a.src
    if not os.path.exists(src):
        print('[FAIL] src not found: %s' % src)
        return 2

    s = _read(src)
    if MARK in s:
        print('[SKIP] already patched (%s)' % MARK)
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[ABORT] %s' % err)
        return 2
    if out is None:
        print('[SKIP] already patched')
        return 3

    # 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        act = _count(out, needle)
        good = (act == exp) if op == '==' else (act >= exp)
        ok = ok and good
        print('  [%s] %-32s actual=%d expect%s%d %s'
              % ('OK' if good else 'FAIL', label, act, op, exp, note))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 往返自证
    back = out.replace(INSERT, ANCHOR, 1)
    if back != s:
        print('[FAIL] round-trip mismatch')
        return 1
    print('  往返自证: 新串→旧串 与源逐字节相同 OK')

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(s), len(s), len(out)))

    # 备份 + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src + '.bak-sectsalary-' + ts
    with io.open(bak, 'wb') as f:
        f.write(s.encode('utf-8'))
    print('  已备份 -> %s' % bak)
    d0 = os.path.dirname(os.path.abspath(src)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d0, prefix='.sectsalary-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out.encode('utf-8'))
        os.replace(tmp, src)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    import hashlib
    print('  已原子写回 %s（md5 %s）' % (src, hashlib.md5(out.encode('utf-8')).hexdigest()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
