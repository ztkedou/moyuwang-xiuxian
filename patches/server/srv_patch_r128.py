# -*- coding: utf-8 -*-
r"""
srv_patch_r128.py -- R-128 每日行乐：掷骰 10 次/日×固定 2 万注 + 灵石翻牌 10 次/日×2 万×10 档（服务端 · SRV_CHAIN 新环）

台账原文（R-128，逐字）
--------------------------------------------------------------------------
  「掷骰比大小 上限10次。灵石翻牌 10次。每次需求2W灵石，牌子数量扩充到10张，
    大概一半会亏，一半会赚钱。10个档位设置差距都比较大。」

数值依据（docs/0.9.13-design/数值表.md §10 + §14，逐字实读）
--------------------------------------------------------------------------
  掷骰（铁律②：赔率不动，只动次数与注额）：
    FUN_DICE_DAILY          3  → 10
    FUN_DICE_MIN / MAX      1000 / 20000 → 20000 / 20000（每次固定 2 万）
    FUN_DICE_PAY / TRIPLE   1.95 / 25 不动
    EV 验算：P(大)=P(小)=105/216=0.486111 ⇒ EV=0.947917（=91/96，与 0.9.12 逐位一致）；
             豹子 6/216×25=0.694444 不动。
    日经济：日注 200,000 → 期望回 189,583（回收口）。
  翻牌：
    FUN_CARD_DAILY          2  → 10
    FUN_CARD_COST           2000 → 20000
    FUN_CARD_PAYS           [4500,1200,0]（3 档）→ [0,2000,6000,10000,14000,18000,22000,28000,34000,54000]（10 档）
    EV 验算：Σ=188,000，均值/成本=18,800/20,000=0.94 ≤ 1 ✓（10 档全不等；头奖 54,000=2.7x 注额；
             赚(>2万)4 张 / 亏(<2万)6 张 ≈ 一半一半 —— R-128 原文逐字兑现）。
    日经济：日注 200,000 → 期望回 188,000。
  两玩法合计日回收 ≈ 400,000 − 377,583 = −22,417（数值表 §14「掷骰+翻牌 = −22,417 回收口」）。

改动面（全部唯一锚点，expect=1，共 6 处替换）
--------------------------------------------------------------------------
  ① FUN_DICE_DAILY 3→10            ② FUN_DICE_MIN 1000→20000（MAX 不动）
  ③ FUN_CARD_DAILY 2→10 · COST 2000→20000
  ④ FUN_CARD_PAYS 3 档→10 档       ⑤ /api/fun/card pick 校验 0..2→0..9 + 400 文案
  ⑥ 洗牌注释「三张牌」→「十张牌」（注释准确性）
  端点逻辑零改动：dice/card 两端点既有「先占次数位（UNIQUE 幂等）→ 扣款派彩 → 失败补偿 DELETE」
  顺序契约原样保留（铁律③本环适用面=不动，冻结门禁钉死）；次数上限走模板字面量
  `今日已掷/已翻 ${FUN_*_DAILY} 次` 自动适配，无硬编码次数需改。

接线约束（lead 注意）
--------------------------------------------------------------------------
  · SRV_CHAIN 追加 'srv_patch_r128.py'（常量在基座段，recon 实证无既有补丁归属）。
  · 与 srv_patch_r127.py（FUN_SIGN_* 域）锚点零交集：本环对 R-127 域与全部红线做「相对计数冻结」
    （打前统计=打后统计），两环先后序任意自洽；R-127 亦对本环域做了同款相对冻结（其脚本实证）。
  · ★ 验收件期望值变更（属 lead 领地，本环不改，移交登记）：
      - localtest/e2e_087.py E16-6 硬断言活服 `pays == [4500, 1200, 0]` → 0.9.13 须改新 10 档；
      - 根目录 _e2e_fun086.py（0.8.6 老沙盒 E2E）断言 dailyMax=2/cost=2000/pays 3 档/赌注 1000 合法/
        pick 5 → 400 —— 新规则下全部反转，若重跑该老脚本必 FAIL（历史脚本，非四道门禁成员）；
      - deploy_v28/remote_check_v2810.sh / v2811.sh 断言旧 pays —— 0.9.13 部署件（EXPECT_0913）
        须写新值：dice dailyMax=10 minBet=maxBet=20000 pay=1.95；card dailyMax=10 cost=20000
        pays=10 档。

CLI 契约（照 srv_patch_r127.py）
--------------------------------------------------------------------------
  `--src <path>` 就地原子写回该路径（写回前生成 .bak-r128-<时间戳>）；
  `--check` / `--selftest` 只校验不写。幂等：产物含 [r128fun] 或新 PAYS 数组则 SKIP（rc=0）。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 require(；不新增 res.status(403) / setInterval / PRAGMA（红线相对冻结）。
  · 业务拒绝码只用 400/409（铁律①：Xc() 把 403 当会话失效强制登出）。
  · 不改 srv/index_v28.ts 共享产物（lead 跑本环时对链产物写回）；不改任何既有 srv_patch_*.py。
  · 每处替换 expect=1；门禁全绿 + Fraction 逐位镜像验算 + round-trip 自证后才原子写回。
"""

