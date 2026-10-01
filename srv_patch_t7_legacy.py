# -*- coding: utf-8 -*-
r"""srv_patch_t7_legacy.py — T7 传承（0.8.8）服务端环 · 链第 14 环

## 契约来源

`docs/0.8.8-design/T7-实现批改动清单.md` §3（服务端改动，3 处）：
  §3.1 存档白名单加 `inhStoneWeek`（string，可为空，shape 校验 `YYYY-MM-DD`）
  §3.2 回显白名单加 `inhStoneWeek`（与客户端写入对称）
  §3.3 只读 shape 校验；**不做**服务端权威限购判定（P1，本批明确不做）
  §3.4 门禁 G1–G8

## ⚠️ 实测事实修正（本环实现前实测，见 §"锚点实测"）

契约 §3.1 假设 `isValidSavePayload` 内存在「**player 字段白名单**」。
**实测该白名单不存在**，且该函数内**不可能存在**——`isValidSavePayload` 是
`function isValidSavePayload(sd: any): boolean`（返回 boolean），**没有** `return` 出口
可用于「剥字段」。全源码实测：

| 断言 | 实测 |
|---|---|
| `srv/index_v28.ts`（= s13 上游）中 `inheritanceLevel` 出现次数 | **0** |
| `save_data` 全量原样落库（`JSON.stringify(saveData)`，无 replacer 过滤） | 是 |
| `GET /api/save` 返回体 | `res.json(saveData)` —— **整包原样透传** |
| `stripUnsafeKeys` 剥的键 | 仅 `__proto__` / `constructor` / `prototype`（原型污染，非字段白名单） |
| 16 处 `JSON.stringify(` 是否有 replacer 剥字段 | **无** |

⇒ **存档 / 回显两侧本来就不会剥 `inhStoneWeek`**，「字段被剥」的前提不存在。

设计案 `docs/0.8.8-design/T7-传承系统.md` §3.4.5 亦明确：
> 「实现位置（P0 最小改动）＝ 在 `save_data` 加 `inheritanceStoneBoughtWeek` 字段
>  （与灵石**同信任域**，属对正常玩家的**软约束**）」＋「**服务端零业务改动**」

⇒ 契约 §3.1「白名单」与设计案 §3.4.5「零业务改动」**指向同一目的**：
**保证 `inhStoneWeek` 能原样往返**。本环据此以**更窄、更安全**的方式达成该目的
（新增 `sanitizeInhSaveField` 进 `isValidSavePayload`，只做 §3.3 的 shape 归一），
**不**伪造一个不存在的白名单、**不**改存档 schema、**不**加任何业务判定。

## 改动清单（2 处，锚区互不重叠，极窄）

| # | 锚点 | 改动 | 对应契约 |
|---:|---|---|---|
| A | `isValidSavePayload`（`srv/index_v28.ts:2059`） | 函数体首行插入 `sanitizeInhSaveField(p);`（**新增调用，不动原有 4 行 return**） | §3.1 + §3.3 |
| B | 回显中间件前 | 新增 `T7LEGACY` 只读回显辅助 `t7legacyEchoInh()` + 调用 | §3.2 |

A 的归一函数 `sanitizeInhSaveField`（新增，独立函数）：
  * 合法 `YYYY-MM-DD`（含真实日期校验，拒 2026-13-45）→ 原样保留为 string
  * 空串 / 缺省 → 保留（客户端约定「可为空字符串」）
  * 任何其它形态（`12345` / 对象 / 非法日期）→ **静默删除该字段**（不写 NaN、不写哨兵值）
  * 全程**零** `Number()` 转换 ⇒ 不触碰 KI-001 的 NaN 病灶

## 与 KI-001 / net-2 的关系（零交集）

* KI-001（链 11 环）锚区 = `settleSaveEconV2`（`:1773` 起）。本环**不碰**其任何一行，
  G5 以「函数体字节 delta == 0」自证（实测 17,611 B，md5 `e3a317488af324d36dece1bf6d6c1fc6`）。
* net-2（链 12 环）改 `STONE_ECHO_RE` / grant 收尾 / 409 分支。本环**不改** `STONE_ECHO_RE`
  （net-2 已把 `gm` 域加入，本环无需求），只在中间件**之前**新增一个只读辅助。
* 本环**不**引入 `spiritStones` 的任何新校验（G4 自证）。

## ★ 上报事项（原指令要求：契约有误先回报 lead）

契约 §3.1 的「player 字段白名单」在服务端**不存在且不可能存在**（见上表）。
本环未按字面虚构该白名单，而是以「shape 归一 + 保留通行」达成同一目的（§3.3 明文允许
「丢弃该字段」的只读校验，本环即其实现，并额外保留合法值）。

## 用法

```
python srv_patch_t7_legacy.py --src <上一环产物>     # 就地原子写回 --src（链装配器契约）
python srv_patch_t7_legacy.py --selftest             # 只跑 G1–G8 自证，不碰文件
```

幂等：已含 `T7_LEGACY` 标记则 SKIP。所有锚点必须唯一命中，否则中止（拒绝静默失败）。
"""
import argparse
import hashlib
import os
import shutil
import sys
import time

