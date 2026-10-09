# DEPLOY LOG — 《摸鱼修仙传》 0.9.50

- 部署时间：2026-10-09 23:03 (GMT+8)
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2850.sh`（客户端 + 服务端 + CHANGELOG + index.html bump）
- 本批类型：**服务端有变**（90 → 91 环，新末环 `s91.r225.ts`）⇒ **有停机**（秒级，`NRestarts=0`）
- 定点核对：`deploy_v28/remote_check_v2850.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0850.env`
- 备份整包：`/root/backup/yl_pre_v2950_20261009_230216.tar.gz`
- DB 一致性快照：`/root/backup/database_v2950_consistent_20261009_230216.sqlite`（sqlite3 CLI `VACUUM INTO`：ok）

---

## 1. 本批范围（0.9.50；客户端 134 模块 + 服务端 91 环）

> 规模口径：`CLIENT_MODULES` / `SRV_RINGS` 由部署脚本运行环境填充（未设时显示 `<待填>`）；
> 取值见本批 `localtest/dryrun_*.py`（客户端模块数）与 `localtest/chain_build.py`（服务端环数）输出。

· R-227 specialAbility 死数据：保留 25 条数据段（一字未删）+ 3 处显式标注（纯客户端 `yl_r227_ext.py`）
· R-228 修炼效率明细行改与 `bd()` 同源：`bd()` 尾段拆具名局部量 + 新增 `cArt/cTalent/cTitle/cGrotto/cSynergy/cNpc`，明细行改读 `c*`（纯客户端 `yl_r228_ext.py`）
· R-230 天地之髓掉落门槛 `[化神,∞)` → `[元婴,化神]`：与天地精华同构，4 处同改（历练 / 额外 / 黑市 + `minRealm`）（纯客户端 `yl_r230_ext.py`）
· R-225 服务端离线收益吃难度倍率（**服务端第 91 环** `srv_patch_r225.py`；客户端零改动）
· R-224 DEPLOY_LOG 模板改版本无关 + 变量填充（部署件自身）
· R-229 chk 描述串 R 号错配修正 + 裸「本批」措辞改相对表述（部署件自身）

## 2. 指纹（部署前后）

| 对象 | 上一版（部署前） | 本批（部署后） |
|---|---|---|
| `www/assets/index-v2949-20261009.js` | `d8fac7c23951a88c739579726823fb2c` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2948-20261009.js` | `a01d9aa7959bfabe57e3f91fe893ac79` | 同左（0.9.48 定版，更早的回滚点） |
| `www/assets/index-v2950-20261009.js` | —（新文件） | `f18d9cb8440657e1aa51de1a95c89c9c` |
| `server/index.ts` | `f0f6b69d578854660e0ae32191b233bf` | `ac5c521d726fa74193d96071d63f702d` |
| `www/CHANGELOG.md` | `d15edd1f942960062163ff2de98099cd` | `38b7b622882efadb7c6533f4e098c2d2` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | `1b635513f553875060869272b790f910`（本批不变） |

部署后线上实测（deploy_v2850.sh 采集）：

```
ac5c521d726fa74193d96071d63f702d  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
38b7b622882efadb7c6533f4e098c2d2  /opt/yl/www/CHANGELOG.md
f18d9cb8440657e1aa51de1a95c89c9c  /opt/yl/www/assets/index-v2950-20261009.js
```

## 3. 部署前本地验收

`deploy_v2850.sh` step 0 / 0c 实测（全部通过）：

- CHANGELOG_PLAYER 格式 81/81 OK、每个版本都有 `### 分类`；`CHANGELOG [0.9.50] gate: OK`。
- `EXPECT_0850.env` 四项 md5 全符：bundle `f18d9cb8440657e1aa51de1a95c89c9c`（2,327,686 B）、
  srv `ac5c521d726fa74193d96071d63f702d`、dicts `1b635513f553875060869272b790f910`、CHANGELOG `38b7b622882efadb7c6533f4e098c2d2`。
