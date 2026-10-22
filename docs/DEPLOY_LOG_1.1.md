# DEPLOY LOG — 《摸鱼修仙传》 1.1 正式版

- 部署时间：2026-10-21 23:11（GMT+8，yl-server ActiveEnterTimestamp = Wed 2026-10-21 23:11:03 CST）
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v0101.sh`（登记正本）＋ `_deploy_v0101.py`（paramiko 实际执行，逐段等价，本机无 bash）
- 定点核对：`deploy_v28/remote_check_v0101.sh` → 本地预演 **OK=1223 / SKIP(远端专有)=17 / FAIL=0**；线上实跑 **PASS (0 failures)**
  （首轮实跑曾 rc=2：派生时「1.0 特征点」段标题 echo 漏了闭合引号 ⇒ bash 语法错误；修 1 字符后 `--from-step 6` 续跑全绿，部署本体无恙）
- 冒烟：`smoke_v101_live.py`（EXPECT_VERSION=1.1）→ **PASS=21 / FAIL=0**
- e2e：`_e2e_v0101_once.py`（一次性，测完已删）→ 私信双向 + 反馈顶栏邻接全通，残留全 0
- 登记指纹：`deploy_v28/EXPECT_0101.env`
- 上一版：1.0（2026-10-21 13:42），回滚点 bundle `index-v100-20261020.js`（`09c4ace1…`）/ server `dea7a855…`（98 环）
- 备份：`/root/backup/yl_pre_v101_20261021_231052.tar.gz` ＋ `.pre-v101-20261021_231052` 八件
  （index.ts / game-dicts.json / index.html / CHANGELOG.md / CHANGELOG_PLAYER.md / index-v100 旧包 /
  database.sqlite 热拷贝 19,558,400 B / gm-pro.html）
  ★ DB **VACUUM INTO 一致性快照跳过**（远端无 sqlite3 CLI，同 1.0；已留热拷贝）
- 本批性质：**客户端 + 服务端两件批**（服务端 98→99 环，**重启了 yl-server**，秒级中断）；
  **GM 页零改动**（勿动 gm-pro.html 已兑现：step0b/step4 两次断言线上 gm-pro 仍 = `2f1a2c57…`）

---

## 1. 本批范围（1.1；FB-100 反馈入口迁移 + PM-101 玩家私信 + 版本链 1.1）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| FB-100 v2 | 反馈入口迁移：底栏 6 卡回退 5 卡，「反馈」迁**顶栏「角色」左侧紧邻**（amber 内联样式+红点角标）+ 移动端 ☰ 抽屉「设置」前等价入口 | 纯客户端（yl_fb100_ext v2） | 提交链路（raw fetch `/api/feedback` + 401 pS() 续期重试恰一次 + 60s 冷却）逐字节保持 1.0 | 无 |
| PM-101 | 玩家私信：写信弹窗 + 仙友录/在线人物「私信」钮 + 信箱行「发信人/回信」 | 第 99 环（客户端 standalone yl_pm101_ext + 服务端 srv_patch_pm101.py） | `YL_PM101_V1`（raw fetch `/api/mail/send` + jo() Bearer；401→pS() 重试恰一次；绝不经 Xc/YlxwPost；30s 冷却仅成功记；2~500 字预校验；`__YLPM_CUR` 测试钩子） | mail 表加 `kind` 列（safeAddColumn 幂等，默认 'system'，**回滚不删列**）+ `POST /api/mail/send`（pm101Dispatch 按 Bearer 分流：合法玩家 token → 30s 冷却 409 / UTC+8 日限 50 条 409 → to 存在性/to≠自己/2~500 字校验 400 → insertMail(lingshi=0) + `UPDATE kind='player'`；过期 token 401；GM 串/垃圾/无 Bearer → next() 落既有 GM 发信路由，GM 端点零改动） |
| 版本链 | 1.0 → **1.1** | 四件套 | `YLVERSION_FALLBACK = "1.1"`；CHANGELOG/PLAYER 顶部 `## [1.1] - 2026-10-21` | — |

### 主控裁定存档（2026-10-21 escalate，选 A）
私信**绝不写 chat_messages**（该表被玩家世界聊天无过滤轮询，写入即向全体玩家泄漏）。
e2e 已核：`chat_messages` 无「部署验收」行（`SELECT COUNT(*) WHERE text LIKE '%部署验收%'` = 0，文本列为 `text`）。
GM 侧审核私信按 B 方案（/api/gm/messages UNION + DELETE 分流）另行立项 —— 本批 GM 消息页可见信箱邮件即可。

