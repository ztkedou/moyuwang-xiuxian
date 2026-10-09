# DEPLOY LOG — 《摸鱼修仙传》 **0.9.43**（R-209 在线人数改我方口径）

- 部署时间：**2026-10-09 10:33 (GMT+8)**（= CHANGELOG `[0.9.43]` 条目头时刻）
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2843.sh`（**`--skip-server`**：纯客户端批、**零停机**）
- 定点核对：`deploy_v28/remote_check_v2843.sh` → **PASS (0 failures)**（540 OK / 15 SKIP(远端专有) / 0 FAIL）
- 登记指纹：`deploy_v28/EXPECT_0843.env`
- 备份整包：`/root/backup/yl_pre_v2943_20261009_103317.tar.gz`（六件 `.pre-v2943-20261009_103317` + DB 一致性快照）

---

## 1. 本批范围：0.9.43 = **1 条**（纯客户端批）

| # | 需求 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-209 | 顶部「在线 N」改为**我们服务器自己的口径**，与「在线人物」名单同源 | `localtest/yl_r213_ext.py`（客户端 r213） | ✔ | **零改动** |

### 根因（线上取证，非推测）

用户报：「yl 显示的在线 3，但点开之后只能看到我自己」。

1. **头部徽标**取自**外部 partykit**：`https://xiuxian-game-party.dnzzk2.partykit.dev/`
   的 WebSocket 房间 `global` 的 `onlineCount`。该地址**写死在上游仓库**
   （`_upstream-xiuxian/.env.production:VITE_PARTYKIT_HOST`、`hooks/useParty.ts:16`、`partykit.json:name`）
   ⇒ 我们 fork 时原样继承 ⇒ 它数的是**该 partykit app 的全部连接**（含上游作者部署与其它 fork 的玩家）。
2. **面板名单**取自**我们自己的服务端** `GET /api/online/players`
   （双源 UNION：`active_sessions.last_seen` ∪ `saves.updated_at`，窗口 5 分钟，`srv/index_v28.ts:10992`）。
3. **线上实测**（`database.sqlite`）：`active_sessions` 9 行中除 uid=13 外全部是 1~6 天前的僵尸行；
   `saves` 近 5 分钟有存档 1 行；复刻 `/api/online/players` 查询 = **1 人**。
   ⇒ **面板是对的，头部那个 3 是错的。**
4. **历史成因**：`yl_r144_ext.py` 的 docstring 自己写明这是「刻意取舍」——
   「header『在线 N』仍取 party 实时值 Dr（与徽章同源），名单人数取服务端 players.length」。本环取消该取舍。

### 改动（3 处锚点，纯客户端）

| # | 锚点 | 改法 |
|---|---|---|
| E1 | `let Gr=null,Li=[],Lr=[],Dr=0;` | 原样 + 注入 `YLOnlCur / YLOnlSet / YLOnlTick`：2s 首拉 + **20s 轮询** `YlxwGet("/online/players")`，写 `Dr` 并通知 `Lr` 订阅者 |
| E2 | `Dr=l.onlineCount,…`（`onlineCountUpdate` + `welcome` 两处） | → `Dr=YLOnlCur`（掐掉 party 的写入口） |
| E3 | `Gr.close(),Gr=null,Dr=0` | → `Gr.close(),Gr=null`（避免订阅者重挂载时闪 0） |

★ 只改「写 Dr 的值」，**不动** `Li`（welcome/聊天消息）与 `sendMessage` ⇒ **世界聊天功能零影响**。

### 安全边界
- 复用既有鉴权封装 `YlxwGet`（模块级 `function` 声明 ⇒ 提升）。`Xc` 在**无 token 时直接 throw
  "Not authenticated"、根本不发请求**；401 先 `pS()` 静默续期重试一次
  ⇒ 未登录时轮询**不会把玩家踢下线**（异常已被 catch 吞掉）。
- **无效响应守卫**：响应缺 `players` 且缺 `total` 时**不采纳**，保持上一次值（防端点异常把徽标打成 0）。
- 轮询 20s ≪ 服务端 `rateLimit` 60/min。

## 2. 指纹（部署前后）

