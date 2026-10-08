# DEPLOY LOG — 《摸鱼修仙传》 0.9.39（v28 链 **87 → 88 环**｜**含服务端**批）

- **部署时间**：2026-10-08 17:14:58 ~ 17:16（GMT+8）｜★★ **重启了 yl-server**（秒级中断）
  `ActiveEnterTimestamp = Thu 2026-10-08 17:15:28 CST`｜`ActiveState = active`｜`NRestarts = 0`（人工 restart，非崩溃拉起）
- **目标**：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- **脚本**：`deploy_v28/deploy_v2839.sh`（**未加** `--skip-server`，正确）
- **定点核对**：`deploy_v28/remote_check_v2839.sh` → **PASS (0 failures)**，无 WARN
- **登记指纹**：`deploy_v28/EXPECT_0839.env`
- **备份整包**：`/root/backup/yl_pre_v2939_20261008_171458.tar.gz`（56,449,112 B）
- **DB 一致性快照**：`/root/backup/database_v2939_consistent_20261008_171458.sqlite`（12,607,488 B）
- ★★ 本批**服务端有变化**（87 → **88 环**：`s88.r207` = R-198 心法改经验制）⇒ **不能** `--skip-server`。

## 1. 本批范围：0.9.39 = **3 条**（客户端 3 补丁 + 服务端新增第 88 环）

| # | 台账号 | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|---|
| 1 | **R-198** | 心法学习改「**点一次加经验**」（不再每次升一级）+ 大幅提高单次灵石 | `localtest/yl_r207_ext.py` + `patches/server/srv_patch_r207.py` | ✔ | ✔（第 88 环） |
| 2 | **R-199** | 挂机历练寿命消耗下调 `0.02 → 0.005` | `localtest/yl_r206_ext.py` | ✔ | — |
| 3 | **R-208** | 历练结算「分档」标签改名 常态/几百/几千 → **寻常/丰厚/横财** | `localtest/yl_r208_ext.py` | ✔ | — |

- 客户端 `STANDALONE_CLIENT` **52 → 55 脚本**；服务端 **87 → 88 环**。
- ★ **编号说明**：台账号与补丁号是**两套已漂移的编号**，补丁一律取「下一个空闲号」。
  本批台账 **R-198 / R-199 / R-208** 对应补丁 **r207 / r206 / r208**（注意 **R-199 ↔ r206 不同号**，且 R-208 恰好同名）。

### 1.1 R-198 心法改经验制（**本批唯一动服务端的项**）

> 用户原话：「心法学习也变成点一次增加经验，不要每次升一级，并且大幅度提高点一次所需的灵石数量。」

- **取证**：用户说的「心法学习」= **「仙务 · 心法」六卷面板**（客户端 `YlxwTXinfa087`，注册 `YLXW_COMP.gongfa`），
  **由服务端权威**（`GET /api/gongfa` + `POST /api/gongfa/levelup`），点一次 = 扣灵石 → 等级 +1 ⇒ **必须改服务端**。
- **改法（最省事路径）**：`player_gongfa.exp` 语义**本来就是「累计投入灵石」**，且 `gongfaLevelFromExp()` 已存在
  ⇒ 把「扣满整级价 → `level+1`」改成「**扣按档单价 P → `exp += P` → 等级由 exp 反推**」，**无需新字段、无 DDL**。
- ★★ **数值口径（C 方案）**：用户两条要求存在数学约束 `单价倍数 × 每级点击数 = 满级总价`，**三者不可能都小**。
  优先满足「点一次加经验」（第一诉求）⇒
  - **阈值表 ×7.5**：`[2250, 3750, 6000, 9000, 15000, 22500, 37500, 60000, 90000, 150000]`（首项 300→2250）
  - **每次点击单价（按档）× 2.5**：`[750, 1250, 2000, 3000, 5000, 7500, 12500, 20000, 30000, 50000]`
  - ⇒ **每档点击数恒为 3.000**（十档全等，**不再有一键跨级**）；单价 **2.5×**；满级 528,000 → **3,960,000**（×7.5）
- **未动**：`GONGFA_MAX_LEVEL = 100`、六卷 key 集合、`player_gongfa` 表结构。
- **客户端配套**：进度条改读 `levelExp/levelNeed`；信息行「点一次消耗 P 灵石 · 本级进度 X/Y」；
  兜底两表与服务端**逐项一致**（防服务端不可达时 UI 漂移）。

### 1.2 R-199 挂机历练寿命下调（纯客户端）

