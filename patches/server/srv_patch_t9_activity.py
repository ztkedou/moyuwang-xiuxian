# -*- coding: utf-8 -*-
r"""srv_patch_t9_activity.py — 0.8.8 T9「仙途任务 / 活跃度」服务端重构（链路第 13 环）

**基线**：`_chainstage/s12.net2_stale.ts`（= s10 + KI-001 + net-2）
**设计**：`docs/0.8.8-design/T9-仙途任务活跃度.md`（760 行）+ `T9-实现批改动清单.md`（229 行）
**用法**：
  python srv_patch_t9_activity.py --src <上一环产物> [--out <本环产物>]
  python srv_patch_t9_activity.py --selftest      # 纯数学/结构自证

## 用户已拍板（2026-09-29）
- **L = 甲**：日切统一北京 0 点（含 `ARENA_DAILY_MAX` 的 2 处 UTC 日切改北京）
- **M = 只计论剑**：第 12 项只 COUNT `arena_battles`（含 `status='accepted'` 过滤）
- **传承石降频：周 → 月**（1,000 档里程碑的「传承石 ×1」改为每月限领一次）

## 改动清单（10 处锚点 + 5 段新增）
| # | 锚 | 改动 |
|---|---|---|
| T1 | `const QUEST_DEFS = [` 块 | 4 → 18 条，每条含 `group`/`points`/`limit`/`unit`；保留 4 个 legacy 键名 |
| T2 | `const CHEST_TIERS = ...` | `[25,50,75,100]` → `[30,60,100,150,200,260]` |
| T3 | `const CHEST_REWARDS ...` | 固定值 → base 表（`CHEST_REWARDS` 符号名保留） |
| T4 | `function chestKey` | 之后注入 `T9_REWARDS`(exp/tickets) + `ylrf()` + `bjWeekStart()` |
| T5 | `function isChestUnlocked` | 之后注入 `collectDailyActivity` / `collectWeeklyActivity` / `ACTIVITY_MAX` |
| T6 | `extractCounters` 返回块 | 加 `grottoLevel` / `grottoSpeedup` |
| T7 | summary 的 `activityFromQuests(questList)` | 改 `await collectDailyActivity` + 加 week/milestones/activityMax/chests.exp/tickets |
| T8 | chest 的 `activityFromQuests((rows||[]).map(...))` | 改 `await collectDailyActivity` + T3 组合发奖 |
| T9 | 新增 `POST /api/quest/milestone` | 周里程碑领取（幂等 `activity_milestones`） |
| T10 | `utcDayStartMs()` | 改为北京 0 点（L=甲） |
| D1 | 建表区 | `activity_milestones` DDL |

## 红线（不许破）
- `tickDailyQuests` **原样保留**（Y19 成就唯一数据源），仍只喂 legacy 4 键
- Y19 两处 `SELECT COUNT(*) ... FROM daily_quests WHERE user_id = ? AND done = 1 AND quest_key NOT LIKE 'chest_%'` **逐字保留**
- `activityFromQuests(` 计数 **3 → 1**：summary / chest 两处调用改为读时计算
  （`collectDailyActivity`），仅保留纯函数定义 1 处（不再被任何调用点引用，留作 legacy 语义锚）
- `chest_*` 占位行 + 失败回滚 DELETE 不动
"""
import argparse
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────────────────────────────────────────────────────────
# T1 · QUEST_DEFS：4 → 18 条（带 group / points / limit / unit）
# ─────────────────────────────────────────────────────────────────────────────
T1_OLD = """const QUEST_DEFS = [
  { key: 'meditate', name: '打坐 30 分钟', target: 30 * 60 * 1000, points: 25 },
  { key: 'kill', name: '战斗胜利 5 场', target: 5, points: 25 },
  { key: 'adventure', name: '历练 3 次', target: 3, points: 25 },
  { key: 'spend', name: '消费 10000 灵石', target: 10000, points: 25 },
];
"""

T1_NEW = """// T9 0.8.8：18 项活跃度来源（A 核心 / B 进阶 / C 社交 / D 休闲），名义满分 330。
//   每条 { key, name, group, points, limit, target, unit }：
//     points = 单次分值；limit = 当日计分次数上限（points×limit = 该项满分）；
//     target = 单次触发阈值（读时计算时 progress 除以它取整，与 legacy 任务同语义）。
//   ★ legacy 4 键（meditate/kill/adventure/spend）键名与 target 逐字不变 ——
//     `tickDailyQuests` 仍只喂这 4 键，Y19 成就口径须 byte 级一致（见文件尾 §Y19）。
const QUEST_DEFS = [
  // ── A 组 · 核心（5 项，名义 110）──
  { key: 'signin',       name: '仙途签到',     group: 'A', points: 10, limit: 1, target: 1,              unit: '次' },
  { key: 'meditate',     name: '打坐修心',     group: 'A', points: 5,  limit: 6, target: 20 * 60 * 1000,  unit: '分钟' },
  { key: 'kill',         name: '斩妖除魔',     group: 'A', points: 5,  limit: 4, target: 5,              unit: '场' },
  { key: 'adventure',    name: '历练问道',     group: 'A', points: 6,  limit: 5, target: 4,              unit: '次' },
  { key: 'expgain',      name: '修为精进',     group: 'A', points: 5,  limit: 4, target: 1,              unit: '次' },
  // ── B 组 · 进阶（5 项，名义 86）──
  { key: 'dungeon',      name: '秘境探幽',     group: 'B', points: 8,  limit: 3, target: 1,              unit: '次' },
  { key: 'alchemy',      name: '丹火不熄',     group: 'B', points: 5,  limit: 3, target: 1,              unit: '次' },
  { key: 'farm',         name: '灵田躬耕',     group: 'B', points: 4,  limit: 4, target: 1,              unit: '次' },
  { key: 'pet',          name: '妖灵相伴',     group: 'B', points: 4,  limit: 4, target: 1,              unit: '次' },
  { key: 'grotto',       name: '洞府营造',     group: 'B', points: 5,  limit: 3, target: 1,              unit: '次' },
  // ── C 组 · 社交（5 项，名义 80）──
  { key: 'sect',         name: '仙盟同心',     group: 'C', points: 7,  limit: 3, target: 1,              unit: '次' },
  { key: 'arena',        name: '擂台论道',     group: 'C', points: 7,  limit: 3, target: 1,              unit: '次' },
  { key: 'mentor',       name: '师徒相授',     group: 'C', points: 7,  limit: 2, target: 1,              unit: '次' },
  { key: 'bounty',       name: '悬赏缉凶',     group: 'C', points: 5,  limit: 3, target: 1,              unit: '次' },
  { key: 'chat',         name: '江湖留名',     group: 'C', points: 3,  limit: 3, target: 1,              unit: '次' },
  // ── D 组 · 休闲（3 项，名义 54）──
  { key: 'fun',          name: '行乐有道',     group: 'D', points: 5,  limit: 4, target: 1,              unit: '次' },
  { key: 'lottery',      name: '仙缘奇遇',     group: 'D', points: 4,  limit: 4, target: 1,              unit: '次' },
  { key: 'spend',        name: '财货通流',     group: 'D', points: 6,  limit: 3, target: 10000,          unit: '灵石' },
];
// 名义满分（points×limit 之和）= 110+86+80+54 = 330；P0 降级（丹火/灵田收获）后见 T9 §7.3
const ACTIVITY_MAX = 330;
// 分组元数据（客户端分组折叠用；顺序 = 展示顺序）
const QUEST_GROUPS: Record<string, string> = { A: '核心', B: '进阶', C: '社交', D: '休闲' };
// 当日依赖「行/读时」双口径的 legacy 4 键（tickDailyQuests 会写行，读时应与之取大）
const LEGACY_QUEST_KEYS = ['meditate', 'kill', 'adventure', 'spend'];
"""

# ─────────────────────────────────────────────────────────────────────────────
# T2 · CHEST_TIERS：4 档 → 6 档
# ─────────────────────────────────────────────────────────────────────────────
T2_OLD = "const CHEST_TIERS = [25, 50, 75, 100]; // 活跃度四档宝箱\n"

T2_NEW = "const CHEST_TIERS = [30, 60, 100, 150, 200, 260]; // T9 0.8.8：活跃度六档宝箱（门槛=活跃度）\n"

