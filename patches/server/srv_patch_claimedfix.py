# -*- coding: utf-8 -*-
r"""
srv_patch_claimedfix.py -- 修 `GET /api/quest/summary` 的 `milestones[].claimed` 恒 false

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` / `--selftest` 只校验不写。
  前置依赖：必须在 **r013c** 之后（本环锚点是 r013c 产出的 summary 查询行）。
  lead 接线：把本环挂在 SRV_CHAIN 链尾（第 32 环，紧接 srv_patch_r013c.py）。

=========================================================================== 为什么改（bug 证据）
`activity_milestones.week` 列存的是 **claimKey**，不是裸周号：
  · 档位常规奖励（周频）：`'w' + week + '_' + tier`     例如 `w2026-09-28_500`
  · 传承石（月频）      ：`'m' + weekMonthKey(week) + '_' + tier + '_legacy'`（tier 存 `-tier`）
        —— 两行均由 POST /api/quest/milestone 写入（见 r013c）。

而 summary 的读取用的是**裸周号**：
    db.all('SELECT tier FROM activity_milestones WHERE user_id = ? AND week = ?', [req.user.id, week], …)
⇒ 拿 `'2026-09-28'` 去比表里的 `'w2026-09-28_500'` ⇒ **永远匹配不到**
⇒ `claimedTiers` 恒空 ⇒ `milestones[].claimed = claimedTiers.has(m.tier)` **恒 false**
⇒ 玩家领过之后 UI 仍显示「领取」（点下去被 UNIQUE 挡回 409，**不会重复发奖，非资损，纯显示 bug**）。

该不一致**早于** r013b/r013c（自 0.8.8 `t9_activity` 起：同批写入端用 `'w'` 前缀，summary 却用裸 week）。

=========================================================================== 本环改点（1 处 replace）
把 summary 的查询从「按裸 week 精确匹配」改为「按 claimKey 前缀匹配」：

  旧：WHERE user_id = ? AND week = ?                     参数 [userId, week]
  新：WHERE user_id = ? AND week LIKE ?                  参数 [userId, 'w' + week + '_%']

  ★ LIKE 里的 `_` 是**单字符通配符**，恰好吃掉键里那个字面 `_`（`w2026-09-28` + `_` + `500`）；
    模式 = `w` + 裸周号 + `_` + `%`。
  ★ 为什么安全（不会误算）：
      · 裸周号由 `bjWeekStart()` 产出 = `toISOString().slice(0,10)` = `YYYY-MM-DD`，
        **只含数字与 `-`**，不含 `%` / `_` ⇒ 前缀部分全字面，无通配歧义。
      · 传承石月频行是 `'m<YYYY-MM>_<tier>_legacy'`，**以 `m` 开头** ⇒ 不匹配 `w` 前缀
        ⇒ 不会被算成「档位已领」（这正是必须只匹配 `w<week>_%` 的原因）。
      · 档位 key 恒为 `w<week>_<tier>`，`_` 通配位对应的就是字面 `_`，不存在跨档误配。

=========================================================================== 为什么不动 `monthly` 字段（判断结论）
`monthly: m.tier === MILE_MONTHLY_TIER`（= 2310）**一字未动**，理由：
  · 全仓实测（`grep -F monthly` 扫 yl_*.py + build/assets/*.js）：**客户端从不读取该字段**
    —— `YlxwQMileZone` 只读 `claims[m.tier]`（见 yl_t9quest_ext.py:160），bundle 里也无 `monthly`。
    ⇒ 它是**服务端独有、当前无人消费**的字段，**不会误导玩家**。
  · 语义上它现在表达「本档的 legacy 额外奖励（传承石）按月限领」，与 r013c 后的发放语义**仍一致**
    （2310 = 唯一带传承石的档）。r013c 已把领取响应改成 `monthly: isStoneTier`，与本行同义。
  · 命名偏旧（叫 monthly 易让人误读为「整档按月」），但**无消费者 ⇒ 无实际影响**，
    且改动它属范围外，故按「改一处算一处」不动；如需正名，请 lead 另开一环（详见报告 §「monthly 判断」）。

=========================================================================== 红线
  · **不新增任何 res.status(403)**（本环只改一条只读查询；基线 = 11）。
  · 不新增表 / 列 / 端点；不动 `mail` / `insertMail` / `mailClaimCore`。
  · 不改里程碑端点（写入侧）、不改档位表 / 幂等表 DDL / 周上限常量 / WEEK_MILESTONES 表值。
  · 不改 `claimedTiers` 映射与 `milestones` 结构（只改喂给它的那一条 SELECT）。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ E1 summary 里程碑查询

E1_OLD = """              db.all('SELECT tier FROM activity_milestones WHERE user_id = ? AND week = ?', [req.user.id, week], (errm: any, mrows: any[]) => {"""

E1_NEW = """              // claimedfix：activity_milestones.week 列存的是 **claimKey**（里程碑端点写 'w'+week+'_'+tier），
              //   原来按裸 week（'2026-09-28'）查 ⇒ 永远匹配不到 ⇒ claimedTiers 恒空 ⇒ claimed 恒 false。
              //   改按 claimKey 前缀匹配。LIKE 里的 '_' 是单字符通配符，恰好吃掉键里那个字面 '_'；
              //   裸周号只含数字与 '-'（无 %/_）⇒ 前缀全字面；传承石月频行以 'm' 开头（'m<YYYY-MM>_<tier>_legacy'）
              //   ⇒ 不匹配 'w' 前缀，不会被误算成「档位已领」。
              db.all('SELECT tier FROM activity_milestones WHERE user_id = ? AND week LIKE ?', [req.user.id, 'w' + week + '_%'], (errm: any, mrows: any[]) => {"""

EDITS = [
    ("E1 summary 里程碑查询：裸 week 精确匹配 → claimKey 前缀匹配", E1_OLD, E1_NEW),
]

# 前置依赖（r013c 之后的形态，必须逐条在位；本环只读这些串做自证，不改）
REQUIRES = [
    ("db.all('SELECT tier FROM activity_milestones WHERE user_id = ? AND week = ?', [req.user.id, week], (errm: any, mrows: any[]) => {", 1,
     "待修的裸 week 查询必须在位（本环删除）"),
    ("const claimedTiers = new Set((mrows || []).map((r) => Number(r.tier)));", 1,
     "claimedTiers 构造必须在位（本环不得改）"),
    ("claimed: claimedTiers.has(m.tier),", 1, "claimed 映射必须在位（本环不得改）"),
    ("const week = bjWeekStart(nowMs);", 1, "summary 的周键来源必须在位"),
    ("monthly: m.tier === MILE_MONTHLY_TIER,", 1, "summary monthly 提示行必须在位（本环不得改）"),
    ("const MILE_MONTHLY_TIER = 2310;", 1, "月频档常量必须在位（本环不得改）"),
    ("const claimKey = 'w' + week + '_' + tier;", 1, "r013c 常规奖励周频键必须在位（证明 r013c 已接线）"),
    ("const stoneKey = 'm' + weekMonthKey(week) + '_' + tier + '_legacy';", 1,
     "r013c 传承石月频键必须在位（本环匹配前缀须避开它）"),
    ("CREATE TABLE IF NOT EXISTS activity_milestones", 1, "幂等表 DDL 必须在位"),
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：已打过本环（先于依赖检查，给出明确诊断）
    if ("week LIKE ?', [req.user.id, 'w' + week + '_%']" in src
            or "claimedfix：activity_milestones.week 列存的是 **claimKey**" in src):
        fail("source looks already patched（summary 查询已按 claimKey 前缀匹配）")

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 5) 门禁
    base403 = src.count("res.status(403")
    gates = [
        # ---- E1 查询改前缀匹配 ----
        ("CF 新查询（LIKE ?）就位",   "db.all('SELECT tier FROM activity_milestones WHERE user_id = ? AND week LIKE ?', [req.user.id, 'w' + week + '_%'], (errm: any, mrows: any[]) => {", 1),
        ("CF 旧裸 week 查询已删",     "db.all('SELECT tier FROM activity_milestones WHERE user_id = ? AND week = ?', [req.user.id, week], (errm: any, mrows: any[]) => {", 0),
        ("CF 前缀绑定串就位",         "[req.user.id, 'w' + week + '_%']", 1),
        # ---- 冻结：本环不得回踩的 summary 其它语义 ----
        ("冻结 claimedTiers 构造未动", "const claimedTiers = new Set((mrows || []).map((r) => Number(r.tier)));", 1),
        ("冻结 claimed 映射未动",      "claimed: claimedTiers.has(m.tier),", 1),
        ("冻结 monthly 提示行未动",    "monthly: m.tier === MILE_MONTHLY_TIER,", 1),
        ("冻结 月频常量仍 2310",       "const MILE_MONTHLY_TIER = 2310;", 1),
        ("冻结 summary 周键来源未动",  "const week = bjWeekStart(nowMs);", 1),
        ("冻结 档位表仍 5 档表驱动",   "const WEEK_MILESTONES: Array<{ tier: number; wbase: number; wexp: number; wtk: number; legacy: string }> = [", 1),
        # ---- 冻结：写入侧（r013c）语义不得回踩 ----
        ("冻结 常规奖励周频键未动",    "const claimKey = 'w' + week + '_' + tier;", 1),
        ("冻结 传承石月频键未动",      "const stoneKey = 'm' + weekMonthKey(week) + '_' + tier + '_legacy';", 1),
        ("冻结 发石判定仍按 legacy",   "const isStoneTier = mdef.legacy === '传承石';", 1),
        ("冻结 幂等表 DDL 未动",       "CREATE TABLE IF NOT EXISTS activity_milestones", 1),
        # ---- 红线 ----
        ("冻结 未新增邮件物品列",      "attached_item_json", 0),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 6) 红线：不得新增 403
    a403 = out.count("res.status(403")
    good = (a403 == base403)
    ok = ok and good
    print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", "红线 未新增 res.status(403)", a403, base403))

    # 7) 语义自证：前缀只吃 'w<week>_%'；传承石月频键仍以 'm' 开头（被排除）；claimed 映射仍读 tier 列
    sem_ok = (
        out.count("week LIKE ?") == 1
        and "[req.user.id, 'w' + week + '_%']" in out
        and "week = ?', [req.user.id, week]" not in out
        and out.count("claimed: claimedTiers.has(m.tier),") == 1
        and "const stoneKey = 'm' + weekMonthKey(week)" in out          # 石行以 'm' 开头 ⇒ 不被 'w' 前缀命中
        and "const claimKey = 'w' + week + '_' + tier;" in out          # 档位行以 'w<week>_' 开头 ⇒ 被命中
    )
    ok = ok and sem_ok
    print("  [%s] %-40s likeCnt=%d stoneKey_m=%s"
          % ("OK" if sem_ok else "FAIL", "CF 语义自证(前缀只匹配 w<week>_%)",
             out.count("week LIKE ?"), "const stoneKey = 'm' + weekMonthKey(week)" in out))

    if not ok:
        fail("门禁未全绿，未写回")

    # 8) 往返自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".claimedfix-", suffix=".tmp")
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
