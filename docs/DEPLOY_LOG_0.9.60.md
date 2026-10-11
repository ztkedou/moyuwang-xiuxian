# DEPLOY LOG — 《摸鱼修仙传》 0.9.60

- 部署时间：2026-10-11 18:36 (GMT+8)
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2860.sh`（客户端 + 服务端 + CHANGELOG + index.html bump）
- 定点核对：`deploy_v28/remote_check_v2860.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0860.env`
- 备份整包：`/root/backup/yl_pre_v2960_20261011_183537.tar.gz`
- DB 一致性快照：`/root/backup/database_v2960_consistent_20261011_183537.sqlite`

---

## 1. 本批范围（0.9.60；客户端 **96** 模块 + 服务端 **96** 环）

> 规模口径：`CLIENT_MODULES` = `build_v26n.STANDALONE_CLIENT` 条数；`SRV_RINGS` = `localtest/chain_build.py` 的 `SRV_CHAIN` 环数。

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-251 | 仙务称号加成「重规划」 | `localtest/yl_r254_ext.py` / `patches/server/srv_patch_r253.py`（**第 96 环**） | 7 新维度 + 3 落点 | 14 条 `UPDATE titles SET attr_json` |

### 起因（用户原话）

> 「重新规划一下各个称号的加成，现在的太简单有点无趣且重复较多。」

### ★ 病根诊断 —— 不是数值小，是「没得选」

仙务称号是 **佩戴制**（`saves.title_id`，一次只能戴一个），而 7 个排行称号**全是单属性 +10~15%**
（攻击×2 / 灵石×2 / 修炼×2）⇒ 玩家只有**比较**、没有**选择**，称号不构成**流派**。
**修法 = 复合加成 + 招牌维度唯一。**

### ★ 侦察结论（两套称号系统，本批只动 B 表）

| 系统 | 数量 | 加成维度 | 性质 |
|---|---|---|---|
| **A. 客户端内置 `Ln` 表** | 17（境界 5 + 套装 9 + 独立 3） | `attack/defense/hp/spirit/physique/speed/expRate/luck`（flat） | 境界/成就**自动授予**的成长曲线 ⇒ **本批不动** |
| **B. 服务端 `titles` 表** | 14（排行 7 + 活动 7） | 见下 | **佩戴制** ⇒ 本批对象 |

### 可加成维度（**实测有消费点才可用**）

| 键 | 落点 | 封顶 |
|---|---|---|
| `atkRate` / `defRate` / **`hpRate`** / **`spiritRate`** | `xt()` 末尾（须在 `YlxwStatExtras` / `YlxwSpiritExtras` **之后**） | — |
| **`critRate`** / **`critDamage`** / **`lifeLeech`** / **`damageReduction`** | **`YlxwBattleBonus(p)`**（与 R-245 心法机制**同处**，加法） | crit **35%** / dr **60%** |
| `expRate` | `bd().total` | — |
| `stoneRate` | `YlxwDiffGain` 的 `stoneMul` | — |
| **`luckRate`** | 顿悟式（`/*[r241enl]*/` 后的乘子链） | — |
| `charmRate` | ★ **无消费点**（只能展示，不得作为唯一加成） | — |

### 新设计

**7 个排行称号**（招牌维度互不重复）：

| 榜 | 称号 | 新加成 |
|---|---|---|
| 境界榜 | 登峰造极 | `expRate .15` + `luckRate .10` |
| 战力榜 | 武林盟主 | `critRate .04` + `critDamage .15` + `atkRate .10` |
| 灵石榜 | 富甲一方 | `stoneRate .15` + `luckRate .06` |
| 击杀榜 | 万人敌 | `lifeLeech .04` + `critDamage .10` + `atkRate .10` |
| 成就榜 | 功成名就 | `spiritRate .12` + `expRate .08` |
| 在线榜 | 苦修不辍 | `defRate .12` + `hpRate .12` + `damageReduction .03` |
| 声望榜 | 德高望重 | `luckRate .12` + `stoneRate .08` |

**7 个活动称号**（人格化小幅增强，幅度 ≤5%）：
福缘深厚 / 七日筑基 / 良师益友 / 灵玉仙客 / 月满勤修 / 义结金兰 / 太虚魁首。

★ **服务端改 attr_json 必须用 `UPDATE`** —— 既有 seed 是 `INSERT OR IGNORE`（改不动已存在行）。

## 2. 指纹（部署前后）

| 对象 | 上一版（部署前） | 本批（部署后） |
|---|---|---|
| `www/assets/index-v2959-20261011.js` | `f649dc234f46844c0ebb5fdbb356b3d9` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2958-20261011.js` | `96f1b5e729156079506afa9bf1b00de3` | 同左（0.9.58 定版，更早的回滚点） |
| `www/assets/index-v2960-20261011.js` | —（新文件） | **`dba25e79bf68085d004f74809c567b71`**（2,345,037 B） |
| `server/index.ts` | `0098cb4faa62c6e406963da84ce07120` | **`399bcae1e2896f221fcc6fa6b07c8ee6`**（1,046,957 B） |
| `www/CHANGELOG.md` | `6a8d87223a1d8a26f2f3d6c794fa013d` | **`b3451660bdf70eb4b0ae9eec97cf20ca`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（未变）** |