### 「反馈」顶栏验收口径
e2e 实测（1280 视口）：header 内「反馈」钮与「角色」钮**同行**（中线差 <6px）、反馈在左、右缘到角色左缘间距 **4px**
（`{found:true, sameRow:true, fbLeftOfRole:true, gap:4}`）；弹窗 `.ylfb-box` 打开、提交成功（msg 含成功态，DB 行 kind=bug/version=1.1）。

---

## 2. 指纹核对结论（本批无勘误）

任务书四指纹与本地交付产物实测**全部一致**，provenance 三方互证：
- `_chainstage/s99.pm101.ts` == `_chainstage/index_v28.v28112.ts` == `srv/index_v28.ts` = `c7d06f5f…`（99 环）
- `_chainstage/dryrun_087.bundle.js` == `build/assets/index-v101-20261021.js` = `75adea61…`（2,382,801 B）
- `_chainstage/s20.t16arena.ts` = `7780e099…`（0.8.9 定版，前 20 环不变前提保持）
- 上一版（1.0）四指纹取自 `EXPECT_0100.env` / `DEPLOY_LOG_1.0.md §9`，与部署前远端实测一致。

---

## 3. 指纹（部署前后）

| 对象 | 上一版（1.0） | 本批（1.1） |
|---|---|---|
| `www/assets/index-v100-20261020.js` | `09c4ace10fc7eaab22550cc550dfd668`（线上在跑） | 同左（旧包保留 = 回滚点） |
| `www/assets/index-v2962-20261011.js` | `c2d13533179955841df86891f21a1cb8`（更早回滚点） | 同左 |
| `www/assets/index-v101-20261021.js` | —（新文件） | **`75adea61942d4cc8dd44c922f986e296`**（2,382,801 B） |
| `server/index.ts` | `dea7a8553bff3b22f21ad25a0792d66c`（98 环，1,053,424 B） | **`c7d06f5f0e0ff26e3a2b625180bebcfb`**（99 环，1,059,851 B） |
| `www/CHANGELOG.md` | `484a6bd0cb04b1d1bbe82f3978e7693a` | **`cd59314d533d678a5f27b033681e1164`** |
| `www/CHANGELOG_PLAYER.md` | `6c23b0b7ccd0c6ae2ad08ce47c6c780e` | **`66adf623331cde2c2cef3c3a69c9b43a`** |
| `www/gm-pro/gm-pro.html` | `2f1a2c575ac603ed39676a622112f41e`（172,090 B） | **同左（本批零改动，两次断言未漂移）** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（未变） |

部署后线上实测（2026-10-21 23:5x 采集）：`index.html` 引用 = `assets/index-v101-20261021.js`（唯一）；
`yl-server` active，NRestarts=0；`mail.kind` 列已落库（remote_check 线上库核对 `newcol mail.kind yes`）。

---

## 4. 部署前本地验收（全绿）

| 环节 | 结果 |
|---|---|
| 交付物指纹 | bundle/srv/dicts/CHANGELOG/PLAYER 五件 md5 全 OK（EXPECT_0101.env；★ 本批无 EXPECT_GMPRO —— GM 页零改动） |
| 版本门禁 | `YLVERSION_FALLBACK = "1.1"` ×1；旧 1.0 / 0.9.x 全清零 |
| provenance | 交付 bundle == 预演 `dryrun_087.bundle.js`；srv == 链尾 `s99.pm101.ts` == canon；s20 == 0.8.9 定版 |
| 玩家日志格式 | 顶部 `## [1.1] - 2026-10-21`、无独立粗体行 |
| `sim_remote_check.py --script deploy_v28/remote_check_v0101.sh` | **OK=1223 / SKIP(远端专有)=17 / FAIL=0** |
| 引号配平 | 逐行 shell 状态机核 remote_check_v0101.sh = 0 不配平行（v0100 同法对照 0） |

### 1.1 特征串先 grep 再钉（SKILL §18.17；在交付产物上实测后才写进门禁）
- bundle：`YLPM_`=17（OPEN 7 / SUBMIT 6 / CUR 2 / SEND 2）、`window.YLPM_OPEN = function`=1、
  `fetch(ln + "/mail/send"`=1、`window.__YLPM_CUR`=2、`\u56de\u4fe1`=1、`\u53d1\u4fe1\u4eba`=1、
  回信判定 `(g.kind === "player" || (!g.kind && g.sender && g.sender !== "system"))`=2、
  顶栏 amber `borderColor:"#f59e0b",background:"#451a03"`=1、反馈↔角色邻接形态=1、抽屉等价入口=1、
  `YLFB_`=19（=1.0 的 17 + 顶栏/抽屉 2 新守卫）、`ylbar6`=0（回退清零）、raw `反馈`=4、`chat_messages`=0
