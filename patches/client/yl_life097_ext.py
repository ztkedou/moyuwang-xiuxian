# -*- coding: utf-8 -*-
r"""
yl_life097_ext.py — 0.9.7 寿元体系改为《凡人修仙传》权威设定

背景（用户 2026-10-01 拍板）
--------------------------------------------------------------------------
用户原话：「寿元改成按《凡人修仙传》权威设定」。炼气修士寿 100 年、筑基 200 年、
金丹 450 年、元婴 1000 年、化神 2000 年、合道 4000 年、长生 8000 年。
基线（0.9.6）里这套数值是另一套（120/300/800/2000/5000/12500/31250），本模块整体替换。

权威数值表（7 档，用户拍板，直接用）
--------------------------------------------------------------------------
  序  0 炼气  1 筑基  2 金丹  3 元婴  4 化神  5 合道  6 长生
  上限 100    200     450     1000    2000    4000    8000

分段规则（用户口述：境界内 1→9 层只走跨阶量的一半，突破下一境界时一次性补上另一半）
--------------------------------------------------------------------------
    half(i) = (TBL[i+1] - TBL[i]) * 0.5          # 跨阶量的一半
    小境界突破（同境界升级，m=false）：_e = half(i) / 8     # 1→9 共 8 步
    大境界突破（进入下一境界，m=true）：_e = half(i)
  ⚠ 两种情况下 i 都是「**突破前所在境界**」的序号 —— 由校验链唯一确定（见下）。

校验链（必须成立，已按 i=当前境界序 逐项验算）
--------------------------------------------------------------------------
    炼气 L1=100  --8×6.25-->  L9=150   --+50-->  筑基 L1=200
    筑基 L1=200  --8×15.625-> L9=325   --+125->  金丹 L1=450
  各境界单步/大跳（half = (next-cur)*0.5）：
    炼气 6.25 / 50 · 筑基 15.625 / 125 · 金丹 34.375 / 275 · 元婴 62.5 / 500
    化神 125  / 1000 · 合道 250  / 2000 · 长生 0 / —（末档无下一境界）
  累计自洽性证明：起始 maxLifespan = Cs[炼气].baseMaxLifespan = 100
    （创建对象 `lifespan:M,maxLifespan:$`，`$=b.baseMaxLifespan`）；
    突破时 `st=Ne+_e`（Ne=g.maxLifespan）为纯累加 ⇒ 每档 L9 = TBL[i] + half(i)，
    大跳补 half(i) 后恰好落到 TBL[i+1]。链条闭合。

本模块动作（7 处表值替换 + 1 处 `_e` 公式替换 + 1 处提示文案取整 + 1 段注入）
--------------------------------------------------------------------------
  patch ① `life097-base-*`：`Cs[realm].baseMaxLifespan` 七档就地替换为新表。
      基线原文（逐档唯一锚点，带右花括号 + 下一境界标签）：
        baseMaxLifespan:120},[ae.Foundation]     → 100
        baseMaxLifespan:300},[ae.GoldenCore]     → 200
        baseMaxLifespan:800},[ae.NascentSoul]    → 450
        baseMaxLifespan:2e3},[ae.SpiritSevering] → 1000
        baseMaxLifespan:5e3},[ae.DaoCombining]   → 2000
        baseMaxLifespan:12500},[ae.LongevityRealm]→ 4000
        baseMaxLifespan:31250}}                  → 8000
      ⚠ 与任务书差异：任务书把「合道」写成 31250、把 12500 漏了。实测基线顺序为
        120, 300, 800, 2e3, 5e3, **12500(合道)**, **31250(长生)**，故旧值清零门禁
        必须把 12500 也纳入（否则 12500 会残留）。
  patch ② `life097-bt-step`：把突破寿元增量整段换成按表算步长。
      基线现状（0.9.6 的 yl_bt096_ext.py 改过之后）：
        if(m)_e=(qe-Ne)*YLXW_BT_BIG_MUL+Math.floor(qe*YLXW_BT_BIG_PCT);
        else{const Yt=Math.floor((qe-Ne)/YLXW_BT_SM_DIV),gt=Math.floor(Math.random()*YLXW_BT_SM_RND)+YLXW_BT_SM_BASE;_e=Yt+gt}
      ⇒ 本模块替换为：`_e=YlxwLifeStep(fe.indexOf(g.realm),m);`
      ⚠ 末尾分号必须保留：原锚点以 `}` 收尾（else 块），其后紧跟 `const st=Ne+_e`；
        替换后若不留 `;`，会得到 `…,m)const st=…` 直接触发语法错误
        （build_v26n.py 的 `_js_syntax_check` 会拦下）。
  patch ③ `life097-toast-int`：突破提示文案把小数取整，避免玩家看到
      「当前寿命：150/106.25 年」或「增加了 6.25 年」。仅改**显示**，不影响累加值：
        旧 `…增加了 ${_e} 年！当前寿命：${Math.floor(ke)}/${st} 年`
        新 `…增加了 ${Math.floor(_e)} 年！当前寿命：${Math.floor(ke)}/${Math.floor(st)} 年`
      ⚠ 任务书限定「只改两处」已由 team-lead 追加为第三处，明确授权；`${Math.floor(ke)}`
        本就在同一模板里，风格保持一致。

「境界序」怎么拿到的（决定集成顺序）
--------------------------------------------------------------------------
  · 突破点位于 `qS({player:t,...})` 的 `handleBreakthrough` 内、`r(g=>{...})` 的 updater 里。
  · 作用域里**没有**现成的「新境界序」；有 `N`（新境界名）、`g.realm`（当前境界名）、
    `m`（是否大境界）、`fe`（境界顺序数组 `[QiRefining..LongevityRealm]`）、
    以及映射 `TS=new Map(fe.map((t,r)=>[t,r]))` / `Xm=t=>TS.get(t)??0`。
  · 关键判定：**i 必须取「突破前所在境界」序号**。取 `fe.indexOf(g.realm)`：
      小境界：g.realm 未变 ⇒ i=当前档；大境界：g.realm=旧境界（如炼气）⇒ i=旧档。
    反证：若按任务书建议对大境界取新境界序 `fe.indexOf(N)`（如炼气→筑基取 i=1），
    则 `_e=half(1)=125`，累计 `150+125=275 ≠ 200`，校验链断裂。
    故**两分支统一用 `fe.indexOf(g.realm)`**（等价于 `Xm(g.realm)`）。
  · ⚠ 与任务书差异：任务书 `Math.round(big?half:half/8)` 会把 6.25 舍成 6，
    L9 变 148、筑基 L1 变 198，校验链同样断裂。故本模块**不做取整**（保留 6.25/15.625）。
    副作用：`_e` 与 `maxLifespan` 内部可能为小数（如 106.25）—— 仅累加值如此，
    **显示层已由 patch ③ 取整**（`${Math.floor(_e)}` / `${Math.floor(st)}`），玩家看不到小数。

依赖与顺序
--------------------------------------------------------------------------
  ⚠ 本模块的 `_e` 锚点是 **yl_bt096_ext.py 改过之后**的形态 ⇒ 集成时本模块必须排在
    `yl_bt096_ext.py` **之后**。两者注入点相同（`function YlxwPanelModal(p) {`），
    bt096 的 `YLXW_BT_*` 常量在本模块替换后不再被 `_e` 引用（残留定义无害）。

未纳入（仅提示，未改动）
--------------------------------------------------------------------------
  · 传承突破路径（`你引动传承之力…` @722192 附近）另有一段 `ge+=…` 寿元累加，
    仍用旧规则（`Ft+floor(Mt.baseMaxLifespan*.1)` / `floor((…)/9)+rand5+1`）。
    任务书只要求改「两处」，故未动；如需统一请另开模块。

锚点纪律（实测计数，基线 index-v296-20261001.js，LEN=2060466）
--------------------------------------------------------------------------
  7 个表值锚点 count 全 = 1；注入锚点 count = 1；旧 `_e` 公式 count = 1；
  突破提示文案锚点 count = 1（模板串含反引号，中文为原样 UTF-8）。
  门禁同时断言「新形态存在 ==1」与「旧形态清零 ==0」。
"""

