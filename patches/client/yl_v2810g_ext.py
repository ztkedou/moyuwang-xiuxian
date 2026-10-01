# -*- coding: utf-8 -*-
r"""yl_v2810g_ext.py -- 演武场周榜面板（0.8.10 · 0.8.10 待办池 P1 的客户端半边）

## 为什么有这一环

服务端第 22 环（`srv_patch_arenaweek.py`）把 T16 周榜**结算**补齐了（每周一 0 点按积分发奖、
第 1 名称号「太虚魁首」、本周满 10 场参与奖，全部走邮件）。
但客户端此前**只有一句帮助文案**（`yl_t16arena_ext.py` 的玩法说明），
**没有任何界面**能让玩家看到榜单与自己名次 ⇒ 本模块补上这块「可见性」。

## 改动（2 处，都在论剑区内，不新增页签、不动三区分栏结构）

| # | 锚点 | 改动 |
|---:|---|---|
| 1 | `function YlxwArenaLadderZone(props) {` 之前 | 新增 `YlxwArenaWeekZone` 组件（自取 `/arena/week`） |
| 2 | 论剑区 Fragment 收尾（`children: board }))` 那一行的 `] })` 之后） | 追加一个 `e.jsx(YlxwArenaWeekZone, {})` 子节点 |

渲染内容：标题 + 我的名次/积分 + 本周论剑场次与参与奖进度 + 最近结算周 + TOP10 榜单（名次/道号/段位/积分/档位标记）。

## 依赖的既有符号（全部已在论剑区使用，零新增）

`YlxwUseList`（取数）/ `YlxwRow`（行容器）/ `YlxwErr`（错误+重试）/ `YlxwEmpty`（空态）/ `YlxwNum`（数值归一）。

## 硬约束遵守

  · 只新建本文件 + 修改 `build_v26n.py` / `localtest/dryrun_087.py` 接线；**不写回 build/assets/**。
  · 注入块 zh() 后纯 ASCII；不含禁用模式 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-。
  · 每个 replace 带 expect=精确次数；`apply()` 返回门禁五元组列表。
  · ★ 坑 2：门禁 needle 落在注入块内 ⇒ 一律用 `zh()` 之后的**转义形态**。
"""

# --------------------------------------------------------------------------- 锚点
A1 = 'function YlxwArenaLadderZone(props) {'

# 论剑区 Fragment 收尾（含 `children: board` 那行的闭合）。整段在产物里唯一。
A2_OLD = 'children: board }))\n    ] })\n  ] });\n}'
A2_NEW = ('children: board }))\n    ] }),\n'
          '    e.jsx(YlxwArenaWeekZone, {})\n'
          '  ] });\n}')

