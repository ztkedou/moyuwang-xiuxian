# -*- coding: utf-8 -*-
r"""
srv_patch_p0_save.py -- P0 存档经济三缺陷 服务端补丁生成器（srv-econ）

Reads : srv/index_v28.ts   (current source of truth; in-place atomic rewrite)
Writes: srv/index_v28.ts

背景（三条，均在 idx=20 沙盒用真实 HTTP 复现，见 localtest/report_srv-econ.md）

  P0-1  通天塔/远征 LUMP 每次存档无条件放行
        `E2_TOWER_EXP_LUMP`(12e6) / `E2_EXPED_EXP_LUMP`(2e6) 的注释自己写着「一次性」，
        实现却是 `Math.min(dTowerExp, perMin*mins + LUMP)` —— 每次 /api/save 都白送一份额度。
        反复推档 = 无限白拿修为。
        修法：改成**服务端权威的终身额度池**，落在 saves 表新增列
        `tower_lump_left` / `exped_lump_left`（默认值=满额，老档自动迁移为「未发放」）。
        每次存档按「本次实际从池中支取」扣减，扣完为止；池余额客户端不可见、不可篡改。
        为什么是「池」而不是布尔标记：LUMP 覆盖的是「1..100 层全通累计 7,855,203」，
        是**累计**额度。若用布尔「首次超额即置位」，玩家打第 1 层（单层最高 375,920）
        就会把整池烧掉，之后真正的百层通关反而被钳死 —— 布尔会把正常玩家打残。

  P0-2  `mins` 下限截断（E2_MIN_SAVE_MINS = 0.5）—— option b：落库额度台账
        旧写法 `mins = max(0.5, Δt)` 同时驱动「逐类配额」与「每存档上限」。上限项
        `ECON_CLAMP_EXP_PER_MIN * mult * mins` 是一个**每请求常数**（Δt<0.5min 时恒等于
        rate*0.5），120 req/min 限流下稳态 Σcap = 120 × rate*0.5min = 60 × rate/min ⇒ 60x 放大。
        纯内存的窗口状态会在重启时清零 ⇒ 洞还在。故落库：
          saves 新增 `econ_win_start`(锚点 ms, NULL=未开窗) / `econ_win_exp` / `econ_win_stone`
          （本窗口内**已发放**的累计额度）。
        算法（每次存档）：
          elapsed  = now - winStart                （真实时间，无任何 0.5 下限）
          allow    = floor(rate * mult * elapsed)  （真实时间口径的累计应发放额度）
          grant    = max(0, allow - winExp)        （本次还能给多少）
          cap 时间项 = grant
          winExp  += 本次实际入账的增量（不超过 allow）
        ⇒ 刷档者稳态只能吃 `rate * 真实经过时间`（放大 1.0x）；挂机/离线玩家 credit 按真实
          时间累积，单次爆发（通天塔 100 层扫荡 2,356,523）由一次性池承担（见下），
          所以**不需要**旧的 0.5 下限 ⇒ `E2_MIN_SAVE_MINS` 不再出现在 capExp/capStone 路径上。
        锚点重置：首存（econ_win_start IS NULL，老档迁移）/ 时钟回拨 / 境界变化（mult 变了，
        旧 credit 定价失效）。重置时锚点取 prevSavedAtMs（真实上次存档时间），不是 now，
        避免「重置瞬间 allow=0 ⇒ 本次 cap=0」的断崖。

  P0-1 × P0-2 的衔接：一次性池改为**对时间上限的可加项**
        `capExp 时间项 = grantExp + lumpGrantExp`（lumpGrantExp = 本次可从池中支取的量）。
        这样单次爆发由池承担，不再依赖每请求的 0.5 下限 —— 既堵住 60x，又不误伤合法扫荡。
        池的扣减仍按「本次实际入账中来自池的部分」，不超发、不空扣。

  P0-3  POST /api/save 不校验存档结构
        `const saveData = req.body;` 之后只判 `if (!saveData)`。传 `{"logs":[]}` /
        `{"player":null}` / `{"player":[]}` 都 200 并把云档覆盖成没有 player 的对象 ⇒ 账号报废。
        修法：落库前做结构校验（规则由 bundle 实际提交体取证得出，见下），不合法 → 400
        `{error:'invalid_save'}` 且绝不落库。GM 的 updatePlayerSave 走另一条路径，不受影响。

  客户端实际提交体取证（bundle build/assets/index-v28-20260928.js, md5 515aaac94f3db6908aac0a728be5a6e1）：
    - 自动存档 10s：YLSync.push({player, logs, marketItems, timestamp, lastActiveTime})
    - dirty 事件：  同上
    - 手动存档：    Pn.pushSave({player, logs, timestamp})
    - 导入存档：    Pn.pushSave({player, logs, marketItems, timestamp, lastActiveTime})
    - pushSave 内部再补：t.dungeonGate = window.__ylDg||null; t.settings = settings
    ⇒ 顶层键是 {player, logs?, marketItems?, timestamp?, lastActiveTime?, dungeonGate?, settings?}，
      唯一的结构性必需字段是 `player`。沙盒库 22 个存量档统计：player 全部是 dict，
      name/realm 全部是 str，exp/spiritStones 全部是 int；但有 2 个档**没有** realmLevel/maxExp，
      也有档**没有** logs/timestamp ⇒ 校验规则绝不能要求这些字段（过严会误杀老档）。
    定案规则：body 是对象 且 player 是非 null 非数组对象 且 player.name/player.realm 是字符串。

Engineering guarantees (any failure => sys.exit(1), no write):
  1. every anchor occurs EXACTLY once in the source;
  2. round-trip equivalence: replacing each new fragment back with its old fragment yields
     the source byte-for-byte;
  3. every newly introduced identifier occurs 0 times in the source;
  4. no NEW non-ASCII is introduced: every maximal non-ASCII run in a `new` fragment must also
     occur in its `old` fragment (the file is Chinese-commented; this is the ASCII guarantee
     applied per-fragment so anchors may keep their original Chinese comments);
  5. the source is not already patched;
  6. gates: new forms present AND old forms zeroed.

NOTE（可复现性）：本补丁打在链式产物的**末端**（`index_v28.ts`），且是 in-place。
      若有人从 `index_v27b.ts` 重跑整条链，必须在最后再跑一次本脚本。

Run (cwd = yl-deploy/):
  python srv_patch_p0_save.py            # 就地打补丁（原子写）
  python srv_patch_p0_save.py --check    # 只体检，不写
"""
import argparse
import hashlib
import io
import os
import re
import sys
import tempfile

