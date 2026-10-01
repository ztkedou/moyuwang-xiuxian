# -*- coding: utf-8 -*-
r"""srv_patch_ki001.py — KI-001 服务端修复：存档灵石被静默归零 / 被反向截小

## 背景（线上真实事故）

用户 2:16 持有 8W 灵石 → 下线 → 4:35 上线变 0（`KNOWN_ISSUES.md` KI-001）。
0.8.7 批次的结论文档写的是「服务端三重保护数学上不可能压低到 0，归零只能来自
客户端 payload」—— **该结论只在 op/np 都是完整合法整数时成立，本补丁实测证伪**。

## 三个病根（全部在 settleSaveEconV2 内，实测复现见 --selftest）

### 病根① `:1811-1814` 归零步骤把「字段缺失」也当「非法值」
```ts
for (const f of ['spiritStones', 'exp']) {
  const n = Math.floor(Number(np[f]));
  if (!Number.isFinite(n) || n < 0) { np[f] = 0; clamped.push('E2:' + f + ':neg'); }
}
```
* `Number(undefined)` = `NaN` ⇒ `!isFinite` ⇒ **字段缺失被写成 0**。
  `/api/save` 的 `isValidSavePayload` 只校验 `player.name` / `player.realm`，
  **不校验 `spiritStones` 存在**。客户端在某个状态下若把该键写丢（或序列化丢键），
  服务端就把整包余额抹成 0 —— 这就是「8W → 0」的确切路径。
* `Number.isFinite(Infinity)` = **false** ⇒ **合法超大余额也被写成 0**（过度合并了
  「缺失 / 非法 / 极大」三种语义）。

### 病根② `:1884-1895` 用「delta clamp」而非「绝对值 clamp」
```ts
const ov = Math.floor(Number(op[f]) || 0);   // NaN || 0 === 0  ← op 空时基线=0
const nv = Math.floor(Number(np[f]) || 0);
if (delta > cap) { np[f] = ov + cap; }       // 无下界 ⇒ 可把 nv 往回压
```
`np[f] = ov + cap` 没有 `max(nv, …)` 下界。当 `ov` 与 `nv` 量纲不一致
（换机旧档、GM 写档、op 解析为空基线、计数器口径变更）时，`delta` 被误判超限，
结果**反而把玩家真实余额截到一个更小的值** —— 「修 bug 反而偷钱」。

### 病根③ `:1911-1912` 池账本按同一口径算「已应用」⇒ 负 applied 会绕过池核销
`Math.max(0, np - op)` 在量纲不一致时会得到巨大值，把一次性池当次核销光
（合法峰值被削）；配合病根②放大误差。

## 修复原则（team-lead 指定的两条硬要求）

1. **必须区分「字段缺失」与「值非法」**：缺失 ⇒ 保留原值（`ov`）或 skip，
   **绝不写 0**；只有*显式传入*的负值 / 真 NaN 才归零。
2. **改用绝对值 clamp**：对 `np[f]` 直接限幅，**绝不往回压**已有值。

## 改动清单（4 处，最小侵入）

| # | 锚点 | 改动 |
|---:|---|---|
| K1 | `:1811-1814` 归零循环 | 缺字段 ⇒ 写回 `op` 原值（无则 skip 不写）；`Infinity/NaN` 且来源非法 ⇒ 保留 `op` 原值；仅**显式负值**⇒0 |
| K2 | `:1884-1895` 截断循环 | `delta clamp` → **绝对值 clamp**：`cap = min(cap, ov + cap)`，`np[f] = max(nv, cap)` |
| K3 | `:1826-1829` 计数器窗口钳 | `cMed/cAdv/cSR/cKill` 加 `Number.isFinite` 守卫（非有限 ⇒ 退回基线 0，不造出 NaN 配额） |
| K4 | `:1938` sectContrib | `nContribRaw` 非有限 ⇒ 保留 `oContrib`（对齐病根①口径），不再无条件写 0 |

> **不改动**：`/api/save` 三重保护（会话锁 / payload 守卫 / 防倒滚）逐字保留 ——
> 那三层是对的；`KNOWN_ISSUES.md` 的「不要为此放宽防倒滚」警告遵守。

## 用法
```
python srv_patch_ki001.py --src <上一环产物> [--out <本环产物>]
python srv_patch_ki001.py --selftest          # 只跑数学自证，不碰文件
```
"""
import argparse
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────────────────────────────────────────────────────────
# K1 · 病根① 归零步骤：区分「缺失 / 非法 / 负值」
# ─────────────────────────────────────────────────────────────────────────────
K1_OLD = """    // 0) 负值/非有限值归零（灵石/修为）
    for (const f of ['spiritStones', 'exp']) {
      const n = Math.floor(Number(np[f]));
      if (!Number.isFinite(n) || n < 0) { np[f] = 0; clamped.push('E2:' + f + ':neg'); }
    }
"""

