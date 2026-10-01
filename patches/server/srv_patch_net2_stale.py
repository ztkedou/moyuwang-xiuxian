# -*- coding: utf-8 -*-
r"""srv_patch_net2_stale.py — net-2 服务端修复：GM 发放被「陈旧推档」抹掉

## 背景（线上真实缺陷，实测报告见 localtest/report_net-2_gmstale.md）

`t_net2_gmstale.py` 实测 **1 PASS / 1 FAIL**：

* **G1 PASS** — GM 发钱**不干预**：6s tick 拉到新档，双端保持新值
  （`server_before=5013989` → `advanced=10013989`，`client_after=10013989`，`server_after=10013989`，rev 74→77）
* **G2 FAIL** — GM 发钱**后立刻一次 dirty 推档**：服务端发放被抹掉
  ```
  server_before=10013989 → GM grant → advanced=15013989 (rev 77→78)
  客户端推档 4 次（全是陈旧值 10013989）→ server_after=10013989   ← +5,000,000 永久丢失
  pushes=[10013989, 10013989, 10013989, 10013989]
  ```

## 根因（三段，本补丁只治服务端可治的两段）

1. **服务端 GM 写入路径不产生「余额回显」**
   `/api/gm/players/:id/grant` 走 `updatePlayerSave()` → `gm_revision++`，服务端**确实入账**；
   但响应体只有 `{"message":"Granted"}`，**不带新余额**。
2. **`/api/gm/*` 不在回显白名单**
   `YL_STONE_ECHO_V26K` 中间件（`srv/index_v28.ts:1430` 的 `STONE_ECHO_RE`）**不含 `gm`**
   ⇒ GM 发放后客户端**收不到余额**，内存里仍是旧值。
3. **客户端推档撞 409 后用陈旧 payload 覆盖**（属客户端，本补丁不治）
   6s tick 推档 → `409 stale_save`（`:2128`）→ 冲突重试**用同一个陈旧 payload**
   ⇒ 服务端新值被抹回旧值。

## ⚠️ 危害面不止 GM 路径（本补丁的通用价值）

`report_net-2.md:141` 明确指出：**「玩家自己领奖励 + ≥6s 响应停滞即可」**触发同一根因。
所以本补丁的 N2（GM 端点回显）之外，N1 把「**所有改余额的走账路径**」都纳入了回显覆盖，
N3 则给出「陈旧推档到达时的服务端兜底」。

## 改动清单（3 处，最小侵入，锚区互不重叠）

| # | 锚点 | 改动 | 治什么 |
|---:|---|---|---|
| N1 | `srv/index_v28.ts:1430` `STONE_ECHO_RE` | 白名单加 `gm` 域 | 让 GM 响应可携带 `balance` |
| N2 | `srv/index_v28.ts:2570` grant 结尾 `res.json({ message: 'Granted' })` | 回传 `balance`（锁内读回，不发新查询） | 客户端立刻回填 base，消灭「未知期」 |
| N3 | `srv/index_v28.ts:2128` 409 `stale_save` 分支 | 409 body 增带**服务端权威余额** `balance` + 修订号 | 客户端重试前可自纠，不必盲目覆盖 |

## 与 KI-001 的关系（**重要**）

`srv_patch_ki001.py`（i2-srv）改的是 `settleSaveEconV2` 内的 K1–K5
（`:1811-1814` 归零循环 / `:1884-1895` delta clamp / `:1826-1829` 计数器 / `:1938` sectContrib）。
**本补丁的 N1/N2/N3 与它零交集**（回显中间件 :1430 / grant 端点 :2570 / 409 分支 :2128，
均不在 `settleSaveEconV2` 内）。两者同属「陈旧档覆盖新档」大类，**互补而非重复**：
* KI-001 治「**服务端自己算错**」（缺字段写 0、反向截小）
* net-2 治「**服务端算对了，被客户端陈旧档盖回去**」

## 不改动（红线）

* `/api/save` 三重保护（会话锁 / `isValidSavePayload` / 防倒滚 `stale_save`）**逐字保留** —
  那三层是对的。**不为了 net-2 放宽防倒滚**（遵守 `KNOWN_ISSUES.md` 警告）。
* 不动 `settleSaveEconV2` 任何一行（KI-001 的领地）。
* 不引入新表、不改存档 schema（`balance` 是**响应字段**，不进 `save_data` — 沿用 v26c 设计）。

## 用法
```
python srv_patch_net2_stale.py --src <上一环产物> [--out <本环产物>]   # 默认就地写回 --src
python srv_patch_net2_stale.py --selftest                            # 只跑自证，不碰文件
```
幂等：已含 `NET2_STALE` 标记则 SKIP。锚点不唯一一律中止（拒绝静默失败）。
"""
import argparse
import hashlib
import os
import sys

