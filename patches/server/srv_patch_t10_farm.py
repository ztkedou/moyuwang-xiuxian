# -*- coding: utf-8 -*-
r"""
srv_patch_t10_farm.py -- 0.8.7 T10 灵田功能扩充（服务端环 t10_farm；归属 implGrotto）

CLI 契约（与链上其余补丁一致）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径；`--check` 只校验不写。
  不提供 `--out`：`localtest/chain_build.py` 会把上一环产物复制成私有工作副本
  再让本补丁就地改。

覆盖范围（T9T10-洞府灵田.md §3~§4 + 0.8.7-build-plan.md §2-T10/§4.5 契约 E1~E6）
--------------------------------------------------------------------------
  F1  新表 farm_daily_care（照料/催熟日切幂等占位，PK(player_id,slot,date)，北京日切）
  F2  [farmcore] 常量区：FARM_SLOTS 3→6；FARM_CROPS +2 高阶作物（太虚果/造化青莲）；
      FARM_UNLOCK_COST +4/5/6 三档；新增 FARM_UNLOCK_GROTTO_LEVEL 与照料/虫害/连作/催熟常量
  F3  [farmcore] 纯函数：farmYield 加 mods 乘区（缺省=0.8.6 口径逐位不变）；
      新增 farmStreakDecayOf / farmPestToday / farmBoostCost / farmBoostCap /
      farmGrottoBonusOf / farmSlotsForLevel（全部纯函数，供单测整块提取）
  F4  GET /api/farm/status 扩展（E1）：+grottoLevel、每田 care/streak/boostCost、
      readyCount、nextUnlock、boostDaily{used,cap}、unlockGrottoLevel
  F5  POST /api/farm/plant 扩展（E2）：高阶作物洞府门槛 409；成熟时长吃洞府
      growthSpeedBonus×0.5 折算；回执 +streakDecay/pest
  F6  POST /api/farm/harvest 重构（不改对外契约）：抽出公共 farmHarvestOne，
      单收/一键收倍率与入账口径逐位一致（T5 掉玉挂点只钩公共入账点）
  F7  POST /api/farm/unlock 扩展（E6）：slot 4/5/6 洞府等级门槛 409
  F8  新端点 POST /api/farm/boost（E3）/api/farm/tend（E4）/api/farm/harvest/all（E5）

★ 铁律遵守
--------------------------------------------------------------------------
  · 业务拒绝一律 400/409（绝不 403：客户端 Xc() 把 403 当会话失效强制登出）
  · 扣费端点（boost）统一「先占次数位 → 再守卫推进 → 再扣灵石 → 失败补偿删行回滚」，
    占位闸门 = farm_daily_care PK + ON CONFLICT DO UPDATE ... WHERE boosted=0 单语句原子
  · ★ 禁改 T5 actApplyGain 挂点区（原 :5809-5813 五行）：resolveEventMults /
    resolveMentorGains / actApplyGain 三行逐字保留、仅随 farmHarvestOne 抽取整体搬家，
    全文件 actApplyGain 总量不变（定义 1 + 调用 7 = 8）
  · 经济红线 #11（相对式已定）：满配（洞府 L10+照料）灵田日净灵石
    = 6 田 × (215000×1.21−200000)/3 天 ≈ 120,300/日
    ≤ 150,000（= T5-C 灵玉阁日上限对价 150 万/日的 1/10）；绝对值待数值表定档
  · ★ 数值批依赖：本文件所有「建议锚值」常量集中在 F2 一个块，★待《数值表-T9T10.md》
    定档后只改常量、端点零改动（build-plan v2 §8 步骤 0）

门禁计数清单（供 check_srv_087 落表；接线人 implEventsSrv）
--------------------------------------------------------------------------
  const FARM_SLOTS = 6;                         ==1   （旧 `= 3` ==0）
  CREATE TABLE IF NOT EXISTS farm_daily_care    ==1
  '/api/farm/boost' / '/api/farm/tend' / '/api/farm/harvest/all'  各==1
  actApplyGain(                                 ==8（与 0.8.6 基线同，零新增）
  await resolveEventMults(now)                  ==2（与基线同；farm 域 1 处在 farmHarvestOne 内）
  [farmcore] / [/farmcore]                      各==1
  res.status(403                                与基线同（T10 零新增 403）
  ON CONFLICT(player_id, slot, date) DO UPDATE SET boosted = 1 WHERE boosted = 0   ==1
  ON CONFLICT(player_id, slot, date) DO UPDATE SET tended = 1 WHERE tended = 0     ==1
"""
import argparse
import io
import os
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ============================================================ F1 新表

F1_OLD = """  db.run(`
    CREATE TABLE IF NOT EXISTS farm_unlocks (
      player_id INTEGER NOT NULL,
      slot INTEGER NOT NULL,
      unlocked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (player_id, slot),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);"""

F1_NEW = F1_OLD + """
  // 0.8.7 T10：farm_daily_care——照料/催熟的日切状态（北京日切，与 stats_daily 同口径）。
  // PK(player_id,slot,date) 幂等 + ON CONFLICT DO UPDATE ... WHERE x=0 单语句原子闸门：
  // 「每田每日照料 1 次 / 催熟 1 次」与并发双击的唯一防线；每日催熟总次数 = COUNT(boosted=1) 复核。
  // 回滚保留勿删（IF NOT EXISTS，旧代码无害）。
  db.run(`
    CREATE TABLE IF NOT EXISTS farm_daily_care (
      player_id INTEGER NOT NULL,
      slot INTEGER NOT NULL,
      date TEXT NOT NULL,
      tended INTEGER NOT NULL DEFAULT 0,
      boosted INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (player_id, slot, date),
      FOREIGN KEY (player_id) REFERENCES users (id)
    )
  `);
  db.run(`CREATE INDEX IF NOT EXISTS idx_farm_care_player_date ON farm_daily_care(player_id, date)`);"""

# ============================================================ F2 常量区

F2A_OLD = "const FARM_SLOTS = 3; // 每玩家田位数（slot 1..3；slot 1 免费隐式解锁，2/3 灵石开垦永久）"
F2A_NEW = "const FARM_SLOTS = 6; // T10：田位数 3→6（slot 1 免费隐式解锁；2/3 灵石开垦；4/5/6 另需洞府等级门槛，见 FARM_UNLOCK_GROTTO_LEVEL；farmSlotOk/status 循环/LIMIT 全部随本常量自动泛化）"

