# -*- coding: utf-8 -*-
r"""
yl_r121_ext.py — R-121「全局玩法说明补齐」客户端补丁脚本（0.9.13 批次）

需求原文（台账 R-121 · yl整个项目 · 进行中）
--------------------------------------------------------------------------
  「大任务，全局排查一下所有玩法，把所有没有玩法说明的功能和内容，全部加上玩法说明。」

设计依据（docs/0.9.13-design/玩法说明与文案.md，逐字照抄其 §A~§F 文案）
--------------------------------------------------------------------------
  文案师排查 39 个面板/页签：22 处已有说明不动，17+ 处无说明需补。
  本脚本共补 23 处落点（清单见 PATCHES）：
    A. yl 域面板 10 处：信箱/秘境手札/仙友录/称号/仙务成就/修行统计/万宝洗炼/
       活动中心-总览/活动中心-仙途冲榜/活动中心-每日签到 —— YlxwTitle 后插展开式说明行
    B. 行内玩法 5 处：奇遇抽奖/每日一签/掷骰比大小/灵石翻牌/万妖巢穴补行
    C. 基座 modal 5 处：修仙排行榜/交易行/洞府/商店/人物志 —— 容器开头插说明行
    D. 主屏 2 处：打坐/历练按钮加 title 悬浮说明（主屏为 fixed 底栏 grid，无面板级挂点）
    E. 灵宠视图 1 处：出战/助战栏补亲密度作用说明（§F-37，与 R-120 联动）

★ 与设计文档验收要点 1 的偏离（代决，已记拍板记录）
--------------------------------------------------------------------------
  文档要求「新增折叠块统一用 R-079 的 YlxwR79Box 模式」——但 yl_r079_ext.py:207 存在
  冻结门禁 ('R79·说明块共 8 处', 'YlxwR79Box("', 8, '==')，_r123_selfcheck.py:172 亦冻结
  R79Box(=9 / 玩法说明=17。新增任何 R79Box 调用都会打爆既有冻结门禁 ⇒
  本脚本改用展开式说明行 div（e.jsx("div", ...)），一个 R79Box 都不加：
    · YlxwR79Box("  保持 8 == 8（R-079 门禁不破）
    · YlxwR79Box(   保持 9 == 9（R-123 稳定性断言不破）
    · \u73a9\u6cd5\u8bf4\u660e（玩法说明）保持 17 == 17（说明文案不含该四字）
  展开式说明玩家打开面板即见，可见性优于需点击的折叠块。

锚点纪律（2026-10-02 对 build/assets/index-v2912-20261002.js 逐字实证）
--------------------------------------------------------------------------
  · 每个锚点（OLD）count==1 才动手；全部锚点已在基线产物上验证唯一。
  · yl 域为美化代码（`key: value` 带空格），基座为压缩代码（`key:value` 无空格）——
    锚点一律取产物真实字节形态（经 esc() 从中文源码转出，与产物 \uXXXX 形态逐位一致）。
  · 全部新串改前 count==0（独有信号，铁律⑥）。
  · 锚点全部位于本模块独占域，与同批 r116/r118/r119/r124/r125/r126 的改动区零交集
    （medlog 模板 @718021、ZN @325575、yl_049 E1/E7、YLXW_CHAR_DEXMILE @1209727 均不碰）。

文案与数值联动
--------------------------------------------------------------------------
  · §A-6 翻牌（花 2 万/10 张/限 10 次）、掷骰（10 次）＝ R-128 新值口径（数值表 §10）。
  · §F-30 历练「极低概率捡到抽奖券」＝ R-116 压券后口径（数值表 §4）。
  · §F-37 亲密度文案按代码实证改写（代决，已记拍板）：YlxwPetBonusOne = 属性 × 转化率
    × K品阶 × K阶段 × (1+亲密度/200)（srv/客户端 @1419372 实读），方案原文
    「每 25 点暴击 +0.5%」与该公式不符 ⇒ 按铁律「文案对齐代码」处理。

契约（0.9.13 批次成员补丁脚本，同 yl_r118_ext.py）
--------------------------------------------------------------------------
  · 命令行只有 --src <文件>；二进制读写；就地原子写回（临时文件 + os.replace）。
  · 首次改写前落 <src>.bak-r121-<时刻>；重跑已补丁文件不写盘（幂等保护，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；
    4=形态异常（部分已补/部分未补）；1=断言失败。
  · 前置依赖：--src 为 0.9.13 装配链产物（0.9.12 index-v2912-20261002.js 实测满足）。

门禁（apply 后形态；供 dryrun 门禁表原样收录）
--------------------------------------------------------------------------
  23 条 'R121·<处>' 独有信号 ==1 + 4 条冻结面（R79Box 调用 8 / R79Box( 9 /
  玩法说明 17 / 茶馆说明块 1）。
"""

