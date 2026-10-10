# -*- coding: utf-8 -*-
r"""
yl_r165_ext.py — R-165 打坐「顿悟」同一触发点产生悟道心得（standalone · 与 srv_patch_r165.py 配套）

需求原文（台账 R-165，逐字）
--------------------------------------------------------------------------
  「打坐 / 历练中会随机触发悟道经验提升。可以把这个和打坐的顿悟做成同一个点触发，
    这样顿悟时既可以获得额外的经验，又可以产生悟道经验。」

==============================================================================
一、判断：能不能纯客户端实现？—— 不能
==============================================================================
  · 悟道（wudao 表：player_id/dao_type/level/exp）是**服务端权威**数据，
    客户端只读（GET /wudao 拉等级/经验），没有任何客户端入账通路。
  · 因此「顿悟时产生悟道经验」必须由服务端入账：唯一入账函数
    wudaoAddExp(userId, daoKey, expDelta, source)（srv/index_v28.ts:7166）。
  ⇒ 本环 = 客户端「多打一次请求」+ 服务端「新端点入账」，两侧配套。

  被否掉的方案（含理由）：
    (a) 客户端直接改 wudao 表 / 本地造 exp —— 无通路，且破坏服务端权威。否。
    (b) 复用既有 POST /wudao/insight —— 语义错误：那是「花 5000 灵石换 100 exp」的
        手动顿悟快车道（WUDAO_MANUAL_COST / WUDAO_MANUAL_EXP），与「打坐顿悟免费得心得」无关。否。
    (c) 客户端把「顿悟次数」写进存档字段，服务端在既有 tickWudaoIdle 里按次数入账
        （零新端点）—— 需要动存档结构（存档由客户端权威上传，改结构风险高、且与
        既有 statistics/差值口径耦合），回报不成比例。否（作为备选记录）。
    (d) 裸 fetch / XMLHttpRequest 自建请求 —— 项目风格禁止；必须沿用既有请求包装
        YlxwPost(path, body)（= YlxwUseAct 内部所用同一包装，bundle @913xxx）。否。

==============================================================================
二、改法（2 处精确替换 · 只挂 1 个客户端触发点）
==============================================================================
  E1  打坐顿悟分支末尾挂一次 fire-and-forget 入账调用：
        原： ...YlxwToast(x,"special","md-exp",4000),c(x,"special")}
        新： ...YlxwToast(x,"special","md-exp",4000),c(x,"special"),YlxwWudaoEnlighten(c)}
      （`c` = Be.getState().addLog；`x` = 顿悟文案；此分支即 bundle 内唯一顿悟点，
        Math.random()<.004，count==1。日志仍只写「顿悟」一条 —— 见下方「三」。）
  E2  在 `function YlxwMedTick(S, insight) {` 之前声明助手 YlxwWudaoEnlighten(addLog)：
      走 YlxwPost("/wudao/enlighten", {})，成功(r.ok && r.daoName)才补一条日志，
      失败/被频控一律静默（.catch 吞掉 + 外层 try/catch），绝不影响打坐主流程。

  ★ 为什么「只挂 1 处（打坐顿悟），不挂历练」——务必保留此结论：
    1) 需求「和打坐的顿悟做成同一个点触发」指向打坐顿悟这一点；
    2) **历练已在服务端计入悟道**：srv/index_v28.ts:7193 ylWudaoIdleDelta() 已把
       「打坐 + 历练」两类计数器差值一起喂给 tickWudaoIdle（该处注释明写
       「悟道挂机时长 = 打坐 + 历练（用户要求『打坐/历练中随机触发悟道经验』）」），
       即历练侧的时间型随机悟道经验服务端已具备；
    3) 历练的即时事件「奇遇」(bundle @1913920) 概率 V=min(.3, .05+境界*.02+…)
       最高 30%/次、历练间隔 6s ⇒ 最高约 180 次/小时；若同点入账 10 exp =
       ~1800 exp/小时 ≈ 单系满级 2250 的 80%/小时，**严重破坏悟道曲线**。
       故历练不挂即时点，继续走服务端已定档的挂机 roll（0.04/min ⇒ ~24 exp/小时）。
    4) 少一个锚点 = 少一份回归风险。

==============================================================================
三、日志文案策略（为什么是「紧随其后补一条」而不是「并进同一句」）
==============================================================================
  · 系别由**服务端随机取本人已开放系**（服务端才知道境界门槛 WUDAO_DAO_REALM_GATE），
    客户端在顿悟那一刻拿不到 daoName ⇒ 无法把内容并进同一句 x（同步字符串）。
  · 故：顿悟那一句原样不动（仍只 1 条 c(x,"special")），入账**成功后**再补 1 条
    「☯ 悟道【X道】心得 +N」。这样文案永不说谎（失败/被频控时不补）。
  · 若改由客户端随机取系并同步拼进同一句 ⇒ 需把十系 key/name 复制到客户端
    （与服务端 WUDAO_DAOS 双份真相、易漂移），且被频控时文案会虚报。故不取。

==============================================================================
四、契约（照 localtest/yl_r163_ext.py / yl_r155_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`（另留 `--check` 只验不写）；二进制读写；就地原子写回
    （mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r165-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；
            1=断言失败或门禁/往返失败。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
  · 中文一律 esc() 成 \uXXXX 字面量（本脚本新增文案全为 BMP 码点，无代理对问题）。
  · 不跑网络：只读 --src 指向的本地文件。

==============================================================================
五、锚点（在 build/assets/index-v2924-20261006.js 上字符级实测，全部 count==1）
==============================================================================
  E1 锚  : YlxwToast(x,"special","md-exp",4000),c(x,"special")           -> 1
  E1 旧尾: <E1 锚>}                                                       -> 1（打后须 0）
  E2 锚  : function YlxwMedTick(S, insight) {                            -> 1
  冻结   : 你突然顿悟 -> 1 · 打坐加速回血 -> 1 · YlxwMedTick(S,b); -> 1
           function YlxwMedSession(on) { -> 1
  幂等标 : YlxwWudaoEnlighten  -> 0（打后 >=1）

==============================================================================
六、自测记录（本机实测，命令 + 结果）
==============================================================================
  NODE = C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe
  TMP  = C:/Users/<USER>/AppData/Local/Temp/r165t/t.js   （build 产物临时副本）

  [1] 首次补丁：  python localtest/yl_r165_ext.py --src $TMP
        -> rc=0
        -> "patched: 2133500 -> 2134404 bytes (backup t.js.bak-r165-20261006_125023)"
           （脚本沿用 r163/r155 口径，len() 打印的是**字符数**；磁盘字节
            2301289 -> 2302193，+904 字节）
        -> 12 条 gate 全 OK（含 5 条冻结针脚）
  [2] 幂等重跑：  python localtest/yl_r165_ext.py --src $TMP
        -> rc=3  "already patched (idempotent skip)"（未写盘；文件 mtime 不变）
  [3] 语法合法：  node --check $TMP
        -> rc=0（无输出=语法合法）
  [4] 逐字符 diff（python，原件 vs 补丁件）：
        -> 恰 2 处纯插入（无删除/无改写）：
             INS1 = ',YlxwWudaoEnlighten(c)'                      22 字符 @743420
             INS2 = 助手块（注释+函数体）                            882 字符 @619449
           22+882 = 904 = 字符差；两插入各自唯一；
           逆向删除两插入 == 原件（round-trip identical = True）。
        -> 其余 2133500 字符逐字符一致。
  [5] 助手文案解码复核：addLog("☯ 悟道【" + r.daoName + "】心得 +" + (r.expGain||0), "special")

  ★ 只动展示/请求侧：不改任何数值结算、不改 Hw 循环、不改 addLog、不改存档结构、
    不改版本号 / build_v26n.py / chain_build.py / dryrun_087.py / CHANGELOG* /
    build/index.html / srv/index_v28.ts / 任何既有 yl_*_ext.py。
"""

