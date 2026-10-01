# -*- coding: utf-8 -*-
r"""yl_v2810h_ext.py -- 玩家侧存档快照面板「时光回溯」（0.8.10 · 0.8.10 待办池 P2 的客户端半边）

## 为什么有这一环

服务端第 23 环（`srv_patch_snapself.py`）把 `save_snapshots` 开放给玩家自助回溯：
`GET /api/snapshots`（本人快照列表 + 本周额度）+ `POST /api/snapshots/:id/restore`（回溯）。
此前读侧**只有 GM 端点**（`/api/gm/players/:id/snapshots`），玩家误操作只能去求 GM。

本模块补客户端：在**仙务枢纽**（`YlxwHub`）的「成长」分组里加一个页签「时光回溯」，
列出本人快照（相对时间 / 修订号 / 境界 / 灵石 / 战力）并可一键回溯。

## 改动（4 处，锚点互不重叠）

| # | 锚点 | 改动 |
|---:|---|---|
| 1 | `function YlxwTStats() {` 之前 | 新增 `YLXW_SNAP_ADOPT` 开关 + `YlxwTSnapAgo` / `YlxwTSnapRow` / `YlxwTSnapshot` 三个定义 |
| 2 | `YLXW_TABS` 末项（`stats` 行）之后 | 追加 `{ key: "snapshot", label: "时光回溯", group: 3 }`（「成长」分组） |
| 3 | `YLXW_COMP` 末项 `stats: YlxwTStats };` | 追加注册 `snapshot: YlxwTSnapshot` |
| 4 | `applyRemoteSave` 内的灵石仲裁调用点 | 加**一次性放行开关**（见下，★ 本模块最关键的一处） |

## ★ 改动 4 为什么必须做（否则回溯会被客户端自己冲掉）

客户端每 6s 轮询 `GET /api/save?revision=1`；`gm_revision` 变大就 `fetchSave()` →
`applyRemoteSave(save, rev)` 采纳远端档。而 `applyRemoteSave` 里**先过灵石仲裁**：

```js
var ylArbD = YLArbDecide(Number((r().player||{}).spiritStones)||0, Number(c.spiritStones)||0);
if (ylArbD !== "apply") { if (ylArbD === "flush") YLArbFlush(); return }   // ← 直接 return
```

`YLArbDecide`（0.8.8 灵石归零修复的产物）的规则是：
`local > remote && (local - ack) > 0` 时，若 `remote > ack` 判 `skip`，否则判 `flush`
（把**本地**档推上去）。它的前提假设是「远端值来自推档应答 / 服务端钳制」。
**而回溯的本质就是让数值整体变小** —— 恰好踩中该假设：本地若有一点未推档的收益
（`local > ack`），回溯就会被判 `flush` 或 `skip`，**回溯结果被本地档盖回去**。

故本模块在回溯成功后置 `YLXW_SNAP_ADOPT = true`，让**下一次** `applyRemoteSave`
跳过仲裁直接采纳（一次性消费，用完即清）。

★ 只改 `applyRemoteSave` 这一个调用点，**不动** `YLArbDecide` 本体
（`YLApplyBalance` 的余额回显路径仍走原仲裁，0.8.10 B1 的灵石归零修复不受影响）。

## 依赖的既有符号（全部零新增）

`YlxwUseList` / `YlxwPanel` / `YlxwTitle` / `YlxwRow` / `YlxwBtn` / `YlxwErr` / `YlxwEmpty` / `YlxwNum`
（仙务面板公共件）· `Xc`（统一鉴权 fetch，**返回原始 Response** ⇒ 可按 status 分支）·
`an`（全站确认弹窗宿主）· `ia` / `Je`（成功 / 失败 toast）· `O`（React）。

★ 请求**不用** `YlxwPost`：它把非 2xx 折叠成 `new Error(body.error || "请求失败(N)")`，
409 / 404 / 429 无法区分；回溯必须按状态码给不同文案（额度用尽 ≠ 快照不存在）。

★ 成功回调**不调** `YlxwDirty()`：那会把**尚未采纳远端档的本地档**推上去。
角色数据的刷新交给既有的 6s `gm_revision` 轮询（与 GM 改档同一机制）。

## 硬约束遵守

  · 只新建本文件 + 修改 `build_v26n.py` / `localtest/dryrun_087.py` 接线；**不写回 build/assets/**。
  · 注入块 zh() 后纯 ASCII；不含禁用模式 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-。
  · 每个 replace 带 expect=精确次数；`apply()` 返回门禁五元组列表。
  · ★ 坑 2：门禁 needle 落在注入块内 ⇒ 一律用 `zh()` 之后的**转义形态**。
"""

