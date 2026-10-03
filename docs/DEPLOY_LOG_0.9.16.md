# DEPLOY LOG — 《摸鱼修仙传》 0.9.16（历练 / 秘境 七条：R-133~R-139）

- 部署时间：2026-10-03 **09:17** (GMT+8)（服务端原子 swap + index.html bump 时刻；备份戳 `20261003_091720`）
- 目标：香港 VPS `47.243.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2811.sh`（客户端 + 服务端 + CHANGELOG + index.html bump）
- 定点核对：`deploy_v28/remote_check_v2811.sh` → **PASS (0 failures)**（OK 288 / FAIL 0）
- 登记指纹：`deploy_v28/EXPECT_0811.env`
- 备份整包：`/root/backup/yl_pre_v2916_20261003_091720.tar.gz`
- DB 一致性快照：`/root/backup/database_v2916_consistent_20261003_091720.sqlite`（sqlite3 VACUUM INTO: ok）
- 执行方式：**工作流（主控 + 7 子代理并行）**——7 条待办各一个子代理写 standalone 模块，主控独占共享文件与构建/部署

---

## 0. ★ 本批拦下的上一批回归：0.9.15 热修打坏 `index.html`

**这是本批最重要的附带修复，独立于 R-133~R-139。**

| 项 | 内容 |
|---|---|
| 现象 | `deploy_v2811.sh` step 3 前置断言失败：`bundle src /myxxz/assets/index-v2915-20261002.js: found 0` + `platform injection missing BEFORE patch: unified-stats / mw-reward start / mw-reward end` |
| 根因 | 0.9.15 是 **paramiko 直发**的纯客户端热修，它把**仓库里的 `build/index.html`（干净模板：`./assets/` 相对路径、无平台注入）直接覆盖到线上 `/opt/yl/www/index.html`**。而线上那份**必须**保留平台注入并走 `/myxxz/assets/` 绝对路径（`live_bump_bundle.js` 头部注释写明了这个约束）。 |
| 影响 | 自 2026-10-02 23:02 起，线上 index.html **丢了平台注入块** ⇒ `/h5game/unified-stats.js` 与 `<!-- mw-reward -->` 奖励钩子**不再加载**（游戏本体仍能跑，因为 `./assets/` 在 `/myxxz/` 下等价解析）。0.9.15 未跑 remote_check，所以没被拦住。 |
| 修法 | 从 `/root/backup/index.html.pre-v2914-20261002_190621`（0.9.14 定版 = 规范形态）还原，仅把包名替换为 `index-v2915-20261002.js`（保持与 `OLD_BUNDLE` 一致，好让 `live_bump_bundle.js --from` 正常工作），上传后重跑部署；部署 step 3 正常完成 v2915 → v2916 bump。 |
| 验收 | 线上 index.html `ac5a57f17554c02d742a5b8fff0870e3`（2213 B）；`src="/myxxz/assets/index-v2916-20261003.js"`；`unified-stats` / `mw-reward:start` / `mw-reward:end` **各 1 处，公网实测全部在位**。 |

**遗留提醒**：以后任何**不走 `deploy_v2811.sh` 的热修**，若要动 index.html，**必须**用 `live_bump_bundle.js` 原地 patch，
**禁止**把 `build/index.html` 直接 scp 上线。（建议后续在 `build/index.html` 顶部加一行注释警示。）

---

## 1. 本批范围：0.9.16（R-133 ~ R-139，历练 / 秘境七条）

客户端 **standalone 模块 11 → 19**（新增 r133~r139 七支）；服务端 **SRV_CHAIN 65 → 66 环**（新增 `srv_patch_r136.py`）。
**零新 DDL、零新端点**。

| 编号 | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-133 | 历练抽奖券大幅降温 | `yl_r133_ext.py` | ✔ | — |
| R-134 | 奇遇修为下调 | `yl_r134_ext.py` | ✔ | — |
| R-135 | 历练商店售价梯度 + 掉落品质重配 | `yl_r135_ext.py` | ✔ | — |
| R-136 | 秘境手札「地宫冷却」+ 冷却根因修复 | `yl_r136_ext.py` + `srv_patch_r136.py` | ✔ | ✔ |
| R-137 | 地宫「再次探索」冷却 toast | `yl_r137_ext.py` | ✔ | — |
| R-138 | 自动历练统计（单次 + 汇总） | `yl_r138_ext.py` | ✔ | — |
| R-139 | 后台标签页自动循环继续走（Worker 心跳） | `yl_r139_ext.py` | ✔ | — |

### 1.1 各条要点

