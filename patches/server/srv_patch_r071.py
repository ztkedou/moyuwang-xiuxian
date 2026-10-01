# -*- coding: utf-8 -*-
r"""
srv_patch_r071.py — 妖灵「收养 / 归位 / 放生」服务端环（R-071 + R-072 + R-075）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  前置依赖：必须在 **r018**（本环锚点 `R018_CONVERT` 常量行 / `/api/pet/spirit/away` 端点）
  与 **t2spirit**（`pets.merged` 列 / `rollPetName` / `rollPetRarity`）之后。挂链尾即可。

本环做什么
--------------------------------------------------------------------------
  R-071  收养花灵石 + 随机品种品阶：`POST /api/pet/adopt` 加**扣费**（20000 灵石），
         品种（`rollPetName` 仙兽名池）+ 品阶（`rollPetRarity` 凡85/灵12.5/仙2.5）**保持随机**，
         回执带 `cost`。品种品阶的随机性本就在服务端，本环只补「花灵石」这一半。
  R-072  归位后不能重新收养（bug + 功能缺失）：
         · 旧 `adopt` 里 `if (existed) 409` —— 归位后 `pets` 行仍在（`merged=1` 墓碑），
           ⇒ 收养被**永久**挡死，妖灵系统成一次性（服务端侧根因，客户端侧见 yl_r071_ext.py）。
         · 修法：`existed && merged===0` 才拒；`existed && merged>0` ⇒ 先删墓碑行再 INSERT。
  R-075  归位花灵石 + 新增放生：
         · `/api/pet/spirit/away` 加**扣费**（30000 灵石；归位产出可出战灵宠，属高价动作）。
         · 新增 `POST /api/pet/spirit/release`（放生）：**DELETE** 当前 `pets` 行、**免费无产出**，
           释放妖灵槽位 ⇒ 之后可重新收养。
         · 归位 vs 放生：归位=转化（妖灵→灵宠，有产出、30000）；放生=舍弃（无产出、0）。

定价理由（详见报告）
--------------------------------------------------------------------------
  · 收养 20000 = 「买互动额度 / 灵兽远征」同档（同系统既有价格点）；
  · 归位 30000 = 「点化」同档（同系统既有价格点）；
  · 放生 0     = 纯舍弃。凡品/没养过的妖灵用放生腾位最划算，养成的才值得花 30000 归位。
  ★ 三者都是**消耗**（0 新增灵石 faucet）；业务拒绝码一律 **409**（403 会被客户端 Xc() 当会话失效强制登出）。

经济 / 并发口径（照抄 r018 既有先例）
--------------------------------------------------------------------------
  · 扣费走 `updatePlayerSave`（saveLock 互斥 + 回调内二次校验），行缺失 / INSERT 失败一律**补偿退费**。
  · `pets` 的 `UNIQUE(player_id)` 仍是「并发双收养」的唯一原子防线：并发下败方拿 UNIQUE → 退费 409。
  · 放生的 DELETE 以 `del.changes` 判成败（0 行 = 并发下已被他人放生/归位）。

锚区（与既有环零交集，逐条 grep 过）
--------------------------------------------------------------------------
  S0  `const R018_CONVERT = 0.06;` 之后 —— 加 R071_ADOPT_COST / R071_AWAY_COST 两常量。
  S1  `/api/pet/adopt` 三处（existed 判定 / INSERT catch 退费 / 回执带 cost）。
  S2  `/api/pet/spirit/away` 两处（加扣费 / 回执带 cost）。
  S3  away 端点 `console.error('pet spirit away error'` 尾部之后 —— 插入 release 端点。
  ★ 不删 / 不改 r018 的任何常量、端点签名与门禁串（r018 门禁面全部保留）。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ S0 常量（插在 R018_CONVERT 之后）

S0_ANCHOR = "const R018_CONVERT = 0.06;          // 转化率（决策点 3 = A）"

S0_CODE = r"""

