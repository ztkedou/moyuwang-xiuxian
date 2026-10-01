# -*- coding: utf-8 -*-
r"""
srv_patch_r018b.py -- R-018 D5 灵纹（服务端环 r018b）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  前置依赖：必须在 **r018** 之后（本环改写 r018 注入块内的三处纯函数体 / 响应体，
  并复用其 `r018SpiritBonus()` / `R018_EXPED_EXP` / `petLevel()` / `petView()` / `logPetCare()`）。
  lead 接线时请把本环挂在 `srv_patch_r018.py` **之后**、链尾。

=========================================================================== 本环做什么（R-018 缺口 1：D5 灵纹整维）
  设计原文 = `策划_妖灵培养重设计.md` §2 D5：
    「妖灵每 10 级解锁 1 条「灵纹」，从已解锁的灵纹中任选 1 条生效；花 50,000 灵石可换纹。」
    | 灵纹 | 解锁 | 效果 | 落点 |
    | 锐纹 | Lv10 | 主人暴击率 +1.5% | 客户端 |
    | 御纹 | Lv20 | 主人减伤 +2%    | 客户端 |
    | 疾纹 | Lv30 | 主人闪避 +1.5% | 客户端 |
    | 噬纹 | Lv40 | 主人吸血 +1%    | 客户端 |
    | 蕴纹 | Lv50 | 妖灵秘径修为产出 +30% | 服务端 |
    | 天纹 | Lv60 | 妖灵之力 PP ×1.10 | 服务端 |
    新增列：`pets.rune_active TEXT DEFAULT ''`（§8.1 落点清单第 15 行）。
  ★ 本环补齐 r018 第一版按决策点 9（「D5 留第二版」）**刻意未做**的整维。
    6 条灵纹 / 解锁等级 / 换纹价 / 「1 条生效」全部照设计原文，**未发明任何数值**。

=========================================================================== 幂等 / 红线
  · 幂等：`--src` 内出现 `r018bRuneDef` / `rune_active` 即判「已打过」并拒绝二次应用。
  · 新列走 `safeAddColumn`（容忍 duplicate column name；冷启动 / 重跑双安全）。
  · 业务拒绝码一律 **409**（未解锁 / 灵石不足），参数错 **400**；**不新增 `res.status(403)`**
    （基线 11；403 会被客户端 `Xc()` 当会话失效并强制登出）。
  · 0 新增灵石 faucet（换纹是**消耗**灵石）；修为产出仍是既有秘径的 +30% 派生（有灵石对价）。
  · 不引用 QUEST_DEFS（不新增仙途任务）。

=========================================================================== 锚区（与 r018 同区但**只改其函数体 / 响应体，不改其门禁面**）
  S1  DDL：`safeAddColumn('pets','aptitude',…)` 之后追加 `pets.rune_active`（仍在 db.serialize 回调内）。
  S2  整块注入（常量 + 纯函数 + `POST /api/pet/rune`）：插在 `// [wudaocore]` 之前
      ⇒ 物理上落在 r018 注入块**之后**（`// [/t2spirit]` … `[r018]` … `[r018b]` … `[wudaocore]`）。
  S3  `GET /api/pet` 的 pets SELECT 加 `rune_active`。
  S4  `r018SpiritSync()` 的 SELECT 加 `rune_active`，payload 改走 `r018bSpiritBonus()`（含天纹 ×1.10）。
  S5  `GET /api/pet` 回显 `spirit` 的 `r018SpiritBonus(...)` 调用改走 `r018bSpiritBonus(...)`
      （保留 r018 门禁串 `? Object.assign({ level: petLevel(pet.hunger), …` 一字不动）。
  S6  `GET /api/pet` 响应追加 `rune`（当前激活 + 已解锁列表）+ `consts.runeCost / runeTable`。
  S7  秘径领取（exped/claim）修为入账叠加蕴纹 +30%（保留 r018 门禁串
      `sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + R018_EXPED_EXP;` 一字不动）。

=========================================================================== 一处口径澄清（非发明，按设计原文两句话合成）
  设计 §2 D5 表头写「任选 1 条生效」+「换纹 50,000 灵石/次」⇒ 本环实现为
  **首次激活免费、此后换纹 50,000 灵石/次**（`cost = cur ? R018B_RUNE_COST : 0`）。
  若产品希望「每次（含首次）都收 50,000」，把该行改成 `const cost = R018B_RUNE_COST;` 即可（单点）。
"""

