# 开源到自己的 GitHub · 可粘贴指令（最终版）

> **用法**：把「═══ 复制从这里开始 ═══」到「═══ 复制到这里结束 ═══」之间的**全部内容**，
> 原样粘贴到一个**新对话**的第一条消息里，**并在同一条消息里附上你的 GitHub Token**。
>
> 本文件放在仓库内（`docs/GITHUB-PUBLISH-INSTRUCTIONS.md`），随仓库一起公开也无敏感信息。

---

═══ 复制从这里开始 ═══

# 任务：把《摸鱼修仙传》开源到我的 GitHub

我要把《摸鱼修仙传》**完整开源到我自己的 GitHub 公开仓库**，并长期维护同步。
**我没用过 GitHub、不懂任何 git 命令，需要你全程代劳。** 我的 GitHub Token 我贴在下面。
你执行，我只看结果；每步做完给我**一句话结论 + 可点击链接**。

---

## 一、好消息：发布物**已经准备好了**，你只需「建仓库 + 推上去」

本机已有一份**完整、已脱敏、已提交**的本地 git 仓库，**不要重新准备发布物**：

| 项 | 值 |
|---|---|
| **本地仓库路径** | `D:\AIWorkspaces\github-moyuwang-xiuxian\` |
| **当前 commit** | `main` 分支最新提交（见 `git log --oneline -1`；工作区干净） |
| **文件数 / 体积** | **173 个文件 / 约 14 MB**（不含 `.git`） |
| **仓库名（已定）** | **`moyuwang-xiuxian`** |
| **作者署名** | **`Fipken`**（已写入 `README.md` / `LICENSE`） |
| **许可** | **MIT**（已含上游 fansj 版权声明） |
| **敏感串扫描** | **已做，真实密钥 0 命中**（报告：`docs/SECRETS-SCAN.md`） |
| 当前无 remote | `git remote -v` 为空 —— 你只需要 `remote add` + `push` |

> 仓库内 `docs/NEXT-CONVERSATION-STEPS.md` 是详细执行清单，可作参考（本指令自包含，不看也行）。

---

## 二、项目背景（直接拿去填仓库 About）

- **在线试玩**：**https://moyuwang.online/myxxz/** —— 打开即玩，无需安装、无需注册即可体验；**本仓库版本 0.8.11.1**（线上试玩环境可能滞后于仓库，截至本仓库更新时线上即为 0.8.11.1）
- **上游开源项目**：**https://github.com/JeasonLoop/react-xiuxian-game**（作者 **fansj**，包名 `cloud-spirit-cultivation`）
  - 上游 **README 声明 MIT 许可**（但上游仓库内**没有 `LICENSE` 文件**）
  - 本改版的**基线提交 = `b822f2d`**（2026-07-31）
- **⚠️ 必须如实声明的技术事实（不要在 README 里假装是「上游源码 + 改动内联」）**：
  改版后的 React 源码树**在本机已不存在**。因此本仓库发布的是 **「冻结基座 + 补丁管线」**——
  以一份**不可变的冻结 bundle** 为基座，用脚本按固定顺序注入全部改造，产出与线上**逐字节一致**的最终产物。
  README 里**已经写清楚**了这一点，**你原样保留即可**。

### 仓库结构速览

| 路径 | 是什么 |
|---|---|
| `build_v26n.py` + `yl_*.py`（59 个补丁模块 + 引擎） | ★ 前端装配器：冻结基座 → 注入改造 → 最终 bundle |
| `srv_patch_*.py`（44 个）+ `localtest/chain_build.py` | ★ 服务端链式装配器（32 环串行） |
| `build/assets/index-v26m-20260927.js` | ★ 前端冻结基座（装配输入，md5 `b315eb1a04e967a66c128861b3a3dadd`） |
| `build/assets/index-v28111-20260930.js` | ★ 装配产出 = 0.8.11.1 定版产物（md5 `78f16303052233968fdb4bb286a53e15`） |
| `srv/index_v28.ts` | ★ 服务端单文件 TS，200+ 接口（md5 `8342bedceb171bc922bc5e8c0ef339b1`） |
| `srv/game-dicts.json`、`srv/*.sql` | 游戏数据字典、建表迁移脚本 |
| `_v281_base/` | 服务端/前端/字典的冻结基座 |
| `docs/` | 设计文档、发布清单、扫描报告、部署说明 |
| `localtest/` | 本地沙盒测试说明 + 链式装配器 |
| `CHANGELOG.md` | 0.3.8 ~ 0.8.11.1 逐版更新日志 |

---

## 三、我要的最终结果

1. **我自己的 GitHub 公开仓库** —— 名字 **`moyuwang-xiuxian`**，**Public**（公开）
2. **仓库 About**：描述 + 官网链接 + 标签（见第四节第 3 步的现成命令）
3. **建一个 Release** —— tag `v0.8.11.1`，标题「摸鱼修仙传 v0.8.11.1」，正文取 `CHANGELOG.md` 的 0.8.11.1 段落
4. **长期同步能力**：以后我每次改完游戏，你要能把改动推上去，提交信息用**中文**写清楚改了什么

---

## 四、请按这个顺序做（每步做完先给我结论）

### 第 0 步 · 先自检（不要跳过）

```bash
cd /d/AIWorkspaces/github-moyuwang-xiuxian
git log --oneline -3          # 应看到本仓库的同步提交（0.8.11.1）
git status                    # 应为 clean
git remote -v                 # 应为空
git ls-files | wc -l          # 应为 173
```

> 若 `git status` 不是 clean，**先停下告诉我**，不要自行提交或丢弃改动。

### 第 1 步 · 用我的 Token 创建公开仓库

```bash
# 若本机没有 gh：winget install --id GitHub.cli
echo "<我的TOKEN>" | gh auth login --with-token
gh auth status

gh repo create moyuwang-xiuxian --public \
  --description "摸鱼修仙传 —— 浏览器挂机文字修仙游戏（基于 JeasonLoop/react-xiuxian-game 二次开发）。在线试玩：https://moyuwang.online/myxxz/" \
  --source . --remote origin --push
```

> **这条命令会一次性完成：建仓库 + 关联 origin + 推送到 main。**
> 如果 `moyuwang-xiuxian` 这个名字**已被占用**，先停下来告诉我，我给备选（`moyu-xiuxian` / `moyuwang-xiuxian-game`）。
> 如果**不装 gh**（或你要更可控），改用 REST API：
>
> ```bash
> curl -sS -X POST https://api.github.com/user/repos \
>   -H "Authorization: Bearer <我的TOKEN>" \
>   -H "Accept: application/vnd.github+json" \
>   -d '{"name":"moyuwang-xiuxian","description":"摸鱼修仙传 —— 浏览器挂机文字修仙游戏（基于 JeasonLoop/react-xiuxian-game 二次开发）。在线试玩：https://moyuwang.online/myxxz/","private":false,"has_issues":true,"has_wiki":false}'
>
> git remote add origin https://github.com/<我的用户名>/moyuwang-xiuxian.git
> git -c http.extraheader="Authorization: Bearer <我的TOKEN>" push -u origin main
> ```
>
> **推之前必须先跑一遍第 2 步的安全闸。** 若 `gh repo create` 已直接 push 了，push 完**补跑一次安全闸**做二次确认。

### 第 2 步 · 推送前的安全闸（**每次 push 之前都要跑**）

```bash
# 2.1 看将要推送的文件清单
git status
git ls-files | wc -l

# 2.2 全量敏感串扫描 —— 期望「全部 0 命中」
git grep -nE "sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{36}|github_pat_|AKIA[0-9A-Z]{16}|-----BEGIN|PRIVATE KEY|47\.243\.|[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|1[3-9][0-9]{9}|C:\\\\Users|<USER>" -- . || echo "OK: 真实密钥/IP/手机号 0 命中"

# 2.3 确认敏感文件没被跟踪 —— 期望「OK」
git ls-files | grep -E "\.env$|\.sqlite|\.db$|\.key$|\.pem$|id_rsa|\.p12$|\.jks$" && echo "!! 危险：敏感文件被跟踪，立即停止" || echo "OK: 无敏感文件被跟踪"
```

**任何一条命中真实凭据 → 立即停止，先告诉我，不要推。**

> 已知的「命中但无害」（2026-09-29 已逐条人工核验，可放行）：
> - 两个 bundle 里的 `127.0.0.1:1999` / `127.0.0.1:PORT` —— 库代码里的本地回环地址，非服务器地址
> - `docs/SECRETS-SCAN.md`、`docs/PUBLISH-MANIFEST.md` 里出现的 `PRIVATE KEY` / `ssh -i` 字样 —— 是「扫描报告和排除清单本身的描述文字」
> - `srv/index_v28.ts` 里的 `process.env.JWT_SECRET` / `process.env.AI_API_KEY` —— **只读环境变量名，无值**
> - `.env.example` 里的 `change-me-to-a-long-random-string` —— **占位符**

### 第 3 步 · 填仓库 About（描述 / 官网 / 标签）

```bash
gh repo edit <我的用户名>/moyuwang-xiuxian \
  --description "摸鱼修仙传 —— 浏览器挂机文字修仙游戏（基于 JeasonLoop/react-xiuxian-game 二次开发）。在线试玩：https://moyuwang.online/myxxz/" \
  --homepage "https://moyuwang.online/myxxz/" \
  --add-topic react --add-topic typescript --add-topic game --add-topic xiuxian \
  --add-topic idle-game --add-topic webgame --add-topic vite --add-topic mit-license
```

（也可以到仓库页面右上角 ⚙️ 手动填。）

### 第 4 步 · 建 Release

```bash
gh release create v0.8.11.1 --title "摸鱼修仙传 v0.8.11.1" \
  --notes "详见 CHANGELOG.md 的 0.8.11.1 段落。在线试玩：https://moyuwang.online/myxxz/"
```

### 第 5 步 · 给我验收链接

```
✅ 已上传：https://github.com/<我的用户名>/moyuwang-xiuxian
✅ 试玩：https://moyuwang.online/myxxz/
```

并确认：仓库首页 `README.md` 正常渲染、`LICENSE` 在页面右侧显示为 **MIT**、
About 区能点到试玩链接、Release 页能看到 `v0.8.11.1`。

---

## 五、Token 与权限

- 我用的是 **fine-grained PAT**，权限只有 **`Contents: Read and write`** + **`Metadata: Read`**。
  **权限不够（比如建仓库 403）你直接告诉我错误原文，我去调权限，别绕。**
- Token 只在内存/环境变量里用：**绝不写进任何文件、绝不 commit、绝不回显在聊天里、绝不写进 git remote URL**。
- 用完提醒我去 GitHub 设置里**轮换（revoke + 重新生成）**。

---

## 六、绝对红线（违反会造成安全事故）

1. **绝不提交任何密钥/隐私**。仓库现已扫描干净（173 文件 / 真实密钥 0 命中），
   **但你若新增或修改任何文件，必须重新跑第 2 步的安全闸**。
   禁止入库：`.env`、`*.key`、`*.pem`、`*.p12`、`id_rsa*`、`.jwt_secret`、
   `*.sqlite` / `*.db`（真实玩家数据）、`*DEPLOY_LOG*`、任何 `deploy_*.sh`。
2. **不碰线上服务器**（除非我明确要求发布）。
3. **单文件 > 50 MB 先问我**。（当前最大文件 2.03 MB，安全。）
4. **每次推送前先 `git status` 给我看「将要提交的文件清单」，我确认后才推。**
5. 服务端 `srv/index_v28.ts` 的 GM 口令兜底 `|| 'gamer'` **已在 0.8.9 移除** ——
   现在 `GM_PASSWORD` 未设置时服务端会以 `[FATAL]` **拒绝启动**。**这是个安全性改进，不要改回去。**
   （冻结基座 `_v281_base/index_v28.base.ts` 里仍保留旧写法，属历史原貌，不要动。）
6. **不要**把 `docs/GITHUB-PUBLISH-INSTRUCTIONS.md` 里我的 Token 示例替换成真 token 后提交。
7. 别改 `Fipken` 这个署名。要改就全局替换并告诉我。

---

## 七、之后的长期维护（我每次改完游戏）

1. 我在本机改完并重新构建：
   ```bash
   python build_v26n.py                    # 前端产物
   python localtest/chain_build.py --srv   # 服务端产物
   ```
2. 你把新产物同步进 `D:\AIWorkspaces\github-moyuwang-xiuxian\`。
3. 跑第 2 步安全闸 → `git add -A` → `git commit -m "<中文说明>"` → `git push`。
4. 提交信息用中文写清「改了什么、为什么」，例如：
   - `feat(0.8.11.1): 周里程碑「已领取」显示修复（服务端+客户端两半边）`
   - `fix: 修复炼丹炉右侧 UI 挤压`

---

═══ 复制到这里结束 ═══

---

## 附 · 本指令的事实核对来源（供你自查，不用贴进新对话）

| 事实 | 出处 |
|---|---|
| 173 文件 / 14 MB / commit 见 `git log --oneline -1` | `git ls-files \| wc -l` / `du -sh` / `git log --oneline` |
| 无 remote | `git remote -v`（空） |
| 署名 Fipken | `LICENSE`、`README.md` |
| MIT | `LICENSE` 全文 + 上游版权行 |
| 试玩链接 | `README.md`、`docs/REPO-NAME.md` |
| 上游来源 | `README.md` 致谢段、`LICENSE` |
| 冻结基座 / 产出 md5 | `docs/PUBLISH-MANIFEST.md` |
| 敏感串 0 命中 | 本次独立复扫（4 组正则全 0，与 `docs/SECRETS-SCAN.md` 一致） |
| 最大文件 2.06 MB | `git ls-files \| xargs ls -l \| sort -k5 -rn` |
| 无 node_modules / 无嵌套 .git | `find . -name node_modules` / `find . -name .git` |