import argparse
import os
import sys
import tempfile
from datetime import datetime


def esc(w):
    r"""中文 → bundle 内的 \uXXXX 字面量形态（bundle 以此存中文）。

    仅用于 BMP 码点（本环新增文案全为 BMP：☯ U+262F / 【】U+3010-3011 / 常用汉字）。
    """
    return ''.join('\\u%04x' % ord(c) for c in w)


# --------------------------------------------------------------------------- 锚点（线上产物字符级实测 count==1）

# E1：打坐顿悟分支末尾（纯 ASCII 段，唯一）
E1_OLD = 'YlxwToast(x,"special","md-exp",4000),c(x,"special")'
E1_NEW = E1_OLD + ',YlxwWudaoEnlighten(c)'
# ★ 2026-10-10 R-241：顿悟分支尾部又被合法改写为「1/3 概率产心得」
#   ⇒ 终态（全链跑完）此段为 E1_NEW_END，而本环 apply 时（R-241 之前）仍是 E1_NEW。
#   故门禁改「tuple 合计两形态」，两种场景均 == 1（照 R-206 的跨补丁针脚演进做法）。
E1_NEW_END = E1_OLD + ',Math.random()<.3333&&YlxwWudaoEnlighten(c)'
# 旧尾（打后必须清零）：证明「顿悟分支的收尾」确实被改写
E1_OLD_TAIL = E1_OLD + '}'

