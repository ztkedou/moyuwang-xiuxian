# -*- coding: utf-8 -*-
r"""
yl_r123_ext.py — R-123「仙途指引/七日礼加码」客户端伴生补丁：指引面板说明文案数字同步（0.9.13 批次）

需求原文（台账 R-123 · 仙途指引）
--------------------------------------------------------------------------
  「仙途指引也是，奖励档位太少，高档位力度太小，越往上难度其实越大，
    但是现在奖励变化太小了。」

为什么要动客户端（ srv_patch_r123.py 之外唯一伴生面，2026-10-02 产物实证）
--------------------------------------------------------------------------
  · 指引/七日礼的**实际奖励数值**由服务端 /api/guide/status 下发（面板每行
    `m.desc · 奖励 m.reward`、`七日第 N 天 · 奖励 m.reward` 均渲染服务端值），
    srv_patch_r123.py 改常量即全生效，客户端零结构改动。
  · 但指引面板的 R79Box 玩法说明**硬编码了旧数字**（build/assets 产物 @1120913
    逐字节实证，玩法说明与文案.md §A #19 明示"R-123 改档位后说明内数字同步"）：
      ① 里程碑：创建角色 500 / 总等级 3 得 800 / … / 结道侣 3000，达标后手动领取、各一次性。
      ② 七日礼：以首次存档日为第 1 天，逐日可领 500 / 800 / 1200 / 1800 / 2500 / 3500 / 5000 灵石，…
    本脚本把两行说明同步为新档（与 srv 新值逐字一致），防「面板发新奖、说明写旧数」。
  · 仅改两条字符串字面量的 ASCII 数字，中文 \uXXXX 转义段一字不动；不动 R79Box
    调用本身，不动「玩法说明」折叠块结构（R-121 文案线冻结面），不动奖励行渲染代码。

锚点侦察（build/assets/index-v2912-20261002.js 逐字实证，2026-10-02）
--------------------------------------------------------------------------
  ①行（364 字节，count==1，@1120913 YlxwTGuide 的 R79Box 内）
  ②行（263 字节，count==1，紧随其后）
  归属保障：'YlxwR79Box("\u4ed9\u9014\u6307\u5f15"' 全产物恰 1 处（指引面板那组）。
  新串改前 count==0（新数字组合为独有信号，铁律⑥）。

契约（0.9.13 批次成员补丁脚本，同 yl_r118 样例）
--------------------------------------------------------------------------
  · 命令行只有 --src <文件>；二进制读写；就地原子写回（同卷临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r123-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 前置依赖：--src 必须是含指引面板（YlxwTGuide + R79Box）的装配产物
    （0.9.12 index-v2912-20261002.js 与 0.9.13 链均满足；面板在基座段，与链上其他环无交集）。

门禁（apply 后形态；供 dryrun 门禁表原样收录）
--------------------------------------------------------------------------
  见 gates()。注：『YlxwR79Box( 调用总数』『\u73a9\u6cd5\u8bf4\u660e 总数』是 R-121
  文案线的活面（其完工后总数会变大），**不做绝对值门禁**，只在 apply 内做
  before==after 稳定性自证（证明本补丁零涟漪）；跨模块漂移由 dryrun 全局表管。
"""

import os
import sys
import argparse
import shutil
from datetime import datetime

# ---- 锚点 / 替换（全部 rb 字面量：\u 保持两字符 backslash+u，与产物字节一致）----
# ① 里程碑行：数字 500/800/1500/2000/800/1500/5000/3000 → 2000/3000/6000/8000/3000/6000/20000/12000
ANC1 = (rb'\u2460 \u91cc\u7a0b\u7891\uff1a\u521b\u5efa\u89d2\u8272 500 / \u603b\u7b49\u7ea7 3 \u5f97 800'
        rb' / \u603b\u7b49\u7ea7 9 \u5f97 1500 / \u603b\u7b49\u7ea7 10 \u5f97 2000 / \u52a0 1 \u4f4d\u597d\u53cb 800'
        rb' / \u62dc\u5e08 1500 / \u603b\u7b49\u7ea7 19 \u5f97 5000 / \u7ed3\u9053\u4fa3 3000\uff0c'
        rb'\u8fbe\u6807\u540e\u624b\u52a8\u9886\u53d6\u3001\u5404\u4e00\u6b21\u6027\u3002')
NEW1 = (rb'\u2460 \u91cc\u7a0b\u7891\uff1a\u521b\u5efa\u89d2\u8272 2000 / \u603b\u7b49\u7ea7 3 \u5f97 3000'
        rb' / \u603b\u7b49\u7ea7 9 \u5f97 6000 / \u603b\u7b49\u7ea7 10 \u5f97 8000 / \u52a0 1 \u4f4d\u597d\u53cb 3000'
        rb' / \u62dc\u5e08 6000 / \u603b\u7b49\u7ea7 19 \u5f97 20000 / \u7ed3\u9053\u4fa3 12000\uff0c'
        rb'\u8fbe\u6807\u540e\u624b\u52a8\u9886\u53d6\u3001\u5404\u4e00\u6b21\u6027\u3002')
