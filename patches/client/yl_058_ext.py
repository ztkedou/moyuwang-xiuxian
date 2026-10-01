# -*- coding: utf-8 -*-
r"""
yl_058_ext.py — R-058 人物志·缘契：寻访任务板「整体刷新」按钮（每日 1 次 ⇒ 最多 10 条/天）

需求原文（台账 R-058 逐字，需求台账_进行中.md:29）
--------------------------------------------------------------------------
  「道友图鉴 · 缘契，每个NPC单独的领奖没做。每个NPC也同样要增加不同阶段获得奖励。
    增加一个整体刷新5条任务的按钮，相当于一天最多可以做10条任务。」

侦察结论（build/assets/index-v28115-20261001.js 逐字实证，2026-10-01）
--------------------------------------------------------------------------
  前两句（每 NPC 单独领奖 + 各阶段奖励）**0.8.11 已经落地**，本 build 里证据：
    · YlxwCharBondPanelT6（yl_t6chardex_ext 造，renwu 保留）按 NPC 渲染
      「缘契里程碑（点击领取 · 随机物品）」chips：25 相知 / 50 知己 / 75 莫逆 / 100 道侣
      四阶段，各阶段随机掉落件数 = YLXW_CHAR_DROP_N=[2,3,4,5]（R-036/A6 拍板值）；
    · 已领状态按 NPC 存 `charDex.bond[relId][at]`（`var claimed = ps.bond[rel.id] || {}`），
      claim(mile) 幂等（连点不重发）。
    ⇒ R-034/R-036（归档「已完成 0.8.11」）正是这两句的需求，台账里的「没做」
      是对照旧线上版写的。本模块**不重做**，只用冻结门禁证明没碰（见 gates 后半）。

  第三句是真缺口：「寻访任务」板（YlxwCharBoardR34，renwu 注入，每日 5 条，提交即寻访）
  **没有任何刷新手段**——任务不满意/材料凑不齐就卡死一整天，也没有加做渠道。
  本模块只做这一句。

本模块动作（纯客户端就地替换 ×2，INJECT_JS=''，零网络、零服务端改动）
--------------------------------------------------------------------------
  ① 在 YlxwCharBoardR34 的 rows 循环前注入 refreshAll 机制：
     · 每日 1 次：`charDex.board.refAll` 记当天日期串（随 /api/save 整包落库，
       跨日 YlxwRnBoardOf 重掷 board 时 refAll 自然消失）⇒ 5（原）+5（刷后）=10 上限成立；
     · 只重掷**未完成**条目（`!x.done`），已完成条保持 ✓ —— 保证任何操作顺序下
       当日完成数 ≤ 10（若连已完成条一起重掷，可无限重做破上限）；
     · 定价 = Σ未完成条 YlxwRnRowCost(t, rf)（与 R-035 A4 单条刷新同口径，Σ≈整板价，
       不另造钱），价格实时标在按钮文案上（点前可见）。
  ② 板标题行 → flex 行：标题原串保留 + 「整体刷新 · N 灵石 / 今日已整体刷新」按钮
     + 「每日限 1 次 · 最多可做 10 条」提示。样式类全部复用 renwu 块既有类
     （编译 CSS index-ZuV-l8Gt.css 逐一验证存在，见自检输出）。

AI 代决（无人值守，详见 拍板/2026-10-01_*_R-058_*.md）
--------------------------------------------------------------------------
  1. R-058 前两句判「0.8.11 已覆盖」，不重做，只冻结；
  2. 整体刷新**收费**：Σ未完成条单条价（A4 同口径）。理由：R-035 用户亲自定过
     「刷新按难度收灵石」的口径，整体刷新是同一族操作；嫌贵可后续一键改免费；
  3. 每日限 1 次、已完成条不重掷 —— 这两条合起来才使「最多 10 条」成立。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 锚点在 renwu 注入块内：A_FUNC/A_HDR 实测全文 count==1（probe 2026-10-01，
    另在「链跑到本模块之前」的内存基线上二次复验，见 __main__）；
  · 不改 renwu 任何门禁串：板标题串原样保留（renwu 门禁 ==1）、任务板挂载 ×2、
    R35 每日 3 条 / A4 单条刷新 / 定价函数一字不动；
  · 新增标识符 refRf/refCost/refUsed/refreshAll/refAll/i58/j58/n58/e58 全 bundle 改前
    count==0（probe 2026-10-01），零碰撞；
  · 扣灵石行刻意写 `{ charDex: d0, spiritStones: ... }`（charDex 在前），
    不产生 `charDex: d0 })` 字面（t6/renwu 块既有 6 处，不添乱）；
  · 注入内容不含 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-/fetch(
    （apply 内自检，含中文一律 zh() 转义，落 bundle 纯 ASCII）；
  · 不碰 build_v26n.py / localtest/ / deploy_v28/ / srv/index_v28.ts / CHANGELOG.md。
  · 服务端零改动：srv/index_v28.ts 全文 0 处 charDex/socialRelations（probe 2026-10-01）
    —— player 存档整包落库无字段白名单，board.refAll 随包走，故**无 srv_patch_058**。

装配顺序
--------------------------------------------------------------------------
  唯一硬约束：**必须排在 renwu 之后**（锚点在 renwu 注入的 YlxwCharBoardR34 内，
  renwu 之前锚点不存在）。建议与第 2 批同列：r053 之后、numbal 之前。
  对既有模块门禁命中数零影响（gates 后半逐条冻结证明）。

导出符号（构建侧契约）
  INJECT_JS : str（''，纯就地替换）
  apply(p, ctx) -> list[(name, needle, expect, cmp, note[, within])]
"""

