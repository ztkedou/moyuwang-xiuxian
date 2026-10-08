# DEPLOY LOG — 《摸鱼修仙传》 0.9.36（v28 链 **第 87 环**）

- **部署时间**：2026-10-08 11:36:22 ~ 11:37:2x（GMT+8）｜**服务重启时刻 `ActiveEnterTimestamp = 11:36:51`**
- **目标**：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- **脚本**：`deploy_v28/deploy_v2836.sh`（客户端 + **服务端 2 新环 85→87** + 双 CHANGELOG + index.html bump + gz 同步）
- **定点核对**：`deploy_v28/remote_check_v2836.sh` → **PASS (0 failures)**，**无 WARN**
- **登记指纹**：`deploy_v28/EXPECT_0836.env`
- **备份整包**：`/root/backup/yl_pre_v2936_20261008_113622.tar.gz`
- ★★ **本批服务端有变** ⇒ **重启了 yl-server**（`NRestarts = 0`，`ActiveState = active`）。

## 1. 本批范围：0.9.36 = **2 条**（客户端 1 补丁 + 服务端 2 环）

| # | 任务 | 落点 |
|---|---|---|
| **R-192** | 去掉 R-167「当日首次免费」喂养（冗余的第二套免费机制） | `patches/server/srv_patch_r200.py`（**第 86 环**）+ `localtest/yl_r200_ext.py` |
| **R-193** | 服务端渡劫门槛与客户端曲线对齐（补上 R-183 的 K 表） | `patches/server/srv_patch_r201.py`（**第 87 环**） |

- 客户端 `STANDALONE_CLIENT` **49 → 50 脚本**（新增 1：`r200`）
- 服务端 `SRV_CHAIN` **85 → 87 环**（`s86.r200` / `s87.r201`）
- ★ **门禁退役 3 条**（R-167 首免被整条移除 ⇒ 相关形态归 0）：
  - `remote_check` 2 条：`... WHERE times < 1`（原 R167 闸门断言）+ `UPDATE pet_feed_log SET times = MAX(0, times - 1)`（原 R167 失败补偿回退）
  - 补丁门禁 4 条：`yl_r189_ext.py` 3 条（消费 feedQuota / 「今日首次免费」标记 / free 判定）+ `yl_r198_ext.py` 1 条（保留 r189ui 首免后缀）
    —— 均以 `RETIRED_TAG` 退役、终态期望 0（由 `pinfix5` 实施）
  - ★ 另退役 1 条**既有红灯**：`yl_r189_ext.py` 的 `R189①·新标题「参考非当前加成」`
    —— R-197（0.9.35）已把该块标题合法改名为「妖灵折算棱宠属性（参考）」⇒ 旧标题终态归 0（③ 类冲突）

## 2. 指纹（部署前后）

| 对象 | 部署前（0.9.35） | 部署后（0.9.36） |
|---|---|---|
| `www/assets/index-v2935-20261008.js` | `af2883a4a7fa489b9b5c3851d1c85948` | 同左（**旧包保留不删 = 秒级回滚点**） |
| `www/assets/index-v2934-20261008.js` | `550efc63d2289efa2795b1dc1bbda115` | 同左（更早回滚点） |
| `www/assets/index-v2936-20261008.js` | —（新文件） | **`649ef7c8ccb9886004a5d4427b709f87`**（2,315,801 B） |
| `server/index.ts` | `8318e1c9fad3242364df7b3a585ca61f`（85 环） | **`b598eab621c6fe68f666f8ad7f19b847`**（1,017,257 B / **87 环**） |
| `www/CHANGELOG.md` | `33231247d8dd8608d0decaaf61a5d8dd` | **`99d0b2360fa332e0947faf6d6afe9255`** |
| `www/CHANGELOG_PLAYER.md` | `81180d88e261207617b1ebeb93a0100c` | **`d0bc3f8cb6b98ba8723eca0439cd8f0a`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（未变）** |

## 3. 部署前本地验收

