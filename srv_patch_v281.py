# -*- coding: utf-8 -*-
"""
srv_patch_v281.py -- v28 深测回归补丁（0.8.1）服务端生成器

Reads : srv/index_v28.ts   (current source of truth; in-place atomic rewrite)
Writes: srv/index_v28.ts

背景（三条，均由本轮「本机沙盒深度实测」发现并实测复现）
  A) 心法等级 10x 虚高 + 满级后照扣灵石
     `GONGFA_STEP_COST` 被「物价 x10」从 100 提到 1000，但 `gongfaExpToReach(L)`
     仍是旧量纲 `Σ100xi = 50xLx(L+1)`（满级 5500）。而 `/api/gongfa` 展示层用
     `gongfaLevelFromExp(exp)` 推导等级，`/api/gongfa/levelup` 又按 `exp += cost`
     （cost = 1000xL）累加 —— 量纲差 10 倍。
     实测（s5 / ylt_mid）：付 1000 灵石 -> 界面 Lv4；付 3000 -> Lv7；付 6000 -> 显示
     「已满级」。设计上满级需 Σ1000xi = 55000。且 `levelup` 的满级判定读的是
     `player_gongfa.level` 列（此时仅 3），故继续点会**照扣灵石**且等级列继续涨。
     修法：让 exp 曲线随 `GONGFA_STEP_COST` 走（`(STEP/2)xLx(L+1)`），与
     「exp = 累计投入灵石」这一既有语义（见函数注释）一致。
     存量自愈：已写入的 exp 就是 Σ1000xi，改后展示等级 == 实际升级次数 == level 列，
     不削弱任何老档。

  B) `POST /api/save` 无限流（唯一没有限流的写端点）
     实测（flow-1）：20/20 全部 200、0 个 429，持续 54 次/秒。
     叠加 `mins = max(E2_MIN_SAVE_MINS=0.5, dt)` 的下限截断，把「按分钟配额」放大成
     「按请求配额」。本补丁只加限流（纯防护，不动任何收益公式）；配额公式本身属
     数值平衡，交用户拍板（见 报告）。
     限流阈值 120/min：客户端 10s 自动推档 = 6/min，加手动/冲突重推，最坏 ~20/min，
     留 6 倍余量；同时把 54/s 压到 2/s。

  C) `rateLimit` 429 响应不带 `Retry-After`
     客户端 0.8.1 起已按 `Retry-After` 退避（yl_saveretry_ext.py），服务端补齐该头，
     让退避有依据而不是盲等。

Engineering guarantees (any failure => sys.exit(1), no write):
  1. every anchor occurs EXACTLY once in the source;
  2. round-trip equivalence: replacing each new fragment back with its old fragment yields
     the source byte-for-byte;
  3. every newly introduced identifier occurs 0 times in the source;
  4. every INJECTED fragment is pure ASCII;
  5. the source is not already patched.

NOTE（可复现性）：本补丁打在链式产物的**末端**（`index_v28.ts`），且是 in-place。
      若有人从 `index_v27b.ts` 重跑整条链，必须在最后再跑一次本脚本。

Run (cwd = yl-deploy/):
  python srv_patch_v281.py                 # 就地打补丁（原子写）
  python srv_patch_v281.py --check         # 只体检，不写
"""
import argparse
import io
import os
import sys
import hashlib
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ---------------------------------------------------------------------------
# EDITS: (label, old, new)  -- 全部纯 ASCII
# ---------------------------------------------------------------------------
EDITS = [
    # ---- D) rateLimit 提升为函数声明（关键：/api/save 在文件更早处就引用它）----
    #   `const rateLimit = (...) => ...` 位于 :2686，而 /api/save 位于 :1774 —— const 不提升，
    #   模块求值到 :1774 时即抛 `ReferenceError: Cannot access 'rateLimit' before initialization`
    #   （沙盒实测：服务端**启动即崩**）。改成函数声明（声明式提升）即可，函数体不变。
    #   `rateBuckets`（:2685 的 const）只在中间件闭包内被引用，请求期才求值，无需提升。
    (
        "ratelimit-hoist",
        "const rateLimit = ({ windowMs, max, keyFn }: { windowMs: number; max: number;"
        " keyFn?: (req: any) => string }) =>\n"
        "  (req: any, res: any, next: any) => {",
        "// v28.1: hoisted to a function declaration on purpose -- `/api/save` (declared earlier"
        " in this file) references it at module-eval time; a `const` arrow would hit the"
        " temporal dead zone and crash the server on boot.\n"
        "function rateLimit({ windowMs, max, keyFn }: { windowMs: number; max: number;"
        " keyFn?: (req: any) => string }) {\n"
        "  return (req: any, res: any, next: any) => {",
    ),
    (
        "ratelimit-hoist-close",
        "    next();\n  };",
        "    next();\n  };\n}",
    ),
    # ---- A) 心法 exp 量纲对齐 ----
    (
        "gfexp-curve",
        "  return 50 * l * (l + 1);",
        "  // v28.1: exp curve MUST scale with GONGFA_STEP_COST."
        " Was hard-coded 50*L*(L+1) (= 100/level) while cost is 1000/level -> 10x mismatch,\n"
        "  return (GONGFA_STEP_COST / 2) * l * (l + 1);",
    ),
    (
        "gfexp-total-comment",
        "GONGFA_MAX_EXP_TOTAL = gongfaExpToReach(GONGFA_MAX_LEVEL); // 5500",
        "GONGFA_MAX_EXP_TOTAL = gongfaExpToReach(GONGFA_MAX_LEVEL); // 55000",
    ),
    # ---- B) POST /api/save 限流 ----
    (
        "save-ratelimit",
        "app.post('/api/save', authenticateToken, async (req: any, res: any) => {",
        "app.post('/api/save', authenticateToken,"
        " rateLimit({ windowMs: 60 * 1000, max: 120,"
        " keyFn: (req: any) => 'save:' + (req.user?.id ?? req.ip) }),"
        " async (req: any, res: any) => {",
    ),
    # ---- C) 429 带 Retry-After ----
    (
        "ratelimit-retry-after",
        "    if (bucket.count > max) {",
        "    if (bucket.count > max) {\n"
        "      res.set('Retry-After', String(Math.max(1,"
        " Math.ceil((bucket.resetAt - now) / 1000))));",
    ),
]

