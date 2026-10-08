# -*- coding: utf-8 -*-
r"""
srv_patch_r186.py -- R-186 挂机收益「离线一整天仍为 0」修复（服务端环）

  ★ 环号说明：当前 srv/index_v28.ts 末环 = R-176 ⇒ 本环顺延 **R-186**。
    锚点全部落在 offlineAnchor() 的 last_active_at 分支 + ylTouchActive() 的封口条件，
    与其余任何锚区零交集。

台账原文（R-186，逐字）
--------------------------------------------------------------------------
  「挂机收益还是有大问题，我昨天一天没登录，今天上线挂机收益还是 0」

  ⇒ 用户明说「**还是**」= 上次已修过但没解决 ⇒ 本环先取证「上次为什么没生效」。

==============================================================================
一、上次改了什么（R-173，0.9.26，第 77 环 · patches/server/srv_patch_r173.py）
==============================================================================
  R-173 新增 saves.last_active_at（服务端权威「最后活跃时刻」）+ authenticateToken 里
  res.on('finish') 60s 节流打点（ylTouchActive），意图：在线期间锚点≈now（在线不计入），
  真离线后锚点冻结在最后一次请求时刻（离线时长=真离线时长，不依赖客户端 away/back）。
  ★ 已确认 R-173 **确已上线**：
      · 线上 /opt/yl/server/index.ts md5 = 5ea456429a9e60f8f7458781fa63131f
        == 本地 srv/index_v28.ts md5（1,008,329 B）
      · 线上库 saves 已含 last_active_at 列；文件内 [r173offline]×7、last_active_at×21。

==============================================================================
二、根因（R-173 为什么没解决）
==============================================================================
  缺陷在 offlineAnchor() 的 last_active_at 分支（srv/index_v28.ts:5556-5559）：

      if (a != null) {
        const end = (r != null && r > a) ? r : nowMs;          // ← a=last_active_at, r=last_resume_at
        return { anchorMs: Math.max(a, cl), endMs: end, source: 'last_active_at' };
      }

  · R-173 把客户端事件 last_resume_at(r) 当**窗口末端**（照抄 R-021 的 last_seen_at 分支形态）。
  · 但 r 是「**回来**」事件：客户端在**上一段会话结束前**最后一次 back（切回标签页/刷新）
    会把它写成 ≈ 最后一次服务端打点 a 之后 1~2 秒 —— 于是 r > a 且 r-a 只有 1~2 秒。
  · 结果窗口 = [max(a,cl), r] = r-a ≈ 1~2 秒 < OFFLINE_MIN_MS(5min) ⇒
        report 返回 hours=0 / expGain=0 / claimable=false ⇒ **面板恒 0**（即使离线一整天）。
  · 更致命：ylTouchActive()（:5608）用同一个 anc 判 pending：
        pending=false ⇒ 走 else 分支 `UPDATE saves SET last_active_at = now`（:5622）
        ⇒ 真离线一整天的窗口被**当场抹掉**（锚点被推进到「刚刚」），且此后每次上线都如此。

  ★ 线上真实行（只读 sqlite 实测，user 82）：
      updated_at=2026-10-06 14:58:34  last_active_at=1791298698612
      last_resume_at=1791298700044    (r-a = **+1432ms**)  offline_claimed_until=NULL
      读取时刻 now=1791339776898 ⇒ 已离线 **11.41h**，但 r-a=1.4s
      ⇒ 现网 report 必为 windowMs=1432 / hours=0 / claimable=false（见 §四 harness 实测）。

  ★ 天然对照（同一时刻的线上两行）：
      user 81：last_resume_at=NULL  ⇒ 走 r==null ⇒ end=now ⇒ 窗口 = now-a ≈ 12h（**正确**）
      user 82：last_resume_at=a+1.4s ⇒ end=r     ⇒ 窗口 = 1.4s（**恒 0**）
    同一份代码、同一离线时长，仅因「上一段会话尾部有没有 back 事件」而一个对一个错
    ⇒ 精确定位到 last_active_at 分支的 end 取值，而非收益公式 / 常量 / 表结构。

==============================================================================
三、改法（2 处，均在服务端；客户端零改动）
==============================================================================
  [1] offlineAnchor() · last_active_at 分支：仅当 r 相对 a **至少晚 OFFLINE_MIN_MS**
      （确属「本次离线结束后的首次回归时刻」）才用 r 封口；否则 endMs 回落 nowMs。
      · 判据可靠：真回归 r 必然 ≥ a+gap（gap≥OFFLINE_MIN_MS 才叫离线）；
        遗留 r 恒 ≤ a+~60s（打点节流 60s，且 r 是请求事件 ⇒ 不可能晚于最后一次请求太多）
        < OFFLINE_MIN_MS。两者互斥，阈值 OFFLINE_MIN_MS 恰好分开。
  [2] ylTouchActive() · 封口条件：旧条件 `r <= anchorForResume` 放过了「r 略晚于锚点」的遗留 r
      ⇒ 永不落封口。改为 `(r - anchorForResume) < OFFLINE_MIN_MS`（含 r<a）即落一次 now。
      落完后 r-a 即为真实离线时长 ≥ 阈值 ⇒ 后续请求不再重落（每段离线只落一次）。

  修后语义：
    · 用户离线一整天后首个请求 ⇒ 窗口 = now - last_active_at ≈ 真离线时长 ⇒ 可领（面板非 0）；
      同时 ylTouchActive 冻结锚点并落一次封口 ⇒ 在线期间窗口不随在线时长增长（保留 R-149 精神）。
    · 在线用户 ⇒ 窗口 < 5min ⇒ pending=false ⇒ 锚点照旧前移（在线不计入）。
    · 老行（last_active_at IS NULL）⇒ 逐位回落 R-021 口径，一行未动。

  ★ 红线（一行未动）：offlineRewards()/offlineWindow()/offlineCapHours()/offlineRatePerHour()
    公式本体、OFFLINE_RATE_*/OFFLINE_CAP_HOURS_*/OFFLINE_STONE_RATIO/OFFLINE_MIN_MS 常量、
    月卡判定 hasMonthCard()、offline_claimed_until 幂等推进、/api/session/presence 本体、
    /api/offline/report|claim 端点、活动/师徒倍率、入账与钳制逻辑。

==============================================================================
四、自证推演（本机 node 直跑 harness，逐字复制线上纯函数）
==============================================================================
  [场景1 · 线上真实行 user 82，离线 11.41h，r-a=1432ms]
     现网 report : windowMs=1432   hours=0     claimable=false   ← 用户看到的「0」
     R-186 report: windowMs=41078286 hours=11.41 claimable=true
  [场景2 · 复刻 R-186 原文时间线（离开时 r 比 a 晚 1s，离线 20.4h）]
     现网：首个请求 pending=false ⇒ last_active_at 被推进 now ⇒ 回来瞬间 report hours=0；
           在线 23 分钟后 last_active_at=「刚刚」、report 仍 0（整段离线被抹掉）。
     R-186：首个请求 pending=true（window=20.43h）⇒ 冻结锚点 + 落封口 ⇒
           回来瞬间 report hours=20.43 claimable=true；在线 23 分钟后窗口**冻结不变** 20.43h。

CLI 契约（照 srv_patch_r173.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r186-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r186offline] 则 SKIP（直接返回 rc=0，不写盘）。
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
MARK = "[r186offline]"

# ============================================================ 改动点（2 处）

# ── A. offlineAnchor() · last_active_at 分支：封口条件加 OFFLINE_MIN_MS 门槛 ─────────────
A_OLD = (
    "  if (a != null) {\n"
    "    const end = (r != null && r > a) ? r : nowMs;\n"
    "    return { anchorMs: Math.max(a, cl), endMs: end, source: 'last_active_at' };\n"
    "  }\n"
)
A_NEW = (
    "  if (a != null) {\n"
    "    // \u2605 R-186\uff08[r186offline]\uff09\uff1aR-173 \u7528 last_resume_at(r) \u5f53\u7a97\u53e3\u672b\u7aef\u2014\u2014\u4f46 r \u5e38\u662f**\u4e0a\u4e00\u6bb5\u4f1a\u8bdd**\n"
    "    //   \u9057\u7559\u7684\u300c\u56de\u6765\u300d\u65f6\u523b\uff08\u5ba2\u6237\u7aef\u6700\u540e\u4e00\u6b21 back \u53ea\u6bd4\u6700\u540e\u4e00\u6b21\u670d\u52a1\u7aef\u6253\u70b9 a \u665a 1~2 \u79d2\uff09\u3002\n"
    "    //   \u6b64\u65f6\u7a97\u53e3 = r-a \u2248 1~2s < OFFLINE_MIN_MS \u21d2 \u9762\u677f\u6052 0\uff08R-173 \u4e0a\u7ebf\u540e\u300c\u6302\u673a\u6536\u76ca\u8fd8\u662f 0\u300d\u6839\u56e0\uff09\u3002\n"
    "    //   \u4ec5\u5f53 r \u76f8\u5bf9 a \u81f3\u5c11\u665a OFFLINE_MIN_MS\uff08\u786e\u5c5e\u672c\u6b21\u79bb\u7ebf\u7ed3\u675f\u540e\u7684\u9996\u6b21\u56de\u5f52\u65f6\u523b\uff09\u624d\u7528\u5b83\u5c01\u53e3\uff1b\n"
    "    //   \u5426\u5219\u7a97\u53e3\u672b\u7aef\u56de\u843d nowMs\uff08\u7528\u6237\u4ecd\u5728\u7ebf/\u521a\u56de\u6765 \u21d2 now \u5373\u6b63\u786e\u672b\u7aef\uff09\u3002\n"
    "    const end = (r != null && r > a && (r - a) >= OFFLINE_MIN_MS) ? r : nowMs;\n"
    "    return { anchorMs: Math.max(a, cl), endMs: end, source: 'last_active_at' };\n"
    "  }\n"
)

# ── B. ylTouchActive() · 封口条件：放过「r 略晚于锚点」的遗留 r ⇒ 改为 < OFFLINE_MIN_MS 即落 ──
B_OLD = (
    "          if (r == null || (anchorForResume != null && r <= anchorForResume)) {\n"
    "            await dbRun('UPDATE saves SET last_resume_at = ? WHERE user_id = ?', [now, uid]);\n"
    "          }\n"
)
B_NEW = (
    "          // \u2605 R-186\uff08[r186offline]\uff09\uff1a\u65e7\u6761\u4ef6\u53ea\u8ba4\u300cr \u65e9\u4e8e\u951a\u70b9\u300d\u624d\u843d\u5c01\u53e3\uff1b\u4f46\u4e0a\u4e00\u6bb5\u4f1a\u8bdd\u9057\u7559\u7684 r\n"
    "          //   \u5e38**\u7565\u665a\u4e8e**\u951a\u70b9\uff08r-a \u4ec5 1~2s\uff09\u21d2 \u65e7\u6761\u4ef6\u5224\u4e3a\u300c\u5df2\u6709\u6709\u6548\u5c01\u53e3\u300d\u800c\u4e0d\u5199 \u21d2 r \u6c38\u8fdc\u505c\u5728\n"
    "          //   \u65e7\u503c \u21d2 \u7a97\u53e3\u6052 = r-a \u2248 0\uff0c\u4e14 pending \u5224\u5047 \u21d2 \u951a\u70b9\u88ab\u63a8\u8fdb now \u21d2 \u6574\u6bb5\u79bb\u7ebf\u88ab\u62b9\u6389\u3002\n"
    "          //   \u6539\u4e3a\uff1ar \u76f8\u5bf9\u951a\u70b9\u4e0d\u8db3 OFFLINE_MIN_MS\uff08\u542b r<a\uff09\u5373\u89c6\u4e3a\u300c\u672c\u6bb5\u5c1a\u65e0\u6709\u6548\u5c01\u53e3\u300d\u21d2 \u7528 now \u843d\u4e00\u6b21\u3002\n"
    "          //   \uff08\u6bcf\u6bb5\u79bb\u7ebf\u53ea\u843d\u4e00\u6b21\uff1a\u843d\u5b8c\u540e r-a \u5373\u4e3a\u771f\u5b9e\u79bb\u7ebf\u65f6\u957f \u2265 \u9608\u503c \u21d2 \u540e\u7eed\u8bf7\u6c42\u4e0d\u518d\u91cd\u843d\u3002\uff09\n"
    "          if (r == null || (anchorForResume != null && (r - anchorForResume) < OFFLINE_MIN_MS)) {\n"
    "            await dbRun('UPDATE saves SET last_resume_at = ? WHERE user_id = ?', [now, uid]);\n"
    "          }\n"
)

EDITS = [
    ("R186 offlineAnchor · last_active_at 分支封口门槛", A_OLD, A_NEW),
    ("R186 ylTouchActive · 封口条件改 MIN 门槛", B_OLD, B_NEW),
]

# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("[r173offline]", ">=", 1,
     "R-173 环必须已应用（链序约束：本环修其 last_active_at 分支）"),
    ("function offlineAnchor(", "==", 1,
     "离线锚点纯函数必须在位（本环只改 last_active_at 分支 end 取值）"),
    ("function offlineWindow(", "==", 1,
     "离线窗口纯函数必须在位（本环一行未动）"),
    ("function offlineRewards(", "==", 1,
     "离线收益纯函数必须在位（本环一行未动）"),
    ("const OFFLINE_MIN_MS = 5 * 60 * 1000;", "==", 1,
     "最小离线时长常量必须在位（本环以它为封口门槛）"),
    ("function ylTouchActive(", "==", 1,
     "R-173 打点函数必须在位（本环改其封口条件）"),
    ("const YL_ACTIVE_TOUCH_MIN_MS = 60 * 1000;", "==", 1,
     "R-173 打点节流常量必须在位（本环一行未动）"),
    ("app.get('/api/offline/report', authenticateToken", "==", 1,
     "report 端点必须在位（本环只读其调用链）"),
    ("app.post('/api/offline/claim', authenticateToken", "==", 1,
     "claim 端点必须在位（本环只读其调用链）"),
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
    "res.on('finish', () => { ylTouchActive(req.user.id); })",
    "function ylTouchActive(",
    "const YL_ACTIVE_TOUCH_MIN_MS = 60 * 1000;",
    "source: 'last_active_at'",
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
        ("R186 幂等标记在位", MARK, 1, ">=", "本环已应用"),
        # ── 新形态在位 ──
        ("R186 权威分支新封口条件", "const end = (r != null && r > a && (r - a) >= OFFLINE_MIN_MS) ? r : nowMs;", 1, "==", "end 只在真回归时用 r"),
        ("R186 打点封口新条件", "(r - anchorForResume) < OFFLINE_MIN_MS", 1, "==", "遗留 r 也落一次封口"),
        # ── 旧形态清零 ──
        ("R186 旧形态·权威分支封口清零", "const end = (r != null && r > a) ? r : nowMs;", 0, "==", "旧 end 取值必须消失"),
        ("R186 旧形态·打点封口条件清零", "(anchorForResume != null && r <= anchorForResume)", 0, "==", "旧封口条件必须消失"),
        # ── 冻结断言：公式本体 / 常量 / 签名 改动前后逐字一致 ──
        ("R186 冻结·offlineRewards 小时", "const rawHours = Math.max(0, (Number(windowMs) || 0) / 3600000);", 1, "==", "公式未动"),
        ("R186 冻结·offlineRewards 修为钳槽", "const expGain = enough ? Math.max(0, Math.min(Math.floor(slot * rate * effHours), slot - cur)) : 0;", 1, "==", "公式未动"),
        ("R186 冻结·offlineRewards 灵石比", "const stonesGain = Math.floor(expGain * OFFLINE_STONE_RATIO);", 1, "==", "公式未动"),
        ("R186 冻结·offlineWindow 起点", "const startMs = Math.max(Number(lastSaveMs), cl);", 1, "==", "公式未动"),
        ("R186 冻结·RATE_BASE", "const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;", 1, "==", "常量未动"),
        ("R186 冻结·RATE_MONTHCARD", "const OFFLINE_RATE_MONTHCARD_PER_HOUR = 0.006;", 1, "==", "常量未动"),
        ("R186 冻结·CAP_BASE", "const OFFLINE_CAP_HOURS_BASE = 24;", 1, "==", "常量未动"),
        ("R186 冻结·CAP_PER_LEVEL", "const OFFLINE_CAP_HOURS_PER_LEVEL = 1;", 1, "==", "常量未动"),
        ("R186 冻结·CAP_MONTHCARD_RATIO", "const OFFLINE_CAP_HOURS_MONTHCARD_RATIO = 1.5;", 1, "==", "常量未动"),
        ("R186 冻结·STONE_RATIO", "const OFFLINE_STONE_RATIO = 0.1;", 1, "==", "常量未动"),
        ("R186 冻结·MIN_MS", "const OFFLINE_MIN_MS = 5 * 60 * 1000;", 1, "==", "常量未动"),
        ("R186 冻结·offlineRewards 签名", "function offlineRewards(", 1, "==", "签名未动"),
        ("R186 冻结·offlineWindow 签名", "function offlineWindow(", 1, "==", "签名未动"),
        ("R186 冻结·offlineCapHours 签名", "function offlineCapHours(", 1, "==", "签名未动"),
        ("R186 冻结·offlineRatePerHour 签名", "function offlineRatePerHour(", 1, "==", "签名未动"),
        ("R186 冻结·offlineAnchor 仍在位", "function offlineAnchor(", 1, "==", "唯一锚点函数"),
        ("R186 冻结·last_active_at 来源标记", "source: 'last_active_at'", 1, "==", "分支仍在位"),
        ("R186 冻结·presence 保留", "app.post('/api/session/presence', authenticateToken", 1, "==", "兜底信号保留"),
        ("R186 冻结·防双领幂等", "AND (offline_claimed_until IS NULL OR offline_claimed_until < ?)", 1, "==", "未动"),
        ("R186 冻结·打点挂点", "res.on('finish', () => { ylTouchActive(req.user.id); })", 1, "==", "未动"),
        ("R186 冻结·打点节流常量", "const YL_ACTIVE_TOUCH_MIN_MS = 60 * 1000;", 1, "==", "未动"),
        # ── 工程红线（相对计数）──
        ("R186 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403（客户端会强制登出）"),
        ("R186 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R186 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        ("R186 红线·无 require", "require(", 0, "==", "ESM 不新增 require"),
    ]
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-186 挂机收益离线恒 0 修复（last_active_at 封口门槛）")
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
    bak = "%s.bak-r186-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r186offline-", suffix=".tmp")
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
