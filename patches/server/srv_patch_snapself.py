# -*- coding: utf-8 -*-
r"""srv_patch_snapself.py — 0.8.10 玩家侧存档快照「时光回溯」环（链第 23 环 / 新末环）

只做一件事：把已经落库、却**只有 GM 能看**的 `save_snapshots` 开放给玩家**自助回溯**，
用于误操作 / 误覆盖救援。

## 现状（为什么是缺口）

`save_snapshots` 表与 `snapshotOldSave()` 自 S4 v26c 就在跑：玩家**每次写档**都会节流
（≥10min 一条、每号最多留 50 条）落一条旧档快照，本意就是「误覆盖 / 防倒滚误伤救援」。
但读侧此前**只有 GM 端点**：
  · `GET  /api/gm/players/:id/snapshots`（BASECLEAN089 ③-a，元数据列表）
  · `POST /api/gm/players/:id/snapshots/:sid/restore`（③-b，回档）
⇒ 玩家自己误操作把档搞坏了，只能去求 GM。本环补上玩家自助面。

## 本环改动（1 处插入，锚区与前 22 环零交集）

| # | 锚点 | 改动 |
|---:|---|---|
| S1 | `// BASECLEAN089 ③-a：…` 注释行之前 | 新增玩家侧两个端点 + 额度三件套（见下） |

**无 DDL、无 ALTER、无 PRAGMA、无新表**：额度计数复用既有 KV 表 `activity_config`。

## 契约

```
GET  /api/snapshots
  200 { ok, week, quota:{weekly,used,left}, count, snapshots:[{ id, created_at,
        gm_revision, save_bytes, age_ms, summary:{realm,realmLevel,stones,combatPower}|null }] }

POST /api/snapshots/:id/restore
  200 { ok, restored_snapshot_id, gm_revision, quota:{weekly,used,left} }
  400 快照编号非法 / 快照内容非法
  404 快照不存在或不属于你 / 尚无存档
  409 本周额度用尽（code=SNAP_QUOTA_EXHAUSTED）
  429 频率限制（rateLimit）
```

## ★ 为什么必须限额（本环最重要的取舍）

本作绝大多数玩法（抽奖 / 灵田 / 丹炉 / 试炼 / 奇遇）**在客户端结算、只把结果写进存档**。
「回溯」在语义上等于「**无成本撤销一次结果**」⇒ 不限额就是无限刷概率（抽到坏结果就回溯重抽）。
因此本环加**每周 1 次**的额度（北京周一口径，与周榜 / 周里程碑同源 `bjWeekStart`）。
放宽只需改 `SNAP_SELF_WEEKLY` 一个常量。

## 安全设计（与 GM 侧逐条同口径）

1. **归属校验打在 `id + user_id`**：`save_snapshots.id` 全表自增，只按 id 查会拿到别人号的快照
   （跨号越权）——与 ③-b 同款写法。
2. **回溯前强制落一条当前档快照**（`snapshotOldSave(..., force=true)`）⇒ 回溯**本身可逆**，
   玩家点错了还能再回溯回来（`force` 参数由第 21 环 `srv_patch_v2810.py` ⑤ 引入，本环直接用）。
3. **写回走 `updatePlayerSave`**：持 `saveLock` 串行化 + `gm_revision++` + 排行同步 + 经济镜像，
   与 GM 改档同一条汇聚路径（不自己写 UPDATE）。
4. **占额是原子的**：`UPDATE … WHERE key = ? AND CAST(value AS INTEGER) < ?` 单语句条件自增，
   并发下不会超发；**回溯失败则退还**（`finally` 里 `snapSelfRelease`），不白扣玩家次数。
5. **绝不回存档正文**：列表只回 4 个标量摘要（服务端解析后提取），整档 JSON（数十~数百 KB）不出网。

## ★ 客户端配套（不是本环的事，但必须同时上线）

客户端 `applyRemoteSave`（每 6s 轮询 `gm_revision` 变大便采纳远端档）里有**灵石仲裁**
`YLArbDecide`：当「本地灵石 > 远端灵石」且「本地 > 服务端已确认值」时，会判 `flush`
（把本地档推上去）或 `skip`（不采纳）—— 其前提假设是「远端值来自推档应答 / GM 钳制」。
**回溯会让数值整体变小**，恰好踩中该假设 ⇒ 可能把回溯结果冲掉。
故客户端侧 `yl_v2810h_ext.py` 在回溯成功后置一次性放行开关，让下一次 `applyRemoteSave`
跳过仲裁直接采纳。服务端只需保证 `gm_revision` 递增（`updatePlayerSave` 天然满足）。

## 工程约束（本项目已踩过的坑，本环逐条遵守）

1. **回调式 sqlite3** ⇒ 一律 `dbGet / dbAll / dbRun`；`db.run(...).catch(...)` 禁止
   （门禁断言 `db.run(` 计数**零新增**）。
2. **ESM** ⇒ `require(` 禁止（门禁断言计数不增加）。
3. **不新增表 / 不新增列** ⇒ 无 `CREATE`/`ALTER`/`PRAGMA`（坑 12 无关）。
4. **注入块里的中文一律 `zh()` 转义**；门禁 needle 落在注入块内时同样用 `zh()`（坑 2）。
5. **不新增 `res.status(403)`**（`check_srv_087.py` 有 403 计数门禁；业务拒绝用 400/404/409）。
6. **锚点带 `expect=1` 前置守卫 + 自毁防线**（插入式改动 new 必须含锚点原文）。
7. ⛔ 不改 `srv/index_v28.ts`（链产物）；⛔ 不改前 22 环补丁；⛔ 不改基座指纹。

## 用法

```
python srv_patch_snapself.py --src <上一环产物>    # 就地原子写回 --src
python srv_patch_snapself.py --selftest            # 只跑门禁，不碰文件
```

幂等：已含 `[snapself]` 标记则 SKIP。锚点不唯一一律中止（拒绝静默失败）。
"""

