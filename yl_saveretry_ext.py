# -*- coding: utf-8 -*-
r"""
yl_saveretry_ext.py -- 云端存档 pushSave 的 5xx / 网络层退避重试 + 文案分级 (v27)

缺陷（用户反馈 #10「云端存档保存失败，请检查网络」）：
    部署重启 yl-server 的 1~2 秒窗口内，正在上传存档的客户端会拿到 nginx 502。
    原 pushSave 只对 409 有重试语义（__ylConflict 标志由调用方处理），
    5xx / 网络层异常一律直接失败，并且文案把「服务端在更新」误导成「你的网络有问题」。

本模块做两件事，全部限定在 pushSave / fetchSave 两个函数体内：
    1. 注入通用退避重试助手 YLSaveRetryPush(payload)
       - 可重试：HTTP 502 / 503 / 504 / 429；网络层异常（fetch 抛 TypeError 等，AbortError 除外）
       - 不重试：400 / 401 / 403 / 404 / 409（401 由 Xc 既有 refresh + logout 流程处理；
         409 仍走既有 __ylConflict 分支，语义一字不动）
       - 退避：3 次重试，间隔 800 / 2000 / 4000 ms，每次 ±25% 随机抖动
       - 并发保护：模块级 Promise 串行闸 YLSaveGate，同一时刻只允许一个 pushSave 序列
         （含退避等待）在跑，后续调用排队，杜绝并发重复上传
    2. 文案分级
       - 502/503/504 且重试仍失败 → 「服务器正在更新，请稍候片刻后重试」
       - 网络层不可达且重试仍失败 → 「网络连接异常，请检查网络后重试」
       - 其它 5xx / 4xx → 「云端存档保存失败，请稍后重试」（删掉误导的「请检查网络」）
       - 重试期间一次性提示「服务器正在更新，已自动重试…」（复用既有 Je 通知）

契约（本文件对外只导出这两个符号）：
    INJECT_JS : str        注入 JS 块（含中文，由构建侧统一 zh() 转义）
    apply(p, ctx) -> gates
        p   : yl_patch.Patcher
        ctx : {'zh': zh 函数, 'base_text': str}
        gates: list[(name, needle, expected, op, note)]，op ∈ {'==','>=','<='}

锚点实测（基线 build/assets/index-v26m-20260927.js，1419571 chars）：
    _ANCHOR_PN      'const Pn={async fetchSave(){const t=await Xc('            count=1
    _OLD_REQ        'const r=await Xc(`${ln}/save`,{method:"POST",...'          count=1
    _OLD_PUSH_ERR   'throw new Error("云端存档保存失败，请检查网络或稍后重试")'      count=1
    _OLD_FETCH_ERR  'if(!t.ok)throw new Error("拉取云端存档失败，请检查网络或稍后重试")' count=1
    'YLSaveRetry' 在基线 count=0（无标识符碰撞）
"""

# --------------------------------------------------------------------------- 锚点
# 全部为纯 ASCII（除两处错误文案外），且实测 count==1。
_ANCHOR_PN = 'const Pn={async fetchSave(){const t=await Xc('

_OLD_REQ = ('const r=await Xc(`${ln}/save`,{method:"POST",'
            'headers:{"Content-Type":"application/json"},body:JSON.stringify(t)});if(!r.ok){')
_NEW_REQ = 'const r=await YLSaveRetryPush(t);if(!r.ok){'

_OLD_PUSH_ERR = 'throw new Error("云端存档保存失败，请检查网络或稍后重试")'
_NEW_PUSH_ERR = 'throw YLSaveHttpError(r.status)'

_OLD_FETCH_ERR = 'if(!t.ok)throw new Error("拉取云端存档失败，请检查网络或稍后重试")'
_NEW_FETCH_ERR = 'if(!t.ok)throw YLSaveHttpError(t.status,"拉取云端存档失败，请稍后重试")'

