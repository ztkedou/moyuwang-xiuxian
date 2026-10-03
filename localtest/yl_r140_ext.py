# -*- coding: utf-8 -*-
r"""
yl_r140_ext.py — R-140 消耗品数值重构 · 批 1（纯数值表；客户端 standalone · 0.9.17 批次）

需求原文（台账 R-140，用户逐字）
--------------------------------------------------------------------------
  「所有可使用的如药草，丹药这些数值需要全部重构，因为这些东西不限量使用，如果数值过高
    会导致低等级轻易就能获得大量数值加强。一是可使用物品方面：低稀有度不加稀有属性，
    高稀有度数值减少并且售价提高，获取几率变小。那种升段位只能使用一次的奇物类道具不改。」

唯一真源
--------------------------------------------------------------------------
  docs/0.9.17-design/R140-消耗品数值重构.md
    · §3.1 新 fg 品质地板表      · §3.2 新 Ic 系数 + Rr/mw + DN 纯度
    · §3.5 爆表丹药重做          · §3.6 全量运行时丹药表（21 条，改 13 条）
    · §3.7 全量运行时草药表（7 条带 effect）
    · §6   死键处置（effect 里的 spirit/physique/attack → 删除）
    · §9   清单标「批 1」的数值行
  基线 = build/assets/index-v2916-20261003.js（2,285,822 B，md5 a59ac4496ab0e8ab81fdb147b45488ec）

==============================================================================
一、本脚本做什么（批 1 = 纯数值，无引擎逻辑改动）
==============================================================================
  【1】fg 品质地板表（@310384，1 处）—— 整体压到约旧值 1/4；普通/稀有 的
       spirit/physique 置 0（兑现「低稀有度不加稀有属性」；ry 里地板写法
       `M.spirit?Math.max(h,M.spirit):h`，0 为 falsy ⇒ 自动跳过）。
  【2】Rr 250→40、mw 5000→1200（@534883，1 处）—— yg 的仙品地板。
  【3】Ic 系数（@572462，2 处）—— effect u*2→u*1；permanentEffect u*1.5→u*0.8。
  【4】DN 炼丹纯度（@321629，1 处）—— effect 1.5+*0.025→1.2+*0.02；
       permanentEffect 1.0+*0.0125→0.7+*0.01。
  【5】yg 地板函数（@572084）—— 不改代码；它按标识符读 Rr/mw，随【2】自动生效
       （gates 里加断言证明 yg 体内确有 Math.max(t.exp,mw)/Math.max(t.hp,Rr)）。
  【6】Dm/Vr 丹药 result（@295860 / @298699，共 13 条改值）—— §3.5/§3.6：
       聚气丹/回春丹/洗髓丹/筑基丹/龙血丹/九转金丹/不死仙丹/破境丹/仙灵丹/
       天元丹/结金丹/凝魂丹/凤凰涅槃丹。
  【7】AN/ta 草药（@302601 / @294965，共 7 条改值）—— §3.7：
       凝神花/回气草/千年灵芝/万年仙草/九叶芝草/龙鳞果（AN）+ 止血草（ta）。
  【8】死键删除（并入【6】【7】）—— §6：effect 里 Ig 从不消费的永久属性键
       （仙灵丹 effect.spirit/physique、结金丹 effect.spirit、凝魂丹 effect.spirit、
        凤凰涅槃丹 effect.attack、凝神花 effect.spirit）一律删除。

==============================================================================
二、关键前提（已实测，勿推翻）
==============================================================================
  ★ 客户端不读 srv/game-dicts.json（bundle 内 `game-dicts` 出现 0 次）。
    字典里的 33 丹药 / 20 草药多为 bundle 内 0 次出现；**只改客户端内嵌表**。
    §9 第 15 行（game-dicts 同步）整行跳过 —— 本脚本不碰 srv/**。
  ★ 不碰：ny 境界系数（§3.3 定「不动」）、装备 iy 的 spirit/speed 独立分支、
    HN 兜底表（R-107 冻结面，§8.1）、Ct（只是 us.*() 的名字引用，值随 Dm/Vr 变）。
  ★ 「breakthrough 升段类 7 条道具」（§7 N1）= game-dicts 里的
    [练气]筑基丹(.3/.6) / [练气]结金丹(.5/.8) / [练气]破境丹(.5) /
    [大乘]天元果(.1) / [大乘]金仙果(.3)。这些是 **game-dicts** 条目（bundle 内
    `天元果`/`金仙果` 出现 0 次，且全 bundle 无 `breakthrough:` effect 键）⇒
    本脚本天然不碰，逐字未变。
    注意命名撞车：客户端 pi() 池里的「筑基丹/结金丹/破境丹」是**炼丹产出**的
    可重复服用丹药（无 breakthrough 键），按 §3.6 #4 明确「可改」，本脚本照改。

==============================================================================
三、契约（standalone · 同 localtest/yl_r135_ext.py）
==============================================================================
  · CLI 只有 --src <js>；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r140-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=锚点不符/文件不可用；
    1=断言失败。
  · gates() 返回五元组 (name, needle, count, op, note)；_precheck() + 往返自证。
  · 纯客户端；不改 srv/**、build_v26n.py、CHANGELOG*、其它 yl_*_ext.py、产物本体。
  · **不进 V28_MODULES**（standalone，由装配层 apply_standalone() 按序套用）。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 在位标记

MARK = '/*YLXW_R140_V2916*/'   # 幂等/在位标记，仅植入 fg 替换（全库唯一）

# =========================================================================== 锚点
# 全部实测：旧锚点在基线 bundle 内 count==1；新锚点在基线内 count==0。

# 【1】fg 品质地板表（§3.1）
FG_OLD = ('fg={普通:{hp:80,exp:40,spirit:3,physique:3,maxHp:8},'
          '稀有:{hp:280,exp:180,spirit:12,physique:12,maxHp:35},'
          '传说:{hp:900,exp:700,spirit:55,physique:55,maxHp:120},'
          '仙品:{hp:2600,exp:2200,spirit:180,physique:180,maxHp:380}}')
FG_NEW = (MARK +
          'fg={普通:{hp:20,exp:12,spirit:0,physique:0,maxHp:3},'
          '稀有:{hp:70,exp:45,spirit:0,physique:0,maxHp:10},'
          '传说:{hp:220,exp:170,spirit:12,physique:12,maxHp:30},'
          '仙品:{hp:650,exp:550,spirit:40,physique:40,maxHp:95}}')

# 【2】yg 仙品地板常量（§3.2）
RRMW_OLD = 'Rr=250,mw=5e3'
RRMW_NEW = 'Rr=40,mw=1200'

# 【3】Ic 缩放系数（§3.2）
IC_EFF_OLD = 'if(c){const u=l*2;'
IC_EFF_NEW = 'if(c){const u=l*1;'
IC_PERM_OLD = 'if(d){const u=l*1.5;'
IC_PERM_NEW = 'if(d){const u=l*.8;'

# 【4】DN 炼丹纯度系数（§3.2）
DN_OLD = ('DN=(t,r,a)=>{const l=1.5+(Math.max(60,a)-60)*.025,'
          'c=1+(Math.max(60,a)-60)*.0125;'
          'return{effect:t?gm(t,l):void 0,permanentEffect:r?gm(r,c):void 0}}')
DN_NEW = ('DN=(t,r,a)=>{const l=1.2+(Math.max(60,a)-60)*.02,'
          'c=.7+(Math.max(60,a)-60)*.01;'
          'return{effect:t?gm(t,l):void 0,permanentEffect:r?gm(r,c):void 0}}')

# 【6】Dm 丹药 result（§3.5/§3.6）
P_JUQI_OLD = 'rarity:"普通",effect:{exp:150}}'
P_JUQI_NEW = 'rarity:"普通",effect:{exp:120}}'

P_HUICHUN_OLD = 'rarity:"稀有",effect:{hp:200}}},{name:"洗髓丹"'
P_HUICHUN_NEW = 'rarity:"稀有",effect:{hp:150}}},{name:"洗髓丹"'

P_XISUI_OLD = 'rarity:"稀有",permanentEffect:{maxHp:50}}},{name:"筑基丹"'
P_XISUI_NEW = 'rarity:"稀有",permanentEffect:{maxHp:30}}},{name:"筑基丹"'

P_ZHUJI_OLD = 'effect:{exp:500},permanentEffect:{spirit:30,physique:3,maxHp:100}'
P_ZHUJI_NEW = 'effect:{exp:400},permanentEffect:{spirit:8,physique:3,maxHp:60}'

P_LONGXUE_OLD = 'permanentEffect:{maxHp:500,physique:5}'
P_LONGXUE_NEW = 'permanentEffect:{maxHp:200,physique:4}'

P_JIUZHUAN_OLD = ('effect:{exp:5e4},permanentEffect:{maxLifespan:5,spirit:100,'
                  'attack:1e3,defense:1e3,physique:100,speed:100}')
P_JIUZHUAN_NEW = ('effect:{exp:2e4},permanentEffect:{maxLifespan:5,spirit:20,'
                  'attack:120,defense:120,physique:20,speed:20}')

P_BUSI_OLD = 'effect:{lifespan:10},permanentEffect:{maxLifespan:10}'
P_BUSI_NEW = 'effect:{lifespan:5},permanentEffect:{maxLifespan:8}'

# 【6】Vr 丹药 result（§3.5/§3.6）
P_POJING_OLD = ('rarity:"传说",effect:{exp:1e4},'
                'permanentEffect:{spirit:5,physique:5,attack:30,defense:30}')
P_POJING_NEW = ('rarity:"传说",effect:{exp:8e3},'
                'permanentEffect:{spirit:3,physique:3,attack:20,defense:20}')

P_XIANLING_OLD = ('rarity:"传说",effect:{exp:2e3,spirit:50,physique:50},'
                  'permanentEffect:{maxLifespan:3,spirit:30,attack:300,'
                  'defense:300,physique:30,speed:30}')
P_XIANLING_NEW = ('rarity:"传说",effect:{exp:1500},'
                  'permanentEffect:{maxLifespan:3,spirit:10,attack:60,'
                  'defense:60,physique:10,speed:10}')

P_TIANYUAN_OLD = ('effect:{exp:1e4},permanentEffect:{maxLifespan:5,spirit:50,'
                  'attack:500,defense:500,physique:50,speed:50}')
P_TIANYUAN_NEW = ('effect:{exp:8e3},permanentEffect:{maxLifespan:5,spirit:15,'
                  'attack:90,defense:90,physique:15,speed:15}')

P_JIEJIN_OLD = 'effect:{exp:3e4,spirit:20},permanentEffect:{spirit:5,maxHp:200}'
P_JIEJIN_NEW = 'effect:{exp:2e4},permanentEffect:{spirit:3,maxHp:120}'

P_NINGHUN_OLD = ('effect:{exp:1e4,spirit:50,hp:300},'
                 'permanentEffect:{spirit:10,maxHp:300,attack:50}')
P_NINGHUN_NEW = ('effect:{exp:8e3,hp:200},'
                 'permanentEffect:{spirit:6,maxHp:150,attack:20}')

P_FENGHUANG_OLD = ('effect:{hp:800,exp:1500,attack:30},'
                   'permanentEffect:{maxHp:400,attack:100,defense:100,'
                   'spirit:8,physique:8,speed:5}')
P_FENGHUANG_NEW = ('effect:{hp:600,exp:1200},'
                   'permanentEffect:{maxHp:200,attack:40,defense:40,'
                   'spirit:4,physique:4,speed:3}')

# 【7】AN 草药（§3.7）
H_NINGSHEN_OLD = 'effect:{hp:50,spirit:5},permanentEffect:{spirit:50}'
H_NINGSHEN_NEW = 'effect:{hp:40},permanentEffect:{spirit:6}'

H_HUIQI_OLD = 'effect:{hp:300},permanentEffect:{maxHp:50}'
H_HUIQI_NEW = 'effect:{hp:150},permanentEffect:{maxHp:20}'

H_QIANNIAN_OLD = ('effect:{hp:1500},'
                  'permanentEffect:{maxHp:400,spirit:20,physique:15,maxLifespan:3}')
H_QIANNIAN_NEW = ('effect:{hp:400},'
                  'permanentEffect:{maxHp:150,spirit:6,physique:6,maxLifespan:3}')

H_WANNIAN_OLD = ('effect:{hp:1e4},'
                 'permanentEffect:{maxHp:1e3,spirit:100,physique:80,speed:50,maxLifespan:5}')
H_WANNIAN_NEW = ('effect:{hp:1500},'
                 'permanentEffect:{maxHp:300,spirit:15,physique:15,speed:12,maxLifespan:5}')

H_JIUYE_OLD = ('effect:{hp:2500},'
               'permanentEffect:{maxHp:800,spirit:600,physique:500,defense:300}')
H_JIUYE_NEW = ('effect:{hp:600},'
               'permanentEffect:{maxHp:200,spirit:12,physique:12,defense:40}')

H_LONGLIN_OLD = 'effect:{hp:1200},permanentEffect:{physique:150,maxHp:300}'
H_LONGLIN_NEW = 'effect:{hp:350},permanentEffect:{physique:8,maxHp:80}'

# 【7】ta 草药（§3.7）
H_ZHIXUE_OLD = 'effect:{hp:200}},{id:"spirit-gathering-grass"'
H_ZHIXUE_NEW = 'effect:{hp:120}},{id:"spirit-gathering-grass"'


EDITS = [
    # ---- 缩放链常量 ----
    ('R140-1 fg 品质地板表（约 −75%；普通/稀有 spirit/physique 置 0）', FG_OLD, FG_NEW),
    ('R140-2 yg 仙品地板常量 Rr 250→40 / mw 5000→1200', RRMW_OLD, RRMW_NEW),
    ('R140-3a Ic effect 系数 u*2→u*1', IC_EFF_OLD, IC_EFF_NEW),
    ('R140-3b Ic permanentEffect 系数 u*1.5→u*0.8', IC_PERM_OLD, IC_PERM_NEW),
    ('R140-4 DN 炼丹纯度系数下调', DN_OLD, DN_NEW),
    # ---- Dm 丹药 ----
    ('R140-6a 聚气丹 effect.exp 150→120', P_JUQI_OLD, P_JUQI_NEW),
    ('R140-6b 回春丹 effect.hp 200→150', P_HUICHUN_OLD, P_HUICHUN_NEW),
    ('R140-6c 洗髓丹 perm.maxHp 50→30', P_XISUI_OLD, P_XISUI_NEW),
    ('R140-6d 筑基丹 exp 500→400 / spirit 30→8 / maxHp 100→60', P_ZHUJI_OLD, P_ZHUJI_NEW),
    ('R140-6e 龙血丹 maxHp 500→200 / physique 5→4', P_LONGXUE_OLD, P_LONGXUE_NEW),
    ('R140-6f 九转金丹 exp 5e4→2e4 / atk,def 1e3→120 / spirit,phys,speed 100→20',
     P_JIUZHUAN_OLD, P_JIUZHUAN_NEW),
    ('R140-6g 不死仙丹 lifespan 10→5 / maxLifespan 10→8', P_BUSI_OLD, P_BUSI_NEW),
    # ---- Vr 丹药 ----
    ('R140-6h 破境丹 exp 1e4→8e3 / spirit,phys 5→3 / atk,def 30→20', P_POJING_OLD, P_POJING_NEW),
    ('R140-6i 仙灵丹 exp 2e3→1500 / 删 effect.spirit,physique / perm 全降',
     P_XIANLING_OLD, P_XIANLING_NEW),
    ('R140-6j 天元丹 exp 1e4→8e3 / atk,def 500→90 / spirit,phys,speed 50→15',
     P_TIANYUAN_OLD, P_TIANYUAN_NEW),
    ('R140-6k 结金丹 exp 3e4→2e4 / 删 effect.spirit / spirit 5→3 / maxHp 200→120',
     P_JIEJIN_OLD, P_JIEJIN_NEW),
    ('R140-6l 凝魂丹 exp 1e4→8e3 / 删 effect.spirit / hp 300→200 / perm 全降',
     P_NINGHUN_OLD, P_NINGHUN_NEW),
    ('R140-6m 凤凰涅槃丹 删 effect.attack / hp 800→600 / exp 1500→1200 / perm 全降',
     P_FENGHUANG_OLD, P_FENGHUANG_NEW),
    # ---- AN 草药 ----
    ('R140-7a 凝神花 删 effect.spirit / hp 50→40 / perm.spirit 50→6',
     H_NINGSHEN_OLD, H_NINGSHEN_NEW),
    ('R140-7b 回气草 hp 300→150 / maxHp 50→20', H_HUIQI_OLD, H_HUIQI_NEW),
    ('R140-7c 千年灵芝 hp 1500→400 / maxHp 400→150 / spirit,phys 20,15→6',
     H_QIANNIAN_OLD, H_QIANNIAN_NEW),
    ('R140-7d 万年仙草 hp 1e4→1500 / maxHp 1e3→300 / spirit,phys 100,80→15 / speed 50→12',
     H_WANNIAN_OLD, H_WANNIAN_NEW),
    ('R140-7e 九叶芝草 hp 2500→600 / maxHp 800→200 / spirit,phys 600,500→12 / def 300→40',
     H_JIUYE_OLD, H_JIUYE_NEW),
    ('R140-7f 龙鳞果 hp 1200→350 / physique 150→8 / maxHp 300→80',
     H_LONGLIN_OLD, H_LONGLIN_NEW),
    ('R140-7g 止血草 hp 200→120', H_ZHIXUE_OLD, H_ZHIXUE_NEW),
]

# --------------------------------------------------------------------------- 冻结串
# yg 地板函数（@572084）—— 不改代码；断言它按标识符读 Rr/mw（随【2】自动生效）
FRZ_YG_MW = 't.exp=Math.max(t.exp,mw)'
FRZ_YG_RR = 't.hp=Math.max(t.hp,Rr)'
# ny 境界系数（§3.3 不动）
FRZ_NY = 'ny=[1,1.25,1.75,2.5,3.5,5,7]'
# 奇物类（game-dicts）在 bundle 内 0 次；断言其不存在（本脚本不新增）
FRZ_TIANYUANGUO = '天元果'
FRZ_JINXIANGUO = '金仙果'
# §3.6「不动」的丹药逐字保留
FRZ_YANSHOU = 'rarity:"稀有",effect:{lifespan:1}'                      # 延寿丹
FRZ_CHANGSHENG = 'rarity:"传说",permanentEffect:{maxLifespan:3}'       # 长生丹
FRZ_XILING = 'permanentEffect:{spiritualRoots:{metal:5,wood:5,water:5,fire:5,earth:5}}'  # 洗灵丹
FRZ_WUXING = 'permanentEffect:{spiritualRoots:{metal:3,wood:3,water:3,fire:3,earth:3}}'  # 五行灵丹
FRZ_TIANLING = 'permanentEffect:{spiritualRoots:{metal:10,wood:10,water:10,fire:10,earth:10}}'  # 天灵根丹
FRZ_NINGSHEN_DAN = 'rarity:"稀有",permanentEffect:{spirit:2}'          # 凝神丹（专职丹，§10-Q2 保留）
FRZ_QIANGTI_DAN = 'rarity:"稀有",permanentEffect:{physique:2}'         # 强体丹（专职丹）
# 废丹（§3.6 #21 不动）
FRZ_FEIDAN = ('{name:"废丹",type:H.Pill,description:"炼丹失败后的残留物，'
              '不仅毫无用处，服用后还可能损伤经脉。",rarity:"普通",effect:{hp:-50}}')
# HN 兜底表（R-107 冻结面，§8.1 不同步改）
FRZ_HN_QIANGTI = '强体丹:{permanentEffect:{physique:20}}'
# Ct 名字引用表（值随 Dm/Vr 变，引用本身不动）
FRZ_CT = 'Ct={聚气丹:us.聚气丹(),回春丹:us.回春丹(),洗髓丹:us.洗髓丹(),'


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note) —— 供 dryrun 门禁表收录。"""
    g = [
        # ===================== 在位标记 =====================
        ('R140·在位标记存在', MARK, 1, '==', 'YLXW_R140_V2916'),

        # ===================== 【1】fg =====================
        ('R140-1·新 fg 表在位', FG_NEW, 1, '==', '约旧值 1/4'),
        ('R140-1·旧 fg 表清零', FG_OLD, 0, '==', ''),
        ('R140-1·普通地板 spirit 归零', '普通:{hp:20,exp:12,spirit:0,physique:0,maxHp:3}', 1, '==', 'G1 低稀有度不加稀有属性'),
        ('R140-1·稀有地板 spirit 归零', '稀有:{hp:70,exp:45,spirit:0,physique:0,maxHp:10}', 1, '==', 'G1'),

        # ===================== 【2】Rr/mw =====================
        ('R140-2·新 Rr/mw 在位', RRMW_NEW, 1, '==', 'Rr40/mw1200'),
        ('R140-2·旧 Rr/mw 清零', RRMW_OLD, 0, '==', ''),

        # ===================== 【3】Ic =====================
        ('R140-3a·新 Ic effect 系数在位', IC_EFF_NEW, 1, '==', 'u*1'),
        ('R140-3a·旧 Ic effect 系数清零', IC_EFF_OLD, 0, '==', '原 u*2'),
        ('R140-3b·新 Ic perm 系数在位', IC_PERM_NEW, 1, '==', 'u*0.8'),
        ('R140-3b·旧 Ic perm 系数清零', IC_PERM_OLD, 0, '==', '原 u*1.5'),

        # ===================== 【4】DN =====================
        ('R140-4·新 DN 系数在位', DN_NEW, 1, '==', ''),
        ('R140-4·旧 DN 系数清零', DN_OLD, 0, '==', ''),

        # ===================== 【5】yg 读新值（不改代码，断言其读 Rr/mw） =====================
        ('R140-5·yg 读修为地板 mw', FRZ_YG_MW, 1, '==', '随【2】mw=1200 自动生效'),
        ('R140-5·yg 读属性地板 Rr', FRZ_YG_RR, 1, '==', '随【2】Rr=40 自动生效'),

        # ===================== 【6】丹药（新形态在位 + 旧形态清零） =====================
        ('R140-6a·聚气丹已降', P_JUQI_NEW, 1, '==', ''),
        ('R140-6a·旧聚气丹清零', P_JUQI_OLD, 0, '==', ''),
        ('R140-6b·回春丹已降', P_HUICHUN_NEW, 1, '==', ''),
        ('R140-6b·旧回春丹清零', P_HUICHUN_OLD, 0, '==', ''),
        ('R140-6c·洗髓丹已降', P_XISUI_NEW, 1, '==', ''),
        ('R140-6c·旧洗髓丹清零', P_XISUI_OLD, 0, '==', ''),
        ('R140-6d·筑基丹已降', P_ZHUJI_NEW, 1, '==', '炼丹产出，非 breakthrough'),
        ('R140-6d·旧筑基丹清零', P_ZHUJI_OLD, 0, '==', ''),
        ('R140-6e·龙血丹已降', P_LONGXUE_NEW, 1, '==', ''),
        ('R140-6e·旧龙血丹清零', P_LONGXUE_OLD, 0, '==', ''),
        ('R140-6f·九转金丹已降', P_JIUZHUAN_NEW, 1, '==', '爆表重做'),
        ('R140-6f·旧九转金丹清零', P_JIUZHUAN_OLD, 0, '==', ''),
        ('R140-6g·不死仙丹已降', P_BUSI_NEW, 1, '==', ''),
        ('R140-6g·旧不死仙丹清零', P_BUSI_OLD, 0, '==', ''),
        ('R140-6h·破境丹已降', P_POJING_NEW, 1, '==', '炼丹产出，非 breakthrough'),
        ('R140-6h·旧破境丹清零', P_POJING_OLD, 0, '==', ''),
        ('R140-6i·仙灵丹已降', P_XIANLING_NEW, 1, '==', '删死键 effect.spirit/physique'),
        ('R140-6i·旧仙灵丹清零', P_XIANLING_OLD, 0, '==', ''),
        ('R140-6j·天元丹已降', P_TIANYUAN_NEW, 1, '==', '爆表重做'),
        ('R140-6j·旧天元丹清零', P_TIANYUAN_OLD, 0, '==', ''),
        ('R140-6k·结金丹已降', P_JIEJIN_NEW, 1, '==', '删死键 effect.spirit'),
        ('R140-6k·旧结金丹清零', P_JIEJIN_OLD, 0, '==', ''),
        ('R140-6l·凝魂丹已降', P_NINGHUN_NEW, 1, '==', '删死键 effect.spirit'),
        ('R140-6l·旧凝魂丹清零', P_NINGHUN_OLD, 0, '==', ''),
        ('R140-6m·凤凰涅槃丹已降', P_FENGHUANG_NEW, 1, '==', '删死键 effect.attack'),
        ('R140-6m·旧凤凰涅槃丹清零', P_FENGHUANG_OLD, 0, '==', ''),

        # ===================== 【7】草药 =====================
        ('R140-7a·凝神花已降', H_NINGSHEN_NEW, 1, '==', '删死键 effect.spirit'),
        ('R140-7a·旧凝神花清零', H_NINGSHEN_OLD, 0, '==', ''),
        ('R140-7b·回气草已降', H_HUIQI_NEW, 1, '==', ''),
        ('R140-7b·旧回气草清零', H_HUIQI_OLD, 0, '==', ''),
        ('R140-7c·千年灵芝已降', H_QIANNIAN_NEW, 1, '==', 'R-107 遗留 P2'),
        ('R140-7c·旧千年灵芝清零', H_QIANNIAN_OLD, 0, '==', ''),
        ('R140-7d·万年仙草已降', H_WANNIAN_NEW, 1, '==', 'R-107 遗留 P3'),
        ('R140-7d·旧万年仙草清零', H_WANNIAN_OLD, 0, '==', ''),
        ('R140-7e·九叶芝草已降', H_JIUYE_NEW, 1, '==', 'spirit600/phys500 −98%'),
        ('R140-7e·旧九叶芝草清零', H_JIUYE_OLD, 0, '==', ''),
        ('R140-7f·龙鳞果已降', H_LONGLIN_NEW, 1, '==', ''),
        ('R140-7f·旧龙鳞果清零', H_LONGLIN_OLD, 0, '==', ''),
        ('R140-7g·止血草已降', H_ZHIXUE_NEW, 1, '==', ''),
        ('R140-7g·旧止血草清零', H_ZHIXUE_OLD, 0, '==', ''),

        # ===================== 冻结：不改项 =====================
        ('冻结·ny 境界系数未动', FRZ_NY, 1, '==', '§3.3'),
        ('冻结·奇物天元果不在 bundle', FRZ_TIANYUANGUO, 0, '==', 'game-dicts 专有'),
        ('冻结·奇物金仙果不在 bundle', FRZ_JINXIANGUO, 0, '==', 'game-dicts 专有'),
        ('冻结·延寿丹未动', FRZ_YANSHOU, 1, '==', 'R-107 已定档'),
        ('冻结·长生丹未动', FRZ_CHANGSHENG, 1, '==', ''),
        ('冻结·洗灵丹灵根未动', FRZ_XILING, 1, '==', 'R4'),
        ('冻结·五行灵丹灵根未动', FRZ_WUXING, 1, '==', 'R4'),
        ('冻结·天灵根丹灵根未动', FRZ_TIANLING, 1, '==', 'R4'),
        ('冻结·凝神丹未动', FRZ_NINGSHEN_DAN, 1, '==', '专职丹 §10-Q2'),
        ('冻结·强体丹未动', FRZ_QIANGTI_DAN, 1, '==', '专职丹 §10-Q2'),
        ('冻结·废丹未动', FRZ_FEIDAN, 1, '==', '§3.6 #21'),
        ('冻结·HN 兜底表未动', FRZ_HN_QIANGTI, 1, '==', 'R-107 冻结面 §8.1'),
        ('冻结·Ct 名字引用表未动', FRZ_CT, 1, '==', '值随 Dm/Vr 变'),
    ]
    return g


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    assert FG_NEW.startswith(MARK), 'MARK 必须植入 FG_NEW'
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
        assert old not in new and new not in old, '%s 新旧锚点互相包含' % name
    # 唯一性：标记只在 fg 出现一次
    assert sum((MARK in new) for _, _, new in EDITS) == 1, 'MARK 只应植入一处（fg）'
    # 死键删除自证：新形态不得再含被删的 effect 永久属性键
    assert 'effect:{exp:2e3,spirit:50,physique:50}' not in P_XIANLING_NEW, '仙灵丹 effect 死键未删净'
    assert 'effect:{exp:3e4,spirit:20}' not in P_JIEJIN_NEW, '结金丹 effect 死键未删净'
    assert 'effect:{exp:1e4,spirit:50,hp:300}' not in P_NINGHUN_NEW, '凝魂丹 effect 死键未删净'
    assert 'effect:{hp:800,exp:1500,attack:30}' not in P_FENGHUANG_NEW, '凤凰涅槃丹 effect 死键未删净'
    assert 'effect:{hp:50,spirit:5}' not in H_NINGSHEN_NEW, '凝神花 effect 死键未删净'
    # 新 fg 的普通/稀有 spirit/physique 必须为 0
    assert '普通:{hp:20,exp:12,spirit:0,physique:0,maxHp:3}' in FG_NEW, '普通地板 spirit/physique 须为 0'
    assert '稀有:{hp:70,exp:45,spirit:0,physique:0,maxHp:10}' in FG_NEW, '稀有地板 spirit/physique 须为 0'
    # 不得注入网络/危险调用
    assert 'fetch(' not in FG_NEW and 'XMLHttpRequest' not in FG_NEW, '注入块不得含网络调用'
    # gates 自检：门禁条目格式正确
    for row in gates():
        assert len(row) == 5, 'gates 条目须为五元组'
        assert row[3] == '==', 'op 目前仅支持 =='


