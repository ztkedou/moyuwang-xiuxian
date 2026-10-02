# -*- coding: utf-8 -*-
r"""
yl_r106_ext.py — R-106 道具「描述/预览」与实际生效值不一致（只改显示口径）

需求原文（台账 R-106，用户 2026-10-01）
--------------------------------------------------------------------------
  「丹药的使用，描述中写的神识+23 体魄+22，使用后提示神识+5，体魄+9，
    为什么会出现这种情况。千年灵芝也和刚才的显示属性不同『你使用了千年灵芝。
    恢复了1500点气血。神识永久+50，体魄永久+43，气血上限永久+100，
    最大寿命永久+300年』」

==============================================================================
一、根因（本会话独立复核，基线 build/assets/index-v2910-20261001.js）
==============================================================================
① 永久属性加成在**使用侧**只走一个入口 —— 缩放函数 `$r`（@774378，全文 count==1）：
       $r=(t,r,a)=>{if(!Number.isFinite(a)||a<=0)return 0;
                    const l=Number(t[r])||0, c=ZS(t,r);
                    if(l<=c)return Math.floor(a);
                    const d=Math.max(.25,Math.min(1,c/l));
                    return Math.max(1,Math.floor(a*d))}
   `ZS=(t,r)=>{...}`（@774300，count==1）给出该境界的「基准值」：
   仅由 `t.realm` / `t.realmLevel` 决定（baseMaxHp/baseAttack/baseDefense/…），
   **与玩家当前属性无关**。
   ⇒ 当玩家当前属性 `t[r]` **超过**该境界基准值 `c` 时，永久加成按 `c/l` 打折，
     下限 25%。境界越高、属性越超前，折扣越狠。

② 使用道具的唯一处理函数 `Ig`（@774437）在 `r.permanentEffect && !r.isEquippable`
   分支里对 6 个属性逐个 `$r(u,key,raw)`（锚点 @776491，count==1）：
       if(R.spirit){const E=$r(u,"spirit",R.spirit);u.spirit+=E,h.push(`神识永久 +${E}`)}
   ⇒ **入账值 E 已是折算值**（用户看到的「神识永久 +5」= E，正确）；
     而道具详情/预览显示的是 `permanentEffect` 的**原值**（23），
     两者口径不同 ⇒ 用户看到「描述 23 / 实际 5」。

③ 反证对照：`maxLifespan` **不走** `$r`，是原值直加：
       if(R.maxLifespan&&(u.maxLifespan=(u.maxLifespan??100)+R.maxLifespan,…
          h.push(`最大寿命永久 +${R.maxLifespan} 年`)),
   ⇒ 用户反馈里「最大寿命永久 +300 年」与描述一致（千年灵芝 maxLifespan:300），
     而同一件道具的 spirit/physique/maxHp 被折成 50/43/100 —— 完美吻合根因。

④ 千年灵芝数据核对：`AN` 灵草表 @301979
       {id:"millennium-lingzhi",…,effect:{hp:1500},
        permanentEffect:{maxHp:400,spirit:200,physique:150,maxLifespan:300}}
   用户提示「恢复1500点气血 / 神识+50 / 体魄+43 / 气血上限+100 / 寿命+300」：
   1500 与 300 是原值（气血恢复不走 $r；寿命不走 $r），
   200→50、150→43、400→100 是 $r 折算（不同属性的 c/l 不同，故折扣率不同）。
   ⇒ 根因确认。

==============================================================================
二、改后行为（只改「显示/提示口径」，数值一律不动）
==============================================================================
1) 背包/储物袋道具详情卡（`s1` 组件，@1473618 的永久加成格）：
   6 个永久属性显示值改为 `YlxwR106F(key,原值)`（= 当前玩家 `$r` 折算值），
   并在发生折算时追加标注「（按当前属性折算）」。
2) 宗门宝库/奖励选择浮层（@1834256）与商店道具详情（@1790283，zh() 转义形态）：
   同样 6 个属性按 `$r` 折算 + 标注。
3) 丹药/丹方药效预览（R-064 注入的 `YLXW_PILL_FX` 永久段）：
   永久值改为折算值，折算时追加「（原值 +N，按当前属性折算）」。
4) 使用后的提示（`Ig` 的 `h.push`）：
   保留折算后的入账值，折算时追加「（原值 +N，按当前属性折算）」，
   让玩家一眼看懂「为什么比描述少」。`maxLifespan` 不折算、不加注（口径本就一致）。

**禁止项**（严守边界）：
  · 不改 `$r` / `ZS` 的数学（本模块只**调用** `$r`）；
  · 不改任何数值表：`permanentEffect` 数字、`HN` 表、`AN` 表、售价 —— 那是 R-107；
  · 不改存档 schema、不改使用侧入账逻辑（`u[key]+=E` 原样保留）。

==============================================================================
三、实现
==============================================================================
模块级 `INJECT_JS` 注入 3 个纯展示助手（**只读**）：
  YlxwR106F(k,v)    → 当前玩家 `$r` 折算后的展示值（非 6 属性 key / 无玩家时原值返回）
  YlxwR106Tag(k,v)  → 折算过则「（按当前属性折算）」，否则 ""
  YlxwR106Note(k,v) → 折算过则「（原值 +v，按当前属性折算）」，否则 ""
取玩家走**基座既有**的 `YlxwPlayer()`（yl_flow083 定义，@1285428）——
`return Be.getState().player`，是模块级 `function`，函数声明提升，
故注入位置在显示点之前/之后都能调用。助手置于 `function YlxwPlayer() {` 之前。

注入块由 build 侧按 `INJECT_BEFORE_ANCHOR` 自动插入；`_t_mod.py` 不做该步，
故 `apply()` 内做「缺失才补插」的兼容（**不产生重复**，两侧产物一致）。

==============================================================================
四、风险点
==============================================================================
1. `YlxwR106F` 内部用 try/catch 兜底，任何异常都回落原值 ⇒ 最坏退化为「显示原值」，
   不会白屏、不会改数。
2. 详情卡 `s1` 是 `Rt.memo` 且自定义比较器不含 `player` ⇒ 玩家属性单独变化而
   道具其它 props 不变时可能显示略旧的折算值；但入账/使用必然伴随 inventory
   quantity 变化（比较器命中 quantity）而重渲染，实际影响可忽略。
3. `$r` / `ZS` 是压缩名：本模块只引用、不改写；`numbal` 不碰这两个符号（已核）。
   若后续有模块重命名 `$r`，需同步本模块（当前链无此风险）。
4. 与 R-107 的边界：R-107 若改数值表，本模块的折算显示会自动跟随（读的是现值）；
   若 R-107 也改同一批显示锚点，会与本模块冲突（已报备，见报告）。
5. 未改版本号、未动 build_v26n.py / CHANGELOG / localtest / deploy / srv。

锚点纪律：所有 needle 实测 count 均 ==1（基线 @2,247,976 chars）；
GATES 同时断言新形态 ==1 与旧形态 ==0，并冻结 `$r`/`ZS`/数值表/寿命直加。
"""

