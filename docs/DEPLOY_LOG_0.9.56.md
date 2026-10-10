# DEPLOY LOG — 《摸鱼修仙传》 0.9.56

- 部署时间：2026-10-11 00:19 (GMT+8)
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2856.sh`（**纯客户端批** ⇒ `--skip-server`，**零停机**）
- 定点核对：`deploy_v28/remote_check_v2856.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0856.env`
- 备份整包：`/root/backup/yl_pre_v2956_20261011_001802.tar.gz`
- DB 一致性快照：`/root/backup/database_v2956_consistent_20261011_001802.sqlite`

---

## 1. 本批范围（0.9.56；客户端 3 模块 + 服务端 93 环**不变**）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-243 | 打坐侧 3 机制消费钩子（批 1b） | `localtest/yl_r243_ext.py` → 注册 `('r243', …)`（**排 r241 之后**）| ✅ 1 模块 | — 零改动 |
| R-244 | 体术 89 部数据层 + 叠加软上限（批 2） | `localtest/yl_r244_ext.py` → 注册 `('r244', …)` | ✅ 1 模块 | — 零改动 |
| R-245 | 战斗侧 4 机制消费钩子（批 2） | `localtest/yl_r245_ext.py` → 注册 `('r245', …)`（**排 r244 之后**）| ✅ 1 模块 | — 零改动 |

**R-243**：心法在 0.9.55 只写了**机制数据**（`yl_r240_ext.py` 的 `is[]` mental 段），**没有消费方**
⇒ 面板承诺的机制不生效。本环补消费方，读 `effects` 的 `wudaoRate` / `breathHeal` / `spiritGain`：
顿悟率**乘性** `p = p_base × (1 + wudaoRate)`（叠加在 R-241 的乘性概率式之上）、吐纳回血 `N += breathHeal`、聚灵 `stones += spiritGain`（定额，不乘 `stoneMul`）。

**R-244**：`is[]` body 段 89 部按新设计表重写属性/机制/描述（**`id` 与 `spiritualRoot` 一字未改**）；
黄≈60 / 玄≈160 / 地≈400 / 天≈1000 当量，同品级总当量相等、**机制强则属性略降**。
因体术**保持叠加、不做可切换**，新增**分属性软上限（方案 A）**：
`cap(v,C) = v<=C ? v : C + (v-C)×0.30`，C = 攻击 6000 / 防御 3000 / 气血 8000 / 速度 1800 / 根骨 800 / 神识 500。
★ 实测：全 89 部叠加 **攻击 13517 → 8255.1**（超出 7517 × 30%）；软上限**只作用于体术侧累加器 `_r244b`**，
心法贡献在其后相加 ⇒ 六源不受影响（已在产物上逐点核对）。

**R-245**：战斗侧 4 机制 —— **反震**（复用 bundle **既有** `reflectDamage` 通道，bundle 里已有 19 处）、
**连击** `comboRate`、**斩杀**（敌血 <30% 增伤）`executeRate`、**破甲** `armorPenRate`。
覆盖三条战斗路径：回合制 `km`、技能 `zy`、历练快速结算（`YlxwBattleBonus`）。

## 2. 指纹（部署前后）

| 对象 | 上一版（部署前） | 本批（部署后） |
|---|---|---|
| `www/assets/index-v2955-20261010.js` | `77d35f9c7a1570308cee19c319348e6a` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2954-20261010.js` | `aa49623854fad1bbe22f6ab3076b804f` | 同左（0.9.54 定版，更早的回滚点） |
| `www/assets/index-v2956-20261010.js` | —（新文件） | `6fc3c750d147aa314e3a9433a6c9385e` |
| `server/index.ts` | `328170ededb61fe3289845cb91d3419d` | `328170ededb61fe3289845cb91d3419d`（**未变**） |
| `www/CHANGELOG.md` | `8b51a980be81aebeb621311a0757fc3e` | `39e7a8ad964c63756d6f5a8b0c54f8d7` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | `1b635513f553875060869272b790f910`（本批不变） |

部署后线上实测（deploy_v2856.sh 采集）：

```
328170ededb61fe3289845cb91d3419d  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
39e7a8ad964c63756d6f5a8b0c54f8d7  /opt/yl/www/CHANGELOG.md
6fc3c750d147aa314e3a9433a6c9385e  /opt/yl/www/assets/index-v2956-20261010.js
```

## 3. 部署前本地验收

- `_bump_0856.py`：八处同改，预检 + 落盘 + 复核全 OK。
- `localtest/dryrun_087.py` → 门禁 **4338 条 / FAIL 0**；「预演 == 交付」md5 一致 = `6fc3c750…`（step 0c 已过）。
- `localtest/sim_r231_inject.py --new 0.9.56 --prev 0.9.55` → **FAILS=0**。
- `localtest/sim_remote_check.py --script deploy_v28/remote_check_v2856.sh` → **OK=931 / SKIP=15 / FAIL=0**。
- 三件套 `bash -n` 双绿；纯 LF / 无 BOM / 换行结尾。
- `chain_build.py --all`：前端 `6fc3c750…`、服务端 `328170ed…`（**未变**，93 环，链尾 `s93.r233.ts`）、
  dicts `1b635513…`；链 `s20.t16arena.ts` == `7780e099a6cd1ac0de4b502c467ae2c0`（前 20 环 == 0.8.9 定版）。
- `build_v26n.py` 产物 md5 == 预演 md5（**「预演 == 交付」成立**）。
- 交付产物上复验：三补丁**幂等 rc=3**；标记 `r243hook` / `r244body` / `r245combat` 各 1 处。

## 4. 线上验收

