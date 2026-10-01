# -*- coding: utf-8 -*-
r"""
yl_050_ext.py — R-050 洞府：灵石加速一次半小时 + 每日催熟 10 次起步随洞府等级

需求原文（需求台账_待办.md:39）
--------------------------------------------------------------------------
  「自带的灵草种植，灵石加速变成一次半小时。每日催熟次数也增加到最简陋的
  10次起步，根据洞府等级相应增加。」

口径判定（本批代决，已写拍板：拍板/2026-10-01_*_R-050_*.md）
--------------------------------------------------------------------------
  游戏里有两个「催熟」：
    A. 洞府灵草园加速（plantedHerbs，客户端权威，无服务端）——UI 文案是
       「加速」「今日加速 N / 10」，上限 = Br.dailyLimit = 10 固定。
    B. 仙务灵田作物催熟（/farm/boost，服务端 farm_daily_care 强执法）——
       UI 文案正是「每日催熟 X 次」（洞府总览「灵田联动」行 + 升级 toast），
       值 = 服务端 farmBoostCap = 10 + 3*min(max(0,级-1),4) + 2*max(0,级-5)
       （R-050 改档前为 FARM_BOOST_BASE_CAP(3) + floor(洞府等级/2)）。
  判据：全 bundle「每日催熟」仅 B 的两处展示；简陋洞府原显示 3 次，
  「**增加到**最简陋的10次起步」只对 3→10 成立（A 已是 10，无「增加」可言）。
  ⇒ 「每日催熟次数」按 B 处理（改服务端常数 + 两处展示同步）；
    A 的加速上限已是 10 ≥ 10，不动（其文案措辞是「加速」非「催熟」）。

本模块动作（客户端 3 处）
--------------------------------------------------------------------------
  1. 灵石加速一次半小时：v2810c 把加速改成按品阶缩短（普通1/稀有2/传说4/
     仙品6 小时）。R-050 要求一次只缩半小时 ⇒ 在 v2810c 注入块内、
     YlxwHerbSpeedMs 定义行之后插一条**赋值覆盖**：
         YlxwHerbSpeedHours = function (h) { return .5; };
     ★ 为什么用赋值而不是同名函数声明：bundle 顶层是 ES module 作用域，
       重复函数声明 = SyntaxError（node v24 实证，整包白屏）；词法绑定
       可写 ⇒ 顶层赋值在求值期执行，晚于任何 UI 调用，安全（已实证）。
     ★ v2810c 被逐字钉死的字面串（品阶表 return 6/4/2、Ms 函数行、C 截断行、
       按钮预览、tooltip）一个字不动 ⇒ 上游门禁零破坏。
     计价不变：费用仍 = max(minCost, 实际缩短分钟 × costPerMinute)，
     q 累计 = 实际缩短量 ⇒ 整株催熟到成熟的总花费与改前完全一致，
     只是单次步长减半（30 分钟 × 100 = 3000 灵石/次，原 1~6h 一档）。
  2. 洞府总览「灵田联动」行：每日催熟 3+floor(级/2) → 10+3*min(max(0,级-1),4)+2*max(0,级-5)
     （逐级 +3 前 4 级 / +2 其后；L1=10 L2=13 … L5=22 … L10=32）。
  3. 升级成功 toast「灵田联动」行：同式 3+floor(级/2) → 同一梯度式（与服务端
     farmBoostCap = 10 + 3*min(max(0,级-1),4) + 2*max(0,级-5) 保持三处同式）。
     （farm087 灵田面板头部的「今日催熟 used/cap」直接吃服务端回执，自动跟随。）

服务端配套（另文件 srv_patch_050.py，不在本模块）
--------------------------------------------------------------------------
  FARM_BOOST_BASE_CAP 3→10 且 farmBoostCap 公式改「逐级 +3（前 4 级）/ +2（其后）」
  （t10_farm 定档口径：常数/纯函数集中可调、端点零改动）；
  /farm/boost 的 409 文案、boostDaily 回执全部自动跟随。
  接线：localtest/chain_build.py 的 SRV_CHAIN 链尾（第 35 环，现末环
  srv_patch_r039.py 之后）；无锚点交集，仅要求 t10_farm（第 7 环）在前。

接线（lead 执行，本模块不改 build_v26n.py）
--------------------------------------------------------------------------
  build_v26n.py：import 行 + V28_MODULES 追加 ('r050', v28_r050_apply)，
  位置在 ('r039', …) 之后、('numbal', …) 之前。
  ★ 硬依赖：必须排在 v2810c 之后（insert_after 锚 = v2810c 注入的
    YlxwHerbSpeedMs 定义行，v2810c 不跑则本环当场报错，符合 §18.15 链式姿势）。
  与同批 R-049（洞府灵草位扩充）无锚区交集；两者都若注入 function Yk(t){
  前插，属既有共享锚模式（grotto087/v2810c 同锚先例），互不影响。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 不改 build/assets/*.js、srv/index_v28.ts、build_v26n.py、localtest/、
    deploy_v28/、yl_version_ext.py、CHANGELOG.md 与任何既有模块。
  · 注入块经 zh() 后纯 ASCII，无 V28_BAN_PATTERNS（iframe/postMessage/
    XMLHttpRequest/auth_token/X-YL-），无 fetch。
  · 锚点全部 expect 精确计数；门禁含「改动面 + 冻结面」两截
    （冻结面 = 上游被钉字面串的镜像复述，防本环回踩，§17.6）。
"""

