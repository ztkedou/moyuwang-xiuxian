# DEPLOY LOG — 《摸鱼修仙传》 0.9.57

- 部署时间：2026-10-11 01:27 (GMT+8)
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2857.sh`（**纯客户端批** ⇒ `--skip-server`，**零停机**）
- 定点核对：`deploy_v28/remote_check_v2857.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0857.env`
- 备份整包：`/root/backup/yl_pre_v2957_20261011_012619.tar.gz`
- DB 一致性快照：`/root/backup/database_v2957_consistent_20261011_012619.sqlite`

---

## 1. 本批范围（0.9.57；客户端 2 模块 + 服务端 93 环**不变**）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-247 | 功法机制库补完：**先手 / 淬体 / 逆修**（第 7/8/9 个机制） | 数据层 `localtest/yl_r247_ext.py` + 钩子层 `localtest/yl_r248_ext.py` | ✅ 2 模块 | — 零改动 |

**接口冻结（★ 本批流程改进）**：先写规格 `策划_R247_三机制接口冻结_20261011.md` 作为**唯一真相源**
（字段名逐字 / 数值档 / 折价规则 / 落点锚点 / 工单边界），再派两个**并行**工单（数据层 / 钩子层）
⇒ 直接吸收了 0.9.56 批「并行工单接口没冻结」的教训。

**机制设计**
| 机制 | 效果 | 归属流派 | 落点 |
|---|---|---|---|
| **先手** `firstStrike` | 战斗**首回合**伤害 +4%~18% | 攻伐 / 身法 | `km` / `zy`（`t.round<=1`）；历练快速结算用 `R.length===0`（该路径无回合概念） |
| **淬体** `cuiti*` | **每次突破**永久 +属性 | 守御 | `xt()` 属性汇总 ×`statistics.breakthroughCount` |
| **逆修** `nixiuExp`/`nixiuDef` | **修炼 +6%~16% 但防御 −4%~11%** | 诡道 | `bd().total` 加成；`xt()` 防御扣减 |

**★ 淬体走「突破次数派生」**：`statistics.breakthroughCount` **已随玩家 blob 持久化**
⇒ **无需改存档结构、无需服务端变更**。★ 边界：**转世**会重建玩家对象、不携带 `statistics`
⇒ 淬体收益归零（与既有 `permGain` 同）。
**★ 逆修防御扣减**落在 `xt()` 属性汇总**末尾**（作用于最终面板值）⇒ 面板与战斗**同步**下降（有意为之），
也会降低秘境/道合实力估算。★ 已复验**与金丹法门无关**（`goldenCoreMethodCount`=0 与 =5 都扣）。

**数据层**：给 **9 部**功法追加字段（先手 3 部：御风步/金乌啄日/天雷剑诀；淬体 3 部：铁皮功/玉骨功/万灵树甲；
逆修 3 部：木身功/血刃诀/地煞冥诀），并按 §7.2 折价重算属性（黄/玄/地/天 四档总当量各降 **2.1%~2.5%**，≤3%）。
★ 诡道 15 部**全带既有机制**（`lifeLeech`）⇒ 逆修必然成「双机制」，取**中档 ×0.78**（非双机制 ×0.58，
避免过度削弱）；折价基准取**该部当前当量**（非品级基准，否则会把地/天部属性抬高）。
★ **无对应字段的功法行为不变**（向后兼容）。

## 2. 指纹（部署前后）

| 对象 | 上一版（部署前） | 本批（部署后） |
|---|---|---|
| `www/assets/index-v2956-20261010.js` | `6fc3c750d147aa314e3a9433a6c9385e` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2955-20261010.js` | `77d35f9c7a1570308cee19c319348e6a` | 同左（0.9.55 定版，更早的回滚点） |
| `www/assets/index-v2957-20261011.js` | —（新文件，**日期跨天**） | `cacfe8f21bd283d46bb2b4c5f4c5012c` |
| `server/index.ts` | `328170ededb61fe3289845cb91d3419d` | `328170ededb61fe3289845cb91d3419d`（**未变**） |
| `www/CHANGELOG.md` | `39e7a8ad964c63756d6f5a8b0c54f8d7` | `9e8e5afda256e3f66fe0e31bc19d699d` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | `1b635513f553875060869272b790f910`（本批不变） |

部署后线上实测（deploy_v2857.sh 采集）：

```
328170ededb61fe3289845cb91d3419d  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
9e8e5afda256e3f66fe0e31bc19d699d  /opt/yl/www/CHANGELOG.md
cacfe8f21bd283d46bb2b4c5f4c5012c  /opt/yl/www/assets/index-v2957-20261011.js
```

★ **bundle 日期跨天**：`20261010` → **`20261011`**（0.9.53~0.9.56 四批都是 20261010 同日再版）。

## 3. 部署前本地验收

- `_bump_0857.py`：八处同改，预检 + 落盘 + 复核全 OK。
- `localtest/dryrun_087.py` → 门禁 **4339 条 / FAIL 0**；「预演 == 交付」md5 一致 = `cacfe8f2…`。
- `localtest/sim_r231_inject.py --new 0.9.57 --prev 0.9.56` → **FAILS=0**。
- `localtest/sim_remote_check.py --script deploy_v28/remote_check_v2857.sh` → **OK=964 / SKIP=15 / FAIL=0**。
- 三件套 `bash -n` 双绿；纯 LF / 无 BOM / 换行结尾。
- `chain_build.py --all`：前端 `cacfe8f2…`、服务端 `328170ed…`（**未变**，93 环，链尾 `s93.r233.ts`）、
  dicts `1b635513…`；链 `s20.t16arena.ts` == `7780e099a6cd1ac0de4b502c467ae2c0`（前 20 环 == 0.8.9 定版）。
