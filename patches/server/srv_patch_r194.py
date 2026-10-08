# -*- coding: utf-8 -*-
r"""
srv_patch_r194.py -- R-194 悟道心得「随机加一种道」（服务端环 · 方案 A）

  ★ 用户原话（逐字，唯一依据）：
    「历练这个悟道经验和奇遇绑定触发成功了，但是每次都加的是血道第一个，这个触发要
      变成随机加一种道的经验，而不是固定第一个。」
  ★ team-lead 裁决（逐字）：走**方案 A** —— 「按字面就是十道均匀；而且炼气期池恒为 1，
    『仅已开放』这条路根本满足不了他的诉求」。门槛越界已认可。

根因（本环取证结论）
--------------------------------------------------------------------------
  「每次都血道」**不是写死取第一个**，而是「只在**本人已开放**的道里随机」：
    · `srv/index_v28.ts:6832` `const WUDAO_DAOS = {`（顺序：pill 血道 第一 … tame 丰道）
    · `srv/index_v28.ts:6899` `const WUDAO_DAO_REALM_GATE = { pill: 0, sword: 1, body: 1,
        spell: 2, edge: 2, shadow: 3, armor: 3, devour: 3, array: 4, tame: 6 };`
        ★ 血道门槛=0 ⇒ **炼气期唯一开放** ⇒ `open=['pill']`、`pool=['pill']` ⇒ 恒血道。
    · 客户端 `YlxwWudaoEnlighten` POST **空 body `{}`**、不传 dao，服务端也不读 body
      ⇒ 客户端无权选道（本环**不集成**客户端半边 `localtest/yl_r194_ext.py`）。
    · git blame：该选道逻辑自 b9600061（R-165 / 0.9.25）起就在；线上服务端 md5
      `e12f4ebc0d1e6aa98d9c9ce1b71d998b` 与 HEAD 一致 ⇒ 线上就是这个逻辑。

改法（唯一一处 · srv/index_v28.ts:9023-9026）
--------------------------------------------------------------------------
  改前（4 行）：
      const keys = Object.keys(WUDAO_DAOS);
      const open = keys.filter((k) => realmIdx >= wudaoDaoGateRealm(k));
      const pool = open.length > 0 ? open : [keys[0]];
      const dao = pool[Math.min(pool.length - 1, Math.max(0, Math.floor(Math.random() * pool.length)))];
  改后（2 行）：
      const keys = Object.keys(WUDAO_DAOS);
      const dao = keys[Math.floor(Math.random() * keys.length)]; /*[r194dao]*/

  ★ 等价于 team-lead 指定的 `Object.keys(WUDAO_DAOS)[Math.floor(Math.random()*Object.keys(WUDAO_DAOS).length)]`；
    **单次 `Math.random()`**，未引入额外调用。
  ★ 其余**一律不动**：`WUDAO_DAOS` 表、`WUDAO_DAO_REALM_GATE` 表、`wudaoDaoGateRealm` 函数、
    三层 rateLimit、返回体结构、错误分支（经验发放 / 日志 / 响应）逐字保留。
    （注：`realmIdx`（:9021-9022）在本端点内因此不再被读，但**保持原样不删**——
     它仍在别处使用，且删除属越界改动。）

契约
--------------------------------------------------------------------------
  CLI：--src <path>（就地原子写回；写回前落 .bak-r194-<时间戳>）/ --check / --selftest（只验不写）。
  幂等：产物含 /*[r194dao]*/ ⇒ SKIP（不写盘，rc=0）。
  退出码：0=成功/跳过；1=契约/门禁失败；2=意外异常（IO/写回）。
  · 锚点唯一（count==1）；round-trip 正反双向自证后才原子写回。
  · 工程红线：不新增 require(（ESM 直跑）/ 不新增 res.status(403 / 不动 PRAGMA / 不新增 setInterval。
  · 不改 srv/index_v28.ts 本体（由 chain_build 落盘）；不改任何既有 srv_patch_*.py。
  · --selftest 额外跑 node 真跑「改后选道表达式」N=200,000 ⇒ 报十道分布（应各 ≈10%）。
  ★ 服务端源码的中文为**真实 UTF-8 字符** ⇒ 锚点含中文；本脚本以「整行唯一」保证不歧义。

链上位置
--------------------------------------------------------------------------
  SRV_CHAIN 末环 = srv_patch_r191.py（第 82 环）。team-lead 已排 srv_patch_r196.py 为**第 83 环**，
  ⇒ 本环 `srv_patch_r194.py` = **第 84 环（新末环）**，紧接 r196 之后。
  锚点（:9023-9026）与 r196（R018B_RUNE_* 段 :6716-6768）**零交集**，顺序无关；按 team-lead 要求排在 r196 之后。
"""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（TS 源码合法块注释）
MARK = "/*[r194dao]*/"

