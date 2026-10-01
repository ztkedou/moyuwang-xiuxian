# -*- coding: utf-8 -*-
r"""
yl_toast083_ext.py — 0.8.3 客户端改造：打坐获得的「数值信息」从**日志**改为**toast 浮层**
（cli-toast）；0.8.7 T1 修订：①宿主改屏幕中间水平居中 ②顿悟还原「toast+日志」双写

================================================================================ 0.8.7 修订（T1，implToast，2026-09-29）
① 宿主定位：`position:fixed;top:148px;right:16px;` → `position:fixed;top:148px;left:50%;
   transform:translateX(-50%);`，行对齐 `align-items:flex-end` → `center`（cssText 单点改）。
② 顿悟分支（A1）：REPL_SPECIAL 由只 toast 反转为「toast + `c(x,"special")` 日志」双写；
   反转 0.8.3 门禁「打坐·顿悟不再写日志」（`,c(x,"special")}` 计数 0→1）。普通增益（A2/B/C）不动。
③ 服务端：无。纯客户端，无 API 面变更。

★ 0.8.7 门禁计数清单（供接线人录入 dryrun_087；其余门禁沿用本文件 _gates() 动态产出）：
   `position:fixed;top:148px;left:50%;transform:translateX(-50%);z-index:2147482000;`  ==1
   `flex-direction:column;align-items:center;gap:8px;`                                 ==1
   `top:148px;right:16px`                                                              ==0
   `align-items:flex-end`                                                              ==0
   `,c(x,"special")}`                                                                  ==1 （0.8.3 为 0，本轮反转）
   `,YlxwToast(x,"special","md-exp",4000),c(x,"special")}else`                         ==1
   fun086 F1 串零回归：本模块 5 个补丁点均在打坐域（RS 组件 @~1277508），与
   fun086 F1 锚 `title:"使用灵石加速生长",…`（@~1361456）零交集（implToast 交付批已
   实测：本模块 apply 后 F1_ANCHOR 在产物中仍 count==1、F1_REPL 仍 0，由 fun086 自身
   门禁「F1·加速按钮带费用/旧无费用按钮已清零」继续把关）。
   ⚠ localtest/t_toast083.py 是 0.8.3 批的冻结自测，其硬编码期望（顿悟日志 0、右贴边定位）
   在 0.8.7 后已过时，勿再当 0.8.7 门禁跑；0.8.7 权威门禁 = 本文件 _gates()。

================================================================================ 用户诉求
「打坐获得的数值信息不写入日志中，改成那种 toast 的样式」
—— 即：日志面板（可滚动历史，`logs` 数组）里不再刷屏打坐的 +修为 / +气血 / +灵石；
   改成短暂出现、自动消失、不打断操作的非阻塞浮层。

================================================================================ 侦察复核（cli-toast 独立复核，非转述）
【1】打坐产出写日志的位置：组件 `RS` 的 `handleMeditate`
     `function RS(t){return Be(a=>a.player),Be(a=>a.setPlayer),Be(a=>a.addLog),{handleMeditate:O.useCallback(()=>{...`
     本作用域内 `c` = `Be.getState().addLog`。该路径上共 **4 处** addLog 调用，分属 3 个日志点：
       (a) 主产出 顿悟分支：`c(x,"special")`      文案 `✨ 你突然顿悟，灵台清明，对大道有了更深的理解…！(+N 修为)`
       (b) 主产出 常规分支：`c(x,"gain")`         文案 `你潜心感悟大道…。(+N 修为)`
       (c) 回血：`const I=Be.getState().addLog;I(\`💚 打坐加速回血，恢复 N 点气血（X倍速度）\`,"gain")`
       (d) 灵石：`const I=Be.getState().addLog;I(\`💰 打坐时获得了 N 灵石\`,"gain")`
     另有 1 处**成就** addLog（`🎉 达成成就：【…】！`）—— 属一次性成就通知，**不在**本次改动范围。
     自动打坐（autoMeditate）也走同一函数（`Zt.current.handleMeditate()` @bundle 1277508），故改此处即全覆盖。

【2】修正 lead 侦察的一处遗漏：bundle 里**存在**非阻塞浮层通知，只是不叫 toast。
     组件 `e1({log:t})`（bundle @780538）渲染的就是一个 toast：
       `div.fixed.top-20.right-4.z-[70].pointer-events-none.animate-fade-in` +
       按 `type` 配色（gain=emerald-900/90+emerald-100、special=amber-900/90+amber-100、
       danger=red-900/90、normal=ink-800/90），`border-l-4` 左侧色条。
     其数据源是**单槽**瞬态状态 `itemActionLog`（`Gw()` = `Pw(3000)`：set 后 3s 自动置 null），
     由**物品相关操作**（获得/购买等）调用 `setItemActionLog` 写入。
     ⇒ 结论：它是「物品动作 toast」，**不是** addLog 的伴生 toast；`addLog` 只写 `logs` 数组。
       所以「打坐只出 toast 不进日志」确实需要新通道，lead 的判断成立。

     为什么不复用它（`itemActionLog` / `e1`）：
       ① **单槽**：打坐一次可能同时产出 3 条（修为 + 回血 + 灵石），单槽会互相覆盖，只剩最后一条。
       ② 语义已归属物品动作，借用会与其冲突（且 3s 自动清除的定时器只挂在组件内部 setter 上，
          直接写 store 会导致 toast 永不消失）。
       ③ `e1` 是 React 组件，改它要动 React 树；而本模块契约要求「纯 vanilla JS，不碰 React 树」。
     ⇒ 本模块自建 vanilla 宿主，但**配色/位置/圆角/左侧色条完全对齐 `e1`**，视觉语言保持一致。

================================================================================ 本次改动（4 处 addLog → toast，共 4 个调用点）
  A1 顿悟分支   `,c(x,"special")}else`            → `,YlxwToast(x,"special","md-exp",4000)}else`
                0.8.3 修订：**不再双写**，顿悟也只弹 toast（用户原话「打坐获得的数值信息不写入日志中」）。
                0.8.7 T1 再修订：**恢复双写**（toast + 日志），见文首 0.8.7 修订节。
  A2 常规分支   `,c(x,"gain");l(`                 → `,YlxwToast(x,"gain","md-exp",2400);l(`   （只 toast）
  B  回血       `const I=…addLog;I(\`💚 …\`,"gain")` → `YlxwToast(\`💚 …\`,"gain","md-hp",2400)`    （只 toast）
  C  灵石       `const I=…addLog;I(\`💰 …\`,"gain")` → `YlxwToast(\`💰 …\`,"gain","md-stone",2400)` （只 toast）

================================================================================ 同类合并（0.8.3 核心修订）
  打坐是自动循环，约 1 次/秒，每次产出 1~3 条数值。若每条都新建节点，2400ms 驻留下屏幕上会长期
  挂着 3~5 条 toast 不断生灭，比日志更吵。用户明确选择「同类合并、原地刷新」，于是：
    · YlxwToast(msg, kind, key, holdMs) 新增 key / holdMs 两个可选参数（旧调用零改动仍可用）。
    · key 为空/未传 ⇒ 老行为（新建 append）。
    · key 非空 ⇒ 宿主内按 data-ylxw-toast-key 找**存活**同 key 节点：
        找到 ⇒ 原地改 textContent + 按 kind 重刷 background/color/border-left-color + 重置 hold 计时器；
        找不到 ⇒ 新建并打上该 key 属性。
    · 节点淡出移除前先清掉自己的 timer，杜绝「更新已移除节点」。
    · A1/A2 共用 key "md-exp"，所以顿悟会把那一行**原地**刷成 special（琥珀）配色。
  净效果：打坐期间屏幕上稳定只有 1~3 行（修为 / 气血 / 灵石），数值原地跳动；停手约 2.4s 后逐条消失。

================================================================================ 宿主位置（0.8.3 修订 → 0.8.7 T1 再修订）
  游戏已有的物品动作 toast 组件 `e1` 坐标是 top:80px;right:16px（tailwind `top-20 right-4`）。
  0.8.3：本宿主下移到 top:148px（e1 正下方）避免重叠，右贴边 right:16px。
  0.8.7 T1：改**屏幕中间水平居中**——top:148px 不变（仍低于 e1），`right:16px` →
  `left:50% + translateX(-50%)`，行对齐 flex-end → center。

================================================================================ 契约
  INJECT_JS : str                     纯 ASCII（中文/emoji 一律 \uXXXX），经 zh() 后逐字节不变
  apply(p, ctx) -> gates              p = yl_patch.Patcher；ctx = {'zh': zh, 'base_text': str}
  gates : list[(name, needle, expected, op, note)]   op ∈ {'==','>=','<='}

  禁用模式自检（本模块 INJECT_JS 内为 0，见 localtest/t_toast083.py）：
      iframe / postMessage / XMLHttpRequest / auth_token / X-YL-

================================================================================ 依赖与顺序
  无前置依赖（不读任何其它 v28 模块注入的锚点）。
  可置于 V28_MODULES 任意位置；若与 numbal 的「恒为最后」冲突，请排在 numbal **之前**。

================================================================================ 锚点实测
  基线 build/assets/index-v26m-20260927.js 与现产物 build/assets/index-v28-20260928.js
  上，下列 5 个锚点 count **均为 1**（见 localtest/t_toast083.py 输出）。
"""

