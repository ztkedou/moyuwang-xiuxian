# DEPLOY LOG — 《摸鱼修仙传》 0.9.20 (v2920)

- 部署时间：2026-10-03 23:49 (GMT+8)
- 目标：香港 VPS `47.243.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2820.sh`（**服务端链重建批**：客户端 + 服务端 + CHANGELOG + index.html bump；**不可加 `--skip-server`**）
- 定点核对：`deploy_v28/remote_check_v2820.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0820.env`
- 备份整包：`/root/backup/yl_pre_v2920_20261003_234850.tar.gz`
- DB 一致性快照：`/root/backup/database_v2920_consistent_20261003_234850.sqlite`

---

## 1. 本批范围：0.9.20（客户端 95 模块 + standalone 27 脚本；服务端 66 → **67 环**）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-144 | 在线人物 → **真实在线玩家名单**：新端点 `GET /api/online/players`（最近 5 分钟内有活跃上报，双源 UNION）；客户端面板改读真名单，每行加「加好友 / 拜师 / 切磋」三入口 | 服务端新末环 `patches/server/srv_patch_r144.py`；客户端 standalone `yl_r144_ext.py`（**原位改造**，不新增脚本） | ✔ | ✔ |

★ 用户 2026-10-03 拍板两项，本批落地：

1. **R-141 稀有属性封顶口径 = 「每类 ≤80%」**（即已实现口径，**不改**）——
   `YlxwBattleCapCfg = { critRate: 0.35, critDamage: 0.8, dodgeRate: 0.35, lifeLeech: 0.25, damageReduction: 0.5 }` 逐条独立封顶，非「合计 ≤80%」。
2. **R-144 在线判定口径 = 「最近 5 分钟内有活跃上报」**——
   `const ONLINE_WINDOW_MS = 5 * 60 * 1000;`（服务端常量，写进本环门禁）。

### 1.1 R-144 服务端面（本批唯一服务端改动）

- 端点：`app.get('/api/online/players', authenticateToken, rateLimit({ windowMs: 60 * 1000, max: 60, ... }))`
- 双源 UNION 去重（取 `MAX(ts)`，任一源新鲜即算在线）：
  1. `active_sessions.last_seen` —— 客户端每 15s 心跳（`YLSync.beat()` → `POST /api/session/heartbeat`）写入，**权威源**；
  2. `saves.updated_at` —— 存档兜底；该列是 SQLite `CURRENT_TIMESTAMP`（**UTC**），
     故必须 `CAST(strftime('%s', updated_at) AS INTEGER) * 1000` 转毫秒 epoch。
- 名字/境界口径与 `/api/friends/list` **同源**（逐字）：`COALESCE(NULLIF(r.name,''), u.username)` /
  `REALM_ORDER_FOR_RANKING[idx]` / `level = realmIndex*9 + realmLevel`。
- 响应体：`{ now, windowMs, total, players:[{ id, name, realmIndex, realmName, realmLevel, level,
  combatPower, isFriend, isSelf, online }] }` —— **含自己**（`isSelf: true`），按最近活跃倒序，上限 `ONLINE_LIST_MAX = 50`。
- 幂等索引：`CREATE INDEX IF NOT EXISTS idx_active_sessions_last_seen ON active_sessions(last_seen)`。
- 插入锚点 = `app.post('/api/friends/add', authenticateToken,` **之前**（装配态实测 `count == 1`）。
- 业务拒绝一律 **409**（绝不 403 —— 客户端 `Xc()` 见 403 会强制登出）。
- **零新表、零新列**（只读既有 `active_sessions` / `saves` / `rankings` / `friendships` / `users`）。

### 1.2 R-144 客户端面

- 徽章 `span` → `button`（去掉 `C>0&&` 守卫，始终可点）→ 派发 `open-online-panel`；
- 覆盖层「在线人物 · 好友」上半 = 服务端真名单（`!isSelf` 行渲染 加好友 / 拜师 / 切磋），
  下半 = 好友列表（加 / 删 / 赠灵石）；
- 文案由「最近在公屏说过话」改为「**最近 5 分钟内有活跃**」；近似来源 `kk(0,60)` 已清零（门禁 `eq 0`）。
- 复用端点（**本批零新增**）：`/friends/list`、`/friends/add`、`/friends/remove`、`/friends/gift`、
  `/mentor/apprentice`、`/arena/challenge`。

## 2. 指纹（部署前后）

