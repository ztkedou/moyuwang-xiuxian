# DEPLOY LOG — 《摸鱼修仙传》 0.9.29

- 部署时间：**2026-10-07 00:37 (GMT+8)**
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2829.sh`（客户端 + 服务端 + CHANGELOG + index.html bump）
- 定点核对：`deploy_v28/remote_check_v2829.sh` → **PASS (0 failures)**（★ 首次跑出 2 条**假 FAIL**，见 §5-1，已修脚本单独重跑）
- 登记指纹：`deploy_v28/EXPECT_0829.env`
- 备份整包：`/root/backup/yl_pre_v2929_20261007_003708.tar.gz`
- 生成器：`_mk_2829.py`（deploy）/ `_mk_rc2829.py`（remote_check）—— 机械重登记，**只做整名替换**（铁律 D）
- ★ **本批 bundle 日期跨天**：`20261006` → **`20261007`**（六处已同步，见 §5-1）

---

## 1. 本批范围：0.9.29（客户端 95 模块 + 41 standalone 脚本；服务端 **79 环**）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-170 二环 | 成就「境界组」奖励重定档 | `srv_patch_r170b.py`（第 79 环） | 仅版本号 | ✔ |

### 用户拍板原文（2026-10-07 00:27）
> 「是灵石的话把最顶级换算成奖励1亿，其他根据等级设置」

### 背景与根因
- 前置确认：`POST /api/achievements/claim` 把 5 个组的 `reward` **一视同仁**地累加成 `stones`，
  走邮件发「奖励灵石 ×N」⇒ **境界组与其他组同为灵石，无特殊待遇**。
- 问题：R-170 一环把成就奖励统一成「**按需求次数正比**」，但**境界组的「需求」是等级数（3~63）**，
  量纲与其他组（分钟 / 场次 / 灵石 / 任务个数）差**两个数量级** ⇒ 整组只有 2,000~42,000、Σ 249,470，
  明显小于其他组（修行 12,215,000 / 战斗 13,492,000 / 任务 24,922,000）⇒ 观感「乘数太少」。

### 改法（**等比数列**）
首档仍 **2,000**（守 R-171「所有成就最低档位 = 2000 灵石」），末档锁定 **100,000,000（1 亿）**，
中间按公比 **r = 50000^(1/9) ≈ 3.3274**（≈「每档 ×3.33」）铺开，四舍五入到 3 位有效数字：

| 档 | 名称 | 需求（总等级） | 旧 | **新** |
|:--:|:--|--:|--:|--:|
| 1 | 初入仙途 | 3（炼气三层） | 2,000 | **2,000** |
| 2 | 筑基功成 | 10（筑基一层） | 6,670 | **6,650** |
| 3 | 金丹初成 | 19（金丹一层） | 12,700 | **22,100** |
| 4 | 元婴出窍 | 28（元婴一层） | 18,700 | **73,700** |
| 5 | 化神通玄 | 37（化神一层） | 24,700 | **245,000** |
| 6 | 合道之始 | 46（合道一层） | 30,700 | **815,000** |
| 7 | 合道七重 | 52（合道七层） | 34,700 | **2,710,000** |
| 8 | 长生之初 | 56（长生境二层） | 37,300 | **9,030,000** |
| 9 | 长生六重 | 60（长生境六层） | 40,000 | **30,000,000** |
| 10 | 长生久视 | 63（长生境九层·圆满） | 42,000 | **100,000,000** ← 用户指定 |
| | **Σ** | | 249,470 | **142,904,450** |

★ **为什么用等比而非「按等级线性」**：
- 「线性 + 首档 2,000」在 60 级跨度上斜率高达 **166.7 万/级** ⇒ 第 2 档就是 **1,167 万**，
  第 1 档 2,000 → 第 2 档 1,167 万，曲线开头直接断裂，观感极差；
- 「按等级等比（reward ∝ 需求）」会让首档 = 1 亿 × 3/63 = **476 万**，**违反 R-171**。
⇒ 等比（每档固定倍率）是唯一同时满足「首档 2,000」+「末档 1 亿」+ 平滑单调 的形态。

★ **只动境界组 10 条 reward**；修行 / 战斗 / 财富 / 任务 四组**一行未动**
（用户 2026-10-07 00:18 明确「财富组先不压」）。
★ **`target` 一行未动** ⇒ **不影响任何玩家已有的进度判定**（已领的不退、未领的门槛不变）。
★ 发放口径未动：`const stones = claimedNow.reduce((a, id) => a + (byId.get(id)?.reward || 0), 0);` 逐字保留。

## 2. 指纹（部署前后）

| 对象 | 0.9.28（部署前） | 0.9.29（部署后，线上实测） |
|---|---|---|
| `www/assets/index-v2928-20261006.js` | `47227cabf8eb5e1fa9bfe78d1de49e75` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2927-20261006.js` | `c3b2c9bab29830de1f831b8d6d012171` | 同左（0.9.27 定版，更早的回滚点） |
| `www/assets/index-v2929-20261007.js` | —（新文件） | **`5d16be3568e02d2cde14c4302e74c7cf`** |
| `server/index.ts` | `3cecbaf388c7ab87a469f7ec2cf4df85` | **`5ea456429a9e60f8f7458781fa63131f`**（1,008,329 B / 79 环） |
| `www/CHANGELOG.md` | `41fa2b76f36ddad6ed19dafdb9dbb6a0` | **`149551a10dc7b3db5ce044ee185d6712`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批未变） |

