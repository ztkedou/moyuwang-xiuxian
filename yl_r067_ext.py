# -*- coding: utf-8 -*-
r"""
yl_r067_ext.py — R-067 功法大任务：①全表五行分类（金木水火土）+ 灵根亲和接通人物属性加成
②扩充 55 部功法（黄每属性+5 / 玄+3 / 地+2 / 天+1，高品阶递减）

需求原文（需求台账_进行中.md R-067）
--------------------------------------------------------------------------
  「一是给现有的功法根据属性分类，现有的技能类型也增加属性的分类，金木水火土这些的，
    对应到人物这些属性的相应加成里。二大量增加功法数量，……每一个品阶，最低的品阶
    按照每个属性最少5本来扩充。高品阶扩充的数量再递减。具体扩充的数量以及数值你详细
    策划一下。可以网上搜一搜其他类型的设定。」

侦察结论（build/assets/index-v28117-20261001.js，2026-10-01）
--------------------------------------------------------------------------
  · 功法定义表 `is`（恰 1 次，`is=[{id:"art-basic-breath"`），共 **82 部**：
    黄 17 / 玄 19 / 地 18 / 天 28。
  · 五行属性 = 功法字段 `spiritualRoot`（"metal|wood|water|fire|earth"），现状仅 32 部有，
    50 部缺（含吐纳法/铁皮功/诛仙四剑/混沌归元功等）。
  · 「对应到人物属性的加成」**游戏本体已有现成机制**，本模块不发明公式：
      go=(t,r)=>t.spiritualRoot?1+(r[t.spiritualRoot]||0)*.005:1
    玩家灵根 spiritualRoots={metal..earth}（0~100，角色面板已显示金木水火土），
    每 1 点对应灵根 = 该功法效果 +0.5%，消费点：
      Cg() 全部已修功法属性汇总（攻/防/血/灵/体/速 × go×成长×递减）；
      xt() 激活心法的属性面板；bd() 心法修炼效率；领悟 toast。
    ⇒ 补齐 50 部 spiritualRoot 后，全表 137 部自动进入该加成体系 —— 需求①的加成落点。
  · 技能侧：战斗技能 100% 来自本体 og（9 部手写）+ GS 生成器，R-016（yl_gongfa_ext.py）
    已把技能类型展示进卡片并冻结战斗侧零改动 ⇒ 五行标识做在功法阁 UI（徽标+筛选+说明），
    **不改 GS/QS/og**（遵守 R-016 冻结面）。
  · numbal（yl_numbal_ext.py）的 YlxwArtBalance() 启动时按「品级×境界」格预算**重算**全部
    功法 effects（5 桶+expRate），带 spiritualRoot 的功法预算 ×1.15（YlxwArtGate）。
    ⇒ 新功法 effects 只需「侧重形态」正确，终值由同一预算体系自动对齐同档均值；
      本模块注入块置于 `function GS(` 之前，先于 numbal 执行（is 表 264k < GS 720k），
      50 部补 root 后 numbal 统一按 ×1.15 补偿 —— 同格倍率一致，无离散。
  · 获取途径自动生效：机缘领悟池（is.filter 不带 sectId 全量进池）、功法阁「批量修习」
    自动购买、战斗 GS 生成技能；宗门功法阁走独立 SECT_GF_CATALOG（R-066 面，互不影响）。
  · 服务端 index_v28.ts 无 art- 白名单（gongfa 表是另一套「心法六卷」系统）⇒ 纯客户端，无
    srv_patch。

本模块动作（1 注入 + 6 替换，全部锚点 expect=1 且侦察 count==1）
--------------------------------------------------------------------------
  1. 注入块（insert_before `function GS(`）：YLXW_ELEM_* 表 + YlxwElemOf/Init/Label/Cls +
     50 部旧功法五行分派表（语义分派，已有 root 的 32 部不动）+ YlxwElemInit() 自启动。
  2. is 表尾（`speed:1e4}}],og={"art-thunder-sword"` 前）插入 **55 部新功法**
     （id 前缀 art-wx-，含 spiritualRoot； realmRequirement 黄/玄=QiRefining、
     地=GoldenCore、天=NascentSoul，与同品阶现状一致）。
  3. 功法阁 z4：新增第五筛选维「五行筛选：」（金/木/水/火/土，配色对齐灵根面板）；
     state/deps/谓词三件套；卡片品阶徽标后挂五行徽标；intro 补五行亲和说明。
  4. 门禁：本模块改动 ~70 条 + 冻结（R-016 面 7 / numbal 面 6 / 战斗面 5 / 既有 root
     字节 5）——改数值的冻结证明：YlxwElemInit 只在运行时**补缺失字段**，
     既有 32 部 root 的字节形态（9/4/6/8/5）不变，numbal/战斗锚恒 1。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 不碰：GS/QS/og/PS/go 公式、YlxwGongfa*（R-016）、YlxwArt*（numbal）、
    build_v26n.py、deploy_v28/、srv/、既有 32 部功法的 spiritualRoot 字面量。
  · 注入块经 build 侧 zh() 转义为纯 ASCII；无 iframe/postMessage/XMLHttpRequest/
    auth_token/X-YL-/fetch。
  · 锚点唯一（本模块 + 下游门禁双保险）；替换 expect 全部显式。
"""

