# DEPLOY LOG — 《摸鱼修仙传》 0.9.61

- 部署时间：2026-10-14（GMT+8）
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2861.sh`（客户端 + 服务端 + CHANGELOG + index.html bump）
- 定点核对：`deploy_v28/remote_check_v2861.sh` → 本地预演 **OK=1163 / SKIP(远端专有)=15 / FAIL=0**
- 登记指纹：`deploy_v28/EXPECT_0861.env`
- 上一版：0.9.60（2026-10-11 18:36），回滚点 bundle `index-v2960-20261011.js` / server `399bcae1…`（96 环）

---

## 1. 本批范围（0.9.61；客户端 **97** 模块 + 服务端 **97** 环）

> 规模口径：`CLIENT_MODULES` = `build_v26n.STANDALONE_CLIENT` 条数；`SRV_RINGS` = `localtest/chain_build.py` 的 `SRV_CHAIN` 环数。

| # | 任务 | 客户端 | 服务端 |
|---|---|---|---|
| R-255 | 寿命系统重构：剩余寿命递减 → **年龄递增** | `localtest/yl_r255_ext.py`（第 97 个 / 新末环） | `patches/server/srv_patch_r255.py`（**第 97 环** / 新末环） |

### 起因（用户原话）

> 「yl项目，把寿命彻底重构一下，要求如下：1.寿命不是现在的进度条降低，换成『年龄』，变成增长，新建角色从0岁开始。
> 2.默认寿命区间展示在面板上，比如说炼气1层大概80-100岁。但是实际的初始寿命是在区间内随机出一个固定值，
> 只是不展示出来，但是游戏到了固定的寿命值就只能重开游戏重修。3.游戏每升一个境界或者吃延长寿命的丹药，
> 就会展示新的寿命区间，并且把寿命上限加上。4.现在的打坐、历练这些的减少寿命，就变成了增加年龄。
> 5.寿命的上限区间还是用之前参考实际修仙小说的设定。6.大概按照这样的内容重构，有什么问题你先问我，设计好了之后再开始动工。」

### ★ 设计（用户 11 项裁定拍板；完整方案见 `docs/寿命重构设计方案.md`）

**核心模型**（`maxLifespan` 保留字段名，语义改为**真实死线**的落盘副本）：

```
age          当前年龄（内部小数，面板取整）            可见
lifeRatio    建号时随机抽定 ∈ [0.9, 1]，终身不变      隐藏
lifeBonus    丹药永久加寿累计                          间接可见
U_display = U_base(境界,层) + lifeBonus                面板展示的区间上限
deathLine = lifeRatio × U_base + lifeBonus             真实死线（隐藏）
展示区间   = [⌊0.9 × U_display⌋, ⌈U_display⌉]
寿终条件   = age ≥ deathLine
```

**★ 数学自洽性（本批最关键的不变量）**：对任意 `lifeBonus ≥ 0`、`lifeRatio ∈ [0.9, 1]`，

```
0.9 × U_display  ≤  deathLine  ≤  U_display
```

恒成立 ⇒ **真实死线永远落在展示区间内，永不穿帮**。证明：
左端 ⟺ `(0.9 − lifeRatio) × U_base ≤ 0.1 × lifeBonus`，因 `lifeRatio ≥ 0.9` 左端 ≤ 0；
右端 ⟺ `lifeRatio ≤ 1`。
验证：`localtest/_r255_sem.js` 真值表 8 组（区间表 / 成长自洽 / 死线∈区间随机 **1000 组** / 建号 200 组 /
突破 300 组 / 迁移 8 例 / 迁移幂等 / 丹药）+ 交付产物实抽算法复跑 5000 组 —— **全绿**。

**★ 成长公式沿用既有 `YlxwLifeStep`，一行不改**：小境界 `(next−cur)/16` × 8 步 + 大境界 `(next−cur)/2`
= `next − cur` ⇒ 天然满足用户「前 9 层少量增加、跨大境界大量补齐」。

**寿元区间表**（沿用《凡人修仙传》权威设定；下限 = 上限 × 0.9）：

| 境界 | 1 层区间 | 9 层区间 |
|---|---|---|
| 炼气期 | **90-100** | 135-150 |
| 筑基期 | **180-200** | 292-325 |
| 金丹期 | **405-450** | 652-725 |
| 元婴期 | **900-1000** | 1350-1500 |
| 化神期 | **1800-2000** | 2700-3000 |
| 合道期 | **3600-4000** | 5400-6000 |
| 长生境 | **7200-8000** | 7200-8000（末档不再加） |

### ★ 客户端 16 处落点（`yl_r255_ext.py`，幂等标记 `/*YLXW_R255_V2961*/`）

| # | 落点 | 改法 |
|---|---|---|
| I0 | 注入辅助函数块（YL_LIFE_097 块内） | `YlxwAgeRoll/YlxwLifeUpper/YlxwLifeBonus/YlxwLifeShow/YlxwLifeDeathLine/YlxwLifeRange/YlxwLifeTextOf/YlxwLifeText/YlxwLifeMigrate`（**纯 ASCII**，中文全 `\uXXXX`） |
| E1 | 建号 @537472/@538630 | `age:0, maxLifespan:M, lifeRatio:M/$||1, lifeBonus:0`；`M = 100 × YlxwAgeRoll()`（**只抽一次随机**） |
| E2 | 打坐 @761520 + 常量 @1525530 | `lifespan −= YLXW_MED_LIFE` → `age += YLXW_MED_LIFE`；**`0.001 → 0.0002`**（用户裁定：约 43 → 8.6 岁/天） |
| E3 | 历练 @1939368 + 日志 @1939401 | `S.age = (age??0)+h+(lifespanChange<0?−lifespanChange:0)`；`lifespanChange>0 → lifeBonus +=`；日志「寿元 −N 年」→「年龄 +N 岁」 |
| E4 | 突破 @764155/日志/返回 @765131 | `st = Ne + (g.lifeRatio??1)×_e, ke = g.age??0`（死线按比例增长、**age 不变**）；文案改「寿元增长，当前寿元区间：…」 |
| E5 | 传承连跳 @767860 | 同源化 `Ie = le+(f.lifeRatio??1)×ge, ue = f.age??0`；**删死代码 `T.baseMaxLifespan;`** |
| E6 | 丹药 `effect.lifespan` @814609 | → `effect.ageReduce`（**减年龄**） |
| E7 | 丹药 `permanentEffect.maxLifespan` @815295 | → `u.lifeBonus += N`（**加真实寿元**） |
| E8 | 离线 @590734/@591147 | `lifespanSpent` → `ageSpent`；`age += ageSpent` |
| E9 | 面板 @847626/@850556 | `寿命 (年) X / Y` + 递减条 → **`年龄 X 岁 · 寿元 lo-hi 岁`** + 递增条（分母 = 区间上限） |
| E10 | 预警 @2150441 | 改比较**区间下限**（不泄露真实死线） |
| E11 | 寿终判定 @609853 | 整段替换：`age ≥ deathLine` → 日志 + **一次性闩锁** + `Ui(...,"转世重修",...)` 清档链路 |
| E12 | 读档归一 @249385 | `lifespan:t.lifespan??…` → `...YlxwLifeMigrate(t),` |
| E13/E14 | 属性名表 @311750 / PILL_FX @1016013 | 文案改「年龄 / 寿元上限」；新增 `ageReduce` 标签 |
| E15 | 丹方 | 延寿丹 `lifespan:1` → `maxLifespan:3`；长生丹 `3` → **8**；不死仙丹 → **20**（去临时补寿）；**新增驻颜丹（−3 岁）/ 返春丹（−8 岁）** + `us` 懒取表 |
| E16 | 法宝死代码（**109 处**） | 删 `cost:{lifespan:N},` + 删「消耗N年寿命，」文案 + 删渲染分支（**不改任何实际数值**，因为它从未生效） |
| E17–E29 | 残留清理（13 处） | 死亡 useEffect 依赖数组 / R-219 nat 分支 / 传承返回 / 丹药 tooltip ×2 / `iy`·`ry` 缩放 / 法宝结算死逗号 / `Ic` 加寿保底 / 物品详情文案 / `sy()` 死映射 / 历练日志 ×2 |

### ★ E17 是本批**最关键的一处隐藏 bug**

`$w` 的死亡 `useEffect` 依赖数组原文是 `[t.hp, t.lifespan, ...]`。
若只改判定式而不改依赖数组，**`age` 变化不会触发 effect ⇒ 寿终永不判定**（年龄涨到死线也不死）。
已在 E17 修正为 `t.age`，并加了专门门禁 `E17 依赖数组新串在位/旧串清零`。

### ★ E11 的**双弹窗缺陷**（本地联调截图实测发现并修掉）

初版 E11 用 `l(!0)`（= `setIsDead(true)`）当「只处理一次」的闩锁。
后果：`isDead` 同时驱动**旧的「身死道消 / 涅槃重生」弹窗 `bk`** ⇒ 两个弹窗**叠层**，
玩家会看到旧弹窗压在「转世重修」背后（且旧弹窗带「涅槃重生」= 与「只能重开」语义冲突）。
**修法**：改用 `window.__ylR255Ended` 一次性闩锁，`isDead` 保持 `false` ⇒ `bk` 不再渲染。
复验：浏览器实测 `hasOldRebirth=false`（旧文案清零）、截图确认**单弹窗**。

### ★ 服务端半边（`srv_patch_r255.py`）

服务端**完全不参与寿命结算**（`lifespan`/`maxLifespan`/`寿元` 在该文件里出现 **0** 次）。
本环只改 `ALCHEMY_RECIPES` 两条**玩家可见** `summary`：

| key | 旧 | 新 |
|---|---|---|
| `yanshou` 延寿丹 | `服用 寿命+10年` | `服用 真实寿元+3年`（与客户端 `maxLifespan:3` 一致） |
| `jiuzhuan` 九转金丹 | `…永久 全属性+1000 寿命上限+1000年` | `…永久 全属性+1000 真实寿元+5年`（与客户端 `maxLifespan:5` 一致） |

★ 改前两条文案与客户端数值**长期脱节**（客户端实际 1 / 5）。
★ **只改 `summary`**：cost / minutes / rarity / unlockLevel / profGain / 配方 key / 炼丹枚数旁表**一律不碰**（4 条冻结门禁钉死）。
★ 本环门禁含 `全局·服务端「寿命」清零`（= 0），保证口径彻底统一。

---

## 2. 指纹（部署前后）

| 对象 | 上一版（0.9.60） | 本批（0.9.61） |
|---|---|---|
| `www/assets/index-v2960-20261011.js` | `dba25e79bf68085d004f74809c567b71` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2959-20261011.js` | `f649dc234f46844c0ebb5fdbb356b3d9` | 同左（0.9.59 定版，更早回滚点） |
| `www/assets/index-v2961-20261011.js` | —（新文件） | **`5e3c732e6a5e019d69a918c9de8f5fd1`**（2,343,809 B） |
| `server/index.ts` | `399bcae1e2896f221fcc6fa6b07c8ee6`（96 环） | **`bc623f3117529477157ebdbb413cac88`**（**97 环**，1,046,959 B） |
| `www/CHANGELOG.md` | `b3451660bdf70eb4b0ae9eec97cf20ca` | **`db61534c31586a139e90d5f6dfa87ada`** |
| `www/CHANGELOG_PLAYER.md` | `bd13ae4914f916f7d388f3831bdf77a3` | **`f01951faeeefabc253b6667a2ba56041`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（未变）** |

