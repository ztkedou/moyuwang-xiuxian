#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_v26n.py — yl 客户端 v26n：移植上游 0.3.8「九天通天塔」

上游来源：JeasonLoop/react-xiuxian-game @1ec1b63
  - constants/tower.ts          (getTowerFloorConfig / calculateTowerDailySweep / 两个 item 工厂)
  - services/towerService.ts    (challengeTowerFloor / sweepTower)
  - components/TowerModal.tsx   (UI 结构参照)

我方适配（bundle 锚点注入）：
  - 数值公式 1:1 保留（境界分段、realmFactor、boss ×1.4、25 回合模拟、每日扫荡 35% 累计）
  - 玩家总属性改用我方 xt(player)（含心法/金丹法；player.attack 已含装备+称号）
  - 物品落库改用 YlxwTowerAddItem（Material 按 name 叠加；isEquippable 每次新建实例，id 用 St()）
  - UI 用仙务枢纽既有展示组件（YlxwPanel/YlxwRow/YlxwBtn/YlxwTitle/YlxwKv）重写
  - 挂载：YLXW_COMP.tower + YLXW_TABS.push + YLXW_ICONS.tower + 抽屉入口 YlxwOpen("tower")
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 客户端补丁模块（yl_*_ext.py）已收进 patches/client/，加进搜索路径保持裸名 import 不变
sys.path.insert(0, os.path.join(HERE, 'patches', 'client'))
from yl_patch import Patcher, zh  # noqa: E402
from yl_v26n_ext import (  # noqa: E402
    CORE_JS, REFORGE_JS, SPELL_JS, BATTLE_PATCHES,
    DRAWER_ITEM_REF, DRAWER_ITEM_SPELL,
    PAYOUT_API_JS, PAYOUT_API_ANCHOR, PAYOUT_JS, DRAWER_ITEM_PAYOUT,
)
from yl_sellui_ext import (  # noqa: E402
    SELL_UI_HELPER_ANCHOR, SELL_UI_HELPER_JS, SELL_UI_PATCHES, SELL_UI_GATES,
)
from yl_rename_ext import RENAME_PATCHES, RENAME_GATES  # noqa: E402
# ---- v28 模块（按调用顺序导入；num-balance 必须最后跑，才能看到别人注入的块）----
from yl_saveretry_ext import apply as v28_saveretry_apply  # noqa: E402
from yl_version_ext import apply as v28_version_apply
from yl_changelog_ext import apply as v28_changelog_apply  # noqa: E402  # 游戏内更新日志：玩家向 + 不截断  # noqa: E402
from yl_mail_ext import apply as v28_mail_apply  # noqa: E402
from yl_entry_ext import apply as v28_entry_apply  # noqa: E402
from yl_sectgf_ext import apply as v28_sectgf_apply  # noqa: E402
from yl_char_ext import apply as v28_char_apply  # noqa: E402
# ---- 0.8.2 新增三模块（lead 接线；顺序见下方 V28_MODULES 注释）----
from yl_bond_ext import apply as v28_bond_apply  # noqa: E402
from yl_ui_ext import apply as v28_ui_apply  # noqa: E402
from yl_arb_ext import apply as v28_arb_apply  # noqa: E402
# ---- 0.8.12 新增一模块（offline2：R-021 离线窗口锚点 + R-020 灵石日志文案）----
#      ★ **必须紧跟 arb 之后** —— 它锚定的 `function YLArbTrace(msg) {` 是 arb 注入的。
#      ① R-021（真 bug）：客户端每 10s 自动存档 → 服务端每次 /api/save 刷新 updated_at →
#         而离线窗口锚点就是 updated_at ⇒ 页面开着时 windowMs 恒 ≈10s < 5min ⇒ 面板恒 0。
#         修法：服务端 saves 加 last_seen_at/last_resume_at + 新增 offlineAnchor() +
#         POST /api/session/presence（客户端在 visibilitychange(hidden)/beforeunload 上报）。
#         ★ 机制上真断开：away 落的是「上报那一刻本行的 updated_at」，客户端无法带时间戳伪造时长；
#         心跳 /api/save 只刷 updated_at、不碰 last_seen_at。
#      ② R-020（非 bug，仅文案）：那 5 条日志是玩家自己花掉的（加速/远征/秘径），
#         原 `addLog(..., 'danger')` + 「服务端权威变更，已留痕」误导 ⇒ 降级 + 带来源。
#      ★ 收益公式一行未动（服务端 6 条硬断言 + 改前改后计数相等）；恒在 numbal 之前。
from yl_offline2_ext import apply as v28_offline2_apply  # noqa: E402
# ---- 0.8.12 新增一模块（farm2）----
#      R-019 灵田：照料 2h 冷却 + 种子成品属性/售价 + 变卖/服用价格（依赖 farm087+farm089+v2810c）
from yl_farm2_ext import apply as v28_farm2_apply  # noqa: E402
# ---- 0.8.12 新增一模块（medlog）----
#      R-023 打坐停止日志：时长/修为/灵石 + 顿悟次数 + 平均每跳（依赖 toast083 + 基座打坐本体）
from yl_medlog_ext import apply as v28_medlog_apply  # noqa: E402
# ---- 0.8.12 新增一模块（daily）----
#      R-027 日常任务：每项写入「获取方式」（依赖 v2810c）
from yl_daily_ext import apply as v28_daily_apply  # noqa: E402
# ---- 0.8.12 新增一模块（fun2）----
#      R-029 每日行乐：茶馆结果三态展示 + 茶馆记录折叠块（依赖 v2810c）
from yl_fun2_ext import apply as v28_fun2_apply  # noqa: E402
# ---- 0.8.12 新增一模块（lottery）----
#      R-031 抽奖：精简面板自定义数量 + 完整面板返回精简（依赖 v2810c）
from yl_lottery_ext import apply as v28_lottery_apply  # noqa: E402
# ---- 0.8.12 新增一模块（dungeon2）----
#      R-032 秘境：冷却 30s→5min + 每日上限 [10,12,14,15,17,18,20] 随境界（依赖 dungeon085+v2811a）
from yl_dungeon2_ext import apply as v28_dungeon2_apply  # noqa: E402
from yl_numbal_ext import apply as v28_numbal_apply  # noqa: E402
# ---- 0.8.3 新增四模块（lead 接线；顺序见下方 V28_MODULES 注释）----
from yl_chargift083_ext import apply as v28_chargift083_apply  # noqa: E402
from yl_intro083_ext import apply as v28_intro083_apply  # noqa: E402
from yl_flow083_ext import apply as v28_flow083_apply  # noqa: E402
from yl_toast083_ext import apply as v28_toast083_apply  # noqa: E402
# ---- 0.8.5 新增两模块（cli-eco 灵石经济 / cli-dg 秘境每日限制；顺序见下方 V28_MODULES 注释）----
from yl_eco085_ext import apply as v28_eco085_apply  # noqa: E402
from yl_dungeon085_ext import apply as v28_dungeon085_apply  # noqa: E402
# ---- 0.8.6 新增一模块（fun086：洞府加速提示 / 日常任务灵石×5 / 每日行乐四玩法 /
#      奇遇区间化展示 / 妖灵日志折叠 / 远征 2W / 仙务面板两列）----
from yl_fun086_ext import apply as v28_fun086_apply  # noqa: E402
# ---- 0.8.7 新增八模块（implEventsUi 唯一接线；各模块由十一人分工交付）----
#      grotto087(T4+T9) / farm087(T10) / xinfa087(T3) / t6chardex(T6) / adv087(T11)
#      act087(T5 活动中心) / t7sect(T7) / t8mentor(T8)；装配序见下方 V28_MODULES 注释
from yl_grotto087_ext import apply as v28_grotto087_apply  # noqa: E402
from yl_farm087_ext import apply as v28_farm087_apply  # noqa: E402
from yl_xinfa087_ext import apply as v28_xinfa087_apply  # noqa: E402
from yl_t6chardex_ext import apply as v28_t6chardex_apply  # noqa: E402
from yl_adv087_ext import apply as v28_adv087_apply  # noqa: E402
from yl_act087_ext import apply as v28_act087_apply  # noqa: E402
from yl_t7sect_ext import apply as v28_t7sect_apply  # noqa: E402
from yl_t8mentor_ext import apply as v28_t8mentor_apply  # noqa: E402
# ---- 0.8.8 新增一模块（forge088：item19 炼器产出补 [境界] 前缀；不改基座，包装 zg 两工厂）
from yl_forge088_ext import apply as v28_forge088_apply  # noqa: E402
# ---- 0.8.9 新增两模块（T2 灵宠玩法扩展 / T5 灵田品种重构；客户端部分）
#      pet089（秘径消耗重构 / 出战助战加成 / 融合 / 妖灵归位）
#      farm089（灵田双出口「变卖 / 服用」面板；覆盖 farm087 的 YLXW_COMP.farm 注册）
from yl_pet089_ext import apply as v28_pet089_apply  # noqa: E402
from yl_farm089_ext import apply as v28_farm089_apply  # noqa: E402
# ---- 0.8.9 新增一模块（i4-reward：灵石奖励口径统一；抽 YLReward 纯函数供显示端/入账端同调）
#      排位理由：只改「显示端」的两处面板文案 + 注入纯函数，与 forge088 面不重叠，
#      且必须在 numbal 之前（numbal 恒最后）。注入锚是 YLRF 块结束标记，早于所有 v28 模块，
#      故本模块只看得到基座形态，与其它模块的注入互不干扰。
from yl_reward089_ext import apply as v28_reward089_apply  # noqa: E402
# ---- 0.8.9 新增两模块（T16 演武场 / T17 丹炉重构；i3-cli 交付，恒在 numbal 之前）----
#      t17alchemy：重写 YlxwTAlchemy 面板（丹道挂机线）+ 丹房弹窗 item18 布局修复
#      t16arena：重写 YlxwTArena 面板（PVE 试炼 + 异步 PVP 论剑）
from yl_t17alchemy_ext import apply as v28_t17alchemy_apply  # noqa: E402
from yl_t16arena_ext import apply as v28_t16arena_apply  # noqa: E402
#      t9quest：仙途任务·活跃度客户端显示层（18 项分组 / 6 档宝箱 / 周里程碑 / 一键领取）
from yl_t9quest_ext import apply as v28_t9quest_apply  # noqa: E402
# ---- 0.8.9 新增一模块（T7 传承系统重构；i3-cli 交付，恒在 numbal 之前）----
#      t7legacy：逐点使用 + 分境界效果（低境界跳 1 层 / 元婴+ 注入 25% 修为）
#                + 传承石分层定价（100 万起 / 长生 2000 万）+ 声望商店每周限 1
from yl_t7legacy_ext import apply as v28_t7legacy_apply  # noqa: E402
# ---- 0.8.10 新增五模块（三步工作流：修 bug + 0.8.10 待办池 + 需求查漏补缺）----
#      v2810a：称号列表展示装备后加成数值 + 角色面板补属性作用说明与命中/暴击/闪避/吸血
#      v2810b：悟道并入功法（删独立入口 ×3 + 功法面板左栏心法下方挂悟道区块 + 玩法提示）
#      v2810c：灵田作物「变卖/服用」收获内容标注 + 洞府灵草加速改「只缩短小时数」
#      v2810d：奇遇抽奖与抽奖合并为一个入口（左奇遇/右抽奖）+ 抽奖高阶折算「灵石+修为」
#      v2810e：信箱删除邮件（DELETE /api/mail/:id）+ 灵宠左栏「仙务·妖灵」补作用/融合入口
from yl_v2810a_ext import apply as v28_v2810a_apply  # noqa: E402
from yl_v2810b_ext import apply as v28_v2810b_apply  # noqa: E402
from yl_v2810c_ext import apply as v28_v2810c_apply  # noqa: E402
from yl_v2810d_ext import apply as v28_v2810d_apply  # noqa: E402
from yl_v2810e_ext import apply as v28_v2810e_apply  # noqa: E402
#      v2810f：洞府灵草「配置信息缺失」兜底修复（旧名 灵紫猴草 → 现名 紫猴花 别名表）
from yl_v2810f_ext import apply as v28_v2810f_apply  # noqa: E402
#      v2810g：演武场周榜面板（论剑区追加「我的名次 + 本周场次 + TOP10」；
#              配套服务端第 22 环 srv_patch_arenaweek.py 的 GET /arena/week）
from yl_v2810g_ext import apply as v28_v2810g_apply  # noqa: E402
#      v2810h：仙务「时光回溯」面板（玩家侧存档快照列表 + 自助回溯；
#              配套服务端第 23 环 srv_patch_snapself.py 的 GET /api/snapshots
#              与 POST /api/snapshots/:id/restore）
#              ★ 同时给 applyRemoteSave 的灵石仲裁加一次性放行开关 ——
#                回溯会让数值整体变小，YLArbDecide 会误判为服务端钳制而 flush/skip，
#                把回溯结果冲掉；放行开关用完即清，不动 YLArbDecide 本体。
from yl_v2810h_ext import apply as v28_v2810h_apply  # noqa: E402
# ---- 0.8.11 新增一模块（v2811a：秘境弹窗显示服务端权威每日次数）----
#      0.8.5（dg085）已把秘境每日 3 次接到服务端账本，但只在**地宫 Roguelike 弹窗**
#      打开时同步；「秘境探索」弹窗（组件 cM）从未拉过 ⇒ 玩家看不到剩余次数与冷却。
#      本模块在 cM 打开时复用 dg085 的 YlxwDungeonStatusSync() 拉一次，并在内容区顶部
#      常驻一条「今日秘境次数 x/3 + 剩余 + 冷却」信息栏；刷新按钮顺带刷新次数。
#      ★ 零新增网络调用、零服务端改动；恒在 numbal 之前。
from yl_v2811a_ext import apply as v28_v2811a_apply  # noqa: E402
# ---- 0.8.12 新增一模块（gongfa：R-016 功法按技能类型分类 + 展示战斗技能效果）----
#      侦察结论：本体**早已实现**功法→技能的映射 —— 手写技能表 og（9 部有专属技能）
#      + 生成器 GS(art)（其余 73 部按 type/grade 生成），战斗入口 QS(player) 里
#      `t.cultivationArts.forEach` 逐部取用 ⇒ 每部已习得功法在战斗里就是一个技能。
#      缺的只是「卡片没展示」。故本模块**只读复用** og/GS/is，把 82 部功法的战斗技能
#      展示进卡片，并把失真的「心法/体术」二分改为真实技能类型（攻击 54 / 辅助 27 / 治疗 1）。
#      ★ 战斗侧（og/GS/QS/X0/uM）零改动；恒在 numbal 之前。
from yl_gongfa_ext import apply as v28_gongfa_apply  # noqa: E402
# ---- 0.8.12 新增一模块（char2：R-012 角色属性补说明+隐藏属性 / R-014 称号系统移到左列 /
#      R-015 天赋默认折叠 + 描述标注属性）----
#      三条改同一个「角色系统」弹窗，必须同一模块交付（否则撞锚点）。
#      ① R-012：声望/幸运补影响说明；补 5 项隐藏属性（暴击/暴伤/闪避/吸血/减伤，
#         取自本体 YlxwBattleBonus(player)）。★「命中」玩家侧不存在（hit 只在敌人数据里）
#         ⇒ 按「不自己发明数值」不渲染，面板里写明「玩家无命中属性」。
#      ② R-014：称号系统搬到左列「仙务·修行统计」上方（**JSX 层搬移，不碰 DOM**）。
#      ③ R-015：天赋默认折叠 + 展开/收起按钮 + 描述加属性数值（读本体天赋表 Un 的 effects）。
#      ★ 基线依赖 0.8.11 已装配（v2810a）；恒在 numbal 之前。
from yl_char2_ext import apply as v28_char2_apply  # noqa: E402
# ---- 0.8.13 一模块（M-1/M-2 上游 bug 摘取；恒在 numbal 之前）----
from yl_merge01_ext import apply as v28_merge01_apply  # noqa: E402
# ---- 0.8.13 二模块（R-034/035/036 人物志任务化；R-013 传承石可交易）----
from yl_renwu_ext import apply as v28_renwu_apply  # noqa: E402
from yl_r013_ext import apply as v28_r013_apply  # noqa: E402
# ---- 0.8.13 三模块（R-017/022/024/025/028 数值统一 / R-018 妖灵培养重设计）----
#   · econ2：R-025 修炼效率 6 桶「相乘→相加 + 降幅系数 K（无总帽）」/ R-022 打坐
#     自动+手动冷却 1s→2s、顿悟 1%→0.2% / R-024 每跳灵石 `×5` →
#     `floor(max(1,q)·4.25·(1+(层−1)·0.03))`（新增 YlxwMedStone2 中转）/ R-017 灵宠喂养
#     收益÷3、亲密÷2.333、消耗×5 / R-028 周里程碑 3 档→5 档。
#     ★ 其锚点实测于「已含 medlog / toast083 / flow083 / eco085 / reward089」的产物
#       ⇒ 必须排在它们之后（本处即链尾，满足）。8 条跨模块冻结串已由 lead 依
#       dungeon085「约束权移交」先例改名/换断言（见各 ext 文件内 2026-09-30 注释）。
#   · r018：妖灵出口 PP 纯函数 + `player.petSpirit` + `xt()` 末尾加算（X0/QS 双战斗）
#     + D1 三档进食 / D2 三选互动+买额度 / D3 点化 / D4 秘径 / D6 归位。
#     ★ 锚点形态 = 已含 fun086 / v2810e / pet089 的产物；不删 v2810e 冻结的「喂养/嬉戏」行。
#   · 两者恒在 numbal 之前（numbal 恒最后，需看到所有注入块）。
from yl_econ2_ext import apply as v28_econ2_apply  # noqa: E402
from yl_r018_ext import apply as v28_r018_apply  # noqa: E402
# ---- 0.8.13 一模块（★ 冷却机制真 bug 修复 + 历练冷却还原上游原版口径）----
#   · R1：UI store 的 `setCooldown:a=>t({cooldown:a})` **不支持 updater 函数**，
#     而被动回复每秒调 `setCooldown(x=>x>0?x-1:0)` ⇒ cooldown 字段被写成**函数**
#     ⇒ 全仓 `cooldown>0` 守卫恒 false ⇒ **冷却机制彻底失效**。
#     运行时实证：`typeof cooldown === "function"`；自动历练实测 2002ms（代码意图 6000ms）。
#     修法与 setPlayer/setSettings 同构（补 typeof 判断）。
#   · R2：历练 9 个冷却点还原为**上游基线 b822f2d 原值**（1/1/2/2/2/1/2/1/2）。
#     ★ 必须排在 `yl_flow083_ext.py` 之后（要改它留下的 d(6)/d(4)/d(.4)/d(1)）。
#   · 恒在 numbal 之前。
from yl_cooldown_ext import apply as v28_cooldown_apply  # noqa: E402
# ---- 0.8.13 一模块（R-028 客户端 `YlxwQMile` 表对齐：1000 extra 清空 / 1900 承接
#      「仙品珍宝+称号」/ 2310 改「传承石×1（每月限领）」）----
#   ★ 必须排在 `econ2` 之后（econ2 的 `MILE_OLD` 锚点就是 t9quest 的旧 3 档表，
#     原地改 t9quest 会让 econ2 锚点 count=0 ⇒ 整链硬崩）。
from yl_r013c_ext import apply as v28_r013c_apply  # noqa: E402
# ---- 0.8.11.2 一模块（R-024 每跳灵石因子加入大境界序号，修正「跨大境界回落」）----
#   因子 = 1 + realmIndex*K + (层-1)*0.03，K=0.083；炼气 L1 仍 ×1.00（不动 R-022 的 2-3h 锚点）。
#   ★ 必须排在 econ2 之后（锚点是 econ2 的产物形态）。
from yl_r024_ext import apply as v28_r024_apply  # noqa: E402
# ---- 0.8.11.2 两模块（R-021 挂机收益玩法说明 + R-032③ 秘境网格降列）----
from yl_r021help_ext import apply as v28_r021help_apply  # noqa: E402
from yl_r032layout_ext import apply as v28_r032layout_apply  # noqa: E402
# ---- 2026-10-01 一模块（R-040 修炼效率：明细显示对齐实算；★ 必须排在 econ2 之后）----
#   R-025（econ2）把 6 桶改成「相加 × 各来源 K」，但**明细显示没跟着改**，仍打未打折的原值
#   ⇒ 面板显示「天赋 +380%」而实算只有 a*0.26=+98.8%（用户截图 +108.8% 完全吻合）。
#   本环只改展示那一串（换成实际生效值 + 补 协同/羁绊 两桶），**公式一个字不动**。
from yl_r040_ext import apply as v28_r040_apply  # noqa: E402
# ---- 2026-10-01 二模块（R-037 去掉自带离线修炼；R-041 悟道触发率+日志）----
#   r037：删读档离线结算触发块 + Sw 文案 + ww 入账；★ 连带停用「离线洞府灵草收获/离线寿命流逝」
#   r041：打坐顿悟 0.2%->1.5%、历练奇遇基础 5%->15%(上限 30%->50%) + 补历练触发日志；
#         ★ 必须排在 econ2 之后（锚点是 econ2 产物的 .002）
from yl_r037_ext import apply as v28_r037_apply  # noqa: E402
from yl_r037b_ext import apply as v28_r037b_apply  # noqa: E402  # R-037b 接回离线洞府灵草+寿命（★ 必须紧接 r037）
from yl_r041_ext import apply as v28_r041_apply  # noqa: E402
from yl_r038_ext import apply as v28_r038_apply  # noqa: E402
from yl_r039_ext import apply as v28_r039_apply  # noqa: E402
from yl_r044_ext import apply as v28_r044_apply  # noqa: E402  # R-044 历练灵石（★ 排 r062 之后）
from yl_r045_ext import apply as v28_r045_apply  # noqa: E402  # R-045 妖灵归位（★ 排 pet089 之后）
from yl_r046_ext import apply as v28_r046_apply  # noqa: E402  # R-046 灵田显示（★ 排 farm2 之后）
from yl_r047_ext import apply as v28_r047_apply  # noqa: E402  # R-047 灵田收益（客户端侧 no-op 守卫）
from yl_r048_ext import apply as v28_r048_apply  # noqa: E402  # R-048 灵草分档（★ 排 farm2 之后）
from yl_r070_ext import apply as v28_r070_apply  # noqa: E402
from yl_r071_ext import apply as v28_r071_apply  # noqa: E402
from yl_r073_ext import apply as v28_r073_apply  # noqa: E402
from yl_r074_ext import apply as v28_r074_apply  # noqa: E402
from yl_r078_ext import apply as v28_r078_apply  # noqa: E402  # R-078 收养显示灵石（★ 排 r071 之后）
from yl_r082_ext import apply as v28_r082_apply  # noqa: E402  # R-082 洞府可收获提示
from yl_r076_ext import apply as v28_r076_apply  # noqa: E402
from yl_r077_ext import apply as v28_r077_apply  # noqa: E402
from yl_r080_ext import apply as v28_r080_apply  # noqa: E402
from yl_r081_ext import apply as v28_r081_apply  # noqa: E402
from yl_r079_ext import apply as v28_r079_apply  # noqa: E402  # R-079 补全玩法介绍
# ---- 0.9.3 客户端小修（R-083 云端刷新弹窗 + 仓库链接指向本仓库；无硬依赖）----
from yl_r083_ext import apply as v28_r083_apply  # noqa: E402
# ---- 0.9.4 寿元体系（自动历练温和化 + 扣减可见 + 打坐耗命）----
from yl_life094_ext import apply as v28_life094_apply  # noqa: E402
# ---- 0.9.6 突破奖励 + 每点属性加成（用户：升级难、寿命易耗尽）----
from yl_bt096_ext import apply as v28_bt096_apply  # noqa: E402
# ---- 0.9.7 属性/寿元/灵根（R-095/096 体魄+气血 · R-099 寿元按小说设定 · R-098 五系灵根被动）----
from yl_attr097_ext import apply as v28_attr097_apply  # noqa: E402
from yl_life097_ext import apply as v28_life097_apply  # noqa: E402  # ★ 必须排 bt096 之后（覆盖其 _e 公式）
from yl_linggen097_ext import apply as v28_linggen097_apply  # noqa: E402
# ---- 0.9.8（R-085/087 天赋重做 · R-089/090 历练+顿悟 · R-091 悟道面板 · 速度→身法改名）----
from yl_speedname097_ext import apply as v28_speedname097_apply  # noqa: E402
from yl_talent097_ext import apply as v28_talent097_apply  # noqa: E402
from yl_adv097_ext import apply as v28_adv097_apply  # noqa: E402
from yl_dao097_ext import apply as v28_dao097_apply  # noqa: E402
# ---- 0.9.9（R-101 历练商店刷新计费 · R-084 人物志与道友图鉴解耦）----
from yl_shoprefresh101_ext import apply as v28_shoprefresh101_apply  # noqa: E402
from yl_chardex101_ext import apply as v28_chardex101_apply  # noqa: E402
# ---- 0.9.10（R-102/103/104 商店三连 · R-105 自动历练结束汇总推送）----
from yl_shop102_ext import apply as v28_shop102_apply  # noqa: E402
from yl_advend105_ext import apply as v28_advend105_apply  # noqa: E402  # ★ 必须排 adv097 之后
# ---- 0.9.11（R-106 折算显示口径 · R-107 道具数值与售价重配 · R-108 商店刷新显示修复 · R-109 加点面板口径）----
from yl_r106_ext import apply as v28_r106_apply  # noqa: E402  # R-106 道具描述/预览按 $r 折算（只改显示）
from yl_r107_ext import apply as v28_r107_apply  # noqa: E402  # R-107 数值/售价重配（★ 必须排 r106 之后：r106 的冻结断言认它的定稿值）
from yl_r108_ext import apply as v28_r108_apply  # noqa: E402  # R-108 刷新显示修复（★ 必须排 shoprefresh101 之后）
from yl_r109_ext import apply as v28_r109_apply  # noqa: E402  # R-109 加点面板每点增量改读 Ps
# ---- 2026-10-02 链式自动轮次第 2 批（R-111/R-113/R-114/R-115）----
from yl_r111_ext import apply as v28_r111_apply  # noqa: E402  # R-111 每日签到可用（★ 服务端配套 = SRV_CHAIN 'srv_patch_111.py'）
from yl_r113_ext import apply as v28_r113_apply  # noqa: E402  # R-113 万妖巢穴五 boss 同现（★ 服务端配套 = SRV_CHAIN 'srv_patch_113.py'）
from yl_r114_ext import apply as v28_r114_apply  # noqa: E402  # R-114 历练收获：修 0 值 + 参照打坐丰富化
from yl_r115_ext import apply as v28_r115_apply  # noqa: E402  # R-115 洞府灵田价格/等阶/扩地/田位/悬停（★ 服务端配套 = SRV_CHAIN 'srv_patch_115.py'）
# ---- 2026-10-02 0.9.13 第 1 批接线（R-124 = apply 模块；R-116/R-118 = 成员新契约 standalone
#      --src 脚本，**不进 V28_MODULES**——由装配层（本文件 __main__ / dryrun_087）对最终产物
#      按序套用，见下方 STANDALONE_CLIENT / apply_standalone()）----
from yl_r124_ext import apply as v28_r124_apply  # noqa: E402  # R-124 灵田服用预览 spirit→神识（★ 必须排 farm089/speedname097 之后）
from yl_r042_ext import apply as v28_r042_apply  # noqa: E402  # ★ 必须排在 cooldown 之后
from yl_r043_ext import apply as v28_r043_apply  # noqa: E402  # ★ 必须排在 r041 之后
# ---- 0.8.11.2 一模块（R-018 D5 灵纹：战斗层只读 + 换纹行）----
from yl_r018b_ext import apply as v28_r018b_apply  # noqa: E402
# ---- 0.8.11.1 一模块（周里程碑「已领取」显示修复：milestones 数组 → {tier: claimed} 映射）----
#   服务端第 32 环修好了 summary 的 claimed，但客户端从来是拿**数组当字典取**（`claims[m.tier]`）
#   ⇒ claimed 恒 false。本环把数组归一成映射，第 160 行原样即可命中。
#   ★ 必须排在 `r013c` 之后（r013c 覆盖式替换 `YlxwQMile` 表，本环要看到最终形态）。
from yl_claimedfix_ext import apply as v28_claimedfix_apply  # noqa: E402
# ---- 2026-10-01 第 1 批 R 批次五模块（R-049/050/051/052/053；恒在 numbal 之前）----
#      r049：洞府灵草种植区扩地（grotto.extraSlots，上限=基础+3，价格 2000/8000/24000）。
#            锚点全在基座 vite 字面区、与全部现有模块零文本交集；紧随 grotto087 便于审阅。
#      r050：洞府加速一次半小时（★ 必须排在 v2810c 之后——锚是其注入的 YlxwHerbSpeedMs 定义行）
#            + 每日催熟基础 3→10 随洞府等级（服务端配套 = SRV_CHAIN 第 35 环 srv_patch_050.py）。
#      r051：日常任务修为+灵石奖励 ×1.5（★ 必须排在 fun086 之后——锚是其 F2 造出的
#            'v=r*d.rewardMultiplier*u*f,vs=v*5' 形态）。
#      r052：周活跃度显示修（summary.week 日期串 → weekActivity 数值；★ 必须排在 claimedfix
#            之后，锚点行由 t9quest 的 INJECT_JS 产出）。
#      r053：茶馆玩法说明 + 灰因动态提示（★ 必须排在 fun2 之后——锚在 fun086 注入、
#            fun2 改写过的 YlxwTDaily 区域内）。
from yl_049_ext import apply as v28_049_apply  # noqa: E402
from yl_050_ext import apply as v28_r050_apply  # noqa: E402
from yl_051_ext import apply as v28_r051_apply  # noqa: E402
from yl_052_ext import apply as v28_r052_apply  # noqa: E402
from yl_053_ext import apply as v28_r053_apply  # noqa: E402
# ---- 2026-10-01 第 2 批 R 批次五模块（R-054~R-058；恒在 numbal 之前）----
#      r054：每日签到（月历长期签到+修为/灵石+里程碑；★ 锚在 act087 注入区，必须排其后）
#      r055：灵玉阁玩法说明+掉落口径透明化（★ 必须排在 act087 之后）
#      r056：万妖巢穴多 boss（每期 5 只+每只免费 5 次+10 分钟冷却；★ 锚在 act087 注入块内）
#      r057：奇遇抽奖 UI 面（冷却禁用/倒计时/规则说明/暴击 toast；无硬依赖）
#      r058：缘契寻访任务板「整体刷新」按钮（★ 必须排在 renwu 之后）
from yl_054_ext import apply as v28_r054_apply  # noqa: E402
from yl_055_ext import apply as v28_r055_apply  # noqa: E402
from yl_056_ext import apply as v28_r056_apply  # noqa: E402
from yl_057_ext import apply as v28_057_apply  # noqa: E402
from yl_058_ext import apply as v28_r058_apply  # noqa: E402
# ---- 2026-10-01 第 3 批 R 批次五模块（R-059~R-063；恒在 numbal 之前）----
#      r059：人物志·缘契结识好感递减 + 解锁档 2→4 带奖励（★ 必须排在 renwu/t6chardex 之后）
#      r060：师门任务好感按提交品阶结算 + 单条刷新每日限 3 次（★ 必须排在 renwu 之后）
#      r061：演武场试炼战报反馈 + 次数即时刷新（★ 必须排在 t16arena 之后；服务端 = SRV_CHAIN 链尾 srv_patch_061.py）
#      r062：秘境单独点选收益 ×3 + 冷却 15 分钟（★ 必须排在 eco085/dungeon2 之后；服务端 = SRV_CHAIN 链尾 srv_patch_062.py）
#      r063：roguelike 地宫单独算上限（★ 必须排在 dungeon085/dungeon2/v2811a 之后；服务端 = SRV_CHAIN 链尾 srv_patch_063.py）
from yl_059_ext import apply as v28_059_apply  # noqa: E402
from yl_060_ext import apply as v28_r060_apply  # noqa: E402
from yl_061_ext import apply as v28_061_apply  # noqa: E402
from yl_062_ext import apply as v28_062_apply  # noqa: E402
from yl_063_ext import apply as v28_063_apply  # noqa: E402
# ---- 2026-10-01 第 4 批 R 批次五模块（R-064~R-068；恒在 numbal 之前）----
#      r064：炼丹出炉丹道造诣 + 药效数值透明化 + 丹炉 3→9 方（★ 必须排在 t17alchemy 之后；
#            7 个客户端锚点全是 t17 注入产物；服务端 = SRV_CHAIN 链尾 srv_patch_064.py）
#      r065：宗门页只做宗门内容（摘 xw:"sect" 融合标记，1 处替换；无硬依赖，锚在 base 原生存在）
#      r066：宗门功法阁贡献值重做 + 修满化形（★ 必须排在 sectgf 之后——全部锚点在 sectgf 注入块内；
#            服务端 = SRV_CHAIN 链尾 srv_patch_066.py）
#      r067：功法全表五行分类 + 扩充 55 部（★ 必须排在 gongfa 之后——功法阁 UI 锚消费 R-016 改后的
#            z4 语义；YlxwElemInit 注入先于 numbal 才能让补 root 功法进预算重算）
#      r068：人物志自带结交降频（★ 必须排在 t6chardex 之后——7 条锚点全是 T6-7 降频产物形态）
from yl_064_ext import apply as v28_064_apply  # noqa: E402
from yl_065_ext import apply as v28_065_apply  # noqa: E402
from yl_066_ext import apply as v28_r066_apply  # noqa: E402
from yl_r067_ext import apply as v28_r067_apply  # noqa: E402
from yl_068_ext import apply as v28_r068_apply  # noqa: E402

