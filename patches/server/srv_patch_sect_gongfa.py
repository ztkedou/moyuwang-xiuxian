# -*- coding: utf-8 -*-
"""
srv_patch_sect_gongfa.py -- v28 宗门功法（宗门「功法阁」）服务端补丁生成器

Reads : srv/index_v27b.ts            (pristine baseline; NEVER modified)
Writes: srv/index_v27b_sectgf.ts     (patched product)

背景
  客户端宗门模态（底部「宗门」按钮）的「功法阁」子页恒为空：它的数据源是心法表 `is` 里
  `sectId === player.sectId` 的那几部，而全表只有 `art-spirit-cloud` 绑了静态 id
  `sect-cloud`，玩家实际入的是动态生成的宗门 id（线上实测 `sect-q07t7uh`）。
  本补丁为「功法阁」提供一套**服务端权威**的宗门传承功法：4 阶 × 3 系 = 12 部，每部 5 层。

设计
  * 资源 = **宗门贡献度** `player.sectContribution`（legacy 宗门体系既有字段；任务阁产出、
    藏宝阁消耗）。不新增任何货币/计数，不改动既有任何数值常量。
  * 与既有「心法六卷」(`/api/gongfa`：灵石 + 全属性**百分比** + `player_gongfa` 表) 完全分离：
    本系统只给**定向固定值**，且受**职衔 + 境界**双门槛约束，表为 `player_sect_gongfa`。
  * 归属校验口径：legacy 宗门是**纯客户端存档字段**（服务端无成员表），故以
    `save_data.player.sectId` 非空 + `sectRank`/`realm` 作为门槛依据 —— 与客户端同源。
  * 入账一律走 `updatePlayerSave()`（saveLock 读改写互斥 + gm_revision++ 触发客户端拉新档）。
    加成落在 `player.sectGongfa = { "<id>": level }`，客户端 `xt(player)` 直接读该字段。
  * 表 `player_sect_gongfa` 是**权威层数**；`player.sectGongfa` 是给客户端消费的镜像，
    每次学习/升级整表重建（顺手修复被客户端权威存档覆盖造成的漂移）。

Engineering guarantees enforced here (any failure => sys.exit(1), no write):
  1. every anchor occurs EXACTLY once in the source;
  2. round-trip equivalence: replacing each new fragment back with its old fragment yields
     the source byte-for-byte;
  3. every newly introduced identifier occurs 0 times in the source;
  4. every INJECTED fragment (the added text) is pure ASCII (non-ASCII emitted as \\uXXXX);
  5. the source is not already patched.

Run (paths are relative to the current working directory, i.e. yl-deploy/):
  python srv_patch_sect_gongfa.py
  python srv_patch_sect_gongfa.py --src srv/index_v27b.ts --out srv/index_v27b_sectgf.ts
"""
import argparse
import io
import os
import sys
import hashlib

DEFAULT_SRC = os.path.join("srv", "index_v27b.ts")
DEFAULT_OUT = os.path.join("srv", "index_v27b_sectgf.ts")


def esc(s: str) -> str:
    """Escape every non-ASCII code point as \\uXXXX so injected text is pure ASCII."""
    out = []
    for ch in s:
        if ord(ch) < 128:
            out.append(ch)
        else:
            out.append("\\u%04x" % ord(ch))
    return "".join(out)


# ---------------------------------------------------------------------------
# 数值表（单一事实源：必须与 yl_sectgf_ext.py 的 SECT_GF_CATALOG 逐字一致；
#         _test_sectgf.py 会做跨文件一致性断言）
# ---------------------------------------------------------------------------
SECT_GF_MAX_LEVEL = 5
SECT_GF_TIER_BASE = {1: 100, 2: 250, 3: 600, 4: 1500}

