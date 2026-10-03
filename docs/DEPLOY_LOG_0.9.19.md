# DEPLOY LOG — 《摸鱼修仙传》 0.9.19 (v2919)

- 部署时间：2026-10-03 23:00 (GMT+8)
- 目标：香港 VPS `47.243.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2811.sh --skip-server`（**纯客户端批**：客户端 + CHANGELOG + index.html bump；服务端零改动）
- 定点核对：`deploy_v28/remote_check_v2811.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0811.env`
- 备份整包：`/root/backup/yl_pre_v2919_20261003_225944.tar.gz`
- DB 一致性快照：`/root/backup/database_v2919_consistent_20261003_225944.sqlite`

---

## 1. 本批范围：0.9.19（客户端 95 模块 + standalone 27 脚本；服务端 0 改动）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-140 | 丹药永久加成硬顶比例 `YLXW_R140_PERM_CAP_RATIO` `1.0 → 2.0`（用户拍板「松一点」）；专职丹保留 | standalone `yl_r140b_ext.py`（原位调参） | ✔ | — |
| R-141 | 装备天生词条重构：①稀有池收窄为 **4 类**（暴击率/暴击伤害/闪避/吸血）；②攻%/防%/气血% 移出稀有池、改「**随机属性条**」（1~3 条随机、类型/数值/条数随机、**所有品质含普通**）；③稀有封顶 **≤80%**（`YlxwBattleCapCfg.critDamage 1.0→0.8`）；④攻/防/气血% **不封顶** | standalone `yl_r141_ext.py` + V28 `yl_numbal_ext.py`（封顶表） | ✔ | — |
| R-144 | 右上角「在线 N」徽章 → `button` + 覆盖层「在线人物 · 好友」（在线人物 / 好友 两页签；好友支持加/赠灵石/删） | standalone `yl_r144_ext.py` | ✔ | — |
| R-145 | 自动历练灵石收益 `×5 → ×10`（2 倍）+ 零灵石兜底 `min(50,max(1,floor(修为×0.5)))` | standalone `yl_r145_ext.py` | ✔ | — |
| R-146 | 自动历练结算展示：同帧微批**合并成一条** + 按文本**去重** + type 取最高优先级 | standalone `yl_r146_ext.py` | ✔ | — |
| R-147 | 待拍板**固定格式页**生成器（工具链，**不随包上线**） | `D:/AIWorkspaces/req-ledger/build_待拍板.py` | — | — |

★ **本批为纯客户端批** ⇒ `--skip-server` 发布；`SRV_CHAIN` 仍 66 环，链尾 `s66.r136.ts`，
md5 与 0.9.16 / 0.9.17 / 0.9.18 定版**逐位相同**（`664501929cecb41fd57e65d9d0c48872`）。

★ **R-144「真实在线玩家名单」已移出本批** ⇒ 排入 0.9.20。
  用户 2026-10-03 22:40 拍板：要真实在线名单，并接上游戏自带多人功能（加好友 / 拜师 / 演武场）。
  需**服务端新接口**（按最近活跃时间维护在线集合）⇒ 0.9.20 必须走服务端链重建批，不能 `--skip-server`。

### 1.1 二轮拍板折叠（上线前插入）

用户在 22:34 导出 `C:/Users/27026/.oci/待拍板决定_2026-10-03.md`（14 项已选 13 项），
本批在**上线前**把新决定折进同一批（未另开版本）：
- R-141 二次重构（上表）——由一轮的「7 类词条池 + 三类独立区间表」改为「4 类稀有池 + 随机属性条」
- R-145 `×15 → ×10`（用户「X5 改成 X10 就行」）
- R-140 / R-142 / R-143 / R-146 **保持现状**
- 拍板记录：`D:/Personal/Documents/需求台账/拍板/2026-10-03_2240_0.9.19二轮拍板答复.md`

## 2. 指纹（部署前后）

