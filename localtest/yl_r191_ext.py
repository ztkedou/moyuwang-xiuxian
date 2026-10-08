# -*- coding: utf-8 -*-
r"""
yl_r191_ext.py — R-191：自动历练「奇遇率」修复 + 结算日志「分档触发次数」统计（standalone 纯客户端）

★ 用户现场（原话）：
  「9 次历练出奇遇 3 次（33%），灵石 +1445/次 —— 不是说奇遇只有 1% 概率吗？」
  「把触发各种加成的次数也统计进来，现在的里面只统计了奇遇的 3 次，中等加好几百灵石的那种没统计。」

★ 本环边界（严格）：
  · 只改**客户端 bundle** 两处逻辑：① 奇遇率 EV 公式；② 自动历练结算日志的分档统计。
  · 不改服务端、不改数值表、不删功能块、不动其它 `yl_r*_ext.py` / `patches/*` / 台账 / `build/assets/*`。
  · 不改 R-180 的档位权重（E2/E3/E4/E5/E6/E7 逐字不动）；只把 EV 常数项重写（R-180 v4 的 EV 由本环接管）。

==============================================================================
零、根因（bundle 字符级实抽 + node 复算）
==============================================================================
  奇遇判定**只有一处**（本产物 char 1922443 起，`handleAdventure` 内）：

      const U=fe.indexOf(t.realm),V=Math.min(.3,0.01+(t.luck||0)*.001);
      if(Math.random()<.15){ ...商铺... }
      const Z=Math.random()<V;
      Z && a("✨ 你福至心灵，触发了奇遇！","special");
      await I(Z?"lucky":"normal")

  · `t.luck` 是**数字**（旁证：炼丹 `(j.luck||0)*.001` char 1564235、战斗 `(t.luck||0)*15e-5` char 767522）。
  · `luck` 来源 = **天赋**（`Un` 数组，char 367070 起；随机/自选获得）：
      `by(t,r)` → `j = Σ Un[].effects.luck` → 角色创建 `luck: 10 + j`（char 533844）。
    `Un` 的 effects 被 **R-132 补丁表** `YLXW_R132_PATCH`（char 395740 起）**覆盖**：
      `"nt-50":{e:{luck:300,...}}`（天机共鸣）｜`"nt-69":{e:{luck:300,...}}`（祥云护体）
      `"nt-68":{e:{luck:240,...}}`（瑞气东来）
    应用点：`YlxwR132Variety(Un)` → `arr[i].effects = Object.assign({}, p.e)`（char 400850 起）。
  ⇒ **V = Math.min(0.3, 0.01 + 300×0.001) = Math.min(0.3, 0.31) = 0.30 = 30%**
  ⇒ 基础项 0.01 被幸运项彻底淹没 —— 这就是用户看到 33%（3/9）的原因。

  复核结论（本环实测，见 §一 / §二）：
    ① `nt-50`/`nt-69` **确实可获得**（在 `Un` 天赋池内，`F3` 随机抽取 / `startNewGame` 自选）；
       ★ 更正团队取证的一处**标签**：它们是**天赋/命运**（`Un`），不是**称号**（`Ln`）；
         但「luck 来自这两项、值 300」的**机制判断成立**。
    ② **只有一条** `lucky` 路径：`adventureType:"lucky"` 字面量全库**仅 1 处**（`xw` 奇遇模板生成器，
       char 568794）；`Fm(type,...)` 首行即 `fi.filter(m=>m.adventureType===t)`（按 type 过滤）
       ⇒ `Fm("normal")` **永不**产出 lucky 模板。

==============================================================================
一、复核①：nt-50/nt-69 可获得性（node 实抽 + 链路）
==============================================================================
  · `Un = [{id,name,description,category,rarity,fateCost,effects}, ...]`（char 367070）。
  · 随机天赋生成 `F3(t)`（char 499606）：从 `[...Un]` 按 `rarity` 权重抽（普通40/稀有30/传说20/仙品10），
    受 `fateCost` 预算约束（`l.filter(j=>!(j.fateCost>a))`）⇒ `nt-50`(fateCost 8) 可达。
  · 自选路径：`startNewGame(a,l,c)` → `by(a,l)`，`l` = 玩家选定天赋 id 列表。
  · `by(t,r)`（char 531992）：`const a = r.map(h=>Un.find(...))`，`l=V3(a)`，`j=l.luck||0`
    ⇒ 角色 `luck: 10 + j`（char 533844）。
  · `V3`（char 499547）：`a.effects.luck && (r.luck=(r.luck||0)+a.effects.luck)` —— 逐项累加。
  ⇒ 携带 nt-50 或 nt-69 任一 ⇒ luck ≥ 10+300 = 310 ⇒ V 封顶 30%。

==============================================================================
二、复核②：lucky 路径唯一性（node 实抽）
==============================================================================
  · 全库 `adventureType:"lucky"` 字面量：**1 处**（char 568794，`xw` 奇遇模板生成器返回值内）。
  · 其余 `adventureType:` 均为**透传**（`adventureType:t.adventureType` / `:Q` / `:m` / `:a` 等）。
  · `Fm(t="normal",r,a,l)`（char 574994）首行 `let v=fi.filter(m=>m.adventureType===t)`
    ⇒ 按 type 过滤；`normal` 池**不含** lucky 模板。
  · 模板池 `Oc={NORMAL:720,LUCKY:120,SECRET_REALM:300,SECT_CHALLENGE:60}`（char 535207）。
  · `hw`（普通模板生成器，char 541734~567336）内 `lucky` 出现 **0 次**。
  ⇒ 唯一路径 = `handleAdventure` 的 `Z=Math.random()<V` ⇒ `I(Z?"lucky":"normal")`。

==============================================================================
三、任务 A：奇遇率修复
==============================================================================
  · 旧：`V=Math.min(.3,0.01+(t.luck||0)*.001)`   （基础 1% + 幸运无界，封顶 30%）
  · 新：`V=0.01+Math.min(0.01,(t.luck||0)*0.00003)`（基础 1% + 幸运有界 +1%，封顶 2%）

    取值：luck 0 → 1.0% ｜ 100 → 1.3% ｜ 300 → 1.9% ｜ ≥334 → 2.0%（封顶）
  · ★ 保留幸运语义（称号/天赋「气运」仍有一点点作用），但**有界**（最多 +1%）。
  · ★ **不引入境界项**（保住 R-180 v3/v4「全境界概率统一」）：`fe.indexOf(t.realm)`（=U）不参与 V。
  · ★ 单行、纯 ASCII、便于 grep 与门禁断言。

==============================================================================
四、任务 B：结算日志「分档触发次数」
==============================================================================
  取证（现有那行「事件类型：奇遇 3 · 历练 6」是谁写的）：
    · 累加 `YlxwAdvStatAcc(res)`（char 626480 起，R-138/R-155 链）：
        var ty = res.adventureType || "normal";
        S.types[ty] = (S.types[ty] || 0) + 1;
        if (ty === "lucky") S.lucky += 1;
      ⇒ 口径 = **按 `res.adventureType` 分类计数**（normal/lucky/secret_realm/...）。
    · 渲染 `YlxwAdvSummary(el)`（char 628690 起，marker `[r179advlog]`）：
        for (k in st.types) { if (st.types[k]) dist.push(YlxwAdvTypeName(k) + " " + st.types[k]); }
        if (dist.length) __r179d.push("事件类型：" + dist.join(" · "));
      ⇒ 「奇遇 3 · 历练 6」= `dist.join(" · ")`，`YlxwAdvTypeName` 把 `lucky→奇遇`、`normal→历练`。
    ⇒ **「几百灵石」的普通事件 type 仍是 `normal`**，故被并入「历练」——这正是用户说的「没统计」。

  扩展（按**该次结算的灵石值** `ds = floor(res.spiritStonesChange)` 分档，口径与 R-180 一致）：
    · 常态 ≤150 ｜ 几百 151~900 ｜ 几千 ≥1000（R-180 口径，见 `deploy_v28/DEPLOY_LOG_0.9.32.md` §R-180 表头）。
    · ★ 为使三档**穷尽无缝隙**，`901~999` 并入「几百」（同属「几百灵石」量级）；
      实现用 `if (ds<=150) low; else if (ds>=1000) high; else mid;` ⇒ `low+mid+high == runs`。
    · 新增字段：`tierLow / tierMid / tierHigh`（初始化于 `YlxwAdvStatNew`）。
    · 渲染：在「事件类型：…」**其后**追加一行 `分档 常态 N · 几百 N · 几千 N`
      （同一「·」分隔 + 中文标签风格，与既有字段并列；不动其它既有字段）。
    · 受伤次数（`hpDown`）**已有**，不改。

==============================================================================
五、契约
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 蒙特卡洛）。
  · 就地替换 4 处（见 REPLACEMENTS）；每处打前断言 `count == 1`（锚点纯 ASCII）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r191-<时刻>`。
  · 幂等：产物已含标记 `/*[r191adv]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 蒙特卡洛：从补丁后产物**实抽** EV 表达式，node 真跑 n=20 万/组合，
    报 luck=0/100/300/500 × 境界（炼气/金丹/长生）奇遇率 ⇒ 必须全落 [1%, 2%]。
  · 不跑网络：只读 --src 指向的本地文件。
  · ★ 冻结针脚只钉本批**不动**的稳定形态，**绝不**钉 `[r180adv*]`/`[r185farm*]`/`[r184wudao]`/
    `[r187guide]`/`[r188med*]`/`[r190feed]`/`[r189ui]`。
  · ★ `yl_r180_ext.py` 在本补丁**之前**套用 ⇒ EV 锚点按 **v4 形态**（`Math.min(.3,0.01+(t.luck||0)*.001)`）写。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# 幂等标记（本批）
IDEMPOTENT_MARK = '/*[r191adv]*/'

# ---- 退役针脚标记（0.9.36 起）----
# 语义：本环（R-191）**排在 R-193 之前**套用 ⇒ apply 时本环注入的新 EV 形态与幂等标记
#   `/*[r191adv]*/` **仍在**（count==1）；而 R-193（0.9.33）已**取代**本环的 EV 公式
#   （终态 `V=0.01+Math.min(0.03,$a(titleId,unlockedTitles).luck*0.0003)`，不再含本环的 0.00003 项，
#    且 `/*[r191adv]*/` 被移除）⇒ 本环这 3 条形态在终态为 0。
# 单条 (needle, expect) 无法同时满足 apply 态(1) 与终态(0)，故退役 = **终态专用**：
#   · dryrun 读 gates() 在终态复核（期望 0，如实反映 R-193 改写后的形态）；
#   · 本环 apply/--check 时跳过（不检、不计 FAIL），避免「老补丁依赖新补丁」——新形态由
#     R-193 自己的门禁负责。
RETIRED_TAG = '【已退役·终态专用】'

# --------------------------------------------------------------------------- 替换项
# ★ 形态约定：本批锚点全为**纯 ASCII**（EV 公式 / 统计函数体）；渲染行中文为 bundle 内
#   **字面 `\uXXXX`**（六字符）⇒ 本 .py 源码用 `\\uXXXX`（双反斜杠）写出，运行期字符串即 `\uXXXX`。

# ---- A：奇遇率 EV（有界幸运项） ----
A_OLD = 'V=Math.min(.3,0.01+(t.luck||0)*.001)'
A_NEW = 'V=0.01+Math.min(0.01,(t.luck||0)*0.00003)' + IDEMPOTENT_MARK

# ---- B1：统计对象新增分档字段 ----
B1_OLD = (
    '  return { sess: null, runs: 0, exp: 0, stone: 0, hp: 0, hpDown: 0, life: 0,\n'
    '           lot: 0, rep: 0, drops: 0, lucky: 0, soul: 0, items: {}, types: {} };'
)
B1_NEW = (
    '  return { sess: null, runs: 0, exp: 0, stone: 0, hp: 0, hpDown: 0, life: 0,\n'
    '           lot: 0, rep: 0, drops: 0, lucky: 0, soul: 0, items: {}, types: {},\n'
    '           tierLow: 0, tierMid: 0, tierHigh: 0 };'
)

# ---- B2：按结算灵石值分档累加 ----
B2_OLD = '  if (ty === "lucky") S.lucky += 1;\n'
B2_NEW = (
    '  if (ty === "lucky") S.lucky += 1;\n'
    '  if (ds <= 150) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; else S.tierMid += 1;\n'
)

# ---- B3：渲染追加「分档」字段（紧跟「事件类型」行之后） ----
B3_OLD = '    if (dist.length) __r179d.push("\\u4e8b\\u4ef6\\u7c7b\\u578b\\uff1a" + dist.join(" \\u00b7 "));'
B3_NEW = (
    B3_OLD + '\n'
    '    __r179d.push("\\u5206\\u6863 \\u5e38\\u6001 " + st.tierLow + " \\u00b7 \\u51e0\\u767e " '
    '+ st.tierMid + " \\u00b7 \\u51e0\\u5343 " + st.tierHigh);'
)

REPLACEMENTS = [
    ('a_ev', A_OLD, A_NEW),
    ('b1_init', B1_OLD, B1_NEW),
    ('b2_acc', B2_OLD, B2_NEW),
    ('b3_render', B3_OLD, B3_NEW),
]

# 冻结针脚（对**输入**校验）：本批不动的稳定形态
# （绝不含 [r180adv*]/[r185farm*]/[r184wudao]/[r187guide]/[r188med*]/[r190feed]/[r189ui]）。
FREEZE = [
    ('function YlxwAdvStatNew() {', 1),
    ('function YlxwAdvStatAcc(res) {', 1),
    ('function YlxwAdvSummary(el) {', 1),
    ('function YlxwAdvTypeName(t) {', 1),
    ('var YLXW_ADV_STAT = null;', 1),
    ('var YLXW_ADV156_LINES = [];', 1),
    ('function Fm(t="normal"', 1),
    ('Oc={NORMAL:720,LUCKY:120,SECRET_REALM:300,SECT_CHALLENGE:60}', 1),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    needle 可为 tuple（多形态合计计数）。"""
    return [
        # ---- 幂等标记（★ 终态退役：R-193 已取代本环公式并移除标记）----
        ('R191\u00b7\u5e42\u7b49\u6807\u8bb0 r191adv' + RETIRED_TAG, IDEMPOTENT_MARK, 0, '==',
         'R-193 已取代本环 EV 公式并移除 /*[r191adv]*/ ⇒ 终态归 0；新形态由 R193 自己的门禁负责'),
        # ---- A：EV（★ 前/末两条终态退役：R-193 已取代本环公式）----
        ('R191\u2460\u00b7\u65b0 EV \u516c\u5f0f\u5728\u4f4d' + RETIRED_TAG,
         'V=0.01+Math.min(0.01,(t.luck||0)*0.00003)', 0, '==',
         'R-193 已把 EV 换成「纯称号来源」公式 ⇒ 本环 0.00003 项终态归 0；新形态由 R193 自己的门禁负责'),
        ('R191\u2460\u00b7\u65e7 EV \u516c\u5f0f\u5df2\u6e05\u96f6',
         'V=Math.min(.3,0.01+(t.luck||0)*.001)', 0, '==', '旧无界 EV 0 处'),
        ('R191\u2460\u00b7\u65e7\u5c01\u9876\u9879\u5df2\u6e05\u96f6',
         'Math.min(.3,0.01+(t.luck||0)*.001)', 0, '==', 'Math.min(.3,0.01+…) 0 处'),
        ('R191\u2460\u00b7\u65b0 EV \u884c\u5b8c\u6574\u5728\u4f4d' + RETIRED_TAG,
         'V=0.01+Math.min(0.01,(t.luck||0)*0.00003)' + IDEMPOTENT_MARK + ';', 0, '==',
         'R-193 已取代本环 EV 行（含标记）⇒ 终态归 0；新形态由 R193 自己的门禁负责'),
        # ---- B1：初始化 ----
        ('R191\u2461\u00b7\u5206\u6863\u5b57\u6bb5\u521d\u59cb\u5316',
         'tierLow: 0, tierMid: 0, tierHigh: 0 };', 1, '==', '统计对象新增 3 字段'),
        # ---- B2：累加 ----
        ('R191\u2462\u00b7\u5206\u6863\u7d2f\u52a0\u5728\u4f4d',
         'if (ds <= 150) S.tierLow += 1; else if (ds >= 1000) S.tierHigh += 1; else S.tierMid += 1;',
         1, '==', '常态/几百/几千 穷尽分档'),
        # ---- B3：渲染 ----
        # ★ 2026-10-08（0.9.39 / R-208）：标签改名（常态→寻常 / 几百→丰厚 / 几千→横财）⇒
        #   本针改为**值无关**（只钉「分档 」这个行首前缀，跨 r208 恒成立）。三个新标签由 r208 自己的门禁负责。
        ('R191\u2463\u00b7\u5206\u6863\u6e32\u67d3\u5728\u4f4d',
         '\\u5206\\u6863 ', 1, '==', '「分档 …」行在位（标签名见 r208）'),
        ('R191\u2463\u00b7\u4e8b\u4ef6\u7c7b\u578b\u884c\u4fdd\u7559',
         '\\u4e8b\\u4ef6\\u7c7b\\u578b\\uff1a', 1, '==', '既有「事件类型」行未动'),
        ('R191\u2463\u00b7\u53d7\u4f24\u884c\u4fdd\u7559',
         'if (st.hpDown) __r179d.push("\\u53d7\\u4f24 ', 1, '==', '既有「受伤」行未动'),
        # ---- 未动（冻结针脚对应产物） ----
        ('R191\u00b7YlxwAdvStatNew \u672a\u5220',
         'function YlxwAdvStatNew() {', 1, '==', '函数体保留'),
        ('R191\u00b7YlxwAdvStatAcc \u672a\u5220',
         'function YlxwAdvStatAcc(res) {', 1, '==', '函数体保留'),
        ('R191\u00b7YlxwAdvSummary \u672a\u5220',
         'function YlxwAdvSummary(el) {', 1, '==', '函数体保留'),
        ('R191\u00b7YlxwAdvTypeName \u672a\u5220',
         'function YlxwAdvTypeName(t) {', 1, '==', '函数体保留'),
        ('R191\u00b7Fm \u9009\u62e9\u5668\u672a\u52a8',
         'function Fm(t="normal"', 1, '==', '按 type 过滤未动'),
        ('R191\u00b7\u6a21\u677f\u6c60\u672a\u52a8',
         'Oc={NORMAL:720,LUCKY:120,SECRET_REALM:300,SECT_CHALLENGE:60}', 1, '==', '模板池计数未动'),
    ]


