# -*- coding: utf-8 -*-
r"""
yl_r232_ext.py — R-232 在线收益难度倍率「服务端权威值优先」（纯客户端 · 追加式）

需求原文（台账 R-232）
--------------------------------------------------------------------------
    在线收益的难度倍率（×1 / ×1.5 / ×2）仍读客户端 `localStorage`，
    玩家改一行本地存储即可白拿 ×2。改为「服务端权威值优先」。

背景（为什么必须「追加」到 R-218 之上、而不改 r218）
--------------------------------------------------------------------------
  · R-218（localtest/yl_r218_ext.py，标记 /*YLXW_R218_V2945*/）在 bundle @294933
    注入取值器 `YlxwDiffMul(t,r)`，取值优先级：
        ① 显式入参 t
        ② Be.getState().settings.difficulty（游戏内 store）
        ③ localStorage["xiuxian-game-settings"].difficulty（兜底）
        ④ 都拿不到 ⇒ "normal"
  · ② 与 ③ 都源自**客户端可控**数据（settings 是 localStorage 的镜像；难度写入点是
    `localStorage.setItem("xiuxian-game-settings", …)`）。⇒ 改本地存储即可白拿 ×2。
  · 服务端侧（另一环）持有**冻结难度**（saves.difficulty 列，0.9.51 的 R-225b 已在服务端
    落库冻结），本环约定服务端把冻结值以**顶层字段 `ylDifficulty`**（∈ easy/normal/hard）
    随读档接口下发到客户端。
  · 本环**不改** yl_r218_ext.py，而是在其产物之上**再注入**：
      1) 两个新模块级函数（追加进 md() 所在的同一逗号声明组）：
           · YlxwServerDiff()       —— 读模块级缓存 window.__ylSrvDiff（合法值才返回）。
           · YlxwSrvDiffCapture(j)  —— 从任意 JSON 响应里提取顶层 ylDifficulty 并缓存。
      2) 在**读档接口**的接收点（`const Pn={async fetchSave(){…const r=await t.json();…}}`）
         插入一次 `YlxwSrvDiffCapture(r);` —— 这是服务端下发值的落点。
      3) 把 `YlxwDiffMul` 的优先级改为：
           ① 显式入参 t
           ② **服务端下发值 YlxwServerDiff()（新增，权威）**
           ③ Be.getState().settings.difficulty（游戏内 store）
           ④ localStorage（降为最后兜底）
           ⑤ 都拿不到 ⇒ "normal"
      4) 把 R-222 的**显示取值器** `YlxwDiffCn` 也前置服务端值（与 3 同源），
         确保面板显示的中文难度与实际入账口径恒等。

服务端下发值在客户端「落到哪」——实测定论
--------------------------------------------------------------------------
  读档响应消费者 = `const Pn={async fetchSave(){const t=await Xc(`${ln}/save`);…
  const r=await t.json();try{var ylGh=t.headers&&t.headers.get("x-yl-gm-revision");…}`。
  该函数 `r` 即 `/yl/api/save` 的整包 JSON（含 `player` / `settings` / `logs` / …）。
  随后客户端据 `r.settings` 调 `setSettings`，据 `r.player` 调 loadGame。
  ⇒ 服务端若把 `ylDifficulty` 放在该响应**顶层**，则**落点就在 `r` 这一层**。
  本环**不猜**服务端是否已下发、也不依赖任何既有状态字段：直接在 `const r=await t.json();`
  之后插一个**接收钩子** `YlxwSrvDiffCapture(r);` —— 有则缓存、无则不动（幂等、零副作用）。
  另：所有 `YlxwGet/YlxwPost` 走 `YlxwApi()`（`YLApplyBalance(l, r)` 处），非读档接口若也带
  `ylDifficulty` 亦可被下游端点 payload 触达；但**本环只挂读档接口**（最小面、任务指定载体）。

★ 未覆盖（有意）
--------------------------------------------------------------------------
  · 本环**只换「在线收益取值的难度从哪来」**，不碰任何入账点 / 倍率表 / 惩罚项 ——
    R-218 的 EDITS（难度表 expMul/stoneMul、19 个入账点、YlxwDiffGain）**逐字未动**。
  · 服务端下发字段名约定为 `ylDifficulty`；若服务端改用别的字段/位置，本环的
    `YlxwSrvDiffCapture` 会取不到 ⇒ 自动回落旧优先级（= 与未打本环时行为一致，**不劣化**）。

==============================================================================
本环 EDITS（4 处，全部为**追加 / 前置插入**，旧串不删除）
==============================================================================
  A）定义处追加（md() 声明组的尾部，紧跟 R-218 的 YlxwDiffGain、在 `,Lm=` 之前）：
      锚：`…return isFinite(m)&&m>0?Math.floor(x*m):x}catch(e){return x}},Lm=`
      新：在 `}}` 与 `,Lm=` 之间插入 `MARK + YlxwServerDiff=…,YlxwSrvDiffCapture=…,`
  B）取值器优先级改写（YlxwDiffMul 内、var d=t 之后插入服务端分支）：
      锚：`YlxwDiffMul=(t,r)=>{try{var d=t;if(!d||!Qr.difficulty[d]){try{d=(Be.getState().settings||{}).difficulty}`
      新：`var d=t;` 后插 `if(!d||!Qr.difficulty[d]){try{d=YlxwServerDiff()}catch(e){}}`
  C）接收钩子（读档接口 fetchSave 的响应解析处）：
      锚：`const r=await t.json();try{var ylGh=t.headers`
      新：`const r=await t.json();MARK YlxwSrvDiffCapture(r);try{var ylGh=t.headers`
  D）显示取值器同步（R-222 的 YlxwDiffCn，面板难度中文名；与 B 同理，防「界面说困难、
     实际按普通算」的显示/入账不一致）：
      锚：`YlxwDiffCn=()=>{try{var d;try{d=(Be.getState().settings||{}).difficulty}`
      新：`YlxwDiffCn=()=>{try{var d;` 后插 `try{d=YlxwServerDiff()}catch(e){}`

==============================================================================
契约（standalone，同 localtest/yl_r218_ext.py / yl_r222_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`（缺省自动探测 PATH 上的 node）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r232-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（含门禁未全绿、往返不一致、node --check 失败）。
  · EDITS 四元组 (label, old, new, n)；n=该处旧串期望命中数=替换次数。
  · gates() 五元组 (name, needle, count, op, note)；_precheck() + 往返自证 + node 自检。
  · 纯客户端；不改 build_v26n.py / chain_build.py / dryrun_087.py / sim_remote_check.py /
    任何 build/assets/* / 其它 yl_*_ext.py（尤其 yl_r218_ext.py / yl_r222_ext.py）；
    不动 r218 的难度表与全部入账点。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*YLXW_R232_V2951*/'
# 接收钩子处另用一个短标记（避免与定义处标记重复 ⇒ 保证「标记唯一」门禁成立）
MARK_C = '/*[r232recv]*/'

# 合法难度集合（与服务端落库口径 easy/normal/hard 逐字对齐）
_YLXW_DIFF_ALLOWED = ('easy', 'normal', 'hard')

# --------------------------------------------------------------------------- A. 定义处追加
# 在 md() 的逗号声明组尾部（R-218 的 YlxwDiffGain 之后、Lm 之前）追加两个模块级函数：
#   YlxwServerDiff()      —— 读模块级缓存（合法值才返回，否则 null）
#   YlxwSrvDiffCapture(j) —— 从 JSON 响应提取顶层 ylDifficulty 并缓存（非法/缺失 → 不动）
A_old = ('return isFinite(m)&&m>0?Math.floor(x*m):x}catch(e){return x}},Lm=')
A_new = (
    'return isFinite(m)&&m>0?Math.floor(x*m):x}catch(e){return x}},'
    + MARK +
    'YlxwServerDiff=()=>{try{var d=window.__ylSrvDiff;'
    'return (d==="easy"||d==="normal"||d==="hard")?d:null}catch(e){return null}},'
    'YlxwSrvDiffCapture=(j)=>{try{if(!j||typeof j!=="object")return;'
    'var d=j.ylDifficulty;'
    'if(d==="easy"||d==="normal"||d==="hard")window.__ylSrvDiff=d}catch(e){}},Lm='
)

# --------------------------------------------------------------------------- B. 优先级改写
# YlxwDiffMul 内 `var d=t;` 之后，把「服务端权威值」插为**第二优先级**
# （显式入参 → 服务端 → 游戏内状态 → localStorage）。
B_old = ('YlxwDiffMul=(t,r)=>{try{var d=t;'
         'if(!d||!Qr.difficulty[d]){try{d=(Be.getState().settings||{}).difficulty}')
B_new = ('YlxwDiffMul=(t,r)=>{try{var d=t;'
         'if(!d||!Qr.difficulty[d]){try{d=YlxwServerDiff()}catch(e){}}'
         'if(!d||!Qr.difficulty[d]){try{d=(Be.getState().settings||{}).difficulty}')

# --------------------------------------------------------------------------- C. 接收钩子
# 读档接口 fetchSave 的响应解析处（整包 JSON r 落地后立即提取 ylDifficulty）。
C_old = 'const r=await t.json();try{var ylGh=t.headers'
C_new = 'const r=await t.json();' + MARK_C + 'YlxwSrvDiffCapture(r);try{var ylGh=t.headers'

# --------------------------------------------------------------------------- D. 显示取值器同步
# R-222 的 YlxwDiffCn()（面板中文名显示，定义在 localtest/yl_r222_ext.py:141-146）与
# YlxwDiffMul 同源读法：「游戏内 store → localStorage」——两者均客户端可控。
# 若不改它：玩家改 localStorage 后**显示**变「困难」，而实际入账走服务端权威值 ⇒
# 出现「界面说困难、收益按普通算」的显示/实际不一致。故把服务端值同样前置。
# ★ 唯一性：本处前缀 `YlxwDiffCn=()=>{try{var d;` 与 YlxwDiffMul 的
#   `YlxwDiffMul=(t,r)=>{try{var d=t;` 不同 ⇒ 各自命中 1 次（B 处锚点带 (t,r)=>{var d=t）。
D_old = ('YlxwDiffCn=()=>{try{var d;'
         'try{d=(Be.getState().settings||{}).difficulty}catch(e){}')
D_new = ('YlxwDiffCn=()=>{try{var d;'
         'try{d=YlxwServerDiff()}catch(e){}'
         'try{d=(Be.getState().settings||{}).difficulty}catch(e){}')

EDITS = [
    ('A 追加以逗号声明组注入 YlxwServerDiff / YlxwSrvDiffCapture + 幂等标记',
     A_old, A_new, 1),
    ('B YlxwDiffMul 前置服务端权威分支（服务端 → 状态 → localStorage）',
     B_old, B_new, 1),
    ('C fetchSave 响应解析处挂接收钩子 YlxwSrvDiffCapture(r)',
     C_old, C_new, 1),
    ('D YlxwDiffCn 前置服务端权威分支（显示与实际同源）',
     D_old, D_new, 1),
]

# --------------------------------------------------------------------------- 冻结门禁（R-218 产物一字未动）
# 五元组语义：(name, needle, count, op, note)；op 恒为 '=='。
# 目的：证明本环**只做「难度从哪来」+ 接收钩子**，R-218 的取值器其余分支 / 难度表 /
#       入账点 / 惩罚项**逐字未动**。
FREEZE = [
    # —— R-218 取值器核心分支（除被本环前置的新分支外，其余必须原样在位）——
    #    注意：状态分支取**带前置判定的唯一串**（YlxwDiffMul 内那一处；YlxwDiffCn 的前置不同）。
    ('冻结·R218 状态取值分支',
     'if(!d||!Qr.difficulty[d]){try{d=(Be.getState().settings||{}).difficulty}', 1),
    #    localStorage 兜底串在 R-218 的 YlxwDiffMul 与 R-222 的 YlxwDiffCn 各一处 ⇒ 恒 2。
    ('冻结·R218/R222 localStorage 兜底分支',
     'localStorage.getItem("xiuxian-game-settings")', 2),
    ('冻结·R218 难度表回退',     'Qr.difficulty[d]||Qr.difficulty.normal',  1),
    ('冻结·R218 恒等兜底',       'if(!(x>0))return x',                      1),
    ('冻结·R218 取整',           'Math.floor(x*m)',                         1),
    # —— 难度表三档倍率（本环不碰）——
    ('冻结·easy 档倍率',         'expMul:1,stoneMul:1}',                    1),
    ('冻结·normal 档倍率',       'expMul:1.5,stoneMul:1.5}',                1),
    ('冻结·hard 档倍率',         'expMul:2,stoneMul:2}',                    1),
    # —— 入账点抽检（本环不碰；证明 R-218 获取侧未被破坏）——
    ('冻结·入账点 YlxwDiffGain 在打坐修为', 'v=YlxwDiffGain(v,"expMul")',   1),
    ('冻结·入账点 YlxwDiffGain 在打坐灵石', '__ylsq=YlxwDiffGain(',         1),
    # —— R-222 新增显示取值器（同区，禁止误删）——
    ('冻结·R222 中文名取值器在位', 'YlxwDiffCn=()=>{',                       1),
    # —— 消耗点冻结（证明本环未触碰任何消费侧）——
    ('冻结·商店刷新花费',        'spiritStones:v.spiritStones-f',           1),
    ('冻结·炼丹花费',            'spiritStones:j.spiritStones-m.cost',      1),
    ('冻结·突破失败惩罚',        'exp:Math.floor(q.exp*.7)',                1),
]


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    g = []
    # 每处 EDITS：新串在位（count=n）+ 旧串清零（count=0）
    for label, old, new, n in EDITS:
        g.append(('%s · 新串在位' % label, new, n, '==', ''))
        g.append(('%s · 旧串清零' % label, old, 0, '==', ''))
    # 幂等标记唯一（定义处主标记 + 接收钩子短标记各一）
    g.append(('定义处幂等标记唯一', MARK, 1, '==', '/*YLXW_R232_V2951*/'))
    g.append(('接收钩子标记唯一', MARK_C, 1, '==', '/*[r232recv]*/'))
    # 新函数在位
    g.append(('新取值器 YlxwServerDiff 在位', 'YlxwServerDiff=()=>{', 1, '==', ''))
    g.append(('新接收器 YlxwSrvDiffCapture 在位', 'YlxwSrvDiffCapture=(j)=>{', 1, '==', ''))
    # 服务端分支必须**前置于**状态分支（强证明优先级）
    g.append(('服务端分支前置（服务端→状态相邻）',
              'try{d=YlxwServerDiff()}catch(e){}}if(!d||!Qr.difficulty[d]){try{d=(Be.getState()',
              1, '==', ''))
    # 接收钩子挂在读档接口
    g.append(('读档接收钩子就位', 'YlxwSrvDiffCapture(r);try{var ylGh=t.headers', 1, '==', ''))
    # D：显示取值器同样前置服务端分支（显示与实际同源，防界面/入账不一致）
    g.append(('显示取值器服务端分支就位',
              'YlxwDiffCn=()=>{try{var d;try{d=YlxwServerDiff()}catch(e){}', 1, '==', ''))
    # 冻结（R-218 产物 + 消耗点）
    for name, needle, cnt in FREEZE:
        g.append((name, needle, cnt, '==', '冻结未动'))
    return g


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert MARK == '/*YLXW_R232_V2951*/', '幂等标记被改动'
    assert MARK_C == '/*[r232recv]*/', '接收钩子标记被改动'
    assert _YLXW_DIFF_ALLOWED == ('easy', 'normal', 'hard'), '难度集合口径被改动'

    for name, old, new, n in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old and new, '%s 锚点不得为空' % name
        assert n >= 1, '%s n 必须 >=1' % name
        # old 不得是 new 的子串（否则「旧串清零」门禁在补丁后仍为 1，破坏幂等判定）
        assert old not in new, '%s old 是 new 的子串，会破坏旧串清零门禁' % name
        # 形态一致性：本环全部为纯 ASCII（无 \uXXXX 转义 / 无字面中文）
        assert all(ord(ch) < 128 for ch in old), '%s old 必须纯 ASCII' % name
        assert all(ord(ch) < 128 for ch in new), '%s new 必须纯 ASCII' % name

    # A：两个新函数必须在同一注入串里，且各自含关键子串
    assert 'YlxwServerDiff=()=>{' in A_new, 'A 缺 YlxwServerDiff 定义'
    assert 'YlxwSrvDiffCapture=(j)=>{' in A_new, 'A 缺 YlxwSrvDiffCapture 定义'
    assert 'window.__ylSrvDiff' in A_new, 'A 缺模块级缓存键'
    assert 'j.ylDifficulty' in A_new, 'A 缺服务端下发字段名 ylDifficulty'
    assert A_new.count('"easy"') >= 2, 'A 缺 easy 合法值守卫'
    assert A_new.count('"normal"') >= 2, 'A 缺 normal 合法值守卫'
    assert A_new.count('"hard"') >= 2, 'A 缺 hard 合法值守卫'
    assert A_new.endswith(',Lm='), 'A 未把注入缝回声明组（缺尾部 ,Lm=）'

    # B：服务端分支必须紧邻并**前置于**状态分支
    assert 'var d=t;if(!d||!Qr.difficulty[d]){try{d=YlxwServerDiff()}catch(e){}}' in B_new, \
        'B 未把服务端分支置于 var d=t 之后'
    assert B_new.index('YlxwServerDiff()') < B_new.index('Be.getState()'), \
        'B 服务端分支未前置于游戏内状态分支'
    assert 'if(!d||!Qr.difficulty[d]){try{d=(Be.getState()' in B_new, \
        'B 改坏了紧随其后的游戏内状态分支'

    # C：钩子必须紧跟读档响应解析（const r=await t.json();）
    assert C_new.startswith('const r=await t.json();' + MARK_C + 'YlxwSrvDiffCapture(r);'), \
        'C 钩子未紧跟读档响应解析'

    # D：显示取值器 YlxwDiffCn 的服务端分支必须前置于其状态分支
    assert 'YlxwDiffCn=()=>{try{var d;try{d=YlxwServerDiff()}catch(e){}' in D_new, \
        'D 未把服务端分支置于 YlxwDiffCn 的 var d; 之后'
    assert D_new.index('YlxwServerDiff()') < D_new.index('Be.getState()'), \
        'D 服务端分支未前置于 YlxwDiffCn 的游戏内状态分支'
    assert 'try{d=(Be.getState().settings||{}).difficulty}catch(e){}' in D_new, \
        'D 改坏了 YlxwDiffCn 紧跟其后的游戏内状态分支'
    # D 锚点必须与 B 锚点不重合（各自前缀唯一，否则会误替换 YlxwDiffMul 那处）
    assert D_old not in B_old and 'YlxwDiffCn=()=>{' not in B_old, \
        'D 锚点与 B 锚点重合（YlxwDiffCn 前缀被 YlxwDiffMul 覆盖）'

    # 注入内容不得含网络 / 定时器原语（接收器只读入参对象，不主动发起请求）
    for _n, _o, nw, _c in EDITS:
        for ban in ('fetch(', 'XMLHttpRequest', 'setInterval(', 'setTimeout('):
            assert ban not in nw, '注入内容不得含 %s' % ban


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
        print('  [WARN] 未找到 node，跳过 node --check（可用 --node 显式指定）')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r232chk-', suffix='.js')
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


def _dump_views(txt0, txt1):
    """打印每处 EDITS 补丁前后的解码视图对照（±90 字符窗口）。"""
    print('  --- EDITS 补丁前后解码视图（±90 字符）---')
    for name, old, new, _n in EDITS:
        i0 = txt0.find(old)
        i1 = txt1.find(new)
        if i0 < 0 or i1 < 0:
            print('    [WARN] %s 未定位到（%d/%d）' % (name, i0, i1))
            continue
        before = txt0[max(0, i0 - 90):i0 + len(old) + 90]
        after = txt1[max(0, i1 - 90):i1 + len(new) + 90]
        print('    · %s' % name)
        print('        前: %s' % before.replace('\n', '\\n'))
        print('        后: %s' % after.replace('\n', '\\n'))


def main() -> int:
    ap = argparse.ArgumentParser(description='R-232 在线收益难度倍率「服务端权威值优先」（客户端 --src 补丁）')
    ap.add_argument('--src', required=True,
                    help='装配产物 js（如 build/assets/index-v2951-20261009.js）')
    ap.add_argument('--node', default=None, help='node 可执行文件（缺省自动探测 PATH）')
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

    # 0) R-218 前置在位检查：本环依赖 R-218 的 YlxwDiffMul 与其注入形态
    if 'YlxwDiffMul=(t,r)=>{try{var d=t;' not in txt0 or '/*YLXW_R218_V2945*/' not in txt0:
        print('[FAIL] 前置 R-218 未在位（缺 YlxwDiffMul / /*YLXW_R218_V2945*/），拒绝写盘')
        return 2

    # 1) 幂等 / 部分补丁态
    st = _classify(txt0)
    if st == 'patched':
        print('[SKIP] source looks already patched（R-232 服务端优先 + 接收钩子已在位）')
        return 3
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 2) 基线碰撞检查：新串不得已在基线出现
    for _name, _old, new, _n in EDITS:
        c = txt0.count(new)
        if c != 0:
            print('[FAIL] 新串已在基线出现 %d 次，拒绝写盘：%s' % (c, new[:60]))
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
        if not good:
            print('  [FAIL] %-44s actual=%d expect %s %d %s'
                  % (label, act, op, exp, note))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  [OK] 门禁全绿（EDITS %d 处；冻结 %d 项）' % (len(EDITS), len(FREEZE)))

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

    # 8) 视图对照
    _dump_views(txt0, out_txt)

    # 9) 改前 .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r232-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r232-', suffix='.tmp')
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
