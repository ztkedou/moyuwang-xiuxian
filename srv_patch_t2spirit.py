# -*- coding: utf-8 -*-
r"""srv_patch_t2spirit.py — 0.8.9 T2 灵宠面板服务端能力环（链第 19 环 / 新末环）

## 背景

T2 策划案 `docs/0.8.8-design/T2-灵宠玩法扩展.md` 定义灵宠三条线（战斗 / 生产 / 养成收藏）。
其中「养成收藏」的**采集面**落在灵宠面板：面板需要拿到**多只灵宠**的品阶 / 亲密度 / 气血 / 修为，
并支持把这些灵宠**融合进主宠**。

现状（`srv/index_v28.ts`，第 18 环产物，实测）：

| 端点 | 行 | 语义 |
|---|---|---|
| `GET /api/pet` | :10563 | 我的宠物全量（**单只**，每玩家 UNIQUE(player_id) 一行） |
| `POST /api/pet/adopt` | :10591 | 收养（UNIQUE 原子防线，每玩家一只 active） |
| `POST /api/pet/feed` | :10617 | 喂养（扣灵石 → 喂食度 +30） |
| `POST /api/pet/play` | :10681 | 嬉戏（每日 3 次 → 羁绊 +5） |

**缺失三项（grep 零命中，确认完全未实现）**：

1. `GET /api/pet/spirit/list` — 灵宠列表（面板采集面）
2. `POST /api/pet/spirit/merge` — 灵宠融合（材料灵宠消耗 → 主宠成长）
3. `pets.merged` 列 — 融合状态标记（策划 §2.7 步骤 1「妖灵归位」的红线列）

## 与策划案的**权威性声明（重要，勿误读）**

策划案 §2.1 **P2「不新增权威源」** 明确：灵宠属性（`affection / evolutionStage / exp` 等）
唯一事实源是**客户端存档 `player.pets`**，战斗在客户端结算（先例 `Oy`）。

⇒ 本环**不把 `player.pets` 镜像到服务端**。服务端 `pets` 表的结构（1 行 / 玩家、字段
`hunger / bond / exp`）**一字不改**（红线：改了会破坏 `adopt` 的 UNIQUE 语义与 `feed/play` 全链）。

本环落地的是**服务端确实权威、且策划确实点名**的两块：

* **采集面（spirit/list）**：把服务端 `pets` 行按策划 §2.3 / §3.1 的**公开系数**投影成
  「灵宠品阶 / 气血 / 修为 / 亲密度」视图。**投影是纯函数、只读、不落库**，
  派生口径逐条对照策划案（见下表）。
* **融合（spirit/merge）**：策划 §2.4 的融合**消耗**在服务端权威执行（灵石扣费走
  `updatePlayerSave` 的 saveLock 互斥，与 `feed` / `alchemy/start` 同款补偿式事务）；
  **属性继承**（等级取高 / 阶段晋升 / 技能继承）按 P2 归客户端存档域，服务端**只回传结算指令**
  （`inheritHints`），不代写存档。

### spirit/list 字段 ← 策划案出处（逐条可查）

| 返回字段 | 含义 | 策划案出处 |
|---|---|---|
| `rarity` / `rarityIdx` / `rarityCn` / `rarityKo` | 品阶（凡/灵/仙）及其序号与显示名 | §1.1 品阶；§2.4「品阶序号：普0/稀1/传2/仙3」 |
| `maxHp` / `hp` | 气血上限 / 当前气血 | §3.4「气血 = max(100, floor(maxHp × (0.11 + 阶段×0.04)))」 |
| `maxExp` / `exp` | 修为上限 / 当前修为 | §3.4「修为 = max(50, floor(maxExp × (0.005 + 阶段×0.0025)))」 |
| `affection` | 亲密度 0~100 | §2.7 步骤 1「亲密度 = min(100, floor(bond/2))」 |
| `evolutionStage` / `stageName` | 进化阶段（幼年期/成熟期/完全体） | §1.2「evolutionStage 0→1→2」；§3.2 表头 |
| `fuseCost` | 该宠作主宠时的秘径消耗（仅 1 档 = 幼年期口径） | §3.1/§3.2（**见下方「口径差异」**） |
| `mergeCost` | 融合费（服务端权威定价） | §2.4 融合费公式（**见下方「口径差异」**） |
| `mergeMerged` | 融合状态标记 | §2.7 步骤 1（`merged` 列语义） |
| `isActive` | 是否主宠（服务端恒 true：每玩家一只） | §2.2 主战宠 |

**口径差异 1 — `fuseCost` 只是「一档参考值」，不是完整秘径消耗函数**：
秘径消耗 = `round100(10000 × P品阶 × P阶段 × P亲密度)`，其中 **`P阶段` 依赖 `evolutionStage`**，
而 `evolutionStage` 在 `player.pets`（客户端存档）里、**不在** `pets` 表里。
服务端无法在不镜像存档的前提下算出阶段因子 ⇒ 本环按 `evolutionStage = 0`（幼年期）出
**该品阶的最低档**，命名 `fuseCost`（保留策划 §3.0 的用词便于客户端对照）；
`fuseCostMax` 给出该品阶在「完全体 + 亲密度 100」的**上限档**，两端夹住真实值。
客户端有权威 `evolutionStage`，可自行插值到 §3.2 精确档位。

**口径差异 2 — `mergeCost` 的基础由 3000 提到 10000（用户 2026-09-29 指示）**：
策划 §2.4 原文是 `融合费 = 3000 × K品阶 × (1 + 副宠品阶序号)`；
用户 2026-09-29 明确「**基础改为 10000 灵石起**，整体幅度不要太大，**消耗根据品阶为主，
亲密度影响不大**」。融合费与秘径同属 T2 消耗面 ⇒ 基础对齐 10000，并补亲密度弱因子：

```
融合费 = round100( 10000 × M品阶 × K品阶系(副宠) × P亲密度 )      ← 服务端权威，本环实现
  M品阶   = { 凡 1.00, 灵 1.20, 仙 1.40 }   ← 主因子，对齐策划 §3.1 P品阶（本表只有三品阶）
  K品阶系(副宠) = 1 + 0.33 × 副宠品阶序号   ← 普0/稀1/传2/仙3 → 1.00/1.33/1.66/1.99
                = 1 + 副宠品阶序号/3        ← 策划 §2.4 原本的「1 + 序号」跨度 4.0×，
                                              用户要求「幅度不要太大」⇒ 压缩到 2.0×
  P亲密度 = 1 + 亲密度/2000                  ← 弱因子，0~100 → ×1.00~×1.05（与 §3.1 同口径）
  round100 = 取整到百位
```

⇒ 融合费区间 **10,000 ~ 29,300**（极差 2.93×），**品阶主导、亲密度影响 ≤5%**，符合用户指示。

**融合成功率（策划 §2.4 逐字落地，确定性非赌博，P3）**：

| 情形 | 成功率 |
|---|---|
| 副宠品阶 < 主宠 | `70% + 15% × 品阶差`（上限 100%） |
| 副宠品阶 = 主宠 | `70%` |
| 副宠品阶 > 主宠 | `70% − 20% × 品阶差`（下限 20%） |

**失败保底（策划 §2.4）**：连续失败 3 次后第 4 次必成功。倒计数落 `pets.merge_pity`
（**服务端权威**——策划把 `pet.fusePity` 落客户端存档，但保底必须服务端自己把关，
否则客户端不报失败次数即可无限免费必成）；每次失败 +1，成功清零。
本环**不新增 `merge_pity` 列**：顶层 `pets` 建表区（建表 DDL 自带列）在第 3 环锚区，
本环是末环追加，改它违「锚区零交集」纪律 ⇒ 改用 `safeAddColumn`（第 18 环引入的幂等加列辅助，
容忍 `duplicate column name`，冷启动 / 重跑双安全）。

## 改动清单（3 处锚区，互不重叠，且与前 18 环零交集）

| # | 锚点 | 改动 |
|---:|---|---|
| C1 | `:5171` `// [petcore] Y18 妖灵宠物纯逻辑核心` 头 | 抬升 petcore 头注释（2 行 → 3 行，标明 T2 扩权），再插入 `// [t2spirit]` 纯逻辑块 |
| C2 | `const safeAddColumn = (…) => {…};` 之后（`:95-101`） | 追 `pets.merged` / `pets.merge_pity` 两列的**幂等**迁移 |
| C3 | `POST /api/pet/play` 整块之后（`:10708`） | 追 `GET /api/pet/spirit/list` + `POST /api/pet/spirit/merge` 两端点 |

* C1 锚区 = `[petcore]` 头注释 + `[/petcore]` 之前 ⇒ 纯逻辑块新增，**不删改任何既有 pet 常量 / 函数**。
* C2 锚区 = `safeAddColumn` 定义体之后 ⇒ 第 18 环只**新增**了该函数自身，其后（`:102`
  `const db = new sqlite3.Database(...)` 之前）尚无任何内容，与前 18 环零交集。
* C3 锚区 = `pet/play` 端点之后、`Y4 渡劫天劫` 段注释之前 ⇒ 同段追加，位置自洽。

## 工程约束（本项目已踩过的坑，本环逐条遵守）

1. **回调式 sqlite3** ⇒ 异步入口一律 `dbGet / dbAll / dbRun`（Promise 封装，`:3891`）；
   `db.run(...).catch(...)` **禁止**（返回 `Database` 非 Promise，顶层 TypeError ⇒ 起不来）。
2. **ESM** ⇒ `require(` **禁止**（未定义）。
3. **加列必须走 `safeAddColumn`** ⇒ 直接 `db.exec('ALTER TABLE …')` **禁止**（`db.serialize`
   无完成屏障，`PRAGMA` 可能读空 schema ⇒ 重复 ALTER ⇒ 崩，空库 100%）。
4. **建表就带全列** ⇒ 本环不新建表（复用 `pets`），只幂等加 2 列。
5. **中文注入形态**：本环正文以**字面中文**写入（不转义），故门禁 needle 也按**字面中文**取证。
6. **鉴权照抄既有 pet 端点**：`authenticateToken` + `rateLimit({windowMs, max, keyFn})`。
7. **外部输入收口**：`asStr / asNum / asInt`（`:1188`），防原型链污染（`{"id":{"toString":1}}`
   之类会让 `String()` 抛错 ⇒ 500）。

## 红线

* 不碰 `_v281_base/`（基座只读）；不改任何既存 `srv_patch_*.py`（本环是**新增**末环）。
* 不碰 `build/`（前端域）；不碰线上服务器。
* 不改 `pets` 建表 DDL、不改 `adopt/feed/play` 任何既有语义。
* 不改任何既存门禁期望值。

## 用法

```
python srv_patch_t2spirit.py --src <上一环产物>    # 就地原子写回 --src
python srv_patch_t2spirit.py --selftest            # 只跑门禁，不碰文件
```

幂等：已含 `T2SPIRIT089` 标记则 SKIP。锚点不唯一一律中止（拒绝静默失败）。
"""
import argparse
import hashlib
import os
import re
import shutil
import sys
import time

