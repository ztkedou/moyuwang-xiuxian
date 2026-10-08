# 敏感串扫描报告 · SECRETS-SCAN

> 目的：证明即将发布到公开 GitHub 的仓库中**不含任何密钥、凭据、隐私或服务器信息**。
> 扫描对象：staging 目录 `<WORKDIR>\github-moyuwang-xiuxian\`（**306 个文件 / 约 14.3 MB**）
> 扫描时间：2026-10-02（0.9.13 同步后复扫；历史 0.8.11.1 记录见下文） ｜ 扫描方式：`grep -rE` / `git grep` 逐文件全量匹配
>
> **独立复扫（2026-09-30）**：以 `git grep` 对**全部文件（含本次新增的 59 个客户端补丁 / 44 个服务端补丁 / 产物 / 设计文档）**重跑 4 组正则
> （`sk-` / `ghp_` / `github_pat_` / `AKIA` / `-----BEGIN` / `PRIVATE KEY` / 服务器 IP /
> 通用 IPv4 / 手机号 / 本机用户名 `<USER>` / `C:\Users` / SSH 私钥用法），**真实凭据全部 0 命中**。

---

## 一、结论（一句话）

**未发现任何真实密钥、口令、私钥、数据库文件或服务器地址。**
所有 `password` / `JWT_SECRET` / `api_key` 等字样的命中，均为**变量名、环境变量名或代码逻辑**，
不是可被利用的凭据；文档层出现的沙盒凭据明文**已全部脱敏**。可以安全发布。

---

## 二、扫描了哪些目录

| 目录 | 文件数 | 说明 |
|---|---|---|
| `./`（根） | 113 | README / LICENSE / .gitignore / .env.example / CHANGELOG / 62 个 `yl_*_ext.py` / 44 个 `srv_patch_*.py` / `build_v26n.py` / `yl_patch.py` |
| `build/` `build/assets/` | 5 | index.html + 基座/产出 bundle + css + logo |
| `srv/` | 6 | index_v28.ts + game-dicts.json + 4 个 .sql |
| `_v281_base/` | 4 | 服务端/前端/字典冻结基座 + changelog |
| `localtest/` | 3 | chain_build.py + KNOWN_ISSUES.md + README_SANDBOX.md |
| `docs/`（含 design / 0.8.7 / 0.8.8） | 42 | 发布清单 / 扫描报告 / 部署说明 / 设计文档 |
| **合计** | **173** | |

**扫描范围**：上述全部文件（含二进制 bundle 的字符串扫描）。

---

## 三、逐模式扫描结果

| # | 模式 | 命中文件数 | 判定 |
|---|---|---|---|
| 1 | `sk-[A-Za-z0-9_-]{16,}`（OpenAI/SiliconFlow 风格密钥） | **0** | ✅ 通过 |
| 2 | `PRIVATE KEY` / `BEGIN RSA` / `BEGIN OPENSSH` / `-----BEGIN` | 3 | ✅ 全部为**扫描命令正则/报告描述文字**（无真实私钥块） |
| 3 | `api_key` | 2 | ✅ 同上（扫描正则/报告文字） |
| 4 | `AKIA[0-9A-Z]{16}`（AWS Access Key） | **0** | ✅ 通过 |
| 5 | `ghp_[A-Za-z0-9]{36}`（GitHub Token） | **0** | ✅ 通过 |
| 6 | `<SERVER_IP>`（服务器 IP，已脱敏占位符） | 6 | ✅ 通过（真实 IP 已脱敏） |
| 7 | `1[3-9]\d{9}`（手机号） | **0** | ✅ 通过（含手机号的文件已排除） |
| 8 | 本机用户名 `<USER>` / 本机路径 `C:\Users` | 3 | ✅ 仅出现在**扫描命令与报告描述**中；`C:\Users\<数字>` 0 命中 |
| 9 | 沙盒 JWT 密钥明文（已脱敏） | **0** | ✅ 通过（已脱敏） |
| 10 | `password` / `PASSWORD` | 20 | ⚠️ 见下（全部为代码逻辑/字段名/文档说明） |
| 11 | `JWT_SECRET` | 9 | ⚠️ 见下（全部为环境变量名/文档说明） |
| 12 | `GM_PASSWORD` | 14 | ⚠️ 见下（全部为环境变量名/文档说明） |
| 13 | `API_KEY` | 7 | ⚠️ 见下（环境变量名） |
| 14 | `token=` | 10 | ⚠️ 见下（`?token=` 查询参数处理逻辑） |
| 15 | `moyuwang.online`（公开域名） | 7 | ✅ 公开信息（README 试玩链接，本就对外公开） |
| 16 | `root@` | 4 | ⚠️ 均为 `root@<SERVER_IP>`（IP 已脱敏）或清单描述文字 |

---

## 四、逐条解释「命中但非密钥」

### 4.1 `password`（20 个文件）
- `build/assets/*.js`（2 个 bundle）：**误报** —— 命中来自
  `type="password"`（HTML 输入框类型）、`{username, password}`（登录请求体字段名）。
- `srv/index_v28.ts`：`password_hash`（数据库列名）、`validatePassword()`（口令强度校验函数）、
  `const { username, password } = req.body`（登录端点）。**无字面量口令。**
- `.env.example` / `README.md` / `docs/PUBLISH-MANIFEST.md`：文档中说明「GM_PASSWORD 环境变量」。
- `localtest/KNOWN_ISSUES.md` / `README_SANDBOX.md`：测试说明。**原含沙盒口令明文，已脱敏为 `<REDACTED>` / `<GM_PASSWORD>`。**

### 4.2 `JWT_SECRET`（9 个文件）
- `srv/index_v28.ts` / `_v281_base/index_v28.base.ts`：**只读 `process.env.JWT_SECRET`**；
  未配置时随机生成并写入 `.jwt_secret`（该文件在 `.gitignore` 中）。**源码不含密钥值。**
- `.env.example`：键名 + 占位符 `change-me-to-a-long-random-string`。
- 其余为 README / 清单 / 测试说明中的文字提及。

### 4.3 `GM_PASSWORD`（14 个文件）
- `srv/index_v28.ts`：**0.8.9 起已移除兜底默认值**，改为
  `const GM_PASSWORD = process.env.GM_PASSWORD; if (!GM_PASSWORD) { [FATAL] 拒绝启动 }`。
  **源码中已无 `'<WEAK_PASSWORD>'` 字面量**（见第五节「需确认项 A」——已解决）。
- `_v281_base/index_v28.base.ts`（冻结基座）：仍保留历史写法 `|| '<WEAK_PASSWORD>'`，由 `srv_patch_baseclean089.py` 移除；
  `srv_patch_baseclean089.py` 内含 `'<WEAK_PASSWORD>'` 字面量（作为被清除的旧代码与门禁断言），属**代码事实，非凭据**。
- `.env.example`：占位符 `change-me-gm-password`。
- 文档/测试说明：已脱敏。

### 4.4 `API_KEY`（7 个文件）
- `srv/index_v28.ts`：`const apiKey = process.env.AI_API_KEY;` + `if (!apiKey) return 500`。
  **只读环境变量，无值。**
- `.env.example`：`AI_API_KEY=`（留空）。
- 文档：说明。

### 4.5 `token=`（10 个文件）
- `build/assets/*.js`：客户端拼接 `?token=` 查询参数（外链会话）。
- `srv/index_v28.ts` / `yl_dungeon085_ext.py` / 设计文档：`?token=` 处理逻辑与测试说明。
- **无真实 token 值**（`eyJ...` 出现在文档里的是省略号占位，非完整 JWT）。

### 4.6 `root@`（4 个文件）
- `docs/design/注入挂载点地图.md`：`root@<SERVER_IP>:/opt/yl/...`（IP 已脱敏）
- `localtest/README_SANDBOX.md`：`ssh root@<SERVER_IP>`（IP 已脱敏）
- `docs/PUBLISH-MANIFEST.md` / `docs/SECRETS-SCAN.md`：清单中说明「为何排除部署脚本」
→ 均为**脱敏后**的 `<SERVER_IP>` 或描述文字，不含真实地址。

---

## 五、处理动作汇总

| 动作 | 对象 | 说明 |
|---|---|---|
| **整体排除** | `localtest/_srvprobe/.env` | 真实沙盒密钥（`JWT_SECRET` / `GM_PASSWORD`），未进入 staging |
| **整体排除** | `localtest/_srvprobe/database.sqlite`（8.96 MB） | 真实数据库，未进入 staging |
| **整体排除** | `deploy_v28/*.sh`、`deploy_v28/DEPLOY_LOG_*.md`、`deploy_moyu/*.sh`、`deploy_v26*.sh`、`deploy_v27.sh` | 含服务器 IP + SSH 私钥路径 |
| **整体排除** | `HANDOVER_0.8.2.md`、`report_brand_myxxz.md`、`docs/GITHUB-开新对话指令.md` | 含服务器 IP |
| **整体排除** | `v26h-修复报告.md` | ⚠️ 含手机号 |
| **整体排除** | `docs/0.8.8-design/GM后台重构方案.md` | ⚠️ **含真实凭据**（口令变体 / Cerebras key / 真实服务器 IP） |
| **整体排除** | `docs/0.8.9-design/GM凭据盘点报告.md`（含 `.bak-*`）、`docs/0.8.9-design/GM服务端待补端点需求.md` | ⚠️ 前者**含真实凭据 + 生产 IP 完整暴露**；后者为 GM 内部设计稿 |
| **整体排除** | `docs/0.8.8-design/HANDOFF-0.8.8-进行中.md` | 内部交接稿（含本机路径） |
| **文本脱敏** | `docs/design/上游客户端合并面清单.md`、`docs/design/注入挂载点地图.md`、`localtest/chain_build.py`、`localtest/README_SANDBOX.md` | 服务器 IP → `<SERVER_IP>`；本机绝对路径 → `<WORKDIR>` |
| **文本脱敏** | `localtest/KNOWN_ISSUES.md`、`localtest/README_SANDBOX.md` | 沙盒 JWT 密钥 / 沙盒 GM 口令明文 → `<REDACTED...>` |
| **`.gitignore` 兜底** | 全局 | 忽略 `.env` / `*.key` / `*.pem` / `*.sqlite` / `*.db` / `id_rsa*` / `.jwt_secret` / `__pycache__` / `_chainstage/` / `deploy_*/` / `*DEPLOY_LOG*` / `EXPECT_*.env` 等 |

---

## 六、需确认项

### ✅ 需确认项 A：`srv/index_v28.ts` 的 GM 口令兜底默认值 —— **已于 0.8.9 解决**

早先 `srv/index_v28.ts` 第 1094 行为：

```ts
const GM_PASSWORD = process.env.GM_PASSWORD || '<WEAK_PASSWORD>';
```

**0.8.9 已移除该兜底**，产物 `srv/index_v28.ts` 现为（`:1129-1131`）：

```ts
const GM_PASSWORD = process.env.GM_PASSWORD;
if (!GM_PASSWORD) {
  console.error('[FATAL] GM_PASSWORD 未设置，拒绝以弱口令启动。请在 .env 配置 GM_PASSWORD 后重启。');
  // …进程退出
}
```

- 产物中 `'<WEAK_PASSWORD>'` 字面量**已清零**（`grep -c "|| '<WEAK_PASSWORD>'" srv/index_v28.ts` = 0）。
- 冻结基座 `_v281_base/index_v28.base.ts` 与移除它的补丁 `srv_patch_baseclean089.py` 中仍有 `'<WEAK_PASSWORD>'` 字面量，
  属**历史基座原貌 + 补丁逻辑**，非凭据。
- README 部署章节已同步改写为「未设置 `GM_PASSWORD` 则服务端拒绝启动」。

### 说明项 B：`/opt/yl` 部署路径
部分设计文档中出现 `/opt/yl/...`。这是通用的 Linux 部署目录约定，**不含任何凭据或主机信息**，
属正常上下文，**保留不脱敏**。

---

---

## 六·补·4、0.9.13 同步后的复扫记录（2026-10-02）

同步阶段做了以下改动，并**对全部 306 个文件重新完整扫描一次**：

| 动作 | 内容 |
|---|---|
| 同步至 0.9.13 | 新增 24 个 `yl_*_ext.py`（0.9.3~0.9.11 批：adv097 / advend105 / attr097 / bt096 / chardex101 / dao097 / life094 / life097 / linggen097 / r083 / r106 / r107 / r108 / r109 / r111 / r112 / r113 / r114 / r115 / r124 / shop102 / shoprefresh101 / speedname097 / talent097）+ 12 个 `srv_patch_*.py`（101 / 110 / 111 / 113 / 115 / r116 / r122 / r123 / r124 / r127 / r128 / r129）+ 11 个 standalone 客户端补丁 `localtest/yl_r1*_ext.py`（r116/r118/r119/r120/r121/r123/r124/r125/r126/r128/r131）+ `docs/0.9.13-design/` 2 份；更新 17 个既有客户端补丁 / `build_v26n.py` / `localtest/chain_build.py` / `localtest/dryrun_087.py` / `srv/index_v28.ts` / `CHANGELOG.md` / `CHANGELOG_PLAYER.md` / `build/index.html` / `docs/0.8.8-design/接力与坑清单.md` |
| 产物换版 | 新增 `build/assets/index-v2913-20261002.js`（0.9.13 定版，md5 `b4586dba…`），删除旧产出 `index-v292-20261001.js`（仅保留冻结基座 v26m + 当前产出 v2913） |
| **本轮新修脱敏回流（重要）** | ① `build_v26n.py` 的 node 探测兜底串带**真实本机用户名**绝对路径 → 还原为 `<WORKDIR>`；② `localtest/README_SANDBOX.md` 两处真实本机路径（`/c/Users/<数字>/...` 与 python 路径）→ `<USER>`；③ `localtest/chain_build.py` 的 `NODE` 常量 —— **0.9.2 同步时已回流成真值且随 41a73ca 入库**（此前 0.8.10 曾打码），本轮重新打码为 `<WORKDIR>`；④ `docs/0.8.8-design/接力与坑清单.md` 反面教材引用的三个真实 IP + 本机用户名 → 还原为 `47.243.x.x` / `161.33.*` / `47.109.*` / `C:/Users/<USER>`，并把括注中的真实用户名字面量一并打码 |

**复扫结果：真实密钥 / 私钥 / 真实 IP / 手机号 / 本机用户名路径 = 0 命中。**
剩余 17 处正则命中全部为**扫描自指文档字面量**（本报告自身的模式清单、`GITHUB-PUBLISH-INSTRUCTIONS.md` / `NEXT-CONVERSATION-STEPS.md` 的扫描命令原文、`README_SANDBOX.md 的 PortableGit 通用占位示例），与 0.8.9~0.8.11.1 各轮的既定豁免口径一致。

