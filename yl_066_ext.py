# -*- coding: utf-8 -*-
r"""
yl_066_ext.py -- R-066 宗门「功法阁」：贡献值整体重做 + 修满化形（转游戏实装功法）

需求（台账 R-066，附图空）
--------------------------------------------------------------------------
  宗门的功法阁，兑换功法的贡献值要整体重做，现在都是固定的 100，要求太低；
  功法层数修满后，可以直接再转换为游戏实装的可用功法；
  功法阁数量大幅扩充依赖 R-067（功法系统重做），本次只留数据接口。

现状（2026-10-01 实测：线上 https://moyuwang.online/myxxz/ 与工作区 build 同版
  index-v28117-20261001.js；以下锚点全部 count==1 验证通过）
--------------------------------------------------------------------------
  功法阁 library 页 = `L.length===0 ? <YlxwSectGfPanel player={a}/> : 原版 grid`。
  原版 grid 数据源 `is` 表只有 1 部带 sectId（恒不匹配动态宗门 id）⇒ L 恒空，
  玩家实际看到的、也唯一可达的兑换面 = v28.1 注入的 YlxwSectGfPanel（宗门传承功法）。
  当前定价（yl_sectgf_ext.py / srv SECT_GF_TIER_BASE 同源）：
      每层消耗 = TIER_BASE[tier] × level（线性），TIER_BASE = {1:100, 2:250, 3:600, 4:1500}
      单部满级（5 层）= 1500 / 3750 / 9000 / 22500 贡献；12 部全满 = 110250。
  用户口径「都是固定的 100 / 要求太低」：入门档首层恰为 100，且整条曲线线性偏便宜。

本模块动作（3 件，全部落在 sectgf 注入块内，不碰其宿主逻辑）
--------------------------------------------------------------------------
  1. 贡献值重做：TIER_BASE → {1:200, 2:600, 3:1500, 4:4000}，公式改每层 ×2 指数
     cost(lv)=base×2^(lv-1)。新满级总耗 = 6200 / 18600 / 46500 / 124000（×4.1~×5.5），
     12 部全满 = 585900（旧 110250，×5.3）。经济底盘：捐献回馈日帽 1000 贡献 +
     任务阁产出、服务端 E2 钳 1200/时 ⇒ 入门部 1~6 天、镇宗部（长老+元婴门槛，
     收入同步更高）约 8~40 天，全满为宗门长线沉淀目标。
  2. 修满化形（★ 本轮改动：由「免费」改为「收贡献」）：5 层大成后卡片按钮变
     「化为功法」，并**显示化形费**（玩家点之前就能看见要花多少）；贡献不足时
     按钮变「贡献不足」置灰。点击走 POST /sect/gongfa/convert → 服务端在
     updatePlayerSave 锁内**权威扣费**，并把对应「游戏实装功法」（基座 `is` 表 id）
     写入 player.unlockedArts（功法界面即可修炼）+ 幂等表 player.sectGfConverted。
     化形费 = f(品阶) = YLXW_SECT_GF_TIER_BASE[tier] × 16（= 第 5 层单价 = 修满总耗
     基价×31 的 51.6%；黄 3200 / 玄 9600 / 地 24000 / 天 64000；与服务端
     srv_patch_066.py 的 sectGfConvertFee 同源）。
     映射表 YLXW_SECT_GF_CONVERT 按流派攻/防/辅 × 品阶黄玄地天对齐 12 条。
     服务端贡献不足返回 409（绝不用 403，Xc 强登出纪律）；客户端只显示/预扣，不拦。
  3. 扩充留口（R-067）：目录/门槛/化形全部数据驱动 —— 客户端
     YLXW_SECT_GF + YLXW_SECT_GF_TIER_BASE + YLXW_SECT_GF_CONVERT，
     服务端 SECT_GF_LIST + SECT_GF_TIER_BASE + SECT_GF_CONVERT（srv_patch_066.py）。
     R-067 扩充时两侧同表追加即可：tier 连续递增、rank 扩取值域表、per 键沿用
     六属性键名、化形值填基座 is 表 id；端点/面板/校验零改动。
     门禁按「品阶前缀计数」钉结构（黄玄地天各 6=目录3+化形3），扩充后同步改 4 条。

不做 / 冻结面
--------------------------------------------------------------------------
  · 原版 `is` 表功法定价（X.cost）不动 —— 那条 grid 分支恒空不可达，定价属 R-067
    功法大重做的领地（门禁冻结其消耗行原样）。
  · yl_sectgf_ext.py 的全部锚点与门禁（空态替换 / xt 六连 / 快照守卫 / 三接口 /
    act 主路径 / toast 通道）逐条冻结 ==1。
  · 藏宝阁 handleSectBuy、原版 handleLearnArt 路径零改动。
  · yl_arb_ext.py 的推档守卫 YL_SECT_CONTRIB_MAX_DELTA=50000 是「单次推档增量」
    钳制，与本模块的服务端扣费路径（saveLock 内 updatePlayerSave）无交集；
    其注释「单部满级=7500」随本模块过期，属注释漂移，不改他人文件，此处存档。

装配（接线员照抄）
--------------------------------------------------------------------------
  import：from yl_066_ext import apply as v28_r066_apply  # noqa: E402
  条目  ：('r066', v28_r066_apply)  放 ('r063', …) 之后、('numbal', …) 之前。
  ★ 必须排在 sectgf（V28_MODULES 第 7 位）之后 —— 本模块全部锚点都在 sectgf
    注入块内。r049~r063 与 numbal 与本模块零锚点交集。
  服务端配套 = srv_patch_066.py（SRV_CHAIN 链尾，与 061/062/063 零锚点交集）。

契约
--------------------------------------------------------------------------
  INJECT_JS : str   —— 本模块纯就地替换，无独立注入块（''）
  apply(p, ctx) -> gates   —— gates 为 (name, needle, expect, cmp, note) 5 元组
"""

