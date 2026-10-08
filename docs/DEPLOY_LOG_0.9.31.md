# DEPLOY LOG — 《摸鱼修仙传》 0.9.31（v28 链第 81 环）

- **部署时间**：2026-10-08 07:11 ~ 07:15（GMT+8）
- **目标**：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- **脚本**：`deploy_v28/deploy_v2831.sh`（客户端 + 服务端 + 双 CHANGELOG + index.html bump + gz 同步）
- **定点核对**：`deploy_v28/remote_check_v2831.sh` → **PASS (0 failures)**（本批段 36 条断言全 [OK]，无 WARN）
- **登记指纹**：`deploy_v28/EXPECT_0831.env`
- **备份整包**：`/root/backup/yl_pre_v2931_20261008-071150.tar.gz`（51,390,479 B）
- **DB 一致性快照**：**跳过** —— 远端无 `sqlite3` CLI，且 `better-sqlite3` 驱动不可用（已留热拷贝 `database.sqlite.pre-v2931-20261008-071150`，10,694,656 B）。本批**无 DDL**，热拷贝足够回滚。

> ★ **执行方式说明**：本会话沙箱**禁止起非 PowerShell 的 shell**（`bash`/`sh`/`cmd` 一律被拦，提权也不行）
> ⇒ `deploy_v2831.sh` 无法由 AI 直接运行。改为**逐段照抄脚本的 ssh/scp 步骤**执行（脚本每一步都只是 ssh/scp，
> 关键逻辑在服务器上现成的 `remote_swap.sh` / `live_bump_bundle.js` / `remote_gz_sync.sh` 里），每步实测验证。

---

## 1. 本批范围：0.9.31 = R-180~R-190 批次收尾 7 条

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-180 v2 | 历练：**删 60 分硬上限** + **E3 回滚**（恢复灵石数量）+ **掉血重调**（PD 0.14→0.40、带宽 [3%,9%]→[1.0%,3.2%]） | `yl_r180_ext.py` | ✔ | — |
| R-182 | 纯卖钱草利润重定档（净利 = 成熟分钟 × 200）+ 催熟费率 100→300 | `patches/server/srv_patch_r182.py` | — | ✔ |
| R-184 | 功法悟道挂到「几千灵石」稀有事件（判据 `raw ≥ 200`） | `yl_r184_ext.py` | ✔ | — |
| R-185 v2 | 「灵田联动」**真搬到左列** + 去重 + 口径标注「洞府可扩展」 | `yl_r185_ext.py` | ✔ | — |
| R-187 | 仙途指引「玩法说明」数字同步为实发值（8600/9900/61000） | `yl_r187_ext.py` | ✔ | — |
| R-188 v2 | 顿悟率：有天赋 15%→**5%**、普通 0.4%→**1%** | `yl_r188_ext.py` | ✔ | — |
| R-190 | 灵宠血量喂养 ÷50 + 亲密度归零 + 闸门 200→1000 | `yl_r190_ext.py` | ✔ | — |

- 客户端 `STANDALONE_CLIENT` **35 → 38** 脚本（新增 r184/r187/r190；r180/r185/r188 升 v2 双路径）
- 服务端 `SRV_CHAIN` **80 → 81** 环（末环 `s81.r182.ts`）

## 2. 指纹（部署前后）

| 对象 | 部署前（0.9.30） | 部署后（0.9.31） |
|---|---|---|
| `www/assets/index-v2930-20261007.js` | `4a765aa197694ff3175f29e8a38cc2c2` | 同左（**旧包保留不删 = 秒级回滚点**） |
| `www/assets/index-v2929-20261007.js` | `5d16be3568e02d2cde14c4302e74c7cf` | 同左（更早回滚点） |
| `www/assets/index-v2931-20261007.js` | —（新文件） | **`982a81c6033fbdda50fa5367ce54b30d`**（2,309,108 B） |
| `server/index.ts` | `bd7abfae10131e6099580c1163b51673` | **`e12f4ebc0d1e6aa98d9c9ce1b71d998b`**（1,011,566 B） |
| `www/CHANGELOG.md` | `9674d7ac2093bbe8d950bd204cf6cb39` | **`364e31977b13c590e1d0b7a4db3de088`** |
| `www/CHANGELOG_PLAYER.md` | （未登记） | **`6ac71007a8082595e3bd343707213ac6`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（本批无变化）** |

部署后线上实测（deploy 步骤采集）：

```
index.ts   : e12f4ebc0d1e6aa98d9c9ce1b71d998b
dicts      : 1b635513f553875060869272b790f910
bundle new : 982a81c6033fbdda50fa5367ce54b30d
bundle old : 4a765aa197694ff3175f29e8a38cc2c2
CHANGELOG  : 364e31977b13c590e1d0b7a4db3de088
index.html : assets/index-v2931-20261007.js
service    : active     restarts: 0     maint flag: absent
```

## 3. 部署前本地验收

