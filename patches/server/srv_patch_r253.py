# -*- coding: utf-8 -*-
r"""
srv_patch_r253.py -- R-251 服务端环（服务端第 96 环 / 新末环）

唯一真相源：策划_仙务称号加成重规划_20261011.md（§3.1 排行称号新表 / §3.2 活动称号新表 /
§4.1 服务端接口冻结 / §5 工单边界）。
本文件只按该规格实现，任何偏离必须先改那份规格文件。

背景（基座 = 95 环终态 srv/index_v28.ts，md5 0098cb4faa62c6e406963da84ce07120）
--------------------------------------------------------------------------
  · r249 已落地：RANK_TITLE_SOURCES / reconcileRankTitles / rankHoldersSnapshot /
    三句 `UPDATE titles SET attr_json`（rank_combat/rank_stones/rank_realm，均 15%）。
  · r251 已落地：rank_title_state 日期门 + 4 新榜/4 新称号 seed（INSERT OR IGNORE）+ 端点扩 7 键。
  · 缺口：7 排行称号**仍是单属性**（佩戴制下只有大小关系、没有取舍 ⇒ 沦为排行榜副产物）；
    7 活动称号加成同样单薄、辨识度低。
  ⇒ 本环：把 14 个称号的 attr_json 一次性重规划为「唯一招牌维度 + 复合辅项」。

机制（逐条）
--------------------------------------------------------------------------
  · 14 句 `UPDATE titles SET attr_json = ? WHERE source = ?`（幂等迁移）：
      - 7 排行称号（§3.1，source = rank_realm / rank_combat / rank_stones / rank_kills /
        rank_achieve / rank_playtime / rank_fame）；
      - 7 活动称号（§3.2，source = adventure_gold / week7 / mentor_grad / act087_jade /
        r054_month_sign / sworn / arena_week1）。
  · ★ 必须用 UPDATE —— 既有 seed 全部是 INSERT OR IGNORE（改不动已存在的行）；按 source 定位，
    与 seed 在文件中的散布位置无关。
  · 位置：紧邻 r249 的三句 `UPDATE titles SET attr_json` 之后（保持「加成集中于此、单点可调」的既有注释约定）。

★ 不改（规格 §4.1.3）：RANK_TITLE_SOURCES / reconcileRankTitles / 日期门 / LEADERBOARD_SORTS /
  rankHolders / `/api/leaderboard/me` / 表结构 / 任何 API / 任何既有 seed。

设计取向
--------------------------------------------------------------------------
  · 只新增 14 行 UPDATE，不触碰任何既有符号、表结构、seed、端点、定时器。
  · SQL 常量 SQL_UPD_ATTR 与注入 TS **逐字同源**：既用于 sqlite3 语义真跑（harness），
    也由门禁断言「必须出现在产物中」—— 保证「测的就是发出去的逻辑」。

CLI 契约（照 srv_patch_r251.py / r249.py / r233.py）
--------------------------------------------------------------------------
  `--src <path>`：就地原子写回该路径（写回前落 `<src>.bak-r253-<时间戳>`）。
  `--check` / `--selftest`：只校验不写回（含 Node 语法门禁 + sqlite3 语义真跑）。
  `--reverse <path>`：反向对照——在**未打 r253 的服务端**上跑同一套断言，必须确认标记缺席。
  退出码：0=成功 / 3=幂等（产物已含 [r253]）/ 2=锚点不符 / 1=门禁失败。

工程约束
--------------------------------------------------------------------------
  · ESM ⇒ 不写 `require(`；不新增 `res.status(403)` / `PRAGMA`。
  · 只改服务端；不改客户端 bundle；不改任何既有 srv_patch_*.py / chain_build.py / deploy_*/。
  · 每处替换 expect=1，命中数不符即中止（退出码 2）；产物 round-trip 自证 + Node 语法门禁
    + sqlite3 语义真跑后原子写回。
"""

import argparse
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# 本脚本位于 <repo>/patches/server/，服务端源码在 <repo>/srv/index_v28.ts ⇒ 上跳两级到仓库根再拼。
SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)), "srv", "index_v28.ts")

MARK = "[r253]"

