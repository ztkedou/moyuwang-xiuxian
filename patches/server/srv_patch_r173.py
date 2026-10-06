# -*- coding: utf-8 -*-
r"""
srv_patch_r173.py -- R-173 离线时长精准测算：服务端权威「最后活跃时刻」（服务端环）

  ★ 环号说明：当前 srv/index_v28.ts 末环 = R-165（[r165wudao]）⇒ 本环顺延 **R-173**。
    锚点全部落在「离线收益 / 鉴权中间件 / saves 建表迁移」三处，与 r160/r163/r165 锚区零交集。

台账原文（R-173，逐字）
--------------------------------------------------------------------------
  「挂机收益是不是好像现在在线也在计算时长？这个我不太确定是否算的准确，之前的离线修炼
    奖励好像能精准计算出真正离线的时间。这个有没有办法精准的测算离线的时间？而不是在线的
    时候也会被算进去。真正离线了却计算少了」

改前取证（srv/index_v28.ts 字符级实测 + 客户端 bundle 实测）
--------------------------------------------------------------------------
  [证据 1] 锚点纯函数 offlineAnchor() @5499-5514（现状）：
      const cl = (claimedUntilMs != null && Number.isFinite(Number(claimedUntilMs))) ? Number(claimedUntilMs) : 0;
      if (l != null && l > cl) {                       // l = 客户端上报的 last_seen_at
        const end = (r != null && r > l) ? r : nowMs;  // r = 客户端上报的 last_resume_at
        return { anchorMs: Math.max(l, cl), endMs: end, source: 'last_seen_at' };
      }
      return { anchorMs: u, endMs: nowMs, source: 'updated_at' };   // u = updated_at
    ⇒ 窗口末端 endMs 完全由客户端上报的 last_resume_at 决定；一旦「回来」事件缺失，
      endMs 恒回落 nowMs ⇒ 窗口随**在线时长**继续增长（症状①「在线也被算进离线」）。

  [证据 2] POST /api/session/presence @5521-5550（事件源，R-021/R-149）：
      away：UPDATE saves SET last_seen_at = <本行 updated_at> WHERE user_id = ?
      back：UPDATE saves SET last_resume_at = <Date.now()>   WHERE user_id = ?
    ⇒ 离线锚点完全依赖这两个**客户端事件**是否送达；服务端没有任何独立可信的活跃时刻。

  [证据 3] 客户端实现（build/assets/index-v2925-20261006.js · YlxwPresence*）：
      function YlxwPresenceSend(state) {
        fetch(YlxwPresenceUrl(), { method: "POST", keepalive: true, ...,
          body: JSON.stringify({ state: state }) }).catch(function () {});
      }
      document.addEventListener("visibilitychange", ... hidden -> Away / visible -> Back);
      window.addEventListener("pagehide",  -> Away);
      window.addEventListener("beforeunload", -> Away);
    ⇒ away/back 都是 `keepalive` fetch + `.catch(){}` 静默吞错，**送达不保证**：
      · beforeunload 在移动端/iOS 常不触发；崩溃 / 强杀 / 后台回收 ⇒ away 根本没发出；
      · keepalive 请求被浏览器丢弃 / 网络抖动 / bfcache 恢复无 visibilitychange
        ⇒ back 没送达；
      · YlxwPresenceAway() 还有 `if (STATE === "hidden") return;` 短路，状态错位时不再补发。
    ⇒ 两个症状各自对应一条确定的失败路径：
      症状①：away 送达、back 丢失 ⇒ last_resume_at 不更新 ⇒ offlineAnchor endMs=nowMs
             ⇒ 玩家已回到线上，窗口仍随在线时长增长。
      症状②：away 丢失（崩溃/强杀/移动端回收）⇒ last_seen_at 停在旧值，叠加旧 last_resume_at
             的封口 ⇒ 新的一段真离线永远落在 [旧锚点, 旧封口] 之外 ⇒ 真离线被算少。

  [证据 4] 领取端点 POST /api/offline/claim @12931-12991：offline_claimed_until 在**所有**领取路径
    都有写：@12956 守卫式单语句推进（成功）+ @12973 入档失败补偿回退 ⇒ 幂等本身没问题；
    问题只在**窗口起止**（offlineAnchor 的 anchor/end）。

  [证据 5] 表 saves 的列：updated_at（客户端每 10s 心跳存档刷新 ⇒ 不可当锚点）、last_seen_at、
    last_resume_at、offline_claimed_until（三列均由既有 `db.all("PRAGMA table_info(saves)")`
    回调 + safeAddColumn 幂等建列，见 @155-171 / @313-324）。

改法（1 处建列 + 1 处鉴权挂点 + 1 处锚点函数扩展 + 1 段新逻辑 + 4 处 report/claim 接线）
--------------------------------------------------------------------------
  新增 saves.last_active_at（服务端权威「最后活跃时刻」，ms）：
    · 建列：复用**既有** PRAGMA 快路径回调 + safeAddColumn（后者容忍 duplicate column name
      ⇒ 冷启动/重跑幂等）。**不新增任何 PRAGMA 语句**（红线）。
    · 打点：在 authenticateToken() 里 `res.on('finish', ...)` —— 已鉴权请求**响应结束后**，
      按 60s/人节流落一次库（进程内 Map 节流，降写放大；无常驻定时器）。
      ★ 放在响应之后 ⇒ /api/offline/report|claim 读到的是**本次请求之前**的快照，否则窗口恒 0。
    · 锚点：offlineAnchor() 末尾新增可选参数 lastActiveAtMs，**最高优先级**：
        a != null ⇒ anchorMs = max(a, cl)，endMs = (r > a ? r : nowMs)，source='last_active_at'。
        a == null（老行/未打点）⇒ **逐位回落**原 R-021 口径（last_seen_at → updated_at）。
    · 保留未领取窗口（R-149 精神）：打点时若「本次请求之前」已存在 ≥ OFFLINE_MIN_MS 的
      **未领取**可结算窗口，则**冻结锚点**（last_active_at 不推进）并封口（last_resume_at=now），
      避免在线期间把未领取窗口吃掉；老行首次打点则把该锚点**固化**进 last_active_at（口径无缝衔接）。
      无未领取窗口时才前移 last_active_at ⇒ 在线期间持续刷新（在线时长天然不计入）。
    · 领取成功后把 last_active_at 前移到 now（@claim），避免冻结锚点拖住下一段离线计时。

  语义：在线 ⇒ last_active_at≈now ⇒ 窗口≈0（在线不计入）；真离线 ⇒ 冻结在最后一次请求时刻
  ⇒ 离线时长 = 真离线时长（不再依赖客户端 away/back 是否送达）。

  ★ 红线（一行未动）：offlineRewards()/offlineWindow()/offlineCapHours()/offlineRatePerHour()
    公式本体、OFFLINE_RATE_*/OFFLINE_CAP_HOURS_*/OFFLINE_STONE_RATIO/OFFLINE_MIN_MS 常量、
    月卡判定 hasMonthCard()、offline_claimed_until 幂等推进、/api/session/presence 本体、
    活动/师徒倍率、入账与钳制逻辑。

自证推演（可人工复核 · 与 gates 冻结断言互补）
--------------------------------------------------------------------------
  [断言 A · 症状①「在线被算进离线」]
    在线连续 3h（客户端每 10s 心跳存档 ⇒ 打点每 60s 刷新 last_active_at）后，玩家**在线**打开
    离线面板：report 读到的 last_active_at 距今 ≤ 60s ⇒ 窗口 ≤ 60s < OFFLINE_MIN_MS(5min)
    ⇒ claimable=false，在线 3h 一分钟都不计入。
    （改前：若某次 back 丢失，endMs=nowMs ⇒ 窗口可能达 3h，虚报可领。）

  [断言 B · 症状②「真离线被算少」]
    在线 3h（last_active_at≈T0 冻结于最后一次请求）→ 关浏览器（away 丢失，无任何请求）→
    真离线 1h → T1 回来（首个已鉴权请求）：
      · report 读到 a=T0（本次请求之前的快照）⇒ anchor=max(T0,cl)=T0，end=now=T1
        ⇒ 窗口 = 1h ⇒ 恰好真离线 1h（不是 4h、也不是 0）。
      · report 的 finish 打点：pending(1h ≥ 5min) ⇒ 冻结 a=T0、封口 last_resume_at=T1
        ⇒ 之后在线期间窗口保持 1h 不变（R-149 未领取窗口不被在线时长吃掉）。
      · claim ⇒ offline_claimed_until=T1，随后 last_active_at 前移到 now ⇒ 下一段离线重新起算。
    （改前：away 丢失 + 旧 last_resume_at 封口 ⇒ 新离线段恒落在 [旧锚点, 旧封口] 之外 ⇒ 少算。）

  [断言 C · 向后兼容]
    last_active_at 为 NULL 的老行：offlineAnchor 走原 R-021 分支 ⇒ 与改前**逐位一致**；
    首次打点时若存在未领取窗口，固化锚点后口径与 R-021 完全等价（窗口不变）。

CLI 契约（照 srv_patch_r165.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r173-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r173offline] 则 SKIP（直接返回 rc=0，不写盘）。
  退出码：0=成功/跳过；1=契约/门禁失败；2=意外异常（IO/写回）。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII；替换 expect=1；门禁全绿 + round-trip 正反双向自证后才原子写回。
"""