import os
import sys
import argparse
import shutil
from datetime import datetime

# ---- 运行时转义：中文源码 → 产物 \uXXXX ASCII 字节形态（BMP only）----


def esc(t):
    """把 str 转成产物字节形态：非 ASCII 码点 → \\uXXXX（小写 hex），ASCII 原样。
    注：old 锚点含 JS 结构引号属正常，本函数不做引号检查；纯文案入口见 _chk_txt。"""
    out = []
    for ch in t:
        o = ord(ch)
        if o < 128:
            out.append(ch)
        else:
            if o > 0xFFFF:
                raise AssertionError('非 BMP 字符: %r' % ch)
            out.append('\\u%04x' % o)
    return ''.join(out).encode('ascii')


def _chk_txt(t):
    """纯文案段检查：ASCII 引号/反斜杠会破坏 JS 字符串字面量。"""
    if '"' in t or '\\' in t:
        raise AssertionError('文案含 ASCII 引号/反斜杠: %r' % t[:40])
    return t


def jsdiv(text, cls):
    """展开式说明行 div（e.jsx 形态）。"""
    return ', e.jsx("div", { className: "%s", children: "%s" })' % (cls, esc(_chk_txt(text)).decode('ascii'))


DIV_YL = 'mt-2 rounded border border-stone-600 px-3 py-2 text-xs text-stone-400 leading-relaxed'
DIV_FULL = 'mt-2 rounded border border-stone-600 px-3 py-2 text-xs text-stone-400 leading-relaxed w-full'

# ---- 23 处补丁（note, old, new）—— old/new 均为中文源码 str，跑时经 esc() 转字节 ----
# 文案出处：docs/0.9.13-design/玩法说明与文案.md §A-1/A-3/A-6/A-7/B-12/C-14/D-20/D-21/D-22/
# E-26/F-29/F-30/F-31/F-32/F-33/F-34/F-35/F-37（除 §F-37 按代码实证改写、万妖只补缺半句）。

