# DEPLOY LOG — 《摸鱼修仙传》 0.9.45

- 部署时间：**2026-10-09 16:03 (GMT+8)**
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2845.sh`（客户端 + **服务端（90 环）** + CHANGELOG + index.html bump）
- 定点核对：`deploy_v28/remote_check_v2845.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0845.env`
- 备份整包：`/root/backup/yl_pre_v2945_20261009_160251.tar.gz`
- DB 一致性快照：`/root/backup/database_v2945_consistent_20261009_160251.sqlite`
- 本批类型：**混合批**（服务端 89 → **90 环**）⇒ **未加 `--skip-server`**，服务于 `16:03:22 CST` 重启

## 1. 定版指纹

| 产物 | md5 | 字节 |
|---|---|---|
| `build/assets/index-v2945-20261009.js` | `e5a451fe35fb7d0ad4422bdd8ddcac9b` | 2,321,665 |
| `srv/index_v28.ts`（= 链尾 `s90.r215.ts`） | `f0f6b69d578854660e0ae32191b233bf` | 1,025,161 |
| `CHANGELOG.md`（顶部 `[0.9.45]`） | `97eaf6fc68941c6bb9ef524e8361469a` | — |
| `game-dicts.json`（未变） | `1b635513f553875060869272b790f910` | — |

公网实测（独立复核，非部署脚本自述）：bundle md5 **逐位一致**；`index.html` → `assets/index-v2945-20261009.js`；
`CHANGELOG.md` 头部 = `## [0.9.45] - 2026-10-09 15:51`；远端 `index.ts` = `f0f6b69d…`；`systemctl is-active` = active。

## 2. 本批内容（2 条）

- **R-213 全站文案过时修正 6 处**（客户端 `yl_r216_ext.py`）：交易行手续费 10%→0、奇遇规则行 5%→1%、
  灵田 T5 照料频率、天地之髓投喂区间、缘契任务 10→5 条、丹炉仙品 9 层。**只改文字，玩法数值未动**。
- **R-215 整体升级经验 ÷2**（服务端第 90 环 `srv_patch_r215.py` + 客户端 `yl_r217_ext.py`）：
  7 档 `maxExpBase` 全部减半（`60000→30000` … `452500000→226250000`）；只改该字段。

## 3. 版本号六处同步

`build_v26n.OUT` / `chain_build.CLIENT_OUT` / `dryrun_087.BUNDLE_BASENAME` / `dryrun_087.VERSION` /
`yl_version_ext.DEFAULT_VERSION`(+fallback) / `build/index.html` —— 全部 `0.9.45` / `index-v2945-20261009.js`。

## 4. ★ 门禁退役记录（版本铁律：不得静默删断言）

预演首轮报 **16 条 FAIL**，全部是**本批改动合法打破的既有冻结门禁**（跨模块门禁耦合）。按本仓
`RETIRED_TAG = '【已退役·终态专用】'` 机制处理（**apply 态自检跳过、终态仍检新值**），**未删任何断言**：

| 模块 | 门禁 | 旧期望 | 新期望 | 原因 |
|---|---|---|---|---|
| `yl_r183_ext.py` | `冻结 maxExpBase:{60000,390000,1521000,6592000,26775e3,104430e3,45250e4}`（7 条） | 各 `== 1`（旧值） | 各 `== 1`（**新值**） | R-215 已合法把 Cs 七档基数减半。★ apply 态仍按 FREEZE **原值**校验（`_precheck` 未动）⇒「R-183 当年没动基数」这一历史事实**原样保留** |
| `yl_r189b_ext.py` | `R189b·全 bundle 10% 计数` | `== 29` | `== 28` | R-216 把天地之髓投喂「+6-10%」改成「+6-9%」⇒ 全 bundle `10%` 少 1 处；本环新增的 4 处仍由 ①~④ 逐条钉死 |

退役原因已写进各门禁 label 的 note，可回溯。

## 5. 部署件注释修正（本批发现并修掉）

`deploy_v2845.sh` / `remote_check_v2845.sh` 里继承自模板的注释与本批实况矛盾，已全部修正（各命中 1 次）：

