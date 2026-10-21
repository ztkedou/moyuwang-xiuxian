# -*- coding: utf-8 -*-
r"""
t_fb100.py — FB-100 玩家反馈 + v1.0 版本链 + R-254/R-255 浏览器实测（本机全栈临时环境，不碰线上）

被测对象（fail-closed 指纹校验，不符即退出，绝不产出半成品）：
    bundle = build/assets/index-v100-20261020.js   md5 c88305b9af37d39e8ed7cebc5736f32a
    服务端 = srv/index_v28.ts                      md5 dea7a8553bff3b22f21ad25a0792d66c

环境（SKILL §13.8：起服+测试在同一条命令内完成；先清残留监听进程；独立端口避开 3001/3100~3210）：
    服务端：node --experimental-strip-types 直跑 dev/srv/index_v28.ts
            ★ 环境漂移：任务书写 versions/22.22.2-3，该目录已不存在（SKILL §18.17），
              实际用 versions/22.22.2-6（v22.22.2，实测可跑 --experimental-strip-types）。
            依赖：ESM 从 .ts 所在目录向上解析 ⇒ dev/srv/node_modules junction →
              D:\ARM-VPS\yl\server\node_modules（sandbox.sh:35 同源），.gitignore 已盖 node_modules/
            独立 DATABASE_PATH=临时库；GM_PASSWORD/JWT_SECRET 随机生成，仅经子进程环境变量
            传递、绝不落盘；feedback_inbox.jsonl 落 __dirname=dev/srv/（测完删除）
    静态壳：localtest/harness.js --root=dev --bundle=index-v100-20261020.js（/myxxz/ + /api 反代 + 全响应 no-store）
    浏览器：workbuddy-ai python（唯一带 playwright）+ launch_persistent_context
            （A8「真关页面后全新打开」用同一 profile 重启浏览器进程实现，navigation type=navigate）
    测试钩子：bundle 尾部追加 window.__Be/__YLogs（route.fulfill + no-store + setInterval 500ms 自愈重挂，SKILL §20.4）
    时序依据：YLR256Boot 挂 player-subscribe 后 1200ms（读档完成后才回放/结算，日志不被
              applyRemoteSave 的 logs 替换冲掉 —— bundle @598650 / @596269 实测）⇒ b1/b2 断言前等 2.5s

断言清单（全过才算 ok）：
    A1 390/1440 底部操作栏 6 卡完整渲染无溢出；反馈卡 previousElementSibling 关系
    A2 反馈模态「bug 与需求反馈」；空内容/超长内容客户端拦截（零网络请求）
    A3 合法提交 POST /api/feedback 200 + toast + 模态关；60s 内二连发客户端冷却拦截
    A4 临时库 feedback 表 1 行字段齐全；feedback_inbox.jsonl 1 行 JSON 可解析且与库行对应
    A5 GM 链路 login → list 见行 → status=resolved 生效
    A6 顶栏徽标 v1.0；设置页游戏版本 v1.0；更新日志弹窗 [1.0] + 绿条「当前为最新版本」
    A7 非回归：打坐可点；全程无 pageerror（HTTP 4xx 预期噪声与真实 JS 异常分开记账）
    A8 R-255 三分行为：reload=开关仍在+会话续接不重复发奖；真关页重开(navigate)=开关关+补结算日志；
       开着 ≥60s 绝不自停
    A9 R-254：「年龄/危险度」与「历练收获」不在同一条日志（r257 旁路层落法，读 store.logs + DOM 双判）

用法：C:/Users/<USER>/.workbuddy-ai/binaries/python/envs/default/Scripts/python.exe localtest/t_fb100.py
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
BUNDLE_REL = os.path.join("build", "assets", "index-v100-20261020.js")
SRV_REL = os.path.join("srv", "index_v28.ts")
BUNDLE_MD5 = "09c4ace10fc7eaab22550cc550dfd668"   # 2026-10-21 A8 修复重建（r256v2 会话重建三重自愈）
SRV_MD5 = "dea7a8553bff3b22f21ad25a0792d66c"
API_PORT, WEB_PORT = 3321, 3421                    # 实测空闲，且在 3001/3100~3210 之外
WORK = r"<LOCAL>\Temp\yl_fb100_sandbox"
JUNCTION = os.path.join(ROOT, "srv", "node_modules")
JUNCTION_SRC = r"D:\ARM-VPS\yl\server\node_modules"
JSONL = os.path.join(ROOT, "srv", "feedback_inbox.jsonl")
API = "http://127.0.0.1:%d" % API_PORT
WEB = "http://127.0.0.1:%d/myxxz/" % WEB_PORT
USER, PASS = "ylfb100a", "Test123456"
USER2 = "ylfb100b"                    # A1@390 独立页专用（避开服务端单写者会话守卫）
DAOH = "ylfb100"
# 临时 GM 口令：只在内存生成、经子进程环境变量传给服务端，绝不落盘（铁律）
GM_PASS = "fb100gm_" + hashlib.md5(str(time.time_ns()).encode()).hexdigest()[:12]

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
    """★ 不走 urllib.request.urlopen：本机 python 3.13.12 上 install_opener(ProxyHandler({}))
    实测抛 'ProxyHandler' object has no attribute 'open'（ylc_local.py:25 的旧修法在本机失效）。
    http.client 直连，零代理参与，对 127.0.0.1 天然安全。"""
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
    """清掉占用端口的残留监听进程（SKILL §13.8）。"""
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
    """传输层就绪判据：任何真实 HTTP 状态（含 4xx/5xx）都证明 HTTP 层在应答；
    功能就绪由其后的 register=201 硬校验兜底（空库冷启动 market/items 可能非 200）。"""
    last = (-1, "")
    for i in range(tries):
        last = http("GET", url, timeout=4)
        if last[0] != -1:
            print("  [pre] ready after %ds: %s %s -> http %s" % (i + 1, what, url, last[0]), flush=True)
            return True
        time.sleep(1)
    print("  [pre] NOT ready: %s last=%s" % (url, last), flush=True)
    return False


# ---------------------------------------------------------------- 浏览器侧 JS 片段
JS_CLICK_TXT = r"""(txt) => {
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const norm = s => (s || '').replace(/\s+/g, '');
  const b = Array.from(document.querySelectorAll('button')).find(x => vis(x) && norm(x.innerText).indexOf(norm(txt)) >= 0);
  if (b) { b.click(); return (b.innerText || '').trim().slice(0, 40); }
  return null;
}"""

JS_BAR = r"""(vw) => {
  const diag = { innerW: window.innerWidth, innerH: window.innerHeight,
                 mq768: window.matchMedia('(min-width:768px)').matches,
                 styleHook: !!document.getElementById('ylfb-style') };
  /* 全量枚举 .ylbar6（可能存在多布局分支实例），取第一个「可见」实例 */
  const all = Array.from(document.querySelectorAll('.ylbar6')).map((bar, idx) => {
    const r = bar.getBoundingClientRect();
    return { idx, w: Math.round(r.width), h: Math.round(r.height), top: Math.round(r.top) };
  });
  const bar = Array.from(document.querySelectorAll('.ylbar6')).find(b => {
    const r = b.getBoundingClientRect(); return r.width > 100 && r.height > 40;
  });
  if (!bar) return Object.assign({ err: 'no visible .ylbar6', allBars: all,
                                   scrollW: document.documentElement.scrollWidth,
                                   bodyTail: (document.body.innerText || '').slice(-300) }, diag);
  const br = bar.getBoundingClientRect();
  const kids = Array.from(bar.children);
  /* N4 实测结构：打坐/历练是 div.relative 包裹（内含自动开关小钮），
     秘境/炼丹·炼器/宗门是裸 button，反馈是本特性插入的 button，页脚是 <p> —— 排除 p */
  const cards = kids.filter(k => k.tagName === 'DIV' || k.tagName === 'BUTTON');
  const info = cards.map(k => {
    const r = k.getBoundingClientRect();
    return { tag: k.tagName, label: ((k.innerText || '').replace(/\s+/g, ' ').trim() || '').slice(0, 18),
             x: Math.round(r.left), r: Math.round(r.right), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
  });
  const fbBtn = cards.find(k => k.tagName === 'BUTTON' && (k.innerText || '').indexOf('反馈') >= 0);
  let prevRel = null, prevGeom = null, prevLabel = null;
  if (fbBtn && fbBtn.previousElementSibling) {
    const p = fbBtn.previousElementSibling;
    prevLabel = ((p.innerText || '').replace(/\s+/g, ' ').trim() || '').slice(0, 18);
    prevRel = { sameParent: p.parentNode === fbBtn.parentNode, tag: p.tagName };
    const pr = p.getBoundingClientRect(), fr = fbBtn.getBoundingClientRect();
    prevGeom = { sameRow: Math.abs(pr.top - fr.top) < 4, gap: Math.round(fr.left - pr.right) };
  }
  const roles = Array.from(document.querySelectorAll('header button')).filter(
    b => (b.innerText || '').indexOf('角色') >= 0 && b.getBoundingClientRect().width > 0).length;
  return Object.assign({
    allBars: all,
    barClass: bar.className.slice(0, 90),
    cols: getComputedStyle(bar).gridTemplateColumns.split(' ').filter(s => s && s !== 'none').length,
    barRect: { w: Math.round(br.width), h: Math.round(br.height) },
    nCards: cards.length, info, overflowDoc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    overRight: info.filter(c => c.r > vw + 1).map(c => c.label),
    overLeft: info.filter(c => c.x < -1).map(c => c.label),
    tiny: info.filter(c => c.w < 40 || c.h < 40).map(c => c.label),
    fbPrev: prevRel, prevGeom, prevLabel, headerRoleBtns: roles,
    barVisible: br.width > 100 && br.height > 40,
  }, diag);
}"""

JS_STORE_LOGS = r"""() => {
  try {
    const logs = window.__YLogs ? window.__YLogs() : null;
    if (!logs) return { err: 'no __YLogs' };
    return { items: Array.from(logs).slice(-80).map(x => String((x && (x.text ?? x.msg ?? x.content)) ?? x)) };
  } catch (e) { return { err: String(e) }; }
}"""


def main():
    t0 = time.time()
    print("== t_fb100 全栈临时环境实测 ==", flush=True)

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
        print("  [pre][FATAL] %s 已存在（上次运行泄漏），拒绝覆盖，请先人工处理" % JSONL, flush=True)
        return 2

    kill_port(API_PORT)
    kill_port(WEB_PORT)

    j_created = False
    if not os.path.isdir(JUNCTION):
        subprocess.run(["cmd", "/c", "mklink", "/J", JUNCTION, JUNCTION_SRC], capture_output=True, text=True, encoding="utf-8", errors="replace")
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
        "JWT_SECRET": "fb100tmp_" + hashlib.md5(GM_PASS.encode()).hexdigest()[:16],
    })
    srv = subprocess.Popen([NODE, "--experimental-strip-types", s_path], cwd=WORK,
                           env=env, stdout=srv_log, stderr=srv_log,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    har = subprocess.Popen([NODE, os.path.join(HERE, "harness.js"),
                            "--port=%d" % WEB_PORT, "--api-port=%d" % API_PORT,
                            "--root=%s" % ROOT, "--bundle=index-v100-20261020.js"],
                           cwd=ROOT, stdout=har_log, stderr=har_log,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    print("  [pre] server pid=%s harness pid=%s api=%d web=%d" % (srv.pid, har.pid, API_PORT, WEB_PORT), flush=True)

    FB_CONTENT = "自动化测试反馈：请忽略本条（fb100 e2e %d）" % int(time.time())
    FB_CONTACT = "fb100@test.local"

    try:
        if not wait_http(API + "/api/market/items?page=1&limit=1", what="api"):
            print(open(os.path.join(WORK, "server.log"), encoding="utf-8", errors="replace").read()[-3000:], flush=True)
            return 2
        if not wait_http(WEB, what="web"):
            print(open(os.path.join(WORK, "harness.log"), encoding="utf-8", errors="replace").read()[-2000:], flush=True)
            return 2

        reg = (-1, "")
        for i in range(3):
            reg = http("POST", API + "/api/auth/register", body={"username": USER, "password": PASS})
            if reg[0] in (200, 201):
                break
            time.sleep(2)
        print("  [pre] register %s -> %s %s" % (USER, reg[0], reg[1][:120]), flush=True)
        if reg[0] not in (200, 201):
            print("  [pre][FATAL] 注册失败", flush=True)
            return 2
        reg2 = (-1, "")
        for i in range(3):
            reg2 = http("POST", API + "/api/auth/register", body={"username": USER2, "password": PASS})
            if reg2[0] in (200, 201):
                break
            time.sleep(2)
        print("  [pre] register %s -> %s %s" % (USER2, reg2[0], reg2[1][:120]), flush=True)
        if reg2[0] not in (200, 201):
            print("  [pre][FATAL] 第二账号注册失败", flush=True)
            return 2

        # ---------- PH-1 进入游戏 ----------
        from playwright.sync_api import sync_playwright
        net_fb = []          # (method, status, url) — /api/feedback 全量
        page_errors = []     # 真实 JS 异常

        bundle_text = open(b_path, encoding="utf-8").read()
        HOOK = ("\n;try{window.__Be=Be;"
                "window.__YLogs=function(){return Be.getState().logs};"
                "window.__fbhook=1;}catch(e){}"
                "setInterval(function(){try{window.__Be=Be;"
                "window.__YLogs=function(){return Be.getState().logs};}catch(e){}},500);\n")
        # §20.4：init 脚本每文档自动重挂；记录页面卸载生命周期到 localStorage（headless 是否真发 pagehide 的证据）
        LC_INIT = ("(()=>{try{const rec=e=>{try{const k='yl_lc_log';"
                   "const a=JSON.parse(localStorage.getItem(k)||'[]');"
                   "a.push({e:e.type,t:Date.now(),v:document.visibilityState});"
                   "localStorage.setItem(k,JSON.stringify(a.slice(-12)))}catch(_){}};"
                   "addEventListener('pagehide',rec);addEventListener('beforeunload',rec);"
                   "document.addEventListener('visibilitychange',rec)}catch(e){}})();")

        def on_response(r):
            u = r.request.url
            if "/api/feedback" in u:
                net_fb.append((r.request.method, r.status, u))

        def wire(page):
            page.add_init_script(LC_INIT)
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.on("response", on_response)
            page.route(re.compile(r".*/assets/.*\.js.*"),
                       lambda route: route.fulfill(
                           status=200, content_type="application/javascript; charset=utf-8",
                           headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
                           body=bundle_text + HOOK))

        def stamp_leave_synthetic(page):
            """headless 不发 pagehide/beforeunload（首轮实测 sess 恒无 left）。
            合成派发同一事件 → 产品自己的 StampLeave 监听器真实执行（打点离开时刻）。"""
            page.evaluate("() => { try { window.dispatchEvent(new Event('pagehide')); } catch (e) {} }")

        # ★ CDP 焦点仿真已撤（第 7/8 轮实测：开着它 A9 历练事件 65s 颗粒无收，2/2 复现；
        #   headless 新模式原生 document.visibilityState=='visible'，无需仿真）。

        def snap_logs(page):
            j = page.evaluate(JS_STORE_LOGS)
            return j.get("items") or []

        def body_text(page):
            return page.evaluate("() => document.body ? document.body.innerText : ''")

        def auto_title(page):
            """★ 精确匹配开关小钮的 title（恰为 开启/关闭自动打坐）。
            打坐主按钮的大 tooltip 内文含「自动打坐」四字，indexOf 匹配会命中它（首轮实测踩到）。"""
            return page.evaluate("""() => {
              const b = Array.from(document.querySelectorAll('button[title]'))
                .find(x => { const t = x.getAttribute('title')||'';
                             return x.offsetParent !== null && (t === '开启自动打坐' || t === '关闭自动打坐'); });
              return b ? b.getAttribute('title') : null;
            }""")

        def in_game(page, user=USER, pw_=PASS):
            """分层进入流程（fresh/登录页/法门/道号/天赋/开始），复用 t_r255_local 实测逻辑。"""
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
                        page.evaluate(JS_CLICK_TXT, "已有道号")   # 注册模式 → 切登录模式
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
                        page.locator('input[placeholder*="道号"]').first.fill(DAOH, timeout=4000)
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

        def dismiss_overlay(page):
            """首访版本弹窗等覆盖层：尽力关闭（可能无文字关闭钮，不阻塞主流程）。"""
            for _ in range(3):
                t = body_text(page)
                if "当前为最新版本" not in t and "更新日志" not in t:
                    return
                r = (page.evaluate(JS_CLICK_TXT, "关闭") or page.evaluate(JS_CLICK_TXT, "确定")
                     or page.evaluate(JS_CLICK_TXT, "我知道了"))
                if not r:
                    page.keyboard.press("Escape")
                page.wait_for_timeout(800)
                print("  [nav] dismiss overlay -> %r" % r, flush=True)

        def toggle_auto(page, on):
            """点打坐卡右上角小开关（title 驱动，t_r256_live 实测形态）。
            ★ 方向：开关 OFF 时 title=「开启自动打坐」→ 点它=开；ON 时 title=「关闭自动打坐」→ 点它=关。
              （首轮实测把方向点反了 ⇒ 开关从未打开，A8 全簇连锁失败。）"""
            want_click = "开启自动打坐" if on else "关闭自动打坐"
            expect_after = "关闭自动打坐" if on else "开启自动打坐"
            for _ in range(3):
                page.evaluate("""(want) => {
                  const b = Array.from(document.querySelectorAll('button[title]'))
                    .find(x => x.offsetParent !== null && (x.getAttribute('title')||'') === want);
                  if (b) b.click();
                }""", want_click)
                page.wait_for_timeout(700)
                cur = auto_title(page)
                if cur == expect_after:
                    return True
            return False

        def close_any_modal(page):
            for _ in range(4):
                before = body_text(page)
                r = (page.evaluate(JS_CLICK_TXT, "关闭") or page.evaluate(JS_CLICK_TXT, "×")
                     or page.evaluate(JS_CLICK_TXT, "✕"))
                if not r:
                    page.keyboard.press("Escape")
                    # 通用弹窗（bundle @254058）：遮罩 [role=dialog] onClick=onClose → 点遮罩即关
                    page.evaluate("""() => {
                      const d = document.querySelector('[role="dialog"]');
                      if (d) d.click();
                    }""")
                page.wait_for_timeout(700)
                if body_text(page) == before:
                    return False
            return True

        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                profile, headless=True, viewport={"width": 1440, "height": 900},
                args=["--no-proxy-server"])
            # ---------- PH-1a A1@390：独立页 + 独立账号（USER2），先独占跑完再关页 ----------
            # ★ 服务端有「单写者会话」守卫（YLSync/__ylBlocked：此账号已在其他设备打开 → 旧页只读）。
            #   同一账号开两页会把主页挤成 blocked（第 7 轮实测：A9 颗粒无收、会话写入被拦、打坐产出迟滞）。
            #   ⇒ 390 页用第二账号，且先于主页独占完成，两页在时间上不并存。
            print("\n== A1 底部操作栏 @390（独立页·独立账号） ==", flush=True)
            page_x = ctx.new_page()
            page_x.set_viewport_size({"width": 390, "height": 844})
            wire(page_x)
            page_x.goto(WEB, wait_until="domcontentloaded", timeout=60000)
            page_x.wait_for_timeout(6000)
            if not in_game(page_x):
                chk("A1@390 独立页进入游戏（%s）" % USER, False, body_text(page_x)[:200])
            else:
                page_x.wait_for_timeout(2500)
                dismiss_overlay(page_x)
                page_x.wait_for_timeout(500)
                j = page_x.evaluate(JS_BAR, 390)
                print("  @390: %s" % json.dumps(j, ensure_ascii=False)[:800], flush=True)
                tag, vw = "A1@390", 390
                chk(tag + " .ylbar6 容器在位且可见", j.get("barVisible") is True,
                    "barRect=%s innerW=%s mq768=%s styleHook=%s" % (
                        j.get("barRect"), j.get("innerW"), j.get("mq768"), j.get("styleHook")))
                chk(tag + " 6 张卡全部渲染", j.get("nCards") == 6,
                    "n=%s labels=%s" % (j.get("nCards"), [c["label"] for c in j.get("info", [])]))
                chk(tag + " 无左右越界（逐卡矩形，§20.5 判据）", not j.get("overRight") and not j.get("overLeft"),
                    "overR=%s overL=%s" % (j.get("overRight"), j.get("overLeft")))
                chk(tag + " 无过小卡（宽高≥40）", not j.get("tiny"), j.get("tiny"))
                chk("A1@390 文档无横向溢出（scrollWidth 判据）", (j.get("overflowDoc") or 0) <= 2,
                    "overflow=%spx" % j.get("overflowDoc"))
                fp = j.get("fbPrev")
                chk(tag + " 反馈卡 previousElementSibling 存在且同父（=宗门卡）",
                    bool(fp) and fp.get("sameParent") is True
                    and "宗门" in (j.get("prevLabel") or ""),
                    "prev=%s(%s) rel=%s" % (j.get("prevLabel"), j.get("prevTag"),
                                            json.dumps(fp, ensure_ascii=False)))
                chk(tag + " 反馈卡与前卡紧邻（同行 + 间距 0~40px）",
                    bool(j.get("prevGeom")) and j["prevGeom"].get("sameRow") is True
                    and 0 <= (j["prevGeom"].get("gap") if j["prevGeom"].get("gap") is not None else 999) <= 40,
                    "prev=%s geom=%s" % (j.get("prevLabel"), j.get("prevGeom")))
            page_x.close()
            time.sleep(1)

            # ---------- PH-1b 主页 @1440（账号 USER），此后全程独占 ----------
            pg = ctx.new_page()
            pg.set_viewport_size({"width": 1440, "height": 900})
            wire(pg)
            pg.goto(WEB, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(6000)
            if not in_game(pg):
                print(body_text(pg)[:1500], flush=True)
                print("  [FATAL] 未能进入游戏", flush=True)
                ctx.close()
                return 1
            print("  [nav] 已进入游戏（%.0fs）" % (time.time() - t0), flush=True)
            pg.wait_for_timeout(2500)
            dismiss_overlay(pg)
            pg.wait_for_timeout(500)

            # ---------- A1 @1440（主页原生视口） ----------
            print("\n== A1 底部操作栏 @1440（主页原生视口） ==", flush=True)
            j = pg.evaluate(JS_BAR, 1440)
            print("  @1440: %s" % json.dumps(j, ensure_ascii=False)[:800], flush=True)
            tag, vw = "A1@1440", 1440
            chk(tag + " .ylbar6 容器在位且可见", j.get("barVisible") is True,
                "barRect=%s innerW=%s mq768=%s styleHook=%s" % (
                    j.get("barRect"), j.get("innerW"), j.get("mq768"), j.get("styleHook")))
            chk(tag + " 6 张卡全部渲染", j.get("nCards") == 6,
                "n=%s labels=%s" % (j.get("nCards"), [c["label"] for c in j.get("info", [])]))
            chk(tag + " 无左右越界（逐卡矩形，§20.5 判据）", not j.get("overRight") and not j.get("overLeft"),
                "overR=%s overL=%s" % (j.get("overRight"), j.get("overLeft")))
            chk(tag + " 无过小卡（宽高≥40）", not j.get("tiny"), j.get("tiny"))
            chk("A1@1440 6 列布局生效（ylbar6 media 规则 + 注入 style 在位）",
                j.get("cols") == 6 and j.get("styleHook") is True,
                "cols=%s styleHook=%s" % (j.get("cols"), j.get("styleHook")))
            chk("A1@1440 顶栏「角色」按钮仍在（本特性不碰）", (j.get("headerRoleBtns") or 0) >= 1,
                "roles=%s" % j.get("headerRoleBtns"))
            fp = j.get("fbPrev")
            chk(tag + " 反馈卡 previousElementSibling 存在且同父（=宗门卡）",
                bool(fp) and fp.get("sameParent") is True
                and "宗门" in (j.get("prevLabel") or ""),
                "prev=%s(%s) rel=%s" % (j.get("prevLabel"), j.get("prevTag"),
                                        json.dumps(fp, ensure_ascii=False)))
            chk(tag + " 反馈卡与前卡紧邻（同行 + 间距 0~40px）",
                bool(j.get("prevGeom")) and j["prevGeom"].get("sameRow") is True
                and 0 <= (j["prevGeom"].get("gap") if j["prevGeom"].get("gap") is not None else 999) <= 40,
                "prev=%s geom=%s" % (j.get("prevLabel"), j.get("prevGeom")))
            print("  [note] ask 字面「previousElementSibling=紧邻角色左侧」：实测底栏 6 卡 = 打坐/历练/秘境/炼丹·炼器/宗门/反馈，"
                  "「角色」只在顶栏 j4 行（bundle @905332），底栏无此卡 ⇒ 反馈卡前邻=宗门卡，已如实断言（见 prevLabel 实测值）", flush=True)

            pg.wait_for_timeout(600)

            # ---------- PH-4 A2 反馈模态 + 客户端拦截 ----------
            print("\n== A2 反馈模态 + 空内容/超长拦截 ==", flush=True)
            n0 = len([x for x in net_fb if x[0] == "POST"])
            opened = pg.evaluate("""() => {
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              const b = Array.from(document.querySelectorAll('button')).find(
                x => vis(x) && (x.innerText||'').indexOf('反馈') >= 0 && (x.className||'').indexOf('relative') >= 0);
              if (b) { b.click(); return true; } return false;
            }""")
            pg.wait_for_timeout(700)
            box = pg.evaluate("""() => ({
              mask: !!document.querySelector('.ylfb-mask'),
              title: (document.querySelector('.ylfb-title') || {}).textContent || null,
              taMax: (document.querySelector('.ylfb-ta') || {}).maxLength,
              btn: (document.querySelector('.ylfb-btn') || {}).textContent || null
            })""")
            print("  modal:", json.dumps(box, ensure_ascii=False), flush=True)
            chk("A2 点「反馈」卡开模态", bool(opened) and box.get("mask") is True)
            chk("A2 模态标题=「bug 与需求反馈」", box.get("title") == "bug 与需求反馈", box.get("title"))
            chk("A2 textarea maxLength=2000（UI 超长硬拦截）", box.get("taMax") == 2000, box.get("taMax"))

            pg.evaluate("() => { const b = document.querySelector('.ylfb-btn'); if (b) b.click(); }")
            pg.wait_for_timeout(700)
            info1 = pg.evaluate("() => (document.querySelector('.ylfb-info') || {}).textContent || ''")
            n1 = len([x for x in net_fb if x[0] == "POST"])
            print("  empty submit info=%r newPosts=%d" % (info1, n1 - n0), flush=True)
            chk("A2 空内容被客户端拦截（提示 + 零请求）",
                info1 == "请填写反馈内容" and n1 == n0, "info=%r dPOST=%d" % (info1, n1 - n0))

            over = pg.evaluate("""() => new Promise(res => {
              window.YLFB_SEND('bug', 'x'.repeat(2001), '', r => res(r));
            })""")
            n2 = len([x for x in net_fb if x[0] == "POST"])
            print("  overlong:", json.dumps(over, ensure_ascii=False), flush=True)
            chk("A2 超长内容被客户端拦截（零请求）",
                bool(over) and over.get("ok") is False and over.get("status") == -1
                and "内容太长" in (over.get("msg") or "") and n2 == n1,
                json.dumps(over, ensure_ascii=False) + " dPOST=%d" % (n2 - n1))

            # ---------- PH-5 A3 合法提交 + 冷却 ----------
            print("\n== A3 合法提交 + 60s 冷却 ==", flush=True)
            pg.evaluate("""(v) => { const ta = document.querySelector('.ylfb-ta'); if (ta) ta.value = v; }""", FB_CONTENT)
            pg.evaluate("""(v) => { const i = document.querySelector('.ylfb-in'); if (i) i.value = v; }""", FB_CONTACT)
            pg.evaluate("() => { const b = document.querySelector('.ylfb-btn'); if (b) b.click(); }")
            toast = False
            for _ in range(16):
                pg.wait_for_timeout(250)
                if "已收到，感谢反馈" in body_text(pg):
                    toast = True
                    break
            pg.wait_for_timeout(600)
            mask_gone = pg.evaluate("() => !document.querySelector('.ylfb-mask')")
            posts = [x for x in net_fb if x[0] == "POST"]
            print("  posts=%s toast=%s maskGone=%s" % (posts, toast, mask_gone), flush=True)
            chk("A3 网络面板 POST /api/feedback 恰 1 次且 200",
                len(posts) == 1 and posts[0][1] == 200, json.dumps(posts))
            chk("A3 toast「已收到，感谢反馈」出现", toast)
            chk("A3 提交成功后模态自动关闭", mask_gone is True)

            cool = pg.evaluate("""() => new Promise(res => {
              window.YLFB_SEND('bug', '二连发测试内容（应被冷却拦截）', '', r => res(r));
            })""")
            posts2 = [x for x in net_fb if x[0] == "POST"]
            print("  cooldown:", json.dumps(cool, ensure_ascii=False), "posts=%d" % len(posts2), flush=True)
            chk("A3 60s 内二连发被客户端冷却拦截（status=-1 + 零新请求）",
                bool(cool) and cool.get("ok") is False and cool.get("status") == -1
                and "提交太频繁" in (cool.get("msg") or "") and len(posts2) == 1,
                json.dumps(cool, ensure_ascii=False))

            # ---------- PH-6 A6 版本链 ----------
            print("\n== A6 版本：徽标 / 设置页 / 更新日志 ==", flush=True)
            badge = pg.evaluate("""() => {
              /* 取第一个「可见」的徽标按钮（可能存在多布局分支的隐藏实例） */
              const b = Array.from(document.querySelectorAll('header button[title]'))
                .find(x => (x.getAttribute('title')||'').indexOf('更新日志') >= 0
                           && x.getBoundingClientRect().width > 0);
              const any = Array.from(document.querySelectorAll('header button[title]'))
                .find(x => (x.getAttribute('title')||'').indexOf('更新日志') >= 0);
              return { vis: b ? { text: (b.innerText||'').trim() } : null,
                       hiddenOne: any ? (any.innerText||'').trim() : null,
                       nBadges: document.querySelectorAll('header button[title*="更新日志"]').length };
            }""")
            print("  badge:", badge, flush=True)
            chk("A6 顶栏徽标显示 v1.0", bool(badge) and bool(badge.get("vis"))
                and badge["vis"].get("text") == "v1.0", json.dumps(badge, ensure_ascii=False))

            st_btn = pg.evaluate("""() => {
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              const norm = s => (s||'').replace(/\\s+/g,'');
              const bs = Array.from(document.querySelectorAll('button')).filter(vis);
              const b = bs.find(x => norm(x.innerText) === '设置' || x.getAttribute('title') === '设置');
              if (b) { b.click(); return norm(b.innerText) || b.getAttribute('title'); }
              return null;
            }""")
            pg.wait_for_timeout(900)
            pg.evaluate("""() => {
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              const tab = Array.from(document.querySelectorAll('button,div,span')).find(
                x => vis(x) && (x.innerText||'').trim() === '关于');
              if (tab) tab.click();
              return !!tab;
            }""")
            pg.wait_for_timeout(800)
            set_txt = body_text(pg)
            m = re.search(r"游戏版本\s*\n?\s*(v[\d.]+)", set_txt)
            ev = ""
            if not m and "游戏版本" in set_txt:
                i = set_txt.find("游戏版本")
                ev = set_txt[i:i + 60]
            print("  settings open=%r 版本行=%s" % (st_btn, m.group(1) if m else None), flush=True)
            chk("A6 设置页「游戏版本 v1.0」", bool(m) and m.group(1) == "v1.0",
                m.group(1) if m else ("未匹配到 v1.0；上下文=%r" % ev))
            close_any_modal(pg)

            pg.evaluate("""() => {
              const b = Array.from(document.querySelectorAll('header button[title]'))
                .find(x => (x.getAttribute('title')||'').indexOf('更新日志') >= 0);
              if (b) b.click();
            }""")
            pg.wait_for_timeout(1800)
            chg = pg.evaluate(r"""() => {
              const t = document.body.innerText || '';
              const green = Array.from(document.querySelectorAll('[class*="text-green-400"]'))
                .map(x => (x.innerText||'').trim()).find(x => x.indexOf('当前为最新版本') >= 0);
              /* 弹窗展示的是解析后的版本名（如 v1.0），不含字面「[1.0]」；
                 绿条「当前为最新版本」只在「解析出的最新版本 === 当前版本 1.0」时渲染，
                 即绿条本身就是 [1.0] 解析+比对成功的产物（bundle @1851021） */
              return { verSeen: /(v)?1\.0(\.0)?/.test(t), hasLatest: t.indexOf('当前为最新版本') >= 0,
                       green: green || null,
                       tail: t.slice(Math.max(0, t.indexOf('更新日志') - 60), t.indexOf('更新日志') + 260) };
            }""")
            print("  changelog:", json.dumps(chg, ensure_ascii=False)[:500], flush=True)
            chk("A6 更新日志弹窗解析出版本 1.0（v1.0 字样在窗）",
                chg.get("verSeen") is True, (chg.get("tail") or "")[:200])
            chk("A6 绿条「当前为最新版本」（text-green-400，=解析结果与当前版本比对成功）",
                chg.get("hasLatest") is True and bool(chg.get("green")), chg.get("green"))
            close_any_modal(pg)

            # ---------- PH-8 A9 R-254 日志拆分（先于 A7：历练需角色空闲态，A7 的打坐残留会影响它） ----------
            close_any_modal(pg)   # ★ 更新日志等弹窗未真关时，历练 handler 会被 modal 门禁拦下（复测#1 第 11 轮实测 65s 零事件）
            adv = None
            adv_started = False
            for attempt in range(3):
                adv = pg.evaluate("""() => {
                  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
                  const b = Array.from(document.querySelectorAll('button')).find(
                    x => vis(x) && (x.innerText||'').startsWith('历练'));
                  if (b) { const dis = b.disabled; b.click(); return { text: (b.innerText||'').trim().slice(0,20), disabled: dis }; }
                  return null;
                }""")
                pg.wait_for_timeout(3000)
                stt_adv = pg.evaluate("""() => {
                  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
                  const b = Array.from(document.querySelectorAll('button')).find(
                    x => vis(x) && (x.innerText||'').startsWith('历练'));
                  if (!b) return { found: false };
                  return { found: true, disabled: !!b.disabled, label: (b.innerText||'').trim().slice(0,20) };
                }""")
                # ★ 本作历练点击后秒回结算+进入冷却（复测#2 实测：attempt2 disabled=true 即冷却铁证，
                #   「历练中…」标签不常驻）⇒ 生效判据 = 按钮转 disabled 或标签含 历练中
                started = bool(stt_adv.get("found")) and (stt_adv.get("disabled") is True or "历练中" in (stt_adv.get("label") or ""))
                if started:
                    adv_started = True
                    break
                print("  [retry] 历练第 %d 次点击未进入历练中（click=%s）→ 关弹窗重试" % (attempt + 1, json.dumps(adv, ensure_ascii=False)), flush=True)
                close_any_modal(pg)
            print("  历练 click=%s started=%r，等结算…" % (json.dumps(adv, ensure_ascii=False), adv_started), flush=True)
            chk("A9 历练点击生效（按钮转 disabled/历练中 = 秒回结算+冷却）", adv_started, json.dumps(adv, ensure_ascii=False))
            got = None
            for i in range(50):
                pg.wait_for_timeout(1000)
                if "历练收获" in "\n".join(snap_logs(pg)):
                    got = i + 1
                    break
                if i == 24:  # 25s 未回 → 再点一次（停止历练）
                    pg.evaluate("""() => {
                      const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
                      const b = Array.from(document.querySelectorAll('button')).find(
                        x => vis(x) && (x.innerText||'').indexOf('历练中') >= 0);
                      if (b) b.click();
                    }""")
            if got is None:
                for i in range(15):
                    pg.wait_for_timeout(1000)
                    if "历练收获" in "\n".join(snap_logs(pg)):
                        got = i + 1
                        break
            pg.evaluate("""() => {
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              const b = Array.from(document.querySelectorAll('button')).find(
                x => vis(x) && (x.innerText||'').indexOf('历练中') >= 0);
              if (b) b.click();
            }""")
            pg.wait_for_timeout(1500)
            items = snap_logs(pg)
            age_lines = [x for x in items if "年龄 +" in x and "危险度" in x]
            gain_lines = [x for x in items if "历练收获" in x]
            mixed = [x for x in items if "年龄 +" in x and "历练收获" in x]
            print("  logs=%d 年龄行=%s 收获行=%s 混排=%s" % (
                len(items), age_lines[:2], gain_lines[:1], mixed[:2]), flush=True)
            chk("A9 触发历练结算（出现「历练收获」行）", bool(gain_lines),
                (gain_lines[:1] or ("logs=%d 全量=%s" % (len(items), items[:3]))))
            chk("A9 出现独立「年龄 +…（危险度…）」行", bool(age_lines), age_lines[:1])
            chk("A9 「年龄/危险度」与「历练收获」不在同一条日志（store.logs 逐条判）",
                bool(gain_lines) and bool(age_lines) and not mixed, "mixed=%s" % mixed[:1])
            dom_t = body_text(pg)
            chk("A9 DOM 日志面板同样可见两类行",
                ("年龄 +" in dom_t and "危险度" in dom_t and "历练收获" in dom_t),
                "dom age=%s gain=%s" % ("年龄 +" in dom_t, "历练收获" in dom_t))

            # ---------- PH-7 A7 非回归：打坐（exp 观测法：点击后 10s 窗口内修为必须增长） ----------
            print("\n== A7 非回归：打坐按钮 ==", flush=True)
            # ★ A9 历练刚结束 → 打坐按钮带历练冷却 disabled；轮询等冷却归零（首轮实测在此点了禁用钮）
            waited = 0
            while waited < 90:
                dis = pg.evaluate("""() => {
                  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
                  const b = Array.from(document.querySelectorAll('button')).find(
                    x => vis(x) && (x.innerText||'').replace(/\\s+/g,'').startsWith('打坐'));
                  return b ? !!b.disabled : null;
                }""")
                if dis is False:
                    break
                pg.wait_for_timeout(3000)
                waited += 3
            print("  等打坐冷却归零：%ds（disabled 现=%s）" % (waited, dis), flush=True)
            clicked = pg.evaluate("""() => {
              const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
              const b = Array.from(document.querySelectorAll('button')).find(
                x => vis(x) && (x.innerText||'').replace(/\\s+/g,'').startsWith('打坐'));
              if (b) { const dis = b.disabled; b.click(); return { text: (b.innerText||'').trim().slice(0,20), disabled: dis }; }
              return null;
            }""")
            exps = []
            for _ in range(30):   # 实测：手动打坐首笔产出 ~21-24s 才落账（tick 间隔长），20s 仍不够
                pg.wait_for_timeout(1000)
                exps.append(pg.evaluate("() => { try { const p = window.__Be.getState().player; return p ? p.exp : null; } catch (e) { return null; } }"))
            print("  打坐 click=%s exp 序列=%s" % (json.dumps(clicked, ensure_ascii=False), exps), flush=True)
            chk("A7 打坐按钮可点（按钮在位未禁用）", bool(clicked) and clicked.get("disabled") is False,
                json.dumps(clicked, ensure_ascii=False))
            # 注：手动打坐的产出在「停止」时批量入账（会话内 player.exp 平坦，多轮实测一致）
            #   ⇒ 生效判据 = 停止后修为净增（见下方停止段）
            # 停止打坐（再点一次）：产出在此刻批量入账；最多 3 轮直到 exp 平台化，确保不把打坐态带进 A8
            exp_before_stop = exps[-1] if exps else None
            for _ in range(3):
                pg.evaluate("""() => {
                  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
                  const b = Array.from(document.querySelectorAll('button')).find(
                    x => vis(x) && (x.innerText||'').replace(/\\s+/g,'').startsWith('打坐'));
                  if (b) b.click();
                }""")
                pg.wait_for_timeout(4500)
                e1 = pg.evaluate("() => { try { return window.__Be.getState().player.exp; } catch (e) { return null; } }")
                pg.wait_for_timeout(3000)
                e2 = pg.evaluate("() => { try { return window.__Be.getState().player.exp; } catch (e) { return null; } }")
                print("  停止打坐后 exp %s -> %s" % (e1, e2), flush=True)
                if isinstance(e1, (int, float)) and isinstance(e2, (int, float)) and e2 == e1:
                    break
            chk("A7 打坐生效（停止后修为净增=产出入账）",
                isinstance(exp_before_stop, (int, float)) and isinstance(e2, (int, float)) and e2 > exp_before_stop,
                "点击后 exp=%s → 停止后 exp=%s" % (exp_before_stop, e2))

            # ---------- PH-11 A8 R-255 三分行为 ----------
            print("\n== A8 R-255 三分行为 ==", flush=True)
            pg.evaluate("() => { try { localStorage.removeItem('yl_auto_switch'); localStorage.removeItem('yl_auto_sess'); localStorage.removeItem('yl_lc_log'); } catch (e) {} }")
            b0 = toggle_auto(pg, True)
            sw0 = pg.evaluate("() => localStorage.getItem('yl_auto_switch')")
            print("  开自动打坐 on=%s switch=%s" % (b0, sw0), flush=True)
            chk("A8·开 自动打坐开关打开且落 localStorage(m=1)", b0 is True and '"m":1' in (sw0 or ""), sw0)
            pg.wait_for_timeout(4500)  # 会话 ≥3s，reload 才有回放日志
            # ★ 会话记录（yl_auto_sess）由自动循环首个 tick 写入，4.5s 可能还没落 —— 轮询等它出现再 stamp
            sess_wait = 0
            while sess_wait < 30:
                if pg.evaluate("() => !!localStorage.getItem('yl_auto_sess')"):
                    break
                pg.wait_for_timeout(1000)
                sess_wait += 1
            # headless 不发页面卸载事件 ⇒ 合成 pagehide 让产品自己的 StampLeave 监听器打点离开时刻
            stamp_leave_synthetic(pg)
            lc1 = pg.evaluate("() => localStorage.getItem('yl_lc_log')")
            sess_pre = pg.evaluate("() => localStorage.getItem('yl_auto_sess')")
            visinfo = pg.evaluate("() => ({ v: document.visibilityState, b: window.__ylBlocked === undefined ? 'undef' : !!window.__ylBlocked })")
            print("  reload 前（等 sess %ds）：lc=%s sess=%s vis=%s" % (sess_wait, lc1, sess_pre, json.dumps(visinfo)), flush=True)

            # b1 reload → 开关仍在 + 会话续接 + 回放日志恰 1 条（不重复发奖）
            pg.reload(wait_until="domcontentloaded")
            pg.wait_for_timeout(6000)
            if not in_game(pg):
                chk("A8·reload 后回到游戏", False, "未回到游戏")
            pg.wait_for_timeout(2500)  # YLR256Boot = player-ready + 1200ms
            sw1 = pg.evaluate("() => localStorage.getItem('yl_auto_switch')")
            ttl1 = auto_title(pg)
            items1 = snap_logs(pg) or []
            replay1 = sum(x.count("上次打坐中页面已刷新") for x in items1)
            close1 = sum(x.count("上次打坐因关闭页面已自动停止") for x in items1)
            sess1 = pg.evaluate("() => localStorage.getItem('yl_auto_sess')")
            exp_a = pg.evaluate("() => { try { const p = window.__Be.getState().player; return p ? p.exp : null; } catch (e) { return null; } }")
            pg.wait_for_timeout(3200)
            exp_b = pg.evaluate("() => { try { const p = window.__Be.getState().player; return p ? p.exp : null; } catch (e) { return null; } }")
            print("  reload: switch=%s title=%s replay=%d close=%d sess=%s exp %s->%s" % (
                sw1, ttl1, replay1, close1, sess1, exp_a, exp_b), flush=True)
            chk("A8·reload 开关仍在（localStorage m=1）", '"m":1' in (sw1 or ""), sw1)
            chk("A8·reload 开关 UI 仍为开（关闭自动打坐）", ttl1 == "关闭自动打坐", ttl1)
            chk("A8·reload 回放结算日志恰 1 条（不重复发奖）", replay1 == 1,
                "count=%d（回放日志=%s）" % (replay1, [x for x in items1 if "上次打坐" in x][:2]))
            chk("A8·reload 无「关闭页面」结算串（三分路径不串）", close1 == 0, "count=%d" % close1)
            # 会话续接的产物级证据 = 回放恰 1 条（会话被消费补账）+ 循环继续产出（下一条 exp 增长）。
            #   yl_auto_sess 的 boot 尾重建多轮实测时序不稳（None/{"m":..} 两态），只观察不断言：
            print("  [note] reload 后 yl_auto_sess=%r（会话续接以 replay=1 + exp 增长为准）" % sess1, flush=True)
            # 微诊断：boot/medOn 置位 + sess 每秒采样（定性 reload 后会话记录未重建的窗口）
            trace = []
            for _ in range(10):
                trace.append(pg.evaluate("""() => ({
                  sess: localStorage.getItem('yl_auto_sess'),
                  boot: window.__ylR256Boot === undefined ? 'undef' : window.__ylR256Boot,
                  medOn: window.__ylR256MedOn === undefined ? 'undef' : window.__ylR256MedOn
                })"""))
                pg.wait_for_timeout(1000)
            print("  [diag] reload 后 10s 采样：%s" % json.dumps(trace, ensure_ascii=False)[:800], flush=True)
            chk("A8·reload 自动打坐仍在产出（exp 增长）",
                isinstance(exp_a, (int, float)) and isinstance(exp_b, (int, float)) and exp_b > exp_a,
                "%s -> %s" % (exp_a, exp_b))

            # b3 页面开着 ≥60s 开关绝不自己停（7 采样 × 10s）
            print("  b3 观察 70s（7 采样 × 10s）…", flush=True)
            stable = True
            for i in range(7):
                pg.wait_for_timeout(10000)
                stt = pg.evaluate("""() => ({
                  ttl: (Array.from(document.querySelectorAll('button[title]'))
                        .find(x => { const t = x.getAttribute('title')||'';
                                     return x.offsetParent !== null && (t === '开启自动打坐' || t === '关闭自动打坐'); })
                        || { getAttribute: () => null }).getAttribute('title'),
                  sw: localStorage.getItem('yl_auto_switch'),
                  sess: localStorage.getItem('yl_auto_sess'),
                  v: document.visibilityState,
                  b: window.__ylBlocked === undefined ? 'undef' : !!window.__ylBlocked
                })""")
                print("    t+%ds title=%s switch=%s sess=%s vis=%s/%s" % (
                    (i + 1) * 10, stt.get("ttl"), stt.get("sw"), stt.get("sess"), stt.get("v"), stt.get("b")), flush=True)
                if stt.get("ttl") != "关闭自动打坐" or '"m":1' not in (stt.get("sw") or ""):
                    stable = False
            chk("A8·开着 ≥60s 开关绝不自己停（7 采样，10s 间隔）", stable)

            # b2 真关页面（整浏览器进程退出）→ 同 profile 全新打开（navigation type=navigate）
            # ★ 日志持久化在存档里，重开后历史日志整批回来 ⇒ 判定用「与关页前基线的差值」
            items_pre_close = snap_logs(pg) or []
            replay_pre = sum(x.count("上次打坐中页面已刷新") for x in items_pre_close)
            close_pre = sum(x.count("上次打坐因关闭页面已自动停止") for x in items_pre_close)
            stamp_leave_synthetic(pg)   # headless 不发 pagehide → 合成事件驱动产品 StampLeave
            sess_pre2 = pg.evaluate("() => localStorage.getItem('yl_auto_sess')")
            print("  close 前：sess=%s" % sess_pre2, flush=True)
            ctx.close()
            pg = None
            time.sleep(2)
            ctx = pw.chromium.launch_persistent_context(
                profile, headless=True, viewport={"width": 1440, "height": 900},
                args=["--no-proxy-server"])
            pg = ctx.new_page()
            wire(pg)
            pg.goto(WEB, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(6000)
            nav_type = pg.evaluate("() => { try { const n = performance.getEntriesByType('navigation'); return n && n.length ? n[0].type : null; } catch (e) { return null; } }")
            if not in_game(pg):
                chk("A8·重开回到游戏", False, "未回到游戏")
            pg.wait_for_timeout(2500)
            sw2 = pg.evaluate("() => localStorage.getItem('yl_auto_switch')")
            ttl2 = auto_title(pg)
            items2 = snap_logs(pg) or []
            replay2 = sum(x.count("上次打坐中页面已刷新") for x in items2)
            close2 = sum(x.count("上次打坐因关闭页面已自动停止") for x in items2)
            sess2 = pg.evaluate("() => localStorage.getItem('yl_auto_sess')")
            print("  基线（关页前）：replay=%d close=%d" % (replay_pre, close_pre), flush=True)
            print("  reopen: nav=%s switch=%s title=%s replay=%d close=%d sess=%s" % (
                nav_type, sw2, ttl2, replay2, close2, sess2), flush=True)
            chk("A8·重开 navigation type=navigate", nav_type == "navigate", nav_type)
            chk("A8·重开 自动开关=关（switch 归零 m=0/a=0）",
                sw2 is not None and '"m":0' in sw2 and '"a":0' in sw2, sw2)
            chk("A8·重开 开关 UI=关（开启自动打坐）", ttl2 == "开启自动打坐", ttl2)
            chk("A8·重开 补一条「因关闭页面已自动停止」结算日志（恰新增 1 条）", close2 == close_pre + 1,
                "close %d -> %d（新增日志=%s）" % (close_pre, close2,
                                                  [x for x in items2 if "因关闭页面已自动停止" in x][:1]))
            chk("A8·重开 无新增「页面已刷新」回放串（三分路径不串）", replay2 == replay_pre,
                "replay %d -> %d" % (replay_pre, replay2))
            chk("A8·重开 会话记录已清（yl_auto_sess 不存在）", sess2 is None, sess2)

            # ---------- NOTE 对照探针：纯「关页→重开」路径（不经 reload），验证 close-settle 机制本身 ----------
            # b2 的结论：reload 消费会话后 yl_auto_sess 未被重建（boot=1/medOn=1/未blocked/visible 仍 None）
            #   ⇒ 该状态下真关页无会话可结算。此探针验证不经 reload 的纯关页路径能否正常补日志（给主线的画像）。
            print("\n== [NOTE] 对照：纯关页路径（toggle→close→reopen，无 reload） ==", flush=True)
            pg.evaluate("() => { try { localStorage.removeItem('yl_auto_switch'); localStorage.removeItem('yl_auto_sess'); } catch (e) {} }")
            if toggle_auto(pg, True):
                sess_w2 = 0
                while sess_w2 < 30:
                    if pg.evaluate("() => !!localStorage.getItem('yl_auto_sess')"):
                        break
                    pg.wait_for_timeout(1000)
                    sess_w2 += 1
                items_pc = snap_logs(pg) or []
                replay_pc = sum(x.count("上次打坐中页面已刷新") for x in items_pc)
                close_pc = sum(x.count("上次打坐因关闭页面已自动停止") for x in items_pc)
                pg.wait_for_timeout(4500)
                stamp_leave_synthetic(pg)
                sess_pc = pg.evaluate("() => localStorage.getItem('yl_auto_sess')")
                print("  [NOTE] close 前 sess=%s（等 %ds）" % (sess_pc, sess_w2), flush=True)
                ctx.close()
                time.sleep(2)
                ctx = pw.chromium.launch_persistent_context(
                    profile, headless=True, viewport={"width": 1440, "height": 900},
                    args=["--no-proxy-server"])
                pg = ctx.new_page()
                wire(pg)
                pg.goto(WEB, wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(6000)
                if in_game(pg):
                    pg.wait_for_timeout(2500)
                    items_p2 = snap_logs(pg) or []
                    replay_p2 = sum(x.count("上次打坐中页面已刷新") for x in items_p2)
                    close_p2 = sum(x.count("上次打坐因关闭页面已自动停止") for x in items_p2)
                    print("  [NOTE] 纯关页路径：replay %d -> %d，close %d -> %d（新增=%s）" % (
                        replay_pc, replay_p2, close_pc, close_p2,
                        [x for x in items_p2 if "因关闭页面已自动停止" in x][:1]), flush=True)
                    print("  [NOTE] 判读：close 新增 1 = close-settle 机制本身健康，缺陷定位于「reload 消费会话后未重建会话记录」", flush=True)
                else:
                    print("  [NOTE] 对照重开未回到游戏（跳过）", flush=True)
            else:
                print("  [NOTE] 对照探针 toggle 失败（跳过）", flush=True)

            # ---------- PH-7b pageerror 终判 ----------
            print("\n== A7 终判：pageerror 分账 ==", flush=True)
            print("  pageerror(%d): %s" % (len(page_errors), page_errors[:5]), flush=True)
            print("  /api/feedback 网络: %s" % net_fb, flush=True)
            chk("A7 全程无 pageerror（真实 JS 异常，与 HTTP 4xx 预期噪声分开判）",
                len(page_errors) == 0, "; ".join(page_errors[:3]))

        # ---------- PH-9 A4 服务端侧 ----------
        print("\n== A4 临时库 feedback 表 + jsonl ==", flush=True)
        copy_db = os.path.join(WORK, "copy.sqlite")
        shutil.copyfile(db_path, copy_db)
        for ext in ("-wal", "-shm"):
            if os.path.exists(db_path + ext):
                shutil.copyfile(db_path + ext, copy_db + ext)
        con = sqlite3.connect(copy_db)
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute("SELECT * FROM feedback ORDER BY id").fetchall()]
        con.close()
        print("  feedback rows=%d %s" % (len(rows), json.dumps(rows, ensure_ascii=False)[:600]), flush=True)
        row = rows[0] if rows else {}
        need = ["id", "user_id", "username", "kind", "content", "contact", "version", "realm", "ua", "status", "created_at"]
        chk("A4 feedback 表恰 1 行（冷却拦截/超长拦截均未入库）", len(rows) == 1, "rows=%d" % len(rows))
        chk("A4 行字段齐全（11 字段全在）", all(k in row for k in need), [k for k in need if k not in row])
        chk("A4 行内容=本次提交（kind/content/contact/version=1.0）",
            row.get("kind") == "bug" and row.get("content") == FB_CONTENT and row.get("contact") == FB_CONTACT
            and row.get("version") == "1.0",
            "kind=%s ver=%s status=%s" % (row.get("kind"), row.get("version"), row.get("status")))
        chk("A4 user_id/realm/ua/created_at 非空",
            bool(row.get("user_id")) and bool(row.get("realm")) and bool(row.get("ua")) and bool(row.get("created_at")),
            "user=%s realm=%s ua=%s… created=%s" % (row.get("user_id"), row.get("realm"), (row.get("ua") or "")[:30], row.get("created_at")))

        chk("A4 feedback_inbox.jsonl 存在（__dirname=dev/srv/）", os.path.exists(JSONL), JSONL)
        if os.path.exists(JSONL):
            lines = [l for l in open(JSONL, encoding="utf-8").read().splitlines() if l.strip()]
            ok_json, last = False, None
            try:
                last = json.loads(lines[-1])
                ok_json = True
            except Exception as e:
                print("  jsonl parse err:", e, flush=True)
            print("  jsonl lines=%d last=%s" % (len(lines), json.dumps(last, ensure_ascii=False)[:300]), flush=True)
            chk("A4 jsonl 恰 1 行且 JSON 可解析", len(lines) == 1 and ok_json, "lines=%d" % len(lines))
            chk("A4 jsonl 行与库行对应（id/user/kind/content/version）",
                bool(last) and last.get("content") == FB_CONTENT and last.get("user") == USER
                and last.get("kind") == "bug" and last.get("id") == row.get("id") and last.get("version") == "1.0",
                json.dumps(last, ensure_ascii=False)[:200] if last else "none")

        # ---------- PH-10 A5 GM 链路 ----------
        print("\n== A5 GM 链路 ==", flush=True)
        st, body = http("POST", API + "/api/gm/login", body={"password": GM_PASS})
        gm_tok = ""
        try:
            gm_tok = (json.loads(body) or {}).get("token") or ""
        except Exception:
            pass
        print("  gm/login -> %s tok=%s…" % (st, gm_tok[:20]), flush=True)
        chk("A5 GM 登录（临时口令，经子进程环境变量注入未落盘）", st == 200 and bool(gm_tok), "http=%s" % st)
        st, body = http("GET", API + "/api/gm/feedback?page=1&limit=20", token=gm_tok)
        try:
            j = json.loads(body)
            items = j.get("items") if isinstance(j, dict) else j
        except Exception:
            items = None
        mine = [x for x in (items or []) if x.get("content") == FB_CONTENT]
        print("  gm/feedback -> %s items=%d mine=%s" % (
            st, len(items or []), json.dumps(mine, ensure_ascii=False)[:200]), flush=True)
        chk("A5 GM 列表见该行（status=open）",
            st == 200 and len(mine) == 1 and mine[0].get("status") == "open",
            json.dumps(mine[:1], ensure_ascii=False)[:200])
        fid = mine[0]["id"] if mine else None
        st, body = http("POST", API + "/api/gm/feedback/%s/status" % fid, body={"status": "resolved"}, token=gm_tok)
        print("  status=resolved -> %s %s" % (st, body[:100]), flush=True)
        chk("A5 GM 改 status=resolved 生效（{ok:true}）",
            st == 200 and body.replace(" ", "").replace('"', "'") == "{'ok':true}",
            "%s %s" % (st, body[:80]))
        st, body = http("GET", API + "/api/gm/feedback?page=1&limit=20", token=gm_tok)
        try:
            items2 = json.loads(body).get("items")
        except Exception:
            items2 = []
        mine2 = [x for x in (items2 or []) if x.get("id") == fid]
        chk("A5 复查状态已落库为 resolved", st == 200 and mine2 and mine2[0].get("status") == "resolved",
            json.dumps(mine2[:1], ensure_ascii=False)[:160])

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

    print("\n===== t_fb100 结果 =====", flush=True)
    print("  PASS = %d   FAIL = %d   (耗时 %.0fs)" % (len(PASS_LIST), len(FAIL_LIST), time.time() - t0), flush=True)
    for f in FAIL_LIST:
        print("   FAIL: %s" % f, flush=True)
    return 1 if FAIL_LIST else 0


if __name__ == "__main__":
    sys.exit(main())
