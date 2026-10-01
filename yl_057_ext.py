# -*- coding: utf-8 -*-
r"""
yl_057_ext.py — R-057「奇遇抽奖」客户端半边（消耗修为 · 冷却 30 分钟 · 每日 10 次 · 暴击双倍 的 UI 面）

需求原文（需求台账_进行中.md R-057）
--------------------------------------------------------------------------
  「奇遇抽奖变成消耗修为抽取，冷却时间30分钟，每日最多10次。获得的灵石数量大幅提升，
    这个也作为主要的灵石来源活动。并且抽奖时还有几率暴击，暴击获得双倍。」

系统定位（构建产物 index-v28115-20261001.js 逐字实证）
--------------------------------------------------------------------------
  「奇遇抽奖」= 仙务 adventure 面板，服务端权威（/api/adventure/list + /api/adventure/draw）。
  客户端面板 = function YlxwTAdventure()（v2810d-A 注入，bundle @895623，本批实测唯一）：
    · 标题  「奇遇抽奖 · 今日 drawn/dailyMax」
    · 按钮  「抽一次」，禁用条件 g || l || (!!t && drawn >= dailyMax)
    · tier 行 展示 T.name + weight% · 灵石 stonesMin~stonesMax（**服务端数值直接跟随**）
    · toast  ia("奇遇：" + tierName + " · " + text + "（灵石+stones 修为+expGain 抽奖券…）")
  经济逻辑（消耗/冷却/上限/灵石/暴击）全部在服务端 —— 由配套环 srv_patch_057.py
  （SRV_CHAIN 第 23 环）落地；本环只做 4 件事的**显示面**：
    ① 按钮禁用加冷却（cdLeft 由 /adventure/list 下发，抽后 await c() 自动刷新）
    ② 标题显示「冷却 N 分钟」（分钟粒度、静态，重开面板或抽后刷新更新——30 分钟冷却
       本来就是"去干别的"的节奏，不为倒数挂 interval，保持最小改动）
    ③ 面板说明行写死新规则文案（数值与 srv_patch_057.py 定档常量一一对应，两边门禁互锁）
    ④ toast 加「⚡暴击×2！」前缀 + 「修为-cost」消耗显示（字段 crit/cost 由 draw 响应下发）

锚点纪律
--------------------------------------------------------------------------
  · 三个替换锚全部 count==1（_r057_anchors.py 实测）；替换串一律 \uXXXX 转义，
    与 bundle 内中文字节形态一致（该面板中文全部为 \uXXXX 转义形态）。
  · 不碰 R-031（yl_lottery_ext.py）的面：精简面板 YlxwTDrawQuick / 完整面板 NM /
    单抽 / 十连 / 完整抽奖面板 / 返回精简面板 按钮 / handleDraw 抽奖本体 —— 全部冻结门禁。
  · 不碰 tier 展示行与历史记录行：服务端 TIERS ×30 后这两处**自动跟随**，零改动零风险。
  · INJECT_JS 为空（纯就地替换，无注入块 ⇒ 天然无 V28_BAN_PATTERNS 风险）。

硬约束
--------------------------------------------------------------------------
  · 只新建本文件；不改 build_v26n.py / localtest/ / deploy_v28/ / srv/index_v28.ts / CHANGELOG.md。
  · 每处替换 expect=1；门禁含「旧形态清零」+「R-031 面冻结」双保险。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = ''          # 本模块只做「就地替换」，不需要额外注入块（同 yl_r040_ext.py 先例）

# --------------------------------------------------------------------------- 锚点（bundle 内为 \uXXXX 转义形态；已实测各 count==1）

# C1 「抽一次」按钮禁用条件：加冷却（t.cdLeft 毫秒，srv 下发）
C1_OLD = 'disabled: g || l || (!!t && YlxwNum(t.drawn) >= YlxwNum(t.dailyMax))'
C1_NEW = ('disabled: g || l || (!!t && (YlxwNum(t.drawn) >= YlxwNum(t.dailyMax)'
          ' || YlxwNum(t.cdLeft) > 0))')

# C2 标题加「· 冷却 N 分钟」（cdLeft>0 时显示，向上取整到分钟）
# C4 u 错误行后插说明行（与 C2 同一长锚一次替换，防「u 行」多面板同形态不唯一）
C2_OLD = ('children: "\\u5947\\u9047\\u62bd\\u5956" + (t ? " \\u00b7 \\u4eca\\u65e5 "'
          ' + YlxwNum(t.drawn) + "/" + YlxwNum(t.dailyMax) : "") }),'
          ' u && e.jsx("div", { className: "text-xs text-red-300", children: u }),')
C2_NEW = ('children: "\\u5947\\u9047\\u62bd\\u5956" + (t ? " \\u00b7 \\u4eca\\u65e5 "'
          ' + YlxwNum(t.drawn) + "/" + YlxwNum(t.dailyMax)'
          ' + (YlxwNum(t.cdLeft) > 0 ? " \\u00b7 \\u51b7\\u5374 "'
          ' + Math.ceil(YlxwNum(t.cdLeft) / 60000) + " \\u5206\\u949f" : "") : "") }),'
          ' u && e.jsx("div", { className: "text-xs text-red-300", children: u }),'
          ' e.jsx("div", { className: "text-[11px] text-stone-500", children:'
          ' "\\u6bcf\\u6b21\\u62bd\\u53d6\\u6d88\\u8017\\u5f53\\u5c42\\u4fee\\u4e3a 5%\\uff0c'
          '\\u51b7\\u5374 30 \\u5206\\u949f\\uff0c\\u6bcf\\u65e5\\u6700\\u591a 10 \\u6b21\\uff1b'
          '15% \\u51e0\\u7387\\u66b4\\u51fb\\u53cc\\u500d\\u3002" }),')

# C3 toast：加「⚡暴击×2！」前缀 + 「修为-cost」消耗显示（crit/cost 由 draw 响应下发）
C3_OLD = ('ia("\\u5947\\u9047\\uff1a" + (b.tierName || "") + " \\u00b7 " + (b.text || "")'
          ' + " \\uff08\\u7075\\u77f3+" + YlxwNum(b.stones) + " \\u4fee\\u4e3a+"'
          ' + YlxwNum(b.expGain)')
C3_NEW = ('ia((b.crit ? "\\u26a1\\u66b4\\u51fb\\u00d72\\uff01" : "")'
          ' + "\\u5947\\u9047\\uff1a" + (b.tierName || "") + " \\u00b7 " + (b.text || "")'
          ' + " \\uff08" + (YlxwNum(b.cost) > 0 ? "\\u4fee\\u4e3a-" + YlxwNum(b.cost) + " " : "")'
          ' + "\\u7075\\u77f3+" + YlxwNum(b.stones) + " \\u4fee\\u4e3a+" + YlxwNum(b.expGain)')

EDITS = [
    ('C1 按钮禁用加冷却',        C1_OLD, C1_NEW),
    ('C2 标题加冷却分钟 + C4 说明行', C2_OLD, C2_NEW),
    ('C3 toast 加暴击与消耗',    C3_OLD, C3_NEW),
]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 本模块无注入块；三处替换串全部为 ASCII（\uXXXX 形态），自证防手滑
    for name, old, new in EDITS:
        for tag, s in (('OLD', old), ('NEW', new)):
            bad = re.findall(r'[^\x00-\x7f]', s)
            if bad:
                raise AssertionError('%s %s 串含非 ASCII（必须 \\uXXXX 转义）: %r' % (name, tag, bad[:10]))

    for name, old, new in EDITS:
        p.replace(name, old, new, expect=1)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本模块改动 =================
        ('R57·按钮冷却禁用（新形态）', 'YlxwNum(t.drawn) >= YlxwNum(t.dailyMax) || YlxwNum(t.cdLeft) > 0)', 1, '==', 'cdLeft 为 srv 下发的毫秒'),
        ('R57·标题冷却分钟显示',      'Math.ceil(YlxwNum(t.cdLeft) / 60000)', 1, '==', ''),
        ('R57·说明行（消耗修为 5%）', '\\u6bcf\\u6b21\\u62bd\\u53d6\\u6d88\\u8017\\u5f53\\u5c42\\u4fee\\u4e3a 5%', 1, '==', '与 srv ADVENTURE_COST_RATE=0.05 对应'),
        ('R57·说明行（冷却 30 分钟）', '\\u51b7\\u5374 30 \\u5206\\u949f', 1, '==', '与 srv ADVENTURE_COOLDOWN_MS 对应'),
        ('R57·说明行（每日 10 次）',  '\\u6bcf\\u65e5\\u6700\\u591a 10 \\u6b21', 1, '==', '与 srv ADVENTURE_DAILY_MAX=10 对应'),
        ('R57·说明行（15% 暴击双倍）', '15% \\u51e0\\u7387\\u66b4\\u51fb\\u53cc\\u500d', 1, '==', '与 srv ADVENTURE_CRIT_RATE=0.15 对应'),
        ('R57·toast 暴击前缀',       'b.crit ? "\\u26a1\\u66b4\\u51fb\\u00d72\\uff01" : ""', 1, '==', 'crit 由 draw 响应下发'),
        ('R57·toast 消耗显示',       'YlxwNum(b.cost) > 0 ? "\\u4fee\\u4e3a-" + YlxwNum(b.cost) + " " : ""', 1, '==', 'cost 由 draw 响应下发'),
        ('R57·旧按钮形态已清零',      C1_OLD, 0, '==', ''),
        ('R57·旧 toast 形态已清零',   'ia("\\u5947\\u9047\\uff1a"', 0, '==', ''),
        # ================= 冻结：adventure 面板其余面一字不动 =================
        ('冻结·YlxwTAdventure 唯一',  'function YlxwTAdventure() {', 1, '==', ''),
        ('冻结·抽一次按钮未动',       'onClick: N, children: "\\u62bd\\u4e00\\u6b21"', 1, '==', 'onClick 体不变（冷却/扣费由 srv 把关）'),
        ('冻结·tier 展示行未动',      'children: T.name + " " + YlxwNum(T.weight)', 1, '==', 'srv TIERS ×30 后展示自动跟随'),
        ('冻结·历史行未动',          '"d" + b.count', 1, '==', 'draws 列表渲染零改动'),
        # ================= 冻结：R-031（yl_lottery_ext.py）的面 =================
        ('冻结·R31 精简面板唯一',     'function YlxwTDrawQuick(p) {', 1, '==', ''),
        ('冻结·R31 完整面板按钮',     'children: "\\u5b8c\\u6574\\u62bd\\u5956\\u9762\\u677f" })', 1, '==', ''),
        ('冻结·R31 单抽按钮',        'children: "\\u5355\\u62bd\\uff081 \\u5f20\\uff09"', 1, '==', ''),
        ('冻结·R31 十连按钮',        'children: "\\u5341\\u8fde\\u62bd\\uff0810 \\u5f20\\uff09"', 1, '==', ''),
        ('冻结·R31 返回精简按钮',     'children:"\\u8fd4\\u56de\\u7cbe\\u7b80\\u9762\\u677f"})}),', 1, '==', ''),
        ('冻结·抽奖券本体未动',       'if(!d||d.lotteryTickets<S){f("抽奖券不足！","danger");return}', 1, '==', 'handleDraw 券校验原样（UTF-8 直存形态，实测唯一）'),
    ]
    return gates
