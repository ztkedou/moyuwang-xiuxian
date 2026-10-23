# DEPLOY LOG — 《摸鱼修仙传》 1.2 正式版

- 部署时间：2026-10-23 13:57（GMT+8，yl-server ActiveEnterTimestamp = Fri 2026-10-23 13:57:15 CST）
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v0102.sh`（登记正本）＋ `_deploy_v0102.py`（paramiko 实际执行，逐段等价，本机无 bash）
- 定点核对：`deploy_v28/remote_check_v0102.sh` → 线上实跑 **PASS (0 failures)**（chk×1264 + probe×45，自 remote_check_v0101.sh 机械派生）
  （首轮实跑曾卡死：PM 块提取对 2.3MB 整文件做 bash 参数展开 `${var%%pat*}` 是 **O(n²)** ⇒ 线上 CPU 空转 13 分钟 + 频道 600s 无输出 PipeTimeout；
  改 `grep -b` 字节偏移 + `tail|head` 切片后 `--from-step 6` 续跑 **30 秒全绿**；部署本体（备份/换环/换包/CHANGELOG）首轮已全绿无恙）
- 冒烟：`smoke_v102_live.py`（EXPECT_VERSION=1.2）→ **PASS=21 / FAIL=0**
- e2e：`e2e_v102_live.py`（一次性，测完已删）→ **PASS=14 / FAIL=0**：布局并排 + 3 条私信全 200 + 信箱可见 + 删行 0 残留
- 登记指纹：`deploy_v28/EXPECT_0102.env`
- 上一版：1.1（2026-10-21 23:11），回滚点 bundle `index-v101-20261021.js`（`75adea61…`）/ server `c7d06f5f…`（99 环 1.1 改写版）
- 备份：`/root/backup/yl_pre_v102_20261023_135707.tar.gz` ＋ `.pre-v102-20261023_135707` 八件
  （index.ts / game-dicts.json / index.html / CHANGELOG.md / CHANGELOG_PLAYER.md / index-v101 旧包 /
  database.sqlite 热拷贝 19,664,896 B / gm-pro.html）
  ★ DB **VACUUM INTO 一致性快照跳过**（远端无 sqlite3 CLI，同 1.0/1.1；已留热拷贝）
- 本批性质：**客户端 + 服务端两件批**（服务端仍 99 环 `srv_patch_pm101.py` **原地改写 1.2**，**重启了 yl-server**，秒级中断）；
  **GM 页零改动**（勿动 gm-pro.html 已兑现：step0b/step4 两次断言线上 gm-pro 仍 = `2f1a2c57…`）
- ★ 勘误存档：部署任务书给的「1.1 回滚基线 CHANGELOG `484a6bd0` / PLAYER `6c23b0b7`」实为 **1.0** 定版值
  （EXPECT_0101.env 的 PREV_* 行）。本批按 1.1 自身定版（EXPECT_0101.env 的 EXPECT_* 行）勘正为
  `cd59314d…` / `66adf623…`，并在 step 0b 以远端实读 md5 逐项比对兜底 —— **实测与勘正值全部吻合**（任务书四指纹本身无误）。

---

## 1. 本批范围（1.2；PM-101 v1.2：私信按钮布局修复 + 私信升级私聊取消限频 + 版本链 1.2）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| PM-101 v1.2·布局 | 「仙友录」好友行：1.1 的「私信」钮直追加行尾把「送礼」挤换行 ⇒ 1.2 按原始结构在姓名 span 收口后并入 `flex items-center gap-1` 同组容器，[送礼钮（或今日已送礼 span）、私信钮] 并排贴右（justify-between 恢复 2 子）；行键 `"f"+N.id` 不变；「在线人物」玩家行维持切磋钮后 `acts.push` 私信钮（DOM 栈，无布局回归） | 纯客户端（yl_pm101_ext v1.2 的 E2①/E2②） | 送礼/私信同组并排，送礼归位 | 无 |
| PM-101 v1.2·取消限频 | 私信升级私聊：删 30s 冷却与 UTC+8 日限 50 | 第 99 环原地改写（客户端 yl_pm101_ext v1.2 + 服务端 srv_patch_pm101.py 1.2） | 写信弹窗删冷却段（`COOLDOWN_MS`/`lastOk` 声明、`wait` 拦截、`lastOk = Date.now()` 记点全删，发送成功直接 `return done`）；409 映射分支留作兼容兜底；门禁冷却清零断言**限域到 PM 块**（防 fb100 同名假失败） | 删 `PM_COOLDOWN_MS` / `PM_DAILY_LIMIT` / `PM_UTC8_OFFSET_MS`、`PM_LAST_SEND_SQL` / `PM_DAILY_COUNT_SQL`、30s 冷却 409「发送太频繁，请稍后再试」与日限 409「今日私信已达上限（50 条）」及 harness 限频用例；登录、收件人非空/存在性、非自己、内容去空格 2~500 字校验逐条保留；★ 独立限流 `pm101Rate`（60s 窗 20 条，超限 429）不在本次指令点名范围、按原样保留，去留待主控裁定 |
| 版本链 | 1.1 → **1.2** | 四件套 | `YLVERSION_FALLBACK = "1.2"`；CHANGELOG/PLAYER 顶部 `## [1.2] - 2026-10-22` | — |