| 对象 | 0.9.19（部署前） | 0.9.20（部署后） |
|---|---|---|
| `www/assets/index-v2920-20261003.js` | —（新文件） | `8ad857ffb547c8747f17c88a4638be9b`（2,299,359 B） |
| `www/assets/index-v2919-20261003.js` | `c02350f26d1d65c35e1640748901a466` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2918-20261003.js` | `7abf7b22308cfdba58312f21705a5e02` | 同左（更早的回滚点） |
| `www/assets/index-v2917-20261003.js` | `0470077292ba4ca446f92897257e0c54` | 同左（更早的回滚点） |
| `server/index.ts` | `664501929cecb41fd57e65d9d0c48872` | `4c3a3eea75ca8f11be18b5c0c2127dd1`（982,652 B，**+2,562 B**） |
| `www/CHANGELOG.md` | `b3939a1b69f3e518ac61192884dda52f` | `3003b55624e64fe0d45f996feba99725` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批未动） |

链产物（单变量可核）：

```
s20.t16arena.ts  7780e099a6cd1ac0de4b502c467ae2c0   824,768 B  ← == 0.8.9 定版（前 20 环不变）
s64.r128.ts      77c705ec1035c91eedd7b9eb7dde824e   976,544 B  ← == 0.9.13 定版
s65.r112.ts      9033c805be1022e692bc67f7ccc3b1ae   979,955 B  ← == 0.9.15 定版
s66.r136.ts      664501929cecb41fd57e65d9d0c48872   980,090 B  ← == 0.9.16~0.9.19 定版（本批**已变**）
s67.r144.ts      4c3a3eea75ca8f11be18b5c0c2127dd1   982,652 B  ← 链尾（本批新增第 67 环）
```

部署后线上实测（ssh 独立复核）：

```
8ad857ffb547c8747f17c88a4638be9b  /opt/yl/www/assets/index-v2920-20261003.js
c02350f26d1d65c35e1640748901a466  /opt/yl/www/assets/index-v2919-20261003.js   （0.9.19 回滚点保留）
7abf7b22308cfdba58312f21705a5e02  /opt/yl/www/assets/index-v2918-20261003.js   （更早回滚点保留）
4c3a3eea75ca8f11be18b5c0c2127dd1  /opt/yl/server/index.ts
3003b55624e64fe0d45f996feba99725  /opt/yl/www/CHANGELOG.md
```

公网双路（`curl`）：

```
index.html 引用        : index-v2920-20261003.js（且 v2919 引用已清零）
/assets/index-v2920... : 200
/assets/index-v2919... : 200（回滚点保留）
CHANGELOG_PLAYER.md 头  : ## [0.9.20] - 2026-10-03 23:55
bundle 内版本号         : YLVERSION_FALLBACK = "0.9.20"
GET /api/online/players（无 token）: 401（**不是 404** ⇒ 新端点确已上线）
systemctl is-active     : active（NRestarts: 0；日志 "Server running on port 3001" / "Connected to the SQLite database."）
```

## 3. 部署前本地验收

- `python localtest/chain_build.py --srv` → `SRV_CHAIN` 66 → **67 环**，
  `[67/67] srv_patch_r144.py` 门禁全绿 + `R144 绑定数自证(3)` → 落盘 `srv/index_v28.ts` = `_chainstage/s67.r144.ts`
  = `_chainstage/index_v28.v28112.ts`（三文件 md5 `4c3a3eea…`，982,652 B）；`node --experimental-strip-types --check` rc=0。
- `python build_v26n.py` → `build/assets/index-v2920-20261003.js`（2,299,359 B，md5 `8ad857ffb547c8747f17c88a4638be9b`）
  - V28_MODULES 95 模块 + standalone **27 脚本**（r144 为原位改造，脚本数不变）**全部 rc ∈ {0,3}**
  - `[standalone/r144]` 门禁 **23/23 PASS**，delta `+6358 B`（2,292,156 → 2,298,514）
  - `node --check` rc=0
- `python localtest/dryrun_087.py` → **门禁 PASS（FAIL=0）**，standalone **622 条** FAIL 0，
  且预演产物 `_chainstage/dryrun_087.bundle.js` 的 md5 **== 交付产物 md5** ⇒ **「预演==交付」成立**
- `python localtest/sim_remote_check.py` → **OK=344 / SKIP(远端专有)=13 / FAIL=0**
  （★ 本批新增特征断言后曾抓出 2 处预期值写错：`COALESCE(NULLIF(r.name,''), u.username) AS name` 与
  `REALM_ORDER_FOR_RANKING[Number(r.realm_index)]` 是**全服共用式**，在服务端分别出现 26 / 3 次，
  误写成 `eq 1` ⇒ 已订正为 `ge 2`「同源」语义）
- `deploy_v2820.sh` step 0 / 0b / 0c 全过（EXPECT 指纹比对 + 双 provenance 自证 + 远端未漂移断言）

## 4. 线上验收

- `remote_check_v2820.sh` → **PASS (0 failures)**
- 服务健康：`systemctl is-active yl-server = active`；`NRestarts: 0`；maintenance flag absent
- 线上库核对：0.8.7 的 8 张表 + `sects.join_mode` + 0.8.9 `pets` 三列 + 0.8.11 两新列全部在位；
  **本批新增一项**：`db: idx_online yes` ⇒ R-144 索引 `idx_active_sessions_last_seen` 已建
  （服务端启动时跑 `CREATE INDEX IF NOT EXISTS` ⇒ 该断言同时证明服务端确已启动过）
- 公开冒烟：见 §2「公网双路」

## 5. 本轮踩到的新坑（★ 重要，后续批次必看）

### 5.1 生成核对脚本时「v 字号整体位移兜底」会把 `OLD_BUNDLE` 一起改掉 ⇒ 首轮核对假 FAIL

`_mk_rc2820.py` 末尾原有一句兜底：

```python
for old, new in (('index-v2919-20261003.js', 'index-v2920-20261003.js'),):
    s = s.replace(old, new)      # ← 本意「万一还有裸 v2919」，实际把刚精确设好的 OLD_BUNDLE 也改了