# --------------------------------------------------------------------------- 注入块

# 注入位置：基座 YlxwPlayer 定义之前（模块级；函数声明提升，位置仅为可读）
INJECT_BEFORE_ANCHOR = 'function YlxwPlayer() {'
INJECT_BLOCK_ID = 'yl-r106-block'

INJECT_JS = r'''
/* == YL_R106 == 永久属性加成：显示口径按当前玩家折算（只读展示；不改数值表、不改 $r/ZS） */
var YLXW_R106_KEYS = ["attack", "defense", "spirit", "physique", "speed", "maxHp"];
function YlxwR106F(k, v) {
  try {
    if (typeof v !== "number" || !(v > 0) || YLXW_R106_KEYS.indexOf(k) < 0) { return v; }
    var pl = YlxwPlayer();
    if (!pl) { return v; }
    return $r(pl, k, v);
  } catch (e) { return v; }
}
function YlxwR106Tag(k, v) {
  try { return YlxwR106F(k, v) < v ? "（按当前属性折算）" : ""; } catch (e) { return ""; }
}
function YlxwR106Note(k, v) {
  try { var f = YlxwR106F(k, v); return f < v ? "（原值 +" + v + "，按当前属性折算）" : ""; } catch (e) { return ""; }
}
'''

# --------------------------------------------------------------------------- 锚点

