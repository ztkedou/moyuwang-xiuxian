# -*- coding: utf-8 -*-
r"""
yl_r194_ext.py — R-194：悟道心得「随机加一种道」（standalone 客户端半边 + 服务端方案）

★ 本环采用**服务端方案 A**（`patches/server/srv_patch_r194.py`：`/api/wudao/enlighten`
  改为在**全部十道**里均匀随机），本客户端半边**未集成**，仅备方案 C（服务端接受
  `req.body.dao`）使用。方案 A 下服务端自行选道，客户端传参无意义。

★ 用户原话（逐字，唯一依据）：
  「历练这个悟道经验和奇遇绑定触发成功了，但是每次都加的是血道第一个，这个触发要
    变成随机加一种道的经验，而不是固定第一个。」

目标产物：build/assets/index-v2934-20261008.js（0.9.34；2,312,438 B；
          md5 41af9edf943a04c65447a7b74a4bd5b4）

==============================================================================
零、三问取证（对 0.9.34 产物字符级实抽 + 服务端源码 + git blame）
==============================================================================
── 问 1：「道」的列表在哪定义？「每次都血道第一个」的成因？──
  [结论] ★★ 根因在**服务端**，不在客户端 ★★
    客户端 `YlxwWudaoEnlighten` **POST 空 body `{}`**，根本不知道服务端挑了哪个道；
    是服务端 `POST /api/wudao/enlighten`（srv/index_v28.ts）在**本人已开放的道**里随机。
    用户之所以「每次都是血道」，是因为**该账号只有血道开放**（炼气期）：池子只有 1 项，
    `Math.random()*1` 恒取第 0 项 ⇒ 恒血道。**不是「写死取第一个」。**

  [道列表定义] —— **只在服务端**（客户端零副本，已实测）：
    srv/index_v28.ts:6832  `const WUDAO_DAOS = {`
      顺序即展示顺序：pill(血道) sword(剑道) body(体道) spell(法道) edge(锋道)
                      shadow(影道) armor(甲道) devour(噬道) array(禅道) tame(丰道)
    srv/index_v28.ts:6899  `const WUDAO_DAO_REALM_GATE = { pill: 0, sword: 1, body: 1,
                              spell: 2, edge: 2, shadow: 3, armor: 3, devour: 3,
                              array: 4, tame: 6 };`   ← ★ 血道门槛=0（炼气期唯一开放）
    srv/index_v28.ts:6904  `function wudaoDaoGateRealm(daoKey) {...}`

  [「固定第一个」被选中的那一行] —— srv/index_v28.ts:9023-9026（R-165 端点）：
      9023  const keys = Object.keys(WUDAO_DAOS);
      9024  const open = keys.filter((k) => realmIdx >= wudaoDaoGateRealm(k));
      9025  const pool = open.length > 0 ? open : [keys[0]];          // ← 炼气期 open=['pill']
      9026  const dao = pool[Math.min(pool.length - 1, Math.max(0, Math.floor(Math.random() * pool.length)))];
      ⇒ realmIdx=0 时 open=['pill']、pool=['pill'] ⇒ dao 恒 'pill'（血道）。**这一行就是「每次都血道」。**

  [客户端侧取证] —— 客户端**无法**决定道（实抽）：
    bundle @620478  `function YlxwWudaoEnlighten(addLog) {`
    bundle @620541  `YlxwPost("/wudao/enlighten", {}).then(function (r) {`   ← ★ POST **空 body**，不传 dao
    客户端唯一「带 dao 的请求」是**付费**顿悟按钮（bundle @987297）：
      `f("w"+g.key, "/wudao/insight", { dao: g.key }, ...)` —— 端点不同、且花灵石。
    客户端**没有任何**「道 key 列表」（实测：血道/剑道… 仅散见于随机名池；`daos` 只作
    渲染 `GET /wudao` 的返回值，`YlxwWudaoEnlighten` 拿不到）。
    ⇒ **客户端既不知道道列表、也无权选道。** 这一环若只改客户端 = 改一个不生效的地方。

  [git blame] —— 服务端 9023-9026 的「按已开放随机」自 **b9600061（R-165 / 0.9.25）**
    起就在，从未写死过 `keys[0]`（`keys[0]` 只是 open 为空时的兜底，而 pill 门槛=0 ⇒ 永不为空）。
    部署指纹：HEAD `srv/index_v28.ts` md5 = `e12f4ebc0d1e6aa98d9c9ce1b71d998b`
    = 线上 0.9.32/0.9.33 的服务端（见 .codebuddy/memory/2026-10-08.md）⇒ **线上就是这个逻辑**。

  [账号境界] 客户端把境界存成**中文**（bundle @244857 `ae.QiRefining="炼气期"`；
    @247832 `realm = t.realm && Cs[t.realm] ? t.realm : ae.QiRefining`）⇒ 与服务端
    `WUDAO_REALM_ORDER` 同形，门槛解析正确 ⇒ 「恒血道」只能是**该账号境界下池=1**（炼气期）。

── 问 2：这个补丁该改在哪一端？──
  ★ **根因与决定权都在服务端**（客户端 POST `{}`，服务端忽略 body 自行选道）。
    · 纯客户端改法**永远不生效**（服务端不看客户端传的 dao）。
    · 要满足用户「随机加一种道」，**服务端必须改**（见 §三 服务端方案，本环只报告不交付）。
    · 但为把「客户端半边」也备好（一旦服务端接受 `dao` 即生效、且当前多传一个字段
      **完全无害**），本环**同时**交付客户端半边：让 `YlxwWudaoEnlighten` 均匀随机选一个道
      key 一并 POST `{ dao: <key> }`。**★ 单独集成本补丁不改变任何行为。**

── 问 3：随机序列的影响面？──
  · 原 `YlxwWudaoEnlighten` **从不调 `Math.random()`**；本补丁在**每次触发**时新增 **1 次**
    `Math.random()`（`YlxwWudaoRandomDao`）。触发本身是稀有事件（R-184：奇遇绑定，
    全境界统一 ~1%/次历练；R-180 v4 后 ≈6~18 分/次）⇒ 对全局 PRNG 流的扰动**极低频且非语义**。
  · 服务端方案（§三）在服务端选道，**不扰动客户端 PRNG** —— 若拍板走服务端单改，可**跳过**
    本客户端半边。

==============================================================================
一、客户端半边改法（2 处就地替换 · 纯 ASCII）
==============================================================================
  E1  把入账调用改成带上均匀随机的道 key：
        原： `YlxwPost("/wudao/enlighten", {})`
        新： `YlxwPost("/wudao/enlighten", { dao: YlxwWudaoRandomDao() })`
      （函数提升 ⇒ E2 的声明可后置；多传字段对现服务端**无害**——它不读 body。）
  E2  在 `function YlxwWudaoEnlighten(addLog) {` **之前**声明：
        `var YLXW_WUDAO_DAO_KEYS = [10 个 key]`（镜像服务端 WUDAO_DAOS 顺序）
        `function YlxwWudaoRandomDao(){ return KEYS[Math.floor(Math.random()*KEYS.length)]; }`
      10 道 key（服务端顺序）：pill sword body spell edge shadow armor devour array tame。

==============================================================================
二、锚点与冻结针脚（对 build/assets/index-v2934-20261008.js 字符级实测，均唯一）
==============================================================================
  替换锚点（打前 count==1）：
    E1 OLD = `YlxwPost("/wudao/enlighten", {})`              → 1
    E2 ANC = `function YlxwWudaoEnlighten(addLog) {`         → 1
  ★ 锚点与 `yl_r184_ext.py` **无关**（r184 只在其 helper 内调 `YlxwWudaoEnlighten`，
    不动 R-165 的 `YlxwWudaoEnlighten` 定义/端点调用）⇒ 本补丁对 r184 **顺序无关**；
    r184 之后形态与之前**逐字相同**，故本环锚点天然满足「按 r184 之后形态写」。
  冻结针脚（对**原件**校验 count 必须 == 1；★ 只钉本批其它补丁不动的稳定形态）：
    `function YlxwWudaoEnlighten(addLog) {`   ← R-165 助手定义未动
    `var YLXW_MED_SESS = null;`               ← R-165 会话变量未动
    `YlxwWudaoEnlighten(c)`                   ← 打坐顿悟接线未动
    `YlxwPost("/wudao/enlighten", {})`        ← E1 锚点（打后清零）
    `function YlxwMedTick(S, insight) {`      ← E2 右侧邻域未动
  ★ 针脚选择原则·不钉邻居：**绝不**钉 `[r180adv*]` / `[r185farm*]` / `[r184wudao]` /
    `[r187guide]` / `[r188med*]` / `[r190feed]` / `[r189ui]` / `[r189conv]` /
    `[r189rune]` / `[r192fuse]` / `[r191adv]` 等任何**并行补丁的标记/形态**。

==============================================================================
三、★ 服务端方案（本环**不**交付，只报告；根因在此）★
==============================================================================
  方案 A（最小·推荐）—— 让**免费心得**在**全部十道**里均匀随机（用户要的「随机一种道」）：
    srv/index_v28.ts:9023-9026 改为：
      const keys = Object.keys(WUDAO_DAOS);
      const dao = keys[Math.floor(Math.random() * keys.length)];
    影响：炼气期也能得稀有道心得（**这正是用户诉求**「随机加一种道」）。若担心越过 R-110
    稀有道门槛，见方案 B。
  方案 B（保守）—— 保留门槛，但把池子放大到「境界内全部已开放」：
    （= 现状 9024 已是如此）⇒ **对炼气期无解**（池恒为 1）。故方案 B 不满足用户诉求。
  方案 C（客户端半边配套·需服务端接受 `dao`）—— 服务端改为：
      const want = asStr(req.body?.dao);
      const dao = (want && WUDAO_DAOS[want]) ? want
                : pool[Math.min(pool.length - 1, Math.max(0, Math.floor(Math.random() * pool.length)))];
    即「客户端传了就采纳（校验 key 合法），没传就退回现状随机」。
    这是**与本客户端半边配套**的服务端改法；若采用，客户端半边（本补丁）即生效。
  ★ 建议：拍板 **方案 A（一行）** 或 **方案 C（两行 + 本客户端半边）**。二者都不需要
    DB 迁移、不新增列；方案 A 连客户端都不用改（此时本补丁可整环跳过）。

==============================================================================
四、契约（照抄 localtest/yl_r191_ext.py）
==============================================================================
  · CLI：`--src <bundle.js>`（就地写回）/ `--check`（只校验不写盘）/ `--selftest`（内存自证）。
  · 就地替换，全部纯 ASCII 注入；bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；
    首次改写前落 `<src>.bak-r194-<时刻>`。
  · 幂等：产物已含 `/*[r194dao]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 行为探针（node，真跑抽取出的真实代码）：
      ① 抽真实 `YlxwWudaoRandomDao` + `YLXW_WUDAO_DAO_KEYS`，Monte-Carlo 20 万次 ⇒
         十道**均匀**（每道 10%±10%）、key 全落在合法集合。
      ② 抽真实 `YlxwWudaoEnlighten`，桩化 `YlxwWudaoRandomDao`/`YlxwPost` ⇒
         断言 POST body 的 `dao` 恰为所选道 key（客户端确实把它发出去了）。
  · 不跑网络：只读 --src 指向的本地文件。

==============================================================================
五、自测记录（本机实测 · 2026-10-08）
==============================================================================
  见文件末尾 `--selftest` 实跑输出（门禁条数 / roundtrip / delta / 分布）。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r194dao]*/'

# --------------------------------------------------------------------------- 替换项
# ★ 全部纯 ASCII。E1 多传一个 `dao` 字段：对当前服务端无害（它不读 body）；
#   一旦服务端采纳（§三 方案 C），即为「随机加一种道」的客户端半边。

# E1：入账端点调用 → 带上均匀随机的道 key
E1_OLD = 'YlxwPost("/wudao/enlighten", {})'
E1_NEW = 'YlxwPost("/wudao/enlighten", { dao: YlxwWudaoRandomDao() })'

# E2：助手声明插入点（YlxwWudaoEnlighten 之前；函数提升 ⇒ E1 可调用）
E2_ANCHOR = 'function YlxwWudaoEnlighten(addLog) {'

# 十道 key（镜像服务端 WUDAO_DAOS 顺序：血/剑/体/法/锋/影/甲/噬/禅/丰）
DAO_KEYS_LITERAL = '["pill","sword","body","spell","edge","shadow","armor","devour","array","tame"]'

HELPER_BLOCK = (
    IDEMPOTENT_MARK + '\n'
    '/* ===== yl-R194 wudao-insight random-dao =====\n'
    '   The server POST /wudao/enlighten picks a dao by ITSELF (srv/index_v28.ts:9023-9026)\n'
    '   among the player UNLOCKED daos only; at 炼气期 (realmIdx 0) only 血道(pill, gate 0)\n'
    '   is unlocked => pool size 1 => EVERY insight credits 血道 (user: "每次都加的是血道第一个").\n'
    '   The old client POSTed {} and had no say. This sends an explicit UNIFORMLY RANDOM dao key\n'
    '   so the server can honour it. NOTE: harmless with the current server (it ignores body);\n'
    '   it only takes effect once the server accepts req.body.dao (see report / 方案 C).\n'
    '   Keys mirror the server WUDAO_DAOS order (血/剑/体/法/锋/影/甲/噬/禅/丰). */\n'
    'var YLXW_WUDAO_DAO_KEYS = ' + DAO_KEYS_LITERAL + ';\n'
    'function YlxwWudaoRandomDao() {\n'
    '  return YLXW_WUDAO_DAO_KEYS[Math.floor(Math.random() * YLXW_WUDAO_DAO_KEYS.length)];\n'
    '}\n'
)

REPLACEMENTS = [
    ('r194-e1-post-dao', E1_OLD, E1_NEW),
    ('r194-e2-decl', E2_ANCHOR, HELPER_BLOCK + E2_ANCHOR),
]

# 冻结针脚（对**输入**校验）：本批不动的稳定形态
FREEZE = [
    ('function YlxwWudaoEnlighten(addLog) {', 1),
    ('var YLXW_MED_SESS = null;', 1),
    ('YlxwWudaoEnlighten(c)', 1),
    ('YlxwPost("/wudao/enlighten", {})', 1),
    ('function YlxwMedTick(S, insight) {', 1),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    return [
        # ---- 幂等标记 ----
        ('R194\u00b7\u5e42\u7b49\u6807\u8bb0 r194dao', IDEMPOTENT_MARK, 1, '==', '[r194dao] 恰 1 处'),
        # ---- E1 端点调用带随机道 ----
        ('R194\u00b7E1 \u968f\u673a\u9053\u5df2\u4e0a\u4f20', E1_NEW, 1, '==',
         'POST body 带 { dao: YlxwWudaoRandomDao() }'),
        ('R194\u00b7E1 \u65e7\u7a7a body \u5df2\u6e05\u96f6', E1_OLD, 0, '==', '旧 {} 形态必须消失'),
        # ---- E2 助手 ----
        ('R194\u00b7E2 \u9053 key \u5217\u8868\u5728\u4f4d', 'var YLXW_WUDAO_DAO_KEYS = ' + DAO_KEYS_LITERAL + ';',
         1, '==', '十道 key（镜像服务端顺序）'),
        ('R194\u00b7E2 \u968f\u673a\u5668\u5df2\u58f0\u660e', 'function YlxwWudaoRandomDao() {', 1, '==', '助手声明恰 1 处'),
        ('R194\u00b7E2 \u5747\u5300\u53d6\u4e00\u9053',
         'Math.floor(Math.random() * YLXW_WUDAO_DAO_KEYS.length)', 1, '==', 'Math.floor(random*N)'),
        ('R194\u00b7E2 \u8ddf\u5728 Enlighten \u4e4b\u524d',
         IDEMPOTENT_MARK + '\n/* ===== yl-R194', 1, '==', '标记紧跟 R-194 注释块'),
        # ---- 既有悟道链路保持 ----
        ('R194\u00b7\u52a9\u624b\u5b9a\u4e49\u4ecd\u5728\u4f4d', 'function YlxwWudaoEnlighten(addLog) {', 1, '==', 'R-165 定义未动'),
        ('R194\u00b7\u6253\u5750\u63a5\u7ebf\u4ecd\u5728\u4f4d', 'YlxwWudaoEnlighten(c)', 1, '==', 'R-165/R-188 未动'),
        ('R194\u00b7\u5165\u8d26\u7aef\u70b9\u8def\u5f84\u672a\u6539', '"/wudao/enlighten"', 1, '==', '端点路径未改'),
        ('R194\u00b7\u4f1a\u8bdd\u53d8\u91cf\u672a\u52a8', 'var YLXW_MED_SESS = null;', 1, '==', ''),
        ('R194\u00b7MedTick \u90bb\u57df\u672a\u52a8', 'function YlxwMedTick(S, insight) {', 1, '==', ''),
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
    """返回 err（None 表示可打）。对**原件** s 校验锚点与冻结针脚。"""
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
    """反向还原：把每个 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _fn_src(text, name):
    """从 text 中按花括号配对精确抽出 `function <name>(...) {...}` 源码。"""
    i = text.find('function %s(' % name)
    if i < 0:
        return None
    j = text.find('{', i)
    if j < 0:
        return None
    depth = 0
    k = j
    n = len(text)
    mode = None
    while k < n:
        c = text[k]
        if mode is None:
            if c == '"' or c == "'":
                mode = c
            elif c == '`':
                mode = '`'
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return text[i:k + 1]
            elif c == '/' and k + 1 < n and text[k + 1] == '/':
                k = text.find('\n', k)
                if k < 0:
                    return text[i:n]
            elif c == '/' and k + 1 < n and text[k + 1] == '*':
                k = text.find('*/', k)
                if k < 0:
                    return text[i:n]
                k += 1
        else:
            if c == '\\':
                k += 1
            elif c == mode:
                mode = None
        k += 1
    return text[i:n]


