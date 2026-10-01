# -*- coding: utf-8 -*-
r"""
yl_r037_ext.py — R-037 去掉自带「离线修炼」，只保留「挂机收益」

用户原话
--------------------------------------------------------------------------
  「游戏自带的有一个离线修炼，把这个去了，只保留"挂机收益"这一个离线功能」
  附图（聊天框）：
      `💤 你离线修炼了 28 分钟 · 获得 14959 修为 · 自动吸纳 413 灵石`

判定口径（已定，不要改）
--------------------------------------------------------------------------
  **方案 A —— 彻底删掉**（不是只隐藏消息）：
    · 回来时不再自动结算 修为 / 灵石；
    · 不再发那条「💤 你离线修炼了 …」消息；
    · 离线收益只剩「挂机收益」（服务端算、面板手动领取的那个）。

产物里的三个自带函数（都是**游戏自带代码**，非任何 yl 模块产物）
--------------------------------------------------------------------------
  · `Nw(t,r)` —— 离线结算「计算」：elapsedText / meditationExp / spiritStoneIncome
                 / grottoHerbs / lifespanSpent
  · `ww(t,r)` —— 离线结算「入账」：exp += meditationExp、spiritStones += spiritStoneIncome、
                 洞府灵草入账、寿命扣减
  · `Sw(t)`   —— 拼那条消息：💤 你离线修炼了 … · 获得 … 修为 · 自动吸纳 … 灵石（+ 洞府收获）

  触发点（**读档时**，全产物仅此一处调用）：
      let v=d,m=null;if(f>3e4){const b=Nw(d,f);v=ww(d,b),m=Sw(b)}
      其中 f>3e4 ⇒ 离线 ≥ 30s 才结算；m 非空才往 logs 落一条 type:"gain"。

本模块动作（3 处就地替换，锚点均已实测唯一）
--------------------------------------------------------------------------
  1) 触发点：删掉 `if(f>3e4){…}` 结算块 —— 回来不再结算、也不再落日志。
  2) `Sw`：删掉 💤 / 修为 / 灵石 三段文案（**保留「洞府收获」文案** —— 那是洞府面，非修炼面）。
  3) `ww`：删掉 `exp / spiritStones` 入账那一句（即需求所说的「修为/灵石入账那一段」）。

  ⇒ 改动后：`离线修炼` / `你离线修炼了` / `自动吸纳` 在产物中**归零**；
     `挂机收益`（`YlxwTOffline` + `/offline/report|claim`）与打坐/历练 **一字未动**。

未动 / 已报告（见交付报告）
--------------------------------------------------------------------------
  · `Nw` / `ww` 的**函数定义保留**（已不可达）。原因：`Nw`/`ww` 内含**共享**的
    「离线洞府灵草入账 + 离线寿命流逝」逻辑，删定义会连带移除这两项侧机制，超出本条范围；
    因触发点已删，二者不可达，无行为影响。
  · 服务端 `srv/index_v28.ts` **未动**：离线修炼是**纯客户端**结算（读档时用
    lastActiveTime 算），与服务端「挂机收益」(/offline/report|claim) 无关。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 只新建本文件；不改 build_v26n.py / localtest/*.py / srv/index_v28.ts / deploy_v28/*。
  · INJECT_JS 为空串（纯就地替换）⇒ 无 V28_BAN_PATTERNS 风险。
  · 每个 replace 带 expect=1（锚点唯一）。
"""

import re

INJECT_JS = ''          # 本模块只做就地替换，不需要注入块

# --------------------------------------------------------------------------- 锚点

# 1) 读档时的离线结算触发块（全产物唯一）
TRIGGER_OLD = 'let v=d,m=null;if(f>3e4){const b=Nw(d,f);v=ww(d,b),m=Sw(b)}'
TRIGGER_NEW = 'let v=d,m=null;/*R037*/'

# 2) Sw：离线修炼消息的三段文案（唯一；保留「洞府收获」）
MSG_OLD = (
    'if(r.push(`\U0001f4a4 \u4f60\u79bb\u7ebf\u4fee\u70bc\u4e86 ${t.elapsedText}`),'
    't.meditationExp>0&&r.push(`\u83b7\u5f97 ${t.meditationExp} \u4fee\u4e3a`),'
    't.spiritStoneIncome>0&&r.push(`\u81ea\u52a8\u5438\u7eb3 ${t.spiritStoneIncome} \u7075\u77f3`),'
    't.grottoHerbs.length>0){'
)
MSG_NEW = 'if(t.grottoHerbs.length>0){'

