# DEPLOY LOG — 《摸鱼修仙传》 1.0 正式版

- 部署时间：2026-10-21 13:42（GMT+8）
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v0100.sh`（登记正本）＋ `_deploy_v0100.py`（paramiko 实际执行，逐段等价，本机无 bash）
- 定点核对：`deploy_v28/remote_check_v0100.sh` → 本地预演 **OK=1183 / SKIP(远端专有)=16 / FAIL=0**；线上实跑 **PASS (0 failures)**（chk×1194 + probe×44）
- 冒烟：`smoke_v100_live.py` → **PASS=20 / FAIL=0**
- 登记指纹：`deploy_v28/EXPECT_0100.env`
- 上一版：0.9.62（2026-10-14），回滚点 bundle `index-v2962-20261011.js`（`c2d13533…`）/ server `bc623f31…`（97 环）
- 备份：`/root/backup/yl_pre_v100_20261021_134248.tar.gz` ＋ `.pre-v100-20261021_134248` 八件
  （index.ts / game-dicts.json / index.html / CHANGELOG.md / CHANGELOG_PLAYER.md / index-v2962 旧包 /
  database.sqlite 热拷贝 / **gm-pro.html 旧版 165,693 B**）
  ★ DB **VACUUM INTO 一致性快照跳过**（远端无 sqlite3 CLI；已留热拷贝 `database.sqlite.pre-v100-…`）
- 本批性质：**客户端 + 服务端 + GM 页三件批**（服务端 97→98 环，**重启了 yl-server**，秒级中断）

---

## 1. 本批范围（1.0；FB-100 玩家反馈三件套 + R-257/R-258 + 版本链 1.0）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| FB-100 | 玩家反馈三件套 | 第 99 环（客户端模块）+ 第 98 环（服务端）+ gm-pro 反馈页 | `localtest/yl_fb100_ext.py`（底部栏第 6 卡 ylbar6 + raw fetch） | `srv_patch_feedback.py`（feedback 表 + POST /api/feedback + GM 列表/改状态 + feedback_inbox.jsonl） |
| R-257 | 寿命「年龄/危险度」日志与历练结算行拆分 | 纯客户端 | `localtest/yl_r257_ext.py` | 无 |
| R-258 | 真关页面停止自动循环 + 补结算日志 | 纯客户端 | `localtest/yl_r258_ext.py` | 无 |
| 版本链 | 0.9.62 → **1.0** | 四件套 | `YLVERSION_FALLBACK = "1.0"`；CHANGELOG/PLAYER 顶部 `## [1.0] - 2026-10-20` | — |

### FB-100 接口契约（三端冻结，字段名一个不能改）

- `POST /api/feedback`（authenticateToken）：入参 `{kind, content, contact?}`，kind ∈ {'bug','suggestion'}；
  客户端固定 6 字段 kind/content/contact/version/realm/ua；5~2000 字校验、60s 限频 409；
  成功 `200 {ok:true,id}` 并**追加一行 JSON** 到 `/opt/yl/server/feedback_inbox.jsonl`（AI 免后台直读通道）
- `GET /api/gm/feedback?limit=&offset=&status=` / `POST /api/gm/feedback/:id/status`（authenticateGM）
- 表 `feedback(id, user_id, username, kind, content, contact, version, realm, ua, status DEFAULT 'open', created_at)`
  —— 启动 DDL 自建，**回滚不删表**（旧代码不读它，无害）
- 客户端**绝不经 Xc()/YlxwPost()**（其 401/403 会强制登出）：raw fetch + 401 静默续期重试一次

### 「反馈」卡位置（★ 与任务书验收表述的偏差，已在任务书裁定）

任务书验收写「反馈按钮在角色左侧」；勘察确认底部栏 5 卡**无「角色」**（角色在顶部 j4 按钮行与抽屉里）。
装配线按裁定方案落地：**底部栏第 6 卡**（容器追加 `ylbar6`，运行时注入 6 列 grid 样式；
`grid-cols-6` 预构建 CSS 不存在故走注入）。线上验收实测：反馈卡位于底部栏
（@1177,770，容器 class 链含 `ylbar6`），「角色」在顶部 header（@730,15）——**不同 UI 区域，
非左右关系**；反馈卡可见、可点、可提交（E2E 全通）。

---

## 2. ★★ 任务书指纹勘误（务必读）

部署任务书给的 bundle 被测指纹 = `c88305b9af37d39e8ed7cebc5736f32a` —— 那是 r256v2 修复重建
**之前**的陈旧中间值（dev + publish 全盘约 2.7 万文件扫描**不存在**该 md5）。