import argparse
import io
import math
import os
import re
import shutil
import sys
import tempfile
import time
from fractions import Fraction

SRC = os.path.join("srv", "index_v28.ts")

# 幂等标记
MARK = "[r128fun]"

# ============================================================ 改动点（6 替换）

EDITS = [
    # ① 掷骰每日次数 3 → 10
    ("R128 掷骰日次数",
     "const FUN_DICE_DAILY = 3;",
     "const FUN_DICE_DAILY = 10; // R-128 [r128fun] 每日 3→10 次（掷骰上限 10 次，台账原文）"),

    # ② 掷骰注额：MIN 1000→20000（MAX 20000 不动）⇒ 每次固定 2 万；赔率 1.95/25 一字不动
    ("R128 掷骰注额",
     "const FUN_DICE_MIN = 1000, FUN_DICE_MAX = 20000;",
     "const FUN_DICE_MIN = 20000, FUN_DICE_MAX = 20000; // R-128 [r128fun] 每次固定 2 万注（MIN 1000→20000；赔率 1.95/25 不动，EV=91/96≈0.9479≤1 铁律②）"),

    # ③ 翻牌每日次数 2 → 10 · 单次成本 2000 → 20000
    ("R128 翻牌日次数与成本",
     "const FUN_CARD_DAILY = 2, FUN_CARD_COST = 2000;",
     "const FUN_CARD_DAILY = 10, FUN_CARD_COST = 20000; // R-128 [r128fun] 每日 2→10 次 · 单次成本 2000→20000"),

    # ④ 翻牌奖池：3 档 → 10 档（Σ=188,000，EV=0.94；赚 4/亏 6；头奖 54,000=2.7x）
    ("R128 翻牌奖池 10 档",
     "const FUN_CARD_PAYS = [4500, 1200, 0];",
     "const FUN_CARD_PAYS = [0, 2000, 6000, 10000, 14000, 18000, 22000, 28000, 34000, 54000]; // R-128 [r128fun] 3 档→10 档：Σ=188,000，EV=18,800/20,000=0.94≤1；赚(>2万)4 张/亏(<2万)6 张，头奖=2.7x 注额"),

    # ⑤ /api/fun/card 牌号校验 0..2 → 0..9（400 业务拒绝，非 403 —— 铁律①）
    ("R128 牌号校验 0..9",
     "if (!(pick >= 0 && pick <= 2)) return res.status(400).json({ error: '只能翻 1 / 2 / 3 号牌' });",
     "if (!(pick >= 0 && pick <= 9)) return res.status(400).json({ error: '只能翻 1 ~ 10 号牌' }); // R-128 [r128fun] 牌号 0..2→0..9（400=业务拒绝，非 403）"),

    # ⑥ 洗牌注释同步（准确性，避免后人误读牌数）
    ("R128 洗牌注释",
     "// 洗牌：奖项等概率落三张牌",
     "// 洗牌：奖项等概率落十张牌（R-128 [r128fun] 3→10 档）"),
]

