# DEPLOY LOG — 《摸鱼修仙传》 0.9.41（v28 链 **88 环不变**｜**纯客户端批**）

- **部署时间**：2026-10-08 20:02:38 ~ 20:0x（GMT+8）｜★★ **未重启服务** ⇒ **零停机**
  （`ActiveEnterTimestamp` 仍为 0.9.39 的 `Thu 2026-10-08 17:15:28 CST`，`NRestarts = 0`）
- **目标**：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- **脚本**：`deploy_v28/deploy_v2841.sh --skip-server`
- **定点核对**：`deploy_v28/remote_check_v2841.sh` → **PASS (0 failures)**，无 WARN
- **登记指纹**：`deploy_v28/EXPECT_0841.env`
- **备份整包**：`/root/backup/yl_pre_v2941_20261008_200238.tar.gz`（57,717,545 B）
- **DB 一致性快照**：`/root/backup/database_v2941_consistent_20261008_200238.sqlite`（13,701,120 B）
- ★★ **服务端逐字节不变**（`srv/index_v28.ts` 与 0.9.40 同 md5 = `2f49c2a7…`，仍 **88 环**）⇒ 必须 `--skip-server`。

## 1. 本批范围：0.9.41 = **1 条**（客户端 1 补丁 / 服务端 0 环）

| # | 台账号 | 任务 | 落点 |
|---|---|---|---|
| 1 | **R-204** | 历练分档：下界 **370 → 200**（修正 0.9.40）+ 判定**随境界缩放** | `localtest/yl_r211_ext.py` |

- 客户端 `STANDALONE_CLIENT` **57 → 58 脚本**；服务端 **88 环不变**。

### 1.1 改动一：下界 370 → 200（**修正 0.9.40 的过度修正**）

> 用户澄清设计意图：「最低档位的灵石获取几率最高，中档位获取比较低，高档位灵石获取现在设计默认 1% 最高 4%。
> **这些跟灵石数量没有太大关系，灵石数量随着境界提升而升高。主要是档位的概率设定**」
> 并给出定义：「炼气 1 层时，获取 0~1,2百 灵石的事件归为常态事件；获取 200 以上到 1000 的归为稀有事件；
> 现有的奇遇归为 1% 最高 4% 的事件」

- **200 是天然分界**：`battle` 族（raw 10~39 ⇒ 结算 **51~198**）与
  `cave` / `spiritStone` / `evilCultivator` 族（raw 40~149 ⇒ **204~760**）之间那道缝正好在 200 ——
  也正是 R-180 `MID_STONE_MIN = 40` 的原意。
- 0.9.40 把下界设成 370 ⇒ 把 200~370 这段（`cave`/`spiritStone` 的**低端**）误划进了常态。
- ★★ **反证**（真实模板 + 真实权重 + 真实战斗路，n=4 万）：

  | T | 常态 | 稀有 | 奇遇 |
  |--:|--:|--:|--:|
  | 150（原版） | 64.4% | 34.7% | 0.9% |
  | **200（本次）** | **66.7%** | **32.5%** | **0.9%** |
  | 370（0.9.40） | 83.0% | 16.1% | 0.9% |

  用户当初实测 = `常态 106 · 几百 52 · 几千 0` = **67.1% / 32.9% / 0** ⇒ 与 **T=200 几乎逐位吻合**
  ⇒ **原版分档本来就是对的；0.9.40 的 370 才是把分布扭歪的那次。**

### 1.2 改动二：判定随境界缩放（**这才是设计意图**）

- 问题：结算值 = `raw × 5.1 × u`，`u = [1,1.236928,1.529991,1.892489,2.340873,2.895491,3.581514][境界] × (1+(层-1)×0.3)`。
  0.9.40 用的是**绝对**阈值 ⇒ 境界越高「折叠」得越少 ⇒ **档位概率随境界漂移**。
- **独立验算**：6 类模板 × 7 境界 = **42 组合中 21 组会漂** ——
  金丹期起 `spiritStone` / `evilCultivator` 上界**漂进「几千」**（直接吃掉「高档 1%」）；长生期 `battle` 从常态漂成稀有、`cave` 从稀有漂成几千。
- **修法**：把**判定输入归一化** `ds/u` ⇒ 判定等价于炼气 L1 ⇒ **档位概率与境界无关**（恒 ≈67% / ≈32% / ≈1%）。
  ★ 数学上 `ds/u <= 200 ⟺ ds <= 200u`（u>0），与「阈值 ×u」**严格等价**（连续除法，无取整误差）。
- ★★ **为什么不直接改签名把境界传进来**：`function YlxwAdvStatAcc(res) {` / `function YlxwAdvAcc(res) {` /
  `YlxwAdvAcc(t)` / `YlxwAdvStatAcc(res);` 被 **r138 / r155 / r161 / r184 / r191** 的 `gates()` **逐字钉死**
  （已 `grep` 实证）⇒ 改签名会连带撞坏 5 个补丁。故采用「**判定行结构不动、只归一化输入**」，
  用**块级 `let ds`** 遮蔽 ⇒ 外层真实 `ds`（供 `S.stone += ds` 累加灵石总量）**一字未动**。
