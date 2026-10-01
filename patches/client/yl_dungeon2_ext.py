# -*- coding: utf-8 -*-
r"""
yl_dungeon2_ext.py — R-032「秘境：冷却制度 + 每日上限随等阶」客户端单模块

需求原文（用户）
--------------------------------------------------------------------------
  「① 秘境探索改冷却制度 ② 每日上限 3→20 随等阶提升（需服务端+客户端同改）
    ③ 修复右侧面板被压缩布局」

侦察（构建产物 index-v2811-20260930.js 逐字实证）
--------------------------------------------------------------------------
  · 秘境 Roguelike 面板 `yk=({isOpen:t,onClose:r,player:a,setPlayer:l,addLog:c})=>`（@1793739，
    `vk=Rt.memo(yk)`，由 `isDungeonOpen` 打开）内自带**本地闸门** `ylDgGate()`（@1795911）：
        function ylDgGate(){const q=window.__ylDg||(window.__ylDg={d:"",cnt:0,cd:0}),...
          return{day:q.d===X?q.cnt||0:0,cdMin:Date.now()<Y?Math.ceil((Y-Date.now())/6e4):0}}
    · 每日上限硬编码为 **3**：
        - `T` 回调内预检 `if(q.day>=3){c("…今日地宫探索次数已用完（3/3）…")}`
        - 按钮 `disabled:ylDgGate().day>=3||ylDgGate().cdMin>0`（disabled + className 两处）
        - 文案 `children:ylDgGate().day>=3?"今日次数已用完":…`
        - 展示行 `"今日已探索 "+ylDgGate().day+"/3 次 · 每次探索后冷却 30 分钟 · …"`
    · **冷却实际是死的**：进入成功时写 `cd:Date.now()`（= 当下即已过去 ⇒ cdMin 恒 0），
      即 UI 宣称的「冷却 30 分钟」从未生效。
    · 且 `YlxwDungeonStatusSync()`（每次开面板都调）→ `YlxwDungeonMarkLocal(count)`
      会把 `window.__ylDg.cd` **重置为 0**（`cd: 0`）⇒ 即便写了冷却也会被下一次开面板抹掉。
  · 等阶序 `fe=[炼气期,筑基期,金丹期,元婴期,化神期,合道期,长生境]`（7 档）。
  · 服务端 `DUNGEON_DAILY_CAP=3` / `DUNGEON_ENTRY_CD_MS=30_000`（srv:3484-3485），
    且 `/api/dungeon/entry` 超限 **403 reason:'cap'**；`yl_dungeon085_ext` 已把两条入口
    接到该端点且 **403 即拒绝** ⇒ **服务端必须同改**（见 `srv_patch_dungeon2.py`）。

改法（1 处注入 + 6 处就地替换；E9 与 E10 同处一行，合并为一条）
--------------------------------------------------------------------------
  E2  三处 `ylDgGate().day>=3` → `ylDgGate().day>=YlxwDgCap(a&&a.realm)`
  E2b `T` 回调预检 `if(q.day>=3)` → `if(q.day>=YlxwDgCap(a&&a.realm))`，并把文案里的
      写死「（3/3）」改成动态「（x/cap）」
  E4  进入成功写入 `cd:Date.now()` → `cd:Date.now()+YLXW_DG_CD_MS`（**真正开始冷却**）
  E5  `YlxwDungeonMarkLocal` 不再清零冷却（`cd: 0` → `cd: YlxwDgCdUntil()`）
  E6  `YlxwDungeonStatusSync` 把服务端 `cdLeftMs` 存进模块级 `YLXW_DG_SRV_CD` 再回灌
  E9+E10 ★ **同一条 replace**（同一行）：
        `"今日已探索 "+ylDgGate().day+"/3 次 · 每次探索后冷却 30 分钟 · …"`
        → `"今日已探索 "+ylDgGate().day+"/"+YlxwDgCap(a&&a.realm)+" 次 · 每次探索后冷却 5 分钟 · …"`
        （E9 = 30→5 分钟；E10 = 写死 `/3 ` → 动态 `x/cap`）

  ★ **为什么不改 `ylDgGate()` 本体**：`yl_dungeon085_ext.py` 的
    `基线·ylDgGate 定义未动` 门禁把整个函数体冻结（逐字断言），且本模块
    **不得改动其它已接线模块**。故 cap 一律在**调用点**用 `YlxwDgCap(境界)` 求值。
  ★ **为什么不改 `YlxwDungeonMarkLocal(count)` 签名**：dungeon085「E6·本地计数回灌
    函数已定义」与 v2811a「基线·dg085 回灌函数未动」都断言该签名逐字不变 ⇒
    服务端冷却改用模块级 `YLXW_DG_SRV_CD` 传参（签名零改动）。

数值口径（用户最新拍板 + 策划《策划_R032秘境配平与R019R023口径.md》）
--------------------------------------------------------------------------
  · 冷却 5 分钟（策划 D12-A）：服务端 `DUNGEON_ENTRY_CD_MS` 30_000 → 300_000，
    客户端 `YLXW_DG_CD_MS = 5 * 60 * 1000`；UI 既有文案「每次探索后冷却 30 分钟」
    同步改为「每次探索后冷却 5 分钟」（E9）。
  · 上限表 `[10,12,14,15,17,18,20]` = 7 档、**炼气 10 → 长生 20**（用户最新拍板
    「炼气基数定 10 次，其他境界递增」）。6 段总增 10 ⇒ 平均 1.67/档，取整后
    严格单调递增，两端精确落 10 / 20。
    ★ 与策划案定档 D13-A（`min(20,3+3×境界序)` = `[3,6,9,12,15,18,20]`，炼气 3 起）
    **不一致** —— 以用户最新拍板为准，此处为唯一改点；服务端
    `srv_patch_dungeon2.py` 用**同一张表**保证同源。
  · 单次产出 / 60% 掉落率：**不动**（策划 §1.3、§1.5 结论：日注入恒为打坐 0.17~0.24h）。
  · 服务端经济配额（`settleSaveEconV2` 的 `cSR = ceil(mins*4)+6`）：**不动**
    （策划 §1.6：只松 9.8%，不引入新夹取风险）。

★ 历史未覆盖项（**已解决**，留档）
--------------------------------------------------------------------------
  · ~~Roguelike 面板展示行 `ylDgGate().day+"/3 "` 是 dungeon085 的门禁串~~ →
    **2026-09-30 lead 已把 `yl_dungeon085_ext.py` 的 `基线·地宫展示文案未动`
    改为注释（约束权移交 dungeon2）** ⇒ 本模块已补 **E10** 把该行改成
    `day+"/"+YlxwDgCap(a&&a.realm)+" 次`（与 E9 合并为一条 replace，因两者同一行）。
  · 秘境探索弹窗（组件 `cM`）的 `x/cap` 信息条来自服务端 `/dungeon/status` 的
    `cap` 字段 ⇒ 由 `srv_patch_dungeon2.py` 按境界下发正确值（客户端零改动）。

硬约束
--------------------------------------------------------------------------
  · 不改 `/dungeon/entry` 的 403 契约（yl_dungeon085_ext 以 `status===403` 判定拒绝）。
  · 注入块 zh() 后纯 ASCII；每个 replace 带 expect=精确次数。
  · 只新建本文件；不改 build_v26n.py、不写 build/assets/。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-R032: 秘境「冷却制度」+「每日上限随等阶 10→20」=====
   ① 冷却：进入成功即写 window.__ylDg.cd = now + 5 分钟（策划 D12-A，与
      服务端 DUNGEON_ENTRY_CD_MS=300000 同源），并把「服务端 cdLeftMs」与
      「本地剩余」取较晚者，避免开面板被 StatusSync 清零。
   ② 上限：YLXW_DG_CAP = 炼气 10 → 长生 20（7 档，用户最新拍板），与服务端同一张表。
      ★ 不改 ylDgGate() 本体（dungeon085 门禁冻结），cap 在调用点用 YlxwDgCap 求值。 */
var YLXW_DG_CD_MS = 5 * 60 * 1000;
var YLXW_DG_CAP = [10, 12, 14, 15, 17, 18, 20];
var YLXW_DG_SRV_CD = 0;
function YlxwDgCap(realm) {
  try {
    var i = fe.indexOf(realm);
    if (!(i >= 0)) i = 0;
    if (i > YLXW_DG_CAP.length - 1) i = YLXW_DG_CAP.length - 1;
    return YLXW_DG_CAP[i];
  } catch (e) { return YLXW_DG_CAP[0]; }
}
/* 冷却剩余 = max(本地剩余, 服务端 cdLeftMs)，两者取较晚者（服务端未上线时本地仍生效）。
   服务端冷却经模块级 YLXW_DG_SRV_CD 传入 —— 不改 YlxwDungeonMarkLocal(count) 签名。 */
function YlxwDgCdUntil() {
  var prev = 0;
  try { prev = Number(window.__ylDg && window.__ylDg.cd) || 0; } catch (e0) { prev = 0; }
  var srv = Number(YLXW_DG_SRV_CD) > 0 ? Date.now() + Number(YLXW_DG_SRV_CD) : 0;
  return Math.max(prev, srv);
}
'''

# --------------------------------------------------------------------------- 锚点常量

# 注入锚：yl_dungeon085_ext 块内的模块级函数（depth=2）
INJECT_ANCHOR = 'async function YlxwDungeonStatusSync() {'

# E2 三处硬编码上限（disabled / className / children；`T` 回调内的 `q.day>=3` 走 E2b）
E2_OLD = 'ylDgGate().day>=3'
E2_NEW = 'ylDgGate().day>=YlxwDgCap(a&&a.realm)'

# E2b T 回调预检 + 写死「（3/3）」改动态
E2B_OLD = 'if(q.day>=3){c('
E2B_NEW = 'if(q.day>=YlxwDgCap(a&&a.realm)){c('
E2C_OLD = r'\u5df2\u7528\u5b8c\uff083/3\uff09\uff0c\u660e\u65e5\u518d\u6765'
E2C_NEW = (r'\u5df2\u7528\u5b8c\uff08"+(q.day)+"/"+YlxwDgCap(a&&a.realm)+"\uff09'
           r'\uff0c\u660e\u65e5\u518d\u6765')

# E4 进入成功真正开始冷却
E4_OLD = 'cd:Date.now()}}catch(KS){}'
E4_NEW = 'cd:Date.now()+YLXW_DG_CD_MS}}catch(KS){}'

# E5 MarkLocal 不再清零冷却（签名逐字不动）
E5_OLD = 'cd: 0 };'
E5_NEW = 'cd: YlxwDgCdUntil() };'

# E6 StatusSync 把服务端 cdLeftMs 存进模块级变量再回灌（不传参）
E6_OLD = 'if (s && typeof s.count === "number") YlxwDungeonMarkLocal(s.count);'
E6_NEW = ('if (s && typeof s.count === "number") '
          '{ YLXW_DG_SRV_CD = Number(s.cdLeftMs) || 0; YlxwDungeonMarkLocal(s.count); }')

# E9+E10 合并（★ 同一行，必须一次改完）
#   展示行原文（实测，bundle 内 count==1）：
#     children:"今日已探索 "+ylDgGate().day+"/3 次 · 每次探索后冷却 30 分钟 · 层数境界：…"
#   · E9 只改「冷却 30 分钟」→「冷却 5 分钟」（D12-A）
#   · E10 改「day+"/3 "」→「day+"/"+YlxwDgCap(a&&a.realm)+" "」（写死 /3 改动态）
#   两者同属这一行 ⇒ 合并成**一条** replace，避免两段锚点在同一行互相影响。
#   ★ 作用域确认：本行紧邻的按钮 `children` 已由 E2 改成
#     `ylDgGate().day>=YlxwDgCap(a&&a.realm)?…`（实测同一渲染处）⇒ `a`（player）在作用域内，
#     直接用 `a&&a.realm`，无需从 store 另读，运行期不会抛 ReferenceError。
E9_OLD = (r'ylDgGate().day+"/3 \u6b21 \u00b7 '
          r'\u6bcf\u6b21\u63a2\u7d22\u540e\u51b7\u5374 30 \u5206\u949f')
E9_NEW = (r'ylDgGate().day+"/"+YlxwDgCap(a&&a.realm)+" \u6b21 \u00b7 '
          r'\u6bcf\u6b21\u63a2\u7d22\u540e\u51b7\u5374 5 \u5206\u949f')

EDITS = [
    ('E2 三处上限改读 cap',          E2_OLD, E2_NEW, 3),
    ('E2b T 回调预检改读 cap',       E2B_OLD, E2B_NEW, 1),
    ('E2c 预检文案 3/3 改动态',      E2C_OLD, E2C_NEW, 1),
    ('E4 进入成功真正开始冷却',      E4_OLD, E4_NEW, 1),
    ('E5 MarkLocal 不再清零冷却',    E5_OLD, E5_NEW, 1),
    ('E6 StatusSync 下发服务端冷却', E6_OLD, E6_NEW, 1),
    ('E9+E10 展示行改动态 + 冷却 5 分钟', E9_OLD, E9_NEW, 1),
]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 dungeon085/v2811a）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('dungeon2 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 模块级工具函数（depth=2）
    p.insert_before('dungeon2-helpers', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 YLXW_DG_CD_MS/CAP/SRV_CD + YlxwDgCap/YlxwDgCdUntil')

    # 1) 就地替换
    for name, old, new, exp in EDITS:
        p.replace(name, old, new, expect=exp)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 注入块 =================
        ('R32·冷却常量 15 分钟（R-062 改）', 'var YLXW_DG_CD_MS = 15 * 60 * 1000;', 1, '==', 'D12-A 5 分钟 → R-062 拍板 15 分钟，与 srv DUNGEON_ENTRY_CD_MS=900_000 同源'),
        ('R32·上限表 10→20 递增',     'var YLXW_DG_CAP = [10, 12, 14, 15, 17, 18, 20];', 1, '==', '炼气10→长生20（用户最新拍板）'),
        ('R32·上限表两端恰为 10/20',  '[10, 12, 14, 15, 17, 18, 20]', 1, '==', ''),
        ('R32·旧 3/6/9 表已清零',     '[3, 6, 9, 12, 15, 18, 20]', 0, '==', '策划案 D13-A 旧表不得残留'),
        ('R32·旧 14/17 表已清零',     '[3, 6, 9, 12, 14, 17, 20]', 0, '==', '线性插值旧表不得残留'),
        ('R32·旧 30 分钟冷却已清零',  'var YLXW_DG_CD_MS = 30 * 60 * 1000;', 0, '==', ''),
        ('R32·按境界取上限函数',      'function YlxwDgCap(realm) {', 1, '==', ''),
        ('R32·读境界序 fe',           'var i = fe.indexOf(realm);', 1, '==', ''),
        ('R32·服务端冷却变量',        'var YLXW_DG_SRV_CD = 0;', 1, '==', '不传参，保 MarkLocal 签名'),
        ('R32·冷却取较晚者',          'function YlxwDgCdUntil() {', 1, '==', ''),
        ('R32·冷却 max 口径',         'return Math.max(prev, srv);', 1, '==', '本地 vs 服务端取较晚'),
        # ================= E2/E2b/E2c 上限 =================
        ('R32·三处硬编码 3 已清零',   'ylDgGate().day>=3', 0, '==', ''),
        ('R32·闸门比较改读 cap',      'ylDgGate().day>=YlxwDgCap(a&&a.realm)', 3, '==', 'disabled/className/children'),
        ('R32·T 预检改读 cap',        'if(q.day>=YlxwDgCap(a&&a.realm)){c(', 1, '==', ''),
        ('R32·预检文案 3/3 已清零',   r'\uff083/3\uff09', 0, '==', ''),
        ('R32·预检文案改动态',        r'\uff08"+(q.day)+"/"+YlxwDgCap(a&&a.realm)+"\uff09', 1, '==', ''),
        # ================= E4 冷却 =================
        ('R32·进入成功开始冷却',      'cd:Date.now()+YLXW_DG_CD_MS}}catch(KS){}', 1, '==', '旧 cd:Date.now() 已清零'),
        ('R32·旧零冷却写法清零',      'cd:Date.now()}}catch(KS){}', 0, '==', ''),
        # ================= E5/E6 冷却不被清零 =================
        ('R32·MarkLocal 不清零冷却',  'cd: YlxwDgCdUntil() };', 1, '==', '旧 cd:0 已清零'),
        ('R32·旧清零写法已清零',      'window.__ylDg = { d: YlxwDungeonToday(), cnt: Math.floor(n), cd: 0 };', 0, '==', ''),
        ('R32·StatusSync 下发冷却',   'YLXW_DG_SRV_CD = Number(s.cdLeftMs) || 0; YlxwDungeonMarkLocal(s.count);', 1, '==', ''),
        ('R32·提示文案冷却改 15 分钟（R-062 改）', r'\u6bcf\u6b21\u63a2\u7d22\u540e\u51b7\u5374 15 \u5206\u949f', 1, '==', 'R-062 拍板 15 分钟'),
        ('R32·旧 30 分钟文案已清零',  r'\u6bcf\u6b21\u63a2\u7d22\u540e\u51b7\u5374 30 \u5206\u949f', 0, '==', ''),
        ('R32·地宫展示文案改动态',   'ylDgGate().day+"/"+YlxwDgCap(', 1, '==', '原 "/3 " 写死已清零'),
        ('R32·地宫旧 /3 文案已清零', 'ylDgGate().day+"/3 ', 0, '==', '约束权已由 dungeon085 移交 dungeon2'),
        # ================= ★ 跨模块冻结串必须逐字保留 =================
        ('跨模块·ylDgGate 定义未动',
         'function ylDgGate(){const q=window.__ylDg||(window.__ylDg={d:"",cnt:0,cd:0}),W=new Date(),X=W.getFullYear()+"-"+(W.getMonth()+1)+"-"+W.getDate(),Y=q.cd||0;return{day:q.d===X?q.cnt||0:0,cdMin:Date.now()<Y?Math.ceil((Y-Date.now())/6e4):0}}',
         1, '==', 'dungeon085 门禁串：cap 在调用点求值，不改本体'),
        ('跨模块·MarkLocal 签名未动',  'function YlxwDungeonMarkLocal(count) {', 1, '==', 'dungeon085 + v2811a 门禁串'),
        ('跨模块·cM 信息条未动',       r'children:[YLXW_DGS?YLXW_DGS.count:"\u2014"," / ",YLXW_DGS?YLXW_DGS.cap:3]', 1, '==', 'v2811a 门禁串：cap 由服务端按境界下发'),
        ('跨模块·Roguelike 面板唯一', 'vk=Rt.memo(yk);', 1, '==', ''),
        ('R32·未新增网络调用',        'fetch(', 0, '==', '纯客户端；entry 走既有裸 fetch',
         ('/* ===== yl-R032:', 'async function YlxwDungeonStatusSync() {')),
    ]
    return gates
