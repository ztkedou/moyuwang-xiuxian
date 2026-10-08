# DEPLOY LOG — 《摸鱼修仙传》 0.9.21 (v2921)

- 部署时间：2026-10-04 02:00 (GMT+8)
- 目标：香港 VPS `47.243.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2821.sh`（**服务端链重建批**：客户端 + 服务端 + CHANGELOG + index.html bump；**不可加 `--skip-server`**）
- 定点核对：`deploy_v28/remote_check_v2821.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0821.env`
- 备份整包：`/root/backup/yl_pre_v2921_20261004_015954.tar.gz`（44,481,844 B）
- DB 一致性快照：`/root/backup/database_v2921_consistent_20261004_015954.sqlite`（5,447,680 B，VACUUM INTO）
  ＋ 热拷贝 `/root/backup/database.sqlite.pre-v2921-20261004_015954`（7,094,272 B）

---

## 1. 本批范围：0.9.21（客户端 95 模块 + standalone 27 脚本；服务端 67 → **68 环**）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-148 | **修 0.9.20 回归**：R-144 把在线索引写成模块加载期顶层语句 ⇒ **全新 / 空数据库启动即崩**。修法 = 把该 DDL 原样挪进建表块内 | 服务端新末环 `patches/server/srv_patch_r148.py` | —（零功能改动） | ✔ |

### 1.1 回归根因（R-148）

0.9.20 的 R-144 新增了一条幂等索引：

```js
db.run('CREATE INDEX IF NOT EXISTS idx_active_sessions_last_seen ON active_sessions(last_seen)');
```

它被写在**模块加载期顶层**，而 `CREATE TABLE active_sessions` 在 `db.serialize(() => {...})` 块内 ——
Node 侧 `db.run()` 是**同步入队**、SQLite 侧**顺序执行**，于是顶层那句排在建表**之前**：

- **线上库**：`active_sessions` 表早已存在 ⇒ 不报错，问题被掩盖（0.9.20 上线时无人发现）；
- **全新 / 空库**：表不存在 ⇒ `SQLITE_ERROR: no such table: main.active_sessions`
  ⇒ unhandled `'error'` ⇒ **进程直接退出**（不是 500，是整个服务起不来）。

**发现路径**：本机全栈沙盒（pristine 库 `<LOCAL>/Temp/yl_srv_merge/work/database.sqlite.pristine`
共 63 表，**恰好缺 `active_sessions`**）在 0.9.20 批后**全部起不来**：
`Server running on port 3105` 之后紧接 `[Error: SQLITE_ERROR: no such table: main.active_sessions` → `NOT READY`。

三组对照实验定性（2026-10-04 01:3x，全部指向「全新空 sqlite」）：

| 变量 | 结果 |
|---|---|
| 0.9.20 服务端（`s67.r144.ts`） | **崩**（no such table: main.active_sessions） |
| 0.9.19 服务端（`s66.r136.ts`） | 正常启动，84 表 |
| 删掉那句顶层 `db.run` | 正常启动，84 表 |
| 把该句**移入建表块内** | 正常启动，84 表 **且索引就位** |

★ 另记一条反直觉结论：**「在顶层行前面插一个 `CREATE TABLE active_sessions`」无效** ——
`tables` 数已到 68 但进程仍崩。说明 `db.serialize()` 的队列语义比直觉复杂，
**只有「挪进建表块」才可靠**。这也是最终采用的修法。

### 1.2 R-148 服务端面（本批唯一改动）

- 删除顶层那句单引号 `db.run('CREATE INDEX IF NOT EXISTS idx_active_sessions_last_seen ...');`；
- 在 `active_sessions` 的 `CREATE TABLE` 之后（`db.serialize` 块内）补回同一条 DDL，
  形态 = **6 空格缩进 + 反引号**：
  ```js
        db.run(`CREATE INDEX IF NOT EXISTS idx_active_sessions_last_seen ON active_sessions(last_seen)`);
  ```