import re

# --------------------------------------------------------------------------- 锚点

# 1) 组件注入点：仙务「修行统计」面板之前（同一模块作用域，O / Xc / an / ia / Je 均可见）
A1 = 'function YlxwTStats() {'

# 2) YLXW_TABS 末项（「成长」分组最后一项）—— 在它之后追加新页签
A2 = r'  { key: "stats", label: "\u4fee\u884c\u7edf\u8ba1", group: 3 }' + '\n];'
A2_NEW = (r'  { key: "stats", label: "\u4fee\u884c\u7edf\u8ba1", group: 3 },' + '\n'
          + r'  { key: "snapshot", label: "\u65f6\u5149\u56de\u6eaf", group: 3 }' + '\n];')

# 3) YLXW_COMP 注册 —— ★ 不动 `stats: YlxwTStats };` 那一行
#    （`build_v26n.py:896` 与 `yl_t8mentor_ext.py:382` 都把它当「基线未动」的 needle），
#    改用**追加赋值**的既有写法（基座里已有 `YLXW_COMP.mentor=…` / `YLXW_COMP.farm=…`）。
A3 = 'stats: YlxwTStats };'
A3_TAIL = '\nYLXW_COMP.snapshot=YlxwTSnapshot;'

# 4) applyRemoteSave 内的灵石仲裁守卫 —— ★ 保留 `var ylArbD=YLArbDecide(` 与
#    `try{const c=ho(a.player);var ylArbD=YLArbDecide(` 两处 needle 原样
#    （`yl_arb_ext.py:596/599` 的「通道B·已接守卫」门禁依赖它们），
#    只在守卫条件上加一个**一次性放行**项，并在其后清位。
A4 = 'if(ylArbD!=="apply"){if(ylArbD==="flush")YLArbFlush();return}'
A4_NEW = ('if(ylArbD!=="apply"&&!YLXW_SNAP_ADOPT){if(ylArbD==="flush")YLArbFlush();return}'
          'YLXW_SNAP_ADOPT=false;')

# --------------------------------------------------------------------------- 注入片段