NEW_IDENTIFIERS = [
    "rateLimit({ windowMs: 60 * 1000, max: 120,",
    "'save:' + (req.user?.id ?? req.ip)",
    "res.set('Retry-After', String(Math.max(1,",
    "(GONGFA_STEP_COST / 2) * l * (l + 1)",
]


def fail(msg: str) -> None:
    print("FAIL: " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 5) already patched?
    for label, old, new in EDITS:
        if src.count(new) > 0 and src.count(old) == 0:
            fail("source looks already patched at %s" % label)

    # 1) anchor uniqueness
    for label, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("anchor %s occurs %d times (want exactly 1): %r" % (label, n, old[:80]))

    # 4) injected text ASCII
    for label, old, new in EDITS:
        try:
            new.encode("ascii")
        except UnicodeEncodeError as e:
            fail("injected text for %s is not ASCII: %s" % (label, e))

    # 3) identifier collision
    for ident in NEW_IDENTIFIERS:
        if src.count(ident) != 0:
            fail("new identifier already present (%d): %r" % (src.count(ident), ident))

    out = src
    for label, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 2) round-trip
    rt = out
    for label, old, new in reversed(EDITS):
        if rt.count(new) != 1:
            fail("round-trip: fragment %s occurs %d times in product" % (label, rt.count(new)))
        rt = rt.replace(new, old, 1)
    if rt != src:
        fail("round-trip mismatch: product is not an exact superset of source")

    # 语义断言
    if out.count("app.post('/api/save', authenticateToken, rateLimit(") != 1:
        fail("save rate limit not applied exactly once")
    if "(GONGFA_STEP_COST / 2) * l * (l + 1)" not in out:
        fail("gongfa exp curve not rewritten")
    if out.count("// 55000") != 1:
        fail("GONGFA_MAX_EXP_TOTAL comment not updated")

    if a.check:
        print("CHECK OK: all anchors unique, round-trip byte-exact, injected text ASCII")
        return

    # 原子写（in-place）：先写同目录临时文件再 os.replace
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".v281_", suffix=".ts")
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

    def md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    print("OK  source : %s  chars=%d bytes=%d md5=%s"
          % (src_path, len(src), len(src.encode("utf-8")), md5(src)))
    print("OK  product: %s  chars=%d bytes=%d md5=%s"
          % (src_path, len(out), len(out.encode("utf-8")), md5(out)))
    print("OK  delta  : chars=+%d bytes=+%d"
          % (len(out) - len(src), len(out.encode("utf-8")) - len(src.encode("utf-8"))))
    for label, old, new in EDITS:
        print("    + %-24s injected chars=%d (ascii=%s)" % (label, len(new) - len(old), new.isascii()))
    print("OK  all anchors unique, identifiers collision-free, round-trip byte-exact, injected text ASCII")


if __name__ == "__main__":
    main()
