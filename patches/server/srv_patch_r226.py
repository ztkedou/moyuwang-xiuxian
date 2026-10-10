# -*- coding: utf-8 -*-
r"""
srv_patch_r226.py -- R-226 服务端离线收益吃难度倍率（服务端第 91 环）

==============================================================================
零、需求原文（R-225/R-226，唯一依据）
==============================================================================
  「0.9.46（R-217）给难度加了收益倍率，客户端在 19 个「获取」入账点外包了
    YlxwDiffGain(x,"expMul"/"stoneMul")。但服务端结算的离线收益走 loadGame 直接 t({player})，
    绕过客户端全部入账点 ⇒ 离线收益不吃倍率。用户选困难（+100%）就是想要更高收益，
    离线不享受属缺口。让服务端离线收益也吃难度倍率。」

==============================================================================
一、改前取证（_chainstage/s90.r215.ts 字符级实测）
==============================================================================
  【A. 离线收益结算点】服务端共两处玩家可见的离线收益端点（客户端伴生页 /yl/apps/offline/ 调用）：
    · GET  /api/offline/report  @13225 —— 明细预览（不落账），产 expGain/stonesGain 供 UI 显示；
    · POST /api/offline/claim   @13281 —— 领取入档（updatePlayerSave 直改 player.exp/spiritStones）。
    两者共享同一套纯函数，公式逐项如下（原公式，本环不动）：
      nr        = normalizeRealm(player)                       // {realmIndex, realmLevel, exp, maxExp}
      capHours  = offlineCapHours(ri, lv, hasMonth)            // 24h(练气1层)+(总层-1)*1h；月卡 ×1.5
      rate      = offlineRatePerHour(hasMonth)                 // 无月卡 0.0048 / 月卡 0.006（当层修为槽/小时）
      win       = offlineWindow(offlineAnchor(...), claimedUntil, endMs)  // 离线窗口（起算锚点）
      rw        = offlineRewards(maxExp, exp, windowMs, capHours, rate)
                    修为 expGain  = floor(slot * rate * effHours)，再钳槽内 min(…, slot-cur)
                    灵石 stonesGain = floor(expGain * OFFLINE_STONE_RATIO=0.1)
      入账     shownExpGain    = min(actApplyGain(rw.expGain,    evMult.expMult   * mnG.expMult),   maxExp-exp)
               shownStonesGain =     actApplyGain(rw.stonesGain, evMult.stonesMult * mnG.stonesMult)
      （claim 侧 gExp/gStones 同口径，evMult=限时活动倍率、mnG=师徒加成；本环在其后**再乘**难度倍率）

  【B. 难度来源的实测结论 —— 本环核心】★ 服务端**已经能**拿到难度，无需任何新增上报通道：
    (1) 客户端 pushSave（bundle @716359）在发存档前**注入** settings：
          async pushSave(t){ try{ t.dungeonGate=window.__ylDg||null, t.settings=Be.getState().settings }catch(l){} … }
        其中 Be.getState().settings.difficulty 即玩家难度（默认 'normal'，见 Mg={…,difficulty:"normal"}）。
    (2) 服务端 POST /api/save（@2451 `const saveData = req.body;` → @2462 `JSON.stringify(saveData)`）
        **整包原样落库** saves.save_data；isValidSavePayload 只校验 player.name/realm，**不剔除 settings**。
    (3) 客户端 fetchSave（@716175）读回并回填：r.settings && setSettings({...Cw(),...r.settings})
        —— 说明 settings 本就往返于服务端存档，是**既有数据通路**。
    (4) 真库实证（localtest/_srvprobe/database.sqlite，23 档）：16/23 档 save_data 含 settings，
        其中 5 档 settings.difficulty='normal'（其余为 settings:{} 空对象，缺 difficulty）。
        ⇒ 服务端从 row.save_data 读 settings.difficulty 是**成立且已在用**的数据来源。
    ⇒ **结论：难度来源 = saves.save_data.settings.difficulty。可直接实现，客户端零改动。**
    （若难度缺失/非法/未知，按客户端 YlxwDiffMul 的兜底语义回落 normal=1.5，与客户端默认难度一致。）

  【C. 口径（与客户端 Qr.difficulty 逐字一致）】
      easy:   expMul=1,   stoneMul=1
      normal: expMul=1.5, stoneMul=1.5
      hard:   expMul=2,   stoneMul=2
      客户端 YlxwDiffMul 兜底 = Qr.difficulty.normal ⇒ 本环缺失/未知一律回落 normal(1.5)。

==============================================================================
二、改动点（6 处；锚点全部纯 ASCII 且唯一 count==1）
==============================================================================
  E1  MARK+纯函数注入：在 offlineRewards() 之后插入 /*[r226offline]*/ 说明块与
      offlineDifficultyMuls(saveDataRaw) 纯函数（读 save_data.settings.difficulty → {expMul,stoneMul}）。
  E2  GET /report：新增 const dfM，修为预览乘 dfM.expMul（乘进既有 evMult*mnG 乘积）。
  E3  GET /report：灵石预览乘 dfM.stoneMul。
  E4  POST /claim：新增 const dfM（与 report 同源 row.save_data，保证"预览=领取"一致）。
  E5  POST /claim：入档修为乘 dfM.expMul。
  E6  POST /claim：入档灵石乘 dfM.stoneMul。

  ★ 「只放大获取」的证据：改动仅把难度倍率**乘进既有的 actApplyGain(base, mult) 的 mult 参数**，
    该函数签名 = max(0, floor(floor(base) * (Number(mult)||1)))，只作用于传入的收益基数 base；
    未新增任何扣减/消耗路径；capHours/rate/STONE_RATIO/MIN_MS/锚点 一行未动（见门禁冻结项）。
  ★ 范围边界：服务端另有 calcOfflineGainV2()（@1994，POST /api/save 的 E2「离线重算封顶」）
    —— 它是防改档的**上限**（ceiling），非玩家可见的离线收益发放；且 offline/claim 走
    updatePlayerSave 直写、不经 E2 结算，故本环**不碰** calcOfflineGainV2（符合"上限不变"）。

==============================================================================
三、客户端需要做什么
==============================================================================
  **无需任何客户端改动**。客户端 pushSave 已在存档包里带 settings.difficulty（既有行为），
  服务端离线结算据此读难度即可。客户端环无需另立。

契约
--------------------------------------------------------------------------
  CLI：--src <path>（默认 _chainstage/s90.r215.ts；就地原子写回，写回前落 .bak-r226-<时间戳>）
       / --check / --selftest（只验不写） / --sim（跑难度×离线时长模拟表，不写）。
  幂等：产物含 /*[r226offline]*/ ⇒ SKIP（不写盘，rc=3）。
  退出码：0=成功/自检通过；1=门禁/往返失败；2=前置断言（依赖/锚点/冻结）不符或 IO 异常；3=幂等跳过。
  · 锚点唯一（count==1，纯 ASCII）；round-trip 正反双向自证后才原子写回。
  · 工程红线：不新增 require(（ESM 直跑）/ 不新增 res.status(403 / 不动 PRAGMA / 不新增 setInterval(。
  · 自证：--check rc=0 → 临时副本写回 → node --experimental-strip-types --check rc=0 → 复跑 SKIP rc=3
          → --sim 打印 easy/normal/hard 改前改后对照表。
"""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.join("_chainstage", "s90.r215.ts")

