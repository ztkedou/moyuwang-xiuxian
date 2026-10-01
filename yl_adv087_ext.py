# -*- coding: utf-8 -*-
r"""
yl_adv087_ext.py — 0.8.7 批次 · T11 历练修复（模块 adv087，纯客户端零服务端改动）

=========================================================================== 一句话
0.8.5 灵石放缓的三处审计漏网，一次修完（《数值表-T11历练》定档）：
  ① 战斗奖励隐藏 ×5 归 1（两处结算点；By 公式本体不动）
  ② 抽奖第三份过滤器 _ylk：90% 漏网 → 100% 折算 + 天价折算额(8e4/3e4/8e3) → T2 查表
  ③ 生成侧境界门 YLRealmOk 字段失配（WN 掉落池装备只有 realm 字段 ⇒ 恒放行）→ 补 realm fallback

=========================================================================== 证据（0.8.6 定版产物实测，2026-09-29，implDrops）
产物 _chainstage/dryrun.bundle.js（md5 3938a4ee7850e033b8a08e1dfda1c52d = 线上逐位）：
  - `Q=_?I*5:` @680040 战斗结算点①（{exp:A,stones:I}=By(...) 后）——0.8.5 ÷5 从未覆盖战斗线
  - `T=d?S*5:` @681740 战斗结算点②（Hc 回放快进路径，同款同改，铁律⑤同逻辑两份）
  - `function YLRealmOk(` @602859 注入块（带换行缩进）；读 realmRequirement→minRealm，
    而 WN() 掉落池装备只有 `realm` 字段 ⇒ 两字段全 undefined ⇒ 恒放行（v26l 设计失效）
  - `Math.random()<.9){const _ylk=...8e4/3e4/8e3...*YLRF(g)/3` @1449983 抽奖 draw 物品分支：
    10% 放行真装备 + 炼气抽到长生 = 35,555 灵石/件（lottery 单次期望 19,619~66,396）
  - 份数底账（铁律④/⑤，grep -o|wc -l 语义实测）：守卫串恒 2、`(_q>=6?160:...)` 恒 2、
    `Q=_?I*5:` 1、`T=d?S*5:` 1、Hc Boss `*5` 两处各恒 1、`const _ylm=/^[` 全产物 2、
    裸 `.exec(x.name` 3（其中 2 处是 _ylfb/_ylf 的 _m 解析，禁碰）

=========================================================================== 改动清单（6 处替换，零新增注入块）
  A  `Q=_?I*5:`            → `Q=_?I:`    （expect=1）
  B  `T=d?S*5:`            → `T=d?S:`    （expect=1）
  C  YLRealmOk 内 `r=q.minRealm;` 行前插 `r=q.realm;` fallback（expect=1，带同款缩进）
     语义：商店物品先吃 realmRequirement（不变）→ WN 掉落池装备吃 realm（恢复 v26l：
     +1 阶 18% / +2 阶 1.5% / ≥+3 阶恒 0）→ 兜底 minRealm
  D  `_ylk` 守卫行：`&&Math.random()<.9` 删除（100% 折算）+ 折算额 → `YlxwCvtStones(U,_ylq)`
  E  抽奖份正则 `const _ylm=/^\[(.+?)\]/.exec(U.name||"");` → `\[([^\[\]]+)\]`（与 _ylf/_ylfb 对齐）

=========================================================================== 明示不动（门禁恒值断言，防实现批误伤）
  - `spiritChange:Hn.victoryReward.spiritStones*5` / `spiritChange:h.rewards.spiritStones*5`
    （Hc 内宗门挑战夺宗 / 合道天地之魄试炼，一次性 Boss 奖励）恒各 1
  - `const _ylm=/^\[(.+?)\]/.exec(x.name`（@713253 穿戴门 _ylrn）恒 1；全产物 `const _ylm=/^[`
    基线 2 → 改后剩 1，**不归零**（v2 评审修订口径）
  - `_ylrn` 穿戴门 / `_eqp` / cy 秘境直调 / 商店 minRealm / `vs()` 入包口：零改动
  - `By` 公式本体（v 表 / *10 尾数 / b）零改动（动它会波及战败惩罚基数与快进路径）
  - 0.8.5 既定事件线（Ym ÷5、YLXW_STONE_MUL_ADV=0.2）/ 秘境 / 宗门任务：零改动

=========================================================================== 依赖与装配序（硬约束）
  - D 用 `YlxwCvtStones`（定义由 T2 的 eco 模块注入，恰 1 份）⇒ 装配序必须 **eco → adv087**
    （V28_MODULES 中 adv087 落在 eco 之后、numbal 之前；接线归 implEventsUi）。
  - 与 implRenwu(T6) 的锚点边界（0.8.7-build-plan §5.1 底账）：T6 结交产生点 ×7 归 T6；
    本模块六锚（结算×2 / YLRealmOk / _ylk 行 / U.name 正则）与 T6 概率字面量无文本重叠。

=========================================================================== 门禁计数清单（供接线人落 dryrun_087；adv087 装配态，grep -o|wc -l 语义）
  - `Q=_?I*5:`                                    1 → 0
  - `Q=_?I:`                                      0 → 1
  - `T=d?S*5:`                                    1 → 0
  - `T=d?S:`                                      0 → 1
  - `if(r===void 0||r===null||r==='')r=q.realm;`  0 → 1
  - `if(r===void 0||r===null||r==='')r=q.minRealm;` 恒 1
  - `Math.random()<.9){const _ylk=`               1 → 0
  - `const _ylk=YlxwCvtStones(U,_ylq)`            0 → 1
  - `(_ylq>=6?8e4:_ylq>=4?3e4:8e3)`               1 → 0
  - `const _ylm=/^\[(.+?)\]/.exec(U.name`         1 → 0
  - `const _ylm=/\[([^\[\]]+)\]/.exec(U.name`     0 → 1
  - `const _ylm=/^\[`                             2 → 1（不归零；剩 1 = 穿戴门）
  - `const _ylm=/^\[(.+?)\]/.exec(x.name`         恒 1（穿戴门，禁改）
  - `spiritChange:Hn.victoryReward.spiritStones*5` 恒 1（Boss，禁改）
  - `spiritChange:h.rewards.spiritStones*5`        恒 1（Boss，禁改）
  - `function YLRealmOk(`                          恒 1
  - `function YlxwCvtStones(`                      恒 1（T2 依赖，装配序守卫）
  - `YlxwCvtStones(x,_q)`                          恒 2（T2 两份调用，不被本模块波及）
  - 数值预期（tools/_t11_calc.py 复算）：单次历练期望 炼气L1 906→99、筑基L5 2670→434、
    金丹L5 4087→688、长生L9 22531→8793；每券折算期望 ≤52（旧 3,567~12,072）。

=========================================================================== 技术约束遵守
· 纯 ASCII 模块（无中文注入；本文件注释可中文，落产物字节全部 ASCII）。
· 不含禁用模式：iframe / postMessage / XMLHttpRequest / auth_token / X-YL-。
· 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
· 本模块不改任何其他文件；锚区与 T2(eco)/T6(t6chardex) 零重叠。
"""

