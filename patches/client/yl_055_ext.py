# -*- coding: utf-8 -*-
r"""
yl_055_ext.py — R-055 活动中心·灵玉阁：玩法说明 + 掉落口径透明化（客户端半边）

需求（R-055 原文，需求台账_进行中.md）
  「灵玉阁这个玩法说明也要写上，而且灵玉的获取途径和触发几率实装了吗，我玩了很久
   也没遇到过。如果每次是按个获取的话，最高2500个灵玉获取难度有点太高了……
   玩法比较不错，但是数值和落地实装效果需要策划一下。」

侦察结论（2026-10-01 实测，build/assets/index-v28115-20261001.js + srv/index_v28.ts）
  1) 掉玉机制【已实装】：srv/index_v28.ts `actDropTokens` + 三个结算点挂点——
     炼丹出炉（yieldStones）/ 灵田收获（farmHarvestOne 的 gain.stones）/
     离线收益（applied.stonesGain）。
  2) 玩家「玩了很久也没遇到过」的两个真因（代码可证）：
     a. 只认活跃 token_shop 场次（events 表无 enabled=1 且在窗口内的行 ⇒ 恒 0）；
     b. 掉率 ACT_TOKEN_RATE_PER_10K = 2（0.02%）+ floor ⇒ 单笔结算 <500 灵石必为 0，
        而炼丹/灵田单笔常见几百，几乎永远 floor 到 0。
  3) 「最高 2500」= 灵玉阁货架 title_jade（称号·灵玉仙客）的服务端定价
     （srv :451195 附近），可达性实测极差（推演见拍板文件
     <LOCAL>/Documents/需求台账/拍板/2026-10-01_*_R-055_*.md）。
  4) 面板原本只有一句「未开放」话术，没有玩法说明 —— 本模块补上。

本模块动作（纯客户端 · 2 处就地替换，锚点全在 act087 注入区 = \u 转义形态）
  ① 「我的灵玉」行后追加一行【玩法说明】：获取途径 / 掉率 0.5%（50 玉 / 1 万灵石结算）/
     每日上限 300 / 仅活动期掉落 / 余额跨期保留 / 限购每期重置。
     —— 数值与 srv_patch_055.py（R-055 服务端半边）的新常量同源：掉率 2→50、
        日上限 300 不变；日后若再调数值，两半边必须一起改（文案里是明写数字）。
     —— 货架价格不在客户端硬编码（由 /api/activity/shop 下发），本模块零价格文案。
  ② 「灵玉阁未开放；炼丹出炉、灵田收获、离线收益可掉落灵玉，余额跨期保留。」
     改为不含误导的表述：旧句读起来像「随时可掉」，正是玩家困惑来源之一；
     新句明确「仅开放期内掉落」。

硬约束 / 纪律
  · 不碰 act087 其它任何面：掉玉 toast（YLACT_LAST_JADE）、页签表、万妖巢穴/冲榜/
    七日礼面板、YlxwTDaily（R-053 面）—— 全部进冻结门禁。
  · INJECT_JS = ''（纯就地替换，无注入块，天然无 BAN_PATTERNS 风险）；
    替换串仍自检禁词与 ASCII（act087 区是转义形态，中文必须经 u() 生成 \uXXXX 字面）。
  · 锚点唯一：bundle 实测 count==1（2026-10-01 探针）；全仓 yl_*.py 只有
    yl_act087_ext.py 引用 YlxwTActShop（无人改同一串，无抢占）。
  · ⛔ 不改 build_v26n.py / srv/index_v28.ts / localtest/ / deploy_v28/ 任何文件；
    接线（V28_MODULES 加 ('r055', ...)）由 lead 完成。
"""

# ---------------------------------------------------------------- 转义助手


def u(s):
    r"""与 yl_patch.zh 同口径：非 ASCII → \uXXXX 字面（小写 hex）。

    本模块锚点位于 act087 注入区，产物里中文全部是 \uXXXX 转义形态；
    锚点/替换串必须先转成同形态才能命中。"""
    out = []
    for ch in s:
        o = ord(ch)
        if o < 128:
            out.append(ch)
        elif o <= 0xFFFF:
            out.append('\\u%04x' % o)
        else:  # 星平面（emoji 等）→ 代理对
            o -= 0x10000
            out.append('\\u%04x\\u%04x' % (0xD800 + (o >> 10), 0xDC00 + (o & 0x3FF)))
    return ''.join(out)


INJECT_JS = ''          # 纯就地替换，无注入块

# ---------------------------------------------------------------- 锚点（bundle 实测 count==1 @2026-10-01）

# 「我的灵玉」行（act087 注入区转义形态）。替换 = 原串原样保留 + 追加说明行（前缀保持型，
# 替换后 MYROW 自身仍 count==1，可作门禁）。
MYROW = ('e.jsx(YlxwRow, { children: e.jsx("div", { className: "text-sm text-amber-300 font-bold", '
         'children: "' + u('我的灵玉：') + '" + YlxwNum(bal) }) }),')