# ============================================================ 与注入 TS 逐字同源的 SQL 常量
# ★ 该常量既用于 sqlite3 语义真跑（harness），也由门禁断言「必须出现在产物中」。
SQL_UPD_ATTR = "UPDATE titles SET attr_json = ? WHERE source = ?"

# ============================================================ 规格 §3 的 14 条 (source, attr_json, 注释)
# ★ 逐字照抄规格 §3.1 / §3.2 表；不许自创数值。EDITS / 门禁 / harness 全部由此单点生成。
R253_RANK = [
    ("rank_realm", '{"expRate":0.15,"luckRate":0.10}',
     "登峰造极 · 修炼宗师 ⇒ 修为 +15% / 气运 +10%"),
    ("rank_combat", '{"critRate":0.04,"critDamage":0.15,"atkRate":0.10}',
     "武林盟主 · 武力巅峰 ⇒ 暴击 +4% / 暴伤 +15% / 攻击 +10%"),
    ("rank_stones", '{"stoneRate":0.15,"luckRate":0.06}',
     "富甲一方 · 豪商 ⇒ 灵石 +15% / 气运 +6%"),
    ("rank_kills", '{"lifeLeech":0.04,"critDamage":0.10,"atkRate":0.10}',
     "万人敌 · 杀神 ⇒ 吸血 +4% / 暴伤 +10% / 攻击 +10%"),
    ("rank_achieve", '{"spiritRate":0.12,"expRate":0.08}',
     "功成名就 · 博学 ⇒ 神识 +12% / 修为 +8%"),
    ("rank_playtime", '{"defRate":0.12,"hpRate":0.12,"damageReduction":0.03}',
     "苦修不辍 · 苦修者 ⇒ 防御 +12% / 气血 +12% / 减伤 +3%"),
    ("rank_fame", '{"luckRate":0.12,"stoneRate":0.08}',
     "德高望重 · 人望 ⇒ 气运 +12% / 灵石 +8%"),
]
R253_ACT = [
    ("adventure_gold", '{"stoneRate":0.03,"luckRate":0.05}',
     "福缘深厚 ⇒ 灵石 +3% / 气运 +5%"),
    ("week7", '{"expRate":0.03,"hpRate":0.03}',
     "七日筑基 ⇒ 修为 +3% / 气血 +3%"),
    ("mentor_grad", '{"expRate":0.03,"spiritRate":0.05}',
     "良师益友 ⇒ 修为 +3% / 神识 +5%"),
    ("act087_jade", '{"stoneRate":0.02,"luckRate":0.03}',
     "灵玉仙客 ⇒ 灵石 +2% / 气运 +3%"),
    ("r054_month_sign", '{"expRate":0.02,"defRate":0.03}',
     "月满勤修 ⇒ 修为 +2% / 防御 +3%"),
    ("sworn", '{"charmRate":0.02,"luckRate":0.03}',
     "义结金兰 ⇒ 魅力 +2% / 气运 +3%"),
    ("arena_week1", '{"stoneRate":0.05,"atkRate":0.05}',
     "太虚魁首 ⇒ 灵石 +5% / 攻击 +5%"),
]
R253_ALL = R253_RANK + R253_ACT  # 14 条
R253_NEW = {src: attr for src, attr, _n in R253_ALL}


def _upd_line(source, attr, note):
    """生成一条注入 TS 的 UPDATE 行（★ 单引号包裹 TS 串 + 内层双引号 JSON，照 r249 写法）。"""
    return ("  db.run('UPDATE titles SET attr_json = ? WHERE source = ?', ['%s', '%s']);  // %s %s"
            % (attr, source, MARK, note))


# ============================================================ 改动点（expect=1）
# 锚点 = r249 三句 UPDATE 的**末句**（rank_realm）；新块紧贴其后（保持「加成集中于此」约定）。
_ANCHOR = ("  db.run('UPDATE titles SET attr_json = ? WHERE source = ?', "
           "['{\"expRate\":0.15}', 'rank_realm']);    // [r249] 登峰造极 · 境界第一 ⇒ 修为 +15%\n")