- `var YLXW_LIFE_AUTO_MUL = 0.05` → **`0.0125`** ⇒ 挂机单次寿命消耗 `0.4 × 0.0125` = **0.005**（原 0.02）。
- **与用户实测精确对上**：用户数据「158 次掉 3.1 年」= **0.0196/次** ≈ 旧值 0.02 ✓；改后同样 158 次只掉 **≈ 0.79 年**。
- ★ **手动历练的 `0.4` 未动**（用户给的 0.02 对应的是**挂机**档）；挂机秘境 = 0.0125、手动秘境 = 1。

### 1.3 R-208 分档标签改名（纯客户端）

- `分档 常态 N · 几百 N · 几千 N` → **`分档 寻常 N · 丰厚 N · 横财 N`**
- ★ **只改渲染行那三个词**；**代码注释里的旧词逐字保留**（故门禁必须钉「渲染行」，不能全局钉旧词——见 §6.2）。

## 2. 指纹（部署前后）

| 对象 | 部署前（0.9.38） | 部署后（0.9.39） |
|---|---|---|
| `www/assets/index-v2936-20261008.js` | `649ef7c8ccb9886004a5d4427b709f87` | 同左（更早回滚点） |
| `www/assets/index-v2937-20261008.js` | `5a35630ea5914ab7f8b94a9f2bfb0686` | 同左（0.9.37 定版） |
| `www/assets/index-v2938-20261008.js` | `a4726c77b810c6b620b0604ce89cf9a7` | 同左（**0.9.38 定版 = 秒级回滚点**） |
| `www/assets/index-v2939-20261008.js` | —（新文件） | **`21a16b962a1ccedfc02c021b3bd2dc71`**（2,318,404 B） |
| `server/index.ts` | `b598eab621c6fe68f666f8ad7f19b847`（87 环） | **`2f49c2a7bc1b7348c2732912afe968ff`**（1,019,321 B / **88 环**） |
| `www/CHANGELOG.md` | `e5e99952fde6a4087c0cfff7f26dc1db` | **`be3ffc8b081882ec41fd27dcfe3ace58`**（回填上线时刻后） |
| `www/CHANGELOG_PLAYER.md` | `8153284cee6618d63b24346d335133da` | **`4c0c1b14b2e940f23e64fb0515535a4d`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（未变）** |

线上实测（部署后 SSH 直采，与本表逐字一致）：

```
2f49c2a7bc1b7348c2732912afe968ff  /opt/yl/server/index.ts          (1,019,321 B / 88 环)
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
be3ffc8b081882ec41fd27dcfe3ace58  /opt/yl/www/CHANGELOG.md
4c0c1b14b2e940f23e64fb0515535a4d  /opt/yl/www/CHANGELOG_PLAYER.md
21a16b962a1ccedfc02c021b3bd2dc71  /opt/yl/www/assets/index-v2939-20261008.js  (2,318,404 B)
```

**服务端链中间产物**（供单变量可核与排查）：

| 环 | 文件 | md5 | 大小 | 备注 |
|---|---|---|---|---|
| s20 | `s20.t16arena.ts` | `7780e099a6cd1ac0de4b502c467ae2c0` | 824,768 B | == 0.8.9 定版（前 20 环不变） |
| s84 | `s84.r194.ts` | `4cd3632ceebee7a50c6943d89da4c23d` | 1,011,716 B | == 0.9.34 定版 |
| s85 | `s85.r198.ts` | `8318e1c9fad3242364df7b3a585ca61f` | 1,016,800 B | == 0.9.35 定版 |
| s86 | `s86.r200.ts` | — | 1,016,633 B | R-192 去掉 R-167 当日首免 |
| s87 | `s87.r201.ts` | — | 1,017,257 B | R-193 渡劫门槛乘 K 表 ← == 0.9.37/0.9.38 定版 |
| **s88** | **`s88.r207.ts`** | **`2f49c2a7bc1b7348c2732912afe968ff`** | **1,019,321 B** | **R-198 心法改经验制 ← 链尾（本批新末环）** |

★ 三文件逐字节 IDENTICAL：`_chainstage/s88.r207.ts` == `srv/index_v28.ts` == `_chainstage/index_v28.v28112.ts`（均 `2f49c2a7…`）。

## 3. 部署前本地验收