- `chain_build --all`：**rc=0**（bundle `649ef7c8…`；服务端 `b598eab6…` / 87 环；`node --check` rc=0）
- `dryrun_087.py`：**PASS（FAIL=0）**，894 条 standalone 门禁
- 「预演==交付」：`_chainstage/dryrun_087.bundle.js` md5 == 交付 bundle md5 ✓
- `remote_check_v2836.sh` 本地预演（`sim_remote_check.py`）：**OK=544 / SKIP=15 / FAIL=0**
- `bash -n` 两个脚本：语法 OK
- ★ **远端基线预检**：部署前线上 4 个 PREV_* 指纹**逐字节命中**
  （bundle `af2883a4…` / 更早回滚点 `550efc63…` / server `8318e1c9…` / CHANGELOG `33231247…`），
  `index.html` 指向 `index-v2935-20261008.js`，且 v2936 新包**尚不存在**。
- ★ **独立数值自证**：服务端 87 环产物字符数 **871,927** = 871,870 − 357（r200）+ 414（r201），与两个补丁自报 delta **精确吻合**；
  `TRIB_REALM_R183_K` 与 `TRIB_REALM_BASES` **键序完全一致 / 7 个值完全一致**；
  链尾三文件（`srv/index_v28.ts` / `_chainstage/s87.r201.ts` / `canon`）**逐字节 IDENTICAL**。

## 4. 线上验收

- `remote_check_v2836.sh` → **REMOTE-CHECK: PASS (0 failures)**，**无 WARN**
- 线上实测指纹：bundle `649ef7c8…`（2,315,801 B）｜server `b598eab6…`（1,017,257 B）｜
  CHANGELOG `99d0b236…`｜CHANGELOG_PLAYER `d0bc3f8c…`
- `index.html` 指向 **`index-v2936-20261008.js`**（旧引用已清零）
- ★★ **gzip 硬断言**：`zcat index.html.gz | grep 新包 = 1` ✓
- `yl-server`：`active` / `NRestarts = 0` / **`ActiveEnterTimestamp = 2026-10-08 11:36:51 CST`（已重启）**
- 回滚点 **v2934 + v2935 双双仍在** ✓
- 双 CHANGELOG 已回填**实际上线时刻 11:36** 并重传；`EXPECT_0836.env` 的 `EXPECT_CHANGELOG_MD5` 已重登记
  （无 `.gz` 伴生文件 ⇒ 无需重建）

## 5. 本轮踩到的新坑

1. ★ **`sim_remote_check.py` 的 `$B` 默认值是硬编码的上一版包名**（`:37`），换版时必须同步改，
   否则预演会拿**旧包**去核新断言 ⇒ 出现「首免后缀 got=1」「版本号 0.9.36 got=0」这类**假 FAIL**
   （数值恰好与上一版一致，是极好的识别特征）。已改 `:37` → `index-v2936-20261008.js`。
2. ★ **门禁针的短串会被「留档注释」污染**：R-192 把首免闸门删掉后，**SQL 短串 `... WHERE times < 1` 仍留在 r200 写的留档注释里**
   ⇒ 直接拿短串当「已移除」的针会 FAIL。改用**完整可执行 SQL** 当针（`INSERT INTO pet_feed_log (...) VALUES (?, ?, 1) ON CONFLICT`）后归 0 ✓。
   **教训：判「某形态已消失」的针必须长到能区分「代码」与「注释」。**
3. ★ **`_mk_2835.py` 的整段替换会连带吃掉下一批的退役对象**：`RETIRE_CHK` 里 `... WHERE times < 1` 我按 v2835 全文数了 2 处，
   但其中 1 处位于**本批被摘掉的 0.9.35 旧段内** ⇒ 摘段后只剩 1 处、断言当场炸。
   **教训：退役计数要按「摘段后的文本」数，不是按输入文件数。**
4. ★ **生成器把上一批 note 里的历史字节数误判为「残留」**（`1,016,800` 是 0.9.35 的合法历史值）⇒ 从 bad 列表移除。
5. **`SendMessage` 中途报「Not in a team」**（团队上下文丢失）⇒ 后续审计改由主线自己用脚本完成（`_audit_gates.py`）。

## 6. ★★ 已量化的遗留债务（本批**未处理**，建议单独立项）