BASE = os.path.join(HERE, 'build', 'assets', 'index-v26m-20260927.js')
OUT = os.path.join(HERE, 'build', 'assets', 'index-v2953-20261010.js')

# v28 模块调用顺序（锚点稳定性 + num-balance 必须最后）：
#   saveretry → arb → version → mail → entry → sectgf → char → bond → ui
#             → chargift → intro → flow → toast → eco → dungeon → numbal
#   顺序理由（0.8.2 装配定案，预演 373 门禁 FAIL 0）：
#     · arb 必须晚于 saveretry：两者都改存档/同步函数（Pn.fetchSave / pushSave / applyRemoteSave）
#     · ui 必须晚于 version：ui 的 EVT_TAIL_ANCHOR 依赖 version 先插入 `d.desc` 行
#     · bond 放在 ui 之前：只改 YlxwStatExtras/YlxwBattleBonus 的函数体头部，与 ui 无交集
#     · numbal 恒为最后：它要看到别人注入的块（心法预算表 / 战斗封顶表）
#   0.8.3 追加理由（lead 接线）：
#     · chargift 排在 char 之后：与 yl_char_ext 同触「人物志」域，后跑才能看到 char 的最终形态
#     · intro / flow / toast 三者彼此无交集、也不依赖前置模块，顺序仅为确定性
#     · toast 排在 numbal 之前（toast 的宿主锚点 RS 与 numbal 的心法表互不重叠）
#   0.8.5 追加理由（cli-eco / cli-dg）：
#     · eco 与 dungeon 改的面互不重叠（eco: Ym/_ylf/G3/商店刷新；dungeon: handleEnterRealm/yk/秘境 API 助手）
#     · 两者都排在 numbal 之前，且都在 toast 之后（toast 之后已无其它模块触碰同一锚点）
#     · dungeon 的注入锚是 YlxwMin（hub block），eco 的注入锚是 Ym 定义前 —— 互不干扰
#   0.8.6 追加理由（fun086）：
#     · fun086 改的是「玩法内容层」（洞府加速文案 / 日常任务奖励公式 / 每日行乐面板 /
#       奇遇面板 / 妖灵面板 / 远征按钮 / 仙务页签栏），与 0.8.5 的 eco（Ym/_ylf/G3/商店刷新）
#       和 dungeon（handleEnterRealm/yk/秘境 API 助手）**面不重叠**
#     · 必须排在 numbal **之前**（numbal 恒最后），也排在 dungeon 之后 —— dungeon 会改
#       hub block 的注入锚 YlxwMin，fun086 的注入锚是 YlxwTDaily 定义前，互不干扰
#   0.8.7 追加理由（implEventsUi 接线，装配序即 0.8.7-build-plan §1.1 定案）：
#     · 七个新模块统一插在 fun086 之后、numbal 之前（numbal 恒最后不动）
#     · grotto087 紧跟 fun086：锚定 fun086 产物形态（F1 加速按钮文案串零回归），
#       T4 修复 + T9 等级路径同 modal 同模块；farm087 紧邻 grotto087 便于洞府↔灵田联动
#     · adv087 必须晚于 eco（复用 T2 注入的 YlxwCvtStones，装配序硬约束 eco → adv087）
#       且按「T2→T6→T11」序排 t6chardex 之后
#     · act087（活动中心）只覆盖注册 YLXW_COMP.events 并调用 toast 宿主（只调用不改宿主），
#       注入锚是 YlxwHub 定义行（紧跟 var YLXW_COMP 之后），与 t7sect/t8mentor 的
#       YLXW_COMP.sect / YLXW_COMP.mentor 覆盖互不同键、互不重叠
#     · numbal 恒最后：它要看到别人注入的块
# ---- 2026-10-09 0.9.50 批接线（R-227 / R-228 / R-230；三个 apply 模块，恒在 numbal 之前）----
#   ★ 这三个模块文件位于 yl-deploy/ 根（HERE 已在 sys.path[1]），非 patches/client/ ——
#     裸名 import 同样成立（patches/client/ 优先，其中无同名文件 ⇒ 落到根）。
#   · r227（死数据清理 specialAbility）：只加 3 处注释标注 + 断言字段一字未删。
#     必须排在 talent097 / r132 / r087 之后 —— 它锚定天赋表 `Un=[{"id":"nt-31"` 的最终形态。
#   · r228（修炼效率明细行改与 bd() 同源）：必须排在 talent097 之后 —— talent097 改的是
#     `bd()` 的 expRate 口径，r228 读的正是 bd() 的返回结构。
#   · r230（天地之髓掉落门槛同构化）：必须排在 r135 / r140b 之后 —— 两者都改过掉落路径
#     （r140b 收紧 hw/xw/gw/bw 掉率），r230 锚定的是同一批掉落函数的最终形态。
#   · 三者彼此锚区零交集（r227=天赋表；r228=bd()/人物志明细行；r230=进阶物品掉落三处）。
from yl_r227_ext import apply as v28_r227_apply  # noqa: E402
from yl_r228_ext import apply as v28_r228_apply  # noqa: E402
from yl_r230_ext import apply as v28_r230_apply  # noqa: E402

