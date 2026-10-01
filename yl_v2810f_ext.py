# -*- coding: utf-8 -*-
r"""yl_v2810f_ext.py -- 洞府灵草「配置信息缺失」兜底修复（0.8.10 · 需求 6b）

用户原话：
  「『**灵草【灵紫猴草】配置信息缺失，已按 600 灵石折算回收（每个 300 灵石）**』是什么意思；
     **若无该灵草就增加，或把洞府灵草全改为已有品种**，不要出现缺配置内容。」

=========================================================================== 这是什么（实证）
0.8.7 T4 给「洞府灵草收获」加了一条**懒兼容兜底**（`yl_grotto087_ext.py` 的 G14）：
    const _ = wn.find(Q=>Q.id===N.herbId)
           || wn.find(Q=>Q.id===String(N.herbId??"").replace(/^herb-/,""))
           || wn.find(Q=>Q.name===N.herbName);
    if (!_) { /* 折算回收：max(100, quantity*300) 灵石 */ }
三级查找（按 id / 去掉 `herb-` 前缀的 id / 按名字）**全落空**时，把该株灵草**按每个 300 灵石
折算回收**，并弹这条警告。

⇒ 实测：`灵紫猴草` 在**全仓**（`yl_*_ext.py` / `build/assets/*.js` / `srv/*.ts` /
  `srv/game-dicts.json` / `docs/`）**零命中** —— 它只存在于**某个玩家旧存档的
  `grotto.plantedHerbs[].herbName`**里。
⇒ 现役灵草表（客户端内嵌 20 种 + `game-dicts.json` `herbs` 20 条）里只有
  **`紫猴花`（id `purple-monkey-flower`）** —— `灵紫猴草` 是它被改名前的**旧名**。
⇒ 所以这不是「服务端配置缺失」，而是「**旧存档带着改名前的名字回来收菜**」。

=========================================================================== 改法（不动灵草表、不新增品种）
用户给了两条可选路径：「若无该灵草就增加」或「把洞府灵草全改为已有品种」。
本模块选**第三条更小侵入的路**：加一张**旧名 → 现名**的别名表，把查找链延长一级。
理由：
  · 新增一个「灵紫猴草」品种 ⇒ 要同时改客户端内嵌表 + `game-dicts.json` + 掉落/商店/图鉴，
    改动面大且会让一个**只该存在于历史存档**的名字变成正式品种；
  · 把洞府灵草「全改为已有品种」⇒ 要遍历改写玩家存档，属**破坏性迁移**；
  · 别名映射 ⇒ **一次 replace、零存档改写**：旧存档照样能收菜，收到的是**真实道具
    `紫猴花`**（进背包、可用、可卖），**不再出现「折算回收」与缺配置警告**。

别名表刻意**内联在替换点**（不新增模块级常量）：单点可核、不引入新的注入锚，
与 `yl_grotto087_ext.py` 的 G14 替换点**逐字咬合**（本模块排在 grotto087 之后）。

硬约束遵守：
  · 只新建本文件 + 修改 build_v26n.py 接线；**不写回 build/assets/**。
  · 注入块 zh() 后纯 ASCII；不含禁用模式 iframe/postMessage/XMLHttpRequest/auth_token/X-YL-。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
"""

import re

# --------------------------------------------------------------------------- 注入片段

# 原始查找链（`yl_grotto087_ext.py` G14_NEW 的产物形态，逐字；在链产物里 count==1）
OLD_FIND = (
    'const _=wn.find(Q=>Q.id===N.herbId)'
    '||wn.find(Q=>Q.id===String(N.herbId==null?"":N.herbId).replace(/^herb-/,""))'
    '||wn.find(Q=>Q.name===N.herbName);'
)

# 延长一级：旧名 → 现名别名表（表内为「旧存档里出现过的名字」→「现役灵草名」）
NEW_FIND = (
    'const __halias={"\u7075\u7d2b\u7334\u8349":"\u7d2b\u7334\u82b1"};'
    'const __hn=String(N.herbName==null?"":N.herbName);'
    'const __hnc=__halias[__hn]||__hn;'
    'const _=wn.find(Q=>Q.id===N.herbId)'
    '||wn.find(Q=>Q.id===String(N.herbId==null?"":N.herbId).replace(/^herb-/,""))'
    '||wn.find(Q=>Q.name===N.herbName)'
    '||wn.find(Q=>Q.name===__hnc);'
)

# 兜底警告文案（保留原文不动；别名命中后走的是正常收获路径，不再弹这条）
OLD_MSG = (
    'const __msg=`\u26a0\ufe0f \u7075\u8349\u3010${N.herbName}\u3011\u7684\u914d\u7f6e\u4fe1\u606f\u7f3a\u5931\uff0c'
    '\u5df2\u6309 ${__sv.toLocaleString()} \u7075\u77f3\u6298\u7b97\u56de\u6536\uff08\u6bcf\u4e2a 300 \u7075\u77f3\uff09\u3002`;'
)

# ★ 坑 2：gate 的 needle 落在**注入块内** ⇒ 必须写 `zh()` 之后的**转义形态**
#   （产物里是字面 `\u7075\u7d2b\u7334\u8349`，不是中文「灵紫猴草」）。
#   下面两个常量就是转义形态的 needle，用 r'' 防止 Python 先解一次。
_ND_OLDNAME = r'\u7075\u7d2b\u7334\u8349'                       # 灵紫猴草
_ND_MAP = r'{"\u7075\u7d2b\u7334\u8349":"\u7d2b\u7334\u82b1"}'  # {"灵紫猴草":"紫猴花"}


def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""
    zh = ctx['zh']

    # 1) 延长灵草查找链（旧名 → 现名）
    p.replace('v2810f-herb-alias', OLD_FIND, zh(NEW_FIND), expect=1,
              note='灵草查找链加一级「旧名→现名」别名表（灵紫猴草 → 紫猴花）')

    # ------------------------------------------------------------- 门禁
    gates = [
        ('6b·别名表已注入',            _ND_OLDNAME,                                      1, '==', '旧名（转义形态 needle）'),
        ('6b·现名映射为紫猴花',        _ND_MAP,                                          1, '==', ''),
        ('6b·原名兜底查找保留',        '||wn.find(Q=>Q.name===N.herbName)',              1, '==', '基线三级查找未删'),
        ('6b·别名兜底查找已加',        '||wn.find(Q=>Q.name===__hnc);',                  1, '==', '第四级：别名归一后按名找'),
        ('6b·空名安全化',              'const __hn=String(N.herbName==null?"":N.herbName);', 1, '==', '防 null 参与索引'),
        ('6b·折算回收兜底仍在',        'const __sv=Math.max(100,N.quantity*300);',        1, '==', '真·未知灵草仍有兜底（不删退路）'),
        # 基线未动断言
        ('6b·基线按 id 查找未动',      'const _=wn.find(Q=>Q.id===N.herbId)',             1, '==', ''),
        ('6b·基线去前缀查找未动',      '||wn.find(Q=>Q.id===String(N.herbId==null?"":N.herbId).replace(/^herb-/,""))', 1, '==', '整段唯一'),
    ]
    return gates
