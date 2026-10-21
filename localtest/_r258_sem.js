// R-255 语义真值表（r258）：把 r256+r258 注入块从**补丁后产物**里切出来，在 Node 里跑状态机。
// 验证：reload→续跑（r256 语义原样）/ navigate→停+结算+开关复位 / pagehide 打点不误删会话 /
//       补发幂等 / 宁停勿盗跑（崩溃、未知类型）/ 回填守卫堵预启动窗口 / 红线静态检查。
// 不依赖浏览器。用法：node _r258_sem.js <补丁后的bundle.js>
const fs = require('fs');
const vm = require('vm');
const path = process.argv[2];
if (!path) { console.error('usage: node _r258_sem.js <patched-bundle.js>'); process.exit(2); }
const src = fs.readFileSync(path, 'utf8');

let fail = 0;
function chk(c, m) { if (!c) { fail++; console.log('  [FAIL] ' + m); } }
function ok(m) { console.log('  [ok] ' + m); }

// ---------- 从产物切片 ----------
function slice(startMark, endMark) {
  const i = src.indexOf(startMark);
  if (i < 0) throw new Error('missing start ' + startMark);
  const j = endMark ? src.indexOf(endMark, i) : -1;
  return src.slice(i, j > i ? j : i + 60000);
}
const autoRegion = slice('/*YLXW_R256A_V2962*/', 'function YlxwMedSession(on) {');
const bfStart = src.indexOf('(function () { try { if (typeof YLR258NavKind');
if (bfStart < 0) throw new Error('missing r258 backfill guard');
const bfEnd = src.indexOf('})(),', bfStart);
const backfillSrc = src.slice(bfStart, bfEnd > bfStart ? bfEnd + 4 : -1); // 只取到 '})()'，不带尾逗号
const r258Block = slice('/*YLXW_R258_V2963*/', 'function YLR256Boot() {');

console.log('=== 切片长度 ===');
console.log('  autoRegion =', autoRegion.length, ' backfill =', backfillSrc.length, ' r258 =', r258Block.length);

// ---------- 最小运行环境 ----------
let store, kv, listeners, docListeners, window, document, localStorage, Be, performance, setCalls;

function makeWorld() {
  store = { player: { name: 'T' }, gameStarted: true, logs: [],
            autoMeditate: false, autoAdventure: false };
  setCalls = [];
  store.setAutoMeditate = v => { setCalls.push(['m', v]); store.autoMeditate = v; };
  store.setAutoAdventure = v => { setCalls.push(['a', v]); store.autoAdventure = v; };
  store.addLog = (t, k) => { store.logs.push({ text: t, type: k }); };
  kv = {};
  localStorage = {
    getItem: k => (k in kv ? kv[k] : null),
    setItem: (k, v) => { kv[k] = String(v); },
    removeItem: k => { delete kv[k]; },
  };
  listeners = {}; docListeners = {};
  window = { __ylBlocked: false, __ylSid: 'sid1',
             addEventListener: (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); },
             localStorage };
  document = { visibilityState: 'visible',
               addEventListener: (ev, fn) => { (docListeners[ev] = docListeners[ev] || []).push(fn); } };
  Be = { getState: () => store };
  performance = { getEntriesByType: t => (t === 'navigation' ? [{ type: 'navigate' }] : []) };
}

makeWorld();
// eval 时刻的监听器登记表（pagehide/visibilitychange 注册进这一组；场景重建世界后仍从这里取 handler。
// handler 体内对 window/document 的引用走 context global、调用时已重绑到新世界，所以打点落在当前 kv 上）
const evalWinListeners = listeners;
const evalDocListeners = docListeners;
const ctx = { window, document, localStorage, navigator: { onLine: true },
              Be, performance,
              YlxwMedDur: ms => Math.round(ms / 1000) + 's',
              YlxwAdvDur: ms => Math.round(ms / 1000) + 's',
              console, setTimeout, clearTimeout, JSON, Math, Date, Number, String, Object, Array };
const sandbox = vm.createContext(ctx);
vm.runInContext(autoRegion, sandbox, { filename: 'r256auto+r258.js' });
vm.runInContext('var __r258bf = function () { return ' + backfillSrc + '; };', sandbox, { filename: 'r258bf.js' });

