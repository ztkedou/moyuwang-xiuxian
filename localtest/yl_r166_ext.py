# -*- coding: utf-8 -*-
r"""
yl_r166_ext.py — R-166 仙务·妖灵「放生妖灵」补确认弹窗（纯客户端 standalone）

需求原文（R-166）
--------------------------------------------------------------------------
  仙务·妖灵  放生要加确认弹窗。

现状侦察（线上产物 build/assets/index-v2924-20261006.js · 0.9.24）
--------------------------------------------------------------------------
  产物里「放生」入口共 4 个 UI 入口（另有 2 个 store action 非 UI 入口）：

  #  入口（组件链）                                          触发代码                          确认?
  -  ------------------------------------------------------  --------------------------------  -----
  1  仙务·妖灵 → YlxwTPet → YlxwR18Panel → YlxwR18MiscRow    f("r18release",                    ❌无
     → YlxwR18AwayReleaseRow @1039810                         "/pet/spirit/release", ...)
  2  灵宠面板 YlxwPetShell 卡内单个放生 @1754024              onClick:()=>A(I.id) → 弹窗 @1766045 ✅有
  3  灵宠面板 YlxwPetShell 列表单个放生 @1761079              onClick:()=>A(P.id) → 弹窗 @1766045 ✅有
  4  灵宠面板 YlxwPetShell 批量放生 @1754449                  onClick:()=>q(!0) → 弹窗 @1737214  ✅有
                                                             （title 批量放生灵宠 / 确认放生 @1737736）
  —  store handleReleasePet @1932636 / handleBatchReleasePets @1933117（业务逻辑，非 UI 入口）

  ⇒ 唯一「无确认」入口 = ① 仙务·妖灵面板的「放生妖灵」按钮，直连
    f("r18release", "/pet/spirit/release", {}, "已放生妖灵")，点了立即放生、无任何二次确认。
    这正是 R-166 所指。

改动（1 处精确替换 · 只包一层确认，不动数值/不改请求参数）
--------------------------------------------------------------------------
  E1 在 YlxwR18AwayReleaseRow 的放生按钮 onClick 里，`f(...)` 调用前插一句
     `if (!window.confirm("...")) return;`：
       · 与产物既有 4 处 `if (!window.confirm(...)) return;`（宗门/结盟 @1411194 等）
         及 R-163 一键收取确认同款写法，零新组件、锚点最小、最稳。
       · 取消 → return，不发起 /pet/spirit/release；确定 → 原请求逐字不变。
       · 不改「归位」「点化」「灵纹」等同排按钮；不改服务端。
  ★ 不碰 build_v26n.py / patches/client/yl_version_ext.py / CHANGELOG* / chain_build.py /
    dryrun_087.py / sim_remote_check.py / build/index.html / srv/index_v28.ts / deploy_v28/* /
    任何既有 yl_*_ext.py。注册（STANDALONE_CLIENT 追加 'r166'）与升版由主对话做。

产物中文存法说明
--------------------------------------------------------------------------
  产物存在两种中文形态：① 手写扩展块（Ylxw* 系列）用 \uXXXX 转义；② 压缩产物主体用
  原文字面量。本补丁锚点位于扩展块 ⇒ 新插入的中文一律用 esc() 转成 \uXXXX 字面量。

契约（照 localtest/yl_r163_ext.py / yl_r155_ext.py）
--------------------------------------------------------------------------
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r166-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；
            1=断言失败或门禁/往返失败。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。

自测实录（2026-10-06 · python 3.13.14 / node 22.22.2 · 全程只动临时副本）
--------------------------------------------------------------------------
  0) 锚点字符级实测（对 index-v2924-20261006.js 原文）：
       E1_OLD                count==1
       'r18release'          count==1
       '/pet/spirit/release' count==2（1 注释 + 1 调用）
       'window.confirm'      count==7（既有；本补丁后 8）
       'if (!window.confirm(' count==4（既有；本补丁后 5）
  1) cp bundle → /c/tmp/r166/test.js
     `python yl_r166_ext.py --src ./test.js`
       ⇒ rc=0 · patched: 2133500 -> 2133769 chars (2301289 -> 2301558 bytes)
         · 8 条 gate 全 OK（含往返自证 rev==s0）
         · 落备份 test.js.bak-r166-20261006_124908
  2) 再跑同一 test.js ⇒ rc=3（already patched (idempotent skip)）
  3) `node --check ./test.js` ⇒ rc=0（语法合法；对照原文 test.orig.js 亦 rc=0）
  4) `diff -u test.orig.js test.js`：唯一 hunk = @@ -4126,6 +4126,7 @@，
     新增 1 行 `if (!window.confirm("\u786e...")) return;`；
     `diff | grep -c '^[<>]'` = **1**（仅命中声明片段，其余逐字节不变）
  5) 解码核对：插入文案 = 「确定放生当前妖灵吗？放生后妖灵将被放弃（免费，可重新收养），此操作不可撤销。」
"""

