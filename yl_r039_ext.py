# -*- coding: utf-8 -*-
r"""
yl_r039_ext.py — R-039 设置「重新开始游戏」要把该角色的**服务端**数据一并清干净

问题（用户 R-039 原话）
--------------------------------------------------------------------------
  设置里点「重新开始游戏」，只清了本地（回到开始界面），服务端仍留着：
  「仙务·称号」还保留，修行统计、仙务·心法 等等一大堆数据都保留了。

根因（已在压缩产物 `build/assets/index-v28113-20260930.js` 里定位到，非猜测）
--------------------------------------------------------------------------
  设置组件（产物里的 `RM`，约 @1654082）：
      RM=({isOpen:t,onClose:r,settings:a,onUpdateSettings:l,onRestartGame:c})=>{ … }
        onClick:()=>{Ui(`重新开始游戏将清除当前所有进度，包括：…`,"转世重修",()=>{c(),r()})}

  两个回调各自是什么（顺链查清，别猜）：
    · r = onClose            —— 关掉设置弹窗
    · c = onRestartGame = 父组件 `c.handleRestartGame`
        父组件渲染处：`onRestartGame:c.handleRestartGame`
        而 `handleRestartGame` 这个名字是产物里的**别名**：hook `xk()` 把入参
        `handleRebirth:ke` 原样返回成 `handleRestartGame:ke`
        ⇒ `c()` 实际执行的是 `fS()` 里的 `handleRebirth`：
            handleRebirth:()=>{mm(),c(!1),d(null),u(""),f(null),v(!1),m(!1),j(!1),b(!1),
                               S(!1),t(null),r([]),a(!1),l(!1)}
        其中 `mm=()=>{}`（**空实现**），其余全是 setPlayer(null)/setHasSave(false) 之类的
        前端状态归零。
  ⇒ 结论：点「重新开始游戏」**一次服务端请求都不发**，纯前端回到开始界面。
    服务端的 `player_titles`（称号）/`stats_daily`（统计）/`wudao`（心法）/
    `achievement_claimed`（成就）/`player_gongfa`（功法）… 全部原样留在库里。

本模块动作（1 处就地替换，锚点唯一）
--------------------------------------------------------------------------
  只把确认回调的**回调体**换掉（`Ui(...)` 二次确认弹窗与「转世重修」标题一字不动）：

    旧： "转世重修",()=>{c(),r()}
    新： "转世重修",()=>{
          const ylR039Done = () => { 清 3 个本地存档键 → c(),r() };
          if (!已登录) { ylR039Done(); return }        // 无服务端数据可清
          Xc(`${ln}/character/reset`,{method:"POST"})   // 走既有鉴权封装：Bearer + 401 续期
            .then(ylR039Done, () => 提示「服务端数据清除失败，本次未重置」)
        }

  为什么这么排：
    · **先服务端、后本地** —— 服务端清成功才动本地。失败就**不重置**，避免出现
      「玩家以为清了、服务端其实还在」的原样复现（宁可提示重试，也不静默半清）。
    · 清本地只清 3 个**存档键**（et.SAVE / SAVE_BACKUP / SAVE_OWNER，与「登出」路径同款），
      **绝不碰** auth_refresh_token / yl_refresh / settings ⇒ 账号与登录态原样保留。
    · `Xc` 是产物里既有的带鉴权 fetch 封装（`Authorization: Bearer …` + 401 自动续期 +
      `X-YL-Base-Revision`），**不新开无鉴权端点**。

硬约束 / 纪律
--------------------------------------------------------------------------
  · 二次确认弹窗（`Ui(...)` + 「转世重修」）原样保留 —— 只换它的回调体。
  · 保留账号：不动 auth / refresh token / 设置 / 语言等本地键。
  · 替换串不含 V28_BAN_PATTERNS：['iframe','postMessage','XMLHttpRequest','auth_token','X-YL-']。
  · 锚点唯一（`expect=1`）；另留**冻结门禁**证明没碰相邻功能（存档同步 / 挂机收益 / 离线结算）。
  · 只新建本文件；不改 build_v26n.py / localtest/*.py / srv/index_v28.ts / deploy_v28/*。
  · 本模块是**就地替换**（无注入块）⇒ 替换串里的中文与产物里同形（UTF-8 字面中文，非 \uXXXX），
    故不做 ASCII 自检（那只适用于 INJECT_JS）。
"""

import re

INJECT_JS = ''          # 本模块只做「就地替换」，不需要额外注入块

# --------------------------------------------------------------------------- 锚点

# 设置里「重新开始游戏」的确认回调（唯一；`转世重修` 全文 6 处，但带这段回调体只此 1 处）
ANCHOR_OLD = '"转世重修",()=>{c(),r()}'