# ============================================================ 前置依赖（只读自证，不改）
REQUIRES = [
    # 本环 6 个旧锚点必须在位且唯一
    ("const FUN_DICE_DAILY = 3;", 1, "掷骰日次数旧值必须在位且唯一"),
    ("const FUN_DICE_MIN = 1000, FUN_DICE_MAX = 20000;", 1, "掷骰注额旧值必须在位且唯一"),
    ("const FUN_CARD_DAILY = 2, FUN_CARD_COST = 2000;", 1, "翻牌次数/成本旧值必须在位且唯一"),
    ("const FUN_CARD_PAYS = [4500, 1200, 0];", 1, "翻牌奖池旧值必须在位且唯一"),
    ("if (!(pick >= 0 && pick <= 2)) return res.status(400).json({ error: '只能翻 1 / 2 / 3 号牌' });",
     1, "牌号校验旧行必须在位且唯一"),
    ("// 洗牌：奖项等概率落三张牌", 1, "洗牌注释必须在位且唯一"),
    # 本环不动但语义依赖的形态（绝对在位）
    ("const FUN_DICE_PAY = 1.95, FUN_DICE_TRIPLE_PAY = 25;", 1, "掷骰赔率行必须在位（本环不动=铁律②）"),
    ("app.post('/api/fun/dice'", 1, "掷骰端点注册必须在位（端点逻辑零改动）"),
    ("app.post('/api/fun/card'", 1, "翻牌端点注册必须在位（端点逻辑零改动）"),
    "const deck = FUN_CARD_PAYS.slice();",
    ("const payout = Math.max(0, Math.floor(Number(deck[pick]) || 0));", 1,
     "翻牌派彩行必须在位（洗牌后按牌号取奖，逻辑不动）"),
    ("card: { left: Math.max(0, FUN_CARD_DAILY - (Number(cardRow?.c) || 0)), dailyMax: FUN_CARD_DAILY, cost: FUN_CARD_COST, pays: FUN_CARD_PAYS },",
     1, "teahouse/today 下发的 card 配置行必须在位（客户端随服务端配置渲染，两端同源）"),
    ("minBet: FUN_DICE_MIN, maxBet: FUN_DICE_MAX, pay: FUN_DICE_PAY, triplePay: FUN_DICE_TRIPLE_PAY,",
     1, "teahouse/today 下发的 dice 配置行必须在位（客户端随服务端配置渲染，两端同源）"),
]
# 元组长度归一（3 元组 / 2 元组都收）
_REQ = []
for item in REQUIRES:
    if isinstance(item, str):
        _REQ.append((item, 1, "必须在位"))
    else:
        _REQ.append(item)
REQUIRES = _REQ

# ============================================================ 冻结基线（相对计数：打前 == 打后，链上任意顺序自洽）
BASE_NEEDLES = [
    # 红线（不得新增）
    "res.status(403", "require(", "setInterval(", "PRAGMA",
    # R-127 域（FUN_SIGN_*，相邻需求锚点零交集；先打后打均自洽）
    "const FUN_SIGN_BASE = 500;",
    "FUN_SIGN_BASE = 2000",
    "const FUN_SIGN_DAILY = 1;",
    "{ key: 'ss', name: '上上签'",
    "{ key: 's', name: '上签'",
    "{ key: 'm', name: '中签'",
    "{ key: 'x', name: '下签'",
    # 本域结构冻结（次数上限走模板字面量，自动适配，不得手改）
    "今日已掷 ${FUN_DICE_DAILY} 次，明日再来",
    "今日已翻 ${FUN_CARD_DAILY} 次，明日再来",
    "if (!Number.isInteger(bet) || bet < FUN_DICE_MIN || bet > FUN_DICE_MAX)",
    "// ★ 顺序契约（全或无）：先占次数位 → 再扣成本派彩。",
    # 茶馆域（R-053/R-029 冻结面，本环不碰）
    "app.post('/api/teahouse/bet'",
]

# ============================================================ 设计对照（数值表 §10 逐项）
DICE = {"daily": 10, "min": 20000, "max": 20000, "pay": "1.95", "triple": "25"}
CARD = {"daily": 10, "cost": 20000}
PAYS_NEW = [0, 2000, 6000, 10000, 14000, 18000, 22000, 28000, 34000, 54000]


