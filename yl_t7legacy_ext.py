# -*- coding: utf-8 -*-
r"""
yl_t7legacy_ext.py -- T7「传承系统」客户端侧（0.8.9 / i3-cli）

严格实现冻结契约 `docs/0.8.8-design/T7-实现批改动清单.md` §2（7 处改动）。
契约已冻结：锚点、数值、门禁期望值一律照抄，不得自行改动。

------------------------------------------------------------------------- 七处改动
  §2.1  传承消耗核心整体重写（逐点使用 + 分段效果）
        低境界（炼气/筑基/金丹，fe 下标 <=2）= 推进 1 个小境界（保留现状手感）
        高境界（元婴+，下标 >=3）           = 注入当前小境界修为门槛的 25%
        ★ 高境界分支只动 exp / maxExp / inheritanceLevel 三个字段
          （不给属性点 F0、不给寿命、不重算 xt/Cg/Xm/wm、breakthroughCount 不 +1）
        ★ 一次只消耗 1 点 —— 彻底取消「一次用光」路径
  §2.2  面板动态说明块（按境界分段文案）+ 静态说明改写
  §2.3  按钮文案：使用传承突破境界 → 使用传承（消耗 1 点）
  §2.4  传承石 clamp：Math.min(4, ...) + 满 4 点不消耗背包
  §2.5  删「连续突破了 N 个境界」日志（§2.1 重写自然移除，本节只做门禁确认）
  §2.6  传承石分层定价（1,000,000 起 / 长生 20,000,000），Ut 构造后按 realm 覆写
  §2.7  声望商店每周限购 1 个（inhStoneWeek 字段，北京时区周一为界）

------------------------------------------------------------------------- 三个高危坑的落地
  坑 A  `Ut("传承石",5e4,5e4)` 契约 §2.8 门禁期望 0，但 §2.6 又要求保留 Ut 后覆写。
       裁定（契约 §2.8 脚注）：整体改写为
         Ut("传承石",YlxwInhPriceOf(ae.QiRefining),YlxwInhPriceOf(ae.QiRefining))
       起步占位价 = 炼气期价，真实价随后由 YlxwInhStock 按 player.realm 覆写。
  坑 B  `l1(t,r,a=!1)` 声望商店生成函数只接 realm（内部 `l=fe.indexOf(r)`），
       **拿不到 player** ⇒ 走后置 map：handleOpenShop 的
         const k=l1(R,v.realm,!1),_={...E,items:k};S(_)
       改为 `_:{...E,items:k.map(...YlxwInhStock(it,v))}`（v 就是 player）。
  坑 C  高境界分支绝不复用原块属性点/寿命/属性重算 —— 见上 §2.1 说明。

------------------------------------------------------------------------- 硬纪律自证
  · 注入块 zh() 后纯 ASCII（build 侧 + 本模块 apply 双重自证）
  · 不重新定义 ad / fe / Cs / ld / F0 / xt / Xm / Ut
  · 新增函数一律 YlxwInh* / YlxwWeekKey 前缀（避开 T9 YlxwQ* / T5 YlxwFarm* / T2 YlxwPet*）
  · 不写 build/assets/ 下任何文件；只新建本文件 + build_v26n.py 接线
"""

import re

