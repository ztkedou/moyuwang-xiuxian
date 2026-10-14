// R-252 年龄制核心算法的运行时语义验证（Node，不依赖浏览器）
// 抽出注入块里的算法，用真值表验证：真实死线恒落在展示区间内。
var YLXW_AGE_MIN = 0.9;
var YLXW_LIFE_TBL = [100, 200, 450, 1000, 2000, 4000, 8000];
var fe = ["炼气期", "筑基期", "金丹期", "元婴期", "化神期", "合道期", "长生境"];
function YlxwLifeCur(i) { i = Math.max(0, Math.min(YLXW_LIFE_TBL.length - 1, i)); return YLXW_LIFE_TBL[i]; }
function YlxwLifeNext(i) { return YLXW_LIFE_TBL[Math.min(YLXW_LIFE_TBL.length - 1, Math.max(0, i) + 1)]; }
function YlxwAgeRoll() { return YLXW_AGE_MIN + Math.random() * (1 - YLXW_AGE_MIN); }
function YlxwLifeUpper(realm, lv) {
  var i = fe.indexOf(realm); if (i < 0) i = 0;
  var L = Math.floor(Number(lv)); if (!isFinite(L) || L < 1) L = 1; if (L > 9) L = 9;
  var cur = YlxwLifeCur(i), nxt = YlxwLifeNext(i);
  return cur + (L - 1) * ((nxt - cur) / 16);
}
function YlxwLifeBonus(p) { var n = Number(p && p.lifeBonus); return isFinite(n) ? n : 0; }
function YlxwLifeShow(p) { if (!p) return 100; return YlxwLifeUpper(p.realm, p.realmLevel) + YlxwLifeBonus(p); }
function YlxwLifeDeathLine(p) {
  if (!p) return 100;
  var r = Number(p.lifeRatio);
  if (!isFinite(r) || r < YLXW_AGE_MIN || r > 1) r = 1;
  return r * YlxwLifeUpper(p.realm, p.realmLevel) + YlxwLifeBonus(p);
}
function YlxwLifeRange(upper) {
  var u = Number(upper); if (!isFinite(u) || u < 1) u = 1;
  var lo = Math.floor(u * YLXW_AGE_MIN); if (lo < 0) lo = 0;
  var hi = Math.ceil(u); if (hi < lo) hi = lo;
  return [lo, hi];
}
function YlxwLifeMigrate(t) {
  if (!t) return { age: 0, lifeRatio: 1, lifeBonus: 0, maxLifespan: 100 };
  var n = YlxwLifeBonus(t), r = Number(t.lifeRatio);
  if (!isFinite(r) || r < YLXW_AGE_MIN || r > 1) r = 1;
  var a = Number(t.age);
  if (isFinite(a) && t.age !== null && t.age !== void 0) {
    var d0 = Number(t.maxLifespan);
    if (!isFinite(d0)) d0 = YlxwLifeDeathLine({ realm: t.realm, realmLevel: t.realmLevel, lifeRatio: r, lifeBonus: n });
    return { age: a, lifeRatio: r, lifeBonus: n, maxLifespan: d0 };
  }
  var base = YlxwLifeUpper(t.realm, t.realmLevel);
  var old = Number(t.maxLifespan); if (!isFinite(old) || old <= 0) old = base;
  var left = Number(t.lifespan); if (!isFinite(left)) left = old;
  var age = old - left; if (age < 0) age = 0;
  var ratio = old / base;
  if (!isFinite(ratio) || ratio < YLXW_AGE_MIN) ratio = YLXW_AGE_MIN; if (ratio > 1) ratio = 1;
  var bonus = old - ratio * base; if (bonus < 0) bonus = 0;
  return { age: age, lifeRatio: ratio, lifeBonus: bonus, maxLifespan: ratio * base + bonus };
}

var fail = 0;
function chk(cond, msg) { if (!cond) { fail++; console.log('  [FAIL] ' + msg); } }

// ---- 1. 区间表逐大境界核对（用户裁定：上限 × 0.9）
console.log('=== 1. 各大境界 1 层 / 9 层区间表 ===');
var expect1 = { '炼气期': [90, 100], '筑基期': [180, 200], '金丹期': [405, 450],
                '元婴期': [900, 1000], '化神期': [1800, 2000], '合道期': [3600, 4000],
                '长生境': [7200, 8000] };
fe.forEach(function (rl) {
  var u1 = YlxwLifeUpper(rl, 1), r1 = YlxwLifeRange(u1);
  var u9 = YlxwLifeUpper(rl, 9), r9 = YlxwLifeRange(u9);
  var e = expect1[rl];
  chk(r1[0] === e[0] && r1[1] === e[1], rl + ' 1层区间 ' + r1 + ' 应为 ' + e);
  console.log('  ' + rl + '  1层 ' + r1[0] + '-' + r1[1] + '   9层 ' + r9[0] + '-' + r9[1]);
});

