# -*- coding: utf-8 -*-
r"""
dryrun_087.py — 0.8.7 批次客户端**全量门禁预演**（不落盘 build/assets、不碰线上定版）

build_v26n.V28_MODULES 已由 implEventsUi 接线为 25 模块（0.8.2~0.8.6 的 17 个
+ 0.8.7 新增 8 个：grotto087/farm087/xinfa087/t6chardex/adv087/act087/t7sect/t8mentor，
numbal 恒最后）。本脚本直接跑完整 build()：
  · 旧批回归自动包含——每个模块（含就地改的 toast083/eco085/arb/version）的 apply()
    门禁都会在新产物上重跑一遍，FAIL≠0 即拒绝；
  · 另加接线完整性 / 版本四件套一致性 / T5 EV 红线 / T7 403 双计数（可选）。
产物只写 _chainstage/dryrun_087.bundle.js（二进制，防 \r\n 坑）；「预演==交付」
由装配工程师比对 md5：本脚本 md5 == build/assets/index-v288-*.js md5。

用法：
  python localtest/dryrun_087.py
  python localtest/dryrun_087.py --srv-text=srv/index_v28.ts
      # 可选：对服务端产物做 T7 403 双计数（res 形式 22→11 / 对象形式 2→0）。
      # 权威检查归 check_srv_087（implEventsSrv）；此处仅在给定路径时复核，
      # 不给路径则 SKIP（dryrun 阶段服务端链可能尚未重建，不算 FAIL）。
"""
import hashlib
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
# 客户端补丁模块（yl_*_ext.py）已收进 patches/client/（import yl_version_ext 等需要）
sys.path.insert(0, os.path.join(ROOT, 'patches', 'client'))
# 0.9.13 standalone 成员脚本（yl_r116_ext / yl_r118_ext 在 localtest/；append 防抢位 patches/client）
sys.path.append(HERE)

STAGE = os.path.join(ROOT, '_chainstage')
os.makedirs(STAGE, exist_ok=True)