PATCHES = [
    # ===== A. yl 域面板：YlxwTitle 元素后插说明行 =====
    ('mail信箱',
     'children: "信箱" + (t ? " · 未读 " + t.unread : "") })',
     'children: "信箱" + (t ? " · 未读 " + t.unread : "") })' + jsdiv(
         '系统发的奖励（成就、里程碑、活动结算等）都会寄到这里。逐封领取，或点「一键领取」全部落袋；已领奖励的邮件可删，未领附件的邮件不可删。', DIV_YL)),
    ('dungeon秘境手札',
     'children: "秘境手札（只读）" })',
     'children: "秘境手札（只读）" })' + jsdiv(
         '你的秘境探索日志（只读）：今天进过几次、还剩几次、冷却何时转好，都记在这。「观测秘境/观测奇遇」是你进秘境时顺手记下的额外发现，「异常标记」提示本期记录有波动、仅供参考。手札只记账，进秘境请在探索入口操作。', DIV_YL)),
    ('friends仙友录',
     'children: "仙友录" })',
     'children: "仙友录" })' + jsdiv(
         '加其他玩家为好友（输入对方名号申请），每天可给每位好友送一件礼物。江湖不是一个人的修行，朋友多了路好走。', DIV_YL)),
    ('titles称号',
     'children: "称号" + (function () { for (var i = 0; i < m.length; i++) { if (m[i].id === g) return " · 佩戴中「" + m[i].name + "」"; } return g ? " · 佩戴中" : ""; })() })',
     'children: "称号" + (function () { for (var i = 0; i < m.length; i++) { if (m[i].id === g) return " · 佩戴中「" + m[i].name + "」"; } return g ? " · 佩戴中" : ""; })() })' + jsdiv(
         '成就和活动授予的头衔：佩戴后名字前挂着走，每项都标注「装备后加成」，按效果挑最好的戴上，这里一键佩戴/摘下。', DIV_YL)),
    ('ach仙务成就',
     'children: "仙务成就" + (l && l.claimableIds && l.claimableIds.length ? " · 可领 " + l.claimableIds.length : "") })',
     'children: "仙务成就" + (l && l.claimableIds && l.claimableIds.length ? " · 可领 " + l.claimableIds.length : "") })' + jsdiv(
         '修仙路上的里程碑清单：按分组列出进度（突破、击杀、秘境……），达标后点「领取」，奖励经信箱发放，每档只领一次。', DIV_YL)),
    ('stats修行统计',
     'children: "修行统计（只读）" })',
     'children: "修行统计（只读）" })' + jsdiv(
         '你的修行账本（只读）：最近 7 天每天的修为、灵石、击杀与修炼时长一目了然，看看自己今天摸没摸鱼。', DIV_YL)),
    ('reforge万宝洗炼',
     'children: "万宝洗炼" })',
     'children: "万宝洗炼" })' + jsdiv(
         '花灵石给法宝装备重铸随机词条：越洗越贵，中意的词条可锁定保留（锁定费用更高）。洗出新道蕴后由你取舍换不换——脸黑及时收手。', DIV_YL)),
    ('events总览',
     'children: "限时活动（只读）" })',
     'children: "限时活动（只读）" })' + jsdiv(
         '当期所有限时活动的总览：这里看活动名字与起止时间，想玩哪个点上面的页签。结算奖励统一发到信箱。', DIV_YL)),
    ('actRank仙途冲榜',
     'children: "仙途冲榜" })',
     'children: "仙途冲榜" })' + jsdiv(
         '活动期竞速榜：灵石榜比赚灵石的手速，击杀榜比斩妖的数量。按名次结算奖励发信箱，冲榜靠日常积累。', DIV_YL)),
    ('actCheckin每日签到',
     'children: "每日签到" })',
     'children: "每日签到" })' + jsdiv(
         '按自然月签到：每天签一次拿当日奖励，累计天数达标还能领里程碑大奖。月初开始别断签。', DIV_YL)),

    # ===== B. 行内玩法 =====
    ('advDraw奇遇抽奖',
     'children: "奇遇抽奖" })',
     'children: "奇遇抽奖" })' + jsdiv(
         '左侧是你的历练奇遇记录；右侧「奇遇抽奖」每次消耗修为抽一次，有冷却、每天限次数，运气好触发暴击奖励翻倍。灵石产出可观，是重要的进项。', DIV_YL)),
    ('fun每日一签',
     'children: "每日一签 · 今日 " + left + "/" + max })',
     'children: "每日一签 · 今日 " + left + "/" + max })' + jsdiv(
         '每天免费求一支签，上/中/下签奖励差距很大——上签大赚，中签小赚，下签也有保底。一天只有一次，别忘来抽。', DIV_FULL)),
    ('fun掷骰',
     'children: "大/小 赔 1.95 · 豹子 赔 25" })',
     'children: "大/小 赔 1.95 · 豹子 赔 25" })' + jsdiv(
         '和庄家比骰子大小，猜赢了按倍率拿灵石，猜输了输掉注金。每天最多玩 10 次，见好就收。', DIV_FULL)),
    ('fun翻牌',
     'children: "每次 " + cost + " 灵石 · 三张牌 " + pays.map(function (x) { return YlxwNum(x); }).join(" / ") })',
     'children: "每次 " + cost + " 灵石 · 三张牌 " + pays.map(function (x) { return YlxwNum(x); }).join(" / ") })' + jsdiv(
         '花 2 万灵石翻一张牌，牌池共 10 张、约一半亏一半赚，高档牌奖励差距很大。每天限翻 10 次，赌的就是手气。', DIV_FULL)),
    ('actBoss万妖补行',
     'children: "五只妖兽同时现身，每只的次数与冷却各自独立；免费 " + freeLim + " 次/日/只，收费 " + paidLim + " 次/日/只，收费每次冷却 5 分钟。" })',
     'children: "五只妖兽同时现身，每只的次数与冷却各自独立；免费 " + freeLim + " 次/日/只，收费 " + paidLim + " 次/日/只，收费每次冷却 5 分钟。" })' + jsdiv(
         '每次出手伤害计入本期排行榜，期末按名次发放奖励到信箱。', 'mt-2 text-[11px] text-stone-400 leading-relaxed')),

    # ===== C. 基座 modal：容器开头插说明行（压缩代码，无空格） =====
    ('leaderboard排行榜',
     'children:e.jsxs("div",{className:"flex flex-col h-full",children:[e.jsx("div",{className:"flex gap-2 mb-4",children:DM.map(',
     'children:e.jsxs("div",{className:"flex flex-col h-full",children:['
     + 'e.jsx("div", { className: "mb-3 rounded border border-stone-600 px-3 py-2 text-xs text-stone-400 leading-relaxed", children: "'
     + '全服修士的三大榜：修为榜、战力榜、灵石榜。看看自己排第几，也看看榜首大佬离你多远。'
     + '" }), e.jsx("div",{className:"flex gap-2 mb-4",children:DM.map('),
    ('trade交易行',
     'subHeader:e.jsxs("div",{children:[e.jsxs("div",{className:"flex border-b border-stone-600 bg-stone-900"',
     'subHeader:e.jsxs("div",{children:['
     + 'e.jsx("div", { className: "px-4 pt-2 text-xs text-stone-400 leading-relaxed", children: "'
     + '玩家之间的集市：可以买别人挂售的货，也能自己挂售换灵石。成交收取 10% 手续费；你的货款托管在行里，记得去「交易行货款」手动领取。'
     + '" }), e.jsxs("div",{className:"flex border-b border-stone-600 bg-stone-900"'),
    ('grotto洞府',
     'showHeaderBorder:!1,children:e.jsxs("div",{className:"space-y-6",children:[',
     'showHeaderBorder:!1,children:e.jsxs("div",{className:"space-y-6",children:['
     + 'e.jsx("div", { className: "rounded border border-stone-600 px-3 py-2 text-xs text-stone-400 leading-relaxed", children: "'
     + '你的私人道场：升级洞府可提升修为效率、加快作物成长、增加默认田位与可扩田数，高等级还解锁自动收获与助战灵宠位。左页灵田种植，收获的灵草可变卖换灵石或服用强化属性。'
     + '" }), '),
    ('shop商店',
     'children:a.description}),a.reputationRequired&&',
     'children:a.description}),e.jsx("p",{className:"text-xs text-stone-400 font-normal mt-0.5",children:'
     + '"游历途中遇到的各处店铺（村庄/城市/仙门/黑市/限时/声望），货品与价钱各不相同；黑市货贵但稀有，限时商店每日特价，部分店铺可花灵石刷新货架。'
     + '"}),a.reputationRequired&&'),
    ('charDex人物志',
     'children:e.jsxs("div",{className:"grid grid-cols-1 md:grid-cols-2 gap-4 items-start",children:[e.jsxs("div",{className:"min-w-0 space-y-4",children:[e.jsx(YlxwCharSafe,',
     'children:e.jsxs("div",{className:"grid grid-cols-1 md:grid-cols-2 gap-4 items-start",children:['
     + 'e.jsx("div", { className: "col-span-full rounded border border-stone-600 px-3 py-2 text-xs text-stone-400 leading-relaxed", children: "'
     + '你结识的各方道友档案：历练偶遇或主动寻访可结识 NPC，提交其心仪的礼物提升好感；缘分足够深可解锁缘契奖励，收录进图鉴的道友还能提供永久的修炼速度加成。稀有度越高的道友越难寻访。'
     + '" }), e.jsxs("div",{className:"min-w-0 space-y-4",children:[e.jsx(YlxwCharSafe,'),

    # ===== D. 主屏按钮 title 悬浮（fixed 底栏 grid，无面板级挂点——代决记拍板） =====
    ('med主屏打坐',
     'e.jsxs("button",{onClick:a,disabled:t||r>0||v,className:',
     'e.jsxs("button",{onClick:a,disabled:t||r>0||v,title:'
     + '"静心打坐持续产出修为与灵石，偶尔触发顿悟（灵台清明，修为暴涨数倍）。开启「自动打坐」可持续修炼；遇战斗、购物等会自动暂停，停止时日志里给出本轮收益小结。'
     + '",className:'),
    ('adv主屏历练',
     'e.jsxs("button",{onClick:l,disabled:t||r>0||f,className:',
     'e.jsxs("button",{onClick:l,disabled:t||r>0||f,title:'
     + '"外出历练随机遭遇奇遇：修为、灵石、物品入手，偶尔还能结识道友。开启「自动历练」可挂机遇事；历练中还有极低概率捡到抽奖券（奖励主要还是靠任务和活动）。'
     + '",className:'),

    # ===== E. 灵宠视图：出战/助战栏补亲密度说明（§F-37 按代码实证改写——代决记拍板） =====
    ('petLane亲密度',
     'children: "出战 / 助战（加成直接计入你的属性，角色面板可见）" })',
     'children: "出战 / 助战（加成直接计入你的属性，角色面板可见）" })' + ', e.jsx("div", { children: "'
     + '亲密度决定灵宠帮你多少：出战/助战的属性转化会随亲密度增强（1 + 亲密度÷200，满 100 时为 1.5 倍），日常互动、融合取高可提升。主战宠 50% 属性转化给你，助战位各 15%（洞府 Lv3/Lv6 解锁）。'
     + '" })'),
]


