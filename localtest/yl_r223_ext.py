# -*- coding: utf-8 -*-
r"""
yl_r223_ext.py — R-223 自动打坐「悟道」触发率改为与自动历练同口径（1%~4%，纯客户端）
                  + R223b 天赋「一念悟道」描述同步（C+B：删失效的顿悟承诺，改述基础加成）

==============================================================================
需求原文（用户原话）
==============================================================================
  「自动打坐时候悟道还是不和顿悟绑定了，这样几率太高，把悟道也改成和自动历练
    一样1%最高4%」

==============================================================================
背景与旧/新概率对照
==============================================================================
输入产物：build/assets/index-v2948-20261009.js（线上 0.9.48，
          md5 a01d9aa7959bfabe57e3f91fe893ac79，2,326,078 B）

打坐悟道触发点（`handleMeditate` 内，bundle@748630~748929），旧代码：

    const j=gd(a),
          __r188t=a.talentIds!=null&&a.talentIds.includes("instant-dao"),
          b=Math.random()<(__r188t?0.05:0.01);/*[r188med]*//*[r188med2]*/;
    ...
    if(b){ ... 顿悟文案(+S 修为) ... YlxwToast(x,"special","md-exp",4000),c(x,"special"),
           YlxwWudaoEnlighten(c) }
    else S=Math.floor(v*(.85+Math.random()*.3)), ... 普通打坐文案 ...

  ⇒ 旧口径（与「一念悟道」天赋绑定）：
        · 无该天赋：**1%**
        · 有该天赋（talentIds 含 "instant-dao"）：**5%**
    用户认为「太高」（5% > 4%），且明确要求「不和顿悟绑定」。

  ⇒ 新口径（本模块）：与自动历练**同源同式**的 1%~4%：

        V = 0.01 + Math.min(0.03, luck * 0.0003)

        luck=0   → 1%
        luck=50  → 2.5%
        luck=100 → 4%
        luck≥100 → 4%（封顶，Math.min 截断）

    即：
        · 旧 1%（无天赋）/ 5%（有「一念悟道」天赋）
        · 新 1%（luck=0）~ 4%（luck≥100，封顶）

==============================================================================
★ luck 取值与历练侧同源的证据（照搬口径，不另造来源）
==============================================================================
历练侧（`handleAdventure`，bundle@1936166）原文：

    const U=fe.indexOf(t.realm),
          V=0.01+Math.min(0.03,($a(t.titleId,t.unlockedTitles||[]).luck||0)*0.0003)/*[r193qy]*/;
    ...
    const Z=Math.random()<V;
    Z&&a("✨ 你福至心灵，触发了奇遇！","special");
    await I(Z?"lucky":"normal")

  ⇒ 历练侧 1%~4% 的 `V` 即**奇遇(lucky)触发率**；`luck` 取自
     `$a(t.titleId, t.unlockedTitles||[]).luck`。

打坐侧（`handleMeditate`）玩家对象变量名为 `a`（`const a=Be.getState().player`），
与历练侧的 `t`（同一 player 角色对象）同源同形：两者均从 player 上读
`titleId` / `unlockedTitles`。实测 player 默认对象（bundle@534941）确实含
`titleId:"title-novice"` 与 `unlockedTitles:["title-novice"]`；
`$a` 为模块级函数 `function $a(t,r){...}`（bundle@614400），返回对象含 `.luck`
（`if(!t)return {...,luck:0}`，防御性，缺字段时返回 0）。

  ⇒ 故本模块把打坐那行换成**与历练完全相同的写法**，只把变量 `t` 换成打坐侧的 `a`：

        (__r188t?0.05:0.01)
      →
        (0.01+Math.min(0.03,($a(a.titleId,a.unlockedTitles||[]).luck||0)*0.0003))

     即 `$a(a.titleId, a.unlockedTitles||[]).luck` —— 与历练侧
     `$a(t.titleId, t.unlockedTitles||[]).luck` **同一取值方式、同一函数、同一字段**，
     两处口径严格一致，未自造不同来源。

==============================================================================
★ 查证结论 ②：「一念悟道」天赋（instant-dao）改后是否失效
==============================================================================
实测 `instant-dao` 全 bundle **仅 2 处**引用：
  1. 天赋定义（bundle@375956，talent 的 `specialAbility`）：
       "specialAbility":{"id":"instant-dao","name":"一念悟道",
        "description":"打坐修炼时有15%几率进入顿悟状态，本次修炼经验翻倍。",
        "type":"passive","effects":{"triggerChance":0.15,"damageMultiplier":2}}
  2. 打坐检测行（bundle@748630）：`__r188t=a.talentIds...includes("instant-dao")`

`__r188t` 亦**仅**用于该三元 `(__r188t?0.05:0.01)`（bundle 内 `__r188t` 共 2 处：
定义 1 + 使用 1）。

  ⇒ 结论：把三元换成固定 1%~4% 后，`instant-dao` 的 `specialAbility`
    （`triggerChance:0.15` / `damageMultiplier:2`）**再无任何读取点，彻底失效**。
    打坐悟道率将**不再受该天赋影响**（无天赋/有天赋一律 1%~4%）。
    ★ 注意：该天赋的**基础 effects（expRate+0.2 / spirit+35 / luck+10）仍生效**
      （走常规天赋属性聚合），只是其 specialAbility 变成死数据。
    ★ 另：该天赋描述本就与旧代码不一致——描述写「**15%** 几率进入顿悟」，
      旧代码却用 **5%**（无天赋 1%）；改后则为 0%，描述进一步失真。
    ★ 该天赋 rarity=传说、fateCost=4（昂贵），失效影响不可忽略。

  可选处理（**本环仅改概率，以下均待用户拍板，不擅自实施**）：
    (A) 保留其作用：有天赋时给一个小幅加成（例如 luck 视为 +N，或概率 +1%），
        但会突破「最高 4%」上限，与用户「最高4%」的表述冲突，需用户确认；
    (B) 改其**描述**：去掉「15%…翻倍」表述，改为与实际一致（如「打坐修炼速度提升」
        或删除 specialAbility 段），使文案不再误导；
    (C) 保持现状：接受该天赋 specialAbility 失效（用户「不和顿悟绑定」的字面诉求）。

==============================================================================
★ 查证结论 ③：悟道面板提示文案是否仍准确
==============================================================================
悟道面板提示（bundle@1456057，转义态，全 bundle 恰 1 处）：

    "\u73a9\u6cd5\u63d0\u793a\uff1a\u6253\u5750 / \u5386\u7ec3\u4e2d\u4f1a\u968f\u673a
     \u89e6\u53d1\u609f\u9053\u7ecf\u9a8c\u63d0\u5347\u3002"

  解码：**「玩法提示：打坐 / 历练中会随机触发悟道经验提升。」**

  ⇒ 改后：打坐侧仍**随机触发**悟道（1%~4%），历练侧仍**随机触发**（跟随奇遇率）。
    该文案**仍然准确**，故**未动**（本环不擅自改文案）。

==============================================================================
★ R223b（本轮追加）：天赋「一念悟道」描述同步 —— 用户拍板 C + B
==============================================================================
用户已拍板（C + B）：
  · C —— 接受「悟道不再与天赋绑定」（这正是用户要的，见上「查证结论 ②」）。
  · B —— 把该天赋的描述改掉，不让它继续撒谎。

改动点：天赋 talent-dao-mind「道心通明」的 specialAbility「一念悟道」的 description
（bundle@375998，本区段为**字面中文**，全 bundle 恰 1 处）：

  旧（解码）：打坐修炼时有15%几率进入顿悟状态，本次修炼经验翻倍。
  新（解码）：道心通明：修炼速度提升20%，神识+35、气运+10。

  依据：specialAbility 的 {triggerChance:0.15, damageMultiplier:2} 自 R-223 起
        **再无读取点**（见上「查证结论 ②」），旧描述承诺的「15% 顿悟、经验翻倍」
        彻底失效；该天赋真实生效的是**基础 effects**：
          expRate+0.2（修炼速度 +20%）、spirit+35（神识 +35）、luck+10（气运 +10）。
        新描述即逐项对应这三项基础加成，与实现一致、玩家看得懂。
        （数值口径对照：talent-fast-cultivation expRate 0.15 → 描述「修炼速度提升15%」；
          nt-61 luck 10 → 「提升气运」；nt-47 spirit 64 → 「提升神识」。）

  ★ 只改 description 一个字串：不删 specialAbility 整段、不动其 id/name/type/effects，
    也不动天赋基础 effects 与基础描述（见新增冻结门禁）。
  ★ 实测 specialAbility 段**确无读取点**（全 bundle 27 处引用中，除 25 处为各天赋自身
    的 JSON 数据外，仅 @507858 / @517507 两处 `t.specialAbility ? ⭐图标 : null`
    的 truthiness 判断——不读 name/description/effects）⇒ 该段为死数据，其 description
    亦不渲染；本环按用户拍板只同步描述，**建议后续清理整段**（本环不动）。

  ★ 同时核对「别处承诺顿悟」：全 bundle 与本天赋（talent-dao-mind / instant-dao）相关的
    文案**仅此 1 处**（即本次改动点）；天赋列表/抽取/图鉴无独立串（天赋渲染仅用 t.name +
    t.specialAbility 存在性）。另有 3 个**他天赋**的名字含「顿悟」（非本天赋、纯风味命名）：
      · talent-enlightened「顿悟」（desc：偶有灵光一闪，修炼速度提升明显。）
      · nt-46「顿悟大道」（desc：提升修炼速度、神识。）
      · nt-comp-6「一念顿悟」（desc：提升修炼速度、神识。）
    三者均非「机制承诺」，**不在本环范围、一字未动**（见冻结门禁 FRZ_OTHER_DUNWU_*）。
    打坐按钮 tooltip（@878352「偶尔触发顿悟」）与打坐顿悟 toast（@748824）**仍准确**
    （打坐悟道仍 1%~4% 触发），未动。

==============================================================================
契约（standalone，同 localtest/yl_r216_ext.py / yl_r214_ext.py / yl_r215_ext.py）
==============================================================================
  · CLI：`--src <js>`；可选 `--node <node.exe>`（缺省自动探测 PATH 上的 node）；
         可选 `--simulate [N]`（对 1%~4% 公式做蒙特卡洛自测，默认 100000 次）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r223-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点计数失败；
    1=其它错误（含门禁未全绿、往返不一致、node --check 失败）。
  · EDITS 四元组 (label, old, new, n)；n=该处旧串期望命中数=替换次数
    （本环 2 处：① 打坐悟道率概率式；② 一念悟道描述。两者锚点形态不同：①转义态纯 ASCII、
     ②字面中文，_precheck 按形态分别断言）。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证 + node 自检。
  · 纯客户端；不改 build_v26n.py / chain_build.py / dryrun_087.py / sim_remote_check.py /
    任何 build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 锚点
# 打坐顿悟分支的概率表达式（含前后锚点，保证唯一；纯 ASCII）
A_OLD = 'b=Math.random()<(__r188t?0.05:0.01);/*[r188med]*//*[r188med2]*/'
# 新表达式：与历练侧同源同式（变量由 t 换成打坐侧的 a），并追加幂等标记
N_NEW = ('b=Math.random()<(0.01+Math.min(0.03,'
         '($a(a.titleId,a.unlockedTitles||[]).luck||0)*0.0003))'
         ';/*[r188med]*//*[r188med2]*//*YLXW_R223_V2948*/')

# 核心新公式（门禁在位判定用；与历练侧 handleAdventure 的 V 完全一致，仅变量名不同）
N_CORE = '0.01+Math.min(0.03,($a(a.titleId,a.unlockedTitles||[]).luck||0)*0.0003)'
# 旧三元（必须清零）
OLD_TERNARY = '(__r188t?0.05:0.01)'
# 幂等标记
MARK = '/*YLXW_R223_V2948*/'

# ---- R223b：天赋「一念悟道」描述（字面中文，全 bundle 恰 1 处）----
# 旧描述：承诺 15% 顿悟、经验翻倍（specialAbility 失效后为谎言）
A_DESC = '打坐修炼时有15%几率进入顿悟状态，本次修炼经验翻倍。'
# 新描述：改述该天赋真实生效的基础 effects（expRate+0.2 / spirit+35 / luck+10）
N_DESC = '道心通明：修炼速度提升20%，神识+35、气运+10。'

EDITS = [
    ('R223 打坐悟道率 (__r188t?0.05:0.01) → 与历练同源 1%~4%', A_OLD, N_NEW, 1),
    ('R223b 一念悟道描述 → 与实现一致（去失效的顿悟承诺，改述基础加成）', A_DESC, N_DESC, 1),
]

# --------------------------------------------------------------------------- 冻结门禁串（不得改动）
FRZ_TALENT_DETECT = 'a.talentIds!=null&&a.talentIds.includes("instant-dao")'  # 天赋检测行
FRZ_INSIGHT_TEXT = '你突然顿悟，灵台清明，对大道有了更深的理解'                   # 顿悟文案（字面中文）
FRZ_ENLIGHTEN_CALL = 'YlxwWudaoEnlighten(c)'                                # 打坐侧悟道调用
FRZ_WUDAO_MAYBE = 'YlxwWudaoMaybe'                                          # 历练侧悟道入口（def+call）
FRZ_STONE_MIN = 'YLXW_WUDAO_ADV_STONE_MIN'                                  # 历练侧奇遇阈值
FRZ_DIFFGAIN = 'YlxwDiffGain(v,"expMul")'                                   # r218 打坐入账点
FRZ_MED_MARKERS = '/*[r188med]*//*[r188med2]*/'                             # r188 打坐标记
FRZ_PANEL_HINT = ('\\u73a9\\u6cd5\\u63d0\\u793a\\uff1a\\u6253\\u5750 / '
                  '\\u5386\\u7ec3\\u4e2d\\u4f1a\\u968f\\u673a\\u89e6\\u53d1'
                  '\\u609f\\u9053\\u7ecf\\u9a8c\\u63d0\\u5347\\u3002')       # 悟道面板提示（转义态）

# ---- R223b 冻结：本天赋的基础加成 / specialAbility 段 / 基础描述，逐字未动 ----
# 天赋基础 effects（expRate+0.2 / spirit+35 / luck+10）——必须保持，且紧邻 specialAbility
FRZ_TALENT_BASE_EFFECTS = '"effects":{"expRate":0.2,"spirit":35,"luck":10},"specialAbility"'
# specialAbility 的 id / name 未被改动（仅改其 description）
FRZ_SA_NAME = '"specialAbility":{"id":"instant-dao","name":"一念悟道"'
# specialAbility 的 type / effects（triggerChance:0.15 / damageMultiplier:2）未被改动
FRZ_SA_EFFECTS = '"type":"passive","effects":{"triggerChance":0.15,"damageMultiplier":2}'
# 天赋自身基础描述未被改动
FRZ_TALENT_BASE_DESC = '道心如明镜，对天地法则有超凡感悟。'
# ---- R223b：他天赋名字含「顿悟」（非本天赋、纯风味命名；本环一字未动）----
FRZ_OTHER_DUNWU_1 = '{"id":"talent-enlightened","name":"顿悟"'
FRZ_OTHER_DUNWU_2 = '{"id":"nt-46","name":"顿悟大道"'
FRZ_OTHER_DUNWU_3 = '{"id":"nt-comp-6","name":"一念顿悟"'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note)。"""
    return [
        ('R223·新概率式在位', N_CORE, 1, '==', '1%~4% 公式（与历练同源）'),
        ('R223·旧三元清零', OLD_TERNARY, 0, '==', '旧 (__r188t?0.05:0.01) 必须为 0'),
        ('R223·幂等标记唯一', MARK, 1, '==', '/*YLXW_R223_V2948*/'),
        ('冻结·天赋检测行未动', FRZ_TALENT_DETECT, 1, '==', 'a.talentIds…includes("instant-dao")'),
        ('冻结·顿悟文案未动', FRZ_INSIGHT_TEXT, 1, '==', '你突然顿悟，灵台清明…'),
        ('冻结·Enlighten调用未动', FRZ_ENLIGHTEN_CALL, 1, '==', 'YlxwWudaoEnlighten(c)'),
        ('冻结·历练WudaoMaybe未动', FRZ_WUDAO_MAYBE, 2, '==', 'def + call'),
        ('冻结·STONE_MIN未动', FRZ_STONE_MIN, 3, '==', 'YLXW_WUDAO_ADV_STONE_MIN'),
        ('冻结·r218入账点未动', FRZ_DIFFGAIN, 1, '==', 'YlxwDiffGain(v,"expMul")'),
        ('冻结·r188打坐标记未动', FRZ_MED_MARKERS, 1, '==', '/*[r188med]*//*[r188med2]*/'),
        ('冻结·悟道面板提示未动', FRZ_PANEL_HINT, 1, '==', '玩法提示：打坐 / 历练中…（改后仍准确）'),
        # ---- R223b：一念悟道描述同步 ----
        ('R223b·新天赋描述在位', N_DESC, 1, '==', '道心通明：修炼速度提升20%，神识+35、气运+10。'),
        ('R223b·旧天赋描述清零', A_DESC, 0, '==', '「15%…顿悟…翻倍」旧口径必须为 0'),
        ('冻结·天赋基础effects未动', FRZ_TALENT_BASE_EFFECTS, 1, '==', 'expRate0.2/spirit35/luck10'),
        ('冻结·specialAbility名未动', FRZ_SA_NAME, 1, '==', 'id=instant-dao / name=一念悟道'),
        ('冻结·specialAbility效果未动', FRZ_SA_EFFECTS, 1, '==', 'triggerChance0.15/damageMultiplier2'),
        ('冻结·天赋基础描述未动', FRZ_TALENT_BASE_DESC, 1, '==', '道心如明镜…'),
        ('冻结·他天赋「顿悟」名未动', FRZ_OTHER_DUNWU_1, 1, '==', 'talent-enlightened（非本环）'),
        ('冻结·他天赋「顿悟大道」名未动', FRZ_OTHER_DUNWU_2, 1, '==', 'nt-46（非本环）'),
        ('冻结·他天赋「一念顿悟」名未动', FRZ_OTHER_DUNWU_3, 1, '==', 'nt-comp-6（非本环）'),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new, n in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old and new, '%s 锚点不得为空' % name
        assert n >= 1, '%s n 必须 >=1' % name
        # 形态一致性：转义态（纯 ASCII）与字面态（含非 ASCII）须成对出现
        ascii_old = all(ord(ch) < 128 for ch in old)
        ascii_new = all(ord(ch) < 128 for ch in new)
        assert ascii_old == ascii_new, '%s 新旧锚点形态（转义/字面）必须一致' % name

    # 形态断言：概率锚点为转义态（纯 ASCII）；描述锚点为字面中文（含非 ASCII）
    for tag, s in (('A_OLD', A_OLD), ('N_NEW', N_NEW)):
        assert all(ord(ch) < 128 for ch in s), '%s 须纯 ASCII（转义态）' % tag
    for tag, s in (('A_DESC', A_DESC), ('N_DESC', N_DESC)):
        assert any(ord(ch) >= 128 for ch in s), '%s 须为字面中文（含非 ASCII）' % tag

    # 旧三元必须内嵌于旧锚点；新公式必须内嵌于新锚点
    assert OLD_TERNARY in A_OLD, '旧三元不在旧锚点内'
    assert N_CORE in N_NEW, '新公式不在新锚点内'
    assert MARK in N_NEW, '幂等标记不在新锚点内'
    # 新旧互斥：新锚点不得再含旧三元；旧锚点不得含新公式
    assert OLD_TERNARY not in N_NEW, '新锚点不得再含旧三元'
    assert N_CORE not in A_OLD, '旧锚点不得含新公式'
    # 旧概率数字（0.05）必须被清除
    assert '0.05' in A_OLD, '旧锚点应含 0.05'
    assert '0.05' not in N_NEW, '新锚点不应再出现 0.05'
    # 新公式三要素：下界 0.01 / 上限 Math.min(0.03) / 系数 0.0003
    assert '0.01' in N_CORE and 'Math.min(0.03' in N_CORE and '0.0003' in N_CORE, \
        '新公式须含 0.01 / Math.min(0.03) / 0.0003'
    # 同源取值方式：与历练侧一致的 $a(...).luck
    assert '$a(a.titleId,a.unlockedTitles||[]).luck' in N_CORE, \
        '新公式须与历练侧同源的 luck 取值方式'
    # 上下文锚点（前后标记）必须保留
    assert '/*[r188med]*//*[r188med2]*/' in N_NEW, '新锚点须保留 r188 打坐标记'

    # ---- R223b：描述新旧锚点语义断言 ----
    # 旧描述须含失效承诺三要素：15% / 顿悟 / 翻倍
    assert '15%' in A_DESC and '顿悟' in A_DESC, 'A_DESC 应含「15%」与「顿悟」'
    assert '翻倍' in A_DESC, 'A_DESC 应含「翻倍」'
    # 新描述必须彻底清除失效承诺，且逐项体现基础加成（20% / 35 / 10）
    assert '15%' not in N_DESC and '顿悟' not in N_DESC and '翻倍' not in N_DESC, \
        'N_DESC 不得再出现「15%」/「顿悟」/「翻倍」'
    assert '20%' in N_DESC and '35' in N_DESC and '10' in N_DESC, \
        'N_DESC 须体现基础加成 expRate+0.2 / spirit+35 / luck+10'
    # 新旧描述不得互相包含（保证唯一命中）
    assert A_DESC not in N_DESC and N_DESC not in A_DESC, '描述新旧锚点不得互相包含'

    # 注入内容不得含网络/存储原语（纯概率式/文案替换，理应都不含）
    for _n, _o, nw, _c in EDITS:
        for ban in ('fetch(', 'localStorage', 'XMLHttpRequest', 'setInterval(', 'setTimeout('):
            assert ban not in nw, '注入内容不得含 %s' % ban


def _classify(txt):
    """判定基线态：'patched' / 'baseline' / 'partial'。"""
    n_new_ok = sum(1 for _t, _o, n, c in EDITS if txt.count(n) == c)
    n_old_ok = sum(1 for _t, o, _n, c in EDITS if txt.count(o) == c)
    if n_new_ok == len(EDITS) and n_old_ok == 0:
        return 'patched'
    if n_new_ok == 0 and n_old_ok == len(EDITS):
        return 'baseline'
    return 'partial'


def _node_check(out_bytes, node_bin):
    """对产物跑 `node --check`（fail-closed）；找不到 node 则告警跳过。"""
    if not node_bin:
        node_bin = shutil.which('node')
    if not node_bin:
        print('  [WARN] 未找到 node，跳过 node --check（可用 --node 显式指定）')
        return True
    fd, tmp = tempfile.mkstemp(prefix='.r223chk-', suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out_bytes)
        p = subprocess.run([node_bin, '--check', tmp],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            print('  [FAIL] node --check 未通过:\n%s'
                  % p.stderr.decode('utf-8', 'replace')[:2000])
            return False
        print('  [OK] node --check 通过')
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _simulate(n=100000):
    """对 1%~4% 公式做蒙特卡洛自测（与 bundle 内公式逐字等价）。"""
    import random
    print('[SIM] Math.random() < 0.01 + Math.min(0.03, luck*0.0003)   n=%d/组' % n)
    for luck in (0, 50, 100, 200):
        p = 0.01 + min(0.03, luck * 0.0003)
        hit = sum(1 for _ in range(n) if random.random() < p)
        print('  luck=%-4d  p=%.4f  命中=%d/%d  (%.3f%%)'
              % (luck, p, hit, n, 100.0 * hit / n))
    print('  预期：luck=0→1.0%%  luck=50→2.5%%  luck=100→4.0%%  luck=200→4.0%%(封顶)')


def main() -> int:
    ap = argparse.ArgumentParser(description='R-223 打坐悟道率改为与历练同口径 1%~4% + R223b 一念悟道描述同步（客户端 --src 补丁）')
    ap.add_argument('--src', default=None, help='装配产物 js（如 build/assets/index-v2948-20261009.js）')
    ap.add_argument('--node', default=None, help='node 可执行文件（缺省自动探测 PATH）')
    ap.add_argument('--simulate', nargs='?', type=int, const=100000, default=None,
                    help='仅运行 1%%~4%% 公式蒙特卡洛自测（可选次数，默认 100000），不做补丁')
    a = ap.parse_args()

    if a.simulate is not None:
        _simulate(a.simulate)
        return 0

    if not a.src:
        print('[FAIL] 未提供 --src（或使用 --simulate 仅自测）')
        return 2
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
    txt0 = src.decode('utf-8', errors='replace')

    # 1) 幂等 / 部分补丁态
    st = _classify(txt0)
    if st == 'patched':
        print('[SKIP] source looks already patched（R-223 打坐悟道率已在位）')
        return 3
    if st == 'partial':
        print('[FAIL] 检测到部分补丁态，拒绝写盘')
        return 2

    # 2) 基线碰撞检查：新串不得已在基线出现
    for _name, _old, new, _n in EDITS:
        c = txt0.count(new)
        if c != 0:
            print('[FAIL] 新串已在基线出现 %d 次，拒绝写盘：%s' % (c, new[:60]))
            return 2

    # 3) 锚点计数（rc=2 面）
    for name, old, _new, n in EDITS:
        c = txt0.count(old)
        if c != n:
            print('[FAIL] %s 锚点出现 %d 次（期望 %d）' % (name, c, n))
            return 2

    # 4) 应用
    out_txt = txt0
    for _name, old, new, n in EDITS:
        out_txt = out_txt.replace(old, new, n)
    out = out_txt.encode('utf-8')

    # 5) 门禁
    ok = True
    for label, needle, exp, op, note in gates():
        act = out_txt.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-28s actual=%d expect %s %d' % ('OK' if good else 'FAIL', label, act, op, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 6) 往返自证
    back = out_txt
    for _name, old, new, n in reversed(EDITS):
        assert back.count(new) == n, '往返自证：new 在产物中计数 != %d' % n
        back = back.replace(new, old, n)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 7) node 自检（fail-closed）
    if not _node_check(out, a.node):
        print('[FAIL] node --check 失败，未写盘')
        return 1

    # 8) 改前 .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r223-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r223-', suffix='.tmp')
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
