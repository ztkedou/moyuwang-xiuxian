# DEPLOY LOG — 《摸鱼修仙传》 0.9.25

- 部署时间：`2026-10-06 13:03` (GMT+8)
- 目标：**Azure East Asia 新机 `104.208.x.x`（HKVPS）** / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2825.sh`（服务端 + 客户端 + CHANGELOG + index.html bump + gz sync）
- 定点核对：`deploy_v28/remote_check_v2825.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0825.env`
- 备份：`/root/backup/yl_pre_v2925_20261006_130308.tar.gz`（47,610,348 B）
  + 七件 `.pre-v2925-20261006_130308`（index.html / CHANGELOG.md / CHANGELOG_PLAYER.md / index.ts /
  game-dicts.json / index-v2924-20261006.js / database.sqlite）
  + `database_v2925_consistent_20261006_130308.sqlite`（VACUUM INTO 一致性快照，7,475,200 B）
- 服务：`systemctl is-active yl-server` = **active**，`NRestarts=0`

---

## 1. 本批范围：0.9.25 = R-165 + R-166（2 条需求，链式自动轮次 · 3 子代理并行）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-165 | 打坐「顿悟」同一触发点产生悟道心得 | `srv_patch_r165.py`（**第 72 环 / 新末环**）+ `yl_r165_ext.py`（standalone） | ✔ | ✔ |
| R-166 | 仙务·妖灵「放生妖灵」补确认弹窗 | `yl_r166_ext.py`（standalone） | ✔ | — |

### 1.1 R-165 打坐顿悟联动悟道心得

**需求原文**：「打坐 / 历练中会随机触发悟道经验提升。可以把这个和打坐的顿悟做成同一个点触发，
这样顿悟时既可以获得额外的经验，又可以产生悟道经验。」

**改前取证**：打坐 tick 的顿悟分支（bundle 内 `Math.random()<.004`，唯一一处）只给额外修为
（`v×30~50`），不产生任何悟道心得。悟道（`wudao` 表）是**服务端权威**，客户端只读
（`GET /api/wudao`），入账唯一函数 `wudaoAddExp(userId, daoKey, expDelta, source)`。
既有端点只有 `GET /api/wudao` 与 `POST /api/wudao/insight`（**花 5000 灵石**换 100 心得）
⇒ **必须新增一个免费端点**，故本批是服务端链重建批。

**改法（1 处插入 · 零新表 / 零新列 / 零改既有端点）**：
- 新增 `POST /api/wudao/enlighten`（插在 `/api/wudao/insight` 路由行之前）：
  - 系别由**服务端**按境界门槛随机挑（`Object.keys(WUDAO_DAOS).filter(k => realmIdx >= wudaoDaoGateRealm(k))`），
    客户端不传 `dao`（只有服务端知道门槛）
  - 入账复用既有 `wudaoAddExp(userId, dao, WUDAO_INSIGHT_EXP, 'idle')`（与挂机心得同源，写 `wudao_log`）
  - **三层频控**复用既有 `rateLimit()`：L1 最小间隔 5s（max 1 / 5s）、L2 小时帽 60、L3 日帽 200
  - 响应 `{ok, dao, daoName, expGain, level, exp}`；★ 顶层**不含** `balance`（避免 STONE_ECHO 覆写玩家灵石）
- 客户端 `yl_r165_ext.py`：顿悟分支末尾追加 `,YlxwWudaoEnlighten(c)`；
  新增助手 `YlxwWudaoEnlighten(addLog)` 走项目请求包装 `YlxwPost("/wudao/enlighten", {})`，
  **仅成功时**补一条日志「☯ 悟道【X道】心得 +10」，失败/被频控一律静默（不影响打坐主流程）。

**上限推演**：客户端顿悟期望 ≈ 7.2 次/小时（2s tick × 0.4%）⇒ 正常 **+72 心得/小时**；
最坏 200 次/日 × 10 = **2000 心得/日 < 单系满级 2250** ⇒ 不会一夜满级。

**★ 历练侧明确不挂点**（客户端与服务端均不加）：服务端 `ylWudaoIdleDelta()` 已把
「打坐 + 历练」计数器差值一起喂给 `tickWudaoIdle`（≈24 心得/小时），历练的时间型随机心得已具备；
而历练即时奇遇最高 ~180 次/小时，若同点 +10 ⇒ ~1800 心得/小时 ≈ 单系满级的 80%/小时，**会破坏曲线**。

**红线（一行未动）**：`WUDAO_INSIGHT_CHANCE` / `WUDAO_INSIGHT_EXP` / `WUDAO_MANUAL_COST` /
`WUDAO_MANUAL_EXP` / `WUDAO_MAX_LEVEL` / `WUDAO_MAX_EXP_TOTAL` / `wudaoIdleInsights` /
`tickWudaoIdle` / `ylWudaoIdleDelta` / `wudaoAddExp` / `GET /api/wudao` / `POST /api/wudao/insight`
本体；打坐/历练的修为结算、回血、存档结构、开关。

### 1.2 R-166 仙务·妖灵「放生妖灵」补确认弹窗

**需求原文**：「仙务·妖灵  放生要加确认弹窗。」

**改前取证**（产物内「放生」入口逐个排查）：

| # | 入口（组件链） | 触发 | 改前有无确认 |
|---|---|---|---|
| 1 | **仙务·妖灵 → `YlxwR18AwayReleaseRow`** | `f("r18release", "/pet/spirit/release", {}, "已放生妖灵")` | ❌ **无** ← 本需求所指 |
| 2 | 灵宠面板卡内单个放生 | `onClick:()=>A(I.id)` → 弹窗 @1766045 | ✅ 有 |
| 3 | 灵宠面板列表单个放生 | `onClick:()=>A(P.id)` → 弹窗 @1766045 | ✅ 有 |
| 4 | 灵宠面板批量放生 | `onClick:()=>q(!0)` → 弹窗 @1737214 | ✅ 有 |

**改法**：在入口 ① 的 `onClick` 里、`f(...)` 之前插一句 `if (!window.confirm("…")) return;`
（与产物既有 4 处 `window.confirm` 及 R-163 一键收取同款写法；零新组件、锚点最小）。
取消 ⇒ 直接 return，**不发任何请求**；确定 ⇒ 原请求逐字不变。
灵宠面板那 3 个入口**未改动**。

## 2. 指纹

| 对象 | 0.9.24（部署前） | 0.9.25（部署后） |
|---|---|---|
| `www/assets/index-v2924-20261006.js` | `3d0980c5c4f5f6adc988101d7411bec5` | 同左（旧包保留 = 回滚点） |
| `www/assets/index-v2923-20261006.js` | `5cd89d3522f52ec0fcaf5f659f230504` | 同左（0.9.23 定版，更早的回滚点） |
| `www/assets/index-v2925-20261006.js` | —（新文件） | `153c19120249210e7aa546eeb6ab740a`（2,302,462 B） |
| `server/index.ts` | `a7cb34cccad9343ebab8ffcfa06c9852` | `6ebc3d070e401af46e199bf2926fe127`（989,996 B / **72 环**） |
| `www/CHANGELOG.md` | `5b9b4d025493364d2c6c5ece32b3a58d` | `fe24e79cba41df3c83e0a8eff441b119`（见 §5.1） |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批不变） |

链中间产物（单变量可核）：

```
s20.t16arena.ts  7780e099a6cd1ac0de4b502c467ae2c0  824,768 B  ← == 0.8.9 定版（前 20 环不变）
s66.r136.ts      664501929cecb41fd57e65d9d0c48872  980,090 B  ← == 0.9.16~0.9.19 定版
s67.r144.ts      4c3a3eea75ca8f11be18b5c0c2127dd1  982,652 B  ← == 0.9.20 定版
s68.r148.ts      847618c70f965621417ee4611ba41340  982,767 B  ← == 0.9.21 定版
s69.r149.ts      479dcc66a3261c98254367c1cab0f416  983,742 B  ← == 0.9.23 定版
s70.r160.ts      2de9f429f5a861dc5fa8b8f49fcbc1a5  984,750 B  ← 第 70 环（R-160 cap 曲线）
s71.r163.ts      a7cb34cccad9343ebab8ffcfa06c9852  987,387 B  ← == 0.9.24 定版（本批 PREV）
s72.r165.ts      6ebc3d070e401af46e199bf2926fe127  989,996 B  ← 链尾（本批新增第 72 环）
```

## 3. 部署前本地验收

- `localtest/chain_build.py --all` ⇒ **rc=0**（**72 环**门禁全绿 + `node --check` rc=0）；链尾 `_chainstage/s72.r165.ts` = `6ebc3d07…`
- `localtest/dryrun_087.py` ⇒ **门禁结果: PASS（FAIL=0）**
  - 模块门禁 **4248 条 FAIL 0**
  - standalone 门禁 **711 条 FAIL 0**（★ 本批把 r155/r161/r162/r163 补登记进名单，并修 harness 以支持 `cmp='>=1'` 写法；27 → **33 脚本**）
  - **预演==交付**：`153c19120249210e7aa546eeb6ab740a`
- `localtest/sim_remote_check.py --script deploy_v28/remote_check_v2825.sh` ⇒ **OK=406 / SKIP=15 / FAIL=0**
- 两个 standalone 模块各自自测：rc=0 → 重跑 rc=3（幂等）→ `node --check` rc=0 → diff 仅命中声明片段
- 服务端环 `srv_patch_r165.py` 自测：17 条门禁全绿 + round-trip 自证 + `node --experimental-strip-types --check` rc=0

## 4. 线上验收

- `remote_check_v2825.sh` ⇒ **PASS (0 failures)**（含 0.8.1~0.8.11 全量回归 + 0.9.x 回归 + R-165/R-166 新断言 + 服务健康 + 线上库核对）
- 新端点判活：`POST /api/wudao/enlighten` 无 token ⇒ **401**（与既有 `/api/wudao`、`/api/wudao/insight` 一致）
- ★ **浏览器视角（带 `Accept-Encoding: gzip`）**：公网 `curl -H 'Accept-Encoding: gzip' | gunzip -c` 得到
  `assets/index-v2925-20261006.js`；服务器 `zcat /opt/yl/www/index.html.gz` 同包 ⇒ **R-159 的 gzip 旧壳防线继续生效**
- `_remote_gz_sync.sh --check` ⇒ 全 OK
- 服务 `active` / `NRestarts=0`
- 公网指纹逐位核验（ssh md5sum）：bundle `153c1912…` / server `6ebc3d07…` / dicts `1b635513…` 全部与本地交付产物一致

## 5. 本批踩到的新坑

### 5.1 ★ CHANGELOG 条目头时刻必须 = **实际上线时刻**，发布前写的时间常差几分钟
本批 CHANGELOG 初稿写 `13:05`，实际备份戳 `20261006_130308`（= 13:03）。
⇒ 已把条目头改为 `## [0.9.25] - 2026-10-06 13:03`，重算 md5（`1514b943…` → **`fe24e79c…`**）、
回写 `EXPECT_0825.env`、**重传线上 `/opt/yl/www/CHANGELOG.md`**（与 0.9.22 同款收尾）。
**规矩**：`CHANGELOG` 是公网可访问且被 `EXPECT_CHANGELOG_MD5` fail-closed 门禁的对象 ⇒
发布前就把时间定在「预计备份戳那一分钟」，或发布后按本节流程回填。

