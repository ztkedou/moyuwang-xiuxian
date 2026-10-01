# -*- coding: utf-8 -*-
"""
yl_forge088_ext.py -- 炼器产出补「境界前缀」（0.8.8 / item19）

用户原话：
  「自带炼器中，无论是材料合成、装备融合、是否自定义名称，前面都要跟自带物品
    一样带上相应境界的前缀，不然系统不好判断装备品阶。」

=========================================================================== 命名规则真相（逐字实证）
自带装备名的**唯一**格式是 `[境界]名称`（**没有** `【品阶】` 前缀）：

  ① 装备池生成器（基座 @322168，`WN()` 内）：
        name: "["+rl+"]"+nm        // rl = 境界串（合道期…），nm = 词缀拼出的基名
        realm: rl
     实证（`_v281_base` 对应的 pristine 存档 542 条 item.name）：
        99 条以 `[` 开头（如 `[筑基期]不朽轮回剑` / `[炼气期]旷世壬水道袍`）
         0 条以 `【` 开头   ← `【品阶】` 前缀在真实数据里**不存在**
     （`localtest/e2e_087.py:652` 的 `【普通】[合道期]测试折算甲` 是**测试脚本手搓**
       的注入样本，不是游戏自身产出的格式；team-lead 初判据此误认格式为
       `【品阶】[境界]名称`。）

  ② 落库函数 `vs(inv, item, qty, {realm,realmLevel})`（基座 @566343）：
        if (isEquippable) {
          const _m2 = /^\[(.+?)\]/.exec(d || "");     // ★ `[` 必须落在**串首**
          if (_m2) { item.realm = _m2[1]; ... }        // 解析出境界写回 item.realm
        }
     ⇒ 名字**必须以 `[` 开头**才能被解析；前缀若变成 `【普通】[合道期]…`，正则失效
       （`yl_eco085_ext.py:58` 记录的正是这个 `^\[` 锚定 bug）。

  结论：炼器产出必须产出 `[玩家当前境界]名称`（`[` 在串首），**不能**加 `【品阶】`。

=========================================================================== 三个产出点（改动前）
炼器面板组件 `L4`（基座 @879796）把三个动作透传给 hook `a4`（基座 @695538）：

  ① 材料合成  handleCraftArtifact → `zg.craftFromMaterials(m, 自定义名, 预选部位)`
        name = 自定义名 || `造化·{rarity}{slot}`          ⇒ **无 [境界] 前缀** ❌
  ② 装备融合  handleFuseArtifact  → `zg.fuseEquipment(甲, 乙, 合成石, 自定义名)`
        name = 自定义名 || `{甲.name}·融合`                ⇒ 默认继承甲的前缀（尚可），
                                                             自定义名 **无前缀** ❌
  ③ 自定义名称：① ② 两条路径的自定义名都直接当 name 用，**无前缀** ❌

（**炼丹（丹药）产出未加前缀 —— 有意为之，非遗漏**：
   ① 用户需求原文限定「**炼器**中…材料合成、装备融合、是否自定义名称」三处，丹药不在范围内；
   ② 丹药不参与「装备品阶 / 可穿境界」判定，`vs()` 也不会对它解析 `[…]`（加前缀无收益）。
   若后续需求扩展，再按同一 `YlxwForgeRealmName` 口径补 `handleCraft` 的 `h.name`。）

=========================================================================== 改法（不动基座）
`zg.craftFromMaterials` / `zg.fuseEquipment` 是对象方法，可在**其定义之后、调用方
`a4` 之前**用属性赋值包装（`zg` 是 `const`，但其属性可写；原始方法用 `.call(zg,…)`
保留 `this`——`craftFromMaterials` 内部要用 `this.getItemTypeFromSlot`）。

包装逻辑（`YlxwForgeRealmName`）：
    base = name.replace(/^\[[^\]]*\]/, "")   // 去掉已有 [境界] 前缀，防双前缀
    name = "[" + realm + "]" + base
境界取值（`realm`）：
    · 材料合成：无基装 ⇒ `Be.getState().player.realm`（玩家当前境界，与
      `vs(…,{realm:T.realm})` 同一来源）
    · 装备融合：继承**基装**（第一件）的境界——先从 `t.name` 的 `[…]` 解析，再退
      `t.realm`，都缺才回落玩家当前境界；避免把「筑基期基装」错标成高境界
产出后 `vs()` 会从串首 `[…]` 解析出 realm 写回 `item.realm`，装备品阶判定恢复。

锚点：`H.Artifact:H.Material}};function a4(t){`（zg 对象字面量的收尾 + a4 起点，唯一）。

硬约束遵守：
  · 只新建本文件 + 修改 build_v26n.py 接线；**不写回 build/assets/**。
  · 注入块 zh() 后纯 ASCII；不含禁用模式 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
"""

import re

# --------------------------------------------------------------------------- 注入块

