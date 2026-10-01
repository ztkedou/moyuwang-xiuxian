# 给新对话的「第一步执行清单」 · NEXT-CONVERSATION-STEPS

> **给谁看**：用户开的新对话（专职负责把本仓库上传到用户自己的 GitHub 并长期维护）。
> **前提**：用户已在本机 `D:\AIWorkspaces\github-moyuwang-xiuxian\` 准备好完整的发布物，
> 并且**已经在本地做完一次 git 提交**（只做了本地提交，**没有** remote、**没有** push）。
> **用户不会 git** —— 全部命令由你（AI）代为执行，用户只看结果。

---

## 0. 开始前先向用户索要这些信息

| 需要的信息 | 说明 |
|---|---|
| **GitHub Personal Access Token** | fine-grained token，权限只需 **`Contents: Read and write`** + **`Metadata: Read`**，作用范围选 **All repositories** 或指定新建仓库 |
| **GitHub 用户名** | 用于拼仓库地址 `https://github.com/<用户名>/moyuwang-xiuxian` |
| **仓库名** | 默认建议 `moyuwang-xiuxian`（见 `REPO-NAME.md`），若用户想换名请先确认 |
| **公开还是私有** | 建议 **Public**（公开） |
| ~~作者署名~~ | ✅ **已完成**：用户已拍板署名为 **`Fipken`**，已写入 `README.md` 与 `LICENSE` |

> ⚠️ **Token 安全**：token 只在内存/环境变量中使用，**绝不要写进任何文件、绝不要 commit、绝不要回显在聊天里**。
> 用完建议提醒用户到 GitHub 设置里轮换（revoke + 重新生成）。

---

## 1. 进入仓库目录并确认本地状态

```bash
cd /d/AIWorkspaces/github-moyuwang-xiuxian
git log --oneline -1        # 应看到一条本地提交
git status                  # 应为 clean
git remote -v               # 应为空（本地仓库尚未关联远程）
```

若 `git status` 有未提交改动，先确认改动内容再决定是否提交。

---

## 2. 作者署名 —— ✅ 已完成（无需再做）

作者署名已按用户拍板写入，**发布前无需再改**：

| 文件 | 内容 |
|---|---|
| `LICENSE` | `Copyright (c) 2026 Fipken` + 保留上游 `Copyright (c) 2025-2026 fansj` |
| `README.md` | 致谢段「本仓库维护者 **Fipken**」+ 许可段 `© 2026 Fipken` |

> 如果用户之后想改用别的名字/GitHub 用户名，直接全局替换 `Fipken` 即可：
> `git grep -l Fipken` 找出所有位置 → 替换 → `git add -A && git commit -m "docs: 调整署名"`。

---

## 3. 在 GitHub 上创建仓库

### 方式 A：用 `gh` CLI（推荐，最省事）

```bash
# 若未安装 gh：winget install --id GitHub.cli  （或 brew install gh）
echo "<TOKEN>" | gh auth login --with-token
gh repo create moyuwang-xiuxian --public \
  --description "摸鱼修仙传 —— 浏览器挂机文字修仙游戏（基于 JeasonLoop/react-xiuxian-game 二次开发）。在线试玩：https://moyuwang.online/myxxz/" \
  --source . --remote origin --push
# ↑ 这条命令会：建仓库 + 设 origin + 直接 push
```

### 方式 B：用 GitHub REST API + git（没有 gh 时）

```bash
# 1) 建仓库（--data 里 name/description/private 按需改）
curl -sS -X POST https://api.github.com/user/repos \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  -d '{"name":"moyuwang-xiuxian","description":"摸鱼修仙传 —— 浏览器挂机文字修仙游戏。在线试玩：https://moyuwang.online/myxxz/","private":false,"has_issues":true,"has_wiki":false}'

# 2) 关联远程
git remote add origin https://github.com/<用户名>/moyuwang-xiuxian.git

# 3) 推送（token 走 header，避免写进 remote URL）
git -c http.extraheader="Authorization: Bearer <TOKEN>" push -u origin main
```