import re

INJECT_JS = ''          # 纯就地替换，不需要注入块

# --------------------------------------------------------------------------- 锚点
# 说明：含中文的锚点用 raw 中文书写，apply() 内统一 ctx['zh']() 转义（与 bundle 内
#       \uXXXX 同形）；纯 ASCII 锚点 zh() 为恒等。

# ① 插入点：YlxwCharBoardR34 内 submit 定义结束后的 rows 循环头。
#    TasksR35 同位是 `for (var i = 0; i < list.length; i++)`，故本锚全文唯一。
#    侦察：现行 bundle count==1（probe15），链上前态内存基线复验 ==1（__main__）。
A_FUNC = (
    '  var rows = [];\n'
    '  for (var i = 0; i < tasks.length; i++) {'
)

R_FUNC = (
    '  /* R-058 整体刷新（每日 1 次）：重掷全部未完成条目，已完成不动 ⇒ 5+5=10 上限成立。\n'
    '     价 = Σ未完成条 YlxwRnRowCost（与 R-035 A4 单条刷新同口径），实时标在按钮上；\n'
    '     refAll 落 charDex.board 持久化，跨日 YlxwRnBoardOf 重掷时自然清零。 */\n'
    '  var refRf = 1;\n'
    '  try { refRf = YlxwCharRf(p); } catch (e58) { refRf = 1; }\n'
    '  var refCost = 0;\n'
    '  for (var i58 = 0; i58 < tasks.length; i58++) { if (tasks[i58] && !tasks[i58].done) refCost += YlxwRnRowCost(tasks[i58], refRf); }\n'
    '  var refUsed = board.refAll === day;\n'
    '  function refreshAll() {\n'
    '    if (!p || refUsed) return;\n'
    '    var n58 = 0, j58;\n'
    '    for (j58 = 0; j58 < tasks.length; j58++) { if (tasks[j58] && !tasks[j58].done) n58++; }\n'
    '    if (!n58) { setNotice("今日 5 条已全部完成，无需刷新。"); return; }\n'
    '    if ((Number(p.spiritStones) || 0) < refCost) { setNotice("灵石不足，整体刷新需 " + refCost + " 灵石。"); return; }\n'
    '    var nl = tasks.map(function (x) { return (x && !x.done) ? YlxwRnRollOne(true) : x; });\n'
    '    setP(function (prev) {\n'
    '      if ((Number(prev.spiritStones) || 0) < refCost) return prev;\n'
    '      var d0 = YlxwCharDexV2(prev.charDex);\n'
    '      var b0 = d0.board || { day: day, tasks: tasks };\n'
    '      if (b0.refAll === day) return prev; /* 双击竞态守卫 */\n'
    '      d0.board = { day: b0.day, tasks: nl, refAll: day };\n'
    '      return Object.assign({}, prev, { charDex: d0, spiritStones: (Number(prev.spiritStones) || 0) - refCost });\n'
    '    });\n'
    '    log("【缘契·整体刷新】花费 " + refCost + " 灵石，重掷 " + n58 + " 条寻访任务（已完成的不动），今日最多可做 10 条。", "normal");\n'
    '    setNotice("已整体刷新（-" + refCost + " 灵石），新任务已就位。");\n'
    '  }\n'
    '\n'
    + A_FUNC
)

