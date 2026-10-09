# DEPLOY LOG — 《摸鱼修仙传》 0.9.51

- 部署时间：2026-10-10 00:48 (GMT+8)
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2851.sh`（客户端 + 服务端 + CHANGELOG + index.html bump）
- 本批类型：**服务端有变**（91 → 92 环，新末环 `s92.r225b.ts`）⇒ **有停机**（秒级，`NRestarts=0`）
- 定点核对：`deploy_v28/remote_check_v2851.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0851.env`
- 备份整包：`/root/backup/yl_pre_v2951_20261010_004724.tar.gz`
- DB 一致性快照：`/root/backup/database_v2951_consistent_20261010_004724.sqlite`（sqlite3 CLI `VACUUM INTO`：ok）

---

## 1. 本批范围（0.9.51；客户端 134 模块 + 服务端 92 环）

> 规模口径：`CLIENT_MODULES` / `SRV_RINGS` 由部署脚本运行环境填充（未设时显示 `<待填>`）；
> 取值见本批 `localtest/dryrun_*.py`（客户端模块数）与 `localtest/chain_build.py`（服务端环数）输出。

· R-225b 离线收益的难度加成改由服务端记录（**服务端第 92 环** `srv_patch_r225b.py`；客户端**零功能改动**）

### 起因与改法（R-225b）

- 起因：0.9.50 的 R-225 让离线收益吃难度倍率，但倍率取自客户端 `localStorage` 镜像
  ⇒ 玩家可改本地存储白拿 ×2（`hard`）加成。
- 改法：`saves` 表**新增 `difficulty` 列**；**首次存档记录**、之后**忽略客户端改动**；
  倍率**只读服务端该列**；老档（`NULL`）首次按客户端值落一次（不判作弊）。
- 幂等标记：`[r225b]`；改写 `ylR225DiffMul` / `ylR225OfflineMults` 取值口径（改读冻结难度 `frozenDiff`），
  新增 `ylR225bClientDiff` / `ylR225bFrozen` / `ylR225bFreezeRow`；`settleSaveEconV2` 签名加 `frozenDiff?`；
  4 处调用点（`/api/save` 计算 + `UPDATE` 首次落库 + `INSERT` 首存即冻结 + report/claim 预览与入档）改读冻结值。
- 客户端：**零功能改动**（本批纯服务端 + 部署件）；`V28_MODULES` = 134 模块（未增减）。

## 2. 指纹（部署前后）

| 对象 | 上一版（部署前） | 本批（部署后） |
|---|---|---|
| `www/assets/index-v2950-20261009.js` | `f18d9cb8440657e1aa51de1a95c89c9c` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2949-20261009.js` | `d8fac7c23951a88c739579726823fb2c` | 同左（0.9.49 定版，更早的回滚点） |
| `www/assets/index-v2951-20261009.js` | —（新文件） | `48e7555ea90e0075fb5bc6c9a67904e0` |
| `server/index.ts` | `ac5c521d726fa74193d96071d63f702d` | `f1a06d4412f9b18c42192838dba47416` |
| `www/CHANGELOG.md` | `38b7b622882efadb7c6533f4e098c2d2` | `5fdaf5e5c5028b959be546e8443d481f` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | `1b635513f553875060869272b790f910`（本批不变） |

部署后线上实测（deploy_v2851.sh 采集）：

```
f1a06d4412f9b18c42192838dba47416  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
5fdaf5e5c5028b959be546e8443d481f  /opt/yl/www/CHANGELOG.md
48e7555ea90e0075fb5bc6c9a67904e0  /opt/yl/www/assets/index-v2951-20261009.js
```

## 3. 部署前本地验收

`deploy_v2851.sh` step 0 / 0c 实测（全部通过）：

- `bash -n deploy_v2851.sh` / `bash -n remote_check_v2851.sh` 均 OK（生成器 `selfcheck()` 内）。
- `python _mk_2851.py` **幂等复跑**：三产物 md5 逐字节稳定 ——
  `deploy_v2851.sh` = `28625fc335aabfacc2c6dbf102de4109`、
  `remote_check_v2851.sh` = `f669b9c9d86edc97270b3bb590f5b967`、
  `EXPECT_0851.env` = `e111b82b8b3a6eba9740e1031d9c2419`。
- `python localtest/sim_remote_check.py --script deploy_v28/remote_check_v2851.sh --bundle build/assets/index-v2951-20261009.js`
  （★ 显式传 `--bundle`）：**FAIL=0**（OK=806 / SKIP=15）。
- `EXPECT_0851.env`：**纯 LF / 无 BOM / 以换行结尾**（5,472 B）。
- `deploy_v2851.sh --dry-run` 预检通过：step 0 / 0c 全绿，`CHANGELOG [0.9.51] gate: OK`。
- CHANGELOG_PLAYER 格式校验通过、每个版本都有 `### 分类`。
- `EXPECT_0851.env` 四项 md5 全符：bundle `48e7555ea90e0075fb5bc6c9a67904e0`（2,327,686 B）、
  srv `f1a06d4412f9b18c42192838dba47416`（1,031,922 B）、dicts `1b635513f553875060869272b790f910`、
  CHANGELOG `5fdaf5e5c5028b959be546e8443d481f`。
- canon `_chainstage/index_v28.v28112.ts` == `srv/index_v28.ts` == `EXPECT_SRV_CANON_MD5`；
  前端基座 `index-v26m-20260927.js` == `b315eb1a04e967a66c128861b3a3dadd`。