V28_MODULES = [
    ('saveretry', v28_saveretry_apply),
    ('arb', v28_arb_apply),
    # ---- 0.8.12 一模块（R-021 离线锚点 + R-020 文案；★ 必须紧跟 arb 之后）----
    ('offline2', v28_offline2_apply),
    ('version', v28_version_apply),
    ('changelog', v28_changelog_apply),   # 游戏内更新日志：玩家向 + 不截断（★ 排 version 之后）
    ('mail', v28_mail_apply),
    ('entry', v28_entry_apply),
    ('sectgf', v28_sectgf_apply),
    ('char', v28_char_apply),
    ('bond', v28_bond_apply),
    ('ui', v28_ui_apply),
    ('chargift', v28_chargift083_apply),
    ('intro', v28_intro083_apply),
    ('flow', v28_flow083_apply),
    ('toast', v28_toast083_apply),
    ('eco', v28_eco085_apply),
    ('dungeon', v28_dungeon085_apply),
    ('fun086', v28_fun086_apply),
    ('grotto087', v28_grotto087_apply),
    # ---- 2026-10-01 第 1 批（R-049 洞府灵草扩地；无硬依赖，紧随 grotto087 便于审阅）----
    ('r049', v28_049_apply),
    ('farm087', v28_farm087_apply),
    ('xinfa087', v28_xinfa087_apply),
    ('t6chardex', v28_t6chardex_apply),
    ('adv087', v28_adv087_apply),
    ('act087', v28_act087_apply),
    ('t7sect', v28_t7sect_apply),
    ('t8mentor', v28_t8mentor_apply),
    ('forge088', v28_forge088_apply),
    ('t17alchemy', v28_t17alchemy_apply),
    ('t16arena', v28_t16arena_apply),
    ('t9quest', v28_t9quest_apply),
    ('t7legacy', v28_t7legacy_apply),
    ('reward089', v28_reward089_apply),
    ('pet089', v28_pet089_apply),
    ('farm089', v28_farm089_apply),
    # ---- 0.8.10 五模块（三步工作流；恒在 numbal 之前）----
    ('v2810a', v28_v2810a_apply),
    ('v2810b', v28_v2810b_apply),
    ('v2810c', v28_v2810c_apply),
    ('v2810d', v28_v2810d_apply),
    ('v2810e', v28_v2810e_apply),
    ('v2810f', v28_v2810f_apply),
    ('v2810g', v28_v2810g_apply),
    ('v2810h', v28_v2810h_apply),
    # ---- 0.8.11 一模块（恒在 numbal 之前）----
    ('v2811a', v28_v2811a_apply),
    # ---- 0.8.12 一模块（R-016 功法；恒在 numbal 之前）----
    ('gongfa', v28_gongfa_apply),
    # ---- 0.8.12 一模块（R-012/014/015 角色系统；恒在 numbal 之前）----
    ('char2', v28_char2_apply),
    # ---- 0.8.12 六模块（R-019/023/027/029/031/032；恒在 numbal 之前）----
    ('farm2', v28_farm2_apply),
    ('medlog', v28_medlog_apply),
    ('daily', v28_daily_apply),
    ('fun2', v28_fun2_apply),
    ('lottery', v28_lottery_apply),
    ('dungeon2', v28_dungeon2_apply),
    # ---- 0.8.13 一模块（M-1 宠物buff $ 字面量 + 效果块孤立 0 守卫；M-2 pS 卡死）----
    #   · 与 dungeon2 零交集（merge01 只碰 PetModal buff 块 / 4 个效果块 / pS 定义；
    #     dungeon2 碰秘境入口与冷却），排在 numbal 之前仅为确定性
    #   · M-1(a) 是真 bug（线上可见 `攻击+$100`）；M-1(b) 35 处 !! 为防御性（0 当前不可达）
    ('merge01', v28_merge01_apply),
    # ---- 0.8.13 二模块（R-034/035/036 人物志任务化；R-013 传承石可交易）----
    #   · renwu：改人物志模态框（Nk）+ 缘契面板 + 师门任务卡 + 掉落稀有度矩阵；
    #     排在末尾使 needle 看到全部前置模块的最终形态（对 t6/char 只用声明引用 + 就地改写）
    #   · r013：改传承系统掉落（机缘 → 传承石）+ 上架交易入口；**硬约束**须晚于 t7legacy
    #     （t7legacy 定义传承等级/定价面），两者锚区零交集
    ('renwu', v28_renwu_apply),
    ('r013', v28_r013_apply),
    # ---- 0.8.13 三模块（数值统一 econ2 / 妖灵重设计 r018；恒在 numbal 之前）----
    ('econ2', v28_econ2_apply),
    # ---- 0.8.13 一模块（R-028 客户端表对齐；★ 必须排在 econ2 之后）----
    ('r013c', v28_r013c_apply),
    ('r024', v28_r024_apply),   # 0.8.11.2 R-024 大境界因子（★ 必须紧接 econ2 之后）
    # ---- 0.8.11.1 一模块（周里程碑「已领取」显示修复；★ 必须排在 r013c 之后）----
    ('claimedfix', v28_claimedfix_apply),
    ('r018', v28_r018_apply),
    # ---- 0.8.13 一模块（★ 冷却机制修复 + 历练冷却还原上游原版；恒在 numbal 之前）----
    ('cooldown', v28_cooldown_apply),
    ('r018b', v28_r018b_apply),          # R-018 D5 灵纹（★ 必须紧接 r018 之后）
    ('r021help', v28_r021help_apply),     # R-021 挂机收益玩法说明
    ('r032layout', v28_r032layout_apply),  # R-032③ 秘境网格降列（去 lg 那档）
    ('r040', v28_r040_apply),              # R-040 效率明细显示对齐（★ 必须排在 econ2 之后）
    ('r037', v28_r037_apply),              # R-037 去掉自带离线修炼
    ('r037b', v28_r037b_apply),             # R-037b 接回离线洞府灵草+寿命（★ 必须紧接 r037）
    ('r041', v28_r041_apply),              # R-041 悟道触发率 + 日志（★ 必须排在 econ2 之后）
    ('r038', v28_r038_apply),              # R-038 天赋页重构（6 随机 + 刷新 + 锁 3 + 6点红）
    ('r042', v28_r042_apply),              # R-042 自动历练频率改慢（★ 必须排在 cooldown 之后）
    ('r043', v28_r043_apply),              # R-043 历练掉血改缓（★ 必须排在 r041 之后）
    ('r039', v28_r039_apply),              # R-039 重置删干净（客户端侧）
    ('r044', v28_r044_apply),              # R-044 历练灵石 ×3（★ 必须排在 r062 之后）
    ('r045', v28_r045_apply),              # R-045 妖灵归位修 bug（★ 必须排在 pet089 之后）
    ('r046', v28_r046_apply),              # R-046 灵田显示精简（★ 必须排在 farm2 之后）
    ('r047', v28_r047_apply),              # R-047 灵田收益（客户端守卫；真值在服务端）
    ('r048', v28_r048_apply),              # R-048 灵草分档 UI（★ 必须排在 farm2 之后）
    ('r070', v28_r070_apply),
    ('r071', v28_r071_apply),
    ('r073', v28_r073_apply),
    ('r074', v28_r074_apply),
    ('r078', v28_r078_apply),              # R-078 收养显示灵石（★ 排 r071 之后）
    ('r082', v28_r082_apply),              # R-082 洞府可收获提示
    # ---- 2026-10-01 第 1 批 R 批次四模块（R-050/051/052/053；恒在 numbal 之前）----
    ('r050', v28_r050_apply),              # R-050 洞府：加速一次半小时 + 每日催熟10次起步（★ 必须排在 v2810c 之后）
    ('r051', v28_r051_apply),              # R-051 日常任务奖励×1.5（★ 必须排在 fun086 之后：其 F2 造出 vs=v*5 形态）
    ('r052', v28_r052_apply),              # R-052 周活跃度显示修：week 日期串 → weekActivity 数值（★ 必须排在 claimedfix 之后）
    ('r053', v28_r053_apply),              # R-053 茶馆玩法说明+灰因动态提示（★ 必须排在 fun2 之后）
    # ---- 2026-10-01 第 2 批 R 批次五模块（R-054~R-058；恒在 numbal 之前）----
    ('r054', v28_r054_apply),              # R-054 每日签到：七日礼→月历长期签到+修为/灵石+里程碑（★ 锚在 act087 注入区，必须排其后；与 r055 无序依赖，双向已验证）
    ('r055', v28_r055_apply),              # R-055 灵玉阁玩法说明+掉落口径透明化（★ 必须排在 act087 之后；建议 r053 之后、numbal 之前）
    ('r056', v28_r056_apply),              # R-056 万妖巢穴多boss：每期5只+每只免费5次+10分钟冷却（★ 锚在 act087 注入块内，必须排在 act087 之后；服务端配套 = SRV_CHAIN 链尾 'srv_patch_056.py'）
    ('r057', v28_057_apply),               # R-057 奇遇抽奖 UI 面：冷却禁用/倒计时/规则说明/暴击 toast（服务端配套 = SRV_CHAIN 链尾 'srv_patch_057.py'）
    ('r058', v28_r058_apply),              # R-058 缘契寻访任务板「整体刷新」按钮（★ 必须排在 renwu 之后）
    # 2026-10-01 第 3 批 R 批次五模块（R-059~R-063；恒在 numbal 之前）：
    ('r059', v28_059_apply),               # R-059 寻访好感递减+解锁档2→4带奖励（★ 必须排在 renwu/t6chardex 之后）
    ('r060', v28_r060_apply),              # R-060 师门任务好感按提交品阶 + 单条刷新每日限3次（★ 必须排在 renwu 之后）
    ('r061', v28_061_apply),               # R-061 演武场试炼：战报反馈+次数即时刷新（★ 必须排在 t16arena 之后；服务端配套 = SRV_CHAIN 链尾 'srv_patch_061.py'）
    ('r062', v28_062_apply),               # R-062 秘境单独点选收益×3 + 冷却15分钟（★ 必须排在 eco085/dungeon2 之后；服务端配套 = SRV_CHAIN 链尾 'srv_patch_062.py'）
    ('r063', v28_063_apply),               # R-063 roguelike 地宫单独算上限（★ 必须排在 dungeon085/dungeon2/v2811a 之后；服务端配套 = SRV_CHAIN 链尾 'srv_patch_063.py'）
    # ---- 2026-10-01 第 4 批 R 批次五模块（R-064~R-068；恒在 numbal 之前）----
    ('r064', v28_064_apply),               # R-064 炼丹：出炉加丹道造诣+丹方药效数值透明化+丹炉 3→9 方（★ 排在 r063 之后；服务端配套 = SRV_CHAIN 链尾 srv_patch_064.py，--src srv/index_v28.ts）
    ('r065', v28_065_apply),               # R-065 宗门页只做宗门内容：摘 xw:"sect" 融合标记（1 处替换；无硬依赖，锚在 base 原生存在）
    ('r066', v28_r066_apply),              # R-066 宗门功法阁：贡献值重做（基价×2~×2.7+每层×2指数）+ 修满化形转实装功法（★ 必须排在 sectgf 之后；服务端配套 = SRV_CHAIN 链尾 'srv_patch_066.py'）
    ('r067', v28_r067_apply),              # R-067 功法五行分类+扩充55部（★ 必须排在 gongfa 之后、numbal 之前：功法阁 UI 锚消费 R-016 改后的 z4 语义；YlxwElemInit 先于 numbal 预算重算）
    ('r068', v28_r068_apply),              # R-068 人物志自带结交降频（★ 必须排在 t6chardex 之后）
    # ---- 0.9.x 批次（★ 全部必须排在 r064/r065/r066 之后：r077 锚 R-064 的出炉产出行）----
    ('r076', v28_r076_apply),              # R-076 roguelike 秘境 = 普通 2 倍
    ('r077', v28_r077_apply),              # R-077 开炉出丹随机数量（★ 必须排 r064 之后）
    ('r079', v28_r079_apply),              # R-079 补全玩法介绍
    ('r080', v28_r080_apply),              # R-080 抽奖保底 UI（★ 排 v2810d 之后）
    ('r081', v28_r081_apply),              # R-081 宗门俸禄按职位
    # ---- 0.9.3（R-083 云端刷新弹窗 + 仓库链接；纯字符串替换，无硬依赖，恒在 numbal 之前）----
    ('r083', v28_r083_apply),              # R-083 去掉阻塞弹窗 + 2 处 GitHub 链接改指本仓库
    # ---- 0.9.4（寿元体系；恒在 numbal 之前，冷却值由 r042 负责）----
    ('life094', v28_life094_apply),        # 自动历练寿元 ×0.05 + 每次报扣减 + 打坐每跳扣寿元
    # ---- 0.9.6（突破奖励大幅提升 + 每点属性加成提升）----
    ('bt096', v28_bt096_apply),
    # ---- 0.9.7 ----
    ('attr097', v28_attr097_apply),        # R-095 体魄=防御+气血各半 / R-096 气血 1 点=100
    ('life097', v28_life097_apply),        # R-099 寿元表按《凡人修仙传》+ 50/50 分段（★ 必须排 bt096 之后）
    ('linggen097', v28_linggen097_apply),  # R-098 五系灵根独有被动（只挂 xt，不动既有灵根口径）
    # ---- 0.9.8（★ talent097 改 bd 的 expRate 口径，必须排在 numbal 预算重算之前）----
    ('speedname097', v28_speedname097_apply),  # 「速度」→「身法」文案改名（只动中文，不碰字段名）
    ('talent097', v28_talent097_apply),        # R-085 天赋数值 ×3 + expRate ×0.5 + 放开压制 / R-087 颜色按点数分档
    ('adv097', v28_adv097_apply),              # R-089 历练灵石 ×3 + 每次写成果日志 / R-090 顿悟 0.2%→0.4%
    ('dao097', v28_dao097_apply),              # R-091 悟道面板显示 exp/下级所需（服务端逻辑未动）
    # ---- 0.9.9 ----
    ('shoprefresh101', v28_shoprefresh101_apply),  # R-101 历练商店：首次刷新免费、之后 500 灵石
    ('chardex101', v28_chardex101_apply),          # R-084 人物志与道友图鉴·缘契解耦 + 图鉴里程碑领奖
    # ---- 0.9.10（★ advend105 必须排 adv097 之后：它挂 adv097 的结算调用点）----
    ('shop102', v28_shop102_apply),                # R-102 名字后多「0」/ R-103 商店等阶闸门+售价 / R-104 库存上限
    ('advend105', v28_advend105_apply),            # R-105 自动历练结束汇总推送（时长+成果）
    # ---- 0.9.11 四模块（R-106~R-109；恒在 numbal 之前）----
    ('r106', v28_r106_apply),              # R-106 道具描述/预览按 $r 折算显示（只改显示口径，不碰数值表）
    ('r107', v28_r107_apply),              # R-107 道具数值/售价重配（★ 必须排 r106 之后：r106 的冻结断言认它的定稿值）
    ('r108', v28_r108_apply),              # R-108 商店刷新：保留首次免费 + 恢复 2 万~8 万分级价 + 显示同步（★ 必须排 shoprefresh101 之后）
    ('r109', v28_r109_apply),              # R-109 加点面板「每点增量」改读 Ps（原为上游写死副本，0.9.6/0.9.7 抬值后漏改）
    # ---- 2026-10-02 链式自动轮次第 2 批（R-111/R-113/R-114/R-115；恒在 numbal 之前）----
    ('r111', v28_r111_apply),              # R-111 每日签到可用（★ 服务端配套 = SRV_CHAIN 'srv_patch_111.py'）
    ('r113', v28_r113_apply),              # R-113 万妖巢穴五 boss 同现 + 逐只次数/冷却（★ 服务端配套 = SRV_CHAIN 'srv_patch_113.py'；必须排 r056 之后）
    ('r114', v28_r114_apply),              # R-114 历练收获：修「修为 0 · 灵石 0」+ 参照打坐丰富化（★ 必须排 adv097/advend105 之后）
    ('r115', v28_r115_apply),              # R-115 洞府灵田：价格/等阶可见/扩地按钮/田位扩容/灵草悬停（★ 服务端配套 = SRV_CHAIN 'srv_patch_115.py'；必须排 farm089/farm2/r048/v2810c 之后）
    # ---- 2026-10-02 0.9.13 第 1 批接线（R-124 apply 模块；R-116/R-118 standalone 见 STANDALONE_CLIENT）----
    ('r124', v28_r124_apply),              # R-124 灵田服用预览：FT_ATTR 补 spirit:神识（★ 必须排 farm089/speedname097 之后；服务端配套 = SRV_CHAIN 'srv_patch_r124.py'）
    # ---- 2026-10-09 0.9.50 批（R-227 / R-228 / R-230；序 = 编号序，三者锚区零交集）----
    ('r227', v28_r227_apply),              # R-227 specialAbility 死数据：保留字段 + 3 处显式标注（唯一活消费点 = R38 建号向导卡 ⭐）
    ('r228', v28_r228_apply),              # R-228 修炼效率明细行权重 0.26/0.6/0.6/0.1/0.32 → 改读 bd() 返回值（同源，杜绝双写）
    ('r230', v28_r230_apply),              # R-230 天地之髓掉落门槛 [化神,∞) → [元婴,化神]（与天地精华同构；历练/额外/黑市 + minRealm 共 4 处）
    ('numbal', v28_numbal_apply),
]