import argparse
import io
import os
import shutil
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记（写进替换新增的独立注释行；TS 源码 ⇒ 用 //）
MARK = "[r173offline]"

# ============================================================ 改动点（9 处）

# ── A. 建列：复用既有「列存在性快路径」回调 + safeAddColumn（不新增 PRAGMA 语句）──────────
A_OLD = (
    "          if (!rows.some((r: any) => r.name === 'last_resume_at')) safeAddColumn('saves', 'last_resume_at', 'ALTER TABLE saves ADD COLUMN last_resume_at INTEGER');\n"
    "        }\n"
    "      });\n"
)
A_NEW = (
    "          if (!rows.some((r: any) => r.name === 'last_resume_at')) safeAddColumn('saves', 'last_resume_at', 'ALTER TABLE saves ADD COLUMN last_resume_at INTEGER');\n"
    "          // ★ R-173（[r173offline]）：saves.last_active_at——服务端权威「最后活跃时刻」（ms，NULL=老行/未上报）。\n"
    "          //   已鉴权请求**响应结束后**按 60s/人节流打点（ylTouchActive）⇒ 在线期间持续刷新、\n"
    "          //   真离线后冻结在最后一次请求时刻。只服务 /api/offline/report|claim 的离线窗口锚点，\n"
    "          //   不参与任何收益公式。建列复用既有列存在性快路径 + safeAddColumn（容忍 duplicate\n"
    "          //   column name ⇒ 冷启动/重跑幂等），**不新增任何库表探测语句**。\n"
    "          if (!rows.some((r: any) => r.name === 'last_active_at')) safeAddColumn('saves', 'last_active_at', 'ALTER TABLE saves ADD COLUMN last_active_at INTEGER');\n"
    "        }\n"
    "      });\n"
)

