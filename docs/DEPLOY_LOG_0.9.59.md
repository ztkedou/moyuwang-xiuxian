# DEPLOY LOG — 《摸鱼修仙传》 0.9.59

- 部署时间：2026-10-11 13:46:52（备份）→ 13:47:29（yl-server 重启完成）(GMT+8)
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2859.sh`（客户端 + **服务端** + CHANGELOG + index.html bump；★ **未加 `--skip-server`**）
- 定点核对：`deploy_v28/remote_check_v2859.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0859.env`
- 备份整包：`/root/backup/yl_pre_v2959_20261011_134652.tar.gz`
- DB 一致性快照：`/root/backup/database_v2959_consistent_20261011_134652.sqlite`（11,137,024 B；另有 `database.sqlite.pre-v2959-…` 16,699,392 B）

---

## 1. 本批范围（0.9.59；客户端 **95** 模块 + 服务端 **95** 环）

> 规模口径：`CLIENT_MODULES` = `build_v26n.STANDALONE_CLIENT` 条数 = **95**；
> `SRV_RINGS` = `localtest/chain_build.SRV_CHAIN` 条数 = **95**（本批新增第 95 环）。

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-250a | 4 个新排行榜 + 4 个新称号 + **北京日结算** + `/me` 扩 7 | `patches/server/srv_patch_r251.py`（**第 95 环**） | — | ✔ |
| R-250b | `defRate` 新键 + 文案对齐 + 排行榜 4 新 tab + 两条硬编码链扩 7 | `localtest/yl_r252_ext.py` | ✔ | — |

**R-250 详情**（用户反馈：「再做一些别的称号，再做一些别的排行榜，加成的类型不对吧，战力加攻击力没问题，
灵石应该是灵石获取数量+15%，修为那个应该是修炼速度+15%。重置时间变为1天，不然太频繁也不好。」）

- **侦察结论（关键）**：
  1. ★ **加成的机制本就正确，是文案没说清** —— `stoneRate` 落在 `YlxwDiffGain(x,"stoneMul")`（乘的正是**灵石获取量**）、
     `expRate` 落在 `bd().total`（打坐处 `v=Math.floor(v*(1+m.total))`，正是**修炼速度**）。⇒ 本批**只改文案、不动落点**。
  2. ★★ **`rankings` 表已有 4 个「填好但没启用」的列**（`kill_count` / `achievement_count` / `play_time` / `reputation`，
     `extractRankingData()` 每次存档都在写）⇒ **加新榜无需改 `rankings` 表结构**。
  3. 客户端**已有排行榜页**（`/leaderboard?sort=` + `/leaderboard/me`），tab 表 `DM` 硬编码 3 项。
- **服务端（第 95 环）**：
  - 4 新榜 `LEADERBOARD_SORTS`：`kills` / `achieve` / `playtime` / `fame`（各含 `orderBy`+`aheadCondition`+`getParams`，照 `realm` 同构）。
  - 4 新称号 seed：**万人敌** `atkRate .10`(rank_kills) / **功成名就** `expRate .10`(rank_achieve) /
    **苦修不辍** `defRate .10`(rank_playtime) / **德高望重** `stoneRate .10`(rank_fame) ⇒ 合计 **7 榜 7 称号**。
  - **结算周期 10 分钟 → 每天一次**：新表 `rank_title_state(id, last_date)` + `reconcileRankTitles()` 开头的**北京日日期门**
    （`bjDate` 与上次相同 ⇒ 空转）；`RANK_TITLE_TICK_MS` 改 **1 小时**（每小时检查、每北京日结算一次）；
    保留存档时惰性调用（跨天后首个活动即追赶）。
  - `GET /api/quest/summary` 的 `rankHolders` 扩为 **7 键**；`GET /api/leaderboard/me` 的 `queries` **3 → 7 条**。
  - ★ `/api/leaderboard?sort=` **无需改动** —— 它按 `LEADERBOARD_SORTS` 键取值、未知回落 `realm`（`index_v28.ts:4064`），新增键自动放行。
- **客户端**：`DM` tab +4；`YlxwAttrText` 文案（`灵石获取` / `修炼速度` / 新增 `防御`）；**新增 `defRate` 键**
  （`YlxwXianwuBonus`/`Zero`/`Store` + `xt()` 防御链落点）；`YlxwRankHolders` defs +4；
  ★★ **排行榜页两条硬编码三元链扩 7**（标签链 `k` + 「我的排名」链 `_`）——
  不修会让新 tab 的「我的排名」**回落显示灵石榜名次**（误导）。

## 2. 指纹（部署前后）

| 对象 | 上一版（部署前） | 本批（部署后） |
|---|---|---|
| `www/assets/index-v2958-20261011.js` | `96f1b5e729156079506afa9bf1b00de3` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2957-20261011.js` | `cacfe8f21bd283d46bb2b4c5f4c5012c` | 同左（0.9.57 定版，更早的回滚点） |
| `www/assets/index-v2959-20261011.js` | —（新文件） | **`f649dc234f46844c0ebb5fdbb356b3d9`**（2,343,306 B） |
| `server/index.ts` | `6fe5bf9c33ae5bd3008cbb8f36443860`（94 环） | **`0098cb4faa62c6e406963da84ce07120`**（**95 环**，1,044,070 B） |
| `www/CHANGELOG.md` | `0a5f25180cb8e77b0ed168302ad448a9` | **`6a8d87223a1d8a26f2f3d6c794fa013d`** |
| `www/CHANGELOG_PLAYER.md` | `7729587346992d8134b953591c7bb73b` | **`5cf802d1bd3fa25ede32d92bb3d207ef`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（**本批不变**） |