INJECT_JS = r'''
/* ===== yl-0.8.9 item19: 炼器产出补 [境界] 前缀（对齐自带装备命名 "[境界]名称"） =====
   自带装备名 = "[境界]名称"，vs() 用 /^\[(.+?)\]/ 从串首解析 realm 写回 item.realm。
   炼器两条产出（材料合成 / 装备融合）原本不带前缀（自定义名尤其），本块在 zg 定义之后、
   调用方 a4 之前包装两个工厂，把产出名统一成 "[境界]名称"，并剥掉已有前缀防双前缀。
   境界取值：材料合成无基装 ⇒ 玩家当前境界；装备融合有基装 ⇒ 继承基装境界（缺失则回落玩家）。 */
function YlxwForgeRealm() {
  try { var p = Be.getState().player; return (p && p.realm) || ""; } catch (e) { return ""; }
}
function YlxwForgeRealmName(name, realm) {
  var base = String(name == null ? "" : name).replace(/^\[[^\]]*\]/, "");
  return realm ? ("[" + realm + "]" + base) : base;
}
(function () {
  var _craft = zg.craftFromMaterials, _fuse = zg.fuseEquipment;
  zg.craftFromMaterials = function (t, r, a) {
    var it = _craft.call(zg, t, r, a), rl = YlxwForgeRealm();
    it.name = YlxwForgeRealmName(it.name, rl);
    if (rl) { it.realm = rl; }
    return it;
  };
  zg.fuseEquipment = function (t, r, a, l) {
    var it = _fuse.call(zg, t, r, a, l);
    var m = /^\[([^\]]*)\]/.exec((t && t.name) || "");
    var rl = (m && m[1]) || (t && t.realm) || YlxwForgeRealm();
    it.name = YlxwForgeRealmName(it.name, rl);
    if (rl) { it.realm = rl; }
    return it;
  };
})();
'''

# --------------------------------------------------------------------------- 锚点

# zg 对象字面量收尾（getItemTypeFromSlot 的 return 末尾）紧接 hook a4 定义起点；唯一。
ZG_TAIL_ANCHOR = 'H.Artifact:H.Material}};function a4(t){'
ZG_TAIL_REPL = ('H.Artifact:H.Material}};\n' + INJECT_JS + '\nfunction a4(t){')

# 基线未动断言（工厂内部原样保留，证明只做外层包装）
FACTORY_CRAFT_ANCHOR = 'name:r||`造化·'
FACTORY_FUSE_ANCHOR = 'name:l||`${t.name}·融合`'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('forge088 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    # 负向硬断言：注入块不得含「【」——vs() 用 /^\[(.+?)\]/ 要求 '[' 落在串首，
    # 若给炼器名加「【品阶】」前缀，境界解析会失效（即 eco085 记录的 ^\[ 锚定 bug）。
    assert '\u3010' not in INJECT_JS, 'forge088 注入块不得含【（会破坏 vs() 的 ^\\[ 锚定）'

    # 0) 在 zg 定义之后、hook a4 之前注入包装器（zg 已存在，Be 已存在）
    p.replace('forge088-wrap', ZG_TAIL_ANCHOR, zh(ZG_TAIL_REPL), expect=1,
              note='zg 尾部注入 YlxwForgeRealm/Name + 包装 craftFromMaterials/fuseEquipment')

    # ------------------------------------------------------------- 门禁
    gates = [
        ('item19·YlxwForgeRealm 已定义',        'function YlxwForgeRealm() {',            1, '==', ''),
        ('item19·YlxwForgeRealmName 已定义',    'function YlxwForgeRealmName(name, realm) {', 1, '==', ''),
        ('item19·craftFromMaterials 已包装',    'zg.craftFromMaterials = function (t, r, a) {', 1, '==', ''),
        ('item19·fuseEquipment 已包装',         'zg.fuseEquipment = function (t, r, a, l) {', 1, '==', ''),
        ('item19·包装 IIFE 已注入',             'var _craft = zg.craftFromMaterials, _fuse = zg.fuseEquipment;', 1, '==', ''),
        ('item19·前缀剥离正则',                 '.replace(/^\\[[^\\]]*\\]/, "")',         1, '==', '防双前缀'),
        ('item19·境界来源 player.realm',         'Be.getState().player; return (p && p.realm) || ""', 1, '==', ''),
        ('item19·融合继承基装境界',               'var m = /^\\[([^\\]]*)\\]/.exec((t && t.name) || "");', 1, '==', '基装 [境界] 优先'),
        ('item19·两处调用 YlxwForgeRealmName',   'it.name = YlxwForgeRealmName(it.name, rl);', 2, '==', '材料合成 + 装备融合'),
        # 基线工厂内部零改动（只做外层包装）
        ('item19·基线 craft 命名未动',           FACTORY_CRAFT_ANCHOR,                    1, '==', 'zg.craftFromMaterials 内部原样'),
        ('item19·基线 fuse 命名未动',            FACTORY_FUSE_ANCHOR,                      1, '==', 'zg.fuseEquipment 内部原样'),
        ('item19·call-site craft 未动',          'const x=zg.craftFromMaterials(m,j,b);',  1, '==', ''),
        ('item19·call-site fuse 未动',           'const x=zg.fuseEquipment(m,j,b,S);',     1, '==', ''),
    ]
    return gates
