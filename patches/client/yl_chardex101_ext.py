# -*- coding: utf-8 -*-
r"""
yl_chardex101_ext.py — R-084 「人物志」与「道友图鉴 · 缘契」解耦（寻访不再灌入右侧人物志）

需求原文（台账 R-084，用户 2026-10-01，逐字）
--------------------------------------------------------------------------
  「人物志中之前完全搞错了。左侧"道友图鉴 · 缘契"是新增的系统，图鉴里面的人之前是有故事的，
    我意思图鉴里面的人到达道友缘契里程碑可以在图鉴里面领取奖励。右侧是人物志默认内容，
    里面人是通过游戏默认的渠道获取的，和左边道友图鉴 · 缘契是完全独立的两个系统，
    而不是像现在这样寻访的人直接加到右边了。左侧道友图鉴 · 缘契还是保留之前的，
    每个人有小传、秘辛。并且道友图鉴 · 缘契里面的人物每一段解锁的奖励是非常丰富的，
    因为这里面只能靠任务加缘契值，比较困难」

==========================================================================
一、改前数据流取证（基线 build/assets/index-v298-20261001.js 逐字节读出）
==========================================================================

【右侧「人物志」】= 组件 `Nk`（模态 `title:"人物志"`，@1961685）
  · 数据源：`const m = a.socialRelations || []`（玩家字段 `player.socialRelations`）
  · 列表 = m 按 favorability 排序；详情 = 选中项；详情内挂 `YlxwCharBondPanelT6`（师门任务
    R35 + 缘契里程碑 + 解锁档 + 小传/秘辛，全部以 `rel.id` / `rel.favorability` 为键）
  · ⇒ 右侧人物志 = `socialRelations` 的**唯一渲染面**。

【左侧「道友图鉴 · 缘契」】= 组件 `YlxwCharDexPanelT6`（挂在 Nk 左列）
  · 已识集合 `YlxwCharMet(p)` = `charDex.met` ∪ `socialRelations`（按 id 与 name 双匹配）
  · 缘契值（详情 `selBlock`）：`selRel = socialRelations.find(id===selEntry.id)`；
    `bond = selRel ? selRel.favorability : 0` —— **图鉴的缘契值直接读社会关系好感度**。
  · 里程碑/领奖：左侧只有「收集奖励」`YLXW_CHAR_DEX_MILE`（按已识**人数** 3/6/9/…/24 领奖，
    落 `charDex.claimed`）；**每个道友的「缘契里程碑」领奖入口只在右侧 BondPanelT6**。

【「寻访」handler】= `YlxwCharDexPanelT6.doVisit`（左侧图鉴按钮）与 `YlxwCharBoardR34.submit`
  （左侧寻访任务板，经 `YlxwRnPickVisit`）；两者最终都调 `YlxwCharMeet(prev, entry, gain, desc)`：
      function YlxwCharMeet(prev, entry, gain, desc) {
        … for(…) if (rels[i].id === entry.id) { hit = i; break; }
        if (hit < 0) { rels.push({ id, name, favorability, description, lastEncounterRealm }); }  ← ★ BUG 落点
        else { rels[hit].favorability += gain; }
        next = Object.assign({}, prev, { socialRelations: rels });
        …
      }
  ⇒ **`YlxwCharMeet` 把「寻访」到的道友 upsert 进 `player.socialRelations`**，
    而 `socialRelations` 正是右侧人物志的数据源 ⇒ 寻访的人「直接加到右边」。
    这就是用户报的核心 bug。同理 `charDex.met` 也被点亮（左侧图鉴，属预期）。

【缘契值 / 里程碑 / 领奖现状】
  · 缘契值 = `socialRelations[].favorability`（0~100 clamp），写入点 4 类：
    寻访（Meet）、R34 寻访任务（Meet）、R35 师门任务（favorability += gain）、
    赠灵石/赠物（Nk 内 $ / T 回调，已 `!1&&` 停用）。
  · 缘契里程碑表 `YLXW_CHAR_BOND_MILE = [25 相知/50 知己/75 莫逆/100 道侣]`，
    领取态落 `charDex.bond[relId][at]`，入口只在右侧 BondPanelT6（`claim(mile)`）。
  · 解锁档（R-059）`YLXW_CHAR_UNL` 4 档，领取态落 `charDex.unl[relId][at]`，同样只在右侧。
  · **左侧图鉴没有任何「按道友」的里程碑领奖入口**（用户诉求点 2 缺失）。

【已有相关补丁模块（先读后写，避免撞锚点）】
  · yl_char_ext.py（v28 本体）：定义 24 位图鉴表 / DexPanel / BondPanel / Meet / Met / RollTarget
    / Apply / DexV2 等；本模块的锚点全部落在其产物形态上。
  · yl_t6chardex_ext.py（0.8.7 T6）：把两块面板改写为 `…T6` 并在 Nk 内两列布局。
  · yl_renwu_ext.py（R-034/035）：左列寻访任务板 `YlxwCharBoardR34` + 右列师门任务
    `YlxwCharTasksR35`，两者都经 Meet / socialRelations.favorability 加缘契。
  · yl_059_ext.py（R-059）：寻访增益递减 `YlxwCharVisitGain` + 解锁档 2→4（手动领取）。
  · yl_068_ext.py（R-068）：被动偶遇降频（只改概率，不碰数据流）。
  · yl_bond_ext.py：羁绊 synergy 百分比，与本需求**零交集**（已 grep 复核）。
  ⇒ 本模块锚点：`YlxwCharMeet` 函数体（1）、图鉴 `selBlock` 三处（各 2 = 死面板 + T6）、
    插入点 `function YlxwCharEntry(id) {`（1）。全部与上述模块的锚区无重叠（实测见 __main__）。

==========================================================================
二、改后数据流
==========================================================================
  · `YlxwCharMeet`：命中已存在的社会关系（默认渠道结识者）→ **维持原样**（就地加好感，
    右侧联动不变）；未命中（图鉴独有）→ **不再 push 进 socialRelations**，改为把缘契值
    累加进 `charDex.aff[entryId]`（图鉴专属），并点亮 `charDex.met`。
    ⇒ 寻访 / R34 任务产生的道友**只出现在左侧图鉴**，右侧人物志保持「默认渠道」纯净。
  · 图鉴缘契值统一取值 `YlxwCharBondOf(p, id)` = `charDex.aff[id]` + 同 id 社会关系好感度。
    （两路互斥：默认渠道结识者走社会关系，图鉴独有者走 charDex.aff，不会双计；
      老档中「被寻访写进 socialRelations」的历史数据仍可被读取，向后兼容。）
  · 图鉴详情 `selBlock`：
      - 缘契值改取 `YlxwCharBondOf`；「未结识」判定改看 `charDex.met ∪ socialRelations`（`m`），
        使图鉴独有道友也能正确显示「缘契 N / 100」与正文（小传 / 轶事 / 秘辛）。
      - **新增「缘契里程碑」领奖 chips（图鉴内领奖，用户诉求点 2）**，4 档 25/50/75/100，
        幂等落 `charDex.dexmile[entryId][at]`（与右侧 `charDex.bond` **分开**，两系统独立）。
  · 奖励（用户诉求点 3「非常丰富」，缘契值只能靠任务累积）：
      相识 25 → 灵石×600 + 随机物品×3（行 4）
      相知 50 → 修为×2500 + 随机物品×4（行 5）
      莫逆 75 → 灵石×1500 + 随机物品×5（行 5）
      道侣 100 → 灵石×3000 + 修为×5000 + 随机物品×6（行 6）
    （灵石/修为按 `YLRF` 境界系数缩放；物品经既有 `YlxwCharRollRow` 掷取、`YlxwCharPushItems` 入包。
     对照右侧里程碑（R-036 定档 2/3/4/5 件、stones/exp=0），图鉴侧明显从厚。）

==========================================================================
三、做了哪几条
==========================================================================
  ✅ P1（必做）寻访不再写右侧人物志 —— 改 `YlxwCharMeet`：新道友落 `charDex.aff`，不 push
     `socialRelations`。覆盖左侧「寻访」按钮与「寻访任务板」两条产生点。
  ✅ P2（必做）左侧图鉴的缘契里程碑领奖入口 —— `selBlock` 内新增 4 档 chips + 领取函数。
  ✅ P3（可做）里程碑奖励调丰富 —— 独立 `YLXW_CHAR_DEXMILE` 表（灵石+修为+多件随机物品）。
  ✅ 图鉴小传 / 轶事 / 秘辛保留（`selBlock` 原 4 档文案不动，仅把门槛判定从 `selRel` 改 `selMet`）。

==========================================================================
四、没做哪几条 / 为什么
==========================================================================
  ⛔ 未改服务端 `srv/index_v28.ts`：本改动纯客户端（`player.charDex` / `socialRelations` 随既有
     `/api/save` 整包落库；服务端对 charDex / socialRelations 零命中）。**无需服务端改动。**
  ⛔ 未迁移老档历史数据：老档中「曾被寻访写进 socialRelations」的道友**仍留在右侧**（无法与
    默认渠道结识者可靠区分，硬删有丢失真实社会关系的风险）。改动仅对**新产生点**生效。
    若需清理历史数据，见下方「服务端/运维可选说明」。
  ⛔ 未改 Nk 右列空态文案（「点击下方【寻访】主动结识…」在解耦后已不准确）：该串被
     yl_t6chardex_ext / yl_068_ext 的门禁冻结（各断言 ==1），改动会连带打破其门禁计数，
     故留作**后续独立需求**（建议改为「多在历练中闯荡偶遇」）。已在汇报中标注。
  ⛔ 未新增 player **顶层**字段：新数据全部落在既有容器 `player.charDex` 之下
     （`charDex.aff`、`charDex.dexmile`），与 R-034(`board`/`tasks`)、R-059(`unl`)、
     T6(`demands`) 的既有惯例一致；读取一律 `|| {}` 容错，不破坏存档 schema。
  ⛔ 未动右侧 BondPanelT6 的师门任务 / 缘契里程碑 / 解锁档（默认渠道道友的养成面），
     未动 `YLXW_CHAR_BOND_MILE` / `YLXW_CHAR_DROP_N` / `YLXW_CHAR_DEX_MILE` 等被冻结的表。

==========================================================================
五、风险点
==========================================================================
  R1. 行为变更：寻访不再提升「右侧人际关系加成」（Nk 的 `h.expBonus` 等由 socialRelations 汇总）。
      这是解耦的**预期结果**（图鉴侧另有 `YlxwCharDexRate` 修炼加成，仍按 met 生效）。
  R2. 老档兼容：`charDex.aff` / `charDex.dexmile` 缺失时按 `{}` 处理；老档已寻访者仍在右侧（见四）。
  R3. 锚点依赖上游产物形态（T6 + R-059 的 selBlock 4 档文案）：**必须排在
      char / t6chardex / r059 / renwu / r068 之后**，否则锚点不匹配（Patcher 会 fail-fast 中止，不落盘）。
  R4. 死面板 `YlxwCharDexPanel`（0.8.7 起为死代码）与 T6 面板 selBlock 字节相同 ⇒ 本模块对
      selBlock 锚点用 `expect=2`（死 + T6 同改）。死面板永不渲染，运行时风险为零，仅语法面同改。

==========================================================================
六、装配顺序 / 自检
==========================================================================
  装配：本模块须置于 `V28_MODULES` 中 renwu / r059 / t6chardex / r068 **之后**（建议紧邻 numbal 之前）。
        import:  from yl_chardex101_ext import apply as v28_chardex101_apply  # noqa: E402
        entry :  ('chardex101', v28_chardex101_apply),
  自检：  python patches/client/yl_chardex101_ext.py
         （对 build/assets/index-v298-20261001.js 做改前锚点份数断言 + 内存副本应用 + 全量门禁 +
           node --check 产物级语法校验；不写任何产物盘。）
"""

