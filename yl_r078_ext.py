# -*- coding: utf-8 -*-
r"""
yl_r078_ext.py — R-078 灵宠·妖灵「收养」按钮：**显示消耗 + 灵石不足置灰/提示**

需求（用户原话）
--------------------------------------------------------------------------
  「灵宠系统中收养妖灵需要的灵石数量没有展示。」
  上一轮 R-071 已把「收养妖灵」改成**消耗 20000 灵石**（服务端 `R071_ADOPT_COST`），
  但玩家在按钮上看不到这个消耗、也不知道灵石够不够。

根因（实测，逐条给证据）
--------------------------------------------------------------------------
  R-071 的客户端按钮（本仓产物 `index-v281113` @1001842）写的是：

      var cost = YlxwNum(t && t.consts && t.consts.adoptCost);
      ...
      children: "收养妖灵" + (cost ? "（消耗 " + cost + " 灵石 · 随机品种品阶）" : "")

  ★ 但服务端 `GET /api/pet` 的 `consts` 表里**根本没有 `adoptCost`** ——
    `srv/index_v28.ts` 的 `consts:{ feedCost…, runeCost: R018B_RUNE_COST, runeTable: R018B_RUNE_TABLE, }`
    只有既有字段；`adoptCost/awayCost` 全仓 0 处（grep 确认）。
    服务端只在 **`POST /api/pet/adopt` 的回执**里带 `cost`（点击之后才拿得到，太晚）。
  ⇒ `t.consts.adoptCost === undefined` ⇒ `cost = 0` ⇒ 三元走 else ⇒ **按钮上什么都不显示**。
  ⇒ 这才是「消耗没展示」的真因：**不是按钮没写，是取值源不存在**。

本模块动作
--------------------------------------------------------------------------
  ① 客户端（本文件）：重写 `YlxwR18AdoptBtn` ——
     · 保留 R-071 的消耗源 `t.consts.adoptCost`（★ 一个字不改，R-071 门禁面原样保留）；
     · 补读**玩家当前灵石**（主游戏 store `Be.getState().player.spiritStones`）；
     · `disabled: !!u || _short`（灵石不足 ⇒ 置灰）；不足时按钮下方给一行红字提示
       「灵石不足：收养需 N 灵石，现有 M。」
  ② 服务端（配套 `srv_patch_r078.py`）：把 `adoptCost: R071_ADOPT_COST` / `awayCost: R071_AWAY_COST`
     补进 `GET /api/pet` 的 `consts` 表 —— **读既有常量、零硬编码**，以后调价显示自动跟着变。

  两者必须**同时上线**：只上客户端 ⇒ `adoptCost` 仍 undefined，退回「不显示」（无回归但也无修复）；
  只上服务端 ⇒ 消耗能显示、但不会置灰。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 只新建本文件；不改 build_v26n.py / localtest/* / srv/index_v28.ts / deploy_v28/*。
  · 锚点 = R-071 注入块的**完整 `YlxwR18AdoptBtn` 函数**（纯 ASCII，全仓唯一 count==1）；
    块内中文是 zh() 转义形态（字面 `\uXXXX`），故本文件的锚点/替换串一律用 `\\uXXXX` 书写。
  · 保留 R-071 门禁面：`function YlxwR18AdoptBtn(t, f, u) {` / `t && t.consts && t.consts.adoptCost` /
    `f("adopt", "/pet/adopt", {}, "\u5df2\u6536\u517b\u5996\u7075")` / `res.pet.rarity + "` 计数全部不变。
  · `Be`（主游戏 store，`const Be = Hm()(dw(...))` @570402）在注入块 @1001141 之前定义 ⇒ 同作用域可用。
  · CSS 类 `text-[11px] / text-red-400 / mt-1` 已在预生成 CSS `index-ZuV-l8Gt.css` 里确认存在。
  · ★ 接线顺序：必须排在 **r071** 之后（锚点是 r071 注入块的产物）。服务端配套 = SRV_CHAIN 的 srv_patch_r078.py。
"""

import re

INJECT_JS = ''          # 本模块只做「就地替换」，不需要额外注入块

# --------------------------------------------------------------------------- 锚点（R-071 注入块内的完整函数，纯 ASCII）

BTN_OLD = (
    'function YlxwR18AdoptBtn(t, f, u) {\n'
    '  var cost = YlxwNum(t && t.consts && t.consts.adoptCost);\n'
    '  return e.jsx(YlxwBtn, {\n'
    '    disabled: !!u,\n'
    '    onClick: function () {\n'
    '      f("adopt", "/pet/adopt", {}, "\\u5df2\\u6536\\u517b\\u5996\\u7075").then(function (res) {\n'
    '        if (res && res.pet) { try { ia("\\u5df2\\u6536\\u517b\\u300c" + res.pet.name + "\\u300d\\uff08" + res.pet.rarity + "\\u54c1\\uff09"); } catch (err) {} }\n'
    '      });\n'
    '    },\n'
    '    children: "\\u6536\\u517b\\u5996\\u7075" + (cost ? ("\\uff08\\u6d88\\u8017 " + cost + " \\u7075\\u77f3 \\u00b7 \\u968f\\u673a\\u54c1\\u79cd\\u54c1\\u9636\\uff09") : ""),\n'
    '  });\n'
    '}\n'
)