---

## 3. 部署前本地验收（全绿）

| 环节 | 命令 | 结果 |
|---|---|---|
| 补丁模块自检 | `python localtest/yl_r255_ext.py --src <copy>` | 门禁 **全绿**（含 29 条 EDITS + 13 条残留清理 + 4 条全局残留）、往返自证「除 E16 正则批量外逐字节回到基线」、`node --check` **OK**、`delta = -1632 B` |
| 语义真值表 | `node localtest/_r255_sem.js` | **ALL PASS 0 失败**（8 组断言 + 5000 组随机死线不越界） |
| 链式构建 | `python localtest/chain_build.py --all` | 97 环全过；`node --check rc=0`；bundle `5e3c732e…` / srv `bc623f31…` |
| 全量门禁 | `python localtest/dryrun_087.py` | **PASS（FAIL=0）**；standalone **2247 条**（r116~r255 共 92 脚本 gates()）；**预演产物 md5 == 交付产物 md5**（`5e3c732e…`） |
| 上游门禁同步 | 对交付产物重跑 `STANDALONE_CLIENT` 全部门禁 | **2153 → 2249 条，0 条被 R-255 打穿**（同步前 17 条 FAIL） |
| 浏览器实测（面板/存档） | `python localtest/t_r255_local.py` | **9/9 PASS**：面板「年龄 0 岁 · 寿元 90-100 岁」、无「寿命 (年)」、区间下限 = 上限×0.9 |
| 浏览器实测（端到端） | `python localtest/t_r255_death.py` | **9/9 PASS**：服务端存档含 `age/lifeRatio/lifeBonus` 且**无 `lifespan` 键**；`maxLifespan == lifeRatio × 100`；把 `age` 推到死线之上后重载 ⇒ 弹「寿元已尽 + **转世重修**」，**旧「涅槃重生」清零**，无 JS 错误 |
| 部署包预演 | `python localtest/sim_remote_check.py --script deploy_v28/remote_check_v2861.sh` | **OK=1163 / SKIP(远端专有)=15 / FAIL=0** |

