# -*- coding: utf-8 -*-
r"""
yl_r220_ext.py — R-220 开局难度界面文案同步 + 「游戏中无法更改难度」核查（纯客户端）

需求原文（用户原话，节选）
--------------------------------------------------------------------------
  「简单模式不变，普通模式其他惩罚默认，修炼速度+50%，灵石获取+50%。
   困难模式修炼速度+100%，灵石获取+100%。困难模式不要直接清档，改成装备全掉，
   掉落40%-50%属性，掉一个1个大境界。**并且游戏中无法再更改难度**」

输入产物：build/assets/index-v2945-20261009.js（线上 0.9.45，
          md5 e5a451fe35fb7d0ad4422bdd8ddcac9b，2,321,665 B）
★ 本 bundle 该区段中文为**字面态**（非 \uXXXX 转义）：① 开局难度界面 @526411 起、
  ② 设置面板「游戏难度（仅查看）」@1817249 起，均为字面中文。故本模块所有锚点
  一律用**字面中文**（_precheck 对形态单列断言）。

==============================================================================
A. 文案同步（本环主责，共 4 处锚点）
==============================================================================
① 开局「选择游戏难度」界面（bundle@526411~@529104）
    · 简单档（一字不动）：`死亡无惩罚，适合新手体验`
    · 普通档 旧 → 新：
        `死亡掉落部分属性(10-20%)和装备(1-3件)`
        → `死亡掉落部分属性与装备(属性10-20%、装备1-3件)；修炼速度 +50%，灵石获取 +50%`
    · 困难档 旧 → 新：
        `死亡清除存档，适合挑战自我`
        → `死亡不掉档：装备全掉，掉落 40%~50% 属性，掉一个大境界；修炼速度 +100%，灵石获取 +100%`
② 设置面板「游戏难度（仅查看）」（bundle@1817249~@1817759）
    · 简单档（一字不动）：`简单模式 - 死亡无惩罚`
    · 普通档 旧 → 新：
        `普通模式 - 死亡掉落部分属性和装备`
        → `普通模式 - 死亡掉落部分属性与装备；修炼速度 +50%，灵石获取 +50%`
    · 困难档 旧 → 新（顺带插入幂等标记，见下）：
        `困难模式 - 死亡清除存档`
        → `困难模式 - 死亡不掉档，装备全掉、掉落 40%~50% 属性、掉一个大境界；修炼速度 +100%，灵石获取 +100%`

  ★ 为什么新串**不能**保留旧串为子串：门禁要求「旧文案清零」，若新串以旧串为前缀
    （直接追加），则产物内旧串 count != 0，fail-closed 断言必然失败。故死亡惩罚部分
    做了**等义改写**（「和装备」→「与装备」、「(10-20%)和装备(1-3件)」→
    「(属性10-20%、装备1-3件)」），既保数值口径不变，又保证旧串彻底消失。

  ★ 幂等标记：`/*YLXW_R220_V2945*/` 唯一。本环为纯文案替换，锚点均落在**字符串字面量
    内部**，若把 `/*...*/` 写进字符串会被玩家看到，故仿 r217 的做法，把标记插在 ② 困难档
    的**紧随 JSX 代码位**（`children:"…"})]})` 之后、`,e.jsx("p",…` 之前），
    即 `…})]})/*YLXW_R220_V2945*/,e.jsx(…` —— 这是合法的 JS 注释位（代码区，非字符串）。

  ★ 未动：① 顶部小标题「不同难度决定了死亡惩罚的严重程度」（仍准确——死亡惩罚确实随难度递进）、
    ① 底部脚注、② 底部说明（见 B 节：与实现一致，保留）。

==============================================================================
B. 「游戏中无法再更改难度」核查结论（只读排查，**未改逻辑**）
==============================================================================
  结论：**已成立，无后门**。开局后不存在任何可改写难度的入口。

  证据（bundle 全量枚举，字符级实测）：

  [difficulty 写入点 · 共 2 类，均只在「开局前/开局瞬间」触发]
    W1 @522553 `g=D=>{const Q=localStorage.getItem(et.SETTINGS),U=Q?JSON.parse(Q):{};
             U.difficulty=D,localStorage.setItem(et.SETTINGS,JSON.stringify(U))}`
       —— 该 setter 仅被开局界面单选框 `q=D=>{…j(Q),g(Q)}`（onChange）调用；
          单选框位于**开局难度选择界面**（gameStarted 之前）。⇒ 开局后不可达。
    W2 @594779/@594879 开局确认 `b={...d.settings,difficulty:c};
             t({player:u,logs:j,settings:b,gameStarted:!0,hasSave:!0});
             localStorage.setItem(et.SETTINGS,JSON.stringify(b))`
       —— `c` 即开局界面所选难度，写入发生在**开始游戏那一刻**。⇒ 开局后不可达。

  [difficulty 读点] @521026（读难度初值）、@1983094/@1983329（传入奇遇/挑战）、
    @2128008/@2128021（涅槃重生弹窗读取）——**均为只读**，不写。

  [设置更新器 @592447 `setSettings`] 为通用 settings 写盘器，但**设置面板无任何难度输入控件**：
    「游戏难度（仅查看）」@1817249 是纯 `div`（标签即写明「仅查看」），面板内控件只有
    自动保存 checkbox / 动画速度 select / 键位等，均不触碰 difficulty。⇒ 无法借此改难度。

  [saveGame @592863] 只是把当前 `a.settings` 原样重写回 localStorage，非改值入口。

  [读档 / 导入存档 @529104 及设置面板导入 @1814000] **不会带入难度**：
    · 导出 `hN=t=>btoa(encodeURIComponent(JSON.stringify(t)))`，其入参为
      `{player,logs,marketItems,timestamp,lastActiveTime}`——**不含 settings/difficulty**；
    · 导入 `zm` 只解析并校验 `{player,logs,timestamp}`，随后 `di(ho(L.player),L.logs||[])`
      （`di=(t,r,a)=>!0` 为空实现），全程不写 settings。
    ⇒ 存档往返不含难度，无法经此改难度。

  ⇒ ② 底部说明「难度模式在游戏开始时选择，无法更改」与实现**一致**，**保留原样**；
    ① 底部脚注「* 难度模式在游戏开始后可在设置中查看，但建议在开始前选择」亦与实现一致，保留。

  ★ 边界（不在本环，仅备案）：③ 涅槃重生弹窗 @2027242 的「困难模式下死亡将清除存档…」
    由 r219 负责改写；本模块**不碰**（冻结门禁 FRZ_REBIRTH 断言其原样 ==1）。

==============================================================================
C. 范围与冻结（不得触碰）
==============================================================================
  · 不改死亡惩罚逻辑（@604684 / @605719 / @606688）与涅槃重生弹窗（@2027100）—— r219 范围；
  · 不改难度系数表 `Qr.difficulty`（@294238）—— r218 范围；
  · 简单档两条描述、两处脚注、① 顶部小标题 —— 冻结门禁逐条断言未动。

==============================================================================
D. 契约（standalone，同 localtest/yl_r216_ext.py / yl_r217_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`（缺省自动探测 PATH 与 .workbuddy-ai 目录）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）；改前落 <src>.bak-r220-<时刻>。
  · 重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（含门禁未全绿、往返不一致、node --check 失败）。
  · EDITS 四元组 (label, old, new, n)，n=该处旧串期望命中数=替换次数（本环全 1）。
  · gates() 五元组 (name, needle, count, op, note)；_precheck() + 往返自证 + node 自检。
  · 纯客户端；不改 build_v26n.py / chain_build.py / dryrun_087.py / sim_remote_check.py /
    任何 build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 幂等标记
MARK = 'YLXW_R220_V2945'
MARK_COMMENT = '/*' + MARK + '*/'

# --------------------------------------------------------------------------- 锚点（字面中文，字符级实测 count==1）
# E1 ① 开局界面 · 普通档描述
A1 = '死亡掉落部分属性(10-20%)和装备(1-3件)'
N1 = '死亡掉落部分属性与装备(属性10-20%、装备1-3件)；修炼速度 +50%，灵石获取 +50%'

# E2 ① 开局界面 · 困难档描述
A2 = '死亡清除存档，适合挑战自我'
N2 = ('死亡不掉档：装备全掉，掉落 40%~50% 属性，掉一个大境界；'
      '修炼速度 +100%，灵石获取 +100%')

# E3 ② 设置面板 · 普通档标签
A3 = '普通模式 - 死亡掉落部分属性和装备'
N3 = '普通模式 - 死亡掉落部分属性与装备；修炼速度 +50%，灵石获取 +50%'

# E4 ② 设置面板 · 困难档标签（尾随 JSX 代码位顺带插入幂等标记）
A4 = 'children:"困难模式 - 死亡清除存档"})]})'
N4 = ('children:"困难模式 - 死亡不掉档，装备全掉、掉落 40%~50% 属性、掉一个大境界；'
      '修炼速度 +100%，灵石获取 +100%"})]})' + MARK_COMMENT)

EDITS = [
    ('E1 ①开局·普通「死亡掉落部分属性(10-20%)和装备(1-3件)」→ 等义改写 + 收益倍率',
     A1, N1, 1),
    ('E2 ①开局·困难「死亡清除存档，适合挑战自我」→ 不掉档 + 新死亡惩罚 + 收益倍率',
     A2, N2, 1),
    ('E3 ②设置·普通「普通模式 - 死亡掉落部分属性和装备」→ + 收益倍率',
     A3, N3, 1),
    ('E4 ②设置·困难「困难模式 - 死亡清除存档」→ 不掉档 + 新死亡惩罚 + 收益倍率 + MARK',
     A4, N4, 1),
]

# --------------------------------------------------------------------------- 冻结门禁串（不得改动）
FRZ_SIMPLE1 = '死亡无惩罚，适合新手体验'                       # ① 简单档描述
FRZ_SIMPLE2 = '简单模式 - 死亡无惩罚'                          # ② 简单档标签
FRZ_FOOT1 = '难度模式在游戏开始后可在设置中查看，但建议在开始前选择'   # ① 底部脚注
FRZ_FOOT2 = '难度模式在游戏开始时选择，无法更改'                 # ② 底部说明
FRZ_HEAD1 = '不同难度决定了死亡惩罚的严重程度'                  # ① 顶部小标题
FRZ_REBIRTH = '困难模式下死亡将清除存档，点击后将重置所有数据，返回开始页面'  # ③ r219 范围
FRZ_RADIO_EASY = 'value:"easy",checked:m==="easy"'           # ① 单选框结构
FRZ_RADIO_HARD = 'value:"hard",checked:m==="hard"'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    return [
        # ---- 幂等标记 ----
        ('R220·幂等标记唯一', MARK_COMMENT, 1, '==', 'YLXW_R220_V2945'),
        # ---- E1 ① 普通 ----
        ('E1·新串在位', N1, 1, '==', '① 普通档新描述'),
        ('E1·旧串清零', A1, 0, '==', '旧死亡惩罚括号写法必须为 0'),
        # ---- E2 ① 困难 ----
        ('E2·新串在位', N2, 1, '==', '① 困难档新描述'),
        ('E2·旧串清零', A2, 0, '==', '「死亡清除存档，适合挑战自我」必须为 0'),
        # ---- E3 ② 普通 ----
        ('E3·新串在位', N3, 1, '==', '② 普通档新标签'),
        ('E3·旧串清零', A3, 0, '==', '② 普通旧标签必须为 0'),
        # ---- E4 ② 困难 ----
        ('E4·新串在位', N4, 1, '==', '② 困难档新标签 + MARK'),
        ('E4·旧串清零', A4, 0, '==', '② 困难旧标签必须为 0'),
        # ---- 强化：旧口径彻底消失 ----
        ('强化·「死亡清除存档」全清', '死亡清除存档', 0, '==', '① + ② 两处旧困难口径均消失'),
        ('强化·新困难口径在位', '死亡不掉档', 2, '==', '① + ② 各 1'),
        ('强化·40%~50% 在位', '40%~50%', 2, '==', '① + ② 各 1'),
        ('强化·普通收益倍率在位', '修炼速度 +50%，灵石获取 +50%', 2, '==', '① + ② 各 1'),
        ('强化·困难收益倍率在位', '修炼速度 +100%，灵石获取 +100%', 2, '==', '① + ② 各 1'),
        # ---- 冻结：简单档两条描述（用户明确「简单模式不变」）----
        ('冻结·①简单档描述未动', FRZ_SIMPLE1, 1, '==', '死亡无惩罚，适合新手体验'),
        ('冻结·②简单档标签未动', FRZ_SIMPLE2, 1, '==', '简单模式 - 死亡无惩罚'),
        # ---- 冻结：脚注 / 小标题 / 单选框结构 ----
        ('冻结·①底部脚注未动', FRZ_FOOT1, 1, '==', 'B 节核查：与实现一致，保留'),
        ('冻结·②底部说明未动', FRZ_FOOT2, 1, '==', 'B 节核查：与实现一致，保留'),
        ('冻结·①顶部小标题未动', FRZ_HEAD1, 1, '==', '仍准确'),
        ('冻结·①easy单选框未动', FRZ_RADIO_EASY, 1, '==', ''),
        ('冻结·①hard单选框未动', FRZ_RADIO_HARD, 1, '==', ''),
        # ---- 冻结：③ 涅槃重生弹窗（r219 范围，本环不碰）----
        ('冻结·③涅槃重生弹窗未动', FRZ_REBIRTH, 1, '==', 'r219 范围'),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new, n in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old and new, '%s 锚点不得为空' % name
        assert n >= 1, '%s n 必须 >=1' % name
        # 本 bundle 该区段为字面中文 ⇒ 新旧锚点均须含非 ASCII
        assert any(ord(ch) >= 128 for ch in old), '%s old 须为字面中文（含非 ASCII）' % name
        assert any(ord(ch) >= 128 for ch in new), '%s new 须为字面中文（含非 ASCII）' % name
        # 关键 fail-closed：新串不得以旧串为子串（否则「旧串清零」门禁恒失败）
        assert old not in new, '%s 新串不得包含旧串（否则旧串无法清零）' % name

    # E1：保留 10-20% / 1-3 件 数值口径；追加 +50% 双收益
    assert '10-20%' in N1 and '1-3' in N1, 'E1 新串须保留原死亡惩罚数值口径'
    assert '修炼速度 +50%' in N1 and '灵石获取 +50%' in N1, 'E1 新串须含普通档双 +50%'
    # E2：不掉档 + 40%~50% + 掉一个大境界 + 双 +100%
    assert '不掉档' in N2, 'E2 新串须含「不掉档」'
    assert '40%~50%' in N2, 'E2 新串须含 40%~50%'
    assert '掉一个大境界' in N2, 'E2 新串须含「掉一个大境界」'
    assert '修炼速度 +100%' in N2 and '灵石获取 +100%' in N2, 'E2 新串须含困难档双 +100%'
    # E3：② 普通档前缀与双 +50%
    assert N3.startswith('普通模式 - '), 'E3 新串须保留「普通模式 - 」前缀'
    assert '修炼速度 +50%' in N3 and '灵石获取 +50%' in N3, 'E3 新串须含双 +50%'
    # E4：② 困难档前缀 + 双 +100% + MARK 落在尾随代码位
    assert 'children:"困难模式 - ' in N4, 'E4 新串须保留 children:"困难模式 - 前缀'
    assert '修炼速度 +100%' in N4 and '灵石获取 +100%' in N4, 'E4 新串须含双 +100%'
    assert N4.endswith(MARK_COMMENT), 'E4 新串须以幂等标记注释结尾（代码位）'
    assert MARK_COMMENT in N4, 'E4 新串须含幂等标记'
    # MARK 不得出现在任何 old 内；仅出现在恰一个 new 内
    for _n, o, _w, _c in EDITS:
        assert MARK not in o, 'MARK 不得出现在任何 old 锚点内'
    assert sum(1 for _n, _o, w, _c in EDITS if MARK_COMMENT in w) == 1, \
        'MARK 须恰好出现在一个 new 内'
    # 冻结串不得与任何 old/new 冲突（保证它们原样留存）
    for tag, s in (('FRZ_SIMPLE1', FRZ_SIMPLE1), ('FRZ_SIMPLE2', FRZ_SIMPLE2),
                   ('FRZ_FOOT1', FRZ_FOOT1), ('FRZ_FOOT2', FRZ_FOOT2),
                   ('FRZ_HEAD1', FRZ_HEAD1), ('FRZ_REBIRTH', FRZ_REBIRTH)):
        for _n, o, w, _c in EDITS:
            assert s not in o and s not in w, \
                '冻结串 %s 不得被任何 old/new 触及' % tag
    # 注入内容不得含网络/存储原语（纯文案替换，理应都不含）
    for _n, _o, w, _c in EDITS:
        for ban in ('fetch(', 'localStorage', 'XMLHttpRequest', 'setInterval(', 'setTimeout('):
            assert ban not in w, '注入内容不得含 %s' % ban


def _classify(txt):
    """判定基线态：'patched' / 'baseline' / 'partial'。"""
    n_new_ok = sum(1 for _t, _o, n, c in EDITS if txt.count(n) == c)
    n_old_ok = sum(1 for _t, o, _n, c in EDITS if txt.count(o) == c)
    if n_new_ok == len(EDITS) and n_old_ok == 0:
        return 'patched'
    if n_new_ok == 0 and n_old_ok == len(EDITS):
        return 'baseline'
    return 'partial'


def _node_check(out_bytes, node_bin):
    """对产物跑 `node --check`（fail-closed）；找不到 node 则告警跳过。"""
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        nroot = 'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions'
        if os.path.isdir(nroot):
            subs = sorted(os.path.join(nroot, d, 'node.exe') for d in os.listdir(nroot))
            for p in reversed(subs):
                if os.path.isfile(p):
                    node_bin = p
                    break
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check（可用 --node 显式指定）')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r220chk-', suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out_bytes)
        p = subprocess.run([node_bin, '--check', tmp],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            print('  [FAIL] node --check 未通过:\n%s'
                  % p.stderr.decode('utf-8', 'replace')[:2000])
            return False
        print('  [OK] node --check 通过')
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description='R-220 开局难度界面文案同步（4 处，客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2945-20261009.js）')
    ap.add_argument('--node', default=None, help='node 可执行文件（缺省自动探测）')
    a = ap.parse_args()
    src_path = a.src

    try:
        _precheck()
    except AssertionError as e:
        print('[FAIL] 断言失败: %s' % e)
        return 1

    if not os.path.exists(src_path):
        print('[FAIL] source not found: %s' % src_path)
        return 2
    with io.open(src_path, 'rb') as f:
        src = f.read()
    txt0 = src.decode('utf-8', errors='replace')

    # 1) 幂等 / 部分补丁态
    st = _classify(txt0)
    if st == 'patched':
        print('[SKIP] source looks already patched（R-220 四处文案已在位）')
        return 3
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 2) 基线碰撞检查：新串 / 标记不得已在基线出现
    for _name, _old, new, _n in EDITS:
        c = txt0.count(new)
        if c != 0:
            print('[FAIL] 新串已在基线出现 %d 次，拒绝写盘：%s' % (c, new[:48]))
            return 2
    if txt0.count(MARK_COMMENT) != 0:
        print('[FAIL] 幂等标记 %s 已在基线出现，拒绝写盘' % MARK_COMMENT)
        return 2

    # 3) 锚点计数（rc=2 面）
    for name, old, _new, n in EDITS:
        c = txt0.count(old)
        if c != n:
            print('[FAIL] %s 锚点出现 %d 次（期望 %d）' % (name, c, n))
            return 2

    # 4) 应用
    out_txt = txt0
    for _name, old, new, n in EDITS:
        out_txt = out_txt.replace(old, new, n)
    out = out_txt.encode('utf-8')

    # 5) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-28s actual=%d expect %s %d' % ('OK' if good else 'FAIL', label, act, op, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 6) 往返自证
    back = out_txt
    for _name, old, new, n in reversed(EDITS):
        assert back.count(new) == n, '往返自证：new 在产物中计数 != %d' % n
        back = back.replace(new, old, n)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 7) node 自检（fail-closed）
    if not _node_check(out, a.node):
        print('[FAIL] node --check 失败，未写盘')
        return 1

    # 8) 改前 .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r220-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r220-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print('  已原子写回 %s' % src_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