# ============================================================ 改动点（1 处）

E1_OLD = (
    "      const keys = Object.keys(WUDAO_DAOS);\n"
    "      const open = keys.filter((k) => realmIdx >= wudaoDaoGateRealm(k));\n"
    "      const pool = open.length > 0 ? open : [keys[0]];\n"
    "      const dao = pool[Math.min(pool.length - 1, Math.max(0, Math.floor(Math.random() * pool.length)))];"
)
E1_NEW = (
    "      const keys = Object.keys(WUDAO_DAOS);\n"
    "      const dao = keys[Math.floor(Math.random() * keys.length)]; " + MARK
)

EDITS = [
    ("R194 选道改十道均匀随机", E1_OLD, E1_NEW),
]

# 改后选道表达式（供 node 分布探针抽取）
DAO_RHS = "keys[Math.floor(Math.random() * keys.length)]"

# ============================================================ 冻结针脚（逐字，绝对在位）

# 十道 key（WUDAO_DAOS 的 10 行；逐字不动）
DAO_LINES = [
    "  pill:   { name: '\u8840\u9053', stat: 'maxHp',           statName: '\u6c14\u8840', basePct: 2.0, stepPct: 0.5  }, // 1 \u6c14\u8840\uff08\u70bc\u6c14\u671f\u5f00\u653e\uff09",
    "  sword:  { name: '\u5251\u9053', stat: 'attack',          statName: '\u653b\u51fb', basePct: 2.0, stepPct: 0.5  }, // 2 \u653b\u51fb\uff08\u7b51\u57fa\u671f\uff09",
    "  body:   { name: '\u4f53\u9053', stat: 'defense',         statName: '\u9632\u5fa1', basePct: 2.0, stepPct: 0.5  }, // 3 \u9632\u5fa1\uff08\u7b51\u57fa\u671f\uff09",
    "  spell:  { name: '\u6cd5\u9053', stat: 'crit',            statName: '\u66b4\u51fb', basePct: 1.0, stepPct: 0.25 }, // 4 \u66b4\u51fb\uff08\u91d1\u4e39\u671f\uff09",
    "  edge:   { name: '\u950b\u9053', stat: 'critDamage',      statName: '\u66b4\u4f24', basePct: 1.0, stepPct: 0.25 }, // 5 \u66b4\u4f24\uff08\u91d1\u4e39\u671f\u00b7\u65b0\u589e\uff09",
    "  shadow: { name: '\u5f71\u9053', stat: 'dodge',           statName: '\u95ea\u907f', basePct: 1.0, stepPct: 0.25 }, // 6 \u95ea\u907f\uff08\u5143\u5a74\u671f\u00b7\u65b0\u589e\uff09",
    "  armor:  { name: '\u7532\u9053', stat: 'damageReduction', statName: '\u51cf\u4f24', basePct: 1.0, stepPct: 0.25 }, // 7 \u51cf\u4f24\uff08\u5143\u5a74\u671f\u00b7\u65b0\u589e\uff09",
    "  devour: { name: '\u566c\u9053', stat: 'lifesteal',       statName: '\u5438\u8840', basePct: 1.0, stepPct: 0.25 }, // 8 \u5438\u8840\uff08\u5143\u5a74\u671f\u00b7\u65b0\u589e\uff09",
    "  array:  { name: '\u7985\u9053', stat: 'cultivate',       statName: '\u4fee\u70bc', basePct: 1.0, stepPct: 0.25 }, // 9 \u4fee\u70bc\uff08\u5316\u795e\u671f\uff09",
    "  tame:   { name: '\u4e30\u9053', stat: 'gather',          statName: '\u8d44\u6e90', basePct: 1.0, stepPct: 0.25 }, // 10 \u8d44\u6e90\uff08\u957f\u751f\u5883\uff09",
]

