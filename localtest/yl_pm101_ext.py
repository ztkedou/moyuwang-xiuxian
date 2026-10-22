# -*- coding: utf-8 -*-
r"""
yl_pm101_ext.py -- PM-101 玩家私信（客户端第 102 模块；v28 契约：INJECT_JS + apply(p,ctx) -> gates，
结构照抄 localtest/yl_fb100_ext.py）

接口契约（与三端共同遵守，字段名一个都不能改）：
    POST <ln>/mail/send（= /yl/api/mail/send，服务端 authenticateToken；入参 {to, content}）
      · to      = 目标用户名（服务端 users 表校验存在；to==自己 → 400）
      · content = 去空格后 2~500 字（服务端违规 → 400）
    成功 200 {ok:true,id}；同一发送者 30s 内二连发 → 409；每玩家每日（UTC+8 口径）上限 50 → 409
    ★ 绝不经 Xc()/YlxwPost()（其 401/403 分支会强制登出玩家）——本模块 raw fetch，
      401 时只调 pS() 静默续期后重试恰一次，任何失败都不触碰登录态、不阻断游戏。

客户端四处落位（本文件 4 个补丁操作）：
    E1 API 桥 + 写信弹窗（insert_before `const Q0="/yl/api"`，与 fb100 同锚；求值期只定义函数/
       挂 window/注入 <style>，ln/jo/pS 调用发生在点击时）：
         window.YLPM_SUBMIT   raw fetch + Bearer（jo()），401 → pS() → 重试恰一次
         window.YLPM_SEND     headless 管线：冷却(30s，仅成功记) → 校验(收件人非空/内容 2~500)
                              → YLPM_SUBMIT → 分支映射（成功/409/400/401/其它/网络）
         window.YLPM_OPEN(to) 自包含 DOM 写信弹窗（收件人预填、内容 textarea、发送/关闭；
                              已开则只改收件人）；测试钩子 window.__YLPM_CUR
    E2 「仙友录」好友行（YlxwTFriends）：内层 flex 行（姓名·境界 / 送礼）尾追加「私信」
       e.jsx(YlxwBtn) → YLPM_OPEN(N.name)
    E3 「在线人物」玩家行（R-144 注入块 onlineRow 的 if(!p.isSelf) 内、切磋 push 之后）追加
       acts.push(btn("私信",…)) → YLPM_OPEN(u)（R-144 是 DOM 栈，用其模块内 btn 工厂，非 e.jsx）
    E4 「信箱」行（YlxwTMail m.map 行头右栏、时间 span 之后）：kind='player' 的信件渲染
       「发信人 X」span + 「回信」ghost 钮 → YLPM_OPEN(g.sender)

kind 判定口径（★与任务书的偏差裁定，已按最小惊原则处理）：
    契约 B.3 说「kind='player' 的信件渲染发信人与回信钮」，但**现役** GET /api/mail/list 的
    响应映射（srv/index_v28.ts L7925-7934）只有 {id,sender,title,content,lingshi,claimed,read,
    createdAt}，没有 kind。若服务端半边按契约给 list 补了 kind，判定走 g.kind==="player" 精确成立；
    若 list 尚未带 kind（旧响应），回退用 g.sender 且非 "system" 判定（现役系统信 sender 全量实测
    为 'system'，仅 1 处补偿信为 '天机阁' + GM 可自定义 sender——该兜底态下这两类会误显回信钮，
    点发送会被服务端「用户不存在」400 拒，不阻断游戏）。条件写成两者的或，两种服务端形态都工作。

与任务预期的偏差（勘察结论，本环实测证据）：
    ★ 任务书自检段写「基线 index-v26m-20260927.js 干跑」——但 v26m（2026-09-27，1419571 chars）
      **没有 R-144 在线面板块**（'/*YLXW_R144_V2919*/' count=0）且**信箱行没有删除钮**
      （'e.jsx(YlxwMailDelBtn' count=0），物理上承接不了本模块 E3/E4 拼接。
      任务书自给的锚点偏移（YlxwTFriends @1132581 / YlxwTMail @982244 / R-144 @2197289）全部
      落在**链上产物 build/assets/index-v100-20261020.js**（2202983 chars）坐标系里
      （本环实测：YlxwTMail 恰 @982244 逐字节命中；R-144/YLXW 与之同源）。
      ∴ 本模块是**链上模块**（V28_MODULES 的 fb100 与 STANDALONE_CLIENT 的 r144 都已在其上），
      干跑/往返自检对 index-v100-20261020.js 执行；v26m 干跑另跑一遍留 FAIL 实证（见 dryrun）。

契约（本文件对外只导出这两个符号，同 yl_fb100_ext.py）：
    INJECT_JS : str        注入 JS 块（含中文，由构建侧统一 zh() 转义）
    apply(p, ctx) -> gates
        p   : yl_patch.Patcher
        ctx : {'zh': zh 函数, 'base_text': str}
        gates: list[(name, needle, expected, op, note[, within])]，op ∈ {'==','>=','<='}
               可选第 6 元 within=(start,end)——块内断言一律限域到本模块注入块（fb100 同款
               分支如 401/pS/lastOk 在其块内也各有一份，全文计数会翻倍 ⇒ 必须限域，SKILL §19.1）

锚点实测（2026-10-21 本环，对 build/assets/index-v100-20261020.js，2202983 chars）：
    A_Q0  'const Q0="/yl/api"'                                    count=1（@700355，fb100 块尾之后）
    A_FR  'children: "\u9001\u793c" })] })] }, "f" + N.id); })'   count=1（好友行尾，内含 count=1 的
          ', "f" + N.id); })' 与 'f("ft" + N.id, "/friends/gift"…'）
    A_ON  'acts.push(btn("切磋",null,function(){YlxwPost("/arena/challenge",{name:u}).then('
          'function(){st("已向 "+u+" 下战书");}).catch(function(e){st(e&&e.message||"下战书失败");'
          ');}));'                                                 count=1（@2199288；R-144 raw UTF-8 态）
    A_MA  'g.lingshi > 0 && !g.claimed && e.jsx(YlxwBtn, { disabled: !!u, onClick: function() {'
          ' f("c" + g.id, "/mail/claim"'                            count=1（内含 count=1 的 A_CLAIM）
    冲突体检：'YLPM_' / 'ylpm-' / '私信' / '回信' / '/mail/send' 在 v100 全部 count=0（无碰撞）。
    冻结体检：'const Q0="/yl/api"' / 'function jo(){' / 'async function pS(){' / 'function YlxwTMail() {'
      / 'function YlxwTFriends() {' / 'function YlxwPanelModal(p)' / 'var YLXW_COMP = { mail: YlxwTMail'
      / '/* == end YL_FB100_V1 == */' / 'f("readall", "/mail/read", { all: !0 }' 全部 count=1；
      'window.__ylR144' count=2（R-144 set+check 守卫）；'YL_MAIL_CLAIMALL_V28' count=2（mail-ext 标记+注记）。

中文纪律：
    · INJECT_JS 内的中文 → 构建侧 zh() 转 \uXXXX（apply 内再自检一遍，fail-closed）；
      gates 里断言块内中文一律经本模块 _zh()（= yl_patch.zh 同实现）转义，否则 count==0 假失败。
    · E2/E4 拼接文本用 \uXXXX 转义（与周边 vite 产物串形态逐字同态）；E3 拼接文本用 raw UTF-8
      （R-144 块即此形态，见 onlineRow 原文「已好友/切磋」）——两者都 ASCII/原文直插，不走 zh()。
"""

