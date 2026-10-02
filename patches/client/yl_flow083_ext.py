# -*- coding: utf-8 -*-
"""
yl_flow083_ext.py — 0.8.3 批 cli-flow：三项客户端修复（纯锚点改写，无运行时注入）

=========================================================================== 结论速览
本模块只做三件事，全部为**纯前端**、**纯文本锚点替换**、**不新增组件/不新增 CSS/无运行时注入**：

  ⑤ 历练刷新间隔 ×2（现在太快）  → 历练路径冷却 3 → 6 秒（共 4 个同步点）
  ⑥ 「去信箱」按钮点了没反应      → 把两处空 `go` 接上 `YlxwOpen(k)`
  ⑦ 功法阁等融合页的「仙务」块    → 从页尾移到页面最上方

=========================================================================== 侦察复核（cli-flow 独立复核，非转述）

── ⑤ 历练间隔 ──────────────────────────────────────────────────────────────
1) 真正的节流是**冷却**，不是轮询：自动历练 effect 每 500ms 打一次 `handleAdventure`，
   但 store 版 `handleAdventure` 首行 `if(u||f>0)return;`（u=loading、f=cooldown）直接拦掉。
   `cooldown` 由 `Lw()` 的 `setInterval(...,1e3)` 里 `a(x=>x>0?x-1:0)` 每秒 −1 ⇒ `d(3)` = 3 秒。
2) `d(3)` 全量 17 处，其中 **11 处是 `toFixed(3)` 的假命中**（战斗/融合数值），与历练无关。
   真正属于历练的 `c(!1),d(3)` **共 4 处**（lead 说 3 处，实际避战有两处）：
     · A 内避战   @1396660  `if(k)return a("你选择避开战斗，继续历练..."),c(!1),d(3),{result:{},...}`
     · DS 分支避战 @1398001 `if(k){a("你选择避开战斗，继续历练..."),c(!1),d(3);return}`
     · 正常收尾   @1401345  `...finally{c(!1),d(3)}`
     · 商店跳过   @1401784  `a("你选择跳过商店，继续历练..."),c(!1),d(3);else{`
   注：避战/商店跳过的早期 `return` 落在 `I` 的 try 内 ⇒ `finally{c(!1),d(3)}` 仍会兜底执行，
   所以 4 处必须一起改，否则「有时 6 秒、有时 3 秒」。
3) 打坐是**另一套节奏**：`Zt.current.handleMeditate(),...updateQuestProgress("meditate",1),M(1)`
   ⇒ `setCooldown(1)` = 1 秒（60 次/分）。本模块**绝不触碰**（门禁断言 `M(1)` 仍为 1）。
4) 收益处理：**单次收益不动、每分钟收益减半**——即只把间隔 ×2，不改 `expChange`/`spiritStonesChange`
   等奖励数值。服务端确认无「下限」类反作弊（见下）。
5) 服务端复核（srv/index_v28.ts）：
   · L1704-1717 E2 存档差值钳制：`cAdv = Math.ceil(realMins*130)+30`（≈130 次/分）是**上限**，
     `if(dAdv>cAdv){...clamp}`。新客户端速率 ≈10 次/分（6 秒/次），远低于上限 ⇒ 永不触发。
   · L3682-3686 / L3709-3717 Y2 日常任务：`adventure: 历练 3 次` 是**下限目标**（达成即 done），
     速率变慢只会晚一点完成，无任何惩罚；`computeQuestDeltas` 对计数回退钳 0，不倒扣。
   · L3942 / L4820-4825 dungeon_tracker：`DUNGEON_ANOMALY_THRESHOLD=10`，anomaly 由
     `observed`(secretRealmCount 差值) 或 `count`(秘境进入次数) 判定；`adventure`(adventureCount 差值)
     只入库作「刷度参考」，**不参与 anomaly CASE** ⇒ 历练变慢对异常标记零影响。
   · L467 economy_ledger：旁路只读账本，「绝不拦截/拒绝存档」，与本项无关。
   ⇒ 结论：降速不会触发任何惩罚/异常检测。

── ⑥ 去信箱 ────────────────────────────────────────────────────────────────
1) 3 个「去信箱」按钮（转义串 `\\u53bb\\u4fe1\\u7bb1`）@822987 / @833911 / @873889，
   形态一致：`e.jsx(YlxwBtn, { tone: "ghost", onClick: function() { t("mail"); }, children: "\\u53bb\\u4fe1\\u7bb1" })`
   （组件分别为 YlxwTQuest / YlxwTAlchemy / YlxwTAch），其中 `t` 即 props 的 `go`。
2) `go: function () {}` **共 2 处**（形态完全相同 `go: function () {}, player: YlxwPlayer() }`）：
   · `YlxwPanelModal`（真正被渲染的仙务面板外壳）
   · `YlxwFuseOne`（融合页里的仙务块）
   ⇒ 两处都把 `go` 传成空函数 ⇒ 按钮点了什么都不做（根因确认）。
3) `YlxwHub`（带可用 `go: function(f){d(f);}`）**全文件只出现 1 次** = 定义处，**从未被渲染 ⇒ 死代码**。
4) `YlxwOpen(k)` 定义（bundle @~914969，与 YlxwMeta/YlxwPlayer 相邻，均为顶层 `function`）：
   `function YlxwOpen(k) { try { var s = Ze.getState(); s.setModal("xianwuTab", k || "mail"); s.setModal("isXianwuOpen", !0); } catch (r) {} }`
   ⇒ 语义 = `setModal("xianwuTab",k)` + `setModal("isXianwuOpen",true)`，与 lead 描述一致。
5) 作用域：`function YlxwOpen` / `function YlxwPanelModal` / `function YlxwFuseOne` **三者都在第 0 列**
   （前面都是 `\n\n`，无缩进）⇒ 同一模块顶层作用域，`function` 声明提升 ⇒ 可见。
   另有生产实证：同区域 30+ 处导航按钮（@758997 起）已调用 `YlxwOpen("sect")` 等并正常生效（0.8.2 已上线）。
6) 仙务面板挂载点 @1374436：`d.isXianwuOpen&&e.jsx(YlxwPanelModal,{isOpen:d.isXianwuOpen,tab:d.xianwuTab,onClose:()=>Ze.getState().setModal("isXianwuOpen",!1),player:t})`
   ⇒ 只要 `isXianwuOpen=true` + `xianwuTab` 被设置，面板就会打开并切到对应 tab。

── ⑦ 仙务块置顶 ────────────────────────────────────────────────────────────
1) 唯一统一落点：modal 外壳 `wN`（`ct=O.memo(wN)` @254705）的内容区 @254395：
   `children:[l,__xw?e.jsx(YlxwFuse,{k:__xw}):null]`（**全文件唯一，count=1**）
   其中 `l` = 外壳 props 的 `children`（该页本体），`__xw` = 外壳 props `xw` 的别名（`xw:__xw` @252172）。
2) `YlxwFuse` 全文件只被渲染 **1 次**（就是上面这处）；`e.jsx(YlxwFuse,{k:__xw})` count=1。
3) 传 `xw` 给外壳的页面共 **9 处**（8 个单 key + 1 个数组）：
   gongfa@1045864 / alchemy@1056500 / sect@1117923 / dungeon@1137678 /
   `xw:["titles","stats"]`@1181356（角色系统，一次挂两块）/ ach@1224786 / pet@1246677 /
   farm@1340515 / rebirth@1510234。⇒ 改这一处即 9 页全部生效，无第二处需要改。
4) key 结论：该 `children` 是**数组**，`l` 与 `YlxwFuse` 均**未带显式 key**（靠数组下标隐式处理）。
   · 本 bundle 是 **React 生产构建**（全文件 `Each child in a list`=0、`unique "key"`=0、`react.production`=1）
     ⇒ 生产版**不执行** key 校验，不会打印 key 警告。
   · 数组元素个数/身份不因本次改动而变化（改动前也是 2 元素：`[l, Fuse|null]`），只是顺序互换；
     每次 render 顺序恒定 ⇒ 下标式协调稳定，不会「渲染错乱」。
   · 故**不加 key**（给单侧补 key 反而与另一侧不一致、且给 `l` 补 key 需 cloneElement 引入新风险）。
     —— 结论：无需补 key，见 localtest/report_cli-flow.md。

=========================================================================== 依赖 / 铁律
· 本模块**不依赖**其它 v28 模块的前置改写（三条锚点均来自 0.8.2 基线原文）。
· **只新建本模块与 localtest 下的自测/报告**，不改任何已有模块，不写 build/assets。
· 本批次**无需运行时注入**：`INJECT_JS` 仅作纯 ASCII 说明横幅（不插入 bundle）。
"""

