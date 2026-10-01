# -*- coding: utf-8 -*-
r"""
yl_gongfa_ext.py — 0.8.12 批次 · R-016 功法按战斗技能类型分类 + 战斗技能效果展示（客户端 · impl-gongfa）

=========================================================================== 需求口径（用户原文）
> 自带的功法系统，我看战斗时是可以使用技能的，因此把功法类型调整一下，心法分类保留，
> 把「体术」分类去掉，完全按照技能类型分类。默认功法只展示了加角色的数值属性，
> 把战斗技能效果描述也加进去。

拆成三件事：
  ① 分类调整：保留「心法」，去掉「体术」，改按**战斗技能类型**分类；
  ② 每张功法卡补「战斗技能」区块（技能名 / 类型 / 描述 / 数值）；
  ③ 若战斗系统里功法效果本就没实现 → 出设计案。**侦察结论：已实现**（见下），故不新增数值。

=========================================================================== 侦察结论（决定性，别再重查）
原生功法阁组件 = `z4=({isOpen,onClose,player,onLearnArt,onActivateArt})=>{…}`，
  memo 为 `H4=Rt.memo(z4)`，渲染点 1 处：`d.isCultivationOpen&&e.jsx(H4,{…})`（@1201130，非死代码）。
面板「类型筛选」行：`["all","mental","body"]` → 全部 / 心法 / 体术；
卡片类型徽标：`g.type==="mental"?"心法":"体术"`。

**功法的战斗技能是「已经实现了的」**，来源两处（都在游戏本体里，本模块只读不改）：
  (a) 手写技能表 `og={ "art-xxx":[{id,name,description,type,cost,cooldown,maxCooldown,target,…}] }`
      —— 9 部功法有专属技能：art-thunder-sword / art-immortal-life / art-fiery-fist /
         art-pure-yang / art-wind-step / art-water-mirror / art-earth-shield /
         art-dragon-fist / art-star-destruction。
  (b) 生成器 `GS(art)`（@653567，被 `QS` 调用）—— 其余功法按 type/grade 现场生成：
        body           → `type:"attack"`（物理）
        mental + expRate → `type:"buff"`（攻击力增益）
        mental 无 expRate → `type:"attack"`（法术）
  战斗入口 `QS(player)`：`t.cultivationArts.forEach(N=>{ const k=og[N]; if(k) … else GS(…) })`
  ⇒ **每一部已习得功法都会在战斗里变成一个技能**，与用户直觉一致。
  ⇒ 因此本模块**不发明任何数值**，只把「已经在战斗里生效的技能」渲染出来。

类型分布（82 部功法，按 og 覆盖后的真实技能类型统计）：
  攻击 attack 54 · 辅助 buff 27 · 治疗 heal 1（长生诀）。
  ★ 值得注意：御风步 / 厚土护体是 `body`（旧「体术」）却给 **buff** 技能；
    长生诀是 `mental`（旧「心法」）却给 **heal** 技能 ⇒ 旧 心法/体术 二分确实失真，用户判断正确。

分类落法（**保留心法 + 按技能类型**，语义为「标签」而非互斥分组）：
  筛选按钮：全部 / 心法 / 攻击 / 辅助 / 治疗
    心法 → `art.type==="mental"`（26 部，**保留**）
    攻击/辅助/治疗 → 该功法战斗技能的首个 skill.type
  卡片徽标：`mental` 保留「心法」徽标，**所有**功法再挂一枚技能类型徽标（攻击/辅助/治疗）。
    ⇒ 旧「体术」徽标消失；`body` 功法改由技能类型标识；`mental` 的心法身份不丢。
  ★ 说明：心法(26) 与 辅助(25)/治疗(1) 存在重叠（心法本就走 buff/heal 路线）。
    若产品希望**互斥**（心法 = 全部 mental；body 按技能类型分），改 `YlxwGongfaFilterHit`
    一处即可（见文件尾注释），本模块已把它抽成单点函数。

=========================================================================== 门禁计数清单（给接线人入 dryrun）
  ① 'function YlxwGongfaSkillList('                                基线 0 → 改后 1
  ② 'function YlxwGongfaSkillBlock('                               基线 0 → 改后 1
  ③ '["all","mental","attack","buff","heal"].map('                 基线 0 → 改后 1
  ④ '["all","mental","body"].map('                                 基线 1 → 改后 0（旧分类已清除）
  ⑤ 'children:g.type==="mental"?"心法":"体术"'                      基线 1 → 改后 0（旧徽标已清除）
  ⑥ ',YlxwGongfaSkillBlock(g)]}),e.jsx("div",{className:"flex items-center justify-end'  基线 0 → 改后 1
  ⑦ 'children:"技能类型："'                                         基线 0 → 改后 1
  ⑧ 旧 intro 体术文案清零 / 新文案在位
  ⑨ 战斗逻辑零改动断言：'t.cultivationArts.forEach(N=>{const k=og[N];' 恒 1（对照面）

=========================================================================== 技术约束遵守
· 注入块经 zh() 后无非 ASCII；不含 V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/auth_token/X-YL-）。
· 所有新 Tailwind 类均已对编译后 CSS（build/assets/index-ZuV-l8Gt.css）逐条核对存在（见报告）。
· 注入点唯一（expect=1）；apply() 返回门禁五元组列表；本文件不写任何产物。
· 不改战斗结算（QS/X0/uM…）、不改 og/GS、不新增网络调用、不改服务端。
"""