# ② 七日礼行：数字 500/800/1200/1800/2500/3500/5000 → 2000/3000/4000/6000/8000/12000/15000
ANC2 = (rb'\u2461 \u4e03\u65e5\u793c\uff1a\u4ee5\u9996\u6b21\u5b58\u6863\u65e5\u4e3a\u7b2c 1 \u5929\uff0c'
        rb'\u9010\u65e5\u53ef\u9886 500 / 800 / 1200 / 1800 / 2500 / 3500 / 5000 \u7075\u77f3\uff0c'
        rb'\u7b2c 7 \u5929\u53e6\u8d60\u79f0\u53f7\u300c\u4e03\u65e5\u7b51\u57fa\u300d\u3002')
NEW2 = (rb'\u2461 \u4e03\u65e5\u793c\uff1a\u4ee5\u9996\u6b21\u5b58\u6863\u65e5\u4e3a\u7b2c 1 \u5929\uff0c'
        rb'\u9010\u65e5\u53ef\u9886 2000 / 3000 / 4000 / 6000 / 8000 / 12000 / 15000 \u7075\u77f3\uff0c'
        rb'\u7b2c 7 \u5929\u53e6\u8d60\u79f0\u53f7\u300c\u4e03\u65e5\u7b51\u57fa\u300d\u3002')

# ---- 归属 / 前置 / 冻结断言串 ----
PRE_PANEL = rb'YlxwR79Box("\u4ed9\u9014\u6307\u5f15"'          # 指引面板那组 R79Box（恰 1）
PRE_REWARD = rb'" \u00b7 \u5956\u52b1 ", m.reward'              # 里程碑行奖励渲染自服务端（恰 1）
PRE_WEEKROW = (rb'"\u4e03\u65e5\u7b7c " + m.day + " \u5929 \u00b7 \u5956\u52b1 " + m.reward')  # 七日行同上（恰 1）
FR_TITLE7 = rb'\u4e03\u65e5\u7b51\u57fa'                        # 「七日筑基」称号串（本补丁不改）
FR_CLAIM = b'/guide/claim'                                      # 领取动作端点（不改）
FR_STATUS = b'/guide/status'                                    # 状态拉取端点（不改）
# 稳定性自证（before==after，不做绝对值门禁——R-121 文案线会合法改变其总数）
STAB_R79BOX = b'YlxwR79Box('
STAB_SHUOMING = rb'\u73a9\u6cd5\u8bf4\u660e'