> 若默认分支不是 `main`，先执行 `git branch -M main`。

---

## 4. 设置仓库 About（描述 / 网站 / 标签）

```bash
gh repo edit <用户名>/moyuwang-xiuxian \
  --description "摸鱼修仙传 —— 浏览器挂机文字修仙游戏（基于 JeasonLoop/react-xiuxian-game 二次开发）。在线试玩：https://moyuwang.online/myxxz/" \
  --homepage "https://moyuwang.online/myxxz/" \
  --add-topic react --add-topic typescript --add-topic game \
  --add-topic xiuxian --add-topic idle-game --add-topic webgame --add-topic vite
```

（或到仓库页面右上角 ⚙️ 手动填。）

---

## 5. 推送前的最后一道安全闸（**必做**）

**每次 push 之前**都执行，确认没有密钥混进去：

```bash
# 5.1 看将要推送的文件清单
git status
git ls-files | wc -l

# 5.2 全量敏感串扫描（应全部为 0）
git grep -nE "sk-[A-Za-z0-9_-]{16,}|PRIVATE KEY|BEGIN (RSA|OPENSSH)|api_key|<SERVER_IP>|<SSH_KEY_PATH>|<手机号正则>" -- . || echo "OK: 无命中"

# 5.3 确认这些文件不在版本控制里
git ls-files | grep -E "\.env$|\.sqlite$|\.db$|\.key$|\.pem$|id_rsa" && echo "!! 危险：有敏感文件被跟踪" || echo "OK: 无敏感文件被跟踪"
```

任何一条命中，**立即停止**，从暂存区移除并加进 `.gitignore`。

---

## 6. 首次推送

```bash
git push -u origin main
```

成功后给用户一句话结论 + 可点击链接：

```
✅ 已上传：https://github.com/<用户名>/moyuwang-xiuxian
```

---

## 7. 之后的长期维护（用户每次改完游戏）

1. 用户在本机改完并重新构建（`python build_v26n.py` / `python localtest/chain_build.py --srv`）。
2. 你把新产物同步进 `D:\AIWorkspaces\github-moyuwang-xiuxian\`。
3. `git add -A` → `git commit -m "<中文说明改了什么>"` → 执行第 5 节的扫描 → `git push`。
4. 提交信息用中文，写清「改了什么、为什么」，例如：
   `feat(0.8.11.1): 周里程碑「已领取」显示修复（服务端+客户端两半边）`
   `fix: 修复炼丹炉右侧 UI 挤压`

---

## 8. 绝对红线（再次强调）

1. **绝不**把 `.env` / `*.key` / `*.pem` / `*.sqlite` / `*.db` / `database.sqlite` / SSH 私钥 / token 提交进仓库。
2. **绝不**把真实服务器 IP、SSH 私钥路径、账号口令写进任何仓库文件。
3. 每次 push 前必须跑第 5 节的安全闸。
4. 单文件 > 50 MB 先问用户，别硬推。
5. **不碰线上服务器**，除非用户明确要求发布。
6. Token 用完提醒用户轮换。

---

## 附：本仓库发布物一览（供新对话快速了解）

| 项 | 值 |
|---|---|
| 仓库目录 | `D:\AIWorkspaces\github-moyuwang-xiuxian\` |
| 文件数 / 体积 | 173 个 / 约 14 MB（不含 `.git`） |
| 建议仓库名 | `moyuwang-xiuxian` |
| 关键文件 | `README.md`、`LICENSE`、`.gitignore`、`.env.example`、`CHANGELOG.md`、`build_v26n.py`、`srv/index_v28.ts` |
| 前端冻结基座 md5 | `b315eb1a04e967a66c128861b3a3dadd` |
| 前端最终产出 md5 | `78f16303052233968fdb4bb286a53e15` |
| 服务端产出 md5 | `8342bedceb171bc922bc5e8c0ef339b1` |
| 发布清单 | `docs/PUBLISH-MANIFEST.md` |
| 敏感串扫描报告 | `docs/SECRETS-SCAN.md` |
| 部署说明 | `docs/DEPLOYMENT.md` |
