# -*- coding: utf-8 -*-
"""
yl_version_ext.py — yl 客户端 v28 扩展模块（用户反馈 #3 版本号 / #4 活动说明）

只做两件事，互不影响别人地盘（抽屉入口 / 信箱 / pushSave / 宗门 / 人物志 / 数值常量）：

  #3 版本号不再硬编码
      基线里版本号写死在 4 处，互不相干：
        @573425  function Yw(){return"0.4.0"}                    ← 唯一「版本来源函数」
        @732168  E="0.4.0",N=vd()                                 ← 主页头部徽标（渲染 ["v",E] @734983）
        @1109983 const[a,l]=O.useState([]),[c,d]=O.useState(!0),u="0.4.0";  ← 更新日志弹窗 CM
        @1129770 children:["v","0.4.0"]                           ← 设置页「游戏版本」
      本模块注入模块级 helper（YlxwVersionGet/Parse/Load），把上述 4 处全部改为动态取值：
        · 兜底常量 YLVERSION_FALLBACK（= 当前 CHANGELOG 最新版；0.8.3=0.8.3，…，0.8.7=0.8.7，
          0.8.8=0.8.8，0.8.9=0.8.9，0.8.10=0.8.10）
        · 首次调用发起一次 fetch("/myxxz/CHANGELOG.md")，解析首个 "## [x.y.z]" 行
        · 解析成功 → 写模块级缓存 + 同步写回 localStorage["xiuxian-version-checked"]
        · 模块级闩 YLVERSION_LOADED 保证只请求一次
      「版本来源链」：Yw() 是基线里唯一的版本函数（被 Kw() 的更新检查消费）；本模块让
      Yw() 读 helper，其余 3 处显示点也直接读 helper，全站只剩一个真源。

  #4 限时活动补详细说明
      服务端 GET /api/events 每条已带 desc 字段，客户端渲染（YlxwTEvents @803389）完全没用。
      本模块：① 活动行下方渲染 d.desc（空则不渲染）；② name === typeName 时去重
      （原来是 "天降灵雨 （天降灵雨 ×2）"，去重后 "天降灵雨 ×2"，倍率信息不丢）。

  #3b 去掉上游 GitHub 版本检查（0.8.1 深测回归新增）
      基线 Kw()（App 内以 Kw() 调用的 hook）每次版本变化都 fetch
      api.github.com/repos/JeasonLoop/react-xiuxian-game/releases/latest，
      把**上游仓库** release tag 与**本站**版本比较，上游更大就 window.location.reload()。
      对本站是纯负担（泄露玩家 IP / 国内易超时 / 发版首访可能被强制刷新），故去掉外联。
      ⚠ 注意：Yw()（唯一触发 YlxwVersionLoad() 的函数）**唯一调用点就在 Kw() 里** ——
      删外联时必须保留 `Yw()` 调用，否则 YLVERSION_CACHE 恒为 null、顶栏永远显示兜底常量，
      「版本号动态化」会被静默废掉（ui-3 的 V19 用例就是抓这个）。
      同时补一条 `yl-version` 事件：缓存写入后 dispatch，Kw() 内订阅并 bump state，
      让顶栏在首次 fetch 返回后**确定性地**重渲染（不必等游戏自身的其它 re-render）。

锚点纪律：全部先 count() 实测（实测值见各 *_ANCHOR_COUNT 注释），纯 ASCII 子串。
          注入块亦为纯 ASCII，不依赖 zh()（仍走 zh() 以对齐构建约定）。
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CHANGELOG_LOCAL = os.path.join(HERE, 'CHANGELOG.md')

# 兜底版本（= 当前线上/本地 CHANGELOG 最新版；_test_version.py 会断言两者一致）
DEFAULT_VERSION = '0.9.47'

# ---------------------------------------------------------------------------
# 注入 JS 块（纯 ASCII；构建侧统一 zh()）
# ---------------------------------------------------------------------------
INJECT_JS = r'''
/* == YL_VERSION_DYNAMIC_V28 == */
var YLVERSION_FALLBACK = "0.9.47";
var YLVERSION_CACHE = null;
var YLVERSION_LOADED = false;
function YlxwVersionParse(text) {
  if (!text) return null;
  var lines = String(text).split("\n");
  for (var i = 0; i < lines.length; i++) {
    var m = lines[i].match(/^##\s*\[([0-9]+(?:\.[0-9]+)*)\]/);
    if (m) return m[1];
  }
  return null;
}
function YlxwVersionGet() {
  return YLVERSION_CACHE || YLVERSION_FALLBACK;
}
function YlxwVersionLoad() {
  if (YLVERSION_LOADED) return;
  YLVERSION_LOADED = true;
  try {
    fetch("/myxxz/CHANGELOG.md", { cache: "no-store" }).then(function (r) {
      return r && r.ok ? r.text() : Promise.reject(new Error("changelog fetch failed"));
    }).then(function (txt) {
      var v = YlxwVersionParse(txt);
      if (v) {
        YLVERSION_CACHE = v;
        try { localStorage.setItem("xiuxian-version-checked", v); } catch (e) {}
        try { window.dispatchEvent(new Event("yl-version")); } catch (e) {}
      }
    }).catch(function () {});
  } catch (e) {}
}
/* == end YL_VERSION_DYNAMIC_V28 == */
'''

# ---------------------------------------------------------------------------
# 锚点（实测 count 已核对，见注释）与替换体
# ---------------------------------------------------------------------------

# @573425  count=1
YW_ANCHOR = r'function Yw(){return"0.4.0"}'
# helper 块 + 新的 Yw（Yw 为基线唯一版本来源函数，改它即改「真源」）
YW_REPL = 'function Yw(){YlxwVersionLoad();return YlxwVersionGet()}'

# @732168  count=1  （主页头部徽标 E，渲染点 @734983 children:["v",E]）
HUB_ANCHOR = r'E="0.4.0",N=vd()'
HUB_REPL = r'E=YlxwVersionGet(),N=vd()'

# @1109983 count=1  （更新日志弹窗 CM 的「当前版本」比较基准 u）
CM_ANCHOR = r'const[a,l]=O.useState([]),[c,d]=O.useState(!0),u="0.4.0";'
CM_REPL = r'const[a,l]=O.useState([]),[c,d]=O.useState(!0),u=YlxwVersionGet();'

# @1129770 count=1  （设置页「游戏版本」）
SET_ANCHOR = r'children:["v","0.4.0"]'
SET_REPL = r'children:["v",YlxwVersionGet()]'

# @803389 count=1  （活动名 + 类型 + 倍率；name===typeName 时去重，保留倍率）
EVT_NAME_ANCHOR = (
    r'd.name + " \uff08" + (YLXW_ACT[d.type] || d.typeName) + " \u00d7"'
    r' + YlxwNum(d.multiplier) + "\uff09"'
)
EVT_NAME_REPL = (
    r'(YLXW_ACT[d.type] || d.typeName) === d.name'
    r' ? (d.name + " \u00d7" + YlxwNum(d.multiplier))'
    r' : (d.name + " \uff08" + (YLXW_ACT[d.type] || d.typeName)'
    r' + " \u00d7" + YlxwNum(d.multiplier) + "\uff09")'
)

# @803643 count=1  （活动行 YlxwRow 的 children 数组收尾；插在数组闭合 ']' 之前作为第二个子元素）
#   结构： "已结束" })] })] }, "e"+d.id)
#            \__span__/ \__div__/ \_row_/
#   row children 数组的 ']' 在第二组 })] 的末尾，故在其前插入 ", <desc 行>"
EVT_TAIL_ANCHOR = r'\u5df2\u7ed3\u675f" })] })] }, "e" + d.id);'
EVT_TAIL_REPL = (
    r'\u5df2\u7ed3\u675f" })] }), '
    r'd.desc ? e.jsx("div", { className: "text-xs text-stone-400 mt-1 leading-relaxed"'
    r', children: d.desc }) : null] }, "e" + d.id);'
)


# @1562820  count=1  （App 内以 Kw() 调用的版本检查 hook：基线每版本首访都外联 GitHub）
# 基线行为：fetch https://api.github.com/repos/JeasonLoop/react-xiuxian-game/releases/latest
#           → 把**上游仓库**的 release tag 与**本站** CHANGELOG 版本比较 → 若上游更大则
#             window.location.reload() 强制刷新页面（8s 超时）。
# 对本站（改过版本号、国内访问 GitHub 常超时）是纯负担：泄露玩家 IP、发版首访可能被强制刷新。
# 中性化：保留 useRef/useEffect 两处 hook 调用（维持 hook 顺序），效果体退化为置位闩。
GH_URL_ANCHOR = (
    r'const Fw="https://api.github.com/repos/JeasonLoop/react-xiuxian-game/releases/latest",'
    r'G0="xiuxian-version-checked";'
)
GH_URL_REPL = r'const Fw="",G0="xiuxian-version-checked";'

# 入口迁移（0.8.3）：更新日志面板的 fetch 由 /yl/ 改为 /myxxz/
CHG_FETCH_ANCHOR = 'fetch("/yl/CHANGELOG.md")'
CHG_FETCH_REPL = 'fetch("/myxxz/CHANGELOG.md")'

KW_ANCHOR = (
    r'function Kw(){const t=O.useRef(!1);O.useEffect(()=>{if(t.current)return;t.current=!0;'
    r'const r=Yw();if(localStorage.getItem(G0)===r)return;const a=new AbortController,'
    r'l=setTimeout(()=>a.abort(),8e3);return fetch(Fw,{signal:a.signal,'
    r'headers:{Accept:"application/vnd.github.v3+json"}}).then(c=>c.ok?c.json():Promise.reject())'
    r'.then(c=>{const d=(c.tag_name||c.name||"").replace(/^v/,"");'
    r'if(Xw(d,r)){localStorage.setItem(G0,r);window.location.reload()}'
    r'else localStorage.setItem(G0,r)}).catch(()=>{}).finally(()=>clearTimeout(l)),'
    r'()=>{clearTimeout(l),a.abort()}},[])}'
)
KW_REPL = (
    r'function Kw(){const t=O.useRef(!1);var s=O.useState(0),b=s[1];'
    r'O.useEffect(function(){t.current=!0;'
    r'var f=function(){try{b(function(x){return x+1})}catch(e){}};'
    r'try{window.addEventListener("yl-version",f)}catch(e){}'
    r'try{Yw()}catch(e){}'
    r'return function(){try{window.removeEventListener("yl-version",f)}catch(e){}}'
    r'},[])}'
)


def _parse_latest(text):
    """取 CHANGELOG 首个 '## [x.y.z]' 的版本号（与前端 YlxwVersionParse 同语义）。"""
    if not text:
        return None
    m = re.search(r'^##\s*\[([0-9]+(?:\.[0-9]+)*)\]', text, re.M)
    return m.group(1) if m else None


def local_changelog_version():
    try:
        with open(CHANGELOG_LOCAL, 'rb') as f:
            return _parse_latest(f.read().decode('utf-8'))
    except Exception:
        return None


def apply(p, ctx):
    """p = Patcher；ctx = {'zh': zh, 'base_text': str}
       返回 gates: list[(name, needle, expected, op, note)]，op ∈ {'==','>=','<='}"""
    zh = ctx['zh']
    block = zh(INJECT_JS)

    # --- #3 版本号动态化 ---------------------------------------------------
    # 1) 注入 helper，并把唯一版本来源函数 Yw() 改成读 helper
    p.replace('version-helper+yw', YW_ANCHOR, block + '\n' + YW_REPL,
              expect=1, note='注入 YL_VERSION_DYNAMIC_V28 并让 Yw() 动态取值')
    # 2) 主页头部徽标
    p.replace('version-hub-header', HUB_ANCHOR, HUB_REPL,
              expect=1, note='主页头部版本号改走 YlxwVersionGet()')
    # 3) 更新日志弹窗「当前版本」基准
    p.replace('version-changelog-modal', CM_ANCHOR, CM_REPL,
              expect=1, note='更新日志弹窗当前版本改走 YlxwVersionGet()')
    # 4) 设置页「游戏版本」
    p.replace('version-settings', SET_ANCHOR, SET_REPL,
              expect=1, note='设置页版本号改走 YlxwVersionGet()')

    # --- #4 限时活动详细说明 ------------------------------------------------
    # 5) name 与 typeName 重复时去重（保留 ×倍率）
    p.replace('events-name-dedupe', EVT_NAME_ANCHOR, EVT_NAME_REPL,
              expect=1, note='活动名与类型名相同时只显示一次，倍率保留')
    # 6) 活动行下方渲染服务端 desc（空则不渲染）
    p.replace('events-desc-line', EVT_TAIL_ANCHOR, EVT_TAIL_REPL,
              expect=1, note='渲染 /api/events 已返回但此前未用的 desc 字段')

    # --- 入口迁移：更新日志面板的 fetch 路径 /yl/ -> /myxxz/（0.8.3）--------
    p.replace('changelog-path-moyu', CHG_FETCH_ANCHOR, CHG_FETCH_REPL,
              expect=1, note='更新日志面板 fetch 改走新入口（旧路径虽 301 可达，但少一跳）')

    # --- #3b 去掉上游 GitHub 版本检查（外联 + 误触强制刷新）------------------
    p.replace('vercheck-url', GH_URL_ANCHOR, GH_URL_REPL,
              expect=1, note='清空上游 GitHub releases 地址（外联 + IP 泄露）')
    p.replace('vercheck-kw', KW_ANCHOR, KW_REPL,
              expect=1, note='Kw() 中性化：保留 2 处 hook，去掉 fetch/reload')

    return [
        # ---- #3 版本号 ----
        ('version·Get helper 定义',      'function YlxwVersionGet(',                            1, '==', ''),
        ('version·Parse helper 定义',    'function YlxwVersionParse(',                          1, '==', ''),
        ('version·Load helper 定义',     'function YlxwVersionLoad(',                           1, '==', ''),
        # ★ 2026-10-01：这一条改成**从 DEFAULT_VERSION 派生**，以后升版只需改一处常量，
        #   不必再回来手改门禁名/锚点（原来每升一版都要在这里改一次，容易漏）。
        ('version·兜底常量=%s' % DEFAULT_VERSION,
         'var YLVERSION_FALLBACK = "%s"' % DEFAULT_VERSION,                                    1, '==', ''),
        ('version·旧兜底 0.9.46 已清零', 'var YLVERSION_FALLBACK = "0.9.46"',                   0, '==', ''),
        ('version·旧兜底 0.9.45 已清零', 'var YLVERSION_FALLBACK = "0.9.45"',                   0, '==', ''),
        ('version·旧兜底 0.9.44 已清零', 'var YLVERSION_FALLBACK = "0.9.44"',                   0, '==', ''),
        ('version·旧兜底 0.9.43 已清零', 'var YLVERSION_FALLBACK = "0.9.43"',                   0, '==', ''),
        ('version·旧兜底 0.9.42 已清零', 'var YLVERSION_FALLBACK = "0.9.42"',                   0, '==', ''),
        ('version·旧兜底 0.9.20 已清零', 'var YLVERSION_FALLBACK = "0.9.20"',                   0, '==', ''),
        ('version·旧兜底 0.9.19 已清零', 'var YLVERSION_FALLBACK = "0.9.19"',                   0, '==', ''),
        ('version·旧兜底 0.9.18 已清零', 'var YLVERSION_FALLBACK = "0.9.18"',                   0, '==', ''),
        ('version·旧兜底 0.9.17 已清零', 'var YLVERSION_FALLBACK = "0.9.17"',                   0, '==', ''),
        ('version·旧兜底 0.9.16 已清零', 'var YLVERSION_FALLBACK = "0.9.16"',                   0, '==', ''),
        ('version·旧兜底 0.9.15 已清零', 'var YLVERSION_FALLBACK = "0.9.15"',                   0, '==', ''),
        ('version·旧兜底 0.9.14 已清零', 'var YLVERSION_FALLBACK = "0.9.14"',                   0, '==', ''),
        ('version·旧兜底 0.9.13 已清零', 'var YLVERSION_FALLBACK = "0.9.13"',                   0, '==', ''),
        ('version·旧兜底 0.9.12 已清零', 'var YLVERSION_FALLBACK = "0.9.12"',                   0, '==', ''),
        ('version·旧兜底 0.9.11 已清零', 'var YLVERSION_FALLBACK = "0.9.11"',                   0, '==', ''),
        ('version·旧兜底 0.9.10 已清零', 'var YLVERSION_FALLBACK = "0.9.10"',                   0, '==', ''),
        ('version·旧兜底 0.9.9 已清零',  'var YLVERSION_FALLBACK = "0.9.9"',                    0, '==', ''),
        ('version·旧兜底 0.9.8 已清零',  'var YLVERSION_FALLBACK = "0.9.8"',                    0, '==', ''),
        ('version·旧兜底 0.9.7 已清零',  'var YLVERSION_FALLBACK = "0.9.7"',                    0, '==', ''),
        ('version·旧兜底 0.9.6 已清零',  'var YLVERSION_FALLBACK = "0.9.6"',                    0, '==', ''),
        ('version·旧兜底 0.9.5 已清零',  'var YLVERSION_FALLBACK = "0.9.5"',                    0, '==', ''),
        ('version·旧兜底 0.9.4 已清零',  'var YLVERSION_FALLBACK = "0.9.4"',                    0, '==', ''),
        ('version·旧兜底 0.9.3 已清零',  'var YLVERSION_FALLBACK = "0.9.3"',                    0, '==', ''),
        ('version·旧兜底 0.9.2 已清零',  'var YLVERSION_FALLBACK = "0.9.2"',                    0, '==', ''),
        ('version·旧兜底 0.9.1 已清零',  'var YLVERSION_FALLBACK = "0.9.1"',                    0, '==', ''),
        ('version·旧兜底 0.9.0 已清零',  'var YLVERSION_FALLBACK = "0.9.0"',                    0, '==', ''),
        ('version·旧兜底 0.8.11.13 已清零','var YLVERSION_FALLBACK = "0.8.11.13"',               0, '==', ''),
        ('version·旧兜底 0.8.11.12 已清零','var YLVERSION_FALLBACK = "0.8.11.12"',               0, '==', ''),
        ('version·旧兜底 0.8.11.11 已清零','var YLVERSION_FALLBACK = "0.8.11.11"',               0, '==', ''),
        ('version·旧兜底 0.8.11.10 已清零','var YLVERSION_FALLBACK = "0.8.11.10"',               0, '==', ''),
        ('version·旧兜底 0.8.11.9 已清零', 'var YLVERSION_FALLBACK = "0.8.11.9"',                 0, '==', ''),
        ('version·旧兜底 0.8.11.8 已清零', 'var YLVERSION_FALLBACK = "0.8.11.8"',                0, '==', ''),
        ('version·旧兜底 0.8.11.7 已清零', 'var YLVERSION_FALLBACK = "0.8.11.7"',                0, '==', ''),
        ('version·旧兜底 0.8.11.3 已清零', 'var YLVERSION_FALLBACK = "0.8.11.3"',                0, '==', ''),
        ('version·旧兜底 0.8.11.2 已清零', 'var YLVERSION_FALLBACK = "0.8.11.2"',                0, '==', ''),
        ('version·旧兜底 0.8.11.1 已清零', 'var YLVERSION_FALLBACK = "0.8.11.1"',                0, '==', ''),
        ('version·旧兜底 0.8.11 已清零',  'var YLVERSION_FALLBACK = "0.8.11"',                  0, '==', ''),
        ('version·旧兜底 0.8.10 已清零',  'var YLVERSION_FALLBACK = "0.8.10"',                  0, '==', ''),
        ('version·单次加载闩',           'YLVERSION_LOADED',                                    3, '>=', ''),
        ('version·写回本地缓存',         'localStorage.setItem("xiuxian-version-checked"',      1, '==', ''),
        ('version·Yw 已动态',           'function Yw(){YlxwVersionLoad();return YlxwVersionGet()}', 1, '==', ''),
        ('version·主页头部已动态',       'E=YlxwVersionGet(),N=vd()',                            1, '==', ''),
        ('version·日志弹窗已动态',       'u=YlxwVersionGet();',                                  1, '==', ''),
        ('version·设置页已动态',         'children:["v",YlxwVersionGet()]',                      1, '==', ''),
        ('version·动态取值点 >=4',       'YlxwVersionGet()',                                     4, '>=', ''),
        ('version·硬编码 0.4.0 清零',    '0.4.0',                                                0, '==', '必须为 0'),
        ('version·helper 只注入一次',    'YL_VERSION_DYNAMIC_V28',                               2, '==', '起止标记'),
        # ---- 既有更新日志面板未被破坏 ----
        ('changelog·面板开关仍在',       'YLChgOpen',                                           2, '==', ''),
        ('changelog·按钮仍在',           'YLSetChg(!0)',                                         1, '==', ''),
        ('changelog·fetch 仍在',         'fetch("/myxxz/CHANGELOG.md")',                         1, '==', ''),
        ('changelog·旧 /yl/ 路径清零',   '"/yl/CHANGELOG.md"',                                   0, '==', '入口迁移后不得残留'),
        ('changelog·新路径共 2 处',      '"/myxxz/CHANGELOG.md"',                                2, '==', 'INJECT_JS 1 + 面板 1'),
        ('changelog·CM 解析器仍在',      'const f=async()=>{d(!0);try{const x=await fetch',       1, '==', ''),
        # ---- #4 活动面板 ----
        ('events·面板仍在',              'function YlxwTEvents()',                               1, '==', ''),
        ('events·desc 已渲染',           'd.desc ? e.jsx("div"',                                 1, '==', ''),
        ('events·name 去重已注入',       '(YLXW_ACT[d.type] || d.typeName) === d.name ?',        1, '==', ''),
        ('events·完整分支仅剩一处',      EVT_NAME_ANCHOR,                                        1, '==', '原串只剩在三元 else 分支里'),
        ('events·desc 三元包裹',         ': null] }, "e" + d.id);',                              1, '==', ''),
        ('events·状态行未被破坏',        'YlxwMin(YlxwNum(d.leftMs))',                           1, '==', ''),
        # ---- #3b 上游 GitHub 版本检查已移除 ----
        ('vercheck·GitHub 外联已移除',   'api.github.com',                                       0, '==', '必须为 0'),
        ('vercheck·旧检查头已移除',      'application/vnd.github.v3+json',                       0, '==', '必须为 0'),
        ('vercheck·Fw 常量已清空',       'const Fw="",G0="xiuxian-version-checked";',            1, '==', ''),
        ('vercheck·Kw 已去外联',         'function Kw(){const t=O.useRef(!1);var s=O.useState(0),b=s[1];', 1, '==', ''),
        ('vercheck·Kw 仍触发版本加载',   'try{Yw()}catch(e){}',                                  1, '==', 'Yw() 的唯一调用点，删掉则版本号恒为兜底值'),
        ('vercheck·版本事件已派发',      'window.dispatchEvent(new Event("yl-version"))',         1, '==', '缓存更新后驱动重渲染'),
        ('vercheck·版本事件已订阅',      'window.addEventListener("yl-version",f)',              1, '==', ''),
        ('vercheck·hook 数量保持',       'O.useRef(!1)',                                         1, '>=', 'useRef 仍在'),
    ]
