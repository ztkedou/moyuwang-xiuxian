# -*- coding: utf-8 -*-
r"""
yl_r144_ext.py — R-144 在线人物徽章 → 可点按钮 → 在线人物 / 好友面板（纯客户端）

需求原文（台账 R-144）
--------------------------------------------------------------------------
  「现在的在线人物那里只显示数字，把这个做成一个按钮，点击可以展示在线人物列表，
    可以把交友的这些功能做进去」

基线 = build/assets/index-v26m-20260927.js
       1,583,034 B / 1,419,571 chars
       md5 b315eb1a04e967a66c128861b3a3dadd

==============================================================================
一、侦察结论（字符级实测，全部 count==1）
==============================================================================

【1】在线人数徽章（顶部状态栏内，ASCII 前缀 count==1）：
      C>0&&e.jsxs("span",{className:"text-xs md:text-sm text-green-400 font-mono px-2
      py-1 bg-green-900/30 rounded border border-green-700 flex items-center gap-1",title:
      ... title:"当前在线人数",children:[e.jsx(um,{size:12}),C]})   ← 中文只出现在 title
      锚点只取到 `title:` 之前（纯 ASCII），中文段原样保留。

【2】在线人数来源 = party hook `function y4(t="main",r=150)` →
      `let Gr=null,Li=[],Lr=[],Dr=0;`（模块级 let，b4 单例 socket）。
      消息类型**只有** `onlineCountUpdate` / `welcome`；实测 `sendMessage(` 调用点 0 个
      ⇒ party **只给人数、不给名单**（与需求侦察一致）。

【3】「在线人物」可用的真实名单来源 = **服务端聊天**（已存在、无需登录态）：
      `async function kk(t=0,r=50)` → GET `${u1()}/messages?after=&limit=`
      返回 `{messages:[{id,type:"chat",user,text,timestamp}]}`，`user` = 角色名。
      ⇒ 用「最近发言者去重」近似「在线人物」（下方已注明该近似性）。

【4】交友 API（服务端已有，客户端此前 0 处调用，实测 `/api/friends/*` count==0）：
      GET  /api/friends/list            → {max,giftsLeftToday,friends:[{id,name,realmName,level,giftedToday}]}
      POST /api/friends/add    {name}   → {ok,friend}
      POST /api/friends/remove {friendId}
      POST /api/friends/gift   {friendId} → {ok,quality,stones}
      客户端封装（已存在、带鉴权/token/重试）：`async function YlxwApi(r,t)`
      `function YlxwGet(r)` / `function YlxwPost(r,t)` —— 本补丁直接复用，不自造 fetch。

【5】注入方式：把面板代码 append 到 bundle 末尾（渲染入口之后），
      仍在同一模块作用域 ⇒ 可直接引用 `Dr` / `Lr` / `kk` / `YlxwGet` / `YlxwPost` / `Et`。
      面板用纯 DOM + 复用 Rk 聊天面板已验证存在的 Tailwind 类（编译后 CSS 实测命中）。

==============================================================================
二、改动清单（2 处，均纯 ASCII 锚点、count==1）
==============================================================================
  E1 徽章 span → button（去掉 C>0&& 守卫，始终可点；派发 open-online-panel）
  E2 尾部渲染入口后 append 面板 IIFE（监听 open-online-panel）

  ★ 只改客户端；服务端 srv/** 零改动；不改 party / 聊天面板 / 战斗 / 存档。
  ★ 取舍 = 方案 (a)：上半「最近在线道友」（近似），下半「好友列表 + 加/删/赠」。
    party 无名单 ⇒ 名单改用服务端聊天最近发言者；人数仍用 party 实时值。

==============================================================================
三、契约（standalone，同 localtest/yl_r143_ext.py）
==============================================================================
  · CLI 只有 `--src <js>`；二进制读写；就地原子写回（mkstemp + os.replace）。
  · 首次改写前落 <src>.bak-r144-<时刻>；重跑已补丁文件不写盘（幂等，rc=3）。
  · 退出码：0=成功改；3=已应用；2=预检失败（锚点/部分补丁态）；1=其它错误。
  · `gates()` 五元组 (name, needle, count, op, note)；`_precheck()` + 往返自证。
  · 纯客户端；不改 build_v26n.py / dryrun_087.py / build/assets/* / 其它 yl_*_ext.py。
"""