SRC = os.path.join("srv", "index_v28.ts")

# ---------------------------------------------------------------------------
# EDITS: (label, old, new)
# ---------------------------------------------------------------------------
EDITS = [
    # ===================== P0-1/P0-2 表结构：一次性池 + 额度台账 =====================
    # 1) saves 建表加五列（新库）
    (
        "saves-create-cols",
        "        CREATE TABLE IF NOT EXISTS saves (\n"
        "          id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
        "          user_id INTEGER NOT NULL UNIQUE,\n"
        "          save_data TEXT NOT NULL,\n"
        "          gm_revision INTEGER DEFAULT 0,\n"
        "          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,\n"
        "          FOREIGN KEY (user_id) REFERENCES users (id)\n"
        "        )",
        "        CREATE TABLE IF NOT EXISTS saves (\n"
        "          id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
        "          user_id INTEGER NOT NULL UNIQUE,\n"
        "          save_data TEXT NOT NULL,\n"
        "          gm_revision INTEGER DEFAULT 0,\n"
        "          tower_lump_left INTEGER NOT NULL DEFAULT 12000000,\n"
        "          exped_lump_left INTEGER NOT NULL DEFAULT 2000000,\n"
        "          econ_win_start INTEGER,\n"
        "          econ_win_exp INTEGER NOT NULL DEFAULT 0,\n"
        "          econ_win_stone INTEGER NOT NULL DEFAULT 0,\n"
        "          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,\n"
        "          FOREIGN KEY (user_id) REFERENCES users (id)\n"
        "        )",
    ),
    # 2) 存量库迁移：ALTER TABLE ADD COLUMN
    #    - 池默认值=满额 ⇒ 老档视为「未发放」（不白扣、不永不给）
    #    - econ_win_start 默认 NULL ⇒ 首次存档开窗（锚点取真实上次存档时间）
    (
        "saves-migrate-cols",
        "      // migration: 添加 gm_revision 字段（已有则跳过）\n"
        "      db.all(\"PRAGMA table_info(saves)\", (err: any, rows: any[]) => {\n"
        "        if (!err && rows && !rows.some((r: any) => r.name === 'gm_revision')) {\n"
        "          db.exec('ALTER TABLE saves ADD COLUMN gm_revision INTEGER DEFAULT 0');\n"
        "        }\n"
        "      });",
        "      // migration: 添加 gm_revision 字段（已有则跳过）\n"
        "      db.all(\"PRAGMA table_info(saves)\", (err: any, rows: any[]) => {\n"
        "        if (!err && rows && !rows.some((r: any) => r.name === 'gm_revision')) {\n"
        "          db.exec('ALTER TABLE saves ADD COLUMN gm_revision INTEGER DEFAULT 0');\n"
        "        }\n"
        "      });\n"
        "\n"
        "      // v28 P0-1/P0-2 migration: one-time tower/expedition exp pools + the persisted\n"
        "      // real-time allowance ledger. Pool default = FULL (= \"never granted yet\", so legacy\n"
        "      // saves get the one-time lump exactly once and are never silently zeroed).\n"
        "      // econ_win_start stays NULL for every existing row = \"window not opened yet\" -> the\n"
        "      // first save anchors it at the real previous save time (no zero-grant cliff).\n"
        "      db.all(\"PRAGMA table_info(saves)\", (err: any, rows: any[]) => {\n"
        "        if (!err && rows) {\n"
        "          if (!rows.some((r: any) => r.name === 'tower_lump_left')) db.exec('ALTER TABLE saves ADD COLUMN tower_lump_left INTEGER NOT NULL DEFAULT 12000000');\n"
        "          if (!rows.some((r: any) => r.name === 'exped_lump_left')) db.exec('ALTER TABLE saves ADD COLUMN exped_lump_left INTEGER NOT NULL DEFAULT 2000000');\n"
        "          if (!rows.some((r: any) => r.name === 'econ_win_start')) db.exec('ALTER TABLE saves ADD COLUMN econ_win_start INTEGER');\n"
        "          if (!rows.some((r: any) => r.name === 'econ_win_exp')) db.exec('ALTER TABLE saves ADD COLUMN econ_win_exp INTEGER NOT NULL DEFAULT 0');\n"
        "          if (!rows.some((r: any) => r.name === 'econ_win_stone')) db.exec('ALTER TABLE saves ADD COLUMN econ_win_stone INTEGER NOT NULL DEFAULT 0');\n"
        "        }\n"
        "      });",
    ),
    # 3) settleSaveEconV2 加池入参 + 台账入参
    (
        "econ-settle-signature",
        "function settleSaveEconV2(oldSd: any, newSd: any, prevSavedAtMs: number | null): string[] {",
        "// v28 P0-2b: `mins` is gone from the cap path. Every time-scaled allowance uses REAL\n"
        "// elapsed minutes (no floor); the per-save CEILING comes from the persisted allowance\n"
        "// ledger (saves.econ_win_*) instead of `rate * max(0.5, dt)` -- that per-request floor\n"
        "// was what a 120 req/min spammer multiplied into ~60x.\n"
        "function settleSaveEconV2(oldSd: any, newSd: any, prevSavedAtMs: number | null,"
        " lumpPool?: { tower: number; exped: number },"
        " winState?: { start: number | null; exp: number; stone: number }): string[] {",
    ),
    # 4) 时钟 + 额度台账（取代 `const mins = max(0.5, Δt)`）
    (
        "econ-ledger",
        "    const mins = prevSavedAtMs ? Math.max(E2_MIN_SAVE_MINS, (Date.now() - prevSavedAtMs) / 60000) : ECON_CLAMP_FIRST_SAVE_MINS;",
        "    const realMins = prevSavedAtMs ? Math.max(0, (Date.now() - prevSavedAtMs) / 60000) : ECON_CLAMP_FIRST_SAVE_MINS;\n"
        "    // v28 P0-2b: persisted real-time allowance ledger. The ceiling is the REMAINING\n"
        "    // cumulative allowance since the anchor: allow = rate * mult * elapsed, granted total\n"
        "    // persisted. Steady state a spammer can only consume rate * elapsed (1.0x), while an\n"
        "    // idle/offline player keeps the full real-time credit (no 0.5-floor regression).\n"
        "    const e2NowMs = Date.now();\n"
        "    const anchorRaw = winState ? winState.start : null;\n"
        "    const anchor0: number | null = (typeof anchorRaw === 'number' && Number.isFinite(anchorRaw) && anchorRaw > 0)\n"
        "      ? anchorRaw : null;\n"
        "    let winExp = winState ? Math.max(0, Math.floor(Number(winState.exp) || 0)) : 0;\n"
        "    let winStone = winState ? Math.max(0, Math.floor(Number(winState.stone) || 0)) : 0;\n"
        "    const oldRealmIdx = Math.max(0, ECON_REALM_ORDER.indexOf(String((op && op.realm) || '')));\n"
        "    const reanchor = anchor0 === null || anchor0 > e2NowMs || oldRealmIdx !== realmIdx;\n"
        "    const winStart: number = reanchor\n"
        "      ? (prevSavedAtMs != null ? prevSavedAtMs : e2NowMs - ECON_CLAMP_FIRST_SAVE_MINS * 60000)\n"
        "      : (anchor0 as number);\n"
        "    if (reanchor) { winExp = 0; winStone = 0; }\n"
        "    const elapsedMs = Math.max(0, e2NowMs - winStart);\n"
        "    const allowExp = Math.floor(ECON_CLAMP_EXP_PER_MIN * mult * (elapsedMs / 60000));\n"
        "    // v28 P0-2c: ylScale is hoisted here so allowStone is expressed in the SAME scale as\n"
        "    // winStone / appliedStone. The old shape left allowStone unscaled while capStone\n"
        "    // multiplied it by ylScale, so the ledger mixed a pre-scale allowance with post-scale\n"
        "    // consumption -- at low realms (ylScale 4/3) that let stone throughput exceed the rate\n"
        "    // line (measured up to 2.25x at qi-refining). The value of ylScale is unchanged.\n"
        "    const ylScale = (realmIdx <= 0 ? 4 / 3 : 2 * realmIdx + 1) / 3; // YL_REALM_REWARD_SCALE_V26L realmScale (realmIdx=1 => 1x, 6 => 13/3)\n"
        "    const allowStone = Math.floor((Math.floor(E2_STONE_BURST_PER_HOUR * mult * (elapsedMs / 3600000)) + E2_STONE_BURST_BASE) * ylScale);\n"
        "    const grantExp = Math.max(0, allowExp - winExp);\n"
        "    const grantStone = Math.max(0, allowStone - winStone);",
    ),
    # 5) 计数器增速上限：mins -> realMins
    (
        "econ-cnt-med-mins",
        "    const cMed = Math.ceil(mins * 300) + 30;   // 自动打坐 200ms/次 → 300 次/分",
        "    const cMed = Math.ceil(realMins * 300) + 30;   // 自动打坐 200ms/次 → 300 次/分",
    ),
    (
        "econ-cnt-adv-mins",
        "    const cAdv = Math.ceil(mins * 130) + 30;   // 自动历练 500ms/次 → 120 次/分",
        "    const cAdv = Math.ceil(realMins * 130) + 30;   // 自动历练 500ms/次 → 120 次/分",
    ),
    (
        "econ-cnt-sr-mins",
        "    const cSR = Math.ceil(mins * 4) + 6;       // 秘境门每日 3 次 + 战斗内秘境富余",
        "    const cSR = Math.ceil(realMins * 4) + 6;       // 秘境门每日 3 次 + 战斗内秘境富余",
    ),
    # 6) 出售额度：mins -> realMins
    (
        "econ-sell-mins",
        "      Math.floor(E2_SELL_PER_HOUR * mult * (mins / 60)) + 50000);",
        "      Math.floor(E2_SELL_PER_HOUR * mult * (realMins / 60)) + 50000);",
    ),
    # 7) 池变量 + 台账可加项（插在 capExp 之前）
    (
        "econ-lump-pool-vars",
        "    const capExp = Math.min(ECON_CLAMP_ABS_MAX,",
        "    // v28 P0-1: one-time LUMP pools. Server-authoritative lifetime allowance, NOT a per-save\n"
        "    // bonus: drawn down by what each save actually consumes, never refilled.\n"
        "    const towerPerMin = Math.floor(E2_TOWER_EXP_PER_MIN * mult * realMins);\n"
        "    const expedPerMin = Math.floor(E2_EXPED_EXP_PER_MIN * mult * realMins);\n"
        "    const towerLumpLeft = lumpPool ? Math.max(0, Math.floor(Number(lumpPool.tower) || 0)) : 0;\n"
        "    const expedLumpLeft = lumpPool ? Math.max(0, Math.floor(Number(lumpPool.exped) || 0)) : 0;\n"
        "    // v28 P0-2b: the one-time pools are ADDITIVE to the rate-based ceiling, so a legitimate\n"
        "    // single burst (100-floor tower sweep 2,356,523) is covered by the pool instead of by a\n"
        "    // per-request 0.5-min floor -- which is exactly what made the old ceiling exploitable.\n"
        "    const towerOver = Math.max(0, dTowerExp - towerPerMin);\n"
        "    const expedOver = Math.max(0, dExpedExp - expedPerMin);\n"
        "    const towerLumpGrant = Math.min(towerOver, towerLumpLeft);\n"
        "    const expedLumpGrant = Math.min(expedOver, expedLumpLeft);\n"
        "    const lumpGrantExp = towerLumpGrant + expedLumpGrant;\n"
        "    const capExp = Math.min(ECON_CLAMP_ABS_MAX,",
    ),
    # 8) capExp 时间项：每请求常数 -> 台账剩余额度 + 一次性池可加项
    (
        "econ-cap-exp-time",
        "      Math.floor(ECON_CLAMP_EXP_PER_MIN * mult * mins),          // P0-1 修为总额兜底（合法峰值无实测收紧数据，本批不收紧）",
        "      grantExp + lumpGrantExp,                                    // P0-1 修为总额兜底（合法峰值无实测收紧数据，本批不收紧）",
    ),
    # 9) capExp 累加项里的 LUMP 换成池余额
    (
        "econ-cap-exp-lump",
        "        + Math.min(dTowerExp, Math.floor(E2_TOWER_EXP_PER_MIN * mult * mins) + E2_TOWER_EXP_LUMP)\n"
        "        + Math.min(dExpedExp, Math.floor(E2_EXPED_EXP_PER_MIN * mult * mins) + E2_EXPED_EXP_LUMP)",
        "        + dTowerExp\n"
        "        + dExpedExp",
    ),
    # 10) capStone 时间项：每请求常数 -> 台账剩余额度
    (
        "econ-cap-stone-time",
        "      Math.floor((Math.floor(E2_STONE_BURST_PER_HOUR * mult * (mins / 60)) + E2_STONE_BURST_BASE) * ylScale), // ③ 灵石总额兜底",
        "      Math.floor(grantStone), // ③ 灵石总额兜底",
    ),
    # 11) 结算后：按「本次实际入账」扣池 + 提交台账
    (
        "econ-commit-and-draw",
        "    // 5) 物品数量轻钳制（NaN/负→1，单组上限 1e6；不做总量钳制防误伤囤草党）",
        "    // v28 P0-1c: settle the ledger and the one-time pools by what this save ACTUALLY applied\n"
        "    // under the final cap (never more than was granted).\n"
        "    // INVARIANT: the pool draw-down must depend ONLY on server-observed data (`appliedExp` =\n"
        "    //   the exp actually committed under the final cap) plus server constants. It must NOT\n"
        "    //   depend on `off.exp` / `dMed` / `dAdv` / `dKill` / `dSR` / the old `expSumNoLump` --\n"
        "    //   every one of those is forgeable from the submitted save. Inflating `adventureCount`\n"
        "    //   to its own clamp (cAdv = 31 at dt->0) alone pushed the old `expSumNoLump` to\n"
        "    //   31 * advEach = 9.9e8 at longevity lv9 => `avail` = 0 => `twApplied` = 0 => the tower\n"
        "    //   pool was NEVER drawn => the full 7,855,203 burst was re-granted on EVERY save, forever.\n"
        "    //   Fix: draw each pool by `min(grant, appliedExp)`. Since the pool shrinks by exactly the\n"
        "    //   amount drawn, `sum(pool-funded exp) <= pool size` holds by construction, for ANY\n"
        "    //   submitted payload.\n"
        "    {\n"
        "      const appliedExp = Math.max(0, Math.floor(Number(np.exp) || 0) - Math.floor(Number(op.exp) || 0));\n"
        "      const appliedStone = Math.max(0, Math.floor(Number(np.spiritStones) || 0) - Math.floor(Number(op.spiritStones) || 0));\n"
        "      // The pool may only be charged for exp ABOVE the rate line (towerPerMin + expedPerMin is\n"
        "      // already covered by the ledger/accumulator). `min(capExp, appliedExp)` is server-computed\n"
        "      // (capExp) or server-observed (appliedExp = committed np.exp - stored op.exp).\n"
        "      const appliedOverRate = Math.max(0, Math.min(capExp, appliedExp) - towerPerMin - expedPerMin);\n"
        "      const lumpApplied = Math.min(lumpGrantExp, appliedOverRate);\n"
        "      if (lumpPool) {\n"
        "        const towerDraw = lumpGrantExp > 0\n"
        "          ? Math.floor(lumpApplied * towerLumpGrant / lumpGrantExp) : 0;\n"
        "        const expedDraw = lumpApplied - towerDraw;\n"
        "        lumpPool.tower = Math.floor(Math.max(0, towerLumpLeft - towerDraw));\n"
        "        lumpPool.exped = Math.floor(Math.max(0, expedLumpLeft - expedDraw));\n"
        "      }\n"
        "      if (winState) {\n"
        "        winState.start = winStart;\n"
        "        winState.exp = Math.min(allowExp, winExp + appliedExp);\n"
        "        winState.stone = Math.min(allowStone, winStone + appliedStone);\n"
        "      }\n"
        "    }\n"
        "\n"
        "    // 5) 物品数量轻钳制（NaN/负→1，单组上限 1e6；不做总量钳制防误伤囤草党）",
    ),
    # 12) 三个辅助函数（池读取 + 台账读取 + 结构校验）
    (
        "econ-helpers",
        "  } catch { /* 结算挂掉绝不影响存档主路径（与 P0-1 同纪律） */ }\n"
        "  return clamped;\n"
        "}",
        "  } catch { /* 结算挂掉绝不影响存档主路径（与 P0-1 同纪律） */ }\n"
        "  return clamped;\n"
        "}\n"
        "\n"
        "// v28 P0-1: read the one-time pool balance from the authoritative saves columns. A missing or\n"
        "// NULL value (pre-migration row / older DB) means \"full allowance\", i.e. never granted yet.\n"
        "function lumpPoolFromRow(row: any): { tower: number; exped: number } {\n"
        "  const pick = (v: any, full: number): number => {\n"
        "    if (v === null || v === undefined) return full;\n"
        "    const n = Number(v);\n"
        "    return Number.isFinite(n) ? Math.max(0, Math.floor(n)) : full;\n"
        "  };\n"
        "  return {\n"
        "    tower: pick(row && row.tower_lump_left, E2_TOWER_EXP_LUMP),\n"
        "    exped: pick(row && row.exped_lump_left, E2_EXPED_EXP_LUMP),\n"
        "  };\n"
        "}\n"
        "\n"
        "// v28 P0-2b: read the persisted allowance ledger. econ_win_start NULL = window not opened\n"
        "// yet (legacy row / new account) -> settleSaveEconV2 anchors it at the real previous save time.\n"
        "function winStateFromRow(row: any): { start: number | null; exp: number; stone: number } {\n"
        "  const num = (v: any): number => {\n"
        "    const n = Number(v);\n"
        "    return Number.isFinite(n) ? Math.max(0, Math.floor(n)) : 0;\n"
        "  };\n"
        "  const s = row ? Number(row.econ_win_start) : NaN;\n"
        "  return {\n"
        "    start: Number.isFinite(s) && s > 0 ? s : null,\n"
        "    exp: num(row && row.econ_win_exp),\n"
        "    stone: num(row && row.econ_win_stone),\n"
        "  };\n"
        "}\n"
        "\n"
        "// v28 P0-3: POST /api/save body shape guard, derived from the client's real payload (see the\n"
        "// header of srv_patch_p0_save.py). `player` is the only structural requirement; requiring more\n"
        "// (logs/timestamp/realmLevel/maxExp) would reject legitimate legacy saves.\n"
        "function isValidSavePayload(sd: any): boolean {\n"
        "  if (!sd || typeof sd !== 'object' || Array.isArray(sd)) return false;\n"
        "  const p = sd.player;\n"
        "  if (!p || typeof p !== 'object' || Array.isArray(p)) return false;\n"
        "  if (typeof p.name !== 'string' || typeof p.realm !== 'string') return false;\n"
        "  return true;\n"
        "}",
    ),
    # ===================== /api/save 路由 =====================
    # 13) P0-3 结构校验（落库前，绝不写）
    (
        "save-validate-body",
        "  const saveData = req.body;\n"
        "\n"
        "  if (!saveData) {\n"
        "    return res.status(400).json({ error: 'Save data is required' });\n"
        "  }",
        "  const saveData = req.body;\n"
        "\n"
        "  if (!saveData) {\n"
        "    return res.status(400).json({ error: 'Save data is required' });\n"
        "  }\n"
        "  // v28 P0-3: reject malformed payloads (e.g. {\"logs\":[]}, {\"player\":null}, {\"player\":[]})\n"
        "  // BEFORE any DB write. Previously such a body was stored verbatim and bricked the account.\n"
        "  if (!isValidSavePayload(saveData)) {\n"
        "    return res.status(400).json({ error: 'invalid_save' });\n"
        "  }",
    ),
    # 14) 读档时一并取池余额 + 台账
    (
        "save-select-cols",
        "    db.get('SELECT save_data, gm_revision, updated_at FROM saves WHERE user_id = ?', [req.user.id], (err, row: any) => {",
        "    db.get('SELECT save_data, gm_revision, updated_at, tower_lump_left, exped_lump_left, econ_win_start, econ_win_exp, econ_win_stone FROM saves WHERE user_id = ?', [req.user.id], (err, row: any) => {",
    ),
    # 15) 结算调用带上池与台账
    (
        "save-settle-pass-state",
        "      let clampedFields: string[] = settleSaveEconV2(row && !econSkip ?",
        "      // v28 P0-1/P0-2b: pool balance + allowance ledger for this save (missing -> defaults).\n"
        "      const lumpPool = row ? lumpPoolFromRow(row) : { tower: E2_TOWER_EXP_LUMP, exped: E2_EXPED_EXP_LUMP };\n"
        "      const winState = row ? winStateFromRow(row) : { start: null, exp: 0, stone: 0 };\n"
        "      let clampedFields: string[] = settleSaveEconV2(row && !econSkip ?",
    ),
    (
        "save-settle-arg-state",
        "return Number.isFinite(t) ? t : null; })() : null);",
        "return Number.isFinite(t) ? t : null; })() : null, lumpPool, winState);",
    ),
    # 16) UPDATE 写回池余额 + 台账
    (
        "save-update-sql-state",
        "'UPDATE saves SET save_data = ?, gm_revision = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', // S2 v26c：玩家写递增修订号",
        "'UPDATE saves SET save_data = ?, gm_revision = ?, tower_lump_left = ?, exped_lump_left = ?, econ_win_start = ?, econ_win_exp = ?, econ_win_stone = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', // S2 v26c：玩家写递增修订号",
    ),
    (
        "save-update-params-state",
        "[saveDataStringClamped, curRev + 1, req.user.id],",
        "[saveDataStringClamped, curRev + 1, lumpPool.tower, lumpPool.exped, winState.start, winState.exp, winState.stone, req.user.id],",
    ),
    # 17) INSERT（首存）写回池余额 + 台账
    (
        "save-insert-sql-state",
        "'INSERT INTO saves (user_id, save_data, gm_revision) VALUES (?, ?, 1)',",
        "'INSERT INTO saves (user_id, save_data, gm_revision, tower_lump_left, exped_lump_left, econ_win_start, econ_win_exp, econ_win_stone) VALUES (?, ?, 1, ?, ?, ?, ?, ?)',",
    ),
    (
        "save-insert-params-state",
        "[req.user.id, saveDataStringClamped],",
        "[req.user.id, saveDataStringClamped, lumpPool.tower, lumpPool.exped, winState.start, winState.exp, winState.stone],",
    ),
    # 18) ylScale 原定义行 → 注释（定义已 hoist 到 econ-ledger；capStone 第 3 项仍引用该绑定）
    #     锚点含下一行 capStone，避免与 econ-ledger 新增的同名定义行混淆。
    (
        "econ-yscale-hoist",
        "    const ylScale = (realmIdx <= 0 ? 4 / 3 : 2 * realmIdx + 1) / 3; // YL_REALM_REWARD_SCALE_V26L realmScale (realmIdx=1 => 1x, 6 => 13/3)\n"
        "    const capStone = Math.min(ECON_CLAMP_ABS_MAX,",
        "    // v28 P0-2c: ylScale definition moved up into econ-ledger (above allowStone) so the\n"
        "    // stone allowance ledger is scale-consistent; the scaled accumulator terms below\n"
        "    // still reference that hoisted binding. Value unchanged.\n"
        "    const capStone = Math.min(ECON_CLAMP_ABS_MAX,",
    ),
]