### 玩家可见变化
连发私信不再被 30s 间隔与每日 50 条拦截；仙友录好友行「送礼」「私信」并排不再错位。

---

## 2. 指纹核对结论（本批无勘误）

任务书四指纹与本地交付产物实测**全部一致**，provenance 三方互证：
- `_chainstage/s99.pm101.ts` == `_chainstage/index_v28.v28112.ts` == `srv/index_v28.ts` = `51270cba…`（99 环 1.2 定版）
- `_chainstage/dryrun_087.bundle.js` == `build/assets/index-v102-20261022.js` = `66cf2890…`（2,382,618 B）
- `_chainstage/s20.t16arena.ts` = `7780e099…`（0.8.9 定版，前 20 环不变前提保持）；`s98.feedback.ts` = `dea7a855…`（1.0 链尾不变）
- 上一版（1.1）基线：step 0b 远端实读 bundle `75adea61…` / server `c7d06f5f…` / CHANGELOG `cd59314d…` / PLAYER `66adf623…` / gm-pro `2f1a2c57…` **全吻合**（含上述勘误项）

---

## 3. 指纹（部署前后）

| 对象 | 上一版（1.1） | 本批（1.2） |
|---|---|---|
| `www/assets/index-v101-20261021.js` | `75adea61942d4cc8dd44c922f986e296`（线上在跑） | 同左（旧包保留 = 回滚点） |
| `www/assets/index-v2962-20261011.js` | `c2d13533179955841df86891f21a1cb8`（更早回滚点） | 同左 |
| `www/assets/index-v102-20261022.js` | —（新文件） | **`66cf2890172dc15c8a8fdff9f8c41940`**（2,382,618 B） |
| `server/index.ts` | `c7d06f5f0e0ff26e3a2b625180bebcfb`（99 环 1.1，1,059,851 B） | **`51270cba95846bb75da818d99b012e5c`**（99 环 1.2 原地改写，1,058,383 B） |
| `www/CHANGELOG.md` | `cd59314d533d678a5f27b033681e1164` | **`d288c0bbdc3d4e8a4a0f6f48f1091afe`** |
| `www/CHANGELOG_PLAYER.md` | `66adf623331cde2c2cef3c3a69c9b43a` | **`1adaac999a558bb4cad998ad77d2b39a`** |
| `www/gm-pro/gm-pro.html` | `2f1a2c575ac603ed39676a622112f41e`（172,090 B） | **同左（本批零改动，两次断言未漂移）** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（未变） |

部署后线上实测：`index.html` 引用 = `assets/index-v102-20261022.js`（唯一，旧包引用清零）；
`yl-server` active，NRestarts=0；`mail.kind` 列在库（remote_check 线上库核对 OK）；
gz 旁路同步 OK=4（index.html.gz 已重建并校验含新包）。

---

## 4. 部署前本地验收（全绿）

| 环节 | 结果 |
|---|---|
| 交付物指纹 | bundle/srv/dicts/CHANGELOG/PLAYER 五件 md5 全 OK（EXPECT_0102.env） |
| 版本门禁 | `YLVERSION_FALLBACK = "1.2"` ×1；旧 1.1 / 1.0 / 0.9.x 全清零 |
| provenance | 交付 bundle == 预演 `dryrun_087.bundle.js`；srv == 链尾 `s99.pm101.ts` == canon；s20 == 0.8.9 定版 |
| 玩家日志格式 | 顶部 `## [1.2] - 2026-10-22`、无独立粗体行 |
| `_deploy_v0102.py --dry-run` | 全流程打印正常，本地五件指纹 + provenance 全 OK |