// 各场景间清状态：重建世界并把新对象重绑进 context global（沙箱内函数按标识符在调用时解析）
function resetWorld(navType, opts) {
  opts = opts || {};
  makeWorld();
  if (navType !== null) {
    performance = { getEntriesByType: t => (t === 'navigation' ? [{ type: navType }] : []) };
    sandbox.performance = performance;
  } else {
    performance = undefined;
    sandbox.performance = undefined;
  }
  sandbox.window = window; sandbox.document = document; sandbox.localStorage = localStorage;
  sandbox.Be = Be;
  if (opts.switchOn) sandbox.YLR256WriteSwitch(opts.switchOn[0] ? 1 : 0, opts.switchOn[1] ? 1 : 0);
  if (opts.sess) kv['yl_auto_sess'] = JSON.stringify(opts.sess);
}

console.log('\n=== 1. NavKind 真值表（Navigation Timing 三分 + 兜底） ===');
function navKindWith(perf) {
  const saved = sandbox.performance;
  sandbox.performance = perf;
  const r = sandbox.YLR258NavKind();
  sandbox.performance = saved;
  return r;
}
chk(navKindWith({ getEntriesByType: t => t === 'navigation' ? [{ type: 'reload' }] : [] }) === 'refresh', "reload ⇒ refresh");
chk(navKindWith({ getEntriesByType: t => t === 'navigation' ? [{ type: 'back_forward' }] : [] }) === 'refresh', "back_forward ⇒ refresh");
chk(navKindWith({ getEntriesByType: t => t === 'navigation' ? [{ type: 'navigate' }] : [] }) === 'close', "navigate ⇒ close");
chk(navKindWith({ getEntriesByType: t => t === 'navigation' ? [{ type: 'prerender' }] : [] }) === 'close', "prerender（未知类型）⇒ close");
chk(navKindWith({ getEntriesByType: t => [] }) === 'close', '空 navigation 条目 ⇒ close（宁停勿盗跑）');
chk(navKindWith(undefined) === 'close', '无 performance.getEntriesByType ⇒ close');
chk(navKindWith({ navigation: { type: 1 } }) === 'refresh', '旧版 API type=1(reload) ⇒ refresh');
chk(navKindWith({ navigation: { type: 2 } }) === 'refresh', '旧版 API type=2(back/forward) ⇒ refresh');
chk(navKindWith({ navigation: { type: 0 } }) === 'close', '旧版 API type=0(navigate) ⇒ close');
chk(navKindWith({ navigation: {} }) === 'close', '旧版 API 无数字 type ⇒ close');
ok('NavKind 十条真值全对，未知一律 close（宁停勿盗跑）');

console.log('\n=== 2. store 回填守卫（R3：navigate 加载不得带开关启动） ===');
sandbox.performance = { getEntriesByType: t => t === 'navigation' ? [{ type: 'navigate' }] : [] };
sandbox.window = window; sandbox.Be = Be;
kv['yl_auto_switch'] = '{"m":1,"a":1}';
window.__ylR258ClosedBoot = undefined;
let bf = sandbox.__r258bf();
chk(bf && bf.autoMeditate === undefined && bf.autoAdventure === undefined, 'navigate ⇒ 回填 {}（store 不带开关启动）');
chk(window.__ylR258ClosedBoot === 1, 'navigate ⇒ 置标志 __ylR258ClosedBoot=1');
sandbox.performance = { getEntriesByType: t => t === 'navigation' ? [{ type: 'reload' }] : [] };
window.__ylR258ClosedBoot = undefined;
bf = sandbox.__r258bf();
chk(bf && bf.autoMeditate === true && bf.autoAdventure === true, 'reload ⇒ 回填原样（{autoMeditate:true,autoAdventure:true}）');
chk(window.__ylR258ClosedBoot === undefined, 'reload ⇒ 不置标志');
delete kv['yl_auto_switch'];
bf = sandbox.__r258bf();
chk(bf && Object.keys(bf).length === 0, '无存档 ⇒ 回填 {} 且不置标志');
ok('回填守卫三条全对（预启动窗口已堵死）');