# 实测 count（基线 build/assets/index-v2910-20261001.js）：
#   TOAST_OLD                              = 1   （@776491 Ig 永久加成 6 连 h.push，671 chars）
#   PILL_LOOP_OLD                          = 1   （@974744 起 YLXW_PILL_FX 永久段）
#   INJECT_BEFORE_ANCHOR                   = 1   （@1285428 YlxwPlayer 定义）
#   S1（背包卡 t.）6 条 / S3（选择浮层 m.）6 条 / S2（商店 w.，转义）6 条 各 = 1
#   冻结：$r 缩放函数 / ZS / 寿命直加 / HN 表 / AN 表 均 = 1

# ① 使用后提示：折算时追加「（原值 +N，按当前属性折算）」；寿命不折算不加注
TOAST_OLD = r'''if(R.attack){const E=$r(u,"attack",R.attack);u.attack+=E,h.push(`攻击力永久 +${E}`)}if(R.defense){const E=$r(u,"defense",R.defense);u.defense+=E,h.push(`防御力永久 +${E}`)}if(R.spirit){const E=$r(u,"spirit",R.spirit);u.spirit+=E,h.push(`神识永久 +${E}`)}if(R.physique){const E=$r(u,"physique",R.physique);u.physique+=E,h.push(`体魄永久 +${E}`)}if(R.speed){const E=$r(u,"speed",R.speed);u.speed+=E,h.push(`身法永久 +${E}`)}if(R.maxHp){const E=$r(u,"maxHp",R.maxHp);u.maxHp+=E,u.hp+=E,h.push(`气血上限永久 +${E}`)}if(R.maxLifespan&&(u.maxLifespan=(u.maxLifespan??100)+R.maxLifespan,u.lifespan=Math.min(u.maxLifespan,(u.lifespan??u.maxLifespan??100)+R.maxLifespan),h.push(`最大寿命永久 +${R.maxLifespan} 年`))'''

TOAST_NEW = r'''if(R.attack){const E=$r(u,"attack",R.attack);u.attack+=E,h.push(`攻击力永久 +${E}${E<R.attack?"（原值 +"+R.attack+"，按当前属性折算）":""}`)}if(R.defense){const E=$r(u,"defense",R.defense);u.defense+=E,h.push(`防御力永久 +${E}${E<R.defense?"（原值 +"+R.defense+"，按当前属性折算）":""}`)}if(R.spirit){const E=$r(u,"spirit",R.spirit);u.spirit+=E,h.push(`神识永久 +${E}${E<R.spirit?"（原值 +"+R.spirit+"，按当前属性折算）":""}`)}if(R.physique){const E=$r(u,"physique",R.physique);u.physique+=E,h.push(`体魄永久 +${E}${E<R.physique?"（原值 +"+R.physique+"，按当前属性折算）":""}`)}if(R.speed){const E=$r(u,"speed",R.speed);u.speed+=E,h.push(`身法永久 +${E}${E<R.speed?"（原值 +"+R.speed+"，按当前属性折算）":""}`)}if(R.maxHp){const E=$r(u,"maxHp",R.maxHp);u.maxHp+=E,u.hp+=E,h.push(`气血上限永久 +${E}${E<R.maxHp?"（原值 +"+R.maxHp+"，按当前属性折算）":""}`)}if(R.maxLifespan&&(u.maxLifespan=(u.maxLifespan??100)+R.maxLifespan,u.lifespan=Math.min(u.maxLifespan,(u.lifespan??u.maxLifespan??100)+R.maxLifespan),h.push(`最大寿命永久 +${R.maxLifespan} 年`))'''

# ② 丹药/丹方药效预览（R-064 的 YLXW_PILL_FX 永久段）：永久值折算 + 原值注
PILL_LOOP_OLD = 'if (L[kk] && pf[kk]) { b.push(L[kk] + "+" + pf[kk]); }'
PILL_LOOP_NEW = ('if (L[kk] && pf[kk]) { b.push(L[kk] + "+" + YlxwR106F(kk, pf[kk]) '
                 '+ YlxwR106Note(kk, pf[kk])); }')

