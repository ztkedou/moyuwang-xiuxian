# -*- coding: utf-8 -*-
r"""
yl_r128_ext.py -- R-128 每日行乐：掷骰注额档位/初始注额对齐 + 灵石翻牌牌桌 3→10 张（客户端 · V28_MODULES 新模块）

台账原文（R-128，逐字）
--------------------------------------------------------------------------
  「掷骰比大小 上限10次。灵石翻牌 10次。每次需求2W灵石，牌子数量扩充到10张，
    大概一半会亏，一半会赚钱。10个档位设置差距都比较大。」

分工边界（数值表 §10「两端同源（farm087 教训）」+ §15 移交清单）
--------------------------------------------------------------------------
  · 服务端权威值（次数/成本/奖池/牌号校验）= srv_patch_r128.py（本模块的姊妹环）；
    客户端随 /api/teahouse/today 的 fun.dice/ fun.card 配置渲染 ⇒ 服务端改常量即全量生效。
  · 本模块只修客户端「写死/回退值」与服务端新值的同源性：
      掷骰初始注额 5000 → 20000（否则首击必吃 400「注额须 20000~20000」）；
      掷骰快捷档从 BetBar 默认 [1000,5000,10000,20000] 改为服务端 minBet 单档
        （1000/5000/10000 三档在新规则下全是非法注额）；
      翻牌回退 pays [4500,1200,0] → 10 档、回退 dailyMax/cost 2/2000 → 10/20000；
      牌桌按钮 [0,1,2].map → pays.map（3 张 → 10 张，牌号「牌 N」自动 1~10）；
      标签「三张牌」→「十张牌」；
      BetBar「（区间 …）」行改 props 感知（props.min/max 优先，回退旧全局常量），
        掷骰传服务端 minBet/maxBet ⇒ 区间行 truthful；茶馆调用一字不动（其旧显示维持原状，
        属 R-053/R-029 面，本环不越界）。
  · 中文一律 \uXXXX 转义（锚点=产物真实字节形态，recon 实证），注入零裸中文。

EV/赔率红线（铁律②，本模块零触碰赔率）
--------------------------------------------------------------------------
  掷骰 大/小 1.95（EV=91/96≈0.9479）、豹子 25（EV=25/36≈0.6944）—— 客户端赔率展示串冻结门禁钉死；
  翻牌 10 档 [0,2000,6000,10000,14000,18000,22000,28000,34000,54000] Σ=188,000，
  EV=18,800/20,000=0.94≤1（对照数值表 §10 逐位）。

接线约束（lead 注意）
--------------------------------------------------------------------------
  · V28_MODULES 追加 ('r128', yl_r128_ext.apply 对应入口/main)；
    ★ 必须排在 ('fun086', …) 之后 —— 本模块锚点全部位于 yl_fun086_ext 注入块内部。
  · 与 R-127（每日一签，YlxwFunSign 组件）/R-053（茶馆）锚点零交集（recon 实证：
    yl_053_ext 冻结针 = 茶馆调用前缀 `…value: funBet`，本模块不改茶馆调用，针保持命中）。
  · gates() 供 dryrun 表收录；`--src <bundle>` 就地原子写回（改前 .bak-r128-<时间戳>）。

★ 移交项（lead 验收件，本模块不改，recon 实证存在旧期望）
--------------------------------------------------------------------------
  1. localtest/e2e_087.py E16-6 断言活服 `pays == [4500, 1200, 0]` ⇒ 0.9.13 沙盒 E2E 前须改新 10 档；
  2. 根目录 _e2e_fun086.py（0.8.6 老脚本）断言 dailyMax=2/cost=2000/3 档/bet 1000 合法/pick 5→400
     ⇒ 新规则下全部反转，勿再跑该老脚本当门禁；
  3. deploy_v28/remote_check_v2810.sh / v2811.sh 断言旧 pays ⇒ 0.9.13 部署件 EXPECT 写新值
     （dice: dailyMax=10 minBet=maxBet=20000 pay=1.95 triplePay=25；card: dailyMax=10 cost=20000
       pays=[0,2000,6000,10000,14000,18000,22000,28000,34000,54000]）。

CLI 契约（照 yl_r126_ext.py）
--------------------------------------------------------------------------
  `--src <bundle>`（必填）就地原子写回；已打过（新 pays 回退串在位）⇒ rc=3 SKIP，不写盘。
  退出码：0=OK / 3=已打过 / 1=数值或门禁 FAIL / 2=锚点或前置 FAIL / 4=形态异常。
"""

