# -*- coding: utf-8 -*-
r"""
yl_063_ext.py — R-063 秘境：**roguelike 地宫单独算上限 + 层数境界门根治**

需求原文（需求台账_进行中.md L29，R-063，附图列为空）
--------------------------------------------------------------------------
  「roguelinke这个单独算上限数字吧。现有的上限变成普通点选秘境次数。
    roguelinke这个模式最低等级一天3次，其他相应增加。
    还有你看一下这个层数的重置方式，因为我重开游戏了但是层数还在元婴，现在没法测试。」

拆成三件事
--------------------------------------------------------------------------
  ① roguelike 地宫的每日上限**单独算**（独立账本，与普通点选不再共用计数）
  ② 现有上限表 [10,12,14,15,17,18,20]（R-032 用户拍板）归**普通点选**秘境；
     roguelike 新表**最低等级（炼气期）3 次/日、其他境界相应增加**
  ③ 「层数重置」报障：重开游戏层数还卡在元婴 ⇒ 真根因见下（不是持久化，是随机门）

③ 的根因（逐字实证，bundle @1874684 / @470642，非猜测）
--------------------------------------------------------------------------
  roguelike 进入回调 T：
      const W=U3(),z=fe.indexOf(a.realm),J=Math.max(0,Math.ceil(W.totalFloors/2)-3);
      if(z<J){c("🚫 此地宫深达 N 层，需境界【"+fe[J]+"】方可进入，你的境界不足。","danger");return}
  · U3()（@470642）每次进入**随机**掷层数：xg=5、z3=12 ⇒ totalFloors ∈ [5,12]；
  · 境界门 J=ceil(层数/2)-3：5~6 层→炼气、7~8→筑基、9~10→金丹、**11~12→元婴期**；
  · 层数**根本不持久化**（yk 组件 useState(null)，开弹窗即重置；全产物 currentFloor
    10 处全在 U3/yk 内存态）——玩家感知的「重开游戏层数还在元婴」实为：低境界测试号
    每次进入都有 25%（金丹 50%、炼气 75% 概率撞 9~12 层）被「需境界【元婴期】」
    **整单拒绝**，重开游戏毫无帮助（随机按次重掷，不是跨会话状态）。
  ⇒ 修根因：**地宫深度随境界封顶**——U3 加层数上限参数，调用点按玩家境界封顶
     （炼气 ≤6 层、筑基 ≤8、金丹 ≤10、元婴+ ≤12=z3），J 门从此不可能拒绝任何人；
     `if(z<J)` 原样保留作死代码保险（dungeon085 门禁 `if(z<J){c(` ==1 不破坏）。

①+② 的拆分设计（服务端权威账本分账，客户端只是镜像）
--------------------------------------------------------------------------
  现状（0.8.5 dg085 + R-032 dungeon2 之后）：两条入口（经典秘境 XM.handleEnterRealm
  与地宫 yk.T）都打 `YlxwDungeonEntryGate()` → 同一张 dungeon_tracker.count、
  同一个按境界 cap 表 [10..20]。
  拆分：
    · 服务端（srv_patch_063.py）：dungeon_tracker 加 rogue_count / rogue_last_ts 两列
      （safeAddColumn 幂等加列，house 惯例）；/api/dungeon/entry 读 body.mode==="rogue"
      走独立判定/落库/403；/api/dungeon/status 增发 rogueCount/rogueCap/rogueRemaining/
      rogueCdLeftMs/rogueCanEnter。普通点选路径**一个字节不动**。
    · 客户端（本模块）：rogue 上限表 YLXW_DG_ROGUE_CAP=[3,5,7,8,10,11,13]
      （炼气 3 → 长生 13；递增节奏沿用普通表 +2,+2,+1,+2,+1,+2、总 +10，基座 3，
      任何境界都严格低于普通点选——roguelike 单轮收益更高，次数保持更稀缺，见拍板文件）。
      YlxwDgCap() 六个调用点（dungeon2 门禁钉死恒 6）一个不动，只改**函数体**读新表；
      原 `var YLXW_DG_CAP = [10,...]` 声明原样保留（= 普通点选表的服务端同源记录，
      dungeon2/R-062 门禁都钉它 ==1，弹窗 cap 显示本就走服务端 status.cap）。
      计数分账：入口处设 YLXW_DG_ENTRY_MODE（两个调用点各自先置 0/1 再 await gate，
      同步段无 await ⇒ 不可能串号），gate 响应回灌按模式分流（rogue → window.__ylDg，
      普通 → YLXW_DG_NORM_CNT，不再互相污染面板计数）。

★ 为什么不改这些被钉死的面（跨模块冻结盘点，全部逐字核过）
--------------------------------------------------------------------------
  · `=await YlxwDungeonEntryGate();` 恒 2 —— dungeon085 + v2811a 双门禁（模式改在
    调用点**前面**设变量，调用串原样保留）。
  · `function YlxwDungeonMarkLocal(count) {` 签名 ==1 —— dungeon085 + v2811a；
    只改函数体（模式分流），`cd: YlxwDgCdUntil() };` ==1（dungeon2）保留在 rogue 分支内。
  · `YLXW_DG_SRV_CD = Number(s.cdLeftMs) || 0; YlxwDungeonMarkLocal(s.count);` ==1
    —— dungeon2 门禁整句钉死 ⇒ 普通镜像前**插入** `YLXW_DG_ENTRY_MODE = 0;`、
    rogue 镜像**追加**在其后，钉死串原样保留。
  · `function ylDgGate(){...}` 函数体 ==1 —— dungeon085+dungeon2；不动。
  · `var YLXW_DG_CAP = [10, 12, 14, 15, 17, 18, 20];` ==1 —— dungeon2 + R-062（后者
    明确「上限表是 R-063 的活，别越界」）；本模块正是 R-063，改的是**函数体**不是表。
  · `var i = fe.indexOf(realm);` ==1 —— dungeon2 门禁；E7 新函数体**原样保留这行**。
  · `YlxwDgCap(a&&a.realm)` 恒 6 —— R-062 门禁；六个调用点一个不动。
  · `if(z<J){c(` ==1 —— dungeon085；保留作死代码保险。
  · `cd:Date.now()+YLXW_DG_CD_MS}}catch(KS){}` ==1 —— dungeon2 + R-062；rogue 本地
    冷却写入不动（15 分钟值来自常量，R-062 的活）。
  · R-062 面（order-safe 冻结）：`Ym(oe,…,YLXW_STONE_MUL_ADV)` 内层调用 ==1、
    `*1.63666;`（roguelike G3 收益）==1、秘境深处 SR 站 ==1 —— 收益/冷却都不归 R-063。
  · 冷却展示行（`…冷却 15 分钟…` 与层数境界说明同行）：本模块**不碰该行**（cap 值经
    E7 函数体自动生效），R-062 只动其中 CD 子串 ⇒ 无同行冲突。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 注入块纯 ASCII（zh() 后自检无非 ASCII）；不含 iframe/postMessage/XMLHttpRequest/
    auth_token/X-YL-；无 fetch（入口走 dg085 既有原始 fetch，本模块只加 body 字段）。
  · 每处 replace 带 expect= 精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件 + srv_patch_063.py；不改 build_v26n.py / build/assets/* /
    srv/index_v28.ts / localtest/* / deploy_v28/* / 任何已有模块。
  · 装配序：必须在 yl_dungeon085_ext / yl_dungeon2_ext / yl_v2811a 之后（锚点来自
    它们的产物形态）；与 R-062 无先后依赖（锚点零交集，冻结面全部 order-safe）。
"""

