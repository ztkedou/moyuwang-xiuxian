# DEPLOY LOG · 0.9.30

> 生成方式：**手工复现 `deploy_v2830.sh` 的全部步骤**（本会话沙箱禁止起非 PowerShell shell ⇒ bash 脚本无法代跑；
> 已逐段照抄脚本的 ssh/scp 调用与 fail-closed 断言，并在每步后实测验证）。
> 上线时刻：**2026-10-07 20:38 (GMT+8)**

## 1. 范围

**0.9.30 = R-180~R-190 批次（11 条待办）里完成的 7 条**：5 个客户端补丁 + 1 个服务端补丁。

| 编号 | 模块 | 内容 | 交付物 |
|:--|:--|:--|:--|
| R-180 | 历练 | 三合一：①寿命减少累计 ②灵石事件概率 ③掉血改百分比 + 60 分硬上限 | `yl_r180_ext.py` |
| R-181 | 物品 | 筑基奇物属性实装（原 9 个读取点全是只读展示）+ 神识/身法 ÷8 | `yl_r181_ext.py` |
| R-183 | 修为体系 | 升级经验分级倍率 `K=[14,6,4,2.5,1.5,1,1]` | `yl_r183_ext.py` |
| R-185 | 洞府 | 「灵田联动」文案：可开垦 → 最大可扩展 | `yl_r185_ext.py` |
| R-186 | 挂机收益 | 离线收益恒 0（服务端第 **80** 环） | `srv_patch_r186.py` |
| R-188 | 打坐 | 天赋「一念悟道」15% 从未接线 ⇒ 接上 | `yl_r188_ext.py` |

（R-182 / R-184 / R-187 / R-189 / R-190 未在本批，留待后续。）

## 2. 指纹（部署后实测，全部与 `EXPECT_0830.env` 逐位一致）

| 项 | md5 | 大小 |
|---|---|---|
| 前端 bundle `index-v2930-20261007.js` | `4a765aa197694ff3175f29e8a38cc2c2` | 2,308,071 B |
| 服务端 `index_v28.ts`（= `s80.r186.ts`） | `bd7abfae10131e6099580c1163b51673` | 1,009,602 B |
| game-dicts.json | `1b635513f553875060869272b790f910` | 1,300,048 B |
| CHANGELOG.md | `9674d7ac2093bbe8d950bd204cf6cb39` | — |
| 客户端基座 `index-v26m-20260927.js` | `b315eb1a04e967a66c128861b3a3dadd` | 1,583,034 B |

**回滚点（原样保留在线上）**：
- `index-v2929-20261007.js` = `5d16be3568e02d2cde14c4302e74c7cf`（0.9.29 定版）
- `index-v2928-20261006.js` = `47227cabf8eb5e1fa9bfe78d1de49e75`（0.9.28 定版）
- 服务端上一版 `s79.r170b.ts` = `5ea456429a9e60f8f7458781fa63131f`

## 3. 装配登记

- 客户端 `STANDALONE_CLIENT` **30 → 35** 脚本（新增 `r180` / `r181` / `r183` / `r185` / `r188`）
- 服务端 `SRV_CHAIN` **79 → 80 环**（新增 `srv_patch_r186.py` = `s80.r186.ts`）
- 版本号**六处**同步为 `0.9.30`；`YLVERSION_FALLBACK = "0.9.30"`
- 构建：`chain_build.py --all` rc=0
- 预演：`dryrun_087.py` **FAIL=0**（standalone 门禁 896 条全绿）｜「预演==交付」md5 逐位相等
- 核对脚本本地预演：`sim_remote_check` **OK=553 / SKIP=15 / FAIL=0**

## 4. 部署步骤与实测

| 步骤 | 动作 | 结果 |
|---|---|---|
| 0b | 远端备份 + **3 条漂移断言** | ✅ 3/3 通过；六件 `.pre-v2930-<TS>` + `yl_pre_v2930_<TS>.tar.gz` |
| 0b补 | DB 一致性快照 | ⚠️ 远端无 `sqlite3` CLI，node 驱动回退命令引号未过 ⇒ **仅留热拷贝** `database.sqlite.pre-v2930-<TS>`（脚本本身亦为优雅降级） |
| 1 | 上传（`.new` → 验 md5 → 原子改名） | ✅ bundle `4a765aa1…` 校验通过；服务端 `.new` = `bd7abfae…` |
| 2 | 服务端原子换版 | ✅ `node --check PASS`｜维护标志已解除｜service **active**｜NRestarts **0** |
| 3 | `index.html` 换指向 + gz 全站同步 | ✅ 指向新包，**平台注入块保留**；`index.html.gz` **已重建并校验**；`OK=4 / STALE=0 / ORPHAN=0` |
| 4 | 核验 + 公开冒烟 | ✅ 见下表 |
| 5 | `remote_check_v2830.sh` | ✅ **PASS (0 failures)** |

