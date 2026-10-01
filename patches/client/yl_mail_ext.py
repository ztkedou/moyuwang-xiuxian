# -*- coding: utf-8 -*-
"""
yl_mail_ext.py -- 信箱「一键领取」(用户反馈 #2)

问题：信箱只能逐封点「领取」，附件多时很烦。

本模块在**信箱面板内部**（YlxwTMail 的标题栏 extra 区）加一个「一键领取 (N)」按钮，
点击后一次领取该玩家**所有有附件且未领取**的邮件。

设计取舍
--------
* 客户端只发**一个**请求 `POST /api/mail/claim-all`（服务端批量），而不是在客户端
  逐封循环调 `/api/mail/claim`：
    - 逐封循环 = N 个 HTTP 往返 + N 次客户端状态抖动，且中途失败会留下「领了一半」的
      本地状态需要客户端自己记账；
    - 批量接口把循环放在服务端，逐封复用 mailClaimCore（原子占位 + 补偿回滚），
      客户端只处理一个 `{count, lingshi}` 回执，语义最简。
* 请求**复用既有鉴权封装 `YlxwPost`**（= 信箱面板 YlxwUseAct 内部用的同一个函数，
  即 Xc/ln 那套 Bearer + X-YL-Base-Revision + X-YL-Session + 401 自动刷新），
  不新造 fetch / 请求头。
* 入账**只按增量**：`spiritStones += r.lingshi`，**不采纳服务端绝对余额**。
  本服存档客户端权威，采纳绝对值会抹掉本地尚未同步的收益（既有硬规矩）。

硬约束：INJECT_JS 与插入片段全部为纯 ASCII 校验通过后由 build 侧 zh() 统一转义
        （本文件内 INJECT_JS 保留真中文，apply() 内调 ctx['zh'] 转义）。
"""

# ---------------------------------------------------------------------------
# 注入块（真中文，apply() 里统一走 zh()）
# 复用符号：YlxwPost / YlxwDirty / YlxwBtn / Be / O(React) / e(jsx) / ia / Je
#   —— 均与 YlxwTMail 同作用域，且在注入点之前已定义。
# ---------------------------------------------------------------------------
INJECT_JS = r'''
/* == YL_MAIL_CLAIMALL_V28 (mailbox one-tap claim, feedback #2) == */
function YlxwMailClaimAllBtn(props) {
  // 可领取数量：优先用服务端 list 回执的 claimable（全量准确），
  // 拿不到时退回「当前已加载这一页」里未领取且有附件的封数。
  var list = (props && props.mails) || [];
  var n = 0;
  for (var i = 0; i < list.length; i++) {
    var g = list[i];
    if (g && Number(g.lingshi) > 0 && !g.claimed) n++;
  }
  var sc = props && props.count;
  if (typeof sc === "number" && isFinite(sc) && sc >= 0) n = Math.floor(sc);

  var s = O.useState(!1), busy = s[0], setBusy = s[1];

  function doClaimAll() {
    if (busy || n <= 0) return;
    setBusy(!0);
    // 记录请求前的本地余额。服务端 mailClaimCore 入账后会 gm_revision++，
    // 若客户端的 6s tick 在响应回来之前先拉了一次档，本地余额就已经包含了这笔
    // —— 此时再做「本地 += got」会重复入账（线上实测：3×777 被记成 4662）。
    // 所以只有在余额与请求前一致时才做乐观叠加；否则交给权威存档。
    var before = Number((Be.getState().player || {}).spiritStones) || 0;
    YlxwPost("/mail/claim-all", {}).then(function (r) {
      setBusy(!1);
      var got = Number(r && r.lingshi) || 0;
      if (got > 0) {
        // 只按增量入账，不采纳服务端绝对余额：本服存档客户端权威，
        // 采纳绝对 spiritStones 会把本地尚未同步的收益抹掉。
        var cur = Be.getState().player;
        if (cur) {
          var now = Number(cur.spiritStones) || 0;
          if (now === before) {
            var next = Object.assign({}, cur);
            next.spiritStones = now + got;
            Be.getState().setPlayer(next);
          }
          /* now !== before ⇒ 权威存档已包含这笔，跳过本地叠加 */
        }
        Be.getState().addLog("【信箱】一键领取 " + (Number(r && r.count) || 0) + " 封附件，共 " + got + " 灵石。", "gain");
        ia("已领取 " + got + " 灵石");
      } else {
        ia("暂无可领取的附件");
      }
      if (props && props.onDone) props.onDone();
      YlxwDirty();
    }, function (e1) {
      setBusy(!1);
      Je("一键领取失败：" + ((e1 && e1.message) || e1));
    });
  }

  var dis = !!(props && props.busy) || busy || n <= 0;
  var label = busy ? "领取中…" : (n > 0 ? ("一键领取 (" + n + ")") : "无可领取");
  return e.jsx(YlxwBtn, { disabled: dis, onClick: doClaimAll, children: label });
}
/* == end YL_MAIL_CLAIMALL_V28 == */
'''