import argparse
import os
import sys
import tempfile
from datetime import datetime


def esc(w):
    r"""中文 → bundle 内的 \uXXXX 字面量形态。"""
    return ''.join('\\u%04x' % ord(c) for c in w)


# --------------------------------------------------------------------------- 锚点（线上产物字符级实测 count==1）

# E1 仙务·妖灵「放生妖灵」按钮：确认文案 + 守卫
CONFIRM_CN = '确定放生当前妖灵吗？放生后妖灵将被放弃（免费，可重新收养），此操作不可撤销。'

# 原始直连调用（放生妖灵按钮 onClick 的下一行，唯一）
CALL_OLD = 'f("r18release", "/pet/spirit/release", {}, "' + esc('已放生妖灵') + '")'

E1_OLD = 'onClick: function () {\n        ' + CALL_OLD
E1_NEW = ('onClick: function () {\n        '
          'if (!window.confirm("' + esc(CONFIRM_CN) + '")) return;\n        '
          + CALL_OLD)

# 冻结针脚：本环只动 E1 一处，其余同块片段必须逐字在位
FREEZE = [
    (esc('已放生妖灵'), 1),                                        # 成功 toast 文案仍在
    (esc('放生妖灵（放弃当前妖灵'), 1),                             # 按钮 label 未动（不含空格，避开 \u0020）
    (esc('妖灵已归位'), 1),                                        # 同排「归位」按钮未动
    ('/pet/spirit/release', 2),                                   # 注释 1 + 调用 1
    ('r18release', 1),                                            # 唯一入口键
]


def gates():
    return [
        ('R166·旧直连放生已清零', E1_OLD, 0, '==', '原无确认直连调用必须消失'),
        ('R166·确认弹窗就位', 'window.confirm("' + esc(CONFIRM_CN) + '")', 1, '==',
         '放生前确认文案恰好 1 处'),
        ('R166·确认后仍发起原请求', E1_NEW, 1, '==', '请求参数未改（仅包一层确认）'),
    ] + [('冻结 ' + n[:26], n, c, '==', '冻结既有片段') for n, c in FREEZE]


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
    ('E1 放生妖灵确认', E1_OLD, E1_NEW),
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
        print('[r166] ABORT: ' + err)
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
        print('[r166] src not found: %s' % src)
        return 2

    s0 = _read(src)
    if all(new in s0 for _, _, new in REPS):
        print('[r166] already patched (idempotent skip)')
        return 3

    out = apply_patch(src)
    if isinstance(out, int):
        return out

    # 门禁
    for name, needle, cnt, op, note in gates():
        c = out.count(needle)
        if op == '==' and cnt is not None and c != cnt:
            print('[r166] GATE FAIL %s: count=%d expect %d' % (name, c, cnt))
            return 1
        if op == '>=' and c < cnt:
            print('[r166] GATE FAIL %s: count=%d expect >=%d' % (name, c, cnt))
            return 1
    # 往返自证：除这一处外逐字节一致（逆向还原）
    rev = out
    for name, old, new in REPS:
        rev = rev.replace(new, old, 1)
    if rev != s0:
        print('[r166] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r166] check OK (%d bytes -> %d bytes)' % (len(s0), len(out)))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r166-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r166] patched: %d -> %d bytes (backup %s)' % (len(s0), len(out), os.path.basename(bak)))
    for name, needle, cnt, op, note in gates():
        print('    gate %-40s %s' % (name, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