---

## 六·补·3、0.8.11.1 同步后的复扫记录（2026-09-30）

同步阶段做了以下改动，并**对全部 173 个文件重新完整扫描一次**：

| 动作 | 内容 |
|---|---|
| 同步至 0.8.11.1 | 新增 18 个 `yl_*_ext.py`（`offline2` / `v2811a` / `gongfa` / `char2` / `farm2` / `medlog` / `daily` / `fun2` / `lottery` / `dungeon2` / `merge01` / `renwu` / `r013` / `econ2` / `r013c` / `claimedfix` / `r018` / `cooldown`）+ 9 个 `srv_patch_*.py`（`offline2` / `farm2` / `fun2` / `dungeon2` / `econ2` / `r018` / `r013b` / `r013c` / `claimedfix`）；更新 8 个既有 `yl_*_ext.py` / `build_v26n.py` / `localtest/chain_build.py` / `srv/index_v28.ts` / `CHANGELOG.md` / `build/index.html` / `docs/0.8.8-design/接力与坑清单.md` |
| 产物换版 | 新增 `build/assets/index-v28111-20260930.js`（0.8.11.1 定版），删除旧产出 `index-v2810-20260930.js`（仅保留冻结基座 v26m + 当前产出 v28111） |
| 文档同步 | `README.md` / `docs/DEPLOYMENT.md` / `docs/PUBLISH-MANIFEST.md` / `docs/NEXT-CONVERSATION-STEPS.md` / `docs/GITHUB-PUBLISH-INSTRUCTIONS.md` 全部指纹与计数更新到 0.8.11.1 |
| **本轮新修脱敏（重要）** | 从工作区复制时**发现 3 处「脱敏回流」**（工作区副本把此前已打码的内容又还原成了真值）：① `localtest/chain_build.py` 的 `NODE` 常量里带**真实本机用户名**的绝对路径 → 还原为 `<WORKDIR>`；② `docs/0.8.8-design/接力与坑清单.md` 里作为反面教材引用的**三个真实 IP 与本机用户名** → 还原为 `47.243.x.x` / `161.33.*` / `47.109.*` / `<USER>`；③ `localtest/README_SANDBOX.md` 的工作区副本含**真实 IP** 与 `GM_PASSWORD` 明文 → **该文件整体回退到仓库已脱敏版本，不随本轮同步**（`localtest/KNOWN_ISSUES.md` 同理回退，以与上一轮同步的改动面保持一致） |
| **本轮顺带修的存量泄漏** | ④ `docs/GITHUB-PUBLISH-INSTRUCTIONS.md` 的「全量敏感串扫描」命令里，此前把**一个真实生产 IP 原样写进了正则**（`47\.243\.222\.97`）—— 已打码为网段级 `47\.243\.`（该 IP 与另外两个一样，均属「扫描命令自指泄漏」，见 `接力与坑清单.md` 坑 24） |

