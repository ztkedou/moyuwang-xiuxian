# -*- coding: utf-8 -*-
"""
srv_patch_numbal.py -- v28 数值重规划（服务端侧）

Reads : srv/index_v27b.ts          (线上主本，只读，NEVER modified)
Writes: srv/index_v27b_numbal.ts   (补丁产物)

本脚本只改**奖励常量**，不动任何控制流 / SQL / 路由结构。每一处都是
「同一个数值字面量，旧值 → 新值」，因此可以做到字节级可逆（round-trip）。

为什么这些常量要改（详见 数值重规划案.md 第 4 节）：
  服务端同一类「每日参与型」奖励里，一半按境界缩放（`× mult`，mult = 1.5^realmIdx），
  另一半写死为常数 —— 例如擂台胜者 `ARENA_STONE_BASE * mult`，而活跃度宝箱
  `CHEST_REWARDS` 是死数。结果：长生境玩家开满 100 活跃度宝箱只得 6,000 灵石，
  约等于 0.026 秒打坐收益（打坐 = 17676×13 ≈ 229,788 灵石/小时），奖励彻底失去感知。
  本次把这些死数抬到与「同级玩法」同一量级，并在有 `sd.player.realm` 可用的一处
  （喜宴回礼）改成真正的境界缩放。

经济钳制核对（settleSaveEconV2）—— 逐项数字见 数值重规划案.md 第 5 节：
  本次**唯一调大客户端产出**的改动是通天塔每日扫荡（100 层：修为 533,165 → 2,356,523，
  灵石 305,416 → 938,914，均为**境界无关**的定值）。服务端配额必须同步抬高，否则
  客户端 `YLSettledExp(settledExp)` 会把本地 exp 降回服务端值 ⇒ 玩家真丢修为。

  (1) 修为：约束项是 capExp 的第一项 `ECON_CLAMP_EXP_PER_MIN * mult * mins`。
      最低存档间隔 mins=0.5、最低境界 mult=1 ⇒ 旧值 2e6×1×0.5 = 1,000,000 < 2,356,523 ✗。
      抬高到 10e6 ⇒ 5,000,000（P0-1 本身余量 2.12x）⇒ capExp 的约束项回到
      「各来源配额之和」2,593,391 ≥ 2,356,523 ✓（长生档 56.95M，余量 24.2x）。
      注：`min(dTowerExp, E2_TOWER_EXP_PER_MIN*mult*mins + E2_TOWER_EXP_LUMP)`
      = 12,010,000（炼气）本身就 ≥ 2,356,523，无需改动；真正卡住的是外层 P0-1 兜底。
  (2) 灵石：通天塔灵石**没有独立计数器**，只能落在「杂项余量」
      `E2_LUMP_STONE_ALLOWANCE*ylScale` 与外层 `E2_STONE_BURST_BASE` 里。
      炼气 ylScale=0.4444、mins=0.5 时旧 capStone = min(A=537,962, B=681,525) = 537,962
      < 扫荡灵石 938,914 ✗。两个基数 1,200,000 → 6,000,000 ⇒ 炼气 capStone = min(2,671,296, 2,814,859)
      = 2,671,296 ≥ 最坏单窗口增量 ≈ 997,247（扫荡 938,914 + 满额出售 58,333）✓ 2.68x。
  (3) 其余改动（宝箱/喜宴/擂台/恩怨/结义/江湖志）最大单次增量 ≈ 62k，远低于上述余量 ✓。

用法：
  python srv_patch_numbal.py
  python srv_patch_numbal.py --src srv/index_v27b.ts --out srv/index_v27b_numbal.ts
"""
import argparse
import hashlib
import io
import os
import sys

DEFAULT_SRC = os.path.join("srv", "index_v27b.ts")
DEFAULT_OUT = os.path.join("srv", "index_v27b_numbal.ts")


