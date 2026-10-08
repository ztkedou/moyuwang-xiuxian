# DEPLOY LOG — 《摸鱼修仙传》 0.9.40（v28 链 **88 环不变**｜**纯客户端批**）

- **部署时间**：2026-10-08 19:03:00 ~ 19:0x（GMT+8）｜★★ **未重启服务** ⇒ **零停机**
  （`ActiveEnterTimestamp` 仍为 0.9.39 的 `Thu 2026-10-08 17:15:28 CST`，`NRestarts = 0`）
- **目标**：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- **脚本**：`deploy_v28/deploy_v2840.sh --skip-server`
- **定点核对**：`deploy_v28/remote_check_v2840.sh` → **PASS (0 failures)**，无 WARN
- **登记指纹**：`deploy_v28/EXPECT_0840.env`
- **备份整包**：`/root/backup/yl_pre_v2940_20261008_190300.tar.gz`（57,084,979 B）
- **DB 一致性快照**：`/root/backup/database_v2940_consistent_20261008_190300.sqlite`（13,701,120 B）
- ★★ **服务端逐字节不变**（`srv/index_v28.ts` 与 0.9.39 同 md5 = `2f49c2a7…`，仍 **88 环**）⇒ 必须 `--skip-server`。

## 1. 本批范围：0.9.40 = **2 条**（客户端 2 补丁 / 服务端 0 环）

| # | 台账号 | 任务 | 落点 |
|---|---|---|---|
| 1 | **R-201** | 历练结算「几百」档下界 **150 → 370** | `localtest/yl_r209_ext.py` |
| 2 | **R-202** | 灵宠经验曲线 `1.2^L` → **`1.1^L`** + 存量宠物迁移 | `localtest/yl_r210_ext.py` |

- 客户端 `STANDALONE_CLIENT` **55 → 57 脚本**；服务端 **88 环不变**。
- ★ **编号说明**：台账号 R-201 / R-202 ↔ 补丁号 **r209 / r210**（本仓两套编号已漂移，补丁一律取下一个空闲号）。

### 1.1 R-201 分档阈值重标定（`yl_r209_ext.py`）

> 用户实测：`分档 常态 106 · 几百 52 · 几千 0` ⇒ **几百占 33%**，偏高。

- **取证（本环最有价值的部分）**：用 node 从**真实产物**抽出真实 1200 模板 + 真实 `Fm` 权重 + 真实 `Ym` 结算链精确复算：
  - **模板路单独**（炼气 L1）= 常态 84.2 / 几百 14.8 / 几千 1.0 —— 与 R-180 v4 自报的 84.30/14.71/1.00 **逐位吻合**
    ⇒ 模型无误，但**复现不出 67/33**。
  - 差额来自 R-180 漏掉的**真实战斗路**：`DS()`（炼气 L1 ≈25.5% 触发）→ `X0()` 真跑战斗 → `By()` 结算 → ×0.65/×0.85/×3，
    胜场 `ds ≈ 330~462` **全落「几百」** ⇒ 与 R-208 的结论**完全一致**。
    组合模拟 n=4 万得 **常态 64.4 / 几百 34.7 / 几千 0.9**，命中用户实测 106/52/0。
- **T 扫描**（组合模型，炼气 L1，真实 `X0`，n=4 万，胜率≈94%）：

  | T | 常态 | 几百 | 几千 |
  |--:|--:|--:|--:|
  | 150 | 64.4% | **34.7%** | 0.9% |
  | 250 | 68.3% | 30.9% | 0.9% |
  | 300 | 69.8% | 29.3% | 0.9% |
  | 350 | 75.6% | 23.5% | 0.9% |
  | **370** | **83.0%** | **16.1%** | 0.9% |
  | 400 | 95.6% | 3.5% | 0.9% |

  ⇒ **T ∈ [363,377] 是唯一平台区**（几百 16~18%）；**取 370（平台中点）**，对战斗 `ds` 的量化台阶（363→378）最不敏感。
- **未误伤「几千」**：几千的载体是奇遇（raw 200~499 ⇒ `ds ≈ 1020+`），全程不受 T 影响。
- ★★ **已知局限（本环未处理，待拍板）**：模板与战斗收益都随 `U[realmIdx]` 缩放 ⇒ **T=370 是按「炼气 L1」标定的**；
  更高境界同一**绝对** T 折叠得更少（长生期战斗 `ds ≈ 1182~1654` 反而会落进「几千」）。
  要做成「随境界缩放」需把境界信息接进 `YlxwAdvStatAcc(res)` —— 该函数只收 `res`
  （字段仅 `expChange / spiritStonesChange / hpChange / lifespanChange / lotteryTicketsChange / reputationChange / adventureType`，**无境界**）
  ⇒ 需改调用链，**另立项**。
