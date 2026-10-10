# DEPLOY LOG — 《摸鱼修仙传》 0.9.52

- 部署时间：2026-10-10 09:51:49（备份时刻）/ 09:52:21（服务重启完成）(GMT+8)
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2852.sh`（客户端 + 服务端 + CHANGELOG + CHANGELOG_PLAYER + index.html bump）
- 本批类型：**混合批** —— **服务端有变**（92 → 93 环，新末环 `s93.r233.ts`）+ **客户端有变**（R-232）
  ⇒ **有停机**（秒级，`NRestarts=0`）
- 定点核对：`deploy_v28/remote_check_v2852.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0852.env`
- 备份整包：`/root/backup/yl_pre_v2952_20261010_095149.tar.gz`（64,703,794 B）
- DB 一致性快照：`/root/backup/database_v2952_consistent_20261010_095149.sqlite`（8,339,456 B，VACUUM INTO 热拷贝）

---

## 1. 本批范围（0.9.52；客户端 134 模块 + 服务端 93 环）

> 规模口径：`CLIENT_MODULES` / `SRV_RINGS` 由部署脚本运行环境填充（未设时显示 `<待填>`）；
> 取值见本批 `localtest/dryrun_*.py`（客户端模块数）与 `localtest/chain_build.py`（服务端环数）输出。

· **R-233**（服务端第 93 环 `srv_patch_r233.py`）：把 `saves.difficulty` **冻结值**经 `GET /api/save`
  **主载荷顶层**下发给客户端（字段 `ylDifficulty`）—— 承接 R-225b，为 R-232 提供**服务端权威难度源**。
· **R-232**（客户端 standalone `localtest/yl_r232_ext.py`）：在线收益难度「**服务端权威值优先**」——
  取值器优先级改为「入参 → 服务端下发值 → store → localStorage 兜底」，
  且显示取值器 `YlxwDiffCn` 与实际入账 `YlxwDiffMul` **同源前置**。

### 起因与改法（R-232 / R-233）

- 起因：0.9.51 的 R-225b 只把**离线**难度冻结进服务端；**在线**收益仍读客户端 `localStorage` 镜像
  （`save_data.settings.difficulty`）⇒ 改一行本地存储即可白拿 ×2（`hard`）在线收益。
- 改法：
  - **R-233（服务端）**：`GET /api/save`（仅 `!isRevision` 分支）在**主载荷顶层**以 `Object.assign`
    追加 `ylDifficulty`；取值优先 `saves.difficulty` 冻结值，`NULL` / 非法回落 `ylR225bClientDiff(saveData)`
    （= 与 R-225b 冻结器**同源**）。幂等标记 `[r233]`（×4）。
  - **R-232（客户端）**：注入 `YlxwServerDiff()`（服务端权威取值器）与 `YlxwSrvDiffCapture(j)`（读档响应捕获器），
    把该下发值前置为唯一权威源；`YlxwDiffMul`（入账）与 `YlxwDiffCn`（显示）**同源**（消除「显示 / 入账」口径分叉）。
    幂等标记 `[r232recv]`（×1）+ 版本标记 `/*YLXW_R232_V2951*/`（×1）。
- 客户端模块数：`V28_MODULES` = 134 模块（未增减；R-232 为**追加式** standalone 补丁）。

## 2. 指纹（部署前后）

| 对象 | 上一版（部署前） | 本批（部署后） |
|---|---|---|
| `www/assets/index-v2951-20261009.js` | `48e7555ea90e0075fb5bc6c9a67904e0` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2950-20261009.js` | `f18d9cb8440657e1aa51de1a95c89c9c` | 同左（0.9.50 定版，更早的回滚点） |
| `www/assets/index-v2952-20261009.js` | —（新文件） | `f8d16a51fd516f91b8897dd553089ba7` |
| `server/index.ts` | `f1a06d4412f9b18c42192838dba47416` | `328170ededb61fe3289845cb91d3419d` |
| `www/CHANGELOG.md` | `5fdaf5e5c5028b959be546e8443d481f` | `2e534a9d3f7d4817d449fdc3a79410f9` |
| `www/CHANGELOG_PLAYER.md` | `0985c1a69544c099e1477922123117fa` | `f23ca9b18e43fae8d70a09dc1b975d91` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | `1b635513f553875060869272b790f910`（本批不变） |