// [r071] R-071 / R-072 / R-075 妖灵「收养 / 归位 / 放生」定价（本环新增 2 个消耗常量）
//   · 收养 20000 —— 与「买互动额度 / 灵兽远征」同档（同系统既有价格点），作妖灵入口门票；
//   · 归位 30000 —— 与「点化」同档（同系统既有价格点），归位产出可出战灵宠，属高价动作；
//   · 放生 0     —— 纯舍弃，不产出、不收费，只为腾出妖灵槽位重抽（见本环 S3 端点）。
//   ★ 两者都是**消耗**（0 新增灵石 faucet）；业务拒绝码一律 409。
const R071_ADOPT_COST = 20000;
const R071_AWAY_COST = 30000;"""

# ============================================================ S1 /api/pet/adopt

S1A_OLD = ("    const existed = await dbGet('SELECT id FROM pets WHERE player_id = ?', [userId]);\n"
           "    if (existed) return res.status(409).json({ error: '你已有灵宠相伴' });\n"
           "    const name = rollPetName();\n"
           "    const rarity = rollPetRarity();")
S1A_NEW = ("    const existed: any = await dbGet('SELECT id, merged FROM pets WHERE player_id = ?', [userId]);\n"
           "    if (existed && Number(existed.merged) === 0) return res.status(409).json({ error: '你已有灵宠相伴' });\n"
           "    // R-071 收养花灵石（照抄 r018 补偿式扣费口径：预检 → saveLock 内二次校验 → 失败退费）\n"
           "    const _arow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);\n"
           "    if (!_arow) return res.status(404).json({ error: '请先进游戏创建角色' });\n"
           "    let _abal = 0;\n"
           "    try { _abal = Number(JSON.parse(_arow.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }\n"
           "    if (_abal < R071_ADOPT_COST) return res.status(409).json({ error: `灵石不足：收养需 ${R071_ADOPT_COST}，现有 ${_abal}` });\n"
           "    let _ashort = false;\n"
           "    const _apaid = await updatePlayerSave(userId, (sd: any) => {\n"
           "      const b = Number(sd.player?.spiritStones) || 0;\n"
           "      if (b < R071_ADOPT_COST) { _ashort = true; return; }\n"
           "      sd.player.spiritStones = b - R071_ADOPT_COST;\n"
           "    });\n"
           "    if (!_apaid.ok || _ashort) return res.status(409).json({ error: _ashort ? '灵石不足' : (_apaid.error === 'No save found' ? '请先进游戏创建角色' : '收养失败，请重试') });\n"
           "    // R-072 归位后（merged=1）释放槽位：删墓碑行后重新 INSERT（UNIQUE 仍是并发唯一防线）\n"
           "    if (existed) await dbRun('DELETE FROM pets WHERE player_id = ? AND merged = 1', [userId]);\n"
           "    const name = rollPetName();\n"
           "    const rarity = rollPetRarity();")

S1B_OLD = ("      await dbRun('INSERT INTO pets (player_id, name, rarity, level, exp, hunger, bond) VALUES (?, ?, ?, 0, 0, 0, 0)', [userId, name, rarity]);\n"
           "    } catch (e: any) {\n"
           "      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '你已有灵宠相伴' });\n"
           "      throw e;\n"
           "    }")
S1B_NEW = ("      await dbRun('INSERT INTO pets (player_id, name, rarity, level, exp, hunger, bond) VALUES (?, ?, ?, 0, 0, 0, 0)', [userId, name, rarity]);\n"
           "    } catch (e: any) {\n"
           "      // INSERT 失败（并发双收养 / 已存在 active 行）⇒ 退回已扣的收养费\n"
           "      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + R071_ADOPT_COST; });\n"
           "      if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: '你已有灵宠相伴' });\n"
           "      throw e;\n"
           "    }")

S1C_OLD = "    res.json({ ok: true, pet: petView({ name, rarity, hunger: 0, exp: 0, bond: 0 }) });"
S1C_NEW = "    res.json({ ok: true, pet: petView({ name, rarity, hunger: 0, exp: 0, bond: 0 }), cost: R071_ADOPT_COST });"

# ============================================================ S2 /api/pet/spirit/away

S2A_OLD = ("    if (Number(pet.merged) > 0) return res.status(409).json({ error: '该妖灵已完成归位' });\n"
           "    const upd = await dbRun('UPDATE pets SET merged = 1 WHERE player_id = ? AND merged = 0', [userId]);\n"
           "    if (!upd.changes) return res.status(409).json({ error: '归位状态已变更，请刷新后重试' });")
S2A_NEW = ("    if (Number(pet.merged) > 0) return res.status(409).json({ error: '该妖灵已完成归位' });\n"
           "    // R-075 归位花灵石（归位产出可出战灵宠，故与「点化」同档 30000；口径同收养）\n"
           "    const _wrow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);\n"
           "    if (!_wrow) return res.status(404).json({ error: '请先进游戏创建角色' });\n"
           "    let _wbal = 0;\n"
           "    try { _wbal = Number(JSON.parse(_wrow.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }\n"
           "    if (_wbal < R071_AWAY_COST) return res.status(409).json({ error: `灵石不足：归位需 ${R071_AWAY_COST}，现有 ${_wbal}` });\n"
           "    let _wshort = false;\n"
           "    const _wpaid = await updatePlayerSave(userId, (sd: any) => {\n"
           "      const b = Number(sd.player?.spiritStones) || 0;\n"
           "      if (b < R071_AWAY_COST) { _wshort = true; return; }\n"
           "      sd.player.spiritStones = b - R071_AWAY_COST;\n"
           "    });\n"
           "    if (!_wpaid.ok || _wshort) return res.status(409).json({ error: _wshort ? '灵石不足' : (_wpaid.error === 'No save found' ? '请先进游戏创建角色' : '归位失败，请重试') });\n"
           "    const upd = await dbRun('UPDATE pets SET merged = 1 WHERE player_id = ? AND merged = 0', [userId]);\n"
           "    if (!upd.changes) {\n"
           "      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + R071_AWAY_COST; });\n"
           "      return res.status(409).json({ error: '归位状态已变更，请刷新后重试' });\n"
           "    }")

S2B_OLD = ("      ok: true,\n"
           "      merged: 1,\n"
           "      inheritHints: {")
S2B_NEW = ("      ok: true,\n"
           "      merged: 1,\n"
           "      cost: R071_AWAY_COST,\n"
           "      inheritHints: {")

# ============================================================ S3 release 端点（插在 away 尾部之后）

S3_ANCHOR = ("    console.error('pet spirit away error:', e?.message || e);\n"
             "    res.status(500).json({ error: '服务器繁忙' });\n"
             "  }\n"
             "});")

S3_CODE = r"""

