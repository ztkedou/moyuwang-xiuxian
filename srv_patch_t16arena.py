# -*- coding: utf-8 -*-
r"""srv_patch_t16arena.py — 0.8.8 T16 仙务·演武场服务端环（链第 20 环 / 新末环）

## 背景：客户端已交付，服务端从未实现

`yl_t16arena_ext.py`（客户端，32KB）已把 `YlxwTArena` 重写为三区分栏
（试炼 PVE / 论剑 PVP / 恩怨），但服务端侧**零实现**：没有 `srv_patch_t16*.py`、
没有 trial/ladder 表、没有 `ARENA_TIER_CUTS`。现有 arena 路由只有 0.8.7 旧版 4 个
（`/api/arena/challenge`、`/api/arena/my`、`/api/arena/accept`、`/api/arena/decline`）。

⇒ 客户端新 UI 调 6 个**不存在**的端点，全部吃 Express 404（`YlxwApi` 抛
`请求失败(404)`，面板整块报错）。本环补齐这 6 个端点。

客户端模块头（`yl_t16arena_ext.py:26-29`）明写：建表 / 6 个新端点 / 积分结算 / 日切
**归 i2-srv**；客户端只做「调用与展示」。

## 权威规格

`docs/0.8.8-design/T16-演武场.md`（55KB）。本环逐条落地 §5.1（敌人强度）/ §5.2（奖励）/
§5.3（次数与购买）/ §5.4（段位与积分）/ §6.1（新表）/ §6.2（新端点）/ §6.4（活跃度零埋点）。

## 客户端实际调用（grep 实测 `yl_t16arena_ext.py`）与本环响应形状

| 端点 | 方法 | 客户端读的字段 | 本环响应 |
|---|---|---|---|
| `/api/arena/trials` | GET | `st.dailyLeft` / `st.cleared["r-l"]` / `st.maxRealm` / `st.buyLeft` | 同名同义 |
| `/api/arena/trials/fight` | POST `{realmIndex,layer}` | 仅 toast + reload | `{ok,iWon,log,stones,exp,...}` |
| `/api/arena/trials/buy` | POST `{}` | 仅 toast + reload | `{ok,cost,buyLeft,dailyLeft}` |
| `/api/arena/ladder` | GET | `data.top[].{id\|userId,name,combatPower\|combat_power}` / `data.me.{points,wins,losses}` / `data.snapshotLeft` | 全给（两种键名都给） |
| `/api/arena/snapshot` | POST `{targetId}` | 仅 toast + reload | `{ok,iWon,pointsDelta,points,tier,snapshotLeft}` |
| `/api/arena/grudge` | POST `{targetId}` | 仅 toast + reload | `{ok,iWon,stones,log}` |
| `/api/arena/my`（改造） | GET | `t.realmIndex` / `t.grudges[].{id,name,reason}` / `t.trial`(兜底) | 追加字段（D7：只加不改） |

## 与既有擂台的边界（D7：只加不改）

`ARENA_DAILY_MAX=3` / `ARENA_RENOWN_WIN=10` / `ARENA_STONE_BASE=3000` / `arena_battles`
表结构 / 4 个旧端点语义 —— **一字不动**。本环只**追加**新表、新常量、新端点，
以及 `/api/arena/my` 的**追加字段**（`...spread`，既有 6 个字段逐字保留）。

## ★ 活跃度零埋点（T16 §6.4 / §7.3，T16↔T9 交叉纪律）

演武场侧**不写任何活跃度埋点**：不 `INSERT/UPDATE daily_quests`、不新增 `QUEST_DEFS`、
不碰 `POST /api/quest/chest` 的 `activityFromQuests`。活跃度「擂台论道 3 次/日 × 7 分」
由 T9 在 `/api/quest/summary` 内**读时 COUNT `arena_battles`**（该表结构不变 ⇒ 读法不变）。
门禁里对 `daily_quests` / `QUEST_DEFS` / `activityFromQuests` 三处做**基线计数断言**。

## 日切口径（§5.3 / §3.5.3）

统一**北京 0 点**。实测产物 `utcDayStartMs`（:8925）**已经是北京口径**
（`Date.parse(bjDate(now)+'T00:00:00+08:00')`），并非文档 §3.5.3 所描述的 UTC ——
故既有 2 处竞技场日切**无需改动**（拍板项 I 的方案甲在更早的环已落地）。
本环日串一律用 `bjDate(Date.now())`（北京 YYYY-MM-DD），与 T9 活跃度同口径。

## 改动清单（3 处锚区，互不重叠，且与前 19 环零交集）

| # | 锚点 | 改动 |
|---:|---|---|
| C1 | `idx_arena_cha` 索引行之后（`:771`） | 追 4 张新表 + 索引（全 `CREATE TABLE IF NOT EXISTS`，建表即带全部列） |
| C2 | `// ── 师徒传功 ──` 段注释之前（`:9685`） | 追 `[t16arena]` 常量/纯函数块 + 6 个新端点 |
| C3 | `/api/arena/my` 的 `renownTop:` 行 + `});`（`:9565-9566`） | 追 `...(await arenaMyExtra(userId))`（**只加不改**） |

* C1 锚区 = `arena_battles` 索引之后、`grudges` 建表之前 ⇒ 同段追加，位置自洽。
* C2 锚区 = 恩怨端点之后、师徒传功之前 ⇒ 同段追加。
* C3 锚区 = `/arena/my` 响应对象尾部 ⇒ 单行追加。

## 工程约束（本项目已踩过的坑，本环逐条遵守）

1. **回调式 sqlite3** ⇒ 一律 `dbGet / dbAll / dbRun`（Promise 封装，:3907）；
   `db.run(...).catch(...)` **禁止**（返回 `Database` 非 Promise ⇒ 顶层 TypeError ⇒ 起不来）。
2. **ESM** ⇒ `require(` **禁止**（未定义）。
3. **加列走 `safeAddColumn`**；本环**不新增列**（新表建表即带全部列）⇒ 无 ALTER，
   `db.exec('ALTER TABLE …')` 直调 == 0。
4. **鉴权照抄既有 arena 端点**：`authenticateToken` + `rateLimit({windowMs, max, keyFn})`。
5. **入参收口**：`asStr / asNum`（:1204/:1210），防原型链污染与类型混淆。
6. **★ 不许「引用未声明变量」**：所有 `const` 均在使用前、同作用域内声明；
   门禁有孤儿检测（注入块内每个声明名至少 2 次出现 = 声明 + 至少 1 个消费者）。
7. **数值纪律（§5.2）**：一律**整数百分比式再除**，禁直接乘浮点字面量
   （`150×1.64` 在 IEEE754 下 floor 得 245，而 `150×164/100` 得 246）。

## 红线

* 不碰 `_v281_base/`（基座只读）；不改任何既存 `srv_patch_*.py`（本环是**新增**末环）。
* 不碰 `build/`、不碰 `yl_*.py`（客户端域）；不碰线上服务器。
* 不改 `arena_battles` 建表串、不改 4 个既有 arena 端点语义、不改 `daily_quests`。

## 用法

```
python srv_patch_t16arena.py --src <上一环产物>    # 就地原子写回 --src
python srv_patch_t16arena.py --selftest            # 只跑门禁，不碰文件
```

幂等：已含 `T16ARENA088` 标记则 SKIP。锚点不唯一一律中止（拒绝静默失败）。
"""
import argparse
import hashlib
import os
import re
import shutil
import sys
import time

MARK = 'T16ARENA088'
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


def _assert_anchor_kept(tag: str, old: str, new: str) -> None:
    """★ 自毁防线：**插入式**改动必须把锚点原文带进 new。

    `apply_one` = `text.replace(old, new)`。若 new 不含 old，锚点会被**整段删除**
    —— 那不是「在锚点后插入」，而是「用新块替换掉锚点」（本项目踩过：锚点被吃 ⇒ 500）。
    """
    if old not in new:
        die('%s 自毁防线：new 未包含锚点原文 ⇒ 锚点行会被整段删除（不是插入）。' % tag)
    print('  [OK] %-6s 自毁防线通过（new 含锚点原文，属插入式改动）' % tag)


def _block(text: str, anchor: str, end: str) -> str:
    """取 [anchor, end) 切片 —— 只在该区间内断言，避免全文计数误伤邻座。"""
    i = text.find(anchor)
    if i < 0:
        return ''
    j = text.find(end, i + len(anchor))
    return text[i:] if j < 0 else text[i:j]


