# -*- coding: utf-8 -*-
r"""
yl_061_ext.py — R-061 演武场：试炼挑战「零反馈 + 次数不刷新」修复（客户端半边）

需求原文（需求台账_进行中.md R-061，2026-10-01）
--------------------------------------------------------------------------
  「我点击挑战第一层，直接显示挑战结束，也没有任何反馈，次数也是重开窗口才刷新。」
  报障型真 bug，优先小改动修根因。

根因（bundle index-v28116-20261001.js 逐字取证，全部在客户端，服务端无恙）
--------------------------------------------------------------------------
  演武场面板是 yl-0.8.9 T16 注入的三区面板（yl_t16arena_ext.py 产出）。试炼闯关的
  战斗按钮把 act 的第 4 参（toast 文案）写死成「挑战结束」：

      onClick: function() { act("fight"+realm+"-"+(layer+1), "/arena/trials/fight",
        { realmIndex: realm, layer: layer + 1 }, "挑战结束"); },

  而 act = YlxwUseAct(c).run 的成功路径是：
      var g = await YlxwPost(u, f);
      return ia(m || (g && g.message) || "操作成功"), r && await r(), YlxwDirty(), g;

  ① 零反馈：服务端 /api/arena/trials/fight 明明返回全套战果
     { ok, iWon, log, stones, exp, firstClear, dailyFirst, triple, streak, dailyLeft, ... }
     （srv_patch_t16arena.py C2 块），但第 4 参 m="挑战结束" 把它整个压死 ——
     无论胜负，toast 永远一句「挑战结束」，响应 g 被原样丢弃。
  ② 次数不刷新：act 成功后只 reload 构造时绑定的 r（= /arena/my 的 load），
     而「今日剩 X 次 / 首通✓」的数据源是父组件里**另一个** hook
     YlxwUseList("/arena/trials")（tReload）。act 不碰它 ⇒ dailyLeft/cleared
     在组件重挂载（重开窗口）前永远是旧值。
     （旁证：YlxwDirty() 只触发云端自动存档监听（yS=@671733），不刷新任何面板。）

  结论：不是服务端 bug —— fight 接口工作正常且失败不扣次数（G18a 已有门禁），
  是客户端把结果扔了、又没刷对数据源。

本模块动作（3 处就地替换，锚点各 count==1，全在 T16 注入块内）
--------------------------------------------------------------------------
  R1 父组件给试炼区传参：reload: c → reload: tReload
     —— YlxwArenaTrialZone 的 reload prop 是**死代码**（destructure 后全文无引用，
        bundle 取证：zone 函数体内 reload 仅出现在解构行 1 处），改传 /arena/trials
        的 loader，供 R2/R3 在战斗/购买后刷新次数与首通标记。
  R2 fight onClick：
     - 去掉写死的第 4 参「挑战结束」⇒ act 的 toast 回退链变成 g.message ——
       服务端响应补的 message 字段（srv_patch_061.py）就是单条有内容的战报 toast；
     - 链 .then：先 reload()（刷次数），响应无 message（服务端半边未上线）时
       用今日既有字段 iWon/stones/exp/firstClear/triple 兜底拼一条 toast
       （胜→ia 绿 / 负→Je 红）；响应带 message 则不双弹。
  R3 buy onClick：链 .then reload()（买完次数立刻 +1，不再等重开窗口）。

  降级矩阵：服务端半边上线后 = 单条战报 toast（最佳）；未上线时 = act 兜底
  「操作成功」+ 客户端兜底战报（信息不缺失，仅多一条过渡 toast，不劣于现状）。

硬约束 / 纪律
--------------------------------------------------------------------------
  · ★ 不碰 YlxwTArena2 首行（var r = YlxwUseList("/arena/my"), ..., d = YlxwUseAct(c), ...）
    —— t16arena 门禁 'T16·YlxwUseAct 调用仍在' 对**整行** count==1，动了必炸邻环；
    也不碰 act 成功路径内核（ia(m || (g&&g.message) || "操作成功")，全 Ylxw 面板共用）。
  · 门禁是全模块跑完后在最终文本统一求值（build_v26n.py:1002-1009）⇒ 任何被邻环
    门禁 count 断言的串都不能改形。冻结门禁逐条锁死 t16arena 断言过的面。
  · 本模块无 INJECT_JS（纯就地替换，同 yl_r040_ext.py 形态）；替换串内中文一律
    \uXXXX 转义（T16 块在 bundle 里即转义形态，取证 @1040107）。
  · 只新建本文件 + srv_patch_061.py；不改 build_v26n.py / localtest/chain_build.py /
    build/assets/* / srv/index_v28.ts。
  · 接线（lead/后续工程师）：
      build_v26n.py   → import 行 + V28_MODULES 条目（见模块尾注释）
      chain_build.py  → SRV_CHAIN 链尾追加 'srv_patch_061.py'
  · 装配序：必须排在 t16arena 之后（锚点在 T16 注入产物内）；与其余 R 批次一致放
    numbal 之前即可，无其他顺序依赖。

CLI 契约（服务端半边 srv_patch_061.py）
--------------------------------------------------------------------------
  与 srv_patch_057.py 同款：--src 就地原子写回；--check/--selftest 只验不写；
  幂等标记 [r061]；锚点命中数不符即中止。
"""