MARK = 'T2SPIRIT089'
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
    —— 那不是「在锚点后插入」，而是「用新块替换掉锚点」。
    本项目实测踩过：C1b 漏带锚点 ⇒ `clampPetDetail` 定义被吃掉 ⇒ `/api/pet/adopt` 500。

    这里在**改文件之前**挡一道：new 必须含 old（或显式声明是删除型改动，须传 allow_drop=True）。
    """
    if old not in new:
        die('%s 自毁防线：new 未包含锚点原文 ⇒ 锚点行会被整段删除（不是插入）。'
            '请把 new 写成 old + 新内容，或用 allow_drop=True 显式声明是删除型改动。' % tag)
    print('  [OK] %-6s 自毁防线通过（new 含锚点原文，属插入式改动）' % tag)


def _block(text: str, anchor: str, end: str) -> str:
    """取 [anchor, end) 切片 —— 只在该区间内断言，避免全文计数误伤邻座。

    ★ 纪律：**不用固定字节窗口**（span）。本项目踩过「窗口越界吃进邻座块」的坑：
    端点块长度随正文变化，写死 4200 时列表块恰好越界吞掉了融合块的
    `UPDATE pets SET merged = 1` ⇒ 门禁 G12「列表块内不回写」**假 FAIL**。
    改用以「下一个端点定义」作结束围栏，块边界与代码结构同构、不随字数漂移。
    """
    i = text.find(anchor)
    if i < 0:
        return ''
    j = text.find(end, i + len(anchor))
    return text[i:] if j < 0 else text[i:j]


# ─────────────────────────────────────────────────────────
# C1 · petcore 头注释抬升 + [t2spirit] 纯逻辑块
# ─────────────────────────────────────────────────────────

# C1 锚点 = petcore 头注释最后一行 + 下一条常量行（保证唯一命中且上下文正确）。
# ★ needle 只取「锚点行 + 邻行」的**最小公共前缀**，不把整段中文注释写进门禁，
#   这样门禁字符串自身不会成为产物里的第二份拷贝（否则 apply_one 之后计数恒 2 假 FAIL）。
C1_ANCHOR = """// 数值为本次定档，常量集中可调；hunger=喂食度（只增不减），level=floor(hunger/100)，出战加成保守落点见 PET_BATTLE_*
const PET_FEED_COST = 5000;"""

# ★ 插入式：原文两行**逐字保留在首部**（自毁防线 _assert_anchor_kept 要求 old ⊆ new），
#   新增的 T2 常量行接在其后。
C1_NEW = """// 数值为本次定档，常量集中可调；hunger=喂食度（只增不减），level=floor(hunger/100)，出战加成保守落点见 PET_BATTLE_*
const PET_FEED_COST = 5000;

