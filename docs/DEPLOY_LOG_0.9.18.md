# 部署日志 · 0.9.18（2026-10-03）

> 本批 = **R-142 灵田稀有草属性接线** + **R-143 回合制技能吸血**，两条都是 **修 bug**。
> **纯客户端批**（服务端零改动，`--skip-server` 发布）。

---

## §1 本批范围

| 需求 | 类型 | 落点 | 规模 |
|---|---|---|---|
| **R-142** 灵田稀有草「白种」修复 | 修 bug | `localtest/yl_r142_ext.py` | 10 门禁 / +887 B |
| **R-143** 回合制技能吸血 | 修 bug | `localtest/yl_r143_ext.py` | 10 门禁 / +228 B |

**两个 bug 的根因（侦察结论）**

**R-142**：洞府灵田种出的稀有草，服用后服务端把暴击率 / 闪避 / 吸血写进存档玩家对象
（`srv/index_v28.ts` 约 8453-8465 行；在**百分点**上算、末尾 ÷100 落盘成小数比例，
上限由服务端 `FARM_CROP_ATTR_CAP = {hitRate:8, critRate:8, dodgeRate:6, lifeLeech:4}` 钳制）。
但**客户端战斗层从不读这三个玩家字段** ⇒ 死字段，玩家种出来的稀有属性完全无效。

**R-143**：回合制战斗里普攻 `km`（约 @779350）有吸血分支
（`r==="player" && _>0 && l.buffs.forEach(w => w.lifeLeech>0 && 回血 floor(_ × w.lifeLeech))`），
但技能 `zy`（约 @781185）**没有**吸血分支 ⇒ 技能伤害不回血。
后果：0.9.17 刚实装的「噬元」吸血词条，对技能流打法收益打对折。

**修法与设计取舍**

- **R-142**：在 `YlxwBattleBonus(p)` 的灵纹层 `YlxwR18bRuneBattle(o, p);` **之后**追加三行，
  把 `p.critRate / p.dodgeRate / p.lifeLeech` 累加进聚合对象 `o`。
  链路：`YlxwBattleBonus` → `YlxwSpellBuffs`（@1319606，转成 `{type:"crit", value, duration:9999}` 等 buff）
  → 注入回合制战斗玩家对象 `buffs`（@777152）→ `km`/`zy` 消费。**只改一处即全链生效。**
  末尾由既有 `YlxwBattleCap` 统一封顶（配置 `critRate 0.35 / dodgeRate 0.35 / lifeLeech 0.25`，
  远高于灵田上限 0.08 / 0.06 / 0.04 ⇒ **不会撞顶**）。
  ⚠️ **`hitRate` 不接线**：客户端产物里 `hitRate` grep = **0**，客户端战斗**没有命中率机制**、无消费点，
  不发明机制（脚本里有专门门禁断言补丁后 `hitRate` 仍为 0）。

- **R-143**：在 `zy` 的「伤害结算 + 反弹」段之后补一段吸血。两个刻意取舍：
  ① **仅 `r === "player"`** 生效（与 `km` 一致，敌方技能不吸血）；
  ② **取最强单条 `lifeLeech`（`Math.max`）而非像 `km` 那样 `forEach` 逐条回血** ——
     `km` 的写法在存在多条吸血 buff 时**会重复回血**；当前实际只有一条（`ylxw-rl`，来自 `YlxwSpellBuffs`），
     两者数值等价，但取最大值在将来新增吸血来源时不会叠加。

---

## §2 集成期改动（主控做的）

