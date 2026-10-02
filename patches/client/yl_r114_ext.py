# -*- coding: utf-8 -*-
r"""
yl_r114_ext.py — R-114 历练收获日志：修「修为 0 · 灵石 0」全 0 行 + 参照打坐扩充内容

需求原文（台账 R-114，逐字）
--------------------------------------------------------------------------
    「历练收获：修为 0 · 灵石 0   以及收获也参照自动打坐，内容多一点。」

附图 R-114-1.png：日志出现「历练收获：修为 0 · 灵石 0」——两项全 0，明显异常。
附图 R-114-2.png（参照格式）：
    · 「本次自动历练 33 秒：修为 +1,243 · 灵石 +1,822 · 历练 7 次」（R-105）
    · 「本次打坐 4 秒：修为 +63 · 灵石 +24 · 顿悟 0 次 · 平均每跳 修为 +21 / 灵石 +8」（R-023）

==============================================================================
一、改前取证（基线 build/assets/index-v2911-20261001.js，md5
    5b30fcda29901f8b81358c9490c0ad49，2,085,078 chars，只读）
==============================================================================

【1】「历练收获」这条日志的唯一产生点
--------------------------------------------------------------------------
全文 `历练收获` 只出现 1 处（原始形态 0 次；在 adv097 注入块内以
`\u5386\u7ec3\u6536\u83b7` 转义形态存在）：

  @528067  `function YlxwAdvResultLog(res, advType, addLog) {`（yl_adv097_ext.py 注入）
       var label = advType === "secret_realm" ? "\u79d8\u5883\u6536\u83b7"
         : advType === "sect_challenge" ? "\u5b97\u95e8\u6311\u6218\u6536\u83b7"
         : "\u5386\u7ec3\u6536\u83b7";
       var de = Math.floor(Number(res.expChange) || 0);
       var ds = Math.floor(Number(res.spiritStonesChange) || 0);
       var dh = Math.floor(Number(res.hpChange) || 0);
       var parts = ["\u4fee\u4e3a " + (de > 0 ? "+" : "") + de,          ← 无条件第 1 项
                    "\u7075\u77f3 " + (ds > 0 ? "+" : "") + ds];          ← 无条件第 2 项
       if (dh) parts.push("\u6c14\u8840 " + (dh > 0 ? "+" : "") + dh);
       addLog("\ud83d\udcca " + label + "\uff1a" + parts.join("  \u00b7 "), res.eventColor || "normal");

  唯一调用点 @1863553（Fg 内）：
       `YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),t.lifespanChange&&d(…`
  （`YlxwAdvResultLog(t,m,d)` 全文 1 次；`YlxwAdvAcc(t)` 为 R-105 advend105 追加。）

  ⇒ 该函数**恒定**把 修为/灵石 两项塞进 parts 数组，不看是否为 0。

【2】为什么会出现「修为 0 · 灵石 0」——**不是读错字段，是该类事件本来就 0 收获**
--------------------------------------------------------------------------
历练事件生成器 `hw(t)`（NORMAL 池，@1862xxx 前的 `function hw(t){`，类型权重数组末位
即 `"lottery"`）里，有两类事件把 exp/stones 双双写死为 0：

  ① 抽奖券事件（NORMAL 池内，权重 1/37）@555184：
       `return{...d,story:at(u,t),hpChange:0,expChange:0,spiritStonesChange:0,`
       `eventColor:"gain",lotteryTicketsChange:Ge(t,1,11,450)}`
     ⇒ 唯一收益是 `lotteryTicketsChange`，exp/stones/hp 全 0。
  ② 天地之魄（合道挑战）事件 @553531：
       `return{...d,story:at(f,t),hpChange:0,expChange:0,spiritStonesChange:0,`
       `eventColor:"danger",adventureType:"dao_combining_challenge",heavenEarthSoulEncounter:u.id}`
     ⇒ 同样 0/0/0。

  另有一批事件只给修为、不给灵石（灵石 0），例如顿悟事件 @535171/@536338
  `hpChange:0,expChange:Ge(t,50,130,150),spiritStonesChange:0` ⇒ 显示「修为 +N · 灵石 0」。

  基线事件基对象 `vy()` @529007：
       `{story:"",hpChange:0,expChange:0,spiritStonesChange:0,eventColor:"normal",adventureType:"normal"}`
     ⇒ `adventureType` 是结果对象的**真实字段**（默认 "normal"，奇遇池为 "lucky"）。

  ⇒ **根因一句话**：R-089(a) 的 `YlxwAdvResultLog` 只读 `expChange`/`spiritStonesChange`
    两个字段并**无条件**输出，于是「本类事件恰好不给修为/灵石」时，整行退化成
    「修为 0 · 灵石 0」——没有任何有效信息。R-089 的注入块注释也自证了这一设计
    （「exp + stones always printed」）。

【3】可用的真实数据源（只列结果对象上**确实存在**的字段，均已 grep 到赋值点）
--------------------------------------------------------------------------
  · expChange / spiritStonesChange / hpChange（已在用）
  · itemObtained           单件掉落对象 `{name,type,description,rarity,…}`（@531219 等）
  · itemsObtained          掉落数组；Fg 内消费方式逐字为
                           `const R=[...t.itemsObtained||[]];t.itemObtained&&R.push(t.itemObtained),`
                           `R.forEach(k=>{k!=null&&k.name&&d(\`获得物品: …${k.name}\`)})`（@1863900）
  · lotteryTicketsChange   抽奖券增量（@555184）
  · reputationChange       声望增量（@538945 等）
  · adventureType          事件类型；奇遇池写 "lucky"（@556605）
  · heavenEarthSoulEncounter  天地之魄遭遇（@553531）
  仅取上述字段；**未新增/未编造任何字段**，也**未改** Pc() 的入账数学。

【4】打坐日志（丰富度参照，R-023 medlog）@608000 起
--------------------------------------------------------------------------
  `Be.getState().addLog("\ud83e\uddd8 \u672c\u6b21\u6253\u5750 " + YlxwMedDur(ms)`
  `  + "\uff1a\u4fee\u4e3a +" + de.toLocaleString()`
  `  + " \u00b7 \u7075\u77f3 +" + ds.toLocaleString()`
  `  + " \u00b7 \u987f\u609f " + a.insight + " \u6b21" …`
  ⇒ 打坐行 = 时长 + 修为 + 灵石 + 顿悟次数 + 平均每跳（多字段、` · ` 分隔）。
    本模块沿用同款「多字段 + ` · ` 分隔」风格，把历练收获行扩充为
    `修为 / 灵石 / 气血 / 掉落 / 抽奖券 / 声望 / 奇遇 / 天地之魄挑战`。

==============================================================================
二、改后行为
==============================================================================
每次历练结算仍**只写一行**（不新增第二行，与 R-089/R-105 的「不刷屏」纪律一致），
但内容改为「本次**真实发生**的收益」：

  · 修为 / 灵石 / 气血：**仅在非 0 时出现** ⇒ 彻底消除「修为 0 · 灵石 0」。
  · 掉落：本次 `itemsObtained` ∪ `itemObtained` 的名字，`、` 连接。
  · 抽奖券：`lotteryTicketsChange` ≠ 0 时显示 ⇒ 抽奖券事件不再空行。
  · 声望：`reputationChange` ≠ 0 时显示。
  · 奇遇：`adventureType === "lucky"` 时标注。
  · 天地之魄挑战：`heavenEarthSoulEncounter` 存在时标注。
  · 若以上全无（例如合道挑战入口这类 0 收益事件）⇒ 兜底写「无收益」，行不消失
    （保留 R-089「每次结算必写一行」的初衷，同时不再输出全 0 假数据）。

示例（炼气 L1）：
    普通战斗   📊 历练收获：修为 +36 · 灵石 +332 · 气血 -12 · 掉落 青狼内丹
    顿悟事件   📊 历练收获：修为 +107
    抽奖券事件 📊 历练收获：抽奖券 +7          ← 原为「修为 0 · 灵石 0」
    合道挑战   📊 历练收获：天地之魄挑战        ← 原为「修为 0 · 灵石 0」

实现（2 处就地替换，零注入块、零新增文件、不动存档 schema、不动 Pc 入账）：
  patch ① `r114-parts` ：`var parts = [修为…, 灵石…];` → `var parts = [];` +
                         `if (de) parts.push(…); if (ds) parts.push(…);`
                         （两条 push 的**表达式子串逐字保留**，见第三节）
  patch ② `r114-enrich`：在 `if (dh) parts.push(…);` 之后追加扩充块 + 兜底项。

==============================================================================
三、★ 跨模块门禁的逐字保留（本模块无权改别人的文件）
==============================================================================
`patches/client/yl_adv097_ext.py`（R-089，注入 `YlxwAdvResultLog` 的模块）含 3 条门禁
直接断言本函数**体内**的子串，必须逐字保留、且计数仍为 1：
    ('R89·日志恒定含修为', r'"\u4fee\u4e3a " + (de > 0 ? "+" : "") + de', 1)
    ('R89·日志恒定含灵石', r'"\u7075\u77f3 " + (ds > 0 ? "+" : "") + ds', 1)
    ('R89·日志气血仅非 0 追加', 'if (dh) parts.push(', 1)
    ('R97·成果日志函数已定义', 'function YlxwAdvResultLog(res, advType, addLog)', 1)
    ('R89·成果日志已接管', 'YlxwAdvResultLog(t,m,d)', 1)
    ('R97·提升函数不碰气血', 'o0.hpChange', 0)      ← 本模块**不得**引入 `o0.hpChange`
处置：本模块把这**两条表达式**从「数组字面量项」改成「`if (…) parts.push(表达式)`」，
      **表达式本身一字不动** ⇒ 上述 needle 计数仍为 1；`if (dh) parts.push(` 逐字保留；
      全程不出现 `o0.`。`patches/client/yl_advend105_ext.py`（R-105）的
      ('冻结·adv097 日志函数仍在', 'function YlxwAdvResultLog(res, advType, addLog) {', 1)
      与 ('冻结·adv097 调用点逐字保留', 'YlxwAdvResultLog(t,m,d)', 1) 亦均未触碰。
⇒ 本模块**不产生**跨模块门禁冲突（唯一被改的串是 adv097 的 `var parts = [ … ];` 数组字面量，
  而该串不是任何模块的门禁 needle；已全仓 grep `parts.push` / `var parts` 复核）。

==============================================================================
四、风险点
==============================================================================
1. 「掉落」会与 Fg 紧随其后的独立行「获得物品: 【传说】xxx」形成一次信息重复。
   这是「内容多一点」的直接代价；若嫌重复，删掉 `_ylNames` 那一段即可（单点）。
2. 事件基对象 `vy()` 已带 `adventureType:"normal"`，但**默认兜底结果**
   （`V={story:…,hpChange:0,expChange:Math.floor(10*(1+…)),spiritStonesChange:0,eventColor:"normal"}`）
   不带该字段 ⇒ 奇遇标注只对 `adventureType:"lucky"` 的事件生效，符合预期。
3. `_ylDrop/_ylNames/_ylLot/_ylRep` 为函数内 `var`，作用域封闭，不污染全局；
   注入块内无 fetch / 无 V28_BAN_PATTERNS 模式（本模块 INJECT_JS 为空串）。
4. 未改版本号、未动 build_v26n.py / localtest/*.py / deploy_v28/* / srv/index_v28.ts /
   CHANGELOG* / EXPECT_0811.env / 任何已有 yl_*_ext.py。
5. ★ 附图 R-114-1.png 的 emoji 写作「🏮」，但基线里该行前缀是 `\ud83d\udcca`（📊）；
   U+1F3EE(🏮) 在全仓（含 patches/ 与 srv/）计数为 0。本模块**不改 emoji**（避免无谓改动），
   仅按「历练收获：修为 0 · 灵石 0」这一**全文唯一**串定位到 `YlxwAdvResultLog`。

锚点纪律：2 处锚点实测 count 均为 1；所有 needle 均对基线逐字核过。
"""