1. ★★ **危险项**：用法行原写「本批**必须**加 `--skip-server`（服务端无变化）」——本批服务端**有变化**（90 环）。
   照它做会**漏发服务端**。已改为「**不要加** `--skip-server`（会重启 yl-server）」。
2. `③ 读 EXPECT_0845.env；链尾 = s88.r207.ts（★ 本批无新末环，链尾不变）` → `s90.r215.ts（★ 本批有新末环，链尾已平移）`
3. `★ 本批服务端无 diff（纯客户端批）` → `★ 本批服务端有 diff（89 → 90 环）`
4. `② PREV 指纹取 0.9.44 定版（线上实测 2026-10-07…）` → `2026-10-09`
5. rc 头部 `特征串已本地复核（2026-10-08…）` → `2026-10-09`
6. rc `# 0.9.32 定版 index-v2943-…` → `# 0.9.43 定版`
7. rc `PREV_LIVE_BUNDLE_MD5 … （线上在跑，实测 2026-10-06）` → `2026-10-09`
8. rc `PREV_SRV_MD5` 注释块：`上一版（0.9.41）（= s88.r207.ts）` → `上一版（0.9.44）（= s89.r211.ts）`；
   `本批服务端无变化（仍 88 环）⇒ WARN 会触发且属预期` → `本批服务端有变化（89 → 90 环）⇒ WARN 不应触发`

另：`yl_r217_ext.py` 的幂等标记由 `YLXW_R217_V2944` 更正为 **`YLXW_R217_V2945`**（标记名应按所在产物版本，先例 `YLXW_R214_V2944`）。

## 6. 验证链（六层）

| 层 | 手段 | 结果 |
|---|---|---|
| 1 门禁 | `yl_r216_ext.py` 33 条 / `yl_r217_ext.py` / `srv_patch_r215.py` 35 条 | 全绿 |
| 2 语法 | `node --check`（含服务端 strip-types） | PASS |
| 3 交叉核对 | 两份 `maxExpBase` 表并排 + 炼气 1~9 层推演 | 7/7 一致、逐层 `floor(改前/2)` 精确成立 |
| 4 装配预演 | `dryrun_087.py` | FAIL 0 / SA-FAIL 0；**预演产物 md5 == 交付产物 md5**（`e5a451fe…`） |
| 5 线上定点 | `remote_check_v2845.sh` | **REMOTE-CHECK: PASS (0 failures)** |
| 6 公网独立复核 | curl（不依赖部署脚本结论） | bundle md5 逐位一致 / index.html 指向 v2945 / CHANGELOG 头正确 |

## 7. 回滚

```
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2945-20261009_160251 /opt/yl/www/index.html
cp -a /root/backup/index.ts.pre-v2945-20261009_160251        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2945-20261009_160251 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2945-20261009_160251    /opt/yl/www/CHANGELOG.md
systemctl restart yl-server && systemctl is-active yl-server
```
- 0.9.44 定版：bundle `7dec9546b3b9849063338558ee8eadac` / server `a40670097c22074d4c5c31a444118057`（89 环）
- 整包：`/root/backup/yl_pre_v2945_20261009_160251.tar.gz`

## 8. 遗留 / 待办

- **R-213 与 R-215 已随本批上线**；台账待归档。
- ★ 本批**未动** `ARENA_TRIAL_REALMS`（`srv:11931`）的同值 `maxExpBase` —— 它喂的是**演武场试炼首通奖励**
  （`arenaTrialClearExp = floor(5% × 该槽)`，`srv:11998`），属**产出侧**、非「升级所需经验」⇒ 按裁决不动（patch 内 7 条冻结门禁锁死）。
- ★ 新发现（**未处理**，供后续核查）：天地之髓的**剧情文案**写「**晋升化神**所需之髓」，但突破判定是
  `r === "化神期"`、掉落条件为 `境界序 >= 化神期` ⇒ 实现上它是**离开化神期**的材料。文案与实现疑似不一致，
  建议另立一条按 R-213 口径核查（**新发现，不在本批范围**）。