# --------------------------------------------------------------------------
# 55 部新功法（id 前缀 art-wx-；字段序与 is 表现有功法一致）
# (id, 名称, type, 品阶, 描述, realm, cost, root, effects JS)
#   realm: Q=ae.QiRefining / G=ae.GoldenCore / N=ae.NascentSoul
#   effects 初值 = 同品阶形态量级；终值由 numbal YlxwArtBalance 按格预算重算
# --------------------------------------------------------------------------
_NEW_ARTS_DEF = [
    # ---------------- 黄品 25 部（每属性 +5）----------------
    ('art-wx-metal-h1', '庚金诀', 'mental', '黄', '口诵庚金真言，锐气凝于眉心，微增修炼速度与攻击。', 'Q', 900, 'metal', '{expRate:.12,attack:10}'),
    ('art-wx-metal-h2', '白虹剑法', 'body', '黄', '剑出如白虹贯日，锋锐无匹。', 'Q', 1000, 'metal', '{attack:14,speed:4}'),
    ('art-wx-metal-h3', '锋芒锻体功', 'body', '黄', '以金气淬炼筋骨皮膜，拳掌生芒。', 'Q', 850, 'metal', '{attack:12,defense:6}'),
    ('art-wx-metal-h4', '秋水剑气诀', 'body', '黄', '剑气如秋水般清冽，割金断玉。', 'Q', 1200, 'metal', '{attack:16}'),
    ('art-wx-metal-h5', '破甲锥劲', 'body', '黄', '劲力凝成锥形，专破护体罡气。', 'Q', 1100, 'metal', '{attack:13,speed:5}'),
    ('art-wx-wood-h1', '青木长生功', 'mental', '黄', '青木之气滋养四肢百骸，生机绵长。', 'Q', 800, 'wood', '{expRate:.15,hp:30}'),
    ('art-wx-wood-h2', '万木回春诀', 'mental', '黄', '身如古木，伤势易复，根基日深。', 'Q', 950, 'wood', '{expRate:.18,defense:8}'),
    ('art-wx-wood-h3', '藤蔓缠身功', 'body', '黄', '灵力化作藤蔓护体，柔韧难破。', 'Q', 750, 'wood', '{defense:10,hp:25}'),
    ('art-wx-wood-h4', '灵木锻体功', 'body', '黄', '以灵木之精锻体，气血充盈。', 'Q', 900, 'wood', '{hp:35,defense:8}'),
    ('art-wx-wood-h5', '春风化雨诀', 'mental', '黄', '温润如春风化雨，滋养神识。', 'Q', 850, 'wood', '{expRate:.1,spirit:5}'),
    ('art-wx-water-h1', '玄冰护体', 'body', '黄', '寒冰凝甲护体，水火难侵。', 'Q', 800, 'water', '{defense:12}'),
    ('art-wx-water-h2', '弱水诀', 'mental', '黄', '取弱水三千之意，柔能克刚。', 'Q', 850, 'water', '{expRate:.15,spirit:4}'),
    ('art-wx-water-h3', '碧波剑法', 'body', '黄', '剑走轻灵，如碧波荡漾，绵里藏针。', 'Q', 1000, 'water', '{attack:12,speed:6}'),
    ('art-wx-water-h4', '寒泉洗髓功', 'mental', '黄', '寒泉洗髓，脱胎换骨，悟性渐开。', 'Q', 1100, 'water', '{expRate:.2,hp:20}'),
    ('art-wx-water-h5', '流云水袖', 'body', '黄', '灵力如水袖舒卷，攻守自如。', 'Q', 900, 'water', '{defense:8,speed:6}'),
    ('art-wx-fire-h1', '赤焰掌', 'body', '黄', '掌心凝赤焰，触之即燃。', 'Q', 900, 'fire', '{attack:15}'),
    ('art-wx-fire-h2', '离火心经', 'mental', '黄', '存想离火入心，真气如炎升腾。', 'Q', 1000, 'fire', '{expRate:.14,attack:8}'),
    ('art-wx-fire-h3', '火鸦术', 'body', '黄', '掷出火鸦三只，啄敌于瞬息。', 'Q', 950, 'fire', '{attack:11,speed:7}'),
    ('art-wx-fire-h4', '焚身锻体功', 'body', '黄', '以微火焚身，痛楚中筋骨愈坚。', 'Q', 1000, 'fire', '{attack:12,hp:25}'),
    ('art-wx-fire-h5', '朱明吐纳诀', 'mental', '黄', '朱明之气入体，血行如奔马。', 'Q', 850, 'fire', '{expRate:.12,speed:4}'),
    ('art-wx-earth-h1', '厚土功', 'body', '黄', '引厚土之气护体，稳如泰山。', 'Q', 750, 'earth', '{defense:12,hp:30}'),
    ('art-wx-earth-h2', '黄庭诀', 'mental', '黄', '黄庭之内，土气养身，根基牢靠。', 'Q', 850, 'earth', '{expRate:.13,defense:8}'),
    ('art-wx-earth-h3', '磐石护体', 'body', '黄', '体覆磐石之肤，刀剑难伤。', 'Q', 800, 'earth', '{defense:15}'),
    ('art-wx-earth-h4', '大地之力', 'body', '黄', '借大地之力出拳，势沉力重。', 'Q', 1000, 'earth', '{attack:10,defense:10}'),
    ('art-wx-earth-h5', '息壤心法', 'mental', '黄', '息壤生生不息，气血自复。', 'Q', 900, 'earth', '{expRate:.1,hp:35}'),
    # ---------------- 玄品 15 部（每属性 +3）----------------
    ('art-wx-metal-x1', '庚金剑气诀', 'body', '玄', '庚金剑气离弦，可裂顽石。', 'Q', 4000, 'metal', '{attack:55}'),
    ('art-wx-metal-x2', '金乌啄日', 'body', '玄', '身法如金乌掠空，一啄破防。', 'Q', 4500, 'metal', '{attack:45,speed:20}'),
    ('art-wx-metal-x3', '锐金淬魂诀', 'mental', '玄', '以金气淬炼神魂，杀伐果断。', 'Q', 5000, 'metal', '{expRate:.32,attack:25}'),
    ('art-wx-wood-x1', '苍木罡气', 'body', '玄', '苍木罡气缠身，御敌于外。', 'Q', 3800, 'wood', '{defense:35,hp:120}'),
    ('art-wx-wood-x2', '长青不老功', 'mental', '玄', '长青之气驻体，容颜不老，气血自生。', 'Q', 4200, 'wood', '{expRate:.35,hp:150}'),
    ('art-wx-wood-x3', '枯木逢春诀', 'mental', '玄', '绝境逢生，防御中暗藏生机。', 'Q', 4000, 'wood', '{expRate:.3,defense:25}'),
    ('art-wx-water-x1', '北溟真水诀', 'mental', '玄', '北溟真水入体，神识如渊。', 'Q', 4500, 'water', '{expRate:.36,spirit:25}'),
    ('art-wx-water-x2', '寒潭映月', 'body', '玄', '心如寒潭映月，静极生明。', 'Q', 4200, 'water', '{defense:30,spirit:18}'),
    ('art-wx-water-x3', '逆水行舟剑', 'body', '玄', '剑势如逆水行舟，愈挫愈勇。', 'Q', 4800, 'water', '{attack:40,speed:22}'),
    ('art-wx-fire-x1', '炎爆烧天诀', 'body', '玄', '炎爆升空，灼烧一片。', 'Q', 4600, 'fire', '{attack:60}'),
    ('art-wx-fire-x2', '三昧真火经', 'mental', '玄', '三昧真火淬魂，攻伐凌厉。', 'Q', 5000, 'fire', '{expRate:.34,attack:28}'),
    ('art-wx-fire-x3', '流火飞星', 'body', '玄', '流火如飞星赶月，快而狠。', 'Q', 4400, 'fire', '{attack:42,speed:25}'),
    ('art-wx-earth-x1', '山岳镇魂功', 'body', '玄', '气如山岳，镇守魂魄。', 'Q', 4000, 'earth', '{defense:45,hp:160}'),
    ('art-wx-earth-x2', '厚德载物诀', 'mental', '玄', '厚德载物，稳中求进。', 'Q', 4300, 'earth', '{expRate:.3,defense:30}'),
    ('art-wx-earth-x3', '黄沙百战体', 'body', '玄', '黄沙百战穿金甲，不破楼兰终不还。', 'Q', 4600, 'earth', '{defense:38,attack:25}'),
    # ---------------- 地品 10 部（每属性 +2）----------------
    ('art-wx-metal-d1', '金阙斩雷剑', 'body', '地', '金阙神雷附剑，一斩千钧。', 'G', 30000, 'metal', '{attack:260,defense:60}'),
    ('art-wx-metal-d2', '太白锋锐诀', 'mental', '地', '太白金星之锐，锋可摘星。', 'G', 34000, 'metal', '{expRate:.55,attack:100}'),
    ('art-wx-wood-d1', '建木通天功', 'mental', '地', '攀建木而通天，生机接引仙灵。', 'G', 32000, 'wood', '{expRate:.6,hp:800}'),
    ('art-wx-wood-d2', '万灵树甲', 'body', '地', '万灵树甲护体，刀枪不入。', 'G', 36000, 'wood', '{defense:180,hp:700}'),
    ('art-wx-water-d1', '沧海凝波诀', 'mental', '地', '沧海凝波，神识浩瀚如海。', 'G', 35000, 'water', '{expRate:.58,spirit:120}'),
    ('art-wx-water-d2', '玄冥冰魄剑', 'body', '地', '玄冥冰魄化剑，寒气透骨。', 'G', 38000, 'water', '{attack:220,defense:80}'),
    ('art-wx-fire-d1', '焚天煮海', 'body', '地', '焚天煮海之势，烈焰吞八方。', 'G', 40000, 'fire', '{attack:280,speed:50}'),
    ('art-wx-fire-d2', '太阳神火诀', 'mental', '地', '太阳神火淬体，真阳至刚。', 'G', 36000, 'fire', '{expRate:.52,attack:120}'),
    ('art-wx-earth-d1', '镇岳玄功', 'body', '地', '镇岳玄功，身如大地不动。', 'G', 33000, 'earth', '{defense:200,hp:900}'),
    ('art-wx-earth-d2', '地藏伏魔体', 'body', '地', '地藏伏魔，金身镇狱。', 'G', 42000, 'earth', '{defense:160,attack:110}'),
    # ---------------- 天品 5 部（每属性 +1）----------------
    ('art-wx-metal-t1', '金仙不灭剑体', 'body', '天', '剑体合一，金仙不灭，万法难摧。', 'N', 120000, 'metal', '{attack:2400,defense:600}'),
    ('art-wx-wood-t1', '建木扶桑不朽功', 'mental', '天', '建木扶桑双生，不朽生机自循环。', 'N', 100000, 'wood', '{expRate:.7,hp:6000}'),
    ('art-wx-water-t1', '北溟天渊诀', 'mental', '天', '北溟之渊，深不可测，神识化海。', 'N', 110000, 'water', '{expRate:.68,spirit:900}'),
    ('art-wx-fire-t1', '九阳焚天诀', 'body', '天', '九阳真火焚天，所过之处皆为灰烬。', 'N', 130000, 'fire', '{attack:2200,speed:220}'),
    ('art-wx-earth-t1', '承天载物功', 'body', '天', '承天之德，载物之厚，不可撼动。', 'N', 95000, 'earth', '{defense:1500,hp:9000}'),
]