# E2：助手声明插入点（YlxwMedTick 之前，同模块作用域，函数提升可被 E1 调用）
DECL_ANCHOR = 'function YlxwMedTick(S, insight) {'

# 助手块（注释用 ASCII，避免 \uXXXX 在注释里不可读；文案用 esc()）
WUDAO_TAIL_PREFIX = esc('☯ 悟道【')
WUDAO_TAIL_SUFFIX = esc('】心得 +')

DECL_BLOCK = (
    '/* ===== yl-R165 wudao-enlighten: meditate insight also yields WUDAO insight =====\n'
    '   Same trigger point as the meditate "insight" (bundle: Math.random()<.004).\n'
    '   Fire-and-forget POST /wudao/enlighten -> server picks one of the player\'s\n'
    '   UNLOCKED dao, credits +WUDAO_INSIGHT_EXP via wudaoAddExp(...,\'idle\'), and\n'
    '   self-throttles. Any failure/throttle is swallowed: the meditate loop is never\n'
    '   affected. On success only, append one log line after the insight line.\n'
    '   MUST use the project request wrapper YlxwPost (no raw fetch). */\n'
    'function YlxwWudaoEnlighten(addLog) {\n'
    '  try {\n'
    '    YlxwPost("/wudao/enlighten", {}).then(function (r) {\n'
    '      if (r && r.ok && r.daoName) {\n'
    '        try { addLog("' + WUDAO_TAIL_PREFIX + '" + r.daoName + "' + WUDAO_TAIL_SUFFIX
    + '" + (r.expGain || 0), "special"); } catch (e) {}\n'
    '      }\n'
    '    }).catch(function () {});\n'
    '  } catch (e) {}\n'
    '}\n'
)

# 冻结针脚：本环只动这两处，下列既有形态必须逐字在位（原样 count 见文件头 §五）
FREEZE = [
    ('你突然顿悟', 1),                              # 顿悟文案未被改写
    ('打坐加速回血', 1),                             # 打坐回血段未被改写
    ('YlxwMedTick(S,b);', 1),                       # 打坐 tick 累加调用未动
    ('function YlxwMedSession(on) {', 1),           # 打坐会话汇总未动
    ('YlxwMedTick(S, insight) {', 1),               # 累加器签名未动
]


