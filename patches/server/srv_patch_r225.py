# -*- coding: utf-8 -*-
r"""
srv_patch_r225.py -- R-225 服务端离线收益吃难度倍率（服务端第 91 环）

台账原文（R-225，逐字）
--------------------------------------------------------------------------
  「服务端离线收益未吃难度倍率（loadGame 直接 t({player}) 绕过客户端入账点）⇒ 需开服务端第 91 环。
    ★ 用户选困难就是想要更高收益，离线不享受属缺口。」

勘查结论（先纠正台账的靶点，再实现）
--------------------------------------------------------------------------
  台账把靶点写成 `calcOfflineGainV2`。实测（srv/index_v28.ts @1994）**它不是离线收益的发放点**，
  只是 `settleSaveEconV2`（@2055，POST /api/save 的正增量钳制）里的一个**配额项**
  （capExp 第三项 `off.exp` / capStone 第三项 `off.stones`）。
  服务端**真正的离线收益发放**在 `offlineRewards()`（@5749）：
    GET  /api/offline/report  → 预览（rw.expGain / rw.stonesGain）
    POST /api/offline/claim   → 入档（updatePlayerSave，**不经过 settleSaveEconV2 钳制**）
  客户端 `YlxwTOffline` 面板只读这两个端点；客户端 loadGame 的 `ww(d, Nw(d,f))` 只落
  grottoHerbs / lifespanSpent，**不落离线 exp/灵石**（`meditationExp` / `spiritStoneIncome`
  在 bundle 里是死字段，全产物 0 消费点）⇒ 台账那句「走 loadGame」的归因不成立。
  所以本环**两条路径一起接**同一张倍率表：
    ① 真发放 offlineRewards()（这是用户能看见的「离线收益」）
    ② 配额项 calcOfflineGainV2()（保持 cap 与发放同档，防未来某条推送路径把 ×2 收益钳掉）

难度信息在服务端拿得到吗？（能，证据见下）
--------------------------------------------------------------------------
  客户端 `pushSave`（bundle @603117）body = {player, logs, marketItems, timestamp,
  lastActiveTime, dungeonGate, **settings**: S.settings}；服务端 `app.post('/api/save')`
  （@2451 `const saveData = req.body`）**整包 JSON.stringify 落库**（saves.save_data）
  ⇒ `save_data.settings.difficulty` 恒在（本地探针库 uid=34 实测
  `{"soundEnabled":true,...,"difficulty":"normal"}`）。服务端此前从未读过 settings（0 引用）。
  倍率表与客户端 `Qr.difficulty`（bundle @294322）逐字同源：easy 1/1、normal 1.5/1.5、hard 2/2。
  缺失/非法 ⇒ normal 档 —— 与客户端 `YlxwDiffMul` 的兜底 `Qr.difficulty[d] || Qr.difficulty.normal` 一致。

改动面（全部唯一锚点，expect=1）
--------------------------------------------------------------------------
  ① 新增 `R225_DIFF_MUL` 表 + `ylR225DiffMul()` / `ylR225OfflineMults()`（插在 calcOfflineGainV2 之后）
  ② `calcOfflineGainV2` 加 diffExp/diffStone 形参（默认 1）+ 两行结果乘倍率
  ③ 其唯一调用点（settleSaveEconV2 @2154）传入 oldSd.settings 的倍率
  ④ `offlineRewards` 加 diffExpMul/diffStoneMul 形参（默认 1）+ 结果乘倍率
  ⑤⑥⑦ 三个调用点（report / claim 预览 / claim 入档）传入倍率

§18.2 频率放大手算（10s / 30s / 60s 三档）
--------------------------------------------------------------------------
  离线项 `off.exp = floor(floor(maxExp*0.004*0.02*hours*60) * m)`，`hours = min(sec/3600, 24)`，
  `sec = (now - prevSavedAt)/1000`，且 `sec > 30` 才结算（否则恒 0）。
    · 10s 档：sec = 10 ⇒ 不满足 sec>30 ⇒ off.exp = 0（乘 m 仍 0）
    · 30s 档：sec = 30 ⇒ 不满足 sec>30 ⇒ off.exp = 0（乘 m 仍 0）
    · 60s 档：sec = 60 ⇒ hours = 1/60 ⇒ off.exp = floor(maxExp*0.00008*m)
  一小时 60 次 60s 存档合计 = 60 * maxExp*0.00008*m = maxExp*0.0048*m = **恰好 1 小时离线收益**
  ⇒ 放大倍数 = **1.00x**。离线项**随真实经过时间线性缩放**（上限 24h），倍率 m 是常数因子，
  不引入任何「每请求常数/地板」⇒ **无频率放大**（§18.2 的定律针对的是不随 mins 缩放的常数项，
  本环两项都是时间线性项）。60s 档之上再快也只会让 sec≤30 ⇒ 项归 0，不放大。

§18.3 钳制回归（「合法大额必须全额通过」）
--------------------------------------------------------------------------
  已证：离线发放走 updatePlayerSave，**不经过 settleSaveEconV2**（不丢数据）。
  但 cap 里的 `off.exp/off.stones` 是「离线收益能进 /api/save 的额度」，故必须与发放同档。
  回归（--selftest 里用 Node 真跑产物函数）：困难档 12h 离线
    legit = offlineRewards(maxExp, cur, 12h, cap, 0.0048, 2, 2).expGain
    capOff = calcOfflineGainV2(op, now-12h, 2, 2).exp
    断言 capOff >= legit（cap 覆盖合法 ×2 离线收益 ⇒ 不会钳掉）；且 mE=1 时两函数与基线**逐位相同**。

CLI 契约（照 localtest/srv_patch_r129.py，兼容技能 §18.10 的装配器用法）
--------------------------------------------------------------------------
  `--src <path>`：就地原子写回该路径（写回前落 `<src>.bak-r225-<时间戳>`）。装配器把它复制成
    **私有副本**再传 `--src`，故就地写是安全的、也是被期望的（§18.10）。
  `--check` / `--selftest`：只校验不写回。幂等：产物含 `[r225diff]` 或 `R225_DIFF_MUL` 则 SKIP。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `setInterval` / `PRAGMA`。
  · 只改服务端；**不改客户端 bundle**；不改任何既有 srv_patch_*.py / chain_build.py / deploy_*/。
  · 每处替换 expect=1，命中数不符即中止；产物 round-trip 自证 + Node 真跑语义校验后原子写回。
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "srv", "index_v28.ts")

MARK = "[r225diff]"

# ============================================================ 新增辅助块（纯 ASCII 注释 + TS）
HELPER = r'''// ── R-225（服务端第 91 环）离线收益吃难度倍率 [r225diff] ──
// 台账 R-225：客户端 R-218 把难度倍率乘在**在线入账点**（YlxwDiffGain），离线收益没吃 ⇒ 补上。
// 服务端离线收益两条路径同接一张倍率表：
//   ① 真发放 = offlineRewards()（/api/offline/report 预览 + /api/offline/claim 入档）；
//   ② 配额项 = calcOfflineGainV2()（settleSaveEconV2 的 off.exp / off.stones 项）。
// 难度来源：客户端每次推档都带 settings（pushSave body 含 settings: S.settings），服务端整包
//   落库 ⇒ save_data.settings.difficulty ∈ {easy,normal,hard}。缺失/非法回落 normal —— 与客户端
//   YlxwDiffMul 的默认档（Qr.difficulty[d] || Qr.difficulty.normal）逐字一致。
// ★ 倍率表与客户端 Qr.difficulty 同源（bundle 实测：easy 1/1、normal 1.5/1.5、hard 2/2）。
// ★ Object.create(null) + hasOwnProperty 守卫：difficulty 由客户端提交，防 "toString" 之类
//   命中 Object.prototype（§18.12 原型链泄漏）。
const R225_DIFF_MUL: Record<string, { exp: number; stone: number }> = Object.create(null); // [r225diff]
R225_DIFF_MUL.easy = { exp: 1, stone: 1 };
R225_DIFF_MUL.normal = { exp: 1.5, stone: 1.5 };
R225_DIFF_MUL.hard = { exp: 2, stone: 2 };
// 难度倍率取值（纯）：saveData = 整包存档对象。key ∈ {'exp','stone'}。缺失/非法 ⇒ normal 档。
function ylR225DiffMul(saveData: any, key: 'exp' | 'stone'): number {
  try {
    const d = saveData && saveData.settings ? saveData.settings.difficulty : null;
    const row = (typeof d === 'string' && Object.prototype.hasOwnProperty.call(R225_DIFF_MUL, d))
      ? R225_DIFF_MUL[d] : R225_DIFF_MUL.normal;
    const v = Number(row ? row[key] : 1);
    return Number.isFinite(v) && v > 0 ? v : 1;
  } catch { return 1; }
}
// 难度倍率（接受「整包存档对象」或「原始 JSON 字符串」）：解析失败/缺失 ⇒ normal 档。
function ylR225OfflineMults(saveData: any): { exp: number; stone: number } {
  try {
    let root: any = saveData;
    if (typeof root === 'string') root = JSON.parse(root);
    return { exp: ylR225DiffMul(root, 'exp'), stone: ylR225DiffMul(root, 'stone') };
  } catch {
    return { exp: ylR225DiffMul(null, 'exp'), stone: ylR225DiffMul(null, 'stone') };
  }
}

'''

# ============================================================ 改动点（七替换，全部 expect=1）
EDITS = [
    # ① 插入辅助块（锚 = calcOfflineGainV2 结束后的空行 + 计数器差值注释头）
    ("R225 插入辅助块",
     "\n\n// 计数器差值：只认正增量（回档/多端旧档不倒扣，同 Y15/DG 口径）",
     "\n\n" + HELPER + "// 计数器差值：只认正增量（回档/多端旧档不倒扣，同 Y15/DG 口径）"),

    # ② calcOfflineGainV2 签名加两个形参
    ("R225 calcOfflineGainV2 签名",
     "function calcOfflineGainV2(p: any, fromMs: number | null): { exp: number; stones: number } {",
     "function calcOfflineGainV2(p: any, fromMs: number | null, diffExp: number = 1, diffStone: number = 1): { exp: number; stones: number } { // [r225diff]"),

    # ③ calcOfflineGainV2 结果乘倍率（exp + stones 两行）
    ("R225 calcOfflineGainV2 exp行",
     "    out.exp = Math.floor((Number(p.maxExp) || 100) * 0.004 * 0.02 * hours * 60);",
     "    const ylR225ME = Number.isFinite(diffExp) && diffExp > 0 ? diffExp : 1; // [r225diff]\n"
     "    const ylR225MS = Number.isFinite(diffStone) && diffStone > 0 ? diffStone : 1; // [r225diff]\n"
     "    out.exp = Math.floor(Math.floor((Number(p.maxExp) || 100) * 0.004 * 0.02 * hours * 60) * ylR225ME); // [r225diff] 离线×难度"),
    ("R225 calcOfflineGainV2 stones行",
     "    out.stones = Math.floor(Math.floor((idx <= 0 ? 4 / 3 : 2 * idx + 1) * 125) * hours); // YL_REALM_REWARD_SCALE_V26L",
     "    out.stones = Math.floor(Math.floor(Math.floor((idx <= 0 ? 4 / 3 : 2 * idx + 1) * 125) * hours) * ylR225MS); // [r225diff] 离线×难度 / YL_REALM_REWARD_SCALE_V26L"),

    # ④ calcOfflineGainV2 唯一调用点：传入 oldSd.settings 的倍率
    ("R225 calcOfflineGainV2 调用点",
     "    const off = calcOfflineGainV2(op, prevSavedAtMs);",
     "    const off = calcOfflineGainV2(op, prevSavedAtMs, ylR225DiffMul(oldSd, 'exp'), ylR225DiffMul(oldSd, 'stone')); // [r225diff] 离线收益吃难度（配额项与发放同档）"),

    # ⑤ offlineRewards 签名加两个形参
    ("R225 offlineRewards 签名",
     "  ratePerHour: number = OFFLINE_RATE_BASE_PER_HOUR\n"
     "): { hours: number; expGain: number; stonesGain: number; capped: boolean; claimable: boolean; effectiveMs: number } {",
     "  ratePerHour: number = OFFLINE_RATE_BASE_PER_HOUR,\n"
     "  diffExpMul: number = 1, diffStoneMul: number = 1 // [r225diff]\n"
     "): { hours: number; expGain: number; stonesGain: number; capped: boolean; claimable: boolean; effectiveMs: number } {"),

    # ⑥ offlineRewards 结果乘倍率（mE=mS=1 时与改前逐位一致）
    ("R225 offlineRewards 结果",
     "  const expGain = enough ? Math.max(0, Math.min(Math.floor(slot * rate * effHours), slot - cur)) : 0;\n"
     "  const stonesGain = Math.floor(expGain * OFFLINE_STONE_RATIO);",
     "  const baseExp = enough ? Math.max(0, Math.min(Math.floor(slot * rate * effHours), slot - cur)) : 0;\n"
     "  // [r225diff] 离线收益 × 难度倍率（默认 1 ⇒ 与改前逐位一致）\n"
     "  const ylR225ME = Number.isFinite(diffExpMul) && diffExpMul > 0 ? diffExpMul : 1;\n"
     "  const ylR225MS = Number.isFinite(diffStoneMul) && diffStoneMul > 0 ? diffStoneMul : 1;\n"
     "  const expGain = Math.max(0, Math.min(Math.floor(baseExp * ylR225ME), slot - cur));\n"
     "  const stonesGain = Math.max(0, Math.floor(Math.floor(baseExp * OFFLINE_STONE_RATIO) * ylR225MS));"),

    # ⑦ 三个调用点传倍率
    ("R225 report 调用点",
     "    const rw = win ? offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour) : null;",
     "    const ylR225M = ylR225OfflineMults(row.save_data); // [r225diff]\n"
     "    const rw = win ? offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour, ylR225M.exp, ylR225M.stone) : null;"),
    ("R225 claim 预览调用点",
     "    const rw = offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour);",
     "    const ylR225M = ylR225OfflineMults(row.save_data); // [r225diff]\n"
     "    const rw = offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour, ylR225M.exp, ylR225M.stone);"),
    ("R225 claim 入档调用点",
     "      const r = offlineRewards(nrNow.maxExp, nrNow.exp, win.windowMs, capHours, ratePerHour);",
     "      const ylR225M = ylR225OfflineMults(sd); // [r225diff]\n"
     "      const r = offlineRewards(nrNow.maxExp, nrNow.exp, win.windowMs, capHours, ratePerHour, ylR225M.exp, ylR225M.stone);"),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    ("function calcOfflineGainV2(p: any, fromMs: number | null): { exp: number; stones: number } {",
     1, "calcOfflineGainV2 旧签名必须在位且唯一"),
    ("    const off = calcOfflineGainV2(op, prevSavedAtMs);", 1, "calcOfflineGainV2 唯一调用点必须在位"),
    ("function offlineRewards(", 1, "offlineRewards 定义必须在位"),
    ("  ratePerHour: number = OFFLINE_RATE_BASE_PER_HOUR", 1, "offlineRewards 旧签名必须在位且唯一"),
    ("const OFFLINE_STONE_RATIO = 0.1;", 1, "OFFLINE_STONE_RATIO 必须在位"),
    ("const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;", 1, "OFFLINE_RATE_BASE_PER_HOUR 必须在位"),
    ("const OFFLINE_MIN_MS = 5 * 60 * 1000;", 1, "OFFLINE_MIN_MS 必须在位"),
    ("const ECON_REALM_ORDER: string[] = Object.keys(TRIB_REALM_BASES);", 1, "ECON_REALM_ORDER 必须在位（境界序）"),
    ("[r173offline]", 7, "r173 离线锚点环必须已应用（链序：本环排在既有离线环之后）"),
    ("    const rw = win ? offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour) : null;",
     1, "report 调用点必须在位且唯一"),
    ("    const rw = offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour);",
     1, "claim 预览调用点必须在位且唯一"),
    ("      const r = offlineRewards(nrNow.maxExp, nrNow.exp, win.windowMs, capHours, ratePerHour);",
     1, "claim 入档调用点必须在位且唯一"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "res.status(403", "require(", "setInterval(", "PRAGMA",
    "function offlineRewards(",
    "function offlineWindow(",
    "function offlineAnchor(",
    "function offlineCapHours(",
    "function offlineRatePerHour(",
    "function hasMonthCard(",
    "function offlineBreakthroughHint(",
    "const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;",
    "const OFFLINE_RATE_MONTHCARD_PER_HOUR = 0.006;",
    "const OFFLINE_STONE_RATIO = 0.1;",
    "const OFFLINE_MIN_MS = 5 * 60 * 1000;",
    "function actApplyGain(base: unknown, mult: unknown): number {",
    "const off = calcOfflineGainV2(",
    "app.get('/api/offline/report'",
    "app.post('/api/offline/claim'",
    "insertMail(userId, '闭关修炼 · 离线收益'",
    "offline_claimed_until = ? WHERE user_id = ? AND (offline_claimed_until IS NULL OR offline_claimed_until < ?)",
    "[r173offline]",
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


# ============================================================ 源码抽取（字符串/注释感知的括号配平，§25.1）
def extract_brace(src, start):
    """从 src[start] == '{' 起做括号配平，返回含首尾花括号的函数体片段。"""
    assert src[start] == '{', "extract_brace: not at '{'"
    depth = 0
    k = start
    n = len(src)
    mode = None  # None | "'" | '"' | '`' | '//' | '/*'
    while k < n:
        c = src[k]
        if mode == "'" or mode == '"' or mode == '`':
            if c == '\\':
                k += 2
                continue
            if c == mode:
                mode = None
        elif mode == '//':
            if c == '\n':
                mode = None
        elif mode == '/*':
            if c == '*' and k + 1 < n and src[k + 1] == '/':
                mode = None
                k += 2
                continue
        else:
            if c == '/' and k + 1 < n and src[k + 1] == '/':
                mode = '//'
                k += 2
                continue
            if c == '/' and k + 1 < n and src[k + 1] == '*':
                mode = '/*'
                k += 2
                continue
            if c == "'" or c == '"' or c == '`':
                mode = c
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return src[start:k + 1]
        k += 1
    raise ValueError("unbalanced braces")


def extract_fn(src, header, ret_anchor):
    i = src.index(header)
    a = src.index(ret_anchor, i) + len(ret_anchor) - 1
    assert src[a] == '{', "extract_fn: ret_anchor tail not '{'"
    return src[i:a] + extract_brace(src, a)  # header（含返回类型） + 完整函数体（含花括号）


# ============================================================ Node 语义校验（真跑产物函数）
HARNESS = r'''
const FIXED = 1700000000000;
const _realNow = Date.now;
Date.now = () => FIXED; // 冻结时钟，消除 sec 抖动

const OFFLINE_RATE_BASE_PER_HOUR = 0.0048;
const OFFLINE_RATE_MONTHCARD_PER_HOUR = 0.006;
const OFFLINE_STONE_RATIO = 0.1;
const OFFLINE_MIN_MS = 5 * 60 * 1000;
const ECON_REALM_ORDER = ['\u70bc\u6c14\u671f','\u7b51\u57fa\u671f','\u91d1\u4e39\u671f','\u5143\u5a74\u671f','\u5316\u795e\u671f','\u5408\u9053\u671f','\u957f\u751f\u5883'];

__HELPER__

__BASE_FN__

__NEW_FN__

const R = [];
function ck(name, ok, extra) { R.push({ name, ok: !!ok, extra: extra === undefined ? '' : String(extra) }); }

// ---- A) mE=mS=1 ⇒ 与基线逐位一致 ----
{
  let same = true, first = null;
  const grids = [[100,0,0,24],[60000,0,3600e3,24],[760500,100,12*3600e3,86],[1e9,0,24*3600e3,24],
                 [3e9,3e9-1,3600e3,24],[452500000,1000,47*3600e3,86],[12345,0,299999,24],[12345,0,300001,24]];
  for (const [mx,cu,wm,ch] of grids) {
    for (const rate of [OFFLINE_RATE_BASE_PER_HOUR, OFFLINE_RATE_MONTHCARD_PER_HOUR]) {
      const b = baseOfflineRewards(mx,cu,wm,ch,rate);
      const n = newOfflineRewards(mx,cu,wm,ch,rate);
      if (JSON.stringify(b) !== JSON.stringify(n)) { same = false; if (!first) first = {mx,cu,wm,ch,rate,b,n}; }
    }
  }
  ck('A1 mE=mS=1 与基线逐位一致', same, first ? JSON.stringify(first) : '');
}

// ---- B) 难度倍率生效（未触槽上限时恰 ×m；触上限时钳 slot-cur） ----
{
  const mx = 1e9, ch = 86, wm = 12*3600e3;
  const e1 = newOfflineRewards(mx,0,wm,ch,OFFLINE_RATE_BASE_PER_HOUR,1,1);
  const e2 = newOfflineRewards(mx,0,wm,ch,OFFLINE_RATE_BASE_PER_HOUR,2,2);
  const e15 = newOfflineRewards(mx,0,wm,ch,OFFLINE_RATE_BASE_PER_HOUR,1.5,1.5);
  ck('B1 hard exp 恰 ×2', e2.expGain === e1.expGain*2, e1.expGain+' -> '+e2.expGain);
  ck('B2 hard stones 恰 ×2', e2.stonesGain === e1.stonesGain*2, e1.stonesGain+' -> '+e2.stonesGain);
  ck('B3 normal exp 恰 ×1.5', e15.expGain === Math.floor(e1.expGain*1.5), e1.expGain+' -> '+e15.expGain);
  // 触槽上限：cur 逼近 slot
  const eC = newOfflineRewards(1000, 999, wm, ch, OFFLINE_RATE_BASE_PER_HOUR, 2, 2);
  ck('B4 触槽上限时 exp 钳 slot-cur(=1)', eC.expGain === 1, String(eC.expGain));
  // claimable 不受倍率影响（base 0 ⇒ 仍 0）
  const z = newOfflineRewards(1e9, 1e9, wm, ch, OFFLINE_RATE_BASE_PER_HOUR, 2, 2);
  ck('B5 满槽时 expGain=0 且 claimable=false', z.expGain === 0 && z.claimable === false, JSON.stringify(z));
}

// ---- C) 难度取值器（含原型链/缺失/非法） ----
{
  ck('C1 easy=1/1', ylR225DiffMul({settings:{difficulty:'easy'}},'exp')===1 && ylR225DiffMul({settings:{difficulty:'easy'}},'stone')===1);
  ck('C2 normal=1.5/1.5', ylR225DiffMul({settings:{difficulty:'normal'}},'exp')===1.5 && ylR225DiffMul({settings:{difficulty:'normal'}},'stone')===1.5);
  ck('C3 hard=2/2', ylR225DiffMul({settings:{difficulty:'hard'}},'exp')===2 && ylR225DiffMul({settings:{difficulty:'hard'}},'stone')===2);
  ck('C4 缺失⇒normal', ylR225DiffMul({},'exp')===1.5 && ylR225DiffMul(null,'exp')===1.5);
  ck('C5 非法串⇒normal', ylR225DiffMul({settings:{difficulty:'NOPE'}},'exp')===1.5);
  ck('C6 toString 不命中原型链⇒normal', ylR225DiffMul({settings:{difficulty:'toString'}},'exp')===1.5, String(ylR225DiffMul({settings:{difficulty:'toString'}},'exp')));
  ck('C7 constructor 不命中原型链⇒normal', ylR225DiffMul({settings:{difficulty:'constructor'}},'exp')===1.5);
  ck('C8 settings 非对象⇒normal', ylR225DiffMul({settings:'x'},'exp')===1.5);
  ck('C9 原始 JSON 串可解析', ylR225OfflineMults('{"settings":{"difficulty":"hard"}}').exp===2);
  ck('C10 坏 JSON 串⇒normal', ylR225OfflineMults('{bad').exp===1.5);
}

// ---- D) §18.2 三档频率（calcOfflineGainV2） ----
{
  const mx = 1e9;
  const d10 = newCalcOfflineGainV2({realm:'\u91d1\u4e39\u671f', maxExp:mx}, FIXED-10000, 2, 2);
  const d30 = newCalcOfflineGainV2({realm:'\u91d1\u4e39\u671f', maxExp:mx}, FIXED-30000, 2, 2);
  const d60 = newCalcOfflineGainV2({realm:'\u91d1\u4e39\u671f', maxExp:mx}, FIXED-60000, 2, 2);
  ck('D1 10s 档 off=0', d10.exp===0 && d10.stones===0, JSON.stringify(d10));
  ck('D2 30s 档 off=0', d30.exp===0 && d30.stones===0, JSON.stringify(d30));
  const perHour = d60.exp * 60;                        // 60 次 60s 存档合计
  const oneHour = newCalcOfflineGainV2({realm:'\u91d1\u4e39\u671f', maxExp:mx}, FIXED-3600000, 2, 2).exp;
  const ratio = oneHour > 0 ? perHour / oneHour : 0;
  ck('D3 60s 档：60 次合计 ≈ 1h 离线（放大 ≈1.00x）', Math.abs(ratio - 1) < 0.01, 'ratio='+ratio.toFixed(4)+' perHour='+perHour+' oneHour='+oneHour);
  ck('D4 60s 档 off.exp>0（确已结算）', d60.exp > 0, String(d60.exp));
}

// ---- E) §18.3 钳制回归：合法 ×2 离线收益必须被 cap 覆盖 ----
{
  const mx = 760500, cur = 100, ch = 86, wm = 12*3600e3;
  const legit = newOfflineRewards(mx,cur,wm,ch,OFFLINE_RATE_BASE_PER_HOUR,2,2).expGain;
  const capOff = newCalcOfflineGainV2({realm:'\u91d1\u4e39\u671f', maxExp:mx}, FIXED-12*3600e3, 2, 2).exp;
  ck('E1 cap 离线项 ≥ 合法 ×2 离线收益', capOff >= legit, 'capOff='+capOff+' legit='+legit);
  const legit1 = newOfflineRewards(mx,cur,wm,ch,OFFLINE_RATE_BASE_PER_HOUR,1,1).expGain;
  const capOff1 = newCalcOfflineGainV2({realm:'\u91d1\u4e39\u671f', maxExp:mx}, FIXED-12*3600e3, 1, 1).exp;
  ck('E2 基线档（m=1）cap 仍 ≥ 合法收益', capOff1 >= legit1, 'capOff1='+capOff1+' legit1='+legit1);
  ck('E3 合法 ×2 收益非零（用例非空）', legit > 0, String(legit));
}

Date.now = _realNow;
const bad = R.filter(x => !x.ok);
for (const x of R) console.log((x.ok?'  [OK] ':'  [FAIL] ')+x.name+(x.extra?('  <'+x.extra+'>'):''));
console.log('HARNESS_RESULT '+JSON.stringify({total:R.length, fail:bad.length}));
if (bad.length) process.exit(3);
'''


def build_harness(src, out):
    """从基线 src 与产物 out 抽取函数，生成 Node 校验脚本。"""
    ret_off = "): { hours: number; expGain: number; stonesGain: number; capped: boolean; claimable: boolean; effectiveMs: number } {"
    ret_calc = "): { exp: number; stones: number } {"
    base_off = extract_fn(src, "function offlineRewards(", ret_off).replace(
        "function offlineRewards(", "function baseOfflineRewards(", 1)
    new_off = extract_fn(out, "function offlineRewards(", ret_off).replace(
        "function offlineRewards(", "function newOfflineRewards(", 1)
    new_calc = extract_fn(out, "function calcOfflineGainV2(", ret_calc).replace(
        "function calcOfflineGainV2(", "function newCalcOfflineGainV2(", 1)
    a = out.index("// ── R-225")
    b = out.index("// 计数器差值", a)
    helper = out[a:b]
    js = (HARNESS
          .replace("__HELPER__", helper)
          .replace("__BASE_FN__", base_off + "\n")
          .replace("__NEW_FN__", new_off + "\n" + new_calc + "\n"))
    return js


def node_bin():
    root = r"C:/Users/<USER>/.workbuddy-ai/binaries/node/versions"
    cands = []
    if os.path.isdir(root):
        cands = sorted(os.path.join(root, d, "node.exe") for d in os.listdir(root))
        cands = [c for c in cands if os.path.isfile(c)]
    return os.environ.get("YL_NODE") or (cands[-1] if cands else "node")


def run_harness(js):
    # 抽出的函数带 TS 类型标注 ⇒ 用 .mts + --experimental-strip-types 真跑（不做类型检查）
    d = tempfile.mkdtemp(prefix="r225node-")
    p = os.path.join(d, "h.mts")
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(js)
    try:
        r = subprocess.run([node_bin(), "--experimental-strip-types", p],
                           capture_output=True, text=True, encoding="utf-8")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description="R-225 服务端离线收益吃难度倍率（服务端第 91 环）")
    ap.add_argument("--src", default=SRC, help="待打补丁的服务端源码（装配器会传私有副本）")
    ap.add_argument("--check", action="store_true", help="只校验不写回")
    ap.add_argument("--selftest", action="store_true", help="只校验不写回（含 Node 真跑）")
    a = ap.parse_args()

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等
    if MARK in src or "R225_DIFF_MUL" in src:
        print("[SKIP] source looks already patched（已含 %s / R225_DIFF_MUL）" % MARK)
        return

    # 2) 依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:80], n, cnt, why))

    # 3) 锚点计数
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]))
        if old == new:
            fail("%s old == new" % name)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    mark_n = sum(new.count(MARK) for _, _, new in EDITS)
    gates = [
        ("R225 幂等标记就位", MARK, mark_n),
        ("R225 倍率表 hard=2/2", "R225_DIFF_MUL.hard = { exp: 2, stone: 2 };", 1),
        ("R225 倍率表 normal=1.5/1.5", "R225_DIFF_MUL.normal = { exp: 1.5, stone: 1.5 };", 1),
        ("R225 倍率表 easy=1/1", "R225_DIFF_MUL.easy = { exp: 1, stone: 1 };", 1),
        ("R225 表用 Object.create(null)", "const R225_DIFF_MUL: Record<string, { exp: number; stone: number }> = Object.create(null);", 1),
        ("R225 hasOwnProperty 守卫", "Object.prototype.hasOwnProperty.call(R225_DIFF_MUL, d)", 1),
        ("R225 取值器 ylR225DiffMul", "function ylR225DiffMul(saveData: any, key: 'exp' | 'stone'): number {", 1),
        ("R225 取值器 ylR225OfflineMults", "function ylR225OfflineMults(saveData: any): { exp: number; stone: number } {", 1),
        # calcOfflineGainV2
        ("R225 calc 新签名", "function calcOfflineGainV2(p: any, fromMs: number | null, diffExp: number = 1, diffStone: number = 1): { exp: number; stones: number } {", 1),
        ("R225 calc 旧签名清零", "function calcOfflineGainV2(p: any, fromMs: number | null): { exp: number; stones: number } {", 0),
        ("R225 calc exp 乘倍率", "out.exp = Math.floor(Math.floor((Number(p.maxExp) || 100) * 0.004 * 0.02 * hours * 60) * ylR225ME);", 1),
        ("R225 calc stones 乘倍率", "out.stones = Math.floor(Math.floor(Math.floor((idx <= 0 ? 4 / 3 : 2 * idx + 1) * 125) * hours) * ylR225MS);", 1),
        ("R225 calc 旧 exp 行清零", "out.exp = Math.floor((Number(p.maxExp) || 100) * 0.004 * 0.02 * hours * 60);", 0),
        ("R225 calc 调用点传倍率", "const off = calcOfflineGainV2(op, prevSavedAtMs, ylR225DiffMul(oldSd, 'exp'), ylR225DiffMul(oldSd, 'stone'));", 1),
        ("R225 calc 旧调用点清零", "const off = calcOfflineGainV2(op, prevSavedAtMs);", 0),
        # offlineRewards
        ("R225 offline 新签名", "  diffExpMul: number = 1, diffStoneMul: number = 1", 1),
        ("R225 offline baseExp 引入", "const baseExp = enough ? Math.max(0, Math.min(Math.floor(slot * rate * effHours), slot - cur)) : 0;", 1),
        ("R225 offline exp 乘倍率", "const expGain = Math.max(0, Math.min(Math.floor(baseExp * ylR225ME), slot - cur));", 1),
        ("R225 offline stones 乘倍率", "const stonesGain = Math.max(0, Math.floor(Math.floor(baseExp * OFFLINE_STONE_RATIO) * ylR225MS));", 1),
        ("R225 offline 旧 exp 行清零", "const expGain = enough ? Math.max(0, Math.min(Math.floor(slot * rate * effHours), slot - cur)) : 0;", 0),
        ("R225 offline 旧 stones 行清零", "const stonesGain = Math.floor(expGain * OFFLINE_STONE_RATIO);", 0),
        # 三个调用点
        ("R225 report 调用点传倍率", "offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour, ylR225M.exp, ylR225M.stone) : null;", 1),
        ("R225 claim 预览传倍率", "const rw = offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour, ylR225M.exp, ylR225M.stone);", 1),
        ("R225 claim 入档传倍率", "const r = offlineRewards(nrNow.maxExp, nrNow.exp, win.windowMs, capHours, ratePerHour, ylR225M.exp, ylR225M.stone);", 1),
        ("R225 report 旧调用点清零", "const rw = win ? offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour) : null;", 0),
        ("R225 claim 预览旧调用点清零", "const rw = offlineRewards(nr.maxExp, nr.exp, win.windowMs, capHours, ratePerHour);", 0),
        ("R225 claim 入档旧调用点清零", "const r = offlineRewards(nrNow.maxExp, nrNow.exp, win.windowMs, capHours, ratePerHour);", 0),
    ]
    # 冻结：既有离线函数/常量/路由/邮件一字不动
    for needle in BASE_NEEDLES:
        gates.append(("冻结 " + needle[:44].replace("\n", " "), needle, base[needle]))
    # 红线
    gates.append(("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]))
    gates.append(("红线 未新增 require(", "require(", base["require("]))
    gates.append(("红线 未新增 setInterval", "setInterval(", base["setInterval("]))
    gates.append(("红线 未新增 PRAGMA", "PRAGMA", base["PRAGMA"]))

    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        if not good:
            print("  [FAIL] %-52s actual=%d expect==%d" % (label, act, exp))
    print("  [%s] 门禁 %d 条" % ("OK" if ok else "FAIL", len(gates)))

    # 7) round-trip 自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    # 8) Node 真跑产物函数
    js = build_harness(src, out)
    r = run_harness(js)
    sys.stdout.write(r.stdout or "")
    if r.stderr:
        sys.stdout.write("[node stderr]\n" + r.stderr)
    sem_ok = (r.returncode == 0 and "HARNESS_RESULT" in (r.stdout or "")
              and json.loads(r.stdout.strip().split("HARNESS_RESULT ")[-1].splitlines()[0])["fail"] == 0)
    ok = ok and sem_ok
    print("  [%s] Node 真跑语义校验" % ("OK" if sem_ok else "FAIL"))

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if not ok:
        fail("门禁未全绿，未写回")

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r225-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r225diff-", suffix=".tmp")
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
