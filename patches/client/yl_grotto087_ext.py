# -*- coding: utf-8 -*-
r"""
yl_grotto087_ext.py — 0.8.7 T4 洞府灵草收获修复 + T9 洞府 LV5+ 升级途径（归属 implGrotto）

接线信息（implEventsUi 落表用）
--------------------------------------------------------------------------
  模块名 grotto087；V28_MODULES 紧跟 fun086（锚定 fun086 产物形态，F1 加速串零回归）。
  apply(p, ctx)：p = yl_patch.Patcher；本模块全部为「就地替换 + 一段小注入」，
  锚点均在基座 vite 产物区（中文=字面 UTF-8 形态，与 fun086 F1/F2 同域同形态，勿转 \u）。
  注入锚：function Yk(t){  → 前插 YlxwGrottoUpgradeMaterials（模块级，洞府 modal 作用域可见）

T4 根因与修法（build-plan §2-T4）
--------------------------------------------------------------------------
  根因 = 存档 plantedHerbs[].herbId 与灵草目录 wn id 失配：handlePlantHerb 对目录外种子
  用 f(name) 伪造 `herb-<名>` 形态 id，handleHarvestHerb 只按 id 精确查 wn，查不到即
  「抱歉，找不到这个灵草的配置信息。」死锁（加速成熟后必现路径）。
  修法 = 懒兼容映射（id 精确 → 剥 herb- 前缀 → 按 herbName 查目录）+ 收获兜底
  （仍失配转灵石入账 + 日志说明，不再死锁）。兜底折算 300 灵石/个（仅失配路径触发，
  ★数值未入数值表 11 项，为 T4 自带建议值，定档可在 G14 处一并调）。
  不回改 fun086（F1 门禁串零回归）。

T9 六件（build-plan §2-T9；F6 沙盒实测归 e2e，不在本文件）
--------------------------------------------------------------------------
  F1 升级列表不再整行过滤境界不达标级 → 带 locked 标记进列表（灰卡：名称/境界差/灵石差）
  F2 「🎉 恭喜！已达到最高等级」只在 T.level>=10（真满级）出现
  F3 L9/L10 材料门槛（YlxwGrottoUpgradeMaterials：九叶芝草×3+万年灵乳×2 / 混沌青莲×2+万年仙草×2，
     ★数值=设计案建议锚值，待《数值表-T9T10.md》#2 定档回填；校验+扣减，不足 toast 逐项盘点）
  F4 升级成功 toast 与总览页追加灵田联动行（产出 +等级% / 可开垦块数 / 每日催熟次数；
     口径与服务端 farmcore 常量一致：#3 +1%/级、#4 slot4/5/6=L5/L7/L9、#6 3+1 次/2 级；
     ★定档时两端同步改）
  F5 「请先出售当前洞府」死引用清理（sellGrotto 全产物 0 处）→「洞府只可逐级升级，不可降级。」
  ★ 同名陷阱：洞府 modal 融合 key xw:"farm" ≠ 仙务页签 farm=灵田；本模块只碰前者区域，
  与 yl_farm087_ext.py（YLXW_COMP.farm 覆盖）零锚区交集。

门禁计数清单（供 dryrun_087 落表；接线人 implEventsUi）
--------------------------------------------------------------------------
  Pr.filter(w=>w.level>g).map(w=>({...w,locked:            ==1（旧 if(w.level<=g)return!1 ==0）
  T.level>=10?"🎉 恭喜！已达到最高等级"                     ==1（已达到最高等级 总数仍 ==1）
  __lk=!!g.locked / disabled:!q||__lk / 🔒 需境界           各==1
  function YlxwGrottoUpgradeMaterials(                     ==1（调用 YlxwGrottoUpgradeMaterials(M) ==1）
  inventory:__inv,                                         ==1
  灵田联动：产出 +（字面）/ 灵田联动（字面）                 各==1
  请先出售当前洞府 ==0；洞府只可逐级升级，不可降级 ==1
  抱歉，找不到这个灵草的配置信息。 ==0；的配置信息缺失 ==1；||wn.find(Q=>Q.name===N.herbName) ==1
  fun086 冻结回归：Math.max(Br.minCost,...).toLocaleString() ==1；Br={dailyLimit:10,...} ==1
  Pr=[{level:1,name:"简陋洞府"                              ==1（等级表未动）
"""
import re

# --------------------------------------------------------------------------- 注入（模块级小函数；中文经 ctx['zh'] 转义）

