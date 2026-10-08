# -*- coding: utf-8 -*-
r"""
yl_r187_ext.py — R-187「仙途指引 说明内数字与实发不同步」standalone 纯客户端

需求原文（台账 R-187，逐字）
--------------------------------------------------------------------------
  「仙途指引的经验没有增加啊，昨天让修复的工作怎么没完成」

==============================================================================
零、取证：这条是「上次修过但没生效」型 —— 先查上次改了什么
==============================================================================
── 台账锚定 ──
  · 需求台账_进行中.md R-187 模块 = 「仙途指引」。
  · 「昨天让修复的工作」= **R-172**（台账原文：『仙途指引里面的奖励也同样跟成就系统
    一样…要以实际达到需求所付出的努力来计算…炼气3层到圆满可能需要好多天的时间』）。
    归档备注：「0.9.26 已上线。服务端第 76 环」——即 **2026-10-06 17:12 的 0.9.26**，
    正是「昨天」。本批同类：R-186（R-173 已上线但逻辑错）、R-188（怀疑不成立但有真因）。

── 上次（R-172）改在哪一端？现在还在不在？—— 贴实测 ──
  [服务端 · 在，且已上线]  `srv/index_v28.ts` md5 = `bd7abfae10131e6099580c1163b51673`
      = 0.9.30 DEPLOY_LOG 登记的线上服务端（80 环）。GUIDE_STEPS（@12777-12786）实测：
        enter 2000 / lv3 3000 / **lv9 8600** / **zhuji 9900** / friend 3000 /
        baishi 6000 / **jindan 61000** / daolv 12000        （[r123guide]+[r172guide] 双标记在位）
      ⇒ R-172 **确实生效**：`/api/guide/status` 回 `reward: st.reward`（@12844）、
        `/api/guide/claim` 按 `st.reward` 入账 `sd.player.spiritStones`（@12883）。
  [客户端 · 不在]  0.9.30 产物 `build/assets/index-v2930-20261007.js`
      （2,308,071 B，md5 `4a765aa197694ff3175f29e8a38cc2c2`）实测：
        · `8600` / `61000` / `105500` / `r172guide` 计数**全 = 0** ⇒ R-172 的服务端新值
          **一个都没进客户端**。
        · 「仙途指引」玩法说明（R79Box，@1267206，count=1）里 ① 里程碑行仍是
          **R-123 的旧值**：`… 总等级 9 得 6000 / 总等级 10 得 8000 / … 总等级 19 得 20000 …`
          （逐字节 = yl_r123_ext.py 的 NEW1，实测 count=1）。

── ★★ 结论：R-172 是「服务端半边」，但客户端「说明」半边**漏了** ──
  R-123 当年立下的规矩（`docs/0.9.13-design/玩法说明与文案.md` §A 表 19 原文）：
      「仙途指引(guide) | YlxwTGuide @1119862 + R79Box | ✅ 有 | 不动；
        **提醒：R-123 改档位后说明内数字同步**」
  同文件 §六 第 6 条再次点名：「**数值联动提醒**（本批他项改动后回填说明数字）… R-123
      （仙途指引档位）」。
  ⇒ R-172 改了档位（服务端 6000/8000/20000 → 8600/9900/61000），**却没回填说明数字** ⇒
    面板里「玩法说明：仙途指引」仍写 `得 6000 / 得 8000 / 得 20000`。
    用户读到的正是这行说明 ⇒ 「**经验（奖励）没有增加啊，昨天让修复的工作怎么没完成**」。

── 关于用户措辞「经验」（★ 必须先纠正的认知）──
  · 仙途指引**不发经验**。全链路实测：`/api/guide/status`、`/api/guide/claim`、`/api/week/claim`
    只写 `sd.player.spiritStones`（灵石）；客户端 `YlxwTGuide()`（@1266951）渲染
    `m.name · m.desc · 奖励 m.reward`，**全 bundle「经验」34 处，无一处与指引相关**。
  · 且该面板的行（`奖励 <m.reward>`）**每次都现拉服务端**（`YlxwUseList` → `YlxwGet` →
    `YlxwApi` → `Xc()` 裸 fetch，**无任何缓存**），所以「行」显示的就是 8600/9900/61000。
  · ⇒ 用户口中的「经验」= 他对「仙途指引奖励」的口语称呼；而**唯一没跟着 R-172 变的可见面**
    就是那行玩法说明。本环只修这个「说明 ≠ 实发」的真实缺陷（不碰行渲染、不碰服务端）。

==============================================================================
一、改法（1 处就地替换 · 只同步说明数字，零结构改动）
==============================================================================
  E1 把「仙途指引」那唯一一处 R79Box 调用的**整串**替换为「同串 + 幂等标记 + 新档数字」：
      旧： YlxwR79Box("仙途指引", ["① …得 6000 / …得 8000 / …得 20000 …", "② 七日礼 …"])
      新： YlxwR79Box("仙途指引", [/*[r187guide]*/"① …得 8600 / …得 9900 / …得 61000 …", "② 七日礼 …"])
    仅改 ① 里程碑行内 **3 个数字**（6000→8600 / 8000→9900 / 20000→61000，逐字等于
    srv/index_v28.ts 的 GUIDE_STEPS），并注入 `/*[r187guide]*/`（JS 注释，数组元素间合法）。
    · ② 七日礼行**一字不动**（服务端 WEEK_REWARDS 未变，说明本来就一致，实测逐字相同）。
    · 不动 R79Box 定义/调用结构、不动行渲染、不动 `/guide/*` `/week/*` 端点、
      不动 YlxwTGuide 本体、不动「七日筑基」称号串。

==============================================================================
二、锚点与冻结针脚（对 build/assets/index-v2930-20261007.js 字符级实测）
==============================================================================
  替换锚点（打前 count==1；打后旧串 count==0 —— 整串替换，天然防重复注入）：
    E1_OLD = `YlxwR79Box("仙途指引", ["①…", "②…"]`（683 B，纯 ASCII，内部无 `[`/`]`）
  冻结针脚（对**原件**校验，全 ASCII；★ 只钉**本批其它补丁不动**的稳定形态）：
    `function YlxwTGuide() {`        ← 指引面板本体未动
    `function YlxwR79Box(t, L) {`    ← 通用折叠块定义未动
    `"/guide/status"` / `"/guide/claim"` / `"/week/claim"`  ← 三端点未动
    `\u4e03\u65e5\u7b51\u57fa`        ← 「七日筑基」称号串未动
    `/*[r177adv]*/` / `/*[r179advlog]*/`  ← 更早几环的标记（与指引无关，稳定）
  ★ 不钉本批邻居：**绝不**钉 `[r180adv]` / `[r183exp]` / `[r185farm]` / `[r188med]` /
    `[r184wudao]` / `[r181equip]` 等（这些是并行补丁会新增/改写的形态，本环无权断言）——
    吸取本批 yl_r188_ext.py 把 `[r180adv]` 钉成 `expect==0` 导致集成 ABORT 的教训。

==============================================================================
三、契约（照 localtest/yl_r184_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（就地写回）/ `--check`（只校验不写盘）/ `--selftest`（内存自证）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落
    `<src>.bak-r187-<时刻>`。幂等：产物含 `/*[r187guide]*/` ⇒ SKIP（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 行为探针（node 真跑）：从**打后产物**里抽出 R79Box 的数组字面量真执行，断言
    ① 行的全部数字序列 == 服务端 GUIDE_STEPS 口径、② 行 == WEEK_REWARDS 口径
    （证明「说明」与「实发」逐值一致）。

==============================================================================
四、自测记录（本机实测，命令 + 结果）
==============================================================================
  PY   = C:/Users/27026/.workbuddy-ai/binaries/python/versions/3.13.12/python.exe
  NODE = PATH 上的 node（22.22.2）
  TMP  = 系统临时目录副本（跑完删）
  [1] --check 全绿；[2] 对 TMP 副本真实写回；[3] node --check rc=0；[4] 复跑 SKIP(rc=3)；
  [5] 删副本与 .bak。详见交付汇报。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '[r187guide]'
MARK = '/*[r187guide]*/'

# --------------------------------------------------------------------------- 锚点字面量（\u 保持两字符 backslash+u，与产物字节一致）

# ① 里程碑行（R-123 形态，实测 count==1；本环只改其中 3 个数字）
S1_OLD = (rb'\u2460 \u91cc\u7a0b\u7891\uff1a\u521b\u5efa\u89d2\u8272 2000 / \u603b\u7b49\u7ea7 3 \u5f97 3000'
          rb' / \u603b\u7b49\u7ea7 9 \u5f97 6000 / \u603b\u7b49\u7ea7 10 \u5f97 8000 / \u52a0 1 \u4f4d\u597d\u53cb 3000'
          rb' / \u62dc\u5e08 6000 / \u603b\u7b49\u7ea7 19 \u5f97 20000 / \u7ed3\u9053\u4fa3 12000\uff0c'
          rb'\u8fbe\u6807\u540e\u624b\u52a8\u9886\u53d6\u3001\u5404\u4e00\u6b21\u6027\u3002')
# ① 里程碑行（R-187 新形态：6000→8600 / 8000→9900 / 20000→61000，逐字等于 srv GUIDE_STEPS）
S1_NEW = (rb'\u2460 \u91cc\u7a0b\u7891\uff1a\u521b\u5efa\u89d2\u8272 2000 / \u603b\u7b49\u7ea7 3 \u5f97 3000'
          rb' / \u603b\u7b49\u7ea7 9 \u5f97 8600 / \u603b\u7b49\u7ea7 10 \u5f97 9900 / \u52a0 1 \u4f4d\u597d\u53cb 3000'
          rb' / \u62dc\u5e08 6000 / \u603b\u7b49\u7ea7 19 \u5f97 61000 / \u7ed3\u9053\u4fa3 12000\uff0c'
          rb'\u8fbe\u6807\u540e\u624b\u52a8\u9886\u53d6\u3001\u5404\u4e00\u6b21\u6027\u3002')
# ② 七日礼行（服务端未变 ⇒ 本环一字不动，仅作整串锚点的一部分）
S2 = (rb'\u2461 \u4e03\u65e5\u793c\uff1a\u4ee5\u9996\u6b21\u5b58\u6863\u65e5\u4e3a\u7b2c 1 \u5929\uff0c'
      rb'\u9010\u65e5\u53ef\u9886 2000 / 3000 / 4000 / 6000 / 8000 / 12000 / 15000 \u7075\u77f3\uff0c'
      rb'\u7b2c 7 \u5929\u53e6\u8d60\u79f0\u53f7\u300c\u4e03\u65e5\u7b51\u57fa\u300d\u3002')

E1_OLD = b'YlxwR79Box("\\u4ed9\\u9014\\u6307\\u5f15", ["' + S1_OLD + b'", "' + S2 + b'"]'
E1_NEW = (b'YlxwR79Box("\\u4ed9\\u9014\\u6307\\u5f15", [' + MARK.encode('ascii')
          + b'"' + S1_NEW + b'", "' + S2 + b'"]')

REPS = [
    ('R187-E1 指引玩法说明①里程碑行数字同步', E1_OLD.decode('ascii'), E1_NEW.decode('ascii')),
]

# 冻结针脚：本环只动 E1 一处，下列既有形态必须逐字在位（对**原件**校验，全 ASCII）
FREEZE = [
    ('function YlxwTGuide() {', 1),                       # 指引面板本体未动
    ('function YlxwR79Box(t, L) {', 1),                   # 通用折叠块定义未动
    ('"/guide/status"', 1),                               # 状态端点未动
    ('"/guide/claim"', 1),                                # 领取端点未动
    ('"/week/claim"', 1),                                 # 七日端点未动
    ('\\u4e03\\u65e5\\u7b51\\u57fa', 1),                  # 「七日筑基」称号串未动
    ('/*[r177adv]*/', 1),                                 # R-177 在位标记（更早环）
    ('/*[r179advlog]*/', 1),                              # R-179 在位标记（更早环）
]

# 服务端权威值（srv/index_v28.ts @12777-12791，本环同步的「真值」）
SRV_GUIDE = [2000, 3000, 8600, 9900, 3000, 6000, 61000, 12000]
SRV_WEEK = [2000, 3000, 4000, 6000, 8000, 12000, 15000]
# 打后 ① / ② 行内「全部数字」的期望序列（含等级门槛/序号）
EXP_N1 = [2000, 3, 3000, 9, 8600, 10, 9900, 1, 3000, 6000, 19, 61000, 12000]
EXP_N2 = [1, 2000, 3000, 4000, 6000, 8000, 12000, 15000, 7]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R187·幂等标记唯一', MARK, 1, '==', '[r187guide] 恰好 1 处'),
        # ---- 新形态在位（3 个新数字）----
        ('R187·lv9 说明=8600', '\\u603b\\u7b49\\u7ea7 9 \\u5f97 8600', 1, '==', '与服务端 GUIDE_STEPS 一致'),
        ('R187·zhuji 说明=9900', '\\u603b\\u7b49\\u7ea7 10 \\u5f97 9900', 1, '==', '同上'),
        ('R187·jindan 说明=61000', '\\u603b\\u7b49\\u7ea7 19 \\u5f97 61000', 1, '==', '同上'),
        ('R187·新①行整串在位', S1_NEW.decode('ascii'), 1, '==', '整行逐字'),
        # ---- 旧形态清零 ----
        ('R187·旧 lv9=6000 清零', '\\u603b\\u7b49\\u7ea7 9 \\u5f97 6000', 0, '==', '旧值不得残留'),
        ('R187·旧 zhuji=8000 清零', '\\u603b\\u7b49\\u7ea7 10 \\u5f97 8000', 0, '==', '旧值不得残留'),
        ('R187·旧 jindan=20000 清零', '\\u603b\\u7b49\\u7ea7 19 \\u5f97 20000', 0, '==', '旧值不得残留'),
        ('R187·旧①行整串清零', S1_OLD.decode('ascii'), 0, '==', '旧整行必须消失'),
        ('R187·旧R79Box调用形态清零', E1_OLD.decode('ascii'), 0, '==', '整串替换 ⇒ 防重复注入'),
        # ---- 未动的稳定面 ----
        ('R187·②七日礼行未动', S2.decode('ascii'), 1, '==', '服务端 WEEK_REWARDS 未变'),
        ('R187·指引面板本体未动', 'function YlxwTGuide() {', 1, '==', ''),
        ('R187·折叠块定义未动', 'function YlxwR79Box(t, L) {', 1, '==', ''),
        ('R187·七日筑基称号未动', '\\u4e03\\u65e5\\u7b51\\u57fa', 1, '==', ''),
    ]
    for needle, cnt in FREEZE:
        g.append(('冻结 ' + needle[:30], needle, cnt, '==', '冻结既有形态'))
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
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_run(js):
    node = _find_node()
    if not node:
        return None, None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        return r.returncode, r.stdout.decode('utf-8', 'replace'), r.stderr.decode('utf-8', 'replace')
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


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


def _extract_r79_array(text):
    """抽出「仙途指引」R79Box 的数组字面量源码（含 [ ]）。

    注意：幂等标记 `/*[r187guide]*/` 自带一个 `]` ⇒ 不能取「第一个 ]」，
    而要取数组闭合的 `])`（两条说明串内实测无 `]`，故第一个 `])` 即数组尾）。
    """
    key = 'YlxwR79Box("\\u4ed9\\u9014\\u6307\\u5f15", '
    i = text.find(key)
    if i < 0:
        return None
    j = text.find('[', i)
    k = text.find('])', j)
    if j < 0 or k < 0:
        return None
    return text[j:k + 1]


def _guide_probe(patched_text):
    """真执行打后产物的说明数组，断言 ① / ② 行内全部数字 == 服务端口径。"""
    arr = _extract_r79_array(patched_text)
    if arr is None:
        return False, '仙途指引 R79Box 数组未找到'
    js = (
        'var arr = %s;\n'
        'function chk(n,c){if(!c)throw new Error(n);}\n'
        'chk("arr len", Array.isArray(arr) && arr.length >= 2);\n'
        'function nums(s){ return (String(s).match(/[0-9]+/g)||[]).map(Number); }\n'
        'var n1 = nums(arr[0]), n2 = nums(arr[1]);\n'
        'var EXP1 = %s, EXP2 = %s;\n'
        'var SRVG = %s, SRVW = %s;\n'
        'chk("n1 len", n1.length===EXP1.length);\n'
        'for(var i=0;i<EXP1.length;i++){ if(n1[i]!==EXP1[i]) throw new Error("n1["+i+"]="+n1[i]+" != "+EXP1[i]); }\n'
        'chk("n2 len", n2.length===EXP2.length);\n'
        'for(var j=0;j<EXP2.length;j++){ if(n2[j]!==EXP2[j]) throw new Error("n2["+j+"]="+n2[j]+" != "+EXP2[j]); }\n'
        '// 交叉核对：① 行里的奖励序列 == 服务端 GUIDE_STEPS；② 行里的灵石序列 == WEEK_REWARDS\n'
        'var g = [n1[0], n1[2], n1[4], n1[6], n1[8], n1[9], n1[11], n1[12]];\n'
        'chk("guide rewards len", g.length===SRVG.length);\n'
        'for(var k=0;k<SRVG.length;k++){ if(g[k]!==SRVG[k]) throw new Error("guide["+k+"]="+g[k]+" != "+SRVG[k]); }\n'
        'var w = [n2[1], n2[2], n2[3], n2[4], n2[5], n2[6], n2[7]];\n'
        'chk("week len", w.length===SRVW.length);\n'
        'for(var m=0;m<SRVW.length;m++){ if(w[m]!==SRVW[m]) throw new Error("week["+m+"]="+w[m]+" != "+SRVW[m]); }\n'
        'console.log("guide-probe OK: ①=" + JSON.stringify(g) + "  ②=" + JSON.stringify(w) + " (说明==服务端实发)");\n'
    ) % (arr, EXP_N1, EXP_N2, SRV_GUIDE, SRV_WEEK)
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:400]
    return True, so.strip()


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 说明探针。"""
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r187] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r187] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r187] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r187] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r187] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r187] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _guide_probe(out)
    if ok is False:
        print('[r187] SELFTEST FAIL guide-probe: %s' % pmsg)
        return 1
    print('[r187]   guide-probe -> %s' % pmsg)
    print('[r187] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(gates()), len(out) - len(s0), nmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r187] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r187] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r187] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r187] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r187] round-trip mismatch：除改动点外字节被改动')
        return 1
    rc, node = _node_check(out)
    if rc not in (None, 0):
        print('[r187] node --check FAIL rc=%s' % rc)
        return 1

    if args.check:
        print('[r187] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r187-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r187] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