# ─────────────────────────────────────────────────────────
# C1 · 4 张新表（建表即带全部列；不新增列 ⇒ 无 ALTER）
# ─────────────────────────────────────────────────────────
C1_ANCHOR = "  db.run(`CREATE INDEX IF NOT EXISTS idx_arena_cha ON arena_battles(challenger_id, status)`);"

C1_NEW = C1_ANCHOR + """
  // ── T16（0.8.8）演武场：试炼 / 积分段位 / 快照挑战 / 试炼日状态 ──
  //   全部 `CREATE TABLE IF NOT EXISTS` 且**建表即带全部列**（最稳，后续无需 ALTER）。
  //   * arena_trials       —— 试炼战斗流水（won=1 计次；first_clear=1 为首通，部分唯一索引防重复首通）
  //   * arena_scores       —— 演武场积分/段位（独立表，不动 rankings 存量结构，§6.1）
  //   * arena_snapshots    —— 快照挑战流水（唯一索引 (challenger,target,date) = R6「同一目标每日 1 次」的原子防线）
  //   * arena_trial_daily  —— 试炼日状态（今日已购次数 + 每日首胜/三连胜一次性奖励已发标记）
  db.run(`CREATE TABLE IF NOT EXISTS arena_trials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    realm_index INTEGER NOT NULL,
    layer INTEGER NOT NULL,
    kind TEXT NOT NULL,
    date TEXT NOT NULL,
    won INTEGER NOT NULL DEFAULT 0,
    first_clear INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_arena_trials_daily ON arena_trials(user_id, date)`);
  db.run(`CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_trials_first ON arena_trials(user_id, realm_index, layer) WHERE first_clear = 1`);
  db.run(`CREATE TABLE IF NOT EXISTS arena_scores (
    user_id INTEGER PRIMARY KEY,
    points INTEGER NOT NULL DEFAULT 0,
    tier INTEGER NOT NULL DEFAULT 1,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL
  )`);
  db.run(`CREATE TABLE IF NOT EXISTS arena_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenger_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    won INTEGER NOT NULL,
    date TEXT NOT NULL,
    created_at INTEGER NOT NULL
  )`);
  db.run(`CREATE INDEX IF NOT EXISTS idx_arena_snap_daily ON arena_snapshots(challenger_id, date)`);
  db.run(`CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_snap_once ON arena_snapshots(challenger_id, target_id, date)`);
  db.run(`CREATE TABLE IF NOT EXISTS arena_trial_daily (
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    buys INTEGER NOT NULL DEFAULT 0,
    first_win INTEGER NOT NULL DEFAULT 0,
    triple_win INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
  )`);
  // ── T5（0.8.9）修复落点：farm_daily_care 照料计次列 tend_count 的**幂等迁移** ──
  //   ★ 为何落在本环（第 20 环）而非灵田环（第 15 环）：
  //     第 18 环 rankingmig 的 G5/G7 硬编码「全仓 safeAddColumn 调用点 == 20 / ADD COLUMN == 20」，
  //     且该环为**禁改文件** ⇒ 第 15 环任何新增加列都会让它 FAIL。本环在其之后 ⇒ 计数门禁不受影响。
  //   * tend_count：farm_daily_care 当日该田照料次数（tended 原为布尔，装不下次数）。
  //     tendBonus = min(FARM_TEND_CAP, tend_count × FARM_TEND_PER)（见第 15 环 farmHarvestMods）。
  //     幂等 safeAddColumn（容忍 duplicate column name；空库冷启动 / 重跑双安全）。
  //   * farm_daily_care 的 CREATE TABLE（第 12 环）在本行之前已入 db.serialize 队列 ⇒ PRAGMA 可见该表。
  db.all("PRAGMA table_info(farm_daily_care)", (err: any, rows: any[]) => {
    if (!err && rows && !rows.some((r: any) => r.name === 'tend_count')) {
      safeAddColumn('farm_daily_care', 'tend_count', 'ALTER TABLE farm_daily_care ADD COLUMN tend_count INTEGER NOT NULL DEFAULT 0');
    }
  });"""

# ─────────────────────────────────────────────────────────
# C2 · [t16arena] 常量 + 纯函数 + 6 个新端点（插在「师徒传功」段之前）
# ─────────────────────────────────────────────────────────
C2_ANCHOR = "// ── 师徒传功 ──"