_REALM = {'Q': 'ae.QiRefining', 'G': 'ae.GoldenCore', 'N': 'ae.NascentSoul'}

# JS 对象文本（字段序与 is 表现有一致）
_NEW_ARTS_JS = ','.join(
    '{id:"%s",name:"%s",type:"%s",grade:"%s",description:"%s",realmRequirement:%s,cost:%d,spiritualRoot:"%s",effects:%s}'
    % (aid, nm, tp, gd, ds, _REALM[rl], cst, rt, ef)
    for (aid, nm, tp, gd, ds, rl, cst, rt, ef) in _NEW_ARTS_DEF
)
_NEW_IDS = [row[0] for row in _NEW_ARTS_DEF]

# 50 部旧功法五行分派（语义分派：金主兵戈锐利/木主生机草木/水主寒冰月华幽冥/
# 火主炎爆焚炼/土主厚载护御；已有 spiritualRoot 的 32 部不在此表、永不被触碰）
# 侦察依据：v28117 is 表解析（无 root 的 50 部，id 清单在 apply() 里与 base_text 对账）
_EXPECT_FIX = {
    # 黄 10 部
    'art-basic-breath': 'wood',      # 吐纳法：草木吐纳生机
    'art-iron-skin': 'earth',        # 铁皮功：皮肉如土石
    'art-spirit-cloud': 'water',     # 摸鱼诀：如鱼得水
    'art-wind-step': 'metal',        # 御风步：罡风锐利如金
    'art-wooden-body': 'wood',       # 木身功：名带木
    'art-golden-armor': 'metal',     # 金甲功：金甲
    'art-moonlight-refine': 'water', # 月华淬炼诀：月华太阴之水
    'art-swift-shadow': 'water',     # 疾影步：影随水流转
    'art-sharp-blade': 'metal',      # 锐刃诀：刃
    'art-wind-blade': 'metal',       # 风刃术：金风刃
    # 玄 9 部
    'art-flame-palm': 'fire',        # 炎掌
    'art-frost-breath': 'water',     # 寒冰吐息：冰属水
    'art-iron-fist': 'metal',        # 铁拳术
    'art-cloud-dance': 'wood',       # 云舞身法：风属木（巽）
    'art-storm-heart': 'wood',       # 风暴之心：风
    'art-jade-armor': 'earth',       # 玉甲护体：玉属土石
    'art-blood-blade': 'water',      # 血刃诀：血为水
    'art-demon-fist': 'fire',        # 魔拳：魔火焚身
    'art-wind-sword': 'metal',       # 疾风剑：剑
    # 地 11 部
    'art-ice-soul': 'water',         # 冰心诀
    'art-dragon-fist': 'wood',       # 龙拳：东方青龙属木
    'art-sun-flame': 'fire',         # 太阳真火
    'art-dark-sword': 'water',       # 幽冥剑法：幽冥属阴水
    'art-celestial-body': 'earth',   # 天元体：体厚土
    'art-starlight-gather': 'metal', # 聚星诀：星光如金辉
    'art-soul-forge': 'fire',        # 炼魂诀：炼魂业火
    'art-sword-intent': 'metal',     # 剑意诀
    'art-killing-intent': 'fire',    # 杀意诀：杀气如炎
    'art-dragon-claw': 'wood',       # 龙爪功：青龙
    'art-void-sword': 'metal',       # 虚空剑
    # 天 20 部
    'art-void-body': 'earth',        # 虚空霸体：体
    'art-phoenix-rebirth': 'fire',   # 凤凰涅槃功
    'art-star-destruction': 'metal', # 星辰破灭诀：星辰金刚
    'art-universe-devour': 'earth',  # 吞天噬地：噬地
    'art-divine-dragon': 'wood',     # 真龙诀：青龙
    'art-void-step': 'metal',        # 虚空步：乾金迅捷
    'art-chaos-body': 'earth',       # 混沌体：体
    'art-dao-heart': 'water',        # 道心诀：上善若水
    'art-five-elements': 'earth',    # 五行归一：土居中央为五行之枢
    'art-immortal-sword': 'metal',   # 斩仙剑诀
    'art-lu-xian-sword': 'metal',    # 戮仙剑诀
    'art-xian-xian-sword': 'metal',  # 陷仙剑诀
    'art-divine-destruction': 'metal',  # 诛仙剑诀
    'art-demon-god-fist': 'fire',    # 魔神道音
    'art-universe-sword': 'earth',   # 五行生灭剑：五行之枢
    'art-absolute-destruction': 'water',  # 归墟：天下之水所归
    'art-heaven-justice': 'earth',   # 天罡正法：中正厚德
    'art-earth-evil': 'water',       # 地煞冥诀：冥狱阴水
    'art-yin-yang-reincarnation': 'water',  # 阴阳轮回诀：轮回如流水
    'art-chaos-primal': 'earth',     # 混沌归元功：归元厚土
}