NEW_IDENTIFIERS = [
    "tower_lump_left",
    "exped_lump_left",
    "econ_win_start",
    "econ_win_exp",
    "econ_win_stone",
    "realMins",
    "winState",
    "winStateFromRow",
    "winStart",
    "winExp",
    "winStone",
    "allowExp",
    "allowStone",
    "grantExp",
    "grantStone",
    "elapsedMs",
    "e2NowMs",
    "anchor0",
    "anchorRaw",
    "reanchor",
    "oldRealmIdx",
    "lumpPoolFromRow",
    "isValidSavePayload",
    "towerPerMin",
    "expedPerMin",
    "towerLumpLeft",
    "expedLumpLeft",
    "towerOver",
    "expedOver",
    "towerLumpGrant",
    "expedLumpGrant",
    "lumpGrantExp",
    "appliedExp",
    "appliedStone",
    "appliedOverRate",
    "lumpApplied",
    "towerDraw",
    "expedDraw",
    "invalid_save",
]

# 门禁：新写法必须存在（各恰好 1 次）
GATES_NEW = [
    ("tower_lump_left INTEGER NOT NULL DEFAULT 12000000,\n", 1),
    ("ADD COLUMN tower_lump_left INTEGER NOT NULL DEFAULT 12000000');", 1),
    ("exped_lump_left INTEGER NOT NULL DEFAULT 2000000,\n", 1),
    ("ADD COLUMN exped_lump_left INTEGER NOT NULL DEFAULT 2000000');", 1),
    ("econ_win_start INTEGER,\n", 1),
    ("ADD COLUMN econ_win_start INTEGER');", 1),
    ("econ_win_exp INTEGER NOT NULL DEFAULT 0,\n", 1),
    ("ADD COLUMN econ_win_exp INTEGER NOT NULL DEFAULT 0');", 1),
    ("econ_win_stone INTEGER NOT NULL DEFAULT 0,\n", 1),
    ("ADD COLUMN econ_win_stone INTEGER NOT NULL DEFAULT 0');", 1),
    ("const realMins = prevSavedAtMs ? Math.max(0, (Date.now() - prevSavedAtMs) / 60000) : ECON_CLAMP_FIRST_SAVE_MINS;", 1),
    ("const grantExp = Math.max(0, allowExp - winExp);", 1),
    ("const grantStone = Math.max(0, allowStone - winStone);", 1),
    ("const allowStone = Math.floor((Math.floor(E2_STONE_BURST_PER_HOUR * mult * (elapsedMs / 3600000)) + E2_STONE_BURST_BASE) * ylScale);", 1),
    ("    const ylScale = (realmIdx <= 0 ? 4 / 3 : 2 * realmIdx + 1) / 3; // YL_REALM_REWARD_SCALE_V26L realmScale (realmIdx=1 => 1x, 6 => 13/3)", 1),
    ("Math.ceil(realMins * 300) + 30", 1),
    ("Math.ceil(realMins * 130) + 30", 1),
    ("Math.ceil(realMins * 4) + 6", 1),
    ("E2_SELL_PER_HOUR * mult * (realMins / 60)", 1),
    ("      grantExp + lumpGrantExp,", 1),
    ("      Math.floor(grantStone), // ③ 灵石总额兜底", 1),
    ("        + dTowerExp\n", 1),
    ("        + dExpedExp", 1),
    ("const appliedOverRate = Math.max(0, Math.min(capExp, appliedExp) - towerPerMin - expedPerMin);", 1),
    ("const lumpApplied = Math.min(lumpGrantExp, appliedOverRate);", 1),
    ("const towerDraw = lumpGrantExp > 0", 1),
    ("const expedDraw = lumpApplied - towerDraw;", 1),
    ("lumpPool.tower = Math.floor(Math.max(0, towerLumpLeft - towerDraw));", 1),
    ("lumpPool.exped = Math.floor(Math.max(0, expedLumpLeft - expedDraw));", 1),
    ("const anchor0: number | null = (typeof anchorRaw === 'number' && Number.isFinite(anchorRaw) && anchorRaw > 0)", 1),
    ("winState.exp = Math.min(allowExp, winExp + appliedExp);", 1),
    ("winState.stone = Math.min(allowStone, winStone + appliedStone);", 1),
    ("function lumpPoolFromRow(row: any): { tower: number; exped: number } {", 1),
    ("function winStateFromRow(row: any): { start: number | null; exp: number; stone: number } {", 1),
    ("function isValidSavePayload(sd: any): boolean {", 1),
    ("return res.status(400).json({ error: 'invalid_save' });", 1),
    ("const lumpPool = row ? lumpPoolFromRow(row) :", 1),
    ("const winState = row ? winStateFromRow(row) : { start: null, exp: 0, stone: 0 };", 1),
    ("})() : null, lumpPool, winState);", 1),
    ("tower_lump_left = ?, exped_lump_left = ?, econ_win_start = ?, econ_win_exp = ?, econ_win_stone = ?", 1),
    ("lumpPool.tower, lumpPool.exped, winState.start, winState.exp, winState.stone, req.user.id],", 1),
    ("VALUES (?, ?, 1, ?, ?, ?, ?, ?)", 1),
    ("[req.user.id, saveDataStringClamped, lumpPool.tower, lumpPool.exped, winState.start, winState.exp, winState.stone],", 1),
]

