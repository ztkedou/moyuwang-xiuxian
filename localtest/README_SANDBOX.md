# 本机全栈沙盒说明书（yl-deploy / localtest）

> 目的：在**本机**复刻《摸鱼修仙传》线上环境（nginx `/yl/` 路由 + v28 服务端 + 本机库副本），
> 供 Playwright 做**深度实测**，**完全不碰线上**（<生产服务器 IP>）。
> 版本：v28 / 0.8.1（终版）。bundle = `index-v28-20260928.js`（md5 `515aaac94f3db6908aac0a728be5a6e1`，1567867 chars）。
> 服务端 = `srv/index_v28.ts`（md5 `f6ecc82e72d8425d5064f765d7de0684`，560020 B）。
> 本轮修复共 8 项：货款竞态守卫 · 宗门功法服务端并发单调守卫 · 宗门功法客户端扣贡献快照守卫 ·
> 人物志白屏 try/catch 兜底 · 全 5xx 可重试+Retry-After · `/api/save` 限流 120/min ·
> 心法 exp 量纲对齐（等级不再 10x 虚高）· 移除上游 GitHub 版本检查外联。
> 作废指纹：`eb461136…`(线上) / `c707aef7…` / `607395f8…` / `9f6d580a…` / `5b76b179…` / 服务端 `5434961c…` / `9e6f91f1…`。

---

## 0. 绝对红线

1. **禁止**任何 `ssh root@<生产服务器>` / 线上写操作。本轮只在本机测。
2. **禁止**修改 `build/`、`srv/`、`*.py` 补丁源、`CHANGELOG.md` —— 除非你是 lead 且明确在修 bug。
   普通成员只**读**、只**写** `localtest/` 下的测试脚本 + `localtest/report_<你的名字>.md`。
3. 沙盒库是 `<LOCAL>/Temp/yl_v28_sandbox/s<idx>/database.sqlite`（**副本**，可随便改）。

---

## 1. 起沙盒（每人一个独立 idx，互不干扰）

```bash
cd /c/Users/<USER>/workbuddy-ai/WorkBuddyAiWorkSpace/yl-deploy
bash localtest/sandbox.sh up    <idx>      # 起服 + 前端壳；40s 内就绪
bash localtest/sandbox.sh seed  <idx>      # 灌测试数据（活动 + 3 个原型账号）
bash localtest/sandbox.sh down  <idx>      # 收
bash localtest/sandbox.sh url   <idx>      # 打印入口
```

**端口约定：API = `3100+idx`，前端壳 = `3200+idx`。**

| idx | API | Web 入口 | 库 | 用途 |
|---|---|---|---|---|
| 1 | 3101 | http://127.0.0.1:3201/yl/ | `.../s1/database.sqlite` | flow-1 |
| 2 | 3102 | http://127.0.0.1:3202/yl/ | `.../s2/database.sqlite` | net-2 |
| 3 | 3103 | http://127.0.0.1:3203/yl/ | `.../s3/database.sqlite` | ui-3 |
| 4 | 3104 | http://127.0.0.1:3204/yl/ | `.../s4/database.sqlite` | econ-4 |
| 5 | 3105 | http://127.0.0.1:3205/yl/ | `.../s5/database.sqlite` | lead（修复后验收） |
| 6 | 3106 | http://127.0.0.1:3206/yl/ | `.../s6/database.sqlite` | econ-4（独立复验） |

> ⚠️ **s2 / s3 / s4 的服务端副本仍是 04:33 的旧版（`9e6f91f1…`）**，只适合测**客户端**行为；
> 要测服务端改动，先 `down` + `up` 重起。

- 日志：`<LOCAL>/Temp/yl_v28_sandbox/s<idx>/{server.log,harness.log}`
- `up` 会**先杀**该 idx 的两个端口，再起新进程；重复 `up` 是安全的（幂等）。
- `up` 会**重置库**（从 pristine 拷贝）→ 会丢掉 seed 数据，所以顺序永远是 `up` → `seed`。
- **`up` / `refresh` 会让 Git Bash 的管道挂住**（后台 node 持着 fd），命令看起来「不返回」但服务其实已经起好。
  → 别等它返回：**看端口**。`netstat -ano | grep -E ":(310$IDX|320$IDX)\b"` 有 LISTENING 即就绪；
  → 或者后台跑：`bash localtest/sandbox.sh up <idx> >/dev/null 2>&1 & sleep 8; netstat -ano | grep ":310<idx> "`。
  → `down` 同理，加 `&` 即可。