# --------------------------------------------------------------------------- 锚点（实测 count==1）

# ① 无条件的「修为 / 灵石」数组字面量（逐字取自基线 @528470 起，含换行与 17 空格续行缩排）
PARTS_OLD = (
    r'    var parts = ["\u4fee\u4e3a " + (de > 0 ? "+" : "") + de,' + '\n'
    r'                 "\u7075\u77f3 " + (ds > 0 ? "+" : "") + ds];'
)
# 改为「非 0 才入列」：两条 push 的表达式子串与 adv097 门禁逐字一致
PARTS_NEW = (
    '    var parts = [];\n'
    r'    if (de) parts.push("\u4fee\u4e3a " + (de > 0 ? "+" : "") + de);' + '\n'
    r'    if (ds) parts.push("\u7075\u77f3 " + (ds > 0 ? "+" : "") + ds);'
)

# ② 气血项（adv097 门禁串 `if (dh) parts.push(` 必须逐字保留）→ 其后追加扩充块
DH_OLD = r'    if (dh) parts.push("\u6c14\u8840 " + (dh > 0 ? "+" : "") + dh);'
DH_NEW = DH_OLD + '\n' + (
    r'''    /* R-114: enrich with the settlement's OTHER real gains. Zero fields are
       omitted so an exp/stones-less event never prints a "0 + 0" line. */
    var _ylDrop = [];
    if (res.itemsObtained && res.itemsObtained.length) _ylDrop = _ylDrop.concat(res.itemsObtained);
    if (res.itemObtained) _ylDrop.push(res.itemObtained);
    var _ylNames = _ylDrop.filter(function (x) { return x && x.name; }).map(function (x) { return x.name; });
    if (_ylNames.length) parts.push("\u6389\u843d " + _ylNames.join("\u3001"));
    var _ylLot = Math.floor(Number(res.lotteryTicketsChange) || 0);
    if (_ylLot) parts.push("\u62bd\u5956\u5238 " + (_ylLot > 0 ? "+" : "") + _ylLot);
    var _ylRep = Math.floor(Number(res.reputationChange) || 0);
    if (_ylRep) parts.push("\u58f0\u671b " + (_ylRep > 0 ? "+" : "") + _ylRep);
    if (res.adventureType === "lucky") parts.push("\u5947\u9047");
    if (res.heavenEarthSoulEncounter) parts.push("\u5929\u5730\u4e4b\u9b44\u6311\u6218");
    if (!parts.length) parts.push("\u65e0\u6536\u76ca");'''
)