INJECT_JS = r'''
/* == YL_CHARDEX101 == R-084 人物志（默认渠道）与 道友图鉴·缘契 解耦 */
/* 图鉴缘契值（0~100）：charDex.aff（寻访 / 图鉴任务累积，图鉴专属）
   + 同 id 社会关系好感度（默认渠道结识者）。两路互斥，不会双计。 */
function YlxwCharBondOf(p, id) {
  var aff = (p && p.charDex && p.charDex.aff) || {};
  var v = Number(aff[id]) || 0;
  var rels = (p && p.socialRelations) || [], i;
  for (i = 0; i < rels.length; i++) { if (rels[i] && rels[i].id === id) { v += Number(rels[i].favorability) || 0; break; } }
  return v;
}

/* 图鉴缘契里程碑奖励（R-084 定档）：缘契值只能靠寻访/任务累积，故奖励从厚——
   每档 = 灵石 + 修为 + 若干随机物品（行号越高越偏仙品）。领取态落 charDex.dexmile[entryId][at]，
   与右侧人物志的 charDex.bond 完全分开（两系统独立）。 */
var YLXW_CHAR_DEXMILE = [
  { at: 25,  label: "相识", stones: 600,  exp: 0,    n: 3, row: 4 },
  { at: 50,  label: "相知", stones: 0,    exp: 2500, n: 4, row: 5 },
  { at: 75,  label: "莫逆", stones: 1500, exp: 0,    n: 5, row: 5 },
  { at: 100, label: "道侣", stones: 3000, exp: 5000, n: 6, row: 6 }
];

function YlxwCharDexMileClaim(p, setP, log, setNotice, entry, at, rf) {
  if (!p || !entry) return;
  var mine = ((p.charDex && p.charDex.dexmile) || {})[entry.id] || {};
  if (mine[String(at)]) return;
  if (YlxwCharBondOf(p, entry.id) < at) return;
  var k = null, i;
  for (i = 0; i < YLXW_CHAR_DEXMILE.length; i++) { if (YLXW_CHAR_DEXMILE[i].at === at) { k = YLXW_CHAR_DEXMILE[i]; break; } }
  if (!k) return;
  var st = Math.round((k.stones || 0) * (rf || 1)), ex = Math.round((k.exp || 0) * (rf || 1));
  var items = k.n > 0 ? YlxwCharRollRow(k.row, k.n) : [];
  setP(function (prev) {
    if (YlxwCharBondOf(prev, entry.id) < at) return prev;   /* 守卫：缘契回退 / 关系变动 */
    var d = YlxwCharDexV2(prev.charDex);
    var dm = Object.assign({}, d.dexmile || {});
    var m2 = Object.assign({}, dm[entry.id] || {});
    if (m2[String(at)]) return prev;                        /* 幂等：连点不重发 */
    m2[String(at)] = true;
    dm[entry.id] = m2;
    d.dexmile = dm;
    var nx = Object.assign({}, prev, { charDex: d });
    if (st) nx.spiritStones = Math.max(0, (Number(prev.spiritStones) || 0) + st);
    if (ex) nx.exp = Math.max(0, (Number(prev.exp) || 0) + ex);
    if (items.length) nx.inventory = YlxwCharPushItems(prev.inventory, items);
    return nx;
  });
  var parts = [];
  if (st) parts.push("灵石 ×" + st);
  if (ex) parts.push("修为 ×" + ex);
  for (i = 0; i < items.length; i++) parts.push(items[i].name + " ×" + items[i].qty);
  log("【道友图鉴】" + entry.name + " 缘契达 " + at + "（" + k.label + "）：" + parts.join("、") + "。", "gain");
  if (setNotice) setNotice("🎉 " + entry.name + " 缘契达 " + at + "，图鉴奖励：" + parts.join("、"));
}

/* 图鉴详情「缘契里程碑」chips（与右侧里程碑 chips 同款交互，但落 charDex.dexmile） */
function YlxwCharDexMileChips(p, setP, log, setNotice, entry, bond, rf) {
  var out = [], claimed = ((p && p.charDex && p.charDex.dexmile) || {})[entry.id] || {}, i;
  for (i = 0; i < YLXW_CHAR_DEXMILE.length; i++) {
    (function (k) {
      var done = !!claimed[String(k.at)];
      var can = bond >= k.at;
      var hint = "灵石×" + Math.round((k.stones || 0) * (rf || 1)) + " 修为×" + Math.round((k.exp || 0) * (rf || 1)) + " 随机物品×" + k.n;
      out.push(e.jsx("button", {
        disabled: done || !can,
        onClick: function () { YlxwCharDexMileClaim(p, setP, log, setNotice, entry, k.at, rf); },
        className: "px-2 py-1 rounded border text-[10px] transition-colors " + (
          done ? "bg-emerald-900/20 border-emerald-700/50 text-emerald-300" :
          can ? "bg-amber-600 hover:bg-amber-500 border-amber-500 text-stone-900 font-bold" :
                "bg-stone-800 border-stone-700 text-stone-500"),
        title: done ? "已领取" : (can ? ("点击领取（" + hint + "）") : ("缘契达 " + k.at + " 可领")),
        children: (done ? "✓ " : "") + k.label + " " + k.at
      }, "ylxw-chardexmile-" + entry.id + "-" + k.at));
    })(YLXW_CHAR_DEXMILE[i]);
  }
  return out;
}
/* == end YL_CHARDEX101 == */
'''