# ── B. 打点挂点：authenticateToken 里 res 'finish'（响应之后 ⇒ report 读到更新前快照）──────
B_OLD = (
    "    req.user = { id: payload.id, username: payload.username };\n"
    "    next();\n"
)
B_NEW = (
    "    req.user = { id: payload.id, username: payload.username };\n"
    "    // [r173offline] R-173：服务端权威「最后活跃时刻」打点（响应结束后 · 60s/人节流）。\n"
    "    //   ★ 必须挂在 res 'finish'（响应之后）：/api/offline/report|claim 需读到**本次请求之前**\n"
    "    //     的 last_active_at 快照，否则锚点≈now ⇒ 离线窗口恒 0。\n"
    "    //   ★ fire-and-forget + 自吞异常：打点绝不影响鉴权与业务路径。\n"
    "    try { res.on('finish', () => { ylTouchActive(req.user.id); }); } catch (e) { /* 打点失败忽略 */ }\n"
    "    next();\n"
)

# ── C. 锚点函数：新增可选参数 lastActiveAtMs + 最高优先级分支（NULL ⇒ 回落原口径）─────────
C_OLD = (
    "  claimedUntilMs: unknown, nowMs: number\n"
    "): { anchorMs: number | null; endMs: number; source: string } {\n"
    "  const u = (updatedAtMs != null && Number.isFinite(updatedAtMs)) ? updatedAtMs : null;\n"
    "  const lRaw = Number(lastSeenAtMs);\n"
    "  const l = (lastSeenAtMs != null && Number.isFinite(lRaw) && lRaw > 0) ? lRaw : null;\n"
    "  const rRaw = Number(lastResumeAtMs);\n"
    "  const r = (lastResumeAtMs != null && Number.isFinite(rRaw) && rRaw > 0) ? rRaw : null;\n"
    "  const cl = (claimedUntilMs != null && Number.isFinite(Number(claimedUntilMs))) ? Number(claimedUntilMs) : 0;\n"
    "  if (l != null && l > cl) {\n"
)
C_NEW = (
    "  claimedUntilMs: unknown, nowMs: number, lastActiveAtMs?: unknown\n"
    "): { anchorMs: number | null; endMs: number; source: string } {\n"
    "  const u = (updatedAtMs != null && Number.isFinite(updatedAtMs)) ? updatedAtMs : null;\n"
    "  const lRaw = Number(lastSeenAtMs);\n"
    "  const l = (lastSeenAtMs != null && Number.isFinite(lRaw) && lRaw > 0) ? lRaw : null;\n"
    "  const rRaw = Number(lastResumeAtMs);\n"
    "  const r = (lastResumeAtMs != null && Number.isFinite(rRaw) && rRaw > 0) ? rRaw : null;\n"
    "  const cl = (claimedUntilMs != null && Number.isFinite(Number(claimedUntilMs))) ? Number(claimedUntilMs) : 0;\n"
    "  // ★ R-173（[r173offline]）：最高优先级 = 服务端权威 last_active_at。\n"
    "  //   在线期间由 ylTouchActive() 持续刷新 ⇒ 锚点≈now ⇒ 在线时长天然不计入；\n"
    "  //   真离线后冻结在最后一次请求时刻 ⇒ 离线时长 = 真离线时长（不依赖客户端 away/back 事件）。\n"
    "  //   lastActiveAtMs 为 NULL（老行 / 未打点）⇒ **逐位回落**下面的 R-021 口径（last_seen_at → updated_at）。\n"
    "  const aRaw = Number(lastActiveAtMs);\n"
    "  const a = (lastActiveAtMs != null && Number.isFinite(aRaw) && aRaw > 0) ? aRaw : null;\n"
    "  if (a != null) {\n"
    "    const end = (r != null && r > a) ? r : nowMs;\n"
    "    return { anchorMs: Math.max(a, cl), endMs: end, source: 'last_active_at' };\n"
    "  }\n"
    "  if (l != null && l > cl) {\n"
)