# --------------------------------------------------------------------------- 锚点（0.8.6 产物逐字，2026-09-29 实测 count）

# —— (A) 战斗结算点① 隐藏 ×5 归 1 ——
SETTLE1_ANCHOR = 'Q=_?I*5:'
SETTLE1_REPL = 'Q=_?I:'

# —— (B) 战斗结算点②（回放快进）同款 ——
SETTLE2_ANCHOR = 'T=d?S*5:'
SETTLE2_REPL = 'T=d?S:'

# —— (C) YLRealmOk 生成侧境界门：realm fallback（修 WN 掉落池字段失配）——
# 定义块是带缩进的注入代码形态；插入行保持 4 空格缩进。
RLM_ANCHOR = "if(r===void 0||r===null||r==='')r=q.minRealm;"
RLM_REPL = ("if(r===void 0||r===null||r==='')r=q.realm;\n    "
            "if(r===void 0||r===null||r==='')r=q.minRealm;")

# —— (D) _ylk 抽奖第三份过滤器：90% 漏网 → 100% 折算 + T2 查表 ——
YLK_ANCHOR = ('if(_ylr&&_ylpi>=0&&_ylq>_ylpi&&Math.random()<.9){'
              'const _ylk=Math.floor((_ylq>=6?8e4:_ylq>=4?3e4:8e3)*YLRF(g)/3);w+=_ylk,')
YLK_REPL = ('if(_ylr&&_ylpi>=0&&_ylq>_ylpi){'
            'const _ylk=YlxwCvtStones(U,_ylq);w+=_ylk,')

# —— (E) 抽奖份解析正则对齐（串首锚定 → 名内第一对方括号，与 _ylf/_ylfb 同口径）——
YLKM_ANCHOR = 'const _ylm=/^\\[(.+?)\\]/.exec(U.name||"");'
YLKM_REPL = 'const _ylm=/\\[([^\\[\\]]+)\\]/.exec(U.name||"");'