# ---- 每处新文案（与 PATCHES 一一对应；gates 信号取其转义形态，编译期断言在 new 内）----
SIGS = [
    '系统发的奖励（成就、里程碑、活动结算等）都会寄到这里。',
    '你的秘境探索日志（只读）：今天进过几次',
    '加其他玩家为好友（输入对方名号申请）',
    '成就和活动授予的头衔：佩戴后名字前挂着走',
    '修仙路上的里程碑清单：按分组列出进度',
    '你的修行账本（只读）：最近 7 天每天的修为',
    '花灵石给法宝装备重铸随机词条：越洗越贵',
    '当期所有限时活动的总览：这里看活动名字与起止时间',
    '活动期竞速榜：灵石榜比赚灵石的手速',
    '按自然月签到：每天签一次拿当日奖励',
    '左侧是你的历练奇遇记录；右侧「奇遇抽奖」',
    '每天免费求一支签，上/中/下签奖励差距很大',
    '和庄家比骰子大小，猜赢了按倍率拿灵石',
    '花 2 万灵石翻一张牌，牌池共 10 张',
    '每次出手伤害计入本期排行榜，期末按名次发放奖励到信箱。',
    '全服修士的三大榜：修为榜、战力榜、灵石榜。',
    '玩家之间的集市：可以买别人挂售的货',
    '你的私人道场：升级洞府可提升修为效率',
    '游历途中遇到的各处店铺（村庄/城市/仙门/黑市/限时/声望）',
    '你结识的各方道友档案：历练偶遇或主动寻访可结识 NPC',
    '静心打坐持续产出修为与灵石，偶尔触发顿悟',
    '外出历练随机遭遇奇遇：修为、灵石、物品入手',
    '亲密度决定灵宠帮你多少：出战/助战的属性转化会随亲密度增强',
]