console.log('\n=== 3. navigate boot：停 + 结算 + 开关复位 + 不续跑（R-255 核心场景） ===');
resetWorld('navigate', { switchOn: [true, true], sess: { m: Date.now() - 60000, a: Date.now() - 60000, left: Date.now() } });
window.__ylR258ClosedBoot = 1;
sandbox.YLR256Boot();
chk(store.logs.length === 2, '应补 2 条结算日志（打坐+历练），实际 ' + store.logs.length);
chk(store.logs.every(l => l.type === 'warning'), '结算日志应用 warning 级');
chk(/因关闭页面已自动停止/.test(store.logs[0].text) && /上次打坐/.test(store.logs[0].text), '打坐结算文案正确: ' + store.logs[0].text.slice(0, 40));
chk(/因关闭页面已自动停止/.test(store.logs[1].text) && /上次历练/.test(store.logs[1].text), '历练结算文案正确');
chk(/60s/.test(store.logs[0].text) && /60s/.test(store.logs[1].text), '时长 = 离开打点 − 开门 = 60s');
chk(kv['yl_auto_switch'] === '{"m":0,"a":0}', '开关已复位为关（实际 %s)'.replace('%s', kv['yl_auto_switch']));
chk(!('yl_auto_sess' in kv), '会话已清');
chk(store.autoMeditate === false && store.autoAdventure === false, 'store 两开关均为关（绝不自动续跑）');
chk(!setCalls.some(c => c[1] === true), '全程不得有任何 setAuto*(true) 调用');
chk(window.__ylR258ClosedBoot === 2, '标志已消费（1→2）');
const n3 = store.logs.length;
sandbox.YLR256Boot();
chk(store.logs.length === n3, 'boot 幂等：第二次不重复补发/不重复复位');
ok('navigate boot = 补结算 + 复位 + 清会话 + 零续跑，且幂等');

console.log('\n=== 4. reload boot：r256 语义原样（续跑 + 「页面已刷新」补发 + 开关不复位） ===');
resetWorld('reload', { switchOn: [true, true], sess: { m: Date.now() - 45000, a: Date.now() - 45000, left: Date.now() } });
sandbox.YLR256Boot();
chk(store.logs.length === 2, 'r256 补发 2 条（实际 ' + store.logs.length + '）');
chk(/页面已刷新/.test(store.logs.map(l => l.text).join('|')), '补发文案仍是「页面已刷新」系（r256 原样）');
chk(store.autoMeditate === true && store.autoAdventure === true, '自动开关已恢复（刷新续跑语义保持）');
chk(kv['yl_auto_switch'] === '{"m":1,"a":1}', 'reload 路径绝不得复位开关');
chk('yl_auto_sess' in kv, 'boot 为新会话重新记账（r256 原样）');
const n4 = store.logs.length;
sandbox.YLR256Boot();
chk(store.logs.length === n4, 'boot 幂等守卫依旧（__ylR256Boot）');
ok('reload boot 完全走 r256 原路径，红线未破坏');

console.log('\n=== 5. pagehide 打点不误删会话（打点→真关→重开结算链路） ===');
resetWorld('navigate', { switchOn: [true, false] });
const T5 = Date.now() - 60000;
sandbox.YLR256WriteSess('m', T5);
chk(JSON.parse(kv['yl_auto_sess']).m === T5, '会话开门时刻已落盘');
chk((evalWinListeners['pagehide'] || []).length === 1, 'pagehide 监听已注册');
(evalWinListeners['pagehide'] || [])[0]();
let sess5 = JSON.parse(kv['yl_auto_sess']);
chk(sess5.m === T5 && sess5.left > 0, 'pagehide 打点后 m 仍在、left 已盖（不误删）');
chk(kv['yl_auto_switch'] === '{"m":1,"a":0}', '打点不动开关（页面开着绝不能自己停）');
chk((evalDocListeners['visibilitychange'] || []).length === 1, 'visibilitychange 监听已注册');
(evalDocListeners['visibilitychange'] || [])[0]();
sess5 = JSON.parse(kv['yl_auto_sess']);
chk(sess5.m === T5 && sess5.left > 0, 'visibilitychange hidden 同样只打点不删除');
window.__ylR258ClosedBoot = 1;
sandbox.YLR256Boot();
chk(store.logs.length === 1 && /上次打坐.*因关闭页面已自动停止/.test(store.logs[0].text), '重开后只补打坐 1 条结算（实际 ' + store.logs.length + ' 条）');
chk(kv['yl_auto_switch'] === '{"m":0,"a":0}', '开关复位');
ok('pagehide 打点 → 不删会话 → 下次 navigate boot 按打点时刻结算');

