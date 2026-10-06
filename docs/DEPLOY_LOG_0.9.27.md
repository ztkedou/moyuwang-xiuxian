# DEPLOY LOG — 《摸鱼修仙传》 0.9.27

- 部署时间：**2026-10-06 17:36 (GMT+8)**
- 目标：Azure HKVPS `104.208.x.x` / `https://moyuwang.online/myxxz/`
- 脚本：`deploy_v28/deploy_v2827.sh` **`--skip-server`**（★ 纯客户端批；客户端 + CHANGELOG + index.html bump）
- 定点核对：`deploy_v28/remote_check_v2827.sh` → **PASS (0 failures)**
- 登记指纹：`deploy_v28/EXPECT_0827.env`
- 备份整包：`/root/backup/yl_pre_v2927_20261006_173640.tar.gz`
- 生成器：`_mk_2827.py`（deploy）/ `_mk_rc2827.py`（remote_check）—— 机械重登记，**只做整名替换**（铁律 D）

---

## 1. 本批范围：0.9.27（客户端 95 模块 + **36** standalone 脚本；服务端 **77 环·零改动**）

| # | 任务 | 落点 | 客户端 | 服务端 |
|---|---|---|---|---|
| R-169 二环 | 洞府灵草「配置信息缺失·折算回收」彻底根治 | `localtest/yl_r169b_ext.py` | ✔ | —（零改动） |

### 用户拍板原文（2026-10-06 17:19）
> 「3.没有映射的就补上这个道具，如果不好补就删除这个灵草选项。**总之不要再出现现在这种情况**」

### 根因
**种植与收获不对称**：
- 种植 `m`（@1951472）在灵草表 `wn` 查不到时，会调合成函数 `f(name, rarity)`（@1948652）**现场合成**一个灵草定义
  （`id = "herb-"+name`）⇒ 任意「草药类」背包物品都能种下；
- **收获 `j` 没有这个合成兜底**，只查 `wn` 20 味正式表 ⇒ 旧存档里改名前的旧名 / 随机词缀杂名
  一到收获就弹「⚠️ 灵草【X】的配置信息缺失，已按 N 灵石折算回收（每个 300 灵石）」。

### 修法（两条腿，对应用户「补上道具 / 删掉选项」）
**腿 ① 补上道具** —— 让收获路径与种植路径对称：四级查找全落空时改为调用**与种植完全同一个** `f(__hn, "普通")`
现场合成灵草定义（同名每次结果一致 ⇒ 幂等）⇒ 按正常路径收获、进背包为真实道具。
覆盖 `天灵草 / 星辰草 / 凤羽草 / 灵凤羽草 / 雪莲花` 等全部遗留旧名。
（`plantedHerbs[]` 不存 rarity，故用 `"普通"` —— 与批量收获 / 自动收获的 `||"普通"` 口径逐字一致。）

**腿 ② 删掉选项** —— 名字非法/为空导致连合成都失败时，在洞府**灵田列表**渲染处（`T.plantedHerbs.map(...)` @1855513）
加空名守卫 `return null` 过滤该条目（保留原下标，按钮仍指向正确槽位），
只给中性提示「🍂 灵草【X】已失效，已从灵田移除。」（`type="normal"`，**不发灵石补偿**）。
图鉴（herbarium）列表实际是 `wn.map(...)` 遍历 20 味正式表 ⇒ 旧名/杂名本就不会出现，天然已过滤，未改动。

**腿 ③ 5 个遗留旧名逐个结论 = 补 0 个**（依据「语义明确 **且** 不与现行物品冲突」两条须同时满足）：
| 名字 | 结论 | 理由 |
|---|---|---|
| 天灵草 | **不补** | 现行商店灵草 `ys("天灵草",35)`（@1599530），与 wn 的 `天灵果(spirit-fruit)` 非同物；重名冲突 |
| 雪莲花 | **不补** | 现行抽奖物品 `lottery-material-snow-lotus`（@470991）；重名冲突 |
| 星辰草 / 凤羽草 / 灵凤羽草 | **不补** | wn 无对应系；三名是**随机词缀生成**（herbEffects 含「星辰/凤羽」+ herbTypes 含「草」），非设计品种 |
| — | — | 附：`wn.length` 被图鉴进度分母（已收集/wn.length、%完成）直接使用，增条目会把分母 20→N（可见副作用）⇒ 非必要不动 |
⇒ 统一走腿 ① 的合成兜底。