| 文件 | 改动 |
|---|---|
| `build_v26n.py` | `OUT` → `index-v2918-20261003.js`；`STANDALONE_CLIENT` 追加 `('r142', …)` / `('r143', …)`（序 = 编号序） |
| `localtest/dryrun_087.py` | `VERSION='0.9.18'`；`BUNDLE_BASENAME='index-v2918-20261003.js'`；standalone 门禁段补 2 个 import + 元组（550 → **570** 条）；文案 `r116~r143 共 24 脚本` |
| `patches/client/yl_version_ext.py` | `DEFAULT_VERSION` + `YLVERSION_FALLBACK` → 0.9.18；旧版本号滚动清零门禁新增 0.9.17 一条 |
| `build/index.html` | bundle 引用 → `index-v2918-20261003.js` |
| `localtest/chain_build.py` / `sim_remote_check.py` | 产物路径 → v2918 |
| `deploy_v28/deploy_v2811.sh` | `BUNDLE`/`OLD_BUNDLE`/`PREV_*`/备份命名（`pre-v2917-`→`pre-v2918-` 19 处等）/ 全部文案 |
| `deploy_v28/remote_check_v2811.sh` | 同上 + **新增「0.9.18 特征点」段 12 条 chk**；0.9.17 段降级为「历史批次回归」 |
| `deploy_v28/EXPECT_0811.env` | 全量重登记（见 §4） |
| `CHANGELOG.md` / `CHANGELOG_PLAYER.md` | 新增 `## [0.9.18] - 2026-10-03 12:30` 条目（玩家向用 `### 分类` 格式，符合解析器契约） |
| `_bump2918.py`（新建） | 升版主脚本，8 处落点全部带命中数断言，任一 miss 即 rc=2 不写盘 |

---

## §3 本地验收

### 3.1 两个 standalone 脚本（主控独立复验，非作者自报）

| 项 | R-142 | R-143 |
|---|---|---|
| 基线 md5 前置校验 | `0470077292…` ✓ | `0470077292…` ✓ |
| 门禁 | **10/10 PASS, FAIL 0** | **10/10 PASS, FAIL 0** |
| `node --check` | rc=0 | rc=0 |
| 幂等复跑 | rc=**3**（不写盘，md5 未变） | rc=**3**（不写盘，md5 未变） |
| 往返自证 | 新串→旧串 == 源，逐字节 | 同 |
| delta | +887 B | +228 B |

**串行叠加**（r142 → r143）：两者锚区零交集，`node --check` 通过，终态特征串各命中 1 次。

### 3.2 ★ 独立行为验证（主控自写 `_chainstage/_t_r142r143_beh.js`，改后 vs 基线反向对照）

> 另存 `_chainstage/_t_r143.py`（Python 版 R-143 抽取器）。

抽出真实产物里的函数体用 node 真跑（不是复算公式）：

| 用例 | 改后产物 | 基线产物（反向对照） |
|---|---|---|
| R-142 `{critRate:.06, dodgeRate:.04, lifeLeech:.02}` | `{0.06, 0.04, 0.02}` ✓ | `{0,0,0}` **FAIL** ✓ |
| R-142 `{}`（老存档无字段） | 全 0（与改前逐字节同，**零回归**） | 全 0 |
| R-142 `null` | 全 0，不抛异常 | 全 0 |
| R-142 超大值 `{critRate:9,…}` | 钳到 `0.35 / 0.35 / 0.25`（封顶生效） | `0 / 0 / 0`（未封顶）**FAIL** ✓ |
| R-143 玩家带吸血用技能 | hp **100 → 166**（dmg 220 × 0.3 = 66） ✓ | hp 100 → 100 **FAIL** ✓ |
| R-143 玩家不带吸血 | 100 → 100（零回归） | 100 → 100 |
| R-143 敌方带吸血用技能 | 1000 → 1000（**只对玩家**） | 1000 → 1000 |

> ★ 反向对照两列数字齐备 ⇒ 证明测试非空（skill §18.16 判据）。

### 3.3 全量预演与交付

| 项 | 结果 |
|---|---|
| `localtest/dryrun_087.py` | build 门禁 **4245 条 FAIL 0** + standalone **570 条 FAIL 0** |
| `build_v26n.py` | PASS |
| **预演 == 交付** | 双侧 md5 均 `7abf7b22308cfdba58312f21705a5e02`，**逐位一致** |
| `node --check`（交付产物） | OK |
| `localtest/sim_remote_check.py` | **OK=260 / SKIP(远端专有)=13 / FAIL=0** |

---

## §4 指纹表