# 0.8.7-build-plan §1.1 定案的最终装配序（numbal 恒最后）
EXPECTED_ORDER = [
    'saveretry', 'arb',
    # 2026-09-30 0.8.12 R-021/R-020：离线窗口锚点 + 灵石日志文案（★ 必须紧跟 arb 之后）
    'offline2',
    'version', 'changelog', 'mail', 'entry', 'sectgf', 'char', 'bond', 'ui',
    'chargift', 'intro', 'flow', 'toast', 'eco', 'dungeon', 'fun086',
    'grotto087',
    # 2026-10-01 第 1 批 R-049：洞府灵草扩地（无硬依赖，紧随 grotto087 便于审阅）
    'r049',
    'farm087', 'xinfa087', 't6chardex', 'adv087', 'act087',
    't7sect', 't8mentor',
    # 2026-09-29 0.8.8 item19：炼器产出补 [境界] 前缀（forge088），恒在 numbal 之前
    'forge088',
    # 2026-09-29 0.8.9 T17/T16/T9：丹炉重构 + 演武场 + 仙途任务活跃度（i3-cli），恒在 numbal 之前
    't17alchemy', 't16arena', 't9quest',
    # 2026-09-29 0.8.9 i3-cli：T7 传承系统重构（逐点使用/分境界效果/分层定价/周限购），恒在 numbal 之前
    't7legacy',
    # 2026-09-29 0.8.9 i4-reward：灵石奖励口径统一（YLReward 纯函数 + 显示端对齐），恒在 numbal 之前
    'reward089',
    # 2026-09-29 0.8.9 i1-cli：T2 灵宠玩法扩展（pet089）+ T5 灵田品种重构（farm089），恒在 numbal 之前
    'pet089', 'farm089',
    # 2026-09-30 0.8.10：三步工作流（修 bug + 待办池 + 查漏补缺）六模块，恒在 numbal 之前
    'v2810a', 'v2810b', 'v2810c', 'v2810d', 'v2810e', 'v2810f', 'v2810g',
    # 2026-09-30 0.8.10 P2：仙务「时光回溯」面板（+ applyRemoteSave 仲裁一次性放行），恒在 numbal 之前
    'v2810h',
    # 2026-09-30 0.8.11：秘境弹窗（cM）显示服务端权威每日次数（复用 dg085 的 status 同步），恒在 numbal 之前
    'v2811a',
    # 2026-09-30 0.8.12：R-016 功法按技能类型分类（gongfa）+ R-012/014/015 角色系统（char2）
    'gongfa', 'char2',
    # 2026-09-30 0.8.12 六模块：R-019① 灵田照料冷却 / R-023 打坐日志 / R-027 日常任务说明
    #   / R-029 茶馆记录 / R-031 抽奖面板 / R-032 秘境每日上限按境界
    'farm2', 'medlog', 'daily', 'fun2', 'lottery', 'dungeon2',
    # 2026-09-30 0.8.13：上游 M-1/M-2 bug 摘取（merge01）
    'merge01',
    # 2026-09-30 0.8.13：R-034/035/036 人物志任务化（renwu）+ R-013 传承石可交易（r013，须晚于 t7legacy）
    'renwu', 'r013',
    # 2026-09-30 0.8.13：R-017/022/024/025/028 数值统一（econ2，须晚于 medlog/toast083/flow083）
    #   + R-018 妖灵培养重设计（r018，须晚于 fun086/v2810e/pet089）
    #   + 0.8.11.1 claimedfix（周里程碑「已领取」显示修复，须晚于 r013c）
    'econ2', 'r013c', 'r024', 'claimedfix', 'r018', 'cooldown', 'r018b', 'r021help', 'r032layout', 'r040', 'r037', 'r037b', 'r041', 'r038', 'r042', 'r043', 'r039', 'r044', 'r045', 'r046', 'r047', 'r048', 'r070', 'r071', 'r073', 'r074', 'r078', 'r082', # 2026-10-01 第 1 批 R 批次四模块（r050 ★须晚于 v2810c / r051 ★须晚于 fun086 /
    #   r052 ★须晚于 claimedfix / r053 ★须晚于 fun2），恒在 numbal 之前
    'r050', 'r051', 'r052', 'r053',
    # 2026-10-01 第 2 批 R 批次五模块（r054/r055/r056 ★须晚于 act087 / r057 无硬依赖 /
    #   r058 ★须晚于 renwu），恒在 numbal 之前
    'r054', 'r055', 'r056', 'r057', 'r058',
    # 2026-10-01 第 3 批 R 批次五模块（r059 ★须晚于 renwu+t6chardex / r060 ★须晚于 renwu /
    #   r061 ★须晚于 t16arena / r062 ★须晚于 eco085+dungeon2 / r063 ★须晚于 dungeon085+dungeon2+v2811a），
    #   恒在 numbal 之前
    'r059', 'r060', 'r061', 'r062', 'r063',
    # 2026-10-01 第 4 批 R 批次五模块（r064 ★须晚于 t17alchemy / r065 无硬依赖 /
    #   r066 ★须晚于 sectgf / r067 ★须晚于 gongfa 且先于 numbal 预算重算 /
    #   r068 ★须晚于 t6chardex），恒在 numbal 之前
    'r064', 'r065', 'r066', 'r067', 'r068', 'r076', 'r077', 'r079', 'r080', 'r081',
    # 2026-10-01 0.9.3 R-083：云端刷新弹窗去掉 + 游戏内 2 处 GitHub 链接改指本仓库
    #   （纯字符串替换、无硬依赖；恒在 numbal 之前）
    'r083',
    # 2026-10-01 0.9.4 寿元体系（自动历练温和化 + 打坐耗命）
    'life094',
    # 2026-10-01 0.9.6 突破奖励 + 每点属性加成
    'bt096',
    # 2026-10-01 0.9.7 属性/寿元/灵根（★ life097 必须排 bt096 之后）
    'attr097', 'life097', 'linggen097',
    # 2026-10-01 0.9.8 天赋/历练/悟道面板/改名（★ talent097 必须排 numbal 之前）
    'speedname097', 'talent097', 'adv097', 'dao097',
    # 2026-10-01 0.9.9 商店刷新 + 人物志解耦
    'shoprefresh101', 'chardex101',
    # 2026-10-01 0.9.10 商店三连 + 历练结束推送（★ advend105 必须排 adv097 之后）
    'shop102', 'advend105',
    # 2026-10-01 0.9.11 R-106~R-109（★ r107 必须排 r106 之后：r106 的冻结断言认 r107 的定稿数值；
    #   ★ r108 必须排 shoprefresh101 之后：它改写 r101 的取费/显示形态）
    'r106', 'r107', 'r108', 'r109',
    # 2026-10-02 0.9.12 链式自动轮次第 2 批 R-111/R-113/R-114/R-115（★ r113 必须排 r056 之后）
    'r111', 'r113', 'r114', 'r115',
    # 2026-10-02 0.9.13 第 1 批接线：R-124 灵田服用预览 spirit→神识（apply 模块，★ 必须排
    #   farm089/speedname097 之后）。同批 R-116/R-118 为成员新契约 standalone --src 脚本，
    #   **不进本表 / 不进 V28_MODULES**——由 build_v26n.__main__ 与本文件对产物按序套用
    #   （build_v26n.STANDALONE_CLIENT），其 gates() 在下方 standalone 段单独重跑。
    'r124',
    # 2026-09-30 0.8.13：★ 冷却机制真 bug 修复 + 历练冷却还原上游原版
    #   （须晚于 flow083 —— 要改它留下的 d(6)/d(4)/d(.4)/d(1)）
    #   ★ 注意：cooldown 已并入上一行（它在真实 V28_MODULES 里位于 r018 与 r018b 之间），
    #     此处**不得重复列出**（重复会让顺序校验解析出错）。
    'numbal',
]
NEW_MODULES = ['grotto087', 'farm087', 'xinfa087', 't6chardex',
               'adv087', 'act087', 't7sect', 't8mentor',
               'forge088',   # 2026-09-29 0.8.8 item19 新增
               't17alchemy', 't16arena', 't9quest',  # 2026-09-29 0.8.9 T17/T16/T9（i3-cli）
               't7legacy',  # 2026-09-29 0.8.9 T7 传承系统重构（i3-cli）
               'reward089',  # 2026-09-29 0.8.9 i4-reward 灵石口径统一
               'pet089', 'farm089',  # 2026-09-29 0.8.9 i1-cli T2 灵宠扩展 / T5 灵田重构
               'v2810a', 'v2810b', 'v2810c', 'v2810d', 'v2810e', 'v2810f', 'v2810g',
               'v2810h',  # 2026-09-30 0.8.10 八模块（七 + P2 时光回溯）
               'v2811a',  # 2026-09-30 0.8.11 秘境弹窗权威次数条
               'offline2',  # 2026-09-30 0.8.12 R-021 离线窗口锚点 / R-020 灵石日志文案
               'gongfa', 'char2',  # 2026-09-30 0.8.12 R-016 功法 / R-012+014+015 角色系统
               'farm2', 'medlog', 'daily', 'fun2', 'lottery', 'dungeon2',  # 2026-09-30 0.8.12 六模块
               'merge01',  # 2026-09-30 0.8.13 上游 M-1/M-2
               'renwu', 'r013',  # 2026-09-30 0.8.13 R-034/035/036 人物志 / R-013 传承石
               'econ2', 'r013c', 'r024', 'claimedfix', 'r018', 'r018b', 'r021help', 'r032layout', 'r040', 'r037', 'r037b', 'r041', 'r038', 'r042', 'r043', 'r039', 'r044', 'r045', 'r046', 'r047', 'r048', 'r070', 'r071', 'r073', 'r074', 'r078', 'r082', 'r049', 'r050', 'r051', 'r052', 'r053',  # 2026-10-01 第 1 批 R 批次五模块
               'r054', 'r055', 'r056', 'r057', 'r058',  # 2026-10-01 第 2 批 R 批次五模块
               'r059', 'r060', 'r061', 'r062', 'r063',  # 2026-10-01 第 3 批 R 批次五模块
               'r064', 'r065', 'r066', 'r067', 'r068', 'r076', 'r077', 'r079', 'r080', 'r081',  # 2026-10-01 第 4 批 R 批次五模块
               'cooldown',  # 2026-09-30 0.8.13 ★ 冷却机制修复 + 历练冷却还原上游原版
               'r106', 'r107', 'r108', 'r109',
               'r111', 'r113', 'r114', 'r115',  # 2026-10-02 0.9.12 R-111 签到 / R-113 万妖五boss / R-114 历练收获 / R-115 洞府灵田
               'r124']  # 2026-10-02 0.9.13 R-124 灵田服用预览 spirit→神识（r116/r118 standalone 不在此表）

