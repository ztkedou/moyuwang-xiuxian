# -*- coding: utf-8 -*-
r"""
yl_xinfa087_ext.py — 0.8.7 批次 · T3 心法六卷 100 级（客户端 · implXinfa）

=========================================================================== 任务口径
服务端环 `t3_xinfa087`（srv_patch_t3_xinfa.py）把六卷功法从 Lv10 扩到 Lv100：
  · 升级消耗 = TIER[floor((L-1)/10)] 十档段价（300..20000，玄品口径），满级累计 528,000；
  · 攻/防/血 +1%/级（满级恰 +100%）、暴击/命中/闪避 +0.2%/级（满级恰 +20%）；
  · POST /api/gongfa/levelup 重做为严格三段式【占位→扣款→补偿】，同档连点在占位即被拒
    （零扣费零叠加），频控放宽 20→60/min（连点根治靠幂等占位而非限流硬拦）。
本模块（装配位 xinfa087，在 fun086 之后、numbal 之前）做客户端两件事：
  ① **busy 防抖**：原 YlxwTGongfa 的禁用条件 `disabled: !!u`（actKey）是 React state，
     双击在**同一次渲染闭包**内连发两次 POST（u 还是旧值）——请求在途锁改用**同步 ref**
     （`O.useRef`，改的是普通对象属性，无渲染间隙），双击/连点的重复触发在进入异步前即被
     吞掉；完成后 finally 同步复位锁并复位 actKey。
  ② **新曲线渲染**：逐卷 Lv.x/100 进度条 + 下级价 + 已投入/满级累计；面板尾部渲染服务端
     下发的十档价目（t.tierCost，缺省本地同值兜底表）。连点说明写进面板文案。
服务端零信任面：等级/价格/加成全部以 GET /api/gongfa 响应为准（服务端权威），本模块
不自算价格、不乐观扣本地灵石——扣费由服务端 updatePlayerSave 完成，回执经 YL_STONE_ECHO
回显对齐本地（YLArb 仲裁通道 A）。

=========================================================================== 为什么整组件覆盖注册而不是就地改旧面板
旧 YlxwTGongfa 只有一处注册点 `gongfa: YlxwTGongfa`（bundle 基线恰 1 处）＋定义 1 处，
无其他引用；覆盖注册 `YLXW_COMP.gongfa = YlxwTXinfa087`（t7sect/t8mentor 同款模式）让
旧函数成死代码，零旧体锚点风险。注入点 `function YlxwPanelModal(p) {`（基线恰 1 处）在
`var YLXW_COMP = {…}`（@899574）**之后**（@1033685），赋值语句按文件序执行时对象已存在。

=========================================================================== 门禁计数清单（给接线人 implEventsUi 入 dryrun_087）
  ① 'function YlxwTXinfa087('                                   基线 0 → 改后 1
  ② 'YLXW_COMP.gongfa = YlxwTXinfa087;'                         基线 0 → 改后 1
  ③ 'if (lk.current) return null;'                              基线 0 → 改后 1（busy 防抖核心）
  ④ 'YlxwPost("/gongfa/levelup", { gongfa: key })'              基线 0 → 改后 1
  ⑤ 'var YLXW_XINFA_TIER_FALLBACK = [300, 500, 800, 1200, 2000, 3000, 5000, 8000, 12000, 20000];'
                                                                  基线 0 → 改后 1（与服务端 TIER 逐字一致）
  ⑥ 'function YlxwXinfaTierLine(tiers) {'                       基线 0 → 改后 1
  ⑦ '"\\u4fee\\u70bc\\u6210\\u529f" + '                          基线 0 → 改后 1（修炼成功 toast，zh 后 \u 形态）
  ⑧ 旧面板零改动断言：'function YlxwTGongfa() {'                 恒 1（旧函数保留为死代码，禁删）

=========================================================================== 技术约束遵守
· 注入块经 zh() 后无非 ASCII；不含 V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/auth_token/X-YL-）。
· 注入点唯一（expect=1）；apply() 返回门禁五元组列表；本文件不写任何产物。
· 拒绝码纪律：本模块不新增端点；服务端业务拒绝为 409（不触发 Xc() 403 登出），Je() 弹 toast。
"""

