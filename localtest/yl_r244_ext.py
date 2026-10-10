# -*- coding: utf-8 -*-
r"""
yl_r244_ext.py — R-244 功法体系重做 · 批 2：体术 89 部数据层 + 叠加软上限（方案 A）

需求原文（用户 2026-10-10 · 批 2）
--------------------------------------------------------------------------
    1. 体术 89 部数据层落地：把 `is[]` 里 `type==="body"` 的 89 部，按策划
       `策划_功法体系重做_20261010.md` 第七节设计表替换
       **属性（攻/防/气血/速度/神识/根骨）、机制字段、描述**。
    2. 叠加软上限（方案 A）：体术保持「习得即叠加、不做可切换」；89 部全叠加会
       数值爆炸，故在**体术属性汇总处**加「分属性软上限 + 超额 30% 计入」。

硬性口径（照任务书 + 策划 §七）
--------------------------------------------------------------------------
  · ★ 保留 `id` / `name` / `grade` / `spiritualRoot` / `realmRequirement` / `cost` /
    `sectId` 一字不改；只替换 **effects（属性 + 机制）** 与 **description**。
    （§七：五行分布与现状一致、零改名成本。）
  · ★ 中文存储混合态：`is[]` 内中文为**裸 UTF-8**；本脚本所有锚点均为 ASCII。
  · ★ 严禁 `eval→JSON.stringify` 整段重写 `is[]`（`realmRequirement:ae.QiRefining`
    是枚举引用，会被破坏）⇒ 全程**字符串级替换**。

机制字段名（★ 决策 · 见报告）
--------------------------------------------------------------------------
  · 反震（受击反弹 X%）  → `reflectDamage`  （bundle **既有**字段：km 反弹结算读它）
  · 吸血（伤害 X% 回血） → `lifeLeech`      （bundle **既有**字段，§七 已实装）
  · 连击（X% 概率追击）  → `comboRate`
  · 斩杀（敌血<30% +X%） → `executeRate`
  · 破甲（无视 X% 防御） → `armorPenRate`
  命名风格与 yl_r240_ext.py 已写入的 `wudaoRate / wudaoGain / breathHeal /
  spiritGain / lifeCostCut` **逐字同型**（lowerCamelCase + `<机制><Rate|Gain|Heal|Cut>`）；
  已实装的两项（反震 / 吸血）**逐字沿用 bundle 既有名**，保证下游战斗钩子读得到。

软上限落点（★ 决策 · 见报告）
--------------------------------------------------------------------------
  · `Cg(t)` —— 角色「功法属性汇总」函数（bundle 中与 `bd()` 紧邻，@~616947）。
    它先按 `YlxwArtRanked(t)` 累加**全部已学功法**（体术 + 心法）的
    attack/defense/hp/spirit/physique/speed，**之后**才叠加
    协同 `fy(Pm(...))` / 装备 / 天赋 / 称号 —— 故在此处按 `N.type==="body"` 分流，
    对**体术侧合计**施加软上限，**绝不误伤**心法/天赋/称号/协同/装备（洞府·羁绊在
    `xt()` 的 extras 钩子，不在此函数内）。
  · 口径：`cap(v,C) = v<=C ? v : C + (v-C)*0.30`
      攻击 6000 / 防御 3000 / 气血 8000 / 速度 1800 / 根骨 800 / 神识 500。

契约（照 localtest/yl_r240_ext.py）
--------------------------------------------------------------------------
  · CLI：`--src <bundle.js>`（必填）；`--check`（只验不写）；`--selftest`（内存自证）。
  · 二进制读写；就地原子写回（mkstemp + os.replace）；首次改写前落 <src>.bak-r244-<时刻>。
  · 幂等：产物含唯一标记 `/*[r244body]*/` ⇒ SKIP 并 return 3。
  · 退出码：0=成功；3=已补丁（未写盘）；2=前置断言/锚点计数失败；1=门禁/往返/自检失败。
  · 纯客户端；不改 build_v26n.py / chain_build.py / 任何 build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

MARK = '/*[r244body]*/'

# effects 键输出顺序（属性在前，机制在后）
EFF_ORDER = ['attack', 'defense', 'hp', 'spirit', 'speed', 'physique',
             'reflectDamage', 'lifeLeech', 'comboRate', 'executeRate', 'armorPenRate']

# 软上限（方案 A）
SOFT_CAP = {'attack': 6000, 'defense': 3000, 'hp': 8000,
            'speed': 1800, 'physique': 800, 'spirit': 500}
SOFT_RATE = 0.30

# 机制字段 → 设计表记号（用于 selftest 打印）
MECH_CN = {'reflectDamage': '反震', 'lifeLeech': '吸血', 'comboRate': '连击',
           'executeRate': '斩杀', 'armorPenRate': '破甲'}


def _num(x):
    """数值 → bundle 风格字面量（<1 的小数去前导 0，如 0.03 → '.03'；整数原样）。"""
    if isinstance(x, bool):
        return 'true' if x else 'false'
    if isinstance(x, int) or (isinstance(x, float) and x == int(x)):
        return str(int(x))
    s = repr(round(float(x), 8))
    if s.startswith('0.'):
        s = s[1:]
    return s


def _fmt_effects(d):
    parts = []
    for k in EFF_ORDER:
        if k in d:
            parts.append('%s:%s' % (k, _num(d[k])))
    for k, v in d.items():
        if k not in EFF_ORDER:
            parts.append('%s:%s' % (k, _num(v)))
    return '{' + ','.join(parts) + '}'


def soft_cap(v, cap):
    """方案 A：v ≤ cap 取原值；超出部分按 30% 计入。"""
    return v if v <= cap else cap + (v - cap) * SOFT_RATE


# --------------------------------------------------------------------------- 设计表（89 部）
# (id, 名称, 品级, 属性dict, 机制dict, 新描述)
#   id / name / grade / spiritualRoot 与现状逐字一致（零改名）。
TABLE = [
    # ===== 黄品 27 部 =====
    ('art-wx-fire-h1', '赤焰掌', '黄', {'attack': 42, 'speed': 12}, {},
     '掌心血气化焰，出招又快又烈，专抢先手。'),
    ('art-golden-sword', '金剑诀', '黄', {'attack': 48, 'defense': 12}, {},
     '以金气凝剑意，剑锋自利，护体金芒亦不散。'),
    ('art-wx-metal-h2', '白虹剑法', '黄', {'attack': 40, 'speed': 9}, {'comboRate': 0.02},
     '剑走白虹，一刺未收二刺又至，快得看不清剑影。'),
    ('art-wx-metal-h5', '破甲锥劲', '黄', {'attack': 53}, {'armorPenRate': 0.05},
     '劲力拧成一线专钻甲缝，寻常护体难挡其锋。'),
    ('art-thunder-palm', '雷掌', '黄', {'attack': 39, 'speed': 14}, {},
     '掌缘蓄雷，拍出噼啪作响，快与重兼得。'),
    ('art-wx-metal-h4', '秋水剑气诀', '黄', {'attack': 60}, {},
     '剑气如秋水澄澈，看似平和，实则一味求纯的杀伐之诀。'),
    ('art-wx-fire-h4', '焚身锻体功', '黄', {'attack': 42, 'hp': 90}, {},
     '引火焚身以炼气血，皮肉越灼越韧，出手也越发狠辣。'),
    ('art-wx-fire-h3', '火鸦术', '黄', {'attack': 36, 'speed': 16}, {},
     '掌心放出数点火鸦扑敌，火鸦虽小，胜在迅捷缠人。'),
    ('art-sharp-blade', '锐刃诀', '黄', {'attack': 53}, {'executeRate': 0.06},
     '只求一个「锐」字，专挑敌人力竭之际补上致命一记。'),
    ('art-wx-earth-h1', '厚土功', '黄', {'defense': 42, 'hp': 90}, {},
     '沉腰坐马如厚土扎根，任你拳脚相加，我自岿然。'),
    ('art-earth-core', '土核功', '黄', {'defense': 33, 'hp': 135}, {},
     '内力聚于丹田如土核凝实，气血沉厚，最能挨打。'),
    ('art-wx-earth-h3', '磐石护体', '黄', {'defense': 37, 'hp': 79}, {'reflectDamage': 0.03},
     '皮坚似磐石，敌劲加身竟有三分被硬生生弹回。'),
    ('art-wx-earth-h4', '大地之力', '黄', {'attack': 21, 'defense': 27, 'physique': 12}, {},
     '借大地厚重之力入体，攻守兼备，根基亦稳。'),
    ('art-wx-water-h1', '玄冰护体', '黄', {'defense': 60}, {},
     '周身结一层玄冰薄甲，寒而不脆，专事御敌。'),
    ('art-wx-water-h5', '流云水袖', '黄', {'defense': 33, 'speed': 18}, {},
     '袖如流水卸去来劲，身形随之飘忽难捉。'),
    ('art-iron-skin', '铁皮功', '黄', {'defense': 36, 'hp': 120}, {},
     '最粗浅也最实在的炼皮之法，皮糙肉厚，就是耐打。'),
    ('art-golden-armor', '金甲功', '黄', {'defense': 39, 'hp': 105}, {},
     '灵气化金甲覆体，甲厚而不滞，攻守之间留有余地。'),
    ('art-swift-shadow', '疾影步', '黄', {'attack': 16, 'speed': 25}, {'comboRate': 0.02},
     '身随影动，追敌时一步未停，第二下已到。'),
    ('art-wind-step', '御风步', '黄', {'attack': 21, 'speed': 26}, {},
     '借风而行，进退如风中之叶，轻快却不失力道。'),
    ('art-wind-blade', '风刃术', '黄', {'attack': 27, 'speed': 22}, {},
     '旋身带起风刃，刃随人走，攻速浑然一体。'),
    ('art-wx-water-h3', '碧波剑法', '黄', {'attack': 24, 'speed': 24}, {},
     '剑势如碧波层层推涌，一浪接一浪，绵密不停。'),
    ('art-ice-sword', '寒冰剑', '黄', {'attack': 26, 'speed': 18}, {'comboRate': 0.02},
     '剑锋凝寒，刺出后寒气未散第二剑又至，令人手足僵滞。'),
    ('art-flame-body', '火体功', '黄', {'hp': 135, 'speed': 22}, {},
     '以火炼体，气血沸腾如炉，身法也烧得轻快。'),
    ('art-wooden-body', '木身功', '黄', {'attack': 37, 'speed': 11}, {'lifeLeech': 0.01},
     '身如老木，伤处渗出的生机竟被自己重新汲取回来。'),
    ('art-wx-metal-h3', '锋芒锻体功', '黄', {'attack': 42, 'speed': 7}, {'lifeLeech': 0.01},
     '以锋芒自砺皮肉，每一道伤都化作更利的杀意。'),
    ('art-wx-wood-h4', '灵木锻体功', '黄', {'attack': 32, 'hp': 106}, {'lifeLeech': 0.01},
     '木灵缠身，敌血沾体即被枝叶吸走，回补己身。'),
    ('art-wx-wood-h3', '藤蔓缠身功', '黄', {'attack': 34, 'hp': 92}, {'armorPenRate': 0.05},
     '藤蔓勒敌如蟒，越缠越紧，护甲在其下寸寸崩裂。'),
    # ===== 玄品 23 部 =====
    ('art-wx-metal-x1', '庚金剑气诀', '玄', {'attack': 120, 'speed': 26}, {},
     '庚金之气化作千百剑气破空而至，锐不可当。'),
    ('art-wx-fire-x1', '炎爆烧天诀', '玄', {'attack': 124}, {'executeRate': 0.15},
     '一诀引动炎爆，专在敌人气息将尽时烧尽最后一口气。'),
    ('art-wx-metal-x2', '金乌啄日', '玄', {'attack': 104, 'speed': 38}, {},
     '身法如金乌掠空，出手只啄要害，快而准。'),
    ('art-lightning-strike', '雷霆一击', '玄', {'attack': 100, 'speed': 16}, {'armorPenRate': 0.12},
     '聚雷霆于一击，雷火交加处，护体真气直接被洞穿。'),
    ('art-fire-blade', '烈焰刀', '玄', {'attack': 112, 'hp': 240}, {},
     '刀身裹烈焰，劈砍时火借刀势，气血随之壮盛。'),
    ('art-demon-fist', '魔拳', '玄', {'attack': 128, 'hp': 160}, {},
     '拳意入魔，越打越狂，自身气血也在狂战中被催发。'),
    ('art-fiery-fist', '烈火拳', '玄', {'attack': 160}, {},
     '拳拳裹烈火，是纯粹到极致的攻伐之技。'),
    ('art-golden-protection', '金甲护体', '玄', {'attack': 72, 'defense': 88}, {},
     '金甲加身的同时暗藏反手一击，守中带攻。'),
    ('art-earth-shield', '厚土护体', '玄', {'defense': 82, 'hp': 218}, {'reflectDamage': 0.08},
     '土气护体如墙，敌力打在墙上，八成之力被原样送回。'),
    ('art-wx-earth-x1', '山岳镇魂功', '玄', {'defense': 96, 'hp': 320}, {},
     '气沉如山岳，镇得心神不动，任敌狂风暴雨。'),
    ('art-jade-bone', '玉骨功', '玄', {'defense': 80, 'hp': 400}, {},
     '淬骨如玉，骨坚血足，是慢工出细活的护体根基。'),
    ('art-wx-earth-x3', '黄沙百战体', '玄', {'attack': 56, 'defense': 72, 'physique': 32}, {},
     '黄沙磨体百战不损，攻守与根骨齐进。'),
    ('art-jade-armor', '玉甲护体', '玄', {'defense': 88, 'hp': 188}, {'reflectDamage': 0.08},
     '玉甲温润却极硬，敌劲触之反震，伤敌于无形。'),
    ('art-wx-wood-x1', '苍木罡气', '玄', {'defense': 88, 'hp': 360}, {},
     '木气化罡护身，生机不断，气血自复。'),
    ('art-cloud-dance', '云舞身法', '玄', {'defense': 56, 'speed': 70}, {},
     '身如流云，攻来便散、散而复聚，守与速相生。'),
    ('art-wind-sword', '疾风剑', '玄', {'attack': 56, 'speed': 46}, {'comboRate': 0.05},
     '剑快如疾风，一息之间可连出数剑。'),
    ('art-wx-water-x2', '寒潭映月', '玄', {'defense': 72, 'speed': 58}, {},
     '心静如寒潭映月，敌之来势尽入我眼，避守自如。'),
    ('art-wx-water-x3', '逆水行舟剑', '玄', {'attack': 64, 'speed': 64}, {},
     '剑势逆水而上，越阻越急，攻速相济。'),
    ('art-wx-fire-x3', '流火飞星', '玄', {'attack': 44, 'speed': 54}, {'comboRate': 0.05},
     '火随身走如飞星，划过之处接连爆出第二道火光。'),
    ('art-blood-blade', '血刃诀', '玄', {'attack': 124}, {'lifeLeech': 0.03},
     '以血养刃，刃伤敌亦饮敌血，越战越足。'),
    ('art-flame-palm', '炎掌', '玄', {'attack': 88, 'speed': 24}, {'lifeLeech': 0.03},
     '掌中炎气灼敌伤口，敌血未干已被掌劲引回己身。'),
    ('art-iron-fist', '铁拳术', '玄', {'attack': 94, 'hp': 156}, {'lifeLeech': 0.03},
     '铁拳破防，拳上沾血即回补自身气血。'),
    ('art-frost-sword', '霜寒剑法', '玄', {'attack': 88, 'defense': 38}, {'armorPenRate': 0.12},
     '霜气钻入甲缝冻裂其护，再以一剑破之。'),
    # ===== 地品 18 部 =====
    ('art-sword-intent', '剑意诀', '地', {'attack': 270}, {'executeRate': 0.30},
     '剑未出而意先至，敌人气血一衰，剑意即刻索命。'),
    ('art-thunder-sword', '天雷剑诀', '地', {'attack': 340, 'speed': 40}, {},
     '剑引天雷，落处焦裂，是地阶中少见的纯攻之诀。'),
    ('art-phoenix-blade', '凤凰刀', '地', {'attack': 300, 'hp': 500}, {},
     '刀如凤凰展翼，焚敌亦自燃，气血在烈焰中越发雄浑。'),
    ('art-divine-sword', '神剑诀', '地', {'attack': 220, 'defense': 55}, {'armorPenRate': 0.25},
     '剑锋所指护体如纸，四分之一防御在剑下形同虚设。'),
    ('art-wx-fire-d1', '焚天煮海', '地', {'attack': 360, 'speed': 25}, {},
     '火势焚天煮海，出手间天地为炉，专事毁灭。'),
    ('art-dragon-fist', '龙拳', '地', {'attack': 400}, {},
     '拳出如龙吟，是地阶最直接也最沉重的杀招。'),
    ('art-wx-earth-d2', '地藏伏魔体', '地', {'attack': 140, 'defense': 180, 'physique': 80}, {},
     '以佛土之力炼体，伏魔亦伏己，攻守根骨俱进。'),
    ('art-earth-mountain', '山岳功', '地', {'defense': 175, 'hp': 475}, {'reflectDamage': 0.18},
     '身化山岳，敌之力撞于其上，近两成被原样弹回。'),
    ('art-wx-earth-d1', '镇岳玄功', '地', {'defense': 170, 'hp': 470, 'physique': 45}, {'reflectDamage': 0.12},
     '玄功镇岳，气血沉厚，受击时劲力回弹一分。'),
    ('art-celestial-body', '天元体', '地', {'attack': 40, 'defense': 110, 'hp': 410, 'physique': 40}, {'reflectDamage': 0.18},
     '炼体至天元之境，肉身自生反震，攻守皆固。'),
    ('art-wx-wood-d2', '万灵树甲', '地', {'defense': 240, 'hp': 800}, {},
     '万木之灵凝成树甲，生生不息，是最厚的活体护甲。'),
    ('art-dark-sword', '幽冥剑法', '地', {'attack': 120, 'speed': 100}, {'comboRate': 0.12},
     '剑出幽冥，第一剑尚未回鞘，第二剑已自阴影里刺到。'),
    ('art-killing-intent', '杀意诀', '地', {'attack': 160, 'speed': 160}, {},
     '浑身只剩杀意，攻速浑然一体，招招不留余力。'),
    ('art-void-sword', '虚空剑', '地', {'attack': 140, 'speed': 175}, {},
     '剑自虚空递出，不见来路，唯见其速。'),
    ('art-wx-water-d2', '玄冥冰魄剑', '地', {'defense': 135, 'speed': 90}, {'comboRate': 0.12},
     '剑凝玄冥冰魄，寒锋连点，一息数击冻人经脉。'),
    ('art-dragon-claw', '龙爪功', '地', {'attack': 220, 'hp': 270}, {'lifeLeech': 0.06},
     '龙爪裂敌，爪下血肉尽归己身。'),
    ('art-golden-dragon', '金龙诀', '地', {'attack': 190, 'defense': 80}, {'lifeLeech': 0.06},
     '金龙缠身，攻时化爪，守时化甲，伤敌即养己。'),
    ('art-wx-metal-d1', '金阙斩雷剑', '地', {'attack': 230, 'speed': 25}, {'armorPenRate': 0.25},
     '金阙雷剑劈落，护甲连同一线防御一并斩断。'),
    # ===== 天品 21 部 =====
    ('art-absolute-destruction', '归墟', '天', {'attack': 400, 'speed': 60, 'physique': 80},
     {'executeRate': 0.45, 'armorPenRate': 0.40},
     '万物归于墟。视敌甲如无物，敌血将尽时一剑了结。'),
    ('art-universe-sword', '五行生灭剑', '天', {'attack': 560, 'defense': 200, 'speed': 160}, {},
     '一剑含五行生灭，攻守身法俱在其中，是天阶的均衡之选。'),
    ('art-lu-xian-sword', '戮仙剑诀', '天', {'attack': 620, 'speed': 40}, {'executeRate': 0.45},
     '专为戮仙而生，仙血将尽之际，剑势骤然暴涨。'),
    ('art-immortal-sword', '斩仙剑诀', '天', {'attack': 840, 'speed': 100}, {},
     '剑势纯粹到极致，斩仙只需一剑，不需其余花样。'),
    ('art-star-destruction', '星辰破灭诀', '天', {'attack': 800, 'defense': 200}, {},
     '引星辰破灭之力，攻中带守，如陨星坠地。'),
    ('art-wx-fire-t1', '九阳焚天诀', '天', {'attack': 800, 'speed': 140}, {},
     '九阳齐出焚天，攻速并重，火势不容闪避。'),
    ('art-celestial-blade', '开天', '天', {'attack': 900, 'defense': 100}, {},
     '一刀开天，是攻伐之极，附带一丝护体之势。'),
    ('art-chaos-body', '混沌体', '天', {'defense': 300, 'hp': 1180, 'physique': 140}, {'reflectDamage': 0.25},
     '混沌之体，无隙可击，四分之一来劲被混沌吞返。'),
    ('art-void-body', '虚空霸体', '天', {'defense': 440, 'hp': 1760, 'physique': 200}, {},
     '虚空铸体，硬得不像话，是纯粹的肉身极致。'),
    ('art-wx-earth-t1', '承天载物功', '天', {'defense': 640, 'hp': 1760}, {},
     '承天载物，气量极大，防与血皆是天阶顶尖。'),
    ('art-earth-immortal', '土仙体', '天', {'attack': 60, 'defense': 300, 'hp': 1020, 'physique': 100},
     {'reflectDamage': 0.25},
     '土仙之躯，厚土护身，攻者反受其震。'),
    ('art-heaven-justice', '天罡正法', '天', {'defense': 360, 'hp': 980, 'spirit': 120, 'physique': 120},
     {'reflectDamage': 0.18},
     '天罡护体，神识根骨俱壮，反震护身。'),
    ('art-void-step', '虚空步', '天', {'attack': 280, 'speed': 280}, {'comboRate': 0.18},
     '踏虚而行，身法快极，一息之间连环出手。'),
    ('art-yin-yang-reincarnation', '阴阳轮回诀', '天', {'attack': 360, 'speed': 260, 'physique': 240}, {},
     '阴阳轮回，攻速根骨循环相生，绵长不绝。'),
    ('art-demon-god-fist', '魔神道音', '天', {'attack': 340, 'speed': 220}, {'comboRate': 0.18},
     '一声道音摄魂，身形随之突进，连绵追击。'),
    ('art-golden-immortal', '金仙剑', '天', {'attack': 360, 'speed': 440}, {},
     '金仙之剑，快字当先，出手如仙光一闪。'),
    ('art-divine-destruction', '诛仙剑诀', '天', {'defense': 440, 'speed': 360}, {},
     '剑势环身如诛仙之网，以守为攻，以速困敌。'),
    ('art-earth-evil', '地煞冥诀', '天', {'attack': 400, 'hp': 840, 'physique': 100}, {'lifeLeech': 0.09},
     '地煞入体，阴气噬敌，敌血尽为冥气所夺。'),
    ('art-xian-xian-sword', '陷仙剑诀', '天', {'attack': 580, 'defense': 100}, {'armorPenRate': 0.40},
     '一剑陷仙，四成防御在此剑下尽废。'),
    ('art-chaos-primal', '混沌归元功', '天', {'attack': 340, 'hp': 1020, 'physique': 140}, {'lifeLeech': 0.09},
     '混沌归元，攻时夺血归己，生生不竭。'),
    ('art-wx-metal-t1', '金仙不灭剑体', '天', {'attack': 520, 'defense': 160}, {'lifeLeech': 0.09},
     '剑体不灭，伤敌之血尽数归元，攻中自养。'),
]

TABLE_BY_ID = {row[0]: row for row in TABLE}
assert len(TABLE) == 89, '设计表必须 89 部'


# --------------------------------------------------------------------------- 锚点
# Cg() 的「功法属性汇总」段（含 forEach 收尾 `}});`）。运行时断言 count==1。
CG_OLD = ('function Cg(t){let r=0,a=0,l=0,c=0,d=0,u=0;'
          'const f=t.spiritualRoots||{metal:0,wood:0,water:0,fire:0,earth:0};'
          'YlxwArtRanked(t).forEach((E,YAq)=>{const N=is.find(k=>k.id===E);if(N){'
          'const k=go(N,f)*YlxwArtGrowth(t)*YlxwArtFactor(YAq);'
          'r+=Math.floor((N.effects.attack||0)*k),a+=Math.floor((N.effects.defense||0)*k),'
          'l+=Math.floor((N.effects.hp||0)*k),c+=Math.floor((N.effects.spirit||0)*k),'
          'd+=Math.floor((N.effects.physique||0)*k),u+=Math.floor((N.effects.speed||0)*k)}});')

_CG_HELPER = ('function YlxwBodySoftCap(v,cap){return v<=cap?v:cap+(v-cap)*%s}'
              % _num(SOFT_RATE))

_CG_BODY = ('if(N.type==="body"){'
            '_r244b[0]+=Math.floor((N.effects.attack||0)*k),'
            '_r244b[1]+=Math.floor((N.effects.defense||0)*k),'
            '_r244b[2]+=Math.floor((N.effects.hp||0)*k),'
            '_r244b[3]+=Math.floor((N.effects.spirit||0)*k),'
            '_r244b[4]+=Math.floor((N.effects.physique||0)*k),'
            '_r244b[5]+=Math.floor((N.effects.speed||0)*k)}else{'
            'r+=Math.floor((N.effects.attack||0)*k),'
            'a+=Math.floor((N.effects.defense||0)*k),'
            'l+=Math.floor((N.effects.hp||0)*k),'
            'c+=Math.floor((N.effects.spirit||0)*k),'
            'd+=Math.floor((N.effects.physique||0)*k),'
            'u+=Math.floor((N.effects.speed||0)*k)}')

_CG_MERGE = ('r+=YlxwBodySoftCap(_r244b[0],%d),a+=YlxwBodySoftCap(_r244b[1],%d),'
             'l+=YlxwBodySoftCap(_r244b[2],%d),c+=YlxwBodySoftCap(_r244b[3],%d),'
             'd+=YlxwBodySoftCap(_r244b[4],%d),u+=YlxwBodySoftCap(_r244b[5],%d);'
             % (SOFT_CAP['attack'], SOFT_CAP['defense'], SOFT_CAP['hp'],
                SOFT_CAP['spirit'], SOFT_CAP['physique'], SOFT_CAP['speed']))

CG_NEW = (_CG_HELPER + 'function Cg(t){let r=0,a=0,l=0,c=0,d=0,u=0,_r244b=[0,0,0,0,0,0];'
          'const f=t.spiritualRoots||{metal:0,wood:0,water:0,fire:0,earth:0};'
          'YlxwArtRanked(t).forEach((E,YAq)=>{const N=is.find(k=>k.id===E);if(N){'
          'const k=go(N,f)*YlxwArtGrowth(t)*YlxwArtFactor(YAq);'
          + _CG_BODY + '}});' + _CG_MERGE)

assert CG_NEW != CG_OLD and _CG_HELPER in CG_NEW and _CG_MERGE in CG_NEW


# --------------------------------------------------------------------------- 文本工具
def _extract_is_seg(txt):
    """抽取 `is=[...]` 段的完整文本（含两端方括号），括号配平 + 字符串态感知。"""
    m = re.search(r'\bis=\[', txt)
    if not m:
        return None
    b = txt.index('[', m.start())
    depth = 0
    i = b
    in_s = None
    esc = False
    n = len(txt)
    while i < n:
        ch = txt[i]
        if in_s:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == in_s:
                in_s = None
        else:
            if ch in ('"', "'", '`'):
                in_s = ch
            elif ch in '[{(':
                depth += 1
            elif ch in ']})':
                depth -= 1
                if depth == 0:
                    return txt[b:i + 1]
        i += 1
    return None


def _iter_elems(seg):
    """产出 seg（'[...]'）中每个顶层元素的 (start, end, text)。"""
    i = 1
    n = len(seg)
    while i < n:
        while i < n and seg[i] in ' \t\r\n,':
            i += 1
        if i >= n or seg[i] == ']':
            break
        start = i
        depth = 0
        in_s = None
        esc = False
        while i < n:
            ch = seg[i]
            if in_s:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == in_s:
                    in_s = None
            else:
                if ch in ('"', "'", '`'):
                    in_s = ch
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
            i += 1
        yield (start, i, seg[start:i])


def _brace_span(text, key):
    """定位 `key:{...}` 的 {...} 文本（含花括号）。找不到返回 None。"""
    k = text.find(key + ':{')
    if k < 0:
        return None
    i = k + len(key) + 1
    depth = 0
    in_s = None
    esc = False
    n = len(text)
    start = i
    while i < n:
        ch = text[i]
        if in_s:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == in_s:
                in_s = None
        else:
            if ch in ('"', "'", '`'):
                in_s = ch
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None


def _rewrite_elem(elem, row):
    """在单个体术元素文本内改写 effects / description（id/name/type/grade/... 逐字保留）。"""
    aid, name, grade, attrs, mech, desc = row

    # --- effects ---
    eff_text = _brace_span(elem, 'effects')
    if eff_text is None:
        raise AssertionError('%s 缺 effects 对象' % aid)
    eff = {}
    eff.update(attrs)
    eff.update(mech)
    new_eff_text = _fmt_effects(eff)
    k = elem.find('effects:')
    elem = elem[:k] + 'effects:' + new_eff_text + elem[k + len('effects:') + len(eff_text):]

    # --- description ---
    dm = re.search(r'description:"([^"]*)"', elem)
    if not dm:
        raise AssertionError('%s 缺 description' % aid)
    if dm.group(1) != desc:
        elem = elem[:dm.start()] + 'description:"%s"' % desc + elem[dm.end():]

    # --- name 校验（只校不改）---
    nm = re.search(r'name:"([^"]*)"', elem)
    if not nm:
        raise AssertionError('%s 缺 name' % aid)
    if nm.group(1) != name:
        raise AssertionError('%s 现值名称不符：%r != %r' % (aid, nm.group(1), name))
    return elem


def build_seg_new(seg_old):
    """把 seg_old 的 89 部体术改写为设计表形态，并在段首插入幂等标记。"""
    out = []
    last = 0
    hit = 0
    for start, end, elem in _iter_elems(seg_old):
        m = re.search(r'\{id:"([^"]+)"', elem)
        aid = m.group(1) if m else None
        if aid in TABLE_BY_ID and 'type:"body"' in elem:
            out.append(seg_old[last:start])
            out.append(_rewrite_elem(elem, TABLE_BY_ID[aid]))
            last = end
            hit += 1
    out.append(seg_old[last:])
    seg_new = ''.join(out)
    if hit != 89:
        raise AssertionError('改写命中体术 %d 部（期望 89）' % hit)
    seg_new = seg_new[:1] + MARK + seg_new[1:]
    return seg_new, hit


# --------------------------------------------------------------------------- 门禁
def gates(txt_out, seg_old, seg_new, cg_old, cg_new):
    """补丁后形态门禁：(label, needle, expect, op, note)。

    ★★ 语义说明（R-247，2026-10-11）：本环门禁是**「段落前后比对」型**——
      `seg_new` 是**本环产出**的 `is[]` 段，只对**套用时刻**自洽（断言「旧段清零 / 新段在位」）。
      **它不描述终态**：后续补丁（r247 给 9 部功法追加 `firstStrike` / `cuiti*` / `nixiu*` 字段）
      会合法改写这段内容 ⇒ 终态下 `seg_new` 自然不再逐字存在。
      ⇒ 这属**预期的跨补丁门禁演进**：终态由 **r247 自己的门禁**负责（断言那 9 部的新签名）。
      ★ 本函数签名带 5 参 ⇒ `dryrun_087.py`（自动派生名单）与 `localtest/diag_gate_drift.py`
      都**不会**在终态重跑它（两者的跳过逻辑会打印原因），故不存在「静默失败」。
    """
    g = []
    g.append(('幂等标记唯一', MARK, 1, '==', ''))
    g.append(('旧 is 段清零', seg_old, 0, '==', ''))
    g.append(('新 is 段在位', seg_new, 1, '==', ''))
    g.append(('旧 Cg 段清零', cg_old, 0, '==', ''))
    g.append(('新 Cg 段在位', cg_new, 1, '==', ''))
    g.append(('软上限助手在位', _CG_HELPER, 1, '==', ''))
    g.append(('Cg 体术分流在位', '_r244b[0]+=Math.floor((N.effects.attack||0)*k)', 1, '==', ''))
    g.append(('Cg 软上限接入在位', 'r+=YlxwBodySoftCap(_r244b[0],6000)', 1, '==', ''))
    for row in TABLE:
        g.append(('体术 id 在位 %s' % row[0], '{id:"%s"' % row[0], 1, '==', ''))
    return g


FREEZE = [
    # 心法侧一字未动（R240 标记仍在）
    ('冻结·心法 R240 标记', 'YLXW_R240_V2953', 1),
    # 体术 learn 增量点未动（本环只改汇总侧，不改习得侧）
    ('冻结·体术 learn 增量点', 'if(m.type==="body"&&(R+=Math.floor((m.effects.attack||0)*h)', 1),
    # 属性明细面板累加器未动
    ('冻结·属性面板累加器', 'YlxwArtAdd(X,ue.effects,YlxwArtGrowth(a)*YlxwArtFactor(YAq))', 1),
    # 协同 / 装备 / 天赋 / 称号 聚合未动
    ('冻结·协同 fy', 'function fy(t){const r={};for(const a of t)for(const[l,c]of Object.entries(a.effects))', 1),
    ('冻结·装备聚合', 'j.forEach(E=>{if(E&&E.effect){const N=E.id===t.natalArtifactId', 1),
    ('冻结·天赋聚合', 'for(const E of h){const N=Un.find(k=>k.id===E);N&&(r+=N.effects.attack||0', 1),
    ('冻结·称号聚合', 'const R=Ln.find(E=>E.id===t.titleId);return R&&(r+=R.effects.attack||0', 1),
]


def _precheck():
    assert len(TABLE) == 89
    assert MARK == '/*[r244body]*/'
    ids = [r[0] for r in TABLE]
    assert len(set(ids)) == 89, '体术 id 有重复'
    for r in TABLE:
        assert r[5], '%s 描述为空' % r[0]
        for k in r[3]:
            assert k in ('attack', 'defense', 'hp', 'spirit', 'speed', 'physique'), \
                '%s 非法属性键 %s' % (r[0], k)
        for k in r[4]:
            assert k in MECH_CN, '%s 非法机制键 %s' % (r[0], k)
        assert r[3] or r[4], '%s 属性与机制同时为空' % r[0]
    assert CG_OLD not in CG_NEW and _CG_BODY in CG_NEW and _CG_MERGE in CG_NEW, \
        'CG_NEW 形态异常'
    return True


def _classify(txt):
    if MARK in txt:
        return 'patched'
    return 'baseline'


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe',
            'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    node = _find_node()
    if not node:
        print('  [WARN] 未找到 node，跳过 node --check')
        return True, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
        r = subprocess.run([node, '--check', tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            print('  [FAIL] node --check 未通过:\n%s'
                  % r.stderr.decode('utf-8', 'replace')[:2000])
            return False, node
        return True, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _apply(txt0):
    """返回 (out_text, seg_old, seg_new, cg_old, cg_new, err)。"""
    seg_old = _extract_is_seg(txt0)
    if seg_old is None:
        return None, None, None, None, None, '未定位到 is=[...] 段'
    c = txt0.count(seg_old)
    if c != 1:
        return None, None, None, None, None, 'is 段在源文件中出现 %d 次（期望 1）' % c
    try:
        seg_new, _hit = build_seg_new(seg_old)
    except AssertionError as e:
        return None, None, None, None, None, str(e)
    if txt0.count(seg_new) != 0:
        return None, None, None, None, None, '新 is 段已在基线出现'
    # --- Cg 软上限 ---
    cg_old, cg_new = CG_OLD, CG_NEW
    if txt0.count(cg_old) != 1:
        return None, None, None, None, None, 'Cg 段在源文件中出现 %d 次（期望 1）' % txt0.count(cg_old)
    if txt0.count(cg_new) != 0:
        return None, None, None, None, None, '新 Cg 段已在基线出现'
    out = txt0.replace(seg_old, seg_new, 1).replace(cg_old, cg_new, 1)
    return out, seg_old, seg_new, cg_old, cg_new, None


# --------------------------------------------------------------------------- 自证：属性签名逐部比对
def _parse_effects(eff_text):
    """从 effects 对象文本解析 {key: num}（含机制小数）。"""
    d = {}
    for km, vm in re.findall(r'([A-Za-z_]\w*)\s*:\s*(-?(?:\d+\.\d*|\.\d+|\d+))', eff_text):
        d[km] = float(vm) if ('.' in vm) else int(vm)
    return d


def verify_signature(seg_new):
    """逐部核对「打补丁后 属性/机制/描述 == 策划表」。返回 (匹配数, 不匹配清单)。"""
    bad = []
    seen = set()
    for _st, _en, elem in _iter_elems(seg_new):
        m = re.search(r'\{id:"([^"]+)"', elem)
        aid = m.group(1) if m else None
        if aid not in TABLE_BY_ID or 'type:"body"' not in elem:
            continue
        seen.add(aid)
        _aid, name, _g, attrs, mech, desc = TABLE_BY_ID[aid]
        eff = _parse_effects(_brace_span(elem, 'effects') or '')
        want = {}
        want.update(attrs)
        want.update(mech)
        got = {k: (int(v) if float(v) == int(v) else round(float(v), 6)) for k, v in eff.items()}
        wnt = {k: (int(v) if float(v) == int(v) else round(float(v), 6)) for k, v in want.items()}
        dg = re.search(r'description:"([^"]*)"', elem)
        got_desc = dg.group(1) if dg else None
        if got != wnt or got_desc != desc:
            bad.append((aid, name, got, wnt, got_desc, desc))
    missing = [r[0] for r in TABLE if r[0] not in seen]
    for aid in missing:
        bad.append((aid, TABLE_BY_ID[aid][1], None, 'MISSING', None, None))
    return len(TABLE) - len(bad), bad


def softcap_report():
    """构造「全 89 部叠加」合成输入：各属性加总 → 过软上限后。"""
    sums = {k: 0 for k in SOFT_CAP}
    for _aid, _n, _g, attrs, mech, _d in TABLE:
        for k, v in attrs.items():
            sums[k] += v
    capped = {k: soft_cap(sums[k], SOFT_CAP[k]) for k in SOFT_CAP}
    return sums, capped


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description='R-244 体术 89 部数据层 + 叠加软上限（客户端 --src 补丁）')
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()

    try:
        _precheck()
    except AssertionError as e:
        print('[FAIL] 断言失败: %s' % e)
        return 1

    if not os.path.exists(a.src):
        print('[FAIL] source not found: %s' % a.src)
        return 2

    with io.open(a.src, 'rb') as f:
        txt0 = f.read().decode('utf-8', 'replace')

    if _classify(txt0) == 'patched':
        print('[SKIP] source looks already patched（R-244 体术 89 部 + 软上限已落地）')
        return 3

    out, seg_old, seg_new, cg_old, cg_new, err = _apply(txt0)
    if err is not None:
        print('[FAIL] %s' % err)
        return 2

    # 门禁
    ok = True
    for label, needle, exp, op, note in gates(out, seg_old, seg_new, cg_old, cg_new):
        act = out.count(needle)
        good = (act == exp) if op == '==' else (act >= exp)
        ok = ok and good
        if not good:
            print('  [FAIL] %-40s actual=%d expect %d' % (label, act, exp))
    for label, needle, cnt in FREEZE:
        act = out.count(needle)
        good = (act == cnt)
        ok = ok and good
        if not good:
            print('  [FAIL] %-40s actual=%d expect %d' % (label, act, cnt))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  [OK] 门禁全绿（体术 89 部；冻结 %d 项）' % len(FREEZE))

    # 属性签名逐部比对
    nmatch, bad = verify_signature(seg_new)
    print('  [%s] 属性签名逐部比对：%d/%d 匹配'
          % ('OK' if nmatch == 89 else 'FAIL', nmatch, 89))
    for row in bad[:20]:
        print('      [MISMATCH] %s' % (row,))
    if nmatch != 89:
        print('[FAIL] 属性签名不匹配 %d 部，未写盘' % len(bad))
        return 1

    # 软上限单测
    sums, capped = softcap_report()
    print('  [软上限单测] 全 89 部叠加 → 加总 / 过软上限(方案 A, 超额30%)：')
    for k in ('attack', 'defense', 'hp', 'speed', 'physique', 'spirit'):
        print('      %-9s 加总=%-7d 软上限=%-6d 衰减后=%.1f'
              % (k, sums[k], SOFT_CAP[k], capped[k]))

    # 往返自证
    back = out.replace(seg_new, seg_old, 1).replace(cg_new, cg_old, 1)
    if back != txt0:
        print('[FAIL] round-trip mismatch')
        return 1
    print('  [OK] 往返自证：逆向还原后逐字节相等')

    out_bytes = out.encode('utf-8')
    src_bytes = txt0.encode('utf-8')
    print('  delta = %+d bytes  (%d -> %d)'
          % (len(out_bytes) - len(src_bytes), len(src_bytes), len(out_bytes)))

    # node 自检
    nok, node = _node_check(out)
    if not nok:
        print('[FAIL] node --check 失败，未写盘')
        return 1
    print('  [OK] node --check 通过 (%s)' % (node or 'skipped'))

    if a.check or a.selftest:
        print('[r244] check OK: 89 部体术重写 + 软上限、门禁全绿、签名 89/89、往返一致')
        return 0

    # .bak + 原子写回
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = a.src + '.bak-r244-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src_bytes)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(a.src)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r244-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out_bytes)
        os.replace(tmp, a.src)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print('  已原子写回 %s' % a.src)
    return 0


if __name__ == '__main__':
    sys.exit(main())
