# -*- coding: utf-8 -*-
r"""
yl_fb100_ext.py -- FB-100 玩家反馈（客户端第 99 模块；v28 契约：INJECT_JS + apply(p,ctx) -> gates）

1.1 接口契约 A（反馈入口迁移，本版；1.0 = 底部栏第 6 卡形态已废弃回退）：
    ① 底部操作栏恢复原样：5 卡（打坐/历练/秘境/炼丹·炼器/宗门），grid className 补丁、
       第 6「反馈」卡、.ylbar6 六列 <style> 规则全部回退（=0.9.62 原状，本模块不再改写底栏）；
    ② 顶栏（header 右侧 hidden md:flex 工具条）「角色」按钮左侧紧邻插入「反馈」按钮
       （amber 高亮内联样式保底 + 红点角标，onClick→window.YLFB_OPEN 守卫调用）；
    ③ 移动端（该工具条 hidden md:flex 手机不可见）：☰ 抽屉列表「设置」项之前插入等价「反馈」入口
       （与「信箱」同款 YlxwMk("mail") 图标、amber 配色，onClick 同守卫）；
    ④ 模态「bug 与需求反馈」+ 提交链路（raw fetch+Bearer / 401 静默续期重试恰一次 / 60s 冷却 /
       成功·409·失败 toast）逐字节保持 1.0 行为 —— INJECT_JS 相对 1.0 唯一改动 =
       ensureStyle() 删去 .ylbar6 一条规则（随底栏回退），其余一字不动。

接口契约（与三端共同遵守，字段名一个都不能改）：
    POST <ln>/feedback（= /yl/api/feedback，authenticateToken 必须登录）
    入参 {kind, content, contact?}；kind ∈ {'bug','suggestion'}
    客户端请求体固定 6 字段：kind / content / contact / version / realm / ua
      · version = YlxwVersionGet()（typeof 守卫：基线单测环境无此函数时返回 ""）
      · realm   = Be.getState().player.realm（typeof 守卫）
    成功 200 {ok:true,id}；409 {error:'提交太频繁，请稍后再试'}；400/500 → {error}
    ★ 绝不经 Xc()/YlxwPost()（其 401/403 分支会强制登出玩家）——本模块 raw fetch，
      401 时只调 pS() 静默续期后重试一次，任何失败都不触碰登录态。

契约（本文件对外只导出这两个符号，同 patches/client/yl_saveretry_ext.py）：
    INJECT_JS : str        注入 JS 块（含中文，由构建侧统一 zh() 转义）
    apply(p, ctx) -> gates
        p   : yl_patch.Patcher
        ctx : {'zh': zh 函数, 'base_text': str}
        gates: list[(name, needle, expected, op, note)]，op ∈ {'==','>=','<='}

锚点实测（基线 build/assets/index-v26m-20260927.js，1419571 chars，2026-10-21 本环实测）：
    A_Q0   'const Q0="/yl/api"'                                      count=1（ln 链式派生起点）
    A_HDR  'style:{flexBasis:"420px"},children:[e.jsxs("button",{onClick:c,'
                                                                     count=1（工具条容器
        "hidden md:flex gap-1 flex-wrap items-center justify-end flex-1 min-w-0" 的 children 开头；
        其后第一个按钮即「角色」onClick:c ⇒ 插在 children:[ 之后 = 工具条首位 =「角色」左侧紧邻）
    A_DW   '{icon:Om,label:"设置",onClick:j,color:"text-stone-400"}'  count=1（w4 抽屉列表「设置」项）
    A_BAR  'md:grid-cols-5 gap-2 md:gap-4 shrink-0 fixed'            count=1（底栏容器，仅作回退门禁，不改写）
    A_P    ']}),e.jsx("p",{className:"col-span-2 md:col-span-5 text-center text-[10px] md:text-xs text-stone-500 mt-1"'
                                                                     count=1（底栏宗门卡↔页脚，仅作回退门禁，不改写）
    冲突体检（基线全 count=0）：'YLFB_' / 'ylfb-' / 'children:"反馈"' / 'label:"反馈"' /
      'rgba(245,158,11,.45)' / 'rgba(239,68,68,.9)' / 'ylbar6' / '#451a03'。
    链上体检（2026-10-21 对 patches/client/*.py + build_v26n.py + localtest/yl_*_ext.py 全量
      241 文件源扫描）：'flexBasis' / 'label:"设置"' / 'children:"角色"' / 'YlxwMk("mail")'
      无任何前置模块触碰 ⇒ 第 99 位套用时锚区不受前置扰动；yl_entry_ext / yl_ui_ext 只动
      工具条「仙途指引」之后与抽屉首部分组 / 「仙友录」之前，与本模块锚区零交集。
    冻结体检：'const Q0="/yl/api"' / 'function jo(){' / 'function Nd(t){' / 'async function pS(){' /
      'async function Xc(' / 'const Jy=Rt.memo(N4)' / 'Zy=Rt.memo(j4)' / 'S4=Rt.memo(w4)' /
      'children:"快捷键见设置"' / 'children:"机缘 · 战斗"' 全部 count=1。

中文纪律：
    · INJECT_JS 内的中文 → 构建侧 zh() 转 \uXXXX（apply 内再自检一遍，fail-closed）。
    · HDR_BTN_JSX / DW_ITEM（插进 React JSX 树）用 raw UTF-8 —— 与 bundle 既有 JSX 中文同形态
      （build_v26n.py 抽屉入口 DRAWER_ITEM 'label:"仙途指引"' 即先例），不走 zh()。
    · gates 里断言 INJECT_JS 的中文一律经本模块 _zh()（= yl_patch.zh 同实现）转义，
      否则 count==0 假失败（SKILL §13.4）；断言 JSX 注入的中文直接数 raw UTF-8。
"""