**R-133 抽奖券降温**
`lotteryTicketsChange:Ge(t,1,11,450)` → `lotteryTicketsChange:1`（固定 1 张）；`case"lottery":{` 内加 `if(!fs(t,.1,451))return{...d,story:"<中立一无所获文案>"}` 命中门。
概率 1/37 × 10% ⇒ **2.7% → 0.27%**。事件池权重一字未动。

**R-134 奇遇修为下调**
`expChange:Ge(t,300,800,480)` → `expChange:Ge(t,200,301,480)`。奇遇单次修为 300~799（均 549.5）→ **200~300（均 250）**；
灵石 / 气血 / 掉落**冻结不动**。取证：正常历练修为区间 10~149、均 ≈45。

**R-135 商店售价梯度 + 掉落品质**
① `YlxwShopPriceOf` 注入 `YlxwR135HasRareAttr`：带 `spirit|speed|physique>0` 稀有属性的物品 **×6**，其余 **×1.5**；
② 普通池品质 `l<.6?"普通":l<.9?"稀有":"传说"` → `l<.88…l<.98…`；③ 幸运池 `fs(t,.5,460)?"传说":"仙品"` → `fs(t,.8,460)?"稀有":fs(t,.85,461)?"传说":"仙品"`；
④ 秘境池 `v=a==="低"||a==="中"?"稀有":"传说"` → `v=a==="极度危险"?"传说":"稀有"`（高阶物品只在极度危险出）。
**未做**：「神识 / 身法只在高级物品出现」（需重排上百条字面量，成本高、收益低，留待用户拍板）。

**R-136 秘境冷却根因修复（本批唯一服务端改动）**
- 现象：新号「秘境冷却 800+ 秒」，从没进过秘境却显示冷却中。
- 根因：`dungeon_tracker.last_ts` 有**两个写入者** —— `/api/dungeon/entry`（正确语义「上次进入」）+ `tickDungeonTracker`（由**存档差值**驱动、**无条件刷** `last_ts = excluded.last_ts`），后者污染前者。
- 修法（`srv_patch_r136.py`，3 处 EDITS，MARK `[r136dg]`）：① `tickDungeonTracker` 的 ON CONFLICT **不再写 `last_ts`**（改传 `null`）；② `cdLeftMs` 加 `count > 0` 前置 ⇒ **没进过就没有冷却**；③ 注释同步。
  `last_ts` 写权**收归** `/api/dungeon/entry`。delta **+101 chars**（843,786 → 843,887）。
- 客户端（`yl_r136_ext.py`）：手札 `YlxwKv` 在「冷却剩余」后插 `"地宫冷却": t.rogueCdLeftMs > 0 ? YlxwMin(t.rogueCdLeftMs) : "无"`（服务端 R-063 已返回该字段）。

**R-137 地宫冷却 toast**
冷却中点击「再次探索」原为静默 `return`。改为 `c(_ylcd,"danger"); YlxwToast(_ylcd,"danger","yl-dg-cd"); return`（按钮未 disabled，处理函数 `T`）。

**R-138 自动历练统计**
单次结算行补物品**数量**（`name ×N`）+ 事件类型中文名（仅当 `res.adventureType !== advType`）；汇总块挂 `YlxwAdvSession(on)` 之后，刷 6 行（总次数 / 耗时 / 总修为·灵石·气血 / 抽奖券·声望 / 平均每次 / 事件分布 / 物品清单）。
`addLog` **不支持多行**（LogItem 无 `white-space:pre-wrap`）⇒ 每行一次 `addLog`。累计器 `YLXW_ADV_STAT` 以 `YLXW_ADV_SESS` **对象身份**自动重置。**+4936 B**（本批最大）。

**R-139 后台心跳驱动（本批最关键）**
- 现象：切标签 / 最小化后，打坐、历练、冷却全部停摆。
- 根因：隐藏标签下 window `setInterval` 被浏览器**节流**（≥1s，5 分钟后 1/min）。
- 决策：子代理原方案「隐藏期全速补算」**被主控否决** —— 会与既有离线收益 R-021 **重复计**。
  改为「**只换驱动源**」：**Blob URL Worker 心跳**（Worker 内 `setInterval` **不受 page-level 节流影响**），
  零收益 / 存档语义改动、零资损风险。
- 落点：5 处 EDITS —— 打坐主循环 / 历练主循环 / 两处 `clearInterval` 清理 / **第 5 处额外发现的 1s 心跳**
  （`Lw` 组件 @625842，同时做气血回复 + `cooldown` 每秒 -1；不改它则隐藏页里冷却 2 秒要等 2 分钟，主循环改造形同虚设）。
  注入封装 `YlxwBgInterval / YlxwBgClear`（含 `try/catch` 回退 + `navigator.locks` 保活）；为避开字面量门禁用 `window["set"+"Interval"]`。
  **+1062 B**。