# --------------------------------------------------------------------------- 注入块（纯 ASCII 载体，中文由 build 侧 zh() 转义）

INJECT_JS = r'''
/* ===== yl-0.8.7 T3: 心法六卷 100 级（busy 防抖 + 新修炼曲线渲染） =====
   服务端 /gongfa 权威：六卷 level 1..100；攻/防/血 +1%/级，暴击/命中/闪避 +0.2%/级；
   升级价 = TIER 十档段价（tierCost 下发，此处只做兜底显示）。连点根治双保险：
   ①服务端占位幂等（同档并发只一单扣费，落败方 409 零扣费）；②本面板请求在途锁
   （同步 ref，渲染间隙双击直接吞掉）。两层任一生效都不会重复扣费。 */
var YLXW_XINFA_TIER_FALLBACK = [300, 500, 800, 1200, 2000, 3000, 5000, 8000, 12000, 20000];

function YlxwXinfaTierLine(tiers) {
  var tc = (tiers && tiers.length === 10) ? tiers : YLXW_XINFA_TIER_FALLBACK;
  var seg = [];
  for (var i = 0; i < 10; i++) seg.push("L" + (i * 10 + 1) + "-" + (i * 10 + 10) + " " + YlxwNum(tc[i]));
  return seg.join(" \u00b7 ");
}

function YlxwTXinfa087() {
  var r = YlxwUseList("/gongfa"), t = r.data, a = r.err, l = r.busy, c = r.load;
  var lk = O.useRef(!1);                          /* 请求在途锁：同步 ref，无渲染间隙 */
  var ks = O.useState(""), actKey = ks[0], setAk = ks[1];
  var run = O.useCallback(async function(key) {
    if (lk.current) return null;                  /* 在途：双击/连点的重复触发直接吞掉 */
    lk.current = !0; setAk("g" + key);
    try {
      var g = await YlxwPost("/gongfa/levelup", { gongfa: key });
      ia("修炼成功" + ((g && g.bonusText) ? ("，" + g.bonusText) : ""));
      await c(); YlxwDirty();
      return g;
    } catch (h) { Je((h && h.message) || "操作失败"); return null; }
    finally { lk.current = !1; setAk(""); }        /* actKey 复位 */
  }, [c]);
  var maxLv = YlxwNum(t && t.maxLevel) || 100;
  var maxTotal = YlxwNum(t && t.maxExpTotal) || 528000;
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: "灵石 " + YlxwNum(t && t.balance) }), children: "心法六卷" }),
    a ? e.jsx(YlxwErr, { retry: c, children: a }) : e.jsxs(e.Fragment, { children: [
      ((t && t.gongfas) || []).map(function(g) {
        var pct = Math.max(0, Math.min(100, (YlxwNum(g.level) / maxLv) * 100));
        return e.jsxs(YlxwRow, { children: [
          e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
            e.jsxs("span", { children: [g.name, " Lv.", YlxwNum(g.level), "/", maxLv, " \u00b7 ", g.bonusText] }),
            e.jsx(YlxwBtn, { disabled: !!actKey || g.maxed, onClick: function() { run(g.key); }, children: g.maxed ? "已大成" : "修炼" })
          ] }),
          e.jsx("div", { className: "h-1.5 bg-stone-700 rounded overflow-hidden mt-1.5", children:
            e.jsx("div", { className: "h-full bg-amber-500", style: { width: pct + "%" } }) }),
          e.jsx("div", { className: "text-[11px] text-stone-500 mt-1", children:
            g.maxed
              ? "已满级，累计投入 " + YlxwNum(g.exp) + " 灵石"
              : "下级需 " + YlxwNum(g.costNext) + " 灵石 \u00b7 已投入 " + YlxwNum(g.exp) + "/" + maxTotal })
        ] }, "g" + g.key);
      }),
      e.jsx(YlxwRow, { children: e.jsxs("div", { className: "text-[11px] text-stone-400 leading-5", children: [
        e.jsx("div", { children: "修炼价目（十档）：" + YlxwXinfaTierLine(t && t.tierCost) }),
        e.jsx("div", { children: "攻/防/血每级 +1%（满级翻倍），暴击/命中/闪避每级 +0.2%；连点已防重，同档只扣一次" })
      ] }) })
    ] })
  ] });
}
YLXW_COMP.gongfa = YlxwTXinfa087;
'''

