#!/usr/bin/env node
/**
 * gateway.mjs —— 零依赖「静态前端 + API 反代」网关
 * ---------------------------------------------------------------------------
 * 本仓库的服务端（srv/index_v28.ts）只提供 /api/* 接口，**不托管前端静态文件**；
 * 而前端 bundle 里 API 前缀是硬编码的 `/yl/api`、更新日志是硬编码的 `/myxxz/CHANGELOG*.md`。
 * 因此「跑起来」需要一层把两者拼在一起的东西 —— 上游用的是 Nginx，这里用一个
 * 只用 Node 内置模块写成的网关，好处是：
 *   · 不引入任何新的运行时依赖（无 express/无 nginx，只要 Node 22+）；
 *   · 与 API 服务同机同 libc，docker / 裸机行为一致；
 *   · 单一进程对外，内部再拉起 API 子进程，日志集中、退出码可靠。
 *
 * 路由规则：
 *   /yl/api/*  /myxxz/api/*  /api/*   → 反代到内部 API 服务（去掉前缀映射回 /api/*）
 *   /myxxz/*                          → 静态目录（兼容前端硬编码的更新日志/图标路径）
 *   其它                               → 静态目录，找不到则回退 index.html（SPA）
 *
 * 可用环境变量：
 *   PUBLIC_PORT  对外端口（默认 8080）
 *   API_PORT     内部 API 端口（默认 3000）
 *   STATIC_DIR   静态根目录（默认 <仓库根>/build）
 *   API_ENTRY    API 入口文件（默认 <仓库根>/srv/index_v28.ts）
 *   API_NODE_BIN 运行 API 的 node 可执行文件（默认当前进程的 node）
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');

const PUBLIC_PORT = Number(process.env.PUBLIC_PORT || process.env.PORT || 8080);
const API_PORT = Number(process.env.API_PORT || 3000);
const STATIC_DIR = path.resolve(process.env.STATIC_DIR || path.join(ROOT, 'build'));
const API_ENTRY = path.resolve(process.env.API_ENTRY || path.join(ROOT, 'srv', 'index_v28.ts'));
const API_NODE_BIN = process.env.API_NODE_BIN || process.execPath;

// 需要反代到 API 的路径前缀（按长度降序匹配，长前缀优先）
const API_PREFIXES = ['/yl/api/', '/myxxz/api/', '/api/'];
// 静态资源的「别名前缀」：前端硬编码了 /myxxz/CHANGELOG*.md 与 /myxxz/assets/*，落到静态根
const STATIC_ALIASES = ['/myxxz/'];

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.map': 'application/json; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
};

function log(...args) {
  console.log('[gateway]', ...args);
}

// ---------------------------------------------------------------------------
// 1) 拉起 API 子进程
// ---------------------------------------------------------------------------
if (!fs.existsSync(API_ENTRY)) {
  console.error(`[gateway][FATAL] 找不到 API 入口文件：${API_ENTRY}`);
  process.exit(1);
}
if (!fs.existsSync(STATIC_DIR)) {
  console.error(`[gateway][FATAL] 找不到前端静态目录：${STATIC_DIR}`);
  process.exit(1);
}

log(`启动 API 子进程：${API_NODE_BIN} --experimental-strip-types ${API_ENTRY}（端口 ${API_PORT}）`);
const api = spawn(
  API_NODE_BIN,
  ['--experimental-strip-types', API_ENTRY],
  {
    cwd: path.dirname(API_ENTRY),
    env: { ...process.env, PORT: String(API_PORT) },
    stdio: 'inherit',
  },
);

let shuttingDown = false;
api.on('exit', (code, signal) => {
  if (shuttingDown) return;
  console.error(`[gateway][FATAL] API 进程意外退出（code=${code} signal=${signal}），网关一并退出`);
  process.exit(code == null ? 1 : code);
});
api.on('error', (err) => {
  console.error('[gateway][FATAL] 无法启动 API 子进程：', err.message);
  process.exit(1);
});

// ---------------------------------------------------------------------------
// 2) 反代
// ---------------------------------------------------------------------------
function proxy(req, res, targetPath) {
  const headers = { ...req.headers, host: `127.0.0.1:${API_PORT}` };
  const upstream = http.request(
    { host: '127.0.0.1', port: API_PORT, method: req.method, path: targetPath, headers },
    (upRes) => {
      res.writeHead(upRes.statusCode || 502, upRes.headers);
      upRes.pipe(res);
    },
  );
  upstream.on('error', (err) => {
    if (!res.headersSent) res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ error: '网关无法连接 API 服务', detail: err.message }));
  });
  req.pipe(upstream);
}

// ---------------------------------------------------------------------------
// 3) 静态文件
// ---------------------------------------------------------------------------
function sendFile(res, filePath, statusCode = 200) {
  const ext = path.extname(filePath).toLowerCase();
  const headers = { 'Content-Type': MIME[ext] || 'application/octet-stream' };
  // 带内容哈希的产物可长缓存；index.html / md 不缓存，避免升级后拿到旧页面
  if (['.js', '.css', '.png', '.svg', '.woff', '.woff2', '.ttf'].includes(ext)) {
    headers['Cache-Control'] = 'public, max-age=604800';
  } else {
    headers['Cache-Control'] = 'no-cache';
  }
  const stream = fs.createReadStream(filePath);
  stream.on('error', () => {
    if (!res.headersSent) res.writeHead(500);
    res.end('read error');
  });
  res.writeHead(statusCode, headers);
  stream.pipe(res);
}

/**
 * 把请求路径映射成「候选文件绝对路径」列表（按优先级）。
 * 安全约定：
 *   · 普通路径只在 STATIC_DIR 里找，绝不落到仓库根，避免把 .env / 源码暴露出去；
 *   · 只有命中别名前缀（/myxxz/）时才额外在 ROOT 里找一份 —— 前端硬编码的
 *     /myxxz/CHANGELOG*.md 在「docker 镜像」里位于静态根、在「本地 deploy.sh」里位于仓库根。
 *   · 任何情况下都做目录穿越防护。
 */