# --------------------------------------------------------------------------- 锚点（全部照抄 v2811 产物的精确字节，唯一性见门禁）

_A_INJECT = 'function YlxwPanelModal(p) {'

_A_FILTER_OLD = (
    '["all","mental","body"].map(g=>e.jsx("button",{onClick:()=>v(g),className:'
    '`px-2 py-1 rounded text-xs transition-colors ${f===g?g==="mental"?"bg-blue-700 text-blue-200":'
    'g==="body"?"bg-red-700 text-red-200":"bg-mystic-jade text-white":'
    '"bg-stone-700 text-stone-400 hover:bg-stone-600"}`,'
    'children:g==="all"?"\u5168\u90e8":g==="mental"?"\u5fc3\u6cd5":"\u4f53\u672f"},g))'
)
_A_FILTER_NEW = (
    '["all","mental","attack","buff","heal"].map(g=>e.jsx("button",{onClick:()=>v(g),className:'
    '`px-2 py-1 rounded text-xs transition-colors ${f===g?g==="mental"?"bg-blue-700 text-blue-200":'
    'g==="attack"?"bg-red-700 text-red-200":g==="buff"?"bg-green-700 text-green-200":'
    'g==="heal"?"bg-purple-700 text-purple-200":"bg-mystic-jade text-white":'
    '"bg-stone-700 text-stone-400 hover:bg-stone-600"}`,'
    'children:g==="all"?"\u5168\u90e8":g==="mental"?"\u5fc3\u6cd5":'
    'g==="attack"?"\u653b\u51fb":g==="buff"?"\u8f85\u52a9":"\u6cbb\u7597"},g))'
)

_A_LABEL_OLD = 'children:"\u7c7b\u578b\u7b5b\u9009\uff1a"'
_A_LABEL_NEW = 'children:"\u6280\u80fd\u7c7b\u578b\uff1a"'

_A_PRED_OLD = 'if(d!=="all"&&A!==d||f!=="all"&&w.type!==f)return!1;'
_A_PRED_NEW = ('if(d!=="all"&&A!==d)return!1;'
               'if(f!=="all"&&!YlxwGongfaFilterHit(w,f))return!1;')

_A_BADGE_OLD = (
    'e.jsx("span",{className:`text-[10px] md:text-xs px-1.5 py-0.5 rounded border '
    '${g.type==="mental"?"border-blue-800 text-blue-300 bg-blue-900/20":'
    '"border-red-800 text-red-300 bg-red-900/20"}`,'
    'children:g.type==="mental"?"\u5fc3\u6cd5":"\u4f53\u672f"})'
)
_A_BADGE_NEW = (
    'e.jsxs(e.Fragment,{children:['
    'g.type==="mental"?e.jsx("span",{className:"text-[10px] md:text-xs px-1.5 py-0.5 rounded border '
    'border-blue-800 text-blue-300 bg-blue-900/20",children:"\u5fc3\u6cd5"}):null,'
    'e.jsx("span",{className:YlxwGongfaTypeCls(g),children:YlxwGongfaTypeLabel(g)})]})'
)

