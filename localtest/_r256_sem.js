// R-256 语义真值表：把注入块从**产物**里切出来，在 Node 里跑两个 bug 的修复逻辑。
// 不依赖浏览器，直接验证状态机。
const fs = require('fs');
const path = process.argv[2];
const src = fs.readFileSync(path, 'utf8');

let fail = 0;
function chk(c, m) { if (!c) { fail++; console.log('  [FAIL] ' + m); } }
function ok(m) { console.log('  [ok] ' + m); }

// ---------- 从产物切出两块注入代码 ----------
function slice(startMark, endMark) {
  const i = src.indexOf(startMark);
  if (i < 0) throw new Error('missing start ' + startMark);
  const j = endMark ? src.indexOf(endMark, i) : -1;
  return src.slice(i, j > i ? j : i + 40000);
}

const netBlock = slice('/*YLXW_R256_V2962*/', 'function YLSaveHttpError(');
const autoBlock = slice('/*YLXW_R256A_V2962*/', '/* ===== yl-R105 advend105');

console.log('=== 注入块长度 ===');
console.log('  NET  =', netBlock.length, ' AUTO =', autoBlock.length);

// ---------- 造一个最小运行环境 ----------
const store = { player: { name: 'T' }, gameStarted: true, logs: [],
                autoMeditate: false, autoAdventure: false,
                setAutoMeditate(v) { store.autoMeditate = v; },
                setAutoAdventure(v) { store.autoAdventure = v; },
                addLog(t, k) { store.logs.push({ text: t, type: k }); } };
const kv = {};
const localStorage = {
  getItem: k => (k in kv ? kv[k] : null),
  setItem: (k, v) => { kv[k] = String(v); },
  removeItem: k => { delete kv[k]; },
};
const bodyEl = { children: [], appendChild(el) { this.children.push(el); } };
const removed = [];
const document = {
  visibilityState: 'visible',
  body: bodyEl,
  getElementById: id => bodyEl.children.find(e => e.id === id) || null,
  createElement: () => ({ id: '', style: {}, textContent: '' }),
  addEventListener: () => {},
};
const listeners = {};
const window = {
  __ylBlocked: false, __ylSid: 'sid1',
  addEventListener: (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); },
  localStorage,
};
const Be = { getState: () => store };
const Et = { getState: () => ({ isAuthenticated: true, token: 'tok' }) };
const Ze = { getState: () => ({ marketItems: [] }) };
const YlxwToastCalls = [];
function YlxwToast(m, k, key, hold) { YlxwToastCalls.push({ m, k, key }); }
function YlxwMedDur(ms) { return Math.round(ms / 1000) + 's'; }
function YlxwAdvDur(ms) { return Math.round(ms / 1000) + 's'; }
let jeCalls = 0;
function Je() { jeCalls++; }
// YLSync 最小桩：push/claim 只记录调用次数，**不再改 _busy/_inflight**
// （否则测的就不是「复位是否生效」，而是「桩自己的写回」——第一版测试就踩了这个坑）
let YLR256_PUSHED = 0, YLR256_CLAIMED = 0;
const YLSync = { _busy: false, _inflight: null, _retry: 0,
                 push(p) { YLR256_PUSHED++; return Promise.resolve({ ok: true }); },
                 claim(f) { YLR256_CLAIMED++; },
                 beat() {}, isBlocked() { return !!window.__ylBlocked; } };

// Element.remove 模拟
const _origGet = document.getElementById;
document.getElementById = id => {
  const el = bodyEl.children.find(e => e.id === id);
  if (el && !el.remove) el.remove = () => { const k = bodyEl.children.indexOf(el); if (k >= 0) bodyEl.children.splice(k, 1); };
  return el || null;
};

// ---------- 求值注入块 ----------
const ctx = { window, document, localStorage, navigator: { onLine: true, userAgent: 'node' },
              Be, Et, Ze, YlxwToast, YlxwMedDur, YlxwAdvDur, Je, YLSync,
              console, setTimeout, clearTimeout, JSON, Math, Date, Number, String, Object, Array, isFinite };
const vm = require('vm');
const sandbox = vm.createContext(ctx);
vm.runInContext(autoBlock, sandbox, { filename: 'r256auto.js' });
vm.runInContext(netBlock, sandbox, { filename: 'r256net.js' });

