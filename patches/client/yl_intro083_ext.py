# -*- coding: utf-8 -*-
"""
yl_intro083_ext.py — 0.8.3 客户端两修（cli-intro）

本模块只做**两处原地替换**，不新增任何 helper、不改任何 CSS、不新增组件树节点。
因此 `INJECT_JS` 有意留空（build 侧 `zh('')` 通过、不触发任何插入；dryrun 会打一条
`无 INJECT_JS` 的 WARN，属预期，非失败）。

=========================================================================== ① 首次进游戏弹窗「每次进游戏都弹」
--------------------------------------------------------------------------
弹窗 = 组件 `Bk`（标题「修仙法门」），触发在 `oC`：
    function oC({gameStarted:t,player:r,setShowCultivationIntro:a}){O.useEffect(()=>{
      if(t&&r&&!localStorage.getItem(et.CULTIVATION_INTRO_SHOWN)){
        const l=setTimeout(()=>{a(!0)},Ey.CULTIVATION_INTRO_DELAY);
        return()=>clearTimeout(l)}},[t,r,a])}
关闭时写标记：`onClose:()=>{A(!1),localStorage.setItem(et.CULTIVATION_INTRO_SHOWN,"true")}`

根因（已复核，见 localtest/report_cli-intro.md）：页面加载早期的自执行 IIFE 里有一段
**无条件清除一批 localStorage 键**的循环，其中包含 `"xiuxian-cultivation-intro-shown"`：

    var K=["auth_token","auth_refresh_token","auth_user","xiuxian-debug-mode",
           "xiuxian-cultivation-intro-shown","xiuxian-action-bar-guide-shown",
           "xiuxian-version-checked","xiuxian-game-settings","xiuxian-game-save",
           "xiuxian-game-save-backup","xiuxian-game-save-owner","xiuxian-save"];
    for(var i=0;i<K.length;i++){try{localStorage.removeItem(K[i])}catch(e){}}

⇒ 「已看过」标记永远存不住 ⇒ 每次进游戏都弹。

修法：**只把这一个键从该 clear 数组里摘掉**，其余 11 个键一个不动（它们可能是
「换账号/登出必须清」的有意设计）。摘键后 `et.CULTIVATION_INTRO_SHOWN` 的定义、
`oC` 的 getItem 判断、`onClose` 的 setItem 写入**全部原样保留**，标记从此可持久化。

注：该字符串在文件里共 2 处（①clear 数组 ②`et` 常量表定义）。本模块用「左邻 debug-mode
+ 右邻 action-bar-guide」的上下文锚定，`expect=1` 保证只命中数组里那一处。

是否需要「存档级判定」的评估见报告结论：**建议不加**（最小修法已能达成用户诉求，
多加判定会引入换设备/清缓存之外的误判面）。

=========================================================================== ③ 历练日志满 1000 条后不显示新日志
--------------------------------------------------------------------------
存储（zustand `addLog`，新日志在**末尾**，硬上限 1000）：
    addLog:(a,l)=>{t(c=>({logs:[...c.logs,{id:...,text:a,type:l,timestamp:Date.now()}]
        .slice(-1000)}))}
渲染（组件 `o4`，只渲染末尾 `Hg=201` 条）：
    j=O.useMemo(()=>t.length<=Hg?t:t.slice(-Hg+1),[t==null?void 0:t.length])

根因（已复核）：`useMemo` 依赖是 `t.length`。日志达到 1000 上限后，每次 push 后长度
**恒为 1000**，依赖不变 ⇒ React 返回**缓存的旧切片** ⇒ 新日志永不渲染。

修法：依赖由 `[t==null?void 0:t.length]` 改为 `[t]`（`addLog` 每次 push 都生成新数组，
引用必变 ⇒ 必重算）。**不动** `slice(-1000)`（存储上限，设计值）与 `Hg=201`（渲染窗口，设计值）。

--------------------------------------------------------------------------
模块位置：纯锚点替换，与其余 v28 模块无交集，放在 `V28_MODULES` 任意位置均可。
"""

# 两处均为原地替换，无需注入任何 helper（build 侧 zh('') 合法且不插入）。
INJECT_JS = ''

# --------------------------------------------------------------------------- 锚点（实测 count==1，纯 ASCII）

# ① clear 数组：只摘 "xiuxian-cultivation-intro-shown" 一个键
_ARR_OLD = ('"xiuxian-debug-mode","xiuxian-cultivation-intro-shown",'
            '"xiuxian-action-bar-guide-shown"')