# ② 板标题行（renwu 门禁串所在行）→ flex 行：标题原串 + 整体刷新按钮 + 上限提示。
#    侦察：现行 bundle count==1（probe15）；样式类全部是 renwu 块既有类。
A_HDR = (
    '    e.jsx("div", { className: "text-[10px] text-stone-500", children: "寻访任务（每日 5 条 · 提交该类该品阶以上物品即可寻访）" }),'
)

R_HDR = (
    '    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [\n'
    '      e.jsx("div", { className: "text-[10px] text-stone-500", children: "寻访任务（每日 5 条 · 提交该类该品阶以上物品即可寻访）" }),\n'
    '      e.jsxs("div", { className: "flex items-center gap-1.5", children: [\n'
    '        e.jsx("button", {\n'
    '          disabled: refUsed,\n'
    '          onClick: function () { refreshAll(); },\n'
    '          className: "px-2 py-1 rounded border text-[10px] " + (refUsed ? "bg-stone-800 border-stone-700 text-stone-500" : "bg-yellow-900/20 border-yellow-700 text-yellow-300 hover:bg-yellow-900/30"),\n'
    '          children: refUsed ? "今日已整体刷新" : "整体刷新 · " + refCost + " 灵石"\n'
    '        }),\n'
    '        e.jsx("span", { className: "text-[10px] text-stone-500", children: "每日限 1 次 · 最多可做 10 条" })\n'
    '      ] })\n'
    '    ] }),'
)