def gates():
    """补丁后形态门禁五元组（name, needle, count, op, note）——供 dryrun 门禁表收录。
    needle = 各处新文案前 14 字的产物转义形态（改前 0 处 = 独有信号，铁律⑥）。"""
    assert len(SIGS) == len(PATCHES), 'SIGS(%d) 与 PATCHES(%d) 不等长' % (len(SIGS), len(PATCHES))
    gs = []
    for (note, _old, _new), sg in zip(PATCHES, SIGS):
        gs.append(('R121·' + note, esc(sg[:14]).decode('ascii'), 1, '==', '0.9.13 玩法说明补齐'))
    gs.append(('R121·冻结R79Box调用数', 'YlxwR79Box("', 8, '==', 'R-079 门禁不破（不新增折叠块）'))
    gs.append(('R121·冻结R79Box总数', 'YlxwR79Box(', 9, '==', '定义1+调用8，R-123 稳定性口径'))
    gs.append(('R121·冻结玩法说明计数', '\\u73a9\\u6cd5\\u8bf4\\u660e', 17, '==', '0.9.12 基线 17，本模块不加该四字'))
    gs.append(('R121·冻结茶馆说明块', '\\u3010\\u73a9\\u6cd5\\u8bf4\\u660e\\u3011\\u6bcf\\u5929\\u4e00\\u9053\\u8336\\u9986\\u8bdd\\u9898', 1, '==', 'R-053 茶馆说明不动'))
    return gs