# --------------------------------------------------------------------------- 锚点（全部实测 count==1）
MARK = '/* == YL_PM101_V1 (PM-101 player direct message; raw fetch POST /mail/send; NEVER Xc/YlxwPost) == */'
END_MARK = '/* == end YL_PM101_V1 == */'

# E1 注入点：ln 链式派生起点（fb100 块尾之后；本块求值期不引用 ln/jo/pS，调用发生在点击时）
A_Q0 = 'const Q0="/yl/api"'

# E2 好友行尾（内层 flex 行 children 收尾 → 内层 div 收尾 → YlxwRow children/props 收尾 → 行键）
A_FR = r'children: "\u9001\u793c" })] })] }, "f" + N.id); })'

# E3 切磋 push 全语句（R-144 注入块内，raw UTF-8、无空格紧凑态）
A_ON = ('acts.push(btn("切磋",null,function(){YlxwPost("/arena/challenge",{name:u}).then(function(){'
        'st("已向 "+u+" 下战书");}).catch(function(e){st(e&&e.message||"下战书失败");});}));')

# E4 信箱行右栏领取钮条件开头（内含全局唯一的 A_CLAIM ⇒ 本锚点 count<=1）
A_MA = ('g.lingshi > 0 && !g.claimed && e.jsx(YlxwBtn, { disabled: !!u, onClick: function() { '
        'f("c" + g.id, "/mail/claim"')