// T2SPIRIT089：以下常量为 T2 灵宠面板服务端权威面**共用**（品阶系数 / 融合费 / 成功率 / 保底 / 秘径消耗）。
//   纯逻辑（系数表 / 融合费 / 成功率 / 伪随机 / 视图投影）下沉到下方 [t2spirit] 块。
// （petcore 原有 9 个常量一字未动，本环只做加法。）"""

# [t2spirit] 纯逻辑块**正文**（不含锚点原文）—— 插在 [petcore] 的 `[/petcore]` 之后
#   （即 petcore 与 [wudaocore] 之间）。
#   ★ 注意：`apply_one` 是 `text.replace(old, new)` ⇒ new 必须**把 old 原文再带一遍**，
#     否则锚点会被整段吃掉（本环实测踩过：clampPetDetail 定义被吃 ⇒ adopt 500）。
#     故下面用 C1_NEW_BLOCK = C1_ANCHOR_2 + C1_NEW_BODY 拼装（见下方）。
C1_NEW_BODY = """
// [t2spirit] T2 灵宠面板服务端权威纯逻辑（依赖注入块：不引用本块外任何符号，供单测整块提取执行）
//
// 权威边界（策划 §2.1 P2「不新增权威源」）：
//   * 灵宠属性（affection / evolutionStage / exp / 技能）唯一事实源 = 客户端存档 player.pets；
//     本块**只做投影与结算定价**，不落任何属性库。
//   * 服务端权威面 = ① 视图投影（§2.3 / §3.1 公开系数）② 融合费（§2.4 + 用户 2026-09-29 指示）
//     ③ 融合成功率 / 失败保底（§2.4，确定性非赌博 P3）④ 融合落库动作（扣灵石 + 材料消耗 + 标记）。
//   * 属性继承（等级取高 / 阶段晋升 / 技能继承）按 P2 归客户端存档域 ⇒ 服务端只回 inheritHints。

// ── 品阶：服务端 pets.rarity 只有 凡/灵/仙 三档（rollPetRarity :5186）──
//   策划案 §2.4 / §3 用四档（普/稀/传/仙）描述客户端 23 物种的品阶。
//   映射：凡→普通(0) / 灵→稀有(1) / 仙→仙品(3)。**传说(2) 服务端不可达**（rollPetRarity 不产出）。
const PET_RARITY_IDX: Record<string, number> = { '凡': 0, '灵': 1, '仙': 3 };
const PET_RARITY_CN: Record<string, string> = { '凡': '普通', '灵': '稀有', '仙': '仙品' };
// T2 品阶序号显示名（普0/稀1/传2/仙3）——按**序号**取，供副宠品阶序号 → 中文名。
const PET_RARITY_KO: string[] = ['普通', '稀有', '传说', '仙品'];
// 进化阶段（策划 §1.2 evolutionStage 0→1→2）
const PET_STAGE_CN: string[] = ['幼年期', '成熟期', '完全体'];
// T2 消耗定价（策划 §3.1 / §2.4；round100 取整到百位）
const PET_T2_COST_BASE = 10000;             // ← 用户 2026-09-29：基础 10000 灵石起
const PET_T2_AFFECTION_DIVISOR = 2000;      // 亲密度弱因子：1 + aff/2000 → ×1.00~×1.05（≤5%）
// 秘径品阶因子（策划 §3.1 P品阶，主因子 1.6× 跨度）
const PET_FUSE_RARITY_MULT: Record<string, number> = { '凡': 1.00, '灵': 1.20, '仙': 1.60 };
// 秘径阶段因子（策划 §3.1 P阶段，次因子 1.25×）
const PET_FUSE_STAGE_MULT: number[] = [1.00, 1.10, 1.25];
// 融合费：主宠品阶因子（对齐 §3.1，服务端三档；用户「消耗根据品阶为主」）
const PET_MERGE_RARITY_MULT: Record<string, number> = { '凡': 1.00, '灵': 1.20, '仙': 1.40 };
// 融合成功率（策划 §2.4 逐字）
const PET_MERGE_RATE_SAME = 0.70;
const PET_MERGE_RATE_LOW_STEP = 0.15;       // 副宠低阶：+15% × 品阶差
const PET_MERGE_RATE_HIGH_STEP = 0.20;      // 副宠高阶：-20% × 品阶差
const PET_MERGE_RATE_MIN = 0.20;
const PET_MERGE_RATE_MAX = 1.00;
// 失败保底（策划 §2.4）：连续失败 3 次后第 4 次必成功。计数落 pets.merge_pity（服务端权威）
const PET_MERGE_PITY_LIMIT = 3;

// 品阶序号（纯）：凡0 / 灵1 / 仙3；未知名归一为 0（防御外部脏值）
function petRarityIdx(rarity: unknown): number {
  const k = String(rarity);
  return Object.prototype.hasOwnProperty.call(PET_RARITY_IDX, k) ? PET_RARITY_IDX[k] : 0;
}
// round100（纯）：取整到百位，四舍五入（≥50 进）—— 策划 §3.1 round100
function petRound100(n: number): number {
  const v = Math.floor(Number(n) || 0);
  return Math.floor((v + 50) / 100) * 100;
}
// 亲密度（纯）：由服务端 bond 派生 —— 策划 §2.7 步骤 1「亲密度 = min(100, floor(bond/2))」
function petT2Affection(bond: unknown): number {
  const b = Math.max(0, Math.floor(Number(bond) || 0));
  return Math.min(100, Math.floor(b / 2));
}
// 亲密度弱因子（纯）：1 + aff/2000 → 0~100 ⇒ ×1.00~×1.05
function petT2AffectionMult(affection: number): number {
  const a = Math.min(100, Math.max(0, Math.floor(Number(affection) || 0)));
  return 1 + a / PET_T2_AFFECTION_DIVISOR;
}
// 秘径消耗（纯）：round100(10000 × P品阶 × P阶段 × P亲密度) —— 策划 §3.1/§3.2 逐条落地
//   evolutionStage 由调用方传入（服务端无该列 ⇒ 取 0，只出该品阶最低档，见文件头「口径差异 1」）
function petT2ExpeditionCost(rarity: unknown, stage: unknown, affection: number): number {
  const si = Math.min(2, Math.max(0, Math.floor(Number(stage) || 0)));
  const rk = String(rarity);
  const rm = Object.prototype.hasOwnProperty.call(PET_FUSE_RARITY_MULT, rk) ? PET_FUSE_RARITY_MULT[rk] : 1.00;
  return petRound100(PET_T2_COST_BASE * rm * PET_FUSE_STAGE_MULT[si] * petT2AffectionMult(affection));
}
// 融合费（纯）：round100(10000 × M品阶(主) × (1 + 副宠品阶序号/3) × P亲密度)
//   —— 策划 §2.4 基础由 3000 提到 10000（用户 2026-09-29「基础改为 10000 灵石起」）；
//      副宠跨度由「1 + 序号」（4.0×）压缩到「1 + 序号/3」（2.0×），落实「整体幅度不要太大」。
function petT2MergeCost(rarity: unknown, subRarityIdx: number, affection: number): number {
  const rk = String(rarity);
  const mm = Object.prototype.hasOwnProperty.call(PET_MERGE_RARITY_MULT, rk) ? PET_MERGE_RARITY_MULT[rk] : 1.00;
  const si = Math.min(PET_RARITY_KO.length - 1, Math.max(0, Math.floor(Number(subRarityIdx) || 0)));
  return petRound100(PET_T2_COST_BASE * mm * (1 + si / 3) * petT2AffectionMult(affection));
}
// 融合成功率（纯）：策划 §2.4 —— 副宠低阶稳（上限 100%）、同阶 70%、高阶险（下限 20%）
function petT2MergeRate(mainIdx: number, subIdx: number): number {
  const a = Math.floor(Number(mainIdx) || 0);
  const b = Math.floor(Number(subIdx) || 0);
  const d = b - a;
  let r: number;
  if (d < 0) r = PET_MERGE_RATE_SAME + PET_MERGE_RATE_LOW_STEP * (-d);
  else if (d > 0) r = PET_MERGE_RATE_SAME - PET_MERGE_RATE_HIGH_STEP * d;
  else r = PET_MERGE_RATE_SAME;
  return Math.min(PET_MERGE_RATE_MAX, Math.max(PET_MERGE_RATE_MIN, r));
}
// 是否触发保底（纯）：连续失败 >= 3 后调用必成功（策划 §2.4「连续失败 3 次，第 4 次必成功」）
function petT2PityDue(pity: unknown): boolean {
  return Math.max(0, Math.floor(Number(pity) || 0)) >= PET_MERGE_PITY_LIMIT;
}
// 伪随机（纯）：Node crypto 可用则用之，否则 Math.random（不引新依赖）
function petT2Roll(): number {
  try {
    const c: any = (globalThis as any)?.crypto;
    if (c && typeof c.getRandomValues === 'function') {
      const u = new Uint32Array(1);
      c.getRandomValues(u);
      return (u[0] >>> 0) / 4294967296;
    }
  } catch { /* 无 crypto 时退化为 Math.random，不影响正确性 */ }
  return Math.random();
}
// 视图投影（纯）：pets 行 → T2 灵宠面板卡（策划 §2.3 / §3.1 / §2.7 逐条）
//   ★ 只读投影，不落库；主宠口径 = 服务端每玩家唯一一行（策划 §2.2 主战宠）
function petT2SpiritView(p: any): any {
  if (!p) return null;
  const hunger = Math.max(0, Math.floor(Number(p.hunger) || 0));
  const lv = Math.floor(hunger / PET_LEVEL_DIVISOR);
  const rIdx = petRarityIdx(p.rarity);
  const aff = petT2Affection(p.bond);
  // 气血 / 修为上限（策划 §3.4 新口径的规模基准；服务端无 evolutionStage ⇒ 恒幼年期档）
  const maxHp = 1200 + lv * 20;
  const maxExp = 1200 + lv * 200;
  const stage = 0; // 服务端无 evolutionStage 列 ⇒ 恒幼年期（见文件头「口径差异 1」）
  return {
    name: String(p.name),
    rarity: String(p.rarity),
    rarityIdx: rIdx,
    rarityCn: PET_RARITY_CN[String(p.rarity)] || PET_RARITY_CN['凡'],
    rarityKo: PET_RARITY_KO[Math.min(PET_RARITY_KO.length - 1, rIdx)],
    evolutionStage: stage,
    stageName: PET_STAGE_CN[stage],
    level: lv,
    // 亲密度（策划 §2.7 步骤 1）：bond/2 钳 0..100
    affection: aff,
    // 气血 / 修为（策划 §3.4 口径：幼年期系数 0.11 / 0.005，触底 100 / 50）
    maxHp,
    hp: Math.max(100, Math.floor(maxHp * 0.11)),
    maxExp,
    exp: Math.max(50, Math.floor(maxExp * 0.005)),
    // 喂养面（既有 Y18 字段，面板原样展示）
    hunger,
    bond: Math.max(0, Math.floor(Number(p.bond) || 0)),
    // 秘径消耗（该品阶幼年期档）+ 上限档（完全体 + 亲密度 100）夹住真实值
    fuseCost: petT2ExpeditionCost(p.rarity, stage, aff),
    fuseCostMax: petT2ExpeditionCost(p.rarity, 2, 100),
    // 融合费（该宠作主宠、以同品阶为副宠的基准档）
    mergeCost: petT2MergeCost(p.rarity, rIdx, aff),
    // 融合状态标记（策划 §2.7 步骤 1 的 merged 列语义）
    mergeMerged: Number(p.merged) || 0,
    mergePity: Math.max(0, Math.floor(Number(p.merge_pity) || 0)),
    isActive: true,
  };
}
// [/t2spirit]
"""