_A_SKILL_OLD = '"速度"]})]})]}),e.jsx("div",{className:"flex items-center justify-end sm:w-32 shrink-0 mt-2 sm:mt-0"'
_A_SKILL_NEW = ('"速度"]})]}),YlxwGongfaSkillBlock(g)]}),'
                'e.jsx("div",{className:"flex items-center justify-end sm:w-32 shrink-0 mt-2 sm:mt-0"')

_A_INTRO_OLD = 'e.jsx("p",{children:"\u4f53\u672f\uff1a\u8f85\u4fee\u529f\u6cd5\uff0c\u4e60\u5f97\u540e\u6c38\u4e45\u63d0\u5347\u8eab\u4f53\u5c5e\u6027\u3002"})'
_A_INTRO_NEW = 'e.jsx("p",{children:"\u6218\u6597\u6280\u80fd\uff1a\u6bcf\u90e8\u529f\u6cd5\u4e60\u5f97\u540e\u81ea\u52a8\u52a0\u5165\u6218\u6597\u6280\u80fd\u680f\uff0c\u6309\u6548\u679c\u5206\u4e3a \u653b\u51fb / \u8f85\u52a9 / \u6cbb\u7597\u3002"})'

# 对照面：战斗逻辑（QS 里 og/GS 的取用）必须逐字节未动
_A_BATTLE_REF = 't.cultivationArts.forEach(N=>{const k=og[N];'

# --------------------------------------------------------------------------- 注入块（纯 ASCII 载体，中文由 build 侧 zh() 转义）