# ---------------------------------------------------------------------------
# Edit table: (label, old, new, note)  —— 每处 old 必须恰好出现 1 次
# ---------------------------------------------------------------------------
EDITS = [
    (
        "chest_rewards",
        "const CHEST_REWARDS: Record<number, number> = { 25: 500, 50: 1500, 75: 3000, 100: 6000 };",
        "const CHEST_REWARDS: Record<number, number> = { 25: 2500, 50: 7500, 75: 15000, 100: 30000 };",
        "活跃度宝箱 ×5（100 档 6000→30000）；旧值在长生境 ≈ 0.026 秒打坐收益，纯噪声",
    ),
    (
        "feast_gift_const",
        "const FEAST_GIFT = 100;                               // 赴宴回礼：两位新人各得",
        "const FEAST_GIFT = 1000;                              // 赴宴回礼：两位新人各得（基数，实际再乘 1.5^境界）",
        "喜宴回礼基数 100→1000",
    ),
    (
        "feast_gift_realm_scale",
        "sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) + FEAST_GIFT;",
        "sd.player.spiritStones = (Number(sd.player.spiritStones) || 0) "
        "+ Math.floor(FEAST_GIFT * Math.pow(1.5, Math.max(0, "
        "ECON_REALM_ORDER.indexOf(String(sd.player.realm || '')))));",
        "喜宴回礼改为按境界缩放（与擂台/悬赏/江湖志同一口径 mult=1.5^realmIdx）",
    ),
    (
        "feast_guest_base",
        "const FEAST_GUEST_BASE = 50;                          // 宾客喜糖保底",
        "const FEAST_GUEST_BASE = 500;                         // 宾客喜糖保底",
        "喜糖保底 50→500",
    ),
    (
        "feast_guest_range",
        "const FEAST_GUEST_MIN = 100, FEAST_GUEST_MAX = 1000;  // 宾客随机喜糖闭区间 [100,1000]",
        "const FEAST_GUEST_MIN = 1000, FEAST_GUEST_MAX = 10000; // 宾客随机喜糖闭区间 [1000,10000]",
        "喜糖区间 [100,1000] → [1000,10000]",
    ),
    (
        "arena_stone_base",
        "const ARENA_STONE_BASE = 500;",
        "const ARENA_STONE_BASE = 3000;",
        "擂台胜者灵石基数 500→3000（已 ×1.5^境界；每日上限 3 场）",
    ),
    (
        "grudge_stone_base",
        "const GRUDGE_STONE_BASE = 2000;",
        "const GRUDGE_STONE_BASE = 8000;",
        "复仇雪耻灵石基数 2000→8000（已 ×1.5^境界）",
    ),
    (
        "sworn_cheer_base",
        "const SWORN_CHEER_BASE = 50, SWORN_BOND_STEP = 1000, SWORN_CHEER_BOND = 10;",
        "const SWORN_CHEER_BASE = 500, SWORN_BOND_STEP = 1000, SWORN_CHEER_BOND = 10;",
        "结义助威灵石基数 50→500（SWORN_BOND_STEP 已是 1000，原基数与之差 20 倍，明显脱节）",
    ),
    (
        "chronicle_mail_stones",
        "const CHRONICLE_MAIL_STONES = 1000; // 邮件附件灵石 ≥ 此值入志",
        "const CHRONICLE_MAIL_STONES = 10000; // 邮件附件灵石 ≥ 此值入志",
        "江湖志入志门槛 1000→10000（本次把宝箱/喜宴等邮件抬高后，旧门槛会让日常邮件刷满江湖志）",
    ),
    # ------------------------------------------------------------------
    # ★ 经济钳制同步抬高（铁律：客户端调大产出 ⇒ 服务端配额必须同步）
    # ------------------------------------------------------------------
    (
        "econ_clamp_exp_per_min",
        "const ECON_CLAMP_EXP_PER_MIN = 2_000_000;   // 修为每分钟基线（63 级全程 9.43 亿口径）",
        "const ECON_CLAMP_EXP_PER_MIN = 10_000_000;  // 修为每分钟基线；v28：须容纳通天塔 100 层扫荡"
        " 2,356,523（旧 533,165）。最低存档间隔 0.5min × mult=1 ⇒ 5,000,000，余量 2.12x",
        "capExp 外层兜底 2e6→10e6（旧值 1,000,000 < 新扫荡 2,356,523，会经 YLSettledExp 真丢修为）",
    ),
    (
        "stone_burst_base",
        "const E2_STONE_BURST_BASE = 1_200_000; // YL_REALM_REWARD_SCALE_V26L 原 100_000",
        "const E2_STONE_BURST_BASE = 6_000_000; // YL_REALM_REWARD_SCALE_V26L 原 100_000"
        "（v28：须容纳通天塔 100 层扫荡灵石 938,914 + 满额出售 550,000）",
        "capStone 外层兜底基数 1.2M→6M（旧值炼气档 537,963 < 新扫荡灵石 938,914）",
    ),
    (
        "lump_stone_allowance",
        "const E2_LUMP_STONE_ALLOWANCE = 1_200_000; // YL_REALM_REWARD_SCALE_V26L",
        "const E2_LUMP_STONE_ALLOWANCE = 6_000_000; // YL_REALM_REWARD_SCALE_V26L"
        "（v28：通天塔灵石无独立计数器，只能落在此项；旧值炼气档仅 533,333）",
        "capStone 杂项余量 1.2M→6M（覆盖无计数器的通天塔灵石产出）",
    ),
    (
        "tower_exp_comment",
        "const E2_TOWER_EXP_PER_MIN = 20000;    // 通天塔：100 层扫荡≈533k/天≈370/min，"
        "单层首通最高≈377k；给 ~54x 富余",
        "const E2_TOWER_EXP_PER_MIN = 20000;    // 通天塔：100 层扫荡 2,356,523/天≈1,636/min，"
        "单层首通最高 375,920；给 ~12x 富余（v28 扫荡对齐首通 30% 后刷新）",
        "仅刷新注释里的旧实测值（常量本身不变：12,010,000 配额 ≫ 2,356,523）",
    ),
]

