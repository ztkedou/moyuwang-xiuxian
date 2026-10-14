# -*- coding: utf-8 -*-
r"""R-253 线上端到端验收：直接在 https://moyuwang.online/myxxz/ 上验两个 bug 的修复。

与 t_r256_live.py 的区别：那条走本地 build/ + API 反代；本脚本**打线上真实站点**，
验证「玩家现在打开游戏就是修好的」。

用法: set YL_R255_USER / YL_R255_PASS，然后 python localtest/t_r256_online.py
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(HERE)
os.chdir(ROOTDIR)
sys.path.insert(0, ROOTDIR)
sys.path.insert(0, HERE)
import ylc  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

LIVE = 'https://moyuwang.online/myxxz/'
USER = os.environ.get('YL_R255_USER') or ylc.USER
PW = os.environ.get('YL_R255_PASS') or ylc.PASS
PASS, FAIL = [], []


def chk(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


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


TOGGLE_MED_ON = r"""() => {
  const b = Array.from(document.querySelectorAll('button')).find(x => x.offsetParent !== null && (x.getAttribute('title')||'').indexOf('开启自动打坐') >= 0);
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
    switchRaw: g('yl_auto_switch'),
    sessRaw: g('yl_auto_sess'),
    hasReplayLog: /上次打坐中页面已刷新|上次历练中页面已刷新/.test(t),
    ver: (t.match(/v0\.9\.\d+/) || [''])[0],
  };
}
"""


def main():
    errs = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(viewport={'width': 1440, 'height': 900})
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
        blocked = {'save': False}

        # ★ 只拦截 /save 来模拟断网时的存档失败；其余一律放行到线上
        def route_handler(route):
            u = route.request.url
            if blocked['save'] and '/api/save' in u:
                try:
                    route.abort('failed')
                except Exception:
                    pass
                return
            try:
                route.continue_()
            except Exception:
                pass

        pg.route(re.compile(r".*/yl/api/.*"), route_handler)
        pg.goto(LIVE, wait_until='domcontentloaded', timeout=60000)
        pg.wait_for_timeout(9000)

        loaded = pg.evaluate("() => Array.from(document.querySelectorAll('script[src]')).map(s => s.src)")
        print('  已加载脚本:', [x.split('/')[-1] for x in loaded])
        chk('0a 线上加载的是 v2962 包', any('index-v2962-20261011.js' in x for x in loaded), str(loaded)[:120])

        if not login(pg):
            print('  [!!] 登录失败'); br.close(); return 1
        pr0 = pg.evaluate(PROBE)
        print('  页面版本:', pr0['ver'])
        chk('0b 页面版本号为 0.9.62', pr0['ver'] == 'v0.9.62', pr0['ver'])

        print('\n=== 场景 1：断网不自锁 + 来网自愈（线上）===')
        okm = pg.evaluate(TOGGLE_MED_ON)
        pg.wait_for_timeout(2500)
        pr = pg.evaluate(PROBE)
        chk('1a 自动打坐已开启', okm and pr['medOn'], 'click=%s medOn=%s' % (okm, pr['medOn']))
        chk('1b 开关已落盘', bool(pr['switchRaw']) and json.loads(pr['switchRaw']).get('m') == 1, str(pr['switchRaw']))

        blocked['save'] = True
        pg.evaluate("() => { try { window.dispatchEvent(new Event('offline')); } catch(e){} }")
        pg.wait_for_timeout(28000)
        pr2 = pg.evaluate(PROBE)
        print('  提示条:', pr2['banner'], repr(pr2['bannerText'])[:70], ' 模态:', pr2['hasModalOK'], ' medOn:', pr2['medOn'])
        chk('1c 断网时挂非阻塞提示条', pr2['banner'], pr2['bannerText'][:60])
        chk('1d 断网时**无**模态弹窗', not pr2['hasModalOK'])
        chk('1e 断网期间自动打坐**仍在运行**', pr2['medOn'])

        blocked['save'] = False
        pg.evaluate("() => { try { window.dispatchEvent(new Event('online')); } catch(e){} }")
        pg.wait_for_timeout(5000)
        pr3 = pg.evaluate(PROBE)
        chk('1f 来网后提示条自动消失', not pr3['banner'])
        chk('1g 来网后自动打坐仍开着', pr3['medOn'])

        print('\n=== 场景 2：刷新续跑 + 补发结算（线上）===')
        pg.evaluate("() => { try { window.dispatchEvent(new Event('pagehide')); } catch(e){} }")
        pg.wait_for_timeout(800)
        pr4 = pg.evaluate(PROBE)
        sess = json.loads(pr4['sessRaw'] or '{}')
        chk('2a pagehide 已打「离开时刻」', bool(sess.get('left')), str(pr4['sessRaw'])[:80])

        pg.reload(wait_until='domcontentloaded', timeout=60000)
        pg.wait_for_timeout(9000)
        login(pg)
        pg.wait_for_timeout(7000)
        pr5 = pg.evaluate(PROBE)
        print('  刷新后 medOn:', pr5['medOn'], ' 补发日志:', pr5['hasReplayLog'], ' sess:', pr5['sessRaw'])
        chk('2b 刷新后自动打坐**自动恢复**', pr5['medOn'])
        chk('2c 刷新后补发了结算说明日志', pr5['hasReplayLog'])
        chk('2d 补发后会话 key 已清', not pr5['sessRaw'], str(pr5['sessRaw']))

        chk('3 无 JS 运行时错误', len(errs) == 0, ('; '.join(errs[:2]) if errs else ''))
        pg.screenshot(path=os.path.join(HERE, '_r256_online.png'))
        br.close()
    print('\n===== R-253 线上端到端 =====')
    print('  PASS = %d   FAIL = %d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('   FAIL: %s' % f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