- 语义**一字不改**：零新端点、零新表、零新列、零 ALTER。索引标识符全局计数仍为 **1**（不重不漏）。
- 幂等标记：`[r148boot]`（块头注释）。

### 1.3 R-148 客户端面

**零功能改动** —— 仅版本号 `YLVERSION_FALLBACK` 由 `"0.9.20"` 改为 `"0.9.21"`（+ CHANGELOG 条目）。
V28_MODULES 95 模块、standalone 27 脚本均未增删。

### 1.4 顺带闭环：R-112（灵玉阁「我的灵玉」不再恒 0）

R-112 的代码修复早在 **0.9.15**（2026-10-02 23:02）就已上线（tab C 改读 `d.jadeBalance`），
台账里一直挂在「进行中」，差的是**一次生产验收复跑**。本批补跑并闭环（详见 §4.3）。

## 2. 指纹（部署前后）

| 对象 | 0.9.20（部署前） | 0.9.21（部署后） |
|---|---|---|
| `www/assets/index-v2921-20261004.js` | —（新文件） | `d15800ffb6575fa3325ab5760f2c3f82`（2,299,359 B） |
| `www/assets/index-v2920-20261003.js` | `8ad857ffb547c8747f17c88a4638be9b` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2919-20261003.js` | `c02350f26d1d65c35e1640748901a466` | 同左（0.9.19 定版，更早的回滚点） |
| `server/index.ts` | `4c3a3eea75ca8f11be18b5c0c2127dd1`（982,652 B） | `847618c70f965621417ee4611ba41340`（982,767 B，**+115 B**） |
| `www/CHANGELOG.md` | `3003b55624e64fe0d45f996feba99725` | `0afbec85e32d2a88ab92405099d77b28` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批不变） |

部署后线上实测（deploy_v2821.sh 采集）：

```
847618c70f965621417ee4611ba41340  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
0afbec85e32d2a88ab92405099d77b28  /opt/yl/www/CHANGELOG.md
d15800ffb6575fa3325ab5760f2c3f82  /opt/yl/www/assets/index-v2921-20261004.js
```

★ 公开面**独立复核**（不依赖部署脚本自检，curl 直取）：

```
index.html             -> 200   （引用 assets/index-v2921-20261004.js）
新 bundle              -> 200   md5 = d15800ffb6575fa3325ab5760f2c3f82  ← 与 EXPECT 逐字节一致
旧 bundle（0.9.20）    -> 200
更早（0.9.19）         -> 200
YLVERSION_FALLBACK     = "0.9.21"
CHANGELOG 头部         = ## [0.9.21] - 2026-10-04 02:30
```

## 3. 部署前本地验收

| 门禁 | 结果 |
|---|---|
| `localtest/dryrun_087.py` | **PASS**（门禁 FAIL 0 + standalone **622** 条 FAIL 0） |
| 「预演 == 交付」双 provenance（step 0c） | 通过：`_chainstage/dryrun_087.bundle.js` 与交付产物**逐字节 IDENTICAL** = `d15800ff…` |
| 链单变量可核 | `s20.t16arena.ts == 7780e099a6cd1ac0de4b502c467ae2c0`（前 20 环 == 0.8.9 定版）；`s67.r144.ts == 4c3a3eea…`（== 0.9.20 定版） |
| `localtest/sim_remote_check.py --script deploy_v28/remote_check_v2821.sh` | **OK=356 / SKIP=14 / FAIL=0** |
| 服务端链重建 | `chain_build.py --srv`：67 → **68 环**；`s68.r148.ts == canon _chainstage/index_v28.v28112.ts == srv/index_v28.ts`（三文件同 md5） |
| `node --check srv/index_v28.ts` | rc=0 |
| 沙盒 s5 端到端（`bash localtest/sandbox.sh up 5 --bundle=index-v2921-20261004.js --srv=$PWD/srv/index_v28.ts`） | **1s ready**；84 表 + `idx_active_sessions_last_seen` 就位（**R-148 真机复现通过**） |
| **完全空库启动**（`database.sqlite` 文件不存在） | 84 表 + 索引建好；`/api/market/items` = **200**、`/api/online/players` = **401**（端点存活） |

## 4. 线上验收

### 4.1 `remote_check_v2821.sh` → PASS (0 failures)

覆盖：指纹段 + index.html 引用/平台注入 + CHANGELOG 版本铁律② + 公开冒烟 +
判活探针（新端点 no-token 全 401）+ 0.8.1~0.9.21 全量特征点回归 + 服务健康 + 线上库核对。

新增的 **0.9.21 特征点段**（R-148）逐条 OK：

```
[OK  ] R148 服务端幂等标记                          x1  eq 1
[OK  ] R148 顶层建索引行已清零（回归根因）           x0  eq 0
[OK  ] R148 索引已移入建表块（6 空格缩进 + 反引号）   x1  eq 1
[OK  ] R148 建表语句未误伤                          x1  eq 1
[OK  ] R148 索引标识符总数 = 1（不重不漏）           x1  eq 1
[OK  ] R148 未误伤 R-144 端点                       x1  eq 1
[OK  ] R148 未误伤 R-144 在线窗口                   x1  eq 1
[OK  ] R148 未误伤 R-144 名字口径                   x33 ge 2
[OK  ] 客户端版本号 = 0.9.21                        x1  eq 1
[OK  ] 旧版本号 0.9.20 已清零                       x0  eq 0
[OK  ] 反向对照 R148 标记不在客户端                  x0  eq 0
```

### 4.2 服务健康 + 线上库

```
systemctl is-active yl-server = active ；NRestarts = 0 ；/run/yl-maintenance absent
db: idx_online yes
[OK  ] R-144/R-148 索引 idx_active_sessions_last_seen 已建（服务端确已启动过）
```

★ 本批**零新表、零新列、零 ALTER** —— 线上库核对沿用 0.8.7 的 8 表 + `sects.join_mode` +
0.8.9 的 `pets` 三列 + 0.8.11 的两列，全部 OK；索引核对确认真机已建。

### 4.3 R-112 生产验收复跑（本批顺带闭环）

`localtest/_verify_r112_jade.py`（Playwright 真机，三方一致性）：

```
=== R-112 结果: PASS 8 / FAIL 0 / NOTE 4 ===
[PASS] S1  ylt_mid 登录沙盒并进入主界面
[PASS] S2b 活动中心面板打开（含 灵玉阁 页签）
[PASS] S3  点击「灵玉阁」页签
[PASS] S5  接口 /activity/shop 返回 jadeBalance（拦截真值）  status=200 jadeBalance=137
[PASS] A1  面板显示值已抓取到且 != 0                          panel=137
[PASS] A2  面板显示值 == 接口 jadeBalance                    panel=137 api=137
[PASS] A3  复调接口 jadeBalance == 拦截真值                   refetch=137 api=137
[PASS] A4  面板显示值 == --expect(137)                       panel=137 expect=137
```

- 干净视觉取证：`localtest/shots/r112_jade_panel_20261004_015855.png`
  （活动中心 → 灵玉阁页签选中，面板显示「我的灵玉：**137**」，高价物品按钮为「灵玉不足」禁用态）。
- 首次复跑时 `A1` FAIL 的原因是测试号灵玉**恰为 0**（面板 0 == 接口 0，A2 已 PASS）；
  向沙盒 `activity_token(player_id=40, token_key='lingyu')` 注入 137 后四断言全绿。

## 5. 本轮踩到的新坑

1. **★★ 生成器「版本号 / v 字号整体位移」是本项目的反复踩坑点（0.9.20 记过一次，本批再犯）**。
   `_mk_2821.py` 用 `0.9.20→0.9.21 / 0.9.19→0.9.20 / 0.9.18→0.9.19` 全局位移，
   把两类**语义标签**改错（取值没错，纯注释，但回滚点标签标错很危险）：
   - 「本批 = 0.9.21」这类**当前批次**标签 ⇒ 位移后成 0.9.21，正确应为 **0.9.20**（上一版线上）；
   - 「= s68.r148.ts」这类**链尾**标签 ⇒ 位移后成 s68，而 `PREV_SRV_MD5` 实为 0.9.20 的 **s67.r144.ts**。
   **修法**：`_fix2821_labels.py` 逐处点名修回 **21 处**（取值零改动，`bash -n` 通过）。
   **新生成器 `_mk_rc2821.py` 改为纯精确 `rep()`、零位移**，并把该铁律写进脚本顶部。
   ⇒ **今后一律：所有精确 rep() 先做完；不要任何「整体位移」；末尾只断言不改写。**
2. **`remote_check_v2820.sh` 里 `OLD_BUNDLE` 是裸赋值**（`OLD_BUNDLE=index-v2919-...`），
   而 `deploy_v2820.sh` 里是 `OLD_BUNDLE="${YL_OLD_BUNDLE:-...}"` ⇒ 断言串不能跨文件照抄。
3. **`sim_remote_check.py` 的校验器本身有坑**：`PREV_*` 在 deploy 脚本里出现两次
   （变量块的真值 + 末尾 DEPLOY_LOG 模板的 `<待填>` 占位），用「后者覆盖前者」的字典解析会误报 FAIL。
   ⇒ 只取**变量块区间**（`deploy_v2821.sh` 的 L79~105）比对。
4. **沙盒 `up` 会让 Git Bash 管道挂住**（脚本自带说明）：前台 `| tail` 会吃 SIGTERM。
   必须 `> log 2>&1` 重定向，或整条链路（up → seed → 注入 → 验收）放在**同一次调用**里跑完 ——
   后台任务一结束，其子进程会被回收，沙盒随即失效。

## 6. 残留清理

远端脚本按惯例**留在 `/opt/yl/server/` 便于复跑**：

```
-rwxr-xr-x  61945  /opt/yl/server/_remote_check_v2821.sh
-rwxr-xr-x   2153  /opt/yl/server/_remote_swap.sh
-rwxr-xr-x   3612  /opt/yl/server/_live_bump_bundle.js
```

本地新增一次性脚本（保留供回溯）：`_mk_rc2821.py` / `_fix2821_labels.py` /
`localtest/_verify_r112_jade.py` / `localtest/_shot_r112_clean.py`。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@47.243.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2921-20261004_015954 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2921-20261004.js --to=index-v2920-20261003.js
cp -a /root/backup/index.ts.pre-v2921-20261004_015954        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2921-20261004_015954 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2921-20261004_015954    /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2921-20261004_015954 /opt/yl/www/CHANGELOG_PLAYER.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2920-20261003.js.pre-v2921-20261004_015954 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版（0.9.20）：bundle=8ad857ffb547c8747f17c88a4638be9b  server=4c3a3eea75ca8f11be18b5c0c2127dd1
# 整包：/root/backup/yl_pre_v2921_20261004_015954.tar.gz
```

★ 回滚注意：本批**零 DDL**（无新表 / 无新列 / 无 ALTER），
所以回滚到 0.9.20 **无需动库** —— `idx_active_sessions_last_seen` 索引留在库里无害
（0.9.20 的顶层 DDL 本身就是 `IF NOT EXISTS`，回滚后重启仍可正常建）。
唯一要注意的是**回滚到 0.9.20 会重新带回「空库启动崩溃」这个 bug** ——
若确实要回滚，请**只用 0.9.20 的客户端包 + 0.9.21 的服务端**（服务端无功能改动，跨版本兼容），
即：只 `live_bump` 回 `index-v2920-20261003.js`，**不要**还原 `index.ts`。

## 8. 0.9.21 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=d15800ffb6575fa3325ab5760f2c3f82
PREV_SRV_MD5=847618c70f965621417ee4611ba41340
PREV_CHANGELOG_MD5=0afbec85e32d2a88ab92405099d77b28
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S68_MD5=847618c70f965621417ee4611ba41340   # 链尾 s68.r148.ts（供 0.9.21 单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
