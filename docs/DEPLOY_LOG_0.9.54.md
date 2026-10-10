# DEPLOY LOG — 《摸鱼修仙传》 0.9.54

- 部署时间：2026-10-10 19:54 (GMT+8)
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2854.sh`（**纯客户端批** ⇒ `--skip-server`，**零停机**）
- 定点核对：`deploy_v28/remote_check_v2854.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0854.env`
- 备份整包：`/root/backup/yl_pre_v2954_20261010_195317.tar.gz`
- DB 一致性快照：`/root/backup/database_v2954_consistent_20261010_195317.sqlite`

---

## 1. 本批范围（0.9.54；客户端 1 模块 + 服务端 93 环**不变**）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-239 | 历练寿元消耗「手动/自动统一」 | `localtest/yl_r239_ext.py`（2 EDITS 就地替换）→ `build_v26n.STANDALONE_CLIENT` 注册 `('r239', …)`（排 r206 之后）| ✅ 1 模块 | — 零改动 |

**起因**：用户反馈「普通点击的历练寿命减的有点多」。排查发现历练单次寿元消耗 = 风险档系数 × `YlxwLifeMul()`，
默认风险档 = 0.4：手动历练 `__ylLifeAuto` 假 ⇒ `YlxwLifeMul()` 返回 1 ⇒ 单次 = **0.40**（用户截图「寿元 -0.40」）；
挂机历练 `__ylLifeAuto` 真 ⇒ 返回 `YLXW_LIFE_AUTO_MUL = 0.0125` ⇒ 单次 = 0.005。

**实现（2 处就地替换，幂等标记 `/*[r239life]*/`）**：

- **A** 函数体 `try { return window.__ylLifeAuto ? YLXW_LIFE_AUTO_MUL : 1; } catch (e) { return 1; }`
  → `try { return YLXW_LIFE_AUTO_MUL; } catch (e) { return 1; }`；
- **B** 注释 `/* 自动历练寿元扣减系数（手动 = 1.0） */` → `/* 历练寿元扣减系数（手动/自动统一） */`。

**数值口径**：手动 = 挂机 = 0.4 × 0.0125 = **0.005**；风险档相对比例保留
（低 0.3 → 0.00375 / 普通 0.4 → 0.005 / 中 0.6 → 0.0075 / 高 1.0 → 0.0125 / 极度危险 1.5 → 0.01875 / 秘境 1.0 → 0.0125）。

★ **绝不碰**：风险档表、`S.lifespan=` 结算行、`lifespanChange`、`YLXW_LIFE_AUTO_MUL = 0.0125;`、
`var YLXW_MED_LIFE = 0.001;`、既有标记 `/*[r206life]*/` `/*[r180adv4]*/`。

★ **未覆盖（有意）**：心法 / 天赋 / 称号 / 洞府 / 协同 / 羁绊 六项加成、离线收益，一律未动。

## 2. 指纹（部署前后）

| 对象 | 上一版（部署前） | 本批（部署后） |
|---|---|---|
| `www/assets/index-v2953-20261010.js` | `e525b8027f9a90883db71d834583c5ec` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2952-20261009.js` | `f8d16a51fd516f91b8897dd553089ba7` | 同左（0.9.52 定版，更早的回滚点） |
| `www/assets/index-v2954-20261010.js` | —（新文件） | `aa49623854fad1bbe22f6ab3076b804f` |
| `server/index.ts` | `328170ededb61fe3289845cb91d3419d` | `328170ededb61fe3289845cb91d3419d`（**未变**） |
| `www/CHANGELOG.md` | `1d2ffd4a5b8b7bcd56be72445f82859a` | `e36e2a0b2c3378cf3f3f145d14d93130` |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | `1b635513f553875060869272b790f910`（本批不变） |

部署后线上实测（deploy_v2854.sh 采集）：

```
328170ededb61fe3289845cb91d3419d  /opt/yl/server/index.ts
1b635513f553875060869272b790f910  /opt/yl/server/game-dicts.json
e36e2a0b2c3378cf3f3f145d14d93130  /opt/yl/www/CHANGELOG.md
aa49623854fad1bbe22f6ab3076b804f  /opt/yl/www/assets/index-v2954-20261010.js
```

## 3. 部署前本地验收