import re

INJECT_JS = ''          # 本模块纯就地替换，无注入块

NL = '\n'

# --------------------------------------------------------------------------- 锚点（bundle 实测 count==1，repr 取证）

# R1 · 父组件给试炼区的传参行（reload prop 死代码 ⇒ 改传 tReload = /arena/trials loader）
PROPS_OLD = 'e.jsx(YlxwArenaTrialZone, { st: st, act: f, actKey: u, reload: c, myRealm: (t && t.realmIndex) || 0 })'
PROPS_NEW = 'e.jsx(YlxwArenaTrialZone, { st: st, act: f, actKey: u, reload: tReload, myRealm: (t && t.realmIndex) || 0 })'

# R2 · 战斗按钮：去掉死 label + 链式刷次数 + 战报兜底 toast
#   （锚点含精确缩进 8/10 空格、真实换行、\uXXXX 字面转义 —— repr 取证 @1039773..1040293）
FIGHT_OLD = (
    '        onClick: function() { act("fight" + realm + "-" + (layer + 1), "/arena/trials/fight",' + NL +
    '          { realmIndex: realm, layer: layer + 1 }, "\\u6311\\u6218\\u7ed3\\u675f"); },'
)
#   说明：w61/r61/m61/e61a 为本模块私有名（bundle 取证 0 占用）；服务端有 message ⇒ 只刷
#   次数不双弹；无 message ⇒ 用既有响应字段兜底拼战报（胜 ia 绿 / 负 Je 红）。
FIGHT_NEW = (
    '        onClick: function() { var w61 = act("fight" + realm + "-" + (layer + 1), "/arena/trials/fight",' + NL +
    '          { realmIndex: realm, layer: layer + 1 }); if (w61 && w61.then) w61.then(function(r61) {' + NL +
    '            try { reload && reload(); } catch (e61a) {}' + NL +
    '            if (!r61 || r61.message) return;' + NL +
    '            var m61 = r61.iWon ? ("\\u2728 \\u6311\\u6218\\u80dc\\u5229\\uff01" + (r61.stones > 0 ? "\\u7075\\u77f3 +" + r61.stones : "") + (r61.exp > 0 ? " \\u00b7 \\u4fee\\u4e3a +" + r61.exp : "")) : "\\u2694 \\u6311\\u6218\\u5931\\u8d25\\uff0c\\u4eca\\u65e5\\u6b21\\u6570\\u672a\\u6263\\u9664";' + NL +
    '            if (r61.firstClear) m61 += " \\u00b7 \\u9996\\u901a\\uff01";' + NL +
    '            if (r61.triple) m61 += " \\u00b7 \\u4e09\\u8fde\\u80dc\\u5956\\u52b1\\uff01";' + NL +
    '            if (r61.iWon) ia(m61); else Je(m61);' + NL +
    '          }); },'
)

# R3 · 购买次数按钮：链式刷次数（toast 文案「已购买挑战次数」保留不动）
BUY_OLD = '    onClick: function() { act("buy", "/arena/trials/buy", {}, "\\u5df2\\u8d2d\\u4e70\\u6311\\u6218\\u6b21\\u6570"); },'
BUY_NEW = ('    onClick: function() { var w61 = act("buy", "/arena/trials/buy", {}, "\\u5df2\\u8d2d\\u4e70\\u6311\\u6218\\u6b21\\u6570");'
           ' if (w61 && w61.then) w61.then(function() { try { reload && reload(); } catch (e61b) {} }); },')