# --------------------------------------------------------------------------- 拼接文本（raw 直插，不走 zh()）
# E2「私信」钮：插成内层 flex 行第 3 个子元素（姓名/送礼 之后），点击 → YLPM_OPEN(N.name)
PM_FRIENDS_BTN = (r'e.jsx(YlxwBtn, { onClick: function() { try { typeof window.YLPM_OPEN === "function" '
                  r'&& window.YLPM_OPEN(N.name); } catch (ylpme) {} }, children: "\u79c1\u4fe1" })')
N_FR = r'children: "\u9001\u793c" }),' + PM_FRIENDS_BTN + r'] })] }, "f" + N.id); })'

# E3「私信」push：切磋 push 之后、if(!p.isSelf) 收尾之前（R-144 btn 工厂自带 try/catch + st()）
PM_ONLINE_PUSH = ('acts.push(btn("私信",null,function(){if(typeof window.YLPM_OPEN==="function")'
                  'window.YLPM_OPEN(u);else st("私信功能未就绪");}));')
N_ON = A_ON + PM_ONLINE_PUSH

# E4 信箱行：时间 span 之后插「发信人」span +「回信」ghost 钮。条件 = kind==='player'，
# 无 kind 字段（旧 list 响应）时兜底 sender 非 system（见 docstring「kind 判定口径」）；
# && 优先级高于 ||，A || B && C && D ≡ A || (B&&C&&D)，此处仍显式加括号求稳。
# React 子数组容忍 false——同函数既有 `g.lingshi > 0 && … && e.jsx(…)` 同形态。
PM_PM_COND = '(g.kind === "player" || (!g.kind && g.sender && g.sender !== "system"))'
PM_MAIL_INSERT = (r'' + PM_PM_COND + r' && e.jsx("span", { className: "text-[10px] text-sky-300", '
                  r'children: "\u53d1\u4fe1\u4eba " + (g.sender || "") }), '
                  + PM_PM_COND + r' && e.jsx(YlxwBtn, { tone: "ghost", onClick: function() { try { '
                  r'typeof window.YLPM_OPEN === "function" && window.YLPM_OPEN(g.sender); } catch (ylpme) {} }, '
                  r'children: "\u56de\u4fe1" }),')
N_MA = PM_MAIL_INSERT + A_MA

