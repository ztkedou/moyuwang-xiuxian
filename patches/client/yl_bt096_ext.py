# -*- coding: utf-8 -*-
r"""
yl_bt096_ext.py — 0.9.6 突破奖励大幅提升（属性点 + 寿元）

背景（用户 2026-10-01 19:43）
--------------------------------------------------------------------------
用户贴出实测日志：
    ✨ 突破成功！获得 1 点可分配属性点！
    ✨ 突破成功！你的寿命增加了 1 年！当前寿命：16/121 年
原话：「突破增加的属性点和寿命都大幅度提升，因为现在升级较难，寿命容易耗尽」

排查（逐条读码取证）
--------------------------------------------------------------------------
① 属性点：`Ae=F0(m,Ee)`，而
       F0=(t,r,a=0)=>{Xm(r);const l=x3[r],d=Math.min(t?2:1,l-a);return Math.max(0,d)}
   同文件里**明明白白有一张按境界的属性点表**：
       x3={炼气:5, 筑基:10, 金丹:20, 元婴:30, 化神:40, 合道:50, 长生:60}
   但 `Math.min(t?2:1, x3[r])` 把它**整个钳死**：小境界恒 1 点、大境界恒 2 点。
   ⇒ **`x3` 表从没被真正用上**（`Xm(r)` 的返回值还被丢弃）。这基本可以判定是上游的实现缺陷。
② 寿元：`_e` 的增量
       if(m) _e = qe-Ne + floor(qe*.1);                                  // 大境界
       else { Yt=floor((qe-Ne)/9); gt=floor(random()*5)+1; _e=Yt+gt; }    // 小境界
   同境界内 `qe===Ne`（`qe=Cs[新境界].baseMaxLifespan`，境界没变就相等）⇒ 小境界实际只给
   `floor(0/9)+1..5` = **1~5 年**，正是用户截图里的「增加了 1 年」。

本模块动作（2 处就地替换 + 1 段注入）
--------------------------------------------------------------------------
  patch ① `bt096-pt`：把 `F0` 的钳制上限换成常量 `YLXW_BT_PT_SMALL / YLXW_BT_PT_BIG`，
      于是**那张一直没生效的 `x3` 表终于起作用**（`min(8, 5..60)` / `min(20, 5..60)`）。
  patch ② `bt096-life`：小境界 / 大境界的寿元增量都改成由常量驱动（见下）。

数值（全部可调，改常量即可）
--------------------------------------------------------------------------
  YLXW_BT_PT_SMALL = 8     小境界属性点上限（原 1）⇒ 炼气 5 点、筑基及以上 8 点
  YLXW_BT_PT_BIG   = 20    大境界属性点上限（原 2）⇒ 筑基 10、金丹 20、元婴及以上 20
  YLXW_BT_SM_DIV   = 2     小境界：`floor((qe-Ne)/DIV)`（原 9）
  YLXW_BT_SM_BASE  = 8     小境界保底年数（原 1）
  YLXW_BT_SM_RND   = 13    小境界随机区间（原 5）⇒ 实际 **8 ~ 20 年**（原 1 ~ 5）
  YLXW_BT_BIG_MUL  = 2     大境界：`(qe-Ne) × MUL`（原 ×1）
  YLXW_BT_BIG_PCT  = .3    大境界：`+ floor(qe × PCT)`（原 .1）
      ⇒ 炼气→筑基：原 `180+30=210` → 新 `360+90=**450**`

锚点纪律：两处锚点实测 count==1；GATES 同时断言新形态存在与旧形态清零。
"""

INJECT_BEFORE_ANCHOR = 'function YlxwPanelModal(p) {'

INJECT_JS = r'''
/* == YL_BT_096 == 突破奖励（属性点 / 寿元）大幅提升 */
var YLXW_BT_PT_SMALL = 8;    /* 小境界属性点上限（原 1） */
var YLXW_BT_PT_BIG = 20;     /* 大境界属性点上限（原 2） */
var YLXW_BT_SM_DIV = 2;      /* 小境界寿元：floor((qe-Ne)/DIV)（原 9） */
var YLXW_BT_SM_BASE = 8;     /* 小境界寿元保底（原 1） */
var YLXW_BT_SM_RND = 13;     /* 小境界寿元随机区间（原 5） */
var YLXW_BT_BIG_MUL = 2;     /* 大境界寿元：(qe-Ne)×MUL（原 1） */
var YLXW_BT_BIG_PCT = .3;    /* 大境界寿元：+floor(qe×PCT)（原 .1） */
'''

# --------------------------------------------------------------------------- 锚点

# ① 属性点：把写死的 2/1 换成常量（让 x3 表终于生效）
PT_OLD = 'F0=(t,r,a=0)=>{Xm(r);const l=x3[r],d=Math.min(t?2:1,l-a);return Math.max(0,d)}'
PT_NEW = 'F0=(t,r,a=0)=>{Xm(r);const l=x3[r],d=Math.min(t?YLXW_BT_PT_BIG:YLXW_BT_PT_SMALL,l-a);return Math.max(0,d)}'

