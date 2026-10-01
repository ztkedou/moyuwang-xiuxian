# -*- coding: utf-8 -*-
r"""srv_patch_arenaweek.py — 0.8.10 演武场周榜结算环（链第 22 环 / 新末环）

只做一件事：把客户端**已经对玩家承诺、服务端却零实现**的 T16 周榜结算补上。

## 缺口（假承诺）

客户端 `yl_t16arena_ext.py` 的玩法说明里写着（产物内逐字）：

> 周榜：每周一 0 点按积分排名结算，前 10 名有灵石奖励，第 1 名另得称号「太虚魁首」；
> 本周打满 10 场也有参与奖。

而服务端**只有** `arena_scores`（积分/段位）与试炼/快照端点，**没有任何周结算逻辑**，
也没有任何读取周榜的端点 ⇒ 玩家看到的是一条永远不会兑现的说明。

## 本环改动（5 处，锚区互不重叠，且与前 21 环零交集）

| # | 锚点 | 改动 |
|---:|---|---|
| W1 | 称号目录 `义结金兰` INSERT 之后 | 新增称号目录行 `太虚魁首`（source `arena_week1`，`{"stoneRate":0.05}`） |
| W2 | `// ── 擂台 ──` 之前 | 周榜结算全套：周键换算 / 场次统计 / 奖励表 / `arenaWeekSettle()` |
| W3 | `// POST /api/arena/grudge …` 之前 | 新增 `GET /api/arena/week`（榜单 + 我的名次 + 本周场次 + 最近结算周） |
| W4 | 活动引擎 `setInterval` 块 | 在 `actEngineOn` 早退**之前**插入 `arenaWeekSettle()`（周榜与活动引擎无关） |
| W5 | 活动 boot-run `.catch(...)` 之后 | 周榜 boot-run（重启跨周一 0 点补结算；微任务延迟避免 TDZ） |

## 数值（依据 docs/0.8.8-design/T16-演武场.md §3.3 新增 C / §5.5）

| 名次 | 灵石基数 | 备注 |
|---|---|---|
| 第 1 名 | `20000` | 另授称号「太虚魁首」 |
| 第 2~3 名 | `12000` | |
| 第 4~10 名 | `6000` | |
| 参与奖（本周论剑 ≥10 场） | `2000` | 与名次奖可叠加 |

实发 = `floor(基数 × realmMultOf(userId))`。

★ **倍率取 `realmMultOf`（= `realmStoneFactor`，0.8.9 已由指数收敛为线性）而非策划案写的
`1.5^r`** —— 全仓灵石奖励（擂台结算 / 拜师贺礼 / 求签 / 请安…）都走 `realmMultOf`，
周榜必须同源，否则同一境界出现两套倍率。

## ★ 有意加的一道护栏（与策划案文字的偏离，需知悉）

策划案「积分不清零（滚动累计）」+「按积分排名发奖」组合起来有个经济漏洞：
**早已停玩的高分号会每周白拿名次奖**（积分不清零 ⇒ 永远在前 10）。
本环加护栏：**名次奖要求「本周至少打 1 场论剑」**；参与奖门槛（10 场）不变。
若希望严格照策划案（停玩也发），把 `m >= 1` 改成 `true` 即可（单点开关，见 W2 内注释）。

## ⚠️ 已知边界（如实报）

只补结算「**最近一个已结束的周**」。若停机跨越多个周一，更早的周**不追溯**
（理由：积分不清零 ⇒ 用「当前积分」追溯历史周会给同一批人重复发奖，属奖励膨胀）。

## 工程约束（本项目已踩过的坑，本环逐条遵守）

1. **回调式 sqlite3** ⇒ 一律 `dbGet / dbAll / dbRun`；`db.run(...).catch(...)` 禁止。
2. **ESM** ⇒ `require(` 禁止（门禁断言其计数不增加）。
3. **不新增表**：幂等标记复用既有 `activity_config`（键 `arena_week_settled:<周一>`），
   与活动结算同款；因此**无 DDL、无 ALTER、无 PRAGMA**（坑 12 无关）。
4. **注入块里的中文一律 `zh()` 转义**；门禁 needle 落在注入块内时同样用 `zh()`。
5. **不新增 `res.status(403)`**（`check_srv_087.py` 硬断言其计数；业务拒绝零 403 纪律）。
6. **结算/扣费顺序（坑 16）**：本环只**发**不**扣**，且 `insertMail` 幂等标记在**发完之后**写。
7. 锚点全部带 `expect=1` 前置守卫；插入式改动带「自毁防线」（new 必须含锚点原文）。
8. ⛔ 不改 `srv/index_v28.ts`（链产物）；⛔ 不改前 21 环补丁；⛔ 不改基座指纹。
"""