- `chain_build.py --all`：**rc=0**（服务端链重建 87 → **88 环**；bundle `21a16b96…`）
- `dryrun_087.py`：**PASS（FAIL=0）**，standalone 门禁 **1557 条 / 67 脚本（r116~r208）**
- 「预演==交付」：`_chainstage/dryrun_087.bundle.js` md5 = `21a16b962a1ccedfc02c021b3bd2dc71` **== 交付产物** ✓
- `sim_remote_check.py --script deploy_v28/remote_check_v2839.sh` 本地预演：**OK=538 / SKIP(远端专有)=15 / FAIL=0**
- `bash -n` 两脚本 **OK**；`deploy_v2839.sh` / `remote_check_v2839.sh` / `EXPECT_0839.env`
  **CR 字节 = 0（纯 LF）/ 无 BOM / 以换行结尾** ✓
- ★ 远端基线预检 **5/5 逐字节命中**（bundle `a4726c77…` / 更早回滚点 `5a35630e…` / server `b598eab6…` /
  CHANGELOG `e5e99952…` / `index.html` 指向 v2938），且 v2939 新包**尚不存在**。

## 4. 线上验收

- `remote_check_v2839.sh` → **REMOTE-CHECK: PASS (0 failures)**，无 WARN（含本批 19 条新针：R207 ×5、R206 ×3、R208 ×2、服务端 R207 ×4、回归 ×4）
- 线上指纹全部命中（见 §2 表 + SSH 直采块）
- `index.html` 指向 **`index-v2939-20261008.js`**；★★ **gzip 硬断言**：`zcat index.html.gz | grep 新包 = 1` ✓（R-159 铁律）
- ★★ **服务已重启**：`ActiveState = active` / `ActiveEnterTimestamp = Thu 2026-10-08 17:15:28 CST` / `NRestarts = 0`
- 回滚点 **v2936 + v2937 + v2938 三包均在** ✓
- 公开冒烟：`index.html → 200`｜`bundle → 200`｜`api/gongfa`（未鉴权）`→ 401`（预期）；线上包内版本号 `0.9.39` ✓
- 双 CHANGELOG 已回填**实际上线时刻 17:15** 并重传；`EXPECT_0839.env` 已重登记（`CHANGELOG.md → be3ffc8b…`）

## 5. 本轮踩到的新坑 / 经验

1. ★★ **「值无关针」再次救场（本仓处理「后续补丁合法改写旧针」的标准手法）**：
   R-208 把渲染行的 `分档 常态 ` 改成 `分档 寻常 ` ⇒ `yl_r191_ext.py` 里钉 `\u5206\u6863 \u5e38\u6001 `（「分档 常态 」）的那条针**被打破**。
   因**表达式结构仍在**（行首前缀「分档 」不变）⇒ **收窄成值无关形态** `\u5206\u6863 `（只钉「分档 」前缀），
   三个新标签由 r208 自己的门禁负责。★ 判据：**形态还在、只是常量变了 ⇒ 收窄；形态整体消失 ⇒ 退役（`RETIRED_TAG`）**。
2. ★ **「只改渲染行、保留注释旧词」会让朴素门禁误判**：R-208 刻意只动渲染行那三个词，
   代码注释里的「常态/几百/几千」**逐字保留**（作历史说明）⇒ **不能全局 grep 旧词判 0**，
   必须钉**渲染行完整行**或**行首前缀**。（r208 的门禁即按「新标签 total / 旧标签 cleared」成对写。）
3. ★ **`EXPECT_0839.env` 的注释把 R-199 误写成「R-206」**（把**补丁号**当**台账号**用了）——
   纯注释、不影响任何断言（脚本只 source `EXPECT_*` 变量），**本批不动**；但提醒：写注释时别混用两套编号。
4. ★ **`sendMessage` 在团队被清理后仍会报「Not in a team」** ⇒ 接不上的成员要**新开**（本批 `r208` 就是新开的）。
5. ★ **`$'\r'` 在 Git Bash 里会展开成空串** ⇒ `grep -c $'\r' file` 得到的是**总行数**（伪 CRLF 告警）。
   判 CRLF 请用 `tr -cd '\r' < file | wc -c`，或直接 `od -c`。本批三件**实测 CR 字节 = 0**。

## 6. 本轮三项独立核验的结论（用户提供真实挂机数据后）