# --------------------------------------------------------------------------- 锚点
# 基线 = build/assets/index-v298-20261001.js（2069009 chars）
# 2026-10-01 逐串 re.count 实测（全部与 __main__ 改前断言一致）：
#   A_ENTRY=1 / A_MEET=1 / A_SEL_BOND=2 / A_SEL_HDR=2 / A_SEL_DESC=2 / A_SEL_TAIL=2
#   新标识零碰撞：YlxwCharBondOf=0 / YLXW_CHAR_DEXMILE=0 / YlxwCharDexMileClaim=0 /
#                YlxwCharDexMileChips=0 / selMet=0 / charDex.aff=0 / dexmile=0

# ① 注入块落点：图鉴纯函数层（`function YlxwCharEntry(id) {`，实测 count=1）
A_ENTRY = 'function YlxwCharEntry(id) {'

# ② BUG 落点：YlxwCharMeet 函数体（全文唯一）——寻访「新道友」不再写 socialRelations
A_MEET = (
    'function YlxwCharMeet(prev, entry, gain, desc) {\n'
    '  if (!prev || !entry) return prev;\n'
    '  var rels = (prev.socialRelations || []).slice(), i, hit = -1, next, d, met;\n'
    '  for (i = 0; i < rels.length; i++) { if (rels[i] && rels[i].id === entry.id) { hit = i; break; } }\n'
    '  if (hit < 0) {\n'
    '    rels.push({\n'
    '      id: entry.id, name: entry.name,\n'
    '      favorability: Math.max(-100, Math.min(100, gain)),\n'
    '      description: desc || entry.desc, lastEncounterRealm: prev.realm\n'
    '    });\n'
    '  } else {\n'
    '    rels[hit] = Object.assign({}, rels[hit], {\n'
    '      favorability: Math.max(-100, Math.min(100, (Number(rels[hit].favorability) || 0) + gain)),\n'
    '      lastEncounterRealm: prev.realm\n'
    '    });\n'
    '  }\n'
    '  next = Object.assign({}, prev, { socialRelations: rels });\n'
    '  d = Object.assign({}, next.charDex || {});\n'
    '  met = Object.assign({}, d.met || {});\n'
    '  met[entry.id] = true;\n'
    '  d.met = met;\n'
    '  next.charDex = d;\n'
    '  return next;\n'
    '}'
)
R_MEET = (
    'function YlxwCharMeet(prev, entry, gain, desc) {\n'
    '  if (!prev || !entry) return prev;\n'
    '  var rels = (prev.socialRelations || []).slice(), i, hit = -1, next, d, met, aff;\n'
    '  for (i = 0; i < rels.length; i++) { if (rels[i] && rels[i].id === entry.id) { hit = i; break; } }\n'
    '  d = Object.assign({}, prev.charDex || {});\n'
    '  met = Object.assign({}, d.met || {});\n'
    '  met[entry.id] = true;\n'
    '  d.met = met;\n'
    '  if (hit >= 0) {\n'
    '    /* 已在默认渠道人物志中：就地增缘契（右侧联动保持不变） */\n'
    '    rels[hit] = Object.assign({}, rels[hit], {\n'
    '      favorability: Math.max(-100, Math.min(100, (Number(rels[hit].favorability) || 0) + gain)),\n'
    '      lastEncounterRealm: prev.realm\n'
    '    });\n'
    '    next = Object.assign({}, prev, { socialRelations: rels, charDex: d });\n'
    '  } else {\n'
    '    /* 图鉴独有：只落 charDex.aff，不再写入右侧人物志的社会关系（R-084 解耦） */\n'
    '    aff = Object.assign({}, d.aff || {});\n'
    '    aff[entry.id] = Math.max(-100, Math.min(100, (Number(aff[entry.id]) || 0) + gain));\n'
    '    d.aff = aff;\n'
    '    next = Object.assign({}, prev, { charDex: d });\n'
    '  }\n'
    '  return next;\n'
    '}'
)