import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ S2 纯逻辑 + 端点

R018B_CODE = r'''
// [r018b] R-018 D5 灵纹（6 条被动 · 任选 1 条生效 · 每 10 级解锁）
//   ★ 本环 = r018 的 D5 补齐（r018 第一版按决策点 9 留第二版）。不改 r018 既有常量 / 端点签名，
//     只在 r018 的纯函数体内接入「灵纹」这一层（r018 自身门禁面全部保留）。
//   落点：锐纹/御纹/疾纹/噬纹 → 客户端战斗层（player.petSpirit.rune* → YlxwBattleBonus）；
//         蕴纹 → 服务端秘径修为 +30%；天纹 → 服务端 PP ×1.10。
//   消耗：首次激活免费；此后换纹 50,000 灵石/次（策划 §2 D5「任选 1 条生效」+「换纹 50,000/次」）。
const R018B_RUNE_COST = 50000;      // 换纹单价（首次激活免费）
const R018B_RUNE_TABLE: Record<string, { key: string; name: string; unlock: number; kind: string; value: number; desc: string }> = {
  rui:  { key: 'rui',  name: '锐纹', unlock: 10, kind: 'critRate',        value: 0.015, desc: '主人暴击率 +1.5%' },
  yu:   { key: 'yu',   name: '御纹', unlock: 20, kind: 'damageReduction', value: 0.02,  desc: '主人减伤 +2%' },
  ji:   { key: 'ji',   name: '疾纹', unlock: 30, kind: 'dodgeRate',       value: 0.015, desc: '主人闪避 +1.5%' },
  shi:  { key: 'shi',  name: '噬纹', unlock: 40, kind: 'lifeLeech',       value: 0.01,  desc: '主人吸血 +1%' },
  yun:  { key: 'yun',  name: '蕴纹', unlock: 50, kind: 'expMul',          value: 0.30,  desc: '妖灵秘径修为产出 +30%' },
  tian: { key: 'tian', name: '天纹', unlock: 60, kind: 'ppMul',           value: 0.10,  desc: '妖灵之力 PP ×1.10' },
};
// 灵纹定义（未知 key ⇒ null）
function r018bRuneDef(key: unknown): { key: string; name: string; unlock: number; kind: string; value: number; desc: string } | null {
  const k = String(key == null ? '' : key);
  return Object.prototype.hasOwnProperty.call(R018B_RUNE_TABLE, k) ? R018B_RUNE_TABLE[k] : null;
}
// 已解锁灵纹列表（含 unlocked 标志；供 GET /api/pet 回显）
function r018bRuneList(level: unknown): any[] {
  const lv = Math.max(0, Math.min(99, Math.floor(Number(level) || 0)));
  return Object.keys(R018B_RUNE_TABLE).map((k) => {
    const d = R018B_RUNE_TABLE[k];
    return { key: d.key, name: d.name, unlock: d.unlock, desc: d.desc, unlocked: lv >= d.unlock };
  });
}
// 当前生效灵纹的效果（未解锁 / 未激活 ⇒ 全 0、乘数 1）
function r018bRuneEffect(key: unknown, level: unknown): { key: string; critRate: number; dodgeRate: number; lifeLeech: number; damageReduction: number; expMul: number; ppMul: number } {
  const zero = { key: '', critRate: 0, dodgeRate: 0, lifeLeech: 0, damageReduction: 0, expMul: 0, ppMul: 1 };
  const d = r018bRuneDef(key);
  if (!d) return zero;
  const lv = Math.max(0, Math.min(99, Math.floor(Number(level) || 0)));
  if (lv < d.unlock) return zero;
  const o = Object.assign({}, zero, { key: d.key });
  if (d.kind === 'critRate') o.critRate = d.value;
  else if (d.kind === 'dodgeRate') o.dodgeRate = d.value;
  else if (d.kind === 'lifeLeech') o.lifeLeech = d.value;
  else if (d.kind === 'damageReduction') o.damageReduction = d.value;
  else if (d.kind === 'expMul') o.expMul = d.value;
  else if (d.kind === 'ppMul') o.ppMul = 1 + d.value;
  return o;
}
// 基础加成 + 灵纹（天纹 ×1.10）→ 存档 payload（与 GET /api/pet 回显同源同式）
function r018bApplyRune(b: { pp: number; attack: number; defense: number; maxHp: number; speed: number }, rn: { key: string; critRate: number; dodgeRate: number; lifeLeech: number; damageReduction: number; ppMul: number }): any {
  const mul = (rn && rn.ppMul) ? rn.ppMul : 1;
  return {
    pp: Math.round(b.pp * mul * 10000) / 10000,
    attack: Math.floor(b.attack * mul),
    defense: Math.floor(b.defense * mul),
    maxHp: Math.floor(b.maxHp * mul),
    speed: Math.floor(b.speed * mul),
    rune: rn ? rn.key : '',
    runeCrit: rn ? rn.critRate : 0,
    runeDodge: rn ? rn.dodgeRate : 0,
    runeLeech: rn ? rn.lifeLeech : 0,
    runeDR: rn ? rn.damageReduction : 0,
  };
}
// 品阶 / 等级 / 羁绊 / 资质 + 灵纹 → 主人加成（GET /api/pet 与 r018SpiritSync 同源同式）
function r018bSpiritBonus(rarity: unknown, level: unknown, bond: unknown, aptitude: unknown, runeKey: unknown): any {
  const b = r018SpiritBonus(rarity, level, bond, aptitude);
  return r018bApplyRune(b, r018bRuneEffect(runeKey, level));
}
// 秘径修为（蕴纹 +30%）：返回应发修为（无蕴纹 = R018_EXPED_EXP）
function r018bExpedExp(runeKey: unknown, level: unknown): number {
  const rn = r018bRuneEffect(runeKey, level);
  return R018_EXPED_EXP + Math.floor(R018_EXPED_EXP * (rn.expMul || 0));
}

// POST /api/pet/rune — 换纹（D5）：首次激活免费，此后 50,000 灵石/次；须已解锁（level ≥ unlock）。
//   事务口径 = r018 同款补偿式：预检 → 扣费（saveLock 互斥，二次校验）→ 原子 UPDATE → 行缺失补偿退费。
app.post('/api/pet/rune', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `pet:rune:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const pet: any = await dbGet('SELECT id, name, hunger, rune_active, merged FROM pets WHERE player_id = ?', [userId]);
    if (!pet) return res.status(404).json({ error: '请先收养一只灵宠' });
    if (Number(pet.merged) > 0) return res.status(409).json({ error: '妖灵已归位，无法换纹' });
    const key = String(req.body?.rune ?? '');
    const def = r018bRuneDef(key);
    if (!def) return res.status(400).json({ error: '未知的灵纹' });
    const level = petLevel(pet.hunger);
    if (level < def.unlock) return res.status(409).json({ error: `「${def.name}」需妖灵达到 ${def.unlock} 级` });
    const cur = String(pet.rune_active || '');
    if (cur === key) return res.status(409).json({ error: `「${def.name}」已生效` });
    const cost = cur ? R018B_RUNE_COST : 0; // 首次激活免费（策划 §2 D5「任选 1 条生效」）
    if (cost > 0) {
      const srow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
      if (!srow) return res.status(404).json({ error: '请先进游戏创建角色' });
      let bal = 0;
      try { bal = Number(JSON.parse(srow.save_data)?.player?.spiritStones) || 0; } catch { return res.status(500).json({ error: '存档解析失败' }); }
      if (bal < cost) return res.status(409).json({ error: `灵石不足：需 ${cost}，现有 ${bal}` });
      let short = false;
      const paid = await updatePlayerSave(userId, (sd: any) => {
        const b = Number(sd.player?.spiritStones) || 0;
        if (b < cost) { short = true; return; }
        sd.player.spiritStones = b - cost;
      });
      if (!paid.ok || short) {
        return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '换纹失败，请重试') });
      }
    }
    const upd = await dbRun('UPDATE pets SET rune_active = ? WHERE player_id = ?', [key, userId]);
    if (!upd.changes) {
      if (cost > 0) await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + cost; });
      return res.status(404).json({ error: '请先收养一只灵宠' });
    }
    logPetCare(userId, 'rune', `妖灵换纹「${def.name}」（${def.desc}）${cost > 0 ? '，消耗 ' + cost + ' 灵石' : '（首次激活免费）'}`);
    const spirit = await r018SpiritSync(userId);
    const fresh: any = await dbGet('SELECT name, rarity, hunger, exp, bond, aptitude, merged FROM pets WHERE player_id = ?', [userId]);
    res.json({ ok: true, rune: key, cost, spirit, pet: petView(fresh) });
  } catch (e: any) {
    console.error('pet rune error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});
'''