# ---------------------------------------------------------------- 数值表（文档+门禁用，不直接注入）
TIER_BASE = {1: 200, 2: 600, 3: 1500, 4: 4000}
RATIO = 2
MAX_LEVEL = 5

INJECT_JS = ''          # 本模块只做「就地替换」，全部锚点都在 sectgf 注入块内


# ---------------------------------------------------------------- 旧锚点（zh() 转义后在 bundle 中各 count==1，2026-10-01 实测）

OLD_TIER_BASE = 'var YLXW_SECT_GF_TIER_BASE = { 1: 100, 2: 250, 3: 600, 4: 1500 };'

OLD_COST = (
    'function YlxwSectGfCost(tier, level) {\n'
    '  var b = YLXW_SECT_GF_TIER_BASE[tier] || 0;\n'
    '  var l = Math.max(1, Math.floor(Number(level) || 1));\n'
    '  return b * l;\n'
    '}'
)

OLD_SUBTITLE = '宗门历代长老所留绝学，需以宗门贡献领悟；每部可领悟 5 层，加成随层数递增。'

OLD_CAN = '    var can = !maxed && realmOk && rankOk && payOk && !busy;'

OLD_LABEL = ('    var label = maxed ? "已大成" : !rankOk ? "职衔不足" : !realmOk ? "境界不足" '
             ': !payOk ? "贡献不足" : (L > 0 ? "领悟" : "学习");')

OLD_BTN_CLS = (
    '    var btnCls = maxed\n'
    '      ? "bg-mystic-jade/20 text-mystic-jade border border-mystic-jade/30 cursor-default"\n'
    '      : (can ? "bg-mystic-gold/20 text-mystic-gold border border-mystic-gold hover:bg-mystic-gold/30"\n'
    '             : "bg-stone-800 text-stone-600 border border-stone-700 cursor-not-allowed");'
)

OLD_REQ_ROW = ('          e.jsxs("div", { children: ["要求: ", e.jsx("span", '
               '{ className: (realmOk && rankOk) ? "text-stone-300" : "text-red-400", '
               'children: [gf.rank, " · ", gf.realm] })] }),')

OLD_UPGRADE_FN = 'function YlxwSectGfUpgrade(id) { return YlxwPost("/sect/gongfa/upgrade", { id: id }); }'

OLD_APPLY_LINE = '      setData(j); YlxwSectGfApply(j);'

OLD_ACT_TAIL_CONTRIB = (
    '    }).then(function () { setBusy(!1); });\n'
    '  };\n'
    '\n'
    '  var contrib = Math.max(0, Math.floor(Number(p && p.sectContribution) || 0));'
)