import argparse
import hashlib
import os
import shutil
import sys
import time

MARK = '[arenaweek]'
HERE = os.path.dirname(os.path.abspath(__file__))


def md5s(s: str) -> str:
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def die(msg: str):
    print('[FAIL] ' + msg)
    sys.exit(1)


def zh(s: str) -> str:
    """注入块编码纪律：非 ASCII 一律转 `\\uXXXX`（星平面转代理对）。"""
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


def apply_one(text: str, tag: str, old: str, new: str, expect: int = 1) -> str:
    n = text.count(old)
    if n != expect:
        die('%s 锚点命中 %d 次（期望 %d）—— 拒绝静默失败' % (tag, n, expect))
    print('  [OK] %-4s 锚点命中 %d 次' % (tag, n))
    return text.replace(old, new, expect)


def _assert_anchor_kept(tag: str, old: str, new: str) -> None:
    if old not in new:
        die('%s 自毁防线：new 未包含锚点原文 ⇒ 锚点行会被整段删除（不是插入）。' % tag)
    print('  [OK] %-4s 自毁防线通过（插入式改动）' % tag)


# ═══════════════════════════════════════════════════════════════════════
# W1 称号目录：太虚魁首（source = arena_week1）
# ═══════════════════════════════════════════════════════════════════════
W1_ANCHOR = "db.run(\"INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES ('义结金兰', '{\\\"charmRate\\\":0.01}', 'sworn')\");"
W1_ADD = zh("db.run(\"INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES "
            "('太虚魁首', '{\\\"stoneRate\\\":0.05}', 'arena_week1')\"); "
            "// [arenaweek] T16 周榜第 1 名称号")
W1_NEW = W1_ANCHOR + "\n" + W1_ADD

