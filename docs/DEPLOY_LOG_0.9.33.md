# DEPLOY LOG — 《摸鱼修仙传》 0.9.33（v28 链第 81 环，**纯客户端批**）

- **部署时间**：2026-10-08 08:29 ~ 08:34（GMT+8）
- **目标**：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- **脚本**：`deploy_v28/deploy_v2833.sh`（**以 `--skip-server` 语义执行**：服务端无变化）
- **定点核对**：`deploy_v28/remote_check_v2833.sh` → **PASS (0 failures)**，1 条 **预期 WARN**（见 §5.1）
- **登记指纹**：`deploy_v28/EXPECT_0833.env`
- **备份整包**：`/root/backup/yl_pre_v2933_20261008-082940.tar.gz`
- **DB 一致性快照**：跳过（远端无 `sqlite3` CLI / `better-sqlite3`；已留热拷贝 `database.sqlite.pre-v2933-20261008-082940`）。本批**无 DDL**。

## 1. 本批范围：0.9.33 = R-180 v4 + R-189 第 1 批

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| **R-180 v4** | 自动历练「灵石产出分布」再降一档：**EV 奇遇率 `0.03 → 0.01`**（「几千」3% → **1%**） | `localtest/yl_r180_ext.py`（v3→v4） | ✔ | — |
| **R-189 第 1 批** | 妖灵系统「说明 vs 实际」对齐（**纯文案/标签，零逻辑改动**） | `localtest/yl_r189_ext.py`（**新增**） | ✔ | — |

- `STANDALONE_CLIENT` **38 → 39 脚本**；`SRV_CHAIN` **仍 81 环**（`srv/index_v28.ts` 逐字节未变）。

### R-180 v4 分布（n=30 万/境界）

| 境界 | v3 几千 | **v4 几千** | v4 常态 / 几百 |
|---|---|---|---|
| 炼气 L1 | 3.00% | **1.00%** | 84.30% / 14.71% |
| 金丹 L1 | 3.00% | **0.99%** | 86.09% / 12.92% |
| 元婴 L1 | 3.08% | **1.04%** | 86.97% / 11.99% |
| 合道 L1 | 2.97% | **1.03%** | 88.20% / 10.78% |
| 长生 L1 | 4.85% | **2.94%** | 87.02% / 10.03% |

- ★ **连带效应**：R-184 悟道挂在「几千」事件上 ⇒ 触发率同步降为 1/3：炼气 ≈6.0 分/次 → **≈18.0 分/次**；长生 ≈3.7 分 → **≈6.1 分**。**R-184 文件未改。**
- E1 / E2 / E3 / E4 / **E5·E6·E7（掉血三处）** 逐字不动。

### R-189 第 1 批（12 处文案/标签）

① 「灵宠作用 / 妖灵本体」→ **「灵宠口径参考（非当前加成）」**（原显示 ≈ 实际的 **425 倍**；且复核发现「归位后预览」也不成立 —— 归位写入用的是**等级 1** 的属性）；
② 互动次数标题去掉**虚假总上限**（真实：每种各 1 次免费 + 可花 20000 各买 1 次 ⇒ 最多 5 次）；
③ 进食行补 **「· 今日首次免费」**（消费 `feedQuota.free`）；
④ 术语统一（**喂食度** / **收养** / **进食** / **互动**，旧词全库清零）；
⑤ 两个「秘径」区分：**妖灵秘径·派遣** vs **灵兽秘径·单次**；
⑥ 玩法记录补全 7 类标签（`battle` 「斗法」→ **「精魄」**）；
⑦ 说明②补 品阶K / 等级K 定义 + 资质K 上限。

## 2. 指纹（部署前后）

| 对象 | 部署前（0.9.32） | 部署后（0.9.33） |
|---|---|---|
| `www/assets/index-v2932-20261008.js` | `f01c120e8240e4bb779a554c2102eeaa` | 同左（**旧包保留不删 = 秒级回滚点**） |
| `www/assets/index-v2931-20261007.js` | `982a81c6033fbdda50fa5367ce54b30d` | 同左（更早回滚点） |
| `www/assets/index-v2933-20261008.js` | —（新文件） | **`babae2e2b0cb92f07e0278c5840b1766`**（2,310,491 B） |
| `server/index.ts` | `e12f4ebc0d1e6aa98d9c9ce1b71d998b` | **同左（本批未变）** |
| `www/CHANGELOG.md` | `5f828e55d11f007c5858d481460d1bae` | **`3a585415c8fa18b7e0992dfef6947a0a`** |
| `www/CHANGELOG_PLAYER.md` | `659b5edc65e8d0c0d9c1fa812200efb3` | **`f051682c611628b3419d2bbf45d1b213`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（未变）** |

部署后线上实测：

