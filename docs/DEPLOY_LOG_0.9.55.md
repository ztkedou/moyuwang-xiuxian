# DEPLOY LOG — 《摸鱼修仙传》 0.9.55

- 部署时间：2026-10-10 22:15 (GMT+8)
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2855.sh`（**纯客户端批** ⇒ `--skip-server`，**零停机**）
- 定点核对：`deploy_v28/remote_check_v2855.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0855.env`
- 备份整包：`/root/backup/yl_pre_v2955_20261010_221414.tar.gz`
- DB 一致性快照：`/root/backup/database_v2955_consistent_20261010_221414.sqlite`

---

## 1. 本批范围（0.9.55；客户端 3 模块 + 服务端 93 环**不变**）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-241 | 顿悟频率下调 + 悟道心得解绑 | `localtest/yl_r241_ext.py`（2 EDITS 就地替换）→ 注册 `('r241', …)`（排 r239 之后）| ✅ 1 模块 | — 零改动 |
| 批 1 · R-240 | 心法 48 部数据层（expRate / 描述 / 机制占位，**不写属性列**） | `localtest/yl_r240_ext.py` → 注册 `('r240', …)` | ✅ 1 模块 | — 零改动 |
| 批 1 · R-242 | 批 1 生效前提：删品级覆盖 + 取消 1.25 上限 | `localtest/yl_r242_ext.py` → 注册 `('r242', …)`（**必须排在 r240 之后**）| ✅ 1 模块 | — 零改动 |

**R-241 起因与口径**：用户反馈「顿悟和跳悟道频率比历练高太多」⇒ 目标顿悟 10 分钟 / 悟道心得 30 分钟。
口径依据：打坐 tick = **每秒 1 次**（R-139 的 `YlxwBgInterval(fn,ms)` 在 Worker 可用时忽略 `ms`，走 1s 心跳）。

- **A 顿悟概率**：`(0.01+Math.min(0.03,luck*0.0003))`（加法百分点，1%~4%）
  → `(0.001667*(1+Math.min(1,luck*0.005)))`（**乘性倍率**）+ 幂等标记 `/*[r241enl]*/`。
  ⇒ 基础 **0.1667%**（≈10 分钟）；气运 luck=100 → +50%；≥200 封顶 +100% ⇒ **5~10 分钟**。
- **B 悟道心得解绑**：由「每次顿悟必产」→ `Math.random()<.3333&&YlxwWudaoEnlighten(c)`
  ⇒ 顿悟 ×3 = **30 分钟**一份。
- ★ **只改打坐侧**；历练侧 R-184（`YlxwWudaoMaybe`，灵石≥200）**未动**。

**批 1 起因与关键背景**：心法 expRate 原被**两道抹平** —— ① `YlxwArtRebalance()` 末尾按品级覆盖
（黄.10/玄.16/地.28/天.45）；② `bd()` 的 `r=Math.min(1.25, expRate×{天:2,地:1.5,玄:1.2,黄:1}[grade])`。
⇒ **只做 r240 无效**（会被盖回去），必须配 r242。
- **R-240**：改 `is[]` 心法段数据（每部独立 expRate 7~100%）；★ **不写属性列**。
- **R-242**：移除上述两道抹平 ⇒ 贡献 = `u.effects.expRate`（每部独立）。
  黄 7~14% / 玄 13~20% / 地 30~45% / 天 55~100%。
- ★ 严禁 `eval→JSON.stringify` 整段重写 `is[]`：`realmRequirement:ae.QiRefining` 是**枚举引用**，
  stringify 会变字符串 ⇒ 破坏境界门槛。

## 2. 指纹（部署前后）

| 对象 | 上一版（部署前） | 本批（部署后） |
|---|---|---|
| `www/assets/index-v2954-20261010.js` | `aa49623854fad1bbe22f6ab3076b804f` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2953-20261010.js` | `e525b8027f9a90883db71d834583c5ec` | 同左（0.9.53 定版，更早的回滚点） |
| `www/assets/index-v2955-20261010.js` | —（新文件） | `77d35f9c7a1570308cee19c319348e6a` |
| `server/index.ts` | `328170ededb61fe3289845cb91d3419d` | `328170ededb61fe3289845cb91d3419d`（**未变**） |
| `www/CHANGELOG.md` | `e36e2a0b2c3378cf3f3f145d14d93130` | `8b51a980be81aebeb621311a0757fc3e` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | `1b635513f553875060869272b790f910`（本批不变） |

部署后线上实测（deploy_v2855.sh 采集）：

```
328170ededb61fe3289845cb91d3419d  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
8b51a980be81aebeb621311a0757fc3e  /opt/yl/www/CHANGELOG.md
77d35f9c7a1570308cee19c319348e6a  /opt/yl/www/assets/index-v2955-20261010.js
```

## 3. 部署前本地验收