- **连带**：`yl_r191_ext.py` 与 `yl_r208_ext.py` 共有 **3 处**针逐字钉住了含 `150` 的整串
  ⇒ 按本仓惯例**收窄成「值无关形态」**（去掉阈值字面量、保留 `tierLow/tierMid/tierHigh` 结构）。

### 1.2 R-202 灵宠经验曲线放缓（`yl_r210_ext.py`）

- **4 处宠物升级循环** `Math.floor(X*1.2)` → `Math.floor(X*1.1)`
  （`handleFeedPet` / `batchFeedItems` / `batchFeedHp` / 远征）。
- ★ **BASE 里 `*1.2` 共 11 处，只有这 4 处是宠物升级**；另外 7 处
  （装备槽倍率 / 风险 / 模板权重 / 评级 / 武器攻击 / **预估经验预览** / 境界系数）**一字未动**（前后计数 11 → 7，逐条断言）。
- **曲线对比**（`maxExp(L)`，宠物初始 60）：

  | L | 1.2^L | 1.1^L |
  |--:|--:|--:|
  | 1 | 60 | 60 |
  | 10 | 309 | 141 |
  | 30 | 11,868 | 951 |
  | 50 | 455,021 | 6,403 |
  | 70 | 17,444,447 | 43,077 |
  | 100 | 4,140,898,726 | 751,669 |

  ⇒ `L1→L100` 总需求 **20,704,493,281 → 7,516,047**（约 **1/2755**）。
- ★★ **存量宠物迁移（本环难点）**：`maxExp` 是**存在存档里**的（服务端离线公式还会读它），只改成长率对**已有宠物无效**。
  载入路径唯一 = `ho=t=>{var T,$;`（**玩家对象规范化器**，5 个调用点覆盖本地存档 / 模板重建 / `applyRemoteSave`；
  `ho` 返回 `{...t,…}` ⇒ `pets` 透传）。在 `ho` 头部注入**只降不升、幂等**的重算：
  `need = floor(60*1.1^(level-1))`，**仅当 `maxExp > need` 时**下调。
  - ★ **超出题面的必要修正**：单降 `maxExp` 会破坏系统不变量 `exp < maxExp`
    ⇒ 实测 L30/L50/L70 的宠物在**下次喂食时瞬间连升 4/14/30 级**（L70 直接顶到 L100）。
    故迁移**同步对 `exp` 等比缩放** `floor(exp*need/cur)`，保持进度百分比
    ⇒ 实测迁移后幂等（连跑 3 次同值）、比例不变（0.42→0.42）、喂 +100 经验仅升 ≤1 级。

## 2. 指纹（部署前后）

| 对象 | 部署前（0.9.39） | 部署后（0.9.40） |
|---|---|---|
| `www/assets/index-v2937-20261008.js` | `5a35630ea5914ab7f8b94a9f2bfb0686` | 同左（更早回滚点） |
| `www/assets/index-v2938-20261008.js` | `a4726c77b810c6b620b0604ce89cf9a7` | 同左（0.9.38 定版） |
| `www/assets/index-v2939-20261008.js` | `21a16b962a1ccedfc02c021b3bd2dc71` | 同左（**0.9.39 定版 = 秒级回滚点**） |
| `www/assets/index-v2940-20261008.js` | —（新文件） | **`af8e021dd9fe8883d775c0b0dc223f96`**（2,318,722 B） |
| `server/index.ts` | `2f49c2a7bc1b7348c2732912afe968ff`（88 环） | **同左（未变）** |
| `www/CHANGELOG.md` | `be3ffc8b081882ec41fd27dcfe3ace58` | **`079707b09375b5f18f5a67546fb48c64`**（回填上线时刻后） |
| `www/CHANGELOG_PLAYER.md` | `4c0c1b14b2e940f23e64fb0515535a4d` | **`aafae92230df1006628127ac180e6fd0`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（未变）** |

线上实测（部署后 SSH 直采，与本表逐字一致）：

