#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
srv_patch_numbal_dicts.py -- v28 数值重规划：服务端 GM 字典 game-dicts.json 的 arts 数值对齐

背景
  game-dicts.json 是服务端 GM 参考字典（`loadGameDicts()` 只把 `items` 合进 GM 物品总表，
  `arts` 仅经 /api/gm/dicts 暴露给 GM Pro，不参与任何战斗/结算）。客户端心法数值在
  bundle 的 is[] 数组里（由 yl_numbal_ext.py 的 YlxwArtBalance() 在加载时重算）。
  本脚本把字典里的 arts.effects 对齐到**同一套重规划结果**，避免 GM 视图与实际玩法不符。

重规划规则（与 yl_numbal_ext.py 的 YlxwArtBudgetOf/YlxwArtGate 完全一致）
  1) 预算按 (品级, 境界需求) 单元格取**实测均值**（BOSS 专属心法单独一档）；
  2) 门槛补偿：spiritualRoot ×1.15 / buildAffinity ×1.10 / sectId ×1.15（可叠乘）；
  3) 按原 effects 的各维度权重（attack 1 / defense 1.6 / hp 0.35 / spirit 2 / speed 1.8）
     把预算分摊回各维度 —— 只改「量级」，不改「侧重」；
  4) expRate 按品级统一：黄 0.10 / 玄 0.16 / 地 0.28 / 天 0.45。

设计纪律（照抄 srv_rename_dicts.py）
  · 纯文本 str.replace，**绝不** json.load → json.dump 回写（1.3MB 文件会产生巨量无意义 diff）；
  · 每处替换前后做计数断言；落盘后只读 json.load 校验合法性与数值正确性；
  · 支持 --dry-run（只体检不落盘）；默认原地改写 srv/game-dicts.json，可用 --out 另存。

用法
  python srv_patch_numbal_dicts.py --dry-run
  python srv_patch_numbal_dicts.py
  python srv_patch_numbal_dicts.py --out srv/game-dicts-numbal.json
