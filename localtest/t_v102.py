# -*- coding: utf-8 -*-
r"""
t_v102.py — v1.2（PM-101 E2 私信按钮布局修复 + 私信升级私聊取消限频）浏览器全栈实测（本机临时环境，不碰线上）

被测对象（fail-closed 指纹校验，不符即退出，绝不产出半成品）：
    bundle = build/assets/index-v102-20261022.js   md5 66cf2890172dc15c8a8fdff9f8c41940
    服务端 = srv/index_v28.ts                      md5 51270cba95846bb75da818d99b012e5c

【A1 结构对照基准（与 v100 产物逐字对照，本文件写作前已从三个产物中提取原文）】
  v100（1.0 原始位型，index-v100-20261020.js @YlxwTFriends map）：
    YlxwRow > div.flex.items-center.justify-between.gap-2.flex-wrap > [ span(name·realm),
              (giftedToday ? span今日已送礼 : YlxwBtn「送礼」) ]                     ← 送礼=行右端唯一控件
  1.1 线上产物（Azure /opt/yl/www/assets/index-v101-20261021.js，md5 75adea61…，本脚本外拉取对照）：
    同行 > [ span, YlxwBtn送礼, YlxwBtn私信 ]  ← 私信直接追加为第 3 个行子元素，
              justify-between 三子摊开 ⇒ 送礼被挤离右端（=1.1 布局 bug，CHANGELOG [1.2] 修复段原文）
  v102（被测，index-v102-20261022.js @YlxwTFriends map）：
    同行 > [ span(name·realm), div.flex.items-center.gap-1 > [送礼钮|今日已送礼span, 私信钮] ]
              ← 送礼回到右端组首位、私信紧邻同组（justify-between 恢复 2 子）
  「在线人物」行（r144 面板 onlineRow，live1.1 与 v102 逐字相同）：行 > [左名组, div.flex.items-center.gap-1 >
    [已好友|加好友, 拜师, 切磋, 私信]] —— 私信恒为组末位；该行无送礼控件（CHANGELOG：维持切磋钮后
    acts.push 私信钮，DOM 栈无布局回归），故在线行断言=分组/间距/相邻/不错位/不溢出。

环境（沿用 v1.0/v1.1 实测方案：起服+测试同一条命令内完成；先清残留监听；独立端口 3323/3423）：
    服务端：workbuddy-ai node 22.22.2-6 --experimental-strip-types 直跑 dev/srv/index_v28.ts
            独立 DATABASE_PATH=临时库；GM_PASSWORD/JWT_SECRET 随机生成仅经子进程环境变量传递、绝不落盘
    静态壳：localtest/harness.js --root=dev --bundle=index-v102-20261022.js（/myxxz/ + /yl/ 别名 + /api 反代 + no-store）
    浏览器：workbuddy-ai python（唯一带 playwright）+ launch_persistent_context，账号页严格串行
            （服务端单写者会话守卫：同账号两页并存会把旧页挤成只读）
    测试钩子：bundle 尾部追加 window.__Be/__YLogs（route.fulfill + no-store + setInterval 500ms 自愈重挂）

断言清单（全过才算 ok）：
    A1 1440 与 390：仙友录好友行 =「v100 原始位型 + 私信同组并入」：行恰 2 子（justify-between 恢复 2 子）、
       行末组 div.flex.items-center.gap-1 首位=送礼钮、私信紧邻并排（相邻兄弟同组）、组 column-gap=4px 且
       送礼→私信实缝≈4px、同基线不错位、组/行不溢出视口；「在线人物」行同样断言（私信=组末位、切磋→私信相邻）
    A2 私信连发：同一目标 5 秒内连发 3 条全部 200、发送钮无冷却禁锁（发送中瞬态属设计内，完成即恢复/模态关）、
       全程无「发送太频繁」提示；临时库 mail 快照恰 3 行 kind='player'
    A3 回信链路回归：B 信箱见 A 的 3 封私信 → 点「回信」→ A 收到（标题/正文/发信人标签）
    A4 校验保留：发自己 400（不能给自己发私信，UI .ylpm-info 显示）；超长 400/拦截文案正常显示
       （UI 管线 status=-1「内容太长，最多 500 个字」零网络 + YLPM_SUBMIT/裸 API 打穿服务端 400
       「私信内容去空格后需 2~500 字」双层均验）；未登录（无 Authorization）401
    A5 非回归：系统邮件领取/已读不受影响（GM 行带领取、无发信人/回信列）；反馈顶栏入口可开模态；
       全程无 pageerror（预期 4xx 网络噪声分开判，不计 JS 异常）
    A6 版本：顶栏徽标 v1.2、更新日志弹窗标题「版本信息」+ 首段 [1.2] + 绿条「当前为最新版本」；
       harness /myxxz/CHANGELOG.md 首个版本段 = 1.2

用法：C:/Users/<USER>/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe localtest/t_v102.py
退出码：0=全过；1=有断言失败；2=前置校验失败（fail-closed，未起服）
"""
import hashlib
from http.client import HTTPConnection
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # dev/

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

NODE = r"C:\Users\<USER>\.workbuddy-ai\binaries\node\versions\22.22.2-6\node.exe"
BUNDLE_REL = os.path.join("build", "assets", "index-v102-20261022.js")
SRV_REL = os.path.join("srv", "index_v28.ts")
BUNDLE_MD5 = "66cf2890172dc15c8a8fdff9f8c41940"
SRV_MD5 = "51270cba95846bb75da818d99b012e5c"
API_PORT, WEB_PORT = 3323, 3423                    # 3001/3100~3210 之外；3321/3421(v100)、3322/3422(v101) 不复用
WORK = r"<LOCAL>\Temp\yl_t102_sandbox"
JUNCTION = os.path.join(ROOT, "srv", "node_modules")
JUNCTION_SRC = r"D:\ARM-VPS\yl\server\node_modules"
JSONL = os.path.join(ROOT, "srv", "feedback_inbox.jsonl")
API = "http://127.0.0.1:%d" % API_PORT
WEB = "http://127.0.0.1:%d/myxxz/" % WEB_PORT

USER_A, USER_B, PASS = "ylt_mid", "ylt_max", "Test123456"
GM_MAIL_TITLE = "境界突破结算·A5系统邮件（t102）"
PM_MSGS = ["连发第一条：千里传音，一见如故。",
           "连发第二条：灵石互赠，来日方长。",
           "连发第三条：秘境同行，共赴大道。"]
PM_REPLY = "收到！这是 ylt_max 的回信（t102 回归链）。"
PM_OVERLEN_UI = "超" * 600           # UI 管线超长（>500，程序化赋值绕过 maxLength 属性）
PM_OVERLEN_SRV = "x" * 501           # 服务端超长（去空格 501 字 > 500）
# 临时 GM 口令：只在内存生成、经子进程环境变量传给服务端，绝不落盘（铁律）
GM_PASS = "t102gm_" + hashlib.md5(str(time.time_ns()).encode()).hexdigest()[:12]

PASS_LIST, FAIL_LIST = [], []


def chk(name, cond, detail=""):
    (PASS_LIST if cond else FAIL_LIST).append(name)
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, ("| " + str(detail)[:300]) if detail else ""), flush=True)
    return bool(cond)


def md5_of(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def http(method, url, body=None, token=None, timeout=15):
    """http.client 直连 127.0.0.1，零代理参与（v1.0/v1.1 同款）。"""
    u = urllib.parse.urlsplit(url)
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"} if data else {}
    if token:
        hdrs["Authorization"] = "Bearer " + token
    try:
        conn = HTTPConnection(u.hostname, u.port, timeout=timeout)
        conn.request(method, u.path + ("?" + u.query if u.query else ""), body=data, headers=hdrs)
        r = conn.getresponse()
        out = r.read().decode("utf-8", "replace")
        st = r.status
        conn.close()
        return st, out
    except Exception as e:
        return -1, "TRANSPORT_ERROR: %r" % (e,)


def kill_port(port):
    out = subprocess.run(["netstat", "-ano"], capture_output=True,
                         encoding="utf-8", errors="replace").stdout or ""
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3].upper() == "LISTENING" and parts[1].endswith(":%d" % port):
            pid = parts[-1]
            if pid.isdigit() and pid not in ("0", "4"):
                pids.add(pid)
    for pid in pids:
        print("  [pre] kill stale pid=%s on :%d" % (pid, port), flush=True)
        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True,
                       encoding="utf-8", errors="replace")