OLD_ON_CLICK = '          onClick: function () { if (can) act(gf, L > 0); },'


# ---------------------------------------------------------------- 新文本

NEW_TIER_BASE = ('var YLXW_SECT_GF_TIER_BASE = { 1: 200, 2: 600, 3: 1500, 4: 4000 }; '
                 '/* [r066] R-066 贡献重做：基价 ×2~×2.7（与 srv_patch_066 的 SECT_GF_TIER_BASE 同源） */')

NEW_COST = (
    'function YlxwSectGfCost(tier, level) {\n'
    '  var b = YLXW_SECT_GF_TIER_BASE[tier] || 0;\n'
    '  var l = Math.max(1, Math.floor(Number(level) || 1));\n'
    '  return Math.floor(b * Math.pow(2, l - 1)); /* [r066] 每层消耗 ×2 指数递增（与服务端 sectGfCost 同式） */\n'
    '}'
)

NEW_SUBTITLE = '宗门历代长老所留绝学，需以宗门贡献领悟；每部可领悟 5 层，修满大成可化为游戏实装的可用功法。'

NEW_CAN = (
    '    var cvtFee = maxed ? YlxwSectGfCvtFee(gf.tier) : 0;\n'
    '    var cvt = maxed && YlxwSectGfCvtGet(p, gf.id);\n'
    '    var cvtPayOk = contrib >= cvtFee;\n'
    '    var can = maxed ? (!cvt && cvtPayOk && !busy) : (realmOk && rankOk && payOk && !busy);'
)

NEW_LABEL = ('    var label = maxed ? (cvt ? "已化形" : !cvtPayOk ? "贡献不足" : "化为功法") : !rankOk '
             '? "职衔不足" : !realmOk ? "境界不足" : !payOk ? "贡献不足" : (L > 0 ? "领悟" : "学习");')

NEW_BTN_CLS = (
    '    var btnCls = maxed\n'
    '      ? (cvt ? "bg-mystic-jade/20 text-mystic-jade border border-mystic-jade/30 cursor-default"\n'
    '             : "bg-mystic-gold/20 text-mystic-gold border border-mystic-gold hover:bg-mystic-gold/30")\n'
    '      : (can ? "bg-mystic-gold/20 text-mystic-gold border border-mystic-gold hover:bg-mystic-gold/30"\n'
    '             : "bg-stone-800 text-stone-600 border border-stone-700 cursor-not-allowed");'
)

NEW_REQ_ROW = (
    OLD_REQ_ROW + '\n'
    '          maxed ? e.jsxs("div", { children: ["化形: ", e.jsx("span", { className: cvt ? '
    '"text-mystic-jade" : (cvtPayOk ? "text-mystic-gold" : "text-red-400"), children: (cvt ? "已化 · " : "可化为 · ") + '
    'YlxwSectGfCvtName(gf.id) + (cvt ? "" : "（费 " + cvtFee + " 贡献）") })] }) : null,'
)

