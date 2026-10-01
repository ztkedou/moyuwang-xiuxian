# -*- coding: utf-8 -*-
r"""
yl_r081_ext.py — R-081 宗门俸禄（按职位每日领取）· 客户端半边

复刻目标（上游 JeasonLoop/react-xiuxian-game a8f9810a）
--------------------------------------------------------------------------
  constants/sects.ts: SECT_RANK_SALARY = { 外门/内门/核心/长老/宗主 -> {baseSpiritStones, contribution} }
  SectModal: onClaimSalary 回调 + 每日领取。
  （上游原只有 SECT_LEADER_SALARY 宗主俸禄，本次提交改为「按职位发」。）

★ 我们这边的实况（本次侦察）
--------------------------------------------------------------------------
  职位体系（客户端 `ot` 枚举 + `m3` 标题表，产物逐字实证）：
      外门弟子 / 内门弟子 / **真传弟子** / 长老 / 宗主
      （注意：我们的第 3 档叫「真传弟子」，不是上游的「核心」。）
  贡献值 `player.sectContribution`：来自宗门任务阁 getReward（`contribution: floor((50+rand*70)*t*r*a*l)`，
      职衔系数 t=外门1/内门1.5/真传2/长老·宗主3）、捐献回馈 2%（日帽 1000）、职衔晋升一次性。
      日收入量级 1.2k~6k（服务端注释 line 13911 同口径）。
  俸禄现状：客户端主 bundle **无任何俸禄 UI**（「俸禄」x0）；服务端 V27「仙盟」另有
      `/api/sect/welfare/claim` kind=salary（= 宗门等级×500 灵石，**等级制**、只发灵石、走
      `sect_members` 成员表）—— 与上游的「按职位」不是一回事，且伴生页不在本仓。
      ⇒ 本需求在**基础宗门页（lM）**上从零实装「按职位俸禄」，服务端权威 + 幂等。

本模块动作（1 处注入 + 1 处插入）
--------------------------------------------------------------------------
  E1 注入自包含组件 `YlxwTSectSalary`（模块作用域，自带 state / 请求 / 领取逻辑）。
  E2 插进基础宗门页「宗门大殿(hall)」页签首个子节点。

数据流（服务端权威 + 余额回显）
--------------------------------------------------------------------------
  · GET  /api/sect/salary/status -> { inSect, rank, spiritStones, contribution, claimed, date }
  · POST /api/sect/salary        -> { message, rank, reward:{spiritStones,contribution}, contribution, balance }
  · 灵石：`/api/sect/*` 命中服务端 YL_STONE_ECHO_V26K 回显中间件 ⇒ `YlxwApi` 内 `YLApplyBalance`
    自动把本地 spiritStones 覆盖成服务端权威值（无需本模块插手）。
  · 贡献：回执 `contribution` 字段由本组件回填 zustand（`Be.setState`，与 YLApplyBalance 同款写法），
    随下次 /api/save 推档；单日 300 远低于 E2:sectContrib 差值钳（20/分 + 5000 兜底）。
  · 幂等：服务端 `sect_welfare_claims` PK(user_id,date,kind='rank_salary')，UNIQUE 冲突即 409。

硬约束 / 纪律
--------------------------------------------------------------------------
  · INJECT_JS 走 zh()：中文注释由 zh() 转义；JS 字面量一律**直接写 \uXXXX**（zh 不动 ASCII 反斜杠）。
  · 注入块不含 V28_BAN_PATTERNS；不改任何既有模块；每个 replace 带 expect=精确次数。
  · 只新建本文件；不改 build_v26n.py / localtest/* / srv/index_v28.ts。
"""

import re

# --------------------------------------------------------------------------- 注入块
# 说明：JS 字符串里的中文一律直接写 \uXXXX（zh() 后形态稳定，便于门禁逐字断言）；
#       注释里的中文由 ctx['zh'] 统一转义。

