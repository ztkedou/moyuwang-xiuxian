# DEPLOY LOG — 《摸鱼修仙传》 0.9.28

- 部署时间：**2026-10-06 21:33 (GMT+8)**
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2828.sh`（客户端 + 服务端 + CHANGELOG + index.html bump）
- 定点核对：`deploy_v28/remote_check_v2828.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0828.env`
- 备份整包：`/root/backup/yl_pre_v2928_20261006_213153.tar.gz`
- DB 一致性快照：`/root/backup/database_v2928_consistent_20261006_213153.sqlite`
- 生成器：`_mk_2828.py`（deploy）/ `_mk_rc2828.py`（remote_check）—— 机械重登记，**只做整名替换**（铁律 D）

---

## 1. 本批范围：0.9.28（客户端 95 模块 + **41** standalone 脚本；服务端 **78 环**）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-174 | 活动中心·签到行上移 | `yl_r174_ext.py` | ✔ | — |
| R-175 | 万妖巢穴·排行榜按每只 boss 单独计算 | `yl_r175_ext.py` / `srv_patch_r175.py`（第 78 环） | ✔ | ✔ |
| R-176 | 抽奖券抽奖按境界收敛 + 删除越阶折算灵石 | `yl_r176_ext.py` | ✔ | —（★ 见 §5-4） |
| R-177 | 自动历练节奏统一冷却 9s | `yl_r177_ext.py` | ✔ | — |
| R-178 | 历练三档几率收敛 | 同 R-177（同环） | ✔ | — |
| R-179 | 历练结算信息去重 + 两段重排 + 寿命变化 | `yl_r179_ext.py` | ✔ | — |

**服务端链 77 → 78 环**：
```
s77.r173.ts  a5927a49b17d5262aa12b3f61f27d740  1,005,270 B  ← == 0.9.26/0.9.27 定版（本批 PREV）
s78.r175.ts  3cecbaf388c7ab87a469f7ec2cf4df85  1,007,886 B  ← R-175 逐只榜（新末环）
```

### 各条要点
- **R-174**：签到行由面板**最底部**（上方压着 7×31 月历 grid 与里程碑行）前移到**标题之后、其它活动块之前**。
  纯渲染顺序调整（原位留 `/*[r174act]*/` 哨兵），文案/接口/onClick/数据逻辑一行未动。
- **R-175**：根因 = `event_boss_hits` 表 PK 是 `(event_id, user_id)`、记分 `score = score + excluded.score`
  ⇒ **五只 boss 的伤害在写入时就被累加成一份总分**，物理上没有「每只各打多少」的维度。
  修法：新表 `event_boss_hits5(event_id, boss_no, user_id, score, strikes)` 逐只记分 + `status` 向后兼容新增
  `top10ByBoss`（旧 `top10` 逐位不变）；客户端读 `top10ByBoss` 逐只渲染 5 段（空榜「暂无讨伐记录。」，
  字段缺失/空数组回落旧合计榜）。★ 既有合计口径经**独立复核逐字节 IDENTICAL**（行级 diff 4 纯插入 hunk、0 删除）。
  ⚠️ **过渡态**：新表无历史行 ⇒ 逐只榜初始为空，从上线后每次出手开始累积。
- **R-176**：病根 = 抽奖**完全不看境界**（实测真实池 1193 条：炼气期单抽 **59.12% 越阶**，其中 **39.82% 高 ≥3 大境界**），
  而越阶物品进不了背包、被 `_ylr` 段折算成灵石+修为「消散」。修法：① **整段删除**该折算兜底（`const _ylr=` → 0）；
  ② 按境界差 `d` 整数倍率重加权 **1e7 : 1e4 : 1e2 : 1** ⇒ 炼气 d≤0 **22.88%** / d=1 **0.024%** /
  d=2 **0.00023%** / d≥3 **0.00001%（≈1e-7）**；**越阶合计 59.12% → 0.024%**。
- **R-177**：根因 = **两条并存的冷却档位**（主路 85%：轮询+展示1.5s+**冷却10s** ≈ 11.5~12s；
  商店跳过路 15%：轮询+**冷却2s** ≈ 2~2.5s）⇒ 带宽 **2.25s↔11.75s（5.2 倍）**。
  修法 = 统一冷却 **9s** ⇒ 带宽 **9.25s↔10.75s（1.16 倍）**；平均 10.325s→10.525s ⇒ 单位时间收益 **−1.9%**（不放大）。
- **R-178**：三档**不是随机 roll**，是按 `$=|修为变化|+|灵石变化|` 分桶；原「中档 $>200」是**死代码**
  （1200 条模板在 200~500 区间为空）。修法 `$>500?×0.50 : $>100?×0.88 : ×1`（阈值 200→100）
  ⇒ 低 **[82.1,85.0]** / 中 **[14.2,17.9]** / 高 **[0.0,2.4]**（旧：长生高档 8~9%）。
- **R-179**：去 3 处重复（时长/次数/奇遇）+ 两段重排（主结算：时长·次数·修为·灵石·**寿命**·气血·物品；
  明细：事件类型/掉落/天地之魄/受伤/平均每次）+ 可见字符分割符 `——— 明细 ———`（日志渲染器无 `pre-line`，`\n` 会被折叠）
  + **新增寿命变化累加与条件渲染**（非 0 且 `|值|≥0.05` 才显示）。仍是**一条**日志（只 `add` 一次）。

## 2. 指纹（部署前后）

| 对象 | 0.9.27（部署前） | 0.9.28（部署后，线上实测） |
|---|---|---|
| `www/assets/index-v2927-20261006.js` | `c3b2c9bab29830de1f831b8d6d012171` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2926-20261006.js` | `6ed91e0e46b90fada980367459cbe3fc` | 同左（0.9.26 定版，更早的回滚点） |
| `www/assets/index-v2928-20261006.js` | —（新文件） | **`47227cabf8eb5e1fa9bfe78d1de49e75`** |
| `server/index.ts` | `a5927a49b17d5262aa12b3f61f27d740` | **`3cecbaf388c7ab87a469f7ec2cf4df85`**（1,007,886 B / 78 环） |
| `www/CHANGELOG.md` | `33db9d937823e429873f1ee90dc16156` | **`41fa2b76f36ddad6ed19dafdb9dbb6a0`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批未变） |