# ── D. 新逻辑：打点函数 + 节流常量（插在 presence 端点之前）──────────────────────────────
D_OLD = (
    "// POST /api/session/presence —— 客户端上报「离开 / 回来」（R-021 锚点事件源）\n"
)
D_NEW = (
    "// ─────────────────────────────────────────────────────────\n"
    "// ★ R-173（[r173offline]）离线时长精准测算：服务端权威「最后活跃时刻」\n"
    "//   症状①「在线也被算进离线」：锚点依赖客户端 away/back；back 一旦没送达（keepalive fetch\n"
    "//     被丢弃 / bfcache 恢复无 visibilitychange / 网络抖动被 .catch() 吞掉），offlineAnchor\n"
    "//     的 endMs 恒回落 nowMs ⇒ 玩家已回到线上，窗口却随在线时长继续增长。\n"
    "//   症状②「真离线被算少」：away 一旦没送达（崩溃 / 强杀 / 移动端后台回收 / beforeunload\n"
    "//     不触发），last_seen_at 停在旧值，叠加旧 last_resume_at 的封口 ⇒ 新的一段真离线永远\n"
    "//     落在 [旧锚点, 旧封口] 之外 ⇒ 少算。\n"
    "//   本环：新增 saves.last_active_at（服务端权威），已鉴权请求**响应结束后**节流打点。\n"
    "//     · 在线：last_active_at≈now ⇒ 窗口≈0 ⇒ 在线时长天然不计入（症状①）。\n"
    "//     · 离线：last_active_at 冻结在最后一次请求时刻 ⇒ 离线时长 = 真离线时长（症状②）。\n"
    "//   ★ 保留未领取窗口（R-149 精神）：若「本次请求之前」已存在 ≥ OFFLINE_MIN_MS 的未领取\n"
    "//     可结算窗口，则**冻结锚点**并封口（last_resume_at），避免在线期间把窗口吃掉；老行首次\n"
    "//     打点则把该锚点**固化**进 last_active_at（口径与 R-021 无缝衔接）。\n"
    "//   ★ 红线：offlineRewards()/offlineWindow()/offlineCapHours()/offlineRatePerHour() 公式本体、\n"
    "//     OFFLINE_* 常量、月卡判定、offline_claimed_until 幂等 —— 一行未动。\n"
    "// ─────────────────────────────────────────────────────────\n"
    "const YL_ACTIVE_TOUCH_MIN_MS = 60 * 1000; // 同一玩家落库节流：≥60s 才写一次（降写放大）\n"
    "const YL_ACTIVE_TOUCH = new Map<number, number>(); // userId -> 上次落库 ms（进程内，重启即空）\n"
    "// 服务端权威「最后活跃时刻」打点（fire-and-forget · 自吞异常 · 绝不阻塞/影响请求）\n"
    "function ylTouchActive(userId: number): void {\n"
    "  try {\n"
    "    const uid = Number(userId);\n"
    "    if (!Number.isFinite(uid) || uid <= 0) return;\n"
    "    const now = Date.now();\n"
    "    const last = YL_ACTIVE_TOUCH.get(uid);\n"
    "    if (last != null && now - last < YL_ACTIVE_TOUCH_MIN_MS) return; // 节流\n"
    "    YL_ACTIVE_TOUCH.set(uid, now);\n"
    "    if (YL_ACTIVE_TOUCH.size > 20000) { // 兜底防无界增长（无常驻定时器：机会式清理）\n"
    "      YL_ACTIVE_TOUCH.forEach((v: number, k: number) => { if (now - v > 10 * 60 * 1000) YL_ACTIVE_TOUCH.delete(k); });\n"
    "    }\n"
    "    void (async () => {\n"
    "      try {\n"
    "        const row: any = await dbGet('SELECT updated_at, last_active_at, last_seen_at, last_resume_at, offline_claimed_until FROM saves WHERE user_id = ?', [uid]);\n"
    "        if (!row) return;\n"
    "        const cl = (row.offline_claimed_until != null && Number.isFinite(Number(row.offline_claimed_until))) ? Number(row.offline_claimed_until) : 0;\n"
    "        const aRaw = Number(row.last_active_at);\n"
    "        const a = (row.last_active_at != null && Number.isFinite(aRaw) && aRaw > 0) ? aRaw : null;\n"
    "        // 用「本次请求之前」的口径判定是否存在未领取的可结算窗口（与 claim 同一门槛 OFFLINE_MIN_MS）\n"
    "        const anc = offlineAnchor(parseDbTimeMs(row.updated_at), row.last_seen_at, row.last_resume_at, cl, now, a);\n"
    "        const win = offlineWindow(anc.anchorMs, cl, anc.endMs);\n"
    "        const pending = !!(win && win.windowMs >= OFFLINE_MIN_MS);\n"
    "        if (pending) {\n"
    "          // 有未领取窗口：冻结锚点（不推进），并封口（玩家已回来 ⇒ 离线段不再随在线时长增长）\n"
    "          if (a == null && anc.anchorMs != null) {\n"
    "            await dbRun('UPDATE saves SET last_active_at = ? WHERE user_id = ? AND last_active_at IS NULL', [anc.anchorMs, uid]);\n"
    "          }\n"
    "          const anchorForResume = a != null ? a : anc.anchorMs;\n"
    "          const rRaw = Number(row.last_resume_at);\n"
    "          const r = (row.last_resume_at != null && Number.isFinite(rRaw) && rRaw > 0) ? rRaw : null;\n"
    "          if (r == null || (anchorForResume != null && r <= anchorForResume)) {\n"
    "            await dbRun('UPDATE saves SET last_resume_at = ? WHERE user_id = ?', [now, uid]);\n"
    "          }\n"
    "        } else {\n"
    "          // 无未领取窗口：锚点自由前移 ⇒ 在线期间持续刷新（离线后自然冻结在最后一次请求时刻）\n"
    "          await dbRun('UPDATE saves SET last_active_at = ? WHERE user_id = ?', [now, uid]);\n"
    "        }\n"
    "      } catch (e: any) { console.error('ylTouchActive error:', e?.message || e); }\n"
    "    })();\n"
    "  } catch { /* 打点绝不影响主路径 */ }\n"
    "}\n"
    "\n"
    "// POST /api/session/presence —— 客户端上报「离开 / 回来」（R-021 锚点事件源）\n"
)

