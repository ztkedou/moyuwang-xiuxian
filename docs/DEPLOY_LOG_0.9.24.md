# DEPLOY LOG — 《摸鱼修仙传》 0.9.24

- 部署时间：`2026-10-06 12:39` (GMT+8)
- 目标：**Azure East Asia 新机 `104.208.x.x`（HKVPS）** / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2824.sh`（服务端 + 客户端 + CHANGELOG + index.html bump + gz sync）
- 定点核对：`deploy_v28/remote_check_v2824.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0824.env`
- 备份：`/root/backup/yl_pre_v2924_*.tar.gz` + 六件 `.pre-v2924-*` + `database_v2924_consistent_*.sqlite`

---

## 1. 本批范围：0.9.24 = R-160 + R-161 + R-162 + R-163（4 条需求，工作流 4 成员并行）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-160 | 挂机收益结算时长上限按境界递增 | `srv_patch_r160.py`（**第 70 环**） | —（面板读服务端 capHours，自动跟随） | ✔ |
| R-161 | 历练日志：寿元行与收获行拆分 + 汇总行去重 | `yl_r161_ext.py`（standalone） | ✔ | — |
| R-162 | 历练中操作宠物 ⇒ 宠物/[灵石] 消息串台 | `yl_r162_ext.py`（standalone） | ✔ | — |
| R-163 | 灵田数值重定档 | `srv_patch_r163.py`（**第 71 环**）+ `yl_r163_ext.py`（文案） | ✔ | ✔ |

### 1.1 R-160 挂机收益上限按境界递增
- 旧：固定 8h（月卡 12h）。新：**练气期1层 = 24h**，**每层 +1h**（7 境界 × 9 层 = 63 层）⇒ 最高 **86h**（长生境9层）；月卡 = 上限 ×1.5（24h→36h，86h→129h）。
- 公式：`totalLevel = max(0,realmIndex)*9 + max(1,realmLevel)`；`base = 24 + (totalLevel-1)*1`。★ `realmIndex` 有 `Math.max(0,…)` 钳位 ⇒ 不会出现负值/NaN。
- ★ **澄清**：需求里那条「💤 你离线修炼了 10 小时 29 分钟…」日志**新版本根本不发**（`CHANGELOG.md:797` 载 R-037 已移除；交付产物实测 `你离线修炼了`/`自动吸纳`/`离线修炼` 计数**全为 0**）。用户看到它是因为 nginx `gzip_static` 陈旧 `index.html.gz` 把浏览器喂给了 2026-09-25 的旧包（即 R-159 事故）⇒ **「日志口径」这一半无对象可修**，客户端不做补丁。
- ★ 红线：`OFFLINE_RATE_*` / `OFFLINE_STONE_RATIO` / `OFFLINE_MIN_MS` / `offlineRewards()` / `offlineWindow()` / `offlineAnchor()` **一行未动**。

### 1.2 R-161 / R-162 历练日志（根因 = R-146 同帧微批 flush 合并过宽）
- R-161①：`⚠️ 寿元 -X 年` 与 `⚡ 历练收获` 原被挤成一条 ⇒ 拆回两条。
- R-161②：停止自动历练的汇总行「修为 +N · 灵石 +N」**重复两次**（R-155 合并头行+统计行未去重）⇒ 去重。
- R-162：宠物消息（`这次灵宠机缘转化为亲密度`/`你获得了灵宠`）与 `[灵石] 已同步服务端余额…` 原会并入历练日志行 ⇒ 拆分；并让「灵石来源」跳过 R-146 合并 blob（判据 `  ·  ` 双空格分隔符，全产物实测 2 处：1 处 R-146 合并、1 处 React JSX 标签，非日志路径）。
- ★ **未改** `yl_r146_ext.py`（只在其后追加拆分/去重）—— 保守做法，避免动到已验证的合并逻辑本体。

### 1.3 R-163 灵田数值重定档
- 种子下限 **3000**；卖钱草**小幅净赚且逐档收敛**（回收率 1.200/1.150/1.100/1.050/1.025，净赚上界 **+1200**）；综合/稀有/纯修为草**净亏灵石换修为**（回收率 .50/.40/.25）。
- 修为侧单位时间恒定（sell 4000/h · mix 8000/h · cult 16000/h · rare 2400/h）⇒ 修为/灵石随品阶递减 ≈ `k·S^0.65`。
- 极差：种 **540x→16x**、变卖 **337x→51x**、修为 **675x→30x**。
- 满配加成（洞府 L10 + 照料满 = ×1.21）下卖钱草净赚仍 ≤ +50%/季 ⇒ **永不印钞**（`变卖×1.21 ≤ 种子×1.5` 逐档成立）。
- 旧 5 种（已停种）保持 ×10 兼容口径未动。

## 2. 指纹

| 对象 | 0.9.23（部署前） | 0.9.24（部署后） |
|---|---|---|
| `www/assets/index-v2923-20261006.js` | `5cd89d3522f52ec0fcaf5f659f230504` | 同左（旧包保留 = 回滚点） |
| `www/assets/index-v2922-20261005.js` | `e9c74146e02c9ba638cb0357ef5ed0c7` | 同左（0.9.22 定版，更早的回滚点） |
| `www/assets/index-v2924-20261006.js` | —（新文件） | `3d0980c5c4f5f6adc988101d7411bec5`（2,301,289 B） |
| `server/index.ts` | `479dcc66a3261c98254367c1cab0f416` | `a7cb34cccad9343ebab8ffcfa06c9852`（987,387 B / **71 环**） |
| `www/CHANGELOG.md` | `b04cc322a6e444dfb1624412a97a4631` | `5b9b4d025493364d2c6c5ece32b3a58d` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批不变） |

## 3. 部署前本地验收

- `chain_build.py --all` ⇒ **rc=0**（**71 环**门禁全绿 + `node --check` rc=0）；链尾 `_chainstage/s71.r163.ts` = `a7cb34cc…`
- `dryrun_087.py` ⇒ **门禁结果: PASS（FAIL=0）**；**预演==交付**（`3d0980c5…`）
- `sim_remote_check.py --script deploy_v28/remote_check_v2824.sh` ⇒ **OK=386 / SKIP=15 / FAIL=0**

## 4. 线上验收

- `remote_check_v2824.sh` ⇒ **PASS (0 failures)**（含 0.8.1~0.8.11 全量回归 + 0.9.x 回归 + R-160/161/162/163 新断言 + 服务健康 + 线上库核对）
- ★ **浏览器视角（带 `Accept-Encoding: gzip`）**：`<title>摸鱼修仙传</title>` + `assets/index-v2924-20261006.js` ⇒ **R-159 的 gzip 旧壳防线生效**
- `_remote_gz_sync.sh --check` ⇒ 全 OK，`index.html.gz` 与 `index.html` 同包
- 服务 `active` / `NRestarts=0`；公网 200/200/200/200 + 401/401

## 5. 本批踩到的新坑

### 5.1 ★ 生成 `remote_check_*` 时「通用前缀替换」会**反噬**刚生成的整名
`_mk_rc2824.py` 初版先做整名替换（`index-v2920-20261003.js` → `index-v2922-20261005.js`），
再兜底做通用前缀替换（`index-v2922` → `index-v2924`）⇒ **把刚生成的 `index-v2922-20261005.js` 又改成了 `index-v2924-20261005.js`**，
导致 `PREV_BUNDLE_FILE` 指向一个不存在的包 ⇒ 真机 `probe` 报 **404 假 FAIL**（部署本身没问题）。
**规矩**：包名只做**整名**替换；通用前缀替换必须删掉（或先于整名执行）。

### 5.2 `B=` 行与 `EXPECT_082x` 是独立串，整名替换覆盖不到
`B="index-v292X-${BUNDLE_DATE}.js"` 与 `EXPECT_082X` 不会命中整名规则，必须**单独点名替换**，
否则断言会静默漏掉（本轮各踩一次）。

### 5.3 「假 FAIL」的处理纪律
本轮 `remote_check` 首轮 FAIL 时**没有回滚**，而是先定位到「是我生成的核对脚本写错了」，
修脚本后单独 `scp` 重跑拿到 PASS。**判断依据**：step 4 verify 的指纹（bundle new / index.html / service）
全部正确 ⇒ 部署动作本身成功。★ 不要因为核对脚本自己的 bug 就回滚一次成功的部署。

## 6. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
sed -i 's#/myxxz/assets/index-v2924-20261006.js#/myxxz/assets/index-v2923-20261006.js#' /opt/yl/www/index.html
gzip -9 -k -f /opt/yl/www/index.html          # ★ 必须重建，否则 gzip_static 继续发旧壳
cp -a /root/backup/index.ts.pre-v2924-<TS>        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2924-<TS> /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2924-<TS>    /opt/yl/www/CHANGELOG.md
bash /opt/yl/server/_remote_gz_sync.sh --check
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版（0.9.23）：bundle=5cd89d3522f52ec0fcaf5f659f230504  server=479dcc66a3261c98254367c1cab0f416
```

★ 回滚注意：本批**零 DDL**（无新表/列/索引）⇒ 无需数据库操作。

## 7. 0.9.24 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=3d0980c5c4f5f6adc988101d7411bec5      # index-v2924-20261006.js
PREV_SRV_MD5=a7cb34cccad9343ebab8ffcfa06c9852         # s71.r163.ts（71 环）
PREV_CHANGELOG_MD5=5b9b4d025493364d2c6c5ece32b3a58d
PREV_DICTS_MD5=1b635513f553875060869272b790f910
```