C2_NEW_BODY = """// ─────────────────────────────────────────────────────────
// T16ARENA088 · T16（0.8.8 C 组）演武场：PVE 试炼 + 异步 PVP 论剑（快照挑战）+ 积分段位 + 恩怨入口。
// 权威规格：docs/0.8.8-design/T16-演武场.md §5.1 / §5.2 / §5.3 / §5.4 / §6.1 / §6.2 / §6.4。
// ★ 活跃度纪律（§6.4 / §7.3）：演武场侧**零埋点** —— 本块不写 daily_quests、不新增
//   QUEST_DEFS、不碰 /api/quest/chest 的 activityFromQuests。活跃度「擂台论道」由 T9
//   读时 COUNT arena_battles（本环不动该表结构 ⇒ T9 读法不变）。
// ★ 日切：统一北京 0 点。日串一律 bjDate(Date.now())（与 T9 活跃度同口径）。
// ★ 与存量擂台边界（D7）：ARENA_DAILY_MAX / ARENA_RENOWN_WIN / ARENA_STONE_BASE /
//   arena_battles 表结构 / 4 个旧端点语义 —— 一字不动。
// [t16arena]
const ARENA_TIER_CUTS = [0, 100, 300, 600, 1000, 1500, 2100];
const ARENA_TIER_NAMES = ['凡铁境', '青锋境', '银锋境', '金锋境', '玄锋境', '化虚境', '太虚境'];
const ARENA_PT_WIN = [12, 12, 12, 14, 14, 16, 16];   // 胜（同段 / 低段）
const ARENA_PT_OVER = [18, 18, 18, 21, 21, 24, 24];  // 胜（越级挑战，= 同段 +6/+7/+8）
const ARENA_PT_LOSE = [5, 5, 5, 6, 6, 7, 7];         // 负（扣分，下限 0）
const ARENA_TRIAL_FREE = 5;          // 试炼每日免费 5 次（§5.3）
const ARENA_TRIAL_BUY_MAX = 2;       // 试炼每日最多购买 2 次（§5.3）
const ARENA_SNAPSHOT_MAX = 5;        // 快照挑战每日 5 次（§5.3）
const ARENA_TRIAL_LAYERS = 9;        // 每关 9 层（§3.2）
const ARENA_TRIAL_ELITE = [3, 6, 9]; // 精英层（奖励 ×1.5，§3.2）
// Cs 境界基础属性（§5.1；与客户端 YlxwArenaRealms 同源；maxHp/attack/defense 与
// TRIB_REALM_BASES :4343 逐字一致，spirit=defense、physique=attack，speed 与 maxExpBase 见 §5.1 表）
const ARENA_TRIAL_REALMS = [
  { name: '炼气期', maxHp: 100,   attack: 10,   defense: 5,   spirit: 5,   physique: 10,   speed: 10,  maxExpBase: 60000 },
  { name: '筑基期', maxHp: 250,   attack: 25,   defense: 12,  spirit: 12,  physique: 25,   speed: 15,  maxExpBase: 390000 },
  { name: '金丹期', maxHp: 625,   attack: 50,   defense: 25,  spirit: 25,  physique: 50,   speed: 13,  maxExpBase: 1521000 },
  { name: '元婴期', maxHp: 1250,  attack: 125,  defense: 62,  spirit: 62,  physique: 125,  speed: 13,  maxExpBase: 6592000 },
  { name: '化神期', maxHp: 3125,  attack: 312,  defense: 156, spirit: 156, physique: 312,  speed: 50,  maxExpBase: 26775000 },
  { name: '合道期', maxHp: 7812,  attack: 781,  defense: 390, spirit: 390, physique: 781,  speed: 125, maxExpBase: 104430000 },
  { name: '长生境', maxHp: 19531, attack: 1953, defense: 976, spirit: 976, physique: 1953, speed: 313, maxExpBase: 452500000 },
];
// 试炼 NPC 名号（同一层名号固定，可反复挑战、可记忆，§3.2）
const ARENA_TRIAL_NPC = ['青石道人', '竹影剑客', '玄铁真君', '赤霄魔君', '紫府仙尊', '太虚剑尊', '长生老祖'];
// M(r) = 1.5^r（r 0..6；全部为二进制可精确表示的 dyadic 有理数，无浮点尾巴）
const ARENA_M_MULT = [1, 1.5, 2.25, 3.375, 5.0625, 7.59375, 11.390625];

function arenaM(realmIdx: number): number {
  const i = Math.floor(Number(realmIdx));
  return (Number.isFinite(i) && i >= 0 && i < ARENA_M_MULT.length) ? ARENA_M_MULT[i] : 1;
}
// 段位序（0..6，纯）：积分 → 段位索引（实时升降、可掉段，§5.4）
function arenaTierIdx(points: unknown): number {
  const p = Math.max(0, Math.floor(Number(points) || 0));
  let i = 0;
  for (let k = 0; k < ARENA_TIER_CUTS.length; k++) { if (p >= ARENA_TIER_CUTS[k]) i = k; }
  return i;
}
// 试炼敌人属性（纯）：f(layer)=135×(100+16×(layer-1))/10000，E(stat)=floor(Cs×f)
//   ★ 整数式（乘 10000 再除），不做 60/300 下限 —— §5.1 主表即「已定档绝对属性」，
//     套下限会与主表（炼气 L1 气血 135）自相矛盾；与客户端 YlxwArenaEnemy 同口径。
function arenaTrialStats(realmIdx: number, layer: number): any {
  const r = ARENA_TRIAL_REALMS[realmIdx];
  if (!r) return null;
  const fn = 135 * (100 + 16 * (layer - 1)); // = f(layer) × 10000
  const sc = (v: number) => Math.floor(v * fn / 10000);
  return {
    maxHp: sc(r.maxHp), attack: sc(r.attack), defense: sc(r.defense),
    spirit: sc(r.spirit), physique: sc(r.physique), speed: sc(r.speed),
  };
}
// 战力口径（与 extractRankingData :1315 同式）：floor(attack+defense+maxHp/10+spirit+speed)
//   ★ R2 定档：敌人 CP 用与玩家**同一条**公式（physique 不入 CP —— 玩家侧也不入），
//     保证「同境界同层敌人」与同境界玩家的 CP 可比。
function arenaCombatOfStats(s: any): number {
  if (!s) return 100;
  const cp = Number(s.attack || 0) + Number(s.defense || 0) + Number(s.maxHp || 0) / 10 + Number(s.spirit || 0) + Number(s.speed || 0);
  return Number.isFinite(cp) && cp > 0 ? Math.floor(cp) : 100;
}
function arenaIsElite(layer: number): boolean { return ARENA_TRIAL_ELITE.indexOf(layer) >= 0; }
// 奖励（§5.2；★ 一律整数百分比式再除，禁直接乘浮点字面量）
function arenaTrialWinStones(realmIdx: number, layer: number): number {
  return Math.floor(150 * arenaM(realmIdx) * (100 + 8 * (layer - 1)) / 100);
}
function arenaTrialFirstWin(realmIdx: number): number { return Math.floor(800 * arenaM(realmIdx)); }
function arenaTrialTriple(realmIdx: number): number { return Math.floor(1200 * arenaM(realmIdx)); }
// 首通灵石：普通 floor(500×M×layer)；精英 ×1.5（★ 先乘再 floor，对齐 §5.2 手算 76,886）
function arenaTrialClearStones(realmIdx: number, layer: number, elite: boolean): number {
  const raw = 500 * arenaM(realmIdx) * layer;
  return elite ? Math.floor(raw * 3 / 2) : Math.floor(raw);
}
// 修为槽：floor(maxExpBase × (100 + 24×(layer-1)) / 100)（§5.2 整数式）
//   ★ 刻意不复用 realmMaxExp()（:4354）—— 后者是 `base×(1+(lv-1)×0.24)` 浮点式，
//     金丹 L5 会得 2,981,159 而非 §5.2 的 2,981,160（浮点尾巴）。天劫口径不动，本环另立整数式。
function arenaTrialMaxExp(realmIdx: number, layer: number): number {
  const r = ARENA_TRIAL_REALMS[realmIdx];
  const base = r ? r.maxExpBase : 60000;
  return Math.floor(base * (100 + 24 * (layer - 1)) / 100);
}
// 首通修为：floor(0.05 × realmMaxExp × (精英?1.5:1))，0.05 = 5/100、1.5 = 3/2（整数式）
function arenaTrialClearExp(realmIdx: number, layer: number, elite: boolean): number {
  const raw = arenaTrialMaxExp(realmIdx, layer) * 5;
  return elite ? Math.floor(raw * 3 / 200) : Math.floor(raw / 100);
}
// 购买价：第 n 次（n 从 0 起）floor(2000×(n+1)×M(r))（§5.3）
function arenaTrialBuyPrice(realmIdx: number, nth: number): number {
  return Math.floor(2000 * (nth + 1) * arenaM(realmIdx));
}
// 规则下发（对齐 T8 mentor 的 rules 口径，§6.2）
function arenaRules(): any {
  return {
    trialFree: ARENA_TRIAL_FREE, trialBuyMax: ARENA_TRIAL_BUY_MAX, trialLayers: ARENA_TRIAL_LAYERS,
    trialElite: ARENA_TRIAL_ELITE.slice(), snapshotMax: ARENA_SNAPSHOT_MAX, dailyMax: ARENA_DAILY_MAX,
    tierCuts: ARENA_TIER_CUTS.slice(), tierNames: ARENA_TIER_NAMES.slice(),
    ptWin: ARENA_PT_WIN.slice(), ptOver: ARENA_PT_OVER.slice(), ptLose: ARENA_PT_LOSE.slice(),
  };
}
// 试炼日状态（北京日）：wins=今日胜场（=今日已耗次数，失败不扣次数）；buys=今日已购
async function arenaTrialDay(userId: number): Promise<{ date: string; wins: number; buys: number; firstWin: number; tripleWin: number }> {
  const date = bjDate(Date.now());
  const [w, d] = await Promise.all([
    dbGet("SELECT COUNT(*) AS c FROM arena_trials WHERE user_id = ? AND date = ? AND won = 1", [userId, date]),
    dbGet("SELECT buys, first_win, triple_win FROM arena_trial_daily WHERE user_id = ? AND date = ?", [userId, date]),
  ]);
  return {
    date,
    wins: Number(w && w.c) || 0,
    buys: Number(d && d.buys) || 0,
    firstWin: Number(d && d.first_win) || 0,
    tripleWin: Number(d && d.triple_win) || 0,
  };
}
// 试炼日状态累计（单语句原子 upsert；patch 只传 0/1 增量）
async function arenaTrialDayTouch(userId: number, date: string, patch: { buys?: number; firstWin?: number; tripleWin?: number }): Promise<void> {
  await dbRun(
    `INSERT INTO arena_trial_daily (user_id, date, buys, first_win, triple_win) VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(user_id, date) DO UPDATE SET
       buys = buys + ?, first_win = first_win + ?, triple_win = triple_win + ?`,
    [userId, date, patch.buys || 0, patch.firstWin || 0, patch.tripleWin || 0,
     patch.buys || 0, patch.firstWin || 0, patch.tripleWin || 0]);
}
// 今日尾段连胜数（纯读）：从最新一行往回数，遇到败即停
async function arenaTrialStreak(userId: number, date: string): Promise<number> {
  const rows = await dbAll('SELECT won FROM arena_trials WHERE user_id = ? AND date = ? ORDER BY id DESC LIMIT 20', [userId, date]);
  let s = 0;
  for (const r of (rows || [])) { if (Number(r.won) === 1) s++; else break; }
  return s;
}
// 积分/段位读写（§5.4）
async function arenaScoreOf(userId: number): Promise<{ points: number; wins: number; losses: number }> {
  const r = await dbGet('SELECT points, wins, losses FROM arena_scores WHERE user_id = ?', [userId]);
  return { points: Number(r && r.points) || 0, wins: Number(r && r.wins) || 0, losses: Number(r && r.losses) || 0 };
}
async function arenaScoreAdd(userId: number, dPoints: number, won: boolean): Promise<{ points: number; tier: number; tierName: string }> {
  const cur = await arenaScoreOf(userId);
  const next = Math.max(0, cur.points + Math.floor(Number(dPoints) || 0)); // 积分下限 0（不为负）
  const tier = arenaTierIdx(next);
  await dbRun(
    `INSERT INTO arena_scores (user_id, points, tier, wins, losses, updated_at) VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(user_id) DO UPDATE SET points = ?, tier = ?, wins = wins + ?, losses = losses + ?, updated_at = ?`,
    [userId, next, tier + 1, won ? 1 : 0, won ? 0 : 1, Date.now(),
     next, tier + 1, won ? 1 : 0, won ? 0 : 1, Date.now()]);
  return { points: next, tier: tier + 1, tierName: ARENA_TIER_NAMES[tier] };
}
async function arenaCombatOfUser(userId: number): Promise<number> {
  const r = await dbGet('SELECT combat_power FROM rankings WHERE user_id = ?', [userId]);
  const cp = Number(r && r.combat_power);
  return Number.isFinite(cp) && cp > 0 ? cp : 100;
}
async function arenaNameOf(userId: number): Promise<string> {
  const r = await dbGet('SELECT name FROM rankings WHERE user_id = ?', [userId]);
  if (r && r.name) return String(r.name);
  const u = await dbGet('SELECT username FROM users WHERE id = ?', [userId]);
  return String((u && u.username) || '无名');
}
// /api/arena/my 追加字段（D7：只加不改；既有 6 字段在调用处逐字保留）
//   客户端读：t.realmIndex（试炼 myRealm）/ t.grudges[]（恩怨分栏）/ points/tier/tierName/
//   snapshotLeft（论剑分栏）/ rules（玩法说明动态拼接）。
async function arenaMyExtra(userId: number): Promise<any> {
  const [rk, sc, gr, snap] = await Promise.all([
    dbGet('SELECT realm_index FROM rankings WHERE user_id = ?', [userId]),
    arenaScoreOf(userId),
    dbAll(`SELECT g.enemy_id AS id, g.reason, COALESCE(NULLIF(r.name, ''), u.username) AS name
           FROM grudges g JOIN users u ON u.id = g.enemy_id LEFT JOIN rankings r ON r.user_id = g.enemy_id
           WHERE g.owner_id = ? ORDER BY g.avenged ASC, g.id DESC LIMIT 30`, [userId]),
    dbGet("SELECT COUNT(*) AS c FROM arena_snapshots WHERE challenger_id = ? AND date = ?", [userId, bjDate(Date.now())]),
  ]);
  const tierIdx = arenaTierIdx(sc.points);
  return {
    realmIndex: rk && rk.realm_index != null ? Math.max(0, Math.floor(Number(rk.realm_index))) : 0,
    points: sc.points,
    tier: tierIdx + 1,
    tierName: ARENA_TIER_NAMES[tierIdx],
    snapshotLeft: Math.max(0, ARENA_SNAPSHOT_MAX - (Number(snap && snap.c) || 0)),
    // 客户端恩怨分栏读 my.grudges[]（字段名对齐 YlxwArenaGrudgeZone：g.id / g.name / g.reason）
    grudges: (gr || []).map((g: any) => ({ id: Number(g.id), name: String(g.name || ''), reason: String(g.reason || '') })),
    rules: arenaRules(),
  };
}

// GET /api/arena/trials — 试炼状态（客户端 st = tl.data）：今日剩余次数 / 已首通层 / 可挑战境界 / 购买余额。
//   cleared 键形如 "0-1"（realmIndex-layer），与客户端 `cleared[realm + "-" + (layer+1)]` 逐字对应。
app.get('/api/arena/trials', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `ar:tr:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const [rk, day, clearedRows] = await Promise.all([
      dbGet('SELECT realm_index FROM rankings WHERE user_id = ?', [userId]),
      arenaTrialDay(userId),
      dbAll('SELECT realm_index, layer FROM arena_trials WHERE user_id = ? AND first_clear = 1', [userId]),
    ]);
    const realmIndex = rk && rk.realm_index != null ? Math.max(0, Math.floor(Number(rk.realm_index))) : 0;
    const cleared: Record<string, number> = {};
    for (const c of (clearedRows || [])) cleared[Number(c.realm_index) + '-' + Number(c.layer)] = 1;
    res.json({
      now: Date.now(),
      date: day.date,
      realmIndex,
      maxRealm: realmIndex, // 解锁规则：第 N 关需玩家境界 ≥ 该关境界（§3.2）
      dailyLeft: Math.max(0, ARENA_TRIAL_FREE + day.buys - day.wins),
      buyLeft: Math.max(0, ARENA_TRIAL_BUY_MAX - day.buys),
      winsToday: day.wins,
      firstWinToday: day.firstWin > 0,
      tripleToday: day.tripleWin > 0,
      layers: ARENA_TRIAL_LAYERS,
      eliteLayers: ARENA_TRIAL_ELITE.slice(),
      cleared,
      realms: ARENA_TRIAL_REALMS.map((r: any, i: number) => ({ index: i, name: r.name })),
      rules: arenaRules(),
    });
  } catch (e: any) { console.error('arena trials error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// POST /api/arena/trials/fight {realmIndex, layer} — 试炼闯关（快速结算，复用 arenaResolve 战力加权随机）。
//   校验：境界解锁 → 层解锁（第 k 层需第 k-1 层已首通）→ 次数；★ 失败**不扣次数**（§3.2 取舍点 D 默认）。
//   奖励（§5.2）：单次胜利 + 每日首胜 + 当日三连胜 + 首通（灵石 + 修为，一次性）。
app.post('/api/arena/trials/fight', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `ar:tf:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const realmIndex = Math.floor(asNum(req.body?.realmIndex));
    const layer = Math.floor(asNum(req.body?.layer));
    if (!Number.isInteger(realmIndex) || realmIndex < 0 || realmIndex >= ARENA_TRIAL_REALMS.length) return res.status(400).json({ error: '参数非法' });
    if (!Number.isInteger(layer) || layer < 1 || layer > ARENA_TRIAL_LAYERS) return res.status(400).json({ error: '参数非法' });
    const [rk, day, prevClear, already] = await Promise.all([
      dbGet('SELECT realm_index FROM rankings WHERE user_id = ?', [userId]),
      arenaTrialDay(userId),
      layer > 1 ? dbGet('SELECT 1 AS x FROM arena_trials WHERE user_id = ? AND realm_index = ? AND layer = ? AND first_clear = 1 LIMIT 1', [userId, realmIndex, layer - 1]) : Promise.resolve(null),
      dbGet('SELECT 1 AS x FROM arena_trials WHERE user_id = ? AND realm_index = ? AND layer = ? AND first_clear = 1 LIMIT 1', [userId, realmIndex, layer]),
    ]);
    const myRealm = rk && rk.realm_index != null ? Math.max(0, Math.floor(Number(rk.realm_index))) : 0;
    if (realmIndex > myRealm) return res.status(409).json({ error: '境界不足，尚不可挑战此关' });
    if (layer > 1 && !prevClear) return res.status(409).json({ error: '请先通关上一层' });
    if (Math.max(0, ARENA_TRIAL_FREE + day.buys - day.wins) <= 0) return res.status(409).json({ error: '今日挑战次数已用完' });
    const elite = arenaIsElite(layer);
    const stats = arenaTrialStats(realmIndex, layer);
    const [myCp, myName] = await Promise.all([arenaCombatOfUser(userId), arenaNameOf(userId)]);
    const opName = (ARENA_TRIAL_NPC[realmIndex] || '试炼对手') + '·第' + layer + '层';
    const out = arenaResolve(myCp, arenaCombatOfStats(stats), myName, opName);
    const won = out.winnerIsMe;
    const isFirst = won && !already;
    const now = Date.now();
    await dbRun(
      "INSERT INTO arena_trials (user_id, realm_index, layer, kind, date, won, first_clear, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
      [userId, realmIndex, layer, elite ? 'elite' : 'normal', day.date, won ? 1 : 0, isFirst ? 1 : 0, now]);
    let stones = 0, exp = 0, dailyFirst = false, triple = false, streak = 0;
    if (won) {
      const winsAfter = day.wins + 1;
      stones += arenaTrialWinStones(realmIndex, layer);
      if (day.firstWin === 0 && winsAfter === 1) { stones += arenaTrialFirstWin(realmIndex); dailyFirst = true; }
      streak = await arenaTrialStreak(userId, day.date);
      if (day.tripleWin === 0 && streak >= 3) { stones += arenaTrialTriple(realmIndex); triple = true; }
      if (isFirst) { stones += arenaTrialClearStones(realmIndex, layer, elite); exp += arenaTrialClearExp(realmIndex, layer, elite); }
      await updatePlayerSave(userId, (sd: any) => {
        if (!sd.player || typeof sd.player !== 'object') return;
        if (stones > 0) sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + stones;
        if (exp > 0) sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + exp;
      });
      if (dailyFirst || triple) await arenaTrialDayTouch(userId, day.date, { firstWin: dailyFirst ? 1 : 0, tripleWin: triple ? 1 : 0 });
    }
    const day2 = await arenaTrialDay(userId);
    res.json({
      ok: true, iWon: won, log: out.log, realmIndex, layer, elite, firstClear: isFirst,
      dailyFirst, triple, streak, stones, exp, nextMaxExp: arenaTrialMaxExp(realmIndex, layer),
      dailyLeft: Math.max(0, ARENA_TRIAL_FREE + day2.buys - day2.wins),
      buyLeft: Math.max(0, ARENA_TRIAL_BUY_MAX - day2.buys),
    });
  } catch (e: any) { console.error('arena trials fight error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// POST /api/arena/trials/buy {} — 购买额外试炼次数（每日 ≤2，§5.3）。
//   定价 floor(2000×(n+1)×M(r))（第 1 次 2000×M、第 2 次 4000×M），与客户端
//   YlxwArenaBuyPrice(realm, buyNth) 逐位一致（buyNth = buyMax - buyLeft）。
//   事务口径：预检 → 扣费（saveLock 互斥 + 二次校验）→ 计数；计数失败则**退费**（唯一补偿窗口）。
app.post('/api/arena/trials/buy', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 5, keyFn: (req: any) => `ar:tb:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const [rk, day] = await Promise.all([dbGet('SELECT realm_index FROM rankings WHERE user_id = ?', [userId]), arenaTrialDay(userId)]);
    if (day.buys >= ARENA_TRIAL_BUY_MAX) return res.status(409).json({ error: '今日购买次数已达上限' });
    const realmIndex = rk && rk.realm_index != null ? Math.max(0, Math.floor(Number(rk.realm_index))) : 0;
    const cost = arenaTrialBuyPrice(realmIndex, day.buys);
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < cost) { short = true; return; }
      sd.player.spiritStones = b - cost;
    });
    if (!paid.ok || short) return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '购买失败，请重试') });
    try {
      await arenaTrialDayTouch(userId, day.date, { buys: 1 });
    } catch (e: any) {
      // 补偿：退费（计数未增），保证「扣了钱没加次数」不可能发生
      await updatePlayerSave(userId, (sd: any) => { sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + cost; });
      console.error('arena trial buy settle error:', e?.message || e);
      return res.status(500).json({ error: '购买失败，请重试' });
    }
    const day2 = await arenaTrialDay(userId);
    res.json({ ok: true, cost, buys: day2.buys, buyLeft: Math.max(0, ARENA_TRIAL_BUY_MAX - day2.buys), dailyLeft: Math.max(0, ARENA_TRIAL_FREE + day2.buys - day2.wins) });
  } catch (e: any) { console.error('arena trial buy error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// GET /api/arena/ladder — 战力榜 TOP20（快照挑战目标）+ 我的积分/段位/快照余额。
//   客户端读 data.top[].{id|userId, name, combatPower|combat_power} / data.me.{points,wins,losses}
//   / data.snapshotLeft ⇒ 本响应**两种 id/战力键名都给**，避免客户端取键落空。
app.get('/api/arena/ladder', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `ar:ld:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const [top, me, sc, snap] = await Promise.all([
      dbAll(`SELECT r.user_id AS id, COALESCE(NULLIF(r.name, ''), r.username) AS name, r.combat_power, r.realm_index, r.realm_level
             FROM rankings r ORDER BY r.combat_power DESC, r.user_id ASC LIMIT 20`),
      dbGet('SELECT user_id, combat_power, realm_index, realm_level, name, username FROM rankings WHERE user_id = ?', [userId]),
      arenaScoreOf(userId),
      dbGet("SELECT COUNT(*) AS c FROM arena_snapshots WHERE challenger_id = ? AND date = ?", [userId, bjDate(Date.now())]),
    ]);
    const tierIdx = arenaTierIdx(sc.points);
    res.json({
      now: Date.now(),
      top: (top || []).map((x: any, i: number) => ({
        rank: i + 1, id: Number(x.id), userId: Number(x.id), name: String(x.name || ''),
        combatPower: Number(x.combat_power) || 0, combat_power: Number(x.combat_power) || 0,
        realmIndex: Number(x.realm_index) || 0, realmLevel: Number(x.realm_level) || 1,
      })),
      me: {
        id: userId, userId,
        name: String((me && (me.name || me.username)) || ''),
        combatPower: Number(me && me.combat_power) || 0,
        realmIndex: Number(me && me.realm_index) || 0,
        realmLevel: Number(me && me.realm_level) || 1,
        points: sc.points, tier: tierIdx + 1, tierName: ARENA_TIER_NAMES[tierIdx],
        wins: sc.wins, losses: sc.losses,
      },
      snapshotLeft: Math.max(0, ARENA_SNAPSHOT_MAX - (Number(snap && snap.c) || 0)),
      rules: arenaRules(),
    });
  } catch (e: any) { console.error('arena ladder error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// POST /api/arena/snapshot {targetId} — 快照挑战（§3.3 新增 A）：以目标战力镜像为对手立即结算。
//   对方无需在线、不受任何损失（不加其败场、不进其仇人名单），仅收一封战报邮件。
//   次数 5/日；积分只在此与下战书结算时变动（§3.3 新增 B）。
//   ★ R6 防刷两道守卫：① 同一目标每日 1 次（唯一索引 (challenger,target,date) + INSERT OR IGNORE 原子判定）
//     ② 目标战力 < 我方 50% ⇒ 结算但不计积分（防刷小号刷分）。
app.post('/api/arena/snapshot', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `ar:sn:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const targetId = Math.floor(asNum(req.body?.targetId));
    if (!Number.isInteger(targetId) || targetId <= 0) return res.status(400).json({ error: '参数非法' });
    if (targetId === userId) return res.status(400).json({ error: '不能挑战自己' });
    const date = bjDate(Date.now());
    const [cnt, tgt, sc, myCp, myName] = await Promise.all([
      dbGet('SELECT COUNT(*) AS c FROM arena_snapshots WHERE challenger_id = ? AND date = ?', [userId, date]),
      dbGet('SELECT user_id, combat_power, name, username FROM rankings WHERE user_id = ?', [targetId]),
      arenaScoreOf(userId),
      arenaCombatOfUser(userId),
      arenaNameOf(userId),
    ]);
    if (Number(cnt && cnt.c) >= ARENA_SNAPSHOT_MAX) return res.status(409).json({ error: '今日快照挑战次数已用完' });
    if (!tgt) return res.status(404).json({ error: '查无此道友' });
    const targetCp = Number(tgt.combat_power) || 100;
    const opName = String(tgt.name || tgt.username || '无名');
    const out = arenaResolve(myCp, targetCp, myName, opName);
    const won = out.winnerIsMe;
    // 段位对比（越级加成，§5.4）：先取目标积分再定增量
    const tgtSc = await arenaScoreOf(targetId);
    const myTier = arenaTierIdx(sc.points), tgtTier = arenaTierIdx(tgtSc.points);
    let dPoints = won ? (tgtTier > myTier ? ARENA_PT_OVER[myTier] : ARENA_PT_WIN[myTier]) : -ARENA_PT_LOSE[myTier];
    let noPoint = false;
    if (targetCp < myCp * 0.5) { dPoints = 0; noPoint = true; }
    // 原子占位（唯一索引防「同一目标当日重复」；changes=0 ⇒ 今日已打过，且此时尚未结算积分）
    const ins = await dbRun(
      "INSERT OR IGNORE INTO arena_snapshots (challenger_id, target_id, won, date, created_at) VALUES (?, ?, ?, ?, ?)",
      [userId, targetId, won ? 1 : 0, date, Date.now()]);
    if (!ins.changes) return res.status(409).json({ error: '今日已挑战过此道友' });
    const after = await arenaScoreAdd(userId, dPoints, won);
    insertMail(targetId, '快照挑战', '道友「' + myName + '」向你发起快照挑战：' + out.log + '。此为战力镜像战，你无需应战、亦无任何损失。', 'system', 0).catch(() => {});
    const cnt2 = await dbGet('SELECT COUNT(*) AS c FROM arena_snapshots WHERE challenger_id = ? AND date = ?', [userId, date]);
    res.json({
      ok: true, iWon: won, log: out.log, noPoint, pointsDelta: dPoints,
      target: { id: targetId, name: opName, combatPower: targetCp },
      points: after.points, tier: after.tier, tierName: after.tierName,
      snapshotLeft: Math.max(0, ARENA_SNAPSHOT_MAX - (Number(cnt2 && cnt2.c) || 0)),
    });
  } catch (e: any) { console.error('arena snapshot error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});

// POST /api/arena/grudge {targetId} — 恩怨复仇（客户端「恩怨」分栏的「复仇」按钮）。
//   与既有 POST /api/grudge/revenge 同规则（北京 19:00-22:00 窗口 + 同仇人 24h 冷却 + 雪耻播报），
//   仅入参名不同（客户端传 targetId，旧端点传 enemyId）⇒ 本环新增该入口，**不动旧端点**。
app.post('/api/arena/grudge', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `ar:gv:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const h = new Date().getUTCHours();
    if (!(h >= GRUDGE_WINDOW_UTC[0] && h < GRUDGE_WINDOW_UTC[1])) return res.status(409).json({ error: '快意恩仇仅在晚间开放（北京 19:00-22:00）' });
    const enemyId = Math.floor(asNum(req.body?.targetId));
    if (!Number.isInteger(enemyId) || enemyId <= 0) return res.status(400).json({ error: '参数非法' });
    const g = await dbGet('SELECT * FROM grudges WHERE owner_id = ? AND enemy_id = ?', [userId, enemyId]);
    if (!g) return res.status(404).json({ error: '仇人名单中无此人' });
    if (g.last_revenge_at && Date.now() - Number(g.last_revenge_at) < GRUDGE_COOLDOWN_MS) return res.status(409).json({ error: '同一仇人 24 小时内仅可复仇一次' });
    const [myCp, enCp, myName, enName] = await Promise.all([arenaCombatOfUser(userId), arenaCombatOfUser(enemyId), arenaNameOf(userId), arenaNameOf(enemyId)]);
    const out = arenaResolve(myCp, enCp, myName, enName);
    await dbRun('UPDATE grudges SET last_revenge_at = ?, wins = wins + ?, losses = losses + ?, avenged = CASE WHEN ? THEN 1 ELSE avenged END WHERE id = ?',
      [Date.now(), out.winnerIsMe ? 1 : 0, out.winnerIsMe ? 0 : 1, out.winnerIsMe ? 1 : 0, g.id]);
    if (out.winnerIsMe) {
      const mult = await realmMultOf(userId);
      const stones = Math.floor(GRUDGE_STONE_BASE * mult);
      await updatePlayerSave(userId, (sd: any) => {
        sd.player.spiritStones = (Number(sd.player?.spiritStones) || 0) + stones;
      });
      await addScore(userId, { renown: ARENA_RENOWN_WIN });
      logChronicle(userId, myName, '【快意恩仇】「' + myName + '」阵前雪耻，击败「' + enName + '」，恩怨两清');
      insertMail(enemyId, '恩怨了结', '战报：' + out.log + '。江湖恩怨，来日再叙。', 'system', 0).catch(() => {});
      return res.json({ ok: true, iWon: true, stones, log: out.log });
    }
    await addScore(userId, { losses: 1 });
    return res.json({ ok: true, iWon: false, log: out.log });
  } catch (e: any) { console.error('arena grudge error:', e?.message || e); res.status(500).json({ error: '服务器繁忙' }); }
});
// [/t16arena]

"""

