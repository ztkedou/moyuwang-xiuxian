# DEPLOY LOG — 《摸鱼修仙传》 0.9.32（v28 链第 81 环，**纯客户端批**）

- **部署时间**：2026-10-08 07:51 ~ 07:56（GMT+8）
- **目标**：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- **脚本**：`deploy_v28/deploy_v2832.sh`（**以 `--skip-server` 语义执行**：服务端无变化）
- **定点核对**：`deploy_v28/remote_check_v2832.sh` → **PASS (0 failures)**，1 条 **预期 WARN**（见 §5.1）
- **登记指纹**：`deploy_v28/EXPECT_0832.env`
- **备份整包**：`/root/backup/yl_pre_v2932_20261008-075155.tar.gz`（52,028,289 B）
- **DB 一致性快照**：跳过（远端无 `sqlite3` CLI / `better-sqlite3`；已留热拷贝 `database.sqlite.pre-v2932-20261008-075155`，10,694,656 B）。本批**无 DDL**。

> ★ 执行方式：沙箱仍**禁止起非 PowerShell 的 shell** ⇒ 逐段照抄脚本的 ssh/scp 步骤执行（同 0.9.30/0.9.31）。

---

## 1. 本批范围：0.9.32 = 两只补丁升 v3（**无新增补丁、无新增服务端环**）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| **R-180 v3** | 自动历练「灵石产出分布」重做：**E2** 主路中档改按模板 raw 灵石分档（`$>100?x*=.30` → `S.spiritStonesChange>=40?x*=0.7`）；**EV** 奇遇率常数化（`B=.05,Y=U*.02,…` → `V=Math.min(.3,0.03+(t.luck||0)*.001)`） | `localtest/yl_r180_ext.py` | ✔ | — |
| **R-185 v3** | 洞府**升级 toast** 文案回退修复（`可开垦` / `最大可扩展` → **`洞府可扩展`**） | `localtest/yl_r185_ext.py` | ✔ | — |

- `STANDALONE_CLIENT` **仍 38 脚本**；`SRV_CHAIN` **仍 81 环**（`srv/index_v28.ts` 逐字节未变）。

### R-180 v3 分布（node 真跑，n=30 万/境界）

| 口径 | 境界 | 常态(≤150) | 几百(151-900) | 几千(≥1000) |
|---|---|---|---|---|
| 改前（0.9.31） | 炼气 L1 | 84.6% | 10.4% | **4.98%** |
| 改前 | 长生 L1 | **68.6%** | 9.4% | **22.07%** |
| **改后** | 炼气 L1 | **83.3%** | 13.7% | **2.99%** |
| **改后** | 长生 L1 | 78.8% | 10.1% | 11.14%（绝对档；相对档 4.93%） |

- **相对档位极差 ≤3.2pp**（炼气 2.97% ~ 长生 4.93%）⇒「全境界概率统一」达成；长生多出的 ~1.9pp 来自 `longevityRule` 专属模板（`Fm` 冻结闸门，不可改）。
- 实结算均值 **150（炼气）→ 702（长生）** 单调上升 ⇒「数量随等级不同」达成。
- **★ 口径判定**：「全境界概率统一」与「数值随境界提升」在**绝对档位**下数学上不可兼得（结算值 = raw × u × 5.1）。按用户原话「只是不同等级灵石的数量不同」⇒ 采**相对档位**。
- **联动**：R-184 悟道判据 `raw≥200` ⟺ 奇遇 ⇒ 触发频率由「5%~19% 随境界爬升」变为**全境界统一 ~3%**（长生 4.87%）。**R-184 未改**。

## 2. 指纹（部署前后）

| 对象 | 部署前（0.9.31） | 部署后（0.9.32） |
|---|---|---|
| `www/assets/index-v2931-20261007.js` | `982a81c6033fbdda50fa5367ce54b30d` | 同左（**旧包保留不删 = 秒级回滚点**） |
| `www/assets/index-v2930-20261007.js` | `4a765aa197694ff3175f29e8a38cc2c2` | 同左（更早回滚点） |
| `www/assets/index-v2932-20261008.js` | —（新文件） | **`f01c120e8240e4bb779a554c2102eeaa`**（2,309,111 B） |
| `server/index.ts` | `e12f4ebc0d1e6aa98d9c9ce1b71d998b` | **同左（本批未变）** |
| `www/CHANGELOG.md` | `364e31977b13c590e1d0b7a4db3de088` | **`5f828e55d11f007c5858d481460d1bae`** |
| `www/CHANGELOG_PLAYER.md` | `6ac71007a8082595e3bd343707213ac6` | **`659b5edc65e8d0c0d9c1fa812200efb3`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（未变）** |

部署后线上实测：

```
index.ts   : e12f4ebc0d1e6aa98d9c9ce1b71d998b
bundle new : f01c120e8240e4bb779a554c2102eeaa
bundle prev: 982a81c6033fbdda50fa5367ce54b30d
CHANGELOG  : 5f828e55d11f007c5858d481460d1bae
index.html : assets/index-v2932-20261008.js
service    : active   restarts: 0   ActiveEnterTimestamp: Thu 2026-10-08 07:12:35 CST   ← ★ 未重启（零停机）
maint flag : absent (ok)
```