### 5.2 `dryrun_087.py` 的 standalone 门禁名单是**硬编码**的，新模块不会自动进来
本批发现 r155 / r161 / r162 / r163 **已接线但从未登记**进 `dryrun_087.py` 的名单
（`build_v26n.apply_standalone` 会跑它们，但预演阶段没重跑其 `gates()`）。
⇒ 本批补齐 6 个（r155/r161/r162/r163/r165/r166），并把脚本数 27 → 33。

### 5.3 `dryrun_087.py` 的 harness 不支持 `cmp='>=1'`（expect=None）写法
`yl_r155_ext.gates()` 末条用 `('R155·幂等标记', 'YLXW_ADV156_LINES', None, '>=1', '')`，
harness 直接 `act >= expect` ⇒ `TypeError`。这正是 r155 当年没被登记进名单的**真实原因**。
⇒ 已给 harness 加兼容：`cmp` 以 `>=` 开头时把后缀数字解析成 expect。

### 5.4 `sim_remote_check.py` 的 `$B` 映射是硬编码包名
`FILE_MAP['$B'] = 'build/assets/index-v2924-20261006.js'` 不会自动跟随升版
⇒ 首轮 sim 全部 FAIL（它拿旧包当交付产物）。**升版必须同步改这一行**（已改为 v2925）。