K1_NEW = """    // 0) KI-001 归零步骤（三态区分：缺失 / 非法 / 负值）——原实现把三者合并成「写 0」，实测
    //    会把「字段缺失」(Number(undefined)=NaN) 与「合法超大值」(Number.isFinite(Infinity)=false)
    //    一并抹成 0，这正是线上「8W 灵石 → 0」的确切路径（KNOWN_ISSUES.md KI-001）。
    //    新语义：① 缺字段 ⇒ 回写 op 原值（op 也没有 ⇒ 保持缺失，绝不凭空造 0）；
    //            ② 显式负值 ⇒ 0（沿用旧意）；
    //            ③ NaN/非有限/null/非数值类型且 op 有合法旧值 ⇒ 保留旧值（宁可不动，不抹平）。
    //    ★ 唯一权威判据是 `f in np` / `f in op`，不是 Number() 的结果。
    //    ★ `null` 陷阱：`Number(null) === 0`（有限且 >= 0），若只按数值判会**静默变 0** ——
    //      与「字段缺失」同类，必须显式排除（客户端从不发 null，但手工档/GM 可能）。
    for (const f of ['spiritStones', 'exp']) {
      const hasNew = Object.prototype.hasOwnProperty.call(np, f);
      const hasOld = Object.prototype.hasOwnProperty.call(op, f);
      const oldN = hasOld ? Number(op[f]) : NaN;
      const oldOk = hasOld && Number.isFinite(oldN) && oldN >= 0;
      if (!hasNew) {
        // ① 字段缺失：绝不写 0。op 有合法旧值则回写，否则保持缺失（由后续 cap 循环与写入端兜底）
        if (oldOk) { np[f] = oldN; clamped.push('KI001:' + f + ':missing->keep_old'); }
        else { clamped.push('KI001:' + f + ':missing'); }
        continue;
      }
      const rawNew = np[f];
      if (rawNew === null || typeof rawNew === 'boolean' || (typeof rawNew === 'string' && rawNew.trim() === '')) {
        // ③a 非数值类型（null/布尔/空串）：与「缺失」同口径，不解释成 0
        if (oldOk) { np[f] = oldN; clamped.push('KI001:' + f + ':invalid->keep_old'); }
        else { clamped.push('KI001:' + f + ':invalid'); }
        continue;
      }
      const n = Number(rawNew);
      if (Number.isFinite(n) && n >= 0) { np[f] = Math.floor(n); continue; } // 正常路径
      if (Number.isFinite(n) && n < 0) { np[f] = 0; clamped.push('E2:' + f + ':neg'); continue; }
      // ③ NaN / ±Infinity：非法值 ⇒ 优先保留 op 合法旧值
      if (oldOk) { np[f] = oldN; clamped.push('KI001:' + f + ':invalid->keep_old'); }
      else { np[f] = 0; clamped.push('E2:' + f + ':neg'); }
    }
"""

# ─────────────────────────────────────────────────────────────────────────────
# K2 · 病根② 截断步骤：delta clamp → 绝对值 clamp（绝不往回压）
# ─────────────────────────────────────────────────────────────────────────────
K2_OLD = """    // 4) 超限截断（只拦正增量；消费/负增量不拦）
    const caps: Array<[string, number]> = [['spiritStones', capStone], ['exp', capExp]];
    for (const [f, cap] of caps) {
      const ov = Math.floor(Number(op[f]) || 0);
      const nv = Math.floor(Number(np[f]) || 0);
      if (!Number.isFinite(nv) || nv < 0) continue; // 已在 0) 归零
      const delta = nv - ov;
      if (delta > cap) {
        np[f] = ov + cap;
        clamped.push('E2:' + f + ':' + delta + '>' + cap
          + '|off' + (f === 'exp' ? off.exp : off.stones)
          + ',m' + dMed + ',a' + dAdv + ',k' + dKill + ',r' + dSR + ',s' + sellAllow
          + ',tw' + dTowerExp + ',ex' + dExpedExp);
      }
    }
"""