- `localtest/dryrun_087.py` → 门禁 **4337 条 / FAIL 0**；「预演 == 交付」md5 一致 = `77d35f9c…`（step 0c 已过）。
- `localtest/sim_r231_inject.py --new 0.9.55 --prev 0.9.54` → **FAILS=0**（A/B 逐字节恒等 + 3b-2 段推进 + grep 双计数）。
- `localtest/sim_remote_check.py --script deploy_v28/remote_check_v2855.sh` → **OK=893 / SKIP=15 / FAIL=0**。
- 三件套 `bash -n` 双绿；纯 LF / 无 BOM / 换行结尾。
- `chain_build.py --all`：前端 `77d35f9c…`、服务端 `328170ed…`（**未变**，93 环，链尾 `s93.r233.ts`）、
  dicts `1b635513…`；链 `s20.t16arena.ts` == `7780e099a6cd1ac0de4b502c467ae2c0`（前 20 环 == 0.8.9 定版）。
- `build_v26n.py` 产物 md5 == 预演 md5（**「预演 == 交付」成立**）。

## 4. 线上验收

- `deploy_v2855.sh --skip-server` 内建核对 + 远端 `_remote_check_v2855.sh` → **REMOTE-CHECK: PASS (0 failures)**。
- 公开冒烟：`GET /myxxz/` → **200**；`GET /myxxz/assets/index-v2955-20261010.js` → **200**；未授权 API → **401**。
- 远端 `CHANGELOG_PLAYER.md` md5 == 本地（`ecb35ab75432a0ccf09f2138d2036a1d`），顶部条目即 `[0.9.55]`。
- 远端 `CHANGELOG.md` md5 == 本地（`8b51a980be81aebeb621311a0757fc3e`）。
- ★ 数据库变更：**本批无数据库变更**（快照 `database_v2955_consistent_20261010_221414.sqlite` 仅作回滚热拷贝）。
- ★ 服务端**未重启**（`--skip-server`）⇒ **零停机**。

## 5. 本轮踩到的新坑

1. **跨补丁门禁演进（第二例）**：R-241 合法改写了上游两条冻结针的锚区 ⇒ 4 条针脚失效：
   - `localtest/yl_r165_ext.py` 的 `R165·顿悟分支已挂入账`（锚 `E1_NEW`）⇒ 改 **tuple 合计**
     `(E1_NEW, E1_NEW_END)`；并给该脚本的针脚求值器补 tuple 支持。
   - `localtest/yl_r188_ext.py` 的 3 条 `R188v2·…【已退役·终态专用】`（锚旧概率式）⇒ 同样改 tuple
     `(R-221 形态, R-241 形态)`；并给 `_run_gates` 补 tuple 支持。
   ★ 教训同 §4.1：**更新上游 gates，绝不放宽断言**（旧形态归零 + 新形态 == 1，两面都断言）。
2. **`remote_check_v28NN.sh` 是「远端执行件」，不能本地直跑**：其 `[ -f "$B" ]` 判的是**远端路径**
   ⇒ 本地跑必 `MISSING … exit 99`（**假失败**）。正确姿势：scp 到 `/opt/yl/server/_remote_check_v2855.sh`
   后在远端以 `bash … <远端bundle> <远端index.ts>` 执行（deploy 第 630 行即如此）。
   ★ 本地等价验证走 `localtest/sim_remote_check.py`。
3. **remote_check 的 chk 也会被跨批改写打穿**：本批 `RETIRE_CHK` 由空变 2 条（③ 类冲突）——
   R242 改 `bd()` 心法段取值 ⇒ 退役 R238「冻结·心法贡献算式未动」；R241 改顿悟概率式 ⇒
   退役 R223「新概率式在位」。**退役不是放宽**：两条旧形态的新形态由本批 R241/R242 段**重新断言**
   （`(0.001667*(1+Math.min(1,` eq 1 / `(0.01+Math.min(0.03,` eq 0；`r=u.effects.expRate;` eq 1 / `Math.min(1.25` eq 0）。

## 6. 残留清理

远端 `_remote_check_v2855.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` 留在 `/opt/yl/server/` 便于复跑。
本地沙箱（`localtest/_r239_sandbox/`、`_r240*_sandbox/`、`_r241_sandbox/`、`_r242_sandbox/`、`_p1_sandbox/`）
已 gitignore，提交前可删。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2955-20261010_221414 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2955-20261010.js --to=index-v2954-20261010.js
cp -a /root/backup/index.ts.pre-v2955-20261010_221414        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2955-20261010_221414 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2955-20261010_221414    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2954-20261010.js.pre-v2955-20261010_221414 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版：bundle=aa49623854fad1bbe22f6ab3076b804f  server=328170ededb61fe3289845cb91d3419d
# 整包：/root/backup/yl_pre_v2955_20261010_221414.tar.gz
```

★ 回滚注意：数据库变更（若有）见 §4。回滚到上一版时**无需删列 / 删表**
（旧代码不读多余列，多余列无害）；**如需完全还原**用
`/root/backup/database_v2955_consistent_20261010_221414.sqlite` 热拷贝。

## 8. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=77d35f9c7a1570308cee19c319348e6a
PREV_SRV_MD5=328170ededb61fe3289845cb91d3419d
PREV_CHANGELOG_MD5=8b51a980be81aebeb621311a0757fc3e
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_PLAYER_MD5=ecb35ab75432a0ccf09f2138d2036a1d
PREV_SRV_CHAIN_TAIL_MD5=328170ededb61fe3289845cb91d3419d   # 链尾 _chainstage/s93.r233.ts（供单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
~/.ai-memory/topics/项目-摸鱼修仙传.md「当前版本」段。
