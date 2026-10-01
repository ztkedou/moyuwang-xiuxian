# -*- coding: utf-8 -*-
r"""
srv_patch_p3_brand.py -- 入口迁移的品牌文案同步（lead 新增，2026-09-28）

为什么需要这一环
--------------------------------------------------------------------------
`brand` 工作流在远端把 `/opt/yl/server/index.ts` 里**唯一一处玩家可见**的 `/yl/`
改成了 `/myxxz/`：

    第 6467 行 · 拜师邮件模板尾部
      （若不欲收徒，可在 /yl/apps/mentor/ 解除关系；解除后双方冷却 7 天）
    → （若不欲收徒，可在 /myxxz/apps/mentor/ 解除关系；解除后双方冷却 7 天）

但是**远端不是部署源**：`srv/index_v28.ts` 才是。而该字符串来自**冻结基座**
`_v281_base/index_v28.base.ts:6293`（不可改），所以下一次部署会把远端这处改动
**静默回滚**成 `/yl/apps/mentor/` —— 这就是本地/远端源码分叉。

本模块把那处替换正式纳入装配链，使「本地产物 == 远端现役」重新成立。
远端改后 md5 = `6cd76aa44cb8904ce0594a2c45e13755`（brand 记录），
本模块产出的 `srv/index_v28.ts` 应与之一致（见 chain_build 的最终 md5 自证）。

范围（刻意最小）
--------------------------------------------------------------------------
· 只改**玩家可见**的那 1 处（邮件正文）。该文件里另有 22 处 `/yl/apps/` 是
  代码注释与内部标识，`brand` 已决定保留（改动无收益、徒增 diff 噪音）。
  ⇒ 本模块**不碰**它们。
· `/yl/api/` 保留不动：客户端 bundle 硬编码 `Q0 = "/yl/api"`，nginx 已为它配了
  301 豁免，属有意设计。

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  **不提供 `--out`** —— `localtest/chain_build.py` 会把上一环产物复制成私有
  工作副本再让本补丁就地改。
"""
import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

OLD_SUB = "/yl/apps/mentor/"
NEW_SUB = "/myxxz/apps/mentor/"

# 唯一锚点：拜师邮件模板尾部（含中文上下文，故本模块**不**要求整串 ASCII）
ANCHOR = "（若不欲收徒，可在 /yl/apps/mentor/ 解除关系；解除后双方冷却 7 天）"
REPL = "（若不欲收徒，可在 /myxxz/apps/mentor/ 解除关系；解除后双方冷却 7 天）"

# 链序依赖证明：p0 的存档校验器 + p2b 的去原型链
# 计数取自实测的 p2b 产物 `_chainstage/s03.p2b_hardening.ts`：
#   isValidSavePayload = 2（定义 1 + 调用 1）、Object.create(null) = 1
REQUIRES = [
    ("isValidSavePayload", 2, "p0_save 必须先跑过"),
    ("Object.create(null)", 1, "p2b_hardening 必须先跑过"),
]


def fail(msg):
    print("[FAIL] " + msg)
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

    # 1) 链序依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 2) 幂等：已打过就报错，不静默通过
    if src.count(REPL) != 0:
        fail("source looks already patched: %r x%d" % (REPL[:40], src.count(REPL)))

    # 3) 自证替换的**唯一差异**是那段 ASCII 子串（防止手滑写错中文）
    if ANCHOR.replace(OLD_SUB, NEW_SUB) != REPL:
        fail("ANCHOR/REPL 不是「仅替换 %s」的关系" % OLD_SUB)
    if ANCHOR.count(OLD_SUB) != 1 or REPL.count(NEW_SUB) != 1:
        fail("ANCHOR/REPL 内部出现次数不为 1")
    if not NEW_SUB.isascii() or not OLD_SUB.isascii():
        fail("替换子串必须是 ASCII")
    if len(REPL) - len(ANCHOR) != len(NEW_SUB) - len(OLD_SUB):
        fail("长度差与子串长度差不符")

    # 4) 锚点计数
    n = src.count(ANCHOR)
    if n != 1:
        fail("anchor 出现 %d 次（期望 1）：%r" % (n, ANCHOR[:60]))
    if src.count(OLD_SUB) != 2:
        fail("基座里 %s 应出现 2 次（注释 1 + 邮件 1），实际 %d" % (OLD_SUB, src.count(OLD_SUB)))

    out = src.replace(ANCHOR, REPL)
    if out.count(REPL) != 1:
        fail("替换后 REPL 出现 %d 次（期望 1）" % out.count(REPL))

    # 5) 门禁
    gates = [
        ("邮件模板已换新入口", REPL, 1),
        ("邮件模板旧入口已清零", ANCHOR, 0),
        ("mentor 注释仍保留", OLD_SUB, 1),
        ("myxxz 入口共 1 处", NEW_SUB, 1),
        ("/yl/api 未被动", '"/yl/api"', None),   # None = 只记录不判定
        ("p2b 去原型链未被动", "Object.create(null)", 1),
        ("p0 存档校验未被动", "isValidSavePayload", 2),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        if exp is None:
            print("  [INFO] %-24s actual=%d（仅记录）" % (label, act))
            continue
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-24s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))
    if not ok:
        fail("门禁未全过")

    # 6) 往返必须逐字复现原文
    if out.replace(REPL, ANCHOR) != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars" % (len(out) - len(src)))

    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".p3brand-", suffix=".tmp")
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
