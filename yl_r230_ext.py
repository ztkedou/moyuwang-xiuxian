# -*- coding: utf-8 -*-
r"""
yl_r230_ext.py — R-230「天地之髓掉落门槛偏高」：与「天地精华」同构化（纯客户端 · apply 模块）

输入产物：build/assets/index-v2949-20261009.js
          （线上 0.9.49；md5 d8fac7c23951a88c739579726823fb2c；2,326,139 B）
本模块**只做 4 处原地字符串替换**，不注入任何 helper（INJECT_JS 有意留空 ⇒ build 侧
`zh('')` 合法、不插入；dryrun 会打一条「无 INJECT_JS」的 WARN，属预期非失败）。

==============================================================================
【需求原文（R-230，台账逐字）】
==============================================================================
  掉落条件 `境界序 >= 化神期(SpiritSevering)`（历练 @1938319 / 额外 @1968636 / 黑市 @1843675 三处），
  但其**炼化门槛是元婴期**、**用途是「进入化神期」**
  ⇒ 等于「**得先成为化神期，才能刷到进入化神期的材料**」，
  与同构的**天地精华**（用途=进入元婴期，掉落门槛=金丹~元婴）**不自洽**。
  ★ 缓解：历练事件池 `hw()` 对进阶物品**未按境界过滤** ⇒ 低境界仍可触发，**不构成硬卡死**。

==============================================================================
【取证一】天地精华的掉落门槛写法（实测逐字 —— 本模块要照抄的「形态」）
==============================================================================
  精华在三处**均为「区间」形态**（下界 = 炼化门槛，上界 = 炼化门槛 + 1 档）：
    ① 历练 `tryGetAdvancedItem`（@1937966，count=1）：
       if(a>=fe.indexOf(ae.GoldenCore)&&a<=fe.indexOf(ae.NascentSoul)){        // 金丹~元婴
    ② 额外奖励（@1968261，该形态全文 count=2，其中 1 处是本条、另 1 处是黑市的 else-if 前缀）：
       if(T>=fe.indexOf(ae.GoldenCore)&&T<=fe.indexOf(ae.NascentSoul)){        // 金丹~元婴
    ③ 黑市 `l1raw`（@1843305，count=1）：
       else if(T>=fe.indexOf(ae.GoldenCore)&&T<=fe.indexOf(ae.NascentSoul)){   // 金丹~元婴
       并随物品带 `minRealm:ae.GoldenCore`（@1843645，= 区间下界）
  ⇒ 精华：炼化门槛 = 金丹期（文案 `炼化天地精华需要达到金丹期` @808066/@1538246），
     掉落区间 = [金丹, 元婴] = [炼化门槛, 炼化门槛 + 1]。

【取证二】天地之髓三处原值（实测逐字 + 偏移）
==============================================================================
    ① 历练 @1938316（条件起）/ @1938322（`fe.indexOf(ae.SpiritSevering)`，count=1）：
       if(a>=fe.indexOf(ae.SpiritSevering)&&Math.random()<.7){                // ≥ 化神期
    ② 额外 @1968636（count=1，锚点须带 `const E=Object.values(on);` 以区分黑市同名串）：
       if(T>=fe.indexOf(ae.SpiritSevering)){const E=Object.values(on);         // ≥ 化神期
    ③ 黑市 @1843675（count=1）：
       else if(T>=fe.indexOf(ae.SpiritSevering)){const $=Object.values(on);    // ≥ 化神期
       并随物品带 `minRealm:ae.SpiritSevering`（@1843986，count=1）
  ⇒ 髓：炼化门槛 = 元婴期（文案 `炼化天地之髓需要达到元婴期` @808180），
     掉落区间 = [化神, ∞) —— 与精华的 [炼化门槛, 炼化门槛 + 1] **不同构**。

==============================================================================
【改法】把髓的三处掉落条件改为与精华**同构**的区间：两个境界常量整体上移一档
==============================================================================
    金丹(GoldenCore) → 元婴(NascentSoul)；元婴(NascentSoul) → 化神(SpiritSevering)：
    ① 历练： if(a>=fe.indexOf(ae.NascentSoul)&&a<=fe.indexOf(ae.SpiritSevering)&&Math.random()<.7){
    ② 额外： if(T>=fe.indexOf(ae.NascentSoul)&&T<=fe.indexOf(ae.SpiritSevering)){const E=Object.values(on);
    ③ 黑市： else if(T>=fe.indexOf(ae.NascentSoul)&&T<=fe.indexOf(ae.SpiritSevering)){const $=Object.values(on);
             + `minRealm:ae.NascentSoul`（镜像精华的 minRealm = 区间下界）
  ⇒ 髓：掉落区间 = [元婴, 化神] = [炼化门槛, 炼化门槛 + 1] —— 与精华**结构逐字同构**。
  ⇒ **未发明新机制**：只改境界常量与一个 minRealm 字段；随机项（`.7`）与物品表（`on`）一字未动。
  ⇒ 三处**必须同改**（漏一处 = 「有的地方能刷到、有的地方不能」）；本模块 4 条 EDITS 全覆盖。

==============================================================================
【同构性自证】`_iso()`：把髓的新形态常量回退一档，须逐字等于精华形态
==============================================================================
  · `_iso(髓·历练阈值) == 精华·历练阈值`、`_iso(髓·额外阈值) == 精华·额外阈值`、
    `_iso(髓·黑市阈值) == 精华·黑市阈值`（`_precheck()` 内断言，失败即 rc=1 不落盘）。
  · `_iso()` 的替换顺序：先 `ae.NascentSoul→ae.GoldenCore`，再 `ae.SpiritSevering→ae.NascentSoul`
    （第一轮产出的 `ae.GoldenCore` 不会被第二轮再动，无自碰撞）。

==============================================================================
【★ 已核对出的「本改法的行为边界」（如实记录，供拍板复核；本模块不擅自扩大改动面）】
==============================================================================
  · 三处均为「独立 if 链」/「else-if 链」，**精华分支在髓分支之前**：
      – 历练 `tryGetAdvancedItem`：精华命中即 `return`，故在 **元婴期** 该路径仍只产出精华（髓不会命中）；
      – 黑市 `l1raw`：`else if` 链，元婴期被精华分支截获（髓不命中）；
      – 额外奖励：三条是**独立 if**（累加 `M=vs(...)`），故元婴期精华与髓**可同时命中** ⇒ 该路径确实新增了元婴期髓。
    ⇒ 结论：本次「下调下界」对**额外路径**立即可见；对**历练/黑市**路径，因精华分支抢跑，
      元婴期不新增髓；且新增的上界（≤化神期）会使**合道/长生期**不再产出髓（与精华「各有窗口」同构）。
  · 真正的主路径（历练事件池 `hw()`→`U0()`）**本来就不按境界过滤**（★ 台账缓解项），
    低境界玩家原本就能触发髓事件 ⇒ 本改法是**对齐三条奖励/商店支路**的结构，不是解开硬锁。

==============================================================================
【不变量冻结】精华 / 规则之力 / 髓的其它出现 / 炼化门槛文案 逐字未动
==============================================================================
  · 精华三处区间条件与 minRealm（4 条冻结门禁，计数按实测：1/2/1/1）；
  · 规则之力两处条件（历练 @1939xxx / 额外，1/1）；
  · `hw()` 事件池的髓分支 `case"heavenEarthMarrow":return U0(t,Object.values(on),`（1）；
  · 髓「炼化门槛」文案 `炼化天地之髓需要达到`（2 处，含 `…元婴期` 1 处）。
  · 汇总型位移门禁：`fe.indexOf(ae.NascentSoul)` 6→9（+3 下界）、`ae.NascentSoul` 38→42（+3 下界 +1 minRealm）、
    `fe.indexOf(ae.SpiritSevering)` 6→6（三处上界为等量替换）、`ae.SpiritSevering` 43→42（−1 仅来自 minRealm）、
    `minRealm:ae.NascentSoul` 3→4、`minRealm:ae.SpiritSevering` 4→3。

==============================================================================
【契约】apply(p, ctx) → gates（与 patches/client/yl_r124_ext.py 同族）
==============================================================================
  · `p` = yl_patch.Patcher（文本已含全部前置 v28 模块）；`ctx = {'zh': zh, 'base_text': str}`。
  · 返回 `list[(name, needle, expected, op, note)]`（op ∈ {'==','>=','<='}）。
  · 无 INJECT_JS；不改 build_v26n.py / chain_build.py / deploy_* / smoke_* / 任何 build/assets/*。
  · `python yl_r230_ext.py [--src ...] [--out ...] [--node ...]` 为**独立自检入口**（默认只读、dry-run）：
    载入 → 应用 → 门禁 → 往返自证 → `node --check`；`--out` 才落盘。
"""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