import argparse
import io
import os
import sys
import tempfile
from datetime import datetime

# --------------------------------------------------------------------------- 在位标记

MARK = 'YLXW_R144_V2919'          # 全局唯一，与 R140B_V2919 / R141_V2919 / R142_V2918 / R143_V2918 互不包含
OTHER_MARKS = ['YLXW_R140_V2916', 'YLXW_R140B_V2919', 'YLXW_R141_V2919', 'YLXW_R142_V2918',
               'YLXW_R143_V2918', 'YLXW_R145_V2919', 'YLXW_R146_V2919']

# --------------------------------------------------------------------------- 锚点（纯 ASCII、count==1）

# E1：在线人数徽章的 ASCII 前缀（到 title: 为止，中文 title 值原样保留）
OLD_BADGE = (
    'C>0&&e.jsxs("span",{className:"text-xs md:text-sm text-green-400 font-mono px-2 py-1 '
    'bg-green-900/30 rounded border border-green-700 flex items-center gap-1",title:'
)
# 去掉 C>0&& 守卫 + span→button + onClick 派发 CustomEvent；类名沿用原徽章（保证样式）
NEW_BADGE = (
    'e.jsxs("button",{type:"button",onClick:()=>window.dispatchEvent(new CustomEvent('
    '"open-online-panel")),className:"text-xs md:text-sm text-green-400 font-mono px-2 py-1 '
    'bg-green-900/30 rounded border border-green-700 flex items-center gap-1 cursor-pointer '
    'active:scale-95",title:'
)

# E2：bundle 末尾渲染入口（count==1，纯 ASCII）
TAIL = 'const yC=O2.createRoot(p1);yC.render(e.jsx(Rt.StrictMode,{children:e.jsx(bC,{})}));'