```
af8e021dd9fe8883d775c0b0dc223f96  /opt/yl/www/assets/index-v2940-20261008.js  (2,318,722 B)
2f49c2a7bc1b7348c2732912afe968ff  /opt/yl/server/index.ts          (1,019,321 B / 88 环，未变)
079707b09375b5f18f5a67546fb48c64  /opt/yl/www/CHANGELOG.md
aafae92230df1006628127ac180e6fd0  /opt/yl/www/CHANGELOG_PLAYER.md
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
```

★ 服务端链中间产物**全部不变**（88 环 = `s88.r207.ts` = `2f49c2a7…`）；
`_chainstage/index_v28.v28112.ts` 与 `srv/index_v28.ts` 逐字节 IDENTICAL。

## 3. 部署前本地验收

- `chain_build.py --all`：**rc=0**（服务端链重建后 md5 仍 `2f49c2a7…`；前端装配产出 `af8e021d…`）
- `dryrun_087.py`：**PASS（FAIL=0）**，standalone 门禁 **1599 条 / 69 脚本（r116~r210）**
- 「预演==交付」：`_chainstage/dryrun_087.bundle.js` md5 = `af8e021dd9fe8883d775c0b0dc223f96` **== 交付产物** ✓
- `sim_remote_check.py --script deploy_v28/remote_check_v2840.sh` 本地预演：**OK=545 / SKIP(远端专有)=15 / FAIL=0**
- `bash -n` 两脚本 **OK**；`deploy_v2840.sh` / `remote_check_v2840.sh` / `EXPECT_0840.env`
  **CR 字节 = 0（纯 LF）/ 无 BOM / 以换行结尾** ✓
- ★ 远端基线预检（step 0，fail-closed）：bundle `21a16b96…` / 更早回滚点 `a4726c77…` / server `2f49c2a7…` /
  CHANGELOG `be3ffc8b…` / `index.html` 指向 v2939 —— **全部逐字节命中**，且 v2940 新包**尚不存在**。

## 4. 线上验收

- `remote_check_v2840.sh` → **REMOTE-CHECK: PASS (0 failures)**，无 WARN
  （含本批 **27 条新针**：R209 ×6、R210 ×15、回归 ×5、版本号 ×1）
- 线上指纹全部命中（见 §2 表 + SSH 直采块）
- `index.html` 指向 **`index-v2940-20261008.js`**；★★ **gzip 硬断言**：`zcat index.html.gz | grep 新包 = 1` ✓（R-159 铁律）
- ★★ **零停机**：`ActiveState = active` / `NRestarts = 0` / `ActiveEnterTimestamp` **仍为 `2026-10-08 17:15:28 CST`**（未重启）
- 回滚点 **v2937 + v2938 + v2939 三包均在** ✓
- 公开冒烟：`index.html → 200`｜`bundle → 200`｜`gz → 200`；线上包内抽查 `if (ds <= 370)` = 1、`[r210pet]` = 1、`0.9.40` = 1 ✓
- 双 CHANGELOG 已回填**实际上线时刻 19:03** 并重传（`079707b0…` / `aafae922…`，无 `.gz` 伴生）；
  `EXPECT_0840.env` 已重登记（`EXPECT_CHANGELOG_MD5=079707b0…`）

## 5. 本轮踩到的新坑 / 经验

1. ★★ **「字面链验证」不能从 BASE 起跑**：我第一版独立验证直接把 `build/assets/index-v26m-20260927.js`（BASE）
   当输入依次套 r191 → r208 → r209，**三个全 rc=2 ABORT**。
   原因：r191 的锚点（`if (ty === "lucky") S.lucky += 1;`）**本身是更早的补丁（r179）注入的**，
   BASE 里根本没有 ⇒ 必须走**真实装配链**（`build_v26n.apply_standalone`）或从**已装配产物**起跑。
   ★ 教训：**「补丁的输入契约是「上一个补丁的输出」，不是 BASE」**。
2. ★★ **门禁针可能被「多处」钉住**：R-201 要改的 `if (ds <= 150) …` 整串被 **3 处**逐字钉住
   （`yl_r191_ext.py` 的 `gates()` 1 处 + `yl_r208_ext.py` 的 `gates()` 1 处 + `FREEZE` 1 处）。
   我最初只发现 r191 那处，靠**主动全库 grep**才补出 r208 的两处。
   ⇒ **改任何被门禁钉住的值之前，先 `grep -rn` 全库确认钉住点的数量**。