# --------------------------------------------------------------------------- 锚点常量
# 说明：锚点必须匹配 **bundle 原文**（raw UTF-8 中文），**不走 zh()**；
#       只有注入块 INJECT_JS 才走 zh()。

# —— 注入锚：`RS` 为 bundle 顶层函数声明，其前后即模块作用域（YlxwToast 定义于此）——
ANCHOR_RS = (
    'function RS(t){return Be(a=>a.player),Be(a=>a.setPlayer),Be(a=>a.addLog),'
    '{handleMeditate:'
)

# —— A1 顿悟分支（含 }else 保证唯一；实测 count==1）——
# 0.8.3 修订：顿悟只弹 toast、不写日志。
# 0.8.7 修订（T1②）：顿悟/爆发特殊事件还原「toast + 日志」**双写**——toast 供瞬时反馈
#   （special 琥珀配色，key=md-exp 与常规行原地合并），日志栏恢复可回溯记录；
#   逗号表达式的求值顺序保证先弹 toast 再写日志，`c` 在该作用域即 addLog（原调用原样复活）。
#   普通增益（A2 感悟 / B 回血 / C 灵石）维持 0.8.3 只 toast 不动。
ANCHOR_SPECIAL = ',c(x,"special")}else'
REPL_SPECIAL = ',YlxwToast(x,"special","md-exp",4000),c(x,"special")}else'

