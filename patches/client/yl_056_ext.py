# -*- coding: utf-8 -*-
r"""
yl_056_ext.py — R-056 活动中心·万妖（万兽）巢穴：多 boss + 每只 5 次免费 + 10 分钟冷却（客户端半边）

需求（台账 R-056 原文，进行中.md:27）
--------------------------------------------------------------------------
  「万兽巢穴增加boss数量，每日不设置上限，但是加冷却时间，10分钟一次。免费的次数每一个boss5次。」

口径说明
--------------------------------------------------------------------------
  游戏内实际名为「万妖巢穴」（\u4e07\u5996\u5de2\u7a74，活动中心 tab D，组件 YlxwTActBoss，
  yl_act087_ext.py 注入），用户口中的「万兽巢穴」即此玩法，别无他处。

  现状（侦察 v28115 bundle @1113673 + srv/index_v28.ts:8848/:9215/:9249）：
    · 每期 boss_raid 活动**只有 1 只**妖兽（event_boss.event_id 主键）；
    · 免费出手 **3 次/日**（ACT_BOSS_FREE_STRIKES=3，fun_daily kind='raid' 计数）；
    · 诛妖符 2 张/日（本需求不动）。

  本环客户端改 6 处（全在 YlxwTActBoss 函数体内，全为就地替换，INJECT_JS=''）：
    ① 新增 bossNo / bossMax / coolLeft 三个状态变量（读服务端 status 新回执字段）；
    ② 面板标题追加「· 第 X/Y 只」；
    ③ 「今日免费剩余」→「本只免费剩余」（口径从每日改每只）；
    ④ 状态行尾追加「· 出手冷却 N 秒」（coolLeft>0 时）；
    ⑤ 出手按钮：disabled 加 coolLeft>0，冷却中按钮文字变「冷却 N 分」；
    ⑥ 讨灭横幅文案分叉：非最终只→「下一只妖兽即将现身」，最终只→原文「奖励结算中」。

服务端半边（srv_patch_056.py，另一环，两者配套）
--------------------------------------------------------------------------
  ACT_BOSS_FREE_STRIKES 3→5（口径改每只，event_boss_hits.free_used 随换 boss 归零）+
  ACT_BOSS_MAX_BOSSES=5（每期连刷 5 只，诛一只当场现身下一只）+
  ACT_BOSS_STRIKE_COOLDOWN_MS=10 分钟（event_boss_hits.last_strike_at）+
  第 n 只血量 = 基础×(1+0.5×(n-1))。status 回执新增 bossNo/bossMax/coolLeft。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 只动 YlxwTActBoss 函数体内 6 处；不碰页签数组、不碰三个兄弟子页签函数
    （R-054 签到 / R-055 灵玉阁是并行工友的面，冻结门禁盯住）。
  · act087 门禁依赖的三条计数一律保持：`!engineOn`==4、`{ eventId: ev.id }`==3、
    `actKey !== ""`==3（本环只在 disabled 里**插入** `|| coolLeft > 0`，不删不改原有项）。
  · 新串中文全部 \uXXXX 转义（与 act087 注入块形态一致），落 bundle 纯 ASCII；
    apply 内自检 isascii + V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/auth_token/X-YL-）。
  · 锚点全部 count==1（2026-10-01 对 v28115 逐字节验证，见模块尾自检脚本输出）。
  · 不碰 build_v26n.py / localtest/ / srv/index_v28.ts / CHANGELOG.md / yl_version_ext.py。
"""

import re

INJECT_JS = ''          # 纯就地替换，不需要注入块

# --------------------------------------------------------------------------- 锚点
# 全部为 v28115 bundle 中的逐字节原文（act087 注入块的 \uXXXX 转义形态 + 真实换行/缩进）。

# ① 状态变量行（YlxwTActBoss 函数体内，唯一）
A_VARS = (
    '  var freeLeft = YlxwNum(d && d.freeLeft), talLeft = YlxwNum(d && d.talismanLeft);\n'
)

# ② 面板标题（YlxwTitle 的 children，转义形态全 bundle 唯一；页签数组是 ["boss", "..."] 形态，不相干）
A_TITLE = 'children: "\\u4e07\\u5996\\u5de2\\u7a74" })'

# ③ 「今日免费剩余」（本环改为「本只」，配服务端每只 5 次口径）
A_TODAY = '\\u4eca\\u65e5\\u514d\\u8d39\\u5269\\u4f59'

# ④ 状态行尾（…妖符剩余 N 次" }) 的收尾，唯一；在它后面拼冷却段）
A_TAIL = '+ talLeft + " \\u6b21" })'

# ⑤ 出手按钮 disabled（原形态唯一；诛妖符按钮的 disabled 是 talLeft <= 0 形态，不相干）
A_BTN = 'disabled: busy || killed || freeLeft <= 0 || !engineOn'

