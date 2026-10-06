# -*- coding: utf-8 -*-
r"""
srv_patch_r168.py -- R-168 灵田数值重构（服务端 · SRV_CHAIN 第 73 环）+ R-169 结论留档

  ★ 环号说明：第 70 环 = R-160（srv_patch_r160.py）、第 71 环 = R-163（srv_patch_r163.py）、
    第 72 环 = R-165（srv_patch_r165.py）⇒ 本环顺延 **第 73 环**。锚点落在 farmCropDefs()
    内 R-163 覆盖块之后、`return out;` 之前（与 r160/r165 锚区零交集），链序无硬约束。

台账原文（R-168 / R-169，逐字）
--------------------------------------------------------------------------
  R-168「仙务·灵田 数据还是设计的不对，按下面的要求重构：
    1.纯卖钱草，盈利的灵石收益跟时长有直接关系。服用增加修为极少。
    2.综合草 卖灵石能回本且有部分收益但不是很高。服用增加的修为跟购买时的灵石数相关，不要太高。
    3.修为草变卖现在的灵石数量合适。服用时修为跟时长有关，现在3000灵石那个档位150分钟那个，
      变更1W5修为。以这个为基础设计其他的，越高档位扩大的倍数也要增加，因为高段位需求的升级
      修为较高，低段位升级需求的修为较少。不能让低段位升级太快，也不能让高段位升级过慢。」
  R-169「灵田怎么还有这种缺失问题，之前不是让完全修复吗：
      `12:54:16 ⚠️ 灵草【血参草】的配置信息缺失，已按 1,200 灵石折算回收（每个 300 灵石）。`」

改前取证（srv/index_v28.ts 字符级实测）
--------------------------------------------------------------------------
  · farmCropDefs()（@5802）按「品阶基准 FARM_CROP_BASE × 类型系数 FARM_CROP_KIND」合成 20 新种，
    再经 R-047 双出口倍率、最后被 **R163_FARM_TABLE**（@5849-5874）覆写 seed/stones/exp 三字段。
  · R-163 定档（本轮改前）：
      时长(min) = 来自 BASE.min × KIND.min，下限 120：
        sell 120/180/300/480/720 · cult 150/225/375/600/900 · mix 180/270/450/720/1080
      变卖回收率：sell 1.200→1.025（净赚/小时 300→100，递减）· mix 0.50（巨亏）·
                  cult 0.25 · rare 0.40
      服用修为：sell 8000/12000/20000/32000/48000（明显过多）·
                mix 36000/54000/90000/144000/216000（= 0.9×cult）·
                cult 40000/64000/100000/160000/240000 · rare 60000/96000/96000/144000/144000
  · 病根（用户三条）：① sell 净赚/小时随品阶衰减 3 倍（非「与时长成正比」）；
    ② mix 变卖只回本 0.50（「回本」不成立）；③ cult 修为过低（神品 240000）且低段偏高
    （凡品 40000）⇒ 低段太快、高段太慢。

R-168 数值重构（全部在 farmCropDefs 尾部插入 R168_FARM_TABLE 覆写；见下方 _TABLE_LINES）
--------------------------------------------------------------------------
  ① 纯卖钱草 sell —— 净赚 ∝ 时长：
     种子价不变 3000/6000/12000/24000/48000；时长 2/3/5/8/12 h；
     净赚/小时 **恒定 300 灵石/h** ⇒ 净赚 = 600/900/1500/2400/3600 ⇒
     变卖 = 3600/6900/13500/26400/51600 ⇒ 回收率 1.200/1.150/1.125/1.100/1.075（逐档收敛）。
     服用修为改「极少」：**200 exp/h ∝ 时长** ⇒ 400/600/1000/1600/2400
     （仅同阶 cult 的 2.7%→0.08%，较改前 8000~48000 大幅收敛）。
  ② 综合草 mix —— 回本 + 小幅收益；修为与「购买价」相关：
     变卖 = 种子 ×1.10 ⇒ 3300/6600/13200/26400/52800（净赚 = 10% 种子价，不再是 0.50 巨亏）。
     服用修为 = 种子 ×3 ⇒ 9000/18000/36000/72000/144000（「跟购买时灵石数相关、不要太高」，
     且**必 < 同阶 cult**：9000<15000 / 18000<45000 / 36000<150000 / 72000<600000 / 144000<3000000）。
     FARM_CROP_ATTRS（基础属性加成）**一行未动**。
  ③ 纯修为草 cult —— 变卖不变、修为重定档：
     变卖灵石**逐字保持 R-163**（用户：现在合适）750/1500/3000/6000/12000。
     服用修为 = **15000 / 45000 / 150000 / 600000 / 3000000**
     （用户锚：凡品 3000 灵石/150min 档 = 15000；档间倍率 3 → 3.33 → 4 → 5 **递增**）。
     ★ 校准依据（境界升级修为表 TRIB_REALM_BASES @4850 + realmMaxExp @4861：
       maxExp(境界, lv) = floor(maxExpBase × (1 + (lv−1)×0.24))，每境界 9 层）：
         凡品 → 炼气期(Lv1 60,000)  : 15000/60000    = 25.0%
         灵品 → 筑基期(Lv1 390,000) : 45000/390000   = 11.5%
         玄品 → 金丹期(Lv1 1,521,000): 150000/1521000 =  9.9%
         仙品 → 元婴期(Lv1 6,592,000): 600000/6592000 =  9.1%
         神品 → 化神期(Lv1 26,775,000): 3000000/26775000 = 11.2%
       ⇒ 一株修为草 ≈ 代表境界「升 1 层所需修为槽」的 9~25%：低段 25% 不致秒升、
         高段 ≈11% 不致龟速。档间倍率递增正是为追平境界修为 ≈ ×4/境 的膨胀。
     相对 R-163：凡 40000→15000(降) · 灵 64000→45000(降) · 玄 100000→150000(升) ·
                 仙 160000→600000(升) · 神 240000→3000000(大升) ⇒ 低段压、高段抬，方向自洽。
  ④ 稀有草 rare —— 用户未提，**逐字保持 R-163 不动**：
     变卖 4800/9600/9600/19200/19200 · 修为 60000/96000/96000/144000/144000。
     与新版 cult 无冲突（rare 修为 60000/96000/144000 全部 < 同阶 cult 150000/600000/3000000）。
     ⚠ 观察（非规则冲突，供策划取舍）：神品 mix 修为 144000 恰等于神品 rare 修为 144000
       （两者种子价同为 48000）。二者仍以「mix 变卖 52800 ≫ rare 19200」「rare 供百分比属性」
       区分价值，故本轮不改；如需拉开，建议后续为 rare 单独提修为（会破坏 ④ 的「不动」约束）。
  ⑤ 经济红线复算（sell 组永不印钞，R-163 口径：满配 ×1.21 后 ≤ 种子 ×1.5）：
     · 最高档 sell（神品 神藏金参，seed 48000，12h）：变卖 51600 ⇒
         **净赚/小时 = (51600−48000)/12 = 300 灵石/h**；
         **回收率 = 51600/48000 = 1.075 ⇒ 满配 1.075×1.21 = 1.30075 ≤ 1.5 ✓**
     · 全表最高回收率档（凡品 灵谷穗 3600/3000 = 1.200）⇒ 满配 1.200×1.21 = **1.452 ≤ 1.5 ✓**
     · sell 净赚/小时全档恒 300（不随品阶暴涨）✓

R-169 根因结论（★ 结论：非服务端问题，本轮**不改服务端源码**）
--------------------------------------------------------------------------
  出处定位（grep 证据）：
    · `grep -c "配置信息缺失" srv/index_v28.ts` = **0**；`grep -rn "折算回收" srv/` = 0。
    · 唯一命中在 **客户端 bundle**：`build/assets/index-*.js` 内
        `⚠️ 灵草【${N.herbName}】的配置信息缺失，已按 ${__sv.toLocaleString()} 灵石折算回收（每个 300 灵石）。`
      其上下文为洞府灵草收获分支（读 `N.harvestTime/N.herbName/N.herbId/N.quantity` 与
      `grotto.plantedHerbs` / `grotto.herbarium`），命中 `wn` 三级查找全落空时 `Math.max(100,quantity*300)`
      折算回收 —— 与**灵田（farmCropDefs / FARM_CROPS_NEW）无关**，是两套系统。
    · `wn` = 客户端**内嵌**草药总表（20 草 + 3 阵改造），含 `血参`（id `blood-ginseng`），**不含** `血参草`；
      当前别名表仅 `{"灵紫猴草":"紫猴花"}`（见 patches/client/yl_v2810f_ext.py 0.8.10 需求 6b）。
    · `血参草` 的真实归属 = **玩家存档**：`localtest/_r025_all_players.json` 玩家 1 的
      `grotto.herbarium` 含 `"血参草"`（同列还有 灵凤羽草/凤羽草/星辰草/凝神草/天灵草/灵止血草/
      灵回气草 等一批**改名前的旧名**）。`grep -rn 血参草 srv/` = 0（`srv/game-dicts.json` 的
      `herbs` 20 条亦无；该 json 仅被 GM 工具加载，**不 serve 给玩家**）。
  ⇒ **根因：旧存档带着「改名前的灵草名」回来收菜**（与 0.8.10 需求 6b 的 `灵紫猴草` 同类；
    先例 = R-158 的 `16430_aqjh`）。**不是服务端配置缺失**，服务端亦无任何洞府草药表 / herbarium /
    plantedHerbs 处理 / 该兜底文案 ⇒ 在服务端补 FARM_CROPS_NEW / R163_FARM_TABLE **无效且有害**
    （会把 血参草 变成 `/api/farm/status` 里可播种的**灵田**品种，串系统）。
  修法建议（交客户端/数据侧，**不在本环**）：
    1. ★首选（最小侵入，照既有 `yl_v2810f_ext.py` 做法）：在 `__halias` 增补
       `"\u8840\u53c2\u8349":"\u8840\u53c2"`（血参草 → 血参）⇒ 旧档收菜走正常路径、进背包为真实道具。
       （现名对应关系建议策划确认；若 `血参草` 实为已删除的独立品种，则改为在 `wn` 补条目。）
    2. 或清洗存量 `grotto.plantedHerbs[].herbName` / `grotto.herbarium` 中的旧名（破坏性迁移，不推荐）。
    3. 不建议在 `wn` 新增 `血参草` 品种（会把只该存在于历史存档的名字变成正式品种）。
    ⚠ 同类旧名成批存在（灵凤羽草/凤羽草/星辰草/凝神草/天灵草/灵止血草/灵回气草/紫猴草…），
      建议一次性把 `__halias` 补齐，避免逐条冒烟。

CLI 契约（照 srv_patch_r165.py / srv_patch_r163.py）
--------------------------------------------------------------------------
  --src <path> 就地原子写回（写回前生成 .bak-r168-<时间戳>）；
  --check / --selftest 只校验不写。幂等：产物含 [r168farm] 则 SKIP（直接返回 rc=0，不写盘）。
  退出码 0 成功 / 1 失败 / 2 用法错。

工程约束（TS 源码，将被 node --experimental-strip-types 直跑）
--------------------------------------------------------------------------
  · ESM ⇒ 不新增 require(；不新增 res.status(403)；不新增 setInterval / PRAGMA。
  · 不改任何既有 srv_patch_*.py；不改 srv/index_v28.ts 本体（由 chain_build 落盘）。
  · 锚点纯 ASCII；替换 expect=1；门禁全绿 + round-trip 自证后才原子写回。
  · 位置选择说明：**在 R-163 覆盖块之后再插一张 R168_FARM_TABLE 覆写**（而非原地改 R163_FARM_TABLE），
    因为 R163_FARM_TABLE 的每一行都带中文尾注 ⇒ 原地改需非 ASCII 锚点，违反「锚点纯 ASCII」契约，
    且无法同步订正已失效的中文段注；再插一表与 R-163 覆盖 R-047/R-129 的既有链式做法完全一致，
    R163_FARM_TABLE 保留为历史档、最终值以本表为准。
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
MARK = "[r168farm]"

# ============================================================ 改动点（1 插入）

# 锚点：R-163 覆盖块尾部（纯 ASCII，count==1）
ANCHOR_OLD = (
    "    out[_k163] = Object.assign({}, _d163, { seed: _v163[0], stones: _v163[1], exp: _v163[2] });\n"
    "  }\n"
    "  return out;\n"
)

# [seed, 变卖灵石, 服用修为]（逐档推导见文件头 ①~④；时长注释为核对用）
_TABLE_LINES = [
    "    // ① 纯卖钱草 sell：净赚 ∝ 时长（净赚/小时 恒定 300）⇒ 收益与时长直接挂钩；",
    "    //    服用修为「极少」（200 exp/h ∝ 时长，仅同阶 cult 的 2.7%→0.08%）。",
    "    linggusi:        [3000,  3600,  400],     // 凡品 灵谷穗  2h  净赚 600",
    "    ziwenlingdao:    [6000,  6900,  600],     // 灵品 紫纹灵稻 3h  净赚 900",
    "    jinsuiteng:      [12000, 13500, 1000],    // 玄品 金髓藤  5h  净赚 1500",
    "    xianyulian:      [24000, 26400, 1600],    // 仙品 仙玉莲  8h  净赚 2400",
    "    shencangjinshen: [48000, 51600, 2400],    // 神品 神藏金参 12h 净赚 3600",
    "    // ② 综合草 mix：变卖 = 种子 ×1.10（回本 + 10% 小幅收益，非改前 0.50 巨亏）；",
    "    //    服用修为 = 种子 ×3（跟购买灵石数相关、必 < 同阶 cult）；基础属性加成不动。",
    "    peiyuancao:      [3000,  3300,  9000],    // 凡品 培元草",
    "    zhuangguhua:     [6000,  6600,  18000],   // 灵品 壮骨花",
    "    bailianzhi:      [12000, 13200, 36000],   // 玄品 百炼芝",
    "    jiugiaoxuanzhi:  [24000, 26400, 72000],   // 仙品 九窍玄芝",
    "    wanxianghua:     [48000, 52800, 144000],  // 神品 万象花",
    "    // ③ 纯修为草 cult：变卖灵石逐字不变（用户：合适）；修为重定档，凡品 15000 起、",
    "    //    档间倍率 3→3.33→4→5 递增（追平境界修为 ≈ ×4/境 的膨胀，防高段过慢）。",
    "    yinqimiao:       [3000,  750,   15000],    // 凡品 引气苗 150min",
    "    ningyuanzhi:     [6000,  1500,  45000],    // 灵品 凝元芝 225min",
    "    xuanyuanguo:     [12000, 3000,  150000],   // 玄品 玄元果 375min",
    "    taiqingguo:      [24000, 6000,  600000],   // 仙品 太清果 600min",
    "    hunyuandaoguo:   [48000, 12000, 3000000],  // 神品 混元道果 900min",
    "    // ④ 稀有草 rare：用户未提，逐字保持 R-163 不动（修为 < 同阶 cult，无冲突）。",
    "    jifengye:        [12000, 4800,  60000],    // 玄品 疾风叶",
    "    xuepohua:        [24000, 9600,  96000],    // 仙品 血魄花",
    "    xingyunhua:      [24000, 9600,  96000],    // 仙品 星陨花",
    "    dongxuanhua:     [48000, 19200, 144000],   // 神品 洞玄花",
    "    bumieteng:       [48000, 19200, 144000],   // 神品 不灭藤",
]

ANCHOR_NEW = (
    "    out[_k163] = Object.assign({}, _d163, { seed: _v163[0], stones: _v163[1], exp: _v163[2] });\n"
    "  }\n"
    "  // [r168farm] R-168 灵田数值重构（在 R-163 覆盖之后再覆写一遍 seed/stones/exp；\n"
    "  //   R163_FARM_TABLE 保留为历史档，最终值以本表为准）。\n"
    "  //   ① sell 净赚 ∝ 时长（恒定 300/h）、服用修为极少（200/h）；\n"
    "  //   ② mix 变卖 = 种子×1.10（回本+10%）、修为 = 种子×3（< 同阶 cult）；\n"
    "  //   ③ cult 变卖不变、修为 15000/45000/150000/600000/3000000（倍率 3→3.33→4→5 递增）；\n"
    "  //   ④ rare 不动；⑤ sell 满配回收率 ≤ 1.452 < 1.5（永不印钞）。\n"
    "  //   校准与红线复算详见 srv_patch_r168.py 文件头。\n"
    "  const R168_FARM_TABLE: Record<string, [number, number, number]> = {\n"
    + "\n".join(_TABLE_LINES) + "\n"
    "  };\n"
    "  for (const _k168 of Object.keys(R168_FARM_TABLE)) {\n"
    "    const _d168 = out[_k168];\n"
    "    if (!_d168) continue;\n"
    "    const _v168 = R168_FARM_TABLE[_k168];\n"
    "    out[_k168] = Object.assign({}, _d168, { seed: _v168[0], stones: _v168[1], exp: _v168[2] });\n"
    "  }\n"
    "  return out;\n"
)

EDITS = [
    ("R168 灵田数值覆盖块（farmCropDefs 尾部、R163 覆盖块之后插入）", ANCHOR_OLD, ANCHOR_NEW),
]

# 20 新种 key → 期望的 [seed, stones, exp]（用于逐档门禁，杜绝格式漂移）
EXPECT_TABLE = {
    'linggusi':        [3000,  3600,  400],
    'ziwenlingdao':    [6000,  6900,  600],
    'jinsuiteng':      [12000, 13500, 1000],
    'xianyulian':      [24000, 26400, 1600],
    'shencangjinshen': [48000, 51600, 2400],
    'peiyuancao':      [3000,  3300,  9000],
    'zhuangguhua':     [6000,  6600,  18000],
    'bailianzhi':      [12000, 13200, 36000],
    'jiugiaoxuanzhi':  [24000, 26400, 72000],
    'wanxianghua':     [48000, 52800, 144000],
    'yinqimiao':       [3000,  750,   15000],
    'ningyuanzhi':     [6000,  1500,  45000],
    'xuanyuanguo':     [12000, 3000,  150000],
    'taiqingguo':      [24000, 6000,  600000],
    'hunyuandaoguo':   [48000, 12000, 3000000],
    'jifengye':        [12000, 4800,  60000],
    'xuepohua':        [24000, 9600,  96000],
    'xingyunhua':      [24000, 9600,  96000],
    'dongxuanhua':     [48000, 19200, 144000],
    'bumieteng':       [48000, 19200, 144000],
}
# 每线时长（分钟，来自生成器 BASE.min × KIND.min，下限 120；仅用于红线复算断言）
EXPECT_MIN = {
    'linggusi': 120, 'ziwenlingdao': 180, 'jinsuiteng': 300, 'xianyulian': 480, 'shencangjinshen': 720,
    'peiyuancao': 180, 'zhuangguhua': 270, 'bailianzhi': 450, 'jiugiaoxuanzhi': 720, 'wanxianghua': 1080,
    'yinqimiao': 150, 'ningyuanzhi': 225, 'xuanyuanguo': 375, 'taiqingguo': 600, 'hunyuandaoguo': 900,
    'jifengye': 600, 'xuepohua': 960, 'xingyunhua': 960, 'dongxuanhua': 1440, 'bumieteng': 1440,
}

NEW_TABLE_HEAD = "const R168_FARM_TABLE: Record<string, [number, number, number]> = {"


def _entry_needle(key: str) -> str:
    """返回该 key 在 ANCHOR_NEW 内**逐字**出现的那一行（用于逐档门禁）。"""
    for ln in _TABLE_LINES:
        if ln.lstrip().startswith(key + ":"):
            return ln.strip()
    raise KeyError(key)


_ENTRY_RE = None


def _parse_entry(key: str):
    """从 _TABLE_LINES 里解析该 key 的 [seed, stones, exp]（容忍对齐空格）。"""
    global _ENTRY_RE
    if _ENTRY_RE is None:
        import re as _re
        _ENTRY_RE = _re.compile(r"^([A-Za-z0-9_]+):\s*\[(\d+),\s*(\d+),\s*(\d+)\],")
    for ln in _TABLE_LINES:
        m = _ENTRY_RE.match(ln.strip())
        if m and m.group(1) == key:
            return int(m.group(2)), int(m.group(3)), int(m.group(4))
    raise KeyError(key)


def _mirror_check() -> None:
    """镜像自证：EXPECT_TABLE / EXPECT_MIN 与 ANCHOR_NEW 逐字一致（防手抄漂移）。"""
    for key, (s, st, e) in EXPECT_TABLE.items():
        if _parse_entry(key) != (s, st, e):
            raise AssertionError("EXPECT_TABLE 与 ANCHOR_NEW 不一致：%s" % key)
    # 红线复算（sell 全档）
    for key in ('linggusi', 'ziwenlingdao', 'jinsuiteng', 'xianyulian', 'shencangjinshen'):
        s, st, _ = EXPECT_TABLE[key]
        mins = EXPECT_MIN[key]
        assert st >= s, "sell 净赚 < 0：%s" % key
        assert abs((st - s) / (mins / 60.0) - 300) < 1e-6, "sell 净赚/小时 != 300：%s" % key
        assert st / s * 1.21 <= 1.5 + 1e-9, "sell 满配回收率 > 1.5：%s" % key
    # mix：回本 + 修为 < 同阶 cult
    _cult = [EXPECT_TABLE[k][2] for k in
             ('yinqimiao', 'ningyuanzhi', 'xuanyuanguo', 'taiqingguo', 'hunyuandaoguo')]
    for i, key in enumerate(('peiyuancao', 'zhuangguhua', 'bailianzhi', 'jiugiaoxuanzhi', 'wanxianghua')):
        s, st, e = EXPECT_TABLE[key]
        assert st >= s, "mix 未回本：%s" % key
        assert 3 * s <= e <= 5 * s, "mix 修为不在 seed×3~5 内：%s" % key
        assert e < _cult[i], "mix 修为 !< 同阶 cult：%s" % key
    # cult：凡品锚 15000 + 倍率递增
    _c = _cult
    assert _c[0] == 15000, "cult 凡品锚 != 15000"
    _m = [_c[i] / _c[i - 1] for i in range(1, len(_c))]
    assert all(_m[i] > _m[i - 1] for i in range(1, len(_m))), "cult 档间倍率非递增：%r" % _m
    # rare：与 cult 不冲突（< 同阶）
    for i, key in enumerate(('jifengye', 'xuepohua', 'dongxuanhua')):
        assert EXPECT_TABLE[key][2] < _cult[2 + i], "rare 修为 !< 同阶 cult：%s" % key


_mirror_check()


# ============================================================ 依赖（绝对在位，锚点纯 ASCII）

REQUIRES = [
    ("function farmCropDefs():", "==", 1,
     "farmCropDefs 定义必须在位（本环唯一插入点）"),
    ("const FARM_STONES_MUL = 10;", "==", 1,
     "R-129 灵石侧 ×10 常量必须在位（本环不改常量，只覆盖新种终值）"),
    ("const FARM_YIELD_MUL = 1.0;", "==", 1,
     "R-129 修为侧倍率常量必须在位"),
    ("const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {", "==", 1,
     "20 新种判据表必须在位（不动）"),
    ("const FARM_CROP_ATTRS: Record<string,", "==", 1,
     "综合草属性表必须在位（不动；R-168 明确保持）"),
    ("function farmCropSell(", "==", 1,
     "变卖出口定价必须在位（不动）"),
    ("function farmCropConsume(", "==", 1,
     "服用出口必须在位（不动）"),
    ("const R163_FARM_TABLE: Record<string, [number, number, number]> = {", "==", 1,
     "R-163 覆盖表必须在位（本环在其后追加 R168 覆盖，不删不改）"),
    ("    out[_k163] = Object.assign({}, _d163, { seed: _v163[0], stones: _v163[1], exp: _v163[2] });", "==", 1,
     "R-163 覆盖循环必须在位（本环插入锚点的上半段）"),
    ("[r163farm]", ">=", 1,
     "R-163 环必须已应用（链序约束：本环排在第 71 环之后）"),
    ("[r165wudao]", ">=", 1,
     "R-165 环必须已应用（链序约束：本环排在第 72 环之后 = 新末环）"),
]

# ============================================================ 冻结基线（相对计数快照）

BASE_NEEDLES = [
    # farmCropDefs / 生成器（本环一行未动）
    "function farmCropDefs():",
    "const FARM_CROP_BASE: Record<number, { min: number; sell: number; expBase: number; attr: number }> = {",
    "const FARM_CROP_KIND: Record<string,",
    "const FARM_CROP_EXP_PURE: Record<number, number> =",
    "const FARM_CROP_EXP_MIX_ADJ: Record<number, number> =",
    "const FARM_CROP_TIERS = ['凡品', '灵品', '玄品', '仙品', '神品'];",
    "const FARM_CROPS_NEW: Record<string, { t: number; k: string }> = {",
    "const FARM_CROP_ATTRS: Record<string,",
    "const FARM_CROP_PCT: Record<string,",
    "const FARM_CROP_ATTR_CAP",
    "const FARM_STONES_MUL = 10;",
    "const FARM_YIELD_MUL = 1.0;",
    "const FARM_CROP_TIER_MUL: Record<string, number> = { mix: 1.5, rare: 2.5 };",
    "function farmCropSell(",
    "function farmCropConsume(",
    "function farmCropNoPlant(",
    "  return out;",
    # R-163 覆盖块（保留为历史档）
    "const R163_FARM_TABLE: Record<string, [number, number, number]> = {",
    "  for (const _k163 of Object.keys(R163_FARM_TABLE)) {",
    "[r163farm]",
    # 工程红线（本环不新增）
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
        ("R168 幂等标记在位", MARK, 1, "==", "本环已应用"),
        ("R168 覆盖表头", NEW_TABLE_HEAD, 1, "==", "R168_FARM_TABLE 恰好 1 处"),
        ("R168 覆盖循环", "for (const _k168 of Object.keys(R168_FARM_TABLE)) {", 1, "==", "在 R163 覆盖之后生效"),
        ("R168 覆写三字段", "out[_k168] = Object.assign({}, _d168, { seed: _v168[0], stones: _v168[1], exp: _v168[2] });", 1, "==", "seed/stones/exp"),
        ("R168 追加而非替换（R163 表仍在）", "const R163_FARM_TABLE: Record<string, [number, number, number]> = {", 1, "==", "历史档保留"),
        ("R168 R163 标记未动", "[r163farm]", 1, "==", "冻结"),
        ("R168 R163 覆盖循环未动", "    out[_k163] = Object.assign({}, _d163, { seed: _v163[0], stones: _v163[1], exp: _v163[2] });", 1, "==", "冻结"),
        # 逐档新值（20 种）
        ("R168 值·sell 凡 灵谷穗", _entry_needle('linggusi'), 1, "==", "净赚 600 / 修为 400"),
        ("R168 值·sell 灵 紫纹灵稻", _entry_needle('ziwenlingdao'), 1, "==", "净赚 900 / 修为 600"),
        ("R168 值·sell 玄 金髓藤", _entry_needle('jinsuiteng'), 1, "==", "净赚 1500 / 修为 1000"),
        ("R168 值·sell 仙 仙玉莲", _entry_needle('xianyulian'), 1, "==", "净赚 2400 / 修为 1600"),
        ("R168 值·sell 神 神藏金参", _entry_needle('shencangjinshen'), 1, "==", "净赚 3600 / 修为 2400"),
        ("R168 值·mix 凡 培元草", _entry_needle('peiyuancao'), 1, "==", "回本+10% / 修为 9000"),
        ("R168 值·mix 灵 壮骨花", _entry_needle('zhuangguhua'), 1, "==", "回本+10% / 修为 18000"),
        ("R168 值·mix 玄 百炼芝", _entry_needle('bailianzhi'), 1, "==", "回本+10% / 修为 36000"),
        ("R168 值·mix 仙 九窍玄芝", _entry_needle('jiugiaoxuanzhi'), 1, "==", "回本+10% / 修为 72000"),
        ("R168 值·mix 神 万象花", _entry_needle('wanxianghua'), 1, "==", "回本+10% / 修为 144000"),
        ("R168 值·cult 凡 引气苗", _entry_needle('yinqimiao'), 1, "==", "变卖 750 不动 / 修为 15000"),
        ("R168 值·cult 灵 凝元芝", _entry_needle('ningyuanzhi'), 1, "==", "变卖 1500 不动 / 修为 45000"),
        ("R168 值·cult 玄 玄元果", _entry_needle('xuanyuanguo'), 1, "==", "变卖 3000 不动 / 修为 150000"),
        ("R168 值·cult 仙 太清果", _entry_needle('taiqingguo'), 1, "==", "变卖 6000 不动 / 修为 600000"),
        ("R168 值·cult 神 混元道果", _entry_needle('hunyuandaoguo'), 1, "==", "变卖 12000 不动 / 修为 3000000"),
        ("R168 值·rare 玄 疾风叶(不动)", _entry_needle('jifengye'), 1, "==", "冻结"),
        ("R168 值·rare 仙 血魄花(不动)", _entry_needle('xuepohua'), 1, "==", "冻结"),
        ("R168 值·rare 仙 星陨花(不动)", _entry_needle('xingyunhua'), 1, "==", "冻结"),
        ("R168 值·rare 神 洞玄花(不动)", _entry_needle('dongxuanhua'), 1, "==", "冻结"),
        ("R168 值·rare 神 不灭藤(不动)", _entry_needle('bumieteng'), 1, "==", "冻结"),
        # 生成器/出口未动
        ("R168 出口未动·farmCropSell", "function farmCropSell(", 1, "==", "冻结"),
        ("R168 出口未动·farmCropConsume", "function farmCropConsume(", 1, "==", "冻结"),
        ("R168 属性表未动·FARM_CROP_ATTRS", "const FARM_CROP_ATTRS: Record<string,", 1, "==", "R-168 明确保持"),
        ("R168 品阶表未动·FARM_CROP_BASE", "const FARM_CROP_BASE: Record<number, { min: number; sell: number; expBase: number; attr: number }> = {", 1, "==", "冻结"),
        ("R168 灵石×10 未动", "const FARM_STONES_MUL = 10;", 1, "==", "冻结"),
        ("R168 修为×1 未动", "const FARM_YIELD_MUL = 1.0;", 1, "==", "冻结"),
        ("R168 return out; 计数未变", "  return out;", base["  return out;"], "==", "不增删 return"),
        # 工程红线
        ("R168 红线·无新 require", "require(", 0, "==", "ESM 直跑禁 require"),
        ("R168 红线·无新 403", "res.status(403", base["res.status(403"], "==", "不新增 403（客户端会强制登出）"),
        ("R168 红线·无新 setInterval", "setInterval(", base["setInterval("], "==", "不新增定时器"),
        ("R168 红线·无新 PRAGMA", "PRAGMA", base["PRAGMA"], "==", "不动库"),
    ]
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description="R-168 灵田数值重构（服务端环）+ R-169 结论留档")
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
        print("  [%s] %-46s actual=%d %s %d" % ("OK" if good else "FAIL", label, act, op, exp))
    if not ok:
        fail("门禁未全绿，未写回")

    # 7) 往返自证：除这一处外其余字节完全一致
    if out != src.replace(ANCHOR_OLD, ANCHOR_NEW, 1):
        fail("round-trip(正向重构) mismatch")
    if out.replace(ANCHOR_NEW, ANCHOR_OLD, 1) != src:
        fail("round-trip(逆向) mismatch：除改动点外字节被改动")
    if out.count(ANCHOR_NEW) != 1:
        fail("round-trip：ANCHOR_NEW 出现次数 != 1")
    if out.count(NEW_TABLE_HEAD) != 1:
        fail("R168_FARM_TABLE 出现次数 != 1")

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 8) 改前 .bak + 原子写回
    bak = "%s.bak-r168-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r168farm-", suffix=".tmp")
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