F2B_OLD = """const FARM_CROPS: Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number }> = {
  lingcao:     { name: '灵草',   seed: 1000, minutes: 240,  stones: 800,   exp: 500 },
  lingzhi:     { name: '灵芝',   seed: 5000, minutes: 720,  stones: 5000,  exp: 3000 },
  qianniancan: { name: '千年参', seed: 20000, minutes: 1440, stones: 25000, exp: 15000 },
};
const FARM_UNLOCK_COST: Record<number, number> = { 2: 20000, 3: 80000 }; // 开垦价（slot 1 免费，不在表内；物价×10）"""

F2B_NEW = """const FARM_CROPS: Record<string, { name: string; seed: number; minutes: number; stones: number; exp: number; grottoLevel?: number }> = {
  lingcao:     { name: '灵草',   seed: 1000, minutes: 240,  stones: 800,   exp: 500 },
  lingzhi:     { name: '灵芝',   seed: 5000, minutes: 720,  stones: 5000,  exp: 3000 },
  qianniancan: { name: '千年参', seed: 20000, minutes: 1440, stones: 25000, exp: 15000 },
  // T10 高阶作物（数值=设计案建议锚值，★待《数值表-T9T10.md》#8 定档回填；洞府门槛对齐地块档 #4）：
  //   经济红线 #11 预验算（相对式）：满配（L10 洞府 +10% × 照料 +10% = ×1.21 毛额）最赚钱作物=造化青莲，
  //   日净 = (215000×1.21−200000)/3 天 ≈ 20,050/田 → ×6 田 ≈ 120,300/日 ≤ 150,000（=T5-C 对价 150 万的 1/10）✓
  //   净收益率 产出/种子：太虚果 1.40（2 天）、造化青莲 1.075（3 天，但日净绝对值 2 倍于千年参）；修为≈灵石×0.6 同既有比例
  taixuguo:       { name: '太虚果',   seed: 50000,  minutes: 2880, stones: 70000,  exp: 42000,  grottoLevel: 5 },
  zaohuaqinglian: { name: '造化青莲', seed: 200000, minutes: 4320, stones: 215000, exp: 129000, grottoLevel: 7 },
};
const FARM_UNLOCK_COST: Record<number, number> = { 2: 20000, 3: 80000, 4: 200000, 5: 800000, 6: 2000000 }; // 开垦价（slot 1 免费，不在表内；物价×10；4/5/6=T10 建议锚值，★待 #5 定档）
// ─────────────────────────────────────────────────────────
// T10 灵田扩充（0.8.7 t10_farm）：照料/催熟/虫害/连作/洞府联动常量
// ★ 以下全部「建议锚值」，待《数值表-T9T10.md》定档回填（#3~#7/#10）——定档只改这里，端点零改动
// ─────────────────────────────────────────────────────────
const FARM_UNLOCK_GROTTO_LEVEL: Record<number, number> = { 4: 5, 5: 7, 6: 9 }; // #4 地块洞府门槛（建议 L5/L7/L9，与 T9 表同一套档）
const FARM_GROTTO_BONUS_PER_LEVEL = 0.01;  // #3 灵田产出加成/级（建议 +1%/级线性；服务端按存档 grotto.level 实算）
const FARM_GROWTH_BONUS_COEF = 0.5;        // #10 洞府 growthSpeedBonus→灵田成熟时长折算系数（建议 ×0.5 防双吃）
const FARM_TEND_BONUS = 0.10;              // #7 照料当日收获加成（建议 +10%）
const FARM_PEST_RATE = 0.30;               // #7 虫害概率（建议 30%；确定性 hash 可复算）
const FARM_PEST_PENALTY = 0.20;            // #7 虫害未照料收获减产（建议 -20%）
const FARM_STREAK_DECAY_2 = 0.15;          // #9 连作第 2 茬产出衰减（建议 -15%）
const FARM_STREAK_DECAY_3 = 0.30;          // #9 连作第 3+ 茬产出衰减（建议 -30%）
const FARM_BOOST_MIN_COST = 1000;          // #6 催熟起价（同洞府加速 Br.minCost=1000）
const FARM_BOOST_COST_PER_MIN = 100;       // #6 催熟单价/剩余分钟（同 Br.costPerMinute=100；纯灵石回收口）
const FARM_BOOST_BASE_CAP = 3;             // #6 每日催熟总次数基础值（+1 次/2 级洞府，见 farmBoostCap）"""

# ============================================================ F3 farmYield 加 mods + 新纯函数

F3A_OLD = """// 收益（纯）：到期=全额；提前收获=减半（两项独立 floor）
function farmYield(crop: { stones: number; exp: number }, early: boolean): { stones: number; exp: number } {
  const s = Math.max(0, Math.floor(Number(crop.stones) || 0));
  const e = Math.max(0, Math.floor(Number(crop.exp) || 0));
  return early ? { stones: Math.floor(s / 2), exp: Math.floor(e / 2) } : { stones: s, exp: e };
}"""