## 3. 部署前本地验收

| 环节 | 命令 | 结果 |
|---|---|---|
| 服务端链 + 前端装配 | `localtest/chain_build.py --all` | rc=0；**78 环**；链尾 `node --experimental-strip-types --check` rc=0 |
| 客户端预演 | `localtest/dryrun_087.py` | 门禁 **PASS（FAIL=0）**；standalone 763 → **896** 条；「预演==交付」md5 `47227cab…` 一致 |
| 5 个客户端补丁串行冲突预检 | 临时副本依次套 r174/r175/r176/r177/r179 | 5/5 rc=0；链尾 `node --check` rc=0；复跑 5/5 SKIP；五个标记各就位；`折算回收` = 0 |
| 远端断言本地预演 | `localtest/sim_remote_check.py --script deploy_v28/remote_check_v2828.sh` | **OK=501 / SKIP=15 / FAIL=0** |
| 部署件指纹一致性 | `deploy_v2828.sh` vs `EXPECT_0828.env` 的 6 个 `PREV_*` | 6/6 逐字一致 |

## 4. 线上验收

| 项 | 结果 |
|---|---|
| `REMOTE-CHECK` | **PASS (0 failures)** |
| 服务端 index.ts | `3cecbaf388c7ab87a469f7ec2cf4df85`（1,007,886 B，78 环） |
| CHANGELOG.md | `41fa2b76f36ddad6ed19dafdb9dbb6a0` |
| 游戏内版本号 | `YLVERSION_FALLBACK = "0.9.28"` |
| 服务 | `yl-server` **active**，`NRestarts=0` |
| 新表 / 新字段 | `CREATE TABLE IF NOT EXISTS event_boss_hits5` ×1；`top10ByBoss` ×1 |
| ★ 红线（线上产物实测） | `折算回收` = **0**；`const _ylr=`（越阶折算段）= **0** |
| ★ gzip 同包（R-159 防线） | `zcat /opt/yl/www/index.html.gz` 命中 `assets/index-v2928-20261006.js` ×1 |
| ★ 公网带 `Accept-Encoding: gzip` 冒烟 | http=200，gunzip 后命中 v2928 ×1 |
| 新包可访问 | `GET /myxxz/assets/index-v2928-20261006.js` → 200 |
| CHANGELOG 公网 | `GET /myxxz/CHANGELOG.md` → 200，顶部为 `## [0.9.28] - 2026-10-06 21:32` |
| 探针 | `GET /api/eventboss/status?eventId=1` 无 token → **401**（路由在线） |

## 5. 本轮踩到的新坑（★ 务必保留）