# ③ 图鉴详情 selBlock（死面板 + T6 同文 ⇒ 各 expect=2）
#   ③a 缘契值取值：从 socialRelations 直读 → YlxwCharBondOf；并补 selMet（已识判定）
A_SEL_BOND = '  var bond = selRel ? (Number(selRel.favorability) || 0) : 0;'
R_SEL_BOND = ('  var bond = selEntry ? YlxwCharBondOf(p, selEntry.id) : 0;\n'
              '  var selMet = selEntry ? !!m[selEntry.id] : false;')

#   ③b 头部「缘契 N / 100」：selRel → selMet
A_SEL_HDR = r'children: selRel ? ("\u7f18\u5951 " + bond + " / 100") : "\u672a\u7ed3\u8bc6"'
R_SEL_HDR = r'children: selMet ? ("\u7f18\u5951 " + bond + " / 100") : "\u672a\u7ed3\u8bc6"'

#   ③c 相识档正文门槛：selRel → selMet
A_SEL_DESC = '    selRel\n      ? e.jsx("p", { className: "text-[11px] " + (bond >= 25'
R_SEL_DESC = '    selMet\n      ? e.jsx("p", { className: "text-[11px] " + (bond >= 25'

#   ③d 秘辛档之后追加「图鉴缘契里程碑」领奖 chips（新形态；旧形态收尾串清零）
A_SEL_TAIL = (r'bond >= 100 ? selEntry.secret : "\u7f18\u5951\u8fbe 100 \u89e3\u9501 \u00b7 \u5956\u52b1 '
              r'\u968f\u673a\u7269\u54c1\u00d73 \u4e0e\u7075\u77f3"'
              '\n    ] })\n  ] }) : null;')