# --------------------------------------------------------------------------- 注入片段
WEEK_COMP = r"""/* --- \u533a 2b\uff1a\u5468\u699c\uff080.8.10 [arenaweek] \u65b0\u589e\uff1b\u6570\u636e\u6e90 GET /arena/week\uff09 --- */
function YlxwArenaWeekZone(props) {
  var wk = YlxwUseList("/arena/week"), d = wk.data, err = wk.err, busy = wk.busy;
  var hd = e.jsx("span", { className: "text-xs text-amber-300 font-bold", children: "\u5468\u699c \u00b7 \u6bcf\u5468\u4e00 0 \u70b9\u7ed3\u7b97" });
  if (err) return e.jsxs(YlxwRow, { children: [hd, e.jsx(YlxwErr, { retry: wk.load, children: err })] });
  if (busy && !d) return e.jsx(YlxwRow, { children: hd });
  var me = (d && d.me) || {};
  var rows = (d && d.board) || [];
  var top = YlxwNum(d && d.top) || 10;
  var part = YlxwNum(d && d.participateAt) || 10;
  var myRank = me.rank == null ? "\u672a\u4e0a\u699c" : ("\u7b2c " + me.rank + " \u540d");
  var list = rows.slice(0, top).map(function(p, i) {
    var rk = p.rank == null ? (i + 1) : p.rank;
    var tag = rk === 1 ? "\u9b41\u9996" : (rk <= 3 ? "12000\u00d7" : (rk <= top ? "6000\u00d7" : ""));
    return e.jsxs("div", { className: "flex items-center justify-between gap-2 text-xs", children: [
      e.jsxs("span", { children: [
        e.jsx("span", { className: "text-stone-500 font-mono mr-1.5", children: "#" + rk }),
        e.jsx("span", { className: "text-stone-100", children: p.name || "\u2014" }),
        e.jsx("span", { className: "text-stone-500 ml-2", children: (p.tierName || "") + " \u00b7 " + YlxwNum(p.points) + " \u5206" })
      ] }),
      e.jsx("span", { className: "text-amber-300", children: tag })
    ] }, "wk" + i);
  });
  return e.jsxs(YlxwRow, { children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      hd,
      e.jsx("span", { className: "text-xs text-stone-300", children: "\u6211\u7684\u540d\u6b21 " + myRank + " \u00b7 " + YlxwNum(me.points) + " \u5206" })
    ] }),
    e.jsx("div", { className: "text-xs text-stone-400 pt-1", children:
      "\u672c\u5468\u8bba\u5251 " + YlxwNum(me.matches) + " \u573a" + (me.participated ? "\uff08\u5df2\u8fbe\u6210\u53c2\u4e0e\u5956\uff09" : ("\uff08\u6ee1 " + part + " \u573a\u5f97\u53c2\u4e0e\u5956\uff09")) +
      (d && d.lastSettleWeek ? (" \u00b7 \u4e0a\u6b21\u7ed3\u7b97 " + d.lastSettleWeek) : "") }),
    e.jsx("div", { className: "text-xs text-stone-500 pt-0.5", children: "\u7b2c 1 \u540d\u53e6\u5f97\u79f0\u53f7\u300c\u592a\u865a\u9b41\u9996\u300d\uff1b\u540d\u6b21\u5956\u9700\u672c\u5468\u81f3\u5c11\u51fa\u6218 1 \u573a\u3002" }),
    e.jsx("div", { className: "space-y-1.5 pt-1", children: list.length ? list : e.jsx(YlxwEmpty, { children: "\u672c\u5468\u6682\u65e0\u79ef\u5206\u8bb0\u5f55" }) })
  ] });
}

"""


def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 1) 新增周榜组件（插在论剑区组件定义之前）
    p.insert_before('v2810g-weekcomp', A1, zh(WEEK_COMP),
                    expect=1, note='新增 YlxwArenaWeekZone（周榜：我的名次 + 本周场次 + TOP10）')

    # 2) 论剑区尾部挂载周榜子节点
    p.replace('v2810g-weekrender', A2_OLD, A2_NEW,
              expect=1, note='论剑区 Fragment 追加 e.jsx(YlxwArenaWeekZone, {})')

    # ------------------------------------------------------------- 门禁
    gates = [
        ('P1·周榜组件定义恰 1',      'function YlxwArenaWeekZone(',        1, '==', ''),
        ('P1·周榜数据源端点',        '"/arena/week"',                      1, '==', ''),
        ('P1·论剑区已挂载周榜',      'e.jsx(YlxwArenaWeekZone, {})',       1, '==', ''),
        ('P1·论剑区组件仍在',        'function YlxwArenaLadderZone(',      1, '==', '基线未动'),
        ('P1·战力榜收尾未破',        'children: board }))',               1, '==', '基线未动'),
        # —— 注入块内的 needle 一律用转义形态（坑 2）；needle 必须**唯一** ——
        ('P1·标题（转义形态）',       zh('周榜 · 每周一 0 点结算'),          1, '==', ''),
        ('P1·我的名次（转义形态）',    zh('"我的名次 " + myRank'),            1, '==', '★ 带上下文，避开仙途冲榜面板同名词'),
        ('P1·参与奖进度（转义形态）',  zh('场得参与奖'),                     1, '==', ''),
        ('P1·魁首标记（转义形态）',    zh('"魁首"'),                        1, '==', ''),
        ('P1·称号提示（转义形态）',    zh('另得称号「太虚魁首」'),             2, '==', '本模块 1 + T16 玩法说明 1（假承诺文案仍在）'),
        ('P1·空态（转义形态）',       zh('本周暂无积分记录'),                1, '==', ''),
        # —— 复用既有符号（零新增 helper） ——
        ('P1·复用 YlxwUseList',      'var wk = YlxwUseList("/arena/week")', 1, '==', ''),
        ('P1·组件引用恰 2',          'YlxwArenaWeekZone',                  2, '==', '定义 1 + 挂载 1'),
        # —— 禁用模式：**不在此处断言全文**（基座/其它模块本就含 iframe 等）；
        #    build_v26n.py:780 已对**每个注入块**逐块断言 V28_BAN_PATTERNS。 ——
    ]
    return gates