# --------------------------------------------------------------------------- 注入块
# 本批次全部为「改写既有代码」，无新增运行时逻辑 ⇒ 不注入任何 JS。
# 按契约保留 INJECT_JS（纯 ASCII），zh(INJECT_JS) 必然无非 ASCII。
INJECT_JS = r'''
/* ===== yl-v083 cli-flow: adventure-cooldown x2 + mail button + xianwu-block-first (anchor-only, no runtime inject) ===== */
'''

# --------------------------------------------------------------------------- ⑤ 历练间隔 ×2
# 锚点均取自 0.8.2 基线 bundle 原文（raw 中文，非转义形态）。

# A 内避战（`A=async(...)=>{if(k)return ...}` 的首个 return）
A_ADV_AVOID_A = 'd(3),{result:{},battleContext:null,shouldReturn:!0}'
R_ADV_AVOID_A = 'd(6),{result:{},battleContext:null,shouldReturn:!0}'

# DS 分支避战
A_ADV_AVOID_DS = 'a("\u4f60\u9009\u62e9\u907f\u5f00\u6218\u6597\uff0c\u7ee7\u7eed\u5386\u7ec3...","normal"),c(!1),d(3);return}'
R_ADV_AVOID_DS = 'a("\u4f60\u9009\u62e9\u907f\u5f00\u6218\u6597\uff0c\u7ee7\u7eed\u5386\u7ec3...","normal"),c(!1),d(6);return}'

