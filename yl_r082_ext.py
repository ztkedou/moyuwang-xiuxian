# -*- coding: utf-8 -*-
r"""
yl_r082_ext.py — R-082【上游复刻】洞府加「可收获 N 株灵草」提示条

需求（用户 R-082）
--------------------------------------------------------------------------
  上游 `a8f9810a` 的 `components/GrottoModal.tsx` 在「种植中的灵草」区顶部有一条提示条：

      {matureHerbsCount > 0 && (
        <div className="mb-3 px-3 py-2 rounded border border-green-700 bg-green-900/30 text-green-300 text-sm">
          可收获 {matureHerbsCount} 株灵草
          {grotto.autoHarvest ? '（自动收获已开启）' : '，可一键收获'}
        </div>
      )}

  本仓现状（实测）：文案「可收获」全仓 4 处 ——
    ① 洞府面板「种植中的灵草」标题右侧徽标 `[M," 可收获"]`（有，但只是个绿胶囊数字）
    ② 灵田面板成熟徽标 `e.jsx(Ir,{size:12}),"可收获"`（另一系统，不动）
    ③ 种植槽满 toast「…可收获成熟灵草、扩地或升级洞府。」（`yl_049_ext.py` 的锚点面，不动）
    ④ 种植成功 toast「…预计 X 后可收获 N 个。」（不动）
  ⇒ 「自动收获已开启」这类**状态提示条**全仓 0 处 —— 就是本需求要补的那条。

本模块动作（1 处就地插入，零新增网络调用）
--------------------------------------------------------------------------
  在洞府「种植中的灵草」卡片头部行之后、灵草列表之前，插入上游同款提示条：

      M>0 && <div class="mb-3 px-3 py-2 rounded border border-green-700 bg-green-900/30 text-green-300 text-sm">
                可收获 {M} 株灵草 {T.autoHarvest ? '（自动收获已开启）' : '，可一键收获'}
              </div>

  · `M`  = 该面板既有的 `O.useMemo(... plantedHerbs.filter(q=>g>=q.harvestTime).length)` = **成熟数量**
    （与标题徽标、批量收获按钮同源，不新算一遍）。
  · `T`  = 面板既有的洞府 state；`T.autoHarvest` 即「自动收获开关」卡片读的同一个字段。

CSS 类（★ 逐个在预生成 CSS `build/assets/index-ZuV-l8Gt.css` 里 grep 确认存在，不做新类）
--------------------------------------------------------------------------
  `mb-3` ✓ / `px-3` ✓ / `py-2` ✓ / `rounded` ✓ / `border-green-700` ✓ /
  `bg-green-900/30` ✓ / `text-green-300` ✓ / `text-sm` ✓  —— 与上游完全一致，无需等价替换。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 只新建本文件；不改 build_v26n.py / localtest/* / srv/index_v28.ts / deploy_v28/*。
  · 锚点是**纯 ASCII 边界**（`"]})]}),e.jsx("div",{className:"space-y-3",children:T.plantedHerbs.map(`），
    避开中文；插入文本里的中文写成 \uXXXX（落盘为 UTF-8，与 base 内容同形态）。
  · 不碰「自动收获开关卡片」（`yl_grotto087_ext.py` G13 锚点在其尾部）、不碰灵田徽标、
    不碰 `yl_049_ext.py` 的种植槽满 toast 锚点。
  · ★ 接线顺序：必须排在 grotto087 / r049 / r050 **之后**（锚点是它们的最终产物；建议紧接 r074 之后）。
"""

import re

INJECT_JS = ''          # 本模块只做「就地插入」，不需要额外注入块

# --------------------------------------------------------------------------- 锚点

# 洞府面板「种植中的灵草」卡片：头部行结束 -> 灵草列表开始（纯 ASCII，全仓唯一）
GROTTO_OLD = '"]})]}),e.jsx("div",{className:"space-y-3",children:T.plantedHerbs.map('