部署后线上实测（deploy_v2852.sh 采集）：

```
328170ededb61fe3289845cb91d3419d  /opt/yl/server/index.ts            （1,032,803 B / 93 环）
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json     （本批不变）
2e534a9d3f7d4817d449fdc3a79410f9  /opt/yl/www/CHANGELOG.md           （[0.9.52] 条目）
f23ca9b18e43fae8d70a09dc1b975d91  /opt/yl/www/CHANGELOG_PLAYER.md    （R-231 玩家向日志）
f8d16a51fd516f91b8897dd553089ba7  /opt/yl/www/assets/index-v2952-20261009.js （2,328,116 B）
```

★ 五项**全部逐位 == EXPECT_0852.env 登记值**。`index.html` 引用 = `assets/index-v2952-20261009.js`。
gzip 双路（明文 / `Accept-Encoding: gzip` 经 `--compressed`）= `f8d16a51…`，`cmp` **逐字节 IDENTICAL**（R-159 陷阱已避开）。

## 3. 部署前本地验收

`deploy_v2852.sh` step 0 / 0c 实测（全部通过）：

- `bash -n deploy_v2852.sh` / `bash -n remote_check_v2852.sh` 均 OK（生成器 `selfcheck()` 内）。
- `python _mk_2852.py` 跑通：预检 + 7 文件写回 + 13 条一致性复核；三产物同批生成。
- `python localtest/sim_remote_check.py --script deploy_v28/remote_check_v2852.sh --bundle build/assets/index-v2952-20261009.js`
  （★ 显式传 `--bundle`）：**FAIL=0**（OK=830 / SKIP=15）。
- `EXPECT_0852.env`：**纯 LF / 无 BOM / 以换行结尾**（7,188 B）。
- `deploy_v2852.sh --dry-run` 预检通过：step 0 / 0c 全绿，`CHANGELOG [0.9.52] gate: OK`。
- CHANGELOG_PLAYER 格式校验通过、每个版本都有 `### 分类`；本批 [0.9.52] 段在位。
- `EXPECT_0852.env` 四项 md5 全符：bundle `f8d16a51fd516f91b8897dd553089ba7`（2,328,116 B）、
  srv `328170ededb61fe3289845cb91d3419d`（1,032,803 B）、dicts `1b635513f553875060869272b790f910`、
  CHANGELOG `2e534a9d3f7d4817d449fdc3a79410f9`。
- canon `_chainstage/index_v28.v28112.ts` == `srv/index_v28.ts` == `EXPECT_SRV_CANON_MD5`；
  前端基座 `index-v26m-20260927.js` == `b315eb1a04e967a66c128861b3a3dadd`。
- step 0c 双 provenance：预演 `_chainstage/dryrun_087.bundle.js` == 交付 bundle；链尾 `s93.r233.ts` == `srv/index_v28.ts`；
  `s20.t16arena.ts` == `7780e099a6cd1ac0de4b502c467ae2c0`（前 20 环 == 0.8.9 定版，单变量可核成立）。
- 远端未漂移断言：`index.ts` == `f1a06d44…`（0.9.51）、`index-v2951-20261009.js` == `48e7555e…`、
  `index-v2950-20261009.js` == `f18d9cb8…` 三项全符；`CHANGELOG_PLAYER.md` == `0985c1a6…`（R-231 step0b）。
- 门禁：`dryrun_087.py` **PASS (FAIL=0)**；`check_srv_087.py` 服务端链校验通过（93 环）。

## 4. 线上验收

