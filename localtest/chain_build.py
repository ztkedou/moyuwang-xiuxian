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
# ★ 2026-10-08 修：原为写死 `…/node/versions/22.22.2-3/node.exe`，
#   但本机 node 已随工具升级为 22.22.2-6（旧目录被删）⇒ 写死路径会 FileNotFoundError。
#   改为：YL_NODE 环境变量 → versions 目录下**按名排序取最新** → 兜底裸 `node`。
_NROOT = r'C:/Users/<USER>/.workbuddy-ai/binaries/node/versions'
_NCANDS = []
if os.path.isdir(_NROOT):
    _NCANDS = sorted(os.path.join(_NROOT, _d, 'node.exe') for _d in os.listdir(_NROOT))
    _NCANDS = [_c for _c in _NCANDS if os.path.isfile(_c)]
NODE = os.environ.get('YL_NODE') or (_NCANDS[-1] if _NCANDS else 'node')

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
    'srv_patch_r078.py',
    'srv_patch_r077.py',
    'srv_patch_r081.py',
    # 2026-10-01（本环，第 45 环 / 新末环）：
    'srv_patch_101.py',          # R-091 悟道体系重规划（服务端半边）：
                                 #   ① 去重：阵道 攻击→修炼速度(stat=cultivate)、御道 气血→资源产出(stat=gather)，
                                 #      六道六定位互不重复；
                                 #   ② 稀有道等阶门槛：阵道元婴期(序3)、御道化神期(序4)起开放（门槛只挡未投入者，
                                 #      已投入 exp>0 祖父放行，不追溯锁死）；挂机心得只在已开放的系内随机；
                                 #   ③ 手动顿悟灵石价随境界递增（炼气 5000 → 长生 60000，≈12×）；
                                 #   ④ ★祖父条款：阵/御定位变更按「改前已投入 exp ×50」一次性返还灵石，
                                 #      走 insertMail，幂等键 activity_config['r091_wudao_respec:<uid>']（先占键后发信）；
                                 #      升级曲线刻意不动 ⇒ 存量等级/exp 100% 保留（零降级）。
                                 #   ★ 锚区（[wudaocore] 块 / wudao 两端点 / tickWudaoIdle）与既有各环零交集，
                                 #     挂链尾；客户端半边不在本次范围（客户端读服务端下发字段渲染）。
    # 2026-10-01（本环，第 54 环 / 新末环）：
    'srv_patch_110.py',          # R-110 悟道十道重做（服务端半边）：
                                 #   ① 六道 → 十道：新增 锋道(critDamage/暴伤) / 影道(dodge/闪避) /
                                 #      甲道(damageReduction/减伤) / 噬道(lifeLeech/吸血)；
                                 #      旧六道只改 name/statName（**key 与 level/exp 全保留 ⇒ 存量零降级**）；
                                 #   ② 展示顺序 = 气血→攻击→防御→暴击→暴伤→闪避→减伤→吸血→修炼→资源；
                                 #   ③ WUDAO_REALM_GATE 6→10 项（炼气/筑基/金丹/元婴/化神/长生境逐档开放；
                                 #      门槛只挡未投入者，exp>0 祖父放行 —— 沿用 R-091 语义）；
                                 #   ④ 顺手修 GET /api/wudao 的 LIMIT 6 静默截断新增 4 道；
                                 #   ⑤ 升级曲线 25*(l-1)*l 与 R-091 祖父条款/幂等键逐字未动。
                                 #   ★ 客户端 bundle 无需为悟道单独改动（纯视图，顺序与名称由服务端下发）。
    # 2026-10-02 链式自动轮次第 2 批（第 55~57 环 / 新末环）：
    'srv_patch_111.py',          # R-111 每日签到「当月场永不建立」根因修复（服务端半边）：
                                 #   actSignDaysInMonth / actSignEnsureMonth 两处
                                 #   `month.slice(0, 4)` → `month.slice(0, 5)`（"2026-" + "11" = "2026-11"）。
                                 #   旧写法拼出 "202611" ⇒ Date.parse = NaN ⇒ endAt = NaN
                                 #   ⇒ actSignEnsureMonth 恒返 null ⇒ events.end_at 绑 NULL
                                 #   ⇒ GET /api/activity/checkin 恒 409「签到暂未开放」（1~11 月全坏、12 月正常）。
                                 #   ★ 客户端半边 = V28_MODULES 'r111'；锚区与既有各环零交集。
    'srv_patch_113.py',          # R-113 万妖巢穴「五 boss 同现 + 逐只次数/冷却」（服务端半边）：
                                 #   ① 新增常量 PAID_LIMIT=10 / PAID_COOLDOWN_MS=5min；
                                 #   ② 新表 event_boss5(event_id, boss_no) 复合主键（IF NOT EXISTS，无迁移）；
                                 #   ③ ensure 去「逐只顺序刷新」、五槽位幂等建场；
                                 #   ④ strike/talisman 逐只化（免费 5/日/只 + 10min；收费 10/日/只 + 5min），
                                 #      请求/回执带 bossNo；status 回 bosses[] 逐只状态；
                                 #   ⑤ event_boss 降为聚合行（血量求和，五只全诛才 killed=1）⇒ 结算器/榜单/邮件零改动。
                                 #   ★ 客户端半边 = V28_MODULES 'r113'（必须排 r056 之后）；取代 srv_patch_056.py 的
                                 #     「单只顺序 / 第 X/Y 只 / 单只 coolLeft」形态 ⇒ 其 16 条 gate 已同步改判。
    'srv_patch_115.py',          # R-115 灵田「加属性作物种子价大幅提升」（服务端半边）：
                                 #   FARM_CROP_KIND[mix].seed 0.50 → 1.50（×3.00）、
                                 #   FARM_CROP_KIND[rare].seed 0.56 → 2.00（×3.57）；
                                 #   money/min/exp 与 FARM_CROP_BASE 一字不动 ⇒ 只改种植成本、不改产出。
                                 #   ★ 客户端半边 = V28_MODULES 'r115'（等阶需求原本已生效，客户端只补「恒显」）。
    # 2026-10-02 0.9.13 第 1 批接线（第 58~59 环 / 新末环；两环零锚区交集，按编号序挂链尾）：
    'srv_patch_r116.py',         # R-116 历练奇遇「抽奖券获取概率大幅压低」（服务端半边）：
                                 #   ADVENTURE_TIERS：紫档 bonusChance 0.15→0.01；金档 tickets 1→0 /
                                 #   bonusChance 0.35→0.02 / bonusTickets 2→1 ⇒ 0.0345→0.0009 券/抽（38.3x↓）。
                                 #   ★ 必须排在第 39 环 srv_patch_057.py 之后（锚含其「// [r057] 灵石 ×30」行尾注释）；
                                 #   ★ 客户端半边 = standalone 补丁 localtest/yl_r116_ext.py
                                 #     （build_v26n 装配层 STANDALONE_CLIENT 套用，非 V28_MODULES）。
    'srv_patch_r124.py',         # R-124 灵田种植 BUG（服务端半边）：
                                 #   FARM_CROP_ATTRS.zhuangguhua 去重复 defense 项（3 项→2 项）⇒ 服用不再双倍 +30；
                                 #   培元草防御 8 属凡品基准，数值一字不动。
                                 #   ★ 必须排在第 15 环 srv_patch_t5_crops.py 之后（锚是其 FARM_CROP_ATTRS 表），
                                 #     挂链尾满足；★ 客户端半边 = V28_MODULES 'r124'。
    # 2026-10-02 0.9.13 第 2 批接线（第 60~61 环 / 新末环；按编号序挂链尾）：
    'srv_patch_r122.py',         # R-122 仙务成就 4 档→10 档（服务端，纯服务端无客户端半边）：
                                 #   ACH_DEFS 20→50 行（五类通用灵石阶梯
                                 #   [500..50000]，单类 Σ=144,700）；ACH_REWARD_TIERS 系死常量不碰；
                                 #   境界组 metric 改 totalLevel=境界序×9+层（两端点就地补算）；
                                 #   claim 幂等占位/补偿逻辑一字不动；客户端零改动（/api/achievements 自然下发）。
                                 #   ★ 锚点全在基座段，recon 无既有补丁归属，任意位置可排，挂链尾。
    'srv_patch_r129.py',         # R-129 灵田纯灵石/纯修为收益大幅提升（服务端，纯服务端无客户端半边）：
                                 #   FARM_YIELD_MUL 1.85→1.0 + 新增 FARM_STONES_MUL=10（r047 stones 行改乘）+
                                 #   FARM_CROP_BASE expBase 5 档 → 对标打坐 2h（63,000..5,670,000）+
                                 #   EXP_PURE/EXP_MIX_ADJ 同步（ADJ 取对照表 {3:378000,4:1209600}，代决已录拍板）；
                                 #   种子价/时长/attr 三面一字不动（25 键逐键断言）。
                                 #   ★ 必须排在第 59 环 srv_patch_r124.py 之后（REQUIRES 断言 [r124attrfix]）；
                                 #   ★ r115「冻结 R-047 产出倍率」为当环基线计数（先于本环评估），保持绿。
    # 2026-10-02 0.9.13 第 3 批接线（第 62~64 环 / 新末环；按编号序挂链尾，锚全在基座/既有环段）：
    'srv_patch_r123.py',         # R-123 指引 8 步 + 七日礼奖励加码（服务端半边）：
                                 #   指引 8 步 reward 常量 + 七日 WEEK 表加码；REQUIRES 断言 guide/claim、
                                 #   week/claim 端点与幂等占位在位（本环零结构改动，改常量即全生效）。
                                 #   ★ 客户端半边 = STANDALONE_CLIENT 'r123'。
    'srv_patch_r127.py',         # R-127 每日一签四签档加码（服务端，纯服务端无客户端半边）：
                                 #   上上签 expRate .020→.030/stonesRate 4.0→6.0、上签 .010→.015/2.4→3.5、
                                 #   中签 .005→.008/1.4→2.2、下签 .002→.003/0.7→1.0（weight/赔率面不动）；
                                 #   FUN_SIGN_BASE=500 底数一行不动。
                                 #   ★ 锚在 srv_patch_fun086.py（环 5）段，挂链尾满足。
    'srv_patch_r128.py',         # R-128 掷骰翻牌扩档（服务端半边）：
                                 #   掷骰日次数 3→10、注额 1000~20000→2000~50000；翻牌日次数 2→10、
                                 #   成本 2000→4000、奖池 3 档→10 档 [0..54000]（EV=0.94≤1 铁律②）；
                                 #   赔率 1.95/25 与派彩逻辑一行不动；相对计数冻结（打前==打后）。
                                 #   ★ 锚在 srv_patch_fun086.py（环 5）段，挂链尾满足；
                                 #   ★ 客户端半边 = STANDALONE_CLIENT 'r128'。
    'srv_patch_r112.py',         # R-112 打坐/历练产出灵玉（服务端唯一实现，客户端半边=墓碑零改动）：
                                 #   POST /api/save UPDATE 分支按 Δmeditate/Δadventure roll 掉落
                                 #   （打坐 0.004/跳 < 历练 0.009/次），actDropTokens 发放
                                 #   （RATE=50 ⇒ 200石/玉；日上限 300 全复用既有通道）；纯插入零改基线行，
                                 #   E1 锚=e2Delta 定义行 / E2 锚=UPDATE 分支 tickWudaoIdle 行（均唯一），
                                 #   v2810 的 tickWudaoIdle==2 门禁保持绿（追加独立行不含该子串）。
                                 #   ★ 挂链尾满足（E2 锚在 srv_patch_v2810.py 段之后即可）；
                                 #   ★ patches/client/yl_r112_ext.py 已墓碑（apply() 即 AssertionError），禁接客户端。
    'srv_patch_r136.py',         # R-136B 新开局「普通秘境冷却 800+ 秒」根因修复（0.9.16 / 第 66 环）：
                                 #   根因 = dungeon_tracker.last_ts 有两个写入者，而 tickDungeonTracker
                                 #   （由 /api/save 差值驱动）在**任何历练/观测增量**下都无条件刷 last_ts
                                 #   ⇒ 没进过秘境的玩家 cdLeftMs 恒在 800~900 秒回满 ⇒ 普通秘境永远进不去。
                                 #   ① tickDungeonTracker 观测累加不再触碰 last_ts（ON CONFLICT 删该赋值 +
                                 #      VALUES 传 null；列清单/占位符数 6+2=8 一字不动）
                                 #   ② dungeonStatusView 的 cdLeftMs 加 `count > 0` 前置（兜底 0.9.15 前历史脏数据）
                                 #   ③ 修正上方已失效注释。rogue 半边（rogue_last_ts，只由 entry 写）零改动；
                                 #      /api/dungeon/entry 的读→判→写与 403/200 语义、DDL 全部不动。
                                 #   ★ 挂链尾：本环只改 r063 之后仍为原形态的两行，链上无后继环。
    'srv_patch_r144.py',         # R-144 真实在线玩家名单（0.9.20 / 第 67 环 / 新末环）：
                                 #   新增唯一端点 GET /api/online/players（真名单来源）。
                                 #   在线判据（用户 2026-10-03 23:20 拍板）= 最近 5 分钟内有活跃上报
                                 #   （ONLINE_WINDOW_MS = 5*60*1000）；
                                 #   双源 UNION 去重取 MAX(ts)：
                                 #     ① active_sessions.last_seen（客户端每 15s 心跳写，ms epoch，权威）
                                 #     ② saves.updated_at（存档兜底；SQLite CURRENT_TIMESTAMP 是 **UTC**
                                 #        ⇒ CAST(strftime('%s',updated_at) AS INTEGER)*1000 转 epoch）
                                 #   名字/境界口径与 /api/friends/list **逐字一致**
                                 #   （COALESCE(NULLIF(r.name,''),u.username) / REALM_ORDER_FOR_RANKING /
                                 #    level = realmIndex*9 + realmLevel）；响应含 isFriend / isSelf；
                                 #   新增幂等索引 idx_active_sessions_last_seen。
                                 #   锚点 = app.post('/api/friends/add', authenticateToken, 之前
                                 #   （好友域第一条路由，实测 count==1）；纯插入零改基线行。
                                 #   ★ 挂链尾：只**新增**端点/索引，不改任何既有语义。
                                 #   ★ 客户端半边 = STANDALONE_CLIENT 'r144'（localtest/yl_r144_ext.py）。
    'srv_patch_r148.py',         # R-148 修 0.9.20 回归：空库启动崩溃（0.9.21 / 第 68 环 / 新末环）：
                                 #   R-144 把 CREATE INDEX idx_active_sessions_last_seen 写成
                                 #   **模块加载期顶层语句**，早于 db.serialize 块内的
                                 #   CREATE TABLE active_sessions ⇒ 全新/空库启动即
                                 #   SQLITE_ERROR: no such table: main.active_sessions（unhandled
                                 #   'error' 直接退出）。线上库因表已存在未暴露；本机沙盒全废。
                                 #   修法 = 把该索引语句**移入建表块内**、紧跟 active_sessions 的
                                 #   CREATE TABLE 之后（语义等价，仅执行时机后移）。
                                 #   锚点①（删除处）= 顶层那句 count==1；锚点②（插入处）= 建表整块 count==1。
                                 #   ★ 挂链尾：纯时机修正，端点/字段/口径零改动。
                                 #   ★ 客户端零改动（本批客户端仅版本号 0.9.21）。
    'srv_patch_r149.py',         # R-149 修「挂机收益恒 0」（0.9.22 / 第 69 环 / 新末环）：
                                 #   away（POST /api/session/presence）旧口径无条件把 last_seen_at
                                 #   前移到「本行当前 updated_at」；而客户端在线时每 10s 心跳存档会刷新
                                 #   updated_at ⇒ 玩家登录后只要「切走一次再切回」（visibilitychange
                                 #   hidden→visible / pagehide / 刷新）就产生一对 away/back，把**尚未领取**
                                 #   的离线窗口压成几十秒 < OFFLINE_MIN_MS(5min) ⇒ /api/offline/report 恒 0。
                                 #   客户端只在打开「挂机收益」面板时才取报告 ⇒ 玩家根本来不及领。
                                 #   修法 = away 分支：若存在未领取窗口（last_seen_at 有效且 >
                                 #   offline_claimed_until），保持较早锚点 min(last_seen_at, updated_at)；
                                 #   否则照旧前移。领取过之后行为逐位不变。
                                 #   锚点①（替换处）= away 分支整块 count==1。
                                 #   ★ 挂链尾：offlineRewards()/offlineWindow()/offlineAnchor()/OFFLINE_*
                                 #     常量/月卡判定/入账钳制 **一行未动**，端点与响应结构零改动。
                                 #   ★ 客户端零改动（本批客户端仅版本号 0.9.22）。
    'srv_patch_r160.py',   # R-160 离线结算时长上限按境界递增：基准 8h->24h(练气1层) + 每层 +1h + 月卡 x1.5（第 70 环）
    'srv_patch_r163.py',   # R-163 灵田数值重定档：种子 3000 起 / 卖钱草净赚收敛 / 其余净亏换修为（第 71 环）
    'srv_patch_r165.py',   # R-165 打坐顿悟点联动悟道心得：新增免费端点 POST /api/wudao/enlighten（第 72 环）
                           #   · 复用既有 wudaoAddExp(...,'idle') 与 wudaoDaoGateRealm；零新表 / 零新列 / 零改既有端点
                           #   · 三层 rateLimit（5s 最小间隔 / 小时 60 / 日 200）复用既有 rateLimit()（429，非 401/403）
                           #   · 客户端半边 = STANDALONE_CLIENT 'r165'（打坐顿悟分支挂一次 YlxwPost）
                           #   · ★ 锚点 = /api/wudao/insight 路由行（0.8.x 起在位），与 r160/r163 锚区零交集
    # ---- 2026-10-06 0.9.26 批（R-167 喂养首免 + R-168 灵田重构 + R-170 成就重定档 + R-172 指引重定档
    #      + R-173 离线时长权威化；序=编号序，五环锚区经各自 REQUIRES/EDITS 实证零交集）----
    'srv_patch_r167.py',   # R-167 仙务·妖灵「喂养」当日首次免费：新建 pet_feed_log + 单语句原子闸门
                           #   （第 73 环；★ 客户端半边 = STANDALONE_CLIENT 'r167'；REQUIRES [r165wudao]）
    'srv_patch_r168.py',   # R-168 灵田数值重构：sell 净赚恒 300/h + mix 回本(×1.10) + cult 修为重定档
                           #   15000/45000/150000/600000/3000000（第 74 环；R-169 结论留档于本环文件头）
    'srv_patch_r170.py',   # R-170/R-171 成就奖励按需求次数正比重定档（每组首档 2000）（第 75 环）
    'srv_patch_r172.py',   # R-172 仙途指引奖励按「累计升级所需修为」重定档（Σ 60,000→105,500）（第 76 环）
    'srv_patch_r173.py',   # R-173 离线时长服务端权威化：新增 saves.last_active_at + res.on('finish') 打点
                           #   （60s 节流），offlineAnchor 加可选第 6 参、老行逐位回落（第 77 环）
    # ---- 2026-10-06 0.9.28 批（R-175 万妖巢穴逐只榜；★ 锚区与 r173 零交集）----
    'srv_patch_r175.py',   # R-175 万妖巢穴「五只同现」排行榜改按每只 boss 单独计算（第 78 环 / 新末环）
                           #   · 新表 event_boss_hits5(event_id,boss_no,user_id,score,strikes) 逐只记分
                           #   · status 响应**向后兼容**新增 top10ByBoss（旧 top10 逐位不变）
                           #   · ★ 既有合计口径（event_boss_hits 建表/记分/结算/strike/talisman）逐字节未动（独立复核实证）
                           #   · 客户端半边 = STANDALONE_CLIENT 'r175'（读 top10ByBoss 逐只渲染 + 缺失回落）
                           #   · ★ 注意：R-176 的**服务端**环（srv_patch_r176.py，改奇遇抽品阶）经判定**越界**，
                           #     本批**不接线**（R-176 的真对象「抽奖券抽奖」是纯客户端，见 STANDALONE_CLIENT 'r176'）
    # ---- 2026-10-07 0.9.29 批（R-170 二环：成就境界组奖励重定档；★ 锚区与 r175 零交集）----
    'srv_patch_r170b.py',  # R-170 二环：成就「境界组」奖励重定档（第 79 环 / 新末环）
                           #   · 用户拍板「最顶级 = 1 亿，其他按等级设置」⇒ 等比数列：首档 2000（守 R-171）
                           #     → 末档 100,000,000，公比 r = 50000^(1/9) ≈ 3.3274（≈每档 ×3.33），Σ 249,470 → 142,904,450
                           #   · ★ 只改境界组 10 条 reward；修行/战斗/财富/任务 四组一行未动（用户「财富组先不压」）
                           #   · ★ target 一行未动 ⇒ 不影响玩家已有进度判定；发放式（reward 一律累加成灵石）未动
                           #   · 纯服务端环（客户端本批仅版本号 0.9.29）
    # ---- 2026-10-07 0.9.30 批（R-186 挂机收益恒 0；★ 锚区与 r170b 零交集）----
    'srv_patch_r186.py',   # R-186 离线挂机收益恒为 0（第 80 环 / 新末环）
                           #   · 根因 = R-173 的 offlineAnchor 在 last_active_at 分支**取错了窗口末端**：
                           #     `end = (r != null && r > a) ? r : nowMs`，其中 r=last_resume_at（客户端 back 写的，
                           #     只比服务端打点 a 晚 1~2 秒）⇒ 窗口 ≈1.4s < OFFLINE_MIN_MS(5min) ⇒ report 恒 hours=0。
                           #   · 更致命：ylTouchActive 用同一锚点判 pending ⇒ pending=false ⇒
                           #     `UPDATE saves SET last_active_at = now` ⇒ **真离线一整天的窗口被当场抹掉**。
                           #   · 线上铁证（同库天然对照）：user82 r-a=+1432ms ⇒ hours=0；user81 last_resume_at=NULL ⇒ 窗口≈12h（正确）。
                           #   · 修法（2 处）：① `end` 仅在 r-a >= OFFLINE_MIN_MS 时才用 r；② ylTouchActive 封口条件同步收紧。
                           #   · ★ 红线未动：offlineRewards/offlineWindow/offlineCapHours/offlineRatePerHour、OFFLINE_* 常量、
                           #     月卡判定、offline_claimed_until 幂等、presence 本体、report/claim 端点。
                           #   · ★ 客户端零改动（YlxwTOffline 只渲染 /offline/report 的字段，无本地计算）。
    # ---- 2026-10-07 0.9.31 批（R-182 纯卖钱草利润重定档；★ 锚区与 r186 零交集）----
    'srv_patch_r182.py',   # R-182 纯卖钱草利润重定档 + 催熟费同步抬高（第 81 环 / 新末环）
                           #   · 用户原话：「3000灵石成本，卖只有3600太不合理了。这个要120分钟才能成熟，利润起码2W4。按这个标准给其他卖钱草也修改。」
                           #   · 定价逻辑 100% 在服务端 farmCropDefs()（客户端 bundle 无灵田数值表 ⇒ 改客户端=假修复）
                           #   · 5 条 k==='sell' 由 R-168 钉死「净赚恒 300/h」；本环改为「净利 = 成熟分钟 × 200」：
                           #     linggusi 120→变卖 27000 / ziwenlingdao 180→42000 / jinsuiteng 300→72000 /
                           #     xianyulian 480→120000 / shencangjinshen 720→192000（净利/h 全部 12000）
                           #   · ★ 种子价 / 成熟时长 / 服用修为(exp) **逐字不变**，只覆写 stones
                           #   · ★ 沿用 R-168 范式「另插 R182_FARM_TABLE 覆盖表」，不原地改带中文尾注的旧表
                           #   · ★ 用户拍板接受回收率 4.0~9.0（突破 R-168 的 1.5 红线）：灵田复利有界
                           #     （一块地 120 分钟才收一茬，7 块地 ≈84,000/h，与历练 ≈42,000/h 同量级）
                           #   · 催熟费 FARM_BOOST_COST_PER_MIN 100 → **300**（防催熟变刷钱口）：
                           #     设净收益 P=200×分钟、催熟费 C=rate×分钟，防刷钱 ⇔ C≥P ⇔ rate≥200；取 300 = 1.5×200
                           #     ⇒ 满周期催熟净额 = −0.5P（纯回收口，恢复 R-168 原则并留 50% 余量）
                           #   · ⚠️ 副作用：催熟费是**全局函数** ⇒ 该费率会同步抬高所有作物（含 mix/cult/rare）；
                           #     那几类本就亏本/为换修为，提价只是把回收口收紧，方向一致。
      # ---- 2026-10-08 0.9.34 批（R-189 第 2 批：主人加成 6% → 10%）----
      'srv_patch_r191.py',   # R-189 主人加成 6% → **10%**（第 82 环 / 新末环）
                             #   · 用户原话：「**①加成改到 10%**」
                             #   · 常量是唯一权威源：`const R018_CONVERT = 0.06;` → `0.10;`（改 1 处覆盖 4 个使用点 + 对外暴露）
                             #     自动跟随（一行未动）：r018SpiritBonus 的 4 个使用点、r018bSpiritBonus、GET /api/pet 的 convert
                             #   · ★ 不动**别的** 0.06：`:6455-6457 (1 + lv * 0.06)` 妖灵本体成长系数（3 处）、
                             #     `:5402 bonusChance: 0.06`、`:5680 0.06→0.006`（冻结针脚钉住）
                             #   · 红线未动：无新增 require( / 403 / setInterval / PRAGMA
                             #   · 配套客户端文案同步见 standalone `r189b`（4 处「6%」→「10%」）
      # ---- 2026-10-08 0.9.34 批（R-196 灵纹前 4 条重设）----
      'srv_patch_r196.py',   # R-196 灵纹前 4 条加成重设（第 83 环）
                             #   · 用户拍板：「**数值可以微改，属性要重新设置一下**」
                             #   · 锐纹 critRate .015 → **.02 + critDamage .08**（新增暴伤；暴伤原无占用，封顶 .8）
                             #   · 御纹 damageReduction .02 → **.03**；疾纹 dodgeRate .015 → **.02**；噬纹 lifeLeech .01 → **.02**
                             #   · ★ 后 2 条（蕴纹 expMul .30 / 天纹 ppMul .10）**逐字未动**（门禁冻结）
                             #   · ★ 放弃「防御%/身法%」副属性（量化：petSpirit.defense 仅 2~145，再 ×5% 且 floor ⇒ +0~7，可忽略）
                             #   · 配套客户端接线（新增 payload 键 runeCritDmg）见 standalone `r196`
      # ---- 2026-10-08 0.9.34 批（R-194 悟道十道均匀随机）----
      'srv_patch_r194.py',   # R-194 悟道「随机加一种道」（第 84 环 / 新末环）
                             #   · 用户原话：「这个触发要变成**随机加一种道**，而不是固定第一个」
                             #   · 取证：选道逻辑在服务端 :9023-9026，**本来就在随机**，但**只在「已开放的道」里随机**；
                             #     血道门槛=0 ⇒ 炼气期 pool=['pill'] 唯一 ⇒ 恒血道。客户端只 POST {}、不传道 ⇒ 纯客户端改永不生效。
                             #   · 方案 A：改为 `const dao = keys[Math.floor(Math.random()*keys.length)];` ⇒ 十道均匀（各 ≈10%）
                             #   · ★ 副作用（用户已认可）：低境界也会随机到稀有道心得（越过 R-110 手动门槛）
                             #   · 冻结：WUDAO_DAOS 10 key / WUDAO_DAO_REALM_GATE 10 门槛 / 端点其余逻辑（经验发放/日志/响应）逐字未动
      # ---- 2026-10-08 0.9.35 批（R-198 免费玩法：免费进食每日 3 次 + 买额度 5 次）----
      'srv_patch_r198.py',   # R-198 妖灵「免费玩法」服务端支持（第 85 环 / 新末环）
                             #   · 用户原话：「在『培养（出口：妖灵之力 PP）』加一栏『免费玩法』，里面放一个免费进食的按钮，
                             #     喂食度一次加 100，一日 3 次，冷却 30 分钟……买额度改成 5 次，3 个选项共用 5 次上限」
                             #   · 买额度：`R018_BUY_DAILY_MAX` 2 → **5**（「3 选项共用」本就成立，同一 bought 计数；闸门 SQL 一行未动）
                             #   · 免费进食：**复用 `pet_feed_log`** + 幂等加 2 列（`free_times` / `last_free_at`）
                             #     单语句原子闸门（照 R-167 口径）；**冷却与次数全在服务端判定**；+100 走既有结算
                             #     ⇒ 天然守「喂食度 9999 / 99 级」上限与「跨 10 级妖灵精魄」；失败回退时清冷却
                             #   · 返回体带 `freeFeed:{used,left,cdLeftMs,max,cdMs}`；`consts` 补 3 字段
                             #   · ★ 旧「当日首次免费」（R-167）**逐字保留**（在 else 分支），两套免费机制独立共存
                             #   · 红线未动：无新增 require( / 403 / setInterval / PRAGMA（safeAddColumn 为既有幂等加列）
      # ---- 2026-10-08 0.9.36 批（R-192 去掉 R-167 当日首免 + R-193 渡劫门槛与客户端曲线对齐）----
      'srv_patch_r200.py',   # R-192 移除 R-167「当日首次免费」喂养（第 86 环）
                             #   · 用户原话：「R-167『当日首次免费』这个去掉，前面有专门的免费档了」
                             #   · 删 4 段：else 头 / 首免闸门（`INSERT … SET times = times + 1 WHERE times < 1`）/ 回退闭包 else / catch 三目 times 半
                             #   · ★ R-198 的免费闸门（free_times/last_free_at）与它的回退**逐字保留** —— 两者同处一个 if/else，只拆 else 里 R-167 那半边
                             #   · ★ 不动：pet_feed_log 建表 / times 列 / free_times·last_free_at 列 / feedQuota 回显（避免多造门禁冲突）
                             #   · ★ else 头紧贴裸中文注释 ⇒ 无法整段删 else，只能把 `} else {` 收成 `}`（语义等价）
      'srv_patch_r201.py',   # R-193 服务端渡劫门槛与客户端曲线对齐（第 87 环 / 新末环）
                             #   · 问题：0.9.30（R-183）给客户端曲线乘了 K=[14,6,4,2.5,1.5,1,1]，服务端 TRIB_REALM_BASES/realmMaxExp 没跟上
                             #     ⇒ 渡劫 expOk 用旧门槛 ⇒ 客户端显示「还差很多」时服务端可能已判满
                             #   · 改法：新增 TRIB_REALM_R183_K（与 TRIB_REALM_BASES 同序同字，未知境界 ??1 兜底）+ realmMaxExp 返回值再乘 K
                             #   · 炼气期第 3 层 = 60000×(1+2×0.24)×14 = 1,243,200（与客户端一致）；长生境 K=1 ⇒ 改后=改前
                             #   · ★ 连带修正：realmMaxExp 还给离线重算当单次收益上限（advEach/killEach/srEach）。
                             #     客户端 _ylExpCap = 0.25×ad(...) 而 ad() 含 K ⇒ 改前服务端比客户端紧约 138 倍（炼气期），
                             #     注释写的「÷10 同源」从未成立、会误杀合法离线收益；乘 K 后第一次真正成立 ⇒ 属修正非放松
                             #   · ★ 刻意不动 arenaTrialMaxExp（走另一张表 ARENA_TRIAL_REALMS，有意不复用 realmMaxExp）
      # ---- 2026-10-08 0.9.39 批（R-198 心法改「点一次加经验」）----
      'srv_patch_r207.py',   # R-198 心法六卷改「点一次加经验」（第 88 环 / 新末环）
                             #   · 用户原话：「心法学习也变成点一次增加经验，不要每次升一级，并且大幅度提高点一次所需的灵石数量」
                             #   · 关键：`player_gongfa.exp` 语义本就是「累计投入灵石」+ `gongfaLevelFromExp()` 已存在
                             #     ⇒ 把「扣满整级价 → level+1」改成「扣按档单价 P → exp += P → level 由 exp 反推」，无需新字段
                             #   · **C 方案**（三条约束不可全兼得，优先「点一次加经验」）：阈值表 ×7.5、单价按档 = 现状档位 ×2.5
                             #     ⇒ 每档点击数恒为 3.000（十档全等）；满级 528,000 → 3,960,000（×7.5）
                             #   · 上限 GONGFA_MAX_LEVEL=100 / 六卷 key 集合 / 表结构 一律未动
]

# ---- 前端产物路径（0.9.31 换名：index-v2931-20261007.js，与 build_v26n.py OUT 逐字一致）----
CLIENT_OUT = os.path.join(ROOT, 'build', 'assets', 'index-v2943-20261009.js')
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
        # 服务端补丁模块（srv_patch_*.py）已收进 patches/server/；SRV_CHAIN 仍存裸文件名
        src_py = os.path.join(ROOT, 'patches', 'server', mod)
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
