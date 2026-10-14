# DEPLOY LOG — 《摸鱼修仙传》 0.9.62

- 部署时间：2026-10-14（GMT+8）
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2862.sh`（客户端 + CHANGELOG + index.html bump）
- 定点核对：`deploy_v28/remote_check_v2862.sh` → 本地预演 **OK=1163 / SKIP(远端专有)=15 / FAIL=0**
- 登记指纹：`deploy_v28/EXPECT_0862.env`
- 上一版：0.9.61（2026-10-14），回滚点 bundle `index-v2961-20261011.js` / server `bc623f31…`（97 环）

---

## 1. 本批范围（0.9.62；客户端 **98** 模块 + 服务端 **97** 环 —— **服务端零改动**）

| # | 任务 | 客户端 | 服务端 |
|---|---|---|---|
| R-253 | 网络自愈 + 自动循环断点续跑 | `localtest/yl_r256_ext.py`（第 98 个 / 新末环） | **无** |

### 起因（用户原话）

> 「两个bug看能不能修复：1.有时候断网了会提示 网络断开连接，但是来网之后不会刷新也没有继续，
> 只能手动点击才能继续。2.自动打坐和自动历练时，如果刷新页面，这一轮的结算信息就没有了，
> 打坐和历练也停止了。」

### ★★ 本批最关键的一点：**这是纯客户端批**（与上一批 R-252 相反）

`srv/index_v28.ts` 与 0.9.61 **逐字节相同**（`bc623f31…`，仍 97 环）
⇒ 部署**可以** `--skip-server`，**零停机**（不重启 yl-server）。

---

## 2. Bug ① 根因（已实测取证）

```
断网 → 10s 自动存档失败 → YLSaveAttempt 退避重试 3 次 → throw YLSaveFetchError()
     （文案「网络连接异常，请检查网络后重试」）
  → 自动存档的 .catch 调 Je() → ud() → xo({isOpen:!0,…})  =  **模态弹窗**