# 上游同款提示条（中文写成 \uXXXX，落盘即 UTF-8）
#   可收获 / 株灵草 / （自动收获已开启） / ，可一键收获
GROTTO_NEW = (
    '"]})]}),M>0&&e.jsxs("div",{className:"mb-3 px-3 py-2 rounded border border-green-700 '
    'bg-green-900/30 text-green-300 text-sm",children:["\u53ef\u6536\u83b7 ",M," '
    '\u682a\u7075\u8349",T.autoHarvest?"\uff08\u81ea\u52a8\u6536\u83b7\u5df2\u5f00'
    '\u542f\uff09":"\uff0c\u53ef\u4e00\u952e\u6536\u83b7"]}),'
    'e.jsx("div",{className:"space-y-3",children:T.plantedHerbs.map('
)

# 提示条样式串（用作门禁，证明确实注入了上游同款类）
HINT_CLASS = ('mb-3 px-3 py-2 rounded border border-green-700 '
              'bg-green-900/30 text-green-300 text-sm')

# 冻结面：洞府面板既有元素（本模块只新增、不改它们）
FREEZE_BADGE = 'children:[M," \u53ef\u6536\u83b7"]'                    # 标题右侧「N 可收获」徽标
FREEZE_BULK = 'children:[e.jsx(Ir,{size:16}),"\u6279\u91cf\u6536\u83b7"]'  # 批量收获按钮
FREEZE_AUTO = '"\u81ea\u52a8\u6536\u83b7",T.autoHarvest&&e.jsx("span"'  # 自动收获开关卡片
FREEZE_FARM = 'e.jsx(Ir,{size:12}),"\u53ef\u6536\u83b7"'                # 灵田「可收获」徽标
FREEZE_TOAST_SLOT = '\u53ef\u6536\u83b7\u6210\u719f\u7075\u8349\u3001\u6269\u5730\u6216\u5347\u7ea7\u6d1e\u5e9c'  # yl_049 锚点面


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    zh = ctx['zh']

    # 手滑护栏：插入串必须含「可收获 / 株灵草 / 自动收获已开启」三要素
    if ('\u53ef\u6536\u83b7' not in GROTTO_NEW
            or '\u682a\u7075\u8349' not in GROTTO_NEW
            or '\u81ea\u52a8\u6536\u83b7\u5df2\u5f00\u542f' not in GROTTO_NEW):
        raise AssertionError('r082 插入串异常：缺「可收获 / 株灵草 / 自动收获已开启」')

    p.replace('r082-grotto-hint', GROTTO_OLD, GROTTO_NEW, expect=1,
              note='洞府「种植中的灵草」区补上游同款「可收获 N 株灵草」提示条')

    gates = [
        # ================= 本模块改动 =================
        ('R82·洞府提示条已注入(样式)', HINT_CLASS, 1, '==', '上游同款类，CSS 已确认存在'),
        ('R82·提示条仅成熟>0显示',     'M>0&&e.jsxs("div",{className:"mb-3 px-3 py-2', 1, '==', ''),
        ('R82·提示条显示成熟数量',     '\u53ef\u6536\u83b7 ",M," \u682a\u7075\u8349"', 1, '==', '与标题徽标同源'),
        ('R82·提示条接自动收获态',
         'T.autoHarvest?"\uff08\u81ea\u52a8\u6536\u83b7\u5df2\u5f00\u542f\uff09":"\uff0c\u53ef\u4e00\u952e\u6536\u83b7"',
         1, '==', '与开关卡片同字段'),
        # ================= 冻结：洞府 / 灵田既有元素一个字不动 =================
        ('冻结·标题「N 可收获」徽标未动', FREEZE_BADGE, 1, '==', ''),
        ('冻结·批量收获按钮未动',        FREEZE_BULK, 1, '==', ''),
        ('冻结·自动收获开关卡片未动',    FREEZE_AUTO, 1, '==', 'grotto087 G13 锚区'),
        ('冻结·灵田「可收获」徽标未动',  FREEZE_FARM, 1, '==', '另一系统，本环不碰'),
        ('冻结·种植槽满 toast 未动',     FREEZE_TOAST_SLOT, 1, '==', 'yl_049 锚点面'),
        ('冻结·种植成功 toast 未动',     '\u540e\u53ef\u6536\u83b7 ', 1, '==', ''),
        # 「可收获」总数：改动前 4 处（洞府徽标 / 灵田徽标 / 两条 toast）+ 本环提示条 1 处 = 5
        ('R82·「可收获」总数 = 4+1', '\u53ef\u6536\u83b7', 5, '==', '4 处既有 + 本环新增提示条 1 处'),
    ]
    return gates
