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
    # ★★ 2026-10-10 修复：$B 不再硬编码。
    #   旧写法把它钉死在 'index-v2949-20261009.js'（0.9.49 版产物），
    #   但 remote_check 里的 $B 指向**本批最新 bundle**（0.9.51 批 = index-v2951-…js）。
    #   结果：不传 --bundle 时，模拟器拿**过期 bundle** 去比对**新一批断言** ⇒ 爆 41 条**假 FAIL**，
    #   上批的人被它骗去查了半天假故障。现在 $B 默认由 resolve_bundle() 从最新 remote_check
    #   脚本里解析（见下），保证断言与 bundle 同批同源；--bundle 仍可覆盖（最高优先级）。
    '$B': None,   # 占位：main() 里用 resolve_bundle() 动态解析后填入
    '$S': 'srv/index_v28.ts',
    # ★★ R-231（2026-10-10）：玩家向日志现在也有 chk 断言了 ⇒ 映射到本地交付产物，
    #   让模拟器**真的**跑这几条（此前它只在远端 check，本地漏测）。
    '$PL': 'CHANGELOG_PLAYER.md',
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


def resolve_bundle(script):
    """从最新 remote_check 脚本里解析 $B 实际指向的 bundle 文件名，映射到本地交付产物。

    为什么从脚本里取：断言和 bundle **必须同批**，从同一份脚本里取才是真正同源。
    脚本里的写法（remote_check_v2851.sh:23-25）：
        BUNDLE_DATE="${YL_BUNDLE_DATE:-20261009}"
        B="index-v2951-${BUNDLE_DATE}.js"          # 裸包名（含 ${VAR} 拼接）
        B="${1:-/opt/yl/www/assets/$B}"            # 再拼远端前缀（取默认分支）
    做法：逐行扫描赋值行，把 ${VAR:-default} / $VAR 展开成已知值（只认本脚本内
    **先定义**的变量），取**最后**一条非空的 B 赋值（= 最终生效值），抽出其中的
    index-v*.js 文件名，拼成 'build/assets/<name>'。

    降级链：
      ① 脚本里解析出的 build/assets/<name> 本地确实存在 ⇒ 用它；
      ② 解析失败 / 本地不存在 ⇒ 在 build/assets/ 下按**版本号数值**取最新 index-v295*.js
         （不能用字符串排序：'v2951' < 'v2959' 会在字符串上错，参考 pick_latest_script）；
      ③ 仍失败 ⇒ 报错退出（不静默用可能是错的文件）。
    返回 (relpath, source)；source ∈ {'script', 'fallback'}。
    """
    src = io.open(script, encoding='utf-8').read().splitlines()

    def expand(val, vars_):
        """展开 ${VAR:-default} / $VAR / ${VAR}；未知变量保留原样。"""
        def repl_braced(m):
            name, default = m.group(1), m.group(2)
            if name in vars_:
                return vars_[name]
            return default if default is not None else m.group(0)

        def repl_plain(m):
            name = m.group(1)
            return vars_.get(name, m.group(0))

        val = re.sub(r'\$\{(\w+)(?::-([^}]*))?\}', repl_braced, val)
        val = re.sub(r'\$(\w+)', repl_plain, val)
        return val

    # 逐行收集赋值：var = 值（去引号），并把 ${VAR:-default} 展开
    assigned = {}
    b_assigns = []   # 按出现顺序记录 B 的每次非空赋值
    for line in src:
        st = line.strip()
        if st.startswith('#'):
            continue
        m = re.match(r'^([A-Za-z_]\w*)=(.*)$', st)
        if not m:
            continue
        name, raw = m.group(1), m.group(2)
        raw = raw.split('#')[0].strip()          # 去行尾注释
        if len(raw) >= 2 and raw[0] in '"\'' and raw[-1] == raw[0]:
            raw = raw[1:-1]                       # 去外层引号
        val = expand(raw, assigned)
        assigned[name] = val
        if name == 'B' and val:
            b_assigns.append(val)

    # 取最后一次 B 赋值，抽出 index-v*.js 文件名（优先 build/assets 全路径）
    if b_assigns:
        last = b_assigns[-1]
        m = re.search(r'(?:^|/)(index-v[\w.-]+\.js)$', last)
        if m:
            rel = 'build/assets/%s' % m.group(1)
            if os.path.isfile(os.path.join(ROOT, rel)):
                return rel, 'script'

    # 降级：按版本号数值取最新 bundle
    hits = glob.glob(os.path.join(ROOT, 'build', 'assets', 'index-v295*.js'))
    hits = [h for h in hits if os.path.isfile(h)]

    def ver(p):
        m = re.search(r'index-v(\d+)-', os.path.basename(p))
        return int(m.group(1)) if m else -1

    if hits:
        return os.path.relpath(max(hits, key=ver), ROOT).replace('\\', '/'), 'fallback'

    # 彻底失败：不静默用可能是错的文件
    print('无法解析 $B：脚本 %s 里找不到 B= 赋值行，且 build/assets/ 下无 index-v295*.js'
          % os.path.relpath(script, ROOT).replace('\\', '/'))
    sys.exit(2)


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
    # $B 默认值：从最新 remote_check 脚本解析（与断言同批同源）；--bundle 优先级最高
    b_source = '命令行覆盖'
    if args.bundle:
        file_map['$B'] = args.bundle
    else:
        rel, b_source_key = resolve_bundle(script)
        file_map['$B'] = rel
        b_source = '自动解析(脚本)' if b_source_key == 'script' else '自动解析(降级:build/assets 最新)'
    if args.srv:
        file_map['$S'] = args.srv

    missing = [k for k, v in file_map.items() if not os.path.isfile(os.path.join(ROOT, v))]
    if missing:
        print('缺少本地产物：%s' % ', '.join('%s -> %s' % (k, file_map[k]) for k in missing))
        print('  先跑：python localtest/dryrun_087.py && python build_v26n.py && python localtest/chain_build.py --srv')
        sys.exit(2)

    print('核对脚本 : %s' % os.path.relpath(script, ROOT).replace('\\', '/'))
    for k, v in sorted(file_map.items()):
        tag = ''
        if k == '$B':
            tag = '   [%s]' % b_source
        print('  %s -> %s%s' % (k, v, tag))
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