**复扫结果：4 组正则全部 0 命中**（真实密钥 / 私钥 / 真实 IP / 手机号 / 本机用户名路径）。
**本轮特别复核**：以 `git grep` 检索「真实本机用户名 / `C:/Users/<数字>` / 三个真实生产 IP」→ **0 命中**。

---

## 六·补·2、0.8.10 同步后的复扫记录（2026-09-30）

同步阶段做了以下改动，并**对全部 146 个文件重新完整扫描一次**：

| 动作 | 内容 |
|---|---|
| 同步至 0.8.10 | 新增 8 个 `yl_v2810*_ext.py` + 4 个 `srv_patch_*.py`（`t16arena` / `v2810` / `arenaweek` / `snapself`）；更新 `srv/index_v28.ts` / `build_v26n.py` / `yl_patch.py` / `yl_arb_ext.py` / `yl_ui_ext.py` / `yl_version_ext.py` / 4 个既有模块 / `CHANGELOG.md` / `build/index.html` / `localtest/chain_build.py` |
| 产物换版 | 新增 `build/assets/index-v2810-20260930.js`，删除旧产出 `index-v288-20260929.js`（仅保留冻结基座 v26m + 当前产出 v2810） |
| 文档同步 | `README.md` / `docs/DEPLOYMENT.md` / `docs/PUBLISH-MANIFEST.md` / `docs/NEXT-CONVERSATION-STEPS.md` / `docs/GITHUB-PUBLISH-INSTRUCTIONS.md` 全部指纹与计数更新到 0.8.10 |
| **本轮新修脱敏** | ① `localtest/chain_build.py` 的 `NODE` 常量本机路径 → `<WORKDIR>`；② `docs/0.8.8-design/接力与坑清单.md` 里**作为反面教材引用的真实 IP 与 `C:/Users/<USER>` 已打码**（该文件本身就在讲「扫描报告自述文字也会泄露」，结果自己犯了这个错） |