- `localtest/dryrun_087.py` → 门禁 **FAIL=0**；「预演 == 交付」双 provenance 一致（step 0c 已过）。
- `localtest/sim_r231_inject.py --new 0.9.54 --prev 0.9.53` → **FAILS=0**（R-231 双路径注入回归）。
- `localtest/sim_remote_check.py --script deploy_v28/remote_check_v2854.sh` → **FAIL=0**。
- 三件套 `bash -n` 双绿；纯 LF / 无 BOM。
- 链 `s20.t16arena.ts` == `7780e099a6cd1ac0de4b502c467ae2c0`（前 20 环 == 0.8.9 定版）；服务端 93 环链尾仍 `s93.r233.ts`。
- 浏览器冒烟（0.9.54 本地预览）：历练手动单次寿元扣减显示 **-0.005**，挂机同值。

## 4. 线上验收

- `deploy_v28/remote_check_v2854.sh` → **PASS (0 failures)**。
- 公开冒烟：`GET https://moyuwang.online/myxxz/` → 200；未授权 API → 401。
- `CHANGELOG_PLAYER.md` 远端 == 本地 md5（`bc66e7d86b11be66d3724291688a6352`），顶部条目即 `[0.9.54]`。
- `index.html` 引用巡检 == `assets/index-v2954-20261010.js`。
- ★ 数据库变更：**本批无数据库变更**。

## 5. 本轮踩到的新坑

1. **跨补丁门禁演进（不是放宽，是收窄/等价改写）**：R-239 把 `YlxwLifeMul()` 由「按 `__ylLifeAuto` 分流」
   改为「恒返回 `YLXW_LIFE_AUTO_MUL`」⇒ 上游两条冻结针失效：
   - R-139 的 `__ylLifeAuto` 计数由 2 降为 1 ⇒ 收窄为「历练主循环赋值 `window.__ylLifeAuto=Q()`」（== 1）；
   - R-206 的 `YlxwLifeMul` 函数体针 ⇒ 改用 **tuple 合计**（旧形态 + 新形态），两种场景均 == 1。
   ★ 教训：新补丁合法改写上游冻结项时，**更新上游 gates**，绝不放宽断言。
2. **`sim_r231_inject.py` 版本耦合**：曾硬编码 0.9.52/0.9.51，升版后语义漂移 ⇒ 本批泛化为 `PREV`/`_dec(PREV)`，
   传 `--new/--prev` 即可，无需再改脚本。

## 6. 残留清理

远端 `_remote_check_v2854.sh` / `_remote_swap.sh` / `_live_bump_bundle.js` 留在 `/opt/yl/server/` 便于复跑。
本地沙箱（`localtest/_r239_sandbox/` 等）已 gitignore，提交前可删。

## 7. 回滚

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2954-20261010_195317 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2954-20261010.js --to=index-v2953-20261010.js
cp -a /root/backup/index.ts.pre-v2954-20261010_195317        /opt/yl/server/index.ts
cp -a /root/backup/game-dicts.json.pre-v2954-20261010_195317 /opt/yl/server/game-dicts.json
cp -a /root/backup/CHANGELOG.md.pre-v2954-20261010_195317    /opt/yl/www/CHANGELOG.md
# 旧包文件未删，无需还原；如被误删：cp -a /root/backup/index-v2953-20261010.js.pre-v2954-20261010_195317 /opt/yl/www/assets/
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版：bundle=e525b8027f9a90883db71d834583c5ec  server=328170ededb61fe3289845cb91d3419d
# 整包：/root/backup/yl_pre_v2954_20261010_195317.tar.gz
```

★ 回滚注意：数据库变更（若有）见 §4。回滚到上一版时**无需删列 / 删表**
（旧代码不读多余列，多余列无害）；**如需完全还原**用
`/root/backup/database_v2954_consistent_20261010_195317.sqlite` 热拷贝。

## 8. 本批定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=aa49623854fad1bbe22f6ab3076b804f
PREV_SRV_MD5=328170ededb61fe3289845cb91d3419d
PREV_CHANGELOG_MD5=e36e2a0b2c3378cf3f3f145d14d93130
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_CHAIN_TAIL_MD5=328170ededb61fe3289845cb91d3419d   # 链尾 _chainstage/s93.r233.ts（供单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
~/.ai-memory/topics/项目-摸鱼修仙传.md「当前版本」段。