部署后线上实测（deploy_v2859.sh 采集 + 主对话 ssh 复核，逐位一致）：

```
f649dc234f46844c0ebb5fdbb356b3d9  /opt/yl/www/assets/index-v2959-20261011.js
0098cb4faa62c6e406963da84ce07120  /opt/yl/server/index.ts
6a8d87223a1d8a26f2f3d6c794fa013d  /opt/yl/www/CHANGELOG.md
5cf802d1bd3fa25ede32d92bb3d207ef  /opt/yl/www/CHANGELOG_PLAYER.md
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
```

## 3. 部署前本地验收

- `localtest/dryrun_087.py` → **4341 条门禁 / FAIL 0**（预演 md5 `f649dc234f46844c0ebb5fdbb356b3d9`）
- ★ **「预演==交付」双 provenance 成立**：`build_v26n.py` 产物 md5 **逐位等于** dryrun 预演 md5
- `localtest/chain_build.py --all` → **95 环**；链 s20.t16arena.ts == `7780e099a6cd1ac0de4b502c467ae2c0`（前 20 环 == 0.8.9 定版）
- `localtest/sim_r231_inject.py --new 0.9.59 --prev 0.9.58` → **FAILS = 0**
- `localtest/diag_gate_drift.py --src _chainstage/dryrun_087.bundle.js` → **0 漂移**（rc=0）
- 服务端环独立复跑：`srv_patch_r251.py --selftest --src srv/index_v28.ts` → rc=0 / delta **+5097** /
  **sqlite 语义真跑 5/5**（日期门同日空转、新榜授/收、7 榜互不干扰、`rankHolders` 7 键、`/me` 7 查询名次 == ORDER BY 真值）
- 客户端补丁独立复跑：`yl_r252_ext.py --selftest` → rc=0；幂等 rc=3；往返逐字节相等；
  **node 真跑 7 值标签 / 7 值排名、新 4 榜不再回落 `stones_rank`**
- `sim_remote_check.py --script deploy_v28/remote_check_v2859.sh` → **OK=1099 SKIP=15 FAIL=0**

## 4. 线上验收

- `remote_check_v2859.sh` → **REMOTE-CHECK: PASS (0 failures)**
- 公开冒烟：`index` **200** / `bundle` **200** / `api/save`（未授权）**401**
- `yl-server`：`ActiveEnterTimestamp = Sun 2026-10-11 13:47:29 CST`、`is-active = active`
  ⇒ ★ **本批服务端确实重启生效**（非零停机批）