# —— A2 常规感悟分支（实测 count==1）——
ANCHOR_GAIN = ',c(x,"gain");l('
REPL_GAIN = ',YlxwToast(x,"gain","md-exp",2400);l('

# —— B 回血（实测 count==1）——
ANCHOR_HP = (
    'const I=Be.getState().addLog;I(`\U0001F49A 打坐加速回血，恢复 ${N} 点气血（${_}倍速度）`,"gain")'
)
REPL_HP = 'YlxwToast(`\U0001F49A 打坐加速回血，恢复 ${N} 点气血（${_}倍速度）`,"gain","md-hp",2400)'

# —— C 灵石（实测 count==1）——
ANCHOR_STONE = (
    'const I=Be.getState().addLog;I(`\U0001F4B0 打坐时获得了 ${Math.max(1,q)*5} 灵石`,"gain")'
)
REPL_STONE = 'YlxwToast(`\U0001F4B0 打坐时获得了 ${Math.max(1,q)*5} 灵石`,"gain","md-stone",2400)'

# ★ 2026-09-30 约束权移交（R-024 / econ2，接线在本模块之后）：
#   econ2 把 toast 里的 `${Math.max(1,q)*5}` 换成 `${__ylsq}`（YlxwMedStone2 中转）。
#   `REPL_STONE` 必须保持**改前形态**（它是本模块的替换值，也是 econ2 的锚点），
#   故门禁断言改用下面这两个「最终形态」串，语义不变（仍是「灵石改走 toast」+「文案在位」）。
REPL_STONE_FINAL = 'YlxwToast(`\U0001F4B0 打坐时获得了 ${__ylsq} 灵石`,"gain","md-stone",2400)'
BASELINE_STONE_TEXT_FINAL = '打坐时获得了 ${__ylsq} 灵石'