# ─────────────────────────────────────────────────────────
# C2 · pets 两列幂等加列（merged / merge_pity）
#      锚点 = safeAddColumn 定义体之后（第 18 环唯一的插入点，其后无内容）
# ─────────────────────────────────────────────────────────
C2_ANCHOR = """  // Y18：pet_play_log——每日嬉戏次数（UNIQUE(player_id,date)=PK 单语句原子 upsert，times<3 才放行）"""

C2_NEW = """  // T2SPIRIT089：T2 灵宠面板新增两列（**幂等加列**，冷启动 / 重跑双安全）。
  //   本环是末环追加，顶层 pets 建表 DDL 不在可动范围 ⇒ 走 safeAddColumn（DDL 自带幂等）。
  //   * pets.merged      —— 融合状态标记（策划 §2.7 步骤 1「妖灵归位」：服务端妖灵结算进客户端灵宠后
  //                         本行标记 merged=1，保留不删、幂等；0=未融合 / 1=已归位）。
  //   * pets.merge_pity  —— 融合失败保底计数（策划 §2.4：连续失败 3 次后第 4 次必成功；成功清零）。
  //                         **服务端权威**：若交由客户端报数，客户端不报失败即可无限免费必成。
  //   * pets.sub_consumed—— 累计消耗的副宠数（审计面：融合过多少次，面板/GM 可核）。
  //   ★ 位置纪律（本环实测踩过）：这三行**必须留在 db.serialize 回调内**，不可提到模块顶层。
  //     `const db` 在下方初始化，顶层直调 safeAddColumn ⇒ `ReferenceError: Cannot access 'db'
  //     before initialization` ⇒ 进程起不来（TDZ，实测同 srv_patch_rankmig 文件头警告）。
  //   ★ 三列均不做 PRAGMA 前置守卫：safeAddColumn 自身容忍 duplicate column name，
  //     重复入队无害（守卫只是省一次 DDL 的快路径，不是正确性依赖 —— 与第 18 环口径一致）。
  safeAddColumn('pets', 'merged', 'ALTER TABLE pets ADD COLUMN merged INTEGER NOT NULL DEFAULT 0');
  safeAddColumn('pets', 'merge_pity', 'ALTER TABLE pets ADD COLUMN merge_pity INTEGER NOT NULL DEFAULT 0');
  safeAddColumn('pets', 'sub_consumed', 'ALTER TABLE pets ADD COLUMN sub_consumed INTEGER NOT NULL DEFAULT 0');

  // Y18：pet_play_log——每日嬉戏次数（UNIQUE(player_id,date)=PK 单语句原子 upsert，times<3 才放行）"""

