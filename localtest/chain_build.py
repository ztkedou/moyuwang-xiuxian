# -*- coding: utf-8 -*-
r"""
chain_build.py — 0.8.2 链式构建（lead 独占；从冻结基座重建 bundle + 服务端）

背景（本模块存在的唯一理由）
----------------------------------------------------------------------------
1) `srv/index_v28.ts` 是**共享可变状态**。2026-09-28 09:48/09:55 发生过一次真实事故：
   srv-econ 的 P0 补丁被 srv-api 的 P2 补丁**整份覆盖**（实测 `base+p2` == 561,101 B，
   而 `base+p0+p2` 应为 565,639 B）。所以 srv 补丁必须由**一个**执行者从冻结基座**串行**应用。
2) `build_v26n.py` 会把产物直接写到 `build/assets/index-v28-20260928.js`，覆盖线上 0.8.1 定版。
   本脚本先备份/校验，再构建，再自证。

铁律
----------------------------------------------------------------------------
* 一切从 `_v281_base/` 冻结基座出发（`index_v28.base.ts` / `index-v28-20260928.base.js`）。
* 每个补丁 `--src <上一环产物> --out <本环产物>`，绝不 `--src == --out`。
* 每环跑完立刻 `md5sum` 自证 + `node --experimental-strip-types --check` 语法校验。
* 任一门禁 FAIL 立即中止，不落盘。

用法
----------------------------------------------------------------------------
  python localtest/chain_build.py --check          # 只校验基座指纹，不动任何文件
  python localtest/chain_build.py --client         # 只重建前端 bundle
  python localtest/chain_build.py --srv            # 只重建服务端 index_v28.ts
  python localtest/chain_build.py --all            # 两者都做
"""
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE_DIR = os.path.join(ROOT, '_v281_base')
STAGE = os.path.join(ROOT, '_chainstage')

PY = sys.executable
NODE = r'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe'

# ---- 冻结基座指纹（改这里 = 改事实源，须有明确理由）----
BASE_FP = {
    'index_v28.base.ts':            'f6ecc82e72d8425d5064f765d7de0684',
    'index-v28-20260928.base.js':   '515aaac94f3db6908aac0a728be5a6e1',
    'game-dicts.base.json':         '1b635513f553875060869272b790f910',
}