- `u` 的传递：在 `Fg({..., player:l, ...})` 里把玩家挂到 `window.YLXW_ADV_PL`（本 bundle 已用 `window` 160+ 次）。
- ★ **兜底**：`if(!isFinite(__ylU) || __ylU <= 0) __ylU = 1;`
  （玩家缺失 / `realm` 不在境界表 / `realmLevel` 非法 ⇒ 退化为炼气 L1 行为，**绝不 NaN/0** —— 若为 0 会让所有 ds 归常态）。

## 2. 指纹（部署前后）

| 对象 | 部署前（0.9.40） | 部署后（0.9.41） |
|---|---|---|
| `www/assets/index-v2938-20261008.js` | `a4726c77b810c6b620b0604ce89cf9a7` | 同左（更早回滚点） |
| `www/assets/index-v2939-20261008.js` | `21a16b962a1ccedfc02c021b3bd2dc71` | 同左（0.9.39 定版） |
| `www/assets/index-v2940-20261008.js` | `af8e021dd9fe8883d775c0b0dc223f96` | 同左（**0.9.40 定版 = 秒级回滚点**） |
| `www/assets/index-v2941-20261008.js` | —（新文件） | **`b0b6b771bbb3c89c186016438e7e8cf0`**（2,319,239 B） |
| `server/index.ts` | `2f49c2a7bc1b7348c2732912afe968ff`（88 环） | **同左（未变）** |
| `www/CHANGELOG.md` | `079707b09375b5f18f5a67546fb48c64` | **`271d1a40fe84ca9e4220ff2b797feaf1`**（回填上线时刻后） |
| `www/CHANGELOG_PLAYER.md` | `aafae92230df1006628127ac180e6fd0` | **`f1752ef6d72948e8bf8bd63296ae72c0`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | **同左（未变）** |

线上实测（部署后 SSH 直采，与本表逐字一致）：

```
b0b6b771bbb3c89c186016438e7e8cf0  /opt/yl/www/assets/index-v2941-20261008.js  (2,319,239 B)
2f49c2a7bc1b7348c2732912afe968ff  /opt/yl/server/index.ts          (1,019,321 B / 88 环，未变)
271d1a40fe84ca9e4220ff2b797feaf1  /opt/yl/www/CHANGELOG.md
f1752ef6d72948e8bf8bd63296ae72c0  /opt/yl/www/CHANGELOG_PLAYER.md
```

## 3. 部署前本地验收

- `chain_build.py --all`：**rc=0**（服务端链重建后 md5 仍 `2f49c2a7…`；前端装配产出 `b0b6b771…`）
- `dryrun_087.py`：**PASS（FAIL=0）**，standalone 门禁 **1616 条 / 70 脚本（r116~r211）**
- 「预演==交付」：`_chainstage/dryrun_087.bundle.js` md5 = `b0b6b771bbb3c89c186016438e7e8cf0` **== 交付产物** ✓
- `sim_remote_check.py --script deploy_v28/remote_check_v2841.sh` 本地预演：**OK=555 / SKIP(远端专有)=15 / FAIL=0**
- `bash -n` 两脚本 **OK**；三件套 **CR 字节 = 0（纯 LF）/ 无 BOM** ✓

## 4. 线上验收

- `remote_check_v2841.sh` → **REMOTE-CHECK: PASS (0 failures)**，无 WARN
- 线上指纹全部命中（见 §2 表 + SSH 直采块）
- `index.html` 指向 **`index-v2941-20261008.js`**；★★ **gzip 硬断言**：`zcat index.html.gz | grep 新包 = 1` ✓（R-159 铁律）
- ★★ **零停机**：`ActiveState = active` / `NRestarts = 0` / `ActiveEnterTimestamp` **仍为 `2026-10-08 17:15:28 CST`**
- 回滚点 **v2938 + v2939 + v2940 三包均在** ✓
- 公开冒烟：`index.html → 200`｜`bundle → 200`｜`gz → 200`
- 线上包内抽查：`if (ds <= 200)` = 1、`if (ds <= 370)` = **0**、`__dsRaw` = 2、`window.YLXW_ADV_PL` = 2、
  `/*[r211tieru]*/` = 1、`0.9.41` = 1 ✓
- 双 CHANGELOG 已回填**实际上线时刻 20:02** 并重传；`EXPECT_0841.env` 已重登记（`EXPECT_CHANGELOG_MD5=271d1a40…`）

## 5. 本轮踩到的新坑 / 经验