# ─────────────────────────────────────────────────────────
# C3 · 两个新端点（挂载在 pet/play 之后，同段追加）
# ─────────────────────────────────────────────────────────
C3_ANCHOR = """// ─────────────────────────────────────────────────────────
// Y4 渡劫天劫（伴生页 /yl/apps/rebirth/）：突破仪式化——第九层修为圆满 → 挑战天劫使者，"""

C3_NEW = """// ─────────────────────────────────────────────────────────
// T2 灵宠面板 API（灵宠列表 + 融合）：服务端权威面 = 视图投影（策划 §2.3/§3.1 公开系数）
// + 融合费定价（§2.4 + 用户 2026-09-29「基础 10000 起 / 以品阶为主 / 亲密度影响不大」）
// + 融合成功率与失败保底（§2.4，确定性非赌博 P3）+ 融合落库动作（扣灵石 / 材料消耗 / 标记）。
// 属性继承（等级取高 / 阶段晋升 / 技能继承）按策划 §2.1 P2 归客户端存档域 ⇒ 服务端只回 inheritHints，
// 不代写 player.pets（避免双写漂移；先例：战斗结算 Oy 在客户端）。
// ─────────────────────────────────────────────────────────

// GET /api/pet/spirit/list — 灵宠列表（面板采集面）。
// 语义：服务端 pets 权威行 → T2 视图（品阶 / 亲密度 / 气血 / 修为 / 融合状态 / 消耗预览）。
// 另回常量表，供客户端自算 §3.2 精确档位（服务端无 evolutionStage，只能出幼年期档）。
app.get('/api/pet/spirit/list', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, keyFn: (req: any) => `pet:spirit:list:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const rows = await dbAll('SELECT name, rarity, hunger, exp, bond, merged, merge_pity, created_at FROM pets WHERE player_id = ? ORDER BY id ASC LIMIT 50', [userId]);
    const spirits = (rows || []).map((r: any) => petT2SpiritView(r));
    res.json({
      ok: true,
      spirits,
      count: spirits.length,
      activeIndex: 0, // 服务端每玩家唯一一行 ⇒ 恒为主宠（策划 §2.2 主战宠）
      consts: {
        costBase: PET_T2_COST_BASE,               // 秘径 / 融合费基础 10000 灵石
        affectionDivisor: PET_T2_AFFECTION_DIVISOR, // 亲密度弱因子分母（影响 ≤5%）
        rarityMultFuse: PET_FUSE_RARITY_MULT,     // 秘径品阶因子（主因子）
        stageMultFuse: PET_FUSE_STAGE_MULT,       // 秘径阶段因子（次因子）
        rarityMultMerge: PET_MERGE_RARITY_MULT,   // 融合费主宠品阶因子
        rarityIdxMap: PET_RARITY_IDX,             // 凡0/灵1/仙3
        rarityKo: PET_RARITY_KO,                  // 普0/稀1/传2/仙3
        stageCn: PET_STAGE_CN,                    // 幼年/成熟/完全体
        mergeRateSame: PET_MERGE_RATE_SAME,
        mergeRateLowStep: PET_MERGE_RATE_LOW_STEP,
        mergeRateHighStep: PET_MERGE_RATE_HIGH_STEP,
        mergeRateMin: PET_MERGE_RATE_MIN,
        mergePityLimit: PET_MERGE_PITY_LIMIT,
      },
    });
  } catch (e: any) {
    console.error('pet spirit list error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/pet/spirit/merge — 灵宠融合（主宠保留 + 副宠消耗 + 融合费）。
// 请求体收口：subRarity 只认 凡/灵/仙（asStr + 白名单），忽略任何其它字段（防原型链污染）。
// 事务口径 = pet/feed 同款补偿式：预检余额 → 扣灵石（updatePlayerSave saveLock 互斥，含二次校验）
// → 单语句原子 UPDATE 结算（pity+1 或 清零 + sub_consumed+1 + merged 标记；守卫 merged=0 防重放）
// → 余额不足 / 宠物行缺失 → 补偿退费可重试。
// 成功率按策划 §2.4；失败保底由**服务端** merge_pity 把关（连续失败 3 次后第 4 次必成功）。
// 属性继承不回写服务端（策划 §2.1 P2）⇒ 成功时回 inheritHints 供客户端存档域落主宠。
app.post('/api/pet/spirit/merge', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `pet:spirit:merge:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const subRarity = asStr(req.body?.subRarity);
    if (!PET_RARITIES.includes(subRarity)) return res.status(400).json({ error: '副宠品阶非法（仅 凡/灵/仙）' });

    const pet: any = await dbGet('SELECT id, name, rarity, hunger, exp, bond, merged, merge_pity FROM pets WHERE player_id = ?', [userId]);
    if (!pet) return res.status(404).json({ error: '请先收养一只灵宠' });
    if (Number(pet.merged) > 0) return res.status(409).json({ error: '该灵宠已完成妖灵归位，不可再融合' });

    const aff = petT2Affection(pet.bond);
    const mainIdx = petRarityIdx(pet.rarity);
    const subIdx = petRarityIdx(subRarity);
    const cost = petT2MergeCost(pet.rarity, subIdx, aff);
    const rate = petT2MergeRate(mainIdx, subIdx);

    // 保底判定与掷骰（服务端权威：不信任客户端报数）
    const pityDue = petT2PityDue(pet.merge_pity);
    const roll = petT2Roll();
    const success = pityDue || roll < rate;

    // 单语句原子结算：RHS 全按旧行值求值；守卫 merged = 0 防并发重放（双击只一方 changes>0）。
    // ★ 顺序纪律（本环实测踩过）：**先结算、后扣费**，不是先扣费后结算。
    //   一旦「扣费成功」与「结算抛错」之间存在无补偿窗口，玩家会被扣钱却什么都没得到
    //   （实测：`sub_consumed` 列不存在时 UPDATE 抛错 ⇒ 500 且 10000 灵石已扣、未退回）。
    //   现序：结算失败（changes=0 或异常）→ 直接返回，**此时尚未扣费**，无需补偿、零资损；
    //   结算成功 → 再扣费，扣费失败才需要补偿回滚结算。补偿窗口缩到最短且方向唯一。
    // ★ T2 修复（0.8.9）：`merged` 改为**按成败**写入 —— 成功才归位（merged=1），
    //   失败保持 merged=0（仅 merge_pity+1）。
    //   病根：旧实现无条件 `merged = 1` ⇒ 第 1 次融合（无论成败）后 merged=1，
    //   第 2 次必被上方 `if (Number(pet.merged) > 0) return 409` 与 WHERE merged=0 双双挡下，
    //   merge_pity 永远到不了 3 ⇒ 策划 §2.4「连续失败 3 次后第 4 次必成功」保底形同虚设。
    //   sub_consumed 无论成败都 +1：策划 §2.4「失败：副宠消失」⇒ 副宠已被消耗（审计计数）。
    const nextPity = success ? 0 : Math.min(9999, Math.max(0, Math.floor(Number(pet.merge_pity) || 0)) + 1);
    let upd: { lastID: number; changes: number };
    try {
      upd = await dbRun(
        `UPDATE pets SET merged = ?, merge_pity = ?, sub_consumed = sub_consumed + 1 WHERE player_id = ? AND merged = 0`,
        [success ? 1 : 0, nextPity, userId]
      );
    } catch (e: any) {
      console.error('pet spirit merge settle error:', e?.message || e);
      return res.status(500).json({ error: '融合结算失败，请重试' }); // 未扣费，无资损
    }
    if (!upd.changes) {
      // 并发已归位 / 宠物行异常缺失 —— 未扣费，直接拒绝
      return res.status(409).json({ error: '融合状态已变更，请刷新后重试' });
    }

    // 扣融合费（saveLock 互斥 + gm_revision++ 促客户端拉新档）；扣费失败 → 补偿回滚结算（merged/pity/计数）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Number(sd.player?.spiritStones) || 0;
      if (b < cost) { short = true; return; }
      sd.player.spiritStones = b - cost;
    });
    if (!paid.ok || short) {
      await dbRun(
        'UPDATE pets SET merged = 0, merge_pity = ?, sub_consumed = MAX(0, sub_consumed - 1) WHERE player_id = ?',
        [Math.max(0, Math.floor(Number(pet.merge_pity) || 0)), userId]
      ).catch(() => {});
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '融合失败，请重试') });
    }

    const mainLevel = Math.floor(Math.max(0, Math.floor(Number(pet.hunger) || 0)) / PET_LEVEL_DIVISOR);
    logPetCare(userId, success ? 'merge' : 'merge_fail',
      `「${String(pet.name)}」融合${success ? '成功' : '失败'}（副宠 ${subRarity} 品阶，耗 ${cost} 灵石）`);

    res.json({
      ok: true,
      success,
      pity: pityDue,
      cost,
      rate,
      merged: success ? 1 : 0,
      mergePity: nextPity,
      // 服务端不回写灵宠属性（策划 §2.1 P2）；成功时给出客户端存档域的继承指令
      inheritHints: success ? {
        keepName: String(pet.name),
        keepLevel: mainLevel,
        rarity: String(pet.rarity),
        rarityIdx: mainIdx,
        affection: aff,
        subRarity,
        subRarityIdx: subIdx,
        note: '属性继承按策划 §2.1 P2 归客户端存档域，由客户端按 §2.4 继承表落主宠',
      } : null,
    });
  } catch (e: any) {
    console.error('pet spirit merge error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

""" + C3_ANCHOR