定版依据（三方互证）：
1. 装配线最终 commit `a105f32`（2026-10-21 13:16）明文登记「bundle 指纹→**09c4ace1** r256v2 修复重建……复测 60/60 全绿」；
2. `localtest/t_fb100.py:62` 同值登记（`09c4ace10fc7eaab22550cc550dfd668`）；
3. `_chainstage/dryrun_087.bundle.js` == 交付 bundle **逐字节一致**（09c4ace1，2,372,900 B）。

本批 EXPECT_0100.env / deploy / remote_check / 冒烟全部按 **09c4ace1** 登记。
其余三项指纹（srv `dea7a855…` / CHANGELOG `484a6bd0…` / PLAYER `6c23b0b7…`）与任务书一致。

---

## 3. 指纹（部署前后）

| 对象 | 上一版（0.9.62） | 本批（1.0） |
|---|---|---|
| `www/assets/index-v2962-20261011.js` | `c2d13533179955841df86891f21a1cb8`（线上在跑） | 同左（旧包保留 = 回滚点） |
| `www/assets/index-v2961-20261011.js` | `5e3c732e6a5e019d69a918c9de8f5fd1`（更早回滚点） | 同左 |
| `www/assets/index-v100-20261020.js` | —（新文件） | **`09c4ace10fc7eaab22550cc550dfd668`**（2,372,900 B） |
| `server/index.ts` | `bc623f3117529477157ebdbb413cac88`（97 环） | **`dea7a8553bff3b22f21ad25a0792d66c`**（98 环，1,053,424 B） |
| `www/CHANGELOG.md` | `0df22f63dfade6a6e1e230f4af64b06a` | **`484a6bd0cb04b1d1bbe82f3978e7693a`** |
| `www/CHANGELOG_PLAYER.md` | `425f02bfbb2d5cdca35319e27c50eb01` | **`6c23b0b7ccd0c6ae2ad08ce47c6c780e`** |
| `www/gm-pro/gm-pro.html` | 旧版 165,693 B（@2026-09-30，已备份 `.pre-v100-…`） | **`2f1a2c575ac603ed39676a622112f41e`**（172,090 B，新增「反馈」页） |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（未变） |

部署后线上实测（2026-10-21 13:5x 采集，与上表一致）；`index.html` 引用 = `assets/index-v100-20261020.js`（唯一）；
`yl-server` active，NRestarts=0（ActiveEnterTimestamp = Wed 2026-10-21 13:42:55 CST）。

---

## 4. 部署前本地验收（全绿）

| 环节 | 结果 |
|---|---|
| 交付物指纹 | bundle/srv/dicts/CHANGELOG/PLAYER/gm-pro 六件 md5 全 OK（EXPECT_0100.env） |
| 版本门禁 | `YLVERSION_FALLBACK = "1.0"` ×1；旧 0.9.62 清零 |
| provenance | 交付 bundle == 预演 `dryrun_087.bundle.js`；srv == 链尾 `s98.feedback.ts` == canon；s20 == 0.8.9 定版（前 20 环不变） |
| 玩家日志格式 | 合规 95/95、无独立粗体、无空分类版本、顶部 `## [1.0] - 2026-10-20` |
| `sim_remote_check.py` | **OK=1183 / SKIP(远端专有)=16 / FAIL=0** |

## 5. 线上验收（全绿）

| 环节 | 结果 |
|---|---|
| 部署 | 0→6 步全过：备份 → 服务端 swap（node --check + md5）+ 重启 + **三层健康**（is-active / /api/health / 8s 后 NRestarts 不涨）→ bundle `.new`+md5+mv 原子 → live_bump（平台注入段断言保住）+ gz sync → CHANGELOG×2 → gm-pro（先备份） |
| `remote_check_v0100.sh` 线上实跑 | **PASS (0 failures)**（chk×1194 + probe×44；含 0.9.62 及更早全量回归 + FB-100/R-257/R-258 新断言 + 线上库 feedback 表核对） |
| E2E 验收（一次性脚本，测完已删） | 测试号 `ylui0927a/Test123456` 登录进游戏 ✓ → 反馈卡在底部栏可见 ✓ → 弹窗提交带【部署验收】反馈 → `200 {"ok":true,"id":1}` ✓ → JSONL 尾行核对（user=ylui0927a, kind=bug, version=1.0, realm=炼气期）✓ → GM 口令**只在服务器内存**从 `.env` 读取 → `POST /api/gm/login` + `GET /api/gm/feedback` 命中 id=1 status=open ✓ → **清理**：DB 行 deleted=1、JSONL 过滤后 0 残留，独立复核 grep=0 且 COUNT=0 ✓ |
| `smoke_v100_live.py` | **PASS=20 / FAIL=0**（A 静态 7 + B 服务端 9 + C 浏览器 3 + D 残留 1） |

