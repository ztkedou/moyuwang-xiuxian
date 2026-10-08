# DEPLOY LOG — 《摸鱼修仙传》 0.9.34（v28 链 **第 84 环**）

- **部署时间**：2026-10-08 09:46 ~ 09:52（GMT+8）
- **目标**：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- **脚本**：`deploy_v28/deploy_v2834.sh`（客户端 + **服务端 3 新环** + 双 CHANGELOG + index.html bump + gz 同步）
- **定点核对**：`deploy_v28/remote_check_v2834.sh` → **PASS (0 failures)**，**无 WARN**
- **登记指纹**：`deploy_v28/EXPECT_0834.env`
- **备份整包**：`/root/backup/yl_pre_v2934_20261008-0948xx.tar.gz`
- ★★ **本批服务端有变** ⇒ **重启了 yl-server**（`ActiveEnterTimestamp = 09:48:10`，NRestarts 0，maintenance flag 已解除）。

## 1. 本批范围：0.9.34 = **8 条**（客户端 7 补丁 + 服务端 3 环）

| # | 任务 | 落点 |
|---|---|---|
| **R-191** | 奇遇率修复（`V` 被幸运项顶到 30% 上限）+ 结算日志「分档」统计 | `yl_r191_ext.py` |
| **R-193** | 奇遇率 v2：**幸运彻底移除**，改由**称号**承载（封顶 +3% ⇒ 默认 1% / 顶配 4%） | `yl_r193_ext.py` |
| **R-191**（台账） | 融合弹窗「标题错误 / 内容成功」⇒ `doToast` 按 `tone` 分派 | `yl_r192_ext.py` |
| **R-194** | 悟道**十道均匀随机**（原「只在已开放道里随机」⇒ 炼气恒血道） | `srv_patch_r194.py`（**第 84 环**） |
| **R-195** | 妖灵归位：修等级 bug + 属性倍率 M∈[1.5,3.375]（基准 2.25）+ 保留原名「妖灵·X」+ 独立一类灵宠 | `yl_r195_ext.py` |
| **R-196** | 灵纹前 4 条重设（后 2 条逐字未动） | `srv_patch_r196.py`（**第 83 环**）+ `yl_r196_ext.py` |
| **R-189** | 主人加成 **6% → 10%** | `srv_patch_r191.py`（**第 82 环**）+ `yl_r189b_ext.py` |
| **R-189** | 灵纹**可见化**（4 条经取证全部已实装 ⇒ 数值零改动） | `yl_r189c_ext.py` |

- 客户端 `STANDALONE_CLIENT` **39 → 46 脚本**（新增 7；★ `yl_r194_ext.py` **刻意不集成**）
- 服务端 `SRV_CHAIN` **81 → 84 环**（`s82.r191` / `s83.r196` / `s84.r194`）
- ★ **顺序约束**：`r189c` → `r196`（r196 追加在 r189c 的可见化行内）；`r191` → `r193`（r193 取代 r191 的公式）

## 2. 指纹（部署前后）

| 对象 | 部署前（0.9.33） | 部署后（0.9.34） |
|---|---|---|
| `www/assets/index-v2933-20261008.js` | `babae2e2b0cb92f07e0278c5840b1766` | 同左（**旧包保留不删 = 秒级回滚点**） |
| `www/assets/index-v2932-20261008.js` | `f01c120e8240e4bb779a554c2102eeaa` | 同左（更早回滚点） |
| `www/assets/index-v2934-20261008.js` | —（新文件） | **`550efc63d2289efa2795b1dc1bbda115`**（2,313,677 B） |
| `server/index.ts` | `e12f4ebc0d1e6aa98d9c9ce1b71d998b`（81 环） | **`4cd3632ceebee7a50c6943d89da4c23d`**（1,011,716 B / **84 环**） |
| `www/CHANGELOG.md` | `3a585415c8fa18b7e0992dfef6947a0a` | **`565b030cf7fe98c6383a6f91478aa544`** |
| `www/CHANGELOG_PLAYER.md` | `659b5edc65e8d0c0d9c1fa812200efb3` | **`fa83e3539be679bd46b6306494dc4be4`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（未变）** |