F3A_NEW = """// 收益（纯）：到期=全额；提前收获=减半（两项独立 floor）
// T10：mods 乘区（缺省 undefined = 乘区全 1 / 无虫害 ⇒ 0.8.6 口径逐位不变）：
//   产出 = floor(base × (1+grottoBonus) × (1+tendBonus) × (1−streakDecay−pest))，提前减半照旧在最外层
function farmYield(crop: { stones: number; exp: number }, early: boolean, mods?: { grottoBonus?: number; tendBonus?: number; streakDecay?: number; pest?: boolean }): { stones: number; exp: number } {
  const m = mods || {};
  const mul = (1 + Math.max(0, Number(m.grottoBonus) || 0)) * (1 + Math.max(0, Number(m.tendBonus) || 0));
  const dec = Math.min(0.9, Math.max(0, Number(m.streakDecay) || 0) + (m.pest ? FARM_PEST_PENALTY : 0));
  const s = Math.max(0, Math.floor((Number(crop.stones) || 0) * mul * (1 - dec)));
  const e = Math.max(0, Math.floor((Number(crop.exp) || 0) * mul * (1 - dec)));
  return early ? { stones: Math.floor(s / 2), exp: Math.floor(e / 2) } : { stones: s, exp: e };
}
// T10 连作衰减（纯）：streak=同田同作物连续茬数（由 spirit_farm harvested=1 历史行推导，零新表）
function farmStreakDecayOf(streak: number): number {
  return streak >= 2 ? FARM_STREAK_DECAY_3 : (streak === 1 ? FARM_STREAK_DECAY_2 : 0);
}
// T10 虫害（纯，确定性伪随机）：FNV-1a hash(playerId,slot,crop,plantedAt,bjDate) 取模 < 虫害率。
// 同输入恒同结果 ⇒ status 与 harvest 各自复算恒一致，零 cron 零落库（服务端权威，客户端不判权）
function farmPestToday(playerId: number, slot: number, cropKey: string, plantedAt: number, date: string): boolean {
  const key = playerId + '|' + slot + '|' + cropKey + '|' + plantedAt + '|' + date;
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) { h ^= key.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) % 10000 < Math.round(FARM_PEST_RATE * 10000);
}
// T10 催熟费（纯）：max(起价, 剩余分钟×单价)——公式同构洞府加速 Br={minCost:1000,costPerMinute:100}，
// 常量独立不引客户端符号；催熟是纯灵石回收口（全周期催熟费恒高于作物净收益，不构成刷钱口）
function farmBoostCost(leftMs: number): number {
  return Math.max(FARM_BOOST_MIN_COST, Math.ceil(Math.max(0, leftMs) / 60000) * FARM_BOOST_COST_PER_MIN);
}
// T10 每日催熟总次数上限（纯）：基础 3 + 1 次/2 级洞府（#6；与客户端洞府页联动展示同式）
function farmBoostCap(grottoLevel: number): number {
  return FARM_BOOST_BASE_CAP + Math.floor(Math.max(0, grottoLevel) / 2);
}
// T10 洞府灵田产出加成（纯）：+1%/级线性（#3），等级钳 0..10
function farmGrottoBonusOf(grottoLevel: number): number {
  return Math.min(10, Math.max(0, grottoLevel)) * FARM_GROTTO_BONUS_PER_LEVEL;
}
// T10 洞府等级→可开垦地块上限（纯）：3 基础 + 已达门槛的 4/5/6 号田（#4；与客户端联动展示同式）
function farmSlotsForLevel(grottoLevel: number): number {
  let n = 3;
  for (let s = 4; s <= FARM_SLOTS; s++) { if (grottoLevel >= (FARM_UNLOCK_GROTTO_LEVEL[s] || Infinity)) n++; }
  return n;
}"""

# ============================================================ F4 status 扩展（E1）

F4A_OLD = """    const [unlocks, crops, saveRow] = await Promise.all([
      dbAll('SELECT slot FROM farm_unlocks WHERE player_id = ? LIMIT ?', [userId, FARM_SLOTS]),
      dbAll('SELECT slot, crop, planted_at, mature_at FROM spirit_farm WHERE player_id = ? AND harvested = 0 LIMIT ?', [userId, FARM_SLOTS]),
      dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
    ]);
    let stones = 0;
    if (saveRow) {
      try { stones = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { stones = 0; }
    }"""

F4A_NEW = """    const [unlocks, crops, saveRow, careRows, histRows] = await Promise.all([
      dbAll('SELECT slot FROM farm_unlocks WHERE player_id = ? LIMIT ?', [userId, FARM_SLOTS]),
      dbAll('SELECT id, slot, crop, planted_at, mature_at FROM spirit_farm WHERE player_id = ? AND harvested = 0 LIMIT ?', [userId, FARM_SLOTS]),
      dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
      dbAll('SELECT slot, tended, boosted FROM farm_daily_care WHERE player_id = ? AND date = ?', [userId, bjDate(Date.now())]),
      dbAll('SELECT id, slot, crop FROM spirit_farm WHERE player_id = ? AND harvested = 1 ORDER BY id DESC LIMIT 24', [userId]),
    ]);
    let stones = 0;
    let grottoLevel = 0;
    if (saveRow) {
      try {
        const sd0 = JSON.parse(saveRow.save_data);
        stones = Math.max(0, Math.floor(Number(sd0?.player?.spiritStones) || 0));
        grottoLevel = Math.min(10, Math.max(0, Math.floor(Number(sd0?.player?.grotto?.level) || 0)));
      } catch { stones = 0; }
    }"""

F4B_OLD = """    const bySlot: Record<number, any> = {};
    for (const r of crops || []) bySlot[Number(r.slot)] = r;
    const now = Date.now();"""

F4B_NEW = """    const bySlot: Record<number, any> = {};
    for (const r of crops || []) bySlot[Number(r.slot)] = r;
    const now = Date.now();
    const today = bjDate(now);
    // T10：当日照料/催熟行按田索引；连作数 = 活跃行之前最近同田历史行中同作物的连续条数
    const careBySlot: Record<number, any> = {};
    for (const c of careRows || []) careBySlot[Number(c.slot)] = c;
    const streakOf = (slotNum: number, cropKey: string, beforeId: number): number => {
      let n = 0;
      for (const hr of (histRows || [])) {
        if (Number(hr.slot) !== slotNum || Number(hr.id) >= beforeId) continue;
        if (String(hr.crop) === cropKey) n++;
        else break; // 第一条同田历史行不同作物 ⇒ 无连作
      }
      return n;
    };"""

F4C_OLD = """    const slots: any[] = [];
    for (let s = 1; s <= FARM_SLOTS; s++) {
      const r = bySlot[s];
      const key = r ? String(r.crop) : '';
      const def = farmCrop(key);
      slots.push({
        slot: s,
        unlocked: unlocked.has(s),
        crop: r && def ? {
          key,
          name: def.name,
          plantedAt: Number(r.planted_at),
          matureAt: Number(r.mature_at),
          ready: farmIsReady(Number(r.mature_at), now),
          leftMs: Math.max(0, Number(r.mature_at) - now),
        } : null,
      });
    }
    res.json({ now, stones, slots, crops: FARM_CROPS, unlockCost: FARM_UNLOCK_COST });"""

