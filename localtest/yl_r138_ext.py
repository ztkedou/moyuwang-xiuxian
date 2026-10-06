# -*- coding: utf-8 -*-
r"""
yl_r138_ext.py — R-138 自动历练「非常详细」统计：单次结算行补物品数量 + 停止时多行汇总块
（客户端 standalone · 0.9.15 批次）

需求原文（用户，台账 R-138，逐字）
--------------------------------------------------------------------------
  「自动历练结束时统计信息不够详细，要非常详细把所有数据，物品获得情况以及其他信息
    全都展示，这个可以很好的让我们了解历练的数值，也方便我修改需求。」

基线 = build/assets/index-v2915-20261002.js（2,278,270 B，中文以字面 `\uXXXX` 存储；只读）
本模块由装配层作为 standalone `--src` 脚本，在全部 V28 模块 + 既有 standalone 之后套用
（build_v26n.STANDALONE_CLIENT；门禁由 dryrun_087 对**补丁后**最终产物重跑）。

==============================================================================
一、改前取证（逐字，偏移为基座产物字符偏移）
==============================================================================
  【1】单次结算行 = `function YlxwAdvResultLog(res, advType, addLog)` @537421
       （R-089 adv097 注入、R-114 丰富化后的形态）。体内：
         · `if (de) parts.push("修为 " + …)` / `if (ds) parts.push("灵石 " + …)`
           / `if (dh) parts.push("气血 " + …)`（R-114）
         · `var _ylNames = _ylDrop.filter(…).map(function (x) { return x.name; });`
           → **只取名字，丢失数量**（掉落对象可能带 `quantity`）
         · `if (_ylNames.length) parts.push("掉落 " + _ylNames.join("、"));`
         · 抽奖券 / 声望 / 奇遇(lucky) / 天地之魄(heavenEarthSoulEncounter) 均已展示
         · 事件类型中文名：label 三分支 + R-114 的 lucky/天地之魄 tag（normal 隐含在 label）
       ⇒ 唯一缺「物品数量」；「事件类型中文名」仅当 res.adventureType 与入参 advType
         不一致时才需补显（否则已由 label / R-114 tag 覆盖）。

  【2】自动历练结束汇总 = R-105（advend105）`function YlxwAdvSession(on)` @621212：
         会话 true→false 且 5 个 pausedBy* 全 false（=用户主动关闭）时，写**一条**日志：
           `add("🗺 本次自动历练 " + YlxwAdvDur(el) + "：修为 +" + gx + " · 灵石 +" + gs
                + " · 历练 " + gr + " 次", "gain");`
       其累计来自 `function YlxwAdvAcc(res)` @620797（只累计 exp>0 / stone>0 / runs）。

  【3】addLog 是否支持多行 —— **不支持**。日志 store 定义 @590420：
         `addLog:(a,l)=>{t(c=>({logs:[...c.logs,{id:…,text:a,type:l,timestamp:Date.now()}]
            .slice(-1000)}))}`
       一次调用 = **一个** logs 条目（上限 1000 条）。渲染端 `LogItem` @830927 的外层
       className（@830300）为 `"…border-l-2 font-serif text-xs md:text-sm lg:text-base
       leading-relaxed animate-fade-in"` + 色调类，**无 `whitespace-pre-wrap`/`pre-line`**，
       `t.text` 作为单个文本子节点渲染 ⇒ 文本里的 `\n` 会被 HTML 折叠成空格。
       ⇒ 「多行汇总」必须用**多次 addLog 调用**（每行一个条目），不能用一条带 `\n` 的文本。
         这是项目现状下唯一的多行手段（无 addLog 批量形式）。

==============================================================================
二、改法（3 处就地替换 + 1 段注入块；不新增单次结算行数）
==============================================================================
  E1 单次结算行·物品数量：
      `_ylNames` 的 map 由「返回 name」改为「name +（数量>1 时 " ×N"）」，
      `quantity`（缺失回退 `qty`，再回退 1）取自掉落对象；`parts.push("掉落 " + …)`
      一字不动 ⇒ R-114/adv097 的掉落 needle 全部保留。

  E2 单次结算行·事件类型中文名（补显，不重复）：
      在 `if (!parts.length) parts.push("无收益");` 之前插一行：
        `if (res.adventureType && res.adventureType !== advType)
           parts.push("类型 " + YlxwAdvTypeName(res.adventureType));`
      ⇒ 仅当结果对象的 adventureType 与入参 advType 不一致时才追加（normal 由 label
         「历练收获」体现、lucky 由 R-114「奇遇」tag 体现、秘境/宗门由 label 体现、
         天地之魄由 R-114 tag 体现），不产生冗余。

  E3 每次结算·扩展累计（不改调用点）：
      在 R-105 `YlxwAdvAcc` 体内 `YLXW_ADV_ACC.runs += 1;` 之后追加 `YlxwAdvStatAcc(res);`
      ⇒ 调用点 `YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),` 逐字不动。

  E4 会话结束·多行汇总（保留 R-105 头行）：
      在 R-105 那条 `add("🗺 本次自动历练 …")` 之后、`} catch` 之前追加 `YlxwAdvSummary(el);`
      ⇒ R-105 头行整句逐字保留（advend105 全部 needle 不变），其后再刷 6 行详细统计。

  E5 注入块（纯 ASCII；插在 `function YlxwAdvSession(on) {` 之前，与 R-105 同作用域，
     函数声明提升 ⇒ 定义顺序无关）：`YLXW_ADV_STAT` 累加器 + `YlxwAdvStatNew/Acc/Summary`
     + `YlxwAdvTypeName`（复用既有 `function Aw(t)`，@600195；缺失时内置兜底表）+ `YlxwAdvNum`。

==============================================================================
三、累计器方案（window 之外，模块级；不碰 player / 存档 schema）
==============================================================================
  `var YLXW_ADV_STAT = null;` 模块级。**重置策略 = 会话身份绑定**：
    `YlxwAdvStatAcc` 里 `if (!YLXW_ADV_STAT || YLXW_ADV_STAT.sess !== YLXW_ADV_SESS)
        { YLXW_ADV_STAT = YlxwAdvStatNew(); YLXW_ADV_STAT.sess = YLXW_ADV_SESS; }`
  R-105 每次「false→true 开启新会话」都会把 `YLXW_ADV_SESS` 换成一个**新对象**；临时暂停
  （战斗/商店/声望/天地之魄/渡劫）只保留旧对象不换 ⇒ 身份不变 ⇒ 累加器不重置（暂停期成果
  仍计入本次）。**无需改动 R-105 的起始块**，天然在每次开启时清零。
  ★ 刻意不引入 `if (!YLXW_ADV_SESS) return;` 之外的同款守卫（用 `== null` 写法），
    以免把 advend105 的冻结 needle 计数从 1 抬到 2。

==============================================================================
四、汇总块内容（每次自动历练停止追加 6 行；一次 addLog = 一行）
==============================================================================
  1) 📊 历练统计：共 N 次 · 耗时 <时长>            （YlxwAdvDur，复用 R-105）
  2) 修为 +X · 灵石 +Y · 气血 ±H                  （气血非 0 才附）
  3) 抽奖券 +L · 声望 +R · 平均每次 修为 +X/N · 灵石 +Y/N
  4) 事件类型：历练 a · 奇遇 b · 秘境 c · 宗门挑战 d · 天地之魄挑战 e   （仅非 0 项）
  5) 物品获得（K 种）：名字 ×数量、名字 …          （按名字聚合计数；=1 省略 ×1）
  6) 其他：掉落 n 次 · 奇遇 n 次 · 天地之魄 n 次 [· 受伤 n 次]
  日志 type 一律 "gain"（与 R-105 头行一致）。
  ⚠ 事件类型分布只能按结果对象真实字段 `adventureType`（normal/lucky/secret_realm/
    sect_challenge/dao_combining_challenge）聚合 —— 历练池的子类目（battle/herb/
    enlightenment/lottery…）**不进结果对象**（`hw(t)` 的 switch 只 spread `vy()` 基对象，
    子类目 `a` 不落字段），故无法从客户端结果侧还原「战斗/顿悟」粒度。若用户要该粒度，
    须改 `hw(t)` 的事件生成侧（本模块不做，见报告）。

==============================================================================
五、风险 / 越界声明
==============================================================================
  1. 刷屏：单次结算仍**只 1 行**（未增行）；汇总块仅在**停止时**追加 6 行 ⇒ 对 1000 条
     日志上限的冲击可忽略（R-089 已提示单次行 ~12s/次本身就会 1 小时挤满，与本次无关）。
  2. 本模块改动了 adv097/r114/advend105 三个 **V28 模块**产出的字串（E1/E3/E4 追加式、
     E2 插入式），但**未触碰它们的任何门禁 needle**（advend105 头行整句、YlxwAdvAcc 三条
     累计式、YlxwAdvResultLog 签名与掉落 push 等逐字保留，见 gates 冻结组）。V28 门禁在
     build() 阶段对**standalone 前**文本已校验通过，standalone 门禁只认本模块 gates()。
  3. 纯客户端：不改版本号 / build_v26n.py / CHANGELOG* / EXPECT_0811.env / deploy_v28/* /
     srv/index_v28.ts / 任何已有 yl_*_ext.py。注入块 zh 域纯 ASCII、无 fetch、不含
     V28_BAN_PATTERNS。**无需服务端改动**。

锚点实测 count（基座 build/assets/index-v2915-20261002.js，逐字实测，全部 ==1）：
  E1 `var _ylNames = _ylDrop.filter(function (x) { return x && x.name; }).map(function (x) { return x.name; });`
  E2 `    if (!parts.length) parts.push("\u65e0\u6536\u76ca");`
  E3 `  YLXW_ADV_ACC.runs += 1;\n}`
  E4 `+ gr + " \u6b21", "gain");\n  } catch (e) {}\n}\n\nfunction Hw({autoMeditate:t,`
  E5 `function YlxwAdvSession(on) {`
  `YLXW_R138`（改前 0）
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 注入块（纯 ASCII；中文一律写成字面 `\uXXXX`）
#   直接以 raw 字符串书写 `\uXXXX`（6 个 ASCII 字节），产物里即为该形态，无需 zh()。

INJECT_JS = r'''/* ===== yl-R138 advstat138: detailed per-settlement line + multi-line stop summary =====
   R-138: the auto-adventure STOP summary must be far more detailed. We keep R-105's
   session/pause logic and its one header line byte-for-byte, and APPEND a multi-line
   stats block. LogItem renders t.text as one collapsed text node (no whitespace-pre-wrap),
   so a "multi-line" summary must be several addLog calls (one entry per visual line).
   Extended per-settlement accumulation rides on R-105's YlxwAdvAcc (appended call).
   Marker: YLXW_R138. Pure client, no player field, no save-schema change. */
var YLXW_ADV_STAT = null;
function YlxwAdvStatNew() {
  return { sess: null, runs: 0, exp: 0, stone: 0, hp: 0, hpDown: 0,
           lot: 0, rep: 0, drops: 0, lucky: 0, soul: 0, items: {}, types: {} };
}
function YlxwAdvTypeName(t) {
  try { if (typeof Aw === "function") return Aw(t); } catch (e0) {}
  var m = { normal: "\u5386\u7ec3", lucky: "\u5947\u9047", secret_realm: "\u79d8\u5883",
            sect_challenge: "\u5b97\u95e8\u6311\u6218",
            dao_combining_challenge: "\u5929\u5730\u4e4b\u9b44\u6311\u6218" };
  return m[t || ""] || "\u5386\u7ec3";
}
function YlxwAdvNum(n) { return Math.floor(Number(n) || 0).toLocaleString(); }
/* Accumulate the extra per-settlement fields while a session is live. Bound to R-105's
   YLXW_ADV_SESS identity: a fresh session object (false->true start) auto-resets; a
   temporary pause keeps the same object, so accumulation continues. */
function YlxwAdvStatAcc(res) {
  if (YLXW_ADV_SESS == null) return;
  if (!res || typeof res !== "object") return;
  if (!YLXW_ADV_STAT || YLXW_ADV_STAT.sess !== YLXW_ADV_SESS) {
    YLXW_ADV_STAT = YlxwAdvStatNew();
    YLXW_ADV_STAT.sess = YLXW_ADV_SESS;
  }
  var S = YLXW_ADV_STAT;
  S.runs += 1;
  var de = Math.floor(Number(res.expChange) || 0);
  var ds = Math.floor(Number(res.spiritStonesChange) || 0);
  var dh = Math.floor(Number(res.hpChange) || 0);
  if (de > 0) S.exp += de;
  if (ds > 0) S.stone += ds;
  S.hp += dh;
  if (dh < 0) S.hpDown += 1;
  var lo = Math.floor(Number(res.lotteryTicketsChange) || 0);
  if (lo) S.lot += lo;
  var rp = Math.floor(Number(res.reputationChange) || 0);
  if (rp) S.rep += rp;
  var ty = res.adventureType || "normal";
  S.types[ty] = (S.types[ty] || 0) + 1;
  if (ty === "lucky") S.lucky += 1;
  if (res.heavenEarthSoulEncounter) S.soul += 1;
  var drops = [];
  if (res.itemsObtained && res.itemsObtained.length) drops = drops.concat(res.itemsObtained);
  if (res.itemObtained) drops.push(res.itemObtained);
  for (var i = 0; i < drops.length; i++) {
    var it = drops[i];
    if (!it || !it.name) continue;
    var q = Math.floor(Number(it.quantity != null ? it.quantity : it.qty) || 1);
    if (q < 1) q = 1;
    S.items[it.name] = (S.items[it.name] || 0) + q;
    S.drops += 1;
  }
}
/* Emit the detailed stop summary: called right after R-105's one header line.
   One addLog entry per visual line (see header comment). */
function YlxwAdvSummary(el) {
  try {
    var st = YLXW_ADV_STAT;
    var add = Be.getState().addLog;
    if (typeof add !== "function") return;
    if (!st || !st.runs) return;
    add("\ud83d\udcca \u5386\u7ec3\u7edf\u8ba1\uff1a\u5171 " + st.runs + " \u6b21 \u00b7 \u8017\u65f6 " + YlxwAdvDur(el), "gain");
    var l2 = "\u4fee\u4e3a +" + YlxwAdvNum(st.exp) + " \u00b7 \u7075\u77f3 +" + YlxwAdvNum(st.stone);
    if (st.hp) l2 += " \u00b7 \u6c14\u8840 " + (st.hp > 0 ? "+" : "") + YlxwAdvNum(st.hp);
    add(l2, "gain");
    var l3 = [];
    if (st.lot) l3.push("\u62bd\u5956\u5238 +" + YlxwAdvNum(st.lot));
    if (st.rep) l3.push("\u58f0\u671b +" + YlxwAdvNum(st.rep));
    l3.push("\u5e73\u5747\u6bcf\u6b21 \u4fee\u4e3a +" + YlxwAdvNum(Math.floor(st.exp / st.runs))
      + " \u00b7 \u7075\u77f3 +" + YlxwAdvNum(Math.floor(st.stone / st.runs)));
    add(l3.join(" \u00b7 "), "gain");
    var dist = [], k;
    for (k in st.types) { if (st.types[k]) dist.push(YlxwAdvTypeName(k) + " " + st.types[k]); }
    if (dist.length) add("\u4e8b\u4ef6\u7c7b\u578b\uff1a" + dist.join(" \u00b7 "), "gain");
    var names = [], it;
    for (it in st.items) { if (st.items[it]) names.push(it + (st.items[it] > 1 ? " \u00d7" + st.items[it] : "")); }
    if (names.length) add("\u7269\u54c1\u83b7\u5f97\uff08" + names.length + " \u79cd\uff09\uff1a" + names.join("\u3001"), "gain");
    var l6 = ["\u6389\u843d " + st.drops + " \u6b21", "\u5947\u9047 " + st.lucky + " \u6b21",
              "\u5929\u5730\u4e4b\u9b44 " + st.soul + " \u6b21"];
    if (st.hpDown) l6.push("\u53d7\u4f24 " + st.hpDown + " \u6b21");
    add("\u5176\u4ed6\uff1a" + l6.join(" \u00b7 "), "gain");
  } catch (e1) {}
}
'''

# --------------------------------------------------------------------------- 锚点 / 替换（raw str；`\uXXXX` 为字面 6 字节）
# E5 注入锚（插在其前）
INJECT_ANCHOR = r'function YlxwAdvSession(on) {'

# E1 单次结算行·物品数量
E1_OLD = (r'var _ylNames = _ylDrop.filter(function (x) { return x && x.name; })'
          r'.map(function (x) { return x.name; });')
E1_NEW = (r'var _ylNames = _ylDrop.filter(function (x) { return x && x.name; })'
          r'.map(function (x) { var _q = Math.floor(Number(x.quantity != null ? x.quantity : x.qty) || 1);'
          r' return x.name + (_q > 1 ? " \u00d7" + _q : ""); });')

# E2 单次结算行·事件类型中文名（补显，不重复）
E2_OLD = r'    if (!parts.length) parts.push("\u65e0\u6536\u76ca");'
E2_NEW = (r'    if (res.adventureType && res.adventureType !== advType)'
          r' parts.push("\u7c7b\u578b " + YlxwAdvTypeName(res.adventureType));' + '\n' + E2_OLD)

# E3 每次结算·扩展累计（追加在 R-105 YlxwAdvAcc 尾部；不改调用点）
E3_OLD = '  YLXW_ADV_ACC.runs += 1;\n}'
E3_NEW = '  YLXW_ADV_ACC.runs += 1;\n  YlxwAdvStatAcc(res);\n}'

# E4 会话结束·多行汇总（保留 R-105 头行整句；在其后、catch 前追加调用）
E4_OLD = (r'+ gr + " \u6b21", "gain");' + '\n  } catch (e) {}\n}\n\nfunction Hw({autoMeditate:t,')
E4_NEW = (r'+ gr + " \u6b21", "gain");' + '\n    YlxwAdvSummary(el);'
          + '\n  } catch (e) {}\n}\n\nfunction Hw({autoMeditate:t,')

EDITS = [
    ('E5 注入统计块', INJECT_ANCHOR, INJECT_JS + '\n' + INJECT_ANCHOR),
    ('E1 掉落名补数量', E1_OLD, E1_NEW),
    ('E2 事件类型中文名补显', E2_OLD, E2_NEW),
    ('E3 扩展累计挂点', E3_OLD, E3_NEW),
    ('E4 结束汇总调用', E4_OLD, E4_NEW),
]

# ---- 幂等/在位标记 ----
FR_MARK = 'YLXW_R138'

# ---- 冻结 needle（只读，不得被本模块增/减）----
FRZ_LOG_DEF = r'function YlxwAdvResultLog(res, advType, addLog) {'
FRZ_LOG_CALL = r'YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),'
FRZ_ACC_DEF = r'function YlxwAdvAcc(res) {'
FRZ_SESS_DEF = r'function YlxwAdvSession(on) {'
FRZ_SESS_GUARD = r'if (!YLXW_ADV_SESS) return;'
FRZ_ACC_RUNS = r'YLXW_ADV_ACC.runs += 1;'
FRZ_ACC_RESET = r'YLXW_ADV_ACC = { exp: 0, stone: 0, runs: 0 };'
FRZ_ACC_EXP = r'if (de > 0) YLXW_ADV_ACC.exp += de;'
FRZ_ACC_STONE = r'if (ds > 0) YLXW_ADV_ACC.stone += ds;'
FRZ_HEADER = r'"\ud83d\uddfa \u672c\u6b21\u81ea\u52a8\u5386\u7ec3 " + YlxwAdvDur(el)'
FRZ_PAUSE = r'var yz = Ze.getState();'
FRZ_R114_DE = r'if (de) parts.push("\u4fee\u4e3a " + (de > 0 ? "+" : "") + de);'
FRZ_R114_DS = r'if (ds) parts.push("\u7075\u77f3 " + (ds > 0 ? "+" : "") + ds);'
FRZ_R114_DH = r'if (dh) parts.push('
FRZ_R114_DROP = r'parts.push("\u6389\u843d " + _ylNames.join("\u3001"));'
FRZ_R114_LOT = r'if (_ylLot) parts.push('
FRZ_R114_REP = r'if (_ylRep) parts.push('
FRZ_R114_LUCKY = r'if (res.adventureType === "lucky") parts.push("\u5947\u9047");'
FRZ_R114_SOUL = r'if (res.heavenEarthSoulEncounter) parts.push("\u5929\u5730\u4e4b\u9b44\u6311\u6218");'
FRZ_R114_EMPTY = r'if (!parts.length) parts.push("\u65e0\u6536\u76ca");'
FRZ_LOG_WRITE = r'addLog("\ud83d\udcca " + label'


def gates():
    """补丁后形态的门禁五元组（name, needle, count, op, note[，within]）——供 dryrun 门禁表收录重跑。"""
    return [
        # ================= 注入块 / 新形态（==1） =================
        ('R138·注入标记在位',            FR_MARK,                                          1, '==', ''),
        ('R138·汇总函数已注入',          'function YlxwAdvSummary(el) {',                  1, '==', ''),
        ('R138·统计累加函数已注入',      'function YlxwAdvStatAcc(res) {',                 1, '==', ''),
        ('R138·统计初始化已注入',        'function YlxwAdvStatNew() {',                    1, '==', ''),
        ('R138·类型中文名函数已注入',    'function YlxwAdvTypeName(t) {',                  1, '==', '复用既有 Aw(t)，缺失兜底'),
        ('R138·数字格式化函数已注入',    'function YlxwAdvNum(n) {',                       1, '==', ''),
        ('R138·累加器变量已注入',        'var YLXW_ADV_STAT = null;',                      1, '==', '模块级；不碰 player/schema'),
        ('R138·累加器会话身份绑定',      'YLXW_ADV_STAT.sess !== YLXW_ADV_SESS',           1, '==', '新会话换对象 ⇒ 自动重置'),
        ('R138·累加抽奖券',              'S.lot += lo;',                                   1, '==', ''),
        ('R138·累加声望',                'S.rep += rp;',                                   1, '==', ''),
        ('R138·累加事件分布',            'S.types[ty] = (S.types[ty] || 0) + 1;',          1, '==', '按 res.adventureType 聚合'),
        ('R138·累加物品（按名计数）',    'S.items[it.name] = (S.items[it.name] || 0) + q;', 1, '==', ''),
        ('R138·累加气血/受伤',           'if (dh < 0) S.hpDown += 1;',                     1, '==', ''),

        # ================= 单次结算行（E1/E2） =================
        ('R138·掉落名含数量',            r'return x.name + (_q > 1 ? " \u00d7" + _q : "");', 1, '==', '物品「什么 × 几个」'),
        ('R138·掉落数量回退 quantity/qty', r'Number(x.quantity != null ? x.quantity : x.qty)', 1, '==', ''),
        ('R138·事件类型中文名补显',      r'if (res.adventureType && res.adventureType !== advType) parts.push("\u7c7b\u578b " + YlxwAdvTypeName(res.adventureType));', 1, '==', '仅当与 label 不一致时补显，不重复'),

        # ================= 挂点（E3/E4，==1） =================
        ('R138·每次结算累计已挂',        'YlxwAdvStatAcc(res);',                           1, '==', '追加在 YlxwAdvAcc 尾，不改调用点'),
        ('R138·结束汇总调用已挂',        'YlxwAdvSummary(el);',                            1, '==', '追加在 R-105 头行之后、catch 之前'),

        # ================= 汇总块字段（==1） =================
        ('R138·汇总含次数/耗时',         r'\u5386\u7ec3\u7edf\u8ba1\uff1a\u5171 ',         1, '==', '字段①：共 N 次 · 耗时'),
        ('R138·汇总含平均每次',          r'\u5e73\u5747\u6bcf\u6b21 \u4fee\u4e3a +',        1, '==', '字段⑤：平均每次 修为/灵石'),
        ('R138·汇总含事件类型分布',      r'\u4e8b\u4ef6\u7c7b\u578b\uff1a',                1, '==', '字段④：各 adventureType 中文名分布'),
        ('R138·汇总含物品清单',          r'\u7269\u54c1\u83b7\u5f97\uff08',                1, '==', '字段③：物品按名聚合'),
        ('R138·汇总含其他计数',          r'\u5176\u4ed6\uff1a',                            1, '==', '掉落/奇遇/天地之魄/受伤 次数'),

        # ================= 旧形态清零（==0） =================
        ('R138·旧掉落名（无数量）清零',  E1_OLD,                                           0, '==', ''),
        ('R138·旧累计收尾清零',          E3_OLD,                                           0, '==', ''),
        ('R138·旧汇总收尾清零',          E4_OLD,                                           0, '==', '头行后已插 YlxwAdvSummary(el)'),

        # ================= 冻结：R-089 adv097 面（逐字保留） =================
        ('冻结·adv097 日志函数签名',     FRZ_LOG_DEF,                                      1, '==', ''),
        ('冻结·adv097 调用点',           FRZ_LOG_CALL,                                     1, '==', '本模块只追加 YlxwAdvStatAcc 的体内调用'),
        ('冻结·adv097 写日志调用',       FRZ_LOG_WRITE,                                    1, '==', ''),

        # ================= 冻结：R-105 advend105 面（逐字保留） =================
        ('冻结·R105 累计函数仍在',       FRZ_ACC_DEF,                                      1, '==', ''),
        ('冻结·R105 会话函数仍在',       FRZ_SESS_DEF,                                     1, '==', ''),
        ('冻结·R105 会话外丢弃未被增计', FRZ_SESS_GUARD,                                   1, '==', '本模块用 `== null` 写法，不抬计数'),
        ('冻结·R105 累计次数仍在',       FRZ_ACC_RUNS,                                     1, '==', ''),
        ('冻结·R105 累加器初始化未动',   FRZ_ACC_RESET,                                    2, '==', '声明 + 会话起点清零'),
        ('冻结·R105 修为累计未动',       FRZ_ACC_EXP,                                      1, '==', ''),
        ('冻结·R105 灵石累计未动',       FRZ_ACC_STONE,                                    1, '==', ''),
        # ★ 2026-10-06 R-155 接管：R-155 把 R-105 头行从 `add("🗺 本次自动历练 " + YlxwAdvDur(el) …)`
        #   改成 `var _l155 = ["🗺 本次自动历练 " + YlxwAdvDur(el) …]`（汇总后单次 add）。
        #   ⇒ 本门禁的 needle 去掉 `add(` 前缀，只冻结**头行文案本身**（两阶段都恰好 1 处：
        #     chain_build 阶段在 add(...) 里，dryrun 最终形态在 _l155 数组里）。
        ('冻结·R105 汇总头行文案逐字保留', FRZ_HEADER,                                     1, '==', 'R-155 起容器由 add(...) 变为 _l155[...]，文案不变'),
        ('冻结·R105 暂停快照未动',       FRZ_PAUSE,                                        1, '==', ''),

        # ================= 冻结：R-114 面（逐字保留） =================
        ('冻结·R114 修为非 0 才入列',    FRZ_R114_DE,                                      1, '==', ''),
        ('冻结·R114 灵石非 0 才入列',    FRZ_R114_DS,                                      1, '==', ''),
        ('冻结·R114 气血项',             FRZ_R114_DH,                                      1, '==', ''),
        ('冻结·R114 掉落展示',           FRZ_R114_DROP,                                    1, '==', ''),
        ('冻结·R114 抽奖券展示',         FRZ_R114_LOT,                                     1, '==', ''),
        ('冻结·R114 声望展示',           FRZ_R114_REP,                                     1, '==', ''),
        ('冻结·R114 奇遇标注',           FRZ_R114_LUCKY,                                   1, '==', ''),
        ('冻结·R114 天地之魄标注',       FRZ_R114_SOUL,                                    1, '==', ''),
        ('冻结·R114 全空兜底',           FRZ_R114_EMPTY,                                   1, '==', ''),

        # ================= 冻结：开关未动 =================
        ('冻结·setAutoAdventure 调用点未增减', 'setAutoAdventure',                        29, '==', '本模块不碰启停'),

        # ================= 限域：注入块内不得出现网络调用 =================
        ('R138·注入块内无网络调用',      'fetch(',                                          0, '==', '纯客户端',
         ('/* ===== yl-R138 advstat138:', 'function YlxwAdvSession(on) {')),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点恒等' % name
    # E1/E2/E3/E4 的新形态不得等于旧形态，且旧形态不应作为新形态的整段前缀残留在「清零」语义里
    assert E1_OLD not in E1_NEW, 'E1 新形态不应包含旧形态'
    assert E3_OLD not in E3_NEW, 'E3 新形态不应包含旧形态'
    assert E4_OLD not in E4_NEW, 'E4 新形态不应包含旧形态'
    # E2 新形态必须含旧形态（插入式）——这是设计，故 E2_OLD 不作为清零 gate
    assert E2_OLD in E2_NEW, 'E2 应为插入式（旧行保留在后）'
    # 标记必须落在注入块里
    assert FR_MARK in (INJECT_JS + '\n' + INJECT_ANCHOR), '注入块必须含 YLXW_R138 标记'
    assert INJECT_ANCHOR in EDITS[0][2], 'E5 新形态必须保留注入锚'
    # 注入块 zh 域纯 ASCII
    bad = [c for c in INJECT_JS if ord(c) > 127]
    assert not bad, '注入块必须纯 ASCII（中文一律写成 backslash-u 转义）: %r' % bad[:10]
    assert 'fetch(' not in INJECT_JS, '注入块不得含 fetch('
    for pat in ('iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-'):
        assert pat not in INJECT_JS, '注入块含禁用模式 %r' % pat
    # 注入块不得复刻 advend105 的冻结 needle（防抬计数）
    assert 'if (!YLXW_ADV_SESS) return;' not in INJECT_JS, '不得复刻 R105 会话外丢弃串'
    assert 'YLXW_ADV_ACC' not in INJECT_JS, '注入块不得出现 YLXW_ADV_ACC'


def main() -> int:
    ap = argparse.ArgumentParser(description='R-138 自动历练详细统计（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2915-*.js）')
    a = ap.parse_args()
    src_path = a.src

    try:
        _precheck()
    except AssertionError as e:
        print('[FAIL] 断言失败: %s' % e)
        return 1

    if not os.path.exists(src_path):
        print('[FAIL] source not found: %s' % src_path)
        return 2
    with io.open(src_path, 'rb') as f:
        src = f.read()

    # 1) 幂等：已是补丁后形态 → rc=3 不写盘
    if FR_MARK.encode('ascii') in src and E1_OLD.encode('ascii') not in src:
        print('[SKIP] source looks already patched（已含 YLXW_R138 且旧掉落名形态清零）')
        return 3

    # 2) 锚点计数（rc=2 面）
    for name, old, new in EDITS:
        ob = old.encode('ascii')
        n = src.count(ob)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）：%r' % (name, n, ob))
            return 2
    if src.count(FR_MARK.encode('ascii')) != 0:
        print('[FAIL] 标记 %r 已存在（期望 0，疑部分补丁态）' % FR_MARK)
        return 2

    # 3) 应用（字节级单点替换）
    out = src
    for name, old, new in EDITS:
        out = out.replace(old.encode('ascii'), new.encode('ascii'), 1)

    # 4) 门禁
    ok = True
    for g in gates():
        label, needle, exp, op, note = g[:5]
        within = g[5] if len(g) > 5 else None
        txt = out.decode('utf-8', errors='replace')
        if within:
            s = txt.find(within[0]); e = txt.find(within[1], s + 1)
            seg = txt[s:e] if (s >= 0 and e > s) else ''
            act = seg.count(needle)
        else:
            act = txt.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-32s actual=%d expect==%d' % ('OK' if good else 'FAIL', label, act, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 5) 往返自证
    back = out
    for name, old, new in reversed(EDITS):
        back = back.replace(new.encode('ascii'), old.encode('ascii'), 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r138-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r138-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print('  已原子写回 %s' % src_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
