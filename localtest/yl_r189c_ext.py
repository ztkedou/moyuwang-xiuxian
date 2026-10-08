# -*- coding: utf-8 -*-
r"""
yl_r189c_ext.py — R-189c：妖灵「灵纹」前 4 条战斗加成 · 取证 + 可见化（standalone 纯客户端）

★ 用户原话（唯一依据）：
  「此外，灵文（灵纹）系统现在加成有问题，闪避这个属性在游戏中未实装，减伤我不知道有没有实装，
    把灵纹的属性加成的前四条全都重做一下，后面2条不用动。」

==============================================================================
零、本环的取证结论（先结论，后证据）
==============================================================================
  · 6 条灵纹的数值 / 文案 **全部由服务端写死**（`srv/index_v28.ts` `R018B_RUNE_TABLE`），
    客户端只做两件事：(a) 展示 `t.rune.list[].desc`；(b) 把 `player.petSpirit.rune*`
    映射进战斗属性。⇒ **数值/文案的任何改动都必须是服务端补丁**，本环只交付客户端。

  · 前 4 条（锐/御/疾/噬）**在客户端已经完整接线并生效**（不是"只显示不生效"）：
      锐纹 critRate +1.5%      → 已生效
      御纹 damageReduction +2% → 已生效
      疾纹 dodgeRate +1.5%     → 已生效
      噬纹 lifeLeech +1%       → 已生效
    完整链路（详见 §一）：srv `R018B_RUNE_TABLE` → `r018bRuneEffect` → `r018bApplyRune`
      → `r018SpiritSync` 写 `player.petSpirit.rune{Crit,Dodge,Leech,DR}`
      → 客户端 `YlxwR18bRuneBattle(o,p)` 读 `p.petSpirit.rune*` → `YlxwBattleBonus`
      → 两套战斗引擎（快速结算 X0 / 回合制 YlxwSpellBuffs）**都消费** crit/dodge/DR/leech。

  · 「闪避未实装」「减伤不确定」**均被推翻**：玩家侧 `dodgeRate`/`damageReduction` 在两套
    引擎里都有明确读取点（§二 贴行 + §三 node 实测）。

  · 那么用户为何会觉得"未实装"？—— 见 §四：**加成在战斗里生效，但妖灵面板从不展示"灵纹贡献"**
    （面板的「主人加成」只列 攻/防/血/身法；「灵宠口径参考（非当前加成）」块的暴击/闪避来自
    灵宠亲密公式、与灵纹无关）。玩家在灵纹区看到「主人闪避 +1.5%」却找不到任何落点，自然判为未实装。

  · 本环交付 = **把前 4 条灵纹的真实、当前已生效的战斗贡献显示出来**（读 `player.petSpirit.rune*`），
    强度 **0 改动**（不加强/不削弱、不换属性），直接把"看得见"这件事补齐。数值若要改，见 §七。

==============================================================================
一、链路取证（贴代码行）
==============================================================================
  【服务端】srv/index_v28.ts
    · 灵纹表（6716-6723）：
        rui  critRate 0.015 / yu damageReduction 0.02 / ji dodgeRate 0.015 /
        shi  lifeLeech 0.01  / yun expMul 0.30          / tian ppMul 0.10
      ★ unlock = 10 / 20 / 30 / 40 / 50 / 60（**不是** 0/0/30/40/50/60）。
    · 效果纯函数 r018bRuneEffect（6738-6752）：按 kind 写 critRate/dodgeRate/lifeLeech/damageReduction。
    · 存档 payload r018bApplyRune（6754-6768）：写
        rune: rn.key, runeCrit, runeDodge, runeLeech, runeDR
    · 同步 r018SpiritSync（6495-6505）：`sd.player.petSpirit = payload`（合并已归位时清空）。
    · 换纹 POST /api/pet/rune（6782-6825）：改 rune_active 后 **调 r018SpiritSync**（6818）。
    · GET /api/pet 回显（13363-13366）：spirit 用同一 `r018bSpiritBonus`（含 rune*）。

  【客户端】build/assets/index-v2933-20261008.js
    · 战斗层挂载（1327367-1327377，`YlxwBattleBonus` 内）：
        /* R-018b D5 灵纹战斗类：锐/御/疾/噬（服务端写 player.petSpirit.rune*） */
        YlxwR18bRuneBattle(o, p);
    · YlxwR18bRuneBattle（1040381-1040388）：
        if (s.runeCrit)  o.critRate        += Number(s.runeCrit)  || 0;
        if (s.runeDodge) o.dodgeRate       += Number(s.runeDodge) || 0;
        if (s.runeLeech) o.lifeLeech       += Number(s.runeLeech) || 0;
        if (s.runeDR)    o.damageReduction += Number(s.runeDR)    || 0;
    · 封顶 YlxwBattleCapCfg（1511740）= {critRate .35, critDamage .8, dodgeRate .35,
        lifeLeech .25, damageReduction .5}（灵纹值远低于封顶，不会撞顶）。
    · 面板：YlxwR18bRuneRow（1040786-1040813）渲染 6 条灵纹按钮 + desc（服务端下发）。

==============================================================================
二、闪避 / 减伤 / 暴击 / 吸血 是否实装（贴读取点）
==============================================================================
  【快速结算 X0】（bundle 768332 起，`const X0=async(t,...)` 战斗循环内）
    · 闪避（玩家侧，敌攻时）：
        YlxwPB=YlxwBattleBonus(t),
        YlxwDOD=!G&&YlxwPB.dodgeRate>0&&Math.random()<YlxwPB.dodgeRate,   // G=当前出手方是否玩家
    · 暴击（玩家侧）：F=.1+(G?te:ee)/ne*.1+(G?YlxwPB.critRate:0); W=min(.35,F); K=!YlxwDOD&&rand<W
    · 减伤（玩家侧，敌攻时）：
        (!G&&!YlxwDOD&&YlxwPB.damageReduction>0)?round(v*(1-min(.6,YlxwPB.damageReduction))):v
    · 吸血（玩家侧，命中后）：G&&X>0&&YlxwPB.lifeLeech>0&&(M=min(S,M+floor(X*YlxwPB.lifeLeech)))

  【回合制】（bundle 780769 起，`QS(t)` 造玩家战斗实体；783400 起为主循环结算）
    · buffs 注入：buffs: m.concat(typeof YlxwSpellBuffs==="function"?YlxwSpellBuffs(t):[])
      （YlxwSpellBuffs 1329234：crit→{type:"crit",value}; dodge→{dodge}; lifeLeech→{lifeLeech};
        damageReduction→{damageReduction}）
    · 普通攻击读取（c=目标，l=出手方）：
        c.buffs.forEach(w=>{w.dodge&&w.dodge>$&&($=w.dodge), w.damageReduction&&...&&(M=w.damageReduction), ...});
        if($>0&&Math.random()<$) return {result:{miss:!0}};            // 闪避
        M>0&&(_=Math.round(_*(1-M)));                                   // 减伤
        r==="player"&&_>0&&l.buffs.forEach(w=>{w.lifeLeech&&...(l.hp+=floor(_*w.lifeLeech))});  // 吸血
    · 技能读取：A.type==="crit"→E+=A.value（暴击）；A.dodge→g（闪避）；A.damageReduction（减伤）。

  ⇒ 结论：**暴击 / 减伤 / 闪避 / 吸血 4 项，玩家侧两套引擎均已实装。**
     ★ 注意区分：bundle @1114xxx 的 `dodge:min(.25,.02+.015*layer)` / `vampire:...` /
       `critRate:min(.30,.05+.02*layer)` 是 **演武场/试炼 NPC（YlxwArenaEnemy）** 的属性表，
       与玩家侧无关，勿混淆。

==============================================================================
三、node 实测（把 bundle 真实函数抽出跑）
==============================================================================
  抽取 `YlxwBattleCapCfg` + `YlxwBattleCap` + `YlxwR18bRuneBattle` + `YlxwBattleBonus`
  （YlxwBondCap/fy/Pm/YlxwEqItems 置空桩），对 6 个 key 各造一个 mock player.petSpirit：
      rui   {"critRate":0.015,...}
      yu    {...,"damageReduction":0.02}
      ji    {...,"dodgeRate":0.015}
      shi   {...,"lifeLeech":0.01}
      yun   {"critRate":0,"dodgeRate":0,"lifeLeech":0,"damageReduction":0}
      tian  {"critRate":0,"dodgeRate":0,"lifeLeech":0,"damageReduction":0}
      none  全 0（无 petSpirit）
  ⇒ 前 4 条各自把对应属性 +1.5%/+2%/+1.5%/+1%，后 2 条（修为/PP）战斗层为 0（正确）。

==============================================================================
四、为什么玩家会觉得「闪避未实装」（根因）
==============================================================================
  · 妖灵面板「主人加成」卡片只列 攻击 / 防御 / 气血 / 身法（`YlxwTSpiritUse` lines 只 push
    b.attack/defense/maxHp/speed）；灵纹的 暴击/减伤/闪避/吸血 **不在该卡片里**。
  · 面板另有一块「灵宠口径参考（非当前加成）」，其中 暴击/闪避 来自 `YlxwSpiritBonusView`
    的 `YlxwPetBonusCrit/Dodge(pet.affection)`（**灵宠亲密公式**），与灵纹无关且被显式标注"非当前加成"。
  · 灵纹区只显示按钮 desc（"主人闪避 +1.5%"）与"当前：<key>"，**从不显示已生效数值**。
  ⇒ 玩家看得到"承诺"、看不到"兑现" ⇒ 判为未实装。本环把"兑现"显示出来。

==============================================================================
五、契约
==============================================================================
  · CLI：`--src <bundle.js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 探针）。
  · 就地替换 2 处（REPLACEMENTS）；每处打前断言 `count == 1`（锚点纯 ASCII）。
  · bytes 层读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 `<src>.bak-r189c-<时刻>`。
  · 幂等：产物已含标记 `/*[r189rune]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=成功；3=幂等未写盘；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`；needle 可为 tuple（合计计数）。
  · 探针：从补丁后产物实抽 `var ylxwRunePs = ... /*[r189rune]*/` 段，node 复算并校验
    4 条战斗灵纹 + 1 条非战斗灵纹的输出。
  · 不跑网络：只读 --src 指向的本地文件。
  · ★ 冻结针脚只钉本批**不动**的稳定形态，**绝不**钉 `[r180adv*]`/`[r185farm*]`/`[r184wudao]`/
    `[r187guide]`/`[r188med*]`/`[r190feed]`/`[r189ui]`。
  · ★ 强度：本环对灵纹数值 **0 改动**（仅新增展示行）。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# 幂等标记（本批）
IDEMPOTENT_MARK = '/*[r189rune]*/'

# --------------------------------------------------------------------------- 替换项
# ★ 形态约定：bundle 该区域中文为**字面 `\uXXXX`**（六字符）⇒ 本 .py 源码保持纯 ASCII，
#   用 `\\uXXXX`（双反斜杠）写出，运行期字符串即 `\uXXXX`。

# ---- ① YlxwR18bRuneRow：新增「当前灵纹战斗贡献」计算块 ----
R1_OLD = (
    '  var list = r.list || [];\n'
    '  var active = r.active || "";\n'
)
R1_NEW = (
    '  var list = r.list || [];\n'
    '  var active = r.active || "";\n'
    '  /* R-189c：读当前已生效灵纹的真实战斗贡献（player.petSpirit.rune*，服务端权威） */\n'
    '  var ylxwRunePs = (function () { try { var pl = (typeof YlxwPlayer === "function") ? YlxwPlayer() : null; return (pl && pl.petSpirit) || null; } catch (e) { return null; } })();\n'
    '  var ylxwRuneEff = [];\n'
    '  var ylxwRuneName = "";\n'
    '  for (var ylxwRi = 0; ylxwRi < list.length; ylxwRi++) { if (list[ylxwRi] && list[ylxwRi].key === active) { ylxwRuneName = String(list[ylxwRi].name || ""); break; } }\n'
    '  if (ylxwRunePs) {\n'
    '    var ylxwRc = Number(ylxwRunePs.runeCrit) || 0, ylxwRd = Number(ylxwRunePs.runeDR) || 0, ylxwRo = Number(ylxwRunePs.runeDodge) || 0, ylxwRl = Number(ylxwRunePs.runeLeech) || 0;\n'
    '    if (ylxwRc > 0) ylxwRuneEff.push("\\u66b4\\u51fb +" + (ylxwRc * 100).toFixed(1) + "%");\n'
    '    if (ylxwRd > 0) ylxwRuneEff.push("\\u51cf\\u4f24 +" + (ylxwRd * 100).toFixed(1) + "%");\n'
    '    if (ylxwRo > 0) ylxwRuneEff.push("\\u95ea\\u907f +" + (ylxwRo * 100).toFixed(1) + "%");\n'
    '    if (ylxwRl > 0) ylxwRuneEff.push("\\u5438\\u8840 +" + (ylxwRl * 100).toFixed(1) + "%");\n'
    '  }' + IDEMPOTENT_MARK + '\n'
)

# ---- ② YlxwR18bRuneRow：新增展示行（原说明行之后） ----
R2_OLD = (
    '    e.jsx("div", { className: "text-[11px] text-stone-500", children:\n'
    '      "\\u6bcf 10 \\u7ea7\\u89e3\\u9501 1 \\u6761\\uff0c\\u4efb\\u9009 1 \\u6761\\u751f\\u6548\\uff1b\\u9996\\u6b21\\u6fc0\\u6d3b\\u514d\\u8d39\\uff0c\\u6362\\u7eb9 " + cost + " \\u7075\\u77f3/\\u6b21\\u3002\\u5f53\\u524d\\uff1a" + (active ? active : "\\u672a\\u6fc0\\u6d3b") }),\n'
)
R2_NEW = (
    R2_OLD +
    '    e.jsx("div", { className: "text-[11px] text-cyan-400", children:\n'
    '      ylxwRuneEff.length\n'
    '        ? ((ylxwRuneName ? "\\u5f53\\u524d\\u751f\\u6548\\u300c" + ylxwRuneName + "\\u300d" : "\\u5f53\\u524d\\u7075\\u7eb9") + "\\u5df2\\u8ba1\\u5165\\u6218\\u6597\\uff1a" + ylxwRuneEff.join(" \\u00b7 "))\n'
    '        : "\\u5f53\\u524d\\u7075\\u7eb9\\u65e0\\u6218\\u6597\\u5c5e\\u6027\\u52a0\\u6210\\uff08\\u975e\\u6218\\u6597\\u7c7b / \\u672a\\u6fc0\\u6d3b / \\u5c5e\\u6027\\u540c\\u6b65\\u4e2d\\uff09" }),\n'
)

REPLACEMENTS = [
    ('r1_eff', R1_OLD, R1_NEW),
    ('r2_line', R2_OLD, R2_NEW),
]

# 冻结针脚（对**输入**校验）：本批不动的稳定形态（绝不含 [r180adv*]/[r185farm*]/[r184wudao]/
# [r187guide]/[r188med*]/[r190feed]/[r189ui]）。
FREEZE = [
    ('function YlxwR18bRuneRow(', 1),
    ('function YlxwR18bRuneBattle(', 1),
    ('function YlxwPlayer(', 1),
    ('var YLXW_C2_BATTLE = [', 1),
    ('YlxwBattleCapCfg = { critRate: 0.35', 1),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。
    needle 可为 tuple（多形态合计计数）。"""
    return [
        # ---- 幂等标记 ----
        ('R189c\u00b7\u5e42\u7b49\u6807\u8bb0 r189rune', IDEMPOTENT_MARK, 1, '==', '[r189rune] 恰 1 处'),
        # ---- ① 计算块 ----
        ('R189c\u2460\u00b7\u7075\u7eb9\u5b9e\u6548\u53d6\u503c\u5757', 'var ylxwRuneEff = [];', 1, '==', 'ylxwRuneEff 变量'),
        ('R189c\u2460\u00b7\u8bfb player.petSpirit.runeCrit', 'ylxwRunePs.runeCrit', 1, '>=',
         'runeCrit（R-196 增加第二处读取 ⇒ 用 >= 保持稳健）'),
        ('R189c\u2460\u00b7\u8bfb player.petSpirit.runeDR', 'ylxwRunePs.runeDR', 1, '==', 'runeDR'),
        ('R189c\u2460\u00b7\u8bfb player.petSpirit.runeDodge', 'ylxwRunePs.runeDodge', 1, '==', 'runeDodge'),
        ('R189c\u2460\u00b7\u8bfb player.petSpirit.runeLeech', 'ylxwRunePs.runeLeech', 1, '==', 'runeLeech'),
        ('R189c\u2460\u00b7\u66b4\u51fb\u6807\u7b7e', 'ylxwRuneEff.push("\\u66b4\\u51fb +"', 1, '==', '暴击 +'),
        ('R189c\u2460\u00b7\u51cf\u4f24\u6807\u7b7e', 'ylxwRuneEff.push("\\u51cf\\u4f24 +"', 1, '==', '减伤 +'),
        ('R189c\u2460\u00b7\u95ea\u907f\u6807\u7b7e', 'ylxwRuneEff.push("\\u95ea\\u907f +"', 1, '==', '闪避 +'),
        ('R189c\u2460\u00b7\u5438\u8840\u6807\u7b7e', 'ylxwRuneEff.push("\\u5438\\u8840 +"', 1, '==', '吸血 +'),
        ('R189c\u2460\u00b7YlxwPlayer \u53d6\u73a9\u5bb6', 'typeof YlxwPlayer === "function"', 1, '==', '安全取 player'),
        # ---- ② 展示行 ----
        ('R189c\u2461\u00b7\u300c\u5df2\u8ba1\u5165\u6218\u6597\uff1a\u300d',
         '\\u5df2\\u8ba1\\u5165\\u6218\\u6597\\uff1a', 1, '==', '已计入战斗：'),
        ('R189c\u2461\u00b7\u5f53\u524d\u751f\u6548\u300c\u540d\u300d',
         '\\u5f53\\u524d\\u751f\\u6548\\u300c', 1, '==', '当前生效「'),
        ('R189c\u2461\u00b7\u65e0\u6218\u6597\u52a0\u6210\u5151\u5e95',
         '\\u65e0\\u6218\\u6597\\u5c5e\\u6027\\u52a0\\u6210', 1, '==', '无战斗属性加成兜底'),
        ('R189c\u2461\u00b7\u539f\u8bf4\u660e\u884c\u672a\u52a8',
         '\\u6bcf 10 \\u7ea7\\u89e3\\u9501 1 \\u6761', 1, '==', '换纹说明行保留'),
        # ---- 未动（冻结针脚对应产物） ----
        ('R189c\u00b7YlxwR18bRuneBattle \u672a\u52a8', 'function YlxwR18bRuneBattle(', 1, '==', '战斗接线未动'),
        ('R189c\u00b7YlxwBattleCapCfg \u672a\u52a8', 'YlxwBattleCapCfg = { critRate: 0.35', 1, '==', '封顶未动'),
        ('R189c\u00b7YLXW_C2_BATTLE \u672a\u52a8', 'var YLXW_C2_BATTLE = [', 1, '==', '人物志增益表未动'),
        ('R189c\u00b7YlxwR18bRuneRow \u4ecd\u5728', 'function YlxwR18bRuneRow(', 1, '==', '函数体保留'),
    ]