"""
import argparse
import difflib
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, 'srv', 'game-dicts.json')

# (品级, realmRequirement) -> 攻击当量预算（实测均值，见 数值重规划案.md 第 3 节）
CELL_BUDGET = {
    ('黄', 'QiRefining'): 17,
    ('玄', 'QiRefining'): 73,
    ('地', 'GoldenCore'): 395,
    ('天', 'NascentSoul'): 3338,
    ('天', 'SpiritSevering'): 11134,
    ('天', 'DaoCombining'): 10003,
}
BOSS_BUDGET = 77650          # isHeavenEarthSoulArt（天地之魄 boss 掉落）单独一档
GRADE_FALLBACK = {'黄': 17, '玄': 73, '地': 395, '天': 10003}
EXPRATE = {'黄': 0.10, '玄': 0.16, '地': 0.28, '天': 0.45}
W = {'attack': 1, 'defense': 1.6, 'hp': 0.35, 'spirit': 2, 'speed': 1.8}

# 期望的「重规划前」单元格均值（用于断言设计表确实来自实测数据）
EXPECT_PRE_MEAN = {
    ('黄', 'QiRefining'): 17.2,
    ('玄', 'QiRefining'): 73.4,
    ('地', 'GoldenCore'): 394.9,
    ('天', 'NascentSoul'): 3338.3,
    ('天', 'SpiritSevering'): 11134.4,
    ('天', 'DaoCombining'): 10003.0,
}
EXPECT_PRE_BOSS_MEAN = 77650.0
MEAN_TOL = 1.0               # 均值容差（±1 攻击当量）


def val(effects):
    return sum((effects.get(k) or 0) * w for k, w in W.items())


def gate_mult(a):
    m = 1.0
    if a.get('spiritualRoot'):
        m *= 1.15
    if a.get('buildAffinity'):
        m *= 1.10
    if a.get('sectId'):
        m *= 1.15
    return m


def budget_of(a):
    if a.get('isHeavenEarthSoulArt'):
        return BOSS_BUDGET
    b = CELL_BUDGET.get((a['grade'], a.get('realmRequirement')))
    if b is None:
        b = GRADE_FALLBACK.get(a['grade'], 17)
    return b


def new_effects(a):
    """返回 (新 effects dict, 新 expRate) —— 保留原 key 顺序与侧重。"""
    eff = a.get('effects') or {}
    stats = ['attack', 'defense', 'hp', 'spirit', 'speed']
    budget = budget_of(a) * gate_mult(a)
    prof = {k: (eff.get(k) or 0) * W[k] for k in stats}
    wsum = sum(prof.values())
    out = {}
    for k in eff:                       # 保持原顺序
        if k in W:
            if wsum > 0 and eff.get(k):
                out[k] = max(1, int(round(budget * (prof[k] / wsum) / W[k])))
            elif eff.get(k):
                out[k] = 1
        elif k == 'expRate':
            out[k] = EXPRATE.get(a['grade'], 0.10)
        else:
            out[k] = eff[k]         # 未知字段原样保留
    return out


def fmt_value(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        s = repr(round(v, 3))
        return s
    return json.dumps(v, ensure_ascii=False)


def render_effects(eff):
    """按 game-dicts.json 的既有格式（indent=1，键行 4 空格，闭合 3 空格）渲染 effects **对象本体**。"""
    lines = ['{']
    items = list(eff.items())
    for i, (k, v) in enumerate(items):
        lines.append('    "%s": %s%s' % (k, fmt_value(v), ',' if i < len(items) - 1 else ''))
    lines.append('   }')
    return '\n'.join(lines)


def find_object_end(text, open_idx):
    """从 text[open_idx] == '{' 起做括号匹配，返回闭合 '}' 的下标。"""
    depth = 0
    q = None
    esc = False
    for i in range(open_idx, len(text)):
        c = text[i]
        if q:
            if esc:
                esc = False
                continue
            if c == '\\':
                esc = True
                continue
            if c == q:
                q = None
            continue
        if c in ('"', "'"):
            q = c
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i
    return -1


def md5_bytes(b):
    return hashlib.md5(b).hexdigest()


def main():
    ap = argparse.ArgumentParser(description="Align game-dicts.json arts to the v28 rebalance.")
    ap.add_argument('--src', default=DEFAULT, help='pristine baseline (default: %(default)s)')
    ap.add_argument('--out', default=DEFAULT, help='output path (default: in-place)')
    ap.add_argument('--dry-run', action='store_true', help='只体检，不落盘')
    args = ap.parse_args()

    src_path, out_path = args.src, args.out
    if not os.path.isfile(src_path):
        sys.stderr.write('FAIL: source not found: %s\n' % src_path)
        return 1

    with open(src_path, 'rb') as f:
        raw = f.read()
    bom = raw.startswith(b'\xef\xbb\xbf')
    text = raw.decode('utf-8')

    print('=== game-dicts.json arts 数值对齐 (v28) ===')
    print('  src  : %s' % src_path)
    print('  bytes=%d  md5=%s  BOM=%s' % (len(raw), md5_bytes(raw), bom))

    doc = json.loads(text)                      # 只读
    arts = doc['arts']
    print('  arts=%d' % len(arts))

    # 幂等保护：JSON 不能写注释，所以用「重规划前均值核对」充当二次处理检测 ——
    # 一旦本补丁已生效，下面的 EXPECT_PRE_MEAN 断言必然失败（并给出明确提示）。

    # ---- 1) 断言设计表来自实测数据 ----
    print('  --- 重规划前单元格均值核对 ---')
    for key, exp in EXPECT_PRE_MEAN.items():
        grp = [a for a in arts if not a.get('isHeavenEarthSoulArt')
               and (a['grade'], a.get('realmRequirement')) == key]
        if not grp:
            sys.stderr.write('FAIL: 单元格 %s 无成员\n' % (key,))
            return 1
        m = sum(val(a.get('effects') or {}) for a in grp) / len(grp)
        ok = abs(m - exp) <= MEAN_TOL
        print('    [%s] %-22s n=%-3d mean=%.1f  expect=%.1f' %
              ('OK' if ok else 'FAIL', str(key), len(grp), m, exp))
        if not ok:
            sys.stderr.write(
                'FAIL: 单元格 %s 均值 %.1f 与设计表 %.1f 不符\n'
                '      （若源文件已被本补丁处理过，请用 pristine 备份重跑）\n' % (key, m, exp))
            return 1
    boss = [a for a in arts if a.get('isHeavenEarthSoulArt')]
    bm = sum(val(a.get('effects') or {}) for a in boss) / len(boss)
    print('    [%s] %-22s n=%-3d mean=%.1f  expect=%.1f' %
          ('OK' if abs(bm - EXPECT_PRE_BOSS_MEAN) <= MEAN_TOL else 'FAIL',
           'BOSS', len(boss), bm, EXPECT_PRE_BOSS_MEAN))
    if abs(bm - EXPECT_PRE_BOSS_MEAN) > MEAN_TOL:
        sys.stderr.write('FAIL: BOSS 档均值不符\n')
        return 1

    # ---- 2) 逐条纯文本替换（按 id 定位，括号匹配找 effects 对象）----
    new_text = text
    replaced = 0
    unchanged = 0
    for a in arts:
        eff = a.get('effects') or {}
        if not eff:
            unchanged += 1
            continue
        ne = new_effects(a)
        if ne == eff:
            unchanged += 1
            continue
        key = '"id": "%s"' % a['id']
        n = new_text.count(key)
        if n != 1:
            sys.stderr.write('FAIL: 心法 id 锚点 %s 出现 %d 次（期望 1）\n' % (a['id'], n))
            return 1
        start = new_text.index(key)
        ekey = '"effects": {'
        epos = new_text.index(ekey, start)
        ob = epos + len('"effects": ')
        oe = find_object_end(new_text, ob)
        if oe < 0:
            sys.stderr.write('FAIL: 心法 %s 的 effects 对象未闭合\n' % a['id'])
            return 1
        old_block = new_text[ob:oe + 1]
        new_block = render_effects(ne)          # 对象本体（不含 '"effects": ' 前缀）
        # 反向断言：old_block 必须能被 json 解析回原 effects
        if json.loads(old_block) != eff:
            sys.stderr.write('FAIL: 心法 %s 的 effects 文本解析结果与 json.load 不一致\n' % a['id'])
            return 1
        if json.loads(new_block) != ne:
            sys.stderr.write('FAIL: 心法 %s 的新 effects 渲染不可逆\n' % a['id'])
            return 1
        new_text = new_text[:ob] + new_block + new_text[oe + 1:]
        replaced += 1

    print('  --- 已重算心法 %d 本（另有 %d 本原值已等于新值，无需改写）---'
          % (replaced, len(arts) - replaced))
    if replaced + unchanged != len(arts):
        sys.stderr.write('FAIL: 重算本数 %d + 未变 %d != arts 总数 %d\n'
                         % (replaced, unchanged, len(arts)))
        return 1

    # ---- 3) 替换后断言 ----
    if new_text.count('"effects": {') != text.count('"effects": {'):
        sys.stderr.write('FAIL: effects 对象个数发生变化\n')
        return 1
    if len(new_text.encode('utf-8')) - len(raw) > 20000:
        sys.stderr.write('FAIL: 体积变化异常（>20KB）\n')
        return 1

    chk = json.loads(new_text)                  # 只读校验
    for a, b in zip(arts, chk['arts']):
        assert a['id'] == b['id']
        exp = new_effects(a)
        if b.get('effects') != exp:
            sys.stderr.write('FAIL: 落盘前校验 %s effects 不符\n' % a['id'])
            return 1
        for f in ('name', 'grade', 'cost', 'realmRequirement', 'description'):
            if a.get(f) != b.get(f):
                sys.stderr.write('FAIL: 字段 %s 被误改 (%s)\n' % (f, a['id']))
                return 1
    print('  [OK] json.load 校验通过（只读，未回写）；id/name/grade/cost/realmRequirement 未被改动')

    out_bytes = new_text.encode('utf-8')
    old_lines = text.split('\n')
    new_lines = new_text.split('\n')
    changed = [l for l in difflib.unified_diff(old_lines, new_lines, lineterm='', n=0)
               if (l.startswith('+') or l.startswith('-'))
               and not l.startswith('+++') and not l.startswith('---')]
    print('  新 bytes=%d  md5=%s  差异行数=%d' % (len(out_bytes), md5_bytes(out_bytes), len(changed)))

    if args.dry_run:
        print('  (--dry-run 模式：不落盘)')
        return 0

    with open(out_path, 'wb') as f:
        f.write(out_bytes)
    print('  已落盘: %s' % out_path)
    with open(out_path, 'rb') as f:
        disk = f.read()
    if md5_bytes(disk) != md5_bytes(out_bytes):
        sys.stderr.write('FAIL: 落盘 md5 与预期不符\n')
        return 1
    print('  [OK] 落盘 md5 复核一致')
    return 0


if __name__ == '__main__':
    sys.exit(main())