# —— 反例/基线锚（防误伤）——
BASELINE_ACH = '\U0001F389 达成成就：【${$.name}】！'
BASELINE_HP_LOGCALL = 'const I=Be.getState().addLog;I(`'
BASELINE_MEDITATE = 'handleMeditate:O.useCallback(()=>{const a=Be.getState().player'


# --------------------------------------------------------------------------- 注入块（纯 ASCII）
INJECT_JS = r'''
/* ===== yl-0.8.3 cli-toast: meditation numbers -> non-blocking toast layer ===== */

var YLXW_TOAST_HOST_ID = "ylxw-toast-host";
var YLXW_TOAST_MAX = 5;
var YLXW_TOAST_HOLD_MS = 2400;
var YLXW_TOAST_FADE_MS = 280;
var YLXW_TOAST_MAX_CHARS = 300;
/* Same-key coalescing marker. Two calls carrying one key share a single node. */
var YLXW_TOAST_KEY_ATTR = "data-ylxw-toast-key";

/* kind -> {bg,fg,bd}. Palette copied from the existing floating notice (e1/itemActionLog)
   so the two share one visual language. Inline styles only -- no new CSS classes. */
function YlxwToastStyle(kind) {
  try {
    if (kind === "gain") return { bg: "rgba(0,78,59,0.9)", fg: "#d1fae5", bd: "#5c946e" };
    if (kind === "special") return { bg: "rgba(123,51,6,0.9)", fg: "#fef3c7", bd: "#cba135" };
    if (kind === "danger") return { bg: "rgba(127,29,29,0.9)", fg: "#fee2e2", bd: "#8a2c2c" };
    return { bg: "rgba(26,27,30,0.9)", fg: "#d6d3d1", bd: "#57534e" };
  } catch (e) {
    return { bg: "rgba(26,27,30,0.9)", fg: "#d6d3d1", bd: "#57534e" };
  }
}

/* Lazily create / reuse the host container.
   0.8.7 (T1): horizontally centered on screen -- fixed at top:148px (still one row below
   the item-action notice e1 at top:80px, so the two layers never overlap vertically) with
   left:50% + translateX(-50%); rows are center-aligned instead of right-aligned.
   pointer-events:none => never blocks clicks. */
function YlxwToastHost() {
  try {
    if (typeof document === "undefined" || !document.body) return null;
    var h = document.getElementById(YLXW_TOAST_HOST_ID);
    if (h && h.isConnected) return h;
    if (h && h.parentNode) { try { h.parentNode.removeChild(h); } catch (e) {} }
    h = document.createElement("div");
    h.id = YLXW_TOAST_HOST_ID;
    h.style.cssText = "position:fixed;top:148px;left:50%;transform:translateX(-50%);z-index:2147482000;"
      + "display:flex;flex-direction:column;align-items:center;gap:8px;"
      + "pointer-events:none;max-width:min(92vw,420px);";
    document.body.appendChild(h);
    return h;
  } catch (e) { return null; }
}

/* Cancel the pending hold timer carried by a node (called before any detach). */
function YlxwToastClearTimer(el) {
  try {
    if (!el) return;
    if (el.__ylxwHoldTimer !== null && el.__ylxwHoldTimer !== undefined) {
      try { clearTimeout(el.__ylxwHoldTimer); } catch (e) {}
      el.__ylxwHoldTimer = null;
    }
  } catch (e) {}
}

/* Drop the oldest entries (head of the list) when over the cap. */
function YlxwToastTrim(host) {
  try {
    while (host.childNodes && host.childNodes.length > YLXW_TOAST_MAX) {
      var old = host.firstChild;
      if (!old) break;
      YlxwToastClearTimer(old);
      old.__ylxwDropped = true;
      host.removeChild(old);
    }
  } catch (e) {}
}

/* Find the still-alive node carrying this key inside the host.
   A node already handed to YlxwToastDrop is no longer alive -- a later call with the
   same key must build a fresh node instead of resurrecting a half-faded one. */
function YlxwToastFind(host, key) {
  try {
    var kids = host.childNodes || [];
    for (var i = 0; i < kids.length; i++) {
      var k = kids[i];
      if (!k || k.__ylxwDropped) continue;
      if (!k.parentNode) continue;
      var got = null;
      try { got = k.getAttribute ? k.getAttribute(YLXW_TOAST_KEY_ATTR) : null; } catch (e) { got = null; }
      if (got === null || got === undefined) got = k.__ylxwKey;
      if (got !== null && got !== undefined && String(got) === String(key)) return k;
    }
  } catch (e) {}
  return null;
}

/* Fade out, then detach. The node's own hold timer is cleared first so a stale timer
   can never fire against an already-detached node. */
function YlxwToastDrop(el) {
  try {
    if (!el) return;
    YlxwToastClearTimer(el);
    el.__ylxwDropped = true;
    el.style.opacity = "0";
    el.style.transform = "translateY(-6px)";
    setTimeout(function () {
      try { if (el.parentNode) el.parentNode.removeChild(el); } catch (e) {}
    }, YLXW_TOAST_FADE_MS);
  } catch (e) {}
}

/* Public entry: YlxwToast -- args (message, kind, key, holdMs).
   kind = gain | special | danger | info(default). holdMs defaults to 2400.
   key: when empty/absent the call always appends a brand-new row (legacy behaviour).
   When a non-empty key is given and a live row already carries that key, the row is
   updated in place -- text, palette and hold timer are all refreshed, no node is added.
   Never throws; a bad argument must not disturb the game loop. */
function YlxwToast(msg, kind, key, holdMs) {
  try {
    if (typeof document === "undefined" || !document.body) return;
    if (msg === null || msg === undefined) return;
    var text = String(msg);
    if (!text) return;
    if (text.length > YLXW_TOAST_MAX_CHARS) text = text.slice(0, YLXW_TOAST_MAX_CHARS) + "\u2026";
    var host = YlxwToastHost();
    if (!host) return;
    var c = YlxwToastStyle(kind === null || kind === undefined ? "info" : String(kind));
    var hasKey = !(key === null || key === undefined || key === "");
    var kstr = hasKey ? String(key) : "";
    var hold = (holdMs === null || holdMs === undefined || !(holdMs > 0))
      ? YLXW_TOAST_HOLD_MS : holdMs;

    /* --- same key still on screen: refresh in place --- */
    var live = hasKey ? YlxwToastFind(host, kstr) : null;
    if (live) {
      live.textContent = text;
      try {
        live.style.background = c.bg;
        live.style.color = c.fg;
        live.style.borderLeftColor = c.bd;
      } catch (e) {}
      YlxwToastClearTimer(live);
      live.__ylxwHoldTimer = setTimeout(function () { YlxwToastDrop(live); }, hold);
      return;
    }

    /* --- otherwise: build a fresh row --- */
    var el = document.createElement("div");
    el.style.cssText = "box-sizing:border-box;max-width:100%;padding:8px 12px;"
      + "border-radius:8px;border-left:3px solid " + c.bd + ";background:" + c.bg + ";color:" + c.fg + ";"
      + "font-family:Noto Serif SC,serif;font-size:13px;line-height:1.5;"
      + "box-shadow:0 6px 20px rgba(0,0,0,0.45);word-break:break-word;white-space:normal;"
      + "pointer-events:none;opacity:0;transform:translateY(10px);"
      + "transition:opacity " + YLXW_TOAST_FADE_MS + "ms ease,transform " + YLXW_TOAST_FADE_MS + "ms ease;";
    el.textContent = text;
    if (hasKey) {
      el.__ylxwKey = kstr;
      try { if (el.setAttribute) el.setAttribute(YLXW_TOAST_KEY_ATTR, kstr); } catch (e) {}
    }
    host.appendChild(el);
    YlxwToastTrim(host);
    var raf = function (fn) {
      try {
        if (typeof requestAnimationFrame === "function") return requestAnimationFrame(fn);
      } catch (e) {}
      return setTimeout(fn, 16);
    };
    raf(function () {
      try { el.style.opacity = "1"; el.style.transform = "translateY(0)"; } catch (e) {}
    });
    el.__ylxwHoldTimer = setTimeout(function () { YlxwToastDrop(el); }, hold);
  } catch (e) {}
}
/* ===== end yl-0.8.3 cli-toast ===== */
'''