R_SEL_TAIL = (r'bond >= 100 ? selEntry.secret : "\u7f18\u5951\u8fbe 100 \u89e3\u9501 \u00b7 \u5956\u52b1 '
              r'\u968f\u673a\u7269\u54c1\u00d73 \u4e0e\u7075\u77f3"'
              '\n    ] }),\n'
              '    selMet ? e.jsx("div", { className: "text-[10px] text-stone-500 pt-1", '
              'children: "缘契里程碑（到达即在图鉴领取 · 图鉴专属奖励）" }) : null,\n'
              '    selMet ? e.jsx("div", { className: "flex flex-wrap gap-1.5", '
              'children: YlxwCharDexMileChips(p, setP, log, setNotice, selEntry, bond, rf) }) : null\n'
              '  ] }) : null;')

BAN_PATTERNS = ['fetch(', 'localStorage', 'sessionStorage', 'auth_token',
                '/yl/api', 'iframe', 'postMessage', 'X-YL-', 'XMLHttpRequest',
                'Be.getState().setPlayer']


def _assert_block_clean(block):
    """注入块硬断言：zh() 后纯 ASCII + 禁用模式零命中。"""
    bad = [ch for ch in block if ord(ch) > 0x7F]
    if bad:
        raise ValueError('yl_chardex101_ext: 注入块 zh() 后仍含非 ASCII: %r' % (bad[:10],))
    for pat in BAN_PATTERNS:
        if pat in block:
            raise ValueError('yl_chardex101_ext: 注入块含禁用模式 %r' % pat)