# 幂等标记（TS 源码合法注释）
MARK = "/*[r226offline]*/"

# ============================================================ 新增纯函数（E1 注入体）

HELPER = (
    "// " + MARK + " R-226（服务端第 91 环）：离线收益吃难度倍率。\n"
    "//   难度来源：存档整包 save_data.settings.difficulty —— 客户端 pushSave 注入 t.settings（含 difficulty），\n"
    "//   服务端 POST /api/save 整包原样落库（save_data = JSON.stringify(req.body)），客户端 fetchSave 读回 r.settings。\n"
    "//   三方同源 ⇒ 服务端零新增上报通道、零客户端改动。\n"
    "//   口径与客户端 YlxwDiffMul 完全一致：easy=1.0 / normal=1.5 / hard=2.0；缺失/非法/未知 → normal(1.5)。\n"
    "//   只放大「获取」侧（修为 expGain / 灵石 stonesGain）；上限 capHours、速率 ratePerHour、灵石比例、\n"
    "//   月卡、锚点、起算门槛一律不动（只把倍率乘进既有 evMult*mnG 乘积）。\n"
    "function offlineDifficultyMuls(saveDataRaw: unknown): { expMul: number; stoneMul: number } {\n"
    "  let d: any = undefined;\n"
    "  try {\n"
    "    const sd: any = typeof saveDataRaw === 'string' ? JSON.parse(saveDataRaw) : saveDataRaw;\n"
    "    d = sd && sd.settings ? sd.settings.difficulty : undefined;\n"
    "  } catch { d = undefined; }\n"
    "  if (d === 'easy') return { expMul: 1, stoneMul: 1 };\n"
    "  if (d === 'hard') return { expMul: 2, stoneMul: 2 };\n"
    "  return { expMul: 1.5, stoneMul: 1.5 };\n"
    "}\n"
)