---

## 4. 上游门禁同步（§22.5：不静默放宽）

R-255 改写了 9 个历史模块共同锚定的**寿命机制终态** ⇒ 按规矩把 17 条旧形态针脚升
**tuple 多形态合计计数** 或 **SUPERSEDED_BY_R255 过滤**（逐字原文与原因全部保留在各自文件内）：

| 模块 | 处理 | 旧形态（保留在文件内） | 终态断言移交 |
|---|---|---|---|
| `yl_r140_ext.py` | `SUPERSEDED_BY_R255`（3 条） | `R140-6g·不死仙丹已降` / `冻结·延寿丹未动` / `冻结·长生丹未动` | R-255 E15a/b/c |
| `yl_r140b_ext.py` | 移除 1 条（常量保留） | `冻结·maxLifespan 分支未动` | R-255 E7 |
| `yl_r161_ext.py` | `SUPERSEDED_BY_R255`（2 条） | `R161·旧寿元行未直接混发` / `冻结·寿元产地未动` | R-255 E3b |
| `yl_r179_ext.py` | 移除 2 条 | `R179·寿命真渲染-增加/减少` | R-255 E28/E29 |
| `yl_r206_ext.py` | tuple ×2 + `>=` ×1 | `MED_LIFE kept` / `settle kept` / `lifespanChange kept` | R-255 E2b/E3a |
| `yl_r239_ext.py` | tuple ×2 + `>=` ×1 | 同上 | 同上 |
| `yl_r219_ext.py` | `SUPERSEDED_BY_R255`（4 条） | `注入·自然寿终调用` / `E1·新串在位` / `E1·旧清档串清零` / `冻结·自然寿终非hard未动` | R-255 E11 |
| `patches/server/srv_patch_064.py` | tuple ×2（+ runner 支持 tuple needle） | 两条 summary 旧文案 | `srv_patch_r255.py` |
| `deploy_v28/remote_check_v2861.sh` | 就地改 5 条 + 注释留档 | `R179 寿命增加/减少` / `R239 MED_LIFE` / `settle` / `lifespanChange` | 同上 |