_FIX_JS = ','.join('"%s":"%s"' % (k, v) for k, v in sorted(_EXPECT_FIX.items()))


# --------------------------------------------------------------------------- 注入块
# 中文由 build 侧 zh() 转义为纯 ASCII（build 对 INJECT_JS 有硬断言）；无禁用模式。
INJECT_JS = r'''
/* ===== yl-0.8.13 R-067: 功法五行分类（金木水火土）+ 灵根亲和 + 全表补属性 =====
   ① 五行 = 功法 spiritualRoot × 玩家对应灵根（游戏本体 go(): 1+灵根*0.005，灵根 0~100
      → 最高 +50%），经 xt/Cg/bd 落到 攻/防/血/灵/体/速 与修炼效率 —— 需求「对应到人物
      这些属性的相应加成」走本体机制，本模块只补字段与展示，不动任何结算公式。
   ② 50 部旧功法按语义分派五行（YLXW_ELEM_FIX），已有 spiritualRoot 的功法永不触碰；
      YlxwElemInit() 在模块加载时同步执行（先于 numbal 的 YlxwArtBalance，后者按
      spiritualRoot 给预算 ×1.15 —— 补齐后同格倍率统一）。 */
var YLXW_ELEM_ORDER = ["metal", "wood", "water", "fire", "earth"];
var YLXW_ELEM_LABEL = { metal: "\u91d1", wood: "\u6728", water: "\u6c34", fire: "\u706b", earth: "\u571f" };
var YLXW_ELEM_CLS = {
  metal: "border-yellow-600 text-yellow-300 bg-yellow-900/20",
  wood: "border-green-600 text-green-300 bg-green-900/20",
  water: "border-blue-600 text-blue-300 bg-blue-900/20",
  fire: "border-red-600 text-red-300 bg-red-900/20",
  earth: "border-amber-700 text-amber-300 bg-amber-900/20"
};
var YLXW_ELEM_FIX = { __FIX__ };
/* 取功法五行：优先自身 spiritualRoot（新增 55 部自带），否则查分派表（运行时补写） */
function YlxwElemOf(a) {
  if (!a) return null;
  if (a.spiritualRoot) return a.spiritualRoot;
  return YLXW_ELEM_FIX[a.id] || null;
}
/* 全表补写缺失的 spiritualRoot（幂等：已有值不覆盖；触发 go() 加成体系全覆盖） */
function YlxwElemInit() {
  var i, a, r;
  for (i = 0; i < is.length; i++) {
    a = is[i];
    if (a && !a.spiritualRoot) {
      r = YLXW_ELEM_FIX[a.id];
      if (r) a.spiritualRoot = r;
    }
  }
}
function YlxwElemLabel(a) {
  var r = YlxwElemOf(a);
  return r ? (YLXW_ELEM_LABEL[r] || "无") : "无";
}
function YlxwElemCls(a) {
  var r = YlxwElemOf(a);
  return "text-[10px] md:text-xs px-1.5 py-0.5 rounded border font-bold "
    + ((r && YLXW_ELEM_CLS[r]) || "border-stone-700 text-stone-400 bg-stone-800");
}
YlxwElemInit();
/* ===== end R-067 ===== */
'''.replace('__FIX__', _FIX_JS)