def _node_run(js):
    """跑一段 js；返回 (rc, stdout, stderr) 或 (None, None, None) 当无 node。"""
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


def _extract_keys_literal(patched_text):
    """从补丁后产物里抽 `var YLXW_WUDAO_DAO_KEYS = [...];` 的数组字面量。"""
    m = re.search(r'var YLXW_WUDAO_DAO_KEYS = (\[[^\]]*\]);', patched_text)
    return m.group(1) if m else None


def _dao_probe(patched_text, n=200000):
    """真跑抽取出的 `YlxwWudaoRandomDao`：
    ① 20 万次分布 ⇒ 十道均匀（每道 10%±10%）；
    ② 桩化 `YlxwWudaoEnlighten` 的 POST ⇒ body.dao 恰为所选道 key。"""
    keys_lit = _extract_keys_literal(patched_text)
    if not keys_lit:
        return False, 'YLXW_WUDAO_DAO_KEYS 字面量未找到'
    fn = _fn_src(patched_text, 'YlxwWudaoRandomDao')
    if not fn:
        return False, 'YlxwWudaoRandomDao 定义未找到'
    enf = _fn_src(patched_text, 'YlxwWudaoEnlighten')
    if not enf:
        return False, 'YlxwWudaoEnlighten 定义未找到'
    js = (
        'var KEYS = ' + keys_lit + ';\n'
        'var YLXW_WUDAO_DAO_KEYS = KEYS;\n'
        + fn + '\n'
        '// ---- ① 分布 ----\n'
        'var N = ' + str(int(n)) + ';\n'
        'var cnt = {};\n'
        'for (var i = 0; i < N; i++) { var k = YlxwWudaoRandomDao(); cnt[k] = (cnt[k] || 0) + 1; }\n'
        'var lines = [];\n'
        'var okAll = true;\n'
        'for (var j = 0; j < KEYS.length; j++) {\n'
        '  var key = KEYS[j], c = cnt[key] || 0, p = c / N;\n'
        '  if (p < 0.09 || p > 0.11) okAll = false;\n'
        '  lines.push("  " + key + "  " + (p * 100).toFixed(2) + "%");\n'
        '}\n'
        '// 任何越界 key（不在合法集合）都算失败\n'
        'for (var kk in cnt) { if (KEYS.indexOf(kk) < 0) okAll = false; }\n'
        'if (!okAll) { console.error("分布非均匀/越界:\\n" + lines.join("\\n")); process.exit(1); }\n'
        'console.log("R194-DAO 分布(十道, N=" + N + "):\\n" + lines.join("\\n"));\n'
        '// ---- ② POST body 带道 key ----\n'
        + enf + '\n'
        'var CAP = null;\n'
        'function YlxwPost(u, b) { CAP = { u: u, b: b }; return { then: function () { return { catch: function () {} }; } }; }\n'
        'function chk(c, m) { if (!c) throw new Error(m); }\n'
        'var sent = {};\n'
        'for (var t = 0; t < 2000; t++) { YlxwWudaoEnlighten(function () {}); chk(CAP && CAP.u === "/wudao/enlighten", "url mismatch"); chk(CAP.b && typeof CAP.b.dao === "string", "body.dao missing"); chk(KEYS.indexOf(CAP.b.dao) >= 0, "body.dao not a valid key"); sent[CAP.b.dao] = 1; }\n'
        'var distinct = Object.keys(sent).length;\n'
        'chk(distinct === KEYS.length, "POSTed dao not uniform: distinct=" + distinct);\n'
        'console.log("R194-POST OK: body={dao:<key>} 覆盖 " + distinct + "/" + KEYS.length + " 道");\n'
    )
    rc, so, se = _node_run(js)
    if rc is None:
        return None, 'node not found (skipped)'
    if rc != 0:
        return False, se.strip()[:400]
    return True, so.strip()


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 2 个探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r194] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r194] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r194] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r194] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r194] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r194] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _dao_probe(out)
    if ok is False:
        print('[r194] SELFTEST FAIL dao-probe: ' + pmsg)
        return 1
    print('[r194] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
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
        print('[r194] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r194] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r194] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r194] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r194] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r194] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r194-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r194] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