console.log('\n=== 6. 崩溃场景（有会话、无 left）：只复位不编造时长 ===');
resetWorld('navigate', { switchOn: [true, true], sess: { m: Date.now() - 60000, a: Date.now() - 60000 } });
window.__ylR258ClosedBoot = 1;
sandbox.YLR256Boot();
chk(store.logs.length === 0, '无 left 不得编造结算日志（实际 ' + store.logs.length + ' 条）');
chk(kv['yl_auto_switch'] === '{"m":0,"a":0}', '开关仍复位（宁停勿盗跑）');
chk(!('yl_auto_sess' in kv), '悬挂会话仍清掉');
ok('浏览器崩溃 ⇒ 静默复位，不盗跑也不造假账');

console.log('\n=== 7. 短会话（<3s）：不补结算，但仍复位 ===');
resetWorld('navigate', { switchOn: [true, false], sess: { m: Date.now() - 1500, left: Date.now() } });
window.__ylR258ClosedBoot = 1;
sandbox.YLR256Boot();
chk(store.logs.length === 0, '<3s 不补结算日志');
chk(kv['yl_auto_switch'] === '{"m":0,"a":0}', '开关复位照做');
ok('阈值与 r256 一致（3000ms）');

console.log('\n=== 8. 双保险：store 已被别的路径打开时，close boot 兜底关掉 ===');
resetWorld('navigate', { switchOn: [true, true], sess: { m: Date.now() - 60000, a: 0, left: Date.now() } });
store.autoMeditate = true; // 模拟任何绕过回填的路径
window.__ylR258ClosedBoot = 1;
sandbox.YLR256Boot();
chk(store.autoMeditate === false, 'CloseSettle 兜底把 store 打坐开关关掉');
chk(setCalls.some(c => c[0] === 'm' && c[1] === false), '复位走 setAutoMeditate(false)（联动 UI/边沿效应）');
chk(store.logs.length === 1, '只补存在会话的那 1 条（打坐），历练(a=0)不补');
ok('store 双保险复位生效');

console.log('\n=== 9. 无会话的 navigate boot：静默复位，零日志 ===');
resetWorld('navigate', { switchOn: [true, true] });
window.__ylR258ClosedBoot = 1;
sandbox.YLR256Boot();
chk(store.logs.length === 0, '无会话不补任何日志');
chk(kv['yl_auto_switch'] === '{"m":0,"a":0}', '开关复位');
ok('干净打开（如首次进游戏）不受影响');

console.log('\n=== 10. 静态红线：R258 模块零监听/零定时器/零网络；r256 关键件原样 ===');
chk(r258Block.indexOf('addEventListener') < 0, 'R258 模块不得注册任何事件监听');
chk(r258Block.indexOf('setTimeout') < 0 && r258Block.indexOf('setInterval') < 0, 'R258 模块不得有定时器');
chk(r258Block.indexOf('fetch(') < 0 && r258Block.indexOf('XMLHttpRequest') < 0, 'R258 模块不得有网络原语');
chk(r258Block.indexOf('localStorage') < 0, 'R258 模块不直接碰 localStorage（一律走 r256 助手）');
chk((src.match(/typeof YLR258RouteBoot === "function" && YLR258RouteBoot\(\)\) return/g) || []).length === 1, 'boot 分流调用恰好 1 处');
chk((src.match(/__ylR258ClosedBoot = 1; return \{\};/g) || []).length === 1, '回填守卫恰好 1 处');
chk((src.match(/\/\*YLXW_R258_V2963\*\//g) || []).length === 1, 'r258 幂等标记恰好 1 处');
chk((src.match(/YLR256WriteSwitch\(0, 0\);/g) || []).length === 1, '开关复位调用恰好 1 处');
chk((src.match(/function YLR256Boot\(\) \{/g) || []).length === 1, 'YLR256Boot 定义仍唯一');
chk((src.match(/function YLR256ReplayLost\(\)/g) || []).length === 1, 'ReplayLost 仍唯一');
chk((src.match(/function YLR256AutoResume\(\)/g) || []).length === 1, 'AutoResume 仍唯一');
chk(src.indexOf('window.addEventListener("pagehide", function () { YLR256StampLeave(); })') >= 0, 'r256 pagehide 打点原样');
chk(src.indexOf('if (typeof YLR256Boot === "function") { setTimeout(function () { try { YLR256Boot(); } catch (e) {} }, 1200); }') >= 0, 'r256 boot 接线原样');
ok('静态红线全过');

console.log('\n' + (fail === 0 ? '[ALL PASS] 0 失败' : '[FAIL] ' + fail + ' 项失败'));
process.exit(fail === 0 ? 0 : 1);