# 正常收尾（executeAdventure 的 finally）
A_ADV_FINALLY = 'finally{c(!1),d(3)}'
R_ADV_FINALLY = 'finally{c(!1),d(6)}'

# 商店跳过（handleAdventure 内）
A_ADV_SHOPSKIP = 'a("\u4f60\u9009\u62e9\u8df3\u8fc7\u5546\u5e97\uff0c\u7ee7\u7eed\u5386\u7ec3...","normal"),c(!1),d(3);'
R_ADV_SHOPSKIP = 'a("\u4f60\u9009\u62e9\u8df3\u8fc7\u5546\u5e97\uff0c\u7ee7\u7eed\u5386\u7ec3...","normal"),c(!1),d(6);'

# --------------------------------------------------------------------------- ⑤b 补齐：同组件内其余快返回路径
# 背景：lead 用正则 \bd\((\.?\d+)\) 扫过历练组件区间 [1395500,1402300)，
#       除注释文字外共 **9 个冷却设置点**。只改上面 4 处，自动历练会被下列快路径绕过
#       （尤其「天地之魄·自动模式跳过」在 !M&&j 分支里把间隔压回 0.5s），
#       整体速率降不到一半。故统一 ×2。
# 锚点均实测 count==1（基线 build/assets/index-v28-20260928.js）。

# 挑战 boss 初始化后（onBattleInitialized 回调之后）
A_ADV_BOSSINIT = 'c(!1)}}),d(.5),{resu'
R_ADV_BOSSINIT = 'c(!1)}}),d(1),{resu'

# 天地之魄 · 自动模式跳过（`!M&&j` 分支）
A_ADV_TDP_SKIP = 'c(!1),d(.5);return'
R_ADV_TDP_SKIP = 'c(!1),d(1);return'

# 天地之魄 · 战后 finally
A_ADV_TDP_FIGHT = 'c(!1),d(2)'
R_ADV_TDP_FIGHT = 'c(!1),d(4)'

# 天地之魄 · 玩家选择避开
A_ADV_TDP_AVOID = 'c(!1),d(.2),R&&E'
R_ADV_TDP_AVOID = 'c(!1),d(.4),R&&E'

# 商店访问（setTimeout(...,3e2) 之后）
A_ADV_SHOPVISIT = 'v(ee),c(!1),d(.5)},3e2'
R_ADV_SHOPVISIT = 'v(ee),c(!1),d(1)},3e2'

