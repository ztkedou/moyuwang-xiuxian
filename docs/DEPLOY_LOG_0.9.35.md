# DEPLOY LOG — 《摸鱼修仙传》 0.9.35（v28 链 **第 85 环**）

- **部署时间**：2026-10-08 10:51:43 ~ 10:52:45（GMT+8）｜**服务重启时刻 `ActiveEnterTimestamp = 10:52:13`**
- **目标**：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- **脚本**：`deploy_v28/deploy_v2835.sh`（客户端 + **服务端第 85 环** + 双 CHANGELOG + index.html bump + gz 同步）
- **定点核对**：`deploy_v28/remote_check_v2835.sh` → **PASS (0 failures)**，**无 WARN**
- **登记指纹**：`deploy_v28/EXPECT_0835.env`
- **备份整包**：`/root/backup/yl_pre_v2935_20261008_105143.tar.gz`
- ★★ **本批服务端有变** ⇒ **重启了 yl-server**（`NRestarts = 0`，`ActiveState = active`）。

## 1. 本批范围：0.9.35 = **6 条**（客户端 3 补丁 + 服务端 1 环）

| # | 任务 | 落点 |
|---|---|---|
| **R-197**（R-189②） | 妖灵 UI 重排：折算块（改名「妖灵折算灵宠属性（参考）」）下移到**妖灵卡片正下方**；「融合玩法」整块搬进**灵宠弹窗右栏**（「我的灵宠 (N)」正上方） | `localtest/yl_r197_ext.py` |
| **R-198**（R-189③） | 培养区新增**「免费玩法」栏**：免费进食（+100 喂食度 / 每日 3 次 / 冷却 30 分钟）+ 免费互动三按钮（逗弄 / 梳毛 / 夜话） | `yl_r198_ext.py` + `patches/server/srv_patch_r198.py`（**第 85 环**） |
| **R-198**（R-189④） | **买额度 2 → 5**（3 个选项共用 5 次）；**玩法说明②** 过时文案同步改写 | 同上 |
| **R-199** | **自动历练提速**：3 处收尾冷却 `d(9)` → `d(7)`（每轮快 2 秒） | `localtest/yl_r199_ext.py` |
| — | 回归：0.9.34 的奇遇率(称号承载) / 悟道十道随机 / 妖灵归位 / 灵纹重设 / 主人加成 10% **全部保持** | `remote_check_v2835.sh` 回归段 |

- 客户端 `STANDALONE_CLIENT` **46 → 49 脚本**（新增 3：`r197` / `r198` / `r199`）
- 服务端 `SRV_CHAIN` **84 → 85 环**（`s85.r198`）
- ★ **冲突处理**：`r199` 改的 `d(9)` 与 `r177` / `r183` 的冻结针脚正面冲突
  ⇒ 由 `pinfix4` 用 **`RETIRED_TAG`（【已退役·终态专用】）** 退役 5 条旧针
  （`r120` 说明② 前缀 / `r167` `/pet/feed` / `r177` 3× `d(9)` / `r183` 1× `d(9)`），
  **apply 态跳过、终态仍检**，产品字节零变化。

## 2. 指纹（部署前后）

| 对象 | 部署前（0.9.34） | 部署后（0.9.35） |
|---|---|---|
| `www/assets/index-v2934-20261008.js` | `550efc63d2289efa2795b1dc1bbda115` | 同左（**旧包保留不删 = 秒级回滚点**） |
| `www/assets/index-v2933-20261008.js` | `babae2e2b0cb92f07e0278c5840b1766` | 同左（更早回滚点） |
| `www/assets/index-v2935-20261008.js` | —（新文件） | **`af2883a4a7fa489b9b5c3851d1c85948`**（2,315,892 B） |
| `server/index.ts` | `4cd3632ceebee7a50c6943d89da4c23d`（84 环） | **`8318e1c9fad3242364df7b3a585ca61f`**（1,016,800 B / **85 环**） |
| `www/CHANGELOG.md` | `565b030cf7fe98c6383a6f91478aa544` | **`33231247d8dd8608d0decaaf61a5d8dd`** |
| `www/CHANGELOG_PLAYER.md` | `fa83e3539be679bd46b6306494dc4be4` | **`81180d88e261207617b1ebeb93a0100c`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（未变）** |

## 3. 部署前本地验收

