# -*- coding: utf-8 -*-
r"""
yl_r169_ext.py — R-169 洞府灵草「配置信息缺失·折算回收」旧名归一（standalone 纯客户端）

需求原文（台账 R-169，逐字）
--------------------------------------------------------------------------
  「灵田怎么还有这种缺失问题，之前不是让完全修复吗：
    `12:54:16 ⚠️ 灵草【血参草】的配置信息缺失，已按 1,200 灵石折算回收（每个 300 灵石）。`」

==============================================================================
一、根因（复核前一个代理的取证，逐条实测确认）
==============================================================================
  · 服务端无关：`grep -c "配置信息缺失" srv/index_v28.ts` = 0；`grep -rn "折算回收" srv/` = 0。
  · 唯一出处 = 客户端 bundle 洞府灵草**收获**分支（函数 `j`，bundle @1953xxx）：
        const __halias={"灵紫猴草":"紫猴花"};                 // 0.8.10 需求 6b 注入（转义形态）
        const __hn=String(N.herbName==null?"":N.herbName);
        const __hnc=__halias[__hn]||__hn;
        const _=wn.find(Q=>Q.id===N.herbId)
               ||wn.find(Q=>Q.id===String(N.herbId==null?"":N.herbId).replace(/^herb-/,""))
               ||wn.find(Q=>Q.name===N.herbName)
               ||wn.find(Q=>Q.name===__hnc);                  // ← 别名兜底（唯一改动点）
        if(!_){ const __sv=Math.max(100,N.quantity*300); ... ⚠️ 灵草【${N.herbName}】的配置信息缺失 ... }
    `N` = `grotto.plantedHerbs[i]`；`wn` = 客户端**内嵌**灵草总表（20 味，见 §三）。
    四级查找全落空 ⇒ 按每株 300 灵石折算回收并弹这条警告。

  · ★ 为什么旧存档会种出「wn 里没有的名字」——**种植与收获不对称**：
      种植 `m`（@1951472）在 `wn` 查不到时，会调 `f(name,rarity)`（@1948652）**现场合成**一个
      灵草定义（`id=herb-<name>`），于是任意「草药类」背包物品都能种下，存进
      `plantedHerbs[].herbName`；而收获 `j` **没有** 这个 `f()` 合成兜底，只查 `wn`
      ⇒ 旧名/杂名一到收获就「配置缺失」。
      `f()`/`wn` 都读 `herbEffects=["止血","聚灵","回气","凝神","血参","紫猴","天灵","龙鳞",
      "凤羽","星辰","回春",…]` + `herbTypes=["草","花","果","参","芝",…]`
      + `herbRarityPrefixes={普通:[],稀有:["灵"],传说:["仙","千年","万年"],仙品:["神",…]}`
      —— 即一批「草名」是**随机词缀生成**的杂名（血参草=血参+草、灵止血草=灵+止血+草…）。

  · ⇒ 修法沿用 0.8.10 需求 6b 的先例：**延长 `__halias` 别名表**，把「旧名/杂名」归一到
    wn 里的**真实灵草**。一次 replace、零存档改写；命中后走正常收获路径，不再折算回收。

==============================================================================
二、★ 旧名扫描（localtest/_r025_all_players.json 全量递归扫，7 个玩家）
==============================================================================
  · 唯一非空 `grotto.herbarium`（@73710，14 条）：
        聚灵草·紫猴草·灵凤羽草·凤羽草·止血草·血参草·星辰草·凝神草·天灵草·龙鳞果·
        千年人参·雪莲花·灵止血草·灵回气草
    其中 **10 条不在 wn 20 味表**（= 会触发「配置缺失」的候选）：
        紫猴草 · 灵凤羽草 · 凤羽草 · 血参草 · 星辰草 · 凝神草 · 天灵草 · 雪莲花 ·
        灵止血草 · 灵回气草
  · 唯一非空 `grotto.plantedHerbs`（@113580）= `{herbName:"聚灵草"}`（合法，无旧名）。
  · 背包 `type=="草药"` 另有一批**随机生成杂名**（非洞府灵草，**不**入别名表，见 §四·待确认）：
        万年血参草 · 仙天灵草 · 神天灵草 · 灵星辰草 · 千年龙鳞草 · 业火红莲 · 紫府仙莲 · 仙灵果
    （后三者经核为现行物品：heavenEarthEssence / foundationTreasure / pet 进化材料，非旧名。）

==============================================================================
三、wn 20 味现行灵草全表（bundle @485901，`wn=[{id:"spirit-grass"…}]`）
==============================================================================
   1 spirit-grass                     聚灵草     11 dragon-scale-fruit               龙鳞果
   2 healing-herb                     止血草     12 millennium-ginseng               千年人参
   3 qi-restoring-herb                回气草     13 millennium-lingzhi               千年灵芝
   4 green-grass                      青草       14 nine-leaf-grass                  九叶芝草
   5 white-flower                     白花       15 ten-thousand-year-spirit-milk    万年灵乳
   6 yellow-essence                   黄精       16 ten-thousand-year-immortal-grass 万年仙草
   7 spirit-concentrating-flower      凝神花     17 nine-returning-soul-grass        九转还魂草
   8 blood-ginseng                    血参       18 void-immortal-grass              太虚仙草
   9 purple-monkey-flower             紫猴花     19 chaos-green-lotus                混沌青莲
  10 spirit-fruit                     天灵果     20 creation-immortal-grass           造化仙草

==============================================================================
四、映射表（本环写入 = 确定项；下方「待确认」**不写入**，仅登记待策划确认）
==============================================================================
  【确定 · 已写入 __halias】（旧名/杂名 → wn 真实灵草；词干唯一命中，仅差通用前后缀 灵/草/花）
    · 血参草   → 血参      （R-169 报告本体；血参 herbEffect 唯一命中 blood-ginseng）
    · 紫猴草   → 紫猴花    （紫猴 唯一命中 purple-monkey-flower；与既有 灵紫猴草→紫猴花 同族）
    · 凝神草   → 凝神花    （凝神 唯一命中 spirit-concentrating-flower）
    · 灵止血草 → 止血草    （灵 + 止血草；止血 唯一命中 healing-herb）
    · 灵回气草 → 回气草    （灵 + 回气草；回气 唯一命中 qi-restoring-herb）
    · （既有，保留）灵紫猴草 → 紫猴花

  【⚠ 待策划确认 · 本环**不**写入别名表】（拿不准不瞎猜：宁可少补，不可把道具换错）
    · 天灵草 → 天灵果 ?   —— wn 有 天灵果(spirit-fruit)，但 **天灵草 同时是现行商店灵草**
                             （bundle @1599727 `ys("天灵草",35)`，rarity 稀有，type Herb），
                             名字冲突，无法判定玩家那株是「旧名」还是「真·商店灵草」，故不自动归一。
    · 星辰草 → ?          —— wn 无「星辰」系灵草（星辰石 是炼器材料）；疑已删除的独立品种。
    · 凤羽草 → ?          —— wn 无「凤羽」系灵草（凤羽 是 materialBases/材料关键词）。
    · 灵凤羽草 → ?        —— 同上。
    · 雪莲花 → ?          —— 雪莲花 是现行抽奖物品（lottery-material-snow-lotus，@471009）；
                             wn 无「雪莲」系灵草。

==============================================================================
五、改法（1 处精确替换 · 只动 __halias 对象字面量，追加键值，不重写）
==============================================================================
  E1  在既有别名表末尾追加 5 个「确定」键值 + 幂等标记注释（对象字面量整体替换）：
        原： const __halias={"灵紫猴草":"紫猴花"};
        新： const __halias={"灵紫猴草":"紫猴花","血参草":"血参","紫猴草":"紫猴花",
                            "凝神草":"凝神花","灵止血草":"止血草","灵回气草":"回气草"};/*[r169herb]*/
      （JS 对象键序无关；追加后 `__halias[__hn]||__hn` 行为不变，仅命中集扩大。
        注释 `/*[r169herb]*/` 承载幂等标记，紧随 `};` 之后、`const __hn=` 之前，合法。）

  ★ 不碰：wn 20 味表本体 / 四级查找链结构 / 折算回收兜底（保留未知名的退路）/
    种植函数 m / f() 合成 / herbarium / 存档结构 / 数值结算 / 请求包装 / 版本号；
    不碰 build_v26n.py / chain_build.py / dryrun_087.py / CHANGELOG* / build/index.html /
    srv/index_v28.ts / 任何既有 yl_*_ext.py。注册（STANDALONE_CLIENT 追加 'r169'）与升版由主对话做。

==============================================================================
六、契约（照 localtest/yl_r167_ext.py）
==============================================================================
  · CLI：`--src <js>`（必填）/ `--check`（只验不写）/ `--selftest`（内存自证 + node --check）。
  · 二进制读、就地原子写回（tempfile.mkstemp + os.replace）；首次改写前落 <src>.bak-r169-<时刻>。
  · 幂等：产物已含标记 `[r169herb]` ⇒ 打印 SKIP 直接退出（不写盘，rc=3）。
  · 退出码：0=本次补丁成功；3=已是补丁后形态（未写盘）；2=前置断言/锚点不符；1=门禁/往返/自检失败。
  · `gates()` 五元组 (label, needle, expect, op, note)，op 支持 `==` / `>=`。
  · 中文一律 esc() 成 \uXXXX 字面量（与既有 __halias 的转义形态一致；ASCII 原样保留）。
  · 替换锚点 E_OLD 纯 ASCII 且恰好出现 1 次。
  · 不跑网络：只读 --src 指向的本地文件。

==============================================================================
七、锚点（对 build/assets/index-v2925-20261006.js 字符级实测）
==============================================================================
  E_OLD  count==1（65 字符）→ 打后 0
  E_NEW  count==0（295 字符）→ 打后 1（含 [r169herb]）
  冻结   : const __hn=…==1 · const __hnc=__halias[__hn]||__hn;==1 · ||wn.find(Q=>Q.name===__hnc);==1
           const __sv=Math.max(100,N.quantity*300);==1 · wn.find(Q=>Q.id===N.herbId)==1
           wn=[{id:"spirit-grass"==1 · E.splice(M,1);const __msg==1 · ⚠️ 灵草【==1 · 的配置信息缺失==1
  打后   : [r169herb]==1 · E_OLD==0 · E_NEW==1

==============================================================================
八、自测记录（本机实测 · 全程只动临时副本）
==============================================================================
  NODE = C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe
  [1] --check：门禁全绿 + round-trip identical=True
  [2] 首次补丁：rc=0，落 t.js.bak-r169-<ts>，chars 2134673 -> 2134903（delta +230）
  [3] 幂等重跑：rc=3 "already patched (idempotent skip)"（未写盘）
  [4] node --check 修补件：rc=0（语法合法）
  [5] 逐字符 diff：恰 1 处纯插入（+230 字符），逆向删除 == 原件
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime


def esc(w):
    r"""中文（非 ASCII）→ bundle 内的 \uXXXX 字面量形态；ASCII 原样保留。

    与既有 __halias 注入块的转义形态一致（bundle 里该块是字面 `\uXXXX`，非裸中文）。
    """
    return ''.join(c if ord(c) < 128 else '\\u%04x' % ord(c) for c in w)


# --------------------------------------------------------------------------- 映射表

# 既有键（0.8.10 需求 6b，必须保留）
BASE_OLD, BASE_NEW = '灵紫猴草', '紫猴花'

# 【确定】新增映射（旧名/杂名 → wn 真实灵草）；顺序无关
MAPPINGS = [
    ('血参草',   '血参'),    # R-169 报告本体
    ('紫猴草',   '紫猴花'),  # 紫猴 唯一命中 purple-monkey-flower
    ('凝神草',   '凝神花'),  # 凝神 唯一命中 spirit-concentrating-flower
    ('灵止血草', '止血草'),  # 灵 + 止血草
    ('灵回气草', '回气草'),  # 灵 + 回气草
]

# 待确认（仅登记，**不**写入别名表）——拿不准不瞎猜，见文件头 §四
PENDING = [
    ('天灵草',   '天灵果', '天灵草 同时是现行商店灵草 ys("天灵草",35)，名字冲突'),
    ('星辰草',   '',       'wn 无「星辰」系灵草；疑已删除的独立品种'),
    ('凤羽草',   '',       'wn 无「凤羽」系灵草（凤羽 是材料关键词）'),
    ('灵凤羽草', '',       'wn 无「凤羽」系灵草（凤羽 是材料关键词）'),
    ('雪莲花',   '',       '雪莲花 是现行抽奖物品 lottery-material-snow-lotus'),
]

# --------------------------------------------------------------------------- 锚点

OLD_OBJ = '{"%s":"%s"}' % (esc(BASE_OLD), esc(BASE_NEW))
NEW_OBJ = ('{"%s":"%s"' % (esc(BASE_OLD), esc(BASE_NEW))
           + ''.join(',"%s":"%s"' % (esc(o), esc(n)) for o, n in MAPPINGS)
           + '}')

E_OLD = 'const __halias=' + OLD_OBJ + ';'
E_NEW = 'const __halias=' + NEW_OBJ + ';/*[r169herb]*/'

IDEMPOTENT_MARK = '[r169herb]'

# ★ 0.9.27 变更（R-169 二环 `yl_r169b_ext.py`）：二环**删除**了「配置信息缺失·折算回收」整条分支
#   ⇒ 下列 4 条针脚在**最终产物**上必须**为 0**（一环当时按「不删退路」冻结为 1）。
#   `_precheck` 仍按**原件**校验（原件里它们确实还在，count==1），故拆成 POST_ZERO 单独处理。
#   ★ 规矩：按实际产物更新预期值、并记入 DEPLOY_LOG，**不得静默删断言**。见 DEPLOY_LOG_0.9.27.md §5。
POST_ZERO = [
    'const __sv=Math.max(100,N.quantity*300);',   # 折算回收兜底 —— 二环已删
    'E.splice(M,1);const __msg=',                 # 旧警告文案构造 —— 二环已删
    '\u26a0\ufe0f \u7075\u8349\u3010',            # ⚠️ 灵草【 —— 二环已删
    '\u7684\u914d\u7f6e\u4fe1\u606f\u7f3a\u5931',  # 的配置信息缺失 —— 二环已删
]

# 冻结针脚：本环只动 E1 一处，下列既有形态必须逐字在位（_precheck 对**原件**校验）
FREEZE = [
    ('const __hn=String(N.herbName==null?"":N.herbName);', 1),   # 空名安全化未动
    ('const __hnc=__halias[__hn]||__hn;', 1),                    # 别名归一未动
    ('||wn.find(Q=>Q.name===__hnc);', 1),                        # 第四级别名兜底未动
    ('const __sv=Math.max(100,N.quantity*300);', 1),             # 折算回收兜底仍在（不删退路）
    ('wn.find(Q=>Q.id===N.herbId)', 1),                          # 基线按 id 查找未动
    ('wn=[{id:"spirit-grass"', 1),                               # wn 20 味表本体未动
    ('E.splice(M,1);const __msg=', 1),                           # 警告文案构造未动
    ('\u26a0\ufe0f \u7075\u8349\u3010', 1),                       # ⚠️ 灵草【（源码裸中文形态）未动
    ('\u7684\u914d\u7f6e\u4fe1\u606f\u7f3a\u5931', 1),            # 的配置信息缺失（源码裸中文）未动
]


def gates():
    """返回 5 元组列表 (label, needle, expect, op, note)，对**补丁后**产物校验。"""
    g = [
        ('R169·别名表已扩容', E_NEW, 1, '==', '扩容后的 __halias 恰好 1 处'),
        ('R169·旧别名表已消失', E_OLD, 0, '==', '原单条 __halias 必须清零'),
        ('R169·幂等标记唯一', IDEMPOTENT_MARK, 1, '==', '[r169herb] 恰好 1 处'),
        ('R169·既有别名保留', '"%s":"%s"' % (esc(BASE_OLD), esc(BASE_NEW)), 1, '==',
         '灵紫猴草→紫猴花 未被改写'),
    ]
    for o, n in MAPPINGS:
        g.append(('R169·映射 %s→%s' % (o, n), ',"%s":"%s"' % (esc(o), esc(n)), 1, '==',
                  '确定项已写入'))
    for needle, cnt in FREEZE:
        # ★ POST_ZERO 里的 4 条：本环**不**在 gates() 里约束（本环 apply 时二环还没跑，此刻它们
        #   合法地 == 1；若在此断言 0 会在装配中途误报 ABORT）。它们的「最终必须为 0」断言
        #   **已移交** `yl_r169b_ext.py`（见其 gates(): 折算回收==0 / 配置信息缺失==0 /
        #   h.spiritStones+__sv==0 / R1_OLD==0 / 旧 const 查找==0）。非静默删除。
        if needle in POST_ZERO:
            continue
        g.append(('冻结 ' + needle[:24], needle, cnt, '==', '冻结既有形态'))
    return g


# --------------------------------------------------------------------------- 主流程

def _read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


def _write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(text.encode('utf-8'))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


REPS = [
    ('E1 扩容 __halias 别名表', E_OLD, E_NEW),
]


def _precheck(s):
    """返回 None=可打；否则返回错误串。对**原件** s 校验锚点与冻结针脚。"""
    if IDEMPOTENT_MARK in s or all(new in s for _, _, new in REPS):
        return None  # 幂等，交由 main 判 rc=3
    for name, old, new in REPS:
        if new in s:
            continue
        if s.count(old) != 1:
            return '%s 锚点出现 %d 次（期望 1）' % (name, s.count(old))
    for needle, cnt in FREEZE:
        if s.count(needle) != cnt:
            return '冻结针脚 %r 出现 %d 次（期望 %d）' % (needle, s.count(needle), cnt)
    return None


def apply_patch(src):
    """返回 (out, err)；err 非 None 时为错误串，out 为 None。"""
    s = _read(src)
    err = _precheck(s)
    if err is not None:
        return None, err
    out = s
    for name, old, new in REPS:
        if new in out:
            continue
        out = out.replace(old, new, 1)
    return out, None


def _run_gates(out):
    """返回 None=全绿；否则返回失败串。"""
    for label, needle, expect, op, note in gates():
        c = out.count(needle)
        if op == '==' and c != expect:
            return 'GATE FAIL %s: count=%d expect %d' % (label, c, expect)
        if op == '>=' and c < expect:
            return 'GATE FAIL %s: count=%d expect >=%d' % (label, c, expect)
    return None


def _roundtrip_ok(out, s0):
    rev = out
    for name, old, new in REPS:
        rev = rev.replace(new, old, 1)
    return rev == s0


def _find_node():
    cand = [os.environ.get('NODE'), shutil.which('node'),
            'C:/Users/27026/.workbuddy-ai/binaries/node/versions/22.22.2-3/node.exe']
    for c in cand:
        if c and os.path.exists(c):
            return c
    return None


def _node_check(js_text):
    """对 js_text 跑 node --check；返回 (rc, node_path) 或 (None, None) 当无 node。"""
    node = _find_node()
    if not node:
        return None, None
    fd, tmp = tempfile.mkstemp(suffix='.js')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(js_text.encode('utf-8'))
        r = subprocess.run([node, '--check', tmp], capture_output=True)
        return r.returncode, node
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def selftest(src):
    """内存自证：锚点 → 补丁 → 门禁 → 往返 → 幂等 → node --check（可选）。"""
    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r169] SELFTEST SKIP: src already patched')
        return 0
    out, err = apply_patch(src)
    if err is not None:
        print('[r169] SELFTEST FAIL precheck: ' + err)
        return 1
    e = _run_gates(out)
    if e is not None:
        print('[r169] SELFTEST FAIL ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r169] SELFTEST FAIL round-trip mismatch')
        return 1
    if not all(new in out for _, _, new in REPS):
        print('[r169] SELFTEST FAIL idempotency marker missing')
        return 1
    rc, node = _node_check(out)
    nmsg = 'node --check rc=%s (%s)' % (rc, node) if node else 'node not found (skipped)'
    if rc not in (None, 0):
        print('[r169] SELFTEST FAIL ' + nmsg)
        return 1
    print('[r169] SELFTEST OK: gates=%d roundtrip=True delta=%+d chars; %s'
          % (len(gates()), len(out) - len(s0), nmsg))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()

    src = args.src
    if not os.path.exists(src):
        print('[r169] src not found: %s' % src)
        return 2

    if args.selftest:
        return selftest(src)

    s0 = _read(src)
    if IDEMPOTENT_MARK in s0 or all(new in s0 for _, _, new in REPS):
        print('[r169] already patched (idempotent skip)')
        return 3

    out, err = apply_patch(src)
    if err is not None:
        print('[r169] ABORT: ' + err)
        return 2

    e = _run_gates(out)
    if e is not None:
        print('[r169] ' + e)
        return 1
    if not _roundtrip_ok(out, s0):
        print('[r169] round-trip mismatch：除改动点外字节被改动')
        return 1

    if args.check:
        print('[r169] check OK (%d -> %d chars, %+d)' % (len(s0), len(out), len(out) - len(s0)))
        for label, needle, expect, op, note in gates():
            print('    gate %-34s %s' % (label, 'OK'))
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak-r169-%s' % (src, ts)
    with open(bak, 'wb') as f:
        f.write(s0.encode('utf-8'))
    _write_atomic(src, out)
    print('[r169] patched: %d -> %d chars (%+d) (backup %s)'
          % (len(s0), len(out), len(out) - len(s0), os.path.basename(bak)))
    for label, needle, expect, op, note in gates():
        print('    gate %-34s %s' % (label, 'OK'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