- ★ **数据库变更（本批 1 处结构变更）**：
  - **新增单行表** `rank_title_state (id INTEGER PRIMARY KEY CHECK (id = 1), last_date TEXT NOT NULL DEFAULT '')`
    + `INSERT OR IGNORE ... VALUES (1, '')`（幂等 DDL，重启安全）。
  - 另新增 4 条 `titles` seed（`INSERT OR IGNORE`）与 4 条 `LEADERBOARD_SORTS` 配置（**非 schema**）。
  - **`rankings` 表结构未动**（复用既有 4 列）。
  ⇒ 回滚**无需删表/删列**（旧代码不读多余表，无害）。

## 5. 本轮踩到的新坑

1. ★★ **子代理因 429 频率限制中途死掉**（客户端补丁）：**不是逻辑失败** —— 它死前已落盘 26 KB 且 `--selftest` rc=0，
   唯一缺的是我**在它启动之后**才追加的两条硬编码链。★ **无法拉起**（成员失败后团队被自动清掉，`SendMessage` 返回 `Not in a team`）
   ⇒ 按用户指令**新派成员接手**：先**独立复验**死进程留下的产物，再补缺口。
   ★ 教训：**「失败」要先分清「逻辑失败」还是「配额/基础设施失败」** —— 后者往往已留下可用产物，从头重做才是浪费。
2. ★★ **软件闪退打断三件套派生，留下「半改」生成器**：常量区已改对、但**输入侧路径还停在 v2857**
   ⇒ 跑起来 `AssertionError: OLD_NOTE ... count=0`（★ **fail-closed 挡住了**，未静默产出错件）。
   ★ 处置与上一条**完全相反**：半成品**自相矛盾** ⇒ **不就地打补丁，从干净模板 `_mk_2858.py` 重建**。
   ★ 判断依据不是「完成了多少」，而是**「它内部是否自洽」**。
3. ★ **重建时的关键陷阱**：`_mk_2858.py` 里 `v28NN` 引用**不能无脑整链 +1** ——
   **`v2811`**（`_chainstage/index_v28.v28112.ts` **不可变参照文件名**）与 **`v2852`**（历史注释）**必须保持不动**。
   正确做法：**倒序**平移（`v2858→v2859` → `v2857→v2858` → `v2856→v2857`）+ **带上下文的词**替换
   （`deploy_vNNNN.sh` / `remote_check_vNNNN.sh` / `EXPECT_0NNN`），**不要**裸替换 `v28NN`。
4. 生成器 NEW_NOTE 里漏了一个右括号（`…/me 扩 7` 缺 `）`）⇒ 已修生成器并重跑（**注释性缺陷，不影响断言**）。

## 6. 残留清理

- 远端 `_remote_check_v2859.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` 按惯例留在 `/opt/yl/server/` 便于复跑。
- 本地沙箱 `_r249_srv_sandbox/`、`_r252_sandbox/` 与 `build/assets/*.bak-*` 按惯例不入库。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2959-20261011_134652 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2959-20261011.js --to=index-v2958-20261011.js
cp -a /root/backup/index.ts.pre-v2959-20261011_134652        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2959-20261011_134652 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2959-20261011_134652    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2958-20261011.js.pre-v2959-20261011_134652 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版：bundle=96f1b5e729156079506afa9bf1b00de3  server=6fe5bf9c33ae5bd3008cbb8f36443860
# 整包：/root/backup/yl_pre_v2959_20261011_134652.tar.gz
```

★ 回滚注意：本批新增表 `rank_title_state` 与 4 条 titles seed —— **回滚无需删表/删列**（旧代码不读多余表）。
若需还原称号加成：`UPDATE titles SET attr_json=? WHERE source IN ('rank_kills','rank_achieve','rank_playtime','rank_fame')`。

## 8. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=f649dc234f46844c0ebb5fdbb356b3d9
PREV_SRV_MD5=0098cb4faa62c6e406963da84ce07120
PREV_CHANGELOG_MD5=6a8d87223a1d8a26f2f3d6c794fa013d
PREV_PLAYER_MD5=5cf802d1bd3fa25ede32d92bb3d207ef
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=0098cb4faa62c6e406963da84ce07120   # 链尾 _chainstage/s95.r251.ts（供单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
~/.ai-memory/topics/项目-摸鱼修仙传.md「当前版本」段。
