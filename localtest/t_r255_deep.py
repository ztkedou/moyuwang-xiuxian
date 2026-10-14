# -*- coding: utf-8 -*-
"""R-255 深度联调：用**服务端权威存档**（GET /yl/api/save）验证年龄制。

★ 为什么不用 localStorage：本项目 §10 明确「服务端是唯一真相，客户端只推不拉」，
  本地 `xiuxian-game-save` 已不再是进度缓存 ⇒ 必须问服务端要。

用法: set YL_R255_USER / YL_R255_PASS，然后 python localtest/t_r255_deep.py
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


def api(path, token=None, data=None, method=None):
    u = LIVE + '/yl/api' + path
    hdr = {'Content-Type': 'application/json'}
    if token:
        hdr['Authorization'] = 'Bearer ' + token
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(u, data=body, headers=hdr, method=method)
    r = urllib.request.urlopen(req, timeout=30)
    return json.loads(r.read().decode('utf-8'))


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
            pg.evaluate(ylc.CLICK_JS, '踏入修仙界'); pg.wait_for_timeout(7000); continue
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
    # 服务端存档（登录 → 建号保证存在）
    tok = api('/auth/login', data={'username': USER, 'password': PW})['token']
    sav = api('/save', token=tok)
    p0 = sav['player']
    print('=== 0. 服务端权威存档（进入游戏前）===')
    print('  keys 含 age/lifeRatio/lifeBonus/lifespan?',
          {k: (k in p0) for k in ('age', 'lifeRatio', 'lifeBonus', 'lifespan', 'maxLifespan')})
    print('  %s' % json.dumps({k: p0.get(k) for k in
                               ('name', 'realm', 'realmLevel', 'age', 'lifespan',
                                'maxLifespan', 'lifeRatio', 'lifeBonus')}, ensure_ascii=False))

    p = os.path.join(ROOT, 'index.html')
    s = io.open(p, encoding='utf-8').read().replace('/myxxz/assets/', './assets/').replace('/myxxz/', './')
    io.open(p, 'w', encoding='utf-8').write(s)
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

        # ---- 1. 面板 ----
        print('\n=== 1. 面板渲染 ===')
        panel = pg.evaluate("""() => {
          const t = document.body.innerText || '';
          const m = t.match(/年龄\\s*(\\d+)\\s*岁\\s*·\\s*寿元\\s*(\\d+)\\s*-\\s*(\\d+)\\s*岁/);
          return {hasOld: t.indexOf('寿命 (年)') >= 0, m: m ? [+m[1], +m[2], +m[3]] : null,
                  line: (t.match(/年龄[^\\n]{0,32}/) || [''])[0]};
        }""")
        print('  ', json.dumps(panel, ensure_ascii=False))
        chk('1a 面板无旧「寿命 (年)」', not panel['hasOld'])
        chk('1b 面板可解析「年龄 N 岁 · 寿元 lo-hi 岁」', panel['m'] is not None, panel['line'])
        if panel['m']:
            age, lo, hi = panel['m']
            chk('1c 区间下限 ≈ 上限 × 0.9', abs(lo - round(hi * 0.9)) <= 1, 'lo=%d hi=%d' % (lo, hi))
            chk('1d 炼气期区间为 90-100', (lo, hi) == (90, 100), 'lo=%d hi=%d' % (lo, hi))

        # ---- 2. 服务端存档字段 ----
        print('\n=== 2. 服务端存档字段（年龄制）===')
        p1 = api('/save', token=tok)['player']
        print('  %s' % json.dumps({k: p1.get(k) for k in
                                   ('age', 'lifespan', 'maxLifespan', 'lifeRatio', 'lifeBonus')},
                                  ensure_ascii=False))
        chk('2a 有 age 字段', 'age' in p1)
        chk('2b 有 lifeRatio 字段', 'lifeRatio' in p1)
        chk('2c 有 lifeBonus 字段', 'lifeBonus' in p1)
        chk('2d 旧 lifespan 字段已消失', 'lifespan' not in p1,
            'lifespan=%s' % p1.get('lifespan'))
        if 'age' in p1:
            chk('2e age 为数值且 ≥ 0', isinstance(p1['age'], (int, float)) and p1['age'] >= 0,
                'age=%s' % p1['age'])
        if 'lifeRatio' in p1:
            r = float(p1['lifeRatio'])
            chk('2f lifeRatio ∈ [0.9, 1]', 0.9 <= r <= 1.0, 'ratio=%s' % r)
            dl = float(p1['maxLifespan'])
            chk('2g maxLifespan == lifeRatio × 100（炼气1层）',
                abs(dl - r * 100) < 1e-6, 'dl=%s  ratio*100=%s' % (dl, r * 100))
            chk('2h 死线落在展示区间 [90,100]', 90 <= dl <= 100, 'dl=%s' % dl)

        # ---- 3. 打坐 → 年龄增长 ----
        print('\n=== 3. 打坐 → 年龄增长 ===')
        a0 = float(p1.get('age', 0))
        pg.evaluate("""() => {
          const vis = el => { const r = el.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
          const b = Array.from(document.querySelectorAll('button')).find(x => vis(x) && (x.innerText||'').replace(/\\s+/g,'').startsWith('打坐'));
          if (b) b.click();
        }""")
        pg.wait_for_timeout(25000)
        pg.evaluate("""() => {
          const vis = el => { const r = el.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
          const b = Array.from(document.querySelectorAll('button')).find(x => vis(x) && (x.innerText||'').replace(/\\s+/g,'').indexOf('停止') >= 0);
          if (b) b.click();
        }""")
        pg.wait_for_timeout(18000)
        p2 = api('/save', token=tok)['player']
        a1 = float(p2.get('age', 0))
        d = a1 - a0
        print('  age: %.6f -> %.6f  (delta %.6f)' % (a0, a1, d))
        chk('3a 打坐后 age 严格增加', d > 0, 'delta=%.6f' % d)
        chk('3b 增量量级合理（25s 打坐 < 1 岁）', 0 < d < 1.0, 'delta=%.6f' % d)
        # 0.0002/跳 × ~2s/跳 × 25s ≈ 0.0025
        chk('3c 增量贴近设计速率（0.0002/跳 ⇒ 约 0.001~0.02）', 0.0005 < d < 0.05, 'delta=%.6f' % d)

        # ---- 4. 寿终：把 age 推到死线之上，再让页面重新读档 ----
        print('\n=== 4. 寿终 → 转世重修 ===')
        p3 = api('/save', token=tok)['player']
        dl = float(p3['maxLifespan'])
        forced = dict(p3)
        forced['age'] = dl + 0.5
        # 走客户端同一条 PUSH 通道（/save POST）写回，保证服务端接受
        try:
            api('/save', token=tok, data={'player': forced, 'logs': sav.get('logs', [])},
                method='POST')
            print('  已把 age 推到 %.4f（死线 %.4f）' % (forced['age'], dl))
            wrote = True
        except Exception as e:
            print('  写回失败:', type(e).__name__, str(e)[:160])
            wrote = False
        chk('4a 越线 age 已写回服务端', wrote)
        if wrote:
            pg.reload(wait_until='domcontentloaded', timeout=60000)
            pg.wait_for_timeout(14000)
            vis = {'hasEnd': False, 'hasRebirth': False, 'txt': ''}
            for _ in range(12):
                vis = pg.evaluate("""() => {
                  const t = document.body.innerText || '';
                  return {hasEnd: t.indexOf('寿元已尽') >= 0 || t.indexOf('寿终正寝') >= 0,
                          hasRebirth: t.indexOf('转世重修') >= 0, txt: t.slice(0, 260)};
                }""")
                if vis['hasEnd'] or vis['hasRebirth']:
                    break
                pg.wait_for_timeout(2500)
            print('  弹窗探测:', json.dumps(vis, ensure_ascii=False)[:280])
            chk('4b 出现寿终文案', vis['hasEnd'], vis['txt'][:110].replace('\n', ' | '))
            chk('4c 出现「转世重修」按钮', vis['hasRebirth'])
            pg.screenshot(path=os.path.join(HERE, '_r255_death.png'))

        chk('5 无 JS 运行时错误', len(errs) == 0, ('; '.join(errs[:3]) if errs else ''))
        br.close()
    srv.shutdown()
    print('\n===== R-255 深度联调 =====')
    print('  PASS = %d   FAIL = %d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('   FAIL: %s' % f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