# 纯替换模块：无注入块（build 侧 zh('') 合法、不插入）。
INJECT_JS = ''

# --------------------------------------------------------------------------- 编辑（纯替换，无注入）

# ① 历练 `tryGetAdvancedItem`：`≥化神期` → `元婴期~化神期`（照精华的区间形态，常量上移一档）
ADV_OLD = 'if(a>=fe.indexOf(ae.SpiritSevering)&&Math.random()<.7){'
ADV_NEW = 'if(a>=fe.indexOf(ae.NascentSoul)&&a<=fe.indexOf(ae.SpiritSevering)&&Math.random()<.7){'

# ② 额外奖励：锚点须带 `const E=Object.values(on);` —— 否则 `if(T>=fe.indexOf(ae.SpiritSevering)){`
#    会与黑市的 `else if(...)` 前缀撞车（基线 count=2，非 1）。
EXT_OLD = 'if(T>=fe.indexOf(ae.SpiritSevering)){const E=Object.values(on);'
EXT_NEW = 'if(T>=fe.indexOf(ae.NascentSoul)&&T<=fe.indexOf(ae.SpiritSevering)){const E=Object.values(on);'

# ③ 黑市 `l1raw`：`else if` 形态 + `const $=Object.values(on);`（`$` 与额外的 `E` 区分）
BLK_OLD = 'else if(T>=fe.indexOf(ae.SpiritSevering)){const $=Object.values(on);'
BLK_NEW = 'else if(T>=fe.indexOf(ae.NascentSoul)&&T<=fe.indexOf(ae.SpiritSevering)){const $=Object.values(on);'

