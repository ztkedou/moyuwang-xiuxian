# 部署说明 · DEPLOYMENT

> ⚠️ **本仓库不含任何真实服务器地址、账号或密钥。** 下列示例中的 `<SERVER_IP>`、`<DOMAIN>`、`<路径>` 请自行替换。
> 原始部署脚本因含真实主机信息与私钥路径，已从公开仓库中排除（见 `PUBLISH-MANIFEST.md`）。

---

## 架构总览

```
浏览器 ──► Nginx (443, 静态托管 + 反代)
              ├── /myxxz/            → 前端静态产物 build/（index.html + assets/*.js|css|png）
              ├── /myxxz/api/        → 反代到 Node 服务 (127.0.0.1:PORT)
              └── /myxxz/CHANGELOG.md→ 更新日志（客户端拉取展示）

Node 服务 (systemd: yl-server)
  └── srv/index_v28.ts   ← 单文件 Express 应用
         ├── SQLite: database.sqlite
         └── 数据字典: game-dicts.json
```

**目录约定**（示例，可按需调整）：

| 用途 | 示例路径 |
|---|---|
| 前端静态根 | `/opt/<app>/www/`（`index.html`、`assets/`、`CHANGELOG.md`） |
| 服务端 | `/opt/<app>/server/`（`index.ts`、`game-dicts.json`、`database.sqlite`、`.env`、`node_modules/`） |
| 备份 | `/root/backup/` |

---

## 一、准备产物

在本地执行（详见 README）：

```bash
# 前端：冻结基座 → 注入补丁 → 最终 bundle
python build_v26n.py
#   产出 build/assets/index-v28111-20260930.js

# 服务端：冻结基座 → 串行应用 32 环补丁 → srv/index_v28.ts
python localtest/chain_build.py --srv
```

产物：

| 产物 | 部署到 |
|---|---|
| `build/index.html`、`build/assets/*` | `<前端静态根>/` |
| `srv/index_v28.ts` | `<服务端>/index.ts` |
| `srv/game-dicts.json` | `<服务端>/game-dicts.json` |
| `CHANGELOG.md` | `<前端静态根>/CHANGELOG.md` |

---

## 二、服务端依赖

`index_v28.ts` 直接 import 的运行时依赖：

```bash
npm i express cors sqlite3 bcrypt jsonwebtoken dotenv
```

> 服务端是**单文件 TypeScript**，可用 Node 22+ 的 `--experimental-strip-types` 直接运行，或先用 `tsc` 编译。

数据库：首次启动会自动建表；`srv/*.sql` 为增量迁移脚本（交易行货款 / 限时活动 / 灵田 / 仙盟），按需执行。

---

## 三、环境变量

在 `<服务端>/.env` 中配置（参考 `.env.example`）：

```dotenv
PORT=3000
DATABASE_PATH=./database.sqlite
JWT_SECRET=<用 openssl rand -hex 64 生成一段长随机串>
GM_PASSWORD=<自定义一个强口令>
FRONTEND_URL=https://<DOMAIN>
# 可选：AI 历练剧情
AI_API_KEY=
AI_API_URL=https://api.siliconflow.cn/v1/chat/completions
AI_MODEL=Qwen/Qwen2.5-7B-Instruct
```

> ⚠️ **`GM_PASSWORD` 必须显式设置**。自 0.8.9 起服务端已移除弱口令兜底默认值 —— **未设置时服务端会以 `[FATAL]` 拒绝启动**，不会退化成弱口令。

---

## 四、systemd 常驻服务

`/etc/systemd/system/yl-server.service`：

```ini
[Unit]
Description=yl game server
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/<app>/server
EnvironmentFile=/opt/<app>/server/.env
ExecStart=/usr/bin/node --experimental-strip-types /opt/<app>/server/index.ts
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now yl-server
systemctl is-active yl-server      # 应输出 active
```

---

## 五、Nginx 反代

```nginx
location /myxxz/api/ {
    proxy_pass http://127.0.0.1:3000/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /myxxz/ {
    alias /opt/<app>/www/;
    try_files $uri $uri/ /myxxz/index.html;
}
```

> 前端 bundle 采用「文件名带版本号 + `index.html` 指向新名」的方式发布：
> 上传新 bundle → 校验 md5 → 原子 `mv` → 再改 `index.html` 指向新文件名。
> 旧文件名保留不删，即为**秒级回滚点**。

---

## 六、发布检查清单（建议）

1. 上传前：本地对产物 `md5sum` 留档（本仓库给出参考值：
   前端 `78f16303052233968fdb4bb286a53e15`，服务端 `8342bedceb171bc922bc5e8c0ef339b1`）。
2. 备份：`index.ts` / `game-dicts.json` / `index.html` / `CHANGELOG.md` / `database.sqlite` / 旧 bundle 各留一份。
   数据库建议用 `VACUUM INTO` 做一致性快照。
3. 上传新 bundle → 远端校验 md5 → 原子替换。
4. 上传 `index.ts.new` / `game-dicts.json.new` → 校验 md5 → 原子替换 → `systemctl restart yl-server`。
5. 改 `index.html` 指向新 bundle（确认平台注入块仍在）。
6. 验收：`systemctl is-active yl-server`、访问线上首页、抽查关键玩法。

---

## 七、安全提醒

- `.env`、`database.sqlite`、`.jwt_secret`、SSH 私钥**绝不入库**（已在 `.gitignore` 中兜底）。
- `JWT_SECRET` 建议长期固定（重启不换钥匙，否则全员掉线）；本仓库源码在未配置时会生成并持久化到 `.jwt_secret`。
- 定期备份 `database.sqlite`。
