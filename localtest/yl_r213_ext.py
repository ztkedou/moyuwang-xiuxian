# -*- coding: utf-8 -*-
r"""
yl_r213_ext.py — R-209 在线人数改「我们服务器自己的口径」（与在线人物名单同源）

需求原文（台账 R-209，2026-10-09 用户报）
--------------------------------------------------------------------------
  「yl 显示的在线 3，但是点开之后只能看到我自己，其他在线玩家看不到」

==============================================================================
一、根因（本次线上取证，2026-10-09 10:0x）
==============================================================================

【1】头部徽标「在线 N」的来源 = **外部第三方 partykit 服务器**：
       const Xy=()=>"https://xiuxian-game-party.dnzzk2.partykit.dev/";const g4=Xy();
     该地址写死在上游仓库（`_upstream-xiuxian/.env.production:VITE_PARTYKIT_HOST`、
     `hooks/useParty.ts:16`、`partykit.json:name=xiuxian-game-party`）⇒ 我们 fork 时原样继承。
     ⇒ 房间 "global" 的 `onlineCount` = **该 partykit app 的全部连接数**
       （含上游作者部署 + 其它 fork 的玩家），**与我们站点的玩家无关**。

【2】「在线人物」面板名单的来源 = **我们自己的服务端**：
       GET /api/online/players  → 双源 UNION（active_sessions.last_seen ∪ saves.updated_at），
       窗口 ONLINE_WINDOW_MS = 5 分钟。见 srv/index_v28.ts:10992。

【3】线上实测（Azure 104.208.x.x，database.sqlite）：
       · active_sessions 9 行，除 uid=13 外全部 1~6 天前的僵尸行
       · saves 近 5 分钟有存档 = 1 行
       · 复刻 /api/online/players 查询 = **1 人**（uid=13 Fipken，心跳 0s）
       · 而头部徽标显示 **3**
     ⇒ **面板是对的，头部那个 3 是错的**（它数的是别人的服务器）。

【4】历史成因：`yl_r144_ext.py` 的 docstring 自己写明是「刻意取舍」——
     「header『在线 N』仍取 party 实时值 Dr（与徽章同源），名单人数取服务端 players.length」。
     本补丁即把该取舍**取消**：让 Dr 也来自我们自己的服务端。

==============================================================================
二、改动（3 处锚点，全部 count==1、纯 ASCII）
==============================================================================

  E1【在线人数的新来源】在 party hook 的模块级状态声明之后，追加「我方口径」的实现：
       let Gr=null,Li=[],Lr=[],Dr=0;
       → 原样 + INJECT（YLOnlCur / YLOnlSet / YLOnlTick + 2s 首拉 + 20s 轮询）

     · 复用既有鉴权封装 `YlxwGet`（模块级 function 声明 @917571 → 提升，可安全引用）。
       ★ 安全性：`Xc` 在**无 token 时直接 throw "Not authenticated"、根本不发请求**；
         401 先 `pS()` 静默续期重试一次。⇒ 未登录时轮询不会把玩家踢下线（已被 catch 吞掉）。
     · 端点与「在线人物」面板**完全相同**（`/online/players`），保证两个数字同源。
     · 轮询 20s ≪ 服务端 rateLimit 60/min，安全。

  E2【掐掉 party 的写入点】party 的 onmessage 有两个分支会写 Dr：
       Dr=l.onlineCount,Lr.forEach(c=>c(Dr))):l.type==="welcome"?(Dr=l.onlineCount||0,
       → Dr=YLOnlCur,Lr.forEach(c=>c(Dr))):l.type==="welcome"?(Dr=YLOnlCur,
     ★ 只改「写 Dr 的值」，**不动** Li（welcome/聊天消息）与 sendMessage ⇒ 世界聊天功能零影响。

  E3【清理分支不再清零】socket 释放时原会把 Dr 归零：
       Gr.close(),Gr=null,Dr=0  →  Gr.close(),Gr=null
     （Dr 由我方轮询维持；归零会在「订阅者全部卸载后再挂载」时闪一个 0）

  ★ 不改：服务端（一行未动）、party 连接与聊天、R-144 面板本体、存档、战斗。
  ★ 效果：头部徽标、「在线人物」面板标题的「在线 N」、面板名单人数 **三者恒等**。

==============================================================================
三、契约（standalone，同 localtest/yl_r143_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r213-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言失败；1=其他错误。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
  · 纯客户端；不改 build_v26n.py / dryrun_087.py / build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 锚点（字符级实测 count==1、纯 ASCII）

# E1：party hook 的模块级状态声明（唯一）
A1 = 'let Gr=null,Li=[],Lr=[],Dr=0;'

# E1 注入块：我方在线口径（纯 ASCII）
INJECT = (
    '/*YLXW_R213_V2943*/var YLOnlCur=0;'
    'function YLOnlSet(n){n=Number(n);if(!isFinite(n)||n<0)n=0;n=Math.floor(n);'
    'YLOnlCur=n;if(n!==Dr){Dr=n;try{Lr.forEach(function(c){try{c(n)}catch(e){}})}catch(e){}}}'
    'function YLOnlTick(){try{if(typeof YlxwGet!=="function")return;'
    'YlxwGet("/online/players").then(function(d){var n=null;'
    'if(d&&d.players&&typeof d.players.length==="number")n=d.players.length;'
    'else if(d&&typeof d.total==="number")n=d.total;'
    'if(n===null)return;YLOnlSet(n)}).catch(function(){})}catch(e){}}'
    'setTimeout(YLOnlTick,2000);setInterval(YLOnlTick,20000);'
)

# E2：party onmessage 里两个写 Dr 的分支（一段连续文本，一次替换覆盖两处）
A2 = ('Dr=l.onlineCount,Lr.forEach(c=>c(Dr))):l.type==="welcome"?(Dr=l.onlineCount||0,')
N2 = ('Dr=YLOnlCur,Lr.forEach(c=>c(Dr))):l.type==="welcome"?(Dr=YLOnlCur,')

# E3：socket 释放分支（不再把 Dr 归零）
A3 = 'Gr.close(),Gr=null,Dr=0'
N3 = 'Gr.close(),Gr=null'

EDITS = [
    ('R209 在线人数改为我方口径（party 声明后注入）', A1, A1 + INJECT),
    ('R209 掐掉 party 的两个 Dr 写入点', A2, N2),
    ('R209 释放分支不再清零 Dr', A3, N3),
]

# --------------------------------------------------------------------------- 在位标记 / 新增 needle / 冻结门禁串

MARK = 'YLXW_R213_V2943'   # 全局唯一

M_SET_FN = 'function YLOnlSet(n){'
M_TICK_FN = 'function YLOnlTick(){'
M_INTERVAL = 'setInterval(YLOnlTick,20000);'
M_GET = 'YlxwGet("/online/players")'
M_GUARD = 'if(n===null)return;'   # 无效响应（缺 players 且缺 total）不采纳，保持上一次值

# 冻结：party 主机（不得改动 —— 世界聊天仍在用）
FRZ_PARTY_HOST = 'const g4=Xy();'
# 冻结：鉴权封装（不得改动）
FRZ_YLXWGET = 'function YlxwGet(r) { return YlxwApi(r); }'
# 冻结：R-144 面板本体（不得改动）
FRZ_R144 = 'YLXW_R144_V2919'
# 冻结：徽标锚点（不得改动）
FRZ_BADGE = 'title:"当前在线人数"'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    return [
        ('R209·在位标记存在', MARK, 1, '==', 'YLXW_R213_V2943'),
        ('R209·YLOnlSet 已注入', M_SET_FN, 1, '==', ''),
        ('R209·YLOnlTick 已注入', M_TICK_FN, 1, '==', ''),
        ('R209·轮询已挂上', M_INTERVAL, 1, '==', '20s'),
        ('R209·无效响应守卫', M_GUARD, 1, '==', '端点异常时保持上一次值'),
        ('R209·party 写 Dr 的两处已清零', 'Dr=l.onlineCount', 0, '==', '必须为 0'),
        ('R209·改为读我方口径', 'Dr=YLOnlCur', 2, '==', '两个分支各一处'),
        ('R209·释放分支不再清零', A3, 0, '==', '必须为 0'),
        ('R209·锚点 A1 原样保留', A1, 1, '==', ''),
        ('R209·在线端点两处同源', M_GET, 2, '==', 'R-144 面板 1 + 本补丁 1'),
        ('冻结·party 主机未动', FRZ_PARTY_HOST, 1, '==', '世界聊天仍在用'),
        ('冻结·鉴权封装未动', FRZ_YLXWGET, 1, '==', ''),
        ('冻结·R-144 面板未动', FRZ_R144, 1, '==', ''),
        ('冻结·徽标锚点未动', FRZ_BADGE, 1, '==', ''),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert all(ord(ch) < 128 for ch in old), '%s old 必须纯 ASCII' % name
        assert all(ord(ch) < 128 for ch in new), '%s new 必须纯 ASCII' % name
    # E1 必须是 append 型（old 为 new 前缀）
    assert (A1 + INJECT).startswith(A1), 'E1 必须为 append 型'
    # 新增 needle 必须落在补丁后文本内、且不在原锚点内
    assert MARK in INJECT and M_SET_FN in INJECT and M_TICK_FN in INJECT and M_INTERVAL in INJECT
    assert M_GUARD in INJECT, '必须含无效响应守卫'
    assert MARK not in A1 and M_SET_FN not in A1 and M_TICK_FN not in A1
    assert M_GET not in A1 and M_GET not in A2 and M_GET not in A3
    # E2 必须恰好把两处 Dr=l.onlineCount 都换掉
    assert A2.count('Dr=l.onlineCount') == 2, 'A2 必须含两处 Dr=l.onlineCount'
    assert N2.count('Dr=YLOnlCur') == 2, 'N2 必须含两处 Dr=YLOnlCur'
    assert 'Dr=l.onlineCount' not in N2
    # E2 不得动 Li / 聊天
    assert 'Li.forEach' not in A2 and 'Li.forEach' not in N2, 'E2 不得触碰 Li（聊天）'
    # 注入块不得引入其它网络/存储原语（BAN 面）
    for _n, _o, nw in EDITS:
        for ban in ('fetch(', 'localStorage', 'XMLHttpRequest', 'iframe', 'postMessage'):
            assert ban not in nw, '注入内容不得含 %s' % ban
    # 注入块只允许一处 YlxwGet 调用
    assert INJECT.count('YlxwGet(') == 1


def main() -> int:
    ap = argparse.ArgumentParser(description='R-209 在线人数改我方口径（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2942-*.js）')
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
    if MARK in txt0:
        if all(txt0.count(o) == 0 for _n, o, _w in EDITS if o != A1) and M_INTERVAL in txt0:
            print('[SKIP] source looks already patched（R-209 已在位）')
            return 3
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 2) 基线碰撞检查（新标识符必须 0 次）
    for ident in ('YLOnlCur', 'YLOnlSet', 'YLOnlTick', MARK):
        c = txt0.count(ident)
        if c != 0:
            print('[FAIL] 新标识符 %s 已在基线出现 %d 次（疑碰撞），拒绝写盘' % (ident, c))
            return 2

    # 3) 锚点计数（rc=2 面）
    for name, old, _new in EDITS:
        n = txt0.count(old)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）' % (name, n))
            return 2

    # 4) 应用（逐条单点替换）
    out_txt = txt0
    for name, old, new in EDITS:
        out_txt = out_txt.replace(old, new, 1)
    out = out_txt.encode('utf-8')

    # 5) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-34s actual=%d expect %s %d' % ('OK' if good else 'FAIL', label, act, op, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 6) 往返自证：按逆序把 new 换回 old，必须与源逐字节相同
    back = out_txt
    for _name, old, new in reversed(EDITS):
        assert back.count(new) == 1, '往返自证：new 在产物中不唯一'
        back = back.replace(new, old, 1)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 7) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r213-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r213-', suffix='.tmp')
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
