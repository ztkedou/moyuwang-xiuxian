# DEPLOY LOG — 《摸鱼修仙传》 0.9.23

- 部署时间：`2026-10-06 01:34` (GMT+8)（R-155 主体）+ `2026-10-06 11:5x`（★ 本文件补记的 **R-159 gz 事故修复** 与 **仓库对齐**）
- 目标：**Azure East Asia 新机 `104.208.x.x`（HKVPS）** / `https://moyuwang.online/myxxz/`
- 脚本：★ **本批的 `deploy_v2823.sh` / `remote_check_v2823.sh` / `EXPECT_0823.env` 未留存**（见 §6「本批的缺口」）
- 定点核对：`<未留存>`；本文件由**事后重建**（见 §0）
- 备份：`/root/backup/index.html.gz.pre-r155-*`、`/root/backup/shared.css.gz.pre-r155-*`、`/root/backup/index-v2923-20261006.js.pre-r159-*`

---

## 0. ★ 本文件是「事后重建」——先说清它的来历

0.9.23 是**链式自动轮次**（automation）在 2026-10-06 01:33–01:34 自动发布的一批（R-155：
自动历练结束汇总 7 条 → 1 条，纯客户端）。但该轮**只把产物发到了线上，仓库侧留下一地残迹**：

| 对象 | 线上 | 本地仓库（事故发现时） |
|---|---|---|
| `CHANGELOG.md` 头条 | `## [0.9.23] - 2026-10-06 01:34` | **`0.9.22`（没有 0.9.23 条目）** |
| bundle | `index-v2923-20261006.js` | 不存在（`build/` 里只有 v2922） |
| `build_v26n.OUT` / `chain_build.CLIENT_OUT` / `dryrun_087.BUNDLE_BASENAME` / `build/index.html` | v2923 | **仍是 v2922** |
| `yl_version_ext.DEFAULT_VERSION` | — | **仍是 `0.9.22`** |
| `localtest/yl_r155_ext.py` | — | 在（但 `build_v26n.py` 里的注册是未提交改动） |
| `deploy_v2823.sh` / `remote_check_v2823.sh` / `EXPECT_0823.env` / 本 DEPLOY_LOG | — | **全部缺失** |

⇒ 本地仓库当时**谎报版本为 0.9.22**。若不修，下一轮会把 0.9.22 直接升到 0.9.23 并**用同名文件覆盖线上包**。

**本文件与 §2/§4 的指纹，是 2026-10-06 11:5x 由主控 AI 依据线上实物 + 本地产物逐字节对齐后回填的**。

## 1. 本批范围：0.9.23 = R-155「自动历练结束汇总 7 条 → 1 条」（纯客户端）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-155 | 停止自动历练时日志刷屏（7 条 → 1 条） | `localtest/yl_r155_ext.py`（STANDALONE_CLIENT 第 28 个） | ✔ | — |

- 改前：停止自动历练 → R-105 头行 1 条 + R-138 汇总块 6 条 = **7 条**
- 改后：`YLXW_ADV156_LINES` 收集 → 头行 + 收集行以「 · 」连接 → **单次 `add`** = **1 条**，字段零丢失
- 冻结：`YlxwAdvAcc` / `YlxwAdvStatAcc` / `YlxwAdvStatNew` 逐字不动；R-146 单轮合并、打坐 medlog、开关与存档均未动

## 2. 指纹（0.9.23 定版）

| 对象 | md5 | 备注 |
|---|---|---|
| `www/assets/index-v2923-20261006.js` | `5cd89d3522f52ec0fcaf5f659f230504` | 2,299,703 B |
| `server/index.ts` | `479dcc66a3261c98254367c1cab0f416` | 983,742 B / **69 环**（本批未动） |
| `www/CHANGELOG.md` | `b04cc322a6e444dfb1624412a97a4631` | 头条 `## [0.9.23] - 2026-10-06 01:34` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 未动 |

回滚点：`index-v2922-20261005.js`（`e9c74146e02c9ba638cb0357ef5ed0c7`，0.9.22）+ `index-v2921-20261004.js`（`d15800ff…`）。

## 3. 部署前本地验收（2026-10-06 11:5x 重跑）

- `localtest/chain_build.py --all` ⇒ **rc=0**（69 环门禁全绿 + `node --check`）
- `localtest/dryrun_087.py` ⇒ **门禁结果: PASS（FAIL=0）**；standalone **622 条** FAIL 0；**预演==交付**（`5cd89d35…`）
- ★ **对齐过程中修掉 1 处跨模块门禁冲突**：R-155 把 R-105 头行由 `add("🗺 本次自动历练 " + YlxwAdvDur(el) …)`
  改为 `var _l155 = ["🗺 本次自动历练 " + YlxwAdvDur(el) …]`（汇总后单次 add），
  而 R-138 冻结的 needle 带 `add(` 前缀 ⇒ **chain_build 阶段 count=1 / dryrun 最终形态 count=0**
  （dryrun 在**全补丁套用后的最终形态**上重跑各脚本 gates()，chain_build 则在**本环中间形态**上跑）
  ⇒ 把 `yl_r138_ext.FRZ_HEADER` 的 needle 去掉 `add(` 前缀（只冻结**文案本身**），两阶段都恰好 1 处。

## 4. 线上验收