SNAP_JS = r'''
/* ===== yl-0.8.10h: 仙务·时光回溯（玩家侧存档快照面板） =====
   服务端：GET /api/snapshots（列表 + 本周额度）/ POST /api/snapshots/:id/restore（回溯）
     200 { ok, restored_snapshot_id, gm_revision, quota }
     400 编号/内容非法 · 404 快照不存在或不属于你 · 409 本周额度用尽 · 429 频率限制
   面板落在仙务枢纽「成长」分组；快照由服务端自动产生，玩家只能回溯、不能造快照。 */

/* 一次性放行开关：置 true 后，下一次 applyRemoteSave 跳过灵石仲裁直接采纳远端档。
   原因见模块头「改动 4」——回溯会让数值整体变小，YLArbDecide 会误判为服务端钳制
   而 flush / skip，把回溯结果冲掉。用完即清（只放行一次）。 */
var YLXW_SNAP_ADOPT = false;

/* 相对时间（服务端只给 age_ms，本地化交给客户端，避免时区口径分歧） */
function YlxwTSnapAgo(ms) {
  if (ms == null) return "\u2014";
  var m = Math.floor(Number(ms) / 60000);
  if (!(m >= 0)) return "\u2014";
  if (m < 1) return "\u521a\u521a";
  if (m < 60) return m + " \u5206\u949f\u524d";
  var h = Math.floor(m / 60);
  if (h < 24) return h + " \u5c0f\u65f6\u524d";
  return Math.floor(h / 24) + " \u5929\u524d";
}

/* 单条快照：相对时间 + 修订号 + 摘要（境界/层数/灵石/战力）+ 回溯按钮 */
function YlxwTSnapRow(props) {
  var p = (props && props.s) || {};
  var sm = p.summary || {};
  var busy = !!(props && props.busy);
  var head = sm.realm ? (sm.realm + (sm.realmLevel ? " " + sm.realmLevel + " \u5c42" : "")) : "\u65e7\u6863\uff08\u65e0\u6458\u8981\uff09";
  return e.jsxs(YlxwRow, { children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      e.jsx("span", { className: "text-stone-100 font-mono text-xs", children: YlxwTSnapAgo(p.age_ms) }),
      e.jsx("span", { className: "text-xs text-stone-500", children: "#" + YlxwNum(p.id) + " \u00b7 \u4fee\u8ba2 " + YlxwNum(p.gm_revision) })
    ] }),
    e.jsx("div", { className: "text-xs text-stone-300 pt-1", children: head + " \u00b7 \u7075\u77f3 " + YlxwNum(sm.stones) + " \u00b7 \u6218\u529b " + YlxwNum(sm.combatPower) }),
    e.jsx("div", { className: "pt-1.5", children: e.jsx(YlxwBtn, {
      disabled: busy,
      onClick: function () { if (props && props.onRestore) props.onRestore(p.id); },
      children: busy ? "\u56de\u6eaf\u4e2d\u2026" : "\u56de\u6eaf\u5230\u6b64\u6863"
    }) })
  ] }, "snaprow" + p.id);
}

function YlxwTSnapshot(props) {
  var r = YlxwUseList("/snapshots"), t = r.data, a = r.err, l = r.busy, c = r.load;
  var s = O.useState(""), k = s[0], B = s[1];
  function doRestore(id) {
    an("\u56de\u6eaf\u540e\u5f53\u524d\u8fdb\u5ea6\u5c06\u88ab\u8be5\u5feb\u7167\u66ff\u6362\u3002\u7cfb\u7edf\u4f1a\u5148\u81ea\u52a8\u5907\u4efd\u4f60\u6b64\u523b\u7684\u8fdb\u5ea6\uff0c\u56e0\u6b64\u8be5\u64cd\u4f5c\u53ef\u9006\u3002\u786e\u5b9a\u56de\u6eaf\u5417\uff1f", "\u65f6\u5149\u56de\u6eaf", function () {
      B(String(id));
      Xc(ln + "/snapshots/" + id + "/restore", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
        .then(function (res) {
          return res.json().catch(function () { return null; }).then(function (j) { return { s: res.status, j: j }; });
        })
        .then(function (o) {
          B("");
          if (o.s === 200 && o.j && o.j.ok) {
            YLXW_SNAP_ADOPT = true;
            ia("\u5df2\u56de\u6eaf\uff0c\u89d2\u8272\u6570\u636e\u5c06\u5728\u6570\u79d2\u5185\u81ea\u52a8\u5237\u65b0");
            if (c) c();
            return;
          }
          if (o.s === 409) { Je("\u672c\u5468\u56de\u6eaf\u6b21\u6570\u5df2\u7528\u5c3d\uff0c\u4e0b\u5468\u4e00 0 \u70b9\u540e\u91cd\u7f6e"); return; }
          if (o.s === 404) { Je("\u5feb\u7167\u4e0d\u5b58\u5728\u6216\u4e0d\u5c5e\u4e8e\u4f60\uff0c\u8bf7\u5237\u65b0\u540e\u91cd\u8bd5"); return; }
          if (o.s === 429) { Je("\u64cd\u4f5c\u8fc7\u4e8e\u9891\u7e41\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5"); return; }
          Je("\u56de\u6eaf\u5931\u8d25\uff1a" + ((o.j && o.j.error) || ("\u8bf7\u6c42\u5931\u8d25(" + o.s + ")")));
        }, function () { B(""); Je("\u7f51\u7edc\u5f02\u5e38\uff0c\u56de\u6eaf\u5931\u8d25"); });
    });
  }
  var q = (t && t.quota) || {};
  var list = (t && t.snapshots) || [];
  var head = e.jsx(YlxwTitle, { extra: e.jsx(YlxwBtn, { disabled: l, onClick: c, children: "\u5237\u65b0" }), children: "\u65f6\u5149\u56de\u6eaf" });
  var notice = e.jsxs(YlxwRow, { children: [
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      e.jsx("span", { className: "text-xs text-amber-300 font-bold", children: "\u5b58\u6863\u5feb\u7167 \u00b7 \u8bef\u64cd\u4f5c\u6551\u63f4" }),
      e.jsx("span", { className: "text-xs text-stone-300", children: "\u672c\u5468\u5269\u4f59 " + YlxwNum(q.left) + " / " + YlxwNum(q.weekly) + " \u6b21" })
    ] }),
    e.jsx("div", { className: "text-xs text-stone-400 pt-1", children: "\u7cfb\u7edf\u5728\u4f60\u6bcf\u6b21\u5b58\u6863\u65f6\u81ea\u52a8\u7559\u6863\uff08\u6bcf\u53f7\u6700\u591a\u4fdd\u7559 50 \u4efd\uff09\u3002\u56de\u6eaf\u4f1a\u628a\u5f53\u524d\u8fdb\u5ea6\u66ff\u6362\u4e3a\u8be5\u5feb\u7167\uff0c\u4f46\u7cfb\u7edf\u4f1a\u5148\u81ea\u52a8\u5907\u4efd\u6b64\u523b\u8fdb\u5ea6\uff0c\u53ef\u518d\u6b21\u56de\u6eaf\u627e\u56de\u3002" }),
    e.jsx("div", { className: "text-xs text-stone-500 pt-0.5", children: "\u6bcf\u5468\u53ef\u56de\u6eaf 1 \u6b21\uff0c\u5468\u4e00 0 \u70b9\u91cd\u7f6e\u3002\u56de\u6eaf\u4f1a\u4e00\u5e76\u66ff\u6362\u5883\u754c / \u7075\u77f3 / \u80cc\u5305\u7b49\u5168\u90e8\u8fdb\u5ea6\uff0c\u8bf7\u8c28\u614e\u64cd\u4f5c\u3002" })
  ] });
  var body;
  if (a) body = e.jsx(YlxwErr, { retry: c, children: a });
  else if (l && !t) body = e.jsx(YlxwEmpty, { children: "\u8f7d\u5165\u4e2d\u2026" });
  else if (!list.length) body = e.jsx(YlxwEmpty, { children: "\u6682\u65e0\u5feb\u7167\u3002\u8fdb\u5165\u6e38\u620f\u5e76\u4ea7\u751f\u4e00\u6b21\u5b58\u6863\u540e\uff0c\u8fd9\u91cc\u4f1a\u51fa\u73b0\u4f60\u7684\u5b58\u6863\u5feb\u7167\u3002" });
  else body = e.jsx("div", { className: "space-y-2", children: list.map(function (p) {
    return e.jsx(YlxwTSnapRow, { s: p, busy: k === String(p.id), onRestore: doRestore }, "snap" + p.id);
  }) });
  return e.jsxs(YlxwPanel, { children: [head, notice, body] });
}
'''


