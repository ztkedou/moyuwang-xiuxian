# DEPLOY LOG — 《摸鱼修仙传》 0.9.22

- 部署时间：`2026-10-06 00:44` (GMT+8)
- 目标：**Azure East Asia 新机 `104.208.x.x`（HKVPS）** / `https://moyuwang.online/myxxz/`
  - ★ 本批是 **2026-10-05 zcode 全量迁移后的首次发布**（旧港机 `47.243.x.x` 已退役）
- 脚本：`deploy_v28/deploy_v2822.sh`（服务端 + 客户端 + CHANGELOG + index.html bump）
- 定点核对：`deploy_v28/remote_check_v2822.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0822.env`
- 备份整包：`/root/backup/yl_pre_v2922_20261006_004251.tar.gz`
- DB 一致性快照：`/root/backup/database_v2922_consistent_20261006_004251.sqlite`（5,869,568 B，sqlite3 `VACUUM INTO`）

---

## 1. 本批范围：0.9.22 = R-149「离线挂机收益恒为 0」

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-149 | 离线挂机收益恒 0（away 丢弃未领取窗口） | 服务端第 69 环 `srv_patch_r149.py` | —（仅版本号） | ✔ |

### 1.1 现象
玩家**离线两天后上线**，打开「挂机收益」面板，收益恒为 **0**（一分不给）。

### 1.2 根因（服务端 `POST /api/session/presence` 的 `away` 分支）
旧口径把 `last_seen_at := 本行当前 updated_at`。而客户端**在线时每 10s 心跳存档**会把
`updated_at` 刷成「现在」⇒ 只要产生一对 away/back，离线窗口就被压没：

```
窗口 = [ max(last_seen_at, offline_claimed_until), last_resume_at ]
```

- 客户端上报 `away` 的时机包含 `visibilitychange→hidden`、`pagehide`、`beforeunload`
- 于是「**登录 → 切走一次（或刷新一次）→ 切回**」就会：
  1. `last_seen_at` 被前移到「现在」（← 根因）
  2. 紧接着 boot 定时器上报 `back`，`last_resume_at` 也设为「现在」
  3. 窗口被压成**几十秒** < `OFFLINE_MIN_MS`（5 分钟）⇒ `GET /api/offline/report` 恒 0

★ **更致命**：上一个**尚未领取**的离线窗口会被这一对事件**永久丢弃**——
而客户端只在「打开挂机收益面板」时才 `GET /api/offline/report`，
所以玩家**根本来不及领**，窗口就没了。

### 1.3 修法（1 处精确替换，零新端点 / 零新表 / 零新列）
`away` 分支：若存在**尚未领取**的待结算窗口
（`last_seen_at > 0` 且 `> offline_claimed_until`，或 `offline_claimed_until` 非法/为空），
则保持**较早**的锚点 `anchor = min(last_seen_at, updated_at)`；否则照旧前移。

语义：`away` 只表示「此刻离开」，**不得**把一段还没结算的离线时长作废。
领取过（`offline_claimed_until` 已覆盖旧锚点）后，锚点照常前移 ⇒ 正常玩法**逐位不变**。

★ **红线（一行未动）**：`offlineRewards()`（expGain/stoneGain 公式）、`offlineWindow()` 本体、
`offlineAnchor()` 本体、`OFFLINE_*` 常量、月卡判定、入账与钳制逻辑。

### 1.4 三重硬证据（迁移无罪 + 真凶锁定）
| # | 证据 | 内容 |
|---|---|---|
| ① | **迁移快照对账** | `opt-yl_sqlsnap_20261004` 里 `user_id=13` 的 `last_seen_at = 2026-10-03 07:04:53Z`（= 本地 15:04:53，正是「两天前」）⇒ **迁移没有破坏状态**，锚点本来是健康的 |
| ② | **线上库现状** | `last_seen_at = 2026-10-05 15:52:39Z`、`last_resume_at = 2026-10-05 15:53:14Z`（相隔 **35 秒**）⇒ 被今天的一次 away/back 冲掉 |
| ③ | **nginx access.log** | `23:52:42 presence` → `23:53:14 presence` → `23:53:49 GET /api/offline/report` → **0** |

