# DEPLOY LOG — 《摸鱼修仙传》 0.9.26

- 部署时间：**2026-10-06 17:13 (GMT+8)**
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2826.sh`（客户端 + 服务端 + CHANGELOG + index.html bump）
- 定点核对：`deploy_v28/remote_check_v2826.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0826.env`
- 备份整包：`/root/backup/yl_pre_v2926_20261006_171202.tar.gz`
- DB 一致性快照：`/root/backup/database_v2926_consistent_20261006_171202.sqlite`
- 生成器：`_mk_2826.py`（deploy）/ `_mk_rc2826.py`（remote_check）—— 机械重登记，**只做整名替换**（铁律 D）

---

## 1. 本批范围：0.9.26（客户端 95 模块 + **35** standalone 脚本；服务端 **77 环**）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-167 | 仙务·妖灵面板去重 + 喂养当日首次免费 | `yl_r167_ext.py` / `srv_patch_r167.py`（第 73 环） | ✔ | ✔ |
| R-168 | 灵田三类草收益重定档 | `srv_patch_r168.py`（第 74 环） | — | ✔ |
| R-169 | 洞府灵草旧名归一（`__halias` 别名表） | `yl_r169_ext.py` | ✔ | — |
| R-170 | 成就奖励按需求次数正比重定档 | `srv_patch_r170.py`（第 75 环） | — | ✔ |
| R-171 | 成就每组首档一律 2000 灵石 | 同 R-170（同环） | — | ✔ |
| R-172 | 仙途指引奖励按「实际付出的努力」重定档 | `srv_patch_r172.py`（第 76 环） | — | ✔ |
| R-173 | 挂机（离线）时长服务端权威化 | `srv_patch_r173.py`（第 77 环 / 新末环） | — | ✔ |

**服务端链 72 → 77 环**：
```
s72.r165.ts  6ebc3d070e401af46e199bf2926fe127    989,996 B  ← == 0.9.25 定版（本批 PREV）
s73.r167.ts  7555a8de8ca5cfaac074329f829f7df0    993,712 B  ← R-167 pet_feed_log 喂养首免
s74.r168.ts  3feaae580348ce895eec906d55ab993c    996,895 B  ← R-168 灵田三类草重定档
s75.r170.ts  50b8eebc0608155931790f0535b42d49    997,278 B  ← R-170/R-171 成就奖励正比
s76.r172.ts  d027cca020c50091191c9d92dda11a79    997,731 B  ← R-172 指引奖励按努力
s77.r173.ts  a5927a49b17d5262aa12b3f61f27d740  1,005,270 B  ← R-173 离线时长权威化（链尾）
```

### 各条要点
- **R-167**：客户端删掉与「进食/互动」完全重复的独立「喂养/嬉戏」按钮（逐字节坐实同请求同价：独立嬉戏 = `tease`、独立喂养 = `common`），标题改自解释文案；服务端新表 `pet_feed_log` + **单语句原子闸门** `ON CONFLICT ... DO UPDATE SET times = times + 1 WHERE times < 1`（`changes>0` ⇒ 当日首次免费），含失败回退补偿。★ 取证发现 `r018FeedTier()` 返回**共享引用** ⇒ 必须复制成可变副本，否则改 `.cost` 会污染全局常量。
- **R-168**：新增 `R168_FARM_TABLE` 覆写（**追加而非原地改 R163 表**，因 R163 每行带中文尾注 ⇒ 原地改需非 ASCII 锚点，违反契约）。sell 净赚恒 300 灵石/h；mix 变卖 = 种子 ×1.10（回本+10%）；cult 服用修为 15000/45000/150000/600000/3000000。经济红线复算：满配最高回收率 1.200×1.21 = **1.452 ≤ 1.5** ✓
- **R-169**：根因**不在服务端**（`grep -c "配置信息缺失" srv/index_v28.ts` = 0），而是**旧存档带着改名前的灵草名**（`grotto.herbarium`）回来收菜。修法 = 客户端 `__halias` 补齐 5 条确定映射；拿不准的 5 个（天灵草/星辰草/凤羽草/灵凤羽草/雪莲花）**不写入**，另列待确认。
- **R-170/R-171**：`reward = round3sig(2000 × 该档需求 / 组内首档需求)`，每组首档恒 2000。全 50 项 Σ 723,500 → **241,300,470**。★ 财富组末档 = 1 亿（待拍板，备选方案只写进注释未进代码）。
- **R-172**：以「累计升级所需修为」为度量（`realmMaxExp` × `TRIB_REALM_BASES` 逐档求和）重算：lv9 6000→8600、lv10 8000→9900、lv19 20000→61000；社交三步与锚点保持。Σ 60,000 → 105,500。
- **R-173**：新增服务端权威列 `saves.last_active_at`（复用既有 `safeAddColumn` 迁移写法，**零新增 PRAGMA**），在 `authenticateToken` 的 `res.on('finish')` 打点（60s/人节流）⇒ 在线期间窗口恒 ≤60s、真离线精确累计。`offlineRewards/offlineWindow/OFFLINE_*` **一行未动**，老行逐位回落。

## 2. 指纹（部署前后）

| 对象 | 0.9.25（部署前） | 0.9.26（部署后，线上实测） |
|---|---|---|
| `www/assets/index-v2925-20261006.js` | `153c19120249210e7aa546eeb6ab740a` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2924-20261006.js` | `3d0980c5c4f5f6adc988101d7411bec5` | 同左（0.9.24 定版，更早的回滚点） |
| `www/assets/index-v2926-20261006.js` | —（新文件） | **`6ed91e0e46b90fada980367459cbe3fc`** |
| `server/index.ts` | `6ebc3d070e401af46e199bf2926fe127` | **`a5927a49b17d5262aa12b3f61f27d740`** |
| `www/CHANGELOG.md` | `fe24e79cba41df3c83e0a8eff441b119` | **`7069fe8525c81e990dd527827a67a275`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批未变） |