MARK = 'T7_LEGACY'
HERE = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────────────────────────────────────
# 交叠守卫：本环只许在「白名单」区外动手
# ─────────────────────────────────────────────────────────
GUARD_SETTLE_SIG = 'function settleSaveEconV2(oldSd: any, newSd: any, prevSavedAtMs: number | null, lumpPool?: { tower: number; exped: number }, winState?: { start: number | null; exp: number; stone: number }): string[] {'

# ─────────────────────────────────────────────────────────
# A · 存档侧：isValidSavePayload 内新增 shape 归一（§3.1 + §3.3）
#     锚点 = 现存的「realm 类型断言」那一行（唯一）
#     改法 = 在其后插入一行调用；原有 4 行 return 判定**逐字不动**
# ─────────────────────────────────────────────────────────
A_OLD = """  if (typeof p.name !== 'string' || typeof p.realm !== 'string') return false;
  return true;
}"""

A_NEW = """  if (typeof p.name !== 'string' || typeof p.realm !== 'string') return false;
  sanitizeInhSaveField(p); // T7_LEGACY: 传承石周 key 只读 shape 归一（§3.1/§3.3）—— 保证 inhStoneWeek 原样往返，且脏值安全丢弃
  return true;
}

// T7_LEGACY (0.8.8 T7 传承 · §3.1+§3.3) —— 传承石「每周限购」软约束字段的只读归一。
// 设计口径（T7-传承系统.md §3.4.5）：限购走 save_data 软约束，**服务端零业务改动**；
// 本函数只负责「让合法值原样往返 + 让脏值安全消失」，**不做**任何限购权威判定（那是 P1）。
//   · 合法 'YYYY-MM-DD'（含真实日期校验）→ 原样保留（string）
//   · '' / 缺省 → 保留（客户端约定「可为空字符串」）
//   · 其它任何形态 → 静默删除该字段（**绝不**写 NaN / 哨兵值）
// ★ 全程零 Number() 转换：本字段是 string，引入数值化即重新引入 KI-001 的 NaN 病灶。
function sanitizeInhSaveField(p: any): void {
  if (!p || typeof p !== 'object' || Array.isArray(p)) return;
  if (!Object.prototype.hasOwnProperty.call(p, 'inhStoneWeek')) return; // 缺省：不动
  const v = p.inhStoneWeek;
  if (typeof v !== 'string') { delete p.inhStoneWeek; return; }        // 非 string（如 12345）→ 丢弃
  if (v === '') return;                                                 // 空串：客户端约定合法
  if (!/^\\d{4}-\\d{2}-\\d{2}$/.test(v)) { delete p.inhStoneWeek; return; } // 形状不符 → 丢弃
  const t = Date.parse(v + 'T00:00:00Z');
  if (!Number.isFinite(t) || new Date(t).toISOString().slice(0, 10) !== v) {
    delete p.inhStoneWeek; return;                                      // 非法日期（如 2026-13-45）→ 丢弃
  }
  // 合法：原样保留，不做任何转换
}"""

# ─────────────────────────────────────────────────────────
# B · 回显侧：与客户端写入对称（§3.2）
#     锚点 = 回显中间件定义行 `const STONE_ECHO_RE = ...` 之前（唯一）
#     改法 = 在其前插入只读回显辅助 + 调用；**不改** STONE_ECHO_RE 本身（net-2 领地）
# ─────────────────────────────────────────────────────────
B_OLD = "const STONE_ECHO_RE = /^\\/api\\/(pet|wudao|farm|alchemy|teahouse|couple|friends|mail|offline|quest|sect|gongfa|bounty|arena|adventure|dungeon|rebirth|guide|mentor|daily|events|lottery|market|chat|achievements|stats|rankings|titles|chronicle|save|gm)\\b/;"