### 1.5 沙盒 A/B/反向对照（★ 单变量可核，本批核心证据）
在**本机全栈沙盒**（`localtest/sandbox.sh`，idx=5）里，用同一个账号跑三段：

| 服务端形态 | 场景 A（健康基线） | 场景 B（**再发一次 away+back**） |
|---|---|---|
| **未修复**（`_chainstage/s68.r148.ts` = 0.9.21 定版） | `hours=8` / `claimable=true` | **`hours=0` / `claimable=false`** ← **100% 复现** |
| **已修复**（`srv/index_v28.ts` = `s69.r149.ts`） | `hours=8` / `claimable=true` | **`hours=8` / `claimable=true`** ← **修好** |
| **换回修复版**（复跑确认） | `hours=8` / `claimable=true` | **`hours=8` / `claimable=true`** |

- 场景 A 造数：`last_seen_at = 2 天前`、`updated_at = CURRENT_TIMESTAMP`、`last_resume_at`/`offline_claimed_until` = NULL
- 场景 B = A 之后再 `POST /api/session/presence {state:'away'}` → `{state:'back'}` → 再 `GET /api/offline/report`
- 关键观测量：修复后 `after_back_db.last_seen_at` **仍是 2 天前那个值**（未被前移）；
  未修复时它被改写成「现在」
- 证据文件：`localtest/_r149_result_{unfixed,fixed,fixed_restored}.json`、`localtest/_r149_*.log`

## 2. 指纹（部署前后）

| 对象 | 0.9.21（部署前） | 0.9.22（部署后） |
|---|---|---|
| `www/assets/index-v2921-20261004.js` | `d15800ffb6575fa3325ab5760f2c3f82` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2920-20261003.js` | `8ad857ffb547c8747f17c88a4638be9b` | 同左（0.9.20 定版，更早的回滚点） |
| `www/assets/index-v2922-20261005.js` | —（新文件） | `e9c74146e02c9ba638cb0357ef5ed0c7` |
| `server/index.ts` | `847618c70f965621417ee4611ba41340` | `479dcc66a3261c98254367c1cab0f416` |
| `www/CHANGELOG.md` | `0afbec85e32d2a88ab92405099d77b28` | `814c16ecc3039e91f987306b5ac1316f` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批不变） |

部署后线上实测（`deploy_v2822.sh` 采集 + 外部独立复核）：

```
479dcc66a3261c98254367c1cab0f416  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
814c16ecc3039e91f987306b5ac1316f  /opt/yl/www/CHANGELOG.md
e9c74146e02c9ba638cb0357ef5ed0c7  /opt/yl/www/assets/index-v2922-20261005.js
d15800ffb6575fa3325ab5760f2c3f82  /opt/yl/www/assets/index-v2921-20261004.js   （旧包保留 = 回滚点）
index.html -> assets/index-v2922-20261005.js
systemctl is-active yl-server = active   （NRestarts = 0）
/run/yl-maintenance = absent
```

**★ 外部独立复核（不走部署脚本，单独 ssh + curl）**
- `away` 分支源码段 md5（线上）`942360a68f4317c656dd55210faea1f6` == 本地交付产物同段 md5 ⇒ **修复逐字节上线**
- 线上 `grep -c '[r149anchor]'` = **1**；旧的「无条件前移」语句 `grep -c` = **0**
- 公网冒烟：`index.html` 200 / `/yl/` 301 / 新包 200 / 旧包 200 / `CHANGELOG(.PLAYER).md` 200
- 公网 API（无 token）：`GET /api/offline/report` 401、`POST /api/session/presence` 401、
  `POST /api/offline/claim` 401、`GET /api/teahouse/today` 401、`POST /api/fun/dice` 401、
  旧前缀 `GET /yl/api/offline/report` 401 ⇒ 路由全活
- 线上 `index.html` 指向 `assets/index-v2922-20261005.js`；线上 CHANGELOG 头 = `## [0.9.22] - 2026-10-06 00:44`（两份一致）

## 3. 部署前本地验收