# 冻结面（邻环门禁 count 断言过的串，一个字不能动）
F_T16_HEAD = 'var r = YlxwUseList("/arena/my"), t = r.data, a = r.err, l = r.busy, c = r.load, d = YlxwUseAct(c), u = d.actKey, f = d.run;'
F_ACT_CORE = 'return ia(m || (g && g.message) || "\\u64cd\\u4f5c\\u6210\\u529f"), r && await r(), YlxwDirty(), g;'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    zh = ctx['zh']

    # 本模块无 INJECT_JS；替换串里的中文全为 \uXXXX 转义（ASCII），此处自证防手滑。
    for _tag, _s in (('FIGHT_NEW', FIGHT_NEW), ('BUY_OLD', BUY_OLD), ('F_ACT_CORE', F_ACT_CORE)):
        bad = re.findall(r'[^\x00-\x7f]', _s)
        if bad:
            raise AssertionError('r061 %s 含非 ASCII（T16 块约定为 \\uXXXX 转义形态）: %r' % (_tag, bad[:5]))
    if '\\u6311\\u6218' not in FIGHT_OLD:
        raise AssertionError('r061 FIGHT_OLD 异常：没找到「挑战」转义串')

    p.replace('r061-props', PROPS_OLD, PROPS_NEW, expect=1,
              note='试炼区 reload prop（死代码）改传 /arena/trials loader，供战斗/购买后刷次数')
    p.replace('r061-fight', FIGHT_OLD, FIGHT_NEW, expect=1,
              note='挑战按钮：去死 label（toast 走服务端 message）+ 链式刷次数 + 无 message 时客户端兜底战报')
    p.replace('r061-buy', BUY_OLD, BUY_NEW, expect=1,
              note='购买次数后链式刷次数，不再等重开窗口')

    gates = [
        # ================= 本模块改动 =================
        ('R61·试炼区已改传 tReload',      'reload: tReload, myRealm: (t && t.realmIndex) || 0', 1, '==', '战斗/购买后可刷 /arena/trials'),
        ('R61·旧传参（reload: c）已清零',  'reload: c, myRealm',                                 0, '==', '旧形态'),
        ('R61·fight 死 label 已清零',    '{ realmIndex: realm, layer: layer + 1 }, "\\u6311\\u6218\\u7ed3\\u675f"); },', 0, '==', '「挑战结束」写死串'),
        ('R61·fight 旧直调形态已清零',    'function() { act("fight"',                           0, '==', '旧形态'),
        ('R61·fight 链式刷次数',          'try { reload && reload(); } catch (e61a) {}',        1, '==', ''),
        ('R61·fight message 优先不双弹',  'if (!r61 || r61.message) return;',                   1, '==', '服务端半边上线后单条战报'),
        ('R61·fight 兜底战报 toast',      'if (r61.iWon) ia(m61); else Je(m61);',               1, '==', '胜绿 / 负红'),
        ('R61·兜底含灵石数',              'r61.stones > 0 ? "\\u7075\\u77f3 +" + r61.stones',   1, '==', ''),
        ('R61·buy 旧直调形态已清零',      'function() { act("buy"',                             0, '==', '旧形态'),
        ('R61·buy 链式刷次数',            'w61.then(function() { try { reload && reload(); } catch (e61b) {} });', 1, '==', ''),
        ('R61·私有名 w61 总数自证',       'w61',                                                8, '==', 'fight/buy 各 4（声明+条件两处+调用，干跑实测）'),
        ('R61·私有名声明恰 2 处',         'var w61 = ',                                         2, '==', 'fight+buy 各 1，防撞名'),
        # ================= 冻结：t16arena / 全 Ylxw 面板共用面，一个字不动 =================
        ('冻结·T16 面板首行未动',         F_T16_HEAD,                                           1, '==', 't16arena 门禁对整行 count==1'),
        ('冻结·act 成功路径内核未动',      F_ACT_CORE,                                          1, '==', '全 Ylxw 面板共用的 toast/reload/dirty 链'),
        ('冻结·试炼状态端点唯一',         '"/arena/trials"',                                    1, '==', 't16arena 门禁同款'),
        ('冻结·战斗端点唯一',             '"/arena/trials/fight"',                              1, '==', ''),
        ('冻结·购买端点唯一',             '"/arena/trials/buy"',                                1, '==', ''),
        ('冻结·论剑区传参未动',           'e.jsx(YlxwArenaLadderZone, { act: f, actKey: u, reload: c, my: t })', 1, '==', 'R1 只动试炼区'),
        ('冻结·恩怨区传参未动',           'e.jsx(YlxwArenaGrudgeZone, { act: f, actKey: u, my: t })', 1, '==', ''),
        ('冻结·组件表映射未动',           'arena: YlxwTArena2,',                                1, '==', 't16arena 门禁同款'),
        ('冻结·试炼区组件定义未动',        'function YlxwArenaTrialZone(',                       1, '==', ''),
        ('冻结·演武场入口未动',           'YlxwOpen("arena")',                                  2, '==', '工具栏 + 抽屉各 1'),
        # 「失败不扣次数」的服务端语义（WHERE ... AND won = 1）归 srv_patch_061.py 冻结面，
        # 客户端 bundle 里无此串 —— 放这里会成恒假 FAIL（§19 假 FAIL 教训：计数域要选对）。
    ]
    return gates


# --------------------------------------------------------------------------- 接线（给 lead / 后续工程师，勿手滑改进本文件）
#
# build_v26n.py：
#   import 区（r058 行后）：
#     from yl_061_ext import apply as v28_061_apply  # noqa: E402
#   V28_MODULES（建议 r058 之后、numbal 之前；★ 必须排在 t16arena 之后）：
#     ('r061', v28_061_apply),               # R-061 演武场试炼：战报反馈 + 次数即时刷新（客户端半边；服务端配套 = SRV_CHAIN 链尾 'srv_patch_061.py'）
