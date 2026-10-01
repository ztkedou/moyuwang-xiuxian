# -*- coding: utf-8 -*-
r"""
yl_r013c_ext.py — R-028 收尾（客户端环 r013c）：YlxwQMile 展示表与服务端新表对齐

需求来源
--------------------------------------------------------------------------
  R-028 用户拍板：传承石**移到最高档**（满活跃度才给），「最多一个月一个」。
  r013b（服务端）已把传承石 `legacy` 从 1,000 档移到 **2,310 档**，并把原 2,310 的
  `'仙品道具+称号'` 下移到 1,900 档保留（见 报告_r013b.md §4）。

  但客户端 `YlxwQMile`（在 `yl_t9quest_ext.py` 注入块内，econ2 曾改过）**仍停留旧口径**：
      1,000 extra = 传承石 ×1        （应清空）
      1,900 extra = ""              （应承接 仙品珍宝 ×1 · 称号「勤修不辍」）
      2,310 extra = 仙品珍宝 ×1·称号 （应改 传承石 ×1）
  ⇒ 不改则「服务端发 2,310、客户端显示 1,000」两端不一致。

★ 为什么**不**改 `yl_t9quest_ext.py`（二选一的取舍，结论：新建本模块）
--------------------------------------------------------------------------
  `yl_t9quest_ext.py` 的 `YlxwQMile` 表是 **econ2（yl_econ2_ext.py）的替换锚点**：
      econ2 的 `MILE_OLD` = 旧 3 档表（500/1000/1800，t9quest 原样产出），
            `MILE_NEW` = 新 5 档表（本模块要改的就是 MILE_NEW 的产物）。
  · 若**原地**改 t9quest 的表 → econ2 的 `MILE_OLD` 锚点 count 立即变 0
    ⇒ `p.replace(..., expect=1)` 抛 PatchError ⇒ **整条客户端链构建失败**（不是门禁红，是硬崩）。
  · t9quest 的表是「3 档」形态、econ2 负责「3→5 档」，**职责分离**；r013c 是「5 档 extra 列」
    语义，天然属于 econ2 **之后**的一环。
  ⇒ 选**新建本模块**，挂在 V28_MODULES 的 **econ2 之后、numbal 之前**做覆盖式替换。

★ 跨模块门禁（约束权移交，依 dungeon085 / eco085 先例）
--------------------------------------------------------------------------
  econ2 的 3 条门禁（R28·新 5 档·1000/1900/2310）把 `extra` 值写进了断言串。
  本模块改掉 extra ⇒ 那 3 条在**全链装配后的最终文本**上必然 FAIL
  （build_v26n 把所有模块的 gate 汇总在最终 `out` 上求值）。
  ⇒ 已就地**放宽** econ2 那 3 条为「只锁档位数值前缀（tier/name/base/ticket）」，extra 语义
    移交本模块断言（与 yl_dungeon085_ext.py:261 / yl_eco085_ext.py:368 同款处理）。

硬约束
--------------------------------------------------------------------------
  · 纯展示层：只改 `YlxwQMile` 数据表的 `extra` 列，不新增网络调用、不改任何逻辑。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 不写 build/assets/、不改 build_v26n.py / chain_build.py / srv/index_v28.ts。
  · 本模块无 INJECT_JS（纯就地替换，不需要注入新函数）。
"""

import re


def _rows_zh():
    """返回 (OLD_RAW, NEW_RAW)：中文原形；apply() 内统一走 zh() 转义，
    与 econ2 MILE_NEW 的 zh() 产物逐字对齐（已实测 zh(OLD_RAW) == econ2.MILE_NEW）。"""
    old = (
        'var YlxwQMile = [\n'
        '  { tier: 500,  name: "勤修·初", base: 10000, ticket: 4,  extra: "" },\n'
        '  { tier: 1000, name: "勤修·中", base: 20000, ticket: 9,  extra: "传承石 ×1" },\n'
        '  { tier: 1500, name: "勤修·进", base: 30000, ticket: 14, extra: "" },\n'
        '  { tier: 1900, name: "勤修·深", base: 40000, ticket: 21, extra: "" },\n'
        '  { tier: 2310, name: "勤修·满", base: 60000, ticket: 30, extra: "仙品珍宝 ×1 · 称号「勤修不辍」" }\n'
        '];'
    )
    new = (
        'var YlxwQMile = [\n'
        '  { tier: 500,  name: "勤修·初", base: 10000, ticket: 4,  extra: "" },\n'
        '  { tier: 1000, name: "勤修·中", base: 20000, ticket: 9,  extra: "" },\n'
        '  { tier: 1500, name: "勤修·进", base: 30000, ticket: 14, extra: "" },\n'
        '  { tier: 1900, name: "勤修·深", base: 40000, ticket: 21, extra: "仙品珍宝 ×1 · 称号「勤修不辍」" },\n'
        '  { tier: 2310, name: "勤修·满", base: 60000, ticket: 30, extra: "传承石 ×1（每月限领）" }\n'
        '];'
    )
    return old, new