# --------------------------------------------------------------------------- 锚点

# 注入位置：GS 之前（is 表 264k 已定义、numbal 注入块 1387k 在其后 → 初始化先于预算重算）
_A_INJECT = 'function GS('

# is 表尾：混沌归元功（art-chaos-primal，恰 1 次）的 speed:1e4 收尾 + og 表起点
_A_TABLE_TAIL_OLD = 'speed:1e4}}],og={"art-thunder-sword"'
_A_TABLE_TAIL_NEW = 'speed:1e4}},' + _NEW_ARTS_JS + '],og={"art-thunder-sword"'

# 功法阁 z4：state 三件套 → 四件套（追加五行筛选状态）
_A_STATE_OLD = '[m,j]=O.useState("all")'
_A_STATE_NEW = '[m,j]=O.useState("all"),[YlxwElemSel,YlxwElemSet]=O.useState("all")'

# 筛选谓词：状态筛选之前插五行谓词（不拆 R-016 的 YlxwGongfaFilterHit 谓词锚）
_A_PRED_OLD = 'if(m!=="all"){const D=g.has(w.id),Q=q.has(w.id);'
_A_PRED_NEW = ('if(YlxwElemSel!=="all"&&YlxwElemOf(w)!==YlxwElemSel)return!1;'
               + _A_PRED_OLD)

