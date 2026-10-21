// FB-100 语义真值表：把注入块从**产物**里切出来，在 Node 里直跑反馈提交状态机（仿 _r256_sem.js）。
// 不依赖浏览器：stub DOM/fetch/jo/ln/pS/Be/YlxwVersionGet/YlxwToast，验证：
//   校验(空/太短/太长/联系超长) / 冷却拦截 / 401 静默续期重试恰一次 / 409 与 500(400) 分支 / 成功后清空表单。
// 用法：node _fb100_sem.js <补丁后产物.js>
const fs = require('fs');
const vm = require('vm');
const path = process.argv[2];
if (!path) { console.error('usage: node _fb100_sem.js <patched.js>'); process.exit(2); }
const src = fs.readFileSync(path, 'utf8');

let fail = 0;
function chk(c, m) { if (!c) { fail++; console.log('  [FAIL] ' + m); } }
function ok(m) { console.log('  [ok] ' + m); }

// ---------- 从产物切出注入块（MARK → const Q0 锚点） ----------
function slice(startMark, endMark) {
  const i = src.indexOf(startMark);
  if (i < 0) throw new Error('missing start ' + startMark);
  const j = src.indexOf(endMark, i);
  if (j < 0) throw new Error('missing end ' + endMark);
  return src.slice(i, j);
}
const block = slice('/* == YL_FB100_V1', 'const Q0="/yl/api"');
console.log('=== 注入块 ===');
console.log('  BLOCK =', block.length, 'chars');

// ---------- 最小运行环境 ----------
let token = 'tok1';
function jo() { return token ? { Authorization: 'Bearer ' + token } : {}; }
let pSCalls = 0;
async function pS() { pSCalls++; token = 'tok2'; } // 模拟静默续期：续期后 jo() 读到新 token
let SCRIPT = [];                                   // fetch 脚本化应答队列
let fetchCalls = 0;
const reqs = [];
async function fetchStub(url, opt) {
  fetchCalls++;
  const s = SCRIPT.shift() || { status: 500, body: {} };
  reqs.push({ url, opt, body: JSON.parse(opt.body), headers: opt.headers });
  return { status: s.status, ok: s.status >= 200 && s.status < 300, json: async () => s.body };
}
const Be = { getState: () => ({ player: { realm: '炼气期一层' } }) };
function YlxwVersionGet() { return '9.9.9-sem'; }
const toastCalls = [];
function YlxwToast(msg, kind, key, holdMs) { toastCalls.push({ msg, kind, key, holdMs }); }

function mkEl(tag) {
  const el = {
    tagName: tag, id: '', className: '', textContent: '', value: '',
    maxLength: undefined, placeholder: '', disabled: false,
    style: { cssText: '' },
    children: [], parentNode: null, _h: {},
    appendChild(c) { el.children.push(c); c.parentNode = el; },
    removeChild(c) { const i = el.children.indexOf(c); if (i >= 0) el.children.splice(i, 1); c.parentNode = null; },
    addEventListener(t, fn) { (el._h[t] = el._h[t] || []).push(fn); },
    remove() { if (el.parentNode) el.parentNode.removeChild(el); },
  };
  return el;
}
const created = [];
const documentStub = {
  head: mkEl('head'), body: mkEl('body'),
  createElement: (t) => { const e = mkEl(t); created.push(e); return e; },
  getElementById: (id) => created.find((e) => e.id === id) || null,
};
const windowStub = {};
const navigatorStub = { userAgent: 'sem-ua' };

const ctx = { window: windowStub, document: documentStub, navigator: navigatorStub,
              fetch: fetchStub, jo, ln: '/yl/api', pS, Be, YlxwVersionGet, YlxwToast,
              console, setTimeout, clearTimeout, Date, Math, JSON, String, Number, Promise, Object, Array };
vm.runInNewContext(block, ctx, { filename: 'fb100block.js' });

