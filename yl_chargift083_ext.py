# -*- coding: utf-8 -*-
"""
yl_chargift083_ext.py — 0.8.3 批次 · 人物志「赠送灵石」动态定价（cli-char）

=========================================================================== 一句话
把「人物志」模态框（组件 Nk）里**写死的** `R=100` 灵石，改成
「按当前好感度指数倍增」的纯函数 `YlxwGiftCost(fav)`，并让**计算式 / 按钮文案 /
按钮 disabled 阈值 / 早退条件**四处全部走同一个函数，杜绝公式散落不一致。

=========================================================================== 用户拍板公式
    R = Math.max(1000, Math.min(16000, Math.round(1000 * Math.pow(2, F / 40))))
    F = 当前好感度 favorability（游戏内被 clamp 在 [-100, 100]）

    好感 F   |  R
    ---------|------
    <= 0     |  1000（保底）
    40       |  2000
    80       |  4000
    120      |  8000
    >= 160   |  16000（封顶）

    E（好感增量）保持 5，本模块**不动 E**。

=========================================================================== 修订历史
    0.8.3（2026-09-28 14:48 上线）底数 = 25。上线后复核发现「末段太陡」：
        每 5 点好感送一次礼（E=5），0→100 共 20 次，累计 **100,876** 灵石
        （旧的固定 100×20 次 = 2,000，即贵约 50 倍），且最后 25 点占 53.3%。
    0.8.4（2026-09-28）用户拍板放缓：底数 25 → **40**。同口径 0→100 累计 **51,452**。
        形态不变（仍是「每 40 好感翻倍」的指数曲线、仍 clamp 在 [1000, 16000]），
        只是**倍率减半**：封顶从 F=100 推到 F=160，即全区间内都摸不到 16000 上限。
        ⇒ 保底/封顶两端仍必须有用例（F<=0 → 1000、F>=160 → 16000）。

=========================================================================== 侦察复核（cli-char 独立复核，非转述）
基线：build/assets/index-v28-20260928.js（1595579 chars，**只读，绝不回写**）

1) 逻辑位于**基座 bundle** 的人物志模态框组件 `Nk`（`const Nk=({isOpen:t,...})` @1503908），
   `title:"人物志"`，**不在** yl_char_ext.py 内。已确认 Nk 与 YlxwNum 同属**单一模块作用域**
   （bundle 尾部即顶层 `const p1=document.getElementById("root")`，无 IIFE 包裹）。
2) 精确原文（@1504910 起，实测 count==1）：
     `if(!j||a.spiritStones<100)return;const R=100,E=5;`
   其中 `j = d ? m.find(R=>R.id===d) : null`（@1503950 附近）⇒ **j 就是选中的 socialRelation 对象**，
   带 `.favorability`，故回调内可直接取 `j.favorability`。
3) 按钮（@1508885，实测 count==1）：
     `e.jsx("button",{onClick:$,disabled:a.spiritStones<100,className:"px-3 py-1.5 bg-yellow-900/20 ...",children:"💎 赠灵石 (100)"})`
   ⇒ 按钮与其上方的 `j.favorability` 渲染**同一作用域、同一条件块**（该块仅在 j 非空时渲染）。
4) `spiritStones<100` 全文 **2** 次：① 回调早退条件 ② 按钮 disabled。两处必须同步改，
   否则会出现「按钮可点但点下去静默 return」。
5) 数值守卫：`function YlxwNum(r) { return Number(r) || 0; }`（@810538，实测 count==1）。
   `Number(null)=0`、`Number(undefined)=NaN→0`、`Number("50")=50`、`Number(NaN)=NaN→0`
   ⇒ 复用它可以挡掉 NaN/字符串/空值三类毁档输入。
6) 好感 clamp 原文 `favorability:Math.min(100,Math.max(-100,_.favorability+E))`（实测 count==1）未动。

=========================================================================== NaN 防护（毁档级）
`R` 直接参与 `spiritStones:N.spiritStones-R`。若 R=NaN，spiritStones 会变 NaN 并随存档持久化 ⇒ 毁档。
`YlxwGiftCost` 全函数 try/catch + `YlxwNum` 归一 + `isFinite` 双重兜底，
**任何输入路径（null/undefined/字符串/NaN/±Infinity/对象）都不可能返回 NaN**。
边界表见 localtest/report_cli-char.md。

=========================================================================== 技术约束遵守
· 纯 ASCII 注入块（注释用英文，中文一律 \\uXXXX，经 zh() 后无非 ASCII）。
· 不含禁用模式：iframe / postMessage / XMLHttpRequest / auth_token / X-YL-。
· 每个 replace / insert_before 都带 expect=精确次数；apply() 返回门禁五元组列表。
· **只新建本文件 + 测试/报告**，不修改任何已有模块，不写回 build/assets/。
"""

