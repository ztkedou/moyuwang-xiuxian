# -*- coding: utf-8 -*-
r"""
yl_064_ext.py — R-064 炼丹三修：出炉加丹道造诣（展示侧）+ 丹方数值透明化 + 丹方书获取途径

需求（需求台账_进行中.md:25，R-064，附图列空）
--------------------------------------------------------------------------
  「仙务·丹炉，炼丹出炉好像没加丹道造诣，而且什么丹方没有写丹药的具体作用和
  数值。丹炉这个可以增加一些丹药品种、数量以及丹方的获取途径。」

查证（本会话实测，bundle = build/assets/index-v28117-20261001.js，
       服务端 = srv/index_v28.ts）
--------------------------------------------------------------------------
  ① 出炉没加造诣 —— 根因在**服务端**：POST /api/alchemy/claim 全程只发
     「灵石×1.5 邮件 +（凝元丹）丹囊+1」，全文 0 处 alchemyLevel/alchemyProficiency
     （srv 探针实测 0 命中）。客户端丹房（handleCraft @766268）有完整熟练度入账
     （ug 表 + pm 门槛 @293419/293459），丹炉漏了。**服务端半边由 srv_patch_064.py
     落地**（本模块只接出炉回报的 toast 与展示）。
  ② 丹方没写作用/数值 —— 丹炉丹方书行只有「名·品阶·Lv·灵石·材料」；开炉预览
     有成功率/时长/纯度但**没有出炉产出、没有药效**（出炉=灵石×1.5 的契约也
     没写出来）。丹房弹窗配方卡有 description 文案但**无数值**。
  ③ 品种/数量/获取途径 —— 服务端 ALCHEMY_RECIPES 只有 3 方（聚气丹/凝元丹/破境丹）。

本模块动作（客户端 7 处替换，全部锚点 count==1）
--------------------------------------------------------------------------
  C0 注入 YLXW_PILL_FX / YLXW_PILL_FXN：药效数值格式化（effect/permanentEffect →
     「服用：修为+150｜永久：气血上限+50」）。def 对象直传；FXN 用基座 Qt(name)
     查表兜底（typeof 防卫，服务端未发 summary 时仍可显示）。
  C1 出炉 onClick 链 .then：claim 响应带 prof{gained,level,proficiency,nextAt,
     leveledUp} 时 toast「丹道造诣 +36（，升至第 N 层！）」。存档本体不动——
     服务端 updatePlayerSave 已落档并 gm_revision++，客户端按既有拉新档机制对齐。
  C2 开炉预览「丹方」格补药效行：rc.summary（服务端权威）优先，
     YLXW_PILL_FXN 兜底。
  C3 开炉预览网格补「出炉产出」行：灵石 ×floor(cost×yieldRate)（list 响应字段，
     缺省 1.5），凝元丹加注「+ 丹囊×1」——把 t17 以来从未明示的出炉契约写出来。
  C4/C5 丹方书行改双行：第一行原有（名·品阶·Lv·灵石·材料），第二行 =
     「药效：…」+「获取：造诣第 N 层解锁」（need 沿用原 unlockLevel 回落逻辑，
     服务端下发 unlockLevel 时直接用）。
  C6 丹房弹窗配方卡在 description 之下补一行药效数值（基座最小切口 1 处）。

  ★ 服务端半边（配方 3→9 方扩容 + 出炉熟练度入账 + 开炉造诣门槛权威化）在
    srv_patch_064.py，链序 = SRV_CHAIN 链尾（srv_patch_063.py 之后）。
  ★ 数值口径（AI 代决，详见 拍板/2026-10-01_*_R-064_*.md）：
    · 丹炉熟练度 = 方子档位基础(ug) ×1.2 —— 兑现 t17 玩法说明「丹炉造诣涨得快 20%」；
    · 新 6 方时长/灵石按「净收益 ≈83.3 灵石/分钟」定档，与既有 3 方同收益率，
      只扩便利性不通胀；YIELD_RATE=1.5 不动；
    · 获取途径 = 造诣层数解锁（服务端下发 unlockLevel + start 权威校验），
      不新增丹方道具/掉落系统（记为遗留扩展）。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 不碰 t17 已门禁面：YlxwAlcFire 表、开炉请求契约、成功率/纯度公式、
    玩法说明折叠块、旧函数本体（本模块 helpers 注入在其定义行**之前**）。
  · 不碰丹房 handleCraft 公式（Jb/Wb/pm/ug 四表只读冻结）。
  · 注入块 zh() 后纯 ASCII；无 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-。
  · 每个 replace expect=1；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py / localtest/ / deploy_v28/ / srv/index_v28.ts / 产物。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-0.8.12 R-064: 炼丹数值透明化助手（药效格式化，两系统共用） =====
   YLXW_PILL_FX(d)      ：丹药 def（含 effect/permanentEffect）→「服用：…｜永久：…」
   YLXW_PILL_FXN(name)  ：按药名查基座 Qt 表再格式化（defensive，查不到返回 ""）
   数值标签与丹房/服务端字段同源：exp修为 hp气血 maxHp气血上限 spirit神识
   physique体魄 attack攻击 defense防御 speed身法 lifespan寿命 maxLifespan寿命上限 */
function YLXW_PILL_FX(d) {
  try {
    if (!d) { return ""; }
    var L = {
      exp: "\u4fee\u4e3a", hp: "\u6c14\u8840", maxHp: "\u6c14\u8840\u4e0a\u9650",
      spirit: "\u795e\u8bc6", physique: "\u4f53\u9b44", attack: "\u653b\u51fb",
      defense: "\u9632\u5fa1", speed: "\u8eab\u6cd5",
      lifespan: "\u5bff\u547d(\u5e74)", maxLifespan: "\u5bff\u547d\u4e0a\u9650(\u5e74)"
    };
    var a = [], kk, fx = d.effect || {};
    for (kk in fx) { if (L[kk] && fx[kk]) { a.push(L[kk] + "+" + fx[kk]); } }
    var s = a.length ? "\u670d\u7528\uff1a" + a.join("\u00b7") : "";
    var b = [], pf = d.permanentEffect || {};
    for (kk in pf) {
      if (kk === "spiritualRoots") { b.push("\u4e94\u884c\u7075\u6839\u5404+" + ((pf[kk] && pf[kk].metal) || 0)); continue; }
      if (L[kk] && pf[kk]) { b.push(L[kk] + "+" + pf[kk]); }
    }
    if (b.length) { s += (s ? "\uff5c" : "") + "\u6c38\u4e45\uff1a" + b.join("\u00b7"); }
    return s;
  } catch (e9) { return ""; }
}
function YLXW_PILL_FXN(nm) {
  try { if (typeof Qt === "function") { return YLXW_PILL_FX(Qt(nm)); } } catch (e8) {}
  return "";
}
'''

# --------------------------------------------------------------------------- 锚点（全部取自当前 bundle 逐字字节，本会话探针验证 count==1）

# C1 出炉 onClick：claim 响应带 prof 时补 toast（服务端 srv_patch_064.py 下发）
CLAIM_OLD = r'''        g("cl" + T.slot, "/alchemy/claim", { slot: T.slot }, "\u5df2\u51fa\u7089");
      }, children: "\u51fa\u7089" });'''
CLAIM_NEW = r'''        g("cl" + T.slot, "/alchemy/claim", { slot: T.slot }, "\u5df2\u51fa\u7089").then(function (r6) {
        if (r6 && r6.prof && r6.prof.gained > 0) {
          var m6 = "\u4e39\u9053\u9020\u8be3 +" + r6.prof.gained + (r6.prof.leveledUp ? "\uff0c\u5347\u81f3\u7b2c " + r6.prof.level + " \u5c42\uff01" : "");
          try { if (typeof ia === "function") { ia(m6); } } catch (e6) {}
        }
      });
      }, children: "\u51fa\u7089" });'''

# C2 开炉预览·丹方格：品阶/灵石行下补药效行
RARITY_OLD = r'''        e.jsxs("div", { className: "mt-1.5 text-[11px] text-stone-500", children: [
          "\u54c1\u9636\uff1a", e.jsx("span", { className: "text-stone-300", children: rc.rarity || "\u666e\u901a" }),
          " \u00b7 \u7075\u77f3\uff1a", e.jsx("span", { className: "text-amber-300", children: YlxwNum(rc.cost) })
        ] })'''
RARITY_NEW = r'''        e.jsxs("div", { className: "mt-1.5 text-[11px] text-stone-500", children: [
          "\u54c1\u9636\uff1a", e.jsx("span", { className: "text-stone-300", children: rc.rarity || "\u666e\u901a" }),
          " \u00b7 \u7075\u77f3\uff1a", e.jsx("span", { className: "text-amber-300", children: YlxwNum(rc.cost) })
        ] }),
        e.jsx("div", { className: "mt-1 text-[11px] text-stone-400", children: "\u836f\u6548\uff1a" + (rc.summary || YLXW_PILL_FXN(rc.name) || "\u2014") })'''

# C3 开炉预览网格：品质区间行后补「出炉产出」行
TIER_OLD = r'''      e.jsxs("div", { className: "flex justify-between gap-2", children: [
        e.jsx("span", { className: "text-stone-500", children: "\u54c1\u8d28\u533a\u95f4" }),
        e.jsx("span", { className: "shrink-0 text-stone-300 font-mono", children: YlxwAlcTierName(pr[0]) + " ~ " + YlxwAlcTierName(pr[1]) })
      ] })
    ] }),'''
TIER_NEW = r'''      e.jsxs("div", { className: "flex justify-between gap-2", children: [
        e.jsx("span", { className: "text-stone-500", children: "\u54c1\u8d28\u533a\u95f4" }),
        e.jsx("span", { className: "shrink-0 text-stone-300 font-mono", children: YlxwAlcTierName(pr[0]) + " ~ " + YlxwAlcTierName(pr[1]) })
      ] }),
      e.jsxs("div", { className: "flex justify-between gap-2", children: [
        e.jsx("span", { className: "text-stone-500", children: "\u51fa\u7089\u4ea7\u51fa" }),
        e.jsx("span", { className: "shrink-0 text-amber-300 font-mono", children: "\u7075\u77f3 \u00d7" + YlxwNum(Math.floor((rc.cost || 0) * ((l && l.yieldRate) || 1.5))) + (rc.name === "\u51dd\u5143\u4e39" ? " + \u4e39\u56ca\u00d71" : "") })
      ] })
    ] }),'''

# C4 丹方书行·头：包一层双行容器
BOOK_HEAD_OLD = r'''    return e.jsx("div", { className: "py-1 border-b border-stone-800 last:border-0 " + (ok ? "" : "opacity-50"), children:
      e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: ['''
BOOK_HEAD_NEW = r'''    return e.jsx("div", { className: "py-1 border-b border-stone-800 last:border-0 " + (ok ? "" : "opacity-50"), children:
      e.jsxs("div", { children: [
      e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: ['''

# C5 丹方书行·尾：补第二行（药效 + 获取途径）
BOOK_TAIL_OLD = r'''        e.jsx("span", { className: "shrink-0 text-[11px] text-stone-500 max-w-[55%] truncate", children: im || "\u2014" })
      ] }) }, "bk" + k);'''
BOOK_TAIL_NEW = r'''        e.jsx("span", { className: "shrink-0 text-[11px] text-stone-500 max-w-[55%] truncate", children: im || "\u2014" })
      ] }),
      e.jsxs("div", { className: "mt-0.5 flex justify-between gap-2 flex-wrap text-[11px] text-stone-500", children: [
        e.jsx("span", { className: "min-w-0", children: "\u836f\u6548\uff1a" + (R.summary || YLXW_PILL_FXN(R.name) || "\u2014") }, "fx" + k),
        e.jsx("span", { className: "shrink-0", children: "\u83b7\u53d6\uff1a\u9020\u8be3\u7b2c " + need + " \u5c42\u89e3\u9501" }, "gv" + k)
      ] })
      ] }) }, "bk" + k);'''

# C6 丹房弹窗配方卡：description 下补药效数值行（基座最小切口）
DANFANG_OLD = 'children:W.result.description}),'
DANFANG_NEW = ('children:W.result.description}),'
               'e.jsx("p",{className:"text-[10px] text-amber-300/90 mb-2",children:YLXW_PILL_FX(W.result)||""}),')


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # C0 helpers：zh() 后纯 ASCII 自检 + 禁用模式自检（限注入块，不数全文——
    # 全文里基座/历史模块本就含 iframe 等串，数全文是自毁门禁）+ 注入在 YlxwTAlchemy 之前
    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r064 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for w in ('iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-'):
        if w in blk:
            raise AssertionError('r064 注入块含禁用模式: %r' % w)
    p.replace('r064-helpers', 'function YlxwTAlchemy(r) {',
              blk.rstrip() + '\nfunction YlxwTAlchemy(r) {', expect=1,
              note='注入 YLXW_PILL_FX/FXN 药效助手（在其前，本体不动）')

    p.replace('r064-claim-toast', CLAIM_OLD, CLAIM_NEW, expect=1,
              note='出炉响应带 prof 时 toast「丹道造诣 +N」')
    p.replace('r064-preview-fx', RARITY_OLD, RARITY_NEW, expect=1,
              note='开炉预览补药效行（summary 优先，Qt 表兜底）')
    p.replace('r064-yield-row', TIER_OLD, TIER_NEW, expect=1,
              note='开炉预览补「出炉产出」行（灵石×yieldRate；凝元丹加注丹囊）')
    p.replace('r064-book-head', BOOK_HEAD_OLD, BOOK_HEAD_NEW, expect=1,
              note='丹方书行改双行容器（头）')
    p.replace('r064-book-tail', BOOK_TAIL_OLD, BOOK_TAIL_NEW, expect=1,
              note='丹方书第二行：药效 + 获取途径（造诣解锁）')
    p.replace('r064-danfang-fx', DANFANG_OLD, DANFANG_NEW, expect=1,
              note='丹房弹窗配方卡补药效数值行')

    gates = [
        # ================= 本模块改动 =================
        ('R64·出炉领丹链 .then 已接',   '"/alchemy/claim", { slot: T.slot }, "\\u5df2\\u51fa\\u7089").then(function (r6) {', 1, '==', ''),
        ('R64·造诣 toast 文案',          '"\\u4e39\\u9053\\u9020\\u8be3 +" + r6.prof.gained', 1, '==', ''),
        ('R64·升层提示',                '"\\uff0c\\u5347\\u81f3\\u7b2c " + r6.prof.level + " \\u5c42\\uff01"', 1, '==', ''),
        ('R64·药效助手 FX 已注入',       'function YLXW_PILL_FX(d) {', 1, '==', ''),
        ('R64·药效兜底 FXN 已注入',      'function YLXW_PILL_FXN(nm) {', 1, '==', ''),
        ('R64·开炉预览药效行',           '"\\u836f\\u6548\\uff1a" + (rc.summary || YLXW_PILL_FXN(rc.name) || "\\u2014")', 1, '==', ''),
        ('R64·丹方书药效行',             '"\\u836f\\u6548\\uff1a" + (R.summary || YLXW_PILL_FXN(R.name) || "\\u2014")', 1, '==', ''),
        ('R64·获取途径行',              '"\\u83b7\\u53d6\\uff1a\\u9020\\u8be3\\u7b2c " + need + " \\u5c42\\u89e3\\u9501"', 1, '==', ''),
        ('R64·出炉产出行（灵石×收益率）', '"\\u7075\\u77f3 \\u00d7" + YlxwNum(Math.floor((rc.cost || 0) * ((l && l.yieldRate) || 1.5)))', 1, '==', ''),
        ('R64·凝元丹丹囊加注',           'rc.name === "\\u51dd\\u5143\\u4e39" ? " + \\u4e39\\u56ca\\u00d71" : ""', 1, '==', ''),
        ('R64·丹房卡药效行',            'children:YLXW_PILL_FX(W.result)||""', 1, '==', ''),
        # ================= 冻结：t17 丹炉面板面（一个字不动） =================
        ('冻结·t17 开炉请求契约未动',     '{ recipeKey: selRecipe, slot: pickSlot, fire: selFire, pill: selRecipe }', 1, '==', 't17 门禁同款'),
        ('冻结·t17 火候表未动',          'var YlxwAlcFire = [', 1, '==', ''),
        ('冻结·t17 主面板函数仍唯一',     'function YlxwTAlchemy(r) {', 1, '==', 'helpers 注入其前，本体未动'),
        ('冻结·t17 成功率公式未动',       'function YlxwAlcRate(rc, lv, luck, fire) {', 1, '==', ''),
        ('冻结·t17 纯度区间函数未动',     'function YlxwAlcPurityRange(rc, lv, luck, fire) {', 1, '==', ''),
        ('冻结·t17 造诣解锁表未动',       'var YlxwAlcUnlockLv = {', 1, '==', ''),
        ('冻结·t17 玩法说明折叠块未动',   'function YlxwAlcHelp() {', 1, '==', ''),
        ('冻结·t17 造诣条仍在',          'YlxwAlcBar', 2, '>=', '定义 + 使用'),
        # ================= 冻结：丹房公式面（四表只读） =================
        ('冻结·丹房成功率公式未动',       'const S=Jb[m.result.rarity]||.5', 1, '==', ''),
        ('冻结·造诣门槛 pm 表未动',       'pm=[0,100,300,800,2e3,5e3,12e3,3e4,8e4]', 1, '==', ''),
        ('冻结·熟练度 ug 表未动',         'ug={\u666e\u901a:10,\u7a00\u6709:30,\u4f20\u8bf4:100,\u4ed9\u54c1:500}', 1, '==', '基座裸 UTF-8 中文'),
        ('冻结·丹房卡描述未删',           'children:W.result.description})', 1, '==', '只在其后插入，原文保留'),
        # 禁用模式已在 apply() 内对注入块断言（全文计数会误伤基座/历史模块，不进 gates）
    ]
    return gates