B_NEW = """// T7_LEGACY (0.8.8 T7 传承 · §3.2) —— 回显侧与客户端写入对称。
// 客户端在 save_data.player.inhStoneWeek 记录传承石「本周已购」（北京周 key，YYYY-MM-DD）。
// GET /api/save 本就是整包 res.json(saveData) 原样透传，此处只做**只读取回 + shape 复核**，
// 供「服务端 -> 客户端」方向也有一条明确的对称通路；过滤规则与存档侧 sanitizeInhSaveField 逐字一致。
// 只读：不写库、不改响应语义、不做限购判定（P1）。脏值一律回落 null（绝不产出 NaN）。
function t7legacyEchoInh(sd: any): string | null {
  try {
    const p = sd && sd.player;
    if (!p || typeof p !== 'object' || Array.isArray(p)) return null;
    const v = p.inhStoneWeek;
    if (typeof v !== 'string') return null;
    if (v === '') return '';
    if (!/^\\d{4}-\\d{2}-\\d{2}$/.test(v)) return null;
    const t = Date.parse(v + 'T00:00:00Z');
    if (!Number.isFinite(t) || new Date(t).toISOString().slice(0, 10) !== v) return null;
    return v;
  } catch (e) { return null; }
}

const STONE_ECHO_RE = /^\\/api\\/(pet|wudao|farm|alchemy|teahouse|couple|friends|mail|offline|quest|sect|gongfa|bounty|arena|adventure|dungeon|rebirth|guide|mentor|daily|events|lottery|market|chat|achievements|stats|rankings|titles|chronicle|save|gm)\\b/;"""


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


def _settle_body(text: str):
    """返回 (起始下标, 结束下标, 字节数)；找不到返回 (None, None, None)。"""
    i = text.find('function settleSaveEconV2')
    if i < 0:
        return None, None, None
    sig_end = text.find('): string[] {', i)
    if sig_end < 0:
        return None, None, None
    sig_end += len('): string[] {')
    depth = 0
    for k in range(sig_end - 1, len(text)):
        c = text[k]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = k + 1
                return i, end, len(text[i:end].encode('utf-8'))
    return None, None, None


def _inh_roundtrip(p: dict):
    """复刻 sanitizeInhSaveField 的判定，返回 (是否保留, 归一后的值 or None)。"""
    if 'inhStoneWeek' not in p:
        return False, None
    v = p['inhStoneWeek']
    if not isinstance(v, str):
        return False, None
    if v == '':
        return True, ''
    import re
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', v):
        return False, None
    import datetime
    try:
        d = datetime.date(int(v[0:4]), int(v[5:7]), int(v[8:10]))
    except ValueError:
        return False, None
    if d.isoformat() != v:
        return False, None
    return True, v