// POST /api/pet/spirit/release — 妖灵放生（R-075）：丢弃当前妖灵（DELETE pets 行），免费、无产出。
//   与「归位」的区别：归位 = 转化（妖灵 → 可出战灵宠，花 R071_AWAY_COST）；放生 = 舍弃（无产出，0 灵石）。
//   两者都释放妖灵槽位 ⇒ 之后可重新 POST /api/pet/adopt 收养新妖灵（R-071 / R-072）。
//   无扣费 ⇒ 无补偿退费面；DELETE 以 changes 判成败（0 行 = 并发下已被他人放生 / 归位）。
app.post('/api/pet/spirit/release', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `pet:release:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const pet: any = await dbGet('SELECT id, name, rarity, merged FROM pets WHERE player_id = ?', [userId]);
    if (!pet) return res.status(404).json({ error: '请先收养一只灵宠' });
    const del = await dbRun('DELETE FROM pets WHERE player_id = ?', [userId]);
    if (!del.changes) return res.status(409).json({ error: '放生失败，请刷新后重试' });
    logPetCare(userId, 'release', `放生「${String(pet.name)}」（${String(pet.rarity)}品），妖灵归隐山林`);
    await r018SpiritSync(userId);
    res.json({ ok: true, released: 1, name: String(pet.name), cost: 0 });
  } catch (e: any) {
    console.error('pet spirit release error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});"""

# ============================================================ 汇总

EDITS = [
    ("S1a adopt 加扣费 + 归位后可重收养", S1A_OLD, S1A_NEW),
    ("S1b adopt INSERT 失败退费",          S1B_OLD, S1B_NEW),
    ("S1c adopt 回执带 cost",              S1C_OLD, S1C_NEW),
    ("S2a away 加扣费",                    S2A_OLD, S2A_NEW),
    ("S2b away 回执带 cost",               S2B_OLD, S2B_NEW),
]

REQUIRES = [
    (S0_ANCHOR, 1, "r018 转化率常量行（本环 S0 锚点）"),
    ("app.post('/api/pet/adopt', authenticateToken", 1, "adopt 端点唯一"),
    ("app.post('/api/pet/spirit/away', authenticateToken", 1, "away 端点唯一"),
    ("function rollPetName(", 1, "品种随机源（t2spirit/petcore）"),
    ("function rollPetRarity(", 1, "品阶随机源（petcore）"),
    ("function updatePlayerSave(", 1, "updatePlayerSave 原语"),
    ("function petView(p: any): any {", 1, "petView 原语"),
    ("function logPetCare(playerId: number, kind: string, detail: string): void {", 1, "logPetCare 原语"),
    ("function r018SpiritSync(userId: number): Promise<any> {", 1, "r018 存档同步（放生后清 petSpirit）"),
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description='R-071/R-072/R-075 妖灵收养·归位·放生（服务端环 r071）')
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:70], n, cnt, why))

    # 2) 幂等
    if "R071_ADOPT_COST" in src or "spirit/release" in src:
        fail("source looks already patched（已存在 R071_ADOPT_COST / spirit/release）")

    # 3) 锚点计数（每个必须恰 1）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)
    if src.count(S0_ANCHOR) != 1:
        fail("S0 锚点 %r 出现 %d 次（期望 1）" % (S0_ANCHOR, src.count(S0_ANCHOR)))
    if src.count(S3_ANCHOR) != 1:
        fail("S3 锚点 %r 出现 %d 次（期望 1）" % (S3_ANCHOR[:80], src.count(S3_ANCHOR)))

    # 4) 应用（先 replace，再 insert_after）
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)
    out = out.replace(S0_ANCHOR, S0_ANCHOR + S0_CODE, 1)
    out = out.replace(S3_ANCHOR, S3_ANCHOR + S3_CODE, 1)

    # 5) 门禁
    base403 = src.count("res.status(403")
    gates = [
        # ---- S0 常量 ----
        ("R71 收养价 20000",           "const R071_ADOPT_COST = 20000;", 1),
        ("R71 归位价 30000",           "const R071_AWAY_COST = 30000;", 1),
        # ---- S1 adopt ----
        ("R71 adopt 只挡 active 行",   "if (existed && Number(existed.merged) === 0) return res.status(409).json({ error: '你已有灵宠相伴' });", 1),
        ("R71 adopt 旧无条件 409 已清零", "if (existed) return res.status(409).json({ error: '你已有灵宠相伴' });", 0),
        ("R71 adopt 归位后删墓碑行",   "if (existed) await dbRun('DELETE FROM pets WHERE player_id = ? AND merged = 1', [userId]);", 1),
        ("R71 adopt 预检扣费",         "if (_abal < R071_ADOPT_COST) return res.status(409).json({ error: `灵石不足：收养需 ${R071_ADOPT_COST}，现有 ${_abal}` });", 1),
        ("R71 adopt saveLock 内二次校验", "if (b < R071_ADOPT_COST) { _ashort = true; return; }", 1),
        ("R71 adopt INSERT 失败退费",  "sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + R071_ADOPT_COST; });", 1),
        ("R71 adopt 回执带 cost",      "res.json({ ok: true, pet: petView({ name, rarity, hunger: 0, exp: 0, bond: 0 }), cost: R071_ADOPT_COST });", 1),
        ("R71 品种随机源仍在",         "const name = rollPetName();", 1),
        ("R71 品阶随机源仍在",         "const rarity = rollPetRarity();", 1),
        # ---- S2 away ----
        ("R71 away 预检扣费",          "if (_wbal < R071_AWAY_COST) return res.status(409).json({ error: `灵石不足：归位需 ${R071_AWAY_COST}，现有 ${_wbal}` });", 1),
        ("R71 away saveLock 内二次校验", "if (b < R071_AWAY_COST) { _wshort = true; return; }", 1),
        ("R71 away UPDATE 失败退费",   "sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + R071_AWAY_COST; });", 1),
        ("R71 away 回执带 cost",       "      merged: 1,\n      cost: R071_AWAY_COST,\n      inheritHints: {", 1),
        # ---- S3 release ----
        ("R71 放生端点",               "app.post('/api/pet/spirit/release', authenticateToken, rateLimit(", 1),
        ("R71 放生 DELETE pets 行",    "const del = await dbRun('DELETE FROM pets WHERE player_id = ?', [userId]);", 1),
        ("R71 放生以 changes 判成败",  "if (!del.changes) return res.status(409).json({ error: '放生失败，请刷新后重试' });", 1),
        ("R71 放生清 petSpirit",       "    logPetCare(userId, 'release', `放生「${String(pet.name)}」（${String(pet.rarity)}品），妖灵归隐山林`);\n    await r018SpiritSync(userId);", 1),
        ("R71 放生回执 cost 0",        "res.json({ ok: true, released: 1, name: String(pet.name), cost: 0 });", 1),
        # ---- 冻结（本环不得回踩 r018 / t2spirit 门禁面）----
        ("冻结 r018 转化率常量未动",   "const R018_CONVERT = 0.06;", 1),
        ("冻结 r018 归位端点签名未动", "app.post('/api/pet/spirit/away', authenticateToken", 1),
        ("冻结 r018 点化端点未动",     "app.post('/api/pet/aptitude', authenticateToken", 1),
        ("冻结 r018 秘径端点未动",     "app.post('/api/pet/spirit/exped', authenticateToken", 1),
        ("冻结 r018 归位端点未整体重写", "if (Number(pet.merged) > 0) return res.status(409).json({ error: '该妖灵已完成归位' });", 1),
        ("冻结 r018 归位 inheritHints 未动", "affection: petT2Affection(pet.bond),", 1),
        ("冻结 feed 端点未动",         "app.post('/api/pet/feed', authenticateToken", 1),
        ("冻结 play 端点未动",         "app.post('/api/pet/play', authenticateToken", 1),
        ("冻结 pets UNIQUE 防线未动",  "player_id INTEGER NOT NULL UNIQUE", 1),
        ("冻结 merged 列定义未动",     "safeAddColumn('pets', 'merged'", 1),
        ("冻结 经济配额函数未动",      "function settleSaveEconV2", 1),
        ("R71 不新增仙途任务",         "QUEST_DEFS", src.count("QUEST_DEFS")),
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

    # 6b) 本环注入块内不得引用 QUEST_DEFS（不新增仙途任务）
    qd = (S0_CODE + S3_CODE).count("QUEST_DEFS")
    good = (qd == 0)
    ok = ok and good
    print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", "R71 注入块不引用 QUEST_DEFS", qd, 0))

    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back.count(S0_ANCHOR + S0_CODE) != 1:
        fail("S0 代码块未按预期出现恰 1 次")
    back = back.replace(S0_ANCHOR + S0_CODE, S0_ANCHOR, 1)
    if back.count(S3_ANCHOR + S3_CODE) != 1:
        fail("S3 代码块未按预期出现恰 1 次")
    back = back.replace(S3_ANCHOR + S3_CODE, S3_ANCHOR, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r071-", suffix=".tmp")
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