C2_NEW = C2_NEW_BODY + C2_ANCHOR

# ─────────────────────────────────────────────────────────
# C3 · /api/arena/my 追加字段（D7：只加不改）
# ─────────────────────────────────────────────────────────
# ★ 锚点只取**单行**（renownTop 行）—— `_assert_anchor_kept` 要求 old 是 new 的**连续子串**；
#   若把 `\n    });` 也放进锚点，插入内容会把它与 renownTop 行隔断 ⇒ 自毁防线误报。
C3_ANCHOR = """      renownTop: (renownTop || []).map((x: any) => ({ id: Number(x.id), name: String(x.name || ''), renown: Number(x.renown) || 0 })),"""

C3_NEW = """      renownTop: (renownTop || []).map((x: any) => ({ id: Number(x.id), name: String(x.name || ''), renown: Number(x.renown) || 0 })),
      // ★ T16（0.8.8）追加字段（D7：**只加不改** —— 上面 6 个既有字段逐字保留，零语义变更）。
      //   客户端新演武场面板读：realmIndex（试炼境界）/ grudges[]（恩怨分栏）/
      //   points·tier·tierName·snapshotLeft（论剑分栏）/ rules（玩法说明动态拼接）。
      ...(await arenaMyExtra(userId)),"""


def _strip_line_comments(s: str) -> str:
    """剥掉每行的 `//` 行注释（与 srv_patch_t5_crops.py 的 `_fc_code` 同款）。

    用途：本环注释会**点名** `daily_quests` / `QUEST_DEFS` / `activityFromQuests`
    这三个「不许碰」的标识符；若按原文计数，门禁会被自己的正文误伤（假 FAIL）。
    """
    return '\n'.join(l.split('//')[0] for l in s.split('\n'))


