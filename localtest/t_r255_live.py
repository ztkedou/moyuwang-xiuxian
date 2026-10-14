# -*- coding: utf-8 -*-
r"""最终线上验收：在**真实线上站点**（moyuwang.online/myxxz）跑年龄制端到端。

与 t_r255_death.py 的区别：那条走**本地 build/** 静态服务 + API 反代；
本脚本直接打**线上 URL**，验证「玩家现在打开游戏看到的就是年龄制」。
"""
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(HERE)
os.chdir(ROOTDIR)
sys.path.insert(0, ROOTDIR)
sys.path.insert(0, HERE)
import ylc  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

LIVE = 'https://moyuwang.online/myxxz/'
API = 'https://moyuwang.online/yl/api'
USER = os.environ.get('YL_R255_USER') or ylc.USER
PW = os.environ.get('YL_R255_PASS') or ylc.PASS
PASS, FAIL = [], []


def chk(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('  [%s] %s %s' % ('PASS' if cond else 'FAIL', name, detail))


def api(path, token=None, data=None, method=None, extra=None):
    hdr = {'Content-Type': 'application/json'}
    if token:
        hdr['Authorization'] = 'Bearer ' + token
    if extra:
        hdr.update(extra)
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.urlopen(urllib.request.Request(API + path, data=body, headers=hdr,
                                                      method=method), timeout=30)
    return json.loads(r.read().decode('utf-8'))


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
    print('=== 0. 线上 URL 与 API ===')
    print('  站点:', LIVE)
    tok = api('/auth/login', data={'username': USER, 'password': PW})['token']
    p0 = api('/save', token=tok)['player']
    chk('0a 线上存档含 age', 'age' in p0, 'age=%s' % p0.get('age'))
    chk('0b 线上存档无 lifespan 键', 'lifespan' not in p0)
    if 'lifeRatio' in p0:
        r = float(p0['lifeRatio'])
        chk('0c maxLifespan == lifeRatio × 100', abs(float(p0['maxLifespan']) - r * 100) < 1e-6,
            '%.6f vs %.6f' % (float(p0['maxLifespan']), r * 100))

    errs = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        pg = br.new_page(viewport={'width': 1440, 'height': 900})
        pg.on('pageerror', lambda e: errs.append(str(e)[:200]))
        # ★ 不打任何 route：直接访问线上真实站点
        pg.goto(LIVE, wait_until='domcontentloaded', timeout=60000)
        pg.wait_for_timeout(9000)

        # 确认加载的是新包
        loaded = pg.evaluate("""() => Array.from(document.querySelectorAll('script[src]')).map(s=>s.src)""")
        print('  已加载脚本:', loaded)
        chk('1a 加载的是 v2961 包', any('index-v2961-20261011.js' in s for s in loaded), str(loaded))

        if not login(pg):
            print('  [!!] 登录失败'); br.close(); return 1

        panel = pg.evaluate("""() => {
          const t = document.body.innerText || '';
          const m = t.match(/年龄\\s*(\\d+)\\s*岁\\s*·\\s*寿元\\s*(\\d+)\\s*-\\s*(\\d+)\\s*岁/);
          return {hasOld: t.indexOf('寿命 (年)') >= 0, m: m ? [+m[1],+m[2],+m[3]] : null,
                  line: (t.match(/年龄[^\\n]{0,32}/) || [''])[0], ver: (t.match(/0\\.9\\.\\d+/)||[''])[0]};
        }""")
        print('  面板:', json.dumps(panel, ensure_ascii=False))
        chk('2a 线上面板无旧「寿命 (年)」', not panel['hasOld'])
        chk('2b 线上面板可解析「年龄 N 岁 · 寿元 lo-hi 岁」', panel['m'] is not None, panel['line'])
        if panel['m']:
            age, lo, hi = panel['m']
            chk('2c 区间下限 ≈ 上限 × 0.9', abs(lo - round(hi * 0.9)) <= 1, 'lo=%d hi=%d' % (lo, hi))
            chk('2d 炼气期区间为 90-100', (lo, hi) == (90, 100), 'lo=%d hi=%d' % (lo, hi))
        chk('2e 页面版本号为 0.9.61', panel['ver'] == '0.9.61', panel['ver'])

        # 打坐 → 年龄增长（线上真实写入）
        a0 = float(api('/save', token=tok)['player'].get('age') or 0)
        pg.evaluate("""() => {
          const vis = el => { const r = el.getBoundingClientRect(); return r.width>1 && r.height>1; };
          const b = Array.from(document.querySelectorAll('button')).find(x => vis(x) && (x.innerText||'').replace(/\\s+/g,'').startsWith('打坐'));
          if (b) b.click();
        }""")
        pg.wait_for_timeout(25000)
        pg.evaluate("""() => {
          const vis = el => { const r = el.getBoundingClientRect(); return r.width>1 && r.height>1; };
          const b = Array.from(document.querySelectorAll('button')).find(x => vis(x) && (x.innerText||'').replace(/\\s+/g,'').indexOf('停止')>=0);
          if (b) b.click();
        }""")
        pg.wait_for_timeout(16000)
        a1 = float(api('/save', token=tok)['player'].get('age') or 0)
        print('  线上 age: %.6f -> %.6f  (delta %.6f)' % (a0, a1, a1 - a0))
        chk('3a 线上打坐后 age 增加', a1 > a0, 'delta=%.6f' % (a1 - a0))
        chk('3b 增量贴近 0.0002/跳 设计速率', 0 < (a1 - a0) < 0.05, 'delta=%.6f' % (a1 - a0))

        pg.screenshot(path=os.path.join(HERE, '_r255_live_panel.png'))
        chk('4 无 JS 运行时错误', len(errs) == 0, ('; '.join(errs[:3]) if errs else ''))
        br.close()

    print('\n===== R-252 线上端到端验收 =====')
    print('  PASS = %d   FAIL = %d' % (len(PASS), len(FAIL)))
    for f in FAIL:
        print('   FAIL: %s' % f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