INJECT_JS = r'''
/* ===== yl-0.8.12 R-016: 功法按战斗技能类型分类 + 战斗技能效果展示 =====
   战斗技能 100% 取自游戏本体，本模块只读不改：
     (a) 手写技能表 og[artId]（9 部功法有专属技能，含 治疗/辅助/攻击）
     (b) 生成器 GS(art)（其余功法按 type/grade 生成：body->攻击，mental+expRate->辅助）
   战斗入口 QS(player) 即用这两处 ⇒ 展示的就是战斗中真实可用的技能。 */
function YlxwGongfaSkillList(art) {
  try {
    if (!art) return [];
    var h = og[art.id];
    if (h && h.length) return h;
    var g = GS(art);
    return g ? [g] : [];
  } catch (e) { return []; }
}
function YlxwGongfaSkillType(art) {
  var l = YlxwGongfaSkillList(art);
  return (l.length && l[0] && l[0].type) ? l[0].type : "none";
}
/* 筛选命中：心法按功法 type，其余按战斗技能类型（单点函数，便于改互斥口径） */
function YlxwGongfaFilterHit(art, f) {
  if (!art) return false;
  if (f === "mental") return art.type === "mental";
  return YlxwGongfaSkillType(art) === f;
}
var YLXW_GONGFA_SKILL_LABEL = { attack: "\u653b\u51fb", buff: "\u8f85\u52a9", heal: "\u6cbb\u7597", none: "\u65e0\u6280\u80fd" };
var YLXW_GONGFA_SKILL_CLS = {
  attack: "border-red-800 text-red-300 bg-red-900/20",
  buff: "border-green-700 text-green-300 bg-green-900/20",
  heal: "border-purple-800 text-purple-300 bg-purple-900/20",
  none: "border-stone-700 text-stone-400 bg-stone-800"
};
function YlxwGongfaTypeLabel(art) {
  var t = YlxwGongfaSkillType(art);
  return YLXW_GONGFA_SKILL_LABEL[t] || YLXW_GONGFA_SKILL_LABEL.none;
}
function YlxwGongfaTypeCls(art) {
  var t = YlxwGongfaSkillType(art);
  return "text-[10px] md:text-xs px-1.5 py-0.5 rounded border "
    + (YLXW_GONGFA_SKILL_CLS[t] || YLXW_GONGFA_SKILL_CLS.none);
}
function YlxwGongfaSkillParams(sk) {
  var out = [];
  try {
    var c = sk.cost || {};
    if (sk.type === "attack" && sk.damage) {
      var d = sk.damage;
      out.push((d.type === "magical" ? "\u6cd5\u672f\u4f24\u5bb3 " : "\u7269\u7406\u4f24\u5bb3 ")
        + YlxwNum(d.base) + " x" + d.multiplier);
      if (d.critChance) out.push("\u66b4\u51fb\u7387 " + Math.round(d.critChance * 100) + "%");
    } else if (sk.type === "heal" && sk.heal) {
      out.push("\u6062\u590d\u6c14\u8840 " + YlxwNum(sk.heal.base)
        + " + \u6c14\u8840x" + Math.round(sk.heal.multiplier * 100) + "%");
    }
    if (sk.effects) {
      for (var i = 0; i < sk.effects.length; i++) {
        var ef = sk.effects[i] || {};
        var b = ef.buff, db = ef.debuff;
        if (b && b.description) out.push(b.description);
        if (db && db.description) out.push((db.name || "\u51cf\u76ca") + "\uff1a" + db.description);
      }
    }
    if (c.mana) out.push("\u7075\u529b " + YlxwNum(c.mana));
    if (sk.maxCooldown) out.push("\u51b7\u5374 " + YlxwNum(sk.maxCooldown) + " \u56de\u5408");
  } catch (e) {}
  return out;
}
function YlxwGongfaSkillBlock(art) {
  var list = YlxwGongfaSkillList(art);
  if (!list.length) return null;
  var rows = [];
  for (var i = 0; i < list.length; i++) {
    var sk = list[i];
    if (!sk) continue;
    var ps = YlxwGongfaSkillParams(sk);
    rows.push(e.jsxs("div", { className: "mt-1.5", children: [
      e.jsxs("div", { className: "text-[11px] md:text-xs", children: [
        e.jsx("span", { className: "text-mystic-gold font-bold", children: sk.name }),
        e.jsx("span", { className: "text-stone-500", children: " \u00b7 " + (YLXW_GONGFA_SKILL_LABEL[sk.type] || sk.type) })
      ] }),
      sk.description ? e.jsx("div", { className: "text-[11px] md:text-xs text-stone-400", children: sk.description }) : null,
      ps.length ? e.jsx("div", { className: "text-[10px] md:text-xs text-stone-500", children: ps.join(" \u00b7 ") }) : null
    ] }, "sk" + i));
  }
  return e.jsxs("div", { className: "mt-2 rounded border border-stone-700 bg-ink-900/50 p-2", children: [
    e.jsx("div", { className: "text-[10px] md:text-xs text-stone-400 mb-1",
      children: "\u6218\u6597\u6280\u80fd\uff08\u4e60\u5f97\u540e\u81ea\u52a8\u52a0\u5165\u6218\u6597\u6280\u80fd\u680f\uff09" }),
    rows
  ] });
}
'''

# --------------------------------------------------------------------------- 主入口