- 公网（★ **必须带 `Accept-Encoding: gzip`**，否则看不出 gzip_static 旧壳，见 §5）：
  `index.html` → `<title>摸鱼修仙传</title>` + `assets/index-v2923-20261006.js`；新包 200；旧包 200
- `yl-server` active；`_remote_gz_sync.sh --check` ⇒ **OK=4 / STALE=0 / ORPHAN=0**，`index.html.gz` 与 `index.html` 指向同一包
- 线上 bundle 与本地重建产物 **md5 逐位一致**（`5cd89d35…`）⇒ 仓库 == 线上

## 5. ★★ 本轮最重要的坑：nginx `gzip_static` 长期发陈旧 `index.html.gz`（= R-159）

**症状**：用户打开 `https://moyuwang.online/myxxz/` 看到的是 **11 天前的旧游戏**（界面写「云灵修仙传 v0.3.8」）。

**根因**：
- `nginx.conf` 有 `gzip on;` + **`gzip_static on;`** ⇒ 只要 `X.gz` 存在，nginx **优先把 X.gz 发给浏览器**（真实浏览器都带 `Accept-Encoding: gzip`）。
- `/opt/yl/www/index.html.gz` 是 **2026-09-26 01:59** 生成的**旧壳**，内容为
  `<title>云灵修仙传</title>` + `/yl/assets/index-v26e-20260925.js`（**旧名字 + 旧路径**）；
  而 `index.html` 一直在更新 ⇒ **所有浏览器长期拿到旧壳**。
- 那个旧包 `index-v26e-20260925.js` 里硬编码 `return"0.3.8"` ⇒ 界面显示 **v0.3.8**。
- 同批还发现 `apps/shared.css.gz`（09-25）比明文 `apps/shared.css`（09-28）**陈旧** ⇒ 伴生页样式也在发旧版。
- **为什么长期没被发现**：`curl` 默认**不发** `Accept-Encoding: gzip` ⇒ 冒烟永远拿到明文新壳；
  历史所有 deploy 脚本的 step 4 冒烟也都是明文 curl ⇒ **11 天全程漏检**。

**修法（三层）**：
1. **就地修复**：重建 `index.html.gz`（1158 B，含 `index-v2923-20261006.js` / `摸鱼修仙传` / `/myxxz/`）与 `apps/shared.css.gz`；旧件已备份到 `/root/backup/*.pre-r155-*`。
2. **工具**：新增 `deploy_v28/remote_gz_sync.sh`（全站 `.gz` 与明文逐一 `zcat | cmp` 比对，陈旧即重建；并硬断言 `index.html.gz` 与 `index.html` 指向同一包）；已装到 `/opt/yl/server/_remote_gz_sync.sh`。
3. **管道 fail-closed**：
   - `deploy_v28/live_bump_bundle.js` 在写完 `index.html` 后**必须**重建并校验 `index.html.gz`（含新包引用、无旧包残留），失败即 `exit 1`；
   - `deploy_v2822.sh` step 3 无条件再跑一次 `_remote_gz_sync.sh`（覆盖「bump 被跳过」的重跑场景）；
   - `deploy_v2822.sh` step 4 冒烟新增**浏览器视角**断言：`curl -H 'Accept-Encoding: gzip' | gunzip -c | grep -cF 'assets/$BUNDLE'` 必须 == 1，否则 ABORT。

★ **可复用规矩**：凡 nginx 开 `gzip_static`，**固定文件名的 `.gz` 必须与明文同批重建**；
冒烟必须**至少有一条带 `Accept-Encoding: gzip`**，否则等于没测。

## 6. 本批的缺口（需用户知晓）

- `deploy_v2823.sh` / `remote_check_v2823.sh` / `EXPECT_0823.env` **未留存** ⇒ 0.9.23 没有可复跑的部署件。
  本文件 + §2 指纹 + §3 门禁记录已足以回溯，但**若要重新发布 0.9.23 需先补齐这三件**。
- 建议后续轮次把「**部署件三件套必须与产物一起提交**」写进流程（本轮的事故正是产物与仓库脱节导致的）。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# 0.9.23 → 0.9.22（bundle 名不同，需同时改 index.html + 重建 index.html.gz！）
cp -a /root/backup/index-v2923-20261006.js.pre-r159-<TS> /opt/yl/www/assets/index-v2923-20261006.js  # 或直接指回 v2922
sed -i 's#/myxxz/assets/index-v2923-20261006.js#/myxxz/assets/index-v2922-20261005.js#' /opt/yl/www/index.html
gzip -9 -k -f /opt/yl/www/index.html          # ★ 必须重建，否则 gzip_static 继续发旧壳
bash /opt/yl/server/_remote_gz_sync.sh --check
systemctl restart yl-server && systemctl is-active yl-server
# 0.9.22 定版：bundle=e9c74146e02c9ba638cb0357ef5ed0c7  server=479dcc66a3261c98254367c1cab0f416
```

★ 回滚注意：本批**零 DDL、零服务端改动** ⇒ 无需任何数据库操作，`index.ts` 不必回退。

## 8. 0.9.23 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=5cd89d3522f52ec0fcaf5f659f230504      # index-v2923-20261006.js
PREV_SRV_MD5=479dcc66a3261c98254367c1cab0f416         # s69.r149.ts（69 环，本批未动）
PREV_CHANGELOG_MD5=b04cc322a6e444dfb1624412a97a4631
PREV_DICTS_MD5=1b635513f553875060869272b790f910
```