F4C_NEW = """    const slots: any[] = [];
    let readyCount = 0;
    for (let s = 1; s <= FARM_SLOTS; s++) {
      const r = bySlot[s];
      const key = r ? String(r.crop) : '';
      const def = farmCrop(key);
      const ready = !!(r && def && farmIsReady(Number(r.mature_at), now));
      if (ready) readyCount++;
      const care = careBySlot[s];
      const tended = !!care && Number(care.tended) === 1;
      const boosted = !!care && Number(care.boosted) === 1;
      const leftMs = r && def ? Math.max(0, Number(r.mature_at) - now) : 0;
      // 虫害（净）：仅生长中田 roll，且未照料（照料即净虫害）；status 与 harvest 各自复算恒一致
      const pest = !!(r && def && !ready && !tended && farmPestToday(userId, s, key, Number(r.planted_at), today));
      slots.push({
        slot: s,
        unlocked: unlocked.has(s),
        crop: r && def ? {
          key,
          name: def.name,
          plantedAt: Number(r.planted_at),
          matureAt: Number(r.mature_at),
          ready,
          leftMs,
        } : null,
        // T10 扩展：care（当日照料/催熟/净虫害）/ streak（连作茬数）/ boostCost（催熟费；无生长中作物=null）
        care: { date: today, tended: tended ? 1 : 0, boosted: boosted ? 1 : 0, pest },
        streak: r ? streakOf(s, key, Number(r.id)) : 0,
        boostCost: r && def && !ready ? farmBoostCost(leftMs) : null,
      });
    }
    let nextUnlock: any = null;
    for (let s = 1; s <= FARM_SLOTS; s++) {
      if (!unlocked.has(s)) { nextUnlock = { slot: s, cost: FARM_UNLOCK_COST[s] || 0, grottoLevel: FARM_UNLOCK_GROTTO_LEVEL[s] || 0 }; break; }
    }
    let boostUsed = 0;
    for (const c of careRows || []) { if (Number(c.boosted) === 1) boostUsed++; }
    res.json({ now, stones, grottoLevel, slots, crops: FARM_CROPS, unlockCost: FARM_UNLOCK_COST, unlockGrottoLevel: FARM_UNLOCK_GROTTO_LEVEL, readyCount, nextUnlock, boostDaily: { used: boostUsed, cap: farmBoostCap(grottoLevel) } });"""

# ============================================================ F5 plant 扩展（E2）

F5A_OLD = """    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    if (slot > 1) {"""

F5A_NEW = """    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    // T10：高阶作物洞府门槛（409；needGrottoLevel 供客户端置灰提示）
    const gi = farmGrottoInfo(saveRow.save_data);
    if (crop.grottoLevel && gi.level < crop.grottoLevel) {
      return res.status(409).json({ error: `【${crop.name}】需洞府等级 ≥${crop.grottoLevel}，当前洞府 Lv.${gi.level}`, needGrottoLevel: crop.grottoLevel });
    }
    if (slot > 1) {"""

F5B_OLD = "    const matureAt = farmMatureAt(now, crop.minutes);"
F5B_NEW = "    const matureAt = farmMatureAt(now, crop.minutes * (1 - Math.min(0.5, FARM_GROWTH_BONUS_COEF * gi.growthSpeedBonus))); // T10：洞府生长加速 ×0.5 折算进灵田成熟时长（#10，防双吃）"

F5C_OLD = "    res.json({ ok: true, slot, crop: cropKey, name: crop.name, plantedAt: now, matureAt, seed: crop.seed });"
F5C_NEW = """    // T10：本茬连作衰减与当日虫害随回执下发（提示性字段；衰减/虫害权威口径在收获时复算）
    const mods = await farmHarvestMods(userId, { id: Number(ins.lastID), slot, crop: cropKey, planted_at: now });
    res.json({ ok: true, slot, crop: cropKey, name: crop.name, plantedAt: now, matureAt, seed: crop.seed, streakDecay: mods.streakDecay, pest: mods.pest });"""

# ============================================================ F6 harvest 重构（公共 farmHarvestOne）

F6_OLD = """    const r = await dbGet('SELECT id, crop, planted_at, mature_at FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 0', [userId, slot]);
    if (!r) return res.status(404).json({ error: '该田空空如也' });
    const def = farmCrop(String(r.crop));
    if (!def) return res.status(500).json({ error: '作物数据异常' });
    const now = Date.now();
    const matureAt = Number(r.mature_at);
    const early = !farmIsReady(matureAt, now);
    const gainBase = farmYield(def, early);
    // Y21：活动倍率（收获结算自动应用；引擎读取失败按 ×1 保底，不阻塞收获）
    const evMult = await resolveEventMults(now).catch(() => ({ events: [] as any[], expMult: 1, stonesMult: 1 }));
    // Y6B：师徒加成/出师增益（读取失败 ×1 保底，不阻塞收获）
    const mnG = await resolveMentorGains(userId, now).catch(() => ({ expMult: 1, stonesMult: 1 }));
    const gain = { stones: actApplyGain(gainBase.stones, evMult.stonesMult * mnG.stonesMult), exp: actApplyGain(gainBase.exp, evMult.expMult * mnG.expMult) };
    const claim = await dbRun('UPDATE spirit_farm SET harvested = 1 WHERE id = ? AND player_id = ? AND harvested = 0', [Number(r.id), userId]);
    if (!claim.changes) return res.status(409).json({ error: '该田已收获' }); // 并发双击只一方生效
    let credited = false;
    const hit = await updatePlayerSave(userId, (sd: any) => {
      if (!sd.player || typeof sd.player !== 'object') return;
      sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + gain.stones;
      sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + gain.exp;
      credited = true;
    });
    if (!hit.ok || !credited) {
      // 补偿：回退收获标记（活跃行已清零，恢复 harvested=0 必不违反部分唯一索引；极窄竞态见函数头注）
      await dbRun('UPDATE spirit_farm SET harvested = 0 WHERE id = ?', [Number(r.id)]).catch((e: any) => console.error('farm harvest revert error:', e?.message || e));
      return res.status(hit.error === 'No save found' ? 404 : 500).json({ error: hit.error === 'No save found' ? '请先进游戏创建角色' : '入账失败，请重试' });
    }
    // 回执邮件（尽力而为：收益已实际入档，邮件失败仅记日志不影响收获结果）
    insertMail(userId, '灵田丰收',
      `洞府灵田，「${def.name}」${early ? '提前起收（收益减半）' : '应时而收'}！\\n\\n· 灵石 +${gain.stones}（已入账）\\n· 修为 +${gain.exp}（已入账）\\n\\n灵石与修为已直接汇入随身囊中，回游戏即可查看。田地已翻新，随时可播下一茬。`,
      'system', 0).catch((e: any) => console.error('farm harvest mail error:', e?.message || e));
    res.json({ ok: true, slot, crop: String(r.crop), name: def.name, early, stones: gain.stones, exp: gain.exp, matureAt, eventMults: { exp: evMult.expMult, stones: evMult.stonesMult } });"""

