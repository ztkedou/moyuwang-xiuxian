# -*- coding: utf-8 -*-
r"""
yl_farm087_ext.py — 0.8.7 T10 灵田功能扩充 · 客户端面板覆盖（归属 implGrotto）

接线信息（implEventsUi 落表用）
--------------------------------------------------------------------------
  模块名 farm087；V28_MODULES 插在 grotto087 之后、xinfa087 之前（build-plan §1.1 定案）。
  apply(p, ctx)：p = yl_patch.Patcher；ctx['zh'] = 中文转 \uXXXX。
  注入锚 1：var YLXW_COMP = {                       → 前插 YlxwTFarmT10 组件（zh 后纯 ASCII）
  替换锚 2：stats: YlxwTStats };                    → 追加 YLXW_COMP.farm=YlxwTFarmT10;
  原 YlxwTFarm（bundle 内）零改动，保留为死代码（删除徒增断言面，T7/T8 同先例）。

覆盖内容（T9T10-洞府灵田.md §4.4 面板 IA + build-plan §4.5 契约 E1~E6 的消费端）
--------------------------------------------------------------------------
  · 头部：灵石余额 · 洞府 Lv.X（灵田产出 +N%）｜今日催熟 used/cap ｜ 一键收取（readyCount 徽标）
  · 洞府 autoHarvest 开启且 readyCount>0 → 进页自动调一次 /farm/harvest/all（useRef 防重入）
  · 田位卡 ×1..6：
      未开垦 → 开垦按钮（洞府不足置灰「需洞府 Lv.X」，服务端仍 409 权威）
      空田   → 作物按钮列（高阶作物带洞府门槛灰置）+ 连作衰减提示
      生长中 → 名称 · 成熟倒计时 · 状态徽标（虫害⚠/已照料✓/已催熟⚡/连作减产）+ [照料][催熟 N 灵石]
      已成熟 → [收获]（提前收=减半，服务端口径）
  · 玩法说明折叠块（扩→种→养→催→收 循环 + 轮作/虫害规则玩家文案）
  · 写操作全走 YlxwUseAct.run（busy 键 + toast + 刷新 + YlxwDirty）；
    tend/boost/harvest-all 的玩家可见文案由服务端 message 字段下发（服务端权威，客户端不硬编码数值口径）

断言信号（铁律⑥：断言打独有信号，勿用 toast 文本）
--------------------------------------------------------------------------
  催熟成功断言 matureAt 提前（响应字段）；照料断言 care.tended=1；一键收断言 harvested[] 长度与
  totalStones（见 localtest/_e2e_t9t10_grotto_farm.py E14 场景）。

门禁计数清单（供 dryrun_087 落表；接线人 implEventsUi）
--------------------------------------------------------------------------
  function YlxwTFarmT10() {        ==1
  YLXW_COMP.farm=YlxwTFarmT10;     ==1
  farm: YlxwTFarm,                 ==1（原注册行未动）
  function YlxwTFarm() {           ==1（原组件保留为死代码）
  "/farm/harvest/all"              ==2（autoHarvest 自动 + 按钮手动）
  "/farm/tend" / "/farm/boost" / "/farm/plant" / "/farm/unlock"  各==1
  status === 403                   与基线同（本模块不新增 403 语义）
"""
import re

# --------------------------------------------------------------------------- 注入块（中文经 ctx['zh'] 转义后落盘）