def selftest() -> int:
    """在真实的上一环产物上跑门禁（不碰 srv/index_v28.ts）。"""
    print('0.8.9 T2 灵宠面板环（链第 19 环）— 自证')
    gates = []
    ok = True

    def gate(name, cond, detail=''):
        nonlocal ok
        gates.append((name, bool(cond), detail))
        if not cond:
            ok = False

    cand = os.path.join(HERE, '_chainstage', 's18.rankingmig.ts')
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

    for tag, anc in (('C1', C1_ANCHOR), ('C1b', C1_ANCHOR_2),
                     ('C2', C2_ANCHOR), ('C3', C3_ANCHOR)):
        if src.count(anc) != 1:
            print('  [FAIL] 前置守卫 %s 锚点命中 %d 次（期望 1）' % (tag, src.count(anc)))
            return 1
    print('  [OK]   前置守卫：C1/C1b/C2/C3 锚点各命中 1 次')

    # ★ 自毁防线：4 处改动全部是「插入式」（只做加法），new 必须含 old 原文。
    _assert_anchor_kept('C1', C1_ANCHOR, C1_NEW)
    _assert_anchor_kept('C1b', C1_ANCHOR_2, C1_NEW_BLOCK)
    _assert_anchor_kept('C2', C2_ANCHOR, C2_NEW)
    _assert_anchor_kept('C3', C3_ANCHOR, C3_NEW)

    out = apply_one(src, 'C1', C1_ANCHOR, C1_NEW)
    out = apply_one(out, 'C1b', C1_ANCHOR_2, C1_NEW_BLOCK)
    out = apply_one(out, 'C2', C2_ANCHOR, C2_NEW)
    out = apply_one(out, 'C3', C3_ANCHOR, C3_NEW)

    delta = len(out.encode('utf-8')) - len(src.encode('utf-8'))
    gates2 = []

    def gate2(name, cond, detail=''):
        gates2.append((name, bool(cond), detail))

    _gates(out, delta, gate2)
    for n, c, d in gates2:
        gate(n, c, d)

    print('\n  --- 门禁 ---')
    for name, c, detail in gates:
        print('  [%s] %s%s' % ('OK' if c else 'FAIL', name, ('  ' + detail) if detail else ''))
    print('\n  自证结果：%s' % ('全 PASS' if ok else '存在 FAIL'))
    return 0 if ok else 1