- step 0c 双 provenance：预演 `_chainstage/dryrun_087.bundle.js` == 交付 bundle；链尾 `s92.r225b.ts` == `srv/index_v28.ts`；
  `s20.t16arena.ts` == `7780e099a6cd1ac0de4b502c467ae2c0`（前 20 环 == 0.8.9 定版，单变量可核成立）。
- 远端未漂移断言：`index.ts` == `ac5c521d…`（0.9.50）、`index-v2950-20261009.js` == `f18d9cb8…`、
  `index-v2949-20261009.js` == `d8fac7c2…` 三项全符。

## 4. 线上验收

- `remote_check_v2851.sh`（scp 后远端执行 + 部署脚本内嵌各一次）：**PASS (0 failures)**。
- 公网冒烟：`/myxxz/` = 200；`index.html`（明文 + gzip 双路）→ `assets/index-v2951-20261009.js`；
  公网 bundle md5 `48e7555ea90e0075fb5bc6c9a67904e0`（2,327,686 B）逐位一致；`/myxxz/api/save` 无 token = 401。
- 本批特征（公网 bundle，`grep -o -F | wc -l`）：`0.9.51` ×1；0.9.50 及更早客户端特征（`YLXW_R227_DEADDATA` ×3、
  `YLXW_R228_V2949` ×1、R230 新串）仍在。
- 服务端特征（`grep -o -F | wc -l`）：`[r225b]` ×13、`ADD COLUMN difficulty TEXT` ×1、
  `difficulty = COALESCE(difficulty, ?)` ×1、`econ_win_stone, difficulty FROM saves` ×1、
  `last_active_at, difficulty FROM saves` ×2、`ylR225bFreezeRow(` ×3；
  `[r225diff]` ×9（13 → 9，4 处改 `[r225b]`）、`saveData.settings.difficulty` ×0（已清零）。
- `index.ts` 线上实测 `f1a06d4412f9b18c42192838dba47416`；`systemctl is-active yl-server` = active，`NRestarts=0`。
- ★ **数据库变更**：**本批有数据库变更**（0.9.50 之后首次）——
  `saves` 表**新增 `difficulty TEXT` 列**（幂等加列：`ADD COLUMN difficulty TEXT`，快路径 `r.name === 'difficulty'` 判存在）；
  首次落库 `UPDATE saves SET difficulty = ? WHERE user_id = ? AND difficulty IS NULL`；
  新建档 `INSERT`（`econ_win_stone, difficulty) VALUES`）首存即冻结。**无建表、无删列**。
  回滚时无需删列（旧代码不读多余列）。

## 5. 本轮踩到的新坑

- 任务书描述 §1 占位为 `/* <待补> */`（6 处），实际 `deploy_v2851.sh` 的 §1 用的是 markdown 表格
  `| <待补> | <待补> | <待补> | <待补> | <待补> |`（5 格）+ 1 行 `<待补：…>` 说明；模板头部亦无「本批类型」行。
  ⇒ 已按任务书**意图**回填：§1 换成本批范围（逐字），头部补一行「本批类型」。
- 生成器 rc 新针初稿把「R225b claim 调用点读冻结值」写成 `eq 2`，但该 needle
  `ylR225bFreezeRow(userId, row, row.save_data)` **同时命中函数定义行**（`function ylR225bFreezeRow(userId: number, …)` 前缀相同）
  ⇒ 实际只需 `eq 1`。已由 `sim_remote_check.py` 预演捕获（L1078 FAIL=1）并修正，重跑预演 **FAIL=0**。
- 历史陈旧注释（**本批未引入、未修，如实登记**）：`deploy_v2851.sh` 内 `# 单变量可核：本批服务端**无 diff**（纯客户端批）`
  自 0.9.44 起即与事实不符（服务端自 0.9.44 起持续有环增量），本批沿用原文未改，避免扩大改动面。

## 6. 残留清理

- 远端 `/opt/yl/server/` 保留 `_remote_check_v2851.sh` / `_remote_swap.sh` / `_live_bump_bundle.js`（便于复跑，惯例）。
- 本批未做写库测试，无测试账号 / DB 残留（`difficulty` 列由正常存档路径填充，未注入测试数据）。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2951-20261010_004724 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2951-20261009.js --to=index-v2950-20261009.js
cp -a /root/backup/index.ts.pre-v2951-20261010_004724        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2951-20261010_004724 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2951-20261010_004724    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2950-20261009.js.pre-v2951-20261010_004724 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版：bundle=f18d9cb8440657e1aa51de1a95c89c9c  server=ac5c521d726fa74193d96071d63f702d
# 整包：/root/backup/yl_pre_v2951_20261010_004724.tar.gz
```

★ 回滚注意：数据库变更（若有）见 §4。回滚到上一版时**无需删列 / 删表**
（旧代码不读多余列，多余列无害）；**如需完全还原**用
`/root/backup/database_v2951_consistent_20261010_004724.sqlite` 热拷贝。

## 8. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=48e7555ea90e0075fb5bc6c9a67904e0
PREV_SRV_MD5=f1a06d4412f9b18c42192838dba47416
PREV_CHANGELOG_MD5=5fdaf5e5c5028b959be546e8443d481f
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=f1a06d4412f9b18c42192838dba47416   # 链尾 _chainstage/s92.r225b.ts（供单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
~/.ai-memory/topics/项目-摸鱼修仙传.md「当前版本」段。