import re

# --------------------------------------------------------------------------- 注入块
# 说明：注释里的中文由 ctx['zh'] 转 \uXXXX；代码纯 ASCII。
#       赋值语句（非函数声明）⇒ ES module 顶层合法（重复声明才是 SyntaxError）。

INJECT_JS = r'''
/* ===== R-050: 洞府灵草「灵石加速」改为一次只缩短半小时 =====
   v2810c 原实现按品阶缩短（普通1/稀有2/传说4/仙品6 小时）；R-050 要求一次半小时。
   此处用「赋值覆盖」而非同名声明：bundle 顶层是 ES module 作用域，重复函数声明
   会 SyntaxError（整包白屏）；函数声明的词法绑定可写，顶层赋值在求值期生效，
   晚于全部 UI 调用。品阶表（上方原函数）原样保留：v2810c 门禁钉它 ==1，只读不改。
   计价公式不动（按实际缩短分钟 × costPerMinute、下限 minCost），故整株催熟
   到成熟的总花费不变，仅单次步长减半（半小时 × 100 = 3000 灵石/次）。 */
YlxwHerbSpeedHours = function (h) { return .5; };
'''

# --------------------------------------------------------------------------- 锚点常量

# 注入锚：v2810c 注入块内的 Ms 定义行（全 bundle 唯一；v2810c G253 逐字钉它 ==1）
# 本环插在其后 ⇒ 赋值语句位于原函数声明之后（求值顺序保证覆盖生效）。
MS_ANCHOR = 'function YlxwHerbSpeedMs(h) { return YlxwHerbSpeedHours(h) * 36e5; }'

# 限域门禁右界：grotto087/v2810c 共享的模块级注入锚（唯一）
YK_ANCHOR = 'function Yk(t){'

# 本环覆盖语句（纯 ASCII；与 v2810c G252 的 'function YlxwHerbSpeedHours(h) {'
# 无字面交集 ⇒ 上游「签名 ==1」门禁不受影响）
OVERRIDE_STMT = 'YlxwHerbSpeedHours = function (h) { return .5; };'

# ---- 每日催熟展示（grotto087 T9-F4 引入的两处，字面 UTF-8 区，勿转 \u）----

# 总览「灵田联动」行（洞府页 overview，T.level 为洞府等级；引号内空格与 bundle 逐字一致：`," 块田 … " 次"]`）
E2_OLD = '," \u5757\u7530 \u00b7 \u6bcf\u65e5\u50ac\u719f ",3+Math.floor(T.level/2)," \u6b21"]'
E2_NEW = ('," \u5757\u7530 \u00b7 \u6bcf\u65e5\u50ac\u719f ",'
          '10+3*Math.min(Math.max(0,T.level-1),4)+2*Math.max(0,T.level-5)," \u6b21"]')