```

**★ 放大器（真正的病根）**：该弹窗把 `alertState.isOpen` 置真，而 `isAlertOpen` 是
自动打坐 / 自动历练的**硬门禁**（`Hw` 里两处判定都含它）：

```js
// 自动打坐
if(!(!B.autoMeditate||…||B.isAlertOpen||g.current)){…}
//                         ^^^^^^^^^^^^^^^^ 弹窗一开 ⇒ 恒为真 ⇒ 永久暂停
// 自动历练
return !U.autoAdventure||…||U.isAlertOpen||…
```

而全库 **`addEventListener("online"/"offline")` 命中 0 处**（实测）⇒ 来网后：
弹窗不会自关、存档不会重试、循环不会恢复 ⇒ **只能手点「确定」**。

同一坑还有 `YLSaveNotice`（「服务器正在更新，已自动重试…」）也走 `Je()` 模态。

### 修法

| # | 改动 |
|---|---|
| A1 | 新增**非阻塞提示条** `YLR256NetBanner`（仿 `YLSyncBanner` 的 DOM 做法，但**不占** `alertState`）+ `YLR256Notice`（提示条 + toast），断网时只挂一条，**不锁自动循环** |
| A2 | `YLSaveNotice` 改走 `YLR256Notice`（**不再 `Je()`**） |
| A3 | 自动存档的 `.catch` 改走 `YLR256Notice` |
| A4 | 新增 `offline` / `online` 监听：offline 挂条；**online 自愈** = 撤条 + 复位 `YLSync` 的 `_busy/_inflight/_retry` 卡死态 + 重新认领会话 + **立即补一次存档** |

---

## 3. Bug ② 根因（已实测取证）

**两个独立原因叠加：**

1. `autoMeditate` / `autoAdventure` 是 **zustand 内存态**（初值写死 `!1`），
   全库**没有任何** localStorage/sessionStorage 持久化（实测「持久化痕迹 **0** 处」）
   ⇒ 刷新回 `false` ⇒ 自动循环的 interval effect 依赖 `[t]`/`[r]` ⇒ **不启动**。
2. 结算累加器 `YLXW_MED_SESS` / `YLXW_MED_ACC` / `YLXW_ADV_SESS` / `YLXW_ADV_ACC`
   是**模块级 var**（内存），刷新即丢；而结算日志只在 `false→true` 的**边沿**触发
   （`useEffect(()=>{YlxwMedSession(t)},[t])`）⇒ 刷新后没机会触发
   ⇒ **本轮结算永久蒸发**（从未写进日志，不是被覆盖）。

★ 但累加器里的修为/灵石**已经入账**（`YlxwMedTick` 在 `handleMeditate` 里就地累加），
所以补日志**不会重复发奖**，纯粹是补一条账目说明。

### 修法（用户三项裁定：**记住开启状态** / **只算到离开页面那一刻**）

| # | 改动 |
|---|---|
| B1 | 新增 `yl_auto_switch`（开关）+ `yl_auto_sess`（会话：开门时刻 / 离开时刻）+ 读写/清理/打点/补发/恢复全套函数 |
| B2 | store 初始化**回填**持久化开关 |
| B3 | `setAutoMeditate` / `setAutoAdventure` 包一层**写持久化** |
| B4/B5 | 打坐 / 历练会话边沿：开 ⇒ 记「开门时刻」；**真关闭** ⇒ 清 |
| B6 | **boot 钩子**：`YLR256Boot()`（= 补发 + 恢复 + 为新会话记账）挂在既有
`Be.subscribe(t=>t.player,…)` 之后，`window.__ylR256Boot` 守卫保证**每页只跑一次** |

---

## 4. ★★ 本批踩到的坑（**5 个实现缺陷全部由浏览器 e2e / 语义测试抓到，单元测试曾一度全绿**）

| # | 缺陷 | 怎么发现的 | 修法 |
|---|---|---|---|
| 1 | **`YLR256Boot` 只被定义、无人调用** ⇒ 功能完全静默失效 | 写「boot 钩子是否真的接线」断言时发现产物里**没有**调用点 | 挂到既有玩家订阅后（B6） |
| 2 | `YLR256ReadSess` 要求一个**冗余 `t` 字段** ⇒ 无 `t` 的会话被判为「无会话」 | 调试脚本直调 `ReplayLost` 返回 0 条 | 改为「有 m/a/left 任一即可」 |
| 3 | store 回填**静默失效**：store 在 @590390 求值，而 `var YLXW_AUTO_KEY` 到 @~660k 才赋值 ⇒ `getItem(undefined)` → null | 浏览器实测「刷新后 medOn=False」 | 回填**内联键名直接读 localStorage**，不依赖后置 var |
| 4 | **首帧关边沿误删会话**：`[t]` effect 首帧就跑且 `t=false` ⇒ 把上一页存的会话当「用户主动关闭」清掉 | 浏览器实测「刷新后 sess=None、无补发」 | 只有「曾经开过」（`window.__ylR256MedOn`）才算真关闭 |
| 5 | **effect 在 boot 之前覆盖「开门时刻」** ⇒ `leave − 开门` 变**负数** ⇒ 判定「无需补发」 | 浏览器实测：`m` 变成刷新后的新时间戳、`left` 消失 | ① 待补发期（`left>0 && !REPLAYED`）**禁止写入**；② boot 末尾为仍开着的开关**补记新会话** |

★ 教训：**「单测全绿 ≠ 功能可用」**。本批 5 个缺陷里有 4 个只有**真实浏览器 + 真实产物 + 真实 API**
  才能暴露；第 1 个甚至是「函数写好了但没人调」这种静态检查查不到、语义测试又因为直接调函数而误判通过的类型。

---

## 5. 上游门禁同步（§22.5）

R-253 的 B3 把 `setAutoAdventure` setter 包了一层，boot 恢复又新增 1 处调用
⇒ 全 bundle 该标识 **29 → 31**，打穿三条钉「精确 29」的针脚：

| 模块 | 门禁 | 处理 |
|---|---|---|
| `localtest/yl_r138_ext.py` | `冻结·setAutoAdventure 调用点未增减` | 改 **`>=`**（不变量 = 调用点没被删） |
| `localtest/yl_r155_ext.py` | `冻结·setAutoAdventure未动` | 同上 |
| `patches/client/yl_advend105_ext.py` | `冻结·setAutoAdventure 调用点未增减` | 同上 |

★ 旧精确值 **29 保留在各文件注释里**，并写明「谁改的、为什么」——**无一处静默放宽**。

---

## 6. 指纹（部署前后）

| 对象 | 上一版（0.9.61） | 本批（0.9.62） |
|---|---|---|
| `www/assets/index-v2961-20261011.js` | `5e3c732e6a5e019d69a918c9de8f5fd1` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2960-20261011.js` | `dba25e79bf68085d004f74809c567b71` | 同左（0.9.60，更早回滚点） |
| `www/assets/index-v2962-20261011.js` | —（新文件） | **`c2d13533179955841df86891f21a1cb8`**（2,354,602 B） |
| `server/index.ts` | `bc623f3117529477157ebdbb413cac88`（97 环） | **同左（本批未变）** |
| `www/CHANGELOG.md` | `db61534c31586a139e90d5fdf6a87ada` | **`0df22f63dfade6a6e1e230f4af64b06a`** |
| `www/CHANGELOG_PLAYER.md` | `f01951faeeefabc253b6667a2ba56041` | **`425f02bfbb2d5cdca35319e27c50eb01`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（未变）** |