- **`refresh <idx>`**：服务端打了补丁后，只把最新 `srv/index_v28.ts` 刷进沙盒并重启 API 进程，**不重置库、不动 harness**。
  用于「想保留已 seed 的数据」。用完务必核对 `md5sum .../s$idx/index.ts` == 期望值。

---

## 2. 测试账号（`seed` 之后）

密码统一 **`Test123456`**。

| 用户名 | userId | 定位 | 境界 | 宗门职衔 | 贡献 | 灵石 | 心法 |
|---|---|---|---|---|---|---|---|
| `ylt_new` | 39 | 空态/新手 | 炼气期 lv1 | 无宗门 | 0 | 10,000 | 1 |
| `ylt_mid` | 40 | 中坚正向 | 金丹期 lv3 | 内门弟子 | 50,000 | 2,000,000 | 6 |
| `ylt_max` | 41 | 满级上限 | 长生境 lv9 | 宗主 | 5,000,000 | 500,000,000 | 6 |

- 派生自真实存档 `ztkedou`(userId=13)。
- 三个账号的 `player.sectId = 'sect-localtest'`（**字符串**），`currentSectInfo.name='摸鱼宗'`。
- `seed` 会同时建 `sects` 表里 **数字 id=1** 的「摸鱼宗」+ 清 `sect_members`，并灌一个**限时活动**
  `stones2_live`「天降灵雨」`multiplier=2`，窗口 `[now-1h, now+30d]`。

---

## 3. 关键 API（都用 `Authorization: Bearer <accessToken>`）

登录：`POST /api/auth/login` `{username,password}` → `{accessToken,refreshToken,...}`
（**注意**：access token 在返回体的 `accessToken` 字段；服务端内部变量名是 `Et`。）

| 域 | 端点 |
|---|---|
| 存档 | `GET /api/save`、`POST /api/save`（**body 就是存档本体**，见下方警告） |
| 信箱 | `GET /api/mail/list`、`POST /api/mail/read`、`POST /api/mail/claim`、`POST /api/mail/claim-all` |
| 宗门功法 | `GET /api/sect/gongfa`、`POST /api/sect/gongfa/learn`、`POST /api/sect/gongfa/upgrade` |
| 宗门 | `GET /api/sect/mine`、`POST /api/sect/join`、`POST /api/sect/contribute`、`POST /api/sect/welfare/claim` |
| 心法 | `GET /api/gongfa`、`POST /api/gongfa/levelup` |
| 活动 | `GET /api/events`、`GET /api/activities/schedule` |
| 人物志 | `GET /api/chronicle`、`POST /api/chronicle/praise` |
| 经济 | `GET /api/economy/summary`(GM)、`GET /api/economy/anomalies`(GM) |
| GM | `POST /api/gm/login` `{password:'gamer'}` → `GET /api/gm/players` 等 |

GM 密码：**`<GM_PASSWORD>`**（沙盒 `.env` 里 `GM_PASSWORD=gamer`）。

### ⚠️ `POST /api/save` 的 body 格式（写错会把存档写坏，已有人踩过）

服务端是 `const saveData = req.body;` —— **body 就是存档对象本身，不是 `{saveData: ...}` 包装**。

```python
# ✅ 正确
call(base, "/save", token, method="POST", body=save_obj)          # save_obj = {"player": {...}, "logs": [...], ...}
# ❌ 错误：会把云端存档覆盖成 {"saveData": {...}}，player 丢失 → 账号报废（GET /sect/gongfa 变 NO_SECT）
call(base, "/save", token, method="POST", body={"saveData": save_obj})
```

- 版本并发控制用**请求头** `X-YL-Base-Revision`（不是 body 字段）。
- 服务端**不校验 body 结构**（已知缺口，只报告不修）：传 `{"logs":[]}` 也返回 200 并把云端存档覆盖掉。
  → 测试前务必先 `GET /api/save` 备份一份，或先 `sandbox.sh up <idx>` 重置。

---

## 4. Playwright 用法（唯一可用的 python）

```
C:/Users/<USER>/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe
```
`playwright` 已装（含 chromium）。示例：

```python
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width":1440,"height":900})
    pg.goto("http://127.0.0.1:3201/yl/", wait_until="domcontentloaded")
    # 登录：走 UI 或直接注入 token
    b.close()
```

---

## 5. ★ 已知坑（踩过，别再踩）