# --------------------------------------------------------------------------- 锚点

# S2 注入锚：`[wudaocore]` 之前（= 物理上 r018 注入块之后）
S2_ANCHOR = "// [wudaocore] R-GAME3 悟道系统纯逻辑核心"

A_DDL = "safeAddColumn('pets', 'aptitude', 'ALTER TABLE pets ADD COLUMN aptitude INTEGER NOT NULL DEFAULT 0');"
A_GET_SELECT = "'SELECT name, rarity, hunger, exp, bond, aptitude, merged, created_at FROM pets WHERE player_id = ?'"
A_SYNC_SELECT = "const row: any = await dbGet('SELECT rarity, hunger, bond, aptitude, merged FROM pets WHERE player_id = ?', [userId]);"
A_SYNC_PAYLOAD = (
    "  const b = r018SpiritBonus(row.rarity, level, row.bond, row.aptitude);\n"
    "  const payload = { pp: b.pp, attack: b.attack, defense: b.defense, maxHp: b.maxHp, speed: b.speed, level, rarity: String(row.rarity) };"
)
A_GET_SPIRIT = "r018SpiritBonus(pet.rarity, petLevel(pet.hunger), pet.bond, pet.aptitude))"
A_GET_CONSTS = "        convert: R018_CONVERT, feedTiers: R018_FEED_TIERS, playKinds: R018_PLAY_KINDS,"
A_GET_RUNE_INS = "      consts: {\n        feedCost: PET_FEED_COST, hungerPerFeed: PET_HUNGER_PER_FEED, hungerMax: PET_HUNGER_MAX,"
A_EXPED_EXP = "    await updatePlayerSave(userId, (sd: any) => { if (sd.player) sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + R018_EXPED_EXP; });"
A_EXPED_GAIN = "res.json({ ok: true, pet: petView(fresh), spirit, expGain: R018_EXPED_EXP });"