# ③ 三处道具详情/预览的永久加成格
ATTR_KEYS = ['attack', 'defense', 'maxHp', 'spirit', 'physique', 'speed']

# 背包卡（s1，变量 t）与选择浮层（变量 m）的标签
S1_LABEL = {'attack': '攻', 'defense': '防', 'maxHp': '气血上限',
            'spirit': '神识', 'physique': '体魄', 'speed': '身法'}
S3_LABEL = {'attack': '攻击', 'defense': '防御', 'maxHp': '气血上限',
            'spirit': '神识', 'physique': '体魄', 'speed': '身法'}
# 商店详情（变量 w）该块由 zh() 转义落盘，锚点为字面「\uXXXX」形态
S2_LABEL = {
    'attack':   r'\u6c38\u4e45\u653b\u51fb',
    'defense':  r'\u6c38\u4e45\u9632\u5fa1',
    'maxHp':    r'\u6c38\u4e45\u6c14\u8840',
    'spirit':   r'\u6c38\u4e45\u795e\u8bc6',
    'physique': r'\u6c38\u4e45\u4f53\u9b44',
    'speed':    r'\u6c38\u4e45\u8eab\u6cd5',
}


def _site_edits(var, labelmap):
    """生成某处详情格的 6 条 (key, old, new)。形态：children:["✨ {标签}永久 +",{var}.permanentEffect.{k}]"""
    out = []
    for k in ATTR_KEYS:
        lab = labelmap[k]
        old = 'children:["✨ %s永久 +",%s.permanentEffect.%s]' % (lab, var, k)
        new = ('children:["✨ %s永久 +",YlxwR106F("%s",%s.permanentEffect.%s),'
               'YlxwR106Tag("%s",%s.permanentEffect.%s)]'
               % (lab, k, var, k, k, var, k))
        out.append((k, old, new))
    return out