import argparse
import os
import shutil
import sys
from datetime import datetime

# ============================================================ 数值表 §10 静态数值
PAYS_NEW = [0, 2000, 6000, 10000, 14000, 18000, 22000, 28000, 34000, 54000]
PAYS_OLD = [4500, 1200, 0]
COST_NEW = 20000
DAILY_CARD_NEW = 10
DAILY_DICE_NEW = 10
BET_NEW = 20000
DICE_PAY = "1.95"    # 不动（铁律②）
DICE_TRIPLE = "25"   # 不动

BAN = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# ============================================================ 锚点（产物真实字节形态，全部 recon 实证 count==1）
# (名字, old, new)
EDITS = [
    # C1 BetBar「（区间 …）」行：props.min/max 优先，回退旧全局常量（茶馆不传 ⇒ 维持旧显示）
    ("C1 区间行 props 感知",
     rb'children: "\uff08\u533a\u95f4 " + YLXW_FUN_MIN_BET + " ~ " + YLXW_FUN_MAX_BET + "\uff09"',
     rb'children: "\uff08\u533a\u95f4 " + (props.min || YLXW_FUN_MIN_BET) + " ~ " + (props.max || YLXW_FUN_MAX_BET) + "\uff09"'),

    # C2 掷骰初始注额 5000 → 20000（服务端 MIN=MAX=20000 下唯一合法值，否则首击 400）
    ("C2 掷骰初始注额",
     rb'var st = O.useState(5000), bet = st[0], setBet = st[1];',
     rb'var st = O.useState(20000), bet = st[0], setBet = st[1];'),

    # C3 掷骰头行 dailyMax 回退 3 → 10
    ("C3 掷骰日次回退",
     rb'var left = YlxwNum(d.left), max = YlxwNum(d.dailyMax) || 3;',
     rb'var left = YlxwNum(d.left), max = YlxwNum(d.dailyMax) || 10;'),

    # C4 掷骰 BetBar 调用：快捷档/区间行改服务端配置单档 20000（1000/5000/10000 已非法）
    ("C4 掷骰注额档",
     rb'e.jsx(YlxwFunBetBar, { label: "\u6ce8\u989d", value: bet, onChange: setBet })',
     rb'e.jsx(YlxwFunBetBar, { label: "\u6ce8\u989d", value: bet, options: [YlxwNum(d.minBet) || 20000], min: YlxwNum(d.minBet) || 20000, max: YlxwNum(d.maxBet) || 20000, onChange: setBet })'),

    # C5 翻牌头行回退 dailyMax 2 → 10 · cost 2000 → 20000
    ("C5 翻牌日次/成本回退",
     rb'var left = YlxwNum(d.left), max = YlxwNum(d.dailyMax) || 2, cost = YlxwNum(d.cost) || 2000;',
     rb'var left = YlxwNum(d.left), max = YlxwNum(d.dailyMax) || 10, cost = YlxwNum(d.cost) || 20000;'),

    # C6 翻牌回退奖池 3 档 → 10 档（两端同源）
    ("C6 翻牌回退奖池",
     rb'var pays = d.pays || [4500, 1200, 0];',
     rb'var pays = d.pays || [0, 2000, 6000, 10000, 14000, 18000, 22000, 28000, 34000, 54000];'),

    # C7 标签「三张牌」→「十张牌」（\u4e09→\u5341，牌桌 10 张）
    ("C7 标签十张牌",
     rb'" \u7075\u77f3 \u00b7 \u4e09\u5f20\u724c "',
     rb'" \u7075\u77f3 \u00b7 \u5341\u5f20\u724c "'),

    # C8 牌桌按钮 [0,1,2].map → pays.map（3 张 → 10 张；按钮文案「牌 N」自动 1~10）
    ("C8 牌桌 10 张",
     rb'children: [0, 1, 2].map(function (i) {',
     rb'children: pays.map(function (x, i) {'),
]

ALREADY = [
    rb'var pays = d.pays || [0, 2000, 6000, 10000, 14000, 18000, 22000, 28000, 34000, 54000];',
]