EDITS = [
    # S1 DDL：pets.rune_active 幂等加列
    ('S1 DDL 加列 rune_active', A_DDL,
     A_DDL + "\n  // R-018 D5 灵纹（r018b 环）：当前生效灵纹（'' = 未激活）\n"
     "  safeAddColumn('pets', 'rune_active', \"ALTER TABLE pets ADD COLUMN rune_active TEXT NOT NULL DEFAULT ''\");"),
    # S3 GET /api/pet 的 pets SELECT 加 rune_active
    ('S3 GET SELECT 加 rune_active', A_GET_SELECT,
     "'SELECT name, rarity, hunger, exp, bond, aptitude, merged, rune_active, created_at FROM pets WHERE player_id = ?'"),
    # S4a r018SpiritSync SELECT 加 rune_active
    ('S4a sync SELECT 加 rune_active', A_SYNC_SELECT,
     "const row: any = await dbGet('SELECT rarity, hunger, bond, aptitude, merged, rune_active FROM pets WHERE player_id = ?', [userId]);"),
    # S4b r018SpiritSync payload 改走 r018bSpiritBonus（天纹 ×1.10）
    ('S4b sync payload 走 r018bSpiritBonus', A_SYNC_PAYLOAD,
     "  const payload = Object.assign({ level, rarity: String(row.rarity) }, r018bSpiritBonus(row.rarity, level, row.bond, row.aptitude, row.rune_active));"),
    # S5 GET /api/pet 回显 spirit 改走 r018bSpiritBonus
    ('S5 GET spirit 走 r018bSpiritBonus', A_GET_SPIRIT,
     "r018bSpiritBonus(pet.rarity, petLevel(pet.hunger), pet.bond, pet.aptitude, pet.rune_active))"),
    # S6a GET 响应追加 rune（当前激活 + 已解锁列表）
    ('S6a GET 回显 rune', A_GET_RUNE_INS,
     "      rune: (pet && Number(pet.merged) === 0)\n"
     "        ? { active: String(pet.rune_active || ''), list: r018bRuneList(petLevel(pet.hunger)) }\n"
     "        : null,\n" + A_GET_RUNE_INS),
    # S6b consts 追加 runeCost / runeTable
    ('S6b consts 加 runeCost/runeTable', A_GET_CONSTS,
     A_GET_CONSTS + "\n        runeCost: R018B_RUNE_COST, runeTable: R018B_RUNE_TABLE,"),
    # S7a 秘径领取：修为叠加蕴纹 +30%（保留 r018 门禁串）
    ('S7a 秘径修为叠加蕴纹', A_EXPED_EXP,
     "    const _r018bRow: any = await dbGet('SELECT hunger, rune_active FROM pets WHERE player_id = ?', [userId]);\n"
     "    const _r018bBonus = _r018bRow ? (r018bExpedExp(_r018bRow.rune_active, petLevel(_r018bRow.hunger)) - R018_EXPED_EXP) : 0;\n"
     "    await updatePlayerSave(userId, (sd: any) => { if (sd.player) { sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + R018_EXPED_EXP; if (_r018bBonus > 0) sd.player.exp += _r018bBonus; } });"),
    # S7b 秘径领取回执 expGain 反映实际发放
    ('S7b 秘径回执 expGain', A_EXPED_GAIN,
     "res.json({ ok: true, pet: petView(fresh), spirit, expGain: R018_EXPED_EXP + _r018bBonus });"),
]