- srv：`[r99pm]`=11、`app.post('/api/mail/send', pm101Dispatch);`=1、GM 发信路由保留=1、
  `safeAddColumn('mail', 'kind'`=1、`UPDATE mail SET kind = 'player' WHERE id = ?`=1、
  `kind = 'player'`=3、PM_COOLDOWN_MS=1 / PM_DAILY_LIMIT=1 / PM_UTC8_OFFSET_MS=1、
  pm101Dispatch=4 / pm101Rate=2 / pm101Send=3 / pm101InsertPlayerMail=2、反向对照全 0

---

## 5. 线上验收（全绿）

| 环节 | 结果 |
|---|---|
| 部署 | 0→6 步全过：备份（tar.gz + .pre-v101 八件）→ 服务端 swap（node --check + md5）+ 重启 + **三层健康**（is-active / /api/health / 8s 后 NRestarts 0→0）→ bundle `.new`+md5+mv 原子 → live_bump（平台注入段保留：unified-stats / mw-reward×2；gz 重建校验 + remote_gz_sync OK=4）→ CHANGELOG×2 → gm-pro 未动断言 |
| `remote_check_v0101.sh` 线上实跑 | **PASS (0 failures)**（chk×1240 + probe×45；1.0 及更早全量回归 + 1.1 新断言 + 线上库核对含 `mail.kind 加列已落库`） |
| E2E（一次性脚本，测完已删） | ① ylui0927a 登录 ✓ ② 注册 ylfb1021d（真注册流：立下长生誓 → 道号 → 真言+确认真言 → 开始修仙之旅）✓ ③ 顶栏「反馈」紧邻「角色」（gap=4px）→ 提交【部署验收】反馈成功 ✓ ④ 在线人物面板（在线 3 人，ylui 在 5 分钟窗口内）→ ylui 行「私信」钮 → 弹窗收件人预填 `ylui0927a` → 发【部署验收】私信成功 ✓ ⑤ ylui 信箱可见 `来自 ylfb1021d 的私信 / 发信人 ylfb1021d / 回信` → 回信弹窗收件人预填 → 回信成功 ✓ ⑥ 临时号信箱可见 `来自 ylui0927a 的私信 / 发信人 ylui0927a` ✓ ⑦ SSH：`mail` 表 `kind='player'` **恰两行**（id=49 ylfb1021d→ylui / id=50 ylui→ylfb1021d）、feedback 本轮 +1 行（id=5，kind=bug/version=1.1）、`chat_messages` 零写入 ✓ |
| 清理（e2e 后） | 私信 2 行删除（changes=2）✓；feedback 验收行 4 行删除（前 3 轮 e2e 各留 1 行一并清，changes=4）✓；`feedback_inbox.jsonl` 过滤 1368→0 B ✓；临时号 ylfb1021a/b/c/d 按 `q_cleanup.js` 惯例整删（saves/rankings/daily_quests/stats_daily/chronicle/economy_ledger/refresh_tokens/save_snapshots/active_sessions/activity_rain_state/users 全清，清理后剩余=[]）✓；**0 残留复核**：mail=0 / feedback=0 / users ylfb%=0 / jsonl=0 / chat_messages=0 ✓；`ylui0927a` 保留（1.0 惯例，id=15）✓ |
| `smoke_v101_live.py`（EXPECT_VERSION=1.1） | **PASS=21 / FAIL=0**（A 静态 7 + B 服务端 9 + C 浏览器 4 + D 残留 1） |

---

## 6. 本轮踩到的新坑