import re

# --------------------------------------------------------------------------- 注入块（纯 ASCII）

INJECT_JS = r'''
/* ===== yl-R063: roguelike dungeon gets its own daily ledger + cap table =====
   User R-063: count the roguelike mode separately; the old [10..20] table
   stays with the popup realm; roguelike starts at 3/day for the lowest realm.
   Split summary:
     - server (srv_patch_063.py) tracks rogue_count/rogue_last_ts separately
       and reports rogueCount/rogueCap/rogueCdLeftMs on /dungeon/status;
     - entry posts carry mode:"rogue"|"normal" (mode set right before each
       await-gate call site, synchronous segment, no interleave possible);
     - count mirroring is mode-aware: rogue -> window.__ylDg (rogue panel),
       popup -> YLXW_DG_NORM_CNT (popup panel reads server status directly);
     - rogue cap by realm lives in YLXW_DG_ROGUE_CAP, consumed inside the
       YlxwDgCap() body (its 6 call sites and the old [10..20] var stay put). */
var YLXW_DG_ENTRY_MODE = 0;   /* 0 = popup realm entry, 1 = roguelike dungeon entry */
var YLXW_DG_NORM_CNT = 0;     /* popup realm daily count mirror (display comes from server status) */
var YLXW_DG_SRV_ROGUE_CD = 0; /* roguelike cooldown left (ms), from server status rogueCdLeftMs */
var YLXW_DG_ROGUE_CAP = [3, 5, 7, 8, 10, 11, 13]; /* rogue daily cap by realm: QiRefining 3 -> Longevity 13 */
'''

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# --------------------------------------------------------------------------- 锚点（全部实测 count==1 @ build/assets/index-v28116-20261001.js）