SECT_GF_CATALOG = [
    {"id": "sgf-t1-atk", "tier": 1, "name": "淬体拳谱", "grade": "黄",
     "rank": "外门弟子", "realm": "炼气期",
     "desc": "外门弟子入门拳谱，以拳意淬炼筋骨，出手更疾更重。",
     "per": {"attack": 8, "speed": 2}},
    {"id": "sgf-t1-def", "tier": 1, "name": "玄龟吐纳诀", "grade": "黄",
     "rank": "外门弟子", "realm": "炼气期",
     "desc": "效玄龟闭息之法，吐纳绵长，皮糙肉厚，耐打耐磨。",
     "per": {"defense": 6, "maxHp": 30}},
    {"id": "sgf-t1-psi", "tier": 1, "name": "引气归元篇", "grade": "黄",
     "rank": "外门弟子", "realm": "炼气期",
     "desc": "引天地灵气归入丹田，神识渐明，体魄日固。",
     "per": {"spirit": 5, "physique": 4}},
    {"id": "sgf-t2-atk", "tier": 2, "name": "破军剑诀", "grade": "玄",
     "rank": "内门弟子", "realm": "筑基期",
     "desc": "内门剑修必修，剑走破军之势，一往无前，锋锐逼人。",
     "per": {"attack": 25, "speed": 6}},
    {"id": "sgf-t2-def", "tier": 2, "name": "磐石金身诀", "grade": "玄",
     "rank": "内门弟子", "realm": "筑基期",
     "desc": "以磐石之意铸身，气血浑厚，寻常法宝难伤分毫。",
     "per": {"defense": 20, "maxHp": 120}},
    {"id": "sgf-t2-psi", "tier": 2, "name": "灵犀通神篇", "grade": "玄",
     "rank": "内门弟子", "realm": "筑基期",
     "desc": "灵台通明，神识如犀，可窥敌先机，可养自身根骨。",
     "per": {"spirit": 16, "physique": 13}},
    {"id": "sgf-t3-atk", "tier": 3, "name": "焚天烈焰经", "grade": "地",
     "rank": "真传弟子", "realm": "金丹期",
     "desc": "真传绝学，一身真火焚天灼地，出手便是燎原之势。",
     "per": {"attack": 80, "speed": 18}},
    {"id": "sgf-t3-def", "tier": 3, "name": "玄天不灭体", "grade": "地",
     "rank": "真传弟子", "realm": "金丹期",
     "desc": "玄天护体之法，肉身几近不灭，气血如渊，历劫不损。",
     "per": {"defense": 65, "maxHp": 420}},
    {"id": "sgf-t3-psi", "tier": 3, "name": "太虚元神篇", "grade": "地",
     "rank": "真传弟子", "realm": "金丹期",
     "desc": "凝炼太虚元神，神识外放可覆百里，根骨亦随之脱胎换骨。",
     "per": {"spirit": 50, "physique": 40}},
    {"id": "sgf-t4-atk", "tier": 4, "name": "九霄戮仙典", "grade": "天",
     "rank": "长老", "realm": "元婴期",
     "desc": "镇宗杀伐之典，剑意直上九霄，仙神亦可戮之。",
     "per": {"attack": 250, "speed": 55}},
    {"id": "sgf-t4-def", "tier": 4, "name": "混沌镇岳经", "grade": "天",
     "rank": "长老", "realm": "元婴期",
     "desc": "以混沌之气镇守肉壳，一身气血重逾山岳，万法难侵。",
     "per": {"defense": 200, "maxHp": 1400}},
    {"id": "sgf-t4-psi", "tier": 4, "name": "万灵归元录", "grade": "天",
     "rank": "长老", "realm": "元婴期",
     "desc": "万灵归元，元神圆满，神识与根骨同臻化境。",
     "per": {"spirit": 160, "physique": 130}},
]


