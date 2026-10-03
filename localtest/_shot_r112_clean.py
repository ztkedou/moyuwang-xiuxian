# -*- coding: utf-8 -*-
r"""localtest/_shot_r112_clean.py — R-112 灵玉阁**干净视觉取证**（关掉引导弹窗后再截）。

为什么单独写一个：`_verify_r112_jade.py` 的断言是 DOM 级（textContent），
「修仙法门」引导弹窗虽然盖在面板上方，但不影响断言成立；不过它会让截图看不到面板。
本脚本只负责**出图**：登录 → 关掉引导弹窗 → 开活动中心 → 切灵玉阁 → 截图。

用法：
  python localtest/_shot_r112_clean.py [--url=...] [--user=ylt_mid] [--pass=Test123456]
退出码：0 = 拿到干净截图；非 0 = 未拿到。
"""
import io
import os
import re
import sys
import time
import argparse
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "shots")
TS = datetime.now().strftime("%Y%m%d_%H%M%S")

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright  # noqa: E402

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

# 关掉任意遮罩/引导弹窗：先找右上角 × 类按钮，再点遮罩空白，最后 Esc
DISMISS_JS = r"""
() => {
  const closed = [];
  const cands = Array.from(document.querySelectorAll('button, [role=button], [aria-label]'));
  for (const b of cands) {
    const t = (b.innerText || '').trim();
    const al = (b.getAttribute && (b.getAttribute('aria-label') || '')) || '';
    const looksClose = (t && /^[×✕✖xX]+$/.test(t)) || /close|关闭|dismiss/i.test(al);
    if (looksClose && b.offsetParent !== null) { b.click(); closed.push(t || al); }
  }
  return closed;
}
"""


def dismiss_all(pg, rounds=6):
    for _ in range(rounds):
        txt = pg.evaluate(BODY_TXT) or ""
        # 「点击任意位置关闭」型遮罩
        if "点击任意位置关闭" in txt:
            pg.evaluate(r"""() => {
              const els = Array.from(document.querySelectorAll('div'));
              for (const el of els) {
                if ((el.innerText || '').indexOf('点击任意位置关闭') >= 0 &&
                    getComputedStyle(el).position === 'fixed') { el.click(); return; }
              }
              document.body.click();
            }""")
            pg.wait_for_timeout(600)
            continue
        # × 类关闭按钮
        closed = pg.evaluate(DISMISS_JS)
        if closed:
            pg.wait_for_timeout(600)
            continue
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(400)
        after = pg.evaluate(BODY_TXT) or ""
        if after == txt:
            break
    return pg.evaluate(BODY_TXT) or ""


def ui_login(pg, username, password):
    pg.wait_for_timeout(2000)
    for _ in range(25):
        st = pg.evaluate(r"""() => ({hdr: !!document.querySelector('header'),
          pwd: !!document.querySelector('input[type="password"]')})""")
        if st["hdr"]:
            return True
        if st["pwd"]:
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3205/myxxz/")
    ap.add_argument("--user", default="ylt_mid")
    ap.add_argument("--pass", dest="password", default="Test123456")
    args = ap.parse_args()

    os.makedirs(SHOTS, exist_ok=True)
    rc = 1
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True, args=["--no-proxy-server"])
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        try:
            pg.goto(args.url, wait_until="domcontentloaded")
            if not ui_login(pg, args.user, args.password):
                print("[FAIL] 登录失败")
                pg.screenshot(path=os.path.join(SHOTS, "r112_clean_login_fail_%s.png" % TS), full_page=True)
                raise SystemExit(1)
            print("[OK  ] 登录成功")
            print("[..] 关弹窗，残留文案片段 = %r" % (dismiss_all(pg)[:120],))

            pg.evaluate("() => { if (window.__YxlwOpen) window.__YxlwOpen('events'); }")
            pg.evaluate(CLICK_JS, "活动中心")
            pg.wait_for_timeout(1500)
            print("[OK  ] 活动中心：%s" % (pg.evaluate(CLICK_JS, "活动中心") or "已打开"))
            pg.evaluate(CLICK_JS, "灵玉阁")
            pg.wait_for_timeout(2000)

            txt = pg.evaluate(BODY_TXT) or ""
            m = re.search(r"我的灵玉[：:]\s*(\d+)", txt)
            print("[OK  ] 面板「我的灵玉」= %s" % (m.group(1) if m else "未找到"))
            blocked = [k for k in ("修仙法门", "点击任意位置关闭") if k in txt]
            print("[..] 仍遮挡的弹窗文案 = %r" % (blocked,))

            out = os.path.join(SHOTS, "r112_jade_panel_%s.png" % TS)
            pg.screenshot(path=out, full_page=False)
            print("[OK  ] 截图 %s" % out)
            rc = 0 if (m and not blocked) else 1
        finally:
            br.close()
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
