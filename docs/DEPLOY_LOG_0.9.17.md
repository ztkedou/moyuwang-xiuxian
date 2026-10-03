# DEPLOY LOG — 《摸鱼修仙传》 0.9.17（v29.17）

- 部署时间：2026-10-03 10:12 (GMT+8)（备份 TS `20261003_101235`，live_bump 于 10:12:4x 完成）
- 目标：香港 VPS `47.243.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2811.sh --skip-server`
- 定点核对：`deploy_v28/remote_check_v2811.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0811.env`
- 备份整包：`/root/backup/yl_pre_v2917_20261003_101235.tar.gz`（41,985,663 B）
- DB 一致性快照：`/root/backup/database_v2917_consistent_20261003_101235.sqlite`（5,156,864 B，`VACUUM INTO`）

---

## 1. 本批范围：0.9.17（R-140 消耗品数值重构 + R-141 装备稀有属性）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-140a | 消耗品数值重构：`fg` 品质地板 −75% / `Rr` 250→40 / `mw` 5000→1200 / `Ic` 缩放重配 / 丹药 13 + 草药 7 表重做 / 死键清理 | standalone `yl_r140_ext.py` | ✔ | — |
| R-140b | 消耗品售价品质阶梯（装备沿用 R-135 三元逐字不动）+ 掉率收紧 + `$r` 下限 .10 + 永久属性 `ZS×1.0` 硬顶 | standalone `yl_r140b_ext.py` | ✔ | — |
| R-141 | 装备天生稀有词条：`vs()` 注入 `innateAffixes`（境界凸曲线 × 品质条数 × K=0.35）+ `YlxwStatExtras` / `YlxwBattleBonus` 合并消费 | standalone `yl_r141_ext.py` | ✔ | — |

**客户端**：V28_MODULES 95 模块不变 + standalone 19 → **22 脚本**（新增 r140 / r140b / r141，序 = 编号序）。
**服务端**：SRV_CHAIN **66 环不变**（链尾 `s66.r136.ts`），零新 DDL、零新端点 ⇒ 本批 `--skip-server`。

**未改动（用户明确要求）**：装备上的神识 / 身法（`iy` 独立硬编码分支）一字未动；`breakthrough` 升段类奇物道具
（筑基丹 / 结金丹 / 破境丹 / 天元果 / 金仙果）逐字保留。

## 2. 集成期改动（非子代理产出，主对话做）

| 项 | 内容 | 理由 |
|---|---|---|
| 标记去冲突 | `yl_r140b_ext.py` 的 `MARK` `YLXW_R140_V2916` → `YLXW_R140B_V2916` | 旧值是 r140a 标记 `/*YLXW_R140_V2916*/` 的**子串** ⇒ 串行叠加时 r140b 误判「部分补丁态」rc=2 中止（已实测复现） |
| 门禁约束权移交 | `yl_r135_ext.py` 4 条 needle 改为跨形态稳定片段 | R-140b 合法改写了 R-135 的售价倍率行 / 普通池 .88→.92 / 幸运池 .8→.88、.85→.90 / 宗门掉落门 .4→.30；**改判而非删断言** |
| 接线 | `build_v26n.STANDALONE_CLIENT` + `localtest/dryrun_087.py` standalone 门禁段 追加三脚本 | 新成员进装配序；dryrun 原先只硬编码 r116~r139（419 条），补后 **550 条** |

## 3. 部署前本地验收

- `python localtest/dryrun_087.py`：build() 门禁 **4244 条 FAIL 0**；standalone 门禁 **550 条 FAIL 0**（r116~r141 共 22 脚本）
- **预演 == 交付**（铁律 12/13）：`_chainstage/dryrun_087.bundle.js` 与 `build/assets/index-v2917-20261003.js`
  **md5 逐位一致 = `0470077292ba4ca446f92897257e0c54`**（2,288,389 B）
- `python localtest/sim_remote_check.py`：**OK=248  SKIP(远端专有)=13  FAIL=0**
- 服务端零改动：`srv/index_v28.ts` == `_chainstage/index_v28.v28112.ts` == 0.9.16 定版 `664501929cecb41fd57e65d9d0c48872`
- `bash deploy_v28/deploy_v2811.sh --skip-server --dry-run`：step 0 / 0c 全过

## 4. 指纹（部署前后）

| 对象 | 0.9.16（部署前） | 0.9.17（部署后） |
|---|---|---|
| `www/assets/index-v2917-20261003.js` | —（新文件） | **`0470077292ba4ca446f92897257e0c54`**（2,288,389 B / 95 模块 + 22 standalone） |
| `www/assets/index-v2916-20261003.js` | `a59ac4496ab0e8ab81fdb147b45488ec` | 同左（旧包保留不删 = 回滚点，公网 200） |
| `www/assets/index-v2915-20261002.js` | `41721861172d4655a9765e2a10423c63` | 同左（更早的回滚点） |
| `server/index.ts` | `664501929cecb41fd57e65d9d0c48872` | 同左（**本批零改动**） |
| `www/CHANGELOG.md` | `a6ce240eebd6b5a81fd3fdbb310f76c7` | **`37b01f9682cc406cf55e265da62102c8`**（头条 `## [0.9.17] - 2026-10-03 10:12`） |
| `www/CHANGELOG_PLAYER.md` | `dfb4295f6fad8eb5e760c87b72cf01d3` | **`2907bb6dc30f197dd4f62aa7532204ef`** |
| `www/index.html` | — | `da6215dd0cbd424a438837d48b648f95`（2213 B，`src="/myxxz/assets/index-v2917-20261003.js"`） |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批不变） |