# ============================================================ 改动点（6 处）

# ── [1] MARK + 纯函数注入：offlineRewards() 尾（ASCII 唯一锚点）后 ──────────────────
E1_OLD = "    effectiveMs: Math.round(effHours * 3600000),\n  };\n}\n"
E1_NEW = E1_OLD + "\n" + HELPER + "\n"

# ── [2] GET /report：新增 dfM + 修为预览乘 expMul ──────────────────────────────────
E2_OLD = ("    const shownExpGain = rw ? Math.min(actApplyGain(rw.expGain, "
          "evMult.expMult * mnG.expMult), Math.max(0, nr.maxExp - nr.exp)) : 0;")
E2_NEW = ("    const dfM = offlineDifficultyMuls(row.save_data); // [r226offline] 难度倍率（存档 settings.difficulty）\n"
          + E2_OLD.replace("evMult.expMult * mnG.expMult)",
                           "evMult.expMult * mnG.expMult * dfM.expMul)"))

# ── [3] GET /report：灵石预览乘 stoneMul ───────────────────────────────────────────
E3_OLD = "    const shownStonesGain = rw ? actApplyGain(rw.stonesGain, evMult.stonesMult * mnG.stonesMult) : 0;"
E3_NEW = ("    const shownStonesGain = rw ? actApplyGain(rw.stonesGain, "
          "evMult.stonesMult * mnG.stonesMult * dfM.stoneMul) : 0;")

# ── [4] POST /claim：新增 dfM（与 report 同源 row.save_data）──────────────────────
E4_OLD = "    const claimedUntil = win.startMs + rw.effectiveMs;"
E4_NEW = ("    const dfM = offlineDifficultyMuls(row.save_data); // [r226offline] 难度倍率（存档 settings.difficulty）\n"
          + E4_OLD)

# ── [5] POST /claim：入档修为乘 expMul ─────────────────────────────────────────────
E5_OLD = ("      const gExp = Math.min(actApplyGain(r.expGain, "
          "evMult.expMult * mnG.expMult), Math.max(0, nrNow.maxExp - nrNow.exp));")
E5_NEW = ("      const gExp = Math.min(actApplyGain(r.expGain, "
          "evMult.expMult * mnG.expMult * dfM.expMul), Math.max(0, nrNow.maxExp - nrNow.exp));")

# ── [6] POST /claim：入档灵石乘 stoneMul ───────────────────────────────────────────
E6_OLD = "      const gStones = actApplyGain(r.stonesGain, evMult.stonesMult * mnG.stonesMult);"
E6_NEW = ("      const gStones = actApplyGain(r.stonesGain, "
          "evMult.stonesMult * mnG.stonesMult * dfM.stoneMul);")

EDITS = [
    ("R226 MARK+纯函数注入", E1_OLD, E1_NEW),
    ("R226 report 修为乘 expMul", E2_OLD, E2_NEW),
    ("R226 report 灵石乘 stoneMul", E3_OLD, E3_NEW),
    ("R226 claim 新增 dfM", E4_OLD, E4_NEW),
    ("R226 claim 修为乘 expMul", E5_OLD, E5_NEW),
    ("R226 claim 灵石乘 stoneMul", E6_OLD, E6_NEW),
]

# 供门禁引用的"新行"（不含 dfM 声明行，避免与 E4 撞串）
E2_NEW_EXPLINE = E2_NEW.split("\n", 1)[1]

# ============================================================ 依赖（绝对在位，锚点唯一）