# ── E1. report 读取新列 ──────────────────────────────────────────────────────────────
E1_OLD = (
    "  db.get('SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at FROM saves WHERE user_id = ?', [req.user.id], async (err: any, row: any) => {\n"
)
E1_NEW = (
    "  db.get('SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at, last_active_at FROM saves WHERE user_id = ?', [req.user.id], async (err: any, row: any) => {\n"
)

# ── E2. report 锚点接线（唯一：以 report 专属注释定界）────────────────────────────────
E2_OLD = (
    "    //   缺失 / 已领覆盖时逐位回落 updated_at。offlineWindow/offlineRewards 本体未动。\n"
    "    const ylAnc = offlineAnchor(parseDbTimeMs(row.updated_at), row.last_seen_at, row.last_resume_at, row.offline_claimed_until, nowMs);\n"
)
E2_NEW = (
    "    //   缺失 / 已领覆盖时逐位回落 updated_at。offlineWindow/offlineRewards 本体未动。\n"
    "    // ★ R-173（[r173offline]）：最高优先级传入服务端权威 last_active_at（NULL 时 offlineAnchor 自动回落原口径）。\n"
    "    const ylAnc = offlineAnchor(parseDbTimeMs(row.updated_at), row.last_seen_at, row.last_resume_at, row.offline_claimed_until, nowMs, row.last_active_at);\n"
)

