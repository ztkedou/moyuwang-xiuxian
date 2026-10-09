#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""sim_remote_check.py -- 在**本地产物**上预演 deploy_v28/remote_check_v*.sh 的 chk 断言。

为什么需要它（0.8.10 新增）：
  远端定点核对脚本（remote_check_v*.sh）是**上线后**才跑的，一旦某条 needle 的预期计数
  写错（或本批某任务合法改写了某条回归串），你要等到**部署之后**才发现 FAIL —— 那时
  线上已经切包，回滚成本高。
  本工具把 remote_check 里的 `chk <file> <needle> <label> <ge|eq> <n>` 全部抽出来，
  在**本地交付产物**上按同样的语义（grep -o -F | wc -l ≡ str.count）跑一遍，
  部署前就能拿到 FAIL 清单。**部署前置门禁，不是可选步骤。**

用法：
  python localtest/sim_remote_check.py                         # 自动挑最新 remote_check_v*.sh
  python localtest/sim_remote_check.py --script deploy_v28/remote_check_v2810.sh
  python localtest/sim_remote_check.py --bundle build/assets/index-v2913-20261002.js \
                                       --srv srv/index_v28.ts

退出码：0 = 全绿（含 SKIP）；1 = 有 FAIL 或解析失败。

★ 只覆盖 `chk`（文件内容断言）。`probe`（HTTP 冒烟）、index.html/CHANGELOG 断言、
  服务健康、线上库核对属**远端专有**，本地一律 SKIP —— 那些必须真上线后跑。
"""
from __future__ import print_function

import argparse
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# remote_check 里的 shell 变量 → 本地交付产物（相对仓库根）
FILE_MAP = {
    '$B': 'build/assets/index-v2945-20261009.js',
    '$S': 'srv/index_v28.ts',
}
# 远端专有（本地无对应物）：一律 SKIP
SKIP_KEYS = {'$IH', '$CL'}


def shell_split(line):
    """极简 shell 词法分析：只处理单引号 / 双引号 / 反斜杠，够用于 chk 行。"""
    toks, cur, i, n = [], '', 0, len(line)
    mode = None
    while i < n:
        c = line[i]
        if mode is None:
            if c in ' \t':
                if cur != '':
                    toks.append(cur)
                    cur = ''
                i += 1
                continue
            if c == "'":
                mode = 'sq'
                i += 1
                continue
            if c == '"':
                mode = 'dq'
                i += 1
                continue
            cur += c
            i += 1
            continue
        if mode == 'sq':
            if c == "'":
                mode = None
                i += 1
                continue
            cur += c
            i += 1
            continue
        # dq
        if c == '"':
            mode = None
            i += 1
            continue
        if c == '\\' and i + 1 < n and line[i + 1] in '"\\$`':
            cur += line[i + 1]
            i += 2
            continue
        cur += c
        i += 1
    if cur != '':
        toks.append(cur)
    return toks


def pick_latest_script():
    """取版本号**数值**最大的一份。
    ★ 坑：不能用字符串排序 —— 'v2810' < 'v289'（'1' < '9'），会挑到旧版。"""
    hits = glob.glob(os.path.join(ROOT, 'deploy_v28', 'remote_check_v*.sh'))
    if not hits:
        print('找不到 deploy_v28/remote_check_v*.sh')
        sys.exit(2)

    def ver(p):
        m = re.search(r'remote_check_v(\d+)\.sh$', os.path.basename(p))
        return int(m.group(1)) if m else -1

    return max(hits, key=ver)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--script', default=None, help='remote_check_v*.sh 路径（默认取版本号最大的一份）')
    ap.add_argument('--bundle', default=None, help='覆盖 $B 指向的本地 bundle')
    ap.add_argument('--srv', default=None, help='覆盖 $S 指向的本地 srv/index_v28.ts')
    ap.add_argument('--quiet', action='store_true', help='只打印汇总与 FAIL')
    args = ap.parse_args()

    script = args.script or pick_latest_script()
    if not os.path.isabs(script):
        script = os.path.join(ROOT, script)
    if not os.path.isfile(script):
        print('找不到核对脚本：%s' % script)
        sys.exit(2)

    file_map = dict(FILE_MAP)
    if args.bundle:
        file_map['$B'] = args.bundle
    if args.srv:
        file_map['$S'] = args.srv

    missing = [k for k, v in file_map.items() if not os.path.isfile(os.path.join(ROOT, v))]
    if missing:
        print('缺少本地产物：%s' % ', '.join('%s -> %s' % (k, file_map[k]) for k in missing))
        print('  先跑：python localtest/dryrun_087.py && python build_v26n.py && python localtest/chain_build.py --srv')
        sys.exit(2)

    print('核对脚本 : %s' % os.path.relpath(script, ROOT).replace('\\', '/'))
    for k, v in sorted(file_map.items()):
        print('  %s -> %s' % (k, v))
    print('')

    cache = {}

    def load(rel):
        if rel not in cache:
            cache[rel] = io.open(os.path.join(ROOT, rel), encoding='utf-8', newline='').read()
        return cache[rel]

    src = io.open(script, encoding='utf-8').read().splitlines()
    fails, oks, skipped = [], 0, 0
    for ln, line in enumerate(src, 1):
        st = line.strip()
        if not st.startswith('chk '):
            continue
        toks = shell_split(st[4:])
        if len(toks) < 5:
            fails.append((ln, 'PARSE-ERROR 无法解析为 5 个参数', line.strip()))
            continue
        fkey, needle, label, cmp_, exp = toks[0], toks[1], toks[2], toks[3], toks[4]
        if fkey in SKIP_KEYS:
            skipped += 1
            continue
        rel = file_map.get(fkey)
        if rel is None:
            fails.append((ln, 'UNKNOWN-FILE %s' % fkey, line.strip()))
            continue
        n = load(rel).count(needle)
        try:
            e = int(exp)
        except ValueError:
            fails.append((ln, 'BAD-EXPECT %r' % exp, line.strip()))
            continue
        ok = (n == e) if cmp_ == 'eq' else (n >= e)
        if ok:
            oks += 1
            if not args.quiet:
                print('  [OK  ] %-52s x%-3d expect %s %d' % (label[:52], n, cmp_, e))
        else:
            fails.append((ln, '%s got=%d expect %s %d | %s | needle=%s'
                          % (fkey, n, cmp_, e, label, needle[:90]), line.strip()))

    print('')
    print('本地预演结果：OK=%d  SKIP(远端专有)=%d  FAIL=%d' % (oks, skipped, len(fails)))
    for ln, msg, raw in fails:
        print('  [FAIL] L%-5d %s' % (ln, msg))
        print('         %s' % raw[:160])
    if fails:
        print('')
        print('★ 修法：① 若预期值写错 → 改 remote_check 的 expect；')
        print('        ② 若本批某任务**合法**改写了该串 → 按实际产物更新预期值，并记入 DEPLOY_LOG_*.md，不得静默删断言。')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