# ② 寿元增量：大 / 小境界都改成常量驱动
LIFE_OLD = ('if(m)_e=qe-Ne+Math.floor(qe*.1);'
            'else{const Yt=Math.floor((qe-Ne)/9),gt=Math.floor(Math.random()*5)+1;_e=Yt+gt}')
LIFE_NEW = ('if(m)_e=(qe-Ne)*YLXW_BT_BIG_MUL+Math.floor(qe*YLXW_BT_BIG_PCT);'
            'else{const Yt=Math.floor((qe-Ne)/YLXW_BT_SM_DIV),'
            'gt=Math.floor(Math.random()*YLXW_BT_SM_RND)+YLXW_BT_SM_BASE;_e=Yt+gt}')

# ③ 每点属性加成表：攻击 / 防御 / 气血（体魄附带的血一起抬，否则它相对更废）
#    ⚠ 这里**必须内联数字**：注入锚点（`function YlxwPanelModal(p) {`）在 `Ps` 定义**之后**
#      （锚点 @1446129 vs Ps @716068），对象字面量在模块加载时就求值 ⇒ 引用注入常量会拿到 undefined。
#    数值：攻击 5→15（×3）、防御 3→10（×3.33）、气血 20→60（×3）、体魄附带气血 10→30（×3）
PTGAIN_OLD = 'Ps={attack:5,defense:3,hp:20,spirit:3,physique:3,physiqueHp:10,speed:2}'
PTGAIN_NEW = 'Ps={attack:15,defense:10,hp:60,spirit:3,physique:3,physiqueHp:30,speed:2}'


def apply(p, ctx):
    p.replace('bt096-pt', PT_OLD, PT_NEW, expect=1,
              note='突破属性点上限 1/2 → YLXW_BT_PT_SMALL/BIG（让一直没生效的 x3 境界表起作用）')
    p.replace('bt096-life', LIFE_OLD, LIFE_NEW, expect=1,
              note='突破寿元增量改常量驱动：小境界 8~20 年、大境界 ×2 + qe×.3')
    p.replace('bt096-ptgain', PTGAIN_OLD, PTGAIN_NEW, expect=1,
              note='每点属性加成：攻击 5→15、防御 3→10、气血 20→60、体魄附带气血 10→30')

    return [
        # ---- ③ 每点加成 ----
        # ★ 2026-10-01 0.9.7：attr097 把 hp 提到 100 / physiqueHp 提到 50 ⇒ bt096 的"最终形态"断言移交给 attr097，
        #   本模块只断言"它确实被接管了"（旧形态 0），避免两个模块抢同一个终稿字面量。
        ('bt096·每点加成已被 attr097 接管', PTGAIN_NEW, 0, '==', '最终形态由 attr097 断言（hp:100 / physiqueHp:50）'),
        ('bt096·旧每点加成已清零', PTGAIN_OLD, 0, '==', ''),
        # ---- 注入块 ----
        ('bt096·属性点常量已注入', 'var YLXW_BT_PT_SMALL = 8;',       1, '==', ''),
        ('bt096·寿元常量已注入',   'var YLXW_BT_SM_DIV = 2;',         1, '==', ''),
        # ---- ① 属性点 ----
        ('bt096·属性点上限已接常量', 'd=Math.min(t?YLXW_BT_PT_BIG:YLXW_BT_PT_SMALL,l-a)', 1, '==', ''),
        ('bt096·旧钳制已清零',       PT_OLD,                           0, '==', '旧形态必须为 0'),
        # ---- ② 寿元 ----
        # ★ 2026-10-01 0.9.7：life097 整体替换了 bt096 的 _e 公式（改为按境界查表）⇒ 本模块不再断言该形态。
        ('bt096·大境界寿元已被 life097 接管', '(qe-Ne)*YLXW_BT_BIG_MUL', 0, '==', '0.9.7 life097 用 YlxwLifeStep 取代'),
        ('bt096·小境界寿元已被 life097 接管', 'Math.random()*YLXW_BT_SM_RND', 0, '==', '0.9.7 life097 用 YlxwLifeStep 取代'),
        ('bt096·旧寿元形态已清零',   LIFE_OLD,                         0, '==', ''),
        # ---- 冻结：别动别人的面 ----
        ('冻结·境界寿元表仍在',      'x3={[ae.QiRefining]:5,[ae.Foundation]:10,[ae.GoldenCore]:20,[ae.NascentSoul]:30,[ae.SpiritSevering]:40,[ae.DaoCombining]:50,[ae.LongevityRealm]:60}', 1, '==', 'x3 表本身不动，只是让它生效'),
        ('冻结·突破提示文案未动',    '✨ 突破成功！你的寿命增加了 ', 1, '==', '基线为原样中文模板字符串'),
        ('冻结·寿命上限累加未动',    'st=Ne+_e',                       1, '==', 'maxLifespan 与 lifespan 同步加 _e'),
    ]