# --------------------------------------------------------------------------- 注入块（纯 ASCII）

INJECT_JS = r'''
/* ===== yl-0.8.3/0.8.4: Character-Dex spirit-stone gift dynamic pricing (cli-char) =====
   R = clamp( round(1000 * 2^(F/40)), 1000, 16000 ),  F = favorability
   F<=0 -> 1000 ; F=40 -> 2000 ; F=80 -> 4000 ; F=120 -> 8000 ; F>=160 -> 16000
   Base was 25 in 0.8.3; slowed to 40 in 0.8.4 (0->100 total 100876 -> 51452).
   Fully guarded: never returns NaN / undefined / negative (NaN would corrupt the save). */
function YlxwGiftCost(fav) {
  try {
    var F = YlxwNum(fav);
    if (!isFinite(F)) return F > 0 ? 16000 : 1000;
    var R = Math.round(1000 * Math.pow(2, F / 40));
    if (!isFinite(R)) return F > 0 ? 16000 : 1000;
    return Math.max(1000, Math.min(16000, R));
  } catch (e) { return 1000; }
}
'''

# --------------------------------------------------------------------------- 锚点（均取自基线 raw 文本）

# —— 注入锚：与 YlxwNum / Nk 同作用域（函数声明提升，注入位置不影响调用）——
INJECT_ANCHOR = 'function YlxwNum(r) { return Number(r) || 0; }'

# —— (a) 计算式 + 早退条件（实测 count==1）——
CALC_ANCHOR = 'if(!j||a.spiritStones<100)return;const R=100,E=5;'

# —— (c) 按钮 disabled 阈值（实测 count==1；含 onClick:$ 前缀保证唯一）——
DIS_ANCHOR = 'onClick:$,disabled:a.spiritStones<100,'

# —— (b) 按钮文案（实测 count==1；💎 用转义书写，避免源码编码歧义）——
EMOJI_GEM = '\U0001F48E'
BTN_ANCHOR = 'children:"' + EMOJI_GEM + ' 赠灵石 (100)"'

# --------------------------------------------------------------------------- 替换文本

# (a) 早退条件与计算式统一走 YlxwGiftCost；E=5 原样保留
CALC_REPL = (
    'if(!j||a.spiritStones<YlxwGiftCost(j&&j.favorability))return;'
    'const R=YlxwGiftCost(j&&j.favorability),E=5;'
)

# ★ 0.8.7：本模块仍按 (a) 注入 `,E=5;`（chargift 排在 t6chardex 之前），
#   随后由 T6（yl_t6chardex_ext.py，T6-2 定档）就地改写为 `,E=2;`。
#   下面这份是**批后最终形态**，仅供本模块门禁断言「改名而非删除」使用，不参与打补丁。
CALC_REPL_E2 = CALC_REPL.replace(',E=5;', ',E=2;')

# (c) disabled 阈值同步为当前所需 R（避免「可点但静默 return」）
DIS_REPL = 'onClick:$,disabled:a.spiritStones<YlxwGiftCost(j&&j.favorability),'

