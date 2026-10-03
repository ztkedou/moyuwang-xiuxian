# DEPLOY LOG — 《摸鱼修仙传》 0.9.15（一行热修：灵玉阁余额恒 0）

- 部署时间：2026-10-02 **23:02** (GMT+8)（index.html 原子 swap 时刻；备份戳 `20261002_230206`）
- 目标：香港 VPS `47.243.x.x` / `https://moyuwang.online/myxxz/`
- 执行方式：**paramiko 直发**（不走 deploy_v2811.sh 全量机械——本批纯客户端单点热修，服务端零接触、无维护窗口）：
  预检未漂移 → tar 备份 + 逐文件 `.pre` → bundle `.new` 上传 md5 校验 → 原子 mv → index.html 同法切换 →
  CHANGELOG 两份以实际 swap 时刻校准后上传 → 健康/判活检查 → 本机独立公网复验
- 范围：**纯客户端 1 处显示修复**；服务端 `index.ts` 零改动（65 环不变）、DB 零 DDL、零新端点

---

## 1. 缺陷与修法

| 项 | 内容 |
|---|---|
| 玩家可见 | 活动中心 → 灵玉阁「我的灵玉：」恒显 0；「灵玉 +N」掉玉 toast 永不弹 |
| 根因 | 客户端 `var bal = d && typeof d.balance === "number" ? d.balance : null;`，而服务端 [v2810] 起 GET /api/activity/shop 只发 `{jadeBalance,...}`（0.9.14 线上同页 fetch 实证 `{"jadeBalance":4,...}`，bundle 内 `jadeBalance` 0 命中）⇒ bal=null ⇒ YlxwNum(null)=0 |
| 修法 | 改读 `d.jadeBalance` 优先 + `d.balance` 兜底（服务端响应无 balance 字段，无撞名，兜底仅防未来回退）；`typeof === "number"` 形态保留（对齐组件风格，0 值正确） |
| 落点 | standalone 模块 `localtest/yl_r131fix_ext.py`（r116 契约：--src / 二进制 / 原子写回 / .bak / 幂等 rc=3 / gates()），接线 `build_v26n.STANDALONE_CLIENT`（第 12 个）+ `dryrun_087` standalone 门禁名单 |
| 标记 | `YLXW_R131FIX_V2915`（bundle 内 1 处注释）；字节 delta **+131 B** |
| 冻结 | 邻位 balance 语义不碰：j.balance（存档仲裁）×1、t.balance（心法面板）×3；YlxwTActShop ×2、我的灵玉文案 ×1、/activity/shop 两端点、YLACT_LAST_JADE ×5 |

## 2. 门禁与沙盒（上线前全绿）

- 升版七处同步：`build_v26n.OUT`、`dryrun_087`（VERSION+BUNDLE_BASENAME）、`patches/client/yl_version_ext.py`
  （DEFAULT_VERSION + INJECT_JS 字面量 + 滚动清零门禁加 0.9.14）、`chain_build.CLIENT_OUT`、`build/index.html`（.bak-pre0915）、
  `CHANGELOG.md`、`CHANGELOG_PLAYER.md`（0.9.14 批新坑 §5.1 的第五处）
- `localtest/dryrun_087.py`：**4242 + 275 standalone 门禁，FAIL=0**；R131FIX 门禁 9 条全 OK（含旧形态清零、
  在位标记、邻位冻结）；接线/版本四件套一致性 OK
- `build_v26n.py`：rc=0；**预演==交付**：`_chainstage/dryrun_087.bundle.js` 与 `build/assets/index-v2915-20261002.js`
  **md5 逐位一致 = `41721861172d4655a9765e2a10423c63`**（2,278,270 B）
- 沙盒 s15（服务端显式 `--srv=srv/index_v28.ts` = 生产同源 65 环产物 md5 `9033c805…`；冻结基座无 activity/shop
  端点不可用）：seed 三号 + 直写 `activity_token(token_key='lingyu')`（ylt_mid=123 / ylt_max=4567）→
  Playwright `--no-proxy-server`：**8/8 PASS** = 两号「我的灵玉」面板值 == API jadeBalance == 页内 YlxwGet
  （123 / 4567），harness 所服 bundle 含补丁标记、index.html 引用 v2915（证据：`_sb15_r131_ui.log` +
  `_r131_sbx_ylt_mid.png`/`_r131_sbx_ylt_max.png`/`_r131_sbx_shop_panel.png`）

## 3. 发布指纹（远端实测）

| 对象 | 0.9.14（部署前） | 0.9.15（部署后） |
|---|---|---|
| `www/assets/index-v2915-20261002.js` | —（新文件） | **`41721861172d4655a9765e2a10423c63`**（2,278,270 B / 95 模块+12 standalone） |
| `www/assets/index-v2914-20261002.js` | `e3760e1ec536e5e04760d1bfd84dc069` | 同左（旧包保留不删 = 回滚点，公网 200） |
| `server/index.ts` | `9033c805be1022e692bc67f7ccc3b1ae`（65 环） | **同左（零接触，预检未漂移）** |
| `www/index.html` | 引用 v2914 ×1 | 引用 **v2915** ×1，md5 `6686e4912ad34a54054f507f8c4e29f7` |
| `www/CHANGELOG.md` | `ee1e6508c09474eba3f2a0e1513ebdb0` | **`6d5557543190e366f34235640f42618e`**（头条 `## [0.9.15] - 2026-10-02 23:02`） |
| `www/CHANGELOG_PLAYER.md` | `89b4fc05f7dd287c1a01bba97a10f637` | **`77c7561d66df38f2e2a4ba184b9382b6`**（补 [0.9.15] 玩家向条目） |