INJECT_JS = r'''
/* ===== yl-R081: 宗门俸禄（按职位每日领取）=====
   职位 = 存档 player.sectRank（外门弟子/内门弟子/真传弟子/长老/宗主）。
   领取走服务端 POST /api/sect/salary（权威 + 幂等；见 srv_patch_r081.py）。
   灵石余额由 /api/sect/* 的 YL_STONE_ECHO_V26K 中间件自动回显（YlxwApi -> YLApplyBalance）；
   贡献值由回执 contribution 回填本地 store（随下次 /api/save 推档）。
   本组件自包含（自带 state/请求），不改宗门页 lM 的既有 state 与逻辑。 */
function YlxwTSectSalary(p) {
  var pl = (p && p.player) || YlxwPlayer() || {};
  var st = O.useState(null), info = st[0], setInfo = st[1];
  var bs = O.useState(!1), busy = bs[0], setBusy = bs[1];
  var load = O.useCallback(function () {
    YlxwGet("/sect/salary/status").then(function (r) { setInfo(r || null); }).catch(function () { setInfo(null); });
  }, []);
  O.useEffect(function () { load(); }, [load]);
  var inSect = info ? !!info.inSect : !!pl.sectId;
  if (!inSect) return null;
  var rank = (info && info.rank) || pl.sectRank || "\u2014";
  var amt = info ? (Number(info.spiritStones) || 0) : 0;
  var cnt = info ? (Number(info.contribution) || 0) : 0;
  var claimed = !!(info && info.claimed);
  var doClaim = function () {
    if (busy || claimed) return;
    setBusy(!0);
    YlxwPost("/sect/salary", {}).then(function (r) {
      YlxwToast((r && r.message) || "\u4ff8\u7984\u5df2\u5165\u8d26", "gain");
      try {
        var s = Be.getState();
        if (s && s.player && r && typeof r.contribution === "number") {
          Be.setState({ player: Object.assign({}, s.player, { sectContribution: Math.max(0, Math.floor(r.contribution)) }) });
        }
      } catch (e) {}
      setInfo(function (o) { return Object.assign({}, o || {}, { claimed: !0, inSect: !0 }); });
      setBusy(!1);
    }).catch(function (e) {
      YlxwToast((e && e.message) || "\u9886\u53d6\u5931\u8d25", "danger");
      load(); setBusy(!1);
    });
  };
  var btn = "px-3 py-1.5 rounded border text-xs font-bold transition-colors ";
  var off = "disabled:opacity-50 disabled:cursor-not-allowed";
  return e.jsxs("div", { className: "bg-ink-800 p-4 rounded border border-stone-700", children: [
    e.jsx("h4", { className: "font-serif text-lg text-stone-200 mb-2 border-b border-stone-700 pb-2", children: "\u5b97\u95e8\u4ff8\u7984" }),
    e.jsxs("div", { className: "flex items-center justify-between gap-3", children: [
      e.jsxs("div", { className: "text-xs text-stone-400", children: [
        e.jsxs("div", { children: ["\u804c\u4f4d\uff1a", e.jsx("span", { className: "text-stone-200 font-bold", children: rank })] }),
        e.jsxs("div", { className: "mt-1", children: ["\u4eca\u65e5\u4ff8\u7984\uff1a",
          e.jsxs("span", { className: "text-blue-400", children: [amt, " \u7075\u77f3"] }), " + ",
          e.jsxs("span", { className: "text-amber-300", children: [cnt, " \u8d21\u732e"] })] }),
        e.jsx("div", { className: "mt-1 " + (claimed ? "text-emerald-400" : "text-yellow-400"),
          children: claimed ? "\u4eca\u65e5\u5df2\u9886" : "\u4eca\u65e5\u53ef\u9886" })
      ] }),
      e.jsx("button", { onClick: doClaim, disabled: busy || claimed,
        className: btn + (claimed ? "bg-ink-800 text-stone-500 border-stone-700 " : "bg-mystic-gold/20 text-mystic-gold border-mystic-gold hover:bg-mystic-gold/30 ") + off,
        children: claimed ? "\u5df2\u9886\u53d6" : (busy ? "\u9886\u53d6\u4e2d" : "\u9886\u53d6\u4ff8\u7984") })
    ] })
  ] });
}
'''

# --------------------------------------------------------------------------- 锚点

# 注入锚：与 YlxwPlayer / YlxwGet / YlxwPost / Be / lM 同模块作用域（v2810d 亦用它）
INJECT_ANCHOR = 'function YlxwPanelModal(p) {'

# E2 宗门大殿(hall)首个子节点之前插入俸禄卡（锚点纯 ASCII，唯一）
HALL_ANCHOR = 'S==="hall"&&e.jsxs("div",{className:"space-y-6",children:['
HALL_REPL = 'S==="hall"&&e.jsxs("div",{className:"space-y-6",children:[e.jsx(YlxwTSectSalary,{player:a}),'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r081 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 模块级注入：自包含俸禄组件
    p.insert_before('r081-block', INJECT_ANCHOR, blk + '\n', expect=1,
                    note='注入 YlxwTSectSalary（自包含：state + GET/POST + 领取）')

    # 1) 插进宗门大殿页签
    p.replace('r081-hall', HALL_ANCHOR, HALL_REPL, expect=1,
              note='宗门大殿首子节点插入俸禄卡')

    gates = [
        # ================= 本模块改动 =================
        ('R81·俸禄组件已注入',       'function YlxwTSectSalary(p) {',                1, '==', ''),
        ('R81·组件已插入宗门大殿',   'e.jsx(YlxwTSectSalary,{player:a})',            1, '==', ''),
        ('R81·状态接口已接',         'YlxwGet("/sect/salary/status")',               1, '==', ''),
        ('R81·领取接口已接',         'YlxwPost("/sect/salary", {})',                 1, '==', ''),
        ('R81·贡献回填本地 store',   'sectContribution: Math.max(0, Math.floor(r.contribution))', 1, '==', '与 YLApplyBalance 同款写法'),
        ('R81·今日可领/已领文案',    r'children: claimed ? "\u4eca\u65e5\u5df2\u9886" : "\u4eca\u65e5\u53ef\u9886"', 1, '==', ''),
        ('R81·领取按钮幂等禁用',     'disabled: busy || claimed,',                   1, '==', '连点/已领不再发请求'),
        ('R81·未入宗不渲染',         'if (!inSect) return null;',                    1, '==', ''),
        ('R81·职位与数值展示',       r'children: ["\u4eca\u65e5\u4ff8\u7984\uff1a",', 1, '==', ''),
        # ================= 冻结：宗门页既有结构一字不动 =================
        ('冻结·宗门大殿页签仍在',    HALL_ANCHOR,                                  1, '==', '插入点自身保留'),
        ('冻结·身份晋升卡仍在',      'children:"\u8eab\u4efd\u664b\u5347"',         1, '==', '大殿首卡未动'),
        ('冻结·宗门页组件仍在',      'lM=({isOpen:t,onClose:r,player:a,onJoinSect:l', 1, '==', ''),
        ('冻结·晋升表 ly 未动',      'F=oe?ly[oe]:null',                           1, '==', ''),
        ('冻结·贡献字段未改',        'a.sectContribution>=((F==null?void 0:F.contribution)||0)', 1, '==', '大殿「所需贡献」判定'),
        ('R81·注入块纯 ASCII',       'function YlxwTSectSalary(',                   1, '==', 'zh() 后无中文'),
        ('R81·未新增禁用模式',       'XMLHttpRequest',                             0, '==', 'V28_BAN_PATTERNS'),
    ]
    return gates
