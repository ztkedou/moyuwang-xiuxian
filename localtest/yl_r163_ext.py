# -*- coding: utf-8 -*-
r"""
yl_r163_ext.py — R-163 灵田「玩法说明 + 一键收取」文案校正（纯展示层 standalone · 与 srv_patch_r163.py 配套）

背景（为什么需要这一条客户端改动）
--------------------------------------------------------------------------
  R-163 服务端把灵田数值重定档（patches/server/srv_patch_r163.py）：
    · 种子价下限 3000 灵石；档间 ×2。
    · sell 纯卖钱草 = **小幅净赚**（回收率 1.20→1.025，逐档收敛，净赚 +600~+1200 有上界）；
      mix/rare/cult = **净亏换修为**（回收率 .50/.40/.25）。
  客户端因此有两处文案需要校正 / 补充：
    ① 灵田玩法说明第 ③ 条原文「想稳定**赚**灵石选纯卖钱草」——四线里只有 sell 净赚、
       其余三线净亏 ⇒ 原句把「想赚灵石」泛化到所有选择，属**错误引导**（照做会亏）。
    ② 一键收取（`/farm/harvest/all`）恒按 **变卖** 结算，但按钮**没有任何提示**：
       玩家若种的是 cult/mix/rare，一点即净亏 50%~75%。需在点按前补一句确认文案。

改动（3 处精确替换 · 只动可见文案/确认框，不动数值、不改后端调用参数）
--------------------------------------------------------------------------
  E1 文案纠偏：想稳定赚灵石 → 想稳定回收灵石（与定档口径一致：sell 只回收、不增殖）
  E2 一键收取确认：onClick 内包一层 window.confirm（★ 与 bundle 既有 6 处 window.confirm 同款），
     提示「纯卖钱草净赚 / 其余净亏」，取消则不发起请求（行为仅在「点了取消」时不同）。
  E3 玩法说明第 ⑤ 条「收取」后补一句同口径提示（提前发现，不必等到点按）。
  ★ 不改任何数值：灵田数值唯一权威源 = 服务端 farmCropDefs()（bundle 内注释亦明言
    「成熟时间 / 灵石 / 修为 的数值改档在服务端 farmCropDefs()（本块不改数值）」）。
  ★ 不改 build_v26n.py / chain_build.py / dryrun_087.py / CHANGELOG* / build/index.html /
    任何既有 yl_*_ext.py。注册（STANDALONE_CLIENT 追加 'r163'）由主对话做。

回收率 X（从 srv_patch_r163.py 新表算出，供确认文案）
--------------------------------------------------------------------------
  sell 纯卖钱草：1.200 / 1.150 / 1.100 / 1.050 / 1.025（净赚，102.5%~120%）
  mix 综合：0.50   rare 稀有：0.40   cult 纯修为：0.25（净亏，25%~50%）
  ⇒ 一键收取（恒变卖）的回收率区间 = **25%~120%**。

契约（照 localtest/yl_r155_ext.py）
--------------------------------------------------------------------------
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r163-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；
            1=断言失败或门禁/往返失败。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
"""

import argparse
import os
import sys
import tempfile
from datetime import datetime


def esc(w):
    r"""中文 → bundle 内的 \uXXXX 字面量形态（bundle 以此存中文）。"""
    return ''.join('\\u%04x' % ord(c) for c in w)


# --------------------------------------------------------------------------- 锚点（线上产物字符级实测 count==1）

# E1 文案纠偏
E1_OLD = esc('想稳定赚灵石')
E1_NEW = esc('想稳定回收灵石')

# E2 一键收取确认（按钮 onClick 整段；bundle 内 count==1）
E2_OLD = 'onClick: function () { f("hall", "/farm/harvest/all", {}); }'
CONFIRM_CN = ('一键收取按【变卖】结算：纯卖钱草回收 102.5%~120%（净赚），'
              '综合/稀有/纯修为草仅回收 25%~50%（净亏）。确定收取？')
E2_NEW = ('onClick: function () { if (window.confirm("' + esc(CONFIRM_CN) + '")) '
          'f("hall", "/farm/harvest/all", {}); }')

# E3 玩法说明 ⑤「收取」句尾补充
E3_OLD = esc('进本页自动一键收取成熟田。')
E3_NEW = E3_OLD + esc('一键收取按变卖结算（灵石回收率视品种 25%~120%）。')

# 冻结针脚：同段其余文案必须逐字在位（证明本环只动了这几处）
FREEZE = [
    (esc('想冲修为选纯修为草'), 1),                                        # ③ 另一分支
    (esc('变卖（换灵石，品阶越高越贵）'), 1),                                 # ① 变卖口径
    (esc('提前收获收益减半'), 1),                                          # ⑤ 提前收获
    ('farmCropDefs()', 1),                                                # 数值权威仍在服务端（注释）
]
# 旧形态（打后必须清零）
E1_OLD_CN = '想稳定赚灵石'


def gates():
    return [
        ('R163·旧「赚灵石」已清零', E1_OLD, 0, '==', '旧文案（净负/泛化后为错误引导）必须消失'),
        ('R163·新「回收灵石」就位', E1_NEW, 1, '==', '新文案恰好 1 处'),
        ('R163·一键收取确认就位', 'window.confirm("' + esc(CONFIRM_CN) + '")', 1, '==',
         '按钮点按前确认文案恰好 1 处'),
        ('R163·⑤ 收取补充就位', E3_NEW, 1, '==', '玩法说明 ⑤ 补充恰好 1 处'),
        ('R163·确认后仍发起原请求', E2_NEW, 1, '==',
         '请求参数未改（仅包一层确认）'),
    ] + [('冻结 ' + n[:26], n, c, '==', '冻结既有文案') for n, c in FREEZE]


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
    ('E1 文案纠偏', E1_OLD, E1_NEW),
    ('E2 一键收取确认', E2_OLD, E2_NEW),
    ('E3 ⑤ 收取补充', E3_OLD, E3_NEW),
]


def _precheck(s):
    """返回 None=可打；否则返回错误串。"""
    if all(new in s for _, _, new in REPS):
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
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        print('[r163] ABORT: ' + err)
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
        print('[r163] src not found: %s' % src)
        return 2

    s0 = _read(src)
    if all(new in s0 for _, _, new in REPS):
        print('[r163] already patched (idempotent skip)')
        return 3

    out = apply_patch(src)
    if isinstance(out, int):
        return out

    # 门禁
    for name, needle, cnt, op, note in gates():
        c = out.count(needle)
        if op == '==' and cnt is not None and c != cnt:
            print('[r163] GATE FAIL %s: count=%d expect %d' % (name, c, cnt))
            return 1
        if op == '>=' and c < cnt:
            print('[r163] GATE FAIL %s: count=%d expect >=%d' % (name, c, cnt))
            return 1
    # 往返自证：除这几处外逐字节一致（逆向还原）
    rev = out
    for name, old, new in REPS:
        rev = rev.replace(new, old, 1)
    if rev != s0:
        print('[r163] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r163] check OK (%d bytes -> %d bytes)' % (len(s0), len(out)))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r163-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r163] patched: %d -> %d bytes (backup %s)' % (len(s0), len(out), os.path.basename(bak)))
    for name, needle, cnt, op, note in gates():
        print('    gate %-40s %s' % (name, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