# ★★ 2026-09-30 约束权移交（`yl_cooldown_ext.py` 冷却修复环，接线在本模块之后）★★
#   本模块的**替换值**（上面的 R_ADV_*）必须保持 0.8.3 的 ×2 形态不动 ——
#   它们同时是 cooldown 环的锚点（改了会让 cooldown 环 count=0 直接失败）。
#   但 cooldown 环随后会把 9 个历练冷却**还原成上游原版口径**（1/1/2/2/2/1/2/1/2），
#   ⇒ 下面 5 条门禁的断言串改用「最终形态」，语义不变（仍是「该冷却点已被改到位」）。
#   上游原版依据：`views/adventure/useAdventureHandlers.ts` @b822f2d（行号见 cooldown 环 docstring）。
R_ADV_BOSSINIT_FINAL  = 'c(!1)}}),d(2),{resu'     # 上游 :386  setCooldown(2)
R_ADV_TDP_SKIP_FINAL  = 'bossId:le,difficulty:h}),c(!1),d(1);return}'   # 上游 :427 setCooldown(1)（与 0.8.3 相同）
R_ADV_TDP_FIGHT_FINAL = '}).finally(()=>{c(!1),d(2)})'                  # 上游 :420 setCooldown(2)
R_ADV_TDP_AVOID_FINAL = 'c(!1),d(1),R&&E'         # 上游 :425-427 setCooldown(1)
R_ADV_SHOPVISIT_FINAL = 'v(ee),c(!1),d(2)},3e2'   # 上游 :181  setCooldown(2)

# 历史注释（来历说明）
A_COMMENT_MAIN = (
    '/* yl-exp: \u5386\u7ec3\u5355\u6b21\u95f4\u9694 cooldown .5\u21923 \u79d2\uff08\u81ea\u52a8\u5386\u7ec3\u8282\u6d41\uff1b'
    '\u540c\u6b65\u8c03\u6574\uff1a\u5546\u5e97\u8df3\u8fc7 d(.2)\u2192d(3)\u3001\u907f\u6218 d(1)\u2192d(3)\u3001'
    '\u6218\u540e\u6062\u590d AUTO_ADVENTURE_RESUME_DELAY 300\u21923e3\uff09 */'
)
# 注：新注释**刻意不写 d(N) 字面量**，以免日后 grep `d(3)` 时把注释误当残留代码。
# 注：本字符串用**字面中文**书写（文件头已声明 utf-8；bundle 本身即 UTF-8 文本，
#     插入中文合法）。刻意**不含** `d(数字)` 形态、也不含 `setCooldown` 标识符，
#     以免污染其它模块基于这些串做的计数门禁。
R_COMMENT_MAIN = (
    '/* yl-exp: 历练单次间隔 cooldown .5→3 秒（0.8.2）→ 3→6 秒 ×2（0.8.3 cli-flow ⑤）'
    '（自动历练节流；本次统一 ×2 覆盖历练组件内全部 9 个冷却设置点：'
    '避战 A 内 / 避战 DS 分支 / 正常收尾 finally / 商店跳过 / 挑战初始化 / '
    '天地之魄 跳过·战后·避开 / 商店访问；'
    '打坐冷却 1 秒不动；单次收益不动、每分钟收益减半） */'
)

# 结算展示注释里对 cooldown 的交叉引用（改成 6，避免留下过期指引）
A_COMMENT_SETTLE = '\u5386\u7ec3\u95f4\u9694\u89c1\u4e0b\u65b9 finally cooldown=3'
R_COMMENT_SETTLE = '\u5386\u7ec3\u95f4\u9694\u89c1\u4e0b\u65b9 finally cooldown=6'

# --------------------------------------------------------------------------- ⑥ 去信箱
# 两处空 go（YlxwPanelModal + YlxwFuseOne，形态完全一致）⇒ 一并接上 YlxwOpen
A_GO_EMPTY = 'go: function () {}, player: YlxwPlayer() }'
R_GO_EMPTY = 'go: function (k) { YlxwOpen(k); }, player: YlxwPlayer() }'