- canon `_chainstage/index_v28.v28112.ts` == `srv/index_v28.ts` == `EXPECT_SRV_CANON_MD5`；
  前端基座 `index-v26m-20260927.js` == `b315eb1a04e967a66c128861b3a3dadd`。
- step 0c 双 provenance：预演 `_chainstage/dryrun_087.bundle.js` == 交付 bundle；链尾 `s91.r225.ts` == `srv/index_v28.ts`；
  `s20.t16arena.ts` == `7780e099a6cd1ac0de4b502c467ae2c0`（前 20 环 == 0.8.9 定版，单变量可核成立）。
- 远端未漂移断言：`index.ts` == `f0f6b69d…`（0.9.49）、`index-v2949-20261009.js` == `d8fac7c2…`、
  `index-v2948-20261009.js` == `a01d9aa7…` 三项全符。

## 4. 线上验收

- `remote_check_v2850.sh`（scp 后远端执行）：**PASS (0 failures)**，854 条 `[OK]`。
- 公网冒烟：`/myxxz/` = 200；`index.html`（明文 + gzip 双路）→ `assets/index-v2950-20261009.js`；
  公网 bundle md5 `f18d9cb8440657e1aa51de1a95c89c9c`（2,327,686 B）逐位一致；`/myxxz/api/save`（GET + POST）无 token = 401。
- 本批特征（公网 bundle，`grep -o -F | wc -l`）：`YLXW_R227_DEADDATA` ×3、`YLXW_R228_V2949` ×1、
  R230 新串（历练区间 / `minRealm:ae.NascentSoul`）各 ×1、旧串 ×0。
- 服务端：`ylR225DiffMul` ×7 / `ylR225OfflineMults` ×4；`index.ts` 线上实测 `ac5c521d…`。
- ★ 数据库变更：**本批无数据库变更**（R-225 仅改离线收益倍率计算，无建表 / 加列）。

## 5. 本轮踩到的新坑

- 任务书描述 §1 占位为 `/* <待补> */`（6 处），实际 `deploy_v2850.sh` 的 R-224 模板 §1 用的是 markdown 表格
  `| <待补> | <待补> | <待补> | <待补> | <待补> |`（5 格）+ 1 行 `<待补：…>` 说明；模板头部亦无「本批类型」行。
  ⇒ 已按任务书**意图**回填：§1 换成 6 行本批范围（逐字），头部补一行「本批类型」。

## 6. 残留清理

- 远端 `/opt/yl/server/` 保留 `_remote_check_v2850.sh` / `_remote_swap.sh` / `_live_bump_bundle.js`（便于复跑，惯例）。
- 本批未做写库测试，无测试账号 / DB 残留。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2950-20261009_230216 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2950-20261009.js --to=index-v2949-20261009.js
cp -a /root/backup/index.ts.pre-v2950-20261009_230216        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2950-20261009_230216 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2950-20261009_230216    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2949-20261009.js.pre-v2950-20261009_230216 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版：bundle=d8fac7c23951a88c739579726823fb2c  server=f0f6b69d578854660e0ae32191b233bf
# 整包：/root/backup/yl_pre_v2950_20261009_230216.tar.gz
```

★ 回滚注意：数据库变更（若有）见 §4。回滚到上一版时**无需删列 / 删表**
（旧代码不读多余列，多余列无害）；**如需完全还原**用
`/root/backup/database_v2950_consistent_20261009_230216.sqlite` 热拷贝。

## 8. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=f18d9cb8440657e1aa51de1a95c89c9c
PREV_SRV_MD5=ac5c521d726fa74193d96071d63f702d
PREV_CHANGELOG_MD5=38b7b622882efadb7c6533f4e098c2d2
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=ac5c521d726fa74193d96071d63f702d   # 链尾 _chainstage/s91.r225.ts（供单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
~/.ai-memory/topics/项目-摸鱼修仙传.md「当前版本」段。