# ---- 0.9.13 成员新契约：standalone 客户端补丁脚本（lead 装配层接线）----
#   这两份的契约只有 CLI `--src <装配产物>`（二进制读写、就地原子写回、自带 .bak/幂等/门禁），
#   不是 apply(p, ctx) 模块 ⇒ **不能进 V28_MODULES**；由装配层在 build() 全模块应用并落盘之后
#   对最终产物按序套用（顺序 = 列表序，两脚本锚区零交集）。dryrun_087 对 _chainstage 预演产物
#   做同一套用 ⇒ 「预演==交付」md5 仍逐位成立。门禁表 = 各脚本 gates()（dryrun 收录重跑）。
#   srv 半边不走这里：srv_patch_r116.py / srv_patch_r124.py 已接线进 chain_build.SRV_CHAIN。
STANDALONE_CLIENT = [
    ('r116', os.path.join(HERE, 'localtest', 'yl_r116_ext.py')),   # R-116 抽奖池自回流券权重 15/3/.5 → 4/.6/.08（对产物已展开串替换）
    ('r118', os.path.join(HERE, 'localtest', 'yl_r118_ext.py')),   # R-118 打坐结束日志加「共打坐 N 次」（锚 medlog 展开块）
    # ---- 2026-10-02 0.9.13 第 2 批接线（同契约；序=编号序，三脚本锚区互零交集）----
    ('r119', os.path.join(HERE, 'localtest', 'yl_r119_ext.py')),   # R-119 装备神识/身法重配（改活链 iy/ry 四锚；纯客户端，无 srv 半边）
    ('r125', os.path.join(HERE, 'localtest', 'yl_r125_ext.py')),   # R-125 洞府可扩每级 +≥1 + 扩地价格表 14→18 档根治 NaN 扣款（纯客户端）
    ('r126', os.path.join(HERE, 'localtest', 'yl_r126_ext.py')),   # R-126 图鉴 7 档奖励加码 + doClaim 发放接线 stones/exp×YLRF（纯客户端）
    # ---- 2026-10-02 0.9.13 第 3 批接线（同契约；序=编号序）----
    ('r120', os.path.join(HERE, 'localtest', 'yl_r120_ext.py')),   # R-120 羁绊作用说明（锚 r018 妖灵卡展开块；纯客户端）
    ('r121', os.path.join(HERE, 'localtest', 'yl_r121_ext.py')),   # R-121 全局玩法说明补齐 23 处（混合态 rc=4 拒写；纯客户端）
    ('r123', os.path.join(HERE, 'localtest', 'yl_r123_ext.py')),   # R-123 指引 8 步奖励客户端面（★ 服务端配套 = SRV_CHAIN 'srv_patch_r123.py'）
    ('r128', os.path.join(HERE, 'localtest', 'yl_r128_ext.py')),   # R-128 掷骰翻牌客户端面（锚 fun086 注入块；★ 服务端配套 = SRV_CHAIN 'srv_patch_r128.py'）
    ('r131', os.path.join(HERE, 'localtest', 'yl_r131_ext.py')),   # R-131 缘契 DEXMILE 4→7 档+上限 200+UNL59 落修为（锚 chardex101+r059 产物；★ chardex101 装配态门禁不放宽——终态清零断言在本脚本 gates()）
    # ---- 2026-10-02 0.9.14 第 1 批接线（序=编号序；R-112 走 SRV_CHAIN，客户端墓碑不接线）----
    ('r132', os.path.join(HERE, 'localtest', 'yl_r132_ext.py')),   # R-132 天赋金红互换（8点=红/6点=金）+ 种类梯度重排（锚 r087 swap 行+boost 调用行；★ talent097「对调==1」终态清零断言在本脚本 gates()）
    # ---- 2026-10-02 0.9.15 热修接线（单点显示缺陷；纯客户端，服务端零改动）----
    ('r131fix', os.path.join(HERE, 'localtest', 'yl_r131fix_ext.py')),   # R131 灵玉阁余额恒 0 热修（bal 读值 d.balance→d.jadeBalance 优先+旧字段兜底；服务端 [v2810] 已改名，锚=全语句唯一）
    # ---- 2026-10-03 0.9.16 工作流批（R-133~R-139；序=编号序，七脚本锚区经全量 standalone 门禁实证零交集）----
    ('r133', os.path.join(HERE, 'localtest', 'yl_r133_ext.py')),   # R-133 历练抽奖券：数量恒 1 + 触发率 2.7%→0.27%（池内 1/37 × case 内 10% 门；纯客户端）
    ('r134', os.path.join(HERE, 'localtest', 'yl_r134_ext.py')),   # R-134 奇遇修为 300~799→200~300（xw() 的 expChange；灵石/掉落/HP 冻结；纯客户端）
    ('r135', os.path.join(HERE, 'localtest', 'yl_r135_ext.py')),   # R-135 历练商店：稀有属性物品售价 ×6、普通 ×1.5 + 高稀有度掉落概率大幅下调（纯客户端）
    ('r136', os.path.join(HERE, 'localtest', 'yl_r136_ext.py')),   # R-136A 秘境手札加「地宫冷却」行（读 /dungeon/status 的 rogueCdLeftMs；★ B 半 = SRV_CHAIN 'srv_patch_r136.py'）
    ('r137', os.path.join(HERE, 'localtest', 'yl_r137_ext.py')),   # R-137 地宫「再次探索」冷却中弹 toast（YlxwToast，addLog 保留；纯客户端）
    ('r138', os.path.join(HERE, 'localtest', 'yl_r138_ext.py')),   # R-138 自动历练：单次结算行补数量/事件名 + 会话结束多行汇总块（纯客户端）
    ('r139', os.path.join(HERE, 'localtest', 'yl_r139_ext.py')),   # R-139 隐藏标签不停摆：打坐/历练/冷却倒计时三处定时器改 Worker 心跳驱动（CSP 失败自动回退；纯客户端）
    # ---- 2026-10-03 0.9.17 工作流批（R-140 消耗品数值重构 + R-141 装备稀有属性；序=编号序，锚区经全量 standalone 门禁实证零交集）----
    ('r140', os.path.join(HERE, 'localtest', 'yl_r140_ext.py')),   # R-140 批1 数值：fg 品质地板大砍 + Rr/mw 仙品地板下调 + Ic 缩放重配 + 丹药/草药表逐条重做 + 死键清理（纯客户端）
    ('r140b', os.path.join(HERE, 'localtest', 'yl_r140b_ext.py')), # R-140 批1 经济 + 批2 硬顶：消耗品售价品质阶梯（装备沿用 R-135 三元逐字不动）+ hw/xw/gw/bw 掉率收紧 + vg 升档减半 + $r 下限 .10 + 永久属性 ZS×2.0 硬顶（0.9.19 调参：比例 1.0→2.0）（★ 必须排在 r135 之后——B 组锚点是 R-135 改后形态）
    ('r141', os.path.join(HERE, 'localtest', 'yl_r141_ext.py')),   # R-141 装备稀有属性：vs() 授予管道注入 innateAffixes（境界凸曲线 × 品质条数 普通0/稀有1/传说2/仙品4 × K=0.5；攻/防/气血三类走独立区间表）+ YlxwStatExtras/YlxwBattleBonus 合并消费（0.9.19 调参：K 0.35→0.5、仙品 3→4 条、新增三类表；纯客户端）
    # ---- 2026-10-03 0.9.18 修 bug 批（R-142 灵田死字段 + R-143 技能吸血；序=编号序）----
    ('r142', os.path.join(HERE, 'localtest', 'yl_r142_ext.py')),   # R-142 灵田稀有草接线：YlxwBattleBonus 追加读 player.critRate/dodgeRate/lifeLeech（此前服务端写档但客户端从不读=死字段；末尾由 YlxwBattleCap 封顶）
    ('r143', os.path.join(HERE, 'localtest', 'yl_r143_ext.py')),   # R-143 回合制技能补吸血分支：zy() 结算后按 km 语义回血（仅玩家、取最强单条 lifeLeech；纯客户端）
    # ---- 2026-10-03 0.9.19 批（R-140/R-141 调参 + R-144 在线面板 + R-145 历练灵石 + R-146 日志合并；序=编号序）----
    ('r144', os.path.join(HERE, 'localtest', 'yl_r144_ext.py')),   # R-144 在线人数徽章 → 按钮 + 在线/好友面板（覆盖层；近似在线名单 = 最近 60 条发言去重；纯客户端）
    ('r145', os.path.join(HERE, 'localtest', 'yl_r145_ext.py')),   # R-145 自动历练灵石收益 ×5→×15 + 零灵石兜底 min(50,max(1,floor(修为收益×0.5)))（纯客户端）
    ('r146', os.path.join(HERE, 'localtest', 'yl_r146_ext.py')),   # R-146 自动历练结算展示合并成一行 + 去重（同帧微批 flush；纯客户端）
    ('r155', os.path.join(HERE, 'localtest', 'yl_r155_ext.py')),   # R-155 自动历练「结束汇总」7 条 → 1 条（收集 YLXW_ADV156_LINES + join(" · ") 单次 add；★ 必须排 r138/r146 之后——锚点是 R-138 的 YlxwAdvSummary 与 R-105 的 YlxwAdvSession）（纯客户端）
    ('r161', os.path.join(HERE, 'localtest', 'yl_r161_ext.py')),   # R-161 日志：寿元行与历练收获行拆分 + R-155 汇总行去重（★ 必须排 r146/r155 之后——锚点是 R-146 flush 与 R-155 的 _l155 汇总）（纯客户端）
    ('r162', os.path.join(HERE, 'localtest', 'yl_r162_ext.py')),   # R-162 日志：宠物消息/[灵石]来源跳过 R-146 合并 blob（★ 必须排 r146/r161 之后）（纯客户端）
    ('r163', os.path.join(HERE, 'localtest', 'yl_r163_ext.py')),   # R-163 灵田：一键收取确认文案 + 玩法说明口径（服务端数值见 srv_patch_r163.py 第 71 环）（纯客户端）
    # ---- 2026-10-06 0.9.25 批（R-165 悟道顿悟点 + R-166 妖灵放生确认；序=编号序，锚区经全量 standalone 门禁实证零交集）----
    ('r165', os.path.join(HERE, 'localtest', 'yl_r165_ext.py')),   # R-165 打坐「顿悟」同一触发点产生悟道心得（新增助手 YlxwWudaoEnlighten 走 YlxwPost；★ 服务端配套 = SRV_CHAIN 'srv_patch_r165.py' 第 72 环新端点 POST /api/wudao/enlighten）（纯客户端半边）
    ('r166', os.path.join(HERE, 'localtest', 'yl_r166_ext.py')),   # R-166 仙务·妖灵「放生妖灵」补确认弹窗（唯一无确认入口 YlxwR18AwayReleaseRow；包一层 window.confirm，取消不发请求）（纯客户端，无服务端半边）
    # ---- 2026-10-06 0.9.26 批（R-167 妖灵面板合并 + R-169 旧草药名别名；序=编号序，锚区零交集）----
    ('r167', os.path.join(HERE, 'localtest', 'yl_r167_ext.py')),   # R-167 仙务·妖灵：删掉重复的独立「喂养/嬉戏」按钮并入进食/互动两行 + 「今日互动」标题自解释（★ 服务端配套 = SRV_CHAIN 'srv_patch_r167.py' 第 73 环：喂养当日首次免费）
    ('r169', os.path.join(HERE, 'localtest', 'yl_r169_ext.py')),   # R-169 洞府灵草：__halias 别名表补齐改名前的旧名（血参草→血参 等 5 条）⇒ 旧存档收菜不再走「配置缺失折算回收」兜底（纯客户端）
    # ---- 2026-10-06 0.9.27 批（R-169 二环·根治；★ 必须排 r169 之后——锚点是 r169 改后的 __halias 形态）----
    ('r169b', os.path.join(HERE, 'localtest', 'yl_r169b_ext.py')), # R-169 二环：收获路径与种植路径对称化（四级查找全落空时调同一个 f() 合成灵草定义 ⇒ 「补上道具」）+ 空名条目从灵田列表过滤（⇒「删掉选项」）+ **彻底删除「折算回收」分支**（纯客户端，无服务端半边）
    # ---- 2026-10-06 0.9.28 批（R-174/R-175/R-176/R-177/R-179；序=编号序，五脚本锚区经全量 standalone 门禁实证零交集）----
    ('r174', os.path.join(HERE, 'localtest', 'yl_r174_ext.py')),   # R-174 活动中心：签到行从面板最底部前移到标题之后、其它活动块之前（纯渲染顺序调整，原位留 /*[r174act]*/ 哨兵；纯客户端）
    ('r175', os.path.join(HERE, 'localtest', 'yl_r175_ext.py')),   # R-175 万妖巢穴：排行榜由合计榜改为读 top10ByBoss **逐只渲染 5 段** + 缺失/空数组时回落旧 top10（★ 服务端半边 = SRV_CHAIN 'srv_patch_r175.py' 第 78 环）
    ('r176', os.path.join(HERE, 'localtest', 'yl_r176_ext.py')),   # R-176 抽奖券抽奖：奖品池按「玩家境界 ↔ 奖品境界」差 d 收敛（倍率 1e7/1e4/1e2/1）**+ 删除「越阶→折算灵石」兜底段**（★ 真对象是客户端；服务端 srv_patch_r176.py 经判定越界、不接线）
    ('r177', os.path.join(HERE, 'localtest', 'yl_r177_ext.py')),   # R-177+R-178 历练：①节奏统一冷却到 9s（主路 10→9 / 商店路 2→9，消除 5.2 倍带宽）②三档权重改为 高档×0.5 / 中档×0.88（阈值 200→100，原中档是死代码）/ 低档×1（纯客户端）
    ('r179', os.path.join(HERE, 'localtest', 'yl_r179_ext.py')),   # R-179 历练结算信息：去 3 处重复（时长/次数/奇遇）+ 按「时长·次数·修为·灵石·寿命·气血·物品」重排 + 「——— 明细 ———」分割 + 新增寿命变化累加与条件渲染（纯客户端）
    # ---- 2026-10-07 0.9.30 批（R-180/R-181/R-183/R-185/R-188；序=编号序，
    #      ★ 五脚本已用「串行套用 + node --check」实证零交集；r188 原先钉死 [r180adv]==0 的跨补丁针脚已删（8 条），
    #        现两顺序产物 SHA256 逐位相同 ⇒ 顺序无关）----
    ('r180', os.path.join(HERE, 'localtest', 'yl_r180_ext.py')),   # R-180 历练三合一：①寿命减少累计（接进 Pc() 的 h）②灵石事件概率（主路中档 ×.30 + 奇遇量级降）③掉血改「按 maxHp 百分比 + 几率触发」、回血几率化 + 60 分硬上限（阈值=0 时上限也关）（纯客户端）
    ('r181', os.path.join(HERE, 'localtest', 'yl_r181_ext.py')),   # R-181 筑基奇物属性实装：把 Vn[player.foundationTreasure].effects 接进 xt() 的 YlxwSpiritExtras 钩子（原 9 个读取点全是只读展示）+ 神识/身法 ÷8 归一（纯客户端）
    ('r183', os.path.join(HERE, 'localtest', 'yl_r183_ext.py')),   # R-183 修为体系重定档：升级所需经验分级倍率 K=[14,6,4,2.5,1.5,1,1]（炼气 5.82h/层，高阶段只收紧不放松）（纯客户端）
    ('r185', os.path.join(HERE, 'localtest', 'yl_r185_ext.py')),   # R-185 洞府「灵田联动」文案：可开垦 → 最大可扩展（把 headroom 与总数区分开，消除与左侧灵田页的术语冲突）（纯客户端）
    ('r188', os.path.join(HERE, 'localtest', 'yl_r188_ext.py')),   # R-188 打坐：天赋「一念悟道」的 15% 顿悟从未接线（triggerChance 全 bundle 无一处被读取）⇒ 按既有范式 player.talentIds.includes("instant-dao") 接进判定行（单次 Math.random 保持）（纯客户端）
    # ---- 2026-10-07 0.9.31 批（R-184 / R-187 / R-190；序=编号序）----
    #      ★★ 集成顺序硬约束：**R-180（v2，E3 回滚）必须先于 R-184**（上面 r180 已在前）——
    #         R-184 的触发判据建立在「奇遇灵石量级已恢复 Ge(t,200,500,490)」之上；
    #         顺序颠倒时炼气期命中率实测 = 0.000%（等于没修）。详见 yl_r184_ext.py docstring §二。
    ('r184', os.path.join(HERE, 'localtest', 'yl_r184_ext.py')),   # R-184 功法悟道：历练侧从未接线（YlxwWudaoEnlighten 唯一调用点=打坐顿悟分支）⇒ 挂到「加几千灵石」的稀有事件上（判据 tpl.spiritStonesChange>=200，恰 ⟺ 奇遇事件；★ 依赖 R-180 v2 先套用）（纯客户端）
    ('r187', os.path.join(HERE, 'localtest', 'yl_r187_ext.py')),   # R-187 仙途指引：R-172 只改了服务端半边、漏了客户端「玩法说明」⇒ 面板说明数字与服务端实发不一致（说明 6000/8000/20000 vs 实发 8600/9900/61000）⇒ 同步为实发值（纯客户端）
    ('r190', os.path.join(HERE, 'localtest', 'yl_r190_ext.py')),   # R-190 灵宠血量喂养：收益倍率 U 1.5→0.03（÷50，目标「几次满血才升一级」）+ 血量喂养不再给亲密度（hp 走 0，修为/物品逐字不变）+ 闸门口径对齐实扣（200→1000）（纯客户端）
    ('r189', os.path.join(HERE, 'localtest', 'yl_r189_ext.py')),   # R-189 妖灵系统文案与实际对齐（第 1 批，纯文案/标签）：①「灵宠作用/妖灵本体」标注为「灵宠口径参考（非当前加成）」②互动次数标题去掉虚假总上限 ③进食行补「今日首次免费」④术语统一 喂食度/收养/进食/互动 ⑤两个「秘径」区分为 妖灵秘径·派遣 / 灵兽秘径·单次 ⑥玩法记录补全 7 类标签（斗法→精魄）⑦补 品阶K/等级K/资质K 定义（纯客户端）
    ('r189b', os.path.join(HERE, 'localtest', 'yl_r189b_ext.py')), # R-189 第 2 批：主人加成 6% → **10%** 的**客户端文案**同步（4 处；服务端常量改动见 srv_patch_r191.py 第 82 环）
    ('r189c', os.path.join(HERE, 'localtest', 'yl_r189c_ext.py')), # R-189 第 2 批：灵纹**可见化** —— 4 条加成经取证**全部已实装生效**（用户判断不成立）⇒ 数值零改动，仅在灵纹区新增一行显示当前生效灵纹的真实战斗贡献（读 petSpirit.rune*）
    ('r191', os.path.join(HERE, 'localtest', 'yl_r191_ext.py')),  # R-191 奇遇率修复：`V=Math.min(.3,0.01+luck*.001)` 被幸运项淹没（天赋/命运 nt-50/nt-69 经 R-132 覆盖表给 luck:300 ⇒ V=0.30=30%）⇒ 改 `V=0.01+Math.min(0.01,luck*0.00003)`（1%~2% 封顶，不引入境界项）+ 结算日志新增「分档 常态/几百/几千」触发次数（纯客户端）
    ('r192', os.path.join(HERE, 'localtest', 'yl_r192_ext.py')),  # R-191（台账号）融合弹窗：`YlxwPetShell` 的 doToast 完全无视 tone、恒调 error 提示器 ⇒ 成功消息被套进「错误」弹窗（融合本身确实成功，纯客户端）⇒ 按 tone 分派（danger→Je 红；其它→ia 绿）（纯客户端）
    ('r193', os.path.join(HERE, 'localtest', 'yl_r193_ext.py')),  # R-193 奇遇率 v2（用户拍板「幸运彻底移除 + 称号最大加成 3%」）：`V=0.01+Math.min(0.03, $a(titleId,unlockedTitles).luck*0.0003)` —— 用「纯称号来源」的 $a()（不含天赋 luck）⇒ 默认 1%、顶配称号 4%（纯客户端）
    ('r195', os.path.join(HERE, 'localtest', 'yl_r195_ext.py')),  # R-195 妖灵归位：① 修「等级 1 属性」bug（改用妖灵真实等级）② 整体乘 M=1.5×(1+羁绊/1000)×(1+资质/200)∈[1.5,3.375] ③ 名称改「妖灵·<原名>」（species 一字未动，保进化/秘径）④ 落 isSpirit 标记做独立一类灵宠；并让属性重算闭包 j 感知 spiritMul（5 处调用点，普通宠传 0 ⇒ 零回归）（纯客户端）
    ('r196', os.path.join(HERE, 'localtest', 'yl_r196_ext.py')),  # R-196 灵纹前 4 条重设（客户端半边）：锐纹新增暴伤需客户端接线（读 petSpirit.runeCritDmg）+ 可见化行追加暴伤展示；★ 依赖顺序 r189c → r196（纯客户端）
    ('r197', os.path.join(HERE, 'localtest', 'yl_r197_ext.py')),  # R-197 R-189② UI 调整：①「灵宠口径参考（非当前加成）」整块搬到妖灵卡片正下方（红框位）并改名「妖灵折算灵宠属性（参考）」②「融合玩法」整块搬进灵宠弹窗右列（「我的灵宠 (N)」正上方），妖灵页签内移除（顺带消除 YlxwPetOnFuseRef 隐式依赖）（纯客户端）
    ('r198', os.path.join(HERE, 'localtest', 'yl_r198_ext.py')),  # R-198 R-189③④ 免费玩法栏：新增「免费玩法」分组（免费进食 +100 喂食度/每日3次/冷却30分 + 免费互动三按钮，三按钮为**搬移**非新增）→ 再接「进食」→「买额度」上限 2→5（3 项共用）；并修「玩法说明②」过时文案（纯客户端；服务端见 srv_patch_r198.py 第 85 环）
    ('r199', os.path.join(HERE, 'localtest', 'yl_r199_ext.py')),  # R-199 自动历练频率调快：冷却 d(9) → d(7)（**只改 3 处自动历练常规单轮**：正常收尾 finally / 商店跳过 / 商店访问）⇒ 单轮 10.44s → 8.44s（每轮精确快 2s）；★ 打坐(2s)与 B 组手动/避战/天地之魄(1~2s)一律不动（改 7 反而变慢）（纯客户端）
    ('r200', os.path.join(HERE, 'localtest', 'yl_r200_ext.py')),  # R-192 去掉 R-167「当日首次免费」喂养（客户端半边）：进食三档按钮文案删掉后缀 `+ (fq.free ? " · 今日首次免费" : "")`，并连带删除因此变死变量的 `var fq = (t && t.feedQuota) || {};`；★「玩法说明①」本来就没提首免 ⇒ 一字未动（纯客户端；服务端见 srv_patch_r200.py 第 86 环）
    ('r202', os.path.join(HERE, 'localtest', 'yl_r202_ext.py')),  # R-195 灵宠喂养「文字 vs 实现」审计与修复：修 8 处过期文字（血量喂养 200→1000、批量喂血 /200→/1000、物品/修为喂养亲密度 +2~5→+1~2、修为喂养 5%→25%、两处 toast/报错数字），并全游戏核过 8 个玩法说明块与实现一致（纯客户端；落盘号 r202 —— 旧 R-195「妖灵归位」占用 yl_r195_ext.py）
    ('r203', os.path.join(HERE, 'localtest', 'yl_r203_ext.py')),  # R-196 冷却「静态快照」→「走秒倒计时」：新增 YlxwR196Tick/Remain/Left/Cd 四个 helper + 在 6 处（8 个代码点：免费进食 / 奇遇抽奖 / 秘境+地宫 / 灵田照料×2 / 万妖巢穴 / 渡劫面板）接上组件内局部 tick；把服务端下发的「剩余量」换算成绝对 deadline 后每秒重算；★ 无全局 setInterval、不改任何文案（纯客户端；落盘号 r203 —— 旧 R-196「灵纹重设」占用 yl_r196_ext.py）
    ('r204', os.path.join(HERE, 'localtest', 'yl_r204_ext.py')),  # R-197 修为喂养改 2% + 转换比例下调：消耗（文案/闸门/实扣三处）25%→**2%**、倍率 U 2→**0.5**（hp 0.03 / item 3.5 未动）；★ 真·正比（获得=消耗×R）经测算不可用（跨境界差 500 倍）⇒ 保留按境界算固定量的机制（纯客户端；落盘号 r204）
    ('r206', os.path.join(HERE, 'localtest', 'yl_r206_ext.py')),  # R-199 挂机历练寿命消耗下调：YLXW_LIFE_AUTO_MUL 0.05→**0.0125** ⇒ 挂机单次 0.4×0.0125 = **0.005**（原 0.02）；★ 手动历练 0.4 未动（纯客户端；落盘号 r206）
    ('r207', os.path.join(HERE, 'localtest', 'yl_r207_ext.py')),  # R-198 心法学习改「点一次加经验」：六卷面板改读 levelExp/levelNeed 进度 + 「点一次消耗 P 灵石 · 本级进度 X/Y」；★ 配套服务端见 srv_patch_r207.py 第 88 环（C 方案：阈值×7.5 / 单价按档×2.5 / 每档恒定 3 次 / 满级 396 万）（纯客户端半边）
    ('r208', os.path.join(HERE, 'localtest', 'yl_r208_ext.py')),  # R-208 历练结算「分档」标签改名：常态→寻常 / 几百→丰厚 / 几千→横财（只改渲染行三个词，代码注释里的旧词逐字保留）（纯客户端）
    ('r209', os.path.join(HERE, 'localtest', 'yl_r209_ext.py')),  # R-201 历练结算「几百」档下界 150 → **370**：实测（真实 1200 模板 + 真实 Fm 权重 + 真实战斗路）T∈[363,377] 为平台区，370 取中点 ⇒ 几百 34.7%→16.1%、常态 64.4%→83.0%、几千 0.9% 不误伤（纯客户端；落盘号 r209）
    ('r210', os.path.join(HERE, 'localtest', 'yl_r210_ext.py')),  # R-202 灵宠经验曲线 1.2^L → **1.1^L**（4 处宠物升级循环）+ 存量宠物 maxExp 迁移（ho 钩子：只降不升、exp 等比缩放 ⇒ 幂等且不爆级）；L1→L100 总需求 2.07e10 → 7.52e6（纯客户端；落盘号 r210）
    ('r211', os.path.join(HERE, 'localtest', 'yl_r211_ext.py')),  # R-204 历练分档阈值**随境界缩放**：判定行逐字不动，改为把**判定输入归一化** `ds/u`（与「阈值×u」严格等价）⇒ 档位概率与境界**无关**（恒 83/16/1）。u 由 `Fg` 经 window.YLXW_ADV_PL 外挂传入（★ 签名/调用点被 r138/r155/r161/r184/r191 钉死，不能改）（纯客户端；落盘号 r211）
    ('r212', os.path.join(HERE, 'localtest', 'yl_r212_ext.py')),  # R-205 分档**频率**重标定（边界 200 不动）：① 战斗触发率 ×0.15（25.3%→9.8%，落进既有下限 0.1 ⇒ 触发率**恒 10%**、境界项被吸收）② 中档模板权重 0.7→0.32 ③ 长生 longevityRule 降权 ×0.05 ⇒ **7 境界全 85/14/1**（代价：均值灵石 炼气 −37.6% / 长生 −67.3%，用户已拍板）（纯客户端；落盘号 r212）
    # ---- 2026-10-09 0.9.43 批（R-209 在线人数改我方口径；纯客户端）----
    ('r213', os.path.join(HERE, 'localtest', 'yl_r213_ext.py')),  # R-209 在线人数：头部徽标原取**外部 partykit**（上游作者的服务器）的 onlineCount，与「在线人物」面板（我们服务器 /api/online/players）不同源 ⇒ 显示 3 但名单只有自己。改为轮询我方 /online/players 写入 party hook 的模块级 Dr，并掐掉 party 的两个写 Dr 分支 ⇒ 徽标 / 面板标题 / 名单人数三者恒等（纯客户端；服务端零改动）
    # ---- 2026-10-09 0.9.44 批（R-210 心法按钮/进度提示；纯客户端）----
    ('r214', os.path.join(HERE, 'localtest', 'yl_r214_ext.py')),  # R-210 功法阁·心法：按钮由「修炼」→「修炼 +X 经验」（X=costNext，=服务端每次 exp 增量）；进度条 h-1.5→h-2.5 并补百分比（与条宽同源）；说明行 11px/stone-500 → text-xs/stone-300 + 进度前置 + 补「还差 C 经验」（钳 0）（纯客户端；服务端零改动）
    ('r215', os.path.join(HERE, 'localtest', 'yl_r215_ext.py')),  # R-211 签到「补签卡」客户端半边：新增 makeupDay(day) 调 POST /activity/checkin/makeup；漏签日格 div→button（title 显价、点即补签、字符 ✗→补）；脚注**删掉已不成立的「漏签不补」**并新增补签卡说明行（现价/倍率/已补次数）（纯客户端；服务端半边 = SRV_CHAIN 第 89 环 srv_patch_r211.py）
    # ---- 2026-10-09 0.9.45 批（R-213 全站文案 6 处 + R-215 升级经验 ÷2）----
    ('r216', os.path.join(HERE, 'localtest', 'yl_r216_ext.py')),  # R-213 全站文案审计修正 6 处（纯客户端）：① 交易行弹窗「成交收取 10% 手续费」→「挂售成交全额入账、不收取手续费」（服务端全额入账，实为零手续费）；② 奇遇抽奖规则行「消耗当层修为 5%」→ 1%（R-212 只改了服务端常量、漏了文案）；③ 灵田 T5 说明④「照料：每日每田一次」→「每 2 小时一次（每次 +2%，单田当日封顶 +10%）」；④ 天地之髓投喂区间 1-2/3-5/6-10/15-25 → 1/3-4/6-9/16-23（映射表 floor(ge*(.8+X*.4))）；⑤ 师门任务脚注「最多可做 10 条」→ 5 条（棋盘恒 5 条，整体刷新为原地重掷）；⑥ 丹炉「仙品大丹要 9 层造诣」→「九转金丹需 8 层；不死仙丹·天灵根丹·天元丹需 9 层」
    ('r217', os.path.join(HERE, 'localtest', 'yl_r217_ext.py')),  # R-215 整体升级经验 ÷2（客户端半边）：`Cs` 表 7 个境界 `maxExpBase` 全部减半（60000→30000 … 452500000→226250000）；只改该字段，baseAttack/baseMaxHp/K 倍率表一律未动（服务端半边 = SRV_CHAIN 第 90 环 srv_patch_r215.py）
    # ---- 2026-10-09 0.9.46 批（R-217 开局难度调整：收益倍率 + 困难死亡改造 + UI）----
    # ★★ 顺序有讲究：**r220 必须排在 r219 之前**——r220 有一条「冻结·涅槃重生弹窗未动」门禁，
    #    而 r219 的职责正是改那个弹窗。实测：r219→r220 会 fail（两种顺序都试过）；r218 位置无关。
    ('r218', os.path.join(HERE, 'localtest', 'yl_r218_ext.py')),  # R-217 难度收益倍率：难度表 Qr.difficulty
    #   每档新增 expMul/stoneMul（easy 1/1｜normal 1.5/1.5｜hard 2/2）+ 取值器 YlxwDiffMul/YlxwDiffGain；
    #   在 19 个「获取」入账点外包倍率（打坐/历练/秘境/奇遇/回合制/成就/图鉴/宗门/日常/通天塔/灵宠…），
    #   ★ **消耗点一律不乘**（19 项冻结门禁钉死）（纯客户端；服务端离线收益不涉）
    ('r220', os.path.join(HERE, 'localtest', 'yl_r220_ext.py')),  # R-217 难度界面文案：开局界面 + 设置面板
    #   普通/困难两档各 2 处（简单档两条逐字未动，冻结断言）；并**核查**「游戏中无法再更改难度」——
    #   结论：已成立、无后门（写入点仅开局前/开局瞬间；设置面板纯只读 div；**存档导入不带 difficulty**）
    ('r219', os.path.join(HERE, 'localtest', 'yl_r219_ext.py')),  # R-217 困难模式死亡：清档 → 三重惩罚
    # ---- 2026-10-09 0.9.47 批（R-218 历练掉券率下调；纯客户端）----
    ('r221', os.path.join(HERE, 'localtest', 'yl_r221_ext.py')),  # R-218 自动历练掉抽奖券率：
    # ---- 2026-10-09 0.9.48 批（R-219 修炼弹窗 + R-220 效率面板显示；纯客户端）----
    ('r222', os.path.join(HERE, 'localtest', 'yl_r222_ext.py')),  # R-219 修炼弹窗：正文由服务端 bonusText（按等级算，Lv0 恒 0）
    # ---- 2026-10-09 0.9.49 批（R-221 打坐悟道率 1%~4%；纯客户端）----
    ('r223', os.path.join(HERE, 'localtest', 'yl_r223_ext.py')),  # R-221 打坐悟道触发率改为与历练逐字同式：
    #   `0.01+Math.min(0.03,($a(a.titleId,a.unlockedTitles||[]).luck||0)*0.0003)`（1%~4%），旧 `(__r188t?0.05:0.01)` 清零；
    #   顺带把天赋 talent-dao-mind 的 specialAbility.description 改成与基础 effects 一致（★ 该段实测为死数据、不渲染）
    #   ⇒ 改为「修炼成功，经验 +<g.cost>」（与按钮 _pc 同源、数值恒等），仅真升级(bonusPct>0)才追加「攻击 +N%」；
    #   R-220 修炼效率面板两处：显示值 × 难度倍率并注明难度贡献（只改显示口径，不动 total 计算）
    #   券分支 `case"lottery"` 内**原本已有** 10% 闸门 `if(!fs(t,.1,451))` ⇒ 实际每次历练 = (1/37)×0.1 = 0.2703%；
    #   叠加本环 37/600 闸门 ⇒ 总 = 0.1/600 = 0.016667%/次 ⇒ 约 600 次历练 1 张（≈60 分钟）
    #   (1) 装备全掉（equippedItems 清空，背包不动）(2) 掉 40%~50% 属性（attack/defense/spirit/physique/
    #   speed/maxHp，×[0.50,0.60)，下限 1）(3) 掉一个大境界（复用 fe + ad()；**炼气期跳过**并在日志说明）
    #   + hard 弹窗新增「继续游戏」+ onContinue 在 hard 下也传入 ⇒ **不再清档**（纯客户端）
    # ---- 2026-10-10 0.9.52 批（R-232 在线收益难度「服务端权威值优先」；纯客户端）----
    # ★★ 顺序铁律：**r232 必须排在 r218 之后**——r232 的锚点全部落在 r218 的产物上
    #    （① 追加到 r218 的 YlxwDiffGain 声明组尾，② 改写 r218 的 YlxwDiffMul 取值器，
    #     ③ 挂到读档响应解析处；若 r218 未先跑，三处锚点计数=0 ⇒ rc=2 直接失败）。
    ('r232', os.path.join(HERE, 'localtest', 'yl_r232_ext.py')),  # R-232 在线收益难度改用**服务端下发值**为权威
    #   r218 的取值器优先级「入参 → 游戏内 store → localStorage」中，后两者都是**客户端可控**数据
    #   （store 即 localStorage 镜像）⇒ 玩家改一行本地存储即可白拿 ×2 在线收益。
    #   本环在 r218 产物之上**追加**（不改 r218 本体）：
    #     ① 注入 YlxwServerDiff()（读模块级缓存 window.__ylSrvDiff）+ YlxwSrvDiffCapture(j)（从响应顶层提取 ylDifficulty）；
    #     ② 取值器优先级改为「入参 → **服务端下发值** → 游戏内 store → localStorage（降为末位兜底）」；
    #     ③ 在读档接口 fetchSave 的 `const r=await t.json();` 后挂一次 YlxwSrvDiffCapture(r)。
    #   ★ 服务端下发字段名 = `ylDifficulty`（顶层，非存档内 settings.difficulty），由 SRV_CHAIN 第 93 环 srv_patch_r233.py 注入。
    #   ★ 取不到时自动回落旧优先级 ⇒ 与未打本环行为一致（不劣化）；纯客户端，服务端半边 = 第 93 环。
    # ---- 2026-10-10 0.9.53 批（R-238 悟道「禅道·修炼」加成实装；纯客户端）----
    # ★★ 顺序铁律：**r238 必须排在 r228 之后**（D 锚点 = 属性面板明细行的「羁绊」项，
    #    是 r228「明细行改读 bd() 返回值」之后的形态）；与 r232 锚区零交集
    #    （r232 挂读档响应解析处 `const r=await t.json();`，r238 挂 YlxwApi 公共落点
    #     `YLApplyBalance(l, r);`，两处不同）。
    ('r238', os.path.join(HERE, 'localtest', 'yl_r238_ext.py')),  # R-238 悟道「禅道·修炼」加成接入 bd()
    #   排查结论（报告_修炼加成实装排查_20261010.md）：服务端 WUDAO_DAOS.array 的
    #   stat='cultivate'（显示名「修炼」）只在悟道面板展示 bonusText，客户端 bd() 的六源
    #   （心法/天赋/称号/洞府/协同/羁绊）从不读取 ⇒ 面板承诺「修炼 +X%」实际不生效。
    #   本环把它接进 bd()：① 在 YlxwApi 公共落点挂捕获器，从 /wudao 响应的 daos[] 取
    #   cultivate/array 的 bonusPct（百分比数值 → 小数，与面板显示**逐字同源**）；
    #   ② bd() 的 total 相加（权重 K=1.00，与心法同级）；③ 属性面板明细行新增「悟道:+X%」；
    #   ④ bd() 内首屏兜底拉一次 /wudao（次数上限 20，失败自动复位以便登录后重试）。
    #   ★ 不碰离线收益（用户明确「离线收益不用管」）；不改服务端（数值服务端早已下发）；
    #     不碰心法/天赋/称号/洞府/协同/羁绊六源算式与权重（冻结 10 项门禁）。
]


