# -*- coding: utf-8 -*-
r"""
yl_r047_ext.py — R-047 仙务·灵田「变卖/服用」收益大幅提高 —— ⚠️ 客户端**无改动面**（诚实守卫模块）

需求（台账 R-047，无附图）
--------------------------------------------------------------------------
  「仙务·灵田，变卖和服用的修为、灵石都大幅度增加，这个是游戏另一个获得修为和
    灵石的主要途径。」
  ⇒ 两个出口收益大幅提高：变卖 → 灵石；服用 → 修为（+ 属性）。

★ 结论先行：本需求**无法用客户端补丁实现**，真正的入账在**服务端**。因此本模块是
  「诚实守卫模块」——**不改任何客户端数值/文案**，只用门禁把事实钉死，防止后人
  用「改显示」的方式伪装成 R-047 达标（那正是用户点名过的「显示骗人」）。

侦察（逐字实证：build/assets/index-v28118-20261001.js + srv/index_v28.ts）
--------------------------------------------------------------------------
 1) 客户端两个函数**只是显示**，本身不产生收益：
      function YlxwFtSellText(cd, slot) {
        var s = YlxwNum(cd && cd.sell);
        return "灵石 +" + s.toLocaleString();
      }
      function YlxwFtConsumeText(cd) { … if (YlxwNum(cd.consExp) > 0)
        parts.push("修为 +" + YlxwNum(cd.consExp)); … }
    它们读的 `cd.sell` / `cd.consExp` 来自 GET /farm/status 的 `cropList[]`；
    而 cropList 是服务端 `farmCropDefs()` 的产物（srv/index_v28.ts:7938-7955）。
    ⇒ **只改这两个函数 = 只改显示 = 骗人**（入账分文未增）。
 2) 客户端**没有**任何入账面。点「变卖/服用」→ `runConfirm` →
      f("h" + q.slot + mode, "/farm/harvest", { slot: q.slot, mode: mode }, …)
    ⇒ 只把 `{slot, mode}` POST 给服务端；`YlxwPost` → `YlxwApi` → 服务端算完回显余额。
    客户端不参与收益计算（与技能 §12.6「灵田结算在服务端」同结论）。
 3) 真正入账在服务端 `srv/index_v28.ts`：
      farmHarvestOne → farmYield(farmCrop(row.crop), early, mods)
      farmYield: s = floor(crop.stones * mul * (1-dec));  e = floor(crop.exp * mul * (1-dec))
    其中 `crop` 来自 `farmCrop()` ← `farmCropDefs()` —— **与 cropList 同源**。
 4) ⇒ 只要服务端放大 `farmCropDefs()` 的 `stones` / `exp`，**入账与客户端文案会一起变**
    （同一份数据），客户端零改动即可保持「显示 == 实付」。

本模块动作 = **无（no-op）**
--------------------------------------------------------------------------
  INJECT_JS = ''；`apply()` **不做任何 `p.replace`**（因此也无 expect 命中问题），
  只做「前置自证 + 返回门禁」。门禁全部跨 R-046 前后恒成立（不依赖 r046 是否已落）。

★ 交给主控的落地规格（R-047 的真正实现，本模块**不**代做）
--------------------------------------------------------------------------
  新建 `srv_patch_r047.py`（服务端半边，照 srv_patch_050.py 的 CLI/幂等/门禁模板），
  接到 `localtest/chain_build.py` 的 `SRV_CHAIN` 链尾，只做两件事：
    ① 新增常量：`const FARM_YIELD_MUL = 3;   // R-047 灵田双出口收益倍率`
    ② 在 `farmCropDefs()` 里，对**变卖价 stones 与服用修为 exp** 乘 FARM_YIELD_MUL；
       **种子价 seed 不乘**（只抬产出、不动种植成本，避免顺带抬门槛）：
         - 新 20 种：`const stones = Math.round(b.sell * k.money);`
               → `const stones = Math.round(b.sell * k.money * FARM_YIELD_MUL);`
             并让 seed 仍按**未乘倍率**的 stones 算（`cs` 一行先算 seed 再乘倍率）。
         - 旧种 5 键（FARM_CROPS：灵草/灵芝/千年参/太虚果/造化青莲）：stones/exp 同乘，
           seed 不动（存量田与兼容区口径一并抬升）。
      ⇒ farmYield（入账）与 cropList（文案）同源自动跟随；**无需任何客户端改动**。
  经济口径：×3 与 R-044（历练 ×3）同档 —— 用户把两者都称作「主要途径」；
      上线前请按 T9T10 经济红线复核满配日净（R-054 拍板即以 R-044/R-047 为对照基准）。
  若主控决定本期不做服务端，请把 R-047 退回待办并注明「客户端无法实现」——**不要**
      用改 `YlxwFtSellText` / `YlxwFtConsumeText` 的方式伪达标。

接线 / 纪律
--------------------------------------------------------------------------
  · 本模块**可不接线**（无改动面）；若接线，放在 farm2 / r046 之后、numbal 之前即可
    （纯只读门禁，无锚点依赖、无顺序依赖）。
  · 只新建本文件；不改 build_v26n.py / localtest/* / srv/index_v28.ts / deploy_v28/* /
    任何已有 yl_*_ext.py（含 yl_r046_ext.py —— 它的显示改动本模块一字不碰）。
  · 注入块为空（zh() 后纯 ASCII）；不含 V28_BAN_PATTERNS。
"""

