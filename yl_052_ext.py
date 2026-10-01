# -*- coding: utf-8 -*-
r"""
yl_052_ext.py — R-052 仙途任务：今日进度没有正常计入本周活跃度（周活跃度恒显 0）

问题（用户 R-052 + 附图 R-052-1.png）
--------------------------------------------------------------------------
  仙途任务面板：今日进度 54 / 330 正常走条，但「本周勤修」恒 0 / 2310、
  五档勤修里程碑全部 0%「未达成」——当天明明已有 54 点活跃度，周进度却是 0。

根因（证据链，全部实证于本机冻结产物 index-v28113-20260930.js + srv/index_v28.ts）
--------------------------------------------------------------------------
  服务端是对的，**客户端读错了字段**：

  1. 服务端 `srv/index_v28.ts` `GET /api/quest/summary` 回包（T9 起形态未变）：
         res.json({ ..., week, weekActivity, weekMax: ACTIVITY_MAX * 7, ... })
     其中 `week` = `bjWeekStart(nowMs)` ⇒ **周一日期字符串**（如 "2026-09-28"），
     周活跃度数值在 **`weekActivity`**（= collectWeeklyActivity，7 天读时计算求和，含今天）。
  2. 客户端面板 `YlxwTQuest2`（yl_t9quest_ext.py INJECT_JS 产出，bundle @889980）：
         var week = YlxwNum(l && l.week);        ← 读的是**日期串**
  3. `YlxwNum(r) { return Number(r) || 0; }`（bundle @862120）
     ⇒ Number("2026-09-28") = NaN ⇒ 0。**周活跃度自 T9 上线起恒显 0**，
        五档里程碑 `week >= m.tier` 恒 false ⇒ 永远「未达成」。
  4. 佐证：bundle 里 `weekActivity` 出现 **0 次** —— 数值字段从未被任何客户端代码读过。
     （今日进度正常：`l.activity` 是数值，读对了。）

本模块动作
--------------------------------------------------------------------------
  一行修（同面板先例 yl_claimedfix_ext.py：改「生产者/读取点」单行，不碰渲染体）：

      旧:  var week = YlxwNum(l && l.week);
      新:  var week = YlxwNum(l && l.weekActivity);

  · 只改这一个读取点。`YlxwQMileZone` 消费的 `week` prop 从此拿到真数值，
    「本周勤修 x/2310」「勤修·初~满 进度/还差/领取」全部随之恢复 —— 无需改渲染体。
  · 服务端**一个字不动**（回包里 week/weekActivity 两字段都保留，形状不变；
    不改服务端 ⇒ 对其它潜在消费方零风险，也免一条 srv 补丁链）。
  · 不做 `l.week` 回退：它是日期串，回退没有数值意义；t9 之前的服务端本就
    `week`/`milestones` 双缺 ⇒ 面板周区靠 `(l.week != null || l.milestones != null)`
    门整块隐藏，降级路径不受本改动影响。

门禁设计（冻结面：证明没碰相邻需求）
--------------------------------------------------------------------------
  · 正向：新读取点恰 1 处；旧日期串读取清零（`l.week)` 带右括号边界，
    不会误匹配 `l.weekActivity)` —— §19.2 反查带边界教训）。
  · 冻结 t9quest：面板组件 / 今日进度 `l.activity` 读取 / 里程碑端点 / 周上限 2310。
  · 冻结 claimedfix：`claims` 数组→映射行（同为 T9 面板相邻修，不得被波及）。
  · 冻结 r013c：五档 `YlxwQMile` 表最终形态（2310 档传承石行，\u 转义串比对）。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 纯就地替换、无 INJECT_JS、不引入任何新符号；锚点与替换串纯 ASCII。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py / localtest/ / deploy_v28/ / srv/index_v28.ts /
    yl_version_ext.py / CHANGELOG.md，不写 build/assets/。
  · 注入/替换内容不含 iframe / postMessage / XMLHttpRequest / auth_token / X-YL-。
"""

import re

INJECT_JS = ''          # 本模块纯就地替换，不需要注入块

# --------------------------------------------------------------------------- 锚点

# 旧：读 summary 回包里的 `week`（= 周一日期串 "YYYY-MM-DD"），Number() 后恒 NaN→0
ANCHOR_OLD = 'var week = YlxwNum(l && l.week);'

# 新：读真正的周活跃度数值字段 `weekActivity`（服务端 T7 起一直下发，客户端从未读过）
ANCHOR_NEW = 'var week = YlxwNum(l && l.weekActivity);'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, ...}（本模块锚点纯 ASCII，zh 仅作等值校验用）"""
    zh = ctx['zh']

    # 纪律自检：锚点/替换串必须纯 ASCII（本模块无中文，zh 应为等值）
    for tag, s in (('ANCHOR_OLD', ANCHOR_OLD), ('ANCHOR_NEW', ANCHOR_NEW)):
        if re.findall(r'[^\x00-\x7f]', s):
            raise AssertionError('r052 %s 含非 ASCII: %r' % (tag, s))
        if zh(s) != s:
            raise AssertionError('r052 %s 经 zh() 后变形（应为等值）' % tag)
    if ANCHOR_OLD == ANCHOR_NEW:
        raise AssertionError('r052 ANCHOR_OLD == ANCHOR_NEW')
    if ANCHOR_NEW.count('weekActivity') != 1 or ANCHOR_OLD.count('weekActivity') != 0:
        raise AssertionError('r052 锚点串异常：weekActivity 计数不符')

    p.replace('r052-week-field', ANCHOR_OLD, ANCHOR_NEW, expect=1,
              note='周活跃度改读数值字段 weekActivity（原读 week 日期串 ⇒ NaN→0 恒显示 0）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本模块改动 =================
        ('R52·周活跃度改读 weekActivity', 'var week = YlxwNum(l && l.weekActivity);', 1, '==', '服务端 summary 一直下发的数值字段'),
        ('R52·旧日期串读取已清零',       'YlxwNum(l && l.week)', 0, '==', '右括号边界，不误伤 l.weekActivity)'),
        # ================= 冻结：t9quest 面板本体未动 =================
        ('冻结·今日进度仍读 l.activity',  'var activity = YlxwNum(l && l.activity);', 1, '==', '日活跃度读取点不受影响'),
        ('冻结·周区渲染门未动',          '(l.week != null || (l.milestones != null))', 1, '==', 't9 优雅降级门保持原样'),
        ('冻结·周里程碑卡组件未动',      'function YlxwQMileZone(', 1, '==', '渲染体零改动'),
        ('冻结·周上限 2310 未动',        'var YlxwQWeekMax = 2310;', 1, '==', ''),
        ('冻结·里程碑领取端点未动',      '"/quest/milestone"', 1, '==', ''),
        ('冻结·面板组件仍唯一',          'function YlxwTQuest2(r) {', 1, '==', ''),
        # ================= 冻结：claimedfix 相邻修未动 =================
        ('冻结·claims 映射行未动',       'var claims = {}; (l && l.milestones || []).forEach', 1, '==', 'claimedfix 产物，波及即打爆 R-031 收尾'),
        # ================= 冻结：r013c 五档表最终形态未动 =================
        ('冻结·2310 档传承石行未动',
         'tier: 2310, name: "\\u52e4\\u4fee\\u00b7\\u6ee1", base: 60000, ticket: 30, extra: "\\u4f20\\u627f\\u77f3 \\u00d71\\uff08\\u6bcf\\u6708\\u9650\\u9886\\uff09"',
         1, '==', 'r013c 产物（R-028 拍板形态）'),
    ]
    return gates
