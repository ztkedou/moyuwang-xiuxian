# -*- coding: utf-8 -*-
r"""
yl_r210_ext.py — R-210：宠物经验曲线 1.2 -> 1.1（高等级可达性修复）

==============================================================================
零、目标产物与取证口径
==============================================================================
  目标：build/assets/index-v26m-20260927.js（BASE 未压缩 bundle / 1,583,034 B / 1,419,571 chars）。
  ★ 纯客户端改动（服务端 index_v28.ts 无宠物曲线；仅在离线挂机公式里读 p.maxExp）。

  改动 = 两组：
    (A) 4 处宠物升级循环的成长率 `*1.2` -> `*1.1`；
    (B) 存量宠物 maxExp 一次性迁移（否则老宠物仍按 1.2 尺度爬，改动对其无效）。

==============================================================================
一、(A) 4 处宠物升级循环（对 BASE 字符级实测，打前每锚点 count == 1）
==============================================================================
  ★ `*1.2` 在 BASE 共 11 处，其中仅 4 处是宠物升级循环；其余 7 处必须一字不动
    （见第三节 FREEZE）。故锚点一律用**完整循环表达式**，绝不用裸 `*1.2`。

  L1 (handleFeedPet)         : for(;oe>=W&&F<100;)oe-=W,F+=1,W=Math.floor(W*1.2),K=!0,
  L2 (handleBatchFeedItems)  : for(;Q>=B&&U<100;)Q-=B,U+=1,B=Math.floor(B*1.2),Y=!0,
  L3 (handleBatchFeedHp)     : for(;B>=L&&Y<100;)B-=L,Y+=1,L=Math.floor(L*1.2),P=!0,
  L4 (expedition 结算)       : for(;W>=X&&K<100;)W-=X,K+=1,X=Math.floor(X*1.2),le=!0;

  每处仅把 `Math.floor(<var>*1.2)` 的速率改为 `*1.1`，其余（`<100` 上限、Math.floor、
  变量名、逗号/分号）逐字不动。

==============================================================================
二、(B) 存量宠物 maxExp 迁移 —— 结论：**可行**（唯一载入钩子 ho）
==============================================================================
  取证：宠物从存档载入的路径
    · GET /api/save 整包透传 saveData（服务端只读 p.maxExp 做离线公式，不规范化 pets）
    · 客户端 applyRemoteSave/loadGame/import 全部经**唯一**载入规范化函数
      `ho=t=>{var T,$; ...}`（玩家级 hydration：规范化 realm/maxHp/exp/maxExp...）。
      ★ 实测 `ho=t=>{var T,$;` 在 BASE 中 **count == 1**（唯一）。
    · 但 `ho` 原样透传 pets（`return{...t,...}` 里无 pets 键）⇒ **不存在现成的宠物规范化**。

  结论：`ho` 是每次载入/导入/存档都会跑的**安全载入钩子**，可在此注入**幂等、只降不升**的重算：
      need = floor(60 * 1.1^(level-1))
      仅当 现值 maxExp > need 时下调 maxExp = need；等于/小于/非数一律不动 ⇒ 重复执行无副作用。
      ⇒ 老宠物（如 L30 存 60*1.2^29≈11870）在下次载入时被压到 1.1 尺度（≈951），改动即刻生效。

  ★ 附加的必要安全项（超出题面 maxExp-only 的 1 处，务必知悉）：
    单降 maxExp 会**破坏系统既有不变量 `exp < maxExp`**（循环保证升级后 exp 必 < maxExp）。
    若不同步处理 exp，一只 exp 接近旧 maxExp 的高阶宠在下次获得经验时会在循环里瞬间连升多级
    （L30 约 +5~12 级、L50 约 +40~70 级、L70 直接顶到 L100）。故迁移同时对 exp 做**等比缩放**
      exp = floor(exp * need / cur)
    以保留「距下一级的进度百分比」，维持不变量、避免爆级。此为最小必要修正，非功能扩张。

  幂等标记 `/*[r210pet]*/` 落于 ho 注入语句之后（JS 块注释，玩家不可见）。

==============================================================================
三、冻结（本环**绝不**碰，逐条 count 实测 == 1）
==============================================================================
  其余 7 处 `*1.2`（非宠物循环）：
    [H.Armor]:c*1.2                    （装备槽倍率）
    Math.min(.8,f*1.2)                 （秘境风险）
    x*=.3+f*1.2                        （模板权重）
    Math.max(0,-r)*1.2                 （结果评级）
    Math.floor(m*1.2)                  （武器攻击）
    Math.floor(oe*1.2)                 （预估经验预览）
    L=1+fe.indexOf(C.realm)*1.2        （某奖励倍率）
  宠物创建 `maxExp:60`（3 处）与 `species:` 字段、`<100;` 等级上限 4 处 —— 全部不动。

==============================================================================
四、契约（照 localtest/yl_r208_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 探针）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r210-<时刻>`。
  · 幂等：产物已含标记 `/*[r210pet]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r210pet]*/'

# --------------------------------------------------------------------------- (A) 4 处宠物升级循环
OLD_LOOPS = [
    'for(;oe>=W&&F<100;)oe-=W,F+=1,W=Math.floor(W*1.2),K=!0,',
    'for(;Q>=B&&U<100;)Q-=B,U+=1,B=Math.floor(B*1.2),Y=!0,',
    'for(;B>=L&&Y<100;)B-=L,Y+=1,L=Math.floor(L*1.2),P=!0,',
    'for(;W>=X&&K<100;)W-=X,K+=1,X=Math.floor(X*1.2),le=!0;',
]
NEW_LOOPS = [x.replace('*1.2', '*1.1') for x in OLD_LOOPS]

# --------------------------------------------------------------------------- (B) 存量宠物 maxExp 迁移（ho 钩子）
# 只降不升、等比缩放 exp；`ho=t=>{var T,$;` 在 BASE 唯一。
MIG_OLD = 'ho=t=>{var T,$;'
MIG_BODY = (
    't={...t,pets:(Array.isArray(t.pets)?t.pets:[]).map(ne=>{'
    'const lv=Math.max(1,Math.floor(Number(ne&&ne.level)||1)),'
    'need=Math.floor(60*Math.pow(1.1,lv-1)),cur=Number(ne&&ne.maxExp);'
    'if(!(cur>need))return ne;const e0=Number(ne&&ne.exp)||0;'
    'return{...ne,maxExp:need,exp:Math.floor(e0*need/cur)}})};'
)
MIG_NEW = MIG_OLD + MIG_BODY + IDEMPOTENT_MARK

REPLACEMENTS = [
    ('A1 L1 handleFeedPet  *1.2 -> *1.1', OLD_LOOPS[0], NEW_LOOPS[0]),
    ('A2 L2 batchFeedItems *1.2 -> *1.1', OLD_LOOPS[1], NEW_LOOPS[1]),
    ('A3 L3 batchFeedHp    *1.2 -> *1.1', OLD_LOOPS[2], NEW_LOOPS[2]),
    ('A4 L4 expedition     *1.2 -> *1.1', OLD_LOOPS[3], NEW_LOOPS[3]),
    ('B  pet maxExp migration @ ho', MIG_OLD, MIG_NEW),
]

# 7 处无关 *1.2（本环必须原样保留）
OTHER_12 = [
    '[H.Armor]:c*1.2',
    'Math.min(.8,f*1.2)',
    'x*=.3+f*1.2',
    'Math.max(0,-r)*1.2',
    'Math.floor(m*1.2)',
    'Math.floor(oe*1.2)',
    'L=1+fe.indexOf(C.realm)*1.2',
]

# 冻结针脚（对**输入**校验，全 ASCII，count 实测）：本环不动的结构
FREEZE = [
    ('*1.2', 11),
    ('*1.1', 1),                 # BASE 既有 1 处：Q<.8&&(U=Math.round(U*1.1))
    ('maxExp:60', 3),            # 宠物创建 3 处
    ('F<100;', 1),
    ('U<100;', 1),
    ('Y<100;', 1),
    ('K<100;', 1),
    (MIG_OLD, 1),
] + [(x, 1) for x in OTHER_12]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R210-mark', IDEMPOTENT_MARK, 1, '==', '幂等标记恰 1 处'),
        # ---- (A) 4 处循环已为 *1.1 ----
        ('R210-L1 new', NEW_LOOPS[0], 1, '==', 'L1 循环 *1.1'),
        ('R210-L2 new', NEW_LOOPS[1], 1, '==', 'L2 循环 *1.1'),
        ('R210-L3 new', NEW_LOOPS[2], 1, '==', 'L3 循环 *1.1'),
        ('R210-L4 new', NEW_LOOPS[3], 1, '==', 'L4 循环 *1.1'),
        # ---- 4 处旧循环清零 ----
        ('R210-old L1 gone', OLD_LOOPS[0], 0, '==', 'L1 旧循环已清零'),
        ('R210-old L2 gone', OLD_LOOPS[1], 0, '==', 'L2 旧循环已清零'),
        ('R210-old L3 gone', OLD_LOOPS[2], 0, '==', 'L3 旧循环已清零'),
        ('R210-old L4 gone', OLD_LOOPS[3], 0, '==', 'L4 旧循环已清零'),
        # ---- 全量 *1.2 / *1.1 计数 ----
        ('R210-*1.2 total', '*1.2', 7, '==', '仅余 7 处无关 *1.2'),
        ('R210-*1.1 total', '*1.1', 5, '==', '既有 1 + 宠物循环 4'),
        # ---- 7 处无关 *1.2 原样保留 ----
        ('R210-other-1', OTHER_12[0], 1, '==', '[H.Armor] 装备槽倍率'),
        ('R210-other-2', OTHER_12[1], 1, '==', '秘境风险'),
        ('R210-other-3', OTHER_12[2], 1, '==', '模板权重'),
        ('R210-other-4', OTHER_12[3], 1, '==', '结果评级'),
        ('R210-other-5', OTHER_12[4], 1, '==', '武器攻击'),
        ('R210-other-6', OTHER_12[5], 1, '==', '预估经验预览'),
        ('R210-other-7', OTHER_12[6], 1, '==', '奖励倍率'),
        # ---- <100 上限 + Math.floor 结构未动 ----
        ('R210-cap F', 'F<100;', 1, '==', 'L1 等级上限未动'),
        ('R210-cap U', 'U<100;', 1, '==', 'L2 等级上限未动'),
        ('R210-cap Y', 'Y<100;', 1, '==', 'L3 等级上限未动'),
        ('R210-cap K', 'K<100;', 1, '==', 'L4 等级上限未动'),
        ('R210-floor W', 'Math.floor(W*1.1)', 1, '==', 'L1 Math.floor 结构未动'),
        ('R210-floor B', 'Math.floor(B*1.1)', 1, '==', 'L2 Math.floor 结构未动'),
        ('R210-floor L', 'Math.floor(L*1.1)', 1, '==', 'L3 Math.floor 结构未动'),
        ('R210-floor X', 'Math.floor(X*1.1)', 1, '==', 'L4 Math.floor 结构未动'),
        # ---- (B) 迁移 ----
        ('R210-mig body', MIG_NEW, 1, '==', 'ho 迁移语句恰 1 处'),
        ('R210-mig formula', 'Math.floor(60*Math.pow(1.1,lv-1))', 1, '==', '迁移公式在位'),
        ('R210-ho anchor kept', MIG_OLD, 1, '==', 'ho 锚点仍在（前缀）'),
        ('R210-pet create kept', 'maxExp:60', 3, '==', '宠物创建 3 处未动'),
    ]
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
    """返回 err（None 表示可打）。对**原件** s 校验锚点与冻结针脚。"""
    if _is_patched(s):
        return None  # 幂等，交由 main 判 rc=3
    for name, old, new in REPLACEMENTS:
        c = s.count(old)
        if c != 1:
            return 'anchor %s count=%d (expect 1)' % (name, c)
    for needle, cnt in FREEZE:
        c = s.count(needle)
        if c != cnt:
            return 'freeze pin %r count=%d (expect %d)' % (needle, c, cnt)
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


def _count(out, needle):
    if isinstance(needle, tuple):
        return sum(out.count(x) for x in needle)
    return out.count(needle)


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    """反向还原：把 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    import shutil
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