_BLOCK = (
    "  // %s 称号加成「重规划」（R-251）：14 条 UPDATE 幂等迁移 —— 7 排行称号（§3.1）+ 7 活动称号（§3.2）。\n"
    "  //   既有 seed 均为 INSERT OR IGNORE（改不动已存在行）⇒ 必须 UPDATE；按 source 定位，与 seed 散布位置无关。\n"
    "  //   常量集中于此，单点可调（沿用 [r249] 约定）。\n"
    % MARK
) + "".join(_upd_line(s, a, n) + "\n" for s, a, n in R253_ALL)

EDITS = [
    ("R253 14 条称号 attr_json UPDATE（7 排行 + 7 活动）", _ANCHOR, _ANCHOR + _BLOCK),
]

# ============================================================ 前置依赖（只读自证，不改；不符 ⇒ 退出码 2）
REQUIRES = [
    # 基座必须已是 95 环（r249 + r251 的产物）
    ("CREATE TABLE IF NOT EXISTS rank_title_state (", 1, "r251 的 rank_title_state 必须在位（证明基座=95 环）"),
    ("const RANK_TITLE_TICK_MS = 60 * 60 * 1000;", 1, "r251 的 TICK 必须在位（证明基座=95 环）"),
    ("const RANK_TITLE_SOURCES: Array<{ source: string; sort: string }> = [", 1, "RANK_TITLE_SOURCES 必须在位（本环不改）"),
    ("const LEADERBOARD_SORTS: Record<string, { orderBy: string; aheadCondition: string; getParams: (row: any) => any[] }> = {", 1, "LEADERBOARD_SORTS 必须在位（本环不改）"),
    ("async function reconcileRankTitles(): Promise<void> {", 1, "reconcileRankTitles 必须在位（本环不改）"),
    ("async function rankHoldersSnapshot(): Promise<Record<string, { name: string; title: string } | null>> {", 1, "rankHoldersSnapshot 必须在位（本环不改）"),
    ("function dbRun(sql: string, params: any[] = []): Promise<{ lastID: number; changes: number }> {", 1, "dbRun 必须在位"),
    # 7 排行称号既有 seed（r249 三句 + r251 四句，INSERT OR IGNORE 旧值）
    ("['{\"atkRate\":0.15}', 'rank_combat']", 1, "r249 rank_combat UPDATE 必须在位（本环在其后追加）"),
    ("['{\"stoneRate\":0.15}', 'rank_stones']", 1, "r249 rank_stones UPDATE 必须在位"),
    ("('万人敌', '{\"atkRate\":0.10}', 'rank_kills')", 1, "r251 万人敌 seed 必须在位"),
    ("('功成名就', '{\"expRate\":0.10}', 'rank_achieve')", 1, "r251 功成名就 seed 必须在位"),
    ("('苦修不辍', '{\"defRate\":0.10}', 'rank_playtime')", 1, "r251 苦修不辍 seed 必须在位"),
    ("('德高望重', '{\"stoneRate\":0.10}', 'rank_fame')", 1, "r251 德高望重 seed 必须在位"),
    # 7 活动称号既有 seed（★ 散布在不同位置；用 UPDATE 按 source 定位，与位置无关）
    ("('福缘深厚', '{\"stoneRate\":0.03}', 'adventure_gold')", 1, "活动称号 adventure_gold seed 必须在位"),
    ("('七日筑基', '{\"expRate\":0.02}', 'week7')", 1, "活动称号 week7 seed 必须在位"),
    ("('良师益友', '{\"expRate\":0.02}', 'mentor_grad')", 1, "活动称号 mentor_grad seed 必须在位"),
    ("('灵玉仙客', '{\"expRate\":0.01}', 'act087_jade')", 1, "活动称号 act087_jade seed 必须在位"),
    ("('月满勤修', '{\"expRate\":0.01}', 'r054_month_sign')", 1, "活动称号 r054_month_sign seed 必须在位"),
    ("'{\\\"charmRate\\\":0.01}', 'sworn'", 1, "活动称号 sworn seed（双引号 + \\\" 转义形态）必须在位"),
    ("'{\\\"stoneRate\\\":0.05}', 'arena_week1'", 1, "活动称号 arena_week1 seed（双引号 + \\\" 转义形态）必须在位"),
    # 锚点独占性
    (_ANCHOR, 1, "r249 末句 rank_realm UPDATE 锚点必须唯一"),
]