# 冻结面（本模块不碰、补丁后必须原样在位）
FREEZE = [
    (rb'function YlxwFunCard(props) {', 1, 'fun086 组件定义未动'),
    (rb'function YlxwFunDice(props) {', 1, 'fun086 组件定义未动'),
    (rb'function YlxwFunBetBar(props) {', 1, 'fun086 组件定义未动'),
    (rb'function YlxwFunSign(props) {', 1, 'R-127 域组件未动'),
    (rb'YlxwPost("/fun/card"', 1, '翻牌端点路径未动'),
    (rb'YlxwPost("/fun/dice"', 1, '掷骰端点路径未动'),
    # 赔率展示串（铁律②：赔率不动）
    (rb'"\u5927/\u5c0f \u8d54 1.95 \u00b7 \u8c79\u5b50 \u8d54 25"', 1, '掷骰赔率展示 1.95/25 未动'),
    # 茶馆域（yl_053_ext 冻结针 = 前缀形态；本模块不改茶馆调用）
    (rb'e.jsx(YlxwFunBetBar, { label: "\u6ce8\u989d", value: funBet', 1, '茶馆调用未动（yl_053 冻结针共面）'),
    (rb'options: [YlxwNum(t.minBet) || 500, 5000, 20000, YlxwNum(t.maxBet) || 50000]', 1, '茶馆快捷档未动'),
    # 求签组件体未动（R-127 展示面）
    (rb'e.jsx(YlxwFunSign, { data: fun, reload: c })', 1, '每日一签挂载未动'),
]


def _assert_values():
    """数值表 §10 逐项静态核对（不依赖 bundle）。返回错误列表。"""
    errs = []
    if len(PAYS_NEW) != 10 or len(set(PAYS_NEW)) != 10:
        errs.append('奖池必须 10 个互异档位')
    if sum(PAYS_NEW) != 188000:
        errs.append('Σpays %d != 188000' % sum(PAYS_NEW))
    # EV = 均值/成本 = 18800/20000 = 47/50 = 0.94
    if Fraction_check(sum(PAYS_NEW), len(PAYS_NEW) * COST_NEW) != (47, 50):
        errs.append('翻牌 EV != 0.94')
    win = [x for x in PAYS_NEW if x > COST_NEW]
    lose = [x for x in PAYS_NEW if x < COST_NEW]
    if len(win) != 4 or len(lose) != 6:
        errs.append('赚/亏 = %d/%d，设计 4/6' % (len(win), len(lose)))
    if max(PAYS_NEW) * 10 != COST_NEW * 27:
        errs.append('头奖 != 2.7x 注额')
    if PAYS_OLD != [4500, 1200, 0]:
        errs.append('旧奖池口径与数值表 §10 不符')
    # 掷骰 EV：105/216×1.95 = 91/96 ≈ 0.947917（≤1）；豹子 6/216×25 = 25/36
    if Fraction_check(105 * 195, 216 * 100) != (91, 96):
        errs.append('掷骰大/小 EV != 91/96（赔率必须保持 1.95）')
    if Fraction_check(6 * 25, 216) != (25, 36):
        errs.append('豹子 EV != 25/36（赔率必须保持 25）')
    if DAILY_DICE_NEW != 10 or DAILY_CARD_NEW != 10 or BET_NEW != 20000:
        errs.append('次数/注额口径 != 10/10/20000')
    # 日账（§10/§14）：掷骰注 20 万 → 回 18,200,000/96 = 189,583.33（设计表记 189,583，floor 口径）；
    # 翻牌注 20 万 → 回 188,000；两玩法净 = −2,152,000/96 = −22,416.67（§14 记 −22,417）
    if (91 * 200000) // 96 != 189583:
        errs.append('掷骰日期望回 != 189,583（floor 口径）')
    if (91 * 200000 + 188000 * 96) != 377583 * 96 + 32:
        errs.append('两玩法日期望回合计 != 377,583.33')
    if (91 * 200000 + 188000 * 96) - 400000 * 96 != -2152000:
        errs.append('日净回收 != −22,416.67（§14 记 −22,417）')
    return errs