def _catalog_ts() -> str:
    """Render SECT_GF_CATALOG as a TypeScript array literal (single-quoted, ASCII)."""
    lines = []
    for g in SECT_GF_CATALOG:
        per = ", ".join("%s: %d" % (k, v) for k, v in g["per"].items())
        lines.append(
            "  { id: '%s', tier: %d, name: '%s', grade: '%s', rank: '%s', realm: '%s', "
            "desc: '%s', per: { %s } },"
            % (g["id"], g["tier"], g["name"], g["grade"], g["rank"], g["realm"], g["desc"], per)
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 注入片段（作者用真中文书写，落盘前由 esc() 统一转 \\uXXXX）
# ---------------------------------------------------------------------------

# --- A: 玩家宗门功法进度表（权威层数） --------------------------------------
A_OLD = "  db.run(`CREATE INDEX IF NOT EXISTS idx_sect_ledger_sect ON sect_ledger(sect_id, created_at)`);"

A_ADD = """
  // Y22 sect gongfa progress: one row per (player, gongfa id). PK is the idempotency guard.
  // This table is the AUTHORITATIVE level store; player.sectGongfa in saves.save_data is only a
  // mirror for the client (xt reads it). Written by updatePlayerSave + this table in one request.
  db.run(`CREATE TABLE IF NOT EXISTS player_sect_gongfa (
    user_id INTEGER NOT NULL,
    gongfa_id TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, gongfa_id),
    FOREIGN KEY (user_id) REFERENCES users (id)
  )`);"""

# --- B: 目录 + 纯逻辑核心 ---------------------------------------------------
B_OLD = "// ── V27 限流：读 60/min、写 20/min（按用户分桶；rateLimit 实现见 P1-4/P1-5 段）──"

B_ADD = """
// [sectgfcore] Y22 宗门功法（宗门「功法阁」）纯逻辑核心：4 阶 x 3 系 = 12 部，每部 1..5 层。
// 资源 = 宗门贡献度 player.sectContribution（legacy 宗门既有字段），与「心法六卷」(/api/gongfa：
// 灵石 + 全属性百分比 + player_gongfa 表) 完全分离：本系统只给定向固定值，且受职衔/境界双门槛。
// 每层消耗 = SECT_GF_TIER_BASE[tier] * level（一阶 100/200/300/400/500 ... 四阶 1500..7500）。
// 累计满级（12 部 x 5 层）= 110250 贡献。曲线意图：单部一阶约 1 天、四阶约 4 天（贡献日收入
// 量级 1.2k~6k，随职衔 d=1/1.5/2/3 递增），全部满级约 25~30 天，作为宗门的长期沉淀。
const SECT_GF_MAX_LEVEL = 5;
const SECT_GF_TIER_BASE: Record<number, number> = { 1: 100, 2: 250, 3: 600, 4: 1500 };
const SECT_GF_RANK_ORDER = ['外门弟子', '内门弟子', '真传弟子', '长老', '宗主'];
type SectGfDef = { id: string; tier: number; name: string; grade: string; rank: string; realm: string; desc: string; per: Record<string, number> };
const SECT_GF_LIST: SectGfDef[] = [
__CATALOG__
];
const SECT_GF_BY_ID: Record<string, SectGfDef> = (() => {
  const m: Record<string, SectGfDef> = {};
  for (const g of SECT_GF_LIST) m[g.id] = g;
  return m;
})();
// 层数归一（0..5）
function sectGfLevel(v: unknown): number {
  return Math.min(SECT_GF_MAX_LEVEL, Math.max(0, Math.floor(Number(v) || 0)));
}
// 升到 level 层所需的宗门贡献
function sectGfCost(tier: unknown, level: unknown): number {
  return (SECT_GF_TIER_BASE[Math.floor(Number(tier) || 0)] || 0) * Math.max(1, Math.floor(Number(level) || 1));
}
// 职衔门槛（下标比较；未知职衔一律不通过）
function sectGfRankOk(rank: unknown, need: string): boolean {
  const i = SECT_GF_RANK_ORDER.indexOf(String(rank || ''));
  const j = SECT_GF_RANK_ORDER.indexOf(need);
  return i >= 0 && j >= 0 && i >= j;
}
// 境界门槛（复用排行用境界序）
function sectGfRealmOk(realm: unknown, need: string): boolean {
  const i = REALM_ORDER_FOR_RANKING.indexOf(String(realm || ''));
  const j = REALM_ORDER_FOR_RANKING.indexOf(need);
  return i >= 0 && j >= 0 && i >= j;
}
// 读存档 player（legacy 宗门的单一事实源在客户端存档里）
async function sectGfPlayerOf(userId: number): Promise<any | null> {
  const row: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
  if (!row) return null;
  try {
    const sd = JSON.parse(row.save_data);
    return sd && sd.player ? sd.player : null;
  } catch {
    return null;
  }
}
// 权威层数表
async function sectGfRows(userId: number): Promise<Record<string, number>> {
  const rows: any[] = await dbAll('SELECT gongfa_id, level FROM player_sect_gongfa WHERE user_id = ?', [userId]);
  const out: Record<string, number> = {};
  for (const r of rows || []) out[String(r.gongfa_id)] = sectGfLevel(r.level);
  return out;
}
// 12 部完整镜像（缺项补 0），供写入 player.sectGongfa
function sectGfMirror(levels: Record<string, number>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const g of SECT_GF_LIST) out[g.id] = sectGfLevel(levels[g.id]);
  return out;
}
// 学习/升级共用核心。mode='learn' 要求当前 0 层；mode='upgrade' 要求 1..4 层。
async function sectGfAdvance(userId: number, idRaw: unknown, mode: 'learn' | 'upgrade'): Promise<{ status: number; body: any }> {
  const id = String(idRaw || '');
  const def = SECT_GF_BY_ID[id];
  if (!def) return { status: 400, body: { error: '未知的宗门功法', code: 'BAD_GONGFA' } };
  const pl = await sectGfPlayerOf(userId);
  if (!pl || !pl.sectId) return { status: 400, body: { error: '你还没有加入宗门', code: 'NO_SECT' } };
  if (!sectGfRankOk(pl.sectRank, def.rank)) {
    return { status: 403, body: { error: '职衔不足，需达到' + def.rank, code: 'RANK_TOO_LOW' } };
  }
  if (!sectGfRealmOk(pl.realm, def.realm)) {
    return { status: 403, body: { error: '境界不足，需达到' + def.realm, code: 'REALM_TOO_LOW' } };
  }
  const levels = await sectGfRows(userId);
  const cur = sectGfLevel(levels[id]);
  if (mode === 'learn' && cur > 0) {
    return { status: 409, body: { error: '该功法已领悟，请使用「领悟」提升层数', code: 'ALREADY_LEARNED', level: cur } };
  }
  if (mode === 'upgrade' && cur <= 0) {
    return { status: 409, body: { error: '该功法尚未学习', code: 'NOT_LEARNED', level: cur } };
  }
  if (cur >= SECT_GF_MAX_LEVEL) {
    return { status: 409, body: { error: '该功法已大成（5 层），无法再进', code: 'MAXED', level: cur } };
  }
  const next = cur + 1;
  const cost = sectGfCost(def.tier, next);
  const contrib = Math.max(0, Math.floor(Number(pl.sectContribution) || 0));
  if (contrib < cost) {
    return { status: 400, body: { error: '宗门贡献不足（需 ' + cost + '）', code: 'INSUFFICIENT_CONTRIBUTION', cost, contribution: contrib } };
  }
  const mirror = sectGfMirror(levels);
  mirror[id] = next;
  let applied = false;
  const r = await updatePlayerSave(userId, (sd: any) => {
    const p = sd && sd.player;
    if (!p) return;
    // 锁内二次校验：updatePlayerSave 的 mutate 无中止语义，不满足则原地不动、零副作用
    const bal = Math.max(0, Math.floor(Number(p.sectContribution) || 0));
    if (bal < cost) return;
    p.sectContribution = bal - cost;
    p.sectGongfa = Object.assign({}, mirror); // 整表镜像：顺手修复被客户端存档覆盖造成的漂移
    applied = true;
  });
  if (!r.ok) return { status: 400, body: { error: r.error || '入账失败' } };
  if (!applied) {
    return { status: 400, body: { error: '宗门贡献不足（需 ' + cost + '）', code: 'INSUFFICIENT_CONTRIBUTION', cost } };
  }
  // 层数落表：单调守卫（仅当已存层数 < next 才写入）。
  // 上面的「读层数 → 校验 → 扣贡献」跨越了 saveLock 边界：两个并发请求可能都读到 cur=0
  // 并各自扣一次贡献，随后两次无条件 upsert 都成功 → 同一部功法被重复扣贡献。
  // 因此这里用单条原子语句做并发闸门：抢先者 changes=1，落后者 changes=0。
  // 落后者必须把刚才扣掉的贡献**原样退回**，否则贡献净损失一次。
  const up = await dbRun(
    'INSERT INTO player_sect_gongfa (user_id, gongfa_id, level) VALUES (?, ?, ?) ON CONFLICT(user_id, gongfa_id) DO UPDATE SET level = excluded.level, updated_at = CURRENT_TIMESTAMP WHERE player_sect_gongfa.level < excluded.level',
    [userId, id, next]
  );
  if (!up.changes) {
    const fresh = await sectGfRows(userId);
    await updatePlayerSave(userId, (sd: any) => {
      const p = sd && sd.player;
      if (!p) return;
      p.sectContribution = Math.max(0, Math.floor(Number(p.sectContribution) || 0) + cost);
      p.sectGongfa = Object.assign({}, sectGfMirror(fresh));
    });
    return { status: 409, body: { error: '该功法已被抢先领悟，请刷新后重试', code: 'CONFLICT', cost } };
  }
  return {
    status: 200,
    body: {
      message: '【' + def.name + '】已领悟至第 ' + next + ' 层',
      id, name: def.name, level: next, maxed: next >= SECT_GF_MAX_LEVEL,
      cost, contribution: contrib - cost, levels: mirror,
    },
  };
}
const sectGfReadLimit = rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `sectgf:r:${req.user.id}` });
const sectGfWriteLimit = rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `sectgf:w:${req.user.id}` });

// 宗门功法列表：12 部目录 + 我的层数 + 当前贡献/职衔/境界（一页全量，不落账）
app.get('/api/sect/gongfa', authenticateToken, sectGfReadLimit, async (req: any, res: any) => {
  try {
    const pl = await sectGfPlayerOf(req.user.id);
    if (!pl || !pl.sectId) return res.status(400).json({ error: '你还没有加入宗门', code: 'NO_SECT' });
    const levels = await sectGfRows(req.user.id);
    res.json({
      sectId: String(pl.sectId),
      sectRank: String(pl.sectRank || ''),
      realm: String(pl.realm || ''),
      contribution: Math.max(0, Math.floor(Number(pl.sectContribution) || 0)),
      maxLevel: SECT_GF_MAX_LEVEL,
      tierBase: SECT_GF_TIER_BASE,
      gongfa: SECT_GF_LIST.map((g) => Object.assign({}, g, { cost: sectGfCost(g.tier, 1) })),
      levels: sectGfMirror(levels),
    });
  } catch (e: any) {
    console.error('sect gongfa list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 学习宗门功法（0 -> 1 层）：职衔+境界+贡献三重校验 -> updatePlayerSave 扣贡献并写 player.sectGongfa
app.post('/api/sect/gongfa/learn', authenticateToken, sectGfWriteLimit, async (req: any, res: any) => {
  try {
    const out = await sectGfAdvance(req.user.id, req.body?.id, 'learn');
    res.status(out.status).json(out.body);
  } catch (e: any) {
    console.error('sect gongfa learn error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// 领悟宗门功法（L -> L+1 层，最高 5 层）
app.post('/api/sect/gongfa/upgrade', authenticateToken, sectGfWriteLimit, async (req: any, res: any) => {
  try {
    const out = await sectGfAdvance(req.user.id, req.body?.id, 'upgrade');
    res.status(out.status).json(out.body);
  } catch (e: any) {
    console.error('sect gongfa upgrade error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

"""

# ---------------------------------------------------------------------------
# Edit table: (label, old, new)
# ---------------------------------------------------------------------------
B_ADD_FULL = B_ADD.replace("__CATALOG__", _catalog_ts())

EDITS = [
    ("A_progress_table", A_OLD, A_OLD + esc(A_ADD)),
    ("B_core_and_api",   B_OLD, esc(B_ADD_FULL) + B_OLD),
]

NEW_IDENTIFIERS = [
    "player_sect_gongfa", "sectgfcore",
    "SECT_GF_MAX_LEVEL", "SECT_GF_TIER_BASE", "SECT_GF_RANK_ORDER",
    "SECT_GF_LIST", "SECT_GF_BY_ID", "SectGfDef",
    "sectGfLevel", "sectGfCost", "sectGfRankOk", "sectGfRealmOk",
    "sectGfPlayerOf", "sectGfRows", "sectGfMirror", "sectGfAdvance",
    "sectGfReadLimit", "sectGfWriteLimit",
    "sectGongfa",
]


def injected_text(label: str, old: str, new: str):
    """Return the text actually injected by this edit (None => in-place edit)."""
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
        description="Generate the v28 sect-gongfa server patch product."
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

    # 5) source must not already be patched
    for marker in ("player_sect_gongfa", "sectgfcore"):
        if marker in src:
            fail("source already contains marker %r; refusing to double-patch" % marker)

    # 1) anchor uniqueness
    for label, old, _new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("anchor %s occurs %d times (expected exactly 1)" % (label, n))

    # 3) new identifiers must not pre-exist
    for ident in NEW_IDENTIFIERS:
        n = src.count(ident)
        if n != 0:
            fail("identifier %r already occurs %d times in source" % (ident, n))

    # 4) injected text must be pure ASCII
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

    # 2) round-trip equivalence (undo in reverse order)
    rt = out
    for label, old, new in reversed(EDITS):
        if rt.count(new) != 1:
            fail("round-trip: fragment %s occurs %d times in product" % (label, rt.count(new)))
        rt = rt.replace(new, old, 1)
    if rt != src:
        fail("round-trip mismatch: product is not an exact superset of source")

    # 端点必须注册在 /api/sect/:id 之前，否则会被通配路由吞掉
    if out.index("app.get('/api/sect/gongfa'") > out.index("app.get('/api/sect/:id'"):
        fail("new /api/sect/gongfa routes must be registered BEFORE /api/sect/:id")

    with io.open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(out)

    def md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    print("OK  source : %s  chars=%d bytes=%d md5=%s" % (src_path, len(src), len(src.encode("utf-8")), md5(src)))
    print("OK  product: %s  chars=%d bytes=%d md5=%s" % (out_path, len(out), len(out.encode("utf-8")), md5(out)))
    print("OK  delta  : chars=+%d bytes=+%d" % (len(out) - len(src), len(out.encode("utf-8")) - len(src.encode("utf-8"))))
    for label, old, new in EDITS:
        added = injected_text(label, old, new)
        if added is None:
            print("    ~ %-16s in-place ASCII edit" % label)
        else:
            print("    + %-16s injected chars=%d (ascii=%s)" % (label, len(added), added.isascii()))
    print("OK  all anchors unique, identifiers collision-free, round-trip byte-exact, injected text ASCII")


if __name__ == "__main__":
    main()
