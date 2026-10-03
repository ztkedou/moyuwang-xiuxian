# -*- coding: utf-8 -*-
r"""localtest/_verify_r112_jade.py — R-112 生产验收复跑（灵玉阁「我的灵玉」不再恒为 0）

台账 R-112（yl / 活动中心）：灵玉产出的产出，打坐、历练也会获得，打坐几率最低，历练比打坐略高。
0.9.15 代码修复：活动中心→灵玉阁面板「我的灵玉」原读 d.balance（不存在）⇒ 恒显 0；
0.9.15 改为 `d.jadeBalance ?? d.balance`。本脚本用 Playwright 真机复跑一次生产验收。

三方一致性断言：
  ① 面板「我的灵玉：N」显示值  ==  ② 接口 /activity/shop 返回的 jadeBalance（页面内 fetch 捕获真值）
  且 ① != 0；若给了 --expect，还要 == expect。

用法：
  python localtest/_verify_r112_jade.py \
      [--url=http://127.0.0.1:3205/myxxz/] [--user=ylt_mid] [--pass=Test123456] \
      [--expect=<灵玉值>] [--headed]
  --expect 缺省读环境变量 YL_EXPECT_JADE；未提供则只打印不判等。

退出码：0 全过；非 0 = FAIL 条数。

依据（bundle build/assets/index-v2921-20261004.js, md5 d15800ffb6575fa3325ab5760f2c3f82, 2,299,359 B）：
  ※ 0.9.21 批客户端零功能改动（仅版本号），故本脚本的选择器/文案依据与 0.9.20 完全一致。
  ※ 页面路由 `**/myxxz/assets/*.js` 与包名无关 ⇒ 换版本不影响本脚本。
  · `function YlxwOpen(k){...s.setModal("xianwuTab",k||"mail");s.setModal("isXianwuOpen",!0);}`
      ⇒ 打开活动中心 = YlxwOpen("events")；顶栏/抽屉各有 1 个文案「活动中心」的 <button>。
  · `function YlxwTActCenter()` 里 tabs = [[overview,总览],[rank,仙途冲榜],[checkin,每日签到],
      [shop,灵玉阁],[boss,万妖巢穴]]，每个 tab 是 <button>，onClick setTab("shop") ⇒ 点「灵玉阁」。
  · `function YlxwTActShop(p)`：YlxwActUseApi("/activity/shop") ⇒
      `bal = d && typeof d.jadeBalance === "number" ? d.jadeBalance : ...d.balance... : null`
      面板渲染 `"我的灵玉：" + YlxwNum(bal)`，YlxwNum(r)=Number(r)||0。⇒ 面板文案「我的灵玉：<数>」。
  · `function Xc(t,r)` 用 `fetch(ln+r, {headers:{Authorization:"Bearer "+token,...}})`，
      追加 `?token=...`。⇒ 页面内 fetch 拦截器可捕获 /activity/shop 的真实响应。
"""
import io
import os
import re
import sys
import json
import time
import hashlib
import argparse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHOTS = os.path.join(HERE, "shots")
TS = datetime.now().strftime("%Y%m%d_%H%M%S")

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright  # noqa: E402


# ------------------------------------------------------------------ 结果收集
class Report(object):
    def __init__(self, name):
        self.name = name
        self.rows = []

    def check(self, cid, desc, ok, detail=""):
        self.rows.append({"id": cid, "desc": desc, "ok": bool(ok), "detail": str(detail)[:600]})
        print("[%s] %-6s %-46s %s" % ("PASS" if ok else "FAIL", cid, desc[:46], str(detail)[:180]))
        return bool(ok)

    def note(self, cid, desc, detail=""):
        self.rows.append({"id": cid, "desc": desc, "ok": None, "detail": str(detail)[:600]})
        print("[NOTE] %-6s %-46s %s" % (cid, desc[:46], str(detail)[:180]))

    def summary(self):
        p = sum(1 for r in self.rows if r["ok"] is True)
        f = sum(1 for r in self.rows if r["ok"] is False)
        n = sum(1 for r in self.rows if r["ok"] is None)
        return p, f, n