- `chain_build --all`：**rc=0**（bundle `af2883a4…`；服务端 `8318e1c9…` / 85 环；`node --check` rc=0）
- `dryrun_087.py`：**PASS（FAIL=0）**，**894 条 standalone 门禁**（本批**零冲突**）
- 「预演==交付」：`_chainstage/dryrun_087.bundle.js` md5 == 交付 bundle md5 ✓
- `remote_check_v2835.sh` 本地预演（`sim_remote_check.py`）：**OK=567 / SKIP=15 / FAIL=0**
- `bash -n` 两个脚本：语法 OK
- ★ **远端基线预检**：部署前线上 4 个 PREV_* 指纹**逐字节命中**
  （bundle `550efc63…` / 更早回滚点 `babae2e2…` / server `4cd3632c…` / CHANGELOG `565b030c…`），
  `index.html` 指向 `index-v2934-20261008.js`。

## 4. 线上验收

- `remote_check_v2835.sh` → **REMOTE-CHECK: PASS (0 failures)**，**无 WARN**（服务端有变 ⇒「没换？」WARN 不触发）
- 线上实测指纹：bundle `af2883a4…`（2,315,892 B）｜server `8318e1c9…`（1,016,800 B）｜
  CHANGELOG `33231247…`｜CHANGELOG_PLAYER `81180d88…`
- `index.html` 指向 **`index-v2935-20261008.js`**（旧引用已清零）
- ★★ **gzip 硬断言**：`zcat index.html.gz | grep 新包 = 1` ✓
- `yl-server`：`active` / `NRestarts = 0` / **`ActiveEnterTimestamp = 2026-10-08 10:52:13 CST`（已重启）**
- 双 CHANGELOG 已回填**实际上线时刻 10:52** 并重传；`EXPECT_0835.env` 的 `EXPECT_CHANGELOG_MD5` 已重登记
  （CHANGELOG 无 `.gz` 伴生文件 ⇒ 无需重建 gz）

## 5. 本轮踩到的新坑

1. ★★ **`_mk_2834.py` 的「整文件盲链式版本号替换」在历史段落上是错的** ——
   它把 rc 里「0.9.14 特征点…」一路顶成「0.9.34 特征点…」、把「与 0.9.31 同 md5」顶成「与 0.9.33 同 md5」，
   历史注解全部失真且**每升一版再坏一次**。
   ⇒ `_mk_2835.py` 改为**只在「版本槽位行」上链式升版**
   （`YLVERSION_FALLBACK = "0.9.x"` / `'## [0.9.x] - '` / `chk "$B" '0.9.x'`），历史注解**逐字不动**；
   另加一张「当前 / 上一版署名」显式顶替表。
2. ★ **生成器自身造出 `_chainstage/_chainstage/s85.r198.ts` 双前缀** ——
   调用点原文是 `_chainstage/s84.r194.ts`，而替换串写成**全路径** ⇒ 前缀翻倍。
   若没被残留扫描抓到，**step 0c 单变量可核会直接 ABORT**。
   ⇒ 常量改成只写文件名，并加一条 `_chainstage/_chainstage/` 兜底断言。
3. ★ **`sim_remote_check` 抓到 ③ 类冲突 1 条**：R-198 在 `GET /api/pet` 的 `feedQuota` 旁**加了一条注释**，
   注释里也含 `feedQuota` 一词 ⇒ R-167 当年钉的**裸词**针 `'feedQuota' == 1` 在 85 环产物上变成 **2**（**合法变化**）。
   ⇒ **不删断言、不放松预期**，把针**收紧**为 `feedQuota: {`（仍恰 1 处，语义等价且不再被注释干扰）。
4. ★ **`dryrun_087.py` 的「失败明细打印」是死代码级缺陷**（本批顺手修掉）：
   `fails` 里**两种元组混用**（5 元组来自接线 / EV / 门禁 / T7 / 套用失败；6 元组仅 standalone 门禁一处），
   而打印循环写死 `for name, s, expect, cmp, note, actual in fails`
   ⇒ **只要有任何 5 元组失败就抛 `ValueError`**，**失败明细在最需要它的时刻反而打不出来**（只剩 traceback）。
   ⇒ 改为按长度分派；并**注入一条 5 元组 + 一条 6 元组假失败**跑通自证（两行明细均完整打印、rc=1、无 traceback）。
5. **CHANGELOG 条目头时刻必须先占位、上线后回填**：部署脚本 step 0 会 fail-closed 校验
   `EXPECT_CHANGELOG_MD5` ⇒ 改完文案必须**重登记 EXPECT**，否则下一轮 step 0 会 ABORT。