| 对象 | 0.9.18（本批） | 0.9.17（PREV） |
|---|---|---|
| `www/assets/index-v2918-20261003.js` | `7abf7b22308cfdba58312f21705a5e02`（2,289,504 B） | — |
| `www/assets/index-v2917-20261003.js` | — | `0470077292ba4ca446f92897257e0c54` |
| `server/index.ts` | `664501929cecb41fd57e65d9d0c48872`（**零改动**，980,090 B） | 同 |
| `www/CHANGELOG.md` | `b992dc3c0fe201f410f34b92550cd541` | `37b01f9682cc406cf55e265da62102c8` |
| `www/CHANGELOG_PLAYER.md` | `86c41cf9d86045a4b45f659e2a80ac91` | — |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910`（未变） | 同 |

**回滚点**：`index-v2917-20261003.js`（0.9.17，旧包未删、公网 200）+ `index-v2916-20261003.js`（0.9.16，更早）

---

## §5 线上验收（2026-10-03 12:27 部署，12:28~12:31 复验）

**部署命令**：`bash deploy_v28/deploy_v2811.sh --skip-server`（后台，exit=0，51s；纯客户端批 ⇒ 不动服务端）

### 5.1 部署器自报

```
backup ok: /root/backup/yl_pre_v2918_20261003_122716.tar.gz
step 3 client: live_bump_bundle.js -> index.html 指向 index-v2918-20261003.js（旧包引用已清零 x0）
REMOTE-CHECK: PASS (0 failures)
```

### 5.2 ★ 公网双路核对（下载后算 md5，与本地交付物逐位比对）

| 对象 | 公网 md5 | 本地 md5 | 结果 |
|---|---|---|---|
| `myxxz/assets/index-v2918-20261003.js` | `7abf7b22308cfdba58312f21705a5e02`（2,289,504 B） | 同 | ✓ 逐位一致 |
| `myxxz/CHANGELOG.md` | `b992dc3c0fe201f410f34b92550cd541` | 同 | ✓ |
| `myxxz/CHANGELOG_PLAYER.md` | `86c41cf9d86045a4b45f659e2a80ac91` | 同 | ✓ |
| `myxxz/` 首页 index.html 引用 | `index-v2918-20261003.js`（唯一） | — | ✓ 旧包引用清零 |

线上 `www/` 侧 md5（SSH 直读）：bundle / CHANGELOG / CHANGELOG_PLAYER **全部与本地逐位一致**。
线上 `index.html` md5 `424770b1c971133deaa3ec750c51a159` ≠ 本地 `c0c412f5…`，**属预期**：
`live_bump_bundle.js` 会在服务端注入平台块 —— `diff` 确认差异**仅两处**：
① 资源路径 `./assets/` → `/myxxz/assets/`；② 末尾注入 `unified-stats.js` + `mw-reward` 脚本块。除此之外零差异。

### 5.3 特征串抽查（公网 bundle）

`YLXW_R142_V2918` = **1**；`YLXW_R143_V2918` = **1**（各恰一处，无重复注入）。

### 5.4 服务健康

| 项 | 值 |
|---|---|
| `systemctl is-active yl-server` | **active** |
| `NRestarts` | **0** |
| `ActiveEnterTimestamp` | Sat 2026-10-03 09:17:49 CST |
| `MainPID` | 476193 |
| maintenance flag | absent |

> 注：服务**未重启**（纯客户端批），`ActiveEnterTimestamp` 仍是今早 09:17 服务端批次的时间。

### 5.5 线上库核对（node 只读，`better-sqlite3`）

8 张 0.8.7 新表全部在位：`farm_daily_care` / `activity_rank_settled` / `activity_checkin` / `activity_token` /
`activity_token_daily` / `event_boss` / `event_boss_hits` / `sect_applications`；
6 列全部落库：`sects.join_mode`、`pets.merged`、`pets.merge_pity`、`pets.sub_consumed`、
`gm_sessions.expires_at`、`users.muted_until`。**全 [OK]。**

### 5.6 公开冒烟与判活探针

| 探针 | 期望 | 实测 |
|---|---|---|
| `GET /myxxz/` | 200 | 200 |
| `GET /myxxz/CHANGELOG.md` | 200 | 200 |
| `GET /myxxz/assets/index-v2918-…js` | 200 | 200 |
| `GET /myxxz/assets/index-v2917-…js`（回滚点） | 200 | 200 |
| `GET /myxxz/assets/index-v2916-…js`（更早回滚点） | 200 | 200 |
| `GET /myxxz/api/snapshots` | 401 | 401 |
| `GET /myxxz/api/arena/week` | 401 | 401 |
| `GET /myxxz/api/gongfa` | 401 | 401 |

### 5.7 备份清单（`/root/backup/`，时间戳 `20261003_122716`）

`yl_pre_v2918_20261003_122716.tar.gz`（42.6 MB 全量）+
`index.html` / `CHANGELOG.md` / `CHANGELOG_PLAYER.md` / `index.ts` / `game-dicts.json` / `database.sqlite` /
`index-v2917-20261003.js`（2288389 B）各自 `.pre-v2918-20261003_122716` 副本 +
`database_v2918_consistent_20261003_122716.sqlite`。

**结论：线上验收全绿，0 failures。**

---

## §6 本批踩到的坑

1. **`remote_check_v2811.sh` 是「远端侧脚本」，不能在本地跑** —— 本地直接 `bash deploy_v28/remote_check_v2811.sh`
   会打印 `MISSING /opt/yl/www/assets/index-v2918-…js`（因为它读的是服务器绝对路径）。
   正确姿势：`scp` 到 `/opt/yl/server/_remote_check_v2811.sh` 后经 SSH 带两个参数执行
   （`<bundle 绝对路径> <server 绝对路径>`），或直接靠 `deploy_v2811.sh` 第 384-385 行自动完成。
2. **站点路径是 `/myxxz/`，不是 `/yl/`** —— 直接 `curl https://moyuwang.online/yl/` 会 301 到 `/myxxz/`。
   核对时一律走 `https://moyuwang.online/myxxz/`。旧断言 `'/yl/CHANGELOG.md' eq 0` 正是这个原因（旧入口必须清零）。