部署后线上实测（deploy_v2811.sh 采集）：

```
664501929cecb41fd57e65d9d0c48872  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
0470077292ba4ca446f92897257e0c54  /opt/yl/www/assets/index-v2917-20261003.js
37b01f9682cc406cf55e265da62102c8  /opt/yl/www/CHANGELOG.md
2907bb6dc30f197dd4f62aa7532204ef  /opt/yl/www/CHANGELOG_PLAYER.md
da6215dd0cbd424a438837d48b648f95  /opt/yl/www/index.html
```

## 5. 线上验收

`remote_check_v2811.sh` → **REMOTE-CHECK: PASS (0 failures)**：

- index.html 指向新包 x1 / 旧包引用已清零 x0 / 平台注入块（unified-stats、mw-reward start·end）各 ≥1
- CHANGELOG 含 `[0.9.17]` / `[0.9.16]` / `[0.9.15]` 历史条目
- 公开冒烟：首页 **200**｜`/yl/` 301｜新 bundle **200**｜旧包保留 **200**｜CHANGELOG **200**
- 判活 no-token：`/api/teahouse/today` 401、`/api/fun/dice` POST 401、`/api/pet/spirit/*` 401、`/api/snapshots*` 401、`/api/arena/week` 401、`/api/me/mute` 401、`DELETE /api/mail/1` 401
- **0.9.17 特征点 26 条全 OK**：R-140a/R-140b/R-141 三个在位标记；售价品质阶梯常量 x3；装备分支沿用 R-135 三元 x1；
  普通池 .92/.99 x1（旧 .88/.98 清零）；大机缘 .88/.90 x1（旧 .8/.85 清零）；秘境门 .45 / 宗门门 .30 / 升档率 .02+.15u；
  `$r` 下限 .10（旧 .25 清零）；硬顶比例常量 x2 + 硬顶累加助手 x7；R-141 境界因子表 x2 / 品质条数表 x2 / K=0.35 x1 /
  词条掷函数 x1 / `innateAffixes` x7 / `YlxwBattleBonus` x7
- 服务健康：`systemctl is-active yl-server = active`；maintenance flag absent；NRestarts **0**
- 线上库核对：8 表 + `sects.join_mode` + `pets.merged/merge_pity/sub_consumed` + `gm_sessions.expires_at` / `users.muted_until` 全在

## 6. 本轮踩到的新坑

1. **standalone 在位标记必须全局唯一且互不包含**。r140a 用 `/*YLXW_R140_V2916*/`、r140b 用裸串 `YLXW_R140_V2916`
   —— 后者是前者的子串，`apply_standalone` 按序套用时 r140b 误判「部分补丁态」rc=2 中止。
   ⇒ 约定：新脚本标记带批次后缀字母（`YLXW_R140B_...`），且**不得是任何其它脚本标记的子串**。
2. **同尺寸不同 md5 ≠ 没改**。升版后首次 build 产物与旧 dryrun 产物**字节数完全相同**（2288389）但 md5 不同 ——
   原因是 dryrun 跑在版本号 bump **之前**（`YLVERSION_FALLBACK` 0.9.16 vs 0.9.17，等长）。
   ⇒ 升版后**必须重跑 dryrun** 再做「预演==交付」比对，不能沿用旧预演产物。
3. **产物中文形态是混合的**。Vite 原始代码段是真实 UTF-8 中文，而模块注入块（如 r136 的 `\u5730\u5bab\u51b7\u5374`）
   是 `\u` 转义。写 remote_check needle 前**必须在真实产物上 grep 一次**确认形态，否则断言恒 0（假 PASS 或假 FAIL）。
4. **dryrun 的 standalone 门禁段是硬编码脚本清单**（原先只列 r116~r139）。新增成员必须同步补进
   `localtest/dryrun_087.py`，否则新脚本的 gates() 根本不会被重跑。
5. **CHANGELOG 条目头时刻与实际 swap 时刻差 18 分钟**（预估 10:30，实际 10:12）。已按铁律改为实际上线时刻并重传，
   `EXPECT_CHANGELOG_MD5` 同步重登记。⇒ 下次直接按「预计 +5 分钟」估，不要留大余量。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@47.243.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2917-20261003_101235 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2917-20261003.js --to=index-v2916-20261003.js
cp -a /root/backup/CHANGELOG.md.pre-v2917-20261003_101235 /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2916-20261003.js.pre-v2917-20261003_101235 /opt/yl/www/assets/
# ★ 本批服务端零改动 ⇒ 无需还原 index.ts、无需重启 yl-server
# 0.9.16 定版：bundle=a59ac4496ab0e8ab81fdb147b45488ec  server=664501929cecb41fd57e65d9d0c48872
# 整包：/root/backup/yl_pre_v2917_20261003_101235.tar.gz
```

★ 存档兼容：本批客户端新增 `u.permGain` 归一化（旧档 `undefined → {}`），R-141 的 `innateAffixes` 是**装备对象内的
可选字段**（旧档装备无此字段 ⇒ 读作空数组，零崩溃）⇒ 回滚与前行都不需要动数据库。

## 8. 0.9.17 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=0470077292ba4ca446f92897257e0c54      # index-v2917-20261003.js（2,288,389 B）
PREV_SRV_MD5=664501929cecb41fd57e65d9d0c48872         # srv/index_v28.ts（980,090 B / 66 环，本批零改动）
PREV_CHANGELOG_MD5=37b01f9682cc406cf55e265da62102c8
PREV_CHANGELOG_PLAYER_MD5=2907bb6dc30f197dd4f62aa7532204ef
PREV_INDEX_HTML_MD5=da6215dd0cbd424a438837d48b648f95
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
