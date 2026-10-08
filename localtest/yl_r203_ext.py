# -*- coding: utf-8 -*-
r"""
yl_r203_ext.py — R-196(需求号)/R-201(落盘号)：把「静态冷却快照」改成「走秒倒计时」standalone 纯客户端

★ 用户原话（逐字，唯一依据）：
  「免费喂养后写的30分钟冷却，但是没有30分钟冷却的计时，不知道还剩多少时间。
    游戏还有几个其他的地方也是没有剩余时间的提示。想办法都加上。」

★ ★ 命名说明（重要）：本补丁的**需求号是 R-196**，但 `localtest/yl_r196_ext.py` 已被
  另一个**已上线**的 R-196（「灵纹前 4 条加成重设 / 客户端接线」，标记 `/*[r196rune]*/`，
  已在 build_v26n.py:626 注册）占用 ⇒ 本环落到**下一个空位 `yl_r203_ext.py`**，
  幂等标记 `/*[r203cd]*/`，需在 STANDALONE_CLIENT 末位追加
  `('r203', os.path.join(HERE, 'localtest', 'yl_r203_ext.py')),`。

★ 根因（本环复核确认）：
  这些位置**都有文字**，但文字是**渲染时的一次性快照**：
  服务端只在下发时给一个「剩余量」（cdLeftMs / cdLeft / freeCoolLeft / cooldownLeft），
  组件此后不再重渲染 ⇒ 屏幕上的「冷却 N 分」是**冻结的**，玩家看不出还剩多少。
  正确范式（仓库内已有）= 仙盟 T7：**组件内局部 tick state** + 每秒重渲染，
  且把「剩余量」在收到时换算成**绝对截止时刻** deadline，之后每秒 remaining=max(0,deadline-now)。

★ 本环边界（严格）：
  · 只做「静态冷却 → 走秒」。**不改任何文案/数值/说明文字**（那是 R-195 的活）。
  · 只新增 4 个客户端函数（YlxwR196Tick / YlxwR196Remain / YlxwR196Left / YlxwR196Cd）+
    在 6 处（8 个代码点）把静态冷却接上走秒。
  · **不加任何顶层/全局 setInterval**；tick 一律落在**组件内局部 state**（只让该卡片重渲染）。
  · 不改服务端（cdLeftMs 等**已经在下发**）、不改其它 yl_r*_ext.py / build 脚本 / 数值表。

==============================================================================
零、目标产物与取证口径
==============================================================================
  目标：build/assets/index-v2936-20261008.js（2,315,801 B；utf-8 解码后 2,147,239 char）。
  本环全部偏移/计数均对该文件**字符级实测**（Python 解码 utf-8 后按 char 计）。
  ★ 该产物把**中文字符串统一写成 \uXXXX 转义**（ASCII 形式），故本环替换锚点全为
    「纯 ASCII（含 \uXXXX 字面转义）」串，天然满足「锚点必须唯一 ASCII 串 count==1」。

==============================================================================
一、6 处目标（逐点，含单位与数据来源；offset 为 char）
==============================================================================
  S1 免费进食      YlxwR18FreeRow  @1035584  源=ff.cdLeftMs(剩余 ms, /api/pet 快照)
     `if (cdLeft > 0) ffTxt += " · 冷却 " + Math.ceil(cdLeft / 60000) + " 分";`
     `disabled: !!u || ffLeft <= 0 || cdLeft > 0`（按钮禁用也依赖它）
     ⇒ 走秒 + 按钮归零自动可用。★ YlxwR18FreeRow 原是被**普通函数调用**的渲染助手
       （YlxwR18Panel 在 `m ? ... : ...` 里条件调用它）⇒ 直接塞 hook 会在 m 由空转非空时
       改变父组件 hook 数（React 报错）。故**把它改成真正的 React 组件**（e.jsx 渲染），
       hook 归它自己管理，合法且只重渲染这一行。
  S2 奇遇抽奖      YlxwTAdventure  @960042   源=t.cdLeft(剩余 ms, /adventure/list 快照)
     `(YlxwNum(t.cdLeft) > 0 ? " · 冷却 " + Math.ceil(YlxwNum(t.cdLeft) / 60000) + " 分钟" : "")`
     + 抽一次按钮 `disabled: ... || YlxwNum(t.cdLeft) > 0`
  S3 秘境（入口 + 面板，普通 + 地宫）
     S3a 入口  $4(@1518588, 307KB 巨型组件) @1649084  源=YLXW_DGS.cdLeftMs(剩余 ms, /dungeon/status 快照)
        `"冷却中，约 "+Math.ceil(YLXW_DGS.cdLeftMs/1000)+" 秒后可再进"`
        ⇒ $4 太大，**不能**在 $4 内挂 tick（会每秒重渲染 307KB）；改用**自包含走秒件** YlxwR196Cd。
     S3b 面板  YlxwTDungeon @1059143  源=t.cdLeftMs / t.rogueCdLeftMs(剩余 ms, /dungeon/status 快照)
        `"冷却剩余": t.cdLeftMs > 0 ? YlxwMin(t.cdLeftMs) : "无"`（地宫同理）
  S4 灵田照料      YlxwTFarmT5 @1186470 与 YlxwTFarmT10 @1195104（死代码，覆盖前保留）
     源=care.tendReadyAt(**绝对时刻**!) ⇒ YlxwFtTendCdMs(care)=max(0,tendReadyAt-now) **本身已实时**，
     只缺「组件每秒重渲染」⇒ 只补一个局部 tick 即可，**该表达式一字不改**（含按钮 disabled）。
  S5 万妖巢穴      YlxwTActBoss @1218023/1218974  源=cur.freeCoolLeft / cur.paidCoolLeft(剩余 **秒**)
     文本 `" · 免费冷却 " + N + " 秒"`；免费/收费按钮 `disabled: ... || N > 0` 与按钮文案 `"冷却 " + ceil(N/60) + " 分"`
  S6 渡劫观测面板  YlxwTRebirth @1057009  源=t.cooldownLeft(剩余 ms, /rebirth/status 快照)
     `"冷却": t.cooldownLeft > 0 ? YlxwMin(t.cooldownLeft) : "无"` + 发起渡劫按钮 disabled

  ★ 走秒机制（统一）：
     · YlxwR196Tick()           组件内局部 tick（useState+useEffect+1s setInterval），只重渲染本组件。
     · YlxwR196Remain(rf,ms,key) 把「剩余量 ms」按 key(快照标识) 换算成绝对 deadline，返回实时剩余。
     · YlxwR196Left(ms,key)      = Tick + Remain（给「能挂 hook」的组件直接用）。
     · YlxwR196Cd({k,ms,f,z})    = 自包含走秒件（返回字符串），给 $4 这种巨型组件内联用。
     · S2/S3b/S5/S6 用 Object.assign 把服务端快照对象**归一化**成本地 live 对象
       （只覆盖那 1~2 个冷却字段），从而该组件内**所有**引用（文本/按钮/禁用）自动走秒，零额外改动。

  ★ 其它「静态冷却」排查：见 §五（结论：主 6 处之外，未发现新的独立静态冷却显示点）。

==============================================================================
二、冻结针脚（本环**不动**，对**输入**校验 count，全 ASCII）
==============================================================================
  仙盟 T7 走秒范式原样（data-tick 仅 1 处）｜YlxwFtTendCdMs / YlxwFtCdText / YlxwMin 定义
  ｜S4 的照料冷却表达式（2 处，原样保留，靠 tick 变活）｜S3b/S6/S5 的显示表达式（原样保留，靠归一化变活）
  ｜各组件签名 ｜YlxwR18FreeRow 原调用点 ｜YLXW_COMP 注册表。

==============================================================================
三、契约（照 localtest/yl_r199_ext.py）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check + 走秒探针）。
  · 二进制读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 <src>.bak-r201-<时刻>。
  · 幂等：产物已含标记 `/*[r203cd]*/` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 不跑网络：只读 --src 指向的本地文件。

==============================================================================
五、其它静态冷却排查（结论：未发现新的独立显示点）
==============================================================================
  全库 `Math.ceil(.../60000)` 冷却显示、`cdLeftMs`/`cdLeft`/`freeCoolLeft`/`paidCoolLeft`/
  `cooldownLeft`/`tendReadyAt` 全部读取点已逐一核对，均落在本环 6 处之内；
  仙盟 T7 退盟冷却（data-tick）**本来就是走秒**，本环照抄其范式、未改动它。
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

IDEMPOTENT_MARK = '/*[r203cd]*/'

# --------------------------------------------------------------------------- 新增走秒件（ASCII-only）
HELPER = r'''/* R-196/R-201: local 1s tick (component-scoped; re-renders only this widget, never the whole app). */
function YlxwR196Tick() {
  var st = O.useState(0), setTk = st[1];
  O.useEffect(function () {
    var id = setInterval(function () { setTk(function (x) { return x + 1; }); }, 1000);
    return function () { clearInterval(id); };
  }, []);
  return 0;
}
/* R-196/R-201: server sends a "remaining ms" snapshot; convert it to a live remaining value.
   rf = useRef(null) holder ; ms = remaining ms ; key = snapshot id (deadline re-armed when it changes). */
function YlxwR196Remain(rf, ms, key) {
  var m = Number(ms) || 0;
  if (!rf.current || rf.current.k !== key) rf.current = { k: key, dl: m > 0 ? Date.now() + m : 0 };
  return rf.current.dl > 0 ? Math.max(0, rf.current.dl - Date.now()) : 0;
}
function YlxwR196Left(ms, key) {
  YlxwR196Tick();
  var rf = O.useRef(null);
  return YlxwR196Remain(rf, ms, key);
}
/* R-196/R-201: self-contained ticker (string) for huge components where a local hook is impractical. */
function YlxwR196Cd(a) {
  var left = YlxwR196Left(Number(a && a.ms) || 0, a && a.k);
  var f = (a && a.f) || YlxwT7FmtLeft;
  return left > 0 ? f(left) : ((a && a.z != null) ? a.z : f(0));
}
''' + IDEMPOTENT_MARK + '\n'

# --------------------------------------------------------------------------- 替换项
REPLACEMENTS = []

# R0 —— 注入走秒件（落在 YlxwT7RealmName 之前；与仙盟 T7 的格式化器同处模块作用域）
REPLACEMENTS.append((
    'R0 注入走秒件 + 幂等标记',
    'function YlxwT7RealmName(idx) {',
    HELPER + 'function YlxwT7RealmName(idx) {',
))

# R1 —— S1 免费进食：渲染助手 → 真组件（hook 合法），cdLeft 走秒，按钮归零自动可用
REPLACEMENTS.append((
    'S1a YlxwR18FreeRow 转为 React 组件（hook 合法）',
    'function YlxwR18FreeRow(t, m, f, u) {',
    'function YlxwR18FreeRow(a0) { var t = a0.t, m = a0.m, f = a0.f, u = a0.u;',
))
REPLACEMENTS.append((
    'S1b cdLeft 由剩余量换算为实时剩余',
    '  var cdLeft = YlxwNum(ff.cdLeftMs);',
    '  var cdLeft = YlxwR196Left(YlxwNum(ff.cdLeftMs), ff.cdLeftMs);',
))
REPLACEMENTS.append((
    'S1c 冷却文案走秒（分 -> 分秒）',
    r'  if (cdLeft > 0) ffTxt += " \u00b7 \u51b7\u5374 " + Math.ceil(cdLeft / 60000) + " \u5206";',
    r'  if (cdLeft > 0) ffTxt += " \u00b7 \u51b7\u5374 " + YlxwT7FmtLeft(cdLeft);',
))
REPLACEMENTS.append((
    'S1d 调用点改为 e.jsx 渲染组件',
    'YlxwR18FreeRow(t, m, f, u),',
    'e.jsx(YlxwR18FreeRow, { t: t, m: m, f: f, u: u }),',
))

# R2 —— S2 奇遇抽奖：局部 tick + 快照归一化（cdLeft 走秒；文案改分秒；按钮禁用随归零解除）
#   ★ 关键：YlxwTAdventure 的 head 是**一整条巨型 var 语句**（`var r = ..., N = async function() { ... };`），
#     必须把 tick/hook 插在 `function ... {` 之后（var 之前，合法语句边界、hook 无条件最先调用），
#     把归一化插在那条 var 语句**结束之后**（`};` 与 `return` 之间）——绝不能劈开 var，也不能丢声明关键字。
REPLACEMENTS.append((
    'S2a YlxwTAdventure 挂局部 tick（插在函数头之后、那条巨型 var 之前）',
    'function YlxwTAdventure() {\n'
    '  var r = YlxwUseList("/adventure/list"), t = r.data, a = r.err, l = r.busy, c = r.load,',
    'function YlxwTAdventure() {\n'
    '  YlxwR196Tick(); var __cd = O.useRef(null);\n'
    '  var r = YlxwUseList("/adventure/list"), t = r.data, a = r.err, l = r.busy, c = r.load,',
))
REPLACEMENTS.append((
    'S2a2 YlxwTAdventure cdLeft 归一化（插在那条 var 语句结束之后、return 之前）',
    '  };\n  return e.jsxs(YlxwPanel, { children: [e.jsx(YlxwTitle, { extra: e.jsx(YlxwBtn, { disabled: g || l ||',
    '  };\n'
    '  if (t) t = Object.assign({}, t, { cdLeft: YlxwR196Remain(__cd, YlxwNum(t.cdLeft), t.cdLeft) });\n'
    '  return e.jsxs(YlxwPanel, { children: [e.jsx(YlxwTitle, { extra: e.jsx(YlxwBtn, { disabled: g || l ||',
))
REPLACEMENTS.append((
    'S2b 冷却文案走秒（分钟 -> 分秒）',
    r'(YlxwNum(t.cdLeft) > 0 ? " \u00b7 \u51b7\u5374 " + Math.ceil(YlxwNum(t.cdLeft) / 60000) + " \u5206\u949f" : "")',
    r'(YlxwNum(t.cdLeft) > 0 ? " \u00b7 \u51b7\u5374 " + YlxwT7FmtLeft(YlxwNum(t.cdLeft)) : "")',
))

# R3 —— S3a 秘境入口（$4 巨型组件）：内联自包含走秒件
REPLACEMENTS.append((
    'S3a 秘境入口冷却走秒（$4 内联 YlxwR196Cd）',
    r'children:"\u51b7\u5374\u4e2d\uff0c\u7ea6 "+Math.ceil(YLXW_DGS.cdLeftMs/1000)+" \u79d2\u540e\u53ef\u518d\u8fdb"',
    r'children:["\u51b7\u5374\u4e2d\uff0c\u7ea6 ",e.jsx(YlxwR196Cd,{k:YLXW_DGS.cdLeftMs,ms:YLXW_DGS.cdLeftMs})," \u79d2\u540e\u53ef\u518d\u8fdb"]',
))

# R4 —— S3b 秘境面板（普通 + 地宫）：局部 tick + 两个冷却字段归一化
REPLACEMENTS.append((
    'S3b YlxwTDungeon 挂局部 tick + cdLeftMs/rogueCdLeftMs 归一化',
    'function YlxwTDungeon() {\n'
    '  var r = YlxwUseList("/dungeon/status"), t = r.data, a = r.err, l = r.busy, c = r.load;',
    'function YlxwTDungeon() {\n'
    '  var r = YlxwUseList("/dungeon/status"), t = r.data, a = r.err, l = r.busy, c = r.load;\n'
    '  YlxwR196Tick(); var __cdN = O.useRef(null), __cdR = O.useRef(null);\n'
    '  if (t) t = Object.assign({}, t, { cdLeftMs: YlxwR196Remain(__cdN, YlxwNum(t.cdLeftMs), t.cdLeftMs),'
    ' rogueCdLeftMs: YlxwR196Remain(__cdR, YlxwNum(t.rogueCdLeftMs), t.rogueCdLeftMs) });',
))

# R5 —— S4 灵田照料（T5 与死代码 T10）：源是绝对时刻，只需局部 tick（表达式一字不改）
_FARM_HEAD = ('function %s() {\n'
              '  var r = YlxwUseList("/farm/status"), t = r.data, a = r.err, l = r.busy, c = r.load,'
              ' d = YlxwUseAct(c), u = d.actKey, f = d.run;')
REPLACEMENTS.append((
    'S4a YlxwTFarmT5 挂局部 tick（照料冷却变活）',
    _FARM_HEAD % 'YlxwTFarmT5',
    _FARM_HEAD % 'YlxwTFarmT5' + '\n  YlxwR196Tick();',
))
REPLACEMENTS.append((
    'S4b YlxwTFarmT10 挂局部 tick（死代码同步）',
    _FARM_HEAD % 'YlxwTFarmT10',
    _FARM_HEAD % 'YlxwTFarmT10' + '\n  YlxwR196Tick();',
))

# R6 —— S5 万妖巢穴：局部 tick（必须在 !ev 早退之前）+ cur 冷却字段归一化（秒）
REPLACEMENTS.append((
    'S5a YlxwTActBoss 挂局部 tick（早退之前）',
    'function YlxwTActBoss(p) {\n  var ev = p.ev, engineOn = p.engineOn;',
    'function YlxwTActBoss(p) {\n  var ev = p.ev, engineOn = p.engineOn;\n'
    '  YlxwR196Tick(); var __cdF = O.useRef(null), __cdP = O.useRef(null);',
))
REPLACEMENTS.append((
    'S5b cur.freeCoolLeft/paidCoolLeft 归一化（秒）',
    '  if (!cur && bosses.length) cur = bosses[0];',
    '  if (!cur && bosses.length) cur = bosses[0];\n'
    '  if (cur) cur = Object.assign({}, cur, {'
    ' freeCoolLeft: Math.ceil(YlxwR196Remain(__cdF, YlxwNum(cur.freeCoolLeft) * 1000, cur.freeCoolLeft) / 1000),'
    ' paidCoolLeft: Math.ceil(YlxwR196Remain(__cdP, YlxwNum(cur.paidCoolLeft) * 1000, cur.paidCoolLeft) / 1000) });',
))

# R7 —— S6 渡劫观测面板：局部 tick + cooldownLeft 归一化
REPLACEMENTS.append((
    'S6 YlxwTRebirth 挂局部 tick + cooldownLeft 归一化',
    'function YlxwTRebirth() {\n'
    '  var r = YlxwUseList("/rebirth/status"), t = r.data, a = r.err, l = r.busy, c = r.load,'
    ' d = YlxwUseAct(c), u = d.actKey, f = d.run;',
    'function YlxwTRebirth() {\n'
    '  var r = YlxwUseList("/rebirth/status"), t = r.data, a = r.err, l = r.busy, c = r.load,'
    ' d = YlxwUseAct(c), u = d.actKey, f = d.run;\n'
    '  YlxwR196Tick(); var __cd = O.useRef(null);\n'
    '  if (t) t = Object.assign({}, t, { cooldownLeft: YlxwR196Remain(__cd, YlxwNum(t.cooldownLeft), t.cooldownLeft) });',
))

# 冻结针脚：本环**不动**的稳定形态（对**输入**校验 count，全 ASCII）
FREEZE = [
    # —— 仙盟 T7 走秒范式原样（本环照抄的对象，不得改动）——
    ('"data-tick": tick', 1),                                    # 唯一 data-tick
    ('function YlxwT7FmtLeft(ms) {', 1),                         # 复用格式化器定义
    ('function YlxwFtCdText(ms) {', 1),                          # 灵田格式化器定义
    ('function YlxwFtTendCdMs(care) {', 1),                      # 照料冷却=绝对时刻换算
    (r'function YlxwMin(r) { return r >= 6e4 ? Math.ceil(r / 6e4) + " \u5206\u949f" : Math.ceil(r / 1e3) + " \u79d2"; }', 1),
    # —— S4 表达式原样（靠 tick 变活，不得改文案）——
    (r'YlxwFtTendCdMs(care) > 0 ? "\u51b7\u5374 " + YlxwFtCdText(YlxwFtTendCdMs(care)) : "\u7167\u6599"', 2),
    (r'disabled: !!u || YlxwFtTendCdMs(care) > 0', 2),
    # —— S3b/S6/S5 显示表达式原样（靠快照归一化变活，不得改文案）——
    (r'"\u51b7\u5374\u5269\u4f59": t.cdLeftMs > 0 ? YlxwMin(t.cdLeftMs) : "\u65e0"', 1),
    (r'"\u5730\u5bab\u51b7\u5374": t.rogueCdLeftMs > 0 ? YlxwMin(t.rogueCdLeftMs) : "\u65e0"', 1),
    (r'"\u51b7\u5374": t.cooldownLeft > 0 ? YlxwMin(t.cooldownLeft) : "\u65e0"', 1),
    (r'YlxwNum(cur.freeCoolLeft) + " \u79d2"', 1),
    (r'YlxwNum(cur.paidCoolLeft) + " \u79d2"', 1),
    (r'YlxwNum(cur.freeCoolLeft) > 0', 3),
    (r'YlxwNum(cur.paidCoolLeft) > 0', 3),
    # —— 组件签名 / 注册表 / 调用点（证明结构未动）——
    ('function YlxwTActBoss(p) {', 1),
    ('if (!cur && bosses.length) cur = bosses[0];', 1),
    ('var YLXW_COMP = { mail: YlxwTMail', 1),
    ('YLXW_COMP.farm=YlxwTFarmT10;', 1),
    ('YLXW_COMP.farm=YlxwTFarmT5;', 1),
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R201·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r203cd] 恰 1 处'),
        # 走秒件
        ('R201·走秒件 Tick', 'function YlxwR196Tick() {', 1, '==', '局部 tick 定义'),
        ('R201·走秒件 Remain', 'function YlxwR196Remain(rf, ms, key) {', 1, '==', '剩余量->实时 换算'),
        ('R201·走秒件 Left', 'function YlxwR196Left(ms, key) {', 1, '==', 'Tick+Remain 组合'),
        ('R201·走秒件 Cd', 'function YlxwR196Cd(a) {', 1, '==', '自包含走秒件'),
        ('R201·仅 1 个新 tick 定时器', 'setTk(function (x) { return x + 1; })', 1, '==', '无全局 interval'),
        # S1
        ('S1·组件化签名', 'function YlxwR18FreeRow(a0) { var t = a0.t, m = a0.m, f = a0.f, u = a0.u;', 1, '==', '渲染助手改组件'),
        ('S1·cdLeft 走秒', 'var cdLeft = YlxwR196Left(YlxwNum(ff.cdLeftMs), ff.cdLeftMs);', 1, '==', '剩余量换算'),
        ('S1·文案走秒', 'ffTxt += " \\u00b7 \\u51b7\\u5374 " + YlxwT7FmtLeft(cdLeft);', 1, '==', '分->分秒'),
        ('S1·旧分格式清零', 'Math.ceil(cdLeft / 60000)', 0, '==', '旧静态分已消失'),
        ('S1·调用点组件化', 'e.jsx(YlxwR18FreeRow, { t: t, m: m, f: f, u: u }),', 1, '==', 'e.jsx 渲染'),
        ('S1·旧调用点清零', 'YlxwR18FreeRow(t, m, f, u)', 0, '==', '旧普通调用已消失'),
        ('S1·按钮禁用随归零', 'disabled: !!u || ffLeft <= 0 || cdLeft > 0', 1, '==', 'cdLeft 现为实时值'),
        # S2
        ('S2·局部 tick+归一化', 'if (t) t = Object.assign({}, t, { cdLeft: YlxwR196Remain(__cd, YlxwNum(t.cdLeft), t.cdLeft) });', 1, '==', 'cdLeft 变活'),
        ('S2·文案走秒', 'YlxwT7FmtLeft(YlxwNum(t.cdLeft))', 1, '==', '分钟->分秒'),
        ('S2·旧分钟格式清零', 'Math.ceil(YlxwNum(t.cdLeft) / 60000)', 0, '==', '旧静态分钟已消失'),
        # S3a
        ('S3a·入口走秒件内联', 'e.jsx(YlxwR196Cd,{k:YLXW_DGS.cdLeftMs,ms:YLXW_DGS.cdLeftMs})', 1, '==', '$4 内联走秒'),
        ('S3a·旧秒格式清零', 'Math.ceil(YLXW_DGS.cdLeftMs/1000)', 0, '==', '旧静态秒已消失'),
        # S3b
        ('S3b·局部 tick+归一化', 'cdLeftMs: YlxwR196Remain(__cdN, YlxwNum(t.cdLeftMs), t.cdLeftMs)', 1, '==', '普通秘境变活'),
        ('S3b·地宫归一化', 'rogueCdLeftMs: YlxwR196Remain(__cdR, YlxwNum(t.rogueCdLeftMs), t.rogueCdLeftMs)', 1, '==', '地宫变活'),
        # S4 —— ★ 期望串必须与替换落点一致：tick 插在 **head 行之后**（与 S2a/S3b/S5a/S6 同惯例），
        #   不是紧跟 `{`。原写死 `function YlxwTFarmT5() {\n  YlxwR196Tick();` ⇒ 与替换不符、恒 FAIL。
        ('S4·T5 挂 tick', _FARM_HEAD % 'YlxwTFarmT5' + '\n  YlxwR196Tick();', 1, '==', 'T5 局部 tick（head 之后）'),
        ('S4·T10 挂 tick', _FARM_HEAD % 'YlxwTFarmT10' + '\n  YlxwR196Tick();', 1, '==', 'T10 局部 tick（head 之后）'),
        # S5
        ('S5·局部 tick', 'function YlxwTActBoss(p) {\n  var ev = p.ev, engineOn = p.engineOn;\n  YlxwR196Tick();', 1, '==', 'tick 在早退之前'),
        ('S5·free 归一化', 'freeCoolLeft: Math.ceil(YlxwR196Remain(__cdF, YlxwNum(cur.freeCoolLeft) * 1000, cur.freeCoolLeft) / 1000)', 1, '==', '免费冷却变活'),
        ('S5·paid 归一化', 'paidCoolLeft: Math.ceil(YlxwR196Remain(__cdP, YlxwNum(cur.paidCoolLeft) * 1000, cur.paidCoolLeft) / 1000)', 1, '==', '收费冷却变活'),
        # S6
        ('S6·局部 tick+归一化', 'cooldownLeft: YlxwR196Remain(__cd, YlxwNum(t.cooldownLeft), t.cooldownLeft)', 1, '==', '渡劫冷却变活'),
    ]
    for needle, cnt in FREEZE:
        g.append(('冻结 ' + needle[:34], needle, cnt, '==', '冻结既有形态'))
    return g


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
    """返回 None=可打；否则返回错误串（列出全部不符项）。对**原件** s 校验锚点与冻结针脚。"""
    if _is_patched(s):
        return None  # 幂等，交由 main 判 rc=3
    bad = []
    for name, old, new in REPLACEMENTS:
        n = s.count(old)
        if n != 1:
            bad.append('锚点 %s 出现 %d 次（期望 1）' % (name, n))
    for needle, cnt in FREEZE:
        n = s.count(needle)
        if n != cnt:
            bad.append('冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, n, cnt))
    if bad:
        return '; '.join(bad)
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


def _run_gates(out):
    """返回 None=全绿；否则返回失败串（列出全部失败项）。"""
    bad = []
    for label, needle, expect, op, note in gates():
        c = out.count(needle)
        if op == '==' and c != expect:
            bad.append('%s: count=%d expect %d' % (label, c, expect))
        if op == '>=' and c < expect:
            bad.append('%s: count=%d expect >=%d' % (label, c, expect))
    return '; '.join(bad) if bad else None


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
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
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


def _extract_fn(text, name):
    """从产物里**逐字抽出** function name(...) { ... }（大括号配对），失败返回 None。"""
    key = 'function ' + name + '('
    i = text.find(key)
    if i < 0:
        return None
    j = text.find('{', i)
    if j < 0:
        return None
    depth = 0
    k = j
    while k < len(text):
        ch = text[k]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[i:k + 1]
        k += 1
    return None


def _tick_probe(patched_text):
    """node 真跑：从**产物**抽出 YlxwT7FmtLeft 与 YlxwR196Remain，喂边界值验证走秒语义。

    返回 (ok, msg)；ok=None 表示无 node（跳过）。
    """
    node = _find_node()
    if not node:
        return None, 'node not found (skipped)'
    fmt = _extract_fn(patched_text, 'YlxwT7FmtLeft')
    rem = _extract_fn(patched_text, 'YlxwR196Remain')
    if not fmt or not rem:
        return False, 'extract failed: fmt=%s rem=%s' % (bool(fmt), bool(rem))
    js = ('// ==== 从产物逐字抽出的函数 ====\n'
          + fmt + '\n' + rem + '\n'
          + r'''
// ==== 探针 ====
var fail = 0;
function eq(tag, got, want) {
  var ok = (got === want);
  if (!ok) fail++;
  console.log((ok ? "  OK  " : "  FAIL") + "  " + tag + "  got=" + JSON.stringify(got) + " want=" + JSON.stringify(want));
}
function mk() { return { current: null }; }

console.log("[A] YlxwT7FmtLeft \u8fb9\u754c\uff08\u8de8 60s / 3600s\uff09");
eq("0ms",                YlxwT7FmtLeft(0),              "0\u79d2");
eq("12s",                YlxwT7FmtLeft(12000),          "12\u79d2");
eq("59s",                YlxwT7FmtLeft(59000),          "59\u79d2");
eq("60s->1\u52060\u79d2",        YlxwT7FmtLeft(60000),          "1\u52060\u79d2");
eq("1390s->23\u520610\u79d2",    YlxwT7FmtLeft(1390000),        "23\u520610\u79d2");
eq("3600s->1\u65f60\u5206", YlxwT7FmtLeft(3600000),        "1\u65f60\u5206");
eq("4980s->1\u65f623\u5206", YlxwT7FmtLeft(4980000),       "1\u65f623\u5206");
eq("30min",              YlxwT7FmtLeft(30*60*1000),     "30\u52060\u79d2");

console.log("[B] YlxwR196Remain\uff1a\u5269\u4f59\u91cf -> \u5b9e\u65f6\u5269\u4f59\uff08deadline \u6362\u7b97\uff09");
var rf = mk();
var cd = 30*60*1000;
var r1 = YlxwR196Remain(rf, cd, "k1");
eq("\u521a\u6536\u5230 30min \u5269\u4f59 \u2248 30min", (r1 >= cd - 5 && r1 <= cd), true);
eq("deadline \u5df2\u8fc7 -> 0", YlxwR196Remain({current:{k:"k1", dl: Date.now() - 1000}}, 0, "k1"), 0);
eq("deadline \u5df2\u8fc7 \u683c\u5f0f", YlxwT7FmtLeft(YlxwR196Remain({current:{k:"k1", dl: Date.now() - 1000}}, 0, "k1")), "0\u79d2");
var rf2 = mk(); YlxwR196Remain(rf2, 1800000, "a");
var dlA = rf2.current.dl;
YlxwR196Remain(rf2, 1800000, "a");          // \u540c key\uff1a\u4e0d\u5f97\u91cd\u7f6e deadline
eq("\u540c key \u4e0d\u91cd\u7f6e deadline", rf2.current.dl === dlA, true);
YlxwR196Remain(rf2, 600000, "b");           // \u65b0 key\uff1a\u4ee5\u6b64\u523b\u91cd\u53d6
eq("\u65b0 key \u91cd\u53d6 deadline(\u224810min)", (rf2.current.dl - Date.now()) <= 600000 && (rf2.current.dl - Date.now()) > 600000 - 50, true);
// \u6a21\u62df\u8d70\u79d2\uff1a\u628a deadline \u4eba\u4e3a\u62e8\u5230 now-1ms \u524d\uff0c\u9a8c\u8bc1\u5f52\u96f6\u4e14\u4e0d\u4e3a\u8d1f
var rf3 = mk(); YlxwR196Remain(rf3, 300000, "c"); rf3.current.dl = Date.now() - 1;
eq("\u8d70\u5230 0 \u4e0d\u4e3a\u8d1f", YlxwR196Remain(rf3, 300000, "c"), 0);
eq("\u5f52\u96f6\u540e\u683c\u5f0f 0\u79d2", YlxwT7FmtLeft(YlxwR196Remain(rf3, 300000, "c")), "0\u79d2");
// \u8d70\u79d2\u8fde\u7eed\u6027\uff1a\u628a deadline \u4eba\u4e3a\u62e8\u5230 now+65000
var rf4 = mk(); YlxwR196Remain(rf4, 1000, "d"); rf4.current.dl = Date.now() + 65000;
eq("65s \u5269\u4f59\u683c\u5f0f 1\u52065\u79d2", YlxwT7FmtLeft(YlxwR196Remain(rf4, 1000, "d")), "1\u52065\u79d2");

console.log(fail === 0 ? "[RESULT] ALL PASS" : ("[RESULT] " + fail + " FAILED"));
process.exit(fail === 0 ? 0 : 1);
''')
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js.encode('utf-8'))
        r = subprocess.run([node, tmp], capture_output=True)
        out = r.stdout.decode('utf-8', 'replace').strip()
        if r.returncode != 0:
            return False, out + '\n' + r.stderr.decode('utf-8', 'replace').strip()[:400]
        return True, out
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check → 走秒探针。"""
    s0 = _read(src)
    if _is_patched(s0):
        print('[r201] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r201] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r201] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r201] SELFTEST FAIL round-trip mismatch')
        return 1
    if not _is_patched(out):
        print('[r201] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r201] SELFTEST FAIL ' + nmsg)
        return 1
    ok, pmsg = _tick_probe(out)
    if ok is False:
        print('[r201] SELFTEST FAIL tick-probe: ' + pmsg)
        return 1
    print('[r201] SELFTEST OK: replacements=%d gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(REPLACEMENTS), len(gates()), len(out) - len(s0), nmsg))
    if pmsg:
        print('[r201] 走秒自证(node 真跑，从产物抽函数)：')
        print(pmsg)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r201] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if _is_patched(s0):
        print('[r201] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r201] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r201] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r201] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r201] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-46s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r201-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r201] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-46s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