部署后线上实测（`deploy_v2826.sh` 采集）：
```
a5927a49b17d5262aa12b3f61f27d740  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
7069fe8525c81e990dd527827a67a275  /opt/yl/www/CHANGELOG.md
6ed91e0e46b90fada980367459cbe3fc  /opt/yl/www/assets/index-v2926-20261006.js
```

## 3. 部署前本地验收

| 环节 | 命令 | 结果 |
|---|---|---|
| 服务端链 + 前端装配 | `localtest/chain_build.py --all` | rc=0；**77 环**；链尾 `node --experimental-strip-types --check` rc=0 |
| 客户端预演 | `localtest/dryrun_087.py` | 门禁 **PASS（FAIL=0）**；standalone 711 → **741** 条；「预演==交付」md5 `6ed91e0e…` 一致 |
| 远端断言本地预演 | `localtest/sim_remote_check.py --script deploy_v28/remote_check_v2826.sh` | **OK=454 / SKIP=15 / FAIL=0** |
| 五环串行无锚区冲突 | 临时副本依次套用 r167/r168/r170/r172/r173 | 5/5 rc=0；链尾 `node --check` rc=0；复跑 5/5 SKIP |
| 链 s20 单变量可核 | `_chainstage/s20.t16arena.ts` | `7780e099a6cd1ac0de4b502c467ae2c0` == 0.8.9 定版（前 20 环不变）✓ |

## 4. 线上验收

| 项 | 结果 |
|---|---|
| `REMOTE-CHECK` | **PASS (0 failures)** |
| 新 bundle | `6ed91e0e46b90fada980367459cbe3fc` |
| 服务端 index.ts | `a5927a49b17d5262aa12b3f61f27d740`（1,005,270 B，77 环） |
| CHANGELOG.md | `7069fe8525c81e990dd527827a67a275` |
| 游戏内版本号 | `YLVERSION_FALLBACK = "0.9.26"` |
| 服务 | `yl-server` **active**，`NRestarts=0` |
| ★ gzip 同包（R-159 防线） | `zcat /opt/yl/www/index.html.gz` 命中 `assets/index-v2926-20261006.js` ×1 |
| ★ 公网带 `Accept-Encoding: gzip` 冒烟 | http=200，gunzip 后命中 v2926 ×1 |
| 明文冒烟 | `index.html` 指向 `assets/index-v2926-20261006.js` |
| 新包可访问 | `GET /myxxz/assets/index-v2926-20261006.js` → 200 |
| 新表 / 新列 | `pet_feed_log` + `saves.last_active_at` 均在线上 index.ts 中 |
| 五环标记 | `r167feed` / `r168farm` / `r170ach` / `r172guide` / `r173offline` 全部在位 |
| 无 token 探针 | `POST /api/wudao/enlighten` → 401（与既有端点一致） |
| CHANGELOG 公网 | `GET /myxxz/CHANGELOG.md` → 200 |