def apply(p, ctx):
    """R-084 解耦落到 Patcher 上；返回 gates 列表（含冻结门禁）。"""
    zh = ctx['zh']

    block = zh(INJECT_JS)
    _assert_block_clean(block)
    r_meet = zh(R_MEET)
    r_tail = zh(R_SEL_TAIL)

    # 0) 注入块：YlxwCharBondOf / YLXW_CHAR_DEXMILE / 领取函数 / chips（图鉴纯函数层）
    p.insert_before('chardex101-block', A_ENTRY, block + '\n',
                    note='R-084 图鉴缘契值取值 + 图鉴缘契里程碑表/领取函数/chips')

    # ① 解耦核心：寻访「新道友」不再写 socialRelations（只落 charDex.aff）
    p.replace('chardex101-meet', A_MEET, r_meet, expect=1,
              note='R-084 YlxwCharMeet：图鉴独有道友改落 charDex.aff，不 push socialRelations')

    # ② 图鉴详情：缘契值取值 + 已识判定 + 里程碑领奖入口（死面板 + T6 同改，各 expect=2）
    p.replace('chardex101-sel-bond', A_SEL_BOND, R_SEL_BOND, expect=2,
              note='R-084 图鉴详情缘契值改取 YlxwCharBondOf + 补 selMet 已识判定')
    p.replace('chardex101-sel-hdr', A_SEL_HDR, R_SEL_HDR, expect=2,
              note='R-084 图鉴详情「缘契 N/100」判定 selRel→selMet')
    p.replace('chardex101-sel-desc', A_SEL_DESC, R_SEL_DESC, expect=2,
              note='R-084 图鉴详情相识档正文门槛 selRel→selMet')
    p.replace('chardex101-sel-tail', A_SEL_TAIL, r_tail, expect=2,
              note='R-084 图鉴详情追加「缘契里程碑」领奖 chips（图鉴内领奖）')

    gates = [
        # ================= 注入块本体（新形态 ==1） =================
        ('R084·图鉴缘契取值函数',   'function YlxwCharBondOf(', 1, '==', ''),
        ('R084·图鉴里程碑表',       'var YLXW_CHAR_DEXMILE = [', 1, '==', ''),
        ('R084·图鉴里程碑领取函数', 'function YlxwCharDexMileClaim(', 1, '==', ''),
        ('R084·图鉴里程碑 chips',   'function YlxwCharDexMileChips(', 1, '==', ''),
        ('R084·注入块结束标记',     '/* == end YL_CHARDEX101 ', 1, '==', ''),
        ('R084·图鉴缘契值读 charDex.aff', 'var aff = (p && p.charDex && p.charDex.aff) || {};', 1, '==', ''),
        # ================= 解耦核心（新形态 ==1 / 旧形态 ==0） =================
        ('R084·Meet 图鉴分支落 aff', 'd.aff = aff;', 1, '==', '寻访新道友只落 charDex.aff'),
        ('R084·Meet 图鉴分支不写关系', 'next = Object.assign({}, prev, { charDex: d });', 1, '==', '无 socialRelations 键'),
        ('R084·旧 Meet push 对象已清零', '      id: entry.id, name: entry.name,', 0, '==', '旧 push 字面量必须消失'),
        ('R084·旧 Meet 无条件写关系已清零', '  next = Object.assign({}, prev, { socialRelations: rels });', 0, '==', '旧收尾必须消失'),
        # ================= 图鉴详情（新形态 ==2 / 旧形态 ==0） =================
        ('R084·详情缘契值改取值函数×2', 'var bond = selEntry ? YlxwCharBondOf(p, selEntry.id) : 0;', 2, '==', '死面板 + T6'),
        ('R084·详情已识判定×2',     'var selMet = selEntry ? !!m[selEntry.id] : false;', 2, '==', ''),
        ('R084·详情头部判定×2',     R_SEL_HDR, 2, '==', ''),
        ('R084·详情相识档门槛×2',   R_SEL_DESC, 2, '==', ''),
        ('R084·里程碑 chips 挂载×2', 'YlxwCharDexMileChips(p, setP, log, setNotice, selEntry, bond, rf)', 2, '==', ''),
        ('R084·里程碑标题×2',       zh('缘契里程碑（到达即在图鉴领取 · 图鉴专属奖励）'), 2, '==', ''),
        ('R084·旧详情缘契取值已清零', A_SEL_BOND, 0, '==', ''),
        ('R084·旧详情头部判定已清零', A_SEL_HDR, 0, '==', ''),
        ('R084·旧详情相识档门槛已清零', A_SEL_DESC, 0, '==', ''),
        # ================= 冻结：两个系统各自的数据字段访问面 =================
        # 右侧人物志仍读 socialRelations（Nk 右列数据源不动）
        ('冻结·右列仍读 socialRelations', 'a.socialRelations||[]', 1, '==', 'Nk 右列数据源未动'),
        # 右侧 BondPanelT6 的缘契写入/里程碑/解锁档一字未动
        ('冻结·右列缘契里程碑表未动', 'var YLXW_CHAR_BOND_MILE = [', 1, '==', ''),
        ('冻结·右列里程碑领取入口×2', 'onClick: function () { claim(mile); },', 2, '==', '死面板 + T6'),
        ('冻结·右列落 charDex.bond', 'd0.bond = b;', 1, '==', '右侧里程碑领取态未动'),
        ('冻结·右列落 charDex.unl', 'd59.unl = u59;', 1, '==', 'R-059 解锁档未动'),
        ('冻结·右列师门任务未动', 'function YlxwCharTasksR35(', 1, '==', ''),
        ('冻结·R35/师门求物仍写社会关系', 'socialRelations: rels, charDex: d0 });', 2, '==', 'R35 师门任务 + BondPanelT6 求物交付'),
        # 左侧图鉴其余面不动
        ('冻结·左列寻访任务板未动', 'function YlxwCharBoardR34(', 1, '==', ''),
        ('冻结·图鉴已识集合未动', 'function YlxwCharMet(', 1, '==', ''),
        ('冻结·寻访抽签函数未动', 'function YlxwCharRollTarget(', 1, '==', ''),
        ('冻结·寻访递减函数未动', 'function YlxwCharVisitGain(', 1, '==', ''),
        ('冻结·结算助手未动', 'function YlxwCharApply(', 1, '==', ''),
        ('冻结·入包函数未动', 'function YlxwCharPushItems(', 1, '==', ''),
        ('冻结·DexV2 归一未动', 'function YlxwCharDexV2(', 1, '==', ''),
        ('冻结·图鉴收集奖励表未动', 'var YLXW_CHAR_DEX_MILE = [', 1, '==', ''),
        ('冻结·图鉴收集奖励入口未动', 'function doClaim(mile) {', 2, '==', '死面板 + T6'),
        ('冻结·人物志模态仍在', 'title:"人物志",titleIcon:e.jsx(um,{size:18})', 1, '==', ''),
        ('冻结·图鉴/缘契面板定义仍在', 'function YlxwCharDexPanelT6(', 1, '==', ''),
        ('冻结·缘契面板定义仍在', 'function YlxwCharBondPanelT6(', 1, '==', ''),
        # 数据字段访问次数：socialRelations（基线 33 → 本模块仅 +1：YlxwCharBondOf 的读取）
        ('冻结·socialRelations 访问点 = 基线+1', 'socialRelations', 34, '==',
         '基线 33；本模块仅新增 YlxwCharBondOf 的 1 处只读'),
        ('冻结·charDex.met 写入点未增', 'd.met = met;', 2, '==', 'Meet 1 + Apply 1（基线口径不变）'),
        ('冻结·charDex.claimed 未动', 'd.claimed = c;', 2, '==', '死面板 + T6 收集奖励'),
        ('冻结·charDex.demands 未动', 'd0.demands = dm0;', 2, '==', 'T6 师门求物（effect 补档 + 交付重掷）'),
    ]
    return gates


