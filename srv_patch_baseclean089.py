# -*- coding: utf-8 -*-
r"""srv_patch_baseclean089.py — 0.8.9 基座清理环（链第 17 环 / 末环）

## 背景（两处线上缺陷，均已实测复现）

### ① `require(` ×2 —— ESM 下未定义，GM 字典静默恒为空

`srv/index_v28.ts` 的 `loadGameDicts()` 内：

```js
const fs = require('fs');      // :2902  ← 冗余：fs 已在文件头 :7 import
const path = require('path');  // :2903  ← 冗余：path 已在文件头 :8 import
```

本项目 `.ts` 以 ESM 加载（`srv/` 下**无 package.json**，且基座 `:17-18` 用
`fileURLToPath(import.meta.url)` 自建 `__dirname`）。**ESM 下 `require` 未定义** ⇒
这两行抛 `ReferenceError: require is not defined` ⇒ 被 `:2912` 的 `catch` **静默吞掉**
⇒ `gameDicts = {}` ⇒ `/api/gm/dicts` **永远返回空字典**。

实测（沙箱 `/tmp/yl_v28_sandbox/s0`，同一份 `game-dicts.json` 存在）：

| 版本 | `loadGameDicts()` 结果 |
|---|---|
| 含 `require`（原样） | **0 个 key**（`{}`） |
| 删 `require`（本环） | **16 个 key**（items/skills/arts/achievements/titles/pets/grotto/talents…） |

异常原文（不吞时）：`ReferenceError: require is not defined`。
⇒ 与 journalctl 实锤 `[GM] loadGameDicts error: require is not defined` 一致。

**修法**：删掉这 2 行，保留 `path.join(__dirname, 'game-dicts.json')`。
`__dirname` **可用**（基座 `:18` 已建），且 `fs`/`path` 均已由文件头 `import` 绑定 ⇒
无需任何替代变量、无需自己造。

### ② `GM_PASSWORD` 弱口令缺省 —— `.env` 丢失会静默退回 `'gamer'`

```js
const GM_PASSWORD = process.env.GM_PASSWORD || 'gamer';   // :1094
```

`'gamer'` 是弱口令。`.env` 丢失（或变量误删）时**静默降级**为可猜口令，
GM 后台（`/api/gm/*`，含发钱/改档/封号）即被弱口令保护 —— 属**静默失效的安全降级**。

**修法**：缺省即硬失败 `process.exit(1)`，不静默降级。

### ③ 救援快照「只写不读」—— 表在写、读侧零端点

`save_snapshots` 表（`:151-160`）与 `snapshotOldSave()`（`:2116-2130`：写前节流快照、
每号留 50 条）**早已存在且一直在写**，但**读侧一个端点都没有** ⇒ 表里的救援快照
谁也看不见、谁也回不去，误覆盖时这张表等于不存在。

**修法**：只补**读侧**两个 GM 端点（写侧 `snapshotOldSave` 一字未动）：

| 端点 | 语义 |
|---|---|
| `GET /api/gm/players/:id/snapshots` | **元数据列表**：`id / created_at / gm_revision / save_data 字节数`。**绝不回全文**（整档 JSON 可达数百 KB；要看某一版全文另走 GM 既有 `GET /api/gm/players/:id/save`） |
| `POST /api/gm/players/:id/snapshots/:sid/restore` | 归属校验（`:sid` 必须属于 `:id`，防跨号越权）→ **回档前自动存一条新快照**（防不可逆）→ `updatePlayerSave` 写回 → `gm_audit_logs` → 回传新 `gm_revision` |

两者**必须带 `authenticateGM`**（门禁 G11 逐块断言，非全文计数）。

## 改动清单（3 处，锚区互不重叠）

| # | 锚点（实测行号） | 改动 |
|---:|---|---|
| C1 | `srv/index_v28.ts:2902-2903`（`loadGameDicts` 内） | 删 2 行冗余 `require` |
| C2 | `srv/index_v28.ts:1094`（`GM_PASSWORD` 定义） | 缺省 → `process.exit(1)` |
| C3 | `srv/index_v28.ts:2450-2461`（GM 存档只读端点之后） | 追加快照列表 + 回档两端点 |

## 与其它环的关系（零交集）

* 本环锚区 = `loadGameDicts`（:2899 附近）/ `GM_PASSWORD` 定义（:1094）/
  `GET /api/gm/players/:id/save` 之后（:2461 附近），
  与 ki001（`settleSaveEconV2`）/ net-2（回显中间件 / grant / 409）/
  t7_legacy（`isValidSavePayload` / 回显辅助）/ t9（`activity_*` 建表）**全无交集**。
* `GM_PASSWORD` 的两个使用点：定义（:1094，本环）+ 比对（`:2315`，
  `if (!password || password !== GM_PASSWORD)`）—— **比对处一字未动**。
  改动后 `GM_PASSWORD` 类型仍为 `string`（`process.env.X` 为 `string | undefined`，
  经 `if (!GM_PASSWORD) process.exit(1)` 收窄后 TS 视为 `string`），
  `!==` 比较语义不变。
* 快照写侧 `snapshotOldSave` / 裁 50 逻辑 **一字未动**（门禁 R6 逐字复核）；
  回档**复用** `updatePlayerSave`（saveLock 互斥 + `gm_revision++` + 排行同步），
  不另造写路径。

## 红线

* 不碰 `build/`（i8-gmdeploy 的前端域）—— 本环只动 `srv/` 侧链的**产物**。
* 不改基座指纹（`_v281_base/` 只读）。
* 不改任何既存门禁期望值。

## 用法

```
python srv_patch_baseclean089.py --src <上一环产物>   # 就地原子写回 --src
python srv_patch_baseclean089.py --selftest           # 只跑门禁，不碰文件
```

幂等：已含 `BASECLEAN089` 标记则 SKIP。锚点不唯一一律中止（拒绝静默失败）。
"""
import argparse
import hashlib
import os
import re
import shutil
import sys
import time