# --------------------------------------------------------------------------- 主流程

def _read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


def _write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(text.encode('utf-8'))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _is_patched(s):
    return IDEMPOTENT_MARK in s


def _precheck(s):
    """返回 err（None 表示可打）。"""
    for name, old, new in REPLACEMENTS:
        c = s.count(old)
        if c != 1:
            return '锚点 %s 出现 %d 次（期望 1）' % (name, c)
    for needle, cnt in FREEZE:
        c = s.count(needle)
        if c != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, c, cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时 out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPLACEMENTS:
        out = out.replace(old, new, 1)
    return out, None


def _count(out, needle):
    if isinstance(needle, tuple):
        return sum(out.count(x) for x in needle)
    return out.count(needle)


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        c = _count(out, needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    """反向还原：把每个 new 逐字换回 old，应逐字回到 s0。"""
    rev = out
    for name, old, new in REPLACEMENTS:
        if rev.count(new) != 1:
            return False
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
        r = subprocess.run([node, '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _probe_rune(patched_text):
    """从补丁后产物实抽计算块，node 复算并校验 4 条战斗灵纹 + 非战斗灵纹。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。"""
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    i = patched_text.find('var ylxwRunePs =')
    j = patched_text.find(IDEMPOTENT_MARK, i)
    if i < 0 or j < 0:
        return False, 'ylxwRunePs 块未找到'
    block = patched_text[i:j]
    js = (
        'var YlxwPlayer = null;\n'
        'var CASES = {\n'
        '  rui:  { list:[{key:"rui", name:"\\u9510\\u7eb9"}],  active:"rui",  ps:{runeCrit:0.015} },\n'
        '  yu:   { list:[{key:"yu",  name:"\\u5fa1\\u7eb9"}],  active:"yu",   ps:{runeDR:0.02} },\n'
        '  ji:   { list:[{key:"ji",  name:"\\u75be\\u7eb9"}],  active:"ji",   ps:{runeDodge:0.015} },\n'
        '  shi:  { list:[{key:"shi", name:"\\u566c\\u7eb9"}],  active:"shi",  ps:{runeLeech:0.01} },\n'
        '  yun:  { list:[{key:"yun", name:"\\u8574\\u7eb9"}],  active:"yun",  ps:{} }\n'
        '};\n'
        'var EXPECT = {\n'
        '  rui:  "\\u5f53\\u524d\\u751f\\u6548\\u300c\\u9510\\u7eb9\\u300d\\u5df2\\u8ba1\\u5165\\u6218\\u6597\\uff1a\\u66b4\\u51fb +1.5%",\n'
        '  yu:   "\\u5f53\\u524d\\u751f\\u6548\\u300c\\u5fa1\\u7eb9\\u300d\\u5df2\\u8ba1\\u5165\\u6218\\u6597\\uff1a\\u51cf\\u4f24 +2.0%",\n'
        '  ji:   "\\u5f53\\u524d\\u751f\\u6548\\u300c\\u75be\\u7eb9\\u300d\\u5df2\\u8ba1\\u5165\\u6218\\u6597\\uff1a\\u95ea\\u907f +1.5%",\n'
        '  shi:  "\\u5f53\\u524d\\u751f\\u6548\\u300c\\u566c\\u7eb9\\u300d\\u5df2\\u8ba1\\u5165\\u6218\\u6597\\uff1a\\u5438\\u8840 +1.0%",\n'
        '  yun:  "\\u5f53\\u524d\\u7075\\u7eb9\\u65e0\\u6218\\u6597\\u5c5e\\u6027\\u52a0\\u6210\\uff08\\u975e\\u6218\\u6597\\u7c7b / \\u672a\\u6fc0\\u6d3b / \\u5c5e\\u6027\\u540c\\u6b65\\u4e2d\\uff09"\n'
        '};\n'
        'var keys = Object.keys(CASES);\n'
        'for (var ci = 0; ci < keys.length; ci++) {\n'
        '  var K = keys[ci];\n'
        '  var list = CASES[K].list, active = CASES[K].active;\n'
        '  YlxwPlayer = function () { return { petSpirit: CASES[K].ps }; };\n'
        '  ' + block.replace('\n', '\n  ') + '\n'
        '  var got = ylxwRuneEff.length\n'
        '    ? ((ylxwRuneName ? "\\u5f53\\u524d\\u751f\\u6548\\u300c" + ylxwRuneName + "\\u300d" : "\\u5f53\\u524d\\u7075\\u7eb9") + "\\u5df2\\u8ba1\\u5165\\u6218\\u6597\\uff1a" + ylxwRuneEff.join(" \\u00b7 "))\n'
        '    : "\\u5f53\\u524d\\u7075\\u7eb9\\u65e0\\u6218\\u6597\\u5c5e\\u6027\\u52a0\\u6210\\uff08\\u975e\\u6218\\u6597\\u7c7b / \\u672a\\u6fc0\\u6d3b / \\u5c5e\\u6027\\u540c\\u6b65\\u4e2d\\uff09";\n'
        '  if (got !== EXPECT[K]) throw new Error(K + " \\u4e0d\\u7b26: " + got);\n'
        '}\n'
        'console.log("rune-probe>> " + keys.length + " cases ok");\n'
    )
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        if r.returncode != 0:
            return False, r.stderr.decode('utf-8', 'replace').strip()[:400]
        return True, r.stdout.decode('utf-8', 'replace').strip()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r189c] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r189c] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r189c] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r189c] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r189c] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r189c] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _probe_rune(out)
    if ok is False:
        print('[r189c] SELFTEST FAIL rune-probe: ' + pmsg)
        return 1
    print('[r189c] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg, pmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r189c] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r189c] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r189c] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r189c] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r189c] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r189c] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r189c-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r189c] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