- `localtest/chain_build.py --all` ⇒ **69/69 环全绿** + `node --check rc=0`
  - 链尾 `_chainstage/s69.r149.ts` = `479dcc66a3261c98254367c1cab0f416`（983,742 B，较 s68.r148.ts **+975 B**）
  - `srv/index_v28.ts` == 链尾 == `_chainstage/index_v28.v28112.ts`（三文件逐字节 IDENTICAL）
  - `s20.t16arena.ts` == `7780e099a6cd1ac0de4b502c467ae2c0`（== 0.8.9 定版 ⇒ 前 20 环不变，单变量可核成立）
- `localtest/dryrun_087.py` ⇒ **门禁结果: PASS（FAIL=0）** + standalone **622 条 FAIL 0**
  - 「预演==交付」：`_chainstage/dryrun_087.bundle.js` md5 == `build/assets/index-v2922-20261005.js` md5 == `e9c74146e02c9ba638cb0357ef5ed0c7` ✔
- `localtest/sim_remote_check.py --script deploy_v28/remote_check_v2822.sh` ⇒ **OK=366 / SKIP(远端专有)=15 / FAIL=0**
  （较 0.9.21 的 OK=356 / SKIP=14 **新增 10 条 R-149 断言**）
- **沙盒端到端 A/B/反向对照** ⇒ 见 §1.5（修复前 `hours=0`，修复后 `hours=8`）

## 4. 线上验收

- `deploy_v28/remote_check_v2822.sh` ⇒ **PASS (0 failures)**
  - 含 0.8.1~0.8.11 全量回归 + 0.9.x 回归 + **R-149 新断言 10 条** + 服务健康 + 线上库核对
  - 线上库核对：0.8.7 的 8 张新表 + `sects.join_mode` + 0.8.9 的 `pets` 三列 +
    0.8.11 的 `gm_sessions.expires_at` / `users.muted_until` + `idx_active_sessions_last_seen` 全部在位
- 公开冒烟（`https://moyuwang.online/myxxz/`）：
  - `index.html` = 200；`/yl/` = 301 → `/myxxz/`；新包 = 200；旧包（回滚点）= 200
  - 无 token 端点 = 401（含 POST/DELETE 路由用 `-X POST` / `-X DELETE` 探）
- 服务：`systemctl is-active yl-server` = `active`；`/run/yl-maintenance` = absent
- **线上库核对**：本批**零 DDL**（无新表 / 无新列 / 无新索引）⇒ 只需确认 `saves` 表的
  `last_seen_at / last_resume_at / offline_claimed_until` 三列仍在，且修复后
  「away 不再把 `last_seen_at` 前移」在真实流量里生效（观察下一个 away 事件前后的列值）

### 4.1 线上库现状（只读诊断，非破坏性）

部署后对线上 `saves` 表做**只读**导出（`sqlite3` 只读连接 + 逐行复算窗口）：

| uid | `last_seen_at`(UTC) | `last_resume_at`(UTC) | `offline_claimed_until` | 窗口 | claimable |
|---|---|---|---|---|---|
| 13（ztkedou） | 2026-10-05 16:24:22 | 2026-10-05 16:24:22 | null | 44 ms | **no** |
| 76 | null | null | null | — | YES（但 `max_exp` 为 0 ⇒ 收益 0） |
| 80（测试账号） | 2026-10-03 01:22:50 | 2026-10-03 01:22:50 | null | 874 ms | **no** |

★ **重要说明（写给玩家本人看）**：uid 13 的 `last_seen_at` 被**修复上线之前**（2026-10-06 00:24:22）
的那一对 away/back 冲成了 44 毫秒 —— 这段「两天没上线」的窗口是**修复前就已经丢掉的**，
修复**不会追溯**把它还回来。

修复后的行为：`last_seen_at` 从此**不再**被 away 前移 ⇒
下一次登录触发 `back`（`last_resume_at := now`）后，窗口会从 `last_seen_at` 重新长起来
（例：若 00:24:22 后再次登录，窗口 ≈ 登录时刻 − 00:24:22，超过 5 分钟即可领取）。
⇒ **玩家自己再登录一次就能看到收益恢复**；若希望把被吞掉的那两天补回来，
需要**单独把 `last_seen_at` 回拨**（属数据操作，未在本批自动执行）。

## 5. 本轮踩到的新坑