### 红线达成（线上实测）
```
折算回收        : 0   （原 1，分支**已删除**，非死代码）
配置信息缺失    : 0   （原 1）
h.spiritStones+__sv : 0   （不再发放折算灵石）
合成兜底        : 1   （if(!_&&__hn){try{_=f(__hn,"普通")}catch(__e){_=null}}）
```
另两条收获路径（批量收获 `b` / 自动收获 useEffect）**本来就没有**折算兜底，本环未动（gate 冻结）。

## 2. 指纹（部署前后）

| 对象 | 0.9.26（部署前） | 0.9.27（部署后，线上实测） |
|---|---|---|
| `www/assets/index-v2926-20261006.js` | `6ed91e0e46b90fada980367459cbe3fc` | 同左（旧包保留不删 = 回滚点） |
| `www/assets/index-v2925-20261006.js` | `153c19120249210e7aa546eeb6ab740a` | 同左（0.9.25 定版，更早的回滚点） |
| `www/assets/index-v2927-20261006.js` | —（新文件） | **`c3b2c9bab29830de1f831b8d6d012171`** |
| `server/index.ts` | `a5927a49b17d5262aa12b3f61f27d740` | **同左（★ 本批零改动）** |
| `www/CHANGELOG.md` | `7069fe8525c81e990dd527827a67a275` | **`33db9d937823e429873f1ee90dc16156`** |
| `server/game-dicts.json` | `1b635513f553875060869272b790f910` | 同左（本批未变） |

## 3. 部署前本地验收

| 环节 | 命令 | 结果 |
|---|---|---|
| 前端装配（服务端链不变） | `localtest/chain_build.py --all` | rc=0；**77 环**；srv md5 = `a5927a49…` 与 0.9.26 **逐位相同**（确认纯客户端批） |
| 客户端预演 | `localtest/dryrun_087.py` | 门禁 **PASS（FAIL=0）**；standalone 741 → **763** 条；「预演==交付」md5 `c3b2c9ba…` 一致 |
| 远端断言本地预演 | `localtest/sim_remote_check.py --script deploy_v28/remote_check_v2827.sh` | **OK=467 / SKIP=15 / FAIL=0** |
| 部署件指纹一致性 | `deploy_v2827.sh` vs `EXPECT_0827.env` 的 6 个 `PREV_*` | 6/6 逐字一致 |

## 4. 线上验收

| 项 | 结果 |
|---|---|
| `REMOTE-CHECK` | **PASS (0 failures)** |
| 新 bundle | `c3b2c9bab29830de1f831b8d6d012171`（2,302,499 B） |
| 服务端 index.ts | `a5927a49b17d5262aa12b3f61f27d740`（未变，77 环） |
| CHANGELOG.md | `33db9d937823e429873f1ee90dc16156` |
| 游戏内版本号 | `YLVERSION_FALLBACK = "0.9.27"` |
| 服务 | `yl-server` **active**，`NRestarts=0` |
| ★ 红线（线上产物实测） | `折算回收` = **0**、`配置信息缺失` = **0**、合成兜底 = **1** |
| ★ gzip 同包（R-159 防线） | `zcat /opt/yl/www/index.html.gz` 命中 `assets/index-v2927-20261006.js` ×1 |
| ★ 公网带 `Accept-Encoding: gzip` 冒烟 | http=200，gunzip 后命中 v2927 ×1 |
| 新包可访问 | `GET /myxxz/assets/index-v2927-20261006.js` → 200 |
| CHANGELOG 公网 | `GET /myxxz/CHANGELOG.md` → 200，顶部为 `## [0.9.27] - 2026-10-06 17:36` |

## 5. 本轮踩到的新坑（★ 务必保留）

1. ★★ **跨模块门禁冲突（本批新坑，与 0.9.23 的 `yl_r138_ext.FRZ_HEADER` 同类）**：
   `yl_r169_ext.py`（一环）把「折算回收」那几条串**冻结成必须存在（==1，注释写"不删退路"）**，
   而 `yl_r169b_ext.py`（二环）正是要**删掉**它们 ⇒ `dryrun_087.py` 首轮 **FAIL 4 条**。
   - **修法（不是静默删断言）**：在 `yl_r169_ext.py` 里新增 `POST_ZERO` 列表（列明那 4 条针脚），
     `gates()` 遇到它们**跳过**（附注释：断言已**移交** `yl_r169b_ext.py`，由它断言 ==0），
     `_precheck` 仍按**原件**校验 ==1。
   - ★ **为什么不能直接把 expect 改成 0**：`yl_r169_ext.py` 的 `main()`（= `build_v26n.apply_standalone`
     的调用路径）在**本环应用后**也会跑 `_run_gates(out)`，那一刻二环还没跑、这些串合法地 ==1
     ⇒ 若在此断言 0 会**在装配中途误报 ABORT**。**教训：standalone 补丁的 gates() 会被应用路径复用，
     其预期值必须对「本环刚应用完」的中间形态成立，不能按最终形态写。**