# ── F1. claim 读取新列 ───────────────────────────────────────────────────────────────
F1_OLD = (
    "    const row = await dbGet('SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at FROM saves WHERE user_id = ?', [userId]);\n"
)
F1_NEW = (
    "    const row = await dbGet('SELECT save_data, updated_at, offline_claimed_until, month_card_until, last_seen_at, last_resume_at, last_active_at FROM saves WHERE user_id = ?', [userId]);\n"
)

# ── F2. claim 锚点接线（唯一：以 claim 专属注释定界）──────────────────────────────────
F2_OLD = (
    '    // ★ R-021：与 /api/offline/report 同一锚点口径（预览与领取必须一致，否则出现"看得到领不到"）\n'
    "    const ylAnc = offlineAnchor(parseDbTimeMs(row.updated_at), row.last_seen_at, row.last_resume_at, row.offline_claimed_until, nowMs);\n"
)
F2_NEW = (
    '    // ★ R-021：与 /api/offline/report 同一锚点口径（预览与领取必须一致，否则出现"看得到领不到"）\n'
    "    // ★ R-173（[r173offline]）：与 report 同口径传入 last_active_at（预览/领取必须一致）。\n"
    "    const ylAnc = offlineAnchor(parseDbTimeMs(row.updated_at), row.last_seen_at, row.last_resume_at, row.offline_claimed_until, nowMs, row.last_active_at);\n"
)

# ── G. claim 成功后把锚点前移过已领窗口（避免冻结锚点拖住下一段离线计时）────────────────
G_OLD = (
    "    if (!paid.ok || !applied) {\n"
    "      await dbRun('UPDATE saves SET offline_claimed_until = ? WHERE user_id = ?', [row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, userId]).catch(() => {});\n"
    "      return res.status(409).json({ error: paid.error === 'No save found' ? '请先进游戏创建角色' : '领取失败，请重试' });\n"
    "    }\n"
)
G_NEW = (
    "    if (!paid.ok || !applied) {\n"
    "      await dbRun('UPDATE saves SET offline_claimed_until = ? WHERE user_id = ?', [row.offline_claimed_until != null ? Number(row.offline_claimed_until) : null, userId]).catch(() => {});\n"
    "      return res.status(409).json({ error: paid.error === 'No save found' ? '请先进游戏创建角色' : '领取失败，请重试' });\n"
    "    }\n"
    "    // [r173offline] R-173：本段离线窗口已结算 ⇒ 锚点前移过已领时刻（否则冻结锚点会拖住下一段离线计时）。\n"
    "    await dbRun('UPDATE saves SET last_active_at = ? WHERE user_id = ?', [Date.now(), userId]).catch(() => {});\n"
)