# 必须仍然存在的既有标识（防止误伤）
KEEP_IDENTIFIERS = [
    "E2_TOWER_EXP_PER_MIN",
    "E2_TOWER_EXP_LUMP",
    "E2_EXPED_EXP_PER_MIN",
    "E2_EXPED_EXP_LUMP",
    "settleSaveEconV2",
    "ECON_REALM_ORDER",
    "RAIN_HOURLY_STONES_BASE",
    "DUNGEON_DAILY_CAP",
    "ECON_CLAMP_EXP_PER_MIN",
    "E2_STONE_BURST_BASE",
    "E2_LUMP_STONE_ALLOWANCE",
]


def fail(msg: str) -> None:
    sys.stderr.write("FAIL: " + msg + "\n")
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the v28 server-side numeric rebalance patch.")
    ap.add_argument("--src", default=DEFAULT_SRC, help="pristine baseline (default: %(default)s)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="patched product (default: %(default)s)")
    args = ap.parse_args()
    src_path, out_path = args.src, args.out

    if not os.path.isfile(src_path):
        fail("source not found: " + src_path)
    if os.path.abspath(src_path) == os.path.abspath(out_path):
        fail("--src and --out must differ (refusing to overwrite the baseline in place)")
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 0) 幂等：源必须未打过本补丁
    if "FEAST_GIFT * Math.pow(1.5" in src:
        fail("source already contains the numbal patch; refusing to double-patch")

    # 1) 锚点唯一性
    for label, old, _new, note in EDITS:
        n = src.count(old)
        if n != 1:
            fail("anchor %s occurs %d times (expected exactly 1)  note=%s" % (label, n, note))

    # 2) 既有经济常量必须在位
    for ident in KEEP_IDENTIFIERS:
        if src.count(ident) < 1:
            fail("expected identifier %r missing from source" % ident)

    # 3) 应用
    out = src
    for label, old, new, _note in EDITS:
        out = out.replace(old, new, 1)

    # 4) round-trip 字节级可逆
    rt = out
    for label, old, new, _note in reversed(EDITS):
        if rt.count(new) != 1:
            fail("round-trip: fragment %s occurs %d times in product" % (label, rt.count(new)))
        rt = rt.replace(new, old, 1)
    if rt != src:
        fail("round-trip mismatch: product is not an exact superset of source")

    with io.open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(out)

    def md5(s: str) -> str:
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    print("OK  source : %s  chars=%d bytes=%d md5=%s" % (src_path, len(src), len(src.encode("utf-8")), md5(src)))
    print("OK  product: %s  chars=%d bytes=%d md5=%s" % (out_path, len(out), len(out.encode("utf-8")), md5(out)))
    print("OK  delta  : chars=+%d bytes=+%d" % (len(out) - len(src), len(out.encode("utf-8")) - len(src.encode("utf-8"))))
    for label, old, new, note in EDITS:
        print("    ~ %-24s %s" % (label, note))
    print("OK  all anchors unique, round-trip byte-exact")


if __name__ == "__main__":
    main()