REQUIRES = [
    (E1_OLD, "==", 1, "offlineRewards 尾部（本环在其后插 MARK+纯函数）"),
    (E2_OLD, "==", 1, "report 修为预览行必须在位"),
    (E3_OLD, "==", 1, "report 灵石预览行必须在位"),
    (E4_OLD, "==", 1, "claim claimedUntil 行必须在位"),
    (E5_OLD, "==", 1, "claim 入档修为行必须在位"),
    (E6_OLD, "==", 1, "claim 入档灵石行必须在位"),
    ("function offlineRewards(", "==", 1, "离线收益公式必须在位（本环不动）"),
    ("function offlineCapHours(", "==", 1, "上限公式必须在位（本环不动）"),
    ("function offlineRatePerHour(", "==", 1, "速率公式必须在位（本环不动）"),
    ("function offlineWindow(", "==", 1, "离线窗口公式必须在位（本环不动）"),
    ("function calcOfflineGainV2(", "==", 1, "E2 封顶公式必须在位（本环不动）"),
    ("app.get('/api/offline/report'", "==", 1, "report 端点必须在位"),
    ("app.post('/api/offline/claim'", "==", 1, "claim 端点必须在位"),
    ("const OFFLINE_STONE_RATIO = 0.1;", "==", 1, "灵石比例常量必须在位（本环不动）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    "function offlineRewards(",
    "function offlineCapHours(",
    "function offlineRatePerHour(",
    "function offlineWindow(",
    "function calcOfflineGainV2(",
    "const OFFLINE_CAP_HOURS_BASE = 24;",
    "const OFFLINE_STONE_RATIO = 0.1;",
    "const OFFLINE_MIN_MS = 5 * 60 * 1000;",
    # 工程红线（相对计数）
    "res.status(403",
    "setInterval(",
    "PRAGMA",
    "require(",
]


def fail(msg: str) -> None:
    print("[FAIL] " + msg)
    sys.exit(1)


def gates(out: str, base):
    """五元组 (label, needle, expect, op, note)；base = 冻结针脚在**基座**上的计数。"""
    return [
        ("R226 幂等标记唯一", MARK, 1, "==", "本环已应用"),
        ("R226 纯函数在位", "function offlineDifficultyMuls(saveDataRaw: unknown): { expMul: number; stoneMul: number } {", 1, "==", "新增纯函数"),
        ("R226 easy=1.0", "if (d === 'easy') return { expMul: 1, stoneMul: 1 };", 1, "==", "easy 口径"),
        ("R226 hard=2.0", "if (d === 'hard') return { expMul: 2, stoneMul: 2 };", 1, "==", "hard 口径"),
        ("R226 normal 兜底=1.5", "return { expMul: 1.5, stoneMul: 1.5 };", 1, "==", "normal/缺失/未知"),
        ("R226 dfM 调用=2处", "const dfM = offlineDifficultyMuls(row.save_data);", 2, "==", "report+claim 同源"),
        # ── 接入在位（新行，各 1 次）──
        ("R226 report 修为接入", E2_NEW_EXPLINE, 1, "==", "expMul 已乘"),
        ("R226 report 灵石接入", E3_NEW, 1, "==", "stoneMul 已乘"),
        ("R226 claim 修为接入", E5_NEW, 1, "==", "expMul 已乘"),
        ("R226 claim 灵石接入", E6_NEW, 1, "==", "stoneMul 已乘"),
        # ── 旧行清零（各 0 次）──
        ("R226 report 旧修为行清零", E2_OLD, 0, "==", "已替换"),
        ("R226 report 旧灵石行清零", E3_OLD, 0, "==", "已替换"),
        ("R226 claim 旧修为行清零", E5_OLD, 0, "==", "已替换"),
        ("R226 claim 旧灵石行清零", E6_OLD, 0, "==", "已替换"),
        # ── 冻结：上限/速率/比例/门槛 逐字未动 ──
        ("R226 冻结·CAP_HOURS_BASE=24", "const OFFLINE_CAP_HOURS_BASE = 24;", 1, "==", "未动"),
        ("R226 冻结·CAP_HOURS_PER_LEVEL=1", "const OFFLINE_CAP_HOURS_PER_LEVEL = 1;", 1, "==", "未动"),
        ("R226 冻结·CAP_HOURS_MONTHCARD_RATIO=1.5", "const OFFLINE_CAP_HOURS_MONTHCARD_RATIO = 1.5;", 1, "==", "未动"),
        ("R226 冻结·RATE_BASE=0.0048", "const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;", 1, "==", "未动"),
        ("R226 冻结·RATE_MONTHCARD=0.006", "const OFFLINE_RATE_MONTHCARD_PER_HOUR = 0.006;", 1, "==", "未动"),
        ("R226 冻结·STONE_RATIO=0.1", "const OFFLINE_STONE_RATIO = 0.1;", 1, "==", "未动"),
        ("R226 冻结·MIN_MS=5min", "const OFFLINE_MIN_MS = 5 * 60 * 1000;", 1, "==", "未动"),
        ("R226 冻结·公式修为行", "const expGain = enough ? Math.max(0, Math.min(Math.floor(slot * rate * effHours), slot - cur)) : 0;", 1, "==", "未动"),
        ("R226 冻结·公式灵石行", "const stonesGain = Math.floor(expGain * OFFLINE_STONE_RATIO);", 1, "==", "未动"),
        ("R226 冻结·offlineRewards", "function offlineRewards(", 1, "==", "未动"),
        ("R226 冻结·offlineCapHours", "function offlineCapHours(", 1, "==", "未动"),
        ("R226 冻结·offlineRatePerHour", "function offlineRatePerHour(", 1, "==", "未动"),
        ("R226 冻结·offlineWindow", "function offlineWindow(", 1, "==", "未动"),
        ("R226 冻结·calcOfflineGainV2(E2封顶)", "function calcOfflineGainV2(", 1, "==", "未动"),
        # ── 工程红线（相对计数）──
        ("R226 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403"),
        ("R226 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R226 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
        ("R226 红线·无 require", "require(", 0, "==", "ESM 不新增 require"),
    ]


def _apply(src: str) -> str:
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)
    return out


def _roundtrip(out: str, src: str):
    back = out
    for name, old, new in reversed(EDITS):
        if back.count(new) != 1:
            return False, "逆向：%s 的新块出现 %d 次（期望 1）" % (name, back.count(new))
        back = back.replace(new, old, 1)
    return (back == src), "逆向逐字节还原"


def _find_node():
    cand = [os.environ.get('YL_NODE'), os.environ.get('NODE'), shutil.which('node')]
    nroot = 'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions'
    if os.path.isdir(nroot):
        subs = sorted(os.path.join(nroot, d, 'node.exe') for d in os.listdir(nroot))
        cand += [p for p in reversed(subs) if os.path.isfile(p)]
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(text: str):
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.ts')
    try:
        with io.open(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        r = subprocess.run([node, '--experimental-strip-types', '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _extract(text: str, start_needle: str, end_needle: str) -> str:
    i = text.index(start_needle)
    j = text.index(end_needle, i) + len(end_needle)
    return text[i:j]


def _run_sim(out: str) -> int:
    """用**从产物中抽出的真实函数**（offlineRewards + offlineDifficultyMuls + actApplyGain）
    跑 easy/normal/hard × 相同离线时长的改前/改后对照，证倍率正确、其它项不变。"""
    node = _find_node()
    if not node:
        print("[SIM] node 未找到，跳过模拟")
        return 0
    try:
        f_rew = _extract(out, "function offlineRewards(",
                         "    effectiveMs: Math.round(effHours * 3600000),\n  };\n}")
        f_dif = _extract(out, "function offlineDifficultyMuls(",
                         "  return { expMul: 1.5, stoneMul: 1.5 };\n}")
        f_app = _extract(out, "function actApplyGain(",
                         "  return Math.max(0, Math.floor((Math.max(0, Math.floor(Number(base) || 0))) * (Number(mult) || 1)));\n}")
        c_stone = "const OFFLINE_STONE_RATIO = 0.1;"
        c_min = "const OFFLINE_MIN_MS = 5 * 60 * 1000;"
    except ValueError as e:
        print("[SIM] 抽取失败（产物结构异常）：%s" % e)
        return 1

    driver = "\n".join([
        c_stone, c_min, f_app, f_rew, f_dif,
        "const MAXEXP = 60000, CUR = 0, CAP = 24, RATE = 0.0048, WIN = 12 * 3600000;",
        "const rw = offlineRewards(MAXEXP, CUR, WIN, CAP, RATE);",
        "const bExp = actApplyGain(rw.expGain, 1);",
        "const bSt = actApplyGain(rw.stonesGain, 1);",
        "console.log('[SIM] 场景：练气期1层 maxExp=60000 cur=0 窗口=12h 上限=24h 速率=0.48%/h 灵石比例=10%');",
        "console.log('[SIM] 原始离线：hours=' + rw.hours + ' 修为=' + bExp + ' 灵石=' + bSt);",
        "console.log('[SIM] 难度        倍率    改前修为   改后修为    改前灵石   改后灵石');",
        "const cases = [['easy','easy'],['normal','normal'],['hard','hard'],['(缺失)','__none__']];",
        "for (const c of cases) {",
        "  const d = c[1] === '__none__' ? undefined : c[1];",
        "  const m = offlineDifficultyMuls(JSON.stringify({ settings: { difficulty: d } }));",
        "  const aExp = Math.min(actApplyGain(rw.expGain, m.expMul), Math.max(0, MAXEXP - CUR));",
        "  const aSt = actApplyGain(rw.stonesGain, m.stoneMul);",
        "  console.log('[SIM] ' + c[0].padEnd(10) + '  ' + (m.expMul.toFixed(1) + 'x').padEnd(6) +",
        "    '  ' + String(bExp).padStart(8) + '  ' + String(aExp).padStart(9) +",
        "    '  ' + String(bSt).padStart(9) + '  ' + String(aSt).padStart(9));",
        "}",
    ])
    fd, tmp = tempfile.mkstemp(suffix='.ts')
    try:
        with io.open(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(driver)
        r = subprocess.run([node, '--experimental-strip-types', tmp],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        sys.stdout.write(r.stdout or '')
        if r.returncode != 0:
            sys.stdout.write(r.stderr or '')
            return 1
        return 0
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _run_gates(out, base):
    ok = True
    for label, needle, exp, op, note in gates(out, base):
        act = out.count(needle)
        good = (act == exp) if op == "==" else (act >= exp)
        ok = ok and good
        print("  [%s] %-44s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    return ok


def _verify(out, src, base, do_node, tag):
    if not _run_gates(out, base):
        fail("门禁未全绿，未写回")
    if out != _apply(src):
        fail("round-trip(正向重构) mismatch")
    rt_ok, rt_msg = _roundtrip(out, src)
    if not rt_ok:
        fail("round-trip(逆向) mismatch：%s" % rt_msg)
    print("  %s delta = %+d chars  (%d -> %d)" % (tag, len(out) - len(src), len(src), len(out)))
    if do_node:
        rc, node = _node_check(out)
        print("  node --check rc=%s (%s)" % (rc, node or 'node not found (skipped)'))
        if rc not in (None, 0):
            fail("node --experimental-strip-types --check 未通过")


def main():
    ap = argparse.ArgumentParser(description="R-226 服务端离线收益吃难度倍率（服务端第 91 环）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--sim", action="store_true")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等：产物含标记 ⇒ SKIP（不写盘，rc=3）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return 3

    # 2) 依赖（绝对在位）
    for needle, op, cnt, why in REQUIRES:
        n = src.count(needle)
        good = (n == cnt) if op == "==" else (n >= cnt)
        if not good:
            fail("依赖未满足（%r 出现 %d 次，期望 %s %d）：%s" % (needle[:80], n, op, cnt, why))

    # 3) 锚点唯一 + 纯 ASCII
    for name, old, new in EDITS:
        if not all(ord(c) < 128 for c in old):
            fail("%s 锚点含非 ASCII 字符（违反工程约束）" % name)
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线（针脚必须在基座真实存在，防拼错导致冻结静默失效）
    base = {k: src.count(k) for k in BASE_NEEDLES}
    for k in BASE_NEEDLES:
        if base[k] <= 0 and k != "require(":  # require( 合法基线 = 0（ESM 红线）
            fail("冻结针脚在基座不存在（拼写错误？）：%r" % k[:90])

    # 5) 应用
    out = _apply(src)

    # 6) 门禁 + 往返 + 语法
    _verify(out, src, base, do_node=(a.check or a.selftest or a.sim), tag="--check")

    if a.sim:
        print("  ---- 难度 × 离线时长 模拟对照 ----")
        rc = _run_sim(out)
        if rc != 0:
            fail("模拟失败")

    if a.check or a.selftest or a.sim:
        print("  --check/--selftest/--sim：未写回 %s" % src_path)
        return 0

    # 7) 改前 .bak + 原子写回
    bak = "%s.bak-r226-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r226offline-", suffix=".tmp")
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
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:
        print("[ERROR] %s: %s" % (type(e).__name__, e))
        sys.exit(2)