- `remote_check_v2852.sh`（scp 后远端执行 + 部署脚本内嵌各一次）：**PASS (0 failures)**。
- 公网冒烟：`/myxxz/` = 200；`index.html`（明文 + gzip 双路）→ `assets/index-v2952-20261009.js`；
  公网 bundle md5 `f8d16a51fd516f91b8897dd553089ba7`（2,328,116 B）逐位一致；`/myxxz/api/save` 无 token = 401。
- 公网 HTTP 探针：新包 200 / 旧包 `index-v2951` 200 / 更早回滚点 `index-v2950` 200 / `CHANGELOG_PLAYER.md` 200。
- 本批特征（公网 bundle，`grep -o -F | wc -l`）：`/*YLXW_R232_V2951*/` ×1、`/*[r232recv]*/` ×1、
  `YlxwServerDiff=()=>{` ×1、`YlxwSrvDiffCapture=(j)=>{` ×1、`j.ylDifficulty` ×1；
  0.9.51 及更早客户端特征（R-225b / R-227 / R-228 / R-230 串）仍在。
- 服务端特征（`grep -o -F | wc -l`）：`[r233]` ×4、`ylDifficulty` ×2、
  `updated_at, difficulty FROM saves` ×1、`{ ylDifficulty: ylR233Diff }` ×1；
  `res.json(saveData);`（旧主载荷）×0（已清零）；`[r225b]` ×13 仍在（R-225b 未回退）。
- `index.ts` 线上实测 `328170ededb61fe3289845cb91d3419d`；`systemctl is-active yl-server` = active，`NRestarts=0`，
  `ActiveEnterTimestamp` = `Sat 2026-10-10 09:52:21 CST`。
- ★ **数据库变更**：**本批无数据库变更**（R-233 只读 `saves.difficulty` —— 该列由 0.9.51 的 R-225b 建立；
  本批不新增表 / 列）。

## 5. 本轮踩到的新坑

### 5.1 ★★ 上线时踩到：R-231 玩家向日志断言**假失败 2 条**（真因已根治）

- **现象**：`deploy_v2852.sh` 首次上线时 `remote_check` 报 `FAIL (2 failures)`：
  ①「玩家向日志顶部条目 = `## [0.9.52]`（应为 `## [0.9.51]`）」②「玩家向日志有 0 行独立粗体」。
  **但线上文件完全正确**（`PL_TOP=## [0.9.52]`、独立粗体 0 行、md5 == 登记值）。
- **真因 A（版本号字面量）**：`_r231_blocks.py` 的 `RC_R231_BLOCK` 把「本批版本号」写成**字面量 `0.9.51`**
  （它由 0.9.51 那批实测块程序化提取 ⇒ 只在那一批成立）。派生到 0.9.52 后，
  3c 的注入带 `if "R-231" not in s` 幂等守卫 ⇒ 派生源 `remote_check_v2851.sh` **已含** R-231 ⇒ **整段注入被跳过**
  ⇒ 即便把块改成动态求值也**形同虚设**，继承来的 `'## [0.9.51]'` 原样留下。
- **真因 B（`grep -c` 双计数）**：`PB="$(grep -cE '...' "$PL" 2>/dev/null || echo 0)"` ——
  `grep -c` 在**无匹配**时**仍打印 `0` 且 rc=1** ⇒ `|| echo 0` 触发 ⇒ 变量值为 **`"0\n0"`**（两行）
  ⇒ `[ "$PB" = 0 ]` **恒假** ⇒ 0 行粗体时**误报 FAIL**。★ 这是通用 shell 陷阱，与版本号无关。