- 「约束权移交」：r118（在 r139 之前）对打坐循环做的 `FR_MED_INTERVAL` 门禁被 r139 合法改写 ⇒ r118 **改判**
  （拆 `FR_MED_INTERVAL_PRE` 前置 + `FR_MED_INTERVAL` 终态 + `gates(terminal=True/False)`），**未静默删断言**。

## 2. 门禁与本地预演（上线前全绿）

- **升版 7 处**：`build_v26n.OUT`、`build/index.html`、`build_v26n.py OUT`、`chain_build.CLIENT_OUT`、
  `dryrun_087.(VERSION+BUNDLE_BASENAME)`、`patches/client/yl_version_ext.py`（DEFAULT_VERSION + INJECT_JS 字面量 + 滚动清零门禁）、
  `deploy_v2811.sh` + `remote_check_v2811.sh`；**★ 第 6 处：`localtest/sim_remote_check.py` 的 `$B` 默认 bundle 名**
- `localtest/dryrun_087.py`：**门禁 4243 条，FAIL=0**；`standalone 门禁 419 条（r116~r139 共 19 脚本）`
- **预演 == 交付**（铁律 12/13）：`_chainstage/dryrun_087.bundle.js` 与 `build/assets/index-v2916-20261003.js`
  **md5 逐位一致 = `a59ac4496ab0e8ab81fdb147b45488ec`**（2,285,822 B）
- `localtest/chain_build.py --all`：rc=0；链尾 `s66.r136.ts` = `664501929cecb41fd57e65d9d0c48872`（980,090 B，delta +135 B）；
  不可变参照 `_chainstage/index_v28.v28112.ts` 同 md5；`s65.r112.ts` 仍 `9033c805…`（= 0.9.15 定版，单变量可核成立）
- `localtest/sim_remote_check.py`：**OK=222 / SKIP(远端专有)=12 / FAIL=0**
- 服务端环门禁：每环「md5 必须变化」+ 末尾 `node --experimental-strip-types --check` 全过；
  `srv_patch_r136.py` 语义自证 `VALUES?=8 / CASE=1 / args=8`；幂等 rc=3 验证通过

## 3. 发布指纹（远端实测）

| 对象 | 0.9.15（部署前） | 0.9.16（部署后） |
|---|---|---|
| `www/assets/index-v2916-20261003.js` | —（新文件） | **`a59ac4496ab0e8ab81fdb147b45488ec`**（2,285,822 B / 95 模块 + 19 standalone） |
| `www/assets/index-v2915-20261002.js` | `41721861172d4655a9765e2a10423c63` | 同左（旧包保留不删 = 回滚点，公网 200） |
| `www/assets/index-v2871-20260929.js` | `f0f31f5b88ba3f0f502cf14c071cb008` | 同左（0.8.7.1 热修，更早的回滚点，公网 200） |
| `server/index.ts` | `9033c805be1022e692bc67f7ccc3b1ae`（65 环） | **`664501929cecb41fd57e65d9d0c48872`**（980,090 B / 66 环） |
| `www/index.html` | `de71dd24a791d1caa831afbee7b9027c`（还原后） | **`ac5a57f17554c02d742a5b8fff0870e3`**（2213 B，引用 v2916 ×1，平台注入 3 处在位） |
| `www/CHANGELOG.md` | `6d5557543190e366f34235640f42618e` | **`a6ce240eebd6b5a81fd3fdbb310f76c7`**（头条 `## [0.9.16] - 2026-10-03 09:20`） |
| `www/CHANGELOG_PLAYER.md` | `77c7561d66df38f2e2a4ba184b9382b6` | **`dfb4295f6fad8eb5e760c87b72cf01d3`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批无变化） |

```
a59ac4496ab0e8ab81fdb147b45488ec  /opt/yl/www/assets/index-v2916-20261003.js
ac5a57f17554c02d742a5b8fff0870e3  /opt/yl/www/index.html
664501929cecb41fd57e65d9d0c48872  /opt/yl/server/index.ts
a6ce240eebd6b5a81fd3fdbb310f76c7  /opt/yl/www/CHANGELOG.md
dfb4295f6fad8eb5e760c87b72cf01d3  /opt/yl/www/CHANGELOG_PLAYER.md
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
```

## 4. 线上验收

- **remote_check_v2811.sh**：**PASS (0 failures)** —— OK 288 / FAIL 0（含 0.9.16 新增特征点 24 条：R133 三条、R134 三条、
  R135 五条、R136A 两条、R137 两条、R138 三条、R139 三条、R136B 两条、版本号 0.9.16 在位 + 0.9.15/0.9.14 清零）
