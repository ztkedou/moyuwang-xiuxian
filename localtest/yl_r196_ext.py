# -*- coding: utf-8 -*-
r"""
yl_r196_ext.py — R-196：妖灵「灵纹」前 4 条加成重设 · 客户端接线（standalone 纯客户端）

★ 用户拍板（逐字）：「4. 数值可以微改，属性要重新设置一下。」
★ 服务端环 srv_patch_r196.py 已把前 4 条重设为：
    锐纹 critRate 0.02 + critDamage 0.08（新增第二属性）
    御纹 damageReduction 0.03 / 疾纹 dodgeRate 0.02 / 噬纹 lifeLeech 0.02
  后 2 条（蕴纹 expMul / 天纹 ppMul）一字不动。
  服务端 payload 新增键 `runeCritDmg`（紧邻既有 `runeCrit`）。

本环要解决的事（先结论）
==============================================================================
  ① 客户端 `YlxwR18bRuneBattle(o,p)` 此前**只读** runeCrit/runeDodge/runeLeech/runeDR，
     **不读** runeCritDmg ⇒ 服务端即便写了暴伤也是**死字段**（"只写不读"）。
     本环补一行：`if (s.runeCritDmg) o.critDamage += Number(s.runeCritDmg) || 0;`
     ⇒ 锐纹的暴伤真正进入两套战斗引擎（快速结算 `1.5 + YlxwPB.critDamage` /
        回合制 buffs 里 `critDamage` 累加）。
  ② 另一同事 r189c 的灵纹**可见化行**只展示 暴击/减伤/闪避/吸血，**不展示暴伤**。
     本环在该行内**追加**暴伤展示（读 `player.petSpirit.runeCritDmg`），保持 r189c 既有
     4 条展示与逻辑逐字不变。

链路取证（改前，贴行）
==============================================================================
  【服务端】srv/index_v28.ts
    · R018B_RUNE_TABLE（6716-6723，改后）：rui 含 kind2:'critDamage' value2:0.08。
    · r018bRuneEffect（6738-6752，改后）：kind2==='critDamage' ⇒ o.critDamage = d.value2。
    · r018bApplyRune（6754-6768，改后）：payload 增 `runeCritDmg: rn ? rn.critDamage : 0,`。
    · r018SpiritSync（6495-6505）：把 payload 写入 `player.petSpirit`。

  【客户端】build/assets/index-v2934-20261008.js（md5 41af9edf943a04c65447a7b74a4bd5b4）
    · YlxwR18bRuneBattle（改前）：
        function YlxwR18bRuneBattle(o, p) {
          var s = p && p.petSpirit;
          if (!o || !s) return;
          if (s.runeCrit) o.critRate += Number(s.runeCrit) || 0;
          if (s.runeDodge) o.dodgeRate += Number(s.runeDodge) || 0;
          if (s.runeLeech) o.lifeLeech += Number(s.lifeLeech) || 0;
          if (s.runeDR) o.damageReduction += Number(s.runeDR) || 0;
        }
      （缺 runeCritDmg ⇒ 暴伤死字段）
    · 调用点：YlxwBattleBonus 内 `YlxwR18bRuneBattle(o, p);`（末尾 YlxwBattleCap 统一封顶）。
    · 战斗消费：
        快速结算：`K?Math.round(Z*(1.5+(G?YlxwPB.critDamage:0))):Z`（G=玩家出手）
        回合制：buffs 内 `A.critDamage && (k += A.critDamage)`（YlxwSpellBuffs 已带出）
    · 封顶 YlxwBattleCapCfg = { critRate:.35, critDamage:.8, dodgeRate:.35, lifeLeech:.25, damageReduction:.5 }
      ⇒ 灵纹暴伤 0.08 远低于 0.8，与羁绊层（critDamage 上限 0.4）叠加 = 0.48 < 0.8，不撞顶。
    · r189c 可见化行（改前，本环只**追加**不改写）：
        var ylxwRc = Number(ylxwRunePs.runeCrit) || 0, ... ylxwRl = Number(ylxwRunePs.runeLeech) || 0;
        if (ylxwRc > 0) ylxwRuneEff.push("\u66b4\u51fb +" + ...);
        if (ylxwRd > 0) ...\u51cf\u4f24...  if (ylxwRo > 0) ...\u95ea\u907f...  if (ylxwRl > 0) ...\u5438\u8840...
        }/*[r189rune]*/

契约
==============================================================================
  · CLI：--src <bundle.js>（必填）/ --check（只验不写）/ --selftest（内存自证 + node --check + 探针）。
  · 就地替换 2 处；每处打前断言 count == 1（锚点**纯 ASCII**：bundle 中文为字面 \uXXXX）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 <src>.bak-r196-<时刻>。
  · 幂等：产物含 /*[r196rune]*/ ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · gates() 五元组 (label, needle, expect, op, note)，op 支持 == / >=。
  · 探针：实抽补丁后的 YlxwR18bRuneBattle 与 r189c 展示块，node 复算并校验。
  · ★ 跨补丁依赖：本环第 2 处锚点落在 r189c 的可见化行内 ⇒ **必须先应用 r189c 再应用本环**
    （流水线顺序即 r189c → r196，天然满足；若 r189c 缺失则本环 precheck fail-closed，rc=2）。
  · ★ 冻结针脚只钉本批不动的稳定形态，绝不钉 [r180adv*]/[r185farm*]/[r184wudao]/[r187guide]/
    [r188med*]/[r190feed]/[r189ui]/[r189rune]（后者仅作"r189c 在位"的存在性断言，不做形态冻结）。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# 幂等标记（本批）
IDEMPOTENT_MARK = '/*[r196rune]*/'

# --------------------------------------------------------------------------- 替换项
# ★ 形态约定：bundle 该区域中文为**字面 `\uXXXX`**（六字符）⇒ 本 .py 源码保持纯 ASCII，
#   用 `\\uXXXX`（双反斜杠）写出，运行期字符串即 `\uXXXX`。

# ---- ① YlxwR18bRuneBattle：新增 runeCritDmg → o.critDamage 读取 ----
R1_OLD = (
    '  if (s.runeDR) o.damageReduction += Number(s.runeDR) || 0;\n'
    '}'
)
R1_NEW = (
    '  if (s.runeDR) o.damageReduction += Number(s.runeDR) || 0;\n'
    '  if (s.runeCritDmg) o.critDamage += Number(s.runeCritDmg) || 0;' + IDEMPOTENT_MARK + '\n'
    '}'
)

# ---- ② r189c 可见化行：追加「暴伤」展示（保持原 4 条逐字不变） ----
R2_OLD = (
    '    if (ylxwRl > 0) ylxwRuneEff.push("\\u5438\\u8840 +" + (ylxwRl * 100).toFixed(1) + "%");\n'
    '  }/*[r189rune]*/'
)
R2_NEW = (
    '    if (ylxwRl > 0) ylxwRuneEff.push("\\u5438\\u8840 +" + (ylxwRl * 100).toFixed(1) + "%");\n'
    '    var ylxwRcd = Number(ylxwRunePs.runeCritDmg) || 0;\n'
    '    if (ylxwRcd > 0) ylxwRuneEff.push("\\u66b4\\u4f24 +" + (ylxwRcd * 100).toFixed(1) + "%");\n'
    '  }/*[r189rune]*/'
)

REPLACEMENTS = [
    ('r1_critdmg', R1_OLD, R1_NEW),
    ('r2_rowdmg', R2_OLD, R2_NEW),
]

# 冻结针脚（对**输入**校验）：本批不动的稳定形态。
FREEZE = [
    ('function YlxwR18bRuneBattle(', 1),
    ('function YlxwR18bRuneRow(', 1),
    ('function YlxwBattleBonus(', 1),
    ('function YlxwPlayer(', 1),
    ('YlxwBattleCapCfg = { critRate: 0.35', 1),
    ('var YLXW_C2_BATTLE = [', 1),
    ('/*[r189rune]*/', 1),   # r189c 必须在位（本环第 2 处锚点依赖它）
]


def gates():
    """五元组 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    return [
        # ---- 幂等标记 ----
        ('R196\u00b7\u5e42\u7b49\u6807\u8bb0 r196rune', IDEMPOTENT_MARK, 1, '==', '[r196rune] 恰 1 处'),
        # ---- ① 战斗接线 ----
        ('R196\u2460\u00b7\u8bfb runeCritDmg', 'if (s.runeCritDmg) o.critDamage += Number(s.runeCritDmg) || 0;', 1, '==', '暴伤接线'),
        ('R196\u2460\u00b7\u539f\u56db\u884c\u4ecd\u5728 crit', 'if (s.runeCrit) o.critRate += Number(s.runeCrit) || 0;', 1, '==', '原暴击行保留'),
        ('R196\u2460\u00b7\u539f\u56db\u884c\u4ecd\u5728 dodge', 'if (s.runeDodge) o.dodgeRate += Number(s.runeDodge) || 0;', 1, '==', '原闪避行保留'),
        ('R196\u2460\u00b7\u539f\u56db\u884c\u4ecd\u5728 leech', 'if (s.runeLeech) o.lifeLeech += Number(s.runeLeech) || 0;', 1, '==', '原吸血行保留'),
        ('R196\u2460\u00b7\u539f\u56db\u884c\u4ecd\u5728 DR', 'if (s.runeDR) o.damageReduction += Number(s.runeDR) || 0;', 1, '==', '原减伤行保留'),
        # ---- ② 可见化行追加暴伤 ----
        ('R196\u2461\u00b7\u8bfb runeCritDmg\uff08\u884c\uff09', 'var ylxwRcd = Number(ylxwRunePs.runeCritDmg) || 0;', 1, '==', '展示读取'),
        ('R196\u2461\u00b7\u66b4\u4f24\u6807\u7b7e', 'ylxwRuneEff.push("\\u66b4\\u4f24 +"', 1, '==', '暴伤 +'),
        ('R196\u2461\u00b7\u539f r189c \u56db\u6807\u7b7e\u4ecd\u5728\u66b4\u51fb', 'ylxwRuneEff.push("\\u66b4\\u51fb +"', 1, '==', 'r189c 暴击保留'),
        ('R196\u2461\u00b7\u539f r189c \u56db\u6807\u7b7e\u4ecd\u5728\u51cf\u4f24', 'ylxwRuneEff.push("\\u51cf\\u4f24 +"', 1, '==', 'r189c 减伤保留'),
        ('R196\u2461\u00b7\u539f r189c \u56db\u6807\u7b7e\u4ecd\u5728\u95ea\u907f', 'ylxwRuneEff.push("\\u95ea\\u907f +"', 1, '==', 'r189c 闪避保留'),
        ('R196\u2461\u00b7\u539f r189c \u56db\u6807\u7b7e\u4ecd\u5728\u5438\u8840', 'ylxwRuneEff.push("\\u5438\\u8840 +"', 1, '==', 'r189c 吸血保留'),
        ('R196\u2461\u00b7r189c \u6807\u8bb0\u4ecd\u5728', '/*[r189rune]*/', 1, '==', 'r189c 未被破坏'),
        # ---- 未动（冻结针脚对应产物） ----
        ('R196\u00b7YlxwR18bRuneBattle \u4ecd\u5728', 'function YlxwR18bRuneBattle(', 1, '==', '战斗函数保留'),
        ('R196\u00b7YlxwR18bRuneRow \u4ecd\u5728', 'function YlxwR18bRuneRow(', 1, '==', '面板行保留'),
        ('R196\u00b7YlxwBattleCapCfg \u672a\u52a8', 'YlxwBattleCapCfg = { critRate: 0.35', 1, '==', '封顶未动'),
        ('R196\u00b7YLXW_C2_BATTLE \u672a\u52a8', 'var YLXW_C2_BATTLE = [', 1, '==', '人物志增益表未动'),
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


def _is_patched(s):
    return IDEMPOTENT_MARK in s


def _precheck(s):
    for name, old, new in REPLACEMENTS:
        c = s.count(old)
        if c != 1:
            return '锚点 %s 出现 %d 次（期望 1）' % (name, c)
    for needle, cnt in FREEZE:
        c = s.count(needle)
        if c != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, c, cnt)
    return None