# ═══════════════════════════════════════════════════════════════════════
# W2 周榜结算全套（插在「擂台」段之前）
# ═══════════════════════════════════════════════════════════════════════
W2_ANCHOR = "// ── 擂台 ──"
W2_BODY = zh(r"""
// ── T16 演武场周榜结算（0.8.10 [arenaweek]）────────────────────────────
// 依据 docs/0.8.8-design/T16-演武场.md §3.3「新增 C · 周榜」/ §5.5「周榜奖励」。
//   时点：每周一 00:00（北京）对**刚结束的一周**结算一次；幂等键 activity_config
//         `arena_week_settled:<周一日期>`（与活动结算同款标记，重跑零新增）。
//   排名：arena_scores.points（**不清零**，滚动累计 —— §3.3 取舍点 E）。
//   奖励（邮件发放；倍率一律 realmMultOf，与全仓灵石奖励同源）：
//     第 1 名   floor(20000×M) 灵石 + 称号「太虚魁首」
//     第 2~3 名 floor(12000×M) 灵石
//     第 4~10 名 floor(6000×M) 灵石
//     参与奖（本周论剑 ≥10 场）floor(2000×M) 灵石
//   ★ 护栏：名次奖要求「本周至少打 1 场」，否则积分不清零会让停玩的高分号每周白拿奖。
//   ⚠️ 边界：只补结算「最近一个已结束的周」；停机跨多个周一时不追溯更早的周。
const ARENA_WEEK_PARTICIPATE = 10;
const ARENA_WEEK_TOP = 10;
const ARENA_WEEK_MARK = 'arena_week_settled:';

// 周键（北京周一 YYYY-MM-DD）→ 该周起点 ms（北京周一 0 点）
function arenaWeekStartMs(week: string): number {
  return Date.parse(week + 'T00:00:00.000Z') - 8 * 3600 * 1000;
}
// 某周论剑场次 = 已结算战书（status='accepted'）+ 快照挑战
async function arenaWeekMatches(userId: number, week: string): Promise<number> {
  const s = arenaWeekStartMs(week), e = s + 7 * 86400000;
  const [b, k] = await Promise.all([
    dbGet("SELECT COUNT(*) AS c FROM arena_battles WHERE status = 'accepted' AND (challenger_id = ? OR defender_id = ?) AND resolved_at >= ? AND resolved_at < ?",
      [userId, userId, s, e]).catch(() => null),
    dbGet('SELECT COUNT(*) AS c FROM arena_snapshots WHERE challenger_id = ? AND created_at >= ? AND created_at < ?',
      [userId, s, e]).catch(() => null),
  ]);
  return (Number(b && b.c) || 0) + (Number(k && k.c) || 0);
}
// 名次 → 灵石基数（0 = 不发名次奖）
function arenaWeekRewardBase(rank: number): number {
  if (rank === 1) return 20000;
  if (rank <= 3) return 12000;
  if (rank <= ARENA_WEEK_TOP) return 6000;
  return 0;
}
// 结算「刚结束的一周」。异常自吞不阻塞调用方；幂等（标记在发完之后写）。
let arenaWeekSettling = false;
async function arenaWeekSettle(): Promise<void> {
  if (arenaWeekSettling) return;
  arenaWeekSettling = true;
  try {
    const nowMs = Date.now();
    const curStart = arenaWeekStartMs(bjWeekStart(nowMs));   // 本周一（北京）0 点
    if (nowMs < curStart) return;
    const week = bjWeekStart(curStart - 86400000);           // 刚结束那周的周一
    const done = await dbGet('SELECT value FROM activity_config WHERE key = ?', [ARENA_WEEK_MARK + week]).catch(() => null);
    if (done) return;
    const rows = await dbAll('SELECT user_id FROM arena_scores WHERE points > 0 ORDER BY points DESC, user_id ASC', []).catch(() => []);
    let sent = 0;
    for (let i = 0; i < (rows || []).length; i++) {
      const uid = Number(rows[i].user_id);
      if (!Number.isFinite(uid)) continue;
      const rank = i + 1;
      const mult = await realmMultOf(uid).catch(() => 1);
      const m = await arenaWeekMatches(uid, week);
      const base = arenaWeekRewardBase(rank);
      if (base > 0 && m >= 1) {                              // 护栏：本周至少打 1 场（改 true 即严格照策划案）
        const reward = Math.floor(base * mult);
        if (reward > 0) {
          const champ = rank === 1;
          await insertMail(uid, champ ? '演武场·周榜魁首' : '演武场·周榜结算',
            champ ? `你在 ${week} 这一周的演武场积分高居第 1 名，获封「太虚魁首」，附灵石 ×${reward}。`
                  : `你在 ${week} 这一周的演武场积分排名第 ${rank} 名，奖励灵石 ×${reward}。`,
            'system', reward).catch(() => null);
          if (champ) await grantTitleBySource(uid, 'arena_week1').catch(() => false);
          sent++;
        }
      }
      if (m >= ARENA_WEEK_PARTICIPATE) {
        const pr = Math.floor(2000 * mult);
        if (pr > 0) {
          await insertMail(uid, '演武场·参与奖', `你本周论剑 ${m} 场，达成参与奖，奖励灵石 ×${pr}。`, 'system', pr).catch(() => null);
          sent++;
        }
      }
    }
    await dbRun("INSERT OR IGNORE INTO activity_config (key, value) VALUES (?, '1')", [ARENA_WEEK_MARK + week]).catch(() => null);
    if (sent > 0) logChronicle(null, '天机阁', `【演武场】${week} 周榜已结算，奖励随邮件送达。`);
  } catch (e: any) {
    console.error('arena week settle error:', e?.message || e);
  } finally {
    arenaWeekSettling = false;
  }
}
""").strip("\n")
W2_NEW = W2_BODY + "\n" + W2_ANCHOR