MARK = 'BASECLEAN089'
HERE = os.path.dirname(os.path.abspath(__file__))


def md5s(s: str) -> str:
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def die(msg: str):
    print('[FAIL] ' + msg)
    sys.exit(1)


def apply_one(text: str, tag: str, old: str, new: str, expect: int = 1) -> str:
    n = text.count(old)
    if n != expect:
        die('%s 锚点命中 %d 次（期望 %d）—— 拒绝静默失败' % (tag, n, expect))
    print('  [OK] %-6s 锚点命中 %d 次' % (tag, n))
    return text.replace(old, new, expect)


def _head_block(text: str, anchor: str) -> str:
    """取「锚点所在端点定义」起、到下一个 `app.` 为止的片段。

    用于断言「中间件就挂在端点定义行内」——只扫这一块，避免误捕邻座的 authenticateGM
    （本文件 30+ 个 GM 端点全都带它，全文计数等于没查）。
    """
    i = text.find(anchor)
    if i < 0:
        return ''
    j = text.find('\napp.', i + len(anchor))
    return text[i:] if j < 0 else text[i:j]


def block_ok(text: str, anchor: str) -> bool:
    """锚点在文中恰 1 处，且其端点块内出现 authenticateGM。"""
    return text.count(anchor) == 1 and 'authenticateGM' in _head_block(text, anchor)


# ─────────────────────────────────────────────────────────
# C1 · 删 loadGameDicts 内 2 行冗余 require
#     锚点 = 这两行 + 其后的 path.join 行（保证唯一命中、且确认上下文正确）
# ─────────────────────────────────────────────────────────
C1_OLD = """    const fs = require('fs');
    const path = require('path');
    const file = path.join(__dirname, 'game-dicts.json');"""

C1_NEW = """    // BASECLEAN089: require 在 ESM 下未定义（fs/path 已由文件头 :7/:8 import），
    //   原 2 行会抛 ReferenceError 并被下方 catch 静默吞掉 ⇒ /api/gm/dicts 恒返回 {}。
    //   __dirname 由基座 :18 fileURLToPath(import.meta.url) 自建，可直接用。
    const file = path.join(__dirname, 'game-dicts.json');"""

