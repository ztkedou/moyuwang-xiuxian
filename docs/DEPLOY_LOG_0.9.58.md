# DEPLOY LOG — 《摸鱼修仙传》 0.9.58

- 部署时间：2026-10-11 11:38:12（备份）→ 11:38:45（yl-server 重启完成）(GMT+8)
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2858.sh`（客户端 + **服务端** + CHANGELOG + index.html bump；★ **未加 `--skip-server`**）
- 定点核对：`deploy_v28/remote_check_v2858.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0858.env`
- 备份整包：`/root/backup/yl_pre_v2958_20261011_113812.tar.gz`（68,526,163 B）
- DB 一致性快照：**本批无数据库结构变更**（见 §4），未单独取 sqlite 热拷贝

---

## 1. 本批范围（0.9.58；客户端 **94** 模块 + 服务端 **94** 环）

> 规模口径：`CLIENT_MODULES` = `build_v26n.STANDALONE_CLIENT` 条数 = **94**；
> `SRV_RINGS` = `localtest/chain_build.SRV_CHAIN` 条数 = **94**（本批新增第 94 环）。

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-249a | 排行称号「定时轮换 + 被超越即收回 + 加成上调」 | `patches/server/srv_patch_r249.py`（**第 94 环**） | — | ✔ |
| R-249b | 仙务称号 `attr` 四处加成落点 + 称号页增强 | `localtest/yl_r250_ext.py` | ✔ | — |

**R-249 详情**（用户需求：「仙务·称号中的称号没有任何属性加成……应该是随时或者固定时间轮换的，像首富、战力榜第一这些的……
固定时间读取如果别人是第一，就会那个人获得不是第一个的没有了。把这一套重新规划重新制作。」）

- **侦察结论**：服务端**已有** `titles`/`player_titles` + 三榜自动授予（`maybeGrantAutoTitles`），客户端**已有** `YlxwTTitles` 页面，
  **但两端都停在「展示」层** —— 服务端**只授不收回**（全文件无 `DELETE FROM player_titles`）、只在存档时惰性跑；
  客户端**完全不应用** `attr_json`（`atkRate`/`stoneRate`/`expRate`/`charmRate` **零引用**）⇒ 称号**实际零加成**。
- **服务端**：新增 `reconcileRankTitles()` —— 对 `RANK_TITLE_SOURCES` 每条「取 #1（走 `LEADERBOARD_SORTS.orderBy`，与
  `/api/leaderboard` **逐字同源**）→ `DELETE` 非 #1（榜 <2 人 ⇒ 全表收回）→ 佩戴清理（`saves.title_id` 置空）
  → `grantTitleBySource(#1)`」；`setInterval` **每 10 分钟**一次（首行早退 + 重入锁 + 自吞，照 `[arenaweek]` 写法）
  + 存档时惰性（`maybeGrantAutoTitles` 改为调用它）。加成上调用 **`UPDATE titles SET attr_json`**（★ 幂等迁移 ——
  既有 seed 是 `INSERT OR IGNORE`，**改不动已存在行**）：武林盟主 `atkRate` 0.15 / 富甲一方 `stoneRate` 0.15 / 登峰造极 `expRate` 0.15。
  `GET /api/quest/summary` 追加 `rankHolders`（三榜持有者；**既有键一字未改**）。
- **客户端**：`YlxwXianwuBonus()`（模块级缓存 + 异常静默返回全 0）+ 四处落点
  （`atkRate`→`xt()` 攻击 / `expRate`→`bd().total` 修炼效率 / `stoneRate`→`YlxwDiffGain` 的 `stoneMul` 分支 /
  `charmRate`→仅展示，全 bundle 魅力无消费点）+ 增强 `YlxwTTitles`（`YlxwAttrText` 加成明细 + `YlxwRankHolders` 三榜区块）。

## 2. 指纹（部署前后）

| 对象 | 上一版（部署前） | 本批（部署后） |
|---|---|---|
| `www/assets/index-v2957-20261011.js` | `cacfe8f21bd283d46bb2b4c5f4c5012c` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2956-20261010.js` | `6fc3c750d147aa314e3a9433a6c9385e` | 同左（0.9.56 定版，更早的回滚点） |
| `www/assets/index-v2958-20261011.js` | —（新文件） | **`96f1b5e729156079506afa9bf1b00de3`**（2,342,339 B） |
| `server/index.ts` | `328170ededb61fe3289845cb91d3419d`（93 环） | **`6fe5bf9c33ae5bd3008cbb8f36443860`**（**94 环**，1,038,423 B） |
| `www/CHANGELOG.md` | `9e8e5afda256e3f66fe0e31bc19d699d` | **`0a5f25180cb8e77b0ed168302ad448a9`** |
| `www/CHANGELOG_PLAYER.md` | `1fb6c1f19d893b8a9b5bd4b93d7097c5` | **`7729587346992d8134b953591c7bb73b`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（**本批不变**） |

部署后线上实测（deploy_v2858.sh 采集 + 主对话 ssh 复核，逐位一致）：

```
96f1b5e729156079506afa9bf1b00de3  /opt/yl/www/assets/index-v2958-20261011.js
6fe5bf9c33ae5bd3008cbb8f36443860  /opt/yl/server/index.ts
0a5f25180cb8e77b0ed168302ad448a9  /opt/yl/www/CHANGELOG.md
7729587346992d8134b953591c7bb73b  /opt/yl/www/CHANGELOG_PLAYER.md
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
```

## 3. 部署前本地验收

- `localtest/dryrun_087.py` → **4340 条门禁 / FAIL 0**（预演 md5 `96f1b5e729156079506afa9bf1b00de3`）
- ★ **「预演==交付」双 provenance 成立**：`build_v26n.py` 产物 md5 **逐位等于** dryrun 预演 md5
- `localtest/chain_build.py --all` → **94 环**；链 s20.t16arena.ts == `7780e099a6cd1ac0de4b502c467ae2c0`（前 20 环 == 0.8.9 定版）
- `localtest/sim_r231_inject.py --new 0.9.58 --prev 0.9.57` → **FAILS = 0**
- `localtest/diag_gate_drift.py --src _chainstage/dryrun_087.bundle.js` → **0 漂移**（rc=0）
- 服务端环独立复跑：`srv_patch_r249.py --selftest --src srv/index_v28.ts` → rc=0 / delta **+4293** /
  **sqlite 语义真跑 5/5**（含「B 反超 ⇒ A 失去、B 获得、该称号恰 1 行」）
- 客户端补丁独立复跑：`yl_r250_ext.py --selftest` → rc=0；幂等 rc=3；往返逐字节相等
- `sim_remote_check.py --script deploy_v28/remote_check_v2858.sh` → **OK=1023 SKIP=15 FAIL=0**

## 4. 线上验收

- `remote_check_v2858.sh` → **REMOTE-CHECK: PASS (0 failures)**
- 公开冒烟：`index` **200** / `bundle` **200** / `api/save`（未授权）**401**
- `yl-server`：`ActiveEnterTimestamp = Sun 2026-10-11 11:38:45 CST`、`is-active = active`
  ⇒ ★ **本批服务端确实重启生效**（非零停机批，与纯客户端批不同）
- ★ **数据库变更：本批无结构变更**（无新增表 / 列）。`r249` 只用既有 `titles` / `player_titles` / `saves.title_id`，
  并以 `UPDATE titles SET attr_json = ? WHERE source = ?` 做**数据层幂等迁移**（三条榜称号加成 0.03/0.05 → **0.15**）。
  ⇒ 回滚**无需删列/删表**；旧代码不读多余字段，无害。

## 5. 本轮踩到的新坑

1. ★★ **「冻结针脚被下游改写」第 5 次**（同类事故连续 5 批）：`r250` 往 `bd().total` 追加 `+__xw`、
   并改了 `YlxwDiffGain` 的**函数体** ⇒ 一次打穿 **4 条上游针**（r218 的 E1、r222 的退役针、r238 的 B 针 + 相邻强证明针）。
   - ★ **仍是 R-246 的自动派生名单（`dryrun`）+ `diag_gate_drift.py` 当场抓到的**（前三次靠人发现）。
   - 修法仍是铁律 **tuple 合计多形态**：`E1_NEW_R250` 由 `E1_NEW_ALT` **守卫式 `.replace()`** 构造（含两条 assert 防恒等）、
     `FRZ_TOTAL_R250` 第四形态、`GATE_ALT` 的值改为可容纳 tuple 并把门禁循环**拍平**、相邻强证明加第三形态。**绝无放宽**。
2. **本批与上一批「不同型」⇒ 生成器必须换口径**：`_mk_2853`~`_mk_2857` 连续五批都是**纯客户端批**，
   其生成器带「服务端**必须不变**」的硬断言（`assert s_md5 == PREV_SRV_MD5`、链尾不平移、`必须加 --skip-server`）。
   本批服务端**变了** ⇒ 全部**反向**（`!=`、链尾 `s93.r233.ts` → `s94.r249.ts`、**不要加 `--skip-server`**），
   否则 `mk_expect()` 必然 AssertionError。参照的「服务端批」范本 = `_mk_2852.py`。
3. **生成器遗留注释与本批事实相反**：`deploy_v2858.sh` 里 `PREV_SRV_S20_MD5` 上方那句
   「单变量可核：本批服务端**无 diff**（纯客户端批）」是从上一批**继承**来的（**上个服务端批 v2852 也遗留了同一处**）。
   已顺手在 `_mk_2858.py` 里加第 4 条反向修正并重跑生成器 ⇒ **未来批次（无论客户端批/服务端批）都继承修正后的文案**。

## 6. 残留清理

- 远端 `_remote_check_v2858.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` 按惯例留在 `/opt/yl/server/` 便于复跑。
- 本地沙箱 `_r249_srv_sandbox/`（含 `.bak`）可清理；`build/assets/*.bak-r250-*` 等按惯例不入库。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2958-20261011_113812 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2958-20261011.js --to=index-v2957-20261011.js
cp -a /root/backup/index.ts.pre-v2958-20261011_113812        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2958-20261011_113812 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2958-20261011_113812    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2957-20261011.js.pre-v2958-20261011_113812 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版：bundle=cacfe8f21bd283d46bb2b4c5f4c5012c  server=328170ededb61fe3289845cb91d3419d
# 整包：/root/backup/yl_pre_v2958_20261011_113812.tar.gz
```

★ 回滚注意：本批**无数据库结构变更**（见 §4）⇒ 回滚**无需删列 / 删表**。
唯一的数据迁移是 `titles.attr_json` 三条榜称号被改成 0.15；若需回到旧数值，执行
`UPDATE titles SET attr_json='{"atkRate":0.03}' WHERE source='rank_combat'`（另两条同理 0.03 / 0.05）。

## 8. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=96f1b5e729156079506afa9bf1b00de3
PREV_SRV_MD5=6fe5bf9c33ae5bd3008cbb8f36443860
PREV_CHANGELOG_MD5=0a5f25180cb8e77b0ed168302ad448a9
PREV_PLAYER_MD5=7729587346992d8134b953591c7bb73b
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=6fe5bf9c33ae5bd3008cbb8f36443860   # 链尾 _chainstage/s94.r249.ts（供单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
~/.ai-memory/topics/项目-摸鱼修仙传.md「当前版本」段。