# 面板 IIFE（纯 DOM，复用 Rk 已验证存在的 Tailwind 类；只引用模块内既有助手）
PANEL = r'''
/*YLXW_R144_V2919*/
(function(){
if(window.__ylR144)return;window.__ylR144=1;
var onl=(typeof Dr==="number"?Dr:0),selfName="";
try{var _es=Et&&Et.getState&&Et.getState();selfName=(_es&&_es.user&&(_es.user.name||_es.user.username))||"";}catch(e){}
try{Lr.push(function(n){onl=n;var b=document.getElementById("yl-r144-onl");if(b)b.textContent="在线 "+n;});}catch(e){}
function MK(tag,cls,txt){var d=document.createElement(tag);if(cls)d.className=cls;if(txt!=null)d.textContent=String(txt);return d;}
var ov=null,bodyEl=null,tabsEl=null,statusEl=null,tab="online",recent=[],friends=[],fmeta={};
function st(m){if(statusEl)statusEl.textContent=m||"";}
function closeP(){if(ov&&ov.parentNode)ov.parentNode.removeChild(ov);ov=null;bodyEl=null;tabsEl=null;statusEl=null;}
function btn(label,cls,fn){var b=MK("button",cls||"text-xs px-2 py-1 rounded bg-amber-500/20 text-amber-200 border border-amber-500/30 cursor-pointer active:scale-95",label);b.type="button";b.onclick=function(ev){if(ev)ev.preventDefault();try{fn();}catch(e){st("出错："+(e&&e.message||e));}};return b;}
function row(name,sub,acts){var r=MK("div","flex items-center justify-between gap-2 px-2 py-1 mb-1 rounded bg-stone-800/60");var L=MK("div","flex flex-col min-w-0");L.appendChild(MK("span","text-xs text-amber-200 truncate",name));if(sub)L.appendChild(MK("span","text-[10px] text-stone-400 truncate",sub));r.appendChild(L);var R=MK("div","flex items-center gap-1");(acts||[]).forEach(function(x){R.appendChild(x);});r.appendChild(R);return r;}
function renderBody(){
if(!bodyEl)return;bodyEl.innerHTML="";
if(tab==="online"){
bodyEl.appendChild(MK("div","text-[10px] text-stone-400 mb-2","最近在线道友（取自最近发言，可能不全）"));
if(!recent.length){bodyEl.appendChild(MK("div","text-xs text-stone-500 p-2","暂无在线道友信息"));return;}
recent.forEach(function(u){if(u===selfName)return;bodyEl.appendChild(row(u,"",[btn("加好友",null,function(){YlxwPost("/friends/add",{name:u}).then(function(){st("已加 "+u+" 为好友");loadFriends();}).catch(function(e){st(e&&e.message||"添加失败");});})]));});
}else{
bodyEl.appendChild(MK("div","text-[10px] text-stone-400 mb-2","好友 "+(friends.length||0)+"/"+(fmeta.max||"?")+"　今日可赠丹 "+(fmeta.left==null?"?":fmeta.left)));
if(!friends.length){bodyEl.appendChild(MK("div","text-xs text-stone-500 p-2","还没有好友，去在线人物里加一个吧"));return;}
friends.forEach(function(f){var sub=(f.realmName||"")+(f.level?" Lv."+f.level:"");var g=btn(f.giftedToday?"今日已赠":"赠灵石",null,function(){if(f.giftedToday)return;YlxwPost("/friends/gift",{friendId:f.id}).then(function(d){st("赠丹成功："+(d&&d.quality||"")+" 灵石 x"+(d&&d.stones||0));loadFriends();}).catch(function(e){st(e&&e.message||"赠丹失败");});});var rm=btn("删除","text-xs px-2 py-1 rounded bg-stone-800 text-red-400 border border-stone-600 cursor-pointer active:scale-95",function(){YlxwPost("/friends/remove",{friendId:f.id}).then(function(){st("已删除 "+f.name);loadFriends();}).catch(function(e){st(e&&e.message||"删除失败");});});bodyEl.appendChild(row(f.name,sub,[g,rm]));});
}}
function loadOnline(){st("加载在线人物…");try{kk(0,60).then(function(ms){var seen={},out=[];(ms||[]).forEach(function(m){var u=m&&m.user;if(u&&!seen[u]){seen[u]=1;out.push(u);}});recent=out.slice(-40).reverse();renderBody();st("");}).catch(function(){renderBody();st("在线人物加载失败");});}catch(e){st("在线人物加载失败");}}
function loadFriends(){st("加载好友…");try{YlxwGet("/friends/list").then(function(d){friends=(d&&d.friends)||[];fmeta={max:d&&d.max,left:d&&d.giftsLeftToday};renderBody();st("");}).catch(function(e){st(e&&e.message||"好友加载失败");renderBody();});}catch(e){st(e&&e.message||"好友加载失败");}}
function tabBtn(label,key){var b=MK("button","text-xs px-3 py-1 rounded cursor-pointer "+(tab===key?"bg-amber-500/20 text-amber-200 border border-amber-500/30":"text-stone-400 border border-transparent"),label);b.type="button";b.onclick=function(){tab=key;renderTabs();renderBody();if(key==="online")loadOnline();else loadFriends();};return b;}
function renderTabs(){if(!tabsEl)return;tabsEl.innerHTML="";tabsEl.appendChild(tabBtn("在线人物","online"));tabsEl.appendChild(tabBtn("好友列表","friends"));}
function open(){
if(ov)return;
ov=MK("div","fixed inset-0 z-[70] bg-black/70 flex items-center justify-center p-4");
ov.onclick=function(ev){if(ev.target===ov)closeP();};
var box=MK("div","w-full max-w-md max-h-[80vh] bg-stone-900/95 backdrop-blur-xl border border-amber-500/30 rounded-lg overflow-hidden flex flex-col");
var hd=MK("div","p-3 bg-stone-800 border-b border-amber-500/20 flex items-center justify-between");
var hl=MK("div","flex items-center gap-2");hl.appendChild(MK("span","text-sm font-bold text-amber-200","在线人物 · 好友"));var ob=MK("span","text-[10px] text-green-400","在线 "+onl);ob.id="yl-r144-onl";hl.appendChild(ob);
var cl=MK("button","text-stone-400 cursor-pointer px-2 py-1","关闭");cl.type="button";cl.onclick=closeP;
hd.appendChild(hl);hd.appendChild(cl);
tabsEl=MK("div","flex items-center gap-1 px-3 pt-2");
bodyEl=MK("div","flex-1 overflow-y-auto p-3");
statusEl=MK("div","text-[10px] text-stone-400 px-3 pb-2","");
box.appendChild(hd);box.appendChild(tabsEl);box.appendChild(bodyEl);box.appendChild(statusEl);
ov.appendChild(box);document.body.appendChild(ov);
renderTabs();renderBody();loadOnline();loadFriends();
}
window.addEventListener("open-online-panel",open);
})();'''

