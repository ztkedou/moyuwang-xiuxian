# DEPLOY LOG — 《摸鱼修仙传》 0.9.14 (v28.12)

- 部署时间：2026-10-02 **19:06** (GMT+8)（systemd swap 时刻 19:06:42；备份戳 `20261002_190621`）
- 目标：香港 VPS `47.243.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2811.sh`（客户端 + 服务端 + CHANGELOG + index.html bump；本轮已就地升版 v2914）
- 定点核对：`deploy_v28/remote_check_v2811.sh` → **PASS (0 failures)**（部署时 262 OK / 0 FAIL / 0 WARN；
  CHANGELOG 时刻校准重传后**终态复跑再 PASS**）
- 登记指纹：`deploy_v28/EXPECT_0811.env`（已升版 0.9.14）
- 备份整包：`/root/backup/yl_pre_v2914_20261002_190621.tar.gz`
- DB 一致性快照：`/root/backup/database_v2914_consistent_20261002_190621.sqlite`（VACUUM INTO ok，node sqlite3 驱动；远端无 sqlite3 CLI/better-sqlite3）+ 热拷贝 `database.sqlite.pre-v2914-20261002_190621`
- 执行方式：升版部署员（zcode 动态工作流单步），发布 0.9.14 装配终态
  （装配终测证据：zcode 记忆库 work-2026-10-02-0.9.14接线装配R132R112.md；沙盒 s14 三场景 ALL-PASS =
  work-2026-10-02-0.9.14沙盒端到端三场景.md；装配 git `5e1fe08`）

---

## 1. 本批范围：0.9.14（R-132 + R-112；客户端 95 模块 + standalone 11 脚本；服务端 64→65 环）

| # | 需求 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-132 | 建角天赋金红互换 + 种类梯度重排（8 点档 10 枚每枚 6~7 种、6 点档 13 枚收入 3~5 种、23 枚说明重写、每枚总当量冻结） | standalone `yl_r132_ext`（第 11 个 standalone，排 r131 后） | ✔ | — |
| R-112 | 打坐/历练产出灵玉（打坐 0.004/跳、历练 0.009/次，命中 1 玉；Δ 差值 roll + 时间钳 + actDropTokens 日上限 300；负 Δ/首存/坏基线不 roll） | `srv_patch_r112`（SRV_CHAIN 第 65 环 s65/r112） | —（客户端零改动，墓碑勿接） | ✔ |

**EV 红线**：本批零赔率/零抽奖池改动（T5 EV 红线 3 条 OK，装配已验）。
**服务端新 DDL**：无（R-112 复用 `activity_token` / `activity_token_daily` / `events` 既有表）。
**版本铁律四件套**：bundle 名 `index-v2914-20261002.js` / CHANGELOG `[0.9.14] - 2026-10-02 19:06`（×2 份）/
本 DEPLOY_LOG / topics「当前版本」段回写（收尾已完成）。

## 2. 指纹（部署前后）

| 对象 | 0.9.13（部署前） | 0.9.14（部署后） |
|---|---|---|
| `www/assets/index-v2913-20261002.js` | `b4586dba4943bf62cc4ca818af31fb66` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2871-20260929.js` | `f0f31f5b88ba3f0f502cf14c071cb008` | 同左（0.8.7.1 热修，更早的回滚点） |
| `www/assets/index-v2914-20261002.js` | —（新文件） | **`e3760e1ec536e5e04760d1bfd84dc069`**（2,278,139 B / 95 模块+11 standalone） |
| `server/index.ts` | `77c705ec1035c91eedd7b9eb7dde824e`（64 环） | **`9033c805be1022e692bc67f7ccc3b1ae`**（979,955 B / **65 环**，+3,411 B） |
| `www/CHANGELOG.md` | `765738fa4362f1f0b56af7feab21a844` | **`ee1e6508c09474eba3f2a0e1513ebdb0`**（条目头时刻 18:00→19:06 校准后重传） |
| `www/CHANGELOG_PLAYER.md` | `c3de670587429f4ae0124c41a7317956` | **`89b4fc05f7dd287c1a01bba97a10f637`**（补 [0.9.14] 玩家向条目） |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批未动） |

部署后线上实测（deploy step 4 采集 + 时刻校准重传后复核）：

```
9033c805be1022e692bc67f7ccc3b1ae  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
ee1e6508c09474eba3f2a0e1513ebdb0  /opt/yl/www/CHANGELOG.md      # 19:06 校准后重传
89b4fc05f7dd287c1a01bba97a10f637  /opt/yl/www/CHANGELOG_PLAYER.md
e3760e1ec536e5e04760d1bfd84dc069  /opt/yl/www/assets/index-v2914-20261002.js
```

本机独立 curl 复核（不经部署脚本）：`https://moyuwang.online/myxxz/assets/index-v2914-20261002.js`
= **200 / 2,278,139 B / `e3760e1ec536e5e04760d1bfd84dc069`** —— 与本地交付产物**逐位一致**；
公网 `/myxxz/` 首页引用 `index-v2914-20261002.js`；`/myxxz/CHANGELOG.md` 200。