★ 全部为「**旧形态仍写在文件里**（注释或常量）+ 断言移交」，**无一处静默删除**。

---

## 5. 本批踩到的坑（可复用）

1. ★★ **`setIsDead(true)` 不能当寿终闩锁** —— 它会连带渲染旧死亡弹窗 `bk`，形成**双弹窗叠层**
   （且旧弹窗文案与新语义冲突）。**修法**：用 `window` 标记做一次性闩锁，`isDead` 保持 false。
   **教训**：改一个 `useEffect` 的判定逻辑前，先查「它 set 的 state 还被谁消费」。
2. ★★ **死亡 `useEffect` 的依赖数组必须与判定式同批改** —— 否则判定永不触发（静默失效、无报错）。
   本批已为它单列门禁。
3. ★★ **`Math.floor` 当展示区间上限会泄露隐藏值** —— 死线是小数（`ratio × U_base + bonus`），
   若区间上限取 `floor`，死线可能**大于展示上限** ⇒ 穿帮。**修法**：上限用 `Math.ceil`。
   这是语义测试（真值表）抓到的，**静态门禁查不出来**。
4. ★★ **老存档迁移的边界**：`maxLifespan < 0.9 × U_base` 的脏数据会让 `lifeBonus` 变**负数** ⇒
   破坏「死线 ∈ 区间」不变量。**修法**：`bonus = max(old − ratio×base, 0)`；效果是死线被**抬高**
   （对玩家有利），**绝不猝死**。已加 2 例边界断言。