# —— 明示不动断言用锚 ——
BOSS1_ANCHOR = 'spiritChange:Hn.victoryReward.spiritStones*5'
BOSS2_ANCHOR = 'spiritChange:h.rewards.spiritStones*5'
WEAR_GATE_ANCHOR = 'const _ylm=/^\\[(.+?)\\]/.exec(x.name'
CVT_DEF_ANCHOR = 'function YlxwCvtStones('
CVT_T2_CALL_ANCHOR = 'YlxwCvtStones(x,_q)'
YLREALM_DEF_ANCHOR = 'function YLRealmOk('


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置模块，含 eco=T2 的 YlxwCvtStones 注入）；
    ctx = {'zh': zh, 'base_text': str}（本模块无注入块，不消费 ctx）"""

    # (A)(B) 战斗奖励隐藏 ×5 归 1（By 公式本体零改动）
    p.replace('adv087-settle1', SETTLE1_ANCHOR, SETTLE1_REPL, expect=1,
              note='战斗结算点① Q=_?I*5 -> Q=_?I（0.8.5 漏网主泄漏）')
    p.replace('adv087-settle2', SETTLE2_ANCHOR, SETTLE2_REPL, expect=1,
              note='战斗结算点②（回放快进）T=d?S*5 -> T=d?S（同逻辑两份）')

    # (C) YLRealmOk：realmRequirement(原行为) -> realm(WN 掉落池) -> minRealm(兜底)
    p.replace('adv087-ylrealmok', RLM_ANCHOR, RLM_REPL, expect=1,
              note='生成侧境界门字段 fallback，恢复 +1阶18%/+2阶1.5%/>=+3阶0%')

    # (D) _ylk：100% 折算 + T2 表值（依赖 eco 注入的 YlxwCvtStones，装配序 eco -> adv087）
    p.replace('adv087-ylk', YLK_ANCHOR, YLK_REPL, expect=1,
              note='抽奖第三份过滤器 100% 折算；天价补偿 -> T2 查表(<=160)')

    # (E) 抽奖份正则对齐（穿戴门 _ylrn 的 x.name 形态不动）
    p.replace('adv087-ylkm', YLKM_ANCHOR, YLKM_REPL, expect=1,
              note='^\\[ -> \\[（与 _ylf/_ylfb 的 _m 同口径）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- (A)(B) 战斗乘子 ----
        ('T11·旧战斗乘子①已清零',   'Q=_?I*5:',                              0, '==', ''),
        ('T11·新战斗乘子①生效',     'Q=_?I:',                                1, '==', ''),
        ('T11·旧战斗乘子②已清零',   'T=d?S*5:',                              0, '==', ''),
        ('T11·新战斗乘子②生效',     'T=d?S:',                                1, '==', ''),
        ('T11·By 公式未动',        'M=Math.max(10,Math.round($*b))*10',      1, '==', '公式本体零改动'),
        # ---- Hc Boss 一次性 *5（明示不动，恒值）----
        ('T11·Boss*5 恒1(夺宗)',    BOSS1_ANCHOR,                            1, '==', '宗门挑战一次性奖励，禁改'),
        ('T11·Boss*5 恒1(合道试炼)', BOSS2_ANCHOR,                           1, '==', '天地之魄试炼一次性奖励，禁改'),
        # ---- (C) 生成侧境界门 ----
        ('T11·YLRealmOk 定义恒1',   YLREALM_DEF_ANCHOR,                      1, '==', ''),
        ('T11·realm fallback 生效', "if(r===void 0||r===null||r==='')r=q.realm;", 1, '==', ''),
        ('T11·minRealm 兜底保留',   RLM_ANCHOR,                              1, '==', '第三级兜底原样'),
        ('T11·realm 门概率未动',    'if(d===1)return Math.random()<0.18;',   1, '==', 'v26l +1阶18% 恢复生效'),
        ('T11·realm 门概率未动②',   'if(d===2)return Math.random()<0.015;',  1, '==', 'v26l +2阶1.5%'),
        # ---- (D)(E) _ylk ----
        ('T11·旧90%漏网已清零',     'Math.random()<.9){const _ylk=',          0, '==', ''),
        ('T11·新查表调用生效',      'const _ylk=YlxwCvtStones(U,_ylq)',       1, '==', ''),
        ('T11·旧天价折算档已清零',   '(_ylq>=6?8e4:_ylq>=4?3e4:8e3)',          0, '==', ''),
        ('T11·抽奖份正则已对齐',     'const _ylm=/\\[([^\\[\\]]+)\\]/.exec(U.name', 1, '==', ''),
        ('T11·旧抽奖份正则已清零',   'const _ylm=/^\\[(.+?)\\]/.exec(U.name',  0, '==', ''),
        # ---- 全产物 _ylm 正则底账（v2 评审修订口径：不归零）----
        # ★ 真实字节含反斜杠：正则是 /^\[/，文档简写「const _ylm=/^[」无反斜杠形态在产物 0 命中。
        ('T11·全产物串首_ylm剩1',   'const _ylm=/^\\[',                       1, '==', '真实字节 /^\\[；剩穿戴门 1 份，不归零'),
        ('T11·穿戴门正则恒1',       WEAR_GATE_ANCHOR,                        1, '==', '@713253 _ylrn，禁改'),
        ('T11·_ylfb/_ylf _m解析3',  '.exec(x.name',                           3, '==', '穿戴门1+_m解析2，全不动'),
        # ---- 依赖与共享面守卫（装配序 eco -> adv087）----
        ('T11·T2查表函数恰1',       CVT_DEF_ANCHOR,                           1, '==', '缺它=T2 未装配，序错'),
        ('T11·T2两份调用恒2',       CVT_T2_CALL_ANCHOR,                       2, '==', 'eco085 过滤器不被波及'),
        # ---- 基线未破坏（0.8.5/0.8.6 既定档）----
        ('T11·事件线乘子未动',      'var YLXW_STONE_MUL_ADV = 0.2;',          1, '==', '0.8.5 既定，P2 旋钮'),
        ('T11·守卫串恒2',           'if(!x||x.isAdvancedItem||!(x.isEquippable||x.equipmentSlot))return true;', 2, '==', '全员禁改'),
    ]
    return gates