## 3. 部署前本地验收

| 环节 | 命令 | 结果 |
|---|---|---|
| 服务端链 + 前端装配 | `localtest/chain_build.py --all` | rc=0；**79 环**；链尾 `node --experimental-strip-types --check` rc=0 |
| 客户端预演 | `localtest/dryrun_087.py` | 门禁 **PASS（FAIL=0）**；「预演==交付」md5 `5d16be35…` 一致 |
| 远端断言本地预演 | `localtest/sim_remote_check.py --script deploy_v28/remote_check_v2829.sh` | **OK=529 / SKIP=15 / FAIL=0** |
| 部署件指纹一致性 | `deploy_v2829.sh` vs `EXPECT_0829.env` 的 6 个 `PREV_*` | 6/6 逐字一致 |

## 4. 线上验收

| 项 | 结果 |
|---|---|
| `REMOTE-CHECK`（修脚本后重跑） | **PASS (0 failures)** |
| 服务端 index.ts | `5ea456429a9e60f8f7458781fa63131f`（1,008,329 B，79 环） |
| CHANGELOG.md | `149551a10dc7b3db5ce044ee185d6712` |
| 游戏内版本号 | `YLVERSION_FALLBACK = "0.9.29"` |
| 服务 | `yl-server` **active**，`NRestarts=0` |
| ★ 境界组末档（线上实测） | `id: 'realm_63' … target: 63, reward: 100000000` ✓ |
| ★ 财富组未动（线上实测） | `id: 'wealth_5e8' … target: 500000000, reward: 100000000` ✓ |
| ★ gzip 同包（R-159 防线） | `zcat /opt/yl/www/index.html.gz` 命中 `assets/index-v2929-20261007.js` ×1 |
| ★ 公网带 `Accept-Encoding: gzip` 冒烟 | http=200，gunzip 后命中 v2929 ×1 |
| 新包可访问 | `GET /myxxz/assets/index-v2929-20261007.js` → 200 |
| CHANGELOG 公网 | `GET /myxxz/CHANGELOG.md` → 200，顶部为 `## [0.9.29] - 2026-10-07 00:37` |

## 5. 本轮踩到的新坑（★ 务必保留）