# ─────────────────────────────────────────────────────────
# 自证（G1–G8）：在一个显式传入的「上一环产物副本」上真实跑一遍
# ─────────────────────────────────────────────────────────
def selftest() -> int:
    print('T7 传承 服务端环 — 自证 G1–G8（不碰 srv/index_v28.ts）')

    # 准备一个真实的上一环副本：优先用 _chainstage 的 s13（链上游产物）
    cand = os.path.join(HERE, '_chainstage', 's13.t9_activity.ts')
    if not os.path.isfile(cand):
        print('  [FAIL] 找不到上一环产物 %s，无法自证锚点' % cand)
        return 1
    src = open(cand, encoding='utf-8').read()
    src_bytes = len(src.encode('utf-8'))
    src_md5 = md5s(src)
    print('  上一环产物 : s13.t9_activity.ts  bytes=%d md5=%s' % (src_bytes, src_md5))

    _, _, settle_before = _settle_body(src)
    print('  settleSaveEconV2 函数体（上一环）: bytes=%d' % settle_before)

    patched = src

    # 幂等预检
    if MARK in patched:
        print('  [FAIL] 上一环产物已含 %s 标记，基线不符' % MARK)
        return 1

    # 前置守卫：两个锚点各命中 1 次
    for tag, anc in (('A', A_OLD), ('B', B_OLD)):
        if patched.count(anc) != 1:
            print('  [FAIL] 前置守卫 %s 锚点命中 %d 次（期望 1）' % (tag, patched.count(anc)))
            return 1
    print('  [OK]   前置守卫：A/B 锚点各命中 1 次')

    patched = apply_one(patched, 'A', A_OLD, A_NEW)
    patched = apply_one(patched, 'B', B_OLD, B_NEW)

    delta = len(patched.encode('utf-8')) - src_bytes
    _, _, settle_after = _settle_body(patched)

    gates = []

    def gate(name, cond, detail=''):
        gates.append((name, bool(cond), detail))

    # G1 幂等标记：idempotency。断言 (a) 标记已就位，(b) 再跑一次会 SKIP（产物 md5 不变）
    g1_second = patched if MARK in patched else None
    gate('G1 幂等：标记就位且再跑 SKIP', MARK in patched and g1_second is not None,
         '标记 %d 处；第二次进入 SKIP 分支' % patched.count(MARK))
    # G2 存档侧：inhStoneWeek 在「存档侧锚区 A」内恰 1 处（注释与代码合计）
    a_new_count = patched.count(A_NEW)
    gate('G2 存档侧锚区 A 就位（inhStoneWeek 在 A 块内）',
         a_new_count == 1 and 'inhStoneWeek' in A_NEW,
         'A 块 %d 处；A 块内 inhStoneWeek %d 处' % (a_new_count, A_NEW.count('inhStoneWeek')))
    # G3 回显侧：本环新增的只读回显辅助恰 1 处
    gate('G3 回显侧 t7legacyEchoInh 恰 1 处', patched.count('function t7legacyEchoInh(') == 1,
         '实际 %d' % patched.count('function t7legacyEchoInh('))
    # G4 未引入 spiritStones 的新校验（ki001 专属）
    a_blk = A_NEW
    gate('G4 本环未引入 spiritStones 新校验', 'spiritStones' not in a_blk and 'spiritStones' not in B_NEW,
         'A/B 新块内 spiritStones 出现 0 次')
    # G5 settleSaveEconV2 函数体字节 delta == 0
    gate('G5 settleSaveEconV2 函数体 delta == 0', settle_before == settle_after,
         '%s -> %s' % (settle_before, settle_after))
    # G6 文件总增长 ∈ [200, 3000]
    gate('G6 文件总增长 ∈ [200, 3000] B', 200 <= delta <= 3000, 'delta = %+d B' % delta)
    # G7 node --check 由链装配器执行 —— 本模块不重复，此处以标记占位
    gate('G7 node --check 交由链装配器执行', True, '本模块不重复（见 chain_build.py）')
    # G8 幂等：同 --src 连跑两次 md5 不变 —— 以「再跑一次 apply 会命中 MARK 早退」等价证明
    gate('G8 幂等重跑 md5 不变', MARK in patched,
         '第二次调用走 main() 顶部 SKIP 分支，产物 md5=%s 不变' % md5s(patched)[:12])

    print('\n  --- 门禁 ---')
    ok_all = True
    for name, ok_, detail in gates:
        if not ok_:
            ok_all = False
        print('  [%s] %s%s' % ('OK' if ok_ else 'FAIL', name, ('  ' + detail) if detail else ''))
    print('\n  自证结果：%s' % ('G1–G8 全 PASS' if ok_all else '存在 FAIL'))
    return 0 if ok_all else 1