# --------------------------------------------------------------------------- 注入块
INJECT_JS = r'''
/* == YL_SAVE_RETRY_V27 (5xx/network backoff retry + graded messaging) == */
var YLSaveGate = Promise.resolve();
// v28 补：服务端**自身的写档失败**返回的是 500（index.ts:1841 'Error updating save' /
// :1864 'Error creating save'），不是 502/503/504 —— 只列 502/503/504 会让真正的
// 写档失败只尝试 1 次就报「云端存档保存失败」（用户反馈 #10 的残留缺口）。
// 故改为全 5xx 可重试（推送带 base revision，幂等，重试安全）+ 429。
function YLSaveRetryableStatus(s) { return (s >= 500 && s <= 599) || s === 429; }
function YLSaveNetErr(e) {
  try {
    if (!e) return !1;
    if (e.name === 'AbortError') return !1;
    if (e.name === 'TypeError') return !0;
    var m = String((e && e.message) || e);
    return /Failed to fetch|NetworkError|Load failed|network error|ERR_NETWORK|ERR_INTERNET|ERR_CONNECTION/i.test(m);
  } catch (x) { return !1; }
}
/* 服务端 503 时会带 Retry-After（秒数或 HTTP-date）。尊重它：取 max(退避, 建议值)，
   上限 30s，避免在服务端明确说「别急着来」时反复打扰。 */
function YLSaveRetryAfterMs(r) {
  try {
    var v = r && r.headers && r.headers.get && r.headers.get('retry-after');
    if (!v) return null;
    var n = parseFloat(v);
    if (isFinite(n) && n >= 0) return Math.round(n * 1000);
    var d = Date.parse(v);
    if (isFinite(d)) { var dd = d - Date.now(); return dd > 0 ? dd : null; }
  } catch (e) {}
  return null;
}
function YLSaveBackoff(i, hintMs) {
  var t = [800, 2000, 4000][i];
  if (t == null) t = 4000;
  var ms = Math.round(t * (0.75 + Math.random() * 0.5));
  if (typeof hintMs === 'number' && isFinite(hintMs) && hintMs > ms) ms = Math.min(hintMs, 30000);
  return new Promise(function (r) { setTimeout(r, ms); });
}
function YLSaveNotice(msg) {
  try { if (typeof Je === 'function') { Je(msg); return; } } catch (e) {}
  try { console.warn('[YLSaveRetry] ' + msg); } catch (e) {}
}
function YLSaveHttpError(s, alt) {
  // 文案分级：502/503/504 = nginx 重启窗口（「正在更新」）；其它 5xx = 服务端自身故障（写档失败等）
  var msg = (s === 502 || s === 503 || s === 504)
    ? '服务器正在更新，请稍候片刻后重试'
    : ((s >= 500 && s <= 599) ? '服务器暂时无法保存，请稍后重试'
                              : (alt || '云端存档保存失败，请稍后重试'));
  var e = new Error(msg);
  e.__ylSaveStatus = s;
  return e;
}
function YLSaveFetchError() {
  var e = new Error('网络连接异常，请检查网络后重试');
  e.__ylSaveNet = !0;
  return e;
}
function YLSaveAttempt(t) {
  var maxRetry = 3, i = 0, noticed = !1;
  var once = function () {
    return Xc(`${ln}/save`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(t) }).then(function (r) {
      if (r && !r.ok && YLSaveRetryableStatus(r.status) && i < maxRetry) {
        if (!noticed) {
          noticed = !0;
          YLSaveNotice((r.status === 502 || r.status === 503 || r.status === 504)
            ? '服务器正在更新，已自动重试…' : '服务器繁忙，已自动重试…');
        }
        return YLSaveBackoff(i++, YLSaveRetryAfterMs(r)).then(once);
      }
      return r;
    }, function (e) {
      if (YLSaveNetErr(e) && i < maxRetry) { return YLSaveBackoff(i++).then(once); }
      if (YLSaveNetErr(e)) throw YLSaveFetchError();
      throw e;
    });
  };
  return once();
}
/* 串行闸：同一时刻只允许一个 pushSave 序列（含退避等待）在跑 */
function YLSaveRetryPush(t) {
  var run = function () { return YLSaveAttempt(t); };
  var next = YLSaveGate.then(run, run);
  YLSaveGate = next.then(function () {}, function () {});
  return next;
}
/* == end YL_SAVE_RETRY_V27 == */
'''