VERSION = '0.9.13'
BUNDLE_BASENAME = 'index-v2913-20261002.js'   # 与 build_v26n.OUT / chain_build.CLIENT_OUT / build/index.html 逐字一致
# ★ 升版四件套之外的第 5 处：本文件的 VERSION 必须同步（下方 wiring_checks 用它交叉校验
#   yl_version_ext.DEFAULT_VERSION 与 CHANGELOG 最新条目，两者都对上才算过）。

# ---- T5 EV 红线（数值表-T5T6 §2.3/§2.4 定档，写死；调参只动服务端常量区并回跑验算器）----
HOURLY_MAX = 229788          # floor(17676×13) 长生境时薪（T2T3 §5.3 同源）
JADE_RATE = 2                # r：玉 / 万灵石结算
BIG_BAG = (800, 12)          # 大袋：800 玉 = 12h 时薪
EV_C1_CAP = 9000             # C1 上限（闭环 EV ≤ 0.9；实际 0.689）
TALISMAN_PRICE_H = 1         # 诛妖符价 = 1×境界时薪（h 计）


def ev_checks():
    """T5 EV 红线断言 → [(name, ok, detail)]"""
    out = []
    v_max = HOURLY_MAX * BIG_BAG[1] / BIG_BAG[0]      # 3446.82 灵石/玉（长生大袋）
    c1 = JADE_RATE * v_max                             # 6893.64
    out.append(('EV-C1 灵玉阁闭环 r×v_max <= %d' % EV_C1_CAP,
                c1 <= EV_C1_CAP,
                'r=%d × v_max=%.2f = %.2f（闭环 EV=%.3f）' % (JADE_RATE, v_max, c1, c1 / 10000.0)))
    out.append(('EV-C1 与数值表定值 6893.64 一致',
                abs(c1 - 6893.64) < 0.01,
                '计算值=%.2f' % c1))
    d1_ok = 3 * TALISMAN_PRICE_H >= 2 * 1              # 3h >= 2h（档位增量 2h）→ EV=0.67
    out.append(('EV-D1 诛妖符 3×符价 >= 2×时薪',
                d1_ok,
                '符价=%dh ×3=%dh >= 档位增量 2h（EV=%.2f）' % (TALISMAN_PRICE_H, 3 * TALISMAN_PRICE_H, 2.0 / 3.0)))
    return out