2. ★ **纯客户端批必须 `--skip-server`**：`deploy_v2827.sh` 的 step 0 有
   「`SKIP_SERVER=0 && LS_MD5 == PREV_SRV_MD5` ⇒ ABORT」断言；服务端零改动时 PREV 与 EXPECT 的 srv md5
   相同 ⇒ 不加 `--skip-server` 必被拦下。
3. ★ **bundle 内中文形态不统一**：R-169b 所在区块是**裸中文**（`\u6298\u7b97\u56de\u6536` 转义形态 count==0），
   而 R-167 所在区块是**转义存储**。⇒ remote_check 断言**动手前两种形态都 grep**（0.9.26 已踩过一次）。
4. **`yl_r169_ext.py` 的 R1 锚点含裸中文**（该块必须整段替换删除，无法纯 ASCII 化）—— 已在补丁文件头 §六 如实登记。

## 6. 残留清理

远端 `_remote_check_v2827.sh` / `_live_bump_bundle.js` / `_remote_gz_sync.sh` 留在 `/opt/yl/server/` 便于复跑（惯例）。
本地：`_chainstage/` 各环产物保留（供单变量可核）；补丁自测产生的临时副本与 `.bak-*` 已全部删除。

## 7. 回滚（本轮动了新包 + index.html + CHANGELOG；服务端未动 ⇒ 无需回滚 index.ts）

```bash
ssh -i ~/.ssh/ali-hk-47.243.x.x.key root@104.208.x.x
# index.html 指回旧包（二选一：还原备份 或 live_bump 反向）
cp -a /root/backup/index.html.pre-v2927-20261006_173640 /opt/yl/www/index.html
#   或： /usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2927-20261006.js --to=index-v2926-20261006.js
cp -a /root/backup/CHANGELOG.md.pre-v2927-20261006_173640    /opt/yl/www/CHANGELOG.md
# 服务端本批未变 ⇒ index.ts / game-dicts.json 无需回滚（备份件仍在 /root/backup/）
systemctl restart yl-server && systemctl is-active yl-server
# 上一版定版（0.9.26）：bundle=6ed91e0e46b90fada980367459cbe3fc  server=a5927a49b17d5262aa12b3f61f27d740
# 整包：/root/backup/yl_pre_v2927_20261006_173640.tar.gz
```

★ 回滚注意：本批**无 DDL**（无新表/新列）⇒ 回滚无需任何库操作。

## 8. 0.9.27 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=c3b2c9bab29830de1f831b8d6d012171        # 0.9.27 定版 index-v2927-20261006.js
PREV_SRV_MD5=a5927a49b17d5262aa12b3f61f27d740           # 0.9.27 定版 srv/index_v28.ts（= s77.r173.ts，77 环；与 0.9.26 相同）
PREV_CHANGELOG_MD5=33db9d937823e429873f1ee90dc16156     # 0.9.27 定版 CHANGELOG.md
PREV_DICTS_MD5=1b635513f553875060869272b790f910
PREV_SRV_S77_MD5=a5927a49b17d5262aa12b3f61f27d740       # 链尾 s77.r173.ts（供 0.9.27 单变量可核）
```

★ 收尾（版本铁律④）：上线核验通过后，把新版本号 + 三项指纹回写
`~/.ai-memory/topics/项目-摸鱼修仙传.md`「当前版本」段。

## 9. 本批遗留（待用户）
- **R-170 财富组成就奖励**：用户要求先看全量对照 ⇒ 已产出
  `需求台账\拍板\2026-10-06_1720_R-170成就奖励全量对照与备选.md`（5 组 × 10 档 + 4 备选）。
  **线上当前仍为严格正比版**（财富组末档 1 亿）。**待用户回「A/B/C/D」**（我方建议 B·封顶 500 万）。
- **R-165**：已拍板「不补」，闭环。