# 3) ww：修为 / 灵石入账那一句（唯一）
GRANT_OLD = (
    'const a={...t};'
    'a.exp=Math.min((a.exp||0)+r.meditationExp,(a.maxExp||100)*2),'
    'a.spiritStones=(a.spiritStones||0)+r.spiritStoneIncome;'
    'const l=[...a.inventory||[]];'
)
GRANT_NEW = 'const a={...t};const l=[...a.inventory||[]];'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置模块）；ctx = {'zh': zh, ...}"""
    zh = ctx['zh']

    # 锚点里是**字面中文/emoji**（bundle 里就是 UTF-8，不是 \uXXXX 转义）。
    # 这里做一次「替换串非空且含预期字样」的自检，防手滑写空。
    if '\u4f60\u79bb\u7ebf\u4fee\u70bc\u4e86' not in MSG_OLD:
        raise AssertionError('r037 MSG_OLD 异常：没找到「你离线修炼了」')
    if '\u4fee\u4e3a' not in MSG_OLD or '\u7075\u77f3' not in MSG_OLD:
        raise AssertionError('r037 MSG_OLD 异常：缺「修为/灵石」字样')
    if 'Nw(d,f)' not in TRIGGER_OLD or 'Sw(b)' not in TRIGGER_OLD:
        raise AssertionError('r037 TRIGGER_OLD 异常：缺 Nw/Sw 调用')

    # 1) 删掉离线结算触发块（修为/灵石/灵草/寿命 全部不再自动结算，也不再落日志）
    p.replace('r037-trigger', TRIGGER_OLD, TRIGGER_NEW, expect=1,
              note='读档离线结算触发块整段移除（彻底停用自带「离线修炼」）')

    # 2) 删掉 Sw 里「离线修炼」的三段文案（保留「洞府收获」）
    p.replace('r037-msg', MSG_OLD, MSG_NEW, expect=1,
              note='Sw 去掉 💤/修为/灵石 三段文案，保留洞府收获')

    # 3) 删掉 ww 里「修为/灵石入账」那一句
    p.replace('r037-grant', GRANT_OLD, GRANT_NEW, expect=1,
              note='ww 去掉 exp/spiritStones 入账（修为/灵石入账处）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 本模块改动 =================
        ('R37·离线结算触发已移除',   'let v=d,m=null;/*R037*/', 1, '==', '新形态'),
        ('R37·旧结算块已清零',       'if(f>3e4){const b=Nw(d,f);v=ww(d,b),m=Sw(b)}', 0, '==', '旧形态'),
        ('R37·旧结算阈值已清零',     'if(f>3e4)', 0, '==', '旧形态'),
        ('R37·旧入账调用已清零',     'v=ww(d,b)', 0, '==', '旧形态'),
        ('R37·旧消息调用已清零',     'm=Sw(b)', 0, '==', '旧形态'),
        ('R37·「离线修炼」文案清零', '\u79bb\u7ebf\u4fee\u70bc', 0, '==', 'Sw 内文案'),
        ('R37·「你离线修炼了」清零', '\u4f60\u79bb\u7ebf\u4fee\u70bc\u4e86', 0, '==', ''),
        ('R37·「自动吸纳」清零',     '\u81ea\u52a8\u5438\u7eb3', 0, '==', ''),
        ('R37·修为入账已清零',       'a.exp=Math.min((a.exp||0)+r.meditationExp', 0, '==', 'ww 内修为入账'),
        ('R37·灵石入账已清零',       'a.spiritStones=(a.spiritStones||0)+r.spiritStoneIncome', 0, '==', 'ww 内灵石入账'),
        ('R37·洞府收获文案保留',     '\u6d1e\u5e9c\u6536\u83b7', 1, '==', '洞府面文案，非修炼面'),
        # ================= 冻结：相邻功能一律不动 =================
        ('冻结·挂机收益入口仍在',    '\u6302\u673a\u6536\u76ca', 2, '==', '相邻离线功能，绝对不动'),
        ('冻结·挂机收益接口(report)', '/offline/report', 3, '==', ''),
        ('冻结·挂机收益接口(claim)',  '/offline/claim', 2, '==', ''),
        ('冻结·挂机收益面板未动',    'YlxwTOffline', 2, '==', ''),
        ('冻结·打坐灵石入账未动',    'w=$.spiritStones+__ylsq,__ylms=YlxwMedStone(__ylsq),', 1, '==', ''),
        ('冻结·打坐灵石因子未动',    'YlxwMedStone2(q,$.realmLevel,C)', 1, '==', 'R-024 形态'),
        ('冻结·打坐修为基座未动',    'Math.floor(f*10*(1+a.realmLevel*.15))', 1, '==', ''),
        ('冻结·历练面未动',          '\u5386\u7ec3\u6b21\u6570', 1, '==', ''),
        # ================= 冻结：明确「保留为不可达」的两处（透明声明） =================
        ('冻结·Nw 定义保留(不可达)',  'function Nw(t,r){', 1, '==', '内含共享的离线灵草/寿命逻辑，未删'),
        ('冻结·ww 定义保留(不可达)',  'function ww(t,r){', 1, '==', '同上'),
    ]
    return gates