### 5.5 「旧版本号已清零」断言会在 sim 上假 FAIL —— 其实是 sim 读错文件
`chk "$B" '0.9.24' ... eq 0` 在 sim 上报 got=1，原因是 §5.4 的映射没更新，而非产物有问题。
**判断依据**：`grep -c 'YLVERSION_FALLBACK = "0.9.25"' build/assets/index-v2925-*.js` = 1。
⇒ 先修 sim 映射再判 FAIL，别急着改断言。

## 6. 回滚（本轮动了新包 + index.html + CHANGELOG + index.ts，需重启）

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2925-20261006_130308    /opt/yl/www/index.html
cp -a /root/backup/index.ts.pre-v2925-20261006_130308      /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2925-20261006_130308 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2925-20261006_130308  /opt/yl/www/CHANGELOG.md
systemctl restart yl-server && systemctl is-active yl-server
# 0.9.24 定版：bundle=3d0980c5c4f5f6adc988101d7411bec5  server=a7cb34cccad9343ebab8ffcfa06c9852
# 整包：/root/backup/yl_pre_v2925_20261006_130308.tar.gz
```

## 7. 收尾

- 部署件三件套 + 本日志 + 产物已同批 git 提交（`yl-deploy`）
- 台账：R-165 / R-166 闭环归档
- 待拍板：R-165「历练侧是否也要在奇遇点补发心得」—— 当前**明确不做**（见 §1.1 推演），
  如需改成「历练奇遇也发（但降低单次数值）」请回话。
