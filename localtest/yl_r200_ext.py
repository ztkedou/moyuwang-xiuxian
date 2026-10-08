# -*- coding: utf-8 -*-
r"""
yl_r200_ext.py — R-200：去掉进食行「今日首次免费」后缀（standalone 纯客户端）

★ 用户原话（逐字，唯一依据）：
  「R-167「当日首次免费」这个去掉，前面有专门的免费档了」

★ 背景：R-198（0.9.35 已上线）已在「培养」区加了**专门的免费进食**（+100 喂食度 / 每日 3 次 /
  冷却 30 分钟）。R-167 那套「每日第一次喂养不花灵石」成为冗余的第二套免费机制 ⇒ 服务端整条移除，
  客户端把进食行上那句「· 今日首次免费」后缀一并去掉（否则 UI 仍宣称有首免，与服务端不一致）。

★ 本环边界（严格）：
  · 只删「进食行」文案后缀 + 随之变为**未使用**的 `fq` 变量。
  · 不动「玩法说明①」（`\u2460 进食：三档灵食…`，其内**未**提首免/免费 ⇒ 本环一字不改，
    避免与 R-198 钉死说明① 的 `r198free` 门禁冲突）。
  · 不动 R-198 的「免费玩法」说明② / 免费进食按钮 / 其它任何 `yl_r*_ext.py` / `patches/*` / 台账。

==============================================================================
零、目标产物与取证口径
==============================================================================
  目标：build/assets/index-v2935-20261008.js（0.9.35 交付产物 = 所有 standalone 补丁套用后的形态；
        md5 见交付报告）。本环全部结论均对该文件**字符级实测**（Python 解码 utf-8 后按 char 计偏移）。

==============================================================================
一、进食行「今日首次免费」后缀（bundle 实抽，纯 ASCII 转义形态）
==============================================================================
  YlxwR18FeedRow（函数签名 count==1）内：
    var ft = c.feedTiers || {};
    var fq = (t && t.feedQuota) || {};          ← R-189 消费 feedQuota 引入（本环将删，见 §二）
    var keys = ["common", "fine", "immortal"];
    ...
    children: (tier.name || names[k]) + "\uff08" + YlxwNum(tier.cost) + " \u7075\u77f3 \u00b7
              \u5582\u98df\u5ea6 +" + YlxwNum(tier.hunger) + "\uff09"
              + (fq.free ? " \u00b7 \u4eca\u65e5\u9996\u6b21\u514d\u8d39" : ""),   ← 本环删此段
  · 转义形态 `\u4eca\u65e5\u9996\u6b21\u514d\u8d39`（「今日首次免费」）在整库 count==1（本处）。
  · 删除后 `+ ""` 残渣一并消失（整段 `+ (fq.free ? … : "")` 删净，分隔符 ` \u00b7 ` 随之带走）。

==============================================================================
二、`fq` 是删是留（判定依据）
==============================================================================
  · 整库 standalone `fq`（词边界）count==2：`var fq = (t && t.feedQuota) || {};` 定义 1 + `fq.free` 使用 1。
  · 使用点**仅** `fq.free`（即被删的后缀判定）⇒ 去掉文案后 `fq` 成为未使用变量 ⇒ **删**。
  · 旁证：整库 `feedQuota` count==1（**仅** 该定义处消费）⇒ 删 `fq` 后 `feedQuota` 亦归零，
    客户端不再消费 R-167 的 `feedQuota` 字段（服务端回显保留，见服务端环 R-200）。

==============================================================================
三、玩法说明① 复核（不动）
==============================================================================
  说明①：`\u2460 \u8fdb\u98df\uff1a\u4e09\u6863\u7075\u98df\u63d0\u5347\u5582\u98df\u5ea6……`
    ⇒ 只讲三档灵食的单价/喂食度/等级换算，**未**提「首免 / 免费」⇒ 本环一字不改。
  说明②：`\u2461 \u514d\u8d39\u73a9\u6cd5\uff1a\u514d\u8d39\u8fdb\u98df +100 …`（R-198）⇒ 本环一字不改。

==============================================================================
四、锚点（对目标产物字符级实测，替换锚点全为纯 ASCII 转义）
==============================================================================
  · C1 删 `var fq = (t && t.feedQuota) || {};`（+ 落幂等标记 /*[r200ui]*/）：锚点纯 ASCII，count==1。
  · C2 删进食行 `+ (fq.free ? " \u00b7 \u4eca\u65e5\u9996\u6b21\u514d\u8d39" : "")` 后缀：
    以**整条 children 表达式**为锚点（纯 ASCII 转义），count==1。
  · 冻结针脚（对**输入**校验，count==1，纯 ASCII）：YlxwR18FeedRow 签名 / `var ft` / 其余 R18 组件签名 /
    玩法说明① / 玩法说明②（R-198）/ `/*[r198free]*/` / `/*[r189ui]*/`。

==============================================================================
五、契约（照 localtest/yl_r199_ext.py）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check）。
  · 二进制读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 <src>.bak-r200-<时刻>。
  · 幂等：产物已含标记 `/*[r200ui]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；另含 standalone `fq` 正则校验。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r200ui]*/'

# --------------------------------------------------------------------------- 替换项
# ★ 形态约定：bundle 妖灵页签区域中文为**字面 `\uXXXX`**（六字符）⇒ 本 .py 源码保持纯 ASCII，
#   用 `\\uXXXX`（双反斜杠）写出，运行期字符串即 `\uXXXX`。

# ---- C1 YlxwR18FeedRow：删未使用的 fq 变量 + 落幂等标记 ----
C1_OLD = (
    '  var ft = c.feedTiers || {};\n'
    '  var fq = (t && t.feedQuota) || {};\n'
    '  var keys = ["common", "fine", "immortal"];'
)
C1_NEW = (
    '  var ft = c.feedTiers || {};' + IDEMPOTENT_MARK + '\n'
    '  var keys = ["common", "fine", "immortal"];'
)

# ---- C2 YlxwR18FeedRow：删进食行「· 今日首次免费」后缀（连分隔符与三目整段删净）----
C2_OLD = (
    'children: (tier.name || names[k]) + "\\uff08" + YlxwNum(tier.cost) + " \\u7075\\u77f3 \\u00b7 '
    '\\u5582\\u98df\\u5ea6 +" + YlxwNum(tier.hunger) + "\\uff09" + (fq.free ? " \\u00b7 '
    '\\u4eca\\u65e5\\u9996\\u6b21\\u514d\\u8d39" : ""),'
)
C2_NEW = (
    'children: (tier.name || names[k]) + "\\uff08" + YlxwNum(tier.cost) + " \\u7075\\u77f3 \\u00b7 '
    '\\u5582\\u98df\\u5ea6 +" + YlxwNum(tier.hunger) + "\\uff09",'
)

REPLACEMENTS = [
    ('r200-C1 删未使用 fq 变量 + 幂等标记', C1_OLD, C1_NEW),
    ('r200-C2 删进食行「今日首次免费」后缀', C2_OLD, C2_NEW),
]

# 冻结针脚：本环不动的稳定形态（对**输入**校验，全 ASCII，均 count==1）
FREEZE = [
    # —— 结构：进食行 / 同区组件签名未动 ——
    ('function YlxwR18FeedRow(', 1),
    ('  var ft = c.feedTiers || {};', 1),
    ('function YlxwR18Card(', 1),
    ('function YlxwR18PlayRows(', 1),
    ('function YlxwR18ExpedRow(', 1),
    ('function YlxwR18MiscRow(', 1),
    # —— 玩法说明①（未提首免/免费 ⇒ 一字不改）——
    ('\\u2460 \\u8fdb\\u98df\\uff1a\\u4e09\\u6863\\u7075\\u98df', 1),
    # —— 玩法说明②（R-198 免费玩法 ⇒ 一字不改）——
    ('\\u2461 \\u514d\\u8d39\\u73a9\\u6cd5', 1),
    # —— 既有幂等标记（R-198 / R-189）——证明未误伤既有环
    ('/*[r198free]*/', 1),
    ('/*[r189ui]*/', 1),
]


def _standalone_fq(text):
    """standalone 标识符 fq 的出现次数（词边界；不误计 fqxxx / xxxfq 等子串）。"""
    return len(re.findall(r'(?<![A-Za-z0-9_$])fq(?![A-Za-z0-9_$])', text))


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R200·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r200ui] 恰 1 处'),
        # —— 后缀删净 ——
        ('R200·「今日首次免费」转义串清零', '\\u4eca\\u65e5\\u9996\\u6b21\\u514d\\u8d39', 0, '==', '整库 0 处'),
        ('R200·旧 children（含后缀）清零', C2_OLD, 0, '==', '旧表达式 0 处'),
        ('R200·新 children（无后缀）在位', C2_NEW, 1, '==', '新表达式恰 1 处'),
        ('R200·无 `+ ""` 残渣', '\\uff09" + "",', 0, '==', '未留空串拼接'),
        # —— fq / feedQuota 清零 ——
        ('R200·fq.free 清零', 'fq.free', 0, '==', '判定已删'),
        ('R200·var fq 定义清零', 'var fq = (t && t.feedQuota) || {};', 0, '==', '未使用变量已删'),
        ('R200·feedQuota 清零', 'feedQuota', 0, '==', '客户端不再消费'),
        ('R200·新 ft 行含标记', '  var ft = c.feedTiers || {};' + IDEMPOTENT_MARK, 1, '==', '标记落此'),
        # —— 未动：说明① / 说明② / 组件签名 ——
        ('R200·冻结·玩法说明① 未动', '\\u2460 \\u8fdb\\u98df\\uff1a\\u4e09\\u6863\\u7075\\u98df', 1, '==', '未提首免/免费，一字不改'),
        ('R200·冻结·玩法说明②（R-198）未动', '\\u2461 \\u514d\\u8d39\\u73a9\\u6cd5', 1, '==', 'R-198 免费玩法保持'),
        ('R200·冻结·YlxwR18FeedRow 签名', 'function YlxwR18FeedRow(', 1, '==', '未动'),
        ('R200·冻结·R-198 标记', '/*[r198free]*/', 1, '==', '未误伤'),
        ('R200·冻结·R-189 标记', '/*[r189ui]*/', 1, '==', '未误伤'),
    ]
    for needle, cnt in FREEZE:
        g.append(('冻结 ' + needle[:30], needle, cnt, '==', '冻结既有形态'))
    return g


# --------------------------------------------------------------------------- 主流程

def _read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


def _write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(text.encode('utf-8'))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _is_patched(s):
    return IDEMPOTENT_MARK in s


def _precheck(s):
    """返回 None=可打；否则返回错误串。对**原件** s 校验锚点与冻结针脚。"""
    if _is_patched(s):
        return None  # 幂等，交由 main 判 rc=3
    for name, old, new in REPLACEMENTS:
        if s.count(old) != 1:
            return '锚点 %s 出现 %d 次（期望 1）' % (name, s.count(old))
    for needle, cnt in FREEZE:
        if s.count(needle) != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, s.count(needle), cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时 out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPLACEMENTS:
        out = out.replace(old, new, 1)
    return out, None


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        c = out.count(needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    nfq = _standalone_fq(out)
    if nfq != 0:
        return 'GATE FAIL standalone fq: count=%d expect 0' % nfq
    return None


def _roundtrip_ok(out, s0):
    """反向还原：把每个 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
        r = subprocess.run([node, '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _probe(patched_text):
    """node 真跑：实抽补丁后 YlxwR18FeedRow 的进食按钮 children 表达式，确认后缀与 fq 均已消失。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。
    """
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    if patched_text.count('\\u4eca\\u65e5\\u9996\\u6b21\\u514d\\u8d39') != 0:
        return False, '后缀转义串未清零'
    if _standalone_fq(patched_text) != 0:
        return False, 'standalone fq 未清零（%d）' % _standalone_fq(patched_text)
    # 实抽新 children 表达式并 node 复算（模拟三档渲染，确认渲染结果不再含「今日首次免费」）
    m = re.search(r'children: (\(tier\.name \|\| names\[k\]\)[^,]*),', patched_text)
    if not m:
        return False, '未能实抽 children 表达式'
    expr = m.group(1)
    js = (
        'var names={common:"A",fine:"B",immortal:"C"};\n'
        'function YlxwNum(x){return String(x);}\n'
        'var out=[];\n'
        '["common","fine","immortal"].forEach(function(k){\n'
        '  var tier={name:"",cost:3000,hunger:30};\n'
        '  out.push(' + expr + ');\n'
        '});\n'
        'console.log(out.join("|"));\n'
    )
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:300]
        rendered = r.stdout.decode('utf-8', 'replace').strip()
        # 渲染结果（已把 \uXXXX 还原为真中文）不得再含「今日首次免费」
        if '\u4eca\u65e5\u9996\u6b21\u514d\u8d39' in rendered:
            return False, '渲染结果仍含「今日首次免费」：' + rendered
        return True, rendered
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r200] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r200] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r200] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r200] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r200] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r200] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _probe(out)
    if ok is False:
        print('[r200] SELFTEST FAIL probe: ' + pmsg)
        return 1
    print('[r200] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print('[r200] 探针(node 真跑，进食行渲染)：' + pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r200] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r200] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r200] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r200] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r200] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r200] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r200-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r200] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