# ---- 本轮服务端补丁链（顺序 = 执行顺序；每个都会原子就地写 --src）----
# 0.8.7（implEventsSrv 接线，0.8.7-build-plan §1.2 定案，10 环）：
#   环 6 t3_xinfa087 心法百级 → 环 7 t10_farm 灵田六田（**必须先于 T5**：farmHarvestOne
#   公共入账点先成形，环 8 的掉玉挂点才能单收/一键收同口径）→ 环 8 p4_activity087
#   T5 四活动 → 环 9 t7_sect 仙盟 → 环 10 t8_mentor 师徒。环间锚区零交集，顺序仅为确定性。
SRV_CHAIN = [
    'srv_patch_p0_save.py',        # P0-①②③ 存档结构校验 + 令牌桶配额 + 一次性池
    'srv_patch_p2_api.py',         # P2-⑨ 非字符串 id / 原型链污染（asStr/asNum/asInt 收口）
    'srv_patch_p2b_hardening.py',  # P2-⑨ 残留硬化（lead 独占）：auth 三入口 + SECT_GF_BY_ID 去原型链
    'srv_patch_p3_brand.py',       # 0.8.3 入口迁移：拜师邮件里唯一一处玩家可见 /yl/ -> /myxxz/
    'srv_patch_fun086.py',         # 0.8.6 每日行乐三件套 + 茶馆加注 + 奇遇区间化/扩池 + 抽奖券
    'srv_patch_t3_xinfa.py',       # 0.8.7 T3 心法 10→100 级数值重做 + levelup 三段式（implXinfa）
    'srv_patch_t10_farm.py',       # 0.8.7 T10 灵田 3→6 田 + boost/tend/harvest-all（implGrotto；先于 T5）
    'srv_patch_activity087.py',    # 0.8.7 T5 限时活动 ×4：6 新表 + 4 type + 3 掉玉挂点 + actSettleTick + 8 端点（implEventsSrv）
    'srv_patch_t7_sect.py',        # 0.8.7 T7 仙盟：403 改码 + 审批流 + 检索 + 捐献回馈（implSectSrv）
    'srv_patch_t8_mentor.py',      # 0.8.7 T8 师徒：拜师 pending + decide/cancel + my/search 扩展（implMentorSrv）
    # 0.8.8/0.8.9（顺序 = KI-001 → net-2 → T9 → T7；前两环同源「灵石账目」故紧贴）：
    'srv_patch_ki001.py',          # KI-001 P0：存档灵石静默归零（缺字段被写 0）+ 反向截小（历史余额地板）
                                   #   治「服务端自己算错」。
    'srv_patch_net2_stale.py',     # net-2：GM 发放被「陈旧推档」抹掉（G2 FAIL 实测）。
                                   #   N1 回显白名单加 gm 域 + N2 grant 回传 balance/gm_revision
                                   #   + N3 409 stale_save 多带权威 balance。
                                   #   治「服务端算对了却被陈旧档盖回去」。与 ki001 互补，
                                   #   **锚区零交集**（ki001 在 settleSaveEconV2 内；本环在 :1430 回显
                                   #   中间件 / :2573 grant 收尾 / :2128 409 分支），紧贴仅为可读性。
    'srv_patch_t9_activity.py',    # 0.8.8 T9 仙途任务活跃度：4→18 项 + 6 档宝箱 + 周里程碑 + 读时计算
    'srv_patch_t7_legacy.py',      # 0.8.8 T7 传承：去掉一键全用 + 分层定价 + 声望限购 + inheritanceLevel clamp
    # 0.8.9（本环）：
    'srv_patch_t5_crops.py',       # 0.8.9 T5 灵田品种重构：5 旧种入兼容区 + 20 新种（5 品阶 × 4 产品线）
                                   #   + farmHarvestOne 双出口（sell/consume）+ status 下发 cropList
                                   #   + 照料改档「每次 +2% / 当日封顶 +10%」。**必须在 t10_farm 之后**
                                   #   （依赖 FARM_SLOTS=6 / farmHarvestOne / FARM_TEND_BONUS 三锚）。
    'srv_patch_reward089.py',      # 0.8.9 奖励口径统一（i4-reward）：服务端 6 处灵石发放的
                                   #   境界倍率由 C2 指数(1.5^idx) 收敛到 C1 线性(2idx+1, 0->4/3)，
                                   #   与客户端 YLRF / YLRewardFactor **同源同曲线**。
                                   #   改点：realmMultOf / sameRealmMult / 双修灵石 / 赴宴回礼 / 传阅奖励
                                   #   （realmMultOf 一处收敛擂台+仇杀+请安+求签+出师贺礼 5 个调用点）。
                                   #   边界：血量(1.5^) 与修为(expGain) **不动**；各基数常量 **不动**。
                                   #   锚区（境界倍率函数 / 擂台常量区 / 赴宴 / 传阅）与前环零交集。
    'srv_patch_baseclean089.py',   # 0.8.9 基座清理（i2-srv，**末环**）：
                                   #   ① 删 `loadGameDicts()` 内 2 行冗余 `require('fs'/'path')`
                                   #      —— ESM 下 `require` 未定义，抛错被 catch 静默吞掉 ⇒
                                   #      `/api/gm/dicts` 恒返回 {}（实测 0 key → 修复后 16 key）。
                                   #      锚区 = loadGameDicts（:2899 附近）。
                                   #   ② `GM_PASSWORD` 去掉弱口令兜底，缺省即 `process.exit(1)`
                                   #      —— 原 `.env` 丢失会静默降级为可猜口令。锚区 = :1094 定义行
                                   #      （比对处 :2315 一字未动）。
                                   #   两锚区与前 16 环零交集；放末环因它只清基座遗留、不引新功能。
    # 0.8.9（本环）：
    'srv_patch_rankingmig.py',     # 0.8.9 P0② 存量库加列**幂等**化（i8 侧，链第 18 环 / 新末环）：
                                   #   治「空库冷启动必崩」——`rankings` 建表自带 `name` 列
                                   #   （:184），而 :388 守卫据 `PRAGMA table_info(rankings)` 判断
                                   #   「缺列」。serialize 队列只保证**入队顺序**、不提供**完成屏障**
                                   #   ⇒ 紧随 CREATE TABLE 的 PRAGMA 可能读到空 schema（实测 rows=0
                                   #   @44ms）⇒ 守卫误判 ⇒ 对已含 name 的表重复 ADD COLUMN
                                   #   ⇒ `SQLITE_ERROR: duplicate column name: name` ⇒ db 'error'
                                   #   事件在模块顶层抛出、无人 catch ⇒ **进程起不来**（空库 100%）。
                                   #   修法（lead 裁定方案 D）：新增 `safeAddColumn()`，DDL 本身幂等
                                   #   （容忍 duplicate column name），守卫 PRAGMA 降为快路径。
                                   #   **同病 20 处 ALTER 一次收口**（users/saves/rebirth_state/
                                   #   rankings/adventures/sects），并合并 rankings 两处 PRAGMA 为 1。
                                   #   锚区 = dbPath 定义后（:85）+ 建表/迁移守卫区（:93-:2783 /
                                   #   :11353-:11439），与前 17 环零交集；顺序必须**在末**（它扫全仓）。
    'srv_patch_t2spirit.py',       # 0.8.9 T2 灵宠面板服务端能力（i2 侧，链第 19 环 / 新末环）：
                                   #   ① GET /api/pet/spirit/list —— 灵宠列表（面板采集面）：
                                   #      pets 权威行 → T2 视图（品阶 / 亲密度 / 气血 / 修为 /
                                   #      融合状态 / 消耗预览），只读投影不落库。
                                   #   ② POST /api/pet/spirit/merge —— 融合：服务端权威扣融合费
                                   #      （saveLock 补偿式，同 feed/alchemy）+ 成功率（策划 §2.4）
                                   #      + 失败保底（连续失败 3 次后第 4 次必成功，计数落 pets.merge_pity）
                                   #      + merged 标记；属性继承按策划 §2.1 P2 归客户端存档域，
                                   #      故只回 inheritHints，**不代写 player.pets**。
                                   #   ③ pets.merged / pets.merge_pity 两列 → safeAddColumn 幂等加列
                                   #      （不碰 pets 建表 DDL，守「锚区零交集」）。
                                   #   定价按用户 2026-09-29 指示：基础 10000 灵石起、以品阶为主、
                                   #   亲密度弱因子 ≤5%（融合费 10,000~29,300，极差 2.93×）。
                                   #   锚区 = [petcore] 头/尾（:5171/:5228）+ safeAddColumn 定义后
                                   #   （:101）+ pet/play 之后（:10708），与前 18 环零交集。
    'srv_patch_t16arena.py',       # 0.8.8 T16 演武场（i2-srv 侧，链第 20 环 / 新末环）：
                                   #   客户端 `yl_t16arena_ext.py` 已交付（三区分栏：试炼 PVE /
                                   #   论剑 PVP / 恩怨），但服务端**零实现** ⇒ 6 个新端点全吃
                                   #   Express 404、面板整块报错。本环补齐：
                                   #   ① 4 张新表（arena_trials / arena_scores / arena_snapshots
                                   #      / arena_trial_daily），全 `CREATE TABLE IF NOT EXISTS`
                                   #      且建表即带全部列（无 ALTER）。
                                   #   ② 6 个新端点：GET /api/arena/trials、POST /trials/fight、
                                   #      POST /trials/buy、GET /ladder、POST /snapshot、POST /grudge。
                                   #   ③ /api/arena/my **追加**字段（realmIndex / grudges / points /
                                   #      tier / tierName / snapshotLeft / rules）—— D7 只加不改。
                                   #   数值逐条落 T16 §5.1/§5.2/§5.3/§5.4（整数百分比式，禁浮点字面量）；
                                   #   ★ 活跃度零埋点（§6.4）：不写 daily_quests、不新增 QUEST_DEFS、
                                   #   不碰 /api/quest/chest —— 活跃度「擂台论道」归 T9 读时 COUNT
                                   #   arena_battles（该表结构一字不动）。
                                   #   锚区 = idx_arena_cha 索引后（:771）+ 师徒传功段前（:9685）
                                   #   + /arena/my 响应尾部（:9565），与前 19 环零交集；放末环因
                                   #   它只**新增**端点/表，不改任何既有语义。
    'srv_patch_v2810.py',          # 0.8.10 服务端综合环（第 21 环 / 新末环）—— 8 项：
                                   #   ① /api/activity/shop(+exchange) 顶层 balance → jadeBalance
                                   #      （资损级：客户端把顶层 balance 当灵石采纳，而这里是灵玉）。
                                   #   ② 灵宠秘径基础 10000 → 7500（新 PET_T2_PATH_BASE；融合仍 10000）
                                   #      + /pet/spirit/list 追加 pathCostBase。
                                   #   ③ 悟道挂机时长 = 打坐 + 历练（新 ylWudaoIdleDelta，两处调用点）。
                                   #   ④ DELETE /api/mail/:id（200/400/404/409，claimed=1 不可删）。
                                   #   ⑤ snapshotOldSave 加 force 参（回档点 true 绕过 10min 节流；
                                   #      写档点不传）—— 治「10min 内连回档两次不可逆」。
                                   #   ⑥ gm_sessions.expires_at 幂等加列 + 登录写 7 天 + 校验过期
                                   #      （过期/存量 NULL ⇒ 401 + 惰性删行）。
                                   #   ⑦ DELETE /api/gm/activity/:id（删 events 行 + 审计；级联只留孤儿）。
                                   #   ⑧ 禁言：users.muted_until 加列 + POST /gm/players/:id/mute
                                   #      + 发言处拦截（POST /api/messages）+ GET /api/me/mute。
                                   #   锚区（活动商店 / 灵宠定价 / 悟道挂点 / 邮件路由 / 快照 / GM 会话 /
                                   #   GM 活动 / 封禁-聊天）与前 20 环零交集；放末环因它**只做加法**。
    'srv_patch_arenaweek.py',      # 0.8.10 演武场周榜结算环（第 22 环 / 新末环）—— 1 件事：
                                   #   T16 周榜「每周一 0 点结算 / 前 10 名灵石 / 第 1 名称号
                                   #   「太虚魁首」/ 本周打满 10 场参与奖」客户端**已承诺**、
                                   #   服务端**零实现**（假承诺）⇒ 本环补齐：
                                   #   ① 称号目录行 太虚魁首（source=arena_week1, stoneRate 5%）
                                   #   ② 周榜结算全套（周键换算 / 场次统计 / 奖励表 / arenaWeekSettle）
                                   #      幂等键复用 activity_config `arena_week_settled:<周一>`（无新表）
                                   #      倍率一律 realmMultOf（与全仓灵石奖励同源，非策划案的 1.5^r）
                                   #      ★ 护栏：名次奖要求「本周至少打 1 场」（防停玩高分号每周白拿奖）
                                   #   ③ GET /api/arena/week（榜单 + 我的名次 + 本周场次 + 最近结算周）
                                   #   ④ 活动 tick 内挂结算（在 actEngineOn 早退**之前**，与引擎无关）
                                   #   ⑤ boot-run（重启跨周一 0 点补结算）
                                   #   锚区（称号目录 / 擂台段前 / 恩怨端点前 / 活动 tick / 活动 boot）
                                   #   与前 21 环零交集；放末环因它**只做加法**。
    'srv_patch_snapself.py',       # 0.8.10 玩家侧存档快照「时光回溯」环（第 23 环 / 新末环）—— 1 件事：
                                   #   把 `save_snapshots`（写档时自动落 / 每号最多 50 条 /
                                   #   本意就是「误覆盖救援」）开放给玩家**自助回溯**。
                                   #   此前读侧**只有 GM 端点**（BASECLEAN089 ③-a/③-b）
                                   #   ⇒ 玩家自己误操作把档搞坏只能求 GM。本环补玩家自助面：
                                   #   ① GET  /api/snapshots              本人快照列表 + 本周额度
                                   #      （只回元数据 + 4 个标量摘要，整档 JSON 不出网）
                                   #   ② POST /api/snapshots/:id/restore  自助回溯
                                   #   ③ 额度三件套 snapSelfQuota/Reserve/Release：
                                   #      **每周 1 次**（北京周一口径），键复用 activity_config
                                   #      `snap_self_used:<周一>:<uid>`（**无新表 / 无 DDL**）
                                   #      ★ 必须限额：本作玩法多在客户端结算、只写存档 ⇒
                                   #        「回溯」= 无成本撤销一次结果（抽奖刷概率）
                                   #   ④ 归属校验打在 id + user_id（防跨号越权）；
                                   #      回溯前 snapshotOldSave(..., force=true) ⇒ 回溯可逆；
                                   #      写回走 updatePlayerSave（saveLock + gm_revision++）
                                   #   锚区 = GM 快照元数据端点注释之前，与前 22 环零交集；
                                   #   放末环因它**只做加法**（且必须早于 GM 快照端点定义处，
                                   #   故只能插在 :2562 那一处）。
    'srv_patch_offline2.py',       # 0.8.12 R-021 离线窗口锚点（真实离开时刻）+ R-020 灵石日志文案：
                                   #   ① saves 加 last_seen_at / last_resume_at 两列（safeAddColumn 幂等）
                                   #   ② 新增纯函数 offlineAnchor() + POST /api/session/presence
                                   #   ③ report / claim 的锚点改走 offlineAnchor()（两处同口径）
                                   #   ④ 响应体补只读诊断字段
                                   #   ★ 收益公式一行未动（6 条硬断言 + 改前改后计数相等）；
                                   #     /api/save 心跳只刷 updated_at、不碰 last_seen_at。
                                   #   链序：无前置依赖（session 内容已在 s01/s02 并入），挂链尾即可。

    'srv_patch_farm2.py',        # 0.8.12 R-019① 灵田照料 2h 冷却（依赖 t5_crops）
    'srv_patch_fun2.py',         # 0.8.12 R-029 茶馆可查看记录 myHistory（依赖 fun086）
    'srv_patch_dungeon2.py',     # 0.8.12 R-032 秘境每日上限按境界（与客户端 YLXW_DG_CAP 同表）
    # 0.8.13（本环，第 28/29 环 / 新末环）：
    'srv_patch_econ2.py',        # 0.8.13 R-028 周里程碑 3→5 档（WEEK_MILESTONES 表 +
                                 #   端点注释）。**MILE_MONTHLY_TIER=1000 一行未动**
                                 #   （传承石仍按月）⇒ t9_activity 的 G14 仍成立。
                                 #   发奖逻辑全表驱动，一行未改。锚点与 t9_activity 零交集。
    'srv_patch_r018.py',         # 0.8.13 R-018 妖灵培养服务端：pets 加列 + pet_spirit_exped
                                 #   新表 + 17 处就地替换 + 1 处整块注入（插在 `// [/t2spirit]`
                                 #   之后，该行保留 ⇒ t2spirit G27 计数不变）+ 新端点
                                 #   /pet/aptitude /pet/spirit/exped(+claim) /pet/spirit/away。
                                 #   PET_FEED_COST / PET_PLAY_DAILY_MAX 等定义一字未改。
    # 0.8.13（本环，第 30 环 / 新末环）：
    'srv_patch_r013b.py',        # 0.8.13 R-028/R-013 收尾：传承石 `legacy` 由 **1000 档移到 2310 档**
                                 #   （最高满活跃度）+ `MILE_MONTHLY_TIER` 1000→2310；
                                 #   删「折算 5000 灵石」分支，改走 `updatePlayerSave` 背包通道发
                                 #   **传承石实物**（字段与客户端 `yl_r013_ext.py` 的 `YlxwInhStoneItem()`
                                 #   逐字对齐 ⇒ 交易行上架零改动可用）。
                                 #   锚点：WEEK_MILESTONES 表 / 端点注释 / 发奖分支；与 econ2 零交集
                                 #   （econ2 改的是表值，本环改的是 legacy 归属与发放形态）。
    # 0.8.13（本环，第 31 环 / 新末环）：
    'srv_patch_r013c.py',        # 0.8.13 R-028 收尾：把「整档按月」**解耦**成「只有传承石按月」
                                 #   —— 2310 档的常规奖励（60000 灵石 / 600 修为 / 30 券）恢复**周频**，
                                 #   只有传承石那件按「月」限领一次（用户口径：「最多一个月一个」）。
                                 #   幂等键：档位沿用 `weekMonthKey(week)+':'+tier`（周），
                                 #   传承石单独用 `weekMonthKey(week)+':legacy'`（月）。
                                 #   锚点：claim 幂等键构造 + legacy 发放分支；与 r013b 同区但**顺序相接**
                                 #   （r013b 先改发放形态，本环再拆幂等键）。
    # 0.8.11.1（本环，第 32 环 / 新末环）：
    'srv_patch_claimedfix.py',   # 0.8.11.1 周里程碑「已领取」显示修复（服务端半边）：
                                 #   `GET /api/quest/summary` 原来用**裸周号**查 `activity_milestones`
                                 #   （`WHERE week = ?`），而 `claim` 写入的是 `'w'+week+'_'+tier`
                                 #   ⇒ 永远查不到 ⇒ `claimed` 恒 false（显示 bug，非资损：
                                 #   UNIQUE(user_id, week, tier) 会挡住重复发放）。
                                 #   改为 `week LIKE 'w<week>_%'` 前缀匹配。
                                 #   ★ 客户端半边在 `yl_claimedfix_ext.py`（数组当字典取的 bug），两者配套。
    # 0.8.11.2（本环，第 33 环 / 新末环）：
    'srv_patch_r018b.py',        # R-018 D5 灵纹：注入 R018B_RUNE_TABLE(6 纹) + 8 纯函数 +
                                 #   POST /api/pet/rune（首次免费 / 此后 50000 / 未解锁 409）；
                                 #   幂等加列 pets.rune_active；GET 回显 rune:{active,list}；秘径修为叠蕴纹。
                                 #   ★ 硬依赖 srv_patch_r018.py（同区）。
    # 2026-10-01（本环，第 34 环 / 新末环）：
    'srv_patch_r039.py',         # R-039 重置删干净（服务端半边）：
                                 #   新增 POST /api/character/reset（走现有 authenticateToken + rateLimit），
                                 #   一条 BEGIN IMMEDIATE ... COMMIT 清约 60 张该玩家的表（称号/统计/心法/成就/功法/存档...），
                                 #   先做社交修复（宗主让位/结义解散/悬赏退回/道侣和离）再删。
                                 #   保留 users 行 + 登录态（refresh_tokens/active_sessions）+ 各类字典表。
                                 #   ★ 客户端半边在 yl_r039_ext.py，两者配套。
    # 2026-10-01（本环，第 35 环 / 新末环）：
    'srv_patch_050.py',          # R-050 洞府：每日催熟总次数基础值 3→10（服务端半边）：
                                 #   只把 t10_farm 定档常量 FARM_BOOST_BASE_CAP 3→10 + farmBoostCap
                                 #   说明注释同步；公式（+1 次/2 级洞府）、每田每日 1 次闸门、
                                 #   催熟计价一字不动。催熟是纯灵石回收口（费用恒高于作物净收益），
                                 #   抬次数只加大回收口、不构成刷钱口。
                                 #   ★ 硬依赖第 7 环 srv_patch_t10_farm.py（锚是其常数定义行）；
                                 #   ★ 客户端半边在 yl_050_ext.py，两者配套。
    # 2026-10-01（本环，第 36 环 / 新末环）：
    'srv_patch_054.py',          # R-054 每日签到（服务端半边，七日礼→月历长期签到）：
                                 #   北京自然月 lazy 建场 + 按境界时薪实算 + 五档里程碑
                                 #   （券/灵石/修为/太虚悟道卷/限定称号）+ activity_sign_miles 幂等表。
                                 #   ★ 硬依赖第 8 环 srv_patch_activity087.py 在前；
                                 #   ★ 客户端半边在 yl_054_ext.py，两者配套。
    # 2026-10-01（本环，第 37 环 / 新末环）：
    'srv_patch_055.py',          # R-055 灵玉阁掉落口径透明化（服务端半边）：
                                 #   掉率 2→50、顶价 2500→1000、日上限 300 不变。
                                 #   ★ 仅要求第 8 环 srv_patch_activity087.py 在前；
                                 #   ★ 客户端半边在 yl_055_ext.py，两者配套。
    # 2026-10-01（本环，第 38 环 / 新末环）：
    'srv_patch_056.py',          # R-056 万妖巢穴多 boss（服务端半边）：
                                 #   每期连刷 5 只 + 每只免费 5 次（换 boss 归零）+ 10 分钟出手冷却
                                 #   + 血量每只 +50%；结算器/诛妖符零改动。
                                 #   ★ 仅要求 activity087 环在前；
                                 #   ★ 客户端半边在 yl_056_ext.py，两者配套。
    # 2026-10-01（本环，第 39 环 / 新末环）：
    'srv_patch_057.py',          # R-057 奇遇抽奖经济重做（服务端半边）：
                                 #   每日 3→10 次 + 30 分钟冷却（drawn_at 列）+ 消耗修为槽 1%
                                 #   + 四档灵石 ×30 + 15% 暴击双倍。
                                 #   ★ 无顺序硬约束（锚区与前面各环零交集）；
                                 #   ★ 客户端半边在 yl_057_ext.py，两者配套。
    # 2026-10-01（本环，第 40 环 / 新末环）：
    'srv_patch_061.py',          # R-061 演武场试炼战报反馈（服务端半边）：
                                 #   fight 响应追加 message 战报字段。
                                 #   ★ 锚是第 20 环 srv_patch_t16arena.py 产物形态（链内早已应用），
                                 #     放链尾无顺序风险；客户端半边在 yl_061_ext.py，两者配套。
    # 2026-10-01（本环，第 41 环 / 新末环）：
    'srv_patch_062.py',          # R-062 秘境单独点选收益 ×3 + 冷却 15 分钟（服务端半边）：
                                 #   DUNGEON_ENTRY_CD_MS 30_000 → 900_000。
                                 #   ★ 硬依赖第 27 环 srv_patch_dungeon2.py 在前
                                 #     （REQUIRES 断言 DUNGEON_CAP_BY_REALM 在位；装反则 dungeon2
                                 #     的 REQUIRES 30_000==1 失败，双向强制）；
                                 #   ★ 客户端半边在 yl_062_ext.py，两者配套。
    # 2026-10-01（本环，第 42 环 / 新末环）：
    'srv_patch_063.py',          # R-063 roguelike 地宫单独算上限（服务端半边）：
                                 #   dungeon_tracker 加 rogue_count/rogue_last_ts 分账 +
                                 #   独立上限表 [3,5,7,8,10,11,13]。
                                 #   ★ 硬依赖第 27 环 srv_patch_dungeon2.py 在前（REQUIRES 断言
                                 #     DUNGEON_CAP_BY_REALM 在位强制）；与 srv_patch_062.py
                                 #     零锚点交集先后皆可，惯例 062 → 063；
                                 #   ★ 客户端半边在 yl_063_ext.py，两者配套。
    # 2026-10-01（本环，第 43 环 / 新末环）：
    'srv_patch_064.py',          # R-064 炼丹三修（服务端半边）：
                                 #   ALCHEMY_RECIPES 3→9 方（同收益率不通胀）+ unlockLevel 权威门槛
                                 #   （start 前置校验）+ /alchemy/claim 出炉补熟练度入账
                                 #   （丹房同 pm 表、9 层封顶、×1.2 丹炉倍率、失败不阻塞、
                                 #   响应追加 prof 字段供客户端 toast）。
                                 #   ★ 硬依赖 activity087 领取挂点（actDropTokens 行）在链内
                                 #     （REQUIRES 断言）；与 061/062/063 零锚点交集，挂链尾；
                                 #   ★ 客户端半边在 yl_064_ext.py，两者配套。
    # 2026-10-01（本环，第 44 环 / 新末环）：
    'srv_patch_066.py',          # R-066 宗门功法阁贡献值重做 + 修满化形（服务端半边）：
                                 #   SECT_GF_TIER_BASE {1:200,2:600,3:1500,4:4000} + sectGfCost
                                 #   指数式 floor(base×2^(level-1)) + GET /sect/gongfa 下发
                                 #   converted + 新增 POST /sect/gongfa/convert（5 层大成免费
                                 #   化形转实装功法，幂等，拒绝码 400/409 不用 403）。
                                 #   ★ 硬依赖 sectgf 链在位（REQUIRES 断言 SECT_GF_BY_ID /
                                 #     player_sect_gongfa / sectGfPlayerOf / updatePlayerSave）；
                                 #     与 061/062/063/064 零锚点交集，挂链尾；
                                 #   ★ 客户端半边在 yl_066_ext.py，两者配套。
    # 2026-10-01（本环）：R-047 灵田双出口收益 ×3 / R-048 灵草分档
    'srv_patch_r047.py',
    'srv_patch_r048.py',
    'srv_patch_r069.py',
    'srv_patch_r071.py',
    'srv_patch_r073.py',
]