def mirror_check(out: str):
    """打补丁后的产物文本提取常量，Fraction 逐位镜像验算（对照数值表 §10）。"""
    lines = []
    ok = True

    def grab(pat, label, want):
        nonlocal ok
        m = re.search(pat, out)
        if not m:
            ok = False
            lines.append("  [FAIL] %s 提取失败（%r）" % (label, pat))
            return None
        return m

    m = grab(r"const FUN_DICE_DAILY = (\d+);", "FUN_DICE_DAILY", 10)
    daily = int(m.group(1)) if m else -1
    good = daily == DICE["daily"]
    ok = ok and good
    lines.append("  [%s] FUN_DICE_DAILY = %d（设计 10）" % ("OK" if good else "FAIL", daily))

    m = grab(r"const FUN_DICE_MIN = (\d+), FUN_DICE_MAX = (\d+);", "FUN_DICE_MIN/MAX", None)
    dmin, dmax = (int(m.group(1)), int(m.group(2))) if m else (-1, -1)
    good = dmin == DICE["min"] and dmax == DICE["max"]
    ok = ok and good
    lines.append("  [%s] FUN_DICE_MIN/MAX = %d/%d（设计 20000/20000，每次固定 2 万）"
                 % ("OK" if good else "FAIL", dmin, dmax))

    m = grab(r"const FUN_DICE_PAY = ([\d.]+), FUN_DICE_TRIPLE_PAY = ([\d.]+);", "FUN_DICE_PAY/TRIPLE", None)
    pay, tpay = (m.group(1), m.group(2)) if m else ("?", "?")
    good = Fraction(pay) == Fraction(DICE["pay"]) and Fraction(tpay) == Fraction(DICE["triple"])
    ok = ok and good
    lines.append("  [%s] FUN_DICE_PAY/TRIPLE_PAY = %s/%s（设计 1.95/25 不动=铁律②）"
                 % ("OK" if good else "FAIL", pay, tpay))

    m = grab(r"const FUN_CARD_DAILY = (\d+), FUN_CARD_COST = (\d+);", "FUN_CARD_DAILY/COST", None)
    cdaily, ccost = (int(m.group(1)), int(m.group(2))) if m else (-1, -1)
    good = cdaily == CARD["daily"] and ccost == CARD["cost"]
    ok = ok and good
    lines.append("  [%s] FUN_CARD_DAILY/COST = %d/%d（设计 10/20000）" % ("OK" if good else "FAIL", cdaily, ccost))

    m = grab(r"const FUN_CARD_PAYS = \[([^\]]+)\];", "FUN_CARD_PAYS", None)
    pays = [int(x) for x in m.group(1).split(",")] if m else []
    good = pays == PAYS_NEW
    ok = ok and good
    lines.append("  [%s] FUN_CARD_PAYS = %s（设计 10 档逐位）" % ("OK" if good else "FAIL", pays))

    # ---- 掷骰 EV（赔率未动自证：P(大)=P(小)=105/216，豹子 6/216）----
    ev_big = Fraction(105, 216) * Fraction(pay)
    good = ev_big == Fraction(91, 96)
    ok = ok and good
    lines.append("  [%s] 掷骰 大/小 EV = %s ≈ 0.947917（=91/96，与 0.9.12 逐位一致）≤1"
                 % ("OK" if good else "FAIL", ev_big))
    ev_tri = Fraction(6, 216) * Fraction(tpay)
    good = ev_tri == Fraction(25, 36)
    ok = ok and good
    lines.append("  [%s] 掷骰 豹子 EV = %s ≈ 0.694444 ≤1" % ("OK" if good else "FAIL", ev_tri))

    # ---- 翻牌 EV / 档位结构 ----
    total = sum(pays)
    mean = Fraction(total, len(pays))
    ev_card = mean / ccost
    good = total == 188000 and ev_card == Fraction(94, 100)
    ok = ok and good
    lines.append("  [%s] 翻牌 Σpays = %d，EV = %s×1/%d = %s ≤1（设计 0.94）"
                 % ("OK" if good else "FAIL", total, mean, ccost, ev_card))
    good = len(set(pays)) == 10
    ok = ok and good
    lines.append("  [%s] 10 档全不等（%d 个互异值）" % ("OK" if good else "FAIL", len(set(pays))))
    win = [x for x in pays if x > ccost]
    lose = [x for x in pays if x < ccost]
    good = len(win) == 4 and len(lose) == 6
    ok = ok and good
    lines.append("  [%s] 赚(>2万)=%d 张 %s / 亏(<2万)=%d 张 %s（≈一半一半，R-128 原文）"
                 % ("OK" if good else "FAIL", len(win), win, len(lose), lose))
    good = max(pays) == 54000 and Fraction(max(pays), ccost) == Fraction(27, 10)
    ok = ok and good
    lines.append("  [%s] 头奖 %d = %s× 注额（设计 2.7x，档差最大）"
                 % ("OK" if good else "FAIL", max(pays), Fraction(max(pays), ccost)))

    # ---- 日经济（数值表 §10/§14）----
    dice_in = Fraction(DICE["daily"] * DICE["min"])
    dice_back = dice_in * ev_big
    card_in = Fraction(CARD["daily"] * CARD["cost"])
    card_back = Fraction(total)
    net = (dice_back + card_back) - (dice_in + card_in)
    good = dice_back == Fraction(568750, 3) and net == Fraction(-67250, 3)
    ok = ok and good
    lines.append("  [%s] 日账：掷骰注 %s → 回 %s ≈189,583；翻牌注 %s → 回 %s=188,000；净回收 %s ≈ −22,417（§14）"
                 % ("OK" if good else "FAIL", dice_in, dice_back, card_in, card_back, float(net)))

    # ---- 牌号校验 0..9（400 文案）----
    good = ("pick >= 0 && pick <= 9" in out) and ("只能翻 1 ~ 10 号牌" in out)
    ok = ok and good
    lines.append("  [%s] /api/fun/card 牌号校验 0..9 + 400 文案「只能翻 1 ~ 10 号牌」在位" % ("OK" if good else "FAIL"))
    return ok, lines


