# -*- coding: utf-8 -*-
r"""
srv_patch_p2b_hardening.py -- P2-⑨ 残留硬化（**lead 独占**，2026-09-28）

为什么单独成模块（而不是改 srv_patch_p2_api.py）
--------------------------------------------------------------------------
`srv_patch_p2_api.py` 的作者（srv-api）在 10:12 之后 **1h35m 无写入**，两次催办无响应。
为了不与其并发写同一文件（本轮已发生过一次「共享文件互相覆盖」事故），
本模块由 lead 独立新增，**只做 P2-⑨ 的残留部分**，并在链上排在 p2 之后。

修复内容（ver-a 第二阶段独立复验实测，lead 已逐行核对）
--------------------------------------------------------------------------
残留 ①：`/api/auth/register` 与 `/api/auth/login` 仍 500
  body `{"username":{"toString":1},"password":{"toString":1}}` → `{"error":"服务器繁忙"}`
  根因：p2 只加了 `req.body || {}`，但对象形式的 `username` 照样往下走：
    `validateUsername()` 内 `username.trim()`、register/login 各自的 `username.trim()`
    `{"toString":1}.trim` 是 undefined → TypeError。
  p2 的 `asStr/asNum/asInt` 替换面**整个漏掉了 auth 路由前缀**（其 55 端点清单里没有 auth）。

残留 ②：`SECT_GF_BY_ID` 原型链泄漏（**五个键，不是一个**）
  body `{"id":"toString"}` → `403 {"error":"职衔不足，需达到undefined"}`
  根因：`const m: Record<string, SectGfDef> = {};` 是**普通对象字面量（带原型链）**
    ⇒ `SECT_GF_BY_ID["toString"]` 命中 `Object.prototype.toString`（truthy）
    ⇒ 绕过 `if (!def)` ⇒ `def.rank` = undefined 被拼进给玩家的文案。
  ver-a 用 `proto` 模式实测（5 键 × 10 入口 = 50 例，0.8.1 与 0.8.2 **两版 bad 都是 5**）：
    `toString` / `valueOf` / `constructor` / `hasOwnProperty` / `__proto__` **全部命中**。
  ⇒ 属**既有缺陷**（0.8.1 就坏），不是本批引入；只修 `toString` 会漏 4 个。

全仓同类排查（lead 做过，结论已记录）
--------------------------------------------------------------------------
扫了「`{}` 字面量当 map + 外部可控字符串做键 + 结果直接取属性」的三元组合：
  · `:2340 dict[name]`            → name 来自硬编码 LOTTERY_POOL，**安全**
  · `:3817 map[String(r.date)]`   → 内部日期，**安全**
  · `:9104 out[String(r.gongfa_id)]` → 内部 DB 值，**安全**
  · `:9110 out[g.id]`             → 内部常量，**安全**
  · `:6028 GONGFA_LIST[key]`      → 调用前已过 `:4456 gongfaOk()`（内含 hasOwnProperty 守卫），**安全**
  · `:2438/:6773/:7703/:9319/:9645` → p2 已用 `asStr` 收口，**安全**
  · `:5367/:5430 String(req.query.player ?? '')` → Express 5 simple parser 下 `req.query.player` 不是对象，**安全**
⇒ 只有本模块修的这两处是真缺陷。

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  **不提供 `--out`** —— `localtest/chain_build.py` 会把上一环产物复制成私有工作副本再让本补丁就地改。
"""
import argparse
import hashlib
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ---------------------------------------------------------------------------
# EDITS: (label, old, new, count)   —— 全部 ASCII，old 必须逐字命中
# ---------------------------------------------------------------------------
EDITS = [
    # ---- 残留 ①：auth 三个入口的 username 收口（validateUsername 1 处 + register/login 各 1 处）----
    ("auth·validateUsername 收口",
     "  const trimmed = username.trim();\n",
     "  const trimmed = asStr(username).trim();\n", 1),
    ("auth·register/login 收口",
     "  const trimmedUsername = username.trim();\n",
     "  const trimmedUsername = asStr(username).trim();\n", 2),
    # ---- 残留 ②：SECT_GF_BY_ID 去原型链（一次挡住五个键）----
    ("sectgf·字典去原型链",
     "  const m: Record<string, SectGfDef> = {};\n",
     "  const m: Record<string, SectGfDef> = Object.create(null);\n", 1),
    # ---- 残留 ③：password 面同类缺陷（ver-a 硬反例 ③，2026-09-28 12:00 追加）----
    #   ver-a 指出：p2b v1 只修了 username 面，password 面 5 个 500 原样保留；
    #   且「username+password 同时毒化」的用例会在 username 校验阶段短路 ⇒ 测试空洞。
    #   三处库函数入参收口：
    ("auth·validatePassword 入参收口",
     "const validatePassword = (password: string): { valid: boolean; error?: string } => {\n"
     "  if (password.length < 6) {\n",
     "const validatePassword = (passwordRaw: string): { valid: boolean; error?: string } => {\n"
     "  const password = asStr(passwordRaw);\n"
     "  if (password.length < 6) {\n", 1),
    ("auth·login bcrypt 入参收口",
     "      if (await bcrypt.compare(password, user.password_hash)) {\n",
     "      if (await bcrypt.compare(asStr(password), user.password_hash)) {\n", 1),
    ("auth·改密 oldPassword 收口",
     "    if (!(await bcrypt.compare(oldPassword, user.password_hash))) {\n",
     "    if (!(await bcrypt.compare(asStr(oldPassword), user.password_hash))) {\n", 1),
]