| 对象 | 0.9.18（部署前） | 0.9.19（部署后） |
|---|---|---|
| `www/assets/index-v2919-20261003.js` | —（新文件） | `c02350f26d1d65c35e1640748901a466` |
| `www/assets/index-v2918-20261003.js` | `7abf7b22308cfdba58312f21705a5e02` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2917-20261003.js` | `0470077292ba4ca446f92897257e0c54` | 同左（更早的回滚点） |
| `server/index.ts` | `664501929cecb41fd57e65d9d0c48872` | 同左（本批未动） |
| `www/CHANGELOG.md` | `b992dc3c0fe201f410f34b92550cd541` | `b3939a1b69f3e518ac61192884dda52f` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批未动） |

部署后线上实测（ssh 独立复核）：

```
c02350f26d1d65c35e1640748901a466  /opt/yl/www/assets/index-v2919-20261003.js
7abf7b22308cfdba58312f21705a5e02  /opt/yl/www/assets/index-v2918-20261003.js
b3939a1b69f3e518ac61192884dda52f  /opt/yl/www/CHANGELOG.md
664501929cecb41fd57e65d9d0c48872  /opt/yl/server/index.ts
```

公网双路（`curl`）：

```
index.html 引用        : index-v2919-20261003.js
/assets/index-v2919... : 200
/assets/index-v2918... : 200（回滚点保留）
CHANGELOG.md 头         : ## [0.9.19] - 2026-10-03 23:00
bundle 内版本号         : YLVERSION_FALLBACK = "0.9.19"
systemctl is-active     : active
```

## 3. 部署前本地验收

- `python build_v26n.py` → `build/assets/index-v2919-20261003.js`（2,298,659 B，md5 `c02350f26d1d65c35e1640748901a466`）
  - V28_MODULES 95 模块 + **standalone 27 脚本**（新增 r144/r145/r146）**全部 rc ∈ {0,3}**
  - `node --check` rc=0
- `python localtest/dryrun_087.py` → **门禁 PASS（FAIL=0）**，standalone **619 条** FAIL 0，
  且预演产物 `_chainstage/dryrun_087.bundle.js` 的 md5 **== 交付产物 md5** ⇒ **「预演==交付」成立**
- `python localtest/sim_remote_check.py` → **OK=299 / SKIP(远端专有)=13 / FAIL=0**
  （★ 本批新增特征断言后，此处曾抓出 2 处预期值写错：攻/防是两个不同键
  `attackPercent` / `defensePercent`，误写成 `attackPercent` `eq 2` ⇒ 已订正）
- `deploy_v2811.sh` step 0/0b/0c 全过（EXPECT 指纹比对 + 双 provenance 自证）

## 4. 线上验收

- `remote_check_v2811.sh` → **PASS (0 failures)**
- 服务健康：`systemctl is-active yl-server = active`；`NRestarts: 0`；maintenance flag absent
- 线上库核对：0.8.7 的 8 张表 + `sects.join_mode` + 0.8.9 `pets` 三列 + 0.8.11 两新列
  （`gm_sessions.expires_at` / `users.muted_until`）全部在位
- 公开冒烟：见 §2「公网双路」

★ 本批**零新表、零新列、零新端点**（纯客户端），故线上库核对沿用既有清单、无新增项。

## 5. 本轮踩到的新坑（★ 重要，后续批次必看）

### 5.1 standalone 锚点建在「冻结基座原形」上 ⇒ 集成期必然 rc=2（假绿）

`yl_r145_ext.py` / `yl_r146_ext.py` 的锚点是在**冻结基座** `index-v26m-20260927.js` 上实测的，
但真实装配产物里这两处**早已被更早的 V28 模块改写**：
- `Ym()` 被 r114 改了 4 处：加第 3 参 `_ylm`、境界倍率表 `[1,1.6,2.56,…]` → `[1,1.236928,1.529991,…]`、
  `hpChange` 走 `t.hpChange<0?Math.floor(t.hpChange*u*0.25):…`、灵石字段外包 `*5*(_ylm==null?1:_ylm)`；
- `Fg()` 体内被插入了 `YlxwInhStoneRoll(t,m);`。

⇒ 子代理「实测 rc=0 / 门禁 PASS」是在**冻结基座**上跑的，属**假绿**；一集成必 rc=2。
**规矩**：standalone 的锚点必须按**装配态产物**形态书写；**验证基座必须是真实装配产物**。
**可复用技巧**：上一批构建留下的 `.bak-<tag>-<时刻>` **就是该模块的改前态**，可直接当测试基座。

### 5.2 `EXPECT_0811.env` 的 `PREV_*` 会**覆盖** `deploy_v2811.sh` 的内联值

`deploy_v2811.sh:184` 顶层 `. "$HERE/EXPECT_0811.env"` ⇒ 本文件里的 `PREV_*` 会盖掉脚本第 88-92 行的内联值。
0.9.18 时两边恰好一致所以从未暴露；本批升版只改了内联值 ⇒ **若不连 EXPECT 的 `PREV_*` 一起改，
step 0b「远端未漂移」断言必 ABORT**。
**规矩**：重登记 EXPECT 时，`PREV_*` 必须与 deploy 内联值**逐字一致**（本批已在 EXPECT 头部写明）。

### 5.3 `sim_remote_check.py` 是部署前唯一能拦住「特征断言预期值写错」的闸

本批新增 R-141 特征断言时，把 `attackPercent: [0.01, 0.05]` 写成 `eq 2`（以为攻/防共用一个键），
实际**玄甲用的是 `defensePercent`** ⇒ 被 `sim_remote_check` 抓出 2 处 FAIL。
**规矩**：新增/修改 `remote_check_v2811.sh` 的特征断言后，**必须跑 `localtest/sim_remote_check.py`**。

### 5.4 V28 模块的「冻结门禁串」改动是连锁的

改 `yl_numbal_ext.py` 的 `YlxwBattleCapCfg`（V28 模块）会连带打掉 3 处冻结门禁：
`yl_bond_ext.py` 的战斗层封顶门禁、`yl_r141_ext.py` 与 `yl_r142_ext.py` 的 `FRZ_CAPCFG`。
必须**同一批同步**，否则 dryrun 门禁必 FAIL。

### 5.5 既有小瑕疵（非本批引入，留作后续）

`YlxwInnate_Roll` 在**炼气期 + 稀有品质**下有约 26% 概率把 `value` 舍入为 `0`
（旧版同公式亦有，约 15%；本批因「所有品质都给随机属性条」而放大了触发面）。
表现为个别装备出现 `+0%` 的属性条。属既有公式低境界舍入问题，未在本批改公式。

## 6. 残留清理

远端 `_remote_check_v2811.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` 留在 `/opt/yl/server/` 便于复跑。
本地 `yl-deploy/_v2919_stage/` 为临时测试目录，已清理。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@47.243.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2919-20261003_225944 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2919-20261003.js --to=index-v2918-20261003.js
cp -a /root/backup/index.ts.pre-v2919-20261003_225944        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2919-20261003_225944 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2919-20261003_225944    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2918-20261003.js.pre-v2919-20261003_225944 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 0.9.18 定版：bundle=7abf7b22308cfdba58312f21705a5e02  server=664501929cecb41fd57e65d9d0c48872
# 整包：/root/backup/yl_pre_v2919_20261003_225944.tar.gz
```

★ 回滚注意：本批**零 DDL、零新列、零数据行迁移** ⇒ 回滚**无需任何数据库动作**，
`index.html` 指回 `index-v2918-20261003.js` 即可（服务端 `index.ts` 本批未动，甚至无需还原）。

## 8. 0.9.19 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=c02350f26d1d65c35e1640748901a466        # 0.9.19 定版 index-v2919-20261003.js（线上在跑）
PREV_PREV_BUNDLE_MD5=7abf7b22308cfdba58312f21705a5e02   # 0.9.18 定版 index-v2918-20261003.js（更早的回滚点）
PREV_PREV2_BUNDLE_MD5=0470077292ba4ca446f92897257e0c54  # 0.9.17 定版 index-v2917-20261003.js
PREV_SRV_MD5=664501929cecb41fd57e65d9d0c48872           # 链尾 s66.r136.ts（0.9.16 起未变）
PREV_CHANGELOG_MD5=b3939a1b69f3e518ac61192884dda52f
PREV_DICTS_MD5=1b635513f553875060869272b790f910
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