EDITS = [
    ("R173 建列 last_active_at（复用既有快路径 · 不新增 PRAGMA）", A_OLD, A_NEW),
    ("R173 打点挂点（authenticateToken · res finish）", B_OLD, B_NEW),
    ("R173 锚点函数扩展（可选参数 + 最高优先级分支）", C_OLD, C_NEW),
    ("R173 打点函数 ylTouchActive + 节流常量", D_OLD, D_NEW),
    ("R173 report 读取新列", E1_OLD, E1_NEW),
    ("R173 report 锚点接线", E2_OLD, E2_NEW),
    ("R173 claim 读取新列", F1_OLD, F1_NEW),
    ("R173 claim 锚点接线", F2_OLD, F2_NEW),
    ("R173 claim 成功后锚点前移", G_OLD, G_NEW),
]

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("const safeAddColumn = (table: string, col: string, ddl: string) => {", "==", 1,
     "既有幂等建列器必须在位（本环复用，不自造；容忍 duplicate column name）"),
    ("function offlineAnchor(", "==", 1,
     "离线锚点纯函数必须在位（本环扩展，非重写）"),
    ("function offlineWindow(", "==", 1,
     "离线窗口纯函数必须在位（本环只读，一行未动）"),
    ("function offlineRewards(", "==", 1,
     "离线收益纯函数必须在位（本环只读，一行未动）"),
    ("const OFFLINE_MIN_MS = 5 * 60 * 1000;", "==", 1,
     "最小离线时长常量必须在位（本环只读）"),
    ("app.post('/api/session/presence', authenticateToken", "==", 1,
     "presence 端点必须在位（本环保留为兜底信号，不改本体）"),
    ("app.get('/api/offline/report', authenticateToken", "==", 1,
     "report 端点必须在位（本环接线新锚点）"),
    ("app.post('/api/offline/claim', authenticateToken", "==", 1,
     "claim 端点必须在位（本环接线新锚点 + 领取后前移）"),
    ("AND (offline_claimed_until IS NULL OR offline_claimed_until < ?)", "==", 1,
     "防双领守卫式推进必须在位（本环一行未动）"),
    ("[r165wudao]", ">=", 1,
     "R-165 环必须已应用（链序约束：本环排在其后）"),
    ("[r160cap]", ">=", 1,
     "R-160 环必须已应用（离线上限口径）"),
    ("[r149anchor]", ">=", 1,
     "R-149 环必须已应用（未领取窗口保留逻辑在位）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # 离线核心（本环公式 / 常量 / 签名 一行未动）
    "const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;",
    "const OFFLINE_RATE_MONTHCARD_PER_HOUR = 0.006;",
    "const OFFLINE_CAP_HOURS_BASE = 24;",
    "const OFFLINE_CAP_HOURS_PER_LEVEL = 1;",
    "const OFFLINE_CAP_HOURS_MONTHCARD_RATIO = 1.5;",
    "const OFFLINE_STONE_RATIO = 0.1;",
    "const OFFLINE_MIN_MS = 5 * 60 * 1000;",
    "function offlineAnchor(",
    "function offlineWindow(",
    "function offlineRewards(",
    "function offlineCapHours(",
    "function offlineRatePerHour(",
    "const expGain = enough ? Math.max(0, Math.min(Math.floor(slot * rate * effHours), slot - cur)) : 0;",
    "const stonesGain = Math.floor(expGain * OFFLINE_STONE_RATIO);",
    "const rawHours = Math.max(0, (Number(windowMs) || 0) / 3600000);",
    "const startMs = Math.max(Number(lastSaveMs), cl);",
    "app.get('/api/offline/report', authenticateToken",
    "app.post('/api/offline/claim', authenticateToken",
    "app.post('/api/session/presence', authenticateToken",
    "AND (offline_claimed_until IS NULL OR offline_claimed_until < ?)",
    # 工程红线（相对计数）
    "res.status(403",
    "setInterval(",
    "PRAGMA",
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out: str, base):
    """五元组 (label, needle, expect, op, note)；base = 冻结针脚在**基座**上的计数。"""
    g = [
        ("R173 幂等标记在位", MARK, 1, ">=", "本环已应用"),
        ("R173 新列 DDL", "'ALTER TABLE saves ADD COLUMN last_active_at INTEGER'", 1, "==", "safeAddColumn 幂等建列"),
        ("R173 新列存在性守卫（复用既有快路径）", "r.name === 'last_active_at'", 1, "==", "不新增 PRAGMA"),
        ("R173 report 读新列", ", last_seen_at, last_resume_at, last_active_at FROM saves WHERE user_id = ?', [req.user.id]", 1, "==", "report SELECT"),
        ("R173 claim 读新列", ", last_seen_at, last_resume_at, last_active_at FROM saves WHERE user_id = ?', [userId]", 1, "==", "claim SELECT"),
        ("R173 两处锚点接线", "row.offline_claimed_until, nowMs, row.last_active_at)", 2, "==", "report + claim 同口径"),
        ("R173 权威锚点分支", "source: 'last_active_at'", 1, "==", "last_active_at 最高优先级"),
        ("R173 锚点签名扩展（可选参数）", "claimedUntilMs: unknown, nowMs: number, lastActiveAtMs?: unknown", 1, "==", "向后兼容：NULL 回落原口径"),
        ("R173 打点函数唯一入口", "function ylTouchActive(", 1, "==", "唯一打点入口"),
        ("R173 打点挂点（响应结束后）", "res.on('finish', () => { ylTouchActive(req.user.id); })", 1, "==", "读到更新前快照"),
        ("R173 节流常量", "const YL_ACTIVE_TOUCH_MIN_MS = 60 * 1000;", 1, "==", "60s/人 降写放大"),
        ("R173 未领取窗口冻结分支", "const pending = !!(win && win.windowMs >= OFFLINE_MIN_MS);", 1, "==", "R-149 精神：冻结锚点"),
        ("R173 老行锚点固化", "UPDATE saves SET last_active_at = ? WHERE user_id = ? AND last_active_at IS NULL", 1, "==", "口径无缝衔接"),
        ("R173 领取后锚点前移", "UPDATE saves SET last_active_at = ? WHERE user_id = ?', [Date.now(), userId]", 1, "==", "避免冻结锚点拖住下一段"),
        # ── 冻结断言：公式本体 / 常量 / 签名 改动前后逐字一致 ──
        ("R173 冻结·offlineRewards 小时", "const rawHours = Math.max(0, (Number(windowMs) || 0) / 3600000);", 1, "==", "公式未动"),
        ("R173 冻结·offlineRewards 修为钳槽", "const expGain = enough ? Math.max(0, Math.min(Math.floor(slot * rate * effHours), slot - cur)) : 0;", 1, "==", "公式未动"),
        ("R173 冻结·offlineRewards 灵石比", "const stonesGain = Math.floor(expGain * OFFLINE_STONE_RATIO);", 1, "==", "公式未动"),
        ("R173 冻结·offlineWindow 起点", "const startMs = Math.max(Number(lastSaveMs), cl);", 1, "==", "公式未动"),
        ("R173 冻结·RATE_BASE", "const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;", 1, "==", "常量未动"),
        ("R173 冻结·RATE_MONTHCARD", "const OFFLINE_RATE_MONTHCARD_PER_HOUR = 0.006;", 1, "==", "常量未动"),
        ("R173 冻结·CAP_BASE", "const OFFLINE_CAP_HOURS_BASE = 24;", 1, "==", "常量未动"),
        ("R173 冻结·CAP_PER_LEVEL", "const OFFLINE_CAP_HOURS_PER_LEVEL = 1;", 1, "==", "常量未动"),
        ("R173 冻结·CAP_MONTHCARD_RATIO", "const OFFLINE_CAP_HOURS_MONTHCARD_RATIO = 1.5;", 1, "==", "常量未动"),
        ("R173 冻结·STONE_RATIO", "const OFFLINE_STONE_RATIO = 0.1;", 1, "==", "常量未动"),
        ("R173 冻结·MIN_MS", "const OFFLINE_MIN_MS = 5 * 60 * 1000;", 1, "==", "常量未动"),
        ("R173 冻结·offlineRewards 签名", "function offlineRewards(", 1, "==", "签名未动"),
        ("R173 冻结·offlineWindow 签名", "function offlineWindow(", 1, "==", "签名未动"),
        ("R173 冻结·offlineCapHours 签名", "function offlineCapHours(", 1, "==", "签名未动"),
        ("R173 冻结·offlineRatePerHour 签名", "function offlineRatePerHour(", 1, "==", "签名未动"),
        ("R173 冻结·offlineAnchor 仍在位", "function offlineAnchor(", 1, "==", "唯一锚点函数"),
        ("R173 冻结·presence 保留", "app.post('/api/session/presence', authenticateToken", 1, "==", "兜底信号保留"),
        ("R173 冻结·防双领幂等", "AND (offline_claimed_until IS NULL OR offline_claimed_until < ?)", 1, "==", "未动"),
        # ── 工程红线（相对计数）──
        ("R173 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403（客户端会强制登出）"),
        ("R173 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R173 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库（复用既有快路径）"),
        ("R173 红线·无 require", "require(", 0, "==", "ESM 不新增 require"),
    ]
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-173 离线时长精准测算（服务端权威最后活跃时刻）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：产物含标记则 SKIP（直接返回，不写盘，rc=0）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 2) 依赖（绝对在位）
    for needle, op, cnt, why in REQUIRES:
        n = src.count(needle)
        good = (n == cnt) if op == "==" else (n >= cnt)
        if not good:
            fail("依赖未满足（%r 出现 %d 次，期望 %s %d）：%s" % (needle[:80], n, op, cnt, why))

    # 3) 锚点计数（纯 ASCII，必须恰好 1）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:200]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线（每个针脚必须在基座真实存在，防针脚拼错导致「冻结」静默失效）
    base = {k: src.count(k) for k in BASE_NEEDLES}
    for k in BASE_NEEDLES:
        if base[k] <= 0:
            fail("冻结针脚在基座不存在（拼写错误？）：%r" % k[:90])

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁（五元组，op 支持 == / >=）
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-48s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证：正向重放一致 + 逆向还原后除改动点外字节零变化
    ref = src
    for name, old, new in EDITS:
        ref = ref.replace(old, new, 1)
    if out != ref:
        fail("round-trip(正向重构) mismatch")
    back = out
    for name, old, new in EDITS:
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    for name, old, new in EDITS:
        if out.count(new) != 1:
            fail("round-trip：新增块出现次数 != 1（%s）" % name)

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r173-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r173offline-", suffix=".tmp")
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
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:  # 意外异常（IO/写回）⇒ 退出码 2
        print("[ERROR] %s: %s" % (type(e).__name__, e))
        sys.exit(2)