# ---- 前端产物路径（0.8.11.8 换名：index-v290-20261001.js，与 build_v26n.py OUT 逐字一致）----
CLIENT_OUT = os.path.join(ROOT, 'build', 'assets', 'index-v290-20261001.js')
SRV_OUT = os.path.join(ROOT, 'srv', 'index_v28.ts')


def md5f(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def md5s(s):
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def hr(t):
    print('\n' + '=' * 78)
    print(t)
    print('=' * 78)


def check_bases():
    hr('STEP 0 — 冻结基座指纹校验')
    bad = []
    for name, want in BASE_FP.items():
        p = os.path.join(BASE_DIR, name)
        if not os.path.isfile(p):
            print('  [MISSING] %s' % name)
            bad.append(name)
            continue
        got = md5f(p)
        ok = (got == want)
        print('  [%s] %-30s %s' % ('OK' if ok else 'FAIL', name, got))
        if not ok:
            bad.append(name)
    # 工作副本（会被构建覆盖的两个）当前是否还等于基座
    print('\n  工作副本现状（不等于基座 = 已被别人改过，需先还原）:')
    for live, base in ((CLIENT_OUT, 'index-v28-20260928.base.js'),
                       (SRV_OUT, 'index_v28.base.ts')):
        if not os.path.isfile(live):
            print('    [MISSING] %s' % os.path.relpath(live, ROOT))
            continue
        got, want = md5f(live), BASE_FP[base]
        print('    [%s] %-44s %s' % ('OK' if got == want else 'DRIFT',
                                     os.path.relpath(live, ROOT).replace('\\', '/'), got))
    return not bad


def restore_from_base():
    hr('STEP 0b — 工作副本还原为冻结基座')
    for live, base in ((CLIENT_OUT, 'index-v28-20260928.base.js'),
                       (SRV_OUT, 'index_v28.base.ts')):
        shutil.copyfile(os.path.join(BASE_DIR, base), live)
        print('  还原 %s -> %s' % (os.path.relpath(live, ROOT).replace('\\', '/'), md5f(live)))


def build_client():
    hr('STEP C — 前端 bundle 重建（build_v26n.py）')
    if os.path.isfile(CLIENT_OUT):
        shutil.copyfile(CLIENT_OUT, CLIENT_OUT + '.pre082')
    r = subprocess.run([PY, os.path.join(ROOT, 'build_v26n.py')],
                       cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    tail = (r.stdout or '')[-6000:]
    print(tail)
    if r.returncode != 0:
        # ★ 教训（2026-09-28）：上面只印 tail 的最后 6000 字符，失败门禁若在更早的位置
        #   就会被截掉，只留一句「门禁未过，拒绝落盘」——等于让你去猜是哪条。
        #   这里把 build_v26n 完整 stdout 里的 FAIL 行单独捞出来印，永不截断。
        fails = [ln for ln in (r.stdout or '').splitlines()
                 if ('FAIL' in ln and 'actual=' in ln) or 'PatchError' in ln]
        if fails:
            print('\n[门禁失败明细] 共 %d 条：' % len(fails))
            for ln in fails[:40]:
                print('  ' + ln.strip())
        print('\n[ABORT] build_v26n.py rc=%d' % r.returncode)
        print((r.stderr or '')[-3000:])
        return None
    if 'FAIL' in tail and 'PASS' not in tail:
        print('\n[ABORT] 门禁疑似 FAIL')
        return None
    got = md5f(CLIENT_OUT)
    print('\n  bundle 产物: %s  bytes=%d  md5=%s'
          % (os.path.relpath(CLIENT_OUT, ROOT).replace('\\', '/'),
             os.path.getsize(CLIENT_OUT), got))
    return got


def build_srv():
    hr('STEP S — 服务端 index_v28.ts 重建（从冻结基座串行应用）')
    os.makedirs(STAGE, exist_ok=True)
    cur = os.path.join(STAGE, 's00.base.ts')
    shutil.copyfile(os.path.join(BASE_DIR, 'index_v28.base.ts'), cur)
    print('  [s00.base    ] md5=%s' % md5f(cur))

    # ★ 契约适配（2026-09-28 实测）：成员补丁脚本只实现了 `--src`，**就地原子写回 --src**。
    #   所以本装配器不再依赖 `--out`：先把上一环产物**复制**成下一环的独立工作副本，
    #   再让补丁就地改这份副本。这样「就地写」反而成了优点——
    #   共享文件 `srv/index_v28.ts` 在整个装配过程中**一次都不会被碰到**，
    #   只有全部通过后才由本函数末尾统一落盘。
    for i, mod in enumerate(SRV_CHAIN, start=1):
        src_py = os.path.join(ROOT, mod)
        if not os.path.isfile(src_py):
            print('\n[ABORT] 缺少补丁模块 %s' % mod)
            return None
        nxt = os.path.join(STAGE, 's%02d.%s.ts' % (i, mod.replace('srv_patch_', '').replace('.py', '')))
        shutil.copyfile(cur, nxt)          # 独立工作副本（= 上一环产物）
        before = md5f(nxt)
        print('\n  --- [%d/%d] %s ---' % (i, len(SRV_CHAIN), mod))
        r = subprocess.run([PY, src_py, '--src', nxt],
                           cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
        out = (r.stdout or '') + (r.stderr or '')
        print('\n'.join(out.strip().splitlines()[-14:]))
        if r.returncode != 0:
            print('\n[ABORT] %s 失败 rc=%d' % (mod, r.returncode))
            return None
        if not os.path.isfile(nxt):
            print('\n[ABORT] %s 产物丢失 %s' % (mod, nxt))
            return None
        after = md5f(nxt)
        if after == before:
            print('\n[ABORT] %s 未产生任何变化（补丁静默失效）md5=%s' % (mod, after))
            return None
        print('  => %s  md5=%s  bytes=%d  (delta %+d B)'
              % (os.path.basename(nxt), after, os.path.getsize(nxt),
                 os.path.getsize(nxt) - os.path.getsize(cur)))
        cur = nxt

    # 语法校验（node --experimental-strip-types --check）
    print('\n  --- 语法校验 ---')
    r = subprocess.run([NODE, '--experimental-strip-types', '--check', cur],
                       cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    print('  node --check rc=%d' % r.returncode)
    if r.stdout.strip():
        print('  ' + r.stdout.strip()[:2000])
    if r.stderr.strip():
        print('  ' + r.stderr.strip()[:2000])
    if r.returncode != 0:
        print('\n[ABORT] 语法校验未通过，未落盘')
        return None

    shutil.copyfile(cur, SRV_OUT)
    got = md5f(SRV_OUT)
    print('\n  已落盘 %s  md5=%s  bytes=%d'
          % (os.path.relpath(SRV_OUT, ROOT).replace('\\', '/'), got, os.path.getsize(SRV_OUT)))

    # ★ 同时留一份**不可变参照**：所有人复验时用这份，不用 srv/index_v28.ts
    #   （后者是 deploy 的取源，理论上仍可能被谁误写；_chainstage/ 这份是装配产物原样副本）
    #   参照名随批次递增：v282/v286/v287/v288/v2810 保留不动（设计案行号引用仍有效）；
    #   **0.8.11.2 起 = index_v28.v28112.ts**（★ 注意 v28111 那份在 0.8.11.2 装配时**已被覆盖为 0.8.11 内容**，
    #   不可再当 0.8.10 定版参照 —— 0.8.10 定版链尾以 _chainstage/s23.snapself.ts 为准）。
    canon = os.path.join(STAGE, 'index_v28.v28112.ts')
    shutil.copyfile(cur, canon)
    print('  不可变参照 %s  md5=%s（广播给 ver-a/ver-b 用这个路径做 --srv=）'
          % (os.path.relpath(canon, ROOT).replace('\\', '/'), md5f(canon)))
    return got


def main():
    args = set(sys.argv[1:])
    if not check_bases():
        print('\n[ABORT] 基座指纹不符，先查清是谁改的')
        return 2
    if '--check' in args or not args:
        return 0

    if '--client' in args or '--all' in args:
        c = build_client()
        if c is None:
            return 3
    if '--srv' in args or '--all' in args:
        s = build_srv()
        if s is None:
            return 4

    hr('汇总')
    print('  前端 bundle   md5=%s' % md5f(CLIENT_OUT))
    print('  服务端 index  md5=%s' % md5f(SRV_OUT))
    print('  game-dicts    md5=%s' % md5f(os.path.join(ROOT, 'srv', 'game-dicts.json')))
    print('\n  下一步：把上面两个 md5 广播给 ver-a / ver-b / cli-num / cli-ui 做复验。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