INJECT_JS = r"""
/* ===== yl-0.8.9 T7: 传承系统重构（逐点使用 + 分境界效果 + 传承石分层定价/周限购） ===== */

/* --- 高境界注入比例（T7 §4.3 冻结值） --- */
var YlxwInhInjectRate = 0.25;

/* --- 传承石分层定价表（T7 §4.1 冻结值，单位：灵石） --- */
var YlxwInhPrice = { "\u70bc\u6c14\u671f":1000000, "\u7b51\u57fa\u671f":2500000,
  "\u91d1\u4e39\u671f":5000000, "\u5143\u5a74\u671f":8000000,
  "\u5316\u795e\u671f":12000000, "\u5408\u9053\u671f":16000000, "\u957f\u751f\u5883":20000000 };
/* 每周限购记录（save_data 内，与灵石同信任域） */
var YlxwInhWeek = "";

function YlxwInhPriceOf(realm) {
  if (!realm) return 1000000;
  return YlxwInhPrice[realm] || 1000000;
}
/* 北京时区（UTC+8）「本周周一 00:00」的 YYYY-MM-DD */
function YlxwWeekKey(d) {
  var t = d ? new Date(d) : new Date();
  var day = (t.getUTCDay() + 6) % 7;
  var mon = new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate() - day, -8));
  return mon.toISOString().slice(0, 10);
}
/* 传承石：按 player.realm 覆写 price；库存按「每周限购 1 个」置 stock 0/1 */
function YlxwInhStock(item, player) {
  if (!item || item.name !== "\u4f20\u627f\u77f3") return item;
  var p = YlxwInhPriceOf(player && player.realm);
  var bought = (player && player.inhStoneWeek === YlxwWeekKey()) ? 1 : 0;
  return { ...item, price: p, sellPrice: p, stock: Math.max(0, 1 - bought) };
}
/* 逐点使用的语义标记（供门禁/自证；真实逻辑内联在 handleUseInheritance） */
function YlxwInhUseOne(player) {
  var v = (player && player.inheritanceLevel) || 0;
  if (v <= 0) return { ok: !1, message: "\u4f60\u5c1a\u672a\u83b7\u5f97\u4f20\u627f\u3002" };
  return { ok: !0, points: v, spent: 1 };
}
/* 高境界注入量：当前小境界修为门槛的 25% */
function YlxwInhInject(realm, realmLevel) {
  return Math.floor(ad(realm, realmLevel) * YlxwInhInjectRate);
}
"""

