# -*- coding: utf-8 -*-
r"""
t_v101.py — v1.1（FB-100 反馈入口迁移 + PM-101 玩家私信）浏览器全栈实测（本机临时环境，不碰线上）

被测对象（fail-closed 指纹校验，不符即退出，绝不产出半成品）：
    bundle = build/assets/index-v101-20261021.js   md5 75adea61942d4cc8dd44c922f986e296
    服务端 = srv/index_v28.ts                      md5 c7d06f5f0e0ff26e3a2b625180bebcfb

环境（SKILL §13.8：起服+测试同一条命令内完成；先清残留监听；独立端口 3322/3422 在 3001/3100~3210 外）：
    服务端：workbuddy-ai node 22.22.2-6 --experimental-strip-types 直跑 dev/srv/index_v28.ts
            独立 DATABASE_PATH=临时库；GM_PASSWORD/JWT_SECRET 随机生成仅经子进程环境变量传递、绝不落盘；
            feedback_inbox.jsonl 落 dev/srv/（测完删除）
    静态壳：localtest/harness.js --root=dev --bundle=index-v101-20261021.js（/myxxz/ + /yl/ 别名 + /api 反代 + no-store）
    浏览器：workbuddy-ai python（唯一带 playwright）+ launch_persistent_context，账号页严格串行
            （服务端单写者会话守卫：同账号两页并存会把旧页挤成只读，v1.0 实测）
    测试钩子：bundle 尾部追加 window.__Be/__YLogs（route.fulfill + no-store + setInterval 500ms 自愈重挂，SKILL §20.4）

断言清单（全过才算 ok）：
    A1 1440：顶栏「反馈」按钮 nextElementSibling === 顶栏「角色」按钮（DOM 相邻、同父）；
       底部操作栏恢复 5 卡（打坐/历练/秘境/炼丹·炼器/宗门）、无 .ylbar6 残留
    A2 390：☰ 抽屉有「反馈」入口，点开同一反馈模态（.ylfb-mask + 标题「bug 与需求反馈」）
    A3 反馈提交链路回归（沿用 1.0 断言语义）：合法提交 POST /api/feedback 恰 1 次 200 +
       toast「已收到，感谢反馈」+ 模态自动关；60s 内二连发客户端冷却拦截（status=-1 + 零新请求）
    A4 私信全链（双账号 ylt_mid ↔ ylt_max）：A 在「仙友录」给 B 发私信 200 → B「信箱」出现该信
       （DB kind='player' + UI 显示「发信人」）→ B 点「回信」回复 200 → A 的信箱出现回信 →
       「在线人物」行「私信」按钮同样可发（实际发送 200）
    A5 频控：30s 内二连发客户端冷却拦截（发送太频繁，请 N 秒后再试 + 零新请求）；
       服务端 409 文案（发送太频繁，请稍后再试）能在 UI 显示；发给自己 400（不能给自己发私信）能显示
    A6 非回归：普通系统邮件（GM 发、带灵石）领取 200+toast+入账、全部已读生效，且系统邮件行
       不出现「发信人/回信」；打坐按钮可点；全程无 pageerror（400/409 是预期网络噪声，非 JS 异常）
    A7 版本：顶栏徽标 v1.1（title 点击查看更新日志）；更新日志弹窗最新 [1.1]（1.1 在窗首段）+ 绿条「当前为最新版本」

用法：C:/Users/<USER>/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe localtest/t_v101.py
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
BUNDLE_REL = os.path.join("build", "assets", "index-v101-20261021.js")
SRV_REL = os.path.join("srv", "index_v28.ts")
BUNDLE_MD5 = "75adea61942d4cc8dd44c922f986e296"
SRV_MD5 = "c7d06f5f0e0ff26e3a2b625180bebcfb"
API_PORT, WEB_PORT = 3322, 3422                    # 3001/3100~3210 之外，v1.0 用的 3321/3421 不复用
WORK = r"<LOCAL>\Temp\yl_t101_sandbox"
JUNCTION = os.path.join(ROOT, "srv", "node_modules")
JUNCTION_SRC = r"D:\ARM-VPS\yl\server\node_modules"
JSONL = os.path.join(ROOT, "srv", "feedback_inbox.jsonl")
API = "http://127.0.0.1:%d" % API_PORT
WEB = "http://127.0.0.1:%d/myxxz/" % WEB_PORT

USER_A, USER_B, PASS = "ylt_mid", "ylt_max", "Test123456"
GM_MAIL_TITLE = "境界突破结算·A6系统邮件"
FB_CONTENT = "自动化测试反馈：请忽略本条（v101 e2e %d）" % int(time.time())
FB_CONTACT = "v101@test.local"
PM_MSG_1 = "道友你好，这是一封来自 ylt_mid 的测试私信（仙友录入口）"
PM_MSG_ONL = "第二次私信：来自在线人物面板入口（应正常送达）"
PM_REPLY = "收到！这是 ylt_max 的回信。"
# 临时 GM 口令：只在内存生成、经子进程环境变量传给服务端，绝不落盘（铁律）
GM_PASS = "t101gm_" + hashlib.md5(str(time.time_ns()).encode()).hexdigest()[:12]

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
    """http.client 直连 127.0.0.1，零代理参与（t_fb100 同款：urllib ProxyHandler 在本机失效）。"""
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

# A1：顶栏「反馈」与「角色」DOM 相邻 + 底部操作栏 5 卡 + 无 .ylbar6 残留
JS_TOPBAR_BAR = r"""() => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const norm = s => (s || '').replace(/\s+/g, '');
  const out = {};
  // 顶栏：反馈按钮（内含 span 反馈）与其 nextElementSibling
  const fb = Array.from(document.querySelectorAll('header button')).find(
    b => vis(b) && norm(b.innerText) === '反馈');
  out.fbFound = !!fb;
  if (fb) {
    const r = fb.getBoundingClientRect();
    out.fbRect = { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
    const nx = fb.nextElementSibling;
    out.nextTag = nx ? nx.tagName : null;
    out.nextText = nx ? norm(nx.innerText).slice(0, 12) : null;
    out.nextIsRole = !!nx && norm(nx.innerText).indexOf('角色') >= 0;
    out.sameParent = !!nx && nx.parentNode === fb.parentNode;
  }
  out.roleBtns = Array.from(document.querySelectorAll('header button')).filter(
    b => vis(b) && norm(b.innerText).indexOf('角色') >= 0).length;
  // 底部操作栏：打坐按钮向上找 grid 容器
  const med = Array.from(document.querySelectorAll('button')).find(
    b => vis(b) && norm(b.innerText).indexOf('打坐') >= 0);
  out.medFound = !!med;
  if (med) {
    const bar = med.closest('div.grid');
    out.barFound = !!bar;
    if (bar) {
      const kids = Array.from(bar.children).filter(k => k.tagName === 'DIV' || k.tagName === 'BUTTON');
      out.nCards = kids.length;
      out.labels = kids.map(k => norm(k.innerText).slice(0, 8));
      const br = bar.getBoundingClientRect();
      out.barRect = { w: Math.round(br.width), h: Math.round(br.height) };
      out.cols = getComputedStyle(bar).gridTemplateColumns.split(' ').filter(s => s && s !== 'none').length;
      out.overRight = kids.filter(k => k.getBoundingClientRect().right > window.innerWidth + 1).length;
      out.overLeft = kids.filter(k => k.getBoundingClientRect().left < -1).length;
    }
  }
  out.ylbar6 = document.querySelectorAll('.ylbar6').length;
  out.ylbar6Any = document.body.innerHTML.indexOf('ylbar6') >= 0;
  return out;
}"""


def main():
    t0 = time.time()
    print("== t_v101 全栈临时环境实测（v1.1：反馈入口迁移 + PM-101 私信） ==", flush=True)

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
    db_path = os.path.join(WORK, "database.sqlite")
    profile = os.path.join(WORK, "profile")
    srv_log = open(os.path.join(WORK, "server.log"), "wb")
    har_log = open(os.path.join(WORK, "harness.log"), "wb")

    env = dict(os.environ)
    env.update({
        "PORT": str(API_PORT),
        "DATABASE_PATH": db_path,
        "GM_PASSWORD": GM_PASS,
        "JWT_SECRET": "t101tmp_" + hashlib.md5(GM_PASS.encode()).hexdigest()[:16],
    })
    srv = subprocess.Popen([NODE, "--experimental-strip-types", s_path], cwd=WORK,
                           env=env, stdout=srv_log, stderr=srv_log,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    har = subprocess.Popen([NODE, os.path.join(HERE, "harness.js"),
                            "--port=%d" % WEB_PORT, "--api-port=%d" % API_PORT,
                            "--root=%s" % ROOT, "--bundle=index-v101-20261021.js"],
                           cwd=ROOT, stdout=har_log, stderr=har_log,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    print("  [pre] server pid=%s harness pid=%s api=%d web=%d" % (srv.pid, har.pid, API_PORT, WEB_PORT), flush=True)

    net_api = []        # (method, status, url) — /api/feedback 与 /api/mail/send 全量
    net_all = []        # (method, status, url) — 全部 /api/ 请求（证据链）
    page_errors = []    # 真实 JS 异常（pageerror）

    try:
        if not wait_http(API + "/api/market/items?page=1&limit=1", what="api"):
            print(open(os.path.join(WORK, "server.log"), encoding="utf-8", errors="replace").read()[-3000:], flush=True)
            return 2
        if not wait_http(WEB, what="web"):
            print(open(os.path.join(WORK, "harness.log"), encoding="utf-8", errors="replace").read()[-2000:], flush=True)
            return 2

        # ---------- PH-0b 注册双账号 + GM 系统邮件（A6 用） ----------
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
                              "content": "这是 GM 系统邮件（sender=system），附灵石用于 A6 领取回归。", "lingshi": 7})
        print("  [pre] GM mail -> %s %s" % (st, body[:120]), flush=True)
        if st != 200:
            print("  [pre][FATAL] GM 发信失败", flush=True)
            return 2

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
            if "/api/feedback" in u or "/api/mail/send" in u:
                net_api.append((r.request.method, r.status, u))

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

        def wait_toast(page, frag, tries=24):
            for _ in range(tries):
                if frag in body_text(page):
                    return True
                page.wait_for_timeout(250)
            return False

        def net_of(path, status=None):
            return [x for x in net_api if path in x[2] and x[0] == "POST" and (status is None or x[1] == status)]

        def in_game(page, user, pw_, dao):
            """分层进入：登录页/法门/道号/天赋/开始（t_fb100 同款，道号按账号参数化）。"""
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
            """读 store 里的角色名（道号=用户名，测试号专设）——防「页是旧的、号是错的」假进游戏。"""
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

        def close_fb_modal(page):
            for _ in range(3):
                page.evaluate("() => { const b = document.querySelector('.ylfb-ghost'); if (b) b.click(); }")
                page.wait_for_timeout(500)
                if not page.evaluate("() => !!document.querySelector('.ylfb-mask')"):
                    return True
            page.evaluate("() => { const m = document.querySelector('.ylfb-mask'); if (m) m.remove(); }")
            return False

        def close_pm_modal(page):
            for _ in range(3):
                page.evaluate("() => { const b = document.querySelector('.ylpm-ghost'); if (b) b.click(); }")
                page.wait_for_timeout(500)
                if not page.evaluate("() => !!document.querySelector('.ylpm-mask')"):
                    return True
            page.evaluate("() => { const m = document.querySelector('.ylpm-mask'); if (m) m.remove(); }")
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

        def open_fb_via(page, how):
            """how='topbar'：点顶栏反馈钮；how='drawer'：点抽屉反馈项。返回是否点到了。"""
            if how == "topbar":
                return page.evaluate("""() => {
                  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
                  const norm = s => (s || '').replace(/\\s+/g, '');
                  const b = Array.from(document.querySelectorAll('header button')).find(
                    x => vis(x) && norm(x.innerText) === '反馈');
                  if (b) { b.click(); return true; } return false;
                }""")
            # drawer：☰ 在 md:hidden 顶栏钮里
            page.evaluate("""() => {
              const b = Array.from(document.querySelectorAll('header button')).find(
                x => (x.className||'').indexOf('md:hidden') >= 0);
              if (b) b.click();
            }""")
            page.wait_for_timeout(1200)
            return page.evaluate("""() => {
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              const norm = s => (s || '').replace(/\\s+/g, '');
              const b = Array.from(document.querySelectorAll('button')).find(
                x => vis(x) && norm(x.innerText) === '反馈');
              if (b) { b.click(); return true; } return false;
            }""")

        def fb_modal_state(page):
            return page.evaluate("""() => ({
              mask: !!document.querySelector('.ylfb-mask'),
              title: (document.querySelector('.ylfb-title') || {}).textContent || null,
              taMax: (document.querySelector('.ylfb-ta') || {}).maxLength,
              btn: (document.querySelector('.ylfb-btn') || {}).textContent || null
            })""")

        def fb_submit(page, content, contact):
            page.evaluate("(v) => { const ta = document.querySelector('.ylfb-ta'); if (ta) ta.value = v; }", content)
            page.evaluate("(v) => { const i = document.querySelector('.ylfb-in'); if (i) i.value = v; }", contact)
            page.evaluate("() => { const b = document.querySelector('.ylfb-btn'); if (b) b.click(); }")

        def pm_open_and_send(page, to, content):
            """开私信模态（YLPM_OPEN）→ 填内容 → 点发送。返回 {opened, prefilled, info}。"""
            page.evaluate("(to) => { window.YLPM_OPEN(to); }", to)
            page.wait_for_timeout(500)
            st = page.evaluate("""(to) => {
              const inp = document.querySelector('.ylpm-in');
              const ta = document.querySelector('.ylpm-ta');
              return { mask: !!document.querySelector('.ylpm-mask'),
                       title: (document.querySelector('.ylpm-title')||{}).textContent || null,
                       prefilled: inp ? inp.value : null,
                       taMax: ta ? ta.maxLength : null };
            }""", to)
            page.evaluate("(v) => { const ta = document.querySelector('.ylpm-ta'); if (ta) ta.value = v; }", content)
            page.evaluate("() => { const b = document.querySelector('.ylpm-btn'); if (b) b.click(); }")
            return st

        def pm_info(page):
            return page.evaluate("() => (document.querySelector('.ylpm-info') || {}).textContent || ''")

        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                profile, headless=True, viewport={"width": 1440, "height": 900},
                args=["--no-proxy-server"])

            # ============ PH-2 A 账号页（ylt_mid） ============
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

            # ---------- A1 @1440 ----------
            print("\n== A1 顶栏相邻关系 + 底部操作栏 5 卡 @1440 ==", flush=True)
            j = pg.evaluate(JS_TOPBAR_BAR)
            print("  @1440: %s" % json.dumps(j, ensure_ascii=False)[:700], flush=True)
            chk("A1 顶栏「反馈」按钮在位可见", j.get("fbFound") is True,
                json.dumps(j.get("fbRect"), ensure_ascii=False))
            chk("A1 反馈按钮 nextElementSibling 恰为顶栏「角色」按钮（DOM 相邻 + 同父）",
                j.get("nextIsRole") is True and j.get("sameParent") is True,
                "next=%s(%s) sameParent=%s" % (j.get("nextTag"), j.get("nextText"), j.get("sameParent")))
            chk("A1 底部操作栏容器在位", j.get("barFound") is True, "medFound=%s" % j.get("medFound"))
            chk("A1 底部操作栏恢复 5 卡", j.get("nCards") == 5,
                "n=%s labels=%s" % (j.get("nCards"), j.get("labels")))
            chk("A1 5 卡含 打坐/历练/秘境/炼丹/宗门",
                j.get("labels") and all(any(k in (l or "") for l in j["labels"]) for k in ["打坐", "历练", "秘境", "炼丹", "宗门"]),
                j.get("labels"))
            chk("A1 无 .ylbar6 残留（0 节点 + 全文档无该类名）",
                j.get("ylbar6") == 0 and j.get("ylbar6Any") is False,
                "nodes=%s inHTML=%s" % (j.get("ylbar6"), j.get("ylbar6Any")))
            chk("A1 底栏无越界卡", not j.get("overRight") and not j.get("overLeft"),
                "overR=%s overL=%s" % (j.get("overRight"), j.get("overLeft")))

            # ---------- A7 版本链（先做，若首访更新日志弹窗自动弹出则就地断言） ----------
            print("\n== A7 版本：徽标 v1.1 + 更新日志弹窗 [1.1] + 绿条 ==", flush=True)
            badge = pg.evaluate("""() => {
              const b = Array.from(document.querySelectorAll('header button[title]'))
                .find(x => (x.getAttribute('title')||'').indexOf('更新日志') >= 0
                           && x.getBoundingClientRect().width > 0);
              return b ? { text: (b.innerText||'').trim(), title: b.getAttribute('title') } : null;
            }""")
            print("  badge:", badge, flush=True)
            chk("A7 顶栏徽标显示 v1.1", bool(badge) and badge.get("text") == "v1.1", json.dumps(badge, ensure_ascii=False))
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
              /* 模态真实标题是「版本信息」（CM 组件），badge 的 title 属性才是「点击查看更新日志」 */
              const hasTitle = t.indexOf('版本信息') >= 0;
              const greenEl = Array.from(document.querySelectorAll('[class*="text-green-400"]'))
                .find(x => (x.innerText || '').indexOf('当前为最新版本') >= 0);
              let box = greenEl, boxText = '';
              for (let i = 0; box && i < 8; i++) {
                box = box.parentElement;
                if (box && (box.innerText || '').indexOf('已是最新版本') >= 0) { boxText = box.innerText; break; }
              }
              return { hasTitle,
                       green: greenEl ? (greenEl.innerText || '').trim() : null,
                       boxText: boxText.slice(0, 200) };
            }""")
            print("  changelog:", json.dumps(chg, ensure_ascii=False)[:400], flush=True)
            chk("A7 更新日志弹窗打开（标题「版本信息」在窗）", chg.get("hasTitle") is True)
            chk("A7 绿条「当前为最新版本」且容器含「已是最新版本 v1.1」"
                "（绿条仅当 CHANGELOG 首个版本段解析结果 === 当前版本 1.1 时渲染，bundle CM: S=(a[0]?.version)===u）",
                chg.get("green") == "当前为最新版本" and "已是最新版本 v1.1" in (chg.get("boxText") or ""),
                "green=%s box=%r" % (chg.get("green"), (chg.get("boxText") or "")[:120]))
            close_any_modal(pg)
            pg.wait_for_timeout(400)

            # ---------- A2 @390 抽屉 ----------
            print("\n== A2 390 抽屉「反馈」入口 ==", flush=True)
            pg.set_viewport_size({"width": 390, "height": 844})
            pg.wait_for_timeout(1500)
            st390 = pg.evaluate("""() => {
              const burger = Array.from(document.querySelectorAll('header button'))
                .find(x => (x.className||'').indexOf('md:hidden') >= 0);
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              return { burgerVisible: !!burger && vis(burger) };
            }""")
            print("  @390: %s" % json.dumps(st390), flush=True)
            clicked = open_fb_via(pg, "drawer")
            pg.wait_for_timeout(700)
            box = fb_modal_state(pg)
            print("  modal:", json.dumps(box, ensure_ascii=False), flush=True)
            chk("A2 390 视口 ☰ 抽屉钮可见", st390.get("burgerVisible") is True, st390)
            chk("A2 抽屉「反馈」入口可点", clicked is True)
            chk("A2 点开的是同一反馈模态（.ylfb-mask + 「bug 与需求反馈」）",
                box.get("mask") is True and box.get("title") == "bug 与需求反馈",
                json.dumps(box, ensure_ascii=False))
            close_fb_modal(pg)
            pg.set_viewport_size({"width": 1440, "height": 900})
            pg.wait_for_timeout(1200)

            # ---------- A3 反馈提交链路（顶栏入口，1440） ----------
            print("\n== A3 反馈合法提交 + 60s 冷却 ==", flush=True)
            opened = open_fb_via(pg, "topbar")
            pg.wait_for_timeout(700)
            box = fb_modal_state(pg)
            chk("A3 顶栏「反馈」点开模态（标题=bug 与需求反馈）",
                opened is True and box.get("mask") is True and box.get("title") == "bug 与需求反馈",
                json.dumps(box, ensure_ascii=False))
            fb_submit(pg, FB_CONTENT, FB_CONTACT)
            toast = wait_toast(pg, "已收到，感谢反馈")
            pg.wait_for_timeout(600)
            mask_gone = pg.evaluate("() => !document.querySelector('.ylfb-mask')")
            posts = net_of("/api/feedback")
            print("  posts=%s toast=%s maskGone=%s" % (posts, toast, mask_gone), flush=True)
            chk("A3 POST /api/feedback 恰 1 次且 200", len(posts) == 1 and posts[0][1] == 200, json.dumps(posts))
            chk("A3 toast「已收到，感谢反馈」出现", toast)
            chk("A3 提交成功后模态自动关闭", mask_gone is True)

            cool = pg.evaluate("""() => new Promise(res => {
              window.YLFB_SEND('bug', '二连发测试内容（应被冷却拦截）', '', r => res(r));
            })""")
            posts2 = net_of("/api/feedback")
            print("  cooldown:", json.dumps(cool, ensure_ascii=False), "posts=%d" % len(posts2), flush=True)
            chk("A3 60s 内二连发被客户端冷却拦截（status=-1 + 零新请求）",
                bool(cool) and cool.get("ok") is False and cool.get("status") == -1
                and "提交太频繁" in (cool.get("msg") or "") and len(posts2) == 1,
                json.dumps(cool, ensure_ascii=False))

            # ---------- A5c 发给自己 400（先于任何成功私信，天然无冷却干扰） ----------
            print("\n== A5c 发给自己 → 服务端 400 文案显示 ==", flush=True)
            st = pm_open_and_send(pg, USER_A, "给自己发一条测试私信（应被 400 拒绝）")
            info400 = ""
            ok400 = False
            for _ in range(20):
                pg.wait_for_timeout(250)
                info400 = pm_info(pg)
                if "不能给自己发私信" in info400:
                    ok400 = True
                    break
            posts400 = net_of("/api/mail/send", 400)
            print("  modal=%s info=%r posts400=%s" % (json.dumps(st, ensure_ascii=False), info400, posts400), flush=True)
            chk("A5c 私信模态在位且收件人预填自己", st.get("mask") is True and st.get("prefilled") == USER_A,
                json.dumps(st, ensure_ascii=False))
            chk("A5c 服务端 400「不能给自己发私信」在 .ylpm-info 显示", ok400, info400)
            chk("A5c 网络面板可见 POST 400", len(posts400) == 1 and posts400[0][1] == 400, json.dumps(posts400))
            close_pm_modal(pg)

            # ---------- A4·leg1 仙友录发私信 ----------
            print("\n== A4·leg1 仙友录加好友 + 发私信 ==", flush=True)
            fr_open = pg.evaluate(JS_CLICK_TXT_EXACT, "仙友录")
            pg.wait_for_timeout(1200)
            add_r = pg.evaluate("""(name) => {
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
            }""", USER_B)
            pg.wait_for_timeout(1200)
            print("  friends modal open=%r add=%r" % (fr_open, add_r), flush=True)
            chk("A4 打开仙友录并提交加好友（ylt_max，服务端自动互为好友）",
                fr_open is not None and add_r == "ok", "open=%r add=%r" % (fr_open, add_r))
            row_ok = False
            for _ in range(10):
                row_ok = pg.evaluate("""(name) => {
                  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
                  const norm = s => (s||'').replace(/\\s+/g,'');
                  const rows = Array.from(document.querySelectorAll('*')).filter(
                    x => vis(x) && norm(x.innerText).indexOf(name) >= 0
                         && x.querySelector && Array.from(x.querySelectorAll('button')).some(
                           b => norm(b.innerText) === '私信'));
                  return rows.length > 0;
                }""", USER_B)
                if row_ok:
                    break
                pg.wait_for_timeout(600)
            chk("A4 好友列表出现 ylt_max 行且带「私信」按钮", row_ok)
            sent1 = pg.evaluate("""(name) => {
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              const norm = s => (s||'').replace(/\\s+/g,'');
              const btns = Array.from(document.querySelectorAll('button')).filter(
                x => vis(x) && norm(x.innerText) === '私信');
              // 取含该好友名行内的那个私信钮
              const target = btns.find(b => {
                let p = b, hops = 0;
                while (p && hops < 8) { p = p.parentElement; hops++;
                  if (p && norm(p.innerText).indexOf(name) >= 0) return true; }
                return false;
              }) || btns[0];
              if (target) { target.click(); return true; } return false;
            }""", USER_B)
            pg.wait_for_timeout(700)
            pre = pg.evaluate("""() => ({ mask: !!document.querySelector('.ylpm-mask'),
                                          prefilled: (document.querySelector('.ylpm-in')||{}).value || null })""")
            print("  pm modal: click=%s %s" % (sent1, json.dumps(pre, ensure_ascii=False)), flush=True)
            chk("A4 点好友行「私信」开写信模态且收件人预填 ylt_max",
                sent1 is True and pre.get("mask") is True and pre.get("prefilled") == USER_B,
                json.dumps(pre, ensure_ascii=False))
            pg.evaluate("(v) => { const ta = document.querySelector('.ylpm-ta'); if (ta) ta.value = v; }", PM_MSG_1)
            pg.evaluate("() => { const b = document.querySelector('.ylpm-btn'); if (b) b.click(); }")
            toast_pm = wait_toast(pg, "私信已发送")
            pg.wait_for_timeout(600)
            pm_gone = pg.evaluate("() => !document.querySelector('.ylpm-mask')")
            posts200 = net_of("/api/mail/send", 200)
            print("  toast=%s gone=%s posts200=%s" % (toast_pm, pm_gone, posts200), flush=True)
            chk("A4·leg1 私信 POST 200（恰 1 次成功）", len(posts200) == 1, json.dumps(posts200))
            chk("A4·leg1 toast「私信已发送」+ 模态自动关", toast_pm and pm_gone,
                "toast=%s gone=%s" % (toast_pm, pm_gone))
            t_send1 = time.time()
            close_any_modal(pg)   # 关仙友录面板，别让它挡后续
            pg.wait_for_timeout(400)

            # ---------- A5a 30s 内二连发（客户端冷却） ----------
            print("\n== A5a 30s 内二连发 → 客户端冷却拦截 ==", flush=True)
            st = pm_open_and_send(pg, USER_B, "二连发测试（应被客户端冷却拦截）")
            info_cool = ""
            ok_cool = False
            for _ in range(16):
                pg.wait_for_timeout(250)
                info_cool = pm_info(pg)
                if "发送太频繁" in info_cool:
                    ok_cool = True
                    break
            n_after = len(net_of("/api/mail/send"))
            print("  info=%r net_total=%d" % (info_cool, n_after), flush=True)
            chk("A5a 二连发被客户端冷却拦截（「发送太频繁，请 N 秒后再试」）",
                ok_cool and "秒后再试" in info_cool, info_cool)
            chk("A5a 冷却拦截零新网络请求", n_after == 2, "net=%d（应为 2：400 + 200）" % n_after)
            close_pm_modal(pg)

            # ---------- A5b1 服务端 409（裸 API，同 30s 窗口内） ----------
            st409, body409 = http("POST", API + "/api/mail/send", token=tok_a,
                                  body={"to": USER_B, "content": "裸 API 二连发（应 409）"})
            print("  raw resend -> %s %s" % (st409, body409[:120]), flush=True)
            try:
                err409 = (json.loads(body409) or {}).get("error") or ""
            except Exception:
                err409 = ""
            chk("A5b1 服务端 30s 频控生效（裸 API 409 + 文案「发送太频繁，请稍后再试」）",
                st409 == 409 and err409 == "发送太频繁，请稍后再试", "%s %s" % (st409, body409[:100]))

            # ---------- A5b2 刷新页面（客户端冷却归零）→ UI 再发 → 服务端 409 文案显示 ----------
            print("\n== A5b2 reload 后 UI 再发 → 服务端 409 文案显示 ==", flush=True)
            pg.reload(wait_until="domcontentloaded")
            pg.wait_for_timeout(5000)
            if not in_game(pg, USER_A, PASS, USER_A):
                chk("A5b2 reload 后回到游戏", False, "未回到游戏")
            pg.wait_for_timeout(1200)
            dismiss_overlay(pg)
            st = pm_open_and_send(pg, USER_B, "reload 后再发（应吃服务端 409）")
            info409 = ""
            ok409 = False
            for _ in range(20):
                pg.wait_for_timeout(250)
                info409 = pm_info(pg)
                if "发送太频繁" in info409:
                    ok409 = True
                    break
            posts409 = net_of("/api/mail/send", 409)
            print("  info=%r posts409=%s" % (info409, posts409), flush=True)
            chk("A5b2 reload 后 UI 再发吃到服务端 409（POST 409 可见）", len(posts409) == 1, json.dumps(posts409))
            chk("A5b2 服务端 409 文案在 .ylpm-info 显示", ok409 and "发送太频繁" in info409, info409)
            close_pm_modal(pg)

            # ---------- 等 30s 冷却窗口过去（对 t_send1） ----------
            waitmore = t_send1 + 31.5 - time.time()
            if waitmore > 0:
                print("  [wait] 冷却窗口还剩 %.0fs…" % waitmore, flush=True)
                time.sleep(waitmore)

            # ---------- A4·leg2 在线人物面板「私信」 ----------
            print("\n== A4·leg2 在线人物行「私信」按钮 ==", flush=True)
            # B 尚未开过浏览器页 ⇒ 用 /api/session/claim 直写 active_sessions（last_seen=now），
            # 让 ylt_max 落进「最近 5 分钟活跃」在线窗（ONLINE_WINDOW_MS，srv /api/online/players 口径）
            hb = http("POST", API + "/api/session/claim", token=tok_b, body={"device": "t101-probe"})
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
                if "在线人物" in t and USER_B in t:
                    onl_seen = True
                    break
            print("  panel open=%s ylt_max seen=%s" % (onl_open, onl_seen), flush=True)
            chk("A4 在线人物面板打开且列出 ylt_max（5 分钟活跃窗）", onl_open is True and onl_seen,
                "open=%s seen=%s body=%s" % (onl_open, onl_seen, body_text(pg)[-200:] if not onl_seen else ""))
            sent2 = pg.evaluate("""(name) => {
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              const norm = s => (s||'').replace(/\\s+/g,'');
              const btns = Array.from(document.querySelectorAll('button')).filter(
                x => vis(x) && norm(x.innerText) === '私信');
              const target = btns.find(b => {
                let p = b, hops = 0;
                while (p && hops < 10) { p = p.parentElement; hops++;
                  if (p && norm(p.innerText).indexOf(name) >= 0) return true; }
                return false;
              });
              if (target) { target.click(); return true; } return false;
            }""", USER_B)
            pg.wait_for_timeout(700)
            pre2 = pg.evaluate("""() => ({ mask: !!document.querySelector('.ylpm-mask'),
                                           prefilled: (document.querySelector('.ylpm-in')||{}).value || null })""")
            print("  online-row pm: click=%s %s" % (sent2, json.dumps(pre2, ensure_ascii=False)), flush=True)
            chk("A4 在线人物行「私信」开模态且预填 ylt_max",
                sent2 is True and pre2.get("mask") is True and pre2.get("prefilled") == USER_B,
                json.dumps(pre2, ensure_ascii=False))
            pg.evaluate("(v) => { const ta = document.querySelector('.ylpm-ta'); if (ta) ta.value = v; }", PM_MSG_ONL)
            pg.evaluate("() => { const b = document.querySelector('.ylpm-btn'); if (b) b.click(); }")
            toast2 = wait_toast(pg, "私信已发送")
            pg.wait_for_timeout(500)
            gone2 = pg.evaluate("() => !document.querySelector('.ylpm-mask')")
            posts200b = net_of("/api/mail/send", 200)
            print("  toast=%s gone=%s posts200=%s" % (toast2, gone2, posts200b), flush=True)
            chk("A4 在线人物入口实际发送 POST 200 + toast + 模态关",
                len(posts200b) == 2 and toast2 and gone2,
                "posts200=%s toast=%s gone=%s" % (json.dumps(posts200b), toast2, gone2))
            t_send2 = time.time()

            pg.close()
            time.sleep(1)

            # ============ PH-3 B 账号页（ylt_max） ============
            pg = ctx.new_page()
            wire(pg)
            pg.goto(WEB, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(1200)
            clear_auth(pg)          # A 的 token 还在 localStorage，先清掉再重载，确保落在登录页
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

            print("\n== A4·B 侧：信箱收私信 + 回信；A6 系统邮件领取/已读 ==", flush=True)
            n200_before_b = len(net_of("/api/mail/send", 200))   # A 页已产生 2 次 200（leg1 + 在线面板）
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
              return { hasMailTitle: cnt('来自 ' + """ + json.dumps(USER_A) + r""" + ' 的私信'),
                       gmRow: t.indexOf(""" + json.dumps(GM_MAIL_TITLE) + r""") >= 0,
                       replyN: replyBtns.length, claimN: claimBtns.length, senderTags,
                       unreadHead: (t.match(/信箱\s*·\s*未读\s*\d+/) || [''])[0] };
            }""")
            print("  mailbox:", json.dumps(mails, ensure_ascii=False), flush=True)
            chk("A4 B 信箱打开", mb_open is not None and mails.get("hasMailTitle", 0) >= 1,
                "open=%r %s" % (mb_open, json.dumps(mails, ensure_ascii=False)[:160]))
            chk("A4 B 信箱出现 A 的两封私信（标题「来自 ylt_mid 的私信」×2）",
                mails.get("hasMailTitle", 0) == 2, "count=%s" % mails.get("hasMailTitle"))
            chk("A4 私信行显示「发信人 ylt_mid」", (mails.get("senderTags") or []) == ["发信人 " + USER_A] * 2,
                mails.get("senderTags"))
            chk("A4 私信行带「回信」按钮（恰 2 个）", mails.get("replyN") == 2, "replyN=%s" % mails.get("replyN"))
            chk("A6 系统邮件（GM，sender=system）在列且带「领取」按钮（不受 kind 列影响）",
                mails.get("gmRow") is True and mails.get("claimN") == 1,
                "gmRow=%s claimN=%s" % (mails.get("gmRow"), mails.get("claimN")))
            # 系统邮件行不得出现「发信人/回信」：回信钮总数==私信封数 + 发信人标签只指向 ylt_mid 已证
            # —— 领取（claim，带重试）：mailClaimCore 是「补偿式事务」——B 刚进游戏若首笔存档尚未落库，
            #    服务端 409「请先进游戏创建角色后再领取」并把 claimed 回滚为 0，产品语义即「可重试」
            #    （srv index_v28.ts mailClaimCore 注释原文）。⇒ 测试按产品语义轮询重试，直至入账或预算耗尽。
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
                for _ in range(14):     # ~5s/attempt 内等 toast
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
            chk("A6 系统邮件领取：toast「已领取，灵石已入账」（重试链，补偿式事务语义）", claim_ok,
                "last=%r errs=%s claimPOST=%s" % (claim_toast, claim_errs[:4],
                                                  json.dumps([x[1] for x in claims_net])))
            pg.wait_for_timeout(800)
            # —— 全部已读
            pg.evaluate("""() => {
              const b = Array.from(document.querySelectorAll('button')).find(
                x => x.getBoundingClientRect().width > 0 && (x.innerText||'').replace(/\\s+/g,'') === '全部已读');
              if (b) b.click();
            }""")
            read_toast = wait_toast(pg, "已全部标记已读")
            pg.wait_for_timeout(1000)
            unread_after = pg.evaluate("""() => {
              const t = document.body.innerText || '';
              const m = t.match(/信箱\\s*·\\s*未读\\s*\\d+/) || [''];
              return m[0];
            }""")
            print("  read toast=%s head=%r" % (read_toast, unread_after), flush=True)
            chk("A6 全部已读：toast + 未读归零", read_toast and "未读 0" in unread_after, unread_after)
            # —— 回信（点第一封私信行的回信）
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
            chk("A4 B 点「回信」开模态且预填 ylt_mid",
                replied is True and pre3.get("mask") is True and pre3.get("prefilled") == USER_A,
                json.dumps(pre3, ensure_ascii=False))
            pg.evaluate("(v) => { const ta = document.querySelector('.ylpm-ta'); if (ta) ta.value = v; }", PM_REPLY)
            pg.evaluate("() => { const b = document.querySelector('.ylpm-btn'); if (b) b.click(); }")
            toast3 = wait_toast(pg, "私信已发送")
            pg.wait_for_timeout(500)
            n200_after_b = len(net_of("/api/mail/send", 200))
            print("  reply toast=%s posts200 %d -> %d" % (toast3, n200_before_b, n200_after_b), flush=True)
            chk("A4 B 回信 POST 200 + toast", toast3 and n200_after_b == n200_before_b + 1,
                "toast=%s posts200=%d->%d" % (toast3, n200_before_b, n200_after_b))
            t_reply = time.time()
            pg.close()
            time.sleep(1)

            # ============ PH-4 A 账号回归页：信箱见回信 + A6 打坐 ============
            pg = ctx.new_page()
            wire(pg)
            pg.goto(WEB, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(1200)
            clear_auth(pg)          # B 的 token 在 localStorage，清掉换回 A
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

            print("\n== A4·A 侧：信箱出现回信 ==", flush=True)
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
            chk("A4 A 信箱出现 B 的回信（标题「来自 ylt_max 的私信」）", a_mails.get("replyMail") is True)
            chk("A4 回信正文在 A 信箱可见", a_mails.get("contentSeen") is True)
            chk("A4 回信行显示「发信人 ylt_max」+「回信」钮",
                ("发信人 " + USER_B) in (a_mails.get("senderTags") or []) and a_mails.get("replyN", 0) >= 1,
                "senders=%s replyN=%s" % (a_mails.get("senderTags"), a_mails.get("replyN")))
            close_any_modal(pg)
            pg.wait_for_timeout(400)

            print("\n== A6 非回归：打坐按钮 ==", flush=True)
            med = pg.evaluate("""() => {
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              const norm = s => (s||'').replace(/\\s+/g,'');
              const b = Array.from(document.querySelectorAll('button')).find(
                x => vis(x) && norm(x.innerText).indexOf('打坐') >= 0);
              if (!b) return null;
              return { label: norm(b.innerText).slice(0, 12), disabled: !!b.disabled };
            }""")
            print("  打坐 before: %s" % json.dumps(med, ensure_ascii=False), flush=True)
            chk("A6 打坐按钮在位且未禁用（可点）", bool(med) and med.get("disabled") is False,
                json.dumps(med, ensure_ascii=False))
            clicked2 = pg.evaluate("""() => {
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              const norm = s => (s||'').replace(/\\s+/g,'');
              const b = Array.from(document.querySelectorAll('button')).find(
                x => vis(x) && norm(x.innerText).indexOf('打坐') >= 0);
              if (b) { b.click(); return true; } return false;
            }""")
            state_after = None
            for _ in range(10):
                pg.wait_for_timeout(500)
                state_after = pg.evaluate("""() => {
                  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
                  const norm = s => (s||'').replace(/\\s+/g,'');
                  const b = Array.from(document.querySelectorAll('button')).find(
                    x => vis(x) && norm(x.innerText).indexOf('打坐') >= 0);
                  return b ? { label: norm(b.innerText).slice(0, 12), disabled: !!b.disabled } : null;
                }""")
                if state_after and (state_after.get("disabled") or "停止" in (state_after.get("label") or "")):
                    break
            print("  打坐 after: %s" % json.dumps(state_after, ensure_ascii=False), flush=True)
            chk("A6 打坐点击生效（按钮转禁用/打坐中态）",
                clicked2 is True and bool(state_after)
                and (state_after.get("disabled") is True or "停止" in (state_after.get("label") or "")),
                json.dumps(state_after, ensure_ascii=False))

            print("\n== pageerror 终判（全程 A/B 两账号三页合计） ==", flush=True)
            print("  pageerror(%d): %s" % (len(page_errors), page_errors[:5]), flush=True)
            print("  网络面板（feedback + mail/send 全量）: %s" % net_api, flush=True)
            chk("A6 全程无 pageerror（真实 JS 异常；400/409 为预期网络拒绝，不属此类）",
                len(page_errors) == 0, "; ".join(page_errors[:3]))

        # ---------- PH-5 服务端侧 DB 断言 ----------
        print("\n== PH-5 临时库断言（mail.kind / feedback） ==", flush=True)
        copy_db = os.path.join(WORK, "copy.sqlite")
        shutil.copyfile(db_path, copy_db)
        for ext in ("-wal", "-shm"):
            if os.path.exists(db_path + ext):
                shutil.copyfile(db_path + ext, copy_db + ext)
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
        pm_from_a = [r for r in mails_db if r["sender"] == USER_A]
        pm_from_b = [r for r in mails_db if r["sender"] == USER_B]
        gm_rows = [r for r in mails_db if r["title"] == GM_MAIL_TITLE]
        chk("DB 私信 A→B 恰 2 封且 kind 全='player'", len(pm_from_a) == 2 and all(r["kind"] == "player" for r in pm_from_a),
            "n=%d kinds=%s" % (len(pm_from_a), [r["kind"] for r in pm_from_a]))
        chk("DB 回信 B→A 恰 1 封且 kind='player'", len(pm_from_b) == 1 and pm_from_b[0]["kind"] == "player",
            "n=%d" % len(pm_from_b))
        chk("DB GM 系统邮件 kind='system' 且已领取（claimed=1，不受 kind 列影响）",
            len(gm_rows) == 1 and gm_rows[0]["kind"] == "system" and gm_rows[0]["claimed"] == 1,
            json.dumps(gm_rows, ensure_ascii=False)[:200])
        a_pm_rows = [r for r in pm_from_a if r["read_at"]]
        chk("DB A→B 两封私信已被 B 标记已读（read_at 非空）", len(a_pm_rows) == 2,
            "read=%d/2" % len(a_pm_rows))
        print("  feedback rows=%d" % len(fb_db), flush=True)
        frow = fb_db[0] if fb_db else {}
        chk("DB feedback 恰 1 行（冷却拦截未入库）", len(fb_db) == 1, "rows=%d" % len(fb_db))
        chk("DB feedback 行内容/版本正确（kind=bug version=1.1）",
            frow.get("content") == FB_CONTENT and frow.get("kind") == "bug" and frow.get("version") == "1.1",
            "kind=%s version=%s" % (frow.get("kind"), frow.get("version")))

    finally:
        # ---------- cleanup ----------
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
        print("  removed %s（临时库/浏览器profile/服务端日志）" % WORK, flush=True)
        if os.path.exists(JSONL):
            try:
                os.remove(JSONL)
                print("  removed %s（本次运行新建）" % JSONL, flush=True)
            except Exception as e:
                print("  jsonl cleanup err: %s" % e, flush=True)

    print("\n===== t_v101 结果 =====", flush=True)
    print("  PASS = %d   FAIL = %d   (耗时 %.0fs)" % (len(PASS_LIST), len(FAIL_LIST), time.time() - t0), flush=True)
    for f in FAIL_LIST:
        print("   FAIL: %s" % f, flush=True)
    return 1 if FAIL_LIST else 0


if __name__ == "__main__":
    sys.exit(main())