# 新形态：先请求服务端清档，成功后再重置本地并清本地存档键；失败不静默重置
ANCHOR_NEW = (
    '"转世重修",()=>{'
    'const ylR039Done=()=>{'
    'try{localStorage.removeItem(et.SAVE),localStorage.removeItem(et.SAVE_BACKUP),'
    'localStorage.removeItem(et.SAVE_OWNER)}catch(e){}'
    'c(),r()};'
    'if(!Et.getState().token){ylR039Done();return}'
    'Xc(`${ln}/character/reset`,{method:"POST"}).then(ylR039Done,()=>{'
    'Je("\u670d\u52a1\u7aef\u89d2\u8272\u6570\u636e\u6e05\u9664\u5931\u8d25\uff0c'
    '\u8bf7\u7a0d\u540e\u91cd\u8bd5\uff08\u672c\u6b21\u672a\u91cd\u7f6e\uff09")})}'
)

# 相邻功能锚针（只读、不得被本模块改动）
FREEZE_PUSHSAVE = 'body:JSON.stringify({player:'
FREEZE_SAVEGATE = 'YLSaveGate'
FREEZE_OFFLINE = '\u79bb\u7ebf\u671f\u95f4\u6536\u83b7\u7684\u7075\u8349'
FREEZE_AUTOMED = 'autoMeditate'


# --------------------------------------------------------------------------- 主入口

def apply(p, ctx):
    zh = ctx['zh']

    # 就地替换：锚点/替换串里含**字面中文**（产物里是 UTF-8 中文，不是 \uXXXX）。
    # 防手滑：确认串里确实带了中文与关键接线。
    if '\u8f6c\u4e16\u91cd\u4fee' not in ANCHOR_OLD:
        raise AssertionError('r039 锚点异常：没找到「转世重修」')
    if 'character/reset' not in ANCHOR_NEW or 'et.SAVE_OWNER' not in ANCHOR_NEW:
        raise AssertionError('r039 替换串异常：缺清档接口或本地存档键')
    for _pat in ('iframe', 'postMessage', 'XMLHttpRequest', 'auth_token', 'X-YL-'):
        if _pat in ANCHOR_NEW:
            raise AssertionError('r039 替换串命中禁词：%s' % _pat)

    p.replace('r039-server-purge', ANCHOR_OLD, ANCHOR_NEW, expect=1,
              note='「重新开始游戏」改为：先清服务端角色数据，成功后再重置本地')

    gates = [
        # ================= 本模块改动 =================
        ('R39·重置已接服务端清档',   'Xc(`${ln}/character/reset`,{method:"POST"})', 1, '==', '走既有鉴权封装 Xc'),
        ('R39·成功后清本地存档三键', 'localStorage.removeItem(et.SAVE),localStorage.removeItem(et.SAVE_BACKUP),localStorage.removeItem(et.SAVE_OWNER)', 2, '==', '与登出路径同款（本环新增 1 + 登出路径原有 1）'),
        ('R39·未登录走本地重置',     'if(!Et.getState().token){ylR039Done();return}', 1, '==', '无服务端数据可清'),
        ('R39·失败不静默重置',       '\u672c\u6b21\u672a\u91cd\u7f6e', 1, '==', '失败提示，避免半清'),
        ('R39·旧「只重置本地」已清零', ANCHOR_OLD, 0, '==', '旧形态必须消失'),
        # ================= 冻结：二次确认弹窗 + 接线不动 =================
        ('冻结·二次确认弹窗保留',    '\u91cd\u65b0\u5f00\u59cb\u6e38\u620f\u5c06\u6e05\u9664\u5f53\u524d\u6240\u6709\u8fdb\u5ea6', 1, '==', 'Ui(...) 一字未动'),
        ('冻结·确认标题仍是转世重修', ',"\u8f6c\u4e16\u91cd\u4fee",', 1, '==', ''),
        ('冻结·onRestartGame 接线未动', 'onRestartGame:c.handleRestartGame', 1, '==', ''),
        ('冻结·本地重置回调仍在',    'handleRebirth:()=>{mm()', 1, '==', 'handleRestartGame 的别名源'),
        # ================= 冻结：相邻功能（存档同步 / 挂机 / 离线结算）=================
        ('冻结·存档同步 pushSave 未动', FREEZE_PUSHSAVE, 1, '==', 'yl_entry_ext 的门禁针'),
        ('冻结·存档串行闸未动',      FREEZE_SAVEGATE, 1, '>=', 'saveretry 的地盘'),
        ('冻结·离线结算文案未动',    FREEZE_OFFLINE, 1, '==', 'offline2 的地盘'),
        ('冻结·挂机自动修炼未动',    FREEZE_AUTOMED, 1, '>=', ''),
    ]
    return gates