# --------------------------------------------------------------------------- 锚点（全部实测 count==1）
MARK = '/* == YL_FB100_V1 (FB-100 player feedback; raw fetch + ln/jo/pS; NEVER Xc/YlxwPost) == */'
END_MARK = '/* == end YL_FB100_V1 == */'

# E1 注入点：ln 链式派生起点（其后是 V0/ln/Hr/Pl；本块只定义函数与挂 window，求值期不引用它们，
#     调用发生在点击时 —— ln/jo/pS 彼时必然已初始化；jo 是同作用域函数声明，hoisted）
A_Q0 = 'const Q0="/yl/api"'

# E2 顶栏工具条首位（=「角色」按钮左侧紧邻）：工具条容器 children:[ 与「角色」按钮开头之间
A_HDR = 'style:{flexBasis:"420px"},children:[e.jsxs("button",{onClick:c,'

# E3 抽屉「设置」项之前（w4 列表 C 的成员对象，逗号分隔）
A_DW = '{icon:Om,label:"设置",onClick:j,color:"text-stone-400"}'

# ---- 回退门禁专用（1.0 底栏形态的锚，本版不再改写，仅断言原状）----
A_BAR = 'md:grid-cols-5 gap-2 md:gap-4 shrink-0 fixed'
A_P = (']}),e.jsx("p",{className:"col-span-2 md:col-span-5 text-center text-[10px] '
       'md:text-xs text-stone-500 mt-1"')

# --------------------------------------------------------------------------- 顶栏按钮 JSX（raw UTF-8，不走 zh()）
# 形态对齐工具条既有「角色」按钮（flex items-center gap-1.5 px-2 py-1.5 … min-w-[34px] min-h-[32px]
# justify-center whitespace-nowrap，全部已被编译进 CSS，SKILL §22.3；relative 亦在预构建 CSS）；
# 高亮全内联 style 保底（amber-950 底 + amber-500 描边 + 光晕，区别于 stone 色系）；
# 红点角标 absolute 右上（按钮带 relative）。
HDR_BTN_JSX = ('e.jsxs("button",{onClick:function(){try{typeof window.YLFB_OPEN==="function"&&window.YLFB_OPEN()}'
               'catch(ylfbe){}},className:"relative flex items-center gap-1.5 px-2 py-1.5 rounded border '
               'transition-colors text-xs min-w-[34px] min-h-[32px] justify-center whitespace-nowrap",'
               'style:{borderColor:"#f59e0b",background:"#451a03",boxShadow:"0 0 8px rgba(245,158,11,.45)"},children:['
               'e.jsx("span",{style:{position:"absolute",top:"3px",right:"3px",width:"8px",height:"8px",'
               'borderRadius:"50%",background:"#ef4444",boxShadow:"0 0 4px rgba(239,68,68,.9)"}}),'
               'e.jsx("span",{style:{color:"#fbbf24",fontWeight:"700"},children:"反馈"})]})')