# 升级成功 toast「灵田联动」行（M 为升到的等级）
E3_OLD = '" \u5757\u3001\u6bcf\u65e5\u50ac\u719f " + (3+Math.floor(M/2)) + " \u6b21"'
E3_NEW = ('" \u5757\u3001\u6bcf\u65e5\u50ac\u719f " '
          '+ (10+3*Math.min(Math.max(0,M-1),4)+2*Math.max(0,M-5)) + " \u6b21"')

# --------------------------------------------------------------------------- 冻结针（上游被钉字面串的镜像，全为只读复述）

F_XP6 = r'if (r === "\u4ed9\u54c1") return 6;'          # v2810c 品阶表·仙品（bundle 内是字面 \uXXXX 转义文本）
F_LEG4 = r'if (r === "\u4f20\u8bf4") return 4;'          # 品阶表·传说
F_RARE2 = r'if (r === "\u7a00\u6709") return 2;'         # 品阶表·稀有
F_MS = MS_ANCHOR                                          # Ms 定义行（= 注入锚本体，插入后必须原样在位）
F_CTRUNC = ('const __C0=_[M],g=Date.now(),'
            'C={...__C0,harvestTime:g+Math.min(Math.max(0,__C0.harvestTime-g),YlxwHerbSpeedMs(__C0))};')
F_COMMIT = '_[M]={...C,harvestTime:__C0.harvestTime-q}'
F_HOURS = '\u7f29\u77ed ${YlxwHerbHoursText(q)} \u5c0f\u65f6'
F_LEFT = '（\u5269\u4f59\u4e0d\u8db3\uff0c\u7075\u8349\u5df2\u6210\u719f\uff09'
F_PREVIEW = 'I=Math.min(__left,YlxwHerbSpeedMs(g))'
F_TOOLTIP = ('title:"\u4f7f\u7528\u7075\u77f3\u52a0\u901f\u751f\u957f\uff08\u6bcf\u6b21'
             '\u7f29\u77ed " + YlxwHerbSpeedHours(g) + " \u5c0f\u65f6\uff09",')