# ------------------------------------------------------------------ JS 片段
# ① 页面加载前挂 fetch 拦截器：捕获 /activity/shop 的请求(url+headers)与响应 json
FETCH_HOOK = r"""
(function () {
  window.__r112 = { shop: null, reqs: [] };
  var of = window.fetch;
  window.fetch = function (input, init) {
    try {
      var url = (typeof input === 'string') ? input : ((input && input.url) || '');
      if (url.indexOf('/activity/shop') >= 0) {
        var hdrs = {};
        try {
          var h = (init && init.headers) || (input && input.headers) || {};
          if (h && typeof h.forEach === 'function') { h.forEach(function (v, k) { hdrs[k] = v; }); }
          else { for (var k in h) hdrs[k] = h[k]; }
        } catch (e) {}
        window.__r112.reqs.push({ url: url, headers: hdrs });
        var p = of.apply(this, arguments);
        return p.then(function (resp) {
          try {
            resp.clone().json().then(function (j) {
              window.__r112.shop = { url: url, status: resp.status, json: j };
            }).catch(function () {});
          } catch (e) {}
          return resp;
        });
      }
    } catch (e) {}
    return of.apply(this, arguments);
  };
})();
"""

# ② 追加到 bundle 末尾：把模块作用域里的 YlxwOpen / Et 暴露到 window（自愈重挂）
BUNDLE_HOOK = (
    "\n;try{window.__YlxwOpen=YlxwOpen;}catch(e){window.__hookOpen='err:'+((e&&e.message)||e);}\n"
    ";try{window.__YlxwEt=Et;}catch(e){}\n"
    ";setInterval(function(){try{window.__YlxwOpen=window.__YlxwOpen||YlxwOpen;"
    "window.__YlxwEt=window.__YlxwEt||Et;}catch(e){}},500);\n"
)

CLICK_JS = r"""
(txt) => {
  const bs = Array.from(document.querySelectorAll('button, [role=button], a'));
  for (const b of bs) {
    const t = (b.innerText || '').replace(/\s+/g, '');
    if (t && t.indexOf(txt) >= 0 && b.offsetParent !== null) { b.click(); return t.slice(0, 40); }
  }
  return null;
}
"""

BODY_TXT = "() => document.body.innerText"


def close_intro(pg, timeout_s=10):
    """关闭登录后的引导/遮罩（点击任意位置关闭 / 知道了 / 关闭 / 开始修仙）。"""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if pg.evaluate("() => document.body.innerText.indexOf('点击任意位置关闭') >= 0"):
            pg.evaluate(r"""() => {
              const els = Array.from(document.querySelectorAll('div'));
              for (const el of els) {
                if ((el.innerText || '').indexOf('点击任意位置关闭') >= 0 &&
                    getComputedStyle(el).position === 'fixed') { el.click(); return; }
              }
              document.body.click();
            }""")
            pg.wait_for_timeout(700)
            return True
        if pg.evaluate("() => !!document.querySelector('header')") and \
           pg.evaluate("() => document.body.innerText.indexOf('点击任意位置关闭') < 0"):
            return True
        pg.evaluate(CLICK_JS, "知道了") or pg.evaluate(CLICK_JS, "关闭")
        pg.wait_for_timeout(500)
    return False


def ui_login(pg, username, password):
    """登录沙盒账号（参考 _e2e_t8_ui.py:ui_login）。返回 True=已进主界面。"""
    pg.wait_for_timeout(2000)
    for _ in range(25):
        st = pg.evaluate(r"""() => ({hdr: !!document.querySelector('header'),
          pwd: !!document.querySelector('input[type="password"]')})""")
        if st["hdr"]:
            return True
        if st["pwd"]:
            # 确保处于「登录」模式（注册模式提交按钮为「立下长生誓」）
            if pg.evaluate("() => document.body.innerText.indexOf('已有道号') >= 0"):
                pg.evaluate(CLICK_JS, "已有道号")
                pg.wait_for_timeout(400)
            try:
                pg.locator('input[placeholder*="道号"]').first.fill(username)
                pg.locator('input[placeholder*="真言"]').first.fill(password)
            except Exception:
                pg.fill('input:not([type="password"]):not([type="checkbox"])', username)
                pg.fill('input[type="password"]', password)
            pg.evaluate(CLICK_JS, "踏入修仙界") or pg.evaluate(CLICK_JS, "登录")
            pg.wait_for_timeout(6000)
            continue
        pg.wait_for_timeout(1200)
    return False