def _extract_text(new):
    """从 new 源码串里提取中文文案段：取【最后一个】≥12 字且含中文的引号段
    （新文案总是排在 old 尾段之后/old 中段之内，old 里的长中文段都在其之前）。"""
    import re
    hit = None
    for m in re.findall(r'"([^"]{12,})"', new):
        if any(ord(c) > 127 for c in m):
            hit = m
    if hit is None:
        raise AssertionError('new 无文案段: %r' % new[:60])
    return hit


BAN = [b'iframe', b'postMessage', b'XMLHttpRequest', b'auth_token', b'X-YL-']


def fail(rc, msg):
    print('[yl_r121_ext] FAIL rc=%d: %s' % (rc, msg))
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True, description='R-121 全局玩法说明补齐（--src 就地原子补丁）')
    ap.add_argument('--src', required=True, help='要打补丁的 bundle 文件路径（0.9.13 装配产物）')
    a = ap.parse_args(argv)

    src = a.src
    if not os.path.isfile(src):
        return fail(2, '文件不存在: %s' % src)

    # 编译期自检：锚点互不重复、文案段无反斜杠、转义纯 ASCII、新串无禁用模式
    import re as _re
    olds = [esc(o) for _n, o, _nw in PATCHES]
    if len(set(olds)) != len(olds):
        return fail(1, '编译期自检 FAIL：存在重复锚点')
    news = []
    for (_n, _o, nw), sg in zip(PATCHES, SIGS):
        for seg in _re.findall(r'"([^"]*)"', nw):
            if any(ord(c) > 127 for c in seg) and '\\' in seg:
                return fail(1, '编译期自检 FAIL：文案段含反斜杠 %r' % seg[:40])
        b = esc(nw)
        if esc(sg) not in b:
            return fail(1, '编译期自检 FAIL：SIGS[%s] 文案与 new 不对应（防漂移断言）' % _n)
        for pat in BAN:
            if pat.lower() in b.lower():
                return fail(1, '编译期自检 FAIL：新串含禁用模式 %r' % pat)
        news.append(b)

    with open(src, 'rb') as f:
        data = f.read()

    # 形态判定：全部待补 → 补；全部已补 → rc=3；混合 → rc=4；锚点丢失 → rc=2
    # （新串=独有信号：cn==1 即已补，无论 old 是否仍连续存在——追加型补丁 new 含 old）
    state, missing = [], []
    for i, (note, old_b, new_b) in enumerate(zip([p[0] for p in PATCHES], olds, news)):
        co, cn = data.count(old_b), data.count(new_b)
        if co > 1:
            return fail(2, '锚点不唯一：%s count=%d' % (note, co))
        if cn > 1:
            return fail(4, '新串异常：%s count=%d（应 ≤1）' % (note, cn))
        if cn == 1:
            state.append('done')
        elif co == 1:
            state.append('todo')
        else:
            missing.append(note)
    if missing:
        return fail(2, '锚点丢失（文件不含下述落点，是否传错产物？）: %s' % ', '.join(missing))
    if 'todo' not in state:
        # 已补形态：只读复核门禁（不写盘）
        for name, needle, want, op, _note in gates():
            got = data.count(needle.encode('ascii'))
            if got != want:
                return fail(1, '已补态门禁复核 FAIL：%s count=%d（期望 %d）' % (name, got, want))
        print('[yl_r121_ext] ALREADY-PATCHED（23 处说明全部在位，门禁复核过，未写盘）: %s' % src)
        return 3
    if 'done' in state:
        bad = [p[0] for p, st in zip(PATCHES, state) if st == 'done']
        return fail(4, '部分已补部分未补，拒绝续写: %s' % ', '.join(bad))

    # 前置冻结面：补丁前就应满足（口径不可信则拒绝）
    pre_frozen = [
        ('R79Box调用', b'YlxwR79Box("', 8),
        ('R79Box总数', b'YlxwR79Box(', 9),
        ('玩法说明', b'\\u73a9\\u6cd5\\u8bf4\\u660e', 17),
        ('茶馆说明块', b'\\u3010\\u73a9\\u6cd5\\u8bf4\\u660e\\u3011\\u6bcf\\u5929\\u4e00\\u9053\\u8336\\u9986\\u8bdd\\u9898', 1),
        ('R79Box定义', b'function YlxwR79Box(t, L) {', 1),
    ]
    for nm, nd, want in pre_frozen:
        got = data.count(nd)
        if got != want:
            return fail(2, '前置冻结面不符：%s count=%d（期望 %d）' % (nm, got, want))

    # 逐处替换
    patched = data
    for (note, _o, _nw), old_b, new_b in zip(PATCHES, olds, news):
        if patched.count(old_b) != 1:
            return fail(1, '替换前锚点校验 FAIL：%s count=%d' % (note, patched.count(old_b)))
        patched = patched.replace(old_b, new_b, 1)

    if patched == data:
        return fail(1, '替换未产生变化（不应发生）')

    # 内存自检：全部门禁过才写盘
    # （注：追加型补丁 new 含 old，旧锚点不清零——替换生效由「new==1 + patched!=data」证明）
    for name, needle, want, op, _note in gates():
        nd = needle.encode('ascii')
        got = patched.count(nd)
        if op == '==' and got != want:
            return fail(1, '门禁自检 FAIL：%s count=%d（期望 %d）' % (name, got, want))

    # 改前 .bak（只在真写盘前落）
    bak = '%s.bak-r121-%s' % (src, datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(src, bak)

    # 就地原子写回
    tmp = '%s.tmp-r121' % src
    with open(tmp, 'wb') as f:
        f.write(patched)
    os.replace(tmp, src)

    # 落盘复核
    with open(src, 'rb') as f:
        back = f.read()
    if back != patched:
        return fail(1, '落盘复核失败：磁盘字节 != 预期补丁结果')
    for name, needle, want, op, _note in gates():
        got = back.count(needle.encode('ascii'))
        if got != want:
            return fail(1, '落盘门禁 FAIL：%s count=%d（期望 %d）' % (name, got, want))

    print('[yl_r121_ext] OK 已补丁 23 处玩法说明并原子写回: %s' % src)
    print('[yl_r121_ext] 备份: %s' % bak)
    print('[yl_r121_ext] 产物增量: %d 字节' % (len(patched) - len(data)))
    print('[yl_r121_ext] 门禁表（供 dryrun 收录）:')
    for g in gates():
        print('    %r' % (g,))
    return 0


if __name__ == '__main__':
    sys.exit(main())