6. ★★ **GitHub 远端一直明文留着沙盒口令**（本批一并清掉）：
   - **5 个文件**（`_v281_base/index_v28.base.ts` / `patches/server/srv_patch_baseclean089.py` /
     `docs/GITHUB-PUBLISH-INSTRUCTIONS.md` / `docs/SECRETS-SCAN.md` / `localtest/README_SANDBOX.md`）
     的脱敏改动只落在**本地 staging**（privacy 提交 `60206e2` / `31f8757` / `53349cd`），**从未推到远端**
     ⇒ 远端 main 一直含 `|| 'gamer'`。已用 `_gh_push_privacy5.py` 补推（commit `fe592bad301c`）。
   - 全树复查又抓到**最后 1 处**：`CHANGELOG.md` 历史条目里的 `gamer520` 字面量
     （`_chainstage/` 中间态虽含 `|| 'gamer'`，但被 `_gh_sync` 白名单排除、不进 GitHub）。
     ⇒ 已占位符化为 `<WEAK_PASSWORD>`，重传线上并**第二次**重登记 `EXPECT_CHANGELOG_MD5`
     （`859e8199…` → **`33231247d8dd8608d0decaaf61a5d8dd`**）。
   ★ **根因教训**：`_gh_push*.py` 只推 `git diff HEAD~1 HEAD` ⇒ **历史上漏推的提交永远补不上**；
     「本地 tree == 远端 tree」这条自检是**唯一**能抓到它的手段 —— 本轮就是靠它发现的（`tree 一致：否 ✗`）。

## 6. 待用户拍板（本批**未做**）

- **服务端渡劫判定与客户端修为曲线不同源**：`TRIB_REALM_BASES` 的 7 个境界值**没有乘 R-183 的 K**
  （`K = [14,6,4,2.5,1.5,1,1]`）⇒ 服务端 `expOk` 判定的门槛与客户端实际需求（炼气 3 层 = 1,243,200）**不一致**。
  **本批未立项**（不阻塞上线）；是否补一条服务端环把两边对齐，待拍板。
- **融合块「灵兽秘径 · 单次」数值基准已变**：搬进灵宠弹窗后拿不到妖灵数据 ⇒ 基准由**妖灵**改为**当前出战灵宠**，
  行内文案与算式一字未改，**但 N/M/K 数值会与搬移前不同**（已在双 CHANGELOG 标注）。
- **两套免费喂食机制并存**：R-167「当日首次免费」（else 分支逐字保留）与本批「免费进食 3 次/日」**独立共存**
  ⇒ 当前每日免费喂食度 = 300（3×100）+ 1 档付费档位。
- **奇遇率 4% 的触发条件**：现为「**按称号档位递增**」（默认 1%，顶配称号才 4%）；
  若想「任意称号即 4%」，改一个常数即可。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2935-20261008_105143    /opt/yl/www/index.html
cp -a /root/backup/index.ts.pre-v2935-20261008_105143      /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2935-20261008_105143 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2935-20261008_105143  /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2935-20261008_105143 /opt/yl/www/CHANGELOG_PLAYER.md
# ★ index.html.gz 必须与明文同批重建（nginx gzip_static 铁律 R-159）
gzip -9 -kf -c /opt/yl/www/index.html > /opt/yl/www/index.html.gz
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版（0.9.34）：bundle=550efc63d2289efa2795b1dc1bbda115  server=4cd3632ceebee7a50c6943d89da4c23d
# 整包：/root/backup/yl_pre_v2935_20261008_105143.tar.gz
```

★ **本批 DDL 为「幂等加列」**（`pet_feed_log` 加 `free_times` / `last_free_at`，走 `safeAddColumn`）
⇒ 回滚**无需动库**：多出的两列对 0.9.34 代码**无害**（旧代码不读它们），无需 DROP。

## 8. 0.9.35 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=babae2e2b0cb92f07e0278c5840b1766      # 0.9.33 index-v2933-20261008.js（更早回滚点）
PREV_LIVE_BUNDLE_MD5=550efc63d2289efa2795b1dc1bbda115 # 0.9.34 index-v2934-20261008.js（本次部署前的线上包）
PREV_SRV_MD5=4cd3632ceebee7a50c6943d89da4c23d         # 0.9.34 srv/index_v28.ts（84 环 = s84.r194.ts）
PREV_CHANGELOG_MD5=565b030cf7fe98c6383a6f91478aa544   # 0.9.34 CHANGELOG.md
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S20_MD5=7780e099a6cd1ac0de4b502c467ae2c0     # 0.8.9 定版 s20.t16arena.ts（前 20 环不变）
# 本版（0.9.35）新指纹：
#   bundle   af2883a4a7fa489b9b5c3851d1c85948  (2,315,892 B)  index-v2935-20261008.js
#   server   8318e1c9fad3242364df7b3a585ca61f  (1,016,800 B / 85 环 = s85.r198.ts)
#   CHANGELOG.md        33231247d8dd8608d0decaaf61a5d8dd
#   CHANGELOG_PLAYER.md 81180d88e261207617b1ebeb93a0100c
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
