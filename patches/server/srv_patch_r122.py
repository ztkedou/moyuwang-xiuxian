# -*- coding: utf-8 -*-
r"""
srv_patch_r122.py -- R-122 仙务成就 4 档→10 档（服务端 · SRV_CHAIN 新环）

台账原文（R-122，逐字）
--------------------------------------------------------------------------
  「仙务成就 中高里程碑获得的灵石数量太少了。毕竟每一项只有4个档位。
    每一项的档位加多到10个，加多高档位奖励的内容，毕竟越往上完成难度越高。」

实现口径（0.9.13 数值表 §6，逐项落地）
--------------------------------------------------------------------------
  · 简报所称 ACH_REWARD_TIERS=[200,500,1000,2000] 是**死常量**（全文仅定义 1 处、
    零消费点）——真实档位表 = ACH_DEFS（侦察纠正，2026-10-02 实读 srv/index_v28.ts
    = 0.9.12 线上 b2e472c5…）。本环扩 ACH_DEFS：每类 4→10 行，共 20→50 行。
  · 奖励阶梯（五类通用，灵石）：[500,1200,2500,4500,7000,10000,15000,22000,32000,50000]
    单类 Σ=144,700（旧 16,000）；五类全清 = 723,500（旧 80,000）。
  · 目标阶梯（严格单调）：
      修行=累计在线分钟  60/300/1200/3000/7000/15000/30000/60000/100000/150000
      战斗=累计胜利场次  10/50/200/500/1200/2500/5000/10000/18000/30000
      财富=累计灵石获取  1万/10万/100万/300万/800万/2000万/5000万/1.2亿/2.5亿/5亿
      任务=累计每日任务  1/10/50/150/350/700/1200/2000/3000/5000
      境界=总等级(境界序×9+层)  3/10/19/28/37/46/52/56/60/63
  · 境界组 metric 由 realmIndex（0..6，只有 7 档容量）改为 totalLevel=境界序×9+层
    （rankings 口径；save.player.realm 与 save.player.realmLevel 同源，两端点就地补算）。
    achTotalsFrom 加 totalLevel 字段（纯钳制契约不变），AchMetric 联合类型加成员。
  · 旧 id 语义保持：每类前 3 档 id/target/name/desc 原样保留（reward 按新阶梯调整）；
    旧第 4 档（cultivate_6000/battle_1000/wealth_1e7/quest_200/realm_*）退役。
    新 id 沿用 <group>_<target> 序号制（数值表建议），不复用旧 id 改语义。
    线上库已清空（2026-10-02，备份 /root/backup/database_pre_cleanup_20261002_011944.sqlite）
    ⇒ 无存量 claim 迁移负担；achievement_claimed 主键 user_id+ach_id 天然兼容 50 项。
  · 客户端零改动：YlxwTAch 全量渲染服务端 groups（bundle 实读 claimableIds 三处同函数），
    新档位经 /api/achievements 自然下发；claim 端点的幂等占位（INSERT OR IGNORE）与
    补偿（DELETE 占位）逻辑一字不动。
  · 无档玩家 totalLevel=0（< 首档 3，不误发）；有档 = max(1,floor(realmLevel))，与
    extractRankingData 的 `|| 1` 口径一致。

CLI 契约（照 srv_patch_r124.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径（写回前生成 .bak-r122-<时间戳>）；
  `--check` / `--selftest` 只校验不写。幂等：产物含 [r122ach10] 则 SKIP。
  lead 接线：SRV_CHAIN 追加 'srv_patch_r122.py'（锚点全在基座段，
  recon 全扫无既有补丁归属；排在任意位置均可，建议随 R-123/R-127/128/R-116/R-129 同批）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403) / setInterval / PRAGMA。
  · 不改 srv/index_v28.ts 共享产物（lead 跑本环时对链产物写回）；不改任何既有 srv_patch_*.py。
  · 每处替换带精确 expect（唯一锚点 expect=1、共用调用行 expect=2），命中数不符即中止；
    语义自证（50 行逐行比对数值表）+ round-trip 自证通过后才原子写回。
"""

import argparse
import io
import os
import re
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r122ach10]"

# ============================================================ 新 ACH_DEFS（50 行）