REQUIRES = [
    ("// [r018] R-018 妖灵培养重设计", 1, "r018 注入块必须在位（本环在其后追加 [r018b]）"),
    ("function r018SpiritBonus(rarity: unknown, level: unknown, bond: unknown, aptitude: unknown): { pp: number; attack: number; defense: number; maxHp: number; speed: number } {", 1, "r018 加成纯函数（本环复用）"),
    ("async function r018SpiritSync(userId: number): Promise<any> {", 1, "r018 存档同步函数（本环改其 SELECT/payload）"),
    ("const R018_EXPED_EXP = 800;", 1, "r018 秘径修为常量（蕴纹基数）"),
    ("function petLevel(", 1, "petLevel 原语"),
    ("function petView(p: any): any {", 1, "petView 原语"),
    ("function logPetCare(playerId: number, kind: string, detail: string): void {", 1, "logPetCare 原语"),
    ("function updatePlayerSave(", 1, "updatePlayerSave 原语"),
    ("app.get('/api/pet', authenticateToken", 1, "GET /api/pet 唯一"),
    ("app.post('/api/pet/spirit/exped/claim', authenticateToken", 1, "秘径领取端点唯一"),
    (S2_ANCHOR, 1, "wudaocore 头（本环 S2 注入锚）"),
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description='R-018 D5 灵纹（服务端环 r018b）')
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
    if "r018bRuneDef" in src or "rune_active" in src:
        fail("source looks already patched（已存在 r018bRuneDef / rune_active）")

    # 3) 锚点计数（每个必须恰 1）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)
    if src.count(S2_ANCHOR) != 1:
        fail("S2 锚点 %r 出现 %d 次（期望 1）" % (S2_ANCHOR, src.count(S2_ANCHOR)))

    # 4) 应用（先 replace，后 insert_before）
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)
    out = out.replace(S2_ANCHOR, R018B_CODE + "\n\n" + S2_ANCHOR, 1)

    # 5) 门禁
    base403 = src.count("res.status(403")
    gates = [
        # ---- S2 纯函数 ----
        ("R18b 换纹价 50000",            "const R018B_RUNE_COST = 50000;", 1),
        ("R18b 灵纹表",                  "const R018B_RUNE_TABLE: Record<string, { key: string; name: string; unlock: number; kind: string; value: number; desc: string }> = {", 1),
        ("R18b 锐纹 Lv10 暴击+1.5%",     "rui:  { key: 'rui',  name: '锐纹', unlock: 10, kind: 'critRate',        value: 0.015, desc: '主人暴击率 +1.5%' },", 1),
        ("R18b 御纹 Lv20 减伤+2%",       "yu:   { key: 'yu',   name: '御纹', unlock: 20, kind: 'damageReduction', value: 0.02,  desc: '主人减伤 +2%' },", 1),
        ("R18b 疾纹 Lv30 闪避+1.5%",     "ji:   { key: 'ji',   name: '疾纹', unlock: 30, kind: 'dodgeRate',       value: 0.015, desc: '主人闪避 +1.5%' },", 1),
        ("R18b 噬纹 Lv40 吸血+1%",       "shi:  { key: 'shi',  name: '噬纹', unlock: 40, kind: 'lifeLeech',       value: 0.01,  desc: '主人吸血 +1%' },", 1),
        ("R18b 蕴纹 Lv50 修为+30%",      "yun:  { key: 'yun',  name: '蕴纹', unlock: 50, kind: 'expMul',          value: 0.30,  desc: '妖灵秘径修为产出 +30%' },", 1),
        ("R18b 天纹 Lv60 PP×1.10",       "tian: { key: 'tian', name: '天纹', unlock: 60, kind: 'ppMul',           value: 0.10,  desc: '妖灵之力 PP ×1.10' },", 1),
        ("R18b 灵纹定义纯函数",          "function r018bRuneDef(key: unknown):", 1),
        ("R18b 已解锁列表纯函数",        "function r018bRuneList(level: unknown): any[] {", 1),
        ("R18b 灵纹效果纯函数",          "function r018bRuneEffect(key: unknown, level: unknown):", 1),
        ("R18b 天纹乘数 1+value",        "else if (d.kind === 'ppMul') o.ppMul = 1 + d.value;", 1),
        ("R18b 蕴纹乘数",                "else if (d.kind === 'expMul') o.expMul = d.value;", 1),
        ("R18b 未解锁⇒全 0",             "if (lv < d.unlock) return zero;", 1),
        ("R18b payload 组装",            "function r018bApplyRune(b: { pp: number; attack: number; defense: number; maxHp: number; speed: number }, rn:", 1),
        ("R18b 同源加成函数",            "function r018bSpiritBonus(rarity: unknown, level: unknown, bond: unknown, aptitude: unknown, runeKey: unknown): any {", 1),
        ("R18b 秘径修为纯函数",          "function r018bExpedExp(runeKey: unknown, level: unknown): number {", 1),
        ("R18b 蕴纹 +30% 落点",          "return R018_EXPED_EXP + Math.floor(R018_EXPED_EXP * (rn.expMul || 0));", 1),
        # ---- 端点 ----
        ("R18b 换纹端点",                "app.post('/api/pet/rune', authenticateToken, rateLimit(", 1),
        ("R18b 首次激活免费",            "const cost = cur ? R018B_RUNE_COST : 0;", 1),
        ("R18b 未解锁 409",              "if (level < def.unlock) return res.status(409).json({ error: `「${def.name}」需妖灵达到 ${def.unlock} 级` });", 1),
        ("R18b 未知灵纹 400",            "if (!def) return res.status(400).json({ error: '未知的灵纹' });", 1),
        ("R18b 扣费补偿式",              "        sd.player.spiritStones = b - cost;", 1),
        ("R18b 换纹后同步",              "const spirit = await r018SpiritSync(userId);", 4),
        ("R18b 换纹回执",                "res.json({ ok: true, rune: key, cost, spirit, pet: petView(fresh) });", 1),
        # ---- S1 DDL ----
        ("R18b pets.rune_active 幂等加列", "safeAddColumn('pets', 'rune_active', \"ALTER TABLE pets ADD COLUMN rune_active TEXT NOT NULL DEFAULT ''\");", 1),
        # ---- S3/S4/S5/S6 ----
        ("R18b GET SELECT 带 rune_active", "'SELECT name, rarity, hunger, exp, bond, aptitude, merged, rune_active, created_at FROM pets WHERE player_id = ?'", 1),
        ("R18b sync SELECT 带 rune_active", "'SELECT rarity, hunger, bond, aptitude, merged, rune_active FROM pets WHERE player_id = ?'", 1),
        ("R18b sync payload 走新函数",   "const payload = Object.assign({ level, rarity: String(row.rarity) }, r018bSpiritBonus(row.rarity, level, row.bond, row.aptitude, row.rune_active));", 1),
        ("R18b GET spirit 走新函数",     "r018bSpiritBonus(pet.rarity, petLevel(pet.hunger), pet.bond, pet.aptitude, pet.rune_active))", 1),
        ("R18b GET 回显 rune",           "        ? { active: String(pet.rune_active || ''), list: r018bRuneList(petLevel(pet.hunger)) }", 1),
        ("R18b consts 加 runeCost",      "        runeCost: R018B_RUNE_COST, runeTable: R018B_RUNE_TABLE,", 1),
        # ---- S7 ----
        ("R18b 秘径修为叠加蕴纹",        "const _r018bBonus = _r018bRow ? (r018bExpedExp(_r018bRow.rune_active, petLevel(_r018bRow.hunger)) - R018_EXPED_EXP) : 0;", 1),
        ("R18b 秘径回执 expGain",        "res.json({ ok: true, pet: petView(fresh), spirit, expGain: R018_EXPED_EXP + _r018bBonus });", 1),
        # ---- 冻结：r018 门禁面必须仍在 ----
        ("冻结 r018 注入块仍在",         "// [r018] R-018 妖灵培养重设计", 1),
        ("冻结 r018 写 petSpirit 未动",  "sd.player.petSpirit = payload;", 1),
        ("冻结 r018 清 petSpirit 未动",  "sd.player.petSpirit = null;", 1),
        ("冻结 r018 修为入账串未动",     "sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + R018_EXPED_EXP;", 1),
        ("冻结 r018 GET spirit 门禁串",  "        ? Object.assign({ level: petLevel(pet.hunger), rarity: String(pet.rarity) },", 1),
        ("冻结 r018 GET 常量回显串",     "convert: R018_CONVERT, feedTiers: R018_FEED_TIERS, playKinds: R018_PLAY_KINDS,", 1),
        ("冻结 r018 加成纯函数签名",     "function r018SpiritBonus(rarity: unknown, level: unknown, bond: unknown, aptitude: unknown): { pp: number; attack: number; defense: number; maxHp: number; speed: number } {", 1),
        ("冻结 t2spirit 闭合行仍在",     "// [/t2spirit]", 1),
        ("冻结 r018 PP 纯函数仍在",      "function r018SpiritPP(rarity: unknown, level: unknown, bond: unknown, aptitude: unknown): number {", 1),
        ("R18b 不新增仙途任务",          "QUEST_DEFS", src.count("QUEST_DEFS")),
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

    # 6b) 本环注入块内不得引用 QUEST_DEFS
    qd = R018B_CODE.count("QUEST_DEFS")
    good = (qd == 0)
    ok = ok and good
    print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", "R18b 注入块不引用 QUEST_DEFS", qd, 0))

    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back.count(R018B_CODE + "\n\n" + S2_ANCHOR) != 1:
        fail("S2 代码块未按预期出现恰 1 次")
    back = back.replace(R018B_CODE + "\n\n" + S2_ANCHOR, S2_ANCHOR, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r018b-", suffix=".tmp")
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