- `build_v26n.py` 产物 md5 == 预演 md5（**「预演 == 交付」成立**）。
- `localtest/diag_gate_drift.py` → **0 漂移 rc=0**（R-246 工具，本批已用上）。
- 交付产物独立核验：`firstStrike` / `cuitiDefense` / `cuitiHp` / `nixiuExp` / `nixiuDef` 全在位、
  聚合器 `YlxwR247Mech` 在位、四处钩子就位、幂等标记 `/*[r247data]*/` 与 `/*[r248mech]*/` 各 1 处。

## 4. 线上验收

- `deploy_v2857.sh --skip-server` 内建核对 + 远端 `_remote_check_v2857.sh` → **REMOTE-CHECK: PASS (0 failures)**。
- 公开冒烟：`GET /myxxz/` → **200**；`GET /myxxz/assets/index-v2957-20261011.js` → **200**；未授权 API → **401**。
- 远端 `CHANGELOG_PLAYER.md` md5 == 本地（`1fb6c1f19d893b8a9b5bd4b93d7097c5`），顶部条目即 `[0.9.57]`。
- 远端 `CHANGELOG.md` md5 == 本地（`9e8e5afda256e3f66fe0e31bc19d699d`）。
- `systemctl is-active yl-server` = **active**（`--skip-server` ⇒ **未重启、零停机**）。
- ★ 数据库变更：**本批无数据库变更**（淬体走「突破次数派生」，不新增字段/表）。

## 5. 本轮踩到的新坑

1. **★★ 第 4 次「冻结针脚被下游改写」——但这次是机器抓到的**：
   r248 给 `bd()` 的 `total` 追加 `+__nixiu`（逆修修炼加成）⇒ 打穿 **r238 的 2 条针 + r222 的退役针**。
   ★★ **R-246（上一批）刚把 `dryrun` 的门禁名单改为从 `STANDALONE_CLIENT` 自动派生** ⇒
   **当场**在 `dryrun` 输出里报出来（前 3 次都要靠人想起来补名单）。
   ⇒ 按铁律改 tuple：**r222 升为三形态**（R-228 / R-238 / R-238+r248）、**r238 两条改两形态**（新增 `GATE_ALT` 覆盖表）。
   ★ 结论：**R-246 的投资在这一批就回本了**。
2. **★ 规格 bug（主对话的错，被钩子代理正确拦下）**：初版规格 §3.2 把逆修的防御锚点定在
   `r.defense+=Tr(t.defense,c,d)`，而该行**落在 `if(goldenCoreMethodCount>0){ … }` 块内**
   ⇒ 照做会变成「**只有带金丹法门的玩家**才吃防御扣减」。钩子代理**没有擅自改、如实上报**（做法正确）
   ⇒ 改规格 + 把扣减移到 `xt()` 属性汇总末尾，并复验 `goldenCoreMethodCount`=0/5 都扣。
   ★ 教训：**规格里的锚点必须连「它处在哪个条件分支内」一起写清**，只给字符串不够。
3. **★ 并行工单的接口冻结见效**：本批先冻结字段名/数值档/落点/边界再派单 ⇒ **未出现** 0.9.56 那种
   「两侧字段名不匹配、机制静默失效」的问题。**（0.9.56 的教训已转化为流程。）**
4. **r244 的门禁是「段落前后比对」型**（apply 时刻自洽、**不描述终态**）：r247 合法改写其中 9 部
   ⇒ 已在 `yl_r244_ext.py` 的 `gates()` docstring 写明语义与责任划分（终态由 r247 自己的门禁负责），
   并确认 `dryrun`（自动派生名单）与 `diag_gate_drift.py` 都会**打印跳过原因**（不存在静默失败）。

## 6. 残留清理

远端 `_remote_check_v2857.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` 留在 `/opt/yl/server/` 便于复跑。
本地沙箱（`localtest/_r247_sandbox/`、`_r248_sandbox/`）已 gitignore，提交前可删。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2957-20261011_012619 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2957-20261011.js --to=index-v2956-20261010.js
cp -a /root/backup/index.ts.pre-v2957-20261011_012619        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2957-20261011_012619 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2957-20261011_012619    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2956-20261010.js.pre-v2957-20261011_012619 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版：bundle=6fc3c750d147aa314e3a9433a6c9385e  server=328170ededb61fe3289845cb91d3419d
# 整包：/root/backup/yl_pre_v2957_20261011_012619.tar.gz
```

★ 回滚注意：数据库变更（若有）见 §4。回滚到上一版时**无需删列 / 删表**
（旧代码不读多余列，多余列无害）；**如需完全还原**用
`/root/backup/database_v2957_consistent_20261011_012619.sqlite` 热拷贝。

## 8. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=cacfe8f21bd283d46bb2b4c5f4c5012c
PREV_SRV_MD5=328170ededb61fe3289845cb91d3419d
PREV_CHANGELOG_MD5=9e8e5afda256e3f66fe0e31bc19d699d
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_PLAYER_MD5=1fb6c1f19d893b8a9b5bd4b93d7097c5
PREV_SRV_CHAIN_TAIL_MD5=328170ededb61fe3289845cb91d3419d   # 链尾 _chainstage/s93.r233.ts（供单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
~/.ai-memory/topics/项目-摸鱼修仙传.md「当前版本」段。