# —— 注入锚：dungeon2 助手区（与 dg085/dungeon2 注入同作用域，var 声明在求值期即赋值）——
INJECT_ANCHOR = 'async function YlxwDungeonStatusSync() {'

# —— E1 地宫入口调用点：进门前置 rogue 模式（调用串原样保留，v2811a 钉 ==2）——
E1_OLD = 'return}const _ylg=await YlxwDungeonEntryGate();if(!_ylg.ok){c(_ylg.msg,"danger");return}'
E1_NEW = ('return}YLXW_DG_ENTRY_MODE=1;'
          'const _ylg=await YlxwDungeonEntryGate();if(!_ylg.ok){c(_ylg.msg,"danger");return}')

# —— E2 经典秘境入口调用点：进门前置普通模式 ——
E2_OLD = 'return!1}const _ylg=await YlxwDungeonEntryGate();if(!_ylg.ok){a(_ylg.msg,"danger");return!1}'
E2_NEW = ('return!1}YLXW_DG_ENTRY_MODE=0;'
          'const _ylg=await YlxwDungeonEntryGate();if(!_ylg.ok){a(_ylg.msg,"danger");return!1}')

# —— E3 入口上报带 mode（服务端按 mode 分账；fetch 行原样保留，dg085 钉 ==1）——
E3_OLD = ('headers: Object.assign({ "Content-Type": "application/json" }, jo()),\n'
          '    body: "{}"\n'
          '  });')
E3_NEW = ('headers: Object.assign({ "Content-Type": "application/json" }, jo()),\n'
          '    body: JSON.stringify({ mode: YLXW_DG_ENTRY_MODE ? "rogue" : "normal" })\n'
          '  });')

# —— E4 计数回灌按模式分流（函数签名不动；rogue 分支原样保留 dungeon2 钉死的 cd 串）——
E4_OLD = 'window.__ylDg = { d: YlxwDungeonToday(), cnt: Math.floor(n), cd: YlxwDgCdUntil() };'
E4_NEW = ('if (YLXW_DG_ENTRY_MODE) '
          '{ window.__ylDg = { d: YlxwDungeonToday(), cnt: Math.floor(n), cd: YlxwDgCdUntil() }; } '
          'else { YLXW_DG_NORM_CNT = Math.floor(n); }')

# —— E5 StatusSync：普通镜像前置 mode=0（dungeon2 钉死串保真），追加 rogue 镜像 ——
E5_OLD = ('if (s && typeof s.count === "number") '
          '{ YLXW_DG_SRV_CD = Number(s.cdLeftMs) || 0; YlxwDungeonMarkLocal(s.count); }')
E5_NEW = ('if (s && typeof s.count === "number") '
          '{ YLXW_DG_ENTRY_MODE = 0; YLXW_DG_SRV_CD = Number(s.cdLeftMs) || 0; YlxwDungeonMarkLocal(s.count); }\n'
          '    if (s && typeof s.rogueCount === "number") '
          '{ YLXW_DG_SRV_ROGUE_CD = Number(s.rogueCdLeftMs) || 0; YLXW_DG_ENTRY_MODE = 1; '
          'YlxwDungeonMarkLocal(s.rogueCount); YLXW_DG_ENTRY_MODE = 0; }')

# —— E6 rogue 冷却取服务端 rogueCdLeftMs（YlxwDgCdUntil 只被 rogue 分支调用；取较晚者口径不动）——
E6_OLD = 'var srv = Number(YLXW_DG_SRV_CD) > 0 ? Date.now() + Number(YLXW_DG_SRV_CD) : 0;'
E6_NEW = 'var srv = Number(YLXW_DG_SRV_ROGUE_CD) > 0 ? Date.now() + Number(YLXW_DG_SRV_ROGUE_CD) : 0;'

