# -*- coding: utf-8 -*-
r"""
yl_r124_ext.py — R-124 灵田种植 BUG（客户端半边 · 服用预览英文 `spirit` 修显示名）

台账原文（R-124，逐字，摘句）
--------------------------------------------------------------------------
  「…壮骨花加了两次防御+30，培元草防御只加了8. **有些描述还出现了英文**，总之这一块
    数值、灵石极度不平衡疑似是bug。」

根因（2026-10-02 逐字实读 build/assets/index-v2912-20261002.js = 0.9.12 线上 abda0903…）
--------------------------------------------------------------------------
  服用效果的玩家可见文案（二次确认弹窗 / 「服用」按钮 title / 种植按钮悬浮 tip）全部由
  `YlxwFtConsumeText(cd)` 渲染（farm089 注入，@1145017 起），逐项：
      parts.push((YLXW_FT_ATTR[a[i].key] || a[i].key) + " +" + YlxwNum(a[i].value));
  标签表只有 4 键：
      var YLXW_FT_ATTR = { attack:"攻击", defense:"防御", maxHp:"气血", speed:"身法" };
  而服务端 FARM_CROP_ATTRS.jiugiaoxuanzhi（九窍玄芝·仙品综合草）第三项是
  { key: 'spirit', label: '神识' } ⇒ /farm/status 的 consAttr 下发 key='spirit'
  ⇒ `YLXW_FT_ATTR['spirit']` 未定义 ⇒ 回退显示裸键 **`spirit +350`** ——
  这就是「有些描述还出现了英文」。（dicts 全量扫：含拉丁字母的 description = 0 处；
  FARM_CROP_PCT 三键 critRate/dodgeRate/lifeLeech 全有映射 ⇒ 英文泄漏仅此一处。）

修法（最小根修）
--------------------------------------------------------------------------
  给 YLXW_FT_ATTR 补第 5 键 `spirit: "神识"`。服务端零改动（spirit 本就是真实存档
  字段，服用入账 `sd.player.spirit += attr` 行为不变，只修显示名）。

接线位置（★ 给 lead）
--------------------------------------------------------------------------
  V28_MODULES 中本模块必须排在 **yl_farm089_ext 之后**（FT_ATTR 表来源）且
  **yl_speedname097_ext 之后**（该模块把 FT_ATTR 的 speed 值「速度」→「身法」，
  本模块锚点用的是身法形态）。建议与其它 r1xx 新模块一起排在 numbal 之前的尾部。

不动的面（冻结门禁全数断言）
--------------------------------------------------------------------------
  · YLXW_FT_PCT / YLXW_FT_PCT_CAP 两表与两处 `|| x.key` 回退行一字不动；
  · speedname097 的 sn-e-labels 期望（`speed: "\u8eab\u6cd5"` == 4）本模块 Δ0；
  · YLXW_SECT_GF_STAT（另一张含 speed/spirit 的标签表）一字不动；
  · YlxwFtConsumeText / YlxwFtHarvestText / YlxwFtSellText 函数体一字不动
    （回通行内补映射后自动生效，无需改渲染代码）。
  · 壮骨花重复 defense 的服务端半边见 localtest/srv_patch_r124.py（两线零交集）。
"""

import re

# --------------------------------------------------------------------------- 编辑（纯替换，无注入）

# 锚点 = FT_ATTR 整行字面（\uXXXX 转义形态；2026-10-02 实测 0.9.12 产物内恰 1 处）。
#   ★ 不能用短锚 `speed: "\u8eab\u6cd5" };`：该形态在产物内有 2 处
#     （YLXW_SECT_GF_STAT @1031201 + 本表 @1144232），必须带 `var YLXW_FT_ATTR = {` 前缀限域。
E1_OLD = (r'var YLXW_FT_ATTR = { attack: "\u653b\u51fb", defense: "\u9632\u5fa1", '
          r'maxHp: "\u6c14\u8840", speed: "\u8eab\u6cd5" };')
E1_NEW = (r'var YLXW_FT_ATTR = { attack: "\u653b\u51fb", defense: "\u9632\u5fa1", '
          r'maxHp: "\u6c14\u8840", speed: "\u8eab\u6cd5", spirit: "\u795e\u8bc6" };')