# --------------------------------------------------------------------------- 注入块（中文由构建侧 zh() 转义）
INJECT_JS = '''
/* == YL_PM101_V1 (PM-101 player direct message; raw fetch POST /mail/send; NEVER Xc/YlxwPost) == */
/* ---- part 1: API bridge（与 ln/jo/pS 同作用域；经 window 暴露，调用方零作用域假设，SKILL §13.4）---- */
async function YLPM_SUBMIT(o) {
  o = o || {};
  var send = function () {
    var h = { "Content-Type": "application/json" };
    try { var a = jo(); if (a && a.Authorization) h.Authorization = a.Authorization; } catch (e) {}
    return fetch(ln + "/mail/send", { method: "POST", headers: h, body: JSON.stringify({
      to: String(o.to || ""), content: String(o.content || "") }) });
  };
  var r = await send();
  /* 401: pS() 静默续期后重试恰一次；绝不触发登出（401/403 踢登录的是 Xc 的分支，本模块不经它） */
  if (r && r.status === 401) {
    try { if (typeof pS === "function") await pS(); } catch (e) {}
    r = await send();
  }
  var d = null;
  try { d = await r.json(); } catch (e) {}
  if (r && r.ok) return { ok: !0, id: d ? d.id : null };
  return { ok: !1, status: (r && r.status) || 0, error: (d && d.error) ? String(d.error) : "" };
}
try { window.YLPM_SUBMIT = YLPM_SUBMIT; } catch (e) {}
/* ---- part 2: UI（自包含 DOM 写信弹窗；全链 try/catch —— 本游戏无 app 级 ErrorBoundary，抛异常=全站白屏）---- */
(function () {
  var COOLDOWN_MS = 30000, MIN_LEN = 2, MAX_LEN = 500;
  var lastOk = 0, cur = null;
  function gid(id) { try { return document.getElementById(id); } catch (e) { return null; } }
  function mk(tag, cls, css) { var n = document.createElement(tag); if (cls) n.className = cls; if (css) n.style.cssText = css; return n; }
  function ensureStyle() {
    if (gid("ylpm-style")) return;
    var s = document.createElement("style"); s.id = "ylpm-style";
    s.textContent = ".ylpm-mask{position:fixed;left:0;top:0;right:0;bottom:0;background:rgba(0,0,0,.62);z-index:2147483000;display:flex;align-items:center;justify-content:center;padding:12px}"
      + ".ylpm-box{width:100%;max-width:460px;max-height:86vh;overflow:auto;background:#1c1917;color:#e7e5e4;border:1px solid #0284c7;border-radius:12px;padding:14px 16px;font:14px/1.6 system-ui,-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;box-shadow:0 8px 40px rgba(0,0,0,.6)}"
      + ".ylpm-title{font-weight:700;font-size:16px;color:#7dd3fc;margin-bottom:10px}"
      + ".ylpm-lab{font-size:12px;color:#a8a29e;margin:8px 0 4px}"
      + ".ylpm-ta,.ylpm-in{width:100%;box-sizing:border-box;background:#0c0a09;color:#e7e5e4;border:1px solid #57534e;border-radius:8px;padding:8px;font:13px/1.5 system-ui,sans-serif}"
      + ".ylpm-ta{min-height:110px;resize:vertical}"
      + ".ylpm-btn{display:inline-block;padding:8px 18px;border-radius:8px;border:1px solid #0284c7;background:#0284c7;color:#f0f9ff;font-weight:700;cursor:pointer;font-size:14px}"
      + ".ylpm-btn[disabled]{opacity:.55;cursor:not-allowed}"
      + ".ylpm-ghost{display:inline-block;padding:8px 14px;margin-left:8px;border-radius:8px;border:1px solid #57534e;color:#d6d3d1;background:transparent;cursor:pointer;font-size:14px}"
      + ".ylpm-info{font-size:12px;margin-top:8px;min-height:18px;color:#a8a29e}"
      + ".ylpm-err{color:#f87171}.ylpm-ok{color:#34d399}";
    try { (document.head || document.body).appendChild(s); } catch (e) {}
  }
  function closeBox() {
    try { if (cur && cur.mask && cur.mask.parentNode && cur.mask.parentNode.removeChild) cur.mask.parentNode.removeChild(cur.mask); } catch (e) {}
    cur = null;
    try { window.__YLPM_CUR = null; } catch (e) {}
  }
  function showInfo(msg, bad) {
    try { if (cur && cur.info) { cur.info.textContent = String(msg); cur.info.className = "ylpm-info " + (bad ? "ylpm-err" : "ylpm-ok"); } } catch (e) {}
  }
  function toastOk(msg) { try { if (typeof YlxwToast === "function") YlxwToast(msg, "gain", "pm101", 2600); } catch (e) {} }
  function toastErr(msg) { try { if (typeof YlxwToast === "function") YlxwToast(msg, "danger", "pm101", 2600); } catch (e) {} }
  function onSubmit() {
    var c = cur; if (!c) return;
    var btn = c.btn;
    try {
      if (btn) { btn.disabled = !0; btn.textContent = "发送中…"; }
      window.YLPM_SEND(c.inp.value, c.ta.value, function (res) {
        try { if (btn) { btn.disabled = !1; btn.textContent = "发送"; } } catch (e) {}
        if (res && res.ok) {
          try { c.ta.value = ""; c.inp.value = ""; } catch (e) {}
          toastOk(res.msg || "私信已发送");
          closeBox();
        } else {
          showInfo((res && res.msg) || "发送失败，请稍后再试", !0);
          toastErr((res && res.msg) || "发送失败，请稍后再试");
        }
      });
    } catch (e) {
      try { if (btn) { btn.disabled = !1; btn.textContent = "发送"; } } catch (x) {}
      showInfo("发送失败，请稍后再试", !0);
    }
  }
  /* 发送管线（headless，供按钮与测试共用）：冷却 → 校验 → YLPM_SUBMIT → 分支映射 */
  window.YLPM_SEND = function (to, content, onDone) {
    var done = function (r) { try { if (typeof onDone === "function") onDone(r); } catch (e) {} };
    var wait = COOLDOWN_MS - (Date.now() - lastOk);
    if (wait > 0) return done({ ok: !1, status: -1, msg: "发送太频繁，请 " + Math.ceil(wait / 1000) + " 秒后再试" });
    var tt = String(to == null ? "" : to).trim();
    if (!tt) return done({ ok: !1, status: -1, msg: "请填写收件人" });
    var c = String(content == null ? "" : content).trim();
    if (!c) return done({ ok: !1, status: -1, msg: "请填写私信内容" });
    if (c.length < MIN_LEN) return done({ ok: !1, status: -1, msg: "内容太短，至少 " + MIN_LEN + " 个字" });
    if (c.length > MAX_LEN) return done({ ok: !1, status: -1, msg: "内容太长，最多 " + MAX_LEN + " 个字" });
    if (typeof window.YLPM_SUBMIT !== "function") return done({ ok: !1, status: -1, msg: "私信通道未就绪，请稍后再试" });
    window.YLPM_SUBMIT({ to: tt, content: c }).then(function (r) {
      if (r && r.ok) { lastOk = Date.now(); return done({ ok: !0, status: 200, msg: "私信已发送" }); }
      if (r && r.status === 409) return done({ ok: !1, status: 409, msg: r.error || "发送太频繁，请稍后再试" });
      if (r && r.status === 400) return done({ ok: !1, status: 400, msg: r.error || "内容不合规" });
      if (r && r.status === 401) return done({ ok: !1, status: 401, msg: "登录状态已过期，请重新登录后再试" });
      done({ ok: !1, status: (r && r.status) || 0, msg: "发送失败（" + ((r && r.status) || "网络异常") + "），请稍后再试" });
    }, function () { done({ ok: !1, status: 0, msg: "网络异常，请稍后再试" }); });
  };
  window.YLPM_OPEN = function (to) {
    try {
      ensureStyle();
      if (cur) { try { cur.inp.value = String(to == null ? "" : to); } catch (e) {} return; }
      var mask = mk("div", "ylpm-mask");
      var box = mk("div", "ylpm-box");
      var title = mk("div", "ylpm-title"); title.textContent = "发私信";
      var labIn = mk("div", "ylpm-lab"); labIn.textContent = "收件人";
      var inp = mk("input", "ylpm-in"); inp.placeholder = "对方用户名";
      var labTa = mk("div", "ylpm-lab"); labTa.textContent = "内容（2~500 字）";
      var ta = mk("textarea", "ylpm-ta"); ta.maxLength = MAX_LEN; ta.placeholder = "想对道友说点什么…";
      var info = mk("div", "ylpm-info");
      var row = mk("div"); row.style.cssText = "margin-top:12px";
      var btn = mk("button", "ylpm-btn"); btn.textContent = "发送";
      var ghost = mk("button", "ylpm-ghost"); ghost.textContent = "关闭";
      box.appendChild(title); box.appendChild(labIn); box.appendChild(inp);
      box.appendChild(labTa); box.appendChild(ta); box.appendChild(info);
      box.appendChild(row); row.appendChild(btn); row.appendChild(ghost);
      mask.appendChild(box);
      cur = { mask: mask, box: box, inp: inp, ta: ta, info: info, btn: btn, to: String(to == null ? "" : to) };
      try { inp.value = cur.to; } catch (e) {}
      try { window.__YLPM_CUR = cur; } catch (e) {}
      btn.addEventListener("click", onSubmit);
      ghost.addEventListener("click", closeBox);
      try { document.body.appendChild(mask); } catch (e) { cur = null; return; }
    } catch (e) { try { closeBox(); } catch (x) {} }
  };
  try { ensureStyle(); } catch (e) {}
})();
''' + END_MARK + '\n'