# ═══════════════════════════════════════════════════════════════════════
# W3 周榜读取端点（插在恩怨端点注释之前）
# ═══════════════════════════════════════════════════════════════════════
W3_ANCHOR = "// POST /api/arena/grudge {targetId} — 恩怨复仇（客户端「恩怨」分栏的「复仇」按钮）。"
W3_BODY = zh(r"""
// GET /api/arena/week — 演武场周榜（客户端「论剑」分栏展示用；T16 §3.3 新增 C）。
//   board：前 50 名（按 points 降序）；me：我的名次/积分/段位/本周场次；lastSettleWeek：最近已结算周。
app.get('/api/arena/week', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `ar:wk:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const week = bjWeekStart(Date.now());
    const rows = await dbAll(`SELECT s.user_id AS uid, s.points AS points,
        COALESCE(NULLIF(r.name, ''), u.username) AS name, r.combat_power AS cp
      FROM arena_scores s JOIN users u ON u.id = s.user_id
      LEFT JOIN rankings r ON r.user_id = s.user_id
      WHERE s.points > 0 ORDER BY s.points DESC, s.user_id ASC LIMIT 50`, []).catch(() => []);
    const board = (rows || []).map((x: any, i: number) => {
      const p = Number(x.points) || 0;
      return { rank: i + 1, name: String(x.name || ''), points: p,
               tierName: ARENA_TIER_NAMES[arenaTierIdx(p)], combatPower: Number(x.cp) || 0 };
    });
    const mine = await arenaScoreOf(userId);
    const ahead = await dbGet('SELECT COUNT(*) AS c FROM arena_scores WHERE points > ?', [mine.points]).catch(() => null);
    const myRank = mine.points > 0 ? (Number(ahead && ahead.c) || 0) + 1 : null;
    const matches = await arenaWeekMatches(userId, week);
    const lastMark = await dbGet("SELECT key FROM activity_config WHERE key LIKE 'arena_week_settled:%' ORDER BY key DESC LIMIT 1", []).catch(() => null);
    res.json({
      ok: true, week, participateAt: ARENA_WEEK_PARTICIPATE, top: ARENA_WEEK_TOP,
      board,
      me: { rank: myRank, points: mine.points, tierName: ARENA_TIER_NAMES[arenaTierIdx(mine.points)],
            matches, participated: matches >= ARENA_WEEK_PARTICIPATE },
      lastSettleWeek: lastMark ? String(lastMark.key).slice(ARENA_WEEK_MARK.length) : null,
    });
  } catch (e: any) { console.error('arena week error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});
""").strip("\n")
W3_NEW = W3_BODY + "\n" + W3_ANCHOR

# ═══════════════════════════════════════════════════════════════════════
# W4 活动 tick 内挂周榜结算（必须在 actEngineOn 早退之前）
# ═══════════════════════════════════════════════════════════════════════
W4_OLD = ("setInterval(() => {\n"
          "  if (!actEngineOn) return; // engine off: first-line early return, zero DB work\n"
          "  actSettleTick().catch((e: any) => console.error('act tick error:', e?.message || e));\n"
          "}, ACT_TICK_MS).unref();")
W4_NEW = zh("setInterval(() => {\n"
            "  // [arenaweek] 周榜结算与活动引擎无关 ⇒ 必须早于 actEngineOn 早退，否则引擎关闭时永不结算\n"
            "  arenaWeekSettle().catch((e: any) => console.error('arena week tick error:', e?.message || e));\n"
            "  if (!actEngineOn) return; // engine off: first-line early return, zero DB work\n"
            "  actSettleTick().catch((e: any) => console.error('act tick error:', e?.message || e));\n"
            "}, ACT_TICK_MS).unref();")

# ═══════════════════════════════════════════════════════════════════════
# W5 周榜 boot-run（重启跨周一 0 点补结算）
# ═══════════════════════════════════════════════════════════════════════
W5_ANCHOR = "  .catch((e: any) => console.error('act boot settle error:', e?.message || e));"
W5_ADD = zh("// [arenaweek] 周榜结算 boot-run：重启跨过周一 0 点时补结算（幂等；微任务延迟避免 TDZ）\n"
            "Promise.resolve().then(() => arenaWeekSettle()).catch((e: any) => console.error('arena week boot settle error:', e?.message || e));")
W5_NEW = W5_ANCHOR + "\n" + W5_ADD

EDITS = [
    ('W1', W1_ANCHOR, W1_NEW, 1, True),
    ('W2', W2_ANCHOR, W2_NEW, 1, True),
    ('W3', W3_ANCHOR, W3_NEW, 1, True),
    ('W4', W4_OLD,    W4_NEW, 1, False),
    ('W5', W5_ANCHOR, W5_NEW, 1, True),
]


def _base_counts(src: str) -> dict:
    return {
        'n403': src.count('res.status(403)'),
        'require': src.count('require('),
        'mark': src.count(MARK),
        'dbrun': src.count('db.run('),
    }