# 纯就地替换，无注入块（_t_mod.py / build 侧对空串无自检副作用）
INJECT_JS = ''


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    # 自检：替换串必须真的变了（防手滑写成恒等）
    if PARTS_OLD == PARTS_NEW or 'if (de) parts.push(' not in PARTS_NEW:
        raise AssertionError('r114 锚点异常：修为/灵石未改为「非 0 才入列」')
    if DH_OLD == DH_NEW or '_ylLot' not in DH_NEW:
        raise AssertionError('r114 锚点异常：气血项后未追加扩充块')
    # 自检：adv097 门禁的表达式子串必须仍在（逐字保留）
    for need in (r'"\u4fee\u4e3a " + (de > 0 ? "+" : "") + de',
                 r'"\u7075\u77f3 " + (ds > 0 ? "+" : "") + ds',
                 'if (dh) parts.push('):
        if need not in (PARTS_NEW + DH_NEW):
            raise AssertionError('r114 破坏 adv097 门禁 needle: %r' % need)
    if 'o0.' in (PARTS_NEW + DH_NEW):
        raise AssertionError('r114 不得引入 o0.*（adv097 门禁 o0.hpChange == 0）')

    # ① 修为/灵石 改为「非 0 才入列」（消除「修为 0 · 灵石 0」）
    p.replace('r114-parts', PARTS_OLD, PARTS_NEW, expect=1,
              note='修为/灵石由无条件数组项改为 if(de)/if(ds) 条件入列；表达式子串逐字保留')

    # ② 追加扩充块（掉落 / 抽奖券 / 声望 / 奇遇 / 天地之魄 + 空行兜底）
    p.replace('r114-enrich', DH_OLD, DH_NEW, expect=1,
              note='气血项后追加真实收益字段 + 全空兜底「无收益」')

    return [
        # ================= 新形态（==1） =================
        ('R114·修为非 0 才入列',
         r'if (de) parts.push("\u4fee\u4e3a " + (de > 0 ? "+" : "") + de);', 1, '==',
         '★ 修 0 值 bug：修为 0 时不再输出「修为 0」'),
        ('R114·灵石非 0 才入列',
         r'if (ds) parts.push("\u7075\u77f3 " + (ds > 0 ? "+" : "") + ds);', 1, '==',
         '★ 修 0 值 bug：灵石 0 时不再输出「灵石 0」'),
        ('R114·空 parts 初始化为数组',
         '    var parts = [];\n    if (de) parts.push(', 1, '==',
         '★ 该两行连排形态全文唯一（`var parts = [];` 单串在别处也有，故取连排）'),
        ('R114·掉落字段已读', 'var _ylDrop = [];', 1, '==',
         'itemObtained ∪ itemsObtained（真实字段，取自 Fg 同款消费方式）'),
        ('R114·掉落已展示', r'parts.push("\u6389\u843d " + _ylNames.join("\u3001"));', 1, '==',
         '名字以「、」连接，不显示数量（掉落对象仅保证 name）'),
        ('R114·抽奖券已读', 'Math.floor(Number(res.lotteryTicketsChange) || 0)', 1, '==',
         '抽奖券事件（NORMAL 池 1/37）的唯一收益'),
        ('R114·抽奖券已展示',
         r'if (_ylLot) parts.push("\u62bd\u5956\u5238 " + (_ylLot > 0 ? "+" : "") + _ylLot);',
         1, '==', '原为「修为 0 · 灵石 0」'),
        ('R114·声望已读', 'Math.floor(Number(res.reputationChange) || 0)', 1, '==',
         'reputationChange（Pc 入账用字段，无独立日志行）'),
        ('R114·声望已展示',
         r'if (_ylRep) parts.push("\u58f0\u671b " + (_ylRep > 0 ? "+" : "") + _ylRep);',
         1, '==', ''),
        ('R114·奇遇已标注',
         r'if (res.adventureType === "lucky") parts.push("\u5947\u9047");', 1, '==',
         '奇遇池事件标 adventureType:"lucky"（@556605）'),
        ('R114·天地之魄已标注',
         r'if (res.heavenEarthSoulEncounter) parts.push("\u5929\u5730\u4e4b\u9b44\u6311\u6218");',
         1, '==', '0/0/0 事件（@553531）不再退化成空行'),
        ('R114·全空兜底不写假数据',
         r'if (!parts.length) parts.push("\u65e0\u6536\u76ca");', 1, '==',
         '保留「每次结算必写一行」，但不再输出全 0 假数据'),

        # ================= 旧形态（==0） =================
        ('R114·旧无条件数组已清零', PARTS_OLD, 0, '==',
         '「修为 0 · 灵石 0」的产生源（无条件两项）必须消失'),

        # ================= 冻结：adv097（R-089）的门禁 needle 逐字保留 =================
        ('冻结·adv097 日志函数签名', 'function YlxwAdvResultLog(res, advType, addLog) {',
         1, '==', 'adv097 + advend105 双门禁'),
        ('冻结·adv097 调用点', 'YlxwAdvResultLog(t,m,d)', 1, '==',
         'adv097 + advend105 双门禁'),
        ('冻结·adv097 修为表达式', r'"\u4fee\u4e3a " + (de > 0 ? "+" : "") + de', 1, '==',
         '本模块只把它从数组项改为 push 实参，表达式一字不动'),
        ('冻结·adv097 灵石表达式', r'"\u7075\u77f3 " + (ds > 0 ? "+" : "") + ds', 1, '==', ''),
        ('冻结·adv097 气血项', 'if (dh) parts.push(', 1, '==', ''),
        ('冻结·adv097 写日志调用', r'addLog("\ud83d\udcca " + label', 1, '==',
         '只读+写日志；emoji 未改'),
        ('冻结·adv097 提升函数不碰气血', 'o0.hpChange', 0, '==',
         '本模块不得引入 o0.*'),
        ('冻结·adv097 倍率常量未动', 'var YLXW_ADV_STONE_MUL_R97 = 3;', 1, '==',
         'R-089 面，本模块只动日志格式'),
        ('冻结·adv097 修为倍率未动', 'var YLXW_ADV_EXP_MUL_R97 = 1.2;', 1, '==', ''),
        ('冻结·adv097 标签三分支未动',
         r'advType === "secret_realm" ? "\u79d8\u5883\u6536\u83b7"', 1, '==',
         '秘境/宗门/历练 三种标签未动'),

        # ================= 冻结：advend105（R-105）的面 =================
        ('冻结·R105 汇总函数仍在', 'function YlxwAdvSession(on) {', 1, '==', ''),
        ('冻结·R105 累计函数仍在', 'function YlxwAdvAcc(res) {', 1, '==', ''),
        ('冻结·R105 累计挂点仍在', 'YlxwAdvResultLog(t,m,d),YlxwAdvAcc(t),', 1, '==',
         '本模块只在日志函数体内改动，调用点未碰'),
        ('冻结·R105 汇总行仍在', r'add("\ud83d\uddfa \u672c\u6b21\u81ea\u52a8\u5386\u7ec3 "', 1, '==',
         'R-105 的会话汇总行是另一条，本模块不动'),

        # ================= 冻结：medlog（R-023）的面 =================
        ('冻结·R023 打坐日志仍在', r'Be.getState().addLog("\ud83e\uddd8', 1, '==',
         '丰富度参照物，本模块不碰'),

        # ================= 冻结：入账数学与相邻需求面（一个字不动） =================
        ('冻结·Pc 修为入账未动', 'S.exp=Math.max(0,t.exp+(r.expChange||0))', 1, '==',
         '本模块只读结果对象，不改入账'),
        ('冻结·Pc 灵石入账未动', 'S.spiritStones=Math.max(0,t.spiritStones+(r.spiritStonesChange||0))',
         1, '==', ''),
        ('冻结·Pc 掉落消费未动',
         'const R=[...t.itemsObtained||[]];t.itemObtained&&R.push(t.itemObtained)', 1, '==',
         'Fg 的独立「获得物品」行未动'),
        ('冻结·R44 倍率常量未动', 'var YLXW_ADV_STONE_R44 = 0.85;', 1, '==', ''),
        ('冻结·R42 历练冷却仍 10s', '}finally{c(!1),d(10)}', 1, '==', 'R-117 2026-10-02 调 10s（属主侧放宽）'),
        ('冻结·历练修为硬钳未动', '_ylCapPct=.25', 1, '==', ''),
    ]