# ============================================================ 冻结基线（打前统计，打后必须不变）
BASE_NEEDLES = [
    "res.status(403", "require(", "PRAGMA",
    # 7 榜 orderBy（必须与 /api/leaderboard 逐字同源）——一字不动
    "orderBy: 'realm_index DESC, realm_level DESC, exp DESC, updated_at DESC, user_id ASC'",
    "orderBy: 'combat_power DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC'",
    "orderBy: 'spirit_stones DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC'",
    "orderBy: 'kill_count DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC'",
    "orderBy: 'achievement_count DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC'",
    "orderBy: 'play_time DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC'",
    "orderBy: 'reputation DESC, realm_index DESC, realm_level DESC, updated_at DESC, user_id ASC'",
    # 表结构
    "CREATE TABLE IF NOT EXISTS titles (",
    "CREATE TABLE IF NOT EXISTS player_titles (",
    "CREATE TABLE IF NOT EXISTS rankings (",
    "CREATE TABLE IF NOT EXISTS rank_title_state (",
    # 既有称号 seed（旧值，一字不动；新值由本环 UPDATE 覆盖）
    "('登峰造极', '{\"expRate\":0.05}', 'rank_realm')",
    "('武林盟主', '{\"atkRate\":0.03}', 'rank_combat')",
    "('富甲一方', '{\"stoneRate\":0.03}', 'rank_stones')",
    "('回归仙人', '{\"expRate\":0.02}', 'return')",
    "('初入江湖', '{\"expRate\":0.01}', 'achievement')",
    "('万人敌', '{\"atkRate\":0.10}', 'rank_kills')",
    "('功成名就', '{\"expRate\":0.10}', 'rank_achieve')",
    "('苦修不辍', '{\"defRate\":0.10}', 'rank_playtime')",
    "('德高望重', '{\"stoneRate\":0.10}', 'rank_fame')",
    "('福缘深厚', '{\"stoneRate\":0.03}', 'adventure_gold')",
    "('七日筑基', '{\"expRate\":0.02}', 'week7')",
    "('良师益友', '{\"expRate\":0.02}', 'mentor_grad')",
    "('灵玉仙客', '{\"expRate\":0.01}', 'act087_jade')",
    "('月满勤修', '{\"expRate\":0.01}', 'r054_month_sign')",
    # r249 三句 UPDATE（旧值，一字不动；本环在其后追加）
    "['{\"atkRate\":0.15}', 'rank_combat']",
    "['{\"stoneRate\":0.15}', 'rank_stones']",
    "['{\"expRate\":0.15}', 'rank_realm']",
    # r251 新增物
    "INSERT OR IGNORE INTO rank_title_state (id, last_date) VALUES (1, '')",
    "const RANK_TITLE_TICK_MS = 60 * 60 * 1000;",
    "{ combat: null, stones: null, realm: null, kills: null, achieve: null, playtime: null, fame: null }",
    "{ sort: 'kills', config: LEADERBOARD_SORTS.kills },",
    "{ sort: 'fame', config: LEADERBOARD_SORTS.fame },",
    # 既有符号
    "async function grantTitleBySource(userId: number, source: string): Promise<boolean> {",
    "function shouldGrantRankTitle(topUserId: number, boardSize: number, userId: number, minBoardSize: number = 2): boolean {",
    "const RANK_TITLE_SOURCES: Array<{ source: string; sort: string }> = [",
    "async function maybeGrantAutoTitles(userId: number, achCount: number): Promise<void> {",
    "await reconcileRankTitles(); // [r249]",
    "app.get('/api/leaderboard'",
    "app.get('/api/leaderboard/me'",
    "app.get('/api/quest/summary'",
    # 红线：既有 seed 通道不许被本环改动
    "INSERT OR IGNORE INTO titles",
]


def fail(msg, code=1):
    print("[FAIL] " + msg)
    sys.exit(code)


# ============================================================ Node 语法门禁
def node_bin():
    root = r"C:/Users/<USER>/.workbuddy-ai/binaries/node/versions"
    cands = []
    if os.path.isdir(root):
        cands = sorted(os.path.join(root, d, "node.exe") for d in os.listdir(root))
        cands = [c for c in cands if os.path.isfile(c)]
    return os.environ.get("YL_NODE") or (cands[-1] if cands else "node")