def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 arb / pet089 / v2810a~g）；ctx = {'zh': zh, ...}"""
    zh = ctx['zh']

    snap_js = zh(SNAP_JS)
    bad = re.findall(r'[^\x00-\x7f]', snap_js)
    if bad:
        raise AssertionError('v2810h 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 1) 新增时光回溯面板 + 仲裁放行开关（插在「修行统计」面板之前，同一模块作用域）
    p.insert_before('v2810h-panel', A1, snap_js + '\n',
                    expect=1, note='新增 YLXW_SNAP_ADOPT + YlxwTSnapAgo/YlxwTSnapRow/YlxwTSnapshot')

    # 2) 仙务枢纽「成长」分组追加「时光回溯」页签
    p.replace('v2810h-tab', A2, A2_NEW, expect=1,
              note='YLXW_TABS 末项之后追加 { key:"snapshot", label:"时光回溯", group:3 }')

    # 3) YLXW_COMP 注册面板组件（追加赋值，不动基线 `stats: YlxwTStats };` 行）
    p.insert_after('v2810h-comp', A3, A3_TAIL, expect=1,
                   note='YLXW_COMP.snapshot=YlxwTSnapshot;（追加赋值，与 mentor/farm 同款）')

    # 4) ★ 灵石仲裁一次性放行（只改守卫条件，不动 YLArbDecide 本体与既有 needle）
    p.replace('v2810h-arb', A4, A4_NEW, expect=1,
              note='applyRemoteSave 的仲裁守卫加一次性放行（回溯后跳过 flush/skip）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # —— 组件与注册 ——
        ('P2·面板组件定义恰 1',   'function YlxwTSnapshot(',                    1, '==', ''),
        ('P2·行组件定义恰 1',     'function YlxwTSnapRow(',                     1, '==', ''),
        ('P2·相对时间函数恰 1',   'function YlxwTSnapAgo(',                    1, '==', ''),
        ('P2·组件引用恰 2',       'YlxwTSnapshot',                            2, '==', '定义 1 + YLXW_COMP 注册 1'),
        ('P2·已注册进 YLXW_COMP', 'YLXW_COMP.snapshot=YlxwTSnapshot;',          1, '==', '追加赋值，不动基线行'),
        ('P2·基线 COMP 行未动',   'stats: YlxwTStats };',                      1, '==', 'build_v26n:896 / t8:382 的 needle'),
        ('P2·页签已注册（转义）',  zh('{ key: "snapshot", label: "时光回溯", group: 3 }'), 1, '==', ''),
        ('P2·基线 stats 页签未动', zh('{ key: "stats", label: "修行统计", group: 3 }'), 1, '==', ''),
        ('P2·基线 stats 面板未动', 'function YlxwTStats() {',                   1, '==', ''),
        # —— 数据源与请求 ——
        ('P2·列表数据源端点',      'YlxwUseList("/snapshots")',                 1, '==', ''),
        ('P2·回溯走统一鉴权 Xc',   'Xc(ln + "/snapshots/" + id + "/restore", { method: "POST"', 1, '==', 'ln="/yl/api"，不自己拼前缀'),
        ('P2·二次确认走 an() 宿主', zh('an("回溯后当前进度将被该快照替换。'),       1, '==', '全站确认弹窗，不新造'),
        ('P2·成功 toast',          zh('ia("已回溯，角色数据将在数秒内自动刷新");'), 1, '==', ''),
        ('P2·409 额度文案（转义）', zh('本周回溯次数已用尽'),                    1, '==', ''),
        ('P2·404 文案（转义）',    zh('快照不存在或不属于你，请刷新后重试'),        1, '==', ''),
        ('P2·429 文案（转义）',    zh('操作过于频繁，请稍后再试'),                1, '==', ''),
        ('P2·额度显示（转义）',    zh('"本周剩余 " + YlxwNum(q.left)'),          1, '==', ''),
        ('P2·空态（转义）',        zh('暂无快照。进入游戏并产生一次存档后'),        1, '==', ''),
        # —— ★ 仲裁放行 ——
        ('P2·放行开关声明恰 1',    'var YLXW_SNAP_ADOPT = false;',              1, '==', ''),
        ('P2·放行已接入仲裁守卫',  'if(ylArbD!=="apply"&&!YLXW_SNAP_ADOPT){if(ylArbD==="flush")YLArbFlush();return}YLXW_SNAP_ADOPT=false;', 1, '==', '只改 applyRemoteSave 守卫条件'),
        ('P2·仲裁调用 needle 保留', 'var ylArbD=YLArbDecide(Number((r().player||{}).spiritStones)||0,Number(c.spiritStones)||0);', 1, '==', 'yl_arb_ext:596 门禁依赖'),
        ('P2·通道B needle 保留',   'try{const c=ho(a.player);var ylArbD=YLArbDecide(', 1, '==', 'yl_arb_ext:599 门禁依赖'),
        ('P2·放行是一次性消费',    'YLXW_SNAP_ADOPT=false;',                     1, '==', '用完即清'),
        ('P2·YLArbDecide 本体未改', 'function YLArbDecide(localStones, remoteStones) {', 1, '==', '0.8.10 B1 归零修复不受影响'),
        # —— 复用既有件（零新增 helper） ——
        ('P2·复用 YlxwPanel',      'e.jsxs(YlxwPanel, { children: [head, notice, body] })', 1, '==', ''),
        ('P2·复用 YlxwTitle/Btn',  zh('var head = e.jsx(YlxwTitle, { extra: e.jsx(YlxwBtn, { disabled: l, onClick: c, children: "刷新" }), children: "时光回溯" });'), 1, '==', ''),
        # —— 禁用模式：**不在此处断言全文**（基座/其它模块本就含 iframe 等）；
        #    build_v26n.py:780 已对**每个注入块**逐块断言 V28_BAN_PATTERNS。 ——
    ]
    return gates