# ---------------------------------------------------------------- 自检

if __name__ == '__main__':
    import io
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from yl_patch import Patcher, Gates, zh, load_text  # noqa: E402

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    HERE = os.path.dirname(os.path.abspath(__file__))
    ROOT = os.path.dirname(os.path.dirname(HERE))
    prod = os.path.join(ROOT, 'build', 'assets', 'index-v298-20261001.js')
    base = load_text(prod)
    print('=== R-084 自检：宿主 %s' % os.path.basename(prod))
    print('  chars=%d' % len(base))

    # 改前锚点份数（含新标识零碰撞）
    pre = [
        ('A_ENTRY', A_ENTRY, 1), ('A_MEET', A_MEET, 1),
        ('A_SEL_BOND', A_SEL_BOND, 2), ('A_SEL_HDR', A_SEL_HDR, 2),
        ('A_SEL_DESC', A_SEL_DESC, 2), ('A_SEL_TAIL', A_SEL_TAIL, 2),
    ]
    for nm, s in [
        ('YlxwCharBondOf', 'YlxwCharBondOf'), ('YLXW_CHAR_DEXMILE', 'YLXW_CHAR_DEXMILE'),
        ('YlxwCharDexMileClaim', 'YlxwCharDexMileClaim'), ('YlxwCharDexMileChips', 'YlxwCharDexMileChips'),
        ('selMet', 'selMet'), ('charDex.aff', 'charDex.aff'), ('dexmile', 'dexmile'),
    ]:
        pre.append(('无碰撞·' + nm, s, 0))
    bad = 0
    print('=== 改前锚点份数 ===')
    for name, s, exp in pre:
        n = base.count(s)
        ok = n == exp
        bad += (not ok)
        print('  [%s] %-26s actual=%d expect=%d' % ('OK' if ok else 'FAIL', name, n, exp))
    print('  基线 socialRelations 计数 = %d（本模块预期 +1）' % base.count('socialRelations'))
    if bad:
        print('  [ABORT] 基线锚点份数与设计不符（%d 条）' % bad)
        sys.exit(2)

    print('=== 应用补丁（内存副本，不写盘）===')
    pt = Patcher(base, label='chardex101-selfcheck')
    gts = apply(pt, {'zh': zh, 'base_text': base})
    print(pt.report())

    # 引用核查：新代码调用的 Yl* 函数必须存在于基线（除本模块新定义）
    import re as _re
    newtxt = zh(INJECT_JS) + zh(R_MEET) + zh(R_SEL_TAIL)
    new_fns = set(_re.findall(r'function\s+(Yl\w+)\s*\(', newtxt))
    miss = [c for c in set(_re.findall(r'\b(Yl[A-Za-z]\w{2,40})\s*\(', newtxt))
            if c not in new_fns and base.count(c) == 0]
    if miss:
        print('  [ABORT] 新代码引用了基线中不存在的 Yl* 函数: %r' % (miss,))
        sys.exit(2)
    print('=== Yl* 引用核查 PASS：新增 %r' % sorted(new_fns))

    g = Gates(pt.text)
    for t in gts:
        name, s, expect, cmp, note = t[:5]
        g.check(name, s, expect, cmp, note, within=(t[5] if len(t) > 5 else None))
    print(g.report())
    ok = g.passed()
    print('门禁结果: %s' % ('PASS' if ok else 'FAIL'))

    # node --check 产物级语法校验
    if ok:
        import subprocess
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), 'yl_chardex101_selfcheck.js')
        with open(tmp, 'w', encoding='utf-8', newline='') as f:
            f.write(pt.text)
        node = os.environ.get('YL_NODE', 'node')
        try:
            r0 = subprocess.run([node, '--check', prod], capture_output=True, text=True, timeout=180)
            r1 = subprocess.run([node, '--check', tmp], capture_output=True, text=True, timeout=180)
            print('=== node --check 基线 rc=%s / 补丁后 rc=%s' % (r0.returncode, r1.returncode))
            if r1.returncode != 0:
                print(r1.stderr[:2000])
                ok = False
        except FileNotFoundError:
            print('  [WARN] 未找到 node，跳过 node --check')
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    print('自检结论: %s' % ('PASS' if ok else 'FAIL'))
    sys.exit(0 if ok else 1)