def _gates(text: str, base: dict, delta: int, gate) -> None:
    # ── 标记与结构 ──（W1/W2/W4/W5 各 1 处注释锚 = 4）
    gate('W0 环标记恰 4 处', text.count(MARK) == 4, '实际 %d' % text.count(MARK))
    # ── 新增函数恰 1 处 ──
    for nm, needle in (('arenaWeekStartMs', 'function arenaWeekStartMs('),
                       ('arenaWeekMatches', 'function arenaWeekMatches('),
                       ('arenaWeekRewardBase', 'function arenaWeekRewardBase('),
                       ('arenaWeekSettle', 'function arenaWeekSettle(')):
        gate('W2 %s 定义恰 1' % nm, text.count(needle) == 1, '实际 %d' % text.count(needle))
    # ── 常量 ──
    gate('W2 参与门槛 10', text.count('const ARENA_WEEK_PARTICIPATE = 10;') == 1)
    gate('W2 名次上限 10', text.count('const ARENA_WEEK_TOP = 10;') == 1)
    gate('W2 幂等键前缀', text.count(zh("'arena_week_settled:'")) == 1)
    # ── 奖励基数（逐档） ──
    gate('W2 第1名基数 20000', text.count('if (rank === 1) return 20000;') == 1)
    gate('W2 第2~3名基数 12000', text.count('if (rank <= 3) return 12000;') == 1)
    gate('W2 第4~10名基数 6000', text.count('if (rank <= ARENA_WEEK_TOP) return 6000;') == 1)
    gate('W2 参与奖基数 2000', text.count('Math.floor(2000 * mult)') == 1)
    # ── 护栏在位 ──
    gate('W2 名次奖护栏（本周 >=1 场）在位', text.count('if (base > 0 && m >= 1) {') == 1)
    # ── 称号 ──
    gate('W1 称号目录 source=arena_week1', text.count("'arena_week1'") == 2, '目录 1 + 授予 1')
    gate('W1 称号名（转义形态）', text.count(zh("'太虚魁首'")) == 1)
    gate('W1 称号授予调用', text.count("grantTitleBySource(uid, 'arena_week1')") == 1)
    # ── 端点 ──
    gate("W3 端点 GET /api/arena/week", text.count("app.get('/api/arena/week', authenticateToken") == 1)
    gate('W3 返回 board/me/lastSettleWeek', text.count('lastSettleWeek: lastMark') == 1)
    # ── 挂点 ──
    gate('W4 tick 挂点恰 1', text.count("console.error('arena week tick error:'") == 1)
    gate('W4 挂点在 actEngineOn 早退之前', _before_tick_guard(text))
    gate('W5 boot-run 恰 1', text.count("console.error('arena week boot settle error:'") == 1)
    # ── 依赖函数被真正调用 ──
    gate('调用 realmMultOf（同源倍率）', text.count('realmMultOf(uid)') == 1)
    gate('调用 bjWeekStart', text.count('bjWeekStart(') >= 6, '基线 3 + 本环 3')
    gate('调用 insertMail（名次奖）', text.count('insertMail(uid, champ ?') == 1, '实际 %d' % text.count('insertMail(uid, champ ?'))
    gate('调用 insertMail（参与奖）', text.count(zh("insertMail(uid, '演武场·参与奖'")) == 1, '实际 %d' % text.count(zh("insertMail(uid, '演武场·参与奖'")))
    gate('调用 logChronicle（转义形态，本环恰 1）',
         text.count(zh("logChronicle(null, '天机阁'")) == 1, '实际 %d' % text.count(zh("logChronicle(null, '天机阁'")))
    # ── 纪律红线 ──
    gate('无新增 res.status(403)', text.count('res.status(403)') == base['n403'], '基线 %d' % base['n403'])
    gate('无 require(', text.count('require(') == base['require'], '基线 %d' % base['require'])
    gate('db.run( 仅新增 1 处（幂等标记）',
         text.count('db.run(') == base['dbrun'] + 1, '基线 %d → 期望 %d，实际 %d' % (base['dbrun'], base['dbrun'] + 1, text.count('db.run(')))
    # ── 交付量 ──
    gate('delta 落在合理区间', 6000 <= delta <= 20000, 'delta %+d' % delta)


def _before_tick_guard(text: str) -> bool:
    """W4：在**活动 tick 那个 setInterval 块内**，`arenaWeekSettle()` 必须早于 `actEngineOn` 早退。

    ★ 不能全文 find —— `actSettleTick` 自身首行也有同一句早退注释（基线 2 处），
      全文 find 会命中更早的那处，导致假 FAIL。
    """
    i_end = text.find('}, ACT_TICK_MS).unref();')
    if i_end < 0:
        return False
    i_start = text.rfind('setInterval(() => {', 0, i_end)
    if i_start < 0:
        return False
    seg = text[i_start:i_end]
    i_arena = seg.find('arenaWeekSettle().catch(')
    i_guard = seg.find('if (!actEngineOn) return;')
    return i_arena >= 0 and i_guard >= 0 and i_arena < i_guard


