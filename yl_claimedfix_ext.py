# -*- coding: utf-8 -*-
r"""
yl_claimedfix_ext.py — 周里程碑「已领取」显示修复（客户端单模块）

背景
--------------------------------------------------------------------------
服务端第 32 环（`srv_patch_claimedfix.py`）修好了 `GET /api/quest/summary` 的 `claimed` ——
它原来用**裸周号**去查 `activity_milestones`，而 `claim` 写入的是 `'w'+week+'_'+tier`，永远查不到。

**但光修服务端不够**：客户端从来没读过那个字段。实测产物（`index-v2811-20260930.js`）：

    yl_t9quest_ext.py:246   var claims = (l && l.milestones) || {};        // ★ milestones 是【数组】
    yl_t9quest_ext.py:310   e.jsx(YlxwQMileZone, { ..., claims: claims, ... })
    yl_t9quest_ext.py:156   var claims = props.claims || {}
    yl_t9quest_ext.py:160   var claimed = !!claims[m.tier] || !!claims[String(m.tier)];   // ★ 拿数组当字典取

`milestones` 是 `[{tier, reward, exp, tickets, legacy, monthly, unlocked, claimed}, …]`（长度 5），
对它取 `claims[500]` 恒 `undefined` ⇒ `claimed` 恒 `false` ⇒ **玩家领过之后 UI 仍显示「可领取」**。

（不是资损：`activity_milestones` 的 `UNIQUE(user_id, week, tier)` 会挡住重复发放。纯显示 bug。）

改法（1 处，改「生产者」而不是「消费者」）
--------------------------------------------------------------------------
    旧:  var claims = (l && l.milestones) || {};
    新:  var claims = {}; (l && l.milestones || []).forEach(function (x) { if (x && x.tier != null) claims[x.tier] = !!x.claimed; });

把数组归一成 `{tier: claimed}` 映射 ⇒ 第 160 行现有的 `claims[m.tier]` **原样即可命中**，不用碰渲染体。

★ 为什么改生产者：改 246 只需 1 处；改 160 要在渲染循环里塞分支，改动面更大，
  且会碰到 `YlxwQMileZone` 的卡片渲染（本模块刻意**不碰**它，见门禁冻结项）。

★ 兼容性：新串对「`milestones` 缺失 / 为 null」也安全（`|| []`），旧行为（传空对象）保持不变。

硬约束
--------------------------------------------------------------------------
  · 无注入块（纯 replace），不引入任何新符号。
  · 每个 replace 带 expect=精确次数；apply() 返回门禁五元组列表。
  · 只新建本文件；不改 yl_t9quest_ext.py / build_v26n.py / chain_build.py / srv/index_v28.ts。
  · ★ 必须排在 `r013c` **之后**（r013c 会覆盖式替换 `YlxwQMile` 表，本环要看到它的最终形态）。
"""

# --------------------------------------------------------------------------- 锚点常量

# `YlxwQMileZone` 的宿主（`YlxwQMile` 区块）里，把服务端 milestones 数组接进来的那一行
CLAIMS_OLD = 'var claims = (l && l.milestones) || {};'
CLAIMS_NEW = ('var claims = {}; (l && l.milestones || []).forEach(function (x) '
              '{ if (x && x.tier != null) claims[x.tier] = !!x.claimed; });')

# ---- 参照串（只断言、不改）----
REF_ZONE = 'function YlxwQMileZone('
REF_CONSUMER = 'var claimed = !!claims[m.tier] || !!claims[String(m.tier)];'
REF_TABLE_HEAD = 'var YlxwQMile = ['                 # ★ econ2 的锚点，绝不能动
REF_PROP_PASS = 'week: week, realm: realm, claims: claims, busy: !!actKey, onClaim: claimMile'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    """p = Patcher（文本已含全部前置 v28 模块）；ctx = {'zh': zh, 'base_text': str}"""

    p.replace('claimedfix-map', CLAIMS_OLD, CLAIMS_NEW, expect=1,
              note='milestones 数组 → {tier: claimed} 映射（治 claimed 恒 false）')

    # ------------------------------------------------------------- 门禁
    gates = [
        # ================= 改动本身 =================
        ('CF·claims 已归一为映射', CLAIMS_NEW, 1, '==', '数组 → {tier: claimed}'),
        ('CF·旧数组直传已清零', CLAIMS_OLD, 0, '==', ''),
        ('CF·forEach 遍历 milestones', '(l && l.milestones || []).forEach(', 1, '==', ''),
        ('CF·tier 空值防御', 'if (x && x.tier != null)', 1, '==', ''),
        ('CF·claimed 取布尔', 'claims[x.tier] = !!x.claimed;', 1, '==', ''),
        # ================= 冻结：不碰渲染体 =================
        ('冻结·YlxwQMileZone 未重写', REF_ZONE, 1, '==', ''),
        ('冻结·消费者读取行未动', REF_CONSUMER, 1, '==', '★ 故意不改第 160 行'),
        ('冻结·prop 传参未动', REF_PROP_PASS, 1, '==', ''),
        # ================= 冻结：不碰 econ2 的锚点 =================
        ('冻结·YlxwQMile 表头未动', REF_TABLE_HEAD, 1, '==', '★ econ2 锚点，绝不能动'),
        # ================= 无新增网络调用（限定在 t9quest 注入块范围内）=================
        # 范围锚：T9 注入块头注释 → YlxwQMileZone 定义行（实测产物里 870169 < 877402）
        ('CF·未新增网络调用', 'fetch(', 0, '==', '纯数据归一，无网络',
         ('yl-0.8.9 T9', 'function YlxwQMileZone(')),
    ]
    return gates