console.log('\n=== 1. Bug1：断网提示不再走模态 Je ===');
sandbox.YLR256NetBanner(false);
const before = jeCalls;
sandbox.YLR256Notice('网络连接异常，请检查网络后重试');
chk(jeCalls === before, 'YLR256Notice 不得调用模态 Je（实际 %d 次）' % (jeCalls - before));
chk(bodyEl.children.some(e => e.id === 'yl-r256-net-banner'), '应挂出非阻塞提示条');
chk(YlxwToastCalls.length >= 1, '应同时给一条 toast');
ok('非阻塞提示条 + toast，模态弹窗 0 次');

console.log('\n=== 2. Bug1：来网自愈（撤条 + 复位卡死态 + 重新认领 + 补存档）===');
// 先把 YLSync 置成「卡死」态，再看 heal 是否真的把它复位
YLSync._busy = true; YLSync._inflight = { pending: 1 }; YLSync._retry = 5;
window.__ylSid = '';
const pushBefore = YLR256_PUSHED, claimBefore = YLR256_CLAIMED;
sandbox.YLR256OnlineHeal();
chk(!bodyEl.children.some(e => e.id === 'yl-r256-net-banner'), '来网后提示条应被撤掉');
chk(YLSync._busy === false, 'YLSync._busy 应复位为 false（实际 %s）' % YLSync._busy);
chk(YLSync._inflight === null, 'YLSync._inflight 应复位为 null（实际 %s）' % JSON.stringify(YLSync._inflight));
chk(YLSync._retry === 0, 'YLSync._retry 应复位为 0（实际 %s）' % YLSync._retry);
chk(YLR256_CLAIMED > claimBefore, '未持有会话时应重新 claim');
chk(YLR256_PUSHED > pushBefore, '来网应立即补一次存档 push');
ok('撤条/复位/认领/补档 四件事齐备');

console.log('\n=== 3. Bug1：online 事件确实注册了 ===');
chk((listeners['online'] || []).length === 1, '应注册 online 监听');
chk((listeners['offline'] || []).length === 1, '应注册 offline 监听');
listeners['offline'][0]();
chk(bodyEl.children.some(e => e.id === 'yl-r256-net-banner'), 'offline 应挂出提示条');
listeners['online'][0]();
chk(!bodyEl.children.some(e => e.id === 'yl-r256-net-banner'), 'online 应撤掉提示条');
ok('offline→挂条 / online→撤条 闭环成立');

console.log('\n=== 4. Bug2：开关持久化读写 ===');
sandbox.YLR256WriteSwitch(1, 0);
chk(kv['yl_auto_switch'] === '{"m":1,"a":0}', '写开关格式正确（实际 %s）' % kv['yl_auto_switch']);
const sw = sandbox.YLR256ReadSwitch();
chk(sw && sw.m === 1 && sw.a === 0, '读回一致');
sandbox.YLR256WriteSwitch(0, 1);
chk(sandbox.YLR256ReadSwitch().a === 1, '可翻转');
ok('yl_auto_switch 读写闭环');

console.log('\n=== 5. Bug2：会话会话记/清 + 离开时刻打点 ===');
kv['yl_auto_sess'] = undefined; delete kv['yl_auto_sess'];
const T0 = 1700000000000;
sandbox.YLR256WriteSess('m', T0);
chk(JSON.parse(kv['yl_auto_sess']).m === T0, '打坐开门时刻已落盘');
sandbox.YLR256WriteSess('a', T0 + 1000);
chk(JSON.parse(kv['yl_auto_sess']).a === T0 + 1000, '历练开门时刻已落盘（两条共存）');
sandbox.YLR256StampLeaveAt ? null : null;
// 直接模拟离开时刻
const cur = JSON.parse(kv['yl_auto_sess']); cur.left = T0 + 60000;
kv['yl_auto_sess'] = JSON.stringify(cur);
ok('会话对象已含 left（离开时刻）');