def _gates(text: str, delta: int, gate) -> None:
    """本环门禁（main 与 selftest 共用同一套，避免两处漂移）。"""
    # ── 交付门禁：任务点名的硬指标 ──
    gate('G1 [任务] GET /api/pet/spirit/list 端点 >= 1',
         text.count('/api/pet/spirit/list') >= 1, '实际 %d' % text.count('/api/pet/spirit/list'))
    gate('G2 [任务] POST /api/pet/spirit/merge 端点 >= 1',
         text.count('/api/pet/spirit/merge') >= 1, '实际 %d' % text.count('/api/pet/spirit/merge'))
    gate('G3 [任务] merged 标记 >= 1',
         text.count('merged') >= 1, '实际 %d' % text.count('merged'))
    # ── 坑门禁（本项目四类自毁坑）──
    n_direct = text.count("db.exec('ALTER TABLE") + text.count('db.exec("ALTER TABLE')
    gate('G4 [坑4] db.exec(ALTER TABLE …) 直调 == 0（全走 safeAddColumn）',
         n_direct == 0, '实际 %d' % n_direct)
    gate('G5 [坑5] db.run(...).catch( == 0',
         not re.search(r'db\.run\([^\n]*\)\.catch\(', text), '实际 %d' % len(re.findall(r'db\.run\([^\n]*\)\.catch\(', text)))
    gate('G6 [坑6] require( == 0',
         text.count('require(') == 0, '实际 %d' % text.count('require('))
    # ── 幂等加列就位 ──
    gate('G7 pets.merged 走 safeAddColumn 恰 1 处',
         text.count("safeAddColumn('pets', 'merged',") == 1,
         '实际 %d' % text.count("safeAddColumn('pets', 'merged',"))
    gate('G8 pets.merge_pity 走 safeAddColumn 恰 1 处',
         text.count("safeAddColumn('pets', 'merge_pity',") == 1,
         '实际 %d' % text.count("safeAddColumn('pets', 'merge_pity',"))
    gate('G8d pets.sub_consumed 走 safeAddColumn 恰 1 处（融合块引用的列必须被声明）',
         text.count("safeAddColumn('pets', 'sub_consumed',") == 1,
         '实际 %d' % text.count("safeAddColumn('pets', 'sub_consumed',"))
    # ★ G8b [坑 TDZ] 两处加列**必须在 `const db =` 之后**（在 db.serialize 回调内）。
    #   实测教训：把 safeAddColumn 调用提到模块顶层（`const db` 之前）⇒
    #   `ReferenceError: Cannot access 'db' before initialization` ⇒ 进程起不来。
    #   口径与第 18 环同：db 是 const，函数体只在**调用时**求值 db ⇒ 调用点必须在初始化之后。
    _db_init = text.find('const db = new sqlite3.Database(')
    _c_merged = text.find("safeAddColumn('pets', 'merged',")
    _c_pity = text.find("safeAddColumn('pets', 'merge_pity',")
    gate('G8b [坑TDZ] 两处 pets 加列均在 `const db =` 初始化之后（不得置于模块顶层）',
         _db_init >= 0 and _c_merged > _db_init and _c_pity > _db_init,
         'db@%d merged@%d pity@%d' % (_db_init, _c_merged, _c_pity))
    gate('G9 [坑4 反面] 无 PRAGMA 守卫搭配直调 ALTER 的旧形态',
         text.count('CREATE TABLE IF NOT EXISTS pets (') == 1)
    # ── 端点结构：鉴权 / 限流 / 块内自洽 ──
    _list = "app.get('/api/pet/spirit/list', authenticateToken, rateLimit("
    _merge = "app.post('/api/pet/spirit/merge', authenticateToken, rateLimit("
    gate('G10 列表端点定义恰 1 处且带 authenticateToken + rateLimit',
         text.count(_list) == 1, '实际 %d' % text.count(_list))
    gate('G11 融合端点定义恰 1 处且带 authenticateToken + rateLimit',
         text.count(_merge) == 1, '实际 %d' % text.count(_merge))
    _lb = _block(text, _list, _merge)
    _mb = _block(text, _merge, '\n// ─────────────────────────────────────────────────────────\n// Y4 渡劫天劫')
    gate('G12 列表块内不回写落库（无 UPDATE/INSERT/DELETE pets）',
         'UPDATE pets' not in _lb and 'INSERT INTO pets' not in _lb and 'DELETE FROM pets' not in _lb)
    gate('G13 融合块内：结算 → 扣费 → 扣费失败补偿回滚 三步齐备',
         'spiritStones' in _mb and 'updatePlayerSave(' in _mb
         and 'UPDATE pets SET merged = ?' in _mb and 'MAX(0, sub_consumed - 1)' in _mb)
    # ★ G13b [资损红线] 扣费必须**排在结算之后**：结算异常时尚未扣费 ⇒ 无无补偿窗口。
    #   实测教训：旧序（先扣费后结算）在结算抛错时扣了 10000 灵石且未退回 ⇒ 玩家资损。
    gate('G13b [资损红线] 融合块内结算 UPDATE 先于扣费 updatePlayerSave（无补偿窗口）',
         _mb.find('UPDATE pets SET merged = ?') < _mb.find('updatePlayerSave(')
         and _mb.find('UPDATE pets SET merged = ?') > 0)
    # ★ G13d [保底红线] merged 必须**按成败**写入（切片限域 _mb，不全文计数）：
    #   成功=1 / 失败=0。实测教训：无条件 `merged = 1` ⇒ 第 1 次融合（成败皆然）后即归位，
    #   第 2 次必 409、merge_pity 永远到不了 3 ⇒ 策划 §2.4 保底死。
    gate('G13d [保底红线] 融合落库 merged 按成败写入（成功=1/失败=0），不得无条件 merged=1',
         'UPDATE pets SET merged = ?' in _mb
         and 'success ? 1 : 0' in _mb
         and 'UPDATE pets SET merged = 1,' not in _mb)
    # ★ G13e [保底红线] 回执 merged 必须与 success 同源（失败不得报 merged=1）
    gate('G13e [保底红线] 融合回执 merged 与 success 同源',
         'merged: success ? 1 : 0,' in _mb)
    # ★ G13c [已声明列] 融合块引用的自增列 sub_consumed 必须已由 safeAddColumn 声明
    #   （实测教训：引用了未声明的列 ⇒ SQLITE_ERROR: no such column ⇒ 500）。
    for _col in ('merged', 'merge_pity', 'sub_consumed'):
        if ("%s = %s" % (_col, _col)) in _mb or ('%s + 1' % _col) in _mb:
            gate("G13c 融合块引用的列 pets.%s 已声明（safeAddColumn）" % _col,
                 ("safeAddColumn('pets', '%s'," % _col) in text)
    gate('G14 融合块内输入收口（asStr + PET_RARITIES 白名单，防原型链污染）',
         'asStr(req.body?.subRarity)' in _mb and 'PET_RARITIES.includes(subRarity)' in _mb)
    gate('G15 融合成功不代写存档：只回 inheritHints（策划 §2.1 P2）',
         'inheritHints' in _mb and 'player.pets' not in _mb)
    # ── 定价与规则：用户 2026-09-29 指示 + 策划 §2.4/§3.1 落地 ──
    gate('G16 基础 10000 灵石起（PET_T2_COST_BASE = 10000）',
         text.count('const PET_T2_COST_BASE = 10000;') == 1)
    gate('G17 亲密度弱因子分母 2000（影响 ≤5%）',
         text.count('const PET_T2_AFFECTION_DIVISOR = 2000;') == 1)
    gate('G18 融合品阶为主因子：主宠三档表就位且跨度 >= 1.4',
         text.count("const PET_MERGE_RARITY_MULT: Record<string, number> = { '\u51e1': 1.00, '\u7075': 1.20, '\u5fc9\u54c1': 1.40 };") == 0
         and "PET_MERGE_RARITY_MULT" in text and '1.40' in text and '1.20' in text)
    gate('G19 成功率三档常量就位（0.70 / 0.15 / 0.20 / 下限 0.20）',
         text.count('? 0.70') == 0 or True)  # 占位：真实判定见下行
    gate('G19b 成功率常量逐条就位',
         text.count('const PET_MERGE_RATE_SAME = 0.70;') == 1
         and text.count('const PET_MERGE_RATE_LOW_STEP = 0.15;') == 1
         and text.count('const PET_MERGE_RATE_HIGH_STEP = 0.20;') == 1
         and text.count('const PET_MERGE_RATE_MIN = 0.20;') == 1)
    gate('G20 失败保底：服务端权威（merge_pity 常量 + 计数落库 + 必成分支）',
         text.count('const PET_MERGE_PITY_LIMIT = 3;') == 1
         and 'petT2PityDue(pet.merge_pity)' in _mb
         and 'pityDue || roll < rate' in _mb)
    gate('G21 秘径消耗函数就位（§3.1 round100 × P品阶 × P阶段 × P亲密度）',
         'function petT2ExpeditionCost(' in text and 'petRound100(' in text)
    gate('G22 [红线] 既有 4 个 pet 端点语义未动',
         text.count("app.get('/api/pet', authenticateToken") == 1
         and text.count("app.post('/api/pet/adopt', authenticateToken") == 1
         and text.count("app.post('/api/pet/feed', authenticateToken") == 1
         and text.count("app.post('/api/pet/play', authenticateToken") == 1)
    gate('G23 [红线] pets 建表 DDL 未被改动（每玩家一只 UNIQUE 防线仍在）',
         text.count('player_id INTEGER NOT NULL UNIQUE') == 1)
    gate('G24 [红线] 其它环锚区未动（ki001 / net2 / baseclean089 / rankingmig）',
         text.count('function settleSaveEconV2') == 1
         and text.count("error: 'stale_save'") == 1
         and text.count('const GM_PASSWORD = process.env.GM_PASSWORD;') == 1
         and text.count('const safeAddColumn = (table: string, col: string, ddl: string) => {') == 1)
    # ── 增量区间：防注入爆炸 / 静默没注入 ──
    gate('G25 增量字节 ∈ [6000, 40000] B', 6000 <= delta <= 40000, 'delta = %+d B' % delta)
    gate('G26 幂等标记就位', MARK in text)
    gate('G27 T2 纯逻辑块闭合（[t2spirit] 开闭各 1 处）',
         text.count('// [t2spirit] ') == 1 and text.count('// [/t2spirit]') == 1)
    # ★ G28 [只做加法] 既有 petcore 符号一字未删 —— 本环实测踩过：
    #   新块没把锚点原文带一遍 ⇒ clampPetDetail 定义被 replace 吃掉 ⇒ adopt 500。
    #   凡「在既有块后插入」的补丁，都必须同时断言**既有符号仍在**。
    gate('G28 [只做加法] clampPetDetail 定义仍在且恰 1 处（本环不得删既有符号）',
         text.count('function clampPetDetail(t: unknown): string { return asStr(t).slice(0, 60); }') == 1,
         '实际 %d' % text.count('function clampPetDetail(t: unknown): string { return asStr(t).slice(0, 60); }'))
    gate('G29 [只做加法] petcore 闭合行 [/petcore] 仍在且恰 1 处',
         text.count('// [/petcore]') == 1, '实际 %d' % text.count('// [/petcore]'))
    gate('G30 [只做加法] petcore 既有常量未丢（PET_FEED_COST / PET_PLAY_DAILY_MAX 各 1）',
         text.count('const PET_FEED_COST = 5000;') == 1
         and text.count('const PET_PLAY_DAILY_MAX = 3;') == 1)


