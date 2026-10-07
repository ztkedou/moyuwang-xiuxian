# -*- coding: utf-8 -*-
r"""
srv_patch_r112.py -- R-112 打坐/历练产出灵玉（服务端环 · SRV_CHAIN 新末环）

台账原文（R-112，进行中，逐字）
--------------------------------------------------------------------------
  「灵玉产出的产出，打坐、历练也会获得，打坐几率最低，历练比打坐获得几率略高一点。」

为什么必须走服务端（2026-10-02 主控口径，接替上轮客户端半成品）
--------------------------------------------------------------------------
  灵玉真值在服务端 activity_token（key 'lingyu'，由 actDropTokens 唯一写入）；
  打坐/历练是客户端权威结算、无独立服务端端点 ⇒ 客户端单独写 jadeBalance 会被
  存档采纳器覆盖（资损风险）。上轮 patches/client/yl_r112_ext.py 正是这种客户端
  写入方案（其自述 §三.A 也承认该缺口），已按主控指令改判废弃（墓碑化，见该文件
  头注释），本环为唯一实现：**服务端在 POST /api/save 处理器按 Δ 差值 roll + 发放**。

实现口径（本环代决，已录拍板 2026-10-02_R112灵玉服务端环实现层代决.md）
--------------------------------------------------------------------------
  · 挂点：POST /api/save 的 **UPDATE 分支**回调（row 存在 = 有上次基线），紧跟
    tickWudaoIdle 埋点行之后，fire-and-forget（与同处 6 个埋点同模式）。
    首存走 INSERT 分支 ⇒ **结构性不 roll**（主控口径「存档无上次基线=首存不 roll」）；
    基线坏 JSON ⇒ prevCounters=null ⇒ if 守卫不进 ⇒ 不 roll（同 Y2 埋点口径）。
  · Δ 口径：Δmeditate = e2Delta(旧.meditateCount, 新.meditateCount)，Δadventure 同理。
    e2Delta 对 b<=a 返回 0 ⇒ **Δ 为负（回档/采纳器回调）不 roll 不扣**（主控口径）。
  · 防刷（沿用既有口径，逐字镜像 settleSaveEconV2 :2040-2052）：
      时间钳 cMed=ceil(realMins*300)+30 / cAdv=ceil(realMins*130)+30，
      realMins 由 saves.updated_at 实算；updated_at 缺失/坏 ⇒ NaN ⇒ cntCap=0 ⇒ 不 roll
      （**fail-closed**，比结算器的 1440 分宽限更紧——灵玉是代币，宁不发不误发）。
      ★ 该钳是镜像不是复用：若 settleSaveEconV2 改公式必须同步本环（块内已注）。
  · 概率定档（打坐最低、历练略高；单次率与小时期望双序一致）：
      打坐 0.004/跳（约 2s/跳 ⇒ ≈7.2 玉/时）＜ 历练 0.009/次（约 4s/次 ⇒ ≈8.1 玉/时）。
      命中 1 玉/次（R112_JADE_*_CHANCE 单点常量，调参只动这里）。
  · 发放：actDropTokens(userId, stonesEq, now)，stonesEq = hits*ceil(10000/RATE)。
      RATE=ACT_TOKEN_RATE_PER_10K=50 ⇒ 200 石/玉，floor(200*50/10000)=1 恰 1:1。
      日上限 300（ACT_TOKEN_DAILY_CAP）+ activity_token_daily 守卫钳制 + 活跃
      token_shop 场次门槛全部复用 actDropTokens 既有口径（主控指定发放通道）。
  · 零客户端改动：客户端不写 jadeBalance；灵玉余额经既有 /api/activity/shop 下发
    （jadeBalance 字段，v2810 改名后的安全口径）。无 toast（服务端无 UI 通道，
    灵玉阁余额即反馈；与炼丹/灵田/离线 3 个既有掉玉挂点同静默口径）。

锚点与跨模块门禁核对（坑 26 全仓 grep，2026-10-02 实测）
--------------------------------------------------------------------------
  · E1 锚 = function e2Delta(...) 定义行（唯一，count==1）；全仓仅 t7_sect 引用
    e2Delta(oContrib,nContrib)（用法非定义行），无人以定义行为 needle。
  · E2 锚 = UPDATE 分支 tickWudaoIdle 全行（含行尾「fire-and-forget」注释，唯一）；
    srv_patch_v2810 G 门禁断言 `tickWudaoIdle(...ylWudaoIdleDelta...) == 2`（两分支）——
    本环**追加独立行**、不含该子串 ⇒ 计数仍 2，其门禁保持绿。
  · 纯插入、零改基线行（坑 15：NEW = ANCHOR + 新体，锚点原文逐字保留；坑 26 对策②）。
  · 坑 5/6/红线：无 require(、无 db.run(...).catch(、无新 res.status(403、无 setInterval(
    （打后计数 == 打前计数，门禁冻结面核对）。

CLI 契约（照 srv_patch_r123.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径（写回前 .bak-r112-<时间戳>）；`--check` / `--selftest`
  只校验不写。幂等：产物含 [r112] 则 SKIP。--selftest 用 node --experimental-strip-types
  跑临时 JS 语义 harness（首存/坏基线/负Δ/钳制/换算/常量序 10 项推演），用完即删。
  lead 接线：SRV_CHAIN 追加一行（挂链尾，锚全在基座段/既有环段，任意批次均可）：
      'srv_patch_r112.py',       # R-112 打坐/历练掉玉（服务端）：/api/save UPDATE 分支按
                                 #   Δmeditate/Δadventure roll（打坐0.4%<历练0.9%），命中经
                                 #   actDropTokens 发放（日上限300复用）；首存/坏基线/负Δ不 roll。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time

SRC = os.path.join("srv", "index_v28.ts")
MARK = "[r112]"
NODE = r"C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe"

MED_CHANCE = "0.004"   # 打坐 每跳掉玉率（最低）
ADV_CHANCE = "0.009"   # 历练 每次掉玉率（略高于打坐）

# ============================================================ 锚点（2026-10-02 对链头产物 srv/index_v28.ts md5=77c705ec 实测 count==1）

E1_ANCHOR = "function e2Delta(a: number, b: number): number { return b > a ? Math.floor(b) - Math.floor(a) : 0; }"

E2_ANCHOR = ("            if (prevCounters) tickWudaoIdle(req.user.id, ylWudaoIdleDelta(prevCounters, saveData))"
             ".catch((e: any) => console.error('wudao idle error:', (e as any)?.message || e));"
             " // WUDAO 埋点：打坐时长差值→随机系心得，fire-and-forget")

E2_CALL = ("            if (prevCounters) ylR112JadeDrop(req.user.id, row.save_data, saveData, row.updated_at); "
           "// [r112] R-112 打坐/历练掉玉：Δmeditate/Δadventure 服务端 roll → actDropTokens（行存在=有上次基线；"
           "prevCounters=null=基线坏不 roll；首存走 INSERT 分支无此行=结构性不 roll；Δ负按 e2Delta=0 不扣玉）")

# ============================================================ 注入块（E1：helper，锚点行后追加；纯加法）

BLOCK = """// [r112] R-112 打坐/历练掉玉（服务端环，2026-10-02）：打坐每跳 0.4%、历练每次 0.9%（打坐最低、历练略高），命中 1 玉/次。
// 口径：Δ 差值只在 POST /api/save 的 UPDATE 分支结算（服务端权威）；首存（INSERT 分支）与基线坏 JSON 不 roll；
// Δ 为负（回档/采纳器回调）按 e2Delta 语义 = 0，绝不扣玉；发放走 actDropTokens —— 日上限 300（ACT_TOKEN_DAILY_CAP）、
// activity_token_daily 守卫钳制、活跃 token_shop 场次门槛全部复用既有口径；玉/命中经 stones 当量换算（RATE=50 ⇒ 200 石/玉，floor 恰 1:1）。
// ★ 防刷钳 cMed/cAdv 为 settleSaveEconV2 计数器时间钳的逐字镜像（那边改公式必须同步这边）。
const R112_JADE_MED_CHANCE = __MED__; // 打坐 每跳（约 2s/跳 ⇒ 期望 ≈7.2 玉/时）
const R112_JADE_ADV_CHANCE = __ADV__; // 历练 每次（约 4s/次 ⇒ 期望 ≈8.1 玉/时，略高于打坐）
function ylR112RollHits(n: number, chance: number): number {
  const total = Math.floor(Number(n) || 0);
  const c = Number(chance);
  if (!(total > 0) || !(c > 0)) return 0;
  let hits = 0;
  for (let i = 0; i < total; i++) { if (Math.random() < c) hits++; }
  return hits;
}
function ylR112JadeDrop(userId: number, oldSaveJson: unknown, newSd: any, prevUpdatedAt: unknown): void {
  try {
    if (!oldSaveJson) return; // 无上次基线（首存/行缺失）⇒ 不 roll
    let oldSd: any = null;
    try { oldSd = JSON.parse(String(oldSaveJson)); } catch { return; } // 基线坏 JSON ⇒ 不 roll（防历史计数一次性全额入账）
    const os = (oldSd && oldSd.player && oldSd.player.statistics) || {};
    const ns = (newSd && newSd.player && newSd.player.statistics) || {};
    const t = prevUpdatedAt == null ? NaN : Date.parse(String(prevUpdatedAt).replace(' ', 'T') + 'Z');
    const realMins = Number.isFinite(t) ? Math.max(0, (Date.now() - t) / 60000) : NaN;
    const cntCap = (c: number): number => (Number.isFinite(c) && c >= 0 ? c : 0); // 镜像 settleSaveEconV2 KI-001 K3
    let dMed = e2Delta(Number(os.meditateCount) || 0, Number(ns.meditateCount) || 0);
    let dAdv = e2Delta(Number(os.adventureCount) || 0, Number(ns.adventureCount) || 0);
    const cMed = cntCap(Math.ceil(realMins * 300) + 30); // 镜像：自动打坐 200ms/次 → 300 次/分
    const cAdv = cntCap(Math.ceil(realMins * 130) + 30); // 镜像：自动历练 500ms/次 → 120 次/分
    if (dMed > cMed) dMed = cMed;
    if (dAdv > cAdv) dAdv = cAdv;
    const hits = ylR112RollHits(dMed, R112_JADE_MED_CHANCE) + ylR112RollHits(dAdv, R112_JADE_ADV_CHANCE);
    if (hits <= 0) return;
    const stonesEq = hits * Math.ceil(10000 / ACT_TOKEN_RATE_PER_10K); // 1 玉/命中（RATE=50 ⇒ 200 石/玉，floor 换算恰 1:1）
    actDropTokens(userId, stonesEq, Date.now()).catch((e: any) => console.error('r112 act drop tokens error:', e?.message || e));
  } catch (e: any) {
    console.error('r112 jade drop error:', e?.message || e); // 掉玉旁路，绝不影响存档主路径
  }
}""".replace("__MED__", MED_CHANCE).replace("__ADV__", ADV_CHANCE)

E1_OLD = E1_ANCHOR
E1_NEW = E1_ANCHOR + "\n\n" + BLOCK
E2_OLD = E2_ANCHOR
E2_NEW = E2_ANCHOR + "\n" + E2_CALL

EDITS = [
    ("E1 掉玉 helper 块注入（e2Delta 行后）", E1_OLD, E1_NEW),
    ("E2 UPDATE 分支挂调用（tickWudaoIdle 行后）", E2_OLD, E2_NEW),
]

# ============================================================ 前置依赖（打前自证；count 全部 ==1 除注明外）

REQUIRES = [
    (E1_ANCHOR, 1, "e2Delta 定义行（E1 锚）"),
    (E2_ANCHOR, 1, "UPDATE 分支 tickWudaoIdle 全行（E2 锚；行尾 fire-and-forget 注释区分 INSERT 分支孪生行）"),
    ("async function actDropTokens(userId: number, stonesSettled: number, nowMs: number): Promise<number> {", 1,
     "掉玉发放通道（日上限/场次门槛载体）"),
    ("const ACT_TOKEN_DAILY_CAP = 300;", 1, "日上限 300（主控口径）"),
    ("const ACT_TOKEN_RATE_PER_10K = 50;", 1, "玉/万灵石换算率（stonesEq 换算依据）"),
    ("app.post('/api/save'", 1, "存档处理器在位"),
    ("let dMed = e2Delta(Number(os.meditateCount) || 0, Number(ns.meditateCount) || 0);", 1,
     "结算器 Δmeditate 源行（镜像对象在位）"),
    ("const cMed = Math.ceil(realMins * 300) + 30;", 1, "结算器打坐时间钳源行（镜像对象在位）"),
    ("const cAdv = Math.ceil(realMins * 130) + 30;", 1, "结算器历练时间钳源行（镜像对象在位）"),
    ("tickWudaoIdle(req.user.id, ylWudaoIdleDelta(prevCounters, saveData))", 2,
     "两分支孪生调用在位（v2810 G 门禁同款断言；本环打后必须仍 ==2）"),
]

# ============================================================ 冻结面（打前==打后）

FREEZE_NEEDLES = [
    "res.status(403",                      # 403=强制登出铁律：本环零新增
    "setInterval(",                        # 本环零新增
    "PRAGMA",                              # 本环零新增
    "require(",                            # ESM 红线（恒 0）
    "db.run('INSERT",                      # 本环零新增写表
]


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def apply_edits(src, nl):
    """返回 (out, [(name, old, new)...])；nl = 该文件实际换行符（锚点均为单行，不受影响）。"""
    e1_new = E1_ANCHOR + nl + nl + BLOCK
    e2_new = E2_ANCHOR + nl + E2_CALL
    out = src
    out = out.replace(E1_OLD, e1_new, 1)
    out = out.replace(E2_OLD, e2_new, 1)
    return out


def verify(out):
    checks = [
        ("R112 幂等标记（块头+调用点）", MARK, 2),
        ("R112 打坐率常量 0.004", "const R112_JADE_MED_CHANCE = %s;" % MED_CHANCE, 1),
        ("R112 历练率常量 0.009", "const R112_JADE_ADV_CHANCE = %s;" % ADV_CHANCE, 1),
        ("R112 roll 函数定义", "function ylR112RollHits(n: number, chance: number): number {", 1),
        ("R112 掉玉函数定义", "function ylR112JadeDrop(userId: number, oldSaveJson: unknown, newSd: any, prevUpdatedAt: unknown): void {", 1),
        ("R112 首存/空基线守卫", "if (!oldSaveJson) return;", 1),
        ("R112 坏基线守卫", "catch { return; } // 基线坏 JSON", 1),
        ("R112 负Δ=e2Delta 口径", "let dMed = e2Delta(Number(os.meditateCount) || 0, Number(ns.meditateCount) || 0);", 2),
        ("R112 时间钳镜像 med", "const cMed = cntCap(Math.ceil(realMins * 300) + 30);", 1),
        ("R112 时间钳镜像 adv", "const cAdv = cntCap(Math.ceil(realMins * 130) + 30);", 1),
        ("R112 stones 当量换算", "const stonesEq = hits * Math.ceil(10000 / ACT_TOKEN_RATE_PER_10K);", 1),
        ("R112 发放走 actDropTokens", "actDropTokens(userId, stonesEq, Date.now()).catch(", 1),
        ("R112 UPDATE 分支调用就位", "ylR112JadeDrop(req.user.id, row.save_data, saveData, row.updated_at);", 1),
        ("R112 ylR112JadeDrop 总引用=定义+1 调用（首存分支零调用）", "ylR112JadeDrop(", 2),
        ("R112 ylR112RollHits 总引用=定义+2 调用", "ylR112RollHits(", 3),
        ("R112 v2810 孪生计数保持", "tickWudaoIdle(req.user.id, ylWudaoIdleDelta(prevCounters, saveData))", 2),
    ]
    ok = True
    for label, needle, exp in checks:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        print("  [%s] %-46s actual=%d expect==%d" % ("OK" if good else "FAIL", label, act, exp))
    return ok


# ============================================================ --selftest：node 语义 harness（临时文件，用完即删）

HARNESS = r"""// R-112 语义自证 harness（由 srv_patch_r112.py --selftest 生成，跑完即删）
let grantCalls: Array<{ userId: number; stonesEq: number; nowMs: number }> = [];
let rejectNext = false;
function e2Delta(a: number, b: number): number { return b > a ? Math.floor(b) - Math.floor(a) : 0; }
const ACT_TOKEN_RATE_PER_10K = 50;
async function actDropTokens(userId: number, stonesSettled: number, nowMs: number): Promise<number> {
  if (rejectNext) { rejectNext = false; return Promise.reject(new Error('stub reject')); }
  grantCalls.push({ userId, stonesEq: stonesSettled, nowMs });
  return Math.floor((stonesSettled * ACT_TOKEN_RATE_PER_10K) / 10000);
}
__BLOCK__
function fmt(ms: number): string { return new Date(ms).toISOString().slice(0, 19).replace('T', ' '); }
function mk(m: number, a: number): any { return { player: { statistics: { meditateCount: m, adventureCount: a } } }; }
async function main(): Promise<void> {
  const NOW = Date.now();
  let n = 0;
  // T1 首存（无基线）/ 空串基线：全中随机也不得发放
  Math.random = () => 0.0;
  ylR112JadeDrop(1, null, mk(5, 5), fmt(NOW - 60000));
  ylR112JadeDrop(1, '', mk(5, 5), fmt(NOW - 60000));
  console.log('T1 首存/空基线不 roll: ' + (grantCalls.length === 0 ? 'PASS' : 'FAIL'));
  n++;
  // T2 基线坏 JSON：不 roll
  ylR112JadeDrop(1, '{bad json', mk(5, 5), fmt(NOW - 60000));
  console.log('T2 坏基线不 roll: ' + (grantCalls.length === 0 ? 'PASS' : 'FAIL'));
  n++;
  // T3 Δ 为负（回档/采纳器回调）：不 roll 不扣
  ylR112JadeDrop(1, JSON.stringify(mk(100, 100)), mk(5, 5), fmt(NOW - 60000));
  console.log('T3 负Δ不发放: ' + (grantCalls.length === 0 ? 'PASS' : 'FAIL'));
  n++;
  // T4 正常 Δ 全中：Δmed=3 ⇒ hits=3 ⇒ stonesEq=600（RATE=50 ⇒ 200 石/玉，1:1）
  ylR112JadeDrop(7, JSON.stringify(mk(0, 0)), mk(3, 0), fmt(NOW - 3600000));
  const c4 = grantCalls[grantCalls.length - 1];
  console.log('T4 roll命中换算: ' + (grantCalls.length === 1 && c4.stonesEq === 600 && c4.userId === 7 ? 'PASS' : 'FAIL'));
  n++;
  // T5 全不中：Δmed=1000、rand=0.999 ⇒ 0 命中 ⇒ 不发放
  Math.random = () => 0.999;
  ylR112JadeDrop(7, JSON.stringify(mk(0, 0)), mk(1000, 0), fmt(NOW - 3600000));
  console.log('T5 未命中不发放: ' + (grantCalls.length === 1 ? 'PASS' : 'FAIL'));
  n++;
  // T6 防刷钳镜像（漂移免疫设计）：① 时间戳在未来 ⇒ realMins=max(0,负)=0 ⇒ 钳 30/30 ⇒ Δ=100000 只发 60 玉=12000 石当量；
  //   ② 24h 窗口 ⇒ cMed=432030≫100000 ⇒ 不误钳 ⇒ hits=200000 ⇒ stonesEq=40000000
  Math.random = () => 0.0;
  ylR112JadeDrop(7, JSON.stringify(mk(0, 0)), mk(100000, 100000), fmt(NOW + 3600000));
  const c6 = grantCalls[grantCalls.length - 1];
  const t6a = grantCalls.length === 2 && c6.stonesEq === 12000;
  ylR112JadeDrop(7, JSON.stringify(mk(0, 0)), mk(100000, 100000), fmt(NOW - 86400000));
  const c6b = grantCalls[grantCalls.length - 1];
  const t6b = grantCalls.length === 3 && c6b.stonesEq === 40000000;
  console.log('T6 时间钳防刷/不误钳: ' + (t6a && t6b ? 'PASS' : 'FAIL a=' + (c6 ? c6.stonesEq : 'null') + ' b=' + (c6b ? c6b.stonesEq : 'null')));
  n++;
  // T7 updated_at 缺失/坏 ⇒ fail-closed 不 roll
  ylR112JadeDrop(7, JSON.stringify(mk(0, 0)), mk(5000, 5000), null);
  ylR112JadeDrop(7, JSON.stringify(mk(0, 0)), mk(5000, 5000), 'not-a-date');
  console.log('T7 无时间基线fail-closed: ' + (grantCalls.length === 3 ? 'PASS' : 'FAIL'));
  n++;
  // T8 actDropTokens 拒绝：同步零抛出（.catch 自吞）
  rejectNext = true;
  let threw = false;
  try { ylR112JadeDrop(7, JSON.stringify(mk(0, 0)), mk(3, 0), fmt(NOW - 3600000)); } catch { threw = true; }
  console.log('T8 发放通道异常不阻塞存档: ' + (!threw ? 'PASS' : 'FAIL'));
  n++;
  // T9 常量序：打坐 < 历练（用户口径「打坐几率最低」）
  console.log('T9 打坐率<历练率: ' + (R112_JADE_MED_CHANCE < R112_JADE_ADV_CHANCE ? 'PASS' : 'FAIL'));
  n++;
  // T10 roll 函数边界：0/负数/0率 ⇒ 0
  const e10 = ylR112RollHits(0, 0.5) === 0 && ylR112RollHits(-5, 0.5) === 0 && ylR112RollHits(3, 0) === 0;
  console.log('T10 roll边界: ' + (e10 ? 'PASS' : 'FAIL'));
  n++;
  console.log('R112-SELFTEST PASS total=' + n);
}
main();
"""


def run_selftest():
    if not os.path.isfile(NODE):
        fail("node 不存在: " + NODE)
    d = tempfile.mkdtemp(prefix="r112selftest_")
    hp = os.path.join(d, "harness.ts")
    try:
        with io.open(hp, "w", encoding="utf-8", newline="\n") as f:
            f.write(HARNESS.replace("__BLOCK__", BLOCK))
        r = subprocess.run([NODE, "--experimental-strip-types", hp],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        print(r.stdout.strip())
        if r.returncode != 0:
            print((r.stderr or "")[-2000:])
            fail("--selftest node rc=%d" % r.returncode)
        out = r.stdout or ""
        if "R112-SELFTEST PASS total=10" not in out or out.count("PASS") != 11:
            fail("--selftest 断言未全绿")
        print("  [OK] --selftest 10/10（首存/坏基线/负Δ/命中换算/未命中/时间钳/fail-closed/异常不阻塞/常量序/边界）")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-112 打坐/历练掉玉环（服务端）")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        run_selftest()
        return

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 0) 幂等
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        return

    # 1) 换行符探测（锚点均单行不受影响；插入行沿用文件主导换行）
    nl = "\r\n" if "\r\n" in src[:20000] else "\n"

    # 2) 前置依赖
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:90], n, cnt, why))

    # 3) 冻结基线（打前计数）
    base = {k: src.count(k) for k in FREEZE_NEEDLES}

    # 4) 坑15 防线：NEW 必须包含 ANCHOR 原文
    for name, old, new in EDITS:
        if old not in new:
            fail("%s 的 new 不含锚点原文（坑15 防线）" % name)
    if E1_NEW == E1_OLD or E2_NEW == E2_OLD:
        fail("EDITS 存在恒等替换")

    # 5) 应用
    out = apply_edits(src, nl)
    if out == src:
        fail("补丁静默失效（打后 == 打前）")

    # 6) 打后门禁
    if not verify(out):
        fail("门禁未全绿")
    for k, pre in base.items():
        post = out.count(k)
        if post != pre:
            fail("冻结面被改 %r：%d -> %d" % (k[:60], pre, post))
    print("  [OK] 冻结面 %d 项打前==打后（含 403/require/setInterval/PRAGMA 红线）" % len(FREEZE_NEEDLES))

    # 7) 往返自证
    back = out
    e1_new = E1_ANCHOR + nl + nl + BLOCK
    e2_new = E2_ANCHOR + nl + E2_CALL
    if back.count(e2_new) != 1 or back.count(e1_new) != 1:
        fail("round-trip 前计数异常")
    back = back.replace(e2_new, E2_OLD, 1).replace(e1_new, E1_OLD, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check:
        print("  --check：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r112-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r112-", suffix=".tmp")
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