N_HDR = 'style:{flexBasis:"420px"},children:[' + HDR_BTN_JSX + ',e.jsxs("button",{onClick:c,'

# --------------------------------------------------------------------------- 抽屉入口项（raw UTF-8，不走 zh()）
# 与「信箱」同款 YlxwMk("mail") 图标、amber 配色（w4 列表既有项同形态）；onClick 走 window 守卫
# 复用 FB-100 模态（YLFB_OPEN 由 E1 块暴露）；渲染走 w4 既有普通按钮分支（无 locked/group 字段），
# 点击后经 g(q.onClick) 自动收起抽屉。
DW_ITEM = ('{icon:YlxwMk("mail"),label:"反馈",'
           'onClick:()=>{try{typeof window.YLFB_OPEN==="function"&&window.YLFB_OPEN()}catch(ylfbe){}},'
           'color:"text-amber-300"},')

N_DW = DW_ITEM + A_DW

# --------------------------------------------------------------------------- 注入块（中文由构建侧 zh() 转义）
# 相对 1.0 唯一改动：ensureStyle() 不再注入 .ylbar6 六列规则（随底栏回退）；其余逐字节不变。
INJECT_JS = '''
/* == YL_FB100_V1 (FB-100 player feedback; raw fetch + ln/jo/pS; NEVER Xc/YlxwPost) == */
/* ---- part 1: API bridge（与 ln/jo/pS 同作用域；经 window 暴露，调用方零作用域假设，SKILL §13.4）---- */
function YLFB_Version() {
  try { return (typeof YlxwVersionGet === "function") ? String(YlxwVersionGet() || "") : ""; } catch (e) { return ""; }
}
function YLFB_RealmOf() {
  try {
    var s = (typeof Be !== "undefined" && Be && Be.getState) ? Be.getState() : null;
    var p = s && s.player ? s.player : null;
    return (p && p.realm != null) ? String(p.realm) : "";
  } catch (e) { return ""; }
}
async function YLFB_SUBMIT(o) {
  o = o || {};
  var send = function () {
    var h = { "Content-Type": "application/json" };
    try { var a = jo(); if (a && a.Authorization) h.Authorization = a.Authorization; } catch (e) {}
    return fetch(ln + "/feedback", { method: "POST", headers: h, body: JSON.stringify({
      kind: o.kind === "suggestion" ? "suggestion" : "bug",
      content: String(o.content || ""), contact: String(o.contact || ""),
      version: YLFB_Version(), realm: YLFB_RealmOf(),
      ua: (typeof navigator !== "undefined" && navigator.userAgent) ? navigator.userAgent : "" }) });
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
try { window.YLFB_SUBMIT = YLFB_SUBMIT; } catch (e) {}
/* ---- part 2: UI（自包含 DOM 模态；全链 try/catch —— 本游戏无 app 级 ErrorBoundary，抛异常=全站白屏）---- */
(function () {
  var COOLDOWN_MS = 60000, MIN_LEN = 5, MAX_LEN = 2000, MAX_CONTACT = 100;
  var lastOk = 0, cur = null;
  function gid(id) { try { return document.getElementById(id); } catch (e) { return null; } }
  function mk(tag, cls, css) { var n = document.createElement(tag); if (cls) n.className = cls; if (css) n.style.cssText = css; return n; }
  function ensureStyle() {
    if (gid("ylfb-style")) return;
    var s = document.createElement("style"); s.id = "ylfb-style";
    s.textContent = ".ylfb-mask{position:fixed;left:0;top:0;right:0;bottom:0;background:rgba(0,0,0,.62);z-index:2147483000;display:flex;align-items:center;justify-content:center;padding:12px}"
      + ".ylfb-box{width:100%;max-width:520px;max-height:86vh;overflow:auto;background:#1c1917;color:#e7e5e4;border:1px solid #f59e0b;border-radius:12px;padding:14px 16px;font:14px/1.6 system-ui,-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;box-shadow:0 8px 40px rgba(0,0,0,.6)}"
      + ".ylfb-title{font-weight:700;font-size:16px;color:#fbbf24;margin-bottom:10px}"
      + ".ylfb-lab{font-size:12px;color:#a8a29e;margin:8px 0 4px}"
      + ".ylfb-kind{display:inline-block;padding:4px 12px;margin-right:8px;border-radius:8px;border:1px solid #57534e;cursor:pointer;font-size:13px;color:#d6d3d1}"
      + ".ylfb-kind-on{border-color:#f59e0b;color:#fbbf24;background:rgba(245,158,11,.12)}"
      + ".ylfb-ta,.ylfb-in{width:100%;box-sizing:border-box;background:#0c0a09;color:#e7e5e4;border:1px solid #57534e;border-radius:8px;padding:8px;font:13px/1.5 system-ui,sans-serif}"
      + ".ylfb-ta{min-height:110px;resize:vertical}"
      + ".ylfb-btn{display:inline-block;padding:8px 18px;border-radius:8px;border:1px solid #f59e0b;background:#f59e0b;color:#1c1917;font-weight:700;cursor:pointer;font-size:14px}"
      + ".ylfb-btn[disabled]{opacity:.55;cursor:not-allowed}"
      + ".ylfb-ghost{display:inline-block;padding:8px 14px;margin-left:8px;border-radius:8px;border:1px solid #57534e;color:#d6d3d1;background:transparent;cursor:pointer;font-size:14px}"
      + ".ylfb-info{font-size:12px;margin-top:8px;min-height:18px;color:#a8a29e}"
      + ".ylfb-err{color:#f87171}.ylfb-ok{color:#34d399}";
    try { (document.head || document.body).appendChild(s); } catch (e) {}
  }
  function closeBox() {
    try { if (cur && cur.mask && cur.mask.parentNode && cur.mask.parentNode.removeChild) cur.mask.parentNode.removeChild(cur.mask); } catch (e) {}
    cur = null;
    try { window.__YLFB_CUR = null; } catch (e) {}
  }
  function showInfo(msg, bad) {
    try { if (cur && cur.info) { cur.info.textContent = String(msg); cur.info.className = "ylfb-info " + (bad ? "ylfb-err" : "ylfb-ok"); } } catch (e) {}
  }
  function toastOk(msg) { try { if (typeof YlxwToast === "function") YlxwToast(msg, "gain", "fb100", 2600); } catch (e) {} }
  function toastErr(msg) { try { if (typeof YlxwToast === "function") YlxwToast(msg, "danger", "fb100", 2600); } catch (e) {} }
  function setKind(k) {
    if (!cur) return;
    cur.kind = k;
    try { cur.kBug.className = "ylfb-kind" + (k === "bug" ? " ylfb-kind-on" : "");
          cur.kSug.className = "ylfb-kind" + (k === "suggestion" ? " ylfb-kind-on" : ""); } catch (e) {}
  }
  function onSubmit() {
    var c = cur; if (!c) return;
    var btn = c.btn;
    try {
      if (btn) { btn.disabled = !0; btn.textContent = "提交中…"; }
      window.YLFB_SEND(c.kind, c.ta.value, c.inp.value, function (res) {
        try { if (btn) { btn.disabled = !1; btn.textContent = "提交"; } } catch (e) {}
        if (res && res.ok) {
          try { c.ta.value = ""; c.inp.value = ""; } catch (e) {}
          toastOk(res.msg || "反馈已提交");
          closeBox();
        } else {
          showInfo((res && res.msg) || "提交失败，请稍后再试", !0);
          toastErr((res && res.msg) || "提交失败，请稍后再试");
        }
      });
    } catch (e) {
      try { if (btn) { btn.disabled = !1; btn.textContent = "提交"; } } catch (x) {}
      showInfo("提交失败，请稍后再试", !0);
    }
  }
  /* 发送管线（headless，供按钮与测试共用）：冷却 → 校验 → YLFB_SUBMIT → 分支映射 */
  window.YLFB_SEND = function (kind, content, contact, onDone) {
    var done = function (r) { try { if (typeof onDone === "function") onDone(r); } catch (e) {} };
    var wait = COOLDOWN_MS - (Date.now() - lastOk);
    if (wait > 0) return done({ ok: !1, status: -1, msg: "提交太频繁，请 " + Math.ceil(wait / 1000) + " 秒后再试" });
    var c = String(content == null ? "" : content).trim();
    if (!c) return done({ ok: !1, status: -1, msg: "请填写反馈内容" });
    if (c.length < MIN_LEN) return done({ ok: !1, status: -1, msg: "内容太短，至少 " + MIN_LEN + " 个字" });
    if (c.length > MAX_LEN) return done({ ok: !1, status: -1, msg: "内容太长，最多 " + MAX_LEN + " 个字" });
    var ct = String(contact == null ? "" : contact).trim();
    if (ct.length > MAX_CONTACT) return done({ ok: !1, status: -1, msg: "联系方式最多 " + MAX_CONTACT + " 个字" });
    if (typeof window.YLFB_SUBMIT !== "function") return done({ ok: !1, status: -1, msg: "反馈通道未就绪，请稍后再试" });
    window.YLFB_SUBMIT({ kind: kind === "suggestion" ? "suggestion" : "bug", content: c, contact: ct }).then(function (r) {
      if (r && r.ok) { lastOk = Date.now(); return done({ ok: !0, status: 200, msg: "已收到，感谢反馈" }); }
      if (r && r.status === 409) return done({ ok: !1, status: 409, msg: r.error || "提交太频繁，请稍后再试" });
      if (r && r.status === 401) return done({ ok: !1, status: 401, msg: "登录状态已过期，请重新登录后再试" });
      if (r && r.status === 400 && r.error) return done({ ok: !1, status: 400, msg: r.error });
      done({ ok: !1, status: (r && r.status) || 0, msg: "提交失败（" + ((r && r.status) || "网络异常") + "），请稍后再试" });
    }, function () { done({ ok: !1, status: 0, msg: "网络异常，请稍后再试" }); });
  };
  window.YLFB_OPEN = function () {
    try {
      ensureStyle();
      if (cur) return;
      var mask = mk("div", "ylfb-mask");
      var box = mk("div", "ylfb-box");
      var title = mk("div", "ylfb-title"); title.textContent = "bug 与需求反馈";
      var labKind = mk("div", "ylfb-lab"); labKind.textContent = "类型";
      var kBug = mk("span", "ylfb-kind"); kBug.textContent = "bug";
      var kSug = mk("span", "ylfb-kind"); kSug.textContent = "需求建议";
      var labTa = mk("div", "ylfb-lab"); labTa.textContent = "内容（5~2000 字）";
      var ta = mk("textarea", "ylfb-ta"); ta.maxLength = MAX_LEN; ta.placeholder = "遇到的问题，或想要的功能…";
      var labIn = mk("div", "ylfb-lab"); labIn.textContent = "联系方式（选填）";
      var inp = mk("input", "ylfb-in"); inp.maxLength = MAX_CONTACT; inp.placeholder = "邮箱 / QQ / 微信，便于回访";
      var info = mk("div", "ylfb-info");
      var row = mk("div"); row.style.cssText = "margin-top:12px";
      var btn = mk("button", "ylfb-btn"); btn.textContent = "提交";
      var ghost = mk("button", "ylfb-ghost"); ghost.textContent = "关闭";
      box.appendChild(title); box.appendChild(labKind); box.appendChild(kBug); box.appendChild(kSug);
      box.appendChild(labTa); box.appendChild(ta); box.appendChild(labIn); box.appendChild(inp);
      box.appendChild(info); box.appendChild(row); row.appendChild(btn); row.appendChild(ghost);
      mask.appendChild(box);
      cur = { mask: mask, box: box, ta: ta, inp: inp, info: info, btn: btn, kBug: kBug, kSug: kSug, kind: "bug" };
      try { window.__YLFB_CUR = cur; } catch (e) {}
      kBug.addEventListener("click", function () { setKind("bug"); });
      kSug.addEventListener("click", function () { setKind("suggestion"); });
      btn.addEventListener("click", onSubmit);
      ghost.addEventListener("click", closeBox);
      try { document.body.appendChild(mask); } catch (e) { cur = null; return; }
      setKind("bug");
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


# --------------------------------------------------------------------------- 门禁（对最终产物文本计数）
def gates():
    return [
        # ---- 注入块在位且唯一 ----
        ('FB100·幂等标记',            '/* == YL_FB100_V1', 1, '==', ''),
        ('FB100·结束标记',            '/* == end YL_FB100_V1 == */', 1, '==', ''),
        # ---- API 桥（1.0 原样保留）----
        ('FB100·API 提交函数',        'async function YLFB_SUBMIT(o)', 1, '==', ''),
        ('FB100·API window 暴露',     'window.YLFB_SUBMIT = YLFB_SUBMIT;', 1, '==', ''),
        ('FB100·raw fetch 直连',      'fetch(ln + "/feedback"', 1, '==', '绝不经 Xc/YlxwPost'),
        ('FB100·旧路径 Xc 清零',      'Xc(`${ln}/feedback`', 0, '==', '必须为 0'),
        ('FB100·旧路径 YlxwPost 清零', 'YlxwPost(`${ln}/feedback`', 0, '==', '必须为 0'),
        ('FB100·401 续期分支',        'if (r && r.status === 401) {', 1, '==', ''),
        ('FB100·pS 静默续期',         'try { if (typeof pS === "function") await pS(); } catch (e) {}', 1, '==', '续期后重试恰一次'),
        ('FB100·Bearer 复用 jo',      'if (a && a.Authorization) h.Authorization = a.Authorization;', 1, '==', ''),
        ('FB100·请求体 version/realm', 'version: YLFB_Version(), realm: YLFB_RealmOf(),', 1, '==', '契约字段名'),
        ('FB100·请求体 ua 字段',      'navigator.userAgent) ? navigator.userAgent : ""', 1, '==', ''),
        # ---- UI 管线（1.0 原样保留）----
        ('FB100·冷却/校验常数',       'var COOLDOWN_MS = 60000, MIN_LEN = 5, MAX_LEN = 2000, MAX_CONTACT = 100;', 1, '==', ''),
        ('FB100·冷却模块级时间戳',    'var lastOk = 0, cur = null;', 1, '==', ''),
        ('FB100·冷却拦截',            'var wait = COOLDOWN_MS - (Date.now() - lastOk);', 1, '==', ''),
        ('FB100·成功才记冷却',        'lastOk = Date.now();', 1, '==', '仅 200 记冷却'),
        ('FB100·校验·非空',           'if (!c) return done({ ok: !1, status: -1, msg: "' + _zh('请填写反馈内容') + '" });', 1, '==', ''),
        ('FB100·校验·太短',           'if (c.length < MIN_LEN)', 1, '==', ''),
        ('FB100·校验·太长',           'if (c.length > MAX_LEN)', 1, '==', ''),
        ('FB100·校验·联系长度',       'if (ct.length > MAX_CONTACT)', 1, '==', ''),
        ('FB100·409 显示服务端 error', 'if (r && r.status === 409) return done({ ok: !1, status: 409, msg: r.error || "'
                                       + _zh('提交太频繁，请稍后再试') + '" });', 1, '==', '显示服务端 error'),
        ('FB100·401 不踢登录文案',    _zh('登录状态已过期，请重新登录后再试'), 1, '==', '401 终态只提示不登出'),
        ('FB100·成功文案',            _zh('已收到，感谢反馈'), 1, '==', ''),
        ('FB100·成功 toast(gain)',    '"gain", "fb100", 2600', 1, '==', 'YlxwToast 无 success 档，绿色=gain'),
        ('FB100·失败 toast(danger)',  '"danger", "fb100", 2600', 1, '==', ''),
        ('FB100·成功清表单',          'c.ta.value = ""; c.inp.value = "";', 1, '==', ''),
        ('FB100·发送管线 headless',   'window.YLFB_SEND = function (kind, content, contact, onDone) {', 1, '==', ''),
        ('FB100·模态开启函数',        'window.YLFB_OPEN = function () {', 1, '==', ''),
        ('FB100·测试钩子 OPEN',       'window.__YLFB_CUR = cur;', 1, '==', ''),
        ('FB100·测试钩子 CLOSE',      'window.__YLFB_CUR = null;', 1, '==', ''),
        ('FB100·关闭按钮接线',        'ghost.addEventListener("click", closeBox);', 1, '==', ''),
        # ---- 样式（模态样式保留；.ylbar6 六列规则随底栏回退删除）----
        ('FB100·模态遮罩样式',        '.ylfb-mask{position:fixed;left:0;top:0;right:0;bottom:0', 1, '==', '模态样式保留'),
        ('FB100·样式幂等',            's.id = "ylfb-style";', 1, '==', ''),
        ('FB100·load 即注入样式',     'try { ensureStyle(); } catch (e) {}', 1, '==', ''),
        ('回退·ylbar6 全文清零',      'ylbar6', 0, '==', '1.0 六列样式已回退'),
        ('回退·6 列媒体查询清零',     '@media(min-width:768px){.ylbar6{grid-template-columns:repeat(6,minmax(0,1fr))}}', 0, '==', ''),
        # ---- 回退：底栏原状（=0.9.62，5 卡）----
        ('回退·底栏容器原样',         'grid grid-cols-3 md:grid-cols-5 gap-2 md:gap-4 shrink-0 fixed', 1, '==', 'md:grid-cols-5 卡片数=5'),
        ('回退·容器未追加 ylbar6',    'md:grid-cols-5 ylbar6', 0, '==', '1.0 className 补丁已回退'),
        ('回退·宗门卡↔页脚未插卡',    A_P, 1, '==', '1.0 第 6 卡已撤、页脚 <p> 原位'),
        ('回退·反馈子题清零',         'children:"bug · 建议"', 0, '==', '1.0 底栏卡标记'),
        ('回退·旧红点尺寸清零',       'width:"10px",height:"10px",borderRadius:"50%"', 0, '==', '1.0 底栏卡红点'),
        ('页脚提示未动',              'children:"快捷键见设置"', 1, '==', ''),
        # ---- 顶栏「反馈」按钮（「角色」左侧紧邻）----
        ('顶栏·紧邻角色左侧',         N_HDR, 1, '==', '工具条首位、「角色」按钮紧随其后'),
        ('顶栏·角色按钮在位',         'children:[e.jsx(aa,{size:15}),e.jsx("span",{children:"角色"})]})', 1, '==', ''),
        ('顶栏·主文案',               'children:"反馈"', 1, '==', '基线为 0，插入后恰 1'),
        ('顶栏·红点角标',             'position:"absolute",top:"3px",right:"3px",width:"8px",height:"8px",borderRadius:"50%",background:"#ef4444"', 1, '==', ''),
        ('顶栏·amber 高亮内联',       'borderColor:"#f59e0b",background:"#451a03",boxShadow:"0 0 8px rgba(245,158,11,.45)"', 1, '==', '内联样式保底'),
        ('入口·OPEN 守卫共 2 处',     'typeof window.YLFB_OPEN==="function"', 2, '==', '顶栏 + 抽屉各 1'),
        ('入口·接线 OPEN 共 2 处',    '&&window.YLFB_OPEN()', 2, '==', '顶栏 + 抽屉各 1'),
        # ---- 抽屉「反馈」入口（「设置」项之前）----
        ('抽屉·入口在设置项前',       N_DW, 1, '==', '移动端 ☰ 菜单等价入口'),
        ('抽屉·设置项在位',           A_DW, 1, '==', ''),
        ('抽屉·入口 label',           'label:"反馈"', 1, '==', '抽屉用 label、顶栏用 children'),
        ('抽屉·信箱同款图标',         'YlxwMk("mail")', 2, '==', '信箱 1 + 反馈 1'),
        # ---- 冻结：既有路径一字未动 ----
        ('冻结·Q0 链未动',            'const Q0="/yl/api"', 1, '==', ''),
        ('冻结·jo 未动',              'function jo(){', 1, '==', ''),
        ('冻结·Nd 未动',              'function Nd(t){', 1, '==', ''),
        ('冻结·pS 未动',              'async function pS(){', 1, '==', ''),
        ('冻结·Xc 未动',              'async function Xc(', 1, '==', '其 401/403 分支保持原样、绝不经由'),
        ('冻结·N4 memo 未动',         'const Jy=Rt.memo(N4)', 1, '==', ''),
        ('冻结·j4 memo 未动',         'Zy=Rt.memo(j4)', 1, '==', ''),
        ('冻结·w4 memo 未动',         'S4=Rt.memo(w4)', 1, '==', ''),
        ('冻结·历练卡未动',           'children:"机缘 · 战斗"', 1, '==', ''),
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

    # E1 API 桥 + UI 模态（ln/jo/pS 同作用域；求值期只定义函数/挂 window/注入 <style>）
    p.insert_before('fb100-api-ui-block', A_Q0, block + '\n', expect=1,
                    note='FB100 反馈 API 桥 + 自包含模态（复用 ln/jo/pS，window 暴露）')
    # E2 顶栏「反馈」：hidden md:flex 工具条首位 =「角色」按钮左侧紧邻
    p.replace('fb100-header-btn', A_HDR, N_HDR, expect=1,
              note='顶栏「反馈」按钮（amber 高亮 + 红点角标，紧邻「角色」左侧）')
    # E3 移动抽屉「反馈」：列表「设置」项之前（与信箱同款图标，复用 window.YLFB_OPEN）
    p.replace('fb100-drawer-item', A_DW, N_DW, expect=1,
              note='移动 ☰ 抽屉「反馈」入口（设置项前；onClick→window 守卫调 YLFB_OPEN）')

    return gates()