TAIL_NEW = TAIL + PANEL

EDITS = [
    ('R144 在线徽章 span→button（派发 open-online-panel）', OLD_BADGE, NEW_BADGE),
    ('R144 末尾注入在线人物/好友面板', TAIL, TAIL_NEW),
]

# --------------------------------------------------------------------------- 新增 needle

M_BTN = (
    'e.jsxs("button",{type:"button",onClick:()=>window.dispatchEvent(new CustomEvent('
    '"open-online-panel")),className:"text-xs md:text-sm text-green-400 font-mono px-2 py-1 '
    'bg-green-900/30 rounded border border-green-700 flex items-center gap-1 cursor-pointer '
    'active:scale-95",title:'
)
M_LISTEN = 'window.addEventListener("open-online-panel",open);'
M_OPEN = 'ov=MK("div","fixed inset-0 z-[70] bg-black/70 flex items-center justify-center p-4");'
M_TITLE = '"在线人物 · 好友"'
M_ONLINE_FN = 'function loadOnline(){st("加载在线人物…")'
M_KK = 'kk(0,60)'
M_LIST = 'YlxwGet("/friends/list")'
M_ADD = 'YlxwPost("/friends/add",{name:u})'
M_RM = 'YlxwPost("/friends/remove",{friendId:f.id})'
M_GIFT = 'YlxwPost("/friends/gift",{friendId:f.id})'
M_OLDGONE = OLD_BADGE  # 补丁后应为 0 次（span/守卫已被替换）

# --------------------------------------------------------------------------- 冻结门禁串（不得改动）

FRZ_TITLE = 'title:"当前在线人数"'
FRZ_BADGE_CLS = (
    'text-xs md:text-sm text-green-400 font-mono px-2 py-1 bg-green-900/30 rounded '
    'border border-green-700 flex items-center gap-1'
)
FRZ_PARTY = 'https://xiuxian-game-party.dnzzk2.partykit.dev/'
FRZ_PARTY_STATE = 'let Gr=null,Li=[],Lr=[],Dr=0;'
FRZ_CHAT = 'const Rk=({playerName:t})=>'
FRZ_KKFN = 'async function kk(t=0,r=50){'
FRZ_YAPI = 'async function YlxwApi(r, t) {'
FRZ_TAIL = TAIL