1. **注入的函数在 bundle 的模块作用域，不是 `window` 属性。**
   → `page.evaluate("YlxwSectGfPanel()")` / `page.evaluate("Be.getState()")` 一律 `undefined` / `not defined`。
   → **`page.add_init_script` 也进不去模块作用域**（它只在 `window` 全局跑，拿不到 `Be` / `YLXW_*`）。
     例外：**挂 `window` 的方法和 patch `window.fetch` 是可以的**，因为那本来就是全局的 —— 见下面 1c。
   → **要读模块内部状态的唯一做法：Playwright 拦 bundle 请求，把挂钩代码追加到 bundle 文本尾部**，
     这样追加的代码与被注入的模块处于**同一个脚本作用域**，能直接引用 `Be` / `Et` / `YLXW_*`：

   ```python
   HOOK = ("\n;try{window.__Be=Be;window.__Et=Et;window.__YLXW_CHAR_DEX=YLXW_CHAR_DEX;"
           "window.__hook='ok';}catch(e){window.__hook='ERR:'+e.message}")
   bundle_text = open("build/assets/index-v28-20260928.js", encoding="utf-8").read()
   pg.route("**/assets/*.js", lambda route: route.fulfill(
       status=200, content_type="application/javascript", body=bundle_text + HOOK))
   pg.goto("http://127.0.0.1:3201/yl/", wait_until="domcontentloaded")
   pg.wait_for_function("() => window.__hook === 'ok'")
   ```
   - 路由必须放宽到 `**/assets/*.js`（不要写死 bundle 文件名，A/B 换名会匹配不上）。
   - 挂钩前先 `pg.goto("about:blank")` 或新建 context，避免命中文档缓存。
   - **优先用真实 DOM 点击 + 服务端状态回读**；挂钩只在必须读内部 store 时才用。

1c. **要观察/统计网络请求，用 `add_init_script` patch `window.fetch`**（这是全局的，可行）：
   ```python
   pg.add_init_script("""
     (() => { const of = window.fetch;
       window.__net = [];
       window.fetch = function (...a) {
         const t0 = Date.now();
         const url = (typeof a[0] === 'string') ? a[0] : (a[0] && a[0].url) || '';
         const p = of.apply(this, a);
         p.then(r => { try { window.__net.push({ t: t0, ms: Date.now()-t0, url, status: r.status }); } catch(e){} })
          .catch(e => { try { window.__net.push({ t: t0, ms: Date.now()-t0, url, err: String(e) }); } catch(e2){} });
         return p;
       };
     })();
   """)
   ```
   再配 `MutationObserver` 抓 UI 文案变化。**注意 `fetch` 之外的 XHR 抓不到**（本作都是 fetch）。
   若只想看服务端视角，直接看 `s$idx/server.log` 更省事。

1b. **沙盒的服务端是 `up` 那一刻的冻结副本；bundle 却是共享的实时文件。**
   - `sandbox.sh up <idx>` 会把 `srv/index_v28.ts` **拷**成 `s$idx/index.ts`（之后不再跟随）；
     而前端 bundle 由 `harness.js --root=<yl-deploy>` **直接读 `build/assets/`**，改了就立刻生效。
   - 后果：**中途改了服务端，已起的沙盒不会更新** → 会拿「新前端 + 旧服务端」跑出假结论。
     实测踩过：flow-1 在 07:20 前用旧服务端复现了「宗门功法并发重复扣贡献」，其实该 bug 已修。
   - 规矩：**任何服务端补丁落地后，必须 `down <idx>` + `up <idx>` 重起沙盒**，并核对
     `md5sum /d/Personal/Temp/yl_v28_sandbox/s$idx/index.ts` == 期望值，再跑测试。

2. **抽屉/移动端容器是 `md:hidden`** —— 1440px 视口下 `document.body.innerText` 看不到抽屉内容。
   → 断言抽屉必须 `pg.set_viewport_size({"width":390,"height":844})`，并直接读
   `.flex-1.overflow-y-auto.p-2` 的 `innerText`。

3. **客户端乐观增量 + 服务端 `gm_revision` 拉档会双计。**
   → 任何「客户端本地加钱」的断言，必须在**请求前快照** `before`，**响应后**比对
   `now === before` 才叠加。测试竞态时可用 `page.evaluate` 手动调 `fetchSave()` 制造。

4. **`sects.id` 是 INTEGER 主键**（不是字符串）；功法阁只依赖**存档里**的字符串 `player.sectId`，
   与 `sects` 表无强绑定。

5. **DB 驱动是 `sqlite3`（回调式）**，不是 better-sqlite3。直接改库的脚本用 `node` + 沙盒的
   `node_modules`（`NODE_PATH=<sb>/node_modules`）。表名注意：信箱是 **`mail`**（不是 `mails`）；
   服务端库文件名 **`database.sqlite`**。

6. **Tailwind 是预构建 CSS** —— 新类名（未在构建时出现过的）静默失效，不会报错。