# 化形映射 + 接口 + 合并器（插在 YlxwSectGfUpgrade 之后、面板组件之前）
CONVERT_BLOCK = '''
/* ===== [r066] R-066 修满化形：5 层大成 → 消耗宗门贡献解锁「游戏实装」功法（基座 is 表 id） =====
   化形费 = f(品阶) = YLXW_SECT_GF_TIER_BASE[tier] × 16（= 第 5 层单价 = 修满总耗 基价×31 的 51.6%；
   与服务端 srv_patch_066.py 的 sectGfConvertFee 同源）。服务端在 updatePlayerSave 锁内权威扣费，
   本面板只做「价格显示 + 本地预扣」；贡献不足时服务端回 409（绝不用 403，Xc 对 403 强制登出）。
   R-067 功法大重做扩表：与 YLXW_SECT_GF 同步追加键值即可（服务端 SECT_GF_CONVERT 同源同扩），
   端点/面板/校验零改动。art 必须填基座 is 表实装功法 id。 */
function YlxwSectGfConvert(id) { return YlxwPost("/sect/gongfa/convert", { id: id }); }
function YlxwSectGfCvtFee(tier) {
  var b = YLXW_SECT_GF_TIER_BASE[tier] || 0;
  return b * 16; /* [r066] 化形费 = 基价 × 16 = 第 5 层单价（与服务端 SECT_GF_CONVERT_MULT 同源） */
}
function YlxwSectGfCvtGet(p, id) {
  var c = (p && p.sectGfConverted) || null;
  return !!(c && c[id]);
}
function YlxwSectGfCvtName(id) {
  var d = YLXW_SECT_GF_CONVERT[id];
  return d ? (d.name || d.art) : "";
}
var YLXW_SECT_GF_CONVERT = {
  "sgf-t1-atk": { art: "art-sharp-blade", name: "锐刃诀" },
  "sgf-t1-def": { art: "art-earth-core", name: "土核功" },
  "sgf-t1-psi": { art: "art-moonlight-refine", name: "月华淬炼诀" },
  "sgf-t2-atk": { art: "art-wind-sword", name: "疾风剑" },
  "sgf-t2-def": { art: "art-golden-protection", name: "金甲护体" },
  "sgf-t2-psi": { art: "art-frost-breath", name: "寒冰吐息" },
  "sgf-t3-atk": { art: "art-sword-intent", name: "剑意诀" },
  "sgf-t3-def": { art: "art-earth-mountain", name: "山岳功" },
  "sgf-t3-psi": { art: "art-starlight-gather", name: "聚星诀" },
  "sgf-t4-atk": { art: "art-immortal-sword", name: "斩仙剑诀" },
  "sgf-t4-def": { art: "art-earth-immortal", name: "土仙体" },
  "sgf-t4-psi": { art: "art-dao-heart", name: "道心诀" }
};
/* [r066] 合并服务端 converted 整表进本地 player（真值表、幂等；绝不回写贡献度：
   化形产物写服务端权威的 unlockedArts，由 gm_revision 通道拉新档到功法界面） */
function YlxwSectGfApplyCvt(j) {
  if (!j || typeof j !== "object" || !j.converted) return;
  try {
    var st = Be.getState();
    if (!st || !st.player) return;
    var cur = st.player.sectGfConverted || {}, next = {}, k, ch = false;
    for (k in cur) { if (Object.prototype.hasOwnProperty.call(cur, k)) next[k] = cur[k]; }
    for (k in j.converted) {
      if (!Object.prototype.hasOwnProperty.call(j.converted, k)) continue;
      if (!j.converted[k]) continue;
      if (next[k] !== 1) { next[k] = 1; ch = true; }
    }
    if (!ch) return;
    st.setPlayer(function (pl) { return pl ? Object.assign({}, pl, { sectGfConverted: next }) : pl; });
  } catch (e) {}
}
/* ===== end [r066] 修满化形 ===== */'''

DOCVT_BLOCK = (
    '\n'
    '  /* [r066] 修满化形：大成后消耗贡献转化为游戏实装的可用功法（服务端权威扣费，幂等） */\n'
    '  var doCvt = function (gf) {\n'
    '    if (busy || !gf) return;\n'
    '    setBusy(!0); setErr("");\n'
    '    var cvtBefore = Math.max(0, Math.floor(Number((Be.getState().player || {}).sectContribution) || 0));\n'
    '    YlxwSectGfConvert(gf.id).then(function (j) {\n'
    '      try { ia((j && j.message) || "化形成功"); } catch (e0) {}\n'
    '      YlxwSectGfApplyCvt(j);\n'
    '      // 本地同步扣除化形费（服务端已在同一笔请求里扣过）：仅当本地值仍等于请求前快照才落，防 6s 拉档整包覆盖后双扣\n'
    '      var fee = YlxwSectGfCvtFee(gf.tier);\n'
    '      try {\n'
    '        Be.getState().setPlayer(function (cur) {\n'
    '          if (!cur) return cur;\n'
    '          var now = Math.max(0, Math.floor(Number(cur.sectContribution) || 0));\n'
    '          if (now !== cvtBefore) return cur;\n'
    '          return Object.assign({}, cur, { sectContribution: Math.max(0, now - fee) });\n'
    '        });\n'
    '      } catch (e1) {}\n'
    '      try { YlxwDirty(); } catch (e2) {}\n'
    '      setVer(function (v) { return v + 1; });\n'
    '    }, function (e) {\n'
    '      setErr((e && e.message) || "操作失败");\n'
    '      try { Je((e && e.message) || "操作失败"); } catch (e3) {}\n'
    '    }).then(function () { setBusy(!1); });\n'
    '  };'
)


