# DEPLOY LOG — 《摸鱼修仙传》 **0.9.44**（R-210 心法按钮/进度 · R-211 签到补签卡 · R-212 奇遇消耗 1%）

- 部署时间：**2026-10-09 12:18 (GMT+8)**（= CHANGELOG `[0.9.44]` 条目头时刻）
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2844.sh`（**混合批**：客户端 + **服务端 88→89 环** ⇒ 会重启 `yl-server`）
- 定点核对：`deploy_v28/remote_check_v2844.sh` → **PASS (0 failures)**（555 OK / 15 SKIP(远端专有) / 0 FAIL）
- 登记指纹：`deploy_v28/EXPECT_0844.env`；生成器 `_mk_2844.py`
- 备份整包：`/root/backup/yl_pre_v2944_20261009_121853.tar.gz`（六件 `.pre-v2944-20261009_121853` + DB 一致性快照）

---

## 1. 本批范围：0.9.44 = **3 条**

| # | 需求（用户原话） | 服务端 | 客户端 |
|---|---|---|---|
| R-210 | 「功法阁，心法已经改为经验了，但是按钮还是旧的显示内容，并没有修炼一次加了多少经验，并且下面的进度提示也不明显」 | 零改动 | `yl_r214_ext.py`（r214） |
| R-211 | 「活动中心的每日签到，增加一个补签卡的功能，一张补签卡售价2W，每买一次售价变高1.5倍」 | **第 89 环** `srv_patch_r211.py` | `yl_r215_ext.py`（r215） |
| R-212 | 「抽奖中的奇遇抽奖把消耗改为修为的1%」 | **同上第 89 环** | 零改动 |

### 拍板（用户 2026-10-09 12:0x 已答复，正文见 `需求台账/拍板记录.md`）
- **R-211 ①** 形态 = **买卡即补签（一步）**（不做背包/库存）。
- **R-211 ②** 涨价计数 = **该玩家历史累计补签次数**（跨月累计、不重置）—— 此条**未问、按建议执行**。
  `price(n) = floor(20000 × 1.5^n)`；★ 若要改成「每月重置」：把计数 SQL 的 `WHERE` 加上 `event_id` 即可（一处）。
- **R-212** 1% 的基数 = **当层修为槽上限 `maxExp`**（**非**玩家当前修为）。

## 2. 指纹（部署前后）

| 对象 | 0.9.43（部署前） | 0.9.44（部署后） |
|---|---|---|
| `www/assets/index-v2944-20261009.js` | —（新文件） | **`7dec9546b3b9849063338558ee8eadac`**（2,321,459 B） |
| `www/assets/index-v2943-20261009.js` | `374c68e8a7cd9809cb24e4f8992c5a3b` | 同左（旧包保留 = 回滚点） |
| `www/assets/index-v2942-20261008.js` | `8f3fa81066c374edd9eed60a904f8547` | 同左（更早回滚点） |
| `server/index.ts` | `2f49c2a7bc1b7348c2732912afe968ff`（88 环） | **`a40670097c22074d4c5c31a444118057`**（1,024,938 B，**89 环**） |
| `www/CHANGELOG.md` | `39bd02f72c6d6df38eb907e4ee927e7b` | **`eb0725762dff07653b42a0894a376efe`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批不变） |

部署后线上实测（deploy_v2844.sh 采集 + 独立复核）：

```
a40670097c22074d4c5c31a444118057  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
eb0725762dff07653b42a0894a376efe  /opt/yl/www/CHANGELOG.md
7dec9546b3b9849063338558ee8eadac  /opt/yl/www/assets/index-v2944-20261009.js
```

## 3. 改动摘要

### R-210 心法面板（纯客户端 r214）
| # | 位置 | 改法 |
|---|---|---|
| E1 | 修炼按钮 | `"修炼"` → **`"修炼 +" + YlxwNum(_pc) + " 经验"`**（`_pc` = `costNext`，同一 map 回调内已有，零新增取数） |
| E2 | 进度条 | `h-1.5` → **`h-2.5`**（6px→10px）；包成 flex 一行并在右侧补 **`NN%`**（`Math.floor(pct)`，**与条宽同源**） |
| E3 | 说明行 | `text-[11px] text-stone-500` → **`text-xs text-stone-300`**；**进度前置**；补 **「（还差 C 经验）」**（`max(0, levelNeed-levelExp)` 钳 0） |

### R-211 补签卡
**服务端（第 89 环）**
- 新表 `activity_makeup (player_id, event_id, day, price, created_at)`，PK 三元组 = **幂等键**，**行数 = 涨价指数 n**。
- 新端点 `POST /api/activity/checkin/makeup { day }`：校验（当月天数内 ∧ 已过去 ∧ 未签 ∧ 活动激活 ∧ 引擎开）
  → `price = floor(20000 × 1.5^n)` → 占位 `INSERT OR IGNORE` → **单次 `updatePlayerSave` 内**扣 `price` + 发当日签到奖励
  （灵石 1.0h + 修为 0.5h，与正常 claim 同口径）→ 计入 `activity_checkin`（**与正常签到同表 ⇒ 自动进 `progress` 与里程碑**）；
  扣款失败补偿删占位行（可重试）。
- `GET /api/activity/checkin` 新增下发 `makeup: { count, price, nextPrice, base, mul }`。
- ★ `claim` / 里程碑 / 场次逻辑**一字未动**（原注释「漏签不补」的缺口由本环**独立端点**补上）。

**客户端（r215）**
- 新增 `makeupDay(day)`（照抄 `claimMile` 范式，走 `act.run` ⇒ 统一 toast + reload）。
- 月历**漏签日格 `div` → `button`**（`title` 显价、点即补签、`disabled` 随 busy/engineOn），字符 **`✗` → `补`**。
- ★ **修掉已不成立的过时文案**：脚注原写「**漏签不补**，累计天数当月有效，每月重置」⇒ 删「漏签不补」，
  并新增 amber 行「补签卡：点上面标「补」的日子即可补签，现价 P 灵石（每补一次售价 ×1.5，已补 N 次）」。

### R-212 奇遇消耗（服务端，同一末环）
- 只改常量一处：`ADVENTURE_COST_RATE` **0.05 → 0.01**；消耗式 `Math.max(1, Math.floor(nr0.maxExp * ADVENTURE_COST_RATE))` **一字未动**。

## 4. 部署前本地验收（全绿）

| 层 | 手段 | 结果 |
|---|---|---|
| 1 门禁 | `yl_r214_ext.py` **13/13**、`yl_r215_ext.py` **13/13**、`srv_patch_r211.py` 门禁全绿 | PASS |
| 2 语法 | 客户端 `node --check`；服务端 `node --experimental-strip-types --check` | rc=0 |
| 3 装配预演 | `dryrun_087.py` | **FAIL 0 / SA-FAIL 0**；预演产物 md5 == 交付产物 md5（`7dec9546…`） |
| 4 本地模拟远端核对 | `sim_remote_check.py --script deploy_v28/remote_check_v2844.sh` | **OK=555 / SKIP=15 / FAIL=0** |

## 5. 线上验收

- `remote_check_v2844.sh` → **REMOTE-CHECK: PASS (0 failures)**；`systemctl is-active yl-server` = **active**
- 服务端**确实已重启**：`ActiveEnterTimestamp` = **2026-10-09 12:19:24 CST**（部署前是 10-08 17:15:28）
- 公开冒烟：`/myxxz/` 200、新 bundle 200、旧 bundle 200（保留）、`/yl/` 301、`api/*` 无 token 401、`CHANGELOG.md` 200
- **公网独立复核**（不依赖部署脚本结论）：
  - `curl .../assets/index-v2944-20261009.js` → md5 **逐位 == 本地**
  - `index.html` → `assets/index-v2944-20261009.js`；`CHANGELOG.md` 头 = `## [0.9.44] - 2026-10-09 12:18`
  - bundle 特征串：`YLXW_R214_V2944` ×1、`YLXW_R215_V2944` ×1、`YLVERSION_FALLBACK = "0.9.44"` ×1、
    `function makeupDay(day) {` ×1、**`漏签不补` ×0**
  - 远端 `index.ts`：`const ACT_MAKEUP_BASE = 20000;` ×1、`const ADVENTURE_COST_RATE = 0.01;` ×1、
    `app.post('/api/activity/checkin/makeup'` ×1
  - 新端点公网判活：`POST /myxxz/api/activity/checkin/makeup` 无 token = **401**（存在，非 404）

## 6. 端到端功能实测（沙盒 s9，真跑 API）

**R-211 补签卡**（`localtest/t_r211_makeup.py`）
```
GET /activity/checkin → makeup = {count:0, price:20000, nextPrice:30000, base:20000, mul:1.5}
                         today=9 dim=31 漏签日=[1..8]
POST makeup day=1 → 200  price=20000 nextPrice=30000 progress=1 makeupCount=1
POST makeup day=2 → 200  price=30000 nextPrice=45000 progress=2 makeupCount=2   ← ×1.5 递增
复读 makeup      = {count:2, price:45000, nextPrice:67500}
POST makeup 今天   → 409 「只能补签已经过去的日子」   ← 边界正确
POST makeup 重复日 → 409 「该日已签到，无需补签」      ← 幂等正确
```

**R-212 消耗**（`localtest/t_r212_cost.py`；先给角色灌修为再抽）
```
角色 = 金丹期 L3；服务端当层修为槽 = floor(1521000 × (1+2×0.24) × K=4) = 9,004,320
GET /adventure/draw → 200  cost = 90043
★ floor(9004320 × 0.01) = 90043  ← 精确到个位吻合（旧口径 5% 应为 450,216）
```

**R-210 心法**（沙盒 Playwright，`localtest/t_r214_xinfa.py`，含**反向对照**）
| 观察点 | 旧 `index-v2943` | 新 `index-v2944` |
|---|---|---|
| 按钮 | `修炼` | **`修炼 +750 经验`** |
| 进度条计算高度 | **6px** | **10px** |
| 百分比标签 | 无 | **`0%`** |
| 说明行 | `点一次消耗 750 灵石 · 本级进度 0/2250` | **`本级进度 0/2250（还差 2250 经验）· 点一次消耗 750 灵石`** |

## 7. 本轮踩到的新坑（重要，已写入 `topics/yl.md`）

1. **★ 门禁「收窄 needle」不能只改一头。** r207 的 `R207-D click cost text` 原 needle 带**首尾引号**，
   而 r214 把该字面量的**起点前移**（`· 点一次消耗 …` 不再以引号开头）⇒ 必须**两头引号都去掉**
   才能在两态都命中。首轮只去尾引号 ⇒ r207 自检 `GATE FAIL count=0`，整条链断在 r207。
2. **★★ `_mk_*` 机械派生脚本必须同改「输入文件」与「输出文件」两处路径。**
   只改 `rename()` 里的替换对、漏改 `mk_deploy()` / `mk_rc()` 的 `io.open(... "deploy_v2842.sh")`
   与写盘名 ⇒ 生成器**读了上一批的脚本**、并**覆盖写回上一批的文件**（危险）。
3. **★★ `NEW_BLOCK` 里的 `chk "$B" '<含中文的 needle>'` 必须写成 `\uXXXX` 转义形态。**
   bundle 内中文一律是转义形态，而 chk 是 `grep -o -F | wc -l`（逐字匹配）⇒ 字面中文 **100% 失配**；
   若该条期望值是 `eq 0`，更会变成**恒真**（断言静默失效）。
   ⇒ 本批在 `_mk_2844.py` 里加了**通用归一**：只对本批 `NEW_BLOCK` 的 `chk "$B"` 首个引号参数做转义
   （★ 只动 `$B`；`$S` 服务端 `.ts` 内中文是**字面**的，**不能**转义 —— 首版一刀切曾误伤 15 条既有断言）。
4. **`BLOCK_END_MARK` 必须指向「输入脚本」的段尾**（本批 = `'客户端版本号 0.9.43'`），
   而 `NEW_BLOCK` 的末行才是**新版本**（0.9.44）—— 两者写反会 `substring not found`。
5. **`NOTE_TEXT()` 里出现裸 `%`（「奇遇消耗 1%」）会撞 `%` 格式化** ⇒ 必须写 `%%`。
6. **`deploy_v28/DEPLOY_LOG_*.md` 的自动模板仍是 0.8.11 时代**（写着 s23/0.8.9），每次新批都会落一份错的；
   本批已整份重写（建议后续把模板本身更新到当前世代）。

## 8. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2944-20261009_121853 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2944-20261009.js --to=index-v2943-20261009.js
cp -a /root/backup/index.ts.pre-v2944-20261009_121853        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2944-20261009_121853 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2944-20261009_121853    /opt/yl/www/CHANGELOG.md
systemctl restart yl-server && systemctl is-active yl-server     # ★ 本批改了服务端，必须重启
# 0.9.43 定版：bundle=374c68e8a7cd9809cb24e4f8992c5a3b  server=2f49c2a7bc1b7348c2732912afe968ff
# 整包：/root/backup/yl_pre_v2944_20261009_121853.tar.gz
```

★ **数据面残留**：本批新增表 `activity_makeup`（补签记录）。回滚到 0.9.43 时**无需删表**
（旧代码不读它，多余表无害）；如需完全还原用 `/root/backup/database_v2944_consistent_20261009_121853.sqlite`。

## 9. 0.9.44 定版指纹（供后续批次做 PREV）

```
PREV_BUNDLE_MD5=374c68e8a7cd9809cb24e4f8992c5a3b      # 0.9.43 index-v2943-20261009.js（更早回滚点）
PREV_LIVE_BUNDLE_MD5=7dec9546b3b9849063338558ee8eadac # 0.9.44 index-v2944-20261009.js（线上在跑）
PREV_SRV_MD5=a40670097c22074d4c5c31a444118057         # **89 环**（= s89.r211.ts）
PREV_CHANGELOG_MD5=eb0725762dff07653b42a0894a376efe
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S20_MD5=7780e099a6cd1ac0de4b502c467ae2c0     # 0.8.9 定版 s20.t16arena.ts（前 20 环不变）
```

## 10. 残留清理

- 远端 `/opt/yl/server/` 保留：`_remote_check_v2844.sh` / `_live_bump_bundle.js` / `_remote_gz_sync.sh`。
- 本机沙盒（idx=9）进程已停；目录 `<LOCAL>/Temp/yl_v28_sandbox/s9` 保留备查。
- ★ 沙盒内为验证 R-212 曾**直接改库**给 `ylt_mid` 灌修为（`player.exp = 99999999`）—— 仅沙盒库，未触碰线上。