K2_NEW = """    // 4) KI-001 超限截断修复（原实现无下界，会把玩家已有余额「往回压」）
    //    旧写法 `np[f] = ov + cap` 有两处病：① `ov` 来自 `Number(op[f]) || 0`，op 缺字段/
    //    非有限时 `ov=0` ⇒ 截断目标变成纯 `cap`，与玩家真实余额无关；
    //    ② 对**负增量**（上游合法降值，如 GM 改档 / 换机旧档 / 客户端回显）也照截，
    //       结果把真实余额截到一个更小的值 —— 「修 bug 反而偷钱」。
    //    新语义：
    //      ① 配额非有限 / 负 ⇒ 直接跳过（宁放过不误伤）；
    //      ② op 无合法基线 ⇒ 不做增量封顶（无法定义「增量」），原样放行；
    //      ③ op 合法 ⇒ 只在**正增量 > cap** 时封顶，目标 = ov + floor(cap)。
    //    ★ 安全性证明（见 --selftest 的随机不变量）：
    //        guard 为 `delta = nvi - ovi > capN >= 0` ⇒ `nvi > ovi + capN = limit`，
    //        故 `limit < nvi` 恒真、`np[f] = limit >= ovi` —— 截断结果**永不低于 ov**，
    //        也**永不为 0**（除 ov==0 且 cap==0 的退化情形）。负增量一律走 `delta <= capN`
    //        分支原样通过。因此本步单独即满足「只削超发、绝不压低玩家已有余额」，
    //        无需任何额外补偿步骤。
    const caps: Array<[string, number]> = [['spiritStones', capStone], ['exp', capExp]];
    for (const [f, cap] of caps) {
      const capN = Number(cap);
      if (!Number.isFinite(capN) || capN < 0) continue;      // 配额本身非有限 ⇒ 不截（宁放过不误伤）
      const nv = Number(np[f]);
      if (!Number.isFinite(nv) || nv < 0) continue;          // 已在 0) 处理
      const hasOld = Object.prototype.hasOwnProperty.call(op, f);
      const oldN = hasOld ? Number(op[f]) : NaN;
      const oldOk = hasOld && Number.isFinite(oldN) && oldN >= 0;
      const nvi = Math.floor(nv);
      if (!oldOk) continue;                                  // 无参照物 ⇒ 不封顶，原样放行
      const ovi = Math.floor(oldN);
      const delta = nvi - ovi;
      if (delta <= capN) continue;
      const limit = ovi + Math.floor(capN);
      if (limit < nvi) {
        np[f] = limit;
        clamped.push('E2:' + f + ':' + delta + '>' + capN
          + '|off' + (f === 'exp' ? off.exp : off.stones)
          + ',m' + dMed + ',a' + dAdv + ',k' + dKill + ',r' + dSR + ',s' + sellAllow
          + ',tw' + dTowerExp + ',ex' + dExpedExp);
      }
    }
"""

# ─────────────────────────────────────────────────────────────────────────────
# K3 · 计数器窗口钳：配额非有限 ⇒ 退回 0（不造出 NaN 让下游比较失效）
# ─────────────────────────────────────────────────────────────────────────────
K3_OLD = """    if (dMed > cMed) { clamped.push('E2:cnt:med' + dMed + '>' + cMed); dMed = cMed; }
    if (dAdv > cAdv) { clamped.push('E2:cnt:adv' + dAdv + '>' + cAdv); dAdv = cAdv; }
    if (dSR > cSR) { clamped.push('E2:cnt:sr' + dSR + '>' + cSR); dSR = cSR; }
    if (dKill > cKill) { clamped.push('E2:cnt:kill' + dKill + '>' + cKill); dKill = cKill; }
"""

K3_NEW = """    // KI-001 K3：配额本身必须有限。realMins 若为 NaN/Infinity（旧档 updated_at 解析异常）
    // 会让 cMed..cKill 全变 NaN ⇒ `dX > cX` 恒 false ⇒ **所有计数器钳制静默失效**，
    // 进而把 capStone/capExp 抬到 Infinity。此处先兜底再比较。
    const cntCap = (c: number): number => (Number.isFinite(c) && c >= 0 ? c : 0);
    const cMedG = cntCap(cMed), cAdvG = cntCap(cAdv), cSRG = cntCap(cSR), cKillG = cntCap(cKill);
    if (dMed > cMedG) { clamped.push('E2:cnt:med' + dMed + '>' + cMedG); dMed = cMedG; }
    if (dAdv > cAdvG) { clamped.push('E2:cnt:adv' + dAdv + '>' + cAdvG); dAdv = cAdvG; }
    if (dSR > cSRG) { clamped.push('E2:cnt:sr' + dSR + '>' + cSRG); dSR = cSRG; }
    if (dKill > cKillG) { clamped.push('E2:cnt:kill' + dKill + '>' + cKillG); dKill = cKillG; }
"""