import argparse
import hashlib
import os
import shutil
import sys
import time

MARK = '[snapself]'
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
# S1 玩家侧快照端点（插在 GM 快照元数据端点之前）
# ═══════════════════════════════════════════════════════════════════════
S1_ANCHOR = "// BASECLEAN089 \u2462-a\uff1aGM \u5feb\u7167**\u5143\u6570\u636e**\u5217\u8868\uff08\u6551\u63f4\u5feb\u7167\u8bfb\u4fa7\uff09\u3002"

S1_BODY = zh(r"""
// ── 玩家侧存档快照 · 时光回溯（0.8.10 [snapself]）────────────────────────
// 把 `save_snapshots`（写档时自动落、每号最多 50 条）开放给玩家**自助回溯**，用于误操作救援。
// 快照**全部由服务端自动产生**，玩家不能手工造快照。
//
// 额度：每周 SNAP_SELF_WEEKLY 次（北京周一口径），计数键 activity_config
//       `snap_self_used:<周一>:<uid>`。**必须限额**：本作绝大多数玩法（抽奖 / 灵田 / 丹炉 /
//       试炼 / 奇遇）在客户端结算、只把结果写进存档 ⇒「回溯」= 无成本撤销一次结果。
//
// 安全：① 归属校验打在 id + user_id（防跨号越权）；
//       ② 回溯前 force 落一条当前档快照 ⇒ 回溯可逆（与 GM 侧 ③-b 同款）；
//       ③ 写回走 updatePlayerSave（saveLock + gm_revision++ + 排行同步 + 经济镜像）；
//       ④ 列表只回标量摘要，整档 JSON 不出网。
const SNAP_SELF_WEEKLY = 1;
const SNAP_SELF_MARK = 'snap_self_used:';
const SNAP_SELF_LIST_MAX = 20;

// 本周额度（week = 北京周一，与周榜 / 周里程碑同源）
async function snapSelfQuota(userId: number) {
  const week = bjWeekStart(Date.now());
  const key = SNAP_SELF_MARK + week + ':' + userId;
  const row: any = await dbGet('SELECT value FROM activity_config WHERE key = ?', [key]).catch(() => null);
  const used = Math.max(0, Number(row && row.value) || 0);
  return { week, key, used, left: Math.max(0, SNAP_SELF_WEEKLY - used) };
}
// 原子占额：仅当「已用 < 额度」时 +1；changes === 1 才是占额成功（并发不超发）
async function snapSelfReserve(key: string): Promise<boolean> {
  await dbRun("INSERT OR IGNORE INTO activity_config (key, value) VALUES (?, '0')", [key]).catch(() => null);
  const r: any = await dbRun(
    'UPDATE activity_config SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT) WHERE key = ? AND CAST(value AS INTEGER) < ?',
    [key, SNAP_SELF_WEEKLY]
  ).catch(() => null);
  return !!(r && Number(r.changes) === 1);
}
// 退还占额（回溯失败时调用，不白扣玩家次数）
async function snapSelfRelease(key: string) {
  await dbRun('UPDATE activity_config SET value = CAST(MAX(0, CAST(value AS INTEGER) - 1) AS TEXT) WHERE key = ?', [key]).catch(() => null);
}

// GET /api/snapshots — 本人快照列表（元数据 + 标量摘要，**绝不回存档正文**）+ 本周额度。
//   摘要由服务端解析后只回 4 个标量（境界 / 层数 / 灵石 / 战力），供玩家判断该回哪一版。
app.get('/api/snapshots', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 30, keyFn: (req: any) => `snap:ls:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const q = await snapSelfQuota(userId);
    const rows: any[] = await dbAll(
      'SELECT id, gm_revision, created_at, LENGTH(save_data) AS save_bytes, save_data FROM save_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT ?',
      [userId, SNAP_SELF_LIST_MAX]
    ).catch(() => []);
    const nowMs = Date.now();
    const snapshots = (rows || []).map((r: any) => {
      let summary: any = null;
      try {
        const k = extractRankingData(JSON.parse(String(r.save_data)));
        if (k) summary = {
          realm: REALM_ORDER_FOR_RANKING[k.realm_index] || '',
          realmLevel: k.realm_level,
          stones: k.spirit_stones,
          combatPower: k.combat_power,
        };
      } catch (e) { /* 单条解析失败不影响整表 */ }
      const t = Date.parse(String(r.created_at || '').replace(' ', 'T') + 'Z');
      return {
        id: Number(r.id),
        created_at: r.created_at ?? null,
        gm_revision: Number(r.gm_revision) || 0,
        save_bytes: Number(r.save_bytes) || 0,
        age_ms: Number.isFinite(t) ? Math.max(0, nowMs - t) : null,
        summary,
      };
    });
    res.json({
      ok: true,
      week: q.week,
      quota: { weekly: SNAP_SELF_WEEKLY, used: q.used, left: q.left },
      count: snapshots.length,
      snapshots,
    });
  } catch (e: any) {
    console.error('snapshots list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/snapshots/:id/restore — 自助回溯（每周限额；回溯前强制落一条，保证可逆）。
app.post('/api/snapshots/:id/restore', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => `snap:rs:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  const sid = asInt(req.params.id);
  if (!Number.isFinite(sid) || sid <= 0) return res.status(400).json({ error: '快照编号非法' });
  let reservedKey = '';
  try {
    // 归属校验打在 id + user_id 上（快照 id 全表自增，只按 id 查会跨号越权）
    const snap: any = await dbGet('SELECT id, save_data, gm_revision FROM save_snapshots WHERE id = ? AND user_id = ?', [sid, userId]).catch(() => null);
    if (!snap) return res.status(404).json({ error: '快照不存在或不属于你' });
    let restored: any;
    try { restored = JSON.parse(String(snap.save_data)); } catch (e) { return res.status(500).json({ error: '快照解析失败' }); }
    if (!restored || typeof restored !== 'object' || Array.isArray(restored)) return res.status(400).json({ error: '快照内容非法' });

    // 先占额（原子条件自增）；占不到即拒绝
    const q = await snapSelfQuota(userId);
    const ok = await snapSelfReserve(q.key);
    if (!ok) {
      return res.status(409).json({ error: '本周回溯次数已用尽，下周刷新后再试', code: 'SNAP_QUOTA_EXHAUSTED', weekly: SNAP_SELF_WEEKLY, used: q.used });
    }
    reservedKey = q.key;   // 占额成功；以下任何失败路径都退还

    const cur: any = await dbGet('SELECT save_data, gm_revision FROM saves WHERE user_id = ?', [userId]).catch(() => null);
    if (!cur) return res.status(404).json({ error: '尚无存档，无法回溯' });
    // 回溯前把「当前档」再落一条（force 绕过 10min 节流）⇒ 回溯本身可逆
    snapshotOldSave(userId, String(cur.save_data), Number(cur.gm_revision) || 0, true);

    const r = await updatePlayerSave(userId, (saveData: any) => {
      Object.keys(saveData).forEach((k) => { delete saveData[k]; });
      Object.assign(saveData, restored);
    });
    if (!r.ok) return res.status(400).json({ error: r.error || '回溯失败' });
    reservedKey = '';      // 写回成功 ⇒ 额度已真正消费，不再退还

    const after: any = await dbGet('SELECT gm_revision FROM saves WHERE user_id = ?', [userId]).catch(() => null);
    const gm_revision = Number(after && after.gm_revision) || 0;
    const nowQ = await snapSelfQuota(userId);
    logChronicle(userId, String(req.user?.username || ''), '【逆天改命】回溯自身因果，时光倒转，重回旧日仙途');
    logGmAction('player_restore_snapshot', `user:${userId}`, { snapshot_id: sid, snapshot_gm_revision: Number(snap.gm_revision) || 0, gm_revision, week: q.week });
    res.json({ ok: true, restored_snapshot_id: sid, gm_revision, quota: { weekly: SNAP_SELF_WEEKLY, used: nowQ.used, left: nowQ.left } });
  } catch (e: any) {
    console.error('snapshot restore error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  } finally {
    if (reservedKey) await snapSelfRelease(reservedKey).catch(() => null);   // 失败路径退还额度
  }
});
""").strip("\n")