INJECT_JS = r'''
/* ===== yl-0.8.7 T9-F3: 洞府 L9/L10 升级材料门槛（★数值=设计案建议锚值，待《数值表-T9T10.md》#2 定档回填） =====
   与聚灵阵改造（dy）共享传说/仙品灵草池，给洞府灵草园产出开第二个消耗口（一次性消耗）。 */
function YlxwGrottoUpgradeMaterials(lv) {
  if (lv === 9) return [{ name: "九叶芝草", quantity: 3 }, { name: "万年灵乳", quantity: 2 }];
  if (lv === 10) return [{ name: "混沌青莲", quantity: 2 }, { name: "万年仙草", quantity: 2 }];
  return null;
}

'''

# --------------------------------------------------------------------------- T9-F1/F2 升级页签

G1_OLD = 'const h=O.useMemo(()=>{const g=T.level,q=fe.indexOf(a.realm);return Pr.filter(w=>{if(w.level<=g)return!1;if(w.realmRequirement){const A=fe.indexOf(w.realmRequirement);return q>=A}return!0})},[T.level,a.realm]),'
G1_NEW = 'const h=O.useMemo(()=>{const g=T.level;return Pr.filter(w=>w.level>g).map(w=>({...w,locked:!!w.realmRequirement&&fe.indexOf(a.realm)<fe.indexOf(w.realmRequirement)}))},[T.level,a.realm]),'

G2_OLD = 'children:T.level===0?"暂无可用洞府":"🎉 恭喜！已达到最高等级"'
G2_NEW = 'children:T.level>=10?"🎉 恭喜！已达到最高等级":"暂无可升级的洞府"'

# --------------------------------------------------------------------------- T9-F1 锁定灰卡（卡片四件 + 境界徽标）

G3_OLD = 'h.map(g=>{const q=a.spiritStones>=g.cost,w=g.cost-a.spiritStones;'
G3_NEW = 'h.map(g=>{const q=a.spiritStones>=g.cost,w=g.cost-a.spiritStones,__lk=!!g.locked;'

G4_OLD = '${q?"border-stone-700 hover:border-mystic-gold hover:shadow-mystic-gold/20":"border-stone-700/50 opacity-75"}'
G4_NEW = '${!__lk&&q?"border-stone-700 hover:border-mystic-gold hover:shadow-mystic-gold/20":"border-stone-700/50 opacity-75"}'

G5_OLD = 'children:["等级 ",g.level]})]}),'
G5_NEW = 'children:["等级 ",g.level]}),__lk?e.jsxs("span",{className:"text-xs px-2 py-1 rounded border text-red-300 bg-red-900/30 border-red-500/50",children:["🔒 需境界 ",g.realmRequirement," · 当前 ",a.realm]}):g.realmRequirement?e.jsx("span",{className:"text-xs px-2 py-1 rounded border text-green-300 bg-green-900/20 border-green-500/50",children:"✓ 境界已达标"}):null]}),'

G6_OLD = 'onClick:()=>l(g.level),disabled:!q,'
G6_NEW = 'onClick:()=>l(g.level),disabled:!q||__lk,'

G7_OLD = '${q?"bg-mystic-gold text-stone-900 hover:bg-yellow-600":"bg-stone-700 text-stone-500 cursor-not-allowed"}'
G7_NEW = '${!__lk&&q?"bg-mystic-gold text-stone-900 hover:bg-yellow-600":"bg-stone-700 text-stone-500 cursor-not-allowed"}'

G8_OLD = '!q&&e.jsxs("p",{className:"text-xs text-red-400 text-right",children:["还差 ",w.toLocaleString()," 灵石"]})'
G8_NEW = '!q&&!__lk&&e.jsxs("p",{className:"text-xs text-red-400 text-right",children:["还差 ",w.toLocaleString()," 灵石"]}),__lk&&e.jsx("p",{className:"text-xs text-red-400 text-right",children:"境界未达，升级后即刻解锁本档收益"})'

# --------------------------------------------------------------------------- T9-F3 L9/L10 材料门槛（校验 + 扣减）