# ④ 黑市·髓物品的 minRealm（= 区间下界；镜像精华的 `minRealm:ae.GoldenCore`）
MR_OLD = 'advancedItemType:"heavenEarthMarrow",minRealm:ae.SpiritSevering}'
MR_NEW = 'advancedItemType:"heavenEarthMarrow",minRealm:ae.NascentSoul}'

EDITS = [
    ('R230-历练·髓掉落区间', ADV_OLD, ADV_NEW, 1),
    ('R230-额外·髓掉落区间', EXT_OLD, EXT_NEW, 1),
    ('R230-黑市·髓掉落区间', BLK_OLD, BLK_NEW, 1),
    ('R230-黑市·髓minRealm', MR_OLD, MR_NEW, 1),
]

# --------------------------------------------------------------------------- 同构自证（精华形态）

# 精华三处「阈值段」（去掉 `if(`/`){`/随机项，只留境界判定本体）——`_iso(髓) == 精华`
ESS_THR_ADV = 'a>=fe.indexOf(ae.GoldenCore)&&a<=fe.indexOf(ae.NascentSoul)'
ESS_THR_EXT = 'T>=fe.indexOf(ae.GoldenCore)&&T<=fe.indexOf(ae.NascentSoul)'
ESS_THR_BLK = 'T>=fe.indexOf(ae.GoldenCore)&&T<=fe.indexOf(ae.NascentSoul)'

# 髓三处「新阈值段」
NEW_THR_ADV = 'a>=fe.indexOf(ae.NascentSoul)&&a<=fe.indexOf(ae.SpiritSevering)'
NEW_THR_EXT = 'T>=fe.indexOf(ae.NascentSoul)&&T<=fe.indexOf(ae.SpiritSevering)'
NEW_THR_BLK = 'T>=fe.indexOf(ae.NascentSoul)&&T<=fe.indexOf(ae.SpiritSevering)'

# --------------------------------------------------------------------------- 冻结锚点（逐字实测）