部署后线上实测（deploy_v2860.sh 采集）：

```
399bcae1e2896f221fcc6fa6b07c8ee6  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
b3451660bdf70eb4b0ae9eec97cf20ca  /opt/yl/www/CHANGELOG.md
dba25e79bf68085d004f74809c567b71  /opt/yl/www/assets/index-v2960-20261011.js
```

## 3. 部署前本地验收

- `_bump_0860.py`：八处全绿（预检 + 落盘 + 复核）。
- `localtest/dryrun_087.py`：**4342 条门禁 / FAIL 0**，预演产物 md5 = **`dba25e79…`**。
  （比上批 +1 条 = `yl_version_ext.py` 新增的「0.9.59 已清零」兜底针）
- `localtest/chain_build.py --all`：**96 环**完成；服务端 `0098cb4f…` → `399bcae1…`；
  ★ **前端 md5 == 预演 md5**（「预演 == 交付」成立）。
- `build_v26n.py`：产物 `dba25e79…` **== 预演 md5**。
- `localtest/sim_r231_inject.py --new 0.9.60 --prev 0.9.59`：**FAILS = 0**。
- `localtest/diag_gate_drift.py`（对终态产物）：**0 漂移**（2164 条门禁全成立）。
- `localtest/sim_remote_check.py --script deploy_v28/remote_check_v2860.sh`：**OK=1163 / SKIP=15 / FAIL=0**。

## 4. 线上验收

- `deploy_v28/deploy_v2860.sh`（**未加 `--skip-server`**，本批服务端有变）→ **REMOTE-CHECK: PASS (0 failures)**。
- 远端指纹逐位核对：bundle / server / CHANGELOG / CHANGELOG_PLAYER **四项全与 EXPECT 一致**。
- 公开冒烟：index **200** / bundle **200** / 未授权 API **401**。
- `yl-server`：**2026-10-11 18:36:11 重启，active**（★ 本批**非零停机**，秒级中断）。

★ **数据库变更**：**本批无表结构变更**（无新增表 / 无新增列）。
只有 `UPDATE titles SET attr_json = ? WHERE source = ?` **14 行数据迁移**（7 排行 + 7 活动）。
⇒ **回滚到上一版无需删列 / 删表**（旧代码不读多余键，多余键无害）。

★ **线上 DB 实测复核**（主对话直连 `/opt/yl/server/database.sqlite` 只读查）：

```
灵玉仙客  {"stoneRate":0.02,"luckRate":0.03}        福缘深厚  {"stoneRate":0.03,"luckRate":0.05}
太虚魁首  {"stoneRate":0.05,"atkRate":0.05}         良师益友  {"expRate":0.03,"spiritRate":0.05}
月满勤修  {"expRate":0.02,"defRate":0.03}           功成名就  {"spiritRate":0.12,"expRate":0.08}
武林盟主  {"critRate":0.04,"critDamage":0.15,"atkRate":0.10}
德高望重  {"luckRate":0.12,"stoneRate":0.08}        万人敌    {"lifeLeech":0.04,"critDamage":0.10,"atkRate":0.10}
苦修不辍  {"defRate":0.12,"hpRate":0.12,"damageReduction":0.03}
登峰造极  {"expRate":0.15,"luckRate":0.10}          富甲一方  {"stoneRate":0.15,"luckRate":0.06}
义结金兰  {"charmRate":0.02,"luckRate":0.03}        七日筑基  {"expRate":0.03,"hpRate":0.03}
--- rank_title_state ---
(1, '2026-10-11')
```