def Fraction_check(n, d):
    """n/d 约分成最简 (分子, 分母)。"""
    a, b = n, d
    while b:
        a, b = b, a % b
    return (n // a, d // a)


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 表收录。needle 为 ASCII/\\u 转义字节。"""
    gs = []
    for name, old, new in EDITS:
        gs.append(('R128·' + name + ' 新形态', new.decode('ascii'), 1, '==', ''))
        gs.append(('R128·' + name + ' 旧形态清零', old.decode('ascii'), 0, '==', ''))
    for nd, cnt, note in FREEZE:
        gs.append(('冻结·' + note[:22], nd.decode('ascii'), cnt, '==', note))
    return gs


def fail(rc, msg):
    print('[yl_r128_ext] FAIL rc=%d: %s' % (rc, msg))
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True, description='R-128 掷骰注额对齐 + 翻牌牌桌 10 张（--src 就地原子补丁）')
    ap.add_argument('--src', required=True, help='要打补丁的 bundle 文件路径（需已含 yl_fun086_ext 注入块）')
    a = ap.parse_args(argv)

    errs = _assert_values()
    if errs:
        for e in errs:
            print('[yl_r128_ext] 数值断言: ' + e)
        return fail(1, '数值表 §10 逐项核对未过（见上）')

    src = a.src
    if not os.path.isfile(src):
        return fail(2, '文件不存在: %s' % src)

    # 注入串自检：新字节不得含 V28_BAN_PATTERNS、纯 ASCII
    for _, _old, new in EDITS:
        try:
            new_s = new.decode('ascii')
        except UnicodeDecodeError:
            return fail(1, '新串非 ASCII（客户端注入必须 \\uXXXX 转义）')
        for pat in BAN:
            if pat.lower() in new_s.lower():
                return fail(1, '新串含禁用模式 %r' % pat)

    with open(src, 'rb') as f:
        b = f.read()

    c_old = [b.count(old) for _, old, _new in EDITS]
    c_new = [b.count(new) for _, _old, new in EDITS]
    c_al = [b.count(r) for r in ALREADY]
    if max(c_new + c_al) > 1:
        return fail(4, '形态异常：新串计数 >1（new=%s already=%s），拒绝续写' % (c_new, c_al))
    if sum(c_new) == len(EDITS) and sum(c_al) == len(ALREADY):
        print('[yl_r128_ext] ALREADY-PATCHED（8 新形态全在，未写盘）: %s' % src)
        return 3
    if sum(c_new) + sum(c_al) > 0:
        return fail(4, '部分补丁形态（new=%s already=%s），疑似半成品，拒绝续写' % (c_new, c_al))
    if c_old != [1] * len(EDITS):
        return fail(2, '锚点计数不符（期望 %d×1，实得 %s）。文件是否为已含 yl_fun086_ext 注入块的装配产物？src=%s'
                    % (len(EDITS), c_old, src))

    # 前置：冻结面逐位在位
    for nd, cnt, note in FREEZE:
        got = b.count(nd)
        if got != cnt:
            return fail(2, '前置失败：冻结面 %s count=%d（期望 %d）' % (note, got, cnt))

    # 打补丁（8 处，逐处 expect=1）
    patched = b
    for i, (name, old, new) in enumerate(EDITS):
        if patched.count(old) != 1:
            return fail(2, '锚点 %d（%s）中途失配（不应发生）' % (i, name))
        patched = patched.replace(old, new, 1)
    if patched == b:
        return fail(1, '替换未产生变化（不应发生）')

    # 内存自检：门禁全过才写盘
    for name, needle, want, op, _note in gates():
        got = patched.count(needle.encode('ascii'))
        if op == '==' and got != want:
            return fail(1, '门禁自检 FAIL：%s count=%d（期望 %d）' % (name, got, want))

    # 改前 .bak（只在真写盘前落；重跑不覆盖已有备份）
    bak = '%s.bak-r128-%s' % (src, datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(src, bak)

    # 就地原子写回（同卷临时文件 + os.replace，二进制）
    tmp = '%s.tmp-r128' % src
    with open(tmp, 'wb') as f:
        f.write(patched)
    os.replace(tmp, src)

    # 落盘复核（重读现盘字节再验一遍）
    with open(src, 'rb') as f:
        back = f.read()
    if back != patched:
        return fail(1, '落盘复核失败：磁盘字节 != 预期补丁结果')
    for name, needle, want, op, _note in gates():
        got = back.count(needle.encode('ascii'))
        if got != want:
            return fail(1, '落盘门禁 FAIL：%s count=%d（期望 %d）' % (name, got, want))

    print('[yl_r128_ext] OK 已补丁并原子写回: %s' % src)
    print('[yl_r128_ext] 备份: %s' % bak)
    print('[yl_r128_ext] 产物新增 %d 字节（掷骰 4 处 + 翻牌 4 处）' % (len(patched) - len(b)))
    print('[yl_r128_ext] 数值：掷骰 10 次/日×固定 2 万注（EV=0.9479 赔率未动）；翻牌 10 次/日×2 万×10 档 '
          '[0,2000,6000,10000,14000,18000,22000,28000,34000,54000] EV=0.94，赚 4/亏 6，头奖 2.7x')
    print('[yl_r128_ext] 门禁表（供 dryrun 收录）:')
    for g in gates():
        print('    %r' % (g,))
    return 0


if __name__ == '__main__':
    sys.exit(main())