INJECT_BEFORE_ANCHOR = 'function YlxwPanelModal(p) {'

INJECT_JS = r'''
/* == YL_LIFE_097 == 寿元按《凡人修仙传》权威设定 */
var YLXW_LIFE_TBL = [100, 200, 450, 1000, 2000, 4000, 8000];
function YlxwLifeCur(i) { i = Math.max(0, Math.min(YLXW_LIFE_TBL.length - 1, i)); return YLXW_LIFE_TBL[i]; }
function YlxwLifeNext(i) { return YLXW_LIFE_TBL[Math.min(YLXW_LIFE_TBL.length - 1, Math.max(0, i) + 1)]; }
function YlxwLifeStep(i, big) {
  var cur = YlxwLifeCur(i), nxt = YlxwLifeNext(i), half = (nxt - cur) * 0.5;
  return big ? half : half / 8;
}
'''

# --------------------------------------------------------------------------- 锚点

# ① 境界基础寿命表：7 档（旧值 → 新值），锚点带右花括号 + 下一境界标签，保证唯一
BASE_OLD = [
    'baseMaxLifespan:120},[ae.Foundation]',      # 炼气
    'baseMaxLifespan:300},[ae.GoldenCore]',      # 筑基
    'baseMaxLifespan:800},[ae.NascentSoul]',     # 金丹
    'baseMaxLifespan:2e3},[ae.SpiritSevering]',  # 元婴
    'baseMaxLifespan:5e3},[ae.DaoCombining]',    # 化神
    'baseMaxLifespan:12500},[ae.LongevityRealm]',# 合道（任务书漏列，实测为 12500）
    'baseMaxLifespan:31250}}',                   # 长生
]
BASE_NEW = [
    'baseMaxLifespan:100},[ae.Foundation]',
    'baseMaxLifespan:200},[ae.GoldenCore]',
    'baseMaxLifespan:450},[ae.NascentSoul]',
    'baseMaxLifespan:1000},[ae.SpiritSevering]',
    'baseMaxLifespan:2000},[ae.DaoCombining]',
    'baseMaxLifespan:4000},[ae.LongevityRealm]',
    'baseMaxLifespan:8000}}',
]
BASE_LABEL = ['炼气=100', '筑基=200', '金丹=450', '元婴=1000', '化神=2000', '合道=4000', '长生=8000']