F6_NEW = """    const r = await dbGet('SELECT id, crop, planted_at, mature_at FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 0', [userId, slot]);
    if (!r) return res.status(404).json({ error: '该田空空如也' });
    // T10：单收/一键收抽公共 farmHarvestOne（倍率/掉玉挂点/邮件口径逐位一致；T5 只钩公共入账点）
    const one = await farmHarvestOne(userId, r);
    if (!one.ok) return res.status(one.status || 500).json({ error: one.error || '服务器繁忙' });
    res.json({ ok: true, slot: one.slot, crop: one.crop, name: one.name, early: one.early, stones: one.stones, exp: one.exp, matureAt: one.matureAt, eventMults: one.eventMults });"""

# ============================================================ F7 unlock 扩展（E6）

F7_OLD = """  const cost = FARM_UNLOCK_COST[slot];
  if (!cost) return res.status(409).json({ error: '首块田地免费可用，无需开垦' });
  const userId = req.user.id;
  try {
    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < cost) return res.status(409).json({ error: `灵石不足：需 ${cost}，现有 ${bal}` });"""

F7_NEW = """  const cost = FARM_UNLOCK_COST[slot];
  if (!cost) return res.status(409).json({ error: '首块田地免费可用，无需开垦' });
  const userId = req.user.id;
  try {
    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    // T10：slot 4/5/6 洞府等级门槛（409 需洞府等级 X；E6 契约；门槛先于灵石校验，先告知缺什么）
    const gu = farmGrottoInfo(saveRow.save_data);
    const needLevel = FARM_UNLOCK_GROTTO_LEVEL[slot] || 0;
    if (needLevel > 0 && gu.level < needLevel) {
      return res.status(409).json({ error: `第 ${slot} 块田需洞府等级 ≥${needLevel}，当前洞府 Lv.${gu.level}`, needGrottoLevel: needLevel });
    }
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < cost) return res.status(409).json({ error: `灵石不足：需 ${cost}，现有 ${bal}` });"""

# ============================================================ F8 公共原语 + 三新端点（E3/E4/E5）

F8_OLD = """    res.json({ ok: true, slot, cost });
  } catch (e: any) {
    console.error('farm unlock error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});"""