# ---------------------------------------------------------------------------
# 锚点（全部纯 ASCII，已实测 count）
# ---------------------------------------------------------------------------
# 信箱面板标题栏 extra 数组里的第一个按钮（「全部已读」）——在其前插入一键领取按钮。
MAIL_BTN_ANCHOR = 'e.jsx(YlxwBtn, { tone: "ghost", disabled: l || !t || !t.unread'

# 信箱面板之前（YlxwMailHint 紧挨着 YlxwTMail），同一作用域，函数声明可被 YlxwTMail 引用。
MAIL_BLOCK_ANCHOR = 'function YlxwMailHint() {'

# 插到 extra 数组首位：count 走服务端 list 回执的 claimable（拿不到则组件内退化为按页计数）。
MAIL_BTN_CODE = (
    'e.jsx(YlxwMailClaimAllBtn, { count: (t && t.claimable != null) ? Number(t.claimable) : null, '
    'mails: m, busy: l, onDone: c }, "ca"),'
)


def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}；返回 gates。"""
    zh = ctx['zh']

    # 1) 注入组件（含真中文，统一转义）
    p.insert_before(
        'mail-claimall-block',
        MAIL_BLOCK_ANCHOR,
        zh(INJECT_JS) + '\n',
        expect=1,
        note='信箱一键领取组件（复用 YlxwPost 鉴权 / 增量入账）',
    )

    # 2) 在信箱标题栏 extra 首位挂按钮
    p.insert_before(
        'mail-claimall-button',
        MAIL_BTN_ANCHOR,
        MAIL_BTN_CODE,
        expect=1,
        note='信箱 extra 数组首位插入「一键领取 (N)」按钮',
    )

    # 门禁（s 均为纯 ASCII；对全量输出文本计数）
    return [
        ('信箱一键领取 组件定义',     'function YlxwMailClaimAllBtn(',            1, '==', ''),
        ('信箱一键领取 按钮挂载',     'e.jsx(YlxwMailClaimAllBtn, { count:',      1, '==', ''),
        ('信箱一键领取 调批量接口',   'YlxwPost("/mail/claim-all", {})',          1, '==', ''),
        ('信箱一键领取 增量入账',     'next.spiritStones = now + got',           1, '==', ''),
        ('信箱一键领取 竞态快照',     'var before = Number((Be.getState().player || {}).spiritStones) || 0;', 2, '==', '信箱 + 交易行货款 各一处（同一守卫模式）'),
        ('信箱一键领取 竞态守卫',     'if (now === before) {',                   2, '==', '信箱 + 交易行货款 各一处；余额未变才乐观叠加，避免与拉回的权威存档重复入账'),
        ('信箱一键领取 禁用态',       'var dis = !!(props && props.busy) || busy || n <= 0;', 1, '==', ''),
        ('信箱一键领取 未采纳绝对值',  'r.balance',                                 0, '==', '必须为 0（客户端权威，只按增量）'),
        ('信箱一键领取 标题文案',     zh('一键领取 ('),                             1, '==', ''),
        ('信箱一键领取 标记成对',     'YL_MAIL_CLAIMALL_V28',                     2, '==', '起始+结束'),
    ]