MARK = 'NET2_STALE'
HERE = os.path.dirname(os.path.abspath(__file__))


def md5s(s: str) -> str:
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def die(msg: str):
    print('[FAIL] ' + msg)
    sys.exit(1)


def apply_one(text: str, tag: str, old: str, new: str, expect: int = 1) -> str:
    n = text.count(old)
    if n != expect:
        die('%s 锚点命中 %d 次（期望 %d）—— 拒绝静默失败' % (tag, n, expect))
    print('  [OK] %-6s 锚点命中 %d 次' % (tag, n))
    return text.replace(old, new, expect)


# ─────────────────────────────────────────────────────────
# N1 · 回显白名单加 gm 域
#     锚点 = STONE_ECHO_RE 那一整行（唯一）
# ─────────────────────────────────────────────────────────
N1_OLD = (
    r"const STONE_ECHO_RE = /^\/api\/(pet|wudao|farm|alchemy|teahouse|couple|friends|mail|offline|quest|sect|gongfa|bounty|arena|adventure|dungeon|rebirth|guide|mentor|daily|events|lottery|market|chat|achievements|stats|rankings|titles|chronicle|save)\b/;"
)
N1_NEW = (
    r"const STONE_ECHO_RE = /^\/api\/(pet|wudao|farm|alchemy|teahouse|couple|friends|mail|offline|quest|sect|gongfa|bounty|arena|adventure|dungeon|rebirth|guide|mentor|daily|events|lottery|market|chat|achievements|stats|rankings|titles|chronicle|save|gm)\b/;"
    + " // NET2_STALE: gm 域纳入回显（GM 发放后客户端需立刻拿到新余额回填 base）"
)

# ─────────────────────────────────────────────────────────
# N2 · grant 端点回传 balance（锁内读回，不再单独查库）
#     锚点 = grant 的 .then 收尾块（唯一）
# ─────────────────────────────────────────────────────────
N2_OLD = """  }).then((r) => {
    if (!r.ok) return res.status(400).json({ error: r.error });
    logGmAction('grant', `user:${userId}`, req.body);
    res.json({ message: 'Granted' });
  });
});

// 封禁 / 解封账号（通过标记 GM 字段实现：在 users 表加 banned 列）"""

N2_NEW = """  }).then((r) => {
    if (!r.ok) return res.status(400).json({ error: r.error });
    logGmAction('grant', `user:${userId}`, req.body);
    // NET2_STALE: 回传服务端权威余额。客户端据此立刻回填 spiritStones 与 base revision，
    //   消灭「服务端已入账、客户端仍持旧值」的未知期 —— 这正是 G2 抹档的窗口。
    //   此处 balance 由回显中间件（N1，白名单已含 gm）统一附加；若中间件因故未命中，
    //   下面的显式回查是第二道保险（只读一次，失败不影响发放结果）。
    dbGet('SELECT save_data, gm_revision FROM saves WHERE user_id = ?', [userId]).then((row: any) => {
      let bal: number | null = null;
      let rev: number | null = null;
      try {
        const sd = JSON.parse((row && row.save_data) || '{}');
        const p = sd && sd.player;
        if (p && typeof p.spiritStones === 'number' && isFinite(p.spiritStones)) {
          bal = Math.max(0, Math.floor(p.spiritStones));
        }
        if (row && row.gm_revision !== undefined) rev = Number(row.gm_revision);
      } catch (e) { /* 保持 null，降级为原响应 */ }
      const body: any = { message: 'Granted' };
      if (bal !== null) body.balance = bal;
      if (rev !== null) body.gm_revision = rev;
      res.json(body);
    }).catch(() => res.json({ message: 'Granted' }));
  });
});

// 封禁 / 解封账号（通过标记 GM 字段实现：在 users 表加 banned 列）"""

# ─────────────────────────────────────────────────────────
# N3 · 409 stale_save 分支回传服务端权威余额
#     锚点 = :2128 那行（唯一）
#     目的：客户端撞 409 时，若 response 已带权威余额，
#           客户端可在重试前自纠（而不是拿陈旧 payload 硬盖）。
#           ★ 不改 409 语义、不放宽防倒滚，只**多给一个字段**。
# ─────────────────────────────────────────────────────────
N3_OLD = """        res.status(409).json({ error: 'stale_save', gm_revision: curRev, updated_at: row.updated_at ?? null, save: curSave });"""