```
41721861172d4655a9765e2a10423c63  /opt/yl/www/assets/index-v2915-20261002.js
6686e4912ad34a54054f507f8c4e29f7  /opt/yl/www/index.html
9033c805be1022e692bc67f7ccc3b1ae  /opt/yl/server/index.ts
6d5557543190e366f34235640f42618e  /opt/yl/www/CHANGELOG.md
77c7561d66df38f2e2a4ba184b9382b6  /opt/yl/www/CHANGELOG_PLAYER.md
```

## 4. 线上验收（两路独立）

- **VPS 侧公网 curl**：首页 200 且引用 v2915 ×1｜新 bundle **200 / 2,278,270 B / md5 与本地逐位一致**｜
  旧包回滚点 200｜CHANGELOG 200 头条 [0.9.15] 23:02｜判活 no-token 全 **401**（shop / snapshots / arena/week /
  shop/exchange POST）
- **本机独立复验**（urllib 直连不走代理，不经部署脚本）：五项 ALL GREEN（首页 200+引用 v2915；bundle
  200/2,278,270/md5 同；旧包 200；CHANGELOG 200+[0.9.15]；shop no-token 401）
- journalctl 23:02 后 error/exception/fatal = **0 行**；`yl-server` **active** / **NRestarts=0**（服务端未动）
- **生产注册冒烟：未跑**（纯显示热修，不在本环节指令内；字段形态实证 = 沙盒 s15 生产同源服务端 + 0.9.14
  线上 fetch 先证）

## 5. 备份与回滚

```
# 备份
/root/backup/yl_pre_v2915_20261002_230206.tar.gz   # index.html + CHANGELOG.md + CHANGELOG_PLAYER.md
/root/backup/{index.html,CHANGELOG.md,CHANGELOG_PLAYER}.md.pre-v2915-20261002_230206

# 回滚（纯客户端：指回旧包即彻底还原）
/usr/local/node22/bin/node /opt/yl/server/_live_bump_bundle.js --from=index-v2915-20261002.js --to=index-v2914-20261002.js
#   或： cp -a /root/backup/index.html.pre-v2915-20261002_230206 /opt/yl/www/index.html
# 0.9.14 定版：bundle=e3760e1ec536e5e04760d1bfd84dc069  server=9033c805be1022e692bc67f7ccc3b1ae（未动无需回滚）
```

★ 回滚语义：零 DDL、零新列、零服务端改动；回滚后灵玉阁回到「恒显 0」的旧显示态，数据无损。

## 6. 偏离与遗留

1. **部署不走 deploy_v2811.sh/remote_check/EXPECT 机械**（任务指定 paramiko 直发）⇒ 三件仍钉在 0.9.14
   （OLD_BUNDLE=b4586dba 时代的断言面）。下一批若恢复全量机械，按 §8 指纹推进 OLD_BUNDLE/PREV_*。
2. 沙盒显式用了 `--srv=srv/index_v28.ts`（生产同源）而非默认冻结基座——冻结基座（0.8.1 代）无
   activity/shop 端点，测不了本修。
3. `sim_remote_check.py` 本轮未跑（其断言面属 remote_check 机械，同 §6.1 一并留给下批）。
4. GitHub staging 仍在 0.9.13/0.9.14 态，本批未同步（继承 0.9.14 遗留）。
5. 沙盒 s15 用完即 down（证据已留 log/截图）；账号 ylt_* 仅存在于沙盒库。

## 7. 0.9.15 定版指纹（供后续批次做 PREV 用）

```
PREV_BUNDLE_MD5=41721861172d4655a9765e2a10423c63      # index-v2915-20261002.js（2,278,270 B）
PREV_SRV_MD5=9033c805be1022e692bc67f7ccc3b1ae         # srv/index_v28.ts（979,955 B / 65 环，与 0.9.14 同）
PREV_CHANGELOG_MD5=6d5557543190e366f34235640f42618e
PREV_CHANGELOG_PLAYER_MD5=77c7561d66df38f2e2a4ba184b9382b6
PREV_INDEX_HTML_MD5=6686e4912ad34a54054f507f8c4e29f7
```

## 8. 下一批留意

- `deploy_v2811.sh`：BUNDLE→v2915、OLD_BUNDLE→index-v2914-20261002.js、PREV_*×3 按 §7 重登记、备份命名 v2915
- `remote_check_v2811.sh`：包名两写法 + index.html 断言 + CHANGELOG [0.9.15] 断言 + 版本号段两处 + 0.9.14 清零滚动
- `EXPECT_0811.env` 全量重登记；`sim_remote_check.py` $B → v2915
- `check_srv_087.py` 两处失效未修（继承）；GitHub staging 未同步（继承）
- 客户端/装配面升版清单已在 §2 第一条全清，无需补