def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 0) 注入展示助手（函数声明，只引用本体的 og / GS / YlxwNum，调用期才求值）
    p.insert_before('gongfa-block', _A_INJECT, zh(INJECT_JS) + '\n',
                    expect=1, note='注入 R-016 功法技能展示助手（YlxwGongfaSkill*）')

    # 1) 类型筛选行：心法/体术 → 心法 + 技能类型
    p.replace('gongfa-filter-row', _A_FILTER_OLD, _A_FILTER_NEW, note='类型筛选改为 心法 + 攻击/辅助/治疗')
    p.replace('gongfa-filter-label', _A_LABEL_OLD, _A_LABEL_NEW, note='筛选行标题：类型筛选 → 技能类型')
    # 2) 筛选谓词：走单点函数（心法按 type，其余按技能类型）
    p.replace('gongfa-filter-pred', _A_PRED_OLD, _A_PRED_NEW, note='筛选谓词改走 YlxwGongfaFilterHit')
    # 3) 卡片徽标：去「体术」，保留「心法」，加技能类型徽标
    p.replace('gongfa-type-badge', _A_BADGE_OLD, _A_BADGE_NEW, note='徽标：心法保留 + 技能类型')
    # 4) 卡片尾部插入「战斗技能」区块（作为 flex-1 列的最后一个子元素）
    p.replace('gongfa-skill-block', _A_SKILL_OLD, _A_SKILL_NEW, note='每张功法卡补战斗技能区块')
    # 5) 面板顶部说明：体术说明 → 战斗技能说明
    p.replace('gongfa-intro', _A_INTRO_OLD, _A_INTRO_NEW, note='说明文案同步新分类')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- 注入块本体 ----
        ('R016·技能列表助手已定义',     'function YlxwGongfaSkillList(',                          1, '==', ''),
        ('R016·技能区块组件已定义',     'function YlxwGongfaSkillBlock(',                         1, '==', ''),
        ('R016·筛选单点函数已定义',     'function YlxwGongfaFilterHit(',                          1, '==', ''),
        ('R016·技能类型徽标助手',       'function YlxwGongfaTypeCls(',                            1, '==', ''),
        ('R016·og 手写技能表被复用',    'var h = og[art.id];',                                   1, '==', '9 部专属技能，游戏本体表'),
        ('R016·GS 生成器被复用',        'var g = GS(art);',                                      1, '==', '其余功法按 type/grade 生成'),
        ('R016·攻击徽标配色',           'attack: "border-red-800 text-red-300 bg-red-900/20"',   1, '==', ''),
        ('R016·辅助徽标配色',           'buff: "border-green-700 text-green-300 bg-green-900/20"', 1, '==', ''),
        ('R016·治疗徽标配色',           'heal: "border-purple-800 text-purple-300 bg-purple-900/20"', 1, '==', ''),
        ('R016·技能区块挂载',           ',YlxwGongfaSkillBlock(g)]}),e.jsx("div",{className:"flex items-center justify-end', 1, '==', ''),

        # ---- 分类调整（新写法在位 / 旧写法清零）----
        ('R016·新类型筛选行',           '["all","mental","attack","buff","heal"].map(',           1, '==', ''),
        ('R016·旧类型筛选行已清除',     '["all","mental","body"].map(',                          0, '==', ''),
        ('R016·筛选标题改技能类型',     'children:"\u6280\u80fd\u7c7b\u578b\uff1a"',              1, '==', '原生代码为真 UTF-8，非转义形态'),
        ('R016·旧筛选标题已清除',       'children:"\u7c7b\u578b\u7b5b\u9009\uff1a"',              0, '==', ''),
        ('R016·筛选谓词改单点函数',     'if(f!=="all"&&!YlxwGongfaFilterHit(w,f))return!1;',      1, '==', ''),
        ('R016·旧筛选谓词已清除',       'if(f!=="all"&&w.type!==f)return!1;',                     0, '==', ''),
        ('R016·心法徽标保留',           'children:"\u5fc3\u6cd5"}):null,',                         1, '==', 'mental 仍显示「心法」'),
        ('R016·技能类型徽标挂载',       'YlxwGongfaTypeLabel(g)})]})',                            1, '==', ''),
        ('R016·旧「体术」徽标已清除',   'children:g.type==="mental"?"\u5fc3\u6cd5":"\u4f53\u672f"', 0, '==', ''),
        ('R016·旧 intro 体术文案清零',  '"\u4f53\u672f\uff1a\u8f85\u4fee\u529f\u6cd5',              0, '==', ''),
        ('R016·新 intro 战斗技能文案',  '"\u6218\u6597\u6280\u80fd\uff1a\u6bcf\u90e8\u529f\u6cd5',   1, '==', ''),

        # ---- 对照面：战斗逻辑零改动 ----
        ('基线·QS 取 og/GS 逻辑未动',   _A_BATTLE_REF,                                           1, '==', '战斗侧零改动，本模块只读'),
        ('基线·og 手写技能表未动',      'og={"art-thunder-sword"',                                1, '==', ''),
        ('基线·技能生成器未动',         'function GS(t){var l;const r=IS[t.grade]||1',           1, '==', ''),
        ('基线·注入点未被破坏',         _A_INJECT,                                                1, '==', ''),
    ]
    return gates