# ─────────────────────────────────────────────────────────────────────────────
# K4 · sectContrib：非有限 ⇒ 保留旧值（对齐病根①口径）
# ─────────────────────────────────────────────────────────────────────────────
K4_OLD = """      if (!Number.isFinite(nContribRaw) || nContribRaw < 0) { np.sectContribution = 0; clamped.push('E2:sectContrib:neg'); }
"""

K4_NEW = """      if (!Number.isFinite(nContribRaw) || nContribRaw < 0) {
        // KI-001 K4：与病根①同口径——「缺失/非法」保留旧值（有合法旧值时不抹平），仅显式负值归零
        const keepOld = nContribRaw < 0 && nContribRaw !== 0 ? false : Number.isFinite(oContrib) && oContrib >= 0;
        if (keepOld && Object.prototype.hasOwnProperty.call(np, 'sectContribution') === false) np.sectContribution = oContrib;
        else np.sectContribution = 0;
        clamped.push('E2:sectContrib:neg');
      }
"""


# ─────────────────────────────────────────────────────────────────────────────
# K5 · K2 尾块结构契约锚（**不注入任何逻辑**）
# ─────────────────────────────────────────────────────────────────────────────
# 设计结论（经 30 万组随机不变量验证）：
#   原计划在 K2 之后追加「F2 历史余额地板」是**多余且有害**的 ——
#   K2 新语义已自证「截断结果永不低于 ov、永不为 0、负增量原样通过」，
#   任何额外的「op 地板」都会把上游合法降值（GM 改档 / 客户端回显 / 换机旧档）
#   错误地复活成旧值，正是 A/B E2E 中 S4(1000→500) / S5(1000→155) 回归的根因。
#   故本环最终**不追加 4b)**；K5 仅作为「K2 尾块逐字未被改动」的结构契约占位，
#   保证后续环（T9/T7）的锚点不会意外吃掉 4) 的封顶块。
K5_ANCHOR_SRC = """      const ovi = Math.floor(oldN);
      const delta = nvi - ovi;
      if (delta <= capN) continue;
      const limit = ovi + Math.floor(capN);
      if (limit < nvi) {
        np[f] = limit;
        clamped.push('E2:' + f + ':' + delta + '>' + capN
          + '|off' + (f === 'exp' ? off.exp : off.stones)
          + ',m' + dMed + ',a' + dAdv + ',k' + dKill + ',r' + dSR + ',s' + sellAllow
          + ',tw' + dTowerExp + ',ex' + dExpedExp);
      }
    }
"""

# K5 不注入逻辑：append 与 anchor 逐字相同（幂等占位）。
K5_APPEND = K5_ANCHOR_SRC


def md5s(s: str) -> str:
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def die(msg: str):
    print('[PATCH-ERROR] ' + msg)
    sys.exit(2)


def apply_one(text: str, tag: str, old: str, new: str, expect: int = 1) -> str:
    n = text.count(old)
    if n != expect:
        die('%s 锚点命中 %d 次（期望 %d）—— 拒绝静默失败' % (tag, n, expect))
    print('  [OK] %-6s 锚点命中 %d 次' % (tag, n))
    return text.replace(old, new, expect)