def main() -> int:
    ap = argparse.ArgumentParser(
        description='R-140 消耗品数值重构·批 1（纯数值表；客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v2916-*.js）')
    a = ap.parse_args()
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

    olds = [o.encode('utf-8') for _, o, _ in EDITS]
    news = [n.encode('utf-8') for _, _, n in EDITS]

    # 1) 幂等：全部已是补丁后形态且旧形态全清零 → rc=3 不写盘
    if all((n in src) for n in news) and all((o not in src) for o in olds):
        print('[SKIP] source looks already patched（R-140 批 1 全部新形态齐备且旧形态清零）')
        return 3

    # 2) 锚点计数（rc=2 面）
    for (name, _old, _new), ob in zip(EDITS, olds):
        n = src.count(ob)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）' % (name, n))
            return 2
    if src.count(MARK.encode('utf-8')) != 0:
        print('[FAIL] 在位标记 %r 已存在（疑部分补丁态）' % MARK)
        return 2

    # 3) 应用（字节级单点替换）
    out = src
    for (name, _old, _new), ob, nb in zip(EDITS, olds, news):
        out = out.replace(ob, nb, 1)

    # 4) 门禁
    ok = True
    text = out.decode('utf-8', errors='replace')
    for label, needle, exp, op, note in gates():
        act = text.count(needle)
        good = (act == exp)
        ok = ok and good
        print('  [%s] %-34s actual=%d expect==%d' % ('OK' if good else 'FAIL', label, act, exp))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1

    # 5) 往返自证
    back = out
    for ob, nb in zip(olds, news):
        back = back.replace(nb, ob, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r140-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r140-', suffix='.tmp')
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