# --------------------------------------------------------------------------- 主流程

def _read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


def _write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(text.encode('utf-8'))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _is_patched(s):
    return IDEMPOTENT_MARK in s


def _precheck(s):
    """返回 err（None 表示可打）。"""
    for name, old, new in REPLACEMENTS:
        c = s.count(old)
        if c != 1:
            return '锚点 %s 出现 %d 次（期望 1）' % (name, c)
    for needle, cnt in FREEZE:
        c = s.count(needle)
        if c != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, c, cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时 out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPLACEMENTS:
        out = out.replace(old, new, 1)
    return out, None


def _count(out, needle):
    if isinstance(needle, tuple):
        return sum(out.count(x) for x in needle)
    return out.count(needle)


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        if RETIRED_TAG in label:
            # 退役针脚（终态专用）：本环 apply 时 R-193 尚未套用，自产 EV 形态/标记仍在 ⇒ 不检；
            # 终态由复核（期望 0）负责，新形态由 R-193 自己的门禁负责。
            continue
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    """反向还原：把每个 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
        r = subprocess.run([node, '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _probe_ev(patched_text, n=200000):
    """从补丁后产物**实抽** EV 表达式，node 真跑蒙特卡洛：
    luck=0/100/300/500 × 境界（炼气/金丹/长生）奇遇率 ⇒ 必须全落 [1%, 2%]。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。"""
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    m = re.search(r'V=(0\.01\+Math\.min\(0\.01,\(t\.luck\|\|0\)\*0\.00003\))', patched_text)
    if not m:
        return False, 'EV 表达式未在产物中找到'
    rhs = m.group(1)
    if 'realm' in rhs:
        return False, 'EV 表达式含境界项: ' + rhs
    js = (
        'function ev(t){ return ' + rhs + '; }\n'
        'var lucks=[0,100,300,500];\n'
        'var realms=["\\u70bc\\u6c14","\\u91d1\\u4e39","\\u957f\\u751f"];\n'
        'var N=' + str(int(n)) + ';\n'
        'var lines=[];\n'
        'for(var li=0;li<lucks.length;li++){\n'
        '  for(var ri=0;ri<realms.length;ri++){\n'
        '    var t={realm:realms[ri],luck:lucks[li]};\n'
        '    var p=ev(t);\n'
        '    if(!(p>=0.01-1e-9 && p<=0.02+1e-9)) throw new Error("V out of [1%,2%]: "+p+" luck="+lucks[li]);\n'
        '    var hit=0;\n'
        '    for(var i=0;i<N;i++){ if(Math.random()<p) hit++; }\n'
        '    var rate=hit/N;\n'
        '    if(!(rate>=0.008 && rate<=0.022)) throw new Error("MC rate out of band: "+rate);\n'
        '    lines.push("  luck="+lucks[li]+" \\u5883\\u754c="+realms[ri]+"  V="+(p*100).toFixed(3)+"%  MC="+(rate*100).toFixed(3)+"%");\n'
        '  }\n'
        '}\n'
        'var oldp=Math.min(.3,0.01+300*.001);\n'
        'lines.push("  [\\u5bf9\\u7167] \\u65e7\\u516c\\u5f0f luck=300 V="+(oldp*100).toFixed(1)+"%");\n'
        'console.log(lines.join("\\n"));\n'
    )
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:400]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 蒙特卡洛。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r191] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r191] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r191] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r191] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r191] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r191] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _probe_ev(out)
    if ok is False:
        print('[r191] SELFTEST FAIL ev-probe: ' + pmsg)
        return 1
    print('[r191] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print('[r191] MC(n=%d):' % 200000)
        print(pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r191] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r191] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r191] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r191] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r191] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r191] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            if RETIRED_TAG in label:
                print('    [SKIP] %s 已退役（终态由 R-193 门禁复核）' % label.replace(RETIRED_TAG, ''))
            else:
                print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r191-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r191] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        if RETIRED_TAG in label:
            print('    [SKIP] %s 已退役（终态由 R-193 门禁复核）' % label.replace(RETIRED_TAG, ''))
        else:
            print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