## 6. 本轮踩到的新坑

| # | 坑 | 处理 |
|---|---|---|
| 1 | **任务书指纹过期**：bundle 在装配线 13:16 复测定版（09c4ace1）之后，任务书仍写重建前的 c88305b9（全盘不存在） | 以最新登记指纹 09c4ace1 部署（三方互证），EXPECT/DEPLOY_LOG 全程显式登记勘误 |
| 2 | **机械派生 remote_check 漏改一处 `$IH` needle**（`assets/index-v2962-…` 未改 `v100`）⇒ 首轮线上 remote_check 1 FAIL（正是 §18.17 警告的「版本号字面漏改」形态；sim 抓不到，因 `$IH` 属远端专有被 SKIP） | 修 needle 后 `--from-step 6` 续跑 → PASS (0 failures)；部署本身无恙（index.html 实际正确） |
| 3 | **服务器无 better-sqlite3，只有 sqlite3 驱动**：验收清理脚本单押 better-sqlite3 ⇒ NO_DRIVER | 清理 v2 双驱动回退（sqlite3 命中）；remote_check 的线上库核对本就双驱动，未受影响 |
| 4 | 测试号 `ylui0927a` 线上**不存在**（登录页提示「道号不存在，请先注册」） | 验收脚本走真实注册流建号（立下长生誓 → 道号 → 天赋 → 难度「开始修仙之旅」）；建号流终钮文案是**「开始修仙之旅」**而非「开始游戏」 |
| 5 | 反馈卡 innerText 形态 = `反馈\nbug · 建议`（label+副题），且 `.ylbar6` 底部栏在部分视图下 rect=0 | 冒烟 C3 判据改为「ylbar6 存在 + grid-template-columns 含 repeat(6) + 文本含反馈」（部署态判据）；可见性与可点性由 E2E 验收单独证明（@1177,770 + 全链路） |

## 7. 残留与说明

- 测试号 `ylui0927a`（Test123456）留在线上（验收中注册），后续批次可复用；如需删除走 GM/DB。
- `feedback_inbox.jsonl` 现为 0 字节（验收行已过滤）；通道完好，下次提交自动追加。
- 远端 `/opt/yl/server/_remote_check_v0100.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` / `_remote_gz_sync.sh` 留存便于复跑（惯例）。
- 验收/诊断一次性脚本与临时截图已全部删除（`_accept_v0100_once.py`、`_tmp_*`、PNG）；GM 口令全程未落盘。

## 8. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回 0.9.62 包
/usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v100-20261020.js --to=index-v2962-20261011.js
# 服务端回 97 环
cp -a /root/backup/index.ts.pre-v100-20261021_134248        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v100-20261021_134248 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v100-20261021_134248    /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v100-20261021_134248 /opt/yl/www/CHANGELOG_PLAYER.md
cp -a /root/backup/gm-pro.html.pre-v100-20261021_134248     /opt/yl/www/gm-pro/gm-pro.html
systemctl restart yl-server && systemctl is-active yl-server
# 0.9.62 定版：bundle=c2d13533179955841df86891f21a1cb8  server=bc623f3117529477157ebdbb413cac88
# 整包：/root/backup/yl_pre_v100_20261021_134248.tar.gz
```

★ 回滚注意：**feedback 表不删**（SKILL §22.15 保留新表；0.9.62 代码不读它，无害）。
玩家端新增 localStorage 键由 FB-100 写入（冷却时间戳），旧代码忽略之，不影响进度。
如需完全还原 DB 用热拷贝 `database.sqlite.pre-v100-20261021_134248`（19,345,408 B）。

## 9. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=09c4ace10fc7eaab22550cc550dfd668
PREV_SRV_MD5=dea7a8553bff3b22f21ad25a0792d66c
PREV_CHANGELOG_MD5=484a6bd0cb04b1d1bbe82f3978e7693a
PREV_PLAYER_MD5=6c23b0b7ccd0c6ae2ad08ce47c6c780e
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=dea7a8553bff3b22f21ad25a0792d66c   # 链尾 _chainstage/s98.feedback.ts
PREV_GMPRO_MD5=2f1a2c575ac603ed39676a622112f41e            # 本批新增登记（gm-pro.html 纳入部署对象）
```