DAOS_HEADER = ("const WUDAO_DAOS: Record<string, { name: string; stat: string; statName: string; "
               "basePct: number; stepPct: number }> = {")
GATE_LINE = ("const WUDAO_DAO_REALM_GATE: Record<string, number> = { pill: 0, sword: 1, body: 1, "
             "spell: 2, edge: 2, shadow: 3, armor: 3, devour: 3, array: 4, tame: 6 };")

# /api/wudao/enlighten 的其余逻辑（逐字不动）
ENL_LOGIC = [
    ("app.post('/api/wudao/enlighten',", 1, "端点必须在位"),
    ("const WUDAO_ENL_MIN_INTERVAL_MS = 5000;", 1, "L1 频控常量未动"),
    ("const WUDAO_ENL_HOUR_CAP = 60;", 1, "L2 频控常量未动"),
    ("const WUDAO_ENL_DAY_CAP = 200;", 1, "L3 频控常量未动"),
    ("const WUDAO_INSIGHT_EXP = 10;", 1, "心得经验常量未动"),
    ("      let realmIdx = 0;", 1, "realmIdx 声明保留（本环不删）"),
    ("const added = await wudaoAddExp(userId, dao, WUDAO_INSIGHT_EXP, 'idle');", 1, "经验发放未动"),
    ("if (!added) return res.json({ ok: false, reason: 'fail' });", 1, "失败分支未动"),
    ("ok: true, dao, daoName: WUDAO_DAOS[dao].name, expGain: WUDAO_INSIGHT_EXP,", 1, "响应体未动"),
]

REQUIRES = [
    (DAOS_HEADER, 1, "WUDAO_DAOS 表必须在位（本环冻结）"),
    (GATE_LINE, 1, "WUDAO_DAO_REALM_GATE 十项门槛必须在位（本环冻结）"),
] + [(ln, 1, "十道 key 行必须在位（本环冻结）") for ln in DAO_LINES] + ENL_LOGIC

# 冻结基线（相对计数快照）——★ 仅收「基座必须存在」的针脚；
# `require(` 在本文件基线即为 0（ESM 直跑），故不入此表（红线按常量 0 断言，见 gates）。
BASE_NEEDLES = [
    "res.status(403",
    "setInterval(",
    "PRAGMA",
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out, base):
    """五元组 (label, needle, expect, op, note)。"""
    g = [
        ("R194 幂等标记在位", MARK, 1, "==", "本环已应用"),
        # ── 改后新形态在位 ──
        ("R194 新选道表达式在位", "const dao = keys[Math.floor(Math.random() * keys.length)]; " + MARK,
         1, "==", "十道均匀随机（单次 Math.random）"),
        # ── 旧形态清零 ──
        ("R194 旧 open 过滤清零", "const open = keys.filter((k) => realmIdx >= wudaoDaoGateRealm(k));",
         0, "==", "按已开放过滤必须消失"),
        ("R194 旧 pool 兜底清零", "const pool = open.length > 0 ? open : [keys[0]];",
         0, "==", "keys[0] 兜底必须消失"),
        ("R194 旧 dao 选取清零",
         "const dao = pool[Math.min(pool.length - 1, Math.max(0, Math.floor(Math.random() * pool.length)))];",
         0, "==", "旧池内随机必须消失"),
        # ── 冻结：两张表逐字不动 ──
        ("R194 冻结·WUDAO_DAOS 表头", DAOS_HEADER, 1, "==", "表头未动"),
        ("R194 冻结·门槛表十项", GATE_LINE, 1, "==", "十项门槛值未动"),
    ]
    for i, ln in enumerate(DAO_LINES):
        g.append(("R194 冻结·道 key 行 %d" % (i + 1), ln, 1, "==", "十道 key 逐字未动"))
    # ── 冻结：/api/wudao/enlighten 其余逻辑 ──
    for needle, cnt, why in ENL_LOGIC:
        g.append(("R194 冻结·" + why, needle, cnt, "==", why))
    # ── 工程红线（相对计数）──
    g += [
        ("R194 红线·无新 require", "require(", 0, "==", "ESM 直跑禁 require"),
        ("R194 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403"),
        ("R194 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R194 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
    ]
    return g


def _apply(src):
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)
    return out