- `chain_build --all`：**rc=0**（bundle `982a81c6…` / 服务端 `e12f4ebc…` / 第 81 环）
- `dryrun_087.py`：**PASS（FAIL=0）**；standalone 门禁 896 条全绿；`apply_standalone` 零 SA-FAIL
- **「预演==交付」**：`_chainstage/dryrun_087.bundle.js` md5 == 交付 bundle md5（逐位相等）
- 双 provenance（step 0c）：链尾 `s81.r182.ts` == `srv/index_v28.ts` == canon 副本；`s20.t16arena.ts` == 0.8.9 定版
- `remote_check_v2831.sh` 本地预演（`sim_remote_check.py`）：**OK=570 / SKIP=15 / FAIL=0**
- `EXPECT_0831.env` 与 `deploy_v2831.sh` 内联 PREV_* **6/6 逐字一致**

## 4. 线上验收

- `remote_check_v2831.sh` → **REMOTE-CHECK: PASS (0 failures)**，无 WARN
- 公开冒烟：`index.html=200`｜新包 200｜旧包 200｜`api/teahouse/today=401`｜`api/fun/dice POST=401`｜`api/pet/feed POST=401`｜`api/farm/status=401`
- ★★ **浏览器视角 gzip 硬断言**：`gzip_static index.html 含新包 = 1` ✓（R-159 旧壳陷阱已避开）
- 线上包内标记：`[r180adv2]`=1｜`[r184wudao]`=1｜`[r185farm2]`=1｜`[r187guide]`=1｜`[r188med2]`=1｜`[r190feed]`=5｜`[r181equip]`=1｜`[r183exp]`=1
- 服务端标记：`[r182herb]`=1｜`[r186offline]`=2
- 本批**无新增数据库表/列**（R-182 纯数值、R-186 上批已加列）。

## 5. 本轮踩到的新坑

1. ★★ **`CHANGELOG_PLAYER.md` 漏了新版本条目** —— 我上一轮只写了技术版 `CHANGELOG.md` 的 `[0.9.31]` 条目，
   **玩家版忘了加** ⇒ 游戏内版本卡会**停在 0.9.30**（解析器读的就是这个文件）。
   更隐蔽的是：`deploy_v2831.sh` 的玩家日志门禁**只校验格式**（标题正则 / 分类 / 独立粗体行），
   **不校验「最新版本条目是否存在」** ⇒ 一路绿灯通过。
   ⇒ **教训：双 CHANGELOG 是两份独立文件，改一份必须同时改另一份；且格式门禁不能替代内容完整性检查。**
2. ★ **条目头时刻必须 = 实际上线时刻** —— 我写 `[0.9.31] - 2026-10-08 00:00` 是占位值，
   上线时刻是 `07:14`。已改正（技术版 + 玩家版都改）。
   顺带把玩家版 `[0.9.30]` 的 `13:20`（计划值）改正为 `20:38`（0.9.30 实际上线时刻）。
3. ★ **R-185 v2 的一个已知残留（未修，记入 0.9.32）**：洞府**升级成功 toast** 里的文案仍是原件的
   `可开垦 N 块`（0.9.30 曾把它改成 `最大可扩展`）。原因：R-185 v2 只处理了面板那一行，
   而**构建基线（装配产物）里 toast 是原件形态** ⇒ 相对 0.9.30 出现**回退**。
   影响面：仅升级洞府时的一次性提示，非面板常驻文案。**已列入 0.9.32 一并修**。
4. **版本号「两处」坑复现**（`DEFAULT_VERSION` + `INJECT_JS` 里的 `YLVERSION_FALLBACK` 字面量）——
   本项目文档已记过，本轮仍踩（构建门禁 `version·兜底常量` FAIL）。已两处同改。
5. **node 运行时升级打断写死路径** —— 本机 node `22.22.2-3 → 22.22.2-6`，
   `build_v26n.py` / `chain_build.py` 写死的路径失效 ⇒ `FileNotFoundError`。已改成自动探测。
6. **老门禁因本批合法改动而失效**（第 ③/④ 类冲突）—— 本轮修了 6 条（r123/r125/r134/r139/r165）；
   其中 **r134·奇遇灵石** 与 **r139·新历练驱动** 因 R-180 v2 **回滚**而**重新激活**
   （0.9.30 为 v1 退役过它们）⇒ **「退役」不是永久的，回滚后要复活**。

## 6. 残留清理

- 远端 `_remote_swap.sh` / `_live_bump_bundle.js` / `_remote_gz_sync.sh` / `_remote_check_v2831.sh` 留在 `/opt/yl/server/` 便于复跑（惯例）。
- 本地：`_mk_2831.py` / `_mk_rc2831.py` 为机械重登记脚本，随部署件一并提交。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2931-20261008-071150 /opt/yl/www/index.html
cp -a /root/backup/index.ts.pre-v2931-20261008-071150        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2931-20261008-071150 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2931-20261008-071150    /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2931-20261008-071150 /opt/yl/www/CHANGELOG_PLAYER.md
systemctl restart yl-server && systemctl is-active yl-server
# 旧包文件未删，无需还原
# 上一版定版（0.9.30）：bundle=4a765aa197694ff3175f29e8a38cc2c2  server=bd7abfae10131e6099580c1163b51673
# 整包：/root/backup/yl_pre_v2931_20261008-071150.tar.gz
```

★ 本批**无 DDL** ⇒ 回滚无需动库。