def apply(p, ctx):
    """p = Patcher（文本已含 t9quest + econ2 等全部前置模块）；ctx = {'zh': zh, ...}"""
    zh = ctx['zh']

    old_raw, new_raw = _rows_zh()
    OLD = zh(old_raw)
    NEW = zh(new_raw)

    # 0) 覆盖式替换：econ2 产出的 5 档表 → 新 extra 列（1000 清空 / 1900 承接 / 2310 改传承石）
    p.replace('r013c-mile-extra', OLD, NEW, expect=1,
              note='YlxwQMile extra 列对齐服务端 r013b（传承石移 2310 / 仙品珍宝下移 1900）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本环正向断言（extra 列新口径） =================
        ('R13c·周里程碑表仍唯一',      'var YlxwQMile = [', 1, '==', ''),
        ('R13c·1000 extra 已清空',     'tier: 1000, name: "\\u52e4\\u4fee\\u00b7\\u4e2d", base: 20000, ticket: 9,  extra: ""', 1, '==', '传承石已移走'),
        ('R13c·1900 承接仙品珍宝+称号', 'tier: 1900, name: "\\u52e4\\u4fee\\u00b7\\u6df1", base: 40000, ticket: 21, extra: "\\u4ed9\\u54c1\\u73cd\\u5b9d \\u00d71 \\u00b7 \\u79f0\\u53f7\\u300c\\u52e4\\u4fee\\u4e0d\\u8f8d\\u300d"', 1, '==', '原 2310 的展示串下移'),
        ('R13c·2310 extra 改传承石',   'tier: 2310, name: "\\u52e4\\u4fee\\u00b7\\u6ee1", base: 60000, ticket: 30, extra: "\\u4f20\\u627f\\u77f3 \\u00d71\\uff08\\u6bcf\\u6708\\u9650\\u9886\\uff09"', 1, '==', '与用户「最多一个月一个」一致'),
        # ================= 旧口径必须清零 =================
        ('R13c·旧 1000 挂传承石已清零', 'tier: 1000, name: "\\u52e4\\u4fee\\u00b7\\u4e2d", base: 20000, ticket: 9,  extra: "\\u4f20\\u627f\\u77f3 \\u00d71"', 0, '==', ''),
        ('R13c·旧 1900 extra 空已清零', 'tier: 1900, name: "\\u52e4\\u4fee\\u00b7\\u6df1", base: 40000, ticket: 21, extra: ""', 0, '==', ''),
        ('R13c·旧 2310 挂仙品已清零',   'tier: 2310, name: "\\u52e4\\u4fee\\u00b7\\u6ee1", base: 60000, ticket: 30, extra: "\\u4ed9\\u54c1\\u73cd\\u5b9d', 0, '==', ''),
        # ================= 冻结：档位数值 / 展示组件 / 端点未动 =================
        ('R13c冻结·500 档未动',            'tier: 500,  name: "\\u52e4\\u4fee\\u00b7\\u521d", base: 10000, ticket: 4,  extra: ""', 1, '==', ''),
        ('R13c冻结·1500 档未动',           'tier: 1500, name: "\\u52e4\\u4fee\\u00b7\\u8fdb", base: 30000, ticket: 14, extra: ""', 1, '==', ''),
        ('R13c冻结·周满分 2310 未动',      'var YlxwQWeekMax = 2310;', 1, '==', ''),
        ('R13c冻结·里程碑卡组件未动',      'function YlxwQMileZone(', 1, '==', ''),
        ('R13c冻结·里程碑端点未动',        '"/quest/milestone"', 1, '==', ''),
        ('R13c冻结·extra 渲染仍在',        'm.ticket + (m.extra ?', 1, '==', 'extra 由卡片渲染，数据表改值即生效'),
    ]
    return gates