| 对象 | 0.9.42（部署前） | 0.9.43（部署后） |
|---|---|---|
| `www/assets/index-v2943-20261009.js` | —（新文件） | **`374c68e8a7cd9809cb24e4f8992c5a3b`**（2,319,828 B） |
| `www/assets/index-v2942-20261008.js` | `8f3fa81066c374edd9eed60a904f8547` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2941-20261008.js` | `b0b6b771bbb3c89c186016438e7e8cf0` | 同左（更早的回滚点） |
| `server/index.ts` | `2f49c2a7bc1b7348c2732912afe968ff` | **同左（本批未动，仍 88 环）** |
| `www/CHANGELOG.md` | `d10a8f7e9450cfff3169762721b9f2f7` | **`39bd02f72c6d6df38eb907e4ee927e7b`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批不变） |

部署后线上实测（deploy_v2843.sh 采集）：

```
2f49c2a7bc1b7348c2732912afe968ff  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
39bd02f72c6d6df38eb907e4ee927e7b  /opt/yl/www/CHANGELOG.md
374c68e8a7cd9809cb24e4f8992c5a3b  /opt/yl/www/assets/index-v2943-20261009.js
```

## 3. 部署前本地验收（全绿）

| 层 | 手段 | 结果 |
|---|---|---|
| 1 门禁 | `yl_r213_ext.py` `gates()` | **14/14 PASS** |
| 2 语法 | `node --check` | PASS |
| 3 行为（真跑注入块，非字符串比对） | `_t_r213_beh.js` | **10/10 PASS**（party 覆盖防护 / 无效响应守卫 / 空名单归零 / `total` 兜底 / 值未变不重复通知） |
| 4 装配预演 | `dryrun_087.py` | **FAIL 0 / SA-FAIL 0**；`预演产物 md5 == 交付产物 md5`（`374c68e8…`） |
| 5 本地模拟远端核对 | `sim_remote_check.py --script deploy_v28/remote_check_v2843.sh` | **OK=540 / SKIP=15 / FAIL=0** |
| 6 独立浏览器复验（**子代理 ver-r209，含反向对照**） | 沙盒 s9 Playwright | **VERDICT: FIXED**（见 §5） |

## 4. 线上验收

- `remote_check_v2843.sh` → **REMOTE-CHECK: PASS (0 failures)**
- `systemctl is-active yl-server` = **active**；`NRestarts: 0`
- 公开冒烟：`/myxxz/` 200、新 bundle 200、旧 bundle 200（保留）、`/yl/` **301**、
  `api/*` 无 token **401**（含 POST 路由 `-X POST` 探活）、`CHANGELOG.md` 200
- **公网独立复核**（不依赖部署脚本结论）：
  - `curl https://moyuwang.online/myxxz/assets/index-v2943-20261009.js` → md5 **逐位 == 本地**
  - `index.html` → `assets/index-v2943-20261009.js`
  - `CHANGELOG.md` 头 = `## [0.9.43] - 2026-10-09 10:33`
  - bundle 内特征串：`YLXW_R213_V2943` ×1、`setInterval(YLOnlTick,20000);` ×1、
    `YLVERSION_FALLBACK = "0.9.43"` ×1、`Dr=l.onlineCount` **×0**、
    `xiuxian-game-party.dnzzk2.partykit.dev` ×1（冻结项，世界聊天仍在用）

## 5. 独立复验（ver-r209，含**反向对照**）

| 产物 | 徽标 | 面板标题 | 正文 N | 列表行数 | 服务端真值 |
|---|---|---|---|---|---|
| **新 v2943** | **3** | **3** | **3** | **3** | **3** ← 四者恒等 |
| 旧 v2942 | **5** | **5** | 3 | 3 | 3 ← 精确复现原 bug |

- 两次都 hook 到 party 原始帧 `{"type":"welcome","onlineCount":5}` ⇒ **新产物在 party 推 5 时徽标显示 3**
  （我方真值）—— 这是「徽标已改我方口径」最直接的证据。
- 回归：hook `window.WebSocket` 仍收到 `welcome` 帧 ⇒ **聊天通道未被我改坏**。
- 报告：`localtest/report_r213_ver.md`；脚本：`localtest/t_r213_online.py`。

## 6. 本轮踩到的新坑（重要，已写入 SKILL）

1. **★ 上游模块的 `gates()` 是「在本模块位置上跑的自检」，不是终态断言。**
   首轮我把 `R144·真名单来源已接`（`'/online/players'` ==1）改成 ==2、把
   `R207-timer count kept`（`setInterval(` ==15）改成 ==16 ⇒ **r144/r207 自己的 apply 当场 FAIL/ABORT**
   （那时 r213 还没套），整条 standalone 链断在 r144，后续全崩。
   **正确做法**：上游门禁保持原位期望值；终态断言交给下游模块，或用本仓既有的
   `RETIRED_TAG = '【已退役·终态专用】'` 机制（自检跳过、dryrun 终态复核）。
   本批给 **r207 补上了该机制**（r139 早有先例）。
2. **r144 的门禁 needle 过宽**（`'/online/players'`）⇒ 天然跨模块耦合。
   本批把 needle **收窄到 R-144 面板专属调用点** `YlxwGet("/online/players").then(function(d){recent=`，
   期望仍为 1 ⇒ **断言意图不变、耦合消失**。
3. **`sim_remote_check.py` 的 `FILE_MAP['$B']` 是硬编码的旧包名** ⇒ 不更新会拿旧包做模拟，
   产出「R209 标记 got=0 / 旧版本号 got=1」这类**全是假 FAIL**的结果。本批已更新为新包名。
4. **`BUNDLE_DATE` 跨天必须单独改**：它在 deploy/rc 里是**默认值**，不在「包名整名替换」的覆盖范围内。
   本批已加进生成器（`bdate` 计数 + `rep` 调用）并写进 `mk_deploy` 的 fail-closed 断言。
5. **rc 里存在「宽 needle」的既有 chk 会被本批合法改写**：
   `chk "$B" '/online/players' 'R144 真名单来源已接（服务端端点）' eq 1`。
   按 sim 的指引**按实际产物更新预期值 + 记入本日志**（不静默删断言）：needle 收窄 + 新增一条
   `R209 冻结·在线端点总引用数 == 2`。
6. **`deploy_v28/DEPLOY_LOG_*.md` 的自动模板是 0.8.11 时代的陈旧模板**（写着 s23/0.8.9 等），
   每次新批都会落一份错的。本批**已整份重写**；建议后续把模板本身更新到当前世代。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# 只回滚客户端（本批服务端未动，无需还原 index.ts / game-dicts.json）
cp -a /root/backup/index.html.pre-v2943-20261009_103317 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2943-20261009.js --to=index-v2942-20261008.js
cp -a /root/backup/CHANGELOG.md.pre-v2943-20261009_103317 /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原
# 纯静态回滚**不需要** restart；如需彻底：systemctl restart yl-server && systemctl is-active yl-server
# 0.9.42 定版：bundle=8f3fa81066c374edd9eed60a904f8547  server=2f49c2a7bc1b7348c2732912afe968ff
# 整包：/root/backup/yl_pre_v2943_20261009_103317.tar.gz
```

★ 本批**零 DDL、零数据行**（服务端一字未动）⇒ 回滚无数据面残留。

## 8. 0.9.43 定版指纹（供后续批次做 PREV）

```
PREV_BUNDLE_MD5=8f3fa81066c374edd9eed60a904f8547      # 0.9.42 index-v2942-20261008.js（更早回滚点）
PREV_LIVE_BUNDLE_MD5=374c68e8a7cd9809cb24e4f8992c5a3b # 0.9.43 index-v2943-20261009.js（线上在跑）
PREV_SRV_MD5=2f49c2a7bc1b7348c2732912afe968ff         # 未动，仍 88 环（= s88.r207.ts）
PREV_CHANGELOG_MD5=39bd02f72c6d6df38eb907e4ee927e7b
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S20_MD5=7780e099a6cd1ac0de4b502c467ae2c0     # 0.8.9 定版 s20.t16arena.ts（前 20 环不变）
```

## 9. 残留清理

- 远端 `/opt/yl/server/` 保留：`_remote_check_v2843.sh` / `_live_bump_bundle.js` / `_remote_gz_sync.sh`
  （便于复跑；与本仓 `deploy_v28/` 内容一致）。
- 本机沙盒（`localtest/sandbox.sh` idx=9）进程已停、目录 `<LOCAL>/Temp/yl_v28_sandbox/s9` 保留备查。
- 子代理在沙盒库里留下的测试账号数据随沙盒一起弃用（未触碰线上库）。