# ─────────────────────────────────────────────────────────
# C2 · GM_PASSWORD 弱口令缺省 → 启动硬失败
#     锚点 = :1094 那一行（唯一）
# ─────────────────────────────────────────────────────────
C2_OLD = "const GM_PASSWORD = process.env.GM_PASSWORD || 'gamer';"

C2_NEW = """// BASECLEAN089: 原写法带「弱口令兜底」（env 缺失时回落固定口令）—— .env 丢失会静默降级为
//   可猜口令，使 /api/gm/*（发钱/改档/封号）暴露在弱口令下。改为**启动时硬失败**，不静默降级。
const GM_PASSWORD = process.env.GM_PASSWORD;
if (!GM_PASSWORD) {
  console.error('[FATAL] GM_PASSWORD 未设置，拒绝以弱口令启动。请在 .env 配置 GM_PASSWORD 后重启。');
  process.exit(1);
}"""

# ─────────────────────────────────────────────────────────
# C3 · GM 快照端点点亮（读 + 回档）
#
# 背景：`save_snapshots` 表与 `snapshotOldSave()`（:2116-2130，写前节流快照，每号留 50 条）
# 早已存在且**一直在写**，但**读侧零端点** —— 表里的救援快照谁也看不见、谁也回不去。
# 本块只补**读侧**：列表 + 回档；写侧 `snapshotOldSave` **一字未动**（不抢它的节流/裁 50 逻辑）。
#
# 锚点 = `GET /api/gm/players/:id/save`（:2450，GM 侧同参数同语义的**只读**端点）整块，
#   新端点插在其后、`PUT /api/gm/players/:id/save` 之前 —— GM players 家族内部，位置自洽。
#
# 三个关键设计（都是**复用既有权威路径**，不另造一套）：
#   1) **回档前自动存档**（可逆性）：先 `snapshotOldSave(...)` 把「回档那一刻的现状」存成一条新快照，
#      否则回档本身不可撤销（回错了就永远丢了）。节流命中（<10min）会 skip —— 那时表里已有
#      ≤10min 内的更近快照，语义上等价，且这是既有写侧口径，本块不越权改。
#   2) **归属校验打在主键上**：`WHERE id = ? AND user_id = ?` —— 快照 id 是全表自增，
#      只按 id 查就能拿到**别人**的快照（跨号越权）。带 user_id 后「不属于该号」与「不存在」
#      同走 404 分支，既不越权也不泄露 id 存在性。
#   3) **回档走 `updatePlayerSave`**：复用其 saveLock 读改写互斥 / gm_revision++（促客户端拉新档）/
#      排行同步 / 经济镜像，回档后不会被下一次推档盖回去（与 ki001 / net-2 的收口同款）。
#
# 列表**绝不回全文**：`save_data` 是整段存档 JSON（可达数百 KB），列表只回长度（字节数），
#   全量正文另走 GM 既有的 `GET /api/gm/players/:id/save` 取。
C3_OLD = """app.get('/api/gm/players/:id/save', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  db.get('SELECT save_data FROM saves WHERE user_id = ?', [userId], (err: any, row: any) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    if (!row) return res.status(404).json({ error: 'No save found' });
    try {
      res.json(JSON.parse(row.save_data));
    } catch (e) {
      res.status(500).json({ error: 'Parse error' });
    }
  });
});"""