# (b) 按钮文案动态显示当前所需灵石数
BTN_REPL = (
    'children:"' + EMOJI_GEM + ' 赠灵石 ("+YlxwGiftCost(j&&j.favorability)+")"'
)

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含改名 + 全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 0) 注入纯函数 YlxwGiftCost（模块作用域，三处调用点共用，杜绝公式散落）
    p.insert_before(
        'chargift083-fn',
        INJECT_ANCHOR,
        zh(INJECT_JS) + '\n',
        expect=1,
        note='注入 YlxwGiftCost(fav) 纯函数（全 try/catch，异常/非有限值一律回 1000）'
    )

    # 1) (a) 计算式 + 早退条件：R=100 写死 -> 动态计算
    p.replace(
        'chargift083-calc',
        CALC_ANCHOR,
        zh(CALC_REPL),
        expect=1,
        note='R=100,E=5 -> R=YlxwGiftCost(j.favorability),E=5；早退阈值同步'
    )

    # 2) (c) 按钮 disabled 阈值同步
    p.replace(
        'chargift083-disabled',
        DIS_ANCHOR,
        zh(DIS_REPL),
        expect=1,
        note='disabled:a.spiritStones<100 -> <YlxwGiftCost(j.favorability)'
    )

    # 3) (b) 按钮文案动态显示
    p.replace(
        'chargift083-btntext',
        BTN_ANCHOR,
        zh(BTN_REPL),
        expect=1,
        note='"💎 赠灵石 (100)" -> 动态显示当前所需灵石数'
    )

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- 注入块 ----
        ('T3·YlxwGiftCost 已定义',        'function YlxwGiftCost(fav)',                        1, '==', ''),
        ('T3·公式幂次 2^(F/40)',          'Math.pow(2, F / 40)',                               1, '==', '0.8.4 由 25 放缓到 40'),
        ('T3·旧底数 2^(F/25) 已清零',     'Math.pow(2, F / 25)',                               0, '==', ''),
        ('T3·保底/封顶 clamp',            'Math.max(1000, Math.min(16000, R))',                1, '==', ''),
        ('T3·复用数值守卫 YlxwNum',       'YlxwNum(fav)',                                      1, '==', ''),
        ('T3·异常兜底 return 1000',       '} catch (e) { return 1000; }',                      1, '==', ''),
        # ---- 三处修改 ----
        # ★ 0.8.7 T6（T6-2 定档，yl_t6chardex_ext.py）把默认赠灵石好感增量 `,E=5;` 改成 `,E=2;`
        #   ⇒ 本模块 (a) 的替换串字面形态不复存在；退为「旧字面 == 0」+「E=2 形态 == 1」。
        ('T3·(a) 计算式已改（旧字面已清零）', zh(CALC_REPL),                                  0, '==', '0.8.7 T6-2 把 ,E=5; 改 ,E=2;'),
        ('T3·(a) 计算式已改（E=2 形态）',    zh(CALC_REPL_E2),                                 1, '==', '同 (a) 语义，好感增量按 T6-2 定档'),
        ('T3·(b) 按钮文案已改',           zh(BTN_REPL),                                        1, '==', ''),
        ('T3·(c) disabled 已改',          zh(DIS_REPL),                                        1, '==', ''),
        ('T3·调用点共 4 处',              'YlxwGiftCost(j&&j.favorability)',                   4, '==', 'a×2 + c×1 + b×1'),
        # ---- 旧值清零（防漏改）----
        ('T3·旧 R=100 已清零',            'const R=100,E=5',                                   0, '==', ''),
        ('T3·旧阈值 100 已清零',          'spiritStones<100',                                  0, '==', ''),
        ('T3·旧按钮文案已清零',           '赠灵石 (100)',                                      0, '==', ''),
        # ---- 基线未被破坏 ----
        ('基线·好感增量 E=5 已清零',      ',E=5;',                                             0, '==', '0.8.7 T6-2 定档 → ,E=2;'),
        ('基线·好感增量 E=2 已生效',      ',E=2;',                                             1, '==', '0.8.7 T6-2 定档'),
        ('基线·好感 clamp 未动',          'favorability:Math.min(100,Math.max(-100,_.favorability+E))', 1, '==', ''),
        ('基线·物品赠送回调未动',         'favorability:Math.min(100,Math.max(-100,I.favorability+N))', 1, '==', ''),
        ('基线·人物志模态框仍在',         'title:"人物志"',                                    2, '==', 'Nk + 入口各 1'),
        ('基线·人物志组件 Nk 仍在',       'const Nk=({isOpen:t,onClose:r,player:a,setPlayer:l,addLog:c})', 1, '==', ''),
        ('基线·YlxwNum 未被破坏',         INJECT_ANCHOR,                                       1, '==', ''),
        ('基线·档位函数 Yg 仍在',         'function Yg(t){return t>=80?',                      1, '==', ''),
    ]
    return gates