NEW_ACH_DEFS = r"""const ACH_DEFS: AchDef[] = [
  // 修行：累计 stats_daily.minutes（在线分钟=打坐时长的服务端可见代理）[r122] 4→10 档
  { id: 'cultivate_60', group: 'cultivate', name: '初窥门径', desc: '累计在线 60 分钟', target: 60, reward: 500 },
  { id: 'cultivate_300', group: 'cultivate', name: '潜心修行', desc: '累计在线 300 分钟', target: 300, reward: 1200 },
  { id: 'cultivate_1200', group: 'cultivate', name: '闭关苦修', desc: '累计在线 20 小时', target: 1200, reward: 2500 },
  { id: 'cultivate_3000', group: 'cultivate', name: '水磨功夫', desc: '累计在线 50 小时', target: 3000, reward: 4500 },
  { id: 'cultivate_7000', group: 'cultivate', name: '枯禅入定', desc: '累计在线 7000 分钟', target: 7000, reward: 7000 },
  { id: 'cultivate_15000', group: 'cultivate', name: '心斋坐忘', desc: '累计在线 250 小时', target: 15000, reward: 10000 },
  { id: 'cultivate_30000', group: 'cultivate', name: '禅定不移', desc: '累计在线 500 小时', target: 30000, reward: 15000 },
  { id: 'cultivate_60000', group: 'cultivate', name: '老僧入定', desc: '累计在线 1000 小时', target: 60000, reward: 22000 },
  { id: 'cultivate_100000', group: 'cultivate', name: '静水深流', desc: '累计在线 10 万分钟', target: 100000, reward: 32000 },
  { id: 'cultivate_150000', group: 'cultivate', name: '与道合真', desc: '累计在线 2500 小时', target: 150000, reward: 50000 },
  // 战斗：累计 stats_daily.kills（战斗胜利场次）[r122] 4→10 档
  { id: 'battle_10', group: 'battle', name: '初试锋芒', desc: '累计战斗胜利 10 场', target: 10, reward: 500 },
  { id: 'battle_50', group: 'battle', name: '身经百战', desc: '累计战斗胜利 50 场', target: 50, reward: 1200 },
  { id: 'battle_200', group: 'battle', name: '杀伐果断', desc: '累计战斗胜利 200 场', target: 200, reward: 2500 },
  { id: 'battle_500', group: 'battle', name: '百战成钢', desc: '累计战斗胜利 500 场', target: 500, reward: 4500 },
  { id: 'battle_1200', group: 'battle', name: '千锤百炼', desc: '累计战斗胜利 1200 场', target: 1200, reward: 7000 },
  { id: 'battle_2500', group: 'battle', name: '战无不胜', desc: '累计战斗胜利 2500 场', target: 2500, reward: 10000 },
  { id: 'battle_5000', group: 'battle', name: '攻无不克', desc: '累计战斗胜利 5000 场', target: 5000, reward: 15000 },
  { id: 'battle_10000', group: 'battle', name: '一骑当千', desc: '累计战斗胜利 1 万场', target: 10000, reward: 22000 },
  { id: 'battle_18000', group: 'battle', name: '万夫莫开', desc: '累计战斗胜利 1.8 万场', target: 18000, reward: 32000 },
  { id: 'battle_30000', group: 'battle', name: '天下无敌', desc: '累计战斗胜利 3 万场', target: 30000, reward: 50000 },
  // 财富：累计 stats_daily.silver_gain（灵石净获取，含邮件/宝箱/GM 入账）[r122] 4→10 档
  { id: 'wealth_1e4', group: 'wealth', name: '小有积蓄', desc: '累计获取灵石 1 万', target: 10000, reward: 500 },
  { id: 'wealth_1e5', group: 'wealth', name: '家财万贯', desc: '累计获取灵石 10 万', target: 100000, reward: 1200 },
  { id: 'wealth_1e6', group: 'wealth', name: '富可敌国', desc: '累计获取灵石 100 万', target: 1000000, reward: 2500 },
  { id: 'wealth_3e6', group: 'wealth', name: '日进斗金', desc: '累计获取灵石 300 万', target: 3000000, reward: 4500 },
  { id: 'wealth_8e6', group: 'wealth', name: '堆金积玉', desc: '累计获取灵石 800 万', target: 8000000, reward: 7000 },
  { id: 'wealth_2e7', group: 'wealth', name: '仙门首富', desc: '累计获取灵石 2000 万', target: 20000000, reward: 10000 },
  { id: 'wealth_5e7', group: 'wealth', name: '富甲天下', desc: '累计获取灵石 5000 万', target: 50000000, reward: 15000 },
  { id: 'wealth_12e7', group: 'wealth', name: '金玉满堂', desc: '累计获取灵石 1.2 亿', target: 120000000, reward: 22000 },
  { id: 'wealth_25e7', group: 'wealth', name: '灵石成海', desc: '累计获取灵石 2.5 亿', target: 250000000, reward: 32000 },
  { id: 'wealth_5e8', group: 'wealth', name: '仙界财神', desc: '累计获取灵石 5 亿', target: 500000000, reward: 50000 },
  // 任务：累计 daily_quests 完成（done=1 的任务行，不含宝箱领取占位行）[r122] 4→10 档
  { id: 'quest_1', group: 'quest', name: '小试牛刀', desc: '累计完成每日任务 1 个', target: 1, reward: 500 },
  { id: 'quest_10', group: 'quest', name: '勤修不辍', desc: '累计完成每日任务 10 个', target: 10, reward: 1200 },
  { id: 'quest_50', group: 'quest', name: '任务达人', desc: '累计完成每日任务 50 个', target: 50, reward: 2500 },
  { id: 'quest_150', group: 'quest', name: '日积月累', desc: '累计完成每日任务 150 个', target: 150, reward: 4500 },
  { id: 'quest_350', group: 'quest', name: '恒心毅力', desc: '累计完成每日任务 350 个', target: 350, reward: 7000 },
  { id: 'quest_700', group: 'quest', name: '仙途楷模', desc: '累计完成每日任务 700 个', target: 700, reward: 10000 },
  { id: 'quest_1200', group: 'quest', name: '卷中豪杰', desc: '累计完成每日任务 1200 个', target: 1200, reward: 15000 },
  { id: 'quest_2000', group: 'quest', name: '勤能补拙', desc: '累计完成每日任务 2000 个', target: 2000, reward: 22000 },
  { id: 'quest_3000', group: 'quest', name: '初心如磐', desc: '累计完成每日任务 3000 个', target: 3000, reward: 32000 },
  { id: 'quest_5000', group: 'quest', name: '仙途无悔', desc: '累计完成每日任务 5000 个', target: 5000, reward: 50000 },
  // 境界：saves 存档总等级达标（总等级=境界序×9+层数，rankings 口径；[r122] realmIndex→totalLevel，7 档容量→10 档）
  { id: 'realm_3', group: 'realm', name: '初入仙途', desc: '总等级达到 3（炼气三层）', target: 3, reward: 500 },
  { id: 'realm_10', group: 'realm', name: '筑基功成', desc: '总等级达到 10（筑基期一层）', target: 10, reward: 1200 },
  { id: 'realm_19', group: 'realm', name: '金丹初成', desc: '总等级达到 19（金丹期一层）', target: 19, reward: 2500 },
  { id: 'realm_28', group: 'realm', name: '元婴出窍', desc: '总等级达到 28（元婴期一层）', target: 28, reward: 4500 },
  { id: 'realm_37', group: 'realm', name: '化神通玄', desc: '总等级达到 37（化神期一层）', target: 37, reward: 7000 },
  { id: 'realm_46', group: 'realm', name: '合道之始', desc: '总等级达到 46（合道期一层）', target: 46, reward: 10000 },
  { id: 'realm_52', group: 'realm', name: '合道七重', desc: '总等级达到 52（合道期七层）', target: 52, reward: 15000 },
  { id: 'realm_56', group: 'realm', name: '长生之初', desc: '总等级达到 56（长生境二层）', target: 56, reward: 22000 },
  { id: 'realm_60', group: 'realm', name: '长生六重', desc: '总等级达到 60（长生境六层）', target: 60, reward: 32000 },
  { id: 'realm_63', group: 'realm', name: '长生久视', desc: '总等级达到 63（长生境九层·圆满）', target: 63, reward: 50000 },
]; // [r122ach10] R-122 五类各 4→10 档（0.9.13 数值表 §6）；单类 Σ144,700 / 全清 723,500；旧第 4 档退役（线上库已清空，无迁移负担）"""