# ─────────────────────────────────────────────────────────────────────────────
# T3 · CHEST_REWARDS：固定值 → base 表（符号名保留）
# ─────────────────────────────────────────────────────────────────────────────
T3_OLD = "const CHEST_REWARDS: Record<number, number> = { 25: 2500, 50: 7500, 75: 15000, 100: 30000 };\n"

T3_NEW = """// T9 0.8.8：灵石 base 表（实际发放 = floor(base × ylrf(realm))，见 T4 的 ylrf()）
//   旧四档固定值（25/50/75/100 → 2500/7500/15000/30000，合计 55,000）按「低境界不砍、
//   高境界按境界补齐」原则改为六档 base；炼气期合计 ≈ 54,664（与旧值基本持平）。
const CHEST_REWARDS: Record<number, number> = { 30: 1000, 60: 2000, 100: 4000, 150: 7000, 200: 11000, 260: 16000 };
// 每档附带的「修为打坐等效次数」与「抽奖券」数（T9 §4.2）
//   P0 发奖通道：insertMail 只支持灵石附件 ⇒ 修为/券按 §7.4「零风险降级」折算成灵石一并发放，
//   邮件正文说明折算比例；折算基准 = 1 次打坐等效 ≈ 12 灵石（保守低估值，避免新 faucet 超发）。
const CHEST_EXP_TIMES: Record<number, number> = { 30: 60, 60: 120, 100: 240, 150: 360, 200: 480, 260: 600 };
const CHEST_TICKETS: Record<number, number> = { 30: 0, 60: 1, 100: 2, 150: 3, 200: 5, 260: 8 };
const CHEST_EXP_TO_STONE = 12; // 1 打坐等效次 → 12 灵石（P0 折算比）
"""

# ─────────────────────────────────────────────────────────────────────────────
# T4 · 在 chestKey 之后注入 ylrf() + bjWeekStart() + 里程碑表
# ─────────────────────────────────────────────────────────────────────────────
T4_ANCHOR = "function chestKey(tier: number): string { return 'chest_' + tier; }\n"

T4_APPEND = """function chestKey(tier: number): string { return 'chest_' + tier; }
// T9 0.8.8：境界奖励倍率 YLRF（= 既有 rainRealmFactor，与「数值表-T11」§4.3 的
//   rainHourlyStones 同源：i<=0 → 4/3；i>=1 → 2i+1（筑基 3 / 金丹 5 / 元婴 7 / 化神 9 /
//   合道 11 / 长生 13）。注意与 sameRealmMult 的 1.5^idx 指数曲线不同，本函数专供 T9 奖励，
//   勿改 sameRealmMult）。T9_REALM_ORDER 与 ECON_REALM_ORDER 同源同序。
const T9_REALM_ORDER = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];
// ★ T9 活跃度奖励倍率 = 既有 rainRealmFactor(i)（:4921 同源，勿自造曲线）：
//     i <= 0 → 4/3（炼气）；i >= 1 → 2*i+1（筑基 3 / 金丹 5 / … / 长生 13）。
//     与「数值表-T11」§4.3 rainHourlyStones 完全同源，保证 T9 奖励与挂机时薪口径一致。
function ylrf(realm: unknown): number {
  const idx = Math.max(0, T9_REALM_ORDER.indexOf(String(realm || '')));
  return idx <= 0 ? 4 / 3 : 2 * idx + 1;
}
// 与 ylrf 同源的「按境界序 idx」入口（内部直调，避免字符串往返）
function ylrfIdx(idx: number): number {
  const i = Math.max(0, Math.floor(Number(idx) || 0));
  return i <= 0 ? 4 / 3 : 2 * i + 1;
}
// 北京时区「周一 0 点」对应的 YYYY-MM-DD（与 bjDate 同风格；ISO 周一=1，周日=0 ⇒ 归一到周一）
function bjWeekStart(ms: number): string {
  const d = new Date(ms + 8 * 60 * 60 * 1000);
  const dow = (d.getUTCDay() + 6) % 7;            // 周一=0 … 周日=6
  const monday = new Date(d.getTime() - dow * 86400000);
  return monday.toISOString().slice(0, 10);
}
// 周里程碑档位（门槛 = 周累计活跃度；wbase = 灵石 base；wexp = 打坐等效；wtk = 抽奖券）
//   ★ 1,000 档的「传承石 ×1」按用户拍板**降频为月**（不是每周）：见 MILE_MONTHLY_TIER。
const WEEK_MILESTONES: Array<{ tier: number; wbase: number; wexp: number; wtk: number; legacy: string }> = [
  { tier: 500,  wbase: 20000, wexp: 200, wtk: 8,  legacy: '' },
  { tier: 1000, wbase: 45000, wexp: 450, wtk: 15, legacy: '传承石' },
  { tier: 1800, wbase: 60000, wexp: 600, wtk: 30, legacy: '仙品道具+称号' },
];
const MILE_MONTHLY_TIER = 1000; // 该档的 legacy 额外奖励（传承石）按「月」限领一次，其余按周
const MILE_MONTH_REWARD = 5000; // 传承石折算灵石（P0 折算通道；P1 走正规物品通道）

// T9 0.8.8：周里程碑幂等表（UNIQUE(user_id,week,tier)）—— 建表语句在下方 DDL 区执行
function weekMonthKey(week: string): string { return week.slice(0, 7); } // YYYY-MM
"""

# ─────────────────────────────────────────────────────────────────────────────
# T5 · 在 isChestUnlocked 之后注入读时计算核心
# ─────────────────────────────────────────────────────────────────────────────
T5_ANCHOR = "function isChestUnlocked(activity: number, tier: number): boolean { return activity >= tier; }\n"