# 精华（改前改后均应如此）
ESS_ADV = 'if(a>=fe.indexOf(ae.GoldenCore)&&a<=fe.indexOf(ae.NascentSoul)){'
ESS_EXT = 'if(T>=fe.indexOf(ae.GoldenCore)&&T<=fe.indexOf(ae.NascentSoul)){'      # 全文 2（含黑市前缀）
ESS_BLK = 'else if(T>=fe.indexOf(ae.GoldenCore)&&T<=fe.indexOf(ae.NascentSoul)){'
ESS_MR = 'advancedItemType:"heavenEarthEssence",minRealm:ae.GoldenCore}'
# 规则之力
LON_ADV = 'if(a>=fe.indexOf(ae.LongevityRealm)&&Math.random()<.5){'
LON_EXT = 'if(T>=fe.indexOf(ae.LongevityRealm)){'
# 髓：事件池分支（主路径，未按境界过滤 —— 台账缓解项）
MARROW_HW = 'case"heavenEarthMarrow":return U0(t,Object.values(on),'
# 髓：炼化门槛文案（\uXXXX 转义书写保持源纯 ASCII；产物内为字面中文）
MARROW_REFINE = ('\u70bc\u5316\u5929\u5730\u4e4b\u9ad3\u9700\u8981\u8fbe\u5230')      # 炼化天地之髓需要达到
MARROW_REFINE_WARN = ('\u5929\u9053\u8b66\u544a\uff1a\u70bc\u5316\u5929\u5730\u4e4b\u9ad3'
                      '\u9700\u8981\u8fbe\u5230\u5143\u5a74\u671f')                     # 天道警告：炼化天地之髓需要达到元婴期

# --------------------------------------------------------------------------- 汇总型位移门禁（同构的量化指纹；实测：base → after）
#   fe.indexOf(ae.NascentSoul)     6 → 9   （+3：三处新下界；minRealm 是裸 ae.NascentSoul，不在此列）
#   ae.NascentSoul（裸）           38 → 42 （+3 下界 +1 minRealm）
#   fe.indexOf(ae.SpiritSevering)  6 → 6   （三处上界为「等量替换」，总数不变）
#   ae.SpiritSevering（裸）        43 → 42 （−1：仅 minRealm 由化神→元婴）
#   minRealm:ae.NascentSoul          3 → 4
#   minRealm:ae.SpiritSevering       4 → 3
NAS_REF_AFTER = 9
NAS_BARE_AFTER = 42
SPS_REF_AFTER = 6
SPS_BARE_AFTER = 42
MR_NAS_AFTER = 4
MR_SPS_AFTER = 3


def _iso(thr):
    """把「髓·新阈值段」的常量整体回退一档 ⇒ 应逐字等于「精华·阈值段」。"""
    return (thr.replace('ae.NascentSoul', 'ae.GoldenCore')
               .replace('ae.SpiritSevering', 'ae.NascentSoul'))


