# -*- coding: utf-8 -*-
"""
srv_patch_mail_claimall.py -- 信箱「一键领取」服务端补丁生成器 (用户反馈 #2)

读 : srv/index_v27b.ts          (线上主本，NEVER 修改)
写 : srv/index_v27b_mail.ts     (补丁产物)

幂等：源文件只读，重复运行必得逐字节一致的产物。

本文件强制的不变量（任一不满足 => sys.exit(1)，不落盘）：
  1. 每个锚点在源文件中恰好出现 1 次；
  2. 往返等价：把每个 new 片段换回 old 片段，逐字节还原源文件；
  3. 每个新引入标识符在源文件中出现 0 次（防重复打补丁 / 命名碰撞）；
  4. 每个**注入**片段为纯 ASCII（注入片段里必须出现的中文一律 \\uXXXX）；
  5. 源文件尚未打过本补丁。

本次改动（3 处）：
  E1  GET /api/mail/list 的 COUNT 查询追加 claimable 聚合列（有附件且未领取的封数），
      供客户端按钮显示**全量准确**的可领取数量（默认分页只有 20 封，按页计数会偏小）。
  E2  同上路由的 JSON 回执追加 claimable 字段（纯新增字段，不改既有契约）。
  E3  新增 POST /api/mail/claim-all —— 一次领取该用户全部 attached_lingshi > 0 且
      claimed = 0 的邮件。**逐封复用 mailClaimCore**（不另写入账逻辑），因此原子占位 /
      补偿回滚 / updatePlayerSave(gm_revision++) 语义与单封 /api/mail/claim 完全一致；
      单封失败只记日志并继续，不影响其余邮件。

关于 gm_revision 风暴（重要结论）
--------------------------------
mailClaimCore 每封都会 updatePlayerSave → gm_revision 每封 +1。客户端实时刷新通道是
一个**固定 6s 的 setInterval**（jS() 里 yS=6e3），它比较 `gm_revision > appliedGmRevision`
后**每次 tick 只 fetchSave 一次**。因此一次 claim-all 请求里 N 次自增会被下一个 tick
**合并成一次拉取**，不构成轮询风暴（客户端不存在「每自增一次就拉一次」的反应式路径，
也无 SSE/WebSocket 推送该字段）。故这里保持「逐封复用 mailClaimCore」，
不改成「一次 updatePlayerSave 累加总额」——后者要另写入账逻辑，反而破坏与
mailClaimCore 的原子占位/回滚语义一致性，且收益（少 N-1 次 gm_revision++）本就无客户端影响。

运行（路径相对当前工作目录，即仓库根）：
  python srv_patch_mail_claimall.py
  python srv_patch_mail_claimall.py --src srv/index_v27b.ts --out srv/index_v27b_mail.ts

--src / --out 可选；缺省为 srv/index_v27b.ts -> srv/index_v27b_mail.ts。
"""
import argparse
import io
import os
import sys
import hashlib

DEFAULT_SRC = os.path.join("srv", "index_v27b.ts")
DEFAULT_OUT = os.path.join("srv", "index_v27b_mail.ts")


def esc(s: str) -> str:
    """把每个非 ASCII 码点转成 \\uXXXX，保证注入文本为纯 ASCII。"""
    out = []
    for ch in s:
        if ord(ch) < 128:
            out.append(ch)
        else:
            out.append("\\u%04x" % ord(ch))
    return "".join(out)


# ---------------------------------------------------------------------------
# 片段（真中文书写；esc() 统一转义。注释一律 ASCII 英文，只有必须含中文的
#       字符串字面量会被转义）
# ---------------------------------------------------------------------------

# --- E1: list 路由的 COUNT 查询追加 claimable 聚合列 ------------------------
E1_OLD = (
    "'SELECT COUNT(*) AS total, SUM(CASE WHEN read_at IS NULL THEN 1 ELSE 0 END) AS unread "
    "FROM mail WHERE user_id = ?',"
)
E1_NEW = (
    "'SELECT COUNT(*) AS total, SUM(CASE WHEN read_at IS NULL THEN 1 ELSE 0 END) AS unread, "
    "SUM(CASE WHEN claimed = 0 AND attached_lingshi > 0 THEN 1 ELSE 0 END) AS claimable "
    "FROM mail WHERE user_id = ?',"
)

# --- E2: list 路由回执追加 claimable 字段（纯新增，不改既有键） -------------
E2_OLD = "            unread: Number(cnt?.unread) || 0,"
E2_ADD = "\n            claimable: Number(cnt?.claimable) || 0,"

# --- E3: 新增 POST /api/mail/claim-all ------------------------------------
# 锚点 = 单封 /api/mail/claim 路由的收尾 4 行（含 'mail claim error' 唯一定位串）。
# 注意：源文件这里是**真中文**，锚点必须原样含真中文才能命中（本处是纯追加，
#       old 原样重发、只对注入片段做 ASCII 断言）。
E3_OLD = (
    "    console.error('mail claim error:', e?.message || e);\n"
    "    res.status(500).json({ error: '领取失败' });\n"
    "  }\n"
    "});"
)