def _gates(text: str, base: dict, delta: int, gate) -> None:
    """本环门禁（main 与 selftest 共用同一套，避免两处漂移）。"""
    # ── G1~G6 交付门禁：6 个新端点（以 app.METHOD 声明为准，比裸路径更强）──
    eps = [
        ('G1  GET  /api/arena/trials', "app.get('/api/arena/trials', authenticateToken, rateLimit("),
        ('G2  POST /api/arena/trials/fight', "app.post('/api/arena/trials/fight', authenticateToken, rateLimit("),
        ('G3  POST /api/arena/trials/buy', "app.post('/api/arena/trials/buy', authenticateToken, rateLimit("),
        ('G4  GET  /api/arena/ladder', "app.get('/api/arena/ladder', authenticateToken, rateLimit("),
        ('G5  POST /api/arena/snapshot', "app.post('/api/arena/snapshot', authenticateToken, rateLimit("),
        ('G6  POST /api/arena/grudge', "app.post('/api/arena/grudge', authenticateToken, rateLimit("),
    ]
    for label, nd in eps:
        gate('%s 端点恰 1 处（带 authenticateToken + rateLimit）' % label,
             text.count(nd) == 1, '实际 %d' % text.count(nd))
    # 裸路径门禁（任务点名）
    for p in ('/api/arena/trials', '/api/arena/trials/fight', '/api/arena/trials/buy',
              '/api/arena/ladder', '/api/arena/snapshot', '/api/arena/grudge'):
        gate('G6b 裸路径 %s >= 1' % p, text.count(p) >= 1, '实际 %d' % text.count(p))
    # ── G7~G9 坑门禁（本项目四类自毁坑）──
    n_alter = text.count("db.exec('ALTER TABLE") + text.count('db.exec("ALTER TABLE')
    gate('G7 [坑] db.exec(ALTER TABLE …) 直调 == 0', n_alter == 0, '实际 %d' % n_alter)
    n_catch = len(re.findall(r'db\.run\([^\n]*\)\.catch\(', text))
    gate('G8 [坑] db.run(...).catch( == 0', n_catch == 0, '实际 %d' % n_catch)
    gate('G9 [坑] require( == 0（ESM 下未定义）', text.count('require(') == 0, '实际 %d' % text.count('require('))
    # ── G10~G12 幂等 / 注入规模 / 块闭合 ──
    gate('G10 幂等标记就位（重复跑 SKIP）', MARK in text)
    gate('G11 增量字节 ∈ [8000, 40000] B', 8000 <= delta <= 40000, 'delta = %+d B' % delta)
    gate('G12 [t16arena] 块开闭各 1 处',
         text.count('// [t16arena]') == 1 and text.count('// [/t16arena]') == 1)
    # ── G13 4 张新表（建表即带全部列，全 IF NOT EXISTS）──
    for tbl in ('arena_trials', 'arena_scores', 'arena_snapshots', 'arena_trial_daily'):
        nd = 'CREATE TABLE IF NOT EXISTS %s (' % tbl
        gate('G13 新表 %s 建表恰 1 处（IF NOT EXISTS）' % tbl, text.count(nd) == 1, '实际 %d' % text.count(nd))
    gate('G13b 首通部分唯一索引就位',
         text.count('CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_trials_first ON arena_trials(user_id, realm_index, layer) WHERE first_clear = 1') == 1)
    gate('G13c 快照「同一目标每日 1 次」唯一索引就位',
         text.count('CREATE UNIQUE INDEX IF NOT EXISTS idx_arena_snap_once ON arena_snapshots(challenger_id, target_id, date)') == 1)
    # ── G13d T5 修复落点：farm_daily_care.tend_count 幂等迁移（禁裸 ALTER）──
    gate('G13d farm_daily_care.tend_count 走 safeAddColumn（幂等加列）',
         text.count("safeAddColumn('farm_daily_care', 'tend_count', 'ALTER TABLE farm_daily_care ADD COLUMN tend_count INTEGER NOT NULL DEFAULT 0');") == 1,
         '实际 %d' % text.count("safeAddColumn('farm_daily_care', 'tend_count',"))
    gate('G13e farm_daily_care 加列带 PRAGMA 快路径守卫（禁裸 ALTER）',
         text.count('db.all("PRAGMA table_info(farm_daily_care)"') == 1
         and text.count("db.exec('ALTER TABLE farm_daily_care") == 0)
    # ── G14 /arena/my 只加不改 ──
    gate('G14 /arena/my 追加字段（spread arenaMyExtra）', text.count('...(await arenaMyExtra(userId)),') == 1)
    for keep in ("incoming: (incoming || []).map((x: any) => ({ id: Number(x.id), name: String(x.name || x.uname || '') })),",
                 "score: { renown: Number(score?.renown) || 0, virtue: Number(score?.virtue) || 0, wins: Number(score?.wins) || 0, losses: Number(score?.losses) || 0 },"):
        gate('G14b /arena/my 既有字段逐字保留', text.count(keep) == 1, '实际 %d' % text.count(keep))
    # ── G15 活跃度零埋点（T16 §6.4：与 T9 的边界）──
    #   ★ 纪律：本环注释里会**点名**这三处标识符（写清「不许碰什么」），
    #     故计数必须**剥掉 `//` 行注释**再数 —— 否则门禁被自己的正文误伤（假 FAIL）。
    #     （与 srv_patch_t5_crops.py 的 `_fc_code` 同款处置。）
    _nc = _strip_line_comments(text)
    gate('G15a [T9 边界] 未新增活跃度埋点表写入（剥注释后计数 == 基线）',
         _nc.count('daily_quests') == base['daily_quests'],
         '实际 %d（基线 %d）' % (_nc.count('daily_quests'), base['daily_quests']))
    gate('G15b [T9 边界] 未新增任务定义条目（剥注释后计数 == 基线）',
         _nc.count('QUEST_DEFS') == base['QUEST_DEFS'],
         '实际 %d（基线 %d）' % (_nc.count('QUEST_DEFS'), base['QUEST_DEFS']))
    gate('G15c [T9 边界] 未碰宝箱校验的活跃度读取点（剥注释后计数 == 基线）',
         _nc.count('activityFromQuests') == base['activityFromQuests'],
         '实际 %d（基线 %d）' % (_nc.count('activityFromQuests'), base['activityFromQuests']))
    gate('G15d 演武场侧无任何活跃度埋点调用（bumpArenaQuest 等）',
         'bumpArenaQuest' not in text and 'upsertDailyQuest' not in text)
    # ── G16 存量擂台零改动（D7）──
    gate('G16a arena_battles 建表串逐字未动',
         text.count('CREATE TABLE IF NOT EXISTS arena_battles (') == 1
         and text.count('idx_arena_cha ON arena_battles(challenger_id, status)') == 1
         and text.count('idx_arena_def ON arena_battles(defender_id, status)') == 1)
    gate('G16b 4 个既有 arena 端点语义未动',
         text.count("app.post('/api/arena/challenge', authenticateToken") == 1
         and text.count("app.get('/api/arena/my', authenticateToken") == 1
         and text.count("app.post('/api/arena/accept', authenticateToken") == 1
         and text.count("app.post('/api/arena/decline', authenticateToken") == 1)
    gate('G16c 既有擂台常量未动（DAILY_MAX / RENOWN_WIN / STONE_BASE）',
         text.count('const ARENA_DAILY_MAX = 3;') == 1
         and text.count('const ARENA_RENOWN_WIN = 10;') == 1
         and text.count('const ARENA_STONE_BASE = 3000;') == 1)
    gate('G16d 恩怨旧端点未动（grudge/list + grudge/revenge）',
         text.count("app.get('/api/grudge/list', authenticateToken") == 1
         and text.count("app.post('/api/grudge/revenge', authenticateToken") == 1)
    gate('G16e 日切基准未动（utcDayStartMs 计数不变；北京口径已由前环落地）',
         text.count('utcDayStartMs') == base['utcDayStartMs'], '实际 %d（基线 %d）' % (text.count('utcDayStartMs'), base['utcDayStartMs']))
    gate('G16f 业务拒绝零 403（客户端把 403 当会话失效强制登出）',
         text.count('res.status(403') == base['res.status(403'], '实际 %d（基线 %d）' % (text.count('res.status(403'), base['res.status(403']))
    # ── G17 规格常量与整数式（§5.1/§5.2/§5.3/§5.4）──
    gate('G17a 段位门槛 7 段逐字',
         text.count('const ARENA_TIER_CUTS = [0, 100, 300, 600, 1000, 1500, 2100];') == 1)
    gate('G17b 段位名 7 名逐字', text.count("const ARENA_TIER_NAMES = ['凡铁境', '青锋境', '银锋境', '金锋境', '玄锋境', '化虚境', '太虚境'];") == 1)
    gate('G17c 积分三表逐字（胜/越级/负）',
         text.count('const ARENA_PT_WIN = [12, 12, 12, 14, 14, 16, 16];') == 1
         and text.count('const ARENA_PT_OVER = [18, 18, 18, 21, 21, 24, 24];') == 1
         and text.count('const ARENA_PT_LOSE = [5, 5, 5, 6, 6, 7, 7];') == 1)
    gate('G17d 免费 5 / 买 2 / 快照 5 / 9 层 / 精英 3-6-9',
         text.count('const ARENA_TRIAL_FREE = 5;') == 1 and text.count('const ARENA_TRIAL_BUY_MAX = 2;') == 1
         and text.count('const ARENA_SNAPSHOT_MAX = 5;') == 1 and text.count('const ARENA_TRIAL_LAYERS = 9;') == 1
         and text.count('const ARENA_TRIAL_ELITE = [3, 6, 9];') == 1)
    gate('G17e 敌人强度整数式 f(layer)=135×(100+16×(layer-1))/10000',
         text.count('const fn = 135 * (100 + 16 * (layer - 1));') == 1 and text.count('Math.floor(v * fn / 10000)') == 1)
    gate('G17f 单次胜利整数百分比式',
         text.count('Math.floor(150 * arenaM(realmIdx) * (100 + 8 * (layer - 1)) / 100)') == 1)
    gate('G17g 首通先乘后 floor（精英 ×1.5 不提前 floor）', text.count('Math.floor(raw * 3 / 2)') == 1)
    gate('G17h 修为槽整数式（不复用浮点式 realmMaxExp）',
         text.count('Math.floor(base * (100 + 24 * (layer - 1)) / 100)') == 1)
    gate('G17i 首通修为整数式', text.count('Math.floor(raw * 3 / 200)') == 1 and text.count('Math.floor(raw / 100)') == 1)
    gate('G17j 购买价整数式 floor(2000×(nth+1)×M)',
         text.count('Math.floor(2000 * (nth + 1) * arenaM(realmIdx))') == 1)
    # ── G18 规则与关键行为 ──
    gate('G18a 失败不扣次数（只有 won=1 计次）',
         text.count("WHERE user_id = ? AND date = ? AND won = 1") == 1)
    gate('G18b 日切用北京日串 bjDate(Date.now())', text.count('bjDate(Date.now())') >= 4)
    gate('G18c 层解锁守卫（第 k 层需第 k-1 层已首通）', text.count("if (layer > 1 && !prevClear) return res.status(409).json({ error: '请先通关上一层' });") == 1)
    gate('G18d 境界解锁守卫', text.count("if (realmIndex > myRealm) return res.status(409).json({ error: '境界不足，尚不可挑战此关' });") == 1)
    gate('G18e 积分下限 0（不为负）', text.count('Math.max(0, cur.points + Math.floor(Number(dPoints) || 0))') == 1)
    gate('G18f 快照越级加成 + 防刷守卫齐备',
         text.count('tgtTier > myTier ? ARENA_PT_OVER[myTier] : ARENA_PT_WIN[myTier]') == 1
         and text.count('if (targetCp < myCp * 0.5) { dPoints = 0; noPoint = true; }') == 1
         and text.count("if (!ins.changes) return res.status(409).json({ error: '今日已挑战过此道友' });") == 1)
    gate('G18g 复仇沿用存量窗口/冷却常量（不动 GRUDGE_*）',
         text.count('const GRUDGE_WINDOW_UTC = [11, 14];') == 1 and text.count('const GRUDGE_COOLDOWN_MS = 24 * 3600 * 1000;') == 1)
    gate('G18h 复仇复用 arenaResolve（不新造第二套判定）',
         text.count('const out = arenaResolve(myCp, enCp, myName, enName);') == 1)
    gate('G18i 试炼战斗复用 arenaResolve',
         text.count('const out = arenaResolve(myCp, arenaCombatOfStats(stats), myName, opName);') == 1)
    # ── G19 孤儿检测：注入块内声明的每个名字都必须有消费者 ──
    #   ★ 计数域 = **整个产物**（不是块内切片）：C3 的消费者 `arenaMyExtra` 落在
    #     /api/arena/my（块外）⇒ 只数块内会把「声明 + 块外唯一消费者」误判为孤儿。
    #   ★ 用 `\b` 词边界：`arenaM` 是 `arenaMyExtra` 的子串，裸 count 会互相污染。
    blk = _block(text, '// [t16arena]', '// [/t16arena]')
    names = set(re.findall(r'(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=', blk))
    names |= set(re.findall(r'function\s+([A-Za-z_$][\w$]*)\s*\(', blk))
    orphans = sorted(n for n in names if len(re.findall(r'\b' + re.escape(n) + r'\b', text)) < 2)
    gate('G19 注入块内无孤儿声明（每个 const/let/function 在产物中至少 2 次出现）',
         not orphans, 'orphans=%s 声明数=%d' % (orphans or '[]', len(names)))
    # ── G20 基线锚点未动（只做加法）──
    gate('G20a C1 锚点行仍在（idx_arena_cha）', text.count(C1_ANCHOR) == 1)
    gate('G20b C2 锚点行仍在（师徒传功段注释）', text.count(C2_ANCHOR) == 1)
    gate('G20c C3 锚点行仍在（renownTop 行）', text.count('      renownTop: (renownTop || []).map((x: any) => ({ id: Number(x.id), name: String(x.name || \'\'), renown: Number(x.renown) || 0 })),') == 1)
    gate('G20d 前 19 环关键锚点未丢（safeAddColumn / settleSaveEconV2 / farmCropDefs / T2 灵宠端点）',
         text.count('const safeAddColumn = (table: string, col: string, ddl: string) => {') == 1
         and text.count('function settleSaveEconV2') == 1
         and text.count('function farmCropDefs(') == 1
         and text.count("app.get('/api/pet/spirit/list', authenticateToken") == 1)
    # ── G21 入参收口 ──
    gate('G21 入参收口 asNum + Number.isInteger',
         text.count('Math.floor(asNum(req.body?.realmIndex))') == 1
         and text.count('Math.floor(asNum(req.body?.layer))') == 1
         and text.count('Math.floor(asNum(req.body?.targetId))') == 2)