F8_NEW = F8_OLD + """

// ─────────────────────────────────────────────────────────
// T10（0.8.7）：公共原语与三新端点（boost 催熟 / tend 照料 / harvest/all 一键收取）
// 动账原语零新增：dbGet/dbAll/dbRun/insertMail/bjDate 均为既有 hoisted 函数声明；
// 扣费端点统一「占位 → 守卫推进 → 扣款 → 失败补偿」，拒绝码只用 400/409（绝不 403）。
// ─────────────────────────────────────────────────────────

// T10：从 saves.save_data 读洞府等级与生长加速（读法与 status/plant 现有 JSON.parse 同款；解析失败按 0 处理）
function farmGrottoInfo(saveDataJson: string | null | undefined): { level: number; growthSpeedBonus: number } {
  try {
    const g = JSON.parse(saveDataJson || '{}')?.player?.grotto || {};
    return {
      level: Math.min(10, Math.max(0, Math.floor(Number(g.level) || 0))),
      growthSpeedBonus: Math.min(0.5, Math.max(0, Number(g.growthSpeedBonus) || 0)),
    };
  } catch { return { level: 0, growthSpeedBonus: 0 }; }
}

// T10：收获/种植时的产出修正（洞府加成/照料/连作衰减/虫害）。
// 读存档洞府等级 + 当日 farm_daily_care 行 + spirit_farm 历史行推导连作；全部只读，无副作用。
async function farmHarvestMods(userId: number, row: { id?: number; slot: number; crop: string; planted_at: number }): Promise<{ grottoBonus: number; tendBonus: number; streakDecay: number; pest: boolean }> {
  const slot = Number(row.slot);
  const today = bjDate(Date.now());
  const [saveRow, careRow, histRows] = await Promise.all([
    dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]),
    dbGet('SELECT tended FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]),
    row.id
      ? dbAll('SELECT crop FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 1 AND id < ? ORDER BY id DESC LIMIT 2', [userId, slot, Number(row.id)])
      : Promise.resolve([] as any[]),
  ]);
  const gi = farmGrottoInfo(saveRow ? saveRow.save_data : null);
  const tended = !!careRow && Number(careRow.tended) === 1;
  let streak = 0;
  for (const hr of (histRows || [])) { if (String(hr.crop) === String(row.crop)) streak++; else break; }
  const pest = !tended && farmPestToday(userId, slot, String(row.crop), Number(row.planted_at), today);
  return {
    grottoBonus: farmGrottoBonusOf(gi.level),
    tendBonus: tended ? FARM_TEND_BONUS : 0,
    streakDecay: farmStreakDecayOf(streak),
    pest,
  };
}

// T10：单收/一键收公共收获原语（内部顺序与 0.8.6 单收逐字一致：
// mods→gainBase→Y21 活动倍率→Y6B 师徒加成→守卫式收获→入账→失败回退→回执邮件）。
// opts.mail=false 时不发单行邮件（harvest/all 用，改发一封汇总邮件），其余行为不变。
async function farmHarvestOne(userId: number, row: any, opts?: { mail?: boolean }): Promise<{ ok: boolean; status?: number; error?: string; slot?: number; crop?: string; name?: string; early?: boolean; stones?: number; exp?: number; matureAt?: number; eventMults?: { exp: number; stones: number } }> {
  const def = farmCrop(String(row.crop));
  if (!def) return { ok: false, status: 500, error: '作物数据异常' };
  const now = Date.now();
  const matureAt = Number(row.mature_at);
  const early = !farmIsReady(matureAt, now);
  const mods = await farmHarvestMods(userId, { id: Number(row.id), slot: Number(row.slot), crop: String(row.crop), planted_at: Number(row.planted_at) });
  const gainBase = farmYield(def, early, mods);
  // Y21：活动倍率（收获结算自动应用；引擎读取失败按 ×1 保底，不阻塞收获）
  const evMult = await resolveEventMults(now).catch(() => ({ events: [] as any[], expMult: 1, stonesMult: 1 }));
  // Y6B：师徒加成/出师增益（读取失败 ×1 保底，不阻塞收获）
  const mnG = await resolveMentorGains(userId, now).catch(() => ({ expMult: 1, stonesMult: 1 }));
  const gain = { stones: actApplyGain(gainBase.stones, evMult.stonesMult * mnG.stonesMult), exp: actApplyGain(gainBase.exp, evMult.expMult * mnG.expMult) };
  const claim = await dbRun('UPDATE spirit_farm SET harvested = 1 WHERE id = ? AND player_id = ? AND harvested = 0', [Number(row.id), userId]);
  if (!claim.changes) return { ok: false, status: 409, error: '该田已收获' }; // 并发双击只一方生效
  let credited = false;
  const hit = await updatePlayerSave(userId, (sd: any) => {
    if (!sd.player || typeof sd.player !== 'object') return;
    sd.player.spiritStones = Math.max(0, Math.floor(Number(sd.player.spiritStones) || 0)) + gain.stones;
    sd.player.exp = Math.max(0, Math.floor(Number(sd.player.exp) || 0)) + gain.exp;
    credited = true;
  });
  if (!hit.ok || !credited) {
    // 补偿：回退收获标记（活跃行已清零，恢复 harvested=0 必不违反部分唯一索引；极窄竞态见函数头注）
    await dbRun('UPDATE spirit_farm SET harvested = 0 WHERE id = ?', [Number(row.id)]).catch((e: any) => console.error('farm harvest revert error:', e?.message || e));
    return { ok: false, status: hit.error === 'No save found' ? 404 : 500, error: hit.error === 'No save found' ? '请先进游戏创建角色' : '入账失败，请重试' };
  }
  // 回执邮件（尽力而为：收益已实际入档，邮件失败仅记日志不影响收获结果）
  if (opts?.mail !== false) {
    insertMail(userId, '灵田丰收',
      `洞府灵田，「${def.name}」${early ? '提前起收（收益减半）' : '应时而收'}！\\n\\n· 灵石 +${gain.stones}（已入账）\\n· 修为 +${gain.exp}（已入账）\\n\\n灵石与修为已直接汇入随身囊中，回游戏即可查看。田地已翻新，随时可播下一茬。`,
      'system', 0).catch((e: any) => console.error('farm harvest mail error:', e?.message || e));
  }
  return { ok: true, slot: Number(row.slot), crop: String(row.crop), name: def.name, early, stones: gain.stones, exp: gain.exp, matureAt, eventMults: { exp: evMult.expMult, stones: evMult.stonesMult } };
}

// POST /api/farm/boost {slot} — T10 催熟：立即成熟，灵石计费（公式同构洞府加速 Br，常量独立）。
// 每田每日 1 次 + 每日总次数 = farmBoostCap(洞府等级)。三段式：
//   ①farm_daily_care 单语句原子占位（ON CONFLICT DO UPDATE SET boosted=1 WHERE boosted=0，
//     changes=0 → 409 今日该田已催熟）+ 占位后总次数复核（并发双开不同田双双落闸=宁可错拒不可超扣）
//   ②守卫推进 mature_at（changes=0 → 409 已成熟/并发已收，补偿删 care 行）
//   ③updatePlayerSave 扣费（short → 回滚 mature_at + 删 care 行，可重试）
app.post('/api/farm/boost', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `farm:boost:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const slot = Math.floor(asNum(req.body?.slot));
  if (!farmSlotOk(slot)) return res.status(400).json({ error: '田位非法' });
  const userId = req.user.id;
  try {
    const r = await dbGet('SELECT id, crop, planted_at, mature_at FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 0', [userId, slot]);
    if (!r) return res.status(409).json({ error: '该田空空如也，无需催熟' });
    const now = Date.now();
    const matureAt = Number(r.mature_at);
    if (farmIsReady(matureAt, now)) return res.status(409).json({ error: '该田已成熟，无需催熟' });
    const def = farmCrop(String(r.crop));
    if (!def) return res.status(500).json({ error: '作物数据异常' });
    const cost = farmBoostCost(Math.max(0, matureAt - now));
    const saveRow = await dbGet('SELECT save_data FROM saves WHERE user_id = ?', [userId]);
    if (!saveRow) return res.status(404).json({ error: '请先进游戏创建角色' });
    const gb = farmGrottoInfo(saveRow.save_data);
    let bal = 0;
    try { bal = Math.max(0, Math.floor(Number(JSON.parse(saveRow.save_data)?.player?.spiritStones) || 0)); } catch { return res.status(500).json({ error: '存档解析失败' }); }
    if (bal < cost) return res.status(409).json({ error: `灵石不足：催熟需 ${cost}，现有 ${bal}` });
    const today = bjDate(now);
    const capMsg = `今日催熟总次数已尽（${farmBoostCap(gb.level)} 次/日，随洞府等级提升）`;
    const preCnt = await dbGet('SELECT COUNT(*) AS c FROM farm_daily_care WHERE player_id = ? AND date = ? AND boosted = 1', [userId, today]);
    if (Number(preCnt?.c) >= farmBoostCap(gb.level)) return res.status(409).json({ error: capMsg });
    // ①占位：同田每日 1 次（原子闸门）
    const gate = await dbRun(
      'INSERT INTO farm_daily_care (player_id, slot, date, tended, boosted) VALUES (?, ?, ?, 0, 1) ' +
      'ON CONFLICT(player_id, slot, date) DO UPDATE SET boosted = 1 WHERE boosted = 0',
      [userId, slot, today]
    );
    if (!gate.changes) return res.status(409).json({ error: '该田今日已催熟' });
    // 占位后复核总次数
    const cnt = await dbGet('SELECT COUNT(*) AS c FROM farm_daily_care WHERE player_id = ? AND date = ? AND boosted = 1', [userId, today]);
    if (Number(cnt?.c) > farmBoostCap(gb.level)) {
      await dbRun('DELETE FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]).catch(() => {});
      return res.status(409).json({ error: capMsg });
    }
    // ②守卫推进 mature_at（立即成熟）
    const matureNow = Date.now();
    const upd = await dbRun('UPDATE spirit_farm SET mature_at = ? WHERE id = ? AND player_id = ? AND harvested = 0 AND mature_at > ?', [matureNow, Number(r.id), userId, matureNow]);
    if (!upd.changes) {
      await dbRun('DELETE FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]).catch(() => {});
      return res.status(409).json({ error: '该田已成熟或已收获，无需催熟' });
    }
    // ③扣费（锁内二次校验；失败回滚 mature_at + 删 care 行）
    let short = false;
    const paid = await updatePlayerSave(userId, (sd: any) => {
      const b = Math.max(0, Math.floor(Number(sd.player?.spiritStones) || 0));
      if (b < cost) { short = true; return; }
      sd.player.spiritStones = b - cost;
    });
    if (!paid.ok || short) {
      await dbRun('UPDATE spirit_farm SET mature_at = ? WHERE id = ?', [matureAt, Number(r.id)]).catch((e: any) => console.error('farm boost revert error:', e?.message || e));
      await dbRun('DELETE FROM farm_daily_care WHERE player_id = ? AND slot = ? AND date = ?', [userId, slot, today]).catch(() => {});
      return res.status(409).json({ error: short ? '灵石不足' : (paid.error === 'No save found' ? '请先进游戏创建角色' : '催熟失败，请重试') });
    }
    res.json({ ok: true, slot, matureAt: matureNow, cost, message: `催熟完成，「${def.name}」已立即成熟，消耗 ${cost} 灵石` });
  } catch (e: any) {
    console.error('farm boost error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/farm/tend {slot} — T10 照料（浇灌+除虫二合一，免费）：清当日虫害 + 该田当日收获 FARM_TEND_BONUS。
// farm_daily_care 单语句原子占位（DO UPDATE SET tended=1 WHERE tended=0，changes=0 → 409 今日已照料）
app.post('/api/farm/tend', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `farm:tend:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const slot = Math.floor(asNum(req.body?.slot));
  if (!farmSlotOk(slot)) return res.status(400).json({ error: '田位非法' });
  const userId = req.user.id;
  try {
    const r = await dbGet('SELECT id FROM spirit_farm WHERE player_id = ? AND slot = ? AND harvested = 0', [userId, slot]);
    if (!r) return res.status(409).json({ error: '该田空空如也，无需照料' });
    const today = bjDate(Date.now());
    const gate = await dbRun(
      'INSERT INTO farm_daily_care (player_id, slot, date, tended, boosted) VALUES (?, ?, ?, 1, 0) ' +
      'ON CONFLICT(player_id, slot, date) DO UPDATE SET tended = 1 WHERE tended = 0',
      [userId, slot, today]
    );
    if (!gate.changes) return res.status(409).json({ error: '该田今日已照料过' });
    res.json({ ok: true, slot, tendBonusPct: Math.round(FARM_TEND_BONUS * 100), message: `照料完成，本块田今日收获 +${Math.round(FARM_TEND_BONUS * 100)}%（虫害已清除）` });
  } catch (e: any) {
    console.error('farm tend error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});

// POST /api/farm/harvest/all — T10 一键收取全部成熟田：逐行复用 farmHarvestOne（守卫式逐行，
// 单行失败不阻塞其余行），聚合并只发一封汇总邮件；无成熟田 = 空数组 200。
// 与单收同倍率/同掉玉挂点（T5 挂点零漂移）；GET status 保持只读，自动收取由客户端触发 POST。
app.post('/api/farm/harvest/all', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => `farm:harvestall:${req.user?.id ?? req.ip}` }), async (req: any, res: any) => {
  const userId = req.user.id;
  try {
    const rows = await dbAll('SELECT id, slot, crop, planted_at, mature_at FROM spirit_farm WHERE player_id = ? AND harvested = 0 LIMIT ?', [userId, FARM_SLOTS]);
    const now = Date.now();
    const ready = (rows || []).filter((rw: any) => farmIsReady(Number(rw.mature_at), now));
    const harvested: any[] = [];
    let totalStones = 0, totalExp = 0;
    const mailLines: string[] = [];
    for (const rw of ready) {
      try {
        const one = await farmHarvestOne(userId, rw, { mail: false });
        if (one.ok) {
          harvested.push({ slot: one.slot, crop: one.crop, name: one.name, stones: one.stones, exp: one.exp, early: one.early });
          totalStones += Number(one.stones) || 0;
          totalExp += Number(one.exp) || 0;
          mailLines.push(`· 第 ${one.slot} 田「${one.name}」：灵石 +${one.stones}，修为 +${one.exp}${one.early ? '（提前起收，收益减半）' : ''}`);
        }
      } catch (e: any) {
        console.error('farm harvest all row error:', e?.message || e); // 单行失败不阻塞其余行
      }
    }
    if (harvested.length > 0) {
      insertMail(userId, '灵田丰收（一键收取）',
        `洞府灵田一键收取 ${harvested.length} 块成熟田！\\n\\n${mailLines.join('\\n')}\\n\\n· 合计灵石 +${totalStones}（已入账）\\n· 合计修为 +${totalExp}（已入账）\\n\\n空田可随时播下一茬。`,
        'system', 0).catch((e: any) => console.error('farm harvest all mail error:', e?.message || e));
    }
    res.json({ ok: true, harvested, totalStones, totalExp, message: harvested.length > 0 ? `一键收取 ${harvested.length} 块田：灵石 +${totalStones.toLocaleString()}，修为 +${totalExp.toLocaleString()}` : '暂无成熟田可收' });
  } catch (e: any) {
    console.error('farm harvest all error:', e?.message || e);
    res.status(500).json({ error: '服务器繁忙' });
  }
});"""