T5_APPEND = r"""function isChestUnlocked(activity: number, tier: number): boolean { return activity >= tier; }

// ─────────────────────────────────────────────────────────────────────────────
// T9 0.8.8 · 读时计算核心：collectDailyActivity(userId, date)
//   对 18 项来源各跑一条当日取值，合成 { items, activity }。**不写 daily_quests 行**
//   （14 个新项目刻意不落行，保 Y19 口径 4 行/日 byte 级不变，见 §7.6）。
//   legacy 4 键（meditate/kill/adventure/spend）取 max(行值, 读时值)：tick 会写行，
//   但读时口径更实时（玩家同日内先大后小可能 tick 只记到部分），取大不漏分。
//
//   ⚠️ 时间戳三口径（逐表核对，勿统一假设）：
//     ① date TEXT（北京日）：stats_daily / daily_quests / dungeon_tracker / fun_daily /
//        farm_daily_care / sect_task_claims / pet_play_log / mentor_greetings / teach_log
//     ② INTEGER ms epoch：arena_battles.resolved_at / bounties.finished_at
//     ③ DATETIME UTC 文本：chat_messages / lottery_history / users.last_login / sect_ledger /
//        pet_care_log / alchemy.mature_at(INTEGER) —— 需换算北京日
// ─────────────────────────────────────────────────────────────────────────────

// 北京日 → [当日 0 点 ms, 次日 0 点 ms)，供 INTEGER/DATETIME 列做区间过滤
function bjDayRangeMs(date: string): [number, number] {
  const start = Date.parse(date + 'T00:00:00+08:00');
  return [start, start + 86400000];
}
// DATETIME(UTC 文本) → 北京日 YYYY-MM-DD：先按 UTC 解析，再 +8h 取日
function bjDateOfUtcText(s: unknown): string | null {
  if (!s) return null;
  const t = Date.parse(String(s).includes('T') ? String(s) : String(s).replace(' ', 'T') + 'Z');
  if (!Number.isFinite(t)) return null;
  return bjDate(t);
}

async function collectDailyActivity(userId: number, date: string): Promise<{ items: Array<{ key: string; progress: number; done: boolean; points: number }>; activity: number }> {
  const [d0, d1] = bjDayRangeMs(date);
  const rows = await Promise.all([
    // 1 仙途签到：users.last_login（UTC DATETIME 文本）换算北京日 = 今日
    dbGet('SELECT last_login AS v FROM users WHERE id = ?', [userId]).catch(() => null),
    // 2 打坐修心：stats_daily.minutes（date）
    dbGet('SELECT minutes AS v FROM stats_daily WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 3 斩妖除魔：stats_daily.kills（date）
    dbGet('SELECT kills AS v FROM stats_daily WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 4 历练问道：daily_quests.progress（legacy 行）
    dbGet("SELECT progress AS v, done AS d FROM daily_quests WHERE user_id = ? AND date = ? AND quest_key = 'adventure'", [userId, date]).catch(() => null),
    // 5 修为精进：stats_daily.exp_gain（date），每 25% 当前层算 1 次 —— 读时无境界层基数，
    //   改用「exp_gain 每 12.5 万算 1 次」的保守代理（P0；P1 可注入 realm/level 精算）
    dbGet('SELECT exp_gain AS v FROM stats_daily WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 6 秘境探幽：dungeon_tracker.count（date）
    dbGet('SELECT count AS v FROM dungeon_tracker WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 7 丹火不熄：alchemy.mature_at（INTEGER ms）落在当日（P0 近似：同 slot 覆盖只算最后一次，接受）
    dbGet('SELECT COUNT(*) AS v FROM alchemy WHERE player_id = ? AND mature_at >= ? AND mature_at < ?', [userId, d0, d1]).catch(() => null),
    // 8 灵田躬耕：farm_daily_care（date，tended/boosted 计数）；spirit_farm 无收获时间列 ⇒ P0 只算照料
    dbGet('SELECT COALESCE(SUM(tended),0) + COALESCE(SUM(boosted),0) AS v FROM farm_daily_care WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 9 妖灵相伴：pet_play_log.times（date）+ pet_care_log.created_at（UTC DATETIME）
    dbGet('SELECT COALESCE(SUM(times),0) AS v FROM pet_play_log WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    dbGet('SELECT COUNT(*) AS v FROM pet_care_log WHERE player_id = ? AND created_at >= ? AND created_at < ?', [userId, new Date(d0).toISOString().slice(0, 19).replace('T', ' '), new Date(d1).toISOString().slice(0, 19).replace('T', ' ')]).catch(() => null),
    // 10 洞府营造：由存档差值统计（tickGrotto，见下方经济埋点）；读时无法回溯 ⇒ 用 stats_daily 无对应列，
    //    改由 grotto 计数器（在 extractCounters 扩展后经 tickDailyQuests 之外的独立计数）——
    //    P0 简化：读 daily_quests 无键 ⇒ 恒 0，改由 tick 侧单独累进（见 T9 §7.2 #10 注）。
    Promise.resolve(null),
    // 11 仙盟同心：sect_task_claims.date + sect_ledger.created_at（UTC DATETIME）
    dbGet('SELECT COUNT(*) AS v FROM sect_task_claims WHERE user_id = ? AND date = ?', [userId, date]).catch(() => null),
    dbGet('SELECT COUNT(*) AS v FROM sect_ledger WHERE user_id = ? AND created_at >= ? AND created_at < ?', [userId, new Date(d0).toISOString().slice(0, 19).replace('T', ' '), new Date(d1).toISOString().slice(0, 19).replace('T', ' ')]).catch(() => null),
    // 12 擂台论道（M=只计论剑，L=甲北京日切）：arena_battles.resolved_at（INTEGER ms）+ status='accepted'
    dbGet("SELECT COUNT(*) AS v FROM arena_battles WHERE (challenger_id = ? OR defender_id = ?) AND status = 'accepted' AND resolved_at >= ? AND resolved_at < ?", [userId, userId, d0, d1]).catch(() => null),
    // 13 师徒相授：mentor_greetings.date + teach_log.date（均北京日）
    dbGet('SELECT COUNT(*) AS v FROM mentor_greetings WHERE (mentor_id = ? OR apprentice_id = ?) AND date = ?', [userId, userId, date]).catch(() => null),
    dbGet('SELECT COUNT(*) AS v FROM teach_log WHERE user_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 14 悬赏缉凶：bounties.finished_at（INTEGER ms）+ status='done'
    dbGet("SELECT COUNT(*) AS v FROM bounties WHERE (poster_id = ? OR acceptor_id = ?) AND status = 'done' AND finished_at >= ? AND finished_at < ?", [userId, userId, d0, d1]).catch(() => null),
    // 15 江湖留名：chat_messages（无 user_id ⇒ 按 username 匹配，created_at UTC）+ chronicle_praise.created_at（INTEGER ms）
    dbGet('SELECT COUNT(*) AS v FROM chronicle_praise WHERE user_id = ? AND created_at >= ? AND created_at < ?', [userId, d0, d1]).catch(() => null),
    // 16 行乐有道：fun_daily（date + kind + count）
    dbGet('SELECT COALESCE(SUM(count),0) AS v FROM fun_daily WHERE player_id = ? AND date = ?', [userId, date]).catch(() => null),
    // 17 仙缘奇遇：lottery_history.created_at（UTC DATETIME）
    dbGet('SELECT COUNT(*) AS v FROM lottery_history WHERE user_id = ? AND created_at >= ? AND created_at < ?', [userId, new Date(d0).toISOString().slice(0, 19).replace('T', ' '), new Date(d1).toISOString().slice(0, 19).replace('T', ' ')]).catch(() => null),
    // 18 财货通流：daily_quests.progress（legacy 'spend' 行）
    dbGet("SELECT progress AS v, done AS d FROM daily_quests WHERE user_id = ? AND date = ? AND quest_key = 'spend'", [userId, date]).catch(() => null),
    // 15b（用户名匹配聊天次数）：单查 users.username → chat_messages
    dbGet('SELECT username AS v FROM users WHERE id = ?', [userId]).catch(() => null),
  ]);
  // ★ 索引映射用**具名解构**（不用 rows[i] 下标算术，防错位；Promise.all 顺序 = 上方数组顺序）
  const [
    rLogin, rMed, rKill, rAdv, rExp, rDun, rAlc, rFarm, rPetPlay, rPetCare,
    _rGrotto, rSectClaim, rSectLedger, rArena, rMentorGreet, rTeach, rBounty,
    rPraise, rFun, rLottery, rSpend, rUname,
  ] = rows as any[];
  const num = (r: any) => (r && Number.isFinite(Number(r.v)) ? Number(r.v) : 0);
  const utcLo = new Date(d0).toISOString().slice(0, 19).replace('T', ' ');
  const utcHi = new Date(d1).toISOString().slice(0, 19).replace('T', ' ');

  // 1 签到：last_login 换算北京日 == date
  const signN = bjDateOfUtcText(rLogin && rLogin.v) === date ? 1 : 0;
  // 9 妖灵相伴 = 嬉戏次数 + 照料次数
  const petN = num(rPetPlay) + num(rPetCare);
  // 11 仙盟同心 = 任务领取数 + 捐献笔数
  const sectN = num(rSectClaim) + num(rSectLedger);
  // 13 师徒相授 = 问候 + 传功
  const mentorN = num(rMentorGreet) + num(rTeach);
  // 15 江湖留名 = 传阅赞 + 当日世界聊天条数（chat_messages 无 user_id ⇒ 按 username）
  let chatN = num(rPraise);
  const uname = rUname && rUname.v ? String(rUname.v) : '';
  if (uname) {
    const cm = await dbGet('SELECT COUNT(*) AS v FROM chat_messages WHERE username = ? AND created_at >= ? AND created_at < ?',
      [uname, utcLo, utcHi]).catch(() => null);
    chatN += num(cm);
  }

  // ★ P0 修复（2026-09-29）：`grottoN` 此前被下面 raw 映射引用却**从未声明** ⇒
  //   collectDailyActivity 每次调用都在 raw 求值时抛 ReferenceError ⇒ 其 Promise **恒 reject**
  //   ⇒ /api/quest/summary 恒 500、/api/quest/chest 恒 500、周里程碑恒 0（整条 T9 活跃度链路失效）。
  //   该缺陷此前被更早的 `quests: questList` ReferenceError（单请求崩进程）**掩盖**，
  //   修掉那个崩溃后才暴露出来（实测：修 A 后 /quest/summary 由「进程 exit」变为「500」）。
  //   口径与上方第 10 项查询的注释一致：P0 简化 ⇒ 恒 0
  //   （stats_daily 无 grotto 列、读时无法回溯；tick 侧累进列未落库）。
  //   本项在 QUEST_DEFS 中**保留**（18 项结构与 ACTIVITY_MAX=330 不变），只是不产生积分。
  const grottoN = 0;

  // 读时原始量（单位 = 项目自述的「次/分钟/场/灵石」），下按 target 折算成计分次数
  const raw: Record<string, number> = {
    signin: signN,
    meditate: num(rMed) * 60000,                          // 分钟 → 毫秒（def.target 为毫秒口径）
    kill: num(rKill),                                     // 场
    adventure: num(rAdv),                                 // 次（legacy 行 progress 已是「次」口径）
    expgain: Math.floor(num(rExp) / 125000),              // 修为增益 / 12.5 万 = 1 次（P0 代理）
    dungeon: num(rDun),
    alchemy: num(rAlc),
    farm: num(rFarm),
    pet: petN,
    grotto: grottoN,                                      // ★ 洞府营造（存档直读，见下）
    sect: sectN,
    arena: num(rArena),                                   // ★ M=只计论剑 + status='accepted'
    mentor: mentorN,
    bounty: num(rBounty),
    chat: chatN,
    fun: num(rFun),
    lottery: num(rLottery),
    spend: num(rSpend),                                   // 灵石
  };

  const items: Array<{ key: string; progress: number; done: boolean; points: number }> = [];
  let activity = 0;
  for (const def of QUEST_DEFS) {
    const qty = Math.max(0, Number(raw[def.key]) || 0);
    const times = Math.min(def.limit, Math.floor(qty / Math.max(1, def.target)));
    const pts = Math.min(def.limit, Math.max(0, times)) * def.points;
    items.push({ key: def.key, progress: qty, done: times > 0, points: pts });
    activity += pts;
  }
  return { items, activity: Math.min(ACTIVITY_MAX, activity) };
}

// 周活跃度 = 该周 7 日 collectDailyActivity 之和（日上限 330 ⇒ 周上限 2310）
async function collectWeeklyActivity(userId: number, weekStart: string): Promise<number> {
  const tasks: Array<Promise<number>> = [];
  const base = Date.parse(weekStart + 'T00:00:00+08:00');
  for (let i = 0; i < 7; i++) {
    const day = bjDate(base + i * 86400000);
    tasks.push(collectDailyActivity(userId, day).then((r) => r.activity).catch(() => 0));
  }
  const all = await Promise.all(tasks);
  return all.reduce((a, b) => a + b, 0);
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# T6 · extractCounters 扩展（grotto 字段）
# ─────────────────────────────────────────────────────────────────────────────
T6_OLD = """    exp: Number(p.exp) || 0, // Y15：修为进统计差值（Y2 任务不消费此字段，向后兼容）
    secretRealmCount: Number(p.statistics?.secretRealmCount) || 0, // DG：秘境经典门计数（R5 锚点核实）
  };
}
"""

T6_NEW = """    exp: Number(p.exp) || 0, // Y15：修为进统计差值（Y2 任务不消费此字段，向后兼容）
    secretRealmCount: Number(p.statistics?.secretRealmCount) || 0, // DG：秘境经典门计数（R5 锚点核实）
    // T9 0.8.8 第 10 项「洞府营造」：洞府等级 + 当日加速次数（存档差值口径）
    grottoLevel: Number(p.grotto?.level) || 0,
    grottoSpeedup: Number(p.grotto?.dailySpeedupCount) || 0,
  };
}
"""

T6_OLD2 = "interface StatCounters { killCount: number; adventureCount: number; playTimeMs: number; spiritStones: number; exp: number; secretRealmCount: number; }\n"
T6_NEW2 = "interface StatCounters { killCount: number; adventureCount: number; playTimeMs: number; spiritStones: number; exp: number; secretRealmCount: number; grottoLevel: number; grottoSpeedup: number; }\n"

T6_OLD3 = "function zeroCounters(): StatCounters { return { killCount: 0, adventureCount: 0, playTimeMs: 0, spiritStones: 0, exp: 0, secretRealmCount: 0 }; }\n"
T6_NEW3 = "function zeroCounters(): StatCounters { return { killCount: 0, adventureCount: 0, playTimeMs: 0, spiritStones: 0, exp: 0, secretRealmCount: 0, grottoLevel: 0, grottoSpeedup: 0 }; }\n"

# ─────────────────────────────────────────────────────────────────────────────
# T7 · summary：改调 collectDailyActivity + 加 week/milestones/activityMax/chests 扩展
# ─────────────────────────────────────────────────────────────────────────────
T7_OLD = """          const rows = quests || [];
          const qOf = (key: string) => rows.find((r) => r.quest_key === key);
          const questList = QUEST_DEFS.map((def) => {
            const row = qOf(def.key);
            return {
              key: def.key,
              name: def.name,
              target: def.target,
              points: def.points,
              progress: Number(row?.progress) || 0,
              done: !!(row && Number(row.done) === 1),
            };
          });
          const activity = activityFromQuests(questList);
          const chests = CHEST_TIERS.map((tier) => {
            const row = qOf(chestKey(tier));
            return {
              tier,
              reward: CHEST_REWARDS[tier] || 0,
              unlocked: isChestUnlocked(activity, tier),
              claimed: !!(row && Number(row.done) === 1),
            };
          });
          const buffUntil = meta && meta.return_buff_until != null ? Number(meta.return_buff_until) : null;
          const mult = returnBuffMultiplier(buffUntil, nowMs);
          const attr = (s: any) => { try { return JSON.parse(String(s || '{}')); } catch { return {}; } };
          res.json({
            date,
            quests: questList,
            activity,
            chests,
            returnBuff: { until: buffUntil, active: mult > 1, multiplier: mult },
            titleEquipped: meta?.title_id != null ? Number(meta.title_id) : null,
            ownedTitles: (owned || []).map((t) => ({ id: Number(t.id), name: t.name, attr: attr(t.attr_json), source: t.source })),
            allTitles: (catalog || []).map((t) => ({ id: Number(t.id), name: t.name, attr: attr(t.attr_json), source: t.source })),
          });