# useMemo 依赖：补 YlxwElemSel
_A_DEPS_OLD = '[d,f,m,_,a.cultivationArts,a.unlockedArts,T]'
_A_DEPS_NEW = '[d,f,m,_,a.cultivationArts,a.unlockedArts,T,YlxwElemSel]'

# 筛选行：状态筛选行之前插「五行筛选」行（写法对齐相邻行；配色对齐灵根面板）
_A_FILTER_OLD = ('e.jsxs("div",{className:"flex flex-wrap gap-2",children:[e.jsx("span",'
                 '{className:"text-xs text-stone-400 self-center",children:"状态筛选："}),')
_A_FILTER_NEW = (
    'e.jsxs("div",{className:"flex flex-wrap gap-2",children:[e.jsx("span",'
    '{className:"text-xs text-stone-400 self-center",children:"五行筛选："}),'
    '["all","metal","wood","water","fire","earth"].map(g=>e.jsx("button",'
    '{onClick:()=>YlxwElemSet(g),'
    'className:`px-2 py-1 rounded text-xs transition-colors ${YlxwElemSel===g?'
    'g==="metal"?"bg-yellow-700 text-yellow-200":'
    'g==="wood"?"bg-green-700 text-green-200":'
    'g==="water"?"bg-blue-700 text-blue-200":'
    'g==="fire"?"bg-red-700 text-red-200":'
    'g==="earth"?"bg-amber-700 text-amber-200":'
    '"bg-mystic-jade text-white":"bg-stone-700 text-stone-400 hover:bg-stone-600"}`,'
    'children:g==="all"?"全部":YLXW_ELEM_LABEL[g]},g))]}),'
    + _A_FILTER_OLD
)

# 卡片徽标：品阶徽标后挂五行徽标（不拆 R-016 的 YlxwGongfaTypeLabel 挂载锚）
_A_BADGE_OLD = 'children:[g.grade||"黄","品"]})'
_A_BADGE_NEW = ('children:[g.grade||"黄","品"]}),'
                'e.jsx("span",{className:YlxwElemCls(g),children:YlxwElemLabel(g)})')

# intro：心法说明行后插五行亲和说明（保留 R-016 的「战斗技能：」intro 原文）
_A_INTRO_OLD = 'children:"心法：主修功法，激活后提升修炼效率。"}),'
_A_INTRO_NEW = (_A_INTRO_OLD
                + 'e.jsx("p",{children:"五行亲和：每部功法自带金木水火土属性，'
                  '与你的对应灵根共鸣——灵根每 1 点，功法效果 +0.5%（灵根见角色面板）。"}),')

# --------------------------------------------------------------------------- 主入口


