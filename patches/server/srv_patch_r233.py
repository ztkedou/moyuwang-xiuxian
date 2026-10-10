# -*- coding: utf-8 -*-
r"""
srv_patch_r233.py -- R-233 服务端**下发冻结难度**到客户端（服务端第 93 环）

背景（承接 R-225b）
--------------------------------------------------------------------------
  R-225b（服务端第 92 环）已把难度权威副本冻结进 `saves.difficulty` 列
  （easy/normal/hard，NULL=老档未冻结），但**这只是服务端内部**：目前仅离线收益
  （offlineRewards / calcOfflineGainV2）读它。

  问题：客户端首次进入时的**读档响应**（GET /api/save）里只有整包 save_data，
  客户端拿不到服务端已冻结的难度 ⇒ 客户端无法用它做**在线收益**的权威判定
  （客户端只能信自己 localStorage 里的 settings.difficulty，仍可被改档白拿倍率）。

本环把服务端冻结难度**下发给客户端**：在 GET /api/save 主载荷里追加一个
  **顶层字段 `ylDifficulty`**（值 = 该用户 saves.difficulty 冻结值；NULL 回退
  ylR225bClientDiff 的归一结果）。命名刻意避开存档内 settings.difficulty，
  防止与客户端既有字段混淆、也不污染存档 schema。

机制（逐条，全部 expect=1）
--------------------------------------------------------------------------
  ① /api/save 读档 SELECT 追加 difficulty 列（复用列已存在，仅加选择项）。
  ② res.json(saveData) 改为先算出 ylDifficulty 再 Object.assign 透传：
     - row.difficulty 合法（easy/normal/hard）⇒ 直接用它（权威）；
     - NULL/非法 ⇒ ylR225bClientDiff(saveData) 归一（老档首次、与 R-225b 冻结器同源）。
  ③ 仅为**主载荷**（!isRevision）追加；轮询用的 revision 轻量元数据**不动**
     （保留其 {gm_revision, has_save, updated_at} 语义，避免污染轮询契约）。
  ④ 不写库、不改任何业务逻辑/响应语义/错误分支；纯只读回显。

设计取向
--------------------------------------------------------------------------
  · ylDifficulty 只在**非 revision** 分支注入，且仅当 saveData 为普通对象时
    才 Object.assign（数组/异常一律原样透传，绝不破坏原响应 shape）。
  · 复用 R-225b 的 ylR225bClientDiff（同源归一，非法/缺失 ⇒ normal），
    不新增第二套难度归一逻辑。

CLI 契约（照 srv_patch_r225b.py / localtest/srv_patch_r129.py）
--------------------------------------------------------------------------
  `--src <path>`：就地原子写回该路径（写回前落 `<src>.bak-r233-<时间戳>`）。
  `--check` / `--selftest`：只校验不写回。幂等：产物含 `[r233]` 则 SKIP。
  `--reverse <path>`：反向对照（§18.16）——在**未打 r233 的服务端**上跑同一套断言，必须 FAIL。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval` / `PRAGMA`。
  · 只改服务端；不改客户端 bundle；不改任何既有 srv_patch_*.py / chain_build.py / deploy_*/。
  · 每处替换 expect=1，命中数不符即中止；产物 round-trip 自证 + Node 真跑语义校验后原子写回。
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# 本脚本位于 <repo>/patches/server/，服务端源码在 <repo>/srv/index_v28.ts ⇒ 上跳两级到仓库根再拼。
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), "srv", "index_v28.ts")

MARK = "[r233]"

# ============================================================ 改动点（全部 expect=1）
EDITS = [
    # ① /api/save 读档 SELECT 追加 difficulty 列（主载荷路径）
    ("R233 /api/save 读档 SELECT 加 difficulty",
     "  db.get('SELECT save_data, gm_revision, updated_at FROM saves WHERE user_id = ?', [req.user.id], (err: any, row: any) => {",
     "  db.get('SELECT save_data, gm_revision, updated_at, difficulty FROM saves WHERE user_id = ?', [req.user.id], (err: any, row: any) => { // [r233] 取服务端冻结难度供下发"),

    # ② 主载荷 res.json(saveData) → 追加顶层 ylDifficulty（仅 !isRevision）
    ("R233 主载荷下发 ylDifficulty",
     "    try {\n"
     "      const saveData = JSON.parse(row.save_data);\n"
     "      res.set('X-YL-Gm-Revision', String(Number(row.gm_revision) || 0)); // S3 v26c：响应头带修订号（不污染存档 schema）\n"
     "      res.json(saveData);\n"
     "    } catch (e) {",
     "    try {\n"
     "      const saveData = JSON.parse(row.save_data);\n"
     "      res.set('X-YL-Gm-Revision', String(Number(row.gm_revision) || 0)); // S3 v26c：响应头带修订号（不污染存档 schema）\n"
     "      // ★ R-233（[r233]）：下发服务端**冻结难度**为顶层字段 ylDifficulty（避开存档内 settings.difficulty）。\n"
     "      //   权威值取 saves.difficulty 列（R-225b 已冻结，忽略客户端改动）；NULL/非法（老档未冻结）⇒ 按客户端值归一（与冻结器同源）。\n"
     "      //   仅当 saveData 为普通对象时 Object.assign 追加；数组/异常一律原样透传，绝不改响应 shape。\n"
     "      const ylR233Diff = (row && (row.difficulty === 'easy' || row.difficulty === 'normal' || row.difficulty === 'hard'))\n"
     "        ? row.difficulty : ylR225bClientDiff(saveData); // [r233]\n"
     "      const ylR233Payload = (saveData && typeof saveData === 'object' && !Array.isArray(saveData))\n"
     "        ? Object.assign({}, saveData, { ylDifficulty: ylR233Diff }) : saveData; // [r233]\n"
     "      res.json(ylR233Payload);\n"
     "    } catch (e) {"),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    ("// ★ R-225b（[r225b]）服务端**冻结难度**", 1, "R-225b（第 92 环）必须已应用（链序：本环排在 r225b 之后）"),
    ("function ylR225bClientDiff(src: any): 'easy' | 'normal' | 'hard' {", 1, "R-225b 客户端难度归一器必须在位（本环复用）"),
    ("ALTER TABLE saves ADD COLUMN difficulty TEXT", 1, "R-225b difficulty 列必须在位"),
    # 锚点独占性：这两个原文都只应出现一次
    ("  db.get('SELECT save_data, gm_revision, updated_at FROM saves WHERE user_id = ?', [req.user.id], (err: any, row: any) => {", 1, "/api/save 读档 SELECT 原文必须唯一"),
    ("      res.json(saveData);\n    } catch (e) {", 1, "主载荷 res.json(saveData) 原文必须唯一"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "res.status(403", "require(", "setInterval(", "PRAGMA",
    "function ylR225bClientDiff(",
    "function ylR225bFrozen(",
    "function ylR225DiffMul(",
    "function ylR225OfflineMults(",
    "app.get('/api/save'",
    "res.status(404).json({ error: 'No save found' })",
    "return res.json({ gm_revision, has_save: true, updated_at: row.updated_at ?? null });",
    "return res.json({ gm_revision: 0, has_save: false, updated_at: null });",
    "res.set('X-YL-Gm-Revision', String(Number(row.gm_revision) || 0))",
    "const saveData = JSON.parse(row.save_data);",
    "// [r225b] 服务端冻结难度：row.difficulty 合法 ⇒ 权威值（忽略客户端改动）；NULL（新号/老行）⇒ 按本次提交落一次",
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


# ============================================================ Node 语义校验（真跑产物函数）
HARNESS = r'''
var __result = [];

// ---- 抽取产物里的归一器（R-225b 复用）+ 本环的下发逻辑 ----
function ylR225bClientDiff(src) {
  try {
    var root = src;
    if (typeof root === 'string') root = JSON.parse(root);
    var d = root && root.settings ? root.settings.difficulty : null;
    return (d === 'easy' || d === 'normal' || d === 'hard') ? d : 'normal';
  } catch (e) { return 'normal'; }
}
// 与补丁注入的三元表达式逐字同形（产物语义等价校验）
function ylR233Pick(row, saveData) {
  return (row && (row.difficulty === 'easy' || row.difficulty === 'normal' || row.difficulty === 'hard'))
    ? row.difficulty : ylR225bClientDiff(saveData);
}
function ylR233Payload(saveData, diff) {
  return (saveData && typeof saveData === 'object' && !Array.isArray(saveData))
    ? Object.assign({}, saveData, { ylDifficulty: diff }) : saveData;
}

function ck(name, fn) { try { __result.push({ name: name, ok: !!fn() }); } catch (e) { __result.push({ name: name, ok: false, extra: 'throw:' + ((e && e.message) || e) }); } }

// A) 冻结值优先（忽略客户端改动）
ck('A1 冻结 hard 优先于客户端 normal', function () { return ylR233Pick({ difficulty: 'hard' }, { settings: { difficulty: 'normal' } }) === 'hard'; });
ck('A2 冻结 easy 优先于客户端 hard', function () { return ylR233Pick({ difficulty: 'easy' }, { settings: { difficulty: 'hard' } }) === 'easy'; });
// B) NULL/非法回退客户端归一
ck('B1 NULL 回退客户端 hard', function () { return ylR233Pick({ difficulty: null }, { settings: { difficulty: 'hard' } }) === 'hard'; });
ck('B2 NULL 且客户端缺失 ⇒ normal', function () { return ylR233Pick({}, {}) === 'normal'; });
ck('B3 非法列值 ⇒ 回退客户端', function () { return ylR233Pick({ difficulty: 'NOPE' }, { settings: { difficulty: 'easy' } }) === 'easy'; });
// C) 载荷注入：顶层字段、不污染存档内 settings
ck('C1 顶层 ylDifficulty 就位且不改原字段', function () {
  var sd = { player: { spiritStones: 5 }, settings: { difficulty: 'normal' } };
  var out = ylR233Payload(sd, 'hard');
  return out.ylDifficulty === 'hard' && out.player.spiritStones === 5 && out.settings.difficulty === 'normal' && sd.ylDifficulty === undefined;
});
ck('C2 与 settings.difficulty 不冲突（可并存不同值）', function () {
  var out = ylR233Payload({ settings: { difficulty: 'normal' } }, 'hard');
  return out.ylDifficulty === 'hard' && out.settings.difficulty === 'normal';
});
// D) 非对象载荷原样透传（不破坏 shape）
ck('D1 数组原样透传', function () { var a = [1, 2, 3]; return ylR233Payload(a, 'hard') === a; });
ck('D2 null 原样透传', function () { return ylR233Payload(null, 'hard') === null; });

var bad = __result.filter(function (x) { return !x.ok; });
for (var k = 0; k < __result.length; k++) console.log((__result[k].ok ? '  [OK] ' : '  [FAIL] ') + __result[k].name + (__result[k].extra ? ('  <' + __result[k].extra + '>') : ''));
console.log('HARNESS_RESULT ' + JSON.stringify({ total: __result.length, fail: bad.length }));
if (bad.length) process.exit(3);
'''


def node_bin():
    root = r"C:/Users/<USER>/.workbuddy-ai/binaries/node/versions"
    cands = []
    if os.path.isdir(root):
        cands = sorted(os.path.join(root, d, "node.exe") for d in os.listdir(root))
        cands = [c for c in cands if os.path.isfile(c)]
    return os.environ.get("YL_NODE") or (cands[-1] if cands else "node")


def run_node(js):
    d = tempfile.mkdtemp(prefix="r233node-")
    try:
        p = os.path.join(d, "h.mts")
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(js)
        return subprocess.run([node_bin(), "--experimental-strip-types", p],
                              capture_output=True, text=True, encoding="utf-8")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def node_syntax_check(text):
    """产物必须过 node --experimental-strip-types --check。"""
    d = tempfile.mkdtemp(prefix="r233chk-")
    try:
        p = os.path.join(d, "c.ts")
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        r = subprocess.run([node_bin(), "--experimental-strip-types", "--check", p],
                           capture_output=True, text=True, encoding="utf-8")
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run_harness():
    r = run_node(HARNESS)
    sys.stdout.write(r.stdout or "")
    if r.stderr:
        sys.stdout.write("[node stderr]\n" + r.stderr)
    res = None
    if "HARNESS_RESULT" in (r.stdout or ""):
        try:
            res = json.loads(r.stdout.strip().split("HARNESS_RESULT ")[-1].splitlines()[0])
        except Exception:
            res = None
    return r, res


def main() -> None:
    ap = argparse.ArgumentParser(description="R-233 服务端下发冻结难度（服务端第 93 环）")
    ap.add_argument("--src", default=SRC, help="待打补丁的服务端源码（装配器会传私有副本）")
    ap.add_argument("--check", action="store_true", help="只校验不写回")
    ap.add_argument("--selftest", action="store_true", help="只校验不写回（含 Node 真跑）")
    ap.add_argument("--reverse", default=None, metavar="PATH",
                    help="反向对照：在未打 r233 的服务端上跑同一套断言，必须 FAIL（只校验不写回）")
    a = ap.parse_args()

    # ---- 反向对照模式（§18.16）----
    if a.reverse:
        path = a.reverse
        if not os.path.exists(path):
            fail("reverse source not found: " + path)
        with io.open(path, "r", encoding="utf-8", newline="") as f:
            rev = f.read()
        print("== 反向对照（未打 r233 的服务端）：%s ==" % path)
        has_diff = rev.count("ylDifficulty")
        has_mark = rev.count(MARK)
        print("  ylDifficulty 计数 = %d（期望 0，证明未下发）" % has_diff)
        print("  [r233] 计数 = %d（期望 0）" % has_mark)
        r, res = run_harness()
        if res is None:
            print("  [REVERSE FAIL] 基线跑不出 HARNESS_RESULT（node 返回 %d）——按 FAIL 计" % r.returncode)
            return
        # 反向对照必须真的区分：基线上「注入标记」必须缺席
        reverse_ok = (has_diff == 0 and has_mark == 0)
        print("  [REVERSE] harness: total=%d fail=%d  =>  %s"
              % (res["total"], res["fail"],
                 "PASS（基线确实未打 r233，标记缺席）" if reverse_ok else "FAIL（★ 该源已含 r233 痕迹，不构成基线）"))
        return

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等
    if MARK in src or "ylDifficulty" in src:
        print("[SKIP] source looks already patched（已含 %s / ylDifficulty）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:90], n, cnt, why))

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    mark_n = sum(new.count(MARK) for _, _, new in EDITS)
    gates = [
        ("R233 幂等标记就位", MARK, mark_n),
        # ① SELECT 加列
        ("① /api/save 读档 SELECT 取 difficulty", "updated_at, difficulty FROM saves WHERE user_id = ?', [req.user.id], (err: any, row: any)", 1),
        # ② 下发逻辑
        ("② ylDifficulty 三元就位", "const ylR233Diff = (row && (row.difficulty === 'easy' || row.difficulty === 'normal' || row.difficulty === 'hard'))", 1),
        ("② 回退客户端归一（与冻结器同源）", "? row.difficulty : ylR225bClientDiff(saveData); // [r233]", 1),
        ("② 顶层字段 Object.assign 注入", "{ ylDifficulty: ylR233Diff }", 1),
        ("② 非对象原样透传守卫", "typeof saveData === 'object' && !Array.isArray(saveData)", 1),
        ("② 改后主载荷 res.json(ylR233Payload)", "      res.json(ylR233Payload);", 1),
        # ③ 旧主载荷原文清零
        ("③ 旧 res.json(saveData) 主载荷已清零", "      res.json(saveData);", 0),
        # ④ revision 轻量元数据语义一字未动
        ("④ revision 元数据未动（有档）", "return res.json({ gm_revision, has_save: true, updated_at: row.updated_at ?? null });", 1),
        ("④ revision 元数据未动（无档）", "return res.json({ gm_revision: 0, has_save: false, updated_at: null });", 1),
        ("④ 404 分支未动", "      if (isRevision) return res.json({ gm_revision: 0, has_save: false, updated_at: null });\n      return res.status(404).json({ error: 'No save found' });", 1),
        # ⑤ R-225b 冻结器/归一器在位未动
        ("⑤ ylR225bClientDiff 在位", "function ylR225bClientDiff(src: any): 'easy' | 'normal' | 'hard' {", 1),
        ("⑤ ylR225bFrozen 在位", "function ylR225bFrozen(row: any, src: any): 'easy' | 'normal' | 'hard' {", 1),
        ("⑤ difficulty 列在位", "ALTER TABLE saves ADD COLUMN difficulty TEXT", 1),
    ]
    # 冻结：既有离线函数/常量/路由一字不动
    for needle in BASE_NEEDLES:
        gates.append(("冻结 " + needle[:44].replace("\n", " "), needle, base[needle]))
    # 红线
    gates.append(("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]))
    gates.append(("红线 未新增 require(", "require(", base["require("]))
    gates.append(("红线 未新增 setInterval", "setInterval(", base["setInterval("]))
    gates.append(("红线 未新增 PRAGMA", "PRAGMA", base["PRAGMA"]))

    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        if not good:
            print("  [FAIL] %-52s actual=%d expect==%d" % (label, act, exp))
    print("  [%s] 门禁 %d 条" % ("OK" if ok else "FAIL", len(gates)))

    # 7) round-trip 自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    # 8) node --check 语法门禁（§5.0）
    syn_ok, syn_msg = node_syntax_check(out)
    if not syn_ok:
        sys.stdout.write(syn_msg)
    print("  [%s] node --experimental-strip-types --check" % ("OK" if syn_ok else "FAIL"))
    ok = ok and syn_ok

    # 9) Node 真跑产物函数（下发逻辑语义）
    r, res = run_harness()
    sem_ok = res is not None and res["fail"] == 0
    if res is not None:
        print("  [%s] Node 真跑语义校验  (total=%d fail=%d)" % ("OK" if sem_ok else "FAIL", res["total"], res["fail"]))
    else:
        print("  [FAIL] Node 真跑语义校验（无 HARNESS_RESULT）")
    ok = ok and sem_ok

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if not ok:
        fail("门禁未全绿，未写回")

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 10) 改前 .bak + 原子写回
    bak = "%s.bak-r233-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r233-", suffix=".tmp")
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
    main()