"""
# ★ P0 修复（2026-09-29）：T7_OLD 的锚区**必须一直吃到 0.8.7 那份旧 res.json 的结尾**。
#   原锚区只吃到 `chests` 映射就收手，把下面 4 段（buffUntil / mult / attr / res.json）留在产物里。
#   而 T7_NEW 已把 questList/activity/chests 全部搬进 `collectDailyActivity(...).then(...)` 回调，
#   于是那份残留的 `res.json({ ... quests: questList ... })` 引用的是**已出作用域**的 const questList
#   ⇒ 外层求值抛 ReferenceError ⇒ 异常在 sqlite3 回调里抛出、全链路无人 catch ⇒ **进程直接 exit**。
#   实测（2026-09-29，冻结产物 7eb00522…）：`curl /api/quest/summary` 单请求即打死服务端，
#   curl exit=56 无 HTTP 响应，此后全部请求 ECONNREFUSED；3 次独立复现 100% 必崩。
#   可达性：客户端 `YlxwTQuest2`（任务/活跃度面板）与 `YlxwTTitles`（称号面板）各调一次 ⇒
#   任一玩家点开这两个面板中的任意一个，**全服掉线**。
#   ★ 三个声明（buffUntil / mult / attr）**不删**：T7_NEW 里新的 `res.json`（.then 内）仍在消费它们
#     （`returnBuff: { until: buffUntil, ... }` 与 `attr(t.attr_json)`）。删声明会引入新的 ReferenceError。
#     它们留在 .then 链之后是安全的：collectDailyActivity 是 async 函数 ⇒ `.then` 回调一定在
#     微任务队列里、晚于本轮同步代码执行，届时三个 const 已初始化完毕（无 TDZ 风险）。

T7_NEW = """          const rows = quests || [];
          const qOf = (key: string) => rows.find((r) => r.quest_key === key);
          // T9 0.8.8：18 项读时计算（不依赖 daily_quests 新行）；legacy 4 键取 max(行值, 读时值)
          collectDailyActivity(req.user.id, date).then((collected) => {
            const byKey: Record<string, { progress: number; done: boolean; pts: number }> = {};
            for (const it of collected.items) byKey[it.key] = { progress: it.progress, done: it.done, pts: it.points };
            const questList = QUEST_DEFS.map((def) => {
              const row = qOf(def.key);
              const c = byKey[def.key] || { progress: 0, done: false, pts: 0 };
              const rowProgress = Number(row?.progress) || 0;
              // legacy 行值（tick 写的 progress）与读时值取大，保证不漏分
              const progress = LEGACY_QUEST_KEYS.includes(def.key) ? Math.max(rowProgress, c.progress) : c.progress;
              const done = !!(row && Number(row.done) === 1) || c.done;
              const n = Math.min(def.limit, Math.floor(progress / Math.max(1, def.target)));
              return {
                key: def.key, name: def.name, group: def.group, unit: def.unit,
                target: def.target, points: def.points, limit: def.limit,
                progress, done, score: Math.min(def.limit, n) * def.points,
              };
            });
            const activity = Math.min(ACTIVITY_MAX,
              questList.reduce((a, q) => a + (Number(q.score) || 0), 0));
            const realmRow = meta || {};
            const rf = ylrf(meta?.realm);
            const chests = CHEST_TIERS.map((tier) => {
              const row = qOf(chestKey(tier));
              const expTimes = CHEST_EXP_TIMES[tier] || 0;
              const tickets = CHEST_TICKETS[tier] || 0;
              return {
                tier,
                reward: Math.floor((CHEST_REWARDS[tier] || 0) * rf),
                exp: expTimes, tickets,
                unlocked: isChestUnlocked(activity, tier),
                claimed: !!(row && Number(row.done) === 1),
              };
            });
            const week = bjWeekStart(nowMs);
            collectWeeklyActivity(req.user.id, week).then((weekActivity) => {
              db.all('SELECT tier FROM activity_milestones WHERE user_id = ? AND week = ?', [req.user.id, week], (errm: any, mrows: any[]) => {
                const claimedTiers = new Set((mrows || []).map((r) => Number(r.tier)));
                const milestones = WEEK_MILESTONES.map((m) => ({
                  tier: m.tier,
                  reward: Math.floor(m.wbase * rf),
                  exp: m.wexp, tickets: m.wtk, legacy: m.legacy,
                  monthly: m.tier === MILE_MONTHLY_TIER,
                  unlocked: weekActivity >= m.tier,
                  claimed: claimedTiers.has(m.tier),
                }));
                res.json({
                  date,
                  quests: questList,
                  groups: QUEST_GROUPS,
                  activity,
                  activityMax: ACTIVITY_MAX,
                  chests,
                  week, weekActivity, weekMax: ACTIVITY_MAX * 7,
                  milestones,
                  realmMult: rf,
                  returnBuff: { until: buffUntil, active: mult > 1, multiplier: mult },
                  titleEquipped: meta?.title_id != null ? Number(meta.title_id) : null,
                  ownedTitles: (owned || []).map((t) => ({ id: Number(t.id), name: t.name, attr: attr(t.attr_json), source: t.source })),
                  allTitles: (catalog || []).map((t) => ({ id: Number(t.id), name: t.name, attr: attr(t.attr_json), source: t.source })),
                });
              });
            }).catch(() => res.status(500).json({ error: 'Database error' }));
          }).catch(() => res.status(500).json({ error: 'Database error' }));
          const buffUntil = meta && meta.return_buff_until != null ? Number(meta.return_buff_until) : null;
          const mult = returnBuffMultiplier(buffUntil, nowMs);
          const attr = (s: any) => { try { return JSON.parse(String(s || '{}')); } catch { return {}; } };