⇒ **14 条逐条 == 设计值**；`rank_title_state` 正常（上批建的日结算状态表）。
**这是比"部署成功"更硬的证据：线上数据真的变了。**

## 5. 本轮踩到的新坑

### ★ 第 6 次「冻结针脚被下游改写」—— **又是 R-246 自动名单当场抓到**

r254 把**顿悟式**再包一层 `*(1+luckRate)`（第 3 次改写：R-241 → R-243 → R-251）+ 把
`YlxwXianwuZero` 从 5 键扩到 12 键 ⇒ 一次**打穿 6 条针**：

| 模块 | 针 | 处置 |
|---|---|---|
| `yl_r188_ext.py` | `R188v2·v2 判定行已注入` / `★有天赋分支=0.05` / `★无天赋分支=0.01`（3 条） | 三形态 → **四形态** tuple |
| `yl_r241_ext.py` | `R241-A luck rate` | 两形态 → **三形态** tuple |
| `yl_r243_ext.py` | `R243-H1 顿悟率消费` | 升 **两形态** tuple |
| `yl_r252_ext.py` | `E2 Zero defRate` | 升 **两形态** tuple |

**全部按铁律改 tuple 合计多形态，无一处放宽。**

★ **可记的规律**：前三次（0.9.54 / 0.9.55 / 0.9.56）靠**人**发现；
后三次（R-247 / R-249 / R-251）**全部是 R-246 的自动派生名单 + `diag_gate_drift` 当场报出来的**。
⇒ **机制投资已连续三轮还本。**

### 集成审计（主对话串行做）

- **两端字段名逐字对齐**：客户端 `YlxwXianwuStore` 读 **12 键** == 服务端 attr_json 写 **12 键** ✓
  （审计方法：把补丁打进沙箱产物，再从**真实产物**抽 `YlxwXianwuStore` 全文比对 ——
  不在补丁源码上比对，因为补丁是 EDITS 表、形态与产物不同）
- 三处落点位置精确：`xt()` 在 `YlxwStatExtras`/`YlxwSpiritExtras` **之后**；
  `YlxwBattleBonus` 在 R-245 的 `YlxwR245Mech` **之后**；顿悟式在 `/*[r241enl]*/` 前。
- **服务端代理的一处自主决策**（已接受）：规格只给了 7 条排行 UPDATE 的落点，未给 7 条活动 UPDATE 的落点；
  它按「加成集中于此、单点可调」的既有约定把 **14 条并入同一块**。

## 6. 残留清理

远端 `/opt/yl/server/` 保留 `_remote_check_v2860.sh` / `_remote_swap.sh` / `_live_bump_bundle.js`（便于复跑）。
本地临时脚本（`_chk_db.py` 等）已删；`_r249_srv_sandbox/` / `_r253_srv_sandbox/` 按惯例不入库。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2960-20261011_183537 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2960-20261011.js --to=index-v2959-20261011.js
cp -a /root/backup/index.ts.pre-v2960-20261011_183537        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2960-20261011_183537 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2960-20261011_183537    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2959-20261011.js.pre-v2960-20261011_183537 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版：bundle=f649dc234f46844c0ebb5fdbb356b3d9  server=0098cb4faa62c6e406963da84ce07120
# 整包：/root/backup/yl_pre_v2960_20261011_183537.tar.gz
```

★ 回滚注意：本批**无表结构变更** ⇒ 回滚到上一版**无需删列 / 删表**
（旧代码不读 `hpRate` / `luckRate` / `critRate` 等多余键，多余键无害）；
**如需完全还原**用 `/root/backup/database_v2960_consistent_20261011_183537.sqlite` 热拷贝。

## 8. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=dba25e79bf68085d004f74809c567b71
PREV_SRV_MD5=399bcae1e2896f221fcc6fa6b07c8ee6
PREV_CHANGELOG_MD5=b3451660bdf70eb4b0ae9eec97cf20ca
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=399bcae1e2896f221fcc6fa6b07c8ee6   # 链尾 _chainstage/s96.r253.ts（供单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
~/.ai-memory/topics/项目-摸鱼修仙传.md「当前版本」段。
