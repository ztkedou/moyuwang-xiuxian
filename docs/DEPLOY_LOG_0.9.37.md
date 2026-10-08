# DEPLOY LOG — 《摸鱼修仙传》 0.9.37（v28 链 **第 87 环不变**｜**纯客户端批**）

- **部署时间**：2026-10-08 16:07:03 ~ 16:07:5x（GMT+8）｜★★ **未重启服务** ⇒ **零停机**
  （`ActiveEnterTimestamp` 仍为 0.9.36 的 `11:36:51`，`NRestarts = 0`）
- **目标**：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- **脚本**：`deploy_v28/deploy_v2837.sh --skip-server`（客户端 + 双 CHANGELOG + index.html bump + gz 同步）
- **定点核对**：`deploy_v28/remote_check_v2837.sh` → **PASS (0 failures)**，**无 WARN**
- **登记指纹**：`deploy_v28/EXPECT_0837.env`
- **备份整包**：`/root/backup/yl_pre_v2937_20261008_160703.tar.gz`
- ★★ **本批服务端无变化**（`srv/index_v28.ts` 与 0.9.36 同 md5 = `b598eab6…`，仍 87 环）
  ⇒ **必须加 `--skip-server`**（否则 step 0 的「产物已变」断言会 fail-closed ABORT）。

## 1. 本批范围：0.9.37 = **2 条**（客户端 2 补丁 / 服务端 0 环）

| # | 任务 | 落点 |
|---|---|---|
| **R-195** | 灵宠喂养「文字 vs 实现」审计与修复（8 处过期文字） | `localtest/yl_r202_ext.py` |
| **R-196** | 冷却「静态快照」→「走秒倒计时」（6 处 / 8 个代码点） | `localtest/yl_r203_ext.py` |

- 客户端 `STANDALONE_CLIENT` **49 → 51 脚本**（新增 `r202` / `r203`）
- 服务端 `SRV_CHAIN` **87 环不变**（无新末环）
- ★★ **编号说明（本批踩到的坑）**：本仓有**两套已漂移的编号** —— 「需求台账 R 号」（现到 R-196）与
  「补丁脚本 r 号」（客户端现到 r203、服务端 r201）。本批台账号是 R-195/R-196，而
  `yl_r195_ext.py`（妖灵归位）与 `yl_r196_ext.py`（灵纹重设）**都已存在且已上线** ⇒ 补丁一律取**下一个空闲号**：
  R-195 → **r202**、R-196 → **r203**。（`r195` 代理一度按台账号覆盖了 `yl_r195_ext.py`，
  已**从 git HEAD 完整恢复**，线上功能零损失；教训已写进 `topics/yl.md` 的「★★ 编号约定」。）

## 2. 指纹（部署前后）

| 对象 | 部署前（0.9.36） | 部署后（0.9.37） |
|---|---|---|
| `www/assets/index-v2936-20261008.js` | `649ef7c8ccb9886004a5d4427b709f87` | 同左（**旧包保留不删 = 秒级回滚点**） |
| `www/assets/index-v2935-20261008.js` | `af2883a4a7fa489b9b5c3851d1c85948` | 同左（更早回滚点） |
| `www/assets/index-v2937-20261008.js` | —（新文件） | **`5a35630ea5914ab7f8b94a9f2bfb0686`**（2,318,054 B） |
| `server/index.ts` | `b598eab621c6fe68f666f8ad7f19b847`（87 环） | **同左（未变）** |
| `www/CHANGELOG.md` | `99d0b2360fa332e0947faf6d6afe9255` | **`5a4c0c62f62dd49328851de83f16f434`** |
| `www/CHANGELOG_PLAYER.md` | `d0bc3f8cb6b98ba8723eca0439cd8f0a` | **`3b8901bb71c8f1b94ad597cda5e95795`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（未变）** |

## 3. 部署前本地验收

- `chain_build --all`：**rc=0**（bundle `5a35630e…`；服务端 `b598eab6…` 未变）
- `dryrun_087.py`：**PASS（FAIL=0）**，standalone 门禁 **1481 条 / 63 脚本（r116~r203）**
- 「预演==交付」：`_chainstage/dryrun_087.bundle.js` md5 == 交付 bundle md5 ✓
- ★★ **两补丁顺序无关**：r202/r203 以**任意顺序**套用，产物 **md5 逐字节相同**（`db97c3c4…`）
- `remote_check_v2837.sh` 本地预演（`sim_remote_check.py`）：**OK=539 / SKIP=15 / FAIL=0**
- `bash -n` 两个脚本：语法 OK
- ★ **远端基线预检**：部署前线上 5 项**逐字节命中**
  （bundle `649ef7c8…` / 更早回滚点 `af2883a4…` / server `b598eab6…` / CHANGELOG `99d0b236…` / `index.html` 指向 v2936），
  且 v2937 新包**尚不存在**。

## 4. 线上验收

- `remote_check_v2837.sh` → **REMOTE-CHECK: PASS (0 failures)**，**无 WARN**
- 线上实测指纹：bundle `5a35630e…`（2,318,054 B）｜server `b598eab6…`（未变）｜
  CHANGELOG `5a4c0c62…`｜CHANGELOG_PLAYER `3b8901bb…`
- `index.html` 指向 **`index-v2937-20261008.js`**（旧引用已清零）
- ★★ **gzip 硬断言**：`zcat index.html.gz | grep 新包 = 1` ✓
- ★★ **零停机**：`yl-server` `active` / `NRestarts = 0` / **`ActiveEnterTimestamp` 仍为 `11:36:51`（未重启）**
- 回滚点 **v2935 + v2936 双双仍在** ✓
- 双 CHANGELOG 已回填**实际上线时刻 16:07** 并重传；`EXPECT_0837.env` 的 `EXPECT_CHANGELOG_MD5` 已重登记

