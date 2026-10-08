# 发布清单 · PUBLISH-MANIFEST

> 本文件说明：哪些文件会进入公开的 GitHub 仓库、为什么可发；哪些文件被排除、为什么排除。
> 生成时间：2026-09-29 ｜ 最后更新：2026-10-08（同步至 **0.9.38** 后复扫）
> staging 目录：`<WORKDIR>\github-moyuwang-xiuxian\`
> 统计：**441 个文件 / 约 14.3 MB**（不含 `.git`）

---

## 一、可发布清单（会进入 GitHub）

### 1. 根目录 · 说明与许可

| 文件 | 说明 | 为什么可发 |
|---|---|---|
| `README.md` | 项目说明、试玩链接、来源致谢、改版要点、构建/部署指引 | 面向公众的入口文档，无敏感信息 |
| `LICENSE` | MIT 全文 + 上游 fansj 版权行 | 上游为 MIT，二次开发同样以 MIT 发布，符合许可要求 |
| `.gitignore` | 忽略规则 | 纯规则文本 |
| `.env.example` | 环境变量**键名**示例（值为占位符） | 只有键名，无任何真实值 |
| `CHANGELOG.md` | 0.3.8 ~ 0.9.38 逐版更新日志 | 玩家可见内容，无敏感信息 |

### 2. 前端装配管线（根目录）

| 文件 | 说明 | 为什么可发 |
|---|---|---|
| `build_v26n.py` | 前端装配器：冻结基座 → 串行注入 131 个装配模块 + 28 个 standalone 补丁 → 最终 bundle | 核心可复现逻辑，无密钥 |
| `yl_patch.py` | 补丁引擎（锚点定位 + 字符串注入） | 同上 |
| `patches/client/yl_*_ext.py` × **136** | 客户端补丁模块（每批玩法改造一个文件；V28_MODULES 装配 + standalone） | 全部为纯前端改造逻辑；已逐文件扫描，无密钥/IP/口令 |

### 3. 服务端装配管线（根目录）

| 文件 | 说明 | 为什么可发 |
|---|---|---|
| `patches/server/srv_patch_*.py` × **83** | 服务端补丁模块（存档、经济、活动、宗门、师徒、传承、灵宠…；SRV_CHAIN 69 环） | 纯改造逻辑；已扫描，无密钥/IP/口令 |

### 4. 前端产物与冻结基座

| 文件 | 大小 | md5 | 是否发布 | 理由 |
|---|---|---|---|---|
| `build/index.html` | 2 KB | — | ✅ | 页面外壳，引用最终 bundle |
| `build/assets/index-v26m-20260927.js` | 1.51 MB | `b315eb1a04e967a66c128861b3a3dadd` | ✅ | **前端冻结基座（装配输入）**，不可变，复现必需 |
| `build/assets/index-v2938-20261008.js` | 2.32 MB | `a4726c77b810c6b620b0604ce89cf9a7` | ✅ | **装配产出 = 0.9.38 定版产物**，作为可校验的参考物（见下方「关于产物是否入库」） |
| `build/assets/index-ZuV-l8Gt.css` | 160 KB | — | ✅ | 样式表，前端运行必需 |
| `build/assets/logo-BInDl5Di.png` | 145 KB | — | ✅ | 站点 Logo |

### 5. 服务端源码与数据

| 文件 | 大小 | md5 | 说明 |
|---|---|---|---|
| `srv/index_v28.ts` | 954 KB | `479dcc66a3261c98254367c1cab0f416` | **服务端装配产出**（单文件 TS，200+ 接口）。密钥全部走 `process.env.*`，无硬编码凭据 |
| `srv/game-dicts.json` | 1.24 MB | `1b635513f553875060869272b790f910` | 游戏数据字典（物品/功法/事件…） |
| `srv/market_payouts.sql` | 1.3 KB | — | 建表迁移脚本（交易行货款） |
| `srv/migrate_activity.sql` | 2.5 KB | — | 建表迁移脚本（限时活动） |
| `srv/migrate_t10_farm.sql` | 1.9 KB | — | 建表迁移脚本（灵田） |
| `srv/migrate_t7_sect.sql` | 2.6 KB | — | 建表迁移脚本（仙盟） |

> `*.sql` 仅含 `CREATE TABLE` / 索引语句，无数据、无口令。

### 6. 服务端冻结基座

| 文件 | md5 | 说明 |
|---|---|---|
| `_v281_base/index_v28.base.ts` | `f6ecc82e72d8425d5064f765d7de0684` | 服务端冻结基座（`chain_build.py` 装配输入） |
| `_v281_base/index-v28-20260928.base.js` | `515aaac94f3db6908aac0a728be5a6e1` | 前端冻结基座（链式构建校验用） |
| `_v281_base/game-dicts.base.json` | `1b635513f553875060869272b790f910` | 字典冻结基座（与 `srv/game-dicts.json` 内容相同，校验需要） |
| `_v281_base/CHANGELOG.base.md` | — | 基座时点的更新日志快照 |

### 7. 构建/测试辅助

| 文件 | 说明 | 为什么可发 |
|---|---|---|
| `localtest/chain_build.py` | 服务端链式装配器（69 环串行应用） | 已脱敏（本机路径替换为 `<WORKDIR>`） |
| `localtest/dryrun_087.py` | 预演门禁（「预演 == 交付」硬门禁） | 已含 patches/ 路径适配；扫描通过 |
| `localtest/yl_r1*_ext.py` × **28** | standalone 客户端补丁（装配层末段套用） | 已逐文件扫描，无密钥/IP/口令 |
| `localtest/KNOWN_ISSUES.md` | 已知问题清单 | 扫描通过，无敏感串 |
| `localtest/README_SANDBOX.md` | 本地沙盒测试说明 | **已脱敏**（服务器 IP → `<SERVER_IP>`，本机路径 → `<WORKDIR>`） |

### 8. 设计文档（docs/）

| 路径 | 数量 | 说明 |
|---|---|---|
| `docs/PUBLISH-MANIFEST.md` | 1 | 本文件 |
| `docs/SECRETS-SCAN.md` | 1 | 敏感串扫描报告 |
| `docs/DEPLOYMENT.md` | 1 | 部署说明（脱敏版） |
| `docs/REPO-NAME.md` | 1 | 仓库命名建议 |
| `docs/NEXT-CONVERSATION-STEPS.md` | 1 | 首次上传 GitHub 的步骤清单 |
| `docs/design/*.md` | 14 | 数值/系统/合并面设计文档（**已脱敏**） |
| `docs/0.8.7-design/*.md` | 11 | 0.8.7 批次设计文档（扫描通过） |
| `docs/0.8.8-design/*.md` | 11 | 0.8.8 / 0.8.9 / 0.8.10 批次设计文档（扫描通过；已排除内部交接稿与含凭据的 GM 文档） |
| `docs/0.9.13-design/*.md` | 2 | 0.9.13 数值定档与玩法文案（扫描通过） |

---

## 二、必须排除的清单（不会进入 GitHub）

### 1. 🔴 密钥 / 凭据 / 私密配置

| 排除对象 | 为什么排除 |
|---|---|
| `localtest/_srvprobe/.env` | **真实本地密钥**：`JWT_SECRET=<...>`、`GM_PASSWORD=<...>`（值已在此文档中脱敏） |
| 任何 `*.key` / `*.pem` / `*.p12` / `id_rsa*` | SSH/证书私钥 |
| `.jwt_secret` | 服务端自动持久化的 JWT 密钥 |
| 生产 `srv/.env`（若存在） | 生产环境变量 |
| AI API Key（`AI_API_KEY`） | 真实大模型密钥；源码只读 `process.env`，不含值 |

### 2. 🔴 数据库与备份

| 排除对象 | 大小 | 为什么排除 |
|---|---|---|
| `localtest/_srvprobe/database.sqlite` | 8.96 MB | 真实玩家/测试数据（含账号、存档） |
| `*.sqlite` / `*.db` / `*.dump` / `*.bak.sql` | — | 数据库文件与转储 |
| 整包 `*.tar.gz` 备份 | — | 服务器备份 |

> 注意：`srv/*.sql` **不是**数据转储，而是建表迁移脚本，属于源码，**保留发布**。

### 3. 🔴 服务器地址 / 主机信息 / 部署脚本

| 排除对象 | 为什么排除 |
|---|---|
| `deploy_v28/*.sh`（8 个 deploy + 6 个 remote_check + remote_swap） | 含**真实服务器 IP**、`root@`、**SSH 私钥路径**以及 `ssh -i` / `scp -i` 调用（原文已排除，不在此仓库） |
| `deploy_v28/DEPLOY_LOG_*.md`（7 个） | 部署日志含服务器 IP 与 SSH 私钥路径 |
| `deploy_moyu/*.sh`、`deploy_v26*.sh`、`deploy_v27.sh` | 同上（历史部署脚本） |
| `docs/GITHUB-开新对话指令.md` | 内部指令文档，正文含服务器 IP 作为「红线示例」 |
| `docs/0.8.8-design/GM后台重构方案.md` | ⚠️ **含真实凭据**（口令变体、Cerebras key、**真实服务器 IP（已打码，不在此列明）**），绝对排除 |
| `docs/0.8.9-design/GM凭据盘点报告.md`（含 `.bak-*`） | ⚠️ **含真实凭据**（口令/密钥部分打码但**生产 IP 完整暴露**），绝对排除 |
| `docs/0.8.9-design/GM服务端待补端点需求.md` | GM 后台内部设计稿（安全敏感），排除 |
| `HANDOVER_0.8.2.md` | 内部交接稿，含服务器 IP |
| `report_brand_myxxz.md` | 内部报告，含服务器 IP |
| `v26h-修复报告.md` | ⚠️ **含真实手机号**，绝对排除 |

> 部署需求改由 `docs/DEPLOYMENT.md`（通用、无真实地址）覆盖。

### 4. 🟠 构建中间产物 / 暂存区（体积大、非发布物）

| 排除对象 | 为什么排除 |
|---|---|
| `_chainstage/`（含 `dryrun_*.bundle.js`、`s*.ts` 各环中间产物） | 装配中间态，磁盘约 63 MB；可由 `chain_build.py` 重新生成 |
| `build/assets/index-v26f…v26n / v27 / v28 / v287 / v2871 / v288*.js` | 历史/中间 bundle（仅保留基座 v26m 与产出 v2913） |
| `_v284_base/`、`_numbal_backup/`、`_v281_base` 之外的 `_*` 目录 | 历史快照 |
| `localtest/*.json`、`localtest/_arb_*`、`localtest/t_*_out.json`、`localtest/shots/` | 实测证据/截图/JSON 中间产物（数百个） |
| `__pycache__/`、`*.pyc` | 字节码缓存 |
| 根目录数百个临时脚本（`_*.py`、`probe*.py`、`measure*.py`、`verify*.py`、`smoke*.py`、`*_m.json` 等） | 一次性调试脚本，非发布物 |
| 根目录数百张 `*.png` 截图 | 调试截图（README 截图位另行人工挑选） |
| `*.bak*` / `*.pre082` / `*.pre-v*` | 备份文件 |

### 5. 🟠 内部工作稿

| 排除对象 | 为什么排除 |
|---|---|
| `docs/0.8.8-design/HANDOFF-0.8.8-进行中.md` | 内部进行中交接稿（含本机路径） |
| `docs/0.8.8-design/GM后台重构方案.md`、`docs/0.8.9-design/GM凭据盘点报告.md`、`docs/0.8.9-design/GM服务端待补端点需求.md` | GM 后台内部文档；前两者含真实凭据/生产 IP |
| `CHANGELOG.md.bak-pre087` / `.bak-pre089*` 等 `*.bak*` | 备份 |

---

## 三、关于「构建产物是否入库」的判断

**结论：入库。** 包含 `index-v26m-20260927.js`（冻结基座）与 `index-v2913-20261002.js`（最终产出）。

理由：

1. **冻结基座是装配的必需输入**——没有它，`build_v26n.py` 无法运行，整个「补丁管线」不可复现。它必须入库。
2. **最终产出是「可校验的参考物」**——本仓库的核心承诺是「任何人 clone 后能重建出与线上一致的产物」。
   把参考产物一并入库，任何人都能 `md5sum` 比对自建产物是否与仓库内参考物一致（`a2dbbac0…`），
   否则「可复现」只是一句无法验证的口号。
3. **许可允许**——上游为 MIT，允许再分发与修改。
4. **体积可接受**——两个 bundle 合计约 3.7 MB，对 git 仓库微不足道（远低于 50 MB 红线）。

> 中间态 bundle（v26f…v28、v2871）**不入库**：它们既非输入也非最终产出，可由管线重新生成。

---

## 四、需要用户拍板的点

| # | 事项 | 建议 |
|---|---|---|
| 1 | `_v281_base/game-dicts.base.json` 与 `srv/game-dicts.json` 内容完全相同（各 1.24 MB），是否保留两份？ | **建议保留**：`chain_build.py` 的基座指纹校验依赖前者，删了会破坏可复现性 |
| 2 | 是否发布 `docs/0.8.8-design/`（含 0.8.8 / 0.8.9 / 0.8.10 批次设计）？ | ✅ **已发布**（11 份）：设计文档体现开发过程，且已扫描干净；含凭据的 GM 文档与内部交接稿已排除 |
| 3 | `srv/index_v28.ts` 的 GM 口令兜底 —— **0.8.9 起已移除**（不再有 `\|\| '<WEAK_PASSWORD>'`） | ✅ **已解决**：产物中 `GM_PASSWORD` 未设置即 `[FATAL]` 拒绝启动；仅冻结基座 `_v281_base/index_v28.base.ts` 保留历史写法（由 `srv_patch_baseclean089.py` 移除） |
| 4 | ~~README / LICENSE 中的作者名占位符~~ | ✅ **已完成**：用户拍板署名 `Fipken`，已写入 README 与 LICENSE |