import re

# --------------------------------------------------------------------------- 注入块
# 本模块不注入任何客户端代码：R-047 的入账在服务端，客户端改了就是「显示骗人」。
INJECT_JS = ''

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- 事实针（客户端无入账 / 文案与入账同源）

HARVEST_CALL = '"/farm/harvest", { slot: q.slot, mode: mode }'   # 客户端唯一收获出口：只发 slot/mode
POST_FN      = 'function YlxwPost(r, t) {'                       # POST 到服务端，无本地入账
SELL_READ    = 'var s = YlxwNum(cd && cd.sell);'                 # 变卖显示读服务端字段
CONSUME_READ = 'if (YlxwNum(cd.consExp) > 0) parts.push('        # 服用显示读服务端字段
CROPS_MERGE  = 'g = YlxwFtCrops(t), h = Object.keys(g);'         # farm2：cropList 并入（文案与入账同源）

# --------------------------------------------------------------------------- 未骗人针（两个显示函数原样）

SELL_FN      = 'function YlxwFtSellText(cd, slot) {'
CONSUME_FN   = 'function YlxwFtConsumeText(cd) {'
SELL_RET     = r'return "\u7075\u77f3 +" + s.toLocaleString();'
CONSUME_PUSH = r'parts.push("\u4fee\u4e3a +" + YlxwNum(cd.consExp));'

# --------------------------------------------------------------------------- 冻结针（相邻需求面一字未动）

