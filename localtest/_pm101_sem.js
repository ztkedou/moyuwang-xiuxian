// PM-101 语义真值表：把注入块与三处拼接从**产物**里切出来，在 Node 里直跑（仿 _fb100_sem.js）。
// 不依赖浏览器：stub DOM/fetch/jo/ln/pS/YlxwToast + e.jsx/jsxs/YlxwRow/YlxwBtn 等，验证：
//   校验(收件人空/内容空/太短/太长/2字下界) / 冷却拦截(仅成功记 30s) / 401 静默续期重试恰一次 /
//   409 与 400 服务端 error 透出 / 500 兜底 / 成功 UI 全链(预填/{to,content}/toast/关闭/清空) /
//   仙友录行「私信」钮 / 在线人物行「私信」push(切磋之后、isSelf 无) / 信箱行 kind=player 回信钮。
// 用法：node _pm101_sem.js <补丁后产物.js>
const fs = require('fs');
const vm = require('vm');
const path = process.argv[2];
if (!path) { console.error('usage: node _pm101_sem.js <patched.js>'); process.exit(2); }
const src = fs.readFileSync(path, 'utf8');

let fail = 0;
function chk(c, m) { if (!c) { fail++; console.log('  [FAIL] ' + m); } }
function ok(m) { console.log('  [ok] ' + m); }

// ---------- 切片工具 ----------
function at(s, from) { const i = src.indexOf(s, from || 0); if (i < 0) throw new Error('missing ' + s); return i; }

// ---------- 1) 注入块（MARK → const Q0 锚点） ----------
const block = src.slice(at('/* == YL_PM101_V1'), at('const Q0="/yl/api"'));
console.log('=== 注入块 ===');
console.log('  BLOCK =', block.length, 'chars');

// ---------- 最小运行环境（块用） ----------
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
              fetch: fetchStub, jo, ln: '/yl/api', pS, YlxwToast,
              console, setTimeout, clearTimeout, Date, Math, JSON, String, Number, Promise, Object, Array };
vm.runInNewContext(block, ctx, { filename: 'pm101block.js' });

// ---------- 行拼接 eval 工具（各自独立 vm，window.YLPM_OPEN 换成 spy） ----------
function newRowCtx(spyLog) {
  const w = { YLPM_OPEN: (to) => spyLog.push(String(to)) };
  const c = { window: w, console, setTimeout, Date, Math, JSON, String, Number, Promise, Object, Array };
  // React stub：jsx/jsxs 造 {comp, props, key} 节点；组件函数带 __tag 供归一化识别
  const mkComp = (tag) => { const f = (p) => ({ comp: tag, props: p }); f.__tag = tag; return f; };
  c.YlxwRow = mkComp('Row'); c.YlxwBtn = mkComp('Btn'); c.YlxwMailDelBtn = mkComp('Del');
  const jsx = (comp, p, k) => ({ comp: (comp && comp.__tag) || comp, props: p, key: k });
  c.e = { jsx, jsxs: jsx };
  c.YlxwNum = (n) => String(n);
  return c;
}
function walk(node, out) {
  if (!node || typeof node !== 'object') return;
  if (node.comp !== undefined) out.push(node);
  const ch = node.props && node.props.children;
  if (Array.isArray(ch)) ch.forEach((x) => walk(x, out));
  else if (ch && typeof ch === 'object') walk(ch, out);
}