console.log('\n=== 6. Bug2：刷新后补发结算日志（幂等 + 只算到离开那一刻）===');
store.logs.length = 0;
sandbox.YLR256ReplayLost();
chk(store.logs.length === 2, '应补 2 条日志（打坐 + 历练），实际 %d' % store.logs.length);
const txt = store.logs.map(l => l.text).join(' | ');
chk(/上次打坐中页面已刷新/.test(txt), '应含打坐补发文案');
chk(/上次历练中页面已刷新/.test(txt), '应含历练补发文案');
chk(/60s/.test(txt), '时长应为 离开−开门 = 60s（实际 %s）' % txt.slice(0, 120));
chk(store.logs.every(l => l.type === 'warning'), '补发日志应用 warning 级');
ok('补发 2 条，时长=离开−开门（不含刷新后的空窗）');

// 幂等：再跑一次不应重复补
const n1 = store.logs.length;
sandbox.YLR256ReplayLost();
chk(store.logs.length === n1, '重复调用不得重复补发（幂等）');
chk(!('yl_auto_sess' in kv), '会话消费完应清掉 key');
ok('补发幂等 + key 已清');

console.log('\n=== 7. Bug2：boot 恢复自动开关 ===');
store.autoMeditate = false; store.autoAdventure = false;
sandbox.YLR256WriteSwitch(1, 1);
sandbox.YLR256AutoResume();
chk(store.autoMeditate === true, '打坐开关应恢复为 true');
chk(store.autoAdventure === true, '历练开关应恢复为 true');
// 用户主动关掉 ⇒ 不该被恢复
store.autoMeditate = false; store.autoAdventure = false;
sandbox.YLR256WriteSwitch(0, 0);
sandbox.YLR256AutoResume();
chk(store.autoMeditate === false && store.autoAdventure === false, '开关为 0 时不得恢复');
ok('恢复遵循「记住开启状态」');

console.log('\n=== 8. Bug2：pagehide / visibilitychange 打点已注册 ===');
chk((listeners['pagehide'] || []).length === 1, '应注册 pagehide');
chk((listeners['beforeunload'] || []).length === 1, '应注册 beforeunload');
ok('离开页面会打点');

console.log('\n=== 9. ★ boot 钩子真的被接到产物里了吗（防「函数定义了却没人调」）===');
// ① boot 编排函数在注入块里
chk(typeof sandbox.YLR256Boot === 'function', 'YLR256Boot 应为函数');
// ② 产物里确实有一处「订阅回调 → 调 YLR256Boot」的接线
const wireRe = /if \(typeof YLR256Boot === "function"\) \{ setTimeout\(function \(\) \{ try \{ YLR256Boot\(\); \} catch \(e\) \{\} \}, 1200\); \}/;
chk(wireRe.test(src), '产物里应存在 boot 接线代码');
chk((src.match(/typeof YLR256Boot === "function"/g) || []).length === 1, 'boot 接线应恰好 1 处');
// ③ 接线挂在既有玩家订阅上（同一行附近应能看到 Be.subscribe(...Ny())）
const wIdx = src.search(wireRe);
const near = src.slice(Math.max(0, wIdx - 400), wIdx);
chk(/Be\.subscribe\(t=>t\.player,\(t,r\)=>\{t&&r&&t!==r&&Ny\(\)\}/.test(near), '接线应紧跟既有玩家订阅之后');
ok('boot 钩子已接线（1 处，且挂在玩家订阅后）');

console.log('\n=== 10. boot 编排：先补发、后恢复、且只跑一次 ===');
store.logs.length = 0;
store.autoMeditate = false; store.autoAdventure = false;
delete kv['yl_auto_sess'];
const T1 = 1700000000000;
kv['yl_auto_sess'] = JSON.stringify({ m: T1, a: T1, left: T1 + 45000 });
sandbox.YLR256WriteSwitch(1, 1);
sandbox.YLR256Boot();
chk(store.logs.length === 2, 'boot 应先补发 2 条结算日志（实际 ' + store.logs.length + ' 条）');
chk(store.autoMeditate === true && store.autoAdventure === true, 'boot 应随后恢复两个开关');
// 幂等：同页再调一次不重复
const l2 = store.logs.length;
sandbox.YLR256Boot();
chk(store.logs.length === l2, 'boot 只应执行一次（window.__ylR256Boot 守卫）');
ok('boot = 补发 + 恢复，且幂等');

console.log('\n' + (fail === 0 ? '[ALL PASS] 0 失败' : '[FAIL] ' + fail + ' 项失败'));
process.exit(fail === 0 ? 0 : 1);