### 1.2 特征串先 grep 再钉（SKILL §18.17；2026-10-23 在交付产物上实测后才写进门禁）
- bundle：`e.jsxs("div", { className: "flex items-center gap-1", children: [N.giftedToday ?`（同组开组）=1、
  三组收口 `children: "\u79c1\u4fe1" })] })] })] }, "f" + N.id); })`=1、私信钮整钉=1、`children: "\u79c1\u4fe1"`=1、
  1.1 旧衔接 `: ""] }), N.giftedToday ? e.jsx("span"`=0、1.1 旧行尾收口=0、
  送礼端点 `f("ft" + N.id, "/friends/gift"`=1、行键 `, "f" + N.id); })`=1、`acts.push(btn("私信"`（raw）=1、
  `fetch(ln + "/mail/send"`=1、`YLPM_`=17（复核不变）/`YLPM_OPEN`=7/`\u79c1\u4fe1`=6、
  版本 `1.2`=1 / `1.1`=0；冷却限域（PM 块切片 8,984 B）：块内 `COOLDOWN_MS`=0 / `lastOk`=0 / `Math.ceil(wait / 1000)`=0，
  全文 `COOLDOWN_MS`=2 / `lastOk`=3 / `Math.ceil(wait / 1000)`=1（恰 fb100 固有，佐证限域口径）
- srv：`[r99pm]`=6（1.2 改写后）、双路由（玩家层 + GM 层）=1+1、`safeAddColumn('mail', 'kind'`=1、
  `UPDATE mail SET kind = 'player' WHERE id = ?`=1、`kind = 'player'`=1（1.1 的 3 → 仅补写 1）、
  `PM_COOLDOWN_MS`/`PM_DAILY_LIMIT`/`PM_UTC8_OFFSET_MS`/`PM_LAST_SEND_SQL`/`PM_DAILY_COUNT_SQL`=0、
  「发送太频繁」/「今日私信已达上限」=0、`pm101Rate(req, res, () => { pm101Send(req, res); });`=1、
  `rateLimit({ windowMs: 60 * 1000, max: 20, keyFn: (req: any) => 'pm:send:'`=1、
  `pm101Dispatch`=4 / `pm101Rate`=2 / `pm101Send`=3 / `pm101InsertPlayerMail`=2、反向对照全 0

---

## 5. 线上验收（全绿）

| 环节 | 结果 |
|---|---|
| 部署 | 0→4 步全过：备份（tar.gz + .pre-v102 八件）→ 服务端 swap（node --check + md5）+ 重启 + **三层健康**（is-active / /api/health / 8s 后 NRestarts 0→0）→ bundle `.new`+md5+mv 原子 → live_bump（平台注入段保留：unified-stats / mw-reward×2；gz 重建校验 + remote_gz_sync OK=4）→ CHANGELOG×2 → gm-pro 未动断言 |
| `remote_check_v0102.sh` 线上实跑 | **PASS (0 failures)**（chk×1264 + probe×45；1.1 及更早全量回归 + 1.2 新断言 + 线上库核对；PM 块提取 markers@814264/823265 切片 8,984 B） |
| E2E（一次性脚本，测完已删；**PASS=14 / FAIL=0**） | ① API 靴带：注册收件号 **ylrecv0927a**（id=22，真注册 API 201）+ ylui0927a→收件号 `/api/friends/add` 200（双向落库）✓ ② ylui0927a 真实登录 → 开「仙友录」→ 好友行几何断言 `{hasGift:true, hasPM:true, sameLine:true, gapPx:4, inSameGroup:true, groupKids:['送礼','私信']}` —— **送礼/私信并排同组、同行、间距 4px** ✓ ③ 对同屏好友 5 秒间隔连发 3 条【部署验收】私信（真实 UI：私信钮 → 弹窗收件人预填 ylrecv0927a → 发送），网络层 **[200, 200, 200]**（30s 冷却已取消实测成立）✓ ④ 收件号真实登录（含新号三步建号向导）→ 开「信箱」→ **3 行私信可见**（`发信人 ylui0927a` ×3 + `回信`钮 ×3）✓ ⑤ 逐行「删除」+ 确认弹窗 → **面板 0 残留** ✓ ⑥ SSH 库复核：`mail` 表 `kind='player'`=0、`content LIKE '%部署验收%'`=0 ✓ |
| e2e 前置清理 | 前两轮调试跑共留 6 行测试私信，均经**应用自身 DELETE 路由**（收件号 Bearer）预清（6→3→0 幂等），未直接动库 ✓ |
| `smoke_v102_live.py`（EXPECT_VERSION=1.2） | **PASS=21 / FAIL=0**（A 静态 7 + B 服务端 9 + C 浏览器 4 + D 残留 1） |

---

## 6. 本轮踩到的新坑