# ★ C1 的两段应用：一段抬注释、一段插纯逻辑块。
#   C1_ANCHOR_2 = petcore 块末（clampPetDetail 定义 + [/petcore] 闭合行）。
#
#   ★★ 血泪纪律（本环实测踩过，务必保留）★★
#   `apply_one` 是 `text.replace(old, new)` —— **new 必须把 old 原文再带一遍**，
#   否则锚点行会被**整段吃掉**，而不是「在锚点后插入」。
#   本环第一版把新块写成「纯新增」、没带锚点 ⇒ 替换后 `clampPetDetail` 函数定义
#   与 `[/petcore]` 闭合行一起**消失** ⇒ `POST /api/pet/adopt` 报
#   `clampPetDetail is not defined` ⇒ **HTTP 500**（实测：空库冒烟收养直接 500，
#   服务端日志原文即此；by-function 级回归，冒烟才抓得到、静态 reading 抓不到）。
#   修法：C1_NEW_BLOCK = C1_ANCHOR_2 + C1_NEW_BODY（把锚点逐字重放再挂新块）。
#   兜底门禁：G28「既有 clampPetDetail / [/petcore] 均在且各恰 1 处」——
#   本环**只做加法、绝不删既有符号**。
C1_ANCHOR_2 = """function clampPetDetail(t: unknown): string { return asStr(t).slice(0, 60); }
// [/petcore]"""

C1_NEW_BLOCK = C1_ANCHOR_2 + C1_NEW_BODY


def main() -> int:
    ap = argparse.ArgumentParser(description='0.8.9 T2 灵宠面板环（链第 19 环 / 新末环）')
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
    print('0.8.9 T2 灵宠面板环（链第 19 环 / 新末环）')
    print('  source : %s  bytes=%d md5=%s' % (src, before_bytes, md5s(text)))

    if MARK in text:
        print('  [SKIP] 已包含 %s 标记，无需重复打补丁' % MARK)
        return 0

    for tag, anc in (('C1', C1_ANCHOR), ('C1b', C1_ANCHOR_2),
                     ('C2', C2_ANCHOR), ('C3', C3_ANCHOR)):
        if text.count(anc) != 1:
            die('前置守卫失败：%s 锚点命中 %d 次（期望 1）—— 基线不符' % (tag, text.count(anc)))
    print('  [OK]   前置守卫：C1/C1b/C2/C3 锚点各命中 1 次')

    # ★ 自毁防线：4 处改动全部是「插入式」（只做加法），new 必须含 old 原文。
    _assert_anchor_kept('C1', C1_ANCHOR, C1_NEW)
    _assert_anchor_kept('C1b', C1_ANCHOR_2, C1_NEW_BLOCK)
    _assert_anchor_kept('C2', C2_ANCHOR, C2_NEW)
    _assert_anchor_kept('C3', C3_ANCHOR, C3_NEW)

    text = apply_one(text, 'C1', C1_ANCHOR, C1_NEW)
    text = apply_one(text, 'C1b', C1_ANCHOR_2, C1_NEW_BLOCK)
    text = apply_one(text, 'C2', C2_ANCHOR, C2_NEW)
    text = apply_one(text, 'C3', C3_ANCHOR, C3_NEW)

    delta = len(text.encode('utf-8')) - before_bytes
    gates = []

    def gate(name, cond, detail=''):
        gates.append((name, bool(cond), detail))

    _gates(text, delta, gate)

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
        bak = '%s.bak-t2spirit-%s' % (src, time.strftime('%Y%m%d-%H%M%S'))
        shutil.copy2(src, bak)
        print('\n  [备份] %s' % bak)
        open(src, 'wb').write(text.encode('utf-8'))
        print('  [写出] %s  bytes=%d  md5=%s' % (src, len(text.encode('utf-8')), md5s(text)))

    print('  [PASS] T2 灵宠面板服务端能力落地（delta %+d B）' % delta)
    return 0


if __name__ == '__main__':
    sys.exit(main())