1. ★★ **灵石「几百」占 33% 的真因 = 当年建模漏了一条路**：自动历练有**两条路**（模板路 + **真实战斗路**），
   而 R-180 的设计与 30 万样本模拟**只建模了模板路**。战斗胜利固定给 `max(10, round(20×1.2))×10 = 240` 灵石（炼气 L1）
   ⇒ 正好落进 151~999「几百」档。混合估算 常态≈70% / 几百≈30% ⇒ 与实测 67/33 吻合；
   旁证：战斗胜修为 `round(75×1.2) = 90`，与实测均值 **+95** 吻合。
   **阈值/系数本身没问题**（模板路「几百」恒 ≤15%）。⇒ 要修得动**战斗路灵石**或**「几百」下界**，会跨到所有战斗 ⇒ **待拍板**。
2. **掉血不受幸运影响 —— 幸运项是死代码**：`Ym` 的 **3 个调用点全部只传 `{realm, realmLevel, maxHp}`，不传 `luck`**
   ⇒ `r.luck` 恒 `undefined` ⇒ `(r.luck||0) = 0`。故 `__ylPD = 0.4/(1-__ylVal)` 炼气 L1 恒 **42.1%**。
   实测 36% 偏低是因为该 roll **只对模板路判、战斗路不判**（`0.75 × 42.1% + 战斗败北 ≈ 39%`）。**不需要改**。
   （★ 主线曾一度误判「掉血仍在吃废弃的幸运」，经调用点复核**已推翻**。）
3. **天地之魄 0 次属预期**：其模板被 `Fm` 的闸门按**化神期**过滤 ⇒ 低于化神必为 0，不是 bug。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包
cp -a /root/backup/index.html.pre-v2939-20261008_171458 /opt/yl/www/index.html
# ★ index.html.gz 必须与明文同批重建（nginx gzip_static 铁律 R-159）
gzip -9 -kf -c /opt/yl/www/index.html > /opt/yl/www/index.html.gz
# 服务端回滚（本批服务端有变 ⇒ 必须回滚 index.ts 并重启）
cp -a /root/backup/index.ts.pre-v2939-20261008_171458        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2939-20261008_171458 /opt/yl/server/game-dicts.json
# 日志回滚
cp -a /root/backup/CHANGELOG.md.pre-v2939-20261008_171458        /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2939-20261008_171458 /opt/yl/www/CHANGELOG_PLAYER.md
systemctl restart yl-server && systemctl is-active yl-server
# 旧包文件未删，无需还原；如被误删：
#   cp -a /root/backup/index-v2938-20261008.js.pre-v2939-20261008_171458 /opt/yl/www/assets/
# 上一版定版（0.9.38）：bundle=a4726c77b810c6b620b0604ce89cf9a7  server=b598eab621c6fe68f666f8ad7f19b847
# 整包：/root/backup/yl_pre_v2939_20261008_171458.tar.gz
```

★ 回滚注意：本批**无 DDL**（`player_gongfa` 表结构未动），服务端只改 `levelup` 逻辑与两张常量表 ⇒
回滚 `index.ts` 并重启即完全还原；**DB 无需还原**（`exp` 语义未变，只是写入口径变了）。
★ 若需完全还原 DB：`/root/backup/database_v2939_consistent_20261008_171458.sqlite`（12,607,488 B）。

## 8. 0.9.39 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=5a35630ea5914ab7f8b94a9f2bfb0686      # 0.9.37 index-v2937-20261008.js（更早回滚点）
PREV_LIVE_BUNDLE_MD5=a4726c77b810c6b620b0604ce89cf9a7 # 0.9.38 index-v2938-20261008.js（本次部署前的线上包）
PREV_SRV_MD5=b598eab621c6fe68f666f8ad7f19b847         # 0.9.36/0.9.37/0.9.38 三版同 md5（87 环 = s87.r201.ts）★ 本批已变
PREV_CHANGELOG_MD5=e5e99952fde6a4087c0cfff7f26dc1db   # 0.9.38 CHANGELOG.md
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S20_MD5=7780e099a6cd1ac0de4b502c467ae2c0     # 0.8.9 定版 s20.t16arena.ts（前 20 环不变）
# 本版（0.9.39）新指纹：
#   bundle  21a16b962a1ccedfc02c021b3bd2dc71  (2,318,404 B)  index-v2939-20261008.js
#   server  2f49c2a7bc1b7348c2732912afe968ff  (1,019,321 B / 88 环)  ★ 与 0.9.36~0.9.38 不同
#   CHANGELOG.md        be3ffc8b081882ec41fd27dcfe3ace58
#   CHANGELOG_PLAYER.md 4c0c1b14b2e940f23e64fb0515535a4d
#   dicts    1b635513f553875060869272b790f910  (未变)
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