def fail(msg):
    print("[FAIL] " + msg)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="R-128 掷骰 10 次×2 万注 + 翻牌 10 次×2 万×10 档环（服务端）")
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
    if MARK in src or "FUN_CARD_PAYS = [0, 2000, 6000" in src:
        print("[SKIP] source looks already patched（已含 %s / 新奖池）" % MARK)
        return

    # 2) 依赖（绝对在位）
    for item in REQUIRES:
        needle, cnt, why = item
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

    # 4) 冻结基线（相对计数快照）
    base = {k: src.count(k) for k in BASE_NEEDLES}

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    gates = [
        ("R128 幂等标记就位(x6)", MARK, 6),
        ("R128 掷骰日次数新值", "const FUN_DICE_DAILY = 10;", 1),
        ("R128 掷骰注额新值", "const FUN_DICE_MIN = 20000, FUN_DICE_MAX = 20000;", 1),
        ("R128 翻牌次数成本新值", "const FUN_CARD_DAILY = 10, FUN_CARD_COST = 20000;", 1),
        ("R128 翻牌奖池新值", "const FUN_CARD_PAYS = [0, 2000, 6000, 10000, 14000, 18000, 22000, 28000, 34000, 54000];", 1),
        ("R128 牌号校验新值", "if (!(pick >= 0 && pick <= 9))", 1),
        ("R128 400 文案新值", "'只能翻 1 ~ 10 号牌'", 1),
        ("R128 旧掷骰日次数清零", "const FUN_DICE_DAILY = 3;", 0),
        ("R128 旧掷骰注额清零", "const FUN_DICE_MIN = 1000", 0),
        ("R128 旧翻牌次数成本清零", "const FUN_CARD_DAILY = 2, FUN_CARD_COST = 2000;", 0),
        ("R128 旧奖池清零", "const FUN_CARD_PAYS = [4500, 1200, 0];", 0),
        ("R128 旧牌号校验清零", "if (!(pick >= 0 && pick <= 2))", 0),
        ("R128 旧 400 文案清零", "'只能翻 1 / 2 / 3 号牌'", 0),
        ("R128 旧洗牌注释清零", "// 洗牌：奖项等概率落三张牌", 0),
    ]
    for needle in BASE_NEEDLES:
        label = "冻结 " + needle[:34].replace("\n", " ")
        gates.append((label, needle, base[needle]))
    gates += [
        ("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]),
        ("红线 未新增 require(", "require(", base["require("]),
        ("红线 未新增 setInterval", "setInterval(", base["setInterval("]),
        ("红线 未新增 PRAGMA", "PRAGMA", base["PRAGMA"]),
    ]
    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        if not good:
            print("  [FAIL] %-46s actual=%d expect==%d" % (label, act, exp))

    # 7) 语义镜像验算（数值表 §10 逐项 Fraction）
    sem_ok, sem_lines = mirror_check(out)
    ok = ok and sem_ok
    for l in sem_lines:
        print(l)
    print("  [%s] %-46s" % ("OK" if sem_ok else "FAIL", "R128 语义镜像验算(掷骰EV/翻牌EV/档位/日账)"))

    if not ok:
        fail("门禁未全绿，未写回")

    # 8) 往返自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 9) 改前 .bak + 原子写回
    bak = "%s.bak-r128-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r128fun-", suffix=".tmp")
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