S1_NEW = S1_BODY + "\n" + S1_ANCHOR

EDITS = [
    ('S1', S1_ANCHOR, S1_NEW, 1, True),
]


def _base_counts(src: str) -> dict:
    return {
        'n403': src.count('res.status(403)'),
        'require': src.count('require('),
        'mark': src.count(MARK),
        'dbrun': src.count('db.run('),
    }


def _gates(text: str, base: dict, delta: int, gate) -> None:
    # ── 标记 ──
    gate('S0 环标记恰 1 处', text.count(MARK) == 1, '实际 %d' % text.count(MARK))
    # ── 常量 ──
    gate('S1 周额度常量', text.count('const SNAP_SELF_WEEKLY = 1;') == 1)
    gate('S1 幂等键前缀', text.count(zh("'snap_self_used:'")) == 1)
    gate('S1 列表上限常量', text.count('const SNAP_SELF_LIST_MAX = 20;') == 1)
    # ── 三个 helper 各恰 1 处定义 ──
    for nm, needle in (('snapSelfQuota', 'async function snapSelfQuota('),
                       ('snapSelfReserve', 'async function snapSelfReserve('),
                       ('snapSelfRelease', 'async function snapSelfRelease(')):
        gate('S1 %s 定义恰 1' % nm, text.count(needle) == 1, '实际 %d' % text.count(needle))
    # ── 端点 ──
    gate('S1 端点 GET /api/snapshots', text.count("app.get('/api/snapshots', authenticateToken") == 1)
    gate('S1 端点 POST /api/snapshots/:id/restore',
         text.count("app.post('/api/snapshots/:id/restore', authenticateToken") == 1)
    # ── 归属校验（防跨号越权）──
    gate('S1 归属校验 id + user_id',
         text.count('FROM save_snapshots WHERE id = ? AND user_id = ?') == 2, 'GM 侧 1 + 本环 1')
    # ── 可逆性：回溯前强制快照 ──
    gate('S1 回溯前强制快照 force=true',
         text.count('snapshotOldSave(userId, String(cur.save_data), Number(cur.gm_revision) || 0, true);') == 2,
         'GM 侧 1 + 本环 1')
    # ── 额度原子占额 / 退还 ──
    gate('S1 占额是原子条件自增',
         text.count('WHERE key = ? AND CAST(value AS INTEGER) < ?') == 1)
    gate('S1 changes===1 才算占额成功', text.count('Number(r.changes) === 1') == 1)
    gate('S1 失败路径退还额度', text.count('if (reservedKey) await snapSelfRelease(reservedKey)') == 1)
    gate('S1 额度用尽回 409', text.count(zh("code: 'SNAP_QUOTA_EXHAUSTED'")) == 1)
    # ── 摘要只回标量（整档不出网）──
    gate('S1 摘要复用 extractRankingData', text.count('extractRankingData(JSON.parse(String(r.save_data)))') == 1)
    gate('S1 列表含 save_bytes 不回正文', text.count('LENGTH(save_data) AS save_bytes, save_data FROM save_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT ?') == 1)
    # ── 依赖函数被真正调用 ──
    gate('S1 调用 bjWeekStart（同源周键）', text.count('bjWeekStart(Date.now())') >= 2, '基线 1 + 本环 1')
    gate('S1 调用 updatePlayerSave',
         text.count('const r = await updatePlayerSave(userId, (saveData: any) => {') == 2, 'GM 侧 1 + 本环 1')
    gate('S1 调用 logChronicle（转义形态）', text.count(zh("logChronicle(userId, String(req.user?.username || ''),")) == 1)
    gate('S1 调用 logGmAction（审计）', text.count("logGmAction('player_restore_snapshot'") == 1)
    gate('S1 调用 rateLimit（两端点）', text.count('keyFn: (req: any) => `snap:') == 2)
    # ── 纪律红线 ──
    gate('S1 无新增 res.status(403)', text.count('res.status(403)') == base['n403'], '基线 %d' % base['n403'])
    gate('S1 无 require(', text.count('require(') == base['require'], '基线 %d' % base['require'])
    gate('S1 db.run( 零新增（只用 dbRun/dbGet/dbAll）',
         text.count('db.run(') == base['dbrun'], '基线 %d，实际 %d' % (base['dbrun'], text.count('db.run(')))
    gate('S1 无新增建表 / 加列',
         text.count('CREATE TABLE IF NOT EXISTS save_snapshots') == 1 and text.count('ALTER TABLE save_snapshots') == 0)
    # ── 交付量 ──
    gate('S1 delta 落在合理区间', 4000 <= delta <= 16000, 'delta %+d' % delta)


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
    print('0.8.10 玩家侧快照「时光回溯」环（链第 23 环）— 自证')
    cand = None
    for p in (os.path.join(HERE, '_chainstage', 's22.arenaweek.ts'),):
        if os.path.isfile(p):
            cand = p
            break
    if not cand:
        print('  [SKIP] 找不到 s22.arenaweek.ts（先跑 chain_build.py --srv）')
        return 0
    src = open(cand, encoding='utf-8').read()
    print('  输入 : %s' % cand)
    return _run(src, _base_counts(src), 's22.arenaweek.ts')


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
    print('0.8.10 玩家侧快照「时光回溯」环（链第 23 环 / 新末环）')
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
        bak = '%s.bak-snapself-%s' % (src, time.strftime('%Y%m%d-%H%M%S'))
        shutil.copy2(src, bak)
        print('\n  [备份] %s' % bak)
        open(src, 'wb').write(text.encode('utf-8'))
        print('  [写出] %s  bytes=%d  md5=%s' % (src, len(text.encode('utf-8')), md5s(text)))

    print('  [PASS] 玩家侧快照「时光回溯」环落地（delta %+d B）' % delta)
    return 0


if __name__ == '__main__':
    sys.exit(main())