EDITS = [
    ('E1 FT_ATTR 补 spirit 映射', E1_OLD, E1_NEW, 1),
]

BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']


def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 自检 1：替换串必须真的变了，且新串确含 spirit 映射
    for _nm, _a, _b, _e in EDITS:
        if _a == _b:
            raise AssertionError('r124 %s：锚点替换为恒等（无改动）' % _nm)
    assert r'spirit: "\u795e\u8bc6"' in E1_NEW
    # 自检 2：锚点两形态不得互为子串（防 replace 顺序踩空）
    assert E1_OLD not in E1_NEW and E1_NEW not in E1_OLD
    # 自检 3：本模块无注入块 ⇒ 禁用模式检查退化为对编辑串本身
    for _pat in BAN_PATTERNS:
        for _nm, _a, _b, _e in EDITS:
            if _pat in _a or _pat in _b:
                raise AssertionError('r124 %s 含禁用模式: %s' % (_nm, _pat))

    # 就地替换
    for name, old, new, exp in EDITS:
        p.replace(name, old, new, expect=exp,
                  note='R-124：服用预览 spirit 裸键回退英文 ⇒ 标签表补 spirit:神识')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本环改动 =================
        ('R124·FT_ATTR 补 spirit 映射',  r'speed: "\u8eab\u6cd5", spirit: "\u795e\u8bc6" };', 1, '==',
         '服用预览/确认弹窗/悬浮 tip 不再回退英文 spirit'),
        ('R124·旧 FT_ATTR 行已清零',     E1_OLD, 0, '==', ''),
        # ================= 冻结：渲染路径一字不动（映射补键即生效） =================
        ('冻结·FT_ATTR 定义仍在',        'var YLXW_FT_ATTR = {', 1, '==', ''),
        ('冻结·consAttr 回退行未动',     '(YLXW_FT_ATTR[a[i].key] || a[i].key)', 1, '==', 'farm089 注入'),
        ('冻结·consPct 回退行未动',      '(YLXW_FT_PCT[p[i].key] || p[i].key)', 1, '==', ''),
        ('冻结·FT_PCT 定义未动',         'var YLXW_FT_PCT = { critRate:', 1, '==', ''),
        ('冻结·FT_PCT_CAP 未动',         'var YLXW_FT_PCT_CAP = { critRate: 0.08, dodgeRate: 0.06, lifeLeech: 0.04 };', 1, '==', ''),
        ('冻结·ConsumeText 定义未动',    'function YlxwFtConsumeText(cd) {', 1, '==', ''),
        ('冻结·HarvestText 定义未动',    'function YlxwFtHarvestText(cd, slot) {', 1, '==', ''),
        ('冻结·SellText 定义未动',       'function YlxwFtSellText(cd, slot) {', 1, '==', ''),
        # ================= 冻结：跨模块标签表计数（坑 26：改前全仓 grep） =================
        ('冻结·speedname097 身法映射 Δ0', r'speed: "\u8eab\u6cd5"', 4, '>=', 'sn-e-labels 期望 4，本模块不增不删'),
        ('冻结·SECT_GF_STAT 未动',       'var YLXW_SECT_GF_STAT = {', 1, '==', '另一张含 speed:身法/spirit:神识 的表'),
        ('冻结·FT_PCT 三键映射未动',     r'critRate: "\u66b4\u51fb", dodgeRate: "\u95ea\u907f", lifeLeech: "\u5438\u8840"', 1, '==', ''),
        # ================= 冻结：灵田消费面（R-124 服务端半边零交集） =================
        ('冻结·T5 面板注册未动',         'YLXW_COMP.farm=YlxwTFarmT5;', 1, '==', ''),
        ('冻结·收获端点未动',            '"/farm/harvest"', 3, '==', '旧 + T10 死面板 + T5'),
        ('冻结·状态端点未动',            '"/farm/status"', 3, '==', '原生 YlxwTFarm + T5 活面板 + T10 死面板'),
        # ================= 冻结：客户端仍无作物数值表（权威在服务端） =================
        ('冻结·无作物数值表',            'linggusi', 0, '==', '数值权威在 srv（r115 既有口径）'),
        ('冻结·无壮骨花字面',            '\u58ee\u9aa8\u82b1', 0, '==', '作物名只由服务端下发'),
    ]
    return gates