# --------------------------------------------------------------------------- ⑦ 仙务块置顶
# 外壳内容区：仙务块从「页尾」改为「页首」
A_FUSE_CHILDREN = 'children:[l,__xw?e.jsx(YlxwFuse,{k:__xw}):null]'
R_FUSE_CHILDREN = 'children:[__xw?e.jsx(YlxwFuse,{k:__xw}):null,l]'

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含改名 + 全部 v28 前置模块）；ctx = {'zh': zh, 'base_text': str}"""
    # zh 本批次未用（无注入）；保留形参以对齐模块契约
    _ = ctx['zh']

    # ---------- ⑤ 历练间隔 ×2：4 个同步点 3 → 6 ----------
    p.replace(
        'f5-adv-avoid-a', A_ADV_AVOID_A, R_ADV_AVOID_A, expect=1,
        note='历练·A 内避战：冷却 3→6 秒'
    )
    p.replace(
        'f5-adv-avoid-ds', A_ADV_AVOID_DS, R_ADV_AVOID_DS, expect=1,
        note='历练·DS 分支避战：冷却 3→6 秒'
    )
    p.replace(
        'f5-adv-finally', A_ADV_FINALLY, R_ADV_FINALLY, expect=1,
        note='历练·正常收尾 finally：冷却 3→6 秒（打坐不在此处）'
    )
    p.replace(
        'f5-adv-shopskip', A_ADV_SHOPSKIP, R_ADV_SHOPSKIP, expect=1,
        note='历练·商店跳过：冷却 3→6 秒'
    )
    # ---- ⑤b 同组件内其余 5 个快返回路径，统一 ×2（否则自动历练被绕过）----
    p.replace(
        'f5-adv-bossinit', A_ADV_BOSSINIT, R_ADV_BOSSINIT, expect=1,
        note='历练·挑战 boss 初始化后：冷却 .5→1 秒'
    )
    p.replace(
        'f5-adv-tdp-skip', A_ADV_TDP_SKIP, R_ADV_TDP_SKIP, expect=1,
        note='历练·天地之魄 自动模式跳过（!M&&j）：冷却 .5→1 秒'
    )
    p.replace(
        'f5-adv-tdp-fight', A_ADV_TDP_FIGHT, R_ADV_TDP_FIGHT, expect=1,
        note='历练·天地之魄 战后 finally：冷却 2→4 秒'
    )
    p.replace(
        'f5-adv-tdp-avoid', A_ADV_TDP_AVOID, R_ADV_TDP_AVOID, expect=1,
        note='历练·天地之魄 玩家避开：冷却 .2→.4 秒'
    )
    p.replace(
        'f5-adv-shopvisit', A_ADV_SHOPVISIT, R_ADV_SHOPVISIT, expect=1,
        note='历练·商店访问（setTimeout 3e2 后）：冷却 .5→1 秒'
    )
    p.replace(
        'f5-comment-main', A_COMMENT_MAIN, R_COMMENT_MAIN, expect=1,
        note='更新历史注释锚：写清 0.8.2 .5→3、0.8.3 3→6 的来历'
    )
    p.replace(
        'f5-comment-settle', A_COMMENT_SETTLE, R_COMMENT_SETTLE, expect=1,
        note='结算展示注释里的 cooldown=3 交叉引用同步为 6'
    )

    # ---------- ⑥ 去信箱：两处空 go 接上 YlxwOpen ----------
    p.replace(
        'f6-go-empty', A_GO_EMPTY, R_GO_EMPTY, expect=2,
        note='YlxwPanelModal + YlxwFuseOne 的 go 由空函数改为 YlxwOpen(k)'
    )

    # ---------- ⑦ 仙务块置顶：外壳内容区 [l, Fuse] → [Fuse, l] ----------
    p.replace(
        'f7-xw-first', A_FUSE_CHILDREN, R_FUSE_CHILDREN, expect=1,
        note='仙务融合块从内容区末尾移到最上方（9 个融合页共用此唯一落点）'
    )

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- ⑤ 历练间隔 ×2（★ 2026-09-30 约束权移交：cooldown 环已把值还原为上游原版）----
        ('F5·避战 d(1)（A内+DS分支，上游原版）', 'a("' + '\u4f60\u9009\u62e9\u907f\u5f00\u6218\u6597\uff0c\u7ee7\u7eed\u5386\u7ec3' + '...","normal"),c(!1),d(1)', 2, '==', 'cooldown 环还原上游 :143/:267'),
        ('F5·正常收尾 d(10)（R-117 2026-10-02 定）', 'finally{c(!1),d(10)}', 1, '==', 'cooldown 还原上游 2 → R-042 改 3→4 → R-117 2026-10-02 调 10（属主侧放宽）'),
        ('F5·商店跳过 d(2)（上游原版）', 'a("' + '\u4f60\u9009\u62e9\u8df3\u8fc7\u5546\u5e97\uff0c\u7ee7\u7eed\u5386\u7ec3' + '...","normal"),c(!1),d(2);', 1, '==', 'cooldown 环还原上游 :181'),
        ('F5·历练 d(10) 已回来',        'c(!1),d(10)', 1, '==', 'R-042 引入后 2026-10-01 调 4，R-117 2026-10-02 调 10（属主侧放宽）'),
        ('F5·历练 d(6) 已清零',        'c(!1),d(6)', 0, '==', 'cooldown 环已还原上游原版，不得残留'),
        # ---- ⑤b 补齐的 5 个快返回路径（★ 门禁断言用「cooldown 环之后」的最终形态）----
        ('F5b·挑战初始化 d(2)（上游原版）', R_ADV_BOSSINIT_FINAL,  1, '==', ''),
        ('F5b·天地之魄跳过 d(1)',       R_ADV_TDP_SKIP_FINAL,  1, '==', '上游原版亦为 1'),
        ('F5b·天地之魄战后 d(2)（上游原版）', R_ADV_TDP_FIGHT_FINAL, 1, '==', ''),
        ('F5b·天地之魄避开 d(1)（上游原版）', R_ADV_TDP_AVOID_FINAL, 1, '==', ''),
        ('F5b·商店访问 d(2)（上游原版）', R_ADV_SHOPVISIT_FINAL, 1, '==', ''),
        ('F5b·旧 挑战初始化已清零',     A_ADV_BOSSINIT,  0, '==', ''),
        ('F5b·旧 天地之魄跳过已清零',   A_ADV_TDP_SKIP,  0, '==', ''),
        # ★ 2026-09-30：原 `('F5b·旧 天地之魄战后已清零', A_ADV_TDP_FIGHT, 0)` 已作废 ——
        #   `A_ADV_TDP_FIGHT`(= `c(!1),d(2)`) 是 0.8.2 基线值，而 cooldown 环把上游原版值
        #   还原为 2 ⇒ 该串**重新出现是预期**。改由 cooldown 环断言 `d(4)` 已清零。
        ('F5b·旧 天地之魄避开已清零',   A_ADV_TDP_AVOID, 0, '==', ''),
        ('F5b·旧 商店访问已清零',       A_ADV_SHOPVISIT, 0, '==', ''),
        ('F5b·新注释不含 setCooldown',  'setCooldown',  12, '==', '基座 12；注释不得新增该标识符'),
        ('F5·打坐 cooldown（R-022 已接管）', 'M(2)', 1, '==', 'econ2 改 handleMeditate 后 setCooldown(2)'),
        ('F5·历练 handler 未破坏',      'handleAdventure:async()=>{if(u||f>0)return;', 1, '==', ''),
        ('F5·toFixed(3) 未误伤',        'toFixed(3)', 11, '==', '11 处假命中保持原样'),
        ('F5·d(3) 计数（主循环改 4 后 -1）', 'd(3)', 11, '==', '17-4 历练-2 旧注释+R-042，主循环那条已变 d(4)'),
        ('F5·历史注释已更新',           '0.8.3 cli-flow', 1, '==', '3→6 来历'),
        ('F5·结算注释同步',             '\u5386\u7ec3\u95f4\u9694\u89c1\u4e0b\u65b9 finally cooldown=2', 1, '==', 'cooldown 环已同步注释'),
        # ---- ⑥ 去信箱 ----
        ('F6·go 已接 YlxwOpen',         R_GO_EMPTY, 2, '==', 'PanelModal + FuseOne'),
        ('F6·空 go 已清零',             'go: function () {}', 0, '==', ''),
        ('F6·YlxwOpen 定义仍在',        'function YlxwOpen(k)', 1, '==', ''),
        # ★ 2026-09-29 lead 裁定：0.8.8「T9 仙途任务活跃度」客户端（yl_t9quest_ext）在
        #   6 档宝箱卡上新增了第 4 个「去信箱」入口（引导玩家领奖），把下面两条**绝对计数**
        #   从 3 顶到 4。原 `== 3` 属脆弱写法 —— 本门禁的意图是「存量 3 处没被删」，
        #   而不是「全站恰好 3 处」。故放宽为 `>= 3`：既保住回归保护，又不拦住合理新增。
        #   （T9 侧另有自己的门禁 `基线·邮件跳转按钮仍在` 钉死存量 3 处守恒，两侧不冲突。）
        ('F6·存量「去信箱」按钮未被删', '\\u53bb\\u4fe1\\u7bb1', 3, '>=', '存量 3 仍在；T9 新增第 4 处不算回归'),
        ('F6·存量 t("mail") 未被删',    't("mail")', 3, '>=', '存量 3 仍在；T9 新增第 4 处不算回归'),
        ('F6·YlxwHub 仍为死代码',       'function YlxwHub({', 1, '==', '定义 1、渲染 0'),
        # ---- ⑦ 仙务块置顶 ----
        # ★ 0.8.6 fun086（F6）会把 modal 内容区整体重写为「左列仙务块 / 右列页本体」两列网格
        #   ⇒ 0.8.3 的 R_FUSE_CHILDREN 字面形态在那之后不复存在。本条退为**形态无关**断言：
        #     旧顺序（页本体在前）必须为 0、Fuse 渲染点恰好 1 处。
        #   「仙务块先于页本体」的最终形态由 fun086 的 F6 门禁钉死
        #   （两列 class + 左列 min-w-0>Fuse + 右列 min-w-0>l + 非融合页直传 l）。
        ('F7·仙务块仍在内容区',         'e.jsx(YlxwFuse,{k:__xw})', 1, '==', '唯一渲染点'),
        ('F7·旧顺序已清零',             A_FUSE_CHILDREN, 0, '==', ''),
        ('F7·外壳 memo 未动',           'ct=O.memo(wN)', 1, '==', ''),
        ('F7·gongfa 融合',              'xw:"gongfa"', 1, '==', ''),
        # ★ 0.8.8 item18（yl_fun086_ext F7）：丹房本体是「宽屏多列」布局，被 F6 的 1:1 等分网格
        #   压到 543px ⇒ 用户报「炼丹炼器右侧 UI 被挤压」。修法 = 丹房去掉 xw 键、改由 L4 自己
        #   渲染仙务块（固定 320px 左列 + flex-1 右列）。故本条 1 → 0，并新增下一条钉死新形态。
        ('F7·alchemy 融合键已移交 L4',  'xw:"alchemy"', 0, '==', '0.8.8 item18：见 yl_fun086_ext F7'),
        ('F7·alchemy 仙务块由 L4 渲染', 'e.jsx(YlxwFuse,{k:"alchemy"})', 1, '==', '0.8.8 item18'),
        # ★ R-065（yl_065_ext）：宗门弹窗未入宗分支摘掉 xw:"sect" 融合标记（仙盟走独立按钮），
        #   本条断言的「中间形态字面串」被合法改写打破 ⇒ 1 → 0（先例：上面 alchemy item18 / SKILL §22.5）
        ('F7·sect 融合键已摘除',        'xw:"sect"', 0, '==', 'R-065：见 yl_065_ext'),
        ('F7·dungeon 融合',             'xw:"dungeon"', 1, '==', ''),
        ('F7·ach 融合',                 'xw:"ach"', 1, '==', ''),
        ('F7·pet 融合',                 'xw:"pet"', 1, '==', ''),
        ('F7·farm 融合',                'xw:"farm"', 1, '==', ''),
        ('F7·rebirth 融合',             'xw:"rebirth"', 1, '==', ''),
        ('F7·角色系统 titles+stats',    'xw:["titles","stats"]', 1, '==', '第 9 个融合页'),
    ]
    return gates
