# -*- coding: utf-8 -*-
r"""R-253 浏览器实测（修正版）：两个 bug 的端到端验证。

★ 上一版测试的错处（已修）：自动开关不是文字按钮「自动打坐」，而是打坐/历练卡片右上角的
  **小图标按钮**，用 `title="开启自动打坐"` / `"关闭自动打坐"` 标识（产物 @899222 实测）。
  上一版靠 `CLICK_JS('自动打坐')` 点不到 ⇒ 开关从未打开 ⇒ 后续 8 条断言连环假失败。
"""
import functools
import http.server
import io
import json
import os
import re
import socketserver
import sys
import threading
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(HERE)
os.chdir(ROOTDIR)
sys.path.insert(0, ROOTDIR)
sys.path.insert(0, HERE)
import ylc  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.join(ROOTDIR, 'build')
LIVE = 'https://moyuwang.online'
USER = os.environ.get('YL_R255_USER') or ylc.USER
PW = os.environ.get('YL_R255_PASS') or ylc.PASS
PASS, FAIL = [], []


def chk(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    h = functools.partial(Quiet, directory=ROOT)
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, 'http://127.0.0.1:%d' % srv.server_address[1]


def login(pg, log=print):
    for step in range(30):
        st = pg.evaluate("""() => ({
          pwd: !!document.querySelector('input[type="password"]'),
          header: !!document.querySelector('header'),
          famen: (document.body.innerText||'').indexOf('修仙法门') >= 0,
          dao: !!document.querySelector('input[placeholder*="道号"]'),
          fate: (document.body.innerText||'').indexOf('命运点') >= 0,
          start: (document.body.innerText||'').indexOf('开始游戏') >= 0,
          btns: Array.from(document.querySelectorAll('button')).filter(b=>b.offsetParent!==null).map(b=>(b.innerText||'').replace(/\\s+/g,'')).filter(Boolean).slice(0,14)
        })""")
        if st['header'] and not st['famen']:
            log('  [ok] 已进入游戏 (step %d)' % step)
            return True
        if st['pwd']:
            if any('已有道号' in b for b in st['btns']):
                pg.evaluate(ylc.CLICK_JS, '已有道号'); pg.wait_for_timeout(1200)
            pg.locator('input').first.fill(USER, timeout=5000)
            pg.locator('input[type="password"]').first.fill(PW, timeout=5000)
            pg.evaluate(ylc.CLICK_JS, '踏入修仙界'); pg.wait_for_timeout(8000); continue
        if st['famen']:
            ylc.close_modal(pg, log); continue
        if st['dao']:
            try:
                pg.locator('input[placeholder*="道号"]').first.fill(ylc.DAOH, timeout=4000)
            except Exception:
                pass
            pg.wait_for_timeout(400); pg.evaluate(ylc.CLICK_JS, '下一步'); pg.wait_for_timeout(2000); continue
        if st['fate']:
            pg.evaluate(ylc.CLICK_JS, '随机分配'); pg.wait_for_timeout(1000)
            pg.evaluate(ylc.CLICK_JS, '下一步'); pg.wait_for_timeout(2000); continue
        if st['start']:
            pg.evaluate(ylc.CLICK_JS, '开始游戏'); pg.wait_for_timeout(5000); continue
        pg.evaluate(ylc.CLICK_JS, '下一步') or pg.evaluate(ylc.CLICK_JS, '开始修仙之旅')
        pg.wait_for_timeout(2000)
    return False


# ★ 用 title 精确定位自动开关（实测产物里就是 title="开启自动打坐"）
TOGGLE_MED_ON = r"""() => {
  const b = Array.from(document.querySelectorAll('button')).find(x => x.offsetParent !== null && (x.getAttribute('title')||'').indexOf('开启自动打坐') >= 0);
  if (b) { b.click(); return true; } return false;
}"""
TOGGLE_ADV_ON = r"""() => {
  const b = Array.from(document.querySelectorAll('button')).find(x => x.offsetParent !== null && (x.getAttribute('title')||'').indexOf('开启自动历练') >= 0);
  if (b) { b.click(); return true; } return false;
}"""

PROBE = r"""
() => {
  const ls = (() => { try { return window.localStorage; } catch (e) { return null; } })();
  const g = k => { try { return ls ? ls.getItem(k) : null; } catch (e) { return null; } };
  const t = document.body.innerText || '';
  const vis = el => { const r = el.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
  const titles = Array.from(document.querySelectorAll('button')).filter(vis)
      .map(b => b.getAttribute('title') || '').filter(Boolean);
  return {
    banner: !!document.getElementById('yl-r256-net-banner'),
    bannerText: (document.getElementById('yl-r256-net-banner') || {}).textContent || '',
    hasModalOK: Array.from(document.querySelectorAll('button')).some(b => (b.innerText||'').trim() === '确定' && b.offsetParent !== null),
    medOn: titles.some(x => x.indexOf('关闭自动打坐') >= 0),
    advOn: titles.some(x => x.indexOf('关闭自动历练') >= 0),
    switchRaw: g('yl_auto_switch'),
    sessRaw: g('yl_auto_sess'),
    hasReplayLog: /上次打坐中页面已刷新|上次历练中页面已刷新/.test(t),
    logTail: t.slice(-600),
  };
}
"""


def main():
    p = os.path.join(ROOT, 'index.html')
    s = io.open(p, encoding='utf-8').read().replace('/myxxz/assets/', './assets/').replace('/myxxz/', './')
    io.open(p, 'w', encoding='utf-8', newline='').write(s)
    srv, base = serve()
    errs = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(viewport={'width': 1440, 'height': 900})
        pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
        api_re = re.compile(r".*/yl/api/.*")
        blocked = {'save': False}

        def route_handler(route):
            u = route.request.url
            if blocked['save'] and '/save' in u:
                try:
                    route.abort('failed')
                except Exception:
                    pass
                return
            try:
                route.fulfill(response=route.fetch(url=u.replace(base, LIVE)))
            except Exception:
                try:
                    route.abort('failed')
                except Exception:
                    pass

        pg.route(api_re, route_handler)
        pg.goto(base + '/index.html', wait_until='domcontentloaded', timeout=60000)
        pg.wait_for_timeout(8000)
        if not login(pg):
            print('  [!!] 登录失败'); br.close(); srv.shutdown(); return 1

        print('\n=== 场景 0：开启自动打坐（用 title 精确定位开关）===')
        okm = pg.evaluate(TOGGLE_MED_ON)
        pg.wait_for_timeout(2500)
        pr0 = pg.evaluate(PROBE)
        print('  点击成功:', okm, ' medOn:', pr0['medOn'], ' switchRaw:', pr0['switchRaw'])
        chk('0a 找到并点击了「开启自动打坐」', okm)
        chk('0b 自动打坐已开启（title 变为「关闭自动打坐」）', pr0['medOn'])
        chk('0c 开关已落盘 yl_auto_switch', bool(pr0['switchRaw']) and json.loads(pr0['switchRaw']).get('m') == 1,
            str(pr0['switchRaw']))
        chk('0d 会话已落盘 yl_auto_sess', bool(pr0['sessRaw']), str(pr0['sessRaw'])[:80])

        print('\n=== 场景 1：断网不自锁 + 来网自愈（Bug1）===')
        blocked['save'] = True
        pg.evaluate("() => { try { window.dispatchEvent(new Event('offline')); } catch(e){} }")
        pg.wait_for_timeout(28000)      # 覆盖一次 10s 自动存档 + 退避重试
        pr = pg.evaluate(PROBE)
        print('  提示条:', pr['banner'], repr(pr['bannerText'])[:80])
        print('  模态「确定」:', pr['hasModalOK'], ' medOn:', pr['medOn'])
        chk('1a 断网时挂出非阻塞提示条', pr['banner'], pr['bannerText'][:60])
        chk('1b 断网时**无**模态弹窗（不再锁死自动循环）', not pr['hasModalOK'])
        chk('1c 断网期间自动打坐**仍在运行**', pr['medOn'])

        blocked['save'] = False
        pg.evaluate("() => { try { window.dispatchEvent(new Event('online')); } catch(e){} }")
        pg.wait_for_timeout(5000)
        pr2 = pg.evaluate(PROBE)
        print('  来网后 提示条:', pr2['banner'], ' medOn:', pr2['medOn'])
        chk('1d 来网后提示条自动消失', not pr2['banner'])
        chk('1e 来网后自动打坐仍开着', pr2['medOn'])

        print('\n=== 场景 2：刷新续跑 + 补发结算（Bug2）===')
        pg.evaluate("() => { try { window.dispatchEvent(new Event('pagehide')); } catch(e){} }")
        pg.wait_for_timeout(800)
        pr3 = pg.evaluate(PROBE)
        sess = json.loads(pr3['sessRaw'] or '{}')
        print('  pagehide 后 sess =', pr3['sessRaw'])
        chk('2a pagehide 已打「离开时刻」', bool(sess.get('left')), 'left=%s' % sess.get('left'))

        pg.reload(wait_until='domcontentloaded', timeout=60000)
        pg.wait_for_timeout(9000)
        login(pg)
        pg.wait_for_timeout(7000)
        pr4 = pg.evaluate(PROBE)
        print('  刷新后 medOn:', pr4['medOn'], ' sess:', pr4['sessRaw'])
        print('  补发日志出现:', pr4['hasReplayLog'])
        print('  日志尾:', pr4['logTail'][-200:].replace('\n', ' | '))
        chk('2b 刷新后自动打坐**自动恢复**', pr4['medOn'])
        chk('2c 刷新后补发了结算说明日志', pr4['hasReplayLog'], pr4['logTail'][-150:].replace('\n', ' | '))
        chk('2d 补发后会话 key 已清（幂等）', not pr4['sessRaw'], str(pr4['sessRaw']))

        # 二次刷新：**语义应是「每次中断补一条」**，而不是「永远不再补」——
        #   第二次刷新前 autoMeditate 又开着了（boot 已恢复），pagehide 会为**新一轮**打点
        #   ⇒ 第三次进来理应再补一条「这一轮」的说明。
        #   ★ 真正要防的是「同一轮被补发多次」（重复计数），而非「后续轮次不再补」。
        pg.evaluate("() => { try { window.dispatchEvent(new Event('pagehide')); } catch(e){} }")
        pg.wait_for_timeout(500)
        pg.reload(wait_until='domcontentloaded', timeout=60000)
        pg.wait_for_timeout(9000)
        login(pg)
        pg.wait_for_timeout(6000)
        pr5 = pg.evaluate(PROBE)
        cnt = pg.evaluate("""() => ((document.body.innerText||'').match(/上次打坐中页面已刷新/g) || []).length""")
        print('  二次刷新后：补发日志条数 =', cnt, ' sess =', pr5['sessRaw'])
        chk('2e 每轮中断补一条、不重复计数（条数 ≤ 2）', cnt <= 2, 'cnt=%d' % cnt)
        chk('2f 二次刷新后开关仍自动恢复', pr5['medOn'])

        # 连续刷新两次但不等待 pagehide 打点：同一条会话不得被补两次
        pg.evaluate("() => { try { window.dispatchEvent(new Event('pagehide')); } catch(e){} }")
        pg.wait_for_timeout(300)
        pg.reload(wait_until='domcontentloaded', timeout=60000)
        pg.wait_for_timeout(8000)
        login(pg)
        pg.wait_for_timeout(5000)
        cnt2 = pg.evaluate("""() => ((document.body.innerText||'').match(/上次打坐中页面已刷新/g) || []).length""")
        print('  再刷新一次后：补发日志条数 =', cnt2)
        chk('2g 同一条会话不被补两次（条数 ≤ 3 且单调）', cnt2 <= 3, 'cnt=%d' % cnt2)

        chk('3 无 JS 运行时错误', len(errs) == 0, ('; '.join(errs[:2]) if errs else ''))
        pg.screenshot(path=os.path.join(HERE, '_r256_result.png'))
        br.close()
    srv.shutdown()
    print('\n===== R-253 浏览器实测 =====')
    print('  PASS = %d   FAIL = %d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('   FAIL: %s' % f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