# ============================================================ 旧 ACH_DEFS（2026-10-02 实读 0.9.12 产物逐字节；count 必须 =1）

OLD_ACH_DEFS = """const ACH_DEFS: AchDef[] = [
  // 修行：累计 stats_daily.minutes（在线分钟=打坐时长的服务端可见代理）
  { id: 'cultivate_60', group: 'cultivate', name: '初窥门径', desc: '累计在线 60 分钟', target: 60, reward: 500 },
  { id: 'cultivate_300', group: 'cultivate', name: '潜心修行', desc: '累计在线 300 分钟', target: 300, reward: 1500 },
  { id: 'cultivate_1200', group: 'cultivate', name: '闭关苦修', desc: '累计在线 20 小时', target: 1200, reward: 4000 },
  { id: 'cultivate_6000', group: 'cultivate', name: '枯禅入定', desc: '累计在线 100 小时', target: 6000, reward: 10000 },
  // 战斗：累计 stats_daily.kills（战斗胜利场次）
  { id: 'battle_10', group: 'battle', name: '初试锋芒', desc: '累计战斗胜利 10 场', target: 10, reward: 500 },
  { id: 'battle_50', group: 'battle', name: '身经百战', desc: '累计战斗胜利 50 场', target: 50, reward: 1500 },
  { id: 'battle_200', group: 'battle', name: '杀伐果断', desc: '累计战斗胜利 200 场', target: 200, reward: 4000 },
  { id: 'battle_1000', group: 'battle', name: '战无不胜', desc: '累计战斗胜利 1000 场', target: 1000, reward: 10000 },
  // 财富：累计 stats_daily.silver_gain（灵石净获取，含邮件/宝箱/GM 入账）
  { id: 'wealth_1e4', group: 'wealth', name: '小有积蓄', desc: '累计获取灵石 1 万', target: 10000, reward: 500 },
  { id: 'wealth_1e5', group: 'wealth', name: '家财万贯', desc: '累计获取灵石 10 万', target: 100000, reward: 1500 },
  { id: 'wealth_1e6', group: 'wealth', name: '富可敌国', desc: '累计获取灵石 100 万', target: 1000000, reward: 4000 },
  { id: 'wealth_1e7', group: 'wealth', name: '仙门首富', desc: '累计获取灵石 1000 万', target: 10000000, reward: 10000 },
  // 任务：累计 daily_quests 完成（done=1 的任务行，不含宝箱领取占位行）
  { id: 'quest_1', group: 'quest', name: '小试牛刀', desc: '累计完成每日任务 1 个', target: 1, reward: 500 },
  { id: 'quest_10', group: 'quest', name: '勤修不辍', desc: '累计完成每日任务 10 个', target: 10, reward: 1500 },
  { id: 'quest_50', group: 'quest', name: '任务达人', desc: '累计完成每日任务 50 个', target: 50, reward: 4000 },
  { id: 'quest_200', group: 'quest', name: '仙途楷模', desc: '累计完成每日任务 200 个', target: 200, reward: 10000 },
  // 境界：saves 存档 realm 达标（target=境界序；任务书"大乘"不存在于本游戏境界表 → 以最高境"长生境"压轴）
  { id: 'realm_jindan', group: 'realm', name: '金丹初成', desc: '境界达到金丹期', target: ACH_REALM_ORDER.indexOf('金丹期'), reward: 500 },
  { id: 'realm_yuanying', group: 'realm', name: '元婴出窍', desc: '境界达到元婴期', target: ACH_REALM_ORDER.indexOf('元婴期'), reward: 1500 },
  { id: 'realm_huashen', group: 'realm', name: '化神通玄', desc: '境界达到化神期', target: ACH_REALM_ORDER.indexOf('化神期'), reward: 4000 },
  { id: 'realm_changsheng', group: 'realm', name: '长生久视', desc: '境界达到长生境', target: ACH_REALM_ORDER.indexOf('长生境'), reward: 10000 },
];"""

