# -*- coding: utf-8 -*-
r"""
yl_r175_ext.py — R-175 客户端半边：万妖巢穴排行榜「逐只」而非「合计」（standalone 纯客户端）

需求原文（台账 R-175，逐字）
--------------------------------------------------------------------------
  「万妖巢穴 · 五只同现  下面的排行榜计算，应该每一只单独计算，而不是算合计的攻击伤害」

服务端半边（patches/server/srv_patch_r175.py，SRV_CHAIN 第 78 环）已完成
--------------------------------------------------------------------------
  · 根因：event_boss_hits 表 PK=(event_id,user_id)，记分 score=score+excluded.score
    ⇒ 五只伤害被累加成一份总分，物理上没有「每只各打多少」的维度。
  · 服务端修法：新增表 event_boss_hits5(event_id,boss_no,user_id,score,strikes) 逐只记分；
    GET /api/eventboss/status 响应**向后兼容地新增** top10ByBoss 字段（旧 top10 逐位未变）。
  · 本环 = 客户端跟着改，否则玩家看到的仍是「合计榜」。

服务端新响应（逐字）
--------------------------------------------------------------------------
  { "eventId":12, "hpMax":0, "hpCur":0, "killed":false,
    "myScore":34567, "myStrikes":9,
    "top10":[ {"userId":7,"name":"张三","score":34567,"rank":1} ],
    "top10ByBoss":[
      { "no":1, "top10":[ {"userId":7,"name":"张三","score":12000,"rank":1},
                          {"userId":9,"name":"李四","score":8000,"rank":2} ] },
      { "no":2, "top10":[ {"userId":9,"name":"李四","score":15000,"rank":1} ] },
      { "no":3, "top10":[] }, { "no":4, "top10":[] }, { "no":5, "top10":[] } ] }
  · top10        = 旧字段（合计总榜），服务端逐位未变 ⇒ 老客户端不崩。
  · top10ByBoss  = 新字段：每项 { no, top10:[{userId,name,score,rank}] }，no=boss_no 1..5；
                   某只无人出手则该项 top10 为空数组。
  · ★ 过渡态：上线前已开的活动没有 event_boss_hits5 历史行 ⇒ 逐只榜初始为空（合计榜仍有值），
    记分从上线后逐次累积 ⇒ 客户端必须优雅处理空榜（显示「暂无」，不空白/不报错）。

改动前（客户端 bundle · 本环字符级实测）
--------------------------------------------------------------------------
  目标 bundle：build/assets/index-v2927-20261006.js（2,302,499 B / 2,134,727 chars）
  组件：YlxwTActBoss（活动中心 tab D「万妖巢穴」，@1204722）
  排行榜渲染处（唯一）读的是**合计榜** `d.top10`：
      var top = (d && d.top10) || [];                 ← 唯一读 top10 处
      ...
      top.length ? top.map(function (x, i) {
        return e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex justify-between flex-wrap gap-2", children: [
          e.jsx("span", { children: "第 " + YlxwNum(x.rank || (i + 1)) + " 名 · " + (x.name || "-") }),
          e.jsx("span", { className: "text-xs text-stone-400", children: YlxwNum(x.score) })
        ] }) }, "bs" + i);
      }) : e.jsx(YlxwEmpty, { children: "暂无讨伐记录。" }),
  ⇒ 一行一名「第 N 名 · 名字 / 分数」，空则「暂无讨伐记录。」。这就是「合计榜」。

改法（最小外科手术）
--------------------------------------------------------------------------
  腿 ①（主路径）：读新字段 d.top10ByBoss，**逐只渲染 5 段**：
      每段外层 div（key "bb"+no）→ 段标题「第 N 只 · 排行榜」（key "bh"+no）
      → 该只 top10 逐行（沿用原行样式与文案口径，key "b"+no+"-"+i）
      → 该只空榜则 YlxwEmpty「暂无讨伐记录。」（沿用项目既有空态文案，key "be"+no）。
  腿 ②（回落）：top10ByBoss 缺失**或为空数组**（老服务端/异常/过渡态）⇒ 回落旧合计 top10 渲染，
      逻辑逐字保留（含原「暂无讨伐记录。」空态），**绝不白屏**。
  腿 ③：**不动**出手/诛妖符请求与扣费、myScore/myStrikes 展示口径、boss 血条、其它活动块。

  新增文案仅 1 处：段标题「第 N 只 · 排行榜」——「第 N 只」沿用 boss 选择按钮既有口径
  （"\u7b2c "+bno+" \u53ea"），「排行榜」沿用同组件既有说明句（"…计入本期排行榜…"），
  「 · 」沿用面板标题分隔符 ⇒ 未自造新文案体系。

锚点（纯 ASCII · 对 build/assets/index-v2927-20261006.js 字符级实测）
--------------------------------------------------------------------------
  ★ 本块中文在 bundle 里是 **\uXXXX 转义**（裸中文 count==0）⇒ 锚点天然纯 ASCII（见 §冻结）。
  R1 锚点 = '  var top = (d && d.top10) || [];'                     count==1 → 打后 1（保留作回落）
  R2 锚点 = 排行渲染块（4 空格缩进，末尾 "暂无讨伐记录。"）          count==1 → 打后 0
  ★ 另有一处结构相似的 'top.length ? top.map(function (x, i) {' 在 **YlxwTActRank**（@1194857，
    读的是 d.top50，非本区域，6 空格缩进）——R2 锚点带 4 空格缩进且结尾文案不同 ⇒ 不误伤。
  冻结（对**原件**校验，count 必须 == 1）：
      '  var cur = null, bi;'                        boss 选择/循环态未动
      'YlxwNum(bosses[bi].no) === sel'               boss 选择器未动
      '"/eventboss/strike"' / '"/eventboss/talisman"'  出手/诛妖符请求未动
      'act.run("boss-strike"' / 'act.run("boss-talisman"'  动作未动
      '\u51fa\u624b\u6210\u529f'                      出手成功文案未动
      '\u8bdb\u5996\u7b26\u5df2\u7528'                诛妖符已用文案未动
      'YlxwNum(d && d.myScore)' / 'YlxwNum(d && d.myStrikes)'  myScore/myStrikes 口径未动
      '\u4e07\u5996\u5de2\u7a74 \u00b7 \u4e94\u53ea\u540c\u73b0'  面板标题未动
      'YlxwActPickEvent(evs, "boss_raid")'           活动选取未动
      '\u7b2c " + bno + " \u53ea'                     boss 按钮文案未动（新段标题沿用它）
      '\u6682\u65e0\u8ba8\u4f10\u8bb0\u5f55\u3002'    原空态文案未动（打后 ==2：逐只 + 回落各 1）
  打后：d.top10ByBoss==1 · var __bb==1 · R2==0 · 逐只段键/行键各==1 · 空态==2 · 冻结全绿

契约（照 localtest/yl_r169b_ext.py）
--------------------------------------------------------------------------
  · CLI：--src <js>（必填）/ --check（只验不写）/ --selftest（内存自证 + node --check + UI 逻辑探针）。
  · 二进制读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 <src>.bak-r175-<时刻>。
  · 幂等：产物已含标记 `[r175bossui]` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · gates() 五元组 (label, needle, expect, op, note)，op 支持 == / >=。
  · 不跑网络：只读 --src 指向的本地文件。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r175bossui]'

# --------------------------------------------------------------------------- 替换项

# 腿 ①：在 boss 血条/出手区之后声明逐只榜容器（旧 top 行保留，供腿 ② 回落）。
TOP_OLD = '  var top = (d && d.top10) || [];'
TOP_NEW = ('  var __bb = (d && d.top10ByBoss) || null;\n'
           '  var top = (d && d.top10) || [];')

# 腿 ①+②：排行渲染块。主路径逐只 5 段；缺失/空数组回落旧合计榜。
# 锚点纯 ASCII（bundle 中文为 \uXXXX 转义形态），4 空格缩进，与 YlxwTActRank 的 6 空格块不冲突。
RANK_OLD = r'''    top.length ? top.map(function (x, i) {
      return e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex justify-between flex-wrap gap-2", children: [
        e.jsx("span", { children: "\u7b2c " + YlxwNum(x.rank || (i + 1)) + " \u540d \u00b7 " + (x.name || "-") }),
        e.jsx("span", { className: "text-xs text-stone-400", children: YlxwNum(x.score) })
      ] }) }, "bs" + i);
    }) : e.jsx(YlxwEmpty, { children: "\u6682\u65e0\u8ba8\u4f10\u8bb0\u5f55\u3002" }),'''

RANK_NEW = r'''    (__bb && __bb.length) ? __bb.map(function (g) {
      var gno = YlxwNum(g && g.no), gl = (g && g.top10) || [];
      return e.jsxs("div", { className: "space-y-2", children: [
        e.jsx("div", { className: "text-[11px] text-stone-400", children: "\u7b2c " + gno + " \u53ea \u00b7 \u6392\u884c\u699c" }, "bh" + gno),
        gl.length ? gl.map(function (x, i) {
          return e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex justify-between flex-wrap gap-2", children: [
            e.jsx("span", { children: "\u7b2c " + YlxwNum(x.rank || (i + 1)) + " \u540d \u00b7 " + (x.name || "-") }),
            e.jsx("span", { className: "text-xs text-stone-400", children: YlxwNum(x.score) })
          ] }) }, "b" + gno + "-" + i);
        }) : e.jsx(YlxwEmpty, { children: "\u6682\u65e0\u8ba8\u4f10\u8bb0\u5f55\u3002" }, "be" + gno)
      ] }, "bb" + gno);
    }) : (top.length ? top.map(function (x, i) {
      return e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex justify-between flex-wrap gap-2", children: [
        e.jsx("span", { children: "\u7b2c " + YlxwNum(x.rank || (i + 1)) + " \u540d \u00b7 " + (x.name || "-") }),
        e.jsx("span", { className: "text-xs text-stone-400", children: YlxwNum(x.score) })
      ] }) }, "bs" + i);
    }) : e.jsx(YlxwEmpty, { children: "\u6682\u65e0\u8ba8\u4f10\u8bb0\u5f55\u3002" })) /*[r175bossui]*/,'''

REPS = [
    ('R175-1 逐只榜容器声明（top10ByBoss）', TOP_OLD, TOP_NEW),
    ('R175-2 排行渲染逐只化（5 段 + 合计回落）', RANK_OLD, RANK_NEW),
]

# 冻结针脚：本环只动上面两处，下列既有形态必须逐字在位（对**原件**校验）。
FREEZE = [
    ('  var cur = null, bi;', 1),                                   # boss 选择/循环态未动
    ('YlxwNum(bosses[bi].no) === sel', 1),                          # boss 选择器未动
    ('"/eventboss/strike"', 1),                                     # 出手请求未动
    ('"/eventboss/talisman"', 1),                                   # 诛妖符请求未动
    ('act.run("boss-strike"', 1),                                   # 出手动作未动
    ('act.run("boss-talisman"', 1),                                 # 诛妖符动作未动
    (r'\u51fa\u624b\u6210\u529f', 1),                                # 出手成功文案未动
    (r'\u8bdb\u5996\u7b26\u5df2\u7528', 1),                          # 诛妖符已用文案未动
    ('YlxwNum(d && d.myScore)', 1),                                 # myScore 口径未动
    ('YlxwNum(d && d.myStrikes)', 1),                               # myStrikes 口径未动
    (r'\u4e07\u5996\u5de2\u7a74 \u00b7 \u4e94\u53ea\u540c\u73b0', 1),  # 面板标题未动
    ('YlxwActPickEvent(evs, "boss_raid")', 1),                      # 活动选取未动
    (r'\u7b2c " + bno + " \u53ea', 1),                               # boss 按钮文案未动
]

# 逐只段标题文案（新，逐字）："\u7b2c " + gno + " \u53ea \u00b7 \u6392\u884c\u699c" = "第 N 只 · 排行榜"
HDR_NEEDLE = r'\u7b2c " + gno + " \u53ea \u00b7 \u6392\u884c\u699c'
EMPTY_NEEDLE = r'\u6682\u65e0\u8ba8\u4f10\u8bb0\u5f55\u3002'


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R175·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r175bossui] 恰好 1 处'),
        ('R175·★逐只字段已接入', 'd.top10ByBoss', 1, '==', '新字段读取恰好 1 处'),
        ('R175·逐只容器声明', 'var __bb = (d && d.top10ByBoss) || null;', 1, '==', ''),
        ('R175·逐只渲染分支', '(__bb && __bb.length) ? __bb.map(function (g) {', 1, '==', ''),
        ('R175·逐只段标题', HDR_NEEDLE, 1, '==', '第 N 只 · 排行榜'),
        ('R175·逐只行键唯一', '"b" + gno + "-" + i', 1, '==', ''),
        ('R175·逐只段键唯一', '"bb" + gno', 1, '==', ''),
        ('R175·逐只空态键唯一', '"be" + gno', 1, '==', ''),
        ('R175·空态文案沿用', EMPTY_NEEDLE, 2, '==', '逐只 + 合计回落 各 1'),
        ('R175·★合计回落仍在', ': (top.length ? top.map(function (x, i) {', 1, '==', '老服务端不白屏'),
        ('R175·合计字段未删', 'var top = (d && d.top10) || [];', 1, '==', '供回落使用'),
        ('R175·旧独立渲染头已消失', RANK_OLD, 0, '==', '原合计渲染块已被替换'),
    ]
    for needle, cnt in FREEZE:
        g.append(('冻结 ' + needle[:24], needle, cnt, '==', '冻结既有形态'))
    return g


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


def _precheck(s):
    """返回 None=可打；否则返回错误串。对**原件** s 校验锚点与冻结针脚。"""
    if IDEMPOTENT_MARK in s or all(new in s for _, _, new in REPS):
        return None  # 幂等，交由 main 判 rc=3
    for name, old, new in REPS:
        if new in s:
            continue
        if s.count(old) != 1:
            return '%s 锚点出现 %d 次（期望 1）' % (name, s.count(old))
    for needle, cnt in FREEZE:
        if s.count(needle) != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, s.count(needle), cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时为错误串，out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPS:
        if new in out:
            continue
        out = out.replace(old, new, 1)
    return out, None


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        c = out.count(needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    rev = out
    for name, old, new in reversed(REPS):
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    """对 js_text 跑 node --check；返回 (rc, node_path) 或 (None, None) 当无 node。"""
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


def _ui_probe(patched_text):
    """从补丁后产物抽出**真实**逐只渲染表达式，用 node + 桩 e/Ylxw* 跑数据驱动断言。

    断言：5 只 → 5 段、段标题、逐只行/空态；缺 top10ByBoss → 回落合计榜；
          top10ByBoss 为空数组 → 回落合计榜；单只空 → 1 段 + 空态。
    返回 (ok, msg)；ok=None 表示无 node（跳过）。
    """
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    i = patched_text.find('(__bb && __bb.length) ? __bb.map')
    if i < 0:
        return False, '逐只渲染表达式未找到'
    j = patched_text.find('/*[r175bossui]*/', i)
    if j < 0:
        return False, '逐只渲染表达式结束边界未找到'
    expr = patched_text[i:j].rstrip()
    if not expr.endswith('))'):
        return False, '逐只渲染表达式尾部异常: %r' % expr[-40:]
    harness = (
        "function YlxwNum(r){ return Number(r) || 0; }\n"
        "function YlxwRow(r){ return { t: 'row', p: r }; }\n"
        "function YlxwEmpty(r){ return { t: 'empty', p: r }; }\n"
        "var e = { jsx: function (t, p, k) { return { t: t, p: p, k: k }; },\n"
        "          jsxs: function (t, p, k) { return { t: t, p: p, k: k }; } };\n"
        "function build(d) {\n"
        "  var __bb = (d && d.top10ByBoss) || null;\n"
        "  var top = (d && d.top10) || [];\n"
        "  return (" + expr + ");\n"
        "}\n"
        "function isRow(x){ return !!x && x.t === YlxwRow; }\n"
        "function isEmpty(x){ return !!x && x.t === YlxwEmpty; }\n"
        "function secRows(s){ var c = s.p.children[1]; return Array.isArray(c) ? c.filter(isRow) : []; }\n"
        "function secEmpty(s){ var c = s.p.children[1]; return isEmpty(c) ? c : null; }\n"
        "function hdr(s){ return s.p.children[0].p.children; }\n"
        "var HDR1 = '\\u7b2c 1 \\u53ea \\u00b7 \\u6392\\u884c\\u699c';\n"
        "var HDR5 = '\\u7b2c 5 \\u53ea \\u00b7 \\u6392\\u884c\\u699c';\n"
        "var EMPTY = '\\u6682\\u65e0\\u8ba8\\u4f10\\u8bb0\\u5f55\\u3002';\n"
        "var ROW1 = '\\u7b2c 1 \\u540d \\u00b7 \\u5f20\\u4e09';\n"
        # S1: 5 只（1 只 2 行、1 只 1 行、3 只空）
        "var S1 = { top10: [{userId:7,name:'\\u5f20\\u4e09',score:34567,rank:1}], top10ByBoss: [\n"
        "  { no:1, top10:[ {userId:7,name:'\\u5f20\\u4e09',score:12000,rank:1}, {userId:9,name:'\\u674e\\u56db',score:8000,rank:2} ] },\n"
        "  { no:2, top10:[ {userId:9,name:'\\u674e\\u56db',score:15000,rank:1} ] },\n"
        "  { no:3, top10:[] }, { no:4, top10:[] }, { no:5, top10:[] } ] };\n"
        "var O1 = build(S1);\n"
        "if (!Array.isArray(O1) || O1.length !== 5) throw new Error('S1 sections=' + (O1 && O1.length));\n"
        "if (hdr(O1[0]) !== HDR1) throw new Error('S1 hdr=' + hdr(O1[0]));\n"
        "if (secRows(O1[0]).length !== 2) throw new Error('S1 boss1 rows=' + secRows(O1[0]).length);\n"
        "if (secRows(O1[1]).length !== 1) throw new Error('S1 boss2 rows=' + secRows(O1[1]).length);\n"
        "var rows = 0, emp = 0;\n"
        "for (var i = 0; i < O1.length; i++) { rows += secRows(O1[i]).length; if (secEmpty(O1[i])) emp++; }\n"
        "if (rows !== 3 || emp !== 3) throw new Error('S1 rows=' + rows + ' emp=' + emp);\n"
        "if (secRows(O1[0])[0].p.children.p.children[0].p.children !== ROW1) throw new Error('S1 row0=' + secRows(O1[0])[0].p.children.p.children[0].p.children);\n"
        "if (secEmpty(O1[2]).p.children !== EMPTY) throw new Error('S1 empty=' + secEmpty(O1[2]).p.children);\n"
        # S2: 无 top10ByBoss -> 回落合计榜
        "var S2 = { top10: [ {userId:7,name:'A',score:1,rank:1}, {userId:8,name:'B',score:2,rank:2} ] };\n"
        "var O2 = build(S2);\n"
        "if (!Array.isArray(O2) || O2.length !== 2 || !isRow(O2[0])) throw new Error('S2 fallback len=' + (O2 && O2.length));\n"
        # S3: top10ByBoss 为空数组 -> 回落合计榜
        "var S3 = { top10: [ {userId:7,name:'A',score:1,rank:1} ], top10ByBoss: [] };\n"
        "var O3 = build(S3);\n"
        "if (!Array.isArray(O3) || O3.length !== 1 || !isRow(O3[0])) throw new Error('S3 empty-array fallback len=' + (O3 && O3.length));\n"
        # S4: 单只空榜 -> 1 段 + 空态，标题为第 5 只
        "var S4 = { top10ByBoss: [ { no:5, top10:[] } ] };\n"
        "var O4 = build(S4);\n"
        "if (!Array.isArray(O4) || O4.length !== 1) throw new Error('S4 len=' + (O4 && O4.length));\n"
        "if (!secEmpty(O4[0])) throw new Error('S4 should be empty');\n"
        "if (hdr(O4[0]) !== HDR5) throw new Error('S4 hdr=' + hdr(O4[0]));\n"
        "console.log('ui-probe OK');\n"
    )
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(harness.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:300]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → UI 逻辑探针。"""
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r175] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r175] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r175] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r175] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r175] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r175] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _ui_probe(out)
    if ok is False:
        print('[r175] SELFTEST FAIL ui-probe: ' + pmsg)
        return 1
    print('[r175] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s; %s'
          % (len(gates()), len(out) - len(s0), nmsg, pmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r175] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r175] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r175] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r175] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r175] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r175] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-40s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r175-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r175] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-40s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