def selftest() -> int:
    print('0.8.8 T16 演武场环（链第 20 环）— 自证')
    gates = []
    ok = True

    def gate(name, cond, detail=''):
        nonlocal ok
        gates.append((name, bool(cond), detail))
        if not cond:
            ok = False

    cand = os.path.join(HERE, '_chainstage', 's19.t2spirit.ts')
    if not os.path.isfile(cand):
        cand = os.path.join(HERE, 'srv', 'index_v28.ts')
    if not os.path.isfile(cand):
        print('  [FAIL] 找不到上一环产物')
        return 1

    src = open(cand, encoding='utf-8').read()
    print('  上一环产物 : %s  bytes=%d md5=%s'
          % (os.path.basename(cand), len(src.encode('utf-8')), md5s(src)))

    if MARK in src:
        print('  [SKIP] 已含 %s 标记' % MARK)
        return 0

    for tag, anc in (('C1', C1_ANCHOR), ('C2', C2_ANCHOR), ('C3', C3_ANCHOR)):
        if src.count(anc) != 1:
            print('  [FAIL] 前置守卫 %s 锚点命中 %d 次（期望 1）' % (tag, src.count(anc)))
            return 1
    print('  [OK]   前置守卫：C1/C2/C3 锚点各命中 1 次')

    _assert_anchor_kept('C1', C1_ANCHOR, C1_NEW)
    _assert_anchor_kept('C2', C2_ANCHOR, C2_NEW)
    _assert_anchor_kept('C3', C3_ANCHOR, C3_NEW)

    out = apply_one(src, 'C1', C1_ANCHOR, C1_NEW)
    out = apply_one(out, 'C2', C2_ANCHOR, C2_NEW)
    out = apply_one(out, 'C3', C3_ANCHOR, C3_NEW)

    delta = len(out.encode('utf-8')) - len(src.encode('utf-8'))
    base = _base_counts(src)
    gates2 = []

    def gate2(name, cond, detail=''):
        gates2.append((name, bool(cond), detail))

    _gates(out, base, delta, gate2)
    for n, c, d in gates2:
        gate(n, c, d)

    print('\n  --- 门禁 ---')
    for name, c, detail in gates:
        print('  [%s] %s%s' % ('OK' if c else 'FAIL', name, ('  ' + detail) if detail else ''))
    print('\n  自证结果：%s' % ('全 PASS' if ok else '存在 FAIL'))
    return 0 if ok else 1