def gates():
    return [
        # ===== E1 顿悟分支挂点 =====
        ('R165·顿悟分支已挂入账', (E1_NEW, E1_NEW_END), 1, '==',
         '顿悟分支末尾调用恰好 1 处（tuple 合计：R-241 前 E1_NEW / R-241 后 E1_NEW_END）'),
        ('R165·旧顿悟分支尾清零', E1_OLD_TAIL, 0, '==', '旧收尾（无挂点）必须消失'),
        # ===== E2 助手声明 =====
        ('R165·入账助手已声明', DECL_BLOCK, 1, '==', '助手声明块恰好 1 处'),
        ('R165·走项目请求包装', 'YlxwPost("/wudao/enlighten", {})', 1, '==',
         '必须用 YlxwPost，禁裸 fetch/XMLHttpRequest'),
        ('R165·仅成功才补日志', 'r.ok && r.daoName', 1, '==', '失败/频控不补日志'),
        # ★ 0.9.31 R-184 在 `function YlxwMedTick(S, insight) {` **之前**插入 HELPER_BLOCK，
        #   打断本针脚原「助手收尾紧跟 YlxwMedTick」的相邻性假设 ⇒ 改为以助手自身尾部
        #   （esc 文案 + 内层 try/catch + .catch 吞 + 外层 catch）为锚，不再依赖邻居。
        ('R165·失败静默(无外层抛出)',
         'r.expGain || 0), "special"); } catch (e) {}\n      }\n    }).catch(function () {});\n  } catch (e) {}\n}',
         1, '==', '请求失败自吞(内层 try/catch + .catch 吞 + 外层 catch，唯一；不再依赖 YlxwMedTick 相邻)'),
        ('R165·传入 addLog', 'YlxwWudaoEnlighten(c)', 1, '==', '复用顿悟分支的 addLog'),
    ] + [('冻结 ' + n[:24], n, c, '==', '冻结既有形态') for n, c in FREEZE]


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
    ('E1 顿悟分支挂入账', E1_OLD, E1_NEW),
    ('E2 助手声明', DECL_ANCHOR, DECL_BLOCK + DECL_ANCHOR),
]

IDEMPOTENT_MARK = 'YlxwWudaoEnlighten'


def _precheck(s):
    """返回 None=可打；否则返回错误串。"""
    if all(new in s for _, _, new in REPS):
        return None  # 幂等，交由 main 判 rc=3
    for name, old, new in REPS:
        if new in s:
            continue
        if s.count(old) != 1:
            return '%s 锚点出现 %d 次（期望 1）' % (name, s.count(old))
    if s.count(E1_OLD_TAIL) != 1:
        return 'E1 旧收尾出现 %d 次（期望 1）' % s.count(E1_OLD_TAIL)
    for needle, cnt in FREEZE:
        if s.count(needle) != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, s.count(needle), cnt)
    return None


def apply_patch(src):
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        print('[r165] ABORT: ' + err)
        return 2
    out = s
    for name, old, new in REPS:
        if new in out:
            continue
        out = out.replace(old, new, 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r165] src not found: %s' % src)
        return 2

    s0 = _read(src)
    if all(new in s0 for _, _, new in REPS):
        print('[r165] already patched (idempotent skip)')
        return 3

    out = apply_patch(src)
    if isinstance(out, int):
        return out

    # 门禁
    for name, needle, cnt, op, note in gates():
        # ★ needle 支持 tuple/list（多形态合计计数）——R-241 后 E1 针脚用「E1_NEW + E1_NEW_END」合计。
        c = (sum(out.count(x) for x in needle) if isinstance(needle, (tuple, list))
             else out.count(needle))
        if op == '==' and cnt is not None and c != cnt:
            print('[r165] GATE FAIL %s: count=%d expect %d' % (name, c, cnt))
            return 1
        if op == '>=' and c < cnt:
            print('[r165] GATE FAIL %s: count=%d expect >=%d' % (name, c, cnt))
            return 1
    # 往返自证：除这两处外逐字节一致（逆向还原）
    rev = out
    for name, old, new in REPS:
        rev = rev.replace(new, old, 1)
    if rev != s0:
        print('[r165] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r165] check OK (%d bytes -> %d bytes)' % (len(s0), len(out)))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r165-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r165] patched: %d -> %d bytes (backup %s)'
          % (len(s0), len(out), os.path.basename(bak)))
    for name, needle, cnt, op, note in gates():
        print('    gate %-40s %s' % (name, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