def _precheck():
    """常量自检（失败 → 抛 AssertionError；apply 会先跑它）。"""
    # 1) 编辑串有效性
    for name, old, new, n in EDITS:
        assert old and new, '%s 锚点不得为空' % name
        assert old != new, '%s 新旧相同（恒等替换）' % name
        assert n == 1, '%s 期望命中数必须为 1' % name
        assert old not in new and new not in old, '%s 新旧互为子串（防 replace 顺序踩空）' % name
        assert all(ord(c) < 128 for c in old), '%s 旧锚点必须纯 ASCII' % name
        assert all(ord(c) < 128 for c in new), '%s 新锚点必须纯 ASCII' % name
    # 2) 新串不得含禁用模式（无注入，但编辑串同样过一遍）
    for _pat in ('fetch(', 'XMLHttpRequest', 'setInterval(', 'setTimeout(',
                 'iframe', 'postMessage', 'X-YL-', 'auth_token'):
        for _n, _o, _w, _c in EDITS:
            assert _pat not in _w, '%s 新串含禁用模式 %s' % (_n, _pat)
    # 3) ★ 同构自证：髓新阈值段回退一档 == 精华阈值段
    assert NEW_THR_ADV in ADV_NEW, '历练新串缺阈值段'
    assert NEW_THR_EXT in EXT_NEW, '额外新串缺阈值段'
    assert NEW_THR_BLK in BLK_NEW, '黑市新串缺阈值段'
    assert _iso(NEW_THR_ADV) == ESS_THR_ADV, '历练阈值与精华不同构'
    assert _iso(NEW_THR_EXT) == ESS_THR_EXT, '额外阈值与精华不同构'
    assert _iso(NEW_THR_BLK) == ESS_THR_BLK, '黑市阈值与精华不同构'
    # 4) 髓新阈值 = 「炼化门槛(元婴) ~ 炼化门槛+1(化神)」= [NascentSoul, SpiritSevering]
    for thr in (NEW_THR_ADV, NEW_THR_EXT, NEW_THR_BLK):
        assert thr.startswith('a>=fe.indexOf(ae.NascentSoul)') or \
               thr.startswith('T>=fe.indexOf(ae.NascentSoul)'), '髓下界须为元婴期'
        assert thr.endswith('<=fe.indexOf(ae.SpiritSevering)'), '髓上界须为化神期'
    # 5) 髓旧形态（≥化神）三处锚点均已覆盖（不得残留）
    for _n, _o, _w, _c in EDITS:
        assert 'ae.NascentSoul' in _w, '%s 新串未含 NascentSoul' % _n
    # 6) minRealm 镜像精华（区间下界）
    assert MR_NEW.endswith('minRealm:ae.NascentSoul}'), 'minRealm 未镜像区间下界'


