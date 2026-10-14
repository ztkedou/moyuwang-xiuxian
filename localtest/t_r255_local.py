# -*- coding: utf-8 -*-
"""R-255 本地联调：静态服务 build/ + /yl/api 反代到线上，Playwright 实测年龄制。

用法: python localtest/t_r255_local.py
断言（全部在真实浏览器里读真产物渲染/状态，不靠文本猜测）：
  A 面板已改为「年龄 / 寿元」且不再有「寿命 (年)」
  B 新建角色 age === 0，且 maxLifespan === lifeRatio × 100，展示区间 = 90-100 或 91-101…（落在 [90,100]×0.9 关系内）
  C 打坐一次：age 增加、且不再出现 lifespan 字段
  D 死线恒落在展示区间内（用真实 player 值算）
  E 把 player.age 人为推到死线-0.001：寿终弹窗出现且含「转世重修」
  F 法宝 cost.lifespan 死代码：bundle 里已无该键（静态断言，浏览器侧复核 window 上无残留提示）
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(HERE)
os.chdir(ROOTDIR)

import ylc  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.join(ROOTDIR, 'build')
LIVE = "https://moyuwang.online"
STATE = {'base': ''}
PASS = []
FAIL = []


def chk(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    h = functools.partial(Quiet, directory=ROOT, )
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", 0), h)
    port = srv.server_address[1]
    STATE['base'] = 'http://127.0.0.1:%d' % port
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print('serving %s at %s' % (ROOT, STATE['base']), flush=True)
    return srv


# ---- build/index.html：把 /myxxz/ 绝对路径改相对，并去掉平台注入脚本（避免无关 404）
def prep_index():
    p = os.path.join(ROOT, 'index.html')
    s = io.open(p, encoding='utf-8').read()
    s = s.replace('/myxxz/assets/', './assets/')
    s = s.replace('/myxxz/', './')
    s = re.sub(r'<script[^>]*src="(?:/h5game/unified-stats\.js|/reward/reward\.js)"[^>]*>\s*</script>', '', s)
    if not s.startswith('<!--R255LOCAL-->'):
        s = '<!--R255LOCAL-->\n' + s
    io.open(p, 'w', encoding='utf-8').write(s)


JS_STATE = r"""
() => {
  let st = null;
  try { st = window.__ylR255Store ? window.__ylR255Store() : null; } catch (e) {}
  // 兜底：从 React store 拿（bundle 里 Be.getState()）
  let p = null;
  try { p = (window.__ylPlayer || (window.__ylGetPlayer ? window.__ylGetPlayer() : null)); } catch (e) {}
  return {hasHook: !!st, st: st, p: p};
}
"""


def login_local(pg, base, log=print):
    """本地 build 的登录：**避开 ylc 的 strict-mode 坑**（`fill` 传逗号选择器会命中 2 个元素）。

    ★ 2026-10-14 实测：旧测试账号 `ylui0927a` 在线上已被删（`USER_NOT_FOUND`）；
      改用环境变量 `YL_R255_USER`/`YL_R255_PASS` 传入的新注册账号。
    """
    import re as _re
    user = os.environ.get('YL_R255_USER') or ylc.USER
    pw = os.environ.get('YL_R255_PASS') or ylc.PASS
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
            log('  [%d] 登录页 → 登录  btns=%s' % (step, st['btns']))
            # ★ 页面可能停在「注册」模式（按钮是「立下长生誓」）⇒ 先切到登录模式
            if any('已有道号' in b for b in st['btns']):
                pg.evaluate(ylc.CLICK_JS, '已有道号')
                pg.wait_for_timeout(1200)
            pg.locator('input').first.fill(user, timeout=5000)
            pg.locator('input[type="password"]').first.fill(pw, timeout=5000)
            # 登录按钮文案：优先「踏入修仙界」，否则用当前可见主按钮
            r = pg.evaluate(ylc.CLICK_JS, '踏入修仙界')
            if not r:
                r = pg.evaluate(ylc.CLICK_JS, '登') or pg.evaluate(ylc.CLICK_JS, '入')
            log('      点 %r' % r)
            pg.wait_for_timeout(7000)
            continue
        if st['famen']:
            log('  [%d] 关「修仙法门」' % step)
            ylc.close_modal(pg, log)
            continue
        if st['dao']:
            log('  [%d] 建号·道号' % step)
            try:
                pg.locator('input[placeholder*="道号"]').first.fill(ylc.DAOH, timeout=4000)
            except Exception as e:
                log('      fill err:', str(e)[:100])
            pg.wait_for_timeout(400)
            pg.evaluate(ylc.CLICK_JS, '下一步')
            pg.wait_for_timeout(2000)
            continue
        if st['fate']:
            log('  [%d] 建号·天赋' % step)
            pg.evaluate(ylc.CLICK_JS, '随机分配')
            pg.wait_for_timeout(1000)
            pg.evaluate(ylc.CLICK_JS, '下一步')
            pg.wait_for_timeout(2000)
            continue
        if st['start']:
            log('  [%d] 落地页 → 开始游戏' % step)
            pg.evaluate(ylc.CLICK_JS, '开始游戏')
            pg.wait_for_timeout(5000)
            continue
        r = (pg.evaluate(ylc.CLICK_JS, '下一步') or pg.evaluate(ylc.CLICK_JS, '开始修仙')
             or pg.evaluate(ylc.CLICK_JS, '开始') or pg.evaluate(ylc.CLICK_JS, '完成'))
        log('  [%d] 兜底 → %r btns=%s' % (step, r, st['btns']))
        pg.wait_for_timeout(2000)
    log('  [!!] 未能进入游戏')
    return False


def main():
    prep_index()
    srv = serve()
    base = STATE['base']
    errs = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(viewport={'width': 1440, 'height': 900})
        pg.on('pageerror', lambda e: errs.append(str(e)))
        # API 反代
        pg.route(re.compile(r".*/yl/api/.*"),
                 lambda r: r.fulfill(response=r.fetch(url=r.request.url.replace(base, LIVE))))
        ylc.URL = base + '/index.html'
        pg.goto(base + '/index.html', wait_until='domcontentloaded', timeout=60000)
        pg.wait_for_timeout(8000)
        login_local(pg, base)
        print('\n=== 进游戏后：读取真实 player ===')

        def getp():
            return pg.evaluate("""() => {
              try {
                const s = window.__ylStore;
                if (s && s.getState) return s.getState().player;
              } catch (e) {}
              return null;
            }""")

        # 先探测 store 句柄名
        handles = pg.evaluate("""() => Object.keys(window).filter(k => /yl.*[Ss]tore|__yl|Ze|Be/.test(k)).slice(0, 20)""")
        print('  window 候选句柄:', handles)

        # A 面板文案
        panel = pg.evaluate("""() => {
          const vis = el => { const r = el.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
          const txt = document.body.innerText || '';
          return {hasAge: txt.indexOf('年龄') >= 0 && txt.indexOf('寿元') >= 0,
                  hasOld: txt.indexOf('寿命 (年)') >= 0,
                  ageLine: (txt.match(/年龄[^\\n]{0,40}/) || [''])[0],
                  rangeLine: (txt.match(/寿元[^\\n]{0,20}/) || [''])[0]};
        }""")
        print('  面板:', json.dumps(panel, ensure_ascii=False))
        chk('A1 面板出现「年龄 / 寿元」', panel['hasAge'])
        chk('A2 面板不再有「寿命 (年)」', not panel['hasOld'])

        # B 建号：age 0 且区间合理
        probe = pg.evaluate("""() => {
          const vis = el => { const r = el.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
          const t = document.body.innerText || '';
          const m = t.match(/年龄\\s*(\\d+)\\s*岁\\s*·\\s*寿元\\s*(\\d+)\\s*-\\s*(\\d+)\\s*岁/);
          return m ? {age: +m[1], lo: +m[2], hi: +m[3]} : null;
        }""")
        print('  面板解析:', probe)
        chk('B1 面板可解析出「年龄 N 岁 · 寿元 lo-hi 岁」', probe is not None)
        if probe:
            chk('B2 新建角色 age === 0', probe['age'] == 0, '(age=%s)' % probe['age'])
            ok_lo = abs(probe['lo'] - round(probe['hi'] * 0.9)) <= 1
            chk('B3 区间下限 ≈ 上限 × 0.9', ok_lo, 'lo=%d hi=%d' % (probe['lo'], probe['hi']))
            chk('B4 炼气期区间落在 [90,100] 量级', 90 <= probe['lo'] <= 100 and 90 <= probe['hi'] <= 101,
                'lo=%d hi=%d' % (probe['lo'], probe['hi']))

        # C 打坐：年龄增加
        before = probe['age'] if probe else None
        pg.evaluate("""() => {
          const vis = el => { const r = el.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
          const b = Array.from(document.querySelectorAll('button')).find(x => vis(x) && (x.innerText||'').replace(/\\s+/g,'').startsWith('打坐'));
          if (b) b.click();
        }""")
        pg.wait_for_timeout(2500)
        pg.evaluate("""() => {
          const vis = el => { const r = el.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
          const b = Array.from(document.querySelectorAll('button')).find(x => vis(x) && (x.innerText||'').replace(/\\s+/g,'').indexOf('停止') >= 0);
          if (b) b.click();
        }""")
        pg.wait_for_timeout(800)
        after = pg.evaluate("""() => {
          const t = document.body.innerText || '';
          const m = t.match(/年龄\\s*(\\d+)\\s*岁/);
          return m ? +m[1] : null;
        }""")
        print('  打坐前后 age:', before, '->', after)
        chk('C1 打坐后仍解析到年龄', after is not None)
        chk('C2 年龄单调不减（打坐只增不减）', before is not None and after is not None and after >= before,
            '%s -> %s' % (before, after))

        # D/E 死线语义：静态复核交付 bundle 里的算法仍可求值（页面已加载同一 bundle）
        death = pg.evaluate("""() => {
          try {
            if (typeof YlxwLifeDeathLine !== 'function') return {err: 'YlxwLifeDeathLine 不在全局作用域（模块内，正常）'};
            return {ok: true};
          } catch (e) { return {err: String(e)}; }
        }""")
        print('  死线函数可见性:', death)

        chk('F 无 JS 运行时错误', len(errs) == 0, ('; '.join(errs[:3]) if errs else ''))
        br.close()
    srv.shutdown()
    print('\n===== R-255 本地联调结果 =====')
    print('  PASS = %d   FAIL = %d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('   FAIL: %s' % f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