EDITS = [
    ('F1  新表 farm_daily_care',            F1_OLD, F1_NEW),
    ('F2a FARM_SLOTS 3→6',                  F2A_OLD, F2A_NEW),
    ('F2b 作物表扩 2 + 常量块',              F2B_OLD, F2B_NEW),
    ('F3  farmYield mods + 六纯函数',        F3A_OLD, F3A_NEW),
    ('F4a status 查询扩展',                  F4A_OLD, F4A_NEW),
    ('F4b status care/streak 索引',          F4B_OLD, F4B_NEW),
    ('F4c status 逐田扩展 + 回执',           F4C_OLD, F4C_NEW),
    ('F5a plant 高阶作物门槛',               F5A_OLD, F5A_NEW),
    ('F5b plant 成熟时长联动',               F5B_OLD, F5B_NEW),
    ('F5c plant 回执扩展',                   F5C_OLD, F5C_NEW),
    ('F6  harvest 抽公共 farmHarvestOne',    F6_OLD, F6_NEW),
    ('F7  unlock 洞府门槛',                  F7_OLD, F7_NEW),
    ('F8  farmHarvestOne + 三新端点',        F8_OLD, F8_NEW),
]

# 链序依赖（取自 0.8.6 定版产物实测计数）
REQUIRES = [
    ("const FARM_SLOTS = 3;", 1, "Y19 基线锚必须在位（未被前环改动）"),
    ("idx_farm_active_slot", 3, "spirit_farm 基线在位"),
    ("/api/fun/card", 1, "fun086 必须先跑过（本环为其后继）"),
    ("actApplyGain(", 8, "T5 挂点计数基线：定义 1 + 调用 7"),
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 链序依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle, n, cnt, why))

    # 2) 幂等
    if "farm_daily_care" in src or "FARM_UNLOCK_GROTTO_LEVEL" in src:
        fail("source looks already patched（已存在 farm_daily_care / FARM_UNLOCK_GROTTO_LEVEL）")

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:120]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 5) 门禁
    base_cnt = {
        'actApplyGain(': src.count('actApplyGain('),
        'await resolveEventMults(now)': src.count('await resolveEventMults(now)'),
        'await resolveMentorGains(userId, now)': src.count('await resolveMentorGains(userId, now)'),
        'res.status(403': src.count('res.status(403'),
        'status: 403': src.count('status: 403'),
    }
    gates = [
        # ---- 本批新增 ----
        ('F2 FARM_SLOTS=6 唯一',            'const FARM_SLOTS = 6;', 1, None),
        ('F2 旧 FARM_SLOTS=3 清零',         'const FARM_SLOTS = 3;', 0, None),
        ('F1 farm_daily_care 建表',         'CREATE TABLE IF NOT EXISTS farm_daily_care', 1, None),
        ('F1 care 索引',                    'idx_farm_care_player_date', 1, None),
        ('F2 门槛表',                       'FARM_UNLOCK_GROTTO_LEVEL: Record<number, number> = { 4: 5, 5: 7, 6: 9 }', 1, None),
        ('F2 高阶作物×2',                   "grottoLevel: 5 },\n  zaohuaqinglian", 1, None),
        ('F3 farmYield mods 签名',          'mods?: { grottoBonus?: number; tendBonus?: number; streakDecay?: number; pest?: boolean }', 1, None),
        ('F3 新收益走 mods',                'const gainBase = farmYield(def, early, mods);', 1, None),
        ('F3 旧两参调用清零',               'const gainBase = farmYield(def, early);', 0, None),
        ('F3 虫害纯函数',                   'function farmPestToday(', 1, None),
        ('F3 催熟费纯函数',                 'function farmBoostCost(', 1, None),
        ('F3 催熟上限纯函数',               'function farmBoostCap(', 1, None),
        ('F3 地块上限纯函数',               'function farmSlotsForLevel(', 1, None),
        ('F6 公共收获原语',                 'async function farmHarvestOne(', 1, None),
        ('F8 boost 原子闸门',               'ON CONFLICT(player_id, slot, date) DO UPDATE SET boosted = 1 WHERE boosted = 0', 1, None),
        ('F8 tend 原子闸门',                'ON CONFLICT(player_id, slot, date) DO UPDATE SET tended = 1 WHERE tended = 0', 1, None),
        ('F8 三新端点 boost',               "app.post('/api/farm/boost'", 1, None),
        ('F8 三新端点 tend',                "app.post('/api/farm/tend'", 1, None),
        ('F8 三新端点 harvest/all',         "app.post('/api/farm/harvest/all'", 1, None),
        ('F8 harvest/all 汇总邮件',         '灵田丰收（一键收取）', 1, None),
        ('F5 plant 高阶门槛 409',           'needGrottoLevel: crop.grottoLevel', 1, None),
        ('F7 unlock 门槛 409',              'needGrottoLevel: needLevel', 1, None),
        ('F4 status 回执扩展',              'boostDaily: { used: boostUsed, cap: farmBoostCap(grottoLevel) }', 1, None),
        ('F5 plant 回执扩展',               'streakDecay: mods.streakDecay, pest: mods.pest', 1, None),
        # ---- 红线：T5 挂点零回归 / 403 纪律 / farmcore 标记 ----
        ('红线 actApplyGain 总量不变',       'actApplyGain(', base_cnt['actApplyGain('], 'base'),
        ('红线 resolveEventMults 不变',      'await resolveEventMults(now)', base_cnt['await resolveEventMults(now)'], 'base'),
        ('红线 resolveMentorGains 不变',     'await resolveMentorGains(userId, now)', base_cnt['await resolveMentorGains(userId, now)'], 'base'),
        ('红线 403（res 形式）零新增',       'res.status(403', base_cnt['res.status(403'], 'base'),
        ('红线 403（对象形式）零新增',       'status: 403', base_cnt['status: 403'], 'base'),
        ('farmcore 标记唯一起',              '// [farmcore]', 1, None),
        ('farmcore 标记唯一止',              '// [/farmcore]', 1, None),
        ('守卫式收获语句仅 1（farmHarvestOne 内）', 'SET harvested = 1 WHERE id = ? AND player_id = ? AND harvested = 0', 1, None),
        # ---- 基线未动 ----
        ('基线 spirit_farm 表未动',          'CREATE TABLE IF NOT EXISTS spirit_farm', 1, None),
        ('基线 farm_unlocks 表未动',         'CREATE TABLE IF NOT EXISTS farm_unlocks', 1, None),
        ('基线 三作物数值未动',              "lingcao:     { name: '灵草',   seed: 1000, minutes: 240,  stones: 800,   exp: 500 },", 1, None),
        ('基线 slot2/3 开垦价未动',          '{ 2: 20000, 3: 80000, 4: 200000', 1, None),
    ]
    ok = True
    for g in gates:
        label, needle, exp = g[0], g[1], g[2]
        op = g[3] if len(g) > 3 else None
        if op == 'base':
            shown = 'expect==base(%d)' % exp
        else:
            shown = 'expect==%d' % exp
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-40s actual=%d %s" % ("OK" if good else "FAIL", label, act, shown))
    if not ok:
        fail("门禁未全过")

    # 6) 顺序契约：boost 端点内「占位 → 守卫推进 → 扣款」必须严格递增
    i = out.find("app.post('/api/farm/boost'")
    j = out.find("app.post(", i + 30)
    seg = out[i:j if j > 0 else len(out)]
    p1 = seg.find('ON CONFLICT(player_id, slot, date) DO UPDATE SET boosted = 1')
    p2 = seg.find('SET mature_at = ? WHERE id = ?')
    p3 = seg.find('updatePlayerSave(userId')
    if not (0 <= p1 < p2 < p3):
        fail("boost 顺序契约被破坏：占位(%d) → 守卫推进(%d) → 扣款(%d) 必须严格递增" % (p1, p2, p3))
    print("  [OK] boost 顺序契约：占次数位 → 守卫推进 mature_at → 扣款（失败全补偿，无无对价扣款）")

    # 6b) farmHarvestOne 必须早于单收端点对它的调用点运行期可见（hoisted 声明，静态校验两者都在）
    if out.find('async function farmHarvestOne(') < 0 or out.find('await farmHarvestOne(userId, r)') < 0:
        fail("farmHarvestOne 定义/调用缺失")

    # 7) 往返自证：把每个 new 换回 old 必须逐字复现原文
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".t10farm-", suffix=".tmp")
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