3. ★★ **`gates()` 与 `FREEZE` 的语义不同**（本仓门禁的真正难点）：
   `dryrun_087.py` 的 `_sa_scripts` 循环**只在「全部套用完的终态」上跑各补丁的 `gates()`**；
   而 `FREEZE` 是**套用时刻对输入**的校验。⇒ 被后续补丁合法改写的针，
   **`gates()` 里那条必须收窄**（否则终态必 FAIL），`FREEZE` 里那条不改也能过（但为让 `--check` 在终态产物上也能过，一并收窄更一致）。
4. ★ **`cnt()` 用的是 `grep -o -F`（字面匹配）** ⇒ 针里的 `( ) + = * /` 都是字面量，写针时不必转义。
   （反过来说：**针越长越安全**，短针容易在多处命中。）
5. ★ **「纯客户端批」的 `PREV_SRV_MD5` 不是「恒等替换」**：输入 `deploy_v2839.sh` 里的 `PREV_SRV_MD5` 是
   **0.9.38** 的值（`b598eab6…`），本批必须改成 **0.9.39** 的值（`2f49c2a7…`）。
   「恒等」指的是 **`PREV_SRV_MD5 == EXPECT_SRV_MD5`（都是本批线上值）** —— 这才是纯客户端批的特征。
   ★ 改写时**只动 `PREV_SRV_MD5=` 槽位**，历史注解里的裸 full 值**逐字保留**（避免全局替换误伤）。

## 6. 残留清理

- 远端 `_remote_check_v2840.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` 留在 `/opt/yl/server/` 便于复跑（惯例）。
- 本地 `_vfy/`（本轮独立验证用的临时目录）**已删除**。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2940-20261008_190300 /opt/yl/www/index.html
# ★ index.html.gz 必须与明文同批重建（nginx gzip_static 铁律 R-159）
gzip -9 -kf -c /opt/yl/www/index.html > /opt/yl/www/index.html.gz
cp -a /root/backup/CHANGELOG.md.pre-v2940-20261008_190300        /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2940-20261008_190300 /opt/yl/www/CHANGELOG_PLAYER.md
# ★ 服务端未变 ⇒ 无需回滚 index.ts、无需重启
# 上一版定版（0.9.39）：bundle=21a16b962a1ccedfc02c021b3bd2dc71  server=2f49c2a7bc1b7348c2732912afe968ff
# 整包：/root/backup/yl_pre_v2940_20261008_190300.tar.gz
```

★ 本批**无 DDL、服务端零改动** ⇒ 回滚只动前端三件（`index.html` + 双 CHANGELOG），**不需要重启服务**。
★ 若需完全还原 DB：`/root/backup/database_v2940_consistent_20261008_190300.sqlite`（13,701,120 B）。
★ ⚠ **R-202 的迁移会改写存档里的宠物 `maxExp`/`exp`** ⇒ 回滚到 0.9.39 后，宠物会按**旧曲线**继续
（`maxExp` 已被下调 ⇒ 相当于升级仍然快），**不会损坏数据**，但不会自动"涨回去"。如需完全还原用上面的 DB 快照。

## 8. 0.9.40 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=a4726c77b810c6b620b0604ce89cf9a7      # 0.9.38 index-v2938-20261008.js（更早回滚点）
PREV_LIVE_BUNDLE_MD5=21a16b962a1ccedfc02c021b3bd2dc71 # 0.9.39 index-v2939-20261008.js（本次部署前的线上包）
PREV_SRV_MD5=2f49c2a7bc1b7348c2732912afe968ff         # 0.9.39 = 0.9.40（88 环 = s88.r207.ts）★ 本批未变
PREV_CHANGELOG_MD5=be3ffc8b081882ec41fd27dcfe3ace58   # 0.9.39 CHANGELOG.md
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S20_MD5=7780e099a6cd1ac0de4b502c467ae2c0     # 0.8.9 定版 s20.t16arena.ts（前 20 环不变）
# 本版（0.9.40）新指纹：
#   bundle   af8e021dd9fe8883d775c0b0dc223f96  (2,318,722 B)  index-v2940-20261008.js
#   server   2f49c2a7bc1b7348c2732912afe968ff  (1,019,321 B / 88 环) ★ 与 0.9.39 相同
#   CHANGELOG.md        079707b09375b5f18f5a67546fb48c64
#   CHANGELOG_PLAYER.md aafae92230df1006628127ac180e6fd0
#   dicts    1b635513f553875060869272b790f910  (未变)
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