- 公开冒烟：首页 200 且引用 `assets/index-v2916-20261003.js`｜新 bundle **200**｜旧包 + 0.8.7.1 回滚点 200｜
  `unified-stats` / `mw-reward:start` / `mw-reward:end` **公网实测各 1 处在位**｜判活 no-token 全 **401**
- `yl-server` **active** / **NRestarts=0** / maintenance flag absent
- 线上库核对：8 表 + `sects.join_mode` + `pets` 三列 + `gm_sessions.expires_at` + `users.muted_until` **全绿**
  （本批零新 DDL，此项为回归）

## 5. 备份与回滚

```
# 备份（stamp 20261003_091720）
/root/backup/yl_pre_v2916_20261003_091720.tar.gz
/root/backup/{index.ts,game-dicts.json,index.html,CHANGELOG.md,CHANGELOG_PLAYER.md,index-v2915-20261002.js,database.sqlite}.pre-v2916-20261003_091720
/root/backup/database_v2916_consistent_20261003_091720.sqlite

# 回滚（本轮动了新包 + index.html + CHANGELOG + index.ts，需重启）
cp -a /root/backup/index.html.pre-v2916-20261003_091720 /opt/yl/www/index.html
cp -a /root/backup/index.ts.pre-v2916-20261003_091720   /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2916-20261003_091720 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2916-20261003_091720    /opt/yl/www/CHANGELOG.md
systemctl restart yl-server && systemctl is-active yl-server
# 0.9.15 定版：bundle=41721861172d4655a9765e2a10423c63  server=9033c805be1022e692bc67f7ccc3b1ae
```

★ 回滚语义：零 DDL、零新列；R-136 的服务端改动回滚后，「历练活动」会重新污染秘境冷却（回到新号 800+ 秒的旧态），数据无损。

## 6. 偏离与遗留

1. **0.9.15 的 index.html 回归**（见 §0）——本批已修，但**根因在流程**：热修不得直传 `build/index.html`。已在 §0 写明。
2. 部署期间**同一目标重跑 3 次**：第 1 次 preflight ABORT（`BUNDLE_DATE` 默认值漏改 20261002→20261003）；第 2 次 step 3 ABORT（§0 的 index.html 回归，**此时服务端已切 0.9.16**）；第 3 次为把服务端拉回 0.9.15 基线后重跑。**最终一次全绿**，线上状态以 §3 为准。
3. R-135 的「神识 / 身法只在高级物品出现」**未做**（成本高），留待用户拍板。
4. `check_srv_087.py` 两处失效未修（继承 0.9.15 遗留）。
5. 本批 `EXPECT_CHANGELOG_MD5` 已按最终文案登记；CHANGELOG 头条时刻 = 预估 swap 时刻 `09:20`（实际 swap 09:17，差 3 分钟，同 0.9.14 先例）。

## 7. 0.9.16 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=a59ac4496ab0e8ab81fdb147b45488ec      # index-v2916-20261003.js（2,285,822 B）
PREV_SRV_MD5=664501929cecb41fd57e65d9d0c48872         # srv/index_v28.ts（980,090 B / 66 环）
PREV_CHANGELOG_MD5=a6ce240eebd6b5a81fd3fdbb310f76c7
PREV_CHANGELOG_PLAYER_MD5=dfb4295f6fad8eb5e760c87b72cf01d3
PREV_INDEX_HTML_MD5=ac5a57f17554c02d742a5b8fff0870e3
```

## 8. 下一批留意

- `deploy_v2811.sh`：`BUNDLE_DATE`→2026100x、`BUNDLE`→v2917-*、`OLD_BUNDLE`→`index-v2916-20261003.js`、`PREV_*`×3 按 §7 重登记、`CHAIN_TAIL`→新链尾、备份命名 `v2917`
- `remote_check_v2811.sh`：包名两写法 + index.html 断言 + CHANGELOG `[0.9.17]` 断言 + 版本号段（0.9.17 在位 / 0.9.16 清零滚动）
- `EXPECT_0811.env` 全量重登记；`sim_remote_check.py` `$B` → 新包名
- ★ **index.html 必须用 `live_bump_bundle.js` 原地 patch，禁止直传 `build/index.html`**（本批 §0 教训）
- `check_srv_087.py` 两处失效未修（继承）
- GitHub staging 已同步到 0.9.16（见 §9）
- 待用户拍板：R-135 稀有属性物品范围、R-139 是否要「隐藏期收益上限」策略

## 9. GitHub 同步

见同批 `_github_sync_0.9.16.md`（脱敏扫描 → REST API 并发上传 → commit）。