# 门禁：旧写法必须清零（0 次）
GATES_OLD = [
    "Math.max(E2_MIN_SAVE_MINS, (Date.now() - prevSavedAtMs) / 60000)",
    "Math.ceil(mins * 300) + 30",
    "Math.ceil(mins * 130) + 30",
    "Math.ceil(mins * 4) + 6",
    "E2_SELL_PER_HOUR * mult * (mins / 60)",
    "Math.floor(ECON_CLAMP_EXP_PER_MIN * mult * mins),",
    "Math.floor(E2_STONE_BURST_PER_HOUR * mult * (mins / 60))",
    "+ E2_TOWER_EXP_LUMP)",
    "+ E2_EXPED_EXP_LUMP)",
    "      + Math.max(100, lvlMaxExp * 0.05);",
    "      Math.floor(grantStone * ylScale),",
    "    const allowStone = Math.floor(E2_STONE_BURST_PER_HOUR * mult * (elapsedMs / 3600000)) + E2_STONE_BURST_BASE;",
    # ★ P0-① bypass fix: the old pool draw-down keyed off forgeable inputs. These forms must be GONE.
    "    const towerAllow = towerPerMin + towerLumpLeft;",
    "    const expedAllow = expedPerMin + expedLumpLeft;",
    "    const expSumNoLump = off.exp + dMed * medEach",
    "      const avail = Math.max(0, Math.min(capExp, appliedExp) - expSumNoLump);",
    "      const twApplied = Math.min(dTowerExp, towerAllow, avail);",
    "      const exApplied = Math.min(dExpedExp, expedAllow, Math.max(0, avail - twApplied));",
    "        lumpPool.tower = Math.floor(Math.max(0, towerLumpLeft - Math.max(0, twApplied - towerPerMin)));",
    "        lumpPool.exped = Math.floor(Math.max(0, expedLumpLeft - Math.max(0, exApplied - expedPerMin)));",
    "db.get('SELECT save_data, gm_revision, updated_at FROM saves WHERE user_id = ?', [req.user.id], (err, row: any) => {",
    "'UPDATE saves SET save_data = ?, gm_revision = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', // S2 v26c",
    "'INSERT INTO saves (user_id, save_data, gm_revision) VALUES (?, ?, 1)'",
    "[saveDataStringClamped, curRev + 1, req.user.id],",
    "[req.user.id, saveDataStringClamped],",
]

