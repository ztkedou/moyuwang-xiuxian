# DEPLOY LOG — 《摸鱼修仙传》 0.9.53

- 部署时间：2026-10-10 15:49 (GMT+8)
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2853.sh`（**纯客户端批** ⇒ `--skip-server`，**零停机**）
- 定点核对：`deploy_v28/remote_check_v2853.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0853.env`
- 备份整包：`/root/backup/yl_pre_v2953_20261010_154855.tar.gz`
- DB 一致性快照：`/root/backup/database_v2953_consistent_20261010_154855.sqlite`

---

## 1. 本批范围（0.9.53；客户端 1 模块 + 服务端 93 环**不变**）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-238 | 悟道「禅道」的修炼加成实装 | `localtest/yl_r238_ext.py`（4 EDITS 纯追加式）→ `build_v26n.STANDALONE_CLIENT` 注册 `('r238', …)`（排 r228/r232 之后）| ✅ 1 模块 | — 零改动 |

**起因**：用户反馈「换心法后修炼效率没变化」。排查发现悟道面板的「禅道 · 修炼 +X%」
**只展示、从未被 `bd()` 读取** ⇒ 面板承诺的加成实际不生效。
完整排查见 `报告_修炼加成实装排查_20261010.md`。

**实现（4 处纯追加，旧字节零删除）**：

- **A** `function YlxwGet(r)` 之前注入 `YLXW_WUDAO_CULT` 缓存 + `YlxwWudaoCultPct` / `YlxwWudaoCultCapture` / `YlxwWudaoCultEnsure`；
- **B** `bd()` 的 `return{total:…}` 追加 `total + __wud`，并输出 `wudao` / `cWudao` 字段；
- **C** `YlxwApi()` 的公共落点 `YLApplyBalance(l, r);` 后挂 `YlxwWudaoCultCapture(r, l)`；
- **D** 属性面板明细行（`T.npc>0&&…羁绊…`）追加「悟道:+X%」。

**数值口径（与面板逐字同源）**：取 `/wudao` 响应 `daos[stat==='cultivate' || key==='array']`
的 `bonusPct ÷ 100`，权重 **K = 1.00**（与心法同级）⇒ **Lv3 +1.0% / Lv10 +2.75%**。

**防自激 / 防风暴**：仅当缓存值**变化**时才派发 `YlxwDirty()`；首屏兜底拉取**上限 20 次**，失败自动复位 `READY`。

★ **未覆盖（有意）**：离线收益（用户明确「不用管」）、服务端（数值早已下发）、心法六源算式与权重、
`YlxwArtExpRate` 品级覆盖表（「同品级心法无差异」属另一议题 —— 已另开《功法体系彻底重做》策划）。

## 2. 指纹（部署前后）

| 对象 | 上一版（部署前） | 本批（部署后） |
|---|---|---|
| `www/assets/index-v2952-20261009.js` | `f8d16a51fd516f91b8897dd553089ba7` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2951-20261009.js` | `48e7555ea90e0075fb5bc6c9a67904e0` | 同左（0.9.51 定版，更早的回滚点） |
| `www/assets/index-v2953-20261010.js` | —（新文件） | `e525b8027f9a90883db71d834583c5ec` |
| `server/index.ts` | `328170ededb61fe3289845cb91d3419d` | `328170ededb61fe3289845cb91d3419d`（**未变**） |
| `www/CHANGELOG.md` | `2e534a9d3f7d4817d449fdc3a79410f9` | `1d2ffd4a5b8b7bcd56be72445f82859a` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | `1b635513f553875060869272b790f910`（**不变**） |

部署后线上实测（deploy_v2853.sh 采集）：

```
328170ededb61fe3289845cb91d3419d  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
1d2ffd4a5b8b7bcd56be72445f82859a  /opt/yl/www/CHANGELOG.md
e525b8027f9a90883db71d834583c5ec  /opt/yl/www/assets/index-v2953-20261010.js
```

## 3. 部署前本地验收

- `_bump_0853.py`：升版**八处**预检 + 一致性复核全 OK（含 `CHANGELOG_PLAYER.md`，R-231 缺口已覆盖）。
- `localtest/dryrun_087.py`：**PASS（FAIL=0）**；预演产物 md5 `e525b802…` == 交付产物 md5 ⇒ **「预演==交付」成立**。
- `localtest/chain_build.py --all`：前端 + 服务端链（93 环；服务端产物 md5 与 0.9.52 **逐字节相同**）。
- **R-238 补丁自检**：门禁全绿（4 EDITS + 10 冻结项）· delta **+972 B** · `node --check` 通过 · 幂等重跑 **rc=3** · 单元测试 **12/12**。
- **三件套**：`bash -n` 双绿 · 纯 LF / 无 BOM / 换行结尾 · `sim_remote_check` **OK=850 SKIP=15 FAIL=0**。

## 4. 线上验收

- `remote_check_v2853.sh` → **PASS (0 failures)**。
- **本批无数据库变更**（纯客户端批）。
- 服务端**未重启**（`--skip-server` ⇒ **零停机**）。

## 5. 本轮踩到的新坑

1. ★★ **纯客户端批会被生成器硬断言卡死**：`_mk_2852.py:810` 的 `assert s_md5 != PREV_SRV_MD5`
   （「服务端必须变」口径）在纯批下**必然 AssertionError**。派生 `_mk_2853.py` 时须**反向为 `==`**
   （照纯客户端批范本 `_mk_2849.py:774`），并删除「链尾平移」断言（本批链尾 `s93.r233.ts` **不平移**）。
   逐项清单见 `_skipserver_audit.md`。
2. **`_bump` 脚本的 `%` 转义**：CHANGELOG 条目含「+2.75%」等**裸 `%`** ⇒ `%` 格式化会 `TypeError`，须写 `%%`。
3. **bundle 日期本批跨天**（20261009 → **20261010**），与 0.9.50/51/52 三批「不跨天」不同。
4. **`EXPECT_SRV_MD5` 语义**：纯批下它必须登「**线上正在跑**」的值（= 本批 `PREV_SRV_MD5`），
   否则即使 `--skip-server` 也会在 step0 的 md5 比对处 ABORT（最易踩的坑）。

## 6. 残留清理

远端 `_remote_check_v2853.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` 留在 `/opt/yl/server/` 便于复跑（惯例）。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2953-20261010_154855 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2953-20261010.js --to=index-v2952-20261009.js
cp -a /root/backup/index.ts.pre-v2953-20261010_154855        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2953-20261010_154855 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2953-20261010_154855    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2952-20261009.js.pre-v2953-20261010_154855 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版：bundle=f8d16a51fd516f91b8897dd553089ba7  server=328170ededb61fe3289845cb91d3419d
# 整包：/root/backup/yl_pre_v2953_20261010_154855.tar.gz
```

★ 回滚注意：本批**无数据库变更** ⇒ 回滚到上一版时无需删列 / 删表。

## 8. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=e525b8027f9a90883db71d834583c5ec        # 0.9.53 定版 index-v2953-20261010.js
PREV_LIVE_BUNDLE_MD5=f8d16a51fd516f91b8897dd553089ba7   # 0.9.52（回滚点）
PREV_SRV_MD5=328170ededb61fe3289845cb91d3419d           # 93 环（本批未动）
PREV_CHANGELOG_MD5=1d2ffd4a5b8b7bcd56be72445f82859a
PREV_PLAYER_MD5=b244f81ecadf42cbecfbbc60a0f41b1c
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=328170ededb61fe3289845cb91d3419d   # 链尾 _chainstage/s93.r233.ts
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。
