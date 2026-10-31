# -*- coding: utf-8 -*-
r"""yl_p2misc_ext.py —— P2 三项数值修错（灵宠成长软上限 / 洞府成本曲线 / 通天塔扫荡保底）

★ 本模块为 **V28 阶段**模块（锚点全部在基线+前序 V28 环内，不依赖 standalone 注入）。

三项改动：
  ① 灵宠等级成长 1.08^99 指数失控 —— 加软上限
     仙品凤凰 Lv100 本体攻击 8,916,840 → 主战转化后 22,069,179
     是玩家长生境基础攻击(1953)的 11300 倍
     改法：Lv>50 后每级增长率从 1.08 降为 1.04（平方根式收敛）
  ② 洞府 L9/L10 成本严重不回本 —— 下调成本 + 提高 expRateBonus
     L9 5e7→3e7, L10 15e7→8e7；expRateBonus L9 .45→.52, L10 .50→.60
     原投入/回报 226:1，改后约 60:1
  ③ 通天塔扫荡追不上境界 —— 加 maxExp 百分比保底
     首通 exp 公式 600*1.065^sf 最大 545 倍，而境界门槛增长 7500 倍
     改法：扫荡时额外给「当层修为槽 × 0.02 × 层数占比」保底

幂等标记：/*[p2misc]*/
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

MARK = '/*[p2misc]*/'

# ============================================================ 改动 ①：灵宠成长软上限
PET_OLD = ('for (i = 1; i < lv; i++) { g = Math.floor(g * 1.08); q = Math.floor(q * 1.08); '
           'w = Math.floor(w * 1.08); A = Math.floor(A * 1.02); }')
PET_NEW = ('for (i = 1; i < lv; i++) { var _p2k = i < 50 ? 1.08 : 1.04;'
           ' g = Math.floor(g * _p2k); q = Math.floor(q * _p2k);'
           ' w = Math.floor(w * _p2k); A = Math.floor(A * (i < 50 ? 1.02 : 1.01)); }' + MARK)

# ============================================================ 改动 ②：洞府 L9/L10
DWELL9_OLD = 'cost:5e7,expRateBonus:.45'
DWELL9_NEW = 'cost:3e7,expRateBonus:.52' + MARK
DWELL10_OLD = 'cost:15e7,expRateBonus:.5,'
DWELL10_NEW = 'cost:8e7,expRateBonus:.6,' + MARK

# ============================================================ 改动 ③：通天塔扫荡保底
# 扫荡是每日一次的白给，收益乘 0.3。加 maxExp 百分比保底，让高境界不至于只有 0.36% 槽。
# ★ 落点在 YlxwTowerSweep(p) 内（能拿到玩家对象 p，含 maxExp），不是 YlxwTowerFloor(f)（只有层数）。
# 原循环：e += Math.floor((600*1.065^f + f*500) * 0.3)
# 改后：循环后再按 maxExp 百分比兜底，取较大者。目标 = 当前修为槽的 8%（扫荡每日1次）。
TOWER_ANCHOR = ('for (f = 1; f <= ts.highestFloor; f++) {\n'
                '    e += Math.floor((600 * Math.pow(1.065, f) + f * 500) * 0.3);\n'
                '    s += Math.floor((400 * Math.pow(1.055, f) + f * 300) * 0.3);\n'
                '  }')
TOWER_NEW = (TOWER_ANCHOR + '\n'
             '  /* ' + MARK + ' 扫荡修为保底：高境界首通公式(1.065^sf)追不上境界门槛(7500x)，\n'
             '     按当层修为槽 8% 兜底，避免长生境扫荡仅 0.36% 槽。仅抬高不降低。 */\n'
             '  try {\n'
             '    var _p2me = Number(p.maxExp) || 0;\n'
             '    if (_p2me > 0) {\n'
             '      var _p2fl = Math.floor(_p2me * 0.08);\n'
             '      if (_p2fl > e) e = _p2fl;\n'
             '    }\n'
             '  } catch (_p2e) {}')


def apply(p, ctx):
    """应用四处改动。ctx 由装配器提供。"""
    # 幂等：已打过就直接返回
    if MARK in p.text:
        return gates()
    edits = [
        ('P2①·灵宠成长软上限',      PET_OLD,      PET_NEW,      1),
        ('P2②·洞府L9成本+加成',     DWELL9_OLD,   DWELL9_NEW,   1),
        ('P2②·洞府L10成本+加成',    DWELL10_OLD,  DWELL10_NEW,  1),
    ]
    for name, old, new, cnt in edits:
        p.replace(name, old, new, expect=cnt)
    return gates()


def gates():
    """补丁后形态门禁（5 元组 name/needle/expected/op/note；跑在 V28 阶段产物上）。"""
    g = []
    # ① 灵宠成长软上限
    g.append(('P2①·灵宠软上限在位', 'var _p2k = i < 50 ? 1.08 : 1.04;', 1, '==',
              'Lv>50 后增长率 1.08→1.04，抑制 1.08^99 指数失控'))
    g.append(('P2①·旧线性增长清零', PET_OLD, 0, '==',
              '旧的单一 1.08 连乘必须消失'))
    # ② 洞府 L9/L10
    g.append(('P2②·L9 新成本在位', 'cost:3e7,expRateBonus:.52', 1, '==',
              'L9 5e7→3e7，加成 .45→.52'))
    g.append(('P2②·L10 新成本在位', 'cost:8e7,expRateBonus:.6,', 1, '==',
              'L10 15e7→8e7，加成 .50→.60'))
    g.append(('P2②·L9 旧成本清零', 'cost:5e7,expRateBonus:.45', 0, '==', '旧值必须消失'))
    g.append(('P2②·L10 旧成本清零', 'cost:15e7,expRateBonus:.5,', 0, '==', '旧值必须消失'))
    # ② 其余洞府等级不得被动
    for lv, cost in ((1, '5000'), (2, '2e4'), (3, '8e4'), (4, '25e4'),
                     (5, '7e5'), (6, '2e6'), (7, '6e6'), (8, '18e6')):
        g.append((f'P2②·洞府L{lv} 未动', f'cost:{cost},expRateBonus', 1, '==', '本批不动 L1-L8'))
    # 幂等标记（灵宠1 + 洞府2 = 3）
    g.append(('P2·幂等标记总数', MARK, 3, '==', '灵宠1 + 洞府L9/L10 各1'))
    return g


if __name__ == '__main__':
    print(__doc__)