# ② 突破寿元增量：整段换成按表算步长
#    i = fe.indexOf(g.realm) = 突破前所在境界序；m = 是否大境界
BT_OLD = ('if(m)_e=(qe-Ne)*YLXW_BT_BIG_MUL+Math.floor(qe*YLXW_BT_BIG_PCT);'
          'else{const Yt=Math.floor((qe-Ne)/YLXW_BT_SM_DIV),'
          'gt=Math.floor(Math.random()*YLXW_BT_SM_RND)+YLXW_BT_SM_BASE;_e=Yt+gt}')
BT_NEW = '_e=YlxwLifeStep(fe.indexOf(g.realm),m);'

# ③ 突破提示文案：把 ${_e} / ${st} 取整（小数 _e/maxLifespan 不该直接显示给玩家）
#    模板串用反引号；中文在基线里是原样 UTF-8（非 \uXXXX），锚点直接写原样中文
TOAST_OLD = '`✨ 突破成功！你的寿命增加了 ${_e} 年！当前寿命：${Math.floor(ke)}/${st} 年`'
TOAST_NEW = '`✨ 突破成功！你的寿命增加了 ${Math.floor(_e)} 年！当前寿命：${Math.floor(ke)}/${Math.floor(st)} 年`'


def apply(p, ctx):
    # ---- ① 7 档基础寿命表 ----
    for old, new, label in zip(BASE_OLD, BASE_NEW, BASE_LABEL):
        p.replace('life097-base', old, new, expect=1,
                  note='境界基础寿命表：%s（旧值 %s）' % (label, old))

    # ---- ② 突破寿元增量 ----
    p.replace('life097-bt-step', BT_OLD, BT_NEW, expect=1,
              note='突破寿元增量改按权威表算步长：小境界 half/8、大境界 half')

    # ---- ③ 突破提示文案取整 ----
    p.replace('life097-toast-int', TOAST_OLD, TOAST_NEW, expect=1,
              note='突破提示文案：${_e}→${Math.floor(_e)}、${st}→${Math.floor(st)}（避免显示小数）')

    gates = [
        # ---- 注入块 ----
        ('life097·寿元表已注入', 'var YLXW_LIFE_TBL = [100, 200, 450, 1000, 2000, 4000, 8000];', 1, '==', ''),
        ('life097·步长 helper',  'function YlxwLifeStep(i, big)',                               1, '==', ''),
    ]
    # ---- 7 档新值各存在 ==1 / 旧值清零 ==0 ----
    for old, new, label in zip(BASE_OLD, BASE_NEW, BASE_LABEL):
        gates.append(('life097·新表 %s' % label, new, 1, '==', ''))
        gates.append(('life097·旧值清零 %s' % old, old, 0, '==', '旧寿元值必须为 0'))
    # ---- 突破公式 ----
    gates += [
        ('life097·新突破寿元公式',      BT_NEW, 1, '==', '小境界 half/8、大境界 half'),
        ('life097·旧突破寿元公式已清零', BT_OLD, 0, '==', '旧 bt096 常量驱动形态必须为 0'),
        # ---- ③ 提示文案取整 ----
        ('life097·新提示文案已取整',     TOAST_NEW, 1, '==', '${Math.floor(_e)} / ${Math.floor(st)}'),
        ('life097·旧提示文案已清零',     TOAST_OLD, 0, '==', '未取整文案必须为 0'),
        # ---- 冻结：不得误伤别人的面 ----
        ('冻结·寿命上限累加未动',   'st=Ne+_e',                      1, '==', 'maxLifespan 仍为 Ne+_e 累加'),
        ('冻结·当前寿命累加未动',   'ke=(g.lifespan??Ne)+_e',        1, '==', 'lifespan 与 maxLifespan 同步加 _e'),
        ('冻结·境界顺序数组未动',   'const fe=[ae.QiRefining,ae.Foundation,ae.GoldenCore,ae.NascentSoul,ae.SpiritSevering,ae.DaoCombining,ae.LongevityRealm]', 1, '==', 'fe 只读，本模块不动'),
    ]
    return gates