def wait_http(url, tries=45, what=""):
    last = (-1, "")
    for i in range(tries):
        last = http("GET", url, timeout=4)
        if last[0] != -1:
            print("  [pre] ready after %ds: %s -> http %s" % (i + 1, what, last[0]), flush=True)
            return True
        time.sleep(1)
    print("  [pre] NOT ready: %s last=%s" % (url, last), flush=True)
    return False


def get_token(user, pw):
    st, body = http("POST", API + "/api/auth/login", body={"username": user, "password": pw})
    try:
        j = json.loads(body)
    except Exception:
        j = {}
    tok = j.get("token") or j.get("access_token") or ""
    print("  [pre] login %s -> %s tok=%s…" % (user, st, tok[:16]), flush=True)
    return tok


def db_snapshot():
    """复制临时库（含 wal/shm）供只读断言，返回副本路径。"""
    copy_db = os.path.join(WORK, "copy.sqlite")
    shutil.copyfile(db_path, copy_db)
    for ext in ("-wal", "-shm"):
        if os.path.exists(db_path + ext):
            shutil.copyfile(db_path + ext, copy_db + ext)
    return copy_db


# ---------------------------------------------------------------- 浏览器侧 JS 片段
JS_CLICK_TXT = r"""(txt) => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const norm = s => (s || '').replace(/\s+/g, '');
  const b = Array.from(document.querySelectorAll('button')).find(x => vis(x) && norm(x.innerText).indexOf(norm(txt)) >= 0);
  if (b) { b.click(); return (b.innerText || '').trim().slice(0, 40); }
  return null;
}"""

JS_CLICK_TXT_EXACT = r"""(txt) => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const norm = s => (s || '').replace(/\s+/g, '');
  const b = Array.from(document.querySelectorAll('button')).find(x => vis(x) && norm(x.innerText) === norm(txt));
  if (b) { b.click(); return (b.innerText || '').trim().slice(0, 40); }
  return null;
}"""

# A1：仙友录好友行结构（v100 原始位型 + 私信同组并入）。
#   DOM 层级（bundle 提取原文）：YlxwRow(div.border-stone-700.rounded.p-2.5) > 内层 flexDiv(
#   flex items-center justify-between gap-2 flex-wrap) > [ span(name·realm),
#   div.flex.items-center.gap-1 > [送礼控件, 私信钮] ]
JS_FRIEND_ROW = r"""(name) => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const norm = s => (s || '').replace(/\s+/g, '');
  // YlxwRow 锚：div.bg-ink-800/60.border.border-stone-700.rounded.p-2.5
  const rows = Array.from(document.querySelectorAll('div.border-stone-700.rounded')).filter(
    x => vis(x) && norm(x.innerText).indexOf(name) >= 0
         && Array.from(x.querySelectorAll('button')).some(b => norm(b.innerText) === '私信'));
  if (!rows.length) return { found: false };
  const rowEl = rows[0];
  const flex = Array.from(rowEl.children).find(c => /justify-between/.test(c.className || ''));
  if (!flex) return { found: true, noFlex: true };
  const cs = getComputedStyle(flex);
  const out = {
    found: true,
    nChildren: flex.children.length,
    firstTag: flex.firstElementChild ? flex.firstElementChild.tagName : null,
    firstText: flex.firstElementChild ? norm(flex.firstElementChild.innerText).slice(0, 24) : null,
    rowFlex: cs.display, rowJustify: cs.justifyContent, rowWrap: cs.flexWrap,
    rowRect: (r => ({ l: Math.round(r.left), r: Math.round(r.right), t: Math.round(r.top), b: Math.round(r.bottom) }))(flex.getBoundingClientRect())
  };
  const grp = flex.lastElementChild;
  out.grpTag = grp ? grp.tagName : null;
  out.grpCls = grp ? (grp.className || '') : null;
  out.grpIsGroup = !!grp && /gap-1/.test(grp.className || '') && /items-center/.test(grp.className || '');
  if (grp) {
    out.grpN = grp.children.length;
    const g = grp.firstElementChild, d = grp.lastElementChild;
    out.giftTag = g ? g.tagName : null;
    out.giftText = g ? norm(g.innerText).slice(0, 12) : null;
    out.giftIsBtn = !!g && g.tagName === 'BUTTON' && norm(g.innerText) === '送礼';
    out.giftIsSpan = !!g && g.tagName === 'SPAN' && norm(g.innerText) === '今日已送礼';
    out.dmTag = d ? d.tagName : null;
    out.dmText = d ? norm(d.innerText).slice(0, 12) : null;
    out.dmIsBtn = !!d && d.tagName === 'BUTTON' && norm(d.innerText) === '私信';
    out.adjacent = !!g && !!d && g.nextElementSibling === d && d.previousElementSibling === g;
    out.grpGap = getComputedStyle(grp).columnGap;
    const rg = g && g.getBoundingClientRect(), dg = d && d.getBoundingClientRect();
    const rowr = flex.getBoundingClientRect();
    if (g && d) {
      out.gapPx = Math.round((dg.left - rg.right) * 10) / 10;
      out.dCenterYDiff = Math.round(Math.abs((dg.top + dg.bottom) / 2 - (rg.top + rg.bottom) / 2) * 10) / 10;
      out.grpRight = Math.round(grp.getBoundingClientRect().right);
      out.overRowRight = grp.getBoundingClientRect().right > rowr.right + 1.5;
      out.overViewport = [g, d, grp].some(x => x.getBoundingClientRect().right > window.innerWidth + 1);
      out.giftVisible = vis(g); out.dmVisible = vis(d);
    }
  }
  return out;
}"""

# A1：在线人物行结构（r144 onlineRow）：行 > [左名组, div.flex.items-center.gap-1 > [..., 切磋, 私信]]
JS_ONLINE_ROW = r"""(name) => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const norm = s => (s || '').replace(/\s+/g, '');
  const rows = Array.from(document.querySelectorAll('div')).filter(
    x => vis(x) && /justify-between/.test(x.className || '') && /bg-stone-800\/60/.test(x.className || '')
         && norm(x.innerText).indexOf(name) >= 0
         && Array.from(x.querySelectorAll('button')).some(b => norm(b.innerText) === '私信'));
  if (!rows.length) return { found: false };
  const row = rows[0];
  const out = { found: true, nChildren: row.children.length };
  const grp = row.lastElementChild;
  out.grpCls = grp ? (grp.className || '') : null;
  out.grpIsGroup = !!grp && /gap-1/.test(grp.className || '') && /items-center/.test(grp.className || '');
  if (grp) {
    const kids = Array.from(grp.children);
    out.grpN = kids.length;
    out.btnTexts = kids.map(k => norm(k.innerText).slice(0, 6));
    const dm = grp.lastElementChild, prev = dm ? dm.previousElementSibling : null;
    out.dmIsBtn = !!dm && dm.tagName === 'BUTTON' && norm(dm.innerText) === '私信';
    out.prevText = prev ? norm(prev.innerText).slice(0, 6) : null;
    out.prevIsQie = !!prev && norm(prev.innerText) === '切磋';
    out.adjacent = !!prev && prev.nextElementSibling === dm;
    out.grpGap = getComputedStyle(grp).columnGap;
    const rowr = row.getBoundingClientRect();
    out.gaps = [];
    for (let i = 1; i < kids.length; i++) {
      const a = kids[i - 1].getBoundingClientRect(), b2 = kids[i].getBoundingClientRect();
      out.gaps.push(Math.round((b2.left - a.right) * 10) / 10);
    }
    const cys = kids.map(k => { const r2 = k.getBoundingClientRect(); return (r2.top + r2.bottom) / 2; });
    out.dCenterYSpread = kids.length ? Math.round((Math.max(...cys) - Math.min(...cys)) * 10) / 10 : null;
    out.overRowRight = grp.getBoundingClientRect().right > rowr.right + 1.5;
    out.overViewport = kids.some(k => k.getBoundingClientRect().right > window.innerWidth + 1);
    out.allVisible = kids.every(vis);
  }
  return out;
}"""