E3_ADD = """

// POST /api/mail/claim-all -- one-tap claim of every unclaimed mail that carries a
// lingshi attachment. Reuses mailClaimCore per mail (NEVER a second credit path), so the
// atomic claim flag / compensating rollback / gm_revision semantics stay identical to the
// single /api/mail/claim route. A failing mail is logged and skipped; the rest still settle.
app.post('/api/mail/claim-all', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `mail:claimall:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const rows: any[] = await dbAll(
      'SELECT id FROM mail WHERE user_id = ? AND claimed = 0 AND attached_lingshi > 0 ORDER BY id ASC',
      [userId]
    );
    let count = 0;
    let lingshi = 0;
    for (const row of rows || []) {
      try {
        const r = await mailClaimCore({ dbGet, dbRun, updatePlayerSave }, userId, Number(row.id));
        if (r.ok) { count++; lingshi += Number(r.lingshi) || 0; }
      } catch (perMailErr: any) {
        console.error('mail claim-all per-mail error:', perMailErr?.message || perMailErr);
      }
    }
    res.json({ ok: true, count, lingshi });
  } catch (e: any) {
    console.error('mail claim-all error:', e?.message || e);
    res.status(500).json({ error: '领取失败' });
  }
});"""

# ---------------------------------------------------------------------------
# 编辑表：(label, old, new)。注入文本由 injected_text() 自动推导：
#   * 纯追加 -> new[len(old):]      (old 原样重发)
#   * 纯前置 -> new[:len(new)-len(old)]
#   * 原地改 -> old 与 new 必须全 ASCII
# ---------------------------------------------------------------------------
EDITS = [
    ("E1_list_claimable_sql",   E1_OLD, E1_NEW),
    ("E2_list_claimable_field", E2_OLD, E2_OLD + E2_ADD),
    ("E3_claimall_route",       E3_OLD, E3_OLD + esc(E3_ADD)),
]

# 新引入的标识符/标记，源文件中必须为 0 次。
NEW_IDENTIFIERS = [
    "mail:claimall:",
    "mail claim-all",
    "mail/claim-all",
    "claim-all per-mail",
    "AS claimable",
    "cnt?.claimable",
]


def injected_text(label: str, old: str, new: str):
    """返回该处实际注入的文本（None => 原地编辑）。"""
    if new.startswith(old):
        return new[len(old):]
    if new.endswith(old):
        return new[:len(new) - len(old)]
    return None


def fail(msg: str) -> None:
    sys.stderr.write("FAIL: " + msg + "\n")
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate the mailbox one-tap-claim (feedback #2) server patch product."
    )
    ap.add_argument("--src", default=DEFAULT_SRC, help="pristine baseline (default: %(default)s)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="patched product (default: %(default)s)")
    args = ap.parse_args()
    src_path = args.src
    out_path = args.out

    if not os.path.isfile(src_path):
        fail("source not found: " + src_path)
    if os.path.abspath(src_path) == os.path.abspath(out_path):
        fail("--src and --out must differ (refusing to overwrite the baseline in place)")
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 5) 源文件尚未打过本补丁
    for marker in ("mail:claimall:", "mail/claim-all"):
        if marker in src:
            fail("source already contains marker %r; refusing to double-patch" % marker)

    # 1) 锚点唯一性
    for label, old, _new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("anchor %s occurs %d times (expected exactly 1)" % (label, n))

    # 3) 新标识符不得预先存在
    for ident in NEW_IDENTIFIERS:
        n = src.count(ident)
        if n != 0:
            fail("identifier %r already occurs %d times in source" % (ident, n))

    # 4) 注入文本必须纯 ASCII
    for label, old, new in EDITS:
        added = injected_text(label, old, new)
        if added is None:
            if not (old.isascii() and new.isascii()):
                fail("in-place edit %s touches non-ASCII bytes" % label)
            continue
        try:
            added.encode("ascii")
        except UnicodeEncodeError as e:
            fail("injected text for %s is not ASCII: %s" % (label, e))

    # apply
    out = src
    for label, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 2) 往返等价（逆序还原）
    rt = out
    for label, old, new in reversed(EDITS):
        if rt.count(new) != 1:
            fail("round-trip: fragment %s occurs %d times in product" % (label, rt.count(new)))
        rt = rt.replace(new, old, 1)
    if rt != src:
        fail("round-trip mismatch: product is not an exact superset of source")

    with io.open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(out)

    def md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    print("OK  source : %s  chars=%d bytes=%d md5=%s"
          % (src_path, len(src), len(src.encode("utf-8")), md5(src)))
    print("OK  product: %s  chars=%d bytes=%d md5=%s"
          % (out_path, len(out), len(out.encode("utf-8")), md5(out)))
    print("OK  delta  : chars=+%d bytes=+%d"
          % (len(out) - len(src), len(out.encode("utf-8")) - len(src.encode("utf-8"))))
    for label, old, new in EDITS:
        added = injected_text(label, old, new)
        if added is None:
            print("    ~ %-24s in-place ASCII edit" % label)
        else:
            print("    + %-24s injected chars=%d (ascii=%s)" % (label, len(added), added.isascii()))
    print("OK  all anchors unique, identifiers collision-free, round-trip byte-exact, injected text ASCII")


if __name__ == "__main__":
    main()