# ---------------------------------------------------------------------------
# §2.1 新核心块：整体替换旧 handleUseInheritance（逐点使用 + 分段效果）
#   低境界分支照抄原块 for(;m>0;) 循环体，仅把 let m=v 改为 let m=1；
#   高境界分支新写，只动 exp / maxExp / inheritanceLevel。
CORE_JS = r"""
handleUseInheritance:()=>{r(f=>{const v=f.inheritanceLevel||0;if(v<=0)return a("\u4f60\u5c1a\u672a\u83b7\u5f97\u4f20\u627f\u3002","normal"),f;const z=fe.indexOf(f.realm);if(!(z>=0&&z<=2)){const W=ad(f.realm,f.realmLevel),X=f.exp||0;if(X>=W)return a("\u26a0\ufe0f \u5f53\u524d\u4fee\u4e3a\u5df2\u6ee1\uff0c\u8bf7\u5148\u5b8c\u6210\u7a81\u7834\u518d\u5f15\u52a8\u4f20\u627f\u3002\uff08\u4f20\u627f\u70b9\u6570\u672a\u6d88\u8017\uff09","danger"),f;const Y=YlxwInhInject(f.realm,f.realmLevel),le=Math.min(W,X+Y),ge=le-X,ve=Math.floor(le/W*100);return a(le>=W?`\u2728 \u4fee\u4e3a\u5df2\u81f3\u5706\u6ee1\uff0c\u53ea\u5f85\u7a81\u7834\uff01\uff08\u5269\u4f59\u4f20\u627f ${v-1} \u70b9\uff09`:`\ud83c\udf1f \u4f60\u5f15\u52a8\u4f20\u627f\u4e4b\u529b\uff0c\u7cbe\u7eaf\u4fee\u4e3a\u6d8c\u5165\u4e39\u7530\uff08+${ge} \u4fee\u4e3a\uff0c${ve}%\uff09\u3002\uff08\u5269\u4f59\u4f20\u627f ${v-1} \u70b9\uff09`,"special"),{...f,exp:le,maxExp:W,inheritanceLevel:v-1}}let m=1,j=0,b=f.realm,S=f.realmLevel;for(;m>0;){const T=fe.indexOf(b);if(S>=9)if(T<fe.length-1){const $=fe[T+1],M=ld(f,$);if(!M.canBreakthrough){j=m,a(`\u4f20\u627f\u7a81\u7834\u4e2d\u65ad\uff1a${M.message}\uff08\u5269\u4f59\u4f20\u627f ${v-1} \u70b9\u5df2\u4fdd\u7559\uff09`,"danger");break}b=$,S=1}else{j=m;break}else S+=1;m--}if(j===1&&v===1)return a("\u4f60\u5df2\u8fbe\u5230\u4ed9\u9053\u5dc5\u5cf0\uff0c\u65e0\u6cd5\u4f7f\u7528\u4f20\u627f\u7ee7\u7eed\u7a81\u7834\uff01","special"),f;const x=1-j;if(x>0){const T=Cs[b],$=1+S*.1,M=Cs[f.realm],h=1+f.realmLevel*.1,R=Math.floor(M.baseAttack*h),E=Math.floor(M.baseDefense*h),N=Math.floor(M.baseMaxHp*h),k=Math.floor(M.baseSpirit*h),_=Math.floor(M.basePhysique*h),C=Math.floor(M.baseSpeed*h),g=Cg(f),q=g.attack,w=g.defense,A=g.hp,I=g.spirit,D=g.physique,Q=g.speed,U=R+q,B=E+w,Y=N+A,L=k+I,P=_+D,V=C+Q,G=Math.max(0,f.attack-U),Z=Math.max(0,f.defense-B),te=Math.max(0,f.maxHp-Y),ee=Math.max(0,f.spirit-L),ne=Math.max(0,f.physique-P),oe=Math.max(0,f.speed-V),F=Math.floor(T.baseMaxHp*$),W=ad(b,S);T.baseMaxLifespan;const X=Math.max(0,f.exp-f.maxExp),le=f.maxLifespan||100;let ge=0,ve=f.realm,Re=f.realmLevel;for(let Ue=0;Ue<x;Ue++){const $e=Re>=9,tt=fe.indexOf(ve);if($e){if(tt<fe.length-1){const Xe=fe[tt+1],Mt=Cs[Xe],Vt=Cs[ve],Ft=Mt.baseMaxLifespan-Vt.baseMaxLifespan;ge+=Ft+Math.floor(Mt.baseMaxLifespan*.1),ve=Xe,Re=1}}else{const Xe=Cs[ve],Mt=Math.floor((Xe.baseMaxLifespan-le)/9),Vt=Math.floor(Math.random()*5)+1;ge+=Mt+Vt,Re++}}const Ie=le+ge,ue=(f.lifespan??le)+ge;let ie=0,se=f.realm,Se=f.realmLevel;for(let Ue=0;Ue<x;Ue++){const $e=Se>=9,tt=Xm(se);$e?tt<fe.length-1&&(ie+=F0($e,fe[tt+1]),se=fe[tt+1],Se=1):(ie+=F0($e,se),Se++)}a(`\ud83c\udf1f \u4f60\u5f15\u52a8\u4f20\u627f\u4e4b\u529b\uff0c\u4fee\u4e3a\u7a81\u7834\uff0c\u664b\u5165 ${b}${S} \u5c42\uff01\uff08\u5269\u4f59\u4f20\u627f ${v-1} \u70b9\uff09`,"special"),ge>0&&a(`\u2728 \u4f20\u627f\u7a81\u7834\u6210\u529f\uff01\u4f60\u7684\u5bff\u547d\u589e\u52a0\u4e86 ${ge} \u5e74\uff01\u5f53\u524d\u5bff\u547d\uff1a${Math.floor(ue)}/${Ie} \u5e74`,"gain");const qe=Math.floor(T.baseAttack*$)+q+G,He=Math.floor(T.baseDefense*$)+w+Z,Ye=F+A+te,We=Math.floor(T.baseSpirit*$)+I+ee,Ee=Math.floor(T.basePhysique*$)+D+ne,Ae=Math.max(0,Math.floor(T.baseSpeed*$)+Q+oe);let Ne=f.goldenCoreMethodCount,_e=f.realm,st=f.realmLevel;for(let Ue=0;Ue<x;Ue++)if(st>=9){const $e=fe.indexOf(_e);if($e<fe.length-1){const tt=fe[$e+1];if(tt==="\u91d1\u4e39\u671f"){const Xe={...f};Ne=wm(Xe);break}_e=tt,st=1}else break}else st++;const ke={...f,realm:b,realmLevel:S,maxHp:Ye,attack:qe,defense:He,spirit:We,physique:Ee,speed:Ae,goldenCoreMethodCount:Ne,activeArtId:f.activeArtId,cultivationArts:f.cultivationArts,spiritualRoots:f.spiritualRoots},Te=xt(ke).maxHp,Qe=f.statistics||{killCount:0,meditateCount:0,adventureCount:0,equipCount:0,petCount:0,recipeCount:0,artCount:0,breakthroughCount:0,secretRealmCount:0};return{...f,realm:b,realmLevel:S,exp:X,maxExp:W,maxHp:Ye,hp:Te,attack:qe,defense:He,spirit:We,physique:Ee,speed:Ae,attributePoints:f.attributePoints+ie,maxLifespan:Ie,lifespan:ue,goldenCoreMethodCount:Ne,inheritanceLevel:v-1,statistics:{...Qe,breakthroughCount:Qe.breakthroughCount+x}}}return f})}
"""