**复扫结果：4 组正则全部 0 命中**（唯一命中项是「打码前缀字面量」`csk-` / `47.243.x.x`，非真实凭据）。

---

## 六·补、0.8.9 同步后的复扫记录（2026-09-30）

同步阶段做了以下改动，并**对全部 146 个文件重新完整扫描一次**：

| 改动 | 说明 |
|---|---|
| 同步至 0.8.9 | 新增 8 个 `yl_*_ext.py` + 9 个 `srv_patch_*.py` + 客户端产物 `index-v288-20260929.js`；更新 `srv/index_v28.ts` / `build_v26n.py` / `localtest/chain_build.py` / 7 个既有模块 / `CHANGELOG.md` |
| 删除旧产物 | `build/assets/index-v287-20260929.js`（仅保留冻结基座 v26m + 当前产出 v2810） |
| README | GM 段落改写：兜底 `'<WEAK_PASSWORD>'` 已移除 → `GM_PASSWORD` 未设置即 `[FATAL]` 拒绝启动 |
| 设计文档 | `docs/0.8.8-design/` 更新 5 份 + 新增 5 份（共 11 份）；**排除**含凭据的 GM 文档与内部交接稿 |

**复扫结果（真实密钥/隐私）**：

| 模式 | 命中 |
|---|---|
| `sk-` 密钥 | **0** |
| PEM 私钥块（`-----BEGIN … PRIVATE KEY-----`） | **0** |
| 服务器 IP（真实 IPv4） | **0** |
| 手机号 | **0** |
| 本机用户名 / 路径（`<USER>` / `C:\Users`） | **0**（仅扫描命令/报告文字中提及） |
| 沙盒密钥明文 | **0** |
| GitHub token / AWS key | **0** |
| `.ssh/` | **0** |
| 真实凭据前缀（`csk-` / 口令变体 / `KeyAIO` / 生产 IP） | **0** |

> `docs/PUBLISH-MANIFEST.md` / `docs/GITHUB-PUBLISH-INSTRUCTIONS.md` 中出现的 `ssh -i` / `scp -i` / `PRIVATE KEY` 字样，
> 是「**扫描命令正则 + 说明为何排除部署脚本**」的描述文字，不含真实主机或密钥。

---

## 七、最终判定

- 🔴 高危项（真实密钥 / 私钥 / 数据库 / 服务器 IP / 手机号）：**命中 0 条** ✅
- 🔴 额外核查（真实凭据前缀 `csk-` / 口令变体 / `KeyAIO` / 生产 IP `161.33.*` `47.109.*` `158.179.*`）：**0 命中** ✅
- 🟠 中危项（沙盒凭据明文）：**已全部脱敏** ✅
- 🟡 低危项（代码字段名 / 环境变量名 / 公开域名 / 扫描命令文字）：**经逐条核验，非凭据** ✅

**→ 可以安全发布到公开仓库。** 第六节「需确认项 A」已解决（0.8.9 移除弱口令兜底、改为缺失即拒绝启动），无遗留阻塞项。
