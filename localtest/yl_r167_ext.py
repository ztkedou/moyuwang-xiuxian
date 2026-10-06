# -*- coding: utf-8 -*-
r"""
yl_r167_ext.py — R-167 仙务·妖灵：并入重复的「喂养/嬉戏」按钮 + 明确「今日互动」显示（纯客户端 standalone）

需求原文（台账 R-167，逐字）
--------------------------------------------------------------------------
  「仙务·妖灵 面板很多地方重复了，上面的今日互动不知道显示的什么内容，
    下面还有单独的"喂养"和"嬉戏"两个按钮。这两个应该归到前面的按钮，变成第一次免费。」

==============================================================================
一、现状侦察（线上产物 build/assets/index-v2925-20261006.js · 0.9.25）
==============================================================================
  仙务·妖灵面板 = `YlxwTPet`（GET /api/pet）。渲染顺序：

    YlxwTitle  extra = "今日互动 <playTimes>/<playDailyMax>"     @1041737   ← ①「上面的今日互动」
    YlxwR79Box(...)  帮助折叠框
    ├─ YlxwR18Card(t,m)   妖灵六字段卡
    └─ YlxwR18Panel(t,m,f,u)  「培养（出口：妖灵之力 PP）」
         ├─ YlxwR18FeedRow    「进食」三档：凡品·青草露 3000/+30 · 灵品·玉髓羹 15000/+150 · 仙品·九转灵丹 60000/+600
         │                    → POST /pet/feed { tier }        （服务端恒扣费，无每日免费额度）
         ├─ YlxwR18PlayRows   「互动」三种各 1 次/日免费 + 「买额度」2 次/日
         │                    → POST /pet/play { kind }         （tease/brush/talk 各 <1 放行，即「每日首次免费」）
         ├─ YlxwR18ExpedRow   秘径
         ├─ YlxwR18MiscRow    点化 / 归位 / 放生
         └─ YlxwR18bRuneRow   灵纹
    ─────────────────────────────────────────────────────────
    m && e.jsxs("div",{className:"flex gap-2"}, [
        e.jsx(YlxwBtn,{ ... f("feed","/pet/feed",{},  "已喂养") ... children:"喂养（消耗 <feedCost> 灵石）" }),
        e.jsx(YlxwBtn,{ ... f("play","/pet/play",{},  "嬉戏成功") ... children:"嬉戏" })
    ])                                                          @1043707  ← ②「下面单独的喂养/嬉戏」

  ★ 重复关系（逐字节实测）：
     · 「嬉戏」= POST /pet/play {}          → r018PlayKind(undefined) = **tease**
       「互动·逗弄」= POST /pet/play {kind:"tease"}  ⇒ **同一请求、同一免费额度**（tease < 1 放行）。
     · 「喂养」= POST /pet/feed {}          → r018FeedTier(undefined) = **common（凡品·青草露 3000/+30）**
       「进食·凡品·青草露」= POST /pet/feed {tier:"common"} ⇒ **同一请求、同一价**。
       （注：独立按钮 label 显示的 `consts.feedCost`=5000 是 legacy 值，与服务端 common 实扣 3000 不一致
         —— 删掉该按钮后此不一致自然消失。）
     ⇒ 「喂养/嬉戏」= 进食/互动 两行的**纯重复**，正是用户说的「很多地方重复了」。

==============================================================================
二、改法（2 处精确替换 · 0 新增文件 · 只动 YlxwTPet 内联 JSX）
==============================================================================
  E1  删除 YlxwTPet 里独立的「喂养/嬉戏」块（并入进食/互动两行；原功能一行不缺）：
        原： <...YlxwR18AdoptRow(t,f,u)>, m && e.jsxs("div",{...喂养...嬉戏...}), m && e.jsx(YlxwTSpiritUse,{pet:m})
        新： <...YlxwR18AdoptRow(t,f,u)>, /* [r167pet] ... */ m && e.jsx(YlxwTSpiritUse,{pet:m})
      （JSX children 数组里删掉中间那个元素即可，语法合法；注释即幂等标记 `[r167pet]`。）

  E2  「今日互动」标题由「今日互动 X/Y」改写为自解释文案：
        原： children: ["今日互动 ", playTimes, "/", playDailyMax]
        新： children: ["今日互动已用 ", playTimes, "/", playDailyMax, " 次，还剩 ", playDailyMax-playTimes,
                        " 次（每种每日首次免费）"]
      ⇒ 明确「它是什么（今日互动已用 X/Y 次）」「今日还剩几次」「首次免费」三件事，不再看不懂。

  ★ 不碰：YlxwR18Card / YlxwR18FeedRow / YlxwR18PlayRows / YlxwR18ExpedRow / YlxwR18MiscRow /
    YlxwR18bRuneRow / YlxwR18AdoptRow / YlxwTSpiritUse / careLog 列表 / YlxwR79Box / YlxwTitle 组件本体；
    不改任何数值结算、不改请求包装、不改存档结构、不改版本号；不碰 build_v26n.py / chain_build.py /
    dryrun_087.py / CHANGELOG* / build/index.html / srv/index_v28.ts / 任何既有 yl_*_ext.py。
    注册（STANDALONE_CLIENT 追加 'r167'）与升版由主对话做。

==============================================================================
三、★ 遗留：需求里的「喂养第一次不扣费」客户端表达不了 —— 必须动服务端（本环不改）
==============================================================================
  现状（srv/index_v28.ts 实测）：
    · POST /api/pet/feed（@13223）**无任何每日免费额度**：每次按 r018FeedTier(tier).cost 恒扣
      （common 3000 / fine 15000 / immortal 60000）。全仓 grep 无 feed 每日免费机制
      （`feed_log|feedQuota|feedFree|pet_feed` 均 0 命中）。
    · POST /api/pet/play（@13293）**已实现「每种每日 1 次免费」**（pet_play_log.tease/brush/talk 各 <1 放行）。
  ⇒ 所以：
    · 「嬉戏第一次免费」= **已满足**（嬉戏=tease，服务端本就首次不扣费）；
    · 「喂养第一次免费」= **服务端权威，客户端做不到**（客户端无法阻止 /pet/feed 扣费，也无退款端点）。
  若主对话决定落实「喂养首次免费」，建议（最小改动，照抄 pet_play_log 闸门口径）：
    · 表：新增 `pet_feed_log(player_id INTEGER, date TEXT, times INTEGER, PRIMARY KEY(player_id,date))`
      （或复用/扩展现有每日闸门表，风格与 pet_play_log 一致；注释线索见 srv/index_v28.ts:544）。
    · 端点：srv/index_v28.ts:13226 `const _feed = r018FeedTier(req.body?.tier);` 之后，先跑
      `INSERT INTO pet_feed_log(player_id,date,times) VALUES(?,?,1) ON CONFLICT(player_id,date)
       DO UPDATE SET times=times+1 WHERE times < 1`；`changes>0` ⇒ 本次免单（cost=0），否则按档扣费。
      失败/宠物行缺失时回退计数（照抄 play 端点 @13340-13343 的补偿式口径）。
    · 回显：GET /api/pet 增加 `feedQuota:{free:...}`，客户端可据此把进食行首档标成「今日首次免费」。
  本环**只交付客户端 2 处改动**（删重复按钮 + 明确显示），上述服务端方案仅登记，不在本文件内实施。

==============================================================================
四、契约（照 localtest/yl_r165_ext.py / yl_r166_ext.py）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + 可选 node 语法检查）。
  · 二进制读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 <src>.bak-r167-<时刻>。
  · 幂等：产物已含标记 `[r167pet]` ⇒ 打印 SKIP 并直接退出（不写盘，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 中文一律 esc() 成 \uXXXX 字面量（ASCII 原样保留，与产物「中文转义、ASCII 原文」同形态）。
  · 锚点必须纯 ASCII 且恰好出现 1 次（E1_OLD 含 \uXXXX 段，但无裸中文）。
  · 不跑网络：只读 --src 指向的本地文件。

==============================================================================
五、锚点（对 build/assets/index-v2925-20261006.js 字符级实测）
==============================================================================
  E1_OLD  count==1（494 字符）→ 打后 0
  E1_NEW  count==0（105 字符）→ 打后 1（含 `[r167pet]`）
  E2_OLD  count==1（120 字符）→ 打后 0
  E2_NEW  count==0（312 字符）→ 打后 1
  冻结   : YlxwR18Panel(t, m, f, u)==2 · YlxwR18PlayRows(t, m, f, u)==2 · YlxwR18FeedRow(t, m, f, u)==2
           YlxwR18Card(t, m)==2 · YlxwTSpiritUse, { pet: m }==1 · playDailyMax==1
           "/pet/feed"==2 · "/pet/play"==7
  打后   : "/pet/feed"==1 · "/pet/play"==6 · [r167pet]==1

==============================================================================
六、自测记录（本机实测 · 全程只动临时副本）
==============================================================================
  NODE = C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe
  [1] --check：门禁全绿 + round-trip identical=True（除 2 处外逐字节一致）
  [2] 首次补丁：rc=0，落 test.js.bak-r167-<ts>，chars 2134673 -> 2134476（delta -197）
  [3] 幂等重跑：rc=3 "already patched (idempotent skip)"（未写盘）
  [4] node --check 修补件：rc=0（语法合法）
  [5] 逐字符 diff：E1 -389（删重复块）+ E2 +192（标题改写）= 净 -197；逆向还原 == 原件
  ★ 只动展示侧；不新增请求、不改数值、不改服务端。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime


def esc(w):
    r"""中文（非 ASCII）→ bundle 内的 \uXXXX 字面量形态；ASCII（空格/引号/数字）原样保留。

    与产物形态一致：手写扩展块的中文是转义、ASCII 是原文（如 "（消耗 " -> "\uff08\u6d88\u8017 "）。
    """
    return ''.join(c if ord(c) < 128 else '\\u%04x' % ord(c) for c in w)


# --------------------------------------------------------------------------- 锚点（线上产物字符级实测 count==1）

# E1：YlxwTPet 内独立的「喂养/嬉戏」块 + 紧随其后的 YlxwTSpiritUse（保留作新尾，保证「替换」可逆）
E1_OLD = (
    ', m && e.jsxs("div", { className: "flex gap-2", children: ['
    'e.jsx(YlxwBtn, { disabled: !!u, onClick: function() { f("feed", "/pet/feed", {}, "'
    + esc('已喂养') + '"); }, children: "' + esc('喂养')
    + '" + (t && t.consts ? "' + esc('（消耗 ') + '" + YlxwNum(t.consts.feedCost) + "'
    + esc(' 灵石）') + '" : "") }), e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, '
    'onClick: function() { f("play", "/pet/play", {}, "' + esc('嬉戏成功')
    + '"); }, children: "' + esc('嬉戏') + '" })] }), m && e.jsx(YlxwTSpiritUse, { pet: m })'
)
# 删除重复块；用注释承载幂等标记 [r167pet]（JSX children 数组内块注释合法）
E1_NEW = (', /* [r167pet] dup feed/play buttons merged into feed/play rows */ '
          'm && e.jsx(YlxwTSpiritUse, { pet: m })')

# E2：YlxwTitle extra 的「今日互动」标题
E2_OLD = ('children: ["' + esc('今日互动') + ' ", YlxwNum(t && t.playTimes), "/", '
          'YlxwNum(t && t.consts && t.consts.playDailyMax)]')
E2_NEW = ('children: ["' + esc('今日互动已用') + ' ", YlxwNum(t && t.playTimes), "/", '
          'YlxwNum(t && t.consts && t.consts.playDailyMax), " ' + esc('次，还剩') + ' ", '
          '(YlxwNum(t && t.consts && t.consts.playDailyMax) - YlxwNum(t && t.playTimes)), " '
          + esc('次（每种每日首次免费）') + '"]')

# 冻结针脚：本环只动 E1/E2 两处，下列既有形态必须逐字在位（_precheck 对**原件**校验）
FREEZE = [
    ('YlxwR18Panel(t, m, f, u)', 2),
    ('YlxwR18PlayRows(t, m, f, u)', 2),
    ('YlxwR18FeedRow(t, m, f, u)', 2),
    ('YlxwR18Card(t, m)', 2),
    ('YlxwTSpiritUse, { pet: m }', 1),
    ('playDailyMax', 1),
    ('"/pet/feed"', 2),
    ('"/pet/play"', 7),
]

IDEMPOTENT_MARK = '[r167pet]'


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    return [
        ('R167·独立喂养/嬉戏块已删除', E1_OLD, 0, '==', '重复的独立按钮块必须清零'),
        ('R167·并入尾就位(含[r167pet])', E1_NEW, 1, '==', '删除后与 YlxwTSpiritUse 相邻'),
        ('R167·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r167pet] 恰好 1 处'),
        ('R167·旧标题已改写', E2_OLD, 0, '==', '原「今日互动 X/Y」必须消失'),
        ('R167·新标题就位', E2_NEW, 1, '==', '自解释标题恰好 1 处'),
        ('R167·首免文案在位', esc('每种每日首次免费'), 1, '==', '明确「每种每日首次免费」'),
        ('R167·/pet/feed 仅剩进食档位', '"/pet/feed"', 1, '==', '独立喂养入口已删除'),
        ('R167·/pet/play 仅剩互动档位', '"/pet/play"', 6, '==', '独立嬉戏入口已删除'),
        ('冻结 互动行未动', 'YlxwR18PlayRows(t, m, f, u)', 2, '==', '互动三档结构未改'),
        ('冻结 进食行未动', 'YlxwR18FeedRow(t, m, f, u)', 2, '==', '进食三档结构未改'),
        ('冻结 妖灵卡未动', 'YlxwR18Card(t, m)', 2, '==', '六字段卡未改'),
        ('冻结 灵宠作用块未动', 'YlxwTSpiritUse, { pet: m }', 1, '==', 'YlxwTSpiritUse 调用未改'),
    ]


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


REPS = [
    ('E1 删除重复的喂养/嬉戏块', E1_OLD, E1_NEW),
    ('E2 明确「今日互动」标题', E2_OLD, E2_NEW),
]


def _precheck(s):
    """返回 None=可打；否则返回错误串。对**原件** s 校验锚点与冻结针脚。"""
    if IDEMPOTENT_MARK in s or all(new in s for _, _, new in REPS):
        return None  # 幂等，交由 main 判 rc=3
    for name, old, new in REPS:
        if new in s:
            continue
        if s.count(old) != 1:
            return '%s 锚点出现 %d 次（期望 1）' % (name, s.count(old))
    for needle, cnt in FREEZE:
        if s.count(needle) != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, s.count(needle), cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时为错误串，out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPS:
        if new in out:
            continue
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
    return None


def _roundtrip_ok(out, s0):
    rev = out
    for name, old, new in REPS:
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    """对 js_text 跑 node --check；返回 (rc, node_path) 或 (None, None) 当无 node。"""
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


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check（可选）。"""
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r167] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r167] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r167] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r167] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r167] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r167] SELFTEST FAIL ' + nmsg)
        return 1
    print('[r167] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(gates()), len(out) - len(s0), nmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r167] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r167] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r167] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r167] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r167] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r167] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-34s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r167-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r167] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-34s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