# --------------------------------------------------------------------------- 主入口

_INJECT_ANCHOR = 'function YlxwPanelModal(p) {'
# 心法成功 toast（zh 转义后形态；门禁用）
_TOAST_ESC = '"\\u4fee\\u70bc\\u6210\\u529f" + '
_BTN_MAXED_ESC = 'children: g.maxed ? "\\u5df2\\u5927\\u6210" : "\\u4fee\\u70bc"'


def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 0) 注入组件 + 覆盖注册（必须在 YlxwPanelModal 之前：此锚点位于 YLXW_COMP 字面量之后）
    p.insert_before('xinfa087-block', _INJECT_ANCHOR, zh(INJECT_JS) + '\n',
                    expect=1, note='注入 YlxwTXinfa087 + YLXW_COMP.gongfa 覆盖注册（T3）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- 注入块本体 ----
        ('T3·新面板已定义',            'function YlxwTXinfa087(',                              1, '==', ''),
        ('T3·覆盖注册已生效',          'YLXW_COMP.gongfa = YlxwTXinfa087;',                    1, '==', ''),
        ('T3·busy 在途锁',            'if (lk.current) return null;',                         1, '==', '同步 ref，渲染间隙双击直接吞掉'),
        ('T3·锁复位+actKey 复位',      'lk.current = !1; setAk("");',                          1, '==', 'finally 内同步复位'),
        ('T3·修炼端点路径',            'YlxwPost("/gongfa/levelup", { gongfa: key })',         1, '==', ''),
        ('T3·价目兜底表与服务端一致',    'var YLXW_XINFA_TIER_FALLBACK = [300, 500, 800, 1200, 2000, 3000, 5000, 8000, 12000, 20000];', 1, '==', '《数值表-T2T3》§5.2 十档'),
        ('T3·价目行渲染函数',          'function YlxwXinfaTierLine(tiers) {',                  1, '==', ''),
        ('T3·价目行已挂载',            'YlxwXinfaTierLine(t && t.tierCost)',                   1, '==', '服务端 tierCost 优先'),
        ('T3·进度条已挂载',            'className: "h-full bg-amber-500", style: { width: pct + "%" }', 1, '==', ''),
        ('T3·成功 toast 带加成',       _TOAST_ESC,                                             1, '==', 'zh 转义形态'),
        ('T3·按钮满级态',             _BTN_MAXED_ESC,                                         1, '==', ''),
        ('T3·成本提示取服务端 costNext', 'YlxwNum(g.costNext)',                                 1, '==', '不自算价格'),
        ('T3·契约 100 级进度分母',      'YlxwNum(t && t.maxLevel) || 100',                     1, '==', ''),

        # ---- 旧面板/注册点零破坏 ----
        ('基线·旧面板函数保留（死代码）', 'function YlxwTGongfa() {',                             1, '==', '覆盖注册后成死代码，禁删'),
        ('基线·旧注册字面量保留',       'gongfa: YlxwTGongfa',                                  1, '==', '被本模块运行时覆盖，非替换'),
        ('基线·注入点未被破坏',        _INJECT_ANCHOR,                                         1, '==', ''),
        ('基线·灵石余额展示保留',       'YlxwNum(t && t.balance)',                              3, '==', '0.8.6 终产物基线 2 处（旧 gongfa 面板 + wudao 面板同字段）+ 本模块 1 = 3'),
        ('基线·修炼按钮旧在途锁仍在',    'disabled: !!u || g.maxed',                             1, '==', '旧面板不动（对照面）'),
    ]
    return gates