- **根治**（三处，均已落库）：
  1. `_r231_blocks.py`：块内版本号改 `{NEW_VER}`/`{PREV_VER}` 占位 + 新增 `rc_r231_block(new, prev)`
     求值函数（带占位残留断言）。
  2. `_mk_2852.py` 新增 **3b-2 段**：`rc-fix-r231ver` 三条 fail-closed 规则 ——
     **无论注入是否发生**都推进 `PL_TOP` 断言版本号（`0.9.51`→`0.9.52`，2 处）并把 PB 改为
     `grep -oE ... | wc -l | tr -d ' '`（1 处）。这样两条路径都能得到正确产物。
  3. 修复后重跑 `_mk_2852.py`：三件套重生（`remote_check_v2852.sh` 127,618 B），
     `sim_remote_check.py` **OK=830 / SKIP=15 / FAIL=0**；上传远端复跑 **PASS (0 failures)**。
- ★ 教训固化：**做发布块程序化提取时，凡「本批」字样一律占位化**；否则它会在下一批**静默**变成假失败
  （或更糟——若断言方向相反，会变成静默放过）。

### 5.2 生成器机械派生的槽位错位（上一轮记录，本批沿用）

- `_mk_2852.py` 由 `_mk_2851.py` 机械派生时，多处**槽位错位**（m1/m2 的 md5 锚点、`PREV_SRV_MD5=` 的
  输入锚点、`EXPECT_0851`→`0852` 一度写成恒等、`pre-v2950`/`v2950_consistent` 实为 `pre-v2951`/`v2951_consistent`），
  以及 **STALE_FIX 的 chk 描述串必须用「bump_ver_slots 之后」的新版本号**（0.9.52/0.9.51/0.9.50）——
  已逐条用 `Edit` 精确修正，并靠 `rep_fix` 的 fail-closed 计数断言 + `sim_remote_check.py` 预演全部逼出。
- `rep_log_heredoc` 幂等分支（正文已是版本无关模板 ⇒ 跳过整段替换）意味着 heredoc 里
  `同左（0.9.49 定版，更早的回滚点）` 这类**批次标签不会被自动抬** ⇒ 必须由 `rename()` 的 `c4`
  （本批把 `0.9.49 定版` → `0.9.50 定版`）负责推进；顺序必须**在 c1 之后**（否则新生成的
  「0.9.50 定版」会被 c1 再抬成 0.9.51）。已加注释固化该顺序不变量。
- 历史陈旧注释（**本批未引入、未修，如实登记**）：`deploy_v2852.sh` 内
  `# 单变量可核：本批服务端**无 diff**（纯客户端批）` 自 0.9.44 起即与事实不符
  （服务端自 0.9.44 起持续有环增量），本批沿用原文未改，避免扩大改动面。

## 6. 残留清理

- 远端 `/opt/yl/server/` 保留 `_remote_check_v2852.sh` / `_remote_swap.sh` / `_live_bump_bundle.js`（便于复跑，惯例）。
- 本批未做写库测试，无测试账号 / DB 残留（R-233 只读既有列，未注入测试数据）。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2952-<TS> /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2952-20261009.js --to=index-v2951-20261009.js
cp -a /root/backup/index.ts.pre-v2952-<TS>        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2952-<TS> /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2952-<TS>    /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2952-<TS> /opt/yl/www/CHANGELOG_PLAYER.md   # ★ R-231 新增回滚项
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2951-20261009.js.pre-v2952-<TS> /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版：bundle=48e7555ea90e0075fb5bc6c9a67904e0  server=f1a06d4412f9b18c42192838dba47416
# 整包：/root/backup/yl_pre_v2952_<TS>.tar.gz
```

★ 回滚注意：本批**无数据库变更**（见 §4）；回滚只需还原文件 + 重启服务。
如需完全还原 DB，用 `/root/backup/database_v2952_consistent_<TS>.sqlite` 热拷贝。

## 8. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=f8d16a51fd516f91b8897dd553089ba7
PREV_SRV_MD5=328170ededb61fe3289845cb91d3419d
PREV_CHANGELOG_MD5=2e534a9d3f7d4817d449fdc3a79410f9
PREV_PLAYER_MD5=f23ca9b18e43fae8d70a09dc1b975d91
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=328170ededb61fe3289845cb91d3419d   # 链尾 _chainstage/s93.r233.ts（供单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 各项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