def node_syntax_check(text):
    """产物必须过 node --experimental-strip-types --check。"""
    d = tempfile.mkdtemp(prefix="r253chk-")
    try:
        p = os.path.join(d, "c.ts")
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        r = subprocess.run([node_bin(), "--experimental-strip-types", "--check", p],
                           capture_output=True, text=True, encoding="utf-8")
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ============================================================ sqlite3 语义真跑
# 用内存库 + 合成 titles 行，跑与注入 TS **逐字同源**的 UPDATE 语句（SQL_UPD_ATTR）。
def semantic_harness():
    results = []

    def ck(name, fn):
        try:
            ok = bool(fn())
            results.append((name, ok, ""))
        except Exception as e:
            results.append((name, False, "throw:" + repr(e)))

    # 打前「旧值」（= 基座里 r249/r251 seed 与既有活动 seed 的现状）
    OLD = {
        "rank_realm": '{"expRate":0.15}', "rank_combat": '{"atkRate":0.15}', "rank_stones": '{"stoneRate":0.15}',
        "rank_kills": '{"atkRate":0.10}', "rank_achieve": '{"expRate":0.10}',
        "rank_playtime": '{"defRate":0.10}', "rank_fame": '{"stoneRate":0.10}',
        "adventure_gold": '{"stoneRate":0.03}', "week7": '{"expRate":0.02}', "mentor_grad": '{"expRate":0.02}',
        "act087_jade": '{"expRate":0.01}', "r054_month_sign": '{"expRate":0.01}',
        "sworn": '{"charmRate":0.01}', "arena_week1": '{"stoneRate":0.05}',
    }

    def fresh():
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE titles (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, "
                    "attr_json TEXT, source TEXT UNIQUE)")
        return con

    def seed_old(con, ignore=True):
        verb = "INSERT OR IGNORE" if ignore else "INSERT"
        for src, _a, _n in R253_ALL:
            con.execute(verb + " INTO titles (name, attr_json, source) VALUES (?, ?, ?)",
                        [src, OLD[src], src])
        con.commit()

    def run_updates(con):
        """镜像注入 TS 的 14 句 UPDATE（逐字同源 SQL_UPD_ATTR）。"""
        n = 0
        for src, attr, _note in R253_ALL:
            cur = con.execute(SQL_UPD_ATTR, [attr, src])
            n += cur.rowcount
        con.commit()
        return n

    def get(con, src):
        r = con.execute("SELECT attr_json FROM titles WHERE source = ?", [src]).fetchone()
        return r[0] if r else None

    def all_match_new(con):
        return all(get(con, src) == attr for src, attr, _n in R253_ALL)

    # ① 14 行旧值 ⇒ 跑 14 句 UPDATE ⇒ 14 行 attr_json 全部 == §3 新值
    def s1():
        con = fresh()
        seed_old(con)
        before_all_old = all(get(con, src) == OLD[src] for src, _a, _n in R253_ALL)
        changed = run_updates(con)
        return before_all_old and all_match_new(con) and changed == 14

    # ② 再跑一次（幂等）⇒ 值不变
    def s2():
        con = fresh()
        seed_old(con)
        run_updates(con)
        snapshot1 = {src: get(con, src) for src, _a, _n in R253_ALL}
        run_updates(con)
        snapshot2 = {src: get(con, src) for src, _a, _n in R253_ALL}
        return all_match_new(con) and snapshot1 == snapshot2

    # ③ 「INSERT OR IGNORE 先建旧值行」⇒ 再 INSERT OR IGNORE 新值被挡住 ⇒ UPDATE 仍能覆盖
    def s3():
        con = fresh()
        seed_old(con)  # 先建旧值行（模拟既有 seed）
        # 用 INSERT OR IGNORE 尝试灌新值 ⇒ 必须被挡住（旧值仍在）—— 证明「改不动已存在行」
        for src, attr, _n in R253_ALL:
            con.execute("INSERT OR IGNORE INTO titles (name, attr_json, source) VALUES (?, ?, ?)",
                        [src, attr, src])
        con.commit()
        still_old = all(get(con, src) == OLD[src] for src, _a, _n in R253_ALL)
        # 再跑 UPDATE ⇒ 覆盖为 §3 新值
        run_updates(con)
        return still_old and all_match_new(con)

    # ④ UPDATE 一个不存在的 source ⇒ 0 行受影响且不抛异常（安全）
    def s4():
        con = fresh()
        seed_old(con)
        cur = con.execute(SQL_UPD_ATTR, ['{"x":1}', "__no_such_source__"])
        con.commit()
        return cur.rowcount == 0 and all_match_new(con) is False  # 未跑 ⇒ 仍是旧值

    # ⑤ 14 条 source 互不重复 + attr_json 均为合法 JSON 且非空
    def s5():
        srcs = [s for s, _a, _n in R253_ALL]
        if len(set(srcs)) != 14 or len(srcs) != 14:
            return False
        for _s, attr, _n in R253_ALL:
            obj = json.loads(attr)
            if not isinstance(obj, dict) or not obj:
                return False
        # 招牌维度唯一性自检（规格 §3.1）：7 排行称号的「首个键」互不重复
        first_keys = [next(iter(json.loads(a))) for _s, a, _n in R253_RANK]
        return len(set(first_keys)) == 7

    ck("① 14 旧值 ⇒ 14 UPDATE ⇒ 全部 == §3 新值", s1)
    ck("② 再跑一次（幂等）⇒ 值不变", s2)
    ck("③ INSERT OR IGNORE 先建旧值行 ⇒ UPDATE 能覆盖", s3)
    ck("④ UPDATE 不存在 source ⇒ 0 行且不抛", s4)
    ck("⑤ 14 source 唯一 / attr 合法 JSON / 7 招牌唯一", s5)

    total = len(results)
    nfail = sum(1 for _, ok, _ in results if not ok)
    for name, ok, extra in results:
        print(("  [OK] " if ok else "  [FAIL] ") + name + (("  <" + extra + ">") if extra else ""))
    print("HARNESS_RESULT " + json.dumps({"total": total, "fail": nfail}))
    return total, nfail