### 5.1 生成部署脚本：**版本号「整版位移」会把新块改坏**（第三次踩，务必固化）
`_mk_2822.py` 初版照 `_mk_2821.py` 的「先整块替换、再整版位移」顺序写，
但本批**新块**（HDR/DIFF/VAR/MD5）里已经写好了本批的 `0.9.22` 与「更早回滚点 `0.9.20`」，
再做 `0.9.20→0.9.21` / `0.9.21→0.9.22` 的整版位移会把这些**正确文案改坏**
（例：`# 0.9.21 已上线定版指纹` 会被改成 `0.9.22 已上线定版指纹`）。
⇒ 改为**只对「新块之外」的 8 个点逐个点名替换**（abort 文案 / 漂移文案 / 线上在跑注释 /
更早回滚点注释 / 日志表格 / 回滚注释 / 收尾 echo ×2）。
另：`deploy_v2821.sh→deploy_v2822.sh` 的全局改名会**误伤 DIFF 首行**
「`# 与 deploy_v2821.sh 的差别：`」⇒ 需要一步回修。

### 5.2 换机后 **SSH 私钥文件名里仍含旧 IP**，改名会直接连不上
`~/.ssh/ali-hk-47.243.x.x.key` 是**新机 root 也已授权**的同一把公钥。
`_mk_2822.py` 里替换 `root@47.243.x.x` → `root@104.208.x.x` 时
**必须只替换 `root@` 形态与裸 IP 文案**，绝不能碰 key 文件名（本脚本用断言锁死 count=5）。

### 5.3 沙盒 `sandbox.sh up` 默认用**冻结基座**，不会自动用 `srv/index_v28.ts`
跑 R-149 这类**服务端**改动时，必须显式 `--srv=srv/index_v28.ts`，
否则你测的是旧服务端（`f6ecc82e…`），结论无意义。

### 5.4 后台任务结束会**回收 node 子进程** ⇒ 沙盒必须「起服 + 验收」写在**同一条命令**里
单独一条命令 `sandbox.sh up` 跑完就退出，服务随之被杀，下一条命令探测会拿到连接拒绝。

### 5.5 本机 python `urllib` 走系统代理 ⇒ 探 `127.0.0.1` 得 **502**
必须显式 `urllib.request.build_opener(urllib.request.ProxyHandler({}))` 绕过代理，
否则 localhost 请求会被代理拦成 502（假故障）。

### 5.6 `MSYS_NO_PATHCONV=1` 会**破坏** sandbox.sh 里的 harness 路径（不要图省事加它）

## 6. 残留清理

- 远端保留（便于复跑）：`/opt/yl/server/_remote_check_v2822.sh`、`_remote_swap.sh`、`_live_bump_bundle.js`
- 本地新增（不发布）：`_mk_2822.py`、`_mk_rc2822.py`、`deploy_v28/deploy_v2822.sh`、
  `deploy_v28/remote_check_v2822.sh`、`deploy_v28/EXPECT_0822.env`
- 沙盒证据（保留）：`localtest/_r149_*`

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2922-20261006_004251 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2922-20261005.js --to=index-v2921-20261004.js
cp -a /root/backup/index.ts.pre-v2922-20261006_004251        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2922-20261006_004251 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2922-20261006_004251    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2921-20261004.js.pre-v2922-20261006_004251 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版（0.9.21）：bundle=d15800ffb6575fa3325ab5760f2c3f82  server=847618c70f965621417ee4611ba41340
# 整包：/root/backup/yl_pre_v2922_20261006_004251.tar.gz
```

★ 回滚注意：本批**零 DDL**（无新表 / 无新列 / 无新索引），
⇒ 回滚**无需任何数据库操作**，旧代码读同一份库完全兼容。
（唯一差别是 `away` 会不会前移 `last_seen_at` —— 回滚后旧行为恢复，数据无损坏。）

## 8. 0.9.22 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=e9c74146e02c9ba638cb0357ef5ed0c7      # index-v2922-20261005.js
PREV_SRV_MD5=479dcc66a3261c98254367c1cab0f416         # s69.r149.ts（69 环）
PREV_CHANGELOG_MD5=814c16ecc3039e91f987306b5ac1316f
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S69_MD5=479dcc66a3261c98254367c1cab0f416     # 链尾（供 0.9.22 单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把 0.9.22 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段（**并把「新家 = Azure 104.208.x.x」写进头部**）。