---

## 7. 部署前本地验收（全绿）

| 环节 | 结果 |
|---|---|
| 补丁模块自检 | 门禁全绿（含 5 条冻结 + 2 条防覆盖）｜往返自证「逐字节回到基线」｜`node --check` OK｜`delta +10793 B` |
| 语义真值表 `localtest/_r256_sem.js` | **ALL PASS 0 失败**（10 组：断网不弹模态 / 来网自愈 / online-offline 闭环 / 开关读写 / 会话打点 / 补发幂等 / boot 恢复 / 离开打点 / **boot 接线防呆** / boot 编排幂等） |
| 链式构建 | 97 环全过（服务端 md5 与上批**相同**）；bundle `7f28979b…` |
| 全量门禁 `dryrun_087.py` | **PASS（FAIL=0）**；standalone **2292 条**；**预演 == 交付** |
| 浏览器端到端 `localtest/t_r256_live.py` | **17/17 PASS** —— 含：开自动打坐 → 断网（拦截 /save）→ **无模态弹窗** + **循环仍在跑** → 来网 → **提示条自动消失**；开自动 → pagehide 打点 → 刷新 → **开关自动恢复** + **补发结算日志** + **key 已清**；连续刷新**每轮补一条、不重复计数** |
| 部署包预演 | `sim_remote_check.py` → **OK=1163 / SKIP=15 / FAIL=0** |

---

## 8. 回滚

```bash
# 回滚到 0.9.61（旧包仍在，服务端本批未动 ⇒ 无需回滚 server）
cp /root/backup/index-v2961-20261011.js.pre-v2962-<TS> /opt/yl/www/assets/
/usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2962-20261011.js --to=index-v2961-20261011.js
```

★ 回滚注意：本批**无服务端改动、无表结构变更** ⇒ 回滚只需换回 bundle，**不必重启 yl-server**。

★ **存档兼容性（重要）**：本批在浏览器 localStorage 新增两个键
（`yl_auto_switch` / `yl_auto_sess`）。回滚到 0.9.61 后旧代码**不认识**它们 ⇒ 只是被忽略，
**不影响任何进度**（它们不参与服务端存档）。

---

## 9. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=c2d13533179955841df86891f21a1cb8
PREV_SRV_MD5=bc623f3117529477157ebdbb413cac88
PREV_CHANGELOG_MD5=0df22f63dfade6a6e1e230f4af64b06a
PREV_PLAYER_MD5=425f02bfbb2d5cdca35319e27c50eb01
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=bc623f3117529477157ebdbb413cac88   # 链尾 _chainstage/s97.r255.ts（本批未变）
```