// ---- 2. 小境界步长 × 8 + 大境界步长 = 区间差（完全补齐）
console.log('=== 2. 成长自洽：8×小步 + 1×大步 = 相邻大境界上限差 ===');
for (var i = 0; i < fe.length - 1; i++) {
  var cur = YlxwLifeCur(i), nxt = YlxwLifeNext(i);
  var small = (nxt - cur) / 16, big = (nxt - cur) / 2;
  chk(Math.abs(8 * small + big - (nxt - cur)) < 1e-9, fe[i] + ' 步长不闭合');
  chk(Math.abs(YlxwLifeUpper(fe[i], 9) - (cur + 8 * small)) < 1e-9, fe[i] + ' 9层上限不符');
  chk(Math.abs(YlxwLifeUpper(fe[i + 1], 1) - nxt) < 1e-9, fe[i + 1] + ' 1层上限不符');
}

// ---- 3. 隐藏死线恒落在展示区间内（1000 组随机）
console.log('=== 3. 死线 ∈ 展示区间（随机 1000 组 × 全部境界/层数）===');
for (var n = 0; n < 1000; n++) {
  var ri = Math.floor(Math.random() * fe.length), lv = 1 + Math.floor(Math.random() * 9);
  var ratio = YlxwAgeRoll();
  var bonus = Math.floor(Math.random() * 2000);
  var p = { realm: fe[ri], realmLevel: lv, lifeRatio: ratio, lifeBonus: bonus };
  var dl = YlxwLifeDeathLine(p), rg = YlxwLifeRange(YlxwLifeShow(p));
  if (!(dl >= rg[0] - 1e-9 && dl <= rg[1] + 1e-9)) {
    fail++;
    console.log('  [FAIL] ' + fe[ri] + ' ' + lv + '层 ratio=' + ratio.toFixed(4) +
                ' bonus=' + bonus + ' deathLine=' + dl.toFixed(2) + ' range=' + rg);
    break;
  }
}
console.log('  1000 组随机全部通过（无泄露）');

// ---- 4. 建号：age 0，死线落在区间内
console.log('=== 4. 建号 ===');
for (var t2 = 0; t2 < 200; t2++) {
  var base = 100, M = base * YlxwAgeRoll();
  var np = { age: 0, maxLifespan: M, lifeRatio: M / base || 1, lifeBonus: 0,
             realm: '炼气期', realmLevel: 1 };
  chk(np.age === 0, '建号年龄应为 0');
  var dl2 = YlxwLifeDeathLine(np), rg2 = YlxwLifeRange(YlxwLifeShow(np));
  chk(dl2 >= rg2[0] && dl2 <= rg2[1], '建号死线越界 ' + dl2 + ' ' + rg2);
  chk(Math.abs(np.maxLifespan - dl2) < 1e-9, '建号 maxLifespan 应等于死线');
}

// ---- 5. 突破：age 不变、死线按比例增长、恒不越界
console.log('=== 5. 突破 9 层 → 下一大境界 ===');
for (var t3 = 0; t3 < 300; t3++) {
  var ri3 = Math.floor(Math.random() * (fe.length - 1));
  var ratio3 = YlxwAgeRoll();
  var bonus3 = Math.floor(Math.random() * 500);
  var g = { realm: fe[ri3], realmLevel: 9, lifeRatio: ratio3, lifeBonus: bonus3,
            age: Math.random() * 100 };
  var Ne = YlxwLifeDeathLine(g);
  var step = (YlxwLifeNext(ri3) - YlxwLifeCur(ri3)) / 2;
  var st = Ne + ratio3 * step;
  var g2 = { realm: fe[ri3 + 1], realmLevel: 1, lifeRatio: ratio3, lifeBonus: bonus3, age: g.age };
  var dl3 = YlxwLifeDeathLine(g2), rg3 = YlxwLifeRange(YlxwLifeShow(g2));
  chk(Math.abs(dl3 - st) < 1e-9, '突破死线应与公式一致');
  chk(dl3 >= rg3[0] && dl3 <= rg3[1], '突破后死线越界 ' + dl3 + ' ' + rg3);
}