# 本补丁依赖 p2 已注入的助手（链序：p0 → p2 → p2b）
REQUIRES = [
    ("function asStr(x: unknown): string {", 1, "p2 的 asStr 助手必须已存在（本补丁排在 p2 之后）"),
]

GATES = [
    # ---- 残留 ① 修好 ----
    ("p2b·auth 已收口 asStr",      "asStr(username).trim()",                     3, "==", "validateUsername + register + login"),
    ("p2b·裸 username.trim() 清零", "username.trim()",                            0, "==", "必须为 0"),
    # ---- 残留 ② 修好 ----
    ("p2b·字典已去原型链",          "const m: Record<string, SectGfDef> = Object.create(null);", 1, "==", ""),
    ("p2b·旧字典字面量清零",        "const m: Record<string, SectGfDef> = {};",    0, "==", "必须为 0"),
    ("p2b·字典定义仍在",            "const SECT_GF_BY_ID: Record<string, SectGfDef> = (() => {", 1, "==", ""),
    # ---- 反回归：不许碰别处 ----
    ("p2b·gongfaOk 守卫未动",      "Object.prototype.hasOwnProperty.call(GONGFA_LIST, asStr(key))", 1, "==", ""),
    ("p2b·asStr 助手仍在",         "function asStr(x: unknown): string {",       1, "==", ""),
    ("p2b·asNum 助手仍在",         "function asNum(x: unknown): number {",       1, "==", ""),
    ("p2b·asInt 助手仍在",         "function asInt(x: unknown): number {",       1, "==", ""),
    # ---- 残留 ③（password 面）----
    ("p2b·validatePassword 已收口", "const password = asStr(passwordRaw);",       1, "==", ""),
    ("p2b·login bcrypt 已收口",    "bcrypt.compare(asStr(password),",            1, "==", ""),
    ("p2b·改密 bcrypt 已收口",     "bcrypt.compare(asStr(oldPassword),",         1, "==", ""),
    ("p2b·裸 bcrypt.compare 清零", "bcrypt.compare(password,",                    0, "==", "必须为 0"),
    ("p2b·裸 bcrypt.compare 清零2", "bcrypt.compare(oldPassword,",                0, "==", "必须为 0"),
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

    # 1) 依赖检查（p2 必须先跑过）
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%s 出现 %d 次，期望 %d）：%s" % (needle[:40], n, cnt, why))

    # 2) 是否已打过本补丁
    for label, old, new, cnt in EDITS:
        if src.count(new) > 0 and src.count(old) == 0:
            fail("source looks already patched at %s" % label)

    # 3) 注入文本必须纯 ASCII
    for label, old, new, cnt in EDITS:
        try:
            new.encode("ascii")
        except UnicodeEncodeError as e:
            fail("injected text for %s is not ASCII: %s" % (label, e))

    # 4) 锚点计数
    for label, old, new, cnt in EDITS:
        n = src.count(old)
        if n != cnt:
            fail("anchor %s occurs %d times (want %d): %r" % (label, n, cnt, old[:90]))

    # 5) 注入片段不得已存在（否则反向替换有歧义）
    for label, old, new, cnt in EDITS:
        if src.count(new) != 0:
            fail("injected fragment for %s already present x%d: %r"
                 % (label, src.count(new), new[:90]))

    # 6a) old 之间不得互为子串
    for i, (li, oi, ni, ci) in enumerate(EDITS):
        for j, (lj, oj, nj, cj) in enumerate(EDITS):
            if i != j and oi in oj:
                fail("anchor %s is a substring of anchor %s" % (li, lj))
    # 6b) old 不得出现在 new 里；new 之间不得互为子串
    for i, (li, oi, ni, ci) in enumerate(EDITS):
        for j, (lj, oj, nj, cj) in enumerate(EDITS):
            if oi in nj and not (i == j and oi == oj):
                fail("anchor %s appears inside injected %s" % (li, lj))
            if i != j and ni in nj:
                fail("injected %s is a substring of injected %s" % (li, lj))

    out = src
    for label, old, new, cnt in EDITS:
        before = out.count(new)
        out = out.replace(old, new)
        if out.count(new) - before != cnt:
            fail("edit %s: replaced %d occurrences (want %d)" % (label, out.count(new) - before, cnt))

    # 7) 往返必须逐字复现原文
    rt = out
    for label, old, new, cnt in reversed(EDITS):
        rt = rt.replace(new, old)
    if rt != src:
        fail("round-trip mismatch: product is not an exact superset of source")

    # 8) 门禁
    bad = []
    for name, s, expect, cmp, note in GATES:
        n = out.count(s)
        ok = (n == expect) if cmp == "==" else ((n >= expect) if cmp == ">=" else (n <= expect))
        if not ok:
            bad.append("%s: got %d, want %s %d  %s" % (name, n, cmp, expect, note))
    if bad:
        fail("gate(s) failed:\n  " + "\n  ".join(bad))

    if a.check:
        print("CHECK OK: %d edits, %d requires, %d gates, round-trip byte-exact, ASCII"
              % (len(EDITS), len(REQUIRES), len(GATES)))
        return

    # 原子就地写
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".p2b_", suffix=".ts")
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
    print("OK  delta  : chars=%+d bytes=%+d"
          % (len(out) - len(src), len(out.encode("utf-8")) - len(src.encode("utf-8"))))
    print("OK  edits  : %d   asStr(username).trim()=%d" % (len(EDITS), out.count("asStr(username).trim()")))
    print("OK  gates  : %d passed" % len(GATES))


if __name__ == "__main__":
    main()