def apply_standalone(bundle_path):
    """对装配产物按序套用 STANDALONE_CLIENT（subprocess --src）。

    退出码语义（两脚本一致）：0=本次补丁成功；3=已是补丁后形态（幂等跳过，不写盘）；
    其余 = 失败。返回错误串列表（空列表 = 全部成功）。
    """
    errs = []
    for tag, path in STANDALONE_CLIENT:
        r = subprocess.run([sys.executable, path, '--src', bundle_path],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        out = (r.stdout or '') + ((('\n[stderr] ' + r.stderr) if r.stderr else ''))
        for ln in out.strip().splitlines():
            print('  [standalone/%s] %s' % (tag, ln))
        if r.returncode not in (0, 3):
            errs.append('[standalone/%s] rc=%d（--src %s）' % (tag, r.returncode, bundle_path))
    return errs

# v28 注入块的禁词表（比 build_v26n 自有 6 块的 BAN_PATTERNS 宽松）：
#   保留真危险项；放行 fetch( / localStorage —— version 模块需读取静态 /yl/CHANGELOG.md
#   并缓存版本号到 localStorage，属静态文件读取，非"绕过鉴权自建 API 调用"。
V28_BAN_PATTERNS = ['iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-']

# ---------------------------------------------------------------- 注入代码
# 注意：这里可以放心写中文，落盘前统一走 zh() 转义。

TOWER_JS = r'''
/* ===== yl-v26n 九天通天塔 (upstream react-xiuxian-game 0.3.8) ===== */
var YlxwTowerTitles = ["守塔傀儡", "天门巡卫", "九霄剑修", "荒古武侍", "太虚灵兽", "星宿战将", "雷劫化身", "幽冥道尊", "通天金甲", "九天玄尊"];
var YlxwTowerNames = ["玄铁傀儡", "破军剑侍", "青阳道长", "赤羽妖修", "裂渊蛮王", "飞霜剑圣", "天魁星君", "万劫雷尊", "乾坤法王", "九霄天帝真影"];

function YlxwTowerFloor(f) {
  var sf = Math.max(1, Math.min(100, Math.floor(f)));
  var isBoss = sf % 10 === 0, isMile = sf % 25 === 0;
  var realm = "炼气期", rf = 1;
  if (sf <= 10) { realm = "炼气期"; rf = 1 + sf * 0.12; }
  else if (sf <= 25) { realm = "筑基期"; rf = 2.5 + (sf - 10) * 0.25; }
  else if (sf <= 45) { realm = "金丹期"; rf = 6.5 + (sf - 25) * 0.45; }
  else if (sf <= 65) { realm = "元婴期"; rf = 16 + (sf - 45) * 1.1; }
  else if (sf <= 80) { realm = "化神期"; rf = 40 + (sf - 65) * 2.8; }
  else if (sf <= 95) { realm = "合道期"; rf = 90 + (sf - 80) * 6.5; }
  else { realm = "长生境"; rf = 200 + (sf - 95) * 20; }
  var ti = Math.min(9, Math.floor((sf - 1) / 10));
  var gTitle = YlxwTowerTitles[ti];
  var gName = isBoss ? "【镇塔道尊】" + YlxwTowerNames[ti] : YlxwTowerNames[ti] + "·分身";
  var bm = isBoss ? 1.4 : 1.0;
  var baseAttack = Math.floor((80 + sf * 28) * rf * bm);
  var baseDefense = Math.floor((50 + sf * 20) * rf * bm);
  var baseHp = Math.floor((500 + sf * 260) * rf * bm * 1.5);
  var baseSpeed = Math.floor(40 + sf * 4.5 + (isBoss ? 30 : 0));
  var baseSpirit = Math.floor(60 + sf * 16 * rf * 0.4);
  var expReward = Math.floor(600 * Math.pow(1.065, sf) + sf * 500);
  var stoneReward = Math.floor(400 * Math.pow(1.055, sf) + sf * 300);
  var reforge = Math.max(1, Math.floor(sf / 10) + (isBoss ? 3 : 1));
  var scrolls = isMile ? Math.max(1, Math.floor(sf / 25)) : (isBoss ? 1 : 0);
  var extra = null;
  if (sf === 100) {
    extra = { id: "tower-divine-token", name: "九天通天令", type: "法宝",
      description: "通关九天通天塔百层极顶后天道所赐的神物，佩戴可大幅增强全属性与悟性。",
      rarity: "仙品", quantity: 1, isEquippable: !0, equipmentSlot: "法宝1",
      effect: { attack: 8888, defense: 6666, hp: 66666, spirit: 3333 } };
  } else if (isBoss) {
    extra = { id: "tower-floor-chest-" + sf, name: sf + "层通天宝匣", type: "法宝",
      description: "九天通天塔第 " + sf + " 层镇守者珍藏的秘宝匣，开启可获得大量修炼资粮。",
      rarity: sf >= 70 ? "仙品" : (sf >= 40 ? "传说" : "稀有"), quantity: 1 };
  }
  return {
    floor: sf, name: "九天通天塔 第 " + sf + " 重天", guardianName: gName, guardianTitle: gTitle, realm: realm,
    baseAttack: baseAttack, baseDefense: baseDefense, baseHp: baseHp, baseSpeed: baseSpeed, baseSpirit: baseSpirit,
    description: isBoss
      ? "此乃通天塔第 " + sf + " 关大圆满重地，镇塔尊者神念亲临，威势滔天！"
      : "九天通天塔第 " + sf + " 层，天地法则凝聚的守塔灵将正驻守于此。",
    firstClearRewards: { exp: expReward, spiritStones: stoneReward, reforgeStones: reforge, comprehensionScrolls: scrolls, items: extra ? [extra] : null }
  };
}

function YlxwTowerReforgeStone(q) {
  return { id: "taixu-reforge-stone", name: "太虚洗炼石", type: "材料",
    description: "蕴含九天太虚法则的奇石，可在洞天万宝炉中重铸与洗炼法宝装备的玄妙词条。",
    quantity: q, rarity: "稀有" };
}
function YlxwTowerScroll(q) {
  return { id: "taixu-comprehension-scroll", name: "太虚悟道卷", type: "材料",
    description: "记载远古神通道法奥义的残卷，可用于自创神通与提升神通领悟境界。",
    quantity: q, rarity: "传说" };
}

/* 落库：Material 按 name 叠加；isEquippable 每次新建实例 */
function YlxwTowerAddItem(inv, item, qty) {
  var n = Math.max(1, qty || item.quantity || 1);
  var a = Array.isArray(inv) ? inv.slice() : [];
  if (item.isEquippable) {
    for (var i = 0; i < n; i++) a.push(Object.assign({}, item, { id: St(), quantity: 1 }));
    return a;
  }
  var k = -1;
  for (var j = 0; j < a.length; j++) { if (a[j] && a[j].name === item.name) { k = j; break; } }
  if (k >= 0) a[k] = Object.assign({}, a[k], { quantity: (a[k].quantity || 1) + n });
  else a.push(Object.assign({}, item, { id: St(), quantity: n }));
  return a;
}

/* 挑战：25 回合制模拟（复刻上游 towerService.challengeTowerFloor） */
function YlxwTowerChallenge(p, tf) {
  var ch = (p.tower && p.tower.highestFloor) || 0;
  var logs = [];
  if (tf > ch + 1) return { result: { success: !1, floor: tf, combatLogs: ["你尚未通关前置层数，无法跨层挑战第 " + tf + " 层！"] }, updatedPlayer: p };
  if (tf > 100) return { result: { success: !1, floor: 100, combatLogs: ["你已登顶九天通天塔最高之巅，万界俯首，无人可阻！"] }, updatedPlayer: p };
  var fc = YlxwTowerFloor(tf);
  var ps = xt(p);
  logs.push("【踏入试炼】你踏入【" + fc.name + "】，狂暴的法则雷云翻涌！");
  logs.push("守塔生灵【" + fc.guardianName + "】（境界：" + fc.realm + "）手持道兵，冷冷凝视着你。");
  var pAtk = ps.attack, pDef = ps.defense, pHp = Math.max(1, p.hp), pSpd = ps.speed;
  var gAtk = fc.baseAttack, gDef = fc.baseDefense, gHp = fc.baseHp, gSpd = fc.baseSpeed;
  function pDmg() { return Math.max(1, Math.floor(pAtk * (1 + Math.random() * 0.2) - gDef * 0.4)); }
  function gDmg() { return Math.max(1, Math.floor(gAtk * (1 + Math.random() * 0.2) - pDef * 0.45)); }
  var round = 1, maxRound = 25, win = !1;
  while (round <= maxRound && pHp > 0 && gHp > 0) {
    if (pSpd >= gSpd) {
      var d1 = pDmg(); gHp = Math.max(0, gHp - d1);
      if (round <= 3 || gHp <= 0) logs.push("第" + round + "回合：你运起无上神通轰出，对其造成 " + d1 + " 点穿透伤害！(守关者气血剩余: " + gHp + ")");
      if (gHp <= 0) { win = !0; break; }
      var d2 = gDmg(); pHp = Math.max(0, pHp - d2);
      if (round <= 3 || pHp <= 0) logs.push("守塔将【" + fc.guardianName + "】法印震荡，对你造成 " + d2 + " 点震慑反震！(自身气血剩余: " + pHp + ")");
      if (pHp <= 0) { win = !1; break; }
    } else {
      var d3 = gDmg(); pHp = Math.max(0, pHp - d3);
      if (round <= 3 || pHp <= 0) logs.push("守塔将【" + fc.guardianName + "】先发制人，重击对你造成 " + d3 + " 点伤害！");
      if (pHp <= 0) { win = !1; break; }
      var d4 = pDmg(); gHp = Math.max(0, gHp - d4);
      if (round <= 3 || gHp <= 0) logs.push("你稳住阵脚，反手祭出道芒重创对手 " + d4 + " 点气血！");
      if (gHp <= 0) { win = !0; break; }
    }
    round++;
  }
  if (pHp > 0 && gHp > 0) {
    var pr = pHp / ps.maxHp, gr = gHp / fc.baseHp;
    win = pr >= gr;
    logs.push(win ? "激战数十回合，你气势如虹，生生将守关者本源神念磨灭！" : "力战力竭，守关傀儡大阵威能愈发澎湃，你遗憾败退。");
  }
  if (win) {
    logs.push("【破关大捷】你成功通关【九天通天塔 第 " + tf + " 层】！");
    var items = [];
    if (fc.firstClearRewards.reforgeStones > 0) items.push(YlxwTowerReforgeStone(fc.firstClearRewards.reforgeStones));
    if (fc.firstClearRewards.comprehensionScrolls > 0) items.push(YlxwTowerScroll(fc.firstClearRewards.comprehensionScrolls));
    if (fc.firstClearRewards.items) items = items.concat(fc.firstClearRewards.items);
    var isFirst = tf > ch, rExp = 0, rStone = 0, grant = [];
    if (isFirst) {
      logs.push("【首次破关】天道赐福降下，你获得本层全部首通嘉奖！");
      rExp = fc.firstClearRewards.exp; rStone = fc.firstClearRewards.spiritStones; grant = items;
    } else {
      logs.push("此层早已踏破，本次仅淬炼心性，未再领取首通嘉奖。");
    }
    var inv = p.inventory || [];
    grant.forEach(function (it) { inv = YlxwTowerAddItem(inv, it, it.quantity || 1); });
    var up = Object.assign({}, p, {
      hp: Math.max(1, pHp), exp: p.exp + rExp, spiritStones: p.spiritStones + rStone, inventory: inv,
      tower: Object.assign({}, p.tower, { highestFloor: Math.max(ch, tf), dailySwept: (p.tower && p.tower.dailySwept) || !1, lastSweepDate: (p.tower && p.tower.lastSweepDate) || "", expGained: (Number(p.tower && p.tower.expGained) || 0) + rExp })
    });
    return { result: { success: !0, floor: tf, combatLogs: logs, rewards: { exp: rExp, spiritStones: rStone, items: grant }, playerHpLoss: Math.max(0, p.hp - pHp) }, updatedPlayer: up };
  }
  logs.push("【挑战落败】你被守塔者的恐怖威压震飞出通天塔，所幸本源未损。");
  var up2 = Object.assign({}, p, { hp: Math.max(1, Math.floor(ps.maxHp * 0.15)) });
  return { result: { success: !1, floor: tf, combatLogs: logs, playerHpLoss: p.hp - up2.hp }, updatedPlayer: up2 };
}

/* 每日扫荡（复刻上游 sweepTower + calculateTowerDailySweep） */
function YlxwTowerSweep(p) {
  var today = new Date().toISOString().split("T")[0];
  var ts = p.tower || { highestFloor: 0, dailySwept: !1, lastSweepDate: "" };
  if (ts.highestFloor <= 0) return { success: !1, message: "你尚未通关任何通天塔关卡，无法进行扫荡！", updatedPlayer: p };
  if (ts.lastSweepDate === today && ts.dailySwept) return { success: !1, message: "今日已完成通天塔扫荡，天道回馈每日仅限一次，请明日再来！", updatedPlayer: p };
  var e = 0, s = 0, f;
  for (f = 1; f <= ts.highestFloor; f++) {
    e += Math.floor(150 * Math.pow(1.045, f) + f * 50);
    s += Math.floor(100 * Math.pow(1.04, f) + f * 35);
  }
  var ref = Math.max(1, Math.floor(ts.highestFloor / 8));
  var items = [YlxwTowerReforgeStone(ref)];
  if (ts.highestFloor >= 50 && Math.random() < 0.6) items.push(YlxwTowerScroll(1));
  var inv = p.inventory || [];
  items.forEach(function (it) { inv = YlxwTowerAddItem(inv, it, it.quantity || 1); });
  return {
    success: !0, message: "【仙光垂落】你一键扫荡了前 " + ts.highestFloor + " 层通天塔，收获颇丰！",
    updatedPlayer: Object.assign({}, p, { exp: p.exp + e, spiritStones: p.spiritStones + s, inventory: inv,
      tower: Object.assign({}, ts, { dailySwept: !0, lastSweepDate: today, expGained: (Number(ts.expGained) || 0) + e }) }),
    rewards: { exp: e, spiritStones: s, items: items }
  };
}

/* UI：仙务枢纽「通天塔」页（结构参照上游 TowerModal） */
function YlxwTTower() {
  var p = Be(function (s) { return s.player; });
  var st = O.useState(0), sr = st[0], setSr = st[1];
  var lg = O.useState([]), logs = lg[0], setLogs = lg[1];
  var bs = O.useState(!1), busy = bs[0], setBusy = bs[1];
  if (!p) return e.jsx(YlxwEmpty, { children: "尚未进入游戏，无法登塔。" });
  var hi = (p.tower && p.tower.highestFloor) || 0;
  var next = Math.min(100, hi + 1);
  var sel = sr > 0 ? Math.min(100, sr) : next;
  var today = new Date().toISOString().split("T")[0];
  var swept = !!(p.tower && p.tower.lastSweepDate === today && p.tower.dailySwept);
  var cfg = YlxwTowerFloor(sel);
  var ps = xt(p);
  var cleared = sel <= hi;
  var isNext = sel === next && sel > hi;
  var rew = cfg.firstClearRewards;
  function doSweep() {
    var cur = Be.getState().player; if (!cur) return;
    var r = YlxwTowerSweep(cur);
    if (!r.success) { Be.getState().addLog(r.message, "normal"); setLogs([r.message]); return; }
    var up = r.updatedPlayer;
    Be.getState().setPlayer(Object.assign({}, cur, { exp: up.exp, spiritStones: up.spiritStones, inventory: up.inventory, tower: up.tower }));
    Be.getState().addLog(r.message, "special");
    Be.getState().addLog("【扫荡收获】获得修为 +" + r.rewards.exp + "，灵石 +" + r.rewards.spiritStones + "，珍稀物品 x" + r.rewards.items.length, "gain");
    setLogs([r.message, "【扫荡收获】修为 +" + r.rewards.exp + "，灵石 +" + r.rewards.spiritStones + "，珍稀物品 x" + r.rewards.items.length]);
  }
  function doFight() {
    var cur = Be.getState().player; if (!cur) return;
    if (cur.hp <= 50) { Be.getState().addLog("你气血极度亏空，强行闯关恐有性命之忧，请先疗伤或打坐！", "danger"); return; }
    setBusy(!0);
    var r = YlxwTowerChallenge(cur, sel);
    var up = r.updatedPlayer;
    Be.getState().setPlayer(Object.assign({}, cur, { hp: up.hp, exp: up.exp, spiritStones: up.spiritStones, inventory: up.inventory, tower: up.tower }));
    setLogs(r.result.combatLogs);
    if (r.result.success) {
      Be.getState().addLog("【破关大捷】你成功登上了九天通天塔第 " + sel + " 层！", "special");
      if (sel < 100) setSr(sel + 1);
    } else {
      Be.getState().addLog("【挑战惜败】第 " + sel + " 层守塔灵阵威能磅礴，你不得不退回休整。", "danger");
    }
    setBusy(!1);
  }
  var guardData = { 气血: cfg.baseHp, 攻击: cfg.baseAttack, 防御: cfg.baseDefense, 速度: cfg.baseSpeed, 神识: cfg.baseSpirit };
  var rewData = {
    修为: rew.exp, 灵石: rew.spiritStones, 太虚洗炼石: rew.reforgeStones,
    太虚悟道卷: rew.comprehensionScrolls || 0,
    秘宝: (rew.items && rew.items.length) ? rew.items.map(function (it) { return it.name; }).join("、") : "无"
  };
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: "历史最高 第 " + hi + " 层 / 100" }), children: "九天通天塔" }),
    e.jsx(YlxwRow, { children: e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
      e.jsxs("span", { children: ["第 " + sel + " 重天 · " + cfg.realm + (cleared ? " · 已通关" : (isNext ? " · 挑战目标" : " · 未解锁"))] }),
      e.jsxs("span", { className: "flex items-center gap-1.5", children: [
        e.jsx(YlxwBtn, { tone: "ghost", disabled: sel <= 1, onClick: function () { setSr(Math.max(1, sel - 1)); }, children: "上一重" }),
        e.jsx(YlxwBtn, { tone: "ghost", disabled: sel >= 100, onClick: function () { setSr(Math.min(100, sel + 1)); }, children: "下一重" }),
        e.jsx(YlxwBtn, { tone: "ghost", onClick: function () { setSr(0); }, children: "回待挑战层" })
      ] })
    ] }) }),
    e.jsxs(YlxwRow, { children: [
      e.jsx("div", { className: "text-xs text-stone-400 mb-1.5", children: "守关者：" + cfg.guardianName + "（" + cfg.guardianTitle + "）" }),
      e.jsx(YlxwKv, { data: guardData })
    ] }),
    e.jsxs(YlxwRow, { children: [
      e.jsx("div", { className: "text-xs text-stone-400 mb-1.5", children: "首通破关奖励" }),
      e.jsx(YlxwKv, { data: rewData })
    ] }),
    e.jsxs(YlxwRow, { children: [
      e.jsxs("div", { className: "text-xs text-stone-400", children: ["我方战力：攻击 " + ps.attack + " · 防御 " + ps.defense + " · 气血上限 " + ps.maxHp + " · 速度 " + ps.speed] }),
      e.jsxs("div", { className: "text-[11px] text-stone-500 mt-1", children: ["当前气血 " + p.hp + " / " + ps.maxHp + "（低于 50 无法挑战）"] })
    ] }),
    e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap pt-1", children: [
      e.jsx(YlxwBtn, { tone: "ghost", disabled: hi <= 0 || swept, onClick: doSweep, children: swept ? "今日已扫荡" : "每日一键扫荡" }),
      e.jsx(YlxwBtn, { disabled: busy || sel > next, onClick: doFight, children: busy ? "激战演算中…" : ((cleared && !isNext) ? "复战 第 " + sel + " 重天" : "挑战 第 " + sel + " 重天") })
    ] }),
    logs.length ? e.jsx(YlxwRow, { children: e.jsx("div", { className: "max-h-40 overflow-y-auto font-mono text-[11px] space-y-0.5 text-stone-300", children: logs.map(function (L, i) { return e.jsx("div", { children: L }, i); }) }) }) : null
  ] });
}

YLXW_ICONS.tower = "M12 2l3 3H9zM9 5v3h6V5M7 21h10M8 8v13M16 8v13M9 12h6M9 16h6";
YLXW_COMP.tower = YlxwTTower;
YLXW_TABS.push({ key: "tower", label: "通天塔", group: 1 });
'''

# ================================================================ 灵兽远征
# 上游：constants/petExpedition.ts + services/petExpeditionService.ts
# 适配：
#   1) 上游草药「凝血草」我方物品池不存在（会静默丢奖）→ 替换为「血参」（我方草药）
#   2) 灵石奖励过 YLRF(player)（我方 v26m 既定规则：非挂机玩法灵石按境界缩放）
#   3) 丹药类奖励从 Ct 池取真实定义（保留 effect/permanentEffect，可正常服用）
#   4) UI 用仙务枢纽展示组件；洞府等级决定队伍槽位（≥3→2 / ≥6→3 / ≥9→4）

EXP_JS = r'''
/* ===== yl-v26n 灵兽远征 (upstream react-xiuxian-game 0.3.8) ===== */
var YlxwExpLocations = [
  { id: "ten-thousand-mountains", name: "十万大山外围", minPetLevel: 1, durationMs: 1800000, durationLabel: "30分钟",
    dangerLevel: "普通", description: "古木参天，灵禽栖息。适合初出茅庐的灵兽漫游采撷草木与灵矿。",
    lootPreview: "大量灵石、聚灵草/血参、强化石、灵兽历练心得" },
  { id: "east-sea-dragon-abyss", name: "东海潜龙深渊", minPetLevel: 15, durationMs: 7200000, durationLabel: "2小时",
    dangerLevel: "危险", description: "海眼深邃，暗礁潜龙。灵兽可下潜探索远古沉船与深海秘矿。",
    lootPreview: "海量灵石、龙鳞果/紫猴花、太虚洗炼石、高阶妖丹" },
  { id: "meteor-forbidden-zone", name: "太虚陨星禁地", minPetLevel: 30, durationMs: 14400000, durationLabel: "4小时",
    dangerLevel: "绝凶", description: "虚空裂隙中天火流坠，危机四伏，唯有通灵道行的灵兽方能踏足。",
    lootPreview: "磅礴灵石、太虚洗炼石x2~4、九转金丹/天元丹、天外陨铁/万年灵乳" }
];

/* 草药/材料兜底定义（我方物品池里存在同名物品，按 name 可与炼丹配方匹配） */
var YlxwExpHerbs = {
  "聚灵草": { type: "草药", rarity: "稀有", description: "蕴含浓郁灵气的灵草，炼丹常用材料。" },
  "血参": { type: "草药", rarity: "稀有", description: "色如鲜血的灵参，大补气血，炼丹常用材料。" },
  "紫猴花": { type: "草药", rarity: "稀有", description: "炼制洗髓丹的材料，生长在悬崖峭壁。" },
  "龙鳞果": { type: "草药", rarity: "稀有", description: "龙族栖息地生长的灵果，蕴含龙族血脉之力。" },
  "高阶妖丹": { type: "材料", rarity: "稀有", description: "强大妖兽的内丹，灵气逼人。" },
  "天外陨铁": { type: "材料", rarity: "传说", description: "来自天外的神秘金属，炼制仙器的材料。" },
  "万年灵乳": { type: "材料", rarity: "传说", description: "万年灵脉中凝聚的精华，炼制仙丹的珍贵材料。" },
  "强化石": { type: "材料", rarity: "稀有", description: "提高装备强化成功率的珍贵材料，每颗可提高 10% 成功率。" }
};

/* 取物品定义：丹药优先走 Ct 池（保留 effect），其余走兜底表 */
function YlxwExpItem(name, qty) {
  var n = Math.max(1, qty || 1), d = null;
  try { if (Ct && Ct[name]) d = Ct[name]; } catch (e) { d = null; }
  if (d) return Object.assign({}, d, { id: St(), quantity: n });
  var h = YlxwExpHerbs[name];
  if (h) return Object.assign({ id: St(), name: name, quantity: n }, h);
  return { id: St(), name: name, type: "材料", description: "灵兽远征带回的珍稀物品。", quantity: n, rarity: "稀有" };
}

function YlxwExpSlots(lv) { return lv >= 9 ? 4 : (lv >= 6 ? 3 : (lv >= 3 ? 2 : 1)); }

/* 奖励生成（复刻上游 3 地点公式；灵石过 YLRF 境界缩放） */
function YlxwExpGenRewards(locId, petLevel, player) {
  var r = Math.random, items = [], stones = 0, exp = 0, rf = 1;
  try { rf = YLRF(player); } catch (e) { rf = 1; }
  if (locId === "ten-thousand-mountains") {
    stones = Math.floor(800 + r() * 800 + petLevel * 50);
    exp = Math.floor(1200 + r() * 1000 + petLevel * 80);
    items.push(YlxwExpItem(r() < 0.5 ? "聚灵草" : "血参", Math.floor(r() * 3) + 1));
    if (r() < 0.6) items.push(YlxwExpItem("强化石", 1));
  } else if (locId === "east-sea-dragon-abyss") {
    stones = Math.floor(3500 + r() * 2500 + petLevel * 100);
    exp = Math.floor(6000 + r() * 4000 + petLevel * 150);
    items.push(YlxwTowerReforgeStone(r() < 0.35 ? 2 : 1));
    items.push(YlxwExpItem(r() < 0.5 ? "龙鳞果" : "紫猴花", Math.floor(r() * 2) + 1));
    if (r() < 0.5) items.push(YlxwExpItem("高阶妖丹", 1));
  } else {
    stones = Math.floor(10000 + r() * 8000 + petLevel * 200);
    exp = Math.floor(20000 + r() * 15000 + petLevel * 300);
    items.push(YlxwTowerReforgeStone(Math.floor(r() * 3) + 2));
    var rare = ["天外陨铁", "万年灵乳", "九转金丹", "天元丹"];
    items.push(YlxwExpItem(rare[Math.floor(r() * rare.length)], 1));
  }
  return { spiritStones: Math.floor(stones * rf), exp: exp, items: items };
}

function YlxwExpStart(p, petId, locId) {
  var g = p.grotto, i;
  if (!g || g.level < 1) return { success: !1, message: "尚未开辟洞府，无法开启灵兽苑远征！", updatedPlayer: p };
  var pet = null;
  for (i = 0; i < (p.pets || []).length; i++) { if (p.pets[i].id === petId) { pet = p.pets[i]; break; } }
  if (!pet) return { success: !1, message: "未找到指定灵兽！", updatedPlayer: p };
  var loc = null;
  for (i = 0; i < YlxwExpLocations.length; i++) { if (YlxwExpLocations[i].id === locId) { loc = YlxwExpLocations[i]; break; } }
  if (!loc) return { success: !1, message: "未知的探索地点！", updatedPlayer: p };
  if ((pet.level || 1) < loc.minPetLevel) {
    return { success: !1, message: "【" + pet.name + "】境界未稳（当前等级 " + (pet.level || 1) + "），前往【" + loc.name + "】需达到 Lv." + loc.minPetLevel + "！", updatedPlayer: p };
  }
  var cur = g.petExpeditions || [], slots = YlxwExpSlots(g.level), active = 0, k;
  for (k = 0; k < cur.length; k++) { if (cur[k].status !== "claimed") active++; }
  if (active >= slots) return { success: !1, message: "灵兽远征队伍已满（当前最多 " + slots + " 队），升级洞府可解锁更多队伍！", updatedPlayer: p };
  for (k = 0; k < cur.length; k++) {
    if (cur[k].petId === petId && cur[k].status !== "claimed") {
      return { success: !1, message: "【" + pet.name + "】正在外出远征，无法重复派遣！", updatedPlayer: p };
    }
  }
  var now = Date.now();
  var ne = { id: St(), petId: pet.id, petName: pet.name, locationId: loc.id, locationName: loc.name,
    startTime: now, duration: loc.durationMs, endTime: now + loc.durationMs, status: "exploring" };
  return { success: !0, message: "【灵兽远征】你派遣【" + pet.name + "】前往【" + loc.name + "】踏上寻珍之旅！",
    updatedPlayer: Object.assign({}, p, { grotto: Object.assign({}, g, { petExpeditions: cur.concat([ne]) }) }) };
}

/* 到期结算：exploring → completed + 生成奖励 */
function YlxwExpTick(p) {
  var g = p.grotto;
  if (!g || !g.petExpeditions || !g.petExpeditions.length) return p;
  var now = Date.now(), ch = !1;
  var list = g.petExpeditions.map(function (e) {
    if (e.status === "exploring" && now >= e.endTime) {
      ch = !0;
      var pet = null, i;
      for (i = 0; i < (p.pets || []).length; i++) { if (p.pets[i].id === e.petId) { pet = p.pets[i]; break; } }
      return Object.assign({}, e, { status: "completed", rewards: YlxwExpGenRewards(e.locationId, (pet && pet.level) || 1, p) });
    }
    return e;
  });
  if (!ch) return p;
  return Object.assign({}, p, { grotto: Object.assign({}, g, { petExpeditions: list }) });
}

function YlxwExpClaim(p, id) {
  var g = p.grotto, i;
  if (!g || !g.petExpeditions) return { success: !1, message: "远征记录不存在！", updatedPlayer: p };
  var t = null;
  for (i = 0; i < g.petExpeditions.length; i++) { if (g.petExpeditions[i].id === id) { t = g.petExpeditions[i]; break; } }
  if (!t) return { success: !1, message: "远征记录不存在！", updatedPlayer: p };
  if (t.status !== "completed" || !t.rewards) return { success: !1, message: "远征尚未凯旋，暂无法领取！", updatedPlayer: p };
  var rw = t.rewards, inv = p.inventory || [];
  (rw.items || []).forEach(function (it) { inv = YlxwTowerAddItem(inv, it, it.quantity || 1); });
  var rest = g.petExpeditions.filter(function (e) { return e.id !== id; });
  var summary = (rw.items || []).length
    ? "、获得珍宝：" + rw.items.map(function (it) { return it.name + "x" + (it.quantity || 1); }).join("，") : "";
  return {
    success: !0,
    message: "【远征凯旋】灵兽【" + t.petName + "】自【" + t.locationName + "】满载而归！获得灵石 +" + rw.spiritStones + "，历练修为 +" + rw.exp + summary + "。",
    updatedPlayer: Object.assign({}, p, {
      spiritStones: p.spiritStones + rw.spiritStones, exp: p.exp + rw.exp, inventory: inv,
      grotto: Object.assign({}, g, { petExpeditions: rest, expeditionExpGained: (Number(g.expeditionExpGained) || 0) + rw.exp })
    })
  };
}

function YlxwExpRecall(p, id) {
  var g = p.grotto, i;
  if (!g || !g.petExpeditions) return { success: !1, message: "远征记录不存在！", updatedPlayer: p };
  var t = null;
  for (i = 0; i < g.petExpeditions.length; i++) { if (g.petExpeditions[i].id === id) { t = g.petExpeditions[i]; break; } }
  if (!t) return { success: !1, message: "远征记录不存在！", updatedPlayer: p };
  var rest = g.petExpeditions.filter(function (e) { return e.id !== id; });
  return { success: !0, message: "【灵兽归苑】已提前传音召回【" + t.petName + "】。",
    updatedPlayer: Object.assign({}, p, { grotto: Object.assign({}, g, { petExpeditions: rest }) }) };
}

function YlxwFmtDur(ms) {
  if (ms <= 0) return "已完成";
  var s = Math.floor(ms / 1000), m = Math.floor(s / 60), h = Math.floor(m / 60);
  if (h > 0) return h + "时" + (m % 60) + "分";
  if (m > 0) return m + "分" + (s % 60) + "秒";
  return s + "秒";
}

/* UI：仙务枢纽「灵兽远征」页 */
function YlxwTPetExp() {
  var p = Be(function (s) { return s.player; });
  var st = O.useState(""), selRaw = st[0], setSel = st[1];
  var tk = O.useState(0), tick = tk[0], setTick = tk[1];
  O.useEffect(function () {
    var id = setInterval(function () { setTick(function (x) { return x + 1; }); }, 1000);
    return function () { clearInterval(id); };
  }, []);
  O.useEffect(function () {
    var cur = Be.getState().player;
    if (!cur) return;
    var up = YlxwExpTick(cur);
    if (up !== cur) Be.getState().setPlayer(up);
  }, [tick]);
  if (!p) return e.jsx(YlxwEmpty, { children: "尚未进入游戏，无法开启远征。" });
  var g = p.grotto || { level: 0 };
  var pets = p.pets || [];
  var selPet = selRaw || ((pets[0] && pets[0].id) || "");
  var slots = YlxwExpSlots(g.level);
  var list = g.petExpeditions || [];
  var active = list.filter(function (x) { return x.status !== "claimed"; }).length;
  var now = Date.now();
  var pet = null, i;
  for (i = 0; i < pets.length; i++) { if (pets[i].id === selPet) { pet = pets[i]; break; } }
  function doStart(locId) {
    var cp = Be.getState().player; if (!cp) return;
    var pid = selPet || ((cp.pets && cp.pets[0] && cp.pets[0].id) || "");
    if (!pid) { Be.getState().addLog("你还没有灵兽，无法派遣远征。", "danger"); return; }
    var r = YlxwExpStart(cp, pid, locId);
    Be.getState().addLog(r.message, r.success ? "special" : "normal");
    if (r.success) Be.getState().setPlayer(r.updatedPlayer);
  }
  function doClaim(id) {
    var cp = Be.getState().player; if (!cp) return;
    var up = YlxwExpTick(cp);
    var r = YlxwExpClaim(up, id);
    Be.getState().addLog(r.message, r.success ? "special" : "normal");
    if (r.success) Be.getState().setPlayer(r.updatedPlayer);
  }
  function doRecall(id) {
    var cp = Be.getState().player; if (!cp) return;
    var r = YlxwExpRecall(cp, id);
    Be.getState().addLog(r.message, "normal");
    if (r.success) Be.getState().setPlayer(r.updatedPlayer);
  }
  var head = "洞府 Lv." + g.level + " · 队伍 " + active + "/" + slots + " · 灵兽 " + pets.length;
  var locRows = YlxwExpLocations.map(function (L) {
    var ok = pet ? (pet.level || 1) >= L.minPetLevel : !1;
    return e.jsxs(YlxwRow, { children: [
      e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsxs("span", { children: [L.name + " · " + L.dangerLevel + " · " + L.durationLabel + " · 需 Lv." + L.minPetLevel] }),
        e.jsx(YlxwBtn, { disabled: !ok || active >= slots, onClick: function () { doStart(L.id); }, children: "派遣" })
      ] }),
      e.jsx("div", { className: "text-[11px] text-stone-500 mt-1", children: L.description }),
      e.jsx("div", { className: "text-[11px] text-amber-400/80 mt-0.5", children: "掉落预览：" + L.lootPreview })
    ] }, L.id);
  });
  var runRows = list.map(function (x) {
    var left = x.endTime - now, done = x.status === "completed" || left <= 0;
    return e.jsxs(YlxwRow, { children: [
      e.jsxs("div", { className: "flex items-center justify-between gap-2 flex-wrap", children: [
        e.jsxs("span", { children: [x.petName + " → " + x.locationName + " · " + (done ? "已凯旋" : "剩余 " + YlxwFmtDur(left))] }),
        e.jsxs("span", { className: "flex items-center gap-1.5", children: [
          done ? e.jsx(YlxwBtn, { onClick: function () { doClaim(x.id); }, children: "领取战果" })
               : e.jsx(YlxwBtn, { tone: "ghost", onClick: function () { doRecall(x.id); }, children: "召回" })
        ] })
      ] }),
      x.rewards ? e.jsx("div", { className: "text-[11px] text-stone-400 mt-1", children: "预计战果：灵石 +" + x.rewards.spiritStones + "，修为 +" + x.rewards.exp + "，物品 x" + ((x.rewards.items || []).length) }) : null
    ] }, x.id);
  });
  return e.jsxs(YlxwPanel, { children: [
    e.jsx(YlxwTitle, { extra: e.jsx("span", { className: "text-xs text-stone-400", children: head }), children: "灵兽远征" }),
    pets.length ? e.jsxs(YlxwRow, { children: [
      e.jsx("div", { className: "text-xs text-stone-400 mb-1.5", children: "选择出战的灵兽" }),
      e.jsx("select", {
        value: selPet,
        onChange: function (ev) { setSel(ev.target.value); },
        className: "w-full bg-ink-800 border border-stone-600 rounded px-2 py-1.5 text-sm text-stone-100",
        children: pets.map(function (x) {
          return e.jsx("option", { value: x.id, children: x.name + " Lv." + (x.level || 1) + "（" + (x.species || "灵兽") + "）" }, x.id);
        })
      })
    ] }) : e.jsx(YlxwEmpty, { children: "你还没有灵兽，先去灵宠界面捕捉或孵化吧。" }),
    g.level < 1 ? e.jsx(YlxwEmpty, { children: "尚未开辟洞府，无法开启灵兽远征。" }) : null,
    g.level >= 1 ? e.jsx("div", { className: "text-xs text-amber-300 pt-1", children: "可派遣地点" }) : null,
    g.level >= 1 ? e.jsx(e.Fragment, { children: locRows }) : null,
    runRows.length ? e.jsx("div", { className: "text-xs text-amber-300 pt-1", children: "远征进行中" }) : null,
    runRows.length ? e.jsx(e.Fragment, { children: runRows }) : null
  ] });
}

YLXW_ICONS.expedition = "M6 13a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM10 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM14 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM18 13a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM12 21c-3 0-5-2-5-4s2-3 5-3 5 1 5 3-2 4-5 4z";
YLXW_COMP.expedition = YlxwTPetExp;
YLXW_TABS.push({ key: "expedition", label: "灵兽远征", group: 1 });
'''

DRAWER_ITEM = '{icon:YlxwMk("tower"),label:"通天塔",onClick:()=>YlxwOpen("tower"),color:"text-amber-300"},'
DRAWER_ITEM_EXP = '{icon:YlxwMk("expedition"),label:"灵兽远征",onClick:()=>YlxwOpen("expedition"),color:"text-amber-300"},'


BAN_PATTERNS = ['fetch(', 'localStorage', 'sessionStorage', 'auth_token',
                '/yl/api', 'iframe', 'postMessage', 'X-YL-', 'XMLHttpRequest']



def _js_syntax_check(src):
    """★★ 独立的 JS 语法门禁：产物必须是合法 JS，否则拒绝落盘。
    这一道**任何字面门禁都替代不了** —— 字面门禁只能证明
    「我改了我想改的」，不能证明「产物还是合法 JS」。
    """
    import subprocess, tempfile, os as _os
    # ★ 2026-10-08 修：原为写死 `…\node\versions\22.22.2-3\node.exe`，
    #   但本机 node 已随工具升级为 22.22.2-6（旧目录被删）⇒ 写死路径会 FileNotFoundError。
    #   改为：YL_NODE 环境变量 → versions 目录下**按名排序取最新** → 兜底裸 `node`。
    _nroot = r'C:\Users\<USER>\.workbuddy-ai\binaries\node\versions'
    _ncands = []
    if _os.path.isdir(_nroot):
        _ncands = sorted(_os.path.join(_nroot, _d, 'node.exe') for _d in _os.listdir(_nroot))
        _ncands = [_c for _c in _ncands if _os.path.isfile(_c)]
    node = _os.environ.get('YL_NODE') or (_ncands[-1] if _ncands else 'node')
    if not _os.path.exists(node):
        print('[WARN] 找不到 node，跳过 JS 语法门禁：%s' % node)
        return
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with _os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(src)
        r = subprocess.run([node, '--check', tmp], capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise SystemExit('\n\u2605\u2605 JS 语法门禁未过（产物不是合法 JS，已拒绝落盘）：\n'
                             + (r.stderr or '')[-1500:])
        print('  [OK] JS 语法门禁（node --check 通过）')
    finally:
        try:
            _os.unlink(tmp)
        except Exception:
            pass


def build(base_text):
    import re
    from yl_patch import PatchError

    tower_block = zh(TOWER_JS)
    exp_block = zh(EXP_JS)
    core_block = zh(CORE_JS)
    ref_block = zh(REFORGE_JS)
    spell_block = zh(SPELL_JS)
    payout_block = zh(PAYOUT_JS)

    # 注入块硬断言（不通过 gates，直接拒绝落盘）
    for label, blk in (('tower', tower_block), ('expedition', exp_block),
                       ('core', core_block), ('reforge', ref_block), ('spell', spell_block),
                       ('payout', payout_block)):
        bad = re.findall(r'[^\x00-\x7f]', blk)
        if bad:
            raise PatchError('[%s] 注入块仍含非 ASCII 字符: %r' % (label, bad[:10]))
        for pat in BAN_PATTERNS:
            if pat in blk:
                raise PatchError('[%s] 注入块含禁用模式: %s' % (label, pat))

    p = Patcher(base_text, label='v26n')

    # 0) 整体改名：云灵修仙传 → 摸鱼修仙传（只动 base 既有字面中文，先长后短）
    for name, a, r, expect in RENAME_PATCHES:
        p.replace(name, a, r, expect=expect, note='改名·字面量替换')

    # 1) 主注入块：放在 YlxwPanelModal 之前（此时 YLXW_COMP / YLXW_TABS / YLXW_ICONS /
    #    YlxwIc / YlxwPanel 系列 / xt / St / Ct / YLRF 均已定义）
    p.insert_before(
        'core-block',
        'function YlxwPanelModal(p) {',
        core_block + '\n' + tower_block + '\n' + exp_block + '\n' + ref_block + '\n'
        + spell_block + '\n' + payout_block + '\n',
        note='洗炼/神通 共用层 + 通天塔 + 灵兽远征 + 万宝洗炼 + 自创神通 + 交易行货款'
    )

    # 1b) 交易行货款 API：插在交易行 API 函数 Fk 之后（Nd/jo/ln 同作用域，复用统一鉴权头）
    p.insert_before(
        'market-payouts-api',
        PAYOUT_API_ANCHOR,
        zh(PAYOUT_API_JS) + '\n',
        note='交易行货款查询/领取 API（V27 卖家收益，复用 Nd/jo 鉴权）'
    )

    # 2) 抽屉入口（同一锚点多次 append，锚点本身保留）
    anchor = '{icon:YlxwMk("guide"),label:"仙途指引",onClick:()=>YlxwOpen("guide"),color:"text-amber-300"},'
    p.append_to('drawer-entry-tower', anchor, DRAWER_ITEM, note='抽屉加通天塔入口')
    p.append_to('drawer-entry-exp', anchor, DRAWER_ITEM_EXP, note='抽屉加灵兽远征入口')
    p.append_to('drawer-entry-reforge', anchor, DRAWER_ITEM_REF, note='抽屉加万宝洗炼入口')
    p.append_to('drawer-entry-spell', anchor, DRAWER_ITEM_SPELL, note='抽屉加自创神通入口')
    p.append_to('drawer-entry-payout', anchor, DRAWER_ITEM_PAYOUT, note='抽屉加交易行货款入口')

    # 3) 战斗 / 属性 消费补丁（锚点各自唯一，逐条断言）
    for name, a, r, note in BATTLE_PATCHES:
        p.replace(name, a, r, note=note)

    # 3b) 出售页展示金额对齐实际入账（v27；helper 锚在 YLRF 定义之后，保证同作用域）
    p.insert_after(
        'sellui-helper',
        SELL_UI_HELPER_ANCHOR,
        '\n' + SELL_UI_HELPER_JS + '\n',
        note='注入 YLSellCredit（复用与实际入账同一条公式）'
    )
    for name, a, r, expect, note in SELL_UI_PATCHES:
        p.replace(name, a, r, expect=expect, note=note)

    # 3c) v28 模块：各自 zh() 自己的 INJECT_JS 并自行插入锚点；此处只做安全自检 + 汇总门禁
    v28_gates = []
    for _name, _apply in V28_MODULES:
        _mod = sys.modules[_apply.__module__]
        _blk = zh(getattr(_mod, 'INJECT_JS', ''))
        _bad = re.findall(r'[^\x00-\x7f]', _blk)
        if _bad:
            raise PatchError('[v28/%s] 注入块 zh() 后仍含非 ASCII: %r' % (_name, _bad[:10]))
        for _pat in V28_BAN_PATTERNS:
            if _pat in _blk:
                raise PatchError('[v28/%s] 注入块含禁用模式: %s' % (_name, _pat))
        # 少数模块（numbal）不自行插入 INJECT_JS，由 build 侧按约定插入
        _anchor = getattr(_mod, 'INJECT_BEFORE_ANCHOR', None)
        if _anchor:
            p.insert_before(getattr(_mod, 'INJECT_BLOCK_ID', 'v28-' + _name + '-block'),
                            _anchor, _blk + '\n',
                            note='v28/%s 注入块（模块未自行插入，build 侧补插）' % _name)
        _g = _apply(p, {'zh': zh, 'base_text': base_text})
        if _g is None:
            raise PatchError('[v28/%s] apply() 必须返回 gates 列表' % _name)
        for _t in _g:
            # 5 元 = (name, needle, expect, cmp, note)；可选第 6 元 = within 限域切片
            # （2026-09-29 BLK-A：限域断言需要，见 yl_patch.Gates.check）
            assert len(_t) in (5, 6), '[v28/%s] gate 元组必须 5 元（可选第 6 元 within）: %r' % (_name, _t)
        v28_gates.extend(_g)

    _js_syntax_check(p.text)      # ★ 独立语法门禁（见函数注释）

    out = p.text

    # ---------------- 门禁 ----------------
    towers = zh('九天通天塔')
    exps = zh('灵兽远征')
    gates = [
        ('YLXW_COMP.tower 挂载',      'YLXW_COMP.tower = YlxwTTower',           1, '==', ''),
        ('YlxwTTower 定义',            'function YlxwTTower(',                  1, '==', ''),
        ('YLXW_TABS.push tower',       'YLXW_TABS.push({ key: "tower"',         1, '==', ''),
        ('YLXW_ICONS.tower',           'YLXW_ICONS.tower =',                    1, '==', ''),
        ('抽屉入口 tower',              'YlxwOpen("tower")',                     1, '==', ''),
        ('通天塔标题',                  towers,                                  1, '>=', ''),
        ('YlxwTowerFloor 定义',        'function YlxwTowerFloor(',              1, '==', ''),
        ('YlxwTowerChallenge 定义',    'function YlxwTowerChallenge(',          1, '==', ''),
        ('YlxwTowerSweep 定义',        'function YlxwTowerSweep(',              1, '==', ''),
        ('YlxwTowerAddItem 定义',      'function YlxwTowerAddItem(',            1, '==', ''),
        # ---- 灵兽远征 ----
        ('YLXW_COMP.expedition 挂载',  'YLXW_COMP.expedition = YlxwTPetExp',    1, '==', ''),
        ('YlxwTPetExp 定义',           'function YlxwTPetExp(',                 1, '==', ''),
        ('YLXW_TABS.push expedition',  'YLXW_TABS.push({ key: "expedition"',    1, '==', ''),
        ('YLXW_ICONS.expedition',      'YLXW_ICONS.expedition =',               1, '==', ''),
        ('抽屉入口 expedition',         'YlxwOpen("expedition")',                1, '==', ''),
        ('灵兽远征标题',                exps,                                    1, '>=', ''),
        ('地点·十万大山',                'ten-thousand-mountains',                1, '>=', ''),
        ('地点·东海潜龙',                'east-sea-dragon-abyss',                 1, '>=', ''),
        ('地点·太虚陨星',                'meteor-forbidden-zone',                 1, '>=', ''),
        ('YlxwExpStart 定义',          'function YlxwExpStart(',                1, '==', ''),
        ('YlxwExpTick 定义',           'function YlxwExpTick(',                 1, '==', ''),
        ('YlxwExpClaim 定义',          'function YlxwExpClaim(',                1, '==', ''),
        ('YlxwExpRecall 定义',         'function YlxwExpRecall(',               1, '==', ''),
        ('凝血草已替换(应为0)',          zh('凝血草'),                             0, '==', '必须为 0'),
        ('灵石过 YLRF 缩放',            'Math.floor(stones * rf)',               1, '==', ''),
        # ---- 万宝洗炼 ----
        ('YLXW_COMP.reforge 挂载',      'YLXW_COMP.reforge = YlxwTReforge',      1, '==', ''),
        ('YlxwTReforge 定义',           'function YlxwTReforge(',                1, '==', ''),
        ('YLXW_TABS.push reforge',      'YLXW_TABS.push({ key: "reforge"',       1, '==', ''),
        ('YLXW_ICONS.reforge',          'YLXW_ICONS.reforge =',                  1, '==', ''),
        ('抽屉入口 reforge',             'YlxwOpen("reforge")',                   1, '==', ''),
        ('万宝洗炼标题',                 zh('万宝洗炼'),                           1, '>=', ''),
        ('7 词条·锋芒',                  zh('锋芒'),                               1, '>=', ''),
        ('7 词条·噬灵',                  zh('噬灵'),                               1, '>=', ''),
        ('YlxwRF_Candidate 定义',       'function YlxwRF_Candidate(',            1, '==', ''),
        ('YlxwRF_Apply 定义',           'function YlxwRF_Apply(',                1, '==', ''),
        ('YlxwRF_ToggleLock 定义',      'function YlxwRF_ToggleLock(',           1, '==', ''),
        ('洗炼石 id 一致',              'taixu-reforge-stone',                   2, '>=', ''),
        # ---- 自创神通 ----
        ('YLXW_COMP.spell 挂载',        'YLXW_COMP.spell = YlxwTSpell',          1, '==', ''),
        ('YlxwTSpell 定义',             'function YlxwTSpell(',                  1, '==', ''),
        ('YLXW_TABS.push spell',        'YLXW_TABS.push({ key: "spell"',         1, '==', ''),
        ('YLXW_ICONS.spell',            'YLXW_ICONS.spell =',                    1, '==', ''),
        ('抽屉入口 spell',               'YlxwOpen("spell")',                     1, '==', ''),
        ('自创神通标题',                 zh('自创神通'),                           1, '>=', ''),
        ('YlxwSP_Fuse 定义',            'function YlxwSP_Fuse(',                 1, '==', ''),
        ('YlxwSP_Upgrade 定义',         'function YlxwSP_Upgrade(',              1, '==', ''),
        ('YlxwSP_CanFuse 定义',         'function YlxwSP_CanFuse(',              1, '==', ''),
        # ---- 交易行货款（V27 卖家收益）----
        ('YLXW_COMP.payout 挂载',       'YLXW_COMP.payout = YlxwTPayout',        1, '==', ''),
        ('YlxwTPayout 定义',            'function YlxwTPayout(',                 1, '==', ''),
        ('YLXW_TABS.push payout',       'YLXW_TABS.push({ key: "payout"',        1, '==', ''),
        ('YLXW_ICONS.payout',           'YLXW_ICONS.payout =',                   1, '==', ''),
        ('抽屉入口 payout',              'YlxwOpen("payout")',                    1, '==', ''),
        ('交易行货款标题',               zh('交易行货款'),                         1, '>=', ''),
        ('货款 API·查询',               'async function YlxwMarketPayouts(',     1, '==', ''),
        ('货款 API·领取',               'async function YlxwMarketClaim(',       1, '==', ''),
        ('货款 API 走 Nd 鉴权',          'Nd(`${ln}/market/payouts`)',            1, '==', ''),
        ('货款 API 挂 window',          'window.YlxwMarketPayouts = YlxwMarketPayouts', 1, '==', ''),
        ('领取按 amount 增量入账',       'next.spiritStones = now + r.amount', 1, '==', 'v28 深测：叠加前须过竞态守卫'),
        ('不采纳服务端绝对余额',         'r.stones == null',                      0, '==', '必须为 0（客户端权威，采纳绝对值会丢本地未同步收益）'),
        ('领取提示独立于刷新',           zh('setNotice("已领取 " + r.amount'),    1, '==', ''),
        ('错误态独立于刷新',             zh('setErr((r && r.error) || "查询失败")'), 1, '==', ''),
        ('注入块未自造 fetch',           'window.YlxwMarketPayouts ? window.YlxwMarketPayouts()', 1, '==', ''),
        ('货款明细行两端对齐',           'flex items-center justify-between gap-2", children: [', 2, '>=', ''),
        # ---- 战斗 / 属性 消费 ----
        ('xt 挂载 YlxwStatExtras',      'typeof YlxwStatExtras==="function"&&YlxwStatExtras(t,r)', 1, '==', ''),
        ('YlxwStatExtras 定义',         'function YlxwStatExtras(',              1, '==', ''),
        ('YlxwBattleBonus 定义',        'function YlxwBattleBonus(',             1, '==', ''),
        ('YlxwSpellBuffs 定义',         'function YlxwSpellBuffs(',              1, '==', ''),
        ('X0 暴击上限 .2 已移除',        'Math.min(.2,F)',                        0, '==', '必须为 0'),
        ('X0 暴击上限 .35 已注入',       'W=Math.max(0,Math.min(.35,F))',         1, '==', ''),
        ('X0 吸血已注入',               'YlxwPB.lifeLeech>0&&(M=Math.min(S,M+Math.floor(X*YlxwPB.lifeLeech)))', 1, '==', ''),
        ('km 吸血已注入',               'w.lifeLeech&&w.lifeLeech>0&&(l.hp=Math.min(l.maxHp', 1, '==', ''),
        ('QS buff 注入已生效',          'm.concat(typeof YlxwSpellBuffs==="function"?YlxwSpellBuffs(t):[])', 1, '==', ''),
        ('km 原 .35 上限未被破坏',      'f=Math.min(.35,Math.max(0,f))',         1, '==', ''),
        # ---- v27 修为计数器（服务端 capExp 放行依据）----
        ('通天塔计数·首通',             'expGained: (Number(p.tower && p.tower.expGained) || 0) + rExp', 1, '==', ''),
        ('通天塔计数·扫荡',             'expGained: (Number(ts.expGained) || 0) + e', 1, '==', ''),
        ('远征计数·领取',               'expeditionExpGained: (Number(g.expeditionExpGained) || 0) + rw.exp', 1, '==', ''),
        ('tower 子对象已保留旧字段',     'tower: Object.assign({}, p.tower, {', 1, '==', ''),
        # ---- 基线完整性 ----
        ('YLXW_TABS 原 23 项仍在',      '{ key: "mail", label:',                 1, '==', ''),
        ('YLXW_COMP 原 23 项仍在',      'stats: YlxwTStats }',                   1, '==', ''),
        ('YlxwPanelModal 未被破坏',     'function YlxwPanelModal(p) {',          1, '==', ''),
        ('存档上报 player 原样',        'body:JSON.stringify({player:',          1, '==', ''),
        ('xt 总属性函数仍在',           'const xt=t=>{',                         1, '==', ''),
        ('St uid 生成器仍在',           'const St=()=>(pg++',                    1, '==', ''),
        ('YLRF 缩放函数仍在',           'function YLRF(j) {',                    1, '==', ''),
        ('Ct 物品池仍在',               'const Ct={',                            1, '==', ''),
    ]
    # 交易行货款：乐观增量竞态守卫（v28 本机深测修复；与信箱一键领取同款 bug 类）
    gates.append(('货款·请求前快照 before', 'var before = Number((Be.getState().player || {}).spiritStones) || 0;', 2, '==', '信箱+货款各一处'))
    gates.append(('货款·响应后竞态守卫',   'if (now === before) {',                                   2, '==', '信箱+货款各一处'))
    gates.append(('货款·增量入账新写法',   'next.spiritStones = now + r.amount;',                     1, '==', ''))
    gates.append(('货款·旧无守卫写法已移除', 'next.spiritStones = (Number(cur.spiritStones) || 0) + r.amount;', 0, '==', '必须为 0'))
    # 出售页展示金额对齐（v27）
    gates.append(('出售页 helper 只注入一次', 'YL_SELLUI_FIX_V27', 2, '==', '起始+结束标记'))
    gates.extend(SELL_UI_GATES)
    # 整体改名门禁（v27）
    gates.extend(RENAME_GATES)
    # v28 模块门禁（saveretry / version / mail / entry / sectgf / char / numbal）
    gates.extend(v28_gates)
    return out, gates


if __name__ == '__main__':
    # ---- stdout 减负（2026-10-01 第 3 批接线，假 FAIL 修复）----
    # 工作流执行器对单条命令 stdout 有 262,144 字节硬帽；本批门禁总数增至 2708，
    # 逐条全量打印 ≈266KB 超帽（上批 2367 条未超）→ 执行器报 WorkflowError，
    # 属调用面问题，门禁本体无恙。故默认丢弃逐条 '[OK]' 行（[FAIL] 行、
    # 门禁头/摘要/落盘信息全保留），退出码与判定逻辑零改动。
    # 需要全量逐条输出时：--verbose 或环境变量 YL_BUILD_VERBOSE=1。
    if ('--verbose' not in sys.argv) and os.environ.get('YL_BUILD_VERBOSE') != '1':
        class _QuietGateStdout(object):
            """行级过滤：只丢 '  [OK] …' 行（[FAIL] 行必含 '[FAIL]'，恒放行）。"""

            def __init__(self, raw):
                self._raw = raw

            def write(self, s):
                if '[OK]' in s:
                    # report() 是整段单次 write，按行滤；[FAIL] 行恒保留
                    kept = [ln for ln in s.split('\n')
                            if ('[OK]' not in ln) or ('[FAIL]' in ln)]
                    if any(ln.strip() for ln in kept):
                        return self._raw.write('\n'.join(kept))
                    return len(s)  # 整段皆 OK 行：静默吞掉
                return self._raw.write(s)

            def flush(self):
                self._raw.flush()

        sys.stdout = _QuietGateStdout(sys.stdout)
    from yl_patch import run
    _rc = run(sys.modules[__name__])
    if _rc != 0:
        sys.exit(_rc)
    # ---- 0.9.13 成员新契约：standalone 客户端补丁（R-116/R-118）装配后套用 ----
    #   run() 已把 V28_MODULES 产物二进制落盘 OUT；此处对 OUT 按序套用 standalone 脚本。
    #   任何失败都以非零码退出（chain_build.build_client 靠 rc 中止；「预演==交付」
    #   由 dryrun_087 对同一套 standalone 套用保证两侧 md5 逐位一致）。
    #   ★ --check 模式不落盘 ⇒ 也不能对盘上旧产物套用 standalone（防误补旧包）。
    if '--check' in sys.argv:
        print('(--check 模式：不套用 standalone 补丁)')
        sys.exit(0)
    _errs = apply_standalone(OUT)
    if _errs:
        for _e in _errs:
            print('[ABORT] %s' % _e)
        sys.exit(1)
    sys.exit(0)