F_R046_SEEDTIP = 'title: YlxwFtSeedTip(g[x] || {}, N.slot)'      # R-046 播种 hover（本模块不碰）
F_R046_HTEXT   = 'function YlxwFtHarvestText(cd, slot) {'        # R-046 复用面
F_R048_LEFTMS  = 'YlxwMin(YlxwNum(b.leftMs))'                    # R-048 成熟时间展示
F_R048_PLANTCD = 'ok2 = !nl || gl >= nl;'                        # R-048 种植条件（洞府门槛）
F_R046_RETIRED = 'var ret = cd.retired === true;'                # R-046 已停种判定
F_PLANT        = '"/farm/plant"'                                 # 种植入口
F_UNLOCK       = '"/farm/unlock"'                                # 开垦入口（R-049 面）
F_TEND         = '"/farm/tend"'                                  # 照料入口
F_BOOST        = '"/farm/boost"'                                 # 催熟入口（R-050 面）
F_MODE         = 'var mode = q.kind === "consume" ? "consume" : "sell";'  # 收获结算分流
F_PR           = 'Pr=[{level:1,name:'                           # 洞府扩充等级表（R-049 面）
F_FARMT5       = 'function YlxwTFarmT5() {'                      # 灵田面板本体
F_FARMREG      = 'YLXW_COMP.farm=YlxwTFarmT5;'                   # 面板注册


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 farm2 / r046）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 注入块（空串）禁用模式自查 —— 与其它模块同构
    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r047 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for _pat in BAN_PATTERNS:
        if _pat in blk:
            raise AssertionError('r047 注入块含禁用模式: %s' % _pat)

    # 前置自证：客户端确无入账面 + 两个显示函数在位（防链序/基线漂移后门禁失真）
    if p.count(HARVEST_CALL) != 1:
        raise AssertionError('r047 前置不满足：/farm/harvest 确认调用出现 %d 次（期望 1）'
                             % p.count(HARVEST_CALL))
    if p.count(SELL_FN) != 1 or p.count(CONSUME_FN) != 1:
        raise AssertionError('r047 前置不满足：变卖/服用显示函数不在位'
                             '（SELL=%d CONSUME=%d）' % (p.count(SELL_FN), p.count(CONSUME_FN)))

    # ★★ 本模块**不做任何替换** ★★
    #   R-047 的收益入账在服务端 farmHarvestOne（← farmCropDefs），客户端没有入账面；
    #   在此处改任何数值/文案都只是「显示骗人」，故有意保持零改动（p 仅用于只读 count）。

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 事实固化：客户端不参与入账、文案与入账同源 =================
        ('R47·客户端 harvest 只发 slot/mode', HARVEST_CALL, 1, '==',
         '入账在服务端 farmHarvestOne；客户端不参与收益计算'),
        ('R47·客户端仅经 YlxwPost 提交',      POST_FN, 1, '==', 'POST 到服务端，无本地入账'),
        ('R47·变卖显示读服务端 sell',         SELL_READ, 1, '==',
         'cd.sell 来自 /farm/status cropList（服务端 farmCropDefs）'),
        ('R47·服用显示读服务端 consExp',      CONSUME_READ, 1, '==', '与入账同源'),
        ('R47·文案/入账同源(目录合并)',       CROPS_MERGE, 3, '==',
         'farm2 合并 cropList ⇒ 服务端一改即自动跟随，客户端无需改'),
        # ================= 未骗人：两个显示函数一字未动 =================
        ('R47·未改变卖显示(不骗人)',          SELL_FN, 1, '==',
         'R-047 客户端零改动：改此处=显示骗人'),
        ('R47·未改服用显示(不骗人)',          CONSUME_FN, 1, '==', '同上'),
        ('R47·变卖公式原样',                  SELL_RET, 1, '==', '只读服务端值'),
        ('R47·服用修为前缀原样',              CONSUME_PUSH, 1, '==', ''),
        # ================= 冻结：R-046 灵田显示（刚改，本模块绝不回踩） =================
        ('冻结·R46 播种 hover 未回踩',        F_R046_SEEDTIP, 2, '==', 'R-046 显示改动'),
        ('冻结·R46 标注函数仍唯一',           F_R046_HTEXT, 1, '==', 'R-046 复用面'),
        ('冻结·R46 已停种判定未动',           F_R046_RETIRED, 1, '==', ''),
        # ================= 冻结：R-048 成熟时间 / 种植条件 =================
        ('冻结·R48 成熟时间展示未动',         F_R048_LEFTMS, 3, '==', 'R-048 面'),
        ('冻结·R48 种植条件未动(洞府门槛)',   F_R048_PLANTCD, 2, '==', 'R-048 面'),
        # ================= 冻结：收获结算 + 各入口 =================
        ('冻结·收获结算分流未动',             F_MODE, 1, '==', ''),
        ('冻结·种植入口未动',                 F_PLANT, 3, '==', ''),
        ('冻结·开垦入口未动',                 F_UNLOCK, 3, '==', 'R-049 面'),
        ('冻结·照料入口未动',                 F_TEND, 2, '==', ''),
        ('冻结·催熟入口未动',                 F_BOOST, 2, '==', 'R-050 面'),
        # ================= 冻结：洞府扩充 / 灵田面板 =================
        ('冻结·洞府扩充等级表未动',           F_PR, 1, '==', 'R-049 面'),
        ('冻结·灵田面板函数未动',             F_FARMT5, 1, '==', ''),
        ('冻结·面板注册未动',                 F_FARMREG, 1, '==', ''),
    ]
    return gates