## 3. 部署前本地验收

- `chain_build --all`：**rc=0**（bundle `550efc63…`；服务端 `4cd3632c…` / 84 环）
- `dryrun_087.py`：**PASS（FAIL=0）**，**4248 条门禁**（本批**零冲突**）
- 「预演==交付」：`_chainstage/dryrun_087.bundle.js` md5 == 交付 bundle md5 ✓
- `remote_check_v2834.sh` 本地预演：**OK=550 / SKIP=15 / FAIL=0**
- `EXPECT_0834.env` 与 `deploy_v2834.sh` 内联 PREV_* **6/6 逐字一致**

## 4. 线上验收

- `remote_check_v2834.sh` → **REMOTE-CHECK: PASS (0 failures)**，**无 WARN**（服务端有变 ⇒ 「没换？」WARN 不触发）
- 冒烟：`index.html=200`｜新包 200｜上一版包 200｜`api/teahouse/today=401`｜`api/fun/dice POST=401`｜
  **`api/wudao/enlighten POST=401`**｜**`api/pet/rune POST=401`**
- ★★ **gzip 硬断言**：`gzip_static index.html 含新包 = 1` ✓
- service active / NRestarts 0 / **`ActiveEnterTimestamp = 09:48:10`（已重启）** / maint flag absent

## 5. 本轮踩到的新坑

1. **③ 类冲突再现（1 条）**：`remote_check` 里 **R-165** 的「服务端按门槛挑系」断言
   钉的是 `const open = keys.filter((k) => realmIdx >= wudaoDaoGateRealm(k));`，
   而 **R-194（方案 A）** 把它换成十道均匀随机 ⇒ 老形态消失。已在 `_mk_2834.py` 里**按行定位退役**它。
2. **我自己在 remote_check 的 NEW_BLOCK 里写错了 3 条断言的计数**（`tierLow` 实际 3 处、`_mul` 2 处、`WUDAO_DAO_REALM_GATE` 2 处）
   ⇒ 全改成 `ge 1`。**教训：新写断言前先 `count` 一遍真实产物**，别凭直觉写 `eq 1`。
3. **EXPECT 里一处 md5 被我写漏一个字符**（`4cd3632ceee7a50c...` 少一个 `b`）⇒ 整份重写修正。
   **教训：md5 这类定长串不要手抄，一律程序生成。**

## 6. 待用户拍板（本批**未做**）

- **R-189 ②** UI 调整（折算属性挪到卡片下说明处 / 「融合玩法」搬到灵宠弹窗）—— 排队中；
- **R-189 ③④** 免费玩法栏（免费进食 +100 喂食度 / 每日 3 次 / 冷却 30 分钟）+ 买额度改 5 次 —— 排队中（**需服务端**）；
- **升级耗时复核**：用户实测炼气 L3 需 1,243,200 修为（= 曲线正确），但按其实测「修为 +233/次、10.4 秒/次」估算
  **L3 ≈ 15 小时、L1 ≈ 10.4 小时**，远高于 R-183 当初估的 5.8 小时/层 ⇒ **待复核后决定是否下调 K**。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2934-<TS> /opt/yl/www/index.html
cp -a /root/backup/index.ts.pre-v2934-<TS>        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2934-<TS> /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2934-<TS>    /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2934-<TS> /opt/yl/www/CHANGELOG_PLAYER.md
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版（0.9.33）：bundle=babae2e2b0cb92f07e0278c5840b1766  server=e12f4ebc0d1e6aa98d9c9ce1b71d998b
```

★ 本批**无 DDL** ⇒ 回滚无需动库。