```
index.ts   : e12f4ebc0d1e6aa98d9c9ce1b71d998b
bundle new : babae2e2b0cb92f07e0278c5840b1766
bundle prev: f01c120e8240e4bb779a554c2102eeaa
CHANGELOG  : 3a585415c8fa18b7e0992dfef6947a0a
index.html : assets/index-v2933-20261008.js
service    : active   restarts: 0   ActiveEnterTimestamp: Thu 2026-10-08 07:12:35 CST   ← ★ 未重启（零停机）
maint flag : absent (ok)
```

## 3. 部署前本地验收

- `chain_build --all`：**rc=0**（bundle `babae2e2…`；服务端 `e12f4ebc…` 未变）
- `dryrun_087.py`：**PASS（FAIL=0）**，**4248 条门禁**
- **「预演==交付」**：`_chainstage/dryrun_087.bundle.js` md5 == 交付 bundle md5（逐位相等）
- 双 provenance：链尾 `s81.r182.ts` == `srv/index_v28.ts` == canon；`s20.t16arena.ts` == 0.8.9 定版
- `remote_check_v2833.sh` 本地预演（`sim_remote_check.py`）：**OK=558 / SKIP=15 / FAIL=0**
- `EXPECT_0833.env` 与 `deploy_v2833.sh` 内联 PREV_* **6/6 逐字一致**

## 4. 线上验收

- `remote_check_v2833.sh` → **REMOTE-CHECK: PASS (0 failures)**
- 公开冒烟：`index.html=200`｜新包 200｜上一版包 200｜`api/teahouse/today=401`｜`api/fun/dice POST=401`｜`api/pet/feed POST=401`
- ★★ **浏览器视角 gzip 硬断言**：`gzip_static index.html 含新包 = 1` ✓（R-159 旧壳陷阱已避开）
- 线上包内标记：`[r180adv4]`=1｜`[r189ui]`=1｜`[r185farm3]`=1｜`[r190feed]`=5｜`[r184wudao]`=1
- 线上文案：**`饱食度` = 0** ✓｜**`结缘` = 0** ✓

## 5. 本轮踩到的新坑

1. **R-189 与 R-167 的 ③ 类冲突（新补丁合法改写旧补丁钉住的串）**：
   R-167（0.9.25）当年钉了「新标题就位」（`今日互动 X/3（每种每日首次免费）`）与「首免文案在位」两条门禁；
   **R-189 第 1 批把该标题合法改写**为「免费互动已用 N/3 次（…每种每日免费 1 次…）」并把首免提示移到进食行 ⇒ 两条门禁失效。
   - **处置**：在 `yl_r167_ext.py` 的 `gates()` 里**退役**这两条（注释留痕 + 说明新形态由 R-189 门禁覆盖）；
     **同步退役** `remote_check_v2833.sh` 里的对应两条（`_mk_rc2833.py` 按行定位替换）。
   - ★ 用**按行定位**而非整行字面匹配 —— 那两条含 `\uXXXX` 转义串，整行匹配易被编码坑（本轮第一次就踩了）。
2. **`_mk_2833.py` 的 diff 头断言**：上一版生成器把 `deploy_v2831.sh` 的 diff 头保留下来当锚点；
   本版若只做「整名替换」而不重建 diff 头，`assert s.count("deploy_v2832.sh") == 1` 必挂。
   ⇒ 改为**锚在 `# 与 deploy_v2831.sh 的差别：`**，替换为「本批说明段 + `# 与 deploy_v2832.sh 的差别：`」。
3. **纯客户端批的「预期 WARN」再现**（与 0.9.32 同）：`PREV_SRV_MD5` 与线上实际值相同 ⇒
   remote_check 的「服务端没换？」WARN **必然触发且属预期**，**勿当误报去改预期值**。
4. 顺带清掉一个被误建在 `build/assets/` 的 **0 字节垃圾文件**（某代理的 `>` 重定向写歪）。
   ★ 另：`build/assets/` 累积了 **924 个历轮自动备份（合计 1.96 GB，均被 `.gitignore` 忽略）** —— 待用户决定是否清理。

## 6. 残留清理

- 远端 `_live_bump_bundle.js` / `_remote_gz_sync.sh` / `_remote_check_v2833.sh` 留在 `/opt/yl/server/` 便于复跑（惯例）。
- 本地 `_mk_2833.py` / `_mk_rc2833.py` 为机械重登记脚本，随部署件一并提交。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2933-20261008-082940 /opt/yl/www/index.html
cp -a /root/backup/CHANGELOG.md.pre-v2933-20261008-082940    /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2933-20261008-082940 /opt/yl/www/CHANGELOG_PLAYER.md
# ★ 服务端本批未动 ⇒ 无需还原 index.ts / game-dicts.json、**无需重启服务**
# 上一版定版（0.9.32）：bundle=f01c120e8240e4bb779a554c2102eeaa  server=e12f4ebc0d1e6aa98d9c9ce1b71d998b
# 整包：/root/backup/yl_pre_v2933_20261008-082940.tar.gz
```

★ 本批**无 DDL**、**未重启服务** ⇒ 回滚只需换回 `index.html` + 两份 CHANGELOG（旧包文件未删，秒级生效）。