def main():
    t0 = time.time()
    print("== t_v102 全栈临时环境实测（v1.2：私信按钮布局修复 + 私信取消限频） ==", flush=True)

    # ---------- PH-0 前置 fail-closed ----------
    b_path, s_path = os.path.join(ROOT, BUNDLE_REL), os.path.join(ROOT, SRV_REL)
    bm, sm = md5_of(b_path), md5_of(s_path)
    print("  [pre] bundle md5=%s  srv md5=%s" % (bm, sm), flush=True)
    if bm != BUNDLE_MD5:
        print("  [pre][FATAL] bundle 指纹不符（期望 %s）" % BUNDLE_MD5, flush=True)
        return 2
    if sm != SRV_MD5:
        print("  [pre][FATAL] 服务端指纹不符（期望 %s）" % SRV_MD5, flush=True)
        return 2
    if os.path.exists(JSONL):
        print("  [pre][FATAL] %s 已存在（上次运行泄漏），拒绝覆盖" % JSONL, flush=True)
        return 2

    kill_port(API_PORT)
    kill_port(WEB_PORT)

    j_created = False
    if not os.path.isdir(JUNCTION):
        subprocess.run(["cmd", "/c", "mklink", "/J", JUNCTION, JUNCTION_SRC], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
        if not os.path.isdir(JUNCTION):
            print("  [pre][FATAL] junction 创建失败（依赖源 %s）" % JUNCTION_SRC, flush=True)
            return 2
        j_created = True
        print("  [pre] junction dev/srv/node_modules -> ARM-VPS 已建", flush=True)
    else:
        print("  [pre] junction 已存在（沿用）", flush=True)

    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    global db_path
    db_path = os.path.join(WORK, "database.sqlite")
    profile = os.path.join(WORK, "profile")
    srv_log = open(os.path.join(WORK, "server.log"), "wb")
    har_log = open(os.path.join(WORK, "harness.log"), "wb")

    env = dict(os.environ)
    env.update({
        "PORT": str(API_PORT),
        "DATABASE_PATH": db_path,
        "GM_PASSWORD": GM_PASS,
        "JWT_SECRET": "t102tmp_" + hashlib.md5(GM_PASS.encode()).hexdigest()[:16],
    })
    srv = subprocess.Popen([NODE, "--experimental-strip-types", s_path], cwd=WORK,
                           env=env, stdout=srv_log, stderr=srv_log,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    har = subprocess.Popen([NODE, os.path.join(HERE, "harness.js"),
                            "--port=%d" % WEB_PORT, "--api-port=%d" % API_PORT,
                            "--root=%s" % ROOT, "--bundle=index-v102-20261022.js"],
                           cwd=ROOT, stdout=har_log, stderr=har_log,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    print("  [pre] server pid=%s harness pid=%s api=%d web=%d" % (srv.pid, har.pid, API_PORT, WEB_PORT), flush=True)

    net_mail = []       # (method, status, url) — 浏览器侧 /api/mail/send 全量
    net_all = []        # (method, status, url) — 全部 /api/ 请求（证据链）
    page_errors = []    # 真实 JS 异常（pageerror；4xx 网络噪声不属此类）

    try:
        if not wait_http(API + "/api/market/items?page=1&limit=1", what="api"):
            print(open(os.path.join(WORK, "server.log"), encoding="utf-8", errors="replace").read()[-3000:], flush=True)
            return 2
        if not wait_http(WEB, what="web"):
            print(open(os.path.join(WORK, "harness.log"), encoding="utf-8", errors="replace").read()[-2000:], flush=True)
            return 2

        # ---------- PH-0b 注册双账号 + GM 系统邮件（A5 用）+ A4 未登录 401（裸 API） ----------
        for u in (USER_A, USER_B):
            st, body = http("POST", API + "/api/auth/register", body={"username": u, "password": PASS})
            print("  [pre] register %s -> %s %s" % (u, st, body[:100]), flush=True)
            if st not in (200, 201):
                print("  [pre][FATAL] 注册失败 %s" % u, flush=True)
                return 2
        tok_a = get_token(USER_A, PASS)
        tok_b = get_token(USER_B, PASS)
        if not tok_a or not tok_b:
            print("  [pre][FATAL] 取登录 token 失败", flush=True)
            return 2
        st, body = http("POST", API + "/api/gm/login", body={"password": GM_PASS})
        try:
            gm_tok = (json.loads(body) or {}).get("token") or ""
        except Exception:
            gm_tok = ""
        print("  [pre] gm/login -> %s tok=%s…" % (st, gm_tok[:16]), flush=True)
        if st != 200 or not gm_tok:
            print("  [pre][FATAL] GM 登录失败", flush=True)
            return 2
        st, body = http("POST", API + "/api/mail/send", token=gm_tok,
                        body={"username": USER_B, "title": GM_MAIL_TITLE,
                              "content": "这是 GM 系统邮件（sender=system），附灵石用于 A5 领取回归。", "lingshi": 7})
        print("  [pre] GM mail -> %s %s" % (st, body[:120]), flush=True)
        if st != 200:
            print("  [pre][FATAL] GM 发信失败", flush=True)
            return 2

        # A4·未登录：无 Authorization 头 POST /api/mail/send（pm101Dispatch 无 Bearer → next() → GM 路由 401）
        st401, body401 = http("POST", API + "/api/mail/send", body={"to": USER_B, "content": "未登录私信（应 401）"})
        print("  [pre] no-auth mail/send -> %s %s" % (st401, body401[:100]), flush=True)
        chk("A4 未登录（无 Authorization）POST /api/mail/send → 401", st401 == 401,
            "%s %s" % (st401, body401[:80]))

        # ---------- 浏览器 ----------
        from playwright.sync_api import sync_playwright

        bundle_text = open(b_path, encoding="utf-8").read()
        HOOK = ("\n;try{window.__Be=Be;"
                "window.__YLogs=function(){return Be.getState().logs};"
                "window.__hook='ok';}catch(e){window.__hook='err:'+((e&&e.message)||e);}"
                "setInterval(function(){try{window.__Be=Be;"
                "window.__YLogs=function(){return Be.getState().logs};}catch(e){}},500);\n")

        def on_response(r):
            u = r.request.url
            if "/api/" in u:
                net_all.append((r.request.method, r.status, u))
            if "/api/mail/send" in u:
                net_mail.append((r.request.method, r.status, u))

        def wire(page):
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.on("response", on_response)
            page.route(re.compile(r".*/assets/.*\.js.*"),
                       lambda route: route.fulfill(
                           status=200, content_type="application/javascript; charset=utf-8",
                           headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
                           body=bundle_text + HOOK))

        def body_text(page):
            return page.evaluate("() => document.body ? document.body.innerText : ''")

        def net_mail_of(status=None):
            return [x for x in net_mail if x[0] == "POST" and (status is None or x[1] == status)]

        def in_game(page, user, pw_, dao):
            """分层进入：登录页/法门/道号/天赋/开始（v1.0/v1.1 同款，道号按账号参数化）。"""
            for step in range(30):
                stt = page.evaluate("""() => ({
                  pwd: !!document.querySelector('input[type="password"]'),
                  header: !!document.querySelector('header'),
                  famen: (document.body.innerText||'').indexOf('修仙法门') >= 0,
                  dao: !!document.querySelector('input[placeholder*="道号"]'),
                  fate: (document.body.innerText||'').indexOf('命运点') >= 0,
                  start: (document.body.innerText||'').indexOf('开始游戏') >= 0,
                  auto: Array.from(document.querySelectorAll('button[title]')).some(
                    b => (b.getAttribute('title')||'').indexOf('自动打坐') >= 0)
                })""")
                if stt["header"] and stt["auto"]:
                    return True
                if stt["pwd"]:
                    has_login = page.evaluate("""() => !!Array.from(document.querySelectorAll('button'))
                      .find(b => b.offsetParent !== null && (b.innerText||'').indexOf('踏入修仙界') >= 0)""")
                    if not has_login:
                        page.evaluate(JS_CLICK_TXT, "已有道号")
                        page.wait_for_timeout(900)
                    page.locator("input").first.fill(user, timeout=5000)
                    page.locator('input[type="password"]').first.fill(pw_, timeout=5000)
                    page.evaluate(JS_CLICK_TXT, "踏入修仙界")
                    page.wait_for_timeout(6000)
                    continue
                if stt["famen"]:
                    page.evaluate(JS_CLICK_TXT, "开始游戏") or page.evaluate(JS_CLICK_TXT, "下一步") or page.evaluate(JS_CLICK_TXT, "关闭")
                    page.wait_for_timeout(1500)
                    continue
                if stt["dao"]:
                    try:
                        page.locator('input[placeholder*="道号"]').first.fill(dao, timeout=4000)
                    except Exception:
                        pass
                    page.wait_for_timeout(300)
                    page.evaluate(JS_CLICK_TXT, "下一步")
                    page.wait_for_timeout(1500)
                    continue
                if stt["fate"]:
                    page.evaluate(JS_CLICK_TXT, "随机分配")
                    page.wait_for_timeout(600)
                    page.evaluate(JS_CLICK_TXT, "下一步")
                    page.wait_for_timeout(1500)
                    continue
                if stt["start"]:
                    page.evaluate(JS_CLICK_TXT, "开始游戏")
                    page.wait_for_timeout(4000)
                    continue
                page.evaluate(JS_CLICK_TXT, "下一步") or page.evaluate(JS_CLICK_TXT, "开始修仙") or page.evaluate(JS_CLICK_TXT, "关闭")
                page.wait_for_timeout(1500)
            return False

        def clear_auth(page):
            """账号切换前清 localStorage（同 origin 共享 token，否则新页自动续接上一账号）。"""
            page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} }")

        def who_am_i(page):
            return page.evaluate(
                "() => { try { const p = window.__Be.getState().player;"
                " return p ? (p.name || null) : null; } catch (e) { return 'nostore'; } }")

        def dismiss_overlay(page):
            for _ in range(3):
                t = body_text(page)
                if "当前为最新版本" not in t and "更新日志" not in t:
                    return
                r = (page.evaluate(JS_CLICK_TXT, "关闭") or page.evaluate(JS_CLICK_TXT, "确定")
                     or page.evaluate(JS_CLICK_TXT, "我知道了"))
                if not r:
                    page.keyboard.press("Escape")
                page.wait_for_timeout(800)

        def close_pm_modal(page):
            for _ in range(3):
                page.evaluate("() => { const b = document.querySelector('.ylpm-ghost'); if (b) b.click(); }")
                page.wait_for_timeout(500)
                if not page.evaluate("() => !!document.querySelector('.ylpm-mask')"):
                    return True
            page.evaluate("() => { const m = document.querySelector('.ylpm-mask'); if (m) m.remove(); }")
            return False

        def close_fb_modal(page):
            for _ in range(3):
                page.evaluate("() => { const b = document.querySelector('.ylfb-ghost'); if (b) b.click(); }")
                page.wait_for_timeout(500)
                if not page.evaluate("() => !!document.querySelector('.ylfb-mask')"):
                    return True
            page.evaluate("() => { const m = document.querySelector('.ylfb-mask'); if (m) m.remove(); }")
            return False

        def close_any_modal(page):
            for _ in range(4):
                before = body_text(page)
                r = (page.evaluate(JS_CLICK_TXT_EXACT, "关闭") or page.evaluate(JS_CLICK_TXT, "×")
                     or page.evaluate(JS_CLICK_TXT, "✕"))
                if not r:
                    page.keyboard.press("Escape")
                    page.evaluate("""() => {
                      const d = document.querySelector('[role="dialog"]');
                      if (d) d.click();
                    }""")
                page.wait_for_timeout(700)
                if body_text(page) == before:
                    return False
            return True

        def pm_open_and_send(page, to, content):
            """开私信模态（YLPM_OPEN）→ 填内容 → 点发送。返回 {opened, prefilled}。"""
            page.evaluate("(to) => { window.YLPM_OPEN(to); }", to)
            page.wait_for_timeout(400)
            st = page.evaluate("""(to) => ({
              mask: !!document.querySelector('.ylpm-mask'),
              prefilled: (document.querySelector('.ylpm-in')||{}).value || null })""", to)
            page.evaluate("(v) => { const ta = document.querySelector('.ylpm-ta'); if (ta) ta.value = v; }", content)
            page.evaluate("() => { const b = document.querySelector('.ylpm-btn'); if (b) b.click(); }")
            return st

        def pm_info(page):
            return page.evaluate("() => (document.querySelector('.ylpm-info') || {}).textContent || ''")

        def wait_info(page, frag, tries=24):
            for _ in range(tries):
                if frag in pm_info(page):
                    return True
                page.wait_for_timeout(250)
            return False

        def add_friend_and_open_panel(page, name):
            """打开仙友录 → 加好友 → 等好友行出现。面板保持打开。"""
            fr_open = page.evaluate(JS_CLICK_TXT_EXACT, "仙友录")
            page.wait_for_timeout(1200)
            add_r = page.evaluate("""(name) => {
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              const inp = Array.from(document.querySelectorAll('input')).find(
                x => vis(x) && (x.placeholder||'').indexOf('对方名号') >= 0);
              if (!inp) return 'no-input';
              const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
              setter.call(inp, name);
              inp.dispatchEvent(new Event('input', { bubbles: true }));
              const b = Array.from(document.querySelectorAll('button')).find(
                x => vis(x) && (x.innerText||'').replace(/\\s+/g,'') === '加好友');
              if (!b) return 'no-btn';
              b.click();
              return 'ok';
            }""", name)
            page.wait_for_timeout(1500)
            return fr_open, add_r

        def friend_row_asserts(page, tag, name):
            """按 JS_FRIEND_ROW 测当前视口下的好友行并落断言。"""
            j = page.evaluate(JS_FRIEND_ROW, name)
            print("  %s friendRow: %s" % (tag, json.dumps(j, ensure_ascii=False)[:600]), flush=True)
            chk("A1%s 好友行在位（含 ylt_max + 私信钮）" % tag, j.get("found") is True)
            if not j.get("found"):
                return
            chk("A1%s 行=v100 原始位型：justify-between 恢复 2 子（姓名 span + 右组），首位=姓名 span"
                % tag,
                j.get("nChildren") == 2 and j.get("firstTag") == "SPAN" and name in (j.get("firstText") or "")
                and j.get("rowFlex") == "flex" and j.get("rowJustify") == "space-between",
                "n=%s first=%s(%s) justify=%s" % (j.get("nChildren"), j.get("firstTag"),
                                                  j.get("firstText"), j.get("rowJustify")))
            chk("A1%s 「送礼」回到行末组首位（对照 v100：送礼为行右端控件；1.1 曾被挤成行中第 2 子）" % tag,
                j.get("grpIsGroup") is True and (j.get("giftIsBtn") is True or j.get("giftIsSpan") is True),
                "grp=%s gift=%s(%s)" % (j.get("grpCls"), j.get("giftTag"), j.get("giftText")))
            chk("A1%s 「私信」紧邻「送礼」并排（同组相邻兄弟，组恰 2 子）" % tag,
                j.get("dmIsBtn") is True and j.get("adjacent") is True and j.get("grpN") == 2,
                "dm=%s(%s) adj=%s n=%s" % (j.get("dmTag"), j.get("dmText"), j.get("adjacent"), j.get("grpN")))
            chk("A1%s 同组间距一致（column-gap=4px 且送礼→私信实缝≈4px）" % tag,
                j.get("grpGap") == "4px" and isinstance(j.get("gapPx"), (int, float)) and abs(j["gapPx"] - 4.0) <= 1.5,
                "gap=%s gapPx=%s" % (j.get("grpGap"), j.get("gapPx")))
            chk("A1%s 行不错位（送礼/私信同基线 centerY 差≤2px）" % tag,
                isinstance(j.get("dCenterYDiff"), (int, float)) and j["dCenterYDiff"] <= 2.0,
                "dCenterY=%s" % j.get("dCenterYDiff"))
            chk("A1%s 行不溢出（组不出行盒、控件不出视口、均可见）" % tag,
                j.get("overRowRight") is False and j.get("overViewport") is False
                and j.get("giftVisible") is True and j.get("dmVisible") is True,
                "overRow=%s overVp=%s vis=%s/%s" % (j.get("overRowRight"), j.get("overViewport"),
                                                    j.get("giftVisible"), j.get("dmVisible")))

        def online_row_asserts(page, tag, name):
            j = page.evaluate(JS_ONLINE_ROW, name)
            print("  %s onlineRow: %s" % (tag, json.dumps(j, ensure_ascii=False)[:600]), flush=True)
            chk("A1%s 在线人物行在位（含 ylt_max + 私信钮）" % tag, j.get("found") is True)
            if not j.get("found"):
                return
            chk("A1%s 在线行右组为行末子元素、组类 flex items-center gap-1" % tag,
                j.get("grpIsGroup") is True and j.get("nChildren") == 2,
                "grp=%s n=%s" % (j.get("grpCls"), j.get("nChildren")))
            chk("A1%s 「私信」=组末位且「切磋」紧邻其前（相邻兄弟）" % tag,
                j.get("dmIsBtn") is True and j.get("prevIsQie") is True and j.get("adjacent") is True,
                "btns=%s prev=%s adj=%s" % (j.get("btnTexts"), j.get("prevText"), j.get("adjacent")))
            chk("A1%s 在线行组间距一致（column-gap=4px，相邻钮缝均≈4px）" % tag,
                j.get("grpGap") == "4px" and isinstance(j.get("gaps"), list) and j["gaps"]
                and all(isinstance(g, (int, float)) and abs(g - 4.0) <= 1.5 for g in j["gaps"]),
                "gap=%s gaps=%s" % (j.get("grpGap"), j.get("gaps")))
            chk("A1%s 在线行不错位不溢出（centerY 极差≤2px、组不出行盒、不出视口、均可见）" % tag,
                isinstance(j.get("dCenterYSpread"), (int, float)) and j["dCenterYSpread"] <= 2.0
                and j.get("overRowRight") is False and j.get("overViewport") is False
                and j.get("allVisible") is True,
                "spread=%s overRow=%s overVp=%s" % (j.get("dCenterYSpread"), j.get("overRowRight"),
                                                    j.get("overViewport")))

        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                profile, headless=True, viewport={"width": 1440, "height": 900},
                args=["--no-proxy-server"])

            # ============ PH-2 A 账号页（ylt_mid）@1440 ============
            pg = ctx.new_page()
            wire(pg)
            pg.goto(WEB, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(6000)
            if not in_game(pg, USER_A, PASS, USER_A):
                print(body_text(pg)[:1500], flush=True)
                print("  [FATAL] A 账号未能进入游戏", flush=True)
                ctx.close()
                return 1
            print("  [nav] A（%s）已进入游戏（%.0fs）身份=%s" % (USER_A, time.time() - t0, who_am_i(pg)), flush=True)
            chk("ID A 页当前游戏身份=ylt_mid（store.player.name 判）", who_am_i(pg) == USER_A, who_am_i(pg))
            pg.wait_for_timeout(2500)
            dismiss_overlay(pg)
            pg.wait_for_timeout(500)

            # ---------- A6 版本链（先做：徽标 + 更新日志弹窗） ----------
            print("\n== A6 版本：徽标 v1.2 + 更新日志 [1.2] + 绿条 ==", flush=True)
            badge = pg.evaluate("""() => {
              const b = Array.from(document.querySelectorAll('header button[title]'))
                .find(x => (x.getAttribute('title')||'').indexOf('更新日志') >= 0
                           && x.getBoundingClientRect().width > 0);
              return b ? { text: (b.innerText||'').trim(), title: b.getAttribute('title') } : null;
            }""")
            print("  badge:", badge, flush=True)
            chk("A6 顶栏徽标显示 v1.2", bool(badge) and badge.get("text") == "v1.2", json.dumps(badge, ensure_ascii=False))
            chg_open = pg.evaluate("""() => (document.body.innerText||'').indexOf('当前为最新版本') >= 0""")
            if not chg_open:
                pg.evaluate("""() => {
                  const b = Array.from(document.querySelectorAll('header button[title]'))
                    .find(x => (x.getAttribute('title')||'').indexOf('更新日志') >= 0);
                  if (b) b.click();
                }""")
                pg.wait_for_timeout(1800)
            chg = pg.evaluate(r"""() => {
              const t = document.body.innerText || '';
              const hasTitle = t.indexOf('版本信息') >= 0;   /* 模态真实标题是「版本信息」（CM 组件） */
              const greenEl = Array.from(document.querySelectorAll('[class*="text-green-400"]'))
                .find(x => (x.innerText || '').indexOf('当前为最新版本') >= 0);
              /* 窗内首个版本徽标：CM 把 `## [1.2]` 渲染成裸版本徽标（无方括号），取模态根下
                 第一个形如 v?N.N 的叶子元素（顶栏徽标带 v 且在 header，不在模态根内） */
              let root = greenEl;
              for (let i = 0; root && i < 12; i++) {
                const p = root.parentElement;
                if (!p) break;
                root = p;
                if (/(^|\s)fixed(\s|$)/.test(root.className || '')) break;
              }
              const vers = root && root !== greenEl ? Array.from(root.querySelectorAll('*'))
                .filter(x => x.children.length === 0
                             && /^v?[0-9]+(\.[0-9]+)+$/.test((x.textContent || '').trim()))
                .map(x => (x.textContent || '').trim()) : [];
              let box = greenEl, boxText = '';
              for (let i = 0; box && i < 8; i++) {
                box = box.parentElement;
                if (box && (box.innerText || '').indexOf('已是最新版本') >= 0) { boxText = box.innerText; break; }
              }
              return { hasTitle, firstVer: vers[0] || null, verList: vers.slice(0, 5),
                       green: greenEl ? (greenEl.innerText || '').trim() : null,
                       boxText: boxText.slice(0, 200) };
            }""")
            print("  changelog:", json.dumps(chg, ensure_ascii=False)[:400], flush=True)
            _fv = (chg.get("firstVer") or "").lstrip("v")
            chk("A6 更新日志弹窗打开（标题「版本信息」在窗）且窗内首个版本徽标=1.2（最新段 [1.2]；徽标渲染带 v 前缀）",
                chg.get("hasTitle") is True and _fv == "1.2",
                json.dumps(chg, ensure_ascii=False)[:160])
            chk("A6 绿条「当前为最新版本」且容器含「已是最新版本 v1.2」"
                "（绿条仅当 CHANGELOG 首个版本段解析结果 === 当前版本 1.2 时渲染）",
                chg.get("green") == "当前为最新版本" and "已是最新版本 v1.2" in (chg.get("boxText") or ""),
                "green=%s box=%r" % (chg.get("green"), (chg.get("boxText") or "")[:120]))
            close_any_modal(pg)
            pg.wait_for_timeout(400)
            # A6 补证：harness 直出的 CHANGELOG.md 首个版本段
            st_md, md_txt = http("GET", WEB + "CHANGELOG.md")
            md_ver = ""
            m = re.search(r"^##\s*\[([0-9]+(?:\.[0-9]+)*)\]", md_txt or "", re.M)
            if m:
                md_ver = m.group(1)
            chk("A6 harness GET /myxxz/CHANGELOG.md 200 且首个版本段 = 1.2",
                st_md == 200 and md_ver == "1.2", "http=%s ver=%s" % (st_md, md_ver))

            # ---------- A1·仙友录好友行 @1440 → 390 ----------
            print("\n== A1 仙友录：加好友 + 好友行结构 @1440 ==", flush=True)
            fr_open, add_r = add_friend_and_open_panel(pg, USER_B)
            print("  friends modal open=%r add=%r" % (fr_open, add_r), flush=True)
            chk("A1 打开仙友录并提交加好友（ylt_max，服务端自动互为好友）",
                fr_open is not None and add_r == "ok", "open=%r add=%r" % (fr_open, add_r))
            row_ok = False
            for _ in range(10):
                row_ok = pg.evaluate("""(name) => {
                  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
                  const norm = s => (s||'').replace(/\\s+/g,'');
                  return Array.from(document.querySelectorAll('div.border-stone-700.rounded')).filter(
                    x => vis(x) && norm(x.innerText).indexOf(name) >= 0
                         && Array.from(x.querySelectorAll('button')).some(b => norm(b.innerText) === '私信')).length > 0;
                }""", USER_B)
                if row_ok:
                    break
                pg.wait_for_timeout(600)
            chk("A1 好友列表出现 ylt_max 行且带「私信」按钮", row_ok)
            friend_row_asserts(pg, "@1440", USER_B)

            print("\n== A1 仙友录好友行结构 @390（同一打开的面板，改视口重排） ==", flush=True)
            pg.set_viewport_size({"width": 390, "height": 844})
            pg.wait_for_timeout(1500)
            friend_row_asserts(pg, "@390", USER_B)
            pg.set_viewport_size({"width": 1440, "height": 900})
            pg.wait_for_timeout(1200)
            close_any_modal(pg)          # 关仙友录面板
            pg.wait_for_timeout(500)

            # ---------- A1·在线人物行 @1440 → 390 ----------
            print("\n== A1 在线人物面板行结构 @1440 ==", flush=True)
            hb = http("POST", API + "/api/session/claim", token=tok_b, body={"device": "t102-probe"})
            print("  B session/claim -> %s %s" % (hb[0], hb[1][:80]), flush=True)
            onl_open = pg.evaluate("""() => {
              const b = Array.from(document.querySelectorAll('button[title]')).find(
                x => (x.getAttribute('title')||'') === '当前在线人数' && x.getBoundingClientRect().width > 0);
              if (b) { b.click(); return true; } return false;
            }""")
            onl_seen = False
            for _ in range(12):
                pg.wait_for_timeout(500)
                t = body_text(pg)
                if "在线道友" in t and USER_B in t:
                    onl_seen = True
                    break
            print("  panel open=%s ylt_max seen=%s" % (onl_open, onl_seen), flush=True)
            chk("A1 在线人物面板打开且列出 ylt_max（5 分钟活跃窗）", onl_open is True and onl_seen,
                "open=%s seen=%s" % (onl_open, onl_seen))
            online_row_asserts(pg, "@1440", USER_B)
            print("\n== A1 在线人物行结构 @390 ==", flush=True)
            pg.set_viewport_size({"width": 390, "height": 844})
            pg.wait_for_timeout(1500)
            online_row_asserts(pg, "@390", USER_B)
            pg.set_viewport_size({"width": 1440, "height": 900})
            pg.wait_for_timeout(1200)
            pg.evaluate(JS_CLICK_TXT_EXACT, "关闭")       # 关在线人物面板
            pg.wait_for_timeout(500)

            # ---------- A2 同一目标 5 秒内连发 3 条 ----------
            print("\n== A2 私信连发 3 条（同目标 ylt_max，页面内计时） ==", flush=True)
            n200_before = len(net_mail_of(200))
            send3 = pg.evaluate("""async (to) => {
              const out = { rounds: [], cooldownSeen: false, totalMs: 0 };
              const t0 = performance.now();
              for (let i = 0; i < 3; i++) {
                window.YLPM_OPEN(to);
                let guard = 0;
                while (!document.querySelector('.ylpm-mask') && guard++ < 60) {
                  await new Promise(r => setTimeout(r, 20));
                }
                const ta = document.querySelector('.ylpm-ta');
                ta.value = '连发第' + (i + 1) + '条：千里传音一见如故（t102）';
                const btn = document.querySelector('.ylpm-btn');
                const rb = { disabled: !!btn.disabled, text: (btn.textContent || '').trim() };
                btn.click();
                const rbPost = btn.isConnected ? { disabled: !!btn.disabled, text: (btn.textContent || '').trim() } : null;
                let ended = null, t1 = performance.now();
                while (performance.now() - t1 < 4000) {
                  await new Promise(r => setTimeout(r, 25));
                  const info = (document.querySelector('.ylpm-info') || {}).textContent || '';
                  if (info.indexOf('太频繁') >= 0) out.cooldownSeen = true;
                  if (!document.querySelector('.ylpm-mask')) { ended = 'closed'; break; }
                }
                const dur = Math.round(performance.now() - t1);
                const stillMask = !!document.querySelector('.ylpm-mask');
                const b3 = document.querySelector('.ylpm-btn');
                const stuckDisabled = !!(stillMask && b3 && b3.disabled);
                let infoAfter = (document.querySelector('.ylpm-info') || {}).textContent || '';
                out.rounds.push({ rb, rbPost, ended, dur, stuckDisabled, infoAfter,
                                  cooldownInInfo: infoAfter.indexOf('太频繁') >= 0 });
                if (stillMask) {
                  const g = document.querySelector('.ylpm-ghost');
                  if (g) g.click();
                  await new Promise(r => setTimeout(r, 150));
                }
              }
              out.totalMs = Math.round(performance.now() - t0);
              return out;
            }""", USER_B)
            posts200 = net_mail_of(200)
            print("  send3: %s" % json.dumps(send3, ensure_ascii=False)[:800], flush=True)
            print("  posts200=%d（此前 %d）" % (len(posts200) - n200_before, n200_before), flush=True)
            all_closed = all(r.get("ended") == "closed" for r in (send3.get("rounds") or []))
            chk("A2 同一目标 5 秒内连发 3 条（页面内计时 totalMs<5000 且三轮全走完）",
                isinstance(send3.get("totalMs"), int) and send3["totalMs"] < 5000
                and len(send3.get("rounds") or []) == 3 and all_closed,
                "totalMs=%s rounds=%s" % (send3.get("totalMs"),
                                          [r.get("ended") for r in (send3.get("rounds") or [])]))
            chk("A2 三条全部 200（POST /api/mail/send 200 恰 +3）",
                len(posts200) - n200_before == 3 and all(x[1] == 200 for x in posts200[n200_before:]),
                json.dumps(posts200[n200_before:]))
            chk("A2 发送钮无冷却禁锁（每轮点击后仅「发送中…」瞬态禁用属设计内；轮末无卡死禁用、模态正常关闭可复用）",
                all(r.get("stuckDisabled") is False for r in (send3.get("rounds") or []))
                and all(r.get("rbPost") is None or (isinstance(r.get("rbPost"), dict) and
                        (r["rbPost"].get("disabled") is True or r["rbPost"].get("text") == "发送"))
                        for r in (send3.get("rounds") or [])) and all_closed,
                "stuck=%s" % [r.get("stuckDisabled") for r in (send3.get("rounds") or [])])
            chk("A2 无冷却提示（三轮 info/页面均无「发送太频繁」）",
                send3.get("cooldownSeen") is False
                and all(r.get("cooldownInInfo") is False for r in (send3.get("rounds") or []))
                and "发送太频繁" not in body_text(pg),
                "cooldownSeen=%s" % send3.get("cooldownSeen"))

            # A2 DB 快照：此刻 player 行应恰 3
            copy_db = db_snapshot()
            con = sqlite3.connect(copy_db)
            con.row_factory = sqlite3.Row
            snap_rows = [dict(r) for r in con.execute(
                "SELECT id, user_id, sender, title, kind, read_at FROM mail WHERE kind='player' ORDER BY id").fetchall()]
            con.close()
            print("  snapshot player rows=%d senders=%s" % (len(snap_rows), [r["sender"] for r in snap_rows]), flush=True)
            chk("A2 临时库 mail 快照恰 3 行 kind='player'（均 A→B）",
                len(snap_rows) == 3 and all(r["sender"] == USER_A for r in snap_rows),
                "n=%d senders=%s" % (len(snap_rows), [r["sender"] for r in snap_rows]))

            # ---------- A4·a 发给自己 400（UI） ----------
            print("\n== A4·a 发给自己 → 服务端 400 文案显示 ==", flush=True)
            n_any_before = len(net_mail_of())
            st = pm_open_and_send(pg, USER_A, "给自己发一条测试私信（应被 400 拒绝）")
            ok400 = wait_info(pg, "不能给自己发私信")
            info400 = pm_info(pg)
            posts400 = net_mail_of(400)
            print("  modal=%s info=%r posts400=%s" % (json.dumps(st, ensure_ascii=False), info400,
                                                      json.dumps(posts400)), flush=True)
            chk("A4·a 私信模态在位且收件人预填自己", st.get("mask") is True and st.get("prefilled") == USER_A,
                json.dumps(st, ensure_ascii=False))
            chk("A4·a 服务端 400「不能给自己发私信」在 .ylpm-info 显示 + 网络可见恰 1 次 POST 400",
                ok400 and len(posts400) == 1 and posts400[0][1] == 400,
                "ok=%s posts400=%s info=%r" % (ok400, json.dumps(posts400), info400))
            close_pm_modal(pg)

            # ---------- A4·b 超长：UI 管线拦截（status=-1 零网络）+ 文案显示 ----------
            print("\n== A4·b 超长 600 字（UI 管线）→ 客户端拦截文案显示 ==", flush=True)
            n_before_b = len(net_mail_of())
            st = pm_open_and_send(pg, USER_B, PM_OVERLEN_UI)
            ok_over = wait_info(pg, "内容太长，最多 500 个字")
            info_over = pm_info(pg)
            n_after_b = len(net_mail_of())
            print("  info=%r net %d -> %d" % (info_over, n_before_b, n_after_b), flush=True)
            chk("A4·b UI 管线超长拦截：文案「内容太长，最多 500 个字」在 .ylpm-info 显示且零新网络请求",
                ok_over and n_after_b == n_before_b, "ok=%s info=%r net=%d" % (ok_over, info_over, n_after_b))
            close_pm_modal(pg)

            # ---------- A4·c 超长打穿服务端 400（YLPM_SUBMIT 管线 + 裸 API 双证） ----------
            print("\n== A4·c 超长打穿服务端 400 ==", flush=True)
            sub = pg.evaluate("""async (payload) => {
              return await window.YLPM_SUBMIT(payload);
            }""", {"to": USER_B, "content": PM_OVERLEN_SRV})
            print("  YLPM_SUBMIT(501字) -> %s" % json.dumps(sub, ensure_ascii=False), flush=True)
            chk("A4·c1 YLPM_SUBMIT 管线：服务端 400 + 文案「私信内容去空格后需 2~500 字」",
                isinstance(sub, dict) and sub.get("ok") is False and sub.get("status") == 400
                and "私信内容去空格后需 2~500 字" in (sub.get("error") or ""),
                json.dumps(sub, ensure_ascii=False))
            st_srv, body_srv = http("POST", API + "/api/mail/send", token=tok_a,
                                    body={"to": USER_B, "content": "y" * 501})
            try:
                err_srv = (json.loads(body_srv) or {}).get("error") or ""
            except Exception:
                err_srv = ""
            print("  raw overlen -> %s %s" % (st_srv, body_srv[:120]), flush=True)
            chk("A4·c2 裸 API 超长：服务端 400 + 同文案（校验保留）",
                st_srv == 400 and err_srv == "私信内容去空格后需 2~500 字", "%s %s" % (st_srv, err_srv))

            # ---------- A5·反馈顶栏入口 ----------
            print("\n== A5 反馈顶栏入口 ==", flush=True)
            fb_open = pg.evaluate("""() => {
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              const norm = s => (s || '').replace(/\\s+/g, '');
              const b = Array.from(document.querySelectorAll('header button')).find(
                x => vis(x) && norm(x.innerText) === '反馈');
              if (b) { b.click(); return true; } return false;
            }""")
            pg.wait_for_timeout(800)
            fb_state = pg.evaluate("""() => ({
              mask: !!document.querySelector('.ylfb-mask'),
              title: (document.querySelector('.ylfb-title') || {}).textContent || null })""")
            print("  fb: open=%s %s" % (fb_open, json.dumps(fb_state, ensure_ascii=False)), flush=True)
            chk("A5 反馈顶栏入口可开模态（.ylfb-mask + 标题「bug 与需求反馈」）",
                fb_open is True and fb_state.get("mask") is True and fb_state.get("title") == "bug 与需求反馈",
                json.dumps(fb_state, ensure_ascii=False))
            close_fb_modal(pg)

            pg.close()
            time.sleep(1)

            # ============ PH-3 B 账号页（ylt_max）：A3 见信 + A5 系统邮件 ============
            pg = ctx.new_page()
            wire(pg)
            pg.goto(WEB, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(1200)
            clear_auth(pg)
            pg.goto(WEB, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(6000)
            if not in_game(pg, USER_B, PASS, USER_B):
                print(body_text(pg)[:1500], flush=True)
                print("  [FATAL] B 账号未能进入游戏", flush=True)
                ctx.close()
                return 1
            print("  [nav] B（%s）已进入游戏（%.0fs）身份=%s" % (USER_B, time.time() - t0, who_am_i(pg)), flush=True)
            chk("ID B 页当前游戏身份=ylt_max", who_am_i(pg) == USER_B, who_am_i(pg))
            pg.wait_for_timeout(2500)
            dismiss_overlay(pg)
            pg.wait_for_timeout(500)

            print("\n== A3/A5 B 侧：信箱 3 封私信 + 系统邮件领取/已读 ==", flush=True)
            n200_b_before = len(net_mail_of(200))
            mb_open = pg.evaluate(JS_CLICK_TXT_EXACT, "信箱")
            pg.wait_for_timeout(1800)
            mails = pg.evaluate(r"""() => {
              const t = document.body.innerText || '';
              const cnt = (s) => t.split(s).length - 1;
              const replyBtns = Array.from(document.querySelectorAll('button')).filter(
                b => b.getBoundingClientRect().width > 0 && (b.innerText||'').replace(/\s+/g,'') === '回信');
              const claimBtns = Array.from(document.querySelectorAll('button')).filter(
                b => b.getBoundingClientRect().width > 0 && (b.innerText||'').replace(/\s+/g,'') === '领取');
              const senderTags = Array.from(document.querySelectorAll('span')).filter(
                s => (s.innerText||'').indexOf('发信人') >= 0 && s.getBoundingClientRect().width > 0)
                .map(s => (s.innerText||'').trim());
              return { pmTitle: cnt('来自 ' + """ + json.dumps(USER_A) + r""" + ' 的私信'),
                       gmRow: t.indexOf(""" + json.dumps(GM_MAIL_TITLE) + r""") >= 0,
                       replyN: replyBtns.length, claimN: claimBtns.length, senderTags,
                       unreadHead: (t.match(/信箱\s*·\s*未读\s*\d+/) || [''])[0] };
            }""")
            print("  mailbox:", json.dumps(mails, ensure_ascii=False), flush=True)
            chk("A3 B 信箱打开且出现 A 的 3 封私信（标题「来自 ylt_mid 的私信」×3）",
                mb_open is not None and mails.get("pmTitle") == 3,
                "open=%r pmTitle=%s" % (mb_open, mails.get("pmTitle")))
            chk("A3 3 行私信均显示「发信人 ylt_mid」", (mails.get("senderTags") or []) == ["发信人 " + USER_A] * 3,
                mails.get("senderTags"))
            chk("A3 私信行带「回信」按钮（恰 3 个）", mails.get("replyN") == 3, "replyN=%s" % mails.get("replyN"))
            chk("A5 系统邮件行不受影响（GM 行在列且带「领取」；领取钮恰 1 = 系统邮件行独有，私信行无领取）",
                mails.get("gmRow") is True and mails.get("claimN") == 1,
                "gmRow=%s claimN=%s" % (mails.get("gmRow"), mails.get("claimN")))
            # —— 领取（补偿式事务语义：B 刚进游戏若首笔存档未落库，服务端 409 可重试 ⇒ 轮询重试）
            claim_ok = False
            claim_toast = ""
            claim_errs = []
            for attempt in range(10):
                pg.evaluate("""() => {
                  const b = Array.from(document.querySelectorAll('button')).find(
                    x => x.getBoundingClientRect().width > 0 && (x.innerText||'').replace(/\\s+/g,'') === '领取');
                  if (b && !b.disabled) b.click();
                }""")
                got = ""
                for _ in range(14):
                    pg.wait_for_timeout(350)
                    t = body_text(pg)
                    if "已领取，灵石已入账" in t:
                        got = "已领取，灵石已入账"
                        break
                    for key in ("请先进游戏创建角色后再领取", "领取失败", "入账失败", "附件已领取", "没有可领取附件"):
                        if key in t:
                            got = key
                            break
                    if got:
                        break
                claim_toast = got
                if got == "已领取，灵石已入账":
                    claim_ok = True
                    print("  claim attempt %d -> OK（%s）" % (attempt + 1, got), flush=True)
                    break
                claim_errs.append(got or "(no-toast)")
                print("  claim attempt %d -> %r（等待存档落库后重试…）" % (attempt + 1, got), flush=True)
                pg.wait_for_timeout(2500)
            claims_net = [x for x in net_all if "/api/mail/claim" in x[2]]
            print("  claim_toast=%s errs=%s net=%s" % (claim_toast, claim_errs, json.dumps(claims_net)), flush=True)
            chk("A5 系统邮件领取：toast「已领取，灵石已入账」（重试链，补偿式事务语义）", claim_ok,
                "last=%r errs=%s claimPOST=%s" % (claim_toast, claim_errs[:4],
                                                  json.dumps([x[1] for x in claims_net])))
            pg.wait_for_timeout(800)
            # —— 全部已读
            pg.evaluate("""() => {
              const b = Array.from(document.querySelectorAll('button')).find(
                x => x.getBoundingClientRect().width > 0 && (x.innerText||'').replace(/\\s+/g,'') === '全部已读');
              if (b) b.click();
            }""")
            read_toast = False
            for _ in range(24):
                if "已全部标记已读" in body_text(pg):
                    read_toast = True
                    break
                pg.wait_for_timeout(250)
            pg.wait_for_timeout(1000)
            unread_after = pg.evaluate("""() => {
              const t = document.body.innerText || '';
              const m = t.match(/信箱\\s*·\\s*未读\\s*\\d+/) || [''];
              return m[0];
            }""")
            print("  read toast=%s head=%r" % (read_toast, unread_after), flush=True)
            chk("A5 全部已读：toast + 未读归零", read_toast and "未读 0" in unread_after, unread_after)

            # —— A3 回信
            replied = pg.evaluate(r"""(name) => {
              const norm = s => (s||'').replace(/\s+/g,'');
              const btns = Array.from(document.querySelectorAll('button')).filter(
                b => b.getBoundingClientRect().width > 0 && norm(b.innerText) === '回信');
              const target = btns.find(b => {
                let p = b, hops = 0;
                while (p && hops < 10) { p = p.parentElement; hops++;
                  if (p && norm(p.innerText).indexOf('发信人 ' + name) >= 0) return true; }
                return false;
              }) || btns[0];
              if (target) { target.click(); return true; } return false;
            }""", USER_A)
            pg.wait_for_timeout(700)
            pre3 = pg.evaluate("""() => ({ mask: !!document.querySelector('.ylpm-mask'),
                                           prefilled: (document.querySelector('.ylpm-in')||{}).value || null })""")
            print("  reply modal: click=%s %s" % (replied, json.dumps(pre3, ensure_ascii=False)), flush=True)
            chk("A3 B 点「回信」开模态且预填 ylt_mid",
                replied is True and pre3.get("mask") is True and pre3.get("prefilled") == USER_A,
                json.dumps(pre3, ensure_ascii=False))
            pg.evaluate("(v) => { const ta = document.querySelector('.ylpm-ta'); if (ta) ta.value = v; }", PM_REPLY)
            pg.evaluate("() => { const b = document.querySelector('.ylpm-btn'); if (b) b.click(); }")
            reply_toast = False
            for _ in range(24):
                if "私信已发送" in body_text(pg):
                    reply_toast = True
                    break
                pg.wait_for_timeout(250)
            pg.wait_for_timeout(500)
            n200_b_after = len(net_mail_of(200))
            print("  reply toast=%s posts200 %d -> %d" % (reply_toast, n200_b_before, n200_b_after), flush=True)
            chk("A3 B 回信 POST 200 + toast「私信已发送」", reply_toast and n200_b_after == n200_b_before + 1,
                "toast=%s posts200=%d->%d" % (reply_toast, n200_b_before, n200_b_after))
            pg.close()
            time.sleep(1)

            # ============ PH-4 A 账号回归页：信箱见回信 ============
            pg = ctx.new_page()
            wire(pg)
            pg.goto(WEB, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(1200)
            clear_auth(pg)
            pg.goto(WEB, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(6000)
            if not in_game(pg, USER_A, PASS, USER_A):
                print(body_text(pg)[:1500], flush=True)
                print("  [FATAL] A 账号二次进入失败", flush=True)
                ctx.close()
                return 1
            chk("ID A 二次页身份=ylt_mid", who_am_i(pg) == USER_A, who_am_i(pg))
            pg.wait_for_timeout(2500)
            dismiss_overlay(pg)
            pg.wait_for_timeout(500)

            print("\n== A3 A 侧：信箱出现回信 ==", flush=True)
            pg.evaluate(JS_CLICK_TXT_EXACT, "信箱")
            pg.wait_for_timeout(1800)
            a_mails = pg.evaluate(r"""() => {
              const t = document.body.innerText || '';
              const senderTags = Array.from(document.querySelectorAll('span')).filter(
                s => (s.innerText||'').indexOf('发信人') >= 0 && s.getBoundingClientRect().width > 0)
                .map(s => (s.innerText||'').trim());
              const replyBtns = Array.from(document.querySelectorAll('button')).filter(
                b => b.getBoundingClientRect().width > 0 && (b.innerText||'').replace(/\s+/g,'') === '回信');
              return { replyMail: t.indexOf('来自 ' + """ + json.dumps(USER_B) + r""" + ' 的私信') >= 0,
                       contentSeen: t.indexOf(""" + json.dumps(PM_REPLY) + r""") >= 0,
                       senderTags, replyN: replyBtns.length };
            }""")
            print("  A mailbox:", json.dumps(a_mails, ensure_ascii=False), flush=True)
            chk("A3 A 信箱出现 B 的回信（标题「来自 ylt_max 的私信」）", a_mails.get("replyMail") is True)
            chk("A3 回信正文在 A 信箱可见", a_mails.get("contentSeen") is True)
            chk("A3 回信行显示「发信人 ylt_max」+「回信」钮",
                ("发信人 " + USER_B) in (a_mails.get("senderTags") or []) and a_mails.get("replyN", 0) >= 1,
                "senders=%s replyN=%s" % (a_mails.get("senderTags"), a_mails.get("replyN")))
            close_any_modal(pg)
            pg.wait_for_timeout(400)

            print("\n== pageerror 终判（全程 A/B 三页合计；预期 4xx 网络噪声另判） ==", flush=True)
            print("  pageerror(%d): %s" % (len(page_errors), page_errors[:5]), flush=True)
            print("  浏览器侧 /api/mail/send 全量: %s" % net_mail, flush=True)
            chk("A5 全程无 pageerror（真实 JS 异常；本 run 预期 4xx=自400/超长400×2 等网络拒绝，不属此类）",
                len(page_errors) == 0, "; ".join(page_errors[:3]))

        # ---------- PH-5 服务端侧 DB 终态断言 ----------
        print("\n== PH-5 临时库终态断言 ==", flush=True)
        copy_db = db_snapshot()
        con = sqlite3.connect(copy_db)
        con.row_factory = sqlite3.Row
        mails_db = [dict(r) for r in con.execute(
            "SELECT id, user_id, sender, title, kind, attached_lingshi, claimed, read_at FROM mail ORDER BY id").fetchall()]
        fb_db = [dict(r) for r in con.execute("SELECT * FROM feedback ORDER BY id").fetchall()]
        con.close()
        print("  mail rows=%d" % len(mails_db), flush=True)
        for r in mails_db:
            print("   #%s sender=%s kind=%s claimed=%s read=%s title=%s" % (
                r["id"], r["sender"], r["kind"], r["claimed"], "Y" if r["read_at"] else "N", r["title"][:30]), flush=True)
        pm_a = [r for r in mails_db if r["sender"] == USER_A and r["kind"] == "player"]
        pm_b = [r for r in mails_db if r["sender"] == USER_B and r["kind"] == "player"]
        player_all = [r for r in mails_db if r["kind"] == "player"]
        gm_rows = [r for r in mails_db if r["title"] == GM_MAIL_TITLE]
        chk("DB 终态：player 行恰 4（A→B 连发 3 + B→A 回信 1，kind 全='player'）",
            len(player_all) == 4 and len(pm_a) == 3 and len(pm_b) == 1,
            "player=%d a=%d b=%d" % (len(player_all), len(pm_a), len(pm_b)))
        chk("DB A→B 三封连发已被 B 标记已读（read_at 非空）", all(r["read_at"] for r in pm_a),
            "read=%d/3" % sum(1 for r in pm_a if r["read_at"]))
        chk("DB GM 系统邮件 kind='system' 且已领取（claimed=1，不受 kind 列影响）",
            len(gm_rows) == 1 and gm_rows[0]["kind"] == "system" and gm_rows[0]["claimed"] == 1,
            json.dumps(gm_rows, ensure_ascii=False)[:200])
        print("  feedback rows=%d" % len(fb_db), flush=True)
        chk("DB feedback 恰 0 行（A5 仅验顶栏入口可开模态，未提交反馈）", len(fb_db) == 0, "rows=%d" % len(fb_db))

    finally:
        # ---------- cleanup（写明：杀进程 + 删临时库/profile/日志 + 拆 junction + 删 jsonl） ----------
        print("\n== cleanup ==", flush=True)
        for proc, name in ((har, "harness"), (srv, "server")):
            try:
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=8)
                    except Exception:
                        proc.kill()
                    print("  killed %s pid=%s" % (name, proc.pid), flush=True)
            except Exception as e:
                print("  kill %s err: %s" % (name, e), flush=True)
        try:
            srv_log.close()
            har_log.close()
        except Exception:
            pass
        kill_port(API_PORT)
        kill_port(WEB_PORT)
        if j_created and os.path.isdir(JUNCTION):
            subprocess.run(["cmd", "/c", "rmdir", JUNCTION], capture_output=True, encoding="utf-8", errors="replace")
            print("  removed junction %s（本次新建）" % JUNCTION, flush=True)
        shutil.rmtree(WORK, ignore_errors=True)
        print("  removed %s（临时库 database.sqlite+wal/shm、浏览器 profile、server/harness 日志，整目录删除）" % WORK, flush=True)
        if os.path.exists(JSONL):
            try:
                os.remove(JSONL)
                print("  removed %s（本次运行新建）" % JSONL, flush=True)
            except Exception as e:
                print("  jsonl cleanup err: %s" % e, flush=True)

    print("\n===== t_v102 结果 =====", flush=True)
    print("  PASS = %d   FAIL = %d   (耗时 %.0fs)" % (len(PASS_LIST), len(FAIL_LIST), time.time() - t0), flush=True)
    for f in FAIL_LIST:
        print("   FAIL: %s" % f, flush=True)
    return 1 if FAIL_LIST else 0


if __name__ == "__main__":
    sys.exit(main())