# --------------------------------------------------------------------------- zh 同实现（门禁转义用；= yl_patch.zh）
def _zh(s):
    out = []
    for ch in s:
        o = ord(ch)
        if o < 128:
            out.append(ch)
        elif o <= 0xFFFF:
            out.append('\\u%04x' % o)
        else:
            o -= 0x10000
            out.append('\\u%04x\\u%04x' % (0xD800 + (o >> 10), 0xDC00 + (o & 0x3FF)))
    return ''.join(out)


# 本模块注入块的限域切片（块内断言一律在此切片内计数，防 fb100 同款分支翻倍假失败）
BLOCK_SCOPE = ('/* == YL_PM101_V1', A_Q0)


# --------------------------------------------------------------------------- 门禁（对最终产物文本计数）
def gates():
    W = BLOCK_SCOPE
    return [
        # ---- 注入块在位且唯一 ----
        ('PM·幂等标记',            '/* == YL_PM101_V1', 1, '==', ''),
        ('PM·结束标记',            '/* == end YL_PM101_V1 == */', 1, '==', ''),
        # ---- API 桥（限域：块内）----
        ('PM·API 提交函数',        'async function YLPM_SUBMIT(o)', 1, '==', '', W),
        ('PM·API window 暴露',     'window.YLPM_SUBMIT = YLPM_SUBMIT;', 1, '==', '', W),
        ('PM·raw fetch 直连',      'fetch(ln + "/mail/send"', 1, '==', '绝不经 Xc/YlxwPost', W),
        ('PM·旧路径 Xc 清零',      'Xc(`${ln}/mail/send`', 0, '==', '必须为 0'),
        ('PM·旧路径 YlxwPost 清零', 'YlxwPost(`${ln}/mail/send`', 0, '==', '必须为 0'),
        ('PM·YlxwPost 字面清零',   'YlxwPost("/mail/send"', 0, '==', '必须为 0'),
        ('PM·401 续期分支',        'if (r && r.status === 401) {', 1, '==', '', W),
        ('PM·pS 静默续期',         'try { if (typeof pS === "function") await pS(); } catch (e) {}', 1, '==', '续期后重试恰一次', W),
        ('PM·Bearer 复用 jo',      'if (a && a.Authorization) h.Authorization = a.Authorization;', 1, '==', '', W),
        ('PM·请求体恰 2 字段',     'to: String(o.to || ""), content: String(o.content || "")', 1, '==', '契约字段名', W),
        # ---- UI 管线（限域：块内）----
        ('PM·冷却/校验常数',       'var COOLDOWN_MS = 30000, MIN_LEN = 2, MAX_LEN = 500;', 1, '==', '30s 冷却 + 2~500 字', W),
        ('PM·冷却模块级时间戳',    'var lastOk = 0, cur = null;', 1, '==', '', W),
        ('PM·冷却拦截',            'var wait = COOLDOWN_MS - (Date.now() - lastOk);', 1, '==', '', W),
        ('PM·成功才记冷却',        'lastOk = Date.now();', 1, '==', '仅 200 记冷却', W),
        ('PM·校验·收件人空',       'if (!tt) return done({ ok: !1, status: -1, msg: "' + _zh('请填写收件人') + '" });', 1, '==', '', W),
        ('PM·校验·内容空',         'if (!c) return done({ ok: !1, status: -1, msg: "' + _zh('请填写私信内容') + '" });', 1, '==', '', W),
        ('PM·校验·太短',           'if (c.length < MIN_LEN)', 1, '==', '', W),
        ('PM·校验·太长',           'if (c.length > MAX_LEN)', 1, '==', '', W),
        ('PM·409 显示服务端 error', 'if (r && r.status === 409) return done({ ok: !1, status: 409, msg: r.error || "'
                                   + _zh('发送太频繁，请稍后再试') + '" });', 1, '==', '30s 频控/日限 50 都走此分支', W),
        ('PM·400 显示服务端 error', 'if (r && r.status === 400) return done({ ok: !1, status: 400, msg: r.error || "'
                                   + _zh('内容不合规') + '" });', 1, '==', '', W),
        ('PM·401 不踢登录文案',    _zh('登录状态已过期，请重新登录后再试'), 1, '==', '401 终态只提示不登出', W),
        ('PM·成功文案',            _zh('私信已发送'), 2, '==', '管线返回值 + onSubmit 兜底各 1'),
        ('PM·成功 toast(gain)',    '"gain", "pm101", 2600', 1, '==', 'YlxwToast 无 success 档，绿色=gain', W),
        ('PM·失败 toast(danger)',  '"danger", "pm101", 2600', 1, '==', '', W),
        ('PM·成功清表单',          'c.ta.value = ""; c.inp.value = "";', 1, '==', '', W),
        ('PM·发送管线 headless',   'window.YLPM_SEND = function (to, content, onDone) {', 1, '==', '', W),
        ('PM·模态开启函数',        'window.YLPM_OPEN = function (to) {', 1, '==', '', W),
        ('PM·已开则改收件人',      'cur.inp.value = String(to == null ? "" : to);', 1, '==', '', W),
        ('PM·打开即预填收件人',    'inp.value = cur.to;', 1, '==', '', W),
        ('PM·测试钩子 OPEN',       'window.__YLPM_CUR = cur;', 1, '==', '', W),
        ('PM·测试钩子 CLOSE',      'window.__YLPM_CUR = null;', 1, '==', '', W),
        ('PM·关闭按钮接线',        'ghost.addEventListener("click", closeBox);', 1, '==', '', W),
        ('PM·样式幂等',            's.id = "ylpm-style";', 1, '==', '', W),
        ('PM·load 即注入样式',     'try { ensureStyle(); } catch (e) {}', 1, '==', '', W),
        # ---- E2 仙友录好友行 ----
        ('好友行·私信钮整钉',      PM_FRIENDS_BTN, 1, '==', '基线为 0，插入后恰 1'),
        ('好友行·私信主文案',      r'children: "\u79c1\u4fe1"', 1, '==', ''),
        ('好友行·onClick 接线',    'window.YLPM_OPEN(N.name)', 1, '==', 'window 零作用域假设'),
        ('好友行·送礼钮未动',      'f("ft" + N.id, "/friends/gift", { friendId: N.id }', 1, '==', ''),
        ('好友行·行键未动',        ', "f" + N.id); })', 1, '==', ''),
        # ---- E3 在线人物玩家行（R-144 DOM 栈，raw UTF-8 态）----
        ('在线行·私信 push',       'acts.push(btn("私信"', 1, '==', 'raw UTF-8 needle'),
        ('在线行·私信接 OPEN',     'window.YLPM_OPEN(u)', 1, '==', ''),
        ('在线行·私信在切磋后',    A_ON + 'acts.push(btn("私信"', 1, '==', 'adjacency：紧随切磋 push'),
        ('在线行·切磋钮未动',      'acts.push(btn("切磋",null,function(){YlxwPost("/arena/challenge",{name:u})', 1, '==', ''),
        ('R144·模块标记未动',      '/*YLXW_R144_V2919*/', 1, '==', ''),
        ('R144·守卫未动',          'window.__ylR144', 2, '==', 'set+check'),
        ('R144·onlineRow 未动',    'function onlineRow(p){', 1, '==', ''),
        # ---- E4 信箱行 ----
        ('信箱·kind 判定计数',     'g.kind === "player"', 2, '==', '发信人 span + 回信钮两处'),
        ('信箱·无 kind 兜底计数',  '!g.kind && g.sender && g.sender !== "system"', 2, '==', '旧 list 响应（无 kind）按 sender 判定'),
        ('信箱·发信人 span',       PM_PM_COND + r' && e.jsx("span", { className: "text-[10px] text-sky-300", children: "\u53d1\u4fe1\u4eba " + (g.sender || "") })', 1, '==', ''),
        ('信箱·回信钮整钉',        PM_PM_COND + r' && e.jsx(YlxwBtn, { tone: "ghost", onClick: function() { try { typeof window.YLPM_OPEN === "function" && window.YLPM_OPEN(g.sender); } catch (ylpme) {} }, children: "\u56de\u4fe1" })', 1, '==', ''),
        ('信箱·回信主文案',        r'children: "\u56de\u4fe1"', 1, '==', ''),
        ('信箱·回信接 OPEN',       'window.YLPM_OPEN(g.sender)', 1, '==', ''),
        ('信箱·领取钮未动',        'f("c" + g.id, "/mail/claim", { id: g.id }', 1, '==', ''),
        ('信箱·删除钮未动',        'e.jsx(YlxwMailDelBtn, { mail: g, busy: !!u, onDone: c }, "d" + g.id)', 1, '==', ''),
        ('信箱·行键未动',          ', "m" + g.id);', 1, '==', ''),
        ('信箱·全部已读未动',      'f("readall", "/mail/read", { all: !0 }', 1, '==', ''),
        # ---- 冻结：既有路径一字未动 ----
        ('冻结·Q0 链未动',         'const Q0="/yl/api"', 1, '==', ''),
        ('冻结·jo 未动',           'function jo(){', 1, '==', ''),
        ('冻结·pS 未动',           'async function pS(){', 1, '==', ''),
        ('冻结·YlxwTMail 未动',    'function YlxwTMail() {', 1, '==', ''),
        ('冻结·YlxwTFriends 未动', 'function YlxwTFriends() {', 1, '==', ''),
        ('冻结·YlxwPanelModal 未动', 'function YlxwPanelModal(p)', 1, '==', ''),
        ('冻结·组件表未动',        'var YLXW_COMP = { mail: YlxwTMail', 1, '==', ''),
        ('冻结·fb100 块在位',      '/* == end YL_FB100_V1 == */', 1, '==', ''),
        ('冻结·mail-ext 在位',     'YL_MAIL_CLAIMALL_V28', 2, '==', '2026-10-21 v100 实测=2（标记+注记）'),
    ]


