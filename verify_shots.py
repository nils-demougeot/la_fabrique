"""Capture d'écran mobile des pages de La Fabrique via Chrome DevTools Protocol.

Pourquoi CDP plutôt que `chrome --headless --window-size` : la mise à l'échelle
d'affichage de Windows (120 %) gonfle le viewport et rend les captures brutes
inexploitables. `Emulation.setDeviceMetricsOverride` force un 390 × 844 exact.

Dépendance (dev uniquement, volontairement absente de requirements.txt) :
    pip install websocket-client

Utilisation :
    1) lancer le serveur    : python manage.py runserver 8123
       (sans --noreload : depuis Django 4.1 le chargeur de gabarits est mis en
        cache même en DEBUG, une modification de template passerait inaperçue)
    2) lancer Chrome        : chrome --headless=new --remote-debugging-port=9333
                                     --remote-allow-origins=* --user-data-dir=<tmp>
    3) puis                 : SHOT_USER=... SHOT_PASS=... python verify_shots.py [chemins]

Variante sans mot de passe : SHOT_SESSION=<sessionid> injecte directement le
cookie de session (utile pour un compte dont on ne connaît pas le mot de passe).

Les images atterrissent dans shots/.
"""

import base64
import json
import os
import sys
import time

import requests
import websocket

CDP_PORT = int(os.environ.get('SHOT_CDP_PORT', '9333'))
BASE_URL = os.environ.get('SHOT_BASE_URL', 'http://127.0.0.1:8123')
USERNAME = os.environ.get('SHOT_USER', '')
PASSWORD = os.environ.get('SHOT_PASS', '')
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shots')

WIDTH, HEIGHT = 390, 844


class Tab:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self._id = 0

    def send(self, method, **params):
        self._id += 1
        self.ws.send(json.dumps({'id': self._id, 'method': method, 'params': params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get('id') == self._id:
                if 'error' in msg:
                    raise RuntimeError(f'{method}: {msg["error"]}')
                return msg.get('result', {})

    def close(self):
        self.ws.close()


def evaluate(tab, expression):
    res = tab.send('Runtime.evaluate', expression=expression, awaitPromise=True,
                   returnByValue=True)
    return res.get('result', {}).get('value')


def goto(tab, url, wait=1.4):
    tab.send('Page.navigate', url=url)
    time.sleep(0.4)
    # Sans cela, revenir sur une URL déjà visitée resservirait la version en
    # cache : les modifications de gabarit passeraient inaperçues.
    tab.send('Page.reload', ignoreCache=True)
    time.sleep(wait)


def main(paths):
    os.makedirs(OUT_DIR, exist_ok=True)

    tabs = requests.get(f'http://127.0.0.1:{CDP_PORT}/json').json()
    page = next(t for t in tabs if t['type'] == 'page')
    tab = Tab(page['webSocketDebuggerUrl'])

    tab.send('Page.enable')
    tab.send('Runtime.enable')
    tab.send('Emulation.setDeviceMetricsOverride', width=WIDTH, height=HEIGHT,
             deviceScaleFactor=2, mobile=True)

    session_id = os.environ.get('SHOT_SESSION', '')
    if session_id:
        goto(tab, BASE_URL + '/', wait=0.8)
        tab.send('Network.enable')
        tab.send('Network.setCookie', name='sessionid', value=session_id,
                 url=BASE_URL, path='/')
    elif USERNAME:
        goto(tab, f'{BASE_URL}/connexion/', wait=1.2)
        evaluate(tab, f"""
            (function () {{
                const f = document.querySelector('form');
                f.querySelector('[name=username]').value = {json.dumps(USERNAME)};
                f.querySelector('[name=password]').value = {json.dumps(PASSWORD)};
                f.submit();
                return true;
            }})()
        """)
        time.sleep(2.0)

    # SHOT_SCROLL=0,600,1200 → une capture par position de défilement.
    offsets = [int(v) for v in os.environ.get('SHOT_SCROLL', '0').split(',') if v != '']
    # SHOT_JS="dashOpen('sheet-coins')" → script exécuté avant la capture.
    pre_js = os.environ.get('SHOT_JS', '')

    for path in paths:
        goto(tab, BASE_URL + path, wait=2.2)
        name = (path.strip('/') or 'home').replace('/', '_')
        if pre_js:
            evaluate(tab, pre_js)
            time.sleep(1.0)

        for offset in offsets:
            evaluate(tab, "(document.querySelector('.scrollable-content')"
                          f" || document.scrollingElement).scrollTop = {offset};")
            time.sleep(0.35)
            data = tab.send('Page.captureScreenshot', format='png')['data']
            suffix = '' if len(offsets) == 1 else f'_{offset}'
            dest = os.path.join(OUT_DIR, f'{name}{suffix}.png')
            with open(dest, 'wb') as fh:
                fh.write(base64.b64decode(data))
            print(f'{path} @{offset} -> {dest}')

    tab.close()


if __name__ == '__main__':
    main(sys.argv[1:] or ['/dashboard/'])
