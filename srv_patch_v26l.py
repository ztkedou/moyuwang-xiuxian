# -*- coding: utf-8 -*-
r"""yl v26l 服务端补丁

S1｜删除死代码 clampSaveEcon（遗留2）
   它定义了但从未被调用；/api/save 的唯一结算入口是 settleSaveEconV2。
   顺带修正 P0-2 文档注释里 v26k ×5 后已过期的数值。

S2｜POST /api/save 响应回传 settledExp（遗留3 服务端侧）
   客户端 pushSave 成功后只追平 gm_revision、不采纳服务端结算结果。
   灵石侧 v26k 已用 balance 回显兜住；修为侧补 settledExp 一并闭环。
   （不回传整份存档：save_data 含最多 1000 条日志，每 15~30s 一次会显著放大流量）

用法:
  python srv_patch_v26l.py            # 断言 + 应用 + 反查
  python srv_patch_v26l.py --count    # 只打印命中数
"""
import hashlib
import io
import sys

SRC = "srv/index.ts"
DST = "srv/index_v26l.ts"
EXPECT_MD5 = "628116cade7ce0036553cccf319902f7"

RESP1_OLD = ("res.json({ message: 'Save updated successfully', rankingSynced, "
             "clamped: clampedFields, gm_revision: curRev + 1 });")
RESP1_NEW = ("res.json({ message: 'Save updated successfully', rankingSynced, "
             "clamped: clampedFields, "
             "settledExp: Math.floor(Number(saveData && saveData.player && saveData.player.exp) || 0), "
             "gm_revision: curRev + 1 });")

RESP2_OLD = ("res.json({ message: 'Save created successfully', rankingSynced, "
             "clamped: clampedFields, gm_revision: 1 });")
RESP2_NEW = ("res.json({ message: 'Save created successfully', rankingSynced, "
             "clamped: clampedFields, "
             "settledExp: Math.floor(Number(saveData && saveData.player && saveData.player.exp) || 0), "
             "gm_revision: 1 });")

CMT_OLD = ("// P0-2：二阶段服务端权威结算（离线重算封顶+计数器逐类配额+总额兜底），"
           "签名与 clampSaveEcon 兼容可一键回退")
CMT_NEW = ("// P0-2：二阶段服务端权威结算（离线重算封顶+计数器逐类配额+总额兜底）。"
           "YL_V26L：死代码 clampSaveEcon 已删除")

DOC_OLD = ("// ③ 总额兜底：灵石 25万×1.5^境界/小时+2万（现役合法峰值≈21万/h@金丹，见 E1 SEC §1 校准）、")
DOC_NEW = ("// ③ 总额兜底：灵石 125万×1.5^境界/小时+10万（YL_ECON_X5_V26K 起口径；原 25万+2万）、")

TEXT_EDITS = [
    ("S2  save 更新响应加 settledExp", RESP1_OLD, RESP1_NEW, 1),
    ("S3  save 首存响应加 settledExp", RESP2_OLD, RESP2_NEW, 1),
    ("S4  修正 clampSaveEcon 引用注释", CMT_OLD, CMT_NEW, 1),
    ("S5  修正总额兜底过期注释", DOC_OLD, DOC_NEW, 1),
]

CLAMP_START = "function clampSaveEcon("
CLAMP_END_MARK = "// S4 v26c 保险快照"


def main():
    s = io.open(SRC, encoding="utf-8").read()
    md5 = hashlib.md5(s.encode("utf-8")).hexdigest()
    if md5 != EXPECT_MD5:
        sys.exit("[FAIL] 源 md5 不符: %s != %s" % (md5, EXPECT_MD5))
    print("[ok] 源 %s  %d 字符  md5 %s" % (SRC, len(s), md5))

    bad = []
    for name, old, new, want in TEXT_EDITS:
        got = s.count(old)
        flag = "ok  " if got == want else "FAIL"
        print("  [%s] %-30s 命中 %d (期望 %d)" % (flag, name, got, want))
        if got != want:
            bad.append(name)

    i = s.find(CLAMP_START)
    j = s.find(CLAMP_END_MARK, i) if i >= 0 else -1
    ok_clamp = (i >= 0 and j > i)
    print("  [%s] %-30s start=%d end=%d 待删 %d 字符"
          % ("ok  " if ok_clamp else "FAIL", "S1 删除 clampSaveEcon", i, j, (j - i) if ok_clamp else 0))
    if not ok_clamp:
        bad.append("S1")
    if s.count(CLAMP_START) != 1:
        print("  [FAIL] clampSaveEcon 定义数 != 1")
        bad.append("S1-count")

    if bad:
        sys.exit("\n[FAIL] 断言未过，未产出文件: %s" % ", ".join(bad))
    if "--count" in sys.argv:
        print("\n[count-only] 断言全过，未写文件")
        return

    removed = s[i:j]
    out = s[:i] + s[j:]
    print("  [ok] S1 删除 clampSaveEcon（含尾随空行）%d 字符" % len(removed))
    for name, old, new, want in TEXT_EDITS:
        out = out.replace(old, new, want)
        print("  [ok] %-30s x%d" % (name, want))

    checks = [
        ("clampSaveEcon 定义已消失", "function clampSaveEcon(" in out, False),
        ("settleSaveEconV2 仍在", "function settleSaveEconV2(" in out, True),
        ("settle 调用点仍在", out.count("settleSaveEconV2("), 2),
        ("settledExp 出现 2 次", out.count("settledExp: Math.floor("), 2),
        ("S4 注释已改", "死代码 clampSaveEcon 已删除" in out, True),
        ("S5 注释已改", "125万×1.5^境界/小时+10万" in out, True),
        ("clampSaveEcon 仅剩注释提及 1 处", out.count("clampSaveEcon"), 1),
    ]
    nb = 0
    for label, got, want in checks:
        ok = (got == want)
        if not ok:
            nb += 1
        print("  [%s] 反查 %s%s" % ("ok  " if ok else "FAIL", label,
                                    "" if ok else "  (实际 %s)" % (got,)))
    if nb:
        sys.exit("[FAIL] 反查未过 %d 项，未写文件" % nb)

    # 往返等价证明
    back = out
    for name, old, new, want in TEXT_EDITS:
        back = back.replace(new, old, want)
    back = back[:i] + removed + back[i:]
    print("  [%s] 往返等价（还原后与源逐字一致）: %s" % ("ok  " if back == s else "FAIL", back == s))
    if back != s:
        sys.exit("[FAIL] 往返不等价，未写文件")

    io.open(DST, "w", encoding="utf-8", newline="").write(out)
    print("\n[ok] 已写出 %s" % DST)
    print("     字符数 %d → %d (Δ %+d)" % (len(s), len(out), len(out) - len(s)))
    print("     md5 %s" % hashlib.md5(out.encode("utf-8")).hexdigest())


main()