G9_OLD = 'if(h.spiritStones<N.cost){const A=N.cost-h.spiritStones;return a(`灵石不足！需要 ${N.cost.toLocaleString()} 灵石，当前拥有 ${h.spiritStones.toLocaleString()} 灵石，还差 ${A.toLocaleString()} 灵石。`,"danger"),h}d(E);'
G9_NEW = ('if(h.spiritStones<N.cost){const A=N.cost-h.spiritStones;return a(`灵石不足！需要 ${N.cost.toLocaleString()} 灵石，'
          '当前拥有 ${h.spiritStones.toLocaleString()} 灵石，还差 ${A.toLocaleString()} 灵石。`,"danger"),h}'
          'const __mq=YlxwGrottoUpgradeMaterials(M);'
          'if(__mq){const __miss=[];'
          'for(const __it of __mq){const __own=h.inventory.find(__b=>!__b.locked&&__b.type===H.Herb&&__b.name===__it.name),__n=__own&&__own.quantity||0;'
          'if(__n<__it.quantity)__miss.push(`${__it.name}（需 ${__it.quantity}，有 ${__n}）`)}'
          'if(__miss.length>0){const __msg=`材料不足！升级【${N.name}】还需：${__miss.join("、")}。请先通过洞府灵草园种植或历练收集。`;'
          'return a(__msg,"danger"),l&&l({text:__msg,type:"danger"}),h}}d(E);')

G10_OLD = 'const g=h.spiritStones-N.cost,q=E===0?"购买":"升级",'
G10_NEW = ('let __inv=h.inventory;'
           'if(__mq)__inv=__inv.map(__b=>{const __it=__mq.find(__q=>__q.name===__b.name);'
           'return __it?{...__b,quantity:__b.quantity-__it.quantity}:__b}).filter(__b=>__b.quantity>0);'
           'const g=h.spiritStones-N.cost,q=E===0?"购买":"升级",')

G11_OLD = ',"gain"),{...h,spiritStones:g,grotto:{...R,level:M,'
G11_NEW = ',"gain"),{...h,inventory:__inv,spiritStones:g,grotto:{...R,level:M,'

# --------------------------------------------------------------------------- T9-F4 灵田联动收益展示

G12_OLD = 'N.autoHarvest&&w.push("支持自动收获"),a('
G12_NEW = ('N.autoHarvest&&w.push("支持自动收获"),'
           'w.push("灵田联动：产出 +" + M + "%、可开垦 " + (M>=9?6:M>=7?5:M>=5?4:3) + " 块、每日催熟 " + (3+Math.floor(M/2)) + " 次"),a(')

G13_OLD = '"% 完成"]})]})]})]}),($==null?void 0:$.autoHarvest)&&'
G13_NEW = ('"% 完成"]})]})]})]}),T.level>0&&e.jsx("div",{className:"bg-ink-900 p-4 rounded-lg border border-stone-700 shadow-lg",'
           'children:e.jsxs("div",{className:"flex items-center justify-between gap-2 flex-wrap",children:['
           'e.jsx("span",{className:"text-stone-300 text-sm font-bold",children:"灵田联动"}),'
           'e.jsxs("span",{className:"text-stone-400 text-xs",children:["产出 +",T.level,"% · 可开垦 ",T.level>=9?6:T.level>=7?5:T.level>=5?4:3," 块田 · 每日催熟 ",3+Math.floor(T.level/2)," 次"]})]})}),'
           '($==null?void 0:$.autoHarvest)&&')

# --------------------------------------------------------------------------- T4 收获懒兼容映射 + 兜底转灵石

G14_OLD = 'const _=wn.find(Q=>Q.id===N.herbId);if(!_)return a("抱歉，找不到这个灵草的配置信息。","danger"),h;'
G14_NEW = ('const _=wn.find(Q=>Q.id===N.herbId)||wn.find(Q=>Q.id===String(N.herbId==null?"":N.herbId).replace(/^herb-/,""))||wn.find(Q=>Q.name===N.herbName);'
           'if(!_){const __sv=Math.max(100,N.quantity*300);E.splice(M,1);'
           'const __msg=`⚠️ 灵草【${N.herbName}】的配置信息缺失，已按 ${__sv.toLocaleString()} 灵石折算回收（每个 300 灵石）。`;'
           'return a(__msg,"warning"),l&&l({text:__msg,type:"warning"}),'
           '{...h,spiritStones:h.spiritStones+__sv,grotto:{...R,plantedHerbs:E,lastHarvestTime:k}}}')

# --------------------------------------------------------------------------- T9-F5 死引用清理

G15_OLD = '无法降级洞府！如需更换洞府，请先出售当前洞府。'
G15_NEW = '洞府只可逐级升级，不可降级。'