7. **本作无 app 级 ErrorBoundary**；人物志模块自带 `YlxwCharSafe` 错误边界，其它模块没有。

8. 服务端 `--experimental-strip-types` 直跑 `.ts`；**没有编译产物**。改 `.ts` 后必须重启进程。

---

## 5b. ★ 深测基建坑（2026-09-28 沙盒深测新踩）

1. **`up` 之后不能立刻 `seed`**：v28 服务端 `sects` / `sect_members` / `player_sect_gongfa` /
   `sect_welfare_claims` / `sect_ledger` 的建表是**独立 `db.run`（异步）**，而 `app.listen` 在其后不远处
   → 端口已就绪、表还没建完，seed 会 `SQLITE_ERROR: no such table: player_sect_gongfa`。
   已在 `sandbox.sh up` 里接 `wait_tables.js` 轮询等表（最多 30s），**必须走 `sandbox.sh up`**。

2. **API 请求 URL 带 `?token=`**：客户端把 access token 放在**查询串**里，例如
   `http://127.0.0.1:3201/yl/api/market/payouts/claim?token=eyJ...`。
   → Playwright 的 glob 路由 `**/market/payouts/claim` **匹配不上**（后面还有 `?token=`）。
   → 用正则：`pg.route(re.compile(r".*/market/payouts/claim.*"), handler)`。

3. **不要在 Playwright route handler 里 `time.sleep`**：sync API 的事件循环与 handler 同线程，
   sleep 期间**页面真实发生的 request/response 事件不会投递**，事后拿到的时间戳全部失真
   （会得出「窗口内拉档 0 次」这种假证据）。
   → 要「服务端先处理完、响应再延迟放行」的确定性竞态，用 **`localtest/delayproxy.js`**：
   ```bash
   MSYS_NO_PATHCONV=1 node localtest/delayproxy.js --port=3106 --target=3105 --delay=9000 --match=/market/payouts/claim
   node localtest/harness.js --port=3206 --api-port=3106 --root="$PWD" --bundle=index-v28-20260928.js
   # Playwright 打 3206；直连 HTTP 断言仍打 3105
   ```

4. **Git Bash 会吃掉 `--xxx=/path` 形式的参数**：`--match=/market/payouts/claim` 会被 MSYS 转成
   `C:/Users/.../PortableGit/versions/1.2.0/market/payouts/claim`。
   → 前面加 `MSYS_NO_PATHCONV=1`。

5. **`saves` 表没有 `spiritStones` 列**：玩家数据全在 `saves.save_data`（JSON 文本）。
   要读灵石：`json.loads(row[0])["player"]["spiritStones"]`。

6. **`saves.updated_at` 陈旧会污染灵石增量断言**：首次登录会结算「挂机收益」（`calcOfflineGainV2`，
   与客户端 `Nw` 同源），实测混入过 8333 灵石。
   → 测增量前先 `UPDATE saves SET updated_at = CURRENT_TIMESTAMP WHERE user_id=?`，
   → 并且快照要取在**点击前一刻**，不要用登录后读到的值。

7. **客户端 bundle 用 `pg.route` 追加 hook 时，匹配要放宽**：A/B 换 bundle 文件名（如 `_oldbug_v28.js`）后
   `**/assets/index-v28-*.js` 就匹配不上了 → 用 `**/assets/*.js`。

8. **6s 拉档 tick 的真实条件**（`function jS()`）：`setInterval(..., 6000)`，
   先 `fetchRevision()`（`GET /api/save?revision=1`），仅当
   `d.gm_revision > max(a.current, appliedGmRevision)` 且 `!YLSync.isBusy()` 时才 `fetchSave()` + `applyRemoteSave()`。
   另有 10s 自动推档 `setInterval(..., 1e4)`。

---

## 6. 报告要求（每人一份）

写到 `localtest/report_<你的名字>.md`，格式：

```
# <你的名字> 深测报告

## 结论速览
- PASS x / FAIL y / 疑似 bug z

## 用例明细
| # | 用例 | 账号 | 预期 | 实际 | 判定 |
|---|---|---|---|---|---|

## 疑似 bug（必须含复现步骤 + 原始证据）
### BUG-1 <一句话标题>
- 复现：...
- 证据：<原始 JSON / 截图路径 / 控制台报错>
- 影响面：...
- 建议修法：...

## 未覆盖 / 阻塞
```

**判定纪律**：`FAIL` 必须有**原始证据**（HTTP 状态码 + body、或 DB 里的实际行、或控制台原文）。
**没有证据的「我觉得」不算 FAIL，算「待确认」。**
