// R-254 语义真值表：把 r146+r162+r161+r257 包装链从**补丁后产物**里切出来，在 Node 里跑
// 「年龄 tick + 历练结算输入」，断言年龄/危险度行独立成条、不再与历练奇遇/收获混排。
// 用法: node _r257_sem.js <补丁后的 bundle 路径>   （舞台件由 yl_r257_ext.py --out 产出）
const fs = require('fs');
const vm = require('vm');
const bundlePath = process.argv[2];
if (!bundlePath) { console.error('usage: node _r257_sem.js <patched-bundle>'); process.exit(1); }
const src = fs.readFileSync(bundlePath, 'utf8');

let fail = 0;
function chk(c, m) { if (!c) { fail++; console.log('  [FAIL] ' + m); } }
function ok(m) { console.log('  [ok] ' + m); }

// ---------- 静态接线断言（补丁后产物必须长这样） ----------
console.log('=== 0. 静态接线 ===');
chk((src.match(/\/\*YLXW_R257_V2962\*\//g) || []).length === 1, 'r257 幂等标记应恰 1 处');
chk((src.match(/var _yl257r=d;d=function\(_yl257t,_yl257c\)/g) || []).length === 1, 'r257 包装层应恰 1 处');
chk((src.match(/\/\*YLXW_R146_V2919\*\//g) || []).length === 1, 'r146 头应恰 1 处（未被本环改动）');
chk((src.match(/\/\*YLXW_R162_V2924\*\//g) || []).length === 1, 'r162 层应恰 1 处');
chk((src.match(/\/\*YLXW_R161_V2924\*\//g) || []).length === 1, 'r161 层应恰 1 处');
chk((src.match(/年龄 \+/g) || []).length === 2, '年龄日志两个发射点应原样保留（实际 ' + (src.match(/年龄 \+/g) || []).length + '）');
chk((src.match(/_yl146out\.join\("  \\u00b7  "\)/g) || []).length === 1, 'r146 拼条 join 应未动');
chk((src.match(/text:a,type:l,timestamp:Date\.now\(\)}\]\.slice\(-1000\)/g) || []).length === 1, 'addLog 环形缓冲(上限1000)应未动');
const i161 = src.indexOf('/*YLXW_R161_V2924*/'), i257 = src.indexOf('/*YLXW_R257_V2962*/');
chk(i161 >= 0 && i257 > i161, 'r257 层应追加在 r161 层之后（最外层）');
chk(src.slice(i257).startsWith('/*YLXW_R257_V2962*/var _yl257r=d;'), 'r257 层形态正确');
ok('静态接线 10 项');

// ---------- 切出包装链 ----------
function sliceBetween(a, b) {
  const i = src.indexOf(a);
  if (i < 0) throw new Error('missing start ' + a);
  const j = src.indexOf(b, i);
  if (j < 0) throw new Error('missing end ' + b);
  return src.slice(i, j);
}
const chain = sliceBetween('/*YLXW_R146_V2919*/', '$<0?');
console.log('\n=== 包装链长度 ===');
console.log('  r146..r257 chain =', chain.length, 'chars');
chk(chain.indexOf('/*YLXW_R257_V2962*/') > 0, '切出的链应含 r257 层');

// ---------- 最小运行环境 ----------
const emitted = [];                     // _yl146orig 的落点（= 真 addLog 的替身）
const origAddLog = function (t, c) { emitted.push({ text: String(t), type: c || 'normal' }); };
const sandbox = { d: origAddLog, console };
vm.runInNewContext(chain, sandbox, { filename: 'r257chain.js' });
const d = sandbox.d;                    // 链的最外层 = r257 包装
chk(typeof d === 'function', '链求值后 d 应为函数');
chk(sandbox._yl146orig === origAddLog, 'r146 应捕获原始 addLog');

async function settle() { await new Promise(r => setImmediate(r)); }
function reset() { emitted.length = 0; }

// Pc 的年龄 tick 生成器（与产物 @1950134 逐字同构）
function ageTick(h, u) { return '⚠️ 年龄 +' + h.toFixed(2) + ' 岁（危险度：' + (u || '普通') + '）'; }
const AGE_DANGER = ageTick(0.01, '普通');
const STORY = '你遇到了一位前辈修士，对方见你资质不错……';
const HARVEST = '📊 历练收获：修为 +432  · 灵石 +126  · 气血 -112';

(async function main() {

  console.log('\n=== 1. 台账场景复现：年龄 tick + 历练结算 → 拆成 2 条，年龄行独立 ===');
  reset();
  d(AGE_DANGER, 'danger');      // Pc 年龄/危险度行（先进缓冲？不——应旁路直发）
  d(STORY, 'normal');           // 历练奇遇
  d(HARVEST, 'normal');         // 📊 收获摘要（YlxwAdvResultLog）
  await settle();
  chk(emitted.length === 2, '应恰好 2 条日志（实际 ' + emitted.length + '）');
  chk(emitted[0] && emitted[0].text === AGE_DANGER, '第 1 条应为独立年龄行，原文逐字=' + JSON.stringify(emitted[0] && emitted[0].text));
  chk(emitted[0] && emitted[0].type === 'danger', '年龄行应保持 danger 级');
  chk(emitted[0] && emitted[0].text.indexOf('·') < 0, '年龄行不得混入「·」拼接的他人分段');
  chk(emitted[1] && emitted[1].text === STORY + '  ·  ' + HARVEST, '第 2 条应为 story·收获 并排（r146 原语义）：' + JSON.stringify(emitted[1] && emitted[1].text));
  chk(emitted[1] && emitted[1].text.indexOf('年龄') < 0, '历练行不得再混入年龄信息');
  ok('年龄/危险度独立成条 + 奇遇/收获保持一条，互不混排');

  console.log('\n=== 2. 年龄 tick 必须在最前（Pc 先于 story，时间序保持） ===');
  chk(emitted[0] && emitted[0].text === AGE_DANGER && emitted[1] && emitted[1].text.indexOf(STORY) === 0,
      '年龄行应排在历练行之前（emitted[0]=年龄行, emitted[1] 以 story 开头）');

  console.log('\n=== 3. 空缓冲旁路安全：年龄是结算里第 1 个日志时同步直发 ===');
  reset();
  d(AGE_DANGER, 'danger');
  chk(emitted.length === 1, '空缓冲时年龄行应同步独立发出（实际 ' + emitted.length + '）');
  await settle();
  chk(emitted.length === 1, '微任务冲刷不得重复发');
  ok('空缓冲旁路 + 不重复');

  console.log('\n=== 4. 挂起缓冲先冲刷：年龄行不打乱已有日志的先后 ===');
  reset();
  d('清波湖畔遇见行商', 'normal');
  d('⚠️ 年龄 +1.50 岁', 'danger');   // Fg lifespanChange<0 变体（无「危险度」）
  await settle();
  chk(emitted.length === 2, '应为 2 条（实际 ' + emitted.length + '）');
  chk(emitted[0] && emitted[0].text === '清波湖畔遇见行商', '挂起的先冲刷');
  chk(emitted[1] && emitted[1].text === '⚠️ 年龄 +1.50 岁', 'lifespan 减益年龄行也应独立');
  ok('冲刷次序 = 时间序');

  console.log('\n=== 5. 寿元上限增益（✨ 寿元上限 +）保持 r146 并排，不被本环拆出 ===');
  reset();
  d(STORY, 'normal');
  d('✨ 寿元上限 +3.0 年', 'gain');
  await settle();
  chk(emitted.length === 1, '应仍是 1 条并排（实际 ' + emitted.length + '）');
  chk(emitted[0] && emitted[0].text.indexOf(STORY) === 0 && emitted[0].text.indexOf('寿元上限') > 0, '并排内容正确');
  chk(emitted[0] && emitted[0].type === 'gain', '并排行取高优先级 gain（r146 原语义）');
  ok('增益侧不被误拆');

  console.log('\n=== 6. r146 去重与优先级语义未被本环改变（非年龄 danger 仍并排且升 danger） ===');
  reset();
  d('气血大幅下降', 'danger');
  d(STORY, 'normal');
  await settle();
  chk(emitted.length === 1, '非年龄日志仍应并排 1 条（实际 ' + emitted.length + '）');
  chk(emitted[0] && emitted[0].type === 'danger', '并排行类型仍取 danger');
  reset();
  d('同文', 'normal'); d('同文', 'normal'); d('另文', 'normal');
  await settle();
  chk(emitted.length === 1 && emitted[0].text === '同文  ·  另文', '去重语义保持（实际 ' + JSON.stringify(emitted[0] && emitted[0].text) + '）');
  ok('r146 本体语义冻结');

  console.log('\n=== 7. 判据精度：含「年龄」但非「年龄 +」的文案不旁路 ===');
  reset();
  d('你的年龄阅历增长了', 'normal');   // 含「年龄」不含「年龄 +」
  await settle();
  chk(emitted.length === 1, '应走缓冲并排路径（实际 ' + emitted.length + ' 条）');
  ok('判据=「年龄 +」精确前缀语义');

  console.log('\n' + (fail === 0 ? '[ALL PASS] 0 失败' : '[FAIL] ' + fail + ' 项失败'));
  process.exit(fail === 0 ? 0 : 1);
})().catch(e => { console.error('[ERROR]', e); process.exit(1); });