## 5. 本轮踩到的新坑（★ 务必保留）

1. ★ **bundle 内该段中文以 `\uXXXX` 转义存储** ⇒ `remote_check` 的客户端断言必须用**转义形态**。
   首轮 `sim_remote_check` 因用原文形态 `'今日互动已用 '` 而 FAIL 1 条（实际计数 0），改用
   `'\u4eca\u65e5\u4e92\u52a8\u5df2\u7528 '` 后通过。**教训：客户端断言动手前先两种形态都 grep。**
2. ★ **`r018FeedTier()` 返回共享引用**（`R018_FEED_TIERS[k]`）⇒ 直接把 `.cost` 改 0 会**污染全局常量**。
   必须复制成可变副本 `{cost, hunger, name}` 再改。已在补丁文件头记录。
3. ★ **R-168 必须「追加覆写表」而非「原地改 R163 表」** —— R163 每行带中文尾注，原地改会引入非 ASCII 锚点，
   违反「锚点纯 ASCII」契约；追加一张 `R168_FARM_TABLE` 与 R-163 覆写 R-047/R-129 的既有链式做法一致。
4. ★ **R-169 的根因是「数据」不是「配置」** —— 差一点就在服务端补 `FARM_CROPS_NEW`（那会把「血参草」
   变成 `/api/farm/status` 里可播种的**灵田**品种，**串系统**）。取证顺序：先 `grep` 服务端（0 命中）⇒ 再定位客户端兜底文案。
5. ★ **`dryrun_087.py` 的 standalone 门禁名单是硬编码的** —— 上一批（0.9.25）补齐了 6 个漏登记脚本；
   本批新增 r167/r169 后，报告文案里的「共 33 脚本」也同步改成「共 35 脚本」（本轮已顺手修正）。
6. ★ **后台子代理会话中断会静默丢产出** —— 本轮中途会话被挂起约 3.7 小时，后台代理全部终止，
   其中 2 项（r167 服务端 / r169 客户端）产出缺失。**恢复后必须先 `ls` 核对产出文件是否存在，再判断代理是否真的完成。**
7. **R-168 的 `R163_FARM_TABLE` 保留为历史档**（被 R168 表覆写，最终值以 R168 为准）——
   排查数值时**不要**直接读 R163 表，否则会看到已失效的旧值。

## 6. 残留清理

远端 `_remote_check_v2826.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` / `_remote_gz_sync.sh`
留在 `/opt/yl/server/` 便于复跑（惯例）。
本地：`_chainstage/` 各环产物与 `s73~s77` 中间件保留（供单变量可核）；
补丁脚本自测产生的临时副本与 `.bak-r1xx-*` 已全部删除，`srv/` 与 `build/` 无残留。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2926-20261006_171202 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2926-20261006.js --to=index-v2925-20261006.js
cp -a /root/backup/index.ts.pre-v2926-20261006_171202        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2926-20261006_171202 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2926-20261006_171202    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2925-20261006.js.pre-v2926-20261006_171202 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版（0.9.25）：bundle=153c19120249210e7aa546eeb6ab740a  server=6ebc3d070e401af46e199bf2926fe127
# 整包：/root/backup/yl_pre_v2926_20261006_171202.tar.gz
```

★ 回滚注意：本批新增**表** `pet_feed_log` 与**列** `saves.last_active_at`。
回滚到 0.9.25 时**无需删表/删列**（旧代码不读它们，多余对象无害）；
**如需完全还原**用 `/root/backup/database_v2926_consistent_20261006_171202.sqlite`。
★ 另注意：`pet_feed_log` 的当日计数行属**数据行**，回滚后留存无害（0.9.25 不读）。

## 8. 0.9.26 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=6ed91e0e46b90fada980367459cbe3fc        # 0.9.26 定版 index-v2926-20261006.js
PREV_SRV_MD5=a5927a49b17d5262aa12b3f61f27d740           # 0.9.26 定版 srv/index_v28.ts（= s77.r173.ts，77 环）
PREV_CHANGELOG_MD5=7069fe8525c81e990dd527827a67a275     # 0.9.26 定版 CHANGELOG.md
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S77_MD5=a5927a49b17d5262aa12b3f61f27d740       # 链尾 s77.r173.ts（供 0.9.26 单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
