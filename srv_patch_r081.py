# -*- coding: utf-8 -*-
r"""
srv_patch_r081.py -- R-081 宗门俸禄「按职位发」（服务端半边 · 权威 + 幂等）

复刻目标（上游 JeasonLoop/react-xiuxian-game a8f9810a）
--------------------------------------------------------------------------
  constants/sects.ts: SECT_RANK_SALARY = { 外门/内门/核心/长老/宗主 -> {baseSpiritStones, contribution} }
  （上游原只有 SECT_LEADER_SALARY 宗主俸禄；本次提交改为按职位发 + SectModal 每日领取。）
  我们这边第 3 档叫「真传弟子」（上游叫「核心」），其余同名。
  ★ 职位取值已实测 = 服务端既有 `SECT_GF_RANK_ORDER`
      ['\u5916\u95e8\u5f1f\u5b50','\u5185\u95e8\u5f1f\u5b50','\u771f\u4f20\u5f1f\u5b50','\u957f\u8001','\u5b97\u4e3b']
      （外门弟子/内门弟子/真传弟子/长老/宗主），本环键名与之逐字对齐。

为什么新开端点、而不是改 V27 的 /api/sect/welfare/claim
--------------------------------------------------------------------------
  · V27 那条 kind=salary 是**等级制**（= 宗门等级 × SECT_SALARY_PER_LEVEL，全员）、只发灵石、
    走 `sect_members` 成员表；上游要的是**按职位（5 档）**、发灵石 + 贡献、走基础宗门页的
    `player.sectRank`（客户端存档）。两者数据源与语义都不同，改 V27 会连带打爆仙盟伴生页契约。
  · 本环**新增**两条独立端点，blast radius 最小、不动 V27 任何一行。

端点契约
--------------------------------------------------------------------------
  GET  /api/sect/salary/status -> { inSect, rank, spiritStones, contribution, claimed, date }
      （只读；三段路径，不撞 `app.get('/api/sect/:id')` 两段通配）
  POST /api/sect/salary        -> 200 { message, rank, reward:{spiritStones,contribution},
                                        contribution, date }
                                  400 NO_SECT / 409 ALREADY_CLAIMED
      （`/api/sect/*` 命中 YL_STONE_ECHO_V26K 中间件 ⇒ 响应自动补 `balance` 权威灵石，
        客户端 YlxwApi -> YLApplyBalance 自动覆盖本地 spiritStones。）

幂等 / 防重复（服务端权威）
--------------------------------------------------------------------------
  · 职位来源 = 存档 `player.sectRank`（客户端可改，但**每日领取闸门在服务端**：重复领取被
    `sect_welfare_claims` PK(user_id,date,kind) 的 UNIQUE 挡住 → 409）；未知职位一律按最低档
    （外门弟子）发放，防越权多领。
  · `sect_welfare_claims` 是既有表（V27），PK(user_id,date,kind)，kind=rank_salary 与既有
    salary/pill 不冲突 ⇒ 零 schema 迁移。
  · 发放走 updatePlayerSave（锁内），失败则回删 claim 行（与 V27 welfare 端点同款补偿）。
  · 贡献回执 `contribution` 供客户端回填本地 store；单日 ≤300 远低于 E2:sectContrib 差值钳
    （20/分 + 5000 兜底），下次 /api/save 推档不会被截断。

数值表（灵石按本轮压过一轮的经济重标；贡献沿用上游 10/25/60/120/300）
--------------------------------------------------------------------------
  职位        灵石/日   贡献/日
  外门弟子      1,000       10
  内门弟子      2,500       25
  真传弟子      6,000       60
  长老         12,000      120
  宗主         25,000      300
  ⇒ 宗主 2.5 万/日 ≈ 满配灵田日收益(≈50 万) 的 5%；贡献 300 ≈ 日贡献收入(1.2k~6k) 的 5~25%。
    均**非主要收入**（详见报告）。

CLI 契约（照 srv_patch_r073.py / srv_patch_050.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回；`--check` / `--selftest` 只校验不写。
  幂等：产物里已含 `[r081salary]` 则 SKIP。
  lead 接线：localtest/chain_build.py 的 SRV_CHAIN 链尾追加 'srv_patch_r081.py'
  （仅要求 sect 家族（t7_sect）在前）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval` / `PRAGMA`。
  · ★ 插入的 TS 代码里中文一律转 `\uXXXX`（本模块用 _zh() 在落盘前转义，与 t7_sect/r066 同风格），
    使产物新增段为**纯 ASCII**、门禁锚点也全 ASCII（本项目门禁纪律）。
  · 每处替换 expect=1，命中数不符即中止；round-trip 自证后原子写回。
  · ⛔ 不改 srv/index_v28.ts（链产物，由 lead 跑本环时写回）；⛔ 不改任何既有 srv_patch_*.py。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

MARK = "[r081salary]"


def _zh(s: str) -> str:
    """把非 ASCII 转成 \\uXXXX（BMP 直转；星平面转代理对），保证插入段纯 ASCII。"""
    out = []
    for ch in s:
        o = ord(ch)
        if o < 128:
            out.append(ch)
        elif o <= 0xFFFF:
            out.append('\\u%04x' % o)
        else:
            o -= 0x10000
            out.append('\\u%04x\\u%04x' % (0xD800 + (o >> 10), 0xDC00 + (o & 0x3FF)))
    return ''.join(out)


# ============================================================ 改动点（单处插入）

# 插入锚：宗门福利端点之后、宗门公告端点之前（sect 家族内，helper 全部已在位）
INSERT_ANCHOR = "// 编辑宗门公告：仅宗主"

# 新增代码块（raw 中文，落盘前统一走 _zh() 转 ASCII；插入锚之前）
BLOCK_RAW = (
    "// [r081salary] R-081 宗门俸禄（按职位每日领取）：\n"
    "//   职位来源=存档 player.sectRank（外门弟子/内门弟子/真传弟子/长老/宗主，与 SECT_GF_RANK_ORDER 同源）；\n"
    "//   幂等=sect_welfare_claims PK(user_id,date,kind=rank_salary)（UNIQUE 冲突即 409）；\n"
    "//   灵石余额由 YL_STONE_ECHO_V26K 中间件自动回显；贡献值在回执里回显。\n"
    "const SECT_RANK_SALARY: Record<string, { spiritStones: number; contribution: number }> = {\n"
    "  '外门弟子': { spiritStones: 1000, contribution: 10 },\n"
    "  '内门弟子': { spiritStones: 2500, contribution: 25 },\n"
    "  '真传弟子': { spiritStones: 6000, contribution: 60 },\n"
    "  '长老': { spiritStones: 12000, contribution: 120 },\n"
    "  '宗主': { spiritStones: 25000, contribution: 300 },\n"
    "};\n"
    "const SECT_RANK_SALARY_ORDER = ['外门弟子', '内门弟子', '真传弟子', '长老', '宗主'];\n"
    "// 未知/缺失职衔一律按最低档（防越权多领）\n"
    "function sectSalaryOf(rank: unknown): { spiritStones: number; contribution: number } {\n"
    "  return SECT_RANK_SALARY[String(rank || '')] || SECT_RANK_SALARY[SECT_RANK_SALARY_ORDER[0]];\n"
    "}\n"
    "// 今日可领/已领（只读）\n"
    "app.get('/api/sect/salary/status', authenticateToken, sectReadLimit, async (req: any, res: any) => {\n"
    "  try {\n"
    "    const pl = await sectGfPlayerOf(req.user.id);\n"
    "    if (!pl || !pl.sectId) return res.json({ inSect: false, claimed: false });\n"
    "    const rank = String(pl.sectRank || '');\n"
    "    const sal = sectSalaryOf(rank);\n"
    "    const date = bjDate(Date.now());\n"
    "    const row: any = await dbGet('SELECT 1 AS c FROM sect_welfare_claims WHERE user_id = ? AND date = ? AND kind = ?', [req.user.id, date, 'rank_salary']);\n"
    "    res.json({ inSect: true, rank, spiritStones: sal.spiritStones, contribution: sal.contribution, claimed: !!row, date });\n"
    "  } catch (e: any) {\n"
    "    console.error('sect salary status error:', e?.message || e);\n"
    "    res.status(500).json({ error: '服务器繁忙' });\n"
    "  }\n"
    "});\n"
    "// 领取宗门俸禄（按职位；每日限一次）\n"
    "app.post('/api/sect/salary', authenticateToken, sectWriteLimit, async (req: any, res: any) => {\n"
    "  try {\n"
    "    const pl = await sectGfPlayerOf(req.user.id);\n"
    "    if (!pl || !pl.sectId) return res.status(400).json({ error: '你还没有加入宗门，无法领取俸禄', code: 'NO_SECT' });\n"
    "    const rank = String(pl.sectRank || '');\n"
    "    const sal = sectSalaryOf(rank);\n"
    "    const date = bjDate(Date.now());\n"
    "    try {\n"
    "      await dbRun('INSERT INTO sect_welfare_claims (user_id, date, kind, claimed_at) VALUES (?, ?, ?, ?)', [req.user.id, date, 'rank_salary', nowIso()]);\n"
    "    } catch (e: any) {\n"
    "      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '今日俸禄已领取', code: 'ALREADY_CLAIMED' });\n"
    "      throw e;\n"
    "    }\n"
    "    let contribAfter = 0;\n"
    "    const grant = await updatePlayerSave(req.user.id, (saveData: any) => {\n"
    "      const p = saveData && saveData.player;\n"
    "      if (!p) return;\n"
    "      p.spiritStones = (Number(p.spiritStones) || 0) + sal.spiritStones;\n"
    "      const c0 = Math.max(0, Math.floor(Number(p.sectContribution) || 0));\n"
    "      p.sectContribution = c0 + sal.contribution;\n"
    "      contribAfter = p.sectContribution;\n"
    "    });\n"
    "    if (!grant.ok) {\n"
    "      await dbRun('DELETE FROM sect_welfare_claims WHERE user_id = ? AND date = ? AND kind = ?', [req.user.id, date, 'rank_salary']).catch(() => undefined);\n"
    "      return res.status(400).json({ error: grant.error || '俸禄发放失败' });\n"
    "    }\n"
    "    res.json({ message: '俸禄已入账', rank, reward: { spiritStones: sal.spiritStones, contribution: sal.contribution }, contribution: contribAfter, date });\n"
    "  } catch (e: any) {\n"
    "    console.error('sect salary error:', e?.message || e);\n"
    "    res.status(500).json({ error: '服务器繁忙' });\n"
    "  }\n"
    "});\n"
    "\n"
)

# 落盘形态：纯 ASCII
BLOCK = _zh(BLOCK_RAW)

EDITS = [
    ("R081 注入宗门俸禄端点", INSERT_ANCHOR, BLOCK + INSERT_ANCHOR),
]

# 关键门禁锚（全 ASCII；用 _zh 生成，与落盘形态同源）
ANCHOR_409 = _zh("res.status(409).json({ error: '今日俸禄已领取', code: 'ALREADY_CLAIMED' })")
ANCHOR_400 = _zh("res.status(400).json({ error: '你还没有加入宗门，无法领取俸禄', code: 'NO_SECT' })")
ANCHOR_MSG_OK = _zh("message: '俸禄已入账'")
ANCHOR_GRANT = ("const grant = await updatePlayerSave(req.user.id, (saveData: any) => {\n"
                "      const p = saveData && saveData.player;\n"
                "      if (!p) return;\n"
                "      p.spiritStones = (Number(p.spiritStones) || 0) + sal.spiritStones;")
ANCHOR_RANK_LORD = _zh("'宗主': { spiritStones: 25000, contribution: 300 }")

REQUIRES = [
    (INSERT_ANCHOR, 1, "宗门公告端点注释必须在位（本环唯一插入锚）"),
    ("app.post('/api/sect/welfare/claim'", 1, "V27 福利端点必须在位（本环不动它，作对照）"),
    ("function sectGfPlayerOf(", 1, "读存档 player 助手必须在位（本环复用它取 sectRank）"),
    ("const nowIso = () => new Date().toISOString();", 1, "nowIso 必须在位（claim 行写入时间）"),
    ("function bjDate(ms: number): string {", 1, "bjDate 必须在位（北京日切口径）"),
    ("function updatePlayerSave(", 1, "updatePlayerSave 必须在位（发放通道）"),
    ("CREATE TABLE IF NOT EXISTS sect_welfare_claims (", 1, "幂等表必须在位（PK user_id,date,kind）"),
    ("const STONE_ECHO_RE = /^\\/api\\/(pet|wudao|farm|alchemy|teahouse|couple|friends|mail|offline|quest|sect|", 1,
     "灵石回显中间件必须在位（/api/sect/* 白名单，本环灵石回显依赖它）"),
]

BASE_NEEDLES = ["res.status(403", "setInterval(", "PRAGMA", "require(",
                "app.post('/api/sect/welfare/claim'",
                "CREATE TABLE IF NOT EXISTS sect_welfare_claims (",
                "function sectGfPlayerOf(",
                "const STONE_ECHO_RE = /^\\/api\\/(pet|wudao|farm|alchemy|teahouse|couple|friends|mail|offline|quest|sect|"]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-081 宗门俸禄（按职位）环")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    # 0) 落盘块必须纯 ASCII（自证 _zh 生效）
    bad = [ch for ch in BLOCK if ord(ch) >= 128]
    if bad:
        fail("BLOCK 转义后仍含非 ASCII: %r" % bad[:10])
    if MARK not in BLOCK:
        fail("BLOCK 缺幂等标记 %s" % MARK)

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:90], n, cnt, why))

    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    base = {k: src.count(k) for k in BASE_NEEDLES}

    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    gates = [
        # ---- 本环改动 ----
        ("R81 状态端点已注入", "app.get('/api/sect/salary/status'", 1),
        ("R81 领取端点已注入", "app.post('/api/sect/salary'", 1),
        ("R81 职位俸禄表已注入",
         "const SECT_RANK_SALARY: Record<string, { spiritStones: number; contribution: number }> = {", 1),
        ("R81 职位序表已注入", "const SECT_RANK_SALARY_ORDER = [", 1),
        ("R81 取值函数已注入", "function sectSalaryOf(rank: unknown): { spiritStones: number; contribution: number } {", 1),
        ("R81 未知职位回退最低档",
         "return SECT_RANK_SALARY[String(rank || '')] || SECT_RANK_SALARY[SECT_RANK_SALARY_ORDER[0]];", 1),
        ("R81 五档齐备(宗主行)", ANCHOR_RANK_LORD, 1),
        ("R81 幂等 INSERT 已就位",
         "INSERT INTO sect_welfare_claims (user_id, date, kind, claimed_at) VALUES (?, ?, ?, ?)', [req.user.id, date, 'rank_salary', nowIso()]", 1),
        ("R81 幂等键 rank_salary（代码 3 处）", "'rank_salary'", 3),
        ("R81 重复领取 409", ANCHOR_409, 1),
        ("R81 未入宗 400 NO_SECT", ANCHOR_400, 1),
        ("R81 发放走 updatePlayerSave（唯一复合锚）", ANCHOR_GRANT, 1),
        ("R81 加灵石", "p.spiritStones = (Number(p.spiritStones) || 0) + sal.spiritStones;", 1),
        ("R81 加贡献", "p.sectContribution = c0 + sal.contribution;", 1),
        ("R81 回执含贡献", "contribution: contribAfter, date });", 1),
        ("R81 回执文案", ANCHOR_MSG_OK, 1),
        ("R81 失败回删 claim 行",
         "await dbRun('DELETE FROM sect_welfare_claims WHERE user_id = ? AND date = ? AND kind = ?', [req.user.id, date, 'rank_salary'])", 1),
        ("R81 幂等标记就位", MARK, 1),
        # ---- 冻结：V27 福利端点 / 幂等表 / 回显中间件一字不动 ----
        ("冻结 V27 福利端点仍在", "app.post('/api/sect/welfare/claim'", base["app.post('/api/sect/welfare/claim'"]),
        ("冻结 sect_welfare_claims 建表未动",
         "CREATE TABLE IF NOT EXISTS sect_welfare_claims (", base["CREATE TABLE IF NOT EXISTS sect_welfare_claims ("]),
        ("冻结 sectGfPlayerOf 未动", "function sectGfPlayerOf(", base["function sectGfPlayerOf("]),
        ("冻结 灵石回显白名单含 sect",
         "const STONE_ECHO_RE = /^\\/api\\/(pet|wudao|farm|alchemy|teahouse|couple|friends|mail|offline|quest|sect|",
         base["const STONE_ECHO_RE = /^\\/api\\/(pet|wudao|farm|alchemy|teahouse|couple|friends|mail|offline|quest|sect|"]),
        # ---- 红线 ----
        ("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]),
        ("红线 未新增 require(", "require(", base["require("]),
        ("红线 未新增 setInterval", "setInterval(", base["setInterval("]),
        ("红线 未新增 PRAGMA", "PRAGMA", base["PRAGMA"]),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    # 语义自证：五档齐全、幂等键 3 处、端点各一、V27 仍一、新增段纯 ASCII
    added_ascii = all(ord(c) < 128 for c in BLOCK)
    sem_ok = (
        added_ascii
        and out.count("const SECT_RANK_SALARY: Record<string") == 1
        and out.count("'rank_salary'") == 3
        and out.count("app.get('/api/sect/salary/status'") == 1
        and out.count("app.post('/api/sect/salary'") == 1
        and out.count("app.post('/api/sect/welfare/claim'") == 1
        and out.count(ANCHOR_RANK_LORD) == 1
    )
    ok = ok and sem_ok
    print("  [%s] %-40s ascii=%s salary_tbl=%d rank_salary=%d endpoints=%d"
          % ("OK" if sem_ok else "FAIL", "R81 语义自证(五档/幂等键/端点各一/纯ASCII)",
             added_ascii, out.count("const SECT_RANK_SALARY: Record<string"),
             out.count("'rank_salary'"),
             out.count("app.get('/api/sect/salary/status'") + out.count("app.post('/api/sect/salary'")))

    if not ok:
        fail("门禁未全绿，未写回")

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
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r081salary-", suffix=".tmp")
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