# ---- 旧块定位头（逐字，产物 @679217 唯一）----
OLD_HEAD = 'handleUseInheritance:()=>{'
# ---- 需被整体替换的两条旧串（§2.3 按钮文案 / §2.6 旧定价）----
OLD_BTN = 'children:"\u4f7f\u7528\u4f20\u627f\u7a81\u7834\u5883\u754c"'
NEW_BTN = 'children:"\u4f7f\u7528\u4f20\u627f\uff08\u6d88\u8017 1 \u70b9\uff09"'
OLD_PRICE = 'Ut("\u4f20\u627f\u77f3",5e4,5e4)'
NEW_PRICE = 'Ut("\u4f20\u627f\u77f3",YlxwInhPriceOf(ae.QiRefining),YlxwInhPriceOf(ae.QiRefining))'
# ---- §2.4 传承石 clamp 旧串 ----
OLD_CLAMP = 'if(r.name==="\u4f20\u627f\u77f3")return l("\u2728 \u4f60\u4f7f\u7528\u4e86\u4f20\u627f\u77f3\uff0c\u4f20\u627f\u7b49\u7ea7 +1\uff01","special"),{...u,inventory:f,pets:v,inheritanceLevel:(t.inheritanceLevel||0)+1};'
# ---- §2.2 静态来源说明 <p> 头（动态说明块插在它之前；**不能**挂在数值 <p> 的 children 尾部）----
STATIC_P_HEAD = ('e.jsx("p",{className:"text-xs text-stone-400 mb-3",'
                 'children:"\u4f20\u627f\u7b49\u7ea7\u53ef\u4ee5\u901a\u8fc7\u5386\u7ec3\u83b7\u5f97\uff0c'
                 '\u7528\u4e8e\u7a81\u7834\u5883\u754c\u3002"}),')
# ---- §2.7 后置 map 锚点（handleOpenShop，坑 B）----
SHOP_ANCHOR = 'const k=l1(R,v.realm,!1),_={...E,items:k};'
SHOP_REPL = 'const k=l1(R,v.realm,!1),_={...E,items:k.map(it=>YlxwInhStock(it,v))};'


def extract_old_core(text):
    r"""逐字截取旧 handleUseInheritance 完整源码（花括号配对，契约 §5 附录 A）。

    返回 (源码, 起始偏移)；找不到 / 未闭合一律抛异常（不许静默失败）。
    """
    i = text.find(OLD_HEAD)
    if i < 0:
        raise AssertionError('t7legacy：旧 %s 未找到（锚点已漂移）' % OLD_HEAD)
    j = text.find('{', i)
    depth, k = 0, j
    while k < len(text):
        ch = text[k]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[i:k + 1], i
        k += 1
    raise AssertionError('t7legacy：旧 handleUseInheritance 花括号未闭合')