```

后果（**已实测发生**）：`OLD_BUNDLE` 变成 `index-v2920-20261003.js` ⇒ 线上核对里
`chk "$IH" "assets/$OLD_BUNDLE" ... eq 0` 变成在数**新包自己** ⇒ 必然 x1 FAIL；
`md5sum .../$OLD_BUNDLE` 也把新包当旧包 ⇒ 指纹行是假数据。

**规矩**：**精确 `rep()` 做完就收工，绝不追加任何全局 replace 兜底**；若确需兜底，
**只允许断言、不允许改写**（本批已在 `_mk_rc2820.py` 末尾改成 3 条 `assert`）。
**排查线索**：核对输出里出现「`bundle old` md5 == 新包 md5」即可确诊。

### 5.2 `deploy_v2820.sh` 是 `set -euo pipefail`，step 5 返回非零 ⇒ 脚本在 step 5 后**中止**

`step 5` 的 `run "$SSH $HOST \"bash .../_remote_check_v2820.sh ...\""` 返回 = FAIL 数；
非零 + `set -e` ⇒ 脚本直接退出，**step 6（生成 `DEPLOY_LOG_${CHG_VER}.md` 模板）与 `step done` 都不会执行**。
本批首轮即因此未生成日志模板，**本文件为据实手工补写**（指纹与核对结论均取自真实产物/线上实测）。

**规矩**：`remote_check` 出现非零时，**先按 §5.1 查是否核对脚本自身写错**；
确认是核对脚本问题后，修好脚本、**单独 `scp` 重跑核对拿 PASS**，再手工补 DEPLOY_LOG。
（不要再整跑 `deploy_v2820.sh`：step 0b 的「远端未漂移断言」会因线上已换版而 ABORT。）

### 5.3 「同源口径」类断言不能用 `eq 1`

服务端里 `COALESCE(NULLIF(r.name,''), u.username)` 这类**全服共用式**出现 26 次、境界式 3 次。
断言「与 `/friends/list` 同源」的正确写法是 `ge 2`（≥2 处 ⇒ 至少既有面 + 本端点各一次），
而不是 `eq 1`。**必须跑 `sim_remote_check.py` 才拦得住**。

### 5.4 远端无 `sqlite3` CLI 时核对「索引是否已建」的可用写法

沿用 SKILL §22.15 的驱动兜底，但**新增一条独立的 node 小脚本**（不塞进既有 8 表脚本的异步回调链）：

```bash
cat > /tmp/_yl_idxchk_0820.js <<'IDXEOF'
const SQL = "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_active_sessions_last_seen'";
// better-sqlite3 优先；退化到 sqlite3 时用 open 回调 + db.close()
IDXEOF
```

输出 `idx_online yes|no|skip`；`skip`（无驱动）记 WARN 不记 FAIL。

## 6. 残留清理

远端 `_remote_check_v2820.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` 留在 `/opt/yl/server/` 便于复跑。
本地 `_mk_rc2820.py`（生成器）留在仓库根，与 `_mk_*.py` 系列同列。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@47.243.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2920-20261003_234850 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2920-20261003.js --to=index-v2919-20261003.js
cp -a /root/backup/index.ts.pre-v2920-20261003_234850        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2920-20261003_234850 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2920-20261003_234850    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2919-20261003.js.pre-v2920-20261003_234850 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 0.9.19 定版：bundle=c02350f26d1d65c35e1640748901a466  server=664501929cecb41fd57e65d9d0c48872
# 整包：/root/backup/yl_pre_v2920_20261003_234850.tar.gz
```

★ 回滚注意：本批**零新表、零新列**，只新增了**一个索引** `idx_active_sessions_last_seen`。
回滚到 0.9.19 时**无需任何数据库动作**（多余索引无害，0.9.19 代码不读它，且对既有查询只有好处）；
`index.html` 指回 `index-v2919-20261003.js` + 还原 `index.ts` + 重启即可。

## 8. 0.9.20 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=8ad857ffb547c8747f17c88a4638be9b        # 0.9.20 定版 index-v2920-20261003.js（线上在跑）
PREV_PREV_BUNDLE_MD5=c02350f26d1d65c35e1640748901a466   # 0.9.19 定版 index-v2919-20261003.js（回滚点）
PREV_PREV2_BUNDLE_MD5=7abf7b22308cfdba58312f21705a5e02  # 0.9.18 定版 index-v2918-20261003.js（更早回滚点）
PREV_SRV_MD5=4c3a3eea75ca8f11be18b5c0c2127dd1           # 链尾 s67.r144.ts（67 环）
PREV_CHANGELOG_MD5=3003b55624e64fe0d45f996feba99725
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S20_MD5=7780e099a6cd1ac0de4b502c467ae2c0       # 前 20 环不变
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