def open_activity_center(pg, R):
    """打开活动中心：优先点「活动中心」按钮，失败兜底 window.__YlxwOpen('events')。"""
    clicked = pg.evaluate(CLICK_JS, "活动中心")
    pg.wait_for_timeout(1500)
    if clicked and "活动中心" in (pg.evaluate(BODY_TXT) or ""):
        R.note("S2", "活动中心入口", "点击按钮命中：%s" % clicked)
        return True
    # 兜底：直接调用 bundle 里暴露的切换函数（依据 YlxwOpen("events") 锚点）
    used = pg.evaluate("() => { if (window.__YlxwOpen) { window.__YlxwOpen('events'); return true; } return false; }")
    pg.wait_for_timeout(1500)
    R.note("S2", "活动中心入口", "按钮未命中→兜底 __YlxwOpen('events')=%s" % used)
    return bool(used)


def open_jade_tab(pg):
    """切到「灵玉阁」页签（tab 是 <button>）。"""
    return pg.evaluate(CLICK_JS, "灵玉阁")


def read_panel_jade(pg):
    """从面板文案抓「我的灵玉：N」。返回 int 或 None。"""
    txt = pg.evaluate(BODY_TXT) or ""
    m = re.search(r"我的灵玉[：:]\s*(\d+)", txt)
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3205/myxxz/")
    ap.add_argument("--user", default="ylt_mid")
    ap.add_argument("--pass", dest="password", default="Test123456")
    ap.add_argument("--expect", default=os.environ.get("YL_EXPECT_JADE") or None)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    expect = None
    if args.expect not in (None, ""):
        expect = int(args.expect)

    os.makedirs(SHOTS, exist_ok=True)
    R = Report("R-112 灵玉阁「我的灵玉」生产验收复跑")

    print("=== R-112 验收复跑 ===")
    print("url=%s user=%s expect=%s" % (args.url, args.user, expect))

    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=not args.headed, args=["--no-proxy-server"])
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script(FETCH_HOOK)          # fetch 拦截器（页面脚本前）
        pg = ctx.new_page()

        # 把 __YlxwOpen 注入 bundle（route 改写 assets/*.js，参考 prod087_check_A.install_route）
        def on_route(route):
            try:
                r0 = route.fetch()
                body = r0.text()
                if "__YlxwOpen=YlxwOpen" not in body:
                    body = body + BUNDLE_HOOK
                route.fulfill(status=200,
                              content_type="application/javascript; charset=utf-8",
                              headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
                              body=body)
            except Exception:
                route.continue_()
        pg.route("**/myxxz/assets/*.js", on_route)

        shot = None
        try:
            pg.goto(args.url, wait_until="domcontentloaded")
            ok_login = ui_login(pg, args.user, args.password)
            R.check("S1", "%s 登录沙盒并进入主界面" % args.user, ok_login, args.url)
            if not ok_login:
                shot = os.path.join(SHOTS, "r112_jade_fail_%s.png" % TS)
                pg.screenshot(path=shot, full_page=True)
                R.note("S1.fail", "登录失败截图", shot)
                raise SystemExit(2)

            close_intro(pg)

            ok_open = open_activity_center(pg, R)
            R.check("S2b", "活动中心面板打开（含 灵玉阁 页签）",
                    ok_open and "灵玉阁" in (pg.evaluate(BODY_TXT) or ""),
                    "body含灵玉阁=%s" % ("灵玉阁" in (pg.evaluate(BODY_TXT) or "")))

            tab_hit = open_jade_tab(pg)
            pg.wait_for_timeout(1200)
            R.check("S3", "点击「灵玉阁」页签", bool(tab_hit), "命中=%s" % tab_hit)

            # 等 fetch 拦截器抓到 /activity/shop 真值
            truth = None
            for _ in range(30):
                cap = pg.evaluate("() => window.__r112 && window.__r112.shop")
                if cap and cap.get("json"):
                    truth = cap
                    break
                pg.wait_for_timeout(500)

            panel = read_panel_jade(pg)
            R.note("S4", "面板「我的灵玉」抓取值", "panel=%s" % panel)

            # ② 接口真值：优先用拦截到的响应；再显式用页面内 fetch 复调一次
            api_jade = None
            if truth and isinstance(truth.get("json"), dict):
                j = truth["json"]
                api_jade = j.get("jadeBalance")
                if not isinstance(api_jade, (int, float)):
                    api_jade = j.get("balance") if isinstance(j.get("balance"), (int, float)) else api_jade
                R.check("S5", "接口 /activity/shop 返回 jadeBalance（拦截真值）",
                        isinstance(api_jade, (int, float)),
                        "status=%s jadeBalance=%s keys=%s" % (
                            truth.get("status"), j.get("jadeBalance"),
                            ",".join(list(j.keys())[:8])))
            else:
                R.check("S5", "接口 /activity/shop 返回 jadeBalance（拦截真值）", False,
                        "未捕获到响应：%r" % (truth,))

            # 显式页面内 fetch 复调（用捕获到的真实 url + headers）
            refetch = pg.evaluate(r"""async () => {
              try {
                var c = window.__r112 && window.__r112.shop;
                var rq = window.__r112 && window.__r112.reqs && window.__r112.reqs[0];
                if (!rq) return { err: 'no captured request' };
                var r = await fetch(rq.url, { headers: rq.headers || {} });
                var j = null; try { j = await r.json(); } catch (e) {}
                return { status: r.status, jade: j && (j.jadeBalance != null ? j.jadeBalance : j.balance), keys: j ? Object.keys(j).slice(0,8) : null };
              } catch (e) { return { err: String(e) }; }
            }""")
            R.note("S6", "页面内 fetch 复调 /activity/shop", json.dumps(refetch, ensure_ascii=False)[:200])

            # ---------- 三方一致性断言 ----------
            allok = True
            # A. 面板非空且不为 0
            a = R.check("A1", "面板显示值已抓取到且 != 0", panel is not None and panel != 0,
                        "panel=%s" % panel)
            allok = allok and a
            # B. 面板 == 接口
            if isinstance(api_jade, (int, float)):
                b = R.check("A2", "面板显示值 == 接口 jadeBalance", int(panel) == int(api_jade) if panel is not None else False,
                            "panel=%s api=%s" % (panel, api_jade))
            else:
                b = R.check("A2", "面板显示值 == 接口 jadeBalance", False, "接口值缺失")
            allok = allok and b
            # C. 复调一致（若成功）
            if refetch and not refetch.get("err") and isinstance(refetch.get("jade"), (int, float)):
                c = R.check("A3", "复调接口 jadeBalance == 拦截真值",
                            int(refetch["jade"]) == int(api_jade) if isinstance(api_jade, (int, float)) else False,
                            "refetch=%s api=%s" % (refetch.get("jade"), api_jade))
                allok = allok and c
            else:
                R.note("A3", "复调断言跳过（复调失败）", json.dumps(refetch, ensure_ascii=False)[:160])
            # D. expect
            if expect is not None:
                d = R.check("A4", "面板显示值 == --expect(%d)" % expect, panel == expect,
                            "panel=%s expect=%s" % (panel, expect))
                allok = allok and d
            else:
                R.note("A4", "未传 --expect / YL_EXPECT_JADE，仅打印不判等", "panel=%s" % panel)

            shot = os.path.join(SHOTS, ("r112_jade_ok_%s.png" if allok else "r112_jade_fail_%s.png") % TS)
            pg.screenshot(path=shot, full_page=True)
            R.note("S7", "截图", shot)

        finally:
            br.close()

    p, f, n = R.summary()
    print("\n=== R-112 结果: PASS %d / FAIL %d / NOTE %d ===" % (p, f, n))
    print("截图: %s" % shot)
    return f


if __name__ == "__main__":
    sys.exit(main())