**发现：`dryrun_087.py` 的 standalone 门禁循环只列到 `('r179', _sa_r179)`**
⇒ **r180~r200 这 20 个补丁的 `gates()` 从未被任何流水线跑过**（`remote_check` 覆盖的是终态字符串，不覆盖补丁自己的 `gates()`）。

用 `_audit_gates.py` 在新产物上实测：**门禁总数 513 / OK 501 / 退役 6 / FAIL 6**。6 条红灯**全部是 ③ 类冲突（后续补丁合法改写），无一真 bug**：

| 补丁 | 红灯 | 归因 |
|---|---|---|
| `r180` | `R180v4·EV 奇遇率已常数化 1%` | R-191/R-193 重写了奇遇率公式 |
| `r188` | `冻结 }finally{c(!1),d(9)}` | R-199 把 `d(9)` → `d(7)` |
| `r189c` | `R189c①·读 player.petSpirit.runeCrit`（期望 1 / 实际 2） | R-196 增加了第二处读取 |
| `r191` ×3 | `[r191adv]` 标记 + EV 公式 + EV 行 | R-193 **取代**了 r191 的公式 |

**为何本批不修**：
- 这 6 条是**既有债务**（0.9.34/0.9.35 遗留），不是 0.9.36 引入的；
- 修好需要给 `yl_r180/r188/r189c/r191_ext.py` 这 4 个文件补上 `RETIRED_TAG` 常量 + `--check` 跳过分支（各自骨架不同），属**独立任务**；
- 把 r180~r200 接进 dryrun 会**改变构建门禁的覆盖面**（行为变更），不宜作为功能发布的副作用夹带。

**建议下一轮**：单开「门禁债清理 + dryrun 覆盖面补齐」一批 —— ① 给 4 个文件补 `RETIRED_TAG` 机制并退役这 6 条；
② 把 r180~r200 正式接进 `dryrun_087.py` 的循环（并把打印标签里写死的「r116~r179 共 41 脚本」改成动态计数）。
③ 之后这 513 条门禁才会每次构建都被真正校验。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2936-20261008_113622    /opt/yl/www/index.html
cp -a /root/backup/index.ts.pre-v2936-20261008_113622      /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2936-20261008_113622 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2936-20261008_113622  /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2936-20261008_113622 /opt/yl/www/CHANGELOG_PLAYER.md
# ★ index.html.gz 必须与明文同批重建（nginx gzip_static 铁律 R-159）
gzip -9 -kf -c /opt/yl/www/index.html > /opt/yl/www/index.html.gz
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版（0.9.35）：bundle=af2883a4a7fa489b9b5c3851d1c85948  server=8318e1c9fad3242364df7b3a585ca61f
# 整包：/root/backup/yl_pre_v2936_20261008_113622.tar.gz
```

★ **本批无 DDL**（R-192 只删代码、R-193 只改常量与函数体）⇒ 回滚**无需动库**。

## 8. 0.9.36 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=550efc63d2289efa2795b1dc1bbda115      # 0.9.34 index-v2934-20261008.js（更早回滚点）
PREV_LIVE_BUNDLE_MD5=af2883a4a7fa489b9b5c3851d1c85948 # 0.9.35 index-v2935-20261008.js（本次部署前的线上包）
PREV_SRV_MD5=8318e1c9fad3242364df7b3a585ca61f         # 0.9.35 srv/index_v28.ts（85 环 = s85.r198.ts）
PREV_CHANGELOG_MD5=33231247d8dd8608d0decaaf61a5d8dd   # 0.9.35 CHANGELOG.md
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S20_MD5=7780e099a6cd1ac0de4b502c467ae2c0     # 0.8.9 定版 s20.t16arena.ts（前 20 环不变）
# 本版（0.9.36）新指纹：
#   bundle   649ef7c8ccb9886004a5d4427b709f87  (2,315,801 B)  index-v2936-20261008.js
#   server   b598eab621c6fe68f666f8ad7f19b847  (1,017,257 B / 87 环 = s87.r201.ts)
#   CHANGELOG.md        99d0b2360fa332e0947faf6d6afe9255
#   CHANGELOG_PLAYER.md d0bc3f8cb6b98ba8723eca0439cd8f0a
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