async function main() {
  console.log('\n=== 0. 求值即就绪：window 导出 + 样式已注入 ===');
  chk(typeof windowStub.YLPM_SUBMIT === 'function', 'window.YLPM_SUBMIT 应为函数');
  chk(typeof windowStub.YLPM_SEND === 'function', 'window.YLPM_SEND 应为函数');
  chk(typeof windowStub.YLPM_OPEN === 'function', 'window.YLPM_OPEN 应为函数');
  chk(fetchCalls === 0 && pSCalls === 0, '求值期不得发请求/续期');
  const styleEl = documentStub.head.children.find((e) => e.id === 'ylpm-style');
  chk(!!styleEl, 'load 时应注入 <style id="ylpm-style">');
  chk(!!styleEl && styleEl.textContent.includes('.ylpm-mask{'), '样式应含 .ylpm-mask 定义');
  ok('三个 window 导出 + 弹窗样式就绪');

  // ---------- 1. 校验（全在冷却/网络之前，除「2 字探底」外 fetch 必须保持 0） ----------
  console.log('\n=== 1. 校验：收件人空 / 内容空 / 太短 / 太长 / 2 字下界 ===');
  const sendOnce = (to, content) => new Promise((res) => windowStub.YLPM_SEND(to, content, res));
  let r = await sendOnce('   ', '这是一个合法长度的私信内容');
  chk(r && r.ok === false && /请填写收件人/.test(r.msg), '收件人空应被拒（实际 ' + (r && r.msg) + '）');
  r = await sendOnce('张三', '   ');
  chk(r && !r.ok && /请填写私信内容/.test(r.msg), '内容空应被拒（实际 ' + r.msg + '）');
  r = await sendOnce('张三', '短');
  chk(r && !r.ok && /太短/.test(r.msg), '1 字应判太短（实际 ' + r.msg + '）');
  r = await sendOnce('张三', 'x'.repeat(501));
  chk(r && !r.ok && /太长/.test(r.msg), '501 字应判太长（实际 ' + r.msg + '）');
  chk(fetchCalls === 0, '校验阶段不得触网（实际 fetch=' + fetchCalls + '）');
  SCRIPT = [{ status: 500, body: {} }];
  r = await sendOnce('张三', '好的');                      // 2 字 = 下界合法 → 必须放行到网络（500 不记冷却）
  chk(r && !r.ok && r.status === 500 && fetchCalls === 1, '2 字应放行到网络（实际 fetch=' + fetchCalls + ' status=' + r.status + '）');
  ok('四类校验全拦下；2 字下界放行');

  // ---------- 2. 409：显示服务端 error，不记冷却 ----------
  console.log('\n=== 2. 409 → 显示服务端 error，不记冷却 ===');
  SCRIPT = [{ status: 409, body: { error: '发送太频繁，请稍后再试' } }];
  const fc0 = fetchCalls;
  r = await sendOnce('张三', '这是一条会撞 409 频控的私信内容');
  chk(fetchCalls - fc0 === 1, '应恰好发 1 次请求（实际 ' + (fetchCalls - fc0) + '）');
  chk(pSCalls === 0, '409 不得触发续期');
  chk(r && !r.ok && r.status === 409, 'status 应为 409');
  chk(r.msg === '发送太频繁，请稍后再试', '应原样显示服务端 error（实际 ' + r.msg + '）');
  ok('409 分支 = 服务端 error 透出');

  // ---------- 3. 400 / 500 分支 ----------
  console.log('\n=== 3. 400 / 500 分支表现 ===');
  SCRIPT = [{ status: 400, body: { error: '收件人不存在' } }];
  r = await sendOnce('路人甲', '这是一条会撞 400 的私信内容哦');
  chk(r && !r.ok && r.status === 400 && r.msg === '收件人不存在', '400 应透出服务端 error（实际 ' + r.msg + '）');
  SCRIPT = [{ status: 500, body: {} }];
  r = await sendOnce('张三', '这是一条会撞 500 的私信内容哦');
  chk(r && !r.ok && r.status === 500 && /发送失败/.test(r.msg), '500 应给兜底提示（实际 ' + r.msg + '）');
  ok('400 服务端 error 透出 / 500 兜底提示');

  // ---------- 4. 401 → pS() 静默续期 → 重试恰一次 ----------
  console.log('\n=== 4. 401 → pS() 续期一次 → 重试恰一次（新 token）→ 仍 401 只提示不登出 ===');
  const fc1 = fetchCalls, pc0 = pSCalls;
  token = 'tok1';
  SCRIPT = [{ status: 401, body: { error: 'x' } }, { status: 401, body: { error: 'x' } }];
  r = await sendOnce('张三', '这是一条先撞 401 的私信内容哦');
  chk(fetchCalls - fc1 === 2, '401 应重试恰一次：共 2 次（实际 ' + (fetchCalls - fc1) + '）');
  chk(pSCalls - pc0 === 1, 'pS() 应恰好调用 1 次（实际 ' + (pSCalls - pc0) + '）');
  chk(reqs[reqs.length - 2].headers.Authorization === 'Bearer tok1', '首次请求用旧 token');
  chk(reqs[reqs.length - 1].headers.Authorization === 'Bearer tok2', '重试必须用续期后的新 token');
  chk(r && !r.ok && r.status === 401, '终态 401');
  chk(/重新登录/.test(r.msg), '401 终态只提示重新登录，不踢会话（实际 ' + r.msg + '）');
  ok('401 = 续期 1 次 + 重试 1 次 + 新 token + 不登出');

  // ---------- 5. 成功（走真实 UI 路径）：预填/请求体 2 字段/toast(gain)/关闭/清空/记冷却 ----------
  console.log('\n=== 5. 成功路径（UI 全链）：收件人预填/请求体 {to,content}/toast/关闭/清空 ===');
  SCRIPT = [{ status: 200, body: { ok: true, id: 42 } }];
  windowStub.YLPM_OPEN('李四');
  let cur = windowStub.__YLPM_CUR;
  chk(!!cur && !!cur.ta && !!cur.btn && !!cur.inp, '模态应打开并暴露表单');
  chk(documentStub.body.children.indexOf(cur.mask) >= 0, '模态应挂在 body 上');
  chk(cur.inp.value === '李四', '收件人应预填「李四」（实际 ' + cur.inp.value + '）');
  chk(documentStub.body.children.filter((n) => n.className === 'ylpm-mask').length === 1, '只有 1 个弹窗');
  windowStub.YLPM_OPEN('王五');                            // 已开 → 只改收件人
  chk(windowStub.__YLPM_CUR === cur, '已开时 OPEN 不得新开模态');
  chk(cur.inp.value === '王五', '已开时 OPEN 应改收件人为「王五」（实际 ' + cur.inp.value + '）');
  cur.ta.value = '这是一条语义测试的私信，请忽略';
  const fc2 = fetchCalls;
  cur.btn._h.click[0]();                                    // 点发送
  await new Promise((res) => setTimeout(res, 20));
  chk(fetchCalls - fc2 === 1, '成功路径应恰好 1 次请求');
  const last = reqs[reqs.length - 1];
  chk(last.url === '/yl/api/mail/send', '端点应为 ln + /mail/send（实际 ' + last.url + '）');
  chk(last.opt.method === 'POST', '应为 POST');
  const keys = Object.keys(last.body).sort();
  chk(JSON.stringify(keys) === JSON.stringify(['content', 'to']),
      '请求体字段名必须恰为契约 {to, content}（实际 ' + keys.join(',') + '）');
  chk(last.body.to === '王五', 'to 应为改动后的收件人（实际 ' + last.body.to + '）');
  chk(last.body.content === '这是一条语义测试的私信，请忽略', 'content 应原样上送');
  chk(last.headers.Authorization === 'Bearer tok2', '应带 Bearer（jo() 当前 token）');
  const tOk = toastCalls.find((t) => t.key === 'pm101');
  chk(!!tOk && tOk.msg === '私信已发送' && tOk.kind === 'gain', '成功应 toast「私信已发送」(gain/pm101)');
  chk(windowStub.__YLPM_CUR === null, '成功后模态应关闭');
  windowStub.YLPM_OPEN('赵六');
  cur = windowStub.__YLPM_CUR;
  chk(!!cur, '重开应是新模态');
  chk(cur.ta.value === '', '成功后内容应清空（实际 ' + JSON.stringify(cur.ta.value) + '）');
  chk(cur.inp.value === '赵六', '重开收件人应预填新目标（实际 ' + cur.inp.value + '）');
  ok('成功 = {to,content} 上送 + toast + 关闭 + 清空内容 + 预填生效');

  // ---------- 6. 冷却拦截（模块级时间戳；fetch 不得触网） ----------
  console.log('\n=== 6. 成功后 30s 冷却拦截 ===');
  const fc3 = fetchCalls;
  r = await sendOnce('张三', '冷却期内再试一条合法长度的私信');
  chk(r && !r.ok, '冷却期内应被拒');
  chk(/秒/.test(r.msg), '应提示剩余秒数（实际 ' + r.msg + '）');
  chk(fetchCalls === fc3, '冷却拦截不得触网（实际 fetch=' + fetchCalls + ' 期望 ' + fc3 + '）');
  ok('冷却拦截 = 本地拒绝 + 0 次网络');

  // ---------- 7. 仙友录好友行「私信」钮（拼接 eval） ----------
  console.log('\n=== 7. 仙友录好友行：私信钮 → YLPM_OPEN(N.name) ===');
  {
    const af = at('function YlxwTFriends() {');
    const mStart = '((t && t.friends) || []).map(function(N) {';
    const p1 = at(mStart, af) + mStart.length;
    const endMark = ', "f" + N.id); })';
    const p2 = at(endMark, p1);
    const body = src.slice(p1, p2);                        // return e.jsxs(YlxwRow, {...props}
    const spy = [];
    const c3 = newRowCtx(spy);
    c3.FD = [{ id: 1, name: '张三', realmName: '', giftedToday: false }, { id: 2, name: '李四', realmName: '筑基', giftedToday: true }];
    c3.u = ''; c3.f = function () {};
    vm.runInNewContext('var FR = FD.map(function(N) { ' + body + endMark + ';', c3);
    const rows = c3.FR;
    chk(Array.isArray(rows) && rows.length === 2, '应产出 2 行（实际 ' + (rows && rows.length) + '）');
    const nodes = [];
    rows.forEach((rw) => walk(rw, nodes));
    const pm = nodes.filter((n) => n.comp === 'Btn' && n.props.children === '私信');
    chk(pm.length === 2, '每行应恰有 1 个「私信」钮（实际 ' + pm.length + '）');
    pm[0].props.onClick();
    chk(spy.length === 1 && spy[0] === '张三', '私信钮应调 YLPM_OPEN("张三")（实际 ' + JSON.stringify(spy) + '）');
    pm[1].props.onClick();
    chk(spy[1] === '李四', '第二行私信钮应收件人=李四（实际 ' + spy[1] + '）');
    const gift = nodes.filter((n) => n.comp === 'Btn' && n.props.children === '送礼');
    chk(gift.length === 1, '未送礼行仍应有「送礼」钮（实际 ' + gift.length + '）');
    ok('好友行 = 每行「私信」钮 + 收件人正确 + 送礼钮未动');
  }

  // ---------- 8. 在线人物玩家行「私信」push（R-144 DOM 栈拼接 eval） ----------
  console.log('\n=== 8. 在线人物行：私信 push（切磋之后、isSelf 无） ===');
  {
    const p1 = at('function onlineRow(p){');
    const p2 = at('\nfunction renderBody(){', p1);
    const body = src.slice(p1, p2);                        // 完整 onlineRow 函数
    const spy = [];
    const c4 = newRowCtx(spy);
    c4.btn = (label, cls, fn) => ({ label, cls, fn });
    c4.dis = (label) => ({ label, disabled: true });
    c4.row = (name, sub, acts) => ({ name, sub, acts });
    c4.st = () => {};
    c4.YlxwPost = () => ({ then() { return { catch() {} }; }, catch() {} });
    c4.loadOnline = () => {}; c4.loadFriends = () => {};
    vm.runInNewContext(body, c4);
    const rSelf = c4.onlineRow({ name: '我自己', isSelf: true });
    chk(rSelf.acts.length === 0, 'isSelf 行不得有「私信」（实际 ' + rSelf.acts.length + ' 个按钮）');
    const rOther = c4.onlineRow({ name: '王五', isFriend: true });
    const labels = rOther.acts.map((x) => x.label);
    chk(labels.indexOf('私信') === labels.length - 1, '「私信」应在行尾（实际 ' + labels.join(',') + '）');
    chk(labels.indexOf('切磋') === labels.length - 2, '「私信」应紧随「切磋」（实际 ' + labels.join(',') + '）');
    chk(labels.indexOf('加好友') === -1, 'isFriend=true 不应有「加好友」');
    rOther.acts[labels.indexOf('私信')].fn();
    chk(spy.length === 1 && spy[0] === '王五', '私信 push 应调 YLPM_OPEN("王五")（实际 ' + JSON.stringify(spy) + '）');
    const rStranger = c4.onlineRow({ name: '路人乙', isFriend: false });
    const labels2 = rStranger.acts.map((x) => x.label);
    chk(labels2.join(',') === '加好友,拜师,切磋,私信', '陌生玩家行 = 加好友,拜师,切磋,私信（实际 ' + labels2.join(',') + '）');
    ok('在线行 = 私信在切磋后 + isSelf 无 + 收件人正确');
  }

  // ---------- 9. 信箱行：kind=player → 发信人 + 回信钮（拼接 eval） ----------
  console.log('\n=== 9. 信箱行：kind=player 渲染发信人+回信，system 不渲染 ===');
  {
    const af = at('function YlxwTMail() {');
    const mStart = 'm.map(function(g) {';
    const p1 = at(mStart, af) + mStart.length;
    const endMark = '}, "m" + g.id);';
    const p2 = at(endMark, p1) + endMark.length;
    const body = src.slice(p1, p2);                        // return e.jsxs(YlxwRow, {...}, "m" + g.id);
    const spy = [];
    const c5 = newRowCtx(spy);
    c5.u = ''; c5.f = function () {}; c5.c = function () {};
    c5.M = [
      { id: 1, kind: 'player', sender: '张三', title: '来自 张三 的私信', content: '道友安好', lingshi: 0, claimed: true, createdAt: '2026-10-21 10:00:00' },
      { id: 2, kind: 'system', sender: 'system', title: '灵田丰收', content: '收获血参草×2', lingshi: 0, claimed: true, createdAt: '2026-10-21 09:00:00' },
      { id: 3, sender: '张三', title: '来自 张三 的私信', content: '旧响应无 kind 兜底', lingshi: 0, claimed: true, createdAt: '2026-10-21 08:00:00' },
    ];
    vm.runInNewContext('var ARR = M.map(function(g) { ' + body + ' });', c5);
    const rows = c5.ARR;
    chk(Array.isArray(rows) && rows.length === 3, '应产出 3 行（实际 ' + (rows && rows.length) + '）');
    const collect = (rw) => { const ns = []; walk(rw, ns); return ns; };
    const r1 = collect(rows[0]), r2 = collect(rows[1]), r3 = collect(rows[2]);
    const reply1 = r1.filter((n) => n.comp === 'Btn' && n.props.children === '回信');
    const reply2 = r2.filter((n) => n.comp === 'Btn' && n.props.children === '回信');
    const reply3 = r3.filter((n) => n.comp === 'Btn' && n.props.children === '回信');
    chk(reply1.length === 1, 'player 信（kind=player）应有回信钮（实际 ' + reply1.length + '）');
    chk(reply2.length === 0, 'system 信不得有回信钮（实际 ' + reply2.length + '）');
    chk(reply3.length === 1, '无 kind 但 sender 非 system 应兜底出回信钮（实际 ' + reply3.length + '）');
    const sender1 = r1.filter((n) => n.props && typeof n.props.children === 'string' && n.props.children.indexOf('发信人 ') === 0);
    chk(sender1.length === 1 && sender1[0].props.children === '发信人 张三', '应渲染「发信人 张三」（实际 ' + (sender1[0] && sender1[0].props.children) + '）');
    const sender2 = r2.filter((n) => n.props && typeof n.props.children === 'string' && n.props.children.indexOf('发信人 ') === 0);
    chk(sender2.length === 0, 'system 信不得渲染发信人 span');
    reply1[0].props.onClick();
    chk(spy.length === 1 && spy[0] === '张三', '回信钮应调 YLPM_OPEN("张三")（实际 ' + JSON.stringify(spy) + '）');
    const del = r1.filter((n) => n.comp === 'Del');
    chk(del.length === 1, '删除钮应保留（实际 ' + del.length + '）');
    ok('信箱行 = player 渲染发信人+回信 / system 无 / 无 kind 兜底 / 删除钮未动');
  }
}

main().then(() => {
  console.log('\n' + (fail === 0 ? '[ALL PASS] 0 失败' : '[FAIL] ' + fail + ' 项失败'));
  process.exit(fail === 0 ? 0 : 1);
}, (e) => { console.error('[ERROR] ' + (e && e.stack || e)); process.exit(1); });