_NON_ASCII = re.compile(r"[^\x00-\x7f]+")


def fail(msg: str) -> None:
    print("FAIL: " + msg)
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

    # 5) already patched?
    for label, old, new in EDITS:
        if new in src and old not in src:
            fail("source looks already patched at %s" % label)

    # 1) anchor uniqueness
    for label, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("anchor %s occurs %d times (want exactly 1): %r" % (label, n, old[:90]))

    # 4) no NEW non-ASCII
    for label, old, new in EDITS:
        old_runs = set(_NON_ASCII.findall(old))
        for run in _NON_ASCII.findall(new):
            if run not in old_runs:
                fail("edit %s introduces new non-ASCII text %r" % (label, run))

    # 3) new identifiers must not already exist
    for ident in NEW_IDENTIFIERS:
        if re.search(r"(?<![A-Za-z0-9_$])" + re.escape(ident) + r"(?![A-Za-z0-9_$])", src):
            fail("identifier %r already present in source" % ident)

    # apply
    product = src
    for label, old, new in EDITS:
        product = product.replace(old, new, 1)

    # 2) round-trip byte equivalence
    rt = product
    for label, old, new in reversed(EDITS):
        if rt.count(new) != 1:
            fail("round-trip: fragment %s occurs %d times in product" % (label, rt.count(new)))
        rt = rt.replace(new, old, 1)
    if rt != src:
        fail("round-trip mismatch: product is not byte-equivalent to source")

    # 6) gates
    for frag, want in GATES_NEW:
        got = product.count(frag)
        if got != want:
            fail("gate(new) %r occurs %d times (want %d)" % (frag[:70], got, want))
    for frag in GATES_OLD:
        got = product.count(frag)
        if got != 0:
            fail("gate(old) %r still occurs %d times (want 0)" % (frag[:70], got))

    if a.check:
        print("CHECK OK: anchors unique, round-trip byte-exact, no new non-ASCII, gates hold")
        print("  src     md5=%s  bytes=%d" % (hashlib.md5(src.encode("utf-8")).hexdigest(), len(src.encode("utf-8"))))
        print("  product md5=%s  bytes=%d" % (hashlib.md5(product.encode("utf-8")).hexdigest(), len(product.encode("utf-8"))))
        for label, old, new in EDITS:
            print("    + %-26s injected chars=%d" % (label, len(new) - len(old)))
        return

    # atomic in-place write
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".p0patch.", suffix=".tmp")
    try:
        with io.open(fd, "w", encoding="utf-8", newline="") as f:
            f.write(product)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    print("PATCH OK: %s" % src_path)
    print("  old md5=%s" % hashlib.md5(src.encode("utf-8")).hexdigest())
    print("  new md5=%s  bytes=%d (+%d)" % (
        hashlib.md5(product.encode("utf-8")).hexdigest(),
        len(product.encode("utf-8")),
        len(product.encode("utf-8")) - len(src.encode("utf-8")),
    ))


if __name__ == "__main__":
    main()