def wiring_checks():
    """接线/版本一致性检查 → (hard_errors, soft_lines)"""
    errs = []
    lines = []
    import build_v26n as B
    import yl_version_ext as V
    # ★ 目录重构后（yl_*_ext.py 已收进 patches/client/）：yl_version_ext 用自身目录
    #   定位 CHANGELOG.md（CHANGELOG_LOCAL），现在会指到 patches/client/ 而落空。
    #   由消费方把它校正回仓库根的 CHANGELOG.md（不改模块内容）。
    V.CHANGELOG_LOCAL = os.path.join(ROOT, 'CHANGELOG.md')

    names = [n for n, _ in B.V28_MODULES]
    if names != EXPECTED_ORDER:
        errs.append('V28_MODULES 顺序 != 定案序：实际=%s' % ' -> '.join(names))
    else:
        lines.append('模块顺序 = %s' % ' -> '.join(names))
    if names and names[-1] != 'numbal':
        errs.append('numbal 必须恒最后，实际末位=%s' % names[-1])
    for n in NEW_MODULES:
        if n not in names:
            errs.append('缺新模块 %s' % n)

    # 版本四件套一致性（bundle 名 + 兜底版本 + CHANGELOG 最新条目）
    base = os.path.basename(B.OUT)
    if base != BUNDLE_BASENAME:
        errs.append('build_v26n.OUT 名 %r != 约定 %r（三处手写必须逐字一致）' % (base, BUNDLE_BASENAME))
    if V.DEFAULT_VERSION != VERSION:
        errs.append('yl_version_ext.DEFAULT_VERSION=%r != %r' % (V.DEFAULT_VERSION, VERSION))
    chg = V.local_changelog_version()
    if chg != VERSION:
        errs.append('CHANGELOG 最新条目=%r != %r（游戏内版本面板取首个 ## [x.y.z]）' % (chg, VERSION))

    idx_html = os.path.join(ROOT, 'build', 'index.html')
    try:
        with open(idx_html, 'rb') as f:
            htxt = f.read().decode('utf-8', 'replace')
        if base not in htxt:
            errs.append('build/index.html 未引用 %s' % base)
        if ('index-v28-20260928.js' in htxt) or ('index-v27-20260928.js' in htxt):
            errs.append('build/index.html 仍残留旧 bundle 名')
    except OSError as e:
        errs.append('读 build/index.html 失败: %s' % e)

    chain_py = os.path.join(HERE, 'chain_build.py')
    try:
        with open(chain_py, 'rb') as f:
            ctxt = f.read().decode('utf-8', 'replace')
        if base not in ctxt:
            errs.append('localtest/chain_build.py 的 CLIENT_OUT 未同步为 %s（implEventsSrv 接线件）' % base)
    except OSError as e:
        errs.append('读 localtest/chain_build.py 失败: %s' % e)

    lines.append('bundle 名 = %s（OUT / index.html / chain_build 三处一致）' % base)
    lines.append('DEFAULT_VERSION=%s  CHANGELOG 最新=%s' % (V.DEFAULT_VERSION, chg))
    return errs, lines