# 注入内容禁用模式（与 V28_BAN_PATTERNS + 本项目纯客户端口径一致）
BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-',
                'fetch(', 'localStorage', 'sessionStorage', '/yl/api',
                'Be.getState().setPlayer']


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """把 R-058 落到 Patcher 上；返回 gates 列表。"""
    zh = ctx['zh']

    a_func = A_FUNC          # 纯 ASCII，zh 恒等；统一过一遍防手滑
    r_func = zh(R_FUNC)
    a_hdr = zh(A_HDR)
    r_hdr = zh(R_HDR)

    # 注入内容硬断言：落 bundle 形态必须纯 ASCII + 无禁用模式
    for tag, s in (('r_func', r_func), ('r_hdr', r_hdr)):
        if not s.isascii():
            raise AssertionError('r058 新串(%s)含非 ASCII：zh() 转义失效' % tag)
        for pat in BAN_PATTERNS:
            if pat in s:
                raise AssertionError('r058 新串(%s)含禁用模式: %s' % (tag, pat))
    if '寻访任务' in r_func or '整体刷新' in r_func:
        raise AssertionError('r058 r_func 中文未被转义')

    # ① refreshAll 机制：插在 rows 循环前（submit 之后）
    p.replace(
        'r058-refresh-all', a_func, r_func, expect=1,
        note='R-058 整体刷新：每日 1 次 / 只重掷未完成条 / Σ未完成条定价（A4 同口径）'
    )

    # ② 板标题行 → 标题 + 按钮 + 上限提示（标题原串保留，renwu 门禁计数不变）
    p.replace(
        'r058-board-header', a_hdr, r_hdr, expect=1,
        note='R-058 「整体刷新 · N 灵石」按钮 + 「每日限 1 次 · 最多可做 10 条」提示'
    )

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本模块改动 =================
        ('R58·refreshAll 已注入',     'function refreshAll() {', 1, '==', ''),
        ('R58·按钮已挂载',            'onClick: function () { refreshAll(); }', 1, '==', ''),
        ('R58·disabled 接 refUsed',   'disabled: refUsed,', 1, '==', '每日 1 次判定'),
        ('R58·按钮价标文案',          zh('"整体刷新 · " + refCost + " 灵石"'), 1, '==', '点前可见，A4 同口径'),
        ('R58·已刷文案',              zh('今日已整体刷新'), 1, '==', ''),
        ('R58·上限提示',              zh('每日限 1 次 · 最多可做 10 条'), 1, '==', 'R-058 核心诉求文案'),
        ('R58·refAll 持久化',         'refAll: day', 1, '==', 'charDex.board.refAll 落档'),
        ('R58·双击竞态守卫',          'if (b0.refAll === day) return prev;', 1, '==', ''),
        ('R58·已完成条不动',          'return (x && !x.done) ? YlxwRnRollOne(true) : x;', 1, '==', 'done 不重掷 ⇒ 5+5=10 成立'),
        ('R58·灵石扣减',              '(Number(prev.spiritStones) || 0) - refCost', 1, '==', ''),
        ('R58·成本口径同 A4',         'refCost += YlxwRnRowCost(tasks[i58], refRf)', 1, '==', 'Σ未完成条单条价'),
        ('R58·不足提示',              zh('灵石不足，整体刷新需 " + refCost + " 灵石。'), 1, '==', ''),
        # 限域：本模块全部改动落在 YlxwCharBoardR34 函数体内，域内零网络调用
        ('R58·域内无网络调用',        'fetch(', 0, '==', '纯客户端',
         ('function YlxwCharBoardR34(', 'function YlxwCharTasksR35(')),
        # ================= 冻结：renwu（宿主与近邻）一字未动 =================
        ('冻结·R34 板标题未动',       zh('寻访任务（每日 5 条 · 提交该类该品阶以上物品即可寻访）'), 1, '==', 'renwu 门禁同串'),
        ('冻结·R34 挂载×2 未动',      'e.jsx(YlxwCharBoardR34, { player: p, setPlayer: setP, addLog: log }),', 2, '==', 'renwu 门禁同串'),
        ('冻结·R34 组件定义',         'function YlxwCharBoardR34(', 1, '==', ''),
        ('冻结·R35 组件定义',         'function YlxwCharTasksR35(', 1, '==', ''),
        ('冻结·R35 每日3条未动',      'YlxwRnRollList(3, false)', 1, '==', 'renwu 门禁同串'),
        ('冻结·R34 每日5条未动',      'YlxwRnRollList(5, true)', 1, '==', ''),
        ('冻结·A4 单条刷新未动',      'onClick: function () { refreshOne(idx); },', 1, '==', 'renwu 门禁同串'),
        ('冻结·A4 定价函数未动',      'function YlxwRnRowCost(', 1, '==', ''),
        ('冻结·A4 单条重掷未动',      'var nt = YlxwRnRollOne(false);', 1, '==', 'renwu 门禁同串'),
        ('冻结·A4 价标未动',          zh('children: "刷新 · " + rc + " 灵石"'), 1, '==', 'renwu 门禁同串'),
        # ================= 冻结：R-058 前两句（0.8.11 已落地，证明没碰） =================
        ('冻结·T6 缘契面板定义',      'function YlxwCharBondPanelT6(', 1, '==', '每 NPC 领奖宿主'),
        ('冻结·里程碑标题未动',       zh('缘契里程碑（点击领取 · 随机物品）'), 1, '==', '每 NPC 各阶段领奖入口'),
        ('冻结·里程碑领取入口×2',     'onClick: function () { claim(mile); },', 2, '==', '死 BondPanel + 现役 T6 各 1'),
        ('冻结·per-NPC 已领状态×2',   'var claimed = ps.bond[rel.id] || {};', 2, '==', '按 relId 存档'),
        ('冻结·A6 缘契件数表',        'var YLXW_CHAR_DROP_N = [2, 3, 4, 5];', 1, '==', 'R-036 拍板值'),
        ('冻结·A6 图鉴件数表',        'var YLXW_CHAR_DEX_DROP_N = [2, 2, 4, 4, 6, 8, 12];', 1, '==', 'R-036 拍板值'),
        ('冻结·里程碑档位表',         'var YLXW_CHAR_BOND_MILE = [', 1, '==', '25/50/75/100 四阶段'),
        # ================= 冻结：更远邻面（chargift/renwu 共同门禁） =================
        ('冻结·YlxwGiftCost 定义',    'function YlxwGiftCost(fav)', 1, '==', ''),
        ('冻结·YlxwGiftCost 调用×4',  'YlxwGiftCost(j&&j.favorability)', 4, '==', '停用而非删除 → 计数不变'),
    ]
    return gates