# ⑤' 出手按钮 label（原形态唯一）
A_LABEL = (
    'children: busy && act.actKey === "boss-strike" ? "\\u51fa\\u624b\\u4e2d\\u2026" : '
    '"\\u51fa\\u624b\\uff08\\u514d\\u8d39\\uff09" })'
)

# ⑥ 讨灭横幅结算尾（"…，奖励结算中。" 收尾，唯一）
A_KILLED = '+ "\\uff0c\\u5956\\u52b1\\u7ed3\\u7b97\\u4e2d\\u3002" })'


# --------------------------------------------------------------------------- 组装

def _repl(zh):
    r"""六个替换的新串（中文一律经 zh() 转 \uXXXX，落 bundle 纯 ASCII）。"""
    r_vars = (
        A_VARS
        + '  var bossNo = YlxwNum(d && d.bossNo) || 1, '
        + 'bossMax = YlxwNum(d && d.bossMax) || 5, '
        + 'coolLeft = YlxwNum(d && d.coolLeft);\n'
    )
    r_title = (
        'children: "' + zh('万妖巢穴 · 第 ') + '" + bossNo + "/" + bossMax + "' + zh(' 只') + '" })'
    )
    r_today = zh('本只免费剩余')
    r_tail = (
        '+ talLeft + " ' + zh('次') + '" + (coolLeft > 0 ? " \\u00b7 ' + zh('出手冷却 ')
        + '" + coolLeft + "' + zh(' 秒') + '" : "") })'
    )
    r_btn = 'disabled: busy || killed || freeLeft <= 0 || coolLeft > 0 || !engineOn'
    r_label = (
        'children: busy && act.actKey === "boss-strike" ? "' + zh('出手中…') + '" : '
        '(coolLeft > 0 ? "' + zh('冷却 ') + '" + Math.ceil(coolLeft / 60) + "' + zh(' 分')
        + '" : "' + zh('出手（免费）') + '") })'
    )
    r_killed = (
        '+ (bossNo < bossMax ? "' + zh('，下一只妖兽即将现身。') + '" : "'
        + zh('，奖励结算中。') + '") })'
    )
    return r_vars, r_title, r_today, r_tail, r_btn, r_label, r_killed


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    zh = ctx['zh']

    r_vars, r_title, r_today, r_tail, r_btn, r_label, r_killed = _repl(zh)

    # 自检：新串落 bundle 必须纯 ASCII（zh() 转义生效），且不含禁用模式 / 已知 0-期望门禁字面
    for tag, s in (('vars', r_vars), ('title', r_title), ('today', r_today), ('tail', r_tail),
                   ('btn', r_btn), ('label', r_label), ('killed', r_killed)):
        if not s.isascii():
            raise AssertionError('r056 新串(%s)含非 ASCII：zh() 转义失效' % tag)
        for bad in ('iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-', 'fetch('):
            if bad in s:
                raise AssertionError('r056 新串(%s)含危险字面: %r' % (tag, bad))

    p.replace('r056-vars', A_VARS, r_vars, expect=1,
              note='新增 bossNo/bossMax/coolLeft 三状态变量（读 status 新回执）')
    p.replace('r056-title', A_TITLE, r_title, expect=1,
              note='面板标题追加「· 第 X/Y 只」')
    p.replace('r056-today', A_TODAY, r_today, expect=1,
              note='「今日免费剩余」→「本只免费剩余」（口径每日→每只）')
    p.replace('r056-tail', A_TAIL, r_tail, expect=1,
              note='状态行尾追加「· 出手冷却 N 秒」')
    p.replace('r056-btn', A_BTN, r_btn, expect=1,
              note='出手按钮 disabled 加冷却闸（原 !engineOn 项原样保留在尾部）')
    p.replace('r056-label', A_LABEL, r_label, expect=1,
              note='冷却中按钮文字「冷却 N 分」（请求中分支原样）')
    p.replace('r056-killed', A_KILLED, r_killed, expect=1,
              note='讨灭横幅分叉：非最终只→下一只现身；最终只→奖励结算中')

    gates = [
        # ================= 本模块改动（新形态在位） =================
        ('R56→R113·选择态 state 就位', 'var ss = O.useState(1), sel = ss[0], setSel = ss[1];', 1, '==', 'R-113 接管：五只同现逐只选择器'),
        ('R56→R113·逐只回执数组',    'var bosses = (d && d.bosses) || [];', 1, '==', 'R-113 接管：服务端新回执 bosses[]'),
        ('R56→R113·免费上限读回执',  'freeLim = YlxwNum(d && d.freeLimit) || 5', 1, '==', 'R-113 接管：免费 5 次/日/只'),
        ('R56→R113·五只同现标题',    zh('万妖巢穴 · 五只同现'), 1, '==', 'R-113 接管：不再是「第 X/Y 只」'),
        ('R56·「本只免费剩余」',     zh('本只免费剩余'), 1, '==', '口径每日→每只'),
        ('R56→R113·逐只免费冷却显示', '" ' + zh('· 免费冷却 ') + '" + YlxwNum(cur.freeCoolLeft) + "' + zh(' 秒') + '"', 1, '==', 'R-113 接管'),
        ('R56→R113·免费按钮逐只闸',  'disabled: busy || cur.killed || YlxwNum(cur.freeLeft) <= 0 || YlxwNum(cur.freeCoolLeft) > 0 || !engineOn', 1, '==', 'R-113 接管'),
        ('R56→R113·收费按钮逐只闸',  'disabled: busy || cur.killed || YlxwNum(cur.paidLeft) <= 0 || YlxwNum(cur.paidCoolLeft) > 0 || !engineOn', 1, '==', 'R-113 接管：收费 10 次/日/只 + 5 分钟冷却'),
        ('R56·横幅分叉已清零',      '(bossNo < bossMax ? ', 0, '==', 'R-113 五只同现 ⇒ 顺序现身横幅消失'),
        ('R56·旧结算尾已清零',      zh('，奖励结算中。') + '") })', 0, '==', 'R-113 接管'),
        # ================= 本模块改动（旧形态清零） =================
        ('R56·旧每日口径已清零',     zh('今日免费剩余'), 0, '==', '「今日免费剩余」必须为 0'),
        ('R56·旧按钮 disabled 已清零', 'disabled: busy || killed || freeLeft <= 0 || !engineOn', 0, '==', '已被冷却闸版取代'),
        ('R56·旧按钮 label 已清零',  'children: busy && act.actKey === "boss-strike" ? ' + '"' + zh('出手中…') + '" : ' + '"' + zh('出手（免费）') + '" })', 0, '==', ''),
        ('R56·旧标题已清零',        'children: "\\u4e07\\u5996\\u5de2\\u7a74" })', 0, '==', '已带「第 X/Y 只」'),
        ('R56·旧结算尾已清零',      '+ "\\uff0c\\u5956\\u52b1\\u7ed3\\u7b97\\u4e2d\\u3002" })', 0, '==', '已改条件分叉'),
        ('R56·旧冷却三分支已清零',   'coolLeft > 0', 0, '==', 'R-113 逐只冷却闸取代（见 r113 门禁）'),
        # ================= 冻结：并行工友与 act087 门禁面一字未动 =================
        ('冻结·boss 组件仍唯一',     'function YlxwTActBoss(p) {', 1, '==', 'act087 注入'),
        ('冻结·boss 页签未动',      '["boss", "\\u4e07\\u5996\\u5de2\\u7a74"]', 1, '==', '页签数组本环不碰'),
        ('冻结·出手调用未动',       '"boss-strike", "/eventboss/strike"', 1, '==', 'R-113 改带 bossNo（act087 门禁 T5·⑦ 的端点面仍在）'),
        ('冻结·诛妖符调用未动',     '"boss-talisman", "/eventboss/talisman"', 1, '==', 'R-113 改带 bossNo'),
        ('冻结·诛妖符按钮未动',     '"\\u8bdb\\u5996\\u7b26\\u8ffd\\u52a0\\uff081 \\u5c0f\\u65f6\\u65f6\\u85aa/\\u6b21\\uff09"', 1, '==', 'R-055 邻面'),
        ('冻结·status GET 未动',    '"/eventboss/status?eventId="', 1, '==', 'act087 门禁 T5·⑥'),
        ('冻结·engineOn 计数不变',  '!engineOn', 7, '==', 'v28115 基线 5；r054 重写签到段 −1+3、r056 冷却闸原地 +0 ⇒ 终态 7（lead 接线校准 2026-10-01）；act087 门禁 >=4 仍满足'),
        ('冻结·eventId body 计数 3', '{ eventId: ev.id }', 3, '==', 'act087 门禁 T5·event body'),
        ('冻结·busy 锁计数 3',      'actKey !== ""', 3, '==', 'act087 门禁 T5·busy 锁'),
        ('冻结·签到页签函数未动',    'function YlxwTActCheckin(', 1, '==', 'R-054 工友面'),
        ('冻结·灵玉阁页签函数未动',  'function YlxwTActShop(', 1, '==', 'R-055 工友面'),
        ('冻结·冲榜页签函数未动',    'function YlxwTActRank(', 1, '==', ''),
        ('冻结·血量行未动',         '" / " + YlxwNum(cur.hpMax)', 1, '==', 'R-113 改为「第 N 只血量 x / y」'),
    ]
    return gates