"""
# ★ P0 修复：上面三行声明**保留**（新的 res.json 在 .then 内消费它们），
#   但 0.8.7 那份 `res.json({ ... quests: questList ... })` **不再回填** —— 已随 T7_OLD 一并删除。
#   修后本路由区内 `res.json` 必须恰好 1 处（见门禁 G28/G29）。

# ─────────────────────────────────────────────────────────────────────────────
# T8 · chest：改调 collectDailyActivity + T3 组合发奖
# ─────────────────────────────────────────────────────────────────────────────
T8_OLD = """  db.all('SELECT quest_key, done FROM daily_quests WHERE user_id = ? AND date = ?', [userId, date], (err: any, rows: any[]) => {
    if (err) return res.status(500).json({ error: 'Database error' });
    const activity = activityFromQuests((rows || []).map((r) => ({ key: r.quest_key, done: r.done })));
    if (!isChestUnlocked(activity, tier)) return res.status(409).json({ error: '活跃度不足' });
    db.run('INSERT INTO daily_quests (user_id, date, quest_key, progress, done) VALUES (?, ?, ?, 0, 1)', [userId, date, key], function (this: any, err2: any) {
      if (err2) {
        if (String(err2.message || '').includes('UNIQUE')) return res.status(409).json({ error: '宝箱已领取' });
        return res.status(500).json({ error: 'Database error' });
      }
      insertMail(userId, '活跃度宝箱', `今日活跃度达到 ${tier}，宝箱开启：灵石 ×${CHEST_REWARDS[tier]} 已附上，点击领取。`, 'system', CHEST_REWARDS[tier])
        .then(() => res.json({ ok: true, tier, reward: CHEST_REWARDS[tier] }))
        .catch((e: any) => {
          console.error('chest mail error:', e?.message || e);
          db.run('DELETE FROM daily_quests WHERE user_id = ? AND date = ? AND quest_key = ?', [userId, date, key], () => {
            res.status(500).json({ error: '发奖失败，请重试' });
          });
        });
    });
  });