- `deploy_v2856.sh --skip-server` 内建核对 + 远端 `_remote_check_v2856.sh` → **REMOTE-CHECK: PASS (0 failures)**。
- 公开冒烟：`GET /myxxz/` → **200**；`GET /myxxz/assets/index-v2956-20261010.js` → **200**；未授权 API → **401**。
- 远端 `CHANGELOG_PLAYER.md` md5 == 本地（`33bc3dd2efc6fe01af8ede77589fc251`），顶部条目即 `[0.9.56]`。
- 远端 `CHANGELOG.md` md5 == 本地（`39e7a8ad964c63756d6f5a8b0c54f8d7`）。
- `systemctl is-active yl-server` = **active**（`--skip-server` ⇒ **未重启、零停机**）。
- ★ 数据库变更：**本批无数据库变更**。

## 5. 本轮踩到的新坑（**全部属「跨补丁门禁演进」家族**）

1. **★★ 字段名不匹配 ⇒ 机制静默失效**（并行子代理各写各的，接口没对齐）：
   R-244（数据方）写 `reflectDamage` / `armorPenRate`，R-245（消费方）却读 `reflectRate` / `armorPen`
   ⇒ **反震与破甲读不到值**。裁定**对齐到 bundle 既有约定**：实测 `reflectDamage` 在 bundle 里**已有 19 处**
   （是技能 buff 的既有字段，形如 `effect:{buff:{reflectDamage:.3,duration:4}}`），
   且策划 §2.3 明确「优先选能落到现有钩子上的机制」⇒ 让消费方改用既有名，而非新造。
   ★ 教训：**并行工单之间的接口（字段名/结构）必须在派单时就冻结**，否则两侧各自「自洽」但拼不起来。
2. **★ 重复造轮子 + 双重生效**：`km` 既有链与 `zy` 既有块**都已在消费 `reflectDamage`**。
   R-245 原先把 `w.reflectRate…` 追加进 km 链（改名后会与锚点逐字重复、门禁计数 1→2），
   又给 zy 加了独立读取（会与既有块叠加成 **2×**）⇒ **两处都删**：反震改由
   「R-245 的 E2 把功法 `effects` 汇总推成 buff → 既有链/块消费」；仅**历练 fast 路径**需保留
   （`YlxwBattleBonus` 原本确无此字段）。
3. **★★ dryrun 的 standalone 门禁名单止步 r212**（r239~r242 当年漏登记）⇒ 新补丁**合法改写上游冻结项**时
   **查不出来**（补丁按序套用，轮到上游时下游还没生效，其 gates 在「套用时刻」必然通过）。
   已按「名单严格以 `build_v26n.STANDALONE_CLIENT` 为准」的既有意图补登记 **r239 / r241 / r242 / r243**
   （**只收 0 参 `gates()` 契约者**；r240/r244/r245 的 `gates()` 带参、属「段落前后比对」型自检，对最终形态重跑无意义 ⇒ 不收）。
   ★ **补登记立刻见效**：揪出 **`R241-A luck rate`** —— R-243 把概率式包成
   `…*0.005))*(1+YlxwArtMech(a,"wudaoRate")))` ⇒ R-241 原针 `*0.005)))` 归零。已改 tuple 两形态。
   同时 R188v2 三条退役针由**两形态**升级为**三形态** tuple（R-221 / R-241 / R-241+r243）。
   ⇒ 同一类事故**已连续三批**（0.9.54 的 R-139/R-206、0.9.55 的 R165/R188v2、本批的 R241/R188v2）
   ★ **建议**：把「冻结针脚被下游改写」变成**可自动暴露**的机制（例如：升版时对所有 gates 做一次
   「基座 vs 终态」双跑比对，或给每条针脚登记「归属补丁」以便自动定位责任人），而不是靠人记得补名单。
4. **remote_check 的 chk 同源问题**：`_mk_2856.py` 的 `RETIRE_CHK` 退役 1 条
   `R241 客户端 · 气运折算 0.5%/点 就位`（同因：`*0.005)))` 归零）。★ **退役 ≠ 放宽**：
   新形态由本批 **R243 段重新断言**（`*(1+YlxwArtMech(a,"wudaoRate")))/*[r241enl]*/` eq 1）。

## 6. 残留清理

远端 `_remote_check_v2856.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` 留在 `/opt/yl/server/` 便于复跑。
本地沙箱（`localtest/_r24x_sandbox/`）已 gitignore，提交前可删。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2956-20261011_001802 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2956-20261010.js --to=index-v2955-20261010.js
cp -a /root/backup/index.ts.pre-v2956-20261011_001802        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2956-20261011_001802 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2956-20261011_001802    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2955-20261010.js.pre-v2956-20261011_001802 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版：bundle=77d35f9c7a1570308cee19c319348e6a  server=328170ededb61fe3289845cb91d3419d
# 整包：/root/backup/yl_pre_v2956_20261011_001802.tar.gz
```

★ 回滚注意：数据库变更（若有）见 §4。回滚到上一版时**无需删列 / 删表**
（旧代码不读多余列，多余列无害）；**如需完全还原**用
`/root/backup/database_v2956_consistent_20261011_001802.sqlite` 热拷贝。

## 8. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=6fc3c750d147aa314e3a9433a6c9385e
PREV_SRV_MD5=328170ededb61fe3289845cb91d3419d
PREV_CHANGELOG_MD5=39e7a8ad964c63756d6f5a8b0c54f8d7
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_PLAYER_MD5=33bc3dd2efc6fe01af8ede77589fc251
PREV_SRV_CHAIN_TAIL_MD5=328170ededb61fe3289845cb91d3419d   # 链尾 _chainstage/s93.r233.ts（供单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
~/.ai-memory/topics/项目-摸鱼修仙传.md「当前版本」段。