INJECT_JS = r'''
/* ===== yl-0.8.7 T10: 灵田扩充面板（YlxwTFarmT10 覆盖注册；原 YlxwTFarm 保留为死代码） =====
   服务端权威（t10_farm 环）：GET /farm/status 扩展（care/streak/boostCost/readyCount/nextUnlock/boostDaily）；
   POST /farm/tend | /farm/boost | /farm/harvest/all。业务拒绝一律 400/409（403 会被 Xc() 强制登出）。 */
function YlxwTFarmT10() {
  var r = YlxwUseList("/farm/status"), t = r.data, a = r.err, l = r.busy, c = r.load, d = YlxwUseAct(c), u = d.actKey, f = d.run;
  var m = (t && t.slots) || [], g = (t && t.crops) || {}, h = Object.keys(g);
  var gl = YlxwNum(t && t.grottoLevel);
  var bd = (t && t.boostDaily) || { used: 0, cap: 0 };
  var readyN = YlxwNum(t && t.readyCount);
  var pstore = Be(function (s) { return s.player; });
  var __auto = O.useRef(!1);
  O.useEffect(function () {
    if (__auto.current) return;
    try {
      var gt = pstore && pstore.grotto;
      if (gt && gt.autoHarvest && readyN > 0) { __auto.current = !0; f("hall", "/farm/harvest/all", {}); }
    } catch (e2) {}
  }, [t, readyN]);
  var badge = function (txt, cls, key) {
    return e.jsx("span", { className: cls, children: txt }, key);
  };
  var B_OK = "text-[11px] px-1.5 py-0.5 rounded bg-green-900/40 border border-green-600/50 text-green-300";
  var B_BOOST = "text-[11px] px-1.5 py-0.5 rounded bg-amber-900/40 border border-amber-500/50 text-amber-300";
  var B_PEST = "text-[11px] px-1.5 py-0.5 rounded bg-red-900/40 border border-red-600/50 text-red-300";
  var B_MUTE = "text-[11px] px-1.5 py-0.5 rounded bg-stone-800 border border-stone-600 text-stone-400";
  var cropBtn = function (N, x) {
    var cd = g[x] || {}, nl = YlxwNum(cd.grottoLevel), ok2 = !nl || gl >= nl;
    return e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u || !ok2,
      onClick: function () { f("p" + N.slot + x, "/farm/plant", { slot: N.slot, crop: x }, "已种下 " + (cd.name || YLXW_CROP[x] || x)); },
      children: (cd.name || YLXW_CROP[x] || x) + "（" + YlxwNum(cd.seed).toLocaleString() + " 灵石" + (nl && !ok2 ? " · 需洞府 Lv." + nl : "") + "）" }, x);
  };
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400",
      children: "灵石 " + YlxwNum(t && t.stones).toLocaleString() + " · 洞府 Lv." + gl + "（灵田产出 +" + gl + "%）" }), children: "灵田" }),
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap text-xs text-stone-400", children: [
      e.jsxs("span", { children: ["今日催熟 ", bd.used, " / ", bd.cap, " 次（随洞府等级提升）"] }),
      e.jsx(YlxwBtn, { disabled: !!u || readyN <= 0, onClick: function () { f("hall", "/farm/harvest/all", {}); },
        children: readyN > 0 ? "一键收取（" + readyN + "）" : "一键收取" })
    ] }),
    a ? e.jsx(YlxwErr, { retry: c, children: a }) : m.map(function (N) {
      var b = N.crop, care = N.care || {}, streak = YlxwNum(N.streak);
      if (!N.unlocked) {
        var needLv = YlxwNum(t && t.unlockGrottoLevel && t.unlockGrottoLevel[N.slot]);
        var lvOk = !needLv || gl >= needLv;
        var uc = YlxwNum(t && t.unlockCost && t.unlockCost[N.slot]);
        return e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
          e.jsx("span", { children: "田位 " + N.slot + "（未开垦）" + (needLv ? " · 需洞府 Lv." + needLv : "") }),
          e.jsx(YlxwBtn, { disabled: !!u || !lvOk, onClick: function () { f("u" + N.slot, "/farm/unlock", { slot: N.slot }, "已开垦"); },
            children: lvOk ? "开垦 " + uc.toLocaleString() + " 灵石" : "需洞府 Lv." + needLv })
        ] }) }, "s" + N.slot);
      }
      if (!b) return e.jsxs(YlxwRow, { children: [
        e.jsx("div", { className: "flex items-center justify-between gap-2 flex-wrap", children:
          e.jsx("span", { children: "田位 " + N.slot + "（空田）" + (streak > 0 ? " · 前茬同作物：本茬连作减产" : "") }) }),
        e.jsx("div", { className: "flex items-center gap-1.5 flex-wrap", children: h.map(function (x) { return cropBtn(N, x); }) })
      ] }, "s" + N.slot);
      var badges = [];
      if (care.tended) badges.push(badge("已照料✓", B_OK, "bt"));
      if (care.boosted) badges.push(badge("已催熟⚡", B_BOOST, "bb"));
      if (care.pest && !care.tended) badges.push(badge("虫害⚠", B_PEST, "bp"));
      if (streak > 0) badges.push(badge("连作减产", B_MUTE, "bs"));
      return e.jsxs(YlxwRow, { children: [e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsxs("span", { className: "flex items-center gap-1.5 flex-wrap", children: [
          e.jsx("span", { children: "田位 " + N.slot + " · " + b.name }), badges ] }),
        e.jsxs("span", { className: "flex items-center gap-1.5 flex-wrap", children: [
          !b.ready && e.jsx("span", { className: "text-xs text-stone-400", children: "成熟还需 " + YlxwMin(YlxwNum(b.leftMs)) }),
          !b.ready && e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () { f("t" + N.slot, "/farm/tend", { slot: N.slot }); }, children: "照料" }),
          !b.ready && !care.boosted && e.jsx(YlxwBtn, { tone: "ghost", disabled: !!u, onClick: function () { f("b" + N.slot, "/farm/boost", { slot: N.slot }); },
            children: "催熟 " + YlxwNum(N.boostCost).toLocaleString() }),
          b.ready && e.jsx(YlxwBtn, { disabled: !!u, onClick: function () { f("h" + N.slot, "/farm/harvest", { slot: N.slot }, "收获成功，灵石已入账"); }, children: "收获" })
        ] })
      ] }) ] }, "s" + N.slot);
    }),
    e.jsxs("details", { className: "text-xs text-stone-400", children: [
      e.jsx("summary", { children: "玩法说明" }),
      e.jsxs("div", { className: "space-y-1 pt-1.5", children: [
        e.jsx("div", { children: "① 开垦：第 4/5/6 块田需洞府等级达标后花灵石开垦；② 轮作：同田连种同作物产出递减，换作物即重置；" }),
        e.jsx("div", { children: "③ 照料：每日每田一次，清虫害并使当日收获提升；未照料且生虫害则减产；④ 催熟：灵石按剩余时长计费立即成熟，每田每日一次，每日总次数随洞府等级提升；" }),
        e.jsx("div", { children: "⑤ 收取：提前收获收益减半；洞府 Lv.4+ 开启自动收取后，进本页自动一键收取成熟田。" })
      ] })
    ] })
  ] });
}

'''


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('farm087 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 注入 YlxwTFarmT10 组件（必须在 var YLXW_COMP = { 之前定义/声明）
    p.insert_before('farm087-components', 'var YLXW_COMP = {', blk + '\n',
                    expect=1, note='注入 YlxwTFarmT10（T10 灵田面板）')

    # 1) 覆盖注册（原 farm: YlxwTFarm 行不动 = 死代码保留）
    p.replace('farm087-register', 'stats: YlxwTStats };',
              'stats: YlxwTStats };\nYLXW_COMP.farm=YlxwTFarmT10;', expect=1,
              note='YLXW_COMP.farm 覆盖注册为 T10 面板')

    # ------------------------------------------------------------- 门禁
    # ★ 0.8.9 T5（farm089）在 farm087 之后覆盖注册 YLXW_COMP.farm=YlxwTFarmT5，
    #    故「覆盖注册」「各端点调用」等全局面向计数的门禁，其期望值 +1（T5 面板各 1 处）。
    gates = [
        ('T10·YlxwTFarmT10 已定义',       'function YlxwTFarmT10() {', 1, '==', ''),
        ('T10·覆盖注册（farm087 行保留）', 'YLXW_COMP.farm=YlxwTFarmT10;', 1, '==', 'T5 另起一行覆盖为 T5，T10 行仍保留'),
        ('T10·原组件保留（死代码）',       'function YlxwTFarm() {', 1, '==', '不删原组件，防锚区互踩'),
        ('T10·原注册行未动',              'farm: YlxwTFarm,', 1, '==', ''),
        ('T10·一键收取调用（auto+按钮）',  '"/farm/harvest/all"', 4, '==', 'T10 2 + T5 2（farm089 覆盖面板另 2）'),
        ('T10·照料调用',                  '"/farm/tend"', 2, '==', 'T10 1 + T5 1'),
        ('T10·催熟调用',                  '"/farm/boost"', 2, '==', 'T10 1 + T5 1'),
        ('T10·种植调用（新旧组件各 1）',   '"/farm/plant"', 3, '==', '原 YlxwTFarm + T10 + T5'),
        ('T10·开垦调用（新旧组件各 1）',   '"/farm/unlock"', 3, '==', '同上'),
        ('T10·单收调用（新旧组件各 1）',   '"/farm/harvest"', 3, '==', '带闭引号，与 /farm/harvest/all 区分'),
        ('T10·status 调用（新旧组件各 1）', '"/farm/status"', 3, '==', '同上'),
        ('T10·洞府等级展示',              r'\u7075\u7530\u4ea7\u51fa +', 2, '==', 'T10 + T5 面板各 1（zh 转义形态）'),
        ('T10·玩法说明折叠块',            r'\u2460 \u5f00\u57a6\uff1a\u7b2c 4/5/6 \u5757\u7530', 1, '==', '打本模块独有信号（T7/T8 也有玩法说明）'),
        ('红线·未新增 403 语义',          'status === 403', 1, '==', '仅 0.8.5 秘境 gate 既有 1 处，本模块不新增'),
    ]
    return gates