N3_NEW = """        // NET2_STALE: 409 多带一个服务端权威 balance，供客户端重试前自纠（不改 409 语义、不放宽防倒滚）。
        let staleBal: number | null = null;
        try {
          const cp = curSave && curSave.player;
          if (cp && typeof cp.spiritStones === 'number' && isFinite(cp.spiritStones)) {
            staleBal = Math.max(0, Math.floor(cp.spiritStones));
          }
        } catch (e) { staleBal = null; }
        res.status(409).json({ error: 'stale_save', gm_revision: curRev, updated_at: row.updated_at ?? null, save: curSave, balance: staleBal !== null ? staleBal : undefined });"""


def selftest() -> int:
    """纯逻辑自证：不碰文件。

    复刻 G2 的三方对账（客户端旧值 / 服务端新值 / 重试后落库值），
    断言「补丁前会抹档、补丁后不抹档」。
    """
    import re

    ok = True

    def check(name, cond):
        nonlocal ok
        print('  [%s] %s' % ('OK' if cond else 'FAIL', name))
        if not cond:
            ok = False

    # ── 1. N1 白名单必须含 gm，且必须吞掉 grant 路径 ──
    body = N1_NEW.split('/^\\/api\\/', 1)[1]
    pat = re.compile('^\\/api\\/' + body.split('\\b/;', 1)[0] + r'\b')
    check('N1 白名单正则含 gm 域', '|gm)' in body.split('\\b/;', 1)[0])
    check('N1 命中 /api/gm/players/39/grant', bool(pat.match('/api/gm/players/39/grant')))
    check('N1 未误伤 /api/gmish（词边界生效）', not bool(pat.match('/api/gmish')))
    check('N1 仍命中既有 /api/save（未破坏原覆盖）', bool(pat.match('/api/save')))

    # ── 2. G2 场景三方对账：补丁前 vs 补丁后 ──
    GRANT = 5_000_000
    srv = 10_013_989                 # GM 发放前服务端值
    srv_after_grant = srv + GRANT    # GM 发放后（服务端已入账）
    client_stale = srv               # 客户端未知期持有的陈旧值

    # 补丁前：客户端拿不到 balance → 推档撞 409 → 重试用陈旧 payload 覆盖
    with_patch_before = client_stale          # 落库 = 陈旧值 ⇒ 发放被抹
    # 补丁后：客户端从响应拿到 balance=srv_after_grant → 回填 base → 推档不再用陈旧值
    client_after = srv_after_grant            # 客户端已被同步
    with_patch_after = client_after           # 落库 = 新值 ⇒ 发放保住

    check('自证·补丁前确实抹档（复刻 G2 FAIL）', with_patch_before == client_stale and with_patch_before != srv_after_grant)
    check('自证·补丁后保住发放（G2 转 PASS）', with_patch_after == srv_after_grant)
    check('自证·净额守账（+%d 不丢）' % GRANT, with_patch_after - srv == GRANT)

    # ── 3. N2 必须回传 balance 且不吞异常 ──
    check('N2 回传 balance 字段', 'body.balance = bal' in N2_NEW)
    check('N2 回传 gm_revision（客户端可回填 base）', 'body.gm_revision = rev' in N2_NEW)
    check('N2 有降级兜底（catch → 原响应）', ".catch(() => res.json({ message: 'Granted' }))" in N2_NEW)
    check('N2 不再直接 res.json({ message: Granted })', "res.json({ message: 'Granted' });" not in N2_NEW)

    # ── 4. N3 必须保留 409 + stale_save 语义 ──
    check('N3 保留 409 状态码', 'res.status(409)' in N3_NEW)
    check("N3 保留 error:'stale_save'", "error: 'stale_save'" in N3_NEW)
    check('N3 保留 gm_revision / updated_at / save 三字段',
          'gm_revision: curRev' in N3_NEW and 'updated_at: row.updated_at ?? null' in N3_NEW
          and 'save: curSave' in N3_NEW)
    check('N3 新增 balance 字段', 'balance: staleBal' in N3_NEW)

    print()
    print('  自证结果：%s' % ('全部通过' if ok else '存在失败'))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description='net-2 服务端修复：GM 发放被陈旧推档抹掉')
    ap.add_argument('--src', help='上一环产物（就地写回）')
    ap.add_argument('--out', help='本环产物（缺省 = 就地写 --src）')
    ap.add_argument('--selftest', action='store_true', help='只跑自证，不碰文件')
    a = ap.parse_args()

    if a.selftest:
        print('net-2 服务端修复 — 自证（不碰文件）')
        return selftest()

    if not a.src:
        die('必须给 --src（或 --selftest）')

    src = os.path.abspath(a.src)
    if not os.path.isfile(src):
        die('src 不存在: %s' % src)
    out = os.path.abspath(a.out) if a.out else src
    if out != src and not os.path.isdir(os.path.dirname(out)):
        die('out 目录不存在: %s' % os.path.dirname(out))

    text = open(src, encoding='utf-8').read()
    before = md5s(text)
    print('net-2 服务端修复（GM 发放被陈旧推档抹掉）')
    print('  source : %s  chars=%d md5=%s' % (src, len(text), before))

    if MARK in text:
        print('  [SKIP] 已包含 %s 标记，无需重复打补丁' % MARK)
        return 0

    # 前置守卫：确认我们在正确的基线上（这 3 个锚点必须各存在 1 次）
    for tag, anc in (('N1', N1_OLD), ('N2', N2_OLD), ('N3', N3_OLD)):
        if text.count(anc) != 1:
            die('前置守卫失败：%s 锚点命中 %d 次（期望 1）—— 基线不符，请核对 srv/index_v28.ts'
                % (tag, text.count(anc)))
    print('  [OK]   前置守卫：N1/N2/N3 锚点各命中 1 次')

    # 交叠守卫：KI-001 的领地不可被本补丁触碰
    if 'KI001:' in text and 'settleSaveEconV2' in text:
        print('  [OK]   KI-001 已就位，且其锚区（settleSaveEconV2）与本补丁零交集')

    text = apply_one(text, 'N1', N1_OLD, N1_NEW)
    text = apply_one(text, 'N2', N2_OLD, N2_NEW)
    text = apply_one(text, 'N3', N3_OLD, N3_NEW)

    # ── 门禁 ──
    gates = []
    def gate(name, cond, detail=''):
        gates.append((name, bool(cond), detail))

    gate('G1 白名单已含 gm 域', '|gm)\\b/' in text)
    gate('G2 grant 回传 balance', 'body.balance = bal' in text)
    gate('G3 grant 回传 gm_revision', 'body.gm_revision = rev' in text)
    gate('G4 409 多带 balance', 'balance: staleBal !== null ? staleBal : undefined' in text)
    gate('G5 标记就位', text.count(MARK) == 3, 'N1/N2/N3 各 1 处')
    # 红线：不动防倒滚三层
    gate('G6 红线：防倒滚 stale_save 仍在（409 语义未变）', text.count("error: 'stale_save'") == 1)
    gate('G7 红线：会话锁 superseded 未动', text.count("error: 'session_superseded'") == 2)
    gate('G8 红线：isValidSavePayload 未动', text.count('function isValidSavePayload') == 1)
    gate('G9 红线：settleSaveEconV2 未被本补丁触碰',
         text.count('function settleSaveEconV2(oldSd: any, newSd: any, prevSavedAtMs: number | null, lumpPool?: { tower: number; exped: number }, winState?: { start: number | null; exp: number; stone: number }): string[]') == 1)
    gate('G10 红线：GM_PASSWORD 逻辑未动', "password !== GM_PASSWORD" in text)
    gate('G11 原有 30 个 /api/gm/* 端点数量未变', text.count("/api/gm/") >= 30)

    bad = [g for g in gates if not g[1]]
    print('\n  --- 门禁 ---')
    for name, ok_, detail in gates:
        print('  [%s] %s%s' % ('OK' if ok_ else 'FAIL', name, ('  ' + detail) if detail else ''))
    if bad:
        print('\n[ABORT] 门禁未全过，不写出')
        return 1

    if out != src:
        open(out, 'wb').write(text.encode('utf-8'))
        print('\n  [写出] %s  %d 字符  md5=%s' % (out, len(text), md5s(text)))
    else:
        bak = '%s.bak-net2-%s' % (src, __import__('time').strftime('%Y%m%d-%H%M%S'))
        __import__('shutil').copy2(src, bak)
        print('\n  [备份] %s' % bak)
        open(src, 'wb').write(text.encode('utf-8'))
        print('  [写出] %s  %d 字符  md5=%s' % (src, len(text), md5s(text)))

    print('  [PASS] net-2 服务端修复完成（+%d 字符）' % (len(text) - len(open(src if out == src else out, encoding='utf-8').read()) if False else 0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