# --------------------------------------------------------------------------- 门禁
def _gates():
    return [
        # ---- 助手注入 ----
        ('retry 助手定义',              'function YLSaveRetryPush(',        1, '==', ''),
        ('retry 助手·退避序列',          'YLSaveBackoff',                    3, '>=', '定义+调用'),
        ('retry 助手·可重试状态码',       'function YLSaveRetryableStatus(',  1, '==', ''),
        # v28 补：服务端自身写档失败返回 500，只列 502/503/504 会漏掉它
        ('retry 助手·全 5xx 可重试',      'function YLSaveRetryableStatus(s) { return (s >= 500 && s <= 599) || s === 429; }', 1, '==', '含服务端 500 写档失败'),
        ('retry 助手·旧窄口径已移除',      'return s === 502 || s === 503 || s === 504 || s === 429;', 0, '==', '必须为 0'),
        ('retry 助手·遵循 Retry-After',    'YLSaveBackoff(i++, YLSaveRetryAfterMs(r))', 1, '==', '503 带 Retry-After 时取 max(退避, 建议值)'),
        ('retry 助手·串行闸',            'var YLSaveGate = Promise.resolve();', 1, '==', ''),
        # ---- pushSave 接线 ----
        ('pushSave 已接入重试',          _NEW_REQ,                           1, '==', ''),
        ('pushSave 旧请求行已移除',       'const r=await Xc(`${ln}/save`,{method:"POST"', 0, '==', '必须为 0'),
        ('pushSave 5xx 分级文案',        _NEW_PUSH_ERR,                      1, '==', ''),
        ('旧误导文案(保存)已移除',        '云端存档保存失败，请检查网络或稍后重试', 0, '==', '必须为 0'),
        # ---- fetchSave 文案分级 ----
        ('fetchSave 分级文案',           _NEW_FETCH_ERR,                     1, '==', ''),
        ('旧误导文案(拉取)已移除',        '拉取云端存档失败，请检查网络或稍后重试', 0, '==', '必须为 0'),
        # ---- 409 分支三处原文案（防误伤）----
        ('409·session_superseded',       'ylCf.error==="session_superseded"', 1, '==', ''),
        ('409·setBlocked+原文案',        'YLSync.setBlocked(!0);throw new Error("此账号已在其他设备打开")', 1, '==', ''),
        ('409·gm_revision 回写',         'setAppliedGmRevision(ylCf.gm_revision)', 1, '==', ''),
        ('409·__ylConflict 标志',        'ylCe.__ylConflict=!0',             1, '==', ''),
        ('409·冲突文案',                 '存档版本冲突，正在重试',             1, '==', ''),
        # ---- 成功路径不能丢 ----
        ('成功·setAppliedGmRevision',    'setAppliedGmRevision(ylPs.gm_revision)', 1, '==', ''),
        ('成功·YLSettledExp',            'YLSettledExp(ylPs)',               1, '==', ''),
        # ---- 幂等/无重复 ----
        ('helper 未重复注入',            'function YLSaveAttempt(',          1, '==', ''),
    ]


def apply(p, ctx):
    """就地改造 bundle 文本，返回门禁列表。ctx = {'zh': zh, 'base_text': str}。"""
    zh = ctx['zh']
    block = zh(INJECT_JS)

    # 1) 助手注入：放在 `const Pn={...}` 之前（同一模块作用域，Xc / ln / Je 均可见）
    p.insert_before(
        'saveretry-helper',
        _ANCHOR_PN,
        block + '\n',
        expect=1,
        note='注入 YLSaveRetryPush / 退避 / 文案分级助手',
    )

    # 2) pushSave：请求行换成重试助手（409 分支体一字不动）
    p.replace('saveretry-pushsave-req', _OLD_REQ, _NEW_REQ,
              expect=1, note='pushSave 请求走退避重试')

    # 3) pushSave：非 409 失败改走分级文案
    p.replace('saveretry-pushsave-err', _OLD_PUSH_ERR, _NEW_PUSH_ERR,
              expect=1, note='去掉「请检查网络」误导，按状态码分级')

    # 4) fetchSave：同分级文案
    p.replace('saveretry-fetchsave-err', _OLD_FETCH_ERR, _NEW_FETCH_ERR,
              expect=1, note='拉档失败同样分级，去误导')

    return _gates()