| # | 坑 | 处理 |
|---|---|---|
| 1 | **bash 参数展开 O(n²)**：PM 块限域提取最初用 `${whole#*"$PMSTART"}` / `${pmblk%%"$PMEND"*}`，对 2.3MB 整文件串是平方级 ⇒ 线上 `remote_check` **CPU 97.5% 空转 13 分钟**，paramiko 频道 600s 无输出 PipeTimeout 假死 | 改 `grep -b -o -F` 取 markers 字节偏移 + `tail -c +N | head -c LEN` 切片（毫秒级）；提取失败仍落空文件、守卫断言（块内 `YLPM_SEND`=1）fail-closed。教训：**大文件切片禁用整串参数展开，一律 grep -b + tail/head** |
| 2 | **部署窗口遭遇网络抖动**：首次 SSH 连接 `Error reading SSH protocol banner`（TCP 22 通但空 banner），全部端口 0.00s 假连通（本机 FlClash TUN「Meta」截胡、非 CN 路由的节点瞬时不可用所致）；数分钟后自愈（HTTPS 200 + SSH banner 正常） | 部署前用轻量探针区分「服务器挂了」vs「本机代理路径抖动」（`systemctl is-active` 经 SSH 才算数）；远端长任务改 `setsid nohup` 写日志 + 轮询（`--from-step 6` 续跑不受频道抖动影响） |
| 3 | **新号首登不是直接进游戏**：注册后首次登录落「开始游戏/导入存档」页 → 点「开始游戏」进**三步建号向导**（道号 → 天赋 → 难度）；道号未填时「下一步」点击无效（disabled）；第 0 步「下一步」前进时**自动掷 6 条天赋**；末步按钮文案是「开始修仙之旅」 | e2e 轮询驱动全链：开始游戏 → React 原生 value setter + input 事件填道号（取 **= 用户名**，保证好友行/私信寻址同源）→ 下一步×2 → 开始修仙之旅；16 轮 ×2.5s 内完成 |
| 4 | **信箱行不渲染正文**：私信行只显示标题「来自 X 的私信」+「发信人」span，「【部署验收】」字样不出现在 DOM ⇒ 按内容串数行数恒 0 假 FAIL | 可见性断言改锚「`发信人` span ×3 + `回信`钮 ×3」（发信人徽标只有 player 信才渲染，系统信不计） |

---

## 7. 残留与说明

- 测试号留线上（惯例，供后续批次复用）：`ylui0927a`（Test123456，id=15，1.0 起）＋ **`ylrecv0927a`**（Test123456，id=22，本批新增常备收件号，与 ylui0927a 互为好友、道号=用户名）。
- 测试私信 0 残留（kind='player' 全表 0；【部署验收】全文 0）；feedback/jsonl/chat_messages/users ylfb% 全 0（smoke D1）。
- 远端 `/opt/yl/server/_remote_check_v0102.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` / `_remote_gz_sync.sh` 留存便于复跑（惯例）；`/tmp/_rc0102_*.log`、`/tmp/_ylpm_blk_*.txt` 已清。
- e2e/诊断一次性脚本已全部删除（`e2e_v102_live.py`、`_probe_*`、`_dbg_*`、`_chk144`、`_db_recon`、`_mk_rc0102`、`_recon_cnt_0102`、`_log_facts`、PNG 等）；`_deploy_v0102.py` / `smoke_v102_live.py` 按惯例留存；GM 口令全程未落盘、未使用。
- `smoke_v102_live.py` 留作 1.2 的既有冒烟脚本（下批派生 v103 的母本）。

## 8. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回 1.1 包
/usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v102-20261022.js --to=index-v101-20261021.js
# 服务端回 1.1 定版（99 环 1.1 改写版）
cp -a /root/backup/index.ts.pre-v102-20261023_135707        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v102-20261023_135707 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v102-20261023_135707    /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v102-20261023_135707 /opt/yl/www/CHANGELOG_PLAYER.md
systemctl restart yl-server && systemctl is-active yl-server
# 1.1 定版：bundle=75adea61942d4cc8dd44c922f986e296  server=c7d06f5f0e0ff26e3a2b625180bebcfb
# 整包：/root/backup/yl_pre_v102_20261023_135707.tar.gz
```

★ 回滚注意：**mail.kind 列不删**（SKILL §22.15 保留新表新列）。回滚到 1.1 后 30s 冷却/日限 50 拦截恢复
（客户端 409 兜底分支原样透出服务端 error，不白屏不登出）。如需完全还原 DB 用热拷贝
`database.sqlite.pre-v102-20261023_135707`（19,664,896 B）。

## 9. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=66cf2890172dc15c8a8fdff9f8c41940
PREV_SRV_MD5=51270cba95846bb75da818d99b012e5c
PREV_CHANGELOG_MD5=d288c0bbdc3d4e8a4a0f6f48f1091afe
PREV_PLAYER_MD5=1adaac999a558bb4cad998ad77d2b39a
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=51270cba95846bb75da818d99b012e5c   # 链尾 _chainstage/s99.pm101.ts（99 环原地改写 1.2）
PREV_GMPRO_MD5=2f1a2c575ac603ed39676a622112f41e            # 本批零改动，沿用 1.0 定版
```