| # | 坑 | 处理 |
|---|---|---|
| 1 | **机械派生 remote_check 漏闭合引号**：「1.0 特征点」段标题 `echo "--- …---"` 少写 `"` ⇒ bash 在其后 15 行报 `syntax error near unexpected token '('`（首轮线上实跑 rc=2，卡在部署判定位） | 逐行 shell 引号状态机核配平（v0101 与 v0100 对照）修 1 字符 → `--from-step 6` 续跑 PASS；部署本体（备份/换环/换包）无恙。教训入坑单：**派生类脚本必须跑「逐行引号状态机」+ sim 双门禁**，sim 只解析 chk 行、抓不到 echo 语法错误 |
| 2 | **e2e 注册表单是三件套**：新号注册有「确认真言」框（占位「请再次输入真言」），1.0 smoke 的轮询只填道号 ⇒ 点「立下长生誓」永远不过（截图实锤） | 轮询循环补：道号 + 真言（空才填）+ 确认真言（不等才填）三 set + 按钮点击 |
| 3 | **新号进游戏有「修仙法门」引导弹窗**（9 行逐秒显示 +「点击任意位置关闭」），盖住顶栏徽章；其关闭 × 是**图标无文本**，文本匹配抓不到；且页面 elementFromPoint/offsetParent 判据不可靠 | 从「修仙法门」标题向上爬容器拿第一个 button 点掉；并放弃 hit-test 确认——**evaluate 级 click 不经命中测试**，只需确认标题消失 + 徽章在位 |
| 4 | **`closest('div')` 行匹配陷阱**：在线人物行的「私信」钮最近 div 祖先 = 按钮条 div（不含玩家名）⇒ 「行内出现私信钮」判据恒 false（面板实际已打开、行已在——截图实锤） | 改为「按钮向上爬 ≤5 层祖先，任一层 innerText 含玩家名」判据（信箱行「回信」钮同法） |
| 5 | **`grep -c … \|\| echo 0` 双行输出**：grep -c 无命中时**打印 0 且退出码 1** ⇒ `\|\| echo 0` 再补一行 0 ⇒ `raw='0\n0'` 断言假 FAIL | 命令尾改 `; true`，只取首行 |
| 6 | **chat_messages 没有 `content` 列**（实际列 = id/username/text/created_at）⇒ 按 content 查残留直接 SQLITE_ERROR | 先 `PRAGMA table_info` 实查列名再查（不猜列名） |
| 7 | **e2e 多轮重跑的记账污染**：每轮注册新临时号都会新发一条反馈 ⇒ 「feedback 恰 1 行」按轮累计成 4 行（kind=bug/version=1.1 全对，产品无恙） | 复核口径改为「每轮恰 +1 行且 username 唯一」（实测 a/b/c/d 各 1）；清理时 4 行全删 + 0 残留复核兜底 |

---

## 7. 残留与说明

- 测试号 `ylui0927a`（Test123456，id=15）留在线上（1.0 起沿用），后续批次可复用；临时号 ylfb1021a/b/c/d 已整删。
- `feedback_inbox.jsonl` 现 0 字节（验收行已过滤）；通道完好。
- 远端 `/opt/yl/server/_remote_check_v0101.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` / `_remote_gz_sync.sh` 留存便于复跑（惯例）。
- e2e/诊断一次性脚本与临时截图已全部删除（`_e2e_v0101_once.py`、`_tmp_*`、PNG）；GM 口令全程未落盘、未使用。
- `smoke_v101_live.py` 留作 1.1 的既有冒烟脚本（下批派生 v102 的母本）。

## 8. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回 1.0 包
/usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v101-20261021.js --to=index-v100-20261020.js
# 服务端回 98 环
cp -a /root/backup/index.ts.pre-v101-20261021_231052        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v101-20261021_231052 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v101-20261021_231052    /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v101-20261021_231052 /opt/yl/www/CHANGELOG_PLAYER.md
systemctl restart yl-server && systemctl is-active yl-server
# 1.0 定版：bundle=09c4ace10fc7eaab22550cc550dfd668  server=dea7a8553bff3b22f21ad25a0792d66c
# 整包：/root/backup/yl_pre_v101_20261021_231052.tar.gz
```

★ 回滚注意：**mail.kind 列不删**（SKILL §22.15 保留新表新列；1.0 代码不认识它，无害）。
已发出的私信行回滚后仍留在 mail 表（旧代码按无 kind 读取，sender≠system 的行 1.0 客户端正常展示，不带回信钮/发信人徽标）。
如需完全还原 DB 用热拷贝 `database.sqlite.pre-v101-20261021_231052`（19,558,400 B）。

## 9. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=75adea61942d4cc8dd44c922f986e296
PREV_SRV_MD5=c7d06f5f0e0ff26e3a2b625180bebcfb
PREV_CHANGELOG_MD5=cd59314d533d678a5f27b033681e1164
PREV_PLAYER_MD5=66adf623331cde2c2cef3c3a69c9b43a
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=c7d06f5f0e0ff26e3a2b625180bebcfb   # 链尾 _chainstage/s99.pm101.ts
PREV_GMPRO_MD5=2f1a2c575ac603ed39676a622112f41e            # 本批零改动，沿用 1.0 定版
```