def _base_counts(src: str) -> dict:
    """基线计数（只加不改类断言用；从**上一环产物**取，不从记忆里写死）。

    ★ 三处「T9 边界」标识符按**剥注释后**计数（与 _gates 内同口径，否则基线/实测不可比）。
    """
    nc = _strip_line_comments(src)
    return {
        'daily_quests': nc.count('daily_quests'),
        'QUEST_DEFS': nc.count('QUEST_DEFS'),
        'activityFromQuests': nc.count('activityFromQuests'),
        'utcDayStartMs': src.count('utcDayStartMs'),
        'res.status(403': src.count('res.status(403'),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='0.8.8 T16 演武场环（链第 20 环 / 新末环）')
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
    print('0.8.8 T16 演武场环（链第 20 环 / 新末环）')
    print('  source : %s  bytes=%d md5=%s' % (src, before_bytes, md5s(text)))

    if MARK in text:
        print('  [SKIP] 已包含 %s 标记，无需重复打补丁' % MARK)
        return 0

    for tag, anc in (('C1', C1_ANCHOR), ('C2', C2_ANCHOR), ('C3', C3_ANCHOR)):
        if text.count(anc) != 1:
            die('前置守卫失败：%s 锚点命中 %d 次（期望 1）—— 基线不符' % (tag, text.count(anc)))
    print('  [OK]   前置守卫：C1/C2/C3 锚点各命中 1 次')

    _assert_anchor_kept('C1', C1_ANCHOR, C1_NEW)
    _assert_anchor_kept('C2', C2_ANCHOR, C2_NEW)
    _assert_anchor_kept('C3', C3_ANCHOR, C3_NEW)

    base = _base_counts(text)
    text = apply_one(text, 'C1', C1_ANCHOR, C1_NEW)
    text = apply_one(text, 'C2', C2_ANCHOR, C2_NEW)
    text = apply_one(text, 'C3', C3_ANCHOR, C3_NEW)

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
        bak = '%s.bak-t16arena-%s' % (src, time.strftime('%Y%m%d-%H%M%S'))
        shutil.copy2(src, bak)
        print('\n  [备份] %s' % bak)
        open(src, 'wb').write(text.encode('utf-8'))
        print('  [写出] %s  bytes=%d  md5=%s' % (src, len(text.encode('utf-8')), md5s(text)))

    print('  [PASS] T16 演武场服务端能力落地（delta %+d B）' % delta)
    return 0


if __name__ == '__main__':
    sys.exit(main())