def _roundtrip(out, src):
    back = out
    for name, old, new in reversed(EDITS):
        if back.count(new) != 1:
            return False, "逆向：新块出现 %d 次（期望 1）" % back.count(new)
        back = back.replace(new, old, 1)
    return (back == src), "逆向逐字节还原"


def _find_node():
    cand = [os.environ.get("NODE"), shutil.which("node"),
            "C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe",
            "C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe"]
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_run(js):
    node = _find_node()
    if not node:
        return None, None, None
    fd, tmp = tempfile.mkstemp(suffix=".js")
    try:
        with io.open(fd, "w", encoding="utf-8", newline="") as f:
            f.write(js)
        r = subprocess.run([node, tmp], capture_output=True)
        return (r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace"))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def dao_probe(patched, n=200000):
    """node 真跑「改后选道表达式」N 次 ⇒ 报十道分布（应各 ≈10%）。"""
    m = re.search(r"const dao = (keys\[[^\]]*\]);", patched)
    if not m:
        return False, "改后选道表达式未找到"
    rhs = m.group(1)
    if rhs.count("Math.random()") != 1:
        return False, "选道表达式 Math.random() 调用次数 != 1: " + rhs
    # 十道 key 从门槛表解析（与 WUDAO_DAOS 同序：pill 血道 第一 … tame 丰道）
    mg = re.search(r"const WUDAO_DAO_REALM_GATE: Record<string, number> = \{([^}]*)\};", patched)
    keys = re.findall(r"(\w+):\s*\d+", mg.group(1)) if mg else []
    if len(keys) != 10:
        return False, "WUDAO_DAOS key 数 != 10（实得 %d）" % len(keys)
    js = (
        "var keys = " + repr(keys).replace("'", '"') + ";\n"
        "var N = " + str(int(n)) + ";\n"
        "var cnt = {};\n"
        "for (var i = 0; i < N; i++) { var dao = " + rhs + "; cnt[dao] = (cnt[dao] || 0) + 1; }\n"
        "var lines = [], ok = true;\n"
        "for (var j = 0; j < keys.length; j++) {\n"
        "  var k = keys[j], c = cnt[k] || 0, p = c / N;\n"
        "  if (p < 0.09 || p > 0.11) ok = false;\n"
        "  lines.push('  ' + k + '  ' + (p * 100).toFixed(2) + '%');\n"
        "}\n"
        "for (var kk in cnt) { if (keys.indexOf(kk) < 0) ok = false; }\n"
        "if (!ok) { console.error('分布非均匀/越界:\\n' + lines.join('\\n')); process.exit(1); }\n"
        "console.log('R194-DAO 分布(十道, N=' + N + '):\\n' + lines.join('\\n'));\n"
    )
    rc, so, se = _node_run(js)
    if rc is None:
        return None, "node not found (skipped)"
    if rc != 0:
        return False, se.strip()[:400]
    return True, so.strip()


def main():
    ap = argparse.ArgumentParser(description="R-194 悟道心得随机加一种道（服务端环 · 方案 A）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：产物含标记 ⇒ SKIP（不写盘，rc=0）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖（绝对在位）
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点唯一
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线（针脚必须在基座真实存在，防拼错导致冻结静默失效）
    base = {k: src.count(k) for k in BASE_NEEDLES}
    for k in BASE_NEEDLES:
        if base[k] <= 0:
            fail("冻结针脚在基座不存在（拼写错误？）：%r" % k[:90])

    # 5) 应用
    out = _apply(src)

    # 6) 门禁（五元组）
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-46s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证（正向重放一致 + 逆向逐字节还原）
    if out != _apply(src):
        fail("round-trip(正向重构) mismatch")
    rt_ok, rt_msg = _roundtrip(out, src)
    if not rt_ok:
        fail("round-trip(逆向) mismatch：%s" % rt_msg)

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    # 8) 分布实测（--selftest）
    if a.selftest:
        pr_ok, pr_msg = dao_probe(out)
        if pr_ok is False:
            fail("dao-probe: " + pr_msg)
        if pr_msg:
            print("  " + pr_msg.replace("\n", "\n  "))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r194-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r194dao-", suffix=".tmp")
    try:
        with io.open(fd, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print("  已原子写回 %s" % src_path)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        print("[ERROR] %s: %s" % (type(e).__name__, e))
        sys.exit(2)