F_MATURE = '\u8be5\u7075\u8349\u5df2\u7ecf\u6210\u719f\uff0c\u65e0\u9700\u52a0\u901f\u3002'
F_QPREFIX = 'const q=C.harvestTime-g,w=Math.ceil(q/6e4),'   # fun086 冻结（v2810c G272 镜像）
F_BTNFEE = 'Math.max(Br.minCost,Math.ceil(I/6e4)*Br.costPerMinute).toLocaleString()'  # fun086 冻结
F_BR = 'Br={dailyLimit:10,costPerMinute:100,minCost:1000}'  # Br 常量冻结（fun086/grotto087/v2810c 三方钉）
F_PR = 'Pr=[{level:1,name:"\u7b80\u964b\u6d1e\u5e9c"'      # 洞府等级表冻结（grotto087）
F_LT_TOAST = '\u7075\u7530\u8054\u52a8\uff1a\u4ea7\u51fa +'  # grotto087 G12 门禁针（toast 行前缀）
F_LT_PANEL = '"\u7075\u7530\u8054\u52a8"'                   # grotto087 G13 门禁针（总览行前缀）


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 v2810c）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('r050 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 前置自证（REQUIRES 语义）：v2810c 的 Ms 行必须在位，否则本环锚不成立，当场报错
    n_ms = p.count(MS_ANCHOR)
    if n_ms != 1:
        raise AssertionError('r050 前置不满足：v2810c Ms 定义行出现 %d 次（期望 1）'
                             '——本环必须排在 yl_v2810c_ext.py 之后' % n_ms)

    # 1) 加速一次半小时：Ms 行之后插赋值覆盖（插后 MS_ANCHOR 原文仍在，上游 G253 不受影响）
    p.insert_after('r050-加速半小时覆盖', MS_ANCHOR, blk,
                   expect=1, note='赋值覆盖 YlxwHerbSpeedHours -> 恒返 0.5（ES module 词法绑定可写）')

    # 2) 洞府总览「灵田联动」行：每日催熟 3→10 起步
    p.replace('r050-总览催熟次数10起', E2_OLD, E2_NEW, expect=1,
              note='与服务端 farmBoostCap(=10+3*min(max(0,级-1),4)+2*max(0,级-5)) 同式')

    # 3) 升级 toast「灵田联动」行：同式改「逐级 +3/+2」梯度
    p.replace('r050-toast催熟次数10起', E3_OLD, E3_NEW, expect=1, note='同式')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本环改动 =================
        ('R50·加速覆盖语句已注入',        OVERRIDE_STMT, 1, '==', '恒返 0.5h，计价公式不动'),
        ('R50·覆盖语句位于原实现之后',    OVERRIDE_STMT, 1, '==', '同域后写胜出（node 实证）；within 证明排序',
         (MS_ANCHOR, YK_ANCHOR)),
        ('R50·总览催熟次数已改梯度',      E2_NEW, 1, '==', '10+逐级 +3/+2，与 farmBoostCap 同式'),
        ('R50·toast 催熟次数已改梯度',    E3_NEW, 1, '==', ''),
        ('R50·总览梯度式（前4级+3后+2）',  '3*Math.min(Math.max(0,T.level-1),4)+2*Math.max(0,T.level-5)', 1, '==', ''),
        ('R50·toast 梯度式（前4级+3后+2）', '3*Math.min(Math.max(0,M-1),4)+2*Math.max(0,M-5)', 1, '==', ''),
        ('R50·旧总览 3 次式清零',         '3+Math.floor(T.level/2)', 0, '==', ''),
        ('R50·旧 toast 3 次式清零',       '3+Math.floor(M/2)', 0, '==', ''),
        ('R50·原品阶函数签名仍唯一',      'function YlxwHerbSpeedHours(h) {', 1, '==',
         '赋值覆盖不新增声明（ES module 顶层重复声明会 SyntaxError）'),
        # ================= 冻结：v2810c 加速面逐字保留 =================
        ('冻结·v2810c 品阶表仙品6',       F_XP6, 1, '==', '原函数只读保留（覆盖不删原实现）'),
        ('冻结·v2810c 品阶表传说4',       F_LEG4, 1, '==', ''),
        ('冻结·v2810c 品阶表稀有2',       F_RARE2, 1, '==', ''),
        ('冻结·v2810c Ms 定义行原样',     F_MS, 1, '==', 'G253；亦为本环注入锚'),
        ('冻结·v2810c C 截断行原样',      F_CTRUNC, 1, '==', 'G258：q 天然=实际缩短 ms'),
        ('冻结·v2810c 提交行原样',        F_COMMIT, 1, '==', 'G259'),
        ('冻结·v2810c 新文案缩短小时',    F_HOURS, 1, '==', 'G261：0.5h 时显示「缩短 0.5 小时」'),
        ('冻结·v2810c 剩余不足兜底',      F_LEFT, 1, '==', 'G262'),
        ('冻结·v2810c 按钮预览计价',      F_PREVIEW, 1, '==', 'G263：显示价=实收价'),
        ('冻结·v2810c tooltip 模板',      F_TOOLTIP, 1, '==', 'G265：渲染「每次缩短 0.5 小时」'),
        ('冻结·v2810c 成熟守卫未动',      F_MATURE, 2, '==', 'G266：toast+log 各 1'),
        # ================= 冻结：fun086 / grotto087 / 基线 =================
        ('冻结·fun086 扣费前缀原样',      F_QPREFIX, 1, '==', 'v2810c G272 / grotto087 各钉'),
        ('冻结·fun086 按钮费用串原样',    F_BTNFEE, 1, '==', 'v2810c G273 / grotto087 各钉'),
        ('冻结·Br 常量原样（加速上限10不动）', F_BR, 1, '==', 'G274：本环不改洞府灵草加速次数上限'),
        ('冻结·Pr 等级表未动',            F_PR, 1, '==', 'grotto087：L1~L10 数据齐全'),
        ('冻结·grotto087 toast 行前缀',   F_LT_TOAST, 1, '==', 'G12：只改行内公式不动前缀'),
        ('冻结·grotto087 总览行前缀',     F_LT_PANEL, 1, '==', 'G13'),
        # ================= 冻结：加速入口盘点（v2810c G268/G270 镜像） =================
        ('冻结·加速入口数未变',           'handleSpeedupHerb', 9, '==', '定义1+透传8，唯一逻辑点'),
        ('冻结·无批量加速入口',           'SpeedupAll', 0, '==', ''),
    ]
    return gates