def _pet_probe(out):
    """从补丁后产物**实抽** ho 注入段与 L4 循环，断言关键片段在位。"""
    i = out.find(MIG_OLD)
    if i < 0:
        return False, 'ho anchor not found'
    seg = out[i:i + len(MIG_OLD) + 320]
    if 'Math.floor(60*Math.pow(1.1,lv-1))' not in seg:
        return False, 'migration formula missing in ho'
    if 'maxExp:need' not in seg or 'exp:Math.floor(e0*need/cur)' not in seg:
        return False, 'migration body incomplete in ho'
    if IDEMPOTENT_MARK not in seg:
        return False, 'idempotent mark missing in ho'
    if NEW_LOOPS[3] not in out:
        return False, 'L4 loop not *1.1'
    # ho 段内不得残留旧尺度 1.2 的宠物循环
    if 'Math.floor(X*1.2)' in out or 'Math.floor(W*1.2)' in out:
        return False, 'pet loop still *1.2'
    return True, 'ho inject: %s ...' % seg[:160].replace('\n', ' ')


def selftest(src):
    """内存自证：锚点 -> 补丁 -> 门禁 -> 往返 -> 幂等 -> node --check -> 探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r210pet] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r210pet] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r210pet] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r210pet] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r210pet] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r210pet] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _pet_probe(out)
    if ok is False:
        print('[r210pet] SELFTEST FAIL pet-probe: ' + pmsg)
        return 1
    print('[r210pet] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    print('[r210pet] probe>> ' + pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r210pet] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r210pet] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r210pet] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r210pet] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r210pet] round-trip mismatch: bytes outside the edit points changed')
        return 1

    if args.check:
        print('[r210pet] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-34s %s' % (label, 'OK'))
        ok, pmsg = _pet_probe(out)
        print('    probe %-33s %s' % ('pet-loop/migration', 'OK' if ok else 'FAIL'))
        print('    >> ' + pmsg)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r210-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r210pet] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-34s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