## 5. 本轮踩到的新坑

1. ★★ **`_mk_2836.py` 的 `PREV_SRV_MD5` 链只替了 8 字符前缀** ⇒ 在 `deploy_v2836.sh` / `remote_check_v2836.sh` 里
   留下一个 **56 字符脏值**（`8318e1c9…eebee7a5…`）。0.9.36 之所以没炸，是因为部署脚本
   **顶层 `source EXPECT_0836.env`**，EXPECT 里的正确值**覆盖**了内联脏值。
   ⇒ **教训：用「短前缀 → 占位符 → 全串」的链式替换时，必须确认短前缀不会命中一个更长的旧 md5。**
   本批已整串替换，并加了 bad 断言防回归。
2. ★★ **r196 的补丁把插入点落在一条 `var` 语句中间**：`function YlxwTAdventure() {` 之后的 head 是
   **一整条巨型 `var`**（一路到 `N = async function(){...}`），而原锚点只截到 `c = r.load,`（逗号处）
   ⇒ ① `SyntaxError: Unexpected token '('`；② 更阴的是它把 `d = O.useState("")`、`u/f/m/g/h` 挪位后
   **丢了 `var` 关键字**（语法修好也会运行时 ReferenceError）。
   ⇒ **教训：插入点必须落在语句边界；挪动既有声明时必须保留声明关键字。**
   ★ 这类 bug **`node --check` 之前的门禁查不出来**（dryrun 只跑 `node --check` 在最后一关），
   所以「补丁作者必须实跑 `node --check`」这条自证要求是刚性的。
3. ★★ **「apply 态 vs 终态」是本仓门禁的真正难点**：我第一次更新 r136/r139/r198 的针脚时只写了**终态值**，
   结果 dryrun **348 条级联失败** —— 因为 dryrun 是**边套用边检查**，那些针在**套用那一刻**看到的是旧形态
   ⇒ 补丁「门禁未全绿，未写盘」⇒ 下游全断。
   ⇒ 正确口径就是本仓既有的 **`RETIRED_TAG`（apply 态跳过、终态仍检）**；本批 4 条针（r136 ×1 / r139 ×2 / r198 ×1）
   按此改，并为 `yl_r136_ext.py` **补上了它缺失的 `RETIRED_TAG` 机制**（常量 + `--check` 跳过分支）。
   ★ **下次改老针，必须同时想两套语境。**
4. ★ **上轮修的覆盖洞会随新补丁复发**：`dryrun_087.py` 的终态门禁清单是**字面量列表**
   （r194 从当时的 `STANDALONE_CLIENT` 生成）⇒ 新加的 r202/r203 一开始**没被覆盖**。
   本批已补进清单，并把打印标签的**两端都改成动态**（`_sa_scripts[0][0]`~`_sa_scripts[-1][0]`，此前尾部写死 `r200`）。
   ⇒ **以后每加 standalone 补丁，都要同时把它加进 dryrun 的 import 段与 `_sa_scripts`。**

## 6. 待用户拍板（本批**未做**）

- **修为喂养的真实消耗是 25%，而文案与闸门一直写 5%** —— 说明当年 R-017 只改了实扣、漏改文案与闸门。
  本批把**文字 + 闸门对齐到实际的 25%**、**未动实扣**（闸门 `d.exp>=w` 对 exp≥1 恒真 ⇒ 行为零变化）。
  ⇒ 若 5% 才是本意，需要**改数值**（修为喂养会便宜 5 倍），属**平衡决策**，留给用户。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2937-20261008_160703    /opt/yl/www/index.html
cp -a /root/backup/CHANGELOG.md.pre-v2937-20261008_160703  /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2937-20261008_160703 /opt/yl/www/CHANGELOG_PLAYER.md
# ★ index.html.gz 必须与明文同批重建（nginx gzip_static 铁律 R-159）
gzip -9 -kf -c /opt/yl/www/index.html > /opt/yl/www/index.html.gz
# ★ 本批服务端**未变** ⇒ 无需回滚 index.ts、无需重启
# 上一版定版（0.9.36）：bundle=649ef7c8ccb9886004a5d4427b709f87  server=b598eab621c6fe68f666f8ad7f19b847
# 整包：/root/backup/yl_pre_v2937_20261008_160703.tar.gz
```

★ **本批无 DDL、服务端零改动** ⇒ 回滚只动前端三件，**不需要重启服务**。

## 8. 0.9.37 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=af2883a4a7fa489b9b5c3851d1c85948      # 0.9.35 index-v2935-20261008.js（更早回滚点）
PREV_LIVE_BUNDLE_MD5=649ef7c8ccb9886004a5d4427b709f87 # 0.9.36 index-v2936-20261008.js（本次部署前的线上包）
PREV_SRV_MD5=b598eab621c6fe68f666f8ad7f19b847         # 0.9.36 srv/index_v28.ts（87 环 = s87.r201.ts）★ 本批未变
PREV_CHANGELOG_MD5=99d0b2360fa332e0947faf6d6afe9255   # 0.9.36 CHANGELOG.md
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S20_MD5=7780e099a6cd1ac0de4b502c467ae2c0     # 0.8.9 定版 s20.t16arena.ts（前 20 环不变）
# 本版（0.9.37）新指纹：
#   bundle   5a35630ea5914ab7f8b94a9f2bfb0686  (2,318,054 B)  index-v2937-20261008.js
#   server   b598eab621c6fe68f666f8ad7f19b847  (1,017,257 B / 87 环) ★ 与 0.9.36 相同
#   CHANGELOG.md        5a4c0c62f62dd49328851de83f16f434
#   CHANGELOG_PLAYER.md 3b8901bb71c8f1b94ad597cda5e95795
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