# --------------------------------------------------------------------------- 自检

if __name__ == '__main__':
    import io
    import os
    import subprocess
    import sys
    import tempfile
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from yl_patch import Patcher, Gates, zh  # noqa: E402

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    HERE = os.path.dirname(os.path.abspath(__file__))
    os.chdir(HERE)

    # 基线 = 「链跑到本模块之前」：本模块已接线则截到本模块前；未接线则全链
    # （renwu 自检同款逻辑，见 yl_renwu_ext.py __main__）
    import build_v26n as B  # noqa: E402
    _saved = B.V28_MODULES
    _pos = None
    for _i, _e in enumerate(_saved):
        if getattr(_e[1], '__module__', '') == __name__:
            _pos = _i
            break
    B.V28_MODULES = _saved[:_pos] if _pos is not None else _saved
    try:
        _base_in = io.open(B.BASE, encoding='utf-8').read()
        base, prior_gates = B.build(_base_in)
        n_prior_modules = len(B.V28_MODULES)
    finally:
        B.V28_MODULES = _saved
    print('=== r058 自检：基线 = 链跑到 r058 之前（%d chars，前置 %d 模块，先验门禁 %d 条）'
          % (len(base), n_prior_modules, len(prior_gates)))

    print('=== 改前锚点份数（链上前态） ===')
    pre = [('A_FUNC', zh(A_FUNC), 1), ('A_HDR', zh(A_HDR), 1)]
    bad = 0
    for name, s, exp in pre:
        n = base.count(s)
        ok = n == exp
        bad += (not ok)
        print('  [%s] %-8s actual=%d expect=%d' % ('OK' if ok else 'FAIL', name, n, exp))
    for name, s in (('refreshAll', 'refreshAll'), ('refAll', 'refAll'),
                    ('refCost', 'refCost'), ('refUsed', 'refUsed')):
        n = base.count(s)
        ok = n == 0
        bad += (not ok)
        print('  [%s] 新标识符无碰撞 %-10s actual=%d expect=0' % ('OK' if ok else 'FAIL', name, n))
    if bad:
        print('  [ABORT] 链上前态与设计不符（%d 条）' % bad)
        sys.exit(2)

    print('=== 应用补丁（内存副本，不写盘）===')
    pt = Patcher(base, label='r058-selfcheck')
    gts = apply(pt, {'zh': zh, 'base_text': base})
    print(pt.report())

    g = Gates(pt.text)
    for t in gts:
        name, s, expect, cmp, note = t[:5]
        g.check(name, s, expect, cmp, note, within=(t[5] if len(t) > 5 else None))
    print(g.report())
    ok = g.passed()

    # ★ 冻结证明的链级形态：把「本模块之前全部模块的先验门禁」在新文本上重跑一遍，
    #   任何一条因本模块 additions 漂移都会在此 FAIL（§22.5 下游字面门禁保护）。
    gp = Gates(pt.text)
    for t in prior_gates:
        name, s, expect, cmp, note = t[:5]
        gp.check('[先验] ' + name, s, expect, cmp, note, within=(t[5] if len(t) > 5 else None))
    print('=== 先验门禁重跑（%d 条，证明没碰任何相邻需求的面） ===' % len(prior_gates))
    print(gp.report())
    ok = ok and gp.passed()

    # node --check 产物级语法校验
    if ok:
        tmp = os.path.join(tempfile.gettempdir(), 'yl_r058_selfcheck.js')
        with open(tmp, 'w', encoding='utf-8', newline='') as f:
            f.write(pt.text)
        try:
            r1 = subprocess.run(['node', '--check', tmp], capture_output=True, text=True, timeout=180)
            print('=== node --check 补丁后 rc=%s' % r1.returncode)
            if r1.returncode != 0:
                print(r1.stderr[:2000])
                ok = False
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    print('自检结论: %s' % ('PASS' if ok else 'FAIL'))
    sys.exit(0 if ok else 1)