# —— E7 上限表换血：函数体改读 ROGUE 表（签名行 + `var i = fe.indexOf(realm);` 原样保留）——
E7_OLD = ('function YlxwDgCap(realm) {\n'
          '  try {\n'
          '    var i = fe.indexOf(realm);\n'
          '    if (!(i >= 0)) i = 0;\n'
          '    if (i > YLXW_DG_CAP.length - 1) i = YLXW_DG_CAP.length - 1;\n'
          '    return YLXW_DG_CAP[i];\n'
          '  } catch (e) { return YLXW_DG_CAP[0]; }\n'
          '}')
E7_NEW = ('function YlxwDgCap(realm) {\n'
          '  try {\n'
          '    var i = fe.indexOf(realm);\n'
          '    if (!(i >= 0)) i = 0;\n'
          '    if (i > YLXW_DG_ROGUE_CAP.length - 1) i = YLXW_DG_ROGUE_CAP.length - 1;\n'
          '    return YLXW_DG_ROGUE_CAP[i];\n'
          '  } catch (e) { return YLXW_DG_ROGUE_CAP[0]; }\n'
          '}')

# —— E8 层数根治：U3 支持层数上限参（缺省仍掷满 z3，行为向后兼容）——
E8_OLD = 'function U3(t,r){const a=xg+Math.floor(Math.random()*(z3-xg+1)),'
E8_NEW = 'function U3(t,r){const a=Math.min(r>0?r:z3,xg+Math.floor(Math.random()*(z3-xg+1))),'

# —— E9 层数根治：调用点按境界封顶层数（炼气≤6/筑基≤8/金丹≤10/元婴+≤12 ⇒ J 门永不拒绝）——
#    原 `if(z<J){c("🚫 此地宫深达…需境界…")` 拒绝分支保留为死代码保险（dungeon085 钉 ==1）。
E9_OLD = 'const W=U3(),z=fe.indexOf(a.realm),J=Math.max(0,Math.ceil(W.totalFloors/2)-3);'
E9_NEW = ('const z=fe.indexOf(a.realm),W=U3(0,Math.min(z3,Math.max(xg,(z+3)*2))),'
          'J=Math.max(0,Math.ceil(W.totalFloors/2)-3);')