def srv_403_checks(path):
    """T7 403 双计数（--srv-text 给定时才跑）→ [(name, ok, detail)]；基线 22/2 → 改后 11/0"""
    with open(path, 'rb') as f:
        t = f.read().decode('utf-8', 'replace')
    n_res = t.count('res.status(403)')
    n_obj = t.count('status: 403')
    return [
        # 存量守恒（坑 3/14）：后续环可能继续新增 403 响应，故用 >= 而非 ==
        ('SRV·T7 res 形式 403 >= 11', n_res >= 11, '实际=%d（基线 22）' % n_res),
        ('SRV·T7 对象形式 403 == 0', n_obj == 0, '实际=%d（基线 2）' % n_obj),
    ]


def main():
    srv_path = None
    for a in sys.argv[1:]:
        if a.startswith('--srv-text='):
            srv_path = os.path.join(ROOT, a[len('--srv-text='):])

    fails = []

    print('=== 接线 / 版本一致性 ===')
    try:
        errs, lines = wiring_checks()
    except ImportError as e:
        print('[PREFLIGHT-FAIL] 模块导入失败（8 个新模块未集齐？）: %s' % e)
        traceback.print_exc()
        return 2
    for ln in lines:
        print('  ' + ln)
    for e in errs:
        print('  [WIRE-FAIL] %s' % e)
        fails.append(('接线/' + e[:40], '', 0, '==', e))

    print('\n=== T5 EV 红线（数值表-T5T6 定档） ===')
    for name, ok, detail in ev_checks():
        print('  [%s] %-36s %s' % ('OK' if ok else 'FAIL', name, detail))
        if not ok:
            fails.append((name, '', 0, '==', detail))

    print('\n=== build()（25 模块全量，含 0.8.2~0.8.6 回归门禁） ===')
    import build_v26n as B
    from yl_patch import Gates, load_text
    try:
        out, gates = B.build(load_text(B.BASE))
    except Exception:
        print('\n[PREFLIGHT-FAIL] build() 抛异常 —— 锚点大概率被前序模块吃掉:')
        traceback.print_exc()
        return 3

    g = Gates(out)
    for t in gates:
        name, s, expect, cmp, note = t[:5]
        # 可选第 6 元：within=(start_anchor, end_anchor) 限域计数（BLK-A 修针用）
        within = t[5] if len(t) > 5 else None
        g.check(name, s, expect, cmp, note, within=within)
        # ★ Gates.check() 返回 self（不是 bool）——必须读 results[-1][4]
        ok = g.results[-1][4]
        if not ok:
            fails.append((name, s, expect, cmp, note))

    print('门禁: %d 条, FAIL %d 条' % (len(gates), len(fails)))

    if srv_path:
        print('\n=== T7 403 双计数（--srv-text=%s） ===' % os.path.relpath(srv_path, ROOT))
        try:
            for name, ok, detail in srv_403_checks(srv_path):
                print('  [%s] %-36s %s' % ('OK' if ok else 'FAIL', name, detail))
                if not ok:
                    fails.append((name, '', 0, '==', detail))
        except OSError as e:
            print('  [FAIL] 读 srv 文本失败: %s' % e)
            fails.append(('SRV·读文件', '', 0, '==', str(e)))
    else:
        print('\n=== T7 403 双计数：SKIP（未给 --srv-text；权威检查归 check_srv_087） ===')

    print('\n0.8.7 新符号落位自证:')
    probes = [
        'function YlxwTActCenter()', 'YLXW_COMP.events = YlxwTActCenter',
        '"/activity/rank?eventId="', '"/activity/checkin/claim"', '"/activity/shop/exchange"',
        '"/eventboss/status?eventId="', '"/eventboss/strike"', '"/eventboss/talisman"',
        'var YLVERSION_FALLBACK = "0.8.9"',
    ]
    for probe in probes:
        print('  %-46s x%d' % (probe, out.count(probe)))

    stage_path = os.path.join(STAGE, 'dryrun_087.bundle.js')
    with open(stage_path, 'wb') as f:      # ★ 二进制写盘（\r\n 坑）
        f.write(out.encode('utf-8'))

    # ---- 0.9.13 成员新契约：standalone 客户端补丁（R-116/R-118）对预演产物按序套用 ----
    #   与 build_v26n.__main__ 的装配层同一套（build_v26n.STANDALONE_CLIENT / apply_standalone）
    #   ⇒ 预演产物与最终交付产物走完全相同的补丁序列，「预演==交付」md5 逐位可比。
    print('\n=== standalone 补丁套用（R-116/R-118/R-119/R-125/R-126，成员 --src 契约） ===')
    sa_errs = B.apply_standalone(stage_path)
    for _e in sa_errs:
        print('  [SA-FAIL] %s' % _e)
        fails.append(('standalone·套用失败', '', 0, '==', _e))
    # standalone 门禁（各脚本 gates() 五元组）重跑在**补丁后**的最终形态上
    #   2026-10-02 第 2 批接线 +r119/+r125/+r126；第 3 批接线 +r120/+r121/+r123/+r128/+r131
    #   （与 build_v26n.STANDALONE_CLIENT 同名单）
    import yl_r116_ext as _sa_r116
    import yl_r118_ext as _sa_r118
    import yl_r119_ext as _sa_r119
    import yl_r125_ext as _sa_r125
    import yl_r126_ext as _sa_r126
    import yl_r120_ext as _sa_r120
    import yl_r121_ext as _sa_r121
    import yl_r123_ext as _sa_r123
    import yl_r128_ext as _sa_r128
    import yl_r131_ext as _sa_r131
    n_sa_gates = 0
    with open(stage_path, 'rb') as f:
        final_bytes = f.read()
    final_text = final_bytes.decode('utf-8')
    for _tag, _mod in (('r116', _sa_r116), ('r118', _sa_r118),
                       ('r119', _sa_r119), ('r125', _sa_r125), ('r126', _sa_r126),
                       ('r120', _sa_r120), ('r121', _sa_r121), ('r123', _sa_r123),
                       ('r128', _sa_r128), ('r131', _sa_r131)):
        for name, s, expect, cmp, note in _mod.gates():
            n_sa_gates += 1
            act = final_text.count(s)
            ok = (act == expect) if cmp == '==' else (act >= expect)
            print('  [%s] %s' % ('OK' if ok else 'FAIL', name))
            if not ok:
                print('        actual=%d expect %s %d  %s' % (act, cmp, expect, note))
                fails.append((name, s, expect, cmp, note))
    print('standalone 门禁: %d 条（r116~r126/r131 gates()，跑在补丁后形态）' % n_sa_gates)

    md5 = hashlib.md5(final_bytes).hexdigest()
    print('\n预演产物（未上线）: %s' % os.path.relpath(stage_path, ROOT).replace('\\', '/'))
    print('  chars=%d  md5=%s' % (len(final_text), md5))
    print('  「预演==交付」：此 md5 须等于 build/assets/%s 的 md5（两侧已同套 standalone）' % BUNDLE_BASENAME)

    if fails:
        print('\n失败明细 %d 条:' % len(fails))
        for name, s, expect, cmp, note in fails:
            actual = out.count(s) if len(s) > 1 else -1   # 非门禁类（wiring/ev）s 为占位符
            print('  [FAIL] %-36s 期望 %s %s  实际=%d  %s' % (name, cmp, expect, actual, note))
        return 1
    print('\n门禁结果: PASS（FAIL=0）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
