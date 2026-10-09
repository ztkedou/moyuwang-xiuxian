# -*- coding: utf-8 -*-
r"""
yl_econ2_ext.py — R-025 / R-022 / R-024 / R-017 / R-028 客户端数值统一（econ2 环）

事实源：`策划_数值统一案_v2.md`（424 行，2026-09-30）。旧版 `策划_数值统一案.md`
的 R-022/024/025/028 结论已作废（前提被用户推翻），本模块**只按 v2 落数**。

用户拍板口径（team-lead 转述，严格执行）
--------------------------------------------------------------------------
  R-025  修炼效率：6 桶「相乘」→「相加」+ 各来源大幅下调，**不设任何总帽**。
         total = r*d + a*0.26 + l*0.60 + c*0.60 + min(b,0.10) + S*0.32
         （心法 1.00 / 天赋 0.26 / 称号 0.60 / 洞府 0.60 / 共鸣 1.00 上限 0.10 / 羁绊 0.32）
         uid13：+2067.55% → +199.66%（满共鸣 +209.66%）
  R-022  打坐**间隔 ×2**（1s→2s，自动 + 手动）；每跳收益**不变**（服务端 medEach 一行不动）；
         顿悟 1% → **0.2%**。回血随降频变慢 —— 用户选 A「接受，不补偿」。
  R-024  每跳灵石 ×5 → **×4.25 + 境界内因子** `floor(max(1,q)*4.25*(1+(realmLevel-1)*0.03))`。
         目标：炼气 L1 = 10,107 灵石/h。
  R-017  灵宠亲密度 ÷2.33（= 设计案 E3.5→E1.5）；193 次批量喂血 ≈ 289.5 → 290 点。
  R-028  周里程碑 3 档 → 5 档（500/1000/1500/1900/2310），灵石总额 125k → 160k/周。
         传承石 `MILE_MONTHLY_TIER` **保持「月」不动**（不改为周）⇒ 传承石仍挂 1000 档按月限领。

侦察（构建产物 index-v2811-20260930.js 逐字实测，count 已核）
--------------------------------------------------------------------------
  · R-025 效率聚合：`function bd(t){` @564122；尾段
      `return{total:(1+r*d)*(1+a)*(1+l)*(1+c)*(1+b)*(1+S)-1,art:r,talent:a,title:l,`
      `grotto:c,synergy:b,npc:S,spiritualRootBonus:d}}` —— **count==1**。
    调用点 4 处（handleMeditate @682810 / @763133 / @820571 / @1511256），
    一律读 `total` 且按 `1+total` 乘修为 ⇒ 语义（total 为「加成小数」）不变。
  · R-022 自动打坐冷却：`_.current(1)` @572108（在 `setInterval(...,200)` 内）—— count==1。
    手动打坐：`updateQuestProgress("meditate",1),M(1)` @1791851 —— count==1。
    顿悟：`Math.random()<.01` @682873 —— count==1。
  · R-024 每跳灵石：`Math.max(1,q)*5` 实测 **3 处**（设计案写 2 处，已被 medlog 追加第 3 处）：
      ㈠ 入账 `w=$.spiritStones+Math.max(1,q)*5`
      ㈡ medlog 日志参数 `__ylms=YlxwMedStone(Math.max(1,q)*5)`
      ㈢ toast `YlxwToast(\`💰 打坐时获得了 ${Math.max(1,q)*5} 灵石\`,...)`
    三处必须同改（否则「到账 ≠ 日志 ≠ 提示」）。
  · R-017 灵宠喂养（handleFeed 单次 / handleBatchFeedHp 批量）：
      `let A=300;`（单次修为基数）/ `let B=300;`（批量修为基数）—— 各 count==1
      `Math.floor(2+Math.random()*4)` —— count==2（单次 Z / 批量 I）
      `if(k==="hp")P=Math.max(0,w.hp-200);` / `const ne=Math.max(1,Math.floor(w.exp*.05))`
      `const C=200,g=k||Math.floor(d.hp/C);`（批量每次气血）—— 各 count==1
  · R-028 客户端周里程碑表：`var YlxwQMile = [` @870700（yl_t9quest_ext 注入块内，
    为 zh() 转义形态）—— 表头 count==1；t9quest 门禁只断言表头，**不断言档位内容**。

★ 与已有模块的锚区冲突（已在 报告_econ2.md §6 逐条列明，需 lead 处理）
--------------------------------------------------------------------------
  本环按设计案落在「就地改公式」的位置，以下冻结串会因此**在最终文本上不再逐字成立**：
    · yl_medlog_ext.py:196 `跨模块·打坐灵石表达式未动`  `w=$.spiritStones+Math.max(1,q)*5`
    · yl_medlog_ext.py:192 `R23·灵石累加项已挂`        `...,__ylms=YlxwMedStone(...),`
    · yl_medlog_ext.py:200 `基线·打坐 tick 未动`        `...N.current(),_.current(1)}catch...`
    · yl_eco085_ext.py:368  `基线·打坐灵石未动`         `w=$.spiritStones+Math.max(1,q)*5`
    · yl_reward089_ext.py:139 `BASE_MEDITATE`          `w=$.spiritStones+Math.max(1,q)*5`
    · yl_toast083_ext.py:362 `基线·灵石文案未动`        `打坐时获得了 ${Math.max(1,q)*5} 灵石`
    · yl_flow083_ext.py:256 `F5·打坐 cooldown 未动`      `M(1)`
  ⇒ 依 dungeon085「约束权移交」先例，需 lead 把这 7 条改为注释/放宽（详见报告 §6）。
  本模块**不改任何已存在的 yl_*_ext.py**。

硬约束
--------------------------------------------------------------------------
  · 注入块 zh() 后纯 ASCII；不含 V28_BAN_PATTERNS（iframe/postMessage/XMLHttpRequest/
    auth_token/X-YL-）；注入块内无 fetch。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 build_v26n.py、不写 build/assets/、不改 srv/index_v28.ts。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-0.8.13 econ2: R-025/022/024 数值统一（客户端） =====
   R-025 修炼效率：6 桶「相乘」→「相加」+ 各来源降幅系数 K（**不设总帽**）。
     total = r*d + a*0.26 + l*0.60 + c*0.60 + min(b,0.10) + S*0.32
     K = { 心法 1.00 / 天赋 0.26 / 称号 0.60 / 洞府 0.60 / 共鸣 1.00（上限 0.10）/ 羁绊 0.32 }
     ★ 新增任何效率来源（新天赋 / 新羁绊 / 新洞府建筑 / 新图鉴）必须经过对应 K 或重新评估。
   R-022 打坐降频：冷却 1s→2s（自动 + 手动）、顿悟 1%→0.2%；**每跳收益不变**（服务端每跳基数一行不动）。
   R-024 打坐灵石：每跳 ×5 → ×4.25 + 境界内因子 (1+(realmLevel-1)*0.03)，必须 floor。
   纯数值：不新增网络调用、不改存档结构。 */
var YLXW_ECON2_K = { art: 1.00, talent: 0.26, title: 0.60, grotto: 0.60, synergy: 1.00, bond: 0.32 };
var YLXW_ECON2_SYN_CAP = 0.10;
/* R-024 每跳灵石 = floor(max(1,q) × 4.25 × (1 + (境界层-1) × 0.03))
   —— 与 bd() 内联的 K 表同源（灵石不受效率 K 影响）。 */
function YlxwMedStone2(q, realmLevel) {
  var lv = Math.max(1, Math.floor(Number(realmLevel) || 1));
  return Math.floor(Math.max(1, Number(q) || 1) * 4.25 * (1 + (lv - 1) * 0.03));
}
'''

# --------------------------------------------------------------------------- 锚点常量

# 注入锚：顶层函数（此刻 YlxwNum/Be/fe/gd 等均已定义；函数声明提升，位置无关）
INJECT_ANCHOR = 'function YlxwPanelModal(p) {'

# R-025 · bd() 上方注释锚
BD_ANCHOR = 'function bd(t){'

# R-025 · 效率聚合尾段（6 桶相乘 → 相加 × K）
BD_OLD = 'return{total:(1+r*d)*(1+a)*(1+l)*(1+c)*(1+b)*(1+S)-1,art:r,talent:a,title:l,grotto:c,synergy:b,npc:S,spiritualRootBonus:d}}'
BD_NEW = 'return{total:r*d+a*0.26+l*0.6+c*0.6+Math.min(b,0.1)+S*0.32,art:r,talent:a,title:l,grotto:c,synergy:b,npc:S,spiritualRootBonus:d}}'

# R-022 · 自动打坐冷却 1s→2s
CD_AUTO_OLD = '_.current(1)'
CD_AUTO_NEW = '_.current(2)'

# R-022 · 手动打坐冷却 1s→2s
CD_MAN_OLD = 'updateQuestProgress("meditate",1),M(1)'
CD_MAN_NEW = 'updateQuestProgress("meditate",1),M(2)'

# R-022 · 顿悟 1% → 0.2%
INSIGHT_OLD = 'Math.random()<.01'
INSIGHT_NEW = 'Math.random()<.002'

# R-024 · 每跳灵石（入账 + medlog 日志参数 一次改完，且新增 __ylsq 复用）
STONE_OLD = ('q=Math.max(1,C*2+1)+Math.floor(Math.random()*3)-1,'
             'w=$.spiritStones+Math.max(1,q)*5,'
             '__ylms=YlxwMedStone(Math.max(1,q)*5),')
STONE_NEW = ('q=Math.max(1,C*2+1)+Math.floor(Math.random()*3)-1,'
             '__ylsq=YlxwMedStone2(q,$.realmLevel),'
             'w=$.spiritStones+__ylsq,'
             '__ylms=YlxwMedStone(__ylsq),')

# R-024 · 每跳灵石 toast（与到账同步，否则提示与到账不一致）
TOAST_OLD = 'YlxwToast(`\U0001f4b0 打坐时获得了 ${Math.max(1,q)*5} 灵石`,"gain","md-stone",2400)'
TOAST_NEW = 'YlxwToast(`\U0001f4b0 打坐时获得了 ${__ylsq} 灵石`,"gain","md-stone",2400)'

# R-017 · 单次喂养修为基数 300 → 100
FEED_A_OLD = 'let A=300;'
FEED_A_NEW = 'let A=100;'

# R-017 · 批量喂养修为基数 300 → 100
FEED_B_OLD = 'let B=300;'
FEED_B_NEW = 'let B=100;'

# R-017 · 单次亲密 E3.5 → E1.5（floor(2+rand*4) → floor(1+rand*2)）
INTIM1_OLD = 'const Z=Math.floor(2+Math.random()*4),te=w.pets.map('
INTIM1_NEW = 'const Z=Math.floor(1+Math.random()*2),te=w.pets.map('

# R-017 · 批量亲密 E3.5 → E1.5
INTIM2_OLD = 'I+=Math.floor(2+Math.random()*4)}'
INTIM2_NEW = 'I+=Math.floor(1+Math.random()*2)}'

# R-017 · 单次喂血消耗 200 → 1000
HPCOST_OLD = 'if(k==="hp")P=Math.max(0,w.hp-200);'
HPCOST_NEW = 'if(k==="hp")P=Math.max(0,w.hp-1000);'

# R-017 · 修为喂养消耗 5% → 25%
EXPCOST_OLD = 'const ne=Math.max(1,Math.floor(w.exp*.05));V=Math.max(0,w.exp-ne)'
EXPCOST_NEW = 'const ne=Math.max(1,Math.floor(w.exp*.25));V=Math.max(0,w.exp-ne)'

# R-017 · 批量喂血每次气血 200 → 1000
BATCHC_OLD = 'const C=200,g=k||Math.floor(d.hp/C);'
BATCHC_NEW = 'const C=1000,g=k||Math.floor(d.hp/C);'

# R-028 · 客户端周里程碑 3 档 → 5 档（zh() 转义形态，与注入块同风格）
MILE_OLD = (
    'var YlxwQMile = [\n'
    '  { tier: 500,  name: "\\u52e4\\u4fee\\u00b7\\u521d", base: 20000, ticket: 8,  extra: "" },\n'
    '  { tier: 1000, name: "\\u52e4\\u4fee\\u00b7\\u4e2d", base: 45000, ticket: 15, extra: "\\u4f20\\u627f\\u77f3 \\u00d71" },\n'
    '  { tier: 1800, name: "\\u52e4\\u4fee\\u00b7\\u6ee1", base: 60000, ticket: 30, extra: "\\u4ed9\\u54c1\\u73cd\\u5b9d \\u00d71 \\u00b7 \\u79f0\\u53f7\\u300c\\u52e4\\u4fee\\u4e0d\\u8f8d\\u300d" }\n'
    '];'
)
MILE_NEW = (
    'var YlxwQMile = [\n'
    '  { tier: 500,  name: "\\u52e4\\u4fee\\u00b7\\u521d", base: 10000, ticket: 4,  extra: "" },\n'
    '  { tier: 1000, name: "\\u52e4\\u4fee\\u00b7\\u4e2d", base: 20000, ticket: 9,  extra: "\\u4f20\\u627f\\u77f3 \\u00d71" },\n'
    '  { tier: 1500, name: "\\u52e4\\u4fee\\u00b7\\u8fdb", base: 30000, ticket: 14, extra: "" },\n'
    '  { tier: 1900, name: "\\u52e4\\u4fee\\u00b7\\u6df1", base: 40000, ticket: 21, extra: "" },\n'
    '  { tier: 2310, name: "\\u52e4\\u4fee\\u00b7\\u6ee1", base: 60000, ticket: 30, extra: "\\u4ed9\\u54c1\\u73cd\\u5b9d \\u00d71 \\u00b7 \\u79f0\\u53f7\\u300c\\u52e4\\u4fee\\u4e0d\\u8f8d\\u300d" }\n'
    '];'
)

EDITS = [
    ('R025 bd 效率聚合改相加×K', BD_OLD, BD_NEW, 1),
    ('R022 自动冷却 1s→2s',      CD_AUTO_OLD, CD_AUTO_NEW, 1),
    ('R022 手动冷却 1s→2s',      CD_MAN_OLD, CD_MAN_NEW, 1),
    ('R022 顿悟 1%→0.2%',        INSIGHT_OLD, INSIGHT_NEW, 1),
    ('R024 每跳灵石 ×4.25+境界内因子', STONE_OLD, STONE_NEW, 1),
    ('R024 灵石 toast 同步',      TOAST_OLD, TOAST_NEW, 1),
    ('R017 单次喂养修为基数 300→100', FEED_A_OLD, FEED_A_NEW, 1),
    ('R017 批量喂养修为基数 300→100', FEED_B_OLD, FEED_B_NEW, 1),
    ('R017 单次亲密 E3.5→E1.5',   INTIM1_OLD, INTIM1_NEW, 1),
    ('R017 批量亲密 E3.5→E1.5',   INTIM2_OLD, INTIM2_NEW, 1),
    ('R017 单次喂血消耗 200→1000', HPCOST_OLD, HPCOST_NEW, 1),
    ('R017 修为喂养消耗 5%→25%',  EXPCOST_OLD, EXPCOST_NEW, 1),
    ('R017 批量喂血每次气血 200→1000', BATCHC_OLD, BATCHC_NEW, 1),
    ('R028 客户端周里程碑 3→5 档', MILE_OLD, MILE_NEW, 1),
]


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 t9quest/medlog/eco085 等）；ctx = {'zh': zh, ...}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('econ2 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) R-025 说明注释（直接落在 bd() 上方，法 (b) 强制要求）
    k_note = zh(
        '/* \u2605 R-025\uff08econ2\uff09\uff1a\u4fee\u70bc\u6548\u7387 6 \u6876\u5df2\u7531'
        '\u300c\u76f8\u4e58\u300d\u6539\u4e3a\u300c\u76f8\u52a0\u300d+ \u964d\u5e45\u7cfb\u6570 K\u3002'
        'total = r*d + a*0.26 + l*0.60 + c*0.60 + min(b,0.10) + S*0.32\u3002'
        'K = \u5fc3\u6cd5 1.00 / \u5929\u8d4b 0.26 / \u79f0\u53f7 0.60 / \u6d1e\u5e9c 0.60 / '
        '\u5171\u9e23 1.00\uff08\u4e0a\u9650 0.10\uff09/ \u7f81\u7eca 0.32\u3002'
        '\u2605 \u65b0\u589e\u4efb\u4f55\u6548\u7387\u6765\u6e90\uff08\u65b0\u5929\u8d4b / \u65b0\u7f81\u7eca / '
        '\u65b0\u6d1e\u5e9c\u5efa\u7b51 / \u65b0\u56fe\u9274\uff09\u5fc5\u987b\u7ecf\u8fc7\u5bf9\u5e94 K '
        '\u6216\u91cd\u65b0\u8bc4\u4f30\u3002\u9884\u8b66\u7ebf\uff1atotal \u903c\u8fd1 +350% '
        '\u65f6\u542f\u7528\u8f6f\u4e0a\u9650\u3002 */\n'
    )
    p.replace('econ2-k-note', BD_ANCHOR, k_note + BD_ANCHOR, expect=1,
              note='R-025 降幅系数 K 说明注释（bd() 上方）')

    # 1) 模块级工具函数（YlxwMedStone2）
    p.insert_before('econ2-helpers', INJECT_ANCHOR, blk + '\n',
                    expect=1, note='注入 YlxwMedStone2（R-024 每跳灵石）')

    # 2) 就地替换
    for name, old, new, exp in EDITS:
        p.replace(name, old, new, expect=exp)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 注入块 =================
        # ★ 2026-09-30 约束权移交（`yl_r024_ext.py` 接在本模块之后）：
        #   R-024 的每跳灵石函数被 r024 环改成**三参 + 大境界因子**
        #   （因子 = 1 + realmIndex*K + (层-1)*0.03，K=0.083；炼气 L1 仍 ×1.00）
        #   ⇒ 下面 2 条断言改用「最终形态」，语义不变（仍是「函数在、×4.25 在」）。
        ('R24·每跳灵石函数已注入',   'function YlxwMedStone2(q, realmLevel, realmIndex) {', 1, '==', 'r024 环已升三参'),
        ('R24·灵石公式 ×4.25',       'Math.floor(Math.max(1, Number(q) || 1) * 4.25 * (1 + ri * YLXW_R024_K + (lv - 1) * 0.03))', 1, '==', 'r024 环已加 realmIndex 因子'),
        ('R25·K 表已登记',           'var YLXW_ECON2_K = { art: 1.00, talent: 0.26, title: 0.60, grotto: 0.60, synergy: 1.00, bond: 0.32 };', 1, '==', ''),
        ('R25·共鸣上限常量',         'var YLXW_ECON2_SYN_CAP = 0.10;', 1, '==', ''),
        ('R25·K 说明注释已挂 bd 上方', r'\u2605 R-025\uff08econ2\uff09\uff1a\u4fee\u70bc\u6548\u7387 6 \u6876', 1, '==', '法(b)强制要求'),
        # ================= R-025 效率聚合 =================
        ('R25·效率改为相加×K',       'return{total:_ar+_ta+_ti+_gr+_sy+_np,', 1, '==', ''),
        ('R25·6 桶相乘公式已清零',   'return{total:(1+r*d)*(1+a)*(1+l)*(1+c)*(1+b)*(1+S)-1,', 0, '==', '旧式必须彻底消失'),
        ('R25·心法 K=1.00 直乘',     'const _ar=r*d,', 1, '==', ''),
        ('R25·天赋 K=0.26',          '_ta=a*0.26,', 1, '==', '降最多'),
        ('R25·称号/洞府 K=0.60',     '_ti=l*0.6,_gr=c*0.6,', 1, '==', ''),
        ('R25·羁绊 K=0.32',          '_np=S*0.32;', 1, '==', ''),
        ('R25·无总帽（无 softcap）', 'total<=3?3+', 0, '==', '用户选 A 不设总帽'),
        # ================= R-022 打坐降频 =================
        ('R22·自动冷却改 2s',        '_.current(2)', 1, '==', ''),
        ('R22·旧自动冷却已清零',     '_.current(1)', 0, '==', ''),
        ('R22·手动冷却改 2s',        'updateQuestProgress("meditate",1),M(2)', 1, '==', ''),
        ('R22·旧手动冷却已清零',     'updateQuestProgress("meditate",1),M(1)', 0, '==', ''),
        ('R22·顿悟改 0.4%',          'Math.random()<.004', 1, '==', '0.9.8 adv097(R-090) 有意上调 0.2%→0.4%（R-041 回滚到 0.2% 后由 adv097 再提；本模块仍只负责 .01→.002）'),
        ('R22·旧顿悟 1% 已清零',     'Math.random()<.01;', 0, '==', '带分号精确匹配，防命中 .015 前缀'),
        ('R22·每跳修为公式未动',     'S=Math.floor(v*(.85+Math.random()*.3))', 1, '==', '每跳收益不变'),
        # ================= R-024 每跳灵石 =================
        ('R24·入账与日志同改',       '__ylsq=YlxwMedStone2(q,$.realmLevel,C),w=$.spiritStones+__ylsq,__ylms=YlxwMedStone(__ylsq),', 1, '==', 'r024 环已补传 realmIndex=C'),
        ('R24·toast 与到账同步',     'YlxwToast(`\U0001f4b0 \u6253\u5750\u65f6\u83b7\u5f97\u4e86 ${__ylsq} \u7075\u77f3`,"gain","md-stone",2400)', 1, '==', ''),
        ('R24·旧 ×5 灵石公式已清零', 'Math.max(1,q)*5', 0, '==', '入账/日志/toast 三处全改'),
        ('R24·旧 toast 文案已清零',  '${Math.max(1,q)*5} \u7075\u77f3', 0, '==', ''),
        # ================= R-017 灵宠喂养 =================
        ('R17·单次喂养基数 100',     'let A=100;', 1, '==', '原 300'),
        ('R17·批量喂养基数 100',     'let B=100;', 1, '==', '原 300'),
        ('R17·旧基数 300 已清零',    'let A=300;', 0, '==', ''),
        ('R17·旧批量基数 300 已清零', 'let B=300;', 0, '==', ''),
        ('R17·亲密 E1.5（两处）',    'Math.floor(1+Math.random()*2)', 2, '==', '单次 Z + 批量 I'),
        ('R17·旧亲密 E3.5 已清零',   'Math.floor(2+Math.random()*4)', 0, '==', ''),
        ('R17·单次喂血消耗 1000',    'if(k==="hp")P=Math.max(0,w.hp-1000);', 1, '==', ''),
        ('R17·修为喂养消耗 25%',     'const ne=Math.max(1,Math.floor(w.exp*.25));V=Math.max(0,w.exp-ne)', 1, '==', ''),
        ('R17·批量每次气血 1000',    'const C=1000,g=k||Math.floor(d.hp/C);', 1, '==', ''),
        ('R17·旧批量气血 200 已清零', 'const C=200,g=k||Math.floor(d.hp/C);', 0, '==', ''),
        # ================= R-028 客户端周里程碑 =================
        ('R28·周里程碑表仍唯一',     'var YlxwQMile = [', 1, '==', 't9quest 门禁串保留'),
        ('R28·新 5 档·500',          'tier: 500,  name: "\\u52e4\\u4fee\\u00b7\\u521d", base: 10000, ticket: 4,  extra: ""', 1, '==', ''),
        # ★ 2026-09-30 约束权移交（r013c）：以下 3 条的 extra 列语义已由 r013c（yl_r013c_ext.py）
        #   接管（传承石移 2310 / 仙品珍宝下移 1900 / 1000 清空）⇒ 本环只锁「档位数值前缀」，
        #   extra 值改由 r013c 正向断言（同 dungeon085:261 / eco085:368 先例）。
        ('R28·新 5 档·1000',         'tier: 1000, name: "\\u52e4\\u4fee\\u00b7\\u4e2d", base: 20000, ticket: 9, ', 1, '==', 'extra 列由 r013c 接管'),
        ('R28·新 5 档·1500',         'tier: 1500, name: "\\u52e4\\u4fee\\u00b7\\u8fdb", base: 30000, ticket: 14, extra: ""', 1, '==', ''),
        ('R28·新 5 档·1900',         'tier: 1900, name: "\\u52e4\\u4fee\\u00b7\\u6df1", base: 40000, ticket: 21, ', 1, '==', 'extra 列由 r013c 接管'),
        ('R28·新 5 档·2310(满)',     'tier: 2310, name: "\\u52e4\\u4fee\\u00b7\\u6ee1", base: 60000, ticket: 30, ', 1, '==', 'extra 列由 r013c 接管'),
        ('R28·旧 1800 档已清零',     'tier: 1800,', 0, '==', '1800 → 2310'),
        ('R28·旧 base 20000/45000 已清零', 'base: 20000, ticket: 8,', 0, '==', ''),
        ('R28·周满分 2310 未动',     'var YlxwQWeekMax = 2310;', 1, '==', ''),
        # ================= 冻结：不得回踩其它系统 =================
        ('冻结·打坐修为基座未动',    'Math.floor(f*10*(1+a.realmLevel*.15))', 1, '==', 'R-022 每跳收益不变'),
        ('冻结·服务端字段未入客户端', 'medEach', 0, '==', '客户端无服务端每跳基数串'),
        ('冻结·效率面板读数未动',    '(c.total*100).toFixed(1)', 1, '==', 'UI 只显示 total，无 mismatch'),
        ('冻结·bd 定义唯一',         'function bd(t){', 1, '==', ''),
        ('冻结·自动打坐 interval 未动', '},200);return()=>{clearInterval(U)', 1, '==', '仅改冷却值，不动 tick 粒度'),
        ('R·注入块内无网络调用',     'fetch(', 0, '==', '纯客户端',
         ('/* ===== yl-0.8.13 econ2:', 'function YlxwPanelModal(p) {')),
    ]
    return gates