EDITS = [
    ('E1 地宫入口前置 rogue 模式',   E1_OLD, E1_NEW, 1),
    ('E2 经典入口前置 normal 模式', E2_OLD, E2_NEW, 1),
    ('E3 入口上报带 mode 字段',     E3_OLD, E3_NEW, 1),
    ('E4 计数回灌按模式分流',       E4_OLD, E4_NEW, 1),
    ('E5 StatusSync 双账本镜像',    E5_OLD, E5_NEW, 1),
    ('E6 rogue 冷却走服务端分账值', E6_OLD, E6_NEW, 1),
    ('E7 上限函数体改读 rogue 表',  E7_OLD, E7_NEW, 1),
    ('E8 U3 支持层数上限参',        E8_OLD, E8_NEW, 1),
    ('E9 调用点按境界封顶层数',     E9_OLD, E9_NEW, 1),
]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 dg085/dungeon2/v2811a）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 0) 注入 rogue 模式/上限表/镜像变量（纯 ASCII 自检 + 禁词自检）
    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r063 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for pat in BAN_PATTERNS:
        if pat in blk:
            raise AssertionError('r063 注入块含禁用模式 %r' % pat)
    if 'fetch(' in blk:
        raise AssertionError('r063 注入块不得含 fetch(')

    p.insert_before('r063-ledger-vars', INJECT_ANCHOR, blk + '\n', expect=1,
                    note='注入 YLXW_DG_ENTRY_MODE/NORM_CNT/SRV_ROGUE_CD/ROGUE_CAP（rogue 独立账本客户端半边）')

    # 1) 九处就地替换（全部 expect=1）
    for name, old, new, exp in EDITS:
        p.replace(name, old, new, expect=exp)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本模块改动：rogue 独立账本（客户端半边） =================
        ('R63·rogue 上限表 [3..13]',      'var YLXW_DG_ROGUE_CAP = [3, 5, 7, 8, 10, 11, 13];', 1, '==', '炼气3→长生13，与 srv DUNGEON_ROGUE_CAP_BY_REALM 同源'),
        ('R63·rogue 表两端恰为 3/13',     '[3, 5, 7, 8, 10, 11, 13]', 1, '==', ''),
        ('R63·模式变量声明',              'var YLXW_DG_ENTRY_MODE = 0;', 1, '==', '0=普通点选 1=roguelike'),
        ('R63·普通计数镜像变量',          'var YLXW_DG_NORM_CNT = 0;', 1, '==', ''),
        ('R63·rogue 服务端冷却变量',      'var YLXW_DG_SRV_ROGUE_CD = 0;', 1, '==', ''),
        ('R63·地宫入口已置 rogue 模式',   'return}YLXW_DG_ENTRY_MODE=1;const _ylg=await YlxwDungeonEntryGate();', 1, '==', 'E1'),
        ('R63·经典入口已置 normal 模式',  'return!1}YLXW_DG_ENTRY_MODE=0;const _ylg=await YlxwDungeonEntryGate();', 1, '==', 'E2'),
        ('R63·旧地宫调用形态已清零',      'return}const _ylg=await YlxwDungeonEntryGate();', 0, '==', 'E1 旧形态'),
        ('R63·旧经典调用形态已清零',      'return!1}const _ylg=await YlxwDungeonEntryGate();', 0, '==', 'E2 旧形态'),
        ('R63·上报带 mode 字段',          'body: JSON.stringify({ mode: YLXW_DG_ENTRY_MODE ? "rogue" : "normal" })', 1, '==', 'E3'),
        ('R63·回灌已按模式分流',          'else { YLXW_DG_NORM_CNT = Math.floor(n); }', 1, '==', 'E4'),
        ('R63·rogue 回灌写 __ylDg',       'if (YLXW_DG_ENTRY_MODE) { window.__ylDg = { d: YlxwDungeonToday(), cnt: Math.floor(n), cd: YlxwDgCdUntil() }; }', 1, '==', 'E4'),
        ('R63·旧无条件回灌已清零',        'return;\n    window.__ylDg = {', 0, '==', 'E4 旧形态'),
        ('R63·普通镜像前置 mode=0',       'YLXW_DG_ENTRY_MODE = 0; YLXW_DG_SRV_CD = Number(s.cdLeftMs) || 0;', 1, '==', 'E5'),
        ('R63·rogue 镜像已追加',          'if (s && typeof s.rogueCount === "number") { YLXW_DG_SRV_ROGUE_CD = Number(s.rogueCdLeftMs) || 0; YLXW_DG_ENTRY_MODE = 1; YlxwDungeonMarkLocal(s.rogueCount); YLXW_DG_ENTRY_MODE = 0; }', 1, '==', 'E5'),
        ('R63·rogue 冷却取分账值',        'var srv = Number(YLXW_DG_SRV_ROGUE_CD) > 0 ? Date.now() + Number(YLXW_DG_SRV_ROGUE_CD) : 0;', 1, '==', 'E6'),
        ('R63·旧共享冷却取值已清零',      'var srv = Number(YLXW_DG_SRV_CD) > 0', 0, '==', 'E6 旧形态'),
        # ================= 本模块改动：上限表换血（E7） =================
        ('R63·上限函数体读 rogue 表',     'if (i > YLXW_DG_ROGUE_CAP.length - 1) i = YLXW_DG_ROGUE_CAP.length - 1;', 1, '==', 'E7'),
        ('R63·上限函数返回 rogue 表',     'return YLXW_DG_ROGUE_CAP[i];', 1, '==', 'E7'),
        ('R63·旧读 CAP 表已清零',         'if (i > YLXW_DG_CAP.length - 1)', 0, '==', 'E7 旧形态'),
        ('R63·旧返回 CAP 表已清零',       'return YLXW_DG_CAP[i];', 0, '==', 'E7 旧形态'),
        # ================= 本模块改动：层数境界门根治（E8/E9） =================
        ('R63·U3 层数上限参',             'function U3(t,r){const a=Math.min(r>0?r:z3,xg+Math.floor(Math.random()*(z3-xg+1))),', 1, '==', 'E8（★ 2026-10-01 修：原漏一个右括号，导致整包语法错误、游戏卡加载页）'),
        ('R63·旧 U3 无上限掷骰已清零',    'function U3(t,r){const a=xg+', 0, '==', 'E8 旧形态'),
        ('R63·调用点按境界封顶层数',      'const z=fe.indexOf(a.realm),W=U3(0,Math.min(z3,Math.max(xg,(z+3)*2))),J=Math.max(0,Math.ceil(W.totalFloors/2)-3);', 1, '==', 'E9：炼气≤6/筑基≤8/金丹≤10/元婴+≤12'),
        ('R63·旧无封顶调用已清零',        'const W=U3(),z=fe.indexOf(a.realm)', 0, '==', 'E9 旧形态'),
        # ================= 冻结：上游钉死串逐字保留 =================
        ('冻结·入口 gate 调用恒 2',       '=await YlxwDungeonEntryGate();', 2, '==', 'dg085+v2811a 双门禁'),
        ('冻结·gate 函数定义未动',        'async function YlxwDungeonEntryGate() {', 1, '==', 'dg085+fun086'),
        ('冻结·MarkLocal 签名未动',       'function YlxwDungeonMarkLocal(count) {', 1, '==', 'dg085+v2811a'),
        ('冻结·rogue 冷却写法保留',       'cd: YlxwDgCdUntil() };', 1, '==', 'dungeon2 E5 门禁（在 E4 rogue 分支内）'),
        ('冻结·StatusSync 钉死串保留',    'YLXW_DG_SRV_CD = Number(s.cdLeftMs) || 0; YlxwDungeonMarkLocal(s.count);', 1, '==', 'dungeon2 E6 门禁'),
        ('冻结·ylDgGate 函数体未动',
         'function ylDgGate(){const q=window.__ylDg||(window.__ylDg={d:"",cnt:0,cd:0}),W=new Date(),X=W.getFullYear()+"-"+(W.getMonth()+1)+"-"+W.getDate(),Y=q.cd||0;return{day:q.d===X?q.cnt||0:0,cdMin:Date.now()<Y?Math.ceil((Y-Date.now())/6e4):0}}',
         1, '==', 'dg085+dungeon2 双门禁'),
        ('冻结·普通点选上限表原样',       'var YLXW_DG_CAP = [10, 12, 14, 15, 17, 18, 20];', 1, '==', 'R-032 拍板表归普通点选；dungeon2+R-062 门禁'),
        ('冻结·普通点选表字面恒 1',       '[10, 12, 14, 15, 17, 18, 20]', 1, '==', 'dungeon2 门禁'),
        ('冻结·境界序取值行保留',         'var i = fe.indexOf(realm);', 1, '==', 'dungeon2 门禁（E7 新体内原样保留）'),
        ('冻结·上限函数签名未动',         'function YlxwDgCap(realm) {', 1, '==', 'dungeon2 门禁'),
        ('冻结·上限调用点恒 6',           'YlxwDgCap(a&&a.realm)', 6, '==', 'R-062 门禁：disabled/className/children/E2b/E2c/E9'),
        ('冻结·地宫境界门槛保留',         'if(z<J){c(', 1, '==', 'dg085 门禁（E9 后为死代码保险）'),
        ('冻结·rogue 计数回灌未动',       'cnt:(typeof _ylg.count==="number"?_ylg.count:q.day+1)', 1, '==', 'R-062 门禁；响应已是 rogue 分账值'),
        ('冻结·rogue 本地冷却表达式未动', 'cd:Date.now()+YLXW_DG_CD_MS}}catch(KS){}', 1, '==', 'dungeon2 E4+R-062（15 分钟来自常量）'),
        ('冻结·入口原始 fetch 未动',      'fetch(Nd(ln + YLXW_DG_ENTRY), {', 1, '==', 'dg085 门禁'),
        ('冻结·roguelike 面板唯一',       'vk=Rt.memo(yk);', 1, '==', 'dungeon2 门禁'),
        ('冻结·弹窗信息条未动',           'children:[YLXW_DGS?YLXW_DGS.count:"\\u2014"," / ",YLXW_DGS?YLXW_DGS.cap:3]', 1, '==', 'v2811a 门禁（普通点选走服务端 cap）'),
        ('冻结·冷却取较晚者口径未动',     'return Math.max(prev, srv);', 1, '==', 'dungeon2 门禁'),
        # ================= 冻结：R-062 面（order-safe，装配序无关） =================
        ('冻结·弹窗秘境内层 Ym 未动',     'Ym(oe,{realm:t.realm,realmLevel:t.realmLevel,maxHp:F.maxHp},YLXW_STONE_MUL_ADV)', 1, '==', 'R-062 收益面（无论其先环后环，内层调用串都在）'),
        ('冻结·秘境深处站未动',           'C=Ym(k,{realm:l.realm,realmLevel:l.realmLevel,maxHp:_.maxHp},YLXW_STONE_MUL_SR);', 1, '==', '0.8.5 eco / R-062 冻结面'),
        ('冻结·roguelike G3 收益未动',    '*1.63666;', 1, '==', 'R-062 明确不 boost roguelike'),
        ('冻结·Ym 签名未动',              'function Ym(t,r,_ylm){', 1, '==', 'eco085/R-062 注入锚，未动'),
    ]
    return gates