def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']
    base = ctx.get('base_text') or ''
    fixes = sorted(_EXPECT_FIX.keys())

    # ---- 静态对账：分派表 50 键 = v28117 无 root 清单 ----
    assert len(_EXPECT_FIX) == 50, 'R-067 分派表应为 50 键，实际 %d' % len(_EXPECT_FIX)
    assert len(set(fixes)) == 50, 'R-067 分派表 id 有重复'
    if base:
        missing = [k for k in fixes if base.count('{id:"%s",' % k) != 1]
        assert not missing, 'R-067 分派表 id 不在基线或非唯一: %r' % missing[:5]
        # clash 检测必须按对象边界切片（窗口法会误吞邻对象的 root，如 雷掌/寒冰剑 紧邻）
        clash = []
        for k in fixes:
            seg = base.split('{id:"%s",' % k, 1)[1].split('},{id:"', 1)[0]
            if 'spiritualRoot:"' in seg:
                clash.append(k)
        assert not clash, 'R-067 分派表与基线已有 root 冲突: %r' % clash[:5]

    # 既有 32 部 root 基线计数（基线漂移即刻炸断）；门禁期望 = 基线 + 新功法合法新增
    _ADDED_BY_ELEM = {}
    for _r in ('metal', 'wood', 'water', 'fire', 'earth'):
        _n0 = base.count('spiritualRoot:"%s"' % _r) if base else {
            'metal': 9, 'wood': 4, 'water': 6, 'fire': 8, 'earth': 5}[_r]
        _n1 = sum(1 for row in _NEW_ARTS_DEF if row[7] == _r)
        _ADDED_BY_ELEM[_r] = (_n0, _n1)
        assert _n0 == {'metal': 9, 'wood': 4, 'water': 6,
                       'fire': 8, 'earth': 5}[_r], \
            'R-067 基线 %s root 计数漂移: %d' % (_r, _n0)

    # ---- 注入块自检（与 build 侧同口径的预警：zh 后应纯 ASCII）----
    inj = zh(INJECT_JS)
    assert all(ord(c) < 128 for c in inj), 'R-067 注入块 zh() 后仍含非 ASCII'

    # 0) 五行助手注入（先于 numbal 的 YlxwArtBalance 执行）
    p.insert_before('r067-elem-block', _A_INJECT, inj + '\n',
                    expect=1, note='注入 R-067 五行助手 + 50 部补 root（YlxwElemInit 自启动）')

    # 1) is 表尾插入 55 部新功法（全部自带 spiritualRoot）
    p.replace('r067-arts-expand', _A_TABLE_TAIL_OLD, _A_TABLE_TAIL_NEW, expect=1,
              note='功法表扩充 82→137 部（黄+25 玄+15 地+10 天+5，id 前缀 art-wx-）')

    # 2) 功法阁 z4：五行筛选（state / 谓词 / deps / 筛选行）
    p.replace('r067-elem-state', _A_STATE_OLD, _A_STATE_NEW, expect=1,
              note='追加五行筛选 state')
    p.replace('r067-elem-pred', _A_PRED_OLD, _A_PRED_NEW, expect=1,
              note='五行筛选谓词（状态筛选之前，不动 R-016 谓词锚）')
    p.replace('r067-elem-deps', _A_DEPS_OLD, _A_DEPS_NEW, expect=1,
              note='useMemo 依赖补 YlxwElemSel')
    p.replace('r067-elem-filter', _A_FILTER_OLD, _A_FILTER_NEW, expect=1,
              note='新增「五行筛选」按钮行（金/木/水/火/土）')

    # 3) 卡片五行徽标 + intro 亲和说明
    p.replace('r067-elem-badge', _A_BADGE_OLD, _A_BADGE_NEW, expect=1,
              note='卡片品阶徽标后挂五行徽标')
    p.replace('r067-elem-intro', _A_INTRO_OLD, _A_INTRO_NEW, expect=1,
              note='intro 补五行亲和说明（go() 机制文案）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ---- 本模块：注入块 ----
        ('R067·五行取值函数已定义', 'function YlxwElemOf(', 1, '==', ''),
        ('R067·补写函数已定义', 'function YlxwElemInit(', 1, '==', ''),
        ('R067·补写已自启动', 'YlxwElemInit();', 1, '==', '模块加载时同步补 root'),
        ('R067·五行徽标文案已定义', 'function YlxwElemLabel(', 1, '==', ''),
        ('R067·五行徽标配色已定义', 'function YlxwElemCls(', 1, '==', ''),
        ('R067·分派表已定义', 'var YLXW_ELEM_FIX = {', 1, '==', '50 部旧功法语义分派'),
        ('R067·金徽标配色', 'metal: "border-yellow-600 text-yellow-300 bg-yellow-900/20"', 1, '==', ''),
        ('R067·土徽标配色', 'earth: "border-amber-700 text-amber-300 bg-amber-900/20"', 1, '==', ''),
        # ---- 本模块：表扩充 ----
        ('R067·旧表尾锚已展开', _A_TABLE_TAIL_OLD, 0, '==', '表尾已插入 55 部'),
        ('R067·新表尾在位', '],og={"art-thunder-sword"', 1, '==', 'og 表仍紧随 is 表'),
        ('R067·新功法 id 前缀计数', 'art-wx-', 55, '==', '黄25 玄15 地10 天5'),
        # ---- 本模块：功法阁 UI ----
        ('R067·五行筛选行在位', 'children:"五行筛选："', 1, '==', ''),
        ('R067·五行选项数组', '["all","metal","wood","water","fire","earth"].map(', 1, '==', ''),
        ('R067·五行 state 已挂', '[YlxwElemSel,YlxwElemSet]=O.useState("all")', 1, '==', ''),
        ('R067·五行谓词在位', 'if(YlxwElemSel!=="all"&&YlxwElemOf(w)!==YlxwElemSel)return!1;', 1, '==', ''),
        ('R067·依赖数组已扩', _A_DEPS_NEW, 1, '==', ''),
        ('R067·卡片五行徽标挂载', 'className:YlxwElemCls(g),children:YlxwElemLabel(g)', 1, '==', ''),
        ('R067·intro 五行亲和说明', '五行亲和：每部功法自带金木水火土属性', 1, '==', ''),
        ('R067·原状态 state 保留', _A_STATE_OLD, 1, '==', '追加而非替换'),
        ('R067·状态筛选行保留', 'children:"状态筛选："', 1, '==', '五行行插在其前'),
        # ---- 冻结：R-016（yl_gongfa_ext.py）面 ----
        ('冻结·R016 筛选单点函数未动', 'function YlxwGongfaFilterHit(', 1, '==', ''),
        ('冻结·R016 技能类型筛选行未动', '["all","mental","attack","buff","heal"].map(', 1, '==', ''),
        ('冻结·R016 筛选标题未动', 'children:"技能类型："', 1, '==', ''),
        ('冻结·R016 技能类型徽标挂载未动', 'YlxwGongfaTypeLabel(g)})]})', 1, '==', '未被本模块拆改'),
        ('冻结·R016 心法徽标保留', 'children:"心法"}):null,', 1, '==', ''),
        ('冻结·R016 注入点未破坏', 'function YlxwPanelModal(', 1, '==', ''),
        ('冻结·R016 战斗技能 intro 未动', '战斗技能：每部功法习得后自动加入战斗技能栏', 1, '==', ''),
        # ---- 冻结：numbal（yl_numbal_ext.py）面 ----
        ('冻结·numbal 重算执行器未动', 'function YlxwArtBalance()', 1, '==', ''),
        ('冻结·numbal 逐部重算未动', 'YlxwArtRebalance(is[i])', 1, '==', ''),
        ('冻结·numbal 单元格函数未动', 'function YlxwArtCellOf(a)', 1, '==', ''),
        ('冻结·numbal 预算复算未动', 'YlxwArtBudgetCompute();', 1, '==', ''),
        ('冻结·numbal expRate 封顶未动', 'r=Math.min(1.25,u.effects.expRate*$', 1, '==', ''),
        ('冻结·numbal 递减系数未动', 'YlxwArtFactor(YAq)', 2, '==', 'Cg 内两处'),
        # ---- 冻结：战斗本体（og/GS/QS/PS/go）----
        ('冻结·GS 生成器未动', 'function GS(t){var l;const r=IS[t.grade]||1', 1, '==', ''),
        ('冻结·og 手写技能表未动', 'og={"art-thunder-sword"', 1, '==', ''),
        ('冻结·QS 装配未动', 't.cultivationArts.forEach(N=>{const k=og[N]', 1, '==', ''),
        ('冻结·PS 五行领域未动', 'function PS(t,r){const a=t.spiritualRoots', 1, '==', ''),
        ('冻结·go 灵根加成公式未动',
         'go=(t,r)=>t.spiritualRoot?1+(r[t.spiritualRoot]||0)*.005:1', 1, '==',
         '需求①的加成机制本体，一字不动'),
        # ---- 冻结：既有 32 部功法 root 字节形态不变（基线计数 + 新功法合法新增）----
        ('冻结·金系 root 总数', 'spiritualRoot:"metal"',
         _ADDED_BY_ELEM['metal'][0] + _ADDED_BY_ELEM['metal'][1], '==',
         '基线%d 处未动 + 新功法%d 部' % _ADDED_BY_ELEM['metal']),
        ('冻结·木系 root 总数', 'spiritualRoot:"wood"',
         _ADDED_BY_ELEM['wood'][0] + _ADDED_BY_ELEM['wood'][1], '==',
         '基线%d 处未动 + 新功法%d 部' % _ADDED_BY_ELEM['wood']),
        ('冻结·水系 root 总数', 'spiritualRoot:"water"',
         _ADDED_BY_ELEM['water'][0] + _ADDED_BY_ELEM['water'][1], '==',
         '基线%d 处未动 + 新功法%d 部' % _ADDED_BY_ELEM['water']),
        ('冻结·火系 root 总数', 'spiritualRoot:"fire"',
         _ADDED_BY_ELEM['fire'][0] + _ADDED_BY_ELEM['fire'][1], '==',
         '基线%d 处未动 + 新功法%d 部' % _ADDED_BY_ELEM['fire']),
        ('冻结·土系 root 总数', 'spiritualRoot:"earth"',
         _ADDED_BY_ELEM['earth'][0] + _ADDED_BY_ELEM['earth'][1], '==',
         '基线%d 处未动 + 新功法%d 部' % _ADDED_BY_ELEM['earth']),
        # ---- 冻结：功法表头与既有代表功法 ----
        ('冻结·功法表头未动', 'is=[{id:"art-basic-breath"', 1, '==', ''),
        ('冻结·长生诀（木系）未动', '"art-immortal-life",name:"长生诀"', 1, '==', '本体唯一 heal 技能功法'),
        ('冻结·五行归一（天品）未动', '"art-five-elements",name:"五行归一"', 1, '==', '用户点名过的高阶功法'),
        ('冻结·混沌归元功表尾形态', '"art-chaos-primal",name:"混沌归元功"', 1, '==', 'is 表最后一部'),
    ]
    # 55 部新功法逐部在位（门禁 count==1）
    for _id in _NEW_IDS:
        gates.append(('R067·新功法在位 ' + _id, '{id:"' + _id + '",', 1, '==', ''))
    # 50 部旧功法分派键逐部在位（防 base 漂移；运行时补写不写字节，恒 1）
    for _id in fixes:
        gates.append(('R067·分派目标在位 ' + _id, '{id:"' + _id + '",', 1, '==', ''))
    return gates
