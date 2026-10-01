# 🚀 一键部署 · 小白版

> 目标：把《摸鱼修仙传》跑在**你自己的电脑或服务器**上，浏览器打开就能玩。
> 全程不需要懂 Docker，也不需要改代码。
>
> 只想看代码/自己改？看 [README 的「本地运行」](../README.md#-本地运行--构建--部署)。

---

## 一、先装一个东西：Docker Desktop

- **Windows / macOS**：到 <https://www.docker.com/products/docker-desktop/> 下载安装，装完**启动 Docker Desktop**（任务栏出现小鲸鱼图标才算启动好）。
- **Linux**：装 `docker` 与 `docker compose`（各发行版教程不同，装好后 `docker compose version` 能打印版本即可）。

装好后，打开终端（Windows 用 PowerShell 或 Git Bash 都行），确认：

```bash
docker --version
docker compose version
```

两条都能打印版本号，就可以继续了。

> **拉不动镜像？** 国内网络访问 Docker Hub 可能很慢或失败。解决办法二选一：
> 1. 在 Docker Desktop 的 `Settings → Docker Engine` 里配置 `registry-mirrors`（填一个你能访问的镜像源地址），Apply & Restart；
> 2. 或者构建时换基础镜像源前缀：
>    `docker compose build --build-arg NODE_IMAGE=<镜像源>/library/node:22-bookworm-slim`
>
> 镜像源地址会变，以你所在网络当前可用者为准。

---

## 二、三条命令，起服务

把仓库下载（或 `git clone`）到本地，在**仓库根目录**执行：

```bash
# ① 生成配置（自动填好随机密钥）
cp .env.example .env

# ② 构建镜像并后台启动
docker compose up -d --build

# ③ 打开浏览器
#    http://localhost:8080/
```

第二条命令第一次会花几分钟（要下基础镜像 + 装依赖），看到 `Started` 字样就成了。

> **装了 `make` 的话更省事**：`make init` 会自动帮你生成带随机密钥的 `.env`，
> 然后 `make up` 一条命令搞定。没装 `make` 就用上面的三条命令，效果完全一样。
>
> Windows 自带的 Git Bash 一般**没有** `make`，用上面的 `cp` + `docker compose` 即可。

### 看看是不是真的起来了

```bash
docker compose ps                  # 状态应是 Up (healthy)
curl http://localhost:8080/api/health
# 期望输出：{"status":"ok","message":"Backend is running"}
```

---

## 三、改端口 / 改数据库位置

### 改对外端口

编辑 `.env`，加一行（或用已有的那行）：

```dotenv
HOST_PORT=9000
```

然后 `docker compose up -d` 重建容器，改从 <http://localhost:9000/> 访问。

> 一次性临时改也行：`HOST_PORT=9000 docker compose up -d`

### 数据库放在哪

数据库文件固定在容器内的 `/data/database.sqlite`，由 Docker 命名卷 `moyuwang-xiuxian-data` 持久化。

- **换一个卷**：改 `docker-compose.yml` 里 `volumes` 的卷名，再 `docker compose up -d`。
- **改成宿主机某个目录**（方便直接备份文件）：把 `volumes` 那一行换成
  ```yaml
  - ./data:/data
  ```
  这样数据库就落在仓库根的 `data/` 目录下（`data/` 请自行加进 `.gitignore`，别提交）。
  容器以非 root 用户运行，**Linux 上如果挂载后报权限错误**，先给宿主机目录放权：
  ```bash
  mkdir -p data && sudo chown -R 1000:1000 data
  ```
- **备份**：`docker compose exec moyuwang sh -c "cp /data/database.sqlite /data/backup-$(date +%F).sqlite"`，
  然后 `docker cp moyuwang-xiuxian:/data/backup-2026-01-01.sqlite ./` 取出来。

> ⚠️ `docker compose down` **不会**删数据；只有 `docker compose down -v` 才会连卷一起删。别手滑。

---

## 四、升级到新版本

```bash
git pull                      # 拿到新的产物（build/ 与 srv/index_v28.ts）
docker compose up -d --build  # 重建镜像并滚动替换
```

数据库在卷里，升级**不会丢档**。

> 想回退：`git checkout <旧提交>` 后同样 `docker compose up -d --build` 即可。
> 数据库结构只增不删（服务端自带幂等迁移），回退旧版本一般也能读。

---

## 五、常见报错怎么办

| 现象 | 原因 | 怎么办 |
|---|---|---|
| `docker: command not found` | 没装 Docker / 没启动 | 装并启动 Docker Desktop；重开终端再试 |
| `Cannot connect to the Docker daemon` | Docker Desktop 没起来 | 等鲸鱼图标变绿，或重启 Docker Desktop |
| 拉基础镜像卡住 / `timeout` | 访问 Docker Hub 慢 | 见第一节「拉不动镜像？」配镜像源 |
| `error getting credentials` / 认证失败 | Docker 登录态异常 | `docker logout` 后重试 |
| 启动即退出，日志有 `[FATAL] GM_PASSWORD 未设置` | 没有 `.env` 或没填 `GM_PASSWORD` | 执行 `cp .env.example .env`，填一个强口令，`docker compose up -d` |
| `error while interpolating ... GM_PASSWORD` | 同上，compose 在启动前就拦下了 | 同上 |
| 打开页面是 **502 / 接口全报错** | 服务端没起来（多半是 `GM_PASSWORD` 或数据库权限） | `docker compose logs -f` 看真实原因 |
| 打开页面**白屏** | 浏览器缓存了旧的 `index.html` | 强制刷新（Ctrl+Shift+R）；或 `docker compose restart` |
| 8080 端口被占用 `address already in use` | 本机已有程序占着 8080 | `.env` 里设 `HOST_PORT=9000` 换端口 |
| 升级后还是旧界面 | 浏览器缓存 | Ctrl+Shift+R 强刷 |
| 想看容器里发生了什么 | — | `docker compose logs -f`（Ctrl+C 退出，不影响服务） |

改完配置后**记得** `docker compose up -d` 让改动生效。

---

## 六、没有 Docker？用纯 Node 跑

只要装了 **Node.js 22+**（<https://nodejs.org/>），在仓库根目录：

```bash
cp .env.example .env     # 编辑 .env，至少填 GM_PASSWORD
./deploy.sh              # 装依赖 + 起服务
#   浏览器打开 http://localhost:8080/
```

- 换端口：`./deploy.sh --port 9000`
- 想先重跑一遍装配（需要 Python 3）：`./deploy.sh --assemble`
- 停服务：终端里按 `Ctrl+C`

`deploy.sh` 用的是一段纯 Node 写的网关（`deploy/gateway.mjs`）：既托管 `build/` 里的前端，
又把 `/yl/api` 反代给服务端，所以**不需要 nginx**。数据库默认落在仓库根的 `yl.db`。

---

## 七、想放到公网 / 加 HTTPS

镜像里已经包含了完整的页面与接口，直接用你自己的 Nginx / Caddy 反代到 `http://127.0.0.1:8080`
（或 compose 映射出的宿主机端口）即可，证书在你自己的反向代理上配。

> 上线前务必：① 用 `openssl rand -hex 64` 生成 `JWT_SECRET` 写进 `.env`（别留空，否则重启掉线）；
> ② `GM_PASSWORD` 设成强口令；③ 把 `.env` 和数据库备份妥善保管，**别提交到 Git**。