EDITS = [
    ('T9-F1 升级列表带锁定标记',      G1_OLD, G1_NEW),
    ('T9-F2 真满级判定',              G2_OLD, G2_NEW),
    ('T9-F1a 灰卡变量',               G3_OLD, G3_NEW),
    ('T9-F1b 灰卡边框',               G4_OLD, G4_NEW),
    ('T9-F1c 境界徽标',               G5_OLD, G5_NEW),
    ('T9-F1d 置灰按钮',               G6_OLD, G6_NEW),
    ('T9-F1e 按钮配色',               G7_OLD, G7_NEW),
    ('T9-F1f 缺口文案分流',           G8_OLD, G8_NEW),
    ('T9-F3a 材料校验',               G9_OLD, G9_NEW),
    ('T9-F3b 材料扣减',               G10_OLD, G10_NEW),
    ('T9-F3c 回执带扣减后背包',       G11_OLD, G11_NEW),
    ('T9-F4a 升级 toast 联动行',      G12_OLD, G12_NEW),
    ('T9-F4b 总览联动行',             G13_OLD, G13_NEW),
    ('T4   收获懒兼容映射+兜底',      G14_OLD, G14_NEW),
    ('T9-F5 降级文案死引用清理',      G15_OLD, G15_NEW),
]


def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块，含 fun086）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('grotto087 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # 0) 模块级材料门槛函数（洞府 modal 各组件同作用域可见）
    p.insert_before('grotto087-materials-fn', 'function Yk(t){', blk + '\n',
                    expect=1, note='注入 YlxwGrottoUpgradeMaterials（T9-F3）')

    # 1) 就地替换（基座字面 UTF-8 区）
    for name, old, new in EDITS:
        p.replace(name, old, new, expect=1)

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- T9 F1/F2 ----
        ('T9·升级列表带锁定',           'Pr.filter(w=>w.level>g).map(w=>({...w,locked:', 1, '==', ''),
        ('T9·旧整行过滤清零',           'if(w.level<=g)return!1', 0, '==', ''),
        ('T9·真满级判定',               'T.level>=10?"🎉 恭喜！已达到最高等级"', 1, '==', '字面 UTF-8 区，门禁同形态'),
        ('T9·满级文案总数不变',         '已达到最高等级', 1, '==', '只改判定不改文案'),
        ('T9·灰卡变量',                 '__lk=!!g.locked', 1, '==', ''),
        ('T9·灰卡置灰按钮',             'disabled:!q||__lk', 1, '==', ''),
        ('T9·境界徽标',                 '🔒 需境界 ', 1, '==', ''),
        ('T9·缺口文案分流',             '境界未达，升级后即刻解锁本档收益', 1, '==', ''),
        # ---- T9 F3 ----
        ('T9·材料门槛函数',             'function YlxwGrottoUpgradeMaterials(', 1, '==', ''),
        ('T9·材料校验调用',             'YlxwGrottoUpgradeMaterials(M)', 1, '==', ''),
        ('T9·材料扣减',                 'inventory:__inv,', 1, '==', ''),
        # ---- T9 F4 ----
        ('T9·升级 toast 联动行',        '灵田联动：产出 +', 1, '==', ''),
        ('T9·总览联动行',               '"灵田联动"', 1, '==', ''),
        # ---- T9 F5 ----
        ('T9·死引用清零',               '请先出售当前洞府', 0, '==', 'sellGrotto 全产物 0 处'),
        ('T9·新降级文案',               '洞府只可逐级升级，不可降级。', 1, '==', ''),
        # ---- T4 ----
        ('T4·失配死锁报错清零',         '抱歉，找不到这个灵草的配置信息。', 0, '==', '改兜底转灵石'),
        ('T4·懒兼容映射（按名查目录）',  '||wn.find(Q=>Q.name===N.herbName)', 1, '==', ''),
        ('T4·兜底转灵石',               '的配置信息缺失，已按 ', 1, '==', ''),
        # ---- 冻结回归（fun086 / 基线）----
        ('冻结·fun086 加速费用串',      'Math.max(Br.minCost,Math.ceil(I/6e4)*Br.costPerMinute).toLocaleString()', 1, '==', 'fun086 F1 零回归'),
        ('冻结·Br 常量',                'Br={dailyLimit:10,costPerMinute:100,minCost:1000}', 1, '==', 'fun086 冻结域'),
        ('冻结·Pr 等级表未动',          'Pr=[{level:1,name:"简陋洞府"', 1, '==', 'L1~L10 数据齐全，表不是缺口'),
        ('冻结·handleUpgradeGrotto 接线', 'handleUpgradeGrotto', 9, '==', '定义+接线总数与基线同'),
    ]
    return gates