# V28_BAN_PATTERNS（交接手册 §2.4）：注入串不得含
BAN = [b'iframe', b'postMessage', b'XMLHttpRequest', b'auth_token', b'X-YL-']


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 表收录。"""
    return [
        ('R123·指引①行新数值在位', NEW1.decode('ascii'), 1, '==', '说明文案=服务端新档（Σ60,000）'),
        ('R123·指引①行旧值清零', ANC1.decode('ascii'), 0, '==', '旧 Σ15,100 口径退场'),
        ('R123·七日②行新数值在位', NEW2.decode('ascii'), 1, '==', '说明文案=服务端新档（Σ50,000）'),
        ('R123·七日②行旧值清零', ANC2.decode('ascii'), 0, '==', '旧 Σ15,300 口径退场'),
        ('R123·指引面板R79Box归属', PRE_PANEL.decode('ascii'), 1, '==', '只此一组指引说明，防误伤他面板'),
        ('R123·奖励行渲染自服务端', PRE_REWARD.decode('ascii'), 1, '==', '实际数值随 srv 常量生效（零结构改动证据）'),
        ('R123·七日行渲染自服务端', PRE_WEEKROW.decode('ascii'), 1, '==', '同上'),
        ('R123·七日筑基称号串保留', FR_TITLE7.decode('ascii'), 1, '==', 'day7 称号赠予面不碰'),
        ('R123·领取端点串保留', FR_CLAIM.decode('ascii'), 1, '==', 'guide/claim 动作不碰'),
        ('R123·状态端点串保留', FR_STATUS.decode('ascii'), 1, '==', 'guide/status 拉取不碰'),
    ]


def fail(rc, msg):
    print('[yl_r123_ext] FAIL rc=%d: %s' % (rc, msg))
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True, description='R-123 指引面板说明文案数字同步（--src 就地原子补丁）')
    ap.add_argument('--src', required=True, help='要打补丁的 bundle 文件路径（需含 YlxwTGuide 指引面板）')
    a = ap.parse_args(argv)

    src = a.src
    if not os.path.isfile(src):
        return fail(2, '文件不存在: %s' % src)

    # 新串自检：不含 V28_BAN_PATTERNS、新≠旧（铁律⑥：新串=独有信号）
    for new in (NEW1, NEW2):
        for pat in BAN:
            if pat.lower() in new.lower():
                return fail(1, '新串含禁用模式 %r' % pat)
    if NEW1 == ANC1 or NEW2 == ANC2:
        return fail(1, 'NEW == ANC（配置错误）')

    with open(src, 'rb') as f:
        b = f.read()

    c1o, c1n = b.count(ANC1), b.count(NEW1)
    c2o, c2n = b.count(ANC2), b.count(NEW2)
    if max(c1o, c1n, c2o, c2n) > 1:
        return fail(2, '形态异常：锚点计数 %d/%d/%d/%d（都应 ≤1），拒绝续写' % (c1o, c1n, c2o, c2n))
    if c1n == 1 and c2n == 1 and c1o == 0 and c2o == 0:
        print('[yl_r123_ext] ALREADY-PATCHED（两行新文案已在，未写盘）: %s' % src)
        return 3
    if c1o == 0 and c2o == 0:
        return fail(2, '锚点 count=0/0。文件是否含 YlxwTGuide 指引面板？src=%s' % src)
    if (c1o, c1n, c2o, c2n) != (1, 0, 1, 0):
        return fail(2, '半补丁形态：①%d/%d ②%d/%d（期望 旧1/新0 成对），拒绝续写' % (c1o, c1n, c2o, c2n))
    # 此处必为两锚各恰 1 且新串 0：正常补丁路径

    # 前置：面板归属 + 奖励行渲染自服务端 + 冻结串计数（否则补丁后口径不可信）
    for nm, nd, want in (('指引面板R79Box', PRE_PANEL, 1), ('里程碑奖励行', PRE_REWARD, 1),
                         ('七日行', PRE_WEEKROW, 1), ('七日筑基称号串', FR_TITLE7, 1),
                         ('guide/claim', FR_CLAIM, 1), ('guide/status', FR_STATUS, 1)):
        got = b.count(nd)
        if got != want:
            return fail(2, '前置失败：%s count=%d（期望 %d）' % (nm, got, want))
    # 稳定性基线（before）
    base_r79, base_sm = b.count(STAB_R79BOX), b.count(STAB_SHUOMING)

    patched = b.replace(ANC1, NEW1, 1).replace(ANC2, NEW2, 1)
    if patched == b:
        return fail(1, '替换未产生变化（不应发生）')

    # 内存自检：导出门禁全过 + 稳定性 before==after 才写盘
    for name, needle, want, op, _note in gates():
        got = patched.count(needle.encode('ascii'))
        if op == '==' and got != want:
            return fail(1, '门禁自检 FAIL：%s count=%d（期望 %d）' % (name, got, want))
    if patched.count(STAB_R79BOX) != base_r79 or patched.count(STAB_SHUOMING) != base_sm:
        return fail(1, '稳定性 FAIL：R79Box/玩法说明 总数被本补丁改变（不应发生）')

    # 改前 .bak（只在真写盘前落）
    bak = '%s.bak-r123-%s' % (src, datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(src, bak)

    # 就地原子写回（同卷临时文件 + os.replace）
    tmp = '%s.tmp-r123' % src
    with open(tmp, 'wb') as f:
        f.write(patched)
    os.replace(tmp, src)

    # 落盘复核（重读现盘字节再验一遍 + 往返还原自证）
    with open(src, 'rb') as f:
        back = f.read()
    if back != patched:
        return fail(1, '落盘复核失败：磁盘字节 != 预期补丁结果')
    rev = back.replace(NEW1, ANC1, 1).replace(NEW2, ANC2, 1)
    if rev != b:
        return fail(1, 'round-trip 失败：新→旧还原 != 补丁前字节')
    for name, needle, want, op, _note in gates():
        got = back.count(needle.encode('ascii'))
        if got != want:
            return fail(1, '落盘门禁 FAIL：%s count=%d（期望 %d）' % (name, got, want))

    print('[yl_r123_ext] OK 已补丁并原子写回: %s' % src)
    print('[yl_r123_ext] 备份: %s' % bak)
    print('[yl_r123_ext] 产物新增 %d 字节（① %+d / ② %+d）'
          % (len(patched) - len(b), len(NEW1) - len(ANC1), len(NEW2) - len(ANC2)))
    print('[yl_r123_ext] 门禁表（供 dryrun 收录）:')
    for g in gates():
        print('    %r' % (g,))
    return 0


if __name__ == '__main__':
    sys.exit(main())