3. **服务名是 `yl-server`，不是 `yl`** —— `systemctl is-active yl` 返回 `inactive` 是假象（无此 unit），
   真名 `yl-server`。核对脚本第 513 行已写死正确名。
4. **沙箱 shell 对 `${var%% *}` 参数展开报 `Bad substitution`** —— 复合参数展开偶发被拒，
   拆成逐条字面量命令即可（本批复验已改用逐条写法）。
5. **`node` 只读核对线上库依赖 `better-sqlite3` 驱动** —— 远端 `/opt/yl/server/node_modules` 里已有，
   无驱动时核对脚本会直接 FAIL（设计如此，避免静默跳过）。

---

## §7 回滚

```bash
# 回滚到 0.9.17
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@47.243.x.x \
  "cd /opt/yl/www && sed -i 's|assets/index-v2918-20261003.js|assets/index-v2917-20261003.js|g' index.html && \
   cp /root/backup/CHANGELOG.md.pre-v2918-<TS> CHANGELOG.md"
```
纯客户端批 ⇒ **不需要** restart 服务端。新 bundle 文件保留不删（未来回滚点）。
新版本期间玩家存档里的 `innateAffixes` / `permGain` 等字段对旧代码无害（旧代码忽略）。

---

## §8 定版指纹（0.9.18 线上终态）

| 对象 | md5 | 备注 |
|---|---|---|
| `www/assets/index-v2918-20261003.js` | `7abf7b22308cfdba58312f21705a5e02` | 2,289,504 B；公网 == 线上 == 本地 |
| `www/CHANGELOG.md` | `b992dc3c0fe201f410f34b92550cd541` | 公网 == 线上 == 本地 |
| `www/CHANGELOG_PLAYER.md` | `86c41cf9d86045a4b45f659e2a80ac91` | 公网 == 线上 == 本地 |
| `www/index.html`（线上） | `424770b1c971133deaa3ec750c51a159` | 含平台注入块；本地版 `c0c412f5…` |
| `server/index.ts` | `664501929cecb41fd57e65d9d0c48872` | **零改动**，980,090 B |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 未变，1,300,048 B |

**回滚点**：`index-v2917-20261003.js`（`0470077292ba4ca446f92897257e0c54`，公网 200）→ 更早 `index-v2916-20261003.js`
**备份**：`/root/backup/yl_pre_v2918_20261003_122716.tar.gz`（42.6 MB）
**上线时刻**：2026-10-03 12:27（CST）；部署器 `REMOTE-CHECK: PASS (0 failures)`
**定版状态**：**已上线并复验通过**（公网双路 + 服务健康 + 线上库 + 冒烟探针，全绿）