# ---------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}。返回 gates 列表。"""
    zh = ctx['zh']

    # 全部锚点/替换串统一过 zh()：中文 → \uXXXX，与 sectgf 注入块在 bundle 里的字节形态一致
    p.replace('r066-tierbase', zh(OLD_TIER_BASE), zh(NEW_TIER_BASE), expect=1,
              note='R-066 贡献重做：档位基价 {1:200,2:600,3:1500,4:4000}')
    p.replace('r066-cost', zh(OLD_COST), zh(NEW_COST), expect=1,
              note='R-066 消耗公式改每层 ×2 指数（与 srv_patch_066 同式）')
    p.replace('r066-subtitle', zh(OLD_SUBTITLE), zh(NEW_SUBTITLE), expect=1,
              note='面板副题补「修满大成可化为实装功法」')
    p.replace('r066-can', zh(OLD_CAN), zh(NEW_CAN), expect=1,
              note='卡片 can 分支：maxed 时放行化形（未化形且空闲）')
    p.replace('r066-label', zh(OLD_LABEL), zh(NEW_LABEL), expect=1,
              note='按钮文案：已大成 → 已化形 / 化为功法')
    p.replace('r066-btncls', zh(OLD_BTN_CLS), zh(NEW_BTN_CLS), expect=1,
              note='未化形大成卡用金色可点样式')
    p.replace('r066-cvtrow', zh(OLD_REQ_ROW), zh(NEW_REQ_ROW), expect=1,
              note='大成卡补化形产物展示行')
    p.replace('r066-api', zh(OLD_UPGRADE_FN), zh(OLD_UPGRADE_FN + '\n' + CONVERT_BLOCK), expect=1,
              note='化形接口/映射表/合并器（插在 sectgf 接口区尾）')
    p.replace('r066-applycvt', zh(OLD_APPLY_LINE), zh('      setData(j); YlxwSectGfApply(j); YlxwSectGfApplyCvt(j);'),
              expect=1, note='面板拉档时合并服务端 converted 表')
    p.replace('r066-docvt', zh(OLD_ACT_TAIL_CONTRIB), zh('    }).then(function () { setBusy(!1); });\n  };\n'
              + DOCVT_BLOCK +
              '\n\n  var contrib = Math.max(0, Math.floor(Number(p && p.sectContribution) || 0));'),
              expect=1, note='doCvt：化形请求 + 合并 + 刷新（与 act 同 toast 通道）')
    p.replace('r066-onclick', zh(OLD_ON_CLICK),
              zh('          onClick: function () { if (!can) return; if (maxed) { doCvt(gf); } else { act(gf, L > 0); } },'),
              expect=1, note='按钮分派：大成走 doCvt，其余走 act 学习/升级')

    # 针含中文时必须与锚点同走 zh()（bundle 里是 \uXXXX 转义形态；ASCII 针 zh 恒等）
    raw_gates = [
        # ============ 本模块新面 ============
        ('r066·档位基价已重做',        'var YLXW_SECT_GF_TIER_BASE = { 1: 200, 2: 600, 3: 1500, 4: 4000 };', 1, '==', '基价 ×2~×2.7'),
        ('r066·旧档位基价已清零',      'var YLXW_SECT_GF_TIER_BASE = { 1: 100, 2: 250, 3: 600, 4: 1500 };', 0, '==', '必须为 0'),
        ('r066·消耗已改指数曲线',      'return Math.floor(b * Math.pow(2, l - 1));', 1, '==', 'cost=base×2^(层-1)'),
        ('r066·旧线性消耗已清零',      'return b * l;', 0, '==', '必须为 0'),
        ('r066·化形映射表已入',        'var YLXW_SECT_GF_CONVERT = {', 1, '==', ''),
        ('r066·化形映射 12 部齐',      '"sgf-t4-psi": { art: "art-dao-heart"', 1, '==', '末条在表'),
        ('r066·化形接口已接',          'YlxwPost("/sect/gongfa/convert", { id: id });', 1, '==', ''),
        ('r066·化形费函数已入',        'function YlxwSectGfCvtFee(tier) {', 1, '==', '费=基价×16'),
        ('r066·化形余额闸已入',        'var cvtPayOk = contrib >= cvtFee;', 1, '==', ''),
        ('r066·化形贡献不足文案',      'maxed ? (cvt ? "已化形" : !cvtPayOk ? "贡献不足" : "化为功法")', 1, '==', ''),
        ('r066·卡片已显示化形费',      '（费 " + cvtFee + " 贡献）', 1, '==', '点前可见'),
        ('r066·化形本地预扣已入',      'sectContribution: Math.max(0, now - fee)', 1, '==', '快照守卫防双扣'),
        ('r066·化形合并器已入',        'function YlxwSectGfApplyCvt(j) {', 1, '==', ''),
        ('r066·拉档已合并化形表',      'YlxwSectGfApplyCvt(j);', 2, '==', 'useEffect 1 + doCvt 1'),
        ('r066·按钮已分派化形',        'if (maxed) { doCvt(gf); } else { act(gf, L > 0); }', 1, '==', ''),
        ('r066·旧 maxed 禁点已清零',   'var can = !maxed && realmOk && rankOk && payOk && !busy;', 0, '==', '必须为 0'),
        ('r066·旧「已大成」已清零',    'maxed ? "已大成" : !rankOk', 0, '==', '必须为 0（另一处在别的注入块，针已带上下文限域）'),
        ('r066·面板副题已带化形',      '修满大成可化为游戏实装的可用功法', 1, '==', ''),
        ('r066·卡片化形行已插',        '可化为 · ', 1, '==', ''),
        ('r066·doCvt 走同批 toast',   'try { ia((j && j.message) || "化形成功"); } catch (e0) {}', 1, '==', '与 act 同通道'),
        # 扩充留口：品阶前缀计数（黄玄地天各 6 = 目录3 + 化形3；R-067 扩充后同步改 4 条）
        ('r066·留口·黄档计数',         '"sgf-t1-', 6, '==', '目录3+化形3；R-067 扩充后改此预期'),
        ('r066·留口·玄档计数',         '"sgf-t2-', 6, '==', '同上'),
        ('r066·留口·地档计数',         '"sgf-t3-', 6, '==', '同上'),
        ('r066·留口·天档计数',         '"sgf-t4-', 6, '==', '同上'),
        # ============ 冻结面：sectgf / 相邻需求一个字不动 ============
        ('冻结·功法阁空态替换仍在',    'e.jsx(YlxwSectGfPanel,{player:a})', 1, '==', 'sectgf 锚点未回退'),
        ('冻结·xt 六连·攻击未动',      'attack:t.attack+YlxwSectGfV(t,"attack")', 1, '==', 'sectgf xt 叠加'),
        ('冻结·扣贡献快照守卫仍在',    'if (now !== contribBefore) return cur;', 1, '==', 'v28.1 双扣修复'),
        ('冻结·列表接口',              'YlxwGet("/sect/gongfa")', 1, '==', ''),
        ('冻结·学习接口',              'YlxwPost("/sect/gongfa/learn"', 1, '==', ''),
        ('冻结·升级接口',              'YlxwPost("/sect/gongfa/upgrade"', 1, '==', ''),
        ('冻结·act 学习/升级主路径',   'var run = isUp ? YlxwSectGfUpgrade : YlxwSectGfLearn;', 1, '==', ''),
        ('冻结·act toast 通道',        'try { ia((j && j.message) || "领悟成功"); } catch (e0) {}', 1, '==', ''),
        ('冻结·原版 grid 分支未动',    'className:"grid grid-cols-1 md:grid-cols-2 gap-4",children:L.map', 1, '==', '原版恒空分支'),
        ('冻结·原版卡片消耗行未动',    'X.cost,"', 1, '==', '原版功法定价行（ASCII 针；原区中文是原文形态不过 zh）留给 R-067'),
        ('冻结·藏宝阁 handleSectBuy',  'handleSectBuy:', 5, '==', '多副本计数冻结（2026-10-01 实测 5）'),
    ]
    return [(n, zh(s), e, c, m) for (n, s, e, c, m) in raw_gates]