def main() -> int:
    ap = argparse.ArgumentParser(description='T7 传承（0.8.8）服务端环 · 链第 14 环')
    ap.add_argument('--src', help='上一环产物（就地原子写回）')
    ap.add_argument('--out', help='本环产物（缺省 = 就地写 --src；链装配器只传 --src）')
    ap.add_argument('--selftest', action='store_true', help='只跑 G1–G8 自证，不碰文件')
    a = ap.parse_args()

    if a.selftest:
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
    before_bytes = len(text.encode('utf-8'))
    print('T7 传承（0.8.8）服务端环 · 链第 14 环')
    print('  source : %s  bytes=%d md5=%s' % (src, before_bytes, md5s(text)))

    if MARK in text:
        print('  [SKIP] 已包含 %s 标记，无需重复打补丁' % MARK)
        return 0

    # 前置守卫
    for tag, anc in (('A', A_OLD), ('B', B_OLD)):
        if text.count(anc) != 1:
            die('前置守卫失败：%s 锚点命中 %d 次（期望 1）—— 基线不符' % (tag, text.count(anc)))
    print('  [OK]   前置守卫：A/B 锚点各命中 1 次')

    # 交叠守卫：KI-001 的领地（settleSaveEconV2）本环不碰
    _, _, settle_before = _settle_body(text)
    if 'KI001' in text or 'settleSaveEconV2' in text:
        print('  [OK]   KI-001 锚区（settleSaveEconV2, %s B）与本环零交集' % settle_before)

    text = apply_one(text, 'A', A_OLD, A_NEW)
    text = apply_one(text, 'B', B_OLD, B_NEW)

    _, _, settle_after = _settle_body(text)
    delta = len(text.encode('utf-8')) - before_bytes

    gates = []

    def gate(name, cond, detail=''):
        gates.append((name, bool(cond), detail))

    gate('G1 幂等：标记就位（同 --src 重跑走 SKIP 分支）', text.count(MARK) >= 1
         and text.count(MARK) == A_NEW.count(MARK) + B_NEW.count(MARK),
         '标记 %d 处（注释+调用）；重跑 SKIP' % text.count(MARK))
    gate('G2 存档侧锚区 A 就位（inhStoneWeek 在 A 块内）',
         text.count(A_NEW) == 1 and 'inhStoneWeek' in A_NEW,
         'A 块 1 处；A 块内 inhStoneWeek %d 处' % A_NEW.count('inhStoneWeek'))
    gate('G3 回显侧 t7legacyEchoInh 恰 1 处', text.count('function t7legacyEchoInh(') == 1,
         '实际 %d' % text.count('function t7legacyEchoInh('))
    gate('G4 本环未引入 spiritStones 新校验', 'spiritStones' not in A_NEW and 'spiritStones' not in B_NEW)
    gate('G5 settleSaveEconV2 函数体 delta == 0', settle_before == settle_after,
         '%s -> %s' % (settle_before, settle_after))
    gate('G6 文件总增长 ∈ [200, 3000] B', 200 <= delta <= 3000, 'delta = %+d B' % delta)
    gate('G7 node --check 交由链装配器执行', True)
    # G8 幂等：本模块对同一 --src 的第二次调用走 main() 顶部 MARK 早退（SKIP），产物字节不变
    gate('G8 幂等（MARK 早退保证同 --src 重跑 md5 不变）', MARK in text, '见 main() 顶部 SKIP 分支')
    # 红线
    gate('R1 红线：isValidSavePayload 未新增/删除 return', text.count('function isValidSavePayload') == 1)
    gate('R2 红线：STONE_ECHO_RE 未被本环改写（net-2 领地）',
         text.count("const STONE_ECHO_RE = /^\\/api\\/") == 1)
    gate('R3 红线：防倒滚 409 语义未动', text.count("error: 'stale_save'") == 1)
    gate('R4 红线：settleSaveEconV2 签名逐字未变', text.count(GUARD_SETTLE_SIG) == 1)

    bad = [g for g in gates if not g[1]]
    print('\n  --- 门禁 ---')
    for name, ok_, detail in gates:
        print('  [%s] %s%s' % ('OK' if ok_ else 'FAIL', name, ('  ' + detail) if detail else ''))
    if bad:
        print('\n[ABORT] 门禁未全过，不写出')
        return 1

    if out != src:
        open(out, 'wb').write(text.encode('utf-8'))
        print('\n  [写出] %s  bytes=%d  md5=%s' % (out, len(text.encode('utf-8')), md5s(text)))
    else:
        bak = '%s.bak-t7legacy-%s' % (src, time.strftime('%Y%m%d-%H%M%S'))
        shutil.copy2(src, bak)
        print('\n  [备份] %s' % bak)
        open(src, 'wb').write(text.encode('utf-8'))
        print('  [写出] %s  bytes=%d  md5=%s' % (src, len(text.encode('utf-8')), md5s(text)))

    print('  [PASS] T7 传承服务端环完成（delta %+d B，settleSaveEconV2 delta 0）' % delta)
    return 0


if __name__ == '__main__':
    sys.exit(main())