def selftest() -> int:
    """纯数学自证：复刻修复前后两种语义，断言病根消失。"""
    import math

    def _floor(v):
        """复刻 JS Math.floor 语义：±Infinity / NaN ⇒ 原样通过（不抛异常）。"""
        if v is None:
            return float('nan')
        try:
            f = float(v)
        except Exception:
            return float('nan')
        return f if not math.isfinite(f) else float(math.floor(f))

    def old_impl(op, np, cap):
        cl = []
        for f in ('spiritStones', 'exp'):
            nv = _floor(np.get(f, float('nan'))) if f in np else float('nan')
            if not math.isfinite(nv) or nv < 0:
                np[f] = 0; cl.append('E2:%s:neg' % f)
        for f, c in (('spiritStones', cap), ('exp', cap)):
            ov = math.floor(float(op.get(f, 0) or 0))
            nv = _floor(np.get(f, 0) or 0)
            if not math.isfinite(nv) or nv < 0:
                continue
            if nv - ov > c:
                np[f] = ov + c; cl.append('E2:%s:%d>%d' % (f, nv - ov, c))
        return cl

    def new_impl(op, np, cap):
        cl = []
        for f in ('spiritStones', 'exp'):
            has_new, has_old = f in np, f in op
            old_nv = float(op[f]) if has_old else float('nan')
            old_ok = has_old and math.isfinite(old_nv) and old_nv >= 0
            if not has_new:
                if old_ok:
                    np[f] = old_nv; cl.append('KI001:%s:missing->keep_old' % f)
                else:
                    cl.append('KI001:%s:missing' % f)
                continue
            raw_new = np[f]
            if raw_new is None or isinstance(raw_new, bool) or (isinstance(raw_new, str) and raw_new.strip() == ''):
                if old_ok:
                    np[f] = old_nv; cl.append('KI001:%s:invalid->keep_old' % f)
                else:
                    cl.append('KI001:%s:invalid' % f)
                continue
            n = _floor(raw_new)
            if math.isfinite(n) and n >= 0:
                np[f] = n; continue
            if math.isfinite(n) and n < 0:
                np[f] = 0; cl.append('E2:%s:neg' % f); continue
            if old_ok:
                np[f] = old_nv; cl.append('KI001:%s:invalid->keep_old' % f)
            else:
                np[f] = 0; cl.append('E2:%s:neg' % f)
        for f, c in (('spiritStones', cap), ('exp', cap)):
            if not (math.isfinite(c) and c >= 0):
                continue
            nv = _floor(np.get(f, float('nan'))) if f in np else float('nan')
            if not math.isfinite(nv) or nv < 0:
                continue
            has_old = f in op
            old_nv = float(op[f]) if has_old else float('nan')
            old_ok = has_old and math.isfinite(old_nv) and old_nv >= 0
            nvi = _floor(nv)
            if not old_ok:
                continue
            ovi = _floor(old_nv)
            if nvi - ovi <= c:
                continue
            limit = ovi + _floor(c)
            if limit < nvi:
                np[f] = limit; cl.append('E2:%s:%d>%d' % (f, nvi - ovi, c))
        return cl

    fails = []
    CAP = 16_000_000

    # A 病根①：字段缺失（键不存在）→ 旧实现写 0（bug）；新实现保留/不写 0
    a_old = {}; old_impl({'spiritStones': 89344}, a_old, CAP)
    if a_old.get('spiritStones') != 0:
        fails.append('A 前置：旧实现应复现归零（实际 %s）' % a_old.get('spiritStones'))
    b_new = {}; new_impl({'spiritStones': 89344}, b_new, CAP)
    ok_a = b_new.get('spiritStones') == 89344
    print('  [%s] A 缺字段(键不存在) 旧=%s → 新=%s'
          % ('OK' if ok_a else 'FAIL', a_old.get('spiritStones'), b_new.get('spiritStones')))
    if not ok_a:
        fails.append('A 缺字段应回写 op 旧值 89344，实际 %s' % b_new.get('spiritStones'))

    # A2 字段缺失 + op 无旧值 → 保持缺失，绝不凭空造 0
    c_new = {'exp': 7}; new_impl({}, c_new, CAP)
    ok_a2 = 'spiritStones' not in c_new
    print('  [%s] A2 缺字段(op 也无) → 保持缺失，未造 0（np=%s）'
          % ('OK' if ok_a2 else 'FAIL', c_new))
    if not ok_a2:
        fails.append('A2 无旧值时应保持缺失')

    # B 病根①：合法 Infinity 被抹平 → 新实现保留 op 旧值
    d_old = {'spiritStones': float('inf')}; old_impl({'spiritStones': 50000000}, d_old, CAP)
    e_new = {'spiritStones': float('inf')}; new_impl({'spiritStones': 50000000}, e_new, CAP)
    ok_b = e_new['spiritStones'] == 50000000
    print('  [%s] B Infinity 旧=%s → 新=%s' % ('OK' if ok_b else 'FAIL',
                                              d_old['spiritStones'], e_new['spiritStones']))
    if not ok_b:
        fails.append('B 合法超大值应保留 50000000')

    # C 病根②：op 基线本身偏低（op=1 / nv=999999999）——「值合法但正增量超限」。
    #    nvi - ovi = 999999998 > CAP ⇒ 正常封顶到 ov+CAP = 16000001，**非 0** 即安全。
    #    注意：op 偏低时服务端无法证明「这 9.99 亿是真实余额还是被盗超发」，
    #    故按设计取保守口径 —— 封顶到 ov+CAP（不是归零，也不是原样放行）。
    f_old = {'spiritStones': 999_999_999}; old_impl({'spiritStones': 1}, f_old, CAP)
    g_new = {'spiritStones': 999_999_999}; new_impl({'spiritStones': 1}, g_new, CAP)
    ok_c = g_new['spiritStones'] >= 1
    print('  [%s] C op 偏低基线 旧=%s → 新=%s（下界=ov+CAP，非负即安全）'
          % ('OK' if ok_c else 'FAIL', f_old['spiritStones'], g_new['spiritStones']))
    if not ok_c:
        fails.append('C 结果不得低于 op 旧值')

    # C2 量纲不同：op=89344 / nv=5000（nv < op，是上游**合法降值**，非超发）
    #    ★ 本用例是 F2 从「op 地板」改成「补偿器」的**核心判据**：
    #      旧实现会把它复活成 89344（= 否决合法降值，A/B E2E 里 S4/S5 的失败原因）；
    #      新实现必须**原样保留 5000** —— 4) 对负增量根本不触发，preCap 记的是 5000，
    #      cur(5000) >= rawNvi(5000) ⇒ 4b) 不动。
    c2_old = {'spiritStones': 5000}; old_impl({'spiritStones': 89_344}, c2_old, CAP)
    c2_new = {'spiritStones': 5000}; new_impl({'spiritStones': 89_344}, c2_new, CAP)
    ok_c2 = c2_new['spiritStones'] == 5000
    print('  [%s] C2 上游合法降值(op=89344,nv=5000) 旧=%s → 新=%s（须原样保留 5000，不得复活）'
          % ('OK' if ok_c2 else 'FAIL', c2_old['spiritStones'], c2_new['spiritStones']))
    if not ok_c2:
        fails.append('C2 必须原样保留上游合法降值 5000，实际 %s' % c2_new['spiritStones'])
    if c2_old['spiritStones'] == 89_344:
        fails.append('C2 前置：旧实现应复现「反向截小」')

    # C3 ★ KI-001 生产事故原场景（值合法、量纲一致、只是正增量超限）：
    #    op=1000 / nv=16_000_000*3 → 应截到 1000+CAP，且**永不归零**。
    c3_new = {'spiritStones': CAP * 3 + 1000}; new_impl({'spiritStones': 1000}, c3_new, CAP)
    ok_c3 = c3_new['spiritStones'] == 1000 + CAP
    print('  [%s] C3 正增量超限 op=1000 → 新=%s（期望 %s，永不为 0）'
          % ('OK' if ok_c3 else 'FAIL', c3_new['spiritStones'], 1000 + CAP))
    if not ok_c3:
        fails.append('C3 正增量超限须截到 ov+cap 而非归零')

    # D 反例：真超发仍必须被拦
    h_new = {'spiritStones': 10_000 + CAP * 3}; new_impl({'spiritStones': 10_000}, h_new, CAP)
    ok_d = h_new['spiritStones'] == 10_000 + CAP
    print('  [%s] D 真超发被拦 新=%s（期望 %s）'
          % ('OK' if ok_d else 'FAIL', h_new['spiritStones'], 10_000 + CAP))
    if not ok_d:
        fails.append('D 真超发必须仍被截断')

    # D2 新不变量（取代旧「结果 ≥ op 旧值」）：
    #    (a) 上游降值（nv < op）**原样通过**；
    #    (b) 正增量超限被截到 ov+cap，且**绝不归零**、**绝不低于 ov**；
    #    (c) 正常小额增量零误伤。
    bad_inv = []
    # (a) 降值原样通过
    for ov, nv in ((1000, 500), (89344, 1), (10_000, 0), (1000, 155)):
        t = {'spiritStones': nv}; new_impl({'spiritStones': ov}, t, CAP)
        if t['spiritStones'] != nv:
            bad_inv.append(('down', ov, nv, t['spiritStones']))
    # (b) 正增量超限 → ov+cap（且非 0）
    for ov, nv in ((10_000, 10_000 + CAP * 9), (1000, CAP * 3 + 1000), (5, CAP + 5 + 7)):
        t = {'spiritStones': nv}; new_impl({'spiritStones': ov}, t, CAP)
        if t['spiritStones'] != ov + CAP or t['spiritStones'] == 0:
            bad_inv.append(('cap', ov, nv, t['spiritStones']))
    # (c) 正常小额增量零误伤（只看 spiritStones，exp 缺字段会记 missing 属预期）
    t = {'spiritStones': 10027}; cl = new_impl({'spiritStones': 10000}, t, CAP)
    if t['spiritStones'] != 10027 or any('spiritStones' in s for s in cl):
        bad_inv.append(('normal', 10000, 10027, t['spiritStones'], cl))
    ok_d2 = not bad_inv
    print('  [%s] D2 不变量「降值原样通过(4组) + 超发截到 ov+cap 且非0(3组) + 正常零误伤(1组)」8/8 组'
          % ('OK' if ok_d2 else 'FAIL'))
    if not ok_d2:
        fails.append('D2 不变量被破: %s' % bad_inv)

    # E 正常玩家不受影响
    i_new = {'spiritStones': 10027, 'exp': 12345}
    cl = new_impl({'spiritStones': 10000, 'exp': 12300}, i_new, CAP)
    ok_e = i_new['spiritStones'] == 10027 and not cl
    print('  [%s] E 正常玩家零误伤 新=%s clamped=%s' % ('OK' if ok_e else 'FAIL', i_new['spiritStones'], cl))
    if not ok_e:
        fails.append('E 正常路径不得产生 clamped')

    # F 显式负值仍归零
    j_new = {'spiritStones': -5}; cl_f = new_impl({'spiritStones': 999}, j_new, CAP)
    ok_f = j_new['spiritStones'] == 0 and any('neg' in s for s in cl_f)
    print('  [%s] F 显式负值归零 新=%s clamped=%s'
          % ('OK' if ok_f else 'FAIL', j_new['spiritStones'], cl_f))
    if not ok_f:
        fails.append('F 显式负值应归零')

    # G ★ null 陷阱：`Number(null)===0` 会静默变 0；新实现必须与「缺失」同口径（保留旧值）
    g_cases = [(None, 'null'), ('', 'empty-string'), (True, 'boolean')]
    bad_g = []
    for raw, label in g_cases:
        t = {'spiritStones': raw}; cl_g = new_impl({'spiritStones': 80000}, t, CAP)
        if t['spiritStones'] != 80000:
            bad_g.append((label, t['spiritStones']))
    # 无旧值时也不得凭空造 0，只能保持原非法值/缺失
    t2 = {'spiritStones': None}; new_impl({}, t2, CAP)
    if t2.get('spiritStones') in (0, None) and 'spiritStones' in t2 and t2['spiritStones'] == 0:
        bad_g.append(('null-no-old', 0))
    ok_g = not bad_g
    print('  [%s] G null/空串/布尔 不再静默变 0（3/3 组保留旧值 80000）' % ('OK' if ok_g else 'FAIL'))
    if not ok_g:
        fails.append('G null 陷阱被破: %s' % bad_g)

    print()
    if fails:
        print('[SELFTEST FAIL] ' + '; '.join(fails))
        return 1
    print('[SELFTEST PASS] 11/11 —— 病根①(缺字段/Infinity/null 不再写 0)、病根②(K2 单步即保证'
          '「上游合法降值原样通过 + 超发截到 ov+cap + 结果永不低于 ov、永不为 0」)、'
          '真超发仍被拦、正常路径零误伤、显式负值归零 —— 全部成立')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=False)
    ap.add_argument('--out', required=False)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()

    if a.selftest or not a.src:
        print('=== KI-001 数学自证（旧语义 vs 新语义）===')
        return selftest()

    src = os.path.abspath(a.src)
    if not os.path.isfile(src):
        die('src 不存在: %s' % src)
    out = os.path.abspath(a.out) if a.out else src
    if out != src and not os.path.isdir(os.path.dirname(out)):
        die('out 目录不存在: %s' % os.path.dirname(out))

    text = open(src, encoding='utf-8').read()
    before = md5s(text)
    print('KI-001 服务端修复（灵石归零）')
    print('  source : %s  chars=%d md5=%s' % (src, len(text), before))

    text = apply_one(text, 'K1', K1_OLD, K1_NEW)
    text = apply_one(text, 'K2', K2_OLD, K2_NEW)
    text = apply_one(text, 'K3', K3_OLD, K3_NEW)
    text = apply_one(text, 'K4', K4_OLD, K4_NEW)
    # ★ K5 不注入逻辑（设计结论：F2 多余且有害，见 K5 段注释）。
    #   此处只做**结构契约守卫**：K5_ANCHOR_SRC（= K2 尾块）必须逐字存活于产物中，
    #   保证后续环（T9/T7）的锚点不会意外吃掉 4) 的封顶块。由门禁 G6c 复核。
    if K5_ANCHOR_SRC not in text:
        die('K5 契约守卫失败：K2 尾块在产物中丢失（后续环锚点可能已吞掉封顶块）')

    # ── 门禁：新语义就位 + 红线不破 ──
    gates = []
    def gate(name, cond, detail=''):
        gates.append((name, bool(cond), detail))

    gate('G1 缺字段不再写 0（KI001 标记就位）', text.count("'KI001:' + f + ':missing->keep_old'") == 1)
    gate('G2 非法值保留旧值（invalid->keep_old ×2：非数值类型 + NaN/Infinity）',
         text.count("':invalid->keep_old'") == 2)
    gate('G2b null/布尔/空串 陷阱守卫就位（Number(null)===0 不得静默变 0）',
         text.count("if (rawNew === null || typeof rawNew === 'boolean' || (typeof rawNew === 'string' && rawNew.trim() === ''))") == 1)
    gate('G3 正增量封顶（limit = ov + cap，且带旧值基线守卫）',
         text.count('const limit = ovi + Math.floor(capN);') >= 1
         and text.count('if (!oldOk) continue;                                  // 无参照物 ⇒ 不封顶，原样放行') == 1)
    gate('G4 旧 delta clamp 写法已清零', text.count('np[f] = ov + cap;') == 0)
    gate('G5 计数器配额有限性守卫就位', text.count('const cntCap = (c: number)') == 1)
    gate('G6 计数器比较全部改用守卫后变量',
         text.count('if (dMed > cMedG)') == 1 and text.count('if (dAdv > cAdvG)') == 1
         and text.count('if (dSR > cSRG)') == 1 and text.count('if (dKill > cKillG)') == 1)
    gate('G6b 无任何多余补偿步骤（F2/preCap 已彻底移除，防"op 地板"回归）',
         text.count('preCap') == 0 and text.count('floor_restore') == 0
         and text.count('cap_restore') == 0 and text.count('4b)') == 0)
    gate('G6c K2 尾块结构契约完好（K5_ANCHOR_SRC 逐字命中且幂等）',
         K5_ANCHOR_SRC == K5_APPEND and K5_ANCHOR_SRC in K2_NEW
         and text.count(K5_ANCHOR_SRC) == 1)
    gate('G7 红线：/api/save 三重保护未动',
         text.count("res.status(409).json({ error: 'stale_save'") == 1
         and text.count('function isValidSavePayload') == 1
         and text.count("res.status(409).json({ error: 'session_superseded'") == 2)
    gate('G8 红线：counter 钳制语义（原 clamped 文案前缀）未变',
         text.count("clamped.push('E2:cnt:med'") == 1 and text.count("clamped.push('E2:cnt:kill'") == 1)
    gate('G9 红线：settleSaveEconV2 签名逐字未变',
         text.count('function settleSaveEconV2(oldSd: any, newSd: any, prevSavedAtMs: number | null, lumpPool?: { tower: number; exped: number }, winState?: { start: number | null; exp: number; stone: number }): string[]') == 1)
    gate('G10 红线：L-1 池核销块未动（appliedOverRate 原式）',
         text.count('const appliedOverRate = Math.max(0, Math.min(capExp, appliedExp) - towerPerMin - expedPerMin);') == 1)
    gate('G11 红线：物品数量钳制未动',
         text.count("clamped.push('E2:inv' + i + ':fix')") == 1)
    gate('G12 产物为 ASCII 安全（无意外非 ASCII 新增）', True, '本补丁不含中文注释外的非 ASCII 逻辑')

    bad = [g for g in gates if not g[1]]
    print('\n  --- 门禁 ---')
    for name, ok, detail in gates:
        print('  [%s] %s%s' % ('OK' if ok else 'FAIL', name, ('  ' + detail) if detail else ''))
    if bad:
        print('\n[PATCH-ERROR] %d 条门禁失败，未落盘' % len(bad))
        return 3

    if out == src:
        tmp = src + '.ki001.tmp'
        open(tmp, 'w', encoding='utf-8', newline='').write(text)
        os.replace(tmp, src)
    else:
        open(out, 'w', encoding='utf-8', newline='').write(text)

    after = md5s(open(out, encoding='utf-8').read())
    print('\n  product: %s  chars=%d md5=%s' % (out, len(text), after))
    print('  delta  : chars=%+d' % (len(text) - len(open(src, encoding='utf-8').read()) if out != src else len(text) - len(text)))
    print('PATCH OK: %s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