def _apply_all(text: str) -> str:
    for tag, old, new, expect, insertion in EDITS:
        if insertion:
            _assert_anchor_kept(tag, old, new)
        text = apply_one(text, tag, old, new, expect)
    return text


def _run(src: str, base: dict, label: str) -> int:
    gates = []
    ok = True

    def gate(name, cond, detail=''):
        nonlocal ok
        gates.append((name, bool(cond), detail))
        if not cond:
            ok = False

    before = len(src.encode('utf-8'))
    print('  %s bytes=%d md5=%s' % (label, before, md5s(src)))

    if MARK in src:
        print('  [SKIP] 已含 %s 标记，无需重复打补丁' % MARK)
        return 0

    for tag, old, new, expect, insertion in EDITS:
        if src.count(old) != expect:
            print('  [FAIL] 前置守卫 %s 锚点命中 %d 次（期望 %d）' % (tag, src.count(old), expect))
            return 1
    print('  [OK]   前置守卫：%d 处锚点命中数全部符合期望' % len(EDITS))

    text = _apply_all(src)
    delta = len(text.encode('utf-8')) - before
    _gates(text, base, delta, gate)

    print('\n  --- 门禁 ---')
    for name, c, detail in gates:
        print('  [%s] %s%s' % ('OK' if c else 'FAIL', name, ('  ' + detail) if detail else ''))
    print('\n  自证结果：%s（delta %+d B）' % ('全 PASS' if ok else '存在 FAIL', delta))
    return 0 if ok else 1


def selftest() -> int:
    print('0.8.10 演武场周榜结算环（链第 22 环）— 自证')
    cand = None
    for p in (os.path.join(HERE, '_chainstage', 's21.v2810.ts'),):
        if os.path.isfile(p):
            cand = p
            break
    if not cand:
        print('  [SKIP] 找不到 s21.v2810.ts（先跑 chain_build.py --srv）')
        return 0
    src = open(cand, encoding='utf-8').read()
    print('  输入 : %s' % cand)
    return _run(src, _base_counts(src), 's21.v2810.ts')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--src')
    ap.add_argument('--out')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    if not a.src:
        die('必须给 --src（或 --selftest）')

    src = os.path.abspath(a.src)
    if not os.path.isfile(src):
        die('src 不存在: %s' % src)
    out = os.path.abspath(a.out) if a.out else src
    if out != src and not os.path.isdir(os.path.dirname(out)):
        die('out 目录不存在: %s' % os.path.dirname(out))

    text = open(src, encoding='utf-8').read()
    before_bytes = len(text.encode('utf-8'))
    print('0.8.10 演武场周榜结算环（链第 22 环 / 新末环）')
    print('  source : %s  bytes=%d md5=%s' % (src, before_bytes, md5s(text)))

    if MARK in text:
        print('  [SKIP] 已包含 %s 标记，无需重复打补丁' % MARK)
        return 0

    for tag, old, new, expect, insertion in EDITS:
        if text.count(old) != expect:
            die('前置守卫失败：%s 锚点命中 %d 次（期望 %d）—— 基线不符' % (tag, text.count(old), expect))
    print('  [OK]   前置守卫：%d 处锚点命中数全部符合期望' % len(EDITS))

    base = _base_counts(text)
    text = _apply_all(text)
    delta = len(text.encode('utf-8')) - before_bytes
    gates = []

    def gate(name, cond, detail=''):
        gates.append((name, bool(cond), detail))

    _gates(text, base, delta, gate)

    bad = [g for g in gates if not g[1]]
    print('\n  --- 门禁 ---')
    for name, c, detail in gates:
        print('  [%s] %s%s' % ('OK' if c else 'FAIL', name, ('  ' + detail) if detail else ''))
    if bad:
        print('\n[ABORT] 门禁未全过（%d 条 FAIL），不写出' % len(bad))
        return 1

    if out != src:
        open(out, 'wb').write(text.encode('utf-8'))
        print('\n  [写出] %s  bytes=%d  md5=%s' % (out, len(text.encode('utf-8')), md5s(text)))
    else:
        bak = '%s.bak-arenaweek-%s' % (src, time.strftime('%Y%m%d-%H%M%S'))
        shutil.copy2(src, bak)
        print('\n  [备份] %s' % bak)
        open(src, 'wb').write(text.encode('utf-8'))
        print('  [写出] %s  bytes=%d  md5=%s' % (src, len(text.encode('utf-8')), md5s(text)))

    print('  [PASS] 演武场周榜结算环落地（delta %+d B）' % delta)
    return 0


if __name__ == '__main__':
    sys.exit(main())