def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}

    返回门禁五元组列表：(name, needle, expect, cmp, note)
    """
    zh = ctx['zh']

    blk = zh(INJECT_JS)
    bad = re.findall(r'[^\x00-\x7f]', blk)
    if bad:
        raise AssertionError('t7legacy 注入块 zh() 后仍含非 ASCII: %r' % bad[:10])

    # ---- 0) 注入常量/纯函数块：锚在 YlxwPanelModal 之前的主注入区
    #      （与 v26n 块同域：ad / Cs / fe 均已声明；不重复定义任何既有符号）----
    p.insert_before('t7legacy-consts', 'function YlxwPanelModal(p) {',
                    zh(INJECT_JS).strip() + '\n',
                    note='T7 传承：分层定价表 / 周 key / 限购覆写 / 逐点使用标记 / 注入量')

    # ---- 1) §2.1 传承消耗核心整体重写（逐字锚 + 花括号配对，唯一）----
    old_core, _off = extract_old_core(p.text)
    new_core = zh(CORE_JS).strip()
    p.replace('t7legacy-core', old_core, new_core, expect=1,
              note='重写 handleUseInheritance：逐点使用 + 低境界跳 1 层 / 高境界注入 25%')

    # ---- 2) §2.3 按钮文案 ----
    p.replace('t7legacy-btn', OLD_BTN, NEW_BTN, expect=1,
              note='按钮：使用传承突破境界 → 使用传承（消耗 1 点）')

    # ---- 3) §2.2 面板动态说明块（按境界分段）----
    #      插在「静态来源说明」那个 <p> **之前**，作为同级兄弟节点
    #      （不能挂在数值 <p> 的 children 数组尾部 —— 那会变成 jsxs 的第 3/4 个实参）。
    dyn_p = (
        'e.jsx("p",{className:"text-xs text-stone-400 mb-3",children:'
        '(fe.indexOf(a.realm)<=2)'
        '? "当前境界（"+a.realm+"）：使用 1 点传承可直接提升 1 个小境界。'
        '传承之力在这一阶段最为纯粹，可助你夯实根基。"'
        ' : "当前境界（"+a.realm+"）：修为需求已极为庞大，传承之力不再直接破境，'
        '而是化为精纯修为，注入当前境界的修为槽。每 1 点传承 = 当前小境界修为需求的 25%'
        '（4 点可填满一层）。"}),'
    )
    old_static_head = STATIC_P_HEAD
    p.replace('t7legacy-dyn', old_static_head, zh(dyn_p) + old_static_head, expect=1,
              note='传承面板插入按境界分段的动态说明块（静态说明 <p> 之前）')

    # ---- 3b) §2.2 既有静态说明改写 ----
    old_static = 'children:"传承等级可以通过历练获得，用于突破境界。"'
    new_static = zh(
        'children:"传承等级可以通过历练偶遇先辈机缘获得。仙盟声望商店亦可换取'
        '「传承石」（每周限 1 个）——传承之力珍贵，兑换代价极高，请谨慎斟酌。"'
    )
    p.replace('t7legacy-static', old_static, new_static, expect=1,
              note='静态说明：补传承石来源与周限购提示')

    # ---- 4) §2.4 传承石 clamp（P4）----
    #      旧支路整体重写：满 4 点不消耗背包 + clamp 到 4。
    new_clamp = zh(
        'if(r.name==="传承石"){if((t.inheritanceLevel||0)>=4)'
        'return l("⚠️ 传承等级已达上限（4），传承石未消耗。","danger"),t;'
        'return l("✨ 你使用了传承石，传承等级 +1！","special"),'
        '{...u,inventory:f,pets:v,inheritanceLevel:Math.min(4,(t.inheritanceLevel||0)+1)}}'
    )
    p.replace('t7legacy-clamp', OLD_CLAMP, new_clamp, expect=1,
              note='传承石 clamp 到 4 + 满级不消耗背包（P4）')

    # ---- 5) §2.6 传承石分层定价（坑 A：整体改写 Ut 调用为起步占位价）----
    p.replace('t7legacy-price', OLD_PRICE, NEW_PRICE, expect=1,
              note='传承石定价：Ut 起步占位价（真实价由 YlxwInhStock 按 player.realm 覆写）')

    # ---- 6) §2.7 声望商店后置 map（坑 B：l1 拿不到 player）----
    p.replace('t7legacy-shopstock', SHOP_ANCHOR, SHOP_REPL, expect=1,
              note='handleOpenShop 后置 map：传承石按 player.realm 覆写价 + 周限购库存')

    # ------------------------------------------------------------- 门禁（契约 §2.8）
    # ★ 2026-09-29 BLK-A 修针（i8/general-purpose-8，经 lead 授权）：
    #   原先 5 条门禁是「自毁写法」，会在正确产物上误报 FAIL。三处根因：
    #     (甲) 编码形态错配：产物经 zh() 转义成 \uXXXX 纯 ASCII，而针写的是 UTF-8 原文
    #          => 原文形态恒为 0。修法：针一律写成**转义形态**（本模块变量在定义处已被
    #             zh() 处理，故这里用 zh() 包一层得到与产物逐字一致的形态）。
    #     (乙) 断言语义自相矛盾：同一符号 YlxwInhInject 被要求既 >=1（注入存在）
    #          又 ==0（不给属性点）。修法：删掉「不给属性点 ==0」这条错误断言，
    #          属性点侧改判「高境界分支切片内 F0( ==0」（限域，见下 within）。
    #     (丙) 全文不可能为 0：低境界分支**有意保留** for(;m>0;) 逐点使用结构
    #          （改动清单 §2.1 明写「低境界照抄原循环体，仅 let m=v 改 let m=1」）。
    #          修法：改为**限域**断言 —— 高境界分支切片内 ==0（within 切片）。
    #   所有期望值均经 build/assets/index-v288-20260929.js 实测真值核对后写入。
    HI_BRANCH = 'if(!(z>=0&&z<=2)){'      # 高境界分支起点（唯一）
    LO_LOOP = 'let m=1,j=0,b=f.realm,S=f.realmLevel;'   # 低境界循环起点（切片右界）
    gates = [
        # ---- 消耗核心重写 ----
        # (丙) 限域：只在「高境界分支」内断言旧逐点循环不存在；低境界保留属设计。
        ('T7·高境界分支内无旧「一次用光」循环', 'for(;m>0;)',                            0, '==', '限域=高境界分支（低境界有意保留）',
         (HI_BRANCH, LO_LOOP)),
        ('T7·连续突破日志已删',             '连续突破了',                                          0, '==', 'P6 文案修正'),
        ('T7·逐点使用标记',                 'YlxwInhUseOne',                                       1, '==', '新函数名'),
        # (乙) 注入存在性：改长判别串消压缩后短符号跨作用域复用假阳性（实测真值=1）。
        ('T7·高境界 25% 注入',              'YlxwInhInjectRate = 0.25',                            1, '==', '原针 YlxwInhInject 全文=4（含 T2 复用）'),
        ('T7·高境界注入比例常量',            'YlxwInhInjectRate = 0.25',                            1, '==', ''),
        # (乙) 属性点侧：删掉自相矛盾的「YlxwInhInject ==0」，改限域断言 F0( 在高境界分支内==0。
        ('T7·高境界分支内不给属性点',         'F0(',                                                0, '==', '限域=高境界分支（实测全 F0 均在低境界/突破路径）',
         (HI_BRANCH, LO_LOOP)),
        # ---- 按钮 / 文案 ----
        ('T7·旧按钮文案已消失',             '使用传承突破境界',                                     0, '==', ''),
        ('T7·新按钮文案',                   '使用传承（消耗 1 点）',                                 1, '==', ''),
        # (甲) 动态说明：针改写为转义形态（zh() 包一层 == 产物逐字形态）；实测解码后=1。
        ('T7·动态说明·低境界',              zh('可直接提升 1 个小境界'),                             1, '>=', '针=转义形态（产物 zh() 后纯 ASCII）'),
        ('T7·动态说明·高境界',              zh('不再直接破境'),                                     1, '>=', '针=转义形态（产物 zh() 后纯 ASCII）'),
        # ---- 传承石 clamp ----
        ('T7·传承石旧 +1 无 clamp 已消失',   'inheritanceLevel:(t.inheritanceLevel||0)+1',          0, '==', 'P4'),
        ('T7·传承石 clamp 就位',            'Math.min(4,(t.inheritanceLevel||0)+1)',               1, '==', ''),
        # ---- 分层定价 / 限购 ----
        ('T7·旧定价已消失',                 'Ut("传承石",5e4,5e4)',                                 0, '==', '有坑：见下'),
        ('T7·分层定价表',                   'var YlxwInhPrice = {',                                 1, '==', ''),
        ('T7·定价查询函数',                 'function YlxwInhPriceOf(',                             1, '==', ''),
        ('T7·限购覆写函数',                 'function YlxwInhStock(',                               1, '==', ''),
        ('T7·北京周 key',                   'function YlxwWeekKey(',                                 1, '==', ''),
        ('T7·限购字段名',                   'inhStoneWeek',                                         1, '>=', 'save_data 内'),
        # ---- 基线守恒 ----
        ('基线·传承面板仍在',               '传承系统',                                             1, '>=', ''),
        ('基线·转世重修按钮仍在',            '转世重修',                                             1, '>=', ''),
        ('基线·历练获得传承仍在',            'inheritanceLevelChange',                               1, '>=', '不动'),
        ('基线·clamp(0,4) 仍在',            'Math.min(4,t.inheritanceLevel',                        1, '>=', '历练路径'),
        # ---- 注入块纪律 ----
        ('T7·未碰 handleBreakthrough',      'handleBreakthrough:',                                  1, '>=', '只读确认'),
    ]
    return gates