def _site2_edits():
    """商店详情（w，转义形态）：children:["{esc} +",w.permanentEffect.{k}]"""
    out = []
    for k in ATTR_KEYS:
        lab = S2_LABEL[k]
        old = 'children:["%s +",w.permanentEffect.%s]' % (lab, k)
        new = ('children:["%s +",YlxwR106F("%s",w.permanentEffect.%s),'
               'YlxwR106Tag("%s",w.permanentEffect.%s)]' % (lab, k, k, k, k))
        out.append((k, old, new))
    return out


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    zh = ctx['zh']
    blk = zh(INJECT_JS)

    # 与 build 侧同款自检（注入块 zh() 后必须纯 ASCII 且无禁用模式）
    bad = [c for c in blk if ord(c) > 127]
    if bad:
        raise AssertionError('R106 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])
    for w in ('iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-'):
        if w in blk:
            raise AssertionError('R106 注入块含禁用模式: %r' % w)

    # 助手注入：build 侧会在 apply() 之前按 INJECT_BEFORE_ANCHOR 自动插入；
    # _t_mod.py 不执行该步 ⇒ 此处「缺失才补插」，两侧产物一致且不重复。
    if 'function YlxwR106F(' not in p.text:
        p.insert_before(INJECT_BLOCK_ID, INJECT_BEFORE_ANCHOR, blk + '\n',
                        note='R-106 折算助手（build 自动插入；_t_mod 补插）')

    gates = []

    # ① 使用后提示加折算说明
    p.replace('r106-toast', TOAST_OLD, TOAST_NEW, expect=1,
              note='Ig 永久加成提示：折算时追加「（原值 +N，按当前属性折算）」')
    gates.append(('R106·提示已加折算说明',
                  '"（原值 +"+R.spirit+"，按当前属性折算）"', 1, '==',
                  '使用后提示解释为何低于描述'))
    gates.append(('R106·旧提示形态已清零',
                  'h.push(`神识永久 +${E}`)', 0, '==', ''))

    # ② 丹药/丹方药效预览折算
    p.replace('r106-pill-fx', PILL_LOOP_OLD, PILL_LOOP_NEW, expect=1,
              note='YLXW_PILL_FX 永久段：值改折算 + 原值注')
    gates.append(('R106·丹药预览永久值已折算',
                  'YlxwR106F(kk, pf[kk]) + YlxwR106Note(kk, pf[kk])', 1, '==', ''))
    gates.append(('R106·旧丹药预览形态已清零',
                  'b.push(L[kk] + "+" + pf[kk]); }', 0, '==', ''))

    # ③ 三处详情格折算
    for tag, var, edits in (('s1', 't', _site_edits('t', S1_LABEL)),
                            ('s3', 'm', _site_edits('m', S3_LABEL)),
                            ('s2', 'w', _site2_edits())):
        for k, old, new in edits:
            nm = 'r106-%s-%s' % (tag, k)
            p.replace(nm, old, new, expect=1,
                      note='%s 详情格 %s 显示折算 + 标注' % (tag, k))
            gates.append(('R106·%s %s 已折算' % (tag, k),
                          'YlxwR106F("%s",%s.permanentEffect.%s)' % (k, var, k), 1, '==', ''))
            gates.append(('R106·%s %s 旧值已清零' % (tag, k), old, 0, '==', ''))

    # ④ 助手自身
    gates += [
        ('R106·折算助手 F 已注入',  'function YlxwR106F(k, v) {',  1, '==', ''),
        ('R106·折算标注 Tag 已注入', 'function YlxwR106Tag(k, v) {', 1, '==', ''),
        ('R106·原值注 Note 已注入', 'function YlxwR106Note(k, v) {', 1, '==', ''),
        ('R106·可折算键表已注入',   'var YLXW_R106_KEYS = ["attack", "defense", "spirit", "physique", "speed", "maxHp"];',
         1, '==', ''),
    ]

    # ================= 冻结：缩放数学 / 数值表 / 寿命口径（一个字不动） =================
    gates += [
        ('冻结·缩放函数 $r 未动',
         '$r=(t,r,a)=>{if(!Number.isFinite(a)||a<=0)return 0', 1, '==',
         'R-106 只调用，不改数学'),
        ('冻结·境界基准函数 ZS 未动', 'ZS=(t,r)=>{', 1, '==', ''),
        ('冻结·寿命直加未动',
         'if(R.maxLifespan&&(u.maxLifespan=(u.maxLifespan??100)+R.maxLifespan', 1, '==',
         'maxLifespan 不走 $r，口径本就一致'),
        ('冻结·入账仍走 $r（未改数值）',
         'const E=$r(u,"spirit",R.spirit);u.spirit+=E', 1, '==', ''),
        ('冻结·HN 丹药表未动',
         '强体丹:{permanentEffect:{physique:20}},凝神丹:{permanentEffect:{spirit:20}}', 1, '==',
         '数值表归 R-107'),
        ('冻结·AN 灵草表（千年灵芝）未动',
         'id:"millennium-lingzhi",name:"千年灵芝",type:H.Herb', 1, '==', ''),
        # ★ 2026-10-01 集成期「约束权移交」：千年灵芝数值本属 R-107（本模块 docstring §四.4 已报备），
        #   R-107 按用户台账要求把它改成 {maxHp:400,spirit:20,physique:15,maxLifespan:3}。
        #   故本条的 needle 由「旧值未动」改为「R-107 定稿值仍在」——语义仍是「R-106 没碰数值」，
        #   只是把不变量交给下游模块的定稿形态（与 0.9.9 那批 8 条跨模块冻结串同款处理）。
        ('冻结·千年灵芝数值由 R-107 定稿（R-106 未动）',
         'permanentEffect:{maxHp:400,spirit:20,physique:15,maxLifespan:3}', 1, '==',
         '神识200→20 / 体魄150→15 / 寿命300→3；数值权归 R-107'),
        ('冻结·丹药格式化函数仍在', 'function YLXW_PILL_FX(d) {', 1, '==',
         'R-064 门禁同款：只改永久段一行，签名不动'),
        ('冻结·丹药兜底函数仍在',   'function YLXW_PILL_FXN(nm) {', 1, '==', ''),
        ('冻结·取玩家函数仍在',     INJECT_BEFORE_ANCHOR, 1, '==', 'YlxwPlayer 定义未动'),
    ]
    return gates