// ---- 6. 老存档迁移：死线精确保留
console.log('=== 6. 老存档迁移（镜像等价 + 死线不变）===');
// 合法存档的不变量：旧 maxLifespan == U_base(realm,lv) + 丹药加成（因旧突破步长与 U_base 同源）
// ⇒ ratio = old/base ∈ [1, ...] → clamp 到 1；bonus = old - base ≥ 0 → 死线逐位保留。
var cases = [
  { maxLifespan: 100, lifespan: 60, realm: '炼气期', realmLevel: 1, exp: '满血' },
  { maxLifespan: 112.5, lifespan: 5, realm: '炼气期', realmLevel: 3, exp: '垂死' },
  { maxLifespan: 150, lifespan: 150, realm: '炼气期', realmLevel: 9, exp: '满寿' },
  { maxLifespan: 200, lifespan: 0.5, realm: '筑基期', realmLevel: 1, exp: '将尽' },
  { maxLifespan: 587.5, lifespan: 300, realm: '金丹期', realmLevel: 5, exp: '中期' },
  { maxLifespan: 8000, lifespan: 4000, realm: '长生境', realmLevel: 9, exp: '顶格' },
  { maxLifespan: 106.25, lifespan: 100, realm: '炼气期', realmLevel: 2, exp: '刚突破' },
  { maxLifespan: 130, lifespan: 20, realm: '炼气期', realmLevel: 4, exp: '含丹药加成' },
];
cases.forEach(function (c) {
  var m = YlxwLifeMigrate(c);
  chk(Math.abs(m.maxLifespan - c.maxLifespan) < 1e-9,
      '迁移后死线应精确等于旧 maxLifespan: ' + m.maxLifespan + ' vs ' + c.maxLifespan);
  chk(Math.abs(m.age - (c.maxLifespan - c.lifespan)) < 1e-9, '年龄应等于旧已用寿命');
  var rgm = YlxwLifeRange(YlxwLifeShow(Object.assign({}, c, m)));
  chk(m.maxLifespan >= rgm[0] && m.maxLifespan <= rgm[1],
      '迁移后死线应落在展示区间: ' + m.maxLifespan + ' ' + rgm);
  console.log('  ' + c.exp + ' 旧 ' + c.lifespan + '/' + c.maxLifespan +
              ' → age=' + m.age.toFixed(1) + ' ratio=' + m.lifeRatio.toFixed(4) +
              ' bonus=' + m.lifeBonus.toFixed(2) + ' 区间=' + rgm[0] + '-' + rgm[1]);
});

// 边界：maxLifespan 低于 0.9×U_base（合法存档不可达，仅防御脏数据）
// 不变量：死线只能被抬高（对玩家有利），绝不缩短、绝不猝死
console.log('=== 6b. 脏数据边界（低于区间下限）===');
[{ maxLifespan: 40, lifespan: 10, realm: '炼气期', realmLevel: 1 },
 { maxLifespan: 100, lifespan: 5, realm: '炼气期', realmLevel: 3 }].forEach(function (c) {
  var m = YlxwLifeMigrate(c);
  var rgm = YlxwLifeRange(YlxwLifeShow(Object.assign({}, c, m)));
  chk(m.maxLifespan >= c.maxLifespan, '死线不得被缩短');
  chk(m.maxLifespan >= rgm[0] && m.maxLifespan <= rgm[1], '死线仍须落在区间内');
  chk(m.age <= m.maxLifespan, '年龄不得超过死线（否则立刻猝死）');
  console.log('  脏 ' + c.lifespan + '/' + c.maxLifespan + ' (' + c.realm + c.realmLevel +
              '层) → 死线 ' + m.maxLifespan.toFixed(2) + ' 区间=' + rgm[0] + '-' + rgm[1] +
              ' age=' + m.age.toFixed(1) + '（抬高，不猝死）');
});

// ---- 7. 迁移幂等
console.log('=== 7. 迁移幂等 ===');
var once = YlxwLifeMigrate(cases[0]);
var twice = YlxwLifeMigrate(Object.assign({}, cases[0], once));
chk(Math.abs(once.age - twice.age) < 1e-9 && Math.abs(once.maxLifespan - twice.maxLifespan) < 1e-9,
    '二次迁移应恒等');

// ---- 8. 加寿丹 / 减年龄丹
console.log('=== 8. 丹药 ===');
var pill = { realm: '炼气期', realmLevel: 1, lifeRatio: 0.95, lifeBonus: 0, age: 50 };
pill.lifeBonus += 3;
chk(YlxwLifeDeathLine(pill) === 0.95 * 100 + 3, '加寿丹应抬死线');
chk(YlxwLifeRange(YlxwLifeShow(pill))[1] === 103, '加寿丹应抬展示上限');
pill.age = Math.max(0, pill.age - 3);
chk(pill.age === 47, '减年龄丹应降年龄');

console.log('\n' + (fail === 0 ? '[ALL PASS] 0 失败' : '[FAIL] ' + fail + ' 项失败'));
process.exit(fail === 0 ? 0 : 1);