async function main() {
  console.log('\n=== 0. 求值即就绪：window 导出 + 样式已注入 ===');
  chk(typeof windowStub.YLFB_SUBMIT === 'function', 'window.YLFB_SUBMIT 应为函数');
  chk(typeof windowStub.YLFB_SEND === 'function', 'window.YLFB_SEND 应为函数');
  chk(typeof windowStub.YLFB_OPEN === 'function', 'window.YLFB_OPEN 应为函数');
  chk(fetchCalls === 0 && pSCalls === 0, '求值期不得发请求/续期');
  const styleEl = documentStub.head.children.find((e) => e.id === 'ylfb-style');
  chk(!!styleEl, 'load 时应注入 <style id="ylfb-style">');
  chk(!!styleEl && styleEl.textContent.includes('.ylbar6{grid-template-columns:repeat(6,minmax(0,1fr))}'),
      '样式应含 6 列 .ylbar6 定义');
  ok('三个 window 导出 + 6 列样式就绪');

  // ---------- 1. 校验（全在冷却/网络之前，fetch 必须保持 0） ----------
  console.log('\n=== 1. 校验：空 / 太短 / 太长 / 联系方式超长 ===');
  const sendOnce = (kind, content, contact) => new Promise((res) => windowStub.YLFB_SEND(kind, content, contact, res));
  let r = await sendOnce('bug', '   ', '');
  chk(r && r.ok === false, '空内容应被拒');
  chk(/请填写反馈内容/.test(r.msg), '空内容文案（实际 ' + r.msg + '）');
  r = await sendOnce('bug', 'abc', '');
  chk(r && !r.ok && /太短/.test(r.msg), '太短应被拒（实际 ' + r.msg + '）');
  r = await sendOnce('bug', 'x'.repeat(2001), '');
  chk(r && !r.ok && /太长/.test(r.msg), '太长应被拒（实际 ' + r.msg + '）');
  r = await sendOnce('bug', '足够长的合法内容', 'c'.repeat(101));
  chk(r && !r.ok && /联系方式/.test(r.msg), '联系超长应被拒（实际 ' + r.msg + '）');
  chk(fetchCalls === 0, '校验阶段不得触网（实际 fetch=' + fetchCalls + '）');
  ok('四类校验全拦下，且 0 次网络调用');

  // ---------- 2. 409：显示服务端 error ----------
  console.log('\n=== 2. 409 → 显示服务端 error，不记冷却 ===');
  SCRIPT = [{ status: 409, body: { error: '提交太频繁，请稍后再试' } }];
  r = await sendOnce('bug', '这是一条会撞 409 的反馈内容', '');
  chk(fetchCalls === 1, '应恰好发 1 次请求（实际 ' + fetchCalls + '）');
  chk(pSCalls === 0, '409 不得触发续期');
  chk(r && !r.ok && r.status === 409, 'status 应为 409');
  chk(r.msg === '提交太频繁，请稍后再试', '应原样显示服务端 error（实际 ' + r.msg + '）');
  ok('409 分支 = 服务端 error 透出');

  // ---------- 3. 500 / 400 分支 ----------
  console.log('\n=== 3. 500 / 400 分支表现 ===');
  SCRIPT = [{ status: 500, body: {} }];
  r = await sendOnce('bug', '这是一条会撞 500 的反馈内容', '');
  chk(r && !r.ok && r.status === 500, 'status 应为 500');
  chk(/提交失败/.test(r.msg), '500 应给失败提示（实际 ' + r.msg + '）');
  SCRIPT = [{ status: 400, body: { error: '内容不合规' } }];
  r = await sendOnce('bug', '这是一条会撞 400 的反馈内容', '');
  chk(r && !r.ok && r.status === 400 && r.msg === '内容不合规', '400 应透出服务端 error（实际 ' + r.msg + '）');
  ok('500 兜底提示 / 400 服务端 error 透出');

  // ---------- 4. 401 → pS() 静默续期 → 重试恰一次 ----------
  console.log('\n=== 4. 401 → pS() 续期一次 → 重试恰一次（新 token）→ 仍 401 只提示不登出 ===');
  const fc0 = fetchCalls, pc0 = pSCalls;
  token = 'tok1';
  SCRIPT = [{ status: 401, body: { error: 'x' } }, { status: 401, body: { error: 'x' } }];
  r = await sendOnce('bug', '这是一条先撞 401 的反馈内容', 'me@x');
  chk(fetchCalls - fc0 === 2, '401 应重试恰一次：共 2 次（实际 ' + (fetchCalls - fc0) + '）');
  chk(pSCalls - pc0 === 1, 'pS() 应恰好调用 1 次（实际 ' + (pSCalls - pc0) + '）');
  chk(reqs[reqs.length - 2].headers.Authorization === 'Bearer tok1', '首次请求用旧 token');
  chk(reqs[reqs.length - 1].headers.Authorization === 'Bearer tok2', '重试必须用续期后的新 token');
  chk(r && !r.ok && r.status === 401, '终态 401');
  chk(/重新登录/.test(r.msg), '401 终态只提示重新登录，不踢会话（实际 ' + r.msg + '）');
  ok('401 = 续期 1 次 + 重试 1 次 + 新 token + 不登出');

  // ---------- 5. 成功（走真实 UI 路径）：toast + 关闭 + 清空表单 + 记冷却 ----------
  console.log('\n=== 5. 成功路径（UI 全链）：类型切换/请求体 6 字段/toast(gain)/关闭/清空表单 ===');
  const fc1 = fetchCalls;
  SCRIPT = [{ status: 200, body: { ok: true, id: 42 } }];
  windowStub.YLFB_OPEN();
  const cur = windowStub.__YLFB_CUR;
  chk(!!cur && !!cur.ta && !!cur.btn, '模态应打开并暴露表单');
  chk(documentStub.body.children.indexOf(cur.mask) >= 0, '模态应挂在 body 上');
  chk(cur.kind === 'bug', '默认类型 bug');
  cur.kSug._h.click[0]();                       // 点「需求建议」
  chk(cur.kind === 'suggestion', '类型应切到 suggestion');
  chk(/ylfb-kind-on/.test(cur.kSug.className) && !/ylfb-kind-on/.test(cur.kBug.className), '选中态高亮应切换');
  cur.ta.value = '这是一个语义测试的反馈内容，请忽略';
  cur.inp.value = 'qq:123456';
  cur.btn._h.click[0]();                        // 点提交
  await new Promise((res) => setTimeout(res, 20));
  chk(fetchCalls - fc1 === 1, '成功路径应恰好 1 次请求');
  const last = reqs[reqs.length - 1];
  chk(last.url === '/yl/api/feedback', '端点应为 ln + /feedback（实际 ' + last.url + '）');
  chk(last.opt.method === 'POST', '应为 POST');
  const keys = Object.keys(last.body).sort();
  chk(JSON.stringify(keys) === JSON.stringify(['contact', 'content', 'kind', 'realm', 'ua', 'version']),
      '请求体字段名必须恰为契约 6 字段（实际 ' + keys.join(',') + '）');
  chk(last.body.kind === 'suggestion', 'kind 应为 suggestion');
  chk(last.body.content === '这是一个语义测试的反馈内容，请忽略', 'content 应原样上送');
  chk(last.body.contact === 'qq:123456', 'contact 应原样上送');
  chk(last.body.version === '9.9.9-sem', 'version 应取自 YlxwVersionGet()');
  chk(last.body.realm === '炼气期一层', 'realm 应取自 Be.getState().player.realm');
  chk(last.body.ua === 'sem-ua', 'ua 应取自 navigator.userAgent');
  const tOk = toastCalls.find((t) => t.key === 'fb100');
  chk(!!tOk && tOk.msg === '已收到，感谢反馈' && tOk.kind === 'gain', '成功应 toast「已收到，感谢反馈」(gain/fb100)');
  chk(windowStub.__YLFB_CUR === null, '成功后模态应关闭');
  windowStub.YLFB_OPEN();
  const cur2 = windowStub.__YLFB_CUR;
  chk(!!cur2 && cur2 !== cur, '重开应是新模态');
  chk(cur2.ta.value === '' && cur2.inp.value === '', '成功后表单应清空');
  chk(cur2.kind === 'bug', '重开类型回默认 bug');
  ok('成功 = 6 字段上送 + toast + 关闭 + 清空表单');

  // ---------- 6. 冷却拦截（模块级时间戳；fetch 不得触网） ----------
  console.log('\n=== 6. 成功后 60s 冷却拦截 ===');
  const fc2 = fetchCalls;
  r = await sendOnce('bug', '冷却期内再试一条足够长的内容', '');
  chk(r && !r.ok, '冷却期内应被拒');
  chk(/秒/.test(r.msg), '应提示剩余秒数（实际 ' + r.msg + '）');
  chk(fetchCalls === fc2, '冷却拦截不得触网（实际 fetch=' + fetchCalls + ' 期望 ' + fc2 + '）');
  ok('冷却拦截 = 本地拒绝 + 0 次网络');
}

main().then(() => {
  console.log('\n' + (fail === 0 ? '[ALL PASS] 0 失败' : '[FAIL] ' + fail + ' 项失败'));
  process.exit(fail === 0 ? 0 : 1);
}, (e) => { console.error('[ERROR] ' + (e && e.stack || e)); process.exit(1); });