function resolveStatic(urlPath) {
  const raw = (urlPath || '/').split('?')[0];
  let rel = raw;
  let isAlias = false;
  for (const alias of STATIC_ALIASES) {
    if (rel === alias.slice(0, -1) || rel.startsWith(alias)) {
      rel = rel.slice(alias.length - 1); // 保留前导 '/'
      isAlias = true;
      break;
    }
  }
  let decoded;
  try {
    decoded = decodeURIComponent(rel);
  } catch {
    return [];
  }
  const normalized = path.normalize(decoded).replace(/^([/\\]|\.\.[/\\])+/, '');
  const out = [];
  const primary = path.join(STATIC_DIR, normalized);
  if (primary === STATIC_DIR || primary.startsWith(STATIC_DIR + path.sep)) out.push(primary);
  // 别名路径额外兜底到仓库根，但**只放行 .md**（即更新日志），
  // 避免把 /myxxz/srv/index_v28.ts 之类的源码经由别名读出去。
  if (isAlias && path.extname(normalized).toLowerCase() === '.md') {
    const fallbackRoot = path.join(ROOT, normalized);
    if (fallbackRoot.startsWith(ROOT + path.sep)) out.push(fallbackRoot);
  }
  return out;
}

function tryNext(candidates, i, req, res) {
  if (i >= candidates.length) {
    // 有扩展名（且不是 .html）的请求找不到就老实 404，别拿首页糊弄
    const ext = path.extname((req.url || '').split('?')[0]);
    if (ext && ext !== '.html') {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      return res.end('404 not found');
    }
    const fallback = path.join(STATIC_DIR, 'index.html');
    if (fs.existsSync(fallback)) return sendFile(res, fallback, 200);
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    return res.end('404 not found');
  }
  const candidate = candidates[i];
  fs.stat(candidate, (err, st) => {
    if (!err && st.isFile()) return sendFile(res, candidate);
    if (!err && st.isDirectory()) {
      const idx = path.join(candidate, 'index.html');
      if (fs.existsSync(idx)) return sendFile(res, idx);
    }
    tryNext(candidates, i + 1, req, res);
  });
}

function serveStatic(req, res) {
  const candidates = resolveStatic(req.url);
  if (candidates.length === 0) {
    res.writeHead(400, { 'Content-Type': 'text/plain; charset=utf-8' });
    return res.end('bad path');
  }
  tryNext(candidates, 0, req, res);
}

// ---------------------------------------------------------------------------
// 4) 对外 HTTP 服务
// ---------------------------------------------------------------------------
const server = http.createServer((req, res) => {
  const url = req.url || '/';
  for (const prefix of API_PREFIXES) {
    if (url === prefix.slice(0, -1) || url.startsWith(prefix)) {
      const rest = url.slice(prefix.length - 1); // 保留前导 '/'
      return proxy(req, res, `/api${rest}`);
    }
  }
  serveStatic(req, res);
});

server.on('error', (err) => {
  if (err && err.code === 'EADDRINUSE') {
    console.error(`[gateway][FATAL] 端口 ${PUBLIC_PORT} 已被占用。请换端口（deploy.sh --port N / .env 里的 HOST_PORT）后重试。`);
  } else {
    console.error('[gateway][FATAL] 对外服务启动失败：', err && err.message);
  }
  try { api.kill('SIGKILL'); } catch { /* ignore */ }
  process.exit(1);
});

function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  log(`收到 ${signal}，正在关闭…`);
  server.close(() => {
    try { api.kill('SIGTERM'); } catch { /* ignore */ }
    process.exit(0);
  });
  setTimeout(() => {
    try { api.kill('SIGKILL'); } catch { /* ignore */ }
    process.exit(0);
  }, 3000).unref();
}
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

// 等 API 就绪再对外开端口，避免首屏请求打空
async function waitForApi(maxMs = 30000) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    if (shuttingDown) return false;
    const ok = await new Promise((resolve) => {
      const r = http.request(
        { host: '127.0.0.1', port: API_PORT, path: '/api/health', method: 'GET', timeout: 1500 },
        (res) => { res.resume(); resolve((res.statusCode || 0) < 500); },
      );
      r.on('error', () => resolve(false));
      r.on('timeout', () => { r.destroy(); resolve(false); });
      r.end();
    });
    if (ok) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

waitForApi().then((ok) => {
  if (!ok) {
    console.error('[gateway][FATAL] 等待 API 就绪超时，请检查上方 API 日志（常见原因：未设置 GM_PASSWORD）');
    try { api.kill('SIGKILL'); } catch { /* ignore */ }
    process.exit(1);
  }
  server.listen(PUBLIC_PORT, () => {
    log(`已就绪：http://localhost:${PUBLIC_PORT}/  （静态目录 ${STATIC_DIR}，API 反代 127.0.0.1:${API_PORT}）`);
  });
});