1. ★★ **跨天换名 ⇒ 核对脚本里的 `BUNDLE_DATE` 默认值也必须同步（本轮真踩到，出 2 条假 FAIL）**：
   `remote_check_*.sh` 用 `BUNDLE_DATE="${YL_BUNDLE_DATE:-<默认>}"` 拼出待核对的 bundle 名；
   本批 bundle 日期由 `20261006` → `20261007`，而 `_mk_rc2829.py` 起初**只改了 deploy 脚本的默认值**，
   没改 remote_check 的 ⇒ 脚本去找 `index-v2929-20261006.js` ⇒ **MISSING ⇒ 2 条假 FAIL**，
   `deploy_v2829.sh` 因此在末尾报 `REMOTE-CHECK: FAIL (2 failures)`。
   - **实际状态**：部署**从头就是成功的**（线上已切 v2929、server `5ea45642…`、CHANGELOG `149551a1…` 全部正确）。
   - **处置（按纪律，未回滚）**：修 `_mk_rc2829.py` 补上默认值替换 → 重新生成 → `scp` 单传
     `/opt/yl/server/_remote_check_v2829.sh` → 重跑 ⇒ **PASS (0 failures)**。
   - ★ **规矩**：**bundle 日期一改，六处必须全同步** —— `build_v26n.OUT` / `chain_build.CLIENT_OUT` /
     `dryrun.BUNDLE_BASENAME` / `build/index.html` / `deploy.BUNDLE_DATE` / **`remote_check.BUNDLE_DATE`**。
     （最后这一处是本轮漏的，且它是**默认值**、不在包名整名替换的覆盖范围内 ⇒ 必须单独点名替换。）
2. ★ **空替换会被补丁契约拒绝**：境界组第 1 档（target=3）本来就是 2000，新旧相同
   ⇒ 必须**不列进 `EDITS`**，改用 `gates()` 断言把守。
3. ★ **裸值 needle 会被跨组撞车**：remote_check 原有一条 `'reward: 100000000 }' eq 1`
   （当时只有财富组末档是 1 亿）；本批境界组末档也是 1 亿 ⇒ 计数变 2 ⇒ 已改成带 target 的精确 needle
   `'target: 500000000, reward: 100000000 }'`。
4. ★ **`require(` 不能进 `BASE_NEEDLES`**：它在 ESM 基座里本来就是 0，而 `BASE_NEEDLES` 有
   「基座计数必须 > 0」的自检 ⇒ 要单独写成 `("…", 0, "==", …)`。

## 6. 残留清理

远端 `_remote_check_v2829.sh` / `_live_bump_bundle.js` / `_remote_gz_sync.sh` 留在 `/opt/yl/server/` 便于复跑（惯例）。
本地：`_chainstage/` 各环产物保留；补丁自测产生的临时副本与 `.bak-*` 已全部删除。

## 7. 回滚（本轮动了新包 + index.html + CHANGELOG + index.ts，需重启）

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2929-20261007_003708 /opt/yl/www/index.html   # 或 live_bump 回 index-v2928-20261006.js
cp -a /root/backup/index.ts.pre-v2929-20261007_003708        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2929-20261007_003708 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2929-20261007_003708    /opt/yl/www/CHANGELOG.md
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版（0.9.28）：bundle=47227cabf8eb5e1fa9bfe78d1de49e75  server=3cecbaf388c7ab87a469f7ec2cf4df85
# 整包：/root/backup/yl_pre_v2929_20261007_003708.tar.gz
```

★ 回滚注意：本批**无 DDL**（无新表/新列）⇒ 回滚无需任何库操作。

## 8. 0.9.29 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=5d16be3568e02d2cde14c4302e74c7cf        # 0.9.29 定版 index-v2929-20261007.js
PREV_SRV_MD5=5ea456429a9e60f8f7458781fa63131f           # 0.9.29 定版 srv/index_v28.ts（= s79.r170b.ts，79 环）
PREV_CHANGELOG_MD5=149551a10dc7b3db5ce044ee185d6712     # 0.9.29 定版 CHANGELOG.md
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S79_MD5=5ea456429a9e60f8f7458781fa63131f       # 链尾 s79.r170b.ts（供 0.9.29 单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。

## 9. 本批遗留（待用户）
- **R-170 财富组**：仍是严格正比版（末档 1 亿，Σ 190,422,000）—— 用户 00:18 明确「先不压」。
- **R-176 的服务端环（奇遇抽品阶）**：仍**未接线**（越界）⇒ 待用户确认要不要做。
- **R-175 历史逐只伤害回填**：如需要，另立数据迁移项。