5. ★ `sim_remote_check` 的 `$B` 从**脚本里的 `B=` 行**解析 ⇒ 机械重登记时必须同步改
   `B="index-v<ver>-${BUNDLE_DATE}.js"` 的**版本号字面**，否则模拟器拿**过期 bundle** 跑新断言
   ⇒ 爆一堆**假 FAIL**（本批实测：先爆 12 条，改 fully 后归零）。
6. ★ 机械重登记脚本要覆盖 `${BUNDLE_DATE}` 拼接形态（`BUNDLE="index-v2960-${BUNDLE_DATE}.js"`），
   纯整名替换会漏掉它（本批漏了 `deploy` 与 `remote_check` 各 1 处，已补）。

---

## 6. 回滚

```bash
# 回滚到 0.9.60（一条命令，旧包与旧 server 都在）
cp /root/backup/index-v2960-20261011.js.pre-v2961-<TS> /opt/yl/www/assets/
/usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2961-20261011.js --to=index-v2960-20261011.js
cp /root/backup/index.ts.pre-v2961-<TS> /opt/yl/server/index.ts
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版：bundle=dba25e79bf68085d004f74809c567b71  server=399bcae1e2896f221fcc6fa6b07c8ee6
```

★ 回滚注意：本批**无表结构变更**（服务端只改 `ALCHEMY_RECIPES` 的两条 `summary` 字面量，无 SQL、无新列）
⇒ 回滚**无需删列/删表**。

★ **存档兼容性（重要）**：本批把 `player.lifespan` 换成 `age/lifeRatio/lifeBonus`。
- **新档 → 旧代码**：旧代码读 `t.lifespan` 会得到 `undefined` ⇒ 旧版会把寿元当 `maxLifespan`
  并逐步扣减（回到「递减」口径），**不会崩**，但进度语义会变。
- **老档 → 新代码**：`YlxwLifeMigrate(t)` 做**幂等**一次性迁移
  （`age = 旧maxLifespan − 旧lifespan`、`lifeRatio = clamp(old/base, 0.9, 1)`、`lifeBonus = max(old − ratio×base, 0)`），
  有 `age` 即跳过 ⇒ **死线逐位保留、进度一点不丢**。
- ⇒ **若需回滚且要保老玩家体验，应同时回滚 `database/*.sqlite` 的对应时间点快照**（见下）。

---

## 7. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=5e3c732e6a5e019d69a918c9de8f5fd1
PREV_SRV_MD5=bc623f3117529477157ebdbb413cac88
PREV_CHANGELOG_MD5=db61534c31586a139e90d5f6dfa87ada
PREV_PLAYER_MD5=f01951faeeefabc253b6667a2ba56041
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=bc623f3117529477157ebdbb413cac88   # 链尾 _chainstage/s97.r255.ts（供单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