V28_BAN = ('iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-')


def apply(p, ctx):
    """就地改造 bundle 文本，返回门禁列表。ctx = {'zh': zh, 'base_text': str}。"""
    zh = ctx['zh']
    block = zh(INJECT_JS)

    # fail-closed 自检（与 build_v26n 的 V28 注入块检查同口径，standalone 干跑也受约束）
    bad = [c for c in block if ord(c) >= 128]
    assert not bad, 'INJECT_JS zh() 后仍含非 ASCII: %r' % bad[:8]
    for ban in V28_BAN:
        assert ban not in block, 'INJECT_JS 含禁用模式: %s' % ban

    # E1 API 桥 + 写信弹窗（ln/jo/pS 同作用域；求值期只定义函数/挂 window/注入 <style>）
    p.insert_before('pm101-api-ui-block', A_Q0, block + '\n', expect=1,
                    note='PM-101 私信 API 桥 + 自包含写信弹窗（复用 ln/jo/pS，window 暴露）')
    # E2 仙友录好友行尾追加「私信」钮
    p.replace('pm101-friends-btn', A_FR, N_FR, expect=1,
              note='「仙友录」好友行「私信」钮（内层 flex 行第 3 子，onClick→window.YLPM_OPEN(N.name)）')
    # E3 在线人物玩家行：切磋 push 之后追加「私信」push（R-144 DOM 栈）
    p.replace('pm101-online-btn', A_ON, N_ON, expect=1,
              note='「在线人物」玩家行「私信」push（if(!p.isSelf) 内、切磋之后，btn 工厂直呼 window.YLPM_OPEN(u)）')
    # E4 信箱行：kind='player' 渲染发信人 + 回信钮（插在领取钮条件之前）
    p.insert_before('pm101-mail-reply', A_MA, PM_MAIL_INSERT, expect=1,
                    note='「信箱」行「发信人」span +「回信」钮（kind=player 条件渲染 → window.YLPM_OPEN(g.sender)）')

    return gates()
