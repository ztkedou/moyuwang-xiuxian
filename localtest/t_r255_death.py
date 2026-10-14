# -*- coding: utf-8 -*-
"""R-255 寿终流程验证：把服务端 age 推到死线之上，再用浏览器重新读档，看是否弹「转世重修」。

★ 为什么走浏览器：寿终判定在客户端 `$w` 的 useEffect 里（`age >= YlxwLifeDeathLine(t)`），
  必须让真实页面重新加载服务端存档才会触发 ⇒ 这是唯一能证明「到点只能重开」的端到端路径。

用法: set YL_R255_USER / YL_R255_PASS，然后 python localtest/t_r255_death.py
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
LIVE = "https://moyuwang.online"
USER = os.environ.get('YL_R255_USER') or ylc.USER
PW = os.environ.get('YL_R255_PASS') or ylc.PASS
PASS, FAIL = [], []


def chk(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def api(path, token=None, data=None, method=None, extra=None):
    u = LIVE + '/yl/api' + path
    hdr = {'Content-Type': 'application/json'}
    if token:
        hdr['Authorization'] = 'Bearer ' + token
    if extra:
        hdr.update(extra)
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.urlopen(urllib.request.Request(u, data=body, headers=hdr, method=method), timeout=30)
    return json.loads(r.read().decode('utf-8'))


def rev(token):
    """读当前 gm_revision（S1 v26c 防倒滚：带档上传必须声明基于的修订号）。"""
    u = LIVE + '/yl/api/save?revision=1'
    r = urllib.request.urlopen(urllib.request.Request(
        u, headers={'Authorization': 'Bearer ' + token}), timeout=30)
    return int(json.loads(r.read().decode('utf-8')).get('gm_revision') or 0)


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


def main():
    print('=== 0. 服务端当前状态 ===')
    tok = api('/auth/login', data={'username': USER, 'password': PW})['token']
    sav = api('/save', token=tok)
    p0 = sav['player']
    dl0 = float(p0['maxLifespan'])
    print('  age=%.4f  maxLifespan=%.4f  lifeRatio=%s' % (float(p0['age']), dl0, p0.get('lifeRatio')))
    chk('0a 存档含 age', 'age' in p0)
    chk('0b 存档含 lifeRatio', 'lifeRatio' in p0)
    chk('0c 存档无旧 lifespan 键', 'lifespan' not in p0)
    chk('0d maxLifespan == lifeRatio × 100', abs(dl0 - float(p0['lifeRatio']) * 100) < 1e-6,
        'dl=%.6f ratio*100=%.6f' % (dl0, float(p0['lifeRatio']) * 100))

    # ---- 越线写回 ----
    print('\n=== 1. 把 age 推到死线之上（走客户端同一条 /save 推档通道）===')
    pushed = dict(sav)
    pushed['player'] = dict(p0)
    pushed['player']['age'] = dl0 + 0.5
    pushed['timestamp'] = int(__import__('time').time() * 1000)
    pushed['lastActiveTime'] = pushed['timestamp']
    try:
        r0 = rev(tok)
        print('  当前 gm_revision = %d' % r0)
        api('/save', token=tok, data=pushed, method='POST',
            extra={'X-YL-Base-Revision': str(r0)})
        got = api('/save', token=tok)['player']
        print('  写回后 age=%.4f（死线 %.4f）' % (float(got['age']), float(got['maxLifespan'])))
        chk('1a 越线 age 已被服务端接受', float(got['age']) > float(got['maxLifespan']),
            'age=%.4f dl=%.4f' % (float(got['age']), float(got['maxLifespan'])))
    except Exception as e:
        print('  写回失败:', type(e).__name__, str(e)[:200])
        chk('1a 越线 age 已被服务端接受', False, str(e)[:80])

    # ---- 浏览器重载 → 触发寿终 ----
    print('\n=== 2. 浏览器重新读档 → 寿终判定 ===')
    p = os.path.join(ROOT, 'index.html')
    s = io.open(p, encoding='utf-8').read().replace('/myxxz/assets/', './assets/').replace('/myxxz/', './')
    io.open(p, 'w', encoding='utf-8', newline='').write(s)
    srv, base = serve()
    errs = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(viewport={'width': 1440, 'height': 900})
        pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
        pg.route(re.compile(r".*/yl/api/.*"),
                 lambda r: r.fulfill(response=r.fetch(url=r.request.url.replace(base, LIVE))))
        pg.goto(base + '/index.html', wait_until='domcontentloaded', timeout=60000)
        pg.wait_for_timeout(8000)
        if not login(pg):
            print('  [!!] 登录失败'); br.close(); srv.shutdown(); return 1

        vis = {'hasEnd': False, 'hasRebirth': False, 'txt': ''}
        for i in range(16):
            vis = pg.evaluate("""() => {
              const t = document.body.innerText || '';
              return {hasEnd: t.indexOf('寿元已尽') >= 0 || t.indexOf('寿终正寝') >= 0,
                      hasRebirth: t.indexOf('转世重修') >= 0,
                      hasOldRebirth: t.indexOf('涅槃重生') >= 0,
                      txt: t.slice(0, 300)};
            }""")
            if vis['hasEnd'] or vis['hasRebirth']:
                print('  第 %d 次轮询命中' % i)
                break
            pg.wait_for_timeout(2500)
        print('  探测:', json.dumps({k: v for k, v in vis.items() if k != 'txt'}, ensure_ascii=False))
        print('  正文前 200:', vis['txt'][:200].replace('\n', ' | '))
        chk('2a 出现寿终文案（寿元已尽 / 寿终正寝）', vis['hasEnd'])
        chk('2b 出现「转世重修」按钮', vis['hasRebirth'])
        chk('2c 不再出现旧的「涅槃重生」', not vis['hasOldRebirth'])
        pg.screenshot(path=os.path.join(HERE, '_r255_death.png'))
        print('  截图: localtest/_r255_death.png')
        chk('2d 无 JS 运行时错误', len(errs) == 0, ('; '.join(errs[:2]) if errs else ''))
        br.close()
    srv.shutdown()
    print('\n===== R-255 寿终验证 =====')
    print('  PASS = %d   FAIL = %d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('   FAIL: %s' % f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