def main() -> None:
    ap = argparse.ArgumentParser(description="R-251 服务端环（服务端第 96 环）")
    ap.add_argument("--src", default=SRC, help="待打补丁的服务端源码（装配器会传私有副本）")
    ap.add_argument("--check", action="store_true", help="只校验不写回")
    ap.add_argument("--selftest", action="store_true", help="只校验不写回（含 Node 语法 + sqlite3 语义真跑）")
    ap.add_argument("--reverse", default=None, metavar="PATH",
                    help="反向对照：在未打 r253 的服务端上跑同一套断言，必须确认标记缺席（只校验不写回）")
    a = ap.parse_args()

    # ---- 反向对照模式 ----
    if a.reverse:
        path = a.reverse
        if not os.path.exists(path):
            fail("reverse source not found: " + path)
        with io.open(path, "r", encoding="utf-8", newline="") as f:
            rev = f.read()
        print("== 反向对照（未打 r253 的服务端）：%s ==" % path)
        has_attr = rev.count('{"luckRate":0.12,"stoneRate":0.08}')
        has_mark = rev.count(MARK)
        print("  R253 新 attr 串计数 = %d（期望 0，证明未打）" % has_attr)
        print("  [r253] 计数 = %d（期望 0）" % has_mark)
        if has_attr == 0 and has_mark == 0:
            print("  [REVERSE] PASS（基线确实未打 r253，标记缺席）")
        else:
            print("  [REVERSE] FAIL（★ 该源已含 r253 痕迹，不构成基线）")
        return

    src_path = a.src
    if not os.path.exists(src_path):
        fail("source not found: " + src_path)
    with io.open(src_path, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    # 1) 幂等（幂等 ⇒ 退出码 3，由调用方区分「已打」与「失败」）
    if MARK in src:
        print("[SKIP] source looks already patched（已含 %s）" % MARK)
        sys.exit(3)

    # 2) 依赖（不符 ⇒ 退出码 2）
    for needle, cnt, why in REQUIRES:
        n = src.count(needle)
        if n != cnt:
            fail("依赖未满足（%r 出现 %d 次，期望 %d）：%s" % (needle[:90], n, cnt, why), 2)

    # 3) 锚点计数（不符 ⇒ 退出码 2）
    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("%s 锚点出现 %d 次（期望 1）：%r" % (name, n, old[:160]), 2)
        if old == new:
            fail("%s old == new" % name, 2)

    # 4) 冻结基线
    base = {k: src.count(k) for k in BASE_NEEDLES}
    base_interval = src.count("setInterval(")
    base_sql_upd = src.count(SQL_UPD_ATTR)          # 既有 3 句；打后 = 3 + 14 = 17
    base_ins_titles = src.count("INSERT OR IGNORE INTO titles")

    # 5) 应用
    out = src
    for name, old, new in EDITS:
        out = out.replace(old, new, 1)

    # 6) 门禁
    mark_n = sum(new.count(MARK) for _, _, new in EDITS)
    gates = [
        ("R253 幂等标记就位", MARK, mark_n),
        # 14 条 UPDATE 逐条（★ 单点由 R253_ALL 生成，测的就是发出去的串）
        ("R253 UPDATE 语句总数（3 旧 + 14 新）", SQL_UPD_ATTR, base_sql_upd + 14),
    ]
    for _s, _a, _n in R253_ALL:
        gates.append(("R253 UPDATE " + _s, _upd_line(_s, _a, _n), 1))
        gates.append(("R253 param %s" % _s, "['%s', '%s']" % (_a, _s), 1))
    # 冻结：既有符号/表结构/orderBy/seed 一字不动
    for needle in BASE_NEEDLES:
        gates.append(("冻结 " + needle[:44].replace("\n", " "), needle, base[needle]))
    # setInterval 不变（本环不加定时器）
    gates.append(("红线 setInterval 不变", "setInterval(", base_interval))
    # 红线：不新增 res.status(403) / PRAGMA / require( / INSERT OR IGNORE INTO titles
    gates.append(("红线 未新增 res.status(403)", "res.status(403", base["res.status(403"]))
    gates.append(("红线 未新增 PRAGMA", "PRAGMA", base["PRAGMA"]))
    gates.append(("红线 未新增 require(", "require(", base["require("]))
    gates.append(("红线 未新增 INSERT OR IGNORE INTO titles", "INSERT OR IGNORE INTO titles", base_ins_titles))

    ok = True
    for label, needle, exp in gates:
        act = out.count(needle)
        good = (act == exp)
        ok = ok and good
        if not good:
            print("  [FAIL] %-56s actual=%d expect==%d" % (label, act, exp))
    print("  [%s] 门禁 %d 条" % ("OK" if ok else "FAIL", len(gates)))

    # 7) round-trip 自证
    back = out
    for name, old, new in EDITS:
        if back.count(new) != 1:
            fail("%s 的 new 在产物中出现 %d 次（期望 1）" % (name, back.count(new)))
        back = back.replace(new, old, 1)
    if back != src:
        fail("round-trip mismatch")

    # 8) node --check 语法门禁
    syn_ok, syn_msg = node_syntax_check(out)
    if not syn_ok:
        sys.stdout.write(syn_msg)
    print("  [%s] node --experimental-strip-types --check" % ("OK" if syn_ok else "FAIL"))
    ok = ok and syn_ok

    # 9) sqlite3 语义真跑
    total, nfail = semantic_harness()
    sem_ok = (nfail == 0)
    print("  [%s] sqlite3 语义真跑  (total=%d fail=%d)" % ("OK" if sem_ok else "FAIL", total, nfail))
    ok = ok and sem_ok

    print("  delta = %+d chars  (%d -> %d)" % (len(out) - len(src), len(src), len(out)))

    if not ok:
        fail("门禁未全绿，未写回", 1)

    if a.check or a.selftest:
        print("  --check/--selftest：未写回 %s" % src_path)
        return

    # 10) 改前 .bak + 原子写回
    bak = "%s.bak-r253-%s" % (src_path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copyfile(src_path, bak)
    print("  已备份 %s" % bak)
    d = os.path.dirname(os.path.abspath(src_path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".r253-", suffix=".tmp")
    try:
        with io.open(fd, "w", encoding="utf-8", newline="") as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print("  已原子写回 %s" % src_path)


if __name__ == "__main__":
    main()
