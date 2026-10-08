# -*- coding: utf-8 -*-
r"""
yl_r136_ext.py — R-136 热修（客户端 standalone · 0.9.15 批次）

需求（用户原话）
--------------------------------------------------------------------------
  「秘境手札中也记录 roguelike 的冷却时间，并且我刚进游戏，怎么普通秘境的
    冷却还有 800 多秒」

拆成两件事：
  A. 秘境手札（YlxwTDungeon）增加「地宫（roguelike）冷却」一行。
  B. 「新开局普通秘境不该有冷却，却显示 800+ 秒」的 BUG。

────────────────────────────────────────────────────────────────────────
A. 做法（本次补丁实现）
--------------------------------------------------------------------------
  手札面板读 YlxwUseList("/dungeon/status")，服务端 dungeonStatusView()
  （srv/index_v28.ts:5111-5146）在同一响应里**已经**返回 roguelike 独立账本：
      rogueCount / rogueCap / rogueRemaining / rogueCdLeftMs / rogueCanEnter
  （[r063] R-063 加的，客户端 YlxwDungeonStatusSync @910930 已在读
    s.rogueCount / s.rogueCdLeftMs —— 契约已存在，只是手札没展示）。
  ⇒ 服务端**返回** roguelike 冷却字段，按需求口径直接用服务端权威值，
    与同面板既有「冷却剩余」行同构（YlxwMin 格式化，>0 才显、否则「无」）。
  YlxwUseList 返回的是 YlxwGet 的原始 JSON（@915309），字段全量可达。

  插入位置：既有「冷却剩余」(t.cdLeftMs) 之后、「可进入」之前。
      OLD: ..."冷却剩余": t.cdLeftMs > 0 ? YlxwMin(t.cdLeftMs) : "无", "可进入": ...
      NEW: ..."冷却剩余": t.cdLeftMs > 0 ? YlxwMin(t.cdLeftMs) : "无",
               "地宫冷却": t.rogueCdLeftMs > 0 ? YlxwMin(t.rogueCdLeftMs) : "无"
               /*YLXW_R136_V2915[r136] roguelike dungeon cooldown row*/,
               "可进入": ...
  服务端未上线该字段时（旧档/降级）t.rogueCdLeftMs===undefined ⇒ undefined>0 为
  false ⇒ 显示「无」，不崩、不误报。

B. 根因结论（★ 服务端环，本补丁**不改**服务端，仅记录，交主控另派）
--------------------------------------------------------------------------
  症状唯一显示点：普通秘境弹窗 cM（@1622241）
      "冷却中，约 "+Math.ceil(YLXW_DGS.cdLeftMs/1000)+" 秒后可再进"
  YLXW_DGS = YlxwDungeonStatusSync() 原样返回的 /dungeon/status（@1620465），
  即客户端**直接展示服务端 cdLeftMs**，本地无任何合并/兜底（YLXW_DG_SRV_CD
  @908486 只写不读，是死变量）。⇒ 800+ 秒 = 服务端 cdLeftMs ≈ 8×10^5 ms。

  服务端算 cdLeftMs 的锚点（srv/index_v28.ts）：
      :5126  cdLeftMs = lastTs != null ? max(0, 900000 - (nowMs - lastTs)) : 0
      :5125  lastTs = row.last_ts（dungeon_tracker.last_ts）
      :5049  DUNGEON_ENTRY_CD_MS = 900_000（15 分钟）
  而 dungeon_tracker.last_ts 有**两个写入者**：
      ① 进入上报 /dungeon/entry（:13606，last_ts=nowMs）—— 本意（真进入）；
      ② 存档差值被动观测 tickDungeonTracker（:7076-7083）——
         只要本次存档相对上次有 Δstatistics.secretRealmCount 或
         Δstatistics.adventureCount（:7088-7090），就 last_ts=nowMs。
  ② 的触发面极宽：**任何历练**都会 x.adventureCount+=1（客户端 @1882462），
  开「自动历练」后每约 6 秒一次（@1897270 冷却注释），离线/挂机结算同理；
  进入地宫(roguelike)也会 +secretRealmCount。⇒ 每次历练都刷新 last_ts，
  于是**从没进过普通秘境**的玩家（含新号刚做完一次历练/自动历练）也会被
  /dungeon/status 判成「刚进入过」⇒ 弹窗恒显「冷却中，约 800+ 秒后可再进」，
  且随每次历练不断回满。这与 5126 行「CD=两次进入最小间隔」的设计语义冲突。

  期望修法（服务端，二选一，主控派环）：
    · 期望值 1（推荐，最小改动）：cdLeftMs 仅在 count>0 时才算，
        :5126 改为  cdLeftMs = (lastTs != null && count > 0)
                              ? max(0, cdMs - (nowMs - lastTs)) : 0
      并同步 :5139 canEnter（count>0 才受 cd 约束）——观测通道写的行 count 恒为 0
      （:7076 VALUES 里 count=0 且 ON CONFLICT 不更新 count），故可精准剔除伪冷却。
    · 期望值 2（更彻底）：tickDungeonTracker 不再写共享列 last_ts（另开
      observe_ts 列或只更 observed/adventure），last_ts 仅由 /dungeon/enter 写。
  客户端侧不建议硬改（会掩盖服务端语义错误，且 count>0 后仍会被观测通道刷回）。

契约（0.9.13 成员 standalone 契约，同 localtest/yl_r131fix_ext.py）
--------------------------------------------------------------------------
  · 命令行只有 --src <装配产物 js>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r136-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；1=断言失败。
  · 纯客户端：服务端 0.9.15 零改动（B 的服务端修法另行派环，不在本文件内）。

门禁（apply 后形态；供 dryrun standalone 门禁表收录重跑）
--------------------------------------------------------------------------
  见 gates()。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# ---- 锚点 / 替换（ASCII 字节字面量；产物把中文存成字面 \uXXXX，故用 br'' 原样匹配；
#      实测 0.9.15 产物 build/assets/index-v2915-20261002.js count==1）----
OLD = (br'"\u51b7\u5374\u5269\u4f59": t.cdLeftMs > 0 ? YlxwMin(t.cdLeftMs) : "\u65e0", '
       br'"\u53ef\u8fdb\u5165"')
NEW = (br'"\u51b7\u5374\u5269\u4f59": t.cdLeftMs > 0 ? YlxwMin(t.cdLeftMs) : "\u65e0", '
       br'"\u5730\u5bab\u51b7\u5374": t.rogueCdLeftMs > 0 ? YlxwMin(t.rogueCdLeftMs) : "\u65e0"'
       br'/*YLXW_R136_V2915[r136] roguelike dungeon cooldown row*/, '
       br'"\u53ef\u8fdb\u5165"')
EDITS = [('R136 手札加「地宫冷却」行', OLD, NEW)]

# ---- 前置/冻结断言串 ----
FR_MARK = b'YLXW_R136_V2915'                                  # 幂等/在位标记（NEW 内 1 处）
FR_ROGUE_CD = b'YlxwMin(t.rogueCdLeftMs)'                     # 新行取值（1 处）
FR_NORM_CD = b'YlxwMin(t.cdLeftMs)'                           # 普通冷却行（冻结不碰）
FR_TITLE = (br'"\u79d8\u5883\u624b\u672d\uff08\u53ea\u8bfb\uff09"')  # 「秘境手札（只读）」
FR_STATUS_API = b'YlxwUseList("/dungeon/status")'             # 手札取数端点
FR_SRV_ROGUE = b's.rogueCdLeftMs'                             # StatusSync 读服务端字段（冻结不碰）
FR_GATE = b'ylDgGate'                                         # 地宫门禁（冻结不碰，12 处）
FR_CD_MS = b'YLXW_DG_CD_MS'                                   # 地宫本地冷却常量（冻结不碰）


# ★ 2026-10-08（0.9.37）新增：退役针机制（照 yl_r120 / yl_r139 / yl_r183 既有实现）。
#   语义：标签含本串的门禁 —— **apply 态跳过**（那时后续补丁还没套用、形态还是旧的），
#   **终态仍检**（期望值写成「全部补丁套用后」的值）。
RETIRED_TAG = '【已退役·终态专用】'


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note）——供 dryrun 门禁表收录。"""
    return [
        ('R136·地宫冷却行在位', NEW.decode('ascii'), 1, '==', ''),
        ('R136·旧单行锚点清零', OLD.decode('ascii'), 0, '==', ''),
        ('R136·在位标记', FR_MARK.decode('ascii'), 1, '==', ''),
        # ★ 2026-10-08（0.9.37 / R-196）：2→4 并打退役标签 —— r203 的 S3b 归一化行
        #   `rogueCdLeftMs: YlxwR196Remain(__cdR, YlxwNum(t.rogueCdLeftMs), t.rogueCdLeftMs)`
        #   自身含 2 处 `t.rogueCdLeftMs` ⇒ apply 态仍是 2、终态才是 4
        #   ⇒ 按本仓口径：**apply 态跳过、终态仍检**（期望写终态值 4，非放松）。
        ('R136·新字段引用数' + RETIRED_TAG, b't.rogueCdLeftMs'.decode('ascii'), 4, '==', '仅新行（判空+取值）+ R-196 归一化 2 处'),
        ('R136·冻结 普通冷却行', FR_NORM_CD.decode('ascii'), 1, '==', '普通秘境冷却语义不碰'),
        ('R136·冻结 手札标题', FR_TITLE.decode('ascii'), 1, '==', 'zh 转义域'),
        ('R136·冻结 status 端点', FR_STATUS_API.decode('ascii'), 1, '==', ''),
        ('R136·冻结 服务端地宫字段读', FR_SRV_ROGUE.decode('ascii'), 1, '==', 'StatusSync 不碰'),
        ('R136·冻结 ylDgGate 门禁', FR_GATE.decode('ascii'), 12, '==', '地宫门禁不碰'),
        ('R136·冻结 地宫冷却常量', FR_CD_MS.decode('ascii'), 2, '==', ''),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert OLD != NEW and OLD not in NEW and NEW not in OLD, '新旧锚点互斥被破坏'
    assert FR_MARK in NEW, '标记常量必须植入 NEW'
    assert FR_ROGUE_CD in NEW, 'NEW 必须含地宫冷却取值'
    assert NEW.count(FR_NORM_CD) == 1, 'NEW 应恰含一处普通冷却取值（原行保留）'
    assert NEW.count(FR_ROGUE_CD) == 1, 'NEW 应恰含一处地宫冷却取值'
    assert NEW.count(b't.rogueCdLeftMs') == 2, 'NEW 应恰含 typeof/取值两处 t.rogueCdLeftMs'
    assert b'/*' in NEW and b'*/' in NEW, 'NEW 内注释形态必须完整'


def main() -> int:
    ap = argparse.ArgumentParser(description='R-136 秘境手札加「地宫冷却」行（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2915-*.js）')
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

    # 1) 幂等：已是补丁后形态 → rc=3 不写盘
    if NEW in src and OLD not in src:
        print('[SKIP] source looks already patched（已含地宫冷却行且旧单行锚点清零）')
        return 3

    # 2) 锚点计数（rc=2 面）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）：%r' % (name, n, old))
            return 2
    if src.count(FR_MARK) != 0:
        print('[FAIL] 标记 %r 已存在 %d 次（期望 0，疑部分补丁态）' % (FR_MARK, src.count(FR_MARK)))
        return 2

    # 3) 应用（字节级单点替换）
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 4) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        if RETIRED_TAG in label:            # ★ 退役针：apply 态跳过（终态由 dryrun 的 standalone 段复核）
            print('  [SKIP] %-26s 已退役（终态复核）' % label.replace(RETIRED_TAG, ''))
            continue
        act = out.decode('utf-8', errors='replace').count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-26s actual=%d expect==%d' % ('OK' if good else 'FAIL', label, act, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 5) 往返自证
    back = out
    for name, old, new in EDITS:
        back = back.replace(new, old, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r136-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r136-', suffix='.tmp')
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