### 4.1 公开冒烟（含「浏览器视角」的 gzip 硬断言 —— R-159 铁律）

```
index.html                       = 200
gzip_static index.html 含新包    = 1      ← ★ 关键（旧壳陷阱）
new bundle                       = 200
old bundle kept（回滚点）        = 200
api/teahouse/today（无 token）   = 401
api/fun/dice POST（无 token）    = 401
service = active ｜ NRestarts = 0 ｜ maint flag = absent
```

### 4.2 线上包内本批标记（证明补丁真的进了产物）

```
[r180adv]=1  [r181equip]=1  [r183exp]=1  [r185farm]=1  [r188med]=1
[r186offline] in server = 2
```

## 5. 本批踩坑与处置（★ 全部已固化进技能 / 记忆）

### 5.1 并行编写必然产生的**三类冲突**（本批全部真实踩到）

| 类型 | 实例 | 处置 |
|---|---|---|
| ① 补丁之间 | `yl_r188_ext.py` 把 `[r180adv]` 钉成 `expect==0`（写它时 r180 还没进同一产物）⇒ 集成时 ABORT | 扫全量删 **8 条**同类（其中 **6 条是 `expect==1`**，用「只查 `==0`」扫不到）；给出**顺序无关性证明**（两顺序产物 SHA256 逐位相同） |
| ② 顺序依赖 | 「换顺序能绕过」但脆弱 | 要求 SHA256 级证明 |
| ③ **新补丁合法改写旧针脚** | R-180 改了 `$>100?x*=.88` / `Ge(t,200,500,490)` / `Ge(t,30,80,470)` / `t.hpChange*u*0.25` ⇒ `yl_r134/r139/r145/r177` 的 **8 条冻结针脚** + `dryrun` 若干条 + `remote_check` 的「R178 三档权重已改」全部失效 | **退役**（`RETIRED_TAG`：保留整行 + 显式声明退役 + apply 态跳过、终态仍复核）。**不要**把老针脚改成新形态（会让老补丁依赖新补丁） |

**③ 里藏着一个机械矛盾**：`gates()` 被 **apply 态**与**终态**两处共用 ⇒
**一条 `(needle, expect)` 不可能同时满足两个时刻** ⇒ 必须显式区分两态（`RETIRED_TAG`）或删掉那条断言。

### 5.2 其他

- **核对脚本断言要选对变量**：客户端补丁的标记在 `$B`（bundle），服务端环的标记在 `$S`。写错会得到一片假 FAIL（本批我第一版就写错了 20 条）。
- **`remote_check` 的 `PREV_SRV_MD5` 语义是「上一版」**（用于「`--skip-server` 忘传服务端」告警比对），
  **不能填本版新值** —— 否则「新值比新值」必然误报 WARN。已修正生成器。
- **本会话沙箱禁止起非 PowerShell shell** ⇒ `deploy_v2830.sh` 无法代跑；本次为**手工逐段复现**其 ssh/scp 步骤。

## 6. 回滚

```bash
# 客户端：把 index.html 指回 0.9.29（.gz 必须同批重建！R-159）
ssh root@104.208.x.x
cd /opt/yl/www
sed -i 's#assets/index-v2930-20261007\.js#assets/index-v2929-20261007.js#' index.html
bash /opt/yl/server/_remote_gz_sync.sh          # 重建 index.html.gz
# 服务端：换回 s79.r170b.ts 并重启
cp /root/backup/index.ts.pre-v2930-<TS> /opt/yl/server/index.ts
systemctl restart yl-server
```

**备份位置**：`/root/backup/yl_pre_v2930_<TS>.tar.gz` + 六件 `.pre-v2930-<TS>` + `database.sqlite.pre-v2930-<TS>`
（`<TS>` = `20261007-203736`）