# 玩法说明行。样式类 text-[11px] / text-stone-300 / leading-relaxed 均在编译后
# index-ZuV-l8Gt.css 实测存在（§22.3：凭直觉写的 Tailwind 类可能根本不存在，先查 CSS）。
HELP_TEXT = ('玩法说明：灵玉来自炼丹出炉、灵田收获、离线收益的灵石结算，按 0.5%'
             '（50 玉 / 1 万灵石）折算掉落，仅在灵玉阁开放期内掉落，每人每日上限 300 玉；'
             '余额跨期保留，阁内商品固定价兑换、限购每期重置。')
HELP_LINE = ('\n    e.jsx("div", { className: "text-[11px] text-stone-300 leading-relaxed", children: "'
             + u(HELP_TEXT) + '" }),')

# 「未开放」旧句（含「随时可掉」误导）与新句。
NOTOPEN_OLD = u('灵玉阁未开放；炼丹出炉、灵田收获、离线收益可掉落灵玉，余额跨期保留。')
NOTOPEN_NEW = u('灵玉阁本期未开放；灵玉仅在开放期内掉落，已得余额跨期保留。')

# 注入内容红线（build 侧只查 INJECT_JS；就地替换串自查同一张表）
_BAN = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# ---------------------------------------------------------------- 主入口


def apply(p, ctx):
    # 前置自检：替换串构造没退化；禁词零命中；替换串是纯 ASCII（转义形态）。
    for s in (MYROW, HELP_LINE, NOTOPEN_OLD, NOTOPEN_NEW):
        if not s:
            raise AssertionError('r055 替换串构造异常：出现空串')
        if any(b in s for b in _BAN):
            raise AssertionError('r055 替换串含禁用模式: %r' % _BAN)
        if not s.isascii():
            raise AssertionError('r055 替换串含非 ASCII（应经 u() 转义）')
    if NOTOPEN_OLD == NOTOPEN_NEW:
        raise AssertionError('r055 未开放句 old == new')

    p.replace('r055-help', MYROW, MYROW + HELP_LINE, expect=1,
              note='灵玉阁补玩法说明（掉率/上限与 srv_patch_055.py 新常量同源，改值须两半边同步）')
    p.replace('r055-notopen', NOTOPEN_OLD, NOTOPEN_NEW, expect=1,
              note='未开放句去掉「随时可掉」误导，改述「仅开放期内掉落」')

    gates = [
        # ================= 本模块改动 =================
        ('R55·玩法说明行已插入',        u(HELP_TEXT), 1, '==', '0.5%/300 与服务端 r055 环同源'),
        ('R55·「我的灵玉」行原样保留',  MYROW,        1, '==', '前缀保持型替换，原行未动'),
        ('R55·未开放新句就位',          NOTOPEN_NEW,  1, '==', ''),
        ('R55·未开放旧句已清零',        NOTOPEN_OLD,  0, '==', '旧表述读作「随时可掉」'),
        ('R55·说明行样式类存在',        'text-[11px] text-stone-300 leading-relaxed', 1, '==', '三类均在编译后 CSS 实测存在'),
        # ================= 冻结：act087 相邻面一字不动 =================
        ('冻结·掉玉 toast 未动',        'YlxwToast("' + u('灵玉 +') + '" + (bal - YLACT_LAST_JADE)', 1, '==', 'act087 自有门禁同款'),
        ('冻结·掉玉水位变量计数不变',   'YLACT_LAST_JADE', 5, '==', '声明1+比较2+赋值1+toast内1（bundle 实测基线）'),
        ('冻结·灵玉阁页签表未动',       '["shop", "' + u('灵玉阁') + '"], ["boss", "' + u('万妖巢穴') + '"]', 1, '==', '活动中心页签定义'),
        ('冻结·YlxwTActShop 定义唯一',  'function YlxwTActShop(', 1, '==', 'act087 门禁同款'),
        ('冻结·万妖巢穴面板未动',       'function YlxwTActBoss(', 1, '==', 'tab D 面'),
        ('冻结·闭阁提示未动',           u('本期灵玉阁已闭阁'), 1, '==', 'closed 分支话术'),
        ('冻结·货架兑换按钮未动',       u('灵玉不足'), 1, '==', 'poor 分支话术'),
        # ================= 冻结：相邻需求的面 =================
        ('冻结·每日行乐面板未动（R-053）', 'function YlxwTDaily(', 1, '==', 'R-053 茶馆所在面板定义'),
        ('冻结·仙途冲榜未动',           'function YlxwTActRank(', 1, '==', 'tab A 面'),
        ('冻结·仙缘七日礼未动',         'function YlxwTActCheckin(', 1, '==', 'tab B 面'),
    ]
    return gates