_ARR_NEW = '"xiuxian-debug-mode","xiuxian-action-bar-guide-shown"'

# ③ 日志切片 useMemo：依赖 [t.length] → [t]
_MEMO_OLD = 'O.useMemo(()=>t.length<=Hg?t:t.slice(-Hg+1),[t==null?void 0:t.length])'
_MEMO_NEW = 'O.useMemo(()=>t.length<=Hg?t:t.slice(-Hg+1),[t])'

PATCHES = [
    ('intro·从清除数组摘掉已读标记',
     _ARR_OLD, _ARR_NEW, 1,
     '页面加载时无条件 removeItem 的 K 数组里去掉 "xiuxian-cultivation-intro-shown"；'
     '其余 11 键保持不动'),
    ('logs·useMemo 依赖改为 [t]',
     _MEMO_OLD, _MEMO_NEW, 1,
     '日志达 1000 上限后长度恒为 1000，旧依赖 [t.length] 不再变化导致缓存旧切片；'
     '改 [t] 后每次 push 新数组引用触发重算'),
]

# --------------------------------------------------------------------------- 门禁 (name, needle, expect, cmp, note)
GATES = [
    # ---- ① 新形态存在 / 旧形态清零 ----
    ('intro·数组已摘键',            _ARR_NEW,                                   1, '==', '摘键后的数组形态'),
    ('intro·数组旧形态清零',        _ARR_OLD,                                   0, '==', '含 cultivation-intro 的旧形态必须为 0'),
    ('intro·摘键后右邻未被吞',      '"xiuxian-debug-mode","xiuxian-action-bar-guide-shown",'
                                    '"xiuxian-version-checked"',                1, '==', 'debug-mode 与 version-checked 相邻，证明只删了中间一项'),
    # ---- ① 标记链路必须完好（不得误删定义/读/写）----
    ('intro·et 常量定义仍在',       'CULTIVATION_INTRO_SHOWN:"xiuxian-cultivation-intro-shown"', 1, '==', '常量表定义未被误删'),
    ('intro·键字面量仅剩 1 处',     'xiuxian-cultivation-intro-shown',          1, '==', '摘数组后全库只剩 et 定义这一处'),
    ('intro·getItem 判断仍在',      '!localStorage.getItem(et.CULTIVATION_INTRO_SHOWN)', 1, '==', 'oC 的「未看过才弹」判断未被破坏'),
    ('intro·setItem 写入仍在',      'localStorage.setItem(et.CULTIVATION_INTRO_SHOWN,"true")', 1, '==', 'onClose 的写标记未被破坏'),
    ('intro·clear 循环仍在',        'for(var i=0;i<K.length;i++){try{localStorage.removeItem(K[i])}catch(e){}}', 1, '==', '清键循环本身未动'),
    ('intro·其余清除键未动',        '"auth_refresh_token","auth_user","xiuxian-debug-mode"', 1, '==', '数组头部 3 键原样（避开禁用词 auth_token，只用其后两项定位）'),
    ('intro·延迟常量未动',          'CULTIVATION_INTRO_DELAY:500',              1, '==', '弹窗延迟 500ms 设计值未动'),
    # ---- ③ 新依赖存在 / 旧依赖清零 ----
    ('logs·新依赖已写入',           _MEMO_NEW,                                  1, '==', 'useMemo 依赖 [t]'),
    ('logs·旧依赖清零',             _MEMO_OLD,                                  0, '==', '旧依赖形态必须为 0'),
    ('logs·旧依赖残片全库清零',     '[t==null?void 0:t.length]',                0, '==', '该依赖数组形态全库仅此一处，改后应为 0'),
    # ---- ③ 设计值未动（不得顺手改）----
    ('logs·渲染窗口 Hg=201 未动',   'Hg=201',                                   1, '==', '渲染窗口设计值'),
    ('logs·存储上限 slice(-1000) 未动', '].slice(-1000)}))',                    1, '==', 'addLog 硬上限设计值'),
    ('logs·切片表达式未动',         't.length<=Hg?t:t.slice(-Hg+1)',            1, '==', '仅改依赖，不动切片逻辑'),
]


def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}（本模块不需要 zh）"""
    for name, old, new, expect, note in PATCHES:
        p.replace(name, old, new, expect=expect, note=note)
    return list(GATES)