# ============================================================ 改动点（name, old, new, expect）

EDITS = [
    # E1 Y19 段头注释（含死常量阶梯说明，同步改真值并登记死常量事实）
    ("E1 Y19段头注释",
     "// ── Y19 成就系统：五类各 4 项共 20 项，达成状态从 stats_daily/daily_quests/saves 惰性推导（零新增埋点）；\n"
     "// 领取记录 achievement_claimed 主键幂等防重复领奖；奖励=灵石阶梯 200/500/1000/2000（本次定档，常量集中可调）──\n",
     "// ── Y19 成就系统：五类各 10 项共 50 项，达成状态从 stats_daily/daily_quests/saves 惰性推导（零新增埋点）；[r122] 4→10 档\n"
     "// 领取记录 achievement_claimed 主键幂等防重复领奖；奖励=灵石阶梯 500/1200/2500/4500/7000/10000/15000/22000/32000/50000"
     "（R-122 定档，单类 Σ144,700 / 全清 723,500；下方 ACH_REWARD_TIERS 为历史死常量、零消费点，未动）──\n",
     1),
    # E2 端点段头注释（伴生页说明行）
    ("E2 端点段注释",
     "// Y19 成就系统 API（伴生页 /yl/apps/ach/ 用）：五类各 4 项共 20 项，达成从 stats_daily/daily_quests/saves\n",
     "// Y19 成就系统 API（伴生页 /yl/apps/ach/ 用）：五类各 10 项共 50 项，达成从 stats_daily/daily_quests/saves\n",
     1),
    # E3 AchMetric 联合类型 +totalLevel
    ("E3 AchMetric类型",
     "type AchMetric = 'minutes' | 'kills' | 'silver' | 'quests' | 'realmIndex';",
     "type AchMetric = 'minutes' | 'kills' | 'silver' | 'quests' | 'realmIndex' | 'totalLevel'; // [r122] +totalLevel（境界组 10 档度量）",
     1),
    # E4 ACH_GROUPS 境界组换 metric
    ("E4 境界组metric",
     "  { key: 'realm', name: '境界', metric: 'realmIndex' },\n",
     "  { key: 'realm', name: '境界', metric: 'totalLevel' }, // [r122] realmIndex(0..6) 只有 7 档容量 → 总等级=境界序×9+层（rankings 口径）\n",
     1),
    # E5 AchTotals +totalLevel
    ("E5 AchTotals",
     "interface AchTotals { minutes: number; kills: number; silver: number; quests: number; realmIndex: number; }",
     "interface AchTotals { minutes: number; kills: number; silver: number; quests: number; realmIndex: number; totalLevel: number; } // [r122] +totalLevel",
     1),
    # E6 achTotalsFrom 输入/输出 +totalLevel（纯钳制契约不变）
    ("E6 achTotalsFrom",
     "function achTotalsFrom(t: { minutes?: unknown; kills?: unknown; silver?: unknown; quests?: unknown; realmIndex?: unknown }): AchTotals {\n"
     "  const n = (v: unknown) => { const x = Number(v); return Number.isFinite(x) ? Math.max(0, Math.floor(x)) : 0; };\n"
     "  return { minutes: n(t.minutes), kills: n(t.kills), silver: n(t.silver), quests: n(t.quests), realmIndex: n(t.realmIndex) };\n"
     "}",
     "function achTotalsFrom(t: { minutes?: unknown; kills?: unknown; silver?: unknown; quests?: unknown; realmIndex?: unknown; totalLevel?: unknown }): AchTotals {\n"
     "  const n = (v: unknown) => { const x = Number(v); return Number.isFinite(x) ? Math.max(0, Math.floor(x)) : 0; };\n"
     "  return { minutes: n(t.minutes), kills: n(t.kills), silver: n(t.silver), quests: n(t.quests), realmIndex: n(t.realmIndex), totalLevel: n(t.totalLevel) }; // [r122] +totalLevel\n"
     "}",
     1),
    # E7 GET /api/achievements 存档解析：补 realmLevel（与 rankings 的 ||1 口径一致）
    ("E7 GET存档解析",
     "    let realmIndex = -1;\n"
     "    let realmName = '未开始';\n"
     "    if (saveRow) {\n"
     "      try {\n"
     "        const r = JSON.parse(String(saveRow.save_data))?.player?.realm;\n"
     "        const i = typeof r === 'string' ? REALM_ORDER_FOR_RANKING.indexOf(r) : -1;\n"
     "        if (i >= 0) { realmIndex = i; realmName = r; }\n"
     "      } catch { /* 坏存档按无境界处理，不阻塞列表 */ }\n"
     "    }",
     "    let realmIndex = -1;\n"
     "    let realmLevel = 1; // [r122] 当层层数（save.player.realmLevel，与 rankings 同源；无档=1）\n"
     "    let realmName = '未开始';\n"
     "    if (saveRow) {\n"
     "      try {\n"
     "        const p = JSON.parse(String(saveRow.save_data))?.player;\n"
     "        const r = p?.realm;\n"
     "        const i = typeof r === 'string' ? REALM_ORDER_FOR_RANKING.indexOf(r) : -1;\n"
     "        if (i >= 0) {\n"
     "          realmIndex = i; realmName = r;\n"
     "          const lv = Math.floor(Number(p?.realmLevel));\n"
     "          if (Number.isFinite(lv)) realmLevel = Math.max(1, lv);\n"
     "        }\n"
     "      } catch { /* 坏存档按无境界处理，不阻塞列表 */ }\n"
     "    }",
     1),
    # E8 POST /api/achievements/claim 存档解析：同上（claim 服务端重算达成，必须同口径）
    ("E8 POST存档解析",
     "    let realmIndex = -1;\n"
     "    if (saveRow) {\n"
     "      try {\n"
     "        const r = JSON.parse(String(saveRow.save_data))?.player?.realm;\n"
     "        realmIndex = typeof r === 'string' ? REALM_ORDER_FOR_RANKING.indexOf(r) : -1;\n"
     "      } catch { /* 坏存档按无境界处理 */ }\n"
     "    }",
     "    let realmIndex = -1;\n"
     "    let realmLevel = 1; // [r122] 当层层数（save.player.realmLevel，与 rankings 同源；无档=1）\n"
     "    if (saveRow) {\n"
     "      try {\n"
     "        const p = JSON.parse(String(saveRow.save_data))?.player;\n"
     "        const r = p?.realm;\n"
     "        realmIndex = typeof r === 'string' ? REALM_ORDER_FOR_RANKING.indexOf(r) : -1;\n"
     "        if (realmIndex >= 0) {\n"
     "          const lv = Math.floor(Number(p?.realmLevel));\n"
     "          if (Number.isFinite(lv)) realmLevel = Math.max(1, lv);\n"
     "        }\n"
     "      } catch { /* 坏存档按无境界处理 */ }\n"
     "    }",
     1),
    # E9 两处 achTotalsFrom 调用行（GET+POST 共用形态，expect=2）：传 totalLevel（无档=0）
    ("E9 调用行x2",
     "      achTotalsFrom({ minutes: sum?.m, kills: sum?.k, silver: sum?.s, quests: questCnt?.c, realmIndex }),\n",
     "      achTotalsFrom({ minutes: sum?.m, kills: sum?.k, silver: sum?.s, quests: questCnt?.c, realmIndex, totalLevel: realmIndex >= 0 ? realmIndex * 9 + realmLevel : 0 }), // [r122] 总等级=境界序×9+层；无档=0\n",
     2),
    # E10 GET 端点注释 20→50
    ("E10 GET注释",
     "// GET /api/achievements — 全 20 项 + 每类进度 + 可领取清单（惰性计算，一页全量）",
     "// GET /api/achievements — 全 50 项 + 每类进度 + 可领取清单（惰性计算，一页全量）",
     1),
    # E11 视图组装注释 20→50
    ("E11 视图注释",
     "// 视图组装（纯）：20 项全量 + 分组计数 + 可领取清单（done && !claimed）",
     "// 视图组装（纯）：50 项全量 + 分组计数 + 可领取清单（done && !claimed）",
     1),
    # E12 ACH_DEFS 整块 20 行→50 行（核心改动）
    ("E12 ACH_DEFS扩表",
     OLD_ACH_DEFS,
     NEW_ACH_DEFS,
     1),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    (OLD_ACH_DEFS, 1, "旧 ACH_DEFS 整块必须在位且唯一（链上更早的环不得已改过此表）"),
    ("const ACH_REWARD_TIERS = [200, 500, 1000, 2000]; // 每类四档奖励阶梯（灵石）", 1, "死常量必须在位（本环不动它）"),
    ("const ACH_REALM_ORDER: string[] = Object.keys(TRIB_REALM_BASES);", 1, "境界序镜像必须在位（本环不动定义）"),
    ("interface AchDef { id: string; group: string; name: string; desc: string; target: number; reward: number; }",
     1, "AchDef 接口必须在位（行结构契约）"),
    ("INSERT OR IGNORE INTO achievement_claimed (user_id, ach_id) VALUES (?, ?)", 1, "claim 幂等占位必须已在位（不改）"),
    ("DELETE FROM achievement_claimed WHERE user_id = ? AND ach_id = ?", 1, "claim 发信失败补偿必须已在位（不改）"),
    ("function achPickClaimable(view: { claimableIds: string[] }, requestedId?: unknown): string[] {", 1, "领取选取纯函数必须在位（不改）"),
    ("'INSERT OR IGNORE INTO achievement_claimed", 1, "占位语句唯一性（防幂等面被别的环改过）"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "const ACH_REWARD_TIERS = [200, 500, 1000, 2000];",
    "const ACH_REALM_ORDER: string[] = Object.keys(TRIB_REALM_BASES);",
    "const REALM_ORDER_FOR_RANKING = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];",
    "INSERT OR IGNORE INTO achievement_claimed (user_id, ach_id) VALUES (?, ?)",
    "DELETE FROM achievement_claimed WHERE user_id = ? AND ach_id = ?",
    "function achPickClaimable(view: { claimableIds: string[] }, requestedId?: unknown): string[] {",
    "interface AchDef { id: string; group: string; name: string; desc: string; target: number; reward: number; }",
    "res.status(403",
    "require(",
    "setInterval(",
    "PRAGMA",
]

# ============================================================ 数值表 §6 权威数值（逐行比对用）
LADDER = [500, 1200, 2500, 4500, 7000, 10000, 15000, 22000, 32000, 50000]
EXPECT = {
    "cultivate": [60, 300, 1200, 3000, 7000, 15000, 30000, 60000, 100000, 150000],
    "battle":    [10, 50, 200, 500, 1200, 2500, 5000, 10000, 18000, 30000],
    "wealth":    [10000, 100000, 1000000, 3000000, 8000000, 20000000, 50000000, 120000000, 250000000, 500000000],
    "quest":     [1, 10, 50, 150, 350, 700, 1200, 2000, 3000, 5000],
    "realm":     [3, 10, 19, 28, 37, 46, 52, 56, 60, 63],
}


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def verify_new_block(block):
    """语义自证：逐行解析 NEW 块，比对数值表 §6（行数/分组/目标/奖励/单调/合计）。"""
    rows = re.findall(
        r"\{ id: '([^']+)', group: '([^']+)', name: '([^']+)', desc: '[^']*', target: (\d+), reward: (\d+) \}",
        block)
    ok = True
    if len(rows) != 50:
        return False, "行数 %d != 50" % len(rows)
    ids = [r[0] for r in rows]
    if len(set(ids)) != 50:
        return False, "存在重复 id"
    for grp, targets in EXPECT.items():
        grows = [r for r in rows if r[1] == grp]
        if len(grows) != 10:
            return False, "%s 行数 %d != 10" % (grp, len(grows))
        gt = [int(r[3]) for r in grows]
        gr = [int(r[4]) for r in grows]
        if gt != targets:
            return False, "%s 目标阶梯不符：%s" % (grp, gt)
        if gt != sorted(gt) or len(set(gt)) != 10:
            return False, "%s 目标非严格递增" % grp
        if gr != LADDER:
            return False, "%s 奖励阶梯不符：%s" % (grp, gr)
        s = sum(gr)
        if s != 144700:
            return False, "%s 单类合计 %d != 144700" % (grp, s)
        print("  [OK] %-10s 目标=%s" % (grp, gt))
        print("  [OK] %-10s 奖励=%s Σ=%d" % (grp, gr, s))
    total = sum(int(r[4]) for r in rows)
    if total != 723500:
        return False, "全清合计 %d != 723500" % total
    print("  [OK] %s 五类全清合计 = 723,500（旧 80,000）" % total)
    return True, ""


def main() -> None:
    ap = argparse.ArgumentParser(description="R-122 仙务成就 4→10 档环（服务端）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：已打过本环
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点计数（含 expect>1 的共用行）
    for name, old, new, expect in EDITS:
        n = src.count(old)
        if n != expect:
            fail("%s 锚点出现 %d 次（期望 %d）：%r" % (name, n, expect, old[:120]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用（顺序执行）
    out = src
    for name, old, new, expect in EDITS:
        out = out.replace(old, new, expect)

    # 6) NEW 块语义自证（对写入文本里的实际新块解析，不是对常量自说自话）
    i0 = out.find("const ACH_DEFS: AchDef[] = [")
    i1 = out.find("\n];", i0)
    if i0 < 0 or i1 < 0:
        fail("打后找不到 ACH_DEFS 块边界")
    new_block_in_out = out[i0:i1 + 3]
    ok, why = verify_new_block(new_block_in_out)
    if not ok:
        fail("语义自证失败：" + why)

    # 7) 门禁
    gates = [
        # ---- 本环改动 ----
        ("R122 幂等标记就位", MARK, 1),
        ("R122 新ACH_DEFS块在位", NEW_ACH_DEFS, 1),
        ("R122 旧ACH_DEFS块清零", OLD_ACH_DEFS, 0),
        ("R122 Y19段头已更新", "五类各 10 项共 50 项", 2),
        ("R122 旧20项表述清零", "五类各 4 项共 20 项", 0),
        ("R122 GET注释50项", "// GET /api/achievements — 全 50 项", 1),
        ("R122 视图注释50项", "// 视图组装（纯）：50 项全量", 1),
        ("R122 AchMetric含totalLevel", "| 'realmIndex' | 'totalLevel';", 1),
        ("R122 境界组metric已换", "metric: 'totalLevel' },", 1),
        ("R122 旧metric行清零", "  { key: 'realm', name: '境界', metric: 'realmIndex' },", 0),
        ("R122 AchTotals含totalLevel", "realmIndex: number; totalLevel: number; }", 1),
        ("R122 achTotalsFrom入参", "realmIndex?: unknown; totalLevel?: unknown }", 1),
        ("R122 achTotalsFrom出参", "totalLevel: n(t.totalLevel) }", 1),
        ("R122 调用行新形态x2", "totalLevel: realmIndex >= 0 ? realmIndex * 9 + realmLevel : 0 }),", 2),
        ("R122 调用行旧形态清零", "achTotalsFrom({ minutes: sum?.m, kills: sum?.k, silver: sum?.s, quests: questCnt?.c, realmIndex }),", 0),
        ("R122 realmLevel声明x2", "let realmLevel = 1;", 2),
        # ---- 行数与分组（带引号 id 自封闭，无子串污染）----
        ("R122 总行数=50", ", group: '", 50),
        ("R122 修行10行", ", group: 'cultivate', name:", 10),
        ("R122 战斗10行", ", group: 'battle', name:", 10),
        ("R122 财富10行", ", group: 'wealth', name:", 10),
        ("R122 任务10行", ", group: 'quest', name:", 10),
        ("R122 境界10行", ", group: 'realm', name:", 10),
        ("R122 总等级desc=10", "）', target: ", 10),
        ("R122 满档desc唯一", "desc: '总等级达到 63（长生境九层·圆满）', target: 63, reward: 50000 },", 1),
        ("R122 旧境界desc清零", "境界达到金丹期", 0),
        # ---- 退役旧 id 清零（带引号精确形态）----
        ("R122 退役 cultivate_6000", "'cultivate_6000'", 0),
        ("R122 退役 battle_1000", "'battle_1000'", 0),
        ("R122 退役 wealth_1e7", "'wealth_1e7'", 0),
        ("R122 退役 quest_200", "'quest_200'", 0),
        ("R122 退役 realm_jindan", "'realm_jindan'", 0),
        ("R122 退役 realm_yuanying", "'realm_yuanying'", 0),
        ("R122 退役 realm_huashen", "'realm_huashen'", 0),
        ("R122 退役 realm_changsheng", "'realm_changsheng'", 0),
        # ---- 保留旧 id 语义不变（每类前 3 档，各恰 1 处）----
        ("R122 保留 cultivate_60", "'cultivate_60'", 1),
        ("R122 保留 cultivate_300", "'cultivate_300'", 1),
        ("R122 保留 cultivate_1200", "'cultivate_1200'", 1),
        ("R122 保留 battle_10", "'battle_10'", 1),
        ("R122 保留 battle_50", "'battle_50'", 1),
        ("R122 保留 battle_200", "'battle_200'", 1),
        ("R122 保留 wealth_1e4", "'wealth_1e4'", 1),
        ("R122 保留 wealth_1e5", "'wealth_1e5'", 1),
        ("R122 保留 wealth_1e6", "'wealth_1e6'", 1),
        ("R122 保留 quest_1", "'quest_1'", 1),
        ("R122 保留 quest_10", "'quest_10'", 1),
        ("R122 保留 quest_50", "'quest_50'", 1),
        # ---- 冻结：死常量/幂等面/补偿/相邻系统一字不动 ----
        ("冻结 死常量ACH_REWARD_TIERS未动",
         "const ACH_REWARD_TIERS = [200, 500, 1000, 2000];",
         base["const ACH_REWARD_TIERS = [200, 500, 1000, 2000];"]),
        ("冻结 ACH_REALM_ORDER定义未动",
         "const ACH_REALM_ORDER: string[] = Object.keys(TRIB_REALM_BASES);",
         base["const ACH_REALM_ORDER: string[] = Object.keys(TRIB_REALM_BASES);"]),
        ("冻结 REALM_ORDER_FOR_RANKING未动",
         "const REALM_ORDER_FOR_RANKING = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];",
         base["const REALM_ORDER_FOR_RANKING = ['炼气期', '筑基期', '金丹期', '元婴期', '化神期', '合道期', '长生境'];"]),
        ("冻结 claim幂等占位未动",
         "INSERT OR IGNORE INTO achievement_claimed (user_id, ach_id) VALUES (?, ?)",
         base["INSERT OR IGNORE INTO achievement_claimed (user_id, ach_id) VALUES (?, ?)"]),
        ("冻结 claim补偿删除未动",
         "DELETE FROM achievement_claimed WHERE user_id = ? AND ach_id = ?",
         base["DELETE FROM achievement_claimed WHERE user_id = ? AND ach_id = ?"]),
        ("冻结 achPickClaimable未动",
         "function achPickClaimable(view: { claimableIds: string[] }, requestedId?: unknown): string[] {",
         base["function achPickClaimable(view: { claimableIds: string[] }, requestedId?: unknown): string[] {"]),
        ("冻结 AchDef接口未动",
         "interface AchDef { id: string; group: string; name: string; desc: string; target: number; reward: number; }",
         base["interface AchDef { id: string; group: string; name: string; desc: string; target: number; reward: number; }"]),
        # ---- 红线 ----
        ("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]),
        ("红线 require( 保持 0", "require(", base["require("]),
        ("红线 未新增 setInterval", "setInterval(", base["setInterval("]),
        ("红线 未新增 PRAGMA", "PRAGMA", base["PRAGMA"]),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))

    if not ok:
        fail("门禁未全绿，未写回")

    # 8) 往返自证（新→旧逐环还原，必须 == 原文）
    back = out
    for name, old, new, expect in reversed(EDITS):
        if back.count(new) != expect:
            fail("%s 的 new 在产物中出现 %d 次（期望 %d）" % (name, back.count(new), expect))
        for _ in range(expect):
            back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r122-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r122ach10-", suffix=".tmp")
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