## 3. 部署前本地验收（升版后亲跑）

升版清单（0.9.13→0.9.14 部署面全部出现处）：`deploy_v2811.sh`（BUNDLE/OLD_BUNDLE/CHAIN_TAIL(s65.r112.ts)/
PREV_×3/备份命名 v2914/头注）、`remote_check_v2811.sh`（包名两写法/OLD_BUNDLE/PREV_×2/index.html 断言/
CHANGELOG [0.9.14] 断言/版本号段 0.9.14+0.9.13 清零/**新增 0.9.14 特征点 11 条**）、
`sim_remote_check.py`（$B → v2914）、`EXPECT_0811.env`（全量重登记）、`CHANGELOG_PLAYER.md`（补 0.9.14 条目）。
（客户端/装配面升版已由装配环节完成：`yl_version_ext` 两处常量 + 0.9.13 清零门禁、`build_v26n.OUT`、
`chain_build.CLIENT_OUT`、`dryrun_087` 两常量、`build/index.html`、`CHANGELOG.md`；git `5e1fe08`。）

- `localtest/sim_remote_check.py` → **OK=197 / SKIP=11 / FAIL=0**（0.9.13 时 186+10 → +11 OK/+1 SKIP，数目吻合：
  新增 R-132 客户端 5 条 + R-112 服务端 4 条 + R-112 客户端零改动 1 条 + 0.9.13 清零 1 条；SKIP +1 = CHANGELOG [0.9.14]）
- `deploy_v2811.sh --dry-run` → step 0/0c 全门禁绿：CHANGELOG_PLAYER 格式 46/46、每版本都有 ### 分类、
  CHANGELOG [0.9.14] gate OK、EXPECT 五项 md5 全符、canon==srv==EXPECT、client base 未换、
  **交付 bundle==预演产物（e376…，铁律 12/13）**、链尾 s65.r112.ts==srv（9033…）、s20==0.8.9 定版（前 20 环不变）
- 装配侧既有证据（本环节未重跑，引用）：dryrun 4241+266 门禁 FAIL=0；`chain_build --all` 65 环 `node --check` rc=0；
  沙盒 s14：R112-API-SMOKE ALL-PASS（正命中 balance 32→48 / 负Ω不扣 / 首存不 roll）+ R132-UI-SMOKE ALL-PASS
  （仙品红/史诗金/8点卡 6~7 种全红/6点卡 3~5 种全金）+ server.log 0 错误

## 4. 线上验收

- `deploy_v2811.sh` → rc=0；**REMOTE-CHECK: PASS (0 failures)**；备份戳 `20261002_190621`
- 远端未漂移断言（step 0b 全过才动线上）：index.ts=`77c705ec…` / 线上包=`b4586dba…` / 0.8.7.1=`f0f31f5b…`（三者与 0.9.13 定版逐位一致）
- 六件 `.pre-v2914-20261002_190621`（index.ts / game-dicts.json / index.html / CHANGELOG.md / CHANGELOG_PLAYER.md / index-v2913 包）+ DB 热拷贝 + **VACUUM INTO ok** + 整包 tar.gz
- 服务端链：上传 `.new` md5 校验 → `node --check` PASS → maintenance on → 原子 swap → restart → maintenance off；
  `yl-server` **active** / **NRestarts=0** / maintenance absent
- **journalctl 19:06 后 error/exception/fatal = 0 行**
- 公网冒烟：首页 **200**｜`/yl/` **301**（预期）｜新包 **200**｜旧包回滚点 **200**｜0.8.7.1 **200**｜CHANGELOG **200**｜
  teahouse/fun-dice/pet-merge 等 no-token 全 **401**（判活正确）
- 线上库 dbcheck：8 活动表 + sects.join_mode + pets 三列 + gm_sessions.expires_at / users.muted_until 全部落库 OK
- **CHANGELOG 时刻校准**（先例流程）：装配预估 `18:00` → 实际 swap `19:06`；两份 CHANGELOG 重传 +
  `EXPECT_CHANGELOG_MD5` cb9df7bd→`ee1e6508…` 重登记 + remote_check **终态复跑 PASS (0 failures)**；
  远端头部实测 `## [0.9.14] - 2026-10-02 19:06`
- **生产注册冒烟：本轮未跑**（不在本环节指令六步内）。R-112/R-132 的功能证据 = 装配阶段沙盒 s14
  API+UI ALL-PASS + remote_check 特征门禁 11 条全绿；高境界/掉率类项沿用「代码级断言替代」口径如实标注。
  （0.9.13 生产冒烟账号 `ylv2913smoke1`/uid=76 保留未动。）

## 5. 本轮踩到的新坑

1. **CHANGELOG_PLAYER.md 装配侧没有 0.9.14 条目**（装配只写了 CHANGELOG.md）——deploy step 0 的格式门禁
   只查格式不查「最新版本在不在」，静默漏网。部署面补写玩家向条目（### 玩法与平衡 / ### 体验优化）后重传。
   ⇒ 升版清单应加第五处：`CHANGELOG_PLAYER.md`。
2. **remote_check 的版本号断言有两处**：「0.8.11 A 组」段 1 条 + 「版本号」段 1 条，升版两处都要同步；
   旧版清零断言在版本号段滚动追加（本批加 0.9.13 清零）。
3. **EXPECT_CHANGELOG_MD5 两段式**：部署前登记预估时刻的 md5（fail-closed 门禁可用），swap 后按实际时刻
   修条目头 → 重传两份 → 重登记 → remote_check 复跑。0.9.12/0.9.13/0.9.14 三连踩同款流程，已熟练。
4. deploy_v2811.sh 头部/模板的历史注释（0.8.11/0.9.0 文案）与现状脱节，功能无影响；DEPLOY_LOG 模板仍是
   0.8.11 内容 ⇒ 本文件为全量重写（非模板补空）。
5.（继承提醒）`check_srv_087.py` 两处失效未修（--strict 环查找路径 + 7 条存量断言）；GitHub staging 仍在 0.9.13
   （ba122457），**0.9.14 未同步**。

## 6. 残留清理

- 远端 `_remote_check_v2811.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` 留在 `/opt/yl/server/` 便于复跑。
- 本地 `_deploy_v2914_out.txt`（部署全程输出，工作区根）留档；`%TEMP%` 一次性脚本已删。
- 沙盒 s14 仍留跑（装配阶段为复核保留，`http://127.0.0.1:3214/myxxz/`）；旧包 `index-v2913-20261002.js` 保留不删（回滚点）。
- 冒烟账号无新增（本轮未跑生产注册冒烟）。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@47.243.x.x
cp -a /root/backup/index.html.pre-v2914-20261002_190621 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2914-20261002.js --to=index-v2913-20261002.js
cp -a /root/backup/index.ts.pre-v2914-20261002_190621        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2914-20261002_190621 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2914-20261002_190621    /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2914-20261002_190621 /opt/yl/www/CHANGELOG_PLAYER.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2913-20261002.js.pre-v2914-20261002_190621 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 0.9.13 定版：bundle=b4586dba4943bf62cc4ca818af31fb66  server=77c705ec1035c91eedd7b9eb7dde824e  CHANGELOG=765738fa4362f1f0b56af7feab21a844
# 整包：/root/backup/yl_pre_v2914_20261002_190621.tar.gz
```

★ **回滚语义**：本批零 DDL、零新列、零新端点。R-112 发放走既有 `activity_token`/`activity_token_daily` 行，
回滚到 0.9.13 后旧代码不读新增发放量（余额照显、不再增长），无需数据还原；如需完全还原用
`/root/backup/database_v2914_consistent_20261002_190621.sqlite`。
★ R-132 为纯客户端改动，回滚 index.html 指回旧包即彻底还原。

## 8. 0.9.14 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=e3760e1ec536e5e04760d1bfd84dc069      # index-v2914-20261002.js（2,278,139 B）
PREV_SRV_MD5=9033c805be1022e692bc67f7ccc3b1ae         # srv/index_v28.ts（979,955 B / 65 环）
PREV_CHANGELOG_MD5=ee1e6508c09474eba3f2a0e1513ebdb0
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S20_MD5=7780e099a6cd1ac0de4b502c467ae2c0     # 0.8.9 定版 s20.t16arena.ts（前 20 环不变）
PREV_SRV_S65_MD5=9033c805be1022e692bc67f7ccc3b1ae     # 0.9.14 链尾 s65.r112.ts（= 整包 65 环）⇒ 供 0.9.15 单变量可核
```

## 9. 下一批留意

- **`OLD_BUNDLE` 推进到 `index-v2914-20261002.js`**（= 线上 index.html 当前引用）；`CHAIN_TAIL` 从 `_chainstage/s65.r112.ts` 起算（下一环 = s66）
- **升版 `yl_version_ext.py` 记得两处**：`DEFAULT_VERSION` + `INJECT_JS` 字面量；下一批滚动加「旧兜底 0.9.14 已清零」门禁
- **CHANGELOG_PLAYER.md 升版清单第五处**（本批新坑 §5.1）
- remote_check 版本号段两处同步 + 旧版清零滚动（§5.2）
- `check_srv_087.py` 遗留未修（§5.5）；GitHub staging 待同步 0.9.14；沙盒 s14 记得 down
- R-132 报告观察项（拍板文件命名用需求真实编号）已转达：本批拍板文件命名即按 R-132/R-112 真实编号