## 3. 部署前本地验收

- `chain_build --all`：**rc=0**（bundle `f01c120e…`；服务端 `e12f4ebc…` 未变）
- `dryrun_087.py`：**PASS（FAIL=0）**，**4248 条门禁**
- **「预演==交付」**：`_chainstage/dryrun_087.bundle.js` md5 == 交付 bundle md5（逐位相等）
- 双 provenance：链尾 `s81.r182.ts` == `srv/index_v28.ts` == canon；`s20.t16arena.ts` == 0.8.9 定版
- `remote_check_v2832.sh` 本地预演（`sim_remote_check.py`）：**OK=560 / SKIP=15 / FAIL=0**
- `EXPECT_0832.env` 与 `deploy_v2832.sh` 内联 PREV_* **6/6 逐字一致**

## 4. 线上验收

- `remote_check_v2832.sh` → **REMOTE-CHECK: PASS (0 failures)**
- 公开冒烟：`index.html=200`｜新包 200｜上一版包 200｜`api/teahouse/today=401`｜`api/fun/dice POST=401`
- ★★ **浏览器视角 gzip 硬断言**：`gzip_static index.html 含新包 = 1` ✓（R-159 旧壳陷阱已避开）
- 线上包内标记：`[r180adv3]`=1｜`[r185farm3]`=1｜`[r185farm2]`=1｜`[r184wudao]`=1｜`[r187guide]`=1｜`[r188med2]`=1｜`[r190feed]`=5
- 线上文案：**`可开垦` = 0** ✓｜`洞府可扩展`（裸 UTF-8，toast）= 1 ✓

## 5. 本轮踩到的新坑

1. ★ **纯客户端批会触发一条「预期 WARN」**：`remote_check` 的 `PREV_SRV_MD5` 语义是「**上一版**的服务端 md5」；
   本批服务端**无变化** ⇒ 该值 == 线上实际值 ⇒ 「服务端没换？」WARN **必然触发**。
   ⇒ **不是缺陷**（FAIL 计数不受影响），已在 `remote_check_v2832.sh` 的注释里写清；**勿把它当误报去改预期值**。
2. ★★ **我自己的编辑错误：插入新条目时吃掉了上一版的 `## [x.y.z]` 条目头** ——
   写 0.9.32 条目时，`old_string` 以 `## [0.9.31] - …` 结尾，而 `new_string` **忘了把它补回去** ⇒
   0.9.31 的正文变成 0.9.32 的子节、`## [0.9.31]` 计数归 0 ⇒ remote_check 的「历史条目保留」断言 **FAIL 1 条**。
   ⇒ **教训：用「锚在条目头」的方式插入新版本时，务必把被锚定的那一行原样写回 new_string 末尾**
   （玩家版那次我写回了，技术版漏了 ⇒ 两份不同步）。已修并重传。
3. ★ **`Set-Content -Encoding UTF8`（PS 5.1）会加 BOM，且 `-NoNewline` 会把多行拼成一行** ——
   我一度把 `EXPECT_0832.env` 改成单行 + 潜在 BOM。BOM 会**破坏 `bash source`**。
   ⇒ 已改用 Python 以 `utf-8 / newline=""` 重写，并断言「无 BOM / 纯 LF / 以换行结尾」。
4. ★ **PowerShell 变量名大小写不敏感**：`$h`（md5）覆盖了 `$H`（主机名）⇒ scp 把哈希当主机名解析失败。已避开。
5. ★ **跨天批次**：0.9.32 是 **10-08 批**（0.9.29/30/31 同属 10-07 批）⇒ 六处包名/日期 + 两个部署脚本的
   `BUNDLE_DATE` 默认值全部同步为 `20261008`（历史踩过坑：漏改 ⇒ 2 条假 FAIL）。

## 6. 残留清理

- 远端 `_live_bump_bundle.js` / `_remote_gz_sync.sh` / `_remote_check_v2832.sh` 留在 `/opt/yl/server/` 便于复跑（惯例）。
- 本地 `_mk_2832.py` / `_mk_rc2832.py` 为机械重登记脚本，随部署件一并提交。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2932-20261008-075155 /opt/yl/www/index.html
cp -a /root/backup/CHANGELOG.md.pre-v2932-20261008-075155    /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2932-20261008-075155 /opt/yl/www/CHANGELOG_PLAYER.md
# ★ 服务端本批未动 ⇒ 无需还原 index.ts / game-dicts.json、**无需重启服务**
#    （如确需还原：cp -a /root/backup/index.ts.pre-v2932-… 后 systemctl restart yl-server）
# 上一版定版（0.9.31）：bundle=982a81c6033fbdda50fa5367ce54b30d  server=e12f4ebc0d1e6aa98d9c9ce1b71d998b
# 整包：/root/backup/yl_pre_v2932_20261008-075155.tar.gz
```

★ 本批**无 DDL**、**未重启服务** ⇒ 回滚只需换回 `index.html` + 两份 CHANGELOG（旧包文件未删，秒级生效）。