def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}。返回 gates 列表。"""
    _precheck()
    # 幂等/基线碰撞守卫：新串在基线里必须为 0（防重复应用/与既有文本撞车）
    for name, old, new, exp in EDITS:
        n_new = p.count(new)
        if n_new != 0:
            raise AssertionError('[%s] 新串在基线已出现 %d 次，拒绝替换' % (name, n_new))
    for name, old, new, exp in EDITS:
        p.replace(name, old, new, expect=exp,
                  note='R-230：髓掉落门槛 ≥化神期 → 元婴期~化神期（与天地精华同构）')
    return gates()


def gates():
    """补丁后形态门禁（5 元组 name/needle/expected/op/note）。"""
    g = []
    # ---- 本环 4 处改动：新形态在位 / 旧形态清零 ----
    for label, old, new, n in EDITS:
        g.append(('%s · 新形态在位' % label, new, n, '==', ''))
        g.append(('%s · 旧形态清零' % label, old, 0, '==', ''))
    # ---- 三处掉落条件必须同改（漏一处即「有的地方能刷到、有的地方不能」）----
    g.append(('三处同改·历练', ADV_NEW, 1, '==', '历练 tryGetAdvancedItem'))
    g.append(('三处同改·额外', EXT_NEW, 1, '==', '额外奖励'))
    g.append(('三处同改·黑市', BLK_NEW, 1, '==', '黑市 l1raw'))
    # 旧「≥化神期」掉落条件（三处）在全文中必须为 0
    g.append(('旧≥化神·历练清零', ADV_OLD, 0, '==', ''))
    g.append(('旧≥化神·额外清零', EXT_OLD, 0, '==', ''))
    g.append(('旧≥化神·黑市清零', BLK_OLD, 0, '==', ''))
    # ---- 同构量化指纹：常量引用数位移（实测 base→after）----
    g.append(('同构·NascentSoul 阈值引用 6→9', 'fe.indexOf(ae.NascentSoul)', NAS_REF_AFTER, '==',
              '+3 三处新下界'))
    g.append(('同构·NascentSoul 常量 38→42', 'ae.NascentSoul', NAS_BARE_AFTER, '==',
              '+3 下界 +1 minRealm'))
    g.append(('同构·SpiritSevering 阈值引用 6→6', 'fe.indexOf(ae.SpiritSevering)', SPS_REF_AFTER, '==',
              '三处上界为等量替换，总数不变'))
    g.append(('同构·SpiritSevering 常量 43→42', 'ae.SpiritSevering', SPS_BARE_AFTER, '==',
              '−1 仅来自 minRealm 化神→元婴'))
    g.append(('同构·minRealm 髓 3→4', 'minRealm:ae.NascentSoul', MR_NAS_AFTER, '==',
              '镜像精华 minRealm=区间下界'))
    g.append(('同构·minRealm 旧 4→3', 'minRealm:ae.SpiritSevering', MR_SPS_AFTER, '==', ''))
    # ---- 冻结：天地精华三处区间 + minRealm 逐字未动 ----
    g.append(('冻结·精华·历练区间未动', ESS_ADV, 1, '==', ''))
    g.append(('冻结·精华·额外区间未动', ESS_EXT, 2, '==', '含黑市 else-if 前缀，全文 2'))
    g.append(('冻结·精华·黑市区间未动', ESS_BLK, 1, '==', ''))
    g.append(('冻结·精华·minRealm 未动', ESS_MR, 1, '==', ''))
    # ---- 冻结：规则之力两处条件未动 ----
    g.append(('冻结·规则之力·历练未动', LON_ADV, 1, '==', ''))
    g.append(('冻结·规则之力·额外未动', LON_EXT, 1, '==', ''))
    # ---- 冻结：髓·事件池主路径（未按境界过滤，台账缓解项）未动 ----
    g.append(('冻结·髓·hw 事件池分支未动', MARROW_HW, 1, '==', 'U0() 主路径不受境界过滤'))
    # ---- 冻结：髓·炼化门槛文案（元婴期）未动 ----
    g.append(('冻结·髓·炼化门槛文案未动', MARROW_REFINE, 2, '==', '本模块只改掉落，不动炼化门槛'))
    g.append(('冻结·髓·天道警告文案未动', MARROW_REFINE_WARN, 1, '==', ''))
    return g


# --------------------------------------------------------------------------- 独立自检入口（dry-run）

def _node_bin(explicit=None):
    return explicit or shutil.which('node')


def _node_check(js_text, node_bin):
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check（可用 --node 指定）')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r230chk-', suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
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


def _main(argv):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from yl_patch import Patcher, zh
    ap = argparse.ArgumentParser(description='R-230 天地之髓掉落门槛同构化（自检/dry-run）')
    ap.add_argument('--src', default='build/assets/index-v2949-20261009.js',
                    help='基座产物（默认线上 0.9.49 bundle）')
    ap.add_argument('--out', default=None, help='落盘路径（缺省 = dry-run，不写盘）')
    ap.add_argument('--node', default=None, help='node 可执行文件（缺省自动探测 PATH）')
    a = ap.parse_args(argv)

    if not os.path.exists(a.src):
        print('[FAIL] 源文件不存在: %s' % a.src)
        return 2
    with io.open(a.src, 'rb') as f:
        base = f.read().decode('utf-8')
    print('基座 %s  chars=%d' % (a.src, len(base)))

    p = Patcher(base, label='r230')
    gts = apply(p, {'zh': zh, 'base_text': base})
    out = p.text

    # 门禁
    ok = True
    print('--- 门禁 ---')
    for name, needle, exp, op, note in gts:
        act = out.count(needle)
        good = (act == exp) if op == '==' else (act >= exp if op == '>=' else act <= exp)
        ok = ok and good
        print('  [%s] %-34s actual=%d expect %s %d %s'
              % ('OK' if good else 'FAIL', name, act, op, exp, note))
    print('门禁结果: %s（%d 条）' % ('PASS' if ok else 'FAIL', len(gts)))
    if not ok:
        return 1

    # 往返自证（new→old 必须逐字节还原）
    back = out
    for _n, old, new, _c in reversed(EDITS):
        if back.count(new) != 1:
            print('[FAIL] 往返自证：new 计数 != 1')
            return 1
        back = back.replace(new, old, 1)
    if back != base:
        print('[FAIL] 往返自证不一致（改到了不该改的字节）')
        return 1
    print('  [OK] 往返自证：new→old 后与基座逐字节一致')

    print('  delta = %+d chars' % (len(out) - len(base)))
    if not _node_check(out, _node_bin(a.node)):
        return 1
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with io.open(a.out, 'wb') as f:
            f.write(out.encode('utf-8'))
        print('  已落盘 -> %s' % a.out)
    else:
        print('  (dry-run：未写盘；加 --out 落盘)')
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
