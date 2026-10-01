# =============================================================================
# 摸鱼修仙传 · 部署快捷命令
# -----------------------------------------------------------------------------
#   make help      查看全部命令
#   make init      生成 .env（自动填随机 JWT_SECRET / GM_PASSWORD）
#   make up        构建镜像并后台启动（= docker compose up -d --build）
#   make logs      看日志
#   make down      停止并删除容器（数据卷保留）
# =============================================================================
SHELL := /bin/sh
COMPOSE := docker compose
IMAGE   := moyuwang-xiuxian:local

.PHONY: help init build up down restart logs ps sh health dev assemble clean

help:
	@echo "摸鱼修仙传 · 部署命令"
	@echo ""
	@echo "  make init       生成 .env（随机密钥），首次部署前跑一次"
	@echo "  make up         构建镜像并后台启动   -> http://localhost:8080/"
	@echo "  make build      只构建镜像，不启动"
	@echo "  make logs       实时查看容器日志"
	@echo "  make ps         查看容器状态"
	@echo "  make restart    重启容器"
	@echo "  make down       停止并删除容器（数据库卷保留）"
	@echo "  make sh         进入容器 shell"
	@echo "  make health     调用 /api/health 自检"
	@echo ""
	@echo "  没有 Docker？"
	@echo "  make dev        纯 Node 直接跑（先 make init）"
	@echo "  make assemble   重跑装配（需 Python 3），产物供部署使用"
	@echo "  make clean      清掉本机 node_modules / 本地库文件"

# ---- 初始化：生成 .env ----
init:
	@if [ -f .env ]; then \
	  echo "已存在 .env，跳过（要重来请先删掉它）"; \
	else \
	  cp .env.example .env; \
	  SECRET=$$(node -e "console.log(require('crypto').randomBytes(48).toString('hex'))" 2>/dev/null || openssl rand -hex 48); \
	  GM=$$(node -e "console.log(require('crypto').randomBytes(9).toString('base64url'))" 2>/dev/null || openssl rand -base64 12); \
	  sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=$$SECRET|" .env; \
	  sed -i.bak "s|^GM_PASSWORD=.*|GM_PASSWORD=$$GM|" .env; \
	  rm -f .env.bak; \
	  echo "已生成 .env（JWT_SECRET / GM_PASSWORD 已随机填充）"; \
	fi

# ---- Docker ----
build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build
	@echo ""
	@echo "已启动 -> http://localhost:$${HOST_PORT:-8080}/"
	@echo "看日志：make logs"

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

sh:
	$(COMPOSE) exec moyuwang sh

health:
	@port=$$(grep -E '^HOST_PORT=' .env 2>/dev/null | cut -d= -f2); \
	 port=$${port:-8080}; \
	 curl -fsS "http://localhost:$$port/api/health" && echo "" || echo "健康检查失败"

# ---- 无 Docker 路径 ----
dev:
	./deploy.sh

assemble:
	@echo "注意：装配会就地覆写 build/ 与 srv/ 下的定版产物，建议先备份（见 README）"
	python localtest/chain_build.py --all

clean:
	rm -rf node_modules
	rm -f yl.db yl.db-journal srv/.jwt_secret
	@echo "已清理本机 node_modules 与本地数据库"