# --------------------------------------------------------------------------- 门禁
def _gates():
    return [
        # ---- 注入块：toast 机制 ----
        ('toast·宿主工厂',            'function YlxwToastHost()',            1, '==', ''),
        ('toast·配色表',              'function YlxwToastStyle(kind)',       1, '==', ''),
        ('toast·淡出移除',            'function YlxwToastDrop(el)',          1, '==', ''),
        ('toast·计时器清理',          'function YlxwToastClearTimer(el)',    1, '==', ''),
        ('toast·同 key 查找',         'function YlxwToastFind(host, key)',   1, '==', ''),
        ('toast·主入口新签名',        'function YlxwToast(msg, kind, key, holdMs)', 1, '==', ''),
        ('toast·容器 id',             'var YLXW_TOAST_HOST_ID = "ylxw-toast-host";', 1, '==', ''),
        ('toast·上限 5 条',           'var YLXW_TOAST_MAX = 5;',             1, '==', ''),
        ('toast·驻留 2400ms',         'var YLXW_TOAST_HOLD_MS = 2400;',      1, '==', ''),
        ('toast·pointer-events:none', 'pointer-events:none;max-width:min(92vw,420px);', 1, '==', '不挡点击'),
        ('toast·定义+调用共 8 处',    'YlxwToast(',                          8, '==', '定义 1 + 打坐 4 + 0.8.7 T5 活动中心 3（只调用不改宿主）'),
        ('toast·未重复注入',          'var YLXW_TOAST_HOST_ID =',            1, '==', ''),
        # ---- 宿主位置：0.8.7 T1 改屏幕中间水平居中（0.8.3 右贴边形态作废）----
        ('toast·宿主水平居中',        'position:fixed;top:148px;left:50%;transform:translateX(-50%);z-index:2147482000;', 1, '==', '0.8.7 T1 居中'),
        ('toast·行居中对齐',          'flex-direction:column;align-items:center;gap:8px;', 1, '==', '行居中非右对齐'),
        ('toast·旧右贴边定位已移除',  'top:148px;right:16px',                0, '==', '0.8.3 形态作废'),
        ('toast·旧 flex-end 已移除',  'align-items:flex-end',                0, '==', '0.8.3 形态作废'),
        ('toast·宿主不再用 top:80px', 'top:80px;right:16px',                 0, '==', '原与 e1 重叠'),
        # ---- 同 key 合并机制 ----
        ('toast·data-key 属性常量',   'var YLXW_TOAST_KEY_ATTR = "data-ylxw-toast-key";', 1, '==', ''),
        ('toast·data-key 机制 1 处',  'data-ylxw-toast-key',                 1, '==', '字面量仅常量定义'),
        ('toast·原地重刷配色',        'live.style.borderLeftColor = c.bd;',   1, '==', 'special 可原地变琥珀'),
        ('toast·原地重置计时器',      'YlxwToastClearTimer(live);',           1, '==', ''),
        ('toast·已移除节点不复用',    'if (!k || k.__ylxwDropped) continue;',  1, '==', ''),
        # ---- A1 顿悟分支：0.8.7 T1 反转 0.8.3 —— toast + 日志双写（普通增益 A2/B/C 仍只 toast）----
        ('打坐·顿悟只弹 toast',       REPL_SPECIAL,                          1, '==', 'special / key=md-exp / 4000ms'),
        ('打坐·顿悟还原写日志',       ',c(x,"special")}',                    1, '==', '0.8.7 反转 0.8.3：0→1'),
        # ---- A2 常规感悟分支：只 toast ----
        ('打坐·感悟改 toast',         REPL_GAIN,                             1, '==', ''),
        ('打坐·感悟原调用已移除',     ',c(x,"gain");l(',                     0, '==', '必须为 0'),
        # ---- B 回血 / C 灵石：只 toast ----
        ('打坐·回血改 toast',         REPL_HP,                               1, '==', ''),
        ('打坐·灵石改 toast（R-024 已接管）', REPL_STONE_FINAL,                  1, '==', 'econ2 改 __ylsq 中转'),
        ('打坐·原 addLog 调用已清空', BASELINE_HP_LOGCALL,                   0, '==', '原为 2（回血+灵石）'),
        # ---- key 字面量计数 ----
        ('key·md-exp 共 2 处',        '"md-exp"',                            2, '==', '顿悟 + 常规共用，可原地刷色'),
        ('key·md-hp 共 1 处',         '"md-hp"',                             1, '==', ''),
        ('key·md-stone 共 1 处',      '"md-stone"',                          1, '==', ''),
        # ---- 基线未被破坏 ----
        ('基线·RS 组件仍在',          ANCHOR_RS,                             1, '==', ''),
        ('基线·handleMeditate 仍在',  BASELINE_MEDITATE,                     1, '==', ''),
        ('基线·成就日志未动',         BASELINE_ACH,                          1, '==', '一次性成就，不属数值刷屏'),
        ('基线·顿悟文案未动',         '✨ 你突然顿悟，灵台清明',              1, '==', ''),
        ('基线·回血文案未动',         '打坐加速回血，恢复 ${N} 点气血',        1, '==', ''),
        ('基线·灵石文案（R-024 已接管）', BASELINE_STONE_TEXT_FINAL,            1, '==', 'econ2 改 __ylsq 中转'),
        ('基线·历练 addLog 未波及',   '你在历练途中没有遇到什么特别的事情。',  3, '==', 'adventure 路径原文案，改动前后恒为 3'),
    ]