1. ★★ **「按定义实现」而不是「按指标调参」** —— 本批最大的教训。
   0.9.40 我拿到用户实测 `常态 106 · 几百 52 · 几千 0`，**把「几百 33%」当成了"指标偏高"去优化**，
   于是把下界从 150 抬到 370 硬凑到 16%。但用户的原话只是说**这几个名字不好听**（那是 R-208 的事），
   以及更早 R-180 说的「减少灵石加好几百的事件」（那是**权重**的事，不是阈值）。
   ⇒ 结果：**我把一个本来就正确的分布扭歪了**。用户给出「0~200 常态 / 200~1000 稀有」的定义后，
   实测反证 T=200 得到 66.7/32.5/0.9 ≈ 用户实测 67.1/32.9/0 ⇒ **原版才是对的**。
   ★ 教训：**用户给的是「分类定义」，不是「目标百分比」** —— 应当去实现定义，然后**测量**结果，而不是反过来。

2. ★★ **「改一个被多处钉死的签名」前必须全库 `grep`**：我原方案是给 `YlxwAdvAcc` / `YlxwAdvStatAcc`
   加一个 `pl` 参数把玩家传进去。成员 `grep` 后发现这 4 个串被 **r138 / r155 / r161 / r184 / r191** 逐字钉死
   ⇒ 改签名会连带撞坏 5 个补丁。**我复核了这条论断，属实**（`grep -rln -F` 逐个命中）。
   ⇒ 改用「**判定行结构不动、只归一化判定输入**」，等价且**零门禁冲突**。

3. ★ **等价改写可以规避整类冲突**：`ds/u <= 200 ⟺ ds <= 200u`（u>0）—— 把「缩放阈值」换成「归一化输入」，
   既达到同样效果，又不必改任何被钉死的结构。★ 用**块级 `let ds`** 遮蔽，外层真实 `ds` 不受影响。
   ⇒ **遇到「想改的串被钉死」时，先问：能不能等价改写到别处？**

4. ★ **`_is_ver_slot` 判据要能覆盖两位数小版本**：注册器成员把条件从 `" '0.9.3"` 放宽为 `" '0.9."`，
   否则 `'0.9.40'` / `'0.9.41'` 这类槽位会漏升。★ 升到 0.9.4x 后必须留意这类"硬编码前缀"判据。

5. ★ **`_mk_*.py` 的注释里嵌长句要当心**：我用脚本替换注释时把一行字符串写断了（`SyntaxError: unterminated string literal`）。
   ⇒ 改生成器的注释时，**替换体要保持「每行一个完整字符串元素」**，改完立刻重跑一次验证。

## 6. 残留清理

- 远端 `_remote_check_v2841.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` 留在 `/opt/yl/server/` 便于复跑（惯例）。
- 本地 `_vfy/`（成员验证用的临时目录）**已删除**。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
cp -a /root/backup/index.html.pre-v2941-20261008_200238 /opt/yl/www/index.html
# ★ index.html.gz 必须与明文同批重建（nginx gzip_static 铁律 R-159）
gzip -9 -kf -c /opt/yl/www/index.html > /opt/yl/www/index.html.gz
cp -a /root/backup/CHANGELOG.md.pre-v2941-20261008_200238        /opt/yl/www/CHANGELOG.md
cp -a /root/backup/CHANGELOG_PLAYER.md.pre-v2941-20261008_200238 /opt/yl/www/CHANGELOG_PLAYER.md
# ★ 服务端未变 ⇒ 无需回滚 index.ts、无需重启
# 上一版定版（0.9.40）：bundle=af8e021dd9fe8883d775c0b0dc223f96  server=2f49c2a7bc1b7348c2732912afe968ff
# 整包：/root/backup/yl_pre_v2941_20261008_200238.tar.gz
```

★ 本批**无 DDL、服务端零改动** ⇒ 回滚只动前端三件，**不需要重启服务**。

## 8. 0.9.41 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=21a16b962a1ccedfc02c021b3bd2dc71      # 0.9.39 index-v2939-20261008.js（更早回滚点）
PREV_LIVE_BUNDLE_MD5=af8e021dd9fe8883d775c0b0dc223f96 # 0.9.40 index-v2940-20261008.js（本次部署前的线上包）
PREV_SRV_MD5=2f49c2a7bc1b7348c2732912afe968ff         # 0.9.39 = 0.9.40 = 0.9.41（88 环 = s88.r207.ts）★ 本批未变
PREV_CHANGELOG_MD5=079707b09375b5f18f5a67546fb48c64   # 0.9.40 CHANGELOG.md
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S20_MD5=7780e099a6cd1ac0de4b502c467ae2c0     # 0.8.9 定版 s20.t16arena.ts（前 20 环不变）
# 本版（0.9.41）新指纹：
#   bundle  b0b6b771bbb3c89c186016438e7e8cf0  (2,319,239 B)  index-v2941-20261008.js
#   server  2f49c2a7bc1b7348c2732912afe968ff  (1,019,321 B / 88 环) ★ 与 0.9.39/0.9.40 相同
#   CHANGELOG.md        271d1a40fe84ca9e4220ff2b797feaf1
#   CHANGELOG_PLAYER.md f1752ef6d72948e8bf8bd63296ae72c0
#   dicts    1b635513f553875060869272b790f910  (未变)
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