C3_NEW = """app.get('/api/gm/players/:id/save', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  db.get('SELECT save_data FROM saves WHERE user_id = ?', [userId], (err: any, row: any) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    if (!row) return res.status(404).json({ error: 'No save found' });
    try {
      res.json(JSON.parse(row.save_data));
    } catch (e) {
      res.status(500).json({ error: 'Parse error' });
    }
  });
});

// BASECLEAN089 ③-a：GM 快照**元数据**列表（救援快照读侧）。
// 只回 id / created_at / gm_revision / save_data **字节数** —— 绝不回全文（整档 JSON 可达数百 KB，
// 列表若带正文会一次吐几十 MB）。要看某一版全文：拿 id 走下方 restore 的对照，或另取 GM 存档端点。
app.get('/api/gm/players/:id/snapshots', authenticateGM, (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  if (!Number.isFinite(userId)) return res.status(400).json({ error: 'Bad player id' });
  const limit = Math.min(Math.max(asInt(req.query.limit) || 50, 1), 200);
  db.all(
    'SELECT id, gm_revision, created_at, LENGTH(save_data) AS save_bytes FROM save_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT ?',
    [userId, limit],
    (err: any, rows: any[]) => {
      if (err) return res.status(500).json({ error: 'Database error' });
      const list = (rows || []).map((r: any) => ({
        id: Number(r.id),
        created_at: r.created_at ?? null,
        gm_revision: Number(r.gm_revision) || 0,
        save_bytes: Number(r.save_bytes) || 0,
      }));
      res.json({ ok: true, user_id: userId, count: list.length, snapshots: list });
    }
  );
});

// BASECLEAN089 ③-b：GM 回档到指定快照（救援快照写回）。
// 语义顺序（每步都不可省）：归属校验 → 回档前自动存档 → updatePlayerSave 写回 → 审计 → 回传新修订号。
app.post('/api/gm/players/:id/snapshots/:sid/restore', authenticateGM, async (req: any, res: any) => {
  const userId = parseInt(req.params.id);
  const sid = parseInt(req.params.sid);
  if (!Number.isFinite(userId) || !Number.isFinite(sid)) {
    return res.status(400).json({ error: 'Bad player id or snapshot id' });
  }
  // 归属校验打在**主键 + user_id** 上：快照 id 全表自增，只按 id 查会拿到别人号的快照（跨号越权）。
  const snap: any = await dbGet(
    'SELECT id, save_data, gm_revision FROM save_snapshots WHERE id = ? AND user_id = ?',
    [sid, userId]
  ).catch(() => null);
  if (!snap) return res.status(404).json({ error: 'Snapshot not found for this player' });

  let restored: any;
  try {
    restored = JSON.parse(snap.save_data);
  } catch (e) {
    return res.status(500).json({ error: 'Snapshot parse error' });
  }

  // 回档前把「当前档」再存一条（否则回档不可逆；snapshotOldSave 自带 <10min 节流 + 每号留 50 条）
  const cur: any = await dbGet('SELECT save_data, gm_revision FROM saves WHERE user_id = ?', [userId]).catch(() => null);
  if (cur) snapshotOldSave(userId, String(cur.save_data), Number(cur.gm_revision) || 0);

  const r = await updatePlayerSave(userId, (saveData: any) => {
    if (!restored || typeof restored !== 'object' || Array.isArray(restored)) return;
    Object.keys(saveData).forEach((k) => { delete saveData[k]; });
    Object.assign(saveData, restored);
  });
  if (!r.ok) return res.status(400).json({ error: r.error });

  const after: any = await dbGet('SELECT gm_revision FROM saves WHERE user_id = ?', [userId]).catch(() => null);
  const gm_revision = Number(after && after.gm_revision) || 0;
  logGmAction('restore_snapshot', `user:${userId}`, { snapshot_id: sid, snapshot_gm_revision: Number(snap.gm_revision) || 0, gm_revision });
  res.json({ ok: true, restored_snapshot_id: sid, gm_revision });
});"""