def apply(p, ctx):
    """就地改造 bundle 文本，返回门禁列表。ctx = {'zh': zh, 'base_text': str}。"""
    zh = ctx['zh']

    # 0) 注入 toast 机制（模块作用域；YlxwToast 对 RS 可见）
    p.insert_before(
        'toast083-helper',
        ANCHOR_RS,
        zh(INJECT_JS) + '\n',
        expect=1,
        note='注入 YlxwToast / 宿主容器 / 配色 / 淡出（单块，纯 vanilla，不碰 React 树）',
    )

    # 1) A1 顿悟分支：只 toast，不再写日志（与常规感悟共用 key md-exp，可原地刷色）
    p.replace(
        'toast083-meditate-special',
        ANCHOR_SPECIAL,
        REPL_SPECIAL,
        expect=1,
        note='顿悟改为只弹 toast(special,key=md-exp,4000ms)，日志侧不再写入',
    )

    # 2) A2 常规感悟分支：只 toast，不再写日志
    p.replace(
        'toast083-meditate-gain',
        ANCHOR_GAIN,
        REPL_GAIN,
        expect=1,
        note='打坐常规 +修为 改为 toast(gain,key=md-exp,2400ms)，不再刷日志',
    )

    # 3) B 回血：只 toast
    p.replace(
        'toast083-meditate-hp',
        ANCHOR_HP,
        REPL_HP,
        expect=1,
        note='打坐回血 改为 toast(gain,key=md-hp,2400ms)',
    )

    # 4) C 灵石：只 toast
    p.replace(
        'toast083-meditate-stone',
        ANCHOR_STONE,
        REPL_STONE,
        expect=1,
        note='打坐灵石 改为 toast(gain,key=md-stone,2400ms)',
    )

    return _gates()