def apply_patch(src):
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPLACEMENTS:
        out = out.replace(old, new, 1)
    return out, None


def _count(out, needle):
    if isinstance(needle, tuple):
        return sum(out.count(x) for x in needle)
    return out.count(needle)


def _run_gates(out):
    for label, needle, expect, op, note in gates():
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
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
    """实抽补丁后的 YlxwR18bRuneBattle + r189c 展示块，node 复算。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。"""
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'

    i = patched_text.find('function YlxwR18bRuneBattle(')
    j = patched_text.find('\n}\n', i)
    if i < 0 or j < 0:
        return False, 'YlxwR18bRuneBattle 块未找到'
    battle = patched_text[i:j + 2]

    k = patched_text.find('var ylxwRunePs =')
    m = patched_text.find('/*[r189rune]*/', k)
    if k < 0 or m < 0:
        return False, 'r189c 展示块未找到'
    row = patched_text[k:m]

    js = (
        'function mk(){ return { critRate: 0, critDamage: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0 }; }\n'
        + battle + '\n'
        '/* ---- battle probe ---- */\n'
        'var o1 = mk();\n'
        'YlxwR18bRuneBattle(o1, { petSpirit: { runeCrit: 0.02, runeCritDmg: 0.08 } });\n'
        'if (o1.critRate !== 0.02) throw new Error("critRate=" + o1.critRate);\n'
        'if (o1.critDamage !== 0.08) throw new Error("critDamage=" + o1.critDamage);\n'
        'var o2 = mk();\n'
        'YlxwR18bRuneBattle(o2, { petSpirit: { runeDR: 0.03, runeDodge: 0.02, runeLeech: 0.02 } });\n'
        'if (o2.damageReduction !== 0.03 || o2.dodgeRate !== 0.02 || o2.lifeLeech !== 0.02) throw new Error("other runes: " + JSON.stringify(o2));\n'
        'if (o2.critDamage !== 0) throw new Error("critDamage should stay 0");\n'
        '/* ---- r189c row probe (含本环追加的暴伤) ---- */\n'
        'var YlxwPlayer = function () { return { petSpirit: { runeCrit: 0.02, runeCritDmg: 0.08 } }; };\n'
        'var list = [{ key: "rui", name: "\\u9510\\u7eb9" }], active = "rui";\n'
        + row.replace('\n', '\n') + '\n'
        'var got = ylxwRuneEff.join(" \\u00b7 ");\n'
        'var want = "\\u66b4\\u51fb +2.0% \\u00b7 \\u66b4\\u4f24 +8.0%";\n'
        'if (got !== want) throw new Error("row mismatch: [" + got + "] want [" + want + "]");\n'
        'console.log("r196-probe>> battle+row ok: " + got);\n'
    )
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:400]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    s0 = _read(src)
    if _is_patched(s0):
        print('[r196] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r196] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r196] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r196] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r196] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r196] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _probe(out)
    if ok is False:
        print('[r196] SELFTEST FAIL probe: ' + pmsg)
        return 1
    print('[r196] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg, pmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r196] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r196] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r196] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r196] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r196] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r196] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r196-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r196] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