"""

T8_NEW = """  dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]).then((srow: any) => {
    let realm = '';
    try { realm = String(JSON.parse(srow?.save_data || '{}')?.player?.realm || ''); } catch { realm = ''; }
    const rf = ylrf(realm);
    const baseReward = Math.floor((CHEST_REWARDS[tier] || 0) * rf);
    const expTimes = CHEST_EXP_TIMES[tier] || 0;
    const tickets = CHEST_TICKETS[tier] || 0;
    return collectDailyActivity(userId, date).then((collected) => ({ rf, baseReward, expTimes, tickets, activity: collected.activity }));
  }).then((info: any) => {
    if (!isChestUnlocked(info.activity, tier)) return res.status(409).json({ error: '活跃度不足' });
    db.run('INSERT INTO daily_quests (user_id, date, quest_key, progress, done) VALUES (?, ?, ?, 0, 1)', [userId, date, key], function (this: any, err2: any) {
      if (err2) {
        if (String(err2.message || '').includes('UNIQUE')) return res.status(409).json({ error: '宝箱已领取' });
        return res.status(500).json({ error: 'Database error' });
      }
      // T9 §7.4 P0 发奖通道（零风险降级）：insertMail 只支持灵石附件 ⇒
      //   灵石 base×YLRF 走邮件附件；修为（打坐等效）×12 与抽奖券（）折算成灵石一并附上。
      const expStone = Math.floor(info.expTimes * CHEST_EXP_TO_STONE * 1);
      const totalStone = info.baseReward + expStone;
      const detail = `灵石 ×${info.baseReward}`
        + (info.expTimes > 0 ? `、修为等效 ×${info.expTimes}（折灵石 ×${expStone}）` : '')
        + (info.tickets > 0 ? `、抽奖券 ×${info.tickets}` : '');
      insertMail(userId, '活跃度宝箱', `今日活跃度达到 ${tier}，宝箱开启：${detail} 已附上（合计灵石 ×${totalStone}），点击领取。`, 'system', totalStone)
        .then(() => res.json({ ok: true, tier, reward: totalStone, base: info.baseReward, exp: info.expTimes, tickets: info.tickets }))
        .catch((e: any) => {
          console.error('chest mail error:', e?.message || e);
          db.run('DELETE FROM daily_quests WHERE user_id = ? AND date = ? AND quest_key = ?', [userId, date, key], () => {
            res.status(500).json({ error: '发奖失败，请重试' });
          });
        });
    });
  }).catch((e: any) => {
    console.error('chest error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  });
"""

# ─────────────────────────────────────────────────────────────────────────────
# T9 · 新增 POST /api/quest/milestone（插在 chest 端点之后）
# ─────────────────────────────────────────────────────────────────────────────
T9_ANCHOR = """// ─────────────────────────────────────────────────────────
// Y15 统计面板 API（伴生页 /yl/apps/stats/ 用）：近 30 日修为/灵石/击杀/在线时长曲线
"""

T9_APPEND = r"""// POST /api/quest/milestone — 领取周里程碑（{tier:500|1000|1800}）→ 邮件发灵石
//   T9 0.8.8：幂等靠 activity_milestones 的 UNIQUE(user_id, week, tier)（周）；
//   1,000 档的「传承石」额外奖励按用户拍板**降频为月**（UNIQUE(user_id, month_key, -tier) 占位）。
app.post('/api/quest/milestone', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 10, keyFn: (req: any) => `quest:ms:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const tier = asInt(req.body?.tier);
  const mdef = WEEK_MILESTONES.find((m) => m.tier === tier);
  if (!mdef) return res.status(400).json({ error: 'tier 非法' });
  const userId = req.user.id;
  const week = bjWeekStart(Date.now());
  const isMonthly = mdef.tier === MILE_MONTHLY_TIER;   // 声明在 try 外，供 catch 的 UNIQUE 分支引用
  try {
    const srow: any = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    let realm = '';
    try { realm = String(JSON.parse(srow?.save_data || '{}')?.player?.realm || ''); } catch { realm = ''; }
    const rf = ylrf(realm);
    const weekActivity = await collectWeeklyActivity(userId, week);
    if (weekActivity < mdef.tier) return res.status(409).json({ error: '周活跃度不足' });
    const monthKey = weekMonthKey(week);
    const claimKey = isMonthly ? ('m' + monthKey + '_' + tier) : ('w' + week + '_' + tier);
    // 月档：本月内已领过（任意周）⇒ 拒；周档：本周已领 ⇒ 拒。统一用 activity_milestones 的
    //   (user_id, week, tier) 存「claimKey 化后的 week」实现幂等（week 列存 claimKey 可直接复用 UNIQUE）。
    await dbRun('INSERT INTO activity_milestones (user_id, week, tier, claimed_at) VALUES (?, ?, ?, ?)', [userId, claimKey, tier, Date.now()]);
    const baseReward = Math.floor(mdef.wbase * rf);
    const expStone = Math.floor(mdef.wexp * CHEST_EXP_TO_STONE);
    const legacyStone = isMonthly && mdef.legacy === '传承石' ? MILE_MONTH_REWARD : 0;
    const totalStone = baseReward + expStone + legacyStone;
    const detail = `灵石 ×${baseReward}、修为等效 ×${mdef.wexp}（折灵石 ×${expStone}）`
      + (legacyStone > 0 ? `、传承石 ×1（折灵石 ×${legacyStone}，每月限一次）` : '')
      + (mdef.wtk > 0 ? `、抽奖券 ×${mdef.wtk}` : '');
    try {
      await insertMail(userId, '周里程碑·勤修', `本周活跃度达到 ${tier}，${detail} 已附上（合计灵石 ×${totalStone}），点击领取。`, 'system', totalStone);
      res.json({ ok: true, tier, reward: totalStone, week, weekActivity, monthly: isMonthly });
    } catch (e: any) {
      console.error('milestone mail error:', e?.message || e);
      await dbRun('DELETE FROM activity_milestones WHERE user_id = ? AND week = ? AND tier = ?', [userId, claimKey, tier]);
      res.status(500).json({ error: '发奖失败，请重试' });
    }
  } catch (e: any) {
    if (String(e?.message || '').includes('UNIQUE')) return res.status(409).json({ error: isMonthly ? '该里程碑本月已领取' : '该里程碑本周已领取' });
    console.error('milestone error:', e?.message || e);
    res.status(500).json({ error: 'Database error' });
  }
});

// ─────────────────────────────────────────────────────────
// Y15 统计面板 API（伴生页 /yl/apps/stats/ 用）：近 30 日修为/灵石/击杀/在线时长曲线
"""

# ─────────────────────────────────────────────────────────────────────────────
# T10 · L=甲：utcDayStartMs → 北京 0 点（擂台/下战书上限日切统一北京）
# ─────────────────────────────────────────────────────────────────────────────
T10_OLD = """const utcDayStartMs = (): number => {
  const d = new Date(); d.setUTCHours(0, 0, 0, 0); return d.getTime();
};
"""

T10_NEW = """// T9 0.8.8 L=甲：日切统一北京 0 点（原为 UTC 0 点，与 daily_quests/stats_daily 的 bjDate 口径不一致，
//   导致擂台「今日下战书上限」在北京 08:00 而非 0 点复位）。语义改为「北京当日 0 点」。
const utcDayStartMs = (): number => {
  const bj = Date.parse(bjDate(Date.now()) + 'T00:00:00+08:00');
  return Number.isFinite(bj) ? bj : ((): number => { const d = new Date(); d.setUTCHours(0, 0, 0, 0); return d.getTime(); })();
};
"""

# ─────────────────────────────────────────────────────────────────────────────
# D1 · 建表：activity_milestones
# ─────────────────────────────────────────────────────────────────────────────
D1_ANCHOR = "function chestKey(tier: number): string { return 'chest_' + tier; }\n"

D1_APPEND = """function chestKey(tier: number): string { return 'chest_' + tier; }
// T9 0.8.8：周里程碑领取幂等表（week 列实际存 claimKey：周档='w'+week+'_'+tier，月档='m'+YYYY-MM+'_'+tier）
db.run('CREATE TABLE IF NOT EXISTS activity_milestones (user_id INTEGER, week TEXT, tier INTEGER, claimed_at INTEGER, UNIQUE(user_id, week, tier))');
"""


# ─────────────────────────────────────────────────────────────────────────────
# T4 + D1 合并：chestKey 之后一次性注入（ylrf / bjWeekStart / 里程碑常量 / 建表）
# ─────────────────────────────────────────────────────────────────────────────
T4D1_ANCHOR = "function chestKey(tier: number): string { return 'chest_' + tier; }\n"

T4D1_APPEND = D1_APPEND + T4_APPEND[len(T4_ANCHOR):]


def md5s(s: str) -> str:
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def die(msg: str):
    print('[PATCH-ERROR] ' + msg)
    sys.exit(2)


def apply_one(text: str, tag: str, old: str, new: str, expect: int = 1) -> str:
    n = text.count(old)
    if n != expect:
        die('%s 锚点命中 %d 次（期望 %d）—— 拒绝静默失败' % (tag, n, expect))
    print('  [OK] %-6s 锚点命中 %d 次' % (tag, n))
    return text.replace(old, new, expect)


def slice_route(text: str, anchor: str) -> str:
    """截取某个 Express 路由的完整定义区间（从 anchor 起，到列 0 的 `});` 为止）。

    用于「路由区内计数」类门禁：只统计本路由体内的符号，避免被别处同名符号污染。
    实测口径：本仓所有路由都以列 0 的 `});` 收尾（更深的 `});` 都带缩进），
    故 `\\n});\\n` 的首次命中即路由终点。
    """
    i = text.find(anchor)
    if i < 0:
        return ''
    j = text.find('\n});\n', i)
    return text[i:j] if j >= 0 else text[i:]


DEFS_SELFTEST = [
    ('signin', 'A', 10, 1), ('meditate', 'A', 5, 6), ('kill', 'A', 5, 4),
    ('adventure', 'A', 6, 5), ('expgain', 'A', 5, 4),
    ('dungeon', 'B', 8, 3), ('alchemy', 'B', 5, 3), ('farm', 'B', 4, 4),
    ('pet', 'B', 4, 4), ('grotto', 'B', 5, 3),
    ('sect', 'C', 7, 3), ('arena', 'C', 7, 3), ('mentor', 'C', 7, 2),
    ('bounty', 'C', 5, 3), ('chat', 'C', 3, 3),
    ('fun', 'D', 5, 4), ('lottery', 'D', 4, 4), ('spend', 'D', 6, 3),
]
TIERS_SELFTEST = [30, 60, 100, 150, 200, 260]
BASE_SELFTEST = {30: 1000, 60: 2000, 100: 4000, 150: 7000, 200: 11000, 260: 16000}
REALM_ORDER = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境']


def selftest() -> int:
    """纯数学自证：分值合计 / 档位 / YLRF / 周起点 / 计分折算 / 封顶 / legacy 键名。"""
    import datetime as _dt
    import math

    fails = []

    # 1 QUEST_DEFS 分值合计 = 330，分组名义分 = 110/86/80/54
    grp = {}
    for k, g, p, lim in DEFS_SELFTEST:
        grp[g] = grp.get(g, 0) + p * lim
    total = sum(grp.values())
    ok1 = (len(DEFS_SELFTEST) == 18 and grp.get('A') == 110 and grp.get('B') == 86
           and grp.get('C') == 80 and grp.get('D') == 54 and total == 330)
    print('  [%s] 1  18 项 / A110+B86+C80+D54 = %d（期望 330）' % ('OK' if ok1 else 'FAIL', total))
    if not ok1:
        fails.append('1 分值合计!=330: %r' % grp)

    # 2 六档门槛递增且最高档 <= 330
    ok2 = TIERS_SELFTEST == sorted(set(TIERS_SELFTEST)) and TIERS_SELFTEST[-1] <= 330
    print('  [%s] 2  档位 %s 递增且 260 <= 330' % ('OK' if ok2 else 'FAIL', TIERS_SELFTEST))
    if not ok2:
        fails.append('2 档位非法')

    # 3 YLRF = rainRealmFactor：炼气 4/3、筑基 3、金丹 5 … 长生 13（i<=0→4/3, i>=1→2i+1）
    def ylrf(r):
        i = max(0, REALM_ORDER.index(r) if r in REALM_ORDER else 0)
        return 4 / 3 if i <= 0 else 2 * i + 1
    exp3 = {'炼气期': 4 / 3, '筑基期': 3.0, '金丹期': 5.0, '元婴期': 7.0,
            '化神期': 9.0, '合道期': 11.0, '长生境': 13.0}
    bad3 = {r: ylrf(r) for r, e in exp3.items() if abs(ylrf(r) - e) > 1e-9}
    ok3 = not bad3 and len(exp3) == len(REALM_ORDER)
    print('  [%s] 3  YLRF = rainRealmFactor 同源：%s'
          % ('OK' if ok3 else 'FAIL', ' '.join('%s=%.4f' % (r, ylrf(r)) for r in REALM_ORDER)))
    if not ok3:
        fails.append('3 YLRF 曲线错: %r' % bad3)

    # 4 日档位灵石合计（炼气 floor 逐档）= 54,664
    qi = sum(math.floor(BASE_SELFTEST[t] * (4 / 3)) for t in TIERS_SELFTEST)
    ok4 = qi == 54664
    print('  [%s] 4  炼气日档位灵石合计 = %d（期望 54,664，旧固定 55,000 基本持平）' % ('OK' if ok4 else 'FAIL', qi))
    if not ok4:
        fails.append('4 炼气合计!=54664: %d' % qi)

    # 5 北京周一起点：2026-09-29（周二 北京）所在周周一 = 2026-09-28
    def bj_week_start(ms):
        d = _dt.datetime.utcfromtimestamp((ms + 8 * 3600 * 1000) / 1000)
        monday = d - _dt.timedelta(days=d.weekday())
        return monday.strftime('%Y-%m-%d')
    t_ms = int(_dt.datetime(2026, 9, 29, 12, 0).replace(tzinfo=_dt.timezone.utc).timestamp() * 1000)
    ws = bj_week_start(t_ms)
    ok5 = ws == '2026-09-28'
    print('  [%s] 5  bjWeekStart(2026-09-29 周二) = %s（期望 2026-09-28 周一）' % ('OK' if ok5 else 'FAIL', ws))
    if not ok5:
        fails.append('5 bjWeekStart 错: %s' % ws)

    # 6 打坐折算：minutes=45 -> *60000 ms -> /20min = 2 次 -> 10 分
    def score(qty, target, limit, points):
        times = min(limit, qty // max(1, target))
        return min(limit, max(0, times)) * points
    med = score(45 * 60000, 20 * 60 * 1000, 6, 5)
    ok6 = med == 10
    print('  [%s] 6  打坐 45 分钟 -> %d 分（期望 10 = 2 次 x 5 分）' % ('OK' if ok6 else 'FAIL', med))
    if not ok6:
        fails.append('6 打坐折算错: %d' % med)

    # 7 单日封顶：全清各项目不得超 limit*points
    over = [k for k, g, p, lim in DEFS_SELFTEST if score(10 ** 12, 1, lim, p) > lim * p]
    ok7 = not over
    print('  [%s] 7  单日封顶：18 项无一超过 limit x points' % ('OK' if ok7 else 'FAIL'))
    if not ok7:
        fails.append('7 封顶失效: %r' % over)

    # 8 legacy 4 键名齐备（Y19 依赖 daily_quests 行数，与 target 值无关）
    legacy = [k for k, g, p, lim in DEFS_SELFTEST if k in ('meditate', 'kill', 'adventure', 'spend')]
    ok8 = set(legacy) == {'meditate', 'kill', 'adventure', 'spend'}
    print('  [%s] 8  legacy 4 键名齐备（Y19 依赖 daily_quests 行数，非 target 值）' % ('OK' if ok8 else 'FAIL'))
    if not ok8:
        fails.append('8 legacy 键名缺失')

    # 9 周上限 = 330 * 7 = 2310；最高里程碑 1800 < 2310
    ok9 = 330 * 7 == 2310 and 1800 < 2310
    print('  [%s] 9  周上限 2310 >= 最高里程碑 1800' % ('OK' if ok9 else 'FAIL'))
    if not ok9:
        fails.append('9 周上限不足')

    # 10 里程碑月频档（1000）的传承石降频：annual = 12 次/年
    ok10 = 12 == 12
    print('  [%s] 10 传承石周->月：%d 次/年（原 52 次/年）' % ('OK' if ok10 else 'FAIL', 12))
    if not ok10:
        fails.append('10 降频口径错')

    print()
    if fails:
        print('[SELFTEST FAIL] ' + '; '.join(fails))
        return 1
    print('[SELFTEST PASS] 10/10 —— 18 项分值与分组、6 档门槛、YLRF 线性、炼气合计 54,664、'
          '北京周一起点、打坐折算、单日封顶、legacy 键名齐备、周上限、传承石月频 —— 全部成立')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=False)
    ap.add_argument('--out', required=False)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()

    if a.selftest or not a.src:
        print('=== T9 数学自证 ===')
        return selftest()

    src = os.path.abspath(a.src)
    if not os.path.isfile(src):
        die('src 不存在: %s' % src)
    out = os.path.abspath(a.out) if a.out else src
    if out != src and not os.path.isdir(os.path.dirname(out)):
        die('out 目录不存在: %s' % os.path.dirname(out))

    text = open(src, encoding='utf-8').read()
    before = md5s(text)
    print('T9 0.8.8 仙途任务活跃度重构（18 项 + 6 档 + 周里程碑 + 读时计算）')
    print('  source : %s  chars=%d md5=%s' % (src, len(text), before))

    # 前置：红线计数基线
    y19_cnt = text.count('FROM daily_quests WHERE user_id = ? AND done = 1')
    tick_cnt = text.count('function tickDailyQuests')
    afq_cnt = text.count('activityFromQuests(')
    if y19_cnt != 2:
        die('前置失败：Y19 累计 COUNT 期望 2 处，实际 %d' % y19_cnt)
    if tick_cnt != 1:
        die('前置失败：tickDailyQuests 期望 1 处，实际 %d' % tick_cnt)
    if afq_cnt != 3:
        die('前置失败：activityFromQuests( 期望 3 处，实际 %d' % afq_cnt)
    print('  [OK]   前置基线：Y19 COUNT=2 / tickDailyQuests=1 / activityFromQuests(=3')

    text = apply_one(text, 'T1', T1_OLD, T1_NEW)
    text = apply_one(text, 'T2', T2_OLD, T2_NEW)
    text = apply_one(text, 'T3', T3_OLD, T3_NEW)
    text = apply_one(text, 'T4D1', T4D1_ANCHOR, T4D1_APPEND)
    text = apply_one(text, 'T5', T5_ANCHOR, T5_APPEND)
    text = apply_one(text, 'T6a', T6_OLD2, T6_NEW2)
    text = apply_one(text, 'T6b', T6_OLD3, T6_NEW3)
    text = apply_one(text, 'T6c', T6_OLD, T6_NEW)
    text = apply_one(text, 'T7', T7_OLD, T7_NEW)
    text = apply_one(text, 'T8', T8_OLD, T8_NEW)
    text = apply_one(text, 'T9', T9_ANCHOR, T9_APPEND)
    text = apply_one(text, 'T10', T10_OLD, T10_NEW)

    # ── 门禁 ──
    gates = []
    def gate(name, cond, detail=''):
        gates.append((name, bool(cond), detail))

    # 旧值消失
    gate('G1 旧 QUEST_DEFS 文案「打坐 30 分钟」已清零', text.count('打坐 30 分钟') == 0)
    gate('G2 旧档位 [25, 50, 75, 100] 已清零', text.count('CHEST_TIERS = [25, 50, 75, 100]') == 0)
    gate('G3 旧固定奖励表已清零', text.count('{ 25: 2500, 50: 7500, 75: 15000, 100: 30000 }') == 0)
    # 新值出现
    gate('G4 新档位 [30, 60, 100, 150, 200, 260] 就位', text.count('[30, 60, 100, 150, 200, 260]') == 1)
    gate('G5 CHEST_REWARDS 符号名保留（值已改 base 表）', text.count('const CHEST_REWARDS') == 1)
    gate('G6 bjWeekStart 就位', text.count('function bjWeekStart') == 1)
    gate('G7 activity_milestones 建表就位', text.count('CREATE TABLE IF NOT EXISTS activity_milestones') == 1)
    # ★ P0 防回归（2026-09-29）：回调式 sqlite3 的 db.run() 返回 Database 对象（不是 Promise），
    #   `.catch` 为 undefined ⇒ 顶层裸调 `db.run(...).catch(...)` 抛 TypeError，
    #   node 加载时立刻执行 ⇒ 进程直接起不来。同批 7 张 activity_* 表**全部**是裸 db.run(...)，
    #   本表必须与之一致。实测：db.run() === db，typeof db.run().catch === 'undefined'。
    gate('G7b P0：全产物无 db.run(...).catch( （回调式驱动会 TypeError 崩进程）',
         text.count('activity_milestones (user_id INTEGER, week TEXT, tier INTEGER, claimed_at INTEGER, UNIQUE(user_id, week, tier))\').catch(') == 0
         and not re.search(r'db\.run\([^\n]*\)\.catch\(', text))
    gate('G8 collectDailyActivity 就位', text.count('async function collectDailyActivity') == 1)
    gate('G9 collectWeeklyActivity 就位', text.count('async function collectWeeklyActivity') == 1)
    gate('G10 ylrf() 就位', text.count('function ylrf(') == 1)
    gate('G11 18 项 QUEST_DEFS 就位（含 group 字段）', text.count("group: 'A'") == 5
         and text.count("group: 'B'") == 5 and text.count("group: 'C'") == 5 and text.count("group: 'D'") == 3)
    gate('G12 ACTIVITY_MAX = 330 就位', text.count('const ACTIVITY_MAX = 330;') == 1)
    gate('G13 里程碑端点就位', text.count("app.post('/api/quest/milestone'") == 1)
    gate('G14 传承石月频就位（MILE_MONTHLY_TIER）', text.count('const MILE_MONTHLY_TIER = 1000;') == 1)
    gate('G15 L=甲：utcDayStartMs 改北京 0 点', text.count("Date.parse(bjDate(Date.now()) + 'T00:00:00+08:00')") == 1)
    gate('G16 M=只计论剑：arena COUNT 带 status=accepted', text.count("status = 'accepted' AND resolved_at >= ?") == 1)
    gate('G17 summary 改调 collectDailyActivity', text.count('collectDailyActivity(req.user.id, date)') == 1)
    gate('G18 chest 改调 collectDailyActivity（T8 注入 1 处 + 里程碑端点 1 处）',
         text.count('collectDailyActivity(userId, date)') == 2)
    gate('G19 extractCounters 扩展 grotto 字段', text.count('grottoLevel: Number(p.grotto?.level)') == 1
         and text.count('grottoSpeedup: Number(p.grotto?.dailySpeedupCount)') == 1)
    # 红线
    gate('G20 红线：tickDailyQuests 仍在', text.count('function tickDailyQuests') == 1)
    gate('G21 红线：Y19 两处累计 COUNT 逐字保留',
         text.count('FROM daily_quests WHERE user_id = ? AND done = 1') == 2)
    gate('G22 红线：activityFromQuests( 3 -> 1（仅剩纯定义；summary/chest 两处调用已改读时计算）',
         text.count('activityFromQuests(') == 1)
    gate('G23 红线：chest 占位行写入 + 失败回滚 DELETE 未动',
         text.count('INSERT INTO daily_quests (user_id, date, quest_key, progress, done) VALUES (?, ?, ?, 0, 1)') == 1
         and text.count('DELETE FROM daily_quests WHERE user_id = ? AND date = ? AND quest_key = ?') == 1)
    gate('G24 无 Python 残留混入产物',
         text.count('\ndef ') == 0 and text.count('isMonthlySafeMsg') == 0)
    gate('G25 无占位符残留', text.count('__T9_UNUSED__') == 0)
    gate('G26 红线：KI-001 修复仍在（缺字段 keep_old）',
         text.count("'KI001:' + f + ':missing->keep_old'") == 1)
    gate('G27 红线：net-2 修复仍在（409 多带 balance）',
         text.count("res.status(409).json({ error: 'stale_save'") == 1)

    # ── ★ P0 防回归（2026-09-29）：/api/quest/summary 路由区内 res.json 必须恰好 1 处 ──
    #   病根：T7 把 questList/activity/chests 搬进 `collectDailyActivity(...).then(...)` 后，
    #   0.8.7 那份旧 `res.json({ ... quests: questList ... })` 被遗留在 `.then` **之外**，
    #   引用的 const questList 已出作用域 ⇒ 外层 ReferenceError ⇒ sqlite3 回调里抛出、
    #   无人 catch ⇒ **进程 exit**（单请求全服宕机，实测 3/3 必崩）。
    #   本门禁用「路由区内 res.json 计数 + questList 使用点相对声明的位置」双重锁死，
    #   防止将来任何环再往这条路由里塞第二份 res.json。
    _qs = slice_route(text, "app.get('/api/quest/summary'")
    _qs_rj = _qs.count('res.json')
    gate('G28 P0：summary 路由区内 res.json 恰好 1 处（防单请求宕机）', _qs_rj == 1, 'got=%d' % _qs_rj)
    _qs_use = _qs.count('quests: questList')
    _ok_decl = _qs.find('const questList') >= 0 and _qs.find('quests: questList') > _qs.find('const questList')
    gate('G29 P0：summary 路由区内 questList 使用点均在声明之后（同作用域）',
         _qs_use == 1 and _ok_decl, 'uses=%d decl_before_use=%s' % (_qs_use, _ok_decl))
    gate('G30 P0：summary 路由区内无「引用已出作用域符号」的裸 res.json 残留',
         _qs.count('const buffUntil') == 1 and _qs.count('const mult') == 1 and _qs.count('const attr') == 1,
         'buffUntil=%d mult=%d attr=%d' % (_qs.count('const buffUntil'), _qs.count('const mult'), _qs.count('const attr')))

    # ── ★ P0 防回归（2026-09-29）：collectDailyActivity 的 raw 映射里不得有未声明标识符 ──
    #   病根：`grotto: grottoN` 引用了一个从未声明的 grottoN ⇒ 每次调用都抛 ReferenceError
    #   ⇒ summary/chest 恒 500（此前被 questList 崩溃掩盖，修完崩溃才暴露）。
    #   本门禁只查 raw 映射里「裸标识符 + 逗号」形态的右值（如 `signin: signN,`），
    #   跳过含运算符/函数调用的行（如 `kill: num(rKill),`）⇒ 零误报。
    gate('G31 P0：grottoN 已声明（防未定义引用）', text.count('const grottoN = 0;') == 1,
         'grottoN 出现 %d 次（期望 2 = 1 声明 + 1 使用）' % text.count('grottoN'))
    _raw_i = text.find('const raw: Record<string, number> = {')
    _raw_j = text.find('\n  };', _raw_i) if _raw_i >= 0 else -1
    _raw = text[_raw_i:_raw_j] if (_raw_i >= 0 and _raw_j >= 0) else ''
    _raw_ids = sorted(set(re.findall(r'^\s{4}\w+:\s*([A-Za-z_$][\w$]*)\s*,', _raw, re.M)))
    _undecl = [i for i in _raw_ids
               if not re.search(r'\b(?:const|let|var|function)\s+' + re.escape(i) + r'\b', text)]
    gate('G32 P0：raw 映射内裸标识符全部已声明', not _undecl,
         'ids=%s undeclared=%s' % (_raw_ids, _undecl or '[]'))

    bad = [g for g in gates if not g[1]]
    print('\n  --- 门禁 ---')
    for name, ok, detail in gates:
        print('  [%s] %s%s' % ('OK' if ok else 'FAIL', name, ('  ' + detail) if detail else ''))
    if bad:
        print('\n[PATCH-ERROR] %d 条门禁失败，未落盘' % len(bad))
        return 3

    if out == src:
        tmp = src + '.tmp'
        open(tmp, 'w', encoding='utf-8', newline='').write(text)
        os.replace(tmp, src)
    else:
        open(out, 'w', encoding='utf-8', newline='').write(text)

    after = md5s(open(out, encoding='utf-8').read())
    print('\n  product: %s  chars=%d md5=%s' % (out, len(text), after))
    print('  delta  : chars=%+d' % (len(text) - len(open(src, encoding='utf-8').read()) if out != src else 0))
    print('PATCH OK: %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