def gates():
    """补丁后形态的门禁五元组 (name, needle, count, op, note) —— 供 dryrun 门禁表收录。"""
    return [
        ('R144·在位标记唯一存在', MARK, 1, '==', 'YLXW_R144_V2919'),
        ('R144·徽章已变按钮并派发事件', M_BTN, 1, '==', 'span→button + open-online-panel'),
        ('R144·旧 span/守卫已移除', M_OLDGONE, 0, '==', 'C>0&&e.jsxs("span"... 应消失'),
        ('R144·面板监听已注入', M_LISTEN, 1, '==', 'open-* CustomEvent 模式'),
        ('R144·面板根节点已注入', M_OPEN, 1, '==', 'fixed inset-0 遮罩'),
        ('R144·面板标题已注入', M_TITLE, 1, '==', '在线人物 · 好友'),
        ('R144·在线人物加载已注入', M_ONLINE_FN, 1, '==', ''),
        ('R144·复用聊天拉取 kk(0,60)', M_KK, 1, '==', '最近发言者来源'),
        ('R144·好友列表 API 已接', M_LIST, 1, '==', 'YlxwGet(/friends/list)'),
        ('R144·加好友 API 已接', M_ADD, 1, '==', 'YlxwPost(/friends/add)'),
        ('R144·删好友 API 已接', M_RM, 1, '==', 'YlxwPost(/friends/remove)'),
        ('R144·赠灵石 API 已接', M_GIFT, 1, '==', 'YlxwPost(/friends/gift)'),
        ('冻结·徽章 title 未动', FRZ_TITLE, 1, '==', ''),
        ('冻结·徽章类名未动', FRZ_BADGE_CLS, 1, '==', '沿用原样式类'),
        ('冻结·party 主机未动', FRZ_PARTY, 1, '==', ''),
        ('冻结·party 单例状态未动', FRZ_PARTY_STATE, 1, '==', ''),
        ('冻结·聊天面板未动', FRZ_CHAT, 1, '==', 'const Rk=({playerName:t})=>'),
        ('冻结·kk 拉取函数未动', FRZ_KKFN, 1, '==', ''),
        ('冻结·YlxwApi 封装未动', FRZ_YAPI, 1, '==', ''),
        ('冻结·渲染入口未动', FRZ_TAIL, 1, '==', '面板 append 其后'),
    ]


def _precheck():
    """补丁前常量自检（断言失败 → rc=1）。"""
    for name, old, new in EDITS:
        assert old != new, '%s 新旧锚点相同（恒等替换）' % name
    # 锚点纯 ASCII
    for nm, s in (('OLD_BADGE', OLD_BADGE), ('TAIL', TAIL)):
        assert all(ord(ch) < 128 for ch in s), '%s 必须纯 ASCII' % nm
    # 在位标记互不包含
    for om in OTHER_MARKS:
        assert MARK != om and MARK not in om and om not in MARK, 'MARK 与 %s 冲突' % om
    # 新增 needle 落在 NEW 内、且不在 OLD 内
    assert MARK in TAIL_NEW and M_BTN in NEW_BADGE and M_LISTEN in TAIL_NEW
    assert M_OPEN in TAIL_NEW and M_TITLE in TAIL_NEW and M_ONLINE_FN in TAIL_NEW
    assert M_KK in TAIL_NEW and M_LIST in TAIL_NEW and M_ADD in TAIL_NEW
    assert M_RM in TAIL_NEW and M_GIFT in TAIL_NEW
    assert M_BTN not in OLD_BADGE and MARK not in OLD_BADGE
    assert TAIL_NEW.startswith(TAIL) and TAIL_NEW.count(TAIL) == 1, 'TAIL 必须为前缀且仅一次'
    # 每个新增 needle 在 NEW 中恰出现一次
    for nm, s in (('MARK', MARK), ('M_LISTEN', M_LISTEN), ('M_OPEN', M_OPEN),
                  ('M_TITLE', M_TITLE), ('M_ONLINE_FN', M_ONLINE_FN), ('M_KK', M_KK),
                  ('M_LIST', M_LIST), ('M_ADD', M_ADD), ('M_RM', M_RM), ('M_GIFT', M_GIFT)):
        assert TAIL_NEW.count(s) == 1, '%s 在 NEW 中必须恰出现一次' % nm
    assert NEW_BADGE.count(M_BTN) == 1, 'M_BTN 在 NEW_BADGE 中必须恰出现一次'
    # 注入块不得自造网络调用（复用 YlxwGet/YlxwPost/kk）
    assert 'fetch(' not in PANEL, '注入块不得含 fetch('
    assert 'XMLHttpRequest' not in PANEL, '注入块不得含 XMLHttpRequest'
    # 注入块不得误含其它补丁标记
    for om in OTHER_MARKS:
        assert om not in PANEL, '注入块不得含既有标记 %s' % om
    # E2 为 append 型（TAIL 为 TAIL_NEW 前缀）
    assert TAIL_NEW.startswith(TAIL)