def selftest() -> int:
    """在真实的上一环产物上跑门禁（不碰 srv/index_v28.ts）。"""
    print('0.8.9 基座清理环（链第 17 环）— 自证')
    gate_list = []
    ok = True

    def gate(name, cond, detail=''):
        nonlocal ok
        gate_list.append((name, bool(cond), detail))
        if not cond:
            ok = False

    cand = os.path.join(HERE, '_chainstage', 's16.reward089.ts')
    if not os.path.isfile(cand):
        # 退化：用 srv/index_v28.ts
        cand = os.path.join(HERE, 'srv', 'index_v28.ts')
    if not os.path.isfile(cand):
        print('  [FAIL] 找不到上一环产物')
        return 1

    src = open(cand, encoding='utf-8').read()
    print('  上一环产物 : %s  bytes=%d md5=%s' % (os.path.basename(cand), len(src.encode('utf-8')), md5s(src)))

    if MARK in src:
        print('  [SKIP] 已含 %s 标记' % MARK)
        return 0

    for tag, anc in (('C1', C1_OLD), ('C2', C2_OLD), ('C3', C3_OLD)):
        if src.count(anc) != 1:
            print('  [FAIL] 前置守卫 %s 锚点命中 %d 次（期望 1）' % (tag, src.count(anc)))
            return 1
    print('  [OK]   前置守卫：C1/C2/C3 锚点各命中 1 次')

    out = apply_one(src, 'C1', C1_OLD, C1_NEW)
    out = apply_one(out, 'C2', C2_OLD, C2_NEW)
    out = apply_one(out, 'C3', C3_OLD, C3_NEW)

    delta = len(out.encode('utf-8')) - len(src.encode('utf-8'))

    # 门禁
    gate('G1 require( 已清零', out.count('require(') == 0, '实际 %d' % out.count('require('))
    gate("G2 弱口令缺省 || 'gamer' 已清零", out.count("|| 'gamer'") == 0, "实际 %d" % out.count("|| 'gamer'"))
    gate('G3 GM_PASSWORD 硬失败就位', 'if (!GM_PASSWORD)' in out and 'process.exit(1)' in out)
    gate('G4 红：GM_PASSWORD 比对处未动', out.count("password !== GM_PASSWORD") == 1)
    gate('G5 game-dicts.json 的 path.join 仍在', out.count("path.join(__dirname, 'game-dicts.json')") == 1)
    gate('G6 /api/gm/dicts 端点仍在', out.count("app.get('/api/gm/dicts'") == 1)
    gate('G7 幂等标记就位', MARK in out)
    gate('G8 增长 ∈ [0, 6000] B', 0 <= delta <= 6000, 'delta = %+d B' % delta)
    # C3 快照端点（读侧点亮）
    _slist = 'app.get(\'/api/gm/players/:id/snapshots\', authenticateGM'
    _srest = 'app.post(\'/api/gm/players/:id/snapshots/:sid/restore\', authenticateGM'
    gate('G9 快照列表端点恰 1 处', out.count(_slist) == 1, '实际 %d' % out.count(_slist))
    gate('G10 快照回档端点恰 1 处', out.count(_srest) == 1, '实际 %d' % out.count(_srest))
    gate('G11 两快照端点定义起块内均含 authenticateGM（取到下一个 app. 为止）',
         block_ok(out, _slist) and block_ok(out, _srest))
    # 「不回全文」的可判定口径：列表 SELECT 只取长度（LENGTH），**不取** save_data 正文列。
    #   注意不能在块内直接数 'save_data' == 0 —— 列名本身就叫 save_data（LENGTH(save_data) /
    #   WHERE ... save_data ...），且回档端点**必须**读正文（它就是要写回去）。抓的是 SELECT 投影。
    gate('G12 列表不回全文：投影只取 LENGTH(save_data) 别名、且不 SELECT save_data 正文',
         out.count('LENGTH(save_data) AS save_bytes') == 1
         and 'SELECT id, gm_revision, created_at, LENGTH(save_data) AS save_bytes' in out
         and 'SELECT id, save_data' not in _head_block(out, _slist))
    # 回档端点必须**先存后写**（可逆性）+ 归属校验 + 审计
    _rb = _head_block(out, _srest)
    gate('G13 回档前置：归属校验打的 user_id 主键 + 回档前先 snapshotOldSave',
         'WHERE id = ? AND user_id = ?' in _rb
         and _rb.count('snapshotOldSave(') == 1
         and _rb.find('snapshotOldSave(') < _rb.find('updatePlayerSave('))
    gate('G14 回档审计落库 + 回传新 gm_revision',
         "logGmAction('restore_snapshot'" in _rb
         and 'gm_revision' in _rb and 'restored_snapshot_id' in _rb)
    # 红线：其它环锚区未动
    gate('R1 红线：settleSaveEconV2 仍在', out.count('function settleSaveEconV2') == 1)
    gate('R2 红线：isValidSavePayload 仍在', out.count('function isValidSavePayload') == 1)
    gate('R3 红线：防倒滚 409 语义未动', out.count("error: 'stale_save'") == 1)
    gate('R4 红线：activity_milestones 建表仍在且无 .catch',
         out.count('CREATE TABLE IF NOT EXISTS activity_milestones') == 1
         and not re.search(r'db\.run\([^\n]*\)\.catch\(', out))
    gate('R5 红线：GM 存档只读端点未被破坏（仍在且仍带 authenticateGM）',
         out.count("app.get('/api/gm/players/:id/save', authenticateGM") == 1)
    # 锚点须**含表名**：全文 'ORDER BY id DESC LIMIT 50' 有 7 处（任务是别家的），只数它必然假 FAIL。
    gate('R6 红线：快照写侧 snapshotOldSave 一字未动（节流 <10min / 每号留 50 条）',
         out.count('function snapshotOldSave(userId: number, oldSaveData: string, gmRevision: number)') == 1
         and out.count('DELETE FROM save_snapshots WHERE user_id = ? AND id NOT IN (SELECT id FROM save_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT 50)') == 1
         and out.count('INSERT INTO save_snapshots (user_id, save_data, gm_revision) VALUES (?, ?, ?)') == 1)

    print('\n  --- 门禁 ---')
    for name, c, detail in gate_list:
        print('  [%s] %s%s' % ('OK' if c else 'FAIL', name, ('  ' + detail) if detail else ''))
    print('\n  自证结果：%s' % ('全 PASS' if ok else '存在 FAIL'))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description='0.8.9 基座清理环（链第 17 环 / 末环）')
    ap.add_argument('--src', help='上一环产物（就地原子写回）')
    ap.add_argument('--out', help='本环产物（缺省 = 就地写 --src）')
    ap.add_argument('--selftest', action='store_true', help='只跑自证，不碰文件')
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
    print('0.8.9 基座清理环（链第 17 环 / 末环）')
    print('  source : %s  bytes=%d md5=%s' % (src, before_bytes, md5s(text)))

    if MARK in text:
        print('  [SKIP] 已包含 %s 标记，无需重复打补丁' % MARK)
        return 0

    for tag, anc in (('C1', C1_OLD), ('C2', C2_OLD), ('C3', C3_OLD)):
        if text.count(anc) != 1:
            die('前置守卫失败：%s 锚点命中 %d 次（期望 1）—— 基线不符' % (tag, text.count(anc)))
    print('  [OK]   前置守卫：C1/C2/C3 锚点各命中 1 次')

    text = apply_one(text, 'C1', C1_OLD, C1_NEW)
    text = apply_one(text, 'C2', C2_OLD, C2_NEW)
    text = apply_one(text, 'C3', C3_OLD, C3_NEW)

    delta = len(text.encode('utf-8')) - before_bytes
    gates = []

    def gate(name, cond, detail=''):
        gates.append((name, bool(cond), detail))

    gate('G1 require( 已清零', text.count('require(') == 0, '实际 %d' % text.count('require('))
    gate("G2 弱口令缺省 || 'gamer' 已清零", text.count("|| 'gamer'") == 0, "实际 %d" % text.count("|| 'gamer'"))
    gate('G3 GM_PASSWORD 硬失败就位', 'if (!GM_PASSWORD)' in text and 'process.exit(1)' in text)
    gate('G4 红：GM_PASSWORD 比对处未动', text.count("password !== GM_PASSWORD") == 1)
    gate('G5 game-dicts.json 的 path.join 仍在', text.count("path.join(__dirname, 'game-dicts.json')") == 1)
    gate('G6 /api/gm/dicts 端点仍在', text.count("app.get('/api/gm/dicts'") == 1)
    gate('G7 幂等标记就位', MARK in text)
    gate('G8 增长 ∈ [0, 6000] B', 0 <= delta <= 6000, 'delta = %+d B' % delta)
    # C3 快照端点（读侧点亮）
    _slist = 'app.get(\'/api/gm/players/:id/snapshots\', authenticateGM'
    _srest = 'app.post(\'/api/gm/players/:id/snapshots/:sid/restore\', authenticateGM'
    gate('G9 快照列表端点恰 1 处', text.count(_slist) == 1, '实际 %d' % text.count(_slist))
    gate('G10 快照回档端点恰 1 处', text.count(_srest) == 1, '实际 %d' % text.count(_srest))
    gate('G11 两快照端点定义起块内均含 authenticateGM（取到下一个 app. 为止）',
         block_ok(text, _slist) and block_ok(text, _srest))
    gate('G12 列表不回全文：投影只取 LENGTH(save_data) 别名、且不 SELECT save_data 正文',
         text.count('LENGTH(save_data) AS save_bytes') == 1
         and 'SELECT id, gm_revision, created_at, LENGTH(save_data) AS save_bytes' in text
         and 'SELECT id, save_data' not in _head_block(text, _slist))
    _rb = _head_block(text, _srest)
    gate('G13 回档前置：归属校验打的 user_id 主键 + 回档前先 snapshotOldSave',
         'WHERE id = ? AND user_id = ?' in _rb
         and _rb.count('snapshotOldSave(') == 1
         and _rb.find('snapshotOldSave(') < _rb.find('updatePlayerSave('))
    gate('G14 回档审计落库 + 回传新 gm_revision',
         "logGmAction('restore_snapshot'" in _rb
         and 'gm_revision' in _rb and 'restored_snapshot_id' in _rb)
    gate('R1 红线：settleSaveEconV2 仍在', text.count('function settleSaveEconV2') == 1)
    gate('R2 红线：isValidSavePayload 仍在', text.count('function isValidSavePayload') == 1)
    gate('R3 红线：防倒滚 409 语义未动', text.count("error: 'stale_save'") == 1)
    gate('R4 红线：activity_milestones 建表仍在且无 .catch',
         text.count('CREATE TABLE IF NOT EXISTS activity_milestones') == 1
         and not re.search(r'db\.run\([^\n]*\)\.catch\(', text))
    gate('R5 红线：GM 存档只读端点未被破坏（仍在且仍带 authenticateGM）',
         text.count("app.get('/api/gm/players/:id/save', authenticateGM") == 1)
    # 锚点须**含表名**：全文 'ORDER BY id DESC LIMIT 50' 有 7 处（任务是别家的），只数它必然假 FAIL。
    gate('R6 红线：快照写侧 snapshotOldSave 一字未动（节流 <10min / 每号留 50 条）',
         text.count('function snapshotOldSave(userId: number, oldSaveData: string, gmRevision: number)') == 1
         and text.count('DELETE FROM save_snapshots WHERE user_id = ? AND id NOT IN (SELECT id FROM save_snapshots WHERE user_id = ? ORDER BY id DESC LIMIT 50)') == 1
         and text.count('INSERT INTO save_snapshots (user_id, save_data, gm_revision) VALUES (?, ?, ?)') == 1)

    bad = [g for g in gates if not g[1]]
    print('\n  --- 门禁 ---')
    for name, c, detail in gates:
        print('  [%s] %s%s' % ('OK' if c else 'FAIL', name, ('  ' + detail) if detail else ''))
    if bad:
        print('\n[ABORT] 门禁未全过，不写出')
        return 1

    if out != src:
        open(out, 'wb').write(text.encode('utf-8'))
        print('\n  [写出] %s  bytes=%d  md5=%s' % (out, len(text.encode('utf-8')), md5s(text)))
    else:
        bak = '%s.bak-baseclean-%s' % (src, time.strftime('%Y%m%d-%H%M%S'))
        shutil.copy2(src, bak)
        print('\n  [备份] %s' % bak)
        open(src, 'wb').write(text.encode('utf-8'))
        print('  [写出] %s  bytes=%d  md5=%s' % (src, len(text.encode('utf-8')), md5s(text)))

    print('  [PASS] 基座清理完成（delta %+d B）' % delta)
    return 0


if __name__ == '__main__':
    sys.exit(main())