1. ★★ **跨模块门禁冲突（本轮最大的一处，14 条）**：R-179 重写了「自动历练结束汇总」的装配
   ⇒ 撞坏 **3 个老环（R-138 / R-155 / R-161）共 14 条冻结针脚**（实测 `actual=0`）。
   - **处理方式 = 移交 + 双向承接，非静默删除**：
     · 老环侧各加 `SUPERSEDED_BY_R179` 元组，`gates()` **过滤**掉这些针脚（needle 原文与原因**保留在文件里**）；
     · `yl_r179_ext.py` 侧补承接 gate（单次 add / 空日志回退 / 时长·次数·奇遇各只出现 1 次 / 两段+可见分割符 /
       寿命条件渲染），并在文件头写了「与老环的交接说明」。
   - ★★ **为什么必须「过滤」而不是「把期望值改成 0」**：`yl_r155_ext.py` 的 `main()` 会在**本环刚应用后**的
     **中间形态**上跑 `gates()` —— 那一刻旧针脚**合法地还在**（==1）。若改成断言 0，会在**装配中途误报 ABORT**。
     **教训：standalone 补丁的 `gates()` 会被应用路径复用，其预期值必须对「本环刚应用完」的中间形态成立。**
     （与 0.9.27 的 r169/r169b 同一类坑，本轮再次出现 —— **新增/重写汇总类补丁时必查老环冻结针脚**。）
2. ★ **`dryrun_087.py` 的「失败明细」打印有 bug**：它用了一个陈旧的 `out` 变量算「实际」，导致**数字不可信**
   （本轮一度显示「期望 1 实际 1 却 FAIL」）。**排查时请看循环内联打印的 `actual=` 行**，不要看汇总明细。
3. ★ **三条老断言被本批合法推翻**（已按实际产物更新预期值 + 改标签说明原因，非静默删）：
   `T11 抽奖份新形态`（R-176 删了那段 ⇒ 改 `eq 0`）、`R-117 收尾冷却=10`（R-177 改 9 ⇒ 认 `d(9)`）、
   `R161 汇总行去重块`（R-179 退役 ⇒ 改 `eq 0`）。
4. ★★ **R-176 的服务端环经判定越界，本批不接线**：`srv_patch_r176.py` 改的是**奇遇**（`/api/adventure/draw`，
   每日 3 次）的品阶分布（白档 99.8991%），而 R-176 台账原文说的是「**抽奖券**抽奖」，抽奖券抽奖是**纯客户端**。
   奇遇 ≠ 抽奖券抽奖，且把奇遇压成 99.9% 白档是**用户未要求的重大削弱** ⇒ 文件保留、**不进 `SRV_CHAIN`**，待用户定夺。
5. **R-175 过渡态**：`event_boss_hits5` 是新表，上线前已开的活动**没有历史逐只记录** ⇒ 逐只榜初始为空
   （合计榜仍有值）。历史伤害回填属数据迁移，本批不做。

## 6. 残留清理

远端 `_remote_check_v2828.sh` / `_live_bump_bundle.js` / `_remote_gz_sync.sh` 留在 `/opt/yl/server/` 便于复跑（惯例）。
本地：`_chainstage/` 各环产物保留（供单变量可核）；补丁自测产生的临时副本与 `.bak-*` 已全部删除。

## 7. 回滚（本轮动了新包 + index.html + CHANGELOG + index.ts，需重启）

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2928-20261006_213153 /opt/yl/www/index.html   # 或 live_bump 回 index-v2927-20261006.js
cp -a /root/backup/index.ts.pre-v2928-20261006_213153        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2928-20261006_213153 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2928-20261006_213153    /opt/yl/www/CHANGELOG.md
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版（0.9.27）：bundle=c3b2c9bab29830de1f831b8d6d012171  server=a5927a49b17d5262aa12b3f61f27d740
# 整包：/root/backup/yl_pre_v2928_20261006_213153.tar.gz
```

★ 回滚注意：本批新增**表** `event_boss_hits5`。回滚到 0.9.27 时**无需删表**（旧代码不读它，多余表无害）；
**如需完全还原**用 `/root/backup/database_v2928_consistent_20261006_213153.sqlite`。

## 8. 0.9.28 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=47227cabf8eb5e1fa9bfe78d1de49e75        # 0.9.28 定版 index-v2928-20261006.js
PREV_SRV_MD5=3cecbaf388c7ab87a469f7ec2cf4df85           # 0.9.28 定版 srv/index_v28.ts（= s78.r175.ts，78 环）
PREV_CHANGELOG_MD5=41fa2b76f36ddad6ed19dafdb9dbb6a0     # 0.9.28 定版 CHANGELOG.md
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S78_MD5=3cecbaf388c7ab87a469f7ec2cf4df85       # 链尾 s78.r175.ts（供 0.9.28 单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。

## 9. 本批遗留（待用户）
- **R-176 服务端环（奇遇抽品阶）是否要做**：本批**未接线**（越界 + 用户未要求）。要做请明确「奇遇也要按境界收敛」，
  并确认可接受把白档压到 99.9%（或给出你想要的曲线）。
- **R-170 财富组成就奖励**：仍待你回选 A/B/C/D（线上目前是严格正比版，财富组末档 1 亿）。
- **R-175 历史逐只伤害回填**：如需要，另立数据迁移项。