def _count(txt, needle):
    n, i = 0, 0
    while True:
        i = txt.find(needle, i)
        if i < 0:
            return n
        n += 1
        i += len(needle)


def _gate_ok(act, exp, op):
    if op == '==':
        return act == exp
    if op == '>=':
        return act >= exp
    if op == '<=':
        return act <= exp
    raise ValueError('unknown op: %r' % op)


def main() -> int:
    ap = argparse.ArgumentParser(description='R-144 在线人物/好友面板（客户端 --src 补丁）')
    ap.add_argument('--src', required=True, help='装配产物 js（如 build/assets/index-v26m-*.js）')
    a = ap.parse_args()
    src_path = a.src

    try:
        _precheck()
    except AssertionError as e:
        print('[FAIL] 断言失败: %s' % e)
        return 1

    if not os.path.exists(src_path):
        print('[FAIL] source not found: %s' % src_path)
        return 2
    with io.open(src_path, 'rb') as f:
        src = f.read()

    olds = [o.encode('utf-8') for _, o, _ in EDITS]
    news = [n.encode('utf-8') for _, _, n in EDITS]

    txt0 = src.decode('utf-8', errors='replace')

    # 1) 幂等 / 部分补丁态（以在位标记 + 按钮 + 监听 needle 为判据）
    needles = [MARK, M_BTN, M_LISTEN]
    if MARK in txt0:
        if all(m in txt0 for m in needles):
            print('[SKIP] source looks already patched（R-144 在位标记与新增 needle 齐备）')
            return 3
        print('[FAIL] 检测到部分补丁态（在位标记存在但新增 needle 不齐），拒绝写盘')
        return 2

    # 2) 锚点计数（rc=2 面）
    for (name, _old, _new), ob in zip(EDITS, olds):
        n = src.count(ob)
        if n != 1:
            print('[FAIL] %s 锚点出现 %d 次（期望 1）' % (name, n))
            return 2
    # 新增 needle 在补丁前必须为 0（防重复注入 / 混入其它补丁）
    for nm, s in (('在位标记', MARK), ('按钮 needle', M_BTN), ('监听 needle', M_LISTEN),
                  ('面板根节点', M_OPEN), ('好友列表 needle', M_LIST)):
        if txt0.count(s) != 0:
            print('[FAIL] %s 已存在（疑部分补丁态）' % nm)
            return 2

    # 3) 应用（字节级单点替换）
    out = src
    for (name, _old, _new), ob, nb in zip(EDITS, olds, news):
        out = out.replace(ob, nb, 1)

    # 4) 门禁
    ok = True
    text = out.decode('utf-8', errors='replace')
    gs = gates()
    for label, needle, exp, op, note in gs:
        act = _count(text, needle)
        good = _gate_ok(act, exp, op)
        ok = ok and good
        print('  [%s] %-34s actual=%d expect%s%d %s' % (
            'OK' if good else 'FAIL', label, act, op, exp, note))
    if not ok:
        print('[FAIL] 门禁未全绿，未写盘')
        return 1
    print('  门禁: %d/%d PASS, FAIL 0' % (len(gs), len(gs)))

    # 5) 往返自证
    back = out
    for ob, nb in zip(olds, news):
        back = back.replace(nb, ob, 1)
    if back != src:
        print('[FAIL] round-trip mismatch')
        return 1
    print('  往返自证: 新串→旧串 与源逐字节相同 OK')

    print('  delta = %+d bytes  (%d -> %d)' % (len(out) - len(src), len(src), len(out)))

    # 6) 改前 .bak + 原子写回（二进制）
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    bak = src_path + '.bak-r144-' + ts
    with io.open(bak, 'wb') as f:
        f.write(src)
    print('  已备份原文件 -> %s' % bak)
    d = os.path.dirname(os.path.abspath(src_path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.r144-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out)
        os.replace(tmp, src_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print('  已原子写回 %s' % src_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