# 新形态：读余额 → 不足置灰 + 按钮下补红字提示（消耗源与 R-071 完全一致）
BTN_NEW = (
    'function YlxwR18AdoptBtn(t, f, u) {\n'
    '  var cost = YlxwNum(t && t.consts && t.consts.adoptCost);\n'
    '  var _p = Be.getState().player;\n'
    '  var _bal = YlxwNum(_p && _p.spiritStones);\n'
    '  var _short = cost > 0 && _bal < cost;\n'
    '  return e.jsxs(e.Fragment, { children: [\n'
    '    e.jsx(YlxwBtn, {\n'
    '      disabled: !!u || _short,\n'
    '      onClick: function () {\n'
    '        f("adopt", "/pet/adopt", {}, "\\u5df2\\u6536\\u517b\\u5996\\u7075").then(function (res) {\n'
    '          if (res && res.pet) { try { ia("\\u5df2\\u6536\\u517b\\u300c" + res.pet.name + "\\u300d\\uff08" + res.pet.rarity + "\\u54c1\\uff09"); } catch (err) {} }\n'
    '        });\n'
    '      },\n'
    '      children: "\\u6536\\u517b\\u5996\\u7075" + (cost ? ("\\uff08\\u6d88\\u8017 " + cost + " \\u7075\\u77f3 \\u00b7 \\u968f\\u673a\\u54c1\\u79cd\\u54c1\\u9636\\uff09") : ""),\n'
    '    }),\n'
    '    _short ? e.jsx("div", { className: "text-[11px] text-red-400 mt-1",\n'
    '      children: "\\u7075\\u77f3\\u4e0d\\u8db3\\uff1a\\u6536\\u517b\\u9700 " + cost + " \\u7075\\u77f3\\uff0c\\u73b0\\u6709 " + _bal + "\\u3002" }) : null,\n'
    '  ] });\n'
    '}\n'
)

# 门禁用：不足提示的完整字面串（★ 与 BTN_NEW 同形态 = 字面 \uXXXX，非真字符）
SHORT_TEXT = ('\\u7075\\u77f3\\u4e0d\\u8db3\\uff1a\\u6536\\u517b\\u9700 " + cost + " \\u7075\\u77f3'
              '\\uff0c\\u73b0\\u6709 " + _bal')


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    zh = ctx['zh']

    # 手滑护栏：旧/新串必须各含 R-071 门禁面与新增要素
    for key in ('t && t.consts && t.consts.adoptCost',
                'f("adopt", "/pet/adopt", {}, "\\u5df2\\u6536\\u517b\\u5996\\u7075")',
                'res.pet.rarity + "'):
        if key not in BTN_OLD or key not in BTN_NEW:
            raise AssertionError('r078 锚点/替换串异常：缺 R-071 门禁面 %r' % key)
    if 'Be.getState().player' not in BTN_NEW or '\\u7075\\u77f3\\u4e0d\\u8db3' not in BTN_NEW:
        raise AssertionError('r078 替换串异常：缺「余额读取 / 灵石不足」')

    p.replace('r078-adopt-cost', BTN_OLD, BTN_NEW, expect=1,
              note='收养按钮：显示消耗（R-071 源）+ 灵石不足置灰/提示')

    gates = [
        # ================= 本模块改动 =================
        ('R78·按钮保留 R-071 消耗源', 't && t.consts && t.consts.adoptCost', 1, '==', '服务端 consts.adoptCost'),
        ('R78·按钮读玩家余额',        'var _bal = YlxwNum(_p && _p.spiritStones);', 1, '==', 'Be = 主游戏 store'),
        ('R78·不足判定',              'var _short = cost > 0 && _bal < cost;', 1, '==', ''),
        ('R78·不足时置灰',            'disabled: !!u || _short,', 1, '==', ''),
        ('R78·不足时提示',            SHORT_TEXT, 1, '==', '红字：灵石不足：收养需 N，现有 M'),
        ('R78·按钮仍显示消耗',
         '\\uff08\\u6d88\\u8017 " + cost + " \\u7075\\u77f3 \\u00b7 \\u968f\\u673a\\u54c1\\u79cd\\u54c1\\u9636\\uff09', 1, '==', ''),
        ('R78·旧按钮体已清零',        BTN_OLD, 0, '==', '旧形态（不读余额、不置灰）'),
        ('R78·按钮内未自建 fetch',    'fetch(', 0, '==', '统一走 YlxwUseAct',
         ('function YlxwR18AdoptBtn(t, f, u) {', 'function YlxwR18AdoptRow(t, f, u) {')),
        # ================= 冻结：R-071 门禁面一个字不动 =================
        ('冻结·R71 收养按钮助手签名未动', 'function YlxwR18AdoptBtn(t, f, u) {', 1, '==', ''),
        ('冻结·R71 收养行助手签名未动',   'function YlxwR18AdoptRow(t, f, u) {', 1, '==', ''),
        ('冻结·R71 收养行挂载点未动',     ': YlxwR18AdoptRow(t, f, u),', 1, '==', ''),
        ('冻结·R71 收养端点未动',         'f("adopt", "/pet/adopt", {}, "\\u5df2\\u6536\\u517b\\u5996\\u7075")', 1, '==', ''),
        ('冻结·R71 收养 toast 未动',      'res.pet.rarity + "', 1, '==', ''),
        ('冻结·R71 归位放生行未动',       'function YlxwR18AwayReleaseRow(t, m, f, u) {', 1, '==', ''),
        ('冻结·v2810e YlxwTPet 未整体重写', 'function YlxwTPet() {', 1, '==', ''),
        ('冻结·r018 妖灵卡挂载未动',
         'm ? e.jsxs(e.Fragment, { children: [YlxwR18Card(t, m), YlxwR18Panel(t, m, f, u)] })', 1, '==', ''),
        ('冻结·R71 旧 m 定义未复活',      'm = t && t.pet;', 0, '==', 'R-072 修复面'),
    ]
    return gates
